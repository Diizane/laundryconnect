# Milestone 9 — Phase 3: document API (backend proxy)

Status: **implemented — pending review.** Backend API only; no Flutter/
Android work (next milestone). Design decisions in ADR 0014.

## Endpoint contract

```
GET /api/v1/providers/{provider_id}/documents?ref=<reference>
    → 200 DocumentDiscoveryResponse
      { provider_id, documents: [ { token|null, title, document_type,
        part_number, comment, languages, category, filename, available,
        data_origin } ] }

GET /api/v1/providers/{provider_id}/documents/{token}
    → 200 application/pdf bytes
      Content-Disposition: inline; filename="<sanitised>.pdf"
      Cache-Control: no-store
```

- `ref` is the search result's document reference. For Alliance it is
  `<ManualId>:<ModelId>` — both values already present in search-result
  `metadata` (the M8 search response is unchanged). Providers strictly
  validate their own reference format before any request.
- `token` is an authenticated-**encrypted**, provider-bound, expiring
  opaque identifier minted by discovery (Fernet via the `cryptography`
  library; 15-minute default TTL; ADR 0014). The payload is confidential —
  decoding the token yields ciphertext only. Clients treat it as a black
  box; expiry simply means rediscovering (which re-mints).
- The client workflow: search → select result → discover documents →
  select document → receive validated PDF bytes. **No provider URL, path,
  hostname, or internal identifier appears anywhere in responses** (tested
  by marker-scan against serialized JSON).

Error mapping (fixed detail strings; nothing upstream leaks): 404 document/
provider not found or any invalid token; 400 invalid reference or provider
without document capability; 503 reauthentication required / live mode not
enabled; 502 provider forbidden / invalid content / transient failure.

## Architecture summary

```
client → GET documents?ref → route → registry → connector.discover_documents(ref)
                                  ← metadata            (strict ref validation,
             mint token per available doc                bounded 2-page traversal)
client → GET documents/{token} → Fernet decrypt-and-validate
                                  (authenticated, TTL + issued-at checked,
                                   provider-bound)
                                → connector.fetch_document(source_path)
                                  (path-shape validation → live gates →
                                   allowlist → streamed under cap →
                                   Content-Type + %PDF validated)
                                ← application/pdf bytes, no-store
```

New: `app/api/routes/provider_documents.py`, `app/schemas/provider_documents.py`,
`app/providers/document_token.py`, base-contract document methods (default:
`ProviderDocumentsUnsupported`), mock provider fixture documents, Alliance
reference validation (`<digits>:<digits>`) + document path-shape validation.
Unchanged: Phase 2 parsers/transport internals, the M8 search pipeline, CI,
mock-first defaults, Alliance opt-in gates.

## Security review

- **No client URL/path input surface**: discovery takes a charset/length-
  constrained ref that the provider re-validates strictly (digits-only for
  Alliance; URL/path shapes are rejected at the API surface with 422);
  download takes only an authenticated-encrypted token. SSRF surface: none.
- **Tokens are confidential and fail closed**: the ciphertext contains the
  encrypted provider binding and source reference — nothing is recoverable
  by decoding (tested). Fernet decrypt-and-validate enforces authenticity
  plus issued-at/TTL; malformed, tampered, expired, future-issued,
  wrong-secret and wrong-provider tokens all → the same 404,
  indistinguishable from a missing document. Production refuses token
  operations (503) without a valid configured secret.
- **Defense in depth at fetch time**: even a successfully decrypted path
  must match
  the provider's document-path pattern (`/manuals/<seg>/<file>.pdf`,
  dot-only segments impossible), then pass the live gates, host allowlist,
  URL policy, rate limits, size caps, and Content-Type + `%PDF-` validation.
- **Backend-only authentication** preserved: session gates run before every
  live document fetch, exactly as for search.
- **Leak-free responses/logs**: fixed detail strings; exception class names
  only in logs; filenames sanitised to a strict pattern or a constant.
- **No persistence, no caching** (`Cache-Control: no-store`), no background
  work; CI remains fully offline.

## Test summary

**368 backend tests passing (51 new)**, all offline; mobile analyze clean +
33 mobile tests passing. New coverage: token round-trip/opacity/tampered/
malformed/wrong-provider/wrong-secret/ephemeral-secret; discovery schema and
metadata; unavailable documents carry no token; no-provider-internals marker
scan (mock and Alliance fixture responses); invalid reference (400) and
URL-shaped ref rejected at the surface (422); unknown provider (404);
capability-unsupported (400); discover→download round trip
(`application/pdf`, `%PDF-`, `no-store`); filename sanitisation; tampered/
malformed token (404); provider-bound token (404); `DocumentNotFound` (404);
`ReauthenticationRequired` (503); `ProviderForbidden` (502);
`InvalidDocumentContent` (502); transient provider failure (502) with no
exception text leaked; Alliance reference/path validation rejects URLs,
paths, traversal (`..`) and over-length ids **without any fetch**; M8 search
contract unchanged.

## Risks

- **Token lifetime is a trade-off**: 15 minutes (configurable) bounds a
  leaked token's useful life while comfortably covering discover → tap →
  download; tokens confer no authority regardless — every download
  re-passes provider gates — and secret rotation invalidates everything
  outstanding. Recorded in ADR 0014.
- **Bytes are buffered, not chunk-streamed**, bounded by the 100 MB cap;
  observed documents are ~0.4 MB. A streaming pass-through is a recorded
  future improvement, deliberately not a Phase 3 redesign.
- **Ephemeral dev secret**: without `DOCUMENT_TOKEN_SECRET`, tokens die with
  the process (harmless: rediscovery re-mints them); production deployment
  must set the secret — noted in configuration comments.

## Live validation — PERFORMED 2026-08-02 ✅

One supervised operator run of the real API (local uvicorn, session mode,
fresh operator bootstrap, generated ≥32-char token secret). Results,
sanitised:

1. **Discovery** (`GET /providers/alliance/documents?ref=<known manual>`):
   HTTP 200, **7 documents** (matching the Phase 2 validation and the
   portal's own count) with correct metadata, `data_origin=live`, and a
   token on every downloadable document.
2. **Download** (D0568 Technical Mnl via its token): HTTP 200,
   **420,607 bytes** — byte-for-byte the Phase 1 browser observation and
   Phase 2 provider validation — `content-type: application/pdf`,
   `content-disposition: inline; filename="D0568.pdf"`,
   `cache-control: no-store`, body begins `%PDF-`.
3. **Tampered token** (one character altered): generic
   `404 {"code": "not_found", "message": "Document not found."}` — no hint
   that the token (rather than the document) was the problem.
4. **Leak scan**: the discovery JSON contains no Alliance hostname, path,
   `ManualId`, `ModelId`, or `source_path`; base64-decoding all seven
   issued tokens yields ciphertext only — no path, provider, filename, or
   payload structure recoverable.

Also exercised against production en route: the expired-session case — the
API returned the leak-free 503 "Provider session requires reauthentication"
(class name only in logs) before the operator re-bootstrapped. Operational
note for the mobile milestone: portal sessions expire on the order of
hours-to-days, so the reauthentication state will be a routine part of the
technician experience and the operator re-bootstrap is its recovery path.

### Original plan (for reference / future re-validation)

One supervised operator run of the deployed/local API in session mode:
discovery for a known model (expect the Phase 2-validated document list via
the API), one download (expect byte count to match Phase 2's 420,607 for
D0568), one tampered token (expect 404). Never in CI.

## Recommendation

Ready for review as one focused Phase 3 PR. After merge + the short live
API validation, the backend supports the complete technician workflow and
the next milestone (first Android internal-testing build: search → results
→ open manual → read PDF) can begin against a stable API.
