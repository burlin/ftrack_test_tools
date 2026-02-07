"""Проверить существование компонента."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from run_browser import _bootstrap_environment
_bootstrap_environment(PROJECT_ROOT)

import ftrack_api

component_id = "0555c873-083a-49df-a31b-903e865f8846"
session = ftrack_api.Session()

# Пробуем через get
try:
    comp = session.get('Component', component_id)
    if comp:
        print(f"✓ Found via get(): {comp['name']} (ID: {comp['id']})")
        print(f"  Version: {comp['version']['version']}")
        print(f"  Asset: {comp['version']['asset']['name']}")
    else:
        print("✗ get() returned None")
except Exception as e:
    print(f"✗ get() failed: {e}")

# Пробуем через query
try:
    comp = session.query(f'Component where id is "{component_id}"').first()
    if comp:
        print(f"✓ Found via query(): {comp['name']} (ID: {comp['id']})")
        print(f"  Version: {comp['version']['version']}")
        print(f"  Asset: {comp['version']['asset']['name']}")
    else:
        print("✗ query() returned None")
except Exception as e:
    print(f"✗ query() failed: {e}")
