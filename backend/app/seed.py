"""Realistic demo data: users, places, ~360 items, real embeddings, suggested matches and a
claim workflow in every state.  python -m app.seed [--reset] [--pairs N]

Everything goes through the real constraints, triggers and procedures (no shortcuts), then
timestamps are back-dated so dashboards show weeks of history. Runs as the OWNER role
(MIGRATION_DATABASE_URL): it needs to create staff/admin accounts and back-date history."""
import argparse
import io
import json
import random
import sys
import time
from datetime import date, datetime, timedelta, timezone

from faker import Faker
from sqlalchemy import create_engine, text

from . import matching
from .config import get_settings
from .db import rows, scalar, transaction
from .embed_service import embed_item
from .security import hash_password
from .seed_data import COLORS, DETAIL_TEMPLATES, DETAIL_WORDS, EXTRAS, INITIALS, FOUND_CLOSERS, FOUND_OPENERS, LOCATIONS, LOST_CLOSERS, LOST_OPENERS, OBJECTS
from .seed_images import render
from .storage import get_storage

DEMO_PASSWORD = "Passw0rd!demo"
DEMO_USERS = [("admin@lostfound.dev", "Avery Admin", "admin"), ("staff@lostfound.dev", "Sam Staff", "staff"),
              ("staff2@lostfound.dev", "Riley Reviewer", "staff"), ("alice@lostfound.dev", "Alice Owner", "user"),
              ("bob@lostfound.dev", "Bob Finder", "user"), ("carol@lostfound.dev", "Carol Claimant", "user")]

PROOFS = [
    "It is mine: I can tell you the exact contents and there is a mark on the {noun} that only the owner would know.",
    "I bought this {noun} last year and still have the receipt and a photo of it on my phone from before I lost it.",
    "The {noun} has a detail I did not put in the report: I can describe the inside and the serial or label.",
    "I lost it on the day this was found, in the same area. I can describe the wear and every item that was with it.",
]
WEAK_PROOFS = ["I think this might be mine, it looks very similar to what I lost.", "Looks like my {noun}, can I have a look at it?"]


def log(msg: str) -> None:
    print(f"[seed] {msg}", flush=True)


def phrase_place(name: str, rng: random.Random) -> str:
    return rng.choice([f" at {name}", f" near {name}", f" in the area of {name}", f" around {name}"])


def describe(kind: str, o, color, brand, feat, place, rng) -> tuple[str, str]:
    cat, noun, *_ = o
    adj = f"{color} " + (f"{brand} " if brand else "")
    opener = rng.choice(LOST_OPENERS if kind == "lost" else FOUND_OPENERS)
    body = opener.format(adj=adj, noun=noun, where=phrase_place(place, rng))
    feature = feat[0] if kind == "lost" else feat[1]
    closer = rng.choice(LOST_CLOSERS if kind == "lost" else FOUND_CLOSERS)
    title = (f"Lost {brand + ' ' if brand and rng.random() < .5 else color + ' '}{noun}" if kind == "lost"
             else f"Found {color} {noun}")
    return title.strip(), " ".join(x for x in (body, feature, closer) if x).strip()


def seed(pairs: int, lost_only: int, found_only: int, reset: bool) -> None:
    s = get_settings()
    engine = create_engine(s.migration_database_url, pool_size=3)
    rng, fake = random.Random(42), Faker("en_US")
    Faker.seed(42)
    storage = get_storage()
    today = date.today()

    with transaction(engine=engine) as conn:
        if scalar(conn, "SELECT count(*) FROM users") > 0:
            if not reset:
                log("database already contains data; use --reset to rebuild it")
                return
            conn.execute(text("TRUNCATE outbox, audit_log, claim, match_item, match, embedding, item, location, users "
                              "RESTART IDENTITY CASCADE"))
            log("existing data removed")

    # ------------------------------------------------------------- users & places
    pw_hash = hash_password(DEMO_PASSWORD)
    with transaction(engine=engine) as conn:
        uid = {}
        for email, name, role in DEMO_USERS:
            uid[email] = scalar(conn, "INSERT INTO users (name,email,password_hash,phone) VALUES (:n,:e,:h,:p) RETURNING user_id",
                                n=name, e=email, h=pw_hash, p=fake.numerify("+1-555-01##"))
            if role != "user":
                conn.execute(text("UPDATE users SET role = CAST(:r AS user_role) WHERE user_id = :u"), {"r": role, "u": uid[email]})
        for i in range(40):
            name = fake.name()
            email = f"{name.lower().replace(' ', '.').replace(chr(39), '')}{i}@example.edu"
            uid[email] = scalar(conn, "INSERT INTO users (name,email,password_hash,phone) VALUES (:n,:e,:h,:p) RETURNING user_id",
                                n=name, e=email, h=pw_hash, p=fake.numerify("+1-555-01##"))
        loc_ids = [scalar(conn, """INSERT INTO location (location_name,campus,building,floor,latitude,longitude)
                                   VALUES (:n,:c,:b,:f,:la,:lo) RETURNING location_id""",
                          n=n, c=c, b=b, f=f, la=la, lo=lo) for n, c, b, f, la, lo in LOCATIONS]
        loc_name = dict(zip(loc_ids, [l[0] for l in LOCATIONS], strict=True))
    staff_ids = [uid["staff@lostfound.dev"], uid["staff2@lostfound.dev"], uid["admin@lostfound.dev"]]
    regular = [v for k, v in uid.items() if v not in staff_ids]
    log(f"{len(uid)} users, {len(loc_ids)} locations")

    # ---------------------------------------------------------------------- items
    def image_for(o, color, with_image, story_seed):
        if not with_image or o[2] is None:
            return []
        img = render(o[2], color, random.Random(story_seed))
        buf = io.BytesIO(); img.save(buf, "PNG")
        return [storage.save_image(buf.getvalue(), folder="seed")]

    def insert_item(conn, reporter, kind, o, color, brand, feat, loc, d, image_urls, extras_on):
        title, desc = describe(kind, o, color, brand, feat, loc_name[loc], rng)
        reported = min(datetime.now(timezone.utc), datetime.combine(d, datetime.min.time(), timezone.utc)
                       + timedelta(hours=rng.randint(1, 30)))
        item_id = scalar(conn, """INSERT INTO item (reporter_id, location_id, item_type, title, description, category, color, brand,
                                                    date_lost_or_found, image_urls, reported_at)
                                  VALUES (:r,:l,CAST(:t AS item_type),:ti,:d,CAST(:c AS item_category),:co,:b,:dt,:im,:ra)
                                  RETURNING item_id""",
                         r=reporter, l=loc, t=kind, ti=title, d=desc, c=o[0], co=color, b=brand, dt=d, im=image_urls, ra=reported)
        if extras_on and o[0] in EXTRAS:
            ex = EXTRAS[o[0]](rng)
            if o[0] == "pet":
                ex["species"] = o[1]
            conn.execute(text("""INSERT INTO outbox (aggregate, aggregate_id, event_type, payload)
                                 VALUES ('item_extras', :i, 'item_extras.set', CAST(:p AS jsonb))"""),
                         {"i": item_id, "p": json.dumps({"item_id": item_id, "category": o[0], "extras": ex})})
        return item_id

    true_pairs: list[tuple[int, int]] = []
    with transaction(engine=engine) as conn:
        for n in range(pairs + lost_only + found_only):
            o = rng.choice(OBJECTS)
            color, brand, feat = rng.choice(o[4] or COLORS), rng.choice(o[3]), rng.choice(o[5])
            if rng.random() < .8:                    # a detail the owner and the finder both noticed
                tl, tf = rng.choice(DETAIL_TEMPLATES)
                w = rng.choice(DETAIL_WORDS)
                feat = (f"{feat[0]} {tl.format(w=w)}", f"{feat[1]} {tf.format(w=w)}")
                if rng.random() < .35:
                    ini = rng.choice(INITIALS)
                    feat = (f"{feat[0]} Initials {ini} inside.", f"{feat[1]} The initials {ini} are written inside.")
            base = today - timedelta(days=rng.randint(4, 110))
            loc_l = rng.choice(loc_ids)
            loc_f = loc_l if rng.random() < .7 else rng.choice(loc_ids)
            has_pair = n < pairs
            owner, finder = rng.sample(regular, 2)
            if has_pair:
                d_found = min(today, base + timedelta(days=rng.randint(0, 5)))
                shared_seed = rng.randrange(10**6)
                li = insert_item(conn, owner, "lost", o, color, brand, feat, loc_l, base,
                                 image_for(o, color, rng.random() < .6, shared_seed), rng.random() < .6)
                fi = insert_item(conn, finder, "found", o, color, brand, feat, loc_f, d_found,
                                 image_for(o, color, rng.random() < .6, shared_seed + 1), rng.random() < .6)
                true_pairs.append((li, fi))
            elif n < pairs + lost_only:
                insert_item(conn, owner, "lost", o, color, brand, feat, loc_l, base,
                            image_for(o, color, rng.random() < .5, rng.randrange(10**6)), rng.random() < .6)
            else:
                insert_item(conn, finder, "found", o, color, brand, feat, loc_f, base,
                            image_for(o, color, rng.random() < .5, rng.randrange(10**6)), rng.random() < .6)
    total_items = pairs * 2 + lost_only + found_only
    log(f"{total_items} items inserted ({len(true_pairs)} lost/found pairs describe the same object)")

    # ----------------------------------------- real embeddings (MiniLM + CLIP, local)
    t0 = time.time()
    with transaction(engine=engine) as conn:
        ids = [r["item_id"] for r in rows(conn, "SELECT item_id FROM item ORDER BY item_id")]
        for k, i in enumerate(ids, 1):
            embed_item(conn, i)
            if k % 60 == 0:
                log(f"embedded {k}/{len(ids)}")
    log(f"embeddings done in {time.time() - t0:.0f}s")

    # ------------------------------------------------------------------- matching
    with transaction(engine=engine) as conn:
        created = 0
        for i in ids:
            created += sum(1 for m in matching.refresh_matches(conn, i, backend="pg") if m["out_is_new"])
    log(f"{created} match suggestions created by find_matches() / RRF")

    # ---------------------------------------------------------- workflow simulation
    pair_set = set(true_pairs)
    with transaction(engine=engine) as conn:
        suggested = rows(conn, "SELECT match_id, lost_item_id, found_item_id, lost_reporter_id FROM v_match_details "
                               "WHERE verification_status = 'suggested'")
    true_hits = [m for m in suggested if (m["lost_item_id"], m["found_item_id"]) in pair_set]
    log(f"{len(true_hits)} of {len(true_pairs)} true pairs were suggested (recall of the engine on this data)")
    rng.shuffle(true_hits)
    confirmed = []
    for m in true_hits[: int(len(true_hits) * .55)]:
        with transaction(staff_ids[0], engine=engine) as conn:
            try:
                conn.execute(text("SELECT confirm_match(:m,:s)"), {"m": m["match_id"], "s": rng.choice(staff_ids)})
                confirmed.append(m)
            except Exception:                    # already rejected as a rival of an earlier confirmation
                pass
    false_hits = [m for m in suggested if (m["lost_item_id"], m["found_item_id"]) not in pair_set]
    for m in rng.sample(false_hits, min(30, len(false_hits))):
        with transaction(staff_ids[0], engine=engine) as conn:
            if scalar(conn, "SELECT verification_status::text FROM match WHERE match_id=:m", m=m["match_id"]) == "suggested":
                conn.execute(text("SELECT reject_match(:m,:s)"), {"m": m["match_id"], "s": rng.choice(staff_ids)})

    def file_claim(claimant, found_id, match_id, proof):
        with transaction(claimant, engine=engine) as conn:
            return scalar(conn, """INSERT INTO claim (item_id, claimant_id, match_id, proof_description)
                                   VALUES (:i,:c,:m,:p) RETURNING claim_id""", i=found_id, c=claimant, m=match_id, p=proof)

    approved_found, queue = [], 0
    for m in confirmed:
        roll = rng.random()
        if roll < .12:
            continue                                         # owner never followed up
        own = file_claim(m["lost_reporter_id"], m["found_item_id"], m["match_id"], rng.choice(PROOFS).format(noun="item"))
        if rng.random() < .3:
            file_claim(rng.choice([r for r in regular if r != m["lost_reporter_id"]]), m["found_item_id"], None,
                               rng.choice(WEAK_PROOFS).format(noun="item"))
        staff = rng.choice(staff_ids)
        with transaction(staff, engine=engine) as conn:
            if roll < .70:                                   # verified and approved
                conn.execute(text("SELECT start_claim_review(:c,:s)"), {"c": own, "s": staff})
                conn.execute(text("SELECT approve_claim(:c,:s,'Proof matched the report.')"), {"c": own, "s": staff})
                approved_found.append(m["found_item_id"])
            elif roll < .78:                                 # proof not convincing
                conn.execute(text("SELECT reject_claim(:c,:s,'Proof did not match the item.')"), {"c": own, "s": staff})
            elif roll < .86:                                 # being reviewed right now
                conn.execute(text("SELECT start_claim_review(:c,:s)"), {"c": own, "s": staff}); queue += 1
            else:
                queue += 1                                   # waiting in the queue
    for found_id in approved_found[: int(len(approved_found) * .7)]:
        with transaction(staff_ids[1], engine=engine) as conn:
            conn.execute(text("SELECT mark_returned(:i,:s)"), {"i": found_id, "s": staff_ids[1]})
    # a few unrelated pending claims on open found items so the queue is never empty
    with transaction(engine=engine) as conn:
        open_found = [r["item_id"] for r in rows(conn, "SELECT item_id FROM item WHERE item_type='found' AND status='open' "
                                                       "ORDER BY item_id LIMIT 40")]
    for i in rng.sample(open_found, min(8, len(open_found))):
        with transaction(engine=engine) as conn:
            reporter = scalar(conn, "SELECT reporter_id FROM item WHERE item_id=:i", i=i)
        try:
            file_claim(rng.choice([r for r in regular if r != reporter]), i, None, rng.choice(PROOFS).format(noun="item")); queue += 1
        except Exception:
            pass
    # close some of the oldest open reports
    with transaction(engine=engine) as conn:
        old = rows(conn, "SELECT item_id, reporter_id FROM item WHERE status='open' ORDER BY date_lost_or_found LIMIT 14")
    for r in old:
        with transaction(r["reporter_id"], engine=engine) as conn:
            conn.execute(text("SELECT close_item(:i,:u)"), {"i": r["item_id"], "u": r["reporter_id"]})
    log("claims, confirmations, returns and closures simulated through the real procedures")

    # --------------------------------- back-date history so dashboards show real spans
    with transaction(engine=engine) as conn:
        try:
            conn.execute(text("SET LOCAL session_replication_role = replica"))   # needs superuser; skips guard/audit triggers
            conn.execute(text("""UPDATE match m SET created_at = LEAST(now(), GREATEST(il.reported_at, iF.reported_at) + interval '20 minutes')
                                 FROM match_item a JOIN item il ON il.item_id = a.item_id
                                 JOIN match_item b ON b.match_id = a.match_id AND b.role = 'found' JOIN item iF ON iF.item_id = b.item_id
                                 WHERE a.match_id = m.match_id AND a.role = 'lost'"""))
            conn.execute(text("""UPDATE claim c SET
                                   submitted_at = LEAST(now() - interval '1 hour', i.reported_at + (1 + (c.claim_id * 7) % 72) * interval '1 hour'),
                                   reviewed_at  = CASE WHEN c.reviewed_at IS NULL THEN NULL
                                       ELSE LEAST(now(), i.reported_at + (4 + (c.claim_id * 7) % 72 + 2 + (c.claim_id * 13) % 40) * interval '1 hour') END
                                 FROM item i WHERE i.item_id = c.item_id"""))
            conn.execute(text("UPDATE audit_log a SET changed_at = i.reported_at FROM item i "
                              "WHERE a.table_name='item' AND a.row_pk = i.item_id AND a.action='INSERT'"))
            conn.execute(text("UPDATE audit_log a SET changed_at = c.submitted_at FROM claim c "
                              "WHERE a.table_name='claim' AND a.row_pk = c.claim_id AND a.action='INSERT'"))
            conn.execute(text("UPDATE audit_log a SET changed_at = COALESCE(c.reviewed_at, c.submitted_at + interval '2 hours') FROM claim c "
                              "WHERE a.table_name='claim' AND a.row_pk = c.claim_id AND a.action='UPDATE'"))
            conn.execute(text("UPDATE audit_log a SET changed_at = m.created_at + interval '12 hours' FROM match m "
                              "WHERE a.table_name='match' AND a.row_pk = m.match_id AND a.action='UPDATE'"))
            conn.execute(text("UPDATE audit_log a SET changed_at = m.created_at FROM match m "
                              "WHERE a.table_name='match' AND a.row_pk = m.match_id AND a.action='INSERT'"))
            # item status history: matched ~ day after match, claimed = approval, returned = 1..72h later
            conn.execute(text("""UPDATE audit_log a SET changed_at = CASE a.new_data ->> 'status'
                    WHEN 'claimed'  THEN COALESCE((SELECT max(reviewed_at) FROM claim WHERE item_id = a.row_pk AND result = 'approved'), a.changed_at)
                    WHEN 'returned' THEN COALESCE((SELECT max(reviewed_at) FROM claim WHERE item_id = a.row_pk AND result = 'approved'), a.changed_at)
                                         + (1 + (a.row_pk * 11) % 72) * interval '1 hour'
                    WHEN 'matched'  THEN COALESCE((SELECT min(m.created_at) FROM match m JOIN match_item mi USING (match_id)
                                                   WHERE mi.item_id = a.row_pk), a.changed_at) + interval '1 day'
                    ELSE a.changed_at END
                  WHERE a.table_name = 'item' AND a.action = 'UPDATE' AND a.new_data ->> 'status' IN ('claimed','returned','matched')"""))
            conn.execute(text("UPDATE audit_log SET changed_at = LEAST(changed_at, now())"))
            log("history back-dated")
        except Exception as e:                        # noqa: BLE001
            log(f"skipped back-dating (needs a superuser owner role): {e.__class__.__name__}")

    with transaction(engine=engine) as conn:
        conn.execute(text("SELECT refresh_analytics()"))
        stats = rows(conn, "SELECT status::text AS status, item_type::text AS item_type, count(*)::int AS n FROM item GROUP BY 1,2 ORDER BY 2,1")
        counts = {t: scalar(conn, f"SELECT count(*) FROM {t}") for t in ("users", "item", "embedding", "match", "claim", "audit_log", "outbox")}
    log("rows: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    log("items by type/status: " + ", ".join(f"{r['item_type']}/{r['status']}={r['n']}" for r in stats))
    print(f"""
Demo accounts (password for all: {DEMO_PASSWORD})
  admin  : admin@lostfound.dev
  staff  : staff@lostfound.dev, staff2@lostfound.dev
  users  : alice@lostfound.dev, bob@lostfound.dev, carol@lostfound.dev
The worker now relays {counts['outbox']} outbox events to Qdrant, Mongo and Redis (notifications, vectors, extras).
""")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe existing data first")
    ap.add_argument("--pairs", type=int, default=110)
    ap.add_argument("--lost-only", type=int, default=50)
    ap.add_argument("--found-only", type=int, default=50)
    a = ap.parse_args()
    seed(a.pairs, a.lost_only, a.found_only, a.reset)


if __name__ == "__main__":
    sys.exit(main())
