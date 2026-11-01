# Benchmark: `pg` vs `qdrant` matching backends

Reproduce: `make benchmark` (inside the Docker stack; measures both backends). The script builds a scratch database from the real migrations, bulk loads
synthetic clustered vectors, builds the HNSW indexes, loads the same vectors into Qdrant and replays 100 random open items against each backend.

Environment: Docker stack from `docker-compose.yml`: PostgreSQL 17 + pgvector (`shared_buffers` default, `shm_size: 1gb`), Qdrant 1.12.4, 24 CPU laptop.
384-d text vectors for every item, 512-d image vectors on half of them, 80% of items `open`. Numbers are from one run on one machine: read them as ratios.

## PostgreSQL backend (`MATCH_BACKEND=pg`)

| items | HNSW build (text / image) | find_matches p50 | p95 | exact-scan p50 | HNSW top-10 agreement |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 0.3s / 0.1s | 3.5 ms | 7.6 ms | 4.2 ms | 100.0% |
| 10,000 | 2.4s / 1.5s | 8.7 ms | 25.6 ms | 8.2 ms | 100.0% |
| 100,000 | 37.6s / 24.6s | 118.9 ms | 368.5 ms | 176.1 ms | 100.0% |

*find_matches* = candidate filter (opposite type, open, date window) + text ranking + image ranking + RRF fusion + gate, in one SQL function.
"Exact-scan" is the same function with index scans disabled. Agreement = |HNSW top-10 ∩ exact top-10| / 10.

## Qdrant backend (`MATCH_BACKEND=qdrant`)
Filtered ANN per modality (payload filters on type, status, date window), RRF fused in Python with the same formula and the same gate/boost rules.
Agreement is measured against the *exact SQL* result with the similarity gate off.

| items | index load | p50 | p95 | top-10 agreement vs exact |
|---:|---:|---:|---:|---:|
| 1,000 | 5.6s | 12.9 ms | 93.7 ms | 99.7% |
| 10,000 | 49.5s | 13.9 ms | 26.8 ms | 100.0% |
| 100,000 | 390.7s | 13.8 ms | 24.6 ms | 100.0% |

## What this shows
* **Qdrant's latency is flat (about 13 ms from 1k to 100k items); Postgres' grows with the data (3.5 → 8.7 → 119 ms).** At 100k items Qdrant is roughly **9x faster**
  than the SQL path. At 1k items the SQL path is faster (3.5 ms vs 13 ms) because there is no network round trip and nothing to search.
  Qdrant filters inside the graph traversal using payload indexes; pgvector has to iterate the HNSW scan until enough *qualifying* neighbours turn up.
* **Both backends agree with the exact answer (99.7–100% top-10)** once the SQL ordering bug described in [matching.md](matching.md) was fixed. Before the fix
  the benchmark itself exposed it: Qdrant disagreed with SQL while the SQL-vs-SQL (HNSW vs exact) check kept passing, because both shared the bug.
* **HNSW barely helps `find_matches` in Postgres (119 ms vs 176 ms at 100k)**, even though plain k-NN is about 35x faster with the index
  ([indexing.md](indexing.md)). The query is filtered (about one item in five qualifies), so the exact path only has to measure ~20% of the vectors, and
  the HNSW path must iterate until enough qualifying neighbours are found.
* **Cost of Qdrant:** a second datastore, an index-load step (391 s for 100k points in this benchmark's one-by-one-batch loader; the worker's incremental upserts
  are cheap), and the eventual-consistency window of the outbox ([consistency.md](consistency.md)): a new item is searchable in Qdrant only after the worker
  processed it, whereas the SQL path sees it as soon as its embedding row commits.
* **Recommendation:** keep `pg` (default) up to about 10k items: simpler, transactional, no extra service. Switch to `qdrant` when matching latency at tens of
  thousands of items or more matters. The switch is one environment variable plus `make reindex`.
