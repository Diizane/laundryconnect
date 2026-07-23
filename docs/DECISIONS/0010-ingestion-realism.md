# ADR 0010: Ingestion realism — memory model, limits, isolation

- Status: accepted
- Date: 2026-07-23

## Context

Pre-Milestone-8 review flagged inaccuracies and gaps in the extraction/
ingestion story that must be settled before any live provider documents
are processed.

## Decisions

1. **Honest memory model.** `extract_page_texts` yields pages lazily, but
   `ingest_pdf_pages` MATERIALISES all extracted page text in memory before
   replacing database rows — the deliberate price of the extract-before-
   delete safety guarantee (ADR 0009). The end-to-end ingestion path is NOT
   memory-streaming and documentation no longer claims it is. Page-level
   applies to storage, search, and serving.
2. **Conservative limits sized for commercial-laundry manuals** (observed
   service/parts/installation manuals run well under 500 pages):
   100 MB file, 1,500 pages, 20,000 chars/page — worst-case materialisation
   ~30M characters (~60 MB), versus ~150M under the previous limits.
   **Manuals beyond these limits get a staging-table strategy, not bigger
   limits:** extract in bounded batches into a `document_pages_staging`
   table within the ingestion transaction, then swap staged rows for
   current rows atomically. Planned, not built — no manual has needed it.
3. **The extraction timeout is cooperative, not enforceable.** It is checked
   between pages and cannot interrupt a hung `page.extract_text()` call.
   Documented at the constant and in code. **Hard requirement before
   accepting arbitrary uploads or live provider documents (M8):** run
   extraction in an isolated worker process with a hard wall-clock timeout
   and OS resource limits; the API/ingestion job supervises and receives a
   typed result.
4. **Filesystem failures are typed.** Missing files (`file_not_found`),
   non-regular files (`not_a_file`), and stat/open permission errors
   (`file_access`) all raise `ExtractionError`; raw `OSError` never leaks.
5. **Truncation is observable.** Pages cut at the per-page cap are flagged
   (`document_pages.truncated`, migration `8c2e5f7a1b4d`), logged with
   original size, counted in ingestion logs, and exposed in the page API —
   truncated text must never silently masquerade as complete in search
   results or future RAG citations.

## Consequences

- M8 ingestion inherits accurate constraints: bounded memory, typed
  failures, visible truncation, and a documented escape hatch for oversized
  manuals.
- The worker-process isolation requirement is an explicit M8 entry item for
  any pipeline touching untrusted or provider-supplied files.
