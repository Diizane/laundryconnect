"""Machine catalog: manufacturers, brands, machine models."""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Manufacturer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "manufacturers"

    name: Mapped[str] = mapped_column(String(200), unique=True)

    brands: Mapped[list["Brand"]] = relationship(back_populates="manufacturer")


class Brand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brands"
    __table_args__ = (UniqueConstraint("manufacturer_id", "name"),)

    name: Mapped[str] = mapped_column(String(200))
    manufacturer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manufacturers.id"))

    manufacturer: Mapped[Manufacturer] = relationship(back_populates="brands")
    models: Mapped[list["MachineModel"]] = relationship(back_populates="brand")


class MachineModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "machine_models"
    __table_args__ = (UniqueConstraint("brand_id", "model_number"),)

    model_number: Mapped[str] = mapped_column(String(100), index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"))
    machine_type: Mapped[str | None] = mapped_column(String(100))
    family: Mapped[str | None] = mapped_column(String(100))

    brand: Mapped[Brand] = relationship(back_populates="models")
