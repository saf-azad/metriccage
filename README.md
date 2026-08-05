# MetricCage — portfolio site

Static site, no build step, no dependencies, no tracking. Open `index.html` in a
browser and it works — including offline, straight off the filesystem.

The site is built in the **Paper design system**: flat outlines on a pale grey
sheet, one 2 px stroke weight, no shadows. It follows direction **1a —
"Broadcast scroll"** from the Portfolio Wireframes canvas.

```
index.html          premise → pipeline → ensemble → results → feature importance
                    → findings teaser → case teasers → engineering → roadmap
                    → contact
model.html          evidence: Brier decomposition, forecast distribution,
                    baseline ladder, leave-one-out ablation, permutation
                    importance, performance by experience, stability, repro
discoveries.html    computed findings 01–11 + methods + further results + queue
case-studies.html   Macau (featured) + four scheduled cards + method
assets/tokens/      Paper design-system tokens (colors, type, geometry,
                    spacing, motion, base) — verbatim from the DS export,
                    except fonts.css which self-hosts Space Grotesk
assets/wireframe.css  page layout and the prose layer, on top of the tokens
assets/fonts/       Space Grotesk variable (OFL), self-hosted
assets/favicon.svg  inline-drawn mark, same five-colour palette
```

## Writing conventions

Two rules govern the copy, and both are worth keeping if the site is edited
later.

**Headings are plain labels, not slogans.** Sections are named for what they
contain — `Data pipeline`, `Blind test set`, `Feature importance`,
`Stability by year` — rather than with declarative one-liners. Quotation marks
are not used for emphasis or distancing anywhere in the copy.

**No figure appears in prose that is not already a measured value.** The
sentences supply the argument around the numbers; they never introduce a new
one. Sections with nothing measured to report — the four cards awaiting a
write-up, the four queued findings — render as explicit stubs rather than being
filled in, and each queued finding states the test that would kill it.

## Where every number comes from

All figures are synced to the corrected site content (`data/site-data.js`,
`data/corrections.js`, `data/real-stats.js` from the August 2026 correctness
pass), which re-derived every published value from the raw records. The
wireframe canvas carried placeholder figures; those were **not** used.

| Wireframe placeholder | Shipped (verified) |
|---|---|
| AUC 0.598 | **0.670** [0.630, 0.708] |
| Brier 0.202 | **0.229** [0.218, 0.239] |
| Accuracy 64.7% | **59.6%** · context only |
| Ensemble weights 38 / 27 / 20 / 15 | **35.3 / 29.2 / 23.1 / 12.4** (XGBoost / logreg / LSTM / Elo) |

Discovery figures are computed from UFCStats public fight records, snapshot
2 August 2026: 8,794 fights, 41,392 fighter-round stat lines, 4,578 fighter
profiles. Era figures are expressed **per minute of elapsed fight time** rather
than as a share of a total that roughly tripled across the window — see the
`Rates, not shares` section on `discoveries.html`. Re-run `analysis/` against a
newer snapshot to regenerate `data/real-stats.js`.

## Deploying

Nothing to build. Upload the folder — GitHub Pages, Vercel, or any static host.

## Design system notes

Tokens are the Paper kit's own: paper `#ECF0F3`, ink `#000`, slate `#9CABC2`,
one 2 px stroke, radius ladder 9/19/29/49 px, no shadows anywhere. Space
Grotesk is the kit's real typeface (OFL, self-hosted at ~48 KB so the
no-dependency rule of the original site still holds).

The token files under `assets/tokens/` are verbatim design-system exports and
are not edited. Where the site needs something the kit doesn't provide, the
override lives in `assets/wireframe.css` — notably two extra ink steps
(`--ink-a62`, `--ink-a72`), because the kit's `--ink-a50` is a 3.8:1 grey that
is fine behind a placeholder bar but fails WCAG AA as real body text.

## Checks

CI (`.github/workflows/ci.yml`) parses every page and resolves every internal
`href`/`src`, failing on a missing file or a dead anchor. Beyond that, each
layout change is checked for: horizontal overflow at 1280 px and 560 px, SVG
labels escaping their `viewBox` (the outermost `<svg>` clips by default),
heading order without skipped levels, text contrast against the composited
background, and that no CSS class is either undefined or unused.
