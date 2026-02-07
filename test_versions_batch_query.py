"""
Test batch query vs current approach for loading asset versions.

Compares:
1. Current: query IDs (1 request) + N session.get() (N requests) + populate
2. Batch query: ONE query with full projections - single request, no session.get() loop
3. Only new versions: relationship gives cached IDs, query gives all, fetch only new ones

Note: Batch query / only-new approach may skip populate - we get fresh version list
but lose metadata refresh (date, comment). Component status (component_locations)
is separate - that's for components, not versions.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

# Suppress verbose ftrack logs for cleaner output
logging.getLogger("ftrack").setLevel(logging.WARNING)
logging.getLogger("ftrack_inout").setLevel(logging.WARNING)

# Compatibility: imp module stub for Python 3.12+
if sys.version_info >= (3, 12) and 'imp' not in sys.modules:
    import types
    class ImpModule:
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
    sys.modules['imp'] = ImpModule()


def _load_dotenv_if_available(path: Path) -> None:
    """Load .env file if available."""
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=str(path))
    except Exception:
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

    config_path = project_root / "config" / "mroya.json"
    if config_path.is_file():
        try:
            data: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
            for key, value in data.items():
                os.environ.setdefault(str(key), str(value))
        except Exception:
            pass

    plugins_root = project_root / "ftrack_plugins"
    if plugins_root.is_dir():
        os.environ.setdefault("FTRACK_CONNECT_PLUGIN_PATH", str(plugins_root))
        if str(plugins_root) not in sys.path:
            sys.path.insert(0, str(plugins_root))
        inout_deps = plugins_root / "ftrack_inout" / "dependencies"
        if inout_deps.is_dir() and str(inout_deps) not in sys.path:
            sys.path.insert(0, str(inout_deps))
        multi_site_deps = plugins_root / "multi-site-location-0.2.0" / "dependencies"
        if multi_site_deps.is_dir() and str(multi_site_deps) not in sys.path:
            sys.path.insert(0, str(multi_site_deps))


def _convert_version_to_result(version, asset_id: str, asset_name: str) -> dict:
    """Convert version entity to result format (same as browser_widget_optimized)."""
    user_data = version.get('user')
    user_first_name = 'Unknown'
    user_last_name = 'User'
    user_username = ''
    if user_data:
        try:
            if isinstance(user_data, dict):
                user_first_name = user_data.get('first_name', 'Unknown')
                user_last_name = user_data.get('last_name', 'User')
                user_username = user_data.get('username', '')
            else:
                user_first_name = user_data.get('first_name', 'Unknown')
                user_last_name = user_data.get('last_name', 'User')
                user_username = user_data.get('username', '')
        except Exception:
            pass
    full_name = f"{user_first_name} {user_last_name}".strip()
    if not full_name or full_name == 'Unknown User':
        full_name = user_username or 'Unknown User'
    return {
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


def test_batch_query(asset_id: str):
    """Test batch query vs current approach."""
    print("=" * 80)
    print("TEST: Batch Query vs Current Approach for Asset Versions")
    print("=" * 80)
    print(f"Asset ID: {asset_id}")
    print()

    try:
        from ftrack_inout.common.session_factory import create_shared_session, reset_shared_session
    except ImportError as e:
        print(f"[ERROR] Failed to import: {e}")
        return

    reset_shared_session()
    session = create_shared_session()
    if not session:
        print("[ERROR] Failed to create session")
        return

    try:
        asset = session.get('Asset', asset_id)
        if not asset:
            print(f"[ERROR] Asset {asset_id} not found")
            return
        asset_name = asset.get('name', 'Unknown')
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    results = {}

    # --- TEST 1: Current approach (query IDs + N session.get + populate) ---
    print("[TEST 1] Current: query IDs + session.get() per version + populate")
    t0 = time.time()
    try:
        version_ids_result = session.query(
            f'select id from AssetVersion where asset.id is "{asset_id}" order by version desc'
        ).all()
        version_ids = [v['id'] for v in version_ids_result]
        t_query = time.time() - t0

        t1 = time.time()
        versions_entities = []
        for vid in version_ids:
            v = session.get('AssetVersion', vid)
            if v:
                versions_entities.append(v)
        t_get = time.time() - t1

        t2 = time.time()
        if versions_entities:
            session.populate(versions_entities, 'date, comment')
        t_populate = time.time() - t2

        result_list = [_convert_version_to_result(v, asset_id, asset_name) for v in versions_entities]
        t_total = time.time() - t0

        results['current'] = {
            'time_ms': t_total * 1000,
            'query_ms': t_query * 1000,
            'get_ms': t_get * 1000,
            'populate_ms': t_populate * 1000,
            'count': len(result_list),
            'success': True
        }
        print(f"  Query: {t_query*1000:.1f}ms, Get: {t_get*1000:.1f}ms, Populate: {t_populate*1000:.1f}ms")
        print(f"  Total: {t_total*1000:.1f}ms, {len(result_list)} versions")
    except Exception as e:
        results['current'] = {'success': False, 'error': str(e)}
        print(f"  FAILED: {e}")
        import traceback
        traceback.print_exc()

    # --- TEST 2: Batch query (ONE query with full projections, no session.get loop) ---
    print("\n[TEST 2] Batch query: ONE query with id, version, date, comment, user")
    t0 = time.time()
    try:
        # Single query - returns full entities, merges into cache, no extra session.get
        batch_query = (
            f'select id, version, date, comment, user_id from AssetVersion '
            f'where asset.id is "{asset_id}" order by version desc'
        )
        versions_batch = session.query(batch_query).all()
        t_batch = time.time() - t0

        # Convert - user resolution may trigger populate for user entities
        result_list = [_convert_version_to_result(v, asset_id, asset_name) for v in versions_batch]
        t_total = time.time() - t0

        results['batch_query'] = {
            'time_ms': t_total * 1000,
            'query_only_ms': t_batch * 1000,
            'count': len(result_list),
            'success': True
        }
        print(f"  Query (single): {t_batch*1000:.1f}ms")
        print(f"  Total: {t_total*1000:.1f}ms, {len(result_list)} versions")
    except Exception as e:
        results['batch_query'] = {'success': False, 'error': str(e)}
        print(f"  FAILED: {e}")
        import traceback
        traceback.print_exc()

    # --- TEST 3: Only new versions (relationship for cached, query for all, fetch only new) ---
    print("\n[TEST 3] Only new versions: relationship -> query -> session.get only for new IDs")
    reset_shared_session()
    session2 = create_shared_session()
    if not session2:
        print("  [SKIP] Failed to create new session")
    else:
        t0 = time.time()
        try:
            # Step 1: Get "cached" IDs via relationship (simulates stale cache: 1-39)
            asset2 = session2.get('Asset', asset_id)
            versions_rel = list(asset2.get('versions', []) or [])
            versions_rel.sort(key=lambda v: v.get('version', 0), reverse=True)
            cached_ids = {v['id'] for v in versions_rel}
            t_rel = time.time() - t0

            # Step 2: Query all IDs from server (1-44)
            t1 = time.time()
            version_ids_all = [v['id'] for v in session2.query(
                f'select id from AssetVersion where asset.id is "{asset_id}" order by version desc'
            ).all()]
            t_query = time.time() - t1

            # Step 3: Only fetch versions NOT in "cache"
            new_ids = [vid for vid in version_ids_all if vid not in cached_ids]
            t2 = time.time()
            new_entities = []
            for vid in new_ids:
                v = session2.get('AssetVersion', vid)
                if v:
                    new_entities.append(v)
            t_get_new = time.time() - t2

            # Build result: cached entities + new entities (merge by version order)
            all_entities = versions_rel + new_entities
            all_entities.sort(key=lambda v: v.get('version', 0), reverse=True)
            result_list = [_convert_version_to_result(v, asset_id, asset_name) for v in all_entities]
            t_total = time.time() - t0

            results['only_new'] = {
                'time_ms': t_total * 1000,
                'relationship_ms': t_rel * 1000,
                'query_ms': t_query * 1000,
                'get_new_ms': t_get_new * 1000,
                'cached_count': len(cached_ids),
                'new_count': len(new_ids),
                'count': len(result_list),
                'success': True
            }
            print(f"  Relationship: {t_rel*1000:.1f}ms ({len(cached_ids)} cached)")
            print(f"  Query: {t_query*1000:.1f}ms")
            print(f"  Get new only: {t_get_new*1000:.1f}ms ({len(new_ids)} new)")
            print(f"  Total: {t_total*1000:.1f}ms, {len(result_list)} versions")
        except Exception as e:
            results['only_new'] = {'success': False, 'error': str(e)}
            print(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()

    # --- SUMMARY ---
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if results.get('current', {}).get('success') and results.get('batch_query', {}).get('success'):
        c = results['current']
        b = results['batch_query']
        speedup = c['time_ms'] / b['time_ms'] if b['time_ms'] > 0 else 0
        print(f"\nCurrent approach:   {c['time_ms']:.1f}ms ({c['count']} versions)")
        print(f"Batch query:        {b['time_ms']:.1f}ms ({b['count']} versions)")
        if speedup > 1:
            print(f"Batch query is {speedup:.1f}x faster")
        elif speedup < 1 and speedup > 0:
            print(f"Batch query is {1/speedup:.1f}x slower")

    if results.get('only_new', {}).get('success'):
        o = results['only_new']
        print(f"\nOnly-new approach:  {o['time_ms']:.1f}ms")
        print(f"  (cached: {o.get('cached_count', 0)}, new: {o.get('new_count', 0)})")

    print("\nTrade-offs:")
    print("  - Batch query: 1 request, fresh version list. No populate -> date/comment from query.")
    print("  - Only new: Saves session.get() for cached versions. Relationship can be stale.")
    print("  - Component status (component_locations): separate, needs populate on components.")
    print("=" * 80)

    try:
        session.close()
    except Exception:
        pass


def main():
    asset_id = "a96dc802-4c14-4867-bff8-b1786b014f15"
    if len(sys.argv) >= 2:
        asset_id = sys.argv[1]

    _script_dir = Path(__file__).resolve().parent
    project_root = _script_dir.parent if _script_dir.name == "tools" else _script_dir
    _bootstrap_environment(project_root)

    required_vars = ['FTRACK_SERVER', 'FTRACK_API_KEY', 'FTRACK_API_USER']
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        print(f"[ERROR] Missing: {', '.join(missing)}")
        sys.exit(1)

    try:
        test_batch_query(asset_id)
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
