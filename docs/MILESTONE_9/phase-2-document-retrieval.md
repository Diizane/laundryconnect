# Milestone 9 — Phase 2: document retrieval (provider layer)

Status: **implemented — pending review.** Backend-internal only: Phase 3
(API contract + endpoint) and any mobile work are intentionally NOT in this
phase. Design decisions recorded in ADR 0013.

## Architecture summary

Evidence-driven (every behaviour below traces to a Phase 1 finding):

```
caller (Phase 3 API)
   │  discover_documents("/en/Manual?ManualId=…&ModelId=…")
   ▼
AllianceConnector ── mode gate (fixture default / session gated / credential refused)
   │
   ├─ fetch_page: /en/Manual menu ──────────────┐  bounded:
   │     parse_manual_page                      │  at most 2 HTML pages,
   ├─ fetch_page: /en/Model/Literature (if any) │  then STOP — no loops
   │     parse_literature_page → metadata       │  exist in the code
   ▼                                            ┘
[ProviderDocumentInfo…]  (metadata only; nothing persisted)

   │  fetch_document(source_path)
   ▼
SessionTransport.fetch_document
   ├─ URL policy + host allowlist (unchanged)
   ├─ Content-Type must be application/pdf (before any body read)
   ├─ leading bytes must be %PDF- (early abort otherwise)
   ├─ streamed under the 100 MB cap (unchanged)
   └─ 404 → DocumentNotFound; 401/ReturnUrl-redirect → ReauthenticationRequired;
      403 → AccessForbidden (all unchanged semantics)
```

New modules/changes:
- `app/providers/alliance/document_parser.py` — `parse_manual_page`,
  `parse_literature_page` (isolated, tolerant, fixture-pinned).
- `app/providers/alliance/transport.py` — `fetch_page` + hardened
  `fetch_document`; login-redirect detection extended to the observed
  `ReturnUrl=` form; `AllianceTransport` protocol widened; `FixtureTransport`
  serves the document-workflow fixtures.
- `app/providers/alliance/connector.py` — `discover_documents`,
  `fetch_document`, same mode/live gating as search.
- `app/providers/errors.py` — `DocumentNotFound`, `InvalidDocumentContent`.
- `app/providers/models.py` — `ProviderDocumentInfo` (metadata carrier;
  never persisted).
- `app/core/config.py` — `alliance_parts_base_url` (path resolution only).

Untouched: the Milestone 8 search pipeline, registry, API routes, database,
mobile app.

## Security review

- **No new hosts, no new modes.** Documents live on `pc.alliancels.net`
  (Phase 1, Q6) — already allowlisted. The live gate (approved flag ×
  not-CI × kill switch) and session validation run before ANY document
  fetch, exactly as for search.
- **Content validation is fail-closed.** Wrong Content-Type is rejected on
  headers alone (zero body bytes read); a mislabelled body aborts on its
  first bytes; both are terminal, never retried.
- **Bounded traversal is structural.** There is no loop over discovered
  links anywhere in the code — crawling is impossible, not just forbidden.
- **Sanitised state only.** Stored paths are query-stripped (`_clean_path`),
  so cache-busters/echoed search strings never enter models or logs; error
  messages carry structural detail only (status, declared media type);
  redirect diagnostics remain host+path only.
- **No persistence, no caching, no background work** — document bytes exist
  only for the lifetime of the request; metadata only in provider models.
- **Session-expiry evidence applied**: the observed document-path login
  redirect (`302 /?ReturnUrl=…`) now maps to `ReauthenticationRequired`
  (human re-bootstrap), not a generic failure.

## Test summary

315 backend tests pass (34 new), all fixture/mock, zero network:

- Manual-page parsing: literature/drawings-print/direct-PDF link extraction,
  query stripping, availability message, dedup, garbage tolerance.
- Literature parsing: metadata fields, multi-language rows, category/filename
  derivation, unavailable rows (`available=False`), garbage tolerance.
- Transport: PDF success (incl. `; charset` parameters), HTML-where-PDF
  rejected before body read, missing Content-Type rejected, mislabelled body
  aborted on first chunk, body shorter than magic rejected, 404 →
  `DocumentNotFound` (terminal, unretried) for pages and documents, search
  404 unchanged (`LiveFetchError`), 401 + ReturnUrl-redirect →
  `ReauthenticationRequired`, off-host redirect refused without leaking
  query values, 403 hard stop, size caps for pages and documents,
  off-allowlist refusal with no stream opened.
- Connector: fixture-mode discover→pick→fetch end-to-end (real parsers, real
  minimal PDF), traversal bound (exactly ≤2 page fetches, literature links
  never followed), relative-path resolution, session-mode gates
  (missing session → `ReauthenticationRequired`; credential mode refused).

## Live validation — PERFORMED 2026-07-30 ✅

Executed under operator supervision (session re-bootstrapped by the operator
first; the expired session en route exercised the reauth path against
production — the real `ReturnUrl` login redirect was detected and surfaced
as `ReauthenticationRequired`, as designed). Results, sanitised:

1. **Discovery** (`/en/Manual` for the Phase 1 DR75 manual): **7 documents**
   with correct metadata (4× Declaration of Conformity [DOC, 3+ languages],
   Installation Operation Maintenance Mnl [Production], Parts Mnl
   [PartsService], Technical Mnl [Production]) — matching the portal's own
   "Found 7 documents" and the Phase 1 browser observation.
2. **Document fetch** (D0568 Technical Mnl): 420,607 bytes — byte-for-byte
   the Content-Length observed in the Phase 1 browser capture; `%PDF-`
   magic validated.
3. **Invalid-path probe**: real HTTP 404 → `DocumentNotFound` (resolving the
   "404 behaviour unconfirmed" risk below — the portal does return a genuine
   404 for unknown document paths).

Two production-only defects were found and fixed during validation (the
purpose of the exercise — both were invisible to reconstructed fixtures):

- **Functional query parameters**: intermediate-page links require
  `ManualId`/`ModelId` (the portal 500s without them). The parser now keeps
  ONLY those allowlisted identifiers and still drops all search-echo
  parameters; document paths remain fully query-stripped.
- **Nested layout tables**: production wraps the document table in outer
  layout tables; the wrapper row previously parsed as one giant bogus
  record. Rows containing nested tables are now skipped, and the fixture
  reproduces the nesting so the regression is pinned offline.

### Original plan (for reference / future re-validation)

One supervised operator session, mirroring the Phase 1 procedure:

1. `ALLIANCE_MODE=session` + valid bootstrapped session + explicit
   `ALLIANCE_ACCESS_APPROVED=true`, on an operator machine.
2. One `discover_documents` against a known model's `/en/Manual` link —
   confirm the parsers return the expected document list from production
   HTML (the parsers are pinned to reconstructed fixtures; this validates
   them against reality).
3. One `fetch_document` of a single small manual — confirm
   `application/pdf`, `%PDF-` validation passes, and byte count matches
   the browser-observed Content-Length.
4. One negative probe: a plainly invalid document path → expect
   `DocumentNotFound` (confirms the portal's real 404 behaviour, which
   Phase 1 deliberately left unprobed).
5. Record results (sanitised) in this document; stop after one document.

## Risks

- **Parser drift**: fixtures are reconstructed from the observed DOM, not a
  raw capture. Mitigated by defensive parsing (anchor/table discovery rather
  than class names) and step 2 of the live validation plan; a sanitised raw
  capture can re-pin them if production differs.
- **Portal HTML changes over time** — same mitigation as search: tolerant
  parsers return empty rather than crash; live validation catches drift.
- **Rate limiting makes multi-request workflows slow by design** (12/min,
  single-flight): discovery (≤2 pages) plus a fetch is ≤3 requests — the
  conservative pacing is intentional; Phase 3 should surface progress to the
  client rather than raising limits.
- **Real 404 behaviour unconfirmed**: the portal may serve a themed 200 page
  for unknown ManualIds; the parsers then return an empty document list
  (honest, not wrong). Live validation step 4 resolves this.

## Recommendation

Ready for review as a tightly-scoped Phase 2 PR (provider layer only). The
supervised live validation (above) should run once before Phase 3 exposes an
endpoint, so the parsers are confirmed against production HTML rather than
reconstructed fixtures.
