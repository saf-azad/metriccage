# Model Status — honest scoreboard

> Last reconciled: 2026-07-03 · Source of truth for *what the deployed model actually is
> and how well it actually does*. Where docs/PLAN.md describes the intended design, this file
> describes the shipped reality. If they disagree, this file is right about the present and
> docs/PLAN.md is right about the intent.

## 1. Current metrics vs targets

Blind test slice = `2024-01-01 → 2025-05-04`, n = 695 fights, no odds feature.
Numbers below are read directly from `data/processed/final_model_metrics.json`.

| Metric | Target (PLAN §3) | Current | Status |
|---|---|---|---|
| AUC-ROC | ≥ 0.74 | **0.6695** | ✗ short by ~0.07 |
| Brier | < 0.225 | **0.2286** (test) · 0.2221 (val, post-cal) | ✗ on blind test; ✓ on val |
| Log-loss | below market for non-main-events | **0.6463** | — not benchmarked vs closing line yet |
| ECE (10-bin) | < 0.05 | **~0.011** † | ✓ (see caveat) |
| Accuracy | (not a target — favourite ≈ 60%) | **0.5957** | context only |
| Method top-1 | > 52% finished fights | ~0.508 (val, two-stage head) | ✗ marginal |
| Round MAE | < 0.9 rounds | not measured | — round head is heuristic (see §2) |

† **ECE caveat:** the 0.011 figure was measured on the *legacy Phase-2 three-stream model*
(`docs/backtest_report.md`, 2026-05-06). It has **not** been re-measured on the current
four-stream bundle. Reliability looked well-behaved in live-card use, but treat ECE as
"probably still passing, not freshly verified." Re-measuring it (no retrain needed — just
score the test slice and bin) is the cheapest honesty win available.

**Bottom line:** calibration is close to target; **discrimination (AUC) is the real gap.**
Closing it requires training/compute, which was explicitly out of scope for the
reproducibility overhaul this file was written during. The staged plan to close it is §4.

## 2. What the deployed bundle actually is

`data/processed/final_model_bundle.pkl` is **not** the single clean artifact docs/PLAN.md implies —
it is a composite assembled by four scripts in sequence (all now under `scripts/` /
`scripts/archive/`, documented in `scripts/archive/README.md`):

1. `scripts/train_all.py` — base: 102-feature matrix, logistic-regression stream, ensemble
   scaffold, method-calibration plumbing.
2. `scripts/train_lstm.py` — adds the career-LSTM as a 4th probability stream.
3. `scripts/archive/optuna_xgb.py` — **produced the current win/loss XGB head**: 80-trial
   Optuna search maximising validation AUC over a SHAP-pruned 67-feature subset. The winning
   params are frozen in `src/config.py::XGB_OPTUNA_TUNED` — rerunning training with those
   reproduces the deployed head **without** repeating the sweep.
4. `scripts/archive/retrain_twostage_only.py` — **produced the current method head**: a
   two-stage XGB chain (stage 1 finish-vs-decision, stage 2 submission-vs-KO | finish), each
   with an isotonic calibrator. Ported faithfully to `src/models/method_two_stage.py`
   (verified bit-identical to the bundle's inference math).

**Ensemble streams and fitted weights** (constrained least-squares on the 2023 validation
slice, minimising log-loss): `logreg 0.292 · xgb 0.353 · elo 0.124 · lstm 0.231`. This is a
**logreg / XGB / Elo / LSTM** blend — *not* the `elo/xgb/rf/lstm` seed weighting PLAN §6.6
lists, and the method head is the two-stage XGB above, *not* the Random Forest of PLAN §6.4.
The RF (`src/models/method_rf.py`) and round regressor (`src/models/round_regressor.py`) are
implemented to the plan's design for interface completeness but are **not** what production
uses.

**Calibration chain** applied inside `src/api/predict_fight.py` at blend time:
per-stream isotonic (unused in the current bundle — keys are `None`) → weighted blend →
`iso_blend` isotonic on the blended probability → temperature scaling with
`calibration_temperature = 1.3` (shrinks extremes toward 0.5; set out-of-band, read only by
the API). **Known caveat:** `iso_blend` maps blended probabilities ≥ ~0.73 to 1.0, so a very
confident blend can read as a fake 100%. The API clamps to `1 − 1e-6` before display and the
temperature scaling partly mitigates it, but the underlying calibrator curve is still worth
re-fitting.

**Round prediction is heuristic**, not modelled: the API derives a round distribution from
the method probabilities (finishes skewed to rounds 1–2 per UFC base rates). The
`round_regressor` interface exists for when a real one is trained.

**Reproducibility caveat — pickle version skew.** The bundle and `cluster_model.pkl` were
pickled under **scikit-learn 1.7.2**; loading under a newer minor (e.g. 1.8.0) raises
`InconsistentVersionWarning`. Predictions were re-verified sane under the drift (the headline
Makhachev–Oliveira 0.73 reproduces), but exact reproduction needs the known-good versions listed
at the top of `requirements.txt`. A retrain (`scripts/train_all.py`) re-pickles under the current
environment and clears the warning.

## 3. Known blind spots (validated in live-card use)

These are honest failure modes, not hypotheticals — each was seen on a real card:

- **Method head skews to Decision.** Stage-2 (sub vs KO) validation AUC is only ~0.56; the
  API blends in a rules-based `sub_danger_combined` prior to partly correct grappler-vs-striker
  cases the classifier under-ranks.
- **No weight-change / short-notice feature.** A fighter moving up/down in weight or taking a
  fight on short notice is invisible to the model (missed the Pereira 251-lb move).
- **UFC-only history.** The fighter database is UFC bouts only, so debutants and
  regional-circuit imports have little/no history; the model degrades or abstains on
  debutant-heavy international cards (e.g. Macau: 9/13).
- **Two feature matrices coexist** (technical debt, documented not fixed this run):
  `feature_matrix_built.parquet` (114 col = 12 id/target + 102 features) is canonical for
  training; `feature_matrix.parquet` (34 col, legacy) is still read by
  `scripts/backtest_2026_events.py` and the default path of `scripts/train_lstm.py`. Unifying
  them is a follow-up.

## 4. Staged, compute-enabled roadmap to the targets

**None of this was executed during the reproducibility overhaul — no retraining, no scraping.**
Expected lifts are estimates carried over from `docs/planning/IMPROVEMENT_docs/PLAN.md`, clearly
labelled as estimates. Run these in order; re-measure after each.

| Stage | Change | Expected lift (est.) | Prereqs (already in place) |
|---|---|---|---|
| 1 | **Retrain / upgrade the LSTM** on richer per-round career sequences | +0.02–0.04 AUC | `data/interim/fight_rounds.parquet` (124k rows) already parsed |
| 2 | **True-accuracy features** from attempted counts (strike/TD accuracy, control time) | +0.01–0.02 AUC | `fights_enriched.parquet` already carries `ss_attempted/td_attempted/control_time`; integrate as diff features (a `track2b` attempt exists — reconcile it) |
| 3 | **GMM refinement + weight-class Bayesian shrinkage** for sparse fighters | small AUC; **calibration fix** for debutant-heavy cards | `src/models/clustering.py` already supports division-prior shrinkage |
| 4 | **Optional closing-odds feature** | +~0.04 AUC | changes the model's nature (needs odds at inference) — a product decision, not just a training run; flag before doing it |

Realistic read: stages 1–2 plausibly reach AUC ≈ 0.70; hitting the **0.74** target most
likely also needs stage 4 (odds), which the plan itself flags as the honest lever if the
odds-free model plateaus around 0.70.

## 5. How to rerun training faithfully

```bash
# Fast wiring check (no training, no network, seconds) — proves the pipeline is connected:
make smoke                      # → scripts/train_all.py --smoke, writes only to .smoke/

# Full retrain (compute-heavy; writes data/processed/final_model_bundle.pkl):
PYTHONPATH=. .venv/bin/python scripts/train_all.py --with-lstm --rebuild-matrix
```

To reproduce the **exact deployed win/loss head** without the 80-trial Optuna sweep, pass
`src/config.py::XGB_OPTUNA_TUNED` as the XGB params (see `scripts/archive/README.md`). To
reproduce the **method head**, use `src/models/method_two_stage.train_method_two_stage` with
its default `TWO_STAGE_METHOD_PARAMS`.
