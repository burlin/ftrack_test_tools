"""
Тестовый скрипт: по файловому пути определить ftrack Location и Component.

Два шага (как в документации ftrack):
  1. Среди локаций с DiskAccessor найти ту, чей prefix совпадает с началом пути
     → узнаём локацию и отрезаем от пути корень (prefix).
  2. Относительный путь = resource_identifier в структуре локации.
     По нему один запрос: ComponentLocation where location_id and resource_identifier
     → получаем component_id и компонент.

Использование:
  python tools/test_path_to_location_component.py "x:/proj/lunapark/whores/sh0010/test/v003/test.fbx"
  python tools/test_path_to_location_component.py  # интерактивный ввод
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Project root and tools path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from run_browser import _bootstrap_environment
    _bootstrap_environment(PROJECT_ROOT)
except ImportError:
    plugins_root = PROJECT_ROOT / "ftrack_plugins"
    if plugins_root.is_dir() and str(plugins_root) not in sys.path:
        sys.path.insert(0, str(plugins_root))

import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)
# Убрать шум от кэша сессии (OUR_CACHE CHECK и т.д.)
logging.getLogger("ftrack_inout.common.cache_wrapper").setLevel(logging.WARNING)


def _normalize_path(p: str) -> str:
    """Абсолютный путь, нормализованный, слэши /."""
    p = os.path.expandvars(os.path.expanduser(p))
    p = os.path.normpath(os.path.abspath(p))
    return p.replace("\\", "/").rstrip("/")


def find_location_and_component_for_path(session, file_path: str):
    """
    По файловому пути найти Location и Component.

    Префиксы локаций не пересекаются (x:/proj/, z:/proj/, x:/proja/ и т.д.),
    поэтому путь может относиться только к одной локации.
    1) Найти локацию, чей prefix — начало пути.
    2) Отрезать этот корень → resource_identifier.
    3) Запрос ComponentLocation по location_id и resource_identifier → component.

    Returns:
        (location, component) или (None, None).
    """
    import ftrack_api

    path_norm = _normalize_path(file_path)
    locations = session.query("Location").all()
    disk_locations = [
        loc for loc in locations
        if getattr(loc, "accessor", None) is not None
        and isinstance(loc.accessor, ftrack_api.accessor.disk.DiskAccessor)
    ]

    # Найти локацию, чей prefix совпадает с началом пути (префиксы не пересекаются).
    for loc in disk_locations:
        try:
            prefix_raw = getattr(loc.accessor, "prefix", "") or ""
            if not prefix_raw:
                continue
            loc_prefix = _normalize_path(prefix_raw)
            if not path_norm.startswith(loc_prefix):
                continue
        except Exception:
            continue

        remainder = path_norm[len(loc_prefix):].lstrip("/")
        if not remainder:
            continue
        resource_identifier = remainder.replace("\\", "/")

        for res_id in (resource_identifier, resource_identifier.lower()):
            try:
                res_id_safe = res_id.replace('"', '\\"')
                query = (
                    'ComponentLocation where location_id is "{loc_id}" and resource_identifier is "{res_id}"'
                ).format(loc_id=loc["id"], res_id=res_id_safe)
                comp_locs = session.query(query).all()
            except Exception:
                comp_locs = []
            if comp_locs:
                cl = comp_locs[0]
                component = session.get("Component", cl["component_id"])
                return (loc, component)

    return (None, None)


def main():
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = input("Введите путь к файлу (например x:/proj/lunapark/.../test.fbx): ").strip()
        if not file_path:
            logger.error("Путь не задан.")
            sys.exit(1)

    try:
        from ftrack_inout.common.session_factory import create_shared_session
    except ImportError:
        from ftrack_plugins.ftrack_inout.common.session_factory import create_shared_session

    logger.info("Создаём сессию ftrack (с подгрузкой локаций)...")
    session = create_shared_session(enable_locations=True)
    if not session:
        logger.error("Не удалось создать сессию. Проверьте FTRACK_SERVER, FTRACK_API_USER, FTRACK_API_KEY.")
        sys.exit(1)

    logger.info("Ищем локацию и компонент для пути: %s", file_path)
    location, component = find_location_and_component_for_path(session, file_path)

    if location is None or component is None:
        logger.info("Не найдено: ни одна локация с DiskAccessor не содержит компонент с таким путём.")
        session.close()
        sys.exit(0)

    logger.info("")
    logger.info("--- Результат ---")
    logger.info("Location:  %s (id=%s)", location["name"], location["id"])
    logger.info("Component: %s (id=%s)", component.get("name"), component["id"])
    try:
        ver = component.get("version")
        if ver:
            logger.info("Version:   v%s (id=%s)", ver.get("version"), ver.get("id"))
            asset = ver.get("asset")
            if asset:
                logger.info("Asset:     %s (id=%s)", asset.get("name"), asset.get("id"))
    except Exception as e:
        logger.info("(version/asset: %s)", e)
    logger.info("-------------")
    session.close()


if __name__ == "__main__":
    main()
