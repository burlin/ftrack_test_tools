"""
Quick test script for Houdini to check import paths.
Copy-paste this into Houdini Python Shell.
"""

import sys
import os

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
