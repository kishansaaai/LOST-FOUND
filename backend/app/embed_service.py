"""Compute and store the embedding row for one item (Postgres is the source of truth)."""
import hashlib

from PIL import Image
from sqlalchemy import Connection, text

from . import embeddings as emb
from .db import one, scalar
from .storage import Storage, get_storage

SQL_ITEM = """SELECT item_id, title, description, category::text AS category, color, brand,
                     image_urls, status::text AS status, item_type::text AS item_type,
                     location_id, date_lost_or_found
              FROM item WHERE item_id = :i"""

SQL_UPSERT = """
INSERT INTO embedding (item_id, text_vect, image_vector, model_name, content_hash)
VALUES (:i, CAST(:tv AS vector), CAST(:iv AS vector), :model, :h)
ON CONFLICT (item_id) DO UPDATE
   SET text_vect = EXCLUDED.text_vect, image_vector = EXCLUDED.image_vector,
       model_name = EXCLUDED.model_name, content_hash = EXCLUDED.content_hash, created_at = now()"""


def load_images(item: dict, storage: Storage) -> tuple[list[Image.Image], list[str]]:
    images, digests = [], []
    for url in item["image_urls"] or []:
        try:
            path = storage.local_path(url)
            data = path.read_bytes()
        except (OSError, ValueError):
            continue                                   # missing file: embed what we have
        digests.append(hashlib.sha1(data).hexdigest())
        images.append(Image.open(path).convert("RGB"))
    return images, digests


def embed_item(conn: Connection, item_id: int, embedder: emb.Embedder | None = None,
               storage: Storage | None = None) -> bool:
    """Returns True when the embedding row was (re)written, False when nothing changed
    (content hash identical) or the item does not exist."""
    embedder = embedder or emb.get_embedder()
    storage = storage or get_storage()
    item = one(conn, SQL_ITEM, i=item_id)
    if item is None:
        return False
    images, digests = load_images(item, storage)
    h = emb.content_hash(item, digests)
    if scalar(conn, "SELECT content_hash FROM embedding WHERE item_id = :i", i=item_id) == h:
        return False
    text_vec = embedder.embed_text([emb.item_document(item)])[0]
    image_vec = emb.mean_unit(embedder.embed_images(images)) if images else None
    conn.execute(
        text(SQL_UPSERT),
        {"i": item_id, "tv": emb.vec_literal(text_vec), "iv": emb.vec_literal(image_vec),
         "model": emb.MODEL_LABEL, "h": h})
    return True
