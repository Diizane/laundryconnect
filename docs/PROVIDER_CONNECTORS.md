# Provider Connector Architecture

> Status: **design document**. Implementation begins in Milestone 2. No
> connectors (real or mock) exist yet.

## Goals

- Every provider (Alliance Laundry Systems, Girbau, Richard Jay Service,
  future providers) is integrated behind one stable interface.
- Adding a provider never changes the core search system.
- One provider failing, timing out, or being disabled never breaks search.
- Mock connectors make local development and automated tests independent of
  real provider accounts.
- Mock/demo/manual data is always labelled as such — never presented as live.

## Base interface (planned)

Each connector implements a common interface supporting:

- `authenticate` / `validate_credentials` / `refresh_session`
- `search(query, query_type)` — model, serial, part, fault code, keyword
- `find_model`, `find_documents`, `find_parts`
- `fetch_document_metadata`, `fetch_document`
- `health_check`
- result normalisation into internal models

## Normalised result model (planned)

Connectors return internal models, never provider-specific structures:

| Field | Notes |
| --- | --- |
| `provider_id` | Registry identifier |
| `source_reference` | Provider-side identifier for traceability |
| `result_type` | document / part / model / bulletin / ... |
| `manufacturer`, `brand`, `model`, `serial_range` | Machine association |
| `title`, `description`, `document_type` | Presentation |
| `part_number`, `revision`, `published_at` | Where applicable |
| `source_url`, `access_method` | How to reach the original |
| `metadata` | Provider-specific extras (typed dict) |
| `relevance_score` | For ranking |

## Registry and status

A provider registry tracks configured connectors, whether each is enabled, and
its health. Search fans out to enabled providers in parallel with per-provider
timeouts; the search response reports per-provider status (succeeded, failed,
timed out, cached).

## Security constraints

- Provider authentication happens only on the backend.
- Credentials come from environment/secret manager (see
  [SECURITY.md](SECURITY.md)); never stored in the mobile client, never
  exposed through the API.
- Connectors must comply with provider terms; no unauthorised scraping or
  access-control bypasses.

## Testing strategy

- Connectors are independently testable.
- A mock connector (clearly labelled) drives local development and CI.
- Automated tests never depend on real provider accounts.
- Real-provider integration tests (Milestone 8) run separately, opt-in, with
  credentials injected from the environment.
