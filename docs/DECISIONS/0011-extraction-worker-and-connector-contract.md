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

## Addendum (2026-07-23, pre-merge review of PR #2)

Review required a worker-lifecycle and protocol-hardening pass:

1. **Cleanup on every abnormal parent exit.** The child is killed and
   reaped in a `finally` block covering timeout, asyncio cancellation, and
   unexpected parent errors; `CancelledError` re-raises unchanged. Test-
   proven: cancelling the parent of a deliberately hung child returns
   promptly, and the child is verified dead with no zombie via ps/pgrep.
2. **Strict protocol validation.** `_parse_worker_output` type-checks every
   field (object top level, boolean `ok`, list of object pages with string
   `text` and boolean `truncated`, known `reason` enum, string `detail`).
   A 15-case malformed-output matrix proves every bad shape — including
   ones that previously produced `TypeError` — becomes
   `ExtractionError(UNREADABLE)`. Unexpected extra fields are deliberately
   ignored for forward compatibility.
3. **Aggregate text cap.** `max_total_text_chars` (default 5M) stops
   extraction with a typed `total_text_too_large` error, bounding the
   whole-document materialisation AND the cross-process JSON payload
   (which duplicates text in child strings, child JSON buffer, parent
   stdout bytes, parsed dicts, and final objects). The single-object JSON
   protocol is documented as suitable only within this bound; streamed
   NDJSON or a temporary result file plus staged storage is the future
   path for larger manuals.
4. **Test hang hook isolated.** The hook is now an explicit child CLI
   argument forwarded only by tests (`_test_hang_seconds`); the worker
   never reads it from the environment, and a test proves a stray
   `LC_EXTRACTION_TEST_HANG_SECONDS` service variable is ignored.
