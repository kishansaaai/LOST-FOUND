

def test_register_login_me_and_duplicate_email(client):
    r = client.post("/auth/register", json={"name": "Ann", "email": "Ann@Example.com", "password": "correct-horse-1"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "user"
    assert client.post("/auth/register", json={"name": "Ann2", "email": "ann@example.COM", "password": "correct-horse-1"}).status_code == 409
    tok = client.post("/auth/login", json={"email": "ann@example.com", "password": "correct-horse-1"}).json()
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
    assert me["email"].lower() == "ann@example.com" and "password_hash" not in me


def test_weak_input_and_bad_credentials(client):
    assert client.post("/auth/register", json={"name": "A", "email": "not-an-email", "password": "x"}).status_code == 422
    client.post("/auth/register", json={"name": "Ann", "email": "ann@example.com", "password": "correct-horse-1"})
    r = client.post("/auth/login", json={"email": "ann@example.com", "password": "wrong-password"})
    assert r.status_code == 401
    assert client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever-123"}).status_code == 401


def test_protected_endpoints_need_a_valid_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/claims/mine").status_code == 401


def test_refresh_tokens_rotate_and_cannot_be_replayed(client, make_user):
    u = make_user()
    old = u.tokens["refresh_token"]
    new = client.post("/auth/refresh", json={"refresh_token": old})
    assert new.status_code == 200 and new.json()["refresh_token"] != old
    assert client.post("/auth/refresh", json={"refresh_token": old}).status_code == 401      # replay refused
    assert client.post("/auth/refresh", json={"refresh_token": new.json()["access_token"]}).status_code == 401  # wrong type


def test_logout_revokes_refresh_token(client, make_user):
    u = make_user()
    assert u.post("/auth/logout", json={"refresh_token": u.tokens["refresh_token"]}).status_code == 204
    assert client.post("/auth/refresh", json={"refresh_token": u.tokens["refresh_token"]}).status_code == 401


def test_login_is_rate_limited(client):
    codes = [client.post("/auth/login", json={"email": "x@example.com", "password": "nope-nope-1"}).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10 and 429 in codes[10:]


def test_profile_update_and_password_change(client, make_user):
    u = make_user("Zed")
    assert u.patch("/auth/me", json={"name": "Zed Z", "phone": "555-0100"}).json()["name"] == "Zed Z"
    assert u.patch("/auth/me", json={"new_password": "brand-new-pass-9", "current_password": "wrong"}).status_code == 403
    assert u.patch("/auth/me", json={"new_password": "brand-new-pass-9", "current_password": "correct-horse-1"}).status_code == 200
    assert client.post("/auth/login", json={"email": u.user["email"], "password": "brand-new-pass-9"}).status_code == 200


def test_role_checks(client, make_user):
    user, staff, admin = make_user("U"), make_user("S", "staff"), make_user("A", "admin")
    assert user.get("/staff/claims/queue").status_code == 403
    assert staff.get("/staff/claims/queue").status_code == 200
    assert staff.get("/admin/users").status_code == 403
    assert admin.get("/admin/users").status_code == 200


def test_admin_role_management(client, make_user):
    admin, user = make_user("A", "admin"), make_user("U")
    r = admin.patch(f"/admin/users/{user.id}/role", json={"role": "staff"})
    assert r.status_code == 200 and r.json()["role"] == "staff"
    assert user.get("/staff/claims/queue").status_code == 200            # role is read fresh, no re-login needed
    assert admin.patch(f"/admin/users/{admin.id}/role", json={"role": "user"}).status_code == 409   # last admin
    assert user.patch(f"/admin/users/{admin.id}/role", json={"role": "user"}).status_code == 403
    assert admin.patch(f"/admin/users/{user.id}/role", json={"role": "root"}).status_code == 422


def test_session_store_outage_fails_closed_with_503(client, make_user, monkeypatch):
    u = make_user()
    from app.routers import auth as auth_router

    class Down:
        def __getattr__(self, _):
            raise ConnectionError("redis down")
    monkeypatch.setattr(auth_router, "get_redis", lambda: Down())
    r = client.post("/auth/login", json={"email": u.user["email"], "password": "correct-horse-1"})
    assert r.status_code == 503
    assert client.post("/auth/refresh", json={"refresh_token": u.tokens["refresh_token"]}).status_code == 503
