"""
model_eval2.py — the parts of the model story that needed more than a metric.

Four things live here:

  1. CALIBRATOR AUDIT. The shipped isotonic regression is fitted on 504 validation
     fights, and it maps 695 distinct blended probabilities onto a small number of
     distinct output values. That is a step function pretending to be a forecast.
     Compared here against Platt scaling and against no calibration at all.

  2. PERMUTATION IMPORTANCE AT THE SYSTEM LEVEL. The site currently ranks features
     by XGBoost gain, taken from ONE stream carrying 35% of the weight, and uses it
     to make a claim about the whole ensemble. Gain is biased toward continuous and
     high-cardinality splits and is unstable across refits. This permutes each
     feature in the held-out test set and re-scores every stream, which is what the
     sentence on the page actually claims.

  3. SHAP ACROSS THE TEST SET, not one waterfall.

  4. THE CARD, DONE AS A BINOMIAL. "9 of 13" is not an accuracy claim, and the
     alternative to a misleading rate is not silence — it is the Poisson-binomial
     distribution implied by the model's own probabilities for those 13 fights.

Output: model_eval2.json
"""

import json
import os
import pickle
import sys
import warnings
from datetime import date

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

warnings.filterwarnings("ignore")
sys.path.insert(0, os.environ.get("UFC_REPO", "."))

OUT = os.environ.get("MC_OUT", "/home/claude/mc-analysis")
P = os.environ.get("UFC_REPO", ".") + "/data/processed"
UFC = os.environ.get("UFC_DATA", "/home/claude/ufc-data")
EPS = 1e-6
rng = np.random.default_rng(20260802)

test = pd.read_parquet(f"{OUT}/streams_test.parquet")
val = pd.read_parquet(f"{OUT}/streams_val.parquet")
y = test["y"].to_numpy().astype(int)
p = test["p_final"].to_numpy()
N = len(test)
bundle = pickle.load(open(f"{P}/final_model_bundle.pkl", "rb"))
STREAMS = ["logreg", "xgb", "elo", "lstm"]
W = np.array([bundle["weights"][s] for s in STREAMS])


def ece(y_true, y_prob, n_bins=10):
    edges = np.unique(np.quantile(y_prob, np.linspace(0, 1, n_bins + 1)))
    idx = np.clip(np.digitize(y_prob, edges[1:-1]), 0, len(edges) - 2)
    n = len(y_true)
    e = 0.0
    for b in range(len(edges) - 1):
        m = idx == b
        if m.sum():
            e += m.sum() / n * abs(y_true[m].mean() - y_prob[m].mean())
    return float(e)


def score_all(probs):
    probs = np.clip(probs, EPS, 1 - EPS)
    return {
        "logloss": round(float(log_loss(y, probs)), 5),
        "brier": round(float(brier_score_loss(y, probs)), 5),
        "auc": round(float(roc_auc_score(y, probs)), 5),
        "ece": round(ece(y, probs), 5),
        "accuracy": round(float(((probs > 0.5).astype(int) == y).mean()), 5),
        "n_distinct": int(len(np.unique(np.round(probs, 6)))),
        "sd": round(float(probs.std()), 5),
        "pct_within_10pts_of_half": round(float((np.abs(probs - 0.5) <= 0.10).mean()), 4),
    }


# ====================================================== 1. calibrator audit
blend_v = np.clip(val[STREAMS].to_numpy() @ W, EPS, 1 - EPS)
blend_t = np.clip(test[STREAMS].to_numpy() @ W, EPS, 1 - EPS)
yv = val["y"].to_numpy().astype(int)

iso = bundle["iso_blend"]
platt = LogisticRegression(C=1e6).fit(np.log(blend_v / (1 - blend_v)).reshape(-1, 1), yv)

variants = {
    "shipped_isotonic": np.clip(iso.predict(blend_t), EPS, 1 - EPS),
    "platt_sigmoid": platt.predict_proba(np.log(blend_t / (1 - blend_t)).reshape(-1, 1))[:, 1],
    "uncalibrated_blend": blend_t,
}
calibrator_audit = {k: score_all(v) for k, v in variants.items()}
uv, uc = np.unique(np.round(variants["shipped_isotonic"], 6), return_counts=True)
calibrator_audit["isotonic_quantisation"] = {
    "n_input_values": int(len(np.unique(np.round(blend_t, 9)))),
    "n_output_values": int(len(uv)),
    "largest_atom_size": int(uc.max()),
    "largest_atom_value": round(float(uv[uc.argmax()]), 4),
    "largest_atom_pct_of_test": round(float(uc.max() / N), 4),
    "top_atoms": [{"value": round(float(v), 4), "n": int(c)}
                  for v, c in sorted(zip(uv, uc), key=lambda t: -t[1])[:8]],
    "n_val_fights_calibrator_was_fit_on": int(len(val)),
    "note": "isotonic on 504 validation points is a step function; it buys calibration "
            "by destroying resolution, and the step edges are visible in the histogram",
}
print("calibrator audit:")
for k in ("shipped_isotonic", "platt_sigmoid", "uncalibrated_blend"):
    v = calibrator_audit[k]
    print(f"  {k:20s} ll {v['logloss']:.5f} brier {v['brier']:.5f} ece {v['ece']:.5f} "
          f"auc {v['auc']:.4f} distinct={v['n_distinct']:4d} sd={v['sd']:.4f}")
q = calibrator_audit["isotonic_quantisation"]
print(f"  quantisation: {q['n_input_values']} -> {q['n_output_values']} distinct values; "
      f"biggest atom {q['largest_atom_value']} holds {q['largest_atom_size']} fights "
      f"({q['largest_atom_pct_of_test']*100:.1f}%)")

# ====================================================== 2. permutation importance
from src.models.career_lstm import FightPredictor, predict_model_c  # noqa: E402

mat = pd.read_parquet(f"{P}/feature_matrix_built.parquet")
mat["event_date"] = pd.to_datetime(mat["event_date"])
d = mat["event_date"].dt.date
TEST = mat[(d >= date(2024, 1, 1)) & (d <= date(2025, 5, 4))].reset_index(drop=True)
fights = pd.read_parquet(os.environ.get("UFC_REPO", ".") + "/data/interim/fights_enriched.parquet")
fights = fights.sort_values("event_date").reset_index(drop=True)

feats, xgb_feats = bundle["feats"], bundle["xgb_feats"]
cfg = bundle["lstm_config"]
_m = FightPredictor(cfg["sequence_input_dim"], cfg["diff_feature_dim"])
_m.load_state_dict(bundle["lstm_state_dict"])
_m.eval()


class _R:
    pass


res = _R()
res.model = _m
res.diff_feature_cols = bundle["lstm_diff_cols"]


# Career sequences are a function of fight HISTORY, not of the fight-day diff
# features being permuted, so they are identical across all 306 permutation passes.
# Build the padded batches once; each pass only swaps the diff tensor. Without this
# the LSTM stream dominates runtime and the whole thing takes hours.
import torch  # noqa: E402
from torch.utils.data import DataLoader  # noqa: E402

from src.models.career_lstm import CareerSequenceDataset, _collate  # noqa: E402

LSTM_COLS = bundle["lstm_diff_cols"]
_ds = CareerSequenceDataset(fights, TEST.reset_index(drop=True), LSTM_COLS,
                            max_seq_len=bundle["lstm_seq_len"],
                            past_fight_dim=_m.encoder.lstm.input_size)
_cached = []
_row = 0
for _b in DataLoader(_ds, batch_size=256, shuffle=False, collate_fn=_collate):
    k = _b["diff"].shape[0]
    _cached.append({"a_seq": _b["a_seq"], "a_lengths": _b["a_lengths"],
                    "b_seq": _b["b_seq"], "b_lengths": _b["b_lengths"],
                    "slice": slice(_row, _row + k)})
    _row += k
print(f"cached {len(_cached)} LSTM batches covering {_row} test rows")


def lstm_probs(df):
    D = torch.from_numpy(df[LSTM_COLS].fillna(0.0).to_numpy(dtype=np.float32))
    out = []
    with torch.no_grad():
        for b in _cached:
            logits = _m(b["a_seq"], b["a_lengths"], b["b_seq"], b["b_lengths"], D[b["slice"]])
            out.append(torch.sigmoid(logits).numpy())
    return np.concatenate(out)


def full_pipeline(df):
    p_lr = bundle["lr"].predict_proba(df[feats].fillna(0.0))[:, 1]
    p_xg = bundle["xgb"].predict_proba(df[xgb_feats].fillna(0.0))[:, 1]
    p_el = df["elo_prob_a"].fillna(0.5).to_numpy()
    p_ls = lstm_probs(df)
    b = np.clip(np.column_stack([p_lr, p_xg, p_el, p_ls]) @ W, EPS, 1 - EPS)
    return np.clip(iso.predict(b), EPS, 1 - EPS)


base = full_pipeline(TEST)
base_ll = log_loss(y, base)
assert abs(base_ll - log_loss(y, p)) < 1e-9, "pipeline drift"

N_REPEATS = int(os.environ.get("MC_PERM_REPEATS", "3"))
perm = []
for i, f in enumerate(feats):
    deltas = []
    for r in range(N_REPEATS):
        d2 = TEST.copy()
        d2[f] = d2[f].sample(frac=1.0, random_state=1000 * r + i).to_numpy()
        deltas.append(log_loss(y, full_pipeline(d2)) - base_ll)
    perm.append({"feature": f,
                 "delta_logloss": round(float(np.mean(deltas)), 6),
                 "sd": round(float(np.std(deltas)), 6)})
    if (i + 1) % 20 == 0:
        print(f"  permuted {i+1}/{len(feats)}")
perm.sort(key=lambda r: -r["delta_logloss"])
print("\ntop 12 by permutation importance (held-out log-loss damage):")
for r in perm[:12]:
    print(f"  {r['feature']:26s} {r['delta_logloss']:+.5f} (sd {r['sd']:.5f})")
gain = {k: v for k, v in bundle["best_config"].get("feature_importance", [])} if isinstance(
    bundle["best_config"].get("feature_importance"), list) else {}

# ====================================================== 3. SHAP over the test set
shap_summary = None
try:
    import shap

    ex = shap.TreeExplainer(bundle["xgb"])
    sv = ex.shap_values(TEST[xgb_feats].fillna(0.0))
    mean_abs = np.abs(sv).mean(axis=0)
    order = np.argsort(-mean_abs)[:16]
    shap_summary = {
        "stream": "xgb (35.3% of ensemble weight)",
        "n_test": int(len(TEST)),
        "features": [{
            "feature": xgb_feats[i],
            "mean_abs_shap": round(float(mean_abs[i]), 5),
            # beeswarm needs (shap value, feature value) pairs; subsample to keep JSON small
            "points": [[round(float(sv[j, i]), 4),
                        round(float(TEST[xgb_feats[i]].fillna(0.0).iloc[j]), 4)]
                       for j in rng.choice(len(TEST), size=min(220, len(TEST)), replace=False)],
        } for i in order],
    }
    print(f"\nSHAP: top feature {xgb_feats[order[0]]} mean|SHAP| {mean_abs[order[0]]:.4f}")
except Exception as e:  # pragma: no cover
    print("SHAP unavailable:", e)

# ====================================================== 4. the card, as a binomial
card = json.load(open(f"{P}/macau_predictions.json"))
r_all = pd.read_csv(f"{UFC}/ufc_fight_results.csv")
for c in r_all.columns:
    if r_all[c].dtype == object:
        r_all[c] = r_all[c].astype(str).str.strip()
ev = r_all[r_all["EVENT"].str.contains("Song vs. Figueiredo", case=False, na=False)]


def winner_of(row):
    a, b = [x.strip() for x in row["BOUT"].split(" vs. ")]
    if row["OUTCOME"] == "W/L":
        return a
    if row["OUTCOME"] == "L/W":
        return b
    return None


actual = {}
for _, row in ev.iterrows():
    a, b = [x.strip() for x in row["BOUT"].split(" vs. ")]
    actual[frozenset({a.lower(), b.lower()})] = {
        "winner": (winner_of(row) or "").lower(), "method": row["METHOD"], "no_contest": winner_of(row) is None}

rows, probs, hits = [], [], []
for f in card["fights"]:
    key = frozenset({f["a"].lower(), f["b"].lower()})
    act = actual.get(key)
    if not act or act["no_contest"] or not f.get("ok"):
        rows.append({"a": f["a"], "b": f["b"], "scored": False,
                     "reason": "no contest" if act and act["no_contest"] else "not scored by model"})
        continue
    pa = float(f["p_a"])
    pick_a = pa >= 0.5
    won_a = act["winner"] == f["a"].lower()
    correct = pick_a == won_a
    pick_prob = pa if pick_a else 1 - pa
    rows.append({"a": f["a"], "b": f["b"], "scored": True, "p_a": round(pa, 4),
                 "pick": f["a"] if pick_a else f["b"], "pick_prob": round(pick_prob, 4),
                 "winner": act["winner"], "correct": bool(correct), "method": act["method"]})
    probs.append(pick_prob)
    hits.append(bool(correct))

probs = np.array(probs)
k_actual = int(sum(hits))
n_scored = len(probs)


def poisson_binomial(ps):
    """Exact distribution of the number of correct picks, given each pick's own
    probability. This is the right null for a 13-fight card; a binomial with a
    single p is not, because the picks are not equally confident."""
    dist = np.zeros(len(ps) + 1)
    dist[0] = 1.0
    for pi in ps:
        dist[1:] = dist[1:] * (1 - pi) + dist[:-1] * pi
        dist[0] *= (1 - pi)
    return dist


dist = poisson_binomial(probs)
expected = float((np.arange(len(dist)) * dist).sum())
p_at_least = float(dist[k_actual:].sum())
p_at_most = float(dist[: k_actual + 1].sum())
card_check = {
    "event": card["event"], "date": card["date"],
    "n_on_card": len(card["fights"]), "n_scored": n_scored,
    "correct": k_actual,
    "expected_correct": round(expected, 3),
    "sd_correct": round(float(np.sqrt((probs * (1 - probs)).sum())), 3),
    "distribution": [round(float(x), 5) for x in dist],
    "p_at_least_observed": round(p_at_least, 4),
    "p_at_most_observed": round(p_at_most, 4),
    "central80": [int(np.searchsorted(np.cumsum(dist), 0.10)), int(np.searchsorted(np.cumsum(dist), 0.90))],
    "mean_pick_confidence": round(float(probs.mean()), 4),
    "fights": rows,
    "verdict": None,
}
lo, hi = card_check["central80"]
card_check["verdict"] = ("within tolerance" if lo <= k_actual <= hi else "outside the central 80%")
print(f"\ncard: {k_actual}/{n_scored} correct; model expected {expected:.2f} "
      f"(sd {card_check['sd_correct']}), central 80% = {lo}-{hi} -> {card_check['verdict']}")
print(f"  P(at least {k_actual}) = {p_at_least:.3f}")

# ====================================================== veteran / green AUC gap
test["min_fights"] = test[["n_fights_a", "n_fights_b"]].min(axis=1)
vet = test[test["min_fights"] >= 5]
green = test[test["min_fights"] < 3]


def bootstrap_auc_gap(g1, g2, n=3000):
    out = []
    for _ in range(n):
        a = g1.sample(len(g1), replace=True, random_state=int(rng.integers(1e9)))
        b = g2.sample(len(g2), replace=True, random_state=int(rng.integers(1e9)))
        if a["y"].nunique() < 2 or b["y"].nunique() < 2:
            continue
        out.append(roc_auc_score(a["y"], a["p_final"]) - roc_auc_score(b["y"], b["p_final"]))
    return out


gaps = bootstrap_auc_gap(vet, green)
experience_auc = {
    "veteran_auc": round(float(roc_auc_score(vet["y"], vet["p_final"])), 4), "n_vet": int(len(vet)),
    "green_auc": round(float(roc_auc_score(green["y"], green["p_final"])), 4), "n_green": int(len(green)),
    "gap": round(float(roc_auc_score(vet["y"], vet["p_final"]) - roc_auc_score(green["y"], green["p_final"])), 4),
    "gap_ci95": [round(float(np.percentile(gaps, 2.5)), 4), round(float(np.percentile(gaps, 97.5)), 4)],
}
experience_auc["significant"] = experience_auc["gap_ci95"][0] > 0
print(f"\nAUC veterans {experience_auc['veteran_auc']} vs green {experience_auc['green_auc']}, "
      f"gap {experience_auc['gap']} CI {experience_auc['gap_ci95']} "
      f"{'SIGNIFICANT' if experience_auc['significant'] else '(crosses zero)'}")

out = {
    "key": "model_eval2",
    "calibrator_audit": calibrator_audit,
    "permutation_importance": perm[:30],
    "permutation_meta": {"n_repeats": N_REPEATS, "n_features": len(feats),
                         "base_logloss": round(float(base_ll), 5),
                         "note": "each feature shuffled in the held-out test set, all four "
                                 "streams re-scored, ensemble + calibrator reapplied"},
    "xgb_gain_top": [{"feature": k, "gain": round(float(v), 3)}
                     for k, v in list(gain.items())[:20]] if gain else None,
    "shap": shap_summary,
    "card_binomial": card_check,
    "experience_auc": experience_auc,
}
with open(f"{OUT}/model_eval2.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nWROTE model_eval2.json")
