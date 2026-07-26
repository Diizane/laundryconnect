# Milestone 9 — Phase 1: Document retrieval discovery

Status: **Investigation open — findings not yet captured.** No implementation
of document retrieval may begin until the "Findings" section below is
completed from a supervised live observation. Do not guess any value in the
"Open questions" table; every answer must come from an observation, and be
marked with how it was obtained.

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
| 1 | Does `/en/Manual?ManualId=…&ModelId=…` serve a document body directly, or an intermediate HTML page? | _TBD_ | _TBD_ |
| 2 | If intermediate: how is the real document reached (link in HTML, JS, a second request, a redirect)? | _TBD_ | _TBD_ |
| 3 | What is the `Content-Type` of the final document response? (`application/pdf`, `image/*`, other?) | _TBD_ | _TBD_ |
| 4 | Is there a `Content-Disposition` / filename? | _TBD_ | _TBD_ |
| 5 | Are the final document URLs **stable** (reusable `/en/Manual?...` links) or **short-lived/signed** (tokens, expiry, one-time)? | _TBD_ | _TBD_ |
| 6 | On which host(s) does the final document live? Still `pc.alliancels.net`, or a CDN/blob host? (Determines allowlist adequacy.) | _TBD_ | _TBD_ |
| 7 | What redirect behaviour occurs between the `/en/Manual` URL and the final bytes? (count, hosts, login redirects) | _TBD_ | _TBD_ |
| 8 | How does the portal respond to a **non-existent** ManualId (status code, body)? | _TBD_ | _TBD_ |
| 9 | Approximate size range of a real manual / assembly drawing (sanity-check the 100 MB cap). | _TBD_ | _TBD_ |
| 10 | Does opening a document consume/rotate the session, or require any additional auth step? | _TBD_ | _TBD_ |
| 11 | Does opening the document URL directly in a **fresh unauthenticated** context succeed or fail? | _TBD_ | _TBD_ |

> Hypotheses (NOT answers — recorded only so the observer knows what to look
> for, and must be confirmed or refuted): the `/en/Manual` URL is likely an
> intermediate HTML viewer page rather than raw PDF bytes; if so, the real
> asset may sit behind a second request and possibly a signed/temporary URL on
> a different host. **These are guesses and must not be coded against until
> confirmed.**

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

_To be completed from the supervised observation above. Leave as TBD until an
observation has actually been performed; do not fill in from assumption._

- Q1 (direct vs intermediate): _TBD_
- Q2 (path to real document): _TBD_
- Q3 (Content-Type): _TBD_
- Q4 (Content-Disposition/filename): _TBD_
- Q5 (URL stability): _TBD_
- Q6 (final host): _TBD_
- Q7 (redirect behaviour): _TBD_
- Q8 (not-found behaviour): _TBD_
- Q9 (size range): _TBD_
- Q10 (session effect): _TBD_
- Q11 (direct unauthenticated access): _TBD_

## How findings feed later phases

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
- [ ] Capture findings from an actual supervised observation (blocked on a
      human running Method A). **← the remaining Phase 1 step.**
