# OFFLINE PROXY -- NOT BRAIN
import numpy as np, pandas as pd, re
import proxy_backtest as P
from proxy_backtest import *
P.NS["group_neutralize"]=lambda x,g: sector_demean(df(x))   # proxy: sector stands in for industry
industry=None
P.NS["industry"]=None
exprs=[l.strip() for l in open("round2_candidates.txt") if l.strip()]
def sim(x,decay):
    x=sector_demean(x); x=x.sub(x.mean(axis=1),axis=0)
    if decay>0: x=sum(x.shift(i)*(decay-i) for i in range(decay))/(decay*(decay+1)/2)
    w0=x.div(x.abs().sum(axis=1),axis=0)
    w=w0.clip(-0.08,0.08); w=w.div(w.abs().sum(axis=1),axis=0)
    wl=w.shift(1); pnl=(wl*RET).sum(axis=1).iloc[260:]; pnl=pnl[wl.iloc[260:].abs().sum(axis=1)>0]
    to=(w.diff().abs().sum(axis=1)/2).iloc[260:].mean()
    return pnl,to,w.abs().iloc[260:].max().max(),w0.abs().iloc[260:].max().max()
sh_=lambda p:p.mean()/p.std()*np.sqrt(252) if p.std()>0 else np.nan
rows=[]
for i,e in enumerate(exprs):
    try: x=evaluate(e)
    except Exception as ex: print("ERR",i,repr(ex)[:90]); continue
    for dec in (6,8,10,12):
        pnl,to,mw,mw0=sim(x,dec)
        if len(pnl)<500: continue
        sh,ar,to,fit=stats(pnl,to)
        r=dict(idx=i,decay=dec,sharpe=sh,fitness=fit,turnover=to,ann_ret=ar,max_w_trunc=mw,max_w_pretrunc=mw0)
        ys=pnl.groupby(pnl.index.year).apply(sh_)
        for y,v in ys.items(): r[f"sh_{y}"]=v
        yv=ys.drop(index=[y for y in ys.index if y<2019],errors="ignore")
        r["min_year_sh"]=ys.min(); r["sh_2021"]=ys.get(2021,np.nan)
        r["expr"]=e; rows.append(r)
    print(i,end=" ",flush=True)
R=pd.DataFrame(rows)
R["stab"]=R.fitness+0.3*R.min_year_sh.clip(upper=1)
R=R[R.turnover<=0.7].sort_values("stab",ascending=False)
R.to_csv("round2_results.csv",index=False)
pd.set_option("display.width",250)
print(R.drop(columns="expr").round(2).head(25).to_string())
