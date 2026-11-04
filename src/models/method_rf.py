"""Model B — Random Forest method-of-victory classifier (PLAN §6.4 design).

Implemented per PLAN §6.4 for interface completeness; production uses the
two-stage XGB head in method_two_stage.py (decision 2026-07-02).
The shipped bundle's ``method_head == "two_stage"`` and the api scores it via
the math ported into ``src/models/method_two_stage.py`` — this RF is the
original design kept as a working reference implementation.

3-class: KO/TKO, Submission, Decision. NC/DQ/Draw are folded into Decision
because they are statistically rare and the model has no predictive signal for
them. ``class_weight='balanced'`` handles the label imbalance (the plan's
optional SMOTE-on-submissions step is not applied here).

Labels are the METHOD_LABELS strings below; ``predict_method_proba`` always
returns columns in that order regardless of the fitted ``classes_`` order.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.config import RANDOM_SEED

METHOD_LABELS = ["KO/TKO", "Submission", "Decision"]

#: Light defaults per PLAN §6.4; override via the ``params`` argument
#: (tests pass tiny n_estimators).
RF_DEFAULTS: dict[str, Any] = {
    "n_estimators": 400,
    "max_depth": None,
    "min_samples_leaf": 5,
    "class_weight": "balanced",
    "random_state": RANDOM_SEED,
    "n_jobs": -1,
}


def train_model_b(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    params: dict[str, Any] | None = None,
):
    """Returns (rf_classifier, metrics_dict).

    ``y_train`` / ``y_val`` hold METHOD_LABELS strings. ``params`` overrides
    :data:`RF_DEFAULTS` (e.g. tiny ``n_estimators`` for tests/smoke runs).
    Metrics are computed on the validation slice.
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, log_loss

    cfg = {**RF_DEFAULTS, **(params or {})}
    rf = RandomForestClassifier(**cfg)
    rf.fit(X_train, y_train)

    # Clip away exact 0/1 leaves (small forests emit them) then renormalise so
    # log_loss sees proper probability vectors.
    raw_val = np.clip(rf.predict_proba(X_val), 1e-6, 1 - 1e-6)
    raw_val = raw_val / raw_val.sum(axis=1, keepdims=True)
    metrics = {
        "val_accuracy": float(accuracy_score(y_val, rf.predict(X_val))),
        "val_logloss": float(log_loss(y_val, raw_val, labels=list(rf.classes_))),
        "n_train": int(len(X_train)),
        "n_val": int(len(X_val)),
    }
    return rf, metrics


def predict_method_proba(model, X: pd.DataFrame) -> pd.DataFrame:
    """Returns DataFrame with columns METHOD_LABELS (rows sum to 1).

    Columns are reordered from the model's ``classes_``; any METHOD_LABELS
    class absent from training gets probability 0.0.
    """
    raw = np.asarray(model.predict_proba(X), dtype=float)
    by_class = {str(c): raw[:, i] for i, c in enumerate(model.classes_)}
    zeros = np.zeros(len(raw))
    return pd.DataFrame(
        {label: by_class.get(label, zeros) for label in METHOD_LABELS},
        index=getattr(X, "index", None),
    )
