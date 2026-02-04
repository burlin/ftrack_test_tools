"""
Тестовый скрипт для проверки ручного трансфера компонентов.

Проверяет:
1. Получение resource_identifier для source и target location
2. Получение реальных путей/URL через accessors
3. Копирование файла вручную (пока без прогресса)
4. Регистрация компонента в target location
"""

import os
import sys
from pathlib import Path

# Bootstrap environment (как в run_browser.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from run_browser import _bootstrap_environment

# Загружаем переменные окружения
_bootstrap_environment(PROJECT_ROOT)

import ftrack_api
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_resource_identifier():
    """Тест получения resource_identifier и путей."""
    session = ftrack_api.Session()
    
    try:
        # Получаем локации
        logger.info("=" * 80)
        logger.info("ТЕСТ: Получение локаций")
        logger.info("=" * 80)
        
        locations = session.query('Location').all()
        logger.info(f"Найдено локаций: {len(locations)}")
        for loc in locations[:5]:  # Показываем первые 5
            logger.info(f"  - {loc['name']}: {loc.get('label', 'N/A')} (accessor: {type(loc.accessor).__name__ if loc.accessor else 'None'})")
        
        # Попробуем найти конкретную локацию (например, s3.minio или disk локацию)
        s3_location = None
        disk_location = None
        
        for loc in locations:
            if 's3' in loc['name'].lower() or 'minio' in loc['name'].lower():
                s3_location = loc
                logger.info(f"\nНайдена S3 локация: {loc['name']}")
            if 'disk' in loc['name'].lower() or 'local' in loc['name'].lower():
                if not disk_location:  # Берём первую
                    disk_location = loc
                    logger.info(f"\nНайдена Disk локация: {loc['name']}")
        
        if not s3_location and not disk_location:
            logger.warning("Не найдено S3 или Disk локаций для теста")
            return
        
        # Получаем компонент для теста (берем первый доступный)
        logger.info("\n" + "=" * 80)
        logger.info("ТЕСТ: Получение компонентов")
        logger.info("=" * 80)
        
        components = session.query('Component limit 5').all()
        if not components:
            logger.warning("Компоненты не найдены")
            return
        
        component = components[0]
        logger.info(f"Выбран компонент: {component['name']} (ID: {component['id']})")
        logger.info(f"  Размер: {component.get('size', 'N/A')} bytes")
        logger.info(f"  Тип: {component.entity_type}")
        
        # Проверяем, в каких локациях компонент доступен
        logger.info("\nДоступность компонента по локациям:")
        for loc in locations[:10]:  # Первые 10 локаций
            try:
                availability = loc.get_component_availability(component)
                if availability > 0:
                    logger.info(f"  - {loc['name']}: {availability}%")
            except Exception as e:
                pass  # Компонент не в этой локации
        
        # Тест 1: Получение resource_identifier из source location
        logger.info("\n" + "=" * 80)
        logger.info("ТЕСТ 1: Получение resource_identifier из source location")
        logger.info("=" * 80)
        
        source_location = None
        for loc in locations:
            try:
                availability = loc.get_component_availability(component)
                if availability == 100.0:  # Компонент полностью доступен
                    source_location = loc
                    break
            except Exception:
                continue
        
        if not source_location:
            logger.warning("Не найдена локация, где компонент доступен на 100%")
            return
        
        logger.info(f"Source location: {source_location['name']}")
        try:
            source_resource_id = source_location.get_resource_identifier(component)
            logger.info(f"Source resource_identifier: {source_resource_id}")
            
            # Получаем реальный путь/URL
            try:
                if isinstance(source_location.accessor, ftrack_api.accessor.disk.DiskAccessor):
                    source_path = source_location.get_filesystem_path(component)
                    logger.info(f"Source filesystem path: {source_path}")
                    logger.info(f"Файл существует: {os.path.exists(source_path) if source_path else False}")
                    if source_path and os.path.exists(source_path):
                        file_size = os.path.getsize(source_path)
                        logger.info(f"Размер файла на диске: {file_size} bytes")
                elif hasattr(source_location.accessor, 'get_url') or hasattr(source_location, 'get_url'):
                    try:
                        source_url = source_location.get_url(component)
                        logger.info(f"Source URL: {source_url[:100]}..." if len(str(source_url)) > 100 else f"Source URL: {source_url}")
                    except AttributeError:
                        # Возможно, нужно получить через accessor
                        if hasattr(source_location.accessor, 'get_url'):
                            source_url = source_location.accessor.get_url(source_resource_id)
                            logger.info(f"Source URL (через accessor): {source_url[:100]}..." if len(str(source_url)) > 100 else f"Source URL: {source_url}")
            except Exception as e:
                logger.warning(f"Не удалось получить путь/URL: {e}")
        except Exception as e:
            logger.error(f"Ошибка получения source resource_identifier: {e}")
            return
        
        # Тест 2: Генерация resource_identifier для target location
        logger.info("\n" + "=" * 80)
        logger.info("ТЕСТ 2: Генерация resource_identifier для target location")
        logger.info("=" * 80)
        
        # Выбираем target location (другая, чем source, с accessor и structure)
        target_location = None
        for loc in locations:
            if loc['id'] != source_location['id']:
                if loc.accessor and hasattr(loc, 'structure') and loc.structure:
                    if isinstance(loc.accessor, ftrack_api.accessor.disk.DiskAccessor):
                        target_location = loc
                        break
                    elif s3_location is None and 's3' in str(type(loc.accessor)).lower():
                        s3_location = loc
        
        # Если не нашли Disk, пробуем S3
        if not target_location and s3_location and s3_location['id'] != source_location['id']:
            if hasattr(s3_location, 'structure') and s3_location.structure:
                target_location = s3_location
        
        if not target_location or target_location['id'] == source_location['id']:
            logger.warning("Не найдена подходящая target location с structure и accessor")
            return
        
        logger.info(f"Target location: {target_location['name']}")
        
        # Генерируем resource_identifier для target location
        try:
            # Проверяем, есть ли structure у локации
            if not hasattr(target_location, 'structure') or not target_location.structure:
                logger.warning(f"Target location {target_location['name']} не имеет structure")
                return
            
            # Нужно получить context (как в location._get_context)
            # Context должен быть словарем с source_resource_identifier
            try:
                source_resource_id_str = source_location.get_resource_identifier(component)
                context = {'source_resource_identifier': source_resource_id_str}
                logger.info(f"Context: {context}")
            except Exception as e:
                logger.warning(f"Не удалось получить source_resource_identifier: {e}")
                context = {}
            
            try:
                target_resource_id = target_location.structure.get_resource_identifier(component, context)
                logger.info(f"Target resource_identifier: {target_resource_id} (type: {type(target_resource_id)})")
            except Exception as e:
                logger.warning(f"Не удалось получить resource_identifier с context: {e}")
                # Пробуем без context (некоторые структуры могут работать без него)
                try:
                    target_resource_id = target_location.structure.get_resource_identifier(component, None)
                    logger.info(f"Target resource_identifier (без context): {target_resource_id}")
                except Exception as e2:
                    logger.error(f"Не удалось получить resource_identifier и без context: {e2}")
                    return
            
            # Проверяем тип - должен быть строка
            if not isinstance(target_resource_id, str):
                logger.warning(f"resource_identifier не является строкой: {target_resource_id}, тип: {type(target_resource_id)}")
                return
            
            # Получаем реальный путь для target (если Disk)
            if isinstance(target_location.accessor, ftrack_api.accessor.disk.DiskAccessor):
                if isinstance(target_resource_id, str):
                    target_path = target_location.accessor.get_filesystem_path(target_resource_id)
                    logger.info(f"Target filesystem path: {target_path}")
                    if target_path:
                        parent_dir = os.path.dirname(target_path)
                        logger.info(f"Директория существует: {os.path.exists(parent_dir)}")
                        if not os.path.exists(parent_dir):
                            logger.info(f"  Создадим директорию при трансфере: {parent_dir}")
                else:
                    logger.warning(f"Не можем получить путь: resource_identifier не строка")
        except Exception as e:
            logger.error(f"Ошибка генерации target resource_identifier: {e}", exc_info=True)
            return
        
        # Тест 3: Попробуем прочитать файл из source
        logger.info("\n" + "=" * 80)
        logger.info("ТЕСТ 3: Чтение файла из source location")
        logger.info("=" * 80)
        
        try:
            if isinstance(source_location.accessor, ftrack_api.accessor.disk.DiskAccessor):
                source_path = source_location.get_filesystem_path(component)
                if os.path.exists(source_path):
                    file_size = os.path.getsize(source_path)
                    logger.info(f"Файл существует: {source_path}")
                    logger.info(f"Размер: {file_size} bytes")
                    
                    # Прочитаем первые байты для проверки
                    with open(source_path, 'rb') as f:
                        first_bytes = f.read(16)
                        logger.info(f"Первые 16 байт: {first_bytes.hex()}")
                else:
                    logger.warning(f"Файл не существует: {source_path}")
            else:
                logger.info("Source location не Disk, пропускаем тест чтения")
        except Exception as e:
            logger.warning(f"Не удалось прочитать файл: {e}")
        
        logger.info("\n" + "=" * 80)
        logger.info("ТЕСТ ЗАВЕРШЁН")
        logger.info("=" * 80)
        logger.info("\nВыводы:")
        logger.info("1. resource_identifier - это логический путь к файлу")
        logger.info("2. Для получения реального пути используется accessor.get_filesystem_path()")
        logger.info("3. Context нужен для генерации resource_identifier в target location")
        logger.info("4. Context содержит source_resource_identifier (строка, не Location!)")
        
    except Exception as e:
        logger.error(f"Общая ошибка: {e}", exc_info=True)
    finally:
        session.close()


if __name__ == '__main__':
    test_resource_identifier()
