"""
Test script: location selection and component path resolution.

Uses the same connection/location setup as run_browser.py, then compares:
- session.pick_location() (what get_data uses)
- get_primary_disk_location(session) (what resolve_component_path uses when location=None)
- resolve_component_path(session, component) vs resolve_component_path(session, component, location=...)

Run from repo root or tools/:
  python tools/test_location_path_resolution.py [component_id]
  or set env COMPONENT_ID=...

Example:
  set COMPONENT_ID=2b7c8161-4887-4a14-9112-5f793228af6f
  python tools/test_location_path_resolution.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Same bootstrap as run_browser
_tools_dir = Path(__file__).resolve().parent
_project_root = _tools_dir.parent if _tools_dir.name == "tools" else _tools_dir
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from run_browser import _bootstrap_environment  # type: ignore

_bootstrap_environment(_project_root)


def main() -> None:
    component_id = os.environ.get("COMPONENT_ID") or (sys.argv[1] if len(sys.argv) > 1 else None)

    print("=" * 60)
    print("Location & path resolution test (same setup as run_browser)")
    print("=" * 60)

    # Session (shared, same as browser/input)
    try:
        from ftrack_inout.common.session_factory import get_shared_session
        session = get_shared_session()
    except Exception as e:
        print("ERROR: Could not get session:", e)
        sys.exit(1)
    if not session:
        print("ERROR: Session is None. Check FTRACK_* env / config.")
        sys.exit(1)
    print("\n[OK] Session created")

    # 0) Rule from disk_locations.yaml
    print("\n--- Rule (disk_locations.yaml): smaller priority = primary ---")
    print("  burlin.local=1, burlin.backup=10 => primary should be burlin.local")
    print("  get_primary_disk_location sorts by priority ascending and takes first.")

    # 1) All locations (name, priority, is Disk)
    print("\n--- All locations ---")
    try:
        import ftrack_api
        locations = session.query("Location").all()
        for loc in sorted(locations, key=lambda l: (getattr(l, "priority", 999), (l.get("name") or ""))):
            name = loc.get("name") or "?"
            prio = getattr(loc, "priority", "?")
            acc = getattr(loc, "accessor", None)
            is_disk = "Disk" if (acc and hasattr(ftrack_api.accessor, "disk") and isinstance(acc, ftrack_api.accessor.disk.DiskAccessor)) else "other"
            print("  %s  priority=%s  %s" % (name, prio, is_disk))
    except Exception as e:
        print("  Failed:", e)

    # 2) pick_location (what get_data uses)
    print("\n--- session.pick_location() (used in get_data) ---")
    try:
        picked = session.pick_location()
        if picked:
            print("  name: %s  id: %s  priority: %s" % (
                picked.get("name"), picked.get("id"), getattr(picked, "priority", "?")
            ))
        else:
            print("  None")
    except Exception as e:
        print("  ERROR:", e)

    # 3) get_primary_disk_location (what resolve_component_path uses when location=None)
    print("\n--- get_primary_disk_location(session) (used in resolve_component_path when location=None) ---")
    try:
        import ftrack_api as _ft
        from ftrack_inout.input.core.path_resolution import (
            get_primary_disk_location,
            BUILTIN_LOCATION_NAMES,
        )
        locations = session.query("Location").all()
        disk_locations = []
        for loc in locations:
            name = loc.get("name") or ""
            if name in BUILTIN_LOCATION_NAMES:
                continue
            acc = getattr(loc, "accessor", None)
            if not acc or not (hasattr(_ft.accessor, "disk") and isinstance(acc, _ft.accessor.disk.DiskAccessor)):
                continue
            disk_locations.append(loc)
        disk_locations.sort(key=lambda l: getattr(l, "priority", 999))
        print("  Disk locations (sorted by priority, first = primary):")
        for loc in disk_locations:
            print("    priority=%s  name=%s" % (getattr(loc, "priority", "?"), loc.get("name")))
        primary = get_primary_disk_location(session)
        if primary:
            print("  => primary: %s  (priority: %s)" % (
                primary.get("name"), getattr(primary, "priority", "?")
            ))
        else:
            print("  => None (no user Disk location)")
    except Exception as e:
        print("  ERROR:", e)

    if not component_id:
        print("\n--- No component_id given ---")
        print("  Set COMPONENT_ID=... or pass as first argument to test path resolution.")
        print("  Example: COMPONENT_ID=2b7c8161-4887-4a14-9112-5f793228af6f")
        return

    # 4) Fetch component
    print("\n--- Component: %s ---" % component_id)
    try:
        component = session.get("Component", component_id)
        print("  name: %s  version: %s" % (component.get("name"), component.get("version", {}).get("version")))
    except Exception as e:
        print("  ERROR fetching component:", e)
        return

    # 5) Path with pick_location (same as get_data)
    print("\n--- Path: resolve_component_path(session, component, location=pick_location()) ---")
    try:
        from ftrack_inout.input.core.path_resolution import resolve_component_path
        picked = session.pick_location()
        if picked:
            path = resolve_component_path(session, component, location=picked)
            print("  OK: %s" % path)
        else:
            print("  SKIP: pick_location() returned None")
    except Exception as e:
        print("  ERROR: %s" % e)

    # 6) Path without location (primary Disk only - same as create_node before fix)
    print("\n--- Path: resolve_component_path(session, component) [no location, primary Disk only] ---")
    try:
        from ftrack_inout.input.core.path_resolution import resolve_component_path
        path = resolve_component_path(session, component)
        print("  OK: %s" % path)
    except Exception as e:
        print("  ERROR: %s" % e)

    # 7) Compare
    print("\n--- Summary ---")
    try:
        picked = session.pick_location()
        primary = get_primary_disk_location(session)
        same = (picked and primary and picked.get("id") == primary.get("id"))
        print("  pick_location == get_primary_disk_location: %s" % same)
        if not same and picked and primary:
            print("  -> get_data uses pick_location; create_node (without location) uses primary only.")
            print("  -> If they differ, path on node (get_data) can be set, but create_node may fail.")
    except Exception as e:
        print("  Summary error:", e)
    print("=" * 60)


if __name__ == "__main__":
    main()
