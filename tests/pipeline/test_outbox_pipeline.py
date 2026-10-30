"""End to end through the outbox: SQL write -> worker -> embeddings, Qdrant, Mongo, Redis, matches."""
import pytest

from app import matching, notify, outbox, qdrant_store
from tests.db.factory import Factory


@pytest.fixture
def env(db, engine_rw, fake_stores, app_settings):
    f = Factory(db)
    return dict(f=f, db=db, eng=engine_rw, s=fake_stores, owner=f.user(name="Olive Owner"),
                finder=f.user(name="Finn Finder"), staff=f.user("staff"), loc=f.location("Library"))


def report(e, kind, title, desc, **kw):
    return e["f"].item(e["owner"] if kind == "lost" else e["finder"], e["loc"], kind, title=title,
                       description=desc, date="2025-01-10" if kind == "lost" else "2025-01-12", **kw)


def pending(e):
    return e["db"].execute("SELECT count(*) FROM outbox WHERE processed_at IS NULL").fetchone()[0]


def test_full_pipeline_creates_embeddings_points_matches_and_notifications(env):
    lost = report(env, "lost", "Black leather wallet", "black leather wallet with student card and some cash")
    found = report(env, "found", "Wallet found", "found a black leather wallet with a student card inside")
    other = report(env, "found", "Blue umbrella", "folding umbrella blue with wooden handle", category="other")
    assert pending(env) > 0

    outbox.drain(env["eng"])
    db = env["db"]
    assert pending(db and env) == 0
    # 1. embeddings computed by the worker
    assert db.execute("SELECT count(*) FROM embedding").fetchone()[0] == 3
    # 2. Qdrant has one point per item with status payload
    pts = {p.id: p.payload for p in env["s"].qdrant.scroll(qdrant_store.COLLECTION, limit=10)[0]}
    assert set(pts) == {lost, found, other} and pts[lost]["item_type"] == "lost"
    # 3. exactly the right pair matched, the umbrella is not suggested
    pairs = [r[0] for r in db.execute("SELECT pair_key FROM match").fetchall()]
    assert pairs == [f"{lost}:{found}"]
    # 4. both reporters were notified once, in Mongo, with real-time publish
    notes = list(env["s"].mongo.notifications.find({"type": "match.suggested"}))
    assert sorted(n["user_id"] for n in notes) == sorted([env["owner"], env["finder"]])
    # 5. cache namespaces were invalidated (version counters bumped)
    assert int(env["s"].redis.get("lf:ver:items")) > 1
    # 6. activity feed
    assert env["s"].mongo.activity_feed.count_documents({"type": "item.reported"}) == 3


def test_worker_is_idempotent_on_replay(env):
    report(env, "lost", "Black leather wallet", "black leather wallet with student card")
    report(env, "found", "Wallet found", "black leather wallet with student card inside")
    outbox.drain(env["eng"])
    before = (env["db"].execute("SELECT count(*) FROM match").fetchone()[0],
              env["s"].mongo.notifications.count_documents({}))
    env["db"].execute("UPDATE outbox SET processed_at = NULL")            # force a full replay
    outbox.drain(env["eng"])
    after = (env["db"].execute("SELECT count(*) FROM match").fetchone()[0],
             env["s"].mongo.notifications.count_documents({}))
    assert before == after                                                 # no duplicates anywhere


def test_failed_event_is_retried_not_lost(env, monkeypatch):
    report(env, "lost", "Black leather wallet", "black leather wallet with student card")
    boom = {"on": True}
    real = qdrant_store.upsert_item

    def flaky(*a, **k):
        if boom["on"]:
            raise ConnectionError("qdrant down")
        return real(*a, **k)

    monkeypatch.setattr(qdrant_store, "upsert_item", flaky)
    outbox.process_batch(env["eng"])
    outbox.process_batch(env["eng"])
    row = env["db"].execute("SELECT attempts, last_error FROM outbox WHERE aggregate='embedding'").fetchone()
    assert row[0] >= 1 and "qdrant down" in row[1]
    boom["on"] = False                                                     # store recovers
    outbox.drain(env["eng"])
    assert env["db"].execute("SELECT count(*) FROM outbox WHERE processed_at IS NULL AND attempts < 8").fetchone()[0] == 0
    assert len(env["s"].qdrant.scroll(qdrant_store.COLLECTION, limit=10)[0]) == 1


def test_editing_text_reembeds_but_status_change_does_not(env):
    lost = report(env, "lost", "Black wallet", "black leather wallet")
    outbox.drain(env["eng"])
    h1 = env["db"].execute("SELECT content_hash FROM embedding WHERE item_id=%s", (lost,)).fetchone()[0]
    env["db"].execute("SELECT close_item(%s,%s)", (lost, env["owner"]))
    env["db"].execute("UPDATE item SET status='open' WHERE item_id=%s", (lost,))
    outbox.drain(env["eng"])
    assert env["db"].execute("SELECT content_hash FROM embedding WHERE item_id=%s", (lost,)).fetchone()[0] == h1
    env["db"].execute("UPDATE item SET description='red nylon backpack' WHERE item_id=%s", (lost,))
    outbox.drain(env["eng"])
    assert env["db"].execute("SELECT content_hash FROM embedding WHERE item_id=%s", (lost,)).fetchone()[0] != h1


def test_status_change_updates_qdrant_payload_so_closed_items_leave_the_index_filter(env):
    report(env, "lost", "Black wallet", "black leather wallet")
    found = report(env, "found", "Black wallet", "black leather wallet")
    outbox.drain(env["eng"])
    env["db"].execute("SELECT close_item(%s,%s)", (found, env["finder"]))
    outbox.drain(env["eng"])
    p = env["s"].qdrant.retrieve(qdrant_store.COLLECTION, ids=[found])[0].payload
    assert p["status"] == "closed"


def test_claim_lifecycle_notifications(env):
    found = report(env, "found", "Black wallet", "black leather wallet")
    claimant = env["f"].user(name="Cleo Claimant")
    c = env["f"].claim(found, claimant)
    outbox.drain(env["eng"])
    types = {n["type"] for n in env["s"].mongo.notifications.find()}
    assert {"claim.submitted", "claim.queue"} <= types
    env["db"].execute("SELECT approve_claim(%s,%s)", (c, env["staff"]))
    outbox.drain(env["eng"])
    approved = env["s"].mongo.notifications.find_one({"type": "claim.approved"})
    assert approved["user_id"] == claimant
    env["s"].mongo.notifications.find_one({"audience": "staff"})
    assert notify.unread_count(env["staff"], True) >= 1 and notify.unread_count(claimant, False) == 1
    notify.mark_read(claimant, False)
    assert notify.unread_count(claimant, False) == 0


def test_item_extras_flow_through_outbox(env):
    found = report(env, "found", "Laptop", "silver laptop", category="electronics")
    env["db"].execute("INSERT INTO outbox (aggregate, aggregate_id, event_type, payload) VALUES "
                      "('item_extras', %s, 'item_extras.set', %s::jsonb)",
                      (found, '{"item_id": %d, "category": "electronics", "extras": {"serial_number": "C02XYZ"}}' % found))
    outbox.drain(env["eng"])
    assert notify.get_extras(found) == {"serial_number": "C02XYZ"}


def test_python_rrf_matches_sql_rrf(env):
    for r1 in (1, 2, 7, None):
        for r2 in (1, 5, None):
            sql = env["db"].execute("SELECT rrf_fuse(%s,%s)", (r1, r2)).fetchone()[0]
            py = matching.rrf_fuse(r1, r2)
            assert (sql is None and py is None) or sql == pytest.approx(py)


def test_qdrant_backend_agrees_with_pg_backend(env):
    """Both backends must produce the same pairs and the same ranks on the same data."""
    for _n, (t, d) in enumerate([("black leather wallet", "black leather wallet with student card"),
                                ("silver laptop", "silver laptop with stickers and a dell charger"),
                                ("red umbrella", "red umbrella with a bent handle")]):
        report(env, "lost", t, d, category="other")
        report(env, "found", f"Found {t}", d + " found at the desk", category="other")
    outbox.drain(env["eng"])                                               # pg backend matches
    pg = sorted(env["db"].execute("SELECT pair_key, text_rank, round(rrf_score::numeric,6) FROM match").fetchall())
    env["db"].execute("DELETE FROM match")                                 # owner can; app_rw cannot
    with env["eng"].begin() as conn:
        for (item_id,) in env["db"].execute("SELECT item_id FROM item WHERE item_type='lost'").fetchall():
            matching.refresh_matches(conn, item_id, backend="qdrant")
    qd = sorted(env["db"].execute("SELECT pair_key, text_rank, round(rrf_score::numeric,6) FROM match").fetchall())
    assert pg and [p[0] for p in pg] == [q[0] for q in qd]
    assert [p[1:] for p in pg] == [q[1:] for q in qd]
