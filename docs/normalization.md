# Normalization (3NF)

Notation: `X → Y` is a functional dependency. A relation is in 3NF if, for every non-trivial `X → A`, either `X` is a
superkey or `A` is part of a candidate key. Every table below has a single-column surrogate key, so the check is that
**every non-key attribute depends on the key, the whole key, and nothing but the key.**

| Table | Key and dependencies | Why it is in 3NF |
|---|---|---|
| `users` | `user_id → name, email, password_hash, phone, role, created_at`; `email → user_id` (candidate key via the `lower(email)` index) | Two candidate keys, all attributes depend on them directly. |
| `location` | `location_id → name, campus, building, floor, address, lat, lon`; `location_name → location_id` | `campus` is *not* derived from `building`: one building name can recur across campuses, so no transitive FD is assumed. (If the data guaranteed it, a `building` table would be the next step.) |
| `item` | `item_id → reporter_id, location_id, type, status, title, …` | Reporter and place attributes live in `users` / `location`, reached by FK. `category` is an enum (a domain, not a relation). |
| `embedding` | `embedding_id → item_id, text_vect, image_vector, model_name, content_hash`; `item_id → embedding_id` | 1:1 with `item`. Kept separate because the vectors are large, written by a different process, and indexed differently (HNSW); keeping them out of `item` keeps item scans narrow. |
| `match` | `match_id → rrf_score, scores, ranks, boost, status, pair_key` | Scores are properties of *the pair*, not of either item. |
| `match_item` | `(match_id, item_id) → role` | The junction of the N:N relationship; `role` depends on the whole key. |
| `claim` | `claim_id → item_id, claimant_id, match_id, proof_*, statuses, reviewed_*` | Claimant name/e-mail are not repeated here (reached through `users`). |
| `audit_log`, `outbox` | `audit_id → …`, `outbox_id → …` | Append-only event records; the JSON payload is deliberately an opaque snapshot of a past state. |

## Deliberate denormalizations (each is guarded and tested)

1. **`match.pair_key`** (`'<lost_id>:<found_id>'`) duplicates information in `match_item`. Reason: a junction table cannot
   express "this pair of items exists at most once" with a declarative constraint, and the brief requires it. The redundancy is
   made *safe* rather than avoided: a deferred constraint trigger verifies at `COMMIT` that `pair_key` equals the real
   participants, so it cannot drift (`tests/db/test_state_machine.py::test_match_pair_is_unique_and_pair_key_must_agree`).
2. **`item.search_tsv`** is a `GENERATED ALWAYS … STORED` column: derived data, but maintained by the engine itself, so
   it cannot be stale and no trigger code exists to get wrong.
3. **`embedding.content_hash`** records the inputs an embedding was computed from so unchanged items are never re-embedded.
4. **Materialized views** are denormalized by definition; they are read-only caches with a documented refresh policy.
5. **`audit_log` / `outbox` payloads** store row snapshots by design (history must not change when the source row does).

`claim.item_id` + `match.pair_key` could in theory disagree (a claim linked to a match that involves a different found item);
this is prevented by the `claim_guard` trigger, which rejects a `match_id` whose `match_item` rows do not include the claimed item.
