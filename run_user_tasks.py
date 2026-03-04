from __future__ import annotations

"""
Standalone launcher for the User Tasks widget.

This script is a thin wrapper around the in-plugin launcher
``ftrack_inout.browser.run_user_tasks_launcher``:
- here we only handle environment bootstrap (MROOT, paths, etc.) via run_browser;
- all Qt / session / widget logic lives in the ftrack_inout plugin so that
  ftrack Connect integrations can use the same entry point.
"""

import sys
from pathlib import Path
from typing import Sequence

# Ensure tools is in path for run_browser import
_tools_dir = Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from run_browser import _bootstrap_environment  # type: ignore


def main(argv: Sequence[str] | None = None) -> None:
    """Bootstrap environment, then delegate to in-plugin launcher."""
    if argv is None:
        argv = sys.argv[1:]

    _script_dir = Path(__file__).resolve().parent
    project_root = _script_dir.parent if _script_dir.name == "tools" else _script_dir
    _bootstrap_environment(project_root)

    # Delegate full startup (CLI parsing, Qt, session) to the plugin launcher.
    from ftrack_inout.browser import run_user_tasks_launcher

    exit_code = run_user_tasks_launcher.main(list(argv))
    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
