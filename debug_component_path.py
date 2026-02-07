"""
Diagnostic script: why does component path come back empty for the client?

Reproduces the same flow as get_component_path() in ftrack_hou_utils:
  session.pick_location() -> location.get_filesystem_path(component)

Use: python debug_component_path.py [component_id]
Default component_id: fe0515b1-f2a3-44dc-a38e-74427b8b5057 (from client log)
"""

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

DEFAULT_COMPONENT_ID = "fe0515b1-f2a3-44dc-a38e-74427b8b5057"


def _accessor_type(loc):
    if not loc.accessor:
        return "None"
    t = type(loc.accessor)
    name = t.__name__
    if "s3" in str(t).lower():
        return f"{name} (S3)"
    if hasattr(ftrack_api.accessor, "disk") and isinstance(loc.accessor, ftrack_api.accessor.disk.DiskAccessor):
        return f"{name} (Disk)"
    return name


def main():
    component_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_COMPONENT_ID
    print("=" * 80)
    print("DEBUG: Why is path empty for component?")
    print("=" * 80)
    print(f"Component ID: {component_id}")
    print()

    session = ftrack_api.Session()

    # 1) Load component
    try:
        component = session.get("Component", component_id)
    except Exception as e:
        print(f"[FATAL] Failed to get component: {e}")
        return 1
    if not component:
        print("[FATAL] Component not found.")
        return 1

    print("--- Component ---")
    print(f"  name: {component.get('name')}")
    print(f"  id: {component['id']}")
    print(f"  file_type: {component.get('file_type')}")
    print(f"  entity_type: {getattr(component, 'entity_type', component.get('entity_type', 'N/A'))}")
    if hasattr(component, "container_type"):
        print(f"  container_type: {getattr(component, 'container_type', 'N/A')}")
    if component.get("version"):
        print(f"  version: {component['version'].get('version')} (id: {component['version']['id']})")
    if component.get("version", {}).get("asset"):
        print(f"  asset: {component['version']['asset'].get('name')} (id: {component['version']['asset']['id']})")
    print()

    # 2) What does pick_location() return? (same as production)
    print("--- session.pick_location() (what production uses) ---")
    try:
        picked = session.pick_location()
        if not picked:
            print("  [ERROR] pick_location() returned None - no location selected.")
        else:
            print(f"  Picked: {picked['name']!r} (id: {picked['id']})")
            print(f"  Accessor: {_accessor_type(picked)}")
            avail = picked.get_component_availability(component)
            print(f"  Availability for this component: {avail}%")
            if avail < 100.0:
                print("  [WARN] Availability < 100% - path may be missing or incomplete.")
            # This is the call that might return None/empty or raise
            try:
                path = picked.get_filesystem_path(component)
                if path is None:
                    print("  get_filesystem_path(component) => None")
                elif not str(path).strip():
                    print("  get_filesystem_path(component) => (empty string)")
                else:
                    print(f"  get_filesystem_path(component) => {path!r}")
                # If no path, show resource_identifier (what location stores)
                if not path or not str(path).strip():
                    try:
                        rid = picked.get_resource_identifier(component)
                        print(f"  get_resource_identifier(component) => {rid!r}")
                    except Exception as e2:
                        print(f"  get_resource_identifier(component) => exception: {e2}")
            except Exception as e:
                print(f"  get_filesystem_path(component) => exception: {e}")
                import traceback
                traceback.print_exc()
                try:
                    rid = picked.get_resource_identifier(component)
                    print(f"  get_resource_identifier(component) => {rid!r}")
                except Exception as e2:
                    print(f"  get_resource_identifier(component) => exception: {e2}")
    except Exception as e:
        print(f"  [ERROR] pick_location() or follow-up failed: {e}")
        import traceback
        traceback.print_exc()
    print()

    # 3) All locations where component exists: which return a path, which don't?
    print("--- All locations with component (availability > 0) ---")
    locations = session.query("Location").all()
    for loc in locations:
        try:
            avail = loc.get_component_availability(component)
            if avail <= 0:
                continue
            acc = _accessor_type(loc)
            path_result = "(not tried)"
            try:
                p = loc.get_filesystem_path(component)
                if p is None:
                    path_result = "None"
                elif not str(p).strip():
                    path_result = "(empty)"
                else:
                    path_result = p[:80] + "..." if len(str(p)) > 80 else p
            except Exception as ex:
                path_result = f"exception: {ex!r}"
            print(f"  {loc['name']!r}: {avail}% | accessor={acc} | path => {path_result}")
        except Exception:
            pass
    print()
    print("=" * 80)
    print("If path is None/empty only for S3 location, client may have no S3 accessor or env.")
    print("If path is None/empty for Disk location, check structure/resource_identifier.")
    print("=" * 80)
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
