"""Audit trail and transactional outbox are written by triggers, atomically with the change."""
import json

import pytest

from .factory import Factory, unit
import numpy as np


@pytest.fixture
def w(db):
    f = Factory(db)
    return dict(f=f, u=f.user(), v=f.user(), staff=f.user("staff"), loc=f.location())


def audit(db, table, pk=None):
    q = "SELECT action, actor_id, old_data, new_data FROM audit_log WHERE table_name=%s"
    args = [table]
    if pk is not None:
        q += " AND row_pk=%s"; args.append(pk)
    return db.execute(q + " ORDER BY audit_id", args).fetchall()


def test_item_insert_and_update_are_audited_with_actor(db, w):
    item = w["f"].item(w["u"], w["loc"])
    db.execute("SELECT set_config('app.user_id', %s, false)", (str(w["staff"]),))
    db.execute("UPDATE item SET title='New title' WHERE item_id=%s", (item,))
    rows = audit(db, "item", item)
    assert [r[0] for r in rows] == ["INSERT", "UPDATE"]
    assert rows[1][1] == w["staff"]
    assert rows[1][2]["title"] == "Black backpack" and rows[1][3]["title"] == "New title"
    assert "search_tsv" not in rows[1][3]


def test_noop_update_not_audited(db, w):
    item = w["f"].item(w["u"], w["loc"])
    db.execute("UPDATE item SET title=title WHERE item_id=%s", (item,))
    assert len(audit(db, "item", item)) == 1


def test_password_hash_never_audited(db, w):
    db.execute("UPDATE users SET name='Renamed', password_hash='secret-new' WHERE user_id=%s", (w["u"],))
    rows = audit(db, "users", w["u"])
    assert len(rows) == 1 and "password_hash" not in json.dumps(rows[0][2:])


def test_claim_decision_audit_trail(db, w):
    found = w["f"].item(w["v"], w["loc"], "found")
    c = w["f"].claim(found, w["u"])
    db.execute("SELECT approve_claim(%s,%s)", (c, w["staff"]))
    acts = [(r[0], r[3]["result"]) for r in audit(db, "claim", c)]
    assert acts == [("INSERT", "pending"), ("UPDATE", "approved")]
    item_states = [r[3]["status"] for r in audit(db, "item", found)]
    assert item_states == ["open", "claimed"]


def test_outbox_events_per_aggregate(db, w):
    f = w["f"]
    f.item(w["u"], w["loc"], text_vec=unit(np.random.default_rng(3), 384))
    events = db.execute("SELECT aggregate, event_type FROM outbox ORDER BY outbox_id").fetchall()
    assert ("item", "item.insert") in events and ("embedding", "embedding.insert") in events
    found = f.item(w["v"], w["loc"], "found")
    c = f.claim(found, w["u"])
    payload = db.execute("SELECT payload FROM outbox WHERE aggregate='claim' AND aggregate_id=%s", (c,)).fetchone()[0]
    assert "proof_description" not in payload and payload["claimant_id"] == w["u"]


def test_outbox_rolls_back_with_the_business_write(db, w):
    before = db.execute("SELECT count(*) FROM outbox").fetchone()[0]
    with pytest.raises(RuntimeError):
        with db.transaction():
            w["f"].item(w["u"], w["loc"])
            raise RuntimeError("abort")
    assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == before    # no phantom event


def test_embedding_payload_has_no_vectors(db, w):
    w["f"].item(w["u"], w["loc"], text_vec=unit(np.random.default_rng(4), 384))
    p = db.execute("SELECT payload FROM outbox WHERE aggregate='embedding'").fetchone()[0]
    assert set(p) == {"item_id", "has_image"}
