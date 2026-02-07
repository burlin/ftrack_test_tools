from __future__ import annotations

"""
Standalone launcher for the user tasks widget.

Uses the same environment bootstrap as run_browser.py, but instead of
main browser opens widget with list of current user's tasks.
"""

import sys
from pathlib import Path
import logging

# Ensure tools is in path for run_browser import
_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from run_browser import _bootstrap_environment  # type: ignore


def main() -> None:
    _script_dir = Path(__file__).resolve().parent
    project_root = _script_dir.parent if _script_dir.name == "tools" else _script_dir
    _bootstrap_environment(project_root)

    try:
        from PySide6 import QtWidgets  # type: ignore
    except Exception as exc:  # pragma: no cover
        print(f"[run_user_tasks] Failed to import PySide6: {exc}")
        sys.exit(1)

    try:
        from ftrack_inout import browser as fbrowser  # type: ignore
    except Exception as exc:
        print(f"[run_user_tasks] Failed to import ftrack_inout.browser: {exc}")
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s:%(name)s:%(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )

    if getattr(fbrowser, "UserTasksWidget", None) is None:
        print("[run_user_tasks] UserTasksWidget is not available in ftrack_inout.browser")
        sys.exit(1)

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    widget = fbrowser.UserTasksWidget()  # type: ignore[call-arg]
    widget.setWindowTitle("User Tasks - Mroya")
    widget.resize(900, 600)
    widget.show()

    if not getattr(app, "_is_running_event_loop", False):
        app._is_running_event_loop = True  # type: ignore[attr-defined]
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
