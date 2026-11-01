"""Qdrant: derived ANN index. One point per item (id = item_id) with named vectors
`text` (384) and `image` (512) plus a filterable payload. Rebuildable from Postgres."""
from datetime import date

from qdrant_client import QdrantClient, models

COLLECTION = "items"


_ready: set[int] = set()          # clients (by id) whose collection is known to exist: saves a round trip per upsert


def ensure_collection(c: QdrantClient) -> None:
    if id(c) in _ready:
        return
    if c.collection_exists(COLLECTION):
        _ready.add(id(c))
        return
    c.create_collection(
        COLLECTION,
        vectors_config={
            "text": models.VectorParams(size=384, distance=models.Distance.COSINE),
            "image": models.VectorParams(size=512, distance=models.Distance.COSINE),
        },
    )
    for field, schema in (("item_type", "keyword"), ("status", "keyword"), ("category", "keyword"),
                          ("location_id", "integer"), ("date_ord", "integer")):
        c.create_payload_index(COLLECTION, field, schema)
    _ready.add(id(c))


def payload_for(item: dict) -> dict:
    d: date = item["date_lost_or_found"]
    return {
        "item_id": item["item_id"], "item_type": item["item_type"], "status": item["status"],
        "category": item["category"], "location_id": item["location_id"], "date_ord": d.toordinal(),
        "color": (item.get("color") or "").lower() or None, "brand": (item.get("brand") or "").lower() or None,
    }


def upsert_item(c: QdrantClient, item: dict, text_vec, image_vec) -> None:
    ensure_collection(c)
    vectors = {"text": list(map(float, text_vec))}
    if image_vec is not None:
        vectors["image"] = list(map(float, image_vec))
    c.upsert(COLLECTION, points=[models.PointStruct(id=item["item_id"], vector=vectors,
                                                    payload=payload_for(item))])


def set_payload(c: QdrantClient, item: dict) -> bool:
    """Refresh only the payload (status changed etc.). False if the point does not exist yet."""
    ensure_collection(c)
    if not c.retrieve(COLLECTION, ids=[item["item_id"]]):
        return False
    c.set_payload(COLLECTION, payload=payload_for(item), points=[item["item_id"]])
    return True


def delete_item(c: QdrantClient, item_id: int) -> None:
    ensure_collection(c)
    c.delete(COLLECTION, points_selector=models.PointIdsList(points=[item_id]))


def search(c: QdrantClient, using: str, vector, *, must: list, must_not: list | None = None,
           limit: int = 100):
    """Returns [(item_id, cosine_similarity, payload)] best first."""
    ensure_collection(c)
    res = c.query_points(
        COLLECTION, query=list(map(float, vector)), using=using,
        query_filter=models.Filter(must=must, must_not=must_not or []),
        limit=limit, with_payload=True)
    return [(int(p.id), float(p.score), p.payload) for p in res.points]


def field(key: str, value) -> models.FieldCondition:
    return models.FieldCondition(key=key, match=models.MatchValue(value=value))


def date_range(key: str, gte: int | None = None, lte: int | None = None) -> models.FieldCondition:
    return models.FieldCondition(key=key, range=models.Range(gte=gte, lte=lte))
