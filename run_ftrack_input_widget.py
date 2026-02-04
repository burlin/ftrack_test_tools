from __future__ import annotations

"""
Standalone launcher for testing FtrackInputWidget (generic finput‑like widget).

Uses the same bootstrap as run_browser.py:
- sets FTRACK_CONNECT_PLUGIN_PATH to project ftrack_plugins
- adds ftrack_inout and multi-site-location dependencies to sys.path
- checks ftrack_api availability

Then creates Qt application and shows FtrackInputWidget.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

# imp stub for Python 3.12+ (same as run_browser.py)
if sys.version_info >= (3, 12) and "imp" not in sys.modules:
    import types

    class ImpModule:
        """Minimal imp module stub for Python 3.12+ compatibility"""

        @staticmethod
        def find_module(name, path=None):
            return None

        @staticmethod
        def load_module(name, file=None, pathname=None, description=None):
            raise ImportError("imp.load_module is not supported in Python 3.12+")

        @staticmethod
        def new_module(name):
            return types.ModuleType(name)

        @staticmethod
        def get_suffixes():
            return []

        @staticmethod
        def acquire_lock():
            pass

        @staticmethod
        def release_lock():
            pass

    imp_stub = ImpModule()
    sys.modules["imp"] = imp_stub  # type: ignore
    print("[run_ftrack_input_widget] Added imp module stub for Python 3.12+ compatibility")


def _debug_print_aws_env() -> None:
    """Debug output of AWS environment variables (same as run_browser.py)."""
    keys = (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
    )
    print("[run_ftrack_input_widget] ---- AWS-related environment after bootstrap ----")
    for key in keys:
        value = os.environ.get(key)
        if not value:
            print(f"[run_ftrack_input_widget] {key}=<not set>")
            continue

        if len(value) > 8:
            masked = value[:4] + "..." + value[-4:]
        else:
            masked = "***"
        print(f"[run_ftrack_input_widget] {key}={masked!r}")
    print("[run_ftrack_input_widget] -------------------------------------------------")


def _load_dotenv_if_available(path: Path) -> None:
    """Best-effort .env loading (same as run_browser.py)."""
    if not path.is_file():
        return

    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        # Fallback: manual .env parser
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:  # pragma: no cover - diagnostics
            print(f"[run_ftrack_input_widget] Failed to read {path}: {exc}")
            return

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key:
                os.environ.setdefault(key, value)
        return

    load_dotenv(dotenv_path=str(path))


def _bootstrap_environment(project_root: Path) -> None:
    """Initialize environment for standalone FtrackInputWidget launch."""

    _load_dotenv_if_available(project_root / ".env")
    _load_dotenv_if_available(project_root / "config" / ".env")
    _load_dotenv_if_available(
        project_root / "ftrack_plugins" / "multi-site-location-0.2.0" / ".env"
    )

    config_path = project_root / "config" / "mroya.json"
    if config_path.is_file():
        try:
            data: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
            for key, value in data.items():
                os.environ.setdefault(str(key), str(value))
        except Exception as exc:  # pragma: no cover - diagnostics
            print(f"[run_ftrack_input_widget] Failed to read {config_path}: {exc}")

    plugins_root = project_root / "ftrack_plugins"
    if plugins_root.is_dir():
        os.environ.setdefault("FTRACK_CONNECT_PLUGIN_PATH", str(plugins_root))
        plugins_str = str(plugins_root)
        if plugins_str not in sys.path:
            sys.path.insert(0, plugins_str)

        inout_deps = plugins_root / "ftrack_inout" / "dependencies"
        inout_deps_str = str(inout_deps)
        if inout_deps.is_dir() and inout_deps_str not in sys.path:
            sys.path.insert(0, inout_deps_str)
            print(
                f"[run_ftrack_input_widget] Added ftrack_inout dependencies to sys.path: {inout_deps_str}"
            )

        multi_site_deps = plugins_root / "multi-site-location-0.2.0" / "dependencies"
        multi_site_deps_str = str(multi_site_deps)
        if multi_site_deps.is_dir() and multi_site_deps_str not in sys.path:
            sys.path.insert(0, multi_site_deps_str)
            print(
                f"[run_ftrack_input_widget] Added multi-site-location dependencies to sys.path: {multi_site_deps_str}"
            )

        try:
            import ftrack_api  # type: ignore
            print("[run_ftrack_input_widget] [OK] ftrack_api is available after bootstrap")
        except ImportError as ftrack_err:
            print(
                f"[run_ftrack_input_widget] [WARN] ftrack_api not available after bootstrap: {ftrack_err}"
            )
            print(
                "[run_ftrack_input_widget] Checking sys.path for ftrack_api locations..."
            )
            for i, path_entry in enumerate(sys.path[:10]):
                ftrack_api_check = Path(path_entry) / "ftrack_api"
                if ftrack_api_check.exists():
                    print(
                        f"[run_ftrack_input_widget]   Found ftrack_api at sys.path[{i}]: {path_entry}"
                    )
                else:
                    print(
                        f"[run_ftrack_input_widget]   No ftrack_api at sys.path[{i}]: {path_entry}"
                    )


def main() -> None:
    """Launch standalone FtrackInputWidget."""
    _script_dir = Path(__file__).resolve().parent
    project_root = _script_dir.parent if _script_dir.name == "tools" else _script_dir
    _bootstrap_environment(project_root)
    _debug_print_aws_env()

    try:
        from PySide6 import QtWidgets  # type: ignore
    except Exception as exc:  # pragma: no cover
        print(f"[run_ftrack_input_widget] Failed to import PySide6: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        from ftrack_inout.browser.ftrack_input_widget import (  # type: ignore
            FtrackInputWidget,
            FtrackComponentSelection,
        )

        print(
            "[run_ftrack_input_widget] [OK] Successfully imported FtrackInputWidget from ftrack_inout.browser"
        )
    except Exception as exc:  # pragma: no cover
        import traceback

        print(
            f"[run_ftrack_input_widget] [FAIL] Failed to import FtrackInputWidget: {exc}",
            file=sys.stderr,
        )
        print(
            f"[run_ftrack_input_widget] Traceback:\n{traceback.format_exc()}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        import ftrack_api  # type: ignore

        session = ftrack_api.Session()
        user = session.query(f'User where username is "{session.api_user}"').one()
        print(
            f"[run_ftrack_input_widget] Connected as user: {user['username']} ({user['id']})"
        )
        try:
            loc = session.pick_location()
            if loc:
                print(
                    f"[run_ftrack_input_widget] pick_location() -> {loc['name']} (id={loc['id']}, priority={loc.priority})"
                )
        except Exception as loc_exc:
            print(
                f"[run_ftrack_input_widget] [WARN] pick_location() failed: {loc_exc}"
            )
    except Exception as exc:
        print(
            f"[run_ftrack_input_widget] [WARN] Could not create ftrack_api.Session(): {exc}"
        )

    try:
        app = QtWidgets.QApplication.instance()
        if app is None:
            app = QtWidgets.QApplication(sys.argv)

        widget = FtrackInputWidget()

        def _on_selection(sel: FtrackComponentSelection) -> None:
            print("[run_ftrack_input_widget] selectionResolved:")
            print(
                f"  task_id={sel.task_id}, asset_id={sel.asset_id}, version_id={sel.version_id}, component_id={sel.component_id}"
            )
            print(f"  file_path={sel.file_path!r}, transfer_ready={sel.transfer_ready}")

        def _on_transfer(sel: FtrackComponentSelection) -> None:
            print("[run_ftrack_input_widget] transferRequested:")
            print(
                f"  component_id={sel.component_id}, from={sel.transfer_from_id}, to={sel.transfer_to_id}"
            )

        widget.selectionResolved.connect(_on_selection)
        widget.transferRequested.connect(_on_transfer)

        widget.setWindowTitle("Ftrack Input (finput loader)")
        widget.resize(520, 420)
        widget.show()

        if not getattr(app, "_is_running_event_loop", False):
            app._is_running_event_loop = True  # type: ignore[attr-defined]
            sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\n[run_ftrack_input_widget] Interrupted by user", file=sys.stderr)
        sys.exit(0)
    except Exception as exc:  # pragma: no cover
        import traceback

        print(
            f"[run_ftrack_input_widget] [ERROR] Failed to launch widget: {exc}",
            file=sys.stderr,
        )
        print(
            f"[run_ftrack_input_widget] Traceback:\n{traceback.format_exc()}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
