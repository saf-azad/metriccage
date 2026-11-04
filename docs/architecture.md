# Architecture

End-to-end view of how a fight prediction is produced. For the *why* behind these choices, see
`PLAN.md`; for *what actually shipped and how it scores*, see `MODEL_STATUS.md`. Reconciled
with the implementation 2026-07-03.

## Data flow

```
                     ┌──────────────────────┐
                     │  UFCStats.com (HTML) │
                     │  BestFightOdds.com    │
                     │  Tapology / Sherdog   │
                     └──────────┬───────────┘
                                │ scrape (rate-limited, cached)
                                ▼
                     ┌──────────────────────┐
                     │   data/raw/          │  ← gitignored
                     │   (HTML + raw CSVs)  │
                     └──────────┬───────────┘
                                │ src/data/clean.py
                                ▼
                     ┌──────────────────────┐
                     │  data/interim/       │
                     │  fights.parquet      │
                     │  fighters.parquet    │
                     └──────────┬───────────┘
                                │ src/features/build_matrix.py
                                │   (Elo replay, GMM fit, time-decayed stats)
                                ▼
                     ┌────────────────────────────┐
                     │  data/processed/           │
                     │  feature_matrix_built (102) │  ← one row per fight (canonical)
                     │  cluster_model.pkl          │
                     └──────────┬─────────────────┘
                                │ src/data/splits.py
                                ▼
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
        TRAIN                  VAL                 TEST
        (2005–2022)        (2023)              (2024–2025)
```

## Model layer

```
           feature matrix (X, y)              (shipped reality, 2026-07-03)
                    │
   win/loss streams │                            method head (separate)
   ┌──────┬─────────┴──────┬────────┐         ┌────────────────────────┐
   ▼      ▼                ▼        ▼         ▼                        │
  Elo   Logistic      XGBoost    PyTorch   two-stage XGB               │
(base)  Regression   Model A     LSTM      (finish → sub|finish)       │
 P(A)    P(A)         P(A)       P(A)       + per-stage isotonic        │
   │      │            │          │         → P(KO/Sub/Decision)       │
   └──┬───┴────────────┴─────┬────┘                   │                │
      │  weights .29/.35/.12/.23                       │                │
      ▼  src/models/ensemble.py                        │                │
  weighted blend → iso_blend → temperature(T=1.3)      │                │
      │                                                │                │
      ▼                                                ▼                │
 calibrated P(A wins)                          method probabilities ────┘
      │            │ src/api/predict_fight.py (facade → loading/assembly/types)
      └─────┬──────┘
            ▼
     FightPrediction object
     ├── winner_prob
     ├── method_prob      (two-stage XGB head, calibrated + sub_danger prior)
     ├── round_estimate   (HEURISTIC from method probs — regressor not yet wired)
     ├── confidence       (ensemble spread)
     ├── top_drivers      (SHAP from Model A)
     ├── cluster_matchup
     └── warnings
```

## Why each model is in the ensemble

**Elo** is the strength-of-schedule baseline. It's the only model that updates online during inference (we can re-run the rating store in seconds). If the ensemble can't beat Elo, something is broken.

**XGBoost (Model A)** is the workhorse. Boosted trees handle the small-sample tabular regime better than anything else, and SHAP gives us interpretability for the `top_drivers` output.

**Method head** is a **two-stage XGBoost chain** (`src/models/method_two_stage.py`), not the
Random Forest the plan sketched: stage 1 finish-vs-decision, stage 2 submission-vs-KO given a
finish, each isotonic-calibrated, with a rules-based `sub_danger_combined` prior blended in at the
API. (The RF in `method_rf.py` is implemented to the original design but superseded.) It runs
independently of the win/loss ensemble.

**Logistic regression** is the fourth win/loss stream — a fast, well-calibrated linear baseline that
the ensemble weights alongside Elo/XGB/LSTM.

**PyTorch LSTM (Model C)** is the new ingredient. It looks at each fighter's *career as a sequence* — the trajectory, not just the snapshot. Improving fighters and declining fighters look identical to a tree at a single point in time but very different in sequence.

## Where temporal correctness lives

`src/features/build_matrix.py` is the only place that walks through fights chronologically. Every feature function takes `event_date` and a history DataFrame already filtered to `< event_date`; the row is computed *before* history/Elo are updated with the current fight. If a future leak appears, the bug is here. Two tests enforce this: `tests/test_temporal_split.py` (the split contract) and `tests/test_temporal_leakage.py` (the leak-free contract end-to-end, via truncation invariance — a fight's 100 feature columns must be bit-identical whether or not later fights exist in the input).

## Deferred / not yet wired

- Monte Carlo simulator (`src/models/monte_carlo.py` — deliberate v1.5 stub)
- Round-of-finish regressor (`round_regressor.py` implemented, **not wired** — API round estimate is heuristic)
- Bayesian per-fighter shrinkage to division priors (`clustering.py` supports it; not yet fed to the matrix)
- Referee/judge bias adjustments
- Live odds feed integration (the staged AUC lever — see `docs/MODEL_STATUS.md §4`)

**No longer deferred (now in production):** tier-2 stylistic/archetype features (see
`docs/feature_dictionary.md`).
