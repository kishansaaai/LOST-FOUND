"""MongoDB side: notifications, activity feed, item_extras, upload metadata.

Documents reference Postgres ids; there are no joins and no integrity requirements
here, which is exactly why this data lives in a document store. Writes are idempotent
(`dedupe_key` upserts) because the outbox worker delivers at-least-once."""
import json
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING

from .stores import get_mongo, get_redis


def ensure_indexes() -> None:
    db = get_mongo()
    db.notifications.create_index([("dedupe_key", ASCENDING)], unique=True)
    db.notifications.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    db.notifications.create_index([("audience", ASCENDING), ("created_at", DESCENDING)])
    db.activity_feed.create_index([("created_at", DESCENDING)])
    db.activity_feed.create_index([("item_id", ASCENDING)])
    db.item_extras.create_index([("item_id", ASCENDING)], unique=True)
    db.upload_metadata.create_index([("url", ASCENDING)], unique=True)


def notify(*, dedupe_key: str, type: str, title: str, body: str, user_id: int | None = None,
           audience: str = "user", **refs) -> bool:
    """Insert once; returns True only for the first delivery, then pushes it in real time
    through Redis pub/sub (channel per user, one for staff)."""
    now = datetime.now(timezone.utc)
    doc = {"type": type, "title": title, "body": body, "user_id": user_id, "audience": audience,
           "read_by": [], "created_at": now, **refs}
    res = get_mongo().notifications.update_one({"dedupe_key": dedupe_key}, {"$setOnInsert": doc}, upsert=True)
    if res.upserted_id is None:
        return False
    channel = "lf:notify:staff" if audience == "staff" else f"lf:notify:user:{user_id}"
    try:
        get_redis().publish(channel, json.dumps({"type": type, "title": title, "body": body, **refs}))
    except Exception:
        pass                                      # real-time push is best effort; the document is durable
    return True


def activity(type: str, text: str, **refs) -> None:
    get_mongo().activity_feed.insert_one({"type": type, "text": text, "created_at": datetime.now(timezone.utc), **refs})


def set_extras(item_id: int, category: str, extras: dict) -> None:
    get_mongo().item_extras.update_one(
        {"item_id": item_id},
        {"$set": {"category": category, "extras": extras, "updated_at": datetime.now(timezone.utc)}},
        upsert=True)


def get_extras(item_id: int) -> dict:
    doc = get_mongo().item_extras.find_one({"item_id": item_id}, {"_id": 0, "extras": 1})
    return (doc or {}).get("extras", {})


def list_notifications(user_id: int, is_staff: bool, limit: int = 50) -> list[dict]:
    q = {"$or": [{"user_id": user_id}] + ([{"audience": "staff"}] if is_staff else [])}
    out = []
    for d in get_mongo().notifications.find(q).sort("created_at", DESCENDING).limit(limit):
        d["id"] = str(d.pop("_id"))
        d["read"] = user_id in d.get("read_by", [])
        d.pop("read_by", None); d.pop("dedupe_key", None)
        out.append(d)
    return out


def unread_count(user_id: int, is_staff: bool) -> int:
    q = {"$or": [{"user_id": user_id}] + ([{"audience": "staff"}] if is_staff else []),
         "read_by": {"$ne": user_id}}
    return get_mongo().notifications.count_documents(q)


def mark_read(user_id: int, is_staff: bool, notification_id: str | None = None) -> int:
    from bson import ObjectId
    q = {"$or": [{"user_id": user_id}] + ([{"audience": "staff"}] if is_staff else [])}
    if notification_id:
        q["_id"] = ObjectId(notification_id)
    return get_mongo().notifications.update_many(q, {"$addToSet": {"read_by": user_id}}).modified_count


def delete_notification(user_id: int, notification_id: str) -> int:
    """Delete one of the caller's own notifications. Staff-wide broadcasts are shared, so they are never deletable by one reader."""
    from bson import ObjectId
    return get_mongo().notifications.delete_one({"_id": ObjectId(notification_id), "user_id": user_id}).deleted_count
