"""The product's main story, through the HTTP API, with every store attached."""
from datetime import date, timedelta

from tests.api.conftest import png_bytes


def new_item(u, loc, kind, title, desc, days_ago=2, **kw):
    body = dict(item_type=kind, title=title, description=desc, category="wallet_bag", location_id=loc,
                date_lost_or_found=str(date.today() - timedelta(days=days_ago)), color="black")
    body.update(kw)
    r = u.post("/items", json=body)
    assert r.status_code == 201, r.text
    return r.json()["item_id"]


def test_report_match_claim_verify_return(client, make_user, location):
    alice, bob, carol, staff = make_user("Alice"), make_user("Bob"), make_user("Carol"), make_user("Sam", "staff")
    lost = new_item(alice, location, "lost", "Black leather wallet", "black leather wallet with a student card and cash", days_ago=3)
    found = new_item(bob, location, "found", "Wallet found near desk", "found a black leather wallet containing a student card", days_ago=1)
    new_item(bob, location, "found", "Blue umbrella", "blue folding umbrella wooden handle", category="other", color="blue")
    client.drain()

    # --- matching ran by itself and is explainable to the reporter
    ms = alice.get(f"/items/{lost}/matches").json()["matches"]
    assert [m["other_item_id"] for m in ms] == [found]
    ex = ms[0]["explanation"]
    assert ex["signals"][0]["signal"] == "text" and ex["signals"][0]["rank"] == 1 and "1/(60+1)" in ex["formula"]
    assert carol.get(f"/items/{lost}/matches").status_code == 403           # strangers cannot browse matches
    assert alice.get("/notifications").json()["unread"] == 1                 # "possible match" notification
    match_id = ms[0]["match_id"]

    # --- staff confirms the match
    assert staff.post(f"/staff/matches/{match_id}/confirm").status_code == 200
    assert client.get(f"/items/{lost}").json()["status"] == "matched"

    # --- Alice claims Bob's found wallet; Carol files a competing claim
    c_alice = alice.post(f"/items/{found}/claims", json={"proof_description": "It has my name on the student card and 40 dollars", "match_id": match_id})
    assert c_alice.status_code == 201, c_alice.text
    c_carol = carol.post(f"/items/{found}/claims", json={"proof_description": "Pretty sure this wallet is mine honestly"})
    assert c_carol.status_code == 201
    assert alice.post(f"/items/{found}/claims", json={"proof_description": "second attempt at the same item"}).status_code == 409
    assert bob.post(f"/items/{found}/claims", json={"proof_description": "claiming my own found report"}).status_code == 409
    cid_a, cid_c = c_alice.json()["claim_id"], c_carol.json()["claim_id"]

    # --- RLS: claimants see only their own claims
    assert [c["claim_id"] for c in carol.get("/claims/mine").json()["claims"]] == [cid_c]
    assert carol.get(f"/claims/{cid_a}").status_code == 404

    # --- staff reviews
    q = staff.get("/staff/claims/queue").json()["claims"]
    assert {c["claim_id"]: c["competing_claims"] for c in q} == {cid_a: 2, cid_c: 2}
    detail = staff.get(f"/staff/claims/{cid_a}").json()
    assert detail["item"]["title"] == "Wallet found near desk" and len(detail["other_claims"]) == 1
    assert staff.post(f"/staff/claims/{cid_a}/start-review").json()["verification_status"] == "under_review"
    assert user_forbidden(alice, f"/staff/claims/{cid_a}/approve")
    assert staff.post(f"/staff/claims/{cid_a}/approve", json={"notes": "Student card matches"}).json()["result"] == "approved"
    assert staff.post(f"/staff/claims/{cid_a}/approve", json={}).status_code == 409           # already decided
    assert carol.get("/claims/mine").json()["claims"][0]["result"] == "denied"                # auto-rejected competitor
    assert client.get(f"/items/{found}").json()["status"] == "claimed"
    assert client.post(f"/items/{found}/claims").status_code == 401

    # --- hand-over
    assert staff.post(f"/staff/items/{found}/mark-returned").status_code == 200
    assert client.get(f"/items/{found}").json()["status"] == "returned"
    assert client.get(f"/items/{lost}").json()["status"] == "returned"                        # lost report closed too

    # --- audit trail is complete and staff-only
    trail = staff.get(f"/staff/audit?table_name=item&row_pk={found}").json()["entries"]
    assert [e["new_data"]["status"] for e in reversed(trail)] == ["open", "matched", "claimed", "returned"]
    assert alice.get("/staff/audit").status_code == 403

    # --- notifications reached the right people, through Mongo
    client.drain()
    kinds = {n["type"] for n in alice.get("/notifications").json()["notifications"]}
    assert {"match.suggested", "match.confirmed", "claim.approved", "item.returned"} <= kinds
    assert "claim.denied" in {n["type"] for n in carol.get("/notifications").json()["notifications"]}
    assert alice.post("/notifications/read-all").json()["updated"] >= 4
    assert alice.get("/notifications/unread-count").json()["unread"] == 0

    # --- Mongo DELETE: own notifications only
    mine = alice.get("/notifications").json()["notifications"]
    assert alice.delete(f"/notifications/{mine[0]['id']}").json() == {"deleted": 1}
    assert len(alice.get("/notifications").json()["notifications"]) == len(mine) - 1
    assert carol.delete(f"/notifications/{mine[1]['id']}").status_code == 404      # someone else's
    assert alice.delete("/notifications/not-an-id").status_code == 404

    # --- analytics
    assert staff.post("/analytics/refresh").status_code == 202
    s = staff.get("/analytics/summary").json()
    rec = {r["category"]: r for r in s["recovery"]}
    assert rec["ALL"]["found_items"] == 2 and rec["ALL"]["returned_items"] == 1
    assert alice.get("/analytics/summary").status_code == 403


def user_forbidden(u, path):
    return u.post(path, json={}).status_code == 403


def test_validation_and_security_of_item_creation(client, make_user, location):
    u = make_user()
    ok = dict(item_type="lost", title="Keys", description="car keys on a red lanyard", category="keys",
              location_id=location, date_lost_or_found=str(date.today()))
    assert u.post("/items", json=ok).status_code == 201
    assert client.post("/items", json=ok).status_code == 401
    assert u.post("/items", json={**ok, "date_lost_or_found": str(date.today() + timedelta(days=1))}).status_code == 422
    assert u.post("/items", json={**ok, "category": "spaceship"}).status_code == 422
    assert u.post("/items", json={**ok, "item_type": "stolen"}).status_code == 422
    assert u.post("/items", json={**ok, "image_urls": ["/etc/passwd"]}).status_code == 422
    assert u.post("/items", json={**ok, "image_urls": ["/uploads/../../etc/x.jpg"]}).status_code == 422
    assert u.post("/items", json={**ok, "location_id": 9999}).status_code == 409           # FK violation -> 409
    assert u.post("/items", json={**ok, "extras": {"nested": {"a": 1}}}).status_code == 422
    assert u.post("/items", json={**ok, "title": "x"}).status_code == 422


def test_sql_injection_attempts_are_inert(client, make_user, location):
    u = make_user()
    u.post("/items", json=dict(item_type="lost", title="Keys", description="car keys", category="keys",
                               location_id=location, date_lost_or_found=str(date.today())))
    evil = "'; DROP TABLE item; --"
    assert client.get("/items", params={"q": evil}).status_code == 200
    assert client.get("/items", params={"category": evil}).status_code == 422
    assert client.get("/items", params={"status": evil}).status_code == 422
    assert client.get("/items").json()["total"] == 1                                         # table still there


def test_search_filters_pagination_and_fulltext(client, make_user, location):
    u = make_user()
    for i in range(5):
        new_item(u, location, "lost", f"Silver laptop {i}", "silver dell laptop with stickers", category="electronics", days_ago=i)
    new_item(u, location, "found", "Green scarf", "wool green scarf", category="clothing", color="green")
    assert client.get("/items", params={"q": "laptop"}).json()["total"] == 5
    assert client.get("/items", params={"q": "scarf OR laptop"}).json()["total"] == 6
    assert client.get("/items", params={"item_type": "found"}).json()["total"] == 1
    assert client.get("/items", params={"category": "clothing"}).json()["items"][0]["title"] == "Green scarf"
    page = client.get("/items", params={"page_size": 2, "page": 3}).json()
    assert page["total"] == 6 and len(page["items"]) == 2
    d = (date.today() - timedelta(days=2)).isoformat()
    assert client.get("/items", params={"date_from": d, "item_type": "lost"}).json()["total"] == 3


def test_cache_is_used_and_invalidated(client, make_user, location, fake_stores):
    u = make_user()
    new_item(u, location, "lost", "Red hat", "a red woolen hat", category="clothing")
    assert client.get("/items", params={"q": "hat"}).json()["total"] == 1
    assert any(k.startswith("lf:items:v1:") for k in fake_stores.redis.keys("*"))            # cached
    new_item(u, location, "lost", "Blue hat", "a blue woolen hat", category="clothing")
    client.drain()                                                                           # worker bumps the version
    assert client.get("/items", params={"q": "hat"}).json()["total"] == 2                    # fresh, not stale


def test_upload_validation(client, make_user):
    u = make_user()
    ok = u.post("/uploads", files={"file": ("a.png", png_bytes(), "image/png")})
    assert ok.status_code == 201 and ok.json()["url"].startswith("/uploads/items/") and ok.json()["url"].endswith(".jpg")
    assert client.get(ok.json()["url"]).status_code == 200                                    # served statically
    assert u.post("/uploads", files={"file": ("a.png", b"this is not an image", "image/png")}).status_code == 422
    assert u.post("/uploads", files={"file": ("a.svg", b"<svg onload=alert(1)/>", "image/svg+xml")}).status_code == 422
    assert client.post("/uploads", files={"file": ("a.png", png_bytes(), "image/png")}).status_code == 401


def test_image_flow_extras_and_search_by_image(client, make_user, location):
    u = make_user()
    red = u.post("/uploads", files={"file": ("r.png", png_bytes((220, 20, 20)), "image/png")}).json()["url"]
    blue = u.post("/uploads", files={"file": ("b.png", png_bytes((20, 20, 220)), "image/png")}).json()["url"]
    a = new_item(u, location, "found", "Red thing", "something red", category="other", image_urls=[red],
                 extras={"serial_number": "SN-42"})
    new_item(u, location, "found", "Blue thing", "something blue", category="other", image_urls=[blue])
    client.drain()
    assert client.get(f"/items/{a}").json()["extras"] == {"serial_number": "SN-42"}          # Mongo, via outbox
    r = client.post("/search/by-image", files={"file": ("q.png", png_bytes((215, 25, 25)), "image/png")})
    assert r.status_code == 200 and r.json()["items"][0]["item_id"] == a                      # closest colour first
    assert client.post("/search/by-image", files={"file": ("q.txt", b"nope", "text/plain")}).status_code == 422


def test_find_matches_button_and_permissions(client, make_user, location):
    alice, bob = make_user("Alice"), make_user("Bob")
    lost = new_item(alice, location, "lost", "Black wallet", "black leather wallet with cards")
    assert alice.post(f"/items/{lost}/find-matches").status_code == 409                       # embedding not ready yet
    client.drain()
    new_item(bob, location, "found", "Wallet", "black leather wallet with cards inside")
    client.drain()
    assert alice.post(f"/items/{lost}/find-matches").json()["found"] == 1
    assert bob.post(f"/items/{lost}/find-matches").status_code == 403


def test_edit_and_close_item(client, make_user, location):
    a, b = make_user("A"), make_user("B")
    i = new_item(a, location, "lost", "Keys", "car keys on a red lanyard", category="keys")
    assert b.patch(f"/items/{i}", json={"title": "Hijacked"}).status_code == 403
    assert a.patch(f"/items/{i}", json={"title": "Car keys"}).status_code == 200
    assert a.patch(f"/items/{i}", json={"category": "bogus"}).status_code == 422
    assert b.post(f"/items/{i}/close").status_code == 403
    assert a.post(f"/items/{i}/close").status_code == 200
    assert a.patch(f"/items/{i}", json={"title": "Too late"}).status_code == 409
    assert client.get(f"/items/{i}").json()["status"] == "closed"


def test_staff_match_listing_and_reject(client, make_user, location):
    alice, bob, staff = make_user("Alice"), make_user("Bob"), make_user("Sam", "staff")
    new_item(alice, location, "lost", "Black wallet", "black leather wallet with cards")
    new_item(bob, location, "found", "Wallet", "black leather wallet with cards inside")
    client.drain()
    ms = staff.get("/staff/matches?status=suggested").json()
    assert ms["total"] == 1
    assert alice.get("/staff/matches").status_code == 403
    mid = ms["matches"][0]["match_id"]
    assert staff.post(f"/staff/matches/{mid}/reject").status_code == 200
    assert staff.post(f"/staff/matches/{mid}/reject").status_code == 409
    assert staff.get("/staff/matches?status=suggested").json()["total"] == 0


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    deep = client.get("/health/deep").json()
    assert deep["postgres"] == "ok" and deep["redis"] == "ok"
