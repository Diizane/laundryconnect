# ADR 0003: Provider connector framework shape

- Status: accepted
- Date: 2026-07-23

## Context

Milestone 2 introduces the interface every provider integration will live
behind. This is the most architecture-critical seam in the product: it must
survive real connectors (Alliance, Girbau, Richard Jay) without core changes.

## Decisions

1. **Minimal interface now.** `ProviderConnector` exposes only `search`,
   `health_check`, and `validate_credentials`. Document/part retrieval
   methods are added when the consuming features exist (M6-M8) — no dead
   stubs that look production-ready but aren't.
2. **`data_origin` on every result** (`mock`/`manual`/`live`/`cached`), plus
   a mock connector that names itself "Mock Provider (sample data)". Honest
   labelling is enforced by the data model, not by convention.
3. **Registry-level resilience.** Timeouts and exception handling live in
   `ProviderRegistry.search_all`, not in connectors, so no connector can
   break the fan-out. Partial failure is a first-class per-provider outcome.
4. **Exception class name only in API-visible outcomes.** Provider error
   messages may embed sensitive material (URLs with tokens, response
   bodies), so outcomes expose `type(exc).__name__` and full details go to
   server logs only.
5. **Fail-fast configuration.** `build_registry` raises on unknown ids in
   `ENABLED_PROVIDERS`; a typo should be a startup error, not a silently
   missing provider.
6. **Fault injection in the mock connector** (`latency_seconds`,
   `fail_with`) so timeout/partial-failure paths are deterministic in CI
   rather than relying on real network behaviour.

## Consequences

- Milestone 3's unified search composes `search_all` and adds query-type
  detection, dedup, ranking, and grouping on top — no registry changes
  expected.
- Real connectors implement the same class and register in
  `PROVIDER_FACTORIES`; enabling them is pure configuration.
- The interface will grow in reviewed increments (new ADR or PR note when
  retrieval methods are added).
