"""
analyze_rates.py — the denominator pass.

Everything on discoveries.html that used to be a SHARE or a PER-FIGHT count is
recomputed here against elapsed fight time, because both the denominator (fight
duration) and the total volume roughly tripled across 1994-2026. A share can fall
while the underlying rate rises; four published findings turned on that.

Also fixes:
  * control time summed with min_count=1 so "no tracked control" stays missing,
    never zero (the stated methods guarantee; analyze.py:212 already did this,
    bodies_analyze.py:239 did not)
  * every era/year cell carries its OWN n, so the page can cite the cell rather
    than the corpus
  * winner control expressed as a share of elapsed time, which is the only way to
    compare a submission win against a decision win

Input : a clone of https://github.com/Greco1899/scrape_ufc_stats
Output: rates.json  (consumed by ../data/real-stats.js)
"""

import json
import os
import re

import numpy as np
import pandas as pd

DATA = os.environ.get("UFC_DATA", "/home/claude/ufc-data")
OUT = os.environ.get("MC_OUT", "/home/claude/mc-analysis")
SNAPSHOT_END = pd.Timestamp("2026-08-01")
ERAS = ["1994-1999", "2000-2004", "2005-2009", "2010-2014", "2015-2019", "2020-2026"]


def era_of(year):
    for e in ERAS:
        lo, hi = (int(x) for x in e.split("-"))
        if lo <= year <= hi:
            return e
    return None


# ---------------------------------------------------------------- load
events = pd.read_csv(f"{DATA}/ufc_event_details.csv")
results = pd.read_csv(f"{DATA}/ufc_fight_results.csv")
stats = pd.read_csv(f"{DATA}/ufc_fight_stats.csv")

for df in (events, results, stats):
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype) in ("str", "string"):
            df[c] = df[c].astype("string").str.strip()

events["DATE"] = pd.to_datetime(events["DATE"], format="%B %d, %Y", errors="coerce")
events = events.dropna(subset=["DATE"])
events = events[events["DATE"] <= SNAPSHOT_END]
ev = events[["EVENT", "DATE"]].drop_duplicates(subset="EVENT")

results = results.merge(ev, on="EVENT", how="inner")
stats = stats.merge(ev, on="EVENT", how="inner")
for df in (results, stats):
    df["YEAR"] = df["DATE"].dt.year
    df["ERA"] = df["YEAR"].map(era_of)
    df["FIGHT_ID"] = df["EVENT"] + " || " + df["BOUT"]


# ------------------------------------------------- THE MISSING DENOMINATOR
def round_lengths(fmt):
    """'3 Rnd (5-5-5)' -> [5,5,5];  '1 Rnd + OT (12-3)' -> [12,3]."""
    if pd.isna(fmt):
        return None
    m = re.search(r"\(([\d\-]+)\)", str(fmt))
    if not m:
        return None
    try:
        return [int(x) for x in m.group(1).split("-") if x != ""]
    except ValueError:
        return None


def mmss(t):
    if pd.isna(t):
        return np.nan
    m = re.match(r"^(\d+):(\d{1,2})$", str(t).strip())
    if not m:
        return np.nan
    return int(m.group(1)) * 60 + int(m.group(2))


def elapsed_seconds(row):
    """Exact fight length: completed rounds at their scheduled length, plus the
    clock in the final round. Returns NaN when the format is unparseable."""
    rl = round_lengths(row["TIME FORMAT"])
    final = mmss(row["TIME"])
    rnd = row["ROUND"]
    if final is np.nan or pd.isna(final) or pd.isna(rnd):
        return np.nan
    rnd = int(rnd)
    if rl is None:
        # 'No Time Limit' and friends: only round 1 is unambiguous
        return float(final) if rnd == 1 else np.nan
    if rnd > len(rl):
        return np.nan
    return float(sum(rl[: rnd - 1]) * 60 + final)


results["ELAPSED_SEC"] = results.apply(elapsed_seconds, axis=1)
results["ELAPSED_MIN"] = results["ELAPSED_SEC"] / 60.0
dur_cov = float(results["ELAPSED_SEC"].notna().mean())
print(f"fight-duration coverage: {dur_cov:.4f}  ({results['ELAPSED_SEC'].notna().sum()} of {len(results)})")


def classify_method(m):
    if pd.isna(m):
        return None
    m = str(m)
    if "Submission" in m:
        return "SUB"
    if "KO/TKO" in m or m.strip() == "KO":
        return "KO"
    if "Decision" in m:
        return "DEC"
    return "OTHER"


results["METHOD_CLASS"] = results["METHOD"].map(classify_method)
dur = results.set_index("FIGHT_ID")[["ELAPSED_MIN", "ELAPSED_SEC", "METHOD_CLASS", "WEIGHTCLASS", "OUTCOME", "BOUT"]]


# ---------------------------------------------------------------- parse stats
def parse_xofy(series):
    landed = pd.Series(np.nan, index=series.index, dtype=float)
    att = pd.Series(np.nan, index=series.index, dtype=float)
    mask = series.notna()
    parts = series[mask].astype(str).str.split(" of ")
    landed.loc[mask] = parts.apply(lambda p: float(p[0]) if len(p) == 2 else np.nan).values
    att.loc[mask] = parts.apply(lambda p: float(p[1]) if len(p) == 2 else np.nan).values
    return landed, att


for col in ["SIG.STR.", "TOTAL STR.", "TD", "HEAD", "BODY", "LEG", "DISTANCE", "CLINCH", "GROUND"]:
    stats[col + "_L"], stats[col + "_A"] = parse_xofy(stats[col])


def parse_ctrl(v):
    if pd.isna(v):
        return np.nan
    v = str(v).strip()
    if v in ("--", "") or ":" not in v:
        return np.nan
    try:
        m, s = v.split(":")
        return int(m) * 60 + int(s)
    except ValueError:
        return np.nan


stats["CTRL_SEC"] = stats["CTRL"].map(parse_ctrl)

# fighter-fight rollup. min_count=1 everywhere: an all-missing group must stay
# missing. pandas sum() on all-NaN returns 0.0, which is the bug this file exists
# partly to kill.
ff = stats.groupby(["FIGHT_ID", "FIGHTER"], as_index=False).agg(
    ERA=("ERA", "first"),
    YEAR=("YEAR", "first"),
    N_ROUNDS=("ROUND", "nunique"),
    SIG_L=("SIG.STR._L", lambda s: s.sum(min_count=1)),
    TD_L=("TD_L", lambda s: s.sum(min_count=1)),
    TD_A=("TD_A", lambda s: s.sum(min_count=1)),
    SUBATT=("SUB.ATT", lambda s: s.sum(min_count=1)),
    HEAD_L=("HEAD_L", lambda s: s.sum(min_count=1)),
    BODY_L=("BODY_L", lambda s: s.sum(min_count=1)),
    LEG_L=("LEG_L", lambda s: s.sum(min_count=1)),
    DIST_L=("DISTANCE_L", lambda s: s.sum(min_count=1)),
    CLINCH_L=("CLINCH_L", lambda s: s.sum(min_count=1)),
    GROUND_L=("GROUND_L", lambda s: s.sum(min_count=1)),
    CTRL_SEC=("CTRL_SEC", lambda s: s.sum(min_count=1)),
)
ff = ff.join(dur[["ELAPSED_MIN", "ELAPSED_SEC", "METHOD_CLASS", "WEIGHTCLASS"]], on="FIGHT_ID")

# fight-level (both corners summed)
fight = ff.groupby("FIGHT_ID", as_index=False).agg(
    ERA=("ERA", "first"),
    YEAR=("YEAR", "first"),
    ELAPSED_MIN=("ELAPSED_MIN", "first"),
    METHOD_CLASS=("METHOD_CLASS", "first"),
    N_CORNERS=("FIGHTER", "nunique"),
    SIG_L=("SIG_L", "sum"),
    DIST_L=("DIST_L", "sum"),
    CLINCH_L=("CLINCH_L", "sum"),
    GROUND_L=("GROUND_L", "sum"),
    HEAD_L=("HEAD_L", "sum"),
    BODY_L=("BODY_L", "sum"),
    LEG_L=("LEG_L", "sum"),
    TD_L=("TD_L", "sum"),
    TD_A=("TD_A", "sum"),
    SUBATT=("SUBATT", "sum"),
)
fight = fight[fight["N_CORNERS"] == 2]
rated = fight[fight["ELAPSED_MIN"].notna() & (fight["ELAPSED_MIN"] > 0)].copy()
print(f"fights with stats + usable duration: {len(rated)} of {len(fight)}")


def rate_block(g):
    """Total events / total elapsed minutes — a pooled rate, not a mean of ratios,
    so a 90-second fight cannot outweigh a 25-minute one."""
    mins = g["ELAPSED_MIN"].sum()
    if mins <= 0:
        return None
    out = {"n_fights": int(len(g)), "fight_minutes": round(float(mins), 1)}
    for key, col in [
        ("distance", "DIST_L"), ("clinch", "CLINCH_L"), ("ground", "GROUND_L"),
        ("head", "HEAD_L"), ("body", "BODY_L"), ("leg", "LEG_L"),
        ("sig_total", "SIG_L"), ("td_att", "TD_A"), ("td_landed", "TD_L"),
        ("sub_att", "SUBATT"),
    ]:
        out[key + "_per_min"] = round(float(g[col].sum() / mins), 4)
    pos_total = g[["DIST_L", "CLINCH_L", "GROUND_L"]].sum().sum()
    for key, col in [("distance", "DIST_L"), ("clinch", "CLINCH_L"), ("ground", "GROUND_L")]:
        out[key + "_share"] = round(float(g[col].sum() / pos_total), 4) if pos_total else None
    tgt_total = g[["HEAD_L", "BODY_L", "LEG_L"]].sum().sum()
    for key, col in [("head", "HEAD_L"), ("body", "BODY_L"), ("leg", "LEG_L")]:
        out[key + "_share"] = round(float(g[col].sum() / tgt_total), 4) if tgt_total else None
    out["td_accuracy"] = round(float(g["TD_L"].sum() / g["TD_A"].sum()), 4) if g["TD_A"].sum() else None
    out["sub_att_per_fight"] = round(float(g["SUBATT"].mean()), 4)
    out["td_att_per_fight_per_fighter"] = round(float(g["TD_A"].mean() / 2), 4)
    out["mean_duration_min"] = round(float(g["ELAPSED_MIN"].mean()), 3)
    return out


by_era_rate = {e: rate_block(g) for e, g in rated.groupby("ERA") if e}
by_year_rate = {str(int(y)): rate_block(g) for y, g in rated.groupby("YEAR")}

# ------------------------------------------------- 1.1 position, share vs rate
position_correction = []
for e in ERAS:
    b = by_era_rate.get(e)
    if not b:
        continue
    position_correction.append({
        "era": e,
        "n_fights": b["n_fights"],
        "fight_minutes": b["fight_minutes"],
        "share": {k: b[k + "_share"] for k in ("distance", "clinch", "ground")},
        "rate": {k: b[k + "_per_min"] for k in ("distance", "clinch", "ground")},
    })
first, last = position_correction[0], position_correction[-1]
pos_delta = {
    k: {
        "share_pct_change": round(100 * (last["share"][k] / first["share"][k] - 1), 1),
        "rate_pct_change": round(100 * (last["rate"][k] / first["rate"][k] - 1), 1),
        "rate_from": first["rate"][k], "rate_to": last["rate"][k],
        "share_from": first["share"][k], "share_to": last["share"][k],
    }
    for k in ("distance", "clinch", "ground")
}

# ------------------------------------------------- 1.2 takedowns: level vs step
td_series = [{
    "era": e,
    "per_fighter_fight": by_era_rate[e]["td_att_per_fight_per_fighter"],
    "per_min": by_era_rate[e]["td_att_per_min"],
    "accuracy": by_era_rate[e]["td_accuracy"],
    "n_fights": by_era_rate[e]["n_fights"],
} for e in ERAS if e in by_era_rate]

# ------------------------------------------------- 1.3 submissions: the hump
sub_series = [{
    "era": e,
    "per_fight": by_era_rate[e]["sub_att_per_fight"],
    "per_min": by_era_rate[e]["sub_att_per_min"],
    "per_landed_td": round(float(by_era_rate[e]["sub_att_per_min"] / by_era_rate[e]["td_landed_per_min"]), 4)
    if by_era_rate[e]["td_landed_per_min"] else None,
    "n_fights": by_era_rate[e]["n_fights"],
} for e in ERAS if e in by_era_rate]
peak = max(sub_series, key=lambda r: r["per_fight"])

# ------------------------------- 1.4 control: submission wins vs decision wins
# winner identification: UFCStats BOUT is "A vs. B" and OUTCOME is W/L or L/W.
res_w = results[results["OUTCOME"].isin(["W/L", "L/W"])].copy()


def winner_name(row):
    parts = re.split(r"\s+vs\.\s+", str(row["BOUT"]))
    if len(parts) != 2:
        return None
    return parts[0].strip() if row["OUTCOME"] == "W/L" else parts[1].strip()


res_w["WINNER"] = res_w.apply(winner_name, axis=1)
win_map = res_w.dropna(subset=["WINNER"]).set_index("FIGHT_ID")["WINNER"]
ff["WINNER"] = ff["FIGHT_ID"].map(win_map)
ff["IS_WINNER"] = ff["FIGHTER"] == ff["WINNER"]

# control only where the field is actually tracked (>=2000) AND the value exists
ctrl = ff[ff["IS_WINNER"] & ff["CTRL_SEC"].notna() & ff["ELAPSED_SEC"].notna() & (ff["ELAPSED_SEC"] > 0)].copy()
ctrl = ctrl[ctrl["YEAR"] >= 2000]
ctrl["CTRL_SHARE"] = ctrl["CTRL_SEC"] / ctrl["ELAPSED_SEC"]
ctrl["CTRL_PER_MIN"] = ctrl["CTRL_SEC"] / ctrl["ELAPSED_MIN"]

control_by_method = {}
for m in ("SUB", "DEC", "KO"):
    g = ctrl[ctrl["METHOD_CLASS"] == m]
    if not len(g):
        continue
    control_by_method[m] = {
        "n": int(len(g)),
        "mean_ctrl_sec": round(float(g["CTRL_SEC"].mean()), 1),
        "median_ctrl_sec": round(float(g["CTRL_SEC"].median()), 1),
        "mean_elapsed_min": round(float(g["ELAPSED_MIN"].mean()), 2),
        "median_elapsed_min": round(float(g["ELAPSED_MIN"].median()), 2),
        "mean_ctrl_share": round(float(g["CTRL_SHARE"].mean()), 4),
        "median_ctrl_share": round(float(g["CTRL_SHARE"].median()), 4),
        "ctrl_share_p25": round(float(g["CTRL_SHARE"].quantile(0.25)), 4),
        "ctrl_share_p75": round(float(g["CTRL_SHARE"].quantile(0.75)), 4),
        "mean_ctrl_per_min": round(float(g["CTRL_PER_MIN"].mean()), 2),
    }
    # distribution for a violin / strip plot — 40 quantiles keeps the JSON small
    qs = np.linspace(0.025, 0.975, 40)
    control_by_method[m]["share_quantiles"] = [round(float(g["CTRL_SHARE"].quantile(q)), 4) for q in qs]

# bootstrap the SUB-minus-DEC gap in control share
rng = np.random.default_rng(20260802)
a = ctrl[ctrl["METHOD_CLASS"] == "SUB"]["CTRL_SHARE"].to_numpy()
b = ctrl[ctrl["METHOD_CLASS"] == "DEC"]["CTRL_SHARE"].to_numpy()
boot = [rng.choice(a, a.size, replace=True).mean() - rng.choice(b, b.size, replace=True).mean() for _ in range(4000)]
control_gap = {
    "sub_minus_dec_share": round(float(a.mean() - b.mean()), 4),
    "ci95": [round(float(np.percentile(boot, 2.5)), 4), round(float(np.percentile(boot, 97.5)), 4)],
    "n_sub": int(a.size), "n_dec": int(b.size),
}

sub_finishes = results[(results["METHOD_CLASS"] == "SUB") & results["ELAPSED_MIN"].notna()]
sub_finish_clock = {
    "mean_min": round(float(sub_finishes["ELAPSED_MIN"].mean()), 2),
    "median_min": round(float(sub_finishes["ELAPSED_MIN"].median()), 2),
    "n": int(len(sub_finishes)),
}

# ------------------------------------------------- 1.6 coverage, the honest chart
coverage_by_year = {}
for y, g in stats.groupby("YEAR"):
    y = str(int(y))
    fights_y = results[results["YEAR"] == int(y)]
    coverage_by_year[y] = {
        "fights": int(fights_y["FIGHT_ID"].nunique()),
        "stat_rows": int(len(g)),
        "ctrl_coverage": round(float(g["CTRL_SEC"].notna().mean()), 4),
        "sig_coverage": round(float(g["SIG.STR._L"].notna().mean()), 4),
        "duration_coverage": round(float(fights_y["ELAPSED_SEC"].notna().mean()), 4) if len(fights_y) else None,
    }

corpus = {
    "n_fights": int(results["FIGHT_ID"].nunique()),
    "n_stat_rows": int(len(stats)),
    "n_fights_with_stats": int(stats["FIGHT_ID"].nunique()),
    "duration_coverage": round(dur_cov, 4),
}
era_cells = {}
for e in ERAS:
    g_rows = stats[stats["ERA"] == e]
    g_fights = results[results["ERA"] == e]
    era_cells[e] = {
        "stat_rows": int(len(g_rows)),
        "stat_rows_pct_of_corpus": round(100 * len(g_rows) / len(stats), 2),
        "fights": int(g_fights["FIGHT_ID"].nunique()),
        "fights_pct_of_corpus": round(100 * g_fights["FIGHT_ID"].nunique() / corpus["n_fights"], 2),
        "rated_fights": int((rated["ERA"] == e).sum()),
    }

# ------------------------------------------------- the dog that didn't bark
leg_by_year = {y: {"leg_share": v["leg_share"], "n_fights": v["n_fights"]}
               for y, v in by_year_rate.items() if v}
leg_by_era = {e: {"leg_share": by_era_rate[e]["leg_share"],
                  "leg_per_min": by_era_rate[e]["leg_per_min"],
                  "n_fights": by_era_rate[e]["n_fights"]}
              for e in ERAS if e in by_era_rate}

out = {
    "key": "rates",
    "generated_from": "UFCStats via Greco1899/scrape_ufc_stats",
    "snapshot_end": str(SNAPSHOT_END.date()),
    "corpus": corpus,
    "era_cells": era_cells,
    "by_era_rate": by_era_rate,
    "by_year_rate": by_year_rate,
    "position_correction": position_correction,
    "position_delta": pos_delta,
    "td_series": td_series,
    "sub_series": sub_series,
    "sub_peak_era": peak["era"],
    "control_by_method": control_by_method,
    "control_gap": control_gap,
    "sub_finish_clock": sub_finish_clock,
    "coverage_by_year": coverage_by_year,
    "leg_by_year": leg_by_year,
    "leg_by_era": leg_by_era,
}

os.makedirs(OUT, exist_ok=True)
with open(f"{OUT}/rates.json", "w") as f:
    json.dump(out, f, indent=2)

print("\n--- 1.1 position: share says one thing, rate says another ---")
for k, v in pos_delta.items():
    print(f"  {k:9s} share {v['share_from']:.3f}->{v['share_to']:.3f} ({v['share_pct_change']:+.1f}%)"
          f"   rate {v['rate_from']:.2f}->{v['rate_to']:.2f}/min ({v['rate_pct_change']:+.1f}%)")
print("\n--- 1.2 takedowns ---")
for r in td_series:
    print(f"  {r['era']}  {r['per_fighter_fight']:.3f}/fighter-fight  {r['per_min']:.4f}/min  acc {r['accuracy']:.3f}")
print("\n--- 1.3 submission attempts per fight ---")
print("  " + "  ".join(f"{r['per_fight']:.3f}" for r in sub_series), f"   peak={peak['era']}")
print("\n--- 1.4 winner control as a SHARE of elapsed time ---")
for m, v in control_by_method.items():
    print(f"  {m}: n={v['n']:5d}  mean {v['mean_ctrl_sec']:6.1f}s over {v['mean_elapsed_min']:5.2f}min"
          f"  = {v['mean_ctrl_share']:.3f} share (median {v['median_ctrl_share']:.3f})")
print(f"  SUB-DEC gap {control_gap['sub_minus_dec_share']:+.4f} CI {control_gap['ci95']}")
print(f"  mean submission finish {sub_finish_clock['mean_min']:.2f} min (median {sub_finish_clock['median_min']:.2f}, n={sub_finish_clock['n']})")
print("\n--- 1.6 the 1990s cell ---")
print(f"  1994-1999: {era_cells['1994-1999']['stat_rows']} rows "
      f"({era_cells['1994-1999']['stat_rows_pct_of_corpus']}% of corpus), "
      f"{era_cells['1994-1999']['fights']} fights "
      f"({era_cells['1994-1999']['fights_pct_of_corpus']}%)")
print("\nWROTE rates.json")
