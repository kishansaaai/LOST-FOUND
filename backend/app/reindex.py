"""Rebuild the Qdrant index from Postgres (the source of truth).   python -m app.reindex"""
from . import qdrant_store as qs
from .db import get_engine, rows, transaction
from .stores import get_qdrant


def reindex() -> int:
    c = get_qdrant()
    if c.collection_exists(qs.COLLECTION):
        c.delete_collection(qs.COLLECTION)
        qs._ready.discard(id(c))
    qs.ensure_collection(c)
    n = 0
    with transaction(engine=get_engine()) as conn:
        for r in rows(conn, """SELECT i.item_id, i.item_type::text AS item_type, i.status::text AS status,
                                      i.category::text AS category, i.location_id, i.date_lost_or_found, i.color, i.brand,
                                      e.text_vect::text AS t, e.image_vector::text AS im
                               FROM item i JOIN embedding e USING (item_id) ORDER BY i.item_id"""):
            parse = lambda s: None if s is None else [float(x) for x in s.strip("[]").split(",")]
            qs.upsert_item(c, r, parse(r["t"]), parse(r["im"]))
            n += 1
    return n


if __name__ == "__main__":
    print(f"reindexed {reindex()} items into Qdrant")
