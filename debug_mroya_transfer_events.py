#!/usr/bin/env python
"""
Debug helper for Mroya transfer pipeline.

Запускается **вне** ftrack Connect / DCC и:
- поднимает то же окружение, что `run_browser.py` (загружает `.env` и config);
- подключается к ftrack_api.Session;
- подписывается на topic="mroya.transfer.request";
- печатает любые входящие события в консоль.

Так можно быстро проверить, что браузер / Houdini реально посылают события
и что они доходят до сервера.
"""

import logging
import sys
from pathlib import Path

import ftrack_api  # type: ignore

# Поднимаем project root в sys.path, чтобы можно было импортировать run_browser,
# даже если скрипт запускается как tools/debug_mroya_transfer_events.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_browser import _bootstrap_environment  # type: ignore


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s:%(name)s:%(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("mroya.transfer.debug_listener")

    # Bootstrap окружения так же, как run_browser / run_user_tasks.
    project_root = Path(__file__).resolve().parent.parent
    _bootstrap_environment(project_root)

    session = ftrack_api.Session()
    log.info("Session created for user %s", session.api_user)

    def _handler(event):
        try:
            data = event.get("data") or {}
            log.info("Received mroya.transfer.request event: %r", data)
        except Exception as exc:  # pragma: no cover
            log.warning("Error in event handler: %s", exc)

    log.info("Connecting event hub…")
    session.event_hub.connect()
    log.info("Subscribing to topic=mroya.transfer.request")
    session.event_hub.subscribe("topic=mroya.transfer.request", _handler)

    log.info("Listening for events. Press Ctrl+C to stop.")
    try:
        while True:
            session.event_hub.wait(1)
    except KeyboardInterrupt:
        log.info("Stopped by user.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

