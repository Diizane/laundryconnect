"""Conservative client-side rate limiting (safeguard 7).

A minimal async limiter enforcing a minimum interval between requests. The
clock and sleep are injectable so the behaviour is unit-tested without real
waiting.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable


class RateLimiter:
    def __init__(
        self,
        per_minute: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._min_interval = 60.0 / per_minute if per_minute > 0 else 0.0
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until the next request is allowed under the rate limit."""
        async with self._lock:
            if self._last is not None and self._min_interval > 0:
                elapsed = self._clock() - self._last
                wait = self._min_interval - elapsed
                if wait > 0:
                    await self._sleep(wait)
            self._last = self._clock()
