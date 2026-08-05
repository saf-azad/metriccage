"""Re-score the SHIPPED 4-stream bundle on the frozen temporal test split and
dump every stream's probability, so the site's model page can stop publishing
placeholders.

The site currently ships five `verified: false` flags (reliability bins, Brier
by year, ECE, feature importance, SHAP) because final_predictions.parquet is the
legacy 3-stream file. This reproduces the real thing:
   train 2005-01-01..2022-12-31 | val 2023 | test 2024-01-01..2025-05-04
   -> 5563 / 504 / 695, which matches the bundle's own best_config exactly.

Output: streams.parquet  (one row per test fight, one column per stream)
"""
import os
import pickle
import sys
import warnings
from datetime import date

import numpy as np
import pandas as pd
import torch

warnings.filterwarnings("ignore")
sys.path.insert(0, os.environ.get("UFC_REPO", "."))  # the ufc-fight-predictor checkout

REPO = os.environ.get("UFC_REPO", ".")
P = f"{REPO}/data/processed"
OUT = os.environ.get("MC_OUT", "/home/claude/mc-analysis")

bundle = pickle.load(open(f"{P}/final_model_bundle.pkl", "rb"))
mat = pd.read_parquet(f"{P}/feature_matrix_built.parquet")
fights = pd.read_parquet(f"{REPO}/data/interim/fights_enriched.parquet")

mat["event_date"] = pd.to_datetime(mat["event_date"])
d = mat["event_date"].dt.date
TRAIN = mat[(d >= date(2005, 1, 1)) & (d <= date(2022, 12, 31))]
VAL = mat[(d >= date(2023, 1, 1)) & (d <= date(2023, 12, 31))].reset_index(drop=True)
TEST = mat[(d >= date(2024, 1, 1)) & (d <= date(2025, 5, 4))].reset_index(drop=True)
print(f"split: train={len(TRAIN)} val={len(VAL)} test={len(TEST)}  (expect 5563/504/695)")

feats = bundle["feats"]
xgb_feats = bundle["xgb_feats"]
W = bundle["weights"]
ELO_SCALE = bundle["elo_scale"]


def stream_probs(df):
    X = df[feats].fillna(0.0)
    p_lr = bundle["lr"].predict_proba(X)[:, 1]
    p_xg = bundle["xgb"].predict_proba(df[xgb_feats].fillna(0.0))[:, 1]
    if "elo_prob_a" in df.columns and df["elo_prob_a"].notna().any():
        p_el = df["elo_prob_a"].fillna(0.5).to_numpy()
    else:
        p_el = 1.0 / (1.0 + 10 ** (-df["elo_diff"].fillna(0.0) / ELO_SCALE))
    return p_lr, p_xg, p_el


# ---- LSTM stream -----------------------------------------------------------
from src.models.career_lstm import FightPredictor, predict_model_c  # noqa: E402


class _R:
    pass


cfg = bundle["lstm_config"]
model = FightPredictor(cfg["sequence_input_dim"], cfg["diff_feature_dim"])
model.load_state_dict(bundle["lstm_state_dict"])
model.eval()
res = _R()
res.model = model
res.diff_feature_cols = bundle["lstm_diff_cols"]

fights = fights.sort_values("event_date").reset_index(drop=True)


def score(df, label):
    p_lr, p_xg, p_el = stream_probs(df)
    p_ls = predict_model_c(res, fights, df, seq_len=bundle["lstm_seq_len"])
    S = pd.DataFrame({"logreg": p_lr, "xgb": p_xg, "elo": p_el, "lstm": p_ls})
    w = np.array([W[c] for c in S.columns])
    blend = np.clip(S.to_numpy() @ w, 1e-6, 1 - 1e-6)
    cal = np.clip(bundle["iso_blend"].predict(blend), 1e-6, 1 - 1e-6)
    S["blend_raw"] = blend
    S["p_final"] = cal
    S["y"] = df["fighter_a_won"].to_numpy()
    for c in ["fight_id", "event_date", "weight_class", "fighter_a_name", "fighter_b_name",
              "method", "n_fights_a", "n_fights_b", "round_finished", "fight_duration_min"]:
        if c in df.columns:
            S[c] = df[c].to_numpy()
    print(f"{label}: n={len(S)}")
    return S


test = score(TEST, "test")
val = score(VAL, "val")
train = score(TRAIN, "train")

from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score  # noqa: E402

y, p = test["y"].to_numpy(), test["p_final"].to_numpy()
got = {
    "n": len(test),
    "accuracy": float(((p > 0.5).astype(int) == y).mean()),
    "brier": brier_score_loss(y, p),
    "logloss": log_loss(y, p),
    "auc": roc_auc_score(y, p),
}
want = bundle["best_config"]["test_metrics"]
print("\nreproduction check (mine vs bundle best_config):")
ok = True
for k in ("n", "accuracy", "brier", "logloss", "auc"):
    delta = abs(got[k] - want[k])
    flag = "OK " if delta < 2e-3 else "DIFF"
    ok &= delta < 2e-3
    print(f"  {flag} {k:9s} {got[k]:.6f}  vs published {want[k]:.6f}   (d={delta:.2e})")
print("REPRODUCED" if ok else "NOT REPRODUCED")

os.makedirs(OUT, exist_ok=True)
test.to_parquet(f"{OUT}/streams_test.parquet")
val.to_parquet(f"{OUT}/streams_val.parquet")
train.to_parquet(f"{OUT}/streams_train.parquet")
print(f"wrote {OUT}/streams_{{test,val,train}}.parquet")
