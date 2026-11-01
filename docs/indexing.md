# Indexing

Evidence is `EXPLAIN (ANALYZE, BUFFERS)` from `scripts/benchmark.py` on a **100,000-item** database (raw files in
[`docs/explain/`](explain/); each file shows the plan with the indexes and again with index scans disabled). Times are execution
times on the development machine, warm cache; read them as ratios.

| Index | Definition | Serves | With index | Without | Evidence |
|---|---|---|---|---|---|
| `embedding_text_hnsw` | HNSW `(text_vect vector_cosine_ops)`, m=16, ef_construction=64 | text similarity ranking | **0.8 ms** (Index Scan, ~1,400 buffers) | 30 ms (Parallel Seq Scan, ~20,000 buffers) | [hnsw_text_knn](explain/hnsw_text_knn_100000.txt) |
| `embedding_image_hnsw` | HNSW `(image_vector …)` **partial** `WHERE image_vector IS NOT NULL` | image ranking; skips the ~half of items without a photo | – | – | build time in [benchmark.md](benchmark.md) |
| `item_search_gin` | GIN on generated `search_tsv` | keyword search (`websearch_to_tsquery`) | **0.12 ms** (Bitmap Index Scan) | 28 ms (Seq Scan, 100,000 rows removed) | [fulltext_gin](explain/fulltext_gin_100000.txt) |
| `item_open_idx` | B-tree `(item_type, category, date_lost_or_found) WHERE status='open'` | browse/filter open items | **0.71 ms** (Bitmap Index Scan) | 11 ms (Seq Scan) | [open_items_partial](explain/open_items_partial_100000.txt) |
| `item_open_type_date_idx` | B-tree `(item_type, date_lost_or_found) WHERE status='open'` | candidate window in `find_matches` | see note | | |
| `claim_one_pending_per_user` | UNIQUE `(item_id, claimant_id) WHERE result='pending'` | rule: one live claim per user and item | – | – | `tests/db/test_constraints.py` |
| `claim_one_approved_per_item` | UNIQUE `(item_id) WHERE result='approved'` | rule: one approved claim per item (concurrency backstop) | – | – | `tests/db/test_concurrency.py` |
| `claim_queue_idx` | B-tree `(submitted_at) WHERE result='pending'` | staff queue, oldest first; stays tiny because decided claims are not indexed | – | – | by construction |
| `users_email_lower_uq` | UNIQUE `(lower(email))` | case-insensitive login lookup and uniqueness | – | – | |
| `item_reporter_idx`, `item_location_idx`, `claim_claimant_idx`, `match_item_item_idx`, `claim_match_idx` | B-tree on foreign keys | joins and `ON DELETE RESTRICT` checks (PostgreSQL does not index FKs automatically) | – | – | |
| `audit_row_idx`, `audit_time_idx` | B-tree `(table_name, row_pk, changed_at DESC)`; BRIN `(changed_at)` | audit lookups per row; time-range scans of an append-only table at tiny size | – | – | |
| `outbox_pending_idx` | B-tree `(outbox_id) WHERE processed_at IS NULL` | worker polling; index size is proportional to the *backlog*, not the history | – | – | |

Rows with "–" are included for completeness; the claim made for them is structural (partial/unique indexes are rules or
tiny by construction), not a timing. Only the first four rows carry timing claims, and those are measured.

**Note on `item_open_type_date_idx` and `find_matches`.** The candidate filter was rewritten with equality and range predicates
(`item_type = <opposite>`, `date BETWEEN lo AND hi`) so this partial index is *usable*; the earlier `<>`/`CASE` form made it impossible. The
measured effect on end-to-end `find_matches` latency was small (see [benchmark.md](benchmark.md)); the function's cost is dominated by
distance computations on the ~20% of vectors that qualify, not by finding them. It is kept because it is correct and cheap, not because
it moved the benchmark.

## HNSW notes
* `vector_cosine_ops` matches the `<=>` operator used everywhere (embeddings are L2-normalised, so cosine = dot product).
* `find_matches` sets `hnsw.iterative_scan = strict_order` (function-level `SET`): with a selective filter the plain index returns fewer
  than `LIMIT` rows because it only examines `ef_search` (40) candidates *before* filtering.
* Build once, then insert: bulk loads in the benchmark drop and recreate the HNSW indexes (about 38 s for 100k text vectors) because incremental insertion is much slower than a bulk build.

## How to reproduce the plans
```bash
python scripts/benchmark.py --sizes 100000            # writes docs/explain/*_100000.txt
```
