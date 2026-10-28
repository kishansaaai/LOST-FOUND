"""Shared fixtures for DB and API tests.

Tests run against a REAL PostgreSQL + pgvector: a throwaway database is created,
migrated to head with Alembic (so the migrations are tested too) and dropped at
the end. Point TEST_DB_ADMIN_URL at any server where the user may CREATE DATABASE
(docker: postgresql://lostfound:lostfound_dev@postgres:5432/postgres).
"""
import os
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

ADMIN_URL = os.environ.get(
    "TEST_DB_ADMIN_URL",
    f"postgresql://postgres@/postgres?host={ROOT / '.pgdata'}",
)


def _conninfo(dbname: str, user: str | None = None, password: str | None = None) -> str:
    kw = {"dbname": dbname}
    if user:
        kw["user"] = user
    if password:
        kw["password"] = password
    return make_conninfo(ADMIN_URL, **kw)


@pytest.fixture(scope="session")
def db_name():
    name = f"lf_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')

    from alembic import command
    from alembic.config import Config
    from sqlalchemy.engine import URL

    d = conninfo_to_dict(_conninfo(name))
    host = d.get("host")
    sock = host is not None and host.startswith("/")      # unix-socket directory
    os.environ["MIGRATION_DATABASE_URL"] = URL.create(
        "postgresql+psycopg", username=d.get("user"), password=d.get("password"),
        host=None if sock else host, port=int(d["port"]) if d.get("port") else None,
        database=name, query={"host": host} if sock else {},
    ).render_as_string(hide_password=False)
    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    command.upgrade(cfg, "head")

    yield name
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def connect(db_name):
    """connect(role=None) -> psycopg connection. role: None (owner) | app_rw | app_ro | analytics."""
    passwords = {"app_rw": "app_rw_dev", "app_ro": "app_ro_dev", "analytics": "analytics_dev"}
    opened = []

    def _connect(role: str | None = None, autocommit: bool = False):
        c = psycopg.connect(_conninfo(db_name, role, passwords.get(role)), autocommit=autocommit)
        opened.append(c)
        return c

    yield _connect
    for c in opened:
        try:
            c.rollback()
            c.close()
        except Exception:
            pass


@pytest.fixture
def db(connect, db_name):
    """Owner connection on a clean database (all tables truncated before the test)."""
    c = connect(autocommit=True)
    c.execute(
        "TRUNCATE outbox, audit_log, claim, match_item, match, embedding, item, location, users "
        "RESTART IDENTITY CASCADE")
    return c


def _sa_url(dbname: str, user: str | None, password: str | None) -> str:
    from sqlalchemy.engine import URL
    d = conninfo_to_dict(_conninfo(dbname))
    host = d.get("host")
    sock = host is not None and host.startswith("/")
    return URL.create("postgresql+psycopg", username=user or d.get("user"), password=password or d.get("password"),
                      host=None if sock else host, port=int(d["port"]) if d.get("port") else None,
                      database=dbname, query={"host": host} if sock else {}).render_as_string(hide_password=False)


@pytest.fixture
def engine_rw(db_name, db):
    """SQLAlchemy engine connected as the least-privilege app_rw role (what the API/worker use)."""
    from sqlalchemy import create_engine
    eng = create_engine(_sa_url(db_name, "app_rw", "app_rw_dev"), pool_size=5)
    yield eng
    eng.dispose()


@pytest.fixture
def fake_stores():
    """In-memory Mongo / Redis / Qdrant plus a fast deterministic embedder."""
    import fakeredis
    import mongomock
    from qdrant_client import QdrantClient

    from app import embeddings, stores
    from tests.fakes import FakeEmbedder
    mongo = mongomock.MongoClient()["lf"]
    redis = fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    qdrant = QdrantClient(":memory:")
    stores.set_clients(mongo=mongo, redis=redis, qdrant=qdrant)
    embeddings.set_embedder(FakeEmbedder())
    yield type("Stores", (), {"mongo": mongo, "redis": redis, "qdrant": qdrant})
    stores.set_clients()
    embeddings.set_embedder(None)


@pytest.fixture
def app_settings(db_name, monkeypatch, tmp_path):
    from app.config import get_settings
    monkeypatch.setenv("DATABASE_URL", _sa_url(db_name, "app_rw", "app_rw_dev"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()
    from app import db as appdb
    appdb.get_engine.cache_clear()
    yield get_settings()
    get_settings.cache_clear()
    appdb.get_engine.cache_clear()
