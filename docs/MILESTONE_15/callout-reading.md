# Milestone 15 — reading callout numbers that are never written down

Status: **implemented and validated.** Derived 2026-08-08 from all 34 IA135
drawings.

Field report: "Not all of the diagrams are interactive though. For example,
Drive doesn't."

Thirteen of the thirty-two drawings with a diagram came from an export that
draws its callouts anonymously — a circle and some curves, with the number
nowhere in the markup. The other two exports name theirs
(`<g id="callout_8">`), which is what
[drawings-discovery.md](drawings-discovery.md) records.

This is how the anonymous ones were made readable, and why the result can
be trusted with a part number.

## What made it hard

Exact matching does not work. The same digit is exported with different
curve factorisations (`c0.26,-0.43,0.77,-1` in one instance, `s0.77,-1` in
the next) and at slightly different sizes, so no two instances of a digit
are identical. Of 179 glyphs from the labelled drawings, 144 had a distinct
path signature.

There is also no other source for the mapping: the page carries no script,
no data attribute, and no coordinate table. The number exists only as a
shape.

## The descriptor

Each glyph is flattened to points (curves sampled), normalised into a 16x16
box scaled by its larger dimension — so position and size drop out but
aspect ratio does not, and a `1` cannot normalise into an `8` — and reduced
to the set of occupied cells. Two glyphs are compared by Jaccard distance.

**Checked leave-one-out against 180 glyphs whose digit is known from the
enclosing `<g id="callout_N">`: 180 correct, 0 wrong**, with the nearest
wrong digit never closer than 0.186.

> An earlier run of this check reported 17 failures. Every one was a
> mislabelled sample, not a bad descriptor: legacy ids escape underscores
> (`number_x005F_5_3_`) and duplicate copies are suffixed (`number-10` is
> the tenth copy of an unnamed element, not the digits "1" and "0"). Ground
> truth now comes from the enclosing callout group only.

## Labelling the third typeface

The anonymous drawings use a typeface no labelled drawing uses, so it had
no examples. Its digits were established **three independent ways, which
agree**:

1. **Clustering.** The 262 glyphs inside markers across the 13 drawings
   fall into 10 large clusters (83, 27, 20, 20, 19, 19, 17, 15, 10, 10) and
   16 tiny ones. The tiny ones are arrowhead fragments that stray inside
   the marker circle, not digits.
2. **Constraint solving.** Every marker's number must be a row in that
   drawing's parts table and must not start with a zero. Searching all
   assignments of clusters to digits against 177 markers leaves **three**
   candidates — the constraints cannot separate a 4↔5 or 6↔7 swap, because
   the parts tables are dense.
3. **Cross-typeface matching.** Comparing each cluster to the two known
   typefaces picks the same digit as the contact sheet for 9 of 10
   clusters. The exception is `0`, whose nearest known-typeface neighbour
   is `9` — and all three constraint solutions independently say `0`.

Rendering one representative per cluster resolves what the constraints
cannot, and lands on exactly one of the three constraint-consistent
assignments. Where the eye and the constraints could have disagreed, they
did not.

## Using it

`glyph_reader.read_callouts` finds marker circles (drawn as a `<circle>` in
one pipeline and as arcs in another), takes the small paths that sit inside
them, reads the digits left to right, and returns a number.

Fail-closed at every step. A glyph is not read unless it is within 0.45 of
a known digit **and** at least 0.10 closer to that digit than to any other.
If any digit of a marker fails, the whole marker is dropped. A number that
is not a row in the parts table is dropped.

## The reader also checks the labelled drawings

Running it where the markup already names the callouts turned up something:

```
'callout_20', 'callout_21_1_', 'callout_20_1_', 'callout_21_2_', 'callout_20_2_'
   ref=20 at (227.7, 295.8)      ref=21 at (227.7, 295.8)
   ref=20 at (408.2, 421.2)      ref=21 at (408.2, 421.2)
```

Two differently-numbered callout groups stacked on the same circle. The app
placed both tap targets there and answered with whichever was drawn last —
a wrong part number, from markup alone, with nothing to warn us. The digits
on those markers read `21`, which is corroborated: if they were `20`, then
`21` would have no marker anywhere despite being in the parts table.

So `drawing_callouts.reconcile` combines the two sources without preferring
either — markup alone is used, a read marker alone is used, agreement is
kept, a stacked marker is settled by its digits, and a straight
contradiction is dropped.

## Result

Measured across all 34 drawings:

| | before | after |
|---|---|---|
| tap targets | 282 | 457 |
| interactive diagrams | 19 of 32 | 32 of 32 |
| callouts not in the parts table | 0 | 0 |

Drive — the drawing that prompted this — went from none to 22.

## What would invalidate this

The typefaces are the provider's, not ours. A fourth export pipeline, or a
font change, would show up as markers that stop reading — tap targets
quietly disappearing from a drawing, never a wrong part number, because
nothing is offered unless it clears the distance, the margin, and the
parts table. Regenerate the dictionary with
`scratchpad/build_dictionary.py` if that happens.
