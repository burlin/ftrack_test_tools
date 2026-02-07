"""Проверить в каких локациях компонент доступен и какие имеют accessor."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from run_browser import _bootstrap_environment
_bootstrap_environment(PROJECT_ROOT)

import ftrack_api
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

component_id = "8d026c21-5bc3-491b-980b-e77e76bd547a"

session = ftrack_api.Session()
component = session.get('Component', component_id)

logger.info(f"Компонент: {component['name']} (ID: {component_id})")
logger.info(f"Размер: {component.get('size', 'N/A')} bytes")
logger.info("")

locations = session.query('Location').all()
logger.info("Доступность компонента по локациям:")
logger.info("-" * 80)

for loc in locations:
    try:
        availability = loc.get_component_availability(component)
        if availability > 0:
            accessor_type = type(loc.accessor).__name__ if loc.accessor else "None"
            has_structure = hasattr(loc, 'structure') and loc.structure is not None
            
            logger.info(f"{loc['name']}: {availability}%")
            logger.info(f"  - Accessor: {accessor_type}")
            logger.info(f"  - Structure: {has_structure}")
            
            # Пробуем получить путь
            if loc.accessor:
                try:
                    if isinstance(loc.accessor, ftrack_api.accessor.disk.DiskAccessor):
                        path = loc.get_filesystem_path(component)
                        exists = os.path.exists(path) if path else False
                        logger.info(f"  - Path: {path}")
                        logger.info(f"  - File exists: {exists}")
                        if exists:
                            size = os.path.getsize(path)
                            logger.info(f"  - File size: {size} bytes")
                    elif 's3' in str(type(loc.accessor)).lower():
                        try:
                            url = loc.get_url(component)
                            logger.info(f"  - URL: {url[:80]}..." if len(str(url)) > 80 else f"  - URL: {url}")
                        except:
                            logger.info(f"  - URL: (не удалось получить)")
                except Exception as e:
                    logger.info(f"  - Path/URL: ошибка - {e}")
            
            logger.info("")
    except Exception:
        pass

session.close()
