<div align="center">

# Metric Cage

**A calibrated probability engine for UFC fights.**

[![CI](https://github.com/saf-azad/metriccage/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/saf-azad/metriccage/actions/workflows/ci.yml)
[![Site](https://img.shields.io/badge/site-metriccage.vercel.app-2ea44f)](https://metriccage.vercel.app)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

[**2026 season report (PDF)**](reports/metric-cage-2026-season-report.pdf) · [Model status](docs/MODEL_STATUS.md) · [Architecture](docs/architecture.md) · [Feature dictionary](docs/feature_dictionary.md) · [After the Knockdown](articles/brain-damage-careers/article.md)

</div>

---

Give Metric Cage two fighters and a date and it returns a win probability for each, an estimate
of how the fight ends, and the features that drove the call. It is built and judged on
**calibration**, not accuracy: when it says 70%, that fighter should win about 70% of the time.
Picking the favourite already gets you ~60% in the UFC, so accuracy on its own is a weak yardstick.

## Results on an unseen season

Training data stops on 4 May 2025. I then replayed all 14 UFC cards from January to May 2026
in order, updating ratings only as each event finished, with no betting-market information of
any kind. Figures below are from the [season report](reports/metric-cage-2026-season-report.pdf)
(6 August 2026).

| Measure | Result |
|---|---|
| Fights | 175 across 14 events, none seen in training |
| Winner AUC | **0.691** (95% CI 0.614–0.764) |
| Winners picked | 114 of 175 (65%) |
| Confident calls (≥65%) | **42 of 55 correct (76%)** |
| Method of victory | weak this season, reported as a failure (stage-one AUC 0.42) |
| Round of finish | a fixed base rate, not a prediction |

Published academic UFC models score between 0.68 and 0.74, mostly with betting odds as a
feature. I was aiming for 0.74 without odds and didn't get there. The model also leans
cautious: when it said about 69%, the fighter won 78% of the time. All of this, including the
parts that didn't work, is written up in [`docs/MODEL_STATUS.md`](docs/MODEL_STATUS.md).

## How it works

```
UFCStats (7,200+ bouts since 2010)
   │  scrape → clean → one row per fight, 102 differential features
   ▼
 ┌─────────┬──────────────┬──────────┬───────────────┐
 │ Elo     │ Logistic reg │ XGBoost  │ PyTorch LSTM  │   four win-probability streams
 │ (custom)│              │ (Optuna) │ (career order)│
 └────┬────┴──────┬───────┴────┬─────┴───────┬───────┘
      └───────────┴─── weighted blend ───────┘   weights fitted on the 2023 slice (log-loss)
                         │
          isotonic calibration → temperature scaling
                         │
                 P(win) · P(KO / Sub / Dec) · drivers
```

- **Four streams, one feature set.** A custom MMA Elo, logistic regression, an XGBoost head
  tuned with Optuna over a SHAP-pruned feature subset, and a PyTorch LSTM that reads each
  fighter's career in order. Blend weights (`logreg .29 · xgb .35 · elo .12 · lstm .23`) were
  fitted by constrained least squares on a 2023 validation slice.
- **Calibration chain.** Isotonic regression on the blended probability, then temperature
  scaling (T = 1.3) so extreme calls are shrunk toward 0.5.
- **Method head.** A two-stage XGBoost chain (finish vs decision, then submission vs KO), each
  with its own isotonic calibrator.
- **Temporal correctness is a tested contract.** Every feature for a fight on date *d* uses only
  data strictly before *d*. Walk-forward validation only; `tests/test_temporal_leakage.py` checks
  that no future fight reaches training, including truncation invariance.

Full data flow and model layer: [`docs/architecture.md`](docs/architecture.md). Every feature,
its formula and source: [`docs/feature_dictionary.md`](docs/feature_dictionary.md). The original
design and where reality diverged from it: [`docs/PLAN.md`](docs/PLAN.md) §14.

## Research on the same data

The dataset answers questions the model never asks.

- **[After the Knockdown](articles/brain-damage-careers/article.md)** (PDF
  [here](articles/brain-damage-careers/After-the-Knockdown.pdf)): across 7,270 fights, fighters
  who were dropped and carried on were stopped by strikes in the next round 10.6% of the time
  against 5.1% for those who weren't. After adjustment the knockdown's link to a *repeat*
  knockdown held (odds ratio 1.9, survives Holm correction across 22 tests); its link to being
  stopped did not. Among dropped fighters aged 33+, 15.1% were stopped next round, against 5.7%
  under 29. Scripts, matched-pair lists and the full
  [methods note](articles/brain-damage-careers/METHODS.md) are in the folder.

## Repository

```
src/
  data/        scrape (rate-limited, cached), clean, temporal splits
  features/    Elo replay, time-decayed stats, archetype clustering, build_matrix
  models/      win_loss_xgb, career_lstm, ensemble, method_two_stage, clustering
  eval/        walk-forward backtest, calibration, metrics
  api/         predict_fight(): the one public entry point
scripts/       train_all, predict, backtest, build_features, scrape_all  (see scripts/README.md)
tests/         90 pytest tests: API contract, temporal leakage, each layer, CLI, smoke
docs/          MODEL_STATUS (honest scoreboard), architecture, feature dictionary, model cards
reports/       the 2026 season report
articles/      After the Knockdown: analysis scripts, results, figures
```

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt

make smoke        # runs the whole pipeline on a tiny slice, ~1s: proves the wiring
make test         # pytest; tests that need local data/model artifacts skip automatically
make lint typecheck
```

Raw data, feature matrices and trained bundles are not committed (they're several hundred MB).
To rebuild from scratch:

```bash
python scripts/scrape_all.py                                   # long-running, rate-limited
PYTHONPATH=. python scripts/build_features.py --out data/processed/feature_matrix_built.parquet
PYTHONPATH=. python scripts/train_all.py --with-lstm --rebuild-matrix
PYTHONPATH=. python scripts/predict.py --a "Islam Makhachev" --b "Charles Oliveira" --date 2025-04-12
```

`scripts/backtest_2026_events.py` reproduces the season replay: strict chronological Elo and
history updates, predict-then-absorb, one event at a time.

## Known limits

- UFC-only history, so debutants and regional-circuit imports have little signal.
- No weight-change or short-notice feature.
- The method head skews to Decision; the round output is a base rate.
- Outputs are calibrated probability estimates, not betting advice.

## License

[MIT](LICENSE)
