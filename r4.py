import numpy as np, pandas as pd, sys
import proxy_backtest as P
from proxy_backtest import *
exprs=["rank(-1*ts_corr(rank(volume/adv20), rank(close), 10))",
"rank(-1*ts_corr(rank(high-low), rank(volume), 10))*rank(ts_std_dev(returns,20))",
"-1*rank(ts_rank(volume/adv20,10))*rank(ts_sum(returns,5))",
"rank(-1*ts_sum(returns,10)/ts_std_dev(returns,20))*rank(volume/adv20)"]
sh_=lambda p:p.mean()/p.std()*np.sqrt(252)
for e in exprs:
    x=evaluate(e)
    for dec in (6,8,10,12):
        xx=sector_demean(x); xx=xx.sub(xx.mean(axis=1),axis=0)
        xx=sum(xx.shift(i)*(dec-i) for i in range(dec))/(dec*(dec+1)/2)
        w0=xx.div(xx.abs().sum(axis=1),axis=0); mw0=w0.abs().iloc[260:].max().max()
        pnl,to=simulate(x,dec); sh,ar,to,fit=stats(pnl,to)
        print(f"{sh:.2f} fit {fit:.2f} to {to:.2f} mw {mw0:.3f} ar {ar:.3f} dec {dec} | {e}")
