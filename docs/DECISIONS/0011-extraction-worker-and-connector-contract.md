# ADR 0011: Isolated extraction worker and connector contract harness

- Status: accepted
- Date: 2026-07-23

## Context

Milestone 8 entry conditions (ADR 0010, roadmap checklist) require a
genuinely enforceable extraction timeout before touching provider files,
and fixture-driven connector tests that never call live services in CI.

## Decisions

1. **Subprocess isolation, not threads or task groups.** Extraction for
   untrusted/provider files runs in a child process
   (`python -m app.documents.worker`). Only a process can be killed
   mid-`extract_text()`; the async parent (`extract_pages_isolated`)
   enforces a hard wall-clock deadline (cooperative limit + 30s grace by
   default) and `kill()`s on breach — verified by a test that a child hung
   for 30s is dead in under 10.
2. **Child self-applies OS resource limits** (1 GiB address space, CPU cap
   slightly above the cooperative budget). Best-effort on macOS dev
   machines, enforced on Linux — the container platform. A test-only hang
   hook (`LC_EXTRACTION_TEST_HANG_SECONDS`) exists solely to verify the
   kill path.
3. **One JSON object on stdout is the whole protocol.** Typed
   `ExtractionError` reasons round-trip through it; crashes, OOM-kills, or
   garbage output become `unreadable`. Raw child failures never escape.
4. **The in-process path remains** for trusted local content (seed,
   committed fixtures); `ingest_pdf_pages(..., isolated=True)` selects the
   worker and is REQUIRED for provider-supplied files.
5. **`ConnectorContract` is the acceptance bar for every connector.**
   A shared test suite (identity declared, normalised results with
   mandatory source traceability, empty-not-error on unknown queries,
   health reporting, credential validation, log-safe repr) that each
   provider's tests subclass. The mock connector passes it today; a real
   connector is not done until its fixture-driven subclass passes.
6. **Fixture policy** (fixtures/providers/README.md): recorded, sanitised
   responses only; capture metadata required; CI never calls a live
   provider; live integration tests are manual, opt-in, environment-
   credentialed.

## Consequences

- The first real connector implements `ProviderConnector`, records
  sanitised fixtures, subclasses `ConnectorContract`, and uses
  `isolated=True` ingestion — the architecture-proof checklist is now
  executable, not aspirational.
- A future job queue can reuse the worker protocol unchanged (it is
  already a self-contained CLI).
