# MetricCage — portfolio site

Static site. No build step, no dependencies, no tracking. Open `index.html` in a
browser and it works — including offline, and including straight off the filesystem.

```
index.html          landing page (hero → problem → pipeline → ensemble → results
                    → CORRECTIONS LEDGER → discoveries teaser → drivers
                    → case teasers → limits → roadmap → live tool → contact)
model.html          the model-evidence page: Murphy decomposition, forecast
                    distribution, baseline ladder, leave-one-out ablation,
                    permutation importance, SHAP, the blind spot measured
discoveries.html    eleven computed findings, denominator-corrected, + methods
case-studies.html   2026 card breakdowns, Macau first
data/corrections.js THE LEDGER — every claim the Aug-2026 audit changed
data/site-data.js   model copy + discovery narrative (numbers cite their n)
data/real-stats.js  GENERATED from analysis/*.json — the real chart series
analysis/           Python scripts + JSON outputs; README.md has repro steps
assets/style.css    design tokens + layout
assets/audit.css    audit-layer components (ledger, load-lines, captions, ticker)
assets/app.js       rendering + hand-rolled SVG charts
assets/audit.js     the 19 charts added or replaced by the correctness pass
assets/fonts/       Bitsand, Space Grotesk, IBM Plex Mono (self-hosted, ~85 KB)
```

Everything is driven from `data/site-data.js`. To change a figure, a paragraph, or a
case study, edit that one file — you should never need to touch the HTML.

---

## Before you publish

### 1. Fill in the four placeholders

In `data/site-data.js` → `SITE.meta`:

| Field | Current | Needs |
|---|---|---|
| `github` | `https://github.com/REPLACE-ME/...` | your real repo URL |
| `cv` | `cv.pdf` | drop a CV PDF next to `index.html`, or set to `""` to hide the link |
| `linkedin` | `""` | your profile URL, or leave empty to hide |
| `dashboardUrl` | `viz/showcase/index.html` | wherever the D3 dashboard ends up relative to this page |

### 2. Provisional flags — RESOLVED

All five `verified: false` placeholders are gone. `analysis/score_streams.py`
re-scores the shipped 4-stream bundle on the frozen split and reproduces its own
recorded test metrics to 1e-16, so reliability bins, Brier-by-year, ECE, feature
importance and SHAP are now measured on the model this site actually ships.

| Was provisional | Now |
|---|---|
| `results.rows[3]` ECE `0.011` | **0.049** (95% CI 0.033–0.092) — the 0.011 belonged to the superseded 3-stream model |
| `featureImportance` | superseded by **permutation importance** on held-out data; XGBoost gain is shown only as the discredited comparison |
| `shapCase` | superseded by a **SHAP beeswarm across all 695 test fights** |
| `reliability.bins` | real bins, **equal-frequency, with Wilson intervals** |
| `brierByYear.series` | real, with **train/validation/test shaded** and the axis anchored |

### 3. Write up the four queued case studies

`CASE_STUDIES` in the same file has one complete entry (Macau) and four stubs
(UFC 328, UFC 329, Baku, Kape vs. Horiguchi). Stubs render as a short
"write-up pending" list rather than as fabricated results. Fill in `record`,
`headline`, `lede`, `body`, `lesson`, then flip `verified: true` and the entry
promotes itself into a full case study — and, if you set `featured: true`, onto
the landing page.

### 4. Discovery data is REAL — and was re-derived in August 2026

Everything on discoveries.html is computed from actual UFCStats records
(8,793 bouts, snapshot 2 Aug 2026) — see `analysis/README.md` to re-run the
pipeline on a newer snapshot and regenerate `data/real-stats.js`.

**Read `data/corrections.js` first.** Every era figure is now expressed against
elapsed fight time rather than as a share of a total that tripled over the same
window, and four published findings reversed as a result. One code defect
(`sum()` on an all-NaN group returning `0.0`) contradicted a guarantee printed in
the methods section and is fixed. Nothing was deleted: the ledger renders on the
landing page with the original claim struck through, the corrected claim beside
it, and the mechanism named.

The one remaining approximation is the GSP tree-ring rendering (public record,
year-level, labelled). Every section states the test that would falsify it.

### 5. Regenerate the dashboard fixtures

Per the project's own `viz/README.md`, run `scripts/export_viz_fixtures.py` so the
live tool shows current predictions rather than a stale snapshot, and either swap
`elo_traces.json` / `fighter_network_data.json` for real exports or label them as
illustrative.

---

## Deploying

Nothing to build. Upload the folder.

**GitHub Pages** — commit this directory to the repo (e.g. as `docs/`), then
Settings → Pages → Source: `main` / `docs`. The dashboard needs to sit at the path
in `SITE.meta.dashboardUrl` relative to `index.html`.

**Vercel** — `vercel deploy` from this directory; it will be detected as a static
site with no framework.

**Any static host** — drag the folder in.

---

## Design system — "broadcast scoreboard"

Dark fight-night analytics. Tokens are declared once at the top of `style.css`:

- Canvas `#08090C` / raised `#0E1116` · Foreground `#EDF1F4`
- Signal red `#FF4D3D` (accent, big numerals) · Cool cyan `#57B3D9` (secondary series)
- **Bitsand** (blocky display headlines + numerals) · **Space Grotesk** (body/UI)
  · **IBM Plex Mono** (data labels, tabular figures)
- Atmosphere: faint 12-column cage grid, film grain, octagon wireframe in the hero,
  scroll-triggered reveals and animated bars (all honour `prefers-reduced-motion`)

**Font licence note:** Bitsand ships here as the free *demo* version — fine for a
personal portfolio, but if this site ever becomes commercial (paid product, client
work), buy the full Bitsand licence or swap the display font. Space Grotesk (OFL)
and IBM Plex Mono (OFL) are unrestricted.

Charts are hand-written SVG rather than D3 — the wrapper has no runtime dependency,
so it cannot break because a CDN is down or a version bumped. The dashboard keeps
its own D3.
