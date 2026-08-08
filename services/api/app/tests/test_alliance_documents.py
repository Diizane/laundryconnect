"""Milestone 9 Phase 2: bounded document discovery + retrieval.

All fixture/mock — no network, CI-safe. Covers the page parsers (pinned to
the reconstructed sanitised fixtures), the connector's bounded traversal
(never more than two pages), fixture-mode end-to-end discovery, and the
session-mode gates.
"""

from pathlib import Path

import pytest

from app.core.config import Settings
from app.providers.alliance.connector import AllianceConnector
from app.providers.alliance.document_parser import (
    ManualPage,
    parse_literature_page,
    parse_manual_page,
)
from app.providers.errors import DocumentNotFound, ReauthenticationRequired
from app.providers.models import DataOrigin

FIXTURES = Path(__file__).parent.parent / "providers" / "alliance" / "fixtures"


def _fixture_settings(**overrides) -> Settings:
    return Settings(_env_file=None, alliance_mode="fixture", **overrides)


# -- Manual page parsing ------------------------------------------------------


class TestParseManualPage:
    def test_fixture_manual_page(self) -> None:
        page = parse_manual_page((FIXTURES / "manual_page.html").read_bytes())
        # Functional identifiers (ManualId/ModelId) are KEPT — the portal
        # 500s without them (found by live validation). Search echoes
        # (SearchString, SearchAction, Comment, show) are dropped.
        assert page.literature_path == "/en/Model/Literature?ManualId=1001&ModelId=2002"
        assert page.drawings_print_path == "/en/Manual/DrawingsPrint?ManualId=1001&ModelId=2002"
        assert page.direct_pdf_paths == []
        # The fixture carries the observed "not available" message.
        assert page.drawings_available is False

    def test_search_echo_parameters_never_stored(self) -> None:
        page = parse_manual_page((FIXTURES / "manual_page.html").read_bytes())
        for stored in (page.literature_path, page.drawings_print_path):
            assert "SearchString" not in stored
            assert "SearchAction" not in stored
            assert "Comment" not in stored

    def test_literature_link_without_query_keeps_bare_path(self) -> None:
        body = b'<html><body><a href="/en/Model/Literature">Related Literature</a></body></html>'
        assert parse_manual_page(body).literature_path == "/en/Model/Literature"

    def test_direct_pdf_links_captured_and_deduplicated(self) -> None:
        body = b"""
        <html><body>
          <a href="/manuals/Production/D0999.pdf?639206374676915581">PDF</a>
          <a href="/manuals/Production/D0999.pdf?639206374676915581">PDF again</a>
          <a href="/en/Wiring?x=1">Wiring Diagrams</a>
        </body></html>
        """
        page = parse_manual_page(body)
        assert page.direct_pdf_paths == ["/manuals/Production/D0999.pdf"]
        assert page.literature_path is None
        assert page.drawings_available is True

    def test_unrecognised_html_yields_empty_page(self) -> None:
        page = parse_manual_page(b"<html><body><p>nothing here</p></body></html>")
        assert page == ManualPage(drawings_available=True)

    def test_garbage_bytes_do_not_crash(self) -> None:
        assert isinstance(parse_manual_page(b"\x00\xff not html"), ManualPage)


# -- Literature page parsing --------------------------------------------------


class TestParseLiteraturePage:
    def test_fixture_literature_page(self) -> None:
        records = parse_literature_page((FIXTURES / "literature_page.html").read_bytes())
        assert len(records) == 4

        technical = records[0]
        assert technical["part_number"] == "D0100"
        assert technical["document_type"] == "Technical Mnl"
        assert technical["comment"] == "Date 9/99"
        assert technical["languages"] == ["English"]
        # Cache-buster query stripped: the stable path is the identity.
        assert technical["source_path"] == "/manuals/Production/D0100.pdf"
        assert technical["category"] == "Production"
        assert technical["filename"] == "D0100.pdf"
        assert technical["available"] is True
        assert technical["title"] == "D0100 — Technical Mnl"

    def test_multi_language_row_parsed(self) -> None:
        records = parse_literature_page((FIXTURES / "literature_page.html").read_bytes())
        declaration = next(r for r in records if r["document_type"] == "Declaration of Conformity")
        assert declaration["languages"] == ["English", "česky", "Dansk"]
        assert declaration["category"] == "DOC"

    def test_row_without_pdf_is_returned_as_unavailable(self) -> None:
        records = parse_literature_page((FIXTURES / "literature_page.html").read_bytes())
        unavailable = next(r for r in records if r["part_number"] == "D0300")
        assert unavailable["available"] is False
        assert unavailable["source_path"] == ""
        assert unavailable["category"] is None

    def test_no_document_table_yields_empty(self) -> None:
        assert parse_literature_page(b"<html><body><table><tr><td>x</td></tr></table>") == []

    def test_garbage_bytes_do_not_crash(self) -> None:
        assert parse_literature_page(b"\x00\xff not html") == []


# -- Connector: fixture-mode end-to-end discovery -----------------------------


class TestFixtureDiscovery:
    async def test_discover_documents_from_manual_link(self) -> None:
        connector = AllianceConnector(settings=_fixture_settings())
        documents = await connector.discover_documents("1001:2002")
        assert len(documents) == 4
        for doc in documents:
            assert doc.provider_id == "alliance"
            assert doc.data_origin == DataOrigin.FIXTURE  # never labelled live
        titles = {d.title for d in documents}
        assert "D0100 — Technical Mnl" in titles

    async def test_fetch_document_returns_validated_pdf(self) -> None:
        connector = AllianceConnector(settings=_fixture_settings())
        body = await connector.fetch_document("/manuals/Production/D0100.pdf")
        assert body.startswith(b"%PDF-")

    async def test_fetch_document_missing_raises_document_not_found(self) -> None:
        connector = AllianceConnector(settings=_fixture_settings())
        with pytest.raises(DocumentNotFound):
            await connector.fetch_document("/en/Manual?ManualId=1001")  # not a document path

    async def test_discovered_document_is_fetchable(self) -> None:
        # The workflow composes: discover → pick → fetch.
        connector = AllianceConnector(settings=_fixture_settings())
        documents = await connector.discover_documents("1001:2002")
        chosen = next(d for d in documents if d.available)
        body = await connector.fetch_document(chosen.source_path)
        assert body.startswith(b"%PDF-")


# -- Connector: bounded traversal ---------------------------------------------


class RecordingTransport:
    """Counts fetches; proves the traversal bound structurally."""

    def __init__(self, manual_body: bytes, literature_body: bytes) -> None:
        self._manual_body = manual_body
        self._literature_body = literature_body
        self.page_urls: list[str] = []
        self.document_urls: list[str] = []

    async def search_raw(self, query, query_type):  # pragma: no cover - unused
        return []

    async def fetch_page(self, url: str) -> bytes:
        self.page_urls.append(url)
        if "/en/Model/Literature" in url:
            return self._literature_body
        return self._manual_body

    async def fetch_document(self, url: str) -> bytes:  # pragma: no cover - unused
        self.document_urls.append(url)
        return b"%PDF-1.4"


class TestBoundedTraversal:
    async def test_at_most_two_pages_fetched(self) -> None:
        transport = RecordingTransport(
            (FIXTURES / "manual_page.html").read_bytes(),
            (FIXTURES / "literature_page.html").read_bytes(),
        )
        connector = AllianceConnector(settings=_fixture_settings(), transport=transport)
        await connector.discover_documents("1001:2002")
        # Exactly the observed workflow: manual page + literature page.
        assert len(transport.page_urls) == 2
        # Discovery returns metadata only — no document bytes fetched.
        assert transport.document_urls == []

    async def test_single_page_when_no_literature_link(self) -> None:
        transport = RecordingTransport(
            b"<html><body><p>no links at all</p></body></html>",
            b"",
        )
        connector = AllianceConnector(settings=_fixture_settings(), transport=transport)
        documents = await connector.discover_documents("1001:2002")
        assert len(transport.page_urls) == 1
        assert documents == []

    async def test_literature_links_are_not_followed_further(self) -> None:
        # The literature fixture contains links back to /en/Manual and other
        # pages; discovery must never follow them (no recursion).
        transport = RecordingTransport(
            (FIXTURES / "manual_page.html").read_bytes(),
            (FIXTURES / "literature_page.html").read_bytes(),
        )
        connector = AllianceConnector(settings=_fixture_settings(), transport=transport)
        await connector.discover_documents("1001:2002")
        await connector.discover_documents("1001:2002")
        # Two independent calls → exactly two pages each, never more.
        assert len(transport.page_urls) == 4

    async def test_relative_paths_resolve_against_parts_base(self) -> None:
        transport = RecordingTransport(b"<html></html>", b"")
        connector = AllianceConnector(settings=_fixture_settings(), transport=transport)
        await connector.discover_documents("1001:2002")
        assert transport.page_urls[0] == (
            "https://pc.alliancels.net/en/Manual?ManualId=1001&ModelId=2002"
        )


class TestReferenceValidation:
    """Client-originating references are validated BEFORE any request."""

    @pytest.mark.parametrize(
        "reference",
        [
            "",
            "1001",
            "1001:2002:3",
            "/en/Manual?ManualId=1001&ModelId=2002",  # paths are refused
            "https://evil.example/x",  # URLs are refused
            "1001:2002x",
            "abc:def",
            "1" * 13 + ":2002",  # over-length ids refused
        ],
    )
    async def test_invalid_reference_rejected_without_any_fetch(self, reference: str) -> None:
        from app.providers.errors import InvalidDocumentReference

        transport = RecordingTransport(b"", b"")
        connector = AllianceConnector(settings=_fixture_settings(), transport=transport)
        with pytest.raises(InvalidDocumentReference):
            await connector.discover_documents(reference)
        assert transport.page_urls == []  # nothing was fetched

    @pytest.mark.parametrize(
        "path",
        [
            "",
            "/en/Manual?ManualId=1001",
            "/manuals/Production/../../etc/passwd",
            "/manuals/Production/D0100.exe",
            "https://pc.alliancels.net/manuals/Production/D0100.pdf",  # absolute refused
            "/other/Production/D0100.pdf",
        ],
    )
    async def test_invalid_document_path_fails_closed_without_any_fetch(self, path: str) -> None:
        transport = RecordingTransport(b"", b"")
        connector = AllianceConnector(settings=_fixture_settings(), transport=transport)
        with pytest.raises(DocumentNotFound):
            await connector.fetch_document(path)
        assert transport.document_urls == []  # nothing was fetched


# -- Connector: session-mode gates (pure local, no network) -------------------


class TestSessionModeGates:
    async def test_missing_session_raises_reauthentication_required(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        connector = AllianceConnector(
            settings=Settings(_env_file=None, alliance_mode="session", alliance_session_path=None)
        )
        with pytest.raises(ReauthenticationRequired):
            await connector.discover_documents("1001:2002")
        with pytest.raises(ReauthenticationRequired):
            await connector.fetch_document("/manuals/Production/D0100.pdf")

    async def test_credential_mode_refused(self) -> None:
        from app.providers.errors import LiveModeRefused

        connector = AllianceConnector(settings=Settings(_env_file=None, alliance_mode="credential"))
        with pytest.raises(LiveModeRefused):
            await connector.discover_documents("1001:2002")


class TestDrawingParsing:
    """Assembly drawings (Milestone 15)."""

    def test_nested_layout_row_does_not_become_a_drawing(self) -> None:
        # Production nests the drawing table inside a layout table; the
        # wrapper row's text is every drawing name concatenated, which
        # produced a bogus first entry titled with the whole list.
        def row(drawing_id: str, name: str) -> bytes:
            return (
                b'<tr><td><a href="/en/Manual/Drawing?DrawingId='
                + drawing_id.encode()
                + b'&ManualId=2&ModelId=3">Click to view drawing.</a></td><td>'
                + name.encode()
                + b"</td></tr>"
            )

        html = (
            b"<html><body><table><tr><td><table>"
            + row("1", "Serial Label")
            + row("2", "Drive")
            + b"</table></td></tr></table></body></html>"
        )
        drawings = parse_manual_page(html).drawings
        assert [(d.drawing_id, d.title) for d in drawings] == [
            ("1", "Serial Label"),
            ("2", "Drive"),
        ]

    def test_drawing_paths_keep_only_catalog_identifiers(self) -> None:
        html = (
            b'<html><body><table><tr><td><a href="/en/Manual/Drawing?Index=57&DrawingId=548226'
            b'&ManualId=16774&ModelId=430362&SearchString=135RX009281WK&SearchAction=BySerial">'
            b"Click to view drawing.</a></td><td>Drive</td></tr></table></body></html>"
        )
        path = parse_manual_page(html).drawings[0].source_path
        # Search echoes must not be carried into a stored path.
        assert "SearchString" not in path and "SearchAction" not in path
        assert "DrawingId=548226" in path and "ManualId=16774" in path

    def test_diagram_is_the_inch_sized_svg_not_the_zoom_icons(self) -> None:
        from app.providers.alliance.document_parser import parse_drawing_page

        html = (
            b'<html><body><svg class="zoom-button-svg" width="24" height="24">'
            b'<path d="M1 1"/></svg>'
            b'<svg xmlns="http://www.w3.org/2000/svg" width="7.74in" height="9.71in">'
            b'<g id="callouts"><line x1="1" y1="2" x2="3" y2="4"/></g></svg>'
            b"<table><tr><td>8</td><td>SP533157</td><td>Belt</td><td></td></tr></table></body></html>"
        )
        drawing = parse_drawing_page(html)
        assert drawing.has_diagram
        assert "zoom-button" not in drawing.svg
        assert [(p.reference, p.part_number, p.description) for p in drawing.parts] == [
            ("8", "SP533157", "Belt")
        ]

    def test_missing_diagram_yields_empty_not_an_error(self) -> None:
        from app.providers.alliance.document_parser import parse_drawing_page

        drawing = parse_drawing_page(b"<html><body><p>nothing here</p></body></html>")
        assert drawing.has_diagram is False
        assert drawing.parts == []
