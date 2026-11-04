"""Career-scale tests: does accumulated head-strike VOLUME or KNOCKDOWN history track what happens next?
Adapted from the earlier career study in ../head-trauma-career-arc (same definitions), re-run here from data_out/career.parquet.
Main sample: fighters whose UFC careers began inside the data window (left_censored == False), bouts with at least one prior bout."""
import pandas as pd, numpy as np, json, warnings; warnings.filterwarnings('ignore')
from scipy import stats
from scipy.optimize import linear_sum_assignment
import statsmodels.formula.api as smf, statsmodels.api as sm
from lifelines.statistics import logrank_test
from lifelines import CoxPHFitter
d=pd.read_parquet('data_out/career.parquet'); R={}
R['n_fights']=int(d.fight_id.nunique()); R['n_fighters']=int(d.fighter_id.nunique()); R['total_head']=int(d.head_abs.sum()); R['veterans_excluded']=int(d[d.left_censored].fighter_id.nunique())
m=d[(d.fight_no>=2)&~d.left_censored].dropna(subset=['age']).copy(); R['main_n']=len(m); R['main_fighters']=int(m.fighter_id.nunique())
def partial_spearman(x,y,z):
    ok=x.notna()&y.notna()&z.notna(); rx,ry,rz=[stats.rankdata(v[ok]) for v in (x,y,z)]; Z=sm.add_constant(rz); ex=rx-Z@np.linalg.lstsq(Z,rx,rcond=None)[0]; ey=ry-Z@np.linalg.lstsq(Z,ry,rcond=None)[0]
    r=np.corrcoef(ex,ey)[0,1]; n=ok.sum(); t=r*np.sqrt((n-3)/(1-r*r)); return float(r),float(2*stats.t.sf(abs(t),n-3))
R['volume']={o:dict(raw=[float(v) for v in stats.spearmanr(m.cum_head,m[o])],partial_age=partial_spearman(m.cum_head,m[o],m.age)) for o in ['win','ko_loss','kd_any']}
m['band']=pd.cut(m.cum_head,[-1,49,149,299,599,1e6],labels=['0-49','50-149','150-299','300-599','600+']); R['bands']={b:dict(n=len(v),win=float(v.win.mean()),ko_loss=float(v.ko_loss.mean()),age=float(v.age.mean())) for b,v in m.groupby('band',observed=True)}
# knockdowns per 100 head strikes absorbed ("chin index") by knockdown history and by age
m['kh']=np.where(m.cum_kd>=3,'3+',np.where(m.cum_kd>=1,'1-2','0')); R['chin_by_history']={k:dict(n=len(v),per100=float(100*v.kd_suffered.sum()/v.head_abs.sum()),ko_loss=float(v.ko_loss.mean()),age=float(v.age.mean())) for k,v in m.groupby('kh')}
R['chin_by_age']={str(k):dict(n=len(v),per100=float(100*v.kd_suffered.sum()/v.head_abs.sum()),ko_loss=float(v.ko_loss.mean())) for k,v in m.groupby(pd.cut(m.age,[0,28,32,36,60],labels=['<28','28-31','32-35','36+']),observed=True)}
m['cum_head100']=m.cum_head/100; m['age_c']=m.age-30; 
for c,fill in [('opp_age',30),('opp_power',m.opp_power.median()),('opp_prior_winpct',.5),('prior_winpct',.5)]: m[c]=m[c].fillna(fill)
rhs='cum_head100 + cum_kd + cum_ko_loss + age_c + I(age_c**2) + fight_no + prior_winpct + C(weight_class) + opp_age + opp_power + opp_prior_winpct'; R['joint']={}
for o in ['ko_loss','kd_any']:
    fit=smf.logit(f'{o} ~ {rhs}',m).fit(disp=0,cov_type='cluster',cov_kwds={'groups':m.fighter_id}); R['joint'][o]={k:dict(OR=float(np.exp(fit.params[k])),lo=float(np.exp(fit.conf_int().loc[k,0])),hi=float(np.exp(fit.conf_int().loc[k,1])),p=float(fit.pvalues[k])) for k in ['cum_head100','cum_kd','cum_ko_loss','age_c']}
x=m[m.head_abs>0]; fit=smf.poisson('kd_suffered ~ cum_kd + cum_head100 + age_c + C(weight_class) + opp_power',x,exposure=x.head_abs).fit(disp=0,cov_type='cluster',cov_kwds={'groups':x.fighter_id})
R['chin_poisson']={k:dict(IRR=float(np.exp(fit.params[k])),lo=float(np.exp(fit.conf_int().loc[k,0])),hi=float(np.exp(fit.conf_int().loc[k,1])),p=float(fit.pvalues[k])) for k in ['cum_kd','cum_head100','age_c']}
# matched pairs on age path: exposure in bouts 1-5, outcomes from bout 6 (fighters with 8+ bouts)
e=d[~d.left_censored&(d.n_fights_total>=8)]; early=e[e.fight_no<=5]; late=e[e.fight_no>=6]
F=early.groupby('fighter_id').agg(name=('name','first'),debut_age=('age','min'),e_head=('head_abs','sum'),e_min=('minutes','sum'),e_kd=('kd_suffered','sum'),e_win=('win','mean'),wc=('wc_code','median'),women=('women','max'))
F['e_rate']=F.e_head/F.e_min; F['age6']=late.groupby('fighter_id').age.min(); F['div']=np.where(F.women==1,0,np.where(F.wc<=7,1,np.where(F.wc<=9,2,3)))
L=late.groupby('fighter_id').agg(l_n=('fight_id','count'),l_ko=('ko_loss','mean'),l_kdany=('kd_any','mean'),l_kd=('kd_suffered','sum'),l_head=('head_abs','sum'),l_win=('win','mean'),l_diff=('sig_diff_pm','mean'),l_age=('age','mean')); L['l_chin']=100*L.l_kd/L.l_head.replace(0,np.nan)
F=F.join(L).dropna(subset=['debut_age','age6','l_n']); F=F[F.l_n>=3]; R['match_pool']=len(F)
def match(hi,lo,cal):
    C=np.zeros((len(hi),len(lo))); bad=F.loc[hi,'div'].values[:,None]!=F.loc[lo,'div'].values[None,:]
    for c,w in cal.items(): dif=np.abs(F.loc[hi,c].values[:,None]-F.loc[lo,c].values[None,:]); C+=(dif/w)**2; bad|=dif>w
    C[bad]=1e6; r,c=linear_sum_assignment(C); ok=C[r,c]<1e6; return np.array(hi)[r[ok]],np.array(lo)[c[ok]]
def paired(hi,lo,lab):
    H,Lo=F.loc[hi].reset_index(),F.loc[lo].reset_index(); out=dict(pairs=len(H),balance={c:[float(H[c].mean()),float(Lo[c].mean())] for c in ['debut_age','age6','l_age','e_win','e_head','e_rate','e_kd']},outcomes={}); rng=np.random.default_rng(3)
    for o in ['l_ko','l_kdany','l_chin','l_win','l_diff']:
        df=(H[o]-Lo[o]).dropna(); bs=[df.sample(len(df),replace=True,random_state=int(s_)).mean() for s_ in rng.integers(0,1e9,2000)]
        out['outcomes'][o]=dict(hi=float(H.loc[df.index,o].mean()),lo=float(Lo.loc[df.index,o].mean()),diff=float(df.mean()),ci=[float(np.percentile(bs,2.5)),float(np.percentile(bs,97.5))],t_p=float(stats.ttest_rel(H.loc[df.index,o],Lo.loc[df.index,o])[1]),wilcoxon_p=float(stats.wilcoxon(df)[1]),sign=[int((df>0).sum()),int((df<0).sum())])
    b=pd.concat([late[late.fighter_id.isin(hi)].assign(g=1),late[late.fighter_id.isin(lo)].assign(g=0)]).dropna(subset=['age']); pid={**{h:i for i,h in enumerate(hi)},**{l:i for i,l in enumerate(lo)}}; b['pair']=b.fighter_id.map(pid); b['age_c']=b.age-32
    fit=smf.logit('ko_loss ~ g*age_c',b).fit(disp=0,cov_type='cluster',cov_kwds={'groups':b.pair}); out['group_x_age_p_ko']=float(fit.pvalues['g:age_c']); fit=smf.ols('sig_diff_pm ~ g*age_c',b).fit(cov_type='cluster',cov_kwds={'groups':b.pair}); out['group_x_age_p_diff']=float(fit.pvalues['g:age_c'])
    pd.DataFrame({'hi':F.loc[hi,'name'].values,'lo':F.loc[lo,'name'].values}).to_csv(f'data_out/pairs_{lab}.csv',index=False); R['matched_'+lab]=out
q=F.e_head.quantile([1/3,2/3]).values; R['dose_cuts']=[float(v) for v in q]
paired(*match(F.index[F.e_head>=q[1]].tolist(),F.index[F.e_head<=q[0]].tolist(),{'debut_age':1.5,'age6':1.5,'e_win':0.01}),'dose')
paired(*match(F.index[F.e_kd>=1].tolist(),F.index[F.e_kd==0].tolist(),{'debut_age':1.5,'age6':1.5,'e_win':0.01,'e_rate':0.5}),'early_kd')
# complication: first UFC loss by KO/TKO v submission v decision -> bouts until the next KO/TKO loss
rows=[]
for fid,v in d[~d.left_censored].sort_values(['fighter_id','fight_no']).groupby('fighter_id'):
    Ls=v[v.win==0]
    if Ls.empty: continue
    l=Ls.iloc[0]; post=v[v.fight_no>l.fight_no]
    if post.empty or pd.isna(l.age): continue
    ko=post[post.ko_loss==1]; rows.append(dict(how=l.method_canon,debut_loss=int(l.fight_no==1),T=int(ko.fight_no.iloc[0]-l.fight_no) if len(ko) else len(post),E=int(len(ko)>0),age_c=l.age-30,heavy=int(l.wc_code>=9),women=int(l.women)))
sv=pd.DataFrame(rows); sv=sv[sv.how.isin(['KO/TKO','Decision','Submission'])]; sv.to_parquet('data_out/survival.parquet'); R['first_loss_n']=sv.how.value_counts().to_dict()
for a,b in [('KO/TKO','Decision'),('Submission','Decision'),('KO/TKO','Submission')]:
    A,B=sv[sv.how==a],sv[sv.how==b]; t=logrank_test(A['T'],B['T'],A.E,B.E); R[f'logrank {a} v {b}']=dict(chi2=float(t.test_statistic),p=float(t.p_value))
for lab,sub in [('debut_loss',sv[sv.debut_loss==1]),('after_a_win',sv[sv.debut_loss==0])]:
    A,B,C=sub[sub.how=='KO/TKO'],sub[sub.how=='Submission'],sub[sub.how=='Decision']; R['first_loss_'+lab]=dict(n=sub.how.value_counts().to_dict(),later_ko_share={h:float(v.E.mean()) for h,v in sub.groupby('how')},ko_v_sub_p=float(logrank_test(A['T'],B['T'],A.E,B.E).p_value),ko_v_dec_p=float(logrank_test(A['T'],C['T'],A.E,C.E).p_value),sub_v_dec_p=float(logrank_test(B['T'],C['T'],B.E,C.E).p_value))
sv['ko']=(sv.how=='KO/TKO').astype(int); sv['sub']=(sv.how=='Submission').astype(int); cph=CoxPHFitter().fit(sv[['T','E','ko','sub','age_c','heavy','women']],'T','E').summary
R['cox']={k:dict(HR=float(cph.loc[k,'exp(coef)']),lo=float(cph.loc[k,'exp(coef) lower 95%']),hi=float(cph.loc[k,'exp(coef) upper 95%']),p=float(cph.loc[k,'p'])) for k in ['ko','sub']}
json.dump(R,open('data_out/results_career.json','w'),indent=1,default=str); print(json.dumps(R,indent=1,default=str))
