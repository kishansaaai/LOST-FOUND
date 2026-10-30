"""Clients for the non-relational stores (Mongo, Redis, Qdrant).

None of them is a source of truth: Postgres is. Everything here can be rebuilt from
Postgres (`make reindex`) or discarded (cache). Tests inject in-memory fakes via
`set_clients`."""
from functools import lru_cache

from .config import get_settings

_override: dict = {}


def set_clients(mongo=None, redis=None, qdrant=None) -> None:
    _override.clear()
    for k, v in (("mongo", mongo), ("redis", redis), ("qdrant", qdrant)):
        if v is not None:
            _override[k] = v


@lru_cache
def _mongo():
    from pymongo import MongoClient
    s = get_settings()
    return MongoClient(s.mongo_url, serverSelectionTimeoutMS=3000)[s.mongo_db]


@lru_cache
def _redis():
    import redis
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


@lru_cache
def _qdrant():
    from qdrant_client import QdrantClient
    url = get_settings().qdrant_url
    return QdrantClient(path=url.removeprefix("local:")) if url.startswith("local:") else QdrantClient(url=url)


def get_mongo():
    return _override.get("mongo") or _mongo()


def get_redis():
    return _override.get("redis") or _redis()


def get_qdrant():
    return _override.get("qdrant") or _qdrant()
