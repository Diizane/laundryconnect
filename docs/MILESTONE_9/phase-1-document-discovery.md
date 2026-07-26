# Milestone 9 — Phase 1: Document retrieval discovery

Status: **COMPLETE — findings captured and reviewed (2026-07-26).** A single
supervised observation was performed by the authorised operator on the
authenticated machine (operator performed the login personally; navigation
and sanitised network capture were then performed under the operator's
direct supervision within that session). One document was opened (DR75 →
D0568 Technical Manual); no bulk retrieval, no crawling. Every answer in the
"Open questions" table comes from that observation, and the raw sanitised
capture is transcribed verbatim in the Findings section.

This phase is deliberately documentation-only. It records what the existing
code already establishes as fact, enumerates exactly what is still unknown,
and defines a supervised, human-in-the-loop procedure to answer the unknowns
without any automation, crawling, persistence, or CI involvement.

## Scope reminder (from the Milestone 9 brief)

The goal of Milestone 9 is a single technician workflow:

> Search → select a result → open the associated manual or assembly drawing.

Out of scope for the whole milestone (do not design for these now): caching,
persistence, database storage, background sync, favourites, bulk retrieval,
crawling, indexing, additional providers, UI redesign. Phase 1 specifically
implements **nothing** — it only produces findings.

## What is already known (grounded in code, not observation)

These are facts established by the existing, tested Milestone 8 code. They are
starting points, not answers to the open questions.

1. **A search result already contains the document link.** The Parts
   Connection HTML parser maps each result row to a `source_url`, e.g.
   `https://pc.alliancels.net/en/Manual?ManualId=15171&ModelId=429746`
   (`app/providers/alliance/parser.py`; pinned by
   `app/tests/test_alliance_parser.py` and `test_alliance_connector.py`). So
   the client-visible entry point to a document is this `/en/Manual?...` URL on
   host `pc.alliancels.net`.

2. **A safeguarded fetch primitive already exists.**
   `SessionTransport.fetch_document(url)` (`app/providers/alliance/transport.py`)
   streams a URL under the document size cap and reuses every search-path
   safeguard:
   - HTTPS-only, exact host allowlist (`portal.alliancels.net`,
     `pc.alliancels.net`), no userinfo, port 443 only (`_check_url`).
   - Genuine streaming with early abort past the cap
     (`alliance_max_document_bytes`, default 100 MB) plus a `Content-Length`
     pre-check (`_check_declared_size` / `_read_capped`).
   - Bounded retries on transient 5xx/transport errors only; single-flight
     concurrency; conservative rate limiting.
   - `401` or a `/login` redirect → `ReauthenticationRequired`; `403` →
     `AccessForbidden` (hard stop, never retried); any other 3xx → refused
     `UnexpectedRedirect` (redirects are never followed —
     `follow_redirects=False`).

3. **What `fetch_document` does NOT yet do** (intentionally deferred; these are
   Phase 2/3 concerns, and their design depends on the findings below):
   - No `Content-Type` inspection — it returns raw bytes regardless of whether
     the body is a PDF, an image, or an intermediate HTML page.
   - No distinction between "the URL served the document directly" and "the URL
     served an HTML page that links to / redirects to the real document."
   - No graceful "document not found" (`404`) result — a `404` currently
     surfaces as a generic `LiveFetchError`, indistinguishable from other 4xx.
   - No API endpoint. The mobile client currently has no way to open a
     document, and (per the brief) must never talk to Alliance directly.

4. **Operator smoke test exists but under-reports for discovery.**
   `python -m app.providers.alliance.smoke_test SC60 --document <url>` performs
   one supervised `fetch_document` and prints only a byte count
   (`app/providers/alliance/smoke_test.py`). That is enough to prove retrieval
   works, but NOT enough to answer "PDF vs intermediate page" or "what
   Content-Type / redirects occur." The supervised procedure below therefore
   relies primarily on direct browser observation, which exposes status,
   headers, and redirect chains without any new code.

## Open questions (to be answered ONLY by observation)

| # | Question | Answer | How obtained |
|---|----------|--------|--------------|
| 1 | Does `/en/Manual?ManualId=…&ModelId=…` serve a document body directly, or an intermediate HTML page? | **Intermediate HTML page** (200, `text/html`): an "Additional Information" menu (assembly drawings, Related Literature, wiring diagrams, parts lists) — never the document itself. | Supervised observation, 2026-07-26 |
| 2 | If intermediate: how is the real document reached? | Plain HTML links, no JS required. Observed path: `/en/Manual` → (optionally) `/en/Model/Literature?ManualId=…&ModelId=…` (HTML list of documents) → `<a href="/manuals/<Category>/<PartNumber>.pdf?<ticks>">` with a PDF icon. Assembly drawings link via `/en/Manual/DrawingsPrint?…` from the same menu. | Supervised observation |
| 3 | `Content-Type` of the final document response? | `application/pdf` (body verified to begin `%PDF-1.6`). | Supervised observation (header capture) |
| 4 | `Content-Disposition` / filename? | **No `Content-Disposition` header.** Filename is the URL's `<PartNumber>.pdf`. | Supervised observation (header capture) |
| 5 | Stable or short-lived/signed URLs? | **Stable.** The query value is an identical timestamp-style cache-buster on every link on the page, and the PDF is served identically **without** it (verified: 200, same length, same magic bytes). Canonical identity is the path `/manuals/<Category>/<PartNumber>.pdf`. No token, no expiry, no signature. | Supervised observation (fetch with and without param) |
| 6 | Final document host? | `pc.alliancels.net` — same host, already in the allowlist. No CDN/blob/third-party host observed anywhere in the chain. | Supervised observation |
| 7 | Redirect behaviour? | **None when authenticated** — every hop returns a direct 200. (Unauthenticated → single 302 to login; see Q11.) | Supervised observation |
| 8 | Non-existent ManualId behaviour? | Not probed live (kept to the one-document scope). The observed equivalent: a **valid** manual with no assembly drawings returns 200 HTML with the message "The assembly drawings are not available for the selected model." Genuine 404 behaviour to be confirmed against fixtures in Phase 2 tests; the transport treats any 4xx as a terminal error already. | Supervised observation (partial); deferred |
| 9 | Approximate document size? | Observed manual: **420,607 bytes (~411 KB)** with `Content-Length` present and `Accept-Ranges: bytes`. Far under the 100 MB cap. | Supervised observation (header capture) |
| 10 | Session consumed/rotated by document access? | No additional auth step observed; the same session served page and document requests repeatedly (fetch with and without param both 200). | Supervised observation |
| 11 | Fresh unauthenticated access? | **Fails closed: 302 redirect to login** with `Location: /?ReturnUrl=<pdf path>` — with or without the query param. Documents are session-protected server-side. | Cookie-less HEAD request during observation |

> Hypotheses recorded before observation, now resolved: "the `/en/Manual` URL
> is likely an intermediate HTML viewer page" — **CONFIRMED**. "The real asset
> may sit behind … possibly a signed/temporary URL on a different host" —
> **REFUTED**: same host, stable unsigned path (the query value is a
> cache-buster). The real system is simpler than the cautious assumptions.

## Supervised observation procedure (human-in-the-loop, no automation)

Constraints for this procedure, non-negotiable and consistent with Milestone 8:
no CI involvement; a human performs every step; nothing is crawled; at most a
handful of individual documents are opened by hand; nothing is persisted into
the repo; and no cookies, tokens, signed URLs, query strings, or account
identifiers are recorded or pasted back. Record only sanitised facts (status
codes, `Content-Type`, host + path, PDF-vs-HTML, approximate size).

### Method A — Browser observation (primary; requires no new code)

The operator already has an authenticated browser session (the one used to
bootstrap `alliance-session.json`). Using that same logged-in browser:

1. Run one search in the app / Parts Connection for a known model (e.g. `SC60`)
   and pick one result that has a `/en/Manual?ManualId=…&ModelId=…` link.
2. Open the browser devtools **Network** tab, then click/open the Manual link.
3. From the Network panel, record for each request in the chain (sanitised —
   host + path only, never the query string if it contains a token):
   - the sequence of requests and any redirects (status `30x` + destination
     host/path);
   - the **final** response's status, `Content-Type`, and `Content-Length`;
     whether the browser rendered a PDF/image inline or showed an HTML page;
   - whether the document host is `pc.alliancels.net` or something else.
4. Note whether re-opening the same link later still works (question 5 —
   stable vs short-lived), without recording the actual URL if it is signed.
5. For question 11, copy the final document URL and open it in a **fresh
   unauthenticated context** (a private/incognito window with no Alliance
   cookies); record only whether it succeeds, fails, or redirects to login —
   never the URL itself if it carries a signature/token.

Stop after **one** successful document observation. Do not bulk-open manuals
or download multiple files.

Sanitised capture format (fill this in and paste back — redact cookies,
account details, and any signed query values; host + path only):

```
Search result selected:
Initial request host/path:
Initial status:
Initial Content-Type:
Initial response shape:          # HTML / PDF / other

Secondary document request observed: yes/no
Secondary host/path:             # query values redacted, e.g. /docstore?sig=<redacted>
Secondary status:
Secondary Content-Type:
Redirect chain:                  # host/path hops only, or "none"
Inline or attachment:            # displayed inline vs downloaded
Temporary/signed URL indicators: # e.g. expiry/sig/token params present? yes/no
Authenticated session required:  # yes/no
Direct unauthenticated access result:  # succeeds / fails / redirects to login

Other observations:
```

### Method B — Operator capture (optional; only if exact headers are needed)

Only if the browser observation is ambiguous about headers. A read-only
operator instrument to report sanitised response metadata (final status,
`Content-Type`, `Content-Length`, redirect host/path, and a `%PDF`/`<html`
body sniff — persisting nothing) will be added as a small, clearly
operator-only, CI-refused tool **in Phase 2**, alongside the transport work it
belongs to. It is intentionally not built in Phase 1 so that Phase 1 remains
investigation-only. Until then, Method A is sufficient.

## Findings

Captured 2026-07-26 from a single supervised observation (one document; DR75
Tumbler → D0568 Technical Manual). Reviewed and approved. The sanitised
capture, verbatim:

```
Search result selected: DR75 (Tumbler), Manual "Date 9/99" → Related Literature →
                        D0568 Technical Manual (English)

Initial request host/path: pc.alliancels.net /en/Manual (ManualId/ModelId params)
Initial status: 200
Initial Content-Type: text/html
Initial response shape: HTML — an intermediate menu page ("Additional Information":
                        assembly drawings, Related Literature, wiring diagrams, parts
                        lists). NOT the document.

Secondary document request observed: yes (two hops, both HTML menus, then the PDF)
  Hop 1: /en/Manual?ManualId=…&ModelId=…            → 200 text/html (menu)
  Hop 2: /en/Model/Literature?ManualId=…&ModelId=…  → 200 text/html (lists 7 documents
         with per-document PDF links)
Secondary host/path: pc.alliancels.net /manuals/<Category>/<PartNumber>.pdf?<ticks>
                     (observed categories: Production, PartsService, DOC)
Secondary status: 200
Secondary Content-Type: application/pdf (Content-Length: 420,607; body begins %PDF-1.6;
                        static IIS file: ETag + Last-Modified 2021 + Accept-Ranges)
Redirect chain: none when authenticated (direct 200)
Inline or attachment: inline (no Content-Disposition header; browser renders in-tab)
Temporary/signed URL indicators: NO. The query value is an identical timestamp-style
                     cache-buster on every link on the page, and the PDF is served
                     identically WITHOUT it (verified: 200, same bytes). Paths are
                     stable static file paths keyed by part number.
Authenticated session required: yes
Direct unauthenticated access result: 302 redirect to login
                     (Location: /?ReturnUrl=<the pdf path>) — with or without the
                     query param. Fails closed.

Other observations:
- The /en/Manual link from search results is ALWAYS an intermediate HTML page; for this
  model, assembly drawings were "not available" and the page pointed to Related
  Literature instead. Document discovery therefore requires parsing 1–2 intermediate
  HTML pages (bounded, not crawling).
- Document host is pc.alliancels.net — already in the allowlist. No CDN, no other host.
- Literature page states: "Document is available for download if PDF icon is visible,
  click icon to download."
- Size sanity: this manual was ~411 KB; well under the 100 MB cap.
- Account identifier was visible in the page header — redacted from these findings.
```

### Additional reviewed observations

**Document discovery is bounded — an architectural property, not a policy
promise.** The worst-case traversal from a search result to document bytes is:

```
Search result → /en/Manual (HTML menu) → /en/Model/Literature (HTML list)
             → /manuals/<Category>/<PartNumber>.pdf
```

Maximum depth: **2 HTML pages + 1 PDF**, each reached by following one
explicit link for one user action. This is page parsing, not crawling, and
Phase 2 must preserve that bound structurally (no link-following loops).

**The document list carries useful metadata.** The Literature page exposes,
per document: part number, document type (Declaration of Conformity /
Installation Operation Maintenance Mnl / Parts Mnl / Technical Mnl), a
comment (revision/date), available languages, and whether a PDF is
downloadable. Phase 2's parser should capture this metadata even though the
first Android release only opens a document directly — it enables a richer
document-picker UI later (multiple manuals, language selection) without a
parser redesign.

## Phase 1 conclusions (approved)

1. **`/en/Manual` is an intermediate page.** Document retrieval is HTML page
   parsing (one or two bounded pages), not URL rewriting.
2. **No allowlist change needed.** Every request in the chain stays on
   `pc.alliancels.net`; no CDN, blob storage, or third-party document host.
3. **The session model is server-side and fails closed.** Anonymous document
   requests receive a 302 to login (`ReturnUrl=<pdf>`); URLs alone are
   insufficient. The transport's existing login-redirect → 
   `ReauthenticationRequired` mapping applies to document fetches unchanged.
4. **Document URLs are stable and unsigned.** Canonical identity is the path
   `/manuals/<Category>/<PartNumber>.pdf`; the query value is a cache-buster
   served identically when omitted. No signed-URL handling is needed.
5. **API decision — settled: the backend proxies document bytes.** The mobile
   client has no Alliance session, provider URLs stay private, authentication
   stays server-side, the existing transport is reused, and future providers
   fit the same abstraction.

### Phase 2 requirements distilled from the evidence

- Validate `Content-Type: application/pdf` before streaming; reject
  `text/html` at the final fetch stage (an HTML body at the PDF stage means a
  wrong or error page, not a document).
- Validate magic bytes: the stream must begin `%PDF-` before any bytes are
  forwarded (protects against misconfigured servers).
- Translate 404 into a domain-specific `DocumentNotFound` rather than a
  generic transport error.
- Keep streaming — no buffering; existing size caps and streaming
  implementation unchanged.
- Preserve the bounded traversal: at most the two observed intermediate pages
  per user action, no link-following beyond them.
- Capture the Literature-page document metadata during parsing.

### Phase 3 shape (to be recorded as an ADR before implementation)

`GET /api/v1/documents/{provider}/{document_id}` (or equivalent), internally:
lookup document → fetch via provider transport → validate → stream bytes →
client. The mobile app never sees an Alliance URL.

## How findings feed later phases

> Written before the observation; retained for the reasoning record. The
> conditionals below are now resolved by the "Phase 1 conclusions" section:
> Q1 = intermediate page (bounded parsing required), Q5 = stable unsigned
> URLs, Q6 = same host, and the API decision is settled as backend
> byte-proxying (because documents are session-protected, not because URLs
> are signed — see Q11).

- **Phase 2 (secure transport):** the `Content-Type` (Q3), host (Q6), and
  redirect (Q7) findings determine the document-specific validation to add to
  the existing transport — expected-content-type checking, whether the current
  allowlist covers the real document host, and whether the "never follow
  redirects" stance needs a narrowly-scoped exception (it should not, unless
  the evidence forces it). If Q1 shows an intermediate page, Phase 2 must
  decide whether the backend parses that page to locate the asset (a bounded,
  single extra request — never crawling).
- **Phase 3 (API contract):** Q5 (stable vs signed URLs) is the deciding input
  for proxy-bytes vs internal-download-endpoint vs metadata-only. Signed /
  short-lived URLs argue for the backend proxying bytes (so the mobile client
  never sees a provider URL and never talks to Alliance); stable public-ish
  URLs might allow a metadata approach. The decision will be recorded as an
  ADR before any Phase 4 implementation.
- **Phase 4 (implementation):** proceeds only after the ADR, and keeps current
  behaviour — streaming, no persistence, no caching, no background downloads.

## Deliverable checklist for Phase 1

- [x] Record what is already known from code (entry URL, existing
      `fetch_document` safeguards, gaps).
- [x] Enumerate the open questions that require observation.
- [x] Define a supervised, no-automation observation procedure.
- [x] Capture findings from an actual supervised observation (performed
      2026-07-26; one document; reviewed and approved).

**Phase 1 is complete.** Next: Phase 2 (document transport validation +
bounded page parsing) and the Phase 3 ADR, per the conclusions above.
