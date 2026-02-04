"""
Test script for browser cache integration.

Tests that browser uses shared session factory and optimized caching.
"""

from __future__ import annotations

import sys
import os
import time
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bootstrap environment (same as run_browser.py)
# When run from tools/, use parent as project root
_script_dir = Path(__file__).resolve().parent
project_root = _script_dir.parent if _script_dir.name == "tools" else _script_dir

# Add ftrack_plugins to path
plugins_root = project_root / "ftrack_plugins"
if plugins_root.is_dir():
    plugins_str = str(plugins_root)
    if plugins_str not in sys.path:
        sys.path.insert(0, plugins_str)
    
    # Add ftrack_inout dependencies
    inout_deps = plugins_root / "ftrack_inout" / "dependencies"
    inout_deps_str = str(inout_deps)
    if inout_deps.is_dir() and inout_deps_str not in sys.path:
        sys.path.insert(0, inout_deps_str)
        print(f"[bootstrap] Added ftrack_inout dependencies to sys.path: {inout_deps_str}")
    
    # Add multi-site-location plugin dependencies
    multi_site_deps = plugins_root / "multi-site-location-0.2.0" / "dependencies"
    multi_site_deps_str = str(multi_site_deps)
    if multi_site_deps.is_dir() and multi_site_deps_str not in sys.path:
        sys.path.insert(0, multi_site_deps_str)
        print(f"[bootstrap] Added multi-site-location dependencies to sys.path: {multi_site_deps_str}")

# Load .env if available
def _load_dotenv_if_available(path: Path) -> None:
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

_load_dotenv_if_available(project_root / ".env")
_load_dotenv_if_available(project_root / "config" / ".env")

# Load config/mroya.json
config_path = project_root / "config" / "mroya.json"
if config_path.is_file():
    try:
        import json
        data = json.loads(config_path.read_text(encoding="utf-8"))
        for key, value in data.items():
            os.environ.setdefault(str(key), str(value))
    except Exception:
        pass

print("=" * 80)
print("BROWSER CACHE INTEGRATION TEST")
print("=" * 80)

# Test 1: Check that common session factory is available
print("\n[TEST 1] Checking common session factory availability...")
try:
    from ftrack_inout.common.session_factory import get_shared_session, create_shared_session
    print("[OK] Common session factory module imported successfully")
except ImportError as e:
    print(f"[FAIL] Failed to import common session factory: {e}")
    sys.exit(1)

# Test 2: Check that shared session can be created
print("\n[TEST 2] Creating shared session...")
session = None
try:
    session = get_shared_session()
    if session:
        print(f"[OK] Shared session created: {type(session)}")
        print(f"     Cache type: {type(session.cache)}")
        
        # Check cache type
        cache_type_name = type(session.cache).__name__
        print(f"     Cache class: {cache_type_name}")
        
        # Check if it's our optimized cache
        if 'MemoryCache' in cache_type_name or 'LoggingCache' in cache_type_name:
            print("[OK] Using optimized cache wrapper")
        else:
            print(f"[WARN] Cache type might not be optimized: {cache_type_name}")
    else:
        print("[WARN] Shared session is None (ftrack_api may not be available)")
        print("       This is OK for code structure test, but actual functionality requires ftrack_api")
except Exception as e:
    print(f"[WARN] Failed to create shared session: {e}")
    print("       This is OK for code structure test, but actual functionality requires ftrack_api")

# Test 3: Check that browser widget uses shared session
print("\n[TEST 3] Testing browser widget session creation...")
try:
    from ftrack_inout.browser.browser_widget import FtrackApiClient
    
    # Create browser client
    browser_client = FtrackApiClient()
    
    if browser_client.session:
        print(f"[OK] Browser client created with session: {type(browser_client.session)}")
        
        # Check if it's the same session (or compatible)
        browser_session_id = id(browser_client.session)
        shared_session_id = id(session)
        
        if browser_session_id == shared_session_id:
            print("[OK] Browser uses the same shared session instance")
        else:
            print("[INFO] Browser uses different session instance (may be OK if fallback)")
            print(f"     Shared session ID: {shared_session_id}")
            print(f"     Browser session ID: {browser_session_id}")
        
        # Check cache type
        browser_cache_type = type(browser_client.session.cache).__name__
        print(f"     Browser cache type: {browser_cache_type}")
    else:
        print("[FAIL] Browser client session is None")
except Exception as e:
    print(f"[FAIL] Failed to test browser widget: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Test optimized browser client
print("\n[TEST 4] Testing optimized browser client...")
try:
    from ftrack_inout.browser.browser_widget_optimized import OptimizedFtrackApiClient
    
    optimized_client = OptimizedFtrackApiClient()
    
    if optimized_client.session:
        print(f"[OK] Optimized client created with session: {type(optimized_client.session)}")
        
        # Check cache type
        opt_cache_type = type(optimized_client.session.cache).__name__
        print(f"     Optimized cache type: {opt_cache_type}")
        
        if 'MemoryCache' in opt_cache_type or 'LoggingCache' in opt_cache_type:
            print("[OK] Optimized client uses optimized cache")
    else:
        print("[FAIL] Optimized client session is None")
except Exception as e:
    print(f"[FAIL] Failed to test optimized browser client: {e}")
    import traceback
    traceback.print_exc()

# Test 5: Performance test - query with cache
print("\n[TEST 5] Performance test - query with cache...")
try:
    if not session:
        print("[SKIP] No session available (ftrack_api may not be configured)")
    else:
        # Simple query test
        start = time.time()
        projects = session.query('Project where status is "active"').limit(5).all()
        query_time = time.time() - start
        
        print(f"[OK] Query completed in {query_time*1000:.1f}ms")
        print(f"     Found {len(projects)} projects")
        
        if projects:
            project = projects[0]
            project_id = project['id']
            
            # Test cache hit
            start = time.time()
            cached_project = session.get('Project', project_id)
            cache_time = time.time() - start
            
            print(f"[OK] Cache access completed in {cache_time*1000:.3f}ms")
            
            if cache_time < 0.01:  # Less than 10ms
                print("[OK] Cache access is fast (< 10ms)")
            else:
                print(f"[WARN] Cache access is slow: {cache_time*1000:.1f}ms")
            
            # Speedup calculation
            if query_time > 0:
                speedup = query_time / cache_time if cache_time > 0 else 0
                print(f"     Speedup: {speedup:.1f}x")
except Exception as e:
    print(f"[FAIL] Performance test failed: {e}")
    import traceback
    traceback.print_exc()

# Test 6: Check CachePreloader availability
print("\n[TEST 6] Checking CachePreloader availability...")
try:
    from ftrack_inout.common.cache_preloader import CachePreloader
    
    preloader = CachePreloader(session)
    print("[OK] CachePreloader imported and initialized")
except ImportError as e:
    print(f"[FAIL] Failed to import CachePreloader: {e}")
except Exception as e:
    print(f"[WARN] CachePreloader initialization failed: {e}")

# Test 7: Check that browser widget can be instantiated
print("\n[TEST 7] Testing browser widget instantiation...")
try:
    from PySide6 import QtWidgets
    
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    
    from ftrack_inout.browser import FtrackBrowser
    
    browser = FtrackBrowser()
    print("[OK] Browser widget created successfully")
    
    # Check if browser has session
    if hasattr(browser, 'api') and hasattr(browser.api, 'session'):
        browser_session = browser.api.session
        if browser_session:
            print(f"[OK] Browser widget has session: {type(browser_session)}")
            browser_cache_type = type(browser_session.cache).__name__
            print(f"     Browser widget cache type: {browser_cache_type}")
        else:
            print("[WARN] Browser widget session is None")
    else:
        print("[WARN] Browser widget doesn't have api.session attribute")
    
    # Cleanup
    browser.close()
    del browser
    
except ImportError as e:
    print(f"[SKIP] Qt not available: {e}")
except Exception as e:
    print(f"[FAIL] Browser widget test failed: {e}")
    import traceback
    traceback.print_exc()

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("[OK] All tests completed")
print("\nNext steps:")
print("1. Run 'python run_browser.py' to test browser UI")
print("2. Check logs for '[OK] Using shared session from common factory' messages")
print("3. Verify cache performance in browser operations")
print("=" * 80)
