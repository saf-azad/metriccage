"""Per-class isotonic regression calibration for method probability outputs.

Step 4b from UPDATE_2.md: applies isotonic regression independently to each
method class (Decision, KO/TKO, Submission) to correct the systematic
probability miscalibration in the output vector.

The softmax output layer reflects training label frequency (~45% Decision,
~32% KO/TKO, ~23% Submission). Decision probability is structurally inflated.
Isotonic regression corrects the reliability curve per class so that predicted
probabilities match empirical frequencies.

USAGE IN TRAINING (scripts/train_all.py):

    from src.features.method_calibration import calibrate_method_probs

    calibrators = calibrate_method_probs(raw_probs_val, y_method_val)
    # Save calibrators alongside model bundle:
    bundle["method_calibrators"] = calibrators

USAGE IN INFERENCE (predict_fight.py):

    from src.features.method_calibration import apply_method_calibration

    calibrated = apply_method_calibration(raw_probs, bundle["method_calibrators"])

METHOD LABEL CONVENTION:
    0 = Decision
    1 = KO/TKO
    2 = Submission
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from sklearn.isotonic import IsotonicRegression

if TYPE_CHECKING:
    import pandas as pd


METHOD_LABELS = ["Decision", "KO/TKO", "Submission"]
_N_CLASSES = len(METHOD_LABELS)

EPS = 1e-6


def calibrate_method_probs(
    raw_probs: np.ndarray,
    y_method: np.ndarray,
) -> list[IsotonicRegression]:
    """Fit one IsotonicRegression per method class on a held-out validation set.

    Parameters
    ----------
    raw_probs : np.ndarray, shape (n, 3)
        Raw predicted probabilities [P(decision), P(ko), P(sub)].
    y_method : np.ndarray, shape (n,)
        Integer method labels: 0=Decision, 1=KO/TKO, 2=Submission.

    Returns
    -------
    list of 3 fitted IsotonicRegression objects (one per class).
    Save these alongside the model artifact and pass to apply_method_calibration.

    Notes
    -----
    CRITICAL: raw_probs must come from a held-out validation split, never the
    training set. Fitting on training data will overfit the calibration curve.
    """
    if raw_probs.ndim != 2 or raw_probs.shape[1] != _N_CLASSES:
        raise ValueError(f"raw_probs must have shape (n, {_N_CLASSES}), got {raw_probs.shape}")

    calibrators: list[IsotonicRegression] = []
    for cls in range(_N_CLASSES):
        y_binary = (y_method == cls).astype(int)
        iso = IsotonicRegression(out_of_bounds="clip")
        iso.fit(raw_probs[:, cls], y_binary)
        calibrators.append(iso)
    return calibrators


def apply_method_calibration(
    raw_probs: np.ndarray,
    calibrators: list[IsotonicRegression],
) -> np.ndarray:
    """Apply per-class calibration and renormalise to a valid probability distribution.

    Parameters
    ----------
    raw_probs : np.ndarray, shape (n, 3) or (3,)
        Raw predicted method probabilities.
    calibrators : list of 3 IsotonicRegression objects
        From calibrate_method_probs().

    Returns
    -------
    np.ndarray, same shape as raw_probs, rows summing to 1.
    """
    squeeze = raw_probs.ndim == 1
    if squeeze:
        raw_probs = raw_probs[np.newaxis, :]

    calibrated = np.stack(
        [cal.predict(raw_probs[:, i]) for i, cal in enumerate(calibrators)],
        axis=1,
    )
    calibrated = np.clip(calibrated, EPS, None)
    row_sums = calibrated.sum(axis=1, keepdims=True)
    calibrated = calibrated / np.where(row_sums > 1e-9, row_sums, 1.0)

    return calibrated[0] if squeeze else calibrated


def method_label_from_string(method_str: str) -> int:
    """Convert method string from fights.parquet to integer label.

    Returns 0 (Decision) as fallback for unknown methods.
    """
    m = str(method_str).strip().upper()
    if "KO" in m or "TKO" in m:
        return 1
    if "SUB" in m or "SUBMISS" in m:
        return 2
    return 0


def encode_method_labels(method_series: pd.Series) -> np.ndarray:
    """Convert a pandas Series of method strings to integer labels (0/1/2)."""
    return np.array([method_label_from_string(m) for m in method_series], dtype=int)
