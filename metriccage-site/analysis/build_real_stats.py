"""
build_real_stats.py — regenerate ../data/real-stats.js.

Keeps every key the existing renderers depend on, and adds the corrected series:
rates (the denominator pass), coverage, bodies_v2 (clustered inference), and the
full model-evaluation bundle. Nothing here is hand-edited; if a number changes,
it changes because the analysis changed.
"""

import json
import os
import re

OUT = os.environ.get("MC_OUT", "/home/claude/mc-analysis")
SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(SITE, "data", "real-stats.js")

# ---- keep the existing object as the base so nothing that renders today breaks
src = open(DEST).read()
base = json.loads(src[src.index("{"): src.rindex("};") + 1])
print("existing keys:", list(base.keys()))

rates = json.load(open(f"{OUT}/rates.json"))
bodies2 = json.load(open(f"{OUT}/bodies_v2.json"))
ev1 = json.load(open(f"{OUT}/model_eval.json"))
ev2 = json.load(open(f"{OUT}/model_eval2.json"))

ERAS = ["1994-1999", "2000-2004", "2005-2009", "2010-2014", "2015-2019", "2020-2026"]

# ---------------------------------------------------------------- rates block
by_era = rates["by_era_rate"]
base["rates"] = {
    "eras": ERAS,
    "position": {
        "share": {k: [by_era[e][k + "_share"] for e in ERAS] for k in ("distance", "clinch", "ground")},
        "rate": {k: [by_era[e][k + "_per_min"] for e in ERAS] for k in ("distance", "clinch", "ground")},
        "delta": rates["position_delta"],
    },
    "target": {
        "share": {k: [by_era[e][k + "_share"] for e in ERAS] for k in ("head", "body", "leg")},
        "rate": {k: [by_era[e][k + "_per_min"] for e in ERAS] for k in ("head", "body", "leg")},
    },
    "td": rates["td_series"],
    "sub": rates["sub_series"],
    "sub_peak_era": rates["sub_peak_era"],
    "control_by_method": rates["control_by_method"],
    "control_gap": rates["control_gap"],
    "sub_finish_clock": rates["sub_finish_clock"],
    "n_fights": [by_era[e]["n_fights"] for e in ERAS],
    "fight_minutes": [by_era[e]["fight_minutes"] for e in ERAS],
    "mean_duration": [by_era[e]["mean_duration_min"] for e in ERAS],
    "sig_per_min": [by_era[e]["sig_total_per_min"] for e in ERAS],
    "leg_by_year": rates["leg_by_year"],
    "leg_by_era": rates["leg_by_era"],
    "cells": rates["era_cells"],
    "corpus": rates["corpus"],
}
base["coverage"] = rates["coverage_by_year"]

# ---------------------------------------------------------------- bodies v2
base["bodies2"] = {
    "univariate": bodies2["univariate_forest"],
    "adjusted": bodies2["adjusted_forest"],
    "model": {k: v for k, v in bodies2["adjusted_model"].items() if k != "within_class_sd"},
    "by_weightclass": bodies2["reach_by_weightclass"],
    "coverage": bodies2["coverage"],
    "collisions": bodies2["name_collisions"],
    "ctrl_bug": bodies2["control_min_count_bug"],
    "reach_control": bodies2["reach_control_within_fight"],
    "reach_control_pooled": bodies2["reach_control_pooled_career"],
}

# ---------------------------------------------------------------- model
base["model"] = {
    "provenance": ev1["provenance"],
    "headline": ev1["headline"],
    "murphy": ev1["murphy_quantile"],
    "reliability": ev1["reliability_quantile"],
    "reliability_equalwidth": ev1["reliability_equalwidth"],
    "ece": ev1["ece"],
    "sharpness": ev1["sharpness"],
    "ladder": ev1["ladder"],
    "ablation": ev1["ablation"],
    "experience": ev1["experience"],
    "experience_auc": ev2["experience_auc"],
    "brier_by_year": ev1["brier_by_year"],
    "base_rate": ev1["base_rate_test"],
    "calibrator": ev2["calibrator_audit"],
    "permutation": ev2["permutation_importance"][:18],
    "permutation_meta": ev2["permutation_meta"],
    "gain_vs_perm": ev2["gain_vs_permutation"],
    "card": ev2["card_binomial"],
}
if ev2.get("shap"):
    s = ev2["shap"]
    base["model"]["shap"] = {
        "stream": s["stream"], "n_test": s["n_test"],
        "features": [{"feature": f["feature"], "mean_abs_shap": f["mean_abs_shap"],
                      "points": f["points"][:180]} for f in s["features"][:12]],
    }

header = ("/* GENERATED — do not hand-edit numbers.\n"
          "   Sources: analysis/rates.json, bodies_v2.json, model_eval.json, model_eval2.json\n"
          "   Regenerate: python analysis/build_real_stats.py  (see analysis/README.md)\n"
          f"   Snapshot: {rates['snapshot_end']} · {rates['corpus']['n_fights']} fights ·"
          f" {rates['corpus']['n_stat_rows']} fighter-round rows */\n")
with open(DEST, "w") as f:
    f.write(header + "const REAL = " + json.dumps(base, indent=1) + ";\n")

size = os.path.getsize(DEST)
print(f"wrote {DEST} ({size/1024:.0f} KB)")
print("keys now:", list(base.keys()))
