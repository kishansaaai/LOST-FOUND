"""Run a hand-written .sql file inside the current Alembic transaction.

We bypass SQLAlchemy's text()/exec_driver_sql and talk to the psycopg3
connection directly: with no parameters psycopg uses the simple query
protocol, which allows multi-statement scripts and leaves ':' and '%' in
function bodies untouched.
"""
from pathlib import Path

from alembic import op

SQL_DIR = Path(__file__).resolve().parent / "sql"


def run_sql_file(name: str, **subst: str) -> None:
    sql = (SQL_DIR / name).read_text()
    for key, value in subst.items():
        sql = sql.replace("{{" + key + "}}", value)
    raw = op.get_bind().connection.driver_connection
    raw.execute(sql)
