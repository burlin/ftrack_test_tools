"""Проверить в каких локациях компонент доступен и какие имеют accessor.

Usage:
  python test_check_component_locations.py [component_id]
  Default component_id: fe0515b1-f2a3-44dc-a38e-74427b8b5057 (from client path issue)

  Runs location init (user + S3) like Connect so accessors are set.
  Shows:
  1) BROWSER MECHANISM: component_locations (из него выбираем)
  2) Path из доступной локации с мин. приоритетом (для клиента)
"""

import os
import socket
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

DEFAULT_COMPONENT_ID = "fe0515b1-f2a3-44dc-a38e-74427b8b5057"
component_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_COMPONENT_ID

session = ftrack_api.Session()

# Initialize locations (user disk + S3) like Connect does, so accessors are set
_loc_path = PROJECT_ROOT / "ftrack_plugins" / "multi-site-location-0.2.0" / "hook" / "locations"
if _loc_path.is_dir() and str(_loc_path) not in sys.path:
    sys.path.insert(0, str(_loc_path))
try:
    hostname = socket.gethostname().lower()
except Exception:
    hostname = os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "unknown")).lower()
_fake_event = {"data": {"session": session}, "source": {"hostname": hostname}}
try:
    import user_location_plugin  # noqa: E402
    user_location_plugin.configure_locations(_fake_event)
    logger.info("[OK] User locations configured (disk_locations.yaml)")
except Exception as e:
    logger.warning("User location init failed: %s", e)
try:
    import s3_location_plugin  # noqa: E402
    s3_location_plugin.configure_s3_location(_fake_event)
    logger.info("[OK] S3 location configured (if env set)")
except Exception as e:
    logger.warning("S3 location init failed: %s", e)

# BROWSER MECHANISM: query с component_locations в projection (как browser_widget_optimized)
try:
    components_query = (
        f'select id, name, file_type, component_locations.location.name, '
        f'component_locations.location.label from Component where id is "{component_id}"'
    )
    comps_from_query = session.query(components_query).all()
    if comps_from_query:
        component = comps_from_query[0]
        session.populate([component], 'component_locations')
        logger.info("[OK] Component loaded via BROWSER mechanism (query + populate)")
    else:
        component = session.get('Component', component_id)
        if component:
            session.populate([component], 'component_locations')
        logger.warning("Query returned empty, using session.get")
except Exception as e:
    logger.warning("Browser-style query failed: %s, falling back to session.get", e)
    component = session.get('Component', component_id)
    if component:
        session.populate([component], 'component_locations')

if not component:
    logger.error("Component not found: %s", component_id)
    sys.exit(1)

logger.info("Component: %s (ID: %s)", component['name'], component_id)
logger.info("  entity_type: %s  file_type: %s", getattr(component, 'entity_type', component.get('entity_type', 'N/A')), component.get('file_type'))
logger.info("  size: %s bytes", component.get('size', 'N/A'))
logger.info("")

# 1) BROWSER: список локаций из component_locations (как в "Available at") — отсюда выбираем
comp_loc_entities = []
browser_location_names = []
for comp_loc in component.get('component_locations', []):
    loc_entity = comp_loc.get('location')
    if loc_entity:
        name = loc_entity.get('label') or loc_entity.get('name') or ''
        browser_location_names.append(name)
        comp_loc_entities.append(loc_entity)
logger.info("=" * 80)
logger.info("1) BROWSER MECHANISM (component_locations) - из него выбираем:")
logger.info("   Locations: %s", sorted(set(browser_location_names)) if browser_location_names else "(empty)")
logger.info("=" * 80)
logger.info("")

# Path из доступной локации с мин. приоритетом — берём только из списка component_locations
candidates = []
for loc in comp_loc_entities:
    if getattr(loc, 'accessor', None):
        priority = getattr(loc, 'priority', 999) or 999
        candidates.append((priority, loc))
if candidates:
    candidates.sort(key=lambda x: x[0])
    min_priority_loc = candidates[0][1]
    try:
        path_from_loc = min_priority_loc.get_filesystem_path(component)
        logger.info("2) PATH (мин. приоритет из component_locations, для клиента):")
        logger.info("   Location: %s (priority=%s)", min_priority_loc['name'], getattr(min_priority_loc, 'priority', '?'))
        logger.info("   Path: %s", path_from_loc or "(None)")
    except Exception as e:
        logger.warning("   Path error: %s", e)
else:
    logger.info("2) PATH: среди component_locations нет локации с accessor")

session.close()
