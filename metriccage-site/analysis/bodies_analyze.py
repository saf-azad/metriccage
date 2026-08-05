import pandas as pd
import numpy as np
import json
import re

pd.set_option('display.width', 150)

DATA = '/home/claude/ufc-data/'

# ---------- LOAD ----------
events = pd.read_csv(DATA + 'ufc_event_details.csv')
results = pd.read_csv(DATA + 'ufc_fight_results.csv')
stats = pd.read_csv(DATA + 'ufc_fight_stats.csv')
tott = pd.read_csv(DATA + 'ufc_fighter_tott.csv')

print("raw shapes:", events.shape, results.shape, stats.shape, tott.shape)

# strip whitespace from string cols (pandas 3.x uses a "str" dtype, not "object", so check kind)
for df in [events, results, stats, tott]:
    for c in df.columns:
        if df[c].dtype == object or df[c].dtype.kind in ('O', 'U', 'T') or str(df[c].dtype) == 'str':
            df[c] = df[c].astype(str).str.strip()
            df.loc[df[c].isin(['nan', 'None']), c] = np.nan

# ---------- PARSE TOTT ----------
def parse_height(h):
    if pd.isna(h) or h == '--':
        return np.nan
    m = re.match(r"(\d+)'\s*(\d+)", h)
    if not m:
        return np.nan
    ft, inch = int(m.group(1)), int(m.group(2))
    return ft * 12 + inch

def parse_reach(r):
    if pd.isna(r) or r == '--':
        return np.nan
    m = re.match(r'(\d+(\.\d+)?)"?', r)
    if not m:
        return np.nan
    return float(m.group(1))

tott['HEIGHT_IN'] = tott['HEIGHT'].apply(parse_height)
tott['REACH_IN'] = tott['REACH'].apply(parse_reach)
tott['DOB_DT'] = pd.to_datetime(tott['DOB'], format='%b %d, %Y', errors='coerce')
tott.loc[tott['DOB'] == '--', 'DOB_DT'] = pd.NaT

# dedupe fighter_tott by FIGHTER (keep first)
dup_n = tott['FIGHTER'].duplicated().sum()
tott_dedup = tott.drop_duplicates(subset='FIGHTER', keep='first').set_index('FIGHTER')
print("tott dup fighters dropped:", dup_n)

# ---------- PARSE EVENTS ----------
events['DATE_DT'] = pd.to_datetime(events['DATE'], format='%B %d, %Y', errors='coerce')
events_small = events[['EVENT', 'DATE_DT']].drop_duplicates(subset='EVENT', keep='first')

# ---------- PARSE RESULTS ----------
res = results.copy()
res = res[res['EVENT'].notna() & res['BOUT'].notna()]
split = res['BOUT'].str.split(' vs. ', n=1, expand=True)
res['F1'] = split[0].str.strip()
res['F2'] = split[1].str.strip() if split.shape[1] > 1 else np.nan
res = res[res['F2'].notna()]

# drop draws / NC — outcome must be W/L or L/W
res = res[res['OUTCOME'].isin(['W/L', 'L/W'])]
res['WINNER'] = np.where(res['OUTCOME'] == 'W/L', res['F1'], res['F2'])
res['LOSER'] = np.where(res['OUTCOME'] == 'W/L', res['F2'], res['F1'])

# join events for date
res = res.merge(events_small, on='EVENT', how='left')
before_date_filter = len(res)
res = res[res['DATE_DT'].notna() & (res['DATE_DT'] <= pd.Timestamp('2026-08-01'))]
print("results rows after outcome+date filter:", len(res), "of", before_date_filter, "raw", len(results))

# ---------- JOIN FIGHTER ATTRS ----------
def attach(df, name_col, prefix):
    idx = df[name_col]
    sub = tott_dedup.reindex(idx)
    sub = sub.add_prefix(prefix)
    sub.index = df.index
    return pd.concat([df, sub], axis=1)

res = attach(res, 'WINNER', 'W_')
res = attach(res, 'LOSER', 'L_')

# join rate = fraction of fighter-sides found in tott at all (any row, even if height/reach missing)
w_found = res['WINNER'].isin(tott_dedup.index)
l_found = res['LOSER'].isin(tott_dedup.index)
join_rate = float(((w_found.sum() + l_found.sum()) / (2 * len(res))))
print("join_rate (fighter name found in tott):", round(join_rate, 4))

res['W_AGE'] = (res['DATE_DT'] - res['W_DOB_DT']).dt.days / 365.25
res['L_AGE'] = (res['DATE_DT'] - res['L_DOB_DT']).dt.days / 365.25

def ci95(p, n):
    if n == 0 or p is None:
        return [None, None]
    se = np.sqrt(p * (1 - p) / n)
    return [round(max(0, p - 1.96 * se), 3), round(min(1, p + 1.96 * se), 3)]

out = {"key": "bodies", "join_rate": round(join_rate, 3)}

# ================= 1. REACH =================
r = res.dropna(subset=['W_REACH_IN', 'L_REACH_IN']).copy()
r = r[r['W_REACH_IN'] != r['L_REACH_IN']]
r['longer_won'] = r['W_REACH_IN'] > r['L_REACH_IN']
n_reach = len(r)
p_reach = r['longer_won'].mean() if n_reach else None
reach_out = {"overall": {"win": round(p_reach, 3) if p_reach is not None else None,
                          "ci": ci95(p_reach, n_reach),
                          "n": int(n_reach)}}

r['adv'] = (r['W_REACH_IN'] - r['L_REACH_IN']).abs()
bins = [(1, 2), (3, 4), (5, 999)]
by_bin = {}
for lo, hi in bins:
    sub = r[(r['adv'] >= lo) & (r['adv'] <= hi)]
    n = len(sub)
    p = sub['longer_won'].mean() if n else None
    label = f"{lo}-{hi}in" if hi < 999 else f"{lo}+in"
    by_bin[label] = {"win": round(p, 3) if p is not None else None, "ci": ci95(p, n), "n": int(n)}
reach_out["by_bin"] = by_bin
out["reach"] = reach_out

# ================= HEIGHT =================
h = res.dropna(subset=['W_HEIGHT_IN', 'L_HEIGHT_IN']).copy()
h = h[h['W_HEIGHT_IN'] != h['L_HEIGHT_IN']]
h['taller_won'] = h['W_HEIGHT_IN'] > h['L_HEIGHT_IN']
n_h = len(h)
p_h = h['taller_won'].mean() if n_h else None
height_out = {"overall": {"win": round(p_h, 3) if p_h is not None else None, "ci": ci95(p_h, n_h), "n": int(n_h)}}
h['adv'] = (h['W_HEIGHT_IN'] - h['L_HEIGHT_IN']).abs()
by_bin_h = {}
for lo, hi in bins:
    sub = h[(h['adv'] >= lo) & (h['adv'] <= hi)]
    n = len(sub)
    p = sub['taller_won'].mean() if n else None
    label = f"{lo}-{hi}in" if hi < 999 else f"{lo}+in"
    by_bin_h[label] = {"win": round(p, 3) if p is not None else None, "ci": ci95(p, n), "n": int(n)}
height_out["by_bin"] = by_bin_h
out["height"] = height_out

# ================= 2. STANCE =================
s = res.dropna(subset=['W_STANCE', 'L_STANCE']).copy()
os_pairs = s[((s['W_STANCE'] == 'Orthodox') & (s['L_STANCE'] == 'Southpaw')) |
             ((s['W_STANCE'] == 'Southpaw') & (s['L_STANCE'] == 'Orthodox'))].copy()
os_pairs['southpaw_won'] = os_pairs['W_STANCE'] == 'Southpaw'
n_sp = len(os_pairs)
p_sp = os_pairs['southpaw_won'].mean() if n_sp else None
stance_out = {"southpaw_vs_orthodox": {"win": round(p_sp, 3) if p_sp is not None else None,
                                        "ci": ci95(p_sp, n_sp), "n": int(n_sp)}}

# switch vs non-switch: fighter-fight level (each side is an observation)
w_side = res[['W_STANCE', 'L_STANCE']].rename(columns={'W_STANCE': 'stance', 'L_STANCE': 'opp_stance'})
w_side['won'] = True
l_side = res[['L_STANCE', 'W_STANCE']].rename(columns={'L_STANCE': 'stance', 'W_STANCE': 'opp_stance'})
l_side['won'] = False
allsides = pd.concat([w_side, l_side], ignore_index=True).dropna(subset=['stance', 'opp_stance'])
sw = allsides[allsides['stance'] == 'Switch']
nonsw = allsides[(allsides['stance'] != 'Switch')]
n_switch = len(sw)
p_switch = sw['won'].mean() if n_switch else None
n_nonswitch = len(nonsw)
p_nonswitch = nonsw['won'].mean() if n_nonswitch else None
stance_out["switch"] = {"switch_win": round(p_switch, 3) if p_switch is not None else None,
                         "switch_ci": ci95(p_switch, n_switch),
                         "switch_n": int(n_switch),
                         "non_switch_win": round(p_nonswitch, 3) if p_nonswitch is not None else None,
                         "non_switch_ci": ci95(p_nonswitch, n_nonswitch),
                         "non_switch_n": int(n_nonswitch)}
out["stance"] = stance_out

# ================= 3. AGE =================
a = res.dropna(subset=['W_AGE', 'L_AGE']).copy()
a = a[a['W_AGE'] != a['L_AGE']]
a['younger_won'] = a['W_AGE'] < a['L_AGE']
n_age = len(a)
p_age = a['younger_won'].mean() if n_age else None
age_out = {"younger_overall": {"win": round(p_age, 3) if p_age is not None else None,
                                "ci": ci95(p_age, n_age), "n": int(n_age)}}

a['gap'] = (a['W_AGE'] - a['L_AGE']).abs()
gap_bins = [(1, 3), (4, 6), (7, 999)]
by_gap = {}
for lo, hi in gap_bins:
    sub = a[(a['gap'] >= lo) & (a['gap'] <= hi)]
    n = len(sub)
    p = sub['younger_won'].mean() if n else None
    label = f"{lo}-{hi}y" if hi < 999 else f"{lo}+y"
    by_gap[label] = {"win": round(p, 3) if p is not None else None, "ci": ci95(p, n), "n": int(n)}
age_out["by_gap"] = by_gap

age_out["mean_winner_age"] = round(res['W_AGE'].dropna().mean(), 3)
age_out["mean_loser_age"] = round(res['L_AGE'].dropna().mean(), 3)

# by age band, fighter-fight level
w_age_side = res[['W_AGE']].rename(columns={'W_AGE': 'age'})
w_age_side['won'] = True
l_age_side = res[['L_AGE']].rename(columns={'L_AGE': 'age'})
l_age_side['won'] = False
allage = pd.concat([w_age_side, l_age_side], ignore_index=True).dropna(subset=['age'])
band_defs = [(20, 24), (25, 29), (30, 34), (35, 39), (40, 200)]
by_band = {}
for lo, hi in band_defs:
    sub = allage[(allage['age'] >= lo) & (allage['age'] <= hi)]
    n = len(sub)
    p = sub['won'].mean() if n else None
    label = f"{lo}-{hi}" if hi < 200 else f"{lo}+"
    by_band[label] = {"win": round(p, 3) if p is not None else None, "ci": ci95(p, n), "n": int(n)}
age_out["by_band"] = by_band
out["age"] = age_out

# ================= 4. ERA SHIFT =================
res['YEAR'] = res['DATE_DT'].dt.year
yearage_w = res[['YEAR', 'W_AGE']].rename(columns={'W_AGE': 'age'})
yearage_l = res[['YEAR', 'L_AGE']].rename(columns={'L_AGE': 'age'})
yearage = pd.concat([yearage_w, yearage_l], ignore_index=True).dropna(subset=['age'])
by_year = yearage.groupby('YEAR')['age'].mean().round(3)
age_by_year = {str(int(y)): float(v) for y, v in by_year.items()}
out["age_by_year"] = age_by_year

# ================= 5. HUG CHAIN =================
def parse_ctrl(c):
    if pd.isna(c) or c == '--':
        return np.nan
    try:
        m, s = c.split(':')
        return int(m) * 60 + int(s)
    except Exception:
        return np.nan

stats2 = stats.copy()
stats2['CTRL_SEC'] = stats2['CTRL'].apply(parse_ctrl)
stats2 = stats2.merge(events_small, on='EVENT', how='left')
stats2 = stats2[stats2['DATE_DT'].notna() & (stats2['DATE_DT'] <= pd.Timestamp('2026-08-01'))]

# per fight-per fighter totals (sum across rounds actually fought)
per_fight = stats2.groupby(['EVENT', 'BOUT', 'FIGHTER'], as_index=False).agg(
    CTRL_SEC=('CTRL_SEC', 'sum'), N_ROUNDS=('ROUND', 'nunique'))

# only rows where CTRL was actually tracked (non-null) -> modern era
per_fight_tracked = stats2.dropna(subset=['CTRL_SEC']).groupby(['EVENT', 'BOUT', 'FIGHTER'], as_index=False).agg(
    CTRL_SEC=('CTRL_SEC', 'sum'), N_ROUNDS_TRACKED=('CTRL_SEC', 'count'))
# ctrl per 15 min = total ctrl sec / (n_rounds_tracked * 5min) * 15min = total/n_rounds_tracked * 3
per_fight_tracked['CTRL_PER_15'] = per_fight_tracked['CTRL_SEC'] / per_fight_tracked['N_ROUNDS_TRACKED'] * 3.0

career = per_fight_tracked.groupby('FIGHTER', as_index=False).agg(
    mean_ctrl_per_15=('CTRL_PER_15', 'mean'), n_fights=('CTRL_PER_15', 'count'))
career = career.merge(tott_dedup[['REACH_IN']], left_on='FIGHTER', right_index=True, how='left')
career_valid = career.dropna(subset=['REACH_IN', 'mean_ctrl_per_15'])

corr = career_valid['REACH_IN'].corr(career_valid['mean_ctrl_per_15'])

reach_bins = [(0, 69.999, '<70'), (70, 73.999, '70-73'), (74, 77.999, '74-77'), (78, 999, '78+')]
ctrl_by_reach_bin = {}
for lo, hi, label in reach_bins:
    sub = career_valid[(career_valid['REACH_IN'] >= lo) & (career_valid['REACH_IN'] <= hi)]
    n = len(sub)
    ctrl_by_reach_bin[label] = {"mean_ctrl_per_15min_sec": round(sub['mean_ctrl_per_15'].mean(), 3) if n else None, "n_fighters": int(n)}

hug_out = {"reach_ctrl_corr": round(float(corr), 3) if pd.notna(corr) else None,
           "ctrl_by_reach_bin": ctrl_by_reach_bin}

# ctrl sec per fight for winner: sub vs decision
res_method = res[['EVENT', 'BOUT', 'WINNER', 'METHOD']].copy()
res_method['METHOD'] = res_method['METHOD'].str.strip()
winner_ctrl = per_fight.rename(columns={'FIGHTER': 'WINNER'})
merged_wc = res_method.merge(winner_ctrl, on=['EVENT', 'BOUT', 'WINNER'], how='left')
merged_wc = merged_wc.dropna(subset=['CTRL_SEC'])

sub_wins = merged_wc[merged_wc['METHOD'].str.contains('Submission', case=False, na=False)]
dec_wins = merged_wc[merged_wc['METHOD'].str.contains('Decision', case=False, na=False)]

hug_out["ctrl_sub_vs_dec"] = {
    "sub_win_ctrl_sec": round(sub_wins['CTRL_SEC'].mean(), 3) if len(sub_wins) else None,
    "dec_win_ctrl_sec": round(dec_wins['CTRL_SEC'].mean(), 3) if len(dec_wins) else None,
    "n_sub": int(len(sub_wins)),
    "n_dec": int(len(dec_wins))
}
out["hug"] = hug_out

# ================= 6. WEIGHT CLASS =================
STANDARD_WC = ["Flyweight", "Bantamweight", "Featherweight", "Lightweight",
               "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight",
               "Women's Strawweight", "Women's Flyweight", "Women's Bantamweight", "Women's Featherweight"]

# check women's classes first (substring match order matters: "Flyweight" is a substring of
# "Women's Flyweight", so checking men's classes first would misclassify women's fights)
STANDARD_WC_CHECK_ORDER = ["Women's Strawweight", "Women's Flyweight", "Women's Bantamweight",
                            "Women's Featherweight", "Flyweight", "Bantamweight", "Featherweight",
                            "Lightweight", "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight"]

def norm_wc(x):
    if pd.isna(x):
        return None
    x = x.replace(' Bout', '').replace(' Title', '').strip()
    if 'Catch Weight' in x or 'Catchweight' in x or x == 'Ultimate Fighter':
        return None
    for wc in STANDARD_WC_CHECK_ORDER:
        if wc.lower() in x.lower():
            return wc
    return None

res['WC'] = res['WEIGHTCLASS'].apply(norm_wc)
res['IS_FINISH'] = ~res['METHOD'].str.contains('Decision', case=False, na=False)

by_wc = {}
for wc in STANDARD_WC:
    sub = res[res['WC'] == wc]
    n = len(sub)
    if n == 0:
        by_wc[wc] = {"finish": None, "southpaw_share": None, "n": 0}
        continue
    finish_rate = sub['IS_FINISH'].mean()
    # southpaw share among fighters in this weight class (fighter-fight level, both sides)
    wside = sub[['W_STANCE']].rename(columns={'W_STANCE': 'stance'})
    lside = sub[['L_STANCE']].rename(columns={'L_STANCE': 'stance'})
    allst = pd.concat([wside, lside], ignore_index=True).dropna(subset=['stance'])
    sp_share = (allst['stance'] == 'Southpaw').mean() if len(allst) else None
    by_wc[wc] = {"finish": round(float(finish_rate), 3), "southpaw_share": round(float(sp_share), 3) if sp_share is not None else None, "n": int(n)}

out["by_weightclass"] = by_wc

# ================= HEADLINES =================
headlines = []
if reach_out["overall"]["win"] is not None:
    headlines.append({"stat": "reach_advantage_win_rate", "value": f"{reach_out['overall']['win']*100:.1f}%", "n": reach_out["overall"]["n"], "note": "longer-reach fighter wins, when reaches differ"})
if height_out["overall"]["win"] is not None:
    headlines.append({"stat": "height_advantage_win_rate", "value": f"{height_out['overall']['win']*100:.1f}%", "n": height_out["overall"]["n"], "note": "taller fighter wins, when heights differ"})
if p_sp is not None:
    headlines.append({"stat": "southpaw_vs_orthodox_win_rate", "value": f"{p_sp*100:.1f}%", "n": n_sp, "note": "southpaw win rate when facing orthodox"})
if p_age is not None:
    headlines.append({"stat": "younger_fighter_win_rate", "value": f"{p_age*100:.1f}%", "n": n_age, "note": "younger fighter wins, when ages differ"})
headlines.append({"stat": "mean_winner_age_vs_loser_age", "value": f"{age_out['mean_winner_age']:.2f} vs {age_out['mean_loser_age']:.2f}", "n": int(res['W_AGE'].notna().sum()), "note": "mean age of winners vs losers"})
if hug_out["reach_ctrl_corr"] is not None:
    headlines.append({"stat": "reach_vs_control_time_corr", "value": f"{hug_out['reach_ctrl_corr']:.3f}", "n": int(len(career_valid)), "note": "correlation of career mean reach vs mean control sec/15min"})
if hug_out["ctrl_sub_vs_dec"]["sub_win_ctrl_sec"] is not None and hug_out["ctrl_sub_vs_dec"]["dec_win_ctrl_sec"] is not None:
    headlines.append({"stat": "winner_ctrl_sec_sub_vs_dec", "value": f"{hug_out['ctrl_sub_vs_dec']['sub_win_ctrl_sec']:.1f}s vs {hug_out['ctrl_sub_vs_dec']['dec_win_ctrl_sec']:.1f}s", "n": hug_out["ctrl_sub_vs_dec"]["n_sub"] + hug_out["ctrl_sub_vs_dec"]["n_dec"], "note": "winner's control time per fight: submission wins vs decision wins"})

first_year = min(int(k) for k in age_by_year)
last_year = max(int(k) for k in age_by_year)
headlines.append({"stat": "era_age_shift", "value": f"{age_by_year.get(str(first_year))} ({first_year}) -> {age_by_year.get(str(last_year))} ({last_year})", "n": int(len(yearage)), "note": "mean fighter age by first/last available event year"})

out["headlines"] = headlines

with open('/home/claude/mc-analysis/bodies.json', 'w') as f:
    json.dump(out, f, indent=2)

print(json.dumps(out, indent=2)[:3000])
print("DONE")
