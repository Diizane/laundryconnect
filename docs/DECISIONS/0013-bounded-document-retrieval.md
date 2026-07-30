# 0013 — Bounded document retrieval on the existing transport

Date: 2026-07-30
Status: accepted

## Context

Milestone 9 Phase 1 (docs/MILESTONE_9/phase-1-document-discovery.md)
established by supervised observation that an Alliance search result's
`/en/Manual?...` link is an intermediate HTML menu; documents are listed on
`/en/Model/Literature` and served as **stable, unsigned, session-protected
PDFs** at `pc.alliancels.net/manuals/<Category>/<PartNumber>.pdf` (query
value is a cache-buster; anonymous access 302-redirects to login with a
`ReturnUrl` parameter). The worst-case traversal from search result to
document bytes is two HTML pages plus one PDF.

## Decision

1. **Reuse `SessionTransport` unchanged in its guarantees; extend, don't
   duplicate.** Document fetches go through the same `_fetch` path — host
   allowlist, HTTPS/userinfo/port policy, streaming size caps, single-flight
   concurrency, rate limiting, bounded retries, 401/403/429 handling,
   redirect refusal, sanitised logging. Two additions, both terminal (never
   retried):
   - `fetch_page(url)`: one intermediate HTML page under the search-size
     cap, with HTTP 404 mapped to the domain error `DocumentNotFound`.
   - `fetch_document(url)`: one PDF under the document cap, requiring
     `Content-Type: application/pdf` **before any body bytes are read** and
     `%PDF-` magic bytes on the leading bytes (early abort on mismatch —
     defence against mislabelled responses), 404 → `DocumentNotFound`,
     content mismatch → `InvalidDocumentContent`.

2. **Login-redirect detection extended from evidence.** Phase 1 observed
   session expiry on document paths as `302 Location: /?ReturnUrl=<path>`
   (no `/login` in the URL). `_is_login_redirect` now treats a redirect
   carrying `ReturnUrl=` as session expiry → `ReauthenticationRequired`,
   preserving the human-in-the-loop re-auth flow instead of misclassifying
   it as an unexpected redirect.

3. **Traversal is bounded structurally, not by policy.**
   `AllianceConnector.discover_documents()` fetches the manual page, then at
   most the literature page, then stops — there is no link-following loop in
   the code, so crawling is impossible rather than merely prohibited. Parsing
   is isolated in `document_parser.py` (BeautifulSoup, tolerant, pinned
   against reconstructed sanitised fixtures mirroring the observed DOM).

4. **Metadata is captured but never persisted.** The literature page's
   part number, document type, comment, languages, category, filename and
   availability are returned via `ProviderDocumentInfo` (provider models
   only) to enable a future document picker without a parser redesign. No
   database writes, no caching, no background work.

5. **Fixture mode exercises the real parsers.** `FixtureTransport` serves
   reconstructed sanitised HTML fixtures for the manual/literature pages and
   a minimal real PDF, so CI tests the full discover → fetch → validate
   workflow with zero network access.

## Consequences

- The mobile client still has no path to Alliance: document bytes surface
  only through the backend (the Phase 3 API will proxy them; decision
  settled by Phase 1's Q11 finding that URLs alone are insufficient).
- A live provider response that is not a genuine PDF can never reach a
  client: wrong content type is rejected on headers alone; a mislabelled
  body aborts on its first bytes.
- 404 is now a domain outcome (`DocumentNotFound`) distinguishable from
  transport failure, so the API can answer "that document doesn't exist"
  honestly.
- The parsers are pinned to reconstructed fixtures; the supervised live
  validation plan (one manual re-run of the operator smoke workflow) should
  confirm them against production HTML before Phase 3 ships an endpoint.
