"""Calibration tools — reliability curves, isotonic fit, temperature scaling."""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.isotonic import IsotonicRegression


def reliability_curve(
    y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Returns (bin_centres, observed_freq, predicted_freq, bin_counts).

    Equal-width bins on [0, 1]. Binning matches
    ``src.eval.metrics.expected_calibration_error`` (``np.digitize`` on the
    interior edges, so a probability of exactly 1.0 lands in the last bin).

    Returns
    -------
    bin_centres : midpoint of each bin, shape (n_bins,).
    observed_freq : mean of ``y_true`` per bin (bin accuracy); NaN for empty bins.
    predicted_freq : mean of ``y_prob`` per bin (bin confidence); NaN for empty bins.
    bin_counts : number of samples per bin (int); 0 for empty bins.
    """
    if n_bins < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins}")
    yt = np.asarray(y_true, dtype=float).ravel()
    yp = np.asarray(y_prob, dtype=float).ravel()
    if yt.shape != yp.shape:
        raise ValueError(f"shape mismatch: y_true {yt.shape} vs y_prob {yp.shape}")

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    centres = (edges[:-1] + edges[1:]) / 2.0
    bin_ids = np.digitize(yp, edges[1:-1])

    observed = np.full(n_bins, np.nan)
    predicted = np.full(n_bins, np.nan)
    counts = np.zeros(n_bins, dtype=int)
    for b in range(n_bins):
        mask = bin_ids == b
        c = int(mask.sum())
        counts[b] = c
        if c:
            observed[b] = float(yt[mask].mean())
            predicted[b] = float(yp[mask].mean())
    return centres, observed, predicted, counts


def fit_isotonic(y_true: np.ndarray, y_prob: np.ndarray) -> IsotonicRegression:
    """Returns a fitted sklearn IsotonicRegression.

    Configured exactly like the production blend calibrator fitted in
    ``src/models/ensemble.py`` (bundle key ``iso_blend``):
    ``out_of_bounds="clip"`` with outputs clamped to [0, 1], fitted as
    prob -> label.
    """
    yt = np.asarray(y_true, dtype=float).ravel()
    yp = np.asarray(y_prob, dtype=float).ravel()
    if yt.shape != yp.shape:
        raise ValueError(f"shape mismatch: y_true {yt.shape} vs y_prob {yp.shape}")
    if yt.size == 0:
        raise ValueError("cannot fit isotonic regression on empty arrays")
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(yp, yt)
    return iso


def temperature_scale(y_true: np.ndarray, logits: np.ndarray) -> float:
    """Search for the temperature T that minimises NLL of sigmoid(logits / T).

    Binary temperature scaling: returns the T > 0 minimising the mean negative
    log-likelihood of ``sigmoid(logits / T)`` against ``y_true``, via a bounded
    scalar search on [0.05, 10]. T > 1 shrinks probabilities toward 0.5
    (fixes overconfidence); T < 1 sharpens them.

    Cross-reference: ``src/api/predict_fight.py`` applies the bundle key
    ``calibration_temperature`` to the final blended probability's logit at
    predict time (T=1.3 in production, set out-of-band by the training
    pipeline). This function is how such a T is derived from held-out data.
    """
    yt = np.asarray(y_true, dtype=float).ravel()
    z = np.asarray(logits, dtype=float).ravel()
    if yt.shape != z.shape:
        raise ValueError(f"shape mismatch: y_true {yt.shape} vs logits {z.shape}")
    if yt.size == 0:
        raise ValueError("cannot temperature-scale empty arrays")

    def _nll(temp: float) -> float:
        zt = z / temp
        # BCE with logits, numerically stable: log(1 + e^zt) - y * zt.
        return float(np.mean(np.logaddexp(0.0, zt) - yt * zt))

    res = minimize_scalar(_nll, bounds=(0.05, 10.0), method="bounded")
    return float(res.x)
