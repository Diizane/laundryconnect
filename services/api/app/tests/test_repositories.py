import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.documents import DocumentRepository
from app.repositories.machines import MachineRepository
from app.repositories.providers import ProviderRepository


class TestProviderRepository:
    async def test_create_and_get_by_slug(self, db_session: AsyncSession) -> None:
        repo = ProviderRepository(db_session)
        created = await repo.create(slug="alliance", name="Alliance Laundry Systems")
        found = await repo.get_by_slug("alliance")
        assert found is not None
        assert found.id == created.id
        assert found.enabled is True
        assert found.created_at is not None

    async def test_get_missing_slug_returns_none(self, db_session: AsyncSession) -> None:
        assert await ProviderRepository(db_session).get_by_slug("nope") is None

    async def test_duplicate_slug_rejected(self, db_session: AsyncSession) -> None:
        repo = ProviderRepository(db_session)
        await repo.create(slug="girbau", name="Girbau")
        with pytest.raises(IntegrityError):
            await repo.create(slug="girbau", name="Girbau again")

    async def test_list_all_ordered_by_slug(self, db_session: AsyncSession) -> None:
        repo = ProviderRepository(db_session)
        await repo.create(slug="girbau", name="Girbau")
        await repo.create(slug="alliance", name="Alliance")
        assert [p.slug for p in await repo.list_all()] == ["alliance", "girbau"]


class TestMachineRepository:
    async def test_get_or_create_manufacturer_is_idempotent(self, db_session: AsyncSession) -> None:
        repo = MachineRepository(db_session)
        first = await repo.get_or_create_manufacturer("Alliance Laundry Systems")
        second = await repo.get_or_create_manufacturer("Alliance Laundry Systems")
        assert first.id == second.id

    async def test_create_model_and_find_case_insensitive(self, db_session: AsyncSession) -> None:
        repo = MachineRepository(db_session)
        manufacturer = await repo.get_or_create_manufacturer("Alliance Laundry Systems")
        brand = await repo.get_or_create_brand(manufacturer, "Speed Queen")
        model = await repo.create_model(brand, "SC60", machine_type="washer_extractor")

        [found] = await repo.find_models_by_number("sc60")
        assert found.id == model.id
        assert found.brand.name == "Speed Queen"
        assert found.brand.manufacturer.name == "Alliance Laundry Systems"

    async def test_duplicate_model_per_brand_rejected(self, db_session: AsyncSession) -> None:
        repo = MachineRepository(db_session)
        manufacturer = await repo.get_or_create_manufacturer("Girbau")
        brand = await repo.get_or_create_brand(manufacturer, "Girbau")
        await repo.create_model(brand, "HS-6008")
        with pytest.raises(IntegrityError):
            await repo.create_model(brand, "HS-6008")

    async def test_same_model_number_allowed_across_brands(self, db_session: AsyncSession) -> None:
        repo = MachineRepository(db_session)
        alliance = await repo.get_or_create_manufacturer("Alliance")
        girbau = await repo.get_or_create_manufacturer("Girbau")
        brand_a = await repo.get_or_create_brand(alliance, "Speed Queen")
        brand_b = await repo.get_or_create_brand(girbau, "Girbau")
        await repo.create_model(brand_a, "X100")
        await repo.create_model(brand_b, "X100")
        assert len(await repo.find_models_by_number("X100")) == 2


class TestDocumentRepository:
    async def _setup(self, session: AsyncSession):
        providers = ProviderRepository(session)
        machines = MachineRepository(session)
        provider = await providers.create(slug="alliance", name="Alliance")
        manufacturer = await machines.get_or_create_manufacturer("Alliance")
        brand = await machines.get_or_create_brand(manufacturer, "Speed Queen")
        model = await machines.create_model(brand, "SC60")
        return provider, model

    async def test_create_associate_and_list(self, db_session: AsyncSession) -> None:
        provider, model = await self._setup(db_session)
        docs = DocumentRepository(db_session)
        document = await docs.create(
            title="SC60 Service Manual",
            document_type="service_manual",
            provider_id=provider.id,
            source_reference="doc-1",
            revision="Rev 4",
        )
        await docs.associate_with_model(document, model)

        listed = await docs.list_for_model(model.id)
        assert [d.title for d in listed] == ["SC60 Service Manual"]
        assert await docs.get(document.id) is not None

    async def test_associate_is_idempotent(self, db_session: AsyncSession) -> None:
        provider, model = await self._setup(db_session)
        docs = DocumentRepository(db_session)
        document = await docs.create(
            title="Manual",
            document_type="service_manual",
            provider_id=provider.id,
            source_reference="doc-1",
        )
        await docs.associate_with_model(document, model)
        await docs.associate_with_model(document, model)
        assert len(await docs.list_for_model(model.id)) == 1

    async def test_duplicate_source_reference_per_provider_rejected(
        self, db_session: AsyncSession
    ) -> None:
        provider, _ = await self._setup(db_session)
        docs = DocumentRepository(db_session)
        await docs.create(
            title="A", document_type="manual", provider_id=provider.id, source_reference="ref"
        )
        with pytest.raises(IntegrityError):
            await docs.create(
                title="B", document_type="manual", provider_id=provider.id, source_reference="ref"
            )

    async def test_list_for_model_empty(self, db_session: AsyncSession) -> None:
        _, model = await self._setup(db_session)
        assert await DocumentRepository(db_session).list_for_model(model.id) == []
