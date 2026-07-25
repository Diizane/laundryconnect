# Roadmap

Milestones are delivered in order; each produces a working, reviewable
increment. See git history for exact progress.

## Milestone 1 — Foundation ✅

- [x] Repository structure and documentation set
- [x] FastAPI application with app factory
- [x] Versioned API routes (`/api/v1`)
- [x] Environment-based configuration (pydantic-settings)
- [x] Structured JSON logging with request IDs and redaction guard
- [x] Health, liveness, readiness endpoints
- [x] Structured error responses (no stack traces to clients)
- [x] pytest suite (16 tests) and Ruff linting
- [x] Dockerfile + Docker Compose with PostgreSQL
- [x] `.env.example`, backend README
- [x] GitHub Actions CI (lint + format + tests)

## Milestone 2 — Provider connector framework ✅

- [x] `ProviderConnector` base interface (search, health, credential validation)
- [x] Normalised result models with honest `data_origin` labelling
- [x] Provider registry built from `ENABLED_PROVIDERS` (fails fast on typos)
- [x] Parallel fan-out search with per-provider timeouts
- [x] Partial failure as first-class outcome (one provider never breaks search)
- [x] Mock connector with labelled sample data and fault injection
- [x] `GET /api/v1/providers/status` endpoint
- [x] 22 new tests (registry, mock connector, status route)

## Milestone 3 — Unified search ✅

- [x] `POST /api/v1/search` with request validation (blank/overlong rejected)
- [x] Heuristic query-type detection for `auto` (model/serial/part/fault_code/keyword)
- [x] Parallel provider fan-out (composes Milestone 2 registry)
- [x] Deduplication (source_url / type+model+title+revision identity)
- [x] Exact-identifier ranking boost
- [x] Machine-first grouped response with per-provider outcomes
- [x] Cache-ready service shape (pure request→response; no cache until needed)
- [x] 38 new tests (detection, dedup/rank/group, route, partial failure)

## Milestone 4 — Core database ✅

- [x] Async SQLAlchemy 2.0 + asyncpg (production) / aiosqlite (tests)
- [x] Initial schema: providers, manufacturers, brands, machine_models,
      documents, model_documents
- [x] Alembic migrations, verified by up/down/parity tests
- [x] Repository layer (providers, machines, documents) — flush, never commit
- [x] Request-scoped session dependency (commit/rollback; 503 when no DB)
- [x] Real readiness check (`SELECT 1`, timeout, 503 when failing)
- [x] App still starts without a database (DATABASE_URL optional)
- [x] 19 new tests (repositories, migrations, readiness, session dependency)

## Milestone 5 — Flutter foundation ✅

- [x] Flutter scaffold (Android + iOS platforms, Android-first)
- [x] Navy/teal minimalist LaundryConnect theme
- [x] Home search screen: universal search bar, idle/loading/results/empty/
      error states, retry
- [x] API client for `POST /api/v1/search` with technician-friendly error
      messages (`API_BASE_URL` via --dart-define)
- [x] Machine-grouped results with data-origin, provider, type, revision badges
- [x] Partial-provider-failure warning banner
- [x] 10 tests (model parsing + widget tests for every state)
- [x] CI job: flutter analyze, format check, test

## Milestone 6 — Machine workspace ✅

- [x] Backend: `GET /api/v1/machines?model_number=`, `/machines/{id}`,
      `/machines/{id}/documents` (grouped by document type)
- [x] Idempotent sample-data seed (`python -m app.database.seed`)
- [x] Mobile: machine workspace screen — metadata header, categorised
      documents, loading/error/empty states
- [x] Search result → workspace navigation (honest miss message when the
      catalog doesn't know the model)
- [x] On-device recents (capped, deduplicated) and bookmarks with home-screen
      quick access
- [x] 11 backend tests + 13 mobile tests

## Milestone 7 — Document search ✅

- [x] `document_pages` table + migration (page-level text, unique per page)
- [x] pypdf page extraction (lazy, per-page fault tolerance, fixture-tested)
- [x] `GET /api/v1/documents/{id}` (metadata + page count), `/pages/{n}`,
      `/search?q=` with page-cited hits and server-built snippets
- [x] Seeded sample pages (fault codes, procedures — labelled SAMPLE)
- [x] Mobile: in-document search screen + page text viewer with prev/next
- [x] 14 new backend tests + 6 new mobile tests

## Milestone 8 — First real provider

One provider only, as a proof of architecture. The connector must include
(overseer-required checklist):

- [ ] Explicit authorization and provider terms review before any access —
      IN PROGRESS: access decision record drafted for Alliance Laundry
      Systems, classified UNKNOWN pending account-owner input
      (docs/PROVIDER_ACCESS/alliance-laundry-systems.md)
- [x] Backend-only credentials (never mobile; never from files/args/API —
      env/secret manager only, and credential mode is not implemented until
      terms permit it) (ADR 0012)
- [x] Session expiry handling (missing/invalid/expired → reauth_required)
- [ ] Provider rate limiting (with the live transport, post-approval)
- [ ] Timeout and retry policy (registry timeout applies; retry with the
      live transport, post-approval)
- [x] Structured failure reporting (reauthentication_required outcome,
      typed provider errors, class-name-only exposure)
- [x] Source provenance on every record (DataOrigin.FIXTURE for fixtures,
      LIVE reserved for approved live fetches)
- [ ] Document caching rules (with the live transport, post-approval)
- [x] No credentials or provider HTML in logs (session values never logged;
      security tests assert it)
- [x] Fixture-based tests only in CI — never the live service
      (ConnectorContract harness + fixture policy, ADR 0011)
- [x] Extraction in an isolated worker process with hard timeout and
      resource limits before processing provider documents (ADR 0011)

Explicitly out of scope during this milestone: AI chat, OCR, ordering,
inventory, admin portal expansion, additional providers.

## Post-MVP direction

Technician accounts and roles, offline caching and downloaded manuals,
part confirmation by serial range, retrieval-augmented document Q&A with
citations, admin portal build-out, additional providers.
