"""The round after a knockdown. Unit: fighter-round r where the fight continued into round r+1.
Exposure: knocked down in round r (opp_kd>=1). Outcomes: what happened in round r+1. Standard errors clustered by fight."""
import pandas as pd, numpy as np, json, warnings; warnings.filterwarnings('ignore')
from scipy import stats
import statsmodels.formula.api as smf
x=pd.read_parquet('data_out/rounds.parquet').sort_values(['fight_id','fighter_id','round']); R={}
g=x.groupby(['fight_id','fighter_id'])
nxt=['round','round_sec','opp_kd','opp_head_landed','opp_head_att','head_landed','sig_att','td_att','td_landed','ctrl_sec','clinch_att','dist_att','kd','opp_sig_landed','sig_landed']
for c in nxt: x['n_'+c]=g[c].shift(-1)
x['has_next']=x.n_round==x['round']+1
x['lost']=(x.winner_id!=x.fighter_id).astype(int); x['kd_r']=(x.opp_kd>=1).astype(int)
# how often is a knockdown survived at all?
k=x[x.kd_r==1]; R['kd_rounds']=len(k); R['kd_rounds_fight_ended_same_round']=int((k['round']==k.round_finished).sum()); R['kd_rounds_ended_same_round_as_ko_loss']=int(((k['round']==k.round_finished)&(k.method_canon=='KO/TKO')&(k.lost==1)).sum())
R['kd_rounds_final_scheduled_round_survived']=int(((k['round']!=k.round_finished)==False).sum()-R['kd_rounds_fight_ended_same_round']) if False else None
s=x[x.has_next].copy(); R['rounds_with_next']=len(s); R['kd_survived_into_next']=int(s.kd_r.sum()); R['fights_in_survivor_set']=int(s[s.kd_r==1].fight_id.nunique())
s['n_min']=s.n_round_sec/60; s['stopped_next']=((s.n_round==s.round_finished)&(s.method_canon=='KO/TKO')&(s.lost==1)).astype(int); s['finished_next_any']=((s.n_round==s.round_finished)&(s.method_canon!='Decision')&(s.lost==1)).astype(int)
s['kd_next']=(s.n_opp_kd>=1).astype(int); s['head_abs_pm_next']=s.n_opp_head_landed/s.n_min; s['head_def_next']=1-s.n_opp_head_landed/s.n_opp_head_att.replace(0,np.nan); s['head_def_r']=1-s.opp_head_landed/s.opp_head_att.replace(0,np.nan)
s['out_pm_next']=s.n_sig_att/s.n_min; s['out_pm_r']=s.sig_att/(s.round_sec/60); s['td_try_next']=(s.n_td_att>=1).astype(int); s['td_try_r']=(s.td_att>=1).astype(int); s['won_fight']=1-s.lost
s['head_abs_r']=s.opp_head_landed; s['diff_r']=s.sig_landed-s.opp_sig_landed; s['scored_kd_r']=(s.kd>=1).astype(int)
outs=['stopped_next','kd_next','head_abs_pm_next','head_def_next','out_pm_next','td_try_next','won_fight']
R['raw']={str(k_):{**{o:float(v[o].mean()) for o in outs},'n':len(v),'head_abs_r':float(v.head_abs_r.mean()),'td_try_r':float(v.td_try_r.mean())} for k_,v in s.groupby('kd_r')}
R['raw_tests']={}
for o in ['stopped_next','kd_next','td_try_next','won_fight']:
    ct=pd.crosstab(s.kd_r,s[o]); R['raw_tests'][o]=dict(chi2=float(stats.chi2_contingency(ct)[0]),p=float(stats.chi2_contingency(ct)[1]),OR=float(stats.fisher_exact(ct)[0]))
for o in ['head_abs_pm_next','head_def_next','out_pm_next']:
    a,b=s.loc[s.kd_r==1,o].dropna(),s.loc[s.kd_r==0,o].dropna(); R['raw_tests'][o]=dict(mw_p=float(stats.mannwhitneyu(a,b)[1]),welch_p=float(stats.ttest_ind(a,b,equal_var=False)[1]),median_kd=float(a.median()),median_no=float(b.median()))
# by round of knockdown
R['by_round']={int(r_):dict(n=int(v.kd_r.sum()),stopped_kd=float(v[v.kd_r==1].stopped_next.mean()),stopped_no=float(v[v.kd_r==0].stopped_next.mean()),kd_kd=float(v[v.kd_r==1].kd_next.mean()),kd_no=float(v[v.kd_r==0].kd_next.mean())) for r_,v in s.groupby('round') if v.kd_r.sum()>=30}
# adjusted: is it the knockdown or simply the beating? hold the round's head strikes absorbed and strike deficit constant
s['wc']=s.weight_class; adj='kd_r + head_abs_r + diff_r + scored_kd_r + C(round) + C(wc) + I(age-30)'; sm=s.dropna(subset=['age']); R['adjusted']={}
for o in ['stopped_next','kd_next','td_try_next']:
    rhs=adj+(' + td_try_r' if o=='td_try_next' else ''); fit=smf.logit(f'{o} ~ {rhs}',sm).fit(disp=0,cov_type='cluster',cov_kwds={'groups':sm.fight_id})
    R['adjusted'][o]={k_:dict(OR=float(np.exp(fit.params[k_])),lo=float(np.exp(fit.conf_int().loc[k_,0])),hi=float(np.exp(fit.conf_int().loc[k_,1])),p=float(fit.pvalues[k_])) for k_ in ['kd_r','head_abs_r','diff_r']}; R['adjusted'][o]['n']=int(fit.nobs)
for o in ['head_abs_pm_next','head_def_next']:
    y=sm.dropna(subset=[o,'head_def_r']); fit=smf.ols(f'{o} ~ {adj} + head_def_r',y).fit(cov_type='cluster',cov_kwds={'groups':y.fight_id}); R['adjusted'][o]=dict(b=float(fit.params['kd_r']),lo=float(fit.conf_int().loc['kd_r',0]),hi=float(fit.conf_int().loc['kd_r',1]),p=float(fit.pvalues['kd_r']))
# dose-matched contrast: same round, same division group, head strikes absorbed in round r within +/-2, no knockdown
s['hb']=(s.head_abs_r//3).astype(int); s['div']=np.where(s.women==1,0,np.where(s.wc_code<=7,1,np.where(s.wc_code<=9,2,3)))
cell=s.groupby(['round','div','hb']); tab=cell.apply(lambda v:pd.Series(dict(nk=(v.kd_r==1).sum(),nc=(v.kd_r==0).sum(),sk=v.loc[v.kd_r==1,'stopped_next'].sum(),sc=v.loc[v.kd_r==0,'stopped_next'].mean() if (v.kd_r==0).any() else np.nan,kk=v.loc[v.kd_r==1,'kd_next'].sum(),kc=v.loc[v.kd_r==0,'kd_next'].mean() if (v.kd_r==0).any() else np.nan))).dropna()
tab=tab[(tab.nk>0)&(tab.nc>=5)]; R['dose_matched']=dict(kd_rounds_used=int(tab.nk.sum()),stopped_kd=float(tab.sk.sum()/tab.nk.sum()),stopped_expected=float((tab.sc*tab.nk).sum()/tab.nk.sum()),kd_again=float(tab.kk.sum()/tab.nk.sum()),kd_again_expected=float((tab.kc*tab.nk).sum()/tab.nk.sum()))
# does history matter? previous knockdowns on the record (prior bouts only) among knocked-down survivors
ks=s[s.kd_r==1].copy(); ks['hist']=np.where(ks.cum_kd>=3,'3+',np.where(ks.cum_kd>=1,'1-2','0'))
R['survivor_by_history']={h:dict(n=len(v),stopped=float(v.stopped_next.mean()),kd_again=float(v.kd_next.mean()),age=float(v.age.mean())) for h,v in ks.groupby('hist')}
R['survivor_by_age']={str(a):dict(n=len(v),stopped=float(v.stopped_next.mean()),kd_again=float(v.kd_next.mean())) for a,v in ks.groupby(pd.cut(ks.age,[0,29,33,60],labels=['<29','29-32','33+']),observed=True)}
ct=pd.crosstab(ks['hist'],ks.stopped_next); R['survivor_history_chi2']=[float(v) for v in stats.chi2_contingency(ct)[:2]]
s.to_parquet('data_out/next_round.parquet'); json.dump(R,open('data_out/results_round.json','w'),indent=1); print(json.dumps(R,indent=1))
