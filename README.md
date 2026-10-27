# Lost & Found

A database-centred Lost & Found platform. People report lost or found items; the system **matches** them automatically with
hybrid search (MiniLM text embeddings + CLIP image embeddings fused by **Reciprocal Rank Fusion in SQL**); owners submit **claims**
that staff verify; the item is returned with a complete audit trail.

The database is the point of the project: 3NF schema, constraints, triggers, state machines, stored procedures, views, materialized views,
row-level security, least-privilege roles, a proven concurrency story and measured index behaviour. See [docs/](docs/).

| Store | Role |
|---|---|
| **PostgreSQL 17 + pgvector** | source of truth: users, items, locations, embeddings (HNSW), matches, claims, audit, outbox |
| **MongoDB** | notifications, activity feed, per-category `item_extras`, upload metadata |
| **Qdrant** | derived ANN index for filtered similarity search (`MATCH_BACKEND=qdrant`) |
| **Redis** | query cache, rate limits, refresh-token allow-list / revocation, pub/sub for real-time notifications, worker wake-up |

Backend: FastAPI + SQLAlchemy Core + Alembic (hand-written SQL in `backend/sql/`). Frontend: Next.js (App Router), TypeScript, Tailwind, shadcn/ui.

## Quick start (Docker)

Requires Docker with the Compose plugin and your user allowed to run `docker` (`sudo usermod -aG docker $USER`, re-login).

```bash
make up        # builds and starts postgres, mongo, qdrant, redis, api, worker, frontend; waits until all are healthy
make migrate   # alembic upgrade head
make seed      # ~320 items, real embeddings, matches, claims in every state (first run downloads the models, ~1 GB in the image)
```
Open <http://localhost:3000> (API docs: <http://localhost:8000/docs>). Or all at once: `make demo`.

Demo accounts, password `Passw0rd!demo` for all: `admin@lostfound.dev`, `staff@lostfound.dev`, `staff2@lostfound.dev`,
`alice@lostfound.dev`, `bob@lostfound.dev`, `carol@lostfound.dev`.

| Command | Does |
|---|---|
| `make test` | runs the whole pytest suite (`tests/`) inside the backend container, against the real Postgres |
| `make e2e` | Playwright browser tests against the running stack (see *End-to-end tests* below) |
| `make reseed` | wipes and regenerates the demo data |
| `make reindex` | rebuilds Qdrant from Postgres |
| `make benchmark` | latency and agreement of both matching backends at 1k, 10k and 100k items |
| `make psql` | psql shell (run [docs/demo_queries.sql](docs/demo_queries.sql) from here) |
| `make down` | stop (add `-v` to the compose command to wipe volumes) |

Configuration lives in `.env` (created from `.env.example` on first `make up`).

## Quick start without Docker (development / verification)
Everything except the three non-relational stores runs unprivileged:
```bash
python -m venv .venv && .venv/bin/pip install -r backend/requirements.txt pixeltable-pgserver mongomock fakeredis pytest
.venv/bin/python scripts/local_pg.py start                 # PostgreSQL + pgvector in ./.pgdata; prints a URI like
                                                           #   postgresql://postgres:@/postgres?host=/path/to/socket-dir
SOCK=/path/to/socket-dir                                   # the host=... part of that URI
psql "postgresql://postgres@/postgres?host=$SOCK" -c "CREATE DATABASE lostfound"
export MIGRATION_DATABASE_URL="postgresql+psycopg://postgres@/lostfound?host=$SOCK"
(cd backend && ../.venv/bin/alembic upgrade head)          # creates the schema and the app_rw/app_ro/analytics roles
(cd backend && ../.venv/bin/python -m app.seed)            # demo data (first run downloads the embedding models)
.venv/bin/python scripts/dev_stack.py                      # API + worker with in-memory Mongo/Redis/Qdrant stand-ins
cd frontend && npm ci && npm run build && npm start
TEST_DB_ADMIN_URL="postgresql://postgres@/postgres?host=$SOCK" .venv/bin/python -m pytest tests -q   # DB, pipeline and API tests
```
`scripts/dev_stack.py` expects the database in `./.pgdata`; if that path is too long for a Unix socket (limit about 100 characters),
point `DATABASE_URL` at `$SOCK` instead. The `tests/` suite creates and drops its own throw-away databases.

## What to look at (guided tour)
1. **Report** a lost item as Alice → within seconds *My reports* shows suggested matches → open one → **Why this match?** shows both rankings and the RRF arithmetic.
2. **Claim** the found item (Bob's wallet…) with proof → sign in as `staff@lostfound.dev` → *Staff → Claim queue* → review, **Approve**: the item becomes `claimed`, competing claims are auto-rejected, then **Mark returned**.
3. *Staff → Audit log* shows who did what (written by triggers). *Analytics* is served from materialized views.
4. Run the concurrency proof: `pytest tests/db/test_concurrency.py -v`.

## End-to-end tests
Playwright drives a real browser through sign-in, reporting, claiming and staff review. It needs a seeded, running stack
(`make demo`) and, because the suite signs in many times, a relaxed rate limit: set `RATE_LIMIT_SCALE=20` in `.env` and restart the API.
```bash
cd tests/e2e && npm install && npx playwright install chromium
make e2e                      # from the repository root; E2E_BASE_URL / E2E_API_URL override the defaults
```

## Tests
`tests/db` (constraints, state machines, matching, security/RLS, audit, outbox, views, recursive query, migrations round trip, **concurrency**), `tests/pipeline` (outbox → embeddings → Qdrant → Mongo → Redis, replay idempotence, failure retry, backend agreement), `tests/api` (auth, journey, notification deletion, validation, injection attempts, permissions), `tests/e2e` (Playwright, see *End-to-end tests*).

## Layout
```
backend/app          FastAPI app, outbox worker, matching service, seed
backend/sql          the schema as hand-written SQL, executed by Alembic
backend/alembic      migrations 0001–0005
frontend             Next.js app
docs                 schema, ER, normalization, indexing, concurrency, consistency, matching, benchmark,
                     technology choices, demo_queries.sql (runnable SQL walkthrough)
tests                db / pipeline / api / e2e
scripts              benchmark, explain evidence, Docker-free dev stack
```
