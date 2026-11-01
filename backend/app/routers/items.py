import io
import json
import re
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from PIL import Image
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from .. import cache, embeddings as emb, matching, notify, qdrant_store as qs
from ..config import get_settings
from ..scoring import confidence
from ..db import one, rows, scalar, transaction
from ..deps import Principal, current_user, optional_user, rate_limit, require_staff
from ..outbox import wake_worker
from ..storage import InvalidUpload, get_storage
from ..stores import get_mongo, get_qdrant, get_redis

router = APIRouter(tags=["items"])

CATEGORIES = ["electronics", "wallet_bag", "keys", "id_card", "clothing", "jewelry", "documents", "pet", "other"]
STATUSES = ["open", "matched", "claimed", "returned", "closed"]
IMG_RE = re.compile(r"^/uploads/[a-z0-9_]+/[0-9a-f]{32}\.jpg$")

LIST_COLS = """i.item_id, i.item_type::text AS item_type, i.status::text AS status, i.title, i.description,
               i.category::text AS category, i.color, i.brand, i.date_lost_or_found, i.image_urls, i.reported_at,
               l.location_id, l.location_name, l.campus"""


class ItemIn(BaseModel):
    item_type: str = Field(pattern="^(lost|found)$")
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=5000)
    category: str
    location_id: int
    date_lost_or_found: date
    color: str | None = Field(default=None, max_length=60)
    brand: str | None = Field(default=None, max_length=80)
    image_urls: list[str] = Field(default_factory=list, max_length=5)
    extras: dict = Field(default_factory=dict)

    @field_validator("category")
    @classmethod
    def _cat(cls, v):
        if v not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")
        return v

    @field_validator("image_urls")
    @classmethod
    def _imgs(cls, v):
        if any(not IMG_RE.match(u) for u in v):
            raise ValueError("image_urls must come from POST /uploads")
        return v

    @field_validator("extras")
    @classmethod
    def _extras(cls, v):
        if len(v) > 20 or len(json.dumps(v)) > 4000:
            raise ValueError("extras too large")
        if any(not isinstance(k, str) or not isinstance(x, (str, int, float, bool, type(None))) for k, x in v.items()):
            raise ValueError("extras must be a flat object of simple values")
        return v

    @field_validator("date_lost_or_found")
    @classmethod
    def _date(cls, v):
        if v > date.today():
            raise ValueError("date cannot be in the future")
        return v


class ItemPatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=3, max_length=5000)
    category: str | None = None
    location_id: int | None = None
    date_lost_or_found: date | None = None
    color: str | None = Field(default=None, max_length=60)
    brand: str | None = Field(default=None, max_length=80)
    image_urls: list[str] | None = Field(default=None, max_length=5)

    @field_validator("category")
    @classmethod
    def _cat(cls, v):
        if v is not None and v not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")
        return v

    @field_validator("image_urls")
    @classmethod
    def _imgs(cls, v):
        if v is not None and any(not IMG_RE.match(u) for u in v):
            raise ValueError("image_urls must come from POST /uploads")
        return v


# --------------------------------------------------------------- public stats
@router.get("/stats")
def public_stats():
    """Landing-page counters, read from the materialized view (cheap, slightly stale by design)."""
    with transaction() as conn:
        counts = rows(conn, "SELECT item_type::text AS item_type, status::text AS status, n FROM mv_status_counts")
        rec = one(conn, "SELECT recovery_rate_pct, returned_items FROM mv_recovery_stats WHERE category = 'ALL'")
    by = lambda t, s_=None: sum(c["n"] for c in counts if c["item_type"] == t and (s_ is None or c["status"] == s_))
    return {"open_lost": by("lost", "open"), "open_found": by("found", "open"),
            "returned": by("found", "returned"), "recovery_rate_pct": float(rec["recovery_rate_pct"]) if rec and rec["recovery_rate_pct"] is not None else None}


# ----------------------------------------------------------------- locations
@router.get("/locations")
def list_locations():
    with transaction() as conn:
        return rows(conn, "SELECT location_id, location_name, campus, building, floor, latitude, longitude "
                          "FROM location ORDER BY campus, location_name")


class LocationIn(BaseModel):
    location_name: str = Field(min_length=2, max_length=120)
    campus: str = Field(min_length=1, max_length=80)
    building: str | None = None
    floor: str | None = None


@router.post("/locations", status_code=201)
def create_location(body: LocationIn, user: Principal = Depends(require_staff)):
    with transaction(user.id) as conn:
        return one(conn, """INSERT INTO location (location_name, campus, building, floor)
                            VALUES (:n, :c, :b, :f) RETURNING location_id, location_name, campus, building, floor""",
                   n=body.location_name, c=body.campus, b=body.building, f=body.floor)


# ------------------------------------------------------------------- uploads
@router.post("/uploads", status_code=201, dependencies=[Depends(rate_limit("upload", 30, 60))])
async def upload_image(file: UploadFile = File(...), user: Principal = Depends(current_user)):
    data = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    try:
        url = get_storage().save_image(data)
    except InvalidUpload as e:
        raise HTTPException(422, str(e)) from None
    try:
        get_mongo().upload_metadata.insert_one({"url": url, "user_id": user.id, "size": len(data),
                                                "content_type": file.content_type, "created_at": date.today().isoformat()})
    except Exception:
        pass                                           # metadata is best-effort
    return {"url": url}


# ------------------------------------------------------------------- create
@router.post("/items", status_code=201, dependencies=[Depends(rate_limit("create_item", 30, 3600))])
def create_item(body: ItemIn, user: Principal = Depends(current_user)):
    with transaction(user.id) as conn:
        item = one(conn, """INSERT INTO item (reporter_id, location_id, item_type, title, description, category,
                                              color, brand, date_lost_or_found, image_urls)
                            VALUES (:r, :l, CAST(:t AS item_type), :ti, :d, CAST(:c AS item_category), :co, :b, :dt, :im)
                            RETURNING item_id, item_type::text AS item_type, status::text AS status, title""",
                    r=user.id, l=body.location_id, t=body.item_type, ti=body.title.strip(), d=body.description.strip(),
                    c=body.category, co=body.color, b=body.brand, dt=body.date_lost_or_found, im=body.image_urls)
        if body.extras:   # outbox row in the same transaction: Mongo is updated by the worker, never dual-written
            conn.execute(text("""INSERT INTO outbox (aggregate, aggregate_id, event_type, payload)
                                 VALUES ('item_extras', :i, 'item_extras.set', CAST(:p AS jsonb))"""),
                         {"i": item["item_id"], "p": json.dumps({"item_id": item["item_id"],
                                                                 "category": body.category, "extras": body.extras})})
    wake_worker()
    return item


# -------------------------------------------------------------------- search
@router.get("/items")
def search_items(q: str | None = Query(None, max_length=200), item_type: str | None = Query(None, pattern="^(lost|found)$"),
                 category: str | None = None, location_id: int | None = None, status: str = "open",
                 date_from: date | None = None, date_to: date | None = None,
                 page: int = Query(1, ge=1, le=500), page_size: int = Query(12, ge=1, le=50)):
    return _search(q, item_type, category, location_id, status, date_from, date_to, page, page_size, reporter_id=None)


def _search(q, item_type, category, location_id, status, date_from, date_to, page, page_size, reporter_id):
    if category and category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {CATEGORIES}")
    if status not in STATUSES + ["any"]:
        raise HTTPException(422, f"status must be one of {STATUSES + ['any']}")
    cache_key = json.dumps([q, item_type, category, location_id, status, str(date_from), str(date_to), page, page_size, reporter_id])
    r = get_redis()
    if (hit := cache.get(r, "items", cache_key)) is not None:
        return hit
    where, p = ["TRUE"], {"lim": page_size, "off": (page - 1) * page_size}
    if q and q.strip():
        where.append("i.search_tsv @@ websearch_to_tsquery('english', :q)"); p["q"] = q.strip()
    if item_type:
        where.append("i.item_type = CAST(:t AS item_type)"); p["t"] = item_type
    if category:
        where.append("i.category = CAST(:c AS item_category)"); p["c"] = category
    if location_id:
        where.append("i.location_id = :l"); p["l"] = location_id
    if status != "any":
        where.append("i.status = CAST(:s AS item_status)"); p["s"] = status
    if date_from:
        where.append("i.date_lost_or_found >= :df"); p["df"] = date_from
    if date_to:
        where.append("i.date_lost_or_found <= :dt"); p["dt"] = date_to
    if reporter_id:
        where.append("i.reporter_id = :rep"); p["rep"] = reporter_id
    rank = ("ts_rank_cd(i.search_tsv, websearch_to_tsquery('english', :q))" if "q" in p else "0")
    sql = f"""SELECT {LIST_COLS}, {rank} AS rank, count(*) OVER () AS total
              FROM item i JOIN location l USING (location_id)
              WHERE {' AND '.join(where)}
              ORDER BY rank DESC, i.reported_at DESC, i.item_id DESC LIMIT :lim OFFSET :off"""
    with transaction() as conn:
        found = rows(conn, sql, **p)
    out = {"items": [{k: v for k, v in row.items() if k not in ("total", "rank")} for row in found],
           "total": found[0]["total"] if found else 0, "page": page, "page_size": page_size}
    cache.put(r, "items", cache_key, out, get_settings().cache_ttl_seconds)
    return out


@router.get("/items/mine")
def my_items(user: Principal = Depends(current_user), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100)):
    sql = f"""SELECT {LIST_COLS}, (SELECT count(*) FROM match_item mi JOIN match m USING (match_id)
                        WHERE mi.item_id = i.item_id AND m.verification_status = 'suggested') AS suggested_matches
              FROM item i JOIN location l USING (location_id) WHERE i.reporter_id = :u
              ORDER BY i.reported_at DESC LIMIT :lim OFFSET :off"""
    with transaction(user.id) as conn:
        return {"items": rows(conn, sql, u=user.id, lim=page_size, off=(page - 1) * page_size)}


@router.post("/search/by-image", dependencies=[Depends(rate_limit("image_search", 20, 60))])
async def search_by_image(file: UploadFile = File(...), item_type: str | None = Query(None, pattern="^(lost|found)$"),
                          limit: int = Query(12, ge=1, le=30)):
    """Embed the uploaded picture with CLIP and return the most similar open items."""
    data = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    try:
        img = Image.open(io.BytesIO(data)); img.load(); img = img.convert("RGB")
    except Exception:
        raise HTTPException(422, "not a valid image") from None
    vec = emb.get_embedder().embed_images([img])[0]
    if get_settings().match_backend == "qdrant":
        must = [qs.field("status", "open")] + ([qs.field("item_type", item_type)] if item_type else [])
        hits = qs.search(get_qdrant(), "image", vec, must=must, limit=limit)
        ids = [(h[0], h[1]) for h in hits]
    else:
        with transaction() as conn:
            ids = [(r["item_id"], r["sim"]) for r in rows(
                conn, """SELECT e.item_id, 1 - (e.image_vector <=> CAST(:v AS vector)) AS sim
                         FROM embedding e JOIN item i USING (item_id)
                         WHERE e.image_vector IS NOT NULL AND i.status = 'open'
                           AND (CAST(:t AS text) IS NULL OR i.item_type = CAST(:t AS item_type))
                         ORDER BY e.image_vector <=> CAST(:v AS vector) LIMIT :n""",
                v=emb.vec_literal(vec), t=item_type, n=limit)]
    if not ids:
        return {"items": []}
    with transaction() as conn:
        found = {r["item_id"]: r for r in rows(conn, f"SELECT {LIST_COLS} FROM item i JOIN location l USING (location_id) "
                                                      "WHERE i.item_id = ANY(:ids)", ids=[i for i, _ in ids])}
    return {"items": [{**found[i], "similarity": round(float(s), 4)} for i, s in ids if i in found]}


# -------------------------------------------------------------------- detail
def _viewer_owns(conn, item_id: int, user: Principal | None) -> bool:
    return bool(user and scalar(conn, "SELECT 1 FROM item WHERE item_id = :i AND reporter_id = :u", i=item_id, u=user.id))


@router.get("/items/{item_id}")
def item_detail(item_id: int, user: Principal | None = Depends(optional_user)):
    with transaction(user.id if user else None) as conn:
        item = one(conn, f"""SELECT {LIST_COLS}, i.reporter_id, u.name AS reporter_name, i.updated_at
                             FROM item i JOIN location l USING (location_id) JOIN users u ON u.user_id = i.reporter_id
                             WHERE i.item_id = :i""", i=item_id)
        if not item:
            raise HTTPException(404, "item not found")
        mine = bool(user and item["reporter_id"] == user.id)
        item["is_mine"] = mine
        item.pop("reporter_id")
        item["claimable"] = bool(user and not mine and item["item_type"] == "found" and item["status"] in ("open", "matched"))
        if user:
            item["my_claim"] = one(conn, "SELECT claim_id, verification_status::text AS verification_status, result::text AS result, "
                                         "submitted_at FROM claim WHERE item_id = :i AND claimant_id = :u "
                                         "ORDER BY submitted_at DESC LIMIT 1", i=item_id, u=user.id)
            if mine or user.is_staff:
                item["claim_count"] = scalar(conn, "SELECT count(*) FROM claim WHERE item_id = :i", i=item_id)
        item["suggested_matches"] = scalar(conn, """SELECT count(*) FROM match_item mi JOIN match m USING (match_id)
                                                    WHERE mi.item_id = :i AND m.verification_status = 'suggested'""", i=item_id)
    try:
        item["extras"] = notify.get_extras(item_id)
    except Exception:
        item["extras"] = {}                       # Mongo down: degrade, do not fail the page
    return item


@router.patch("/items/{item_id}")
def edit_item(item_id: int, body: ItemPatch, user: Principal = Depends(current_user)):
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "nothing to update")
    with transaction(user.id) as conn:
        cur = one(conn, "SELECT reporter_id, status::text AS status FROM item WHERE item_id = :i FOR UPDATE", i=item_id)
        if not cur:
            raise HTTPException(404, "item not found")
        if cur["reporter_id"] != user.id and not user.is_staff:
            raise HTTPException(403, "only the reporter or staff can edit an item")
        if cur["status"] not in ("open", "matched"):
            raise HTTPException(409, f"a {cur['status']} item cannot be edited")
        sets = []
        for k in changes:
            sets.append(f"{k} = CAST(:{k} AS item_category)" if k == "category" else f"{k} = :{k}")
        conn.execute(text(f"UPDATE item SET {', '.join(sets)} WHERE item_id = :_id"), {**changes, "_id": item_id})
    wake_worker()
    return {"ok": True}


@router.post("/items/{item_id}/close")
def close_item(item_id: int, user: Principal = Depends(current_user)):
    with transaction(user.id) as conn:
        one(conn, "SELECT * FROM close_item(:i, :u)", i=item_id, u=user.id)
    wake_worker()
    return {"ok": True}


# ------------------------------------------------------------------- matches
def explain(m: dict) -> dict:
    k = get_settings().rrf_k
    parts = []
    if m["text_rank"] is not None:
        parts.append({"signal": "text", "similarity": round(m["text_score"], 4), "rank": m["text_rank"],
                      "contribution": round(1 / (k + m["text_rank"]), 6)})
    if m["image_rank"] is not None:
        parts.append({"signal": "image", "similarity": round(m["image_score"], 4), "rank": m["image_rank"],
                      "contribution": round(1 / (k + m["image_rank"]), 6)})
    formula = " + ".join(f"1/({k}+{p['rank']})" for p in parts)
    return {"rrf_score": round(m["rrf_score"], 6), "boost": round(m["boost"], 4), "k": k, "formula": f"{formula} = {m['rrf_score']:.5f}",
            "signals": parts, "max_possible": round(len(parts) / (k + 1), 6),
            "confidence": confidence(m["text_score"], m["image_score"])}


@router.get("/items/{item_id}/matches")
def item_matches(item_id: int, user: Principal = Depends(current_user)):
    with transaction(user.id) as conn:
        if not _viewer_owns(conn, item_id, user) and not user.is_staff:
            if not scalar(conn, "SELECT 1 FROM item WHERE item_id = :i", i=item_id):
                raise HTTPException(404, "item not found")
            raise HTTPException(403, "only the reporter or staff can see an item's matches")
        found = rows(conn, """SELECT * FROM v_match_details WHERE (lost_item_id = :i OR found_item_id = :i)
                              AND verification_status <> 'rejected' ORDER BY rrf_score + boost DESC""", i=item_id)
    out = []
    for m in found:
        other_is_found = m["lost_item_id"] == item_id
        out.append({"match_id": m["match_id"], "status": m["verification_status"],
                    "other_item_id": m["found_item_id" if other_is_found else "lost_item_id"],
                    "other_title": m["found_title" if other_is_found else "lost_title"],
                    "other_type": "found" if other_is_found else "lost",
                    "other_status": m["found_status" if other_is_found else "lost_status"],
                    "other_images": m["found_images" if other_is_found else "lost_images"],
                    "other_location": m["found_location" if other_is_found else "lost_location"],
                    "other_date": m["found_date" if other_is_found else "lost_date"],
                    "explanation": explain(m)})
    return {"matches": out}


@router.get("/items/{item_id}/claimable-matches")
def claimable_matches(item_id: int, user: Principal = Depends(current_user)):
    """The viewer's own lost reports that were matched to this found item (to link a claim to a match)."""
    with transaction(user.id) as conn:
        return {"matches": rows(conn, """SELECT match_id, lost_item_id, lost_title, rrf_score, verification_status::text AS status
                                         FROM v_match_details
                                         WHERE found_item_id = :i AND lost_reporter_id = :u AND verification_status <> 'rejected'
                                         ORDER BY rrf_score + boost DESC""", i=item_id, u=user.id)}


@router.post("/items/{item_id}/find-matches", dependencies=[Depends(rate_limit("find_matches", 20, 60))])
def find_matches(item_id: int, user: Principal = Depends(current_user)):
    with transaction(user.id) as conn:
        it = one(conn, "SELECT reporter_id, status::text AS status FROM item WHERE item_id = :i", i=item_id)
        if not it:
            raise HTTPException(404, "item not found")
        if it["reporter_id"] != user.id and not user.is_staff:
            raise HTTPException(403, "only the reporter or staff can run matching")
        if it["status"] != "open":
            raise HTTPException(409, f"only open items are matched (this one is {it['status']})")
        if not scalar(conn, "SELECT 1 FROM embedding WHERE item_id = :i", i=item_id):
            raise HTTPException(409, "the item is still being analysed; try again in a few seconds")
        created = matching.refresh_matches(conn, item_id)
    wake_worker()
    return {"found": len(created), "new": sum(1 for c in created if c["out_is_new"])}
