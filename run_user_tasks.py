"""
Standalone launcher for the User Tasks widget.

Uses the same environment bootstrap as run_browser.py. Integrates with:
- common.session_factory.get_shared_session() - shared session with optimized cache
- browser.simple_api_client.SimpleFtrackApiClient(session=...) - API client with shared session
"""

from __future__ import annotations

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
        from ftrack_inout.common.session_factory import get_shared_session
        from ftrack_inout.browser.simple_api_client import SimpleFtrackApiClient
        from ftrack_inout.browser.user_tasks_widget import UserTasksWidget
    except Exception as exc:
        print(f"[run_user_tasks] Failed to import ftrack_inout modules: {exc}")
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s:%(name)s:%(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )

    # Use shared session (same cache as browser, Houdini, Maya)
    session = get_shared_session()
    if not session:
        print("[run_user_tasks] ERROR: Could not create Ftrack session. Check FTRACK_* env vars.")
        sys.exit(1)

    # API client with shared session - uses same cache, no duplicate session
    api_client = SimpleFtrackApiClient(session=session)

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    widget = UserTasksWidget(api_client=api_client)
    widget.setWindowTitle("User Tasks - Mroya")
    widget.resize(900, 600)
    widget.show()

    if not getattr(app, "_is_running_event_loop", False):
        app._is_running_event_loop = True  # type: ignore[attr-defined]
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
