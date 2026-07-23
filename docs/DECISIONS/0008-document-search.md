# ADR 0008: Document search and page-level indexing

- Status: accepted
- Date: 2026-07-23

## Context

Milestone 7 delivers in-document search: page-level text storage, a search
endpoint whose hits cite (document, page), and the first mobile document
viewing experience.

## Decisions

1. **Pages are the unit of storage, search, and serving.** `document_pages`
   holds extracted text per page; search and page retrieval never load a
   whole manual. This is also the retrieval granularity future RAG citations
   need (document + page number).
2. **Portable ILIKE substring search for now.** SQLite-compatible, correct,
   and sufficient for seeded sample pages. The trigger to move to PostgreSQL
   full-text (tsvector + GIN index) — and to add a PostgreSQL job to CI — is
   the first real ingested manual (M8), not this milestone.
3. **PDF extraction via pypdf, page-lazy, fault-tolerant.** One unreadable
   page logs a warning and yields empty text rather than sinking the manual;
   a non-PDF raises a typed `ExtractionError`. Tested against a committed
   933-byte fixture PDF, not real provider files.
4. **Extraction and ingestion are decoupled.** `extract_page_texts` is a pure
   function; `DocumentRepository.replace_pages` swaps a document's indexed
   pages atomically within the caller's transaction. The seed currently
   populates pages directly (clearly-labelled sample text) because no real
   PDFs may be committed; the extraction path is exercised by tests and waits
   for M8's compliant document fetching.
5. **Mobile shows extracted page text, not rendered PDFs.** The page screen
   presents indexed text with prev/next navigation and always shows the page
   number. Rendering original PDFs requires having the files (M8, subject to
   provider terms); a text view of real indexed content is honest — a broken
   embedded PDF viewer would not be.
6. **Snippets are server-built** (~80 chars of context around the first
   match, whitespace collapsed) so all clients cite identically and page text
   isn't shipped in search responses.

## Consequences

- M8 ingestion becomes: fetch document compliantly → `extract_page_texts` →
  `replace_pages` → same search/viewer works unchanged on real manuals.
- Multi-document search across a machine's manuals is a follow-up: the
  repository query generalises from one document id to a set.
