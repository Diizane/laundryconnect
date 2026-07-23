"""Document repository: documents and model associations."""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Document, DocumentPage, MachineModel, ModelDocument

# Bounds for in-document page search (see ADR 0009). Pagination beyond the
# maximum is planned as an offset parameter once real manuals need it.
DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 50


def _escape_like(query: str) -> str:
    r"""Escape LIKE wildcards so user queries match literally.

    Without this, a query like "100%" or "F_8" would be interpreted as a
    pattern, diverging from the literal matching the snippet builder uses.
    """
    return query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        title: str,
        document_type: str,
        provider_id: uuid.UUID,
        source_reference: str,
        source_url: str | None = None,
        revision: str | None = None,
        published_at: date | None = None,
        language: str | None = None,
        origin: str = "live",
    ) -> Document:
        document = Document(
            title=title,
            document_type=document_type,
            provider_id=provider_id,
            source_reference=source_reference,
            source_url=source_url,
            revision=revision,
            published_at=published_at,
            language=language,
            origin=origin,
        )
        self._session.add(document)
        await self._session.flush()
        return document

    async def get(self, document_id: uuid.UUID) -> Document | None:
        return await self._session.get(Document, document_id)

    async def get_by_source_reference(
        self, provider_id: uuid.UUID, source_reference: str
    ) -> Document | None:
        return await self._session.scalar(
            select(Document).where(
                Document.provider_id == provider_id,
                Document.source_reference == source_reference,
            )
        )

    async def associate_with_model(self, document: Document, model: MachineModel) -> None:
        existing = await self._session.get(ModelDocument, (model.id, document.id))
        if existing is None:
            self._session.add(ModelDocument(machine_model_id=model.id, document_id=document.id))
            await self._session.flush()

    async def replace_pages(
        self, document: Document, page_texts: list[str], text_source: str
    ) -> int:
        """Replace a document's indexed pages with freshly extracted text.

        Transactional safety: delete + insert happen in the CALLER's
        transaction and this method only flushes, never commits. If any
        insert fails, the caller's rollback restores the previous pages —
        no partial page set can ever be committed. Callers must fully
        materialise `page_texts` (i.e. extraction has already succeeded)
        before invoking this; `app.documents.ingestion` enforces that order.
        """
        existing = await self._session.scalars(
            select(DocumentPage).where(DocumentPage.document_id == document.id)
        )
        for page in existing:
            await self._session.delete(page)
        # Flush deletes before inserts: SQLAlchemy's unit of work would
        # otherwise emit the inserts first and collide with the unique
        # (document_id, page_number) constraint. Both flushes share the
        # caller's transaction, so rollback still restores the old pages.
        await self._session.flush()
        for number, text in enumerate(page_texts, start=1):
            self._session.add(
                DocumentPage(
                    document_id=document.id,
                    page_number=number,
                    text_content=text,
                    text_source=text_source,
                )
            )
        await self._session.flush()
        return len(page_texts)

    async def page_count(self, document_id: uuid.UUID) -> int:
        result = await self._session.scalar(
            select(func.count())
            .select_from(DocumentPage)
            .where(DocumentPage.document_id == document_id)
        )
        return int(result or 0)

    async def get_page(self, document_id: uuid.UUID, page_number: int) -> DocumentPage | None:
        return await self._session.scalar(
            select(DocumentPage).where(
                DocumentPage.document_id == document_id,
                DocumentPage.page_number == page_number,
            )
        )

    async def search_pages(
        self, document_id: uuid.UUID, query: str, limit: int = DEFAULT_SEARCH_LIMIT
    ) -> tuple[list[DocumentPage], int]:
        """Case-insensitive literal substring search over a document's pages.

        Returns (pages, total_matches): deterministic page-number ordering,
        never more than MAX_SEARCH_LIMIT rows, plus the total match count so
        clients can tell when results were truncated. LIKE wildcards in the
        query are escaped so matching is literal — identical semantics to the
        snippet builder. Portable ILIKE for now; PostgreSQL full-text
        (tsvector) replaces this when real manuals arrive (ADR 0008/0009).
        """
        limit = max(1, min(limit, MAX_SEARCH_LIMIT))
        pattern = f"%{_escape_like(query)}%"
        criteria = (
            DocumentPage.document_id == document_id,
            DocumentPage.text_content.ilike(pattern, escape="\\"),
        )
        total = await self._session.scalar(
            select(func.count()).select_from(DocumentPage).where(*criteria)
        )
        result = await self._session.scalars(
            select(DocumentPage).where(*criteria).order_by(DocumentPage.page_number).limit(limit)
        )
        return list(result), int(total or 0)

    async def list_for_model(self, model_id: uuid.UUID) -> list[Document]:
        result = await self._session.scalars(
            select(Document)
            .options(joinedload(Document.provider))
            .join(ModelDocument, ModelDocument.document_id == Document.id)
            .where(ModelDocument.machine_model_id == model_id)
            .order_by(Document.document_type, Document.title)
        )
        return list(result)
