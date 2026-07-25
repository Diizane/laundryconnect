"""RateLimiter: minimum-interval spacing with injected clock/sleep."""

from app.providers.alliance.ratelimit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds  # advancing time as if we waited


async def test_first_acquire_does_not_sleep() -> None:
    fake = FakeClock()
    limiter = RateLimiter(60, clock=fake.clock, sleep=fake.sleep)  # 1/sec
    await limiter.acquire()
    assert fake.slept == []


async def test_second_immediate_acquire_waits_the_interval() -> None:
    fake = FakeClock()
    limiter = RateLimiter(60, clock=fake.clock, sleep=fake.sleep)  # min interval 1s
    await limiter.acquire()
    await limiter.acquire()  # no time passed → must wait ~1s
    assert fake.slept == [1.0]


async def test_no_wait_when_interval_already_elapsed() -> None:
    fake = FakeClock()
    limiter = RateLimiter(60, clock=fake.clock, sleep=fake.sleep)
    await limiter.acquire()
    fake.now += 5.0  # plenty of time passes
    await limiter.acquire()
    assert fake.slept == []


async def test_zero_rate_disables_limiting() -> None:
    fake = FakeClock()
    limiter = RateLimiter(0, clock=fake.clock, sleep=fake.sleep)
    await limiter.acquire()
    await limiter.acquire()
    assert fake.slept == []


def test_conservative_default_interval() -> None:
    # 12/min → one request per 5 seconds.
    limiter = RateLimiter(12)
    assert limiter._min_interval == 5.0
