# Schema reference

Source of truth: `backend/sql/*.sql`, executed by Alembic migrations `0001`–`0005`
(`make migrate`, or `alembic downgrade base && alembic upgrade head` to rebuild; both directions are tested by
`tests/db/test_migrations.py`). Ready-to-run example queries for every SQL feature below: [demo_queries.sql](demo_queries.sql).

| Migration | SQL file | Contents |
|---|---|---|
| 0001 | `001_core_schema.sql` | enums, 9 tables, constraints, indexes |
| 0002 | `002_triggers.sql` | state machines, validation, audit, outbox |
| 0003 | `003_matching.sql`, `004_workflow.sql` | `rrf_fuse`, `find_matches`, `persist_match`, `refresh_matches`, claim/match procedures |
| 0004 | `005_views.sql` | views, materialized views, `related_items` (recursive CTE) |
| 0005 | `006_security.sql` | roles, column grants, row-level security |

See [er-diagram.md](er-diagram.md) for the entity model.

## Enumerations
`user_role (user, staff, admin)` · `item_type (lost, found)` · `item_status (open, matched, claimed, returned, closed)` ·
`item_category (electronics, wallet_bag, keys, id_card, clothing, jewelry, documents, pet, other)` ·
`match_status (suggested, confirmed, rejected)` · `verification_status (pending, under_review, verified, rejected)` ·
`claim_result (pending, approved, denied)`.

## Constraints that carry business rules (all enforced by the engine, all tested in `tests/db`)
| Rule | Mechanism |
|---|---|
| e-mail unique, case-insensitive | `UNIQUE INDEX ON users (lower(email))` |
| found/lost date not in the future | `BEFORE` trigger (a `CHECK` on `current_date` is not immutable and misbehaves on restore) |
| match pairs exactly one lost + one found; no self pairing | `UNIQUE (match_id, role)` + deferred constraint trigger |
| a pair is never stored twice | `UNIQUE (match.pair_key)` |
| `result` and `verification_status` never contradict | two `CHECK`s on `claim` |
| a decided claim records reviewer and time; nobody reviews their own claim | `CHECK`s on `claim` |
| one live claim per (item, claimant) | partial unique index `WHERE result='pending'` |
| **at most one approved claim per item** | partial unique index `WHERE result='approved'` |
| embedding dimensions | `vector(384)` / `vector(512)` types |

## State machines (trigger `item_guard`, `claim_guard`)
Item status: the only legal moves (anything else raises `LF002`) are

| from | to |
|---|---|
| `open` | `matched`, `claimed`, `closed` |
| `matched` | `open`, `claimed`, `returned`, `closed` |
| `claimed` | `returned`, `closed` |
| `closed` | `open` (reopen) |
| `returned` | none, it is terminal |

Guards on top of that graph: `claimed` needs an approved claim and a *found* item; `returned` needs an approved claim
(found item) or a confirmed match whose found item has an approved claim (lost item, the `matched → returned` move);
`item_type` and `reporter_id` can never change; new items must start `open`.

Claim: `pending → under_review → verified | rejected`, and `pending` may also go straight to `verified` or `rejected`.
A decided claim (`result` approved or denied) is immutable, and only a staff or admin user can be recorded as reviewer.
Illegal moves raise SQLSTATE `LF002`; the API maps `LF001 → 403`, `LF002 → 409`, `LF003 → 404`.

## Triggers
`trg_item_guard`, `trg_item_updated_at`, `trg_match_integrity` / `trg_match_item_integrity` (deferred),
`trg_claim_guard`, `trg_claim_after_approval` (approve ⇒ item `claimed`, competing pending claims auto-rejected,
linked match `confirmed`), `trg_audit_{item,claim,match,users}` (password hashes never audited),
`trg_outbox_{item,match,claim,embedding}`.

## Stored procedures / functions
`rrf_fuse(text_rank, image_rank, k)` · `find_matches(item_id, …)` · `persist_match(…)` · `refresh_matches(item_id, …)` ·
`start_claim_review`, `approve_claim`, `reject_claim`, `mark_returned`, `close_item`, `confirm_match`, `reject_match`,
`set_user_role`, `refresh_analytics`, plus the recursive `related_items(item_id, max_depth)` (items reachable through
non-rejected matches, with the number of hops; a `path` array guards against cycles). State-changing procedures are `SECURITY DEFINER` with a pinned `search_path`
and check the caller's role themselves; execute rights are revoked from `PUBLIC`.

## Views
`v_open_items`, `v_match_details` (the "explain a match" surface), `v_claim_queue` (window functions: competing
claims, queue position; `security_invoker` so RLS still applies), `v_likely_owners` (`dense_rank` of lost reports per found item).
Materialized (all with a unique index so `REFRESH … CONCURRENTLY` never blocks readers):
`mv_status_counts`, `mv_recovery_stats` (`ROLLUP` + `LATERAL` lookup of the return time in `audit_log` + `percentile_cont`),
`mv_location_hotspots` (`rank()`, `percent_rank()`), `mv_match_quality` (`width_bucket`).
**Refresh strategy:** the worker calls `refresh_analytics()` every `ANALYTICS_REFRESH_SECONDS` (default 300) and after seeding;
staff can force it from the dashboard. Dashboards therefore lag writes by at most that interval, in exchange for O(1) reads.

## Security model
| Role | Rights |
|---|---|
| owner (migrations, seed) | everything; bypasses RLS |
| `app_rw` (API, worker) | `SELECT` on tables; `INSERT` on users (name, email, password hash, phone only, never `role`), location, item, claim, embedding, outbox; `UPDATE` only on profile columns, location details, editable item columns (**not** `status`), embedding, outbox (marking events processed); **no `DELETE`, no direct writes to claim decisions, match status, audit_log**. Everything else goes through procedures. |
| `app_ro` | read-only on non-PII columns (no e-mail/phone/hash, no claims, no audit) |
| `analytics` | `SELECT` on the materialized views only |

Row-level security: `claim` (owner sees own claims, staff see all, anyone can only file a claim as themselves) and
`audit_log` (staff only). The API publishes the caller with `set_config('app.user_id', …, true)` in every transaction;
staff-ness is *looked up in `users`*, never taken from the setting, so a forged value grants nothing.
Roles can only be changed through `set_user_role` (admin only; the last admin cannot be demoted).

## Backup / restore
```bash
# logical backup (schema + data, custom format, includes the pgvector columns)
docker compose exec -T postgres pg_dump -U lostfound -Fc lostfound > backup.dump
# restore into an empty database (extension is created by the dump)
docker compose exec -T postgres createdb -U lostfound lostfound_restore
docker compose exec -T postgres pg_restore -U lostfound -d lostfound_restore --no-owner < backup.dump
```
After a restore run `make reindex` (Qdrant is derived) and let the worker replay the outbox; Mongo notifications and the
Redis cache are non-authoritative. Point-in-time recovery: enable WAL archiving (`archive_mode=on`, `archive_command`)
and take `pg_basebackup`s; nothing in this schema prevents it. The role passwords are *not* in `pg_dump -Fc` of one
database, so restore the cluster roles (`pg_dumpall --roles-only`) first.
