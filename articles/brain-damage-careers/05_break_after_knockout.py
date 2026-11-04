"""After a KO/TKO loss: quick return v a significant break. Layoff is measured to the fighter's next listed UFC bout using the RAW bout list
(which still contains draws and no-contests), so an excluded bout cannot inflate a layoff. Outcome = the next bout in the analysis table."""
import pandas as pd, numpy as np, json, warnings; warnings.filterwarnings('ignore')
from pathlib import Path
from scipy import stats
import statsmodels.formula.api as smf
ROOT=Path(__file__).resolve().parents[2]; raw=pd.read_parquet(ROOT/'data/raw/fights_summary.parquet'); raw['event_date']=pd.to_datetime(raw.event_date)
allb=pd.concat([raw[['fight_id','event_date','fighter_a_id']].rename(columns={'fighter_a_id':'fighter_id'}),raw[['fight_id','event_date','fighter_b_id']].rename(columns={'fighter_b_id':'fighter_id'})]).sort_values(['fighter_id','event_date'])
allb['true_prev_date']=allb.groupby('fighter_id').event_date.shift(1); allb['true_prev_fight']=allb.groupby('fighter_id').fight_id.shift(1)
d=pd.read_parquet('data_out/career.parquet').merge(allb[['fight_id','fighter_id','true_prev_date','true_prev_fight']],on=['fight_id','fighter_id'],how='left').sort_values(['fighter_id','fight_no'])
g=d.groupby('fighter_id'); 
for c in ['ko_loss','kd_suffered','fight_id','round_finished','head_abs','win']: d['prev_'+c]=g[c].shift(1)
d['layoff']=(d.event_date-d.true_prev_date).dt.days; d['prev_in_table']=d.prev_fight_id==d.true_prev_fight      # previous listed bout is the KO loss itself (no draw/NC in between)
R={}; t=d[(d.prev_ko_loss==1)&d.prev_in_table&d.age.notna()].copy(); R['returns_after_ko']=len(t); R['fighters']=int(t.fighter_id.nunique())
# how many never came back (in the data) after a KO/TKO loss, by age
last=d[d.ko_loss==1].copy(); last['returned']=last.fight_no<last.n_fights_total; last=last[last.event_date<'2025-01-01']
R['never_returned_by_age']={str(k):dict(n=len(v),share=float(1-v.returned.mean())) for k,v in last.groupby(pd.cut(last.age,[0,30,34,60],labels=['<30','30-33','34+']),observed=True)}
R['layoff_quantiles']={str(q):float(t.layoff.quantile(q)) for q in [.1,.25,.5,.75,.9]}
t['grp']=pd.cut(t.layoff,[0,135,270,365,5000],labels=['under 4.5 months','4.5-9 months','9-12 months','over a year'])
def summarise(x): return {str(k):dict(n=len(v),ko_loss=float(v.ko_loss.mean()),kd_any=float(v.kd_any.mean()),win=float(v.win.mean()),age=float(v.age.mean()),prior_ko=float(v.cum_ko_loss.mean()),chin=float(100*v.kd_suffered.sum()/v.head_abs.sum())) for k,v in x.groupby('grp',observed=True)}
R['all_ko']=summarise(t); hard=t[t.prev_kd_suffered>=1]; R['ko_with_knockdown']=summarise(hard); R['ko_with_knockdown_n']=len(hard)
def tests(x,lab):
    out={}
    for o in ['ko_loss','kd_any','win']:
        ct=pd.crosstab(x.grp,x[o]); out[o+'_chi2_p']=float(stats.chi2_contingency(ct)[1]); out[o+'_spearman']=[float(v) for v in stats.spearmanr(x.layoff,x[o])]
        q,l=x[x.layoff<=135][o],x[x.layoff>270][o]; tb=[[int(q.sum()),int(len(q)-q.sum())],[int(l.sum()),int(len(l)-l.sum())]]; out[o+'_quick_v_long']=dict(quick=float(q.mean()),long=float(l.mean()),n=[len(q),len(l)],fisher_OR=float(stats.fisher_exact(tb)[0]),fisher_p=float(stats.fisher_exact(tb)[1]))
        x2=x.assign(long_break=(x.layoff>270).astype(int),quick=(x.layoff<=135).astype(int),lay_m=x.layoff/30.4,age_c=x.age-30)
        fit=smf.logit(f'{o} ~ quick + long_break + age_c + cum_ko_loss + C(weight_class) + opp_power_f',x2.assign(opp_power_f=x2.opp_power.fillna(x2.opp_power.median()))).fit(disp=0,cov_type='cluster',cov_kwds={'groups':x2.fighter_id})
        out[o+'_adj']={k:dict(OR=float(np.exp(fit.params[k])),lo=float(np.exp(fit.conf_int().loc[k,0])),hi=float(np.exp(fit.conf_int().loc[k,1])),p=float(fit.pvalues[k])) for k in ['quick','long_break','age_c','cum_ko_loss']}
    R[lab]=out
tests(t,'tests_all'); tests(hard,'tests_ko_with_knockdown')
# who takes the long break? (confounding by indication)
R['who_breaks']={str(k):dict(age=float(v.age.mean()),prior_ko=float(v.cum_ko_loss.mean()),prev_round1=float((v.prev_round_finished==1).mean()),prev_head_abs=float(v.prev_head_abs.mean())) for k,v in t.groupby('grp',observed=True)}
# power check: smallest difference detectable quick v long (80% power, two-sided 5%)
q,l=(t.layoff<=135).sum(),(t.layoff>270).sum(); p0=t.ko_loss.mean(); R['mde_ko_loss']=float(2.8*np.sqrt(p0*(1-p0)*(1/q+1/l)))
# examples
ex={}
for n in ['Alexander Volkanovski','Dooho Choi']:
    v=d[d.name==n][['event_date','age','win','method_canon','round_finished','kd_suffered','head_abs','layoff']].copy(); v['event_date']=v.event_date.astype(str); ex[n]=v.tail(6).to_dict('records')
R['examples']=ex; t.to_parquet('data_out/returns_after_ko.parquet'); json.dump(R,open('data_out/results_breaks.json','w'),indent=1,default=str); print(json.dumps({k:v for k,v in R.items() if k!='examples'},indent=1,default=str))
for n,v in ex.items(): print(n); print(pd.DataFrame(v).to_string())
