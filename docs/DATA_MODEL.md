# Data Model

> Status: **design document**. Database integration lands in Milestone 4.
> No tables exist yet.

## Principles

- Start with the minimum useful schema; document intended evolution here.
- UUID primary keys.
- `created_at` / `updated_at` timestamps on every table.
- Database constraints and useful indexes from the start.
- Alembic migrations from the first table.

## Milestone 4 initial schema (planned)

The smallest set that supports unified search results and the machine
workspace:

- **Provider** — registry record: id, slug, name, enabled, base_url, notes.
  (Credentials are *not* stored here — environment/secret manager only, see
  [SECURITY.md](SECURITY.md).)
- **Manufacturer** / **Brand** — machine origin hierarchy.
- **MachineModel** — model number, manufacturer/brand, machine type, family,
  metadata (voltage, configuration) as it becomes available.
- **Document** — title, document_type, provider, source_url,
  source_reference, revision, published_at, language, storage location (when
  a copy is permitted).
- **ModelDocument** — many-to-many association between models and documents.

## Later entities (intended evolution)

Grouped by the milestone that likely introduces them:

- **Document search (M7):** DocumentPage (page-level text for full-text
  search), DocumentCategory, IngestionJob.
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
