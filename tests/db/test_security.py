"""Least-privilege roles, column grants and row-level security."""
import psycopg
import pytest

from .factory import Factory


@pytest.fixture
def world(db):
    f = Factory(db)
    w = dict(f=f, alice=f.user(name="Alice"), bob=f.user(name="Bob"), finder=f.user(),
             staff=f.user("staff"), admin=f.user("admin"), loc=f.location())
    w["found"] = f.item(w["finder"], w["loc"], "found")
    w["ca"], w["cb"] = f.claim(w["found"], w["alice"]), f.claim(w["found"], w["bob"])
    return w


def as_user(conn, uid):
    conn.execute("SELECT set_config('app.user_id', %s, true)", (str(uid),))


def test_register_cannot_choose_role(connect, db):
    rw = connect("app_rw")
    rw.execute("INSERT INTO users (name,email,password_hash) VALUES ('N','n@x.io','h')")
    rw.commit()
    assert db.execute("SELECT role::text FROM users WHERE email='n@x.io'").fetchone()[0] == "user"
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        rw.execute("INSERT INTO users (name,email,password_hash,role) VALUES ('E','e@x.io','h','admin')")
    rw.rollback()
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        rw.execute("UPDATE users SET role='admin' WHERE email='n@x.io'")


def test_app_rw_cannot_write_status_or_delete(connect, world):
    rw = connect("app_rw")
    rw.execute("UPDATE item SET title='Renamed bag' WHERE item_id=%s", (world["found"],))   # allowed
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        rw.execute("UPDATE item SET status='closed' WHERE item_id=%s", (world["found"],))
    rw.rollback()
    for sql in ("DELETE FROM item", "DELETE FROM claim", "UPDATE claim SET result='approved'",
                "INSERT INTO audit_log (table_name,row_pk,action) VALUES ('x',1,'INSERT')",
                "UPDATE match SET verification_status='confirmed'"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            rw.execute(sql)
        rw.rollback()


def test_rls_users_see_only_their_own_claims(connect, world):
    rw = connect("app_rw")
    as_user(rw, world["alice"])
    assert [r[0] for r in rw.execute("SELECT claim_id FROM claim").fetchall()] == [world["ca"]]
    rw.rollback()
    as_user(rw, world["bob"])
    assert [r[0] for r in rw.execute("SELECT claim_id FROM claim").fetchall()] == [world["cb"]]
    rw.rollback()
    assert rw.execute("SELECT count(*) FROM claim").fetchone()[0] == 0          # no identity => nothing
    rw.rollback()
    as_user(rw, world["staff"])
    assert rw.execute("SELECT count(*) FROM claim").fetchone()[0] == 2          # staff see all


def test_rls_cannot_file_claim_as_someone_else(connect, world):
    rw = connect("app_rw")
    f2 = world["f"].item(world["finder"], world["loc"], "found", title="Umbrella")
    as_user(rw, world["alice"])
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        rw.execute("INSERT INTO claim (item_id,claimant_id,proof_description) VALUES (%s,%s,'p')",
                   (f2, world["bob"]))
    rw.rollback()
    as_user(rw, world["alice"])
    rw.execute("INSERT INTO claim (item_id,claimant_id,proof_description) VALUES (%s,%s,'p')",
               (f2, world["alice"]))                                            # as herself: fine


def test_claim_queue_view_respects_rls(connect, world):
    rw = connect("app_rw")
    as_user(rw, world["alice"])
    assert {r[0] for r in rw.execute("SELECT claim_id FROM v_claim_queue").fetchall()} == {world["ca"]}
    rw.rollback()
    as_user(rw, world["staff"])
    rows = rw.execute("SELECT competing_claims FROM v_claim_queue").fetchall()
    assert [r[0] for r in rows] == [2, 2]


def test_audit_log_is_staff_only(connect, world):
    rw = connect("app_rw")
    as_user(rw, world["alice"])
    assert rw.execute("SELECT count(*) FROM audit_log").fetchone()[0] == 0
    rw.rollback()
    as_user(rw, world["staff"])
    assert rw.execute("SELECT count(*) FROM audit_log").fetchone()[0] > 0


def test_staff_procedures_work_through_app_rw(connect, db, world):
    rw = connect("app_rw")
    rw.execute("SELECT approve_claim(%s,%s)", (world["ca"], world["staff"]))
    rw.commit()
    assert world["f"].status(world["found"]) == "claimed"
    with pytest.raises(psycopg.errors.Error) as e:                                 # plain user: refused
        rw.execute("SELECT mark_returned(%s,%s)", (world["found"], world["alice"]))
    assert e.value.sqlstate == "LF001"


def test_set_user_role_admin_only_and_last_admin_protected(connect, db, world):
    rw = connect("app_rw")
    with pytest.raises(psycopg.errors.Error) as e:
        rw.execute("SELECT set_user_role(%s,%s,'staff')", (world["staff"], world["alice"]))
    assert e.value.sqlstate == "LF001"
    rw.rollback()
    rw.execute("SELECT set_user_role(%s,%s,'staff')", (world["admin"], world["alice"]))
    rw.commit()
    assert db.execute("SELECT role::text FROM users WHERE user_id=%s", (world["alice"],)).fetchone()[0] == "staff"
    with pytest.raises(psycopg.errors.Error) as e:
        rw.execute("SELECT set_user_role(%s,%s,'user')", (world["admin"], world["admin"]))
    assert e.value.sqlstate == "LF002"


def test_read_only_and_analytics_roles(connect, world):
    ro = connect("app_ro")
    assert ro.execute("SELECT count(*) FROM item").fetchone()[0] >= 1
    ro.execute("SELECT user_id, name, role FROM users")                            # allowed columns
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        ro.execute("SELECT email FROM users")
    ro.rollback()
    for sql in ("SELECT * FROM claim", "SELECT * FROM audit_log", "UPDATE item SET title='x'"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            ro.execute(sql)
        ro.rollback()
    an = connect("analytics")
    an.execute("SELECT * FROM mv_status_counts")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        an.execute("SELECT * FROM item")
