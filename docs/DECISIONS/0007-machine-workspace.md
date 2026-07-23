# ADR 0007: Machine workspace shape

- Status: accepted
- Date: 2026-07-23

## Context

Milestone 6 delivers the machine workspace: backend machine/document
endpoints plus the mobile detail screen, recents, and bookmarks.

## Decisions

1. **Workspace is served from the internal catalog** (Milestone 4 schema),
   not from live provider fan-out. Search finds things across providers; the
   workspace shows what the catalog knows about a machine. An idempotent
   sample-data seed (`python -m app.database.seed`) populates the catalog
   with the mock provider's dataset — clearly labelled, mirroring the mock
   connector — until real ingestion (M7/M8) replaces it.
2. **Search → workspace linking is by model number.** Search results carry
   no catalog ids (they come from providers); tapping a result looks up
   `GET /api/v1/machines?model_number=...`. No match → honest "No workspace
   available yet" message, not an empty fake workspace.
3. **Documents grouped by `document_type`** with a mobile-side label map
   (service_manual → "Manuals", parts_manual → "Parts & Exploded Diagrams",
   ...). Categories stay data-driven; unknown types render with a derived
   label instead of being dropped.
4. **Recents and bookmarks are on-device only** (shared_preferences), capped
   at 10 recents, stored as machine summaries so they render without a
   network call. This is the bookmarks *foundation*: when technician
   accounts arrive, the store becomes a cache in front of server-side sync.
   No user system was built for this — deliberate scope control.
5. **Document tiles have no tap action yet.** The document viewer is
   Milestone 7; a dead-end tap or a fake viewer would be worse than none.

## Consequences

- M7 document search plugs into the workspace by making document tiles
  navigate to a viewer/page-search screen.
- Serial-range-specific workspaces need only a lookup parameter change
  (`serial` → machine) — the schema already anticipates it.
