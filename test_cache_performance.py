"""
Performance test script for Ftrack cache optimization.

Tests speed of various operations on a specific asset with many versions/components.
Uses the same credentials and bootstrap as run_browser.py.

Usage:
    python test_cache_performance.py <asset_id>

Example:
    python test_cache_performance.py a96dc802-4c14-4867-bff8-b1786b014f15
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
    """Initialize environment (same as run_browser.py)."""
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


def test_asset_performance(asset_id: str):
    """Test performance of various operations on a specific asset."""
    
    print("=" * 80)
    print(f"PERFORMANCE TEST for Asset ID: {asset_id}")
    print("=" * 80)
    
    # Import after bootstrap
    try:
        import ftrack_api
        from ftrack_inout.common.session_factory import create_shared_session, reset_shared_session
        from ftrack_inout.common.cache_preloader import CachePreloader
        from ftrack_inout.browser.browser_widget_optimized import OptimizedFtrackApiClient
    except ImportError as e:
        print(f"[ERROR] Failed to import required modules: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Reset session to start fresh
    reset_shared_session()
    
    # Test 1: Create session with optimized cache
    print("\n[TEST 1] Creating session with optimized cache...")
    start = time.time()
    session = create_shared_session()
    if not session:
        print("[ERROR] Failed to create session")
        return
    
    session_time = time.time() - start
    print(f"[OK] Session created in {session_time*1000:.1f}ms")
    
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
    
    # Test 2: Query for version IDs (fast)
    print("\n[TEST 2] Query for version IDs only...")
    start = time.time()
    version_ids_query = session.query(
        f'select id from AssetVersion where asset.id is "{asset_id}" order by version desc'
    ).all()
    query_time = time.time() - start
    version_ids = [v['id'] for v in version_ids_query]
    print(f"[OK] Found {len(version_ids)} versions in {query_time*1000:.1f}ms")
    print(f"      Speed: {len(version_ids)/query_time:.1f} versions/sec")
    
    if not version_ids:
        print("[WARNING] No versions found for this asset")
        return
    
    # Test 3: Batch get versions (first time - cache miss)
    print("\n[TEST 3] Batch get versions (first time - cache miss)...")
    start = time.time()
    versions_first = []
    for version_id in version_ids[:min(50, len(version_ids))]:  # Limit to 50 for test
        try:
            version = session.get('AssetVersion', version_id)
            if version:
                versions_first.append(version)
        except Exception as e:
            print(f"[WARNING] Failed to get version {version_id}: {e}")
    
    batch_time_first = time.time() - start
    print(f"[OK] Loaded {len(versions_first)} versions in {batch_time_first*1000:.1f}ms")
    print(f"      Speed: {len(versions_first)/batch_time_first:.1f} versions/sec")
    print(f"      Avg per version: {batch_time_first/len(versions_first)*1000:.1f}ms")
    
    # Test 4: Batch get versions (second time - cache hit)
    print("\n[TEST 4] Batch get versions (second time - cache hit)...")
    start = time.time()
    versions_second = []
    for version_id in version_ids[:min(50, len(version_ids))]:
        try:
            version = session.get('AssetVersion', version_id)
            if version:
                versions_second.append(version)
        except Exception:
            pass
    
    batch_time_second = time.time() - start
    print(f"[OK] Loaded {len(versions_second)} versions in {batch_time_second*1000:.1f}ms")
    print(f"      Speed: {len(versions_second)/batch_time_second:.1f} versions/sec")
    print(f"      Avg per version: {batch_time_second/len(versions_second)*1000:.1f}ms")
    
    speedup = batch_time_first / batch_time_second if batch_time_second > 0 else 0
    print(f"      Speedup: {speedup:.1f}x faster with cache")
    
    # Test 5: Get components for first version
    if versions_first:
        first_version_id = versions_first[0]['id']
        print(f"\n[TEST 5] Getting components for version {first_version_id}...")
        
        # Query component IDs
        start = time.time()
        component_ids_query = session.query(
            f'select id from Component where version.id is "{first_version_id}"'
        ).all()
        query_comp_time = time.time() - start
        component_ids = [c['id'] for c in component_ids_query]
        print(f"[OK] Found {len(component_ids)} component IDs in {query_comp_time*1000:.1f}ms")
        
        if component_ids:
            # Batch get components (first time)
            start = time.time()
            components_first = []
            for comp_id in component_ids[:min(20, len(component_ids))]:  # Limit to 20
                try:
                    component = session.get('Component', comp_id)
                    if component:
                        components_first.append(component)
                except Exception:
                    pass
            
            batch_comp_time_first = time.time() - start
            print(f"[OK] Loaded {len(components_first)} components in {batch_comp_time_first*1000:.1f}ms")
            print(f"      Speed: {len(components_first)/batch_comp_time_first:.1f} components/sec")
            
            # Batch get components (second time - cache hit)
            start = time.time()
            components_second = []
            for comp_id in component_ids[:min(20, len(component_ids))]:
                try:
                    component = session.get('Component', comp_id)
                    if component:
                        components_second.append(component)
                except Exception:
                    pass
            
            batch_comp_time_second = time.time() - start
            print(f"[OK] Loaded {len(components_second)} components in {batch_comp_time_second*1000:.1f}ms")
            print(f"      Speed: {len(components_second)/batch_comp_time_second:.1f} components/sec")
            
            speedup_comp = batch_comp_time_first / batch_comp_time_second if batch_comp_time_second > 0 else 0
            print(f"      Speedup: {speedup_comp:.1f}x faster with cache")
    
    # Test 6: Using OptimizedFtrackApiClient
    print("\n[TEST 6] Using OptimizedFtrackApiClient.get_versions_for_asset()...")
    try:
        client = OptimizedFtrackApiClient()
        start = time.time()
        versions_api = client.get_versions_for_asset(asset_id)
        api_time = time.time() - start
        print(f"[OK] Loaded {len(versions_api)} versions in {api_time*1000:.1f}ms")
        print(f"      Speed: {len(versions_api)/api_time:.1f} versions/sec")
    except Exception as e:
        print(f"[ERROR] OptimizedFtrackApiClient failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 7: Cache preloader
    print("\n[TEST 7] Using CachePreloader.preload_asset_data()...")
    try:
        preloader = CachePreloader(session)
        start = time.time()
        result = preloader.preload_asset_data(asset_id, max_versions=50)
        preload_time = time.time() - start
        if result.get('success'):
            print(f"[OK] Preloaded {result.get('loaded_count', 0)} entities in {preload_time*1000:.1f}ms")
            print(f"      Speed: {result.get('loaded_count', 0)/preload_time:.1f} entities/sec")
            print(f"      Avg access time: {result.get('avg_access_time_ms', 0):.1f}ms")
        else:
            print(f"[WARNING] Preload failed: {result.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"[ERROR] CachePreloader failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 8: Refresh comparison (force_refresh=False vs True)
    print("\n[TEST 8] Testing refresh comparison...")
    try:
        client = OptimizedFtrackApiClient()
        
        # Test without refresh (uses cache)
        print("  [8.1] Without refresh (uses cache)...")
        start = time.time()
        versions_normal = client.get_versions_for_asset(asset_id, force_refresh=False)
        normal_time = time.time() - start
        print(f"        Loaded {len(versions_normal)} versions in {normal_time*1000:.1f}ms")
        print(f"        Speed: {len(versions_normal)/normal_time:.1f} versions/sec")
        
        # Test with refresh (forces populate)
        print("  [8.2] With force_refresh=True (forces populate)...")
        start = time.time()
        versions_refresh = client.get_versions_for_asset(asset_id, force_refresh=True)
        refresh_time = time.time() - start
        print(f"        Refreshed {len(versions_refresh)} versions in {refresh_time*1000:.1f}ms")
        print(f"        Speed: {len(versions_refresh)/refresh_time:.1f} versions/sec")
        
        # Compare
        if normal_time > 0 and refresh_time > 0:
            overhead = refresh_time - normal_time
            overhead_percent = (overhead / normal_time) * 100 if normal_time > 0 else 0
            print(f"  [COMPARE] Refresh overhead: {overhead*1000:.1f}ms ({overhead_percent:.1f}% slower)")
            
            # Check if data is different (metadata might have changed)
            if len(versions_normal) == len(versions_refresh):
                print(f"  [COMPARE] Same number of versions: {len(versions_normal)}")
            else:
                print(f"  [COMPARE] Version count changed: {len(versions_normal)} -> {len(versions_refresh)}")
        
    except Exception as e:
        print(f"[ERROR] Refresh test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 9: Component refresh test
    if versions_first:
        first_version_id = versions_first[0]['id']
        print(f"\n[TEST 9] Testing component refresh for version {first_version_id}...")
        try:
            client = OptimizedFtrackApiClient()
            
            # Without refresh
            print("  [9.1] Getting components without refresh...")
            start = time.time()
            components_normal = client.get_components_with_paths_for_version(first_version_id, force_refresh=False)
            normal_comp_time = time.time() - start
            print(f"        Loaded {len(components_normal)} components in {normal_comp_time*1000:.1f}ms")
            
            # With refresh
            print("  [9.2] Getting components with force_refresh=True...")
            start = time.time()
            components_refresh = client.get_components_with_paths_for_version(first_version_id, force_refresh=True)
            refresh_comp_time = time.time() - start
            print(f"        Refreshed {len(components_refresh)} components in {refresh_comp_time*1000:.1f}ms")
            
            # Compare
            if normal_comp_time > 0 and refresh_comp_time > 0:
                overhead_comp = refresh_comp_time - normal_comp_time
                overhead_comp_percent = (overhead_comp / normal_comp_time) * 100 if normal_comp_time > 0 else 0
                print(f"  [COMPARE] Component refresh overhead: {overhead_comp*1000:.1f}ms ({overhead_comp_percent:.1f}% slower)")
                
                # Compare paths (they might differ if component was transferred)
                if components_normal and components_refresh:
                    paths_normal = [c.get('path', '') for c in components_normal]
                    paths_refresh = [c.get('path', '') for c in components_refresh]
                    if paths_normal != paths_refresh:
                        print(f"  [COMPARE] ⚠️  Paths differ - component may have been transferred!")
                        for i, (p1, p2) in enumerate(zip(paths_normal[:3], paths_refresh[:3])):
                            if p1 != p2:
                                print(f"        Component {i}: '{p1}' -> '{p2}'")
                    else:
                        print(f"  [COMPARE] ✓ Paths are identical")
        
        except Exception as e:
            print(f"[ERROR] Component refresh test failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Asset: {asset_name} ({asset_id})")
    print(f"Total versions: {len(version_ids)}")
    print(f"\nTimings:")
    print(f"  Query IDs:        {query_time*1000:.1f}ms")
    print(f"  Batch get (cold): {batch_time_first*1000:.1f}ms ({len(versions_first)} versions)")
    print(f"  Batch get (hot):  {batch_time_second*1000:.1f}ms ({len(versions_second)} versions)")
    print(f"  Cache speedup:    {speedup:.1f}x")
    
    # Refresh comparison summary
    try:
        if 'normal_time' in locals() and 'refresh_time' in locals():
            print(f"\nRefresh Comparison:")
            print(f"  Normal (cache):  {normal_time*1000:.1f}ms")
            print(f"  Refresh (populate): {refresh_time*1000:.1f}ms")
            if normal_time > 0:
                overhead = refresh_time - normal_time
                print(f"  Overhead:       {overhead*1000:.1f}ms ({(overhead/normal_time)*100:.1f}% slower)")
    except:
        pass
    
    print("=" * 80)
    
    # Cleanup
    try:
        session.close()
    except Exception:
        pass


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python test_cache_performance.py <asset_id>")
        print("\nExample:")
        print("  python test_cache_performance.py a96dc802-4c14-4867-bff8-b1786b014f15")
        sys.exit(1)
    
    asset_id = sys.argv[1]
    
    # Bootstrap environment (same as run_browser.py)
    project_root = Path(__file__).resolve().parent
    _bootstrap_environment(project_root)
    
    # Check credentials
    required_vars = ['FTRACK_SERVER', 'FTRACK_API_KEY', 'FTRACK_API_USER']
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        print(f"[ERROR] Missing required environment variables: {', '.join(missing)}")
        print("\nPlease set them in:")
        print("  - .env file")
        print("  - config/.env file")
        print("  - config/mroya.json")
        print("  - Environment variables")
        sys.exit(1)
    
    # Run tests
    try:
        test_asset_performance(asset_id)
    except KeyboardInterrupt:
        print("\n[INFO] Test interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
