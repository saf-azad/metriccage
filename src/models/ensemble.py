"""Final ensemble + isotonic calibration.

Combine up to four win-probability streams into a single calibrated probability:
    - Elo (raw expected score)
    - XGBoost (Model A)
    - Logistic regression / Random Forest (Model B)
    - PyTorch LSTM (Model C, optional — present once Track 2A lands)

WEIGHTING
    Initial weights from src.config.ENSEMBLE_INIT_WEIGHTS, then re-fit on the
    2023 validation slice via constrained least squares minimising log-loss.
    Constraints: weights ≥ 0 and sum to 1 (a proper convex combination).

CALIBRATION
    Isotonic regression fitted on the validation slice. Applied to the final
    blended probability before returning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import log_loss

from src.config import ENSEMBLE_INIT_WEIGHTS

EPS = 1e-6


@dataclass
class EnsembleBundle:
    weights: dict[str, float]
    calibrator: Any  # sklearn IsotonicRegression
    streams: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)


def _initial_weights(stream_names: list[str]) -> np.ndarray:
    """Project ENSEMBLE_INIT_WEIGHTS onto the available streams (renormalised)."""
    w = np.array([ENSEMBLE_INIT_WEIGHTS.get(s, 1.0 / len(stream_names)) for s in stream_names])
    w = np.clip(w, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else np.full_like(w, 1.0 / len(stream_names))


def _blend(streams: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted convex combination → clipped probabilities."""
    p = streams @ weights
    return np.clip(p, EPS, 1 - EPS)


def fit_ensemble(
    probability_streams: pd.DataFrame,
    y_val: pd.Series,
    *,
    isotonic: bool = True,
) -> EnsembleBundle:
    """Re-fit ensemble weights on the validation slice via constrained log-loss.

    `probability_streams` columns become the stream names. Common columns:
    ['elo', 'xgb', 'rf', 'lstm']. Missing streams are simply omitted.
    """
    streams = list(probability_streams.columns)
    P = probability_streams.to_numpy(dtype=float)
    y = y_val.to_numpy(dtype=float)
    n_streams = P.shape[1]
    uniform = np.full(n_streams, 1.0 / n_streams)
    SHRINK_LAMBDA = 0.05  # pull weights toward uniform; combats small-val overfit

    def neg_loglik(w: np.ndarray) -> float:
        p = _blend(P, w)
        ll = float(log_loss(y, p, labels=[0, 1]))
        return ll + SHRINK_LAMBDA * float(np.sum((w - uniform) ** 2))

    w0 = _initial_weights(streams)
    bounds = [(0.0, 1.0)] * len(streams)
    constraints = ({"type": "eq", "fun": lambda w: float(w.sum() - 1.0)},)

    res = minimize(
        neg_loglik,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 500, "ftol": 1e-9},
    )

    w_opt = res.x if res.success else w0
    w_opt = np.clip(w_opt, 0.0, None)
    s = w_opt.sum()
    w_opt = w_opt / s if s > 0 else w0

    weights = {name: float(w) for name, w in zip(streams, w_opt, strict=False)}

    blended = _blend(P, w_opt)
    if isotonic:
        cal = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        cal.fit(blended, y)
        calibrated = cal.predict(blended)
    else:
        cal = None
        calibrated = blended

    metrics = {
        "val_logloss_pre_cal": float(log_loss(y, blended)),
        "val_logloss_post_cal": float(log_loss(y, np.clip(calibrated, EPS, 1 - EPS))),
        "val_brier_post_cal": float(np.mean((calibrated - y) ** 2)),
    }

    return EnsembleBundle(weights=weights, calibrator=cal, streams=streams, metrics=metrics)


def predict_ensemble(
    streams: pd.DataFrame,
    bundle: EnsembleBundle,
) -> np.ndarray:
    """Apply the bundle's weights and calibrator to fresh stream probabilities."""
    cols = [c for c in bundle.streams if c in streams.columns]
    if len(cols) != len(bundle.streams):
        missing = set(bundle.streams) - set(cols)
        raise ValueError(f"Missing stream columns required by ensemble: {missing}")
    P = streams[cols].to_numpy(dtype=float)
    w = np.array([bundle.weights[c] for c in cols], dtype=float)
    blended = _blend(P, w)
    if bundle.calibrator is not None:
        return np.clip(bundle.calibrator.predict(blended), EPS, 1 - EPS)
    return blended
