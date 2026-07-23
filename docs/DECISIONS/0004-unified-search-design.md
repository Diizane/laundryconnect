# ADR 0004: Unified search design

- Status: accepted
- Date: 2026-07-23

## Context

Milestone 3 delivers `POST /api/v1/search` — the primary product experience.
It composes the Milestone 2 provider fan-out with query understanding and
result shaping.

## Decisions

1. **Heuristic, transparent query-type detection.** Ordered regex/shape rules
   (`app/search/detection.py`), not ML. Known misclassifications exist
   (letter-only fault codes like "EdL" read as models). Mitigations: the
   response echoes `detected_query_type` so clients can show and let the
   technician correct it, and an explicitly requested type always wins.
2. **Grouped response, machine-first.** Results are returned grouped by
   (manufacturer, brand, model) — matching the machine-workspace product
   vision — with a final "other" group for unassociated results. No separate
   flat list: one representation, ranked within and across groups.
3. **Deduplication before ranking.** Identity is `source_url` when present,
   else (result_type, model, normalised title, revision). Highest-scoring
   duplicate wins; a `duplicates_collapsed` metadata count keeps the collapse
   visible rather than silent.
4. **Ranking = provider relevance + exact-identifier boost.** Exact model or
   part-number matches get +0.2 (capped at 1.0) so identifier searches
   surface the identified item first. Deliberately simple until real
   providers give better signals.
5. **Cache-ready by shape, no cache yet.** `SearchService.execute` is a pure
   (request → response) function over the registry, so a future cache wraps
   it keyed on (query, query_type) without touching search logic. No cache
   implementation until there is a real latency problem to solve.
6. **Search queries are not logged** — serial numbers can identify customer
   sites. Logs carry query type, result count, and failed provider ids only.

## Consequences

- Milestone 5's Flutter app renders groups directly; badges come from
  `data_origin`, `provider_id`, and `document_type` already in the payload.
- Detection quality can improve independently (rules or model) behind the
  same response contract.
- When document search (M7) lands, document-page results join the same
  normalised result model rather than a parallel schema.

## Bug fixed en route

The 422 handler serialised raw `exc.errors()`, which can contain live
exception objects in `ctx` — this 500'd on custom validator failures. Details
are now passed through `jsonable_encoder` (regression-tested).
