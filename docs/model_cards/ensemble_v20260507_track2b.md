# Model Card — Ensemble v20260507_track2b

> 4-stream ensemble (logreg + XGBoost + Elo + career LSTM) with isotonic calibration.
> Track 2B detail-page enrichment shipped — adds strike-attempted, TD-attempted, and control-time features.

## Identity

- **Trained on**: 2026-05-07
- **Training cutoff**: 2022-12-31
- **Validation slice**: 2023-01-01 → 2023-12-31
- **Test slice (blind)**: 2024-01-01 → 2025-05-04
- **Random seed**: 42

## Data

- **Test rows**: 695
- **Total features**: 27
- **New (Track 2B)**: strike_acc_diff, strike_def_diff, control_pct_diff, td_acc_diff, td_def_acc_diff

## Ensemble weights (refit on val, SLSQP-constrained log-loss)

| Stream | Weight |
|---|---|
| logreg | 0.5921 |
| xgb | 0.4079 |
| elo | 0.0000 |
| lstm | 0.0000 |

LSTM trained successfully (val AUC 0.6522) but ensemble fit dropped its weight — logreg + xgb cover its signal more efficiently after Track 2B features lifted them from val AUC ~0.64 to ~0.66.

## Validation ensemble metrics

- Log-loss (pre-cal): 0.6534
- Log-loss (post-cal): 0.6293
- Brier (post-cal): 0.2216

## Held-out test metrics (blind 2024-01 → 2025-05)

| Metric | Value | Target | Pass? |
|---|---|---|---|
| Brier | 0.2274 | < 0.225 | ✗ |
| Log-loss | 0.6599 | < 0.66 | ✓ |
| AUC | 0.6676 | >= 0.74 | ✗ |
| Accuracy | 0.5971 | informational | ✓ |

## Δ vs prior bundles

| Metric | v1 baseline | LSTM bundle | **Track 2B (this)** |
|---|---|---|---|
| AUC | 0.6580 | 0.6606 | **0.6676** |
| Brier | 0.2315 | 0.2311 | **0.2274** |
| Log-loss | 0.6540 | 0.6525 | **0.6599** |
| Accuracy | 0.6072 | 0.5971 | **0.5971** |

## Top-15 XGBoost feature importance

| Rank | Feature | Importance |
|---|---|---|
| 1 | strike_net_diff | 18.121 |
| 2 | elo_prob_a | 16.031 |
| 3 | elo_diff | 15.566 |
| 4 | age_diff | 15.431 |
| 5 | td_per15_diff | 11.923 |
| 6 | days_inactive_diff | 9.881 |
| 7 | strike_def_diff | 9.709 |
| 8 | rounds_exp_diff | 9.302 |
| 9 | td_def_acc_diff | 9.000 |
| 10 | kd_absorbed_per15_diff | 8.935 |
| 11 | td_def_per15_diff | 8.447 |
| 12 | sapm_diff | 7.954 |
| 13 | a_elo_pre | 7.896 |
| 14 | win_pct_diff | 7.740 |
| 15 | sub_att_per15_diff | 7.469 |

## Notes

- Track 2B detail-page scrape: 7270/7270 fights enriched (100% coverage).
- The XGBoost model now sees  (true sig-strike accuracy),  (1 - opponent accuracy),  (cage-control fraction),  (true TD accuracy), and  — features unavailable from the v1 fight summary alone.
- LSTM still in ensemble (val AUC 0.652 standalone) but receives 0 weight — the constrained-LS optimizer prefers the logreg+xgb pair.
- A/B label balance step () deterministic with seed=42; raw fights frame stored fighter_a as winner everywhere (100% class 1).
