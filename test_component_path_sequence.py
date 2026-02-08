"""
Diagnostic script: component path resolution — finput vs browser flows.

Calls the SAME code paths as:
- finput: ftrack_utils.get_component_path() (from ftrack_houdini)
- browser: FtrackApiClient.get_component_location_info() (from simple_api_client)

Bootstrap matches run_browser (plugins, locations, credentials).
Prints all intermediate data needed for conclusions.

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


def _accessor_info(loc) -> str:
    """Describe location accessor for prints."""
    acc = getattr(loc, "accessor", None)
    if acc is None:
        return "None"
    t = type(acc).__name__
    if "Symbol" in t or "symbol" in str(type(acc)).lower():
        return f"Symbol/placeholder (no real accessor)"
    if hasattr(ftrack_api, "accessor") and hasattr(ftrack_api.accessor, "disk"):
        try:
            if isinstance(acc, ftrack_api.accessor.disk.DiskAccessor):
                return f"DiskAccessor (Disk)"
        except Exception:
            pass
    if "s3" in str(type(acc)).lower():
        return f"{t} (S3)"
    return t


def _section(title: str) -> None:
    print()
    print("=" * 80)
    print(f"  {title}")
    print("=" * 80)


def main() -> int:
    component_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_COMPONENT_ID

    print()
    print("=" * 80)
    print("  COMPONENT PATH DIAGNOSTIC — finput vs browser (real code paths)")
    print("=" * 80)
    print(f"  Component ID: {component_id}")
    print(f"  Project root: {_project_root}")
    print()

    # Session — same as browser: create then add locations (no Qt/browser import)
    try:
        session = ftrack_api.Session(auto_connect_event_hub=True)
        # Register multi-site locations (same logic as simple_api_client._add_locations_if_available)
        _multi_site = _project_root / "ftrack_plugins" / "multi-site-location-0.2.0"
        _hook_locations = _multi_site / "hook" / "locations"
        if _hook_locations.is_dir() and str(_hook_locations) not in sys.path:
            sys.path.insert(0, str(_hook_locations))
        try:
            import s3_location_plugin  # type: ignore
            import user_location_plugin  # type: ignore
            try:
                if _multi_site.joinpath(".env").is_file():
                    try:
                        from dotenv import load_dotenv
                        load_dotenv(_multi_site / ".env")
                    except Exception:
                        pass
            except Exception:
                pass
            s3_location_plugin.session_add_s3_location(session)
            location_setup = user_location_plugin.load_location_config(
                config_path=_hook_locations / "disk_locations.yaml",
                user_name=session.api_user,
            )
            user_location_plugin.session_add_user_location(session, location_setup)
            print("[run_browser] Locations registered via multi-site plugins")
        except Exception as loc_err:
            print(f"[WARN] Multi-site locations: {loc_err}")
    except Exception as e:
        print(f"[FATAL] Failed to create session: {e}")
        import traceback
        traceback.print_exc()
        return 1

    try:
        component = session.get("Component", component_id)
    except Exception as e:
        print(f"[FATAL] Failed to get component: {e}")
        return 1
    if not component:
        print("[FATAL] Component not found.")
        return 1

    # ─── Environment / versions ───
    _section("ENV — Python, fileseq, locations")
    print(f"  Python: {sys.version}")
    try:
        import fileseq
        ver = getattr(fileseq, "__version__", "?")
        print(f"  fileseq: {ver}")
    except ImportError:
        print(f"  fileseq: not available")
    print()
    print("  --- Locations with real accessor (on this host) ---")
    for loc in session.query("Location").all():
        acc = getattr(loc, "accessor", None)
        if acc is None or "Symbol" in type(acc).__name__ or "symbol" in str(type(acc)).lower():
            continue
        if not hasattr(acc, "get_filesystem_path"):
            continue
        print(f"    {loc['name']!r}: {_accessor_info(loc)}")
    try:
        session.populate([component], "component_locations")
        comp_locs = component.get("component_locations") or []
        print()
        print("  --- component_locations (where this component exists) ---")
        for cl in comp_locs:
            loc_ent = cl.get("location")
            loc_name = loc_ent.get("name", "?") if loc_ent else "?"
            rid = cl.get("resource_identifier", "?")
            print(f"    {loc_name!r}: {rid[:70]}{'...' if len(str(rid)) > 70 else ''}")
    except Exception as e:
        print(f"  component_locations: {e}")
    print()

    print("--- Component ---")
    print(f"  name: {component.get('name', '?')}")
    print(f"  file_type: {component.get('file_type', '?')}")
    print(f"  id: {component['id']}")
    if component.get("version"):
        v = component["version"]
        print(f"  version: {v.get('version')} (id: {v['id']})")
        if v.get("asset"):
            print(f"  asset: {v['asset'].get('name')} (id: {v['asset']['id']})")
    print()

    # ─── FINPUT FLOW: ftrack_utils.get_component_path (code copied from finput) ───
    _section("FINPUT FLOW — ftrack_utils.get_component_path (code from finput)")

    # Inject session so ftrack_utils uses our bootstrapped session
    import importlib
    ftrack_utils_mod = None
    for mod_path in [
        "ftrack_inout.ftrack_hou_utils.ftrack_utils",
    ]:
        try:
            ftrack_utils_mod = importlib.import_module(mod_path)
            print(f"  Module: {mod_path}")
            break
        except (ImportError, AttributeError) as e:
            print(f"  Skip {mod_path}: {e}")
            continue

    if not ftrack_utils_mod or not hasattr(ftrack_utils_mod, "get_component_path"):
        print("  [FAIL] ftrack_utils.get_component_path not available")
    else:
        if hasattr(ftrack_utils_mod, "_ftrack_session"):
            ftrack_utils_mod._ftrack_session = session  # type: ignore

        # Manual trace — same logic as get_component_path, with prints
        print()
        print("  --- Step 1: pick_location (as in finput) ---")
        try:
            loc = session.pick_location()
            if loc:
                print(f"    picked_location: name={loc['name']!r} id={loc['id']}")
                print(f"    accessor: {_accessor_info(loc)}")
                avail = loc.get_component_availability(component)
                print(f"    availability: {avail}%")
                if avail >= 100.0:
                    try:
                        p = loc.get_filesystem_path(component)
                        if p and str(p).strip():
                            print(f"    get_filesystem_path: {str(p)[:120]}{'...' if len(str(p)) > 120 else ''}")
                        else:
                            print(f"    get_filesystem_path: {p!r}")
                    except Exception as ex:
                        print(f"    get_filesystem_path: EXCEPTION {ex}")
                else:
                    print(f"    (availability < 100%, skip get_filesystem_path)")
            else:
                print("    picked_location: None")
        except Exception as e:
            print(f"    pick_location: EXCEPTION {e}")

        print()
        print("  --- Step 2a: component_locations — availability and accessor on this host ---")
        try:
            comp_loc_names = {cl.get("location", {}).get("name") for cl in (component.get("component_locations") or []) if cl.get("location")}
            for loc in session.query("Location").all():
                if loc.get("name") not in comp_loc_names:
                    continue
                try:
                    a = loc.get_component_availability(component)
                    acc = getattr(loc, "accessor", None)
                    has_gfp = acc and hasattr(acc, "get_filesystem_path")
                    in_fallback = a >= 100.0 and has_gfp
                    print(f"    {loc['name']!r}: availability={a}%, accessor_ok={has_gfp} -> in_fallback={in_fallback}")
                except Exception as ex:
                    print(f"    {loc['name']!r}: EXCEPTION {ex}")
        except Exception as e:
            print(f"    EXCEPTION: {e}")
        print()
        print("  --- Step 2: fallback — locations with 100% availability ---")
        try:
            all_locs = session.query("Location").all()
            disk, other = [], []
            for loc in all_locs:
                try:
                    a = loc.get_component_availability(component)
                    if a < 100.0:
                        continue
                    acc = getattr(loc, "accessor", None)
                    if acc and hasattr(acc, "get_filesystem_path"):
                        if hasattr(ftrack_api.accessor, "disk") and isinstance(acc, ftrack_api.accessor.disk.DiskAccessor):
                            disk.append(loc)
                        else:
                            other.append(loc)
                except Exception:
                    pass
            for loc in disk + other:
                name = loc.get("name", "?")
                acc_info = _accessor_info(loc)
                path_out = "(not tried)"
                try:
                    p = loc.get_filesystem_path(component)
                    path_out = (str(p)[:80] + "...") if p and len(str(p)) > 80 else (str(p) if p else "None")
                except Exception as ex:
                    path_out = f"EXCEPTION: {ex}"
                print(f"    {name!r}: accessor={acc_info} -> path={path_out}")
        except Exception as e:
            print(f"    EXCEPTION: {e}")

        print()
        print("  --- Step 3: actual get_component_path(component) ---")
        try:
            path = ftrack_utils_mod.get_component_path(component)
            if path and str(path).strip():
                print(f"    RESULT: {path[:120]}{'...' if len(str(path)) > 120 else ''}")
            else:
                print(f"    RESULT: {path!r}")
        except Exception as e:
            print(f"    EXCEPTION: {e}")
            import traceback
            traceback.print_exc()

    # ─── BROWSER FLOW: get_component_location_info (same logic as simple_api_client) ───
    _section("BROWSER FLOW — get_component_location_info (logic from browser, no Qt)")

    try:
        try:
            component.get("version")
        except Exception:
            pass
        location = session.pick_location()
        if not location:
            print("  pick_location: None")
            print("  path: ''")
            print("  availability: 0.0%")
        else:
            availability = location.get_component_availability(component)
            path = ""
            try:
                path = location.get_filesystem_path(component)
                if path is None:
                    path = ""
                path = (path or "").strip()
                if path and "\\" in path:
                    path = path.replace("\\", "/")
            except Exception as e:
                print(f"  get_filesystem_path: EXCEPTION {e}")
            print(f"  pick_location: {location.get('name')!r} (id={location.get('id')})")
            print(f"  path: {path!r}")
            print(f"  availability: {availability}%")
            print(f"  transfer_ready: {availability < 100.0 or not path or path.startswith('N/A')}")
    except Exception as e:
        print(f"  [FAIL] {e}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 80)
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
