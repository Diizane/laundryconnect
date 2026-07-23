# Architecture

## System overview

```
+---------------------+       +----------------------+
|  Flutter mobile app |       |  React admin portal  |
|  (apps/mobile)      |       |  (apps/admin)        |
|  [active, M5]       |       |  [not started]       |
+----------+----------+       +-----------+----------+
           |                              |
           +-------------+----------------+
                         v
              +---------------------+
              |  FastAPI backend    |
              |  (services/api)     |
              |  /api/v1/*          |
              +----+----------+----+
                   |          |
                   v          v
            +----------+  +-------------------------+
            | Postgres |  | Provider connectors     |
            | [M4]     |  | Alliance/Girbau/RJ [M2+]|
            +----------+  +-------------------------+
```

Clients never talk to providers directly. All provider authentication, search,
and document access happen on the backend behind a stable connector interface.

## Backend structure (current)

```
services/api/app/
  main.py            Application factory (create_app)
  core/
    config.py        pydantic-settings, environment-based
    logging.py       Structured JSON logging + request-ID contextvar
    middleware.py    Request ID + request outcome logging
    exceptions.py    Structured error envelope, no stack traces to clients
  api/
    router.py        /api/v1 aggregation
    deps.py          Shared dependencies (settings, registry, search service)
    routes/
      documents.py   Document metadata, page content, in-document search
      health.py      Health, liveness, readiness
      machines.py    Machine lookup/detail + documents grouped by category
      providers.py   Provider status (health-checks each connector)
      search.py      POST /api/v1/search
  search/
    detection.py     Heuristic query-type detection for auto searches
    processing.py    Deduplication, ranking, grouping (pure functions)
    service.py       SearchService: fan-out + shaping, cache-ready
  providers/
    base.py          ProviderConnector interface
    models.py        Normalised results, outcomes, query types, data origins
    registry.py      Registry + parallel fan-out search with timeouts
    mock/            Mock connector (labelled sample data, fault injection)
  documents/
    extraction.py    pypdf page-level text extraction (lazy, fault-tolerant)
    snippets.py      Server-built search-hit snippets
  models/            SQLAlchemy ORM models (catalog, documents+pages, providers)
  repositories/      All database access (flush, never commit)
  database/
    base.py          Declarative base, UUID/timestamp mixins, naming convention
    session.py       Async engine + session factory
    migrations/      Alembic environment and versions
  schemas/           Pydantic models for requests/responses
  tests/             pytest suite (95 tests)
```

The provider registry is built at startup from `ENABLED_PROVIDERS` and stored
on `app.state`; routes access it via a dependency.

The database is optional at startup: the engine is created only when
`DATABASE_URL` is set, session-dependent routes return 503 otherwise, and
readiness reports honestly either way (see ADR 0005).

Planned additions as milestones deliver (see [ROADMAP.md](ROADMAP.md)):
compliant document fetching/ingestion jobs and the first real provider
connector (Milestone 8).

## Mobile structure (current)

```
apps/mobile/lib/
  main.dart
  src/
    app.dart          Root widget; SearchApi injectable for tests
    theme/            Navy/teal brand theme
    api/              HttpSearchApi (API_BASE_URL via --dart-define)
    models/           Dart mirrors of backend search schemas
    screens/          Home search + machine workspace
    storage/          On-device recents/bookmarks (shared_preferences)
    widgets/          Result cards, data-origin + metadata badges
```

The app holds no credentials and talks only to the LaundryConnect backend.
State management is plain `StatefulWidget` + a sealed state class — no
state-management package until complexity demands one.

Separation rules:

- Route handlers stay thin: validate, delegate, shape response.
- Business logic lives in service modules, not routes.
- Provider-specific behaviour never leaks into core search — connectors return
  normalised internal models.
- Database access goes through a repository layer.

## Cross-cutting decisions

- **API versioning:** all routes under `/api/v1`; breaking changes mean a new
  version prefix.
- **Errors:** consistent envelope
  `{"error": {"code", "message", "request_id", "details?"}}`. Stack traces are
  logged server-side only.
- **Request IDs:** every request gets an `X-Request-ID` (incoming header
  honoured, else generated); it is attached to all log lines via a contextvar
  and echoed in responses.
- **Logging:** single-line JSON to stdout; key-based redaction guard for
  sensitive extras. See [SECURITY.md](SECURITY.md).
- **Configuration:** environment variables via pydantic-settings; the app must
  start without a database until Milestone 4.
- **Docs:** OpenAPI docs disabled in production.

## Future-facing constraints (deliberate)

- Search will run providers in parallel with per-provider timeouts; partial
  failure is a first-class response state, never a 500.
- Document storage, search, and serving are page-level (pages, not whole
  PDFs). Note: ingestion itself materialises a manual's extracted text in
  memory (bounded by extraction limits) before atomically replacing pages —
  see ADR 0010; it is not a streaming pipeline.
- Retrieval-augmented AI answers must cite document + page; the document
  system's page-level indexing is designed to support that.
- Offline support: keep API responses cacheable and self-describing so the
  mobile app can cache machine/document data later.

Significant choices are recorded in [DECISIONS/](DECISIONS/).
