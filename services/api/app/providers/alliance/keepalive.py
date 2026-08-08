"""Session keepalive and lifetime measurement (Milestone 11).

The operator-bootstrapped Alliance session expires and must be re-created
by hand, which is disruptive in the field. Portal sessions commonly expire
through *inactivity* rather than absolute age; if that is true here, a
periodic lightweight request against an already-authorised page keeps the
session usable indefinitely.

This deliberately does NOT touch credentials and does NOT log in: it only
keeps an existing, human-authorised session from going idle, and records
how long sessions actually live so the idle-vs-absolute question can be
answered from evidence rather than assumption.

Design constraints, consistent with the rest of the connector:
- OFF by default; explicit per-environment opt-in.
- One request per interval to ONE fixed URL — no crawling, no discovery.
- Runs only when the live gate passes (session mode, access approved, not
  CI, kill switch off); it re-checks on every tick, so flipping the kill
  switch stops it.
- Failures never affect request handling: the loop logs and continues (or
  stops on reauth, where continuing is pointless until a human acts).
- Logs carry structural facts only — never cookies, URLs with queries, or
  response bodies.
"""

import asyncio
import logging
import time

from app.core.config import Settings
from app.providers.alliance.config import AllianceMode, require_live_allowed, resolve_mode
from app.providers.alliance.session import load_session
from app.providers.errors import ProviderError, ReauthenticationRequired

logger = logging.getLogger(__name__)


class SessionKeepalive:
    """Periodically exercises an authorised session and records its lifetime.

    `connector_factory` is injected so tests can supply a fake transport;
    production passes the real Alliance connector.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        fetch_page,
        sleep=asyncio.sleep,
        now=time.time,
    ) -> None:
        self._settings = settings
        self._fetch_page = fetch_page
        self._sleep = sleep
        self._now = now
        self._task: asyncio.Task | None = None
        # Observation state (also useful for diagnostics/tests).
        self.started_at: float | None = None
        self.last_success_at: float | None = None
        self.consecutive_failures = 0
        self.ticks = 0
        self.reauth_detected_at: float | None = None

    @property
    def session_age_seconds(self) -> float | None:
        if self.started_at is None:
            return None
        return self._now() - self.started_at

    def should_run(self) -> bool:
        """Whether keepalive is permitted right now. Re-evaluated each tick
        so the kill switch and mode changes take effect without a restart."""
        if not self._settings.alliance_keepalive_enabled:
            return False
        if resolve_mode(self._settings) is not AllianceMode.SESSION:
            return False
        try:
            require_live_allowed(self._settings)
        except Exception:
            return False
        return True

    def start(self) -> None:
        if self._task is not None or not self.should_run():
            if not self.should_run():
                logger.info("alliance keepalive disabled")
            return
        self.started_at = self._now()
        self._task = asyncio.create_task(self._run(), name="alliance-keepalive")
        logger.info(
            "alliance keepalive started",
            extra={"interval_seconds": self._settings.alliance_keepalive_interval_seconds},
        )

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass  # expected: we just cancelled it
        except Exception as exc:  # shutdown must never raise
            logger.warning(
                "alliance keepalive stopped with an error", extra={"error": type(exc).__name__}
            )

    async def _run(self) -> None:
        interval = max(60, self._settings.alliance_keepalive_interval_seconds)
        while True:
            await self._sleep(interval)
            if not self.should_run():
                logger.info("alliance keepalive stopping (no longer permitted)")
                return
            if not await self.tick():
                return

    async def tick(self) -> bool:
        """One keepalive request. Returns False when the loop should stop
        (the session needs a human — continuing would just repeat)."""
        self.ticks += 1
        age = self.session_age_seconds
        age_hours = round(age / 3600, 2) if age is not None else None
        try:
            # Validate locally first: a missing/expired-by-cookie session
            # needs no request to diagnose.
            load_session(self._settings.alliance_session_path)
            await self._fetch_page(self._settings.alliance_keepalive_url)
        except ReauthenticationRequired:
            self.reauth_detected_at = self._now()
            # THE measurement that matters: how long the session survived
            # while being kept warm.
            logger.warning(
                "alliance session expired despite keepalive",
                extra={
                    "session_age_hours": age_hours,
                    "keepalive_ticks": self.ticks,
                    "outcome": "reauthentication_required",
                },
            )
            return False
        except ProviderError as exc:
            self.consecutive_failures += 1
            logger.warning(
                "alliance keepalive request failed",
                extra={
                    "error": type(exc).__name__,
                    "consecutive_failures": self.consecutive_failures,
                    "session_age_hours": age_hours,
                },
            )
            return True  # transient: keep trying
        except Exception as exc:
            self.consecutive_failures += 1
            logger.warning(
                "alliance keepalive errored",
                extra={"error": type(exc).__name__},
            )
            return True

        self.consecutive_failures = 0
        self.last_success_at = self._now()
        logger.info(
            "alliance session kept alive",
            extra={"session_age_hours": age_hours, "keepalive_ticks": self.ticks},
        )
        return True
