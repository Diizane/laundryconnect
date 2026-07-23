"""Machine workspace endpoints.

Serves machines and their documents from the internal catalog (Milestone 4
schema). The catalog is populated by the sample-data seed for now; live
document ingestion arrives with Milestone 7+.
"""

import uuid
from itertools import groupby

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSessionDep
from app.models import Document, MachineModel
from app.repositories.documents import DocumentRepository
from app.repositories.machines import MachineRepository
from app.schemas.machines import (
    DocumentCategory,
    DocumentItem,
    MachineDocumentsResponse,
    MachineSummary,
)

router = APIRouter(prefix="/machines", tags=["machines"])


def _summary(model: MachineModel) -> MachineSummary:
    return MachineSummary(
        id=model.id,
        model_number=model.model_number,
        brand=model.brand.name,
        manufacturer=model.brand.manufacturer.name,
        machine_type=model.machine_type,
        family=model.family,
    )


def _document_item(document: Document) -> DocumentItem:
    return DocumentItem(
        id=document.id,
        title=document.title,
        document_type=document.document_type,
        provider=document.provider.slug,
        source_url=document.source_url,
        revision=document.revision,
        published_at=document.published_at,
        language=document.language,
        origin=document.origin,
    )


async def _get_model_or_404(session: DbSessionDep, machine_id: uuid.UUID) -> MachineModel:
    model = await MachineRepository(session).get_model(machine_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Machine not found.")
    return model


@router.get("", response_model=list[MachineSummary])
async def find_machines(
    session: DbSessionDep,
    model_number: str = Query(min_length=1, max_length=100),
) -> list[MachineSummary]:
    """Look up catalog machines by exact model number (case-insensitive)."""
    models = await MachineRepository(session).find_models_by_number(model_number)
    return [_summary(model) for model in models]


@router.get("/{machine_id}", response_model=MachineSummary)
async def get_machine(session: DbSessionDep, machine_id: uuid.UUID) -> MachineSummary:
    return _summary(await _get_model_or_404(session, machine_id))


@router.get("/{machine_id}/documents", response_model=MachineDocumentsResponse)
async def get_machine_documents(
    session: DbSessionDep, machine_id: uuid.UUID
) -> MachineDocumentsResponse:
    """The machine workspace: documents grouped by category (document type)."""
    model = await _get_model_or_404(session, machine_id)
    documents = await DocumentRepository(session).list_for_model(machine_id)
    categories = [
        DocumentCategory(
            document_type=document_type,
            documents=[_document_item(document) for document in docs],
        )
        for document_type, docs in groupby(documents, key=lambda d: d.document_type)
    ]
    return MachineDocumentsResponse(machine=_summary(model), categories=categories)
