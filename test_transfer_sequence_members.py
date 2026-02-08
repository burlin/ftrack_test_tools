"""
Test transfer of a sequence component and verify availability at target (members registered).

Usage:
  python test_transfer_sequence_members.py [component_id] [target_location_name]

Default: component_id = dbf2f337-7e71-42ad-a4e3-867ca602c658 (maya_part sequence),
          target = burlin.backup (so we transfer burlin.local -> burlin.backup on same machine)
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from run_browser import _bootstrap_environment, _load_dotenv_if_available
_bootstrap_environment(PROJECT_ROOT)
_load_dotenv_if_available(PROJECT_ROOT / "config" / ".env")

# Locations (same as test_component_path_sequence)
_multi_site = PROJECT_ROOT / "ftrack_plugins" / "multi-site-location-0.2.0"
_hook_locations = _multi_site / "hook" / "locations"
if _hook_locations.is_dir() and str(_hook_locations) not in sys.path:
    sys.path.insert(0, str(_hook_locations))
try:
    import s3_location_plugin
    import user_location_plugin
    if _multi_site.joinpath(".env").is_file():
        try:
            from dotenv import load_dotenv
            load_dotenv(_multi_site / ".env")
        except Exception:
            pass
except ImportError as e:
    print(f"[FAIL] Locations: {e}")
    sys.exit(1)

# mroya_transfer_manager for transfer_component_custom
_lib = PROJECT_ROOT / "ftrack_plugins" / "mroya_transfer_manager" / "hook" / "lib"
if _lib.is_dir() and str(_lib) not in sys.path:
    sys.path.insert(0, str(_lib))

import ftrack_api

DEFAULT_COMPONENT_ID = "dbf2f337-7e71-42ad-a4e3-867ca602c658"
DEFAULT_TARGET = "burlin.backup"


def main():
    component_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_COMPONENT_ID
    target_location_name = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_TARGET

    session = ftrack_api.Session()
    s3_location_plugin.session_add_s3_location(session)
    location_setup = user_location_plugin.load_location_config(
        config_path=_hook_locations / "disk_locations.yaml",
        user_name=session.api_user,
    )
    user_location_plugin.session_add_user_location(session, location_setup)

    component = session.get("Component", component_id)
    if not component:
        print(f"[FAIL] Component {component_id} not found")
        return 1
    print(f"Component: {component.get('name')} (id={component_id}), entity_type={component.entity_type}")

    # Source: location where component has 100%
    source_location = None
    for loc in session.query("Location").all():
        try:
            if loc.get_component_availability(component) >= 100.0:
                acc = getattr(loc, "accessor", None)
                if acc and hasattr(acc, "get_filesystem_path") and "Symbol" not in type(acc).__name__:
                    source_location = loc
                    break
        except Exception:
            continue
    if not source_location:
        print("[FAIL] No source location with 100% and real accessor")
        return 1
    print(f"Source: {source_location['name']}")

    target_location = session.query(f'Location where name is "{target_location_name}"').first()
    if not target_location:
        print(f"[FAIL] Target location {target_location_name!r} not found")
        return 1
    acc = getattr(target_location, "accessor", None)
    if not acc or "Symbol" in type(acc).__name__ or not hasattr(acc, "get_filesystem_path"):
        print(f"[FAIL] Target {target_location_name} has no real accessor")
        return 1
    print(f"Target: {target_location_name}")

    try:
        from custom_transfer import transfer_component_custom
    except ImportError as e:
        print(f"[FAIL] import transfer_component_custom: {e}")
        return 1

    print("\n--- Transfer ---")
    ok = transfer_component_custom(
        session=session,
        component=component,
        source_location=source_location,
        target_location=target_location,
        job_data={},
        progress_callback=lambda b, t: print(f"  Progress: {b}/{t}") if t else None,
    )
    if not ok:
        print("[FAIL] transfer_component_custom returned False")
        return 1
    print("[OK] Transfer done")

    # Refresh and check availability at target
    session.commit()
    component = session.get("Component", component_id)
    avail = target_location.get_component_availability(component)
    print(f"\n--- After transfer: availability at {target_location_name} = {avail}%")
    if avail >= 100.0:
        print("[OK] Availability 100% - members registration works")
    else:
        print(f"[WARN] Expected 100%, got {avail}%")
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
