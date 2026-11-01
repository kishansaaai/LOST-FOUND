"""Namespaced, versioned Redis cache.

Key shape:   lf:<namespace>:v<version>:<sha1(query)>
Invalidation is O(1): bump `lf:ver:<namespace>`; old keys become unreachable and
expire by TTL. The outbox worker bumps versions when items/matches change."""
import hashlib
import json

NS = "lf"


def _ver(r, ns: str) -> int:
    return int(r.get(f"{NS}:ver:{ns}") or 1)


def _key(r, ns: str, query: str) -> str:
    return f"{NS}:{ns}:v{_ver(r, ns)}:{hashlib.sha1(query.encode()).hexdigest()}"


def get(r, ns: str, query: str):
    try:
        raw = r.get(_key(r, ns, query))
        return json.loads(raw) if raw else None
    except Exception:
        return None                      # cache is optional: never fail a request because of it


def put(r, ns: str, query: str, value, ttl: int) -> None:
    try:
        r.setex(_key(r, ns, query), ttl, json.dumps(value, default=str))
    except Exception:
        pass


def invalidate(r, ns: str) -> None:
    try:
        r.incr(f"{NS}:ver:{ns}")
    except Exception:
        pass                             # cache is optional; stale entries expire by TTL
