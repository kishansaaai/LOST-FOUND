import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..db import one, rows, transaction
from ..deps import Principal, current_user, rate_limit
from ..outbox import wake_worker

router = APIRouter(tags=["claims"])
IMG_RE = re.compile(r"^/uploads/[a-z0-9_]+/[0-9a-f]{32}\.jpg$")


class ClaimIn(BaseModel):
    proof_description: str = Field(min_length=10, max_length=3000)
    proof_image_url: str | None = None
    match_id: int | None = None

    @field_validator("proof_image_url")
    @classmethod
    def _img(cls, v):
        if v is not None and not IMG_RE.match(v):
            raise ValueError("proof_image_url must come from POST /uploads")
        return v


CLAIM_COLS = """c.claim_id, c.item_id, i.title AS item_title, i.image_urls AS item_images, c.claimant_id,
                c.proof_description, c.proof_image_url, c.verification_status::text AS verification_status,
                c.result::text AS result, c.submitted_at, c.reviewed_at, c.notes, c.match_id"""


@router.post("/items/{item_id}/claims", status_code=201, dependencies=[Depends(rate_limit("claim", 20, 3600))])
def submit_claim(item_id: int, body: ClaimIn, user: Principal = Depends(current_user)):
    # transaction(user.id) publishes app.user_id: the RLS policy `claimant_id = app_user_id()`
    # lets a user file claims only as themselves; guards live in the claim_guard trigger.
    with transaction(user.id) as conn:
        c = one(conn, """INSERT INTO claim (item_id, claimant_id, match_id, proof_description, proof_image_url)
                         VALUES (:i, :u, :m, :p, :img)
                         RETURNING claim_id, verification_status::text AS verification_status, result::text AS result""",
                i=item_id, u=user.id, m=body.match_id, p=body.proof_description.strip(), img=body.proof_image_url)
    wake_worker()
    return c


@router.get("/claims/mine")
def my_claims(user: Principal = Depends(current_user)):
    with transaction(user.id) as conn:
        return {"claims": rows(conn, f"SELECT {CLAIM_COLS} FROM claim c JOIN item i USING (item_id) "
                                     "WHERE c.claimant_id = :u ORDER BY c.submitted_at DESC", u=user.id)}


@router.get("/claims/{claim_id}")
def get_claim(claim_id: int, user: Principal = Depends(current_user)):
    with transaction(user.id) as conn:                     # RLS: owner or staff, otherwise no row
        c = one(conn, f"SELECT {CLAIM_COLS} FROM claim c JOIN item i USING (item_id) WHERE c.claim_id = :c", c=claim_id)
    if not c:
        raise HTTPException(404, "claim not found")
    return c
