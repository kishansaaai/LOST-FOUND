"""Procedures: approve/reject/return and the approval cascade trigger."""
import psycopg
import pytest

from .factory import Factory


@pytest.fixture
def w(db):
    f = Factory(db)
    w = dict(f=f, finder=f.user(), a=f.user(), b=f.user(), staff=f.user("staff"), admin=f.user("admin"),
             loc=f.location())
    w["found"] = f.item(w["finder"], w["loc"], "found")
    return w


def test_approve_cascade(db, w):
    f = w["f"]
    c1, c2 = f.claim(w["found"], w["a"]), f.claim(w["found"], w["b"])
    db.execute("SELECT approve_claim(%s,%s,'looks right')", (c1, w["staff"]))
    rows = dict(db.execute("SELECT claim_id, result::text FROM claim").fetchall())
    assert rows == {c1: "approved", c2: "denied"}                 # competitor auto-rejected
    assert f.status(w["found"]) == "claimed"                       # item moved
    note = db.execute("SELECT notes FROM claim WHERE claim_id=%s", (c2,)).fetchone()[0]
    assert "Auto-rejected" in note


def test_late_claim_on_claimed_item_refused(db, w):
    f = w["f"]
    c1 = f.claim(w["found"], w["a"])
    db.execute("SELECT approve_claim(%s,%s)", (c1, w["staff"]))
    with pytest.raises(psycopg.errors.Error) as e:
        f.claim(w["found"], w["b"])
    assert e.value.sqlstate == "LF002"


def test_non_staff_cannot_decide(db, w):
    c = w["f"].claim(w["found"], w["a"])
    for fn in ("approve_claim", "reject_claim", "start_claim_review"):
        with pytest.raises(psycopg.errors.Error) as e:
            db.execute(f"SELECT {fn}(%s,%s)", (c, w["b"]))
        assert e.value.sqlstate == "LF001"


def test_review_then_approve_and_double_decision_refused(db, w):
    c = w["f"].claim(w["found"], w["a"])
    assert db.execute("SELECT (start_claim_review(%s,%s)).verification_status::text",
                      (c, w["staff"])).fetchone()[0] == "under_review"
    db.execute("SELECT approve_claim(%s,%s)", (c, w["staff"]))
    with pytest.raises(psycopg.errors.Error) as e:
        db.execute("SELECT approve_claim(%s,%s)", (c, w["staff"]))
    assert e.value.sqlstate == "LF002"


def test_reject_leaves_item_claimable(db, w):
    f = w["f"]
    c1 = f.claim(w["found"], w["a"])
    db.execute("SELECT reject_claim(%s,%s,'proof does not match')", (c1, w["staff"]))
    assert f.status(w["found"]) == "open"
    f.claim(w["found"], w["b"])                                    # next person can claim


def test_missing_claim_is_not_found(db, w):
    with pytest.raises(psycopg.errors.Error) as e:
        db.execute("SELECT approve_claim(9999,%s)", (w["staff"],))
    assert e.value.sqlstate == "LF003"


def test_end_to_end_return_marks_matched_lost_report_too(db, w):
    f = w["f"]
    lost = f.item(w["a"], w["loc"], "lost")
    k = f"{lost}:{w['found']}"
    with db.transaction():          # match + its two participants commit together (deferred integrity check)
        mid = db.execute("INSERT INTO match (pair_key,rrf_score,text_score,text_rank) VALUES (%s,0.03,.9,1) RETURNING match_id",
                         (k,)).fetchone()[0]
        db.execute("INSERT INTO match_item VALUES (%s,%s,'lost'),(%s,%s,'found')", (mid, lost, mid, w["found"]))
    db.execute("SELECT confirm_match(%s,%s)", (mid, w["staff"]))
    assert (f.status(lost), f.status(w["found"])) == ("matched", "matched")
    c = f.claim(w["found"], w["a"], match_id=mid)
    db.execute("SELECT approve_claim(%s,%s)", (c, w["staff"]))
    assert f.status(w["found"]) == "claimed"
    db.execute("SELECT mark_returned(%s,%s)", (w["found"], w["staff"]))
    assert (f.status(lost), f.status(w["found"])) == ("returned", "returned")


def test_mark_returned_requires_claimed_found_item(db, w):
    with pytest.raises(psycopg.errors.Error) as e:
        db.execute("SELECT mark_returned(%s,%s)", (w["found"], w["staff"]))
    assert e.value.sqlstate == "LF002"


def test_close_item_by_reporter_only_or_staff(db, w):
    with pytest.raises(psycopg.errors.Error) as e:
        db.execute("SELECT close_item(%s,%s)", (w["found"], w["a"]))
    assert e.value.sqlstate == "LF001"
    db.execute("SELECT close_item(%s,%s)", (w["found"], w["finder"]))
    assert w["f"].status(w["found"]) == "closed"
