from sqlalchemy.ext.asyncio import AsyncSession

from app.database.seed import seed
from app.repositories.documents import DocumentRepository
from app.repositories.machines import MachineRepository
from app.repositories.providers import ProviderRepository


async def test_seed_creates_sample_catalog(db_session: AsyncSession) -> None:
    created = await seed(db_session)
    assert created == {"providers": 1, "models": 2, "documents": 5}

    provider = await ProviderRepository(db_session).get_by_slug("mock")
    assert provider is not None
    assert "sample" in provider.name.lower()

    [sc60] = await MachineRepository(db_session).find_models_by_number("SC60")
    documents = await DocumentRepository(db_session).list_for_model(sc60.id)
    assert len(documents) == 3
    assert all(doc.title.endswith("(sample)") for doc in documents)


async def test_seed_is_idempotent(db_session: AsyncSession) -> None:
    await seed(db_session)
    second_run = await seed(db_session)
    assert second_run == {"providers": 0, "models": 0, "documents": 0}
