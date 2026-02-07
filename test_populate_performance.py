"""
Test script for debugging populate() performance.

Tests populate() with different field combinations to find optimal performance.
Uses a specific version ID for testing.
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


def test_populate_performance(version_id: str):
    """Test populate() performance with different field combinations."""
    
    print("=" * 80)
    print(f"TESTING populate() PERFORMANCE")
    print(f"Version ID: {version_id}")
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
    
    # Get version entity
    print(f"\n[2] Getting version entity {version_id}...")
    try:
        version = session.get('AssetVersion', version_id)
        if not version:
            print(f"[ERROR] Version {version_id} not found")
            return
        
        asset = version.get('asset')
        asset_name = asset.get('name', 'Unknown') if asset else 'Unknown'
        version_num = version.get('version', 'N/A')
        print(f"[OK] Version: {asset_name} v{version_num}")
    except Exception as e:
        print(f"[ERROR] Failed to get version: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Get all versions for the same asset to test batch populate
    print(f"\n[3] Getting all versions for asset...")
    try:
        asset_id = version.get('asset').get('id')
        version_ids_query = session.query(
            f'select id from AssetVersion where asset.id is "{asset_id}" order by version desc'
        ).all()
        version_ids = [v['id'] for v in version_ids_query]
        print(f"[OK] Found {len(version_ids)} versions")
        
        # Get all version entities
        versions_entities = []
        for vid in version_ids:
            try:
                v = session.get('AssetVersion', vid)
                if v:
                    versions_entities.append(v)
            except Exception:
                pass
        
        print(f"[OK] Loaded {len(versions_entities)} version entities")
    except Exception as e:
        print(f"[ERROR] Failed to get versions: {e}")
        import traceback
        traceback.print_exc()
        return
    
    if not versions_entities:
        print("[ERROR] No version entities loaded")
        return
    
    # Test different populate() field combinations
    print("\n" + "=" * 80)
    print("TESTING DIFFERENT populate() FIELD COMBINATIONS")
    print("=" * 80)
    
    test_cases = [
        ('date', 'Only date field'),
        ('comment', 'Only comment field'),
        ('date, comment', 'Date and comment (current optimization)'),
        ('metadata', 'Only metadata field'),
        ('metadata, date', 'Metadata and date'),
        ('metadata, comment', 'Metadata and comment'),
        ('metadata, date, comment', 'All fields (original)'),
    ]
    
    results = []
    
    for projections, description in test_cases:
        print(f"\n[TEST] {description}")
        print(f"       Fields: {projections}")
        
        try:
            # Reset entities to ensure fresh test
            for v in versions_entities:
                # Clear the fields we're about to populate to force refresh
                # (in real scenario, they're already cached, but we want to test populate speed)
                pass
            
            # Measure populate time
            start = time.time()
            session.populate(versions_entities, projections)
            elapsed = time.time() - start
            
            results.append({
                'fields': projections,
                'description': description,
                'time_ms': elapsed * 1000,
                'time_per_version_ms': (elapsed * 1000) / len(versions_entities) if versions_entities else 0,
                'success': True
            })
            
            print(f"       ✓ Success: {elapsed*1000:.2f}ms total ({elapsed*1000/len(versions_entities):.2f}ms per version)")
            
        except Exception as e:
            results.append({
                'fields': projections,
                'description': description,
                'time_ms': 0,
                'time_per_version_ms': 0,
                'success': False,
                'error': str(e)
            })
            print(f"       ✗ Failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Tested {len(versions_entities)} versions")
    print(f"\nResults (sorted by time):")
    print("-" * 80)
    
    successful_results = [r for r in results if r['success']]
    successful_results.sort(key=lambda x: x['time_ms'])
    
    for i, result in enumerate(successful_results, 1):
        print(f"{i}. {result['description']}")
        print(f"   Fields: {result['fields']}")
        print(f"   Time: {result['time_ms']:.2f}ms total, {result['time_per_version_ms']:.3f}ms per version")
        print()
    
    # Find fastest
    if successful_results:
        fastest = successful_results[0]
        slowest = successful_results[-1]
        
        print(f"Fastest: {fastest['description']} ({fastest['time_ms']:.2f}ms)")
        print(f"Slowest: {slowest['description']} ({slowest['time_ms']:.2f}ms)")
        
        if len(successful_results) > 1:
            speedup = slowest['time_ms'] / fastest['time_ms']
            print(f"Speedup: {speedup:.2f}x faster")
    
    # Failed tests
    failed_results = [r for r in results if not r['success']]
    if failed_results:
        print(f"\nFailed tests ({len(failed_results)}):")
        for result in failed_results:
            print(f"  - {result['description']}: {result.get('error', 'Unknown error')}")
    
    print("=" * 80)
    
    # Cleanup
    try:
        session.close()
    except Exception:
        pass


def main():
    """Main entry point."""
    # Default test version ID
    version_id = "ee2abebc-42cf-4ed0-9804-396ca0b66b79"
    
    if len(sys.argv) >= 2:
        version_id = sys.argv[1]
    
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
        test_populate_performance(version_id)
    except KeyboardInterrupt:
        print("\n[INFO] Test interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
