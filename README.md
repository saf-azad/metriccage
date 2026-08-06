# MetricCage — portfolio site

Static site, no build step, no external dependencies, no tracking. Open
`index.html` in a browser and it works — including offline, straight off the
filesystem. D3 is self-hosted at `assets/vendor/`, so the no-CDN rule still
holds with the interactive charts in place.

MetricCage is presented as two things at once, and the copy keeps both in
frame: **a probability engine for mixed martial arts** (calibrated win
probabilities, not picks) and **a research tool for how the art of MMA is
changing** (the same feature pipeline, read longitudinally across sixteen
years of the sport).

The site is built in the **Paper design system**: flat outlines on a pale grey
sheet, one 2 px stroke weight, no shadows.

```
index.html          what it is → outputs & trust → the outcome tree → the
                    four streams → 2026 season results → the changing art →
                    what it does not know → contact
model.html          four streams, the 102 features family by family with
                    response-curve evidence, the two features that fail,
                    the leakage rule, full feature appendix
discoveries.html    the three season findings (method-head failure, distance
                    predictability, the submission collapse) + how styles
                    make fights + the era study
case-studies.html   the eleven Elo overrules, Vallejos and Ulberg breakdowns,
                    all 14 cards with every high-conviction call, and the
                    8 August card priced in advance
assets/tokens/      Paper design-system tokens — verbatim from the DS export,
                    except fonts.css which self-hosts Space Grotesk
assets/wireframe.css  page layout, prose layer, tables and the chart layer
assets/charts.js    interactive D3 charts (tooltips, hover, click-through)
assets/vendor/      d3 v7.9.0, self-hosted (ISC licence)
assets/fonts/       Space Grotesk variable (OFL), self-hosted
assets/favicon.svg  inline-drawn mark
```

## Where every number comes from

All content and every figure on the site are synced to the **Metric Cage 2026
season report** (prepared 6 August 2026): training data to 4 May 2025, then a
walk-forward run over the January–May 2026 season — 14 events, 175 fights the
model had never seen, no betting-market information of any kind.

Headline results, as published in the report:

| Measure | Result |
|---|---|
| High-conviction calls (≥65%) | **42 of 55 — 76.4%** [65.1%, 87.6%] |
| All 175 fights | **114 of 175 — 65.1%** |
| Winner-head AUC | **0.691** [0.614, 0.764] |
| Method head, stage one | **0.416** [0.330, 0.501] — below chance, reported as a failure |
| Cards where high-conviction calls hit 65%+ | **12 of 14** (4 perfect) |
| Ensemble overruled its own Elo and won | **11 times** at ≥60% conviction |

## Writing conventions

Three rules govern the copy, and all are worth keeping if the site is edited
later.

**Headings are plain labels, not slogans**, and quotation marks are not used
for emphasis anywhere.

**No figure appears that is not a value stated in the report.** The charts
draw only published numbers — nothing is interpolated between stated data
points, and where the report gives only endpoints (e.g. era trends), the
charts show endpoints rather than an invented time series.

**Weak components are reported as weak.** The method head's below-chance
season leads the discoveries page; the round distribution is labelled a base
rate everywhere it appears; method estimates in the card tables are marked as
decoration. The honesty is the point of the site.

## The chart layer

`assets/charts.js` renders into placeholder `<div id="chart-…">` elements and
skips any that a page doesn't declare. Charts keep the Paper language (ink,
slate, one stroke, no gradients), respect `prefers-reduced-motion`, and every
chart's headline figures are repeated in the surrounding prose and tables so
the pages remain fully readable with JavaScript off.

| id | page(s) | what it draws |
|---|---|---|
| `chart-season` | index | 14 cards, correct/total high-conviction calls, click-through |
| `chart-tree` | index, case-studies | the Vallejos v Emmett two-level outcome tree |
| `chart-era` | index, discoveries | four era shifts, then vs now |
| `chart-heads` | discoveries | winner vs method AUC with bootstrap intervals |
| `chart-rule` | discoveries | method head vs an always-decision rule |
| `chart-subq` | discoveries | submission rate by danger quartile, 2015–25 vs 2026 |
| `chart-styles` | discoveries | style presence vs share of fights reaching the judges |
| `chart-families` | model | feature-family response, bottom vs top quintile |
| `chart-ko` | model | knockout family vs its baselines |
| `chart-positions` | model | base submission probability by position |
| `chart-stance` | model | stance multipliers by archetype |

## Deploying

Nothing to build. Upload the folder — GitHub Pages, Vercel, or any static
host.

## Design system notes

Tokens are the Paper kit's own: paper `#ECF0F3`, ink `#000`, slate `#9CABC2`,
one 2 px stroke, radius ladder 9/19/29/49 px, no shadows anywhere. Space
Grotesk is the kit's real typeface (OFL, self-hosted). Token files under
`assets/tokens/` are verbatim design-system exports and are not edited;
overrides live in `assets/wireframe.css`, including two extra ink steps
(`--ink-a62`, `--ink-a72`) because the kit's `--ink-a50` fails WCAG AA as
body text.

## Checks

CI (`.github/workflows/ci.yml`) parses every page and resolves every internal
`href`/`src`, failing on a missing file or a dead anchor. Beyond that, each
layout change is checked for: horizontal overflow at 1280 px and 560 px,
heading order without skipped levels, text contrast against the composited
background, and that no CSS class is either undefined or unused.
