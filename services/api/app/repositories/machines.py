"""Machine catalog repository: manufacturers, brands, machine models."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Brand, MachineModel, Manufacturer


class MachineRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_manufacturer(self, name: str) -> Manufacturer:
        manufacturer = await self._session.scalar(
            select(Manufacturer).where(Manufacturer.name == name)
        )
        if manufacturer is None:
            manufacturer = Manufacturer(name=name)
            self._session.add(manufacturer)
            await self._session.flush()
        return manufacturer

    async def get_or_create_brand(self, manufacturer: Manufacturer, name: str) -> Brand:
        brand = await self._session.scalar(
            select(Brand).where(Brand.manufacturer_id == manufacturer.id, Brand.name == name)
        )
        if brand is None:
            brand = Brand(name=name, manufacturer_id=manufacturer.id)
            self._session.add(brand)
            await self._session.flush()
        return brand

    async def create_model(
        self,
        brand: Brand,
        model_number: str,
        machine_type: str | None = None,
        family: str | None = None,
    ) -> MachineModel:
        model = MachineModel(
            brand_id=brand.id,
            model_number=model_number,
            machine_type=machine_type,
            family=family,
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_model(self, model_id: uuid.UUID) -> MachineModel | None:
        return await self._session.scalar(
            select(MachineModel)
            .options(joinedload(MachineModel.brand).joinedload(Brand.manufacturer))
            .where(MachineModel.id == model_id)
        )

    async def find_models_by_number(self, model_number: str) -> list[MachineModel]:
        result = await self._session.scalars(
            select(MachineModel)
            .options(joinedload(MachineModel.brand).joinedload(Brand.manufacturer))
            .where(MachineModel.model_number.ilike(model_number))
        )
        return list(result)
