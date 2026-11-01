# Matching engine

When an item is created or edited the worker embeds it (`all-MiniLM-L6-v2` for text, CLIP `clip-ViT-B-32` for photos, both run
locally on CPU) and then calls `refresh_matches(item_id)`. Everything that ranks and fuses runs **in SQL** (`backend/sql/003_matching.sql`).

## Pipeline (`find_matches`)
1. **Candidate filter**: opposite `item_type`, `status = 'open'`, plausible time window (found date ≥ lost date).
2. **Text ranking**: cosine distance on `embedding.text_vect` (HNSW), top `p_pool` (100).
3. **Image ranking**: same on `image_vector`, only if *both* items have a photo.
4. **Fusion**: `rrf_score = Σ 1/(k + rank_i)` over the rankings a candidate appears in, `k = 60` (`rrf_fuse()`; `FULL JOIN` of the rankings).
5. **Gate**: keep a candidate only if `text ≥ 0.60` **or** `image ≥ 0.90`. RRF is rank-based, so without a similarity floor the least-bad
   candidate would always "match".
6. **Boost** (explainable, tiny): +0.0020 same category, +0.0010 same location, +0.0005 same colour, +0.0005 same brand. It only
   orders candidates; the stored `rrf_score` is the pure fusion number.
7. **Persist** (`persist_match`): top N (10) into `match` + `match_item` in one transaction; `UNIQUE(pair_key)` makes it idempotent; decided
   (confirmed/rejected) pairs are never touched, so a rejected pair is never re-suggested.
8. The outbox trigger on `match` makes the worker notify both reporters.

`hnsw.iterative_scan = strict_order` is set on the function so the HNSW scan keeps going when the filter in step 1 discards many nearest
neighbours (pgvector ≥ 0.8). Without it a selective filter silently returns fewer than `LIMIT` rows.

### Two backends, one rule set
`MATCH_BACKEND=pg` (default) runs the above in Postgres. `MATCH_BACKEND=qdrant` runs one filtered ANN search per modality in Qdrant
(payload filters: type, status, date window), fuses with the *same formula* in `app/matching.py`, applies the same gate and boost, and
persists through the *same* `persist_match()` function. A test (`test_qdrant_backend_agrees_with_pg_backend`) asserts both produce identical
pairs, ranks and scores, and another asserts the Python and SQL `rrf_fuse` are numerically equal. Latency and agreement:
[benchmark.md](benchmark.md).

## Explainability
`GET /items/{id}/matches` returns, per match, each signal's cosine similarity, its rank, its RRF contribution and the formula
(`1/(60+1) + 1/(60+3) = 0.03227`), shown in the UI under "Why this match?". The headline **confidence** percentage is *not* the RRF score:
RRF only says who is best *among the candidates* (rank 1 of a weak pool scores full marks). Confidence is derived from the real similarities:
how far the best signal sits above its acceptance floor (`app/scoring.py`).

## How good is it?  (measured on the seed data, `python -m app.seed`, in the Docker stack)
110 lost/found pairs describe the same object in different words (and, for ~35%, different renders of the same object), among 320 items and 14 locations.
Reproduce: reseed, then compare `v_match_details` with the generated pairs (items `2i-1`/`2i` are pair *i*).

| Metric (out of the 110 lost reports that have a real match) | Result |
|---|---|
| the real match is among the (max 10) suggestions | 94 / 110 (85%) |
| the real match is the **#1** suggestion | 64% |
| in the top 3 / top 5 | 69% / 82% |

Honest reading: the system offers the right item for most reports and ranks it first for about two in three, which is good for a *suggestion*
that a human confirms, and not good enough to act on automatically. The misses are mostly near-identical objects (several black backpacks) that no
text or image model can tell apart; that is why staff confirm matches and claims need proof. The similarity floors (`MATCH_MIN_TEXT=0.60`,
`MATCH_MIN_IMAGE=0.90`) were tuned on this distribution. Real photographs differ more between shots than the synthetic renders, so expect to lower
the image floor (about 0.80–0.85) on real data and re-measure with the same procedure.

### A bug the benchmark found (kept here because it is instructive)
An earlier version of `find_matches` ended with `ORDER BY 2 + 3 DESC`. In SQL that is the constant `5`, not "column 2 plus column 3", so the
`LIMIT` kept the candidates with the lowest ids instead of the best scores. Unit tests passed because they never had more candidates than the limit,
and the HNSW-vs-exact agreement check passed because both paths shared the bug. It surfaced when the Qdrant backend (which sorts correctly)
disagreed with SQL on the same data. Fixed, and covered by `test_limit_keeps_the_best_candidates_not_the_lowest_ids`. The numbers above are from after the fix.
