"""Seed the catalog with clearly-labelled SAMPLE data (development only).

Mirrors the mock provider connector's dataset so the machine workspace has
DB-backed content to serve. Idempotent: safe to run repeatedly.

Usage (migrations must be applied first):

    DATABASE_URL=... uv run python -m app.database.seed

This is sample data. It must never run against a production database once
real ingested documents exist — the seeded provider is the mock provider.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.session import create_engine, create_session_factory
from app.repositories.documents import DocumentRepository
from app.repositories.machines import MachineRepository
from app.repositories.providers import ProviderRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SampleDocument:
    source_reference: str
    title: str
    document_type: str
    revision: str | None = None
    published_at: date | None = None
    language: str = "en"


@dataclass(frozen=True)
class SampleMachine:
    manufacturer: str
    brand: str
    model_number: str
    machine_type: str
    family: str | None
    documents: tuple[SampleDocument, ...]


SAMPLE_MACHINES: tuple[SampleMachine, ...] = (
    SampleMachine(
        manufacturer="Alliance Laundry Systems",
        brand="Speed Queen",
        model_number="SC60",
        machine_type="washer_extractor",
        family="SC series",
        documents=(
            SampleDocument(
                "mock-doc-sc60-service",
                "SC60 Washer-Extractor Service Manual (sample)",
                "service_manual",
                revision="Rev 4",
                published_at=date(2023, 5, 1),
            ),
            SampleDocument(
                "mock-doc-sc60-parts",
                "SC60 Parts Manual (sample)",
                "parts_manual",
                revision="Rev 2",
                published_at=date(2022, 11, 15),
            ),
            SampleDocument(
                "mock-doc-sc60-wiring",
                "SC60 Wiring Diagram (sample)",
                "wiring_diagram",
                revision="Rev 1",
                published_at=date(2022, 6, 20),
            ),
        ),
    ),
    SampleMachine(
        manufacturer="Girbau",
        brand="Girbau",
        model_number="HS-6008",
        machine_type="washer_extractor",
        family="HS series",
        documents=(
            SampleDocument(
                "mock-doc-hs6008-install",
                "HS-6008 Installation Manual (sample)",
                "installation_manual",
                revision="Rev 1",
                published_at=date(2021, 3, 10),
            ),
            SampleDocument(
                "mock-doc-hs6008-operation",
                "HS-6008 Operation Manual (sample)",
                "operation_manual",
                revision="Rev 2",
                published_at=date(2021, 8, 2),
            ),
        ),
    ),
)


async def seed(session: AsyncSession) -> dict[str, int]:
    """Insert sample data, skipping anything already present.

    Returns counts of newly created rows per entity.
    """
    providers = ProviderRepository(session)
    machines = MachineRepository(session)
    documents = DocumentRepository(session)
    created = {"providers": 0, "models": 0, "documents": 0}

    provider = await providers.get_by_slug("mock")
    if provider is None:
        provider = await providers.create(
            slug="mock",
            name="Mock Provider (sample data)",
            notes="Seeded sample data mirroring the mock connector. Not live.",
        )
        created["providers"] += 1

    for sample in SAMPLE_MACHINES:
        manufacturer = await machines.get_or_create_manufacturer(sample.manufacturer)
        brand = await machines.get_or_create_brand(manufacturer, sample.brand)

        existing = await machines.find_models_by_number(sample.model_number)
        model = next((m for m in existing if m.brand_id == brand.id), None)
        if model is None:
            model = await machines.create_model(
                brand, sample.model_number, sample.machine_type, sample.family
            )
            created["models"] += 1

        for doc in sample.documents:
            document = await documents.get_by_source_reference(provider.id, doc.source_reference)
            if document is None:
                document = await documents.create(
                    title=doc.title,
                    document_type=doc.document_type,
                    provider_id=provider.id,
                    source_reference=doc.source_reference,
                    revision=doc.revision,
                    published_at=doc.published_at,
                    language=doc.language,
                )
                created["documents"] += 1
            await documents.associate_with_model(document, model)

    return created


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set; nothing to seed.")

    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    async with factory() as session:
        created = await seed(session)
        await session.commit()
    await engine.dispose()
    logger.info("sample data seeded", extra=created)


if __name__ == "__main__":
    asyncio.run(main())
