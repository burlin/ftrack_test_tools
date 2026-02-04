"""
Test script for debugging get_versions_for_asset() performance.

Tests each step of the method separately to find bottlenecks.
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


def test_get_versions_performance(asset_id: str, force_refresh: bool = True):
    """Test get_versions_for_asset() performance step by step."""
    
    print("=" * 80)
    print(f"TESTING get_versions_for_asset() PERFORMANCE")
    print(f"Asset ID: {asset_id}")
    print(f"Force refresh: {force_refresh}")
    print("=" * 80)
    
    # Import after bootstrap
    try:
        import ftrack_api
        from ftrack_inout.common.session_factory import create_shared_session, reset_shared_session
        from ftrack_inout.browser.browser_widget_optimized import OptimizedFtrackApiClient
    except ImportError as e:
        print(f"[ERROR] Failed to import required modules: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Reset session to start fresh
    reset_shared_session()
    
    # Create session and client
    print("\n[SETUP] Creating session and client...")
    session = create_shared_session()
    if not session:
        print("[ERROR] Failed to create session")
        return
    
    client = OptimizedFtrackApiClient()
    print("[OK] Session and client created")
    
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
    
    results = {}
    total_start = time.time()
    
    # STEP 1: Query for version IDs
    print("\n" + "=" * 80)
    print("STEP 1: Query for version IDs")
    print("=" * 80)
    step1_start = time.time()
    try:
        version_ids_query = session.query(
            f'select id from AssetVersion where asset.id is "{asset_id}" order by version desc'
        ).all()
        step1_time = time.time() - step1_start
        version_ids = [v['id'] for v in version_ids_query]
        results['step1_query'] = {
            'time_ms': step1_time * 1000,
            'count': len(version_ids),
            'success': True
        }
        print(f"[OK] Found {len(version_ids)} versions in {step1_time*1000:.2f}ms")
        print(f"      Speed: {len(version_ids)/step1_time:.1f} versions/sec")
    except Exception as e:
        results['step1_query'] = {'time_ms': 0, 'success': False, 'error': str(e)}
        print(f"[FAIL] Query failed: {e}")
        return
    
    if not version_ids:
        print("[WARNING] No versions found")
        return
    
    # STEP 2: Check cache status
    print("\n" + "=" * 80)
    print("STEP 2: Check cache status")
    print("=" * 80)
    step2_start = time.time()
    cached_count = 0
    try:
        # Simulate cache check (simplified - actual implementation may differ)
        for version_id in version_ids:
            # Try to get from cache
            try:
                version = session.get('AssetVersion', version_id)
                if version and hasattr(version, '_cache_key'):
                    cached_count += 1
            except:
                pass
        step2_time = time.time() - step2_start
        results['step2_cache_check'] = {
            'time_ms': step2_time * 1000,
            'cached_count': cached_count,
            'total_count': len(version_ids),
            'success': True
        }
        print(f"[OK] Cache check: {cached_count}/{len(version_ids)} cached in {step2_time*1000:.2f}ms")
    except Exception as e:
        results['step2_cache_check'] = {'time_ms': 0, 'success': False, 'error': str(e)}
        print(f"[FAIL] Cache check failed: {e}")
    
    # STEP 3: Batch get versions (session.get for each)
    print("\n" + "=" * 80)
    print("STEP 3: Batch get versions (session.get for each)")
    print("=" * 80)
    step3_start = time.time()
    versions_entities = []
    get_times = []
    try:
        for i, version_id in enumerate(version_ids):
            item_start = time.time()
            try:
                version = session.get('AssetVersion', version_id)
                item_time = time.time() - item_start
                get_times.append(item_time * 1000)
                if version:
                    versions_entities.append(version)
            except Exception as e:
                print(f"[WARNING] Failed to get version {version_id[:8]}...: {e}")
                continue
        
        step3_time = time.time() - step3_start
        avg_get_time = sum(get_times) / len(get_times) if get_times else 0
        max_get_time = max(get_times) if get_times else 0
        min_get_time = min(get_times) if get_times else 0
        
        results['step3_batch_get'] = {
            'time_ms': step3_time * 1000,
            'count': len(versions_entities),
            'avg_per_version_ms': avg_get_time,
            'min_ms': min_get_time,
            'max_ms': max_get_time,
            'success': True
        }
        print(f"[OK] Loaded {len(versions_entities)}/{len(version_ids)} versions in {step3_time*1000:.2f}ms")
        print(f"      Avg per version: {avg_get_time:.3f}ms")
        print(f"      Min: {min_get_time:.3f}ms, Max: {max_get_time:.3f}ms")
        print(f"      Speed: {len(versions_entities)/step3_time:.1f} versions/sec")
    except Exception as e:
        results['step3_batch_get'] = {'time_ms': 0, 'success': False, 'error': str(e)}
        print(f"[FAIL] Batch get failed: {e}")
        return
    
    # STEP 4: Populate (if force_refresh)
    if force_refresh and versions_entities:
        print("\n" + "=" * 80)
        print("STEP 4: Populate (refresh metadata)")
        print("=" * 80)
        step4_start = time.time()
        try:
            session.populate(versions_entities, 'date, comment')
            step4_time = time.time() - step4_start
            results['step4_populate'] = {
                'time_ms': step4_time * 1000,
                'count': len(versions_entities),
                'success': True
            }
            print(f"[OK] Populated {len(versions_entities)} versions in {step4_time*1000:.2f}ms")
            print(f"      Speed: {len(versions_entities)/step4_time:.1f} versions/sec")
        except Exception as e:
            results['step4_populate'] = {'time_ms': 0, 'success': False, 'error': str(e)}
            print(f"[FAIL] Populate failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        results['step4_populate'] = {'time_ms': 0, 'skipped': True}
        print("\n[SKIP] Step 4: Populate skipped (force_refresh=False)")
    
    # STEP 5: Convert entities to result format
    print("\n" + "=" * 80)
    print("STEP 5: Convert entities to result format")
    print("=" * 80)
    step5_start = time.time()
    result_list = []
    conversion_times = []
    try:
        for i, version in enumerate(versions_entities):
            conv_start = time.time()
            try:
                # Convert to same format as get_asset_versions
                user_data = version.get('user')
                user_first_name = 'Unknown'
                user_last_name = 'User'
                user_username = ''
                
                if user_data:
                    if isinstance(user_data, dict):
                        user_first_name = user_data.get('first_name', 'Unknown')
                        user_last_name = user_data.get('last_name', 'User')
                        user_username = user_data.get('username', '')
                    else:
                        try:
                            user_first_name = user_data.get('first_name', 'Unknown')
                            user_last_name = user_data.get('last_name', 'User')
                            user_username = user_data.get('username', '')
                        except:
                            user_first_name = 'Unknown'
                            user_last_name = 'User'
                
                # Build full name
                full_name = f"{user_first_name} {user_last_name}".strip()
                if not full_name or full_name == 'Unknown User':
                    full_name = user_username or 'Unknown User'
                
                version_data = {
                    'id': version['id'],
                    'version': version['version'],
                    'comment': version.get('comment', ''),
                    'date': version.get('date'),
                    'user': {
                        'first_name': user_first_name, 
                        'last_name': user_last_name,
                        'username': user_username,
                        'full_name': full_name
                    },
                    'asset': {'id': asset_id, 'name': asset_name}
                }
                
                result_list.append(version_data)
                conv_time = time.time() - conv_start
                conversion_times.append(conv_time * 1000)
            except Exception as e:
                print(f"[WARNING] Failed to convert version {i}: {e}")
                continue
        
        step5_time = time.time() - step5_start
        avg_conv_time = sum(conversion_times) / len(conversion_times) if conversion_times else 0
        max_conv_time = max(conversion_times) if conversion_times else 0
        min_conv_time = min(conversion_times) if conversion_times else 0
        
        results['step5_conversion'] = {
            'time_ms': step5_time * 1000,
            'count': len(result_list),
            'avg_per_version_ms': avg_conv_time,
            'min_ms': min_conv_time,
            'max_ms': max_conv_time,
            'success': True
        }
        print(f"[OK] Converted {len(result_list)} versions in {step5_time*1000:.2f}ms")
        print(f"      Avg per version: {avg_conv_time:.3f}ms")
        print(f"      Min: {min_conv_time:.3f}ms, Max: {max_conv_time:.3f}ms")
        print(f"      Speed: {len(result_list)/step5_time:.1f} versions/sec")
    except Exception as e:
        results['step5_conversion'] = {'time_ms': 0, 'success': False, 'error': str(e)}
        print(f"[FAIL] Conversion failed: {e}")
        import traceback
        traceback.print_exc()
    
    # STEP 6: Full method call (for comparison)
    print("\n" + "=" * 80)
    print("STEP 6: Full method call (for comparison)")
    print("=" * 80)
    step6_start = time.time()
    try:
        full_result = client.get_versions_for_asset(asset_id, force_refresh=force_refresh)
        step6_time = time.time() - step6_start
        results['step6_full_method'] = {
            'time_ms': step6_time * 1000,
            'count': len(full_result) if full_result else 0,
            'success': True
        }
        print(f"[OK] Full method returned {len(full_result) if full_result else 0} versions in {step6_time*1000:.2f}ms")
    except Exception as e:
        results['step6_full_method'] = {'time_ms': 0, 'success': False, 'error': str(e)}
        print(f"[FAIL] Full method failed: {e}")
        import traceback
        traceback.print_exc()
    
    total_time = time.time() - total_start
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Asset: {asset_name} ({asset_id})")
    print(f"Total versions: {len(version_ids)}")
    print(f"Force refresh: {force_refresh}")
    print(f"\nStep-by-step timings:")
    print("-" * 80)
    
    step_names = {
        'step1_query': '1. Query IDs',
        'step2_cache_check': '2. Cache check',
        'step3_batch_get': '3. Batch get',
        'step4_populate': '4. Populate',
        'step5_conversion': '5. Conversion',
        'step6_full_method': '6. Full method'
    }
    
    total_manual = 0
    for step_key, step_name in step_names.items():
        if step_key in results and results[step_key].get('success'):
            step_time = results[step_key]['time_ms']
            total_manual += step_time
            print(f"{step_name:20s}: {step_time:8.2f}ms", end="")
            if step_key == 'step3_batch_get' and 'avg_per_version_ms' in results[step_key]:
                print(f" (avg: {results[step_key]['avg_per_version_ms']:.3f}ms/version)")
            elif step_key == 'step5_conversion' and 'avg_per_version_ms' in results[step_key]:
                print(f" (avg: {results[step_key]['avg_per_version_ms']:.3f}ms/version)")
            else:
                print()
        elif step_key in results and results[step_key].get('skipped'):
            print(f"{step_name:20s}: {'SKIPPED':>8s}")
        elif step_key in results:
            print(f"{step_name:20s}: {'FAILED':>8s} - {results[step_key].get('error', 'Unknown')}")
    
    print("-" * 80)
    print(f"{'Manual total':20s}: {total_manual:8.2f}ms")
    print(f"{'Full method':20s}: {results.get('step6_full_method', {}).get('time_ms', 0):8.2f}ms")
    print(f"{'Total elapsed':20s}: {total_time*1000:8.2f}ms")
    
    # Find bottleneck
    print("\n" + "=" * 80)
    print("BOTTLENECK ANALYSIS")
    print("=" * 80)
    
    step_times = []
    for step_key, step_name in step_names.items():
        if step_key in results and results[step_key].get('success'):
            step_times.append((step_name, results[step_key]['time_ms']))
    
    if step_times:
        step_times.sort(key=lambda x: x[1], reverse=True)
        print("Steps sorted by time (slowest first):")
        for i, (name, t) in enumerate(step_times, 1):
            percentage = (t / total_manual * 100) if total_manual > 0 else 0
            print(f"{i}. {name:20s}: {t:8.2f}ms ({percentage:5.1f}%)")
        
        if len(step_times) > 1:
            slowest = step_times[0]
            fastest = step_times[-1]
            if slowest[1] > 0:
                ratio = slowest[1] / fastest[1] if fastest[1] > 0 else 0
                print(f"\nSlowest step ({slowest[0]}) is {ratio:.1f}x slower than fastest ({fastest[0]})")
    
    print("=" * 80)
    
    # Cleanup
    try:
        session.close()
    except Exception:
        pass


def main():
    """Main entry point."""
    # Default test asset ID (from heavy_seq)
    asset_id = "a96dc802-4c14-4867-bff8-b1786b014f15"
    force_refresh = True
    
    if len(sys.argv) >= 2:
        asset_id = sys.argv[1]
    if len(sys.argv) >= 3:
        force_refresh = sys.argv[2].lower() in ('true', '1', 'yes')
    
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
        test_get_versions_performance(asset_id, force_refresh)
    except KeyboardInterrupt:
        print("\n[INFO] Test interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
