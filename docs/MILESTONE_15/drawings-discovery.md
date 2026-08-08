# Milestone 15 — Interactive drawings: discovery

Status: **investigation complete; implementation scope recommended below.**
Observed 2026-08-08 against a live IA135 Drive drawing (the one used in the
burner-tube lookup).

The goal was "tap a reference number on an exploded diagram to get the
part". Discovery changes what is safely buildable, so it is recorded before
any code — the same order that caught the unsearchable-manual and
wrong-manual-generation problems.

## What a drawing actually is

`/en/Manual/Drawing?Index=…&DrawingId=…&ManualId=…&ModelId=…` returns a
1.29 MB HTML page containing an **inline SVG** (`7.74in × 9.71in`,
`viewBox 0 0 557.49 699.41`) plus the parts table beneath it.

Vector, not raster — which is better than expected for interactivity and
for rendering on a phone.

The SVG is **semantically grouped**:

| group id | contents |
|---|---|
| `parts` | the machine geometry |
| `misc_parts` | secondary geometry |
| `flow_lines` | flow indicators |
| `callouts` | the numbered markers and their leader lines |
| `HiddenViewBox` | layout helper |

Element counts: 152 `<g>`, 184 `<path>`, 2762 `<polyline>`.

Each callout is a group containing:

1. a leader `<line x1 y1 x2 y2>` from the part to the marker,
2. two `<path>`s forming the marker circle,
3. **one or more `<path>`s drawing the digits themselves**.

## The blocker: callout numbers are curves, not text

The SVG contains **zero `<text>` elements**. Callout numbers are CAD text
converted to outlines — e.g. the digit "1" is
`M25.54,159.74h-1.37v-5.17c-.5.47-1.09.…`.

So:

- ✅ callout **positions** are extractable (leader-line endpoints)
- ❌ callout **numbers** are not readable from the markup
- ✅ the parts table is fully extractable (19 rows, refs `1`–`19`, with part
  numbers and descriptions)

Mapping a tap to a part therefore needs one of:

- **Order assumption** — that callout groups are emitted in ref order.
  Plausible but *unverified*; a first attempt at counting top-level callout
  groups was inconclusive and needs a proper SVG parse.
- **Glyph recognition** — matching path outlines back to digits. Feasible
  (the digit paths look reusable across drawings) but fragile.

**Neither is safe to ship untested.** A wrong mapping means a technician
orders the wrong part — a real cost, in the same category as the wrong
manual generation and the stale document. Consistent with those decisions,
any mapping must be validated against several real drawings before it is
trusted, and should degrade to "unknown" rather than guess.

## Recommended scope

**Phase 1 — render drawings at all (high value, no risk).** The app
currently cannot show assembly drawings; a technician still has to use the
portal for the thing that most helps them. Serving the extracted SVG plus
the parsed parts table through the existing document endpoints gives:

- the exploded diagram, zoomable, on the phone
- the parts list beside it, searchable by description or part number
- no coordinate mapping, so nothing can be wrong

This alone covers most of the burner-tube workflow: find the drawing, read
the ref number off the diagram, find that ref in the list.

**Phase 2 — tap-to-part (needs validation first).** Extract callout
positions, establish the number mapping by whichever method survives
testing across several drawings, and only then make callouts tappable.
Show "unknown" rather than a guess when the mapping is not confident.

**Out of scope:** editing, annotation, or offline storage of drawings.

## Transport notes

Drawings are on `pc.alliancels.net`, already allowlisted, and reachable
with the existing session — no new provider access is required. The page
is large (1.29 MB), comfortably under the 5 MB page cap, though the SVG
should be extracted server-side so the phone receives only the diagram
rather than the whole HTML document.
