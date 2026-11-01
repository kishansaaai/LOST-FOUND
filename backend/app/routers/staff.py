from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import one, rows, transaction
from ..deps import Principal, require_staff
from ..outbox import wake_worker

router = APIRouter(prefix="/staff", tags=["staff"])


class Decision(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


@router.get("/claims/queue")
def claim_queue(user: Principal = Depends(require_staff)):
    with transaction(user.id) as conn:
        return {"claims": rows(conn, "SELECT * FROM v_claim_queue ORDER BY submitted_at")}


@router.get("/claims/{claim_id}")
def claim_for_review(claim_id: int, user: Principal = Depends(require_staff)):
    """Everything a reviewer needs side by side: the claim, the found item, other claims."""
    with transaction(user.id) as conn:
        c = one(conn, """SELECT c.*, c.verification_status::text AS verification_status, c.result::text AS result,
                                u.name AS claimant_name, u.email AS claimant_email, u.phone AS claimant_phone
                         FROM claim c JOIN users u ON u.user_id = c.claimant_id WHERE c.claim_id = :c""", c=claim_id)
        if not c:
            raise HTTPException(404, "claim not found")
        item = one(conn, """SELECT i.item_id, i.title, i.description, i.category::text AS category, i.color, i.brand,
                                   i.image_urls, i.status::text AS status, i.date_lost_or_found, l.location_name
                            FROM item i JOIN location l USING (location_id) WHERE i.item_id = :i""", i=c["item_id"])
        match = one(conn, "SELECT * FROM v_match_details WHERE match_id = :m", m=c["match_id"]) if c["match_id"] else None
        others = rows(conn, "SELECT claim_id, claimant_id, verification_status::text AS verification_status, "
                            "result::text AS result, submitted_at FROM claim WHERE item_id = :i AND claim_id <> :c",
                      i=c["item_id"], c=claim_id)
    return {"claim": c, "item": item, "match": match, "other_claims": others}


def _decide(fn: str, claim_id: int, user: Principal, notes: str | None):
    with transaction(user.id) as conn:
        args = "" if fn == "start_claim_review" else ", :n"
        c = one(conn, f"SELECT claim_id, verification_status::text AS verification_status, result::text AS result "
                      f"FROM {fn}(:c, :s{args})", c=claim_id, s=user.id, n=notes)
    wake_worker()
    return c


@router.post("/claims/{claim_id}/start-review")
def start_review(claim_id: int, user: Principal = Depends(require_staff)):
    return _decide("start_claim_review", claim_id, user, None)


@router.post("/claims/{claim_id}/approve")
def approve(claim_id: int, body: Decision, user: Principal = Depends(require_staff)):
    return _decide("approve_claim", claim_id, user, body.notes)


@router.post("/claims/{claim_id}/reject")
def reject(claim_id: int, body: Decision, user: Principal = Depends(require_staff)):
    return _decide("reject_claim", claim_id, user, body.notes)


@router.post("/items/{item_id}/mark-returned")
def mark_returned(item_id: int, user: Principal = Depends(require_staff)):
    with transaction(user.id) as conn:
        one(conn, "SELECT item_id FROM mark_returned(:i, :s)", i=item_id, s=user.id)
    wake_worker()
    return {"ok": True}


@router.get("/matches")
def list_matches(status: str = Query("suggested", pattern="^(suggested|confirmed|rejected|any)$"),
                 page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                 user: Principal = Depends(require_staff)):
    with transaction(user.id) as conn:
        found = rows(conn, """SELECT *, count(*) OVER () AS total FROM v_match_details
                              WHERE (:s = 'any' OR verification_status::text = :s)
                              ORDER BY rrf_score + boost DESC, match_id LIMIT :l OFFSET :o""",
                     s=status, l=page_size, o=(page - 1) * page_size)
    return {"matches": found, "total": found[0]["total"] if found else 0}


@router.post("/matches/{match_id}/confirm")
def confirm_match(match_id: int, user: Principal = Depends(require_staff)):
    with transaction(user.id) as conn:
        one(conn, "SELECT match_id FROM confirm_match(:m, :s)", m=match_id, s=user.id)
    wake_worker()
    return {"ok": True}


@router.post("/matches/{match_id}/reject")
def reject_match(match_id: int, user: Principal = Depends(require_staff)):
    with transaction(user.id) as conn:
        one(conn, "SELECT match_id FROM reject_match(:m, :s)", m=match_id, s=user.id)
    return {"ok": True}


@router.get("/audit")
def audit(table_name: str | None = Query(None, pattern="^(item|claim|match|users)$"), row_pk: int | None = None,
          limit: int = Query(100, ge=1, le=500), user: Principal = Depends(require_staff)):
    with transaction(user.id) as conn:         # RLS on audit_log: staff only
        return {"entries": rows(conn, """SELECT a.audit_id, a.table_name, a.row_pk, a.action, a.actor_id, u.name AS actor_name,
                                                a.old_data, a.new_data, a.changed_at
                                         FROM audit_log a LEFT JOIN users u ON u.user_id = a.actor_id
                                         WHERE (CAST(:t AS text) IS NULL OR a.table_name = :t)
                                           AND (CAST(:r AS bigint) IS NULL OR a.row_pk = :r)
                                         ORDER BY a.audit_id DESC LIMIT :l""", t=table_name, r=row_pk, l=limit)}
