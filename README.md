# MetricCage — portfolio site, Paper wireframe build

Static site, no build step, no dependencies, no tracking. Open `index.html` in a
browser and it works — including offline, straight off the filesystem.

This build renders the MetricCage portfolio in the **Paper wireframe design
system**: flat outlines on a pale grey sheet, one 2 px stroke weight, no
shadows. It follows wireframe direction **1a — "Broadcast scroll: the current
narrative, redrawn"** from the Portfolio Wireframes canvas, with the treatment
chosen in the design brief:

- **Real type for headings, numbers and labels** — every figure on the page is
  a real, verified number.
- **Body copy drawn as bars** — prose is deferred, not written, per the Paper
  system's content rules (grey bars are interface text, slate bars are content).
- **Charts as ink-line sketches** with slate fills — hand-written SVG, no chart
  library.

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
assets/wireframe.css  page layout on top of the tokens
assets/fonts/       Space Grotesk variable (OFL), self-hosted
```

## Where every number comes from

All real type on these pages is synced to the corrected site content
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

## Deploying

Nothing to build. Upload the folder — GitHub Pages, Vercel, or any static host.

## Design system notes

Tokens are the Paper kit's own: paper `#ECF0F3`, ink `#000`, slate `#9CABC2`,
one 2 px stroke, radius ladder 9/19/29/49 px, no shadows anywhere. Space
Grotesk is the kit's real typeface (OFL, self-hosted at ~48 KB so the
no-dependency rule of the original site still holds).
