# Provider Connector Architecture

> Status: **framework implemented (Milestone 2)** — base interface, registry,
> fan-out search with timeouts/partial failure, and a mock connector. No real
> provider connectors exist yet (Milestone 8 onwards).

## Goals

- Every provider (Alliance Laundry Systems, Girbau, Richard Jay Service,
  future providers) is integrated behind one stable interface.
- Adding a provider never changes the core search system.
- One provider failing, timing out, or being disabled never breaks search.
- Mock connectors make local development and automated tests independent of
  real provider accounts.
- Mock/demo/manual data is always labelled as such — never presented as live.

## Implemented

### Base interface — `app/providers/base.py`

`ProviderConnector` (async ABC): class-level `provider_id`, `display_name`,
`data_origin`; methods `search(query, query_type)`, `health_check()`, and
`validate_credentials()` (default: no credentials required).

Deliberately small for now: document/part/model retrieval methods
(`find_model`, `find_documents`, `find_parts`, `fetch_document_metadata`,
`fetch_document`, `authenticate`/`refresh_session`) join the interface in
Milestones 6–8 when the features that consume them exist — no dead stubs.

### Normalised result — `app/providers/models.py`

`ProviderResult` carries: `provider_id`, `source_reference`, `result_type`
(document/part/model/bulletin/diagram/fault_code), `data_origin`
(**mock/manual/live/cached** — every result is honestly labelled),
machine association (`manufacturer`, `brand`, `model`, `serial_range`),
presentation (`title`, `description`, `document_type`), plus `part_number`,
`revision`, `published_at`, `source_url`, `access_method`, `metadata`,
`relevance_score`.

### Registry and fan-out — `app/providers/registry.py`

- `ProviderRegistry.register/get/all`; duplicate ids rejected.
- `build_registry(settings)` constructs connectors from `ENABLED_PROVIDERS`;
  unknown ids fail fast at startup.
- `search_all(query, query_type, timeout_seconds)` runs all providers in
  parallel via `asyncio.gather`, each wrapped in its own
  `asyncio.wait_for` timeout, and returns `AggregatedSearch`: combined
  results plus a `ProviderOutcome` per provider
  (success / failed / timed_out / disabled, latency, result count).
- Partial failure is first-class: a failing provider is reported, never
  propagated. Outcome `error` carries only the exception class name —
  messages could contain sensitive provider material and are logged
  server-side only.

### Mock connector — `app/providers/mock/`

Fixed, clearly-labelled sample dataset (Speed Queen SC60, Girbau HS-6008:
manuals, a part, a fault code). Presents as "Mock Provider (sample data)",
all results `data_origin=mock`. Constructor accepts fault-injection
parameters (`latency_seconds`, `fail_with`) so timeout and partial-failure
paths are tested deterministically.

### Status endpoint

`GET /api/v1/providers/status` health-checks each registered provider with a
timeout and returns operational metadata only — never credentials, sessions,
or raw provider responses.

## Security constraints

- Provider authentication happens only on the backend.
- Credentials come from environment/secret manager (see
  [SECURITY.md](SECURITY.md)); never stored in the mobile client, never
  exposed through the API.
- Connectors must not embed secrets in exception messages.
- Connectors must comply with provider terms; no unauthorised scraping or
  access-control bypasses.

## Testing strategy

- Connectors are independently testable; the mock connector drives CI.
- Automated tests never depend on real provider accounts.
- Registry tests cover success, partial failure, timeout, disabled providers,
  duplicate registration, and configuration typos.
- Real-provider integration tests (Milestone 8) will run separately, opt-in,
  with credentials injected from the environment.

## Adding a real provider (Milestone 8 checklist)

1. Document the provider's authentication approach and terms compliance.
2. Implement a connector package under `app/providers/<provider>/`.
3. Register its class in `PROVIDER_FACTORIES`.
4. Keep all normalisation inside the connector.
5. Add connector tests with recorded/mocked responses (no real accounts).
6. Enable via `ENABLED_PROVIDERS` per environment.

## Alliance connector — human-in-the-loop auth (Milestone 8, ADR 0012)

The first real connector (`app/providers/alliance/`) proves the
architecture without any agent handling credentials and without live
requests while access is UNKNOWN:

- **fixture mode** (default, CI, dev): sanitised recorded/synthetic
  fixtures, no network, passes `ConnectorContract`; results labelled
  `DataOrigin.FIXTURE` (never presented as live).
- **session mode**: loads a human-bootstrapped browser session from
  `ALLIANCE_SESSION_PATH`; missing/invalid/expired → `reauthentication_
  required` outcome. A live fetch is double-gated on
  `alliance_access_approved` AND not-CI, and the reviewed live transport is
  unimplemented until the access record is approved.
- **credential mode**: refused — terms do not permit automated login;
  credentials are never read from files, args, the API, or source.
- **operator tools** (never CI): `python -m app.providers.alliance.bootstrap`
  (visible-browser manual login → session file outside the repo, `0600`)
  and `sanitise_capture` (strips cookies/tokens/usernames/account data/
  signed URLs before fixtures are committed; human review required).

Session contents and credentials are never logged, returned, or stored as
attributes; security tests assert repr/log safety, that CI cannot enter
live mode, that repo-path sessions are rejected, and that expired sessions
report `reauthentication_required`.
