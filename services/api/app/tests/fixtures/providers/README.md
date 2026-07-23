# Provider response fixtures

Recorded provider responses used by connector tests. Policy (ADR 0011):

- CI and local test runs must NEVER call a live provider service. Every
  connector test — including the shared `ConnectorContract` suite — runs
  against fixtures in this directory.
- Layout: `fixtures/providers/<provider_id>/<name>.json`, loaded via
  `app.tests.provider_fixtures.load_provider_fixture`.
- Fixtures must be SANITISED before committing: no session cookies, tokens,
  account identifiers, personal data, or any content the provider's terms
  do not permit storing. Strip volatile headers; keep only the response
  shapes the connector parses.
- Record the capture date and source endpoint in a `_meta` key so stale
  fixtures are identifiable.
- Live-service integration tests (if ever added) are opt-in, run manually
  outside CI, and take credentials only from the environment.
