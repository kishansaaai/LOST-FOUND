"""Matching service: two interchangeable backends behind one function.

  MATCH_BACKEND=pg      RRF is computed by the SQL functions find_matches()/rrf_fuse()
                        (the DBMS showcase) and persisted by refresh_matches().
  MATCH_BACKEND=qdrant  one filtered ANN search per modality in Qdrant, fused here with
                        the SAME formula  score = sum 1/(k + rank)  and the same gating /
                        boost rules, then persisted through the same SQL function
                        persist_match() so uniqueness and immutability rules are shared.
"""
from dataclasses import dataclass

from sqlalchemy import Connection

from . import qdrant_store as qs
from .config import get_settings
from .db import one, rows
from .stores import get_qdrant

BOOST_CATEGORY, BOOST_LOCATION, BOOST_COLOR, BOOST_BRAND = 0.0020, 0.0010, 0.0005, 0.0005


@dataclass
class Candidate:
    candidate_id: int
    rrf_score: float
    boost: float
    text_score: float | None
    image_score: float | None
    text_rank: int | None
    image_rank: int | None


def rrf_fuse(text_rank: int | None, image_rank: int | None, k: int = 60) -> float | None:
    """Reciprocal Rank Fusion over the rankings the candidate appears in.
    Mirrors the SQL function rrf_fuse() exactly (a test asserts they agree)."""
    if text_rank is None and image_rank is None:
        return None
    return sum(1.0 / (k + r) for r in (text_rank, image_rank) if r is not None)


# ---------------------------------------------------------------- pg backend
def refresh_pg(conn: Connection, item_id: int) -> list[dict]:
    s = get_settings()
    return rows(conn, "SELECT * FROM refresh_matches(CAST(:i AS bigint), CAST(:n AS int), CAST(:mt AS real), CAST(:mi AS real))",
                i=item_id, n=s.match_top_n, mt=s.match_min_text, mi=s.match_min_image)


# ------------------------------------------------------------- qdrant backend
def _vector(conn: Connection, item_id: int, col: str):
    r = one(conn, f"SELECT {col}::text AS v FROM embedding WHERE item_id = :i", i=item_id)
    if not r or r["v"] is None:
        return None
    return [float(x) for x in r["v"].strip("[]").split(",")]


def qdrant_candidates(conn: Connection, item_id: int) -> list[Candidate]:
    s = get_settings()
    me = one(conn, """SELECT item_type::text AS item_type, date_lost_or_found AS d, category::text AS category,
                             location_id, lower(color) AS color, lower(brand) AS brand, status::text AS status
                      FROM item WHERE item_id = :i""", i=item_id)
    if not me or me["status"] != "open":
        return []
    tv, iv = _vector(conn, item_id, "text_vect"), _vector(conn, item_id, "image_vector")
    if tv is None:
        return []
    ordinal: int = me["d"].toordinal()
    other = "found" if me["item_type"] == "lost" else "lost"
    must = [qs.field("item_type", other), qs.field("status", "open"),
            qs.date_range("date_ord", gte=ordinal) if me["item_type"] == "lost"
            else qs.date_range("date_ord", lte=ordinal)]
    must_not = [qs.models.HasIdCondition(has_id=[item_id])]
    c = get_qdrant()

    text_hits = qs.search(c, "text", tv, must=must, must_not=must_not, limit=s.match_pool)
    image_hits = qs.search(c, "image", iv, must=must, must_not=must_not, limit=s.match_pool) if iv else []

    info: dict[int, dict] = {}
    for rank, (iid, score, payload) in enumerate(text_hits, 1):
        info.setdefault(iid, {"payload": payload})["t"] = (rank, score)
    for rank, (iid, score, payload) in enumerate(image_hits, 1):
        info.setdefault(iid, {"payload": payload})["i"] = (rank, score)

    out: list[Candidate] = []
    for iid, d in info.items():
        t_rank, t_score = d.get("t", (None, None))
        i_rank, i_score = d.get("i", (None, None))
        if not ((t_score is not None and t_score >= s.match_min_text)
                or (i_score is not None and i_score >= s.match_min_image)):
            continue                                        # same similarity floor as the SQL gate
        p = d["payload"]
        boost = ((BOOST_CATEGORY if p.get("category") == me["category"] else 0)
                 + (BOOST_LOCATION if p.get("location_id") == me["location_id"] else 0)
                 + (BOOST_COLOR if me["color"] and p.get("color") == me["color"] else 0)
                 + (BOOST_BRAND if me["brand"] and p.get("brand") == me["brand"] else 0))
        out.append(Candidate(iid, rrf_fuse(t_rank, i_rank, s.rrf_k), boost, t_score, i_score, t_rank, i_rank))
    out.sort(key=lambda c: (-(c.rrf_score + c.boost), c.candidate_id))
    return out[: s.match_top_n]


def refresh_qdrant(conn: Connection, item_id: int) -> list[dict]:
    persisted = []
    for c in qdrant_candidates(conn, item_id):
        r = one(conn, "SELECT * FROM persist_match(CAST(:i AS bigint), CAST(:c AS bigint), CAST(:rrf AS float8), CAST(:b AS real), "
                      "CAST(:ts AS real), CAST(:isc AS real), CAST(:tr AS int), CAST(:ir AS int))",
                i=item_id, c=c.candidate_id, rrf=c.rrf_score, b=c.boost, ts=c.text_score,
                isc=c.image_score, tr=c.text_rank, ir=c.image_rank)
        if r:
            persisted.append({"out_match_id": r["out_match_id"], "out_candidate_id": c.candidate_id,
                              "out_rrf_score": c.rrf_score, "out_is_new": r["out_is_new"]})
    return persisted


def refresh_matches(conn: Connection, item_id: int, backend: str | None = None) -> list[dict]:
    """Rank + persist matches for one item inside the caller's transaction."""
    backend = backend or get_settings().match_backend
    return refresh_qdrant(conn, item_id) if backend == "qdrant" else refresh_pg(conn, item_id)
