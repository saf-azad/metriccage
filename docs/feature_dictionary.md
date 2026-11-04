# Feature Dictionary (production — 102 features)

> Reconciled with the shipped model 2026-07-03. This lists **every feature in the deployed
> matrix** (`data/processed/feature_matrix_built.parquet`, and the bundle's `feats`). The
> authoritative list is the bundle's `feats` key; if a column here disagrees with that, the
> bundle wins. Tier-1 = the original core (PLAN §5). Tier-2 = the style/archetype block added in
> UPDATE_2 (post-UFC 328) and now in production — code in `src/features/style_mismatch.py` and
> `src/features/archetypes.py`.

All differential (`_diff`) features are `(fighter A value) − (fighter B value)`, so positive
favours A. Per-fighter features carry an `_a`/`_b` suffix. Time-decayed averages use a 365-day
exponential half-life (`src/features/time_decay.py`). Every feature is computed using only data
strictly before the fight date — enforced by `tests/test_temporal_leakage.py`.

## Targets / identity (not features)

| Column | Notes |
|---|---|
| `fighter_a_won` | Binary win/loss target (0/1). Source lists winner as A everywhere; `balance_fight_labels(seed=42)` swaps ~half the rows to balance. |
| `method` / `method_canon` | Method target → {KO/TKO, Submission, Decision} at train time (DQ/NC handled in `src/data/clean.py`). |
| `round_finished` | 1–5 if finished early, else null. |
| `fight_id, event_id, event_date, weight_class, fighter_a_id/b_id, fighter_a_name/b_name` | Identity/context, excluded from the model input. |

## Tier-1 — Elo & strength

| Column | Meaning |
|---|---|
| `elo_diff` | MMA Elo(A) − Elo(B), evaluated before the fight. Strongest single feature. |
| `elo_prob_a` | Elo-implied P(A wins) = logistic of `elo_diff / 400`. |
| `a_elo_pre`, `b_elo_pre` | Raw pre-fight Elo of each fighter (context, down-weighted as a driver). |

## Tier-1 — Striking

| Column | Meaning |
|---|---|
| `slpm_diff` | Decayed sig. strikes landed / min, A − B. |
| `sapm_diff` | Decayed sig. strikes absorbed / min, A − B (lower is better). |
| `strike_net_diff` | Net striking `(SLpM − SApM)`, A − B. (Was `strike_diff_diff` in the plan.) |
| `strike_acc_diff` | Sig. strike accuracy (landed/attempted), A − B. Needs enriched attempted counts. |
| `strike_def_diff` | Sig. strike defence (1 − opp accuracy), A − B. |

## Tier-1 — Grappling

| Column | Meaning |
|---|---|
| `td_per15_diff` | Takedowns landed per 15 min, A − B. (Was `td_acc_diff`.) |
| `td_def_per15_diff` | Takedowns conceded per 15 min (defence), A − B. |
| `td_acc_diff`, `td_def_acc_diff` | Takedown accuracy / defence-accuracy rates, A − B. |
| `sub_att_per15_diff` | Submission attempts per 15 min, A − B. (Was `sub_avg_diff`.) |
| `control_pct_diff` | Share of fight time in control position, A − B. |

## Tier-1 — Knockdowns

| Column | Meaning |
|---|---|
| `kd_per15_diff` | Knockdowns landed per 15 min, A − B. |
| `kd_absorbed_per15_diff` | Knockdowns absorbed per 15 min, A − B (chin proxy). |

## Tier-1 — Physical, form & experience

| Column | Meaning |
|---|---|
| `age_diff` | Age in years at fight date, A − B. Top-5 SHAP feature. |
| `reach_diff` | Reach (inches), A − B. |
| `stance_mismatch` | 1 if stances differ (open-stance dynamic), else 0. (Was `stance_matchup`.) |
| `win_pct_diff` | Recent win percentage, A − B. |
| `finish_rate_diff` | Career finishes / wins, A − B. |
| `rounds_exp_diff` | Total career rounds (championship-round experience), A − B. |
| `streak_diff` | `min(streak,5)` A − B. (Was `win_streak_diff`.) |
| `days_inactive_diff` | Days since last fight, A − B (ring rust). |
| `n_fights_a`, `n_fights_b` | UFC fight counts (data-density / debut context). |

## Tier-1 — Weight-class change (`core_features.py`)

Divisions are mapped onto a unified ladder of poundage rungs (115 → 265 lbs;
men's and women's classes share rungs), so a "move" is measured in divisions,
not pounds. Catch Weight has no rung and yields the centred default 0.

| Column | Meaning |
|---|---|
| `weight_change_a`, `weight_change_b` | Divisions moved vs the fighter's most recent fight at a known class: +1 = up one (LW→WW), −1 = down one, ±2 for double jumps. Intermediate catchweight bouts are skipped when finding the anchor. 0 for debutants / catchweight bouts. |
| `weight_change_diff` | `weight_change_a − weight_change_b`. |
| `first_at_class_a`, `first_at_class_b` | 1 if the fighter has prior UFC fights but none at this class (true divisional debut, not a return). Debutants read 0 — no signal beyond `n_fights == 0`. |
| `natural_wc_dev_a`, `natural_wc_dev_b` | Rungs between this bout's class and the fighter's time-decayed home class (decay-weighted mean rung of prior fights). Stays elevated across the first few fights after a move — the chronic-displacement signal that `weight_change` (0 again by fight two at the new class) misses. |

## Tier-2 — Archetype membership & matchup (`archetypes.py`)

Soft membership over 8 hand-defined style archetypes, per fighter:

`arch_a_power_puncher`, `arch_b_power_puncher`, `arch_a_muay_thai`, `arch_b_muay_thai`,
`arch_a_dutch_kickboxer`, `arch_b_dutch_kickboxer`, `arch_a_counter_striker`,
`arch_b_counter_striker`, `arch_a_wrestle_striker`, `arch_b_wrestle_striker`,
`arch_a_grappling_first`, `arch_b_grappling_first`, `arch_a_pressure_striker`,
`arch_b_pressure_striker`, `arch_a_decision_fighter`, `arch_b_decision_fighter`.

| Column | Meaning |
|---|---|
| `arch_distance` | Stylistic distance between the two archetype vectors. |
| `arch_similarity` | Overlap/similarity of the two archetype vectors. |

## Tier-2 — Grappler vs striker path (`style_mismatch.py`)

| Column | Meaning |
|---|---|
| `grappler_path_a`, `grappler_path_b`, `striker_path_a`, `striker_path_b` | How much each fighter wins via grappling vs striking. |
| `sg_mismatch_net` | Net striker-vs-grappler mismatch across the pairing. |
| `td_dominance_diff` | Takedown-dominance differential. |

## Tier-2 — KO threat & chin

| Column | Meaning |
|---|---|
| `ko_danger_a`, `ko_danger_b` | Each fighter's knockout threat. |
| `chin_durability_a`, `chin_durability_b` | Each fighter's resistance to being finished. |
| `ko_threat_net`, `ko_danger_differential` | Net KO threat across the pairing. |
| `b_chin_vulnerable` | Flag: B's chin is a live vulnerability. |

## Tier-2 — Submission threat

| Column | Meaning |
|---|---|
| `sub_danger_a`, `sub_danger_b`, `sub_danger_diff` | Per-fighter and differential submission threat. |
| `sub_danger_combined` | Combined ground-finishing threat; **also used as a soft prior in the method head** (`src/api` two-stage branch). |
| `sub_att_rate_diff` | Submission-attempt-rate differential. |

## Tier-2 — Pace, pressure & counter dynamics

| Column | Meaning |
|---|---|
| `pace_mismatch_diff` | Tempo mismatch between the fighters. |
| `pressure_index_a`, `pressure_index_b` | Forward-pressure index per fighter. |
| `counter_efficiency_diff` | Counter-striking efficiency differential. |
| `counter_threat_a_vs_b`, `counter_threat_b_vs_a` | Directional counter threat. |
| `gas_out_risk_diff` | Cardio / late-fade risk differential. |
| `b_counter_upset_setup` | Flag: B is set up as a counter-based upset threat. |

## Tier-2 — Stance interaction

| Column | Meaning |
|---|---|
| `stance_advantage_a` | A's stance advantage. |
| `stance_score_amplified` | Amplified stance-matchup score. |
| `stance_win_prob_uplift` | Estimated win-prob uplift from the stance matchup. |
| `open_stance` | Open-stance (orthodox vs southpaw) indicator. |

## Tier-2 — Stance-context × height-context matchup (`stance_height.py`)

History-conditioned layer: how each fighter has actually performed in the
*current* stance pairing (open vs closed) and against the *current* height
context (taller vs shorter opponent), relative to their own overall baseline.
Bucket metrics are time-decayed (same half-life as core features) and shrunk
toward zero by rounds of in-bucket evidence (`n / (n + 8)`), so tiny samples
contribute ~nothing. Opponent stance/height come from the static bio table;
only prior fights feed the buckets (leakage-safe).

| Column | Meaning |
|---|---|
| `height_diff` | Height differential A − B (inches; 0 if either unknown). |
| `stance_ctx_strike_edge_a`, `stance_ctx_strike_edge_b` | Per-15 net-strike edge of each fighter in the current stance pairing (open or closed) vs their own baseline. 0 when a switch/unknown stance is involved. |
| `stance_ctx_strike_edge_diff` | A − B of the above. |
| `stance_ctx_win_edge_diff` | Same conditioning, win-rate based, A − B. |
| `height_ctx_strike_edge_a`, `height_ctx_strike_edge_b` | Per-15 net-strike edge of each fighter vs opponents in the current height context (opponent ≥1in taller / shorter) vs their own baseline. |
| `height_ctx_strike_edge_diff` | A − B of the above. |
| `height_ctx_win_edge_diff` | Win-rate based, A − B. |
| `stance_height_combo_diff` | Ensemble of the two layers: `stance_ctx_strike_edge_diff + height_ctx_strike_edge_diff`. |
| `open_stance_height_diff` | `open_stance × height_diff` geometry interaction (e.g. southpaw giving up height to an orthodox opponent). |

## Tier-2 — Adaptability / context-insensitivity (`stance_height.py`)

Some fighters perform identically regardless of stance pairing, height gap, or
opponent striking style — for them, context edges are noise. These features
measure each fighter's bucket-to-bucket performance swing (of already-shrunk
edges, so thin evidence reads ~0) and classify the current opponent's striking
style. Style axes: output volume (`slpm ≥ 4.5`), grappling pressure (`TD
landed ≥ 1.5/15`), clinch vs range profile (clinch share of landed strikes
≥ 25% — separates dirty boxers / Muay Thai clinch fighters from rangey point
fighters), and kick-centricity (leg share ≥ 25%). Shares from fights with
< 10 opponent strikes landed are untagged.

| Column | Meaning |
|---|---|
| `stance_sens_a`, `stance_sens_b` | \|open − closed\| net-strike swing per fighter. |
| `height_sens_a`, `height_sens_b` | \|vs-taller − vs-shorter\| swing. |
| `style_sens_a`, `style_sens_b` | Mean swing across the 4 striking-style axes. |
| `adaptability_a`, `adaptability_b`, `adaptability_diff` | −mean(stance, height, style sensitivities); higher = more style-proof. |
| `style_ctx_edge_a`, `style_ctx_edge_b`, `style_ctx_edge_diff` | Historical net-strike edge vs opponents of the class the current opponent belongs to (volume + grappling + clinch/range + kick components, each evidence-shrunk). |

## Tier-2 — Trajectory, age curve & rust

| Column | Meaning |
|---|---|
| `trajectory_diff` | Career-trajectory (improving vs declining) differential. |
| `elo_form_divergence_a`, `elo_form_divergence_b` | Divergence of recent form from Elo per fighter. |
| `age_curve_a`, `age_curve_b`, `age_curve_diff` | Position on the aging curve; differential. |
| `prime_mismatch` | Are the fighters at different points of their primes. |
| `rust_a`, `rust_b`, `rust_diff`, `favourite_rusty` | Layoff/rust per fighter, differential, and a flag when the favourite is rusty. |
| `fr1_danger_diff` | First-round danger differential. |
| `a_upset_risk_score` | Composite upset-risk score for A. |

## Tier-2 — GMM archetype clusters (K=7)

`cluster_a_0`, `cluster_a_1`, `cluster_a_2`, `cluster_a_3`, `cluster_a_4`, `cluster_a_5`,
`cluster_a_6` and `cluster_b_0`, `cluster_b_1`, `cluster_b_2`, `cluster_b_3`, `cluster_b_4`,
`cluster_b_5`, `cluster_b_6`: soft GMM membership probabilities (per fighter, sum to 1) over 7
data-driven clusters. Fitted strictly on
training-period fighter vectors (`scripts/fit_archetypes.py` → `cluster_model.pkl`) and applied
without refit to val/test. `cluster_*_2` are among the highest-gain features in the win/loss head.

## Optional odds feature (not in the shipped no-odds model)

| Column | Meaning |
|---|---|
| `implied_prob_a` | Vig-removed closing-line implied P(A). NaN when unavailable. The headline metrics are the **no-odds** model; adding odds is the staged AUC lever (see `docs/MODEL_STATUS.md §4`). |

## Edge cases

- **Debut / regional imports.** UFC-only history → little/no data; decayed stats fall back to
  defaults and the fight is flagged via `predict_fight()` `warnings`. The model degrades or
  abstains on debutant-heavy cards.
- **Long layoff.** `days_inactive` large → Elo decay applies; `rust_*` fire; flagged.
- **Weight-class change / short notice.** No dedicated feature yet (known blind spot,
  `docs/MODEL_STATUS.md §3`).
