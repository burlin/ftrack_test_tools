"""
Diagnostic script: component path resolution for sequences vs single files.

Tests all path-resolution hypotheses with pre-loaded locations and credentials
(as in run_browser.py). Also tests browser's get_components_with_paths flow.

Usage:
  python test_component_path_sequence.py [component_id]

Default component_id: dbf2f337-7e71-42ad-a4e3-867ca602c658
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Same bootstrap as run_browser.py
if sys.version_info >= (3, 12) and 'imp' not in sys.modules:
    import types
    class ImpModule:
        @staticmethod
        def find_module(name, path=None):
            return None
        @staticmethod
        def load_module(name, file=None, pathname=None, description=None):
            raise ImportError("imp.load_module not supported")
        @staticmethod
        def new_module(name):
            return types.ModuleType(name)
        @staticmethod
        def get_suffixes():
            return []
        @staticmethod
        def acquire_lock():
            pass
        @staticmethod
        def release_lock():
            pass
    sys.modules['imp'] = ImpModule  # type: ignore

if sys.version_info >= (3, 12) and 'distutils' not in sys.modules:
    import re
    import types
    class LooseVersion:
        def __init__(self, v: str):
            self.v = str(v)
            parts = re.findall(r'\d+|[a-zA-Z]+', self.v)
            self.version = [int(x) if x.isdigit() else x for x in parts]
        def __gt__(self, other):
            if not isinstance(other, LooseVersion):
                other = LooseVersion(str(other))
            return self.version > other.version
        def __lt__(self, other):
            if not isinstance(other, LooseVersion):
                other = LooseVersion(str(other))
            return self.version < other.version
        def __eq__(self, other):
            if not isinstance(other, LooseVersion):
                other = LooseVersion(str(other))
            return self.version == other.version
    distutils_version = types.ModuleType('distutils.version')
    distutils_version.LooseVersion = LooseVersion  # type: ignore
    distutils = types.ModuleType('distutils')
    distutils.version = distutils_version  # type: ignore
    sys.modules['distutils'] = distutils  # type: ignore
    sys.modules['distutils.version'] = distutils_version  # type: ignore

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
sys.path.insert(0, str(_project_root))

# Bootstrap environment (locations, creds, plugin paths) - same as run_browser
from run_browser import _bootstrap_environment, _load_dotenv_if_available

_bootstrap_environment(_project_root)
_load_dotenv_if_available(_project_root / "config" / ".env")

import ftrack_api

DEFAULT_COMPONENT_ID = "dbf2f337-7e71-42ad-a4e3-867ca602c658"


def _accessor_type(loc) -> str:
    if not loc.accessor:
        return "None"
    t = type(loc.accessor)
    name = t.__name__
    if "s3" in str(t).lower():
        return f"{name} (S3)"
    try:
        if hasattr(ftrack_api.accessor, "disk") and isinstance(loc.accessor, ftrack_api.accessor.disk.DiskAccessor):
            return f"{name} (Disk)"
    except Exception:
        pass
    return name


def _section(title: str) -> None:
    print()
    print("=" * 80)
    print(f"  {title}")
    print("=" * 80)


def _result(ok: bool, msg: str, detail: str = "") -> None:
    prefix = "[OK]" if ok else "[FAIL]"
    print(f"  {prefix} {msg}")
    if detail:
        for line in detail.strip().split("\n"):
            print(f"       {line}")


def main() -> int:
    component_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_COMPONENT_ID

    print()
    print("=" * 80)
    print("  COMPONENT PATH RESOLUTION DIAGNOSTIC (sequences vs single files)")
    print("=" * 80)
    print(f"  Component ID: {component_id}")
    print(f"  Project root: {_project_root}")
    print()

    # Session with event hub so location plugins register
    try:
        session = ftrack_api.Session(auto_connect_event_hub=True)
    except Exception as e:
        print(f"[FATAL] Failed to create session: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Load component
    try:
        component = session.get("Component", component_id)
    except Exception as e:
        print(f"[FATAL] Failed to get component: {e}")
        return 1
    if not component:
        print("[FATAL] Component not found.")
        return 1

    comp_name = component.get("name", "?")
    comp_file_type = component.get("file_type", "?")
    print("--- Component ---")
    print(f"  name: {comp_name}")
    print(f"  file_type: {comp_file_type}")
    print(f"  id: {component['id']}")
    if component.get("version"):
        v = component["version"]
        print(f"  version: {v.get('version')} (id: {v['id']})")
        if v.get("asset"):
            print(f"  asset: {v['asset'].get('name')} (id: {v['asset']['id']})")
    print()

    # --- Hypothesis A: finput-style (pick_location + get_filesystem_path, no populate) ---
    _section("A) Finput-style: pick_location + get_filesystem_path (no populate)")

    try:
        loc = session.pick_location()
        if not loc:
            _result(False, "pick_location() returned None")
        else:
            print(f"  Picked location: {loc['name']!r} (id: {loc['id']})")
            print(f"  Accessor: {_accessor_type(loc)}")
            avail = loc.get_component_availability(component)
            print(f"  Availability: {avail}%")
            try:
                path = loc.get_filesystem_path(component)
                if path is None:
                    _result(False, "get_filesystem_path => None")
                elif not str(path).strip():
                    _result(False, "get_filesystem_path => (empty string)")
                else:
                    _result(True, f"path = {path[:100]}{'...' if len(str(path)) > 100 else ''}")
                # resource_identifier
                try:
                    rid = loc.get_resource_identifier(component)
                    print(f"  resource_identifier: {rid!r}")
                except Exception as e2:
                    print(f"  resource_identifier: exception {e2}")
            except Exception as e:
                _result(False, f"get_filesystem_path => exception: {e}")
                import traceback
                traceback.print_exc()
    except Exception as e:
        _result(False, f"Finput-style flow failed: {e}")
        import traceback
        traceback.print_exc()

    # --- Hypothesis B: With populate(component_locations) first ---
    _section("B) With session.populate(component, 'component_locations') first")

    try:
        session.populate([component], "component_locations")
        print("  populate(component, 'component_locations') done.")
        comp_locs = component.get("component_locations") or []
        print(f"  component_locations count: {len(comp_locs)}")
        for cl in comp_locs[:5]:
            loc_ent = cl.get("location")
            loc_name = loc_ent.get("name", "?") if loc_ent else "?"
            rid = cl.get("resource_identifier", "?")
            print(f"    - location={loc_name!r}, resource_identifier={rid[:80]!r}{'...' if len(str(rid)) > 80 else ''}")
        if len(comp_locs) > 5:
            print(f"    ... and {len(comp_locs) - 5} more")

        loc = session.pick_location()
        if loc:
            try:
                path = loc.get_filesystem_path(component)
                if path is None or not str(path).strip():
                    _result(False, f"get_filesystem_path after populate => {path!r}")
                else:
                    _result(True, f"path = {path[:100]}{'...' if len(str(path)) > 100 else ''}")
            except Exception as e:
                _result(False, f"get_filesystem_path after populate => exception: {e}")
    except Exception as e:
        _result(False, f"Populate flow failed: {e}")
        import traceback
        traceback.print_exc()

    # --- Hypothesis C: Browser-style (get_components_with_paths logic) ---
    _section("C) Browser-style: get_components_with_paths flow")

    try:
        version_id = component.get("version", {}).get("id")
        if not version_id:
            _result(False, "No version_id on component")
        else:
            # Replicate browser: query components, populate component_locations, pick_location, get_filesystem_path
            comps = session.query(
                'select id, name, file_type, component_locations.location.name, '
                'component_locations.location.label from Component where '
                f'version.id is "{version_id}"'
            ).all()
            comp_ids = [c["id"] for c in comps]
            comp_entities = [session.get("Component", cid) for cid in comp_ids]
            session.populate(comp_entities, "component_locations")

            location = session.pick_location()
            if not location:
                _result(False, "pick_location() returned None")
            else:
                our_comp = next((c for c in comp_entities if c["id"] == component_id), None)
                if not our_comp:
                    _result(False, "Component not found in query result")
                else:
                    try:
                        path = location.get_filesystem_path(our_comp)
                        if path is None or not str(path).strip():
                            _result(False, f"path => {path!r}")
                        else:
                            _result(True, f"path = {path[:100]}{'...' if len(str(path)) > 100 else ''}")
                        try:
                            rid = location.get_resource_identifier(our_comp)
                            print(f"  resource_identifier: {rid!r}")
                        except Exception:
                            pass
                    except Exception as e:
                        _result(False, f"exception: {e}")
                        import traceback
                        traceback.print_exc()
    except Exception as e:
        _result(False, f"Browser-style flow failed: {e}")
        import traceback
        traceback.print_exc()

    # --- Hypothesis D: All locations with availability > 0 ---
    _section("D) All locations where component has availability > 0")

    try:
        locations = session.query("Location").all()
        found_any = False
        for loc in locations:
            try:
                avail = loc.get_component_availability(component)
                if avail <= 0:
                    continue
                found_any = True
                acc = _accessor_type(loc)
                path_result = "(not tried)"
                rid_result = "(not tried)"
                try:
                    rid = loc.get_resource_identifier(component)
                    rid_result = rid[:80] + "..." if rid and len(str(rid)) > 80 else (rid or "(empty)")
                except Exception as ex:
                    rid_result = f"exception: {ex!r}"
                try:
                    p = loc.get_filesystem_path(component)
                    if p is None:
                        path_result = "None"
                    elif not str(p).strip():
                        path_result = "(empty)"
                    else:
                        path_result = (p[:80] + "...") if len(str(p)) > 80 else p
                except Exception as ex:
                    path_result = f"exception: {ex!r}"
                print(f"  {loc['name']!r}: avail={avail}% | accessor={acc}")
                print(f"    resource_identifier: {rid_result}")
                print(f"    path: {path_result}")
                acc = getattr(loc, "accessor", None)
                if acc is None or not hasattr(acc, "get_filesystem_path"):
                    print(f"    [WARN] accessor missing or has no get_filesystem_path")
            except Exception:
                pass
        if not found_any:
            print("  No locations with availability > 0")
    except Exception as e:
        _result(False, f"All-locations scan failed: {e}")
        import traceback
        traceback.print_exc()

    # --- E) Direct ftrack_utils.get_component_path (finput's actual function) ---
    _section("E) ftrack_utils.get_component_path (finput's function)")

    try:
        ftrack_utils_mod = None
        last_err = None
        for mod_path in [
            "ftrack_inout.ftrack_hou_utils.ftrack_utils",
            "ftrack_houdini.ftrack_hou_utils.ftrack_utils",
        ]:
            try:
                parts = mod_path.split(".")
                mod = __import__(parts[0])
                for p in parts[1:]:
                    mod = getattr(mod, p)
                ftrack_utils_mod = mod
                print(f"  Using: {mod_path}")
                break
            except (ImportError, AttributeError) as e:
                last_err = e
                continue

        if not ftrack_utils_mod or not hasattr(ftrack_utils_mod, "get_component_path"):
            if last_err:
                print(f"  Last import error: {last_err}")
            _result(False, f"ftrack_utils module not found or has no get_component_path")
        else:
            # Inject our session so get_component_path uses bootstrapped session
            if hasattr(ftrack_utils_mod, "_ftrack_session"):
                ftrack_utils_mod._ftrack_session = session  # type: ignore
            path = ftrack_utils_mod.get_component_path(component)

            if path is None or not str(path).strip():
                _result(False, f"get_component_path => {path!r}")
            else:
                _result(True, f"path = {path[:100]}{'...' if len(str(path)) > 100 else ''}")
    except Exception as e:
        _result(False, f"ftrack_utils.get_component_path failed: {e}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    print("  If pick_location returns ftrack.unmanaged but component is in burlin.local/s3:")
    print("  -> Finput fails because it uses pick_location + get_filesystem_path.")
    print("  -> Fix: iterate over locations with availability>0, use first that returns path.")
    print()
    print("  If burlin.local has accessor=None/Symbol:")
    print("  -> User location plugin may not be fully configured in standalone mode.")
    print("  -> In Houdini/Connect the accessor is set by the plugin.")
    print("=" * 80)
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
