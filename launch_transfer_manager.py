#!/usr/bin/env python
"""
Standalone Transfer Manager UI.

Запускает то же окно TransferStatusDialog, что используют браузер и UserTasksWidget,
но отдельно от DCC. Можно:
- запускать один раз и держать открытым как общий менеджер;
- закрывать DCC (Houdini/Maya), пока идут трансферы;
- наблюдать общую очередь всех задач, запущенных из любых DCC.
"""

import os
import sys
import logging


def _bootstrap_sys_path() -> None:
    """Add repository root to sys.path so we can import ftrack_inout.browser modules."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(this_dir)  # tools/.. -> repo root
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


def main() -> int:
    _bootstrap_sys_path()

    # Lazy imports after sys.path bootstrap
    try:
        from PySide6 import QtWidgets  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime environment specific
        print(f"[launch_transfer_manager] PySide6 is required but not available: {exc}")
        return 1

    try:
        import ftrack_api  # type: ignore
    except Exception as exc:  # pragma: no cover
        print(f"[launch_transfer_manager] ftrack_api is required but not available: {exc}")
        return 1

    try:
        from ftrack_plugins.ftrack_inout.browser.transfer_status_widget import (  # type: ignore
            TransferStatusDialog,
        )
    except Exception as exc:  # pragma: no cover
        print(f"[launch_transfer_manager] Failed to import TransferStatusDialog: {exc}")
        return 1

    # Basic logging to stdout so можно видеть, что происходит
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s:%(name)s:%(message)s",
        datefmt="%H:%M:%S",
    )

    # Qt приложение
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    # Ftrack session; использует те же env, что Connect/DCC
    try:
        session = ftrack_api.Session()
    except Exception as exc:
        logging.getLogger(__name__).error("Failed to create ftrack_api.Session: %s", exc)
        return 1

    # Окно менеджера. Сессия своя, но мониторит те же Job'ы и события.
    dlg = TransferStatusDialog(session)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()

    # Запускаем цикл событий
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

