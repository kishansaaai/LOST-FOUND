"""Alembic environment.

The schema is hand-written SQL (backend/sql/*.sql), so there is no ORM
metadata and no autogenerate: each migration executes a SQL file.
"""
import os

from alembic import context
from sqlalchemy import create_engine

url = os.environ["MIGRATION_DATABASE_URL"]


def run_migrations_online() -> None:
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
