#!/usr/bin/env python
"""
Send a single test mroya.transfer.request event.

Использует тот же bootstrap окружения, что run_browser / run_user_tasks:
- загружает config/.env и config/mroya.json;
- создаёт ftrack_api.Session;
- создаёт Job c данными tag="mroya_transfer";
- публикует событие topic="mroya.transfer.request".

После запуска, если ftrack Connect с плагином mroya_transfer_manager работает,
вкладка "Mroya Transfer Manager" должна увидеть новый Job.
"""

import json
import sys
from pathlib import Path

import ftrack_api  # type: ignore
from ftrack_api.event.base import Event  # type: ignore

# Add tools to path so run_browser can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = PROJECT_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_browser import _bootstrap_environment  # type: ignore


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    _bootstrap_environment(project_root)

    session = ftrack_api.Session()

    user = session.query(f'User where username is "{session.api_user}"').one()
    user_id = user["id"]

    meta = {
        "tag": "mroya_transfer",
        "description": "Mroya test transfer job from CLI",
        "component_label": "test-cli",
        "from_location_id": None,
        "to_location_id": None,
        "to_location_name": "Test Target",
    }

    job = session.create(
        "Job",
        {
            "user_id": user_id,
            "status": "running",
            "data": json.dumps(meta),
        },
    )
    session.commit()
    
    print(f"[send_mroya_transfer_test] Created Job {job['id']} with data: {json.dumps(meta)}")

    payload = {
        "job_id": job["id"],
        "user_id": user_id,
        "from_location_id": None,
        "to_location_id": None,
        "selection": [],
        "ignore_component_not_in_location": False,
        "ignore_location_errors": False,
    }

    try:
        session.event_hub.connect()
    except Exception:
        # если уже подключен или сервер недоступен, пусть кинет исключение позже
        pass

    event = Event(topic="mroya.transfer.request", data=payload)
    session.event_hub.publish(event, on_error="ignore")

    print(f"[send_mroya_transfer_test] Sent test job {job['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

