"""Matching engine: RRF fusion, candidate filtering, persistence, idempotence."""
import numpy as np
import pytest

from .factory import Factory, near, unit

K = 60


@pytest.fixture
def m(db):
    f = Factory(db)
    rng = np.random.default_rng(42)
    base_t, base_i = unit(rng, 384), unit(rng, 512)
    w = dict(f=f, rng=rng, base_t=base_t, base_i=base_i, loc=f.location(), staff=f.user("staff"),
             owner=f.user(), finder=f.user())
    w["lost"] = f.item(w["owner"], w["loc"], "lost", date="2025-01-10", text_vec=base_t, image_vec=base_i)
    return w


def found(m, noise_t, noise_i=None, **kw):
    f, rng = m["f"], m["rng"]
    return f.item(m["finder"], m["loc"], "found", date=kw.pop("date", "2025-01-12"),
                  text_vec=near(m["base_t"], rng, noise_t),
                  image_vec=None if noise_i is None else near(m["base_i"], rng, noise_i), **kw)


def candidates(db, item):
    return db.execute("SELECT candidate_id, rrf_score, boost, text_score, image_score, text_rank, image_rank "
                      "FROM find_matches(%s)", (item,)).fetchall()


def test_rrf_fuse_formula(db):
    one = lambda q, *a: db.execute(q, a).fetchone()[0]
    assert one("SELECT rrf_fuse(1,1)") == pytest.approx(2 / (K + 1))
    assert one("SELECT rrf_fuse(1,NULL)") == pytest.approx(1 / (K + 1))
    assert one("SELECT rrf_fuse(NULL,3)") == pytest.approx(1 / (K + 3))
    assert one("SELECT rrf_fuse(2,5,10)") == pytest.approx(1 / 12 + 1 / 15)     # custom k
    assert one("SELECT rrf_fuse(NULL,NULL)") is None


def test_text_ranking_orders_by_similarity_and_gates_noise(db, m):
    best, ok = found(m, 0.3), found(m, 1.0)
    junk = m["f"].item(m["finder"], m["loc"], "found", date="2025-01-12",
                       text_vec=unit(m["rng"], 384))                      # unrelated
    rows = candidates(db, m["lost"])
    ids = [r[0] for r in rows]
    assert ids == [best, ok] and junk not in ids                           # junk gated out by min similarity
    assert rows[0][5] == 1 and rows[1][5] == 2                             # text ranks
    assert rows[0][1] == pytest.approx(1 / (K + 1))                        # single ranking => 1/(k+rank)
    assert rows[0][3] > rows[1][3]


def test_candidate_filters(db, m):
    f = m["f"]
    good = found(m, 0.3)
    found(m, 0.3, date="2025-01-05")                                       # found BEFORE it was lost: impossible
    closed = found(m, 0.3)
    db.execute("UPDATE item SET status='closed' WHERE item_id=%s", (closed,))
    same_type = f.item(m["owner"], m["loc"], "lost", text_vec=near(m["base_t"], m["rng"], 0.1))
    assert [r[0] for r in candidates(db, m["lost"])] == [good]
    assert same_type not in [r[0] for r in candidates(db, m["lost"])]


def test_image_and_text_fuse(db, m):
    a = found(m, 0.3, 1.5)          # best text, worse image
    b = found(m, 0.8, 0.2)          # worse text, best image
    rows = {r[0]: r for r in candidates(db, m["lost"])}
    assert rows[a][5] == 1 and rows[a][6] == 2
    assert rows[b][5] == 2 and rows[b][6] == 1
    assert rows[a][1] == pytest.approx(1 / (K + 1) + 1 / (K + 2))          # both rankings contribute
    assert rows[a][1] == pytest.approx(rows[b][1])                         # symmetric ranks => equal RRF


def test_candidate_without_image_still_ranks_on_text_only(db, m):
    c = found(m, 0.3, None)
    row = candidates(db, m["lost"])[0]
    assert row[0] == c and row[4] is None and row[6] is None


def test_boost_is_separate_from_rrf(db, m):
    c = found(m, 0.3, category="wallet_bag", color="black")
    row = candidates(db, m["lost"])[0]
    assert row[0] == c
    assert row[2] == pytest.approx(0.0020 + 0.0010 + 0.0005)               # category + location + colour
    assert row[1] == pytest.approx(1 / (K + 1))                            # rrf_score untouched by boost


def test_refresh_matches_persists_pair_and_is_idempotent(db, m):
    c = found(m, 0.3)
    r1 = db.execute("SELECT * FROM refresh_matches(%s)", (m["lost"],)).fetchall()
    assert len(r1) == 1 and r1[0][1] == c and r1[0][3] is True
    r2 = db.execute("SELECT * FROM refresh_matches(%s)", (m["lost"],)).fetchall()
    assert r2[0][0] == r1[0][0] and r2[0][3] is False                      # same match row, not new
    assert db.execute("SELECT count(*) FROM match").fetchone()[0] == 1
    assert db.execute("SELECT pair_key FROM match").fetchone()[0] == f"{m['lost']}:{c}"
    assert dict(db.execute("SELECT role::text, item_id FROM match_item").fetchall()) == \
        {"lost": m["lost"], "found": c}
    # re-running from the OTHER side must hit the same normalised pair
    db.execute("SELECT * FROM refresh_matches(%s)", (c,))
    assert db.execute("SELECT count(*) FROM match").fetchone()[0] == 1


def test_rejected_pair_is_never_resuggested(db, m):
    found(m, 0.3)
    mid = db.execute("SELECT out_match_id FROM refresh_matches(%s)", (m["lost"],)).fetchone()[0]
    db.execute("SELECT reject_match(%s,%s)", (mid, m["staff"]))
    assert db.execute("SELECT * FROM refresh_matches(%s)", (m["lost"],)).fetchall() == []
    assert db.execute("SELECT verification_status::text FROM match").fetchone()[0] == "rejected"


def test_only_open_items_are_matched(db, m):
    found(m, 0.3)
    db.execute("UPDATE item SET status='closed' WHERE item_id=%s", (m["lost"],))
    assert db.execute("SELECT * FROM refresh_matches(%s)", (m["lost"],)).fetchall() == []


def test_confirm_match_marks_items_and_rejects_rival_suggestions(db, m):
    c1, c2 = found(m, 0.3), found(m, 0.6)
    db.execute("SELECT * FROM refresh_matches(%s)", (m["lost"],))
    mid1 = db.execute("SELECT match_id FROM match WHERE pair_key=%s", (f"{m['lost']}:{c1}",)).fetchone()[0]
    db.execute("SELECT confirm_match(%s,%s)", (mid1, m["staff"]))
    f = m["f"]
    assert f.status(m["lost"]) == "matched" and f.status(c1) == "matched" and f.status(c2) == "open"
    st = dict(db.execute("SELECT pair_key, verification_status::text FROM match").fetchall())
    assert st[f"{m['lost']}:{c1}"] == "confirmed" and st[f"{m['lost']}:{c2}"] == "rejected"


def test_no_embedding_means_no_matches(db, m):
    bare = m["f"].item(m["owner"], m["loc"], "lost")
    assert candidates(db, bare) == []


def test_limit_keeps_the_best_candidates_not_the_lowest_ids(db, m):
    """Regression: results are ordered by fused score. Candidates are inserted WORST first, so the best one has the
    HIGHEST item_id; a query that sorted by id (or anything but score) would return the wrong three."""
    cands = [found(m, 2.0 - 0.15 * n) for n in range(12)]        # similarity rises with n, so does item_id
    rows = db.execute("SELECT candidate_id FROM find_matches(%s, 3, 0.0, 0.0)", (m["lost"],)).fetchall()
    assert [r[0] for r in rows] == [cands[11], cands[10], cands[9]]
