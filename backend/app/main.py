import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from . import notify, qdrant_store
from .config import get_settings
from .db import get_engine
from .errors import db_error_handler
from .routers import admin, auth, claims, items, notifications, staff
from .stores import get_mongo, get_qdrant, get_redis

log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        notify.ensure_indexes()
        qdrant_store.ensure_collection(get_qdrant())
    except Exception as e:                       # noqa: BLE001 - the API still serves relational data
        log.warning("derived stores not ready yet: %s", e)
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Lost & Found API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.add_exception_handler(DBAPIError, db_error_handler)
    for r in (auth.router, items.router, claims.router, staff.router, admin.router, notifications.router):
        app.include_router(r)
    Path(s.upload_dir).mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=s.upload_dir), name="uploads")

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    @app.get("/health/deep", tags=["meta"])
    def health_deep():
        out = {}
        for name, fn in (("postgres", lambda: get_engine().connect().execute(text("SELECT 1")).close()),
                         ("mongo", lambda: get_mongo().command("ping")),
                         ("qdrant", lambda: get_qdrant().get_collections()),
                         ("redis", lambda: get_redis().ping())):
            try:
                fn(); out[name] = "ok"
            except Exception as e:               # noqa: BLE001
                out[name] = f"down: {e.__class__.__name__}"
        return out

    return app


app = create_app()
