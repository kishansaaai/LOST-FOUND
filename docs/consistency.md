# Consistency between PostgreSQL, Qdrant, MongoDB and Redis

**Postgres is the only source of truth.** Everything else is derived and can be rebuilt:

| Store | Holds | Rebuild |
|---|---|---|
| Qdrant | one point per item (named vectors `text`, `image`, payload for filters) | `make reindex` (reads `embedding`) |
| MongoDB | `notifications`, `activity_feed`, `item_extras`, upload metadata | replay `outbox` (notifications/extras); feed is informational |
| Redis | search cache, rate-limit counters, refresh-token allow-list, revocation list, pub/sub, worker wake-up | cache: nothing to do. Tokens: users sign in again |

## Transactional outbox, no dual writes
The API never writes to two stores. A business change commits to Postgres; **triggers insert an `outbox` row in the same
transaction** (`trg_outbox_item/match/claim/embedding`), and `app/outbox.py` relays it:

```
API ──tx──► Postgres (item, outbox)  ──► worker  ──► embed ► Qdrant upsert ► refresh_matches ► Mongo notify ► Redis invalidate + pub/sub
```
Item extras (Mongo) are sent the same way: the API inserts an `item_extras.set` outbox row in the item's transaction.

Guarantees: **at-least-once** delivery (a row is marked `processed_at` only after its handler succeeded) and **idempotent
handlers** (Qdrant upsert by point id; Mongo `update_one(dedupe_key, $setOnInsert)`; embedding skipped when `content_hash` is
unchanged; matching is `UNIQUE` per pair). `tests/pipeline` replays the entire outbox and asserts that nothing is duplicated.

## Failure scenarios
| Failure | What happens | Recovery |
|---|---|---|
| API crashes after commit, before responding | Row + outbox event exist; worker processes them normally | none needed |
| API crashes mid-transaction | Neither row nor event exist (same transaction) | none needed |
| Worker crashes mid-event | Event's `processed_at` still NULL (its savepoint rolled back) | picked up again on restart |
| Qdrant down | Embedding/item events fail, `attempts++`, `last_error` stored; other events continue (per-event savepoint) | retried automatically up to 8 times; afterwards parked; `make reindex` rebuilds the index and resetting `attempts` replays |
| Mongo down | notification handlers fail and retry; item pages degrade (extras omitted, no error) | automatic |
| Redis down | cache misses, rate limiting and the revocation list **fail open** (logged); the worker polls instead of blocking on the wake-up list; **refresh tokens cannot be issued/rotated** (**login and refresh return 503** rather than minting tokens that could not be rotated or revoked; access tokens already issued keep working until they expire) | automatic when Redis returns |
| Event delivered twice | Idempotent handlers | none |
| Out-of-order delivery | One worker processes in `outbox_id` order. With several workers (`SKIP LOCKED`) events for the *same* item may interleave, but handlers re-read current state from Postgres instead of trusting the payload, so the final state converges | none |
| Qdrant payload says `open`, Postgres says `claimed` (stale window) | The Qdrant backend filters on payload only as a *pre-filter*; `persist_match` and `refresh_matches` are only called for items that are `open` in Postgres, and `claim_guard` rejects claims on non-open items | converges when the event is processed |
| Cache serves a stale list | TTL (60 s) bounds staleness; the worker bumps the namespace version on every item/match/claim event | automatic |
| Whole Qdrant/Mongo/Redis lost | No data loss: `make reindex`, replay outbox (`UPDATE outbox SET processed_at=NULL`) | documented commands |

Cache keys are `lf:<namespace>:v<version>:<sha1(query)>`; invalidation is `INCR lf:ver:<namespace>` (O(1), no key scans).
