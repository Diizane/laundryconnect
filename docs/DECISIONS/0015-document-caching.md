# 0015 — Server-side document caching (revalidating, not archiving)

Date: 2026-08-08
Status: accepted — supersedes the "no caching, no persistence" constraint
in ADR 0013/0014 for **documents only**.

## Context

Milestones 9–10 deliberately cached nothing: the provider terms behind the
Alliance login were unreviewed, and transient access was the conservative
choice. Field use since then changed the calculus:

- Every document open costs three sequential provider requests, over a
  trans-Pacific link.
- When the operator session expires — routinely, and unpredictably mid-job
  — the technician loses access to manuals they have already opened.

The business owner, an authorised Alliance service partner, states they
have full rights to download manuals through the platform, and that
LaundryConnect should be able to do the same. On that basis, storing
copies of documents the operator is already entitled to download is
accepted as within their access. **Owner-asserted, as with the original
access decision; not written provider permission** — the standing
recommendation to obtain explicit service-partner terms still applies
(see docs/PROVIDER_ACCESS/alliance-laundry-systems.md).

## Decision

Cache **documents only** — never search results, which change constantly
and would send technicians to the wrong machine.

Crucially this is a **revalidating cache, not an archive**. Manuals are
revised; a technician following a superseded procedure (torque figures,
wiring, fault codes) is a safety problem, not merely a correctness one.
Permission to store copies does not make stale copies safe, so:

1. **Every hit is revalidated.** The stored `ETag`/`Last-Modified` (which
   Alliance supplies — observed in the Phase 1 capture) are sent as
   `If-None-Match`/`If-Modified-Since`. A **304** serves the stored copy
   with no body transfer; a **200** means the provider revised it and the
   new version replaces ours.
2. **Unvalidated copies are served only when the provider cannot answer**
   — expired session, outage, transport failure. This is the case that
   keeps technicians working mid-job.
3. **Honest labelling.** Such responses carry `X-Document-Origin: cached`
   and `X-Document-Age-Seconds`, consistent with the project's rule that
   mock/fixture/cached data is never presented as live.
4. **A staleness ceiling.** Past `DOCUMENT_CACHE_MAX_STALE_SECONDS`
   (default 90 days) without a successful revalidation, a copy is refused
   rather than silently trusted.
5. **Definitive answers are never masked.** `DocumentNotFound` and
   `InvalidDocumentContent` propagate: "this document is gone" must not be
   papered over with an old copy.

Storage is content-addressed by (provider, source path) — the key is a
hash, so paths are not exposed on disk — written 0600, size-capped with
LRU eviction (default 2 GB; manuals are ~0.4 MB).

**Off by default** (`DOCUMENT_CACHE_ENABLED=false`), like every other live
behaviour. Disabled, the fetcher is a pass-through and the pre-cache
behaviour is exactly preserved.

## Consequences

- Repeat opens are instant and survive session expiry — directly reducing
  the operational pain that motivated the request.
- Provider load falls sharply: revalidation is header-only.
- The client contract is unchanged apart from two response headers; the
  app can surface "cached, N days old" without an API redesign.
- The kill switch and per-environment opt-in still gate all live access.
- A future consideration deliberately not taken now: pre-warming the cache
  by fetching documents nobody has asked for. That would be bulk
  retrieval, which every prior ADR rules out, and it should stay ruled out
  until there is written provider permission.
