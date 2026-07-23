"""Documents and their machine-model associations."""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("provider_id", "source_reference"),)

    title: Mapped[str] = mapped_column(String(500))
    document_type: Mapped[str] = mapped_column(String(100), index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"))
    source_reference: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    revision: Mapped[str | None] = mapped_column(String(50))
    published_at: Mapped[date | None] = mapped_column(Date)
    language: Mapped[str | None] = mapped_column(String(20))

    model_links: Mapped[list["ModelDocument"]] = relationship(back_populates="document")


class ModelDocument(TimestampMixin, Base):
    """Association between a machine model and a document."""

    __tablename__ = "model_documents"

    machine_model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("machine_models.id"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), primary_key=True)

    document: Mapped[Document] = relationship(back_populates="model_links")
