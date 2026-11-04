"""How do knocked-down fighters respond, and is any response associated with getting through the next round?
Two designs. (A) Pre-fight wrestling habit (takedown attempts per 15 min in PRIOR bouts only) x knockdown: exposure fixed before the fight, so no leakage
and no immortal-time problem. (B) Descriptive: among survivors who completed the whole next round, takedown users v strikers. (B) is conditional on
surviving that round and is labelled exploratory."""
import pandas as pd, numpy as np, json, warnings; warnings.filterwarnings('ignore')
from scipy import stats
import statsmodels.formula.api as smf
s=pd.read_parquet('data_out/next_round.parquet'); R={}
ks=s[s.kd_r==1].copy(); ks['hist']=np.where(ks.cum_kd>=3,2,np.where(ks.cum_kd>=1,1,0))
def trend(tab):
    n=tab.sum(1).values.astype(float); r=tab.iloc[:,1].values.astype(float); sc=np.arange(len(n)); N=n.sum(); p=r.sum()/N; T=(sc*(r-n*p)).sum(); V=p*(1-p)*((sc**2*n).sum()-(sc*n).sum()**2/N); z=T/np.sqrt(V); return float(z),float(2*stats.norm.sf(abs(z)))
R['history_trend_stopped']=trend(pd.crosstab(ks['hist'],ks.stopped_next)); R['history_trend_kd_again']=trend(pd.crosstab(ks['hist'],ks.kd_next))
ks['ab']=pd.cut(ks.age,[0,29,33,60],labels=False); R['age_trend_stopped']=trend(pd.crosstab(ks.ab.dropna(),ks.loc[ks.ab.notna(),'stopped_next']))
y=ks.dropna(subset=['age']); fit=smf.logit('stopped_next ~ cum_kd + I(age-30) + head_abs_r + C(round) + C(div)',y).fit(disp=0,cov_type='cluster',cov_kwds={'groups':y.fighter_id})
R['survivor_logit']={k:dict(OR=float(np.exp(fit.params[k])),lo=float(np.exp(fit.conf_int().loc[k,0])),hi=float(np.exp(fit.conf_int().loc[k,1])),p=float(fit.pvalues[k])) for k in ['cum_kd','I(age - 30)','head_abs_r']}; R['survivor_logit']['n']=int(fit.nobs)
# (A) wrestling habit from prior bouts
w=s[(s.fight_no>=3)&s.prior_td_att_p15.notna()].copy(); cut=w.drop_duplicates(['fight_id','fighter_id']).prior_td_att_p15.quantile([1/3,2/3]).values; R['habit_cuts']=[float(c) for c in cut]
w['habit']=np.where(w.prior_td_att_p15>=cut[1],'wrestler',np.where(w.prior_td_att_p15<=cut[0],'striker','mixed'))
R['habit']={f'{h}|kd={k}':dict(n=len(v),stopped=float(v.stopped_next.mean()),kd_again=float(v.kd_next.mean()),td_try=float(v.td_try_next.mean()),td_try_r=float(v.td_try_r.mean()),head_pm=float(v.head_abs_pm_next.mean()),ctrl=float(v.n_ctrl_sec.mean())) for (h,k),v in w.groupby(['habit','kd_r'])}
w2=w[w.habit!='mixed'].dropna(subset=['age']).copy(); w2['wr']=(w2.habit=='wrestler').astype(int)
for o in ['stopped_next','kd_next','td_try_next']:
    fit=smf.logit(f'{o} ~ kd_r*wr + head_abs_r + diff_r + C(round) + C(div) + I(age-30)',w2).fit(disp=0,cov_type='cluster',cov_kwds={'groups':w2.fight_id})
    R['habit_logit_'+o]={k:dict(OR=float(np.exp(fit.params[k])),lo=float(np.exp(fit.conf_int().loc[k,0])),hi=float(np.exp(fit.conf_int().loc[k,1])),p=float(fit.pvalues[k])) for k in ['kd_r','wr','kd_r:wr']}
kw=w[w.kd_r==1]; 
for a,b in [('wrestler','striker')]:
    ct=pd.crosstab(kw[kw.habit.isin([a,b])].habit,kw[kw.habit.isin([a,b])].stopped_next); R['habit_fisher_stopped']=dict(OR=float(stats.fisher_exact(ct)[0]),p=float(stats.fisher_exact(ct)[1]))
    ct=pd.crosstab(kw[kw.habit.isin([a,b])].habit,kw[kw.habit.isin([a,b])].td_try_next); R['habit_fisher_tdtry']=dict(OR=float(stats.fisher_exact(ct)[0]),p=float(stats.fisher_exact(ct)[1]))
# within-fight change in behaviour: next round v the round BEFORE the knockdown (needs knockdown in round >=2)
p=s.sort_values(['fight_id','fighter_id','round']); gp=p.groupby(['fight_id','fighter_id'])
for c in ['td_att','sig_att','round_sec','dist_att','clinch_att']: p['p_'+c]=gp[c].shift(1)
b=p[(p.kd_r==1)&p.p_td_att.notna()&(p.p_round_sec>=299)&(p.n_round_sec>=299)].copy(); R['before_after_n']=len(b)
for lab,pre,post in [('td_att_per_round','p_td_att','n_td_att'),('sig_att_per_round','p_sig_att','n_sig_att'),('clinch_att','p_clinch_att','n_clinch_att')]:
    R['before_after_'+lab]=dict(pre=float(b[pre].mean()),post=float(b[post].mean()),wilcoxon_p=float(stats.wilcoxon(b[post]-b[pre])[1]),t_p=float(stats.ttest_rel(b[post],b[pre])[1]))
b['dshare_pre']=b.p_dist_att/b.p_sig_att.replace(0,np.nan); b['dshare_post']=b.n_dist_att/b.n_sig_att.replace(0,np.nan); bb=b.dropna(subset=['dshare_pre','dshare_post']); R['before_after_distance_share']=dict(pre=float(bb.dshare_pre.mean()),post=float(bb.dshare_post.mean()),wilcoxon_p=float(stats.wilcoxon(bb.dshare_post-bb.dshare_pre)[1]))
# (B) exploratory, conditional on completing the next round
c=ks[ks.n_round_sec>=299].copy(); c['grapple']=((c.n_td_landed>=1)|(c.n_ctrl_sec>=60)).astype(int); R['B_n']=len(c)
R['B']={int(k):dict(n=len(v),head_pm=float(v.head_abs_pm_next.mean()),head_pm_median=float(v.head_abs_pm_next.median()),kd_again=float(v.kd_next.mean()),won=float(v.won_fight.mean()),prior_td=float(v.prior_td_att_p15.mean())) for k,v in c.groupby('grapple')}
a_,b_=c.loc[c.grapple==1,'head_abs_pm_next'],c.loc[c.grapple==0,'head_abs_pm_next']; R['B_tests']=dict(head_mw_p=float(stats.mannwhitneyu(a_,b_)[1]),kd_fisher=[float(v) for v in stats.fisher_exact(pd.crosstab(c.grapple,c.kd_next))],won_fisher=[float(v) for v in stats.fisher_exact(pd.crosstab(c.grapple,c.won_fight))])
json.dump(R,open('data_out/results_tactics.json','w'),indent=1); print(json.dumps(R,indent=1))
