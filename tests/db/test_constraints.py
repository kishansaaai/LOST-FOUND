"""Section 5: constraints (PK/FK/UNIQUE/CHECK/ENUM) are real and enforced by the engine."""
import psycopg
import pytest

from .factory import Factory


def test_email_unique_case_insensitive(db):
    db.execute("INSERT INTO users (name,email,password_hash) VALUES ('A','Bob@Example.com','x')")
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute("INSERT INTO users (name,email,password_hash) VALUES ('B','bob@example.COM','x')")


def test_future_date_rejected(db):
    f = Factory(db)
    u, loc = f.user(), f.location()
    with pytest.raises(psycopg.errors.CheckViolation):
        f.item(u, loc, date="2999-01-01")


def test_invalid_enum_rejected(db):
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        db.execute("INSERT INTO users (name,email,password_hash,role) VALUES ('A','a@b.c','x','superuser')")


def test_location_lat_lon_both_or_neither(db):
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("INSERT INTO location (location_name,campus,latitude) VALUES ('X','Main',12.5)")


def test_restrict_delete_user_with_items(db):
    f = Factory(db)
    u, loc = f.user(), f.location()
    f.item(u, loc)
    with pytest.raises(psycopg.errors.IntegrityError):   # ON DELETE RESTRICT (PG17: ForeignKeyViolation, PG18: RestrictViolation)
        db.execute("DELETE FROM users WHERE user_id=%s", (u,))


def test_one_embedding_per_item(db, rng_vec):
    f = Factory(db)
    i = f.item(f.user(), f.location(), text_vec=rng_vec)
    with pytest.raises(psycopg.errors.UniqueViolation):
        f.embed(i, rng_vec)


def test_embedding_dimensions_enforced(db):
    f = Factory(db)
    i = f.item(f.user(), f.location())
    with pytest.raises(psycopg.errors.DataException):
        db.execute("INSERT INTO embedding (item_id,text_vect,model_name) VALUES (%s,'[1,2,3]','t')", (i,))


def test_claim_result_and_status_cannot_contradict(db):
    f = Factory(db)
    owner, claimant, _staff, loc = f.user(), f.user(), f.user("staff"), f.location()
    item = f.item(owner, loc, "found")
    c = f.claim(item, claimant)
    with pytest.raises(psycopg.errors.CheckViolation):  # approved but not verified
        db.execute("UPDATE claim SET result='approved', verification_status='pending' WHERE claim_id=%s", (c,))
    with pytest.raises(psycopg.errors.CheckViolation):  # decided without reviewer
        db.execute("UPDATE claim SET result='denied', verification_status='rejected' WHERE claim_id=%s", (c,))


def test_claim_cannot_be_reviewed_by_claimant(db):
    f = Factory(db)
    owner, claimant, loc = f.user(), f.user("staff"), f.location()
    item = f.item(owner, loc, "found")
    c = f.claim(item, claimant)
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("UPDATE claim SET reviewed_by=claimant_id WHERE claim_id=%s", (c,))


def test_one_pending_claim_per_user_and_item(db):
    f = Factory(db)
    owner, claimant, loc = f.user(), f.user(), f.location()
    item = f.item(owner, loc, "found")
    f.claim(item, claimant)
    with pytest.raises(psycopg.errors.UniqueViolation):
        f.claim(item, claimant)


def test_claim_must_target_found_item_and_not_own_report(db):
    f = Factory(db)
    owner, other, loc = f.user(), f.user(), f.location()
    lost = f.item(owner, loc, "lost")
    found = f.item(owner, loc, "found")
    with pytest.raises(psycopg.errors.Error) as e:
        f.claim(lost, other)
    assert e.value.sqlstate == "LF002"
    with pytest.raises(psycopg.errors.Error) as e:
        f.claim(found, owner)
    assert e.value.sqlstate == "LF002"


def test_audit_log_action_check(db):
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("INSERT INTO audit_log (table_name,row_pk,action) VALUES ('item',1,'TRUNCATE')")
