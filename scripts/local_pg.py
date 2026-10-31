"""Docker-free Postgres + pgvector for DB-layer work and tests.

Uses the `pixeltable-pgserver` wheel (bundles PostgreSQL and pgvector) so the
SQL layer can be developed and tested without root or Docker.

    python scripts/local_pg.py start   # starts a server that outlives this command, prints the URI
    python scripts/local_pg.py stop
"""
import subprocess
import sys
import time
from pathlib import Path

import pixeltable_pgserver as pgserver

DATA = Path(__file__).resolve().parent.parent / ".pgdata"


def start() -> str:
    server = pgserver.get_server(DATA, cleanup_mode=None)   # cleanup_mode=None: leave it running on exit
    return server.get_uri()


def stop() -> None:
    pgserver.get_server(DATA, cleanup_mode=None).cleanup()


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    if cmd == "start":
        print(start())
    elif cmd == "stop":
        stop()
    elif cmd == "serve":                                      # internal: keep a process alive next to the server
        start()
        while True:
            time.sleep(3600)
    else:
        sys.exit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    main()
