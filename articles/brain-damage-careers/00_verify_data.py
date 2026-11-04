"""Integrity checks on the input files before any analysis. Reads only; writes data_out/verification.json."""
import pandas as pd, numpy as np, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; I=ROOT/'data/interim'
f=pd.read_parquet(I/'fights_enriched.parquet'); r=pd.read_parquet(I/'fight_rounds.parquet'); fi=pd.read_parquet(I/'fighters.parquet'); V={}
V['fights']=len(f); V['date_min']=str(f.event_date.min()); V['date_max']=str(f.event_date.max()); V['events']=int(f.event_id.nunique())
V['duplicate_fight_ids']=int(f.fight_id.duplicated().sum()); V['duplicate_round_rows']=int(r.duplicated(['fight_id','round','fighter_id']).sum()); V['self_fights']=int((f.fighter_a_id==f.fighter_b_id).sum())
V['fights_without_rounds']=int((~f.fight_id.isin(r.fight_id)).sum()); V['round_rows']=len(r); V['two_rows_per_round']=bool((r.groupby(['fight_id','round']).size()==2).all())
V['missing_share_fights']={c:float(v) for c,v in f.isna().mean().items() if v>0}; V['missing_share_rounds']={c:float(v) for c,v in r.isna().mean().items() if v>0}; V['fighters_missing_dob']=int(fi.dob.isna().sum())
s=r.groupby(['fight_id','fighter_id'])[['kd','sig_landed','head_landed','td_landed']].sum().reset_index(); chk={}
for side in 'ab':
    m=f[['fight_id',f'fighter_{side}_id',f'kd_{side}',f'ss_landed_{side}',f'head_landed_{side}',f'td_landed_{side}']].merge(s,left_on=['fight_id',f'fighter_{side}_id'],right_on=['fight_id','fighter_id'],how='left')
    for a,b in [(f'kd_{side}','kd'),(f'ss_landed_{side}','sig_landed'),(f'head_landed_{side}','head_landed'),(f'td_landed_{side}','td_landed')]: chk[a]=int((m[a]!=m[b]).sum())
V['alignment_mismatches_bout_vs_round_totals']=chk
V['winner_not_in_fight']=int((~((f.winner_id==f.fighter_a_id)|(f.winner_id==f.fighter_b_id))&f.winner_id.notna()&(f.winner_id!='')).sum()); V['no_winner']=int((f.winner_id.isna()|(f.winner_id=='')).sum())
last=r.groupby('fight_id')['round'].max(); V['round_finished_ne_last_round']=int((f.set_index('fight_id').round_finished!=last.reindex(f.fight_id).values).sum())
V['events_per_year']={int(k):int(v) for k,v in f.groupby(pd.to_datetime(f.event_date).dt.year).event_id.nunique().items()}
json.dump(V,open('data_out/verification.json','w'),indent=1); print(json.dumps(V,indent=1))
