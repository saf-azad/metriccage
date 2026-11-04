# Model Card — Ensemble v20260507_track2c

> 4-stream ensemble + GMM archetype clusters (K=7) + Track 2B detail-page features.

## Identity

- **Trained on**: 2026-05-07
- **Training cutoff**: 2022-12-31
- **Validation slice**: 2023-01-01 → 2023-12-31
- **Test slice (blind)**: 2024-01-01 → 2025-05-04
- **Random seed**: 42

## Data + features

- **Test rows**: 695
- **Total features**: 41 (was 27 in 2B, 22 in v1)
- **New (Track 2C)**: cluster_a_0..6, cluster_b_0..6 — soft GMM membership over 7 archetypes
- **Cluster fit**: 1335 fighters with ≥3 train-period fights, AS-OF 2022-12-31
- **Temporal correctness**: cluster centroids frozen at fit time; predict-time membership recomputed from each fighter's as-of-event career vector

## Ensemble weights (refit on val)

| Stream | Weight |
|---|---|
| logreg | 0.2980 |
| xgb | 0.7020 |
| elo | 0.0000 |
| lstm | 0.0000 |

XGBoost dominates after cluster features (0.70 weight vs 0.41 in 2B); cluster archetypes evidently capture matchup signal that the boosted trees exploit better than logreg.

## Validation ensemble metrics

- Log-loss (pre-cal): 0.6507
- Log-loss (post-cal): 0.6303
- Brier (post-cal): 0.2216

## Held-out test metrics

| Metric | Value | Target | Pass? |
|---|---|---|---|
| Brier | 0.2302 | < 0.225 | ✗ |
| Log-loss | 0.6498 | < 0.66 | ✓ |
| AUC | 0.6648 | >= 0.74 | ✗ |
| Accuracy | 0.6058 | informational | ✓ |

## Δ vs prior bundles

| Metric | v1 | LSTM | 2B | **2C (this)** |
|---|---|---|---|---|
| AUC | 0.6580 | 0.6606 | 0.6676 | **0.6648** |
| Brier | 0.2315 | 0.2311 | 0.2274 | **0.2302** |
| Log-loss | 0.6540 | 0.6525 | 0.6599 | **0.6498** |
| Accuracy | 0.6072 | 0.5971 | 0.5971 | **0.6058** |

## Top-20 XGBoost feature importance

| Rank | Feature | Importance |
|---|---|---|
| 1 | cluster_b_2 | 37.222 |
| 2 | cluster_a_2 | 34.040 |
| 3 | elo_prob_a | 25.897 |
| 4 | cluster_b_0 | 18.335 |
| 5 | elo_diff | 16.589 |
| 6 | strike_net_diff | 16.394 |
| 7 | age_diff | 16.374 |
| 8 | cluster_a_0 | 13.595 |
| 9 | cluster_b_3 | 12.291 |
| 10 | td_per15_diff | 11.437 |
| 11 | cluster_a_1 | 11.350 |
| 12 | td_def_acc_diff | 9.987 |
| 13 | strike_def_diff | 9.151 |
| 14 | kd_absorbed_per15_diff | 9.125 |
| 15 | cluster_a_3 | 9.087 |
| 16 | days_inactive_diff | 8.774 |
| 17 | sapm_diff | 8.191 |
| 18 | cluster_a_5 | 8.077 |
| 19 | cluster_a_6 | 7.918 |
| 20 | reach_diff | 7.763 |

## Honest read

- **Cluster features lifted XGB val AUC** from 0.654 (2B) to 0.670 — clearly providing matchup signal.
- **Test metrics shifted laterally** vs 2B: accuracy +0.9pt, log-loss −0.010 (better), AUC −0.003, Brier +0.003 (slightly worse). Net wash.
- The cluster centroids fit on 1335 train-period fighters; the silhouette score (0.041) confirms archetypes are blends, not crisp clusters — which is realistic for MMA.
- LSTM still gets ensemble weight 0; XGBoost absorbs all the cluster signal.
- Targets remain unmet: AUC 0.665 vs 0.74 target, Brier 0.230 vs 0.225 target. Probable next levers: closing-line odds as feature, or weight-class shrinkage for sparse fighters.
