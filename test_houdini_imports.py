"""
Test script to check library paths and imports in Houdini.
Run this in Houdini Python Shell to see where modules are loaded from.

When run from tools/ (e.g. python tools/test_houdini_imports.py), bootstraps
project root to parent so ftrack_plugins can be found.
"""

import sys
import os
import importlib.util
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
print("HOUDINI IMPORT TEST")
print("=" * 80)

# 1. Show sys.path
print("\n1. sys.path entries:")
for i, path in enumerate(sys.path):
    print(f"  [{i}] {path}")

# 2. Check environment variables
print("\n2. Environment variables:")
env_vars = [
    "FTRACK_CONNECT_PLUGIN_PATH",
    "MROOT",
    "FTRACK_TASK",
    "FTRACK_CONTEXTID",
    "HOUDINI_PATH",
]
for var in env_vars:
    value = os.environ.get(var, "NOT SET")
    print(f"  {var} = {value}")

# 3. Try to import key modules and show their locations
print("\n3. Module locations:")
modules_to_check = [
    "ftrack_inout",
    "ftrack_inout.browser",
    "ftrack_inout.browser.browser_widget",
    "ftrack_inout.browser.transfer_status_widget",
    "ftrack_api",
    "ftrack_connect",
]

for module_name in modules_to_check:
    try:
        module = __import__(module_name, fromlist=[""])
        file_path = getattr(module, "__file__", "N/A (built-in)")
        print(f"  {module_name}:")
        print(f"    Location: {file_path}")
        if hasattr(module, "__path__"):
            print(f"    Package path: {module.__path__}")
    except ImportError as e:
        print(f"  {module_name}: FAILED - {e}")
    except Exception as e:
        print(f"  {module_name}: ERROR - {e}")

# 4. Check specific functions/classes
print("\n4. Checking specific imports:")
try:
    from ftrack_inout.browser.browser_widget import create_browser_widget
    print(f"  create_browser_widget: {create_browser_widget.__module__}")
    print(f"    File: {create_browser_widget.__code__.co_filename}")
except Exception as e:
    print(f"  create_browser_widget: FAILED - {e}")

try:
    from ftrack_inout.browser.transfer_status_widget import TransferStatusDialog, get_transfer_dialog
    print(f"  TransferStatusDialog: {TransferStatusDialog.__module__}")
    print(f"    File: {TransferStatusDialog.__init__.__code__.co_filename}")
    print(f"  get_transfer_dialog: {get_transfer_dialog.__module__}")
    print(f"    File: {get_transfer_dialog.__code__.co_filename}")
    print(f"    Returns: {get_transfer_dialog(None)}")
except Exception as e:
    print(f"  TransferStatusDialog/get_transfer_dialog: FAILED - {e}")

# 5. Check if there are multiple versions of modules
print("\n5. Checking for duplicate module paths:")
module_files = {}
for module_name in modules_to_check:
    try:
        module = __import__(module_name, fromlist=[""])
        file_path = getattr(module, "__file__", None)
        if file_path:
            if file_path in module_files:
                print(f"  WARNING: {module_name} loaded from {file_path}")
                print(f"    (also loaded as {module_files[file_path]})")
            else:
                module_files[file_path] = module_name
    except Exception:
        pass

# 6. Check browser_widget for TransferStatusDialog usage
print("\n6. Checking browser_widget for TransferStatusDialog usage:")
try:
    import inspect
    from ftrack_inout.browser import browser_widget
    browser_widget_file = browser_widget.__file__
    print(f"  browser_widget file: {browser_widget_file}")
    
    # Read the file and search for TransferStatusDialog
    with open(browser_widget_file, 'r', encoding='utf-8') as f:
        content = f.read()
        if 'TransferStatusDialog' in content:
            print("  WARNING: browser_widget.py contains 'TransferStatusDialog'")
            # Find line numbers
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                if 'TransferStatusDialog' in line or 'get_transfer_dialog' in line:
                    print(f"    Line {i}: {line.strip()[:80]}")
        else:
            print("  OK: browser_widget.py does not contain 'TransferStatusDialog'")
except Exception as e:
    print(f"  ERROR checking browser_widget: {e}")

# 7. Check transfer_status_widget for show() calls
print("\n7. Checking transfer_status_widget for show() calls:")
try:
    from ftrack_inout.browser import transfer_status_widget
    transfer_status_file = transfer_status_widget.__file__
    print(f"  transfer_status_widget file: {transfer_status_file}")
    
    with open(transfer_status_file, 'r', encoding='utf-8') as f:
        content = f.read()
        show_calls = []
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if '.show()' in line or 'self.show()' in line:
                show_calls.append((i, line.strip()))
        if show_calls:
            print(f"  Found {len(show_calls)} show() calls:")
            for line_num, line in show_calls[:10]:  # Show first 10
                print(f"    Line {line_num}: {line[:80]}")
        else:
            print("  OK: No show() calls found")
except Exception as e:
    print(f"  ERROR checking transfer_status_widget: {e}")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
