"""
Test script for PublisherWidget.

Run from project root:
    python test_publisher_ui.py
"""

import sys
import os
import json
from pathlib import Path

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
    print("[test_publisher] Added imp module stub for Python 3.12+ compatibility")

# Project root: when run from tools/, use parent
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent if _script_dir.name == "tools" else _script_dir
sys.path.insert(0, str(_project_root / "ftrack_plugins"))

# Bootstrap environment (similar to run_browser.py)
def _bootstrap_environment(project_root: Path) -> None:
    """Initialize environment for standalone publisher launch."""
    # Load credentials from config/.env
    for env_path in [project_root / "config" / ".env"]:
        if env_path.is_file():
            try:
                from dotenv import load_dotenv
                load_dotenv(dotenv_path=str(env_path))
            except ImportError:
                # Fallback: manual .env parser
                try:
                    text = env_path.read_text(encoding="utf-8")
                    for raw_line in text.splitlines():
                        line = raw_line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip("'").strip('"')
                        if key:
                            os.environ.setdefault(key, value)
                except Exception as exc:
                    print(f"[test_publisher] Failed to read {env_path}: {exc}")
    
    # Load config/mroya.json if exists
    config_path = project_root / "config" / "mroya.json"
    if config_path.is_file():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            for key, value in data.items():
                os.environ.setdefault(str(key), str(value))
        except Exception as exc:
            print(f"[test_publisher] Failed to read {config_path}: {exc}")
    
    # Ensure ftrack plugins path is available
    plugins_root = project_root / "ftrack_plugins"
    if plugins_root.is_dir():
        os.environ.setdefault("FTRACK_CONNECT_PLUGIN_PATH", str(plugins_root))
        plugins_str = str(plugins_root)
        if plugins_str not in sys.path:
            sys.path.insert(0, plugins_str)
        
        # Add ftrack_inout dependencies
        inout_deps = plugins_root / "ftrack_inout" / "dependencies"
        if inout_deps.is_dir() and str(inout_deps) not in sys.path:
            sys.path.insert(0, str(inout_deps))
        
        # Add multi-site-location dependencies
        multi_site_deps = plugins_root / "multi-site-location-0.2.0" / "dependencies"
        if multi_site_deps.is_dir() and str(multi_site_deps) not in sys.path:
            sys.path.insert(0, str(multi_site_deps))

try:
    from PySide2 import QtWidgets
except ImportError:
    try:
        from PySide6 import QtWidgets
    except ImportError:
        from PyQt5 import QtWidgets

from ftrack_inout.publisher.ui.publisher_widget import PublisherWidget


def main():
    """Run the test application."""
    # Bootstrap environment (project_root set at module level)
    _bootstrap_environment(_project_root)

    # Load credentials from Ftrack Connect path if not set (same as run_browser)
    try:
        from ftrack_inout.common.credentials_loader import load_ftrack_credentials_into_env
        load_ftrack_credentials_into_env(
            prefer_connect=True,
            dotenv_paths=[
                _project_root / "config" / ".env",
                _project_root / ".env",
            ],
        )
    except ImportError:
        pass

    # Check Ftrack session availability and create session if possible
    ftrack_session = None
    try:
        import ftrack_api
        print("[test_publisher] [OK] ftrack_api is available")

        # Prefer shared session (uses cache and credentials)
        try:
            from ftrack_inout.common.session_factory import get_shared_session
            ftrack_session = get_shared_session()
            if ftrack_session:
                print("[test_publisher] [OK] Ftrack session from session_factory")
        except ImportError:
            pass

        if not ftrack_session:
            try:
                ftrack_session = ftrack_api.Session(auto_connect_event_hub=True)
                print("[test_publisher] [OK] Ftrack session created successfully")
            except Exception as e:
                print(f"[test_publisher] [WARN] Failed to create Ftrack session: {e}")
                print("[test_publisher] [INFO] Session requires FTRACK_SERVER, FTRACK_API_KEY, and FTRACK_API_USER")
                print("[test_publisher] [INFO] Some features may not work without Ftrack session")
    except ImportError as e:
        print(f"[test_publisher] [WARN] ftrack_api not available: {e}")
        print("[test_publisher] Some features may not work without Ftrack session")
    
    app = QtWidgets.QApplication(sys.argv)
    
    # Create and show widget (pass session if available)
    widget = PublisherWidget(session=ftrack_session)
    widget.setWindowTitle("Universal Publisher - Test UI")
    widget.resize(800, 1000)
    widget.show()
    
    # Enable detailed logging first
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # Set specific loggers to DEBUG
    logging.getLogger('ftrack_inout.publisher').setLevel(logging.DEBUG)
    logging.getLogger('ftrack_inout.publisher.core').setLevel(logging.DEBUG)
    logging.getLogger('ftrack_inout.publisher.dcc').setLevel(logging.DEBUG)
    logging.getLogger('ftrack_inout.publisher.ui').setLevel(logging.DEBUG)
    
    # Test parameter access
    print("=" * 60)
    print("Testing parameter access...")
    print("=" * 60)
    
    # Set some test values
    widget.set_parameter('task_Id', 'test-task-id-123')
    widget.set_parameter('asset_name', 'test_asset')
    widget.set_parameter('use_snapshot', 1)
    widget.set_parameter('components', 2)
    
    # Get values back
    print(f"✓ task_Id: {widget.get_parameter('task_Id')}")
    print(f"✓ asset_name: {widget.get_parameter('asset_name')}")
    print(f"✓ use_snapshot: {widget.get_parameter('use_snapshot')}")
    print(f"✓ components: {widget.get_parameter('components')}")
    tt = widget.get_parameter('transfer_target_location')
    print(f"✓ transfer_target_location: {repr(tt)} (len={len(str(tt or ''))})")
    
    # Test JobBuilder and Publisher
    print("\n" + "=" * 60)
    print("Testing JobBuilder and Publisher (dry-run)...")
    print("=" * 60)
    
    try:
        from ftrack_inout.publisher.core import JobBuilder, Publisher
        
        # Build job from widget
        job = JobBuilder.from_qt_widget(widget, source_dcc="standalone_test")
        print(f"\n✓ JobBuilder created PublishJob:")
        print(f"  task_id: {job.task_id}")
        print(f"  asset_id: {job.asset_id}")
        print(f"  asset_name: {job.asset_name}")
        print(f"  asset_type: {job.asset_type}")
        print(f"  components: {len(job.components)}")
        print(f"  transfer_target_location: {repr(getattr(job, 'transfer_target_location', None))} (len={len(str(getattr(job, 'transfer_target_location') or ''))})")
        for i, comp in enumerate(job.components):
            status = "✓" if comp.export_enabled else "✗"
            transfer = getattr(comp, 'transfer_after_publish', None)
            print(f"    [{status}] {comp.name} ({comp.component_type}) transfer_after_publish={transfer}")
        
        # Validate
        is_valid, errors = job.validate()
        print(f"\n  Validation: {'✓ PASSED' if is_valid else '✗ FAILED'}")
        if errors:
            for err in errors:
                print(f"    - {err}")
        
        print("\n✓ Publisher and JobBuilder are ready!")
        print("  Click 'Render' button to test dry-run publish with real Ftrack data.")
        
    except ImportError as e:
        print(f"\n✗ Failed to import JobBuilder/Publisher: {e}")
    except Exception as e:
        print(f"\n✗ Error testing JobBuilder: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Widget is ready!")
    print("=" * 60)
    print("\nWorkflow:")
    print("1. Enter a REAL Task ID from Ftrack")
    print("2. Click 'Check' to validate task")
    print("3. Click 'Apply to asset' to set task parameters")
    print("4. Use 'get_ex' to get existing assets or 'cr_new' to create new")
    print("5. Click 'set_this' to set asset parameters")
    print("6. Click 'Apply' to finalize asset parameters")
    print("7. Click 'Render' to execute dry-run publish")
    print("\nClose the window to exit.")
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
