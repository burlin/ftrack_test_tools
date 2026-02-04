"""Обновить PythonModule в HDA файле."""

import sys
import re
from pathlib import Path

hda_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("hsite/packages_common/mroya_taskhub_browser/hda/driver_burlin.fpublish.2.6.hda")
# fpublish removed; HDA should use publisher (or a wrapper that imports ftrack_inout.publisher.dcc.houdini + f_io.fselector)
new_module = sys.argv[2] if len(sys.argv) > 2 else "ftrack_inout.publisher.dcc.houdini"

with open(hda_path, 'rb') as f:
    data = f.read()

# Заменяем старый модуль на новый
# Ищем паттерн PythonModule\0+<старое_имя>
# Заменяем на PythonModule\0+<новое_имя>

# Сначала найдём старое имя
old_match = re.search(rb'PythonModule\0+(.{1,100}?)(\0|$)', data)
if old_match:
    old_module = old_match.group(1).split(b'\0')[0].decode('utf-8', errors='ignore')
    print(f"Found old PythonModule: {old_module}")
    
    # Создаём новую строку PythonModule
    new_module_bytes = new_module.encode('utf-8')
    padding = b'\0' * max(0, len(old_match.group(1)) - len(new_module_bytes))
    
    # Заменяем
    new_data = data[:old_match.start()] + b'PythonModule' + b'\0' + new_module_bytes + padding + data[old_match.end():]
    
    # Сохраняем
    with open(hda_path, 'wb') as f:
        f.write(new_data)
    print(f"Updated to: {new_module}")
else:
    print("PythonModule not found in HDA file")
