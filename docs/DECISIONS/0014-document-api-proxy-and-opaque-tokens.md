# 0014 — Document API: backend proxy with signed opaque tokens

Date: 2026-07-30
Status: accepted

## Context

Milestone 9 Phases 1–2 produced a live-validated provider capability
(`discover_documents` / `fetch_document`) and settled — from evidence (ADR
0013; Phase 1 Q11) — that the backend must proxy document bytes: documents
are session-protected, the mobile client has no provider session, and
provider URLs must stay private. Phase 3 exposes that capability through a
narrowly scoped backend API without weakening any Phase 2 guarantee.

## Decision

### Endpoint shapes

- `GET /api/v1/providers/{provider_id}/documents?ref=<reference>` —
  discovery. Returns client-safe metadata (title, document type, part
  number, comment, languages, category, filename, availability,
  data_origin) plus an opaque `token` per downloadable document.
- `GET /api/v1/providers/{provider_id}/documents/{token}` — download proxy.
  Resolves the token server-side, fetches via the provider, and returns
  `application/pdf` bytes with a sanitised `inline` filename and
  `Cache-Control: no-store`.

### Opaque identifiers

> Revised during PR #13 review: the first design was an HMAC-signed
> base64url JSON payload — tamper-proof but **readable** (base64 is
> encoding, not encryption), contradicting the guarantee that provider
> paths never reach the client. Replaced with authenticated encryption.

Tokens are **Fernet** tokens from the maintained `cryptography` library —
AES-128-CBC with an HMAC-SHA256 authenticator and an embedded issued-at
timestamp; a standard primitive, no custom cryptography. The encrypted
payload is the minimum for the immediate request:
`{"p": provider_id, "s": provider-local source path}`. The Fernet key is
derived from `DOCUMENT_TOKEN_SECRET` with **HKDF-SHA256**.

- **Genuinely opaque**: the payload is encrypted; base64-decoding a token
  yields ciphertext only (tested: no path, provider, filename, or JSON
  structure is recoverable).
- **Expiry**: tokens embed their issued-at time and expire after
  `DOCUMENT_TOKEN_TTL_SECONDS` (default **900 s / 15 minutes** —
  discover → tap → download comfortably fits). Future-issued timestamps
  beyond Fernet's 60 s clock-skew allowance are also rejected.
- **No persistence**: tokens are stateless; no table, no cache.
- **Secret rotation**: rotating `DOCUMENT_TOKEN_SECRET` invalidates every
  outstanding token immediately (clients simply rediscover).
- **Production configuration is enforced**: with no secret (or one shorter
  than 32 characters) in `ENVIRONMENT=production`, document-token
  operations **refuse with 503** — the API never silently degrades to an
  ephemeral process secret. The ephemeral fallback exists only for
  development and tests (tokens then die with the process; harmless).
- **Everything fails closed identically**: malformed, truncated, tampered,
  expired, future-issued, wrong-secret and wrong-provider tokens all
  produce the same **404**, indistinguishable from a missing document
  (chosen over 400 as the less-leaking response).
- Defence in depth stands regardless: a token grants nothing by itself —
  every download still passes the provider's live gates, host allowlist,
  path validation, rate limits and content validation at fetch time.

### No client-controlled URL/path surface

- Discovery input is a short `ref` (charset/length-constrained at the API,
  then strictly validated by the provider — Alliance accepts only
  `<digits>:<digits>` and builds its `/en/Manual` URL server-side).
- Download input is only the signed token; the provider additionally
  validates the decoded path shape (Alliance: `/manuals/<seg>/<file>.pdf`,
  segments starting alphanumeric so `..` cannot match) before any fetch.
- Clients therefore cannot submit URLs or paths at all — SSRF surface: none.

### Provider abstraction

`ProviderConnector` gains default `discover_documents` / `fetch_document`
methods raising `ProviderDocumentsUnsupported` (stable domain outcome →
400), so the route is provider-agnostic and unsupported providers never
crash. Alliance implements the contract on its validated Phase 2 internals;
the mock provider ships fixture-backed sample documents (one deliberately
non-downloadable) so the full API contract tests run offline with mock as
the default.

### Error mapping (leak-free)

| Domain error | HTTP |
|---|---|
| `DocumentNotFound` | 404 |
| invalid/tampered/malformed/wrong-provider token | 404 (identical to missing) |
| `InvalidDocumentReference` | 400 |
| `ProviderDocumentsUnsupported` | 400 |
| unknown or disabled provider | 404 (indistinguishable) |
| `ReauthenticationRequired` | 503 (operator re-bootstrap; client retries later) |
| `LiveModeRefused` | 503 |
| `ProviderForbidden` | 502 |
| `InvalidDocumentContent` | 502 |
| other `ProviderError` (timeouts, 5xx, caps) | 502 |

Response bodies carry fixed detail strings; raw exception text, upstream
URLs and provider hostnames never appear. Logs carry the exception class
name only.

### Bytes vs streaming

The validated Phase 2 provider contract returns bounded bytes (documents
are capped at 100 MB and validated before return; the observed manual was
~411 KB). Phase 3 deliberately proxies those bytes rather than redesigning
the proven transport for chunked pass-through. If field usage shows large
documents where buffering matters, a streaming pass-through (validating the
prefix, then chunk-forwarding) is recorded as a candidate future
improvement — it must preserve the existing size caps and validation
ordering.

### Filename behaviour

`Content-Disposition: inline; filename="<name>"` where the name is the
provider filename only if it matches a strict safe pattern
(`[A-Za-z0-9._-]+\.pdf`), else the constant `document.pdf`. Never
client-influenced, never path-bearing.

## Consequences

- The mobile client's entire document surface is two backend endpoints; it
  never sees or constructs an Alliance URL, and Alliance authentication
  stays server-side.
- Future providers implement two connector methods and inherit the API,
  tokens, and error contract unchanged.
- Token statelessness means no cleanup jobs and no storage; the 15-minute
  expiry bounds the useful life of a leaked token, and tokens confer no
  authority regardless — the backend re-gates every fetch.
- The API grows one dependency (`cryptography`), already ubiquitous in
  Python deployments.
