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

## Milestone 8 — First real provider (Alliance) — live SEARCH ✅

One provider (Alliance Laundry Systems), as a proof of architecture. Live
**search** is complete, validated, and exposed through `/api/v1/search`.

- [x] Explicit authorization and provider terms review before any access —
      access record CONDITIONALLY APPROVED (authorised service partner;
      owner-asserted, not written provider permission)
      (docs/PROVIDER_ACCESS/alliance-laundry-systems.md)
- [x] Backend-only credentials (never mobile; never from files/args/API);
      credential mode refused (permission not established) (ADR 0012)
- [x] Human-in-the-loop session auth: manual browser bootstrap; no automated
      login; no MFA/CAPTCHA bypass (ADR 0012)
- [x] Session expiry handling (missing/invalid/expired → reauth_required)
- [x] Provider rate limiting (single-flight, conservative default 12/min)
- [x] Timeout, retry, streaming size caps, strict URL policy, terminal
      unexpected-redirect handling (ADR 0011/0012, streaming-verified)
- [x] Structured failure reporting: success / timed_out / disabled /
      reauthentication_required / forbidden; provider-local isolation
- [x] Source provenance on every record (fixture vs live, honest labelling)
- [x] Parts Connection HTML parser isolated from transport, pinned against a
      sanitised production capture (regression-fixtured)
- [x] Live search validated against production (40 SC60 results); no account
      data in logs; httpx request-URL logging quieted (ADR 0004)
- [x] Wired into `/api/v1/search`: mock-first default, explicit Alliance
      opt-in, deterministic aggregation, stateless (no persistence)
- [x] Fixture-based tests only in CI — never the live service (ADR 0011)
- [x] Isolated extraction worker with hard timeout/resource limits (ADR 0011)

Deferred to Milestone 9 (kept out of M8 on purpose): document retrieval,
any caching/persistence of provider data, background sync, OCR.

## Milestone 9 — Document retrieval (separate from search) ✅

Complete and live-validated end to end (2026-08-02): search → discover
documents → validated PDF through the backend proxy, with the mobile
client never seeing a provider URL. Uses the same authenticated transport
but was reviewed and tested independently of the validated search pipeline.

- [x] Phase 1 — Discover the document workflow ✅ (2026-07-26): supervised
  observation complete and reviewed. `/en/Manual` is an intermediate HTML
  menu; documents are stable unsigned PDFs at
  `pc.alliancels.net/manuals/<Category>/<PartNumber>.pdf`, session-protected
  (anonymous → 302 login), no extra hosts, no redirects when authenticated;
  bounded traversal (max 2 HTML pages + 1 PDF). API decision settled:
  backend proxies document bytes. Full findings + Phase 2/3 requirements in
  `docs/MILESTONE_9/phase-1-document-discovery.md`.
- [x] Phase 2 — Secure document retrieval (provider layer) — implemented,
  pending review: bounded discovery (`discover_documents`, max 2 HTML pages,
  structurally no crawling), `fetch_page`/hardened `fetch_document` on the
  existing SessionTransport (Content-Type + `%PDF-` magic validated before
  forwarding, 404 → `DocumentNotFound`, observed `ReturnUrl=` login redirect
  → reauth), literature metadata via `ProviderDocumentInfo` (never
  persisted), fixture-mode exercises the real parsers, 34 new offline tests.
  ADR 0013; docs/MILESTONE_9/phase-2-document-retrieval.md (incl. manual
  live-validation plan); supplementary portal observations recorded as
  future roadmap inputs (docs/MILESTONE_9/supplementary-observations.md).
- [x] Phase 3 — Document API (backend proxy) — implemented, pending review:
  `GET /api/v1/providers/{id}/documents?ref=` (client-safe metadata +
  encrypted opaque tokens; no provider URLs/paths/hostnames in responses) and
  `GET /api/v1/providers/{id}/documents/{token}` (server-side token
  resolution → provider fetch → validated `application/pdf`, sanitised
  filename, `Cache-Control: no-store`). Authenticated-encrypted (Fernet)
  provider-bound expiring tokens (15 min TTL; production secret enforced),
  fail-closed (tampering/expiry ≡ 404); no client URL/path input surface;
  provider-agnostic contract with mock fixture documents as default;
  deliberate leak-free error mapping (404/400/502/503). ADR 0014;
  docs/MILESTONE_9/phase-3-document-api.md. 368 backend tests (51 new),
  offline.
- Phase 4 — Persistence: keep current behaviour — no document persistence,
  no caching, no background downloads (each a separate future milestone if
  ever needed).

## Milestone 10 — First Android internal test build ✅

Complete (2026-08-02, tagged **v0.1.0 Internal Alpha**): installable debug
APK exercising the full technician flow against the Phase 3 backend —
search → result → document discovery (metadata list, disabled
unavailables) → backend PDF proxy via opaque tokens → in-memory in-app
viewer. Emulator smoke test passed with mock-only data; secrets scan
clean; cleartext HTTP isolated to debug builds (verified on both APKs);
46 mobile + 368 backend tests. APK distributed via the v0.1.0 GitHub
prerelease (never committed). Known limitation recorded: the viewer loads
the whole validated PDF into memory — large field manuals may need
temp-file/streamed rendering later.
Details: docs/MILESTONE_10/android-internal-test-build.md

## Next milestones (direction agreed at v0.1.0)

- **Milestone 11 — Technician field testing**: use v0.1.0 on real service
  calls first; record friction (search speed/wording, taps, outdoor
  readability, PDF usability, unsupported workflows) before adding any
  features.
- **Milestone 12 — Interactive drawings**: drawing → tap reference → part
  (builds on the observed /en/Manual/Drawing pages and partSearch
  filtering; requires its own discovery/observation pass first).
- **Milestone 13 — Multi-provider support**: additional connectors on the
  existing provider/transport/registry + document abstraction.
- **Milestone 14 — AI technician assistant**: serial → machine → documents
  → fault codes → suggested diagnosis/repair steps with citations.

## Post-MVP direction

Once document retrieval is validated, treat the Alliance integration as
feature-complete and shift toward product features: unified cross-provider
ranking, technician search UX, favourites/recent searches, offline fixture
packs, additional manufacturer connectors on the same transport/registry
architecture, and operational tooling (session health, provider
diagnostics, admin visibility). Also: technician accounts/roles and
retrieval-augmented document Q&A with citations.
