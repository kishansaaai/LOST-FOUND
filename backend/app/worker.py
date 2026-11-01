"""Background worker: outbox relay + periodic analytics refresh.   python -m app.worker"""
import logging
import time

from sqlalchemy import text

from . import notify, qdrant_store
from .config import get_settings
from .db import get_engine
from .outbox import WAKE_KEY, process_batch
from .stores import get_qdrant, get_redis

log = logging.getLogger("worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    s = get_settings()
    engine = get_engine()
    for _ in range(60):                     # stores may still be starting
        try:
            notify.ensure_indexes()
            qdrant_store.ensure_collection(get_qdrant())
            break
        except Exception as e:                    # noqa: BLE001
            log.info("waiting for stores: %s", e)
            time.sleep(2)
    last_refresh = 0.0
    log.info("worker started (backend=%s)", s.match_backend)
    while True:
        try:
            n = process_batch(engine)
        except Exception as e:                    # noqa: BLE001 - DB not migrated yet / restarting: keep trying
            log.warning("database not ready (%s); retrying in 3s", e.__class__.__name__)
            time.sleep(3)
            continue
        if n == 0:
            try:
                get_redis().blpop(WAKE_KEY, timeout=2)      # woken by the API, else poll every 2s
            except Exception:
                time.sleep(2)
        if time.time() - last_refresh > s.analytics_refresh_seconds:
            try:
                with engine.begin() as conn:
                    conn.execute(text("SELECT refresh_analytics()"))
                last_refresh = time.time()
            except Exception as e:                # noqa: BLE001
                log.warning("analytics refresh failed: %s", e)
                last_refresh = time.time() - s.analytics_refresh_seconds + 30


if __name__ == "__main__":
    main()
