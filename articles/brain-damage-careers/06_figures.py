"""Charts for the article (PNG + SVG). Reads data_out/*.json|parquet written by scripts 02-05 and the raw bout list for the two timelines."""
import json, numpy as np, pandas as pd, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from pathlib import Path
HERE=Path(__file__).resolve().parent
for p in (HERE/'fonts').glob('*.ttf'): fm.fontManager.addfont(str(p))
have={f.name for f in fm.fontManager.ttflist}; HEAD='Fraunces Black' if 'Fraunces Black' in have else 'DejaVu Serif'; BODY='Fraunces Regular' if 'Fraunces Regular' in have else 'DejaVu Serif'; MONOF='IBM Plex Mono' if 'IBM Plex Mono' in have else 'DejaVu Sans Mono'
BONE='#F4EFE7'; INK='#0E0E0C'; GRAPH='#3A3A38'; CAGE='#B8B0A4'; SOFT='#DDD6C9'; OX='#7A1E1E'; STEEL='#2D4A5E'
plt.rcParams.update({'font.family':BODY,'figure.facecolor':BONE,'axes.facecolor':BONE,'savefig.facecolor':BONE,'axes.edgecolor':CAGE,'axes.labelcolor':GRAPH,'xtick.color':GRAPH,'ytick.color':GRAPH,'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,'font.size':11,'svg.fonttype':'path'})
MONO={'family':MONOF}; SRC='Our dataset of 7,270 UFC fights, 2 Jan 2010 to 2 May 2026'
RR=json.load(open(HERE/'data_out/results_round.json')); RT=json.load(open(HERE/'data_out/results_tactics.json')); RB=json.load(open(HERE/'data_out/results_breaks.json')); RC=json.load(open(HERE/'data_out/results_career.json'))
def head(fig,title,sub,y=0.955): fig.text(0.05,y,title,fontsize=19,family=HEAD,color=INK,va='top'); fig.text(0.05,y-0.085,sub,fontsize=10.5,color=GRAPH,va='top')
def foot(fig,t):
    import textwrap; fig.text(0.05,0.018,'\n'.join(textwrap.wrap(t,118)),fontsize=7.8,color=GRAPH,va='bottom',linespacing=1.5,**MONO)
def clean(ax,axis='y'): ax.grid(axis=axis,color=SOFT,lw=0.8); ax.set_axisbelow(True); ax.tick_params(length=0)
def wilson(p,n,z=1.96): c=p+z*z/(2*n); h=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n)); d=1+z*z/n; return (c-h)/d,(c+h)/d
def save(fig,name): fig.savefig(HERE/f'figures/{name}.png',dpi=220); fig.savefig(HERE/f'figures/{name}.svg'); plt.close(fig)
# ---------- Fig 1: the round after a knockdown
raw=RR['raw']; dm=RR['dose_matched']; n0,n1=raw['0']['n'],raw['1']['n']
fig,axs=plt.subplots(1,2,figsize=(9.6,5.2),gridspec_kw={'width_ratios':[1.55,1]}); fig.subplots_adjust(top=0.70,bottom=0.2,left=0.17,right=0.97,wspace=0.2)
ax=axs[0]; rows=[('Stopped by strikes\nin the next round',raw['0']['stopped_next'],dm['stopped_expected'],raw['1']['stopped_next']),('Knocked down again\nin the next round',raw['0']['kd_next'],dm['kd_again_expected'],raw['1']['kd_next'])]
for i,(lab,b,e,k) in enumerate(rows):
    y=1-i
    for j,(v,c,nn) in enumerate([(b,CAGE,n0),(e,'#8C857A',None),(k,OX,n1)]):
        yy=y+0.27-j*0.27; ax.barh(yy,v*100,height=0.22,color=c,zorder=2)
        hi=v
        if nn: lo,hi=wilson(v,nn); ax.plot([lo*100,hi*100],[yy,yy],color=INK,lw=1.1,zorder=3)
        ax.text(hi*100+0.4,yy,f'{v*100:.1f}%',va='center',fontsize=10.5,color=INK,**MONO)
ax.set_yticks([1,0]); ax.set_yticklabels([r[0] for r in rows],fontsize=10.5,color=INK); ax.set_xlim(0,19); ax.set_ylim(-0.6,1.55); ax.set_xlabel('Share of rounds (%)'); clean(ax,'x')
for j,(t,c) in enumerate([(f'Not knocked down the round before (n = {n0:,})',CAGE),('Same division, round and head strikes absorbed, no knockdown','#8C857A'),(f'Knocked down the round before, fight continued (n = {n1:,})',OX)]): fig.text(0.05,0.765-j*0.032,'■',color=c,fontsize=9,family='DejaVu Sans'); fig.text(0.07,0.765-j*0.032,t,fontsize=8.6,color=GRAPH)
ax=axs[1]; A=RR['survivor_by_age']; ks=list(A); v=[A[k]['stopped']*100 for k in ks]; ci=[wilson(A[k]['stopped'],A[k]['n']) for k in ks]
ax.bar(range(3),v,width=0.55,color=[CAGE,'#9A5B52',OX],zorder=2); ax.errorbar(range(3),v,yerr=[[v[i]-ci[i][0]*100 for i in range(3)],[ci[i][1]*100-v[i] for i in range(3)]],fmt='none',ecolor=INK,lw=1.1,capsize=3,zorder=3)
for i,k in enumerate(ks): ax.text(i,ci[i][1]*100+0.7,f'{v[i]:.1f}%',ha='center',fontsize=10.5,color=INK,**MONO); ax.text(i,0.6,f"n = {A[k]['n']}",ha='center',fontsize=8,color=BONE if i else INK,**MONO)
ax.set_xticks(range(3)); ax.set_xticklabels(['Under 29','29 to 32','33 and over'],color=INK,fontsize=10); ax.set_ylim(0,23); ax.set_title('Dropped fighters stopped\nin the next round, by age (%)',fontsize=10,color=GRAPH,loc='left'); clean(ax)
head(fig,'The round after a knockdown is the dangerous one','What happened in round r+1 to fighters who were dropped in round r and answered the next bell')
foot(fig,f"{SRC} · adjusted odds ratios: stoppage 1.34 (1.05–1.70), repeat knockdown 1.90 (1.54–2.36) · 95% Wilson intervals")
save(fig,'fig1_round_after_knockdown')
# ---------- Fig 2: what hurt fighters change
fig,axs=plt.subplots(1,2,figsize=(9.6,4.9),gridspec_kw={'width_ratios':[1.25,1]}); fig.subplots_adjust(top=0.70,bottom=0.2,left=0.19,right=0.97,wspace=0.22)
ax=axs[0]; items=[('Takedown attempts\nper round',RT['before_after_td_att_per_round'],'{:.2f}',1),('Significant strikes\nthrown per round',RT['before_after_sig_att_per_round'],'{:.1f}',1),('Share of strikes thrown\nat distance (%)',{**RT['before_after_distance_share'],'pre':RT['before_after_distance_share']['pre']*100,'post':RT['before_after_distance_share']['post']*100},'{:.1f}',1)]
for i,(lab,d_,f_,_) in enumerate(items):
    y=2-i; base=d_['pre']; a,b=100,100*d_['post']/base; ax.plot([a,b],[y,y],color=SOFT,lw=4,zorder=1); ax.scatter([a],[y],s=120,color=CAGE,zorder=2,edgecolor=BONE,lw=1.5); ax.scatter([b],[y],s=120,color=OX,zorder=3,edgecolor=BONE,lw=1.5)
    ax.text(a-1.2,y+0.27,f_.format(d_['pre']),ha='center',fontsize=9.5,color=GRAPH,**MONO); ax.text(b+1.2,y-0.36,f_.format(d_['post']),ha='center',fontsize=9.5,color=OX,**MONO); ax.text(118,y,f"p = {d_['wilcoxon_p']:.2f}",va='center',fontsize=9,color=GRAPH,**MONO)
ax.set_yticks([2,1,0]); ax.set_yticklabels([i[0] for i in items],fontsize=10,color=INK); ax.set_xlim(85,126); ax.set_ylim(-0.7,2.6); ax.axvline(100,color=GRAPH,lw=0.8,ls=':'); ax.set_xlabel('Round after the knockdown (round before it = 100)'); clean(ax,'x')
ax.set_title(f"Same fighter, full rounds either side of the knockdown (n = {RT['before_after_n']})",fontsize=9.5,color=GRAPH,loc='left')
ax=axs[1]; B=RT['B']; v=[B['0']['head_pm'],B['1']['head_pm']]; ax.bar([0,1],v,width=0.52,color=[CAGE,STEEL],zorder=2)
for i,k in enumerate(['0','1']): ax.text(i,v[i]+0.08,f'{v[i]:.2f}',ha='center',fontsize=11,color=INK,**MONO); ax.text(i,0.12,f"n = {B[k]['n']}",ha='center',fontsize=8,color=INK if i==0 else BONE,**MONO)
ax.set_xticks([0,1]); ax.set_xticklabels(['Stayed in a\nstriking fight','Landed a takedown or\nheld 60 s of control'],color=INK,fontsize=9.5); ax.set_ylim(0,3.8); ax.set_title('Head strikes absorbed per minute, next round\n(exploratory: survivors of that round only)',fontsize=9.5,color=GRAPH,loc='left'); clean(ax)
head(fig,'Most hurt fighters change nothing','Behaviour in the round after a knockdown, and what a grappling round does to the head-strike count')
foot(fig,f"{SRC} · Wilcoxon signed-rank p-values · right panel is conditional on finishing the round")
save(fig,'fig2_what_hurt_fighters_change')
# ---------- Fig 3: breaks after a KO/TKO loss
G=RB['all_ko']; ks=list(G); v=[G[k]['ko_loss']*100 for k in ks]; ci=[wilson(G[k]['ko_loss'],G[k]['n']) for k in ks]
fig,ax=plt.subplots(figsize=(9.6,4.9)); fig.subplots_adjust(top=0.70,bottom=0.24,left=0.08,right=0.97)
ax.bar(range(4),v,width=0.55,color=[OX,CAGE,CAGE,STEEL],zorder=2); ax.errorbar(range(4),v,yerr=[[v[i]-ci[i][0]*100 for i in range(4)],[ci[i][1]*100-v[i] for i in range(4)]],fmt='none',ecolor=INK,lw=1.1,capsize=3,zorder=3)
for i,k in enumerate(ks): ax.text(i,ci[i][1]*100+0.8,f'{v[i]:.1f}%',ha='center',fontsize=11,color=INK,**MONO); ax.text(i,1.0,f"n = {G[k]['n']} · age {G[k]['age']:.1f}",ha='center',fontsize=8,color=BONE if i in(0,3) else INK,**MONO)
ax.axhline(RB['tests_all']['ko_loss_quick_v_long']['quick']*0+100*sum(G[k]['ko_loss']*G[k]['n'] for k in ks)/sum(G[k]['n'] for k in ks),color=GRAPH,lw=0.8,ls=':')
ax.set_xticks(range(4)); ax.set_xticklabels(['Under 4.5 months','4.5 to 9 months','9 to 12 months','Over a year'],color=INK); ax.set_ylim(0,34); ax.set_ylabel('Stopped by strikes again\nin the return bout (%)'); ax.set_xlabel('Time between the KO/TKO loss and the next UFC bout'); clean(ax)
q=RB['tests_all']['ko_loss_quick_v_long']
head(fig,'A longer break does not show up in the next result',f"Return bouts after a KO/TKO loss (n = {RB['returns_after_ko']:,}) · dotted line is the overall rate")
foot(fig,f"{SRC} · quick v 9 months+: {q['quick']*100:.1f}% v {q['long']*100:.1f}%, Fisher p = {q['fisher_p']:.2f} · design can only detect gaps of about {RB['mde_ko_loss']*100:.0f} points or more")
save(fig,'fig3_break_after_knockout')
# ---------- Fig 4: two timelines
rawb=pd.read_parquet(HERE.parents[1]/'data/raw/fights_summary.parquet'); rawb['event_date']=pd.to_datetime(rawb.event_date)
fig,axs=plt.subplots(2,1,figsize=(9.6,5.6)); fig.subplots_adjust(top=0.74,bottom=0.12,left=0.05,right=0.97,hspace=0.6)
for ax,(name,start,label) in zip(axs,[('Alexander Volkanovski','2023-01-01','Alexander Volkanovski'),('Dooho Choi','2016-06-01','Dooho Choi')]):
    b=rawb[((rawb.fighter_a_name==name)|(rawb.fighter_b_name==name))&(rawb.event_date>=start)].sort_values('event_date'); fid=b.apply(lambda r:r.fighter_a_id if r.fighter_a_name==name else r.fighter_b_id,axis=1)
    b=b.assign(res=np.where(b.winner_id==fid,'W',np.where(b.winner_id.isna()|(b.winner_id==''),'D','L'))); ax.axhline(0,color=CAGE,lw=1.2,zorder=1); prev=None; lastup=False; span=(b.event_date.max()-b.event_date.min()).days
    for _,r in b.iterrows():
        ko=(r.res=='L')and(r.method=='KO/TKO'); c=OX if r.res=='L' else (STEEL if r.res=='W' else CAGE); ax.scatter([r.event_date],[0],s=260 if ko else 150,color=c,marker='X' if ko else 'o',zorder=3,edgecolor=BONE,lw=1.5)
        opp=r.fighter_b_name if r.fighter_a_name==name else r.fighter_a_name; txt={'W':'Win','L':'Loss','D':'Draw'}[r.res]; txt=('KO/TKO '+txt.lower()) if r.method=='KO/TKO' else txt; up=(prev is not None) and ((r.event_date-prev.event_date).days<span*0.12) and not lastup; lastup=up; ax.text(r.event_date,1.75 if up else 0.55,f"{opp.split()[-1]}\n{txt}",ha='center',va='bottom',fontsize=8.2,color=INK)
        if up: ax.plot([r.event_date,r.event_date],[0.3,1.65],color=CAGE,lw=0.7,zorder=1)
        if prev is not None: ax.text(prev.event_date+(r.event_date-prev.event_date)/2,-0.5,f"{(r.event_date-prev.event_date).days} days",ha='center',va='top',fontsize=8.5,color=OX if (prev.res=='L' and prev.method=='KO/TKO') else GRAPH,**MONO)
        prev=r
    ax.set_ylim(-1.3,3.2); ax.set_yticks([]); ax.spines['bottom'].set_visible(False); ax.tick_params(length=0,labelsize=9); ax.set_title(label,fontsize=11.5,family=HEAD,color=INK,loc='left',pad=10)
    pad=pd.Timedelta(days=60 if name.startswith('Alex') else 150); ax.set_xlim(b.event_date.min()-pad,b.event_date.max()+pad)
head(fig,'Two comebacks, two different clocks','UFC bouts and the days between them · a cross marks a KO/TKO loss, red day-counts are the gaps that followed one')
foot(fig,'Dates and results from official UFC bout records; the 2023 Choi–Nelson draw is reported but sits outside our analysis table')
save(fig,'fig4_volkanovski_choi_timelines')
# ---------- Fig 5: matched pairs
fig,axs=plt.subplots(1,2,figsize=(9.6,4.7),sharey=True); fig.subplots_adjust(top=0.66,bottom=0.2,left=0.19,right=0.97,wspace=0.08)
for ax,key,hl,ll,col in [(axs[0],'matched_dose','Absorbed 121+ head strikes\nin first five bouts','Absorbed 76 or fewer',STEEL),(axs[1],'matched_early_kd','Knocked down in\nfirst five bouts','Never knocked down',OX)]:
    M=RC[key]
    for i,(o,lab) in enumerate([('l_ko','Later bouts lost\nby KO/TKO (%)'),('l_kdany','Later bouts with a\nknockdown suffered (%)')]):
        y=1-i; a,b=M['outcomes'][o]['lo']*100,M['outcomes'][o]['hi']*100; ax.plot([a,b],[y,y],color=SOFT,lw=4,zorder=1); ax.scatter([a],[y],s=130,color=CAGE,zorder=2,edgecolor=BONE,lw=1.5); ax.scatter([b],[y],s=130,color=col,zorder=3,edgecolor=BONE,lw=1.5)
        ax.text(a,y+0.2,f'{a:.1f}',ha='center',fontsize=10,color=GRAPH,**MONO); ax.text(b,y-0.3,f'{b:.1f}',ha='center',fontsize=10,color=col,**MONO); ax.text(27.5,y,f"p = {M['outcomes'][o]['wilcoxon_p']:.3f}".replace('0.','0.'),ha='right',va='center',fontsize=9,color=GRAPH,**MONO)
    ax.set_xlim(8,28); ax.set_ylim(-0.7,1.7); clean(ax,'x'); ax.set_xlabel('Per cent of bouts from the sixth onwards'); ax.set_title(f"{M['pairs']} pairs · {hl.replace(chr(10),' ')} (colour)\nv {ll.lower()} (grey)",fontsize=9.3,color=GRAPH,loc='left')
axs[0].set_yticks([1,0]); axs[0].set_yticklabels(['Later bouts lost\nby KO/TKO','Later bouts with a\nknockdown suffered'],fontsize=10,color=INK)
head(fig,'Same age path: volume washes out, knockdowns do not','Matched pairs with the same division group, debut age, age at sixth bout and record after five bouts')
foot(fig,f"{SRC} · fighters with 8+ bouts whose careers began inside the window · Wilcoxon signed-rank p-values")
save(fig,'fig5_matched_pairs'); print('figures ok',HEAD,BODY,MONOF)
