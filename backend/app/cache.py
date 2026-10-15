"""Small thread-safe in-process TTL cache for season-wide read endpoints."""

import time
from collections import OrderedDict
from collections.abc import Callable
from threading import Lock
from typing import Any

MAX_ENTRIES = 256

_lock = Lock()
_entries: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()


def cached[T](key: tuple, ttl_seconds: float, compute: Callable[[], T]) -> T:
    now = time.monotonic()
    with _lock:
        hit = _entries.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
    value = compute()
    with _lock:
        _entries.pop(key, None)
        _entries[key] = (time.monotonic() + ttl_seconds, value)
        while len(_entries) > MAX_ENTRIES:
            _entries.popitem(last=False)
    return value


def clear() -> None:
    with _lock:
        _entries.clear()
