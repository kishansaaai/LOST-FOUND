"""Triggers: item/claim state machines and match structural integrity."""
import psycopg
import pytest

from .factory import Factory


def lf002(excinfo):
    return excinfo.value.sqlstate == "LF002"


@pytest.fixture
def world(db):
    f = Factory(db)
    w = dict(f=f, owner=f.user(), claimant=f.user(), staff=f.user("staff"), loc=f.location())
    w["found"] = f.item(w["owner"], w["loc"], "found")
    w["lost"] = f.item(w["claimant"], w["loc"], "lost")
    return w


def set_status(db, item, status):
    db.execute("UPDATE item SET status=%s WHERE item_id=%s", (status, item))


def test_legal_and_illegal_item_transitions(db, world):
    set_status(db, world["found"], "matched")
    set_status(db, world["found"], "open")
    set_status(db, world["found"], "closed")
    set_status(db, world["found"], "open")            # staff reopen is allowed
    with pytest.raises(psycopg.errors.Error) as e:
        set_status(db, world["found"], "returned")    # open -> returned is not an edge
    assert lf002(e)


def test_cannot_claim_or_return_without_approved_claim(db, world):
    with pytest.raises(psycopg.errors.Error) as e:
        set_status(db, world["found"], "claimed")
    assert lf002(e)
    set_status(db, world["found"], "matched")
    with pytest.raises(psycopg.errors.Error) as e:
        set_status(db, world["found"], "returned")    # edge exists, guard (approved claim) fails
    assert lf002(e)


def test_lost_item_cannot_be_claimed(db, world):
    with pytest.raises(psycopg.errors.Error) as e:
        set_status(db, world["lost"], "claimed")
    assert lf002(e)


def test_item_type_and_reporter_immutable(db, world):
    with pytest.raises(psycopg.errors.Error) as e:
        db.execute("UPDATE item SET item_type='found' WHERE item_id=%s", (world["lost"],))
    assert lf002(e)
    with pytest.raises(psycopg.errors.Error) as e:
        db.execute("UPDATE item SET reporter_id=%s WHERE item_id=%s", (world["owner"], world["lost"]))
    assert lf002(e)


def test_new_item_must_start_open(db, world):
    with pytest.raises(psycopg.errors.Error) as e:
        db.execute("""INSERT INTO item (reporter_id,location_id,item_type,status,title,description,category,date_lost_or_found)
                      VALUES (%s,%s,'lost','claimed','abc','d','other','2025-01-01')""",
                   (world["owner"], world["loc"]))
    assert lf002(e)


def test_returned_is_terminal(db, world):
    f = world["f"]
    c = f.claim(world["found"], world["claimant"])
    db.execute("SELECT approve_claim(%s,%s)", (c, world["staff"]))
    db.execute("SELECT mark_returned(%s,%s)", (world["found"], world["staff"]))
    with pytest.raises(psycopg.errors.Error) as e:
        db.execute("UPDATE item SET title='changed' WHERE item_id=%s", (world["found"],))
    assert lf002(e)


def test_decided_claim_is_frozen(db, world):
    f = world["f"]
    c = f.claim(world["found"], world["claimant"])
    db.execute("SELECT reject_claim(%s,%s,'no')", (c, world["staff"]))
    with pytest.raises(psycopg.errors.Error) as e:
        db.execute("UPDATE claim SET notes='sneaky' WHERE claim_id=%s", (c,))
    assert lf002(e)


def test_claim_review_requires_staff_role(db, world):
    f = world["f"]
    c = f.claim(world["found"], world["claimant"])
    with pytest.raises(psycopg.errors.Error) as e:
        db.execute("UPDATE claim SET reviewed_by=%s WHERE claim_id=%s", (world["owner"], c))
    assert e.value.sqlstate == "LF001"


# ---- match structural integrity (deferred constraint trigger) -------------------
def insert_match(db, key, items):
    """Call inside `with db.transaction():` so the deferred integrity trigger sees the whole match."""
    mid = db.execute("INSERT INTO match (pair_key, rrf_score, text_score, text_rank) "
                     "VALUES (%s, 0.03, 0.9, 1) RETURNING match_id", (key,)).fetchone()[0]
    for item, role in items:
        db.execute("INSERT INTO match_item (match_id,item_id,role) VALUES (%s,%s,%s)", (mid, item, role))
    return mid


def test_match_needs_exactly_one_lost_and_one_found(db, world):
    k = f"{world['lost']}:{world['found']}"
    with db.transaction():                             # valid pair commits fine
        insert_match(db, k, [(world["lost"], "lost"), (world["found"], "found")])
    other_lost = world["f"].item(world["owner"], world["loc"], "lost")
    with pytest.raises(psycopg.errors.UniqueViolation):  # 2 lost: UNIQUE(match_id, role) fires immediately
        with db.transaction():
            insert_match(db, f"{world['lost']}:{other_lost}",
                         [(world["lost"], "lost"), (other_lost, "lost")])


def test_match_cannot_pair_item_with_itself(db, world):
    with pytest.raises(psycopg.errors.Error):
        with db.transaction():
            insert_match(db, f"{world['lost']}:{world['lost']}",
                         [(world["lost"], "lost"), (world["lost"], "found")])


def test_match_role_must_equal_item_type(db, world):
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.transaction():                          # roles swapped
            insert_match(db, f"{world['found']}:{world['lost']}",
                         [(world["found"], "lost"), (world["lost"], "found")])


def test_match_pair_is_unique_and_pair_key_must_agree(db, world):
    k = f"{world['lost']}:{world['found']}"
    with db.transaction():
        insert_match(db, k, [(world["lost"], "lost"), (world["found"], "found")])
    with pytest.raises(psycopg.errors.UniqueViolation):
        with db.transaction():
            insert_match(db, k, [(world["lost"], "lost"), (world["found"], "found")])
    with pytest.raises(psycopg.errors.CheckViolation):  # lying pair_key
        with db.transaction():
            insert_match(db, "999:999", [(world["lost"], "lost"), (world["found"], "found")])
