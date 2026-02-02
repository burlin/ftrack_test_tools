"""
Полный тест трансфера компонента:
1. Копирование файла из source location в target location (S3)
2. Регистрация компонента в target location
3. Удаление компонента из target location

Использование:
    python tools/test_full_transfer.py <component_id> [target_location_name]
    
Пример:
    python tools/test_full_transfer.py 0000075b-df8b-48a4-81c5-5aa831b6af9a s3.minio
"""

import os
import sys
from pathlib import Path

# Bootstrap environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from run_browser import _bootstrap_environment
_bootstrap_environment(PROJECT_ROOT)

import ftrack_api
import logging
import hashlib
import shutil
import boto3
from botocore.config import Config
from boto3.s3.transfer import TransferConfig
from typing import Optional
import fileseq
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid

# Загружаем плагины локаций
LOCATIONS_PLUGIN_PATH = PROJECT_ROOT / 'ftrack_plugins' / 'multi-site-location-0.2.0'
if str(LOCATIONS_PLUGIN_PATH / 'hook' / 'locations') not in sys.path:
    sys.path.insert(0, str(LOCATIONS_PLUGIN_PATH / 'hook' / 'locations'))
    sys.path.insert(0, str(LOCATIONS_PLUGIN_PATH / 'dependencies'))

try:
    from s3_location_plugin import session_add_s3_location
    from user_location_plugin import session_add_user_location, load_location_config
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"Не удалось загрузить плагины локаций: {e}")


def load_location_plugins(session: ftrack_api.Session):
    """Загрузить плагины локаций в сессию."""
    try:
        # Загружаем S3 локации
        session_add_s3_location(session)
    except Exception as e:
        logger.warning(f"Не удалось загрузить S3 локации: {e}")
    
    try:
        # Загружаем Disk локации
        location_setup = load_location_config(
            config_path=LOCATIONS_PLUGIN_PATH / 'hook' / 'locations' / 'disk_locations.yaml',
            user_name=session.api_user
        )
        session_add_user_location(session, location_setup)
    except Exception as e:
        logger.warning(f"Не удалось загрузить Disk локации: {e}")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def calculate_file_hash(filepath: str, algorithm: str = 'md5') -> str:
    """Вычислить hash файла."""
    hash_obj = hashlib.new(algorithm)
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def copy_file_with_progress(source_path: str, target_path: str, chunk_size: int = 1024 * 1024) -> tuple[bool, int]:
    """Скопировать файл с отслеживанием прогресса.
    
    Returns:
        (success, bytes_copied)
    """
    try:
        import time
        # Создаём директорию если нужно
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        total_size = os.path.getsize(source_path)
        bytes_copied = 0
        start_time = time.time()
        last_log_time = start_time
        
        with open(source_path, 'rb') as src:
            with open(target_path, 'wb') as dst:
                while True:
                    chunk = src.read(chunk_size)
                    if not chunk:
                        break
                    dst.write(chunk)
                    bytes_copied += len(chunk)
                    
                    # Логируем прогресс каждые 10% или каждые 5 секунд
                    current_time = time.time()
                    progress = (bytes_copied / total_size) * 100
                    elapsed = current_time - start_time
                    speed = (bytes_copied / elapsed / (1024 * 1024)) if elapsed > 0 else 0
                    
                    if (int(progress) % 10 == 0 and bytes_copied > 0) or (current_time - last_log_time >= 5.0):
                        logger.info(f"  Прогресс: {progress:.1f}% ({bytes_copied}/{total_size} bytes) - {speed:.2f} MB/s")
                        last_log_time = current_time
        
        elapsed = time.time() - start_time
        speed = (bytes_copied / elapsed / (1024 * 1024)) if elapsed > 0 else 0
        logger.info(f"✓ Файл скопирован: {bytes_copied}/{total_size} bytes")
        logger.info(f"  Время: {elapsed:.2f} сек, Скорость: {speed:.2f} MB/s")
        return True, bytes_copied
    except Exception as e:
        logger.error(f"✗ Ошибка копирования: {e}", exc_info=True)
        return False, 0


def copy_to_s3_with_progress(source_path: str, bucket: str, key: str, 
                              endpoint_url: Optional[str] = None,
                              s3_client: Optional[boto3.client] = None,
                              transfer_config: Optional[TransferConfig] = None) -> tuple[bool, int]:
    """Скопировать файл в S3 с отслеживанием прогресса.
    
    Args:
        source_path: Путь к исходному файлу
        bucket: Имя S3 bucket
        key: S3 key для файла
        endpoint_url: URL endpoint для S3 (если не указан, берётся из env)
        s3_client: Опциональный предсозданный S3 клиент для переиспользования
        transfer_config: Опциональная конфигурация TransferConfig для настройки multipart upload
    
    Returns:
        (success, bytes_copied)
    """
    try:
        if s3_client is None:
            s3_client = boto3.client(
                's3',
                endpoint_url=endpoint_url or os.getenv('S3_MINIO_ENDPOINT_URL'),
                config=Config(signature_version='s3v4'),
                use_ssl=True,
                verify=True,
            )
        
        import time
        total_size = os.path.getsize(source_path)
        bytes_copied = [0]  # Используем список для изменения в callback
        start_time = [time.time()]  # Время начала загрузки
        
        def progress_callback(bytes_amount):
            bytes_copied[0] += bytes_amount
            current_time = time.time()
            elapsed = current_time - start_time[0]
            progress = (bytes_copied[0] / total_size) * 100 if total_size > 0 else 0
            speed = (bytes_copied[0] / elapsed / (1024 * 1024)) if elapsed > 0 else 0
            
            if int(progress) % 10 == 0 and bytes_copied[0] > 0:
                logger.info(f"  Прогресс S3: {progress:.1f}% ({bytes_copied[0]}/{total_size} bytes) - {speed:.2f} MB/s")
        
        # Если transfer_config не указан, создаём оптимальный для больших файлов
        if transfer_config is None:
            # Динамически подбираем размер чанка в зависимости от размера файла
            if total_size > 100 * 1024 * 1024 * 1024:  # > 100 GB
                chunk_size = 128 * 1024 * 1024  # 128 MB
                concurrency = 10
            elif total_size > 10 * 1024 * 1024 * 1024:  # > 10 GB
                chunk_size = 64 * 1024 * 1024  # 64 MB
                concurrency = 15
            elif total_size > 1024 * 1024 * 1024:  # > 1 GB
                chunk_size = 32 * 1024 * 1024  # 32 MB
                concurrency = 15
            else:
                chunk_size = 16 * 1024 * 1024  # 16 MB
                concurrency = 10
            
            transfer_config = TransferConfig(
                multipart_threshold=5 * 1024 * 1024,  # 5 MB
                multipart_chunksize=chunk_size,
                max_concurrency=concurrency,
                use_threads=True
            )
            logger.info(f"  TransferConfig: chunk_size={chunk_size/(1024*1024):.0f}MB, concurrency={concurrency}")
        
        with open(source_path, 'rb') as f:
            s3_client.upload_fileobj(
                f,
                bucket,
                key,
                Config=transfer_config,
                Callback=progress_callback
            )
        
        elapsed = time.time() - start_time[0]
        speed = (bytes_copied[0] / elapsed / (1024 * 1024)) if elapsed > 0 else 0
        logger.info(f"✓ Файл загружен в S3: {bytes_copied[0]}/{total_size} bytes")
        logger.info(f"  Время: {elapsed:.2f} сек, Скорость: {speed:.2f} MB/s")
        return True, bytes_copied[0]
    except Exception as e:
        logger.error(f"✗ Ошибка загрузки в S3: {e}", exc_info=True)
        return False, 0


def test_full_transfer(component_id: str, target_location_name: Optional[str] = None):
    """Полный тест трансфера компонента."""
    session = ftrack_api.Session()
    
    # Загружаем плагины локаций, чтобы accessor были доступны
    try:
        load_location_plugins(session)
    except Exception as e:
        logger.warning(f"Не удалось загрузить плагины локаций: {e}")
    
    try:
        logger.info("=" * 80)
        logger.info("ПОЛНЫЙ ТЕСТ ТРАНСФЕРА")
        logger.info("=" * 80)
        logger.info(f"Component ID: {component_id}")
        
        # 1. Получаем компонент
        logger.info("\n[1/5] Получение компонента...")
        try:
            component = session.get('Component', component_id)
            if not component:
                logger.error(f"✗ Компонент не найден: ID {component_id}")
                return
            logger.info(f"✓ Компонент: {component['name']} (ID: {component['id']})")
            logger.info(f"  Размер: {component.get('size', 'N/A')} bytes")
            logger.info(f"  Тип: {component.entity_type}")
        except Exception as e:
            logger.error(f"✗ Компонент не найден: {e}", exc_info=True)
            return
        
        # 2. Находим source location (где компонент есть И файл существует)
        logger.info("\n[2/5] Поиск source location...")
        locations = session.query('Location').all()
        source_location = None
        
        # Сначала ищем локации, где компонент зарегистрирован
        candidate_locations = []
        for loc in locations:
            try:
                availability = loc.get_component_availability(component)
                if availability == 100.0:
                    candidate_locations.append(loc)
            except Exception:
                continue
        
        if not candidate_locations:
            logger.error("✗ Не найдена локация, где компонент доступен на 100%")
            return
        
        # Проверяем, где файл физически существует (для Disk локаций)
        for loc in candidate_locations:
            if loc.accessor and isinstance(loc.accessor, ftrack_api.accessor.disk.DiskAccessor):
                try:
                    path = loc.get_filesystem_path(component)
                    if os.path.exists(path):
                        source_location = loc
                        logger.info(f"✓ Source location: {loc['name']} (availability: 100%, файл существует)")
                        break
                except Exception:
                    continue
        
        # Если не нашли Disk с файлом, берём первую кандидатку (для S3 или если файл не нужен)
        if not source_location and candidate_locations:
            source_location = candidate_locations[0]
            logger.info(f"✓ Source location: {source_location['name']} (availability: 100%)")
        
        if not source_location:
            logger.error("✗ Не найдена подходящая source location")
            return
        
        # Получаем resource_identifier из source
        try:
            source_resource_id = source_location.get_resource_identifier(component)
            logger.info(f"  Source resource_identifier: {source_resource_id}")
        except Exception as e:
            logger.error(f"✗ Не удалось получить source resource_identifier: {e}")
            return
        
        # Получаем реальный путь/URL
        source_path = None
        
        # Проверяем тип accessor
        if source_location.accessor:
            logger.info(f"  Source accessor: {type(source_location.accessor).__name__}")
            
            if isinstance(source_location.accessor, ftrack_api.accessor.disk.DiskAccessor):
                try:
                    source_path = source_location.get_filesystem_path(component)
                    
                    # Проверяем, является ли это последовательностью
                    is_sequence = False
                    sequence_files = []
                    
                    if component.entity_type == 'SequenceComponent' or '%' in str(source_path) or '@' in str(source_path):
                        is_sequence = True
                        logger.info(f"  Обнаружена последовательность: {source_path}")
                        
                        # Используем fileseq для поиска файлов
                        try:
                            seq = fileseq.findSequenceOnDisk(str(source_path))
                            if seq:
                                sequence_files = [str(f) for f in seq]
                                logger.info(f"  Найдено файлов в последовательности: {len(sequence_files)}")
                                if sequence_files:
                                    logger.info(f"  Первый файл: {sequence_files[0]}")
                                    logger.info(f"  Последний файл: {sequence_files[-1]}")
                            else:
                                logger.warning(f"  Последовательность не найдена на диске: {source_path}")
                                return
                        except Exception as e:
                            logger.error(f"✗ Ошибка поиска последовательности: {e}", exc_info=True)
                            return
                    else:
                        # Обычный файл
                        if not os.path.exists(source_path):
                            logger.error(f"✗ Файл не существует: {source_path}")
                            return
                        sequence_files = [source_path]
                    
                    logger.info(f"  Source path: {source_path}")
                    logger.info(f"  Тип: {'Последовательность' if is_sequence else 'Одиночный файл'}")
                    logger.info(f"  Файлов для копирования: {len(sequence_files)}")
                    
                    # Вычисляем общий размер (файлы уже проверены fileseq.findSequenceOnDisk)
                    logger.info("  Вычисление общего размера...")
                    total_size = 0
                    for f in sequence_files:
                        try:
                            total_size += os.path.getsize(f)
                        except OSError:
                            # Файл мог быть удалён, пропускаем
                            pass
                    logger.info(f"  Общий размер: {total_size} bytes ({total_size / 1024 / 1024:.2f} MB)")
                    
                except Exception as e:
                    logger.error(f"✗ Не удалось получить путь: {e}", exc_info=True)
                    return
            elif 's3' in str(type(source_location.accessor)).lower():
                logger.info("  Source location - S3")
                try:
                    source_url = source_location.get_url(component)
                    logger.info(f"  Source URL: {source_url[:100]}..." if len(str(source_url)) > 100 else f"  Source URL: {source_url}")
                    logger.warning("⚠ S3→S3 трансфер реализуем позже, сейчас только Disk→S3")
                    return
                except Exception as e:
                    logger.error(f"✗ Не удалось получить URL: {e}")
                    return
            else:
                logger.warning(f"  Неизвестный тип accessor: {type(source_location.accessor)}")
                # Попробуем всё равно получить путь через get_filesystem_path
                try:
                    source_path = source_location.get_filesystem_path(component)
                    if os.path.exists(source_path):
                        logger.info(f"  Source path (через get_filesystem_path): {source_path}")
                        logger.info(f"  Файл существует: ✓")
                        logger.info(f"  Размер файла: {os.path.getsize(source_path)} bytes")
                    else:
                        logger.error(f"✗ Файл не существует: {source_path}")
                        return
                except Exception as e:
                    logger.error(f"✗ Не удалось получить путь: {e}")
                    return
        else:
            logger.error("✗ Source location не имеет accessor")
            return
        
        # 3. Находим target location (S3 или Disk)
        logger.info("\n[3/5] Поиск target location...")
        target_location = None
        
        if target_location_name:
            for loc in locations:
                if loc['name'] == target_location_name:
                    target_location = loc
                    break
        
        if not target_location:
            logger.error(f"✗ Локация '{target_location_name}' не найдена")
            return
        
        logger.info(f"✓ Target location: {target_location['name']}")
        
        # Проверяем, что target location отличается от source
        if target_location['id'] == source_location['id']:
            logger.error("✗ Target location совпадает с source location")
            return
        
        # Проверяем, что у target location есть structure
        if not hasattr(target_location, 'structure') or not target_location.structure:
            logger.error(f"✗ Target location не имеет structure")
            return
        
        # Генерируем resource_identifier для target
        try:
            context = {'source_resource_identifier': source_resource_id}
            target_resource_id = target_location.structure.get_resource_identifier(component, context)
            
            # Добавляем случайную папку для каждого теста
            random_folder = str(uuid.uuid4())[:8]  # Первые 8 символов UUID
            # Добавляем папку перед именем файла
            if '/' in target_resource_id:
                parts = target_resource_id.rsplit('/', 1)
                target_resource_id = f"{parts[0]}/{random_folder}/{parts[1]}"
            else:
                target_resource_id = f"{random_folder}/{target_resource_id}"
            
            logger.info(f"  Target resource_identifier: {target_resource_id}")
            logger.info(f"  Случайная папка для теста: {random_folder}")
        except Exception as e:
            logger.error(f"✗ Не удалось сгенерировать target resource_identifier: {e}")
            return
        
        # Проверяем, не зарегистрирован ли уже компонент в target
        try:
            existing_availability = target_location.get_component_availability(component)
            if existing_availability > 0:
                logger.warning(f"⚠ Компонент уже доступен в target location на {existing_availability}%")
                logger.info("  Компонент уже существует в target location, пропускаем удаление")
        except ftrack_api.exception.ComponentNotInLocationError:
            logger.info("  Компонент ещё не зарегистрирован в target location")
        
        # 4. Копируем файл
        logger.info("\n[4/5] Копирование файла...")
        
        # Засекаем время начала
        import time
        transfer_start_time = time.time()
        
        # Определяем тип target location
        is_s3_target = False
        is_disk_target = False
        
        if target_location.accessor:
            if 's3' in str(type(target_location.accessor)).lower():
                is_s3_target = True
            elif isinstance(target_location.accessor, ftrack_api.accessor.disk.DiskAccessor):
                is_disk_target = True
        
        if not is_s3_target and not is_disk_target:
            logger.error("✗ Target location должна быть Disk или S3")
            return
        
        # Копируем в зависимости от типа target
        if is_s3_target:
            # Копирование в S3
            s3_bucket = os.getenv('S3_BUCKET', 'proj')
            s3_endpoint = os.getenv('S3_MINIO_ENDPOINT_URL')
            
            logger.info(f"  Target: S3")
            logger.info(f"  S3 Bucket: {s3_bucket}")
            logger.info(f"  S3 Endpoint: {s3_endpoint}")
            logger.info(f"  S3 Key (pattern): {target_resource_id}")
            
            # Если это последовательность, копируем все файлы
            if len(sequence_files) > 1:
                max_workers = 5  # Количество параллельных потоков
                logger.info(f"  Копирование последовательности из {len(sequence_files)} файлов в {max_workers} потоков...")
                
                # Генерируем S3 keys для каждого файла
                try:
                    import re
                    import threading
                    
                    # Thread-local storage для S3 клиентов (boto3 клиент не thread-safe)
                    thread_local = threading.local()
                    
                    def get_s3_client():
                        """Получить S3 клиент для текущего потока."""
                        if not hasattr(thread_local, 's3_client'):
                            thread_local.s3_client = boto3.client(
                                's3',
                                endpoint_url=s3_endpoint,
                                config=Config(signature_version='s3v4'),
                                use_ssl=True,
                                verify=True,
                            )
                        return thread_local.s3_client
                    
                    # Подготовим список задач
                    tasks = []
                    for idx, source_file in enumerate(sequence_files):
                        if not os.path.exists(source_file):
                            logger.warning(f"  Пропускаем несуществующий файл: {source_file}")
                            continue
                        
                        # Извлекаем номер кадра из имени файла
                        frame_match = re.search(r'\.(\d+)\.', os.path.basename(source_file))
                        if frame_match:
                            frame_num = int(frame_match.group(1))
                        else:
                            frame_num = idx
                        
                        # Генерируем S3 key для этого файла
                        target_key = target_resource_id.replace('%04d', f'{frame_num:04d}')
                        
                        tasks.append((idx, source_file, target_key, frame_num))
                    
                    total_bytes = 0
                    files_copied = 0
                    files_failed = 0
                    
                    def copy_single_file(task_data):
                        """Копирует один файл и возвращает результат."""
                        idx, source_file, target_key, frame_num = task_data
                        try:
                            logger.info(f"  [{idx+1}/{len(tasks)}] Начало: {os.path.basename(source_file)} -> {target_key}")
                            # Получаем thread-local S3 клиент
                            s3_client = get_s3_client()
                            file_success, file_bytes = copy_to_s3_with_progress(
                                source_file,
                                s3_bucket,
                                target_key,
                                s3_endpoint,
                                s3_client=s3_client  # Используем thread-local клиент
                            )
                            if file_success:
                                logger.info(f"  [{idx+1}/{len(tasks)}] ✓ Завершено: {os.path.basename(source_file)} ({file_bytes} bytes)")
                                return (True, file_bytes, idx)
                            else:
                                logger.error(f"  [{idx+1}/{len(tasks)}] ✗ Ошибка: {os.path.basename(source_file)}")
                                return (False, 0, idx)
                        except Exception as e:
                            logger.error(f"  [{idx+1}/{len(tasks)}] ✗ Исключение: {os.path.basename(source_file)} - {e}", exc_info=True)
                            return (False, 0, idx)
                    
                    # Запускаем параллельное копирование
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        future_to_task = {executor.submit(copy_single_file, task): task for task in tasks}
                        
                        for future in as_completed(future_to_task):
                            task = future_to_task[future]
                            try:
                                file_success, file_bytes, idx = future.result()
                                if file_success:
                                    total_bytes += file_bytes
                                    files_copied += 1
                                else:
                                    files_failed += 1
                            except Exception as e:
                                logger.error(f"  ✗ Исключение при обработке результата: {e}", exc_info=True)
                                files_failed += 1
                    
                    if files_failed > 0:
                        logger.error(f"✗ Ошибки при копировании: {files_failed} файлов не скопированы")
                        return
                    
                    logger.info(f"✓ Последовательность скопирована: {files_copied}/{len(tasks)} файлов, {total_bytes} bytes ({total_bytes / 1024 / 1024:.2f} MB)")
                    success = True
                    bytes_copied = total_bytes
                    
                except Exception as e:
                    logger.error(f"✗ Ошибка копирования последовательности: {e}", exc_info=True)
                    return
            else:
                # Одиночный файл
                logger.info("  Вычисление hash исходного файла...")
                source_hash = calculate_file_hash(sequence_files[0])
                logger.info(f"  Source MD5: {source_hash}")
                
                success, bytes_copied = copy_to_s3_with_progress(
                    sequence_files[0],
                    s3_bucket,
                    target_resource_id,
                    s3_endpoint
                )
        elif is_disk_target:
            # Копирование на Disk
            logger.info(f"  Target: Disk")
            
            if len(sequence_files) > 1:
                logger.info(f"  Копирование последовательности из {len(sequence_files)} файлов...")
                import re
                total_bytes = 0
                files_copied = 0
                
                for idx, source_file in enumerate(sequence_files):
                    if not os.path.exists(source_file):
                        logger.warning(f"  Пропускаем несуществующий файл: {source_file}")
                        continue
                    
                    # Извлекаем номер кадра из имени файла
                    frame_match = re.search(r'\.(\d+)\.', os.path.basename(source_file))
                    if frame_match:
                        frame_num = int(frame_match.group(1))
                    else:
                        frame_num = idx
                    
                    # Формируем resource_identifier для этого файла
                    file_resource_id = target_resource_id.replace('%04d', f'{frame_num:04d}')
                    
                    # Получаем полный путь
                    target_file_path = target_location.accessor.get_filesystem_path(file_resource_id)
                    
                    logger.info(f"  [{idx+1}/{len(sequence_files)}] Копирование: {os.path.basename(source_file)} -> {target_file_path}")
                    
                    # Создаём директорию, если нужно
                    os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                    
                    file_success, file_bytes = copy_file_with_progress(source_file, target_file_path)
                    if file_success:
                        total_bytes += file_bytes
                        files_copied += 1
                    else:
                        logger.error(f"  ✗ Ошибка копирования файла: {source_file}")
                
                if files_copied == len(sequence_files):
                    logger.info(f"✓ Последовательность скопирована: {files_copied}/{len(sequence_files)} файлов, {total_bytes} bytes ({total_bytes / 1024 / 1024:.2f} MB)")
                    success = True
                    bytes_copied = total_bytes
                else:
                    logger.error(f"✗ Ошибки при копировании: {len(sequence_files) - files_copied} файлов не скопированы")
                    success = False
            else:
                # Одиночный файл
                target_path = target_location.accessor.get_filesystem_path(target_resource_id)
                logger.info(f"  Target path: {target_path}")
                
                logger.info("  Вычисление hash исходного файла...")
                source_hash = calculate_file_hash(sequence_files[0])
                logger.info(f"  Source MD5: {source_hash}")
                
                # Создаём директорию, если нужно
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                
                success, bytes_copied = copy_file_with_progress(sequence_files[0], target_path)
                
                if success:
                    # Проверяем целостность (hash)
                    logger.info("\n  Проверка целостности...")
                    target_hash = calculate_file_hash(target_path)
                    logger.info(f"  Target MD5: {target_hash}")
                    
                    if source_hash == target_hash:
                        logger.info("  ✓ Hash совпадает - файл скопирован корректно")
                    else:
                        logger.error("  ✗ Hash не совпадает - файл повреждён!")
                        success = False
        
        if not success:
            logger.error("✗ Копирование не удалось")
            return
        
        # Вычисляем время и скорость
        transfer_end_time = time.time()
        transfer_duration = transfer_end_time - transfer_start_time
        transfer_speed_mbps = (bytes_copied / transfer_duration / (1024 * 1024)) if transfer_duration > 0 else 0
        
        logger.info(f"\n  Время копирования: {transfer_duration:.2f} секунд ({transfer_duration/60:.2f} минут)")
        logger.info(f"  Скорость: {transfer_speed_mbps:.2f} MB/s")
        logger.info(f"  Скопировано: {bytes_copied / (1024*1024):.2f} MB")
        
        # 5. Регистрируем компонент в target location
        # ЗАКОММЕНТИРОВАНО: регистрация отключена для тестирования
        # logger.info("\n[5/5] Регистрация компонента в target location...")
        # try:
        #     # Создаём ComponentLocation запись
        #     component_location = session.create(
        #         'ComponentLocation',
        #         data={
        #             'component': component,
        #             'location': target_location,
        #             'resource_identifier': target_resource_id
        #         }
        #     )
        #     session.commit()
        #     logger.info(f"✓ Компонент зарегистрирован в target location")
        #     logger.info(f"  ComponentLocation ID: {component_location['id']}")
        #     
        #     # Проверяем доступность
        #     availability = target_location.get_component_availability(component)
        #     logger.info(f"  Доступность: {availability}%")
        #     
        # except Exception as e:
        #     logger.error(f"✗ Ошибка регистрации: {e}", exc_info=True)
        #     return
        
        logger.info("\n" + "=" * 80)
        logger.info("ТЕСТ ЗАВЕРШЁН УСПЕШНО")
        logger.info("=" * 80)
        logger.info(f"\nФайлы скопированы в папку: {random_folder}")
        # logger.info("\nДля удаления компонента из target location выполните:")
        # logger.info(f"  python tools/test_full_transfer.py {component_id} {target_location['name']} --delete")
        
    except Exception as e:
        logger.error(f"✗ Общая ошибка: {e}", exc_info=True)
    finally:
        session.close()


# ЗАКОММЕНТИРОВАНО: функция удаления отключена для тестирования
# def delete_from_location(component_id: str, location_name: str):
#     """Удалить компонент из локации."""
#     session = ftrack_api.Session()
#     
#     # Загружаем плагины локаций
#     try:
#         load_location_plugins(session)
#     except Exception as e:
#         logger.warning(f"Не удалось загрузить плагины локаций: {e}")
#     
#     try:
#         logger.info("=" * 80)
#         logger.info("УДАЛЕНИЕ КОМПОНЕНТА ИЗ ЛОКАЦИИ")
#         logger.info("=" * 80)
#         
#         component = session.get('Component', component_id)
#         location = session.query(f'Location where name is "{location_name}"').one()
#         
#         logger.info(f"Component: {component['name']} (ID: {component_id})")
#         logger.info(f"Location: {location['name']}")
#         
#         # Удаляем ComponentLocation
#         try:
#             location_id = location['id']
#             component_location = session.query(
#                 f'ComponentLocation where component_id is "{component_id}" '
#                 f'and location_id is "{location_id}"'
#             ).one()
#             
#             logger.info(f"Найден ComponentLocation: {component_location['id']}")
#             logger.info(f"Resource identifier: {component_location['resource_identifier']}")
#             
#             # Удаляем запись
#             session.delete(component_location)
#             session.commit()
#             
#             logger.info("✓ ComponentLocation удалён из БД")
#             
#             # TODO: Здесь можно удалить файл из S3/диска, но для безопасности оставим
#             
#         except Exception as e:
#             logger.error(f"✗ Ошибка удаления: {e}", exc_info=True)
#             
#     except Exception as e:
#         logger.error(f"✗ Общая ошибка: {e}", exc_info=True)
#     finally:
#         session.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    component_id = sys.argv[1]
    target_location_name = sys.argv[2] if len(sys.argv) > 2 else None
    
    # ЗАКОММЕНТИРОВАНО: удаление отключено для тестирования
    # if '--delete' in sys.argv:
    #     if not target_location_name:
    #         print("Ошибка: для удаления нужна target_location_name")
    #         sys.exit(1)
    #     delete_from_location(component_id, target_location_name)
    # else:
    test_full_transfer(component_id, target_location_name)
