# Analysis pipeline

Every figure on the site traces to a JSON in this folder, produced by the Python
scripts next to it.

Data source: UFCStats.com public fight records, via the open mirror
https://github.com/Greco1899/scrape_ufc_stats (snapshot 2 Aug 2026 —
8,793 unique bouts, 41,392 fighter-round stat lines, 4,578 fighter profiles).
Model artefacts come from the sibling `ufc-fight-predictor` repository.

## Reproduce

```bash
git clone --depth 1 https://github.com/Greco1899/scrape_ufc_stats ufc-data
pip install pandas numpy scikit-learn pyarrow xgboost torch shap

export UFC_DATA=$PWD/ufc-data
export MC_OUT=$PWD/mc-analysis

# ---- the correctness pass (August 2026) --------------------------------
python analyze_rates.py       # rates.json      — the denominator pass
python bodies_v2.py           # bodies_v2.json  — clustered, adjusted inference
python score_streams.py       # streams_*.parquet — re-score the shipped bundle
python model_eval.py          # model_eval.json  — Murphy, ladder, ablation, CIs
python model_eval2.py         # model_eval2.json — calibrator, permutation, SHAP, card
python build_real_stats.py    # regenerates ../data/real-stats.js

# ---- the original pass (kept; superseded where they overlap) -----------
python analyze.py             # targets.json
python analyze_arcs.py        # arcs.json
python bodies_analyze.py      # bodies.json  (SUPERSEDED by bodies_v2.py)
```

`../data/real-stats.js` is generated — never hand-edit numbers in it.

## What the August 2026 pass changed, and why

### `analyze_rates.py` — the denominator

Between 1994 and 2026 the mean fight got longer *and* combined significant-strike
output went from 2.76 to 8.04 per fight-minute. Every era comparison on the site
was a share or a per-fight count, and against a denominator moving that far a
share can fall while the thing it measures rises.

This script computes an exact elapsed time for every fight by parsing
`TIME FORMAT` into round lengths and adding the final-round clock (coverage:
100% of 8,793 fights), then expresses everything per minute. It also emits an
`era_cells` block so the site can cite the **cell** n instead of the corpus n.

Four published findings changed. See `../data/corrections.js` (C01–C04, C06).

### `bodies_v2.py` — the inference

Three fixes, each of which moves a published number:

1. **`sum(min_count=1)` everywhere.** `bodies_analyze.py:239` summed control
   seconds without it, and pandas returns `0.0` for an all-NaN group — so fights
   from before the control field existed entered as *zero seconds of control*,
   the exact opposite of the guarantee printed in the methods section. 360 rows
   were affected; the bias on mean control time was 2.7 seconds. The magnitude is
   small, but the site could not previously tell you that.
2. **Fighter-level cluster bootstrap.** `sqrt(p(1-p)/n)` with n = fights treats a
   twenty-fight career as twenty independent observations. Resampling fighters
   instead widens the intervals by 1.04×–1.17× — real, and smaller than a reviewer
   would guess, which is worth reporting honestly in both directions.
3. **Per-SD, within-weight-class, jointly fitted.** "Seven years beats five
   inches" is a statement about bin edges. Each differential is standardised
   inside its own weight class and all of them enter one logistic regression with
   no intercept (the fighter-side design is antisymmetric by construction, so a
   constant — and a weight-class dummy — would be identically zero).

It also re-runs the reach/control-time null at fight level, where it is actually
identified, and finds a significant *negative* effect that the pooled career
correlation could not have detected.

### `score_streams.py` → `model_eval.py` → `model_eval2.py`

The site shipped five `verified: false` placeholders because
`final_predictions.parquet` is the legacy 3-stream file. `score_streams.py`
re-scores the **shipped 4-stream bundle** on the frozen temporal split
(train 2005-01-01→2022-12-31, val 2023, test 2024-01-01→2025-05-04 = 5,563 /
504 / 695) and reproduces the bundle's own recorded test metrics to
**1e-16**, so every model figure on the site is now the deployed model rather
than an approximation of it.

`model_eval.py` adds the Murphy decomposition (which turns the site's central
claim into an identity), Wilson-banded equal-frequency reliability bins,
bootstrap intervals on every headline metric, a baseline ladder, and a genuine
leave-one-out ablation that refits weights *and* the calibrator on validation
for each subset.

`model_eval2.py` audits the calibrator (isotonic fitted on 504 validation fights
emits 24 distinct values, one of which covers 30% of the test set), runs
system-level permutation importance — every feature shuffled in held-out data
with all four streams re-scored — computes SHAP across the test set, and replaces
the "9 of 13" card claim with the Poisson-binomial its own probabilities imply.

Permutation is the slow part. Career sequences do not depend on the fight-day
differential being permuted, so the LSTM batches are built once and only the diff
tensor is swapped per pass; without that cache the run takes hours instead of
about two minutes.

## Known limitations, unfixed

- **No closing-odds corpus.** `data/external/` is empty and the odds scraper is a
  documented stub, so model-vs-market on the test window cannot be drawn. This is
  the highest-value missing dataset.
- **Method-of-victory head** is reported in prose only (AUC ≈ 0.56).
- **Duplicate fighter names** in the tale-of-the-tape table are resolved by
  `keep="first"`; `bodies_v2.json → name_collisions` now reports how many names
  have genuinely conflicting bodies instead of silently picking one.
- **`analyze.py` / `bodies_analyze.py` are retained** so the original outputs stay
  reproducible and the corrections are diffable. Where the two disagree, the
  `_rates` / `_v2` output is correct.
