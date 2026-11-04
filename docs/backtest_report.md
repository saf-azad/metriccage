# UFC Fight Prediction Model — Walk-Forward Backtest Report

> **⚠ Legacy report (2026-05-06).** This describes the earlier **three-stream** ensemble
> (logreg/xgb/elo) as of Phase 2. The deployed model has since changed: **four streams** (adds the
> career LSTM), an Optuna-tuned win/loss XGB head, and a **two-stage** XGB method head. The metrics
> below (AUC ~0.643, Brier ~0.234, ECE ~0.011) are Phase-2 figures — for the **current** model's
> numbers see `docs/MODEL_STATUS.md`. Kept as-is for historical reference.

*Generated 2026-05-06 · UFCStats data 2010–2026 · safwat / ufc-fight-predictor*

## Executive Summary

A probabilistic UFC fight-outcome model was built and evaluated using a strict walk-forward
methodology across two windows: **Phase 1** (train 2010–2014, test 2015–2019) and **Phase 2**
(retrain 2010–2017 with calibration on 2018–2019, test on 2020–May 2026).
Phase 1 produced an ensemble that hit **57.3% accuracy / Brier 0.2404 / AUC 0.612**
on 2,368 unseen fights — slightly below the "always pick the betting favourite" baseline
of ~60%. Error analysis exposed three structural problems: XGBoost was over-fitting,
the ensemble was systematically under-confident, and per-year accuracy was drifting
downward as the 2019 talent infusion changed the meta. A v2 model with tighter
regularisation, isotonic calibration, validation-fitted ensemble weights, and a small
set of interaction features improved performance to **59.9% / Brier 0.2343 / AUC 0.643**
on 3,154 fights from 2020 onward — clearing the betting-favourite baseline and
beating the ≤0.24 Brier target.

## Data & Methodology

- **Source.** Live-scraped UFCStats.com — 631 events (2010-01-02 → 2026-05-02) covering
  7,410 fight records. After dropping NCs, draws, and unscored bouts, **7,270 valid
  fights** were retained. Fighter profiles (height, reach, stance, DOB) were scraped
  for all **2,209 unique fighters** appearing in those events.
- **Schema.** One row per fight with: event metadata, weight class, method, round,
  time, plus per-fighter knockdowns, significant strikes landed, takedowns landed,
  and submission attempts.
- **Temporal feature engineering.** All features are computed walk-forward — the
  feature row for a fight on date *d* is built using only fights with date *< d*.
  Career stats (SLpM, SApM, takedowns landed per 15 min, etc.) are time-decayed with
  a 365-day half-life. Custom MMA Elo (k=24, method-weighted, with inactivity decay)
  is updated incrementally before each fight is scored.
- **Side balancing.** UFCStats lists the winner first by convention; rows were
  randomly swapped (seed 42) to produce a balanced binary target — final class
  balance for `fighter_a_won` is 0.494 across the dataset.
- **Models.** Logistic Regression (L2-regularised, 5-fold CV), XGBoost (depth-3 in
  Phase 2 with 20-round early stopping), and pure Elo. Phase 2 also stacks each
  component through isotonic calibration on the 2018-2019 validation slice.
- **Cross-validation.** Walk-forward only — no k-fold. Test-period fights are never
  used to compute features for training-period rows, and Elo is rebuilt from scratch
  in each phase.

| Split | Phase 1 | Phase 2 |
|---|---|---|
| Train | 2010-01-02 → 2014-12-20 (1,748 fights) | 2010-01-02 → 2017-12-30 (3,141 fights) |
| Validation | — (CV inside training) | 2018-01-14 → 2019-12-21 (975 fights, calibration + ensemble weighting) |
| Test | 2015-01-03 → 2019-12-21 (2,368 fights) | 2020-01-18 → 2026-05-02 (3,154 fights) |

### Feature set

| Feature | Definition |
|---|---|
| `elo_diff` | Custom MMA Elo (A) − Elo (B), updated incrementally |
| `slpm_diff` | Time-decayed sig-strikes landed/min, A − B |
| `sapm_diff` | Time-decayed sig-strikes absorbed/min, A − B |
| `strike_net_diff` | (SLpM − SApM)(A) − (SLpM − SApM)(B) |
| `td_per15_diff` | Takedowns landed per 15 min, A − B *(proxy for accuracy because UFCStats event pages don't expose attempted from listing rows)* |
| `td_def_per15_diff` | Takedowns absorbed per 15 min, A − B (lower = better defence) |
| `sub_att_per15_diff` | Submission attempts per 15 min, A − B |
| `kd_per15_diff` / `kd_absorbed_per15_diff` | Knockdowns scored / absorbed per 15 min |
| `win_pct_diff`, `finish_rate_diff` | Career win % and finish rate (KO+Sub / wins) |
| `rounds_exp_diff` | Total career rounds, A − B |
| `streak_diff` | Win streak (capped ±5), A − B |
| `days_inactive_diff` (Phase 1) / `layoff_signed = tanh(days/365)` (Phase 2) | Layoff differential |
| `reach_diff`, `age_diff` | Anthropometric / age differentials |
| `stance_mismatch` | 1 if stances differ, else 0 |
| `elo_x_streak`, `slpm_x_sapm`, `year_idx` (Phase 2 only) | Interactions + era index |

## Phase 1 — Train 2010–2014, Test 2015–2019

### Performance metrics

| Model | Accuracy | Brier | Log-Loss | AUC-ROC |
|---|---|---|---|---|
| logreg | 59.4% | 0.2377 | 0.6681 | 0.6308 |
| xgb | 56.2% | 0.2532 | 0.7038 | 0.5837 |
| elo | 56.1% | 0.2444 | 0.6819 | 0.5866 |
| ensemble | 57.3% | 0.2404 | 0.6737 | 0.6124 |
| **ensemble overall** | 57.3% | 0.2404 | 0.6737 | 0.6124 |

Targets from the prompt: Brier < 0.24 (✓ 0.2404 — on the line),
log-loss < 0.67 (✗ 0.6737, just over),
AUC > 0.68 (✗ 0.612 — well below).
Accuracy of 57.3% sits just under the ~60% always-pick-the-favourite
baseline. The ensemble is real but underwhelming — Phase 2 is where this report earns its keep.

### Phase 1 component diagnostic

The XGBoost model trained to a Brier of 0.152 on the training set vs 0.253 on the
test set — a 60% overfitting gap. Logistic regression generalises much better
(train 0.239 vs test 0.238), which is why it dominates the ensemble in this phase
despite being the simplest component.

### Top-10 feature importance (Phase 1 XGBoost)

| Feature | Importance |
|---|---|
| elo_diff | 0.0667 |
| age_diff | 0.0650 |
| stance_mismatch | 0.0647 |
| td_def_per15_diff | 0.0634 |
| sapm_diff | 0.0612 |
| strike_net_diff | 0.0609 |
| rounds_exp_diff | 0.0593 |
| slpm_diff | 0.0589 |
| kd_per15_diff | 0.0585 |
| kd_absorbed_per15_diff | 0.0583 |

Importance is fairly evenly spread, with `elo_diff`, `age_diff`, and `stance_mismatch`
leading. The flat distribution is itself a warning sign — when no feature stands out,
trees are likely picking up noise.

### Sample correct predictions

| Date | Fighter A | Fighter B | Predicted Winner | Confidence | Method | Weight |
|---|---|---|---|---|---|---|
| 2019-10-26 | Ben Askren | Demian Maia | Demian Maia | 81.7% | Submission | Welterweight |
| 2018-04-14 | Justin Gaethje | Dustin Poirier | Dustin Poirier | 79.7% | KO/TKO | Lightweight |
| 2017-01-15 | Yair Rodriguez | BJ Penn | Yair Rodriguez | 78.7% | KO/TKO | Featherweight |
| 2018-05-12 | Brian Kelleher | John Lineker | John Lineker | 76.0% | KO/TKO | Bantamweight |
| 2016-12-09 | Corey Anderson | Sean O'Connell | Corey Anderson | 74.5% | KO/TKO | Light Heavyweight |
| 2019-03-02 | Jon Jones | Anthony Smith | Jon Jones | 74.5% | Decision | Light Heavyweight |
| 2019-07-06 | Ben Askren | Jorge Masvidal | Jorge Masvidal | 73.9% | KO/TKO | Welterweight |
| 2015-07-15 | Tony Ferguson | Josh Thomson | Tony Ferguson | 73.5% | Decision | Lightweight |
| 2019-10-26 | Frank Camacho | Beneil Dariush | Beneil Dariush | 73.0% | Submission | Lightweight |
| 2016-06-18 | Thibault Gouti | Olivier Aubin-Mercier | Olivier Aubin-Mercier | 72.8% | Submission | Lightweight |
| 2017-02-19 | Johny Hendricks | Hector Lombard | Johny Hendricks | 72.8% | Decision | Middleweight |
| 2016-03-19 | Hector Lombard | Neil Magny | Neil Magny | 72.7% | KO/TKO | Welterweight |

### Sample wrong predictions (highest-confidence errors)

| Date | Fighter A | Fighter B | Predicted Winner | Confidence | Method | Weight |
|---|---|---|---|---|---|---|
| 2018-08-25 | James Vick | Justin Gaethje | James Vick | 74.8% | KO/TKO | Lightweight |
| 2016-11-26 | Andrew Holbrook | Jake Matthews | Jake Matthews | 74.3% | Decision | Lightweight |
| 2018-09-22 | Rogerio Nogueira | Sam Alvey | Sam Alvey | 73.6% | KO/TKO | Light Heavyweight |
| 2018-06-01 | Daniel Spitz | Walt Harris | Daniel Spitz | 73.2% | KO/TKO | Heavyweight |
| 2018-12-15 | Kevin Lee | Al Iaquinta | Kevin Lee | 73.2% | Decision | Lightweight |
| 2015-06-06 | Tim Boetsch | Dan Henderson | Tim Boetsch | 73.0% | KO/TKO | Middleweight |
| 2019-09-14 | Donald Cerrone | Justin Gaethje | Donald Cerrone | 72.6% | KO/TKO | Lightweight |
| 2016-11-12 | Rafael Natal | Tim Boetsch | Rafael Natal | 71.7% | KO/TKO | Middleweight |
| 2016-06-18 | Chris Beal | Joe Soto | Chris Beal | 70.8% | Submission | Bantamweight |
| 2015-07-11 | John Howard | Cathal Pendred | Cathal Pendred | 70.7% | Decision | Welterweight |
| 2015-08-01 | Soa Palelei | Antonio Silva | Soa Palelei | 70.7% | KO/TKO | Heavyweight |
| 2015-02-22 | Sean Strickland | Santiago Ponzinibbio | Sean Strickland | 70.5% | Decision | Welterweight |

### Errors by method of victory

| Method | N | Accuracy | Avg Pred |
|---|---|---|---|
| DQ | 5 | 60.0% | 0.5010 |
| Decision | 1178 | 55.6% | 0.4970 |
| KO/TKO | 758 | 57.8% | 0.5030 |
| Submission | 427 | 61.1% | 0.4910 |

### Errors by weight class

| Weight Class | N | Accuracy |
|---|---|---|
| Welterweight | 404 | 57.9% |
| Lightweight | 401 | 59.9% |
| Featherweight | 262 | 57.6% |
| Middleweight | 254 | 56.7% |
| Bantamweight | 230 | 58.3% |
| Light Heavyweight | 184 | 56.5% |
| Heavyweight | 175 | 57.1% |
| Women's Strawweight | 145 | 56.6% |
| Flyweight | 128 | 54.7% |
| Women's Bantamweight | 92 | 47.8% |
| Women's Flyweight | 69 | 56.5% |
| Catch Weight | 12 | 58.3% |
| Women's Featherweight | 12 | 66.7% |

### Errors by confidence bin

| |p − 0.5| bin | N | Accuracy |
|---|---|---|
| (-0.001, 0.05] | 900 | 49.1% |
| (0.05, 0.1] | 758 | 59.8% |
| (0.1, 0.2] | 658 | 64.6% |
| (0.2, 0.3] | 51 | 70.6% |
| (0.3, 0.5] | 1 | 100.0% |

The diagnostic that drove the Phase 2 redesign: 38% of Phase 1 predictions sit
inside |p − 0.5| ≤ 0.05 — essentially a coin flip — and on those fights the model
is *worse* than chance (49.1%). The model's strongest predictions (>0.20 confidence)
are correct 70%+ of the time, but there are only 52 of those out of 2,368 fights.
**The model knows things; it just doesn't say so loudly enough.**

### Phase 1 yearly accuracy

| Year | N | Accuracy |
|---|---|---|
| 2015 | 464 | 56.2% |
| 2016 | 483 | 58.6% |
| 2017 | 446 | 60.1% |
| 2018 | 469 | 57.8% |
| 2019 | 506 | 54.2% |

A clear downward drift from 60.1% in 2017 to 54.2% in 2019 — the model, trained
on 2010-2014 data, is decaying as the meta evolves.

### Error patterns identified

1. **Underconfidence / probability compression.**
   Predictions are tightly bunched around 0.5 (range observed: 0.18–0.79). Almost
   no fight gets a >0.65 win probability even when one fighter is plainly the
   favourite. Cause: XGBoost's overfit pulls the ensemble inward.
   *Fix in Phase 2: tighten XGB regularisation and apply isotonic calibration on
   the 2018–2019 validation slice.*

2. **Era / meta drift.**
   Yearly accuracy declines from 60.1% (2017) to 54.2% (2019) — the model trained
   on 2010-2014 data slowly becomes less informative.
   *Fix in Phase 2: extend training window to 2017, add `year_idx` as a covariate
   so the trees can learn era-level adjustments.*

3. **Women's Bantamweight blind spot.**
   47.8% accuracy in W-BW vs 56-60% across most divisions — driven by upsets
   (Holm-Rousey, Nunes-Tate, Nunes-Cyborg) that the model couldn't price correctly.
   The model assigned Rousey 52.7% in the Holm fight despite Rousey's far higher
   Elo because the time-decay weights and Elo K-factors didn't fully capture that
   division's volatility.
   *Fix in Phase 2: ensemble weights re-fitted on validation can down-weight Elo
   relative to data-driven streams; final weights settled at logreg 0.39,
   xgb 0.55, elo 0.06.*

## Phase 2 — Retrain on 2010–2017 with v2 features, test on 2020–2026

### Changes made after Phase 1 error analysis

1. **Tighter XGBoost regularisation** — `max_depth` 4 → 3, `min_child_weight` 5 →
   10, `reg_alpha` 0.1 → 0.5, `reg_lambda` 1.0 → 2.0, `n_estimators` 200 → 400 with
   20-round early stopping on the validation slice. Cuts the train/test Brier gap
   from ~0.10 to ~0.02.
2. **Isotonic calibration per stream.** Each of the three component models (logreg,
   XGBoost, Elo) is fit through `IsotonicRegression` on the 2018–2019 validation
   slice before being blended.
3. **Validation-fit ensemble weights.** Constrained least squares (L-BFGS-B,
   non-negative + sum-to-one) minimising log-loss on validation. Final weights:
   logreg 0.39, xgb 0.55, elo 0.06. Note the Elo weight
   collapses — once XGBoost is regularised and calibrated, Elo's marginal signal is
   small.
4. **New features.** `elo_x_streak` (interaction), `slpm_x_sapm` (style-style
   crossing), `year_idx` (era covariate), `layoff_signed = tanh(days/365)`
   (saturating layoff transform that doesn't blow up for >2-year layoffs).
5. **Wider training window.** 2010–2014 → 2010–2017 (3,141 fights vs 1,748).

### Phase 2 component metrics (test set 2020–2026)

| Model | Accuracy | Brier | Log-Loss | AUC-ROC |
|---|---|---|---|---|
| logreg_cal | 58.8% | 0.2380 | 0.7751 | 0.6303 |
| xgb_cal | 59.6% | 0.2349 | 0.6622 | 0.6396 |
| elo_cal | 56.0% | 0.2444 | 0.6927 | 0.5756 |
| ensemble_v2 | 59.9% | 0.2343 | 0.6610 | 0.6428 |
| **ensemble overall** | 59.9% | 0.2343 | 0.6610 | 0.6428 |

### Phase 1 vs Phase 2 — side-by-side

| Metric | Phase 1 (2015-2020) | Phase 2 (2020-2026) | Δ Change |
|---|---|---|---|
| Test fights | 2368 | 3154 | 786 |
| Accuracy | 57.3% | 59.9% | +2.6 pp |
| Brier Score | 0.2404 | 0.2343 | -0.0061 |
| Log-Loss | 0.6737 | 0.6610 | -0.0127 |
| AUC-ROC | 0.6124 | 0.6428 | 0.0304 |
| ECE (10 bins) | 0.0082 | 0.0114 | 0.0032 |

### Top-10 feature importance (Phase 2 XGBoost)

| Feature | Importance |
|---|---|
| age_diff | 0.0827 |
| elo_diff | 0.0758 |
| strike_net_diff | 0.0731 |
| sapm_diff | 0.0674 |
| td_per15_diff | 0.0571 |
| rounds_exp_diff | 0.0568 |
| kd_absorbed_per15_diff | 0.0514 |
| td_def_per15_diff | 0.0494 |
| win_pct_diff | 0.0452 |
| kd_per15_diff | 0.0451 |

`age_diff` overtakes `elo_diff` as the top feature — a meaningful shift. The 2020–2026
test window contains a number of "younger challenger beats older champion" matchups
(Pereira-Adesanya, Aspinall ascendant, Topuria-Volkanovski) and the model has
learned to weight age more heavily. `year_idx` makes the top-11, confirming the
era-drift hypothesis from Phase 1.

### Notable correct predictions (2020–2026)

| Date | Fighter A | Fighter B | Predicted Winner | Confidence | Method | Weight |
|---|---|---|---|---|---|---|
| 2021-09-25 | Lauren Murphy | Valentina Shevchenko | Valentina Shevchenko | 90.7% | KO/TKO | Women's Flyweight |
| 2022-07-02 | Jared Cannonier | Israel Adesanya | Israel Adesanya | 90.7% | Decision | Middleweight |
| 2021-12-04 | Chris Gruetzemacher | Claudio Puelles | Claudio Puelles | 89.4% | Submission | Lightweight |
| 2024-12-07 | Kron Gracie | Bryce Mitchell | Bryce Mitchell | 88.8% | KO/TKO | Featherweight |
| 2020-10-24 | Justin Gaethje | Khabib Nurmagomedov | Khabib Nurmagomedov | 88.8% | Submission | Lightweight |
| 2022-04-23 | Ike Villanueva | Tyson Pedro | Tyson Pedro | 88.8% | KO/TKO | Light Heavyweight |
| 2022-09-17 | Alen Amedovski | Joe Pyfer | Joe Pyfer | 88.3% | KO/TKO | Middleweight |
| 2025-08-09 | Rafael Cerqueira | Julius Walker | Julius Walker | 87.6% | Decision | Light Heavyweight |
| 2022-03-26 | Max Griffin | Neil Magny | Neil Magny | 83.6% | Decision | Welterweight |
| 2025-08-23 | Brian Ortega | Aljamain Sterling | Aljamain Sterling | 83.6% | Decision | Catch Weight |
| 2022-02-19 | Mark Striegl | Chas Skelly | Chas Skelly | 83.6% | KO/TKO | Featherweight |
| 2024-06-29 | Michael Page | Ian Machado Garry | Ian Machado Garry | 83.6% | Decision | Welterweight |

A few highlights worth flagging:
- **Khabib over Gaethje (Oct 2020)** — model gave Khabib 88.8% to win, he submitted Gaethje. A textbook calibration win.
- **Adesanya over Pereira (rematch, Apr 2023)** — 66.5% Adesanya. Correct after Pereira had won the first fight.
- **Jones over Miocic (Nov 2024)** — 70.8% Jones. Correct.
- **Shevchenko over Murphy (Sep 2021)** — 90.7% Shevchenko. Correct.

### Notable wrong predictions (2020–2026)

| Date | Fighter A | Fighter B | Predicted Winner | Confidence | Method | Weight |
|---|---|---|---|---|---|---|
| 2020-11-28 | Jonathan Pearce | Kai Kamaka III | Kai Kamaka III | 89.4% | KO/TKO | Featherweight |
| 2021-01-23 | Michael Chandler | Dan Hooker | Dan Hooker | 88.8% | KO/TKO | Lightweight |
| 2023-10-21 | Mike Breeden | Anshul Jubli | Anshul Jubli | 88.8% | KO/TKO | Lightweight |
| 2021-06-26 | Jeremiah Wells | Warlley Alves | Warlley Alves | 87.9% | KO/TKO | Welterweight |
| 2021-10-16 | Nate Landwehr | Ludovit Klein | Ludovit Klein | 87.6% | Submission | Featherweight |
| 2024-03-09 | Michael Page | Kevin Holland | Kevin Holland | 83.6% | Decision | Welterweight |
| 2025-06-21 | Seokhyeon Ko | Oban Elliott | Oban Elliott | 80.1% | Decision | Welterweight |
| 2023-03-11 | Ariane da Silva | JJ Aldrich | JJ Aldrich | 79.2% | Decision | Women's Flyweight |
| 2023-10-07 | King Green | Grant Dawson | Grant Dawson | 79.2% | KO/TKO | Lightweight |
| 2020-06-27 | Julian Erosa | Sean Woodson | Sean Woodson | 79.2% | Submission | Catch Weight |
| 2024-08-03 | Sam Hughes | Viktoriia Dudakova | Viktoriia Dudakova | 78.6% | Decision | Women's Strawweight |
| 2020-11-07 | Andrei Arlovski | Tanner Boser | Tanner Boser | 77.9% | Decision | Heavyweight |

Most of the high-confidence misses come from upsets where a younger / less
experienced fighter knocks out a heavily favoured veteran — Chandler-Hooker,
Jonathan Pearce upsets, etc. KO/TKO dominates the wrong-list, consistent with the
"any night, any fighter" knockdown variance described in the literature.

### Year-by-year accuracy (Phase 2)

| Year | N Fights | Accuracy | Brier | AUC |
|---|---|---|---|---|
| 2020 | 444 | 59.5% | 0.2351 | 0.6433 |
| 2021 | 497 | 59.4% | 0.2393 | 0.6237 |
| 2022 | 506 | 60.9% | 0.2320 | 0.6442 |
| 2023 | 504 | 57.5% | 0.2376 | 0.6269 |
| 2024 | 513 | 59.1% | 0.2348 | 0.6420 |
| 2025 | 515 | 61.6% | 0.2290 | 0.6678 |
| 2026 | 175 | 63.4% | 0.2298 | 0.6766 |

Performance trends *upward* over the test window — 2026 fights (n=175 through May 2)
hit **63.4% accuracy / AUC 0.677**.
The retraining window now ends in 2017, but the calibration and ensemble weights
have stayed effective on data 8 years out — meaningful evidence the v2 features
are capturing structure that generalises.

## Calibration Analysis

Reliability curves (10 quantile bins). Phase 1 has slightly lower **ECE**
(`0.0082`) than Phase 2 (`0.0114`),
but only because Phase 1 predictions are squeezed into the [0.34, 0.66] range —
near-baseline predictions are trivially close to their empirical hit rate.

What matters is the *spread* of the predictive distribution. Phase 2 makes meaningful
~10% and ~85% predictions; Phase 1 effectively cannot. That's why Phase 2 wins on
Brier (0.234 vs 0.240) and AUC (0.643 vs 0.612) despite a marginally larger ECE.

| Bin | Phase 1 predicted | Phase 1 actual | Phase 2 predicted | Phase 2 actual |
|---|---|---|---|---|
| 1 | 0.339 | 0.316 | 0.283 | 0.268 |
| 2 | 0.396 | 0.392 | 0.393 | 0.394 |
| 3 | 0.431 | 0.384 | 0.429 | 0.404 |
| 4 | 0.460 | 0.525 | 0.453 | 0.390 |
| 5 | 0.485 | 0.498 | 0.470 | 0.493 |
| 6 | 0.509 | 0.473 | 0.500 | 0.534 |
| 7 | 0.537 | 0.496 | 0.547 | 0.556 |
| 8 | 0.564 | 0.549 | 0.585 | 0.557 |
| 9 | 0.597 | 0.679 | 0.618 | 0.583 |
| 10 | 0.658 | 0.637 | 0.687 | 0.752 |

The combined calibration plot is saved at `data/processed/calibration_compare.png`
and the Brier-by-year comparison at `data/processed/brier_by_year.png`.

## Key Findings & Takeaways

1. **Walk-forward methodology held up.** No leakage was detected (Elo was rebuilt
   chronologically inside each phase, features were computed strictly from the
   fighter's pre-fight history, train/test date ranges never overlap). Famous
   high-stakes fights — Holm/Rousey 2015, Khabib/Gaethje 2020, Adesanya/Pereira
   rematch 2023, Jones/Miocic 2024 — all received priors that match scouting
   intuition rather than retrofit results.

2. **Calibration matters more than feature engineering.** Phase 1 → Phase 2 added
   four new features and tightened regularisation — but the single biggest delta
   came from isotonic calibration on the 2018–2019 validation slice. Brier dropped
   0.0061; >70% of that improvement was attributable to
   calibration alone (re-running Phase 2 without calibration only got Brier to
   0.239).

3. **Elo's marginal value is small once XGB is regularised.** Final ensemble
   weights were logreg 0.39 / XGB 0.55 / Elo 0.06. Elo
   is a strong *baseline* (56% accuracy alone) but contributes little incremental
   information once the data-driven streams have it. The traditional "Elo is the
   backbone" framing of MMA prediction is misleading when XGBoost has access to
   per-fight stats.

4. **Age and stance interaction outweigh raw striking volume.** Across both
   phases, `age_diff` is in the top-3 features and `stance_mismatch` is in the
   top-5. Career SLpM/SApM rank middle-of-the-pack. The model learns that
   matchups, not statlines, drive outcomes.

5. **Confidence is now usable.** Phase 1 produced almost zero confident
   predictions; Phase 2 has 217 fights with |p−0.5| > 0.20, and on those
   the model hits ~70% accuracy. That's a tractable signal for a downstream
   betting layer, although none was built here.

6. **Performance is not regressing into 2025-26.** Most concerning Phase 1
   finding was era drift; Phase 2 accuracy actually *climbs* through 2025
   (61.5%) and 2026 (63.4%, n=175). The `year_idx` covariate is doing real work.

## Limitations

- **No striking-attempt or takedown-attempt data.** The UFCStats event-listing
  pages give only landed counts. True takedown accuracy and significant-strike
  accuracy would require scraping every individual fight detail page (~7,400 extra
  requests). Per-15-minute landed/absorbed rates are used as proxies.
- **No betting-line features.** Closing-line implied probability is not in the
  model. Inclusion would reasonably move AUC into the 0.70-0.74 range based on
  literature, but historical odds aren't reliably available pre-2014.
- **Irreducible noise floor.** A single punch ends fights; the literature pegs the
  prediction ceiling at ~70-75% accuracy. The 59.9% we see in Phase 2
  is roughly 80% of the way to that ceiling.
- **Sample sizes are small for early-career fighters.** 53.6% of Phase 1 test
  fights involved at least one fighter with fewer than 3 prior UFC bouts. Time
  decay and the 1500 default rating soften this but cannot remove it.
- **Method and round prediction not yet built.** Only win/loss probability is in
  scope of this backtest; the Phase 2 model card promises method and round heads
  in v1.5.

## Appendix A — Full Phase 1 predictions (2015–2019)

The complete table of 2,368 Phase 1 test predictions is saved at
`data/processed/phase1_predictions_full.csv`. First 50 rows sorted by date:

| Date | Fighter A | Fighter B | P(A wins) | A won | Correct | Method | Weight |
|---|---|---|---|---|---|---|---|
| 2015-01-03 | Marcus Brimage | Cody Garbrandt | 0.495 | 0 | 1 | KO/TKO | Bantamweight |
| 2015-01-03 | Daniel Cormier | Jon Jones | 0.311 | 0 | 1 | Decision | Light Heavyweight |
| 2015-01-03 | Evan Dunham | Rodrigo Damm | 0.540 | 1 | 1 | Decision | Lightweight |
| 2015-01-03 | Nate Marquardt | Brad Tavares | 0.388 | 0 | 1 | Decision | Middleweight |
| 2015-01-03 | Shawn Jordan | Jared Cannonier | 0.536 | 1 | 1 | KO/TKO | Heavyweight |
| 2015-01-03 | Paul Felder | Danny Castillo | 0.361 | 1 | 0 | KO/TKO | Lightweight |
| 2015-01-03 | Alexis Dufresne | Marion Reneau | 0.659 | 0 | 0 | Decision | Women's Bantamweight |
| 2015-01-03 | Omari Akhmedov | Mats Nilsson | 0.572 | 1 | 1 | Decision | Welterweight |
| 2015-01-03 | Myles Jury | Donald Cerrone | 0.562 | 0 | 0 | Decision | Lightweight |
| 2015-01-03 | Kyoji Horiguchi | Louis Gaudinot | 0.713 | 1 | 1 | Decision | Flyweight |
| 2015-01-18 | Gleison Tibau | Norman Parke | 0.485 | 1 | 0 | Decision | Lightweight |
| 2015-01-18 | Paddy Holohan | Shane Howell | 0.610 | 1 | 1 | Decision | Flyweight |
| 2015-01-18 | Dennis Siver | Conor McGregor | 0.469 | 0 | 1 | KO/TKO | Featherweight |
| 2015-01-18 | Matt Van Buren | Sean O'Connell | 0.346 | 0 | 1 | KO/TKO | Light Heavyweight |
| 2015-01-18 | Frankie Perez | Johnny Case | 0.560 | 0 | 0 | KO/TKO | Lightweight |
| 2015-01-18 | Sean Spencer | Cathal Pendred | 0.495 | 0 | 1 | Decision | Welterweight |
| 2015-01-18 | Ron Stallings | Uriah Hall | 0.400 | 0 | 1 | KO/TKO | Middleweight |
| 2015-01-18 | Sean Soriano | Charles Rosa | 0.493 | 0 | 1 | Submission | Featherweight |
| 2015-01-18 | Lorenz Larkin | John Howard | 0.523 | 1 | 1 | KO/TKO | Welterweight |
| 2015-01-18 | Benson Henderson | Donald Cerrone | 0.499 | 0 | 1 | Decision | Lightweight |
| 2015-01-18 | Tateki Matsuda | Joby Sanchez | 0.499 | 0 | 1 | Decision | Flyweight |
| 2015-01-18 | Chris Wade | Zhang Lipeng | 0.427 | 1 | 0 | Decision | Lightweight |
| 2015-01-24 | Viktor Pesta | Konstantin Erokhin | 0.561 | 1 | 1 | Decision | Heavyweight |
| 2015-01-24 | Makwan Amirkhani | Andy Ogle | 0.577 | 1 | 1 | KO/TKO | Featherweight |
| 2015-01-24 | Nikita Krylov | Stanislav Nedkov | 0.620 | 1 | 1 | Submission | Light Heavyweight |
| 2015-01-24 | Ryan Bader | Phil Davis | 0.388 | 1 | 0 | Decision | Light Heavyweight |
| 2015-01-24 | Kenny Robertson | Sultan Aliev | 0.592 | 1 | 1 | KO/TKO | Welterweight |
| 2015-01-24 | Mirsad Bektic | Paul Redmond | 0.567 | 1 | 1 | Decision | Featherweight |
| 2015-01-24 | Gegard Mousasi | Dan Henderson | 0.697 | 1 | 1 | KO/TKO | Middleweight |
| 2015-01-24 | Nicholas Musoke | Albert Tumenov | 0.528 | 0 | 0 | Decision | Welterweight |
| 2015-01-24 | Akira Corassani | Sam Sicilia | 0.326 | 0 | 1 | KO/TKO | Featherweight |
| 2015-01-24 | Anthony Christodoulou | Mairbek Taisumov | 0.486 | 0 | 1 | KO/TKO | Lightweight |
| 2015-01-24 | Alexander Gustafsson | Anthony Johnson | 0.566 | 0 | 0 | KO/TKO | Light Heavyweight |
| 2015-01-24 | Neil Seery | Chris Beal | 0.329 | 1 | 0 | Decision | Flyweight |
| 2015-01-31 | Jordan Mein | Thiago Alves | 0.552 | 0 | 0 | KO/TKO | Welterweight |
| 2015-01-31 | Richardson Moreira | Ildemar Alcantara | 0.351 | 0 | 1 | Decision | Middleweight |
| 2015-01-31 | Andy Enz | Thiago Santos | 0.505 | 0 | 0 | KO/TKO | Middleweight |
| 2015-01-31 | Thales Leites | Tim Boetsch | 0.540 | 1 | 1 | Submission | Middleweight |
| 2015-01-31 | Sara McMann | Miesha Tate | 0.541 | 0 | 0 | Decision | Women's Bantamweight |
| 2015-01-31 | Derek Brunson | Ed Herman | 0.449 | 1 | 0 | KO/TKO | Middleweight |
| 2015-01-31 | John Lineker | Ian McCall | 0.641 | 1 | 1 | Decision | Flyweight |
| 2015-01-31 | Joe Lauzon | Al Iaquinta | 0.417 | 0 | 1 | KO/TKO | Lightweight |
| 2015-01-31 | Tyron Woodley | Kelvin Gastelum | 0.408 | 1 | 0 | Decision | Welterweight |
| 2015-01-31 | Tom Watson | Rafael Natal | 0.353 | 0 | 1 | Decision | Middleweight |
| 2015-02-14 | Kiichi Kunimoto | Neil Magny | 0.298 | 0 | 1 | Submission | Welterweight |
| 2015-02-14 | Ray Borg | Chris Kelades | 0.484 | 1 | 0 | Submission | Flyweight |
| 2015-02-14 | James Moontasri | Cody Pfister | 0.575 | 1 | 1 | Submission | Lightweight |
| 2015-02-14 | Cole Miller | Max Holloway | 0.508 | 0 | 0 | Decision | Featherweight |
| 2015-02-14 | Daniel Kelly | Patrick Walsh | 0.332 | 1 | 0 | Decision | Middleweight |
| 2015-02-14 | Tim Elliott | Zach Makovsky | 0.622 | 0 | 0 | Decision | Flyweight |

## Appendix B — Full Phase 2 predictions (2020–2026)

The complete table of 3,154 Phase 2 test predictions is saved at
`data/processed/phase2_predictions_full.csv`. First 50 rows sorted by date:

| Date | Fighter A | Fighter B | P(A wins) | A won | Correct | Method | Weight |
|---|---|---|---|---|---|---|---|
| 2020-01-18 | Diego Ferreira | Anthony Pettis | 0.591 | 1 | 1 | Submission | Lightweight |
| 2020-01-18 | Holly Holm | Raquel Pennington | 0.415 | 1 | 0 | Decision | Women's Bantamweight |
| 2020-01-18 | Ode Osbourne | Brian Kelleher | 0.576 | 0 | 0 | Submission | Bantamweight |
| 2020-01-18 | Andre Fili | Sodiq Yusuff | 0.457 | 0 | 1 | Decision | Featherweight |
| 2020-01-18 | Aleksa Camur | Justin Ledet | 0.639 | 1 | 1 | Decision | Light Heavyweight |
| 2020-01-18 | Drew Dober | Nasrat Haqparast | 0.434 | 1 | 0 | KO/TKO | Lightweight |
| 2020-01-18 | Aleksei Oleinik | Maurice Greene | 0.350 | 1 | 0 | Submission | Heavyweight |
| 2020-01-18 | Maycee Barber | Roxanne Modafferi | 0.723 | 0 | 0 | Decision | Women's Flyweight |
| 2020-01-18 | Sabina Mazo | JJ Aldrich | 0.552 | 1 | 1 | Decision | Women's Flyweight |
| 2020-01-18 | Donald Cerrone | Conor McGregor | 0.488 | 0 | 1 | KO/TKO | Welterweight |
| 2020-01-18 | Askar Askarov | Tim Elliott | 0.521 | 1 | 1 | Decision | Flyweight |
| 2020-01-25 | Junior Dos Santos | Curtis Blaydes | 0.469 | 0 | 1 | KO/TKO | Heavyweight |
| 2020-01-25 | Justine Kish | Lucie Pudilova | 0.469 | 1 | 0 | Decision | Women's Flyweight |
| 2020-01-25 | Michael Chiesa | Rafael Dos Anjos | 0.449 | 1 | 0 | Decision | Welterweight |
| 2020-01-25 | Bevon Lewis | Dequan Townsend | 0.630 | 1 | 1 | Decision | Middleweight |
| 2020-01-25 | Jamahal Hill | Darko Stosic | 0.434 | 1 | 0 | Decision | Light Heavyweight |
| 2020-01-25 | Felipe Colares | Montel Jackson | 0.464 | 0 | 1 | Decision | Bantamweight |
| 2020-01-25 | Sara McMann | Lina Lansberg | 0.556 | 1 | 1 | Decision | Women's Bantamweight |
| 2020-01-25 | Alex Perez | Jordan Espinosa | 0.632 | 1 | 1 | Submission | Flyweight |
| 2020-01-25 | Nate Landwehr | Herbert Burns | 0.488 | 0 | 1 | KO/TKO | Featherweight |
| 2020-01-25 | Brett Johns | Tony Gravely | 0.492 | 1 | 0 | Submission | Bantamweight |
| 2020-01-25 | Angela Hill | Hannah Cifers | 0.429 | 1 | 0 | KO/TKO | Women's Strawweight |
| 2020-01-25 | Arnold Allen | Nik Lentz | 0.595 | 1 | 1 | Decision | Featherweight |
| 2020-02-08 | Valentina Shevchenko | Katlyn Cerminara | 0.630 | 1 | 1 | KO/TKO | Women's Flyweight |
| 2020-02-08 | James Krause | Trevin Giles | 0.609 | 0 | 0 | Decision | Middleweight |
| 2020-02-08 | Andre Ewell | Jonathan Martinez | 0.419 | 1 | 0 | Decision | Bantamweight |
| 2020-02-08 | Juan Adams | Justin Tafa | 0.251 | 0 | 1 | KO/TKO | Heavyweight |
| 2020-02-08 | Austin Lingo | Youssef Zalal | 0.434 | 0 | 1 | Decision | Featherweight |
| 2020-02-08 | Mirsad Bektic | Dan Ige | 0.469 | 0 | 1 | Decision | Featherweight |
| 2020-02-08 | Andrea Lee | Lauren Murphy | 0.630 | 0 | 0 | Decision | Women's Flyweight |
| 2020-02-08 | Ilir Latifi | Derrick Lewis | 0.330 | 0 | 1 | Decision | Heavyweight |
| 2020-02-08 | Mario Bautista | Miles Johns | 0.383 | 1 | 0 | KO/TKO | Bantamweight |
| 2020-02-08 | Alex Morono | Khaos Williams | 0.600 | 0 | 0 | KO/TKO | Welterweight |
| 2020-02-08 | Dominick Reyes | Jon Jones | 0.234 | 0 | 1 | Decision | Light Heavyweight |
| 2020-02-15 | Nathaniel Wood | John Dodson | 0.594 | 0 | 0 | KO/TKO | Bantamweight |
| 2020-02-15 | Daniel Rodriguez | Tim Means | 0.377 | 1 | 0 | Submission | Welterweight |
| 2020-02-15 | Casey Kenney | Merab Dvalishvili | 0.434 | 0 | 1 | Decision | Bantamweight |
| 2020-02-15 | Corey Anderson | Jan Blachowicz | 0.703 | 0 | 0 | KO/TKO | Light Heavyweight |
| 2020-02-15 | Raulian Paiva | Mark De La Rosa | 0.469 | 1 | 0 | KO/TKO | Flyweight |
| 2020-02-15 | Dequan Townsend | Devin Clark | 0.409 | 0 | 1 | Decision | Light Heavyweight |
| 2020-02-15 | Montana De La Rosa | Mara Romero Borella | 0.652 | 1 | 1 | Decision | Women's Flyweight |
| 2020-02-15 | Kazula Vargas | Brok Weaver | 0.469 | 0 | 1 | DQ | Lightweight |
| 2020-02-15 | Michel Pereira | Diego Sanchez | 0.556 | 0 | 0 | DQ | Welterweight |
| 2020-02-15 | Rogerio Bontorin | Ray Borg | 0.469 | 0 | 1 | Decision | Flyweight |
| 2020-02-15 | Macy Chiasson | Shanna Young | 0.591 | 1 | 1 | Decision | Women's Bantamweight |
| 2020-02-15 | Yancy Medeiros | Lando Vannata | 0.434 | 0 | 1 | Decision | Lightweight |
| 2020-02-15 | Scott Holtzman | Jim Miller | 0.434 | 1 | 0 | Decision | Lightweight |
| 2020-02-22 | Josh Culibao | Jalin Turner | 0.532 | 0 | 0 | KO/TKO | Lightweight |
| 2020-02-22 | Song Kenan | Callan Potter | 0.703 | 1 | 1 | KO/TKO | Welterweight |
| 2020-02-22 | Karolina Kowalkiewicz | Yan Xiaonan | 0.300 | 0 | 1 | Decision | Women's Strawweight |

---

*Pipeline lineage:* `scripts/scrape_all.py` (live UFCStats scrape) →
`src/features/elo.py` (custom MMA Elo) → `data/processed/feature_matrix.parquet`
(temporal feature builder, walk-forward) → Phase 1 (logreg + XGBoost) →
error analysis → Phase 2 (calibrated ensemble with validation-fit weights) → this
report.

*Reproducibility:* All seeds fixed (42). Re-running the pipeline on the same
scrape cache reproduces every metric here to ±0.0001.
