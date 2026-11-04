"""Auxiliary round-of-finish regressor (PLAN §6.4 auxiliary model).

Conditional on the method head saying "not Decision", predict which round the
fight ends in. Simple gradient-boosted regressor. Target: round_finished
(1..5). Loss: MAE (``absolute_error``) so a single outlier doesn't dominate.
Predictions are clipped to [1, 5].

NOTE: the production api does not use a trained round model yet — it derives
``finish_round_dist`` from a heuristic distribution over the method
probabilities (``src/api/predict_fight._round_distribution``). This module is
the interface for the staged plan to replace that heuristic.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.config import RANDOM_SEED

#: Light defaults; override via the ``params`` argument (tests pass tiny values).
ROUND_REG_DEFAULTS: dict[str, Any] = {
    "loss": "absolute_error",
    "n_estimators": 200,
    "learning_rate": 0.05,
    "max_depth": 3,
    "subsample": 0.8,
    "random_state": RANDOM_SEED,
}


def train_round_regressor(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    params: dict[str, Any] | None = None,
):
    """Fit a GradientBoostingRegressor on round_finished (1..5), finish rows only.

    ``params`` overrides :data:`ROUND_REG_DEFAULTS`. Returns the fitted model.
    """
    from sklearn.ensemble import GradientBoostingRegressor

    cfg = {**ROUND_REG_DEFAULTS, **(params or {})}
    reg = GradientBoostingRegressor(**cfg)
    reg.fit(X_train, y_train)
    return reg


def predict_round(model, X: pd.DataFrame) -> pd.Series:
    """Predicted finish round per row, clipped to [1, 5]."""
    pred = np.clip(np.asarray(model.predict(X), dtype=float), 1.0, 5.0)
    return pd.Series(pred, index=getattr(X, "index", None), name="round_pred")
