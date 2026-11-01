"""Section 5: two staff members must never approve conflicting claims.

Deterministic proof (no sleeps-and-hope): session A approves claim 1 and holds its
transaction open; session B tries to approve claim 2 for the same item and is shown
to be BLOCKED on a lock by pg_stat_activity; only after A commits does B proceed,
and B then fails because its claim was auto-rejected by A's trigger.
"""
import threading
import time

import psycopg
import pytest

from .factory import Factory


@pytest.fixture
def setup(db):
    f = Factory(db)
    s = dict(finder=f.user(), a=f.user(), b=f.user(), s1=f.user("staff"), s2=f.user("staff"), loc=f.location())
    s["item"] = f.item(s["finder"], s["loc"], "found")
    s["c1"], s["c2"] = f.claim(s["item"], s["a"]), f.claim(s["item"], s["b"])
    return s


def wait_until_blocked(admin, pid, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        row = admin.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", (pid,)).fetchone()
        if row and row[0] == "Lock":
            return True
        time.sleep(0.02)
    return False


def test_second_approver_blocks_then_fails(db, connect, setup):
    s = setup
    a, b = connect("app_rw"), connect("app_rw")
    a.execute("SELECT approve_claim(%s,%s)", (s["c1"], s["s1"]))          # txn A open, holds item lock
    result = {}

    def session_b():
        try:
            b.execute("SELECT approve_claim(%s,%s)", (s["c2"], s["s2"]))
            b.commit()
            result["b"] = "approved"
        except psycopg.errors.Error as e:
            b.rollback()
            result["b"] = e.sqlstate

    t = threading.Thread(target=session_b)
    t.start()
    b_pid = None
    deadline = time.time() + 5
    while b_pid is None and time.time() < deadline:                        # find B's backend
        r = db.execute("SELECT pid FROM pg_stat_activity WHERE query ILIKE '%%approve_claim(%%' "
                       "AND pid NOT IN (%s, pg_backend_pid()) AND state='active'", (a.info.backend_pid,)).fetchone()
        b_pid = r[0] if r else None
        time.sleep(0.02)
    assert b_pid and wait_until_blocked(db, b_pid), "session B should be blocked waiting for A's lock"
    a.commit()
    t.join(5)
    assert result["b"] == "LF002"                                          # lost the race cleanly
    rows = dict(db.execute("SELECT claim_id, result::text FROM claim").fetchall())
    assert rows == {s["c1"]: "approved", s["c2"]: "denied"}
    assert db.execute("SELECT count(*) FROM claim WHERE item_id=%s AND result='approved'",
                      (s["item"],)).fetchone()[0] == 1


def test_stress_exactly_one_winner(db, connect):
    """20 rounds x 2 simultaneous approvers: always exactly one approved claim, no deadlock."""
    f = Factory(db)
    loc, finder, s1, s2 = f.location(), f.user(), f.user("staff"), f.user("staff")
    users = [f.user() for _ in range(40)]
    ca, cb = connect("app_rw", autocommit=True), connect("app_rw", autocommit=True)
    for n in range(20):
        item = f.item(finder, loc, "found", title=f"Wallet {n}")
        c1, c2 = f.claim(item, users[2 * n]), f.claim(item, users[2 * n + 1])
        outcomes = []
        barrier = threading.Barrier(2)

        def run(conn, claim, staff):
            barrier.wait()  # noqa: B023 (threads are joined inside the iteration)
            try:
                conn.execute("SELECT approve_claim(%s,%s)", (claim, staff))
                outcomes.append("ok")  # noqa: B023
            except psycopg.errors.Error as e:
                outcomes.append(e.sqlstate)  # noqa: B023

        ts = [threading.Thread(target=run, args=(ca, c1, s1)), threading.Thread(target=run, args=(cb, c2, s2))]
        [t.start() for t in ts]; [t.join(10) for t in ts]
        assert sorted(outcomes) == ["LF002", "ok"], outcomes
        assert db.execute("SELECT count(*) FROM claim WHERE item_id=%s AND result='approved'", (item,)).fetchone()[0] == 1


def test_unique_index_is_the_backstop_even_without_the_procedure(db, setup):
    """If someone bypasses approve_claim (raw UPDATEs, e.g. a buggy deploy), the
    partial unique index still refuses a second approved claim on the same item."""
    s = setup
    db.execute("SELECT approve_claim(%s,%s)", (s["c1"], s["s1"]))
    with pytest.raises(psycopg.errors.Error):
        db.execute("INSERT INTO claim (item_id,claimant_id,proof_description,verification_status,result,reviewed_by,reviewed_at) "
                   "VALUES (%s,%s,'x','verified','approved',%s,now())", (s["item"], s["b"], s["s2"]))


def test_concurrent_matching_does_not_deadlock(db, connect):
    """Regression: two sessions running refresh_matches over overlapping pairs in opposite orders used to deadlock."""
    import numpy as np
    from .factory import near, unit
    f = Factory(db)
    rng = np.random.default_rng(11)
    base = unit(rng, 384)
    loc, owner, finder = f.location(), f.user(), f.user()
    lost = [f.item(owner, loc, "lost", date="2025-01-01", text_vec=near(base, rng, 0.2)) for _ in range(8)]
    found = [f.item(finder, loc, "found", date="2025-01-05", text_vec=near(base, rng, 0.2)) for _ in range(8)]
    errors = []

    def run(order):
        conn = connect("app_rw", autocommit=True)
        for item in order:
            try:
                conn.execute("SELECT * FROM refresh_matches(%s, 20, 0.0, 0.0)", (item,)).fetchall()
            except psycopg.errors.Error as e:
                errors.append(e.sqlstate)

    a = threading.Thread(target=run, args=(lost + found,))
    b = threading.Thread(target=run, args=(list(reversed(found + lost)),))
    a.start(); b.start(); a.join(60); b.join(60)
    assert "40P01" not in errors, errors                      # 40P01 = deadlock_detected
    assert db.execute("SELECT count(*) FROM match").fetchone()[0] == 64   # every pair exactly once
