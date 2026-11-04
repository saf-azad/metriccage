"""SHAP-based feature pruning analysis.

Loads the trained XGBoost from final_model_bundle.pkl, computes SHAP values
on the validation slice, and outputs a recommendation:
  * KEEP — features with mean |SHAP| >= 2.0 (UPDATE_2.md threshold)
  * DROP — features below threshold

Writes:
  data/processed/feature_prune_report.json
  data/processed/feature_prune_drop_list.txt   (one feature per line)
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import PROCESSED

BUNDLE = PROCESSED / "final_model_bundle.pkl"
MATRIX = PROCESSED / "feature_matrix_built.parquet"

# Mean |SHAP| threshold (log-odds units, not gain-based importance).
# Features below 0.005 contribute negligibly to per-fight predictions.
THRESHOLD = 0.005


def main() -> None:
    bundle = pickle.load(open(BUNDLE, "rb"))
    matrix = pd.read_parquet(MATRIX)
    feats = bundle["feats"]

    # Use validation slice as SHAP eval set
    matrix["event_date"] = pd.to_datetime(matrix["event_date"])
    val_mask = (matrix["event_date"] >= "2023-01-01") & (matrix["event_date"] < "2024-01-01")
    val = matrix[val_mask][feats].fillna(0.0)
    if len(val) < 50:
        # Fallback: use the most recent 504 rows
        val = matrix[feats].fillna(0.0).tail(504)

    clf = bundle["xgb"]
    # Try real SHAP via the underlying booster; fall back to feature_importances_.
    shap_vals = None
    try:
        import xgboost as xgb
        booster = clf.get_booster() if hasattr(clf, "get_booster") else clf
        dmat = xgb.DMatrix(val, feature_names=feats)
        shap_vals = booster.predict(dmat, pred_contribs=True)
        shap_vals = shap_vals[:, :-1]  # drop bias column
    except Exception as e:
        print(f"WARN: SHAP predict failed ({e}); falling back to feature_importances_")

    if shap_vals is not None:
        mean_abs_shap = np.abs(shap_vals).mean(axis=0)
        ranked = sorted(zip(feats, mean_abs_shap.tolist(), strict=True), key=lambda kv: -kv[1])
    else:
        importances = getattr(clf, "feature_importances_", None)
        if importances is None or len(importances) != len(feats):
            print("ERROR: cannot extract any feature importances")
            sys.exit(1)
        # feature_importances_ are normalised gain in [0, 1]; rescale by 100 so
        # the threshold (2.0) is comparable to SHAP units used in metrics.json.
        scaled = (importances * 100).tolist()
        ranked = sorted(zip(feats, scaled, strict=True), key=lambda kv: -kv[1])

    keep = [(f, float(s)) for f, s in ranked if s >= THRESHOLD]
    drop = [(f, float(s)) for f, s in ranked if s < THRESHOLD]

    print(f"\n{'='*70}\nSHAP FEATURE PRUNE — threshold {THRESHOLD}")
    print(f"{'='*70}")
    print(f"  Total features: {len(feats)}")
    print(f"  KEEP (>= {THRESHOLD}): {len(keep)}")
    print(f"  DROP (< {THRESHOLD}): {len(drop)}")
    print()
    print("TOP 25 KEPT:")
    for f, s in keep[:25]:
        print(f"  {f:35s}  {s:.2f}")
    print()
    print(f"DROPPING (lowest 15 of {len(drop)}):")
    for f, s in drop[-15:]:
        print(f"  {f:35s}  {s:.2f}")
    print()

    drop_path = PROCESSED / "feature_prune_drop_list.txt"
    with open(drop_path, "w") as f:
        f.write("\n".join(name for name, _ in drop))
    print(f"Saved drop list -> {drop_path}")

    report = {
        "threshold": THRESHOLD,
        "n_total": len(feats),
        "n_keep": len(keep),
        "n_drop": len(drop),
        "keep": [{"feature": f, "shap": s} for f, s in keep],
        "drop": [{"feature": f, "shap": s} for f, s in drop],
    }
    out = PROCESSED / "feature_prune_report.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Saved report -> {out}")


if __name__ == "__main__":
    main()
