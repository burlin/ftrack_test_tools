from __future__ import annotations

"""
Standalone launcher for the Ftrack browser / Task Hub.

Goals:
- Allow running browser both from ftrack Connect (when environment is already
  configured) and standalone, from clean console.
- Keep all environment bootstrap (MROOT, FTRACK_* and plugin paths) here,
  not scattered across browser code itself.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

# Compatibility: imp module was removed in Python 3.12+, but ftrack_api dependencies may need it
# Add imp module stub before importing ftrack_api (only for Python 3.12+)
# Note: Python 3.11 (used in Houdini/Maya) still has imp module, so this stub is not needed there
if sys.version_info >= (3, 12) and 'imp' not in sys.modules:
    import types
    # Create a minimal imp module stub for compatibility
    class ImpModule:
        """Minimal imp module stub for Python 3.12+ compatibility"""
        @staticmethod
        def find_module(name, path=None):
            return None
        @staticmethod
        def load_module(name, file=None, pathname=None, description=None):
            raise ImportError(f"imp.load_module is not supported in Python 3.12+")
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
    sys.modules['imp'] = imp_stub  # type: ignore
    print("[run_browser] Added imp module stub for Python 3.12+ compatibility")

# Compatibility: distutils was removed in Python 3.12+, ftrack_api.session uses distutils.version.LooseVersion
if sys.version_info >= (3, 12) and 'distutils' not in sys.modules:
    import re
    import types

    class LooseVersion:
        """Minimal LooseVersion for version string comparison (e.g. '3.3.11')."""
        def __init__(self, v: str):
            self.v = str(v)
            parts = re.findall(r'\d+|[a-zA-Z]+', self.v)
            self.version = [int(x) if x.isdigit() else x for x in parts]

        def __gt__(self, other: object) -> bool:
            if not isinstance(other, LooseVersion):
                other = LooseVersion(str(other))
            return self.version > other.version

        def __lt__(self, other: object) -> bool:
            if not isinstance(other, LooseVersion):
                other = LooseVersion(str(other))
            return self.version < other.version

        def __eq__(self, other: object) -> bool:
            if not isinstance(other, LooseVersion):
                other = LooseVersion(str(other))
            return self.version == other.version

    distutils_version = types.ModuleType('distutils.version')
    distutils_version.LooseVersion = LooseVersion  # type: ignore
    distutils = types.ModuleType('distutils')
    distutils.version = distutils_version  # type: ignore
    sys.modules['distutils'] = distutils  # type: ignore
    sys.modules['distutils.version'] = distutils_version  # type: ignore
    print("[run_browser] Added distutils.version stub for Python 3.12+ compatibility")


def _debug_print_aws_env() -> None:
    """Debug output of AWS environment variables.

    To see which credentials are actually active after bootstrap,
    but without full disclosure of secrets in log.
    """
    keys = (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
    )
    print("[run_browser] ---- AWS-related environment after bootstrap ----")
    for key in keys:
        value = os.environ.get(key)
        if not value:
            print(f"[run_browser] {key}=<not set>")
            continue

        # Mask value so log doesn't contain full secret.
        masked: str
        if len(value) > 8:
            masked = value[:4] + "..." + value[-4:]
        else:
            masked = "***"
        print(f"[run_browser] {key}={masked!r}")
    print("[run_browser] -------------------------------------------------")


def _load_dotenv_if_available(path: Path) -> None:
    """Best-effort .env loading.

    Priority:
    1) If python-dotenv is installed, use it.
    2) Otherwise parse file manually in KEY=VALUE format and set environment
       variables via os.environ.setdefault (without overwriting already set ones).
    """
    if not path.is_file():
        return

    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        # Fallback: manual .env parser
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:  # pragma: no cover - diagnostics
            print(f"[run_browser] Failed to read {path}: {exc}")
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

    # happy path with installed python-dotenv
    load_dotenv(dotenv_path=str(path))


def _bootstrap_environment(project_root: Path) -> None:
    """Initialize environment for standalone browser launch.

    Does only safe things:
    - loads Ftrack credentials (Ftrack Connect config.json first, then .env);
    - pulls values from config/mroya.json if some variables are not yet set;
    - adds ftrack_plugins to sys.path and FTRACK_CONNECT_PLUGIN_PATH.
    """

    # 0) Add ftrack_plugins to path so we can import credentials_loader
    plugins_root = project_root / "ftrack_plugins"
    if plugins_root.is_dir() and str(plugins_root) not in sys.path:
        sys.path.insert(0, str(plugins_root))

    # 1) Load credentials: Ftrack Connect path first, then config/.env
    try:
        from ftrack_inout.common.credentials_loader import load_ftrack_credentials_into_env
        dotenv_paths = [
            project_root / "config" / ".env",
            project_root / ".env",
        ]
        if load_ftrack_credentials_into_env(prefer_connect=True, dotenv_paths=dotenv_paths):
            print("[run_browser] Loaded Ftrack credentials (Connect path or .env)")
    except ImportError:
        _load_dotenv_if_available(project_root / "config" / ".env")

    # 2) Pull values from config/mroya.json (if exists).
    config_path = project_root / "config" / "mroya.json"
    if config_path.is_file():
        try:
            data: dict[str, Any] = json.loads(
                config_path.read_text(encoding="utf-8")
            )
            for key, value in data.items():
                # Don't overwrite already set environment variables.
                os.environ.setdefault(str(key), str(value))
        except Exception as exc:  # pragma: no cover - diagnostics
            print(f"[run_browser] Failed to read {config_path}: {exc}")

    # 3) Ensure ftrack plugins path is available (may already be in sys.path from step 0).
    if plugins_root.is_dir():
        os.environ.setdefault("FTRACK_CONNECT_PLUGIN_PATH", str(plugins_root))
        plugins_str = str(plugins_root)
        if plugins_str not in sys.path:
            sys.path.insert(0, plugins_str)

        # Additionally connect internal ftrack_inout dependencies if they exist.
        # Dependencies are located in ftrack_inout/dependencies (fileseq, boto3, ftrack_api, etc.)
        inout_deps = plugins_root / "ftrack_inout" / "dependencies"
        inout_deps_str = str(inout_deps)
        if inout_deps.is_dir() and inout_deps_str not in sys.path:
            sys.path.insert(0, inout_deps_str)
            print(f"[run_browser] Added ftrack_inout dependencies to sys.path: {inout_deps_str}")

        # Add multi-site-location plugin dependencies (boto3, yaml, jinja2, etc.)
        # This is needed for S3 and user location plugins to work
        multi_site_deps = plugins_root / "multi-site-location-0.2.0" / "dependencies"
        multi_site_deps_str = str(multi_site_deps)
        if multi_site_deps.is_dir() and multi_site_deps_str not in sys.path:
            sys.path.insert(0, multi_site_deps_str)
            print(f"[run_browser] Added multi-site-location dependencies to sys.path: {multi_site_deps_str}")

        # Check that ftrack_api is available after adding paths
        try:
            import ftrack_api  # type: ignore
            print(f"[run_browser] [OK] ftrack_api is available after bootstrap")
        except ImportError as ftrack_err:
            print(f"[run_browser] [WARN] ftrack_api not available after bootstrap: {ftrack_err}")
            print(f"[run_browser] Checking sys.path for ftrack_api locations...")
            for i, path_entry in enumerate(sys.path[:10]):  # First 10 entries
                ftrack_api_check = Path(path_entry) / "ftrack_api"
                if ftrack_api_check.exists():
                    print(f"[run_browser]   Found ftrack_api at sys.path[{i}]: {path_entry}")
                else:
                    print(f"[run_browser]   No ftrack_api at sys.path[{i}]: {path_entry}")


def main() -> None:
    """Launch standalone browser."""
    _script_dir = Path(__file__).resolve().parent
    project_root = _script_dir.parent if _script_dir.name == "tools" else _script_dir
    _bootstrap_environment(project_root)
    # Debug output of env after bootstrap to see which AWS credentials are active.
    _debug_print_aws_env()

    # Import Qt and our browser only after environment setup.
    try:
        from PySide6 import QtWidgets  # type: ignore
    except Exception as exc:  # pragma: no cover
        print(f"[run_browser] Failed to import PySide6: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        # Import browser directly from ftrack_inout.browser
        from ftrack_inout.browser import FtrackBrowser  # type: ignore
        print("[run_browser] [OK] Successfully imported FtrackBrowser from ftrack_inout.browser")
    except Exception as exc:  # pragma: no cover
        import traceback
        print(f"[run_browser] [FAIL] Failed to import FtrackBrowser from ftrack_inout.browser: {exc}", file=sys.stderr)
        print(f"[run_browser] Traceback:\n{traceback.format_exc()}", file=sys.stderr)
        sys.exit(1)

    try:
        app = QtWidgets.QApplication.instance()
        if app is None:
            app = QtWidgets.QApplication(sys.argv)

        # Standalone launcher always uses explicit DCC identifier.
        dcc = "standalone"

        print(f"[run_browser] Creating FtrackBrowser widget (dcc={dcc!r})...")
        widget = FtrackBrowser(dcc=dcc)
        widget.show()
        print("[run_browser] [OK] Browser window opened")

        # Start Qt event loop if it's not already running (important for repeated launches).
        if not getattr(app, "_is_running_event_loop", False):
            app._is_running_event_loop = True  # type: ignore[attr-defined]
            sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\n[run_browser] Interrupted by user", file=sys.stderr)
        sys.exit(0)
    except Exception as exc:  # pragma: no cover
        import traceback
        print(f"[run_browser] [ERROR] Failed to launch browser: {exc}", file=sys.stderr)
        print(f"[run_browser] Traceback:\n{traceback.format_exc()}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
