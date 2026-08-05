import pandas as pd
import numpy as np
import json
import re

DATA = '/home/claude/ufc-data/'

events = pd.read_csv(DATA + 'ufc_event_details.csv')
results = pd.read_csv(DATA + 'ufc_fight_results.csv')
stats = pd.read_csv(DATA + 'ufc_fight_stats.csv')

for df in (events, results, stats):
    for c in df.columns:
        if pd.api.types.is_string_dtype(df[c]) or df[c].dtype == object:
            df[c] = df[c].astype(str).str.strip()

events['DATE_PARSED'] = pd.to_datetime(events['DATE'], format='%B %d, %Y', errors='coerce')
events = events[events['DATE_PARSED'].notna()]
events = events[events['DATE_PARSED'] <= pd.Timestamp('2026-08-01')]

def era_bucket(year):
    if 1994 <= year <= 1999: return '1994-1999'
    if 2000 <= year <= 2004: return '2000-2004'
    if 2005 <= year <= 2009: return '2005-2009'
    if 2010 <= year <= 2014: return '2010-2014'
    if 2015 <= year <= 2019: return '2015-2019'
    if 2020 <= year <= 2026: return '2020-2026'
    return None

events['YEAR'] = events['DATE_PARSED'].dt.year
events['ERA'] = events['YEAR'].apply(era_bucket)

ev_map = events.drop_duplicates(subset='EVENT', keep='first').set_index('EVENT')[['DATE_PARSED', 'YEAR', 'ERA']]

results = results.merge(ev_map, left_on='EVENT', right_index=True, how='inner')
stats = stats.merge(ev_map, left_on='EVENT', right_index=True, how='inner')

def parse_x_of_y(s):
    if pd.isna(s):
        return (np.nan, np.nan)
    s = str(s).strip()
    m = re.match(r'^(\d+)\s+of\s+(\d+)$', s)
    if not m:
        return (np.nan, np.nan)
    return (int(m.group(1)), int(m.group(2)))

def parse_ctrl(s):
    if pd.isna(s):
        return np.nan
    s = str(s).strip()
    if s == '--' or s == '' or s.lower() == 'nan':
        return np.nan
    m = re.match(r'^(\d+):(\d+)$', s)
    if not m:
        return np.nan
    return int(m.group(1)) * 60 + int(m.group(2))

sig = stats['SIG.STR.'].apply(parse_x_of_y)
stats['SIG_LANDED'] = [x[0] for x in sig]
stats['SIG_ATT'] = [x[1] for x in sig]

td = stats['TD'].apply(parse_x_of_y)
stats['TD_LANDED'] = [x[0] for x in td]
stats['TD_ATT'] = [x[1] for x in td]

stats['CTRL_SEC'] = stats['CTRL'].apply(parse_ctrl)
stats['SUB_ATT_N'] = pd.to_numeric(stats['SUB.ATT'], errors='coerce')
stats['KD_N'] = pd.to_numeric(stats['KD'], errors='coerce')

stats['ROUND_N'] = stats['ROUND'].str.extract(r'Round (\d+)').astype(float)

results['METHOD_CLEAN'] = results['METHOD'].str.strip()
results['IS_DECISION'] = results['METHOD_CLEAN'].str.contains('Decision', case=False, na=False)
results['IS_DRAW_NC'] = results['OUTCOME'].isin(['D/D', 'NC/NC']) | results['OUTCOME'].str.contains('NC', na=False)

out = {}

tf3 = '3 Rnd (5-5-5)'
tf5 = '5 Rnd (5-5-5-5-5)'

dec3 = results[(results['TIME FORMAT'] == tf3) & results['IS_DECISION']]
dec5 = results[(results['TIME FORMAT'] == tf5) & results['IS_DECISION']]

print('dec3 fights:', len(dec3), 'dec5 fights:', len(dec5))

dec3_keys = set(zip(dec3['EVENT'], dec3['BOUT']))
dec5_keys = set(zip(dec5['EVENT'], dec5['BOUT']))

stats['KEY'] = list(zip(stats['EVENT'], stats['BOUT']))

round_arcs_by_era = {}
eras_order = ['1994-1999', '2000-2004', '2005-2009', '2010-2014', '2015-2019', '2020-2026']

stats3 = stats[stats['KEY'].isin(dec3_keys) & stats['ROUND_N'].isin([1, 2, 3])]

for era in eras_order:
    sub = stats3[stats3['ERA'] == era]
    if sub.empty:
        round_arcs_by_era[era] = None
        continue
    means = sub.groupby('ROUND_N')['SIG_LANDED'].mean()
    n_fights = sub['KEY'].nunique()
    r1 = means.get(1, np.nan)
    r2 = means.get(2, np.nan)
    r3 = means.get(3, np.nan)
    entry = {
        'r1': round(float(r1), 3) if pd.notna(r1) else None,
        'r2': round(float(r2), 3) if pd.notna(r2) else None,
        'r3': round(float(r3), 3) if pd.notna(r3) else None,
        'n_fights': int(n_fights),
    }
    if pd.notna(r1) and r1 != 0:
        entry['r1_norm'] = 1.0
        entry['r2_norm'] = round(float(r2 / r1), 3) if pd.notna(r2) else None
        entry['r3_norm'] = round(float(r3 / r1), 3) if pd.notna(r3) else None
    round_arcs_by_era[era] = entry

out['round_arcs_by_era'] = round_arcs_by_era
print(json.dumps(round_arcs_by_era, indent=2))

stats5 = stats[stats['KEY'].isin(dec5_keys) & stats['ROUND_N'].isin([1, 2, 3, 4, 5])]
means5 = stats5.groupby('ROUND_N')['SIG_LANDED'].mean()
n5 = stats5['KEY'].nunique()
five_round_arc = {f'r{i}': (round(float(means5.get(i)), 3) if i in means5.index and pd.notna(means5.get(i)) else None) for i in range(1, 6)}
five_round_arc['n'] = int(n5)
out['five_round_arc'] = five_round_arc
print(json.dumps(five_round_arc, indent=2))

gas_tank_ratio_by_era = {}
for era in eras_order:
    entry = round_arcs_by_era.get(era)
    if entry and entry.get('r1') and entry.get('r3') is not None and entry['r1'] not in (0, None):
        gas_tank_ratio_by_era[era] = round(entry['r3'] / entry['r1'], 3)
    else:
        gas_tank_ratio_by_era[era] = None
out['gas_tank_ratio_by_era'] = gas_tank_ratio_by_era
print(json.dumps(gas_tank_ratio_by_era, indent=2))

r5 = five_round_arc.get('r5')
r3_5 = five_round_arc.get('r3')
round5_vs_round3 = {
    'r5': r5,
    'r3': r3_5,
    'n': int(n5),
}
if r5 is not None and r3_5 is not None:
    round5_vs_round3['direction'] = 'surge' if r5 > r3_5 else ('fade' if r5 < r3_5 else 'flat')
else:
    round5_vs_round3['direction'] = None
out['round5_vs_round3'] = round5_vs_round3
print(json.dumps(round5_vs_round3, indent=2))

standard_classes = [
    "Flyweight", "Bantamweight", "Featherweight", "Lightweight",
    "Welterweight", "Middleweight", "Light Heavyweight", "Heavyweight",
    "Women's Strawweight", "Women's Flyweight", "Women's Bantamweight", "Women's Featherweight"
]

def extract_class(wc):
    if pd.isna(wc):
        return None
    wc = str(wc)
    for cls in sorted(standard_classes, key=len, reverse=True):
        if cls in wc:
            return cls
    return None

results['WC_CLEAN'] = results['WEIGHTCLASS'].apply(extract_class)

fight_round_counts = stats.groupby('KEY')['ROUND_N'].nunique()
fights_3plus = set(fight_round_counts[fight_round_counts >= 3].index)

key_to_wc = results.drop_duplicates(subset=['EVENT', 'BOUT'], keep='first').set_index(['EVENT', 'BOUT'])['WC_CLEAN']

stats_vol = stats[stats['KEY'].isin(fights_3plus)].copy()
grp = stats_vol.groupby(['KEY', 'FIGHTER'])['SIG_LANDED']
vol_df = grp.std().reset_index(name='vol')
vol_df['WC'] = vol_df['KEY'].map(key_to_wc)

kd_grp = stats.groupby(['KEY', 'FIGHTER'])['KD_N'].sum().reset_index(name='kd_total')
kd_grp['WC'] = kd_grp['KEY'].map(key_to_wc)

volatility_by_class = {}
for cls in standard_classes:
    v = vol_df[vol_df['WC'] == cls]['vol'].dropna()
    k = kd_grp[kd_grp['WC'] == cls]['kd_total'].dropna()
    if len(v) == 0:
        volatility_by_class[cls] = None
        continue
    volatility_by_class[cls] = {
        'vol': round(float(v.mean()), 3),
        'kd_per_fight': round(float(k.mean()), 3) if len(k) else None,
        'n': int(len(v)),
    }

out['volatility_by_class'] = volatility_by_class
print(json.dumps(volatility_by_class, indent=2))

mo_mask = results['BOUT'].str.contains('Makhachev', case=False, na=False) & results['BOUT'].str.contains('Oliveira', case=False, na=False)
mo_fights = results[mo_mask]
print('Makhachev-Oliveira fights found:', len(mo_fights))
print(mo_fights[['EVENT', 'BOUT', 'METHOD', 'ROUND', 'TIME']])

makhachev_oliveira_list = []
for _, row in mo_fights.iterrows():
    event = row['EVENT']
    bout = row['BOUT']
    key = (event, bout)
    fight_stats = stats[stats['KEY'] == key]
    fighters = fight_stats['FIGHTER'].unique()
    makh_name = [f for f in fighters if 'makhachev' in f.lower()]
    oliv_name = [f for f in fighters if 'oliveira' in f.lower()]
    makh_name = makh_name[0] if makh_name else None
    oliv_name = oliv_name[0] if oliv_name else None

    rounds_data = []
    max_round = int(fight_stats['ROUND_N'].max()) if not fight_stats.empty else 0
    for r in range(1, max_round + 1):
        rd_entry = {'round': r}
        for label, name in [('makhachev', makh_name), ('oliveira', oliv_name)]:
            if name is None:
                rd_entry[label] = None
                continue
            rrow = fight_stats[(fight_stats['FIGHTER'] == name) & (fight_stats['ROUND_N'] == r)]
            if rrow.empty:
                rd_entry[label] = None
                continue
            rrow = rrow.iloc[0]
            rd_entry[label] = {
                'sig': int(rrow['SIG_LANDED']) if pd.notna(rrow['SIG_LANDED']) else None,
                'td': int(rrow['TD_LANDED']) if pd.notna(rrow['TD_LANDED']) else None,
                'subatt': int(rrow['SUB_ATT_N']) if pd.notna(rrow['SUB_ATT_N']) else None,
                'ctrl_sec': int(rrow['CTRL_SEC']) if pd.notna(rrow['CTRL_SEC']) else None,
            }
        rounds_data.append(rd_entry)

    makhachev_oliveira_list.append({
        'event': event,
        'bout': bout,
        'method': row['METHOD'],
        'round': int(row['ROUND']) if pd.notna(row['ROUND']) else None,
        'time': row['TIME'],
        'rounds': rounds_data,
    })

if len(makhachev_oliveira_list) == 1:
    out['makhachev_oliveira'] = makhachev_oliveira_list[0]
elif len(makhachev_oliveira_list) > 1:
    out['makhachev_oliveira'] = {f"bout_{i+1}_{d['event']}": d for i, d in enumerate(makhachev_oliveira_list)}
else:
    out['makhachev_oliveira'] = None

print(json.dumps(out['makhachev_oliveira'], indent=2))

quiz_eras = ['1994-1999', '2005-2009', '2010-2014', '2020-2026']
quiz_shapes = {}

results['IS_FINISH'] = ~results['METHOD_CLEAN'].str.contains('Decision', case=False, na=False)
results_valid = results[~results['IS_DRAW_NC']]

for era in quiz_eras:
    sub3 = stats3[stats3['ERA'] == era]
    if sub3.empty:
        quiz_shapes[era] = {'shape': None, 'finish_rate': None, 'n': 0, 'note': 'no 3-round decision fight data for this era'}
        continue
    combined = sub3.groupby(['KEY', 'ROUND_N'])['SIG_LANDED'].sum().reset_index()
    combined_means = combined.groupby('ROUND_N')['SIG_LANDED'].mean()
    vals = [combined_means.get(i, np.nan) for i in [1, 2, 3]]
    n_fights = sub3['KEY'].nunique()
    if any(pd.isna(v) for v in vals) or max(vals) == 0:
        shape = None
    else:
        mx = max(vals)
        shape = [round(float(v / mx), 3) for v in vals]

    era_results = results_valid[results_valid['ERA'] == era]
    finish_rate = round(float(era_results['IS_FINISH'].mean()), 3) if len(era_results) else None

    quiz_shapes[era] = {
        'shape': shape,
        'finish_rate': finish_rate,
        'n': int(n_fights),
        'n_total_fights_for_finish_rate': int(len(era_results)),
    }

out['quiz_shapes'] = quiz_shapes
print(json.dumps(quiz_shapes, indent=2))

headlines = []

gt_2000 = gas_tank_ratio_by_era.get('2000-2004')
gt_now = gas_tank_ratio_by_era.get('2020-2026')
if gt_2000 is not None and gt_now is not None:
    trend = 'improved' if gt_now > gt_2000 else ('declined' if gt_now < gt_2000 else 'flat')
    headlines.append({
        'stat': 'gas_tank_trend',
        'value': f'round3/round1 ratio {trend} from {gt_2000} (2000-2004) to {gt_now} (2020-2026)',
        'n': round_arcs_by_era.get('2020-2026', {}).get('n_fights') if round_arcs_by_era.get('2020-2026') else None,
        'note': 'higher ratio = better endurance / less fade'
    })

if round5_vs_round3.get('r5') is not None and round5_vs_round3.get('r3') is not None:
    headlines.append({
        'stat': 'round5_vs_round3',
        'value': f"round 5 avg sig strikes landed {round5_vs_round3['r5']} vs round 3 {round5_vs_round3['r3']} ({round5_vs_round3.get('direction')})",
        'n': round5_vs_round3['n'],
        'note': '5-round decision fights only, all eras pooled'
    })

hw = volatility_by_class.get('Heavyweight')
fw = volatility_by_class.get('Flyweight')
if hw and fw:
    headlines.append({
        'stat': 'heavyweight_vs_flyweight_volatility',
        'value': f"Heavyweight per-round sig-strike std dev {hw['vol']} (n={hw['n']}) vs Flyweight {fw['vol']} (n={fw['n']})",
        'n': hw['n'] + fw['n'],
        'note': 'std dev of a fighters per-round sig strikes landed within a fight; higher = more volatile pace'
    })
    headlines.append({
        'stat': 'heavyweight_vs_flyweight_kd_per_fight',
        'value': f"Heavyweight KD/fight {hw['kd_per_fight']} vs Flyweight {fw['kd_per_fight']}",
        'n': hw['n'] + fw['n'],
        'note': None
    })

if out.get('makhachev_oliveira'):
    headlines.append({
        'stat': 'makhachev_oliveira',
        'value': 'UFC 280 Oct 2022: Makhachev def. Oliveira via submission, see makhachev_oliveira field',
        'n': 1,
        'note': None
    })

out['headlines'] = headlines

final = {'key': 'arcs'}
final.update(out)

with open('/home/claude/mc-analysis/arcs.json', 'w') as f:
    json.dump(final, f, indent=2)

print('WROTE arcs.json')
