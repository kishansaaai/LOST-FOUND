"""Migrations are reversible: upgrade -> downgrade to base -> upgrade again leaves a working schema."""
import os
import uuid

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict
from sqlalchemy.engine import URL

from tests.conftest import ADMIN_URL, ROOT, _conninfo


def _alembic(db_name: str, command_name: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    d = conninfo_to_dict(_conninfo(db_name))
    host = d.get("host")
    sock = host is not None and host.startswith("/")
    os.environ["MIGRATION_DATABASE_URL"] = URL.create(
        "postgresql+psycopg", username=d.get("user"), password=d.get("password"),
        host=None if sock else host, port=int(d["port"]) if d.get("port") else None,
        database=db_name, query={"host": host} if sock else {}).render_as_string(hide_password=False)
    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    getattr(command, command_name)(cfg, revision)


def test_upgrade_downgrade_upgrade_round_trip():
    name = f"lf_mig_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    try:
        _alembic(name, "upgrade", "head")
        with psycopg.connect(_conninfo(name)) as c:
            assert c.execute("SELECT count(*) FROM information_schema.tables "
                             "WHERE table_schema='public' AND table_name='users'").fetchone()[0] == 1
        _alembic(name, "downgrade", "base")
        with psycopg.connect(_conninfo(name)) as c:
            left = c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' "
                             "AND table_name <> 'alembic_version'").fetchone()[0]
            assert left == 0, "downgrade to base must remove every table"
        _alembic(name, "upgrade", "head")                                   # and it can be rebuilt
        with psycopg.connect(_conninfo(name)) as c:
            assert c.execute("SELECT count(*) FROM pg_proc WHERE proname IN ('find_matches', 'approve_claim', 'related_items')"
                             ).fetchone()[0] == 3
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
