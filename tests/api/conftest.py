import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import outbox


@pytest.fixture
def client(db, engine_rw, fake_stores, app_settings):
    from app.main import create_app
    with TestClient(create_app()) as c:
        c.db, c.engine = db, engine_rw
        c.drain = lambda: outbox.drain(engine_rw)
        yield c


class Session:
    """A logged-in API user."""
    def __init__(self, client, user, tokens):
        self.client, self.user, self.tokens = client, user, tokens
        self.id = user["id"]
        self.h = {"Authorization": f"Bearer {tokens['access_token']}"}

    def get(self, url, **kw): return self.client.get(url, headers=self.h, **kw)
    def post(self, url, **kw): return self.client.post(url, headers=self.h, **kw)
    def patch(self, url, **kw): return self.client.patch(url, headers=self.h, **kw)


@pytest.fixture
def make_user(client):
    n = {"i": 0}

    def _make(name="Pat", role="user") -> Session:
        n["i"] += 1
        r = client.post("/auth/register", json={"name": name, "email": f"{name.lower()}{n['i']}@example.com",
                                                "password": "correct-horse-1"})
        assert r.status_code == 201, r.text
        body = r.json()
        if role != "user":
            client.db.execute("UPDATE users SET role = %s WHERE user_id = %s", (role, body["user"]["id"]))
        return Session(client, body["user"], body)
    return _make


def png_bytes(color=(200, 30, 30), size=(64, 64), fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


@pytest.fixture
def location(client):
    return client.db.execute("INSERT INTO location (location_name, campus) VALUES ('Main Library','North') "
                             "RETURNING location_id").fetchone()[0]
