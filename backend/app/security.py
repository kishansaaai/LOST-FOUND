"""Password hashing and JWT access/refresh tokens.

Refresh tokens are single-use: each carries a `jti` stored in Redis; refreshing
deletes the old jti and stores a new one (rotation). Logging out deletes the jti and
puts the access token's jti on a revocation list until it would have expired."""
import time
import uuid

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import get_settings

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, Exception):
        return False


def _encode(sub: int, kind: str, ttl_seconds: int) -> tuple[str, str, int]:
    s = get_settings()
    now = int(time.time())
    jti = uuid.uuid4().hex
    exp = now + ttl_seconds
    token = jwt.encode({"sub": str(sub), "typ": kind, "jti": jti, "iat": now, "exp": exp},
                       s.jwt_secret, algorithm="HS256")
    return token, jti, ttl_seconds


def create_access_token(user_id: int) -> tuple[str, str, int]:
    return _encode(user_id, "access", get_settings().access_token_minutes * 60)


def create_refresh_token(user_id: int) -> tuple[str, str, int]:
    return _encode(user_id, "refresh", get_settings().refresh_token_days * 86400)


def decode_token(token: str, kind: str) -> dict:
    """Raises jwt.PyJWTError on any problem (bad signature, expired, wrong type)."""
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    if payload.get("typ") != kind:
        raise jwt.InvalidTokenError("wrong token type")
    return payload
