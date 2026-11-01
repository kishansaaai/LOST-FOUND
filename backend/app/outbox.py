"""Transactional-outbox relay.

Postgres triggers insert an `outbox` row in the SAME transaction as every business
change (item / embedding / match / claim). This module drains those rows and brings the
derived stores up to date: embeddings, Qdrant, Mongo, Redis cache, notifications.

Guarantees and failure handling (see docs/consistency.md):
  * at-least-once delivery: a row is marked processed only after its handler succeeded;
  * every handler is idempotent (Qdrant upsert by id, Mongo upsert by dedupe_key,
    embedding skipped when the content hash is unchanged, matching is UNIQUE per pair);
  * a failing event is retried (attempts++, last_error) up to MAX_ATTEMPTS, then parked;
  * `FOR UPDATE SKIP LOCKED` lets several workers share the queue; per-item ordering is
    preserved by outbox_id, so run ONE worker if strict ordering matters.
"""
import logging

from sqlalchemy import Connection, text
from sqlalchemy.engine import Engine

from . import cache, matching, notify, qdrant_store as qs
from .db import one, rows
from .embed_service import embed_item
from .scoring import confidence
from .stores import get_qdrant, get_redis

log = logging.getLogger("outbox")
MAX_ATTEMPTS = 8
WAKE_KEY = "lf:outbox:wake"

SQL_ITEM_FULL = """SELECT i.item_id, i.item_type::text AS item_type, i.status::text AS status, i.title,
                          i.category::text AS category, i.color, i.brand, i.location_id, i.reporter_id,
                          i.date_lost_or_found
                   FROM item i WHERE i.item_id = :i"""



# ------------------------------------------------------------------ handlers
def on_item(conn: Connection, ev: dict) -> None:
    item_id = ev["aggregate_id"]
    op = ev["event_type"].split(".")[1]
    r = get_redis()
    if op == "delete":
        qs.delete_item(get_qdrant(), item_id)
        cache.invalidate(r, "items")
        return
    item = one(conn, SQL_ITEM_FULL, i=item_id)
    if item is None:
        return
    embed_item(conn, item_id)                       # no-op when the content hash is unchanged
    qs.set_payload(get_qdrant(), item)               # keep filter payload (status...) current
    cache.invalidate(r, "items")
    cache.invalidate(r, "matches")

    if op == "insert":
        notify.activity("item.reported", f"{item['item_type'].title()} item reported: {item['title']}",
                        item_id=item_id, user_id=item["reporter_id"])
    elif item["status"] == "returned":
        notify.notify(dedupe_key=f"item:{item_id}:returned", type="item.returned", user_id=item["reporter_id"],
                      title="Item returned", body=f"“{item['title']}” has been returned to its owner. Thank you!",
                      item_id=item_id, link=f"/items/{item_id}")
        notify.activity("item.returned", f"Returned: {item['title']}", item_id=item_id)
    elif item["status"] == "open" and op == "update":
        matching.refresh_matches(conn, item_id)      # reopened or edited: look again


def on_embedding(conn: Connection, ev: dict) -> None:
    item_id = ev["aggregate_id"]
    item = one(conn, SQL_ITEM_FULL, i=item_id)
    emb = one(conn, "SELECT text_vect::text AS t, image_vector::text AS i FROM embedding WHERE item_id = :i", i=item_id)
    if item is None or emb is None:
        return
    parse = lambda s: None if s is None else [float(x) for x in s.strip("[]").split(",")]
    qs.upsert_item(get_qdrant(), item, parse(emb["t"]), parse(emb["i"]))
    if item["status"] == "open":
        matching.refresh_matches(conn, item_id)
    cache.invalidate(get_redis(), "matches")


def on_match(conn: Connection, ev: dict) -> None:
    match_id = ev["aggregate_id"]
    status = ev["payload"].get("verification_status")
    d = one(conn, "SELECT * FROM v_match_details WHERE match_id = :m", m=match_id)
    cache.invalidate(get_redis(), "matches")
    if d is None:
        return
    pct = f"{confidence(d['text_score'], d['image_score']) * 100:.0f}"
    if ev["event_type"] == "match.insert":
        for uid, mine, theirs, kind in ((d["lost_reporter_id"], d["lost_title"], d["found_title"], "found"),
                                        (d["found_reporter_id"], d["found_title"], d["lost_title"], "lost")):
            notify.notify(dedupe_key=f"match:{match_id}:suggested:{uid}", type="match.suggested", user_id=uid,
                          title="Possible match found",
                          body=f"Your item “{mine}” may match a {kind} report: “{theirs}” (confidence {pct}%).",
                          match_id=match_id, link=f"/items/{d['lost_item_id'] if kind == 'found' else d['found_item_id']}")
    elif status == "confirmed":
        for uid in {d["lost_reporter_id"], d["found_reporter_id"]}:
            notify.notify(dedupe_key=f"match:{match_id}:confirmed:{uid}", type="match.confirmed", user_id=uid,
                          title="Match confirmed by staff",
                          body=f"Staff confirmed that “{d['lost_title']}” and “{d['found_title']}” are the same item.",
                          match_id=match_id)


def on_claim(conn: Connection, ev: dict) -> None:
    p, claim_id = ev["payload"], ev["aggregate_id"]
    item = one(conn, SQL_ITEM_FULL, i=p["item_id"])
    if item is None:
        return
    if ev["event_type"] == "claim.insert":
        notify.notify(dedupe_key=f"claim:{claim_id}:new:finder", type="claim.submitted", user_id=item["reporter_id"],
                      title="Someone claimed your found item",
                      body=f"A claim was submitted for “{item['title']}”. Staff will verify it.",
                      claim_id=claim_id, item_id=item["item_id"], link=f"/items/{item['item_id']}")
        notify.notify(dedupe_key=f"claim:{claim_id}:new:staff", type="claim.queue", audience="staff",
                      title="New claim to review", body=f"Claim #{claim_id} on “{item['title']}”.",
                      claim_id=claim_id, item_id=item["item_id"], link="/staff/claims")
    elif p.get("result") in ("approved", "denied"):
        ok = p["result"] == "approved"
        notify.notify(dedupe_key=f"claim:{claim_id}:decided", type=f"claim.{p['result']}", user_id=p["claimant_id"],
                      title="Claim approved" if ok else "Claim not approved",
                      body=(f"Your claim for “{item['title']}” was approved. Staff will arrange the hand-over."
                            if ok else f"Your claim for “{item['title']}” was not approved."),
                      claim_id=claim_id, item_id=item["item_id"], link="/claims")
    elif p.get("verification_status") == "under_review":
        notify.notify(dedupe_key=f"claim:{claim_id}:review", type="claim.under_review", user_id=p["claimant_id"],
                      title="Claim under review", body=f"Staff started reviewing your claim for “{item['title']}”.",
                      claim_id=claim_id, item_id=item["item_id"], link="/claims")
    cache.invalidate(get_redis(), "items")


def on_item_extras(conn: Connection, ev: dict) -> None:
    p = ev["payload"]
    notify.set_extras(p["item_id"], p.get("category", ""), p.get("extras", {}))


HANDLERS = {"item": on_item, "embedding": on_embedding, "match": on_match, "claim": on_claim,
            "item_extras": on_item_extras}


# --------------------------------------------------------------------- relay
def process_batch(engine: Engine, batch: int = 50) -> int:
    """Handle up to `batch` pending events. Returns how many were attempted."""
    with engine.begin() as conn:
        events = rows(conn, """SELECT outbox_id, aggregate, aggregate_id, event_type, payload, attempts
                               FROM outbox WHERE processed_at IS NULL AND attempts < :max
                               ORDER BY outbox_id LIMIT :n FOR UPDATE SKIP LOCKED""",
                      max=MAX_ATTEMPTS, n=batch)
        for ev in events:
            handler = HANDLERS.get(ev["aggregate"])
            sp = conn.begin_nested()            # savepoint: a failing event must not poison the batch
            try:
                if handler:
                    handler(conn, ev)
                conn.execute(text("UPDATE outbox SET processed_at = now() WHERE outbox_id = :i"),
                             {"i": ev["outbox_id"]})
                sp.commit()
            except Exception as exc:            # noqa: BLE001 - recorded and retried
                sp.rollback()
                log.warning("outbox %s %s failed: %s", ev["outbox_id"], ev["event_type"], exc)
                conn.execute(text("UPDATE outbox SET attempts = attempts + 1, last_error = :e "
                                  "WHERE outbox_id = :i"), {"i": ev["outbox_id"], "e": str(exc)[:500]})
        return len(events)


def drain(engine: Engine, max_rounds: int = 200) -> int:
    """Process until the queue is empty (events produce more events, e.g. embedding -> match)."""
    total = 0
    for _ in range(max_rounds):
        n = process_batch(engine)
        total += n
        if n == 0:
            break
    return total


def wake_worker() -> None:
    """Called by the API after commit: nudges the worker so notifications are near-instant.
    Purely an optimisation; the worker also polls, so a lost nudge only adds latency."""
    try:
        r = get_redis()
        r.lpush(WAKE_KEY, "1")
        r.ltrim(WAKE_KEY, 0, 99)
    except Exception:
        pass
