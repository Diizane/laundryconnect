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

A signed, versioned token: `v1.<base64url(payload)>.<base64url(hmac)>`,
where the payload is the minimum for the immediate request —
`{"p": provider_id, "s": provider-local source path}` — and the signature
is **HMAC-SHA256** (Python stdlib `hmac`/`hashlib`; no custom
cryptography) over the version + payload, compared in constant time.

- **No persistence**: tokens are stateless; no table, no cache.
- **Lifetime**: bounded by the signing secret (`DOCUMENT_TOKEN_SECRET`);
  rotating the secret invalidates all outstanding tokens. No embedded
  expiry — a token grants nothing by itself: every download still passes
  the provider's live gates, host allowlist, path validation, rate limits
  and content validation at fetch time. When the secret is unset, an
  ephemeral per-process secret is used (dev/tests); production sets it.
- **Tampering fails closed**: any structural, signature, version, payload
  or provider-binding failure raises one error, mapped to **404** —
  indistinguishable from a missing document (chosen over 400 as the
  less-leaking response). Tokens are provider-bound: a token minted for one
  provider never resolves for another.

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
- Token statelessness means no cleanup jobs and no storage; the trade-off
  (no per-token expiry) is acceptable because tokens confer no authority —
  the backend re-gates every fetch.
