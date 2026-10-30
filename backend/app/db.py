"""PostgreSQL access. SQLAlchemy Core + hand-written SQL; no ORM on purpose."""
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine

from .config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_size=10, max_overflow=10, pool_pre_ping=True)


@contextmanager
def transaction(user_id: int | None = None, engine: Engine | None = None) -> Iterator[Connection]:
    """One database transaction. When `user_id` is given it is published to the
    session as `app.user_id` (transaction-local) so audit triggers record the actor and
    row-level-security policies can see who is asking."""
    with (engine or get_engine()).begin() as conn:
        if user_id is not None:
            conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user_id)})
        yield conn


def rows(conn: Connection, sql: str, **params) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


def one(conn: Connection, sql: str, **params) -> dict | None:
    r = conn.execute(text(sql), params).mappings().first()
    return dict(r) if r else None


def scalar(conn: Connection, sql: str, **params):
    return conn.execute(text(sql), params).scalar()
