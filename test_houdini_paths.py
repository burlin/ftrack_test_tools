"""
Quick test script for Houdini to check import paths.
Copy-paste this into Houdini Python Shell.

When run from tools/ (e.g. python tools/test_houdini_paths.py), bootstraps
project root to parent so ftrack_plugins can be found.
"""

import sys
import os
from pathlib import Path

# When run from tools/, add project ftrack_plugins to path before any ftrack imports
_script_dir = Path(__file__).resolve().parent
if _script_dir.name == "tools":
    _project_root = _script_dir.parent
    _plugins_root = _project_root / "ftrack_plugins"
    if _plugins_root.is_dir():
        if str(_plugins_root) not in sys.path:
            sys.path.insert(0, str(_plugins_root))
        for _sub in ("ftrack_inout/dependencies", "multi-site-location-0.2.0/dependencies"):
            _d = _plugins_root / _sub
            if _d.is_dir() and str(_d) not in sys.path:
                sys.path.insert(0, str(_d))

print("=" * 80)
print("HOUDINI PATH TEST")
print("=" * 80)

# Show sys.path
print("\nsys.path:")
for i, p in enumerate(sys.path):
    print(f"  [{i}] {p}")

# Check environment
print("\nEnvironment:")
print(f"  FTRACK_CONNECT_PLUGIN_PATH = {os.environ.get('FTRACK_CONNECT_PLUGIN_PATH', 'NOT SET')}")
print(f"  MROOT = {os.environ.get('MROOT', 'NOT SET')}")

# Try imports
print("\nImport test:")
try:
    from ftrack_inout.browser.transfer_status_widget import TransferStatusDialog, get_transfer_dialog
    print(f"  ✓ TransferStatusDialog imported from: {TransferStatusDialog.__module__}")
    print(f"    File: {TransferStatusDialog.__init__.__code__.co_filename}")
    print(f"  ✓ get_transfer_dialog imported")
    result = get_transfer_dialog(None)
    print(f"    Returns: {result}")
except Exception as e:
    print(f"  ✗ Import failed: {e}")
    import traceback
    traceback.print_exc()

try:
    from ftrack_inout.browser.browser_widget import create_browser_widget
    print(f"  ✓ create_browser_widget imported from: {create_browser_widget.__module__}")
except Exception as e:
    print(f"  ✗ Import failed: {e}")

print("\n" + "=" * 80)
