"""
Тестовый скрипт для отладки скачивания файлов из S3.
Тестирует функцию copy_from_s3_to_disk из custom_transfer.py
"""

import os
import sys
from pathlib import Path

# Bootstrap environment
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Добавляем путь к custom_transfer
sys.path.insert(0, str(PROJECT_ROOT / "ftrack_plugins" / "mroya_transfer_manager-0.1.0" / "hook" / "lib"))

from run_browser import _bootstrap_environment
_bootstrap_environment(PROJECT_ROOT)

import boto3
from botocore.config import Config
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Импортируем функцию для тестирования
from custom_transfer import copy_from_s3_to_disk


def test_s3_download():
    """Тест скачивания файла из S3."""
    logger.info("=" * 80)
    logger.info("ТЕСТ: Скачивание файла из S3")
    logger.info("=" * 80)
    
    # Получаем параметры из переменных окружения
    s3_bucket = os.getenv('S3_BUCKET', 'proj')
    s3_endpoint = os.getenv('S3_MINIO_ENDPOINT_URL')
    
    logger.info(f"S3 Bucket: {s3_bucket}")
    logger.info(f"S3 Endpoint: {s3_endpoint}")
    
    if not s3_endpoint:
        logger.error("S3_MINIO_ENDPOINT_URL не установлен")
        return
    
    # Создаём S3 клиент
    s3_client = boto3.client(
        's3',
        endpoint_url=s3_endpoint,
        config=Config(signature_version='s3v4'),
        use_ssl=True,
        verify=True,
    )
    
    # Тест 1: Получение списка файлов из S3 по префиксу
    logger.info("\n" + "=" * 80)
    logger.info("ТЕСТ 1: Получение списка файлов из S3")
    logger.info("=" * 80)
    
    # Используем префикс из лога (из реального трансфера)
    prefix = "lunapark/whores/sh0010/heavy_seq/v018/geo_seq."
    logger.info(f"Поиск файлов с префиксом: {prefix}")
    
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=s3_bucket, Prefix=prefix)
        
        sequence_files = []
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    # Извлекаем номер кадра
                    import re
                    frame_match = re.search(r'\.(\d+)\.', key)
                    if frame_match:
                        frame_num = int(frame_match.group(1))
                        sequence_files.append((key, frame_num))
        
        sequence_files.sort(key=lambda x: x[1])
        
        logger.info(f"Найдено файлов: {len(sequence_files)}")
        if sequence_files:
            logger.info(f"Первый файл: {sequence_files[0][0]} (frame: {sequence_files[0][1]})")
            logger.info(f"Последний файл: {sequence_files[-1][0]} (frame: {sequence_files[-1][1]})")
            
            # Тест 2: Скачивание одного файла
            logger.info("\n" + "=" * 80)
            logger.info("ТЕСТ 2: Скачивание одного файла из S3")
            logger.info("=" * 80)
            
            test_key = sequence_files[0][0]
            test_target = os.path.join(os.path.expanduser('~'), 'Downloads', f'test_download_{os.path.basename(test_key)}')
            
            logger.info(f"Скачивание: {test_key} -> {test_target}")
            
            # Создаём директорию, если нужно
            os.makedirs(os.path.dirname(test_target), exist_ok=True)
            
            # Тестируем функцию copy_from_s3_to_disk
            def progress_callback(bytes_transferred, total_size):
                percent = (bytes_transferred / total_size * 100) if total_size > 0 else 0
                logger.info(f"Прогресс: {bytes_transferred}/{total_size} bytes ({percent:.1f}%)")
            
            success, bytes_copied = copy_from_s3_to_disk(
                bucket=s3_bucket,
                key=test_key,
                target_path=test_target,
                endpoint_url=s3_endpoint,
                s3_client=s3_client,
                job_data=None,
                progress_callback=progress_callback,
                session=None
            )
            
            if success:
                logger.info(f"✓ Файл успешно скачан: {bytes_copied} bytes")
                logger.info(f"Путь: {test_target}")
                
                # Проверяем размер файла
                if os.path.exists(test_target):
                    file_size = os.path.getsize(test_target)
                    logger.info(f"Размер файла на диске: {file_size} bytes")
                    if file_size == bytes_copied:
                        logger.info("✓ Размеры совпадают")
                    else:
                        logger.warning(f"⚠ Размеры не совпадают: {file_size} != {bytes_copied}")
            else:
                logger.error("✗ Ошибка скачивания файла")
            
            # Тест 3: Скачивание последовательности с прогрессом
            logger.info("\n" + "=" * 80)
            logger.info("ТЕСТ 3: Скачивание последовательности с прогрессом")
            logger.info("=" * 80)
            
            # Берём первые 5 файлов для теста
            test_sequence = sequence_files[:5]
            logger.info(f"Тестируем последовательность из {len(test_sequence)} файлов")
            
            # Получаем общий размер
            total_size = 0
            for key, frame_num in test_sequence:
                try:
                    response = s3_client.head_object(Bucket=s3_bucket, Key=key)
                    file_size = response.get('ContentLength', 0)
                    total_size += file_size
                    logger.info(f"  {key}: {file_size} bytes")
                except Exception as e:
                    logger.warning(f"  Не удалось получить размер {key}: {e}")
            
            logger.info(f"Общий размер последовательности: {total_size} bytes ({total_size / (1024*1024):.2f} MB)")
            
            # Скачиваем последовательность
            total_bytes = 0
            import threading
            bytes_lock = threading.Lock()
            
            def sequence_progress_callback(bytes_transferred, total_size):
                nonlocal total_bytes
                with bytes_lock:
                    total_bytes += bytes_transferred
                    percent = (total_bytes / total_size * 100) if total_size > 0 else 0
                    logger.info(f"Общий прогресс: {total_bytes}/{total_size} bytes ({percent:.1f}%)")
            
            # Имитируем скачивание последовательности
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            def download_file(key, target_dir):
                target = os.path.join(target_dir, os.path.basename(key))
                success, bytes_copied = copy_from_s3_to_disk(
                    bucket=s3_bucket,
                    key=key,
                    target_path=target,
                    endpoint_url=s3_endpoint,
                    s3_client=s3_client,
                    job_data=None,
                    progress_callback=None,  # Не используем callback для отдельных файлов
                    session=None
                )
                if success:
                    sequence_progress_callback(bytes_copied, total_size)
                return success, bytes_copied
            
            test_dir = os.path.join(os.path.expanduser('~'), 'Downloads', 'test_sequence')
            os.makedirs(test_dir, exist_ok=True)
            
            logger.info(f"Скачивание в: {test_dir}")
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {executor.submit(download_file, key, test_dir): key for key, _ in test_sequence}
                for future in as_completed(futures):
                    key = futures[future]
                    try:
                        success, bytes_copied = future.result()
                        if success:
                            logger.info(f"✓ {os.path.basename(key)}: {bytes_copied} bytes")
                        else:
                            logger.error(f"✗ {os.path.basename(key)}: ошибка")
                    except Exception as e:
                        logger.error(f"✗ {os.path.basename(key)}: исключение - {e}")
            
            logger.info(f"\nИтоговый прогресс: {total_bytes}/{total_size} bytes ({(total_bytes / total_size * 100) if total_size > 0 else 0:.1f}%)")
        else:
            logger.warning("Файлы не найдены в S3")
    
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)


if __name__ == '__main__':
    test_s3_download()
