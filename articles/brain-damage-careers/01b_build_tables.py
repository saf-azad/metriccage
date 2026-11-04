"""Build the two analysis tables. Reads data/interim/*.parquet (never written to) and data_out/fighter_pages.parquet.
career.parquet : one row per fighter per bout; every cumulative exposure counts PRIOR bouts only (no leakage from the bout analysed).
rounds.parquet : one row per fighter per round with the opponent's numbers alongside, keyed on fighter_id (adapted from the Song v Umar round builder)."""
import pandas as pd, numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; I=ROOT/'data/interim'
f=pd.read_parquet(I/'fights_enriched.parquet'); fi=pd.read_parquet(I/'fighters.parquet'); r=pd.read_parquet(I/'fight_rounds.parquet'); pg=pd.read_parquet('data_out/fighter_pages.parquet')
f['event_date']=pd.to_datetime(f.event_date)
stat=['kd','ss_landed','ss_attempted','td_landed','td_attempted','control_time','head_landed','head_att','distance_att','clinch_att','ground_att']
def side(me,op):
    d=f[['fight_id','event_date','weight_class','method_canon','round_finished','fight_duration_sec','winner_id']].copy()
    d['fighter_id']=f[f'fighter_{me}_id']; d['name']=f[f'fighter_{me}_name']; d['opp_id']=f[f'fighter_{op}_id']
    for s in stat: d[s]=f[f'{s}_{me}']; d['opp_'+s]=f[f'{s}_{op}']
    return d
d=pd.concat([side('a','b'),side('b','a')],ignore_index=True)
d['win']=(d.winner_id==d.fighter_id).astype(int); d['ko_loss']=((d.win==0)&(d.method_canon=='KO/TKO')).astype(int); d['minutes']=d.fight_duration_sec/60
d['head_abs']=d.opp_head_landed; d['kd_suffered']=d.opp_kd; d['kd_any']=(d.kd_suffered>0).astype(int)
d=d.merge(fi[['fighter_id','dob']],on='fighter_id',how='left').merge(pg,on='fighter_id',how='left'); d['age']=(d.event_date-pd.to_datetime(d.dob,errors='coerce')).dt.days/365.25
d=d.sort_values(['fighter_id','event_date','fight_id']).reset_index(drop=True); g=d.groupby('fighter_id')
d['fight_no']=g.cumcount()+1; d['n_fights_total']=g.fight_id.transform('count')
for c,new in [('head_abs','cum_head'),('kd_suffered','cum_kd'),('ko_loss','cum_ko_loss'),('minutes','cum_min'),('win','cum_win'),('td_attempted','cum_td_att'),('kd','cum_kd_scored')]: d[new]=g[c].cumsum()-d[c]
d['first_in_data']=g.event_date.transform('min'); d['unobs_listed']=(d.n_listed-d.n_fights_total).clip(lower=0)
d['left_censored']=(d.first_listed<pd.Timestamp('2010-01-01'))|(d.unobs_listed>=3)
d['head_def']=1-d.opp_head_landed/d.opp_head_att.replace(0,np.nan); d['sig_diff_pm']=((d.ss_landed-d.opp_ss_landed)/d.minutes).clip(-10,10)
d['prior_winpct']=d.cum_win/(d.fight_no-1).replace(0,np.nan); d['prior_td_att_p15']=15*d.cum_td_att/d.cum_min.replace(0,np.nan); d['power']=d.cum_kd_scored/d.cum_min.replace(0,np.nan)
wc=["Women's Strawweight","Women's Flyweight","Women's Bantamweight","Women's Featherweight",'Flyweight','Bantamweight','Featherweight','Lightweight','Welterweight','Middleweight','Light Heavyweight','Heavyweight']
d['wc_code']=d.weight_class.map({w:i for i,w in enumerate(wc)}); d['women']=d.weight_class.str.startswith('Women').astype(int)
opp=d[['fight_id','fighter_id','age','prior_winpct','power']].rename(columns={'fighter_id':'opp_id','age':'opp_age','prior_winpct':'opp_prior_winpct','power':'opp_power'}); d=d.merge(opp,on=['fight_id','opp_id'],how='left')
assert len(d)==2*len(f) and not d.duplicated(['fight_id','fighter_id']).any()
d.to_parquet('data_out/career.parquet')
# rounds
o=r.copy(); o['col']=1-o['col']; keep=[c for c in r.columns if c not in('fight_id','round','col','fighter_name')]
o=o[['fight_id','round','col']+keep].rename(columns={c:'opp_'+c for c in keep}); x=r.merge(o,on=['fight_id','round','col'],how='inner',validate='one_to_one')
x=x.merge(f[['fight_id','event_date','weight_class','method_canon','round_finished','time_finished_sec','winner_id']],on='fight_id')
x['round_sec']=np.where(x['round']==x.round_finished,x.time_finished_sec,300).astype(float); x['sched_last']=x.groupby('fight_id')['round'].transform('max')
x=x.merge(d[['fight_id','fighter_id','age','fight_no','cum_kd','cum_ko_loss','prior_td_att_p15','wc_code','women']],on=['fight_id','fighter_id'],how='left')
assert (x.fighter_id!=x.opp_fighter_id).all()
x.to_parquet('data_out/rounds.parquet'); print(d.shape,x.shape,d.left_censored.groupby(d.fighter_id).first().sum())
