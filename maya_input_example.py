"""
Maya Input Example - uses ftrack_inout.input.core from Maya.

Run from Maya Script Editor (ensure ftrack_plugins is in sys.path):
    exec(open(r"G:/mroya/tools/maya_input_example.py").read())

Or add path and call:
    import sys
    sys.path.insert(0, r"G:/mroya/ftrack_plugins")
    from tools.maya_input_example import run_example
    run_example(asset_id="YOUR_ASSET_ID")
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_paths():
    """Add ftrack_plugins to path if not present."""
    try:
        repo_root = Path(__file__).resolve().parent.parent
    except NameError:
        repo_root = Path(sys.argv[0]).resolve().parent.parent
    ftrack_plugins = repo_root / "ftrack_plugins"
    if str(ftrack_plugins) not in sys.path and ftrack_plugins.exists():
        sys.path.insert(0, str(ftrack_plugins))


def run_example(asset_id: str | None = None, force_refresh: bool = True):
    """
    Example: load asset versions, components, and resolve path using input core.

    Args:
        asset_id: Ftrack asset ID. If None, prompts or uses hardcoded test ID.
        force_refresh: Query fresh from server.
    """
    _ensure_paths()

    from ftrack_inout.input.dcc.maya import (
        get_session_for_maya,
        load_asset_version_data_for_maya,
        resolve_component_path_maya,
    )
    from ftrack_inout.input.core import (
        get_component_menu_data,
        resolve_component_to_select,
        compute_version_labels_with_indicators,
    )

    session = get_session_for_maya()
    if not session:
        print("Maya Input Example: No Ftrack session available")
        return

    if not asset_id:
        asset_id = input("Enter asset ID (or leave empty to skip): ").strip()
    if not asset_id:
        print("Maya Input Example: No asset_id, skipping")
        return

    print("Loading asset data...")
    cached = load_asset_version_data_for_maya(session, asset_id, force_refresh=force_refresh)
    if not cached:
        print("Maya Input Example: No data for asset", asset_id)
        return

    version_info = cached["version_info"]
    asset_name = cached.get("asset_name", "")
    print(f"Asset: {asset_name} ({len(version_info)} versions)")
    print("Versions:", [v["name"] for v in version_info])

    if not version_info:
        return

    version_id = version_info[0]["id"]
    items, labels = get_component_menu_data(cached, version_id)
    print("Components (first version):", labels)

    comp_id = resolve_component_to_select(cached, version_id)
    if not comp_id:
        print("No component to select")
        return

    labels_with_indicators = compute_version_labels_with_indicators(
        cached, comp_id, version_id
    )
    print("Version labels with (*):", labels_with_indicators[:5], "...")

    component = session.get("Component", comp_id)
    try:
        path = resolve_component_path_maya(session, component)
        print("Resolved path:", path)
    except Exception as e:
        print("Path resolution error:", e)

    print("Maya Input Example: Done")


if __name__ == "__main__":
    run_example()
