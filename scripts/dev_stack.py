"""Run API + outbox worker WITHOUT Docker (no root needed).

Postgres comes from scripts/local_pg.py; Mongo / Redis / Qdrant are replaced by in-process
stand-ins (mongomock, fakeredis, embedded Qdrant). Data in those three is NOT persistent,
and the worker rebuilds it from the Postgres outbox on start. For the real stack use
`make up`. Handy for UI/API work on a machine where Docker is unavailable.

    python scripts/dev_stack.py [--port 8000]
"""
import argparse
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
SOCK = ROOT / ".pgdata"
os.environ.setdefault("DATABASE_URL", f"postgresql+psycopg://app_rw:app_rw_dev@/lostfound?host={SOCK}")
os.environ.setdefault("UPLOAD_DIR", str(ROOT / "uploads"))
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

import fakeredis  # noqa: E402
import mongomock  # noqa: E402
import uvicorn  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import notify, outbox, qdrant_store, stores  # noqa: E402
from app.db import get_engine  # noqa: E402


def worker() -> None:
    notify.ensure_indexes()
    qdrant_store.ensure_collection(stores.get_qdrant())
    engine = get_engine()
    with engine.begin() as conn:      # in-memory stores start empty: replay the whole outbox (handlers are idempotent)
        conn.execute(text("UPDATE outbox SET processed_at = NULL, attempts = 0"))
    while True:
        try:
            if outbox.process_batch(engine) == 0:
                time.sleep(1)
        except Exception as e:  # noqa: BLE001
            print("worker error:", e)
            time.sleep(2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    stores.set_clients(mongo=mongomock.MongoClient()["lostfound"],
                       redis=fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True),
                       qdrant=QdrantClient(":memory:"))
    threading.Thread(target=worker, daemon=True).start()
    from app.main import app
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="info")
