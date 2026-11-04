"""Two-stage XGBoost method-of-victory head — the PRODUCTION method model.

This module is the canonical, importable port of the training logic in
``scripts/retrain_twostage_only.py``, which produced the method head shipped in
``data/processed/final_model_bundle.pkl`` (``bundle["method_head"] == "two_stage"``,
trained 2026-05-11). docs/PLAN.md §6.4's original Model B design (a 3-class
RandomForest, ``src/models/method_rf.py``) is superseded in production by this
head — decided 2026-07-02.

ARCHITECTURE (binary chain, each stage isotonically calibrated on val):
    Stage 1: finish (KO/TKO or Submission) vs Decision.
    Stage 2: Submission vs KO/TKO, trained only on finish rows, with sample
             weights ``inv_freq × [1.0, sub_boost]`` (sub_boost=1.6 in
             production) to fight the KO-majority bias without wrecking
             calibration the way the single 3-class classifier did.

LABEL CONVENTION (matches ``src.features.method_calibration.encode_method_labels``):
    0 = Decision, 1 = KO/TKO, 2 = Submission.

COMBINED 3-CLASS MATH — exactly what ``src/api/predict_fight._method_distribution``
computes at inference in its two-stage branch:
    p_finish        = clip(iso1(stage1.predict_proba[:, 1]), 1e-6, 1 - 1e-6)
    p_sub_g_finish  = clip(iso2(stage2.predict_proba[:, 1]), 1e-6, 1 - 1e-6)
    p_decision      = 1 - p_finish
    p_ko            = p_finish * (1 - p_sub_g_finish)
    p_sub           = p_finish * p_sub_g_finish
    (then normalised by their sum)
The api additionally blends in a ``sub_danger_combined`` domain prior when that
feature exceeds 0.15; that overlay is an api-level adjustment and intentionally
lives there, not here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

EPS = 1e-6

#: Output column order of :func:`predict_method_proba_two_stage`.
METHOD_CLASS_NAMES = ["Decision", "KO/TKO", "Submission"]

#: Exact METHOD_PARAMS used to train the production head
#: (scripts/retrain_twostage_only.py; ``early_stopping_rounds`` was passed to the
#: XGBClassifier constructor alongside them). Override any of these via the
#: ``params`` argument of :func:`train_method_two_stage` — tests/smoke runs pass
#: tiny values.
TWO_STAGE_METHOD_PARAMS: dict[str, Any] = {
    "max_depth": 4,
    "learning_rate": 0.03,
    "n_estimators": 500,
    "min_child_weight": 5,
    "reg_alpha": 0.3,
    "reg_lambda": 1.5,
    "subsample": 0.85,
    "colsample_bytree": 0.8,
    "gamma": 0.05,
    "early_stopping_rounds": 40,
}


@dataclass
class TwoStageMethodResult:
    """Trained two-stage method head (mirrors the production bundle keys)."""

    stage1_finish: Any  # XGBClassifier — finish vs decision
    stage1_iso: IsotonicRegression
    stage2_sub: Any  # XGBClassifier — sub vs ko, given finish
    stage2_iso: IsotonicRegression
    metrics: dict[str, float] = field(default_factory=dict)
    method_head: str = "two_stage"


def _fit_xgb_binary(
    params: dict[str, Any],
    X_tr: pd.DataFrame,
    y_tr: np.ndarray,
    X_v: pd.DataFrame,
    y_v: np.ndarray,
    sample_weight: np.ndarray | None = None,
) -> Any:
    """Fit one binary XGB stage with early stopping on the val slice.

    Identical construction to scripts/retrain_twostage_only.py::_fit_xgb_binary.
    """
    from xgboost import XGBClassifier

    clf = XGBClassifier(
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
        **params,
    )
    clf.fit(X_tr, y_tr, eval_set=[(X_v, y_v)], sample_weight=sample_weight, verbose=False)
    return clf


def train_method_two_stage(
    X_train: pd.DataFrame,
    y_method_train: pd.Series | np.ndarray,
    X_val: pd.DataFrame,
    y_method_val: pd.Series | np.ndarray,
    *,
    params: dict[str, Any] | None = None,
    sub_boost: float = 1.6,
) -> TwoStageMethodResult:
    """Train the production two-stage method head.

    Parameters
    ----------
    X_train, X_val : feature frames (production uses the pruned ``method_feats``
        columns of ``feature_matrix_built.parquet``, NaNs filled with 0.0).
    y_method_train, y_method_val : integer method labels
        (0=Decision, 1=KO/TKO, 2=Submission).
    params : overrides merged over :data:`TWO_STAGE_METHOD_PARAMS`
        (``early_stopping_rounds`` may be overridden or set to None too).
    sub_boost : extra multiplier on the Submission class weight in stage 2
        (production value 1.6 — subs are ~36% of finishes).

    Returns
    -------
    TwoStageMethodResult with both stages, both isotonics, and val metrics
    (``stage1_val_auc``, ``stage2_val_auc``, ``val_top1_acc``).
    """
    from sklearn.metrics import roc_auc_score

    cfg = {**TWO_STAGE_METHOD_PARAMS, **(params or {})}
    y_tr = np.asarray(y_method_train, dtype=int)
    y_v = np.asarray(y_method_val, dtype=int)

    # --- Stage 1: finish (KO or Sub) vs decision ------------------------------
    y_finish_tr = (y_tr != 0).astype(int)
    y_finish_v = (y_v != 0).astype(int)
    stage1 = _fit_xgb_binary(cfg, X_train, y_finish_tr, X_val, y_finish_v)
    raw_finish_v = stage1.predict_proba(X_val)[:, 1]

    iso1 = IsotonicRegression(out_of_bounds="clip")
    iso1.fit(raw_finish_v, y_finish_v)

    # --- Stage 2: sub vs ko (only on finish rows) -----------------------------
    finish_mask_tr = y_finish_tr == 1
    finish_mask_v = y_finish_v == 1
    y_sub_tr = (y_tr[finish_mask_tr] == 2).astype(int)
    y_sub_v = (y_v[finish_mask_v] == 2).astype(int)
    X_tr_finish = X_train.iloc[np.where(finish_mask_tr)[0]]
    X_v_finish = X_val.iloc[np.where(finish_mask_v)[0]]

    # Class weights: inverse frequency, then boost subs to lift sub recall.
    counts_s2 = np.bincount(y_sub_tr, minlength=2).astype(float)
    counts_s2 = np.where(counts_s2 > 0, counts_s2, 1.0)  # guard tiny synthetic data
    inv_s2 = counts_s2.sum() / (counts_s2 * 2.0)
    weights_s2 = inv_s2 * np.array([1.0, sub_boost])
    sw_s2 = weights_s2[y_sub_tr]

    stage2 = _fit_xgb_binary(cfg, X_tr_finish, y_sub_tr, X_v_finish, y_sub_v, sample_weight=sw_s2)
    raw_sub_v = stage2.predict_proba(X_v_finish)[:, 1]

    iso2 = IsotonicRegression(out_of_bounds="clip")
    iso2.fit(raw_sub_v, y_sub_v)

    # --- Val metrics (same diagnostics as the training script) ----------------
    metrics: dict[str, float] = {}
    if len(np.unique(y_finish_v)) > 1:
        metrics["stage1_val_auc"] = float(roc_auc_score(y_finish_v, raw_finish_v))
    if len(np.unique(y_sub_v)) > 1:
        metrics["stage2_val_auc"] = float(roc_auc_score(y_sub_v, raw_sub_v))

    result = TwoStageMethodResult(
        stage1_finish=stage1, stage1_iso=iso1, stage2_sub=stage2, stage2_iso=iso2
    )
    P = predict_method_proba_two_stage(result, X_val).to_numpy()
    metrics["val_top1_acc"] = float((P.argmax(axis=1) == y_v).mean())
    result.metrics = metrics
    return result


def _resolve_components(bundle_like: Any) -> tuple[Any, Any, Any, Any]:
    """Extract (stage1, iso1, stage2, iso2) from any supported container."""
    if isinstance(bundle_like, TwoStageMethodResult):
        return (
            bundle_like.stage1_finish,
            bundle_like.stage1_iso,
            bundle_like.stage2_sub,
            bundle_like.stage2_iso,
        )
    if isinstance(bundle_like, Mapping):
        stage1 = bundle_like.get("method_stage1_finish")
        stage2 = bundle_like.get("method_stage2_sub")
        if stage1 is None or stage2 is None:
            raise KeyError(
                "Mapping is missing the two-stage bundle keys "
                "'method_stage1_finish' / 'method_stage2_sub'"
            )
        return (
            stage1,
            bundle_like.get("method_stage1_iso"),
            stage2,
            bundle_like.get("method_stage2_iso"),
        )
    raise TypeError(
        f"Unsupported bundle_like type {type(bundle_like).__name__}; expected a "
        "TwoStageMethodResult or a dict with the production bundle keys"
    )


def predict_method_proba_two_stage(bundle_like: Any, X: pd.DataFrame) -> pd.DataFrame:
    """Score the two-stage head → 3-class method probabilities.

    ``bundle_like`` may be a :class:`TwoStageMethodResult` OR any mapping that
    carries the raw production bundle keys (``method_stage1_finish``,
    ``method_stage1_iso``, ``method_stage2_sub``, ``method_stage2_iso``) — the
    full production bundle dict works directly. ``X`` must already contain the
    model's feature columns (production: bundle ``method_feats``, NaN→0.0).

    The math is EXACTLY the two-stage branch of
    ``src/api/predict_fight._method_distribution`` (isotonics applied, both
    stage probabilities clipped to [1e-6, 1-1e-6], products normalised by their
    sum). The api's optional ``sub_danger_combined`` prior blend is NOT applied
    here — that is a separate api-level overlay.

    Returns a DataFrame indexed like ``X`` with columns
    ``["Decision", "KO/TKO", "Submission"]`` summing to 1 per row.
    """
    stage1, iso1, stage2, iso2 = _resolve_components(bundle_like)

    p_finish = np.asarray(stage1.predict_proba(X))[:, 1].astype(float)
    if iso1 is not None:
        p_finish = np.asarray(iso1.predict(p_finish), dtype=float)
    p_finish = np.clip(p_finish, EPS, 1 - EPS)

    p_sub_g_finish = np.asarray(stage2.predict_proba(X))[:, 1].astype(float)
    if iso2 is not None:
        p_sub_g_finish = np.asarray(iso2.predict(p_sub_g_finish), dtype=float)
    p_sub_g_finish = np.clip(p_sub_g_finish, EPS, 1 - EPS)

    p_decision = 1.0 - p_finish
    p_ko = p_finish * (1.0 - p_sub_g_finish)
    p_sub = p_finish * p_sub_g_finish
    total = p_decision + p_ko + p_sub

    return pd.DataFrame(
        {
            "Decision": p_decision / total,
            "KO/TKO": p_ko / total,
            "Submission": p_sub / total,
        },
        index=getattr(X, "index", None),
    )


def as_bundle_keys(result: TwoStageMethodResult) -> dict[str, Any]:
    """Map a training result to the EXACT production bundle key names.

    Merging this dict into a model bundle is what makes the api's two-stage
    branch light up (it checks ``method_head == "two_stage"``).
    """
    return {
        "method_head": result.method_head,
        "method_stage1_finish": result.stage1_finish,
        "method_stage1_iso": result.stage1_iso,
        "method_stage2_sub": result.stage2_sub,
        "method_stage2_iso": result.stage2_iso,
    }
