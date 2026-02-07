"""
Test script for debugging session.populate() usage.

Tests different ways to call populate() to find the correct syntax.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Compatibility: imp module stub for Python 3.12+
if sys.version_info >= (3, 12) and 'imp' not in sys.modules:
    import types
    class ImpModule:
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
    sys.modules['imp'] = ImpModule()


def _load_dotenv_if_available(path: Path) -> None:
    """Load .env file if available."""
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=str(path))
    except Exception:
        # Fallback: manual parser
        try:
            text = path.read_text(encoding="utf-8")
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key:
                    os.environ.setdefault(key, value)
        except Exception:
            pass


def _bootstrap_environment(project_root: Path) -> None:
    """Initialize environment."""
    _load_dotenv_if_available(project_root / "config" / ".env")

    # Load config/mroya.json
    config_path = project_root / "config" / "mroya.json"
    if config_path.is_file():
        try:
            data: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
            for key, value in data.items():
                os.environ.setdefault(str(key), str(value))
        except Exception:
            pass

    # Add ftrack plugins to path
    plugins_root = project_root / "ftrack_plugins"
    if plugins_root.is_dir():
        os.environ.setdefault("FTRACK_CONNECT_PLUGIN_PATH", str(plugins_root))
        if str(plugins_root) not in sys.path:
            sys.path.insert(0, str(plugins_root))

        # Add dependencies
        inout_deps = plugins_root / "ftrack_inout" / "dependencies"
        if inout_deps.is_dir() and str(inout_deps) not in sys.path:
            sys.path.insert(0, str(inout_deps))

        multi_site_deps = plugins_root / "multi-site-location-0.2.0" / "dependencies"
        if multi_site_deps.is_dir() and str(multi_site_deps) not in sys.path:
            sys.path.insert(0, str(multi_site_deps))


def test_populate_syntax(asset_id: str):
    """Test different ways to call session.populate()."""
    
    print("=" * 80)
    print(f"TESTING session.populate() SYNTAX")
    print("=" * 80)
    
    # Import after bootstrap
    try:
        import ftrack_api
        from ftrack_inout.common.session_factory import create_shared_session, reset_shared_session
    except ImportError as e:
        print(f"[ERROR] Failed to import required modules: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Reset session to start fresh
    reset_shared_session()
    
    # Create session
    print("\n[1] Creating session...")
    session = create_shared_session()
    if not session:
        print("[ERROR] Failed to create session")
        return
    print("[OK] Session created")
    
    # Get asset and versions
    print("\n[2] Getting asset and versions...")
    try:
        asset = session.get('Asset', asset_id)
        if not asset:
            print(f"[ERROR] Asset {asset_id} not found")
            return
        print(f"[OK] Asset: {asset.get('name', 'Unknown')}")
    except Exception as e:
        print(f"[ERROR] Failed to get asset: {e}")
        return
    
    # Query for version IDs
    print("\n[3] Querying for version IDs...")
    try:
        version_ids_query = session.query(
            f'select id from AssetVersion where asset.id is "{asset_id}" order by version desc limit 5'
        ).all()
        version_ids = [v['id'] for v in version_ids_query]
        print(f"[OK] Found {len(version_ids)} versions")
    except Exception as e:
        print(f"[ERROR] Failed to query versions: {e}")
        return
    
    if not version_ids:
        print("[WARNING] No versions found")
        return
    
    # Get version entities
    print("\n[4] Getting version entities...")
    versions_entities = []
    for version_id in version_ids:
        try:
            version = session.get('AssetVersion', version_id)
            if version:
                versions_entities.append(version)
        except Exception as e:
            print(f"[WARNING] Failed to get version {version_id}: {e}")
    
    print(f"[OK] Loaded {len(versions_entities)} version entities")
    
    if not versions_entities:
        print("[ERROR] No version entities loaded")
        return
    
    # Test different populate() syntaxes
    print("\n" + "=" * 80)
    print("TESTING DIFFERENT populate() SYNTAXES")
    print("=" * 80)
    
    # Test 1: Current (broken) syntax
    print("\n[TEST 1] Current syntax: session.populate(entities, 'field1', 'field2', 'field3')")
    try:
        start = time.time()
        session.populate(versions_entities, 'metadata', 'date', 'comment')
        elapsed = time.time() - start
        print(f"[OK] ✓ Worked! Took {elapsed*1000:.2f}ms")
    except Exception as e:
        print(f"[FAIL] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: With unpacking
    print("\n[TEST 2] With unpacking: session.populate(entities, *fields)")
    try:
        fields = ['metadata', 'date', 'comment']
        start = time.time()
        session.populate(versions_entities, *fields)
        elapsed = time.time() - start
        print(f"[OK] ✓ Worked! Took {elapsed*1000:.2f}ms")
    except Exception as e:
        print(f"[FAIL] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Single field
    print("\n[TEST 3] Single field: session.populate(entities, 'date')")
    try:
        start = time.time()
        session.populate(versions_entities, 'date')
        elapsed = time.time() - start
        print(f"[OK] ✓ Worked! Took {elapsed*1000:.2f}ms")
    except Exception as e:
        print(f"[FAIL] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 4: Check populate signature
    print("\n[TEST 4] Checking populate() signature...")
    try:
        import inspect
        sig = inspect.signature(session.populate)
        print(f"[INFO] populate() signature: {sig}")
        print(f"[INFO] Parameters: {list(sig.parameters.keys())}")
    except Exception as e:
        print(f"[WARNING] Could not inspect signature: {e}")
    
    # Test 5: Check documentation/help
    print("\n[TEST 5] Checking populate() help...")
    try:
        help_text = session.populate.__doc__
        if help_text:
            print(f"[INFO] Docstring (first 200 chars): {help_text[:200]}...")
        else:
            print("[INFO] No docstring available")
    except Exception:
        pass
    
    # Test 6: Try with list of fields
    print("\n[TEST 6] With list: session.populate(entities, ['metadata', 'date', 'comment'])")
    try:
        fields_list = ['metadata', 'date', 'comment']
        start = time.time()
        session.populate(versions_entities, fields_list)
        elapsed = time.time() - start
        print(f"[OK] ✓ Worked! Took {elapsed*1000:.2f}ms")
    except Exception as e:
        print(f"[FAIL] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 7: Check what works in other parts of codebase
    print("\n[TEST 7] Checking how populate() is used elsewhere in codebase...")
    try:
        # Try the syntax from _refresh_cached_entities
        fields = ['metadata', 'date', 'comment']
        field_strings = [str(f) for f in fields]
        start = time.time()
        session.populate(versions_entities, *field_strings)
        elapsed = time.time() - start
        print(f"[OK] ✓ Worked with field_strings! Took {elapsed*1000:.2f}ms")
    except Exception as e:
        print(f"[FAIL] ✗ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("Check which syntax worked above and use that in browser_widget_optimized.py")
    print("=" * 80)
    
    # Cleanup
    try:
        session.close()
    except Exception:
        pass


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python test_populate.py <asset_id>")
        print("\nExample:")
        print("  python test_populate.py a96dc802-4c14-4867-bff8-b1786b014f15")
        sys.exit(1)
    
    asset_id = sys.argv[1]
    
    # Bootstrap environment (when run from tools/, use parent as project root)
    _script_dir = Path(__file__).resolve().parent
    project_root = _script_dir.parent if _script_dir.name == "tools" else _script_dir
    _bootstrap_environment(project_root)
    
    # Check credentials
    required_vars = ['FTRACK_SERVER', 'FTRACK_API_KEY', 'FTRACK_API_USER']
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        print(f"[ERROR] Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)
    
    # Run tests
    try:
        test_populate_syntax(asset_id)
    except KeyboardInterrupt:
        print("\n[INFO] Test interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
