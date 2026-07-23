"""Response schemas for machine workspace endpoints."""

import uuid
from datetime import date

from pydantic import BaseModel


class MachineSummary(BaseModel):
    id: uuid.UUID
    model_number: str
    brand: str
    manufacturer: str
    machine_type: str | None
    family: str | None


class DocumentItem(BaseModel):
    id: uuid.UUID
    title: str
    document_type: str
    provider: str
    source_url: str | None
    revision: str | None
    published_at: date | None
    language: str | None
    origin: str


class DocumentCategory(BaseModel):
    document_type: str
    documents: list[DocumentItem]


class MachineDocumentsResponse(BaseModel):
    machine: MachineSummary
    categories: list[DocumentCategory]
