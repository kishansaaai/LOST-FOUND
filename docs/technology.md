# Technology justification

One rule drives every choice: **each database owns the data whose access pattern it is best at, and Postgres stays the source of truth.**

| Store | Owns | Why this one, and not Postgres | What we give up |
|---|---|---|---|
| **PostgreSQL 17 + pgvector** | users, items, locations, embeddings, matches, claims, audit log, analytics views | Anything with integrity rules needs ACID, foreign keys, constraints, triggers and row locks (claim approval). pgvector keeps embeddings next to the rows they describe, so RRF is one SQL function. | Vector search at 100k+ items is slower than a dedicated engine (see `benchmark.md`). |
| **MongoDB** | notifications, activity feed, per-category item extras (laptop serial, pet breed, ...) | Documents with a different shape per category, written often, never joined and never needing foreign keys. A relational table would mean many nullable columns or an EAV mess. | No constraints or joins; it holds only data that is safe to lose or rebuild. |
| **Qdrant** | ANN index of text and image vectors with payload filters | Filtered similarity search stays flat at 11-18 ms up to 100k items while the SQL path grows (3.5 -> 119 ms). It is derived from Postgres and rebuildable with `make reindex`. | A second copy of the vectors that must be kept in sync (the outbox does that). |
| **Redis** | search/match cache with TTL, rate limits, refresh-token store, pub/sub for live notifications | Ephemeral, very fast, expiry built in. Nothing in it is a source of truth. | Lost on restart by design; login fails closed (503) if it is down, the cache fails open. |

Consistency between the four is handled by the transactional outbox (`consistency.md`), not by dual writes.

Application stack: **FastAPI** (typed, fast, automatic OpenAPI), **SQLAlchemy Core + hand-written SQL** (the DBMS logic must be visible, not hidden behind an ORM), **Alembic** (every schema change is a migration), **Next.js + TypeScript** (the required front end), **sentence-transformers / CLIP** (local models, no paid API).
