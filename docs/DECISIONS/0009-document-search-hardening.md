# ADR 0009: Document search hardening

- Status: accepted
- Date: 2026-07-23

## Context

Overseer review required hardening Milestone 7 before any real provider
work: replacement safety, bounded search, snippet correctness, extraction
safeguards, text provenance, and source traceability.

## Decisions

1. **Page replacement is extract-first, transaction-bounded.**
   `ingest_pdf_pages` fully materialises extraction BEFORE touching existing
   pages; `replace_pages` deletes+inserts inside the caller's transaction and
   only flushes (deletes flushed before inserts to satisfy the unique
   page-number constraint). Any failure rolls back to the previous page set —
   proven by tests for extraction failure, insertion failure, and obsolete-
   page removal. Transaction ownership: the request-scoped session dependency
   (or the seed/test caller) commits; repositories never do.
2. **Search is bounded and deterministic.** Default limit 20, hard max 50
   (422 above it), results ordered by page number, and `total_hits` reports
   all matches so truncation is always visible. Offset-based pagination is
   the documented plan when real manuals need it. Query execution timing and
   result counts are logged (never query text).
3. **Literal matching everywhere.** LIKE wildcards (`%`, `_`, `\`) are
   escaped so ILIKE matches literally — the same case-insensitive substring
   semantics as the snippet builder, which also normalises whitespace on
   both sides. `build_snippet` returns `None` on a miss; the route logs a
   warning and emits a neutral placeholder rather than misleading fallback
   context. Repeated matches: first occurrence wins (documented).
4. **Extraction safeguards with typed errors.** `ExtractionError` carries a
   machine-readable reason: unreadable, encrypted, file_too_large (200 MB),
   too_many_pages (3000), timeout (300 s wall clock); page text truncates at
   50k chars. Raw pypdf exceptions never escape. All limits are
   test-exercised, including a real encrypted PDF.
5. **Text provenance per page.** `document_pages.text_source`:
   native_pdf / ocr / provider_supplied / manual_entry / seeded_sample.
   Exposed in page content and search hits; shown as a badge on the mobile
   page view.
6. **Document origin per record.** `documents.origin`: seeded_sample / live /
   uploaded / cached. Migration backfills existing rows as `seeded_sample`
   (nothing live has ever been ingested — backfilling as `live` would lie).
   Exposed in document detail, workspace document lists, and every search
   hit; mobile shows a SEEDED SAMPLE badge on every document tile.
7. **Search hits carry full citation data**: provider, source_reference,
   title, revision, origin, page number, text_source; document detail also
   lists associated model numbers.

## Consequences

- M8 real ingestion plugs into `ingest_pdf_pages` and simply passes
  `origin="live"` / `text_source="native_pdf"`; labelling is then automatic
  end to end.
- PostgreSQL full-text migration (tsvector) replaces the ILIKE internals of
  `search_pages` without changing its bounded, counted contract.
