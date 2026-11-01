"""Matching benchmark: latency and top-k agreement at 1k / 10k / 100k items.   (docs/benchmark.md)

For every size it builds a scratch database from the real migrations, bulk loads synthetic
items with CLUSTERED vectors (so nearest neighbours are meaningful), builds the HNSW indexes,
then measures `find_matches()` (the RRF SQL function) on random open items:

  * latency p50 / p95 with the HNSW indexes,
  * top-10 agreement of HNSW vs an EXACT scan (same SQL, indexes disabled),
  * with --qdrant-url: latency and top-10 agreement of the Qdrant backend vs exact.

It also saves EXPLAIN (ANALYZE, BUFFERS) output for the main access paths in docs/explain/.

    python scripts/benchmark.py --sizes 1000 10000 100000 [--qdrant-url http://localhost:6333]
Requires a superuser connection (TEST_DB_ADMIN_URL, default: scripts/local_pg.py server).
"""
import argparse
import os
import platform
import statistics
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import psycopg
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
ADMIN_URL = os.environ.get("TEST_DB_ADMIN_URL", f"postgresql://postgres@/postgres?host={ROOT / '.pgdata'}")
CATS = ["electronics", "wallet_bag", "keys", "id_card", "clothing", "jewelry", "documents", "pet", "other"]


def vec_text(a: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.4f}" for x in a) + "]"


def make_db(n: int) -> str:
    name = f"lf_bench_{n}_{uuid.uuid4().hex[:4]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{name}"')
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.engine import URL
    from psycopg.conninfo import conninfo_to_dict
    d = conninfo_to_dict(make_conninfo(ADMIN_URL, dbname=name))
    host = d.get("host")
    os.environ["MIGRATION_DATABASE_URL"] = URL.create("postgresql+psycopg", username=d.get("user"), password=d.get("password"),
        host=None if host.startswith("/") else host, database=name, query={"host": host} if host.startswith("/") else {}).render_as_string(hide_password=False)
    cfg = Config(str(ROOT / "backend/alembic.ini")); cfg.set_main_option("script_location", str(ROOT / "backend/alembic"))
    command.upgrade(cfg, "head")
    return name


def load(conn, n: int, rng: np.random.Generator) -> dict:
    conn.execute("SET session_replication_role = replica")        # skip audit/outbox triggers for the bulk load
    conn.execute("SET maintenance_work_mem = '1GB'")
    conn.execute("DROP INDEX embedding_text_hnsw; DROP INDEX embedding_image_hnsw")
    with conn.cursor() as cur:
        cur.executemany("INSERT INTO users (name,email,password_hash) VALUES (%s,%s,'x')",
                        [(f"U{i}", f"u{i}@bench.io") for i in range(500)])
        cur.executemany("INSERT INTO location (location_name,campus) VALUES (%s,'Bench')", [(f"L{i}",) for i in range(40)])
    k = max(20, n // 50)                                           # clusters = "kinds of object"
    ct, ci = rng.normal(size=(k, 384)), rng.normal(size=(k, 512))
    ct /= np.linalg.norm(ct, axis=1, keepdims=True); ci /= np.linalg.norm(ci, axis=1, keepdims=True)
    today = date.today()
    t0 = time.time()
    with conn.cursor() as cur:
        with cur.copy("COPY item (reporter_id,location_id,item_type,status,title,description,category,date_lost_or_found) FROM STDIN") as cp:
            for i in range(n):
                typ = "lost" if i % 2 == 0 else "found"
                st = "open" if rng.random() < .8 else rng.choice(["matched", "claimed", "returned", "closed"])
                if typ == "lost" and st in ("claimed",): st = "open"
                day = today - timedelta(days=int(rng.integers(1, 180)))
                cp.write_row((int(rng.integers(1, 501)), int(rng.integers(1, 41)), typ, st, f"item {i} title", f"description of item {i}",
                              CATS[int(rng.integers(len(CATS)))], day))
        ids = [r[0] for r in conn.execute("SELECT item_id FROM item ORDER BY item_id")]
        with cur.copy("COPY embedding (item_id,text_vect,image_vector,model_name) FROM STDIN") as cp:
            for item_id in ids:
                c = int(rng.integers(k))
                t = ct[c] + 0.45 * rng.normal(size=384) / np.sqrt(384) * 3; t /= np.linalg.norm(t)
                im = None
                if rng.random() < .5:
                    im = ci[c] + 0.45 * rng.normal(size=512) / np.sqrt(512) * 3; im /= np.linalg.norm(im)
                cp.write_row((item_id, vec_text(t), None if im is None else vec_text(im), "bench"))
    load_s = time.time() - t0
    t0 = time.time()
    conn.execute("CREATE INDEX embedding_text_hnsw ON embedding USING hnsw (text_vect vector_cosine_ops) WITH (m=16, ef_construction=64)")
    t_text = time.time() - t0; t0 = time.time()
    conn.execute("CREATE INDEX embedding_image_hnsw ON embedding USING hnsw (image_vector vector_cosine_ops) WITH (m=16, ef_construction=64) WHERE image_vector IS NOT NULL")
    t_img = time.time() - t0
    conn.execute("RESET session_replication_role")
    conn.execute("ANALYZE")
    return {"load_s": load_s, "hnsw_text_s": t_text, "hnsw_image_s": t_img, "ids": ids}


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


def run(n: int, queries: int, qdrant_url: str | None, save_explain: bool) -> dict:
    rng = np.random.default_rng(n)
    name = make_db(n)
    conn = psycopg.connect(make_conninfo(ADMIN_URL, dbname=name), autocommit=True)
    info = load(conn, n, rng)
    probes = [r[0] for r in conn.execute("SELECT item_id FROM item WHERE status='open' ORDER BY random() LIMIT %s", (queries,))]
    lat, agree, _scores = [], [], []
    for p in probes:
        t0 = time.perf_counter()
        hnsw = [r[0] for r in conn.execute("SELECT candidate_id FROM find_matches(%s, 10, 0, 0)", (p,))]
        lat.append((time.perf_counter() - t0) * 1000)
        conn.execute("SET enable_indexscan = off; SET enable_bitmapscan = off")
        exact = [r[0] for r in conn.execute("SELECT candidate_id FROM find_matches(%s, 10, 0, 0)", (p,))]
        conn.execute("RESET enable_indexscan; RESET enable_bitmapscan")
        if exact:
            agree.append(len(set(hnsw) & set(exact)) / len(exact))
    out = {"n": n, "p50": statistics.median(lat), "p95": pct(lat, .95), "agree": statistics.mean(agree) if agree else float("nan"), **info}
    # exact-scan latency (what you'd pay without HNSW)
    ex_lat = []
    for p in probes[:min(30, len(probes))]:
        conn.execute("SET enable_indexscan = off; SET enable_bitmapscan = off")
        t0 = time.perf_counter(); conn.execute("SELECT candidate_id FROM find_matches(%s, 10, 0, 0)", (p,)).fetchall()
        ex_lat.append((time.perf_counter() - t0) * 1000)
        conn.execute("RESET enable_indexscan; RESET enable_bitmapscan")
    out["exact_p50"] = statistics.median(ex_lat)
    if qdrant_url:
        out.update(qdrant_bench(conn, name, qdrant_url, probes))
    if save_explain:
        explain(conn, n, probes[0])
    conn.close()
    with psycopg.connect(ADMIN_URL, autocommit=True) as c:
        c.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
    return out


def qdrant_bench(conn, name, url, probes) -> dict:
    os.environ["DATABASE_URL"] = os.environ["MIGRATION_DATABASE_URL"]
    os.environ["QDRANT_URL"] = url
    os.environ["MATCH_MIN_TEXT"] = os.environ["MATCH_MIN_IMAGE"] = "-1"   # same "no similarity floor" as find_matches(..., 0, 0) below
    os.environ["MATCH_TOP_N"] = "10"
    from app import matching, qdrant_store as qs
    from app.config import get_settings
    from app.db import get_engine
    from app.stores import get_qdrant
    get_settings.cache_clear(); get_engine.cache_clear()
    c = get_qdrant()
    if c.collection_exists(qs.COLLECTION): c.delete_collection(qs.COLLECTION)
    qs._ready.discard(id(c))
    qs.ensure_collection(c)
    t0 = time.time(); 
    for r in conn.execute("""SELECT i.item_id, i.item_type::text, i.status::text, i.category::text, i.location_id, i.date_lost_or_found,
                                    e.text_vect::text, e.image_vector::text FROM item i JOIN embedding e USING (item_id)"""):
        it = {"item_id": r[0], "item_type": r[1], "status": r[2], "category": r[3], "location_id": r[4], "date_lost_or_found": r[5]}
        parse = lambda s: None if s is None else [float(x) for x in s.strip("[]").split(",")]
        qs.upsert_item(c, it, parse(r[6]), parse(r[7]))
    load_s = time.time() - t0
    lat, agree = [], []
    with get_engine().connect() as sa:
        for p in probes:
            t0 = time.perf_counter(); cands = matching.qdrant_candidates(sa, p); lat.append((time.perf_counter() - t0) * 1000)
            conn.execute("SET enable_indexscan = off; SET enable_bitmapscan = off")
            exact = [r[0] for r in conn.execute("SELECT candidate_id FROM find_matches(%s, 10, 0, 0)", (p,))]
            conn.execute("RESET enable_indexscan; RESET enable_bitmapscan")
            ours = [x.candidate_id for x in cands]
            if exact: agree.append(len(set(ours) & set(exact)) / len(exact))
    return {"q_p50": statistics.median(lat), "q_p95": pct(lat, .95), "q_agree": statistics.mean(agree) if agree else float("nan"), "q_load_s": load_s}


def explain(conn, n: int, probe: int) -> None:
    outdir = ROOT / "docs" / "explain"; outdir.mkdir(parents=True, exist_ok=True)
    qv = conn.execute("SELECT text_vect::text FROM embedding WHERE item_id=%s", (probe,)).fetchone()[0]
    cases = {
        "hnsw_text_knn": f"SELECT item_id FROM embedding ORDER BY text_vect <=> '{qv}'::vector LIMIT 10",
        "fulltext_gin": "SELECT item_id FROM item WHERE search_tsv @@ websearch_to_tsquery('english','item 4242 title')",
        "open_items_partial": "SELECT item_id FROM item WHERE status='open' AND item_type='found' AND category='keys' AND date_lost_or_found >= current_date - 30",
        "find_matches_function": f"SELECT * FROM find_matches({probe}, 10, 0, 0)",
    }
    for key, q in cases.items():
        conn.execute(q).fetchall()                      # warm the cache: plans below show steady-state, not first-touch disk reads
        with_idx = "\n".join(r[0] for r in conn.execute("EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF) " + q))
        conn.execute("SET enable_indexscan = off; SET enable_bitmapscan = off")
        without = "\n".join(r[0] for r in conn.execute("EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF) " + q))
        conn.execute("RESET enable_indexscan; RESET enable_bitmapscan")
        (outdir / f"{key}_{n}.txt").write_text(f"-- {q[:200]}\n\n== with indexes ==\n{with_idx}\n\n== indexes disabled ==\n{without}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[1000, 10000, 100000])
    ap.add_argument("--queries", type=int, default=100)
    ap.add_argument("--qdrant-url")
    a = ap.parse_args()
    results = []
    for n in a.sizes:
        print(f"== {n} items", flush=True)
        r = run(n, a.queries, a.qdrant_url, save_explain=(n == max(a.sizes)))
        results.append(r); print(r, flush=True)
    srv = psycopg.connect(ADMIN_URL).execute("SHOW server_version").fetchone()[0]
    lines = ["# Matching benchmark", "",
             f"Generated by `scripts/benchmark.py` on {platform.platform()}, {os.cpu_count()} CPUs, PostgreSQL {srv} + pgvector.",
             "Synthetic clustered vectors (384-d text, 512-d image on half the items), 80% of items open, queries are random open items,",
             "`find_matches(item, 10, 0, 0)` = full filter + text ranking + image ranking + RRF fusion in SQL. Agreement = |HNSW top-10 ∩ exact top-10| / 10.", "",
             "| items | HNSW build (text / image) | find_matches p50 | p95 | exact-scan p50 | HNSW top-10 agreement |", "|---:|---:|---:|---:|---:|---:|"]
    for r in results:
        lines.append(f"| {r['n']:,} | {r['hnsw_text_s']:.1f}s / {r['hnsw_image_s']:.1f}s | {r['p50']:.1f} ms | {r['p95']:.1f} ms | {r['exact_p50']:.1f} ms | {r['agree']*100:.1f}% |")
    if a.qdrant_url:
        lines += ["", "## Qdrant backend (filtered ANN per modality + RRF in Python)", "", "| items | index load | p50 | p95 | top-10 agreement vs exact |", "|---:|---:|---:|---:|---:|"]
        for r in results:
            lines.append(f"| {r['n']:,} | {r['q_load_s']:.1f}s | {r['q_p50']:.1f} ms | {r['q_p95']:.1f} ms | {r['q_agree']*100:.1f}% |")
    (ROOT / "docs" / "benchmark.generated.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
