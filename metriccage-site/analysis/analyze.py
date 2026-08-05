import pandas as pd
import numpy as np
import json
import re

DATA = "/home/claude/ufc-data"

# ---------- load ----------
events = pd.read_csv(f"{DATA}/ufc_event_details.csv")
results = pd.read_csv(f"{DATA}/ufc_fight_results.csv")
stats = pd.read_csv(f"{DATA}/ufc_fight_stats.csv")

# strip whitespace from string cols / key join cols
for df in (events, results, stats):
    for c in df.columns:
        if df[c].dtype == object or "str" in str(df[c].dtype).lower() or df[c].dtype.name == "string":
            try:
                df[c] = df[c].astype("string").str.strip()
            except Exception:
                pass

events["DATE"] = pd.to_datetime(events["DATE"], format="%B %d, %Y", errors="coerce")
events = events.dropna(subset=["DATE"])
events = events[events["DATE"] <= "2026-08-01"]

print("events shape after date filter:", events.shape)

ev_small = events[["EVENT", "DATE"]].drop_duplicates(subset=["EVENT"])

stats = stats.merge(ev_small, on="EVENT", how="inner")
results = results.merge(ev_small, on="EVENT", how="inner")

print("stats shape after join:", stats.shape)
print("results shape after join:", results.shape)

stats["YEAR"] = stats["DATE"].dt.year
results["YEAR"] = results["DATE"].dt.year

def era_of(year):
    if 1994 <= year <= 1999:
        return "1994-1999"
    if 2000 <= year <= 2004:
        return "2000-2004"
    if 2005 <= year <= 2009:
        return "2005-2009"
    if 2010 <= year <= 2014:
        return "2010-2014"
    if 2015 <= year <= 2019:
        return "2015-2019"
    if 2020 <= year <= 2026:
        return "2020-2026"
    return None

stats["ERA"] = stats["YEAR"].apply(era_of)
results["ERA"] = results["YEAR"].apply(era_of)

# ---------- parse "x of y" columns ----------
def parse_xofy(series):
    landed = pd.Series(np.nan, index=series.index, dtype=float)
    attempted = pd.Series(np.nan, index=series.index, dtype=float)
    mask = series.notna()
    parts = series[mask].astype(str).str.split(" of ", expand=False)
    l = parts.apply(lambda p: float(p[0]) if len(p) == 2 else np.nan)
    a = parts.apply(lambda p: float(p[1]) if len(p) == 2 else np.nan)
    landed.loc[mask] = l.values
    attempted.loc[mask] = a.values
    return landed, attempted

for col in ["SIG.STR.", "TOTAL STR.", "TD", "HEAD", "BODY", "LEG", "DISTANCE", "CLINCH", "GROUND"]:
    l, a = parse_xofy(stats[col])
    stats[col + "_L"] = l
    stats[col + "_A"] = a

# CTRL parse: "m:ss" -> seconds; "--" -> NaN
def parse_ctrl(v):
    if pd.isna(v):
        return np.nan
    v = str(v).strip()
    if v == "--" or v == "":
        return np.nan
    if ":" not in v:
        return np.nan
    try:
        m, s = v.split(":")
        return int(m) * 60 + int(s)
    except Exception:
        return np.nan

stats["CTRL_SEC"] = stats["CTRL"].apply(parse_ctrl)

print("stats columns sample:\n", stats[["HEAD_L","BODY_L","LEG_L","DISTANCE_L","CLINCH_L","GROUND_L","TD_L","TD_A","CTRL_SEC"]].head())

# ---------- fight-level round rows (fighter-round rows) count ----------
n_rows_total = len(stats)
print("total fighter-round rows:", n_rows_total)

# unique fights (EVENT+BOUT)
stats["FIGHT_ID"] = stats["EVENT"] + " || " + stats["BOUT"]
results["FIGHT_ID"] = results["EVENT"] + " || " + results["BOUT"]

n_fights_stats = stats["FIGHT_ID"].nunique()
n_fights_results = results["FIGHT_ID"].nunique()
print("n unique fights in stats:", n_fights_stats, "in results:", n_fights_results)

# =========================================================
# 1. Strike-target mix by year and era (head/body/leg landed)
# =========================================================
def target_mix(df):
    head = df["HEAD_L"].sum()
    body = df["BODY_L"].sum()
    leg = df["LEG_L"].sum()
    total = head + body + leg
    n_rows = len(df)
    if total == 0 or np.isnan(total):
        return {"head": None, "body": None, "leg": None, "n_rows": int(n_rows)}
    return {
        "head": round(float(head / total), 3),
        "body": round(float(body / total), 3),
        "leg": round(float(leg / total), 3),
        "n_rows": int(n_rows),
    }

by_year_target = {}
for yr, g in stats.groupby("YEAR"):
    by_year_target[str(int(yr))] = target_mix(g)

by_era_target = {}
for era, g in stats.groupby("ERA"):
    by_era_target[era] = target_mix(g)

leg_2014 = by_year_target.get("2014", {}).get("leg")
leg_2021 = by_year_target.get("2021", {}).get("leg")
print("Leg share 2014:", leg_2014, "Leg share 2021:", leg_2021)

# =========================================================
# 2. Position mix by year and era (distance/clinch/ground landed)
# =========================================================
def position_mix(df):
    dist = df["DISTANCE_L"].sum()
    clinch = df["CLINCH_L"].sum()
    ground = df["GROUND_L"].sum()
    total = dist + clinch + ground
    n_rows = len(df)
    if total == 0 or np.isnan(total):
        return {"distance": None, "clinch": None, "ground": None, "n_rows": int(n_rows)}
    return {
        "distance": round(float(dist / total), 3),
        "clinch": round(float(clinch / total), 3),
        "ground": round(float(ground / total), 3),
        "n_rows": int(n_rows),
    }

by_year_position = {}
for yr, g in stats.groupby("YEAR"):
    by_year_position[str(int(yr))] = position_mix(g)

by_era_position = {}
for era, g in stats.groupby("ERA"):
    by_era_position[era] = position_mix(g)

# =========================================================
# 3. Takedowns: mean TD attempts per fight & accuracy by era
#    (aggregate per fighter per fight first by summing rounds)
# =========================================================
fighter_fight = stats.groupby(["FIGHT_ID", "FIGHTER", "ERA", "YEAR"], as_index=False).agg(
    TD_L=("TD_L", "sum"),
    TD_A=("TD_A", "sum"),
    SUBATT=("SUB.ATT", "sum"),
    HEAD_L=("HEAD_L", "sum"),
    BODY_L=("BODY_L", "sum"),
    LEG_L=("LEG_L", "sum"),
    DISTANCE_L=("DISTANCE_L", "sum"),
    CLINCH_L=("CLINCH_L", "sum"),
    GROUND_L=("GROUND_L", "sum"),
)

print("fighter_fight shape (fighter-fight rows):", fighter_fight.shape)

td_by_era = {}
for era, g in fighter_fight.groupby("ERA"):
    att_per_fight = g["TD_A"].mean()
    total_landed = g["TD_L"].sum()
    total_att = g["TD_A"].sum()
    acc = total_landed / total_att if total_att and total_att > 0 else None
    td_by_era[era] = {
        "att_per_fight": round(float(att_per_fight), 3) if not np.isnan(att_per_fight) else None,
        "accuracy": round(float(acc), 3) if acc is not None else None,
        "n_fighter_fights": int(len(g)),
    }

# =========================================================
# 4. Submission attempts per fight by era
#    (sum both corners per fight, then mean across fights)
# =========================================================
subatt_per_fight_by_era = {}
for era, g in fighter_fight.groupby("ERA"):
    per_fight = g.groupby("FIGHT_ID")["SUBATT"].sum()
    subatt_per_fight_by_era[era] = {
        "subatt_per_fight": round(float(per_fight.mean()), 3) if len(per_fight) else None,
        "n_fights": int(len(per_fight)),
    }

# =========================================================
# 5. Control time: mean control seconds per fighter per fight by year,
#    only years with CTRL coverage > 80%
# =========================================================
ctrl_by_year = {}
for yr, g in stats.groupby("YEAR"):
    coverage = g["CTRL_SEC"].notna().mean()
    yr_key = str(int(yr))
    if coverage > 0.8:
        ctrl_ff = stats[stats["YEAR"] == yr].groupby(["FIGHT_ID", "FIGHTER"])["CTRL_SEC"].sum(min_count=1)
        mean_sec = ctrl_ff.mean()
        ctrl_by_year[yr_key] = {
            "mean_sec": round(float(mean_sec), 3) if not np.isnan(mean_sec) else None,
            "coverage": round(float(coverage), 3),
        }
    else:
        ctrl_by_year[yr_key] = {
            "mean_sec": None,
            "coverage": round(float(coverage), 3),
        }

# =========================================================
# 6. Sequence proxies by era
#    (a) ground share of landed strikes (from position_mix by era)
#    (b) sub attempts per landed takedown
#    (c) share of finished fights ending by SUB among finishes
# =========================================================
def classify_method(m):
    if pd.isna(m):
        return None
    m = str(m).strip()
    if "Submission" in m:
        return "SUB"
    if "KO/TKO" in m or "TKO" in m or m.strip() == "KO":
        return "KO"
    if "Decision" in m:
        return "DEC"
    return "OTHER"

results["METHOD_CLASS"] = results["METHOD"].apply(classify_method)

seq_proxies_by_era = {}
for era in ["1994-1999", "2000-2004", "2005-2009", "2010-2014", "2015-2019", "2020-2026"]:
    g_pos = by_era_position.get(era, {})
    ground_share = g_pos.get("ground")

    g_ff = fighter_fight[fighter_fight["ERA"] == era]
    total_subatt = g_ff["SUBATT"].sum()
    total_td_landed = g_ff["TD_L"].sum()
    subatt_per_td = round(float(total_subatt / total_td_landed), 3) if total_td_landed and total_td_landed > 0 else None

    g_res = results[results["ERA"] == era]
    finishes = g_res[g_res["METHOD_CLASS"].isin(["SUB", "KO"])]
    n_finishes = len(finishes)
    n_sub = (finishes["METHOD_CLASS"] == "SUB").sum()
    sub_share = round(float(n_sub / n_finishes), 3) if n_finishes > 0 else None

    seq_proxies_by_era[era] = {
        "ground_share": ground_share,
        "subatt_per_td": subatt_per_td,
        "sub_share_of_finishes": sub_share,
        "n_finishes": int(n_finishes),
    }

print("seq_proxies_by_era:", json.dumps(seq_proxies_by_era, indent=2))

# =========================================================
# headlines
# =========================================================
headlines = []

if leg_2014 is not None and leg_2021 is not None:
    headlines.append({
        "stat": "leg_strike_share_2014_vs_2021",
        "value": f"{leg_2014} -> {leg_2021}",
        "n": by_year_target.get("2014", {}).get("n_rows", 0) + by_year_target.get("2021", {}).get("n_rows", 0),
        "note": "Share of landed sig strikes to the leg, 2014 vs 2021"
    })

era_2020 = td_by_era.get("2020-2026", {})
era_1994 = td_by_era.get("1994-1999", {})
headlines.append({
    "stat": "td_att_per_fighter_fight_1994-1999_vs_2020-2026",
    "value": f"{era_1994.get('att_per_fight')} -> {era_2020.get('att_per_fight')}",
    "n": era_1994.get("n_fighter_fights", 0) + era_2020.get("n_fighter_fights", 0),
    "note": "Mean TD attempts per fighter per fight by era"
})

headlines.append({
    "stat": "td_accuracy_1994-1999_vs_2020-2026",
    "value": f"{era_1994.get('accuracy')} -> {era_2020.get('accuracy')}",
    "n": era_1994.get("n_fighter_fights", 0) + era_2020.get("n_fighter_fights", 0),
    "note": "TD landed/attempted by era"
})

sub_2020 = subatt_per_fight_by_era.get("2020-2026", {})
sub_1994 = subatt_per_fight_by_era.get("1994-1999", {})
headlines.append({
    "stat": "subatt_per_fight_1994-1999_vs_2020-2026",
    "value": f"{sub_1994.get('subatt_per_fight')} -> {sub_2020.get('subatt_per_fight')}",
    "n": sub_1994.get("n_fights", 0) + sub_2020.get("n_fights", 0),
    "note": "Mean submission attempts per fight (both corners summed) by era"
})

years_covered = [y for y, v in ctrl_by_year.items() if v["coverage"] > 0.8]
headlines.append({
    "stat": "ctrl_time_coverage_usable_years",
    "value": f"{min(years_covered) if years_covered else None}-{max(years_covered) if years_covered else None}",
    "n": len(years_covered),
    "note": "Years where CTRL field coverage >80% of fighter-round rows; only these are trustworthy for control-time trend"
})

ground_1994 = seq_proxies_by_era.get("1994-1999", {}).get("ground_share")
ground_2020 = seq_proxies_by_era.get("2020-2026", {}).get("ground_share")
headlines.append({
    "stat": "ground_share_of_landed_strikes_1994-1999_vs_2020-2026",
    "value": f"{ground_1994} -> {ground_2020}",
    "n": None,
    "note": "Share of landed sig strikes occurring on the ground, by era"
})

sub_share_1994 = seq_proxies_by_era.get("1994-1999", {}).get("sub_share_of_finishes")
sub_share_2020 = seq_proxies_by_era.get("2020-2026", {}).get("sub_share_of_finishes")
headlines.append({
    "stat": "sub_share_of_finishes_1994-1999_vs_2020-2026",
    "value": f"{sub_share_1994} -> {sub_share_2020}",
    "n": seq_proxies_by_era.get("1994-1999", {}).get("n_finishes", 0) + seq_proxies_by_era.get("2020-2026", {}).get("n_finishes", 0),
    "note": "Share of finishes (SUB or KO) ending by submission, by era"
})

output = {
    "key": "targets",
    "by_year_target": by_year_target,
    "by_era_target": by_era_target,
    "by_year_position": by_year_position,
    "by_era_position": by_era_position,
    "td_by_era": td_by_era,
    "subatt_per_fight_by_era": subatt_per_fight_by_era,
    "ctrl_by_year": ctrl_by_year,
    "seq_proxies_by_era": seq_proxies_by_era,
    "headlines": headlines,
}

with open("/home/claude/mc-analysis/targets.json", "w") as f:
    json.dump(output, f, indent=2)

print("WROTE targets.json")
print(json.dumps(headlines, indent=2))
