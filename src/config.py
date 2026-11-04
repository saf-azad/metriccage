"""Project-wide paths, constants, and default hyperparameters.

Anything that more than one module reads should live here, not be hard-coded
elsewhere. Override via environment variables or a local .env file.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

# --- Paths -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
EXTERNAL = DATA / "external"
DOCS = ROOT / "docs"
MODEL_CARDS = DOCS / "model_cards"

# --- Temporal split (see docs/PLAN.md §4.2) ---------------------------------------

TRAIN_START = date(2005, 1, 1)
TRAIN_END = date(2022, 12, 31)
VAL_START = date(2023, 1, 1)
VAL_END = date(2023, 12, 31)
TEST_START = date(2024, 1, 1)
TEST_END = date(2025, 5, 4)

# --- Scraper -----------------------------------------------------------------

SCRAPE_USER_AGENT = "UFC-Predictor-Research/0.1 (academic; contact: alazadsafwat@gmail.com)"
SCRAPE_RATE_LIMIT_SECONDS = 1.5

# --- Feature engineering -----------------------------------------------------

DECAY_HALF_LIFE_DAYS = 365
ELO_K_BASE = 24
ELO_DEFAULT_RATING = 1500
ELO_INACTIVITY_THRESHOLD_DAYS = 365
GMM_N_COMPONENTS_RANGE = (4, 14)  # search range; final K chosen by BIC

# --- Models ------------------------------------------------------------------

XGB_DEFAULTS = {
    "objective": "binary:logistic",
    "eval_metric": "logloss",
    "max_depth": 4,
    "learning_rate": 0.05,
    "n_estimators": 200,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
}

# Production win/loss head params, optuna 80-trial val-AUC search 2026-05-10
# (scripts/archive/optuna_xgb.py); rerunning training with these reproduces the
# deployed model without a sweep. Full precision — matches the bundle's
# `xgb_optuna_params` key exactly (asserted in tests/test_models_layer.py).
# (The script lives at scripts/optuna_xgb.py until the scripts consolidation
# moves it into scripts/archive/.)
XGB_OPTUNA_TUNED = {
    "max_depth": 3,
    "learning_rate": 0.027418915222108636,
    "n_estimators": 800,
    "min_child_weight": 9,
    "reg_alpha": 1.215416945178543,
    "reg_lambda": 1.5295791109721033,
    "subsample": 0.9031357748561099,
    "colsample_bytree": 0.7696396827461547,
    "gamma": 0.23186200351845387,
}

LSTM_DEFAULTS = {
    "hidden_dim": 64,
    "num_layers": 2,
    "dropout": 0.3,
    "bidirectional": True,
    "lr": 3e-4,
    "weight_decay": 0.01,
    "label_smoothing": 0.1,
    "epochs": 50,
    "batch_size": 64,
    "warmup_pct": 0.05,
}

# --- Ensemble seed weights (re-fit on validation) ----------------------------
# Stream names match the SHIPPED ensemble: logreg / xgb / elo / lstm (the
# production bundle's fitted weights are ~.29/.35/.12/.23). PLAN §6.6 originally
# seeded an 'rf' stream (elo .20 / xgb .30 / rf .20 / lstm .30), but the RF
# method head never fed the win/loss ensemble — a logistic-regression stream
# ships instead. These are only optimiser seeds; fit_ensemble re-fits them.

ENSEMBLE_INIT_WEIGHTS = {
    "elo": 0.20,
    "xgb": 0.30,
    "logreg": 0.20,
    "lstm": 0.30,
}

RANDOM_SEED = 42
