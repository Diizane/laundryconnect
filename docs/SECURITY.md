# Security Model

## Threat focus

The most sensitive assets are **provider credentials** (Alliance, Girbau,
Richard Jay, and future providers). Compromise would expose third-party
accounts the business depends on.

## Credential rules (non-negotiable)

- Secrets live in environment variables or a proper secret manager — never in
  the repository, never hardcoded.
- `.env` files are gitignored; only `.env.example` (placeholders) is committed.
- Provider credentials exist **only on the backend**. The Flutter app and the
  admin portal never receive provider passwords, session cookies, access
  tokens, or raw authentication responses.
- No plaintext credentials in PostgreSQL. If database storage becomes
  necessary (Milestone 8+), credentials are encrypted at rest and the design
  is documented in an ADR first.
- API responses never include secrets.
- Separate production and development credentials; least-privilege access.
- Any credential ever pasted into chat, a terminal, or a log must be treated
  as compromised and revoked.

## Logging redaction

Structured logging (`app/core/logging.py`) never logs passwords, tokens,
session cookies, or credential payloads. Defence in depth: any structured log
extra whose key contains `password`, `secret`, `token`, `cookie`,
`authorization`, `credential`, or `api_key` is replaced with `[REDACTED]` by
the formatter. This is a backstop — call sites must still never pass secret
values to the logger. Covered by tests (`test_logging.py`).

## API surface

- Structured error envelope; stack traces and internal exception details are
  never returned to clients (tested in `test_errors.py`).
- OpenAPI docs are disabled when `ENVIRONMENT=production`.
- Every response carries an `X-Request-ID` for auditable correlation.
- CORS is deny-by-default: no origins allowed unless explicitly configured.

## Authentication (current and planned)

- Current: none yet — the foundation has no data worth protecting and is not
  deployed. Internal authentication (simple, controlled, not hardcoded) is
  required before any deployment with real data.
- Planned: technician accounts, company membership, roles/permissions, and
  audit logs (see [DATA_MODEL.md](DATA_MODEL.md)). Admin routes will be
  separated and protected.

## Provider access compliance

Connectors must respect provider terms, licensing, and access controls. No
unauthorised scraping, no bypassing access controls, no misrepresenting mock
data as live provider data.
