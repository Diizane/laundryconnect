"""Document repository: documents and model associations."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, MachineModel, ModelDocument


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

    async def associate_with_model(self, document: Document, model: MachineModel) -> None:
        existing = await self._session.get(ModelDocument, (model.id, document.id))
        if existing is None:
            self._session.add(ModelDocument(machine_model_id=model.id, document_id=document.id))
            await self._session.flush()

    async def list_for_model(self, model_id: uuid.UUID) -> list[Document]:
        result = await self._session.scalars(
            select(Document)
            .join(ModelDocument, ModelDocument.document_id == Document.id)
            .where(ModelDocument.machine_model_id == model_id)
            .order_by(Document.document_type, Document.title)
        )
        return list(result)
