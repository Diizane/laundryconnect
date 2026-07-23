"""SQLAlchemy ORM models. Import all models here so Base.metadata and Alembic
autogeneration always see the full schema."""

from app.models.catalog import Brand, MachineModel, Manufacturer
from app.models.document import Document, DocumentPage, ModelDocument
from app.models.provider import Provider

__all__ = [
    "Brand",
    "Document",
    "DocumentPage",
    "MachineModel",
    "Manufacturer",
    "ModelDocument",
    "Provider",
]
