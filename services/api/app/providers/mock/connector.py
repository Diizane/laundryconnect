"""Mock provider connector.

Serves a small fixed dataset of SAMPLE data for local development and
automated tests. Every result is labelled `data_origin=mock` and the provider
presents itself as "Mock Provider (sample data)" — this data must never be
mistaken for real provider content.

The constructor accepts fault-injection parameters (`latency_seconds`,
`fail_with`) so registry timeout and partial-failure behaviour can be tested
deterministically.
"""

import asyncio
import re
from datetime import date
from typing import ClassVar

from app.providers.base import ProviderConnector
from app.providers.errors import DocumentNotFound, InvalidDocumentReference
from app.providers.models import (
    DataOrigin,
    ProviderDocumentInfo,
    ProviderHealth,
    ProviderResult,
    QueryType,
    ResultType,
)

# Fields searched per query type; AUTO and KEYWORD search everything.
_FIELDS_BY_QUERY_TYPE: dict[QueryType, tuple[str, ...]] = {
    QueryType.MODEL: ("model",),
    QueryType.SERIAL: ("serial_range",),
    QueryType.PART: ("part_number",),
    QueryType.FAULT_CODE: ("title", "description"),
}


def _sample_results() -> list[ProviderResult]:
    """Fixed sample dataset: two machines, documents, a part, a fault code."""
    common = {"provider_id": MockProviderConnector.provider_id, "data_origin": DataOrigin.MOCK}
    return [
        ProviderResult(
            **common,
            source_reference="mock-doc-sc60-service",
            result_type=ResultType.DOCUMENT,
            title="SC60 Washer-Extractor Service Manual (sample)",
            description="Sample service manual covering maintenance and repair procedures.",
            manufacturer="Alliance Laundry Systems",
            brand="Speed Queen",
            model="SC60",
            document_type="service_manual",
            revision="Rev 4",
            published_at=date(2023, 5, 1),
            access_method="internal",
            relevance_score=0.9,
        ),
        ProviderResult(
            **common,
            source_reference="mock-doc-sc60-parts",
            result_type=ResultType.DOCUMENT,
            title="SC60 Parts Manual (sample)",
            description="Sample parts manual with exploded diagrams.",
            manufacturer="Alliance Laundry Systems",
            brand="Speed Queen",
            model="SC60",
            document_type="parts_manual",
            revision="Rev 2",
            published_at=date(2022, 11, 15),
            access_method="internal",
            relevance_score=0.8,
        ),
        ProviderResult(
            **common,
            source_reference="mock-part-f8524501",
            result_type=ResultType.PART,
            title="Door lock assembly (sample part)",
            description="Sample part record for the SC60 door lock assembly.",
            manufacturer="Alliance Laundry Systems",
            brand="Speed Queen",
            model="SC60",
            part_number="F8524501",
            access_method="internal",
            relevance_score=0.7,
        ),
        ProviderResult(
            **common,
            source_reference="mock-fault-sc60-edl",
            result_type=ResultType.FAULT_CODE,
            title="Fault code EdL — door lock error (sample)",
            description="Sample diagnostic entry: EdL indicates a door lock fault on SC60.",
            manufacturer="Alliance Laundry Systems",
            brand="Speed Queen",
            model="SC60",
            document_type="diagnostics",
            access_method="internal",
            relevance_score=0.75,
        ),
        ProviderResult(
            **common,
            source_reference="mock-doc-hs6008-install",
            result_type=ResultType.DOCUMENT,
            title="HS-6008 Installation Manual (sample)",
            description="Sample installation manual including utility requirements.",
            manufacturer="Girbau",
            brand="Girbau",
            model="HS-6008",
            serial_range="2100000-2199999",
            document_type="installation_manual",
            revision="Rev 1",
            published_at=date(2021, 3, 10),
            access_method="internal",
            relevance_score=0.85,
        ),
    ]


# Sample document workflow data (Milestone 9). Labelled sample throughout;
# one entry is deliberately unavailable so clients handle that case.
_DOCUMENT_REF = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_MOCK_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
    b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
    b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj\n"
    b"trailer << /Size 4 /Root 1 0 R >>\n"
    b"%%EOF\n"
)


def _sample_documents() -> list[ProviderDocumentInfo]:
    common = {"provider_id": MockProviderConnector.provider_id, "data_origin": DataOrigin.MOCK}
    return [
        ProviderDocumentInfo(
            **common,
            title="MOCK-SC60-SVC — Service Manual (sample)",
            document_type="Service Manual",
            part_number="MOCK-SC60-SVC",
            comment="Rev 4",
            languages=["English"],
            category="Sample",
            filename="sc60-service.pdf",
            source_path="/mock/documents/sc60-service.pdf",
            available=True,
        ),
        ProviderDocumentInfo(
            **common,
            title="MOCK-SC60-PRT — Parts Manual (sample)",
            document_type="Parts Manual",
            part_number="MOCK-SC60-PRT",
            comment="Rev 2",
            languages=["English", "Español"],
            category="Sample",
            filename="sc60-parts.pdf",
            source_path="/mock/documents/sc60-parts.pdf",
            available=True,
        ),
        ProviderDocumentInfo(
            **common,
            title="MOCK-SC60-LEG — Legacy Bulletin (sample, no download)",
            document_type="Bulletin",
            part_number="MOCK-SC60-LEG",
            comment="Printed only",
            languages=["English"],
            category=None,
            filename=None,
            source_path="",
            available=False,
        ),
    ]


class MockProviderConnector(ProviderConnector):
    provider_id: ClassVar[str] = "mock"
    display_name: ClassVar[str] = "Mock Provider (sample data)"
    data_origin: ClassVar[DataOrigin] = DataOrigin.MOCK

    def __init__(self, latency_seconds: float = 0.0, fail_with: Exception | None = None) -> None:
        self._latency_seconds = latency_seconds
        self._fail_with = fail_with
        self._results = _sample_results()

    async def search(self, query: str, query_type: QueryType) -> list[ProviderResult]:
        if self._latency_seconds:
            await asyncio.sleep(self._latency_seconds)
        if self._fail_with is not None:
            raise self._fail_with

        needle = query.strip().lower()
        if not needle:
            return []

        fields = _FIELDS_BY_QUERY_TYPE.get(query_type)
        matches = []
        for result in self._results:
            haystacks = (
                [getattr(result, field) for field in fields]
                if fields
                else [
                    result.title,
                    result.description,
                    result.model,
                    result.part_number,
                    result.brand,
                    result.manufacturer,
                ]
            )
            if any(needle in value.lower() for value in haystacks if value):
                matches.append(result)
        return matches

    async def health_check(self) -> ProviderHealth:
        if self._fail_with is not None:
            return ProviderHealth(status="failed", detail="fault injection enabled")
        return ProviderHealth(status="ok", detail="mock provider always available")

    # -- Document capability (fixture-backed; supports API tests) ----------

    async def discover_documents(self, reference: str) -> list[ProviderDocumentInfo]:
        if self._fail_with is not None:
            raise self._fail_with
        if _DOCUMENT_REF.match(reference or "") is None:
            raise InvalidDocumentReference("mock document reference is invalid")
        return _sample_documents()

    async def fetch_document(
        self, source_path: str, *, conditional: dict[str, str] | None = None
    ) -> bytes:
        if self._fail_with is not None:
            raise self._fail_with
        known = {doc.source_path for doc in _sample_documents() if doc.available}
        if source_path not in known:
            raise DocumentNotFound("no sample document at this location")
        return _MOCK_PDF
