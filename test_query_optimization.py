"""
Test script for optimizing the version IDs query.

Tests different query approaches to find the fastest way to get version IDs.
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
    # Load .env files
    _load_dotenv_if_available(project_root / ".env")
    _load_dotenv_if_available(project_root / "config" / ".env")
    _load_dotenv_if_available(project_root / "ftrack_plugins" / "multi-site-location-0.2.0" / ".env")

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


def test_query_optimization(asset_id: str):
    """Test different query approaches for getting version IDs."""
    
    print("=" * 80)
    print(f"TESTING QUERY OPTIMIZATION")
    print(f"Asset ID: {asset_id}")
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
    print("\n[SETUP] Creating session...")
    session = create_shared_session()
    if not session:
        print("[ERROR] Failed to create session")
        return
    print("[OK] Session created")
    
    # Get asset info
    try:
        asset = session.get('Asset', asset_id)
        if not asset:
            print(f"[ERROR] Asset {asset_id} not found")
            return
        asset_name = asset.get('name', 'Unknown')
        print(f"[INFO] Asset: {asset_name}")
    except Exception as e:
        print(f"[ERROR] Failed to get asset: {e}")
        return
    
    results = []
    
    # Test 1: Current query (select id only)
    print("\n" + "=" * 80)
    print("TEST 1: Current query (select id only)")
    print("=" * 80)
    query1 = f'select id from AssetVersion where asset.id is "{asset_id}" order by version desc'
    print(f"Query: {query1}")
    
    for i in range(3):  # Run 3 times to check consistency
        start = time.time()
        try:
            result1 = session.query(query1).all()
            elapsed = time.time() - start
            version_ids1 = [v['id'] for v in result1]
            results.append({
                'test': 'Current (select id)',
                'run': i + 1,
                'time_ms': elapsed * 1000,
                'count': len(version_ids1),
                'success': True
            })
            print(f"  Run {i+1}: {elapsed*1000:.2f}ms ({len(version_ids1)} versions)")
        except Exception as e:
            results.append({
                'test': 'Current (select id)',
                'run': i + 1,
                'time_ms': 0,
                'success': False,
                'error': str(e)
            })
            print(f"  Run {i+1}: FAILED - {e}")
    
    # Test 2: Query without order by
    print("\n" + "=" * 80)
    print("TEST 2: Query without order by")
    print("=" * 80)
    query2 = f'select id from AssetVersion where asset.id is "{asset_id}"'
    print(f"Query: {query2}")
    
    for i in range(3):
        start = time.time()
        try:
            result2 = session.query(query2).all()
            elapsed = time.time() - start
            version_ids2 = [v['id'] for v in result2]
            # Sort manually
            versions2 = [session.get('AssetVersion', vid) for vid in version_ids2]
            versions2.sort(key=lambda v: v.get('version', 0), reverse=True)
            version_ids2_sorted = [v['id'] for v in versions2]
            
            results.append({
                'test': 'Without order by',
                'run': i + 1,
                'time_ms': elapsed * 1000,
                'count': len(version_ids2),
                'success': True
            })
            print(f"  Run {i+1}: {elapsed*1000:.2f}ms ({len(version_ids2)} versions)")
        except Exception as e:
            results.append({
                'test': 'Without order by',
                'run': i + 1,
                'time_ms': 0,
                'success': False,
                'error': str(e)
            })
            print(f"  Run {i+1}: FAILED - {e}")
    
    # Test 3: Query with limit (if we only need recent versions)
    print("\n" + "=" * 80)
    print("TEST 3: Query with limit 50")
    print("=" * 80)
    query3 = f'select id from AssetVersion where asset.id is "{asset_id}" order by version desc limit 50'
    print(f"Query: {query3}")
    
    for i in range(3):
        start = time.time()
        try:
            result3 = session.query(query3).all()
            elapsed = time.time() - start
            version_ids3 = [v['id'] for v in result3]
            results.append({
                'test': 'With limit 50',
                'run': i + 1,
                'time_ms': elapsed * 1000,
                'count': len(version_ids3),
                'success': True
            })
            print(f"  Run {i+1}: {elapsed*1000:.2f}ms ({len(version_ids3)} versions)")
        except Exception as e:
            results.append({
                'test': 'With limit 50',
                'run': i + 1,
                'time_ms': 0,
                'success': False,
                'error': str(e)
            })
            print(f"  Run {i+1}: FAILED - {e}")
    
    # Test 4: Get asset first, then query versions
    print("\n" + "=" * 80)
    print("TEST 4: Get asset first, then query via relationship")
    print("=" * 80)
    
    for i in range(3):
        start = time.time()
        try:
            asset_entity = session.get('Asset', asset_id)
            # Try to access versions via relationship
            versions4 = asset_entity.get('versions', [])
            elapsed = time.time() - start
            version_ids4 = [v['id'] for v in versions4] if versions4 else []
            
            results.append({
                'test': 'Via asset relationship',
                'run': i + 1,
                'time_ms': elapsed * 1000,
                'count': len(version_ids4),
                'success': True
            })
            print(f"  Run {i+1}: {elapsed*1000:.2f}ms ({len(version_ids4)} versions)")
        except Exception as e:
            results.append({
                'test': 'Via asset relationship',
                'run': i + 1,
                'time_ms': 0,
                'success': False,
                'error': str(e)
            })
            print(f"  Run {i+1}: FAILED - {e}")
    
    # Test 5: Query with minimal fields (id + version for sorting)
    print("\n" + "=" * 80)
    print("TEST 5: Query with id + version (for sorting)")
    print("=" * 80)
    query5 = f'select id, version from AssetVersion where asset.id is "{asset_id}" order by version desc'
    print(f"Query: {query5}")
    
    for i in range(3):
        start = time.time()
        try:
            result5 = session.query(query5).all()
            elapsed = time.time() - start
            version_ids5 = [v['id'] for v in result5]
            results.append({
                'test': 'id + version',
                'run': i + 1,
                'time_ms': elapsed * 1000,
                'count': len(version_ids5),
                'success': True
            })
            print(f"  Run {i+1}: {elapsed*1000:.2f}ms ({len(version_ids5)} versions)")
        except Exception as e:
            results.append({
                'test': 'id + version',
                'run': i + 1,
                'time_ms': 0,
                'success': False,
                'error': str(e)
            })
            print(f"  Run {i+1}: FAILED - {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    # Group by test
    test_groups = {}
    for r in results:
        if r['success']:
            test_name = r['test']
            if test_name not in test_groups:
                test_groups[test_name] = []
            test_groups[test_name].append(r['time_ms'])
    
    print("\nAverage times per test (3 runs):")
    print("-" * 80)
    
    avg_times = []
    for test_name, times in test_groups.items():
        avg_time = sum(times) / len(times) if times else 0
        min_time = min(times) if times else 0
        max_time = max(times) if times else 0
        avg_times.append((test_name, avg_time, min_time, max_time))
        print(f"{test_name:25s}: avg {avg_time:8.2f}ms (min: {min_time:6.2f}ms, max: {max_time:6.2f}ms)")
    
    if avg_times:
        avg_times.sort(key=lambda x: x[1])
        fastest = avg_times[0]
        slowest = avg_times[-1]
        
        print("\n" + "-" * 80)
        print(f"Fastest: {fastest[0]} ({fastest[1]:.2f}ms)")
        print(f"Slowest: {slowest[0]} ({slowest[1]:.2f}ms)")
        
        if fastest[1] > 0:
            speedup = slowest[1] / fastest[1]
            print(f"Speedup: {speedup:.2f}x faster")
    
    print("=" * 80)
    
    # Cleanup
    try:
        session.close()
    except Exception:
        pass


def main():
    """Main entry point."""
    # Default test asset ID
    asset_id = "a96dc802-4c14-4867-bff8-b1786b014f15"
    
    if len(sys.argv) >= 2:
        asset_id = sys.argv[1]
    
    # Bootstrap environment
    project_root = Path(__file__).resolve().parent
    _bootstrap_environment(project_root)
    
    # Check credentials
    required_vars = ['FTRACK_SERVER', 'FTRACK_API_KEY', 'FTRACK_API_USER']
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        print(f"[ERROR] Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)
    
    # Run tests
    try:
        test_query_optimization(asset_id)
    except KeyboardInterrupt:
        print("\n[INFO] Test interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
