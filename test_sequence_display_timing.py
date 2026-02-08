"""
Measure time spent on sequence-related operations when loading version components.

Simulates the browser path: query component IDs -> get components -> populate(members)
-> build display names (frame range + pattern). No Qt, no UI.

Usage:
  python test_sequence_display_timing.py [version_id]

If version_id omitted: finds a version that has at least one SequenceComponent.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_script_dir))  # run_browser.py

# Bootstrap (same as test_component_path_sequence)
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

from run_browser import _bootstrap_environment, _load_dotenv_if_available
_bootstrap_environment(_project_root)
_load_dotenv_if_available(_project_root / "config" / ".env")

import ftrack_api

# Locations
_multi_site = _project_root / "ftrack_plugins" / "multi-site-location-0.2.0"
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


def _frame_range_from_members(members):
    if not members:
        return None, None
    frames = []
    for m in members:
        name = m.get('name')
        if name is None:
            continue
        try:
            frames.append(int(name))
        except (ValueError, TypeError):
            continue
    if not frames:
        return None, None
    return min(frames), max(frames)


def _build_display_name(comp_name, file_type, member_count, padding, frame_min, frame_max):
    if not comp_name:
        comp_name = 'Unknown'
    if member_count is not None and (padding is not None or file_type):
        pad = padding if padding is not None else 4
        pattern = f".%0{pad}d.{file_type}" if file_type else f".%0{pad}d"
        if frame_min is not None and frame_max is not None:
            return f"{comp_name} ({pattern}) {frame_min} - {frame_max} ({member_count})"
        return f"{comp_name} ({pattern}) {member_count}"
    if file_type:
        return f"{comp_name} ({file_type})"
    return comp_name


def main():
    session = ftrack_api.Session()
    s3_location_plugin.session_add_s3_location(session)
    location_setup = user_location_plugin.load_location_config(
        config_path=_hook_locations / "disk_locations.yaml",
        user_name=session.api_user,
    )
    user_location_plugin.session_add_user_location(session, location_setup)

    # Default: version of known sequence component (maya_part)
    DEFAULT_SEQUENCE_COMPONENT_ID = "dbf2f337-7e71-42ad-a4e3-867ca602c658"
    version_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not version_id:
        comp = session.get("Component", DEFAULT_SEQUENCE_COMPONENT_ID)
        if not comp:
            print("[FAIL] Default component not found. Pass version_id: python test_sequence_display_timing.py <version_id>")
            sys.exit(1)
        version_id = comp["version_id"]
        print(f"Using version_id from component {DEFAULT_SEQUENCE_COMPONENT_ID}: {version_id}")

    print(f"\nVersion: {version_id}")
    print("=" * 60)

    # 1) Query component IDs
    t0 = time.perf_counter()
    q = session.query(f'select id from Component where version.id is "{version_id}"')
    component_ids_result = q.all()
    t_query = time.perf_counter() - t0
    component_ids = [c["id"] for c in component_ids_result]
    print(f"  1. Query component IDs:     {t_query*1000:7.1f} ms  -> {len(component_ids)} components")

    if not component_ids:
        print("  No components.")
        session.close()
        return 0

    # 2) session.get for each component
    t0 = time.perf_counter()
    component_entities = []
    for cid in component_ids:
        try:
            comp = session.get("Component", cid)
            if comp:
                component_entities.append(comp)
        except Exception:
            pass
    t_get = time.perf_counter() - t0
    print(f"  2. session.get (batch):    {t_get*1000:7.1f} ms  -> {len(component_entities)} entities")

    # 3) Populate members for SequenceComponents
    sequence_components = [
        c for c in component_entities
        if getattr(c, "entity_type", None) == "SequenceComponent"
    ]
    t0 = time.perf_counter()
    if sequence_components:
        session.populate(sequence_components, "members")
    t_populate = time.perf_counter() - t0
    print(f"  3. populate(members):      {t_populate*1000:7.1f} ms  -> {len(sequence_components)} sequences")

    # 4) Build display names — break down: member access vs entity attr vs our logic
    t0 = time.perf_counter()
    members_list = []
    for component in component_entities:
        members = component.get("members") or []
        members_list.append((component, list(members) if members else []))
    t_member_access = time.perf_counter() - t0

    t0 = time.perf_counter()
    row_data = []
    for component, members in members_list:
        comp_name = component.get("name", "")
        file_type = component.get("file_type", "")
        is_seq = getattr(component, "entity_type", None) == "SequenceComponent"
        padding = component.get("padding") if is_seq else None
        row_data.append((comp_name, file_type, members, is_seq, padding))
    t_entity_attr = time.perf_counter() - t0

    t0 = time.perf_counter()
    for comp_name, file_type, members, is_seq, padding in row_data:
        member_count = len(members) if is_seq else None
        frame_min, frame_max = _frame_range_from_members(members) if is_seq else (None, None)
        _build_display_name(comp_name, file_type, member_count, padding, frame_min, frame_max)
    t_display = time.perf_counter() - t0

    # 4c fast: extract member names once, then pure Python (no entity access in loop)
    t0 = time.perf_counter()
    row_data_fast = []
    for comp_name, file_type, members, is_seq, padding in row_data:
        names = [m.get("name") for m in members] if is_seq and members else []
        row_data_fast.append((comp_name, file_type, names, is_seq, padding))
    t_extract_names = time.perf_counter() - t0

    def _frame_range_from_names(names):
        frames = []
        for name in names:
            if name is None:
                continue
            try:
                frames.append(int(name))
            except (ValueError, TypeError):
                continue
        return (min(frames), max(frames)) if frames else (None, None)

    t0 = time.perf_counter()
    for comp_name, file_type, names, is_seq, padding in row_data_fast:
        member_count = len(names) if is_seq else None
        frame_min, frame_max = _frame_range_from_names(names) if is_seq else (None, None)
        _build_display_name(comp_name, file_type, member_count, padding, frame_min, frame_max)
    t_display_pure = time.perf_counter() - t0

    print(f"  4a. member access (get+list): {t_member_access*1000:7.1f} ms")
    print(f"  4b. entity attr (name, type, padding): {t_entity_attr*1000:7.1f} ms")
    print(f"  4c. frame range + display (members=entities): {t_display*1000:7.1f} ms  <- member.get('name') cost")
    print(f"  4d. extract names (once):    {t_extract_names*1000:7.1f} ms")
    print(f"  4e. frame range + display (plain names): {t_display_pure*1000:7.1f} ms")

    total = t_query + t_get + t_populate + t_member_access + t_entity_attr + t_display
    print("  " + "-" * 50)
    print(f"  TOTAL:                    {total*1000:7.1f} ms")
    print()

    # Show one example
    for c in component_entities:
        if getattr(c, "entity_type", None) == "SequenceComponent":
            members = c.get("members") or []
            member_count = len(members)
            padding = c.get("padding")
            frame_min, frame_max = _frame_range_from_members(members)
            disp = _build_display_name(
                c.get("name", ""), c.get("file_type", ""),
                member_count, padding, frame_min, frame_max
            )
            print(f"  Example: {disp}")
            break

    print()
    print("  Takeaway: 4c slow = member.get('name') per frame (entity access).")
    print("            4e fast = same math on plain names. Extract names once per component.")
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
