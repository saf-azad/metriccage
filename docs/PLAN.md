# UFC Fight Predictor — Master Plan

> Status: blueprint v1.2 · Owner: safwat · Last updated: 2026-07-03 (reconciled with implementation)

This document is the **design intent**. For *what actually shipped and how well it scores*,
read [`MODEL_STATUS.md`](MODEL_STATUS.md) — the honest scoreboard. Where this plan and
reality diverged, the deltas are catalogued in **§14** rather than silently rewritten, so the
original design reasoning stays legible. Sections below carry inline `> Reality (2026-07-03):`
notes where the built system differs. Code lives in `src/`, exploration in `notebooks/`,
supporting docs in `docs/`. If anything here drifts from reality, fix the doc.

---

## 1. What we're building (in one paragraph)

A probabilistic UFC fight prediction system that, given two fighter names and a fight date, returns calibrated probabilities for **(a)** who wins, **(b)** the method of victory (KO/TKO, submission, decision), and **(c)** the round of any finish. The system is an ensemble of four models stacked on the same temporally-correct feature set: a custom MMA Elo, an XGBoost binary win/loss classifier, a Random Forest method classifier, and a PyTorch sequence model that reads each fighter's career as a time series. The four are blended into a final probability with isotonic calibration on a held-out validation slice. Success is measured by calibration (Brier, log-loss, ECE), not raw accuracy — picking the favourite already gets you ~60%, so accuracy is a misleading goalpost.

---

## 2. Why these design choices (decisions log)

| Decision | Choice | Why |
|---|---|---|
| Problem framing | Probabilistic forecasting, not classification | Calibration > accuracy. A model that says 70% and is right 70% of the time is a good model. |
| Model stack | Classical ensemble + PyTorch career sequence | Tabular MMA data favours boosted trees; the sequence model adds a "career arc" signal trees cannot capture (trajectory, recency dynamics). |
| Feature depth | Tier-1 + Elo + cluster (no stylistic deep-dive yet) | Get end-to-end pipeline working first. Stylistic features (clinch dependency, pace mismatch, KO susceptibility) added in v2 if calibration improves. |
| Cross-validation | Walk-forward (temporal) | Standard k-fold leaks the future. Predicting 2019 fights using 2023 data is cheating. |
| Calibration | Isotonic regression on validation slice | More flexible than Platt scaling; proven well-suited to ensemble outputs. |
| Bankroll / Kelly | Out of scope for v1 | The model's purpose is calibrated forecasting. Betting application would be a separate layer with its own risk controls. |

---

## 3. Success criteria

We are not chasing accuracy. We are chasing **calibration** and **discrimination**:

- **Brier score** on 2025 holdout < 0.225 (state-of-the-art is ~0.22–0.24).
- **Log-loss** on 2025 holdout below the closing-line implied-probability log-loss for non-main-event fights (the market is tougher to beat on main events).
- **Expected Calibration Error (ECE)** < 0.05 across 10 probability bins.
- **AUC-ROC** ≥ 0.74 on the holdout (without using closing odds as a feature; with odds, we expect 0.76+).
- **Method accuracy** > 52% on held-out finished fights.
- **Round MAE** < 0.9 rounds on fights that ended early.

If we hit all six on a true blind 2025 test set, the system is doing real work. If only accuracy moves while calibration stays flat, we have a confidence problem and the model is not deployable.

---

## 4. Data

### 4.1 Sources (in priority order)

1. **UFCStats.com** — all UFC fights since 2000. Round-by-round strikes, takedowns, control time, knockdowns. Gold standard. Scrape with rate limit 1.5s/request.
2. **BestFightOdds.com** — opening and closing American moneylines. Only used for benchmarking and as an optional feature; the model must work without odds because odds may not be available pre-fight.
3. **Tapology.com** — fight records, event info, debut/regional fights for fighters new to UFC. Used to seed Elo for debutants.
4. **Sherdog.com** — historical fallback for missing UFCStats records.

External APIs (paid, deferred): Pinnacle/Betfair sharp odds.

### 4.2 Temporal splits (no overlap, no leakage)

| Split | Date range | Purpose |
|---|---|---|
| Train | 2005-01-01 → 2022-12-31 | Fit Elo, GMM, XGBoost, RF, LSTM |
| Validation | 2023-01-01 → 2023-12-31 | Hyperparameter tuning, ensemble weights, calibration |
| Test (blind) | 2024-01-01 → 2025-05-04 | Reported metrics. Never touched during development. |

Every feature for a fight on date `d` must be computable using **only** data from before `d`. This is enforced in `src/features/build_matrix.py` by passing `as_of_date` into every feature function.

### 4.3 Storage

- `data/raw/` — scraped HTML, raw CSVs (gitignored).
- `data/interim/` — cleaned, typed, deduplicated parquet files.
- `data/processed/feature_matrix.parquet` — final feature table, one row per fight.
- `data/external/odds.parquet` — historical odds, joined when available.

---

## 5. Feature set

> **Reality (2026-07-03):** the shipped matrix is **102 features**, not the tier-1 shortlist
> below. The tier-1 core (Elo, striking, grappling, reach/age/streak/inactivity, stance) is all
> present — though several columns were renamed during implementation (`strike_diff_diff` →
> `strike_net_diff`, `td_acc_diff` → `td_per15_diff`, `sub_avg_diff` → `sub_att_per15_diff`,
> `win_streak_diff` → `streak_diff`, `stance_matchup` → `stance_mismatch`). Crucially, a whole
> **tier-2 stylistic/archetype block was added in UPDATE_2 (post-UFC 328) and IS in production**
> — the plan's "no stylistic micro-features yet" is out of date. See the tier-2 subsection below
> and the authoritative, exhaustive list in [`docs/feature_dictionary.md`](docs/feature_dictionary.md).
> GMM cluster membership shipped as **K=7** (`cluster_a_0..6` / `cluster_b_0..6`), not the
> expected K=8.

Every feature is computed for both fighters and entered as a **differential** (A − B) where
applicable. Time-decayed averages use a 365-day half-life.

| Feature | Formula | Source |
|---|---|---|
| `elo_diff` | Custom MMA Elo (A) − Elo (B) | Computed via `src/features/elo.py` |
| `slpm_diff` | Time-decayed sig strikes landed/min, A − B | UFCStats |
| `sapm_diff` | Time-decayed sig strikes absorbed/min, A − B | UFCStats |
| `strike_diff_diff` | (SLpM − SApM) for A minus same for B | Derived |
| `td_acc_diff` | Decayed TD accuracy, A − B | UFCStats |
| `td_def_diff` | Decayed TD defence, A − B | UFCStats |
| `sub_avg_diff` | Submission attempts per 15 min, A − B | UFCStats |
| `reach_diff` | Reach (in), A − B | UFCStats |
| `age_diff` | Age at fight date, A − B | Derived |
| `win_streak_diff` | min(streak, 5) for A − for B | Derived |
| `days_inactive_diff` | Days since last fight, A − B | Derived |
| `finish_rate_diff` | Career finish % (KO+Sub / total wins), A − B | Derived |
| `rounds_exp_diff` | Total career rounds, A − B | Derived |
| `stance_matchup` | 1 if stances differ (open stance), 0 otherwise | UFCStats |
| `cluster_a_*`, `cluster_b_*` | GMM membership probs (K=8 components) | `src/models/clustering.py` |
| `implied_prob_a` (optional) | Closing line implied probability after vig removal | BestFightOdds |

### Tier-2 stylistic / archetype block (IMPLEMENTED — added UPDATE_2, in production)

Originally deferred to v1.5, this block was built after the UFC 328 error analysis and now
feeds the deployed model (present in the bundle's `feats`, `xgb_feats`, and `method_feats`).
Code: `src/features/style_mismatch.py` + `src/features/archetypes.py`. Grouped summary (full
per-column definitions in `docs/feature_dictionary.md`):

| Group | Example columns | What it encodes |
|---|---|---|
| Archetype membership | `arch_a_power_puncher`, `arch_b_grappling_first`, … (8 archetypes × 2 fighters) | Soft membership over hand-labelled style archetypes |
| Archetype matchup | `arch_distance`, `arch_similarity` | Stylistic distance/overlap between the two fighters |
| Path / role | `grappler_path_a/b`, `striker_path_a/b`, `sg_mismatch_net`, `td_dominance_diff` | Grappler-vs-striker dynamics |
| KO / chin | `ko_danger_a/b`, `chin_durability_a/b`, `ko_threat_net`, `b_chin_vulnerable` | Finishing power vs durability |
| Submission threat | `sub_danger_a/b`, `sub_danger_diff`, `sub_danger_combined`, `sub_att_rate_diff` | Ground-finishing threat (also a soft prior in the method head) |
| Pace / pressure / counter | `pace_mismatch_diff`, `pressure_index_a/b`, `counter_threat_*`, `gas_out_risk_diff` | Tempo and counter dynamics |
| Stance | `stance_advantage_a`, `stance_score_amplified`, `stance_win_prob_uplift`, `open_stance` | Southpaw/orthodox interaction, amplified |
| Trajectory / age / rust | `trajectory_diff`, `age_curve_a/b/diff`, `prime_mismatch`, `rust_a/b/diff`, `favourite_rusty` | Career arc, prime, layoff |
| GMM cluster (K=7) | `cluster_a_0..6`, `cluster_b_0..6` | Soft archetype clustering membership |

Full definitions, ranges, and edge cases live in `docs/feature_dictionary.md`.

---

## 6. Models

### 6.1 Custom MMA Elo (`src/features/elo.py`)

K=24 base, scaled by fighter experience (1.5× for first 5 fights, decays to 1.0×) and method (KO/TKO ×1.15, Submission ×1.10, Decision ×1.0). Inactivity decay regresses idle fighters toward 1500 by up to 25% over multi-year layoffs. Promotion strength multiplier for non-UFC fights when seeding from Tapology (UFC ×1.0, Bellator ×0.85, regional ×0.55). Outputs are both a feature for downstream models and a standalone baseline.

### 6.2 GMM archetype clustering (`src/models/clustering.py`)

Soft clustering over standardised, PCA-reduced (10 components) fighter feature vectors. K selected by BIC, expected K=8. Outputs membership probabilities used as features. Soft assignment matters — most fighters are blends, not pure archetypes.

### 6.3 Model A — XGBoost win/loss (`src/models/win_loss_xgb.py`)

Binary classifier on the full feature matrix. Conservative regularisation: `max_depth=4`, `learning_rate=0.05`, `n_estimators=200`, `min_child_weight=5`, L1+L2. Tuned via Optuna on the 2023 validation set. SHAP analysis on every model version to monitor feature drift and detect leakage.

### 6.4 Model B — method classifier

> **Reality (2026-07-03):** production does **not** use the Random Forest below. The deployed
> method head is a **two-stage XGBoost chain** (`src/models/method_two_stage.py`): stage 1
> predicts finish-vs-decision, stage 2 predicts submission-vs-KO given a finish, each with an
> isotonic calibrator; the API blends in a rules-based `sub_danger_combined` prior. The RF
> (`method_rf.py`) is implemented to this design for interface completeness but is superseded.
> The round-of-finish regressor (`round_regressor.py`) is likewise implemented but **not** wired
> into the API yet — the API currently derives rounds from a heuristic distribution. NC/DQ: at
> the **data** layer DQ is preserved as its own label and NC rows are dropped; the NC/DQ→Decision
> rollup is applied only at model-training time.

Original design: 3-class softmax (KO/TKO, Submission, Decision). NC/DQ rolled into Decision because they're statistically rare and behaviourally close. `class_weight='balanced'` plus optional SMOTE on submissions. Auxiliary gradient-boosted regressor predicts the round of finish conditional on Model B saying "not Decision".

### 6.5 Model C — PyTorch career sequence model (`src/models/career_lstm.py`)

This is the new layer the JSX blueprint didn't have. For each fighter, build a sequence of past-fight feature vectors ordered by date. Pass through a small bidirectional LSTM (hidden=64, 2 layers, dropout=0.3), pool to a fixed-size embedding, concatenate the two fighters' embeddings plus the fight-day differential features, and pass through a 2-layer MLP head. Trained with binary cross-entropy + label smoothing 0.1. AdamW, cosine LR schedule with linear warmup. Mixed-precision on GPU. Pad short careers; mask in attention. Captures career trajectory (improving vs declining vs steady) in a way trees can't.

### 6.6 Ensemble (`src/models/ensemble.py`)

> **Reality (2026-07-03):** the four streams are **logreg / XGBoost / Elo / LSTM** — the RF is
> *not* a win/loss stream (there is no "derived win prob from method"). Weights fitted on the
> 2023 validation slice by constrained least-squares (log-loss, with a small uniform-shrinkage
> term): **logreg 0.292 · xgb 0.353 · elo 0.124 · lstm 0.231**. After the weighted blend the
> probability passes through `iso_blend` (isotonic) then temperature scaling (T=1.3). The win/loss
> XGB head was Optuna-tuned on a 67-feature SHAP-pruned subset (params frozen in
> `config.XGB_OPTUNA_TUNED`). Method probabilities come from the two-stage head in §6.4, not this
> ensemble.

Original design: weighted average over the four probability streams. Initial weights from the prediction-skill literature: Elo 0.20, XGBoost 0.30, RF 0.20 (for win/loss task it produces a derived win prob via summing KO+Sub+favourable Decision), LSTM 0.30. Weights re-fit on the 2023 validation set via constrained least squares minimising log-loss. Final probability passes through isotonic regression for calibration. Method probabilities come from Model B alone (no ensemble) but pass through the same calibration step.

### 6.7 Optional Monte Carlo layer

The JSX plan included a 10k-sim Monte Carlo. We keep it in the plan but defer to v1.5 — we want to ship a calibrated point-estimate ensemble first, then layer the simulator for predictive intervals and round distributions. Stub lives in `src/models/monte_carlo.py`.

---

## 7. Training and evaluation protocol

### 7.1 Walk-forward cross-validation

Five expanding-window folds within the train period. Each fold trains on all data before its cutoff and evaluates on the next 6 months. This is the only valid CV scheme for time-ordered fight data. Implemented in `src/eval/temporal_cv.py`.

### 7.2 Reporting

Every model run produces a one-page model card in `docs/model_cards/` containing: training cutoff, feature list, hyperparameters, validation metrics (Brier, log-loss, AUC, ECE), reliability diagram, SHAP top-10, sample of correct and incorrect high-confidence predictions. The model card is the artefact a future-you reads to understand what version 1.4 did differently from 1.3.

### 7.3 Calibration

Reliability curves with 10 bins. Fix any bow before declaring a model done. Two failure modes to watch:
- Overconfident favourites (predicted 80%+ winning at 70%) → temperature-scale or isotonic.
- Underconfident underdogs (predicted 30% winning at 38%) → underestimating upset potential, often a sign of insufficient cluster diversity.

### 7.4 Backtest

The `src/eval/backtest.py` script walks event-by-event through the test period: train on everything before each event, predict the event, score, accumulate. This is the deployment simulation — the numbers it produces are the ones that matter.

> **Reality (2026-07-03):** `src/eval/backtest.py` is now **implemented** (`run_backtest`, with an
> injectable predictor/model-factory) alongside `temporal_cv.py` and `calibration.py`. A CLI wraps
> it at `scripts/backtest.py`; the strict 2026 event replay lives in
> `scripts/backtest_2026_events.py`.

---

## 8. The `predict_fight` interface

Public entry point in `src/api/predict_fight.py`:

```python
def predict_fight(
    fighter_a: str,
    fighter_b: str,
    event_date: date,
    *,
    include_odds: bool = False,
) -> FightPrediction
```

Returns a structured `FightPrediction` dataclass with: `winner_prob` (dict), `method_prob` (dict), `round_estimate` (tuple of low/high if finish), `confidence` (high/medium/low based on ensemble agreement), `top_drivers` (top-5 SHAP factors), `cluster_matchup` (string label), `warnings` (list — fires on debut fighters, long layoffs, missing data). A `to_markdown()` method renders the human-readable narrative the JSX blueprint sketched.

---

## 9. Eight-week timeline

| Week | Focus | Deliverable |
|---|---|---|
| 1 | UFCStats scraper, raw data pull, schema validation | `data/raw/` populated, `notebooks/01_eda.ipynb` |
| 2 | Cleaning, deduplication, temporal split, feature dictionary | `data/interim/fights.parquet`, `docs/feature_dictionary.md` final |
| 3 | Elo system, time-decayed stats, GMM clustering | `src/features/elo.py`, `src/models/clustering.py` shipped + tested |
| 4 | Feature matrix assembly, Model A (XGBoost), SHAP | `data/processed/feature_matrix.parquet`, model card v1.0-A |
| 5 | Model B (Random Forest method), round regressor | model card v1.0-B |
| 6 | Model C (PyTorch career LSTM) | model card v1.0-C, GPU training run logged |
| 7 | Ensemble, calibration, predict_fight() API | end-to-end demo on 5 manually-picked 2025 fights |
| 8 | Blind backtest on 2025, write-up, edge cases | final evaluation report, model card v1.0-ensemble |

V1.5 deferred items: Monte Carlo simulator, stylistic features (tier-2 + tier-3), referee/judge adjustments, betting integration.

---

## 10. Open questions and known risks

**Open.** Should non-UFC fights from Tapology contribute to Elo seeding only, or also to the supervised training set with a promotion-strength weight? Default for v1: seeding only. Revisit if calibration on debut fighters is poor.

**Open.** How to handle short-notice replacements (the highest-variance fights)? Probably a `short_notice` flag and a separate evaluation slice.

**Risk — small samples.** Most fighters have <20 UFC fights. Time-decayed averages help, but Bayesian shrinkage toward division priors would help more. Plan for v1.5.

**Risk — non-stationarity.** The MMA meta evolves. A 2008 striking style is not a 2025 striking style. The recency weighting partially handles this; the LSTM should capture the rest.

**Risk — irreducible noise.** The literature pegs the prediction ceiling at ~70–75% accuracy because a single punch can end any fight. We will not exceed this. Calibration is the only honest target.

**Risk — ethics.** Anything we ship needs an explicit "not for gambling advice, not predictive of any individual outcome, model is uncertain" disclaimer in the API output and any UI.

---

## 11. Repo map (one-line each)

```
data/                  raw/interim/processed/external — git-ignored except processed
notebooks/             numbered exploratory notebooks (01_eda → 06_calibration)
src/data/              scrapers, cleaning (clean_fights/clean_fighters), splits
src/features/          elo, time-decay, core + tier-2 style/archetype builders, method_calibration
src/models/            clustering, win_loss_xgb, method_two_stage (prod) + method_rf, round_regressor,
                       career_lstm, monte_carlo (stub, v1.5), ensemble
src/eval/              metrics, calibration, backtest, temporal_cv  (all implemented)
src/api/               predict_fight() facade + types / loading / assembly (decomposed)
src/utils/             logging, paths, helpers
tests/                 pytest — temporal correctness + leakage, api contract, eval/models/data layers
docs/                  MODEL_STATUS.md, architecture.md, feature_dictionary.md, model_cards/, planning/
scripts/               canonical CLIs (train_all[--smoke], predict, backtest, build_features, …)
scripts/events/        per-card one-off prediction scripts (historical, runnable)
scripts/archive/       superseded/experimental training scripts (incl. the two that built the bundle)
Makefile               make test / lint / typecheck / smoke / predict / ci
.github/workflows/     CI: ruff + mypy + pytest
```

---

## 12. Definitions of done (checklist)

Status as of 2026-07-03 (◑ = partial, see note):

- [x] docs/PLAN.md exists, accurate, current — reconciled 2026-07-03
- [x] Repo skeleton matches §11 (updated below to reflect the post-refactor layout)
- [◑] UFCStats scraper pulls a single event end-to-end — enrichment path (`enrich_with_fight_details`) works; the top-level re-scrape entry points are deliberate deferrals (v1 cached parquet is canonical)
- [x] Elo system passes a deterministic unit test (`tests/test_elo.py`)
- [x] Feature matrix builds without future-data leakage — enforced by `tests/test_temporal_leakage.py` (truncation-invariance over 100 feature columns)
- [x] Model cards under `docs/model_cards/` — Model A (13 versions), ensemble, and LSTM (Model C) cards exist
- [ ] Ensemble Brier on 2024–2025 blind test < 0.225 — **not met**: 0.229 on test (0.222 on val). See `docs/MODEL_STATUS.md`
- [x] `predict_fight("Islam Makhachev", "Charles Oliveira", date(2025, 4, 12))` returns sensible output (73% Makhachev)
- [◑] Viz showcase renders from real outputs — 2 of 4 fixtures are real `predict_fight()` output; 2 are labelled demo data (`viz/README.md`)

The original "v1.0 ships when all boxed" gate is superseded by the reconciliation overhaul: the
*pipeline* is fully wired and reproducible; the *metric* targets (AUC/Brier) remain the open work,
staged in `docs/MODEL_STATUS.md §4`.

---

## 13. Visualization layer

The model produces probabilities. Probabilities only matter if a human can read them. The visualization layer is the bridge — D3-powered, editorial-restrained, always answering a specific question.

### 13.1 Aesthetic direction (deliberate counterweight)

The viz layer takes the **opposite** stance from the JSX scoreboard mock-up. Where that one is dark, neon-yellow, monospace, *broadcast-graphic* energy — viz is bone paper, oxblood ink, serif headlines, *scientific-paper* energy. This split is intentional. Predictions are watched; calibrations are read.

| Token | Hex | Purpose |
|---|---|---|
| `--bone` | `#F4EFE7` | Background. Slightly warm off-white. |
| `--ink` | `#0E0E0C` | Primary text, axis lines, dot fill. |
| `--graphite` | `#3A3A38` | Secondary text, tick labels. |
| `--cage` | `#B8B0A4` | Hairline borders, gridlines. |
| `--oxblood` | `#7A1E1E` | The ONE accent. Highlight, fight-end markers, model line on calibration. |
| `--steel` | `#2D4A5E` | Second-series only — Elo's blue, market line on benchmarks. |

Type stack: **Fraunces** (variable serif display), **Source Serif 4** (body), **IBM Plex Mono** (numerals, axis tick values). Loaded from Google Fonts.

### 13.2 Chart catalogue (each has a job)

| Chart | Question it answers | Module |
|---|---|---|
| Reliability curve | Is the model honest about its confidence? | `viz/components/reliability.js` |
| Career Elo small multiples | How is each fighter trending into this fight? | `viz/components/elo_sparklines.js` |
| GMM archetype scatter | What stylistic cluster does each fighter occupy? | `viz/components/archetype_scatter.js` |
| SHAP feature dot plot | Which features drove this prediction? | `viz/components/shap_dots.js` |
| Method-of-victory matrix | Where does Model B make its mistakes? | `viz/components/method_matrix.js` |
| Brier-over-time line | Is calibration drifting? | `viz/components/brier_timeline.js` |
| Round-finish histogram | If finished, when does it end? | `viz/components/round_histogram.js` |

Headline four for v1.0 demo: reliability, Elo small multiples, archetype scatter, SHAP dots. Others arrive as we instrument the pipeline.

### 13.3 Where it lives

```
viz/
├── README.md
├── showcase/
│   └── index.html          ← editorial demo, single file, opens in any browser
├── components/             ← reusable D3 chart factories (one fn each, ESM)
│   ├── reliability.js
│   ├── elo_sparklines.js
│   ├── archetype_scatter.js
│   └── shap_dots.js
└── data/                   ← JSON fixtures, exported from notebooks/Python
    ├── reliability_v1.json
    ├── elo_traces.json
    └── ...
```

Components are vanilla D3 v7 (no React dependency for v1) so they can be embedded in static reports, notebook outputs, or a future Next/SvelteKit dashboard without rewriting. Each component is a pure function: `chart(selector, data, opts) → cleanup()`.

### 13.4 Integration with `predict_fight`

The `FightPrediction.to_markdown()` method emits a static report; a planned `to_html()` method (v1.1) will inline the four headline charts using the components above with the prediction's data. The same components also power the per-event backtest report in `docs/model_cards/`.

### 13.5 Principles

- **One chart, one question.** If you can't say what question it answers in one sentence, cut it.
- **Restraint over flourish.** No 3D, no gradients, no shadows. Tufte rules apply.
- **Numerals in mono.** Always. Easier to compare digit-by-digit.
- **Direct labelling beats legends.** Label the line, not a swatch in a corner.
- **Annotate the interesting moment.** The single most important quality signal is "the chart already told me what to notice."

---

## 14. Reality reconciliation (2026-07-03)

The 2026-07-03 projectification overhaul wired the clean `src/` interfaces this plan designed and
made the repo reproducible (git history, CI, Makefile, smoke path, tests). It deliberately did
**not** retrain or scrape. In the process the plan-vs-built deltas below were surfaced and are
recorded here so the doc is honest rather than aspirational. `docs/MODEL_STATUS.md` is the live
scoreboard; this table is the design-intent diff.

| Area | Plan said | Built reality |
|---|---|---|
| Feature set | Tier-1 only for v1; stylistic features deferred to v1.5 (§5) | 102 features incl. a full **tier-2 style/archetype block** (UPDATE_2); several tier-1 columns renamed |
| GMM clusters | K=8 expected (§6.2) | K=7 shipped (`cluster_*_0..6`) |
| Method head | Random Forest 3-class (§6.4) | **Two-stage XGBoost** (finish→sub) + isotonics; RF implemented but superseded |
| Round of finish | GB regressor conditional on finish (§6.4) | **Heuristic** distribution in the API; regressor implemented as interface, not wired |
| Ensemble streams | elo/xgb/**rf**/lstm, lit-seed weights (§6.6) | logreg/xgb/elo/**lstm**, val-fitted **0.29/0.35/0.12/0.23** |
| Win/loss head | conservative fixed XGB params (§6.3) | **Optuna-tuned** on 67-feature SHAP-pruned subset (`config.XGB_OPTUNA_TUNED`) |
| Calibration | isotonic on validation (§6.6) | isotonic (`iso_blend`) **+ temperature scaling T=1.3**; note the ≥0.73→1.0 saturation caveat |
| Eval layer | `src/eval/*` designed (§7) | **implemented** this run (metrics/calibration/backtest/temporal_cv) — was stubs |
| `predict_fight` | single 974-line module (§8) | **decomposed** into `types`/`loading`/`assembly` + facade; public surface frozen |
| Bundle provenance | one clean `train_all.py` run | **composite** of train_all → train_lstm → optuna_xgb → retrain_twostage (see `scripts/archive/README.md`) |
| Data cleaning | NC/DQ → Decision (§6.4) | at the data layer DQ kept as own label, NC dropped; the rollup is model-training-time only |
| Feature matrix | one canonical file (§4.3) | **two coexist** (114-col built = canonical; 34-col legacy still used by some scripts) — documented debt |
| Metrics | AUC ≥ 0.74, Brier < 0.225 (§3) | AUC 0.67, Brier 0.229 (test) — **not met**; staged roadmap in MODEL_STATUS §4 |
| Viz data | fixtures from real output (§13) | 2 of 4 fixtures real, 2 hand-authored demo (labelled) |
| Monte Carlo | deferred to v1.5 (§6.7) | still a documented stub — unchanged |
