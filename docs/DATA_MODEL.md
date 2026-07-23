# Data Model

> Status: **initial schema implemented (Milestone 4)** — six tables under
> Alembic migration `d95fc7d10b23`, accessed through the repository layer.

## Principles

- Start with the minimum useful schema; document intended evolution here.
- UUID primary keys (application-generated, portable `sa.Uuid`).
- `created_at` / `updated_at` timestamps on every table.
- Database constraints and useful indexes from the start; explicit
  constraint-naming convention for deterministic migrations.
- Alembic migrations from the first table (verified by tests).

## Implemented schema (Milestone 4)

Models live in `app/models/`, repositories in `app/repositories/`:

- **providers** — registry record: slug (unique), name, enabled, base_url,
  notes. (Credentials are *not* stored here — environment/secret manager
  only, see [SECURITY.md](SECURITY.md).)
- **manufacturers** — name (unique).
- **brands** — name, manufacturer FK; unique (manufacturer, name).
- **machine_models** — model_number (indexed), brand FK, machine_type,
  family; unique (brand, model_number).
- **documents** — title, document_type (indexed), provider FK,
  source_reference, source_url, revision, published_at, language;
  unique (provider, source_reference).
- **model_documents** — model↔document association, composite PK.
- **document_pages** (M7) — page-level extracted text: document FK (indexed),
  page_number, text_content; unique (document, page_number). The unit of
  in-document search and future RAG citations.

Repositories: `ProviderRepository`, `MachineRepository` (manufacturer/brand
get-or-create, model create/find), `DocumentRepository` (create, associate
with model — idempotent, list per model). Repositories flush but never
commit; the session dependency owns the transaction.

## Later entities (intended evolution)

Grouped by the milestone that likely introduces them:

- **Document ingestion (M8):** DocumentCategory, IngestionJob; PostgreSQL
  full-text indexing (tsvector) on document_pages.
- **Serial/part support (M6+):** MachineSerialRange, MachineConfiguration,
  Part, PartSupersession, Diagram, DiagramItem, TechnicalBulletin.
- **Users and company features (post-MVP):** User, Company, Bookmark,
  CompanyNote, AuditLog, SearchQuery, SearchResult (history/analytics).
- **Provider ops (M8+):** ProviderCredential (encrypted, only if unavoidable),
  ProviderSession.

Serial-number-specific document and part association is a first-class design
goal: `MachineSerialRange` links documents/parts to serial intervals so the
MVP's model-based results can become serial-specific without schema rework.

## Search indexing

PostgreSQL full-text search initially (tsvector on document pages);
OpenSearch/Elasticsearch only if scale requires. pgvector is the intended
extension point for semantic search / RAG later.
