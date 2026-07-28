"""Small async primitives used by the local bridge.

The native AIM service is session-oriented.  A per-session lock prevents two
replies from overtaking one another, while the ledger makes retries of the
same request idempotent after a reconnect.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict, Hashable, Optional


class ResultLedger:
    """Bounded, TTL-based request/result cache."""

    def __init__(self, max_entries: int = 2048, ttl_seconds: float = 900.0):
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self._items: "OrderedDict[str, tuple[float, Dict[str, Any]]]" = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            self._purge()
            item = self._items.get(key)
            if item is None:
                return None
            self._items.move_to_end(key)
            return dict(item[1])

    async def put(self, key: str, value: Dict[str, Any]) -> None:
        async with self._lock:
            self._purge()
            self._items[key] = (time.monotonic(), dict(value))
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def _purge(self) -> None:
        cutoff = time.monotonic() - self.ttl_seconds
        stale = [key for key, (created, _) in self._items.items() if created < cutoff]
        for key in stale:
            self._items.pop(key, None)


class SessionSerialiser:
    """Run one coroutine at a time for each session key."""

    def __init__(self):
        self._locks: Dict[Hashable, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def _lock_for(self, key: Hashable) -> asyncio.Lock:
        async with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    async def run(
        self,
        key: Hashable,
        operation: Callable[[], Awaitable[Any]],
    ) -> Any:
        lock = await self._lock_for(key)
        async with lock:
            return await operation()

    async def active_keys(self) -> int:
        async with self._guard:
            return sum(1 for lock in self._locks.values() if lock.locked())
