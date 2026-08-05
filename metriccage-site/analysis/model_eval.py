"""
model_eval.py — turn the model page's central claim into an identity.

The site asserts "excellent calibration, mediocre discrimination" and then shows
neither the sharpness distribution nor a baseline. Both of those are one chart
each, and the Murphy decomposition of the Brier score computes the two halves of
that sentence AS SEPARATE NUMBERS:

    Brier = Reliability - Resolution + Uncertainty

Reliability is calibration error (lower is better, 0 is perfect). Resolution is
discrimination (higher is better). Uncertainty is the irreducible base-rate term
you cannot beat. Writing the three out is the argument.

Everything here runs on streams_test.parquet, produced by score_streams.py, which
re-scores the SHIPPED 4-stream bundle and reproduces the bundle's own published
test metrics to 1e-16. Nothing below is a placeholder.

Output: model_eval.json
"""

import json
import os

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from scipy.optimize import minimize

OUT = os.environ.get("MC_OUT", "/home/claude/mc-analysis")
EPS = 1e-6
rng = np.random.default_rng(20260802)

test = pd.read_parquet(f"{OUT}/streams_test.parquet")
val = pd.read_parquet(f"{OUT}/streams_val.parquet")
train = pd.read_parquet(f"{OUT}/streams_train.parquet")
y = test["y"].to_numpy().astype(int)
p = test["p_final"].to_numpy()
N = len(test)
print(f"test n={N}, base rate={y.mean():.4f}")


# ============================================================ Murphy / CAL-REF
def murphy(y_true, y_prob, n_bins=10, strategy="quantile"):
    """Brier = Reliability - Resolution + Uncertainty, computed on binned forecasts.

    Binning matters: too few bins hides miscalibration, too many manufactures it.
    Quantile bins keep every bin populated, which equal-width bins do not when
    the forecasts are bunched (and at AUC 0.67 they must be)."""
    y_true = np.asarray(y_true, float)
    y_prob = np.asarray(y_prob, float)
    n = len(y_true)
    obar = y_true.mean()
    if strategy == "quantile":
        edges = np.unique(np.quantile(y_prob, np.linspace(0, 1, n_bins + 1)))
    else:
        edges = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(y_prob, edges[1:-1]), 0, len(edges) - 2)
    rel = res = 0.0
    bins = []
    for b in range(len(edges) - 1):
        m = idx == b
        nk = int(m.sum())
        if nk == 0:
            continue
        fk = y_prob[m].mean()
        ok = y_true[m].mean()
        rel += nk * (fk - ok) ** 2
        res += nk * (ok - obar) ** 2
        bins.append({"bin": b, "n": nk, "mean_pred": round(float(fk), 4),
                     "observed": round(float(ok), 4),
                     "lo": round(float(edges[b]), 4), "hi": round(float(edges[b + 1]), 4)})
    rel, res = rel / n, res / n
    unc = obar * (1 - obar)
    return {
        "reliability": round(float(rel), 5),
        "resolution": round(float(res), 5),
        "uncertainty": round(float(unc), 5),
        "brier_from_decomposition": round(float(rel - res + unc), 5),
        "brier_direct": round(float(brier_score_loss(y_true, y_prob)), 5),
        "skill_score": round(float(1 - brier_score_loss(y_true, y_prob) / unc), 5),
        "n_bins_used": len(bins), "strategy": strategy, "bins": bins,
    }


murphy_q = murphy(y, p, 10, "quantile")
murphy_w = murphy(y, p, 10, "uniform")
print("\nMurphy (quantile bins): Brier %.5f = rel %.5f - res %.5f + unc %.5f"
      % (murphy_q["brier_from_decomposition"], murphy_q["reliability"],
         murphy_q["resolution"], murphy_q["uncertainty"]))
print(f"  direct Brier {murphy_q['brier_direct']:.5f}  |  Brier skill score {murphy_q['skill_score']:+.4f}")


# ============================================================ Wilson intervals
def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    ph = k / n
    d = 1 + z * z / n
    c = ph + z * z / (2 * n)
    h = z * np.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))
    return [round(float((c - h) / d), 4), round(float((c + h) / d), 4)]


def reliability(y_true, y_prob, n_bins=10, strategy="quantile"):
    if strategy == "quantile":
        edges = np.unique(np.quantile(y_prob, np.linspace(0, 1, n_bins + 1)))
    else:
        edges = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(y_prob, edges[1:-1]), 0, len(edges) - 2)
    rows = []
    for b in range(len(edges) - 1):
        m = idx == b
        nk = int(m.sum())
        if nk == 0:
            continue
        k = int(y_true[m].sum())
        rows.append({
            "predicted": round(float(y_prob[m].mean()), 4),
            "observed": round(float(k / nk), 4),
            "n": nk, "wilson95": wilson(k, nk),
            "edge_lo": round(float(edges[b]), 4), "edge_hi": round(float(edges[b + 1]), 4),
        })
    return rows


def ece(y_true, y_prob, n_bins=10, strategy="quantile"):
    rows = reliability(y_true, y_prob, n_bins, strategy)
    n = len(y_true)
    return round(float(sum(r["n"] / n * abs(r["observed"] - r["predicted"]) for r in rows)), 5)


rel_quant = reliability(y, p, 10, "quantile")
rel_equal = reliability(y, p, 10, "uniform")
ece_q, ece_w = ece(y, p, 10, "quantile"), ece(y, p, 10, "uniform")
print(f"\nECE (quantile bins) {ece_q:.5f} | ECE (equal-width, the legacy definition) {ece_w:.5f}")
# how many bins sit inside their own Wilson interval?
inside = sum(1 for r in rel_quant if r["wilson95"][0] <= r["predicted"] <= r["wilson95"][1])
print(f"bins whose Wilson interval covers the predicted value: {inside}/{len(rel_quant)}")


# ============================================================ sharpness
hist_edges = np.linspace(0, 1, 21)
counts, _ = np.histogram(p, bins=hist_edges)
sharpness = {
    "edges": [round(float(x), 3) for x in hist_edges],
    "counts": [int(c) for c in counts],
    "sd": round(float(p.std()), 4),
    "iqr": [round(float(np.percentile(p, 25)), 4), round(float(np.percentile(p, 75)), 4)],
    "pct_within_10pts_of_half": round(float((np.abs(p - 0.5) <= 0.10).mean()), 4),
    "pct_outside_30_70": round(float(((p < 0.30) | (p > 0.70)).mean()), 4),
    "min": round(float(p.min()), 4), "max": round(float(p.max()), 4),
    "note": "a model that cannot discriminate has no choice but to bunch near the base rate",
}
print(f"\nsharpness: sd={sharpness['sd']:.4f}, {sharpness['pct_within_10pts_of_half']*100:.1f}% of "
      f"forecasts within 10pts of 0.50, range [{sharpness['min']:.3f},{sharpness['max']:.3f}]")


# ============================================================ bootstrap CIs
def boot_metric(fn, n_boot=4000):
    vals = []
    for _ in range(n_boot):
        i = rng.integers(0, N, N)
        if y[i].sum() in (0, N):
            continue
        try:
            vals.append(fn(y[i], p[i]))
        except ValueError:
            pass
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]


TARGETS = {"auc": 0.740, "brier": 0.225, "logloss": None, "accuracy": None, "ece": 0.030}
headline = {}
for name, fn, point in [
    ("auc", roc_auc_score, roc_auc_score(y, p)),
    ("brier", brier_score_loss, brier_score_loss(y, p)),
    ("logloss", log_loss, log_loss(y, p)),
    ("accuracy", lambda a, b: float(((b > 0.5).astype(int) == a).mean()), float(((p > 0.5).astype(int) == y).mean())),
    ("ece", lambda a, b: ece(a, b, 10, "quantile"), ece_q),
]:
    ci = boot_metric(fn)
    tgt = TARGETS.get(name)
    headline[name] = {
        "point": round(float(point), 4), "ci95": ci, "n": N,
        "target": tgt,
        "target_inside_ci": (ci[0] <= tgt <= ci[1]) if tgt is not None else None,
    }
    t = f"  target {tgt} {'INSIDE' if headline[name]['target_inside_ci'] else 'OUTSIDE'} the interval" if tgt else ""
    print(f"  {name:9s} {point:.4f}  95% [{ci[0]:.4f},{ci[1]:.4f}]{t}")


# ============================================================ baseline ladder
def fit_blend(stream_cols, dfv):
    """Refit convex weights on VALIDATION by log-loss (the repo's own recipe,
    including its 0.05 shrink-to-uniform), then refit isotonic on validation."""
    P = dfv[stream_cols].to_numpy(float)
    yv = dfv["y"].to_numpy(float)
    k = len(stream_cols)
    uni = np.full(k, 1 / k)

    def nll(w):
        q = np.clip(P @ w, EPS, 1 - EPS)
        return log_loss(yv, q, labels=[0, 1]) + 0.05 * float(((w - uni) ** 2).sum())

    r = minimize(nll, uni, method="SLSQP", bounds=[(0, 1)] * k,
                 constraints=({"type": "eq", "fun": lambda w: w.sum() - 1},),
                 options={"maxiter": 500, "ftol": 1e-9})
    w = np.clip(r.x if r.success else uni, 0, None)
    w = w / w.sum()
    blend_v = np.clip(P @ w, EPS, 1 - EPS)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(blend_v, yv)
    return w, iso


def apply_blend(stream_cols, w, iso, dft):
    b = np.clip(dft[stream_cols].to_numpy(float) @ w, EPS, 1 - EPS)
    return np.clip(iso.predict(b), EPS, 1 - EPS)


STREAMS = ["logreg", "xgb", "elo", "lstm"]
ladder = []


def add_rung(label, probs, note="", kind="baseline"):
    probs = np.clip(np.asarray(probs, float), EPS, 1 - EPS)
    ladder.append({
        "label": label, "kind": kind, "note": note,
        "logloss": round(float(log_loss(y, probs)), 4),
        "brier": round(float(brier_score_loss(y, probs)), 4),
        "auc": round(float(roc_auc_score(y, probs)), 4) if len(np.unique(probs)) > 1 else None,
        "accuracy": round(float(((probs > 0.5).astype(int) == y).mean()), 4),
    })


add_rung("Always 0.50", np.full(N, 0.5), "a coin, and the number every model must beat")
add_rung("Train base rate", np.full(N, float(train["y"].mean())),
         f"predict {train['y'].mean():.3f} every time — the corner-A prior")
for s in STREAMS:
    w1, iso1 = fit_blend([s], val)
    add_rung(f"{s} alone", apply_blend([s], w1, iso1, test),
             "single stream, isotonic-calibrated on 2023", kind="stream")
add_rung("Ensemble (shipped)", p, "4 streams, weights + isotonic fitted on 2023", kind="shipped")
print("\nbaseline ladder:")
for r in ladder:
    print(f"  {r['label']:22s} ll {r['logloss']:.4f}  brier {r['brier']:.4f}  "
          f"auc {r['auc'] if r['auc'] else float('nan'):.4f}  acc {r['accuracy']:.4f}")


# ============================================================ LOO ablation
ablation = []
base_ll, base_br = log_loss(y, p), brier_score_loss(y, p)
for drop in STREAMS:
    keep = [s for s in STREAMS if s != drop]
    w2, iso2 = fit_blend(keep, val)
    q = apply_blend(keep, w2, iso2, test)
    ablation.append({
        "dropped": drop,
        "shipped_weight": None,
        "kept": keep,
        "refit_weights": {k: round(float(v), 4) for k, v in zip(keep, w2)},
        "logloss": round(float(log_loss(y, q)), 5),
        "delta_logloss": round(float(log_loss(y, q) - base_ll), 5),
        "brier": round(float(brier_score_loss(y, q)), 5),
        "delta_brier": round(float(brier_score_loss(y, q) - base_br), 5),
        "auc": round(float(roc_auc_score(y, q)), 4),
    })
import pickle  # noqa: E402

_b = pickle.load(open(os.environ.get("UFC_REPO", ".") + "/data/processed/final_model_bundle.pkl", "rb"))
for a in ablation:
    a["shipped_weight"] = round(float(_b["weights"][a["dropped"]]), 4)
ablation.sort(key=lambda a: -a["delta_logloss"])
print("\nleave-one-out ablation (positive delta = the ensemble got WORSE without it):")
for a in ablation:
    print(f"  drop {a['dropped']:7s} (weight {a['shipped_weight']:.3f})  "
          f"logloss {a['logloss']:.5f}  d={a['delta_logloss']:+.5f}  d_brier={a['delta_brier']:+.5f}")


# ============================================================ experience split
test["min_fights"] = test[["n_fights_a", "n_fights_b"]].min(axis=1)
test["max_fights"] = test[["n_fights_a", "n_fights_b"]].max(axis=1)
exp_groups = {
    "veterans_both_5plus": test[test["min_fights"] >= 5],
    "mixed": test[(test["min_fights"] >= 3) & (test["min_fights"] < 5)],
    "green_either_under3": test[test["min_fights"] < 3],
}
experience = {}
for k, g in exp_groups.items():
    if len(g) < 30:
        experience[k] = {"n": int(len(g)), "note": "too few fights to report"}
        continue
    gy, gp = g["y"].to_numpy().astype(int), g["p_final"].to_numpy()
    experience[k] = {
        "n": int(len(g)),
        "ece": ece(gy, gp, 5, "quantile"),
        "brier": round(float(brier_score_loss(gy, gp)), 4),
        "logloss": round(float(log_loss(gy, gp, labels=[0, 1])), 4),
        "auc": round(float(roc_auc_score(gy, gp)), 4) if len(np.unique(gy)) > 1 else None,
        "accuracy": round(float(((gp > 0.5).astype(int) == gy).mean()), 4),
        "mean_pred": round(float(gp.mean()), 4), "base_rate": round(float(gy.mean()), 4),
        "reliability_bins": reliability(gy, gp, 5, "quantile"),
        "murphy": {kk: vv for kk, vv in murphy(gy, gp, 5, "quantile").items() if kk != "bins"},
    }
print("\ncalibration by experience:")
for k, v in experience.items():
    if "ece" in v:
        print(f"  {k:22s} n={v['n']:4d}  ECE {v['ece']:.4f}  brier {v['brier']:.4f}  auc {v['auc']}")
    else:
        print(f"  {k:22s} n={v['n']:4d}  {v['note']}")

# bootstrap the ECE gap between veterans and green fights
gv, gg = exp_groups["veterans_both_5plus"], exp_groups["green_either_under3"]
if len(gv) >= 30 and len(gg) >= 30:
    dif = []
    for _ in range(2000):
        a = gv.sample(len(gv), replace=True, random_state=int(rng.integers(1e9)))
        b = gg.sample(len(gg), replace=True, random_state=int(rng.integers(1e9)))
        dif.append(ece(b["y"].to_numpy().astype(int), b["p_final"].to_numpy(), 5, "quantile")
                   - ece(a["y"].to_numpy().astype(int), a["p_final"].to_numpy(), 5, "quantile"))
    experience["ece_gap_green_minus_vet"] = {
        "point": round(float(ece(gg["y"].to_numpy().astype(int), gg["p_final"].to_numpy(), 5, "quantile")
                              - ece(gv["y"].to_numpy().astype(int), gv["p_final"].to_numpy(), 5, "quantile")), 4),
        "ci95": [round(float(np.percentile(dif, 2.5)), 4), round(float(np.percentile(dif, 97.5)), 4)],
    }
    print(f"  ECE gap (green - veteran) {experience['ece_gap_green_minus_vet']['point']:+.4f} "
          f"CI {experience['ece_gap_green_minus_vet']['ci95']}")


# ============================================================ Brier by year
test["year"] = pd.to_datetime(test["event_date"]).dt.year
by_year = []
for src_df, split_name in ((train, "train"), (val, "val"), (test, "test")):
    d = src_df.copy()
    d["year"] = pd.to_datetime(d["event_date"]).dt.year
    for yr, g in d.groupby("year"):
        if len(g) < 40:
            continue
        gy, gp = g["y"].to_numpy().astype(int), g["p_final"].to_numpy()
        k = int(gy.sum())
        by_year.append({
            "year": int(yr), "split": split_name, "n": int(len(g)),
            "brier": round(float(brier_score_loss(gy, gp)), 4),
            "logloss": round(float(log_loss(gy, gp, labels=[0, 1])), 4),
            "brier_ci95": [round(float(x), 4) for x in np.percentile(
                [brier_score_loss(gy[i], gp[i]) for i in
                 (rng.integers(0, len(g), len(g)) for _ in range(800))], [2.5, 97.5])],
            "base_rate": round(float(gy.mean()), 4), "k_wins": k,
        })
by_year.sort(key=lambda r: r["year"])
print("\nBrier by year (in-sample years flagged honestly):")
for r in by_year:
    print(f"  {r['year']}  {r['split']:5s}  n={r['n']:4d}  brier {r['brier']:.4f} {r['brier_ci95']}")

out = {
    "key": "model_eval",
    "provenance": {
        "bundle": "final_model_bundle.pkl (4-stream, phase update2_optuna_tuned)",
        "split": "train 2005-01-01..2022-12-31 | val 2023 | test 2024-01-01..2025-05-04",
        "n_train": int(len(train)), "n_val": int(len(val)), "n_test": N,
        "reproduces_published_test_metrics": True,
        "max_abs_delta_vs_bundle_best_config": 2.2e-16,
    },
    "headline": headline,
    "murphy_quantile": murphy_q,
    "murphy_equalwidth": {k: v for k, v in murphy_w.items() if k != "bins"},
    "reliability_quantile": rel_quant,
    "reliability_equalwidth": rel_equal,
    "ece": {"quantile_10": ece_q, "equalwidth_10": ece_w,
            "bins_covering_prediction": inside, "n_bins": len(rel_quant)},
    "sharpness": sharpness,
    "ladder": ladder,
    "ablation": ablation,
    "experience": experience,
    "brier_by_year": by_year,
    "base_rate_test": round(float(y.mean()), 4),
}
os.makedirs(OUT, exist_ok=True)
with open(f"{OUT}/model_eval.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nWROTE model_eval.json")
