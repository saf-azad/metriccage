# scripts/

Command-line entry points for the UFC fight predictor. Run everything from the
repo root with the project interpreter and `PYTHONPATH` set (see the top-level
`Makefile`):

```
PYTHONPATH=. .venv/bin/python scripts/<name>.py [args]
```

Each canonical script bootstraps `sys.path` itself, so a bare
`.venv/bin/python scripts/<name>.py` also works.

## Canonical / reusable entry points

| Script | Purpose | Example |
|---|---|---|
| `train_all.py` | **Training entry point.** Full pipeline: load/build matrix → temporal split → Model A (XGB) + Model B (logreg) + optional Model C (LSTM) → ensemble + isotonic calibration → two-stage method head → blind backtest → write `final_model_bundle.pkl` + `final_model_metrics.json`. | `… scripts/train_all.py --skip-lstm` |
| `train_all.py --smoke` | **Smoke target** (`make smoke`). Runs the *entire* wiring on a hard subsample with tiny models, writing only to a scratch dir (`ROOT/.smoke/`) so production artifacts are never touched. Prints `SMOKE OK …` and exits 0 in ~1s. | `… scripts/train_all.py --smoke` |
| `predict.py` | **Prediction entry point.** Thin CLI over `src.api.predict_fight`; prints the Markdown card, or `--json` for `to_dict()`. | `… scripts/predict.py --a "Islam Makhachev" --b "Charles Oliveira" --date 2025-04-12 --weight-class Lightweight` |
| `backtest.py` | **Walk-forward backtest CLI** over `src.eval.backtest.run_backtest` for an arbitrary `--start`/`--end` window, using `predict_fight` as the injected predictor. Bound quick runs with `--limit N`. | `… scripts/backtest.py --start 2024-01-01 --end 2025-05-04` |
| `build_features.py` | Build a feature matrix from cleaned interim data (`--out` required; refuses to clobber without `--force`; `--sample N` for a fast partial build). | `… scripts/build_features.py --out data/processed/feature_matrix_built.parquet` |
| `scrape_all.py` | One-shot UFCStats scraper entry point (network). | `… scripts/scrape_all.py` |
| `train_lstm.py` | Train Model C (career LSTM) and integrate it as the 4th ensemble stream. | `… scripts/train_lstm.py` |
| `fit_archetypes.py` | Fit the GMM archetype clustering on train-period fighter career vectors → `cluster_model.pkl`. | `… scripts/fit_archetypes.py` |
| `prune_features.py` | SHAP-based feature-pruning analysis → `feature_prune_report.json`. | `… scripts/prune_features.py` |
| `parse_per_round.py` | Re-parse per-round stats from cached UFCStats fight HTML → `fight_rounds.parquet`. | `… scripts/parse_per_round.py` |
| `parse_target_strikes.py` | Parse target-zone significant strikes from cached UFCStats HTML. | `… scripts/parse_target_strikes.py` |
| `backtest_2026_events.py` | **Specialised 2026 holdout runner.** Strict chronological Elo+history replay against every 2026 event (predict-then-absorb). Kept because it replays state for events *newer* than the bundle's cached state — something `backtest.py` deliberately does not do. | `… scripts/backtest_2026_events.py` |

`backtest.py` vs `backtest_2026_events.py`: use `backtest.py` for any date range
within the model's known data window (it reuses the generalised
`run_backtest`); use `backtest_2026_events.py` for the live 2026 season, where a
strict Elo/history replay past the cached state is required.

## Subdirectories

- **`events/`** — per-card one-off scripts (specific UFC cards, name checks, odds
  overlays, event reports). Historical and card-specific but still runnable. See
  `events/README.md`.
- **`archive/`** — superseded / experimental one-offs kept non-destructively for
  provenance and reproducibility. **Two of them produced the current production
  bundle** — see `archive/README.md`.
