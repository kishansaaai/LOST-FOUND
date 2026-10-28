"""Tiny data factory for DB tests (plain SQL, owner connection)."""
import itertools

import numpy as np

_counter = itertools.count(1)


def unit(rng: np.random.Generator, dim: int) -> np.ndarray:
    v = rng.normal(size=dim)
    return v / np.linalg.norm(v)


def near(base: np.ndarray, rng: np.random.Generator, noise: float) -> np.ndarray:
    """A unit vector at a controlled angle from `base` (smaller noise = more similar)."""
    v = base + noise * unit(rng, len(base))
    return v / np.linalg.norm(v)


def lit(v: np.ndarray | None) -> str | None:
    return None if v is None else "[" + ",".join(f"{x:.6f}" for x in v) + "]"


class Factory:
    def __init__(self, db):
        self.db = db
        self.rng = np.random.default_rng(7)

    def user(self, role="user", name=None) -> int:
        n = next(_counter)
        row = self.db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, 'x') RETURNING user_id",
            (name or f"User {n}", f"user{n}@example.com")).fetchone()
        if role != "user":
            self.db.execute("UPDATE users SET role = %s WHERE user_id = %s", (role, row[0]))
        return row[0]

    def location(self, name=None) -> int:
        n = next(_counter)
        return self.db.execute(
            "INSERT INTO location (location_name, campus) VALUES (%s, 'Main') RETURNING location_id",
            (name or f"Place {n}",)).fetchone()[0]

    def item(self, reporter, location, item_type="lost", title="Black backpack", category="wallet_bag",
             color="black", brand=None, date="2025-01-10", description="A black backpack with a laptop",
             text_vec=None, image_vec=None) -> int:
        item_id = self.db.execute(
            """INSERT INTO item (reporter_id, location_id, item_type, title, description, category,
                                 color, brand, date_lost_or_found)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING item_id""",
            (reporter, location, item_type, title, description, category, color, brand, date)).fetchone()[0]
        if text_vec is not None:
            self.embed(item_id, text_vec, image_vec)
        return item_id

    def embed(self, item_id, text_vec, image_vec=None):
        self.db.execute(
            "INSERT INTO embedding (item_id, text_vect, image_vector, model_name) "
            "VALUES (%s, %s::vector, %s::vector, 'test')",
            (item_id, lit(text_vec), lit(image_vec)))

    def claim(self, item, claimant, match_id=None, proof="It has my initials inside") -> int:
        return self.db.execute(
            "INSERT INTO claim (item_id, claimant_id, match_id, proof_description) "
            "VALUES (%s,%s,%s,%s) RETURNING claim_id", (item, claimant, match_id, proof)).fetchone()[0]

    def status(self, item_id):
        return self.db.execute("SELECT status FROM item WHERE item_id=%s", (item_id,)).fetchone()[0]
