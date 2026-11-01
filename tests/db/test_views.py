"""Views, window functions and materialized-view analytics."""
import pytest

from .factory import Factory


@pytest.fixture
def w(db):
    f = Factory(db)
    w = dict(f=f, finder=f.user(), a=f.user(), b=f.user(), staff=f.user("staff"),
             l1=f.location("Library"), l2=f.location("Cafeteria"))
    return w


def test_open_items_view_excludes_non_open_and_pii(db, w):
    f = w["f"]
    i1 = f.item(w["finder"], w["l1"], "found")
    i2 = f.item(w["finder"], w["l1"], "found", title="Phone")
    db.execute("UPDATE item SET status='closed' WHERE item_id=%s", (i2,))
    rows = db.execute("SELECT item_id FROM v_open_items").fetchall()
    assert rows == [(i1,)]
    cols = [d.name for d in db.execute("SELECT * FROM v_open_items").description]
    assert "email" not in cols and "phone" not in cols


def test_claim_queue_windows(db, w):
    f = w["f"]
    item = f.item(w["finder"], w["l1"], "found")
    c1, c2 = f.claim(item, w["a"]), f.claim(item, w["b"])
    rows = db.execute("SELECT claim_id, competing_claims, queue_position FROM v_claim_queue "
                      "ORDER BY queue_position").fetchall()
    assert rows == [(c1, 2, 1), (c2, 2, 2)]
    db.execute("SELECT approve_claim(%s,%s)", (c1, w["staff"]))
    assert db.execute("SELECT count(*) FROM v_claim_queue").fetchone()[0] == 0   # queue drains


def test_analytics_materialized_views(db, w):
    f = w["f"]
    for n in range(4):                                       # 4 found at the library, 1 at the cafeteria
        f.item(w["finder"], w["l1"], "found", title=f"Keys {n}", category="keys")
    kept = f.item(w["finder"], w["l2"], "found", title="Wallet", category="wallet_bag")
    c = f.claim(kept, w["a"])
    db.execute("SELECT approve_claim(%s,%s)", (c, w["staff"]))
    db.execute("SELECT mark_returned(%s,%s)", (kept, w["staff"]))
    db.execute("SELECT refresh_analytics()")

    rec = {r[0]: r for r in db.execute("SELECT category, found_items, returned_items, recovery_rate_pct "
                                       "FROM mv_recovery_stats").fetchall()}
    assert rec["ALL"][1:3] == (5, 1) and float(rec["ALL"][3]) == 20.0
    assert float(rec["wallet_bag"][3]) == 100.0 and float(rec["keys"][3]) == 0.0

    hot = db.execute("SELECT location_name, total_items, hotspot_rank FROM mv_location_hotspots "
                     "ORDER BY hotspot_rank").fetchall()
    assert hot[0] == ("Library", 4, 1) and hot[1] == ("Cafeteria", 1, 2)

    st = dict(((t, s), n) for t, s, n in db.execute("SELECT item_type::text,status::text,n FROM mv_status_counts"))
    assert st[("found", "returned")] == 1 and st[("found", "open")] == 4


def test_time_to_return_comes_from_audit_log(db, w):
    f = w["f"]
    item = f.item(w["finder"], w["l1"], "found")
    db.execute("UPDATE item SET reported_at = now() - interval '48 hours' WHERE item_id=%s", (item,))
    c = f.claim(item, w["a"])
    db.execute("SELECT approve_claim(%s,%s)", (c, w["staff"]))
    db.execute("SELECT mark_returned(%s,%s)", (item, w["staff"]))
    db.execute("SELECT refresh_analytics()")
    hours = db.execute("SELECT avg_hours_to_return FROM mv_recovery_stats WHERE category='ALL'").fetchone()[0]
    assert 47.9 <= float(hours) <= 48.2


def test_match_details_and_likely_owners(db, w):
    import numpy as np
    from .factory import near, unit
    f = w["f"]
    rng = np.random.default_rng(5)
    t = unit(rng, 384)
    found = f.item(w["finder"], w["l1"], "found", text_vec=t)
    l1 = f.item(w["a"], w["l1"], "lost", text_vec=near(t, rng, 0.2))
    l2 = f.item(w["b"], w["l1"], "lost", text_vec=near(t, rng, 0.9))
    db.execute("SELECT * FROM refresh_matches(%s)", (found,))
    rows = db.execute("SELECT lost_item_id, lost_reporter_id, owner_rank FROM v_likely_owners "
                      "WHERE found_item_id=%s ORDER BY owner_rank", (found,)).fetchall()
    assert rows == [(l1, w["a"], 1), (l2, w["b"], 2)]                     # closest description = most likely owner
    d = db.execute("SELECT lost_title, found_title, text_rank, image_rank FROM v_match_details LIMIT 1").fetchone()
    assert d[0] and d[1] and d[2] == 1 and d[3] is None
