"""Documents, page-level content, and machine-model associations."""

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.provider import Provider


class DocumentOrigin(StrEnum):
    """How a document record entered the system. Sample/mock content must
    never be presentable as official provider data."""

    SEEDED_SAMPLE = "seeded_sample"
    LIVE = "live"
    UPLOADED = "uploaded"
    CACHED = "cached"


class PageTextSource(StrEnum):
    """Where a page's text came from — matters for trust, citations,
    debugging, and future AI retrieval."""

    NATIVE_PDF = "native_pdf"
    OCR = "ocr"
    PROVIDER_SUPPLIED = "provider_supplied"
    MANUAL_ENTRY = "manual_entry"
    SEEDED_SAMPLE = "seeded_sample"


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
    origin: Mapped[str] = mapped_column(String(20), default=DocumentOrigin.LIVE.value)

    provider: Mapped[Provider] = relationship()
    model_links: Mapped[list["ModelDocument"]] = relationship(back_populates="document")
    pages: Mapped[list["DocumentPage"]] = relationship(back_populates="document")


class DocumentPage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Page-level extracted text: the unit of in-document search.

    Large manuals are indexed and served page by page — whole PDFs are never
    loaded into memory to answer a search.
    """

    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    text_content: Mapped[str] = mapped_column(Text)
    text_source: Mapped[str] = mapped_column(String(30))
    # True when extraction cut the text at the per-page cap — truncation is
    # never silent (incomplete search results and citations must be visible).
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)

    document: Mapped[Document] = relationship(back_populates="pages")


class ModelDocument(TimestampMixin, Base):
    """Association between a machine model and a document."""

    __tablename__ = "model_documents"

    machine_model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("machine_models.id"), primary_key=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), primary_key=True)

    document: Mapped[Document] = relationship(back_populates="model_links")
