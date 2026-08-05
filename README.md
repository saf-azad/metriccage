# MetricCage — portfolio site

Static site, no build step, no dependencies, no tracking. Open `index.html` in a
browser and it works — including offline, straight off the filesystem.

The site is built in the **Paper design system**: flat outlines on a pale grey
sheet, one 2 px stroke weight, no shadows. It follows direction **1a —
"Broadcast scroll: the current narrative, redrawn"** from the Portfolio
Wireframes canvas.

The wireframe stage drew body copy as grey placeholder bars, with the prose
deferred. **That copy is written now** — every section carries real sentences,
and the bar system has been removed from both the markup and the stylesheet.
Charts remain hand-written SVG ink sketches; there is no chart library.

```
index.html          landing: hero → premise → pipeline → ensemble → results
                    → CORRECTIONS LEDGER (all 18 entries) → discoveries teaser
                    → case teasers → limits → roadmap → contact
model.html          model evidence: Murphy decomposition, forecast distribution,
                    baseline ladder, ablation, gain vs permutation, the blind
                    spot measured, Brier-by-year, what's still missing
discoveries.html    the computed findings 00–08 + methods + nulls + queue
case-studies.html   Macau (featured miss) + four pending stubs + method
assets/tokens/      Paper design-system tokens (colors, type, geometry,
                    spacing, motion, base) — verbatim from the DS export,
                    except fonts.css which self-hosts Space Grotesk
assets/wireframe.css  page layout and the prose layer, on top of the tokens
assets/fonts/       Space Grotesk variable (OFL), self-hosted
assets/favicon.svg  inline-drawn mark, same five-colour palette
```

## Where every number comes from

All type on these pages is synced to the corrected site content
(`data/site-data.js`, `data/corrections.js`, `data/real-stats.js` from the
August 2026 correctness pass). The wireframe canvas itself carried placeholder
figures — those were **not** used. Corrected examples:

| Wireframe placeholder | Shipped (verified) |
|---|---|
| AUC 0.598 | **0.670** [0.630, 0.708] · target ≥ 0.740 — miss |
| Brier 0.202 | **0.229** [0.218, 0.239] · target < 0.225 — near |
| Accuracy 64.7% | **59.6%** · context only, favourite baseline ≈ 60% |
| Ensemble weights 38 / 27 / 20 / 15 | **35.3 / 29.2 / 23.1 / 12.4** (XGBoost / logreg / LSTM / Elo) |

The corrections ledger renders all 18 audit entries with the site's own record
(3 upheld · 8 reversed-or-bug · 7 revised). Struck text is what the site
published; bold is what the data says.

The prose written for this pass introduces **no new figures**. Every number in
a sentence was already on the page as a verified value; the copy only supplies
the argument around it. Sections with nothing verified to say — the four
un-scored cards, the four queued discoveries — render as explicit stubs rather
than being filled in, and each queued discovery states the test that would
kill it.

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
change to layout is checked for: horizontal overflow at 1280 px and 560 px,
SVG labels escaping their `viewBox` (the outermost `<svg>` clips by default),
heading order without skipped levels, and text contrast against the composited
background.
