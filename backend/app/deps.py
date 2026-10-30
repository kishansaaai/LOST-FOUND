"""Request dependencies: authentication, role checks, Redis rate limiting."""
import logging
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
from .db import one, transaction
from .security import decode_token
from .stores import get_redis

log = logging.getLogger("deps")
bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    id: int
    name: str
    email: str
    role: str

    @property
    def is_staff(self) -> bool:
        return self.role in ("staff", "admin")


def revoked_key(jti: str) -> str:
    return f"lf:revoked:{jti}"


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if creds is None:
        raise HTTPException(401, "not authenticated", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = decode_token(creds.credentials, "access")
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid or expired token", headers={"WWW-Authenticate": "Bearer"}) from None
    try:
        if get_redis().exists(revoked_key(claims["jti"])):
            raise HTTPException(401, "token revoked")
    except HTTPException:
        raise
    except Exception:                              # Redis down: fail open for reads, log it
        log.warning("revocation list unavailable")
    with transaction() as conn:
        u = one(conn, "SELECT user_id AS id, name, email, role::text AS role FROM users WHERE user_id = :u",
                u=int(claims["sub"]))
    if u is None:
        raise HTTPException(401, "user no longer exists")
    return Principal(**u)                          # role is read fresh: demotions apply immediately


def optional_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal | None:
    """Anonymous visitors may browse; a valid token just adds personalised fields."""
    return current_user(creds) if creds is not None else None


def require_staff(user: Principal = Depends(current_user)) -> Principal:
    if not user.is_staff:
        raise HTTPException(403, "staff only")
    return user


def require_admin(user: Principal = Depends(current_user)) -> Principal:
    if user.role != "admin":
        raise HTTPException(403, "admin only")
    return user


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def rate_limit(name: str, limit: int, window: int):
    """Fixed-window limiter per client IP. Returns a FastAPI dependency."""
    def dep(request: Request):
        key = f"lf:rl:{name}:{client_ip(request)}"
        try:
            r = get_redis()
            n = r.incr(key)
            if n == 1:
                r.expire(key, window)
            if n > limit * get_settings().rate_limit_scale:
                raise HTTPException(429, "too many requests, slow down",
                                    headers={"Retry-After": str(max(r.ttl(key), 1))})
        except HTTPException:
            raise
        except Exception:
            log.warning("rate limiter unavailable")
    return dep
