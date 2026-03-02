"""
Verify Ftrack credentials loading from standard Ftrack Connect path.

Run from project root: python tools/test_credentials_loader.py

Checks:
1. Standard path resolution (%LOCALAPPDATA%\\ftrack\\ftrack-connect)
2. Reading config.json / credentials.json
3. Correct mapping to FTRACK_SERVER, FTRACK_API_USER, FTRACK_API_KEY
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Add ftrack_plugins to path
_project_root = Path(__file__).resolve().parent.parent
_plugins = _project_root / "ftrack_plugins"
if _plugins.is_dir() and str(_plugins) not in sys.path:
    sys.path.insert(0, str(_plugins))

def _mask(s: str, visible: int = 4) -> str:
    if not s or len(s) <= visible * 2:
        return "***"
    return s[:visible] + "..." + s[-visible:]

def main():
    print("=" * 60)
    print("Ftrack credentials loader verification")
    print("=" * 60)

    from ftrack_inout.common.credentials_loader import (
        _get_ftrack_connect_dir,
        load_ftrack_credentials_from_connect,
        load_ftrack_credentials_into_env,
    )

    # 1. Check standard path
    connect_dir = _get_ftrack_connect_dir()
    if connect_dir:
        print(f"\n[OK] Ftrack Connect dir: {connect_dir}")
        for name in ("credentials.json", "config.json"):
            p = connect_dir / name
            print(f"      {name}: {'exists' if p.is_file() else 'not found'}")
    else:
        print("\n[WARN] Could not resolve Ftrack Connect directory (platformdirs/LOCALAPPDATA)")

    # 2. Load from Connect storage
    creds = load_ftrack_credentials_from_connect()
    if creds:
        print("\n[OK] Credentials loaded from Ftrack Connect storage:")
        for k, v in creds.items():
            masked = _mask(v) if v and "KEY" in k or "key" in k.lower() else (v[:50] + "..." if v and len(v) > 50 else v)
            print(f"      {k}: {masked}")
    else:
        print("\n[INFO] No credentials in Ftrack Connect storage (config.json/credentials.json)")

    # 3. Load into env and verify
    print("\n--- load_ftrack_credentials_into_env ---")
    loaded = load_ftrack_credentials_into_env(prefer_connect=True, dotenv_paths=[])
    if loaded:
        print("[OK] Credentials loaded into os.environ")
    else:
        # Try with .env fallback
        dotenv_paths = [
            _project_root / "config" / ".env",
            _project_root / ".env",
        ]
        loaded = load_ftrack_credentials_into_env(prefer_connect=True, dotenv_paths=dotenv_paths)
        if loaded:
            print("[OK] Credentials loaded (Connect or .env)")
        else:
            print("[INFO] No credentials loaded (env may already be set)")

    print("\nCurrent FTRACK_* in env:")
    for k in ("FTRACK_SERVER", "FTRACK_API_USER", "FTRACK_API_KEY"):
        v = os.environ.get(k, "")
        if v:
            masked = _mask(v) if "KEY" in k else v
            print(f"  {k}={masked}")
        else:
            print(f"  {k}=<not set>")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
