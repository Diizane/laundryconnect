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

## ~~The blocker: callout numbers are curves, not text~~ — corrected

> **Correction, same day.** The conclusion below was wrong, and it was
> wrong in the expensive direction: it deferred a feature that is in fact
> safe to build. The *rendered digits* are outlines, which is what the
> first pass looked at. But each callout sits in a group that **states its
> own number**, which the first pass missed by reading the glyph paths
> instead of the enclosing markup. See "Callouts are labelled" below.

The SVG contains **zero `<text>` elements**. Callout numbers are CAD text
converted to outlines — e.g. the digit "1" is
`M25.54,159.74h-1.37v-5.17c-.5.47-1.09.…`.

So:

- ✅ callout **positions** are extractable (leader-line endpoints)
- ❌ ~~callout **numbers** are not readable from the markup~~ — they are;
  see below
- ✅ the parts table is fully extractable (19 rows, refs `1`–`19`, with part
  numbers and descriptions)

The original reasoning was that a mapping would need either an unverified
order assumption or fragile glyph recognition, and that neither is safe to
ship untested — a wrong mapping means a technician orders the wrong part.
That safety bar still stands; it is simply met by the markup itself.

## Callouts are labelled

Observed 2026-08-08 across all 34 IA135 drawings. Each callout is a group
whose id carries the reference number, alongside an `onclick` handler that
repeats it:

```html
<g id="callout_5" onclick="click('5')" onmouseover="over('5')">
  <circle id="circle_5" cx="307.98" cy="437.961" r="9.407"/>
  <path id="number_5" d="…"/>          <!-- the glyph outline -->
</g>
```

The marker's position is stated too: a `<circle cx cy r>` in one export
pipeline, and a path whose on-curve anchors give the same bounding box in
the other.

Consequences for Phase 2:

- No glyph recognition and no order assumption are needed.
- Ids are sometimes mangled by the export tool (`callout_10_1_`,
  `callout_1-2`), so the reference is the leading digits; where `id` and
  `onclick` both state a number they must agree, and a callout is dropped
  if they do not.
- Callouts are a **subset** of the parts table — one drawing lists 5 parts
  but marks only 2 — so some rows have no tap target, and that is normal
  rather than a parsing failure.
- Some drawings have no callouts at all (Serial Label), and one entry
  listed among the drawings is not a drawing (Parts Manual On Demand, a
  bulk export larger than the page cap).

## Two export pipelines, one diagram

Also observed across the same 34 drawings: the page always contains
exactly one diagram plus seven small zoom-control icons, but the diagram's
`width` is `7.74in`, `13.63cm`, `502.941px` **or absent**, and its group
ids are either the CAD set (`parts`, `callouts`, `misc_parts`) or a bare
`Layer_1`. Selecting the diagram by a width in inches — the original
implementation — found it on only 14 of 34.

Geometry separates the two populations cleanly: diagrams hold 22–6,526
drawing elements, icons never more than 2. That is the rule now used, with
ambiguity (two candidates) yielding no diagram rather than a guess.

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
