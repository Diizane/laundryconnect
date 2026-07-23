"""Provider record repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Provider


class ProviderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        slug: str,
        name: str,
        enabled: bool = True,
        base_url: str | None = None,
        notes: str | None = None,
    ) -> Provider:
        provider = Provider(slug=slug, name=name, enabled=enabled, base_url=base_url, notes=notes)
        self._session.add(provider)
        await self._session.flush()
        return provider

    async def get_by_slug(self, slug: str) -> Provider | None:
        return await self._session.scalar(select(Provider).where(Provider.slug == slug))

    async def list_all(self) -> list[Provider]:
        result = await self._session.scalars(select(Provider).order_by(Provider.slug))
        return list(result)
