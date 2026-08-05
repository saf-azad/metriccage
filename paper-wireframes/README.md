# MetricCage — Paper wireframes

The MetricCage portfolio reimagined in the **Paper** wireframe design system, built as
React components from the Claude Design handoff bundle in `../project`.

These are literal wireframes. Prose is drawn as bars rather than set as type, exactly as
the approved mocks draw it — a 5px bar is a heading, a 3px bar is a line of body copy,
and the width carries the meaning. Real type appears only where the mocks use it:
section eyebrows, one heading per band, and numerals.

```
npm install
npm run dev              # review canvas at localhost:5173
npm run build
npm run check:fidelity   # diffs the build against the original export
```

## What is here

Seven screens, presented on the same review canvas the design tool used, so the `#1a`
… `#2c` anchors still resolve.

**Turn 1 — four landing-page structures**

| | | Source |
|---|---|---|
| `1a` | Broadcast scroll — the current narrative, redrawn | verbatim from the export |
| `1b` | Dashboard — sidebar nav, evidence as a control room | verbatim from the export |
| `1c` | Editorial column — one narrow thread, numbers as headlines | **partly reconstructed** |
| `1d` | Bento grid — the whole argument above the fold | **fully reconstructed** |

**Turn 2 — the rest of the site**

| | | Source |
|---|---|---|
| `2a` | Model evidence — `model.html` | derived |
| `2b` | Discoveries — `discoveries.html` | derived |
| `2c` | Case studies — `case-studies.html` | derived |

## What was reconstructed, and why

**The export is truncated.** `Portfolio Wireframes.dc.html` ends mid-element inside
option 1c's corrections ledger, and option 1d is absent from the file entirely even
though chat 2 records it as built. So:

- **1c** is verbatim down to the second ledger row. Its case-study strip and contact
  footer — the two sections chat 2 names — are rebuilt in this layout's own idiom: a
  400px measure inside a 520px card, so the strip is a stacked list rather than the
  three-up grid 1a uses, and the footer stays centred like the hero.
- **1d** is reconstructed from its one-line description, built strictly out of the
  vocabulary the other three options establish. Nothing in it is invented beyond the
  grid itself.

**The three inner pages are derived, not exported.** The design file only covers the
landing page. `2a`–`2c` rebuild the live pages' own structure in option 1a's idiom, so
the site reads as one system. Section eyebrows and headings are the live site's own
text; headings that the live pages compute at runtime are left as bars rather than
invented. No new figures were introduced — the only numerals set anywhere are ones that
already appear in the approved mocks or in the bundle's own README (`0.202`, `0.049`,
`0.598`, `64.7%`, `695`, `102`, `4`, `8,793`, `2 Aug 2026`).

## Fidelity

`npm run check:fidelity` rewrites the export as a static page — it is an `x-dc`
template that otherwise needs the design runtime — renders both documents in Chromium,
and diffs them card by card.

```
  card                        strict     1px-tolerant
  ────────────────────────────────────────────────────
  1a  broadcast scroll        0.000%    0.000%   ok
  1b  dashboard               0.000%    0.000%   ok
  1c  editorial (to cut)      0.023%    0.017%   ok
```

1a and 1b are bit-identical to the export. 1c's residual is its bottom edge: the
reference card ends at the truncation point and its rounded corner clips there, while
this build continues into the reconstructed sections.

Two things the check controls for, both of which otherwise produce large phantom diffs
on pixel-identical layouts: cards are pinned to the viewport origin before capture, so
both documents round their screenshots from the same pixel phase, and the remote webfont
is blocked in both so neither depends on network conditions.

## Structure

```
src/
  styles/tokens/     the seven Paper token files, copied verbatim
  styles/canvas.css  review-canvas chrome, carried over from the export
  components/paper/  the design system as React primitives
  wireframes/landing/ 1a–1d
  wireframes/pages/   2a–2c, plus the chrome they share
  viewer/            turn and option wrappers
scripts/
  fidelity-check.mjs
```

`components/paper/` is the reusable part. It maps onto the system's own component
groups — `Bar`/`TextBlock` for drawn prose, `Card`/`Panel`/`MediaBlock`/`Tile` for
surfaces, `Pill`/`Swatch`/`Chip`/`Track`/`SegmentedBar` for controls, hand-written SVG
for charts, and composite blocks (`StatCard`, `LedgerRow`, `CaseCard`, …) for the shapes
that repeat across screens.

Three rules keep anything new on-system: **one stroke weight** (2px), **no shadows**,
and **never write copy you were not given** — leave it as a bar.

## Known deviation

The Paper readme states the source SVGs contain no all-caps setting anywhere. The
approved wireframes do use one, for section eyebrows. Since these are literal
reproductions of mocks that were signed off, the mock wins — flagged in
`components/paper/Layout.jsx` rather than silently "corrected".
