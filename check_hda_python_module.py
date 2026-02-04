"""Проверить Python модуль в HDA файле."""

import sys
import re
from pathlib import Path

hda_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("hsite/packages_common/ftrack_browser_package_clean/hda/driver_burlin.fpublish.2.6.hda")

with open(hda_path, 'rb') as f:
    data = f.read()

# Ищем PythonModule
pm_match = re.search(rb'PythonModule\0+(.{1,100})', data)
if pm_match:
    module_name = pm_match.group(1).split(b'\0')[0].decode('utf-8', errors='ignore')
    print(f"PythonModule: {module_name}")
else:
    print("PythonModule not found in binary data")

# Ищем ftrack_inout
ftrack_match = re.search(rb'ftrack_inout[^\0]{0,50}', data)
if ftrack_match:
    print(f"ftrack_inout reference: {ftrack_match.group(0).decode('utf-8', errors='ignore')}")
