"""Document cache + cache-aware fetching (Milestone 12) — offline."""

from pathlib import Path

import pytest

from app.documents.cache import DocumentCache
from app.documents.fetcher import CachingDocumentFetcher
from app.providers.alliance.transport import NotModified
from app.providers.errors import (
    DocumentNotFound,
    InvalidDocumentContent,
    ProviderError,
    ReauthenticationRequired,
)

PDF = b"%PDF-1.6 body bytes"
NEWER = b"%PDF-1.6 revised bytes"
PATH = "/manuals/Production/D0568.pdf"


class _Clock:
    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class _FakeConnector:
    """Stands in for a provider connector; records conditional headers."""

    def __init__(self, *, body=PDF, raises=None, validators=None) -> None:
        self.body = body
        self.raises = raises
        self.last_document_validators = validators or {}
        self.calls: list[dict | None] = []

    async def fetch_document(self, source_path, *, conditional=None):
        self.calls.append(conditional)
        if self.raises is not None:
            raise self.raises
        return self.body


def _cache(tmp_path: Path, clock, max_bytes: int = 10_000_000) -> DocumentCache:
    return DocumentCache(tmp_path / "cache", max_bytes=max_bytes, now=clock)


def _fetcher(cache, clock, max_stale_seconds: int = 90 * 24 * 3600):
    return CachingDocumentFetcher(cache, max_stale_seconds=max_stale_seconds, now=clock)


class TestCacheStore:
    def test_round_trip(self, tmp_path: Path) -> None:
        clock = _Clock()
        cache = _cache(tmp_path, clock)
        key = DocumentCache.key("alliance", PATH)
        cache.put(key, PDF, etag='"abc"', last_modified="Tue, 26 Jan 2021 16:59:10 GMT")

        entry = cache.get(key)
        assert entry is not None
        assert entry.body == PDF
        assert entry.etag == '"abc"'
        assert entry.age_seconds(clock.t) == 0

    def test_miss_returns_none(self, tmp_path: Path) -> None:
        assert _cache(tmp_path, _Clock()).get(DocumentCache.key("alliance", PATH)) is None

    def test_keys_are_provider_scoped(self, tmp_path: Path) -> None:
        # The same path from a different provider is a different document.
        assert DocumentCache.key("alliance", PATH) != DocumentCache.key("mock", PATH)

    def test_key_does_not_expose_the_path(self, tmp_path: Path) -> None:
        key = DocumentCache.key("alliance", PATH)
        assert "manuals" not in key and "D0568" not in key

    def test_stored_files_are_owner_only(self, tmp_path: Path) -> None:
        clock = _Clock()
        cache = _cache(tmp_path, clock)
        cache.put(DocumentCache.key("alliance", PATH), PDF)
        for path in (tmp_path / "cache").rglob("*"):
            if path.is_file():
                assert oct(path.stat().st_mode)[-3:] == "600"

    def test_age_tracks_last_revalidation(self, tmp_path: Path) -> None:
        clock = _Clock()
        cache = _cache(tmp_path, clock)
        key = DocumentCache.key("alliance", PATH)
        cache.put(key, PDF)
        clock.t += 3600
        assert cache.get(key).age_seconds(clock.t) == 3600
        cache.mark_revalidated(key)
        assert cache.get(key).age_seconds(clock.t) == 0

    def test_eviction_respects_the_size_cap(self, tmp_path: Path) -> None:
        clock = _Clock()
        cache = _cache(tmp_path, clock, max_bytes=2_000)
        for i in range(5):
            cache.put(DocumentCache.key("alliance", f"/manuals/X/{i}.pdf"), b"x" * 900)
        assert cache.total_bytes() <= 2_000


class TestRevalidation:
    async def test_first_fetch_stores_and_reports_live(self, tmp_path: Path) -> None:
        clock = _Clock()
        cache = _cache(tmp_path, clock)
        connector = _FakeConnector(validators={"etag": '"v1"', "last_modified": "Mon, 01 Jan 2024"})

        result = await _fetcher(cache, clock).fetch(connector, "alliance", PATH)

        assert result.body == PDF and result.origin == "live"
        assert connector.calls == [None]  # nothing cached yet, so no validators
        assert cache.get(DocumentCache.key("alliance", PATH)).etag == '"v1"'

    async def test_second_fetch_sends_validators_and_serves_cache_on_304(
        self, tmp_path: Path
    ) -> None:
        clock = _Clock()
        cache = _cache(tmp_path, clock)
        cache.put(DocumentCache.key("alliance", PATH), PDF, etag='"v1"', last_modified="Mon, 01")
        connector = _FakeConnector(raises=NotModified("unchanged"))

        clock.t += 7200
        result = await _fetcher(cache, clock).fetch(connector, "alliance", PATH)

        assert connector.calls == [{"If-None-Match": '"v1"', "If-Modified-Since": "Mon, 01"}]
        assert result.body == PDF
        assert result.origin == "cached"
        # Revalidated just now, so it is not stale.
        assert result.age_seconds == 0

    async def test_provider_revision_replaces_the_copy(self, tmp_path: Path) -> None:
        clock = _Clock()
        cache = _cache(tmp_path, clock)
        key = DocumentCache.key("alliance", PATH)
        cache.put(key, PDF, etag='"v1"')
        connector = _FakeConnector(body=NEWER, validators={"etag": '"v2"'})

        result = await _fetcher(cache, clock).fetch(connector, "alliance", PATH)

        # A revised manual must win over the stored one — this is the
        # safety-critical case.
        assert result.body == NEWER and result.origin == "live"
        assert cache.get(key).body == NEWER
        assert cache.get(key).etag == '"v2"'


class TestFallbackWhenProviderUnavailable:
    async def test_expired_session_serves_cached_copy_labelled(self, tmp_path: Path) -> None:
        clock = _Clock()
        cache = _cache(tmp_path, clock)
        cache.put(DocumentCache.key("alliance", PATH), PDF, etag='"v1"')
        connector = _FakeConnector(raises=ReauthenticationRequired("session gone"))

        clock.t += 4 * 3600
        result = await _fetcher(cache, clock).fetch(connector, "alliance", PATH)

        # The whole point: the technician still gets the manual.
        assert result.body == PDF
        assert result.origin == "cached"
        assert result.age_seconds == 4 * 3600

    async def test_provider_outage_serves_cached_copy(self, tmp_path: Path) -> None:
        clock = _Clock()
        cache = _cache(tmp_path, clock)
        cache.put(DocumentCache.key("alliance", PATH), PDF)
        connector = _FakeConnector(raises=ProviderError("timeout"))

        result = await _fetcher(cache, clock).fetch(connector, "alliance", PATH)
        assert result.origin == "cached"

    async def test_no_cached_copy_propagates_the_error(self, tmp_path: Path) -> None:
        clock = _Clock()
        connector = _FakeConnector(raises=ReauthenticationRequired("session gone"))
        with pytest.raises(ReauthenticationRequired):
            await _fetcher(_cache(tmp_path, clock), clock).fetch(connector, "alliance", PATH)

    async def test_copy_older_than_the_limit_is_refused(self, tmp_path: Path) -> None:
        clock = _Clock()
        cache = _cache(tmp_path, clock)
        cache.put(DocumentCache.key("alliance", PATH), PDF)
        connector = _FakeConnector(raises=ReauthenticationRequired("session gone"))

        clock.t += 91 * 24 * 3600  # past the 90-day limit
        # Never silently serve a manual we have not been able to confirm
        # for months.
        with pytest.raises(ReauthenticationRequired):
            await _fetcher(cache, clock).fetch(connector, "alliance", PATH)

    @pytest.mark.parametrize(
        "error",
        [
            DocumentNotFound("gone"),
            InvalidDocumentContent("not a pdf"),
        ],
    )
    async def test_definitive_provider_answers_are_never_masked(
        self, tmp_path: Path, error: Exception
    ) -> None:
        clock = _Clock()
        cache = _cache(tmp_path, clock)
        cache.put(DocumentCache.key("alliance", PATH), PDF)
        connector = _FakeConnector(raises=error)

        # "This document is gone / is not a PDF" must reach the caller
        # rather than being papered over with an old copy.
        with pytest.raises(type(error)):
            await _fetcher(cache, clock).fetch(connector, "alliance", PATH)


class TestCacheFailuresNeverBreakServing:
    """An unwritable or unreadable cache is an operational problem, never a
    reason to fail the document a technician asked for. (A root-owned Docker
    volume caused exactly this in deployment: HTTP 500 instead of the PDF.)"""

    async def test_unwritable_cache_still_serves_the_document(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clock = _Clock()
        cache = _cache(tmp_path, clock)

        def boom(*args, **kwargs):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(cache, "put", boom)
        result = await _fetcher(cache, clock).fetch(_FakeConnector(), "alliance", PATH)
        assert result.body == PDF and result.origin == "live"

    async def test_unreadable_cache_falls_back_to_a_plain_fetch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clock = _Clock()
        cache = _cache(tmp_path, clock)

        def boom(*args, **kwargs):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(cache, "get", boom)
        connector = _FakeConnector()
        result = await _fetcher(cache, clock).fetch(connector, "alliance", PATH)
        assert result.body == PDF
        assert connector.calls == [None]  # no validators, since nothing was read

    async def test_unexpected_304_without_a_cached_copy_is_not_swallowed(
        self, tmp_path: Path
    ) -> None:
        clock = _Clock()
        connector = _FakeConnector(raises=NotModified("304 with no validators sent"))
        with pytest.raises(NotModified):
            await _fetcher(_cache(tmp_path, clock), clock).fetch(connector, "alliance", PATH)


class TestCacheDisabled:
    async def test_pass_through_when_no_cache(self, tmp_path: Path) -> None:
        clock = _Clock()
        connector = _FakeConnector()
        result = await CachingDocumentFetcher(None, max_stale_seconds=1, now=clock).fetch(
            connector, "alliance", PATH
        )
        assert result.body == PDF and result.origin == "live"
        assert connector.calls == [None]  # no conditional headers at all
