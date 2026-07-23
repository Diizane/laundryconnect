"""Document repository: documents and model associations."""

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Document, DocumentPage, MachineModel, ModelDocument


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

    async def replace_pages(self, document: Document, page_texts: list[str]) -> int:
        """Replace a document's indexed pages with freshly extracted text."""
        existing = await self._session.scalars(
            select(DocumentPage).where(DocumentPage.document_id == document.id)
        )
        for page in existing:
            await self._session.delete(page)
        for number, text in enumerate(page_texts, start=1):
            self._session.add(
                DocumentPage(document_id=document.id, page_number=number, text_content=text)
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
        self, document_id: uuid.UUID, query: str, limit: int = 20
    ) -> list[DocumentPage]:
        """Case-insensitive substring search over a document's pages.

        Portable ILIKE for now; PostgreSQL full-text (tsvector) replaces this
        when real manuals arrive — see ADR 0008.
        """
        pattern = f"%{query}%"
        result = await self._session.scalars(
            select(DocumentPage)
            .where(
                DocumentPage.document_id == document_id,
                DocumentPage.text_content.ilike(pattern),
            )
            .order_by(DocumentPage.page_number)
            .limit(limit)
        )
        return list(result)

    async def list_for_model(self, model_id: uuid.UUID) -> list[Document]:
        result = await self._session.scalars(
            select(Document)
            .options(joinedload(Document.provider))
            .join(ModelDocument, ModelDocument.document_id == Document.id)
            .where(ModelDocument.machine_model_id == model_id)
            .order_by(Document.document_type, Document.title)
        )
        return list(result)
