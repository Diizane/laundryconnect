"""Session keepalive (Milestone 11) — offline, no network, no credentials."""

import json
import logging
from pathlib import Path

import pytest

from app.core.config import Settings
from app.providers.alliance.keepalive import SessionKeepalive
from app.providers.alliance.transport import LiveFetchError
from app.providers.errors import ReauthenticationRequired


def _session_file(tmp_path: Path, *, expires: float = 4_102_444_800.0) -> str:
    path = tmp_path / "session.json"
    path.write_text(
        json.dumps({"cookies": [{"name": "s", "value": "x", "expires": expires}], "origins": []})
    )
    return str(path)


def _settings(tmp_path: Path, **overrides) -> Settings:
    base = {
        "alliance_mode": "session",
        "alliance_access_approved": True,
        "alliance_keepalive_enabled": True,
        "alliance_session_path": _session_file(tmp_path),
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


class _Clock:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


class TestGating:
    def test_disabled_by_default(self, tmp_path: Path) -> None:
        settings = Settings(_env_file=None)
        keepalive = SessionKeepalive(settings, fetch_page=None)
        assert keepalive.should_run() is False

    def test_requires_session_mode(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        settings = _settings(tmp_path, alliance_mode="fixture")
        assert SessionKeepalive(settings, fetch_page=None).should_run() is False

    def test_requires_access_approved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        settings = _settings(tmp_path, alliance_access_approved=False)
        assert SessionKeepalive(settings, fetch_page=None).should_run() is False

    def test_kill_switch_stops_it(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        settings = _settings(tmp_path, alliance_live_kill_switch=True)
        assert SessionKeepalive(settings, fetch_page=None).should_run() is False

    def test_enabled_when_all_gates_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        assert SessionKeepalive(_settings(tmp_path), fetch_page=None).should_run() is True

    async def test_start_is_a_noop_when_not_permitted(self, tmp_path: Path) -> None:
        keepalive = SessionKeepalive(Settings(_env_file=None), fetch_page=None)
        keepalive.start()
        await keepalive.stop()  # must not raise
        assert keepalive.ticks == 0


class TestTick:
    async def test_successful_tick_hits_the_configured_url_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        calls: list[str] = []

        async def fetch(url: str) -> bytes:
            calls.append(url)
            return b"<html>ok</html>"

        settings = _settings(tmp_path)
        keepalive = SessionKeepalive(settings, fetch_page=fetch, now=_Clock())
        assert await keepalive.tick() is True
        # Exactly one request, to exactly the configured page: not a crawl.
        assert calls == [settings.alliance_keepalive_url]
        assert keepalive.consecutive_failures == 0

    async def test_reauth_stops_the_loop_and_records_lifetime(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delenv("CI", raising=False)

        async def fetch(url: str) -> bytes:
            raise ReauthenticationRequired("session gone")

        clock = _Clock()
        keepalive = SessionKeepalive(_settings(tmp_path), fetch_page=fetch, now=clock)
        keepalive.started_at = clock.t
        clock.t += 6 * 3600  # session lived six hours

        with caplog.at_level(logging.WARNING):
            assert await keepalive.tick() is False

        assert keepalive.reauth_detected_at is not None
        # The measurement we are running this for.
        record = next(r for r in caplog.records if "expired despite keepalive" in r.message)
        assert record.session_age_hours == 6.0

    async def test_transient_failure_keeps_the_loop_running(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)

        async def fetch(url: str) -> bytes:
            raise LiveFetchError("provider returned status 503")

        keepalive = SessionKeepalive(_settings(tmp_path), fetch_page=fetch, now=_Clock())
        assert await keepalive.tick() is True
        assert await keepalive.tick() is True
        assert keepalive.consecutive_failures == 2

    async def test_unexpected_error_does_not_crash_the_loop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)

        async def fetch(url: str) -> bytes:
            raise RuntimeError("something odd")

        keepalive = SessionKeepalive(_settings(tmp_path), fetch_page=fetch, now=_Clock())
        assert await keepalive.tick() is True

    async def test_tick_never_logs_session_material(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delenv("CI", raising=False)

        async def fetch(url: str) -> bytes:
            return b"<html>secret body</html>"

        with caplog.at_level(logging.DEBUG):
            await SessionKeepalive(_settings(tmp_path), fetch_page=fetch, now=_Clock()).tick()
        assert "secret body" not in caplog.text
        assert "cookie" not in caplog.text.lower()


class TestLoop:
    async def test_loop_sleeps_then_ticks_and_stops_on_reauth(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        slept: list[float] = []
        attempts = {"n": 0}

        async def sleep(seconds: float) -> None:
            slept.append(seconds)

        async def fetch(url: str) -> bytes:
            attempts["n"] += 1
            if attempts["n"] >= 3:
                raise ReauthenticationRequired("expired")
            return b"ok"

        settings = _settings(tmp_path, alliance_keepalive_interval_seconds=900)
        keepalive = SessionKeepalive(settings, fetch_page=fetch, sleep=sleep, now=_Clock())
        keepalive.started_at = 1_000_000.0
        await keepalive._run()  # returns when reauth is detected

        assert attempts["n"] == 3
        assert slept == [900, 900, 900]  # interval honoured between ticks

    async def test_interval_is_floored_to_avoid_hammering(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        slept: list[float] = []

        async def sleep(seconds: float) -> None:
            slept.append(seconds)
            raise StopAsyncIteration  # break out after the first sleep

        settings = _settings(tmp_path, alliance_keepalive_interval_seconds=1)
        keepalive = SessionKeepalive(settings, fetch_page=None, sleep=sleep, now=_Clock())
        with pytest.raises(StopAsyncIteration):
            await keepalive._run()
        assert slept == [60]  # never faster than once a minute
