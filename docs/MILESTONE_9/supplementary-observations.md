# Milestone 9 — Supplementary observations (future roadmap inputs)

Recorded 2026-07-26 during a second supervised, bounded portal session (an
operator-driven "find the drive belt" workflow simulation — a handful of
page views, one drawing, no bulk retrieval; account identifiers redacted).
These are **documentation only**: none of them expands Milestone 9 scope.
Each is a candidate for a future roadmap item.

1. **Serial-number search is a first-class portal endpoint.**
   `/en/Search/BySerial?searchString=<serial>&x.Show=Assembly` resolves a
   machine serial to its **exact factory configuration** (e.g. a full
   configured model string), not just a model family, and returns the same
   results-table shape as the model search. Maps directly onto the existing
   `QueryType.SERIAL`; wiring it into the Alliance connector's live search is
   a small future enhancement.

2. **Assembly drawings are interactive HTML pages, not PDFs.**
   `/en/Manual/Drawing?Index=…&DrawingId=…&ManualId=…&ModelId=…` renders a
   zoomable exploded diagram with a Ref → Part callout table alongside. A
   "Printer Friendly Drawing" variant exists at `/en/Manual/DrawingPrint`
   (and a whole-manual `/en/Manual/DrawingsPrint`), which is presumably the
   printable/PDF form — **to be confirmed by observation before any
   implementation** (same discipline as Phase 1; do not assume).

3. **Per-manual part filtering.** `/en/Manual?...&partSearch=<part>` filters
   the manual's drawing list to only drawings containing that part — e.g.
   filtering by a belt part number returned exactly one drawing ("Drive").
   Enables a future "where is this part used?" feature.

4. **Parts lists carry live distributor pricing.** `/en/Model/Parts?...`
   returns several hundred rows of part number / description / price for a
   model. Parts and pricing are a separate product dimension (future
   milestone; requires its own scope and terms review before any
   implementation).

Validated end-to-end during the same session: serial → exact machine →
part-filtered drawing → belt identified (part number + price + drawing
callout) — the precise technician workflow LaundryConnect exists to
streamline.
