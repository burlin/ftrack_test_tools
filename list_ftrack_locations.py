"""
List all Ftrack locations available in the current environment.

Uses the same bootstrap as run_ftrack_input_widget (env, plugin path, multi-site
location registration). Locations come from:
- Ftrack server (e.g. ftrack.server, ftrack.connect)
- multi-site-location plugin: S3 location (if configured), user location from
  disk_locations.yaml (e.g. nalobin.local = machine/user disk location)

Run from project root: python list_ftrack_locations.py
Or from tools/: python tools/list_ftrack_locations.py (project root = parent of tools)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 12) and "imp" not in sys.modules:
    import types
    class ImpModule:
        @staticmethod
        def find_module(name, path=None):
            return None
        @staticmethod
        def load_module(name, file=None, pathname=None, description=None):
            raise ImportError("imp.load_module is not supported in Python 3.12+")
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
    sys.modules["imp"] = ImpModule()  # type: ignore


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(dotenv_path=str(path))
    except Exception:
        try:
            text = path.read_text(encoding="utf-8")
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip().strip("'").strip('"')
                if key:
                    os.environ.setdefault(key, value)
        except Exception:
            pass


def _bootstrap(project_root: Path) -> None:
    _load_dotenv(project_root / "config" / ".env")
    config_path = project_root / "config" / "mroya.json"
    if config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            for k, v in data.items():
                os.environ.setdefault(str(k), str(v))
        except Exception:
            pass
    plugins_root = project_root / "ftrack_plugins"
    if plugins_root.is_dir():
        os.environ.setdefault("FTRACK_CONNECT_PLUGIN_PATH", str(plugins_root))
        if str(plugins_root) not in sys.path:
            sys.path.insert(0, str(plugins_root))
        for sub in ("ftrack_inout/dependencies", "multi-site-location-0.2.0/dependencies"):
            d = plugins_root / sub
            if d.is_dir() and str(d) not in sys.path:
                sys.path.insert(0, str(d))


def main() -> None:
    _script_dir = Path(__file__).resolve().parent
    project_root = _script_dir.parent if _script_dir.name == "tools" else _script_dir
    _bootstrap(project_root)

    print("=" * 60)
    print("Ftrack locations (after same registration as run_ftrack_input_widget)")
    print("=" * 60)

    try:
        from ftrack_inout.browser.simple_api_client import FtrackApiClient
    except Exception as e:
        print(f"Failed to import FtrackApiClient: {e}")
        sys.exit(1)

    client = FtrackApiClient(_enable_bulk_preload=False)
    session = client.get_session()
    if not session:
        print("No session.")
        sys.exit(1)

    try:
        locations = session.query("Location").all()
    except Exception as e:
        print(f"Query failed: {e}")
        sys.exit(1)

    print(f"\nTotal locations: {len(locations)}\n")
    for loc in sorted(locations, key=lambda x: (-(x.get("priority") or 0), (x.get("name") or ""))):
        name = loc.get("name") or ""
        loc_id = loc.get("id") or ""
        priority = loc.get("priority")
        print(f"  {name!r}")
        print(f"    id: {loc_id}")
        print(f"    priority: {priority}")
        print()

    try:
        picked = session.pick_location()
        if picked:
            print("pick_location() ->")
            print(f"  name: {picked.get('name')!r}")
            print(f"  id:   {picked.get('id')}")
        else:
            print("pick_location() -> None")
    except Exception as e:
        print(f"pick_location() failed: {e}")

    print("=" * 60)


if __name__ == "__main__":
    main()
