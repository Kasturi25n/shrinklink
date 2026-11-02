"""Cache abstraction used for (a) hot short-link lookups and (b) rate-limit counters.

Two backends share one interface: Redis for production (shared across workers),
and an in-process dict for local dev and tests.
"""
import threading
import time
from functools import lru_cache
from typing import Dict, Optional, Protocol, Tuple

import redis

from app.config import get_settings


class Cache(Protocol):
    def get(self, key: str) -> Optional[str]: ...
    def set(self, key: str, value: str, ttl: int) -> None: ...
    def delete(self, key: str) -> None: ...
    def incr(self, key: str, ttl: int) -> int: ...
    def clear(self) -> None: ...


class InMemoryCache:
    def __init__(self) -> None:
        self._data: Dict[str, Tuple[str, float]] = {}
        self._lock = threading.Lock()

    def _alive(self, key: str) -> Optional[str]:
        item = self._data.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at <= time.monotonic():
            del self._data[key]
            return None
        return value

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            return self._alive(key)

    def set(self, key: str, value: str, ttl: int) -> None:
        with self._lock:
            self._data[key] = (value, time.monotonic() + ttl)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def incr(self, key: str, ttl: int) -> int:
        """Increment a counter; the window starts at the first increment."""
        with self._lock:
            current = self._alive(key)
            if current is None:
                self._data[key] = ("1", time.monotonic() + ttl)
                return 1
            new = int(current) + 1
            self._data[key] = (str(new), self._data[key][1])
            return new

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class RedisCache:
    def __init__(self, url: str) -> None:
        self._r = redis.Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> Optional[str]:
        return self._r.get(key)

    def set(self, key: str, value: str, ttl: int) -> None:
        self._r.set(key, value, ex=ttl)

    def delete(self, key: str) -> None:
        self._r.delete(key)

    def incr(self, key: str, ttl: int) -> int:
        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl, nx=True)  # only set TTL on the first hit of the window
        count, _ = pipe.execute()
        return int(count)

    def clear(self) -> None:
        self._r.flushdb()


@lru_cache
def get_cache() -> Cache:
    url = get_settings().redis_url
    return RedisCache(url) if url else InMemoryCache()
