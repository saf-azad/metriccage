"""
bodies_v2.py — the inference pass.

Supersedes bodies_analyze.py for everything the forest plot and the reach/control
null are built on. Three things changed, and each changes a published number:

  1. CONTROL TIME IS NO LONGER SILENTLY ZERO.
     bodies_analyze.py:239 does groupby(...).agg(CTRL_SEC=('CTRL_SEC','sum')).
     pandas returns 0.0 for an all-NaN group, so every fight before the CTRL field
     existed entered as "zero seconds of control" — the exact opposite of the
     methods section's stated guarantee. Everything here uses sum(min_count=1).

  2. INTERVALS ARE CLUSTERED ON FIGHTERS, NOT FIGHTS.
     sqrt(p(1-p)/n) with n = fights treats a 20-fight career as 20 independent
     observations. It isn't. Every interval below is a fighter-level cluster
     bootstrap, which is what the dependence structure actually is.

  3. EFFECTS ARE PER STANDARD DEVIATION, WITHIN WEIGHT CLASS.
     "7 years beats 5 inches" is a statement about bin edges, not about fighting.
     Each attribute differential is standardised inside its own weight class, then
     all of them go into one logistic regression, so the forest plot is finally
     plotting what a forest plot claims to plot: adjusted, comparable estimates.

Input : a clone of https://github.com/Greco1899/scrape_ufc_stats
Output: bodies_v2.json
"""

import json
import os
import re

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

DATA = os.environ.get("UFC_DATA", "/home/claude/ufc-data")
OUT = os.environ.get("MC_OUT", "/home/claude/mc-analysis")
SNAPSHOT_END = pd.Timestamp("2026-08-01")
N_BOOT = int(os.environ.get("MC_NBOOT", "2000"))
SEED = 20260802

rng = np.random.default_rng(SEED)

# ---------------------------------------------------------------- load
events = pd.read_csv(f"{DATA}/ufc_event_details.csv")
results = pd.read_csv(f"{DATA}/ufc_fight_results.csv")
stats = pd.read_csv(f"{DATA}/ufc_fighter_tott.csv")
tott = stats
fstats = pd.read_csv(f"{DATA}/ufc_fight_stats.csv")

for df in (events, results, tott, fstats):
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype) in ("str", "string"):
            df[c] = df[c].astype("string").str.strip()
            df.loc[df[c].isin(["nan", "None", "--"]), c] = pd.NA


def parse_height(h):
    if pd.isna(h):
        return np.nan
    m = re.match(r"(\d+)'\s*(\d+)", str(h))
    return int(m.group(1)) * 12 + int(m.group(2)) if m else np.nan


def parse_reach(r):
    if pd.isna(r):
        return np.nan
    m = re.match(r'(\d+(\.\d+)?)"?', str(r))
    return float(m.group(1)) if m else np.nan


tott["HEIGHT_IN"] = tott["HEIGHT"].map(parse_height)
tott["REACH_IN"] = tott["REACH"].map(parse_reach)
tott["DOB_DT"] = pd.to_datetime(tott["DOB"], format="%b %d, %Y", errors="coerce")

# --- the duplicate-name problem, surfaced instead of silently resolved
dup_names = tott["FIGHTER"][tott["FIGHTER"].duplicated(keep=False)].dropna().unique().tolist()
dup_conflicting = []
for nm in dup_names:
    g = tott[tott["FIGHTER"] == nm]
    if g[["HEIGHT_IN", "REACH_IN", "DOB_DT"]].drop_duplicates().shape[0] > 1:
        dup_conflicting.append(nm)
name_collisions = {
    "n_duplicate_name_rows": int(tott["FIGHTER"].duplicated().sum()),
    "n_duplicate_names": len(dup_names),
    "n_names_with_conflicting_bodies": len(dup_conflicting),
    "examples": sorted(dup_conflicting)[:12],
}
print("name collisions:", {k: v for k, v in name_collisions.items() if k != "examples"})

tott_d = tott.drop_duplicates(subset="FIGHTER", keep="first").set_index("FIGHTER")

events["DATE_DT"] = pd.to_datetime(events["DATE"], format="%B %d, %Y", errors="coerce")
ev = events[["EVENT", "DATE_DT"]].dropna().drop_duplicates(subset="EVENT")

res = results[results["EVENT"].notna() & results["BOUT"].notna()].copy()
sp = res["BOUT"].str.split(" vs. ", n=1, expand=True)
res["F1"], res["F2"] = sp[0].str.strip(), sp[1].str.strip()
res = res[res["F2"].notna() & res["OUTCOME"].isin(["W/L", "L/W"])]
res["WINNER"] = np.where(res["OUTCOME"] == "W/L", res["F1"], res["F2"])
res["LOSER"] = np.where(res["OUTCOME"] == "W/L", res["F2"], res["F1"])
res = res.merge(ev, on="EVENT", how="left")
res = res[res["DATE_DT"].notna() & (res["DATE_DT"] <= SNAPSHOT_END)]
res["FIGHT_ID"] = res["EVENT"] + " || " + res["BOUT"]
n_decided = len(res)
print("decided fights:", n_decided)

STANDARD_WC = ["Women's Strawweight", "Women's Flyweight", "Women's Bantamweight",
               "Women's Featherweight", "Flyweight", "Bantamweight", "Featherweight",
               "Lightweight", "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight"]


def norm_wc(x):
    if pd.isna(x):
        return None
    x = str(x).replace(" Bout", "").replace(" Title", "").strip()
    if "Catch" in x or x == "Ultimate Fighter":
        return None
    for wc in STANDARD_WC:
        if wc.lower() in x.lower():
            return wc
    return None


res["WC"] = res["WEIGHTCLASS"].map(norm_wc)

# ------------------------------------------------ fighter-side panel (2 rows/fight)
rows = []
for side_win in (True, False):
    me = "WINNER" if side_win else "LOSER"
    opp = "LOSER" if side_win else "WINNER"
    d = pd.DataFrame({
        "FIGHT_ID": res["FIGHT_ID"].values,
        "fighter": res[me].values,
        "opponent": res[opp].values,
        "won": side_win,
        "date": res["DATE_DT"].values,
        "wc": res["WC"].values,
    })
    rows.append(d)
panel = pd.concat(rows, ignore_index=True)

attrs = tott_d[["HEIGHT_IN", "REACH_IN", "DOB_DT", "STANCE"]]
panel = panel.join(attrs.rename(columns=lambda c: "me_" + c), on="fighter")
panel = panel.join(attrs.rename(columns=lambda c: "op_" + c), on="opponent")
panel["me_age"] = (panel["date"] - panel["me_DOB_DT"]).dt.days / 365.25
panel["op_age"] = (panel["date"] - panel["op_DOB_DT"]).dt.days / 365.25
panel["reach_diff"] = panel["me_REACH_IN"] - panel["op_REACH_IN"]
panel["height_diff"] = panel["me_HEIGHT_IN"] - panel["op_HEIGHT_IN"]
panel["age_diff"] = panel["me_age"] - panel["op_age"]          # positive = older
panel["youth_diff"] = -panel["age_diff"]                        # positive = younger
panel["sp_vs_orth"] = (panel["me_STANCE"] == "Southpaw") & (panel["op_STANCE"] == "Orthodox")
panel["orth_vs_sp"] = (panel["me_STANCE"] == "Orthodox") & (panel["op_STANCE"] == "Southpaw")

# ------------------------------------------------ COVERAGE, per analysis
# "name found in the tale-of-the-tape table" is not "attribute present". Report both.
name_found = panel["fighter"].isin(tott_d.index)
coverage = {
    "n_decided_fights": int(n_decided),
    "join_rate_name_found": round(float(name_found.mean()), 4),
    "per_attribute": {},
}
for label, col in [("reach", "reach_diff"), ("height", "height_diff"),
                   ("age", "age_diff"), ("stance", "me_STANCE")]:
    ok = panel[col].notna()
    fights_ok = panel.loc[ok].groupby("FIGHT_ID").size().eq(2).sum() if label != "stance" else \
        panel.loc[panel["me_STANCE"].notna() & panel["op_STANCE"].notna()].groupby("FIGHT_ID").size().eq(2).sum()
    coverage["per_attribute"][label] = {
        "fighter_sides_with_value": int(ok.sum()),
        "fighter_sides_pct": round(100 * float(ok.mean()), 2),
        "fights_with_both_sides": int(fights_ok),
        "fights_pct_of_decided": round(100 * float(fights_ok) / n_decided, 2),
    }
    print(f"coverage {label:7s}: {coverage['per_attribute'][label]['fights_pct_of_decided']:.1f}% of decided fights")

# is the missingness random? compare era + weight class of covered vs not
panel["year"] = pd.to_datetime(panel["date"]).dt.year
miss = panel[panel["reach_diff"].isna()]
have = panel[panel["reach_diff"].notna()]
coverage["reach_missingness"] = {
    "mean_year_missing": round(float(miss["year"].mean()), 1),
    "mean_year_present": round(float(have["year"].mean()), 1),
    "pct_missing_pre2010": round(100 * float((miss["year"] < 2010).mean()), 1),
    "pct_present_pre2010": round(100 * float((have["year"] < 2010).mean()), 1),
    "note": "attrition is not random: it concentrates in the early corpus",
}
print("reach missingness:", coverage["reach_missingness"])


# ------------------------------------------------ fighter-level cluster bootstrap
def cluster_boot(df, stat_fn, n_boot=N_BOOT, seed=SEED):
    """Resample FIGHTERS with replacement (that is the dependence unit), take all of
    each drawn fighter's rows, recompute. Returns (point, lo, hi, n_rows, n_fighters)."""
    point = stat_fn(df)
    fighters = df["fighter"].dropna().unique()
    groups = {f: idx.to_numpy() for f, idx in df.groupby("fighter").groups.items()}
    r = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        drawn = r.choice(fighters, fighters.size, replace=True)
        idx = np.concatenate([groups[f] for f in drawn])
        v = stat_fn(df.loc[idx])
        if v is not None and np.isfinite(v):
            vals.append(v)
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return (round(float(point), 4), round(float(lo), 4), round(float(hi), 4),
            int(len(df)), int(fighters.size))


def naive_ci(p, n):
    se = np.sqrt(p * (1 - p) / n)
    return [round(max(0.0, p - 1.96 * se), 4), round(min(1.0, p + 1.96 * se), 4)]


def winrate(df):
    return float(df["won"].mean()) if len(df) else None


forest = {}


def add_forest(key, subset, label):
    if not len(subset):
        return
    pt, lo, hi, n, nf = cluster_boot(subset, winrate)
    nlo, nhi = naive_ci(pt, n)
    forest[key] = {
        "label": label, "win": pt,
        "ci_clustered": [lo, hi], "ci_naive_iid": [nlo, nhi],
        "width_clustered": round(hi - lo, 4), "width_naive": round(nhi - nlo, 4),
        "inflation": round((hi - lo) / (nhi - nlo), 2) if nhi > nlo else None,
        "n_fighter_sides": n, "n_fighters": nf,
    }
    print(f"  {label:26s} {pt:.3f}  clustered [{lo:.3f},{hi:.3f}]  iid [{nlo:.3f},{nhi:.3f}]  "
          f"x{forest[key]['inflation']}")


print("\nunivariate win rates, clustered vs naive intervals:")
add_forest("reach", panel[panel["reach_diff"] > 0], "Longer reach")
add_forest("height", panel[panel["height_diff"] > 0], "Taller")
add_forest("southpaw", panel[panel["sp_vs_orth"]], "Southpaw vs orthodox")
add_forest("younger", panel[panel["youth_diff"] > 0], "Younger")
add_forest("reach5", panel[panel["reach_diff"] >= 5], "Reach +5in or more")
add_forest("age7", panel[panel["youth_diff"] >= 7], "Younger by 7y or more")

# ------------------------------------------------ within-weight-class standardisation
model_cols = ["reach_diff", "height_diff", "youth_diff"]
mp = panel.dropna(subset=model_cols + ["wc"]).copy()
mp["sp_edge"] = mp["sp_vs_orth"].astype(float) - mp["orth_vs_sp"].astype(float)  # antisymmetric

sds = {}
for c in model_cols:
    s = mp.groupby("wc")[c].transform("std")
    sds[c] = {wc: round(float(v), 3) for wc, v in mp.groupby("wc")[c].std().items()}
    mp[c + "_z"] = mp[c] / s

zcols = [c + "_z" for c in model_cols] + ["sp_edge"]
mp = mp.dropna(subset=zcols)
X = mp[zcols].to_numpy()
y = mp["won"].astype(int).to_numpy()

# no intercept: the design is antisymmetric by construction (every fight appears in
# both orientations), so a constant would be meaningless and a weight-class dummy
# would be identically zero. Standardising WITHIN class is the class adjustment.
clf = LogisticRegression(fit_intercept=False, C=1e6, max_iter=2000)
clf.fit(X, y)
coefs = dict(zip(zcols, clf.coef_[0]))
print("\nadjusted per-SD log-odds (within weight class):")
for k, v in coefs.items():
    print(f"  {k:14s} {v:+.4f}   (odds x{np.exp(v):.3f})")

# cluster bootstrap the coefficients
groups_m = {f: idx.to_numpy() for f, idx in mp.groupby("fighter").groups.items()}
fighters_m = mp["fighter"].dropna().unique()
rb = np.random.default_rng(SEED + 1)
boot_coefs = []
N_BOOT_MODEL = max(400, N_BOOT // 4)
for _ in range(N_BOOT_MODEL):
    drawn = rb.choice(fighters_m, fighters_m.size, replace=True)
    idx = np.concatenate([groups_m[f] for f in drawn])
    sub = mp.loc[idx]
    try:
        c2 = LogisticRegression(fit_intercept=False, C=1e6, max_iter=400)
        c2.fit(sub[zcols].to_numpy(), sub["won"].astype(int).to_numpy())
        boot_coefs.append(c2.coef_[0])
    except Exception:
        pass
boot_coefs = np.array(boot_coefs)

LABELS = {"reach_diff_z": "Reach (per within-class SD)",
          "height_diff_z": "Height (per within-class SD)",
          "youth_diff_z": "Youth (per within-class SD)",
          "sp_edge": "Southpaw edge"}
adjusted_forest = []
for i, c in enumerate(zcols):
    lo, hi = np.percentile(boot_coefs[:, i], [2.5, 97.5])
    adjusted_forest.append({
        "key": c, "label": LABELS[c],
        "coef": round(float(coefs[c]), 4),
        "ci95": [round(float(lo), 4), round(float(hi), 4)],
        "odds_ratio": round(float(np.exp(coefs[c])), 4),
        "or_ci95": [round(float(np.exp(lo)), 4), round(float(np.exp(hi)), 4)],
        # win prob for a fighter one SD ahead on this attribute alone
        "win_prob_1sd": round(float(1 / (1 + np.exp(-coefs[c]))), 4),
        "win_prob_ci95": [round(float(1 / (1 + np.exp(-lo))), 4), round(float(1 / (1 + np.exp(-hi))), 4)],
        "crosses_zero": bool(lo < 0 < hi),
    })
adjusted_forest.sort(key=lambda d: -abs(d["coef"]))
model_meta = {
    "n_fighter_sides": int(len(mp)),
    "n_fights": int(mp["FIGHT_ID"].nunique()),
    "n_fighters": int(fighters_m.size),
    "n_boot": int(len(boot_coefs)),
    "within_class_sd": sds,
    "design": "one row per fighter-side (both orientations), no intercept, "
              "differentials standardised within weight class",
}
print("\nadjusted forest (sorted):")
for d in adjusted_forest:
    print(f"  {d['label']:34s} {d['coef']:+.4f} [{d['ci95'][0]:+.4f},{d['ci95'][1]:+.4f}]"
          f"  {'(crosses 0)' if d['crosses_zero'] else ''}")

# ------------------------------------------------ reach effect BY weight class
by_wc_reach = {}
for wc, g in panel[panel["reach_diff"].notna() & panel["wc"].notna()].groupby("wc"):
    adv = g[g["reach_diff"] > 0]
    if len(adv) < 120:
        continue
    pt, lo, hi, n, nf = cluster_boot(adv, winrate, n_boot=600)
    by_wc_reach[wc] = {"win": pt, "ci95": [lo, hi], "n_fighter_sides": n, "n_fighters": nf,
                       "mean_abs_reach_gap": round(float(adv["reach_diff"].mean()), 2)}
print("\nreach advantage by weight class:")
for wc, v in sorted(by_wc_reach.items(), key=lambda kv: -kv[1]["win"]):
    print(f"  {wc:24s} {v['win']:.3f} [{v['ci95'][0]:.3f},{v['ci95'][1]:.3f}]  n={v['n_fighter_sides']}")

# ================================================================
# 1.8 — the reach/control null, done at fight level with power
# ================================================================
for c in fstats.columns:
    if fstats[c].dtype == object or str(fstats[c].dtype) in ("str", "string"):
        fstats[c] = fstats[c].astype("string").str.strip()


def parse_ctrl(v):
    if pd.isna(v):
        return np.nan
    v = str(v)
    if ":" not in v:
        return np.nan
    try:
        m, s = v.split(":")
        return int(m) * 60 + int(s)
    except ValueError:
        return np.nan


fstats["CTRL_SEC"] = fstats["CTRL"].map(parse_ctrl)
fstats["FIGHT_ID"] = fstats["EVENT"] + " || " + fstats["BOUT"]

# min_count=1 — an all-missing group stays missing. THIS IS THE BUG FIX.
pf = fstats.groupby(["FIGHT_ID", "FIGHTER"], as_index=False).agg(
    CTRL_SEC=("CTRL_SEC", lambda s: s.sum(min_count=1)),
    N_ROUNDS_TRACKED=("CTRL_SEC", "count"),
)
pf_buggy = fstats.groupby(["FIGHT_ID", "FIGHTER"], as_index=False).agg(CTRL_SEC=("CTRL_SEC", "sum"))
bug = {
    "rows_total": int(len(pf)),
    "rows_missing_correct": int(pf["CTRL_SEC"].isna().sum()),
    "rows_zero_under_buggy_sum": int(((pf_buggy["CTRL_SEC"] == 0) & pf["CTRL_SEC"].isna()).sum()),
    "mean_ctrl_correct": round(float(pf["CTRL_SEC"].mean()), 2),
    "mean_ctrl_buggy": round(float(pf_buggy["CTRL_SEC"].mean()), 2),
}
bug["bias_sec"] = round(bug["mean_ctrl_correct"] - bug["mean_ctrl_buggy"], 2)
print("\nmin_count bug:", bug)

# fight-level differential design, weight class held fixed by construction
elapsed = None
r2 = results.copy()
r2["FIGHT_ID"] = r2["EVENT"] + " || " + r2["BOUT"]


def round_lengths(fmt):
    if pd.isna(fmt):
        return None
    m = re.search(r"\(([\d\-]+)\)", str(fmt))
    return [int(x) for x in m.group(1).split("-") if x] if m else None


def mmss(t):
    m = re.match(r"^(\d+):(\d{1,2})$", str(t).strip()) if pd.notna(t) else None
    return int(m.group(1)) * 60 + int(m.group(2)) if m else np.nan


def elapsed_sec(row):
    rl, fin, rnd = round_lengths(row["TIME FORMAT"]), mmss(row["TIME"]), row["ROUND"]
    if pd.isna(fin) or pd.isna(rnd):
        return np.nan
    rnd = int(rnd)
    if rl is None:
        return float(fin) if rnd == 1 else np.nan
    return float(sum(rl[:rnd - 1]) * 60 + fin) if rnd <= len(rl) else np.nan


r2["ELAPSED_SEC"] = r2.apply(elapsed_sec, axis=1)
# a handful of FIGHT_IDs repeat in the source (same bout listed twice); keep the first
elapsed = r2.drop_duplicates(subset="FIGHT_ID", keep="first").set_index("FIGHT_ID")["ELAPSED_SEC"]

ctrl_panel = panel.merge(pf.rename(columns={"FIGHTER": "fighter"}), on=["FIGHT_ID", "fighter"], how="left")
ctrl_panel = ctrl_panel.merge(
    pf.rename(columns={"FIGHTER": "opponent", "CTRL_SEC": "OP_CTRL_SEC"})[["FIGHT_ID", "opponent", "OP_CTRL_SEC"]],
    on=["FIGHT_ID", "opponent"], how="left")
ctrl_panel["elapsed"] = ctrl_panel["FIGHT_ID"].map(elapsed)
cp = ctrl_panel.dropna(subset=["CTRL_SEC", "OP_CTRL_SEC", "elapsed", "reach_diff", "wc"])
cp = cp[cp["elapsed"] > 0].copy()
cp["ctrl_share_diff"] = (cp["CTRL_SEC"] - cp["OP_CTRL_SEC"]) / cp["elapsed"]
sd_reach_wc = cp.groupby("wc")["reach_diff"].transform("std")
cp["reach_z"] = cp["reach_diff"] / sd_reach_wc
cp = cp.dropna(subset=["reach_z"])


def slope(df):
    x = df["reach_z"].to_numpy()
    yv = df["ctrl_share_diff"].to_numpy()
    return float((x * yv).sum() / (x * x).sum()) if (x * x).sum() else None


pt, lo, hi, n, nf = cluster_boot(cp, slope, n_boot=1500)
within_fight_reach_ctrl = {
    "slope_ctrl_share_per_sd_reach": pt,
    "ci95": [lo, hi],
    "n_fighter_sides": n, "n_fights": int(cp["FIGHT_ID"].nunique()), "n_fighters": nf,
    "significant": bool(lo > 0 or hi < 0),
    "design": "control-share differential on within-class-standardised reach differential, "
              "no intercept (antisymmetric), fighter-clustered bootstrap",
}
print("\nwithin-fight reach -> control share:", within_fight_reach_ctrl)

# the old, underpowered version, kept so the site can show the contrast
per_fight_tracked = fstats.dropna(subset=["CTRL_SEC"]).groupby(["FIGHT_ID", "FIGHTER"], as_index=False).agg(
    CTRL_SEC=("CTRL_SEC", lambda s: s.sum(min_count=1)), NR=("CTRL_SEC", "count"))
per_fight_tracked["CTRL_PER_15"] = per_fight_tracked["CTRL_SEC"] / per_fight_tracked["NR"] * 3.0
career = per_fight_tracked.groupby("FIGHTER", as_index=False).agg(
    mean_ctrl_per_15=("CTRL_PER_15", "mean"), n_fights=("CTRL_PER_15", "count"))
career = career.merge(tott_d[["REACH_IN"]], left_on="FIGHTER", right_index=True, how="left").dropna()
pooled_corr = {"all": round(float(career["REACH_IN"].corr(career["mean_ctrl_per_15"])), 4),
               "n_fighters": int(len(career))}
for k in (3, 5, 10):
    sub = career[career["n_fights"] >= k]
    pooled_corr[f"min{k}_fights"] = {"r": round(float(sub["REACH_IN"].corr(sub["mean_ctrl_per_15"])), 4),
                                     "n_fighters": int(len(sub))}
print("pooled career correlation (the old test):", pooled_corr)

out = {
    "key": "bodies_v2",
    "snapshot_end": str(SNAPSHOT_END.date()),
    "coverage": coverage,
    "name_collisions": name_collisions,
    "univariate_forest": forest,
    "adjusted_forest": adjusted_forest,
    "adjusted_model": model_meta,
    "reach_by_weightclass": by_wc_reach,
    "control_min_count_bug": bug,
    "reach_control_within_fight": within_fight_reach_ctrl,
    "reach_control_pooled_career": pooled_corr,
    "n_boot": N_BOOT,
}
os.makedirs(OUT, exist_ok=True)
with open(f"{OUT}/bodies_v2.json", "w") as f:
    json.dump(out, f, indent=2)
print("\nWROTE bodies_v2.json")
