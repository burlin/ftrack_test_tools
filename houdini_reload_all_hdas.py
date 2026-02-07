"""
Скрипт для Houdini: перезагрузка всех HDA для подтягивания обновлённых скриптов.

Использование:
- В Python shell: exec(open(r"path/to/houdini_reload_all_hdas.py").read())
- Или скопировать содержимое в Python shell
"""

import hou


def reload_all_hdas(rescan=True):
    """
    Перезагружает все загруженные HDA из файлов.
    
    Args:
        rescan: если True, Houdini проверит директории HDA на новые файлы
    """
    loaded = hou.hda.loadedFiles()
    hou.hda.reloadAllFiles(rescan=rescan)
    return loaded


def reload_hda_python_modules():
    """
    Дополнительно перезагружает Python модули (PythonModule секции) 
    всех HDA в текущей сцене. Нужно если обновились внешние .py файлы,
    которые HDA импортирует.
    """
    reloaded = []
    for node in hou.node("/").allSubChildren():
        try:
            hda_mod = node.hdaModule()
            if hda_mod is not None:
                hou.hda.reloadHDAModule(hda_mod)
                reloaded.append(node.path())
        except (AttributeError, hou.OperationFailed):
            pass
    return reloaded


def main():
    print("Перезагрузка HDA...")
    loaded = reload_all_hdas(rescan=True)
    print(f"Перезагружено {len(loaded)} HDA файлов")
    
    # Дополнительно перезагружаем Python модули в HDA
    modules = reload_hda_python_modules()
    if modules:
        print(f"Перезагружены Python модули в {len(modules)} нодах")
        for path in modules[:10]:  # показываем первые 10
            print(f"  - {path}")
        if len(modules) > 10:
            print(f"  ... и ещё {len(modules) - 10}")
    
    hou.ui.setStatusMessage("Все HDA перезагружены", hou.severityType.ImportantMessage)
    print("Готово.")


if __name__ == "__main__":
    main()
