# OFFLINE PROXY -- NOT a WorldQuant BRAIN simulation. Adapted from ../wq_brain_alpha/proxy_backtest.py
import sys, re, json, warnings, numpy as np, pandas as pd, yfinance as yf
from numpy.lib.stride_tricks import sliding_window_view as swv
from universe import SECTOR
warnings.filterwarnings("ignore")
T = sorted(SECTOR)
d = yf.download(T, period="5y", auto_adjust=True, progress=False, group_by="column")
C = d["Close"].dropna(axis=1, thresh=1100); cols = C.columns
O,H,L,V = [d[k][cols].ffill() for k in ("Open","High","Low","Volume")]
C = C.ffill()
VWAP = (H+L+C)/3                       # PROXY: yfinance has no VWAP
RET = C.pct_change(); ADV20 = V.rolling(20).mean()
sec = pd.Series({t:SECTOR[t] for t in cols})
F = dict(close=C,open=O,high=H,low=L,volume=V,vwap=VWAP,returns=RET,adv20=ADV20)
print("universe", len(cols), "stocks", C.index[0].date(), C.index[-1].date())
def _w(x): return int(round(x))
def df(x, like=C): return x if isinstance(x,pd.DataFrame) else pd.DataFrame(x, index=like.index, columns=like.columns)
def rank(x): return df(x).astype(float).rank(axis=1, pct=True)
def ts_delay(x,n): return df(x).shift(_w(n))
def ts_delta(x,n): return df(x)-df(x).shift(_w(n))
def ts_sum(x,n): return df(x).astype(float).rolling(_w(n)).sum()
def ts_mean(x,n): return df(x).astype(float).rolling(_w(n)).mean()
def ts_std_dev(x,n): return df(x).astype(float).rolling(_w(n)).std()
def ts_min(x,n): return df(x).astype(float).rolling(_w(n)).min()
def ts_max(x,n): return df(x).astype(float).rolling(_w(n)).max()
def ts_product(x,n): return df(x).astype(float).rolling(_w(n)).apply(np.prod, raw=True) if _w(n)>1 else df(x).astype(float)
def ts_corr(x,y,n): return df(x).astype(float).rolling(_w(n)).corr(df(y).astype(float))
def ts_covariance(x,y,n): return df(x).astype(float).rolling(_w(n)).cov(df(y).astype(float))
def _win(x,n,f):
    x=df(x).astype(float).values; n=_w(n); out=np.full(x.shape,np.nan)
    if n<=x.shape[0]: out[n-1:]=f(swv(x,n,axis=0))   # windows (T-n+1, N, n)
    return pd.DataFrame(out,index=C.index,columns=C.columns)
def ts_rank(x,n): return _win(x,n,lambda w:(w<w[...,-1:]).sum(-1)/(w.shape[-1]-1+1e-9) if w.shape[-1]>1 else 0.5)
def ts_arg_max(x,n): return _win(x,n,lambda w:(w.shape[-1]-1-np.argmax(w,-1)).astype(float))
def ts_arg_min(x,n): return _win(x,n,lambda w:(w.shape[-1]-1-np.argmin(w,-1)).astype(float))
def ts_decay_linear(x,n):
    n=_w(n); wt=np.arange(1,n+1,dtype=float); wt/=wt.sum()
    return _win(x,n,lambda w:(w*wt).sum(-1))
def sign(x): return np.sign(df(x)) if isinstance(x,pd.DataFrame) else np.sign(x)
def abs_(x): return x.abs() if isinstance(x,pd.DataFrame) else abs(x)
def log(x): return np.log(x.where(x>0)) if isinstance(x,pd.DataFrame) else np.log(x)
def scale(x): x=df(x); return x.div(x.abs().sum(axis=1),axis=0)
def signed_power(x,p):
    if isinstance(p,pd.DataFrame): x=df(x)
    return np.sign(x)*np.abs(x)**p
def if_else(c,a,b):
    c=df(c); return df(a).where(c.astype(bool), df(b)) if isinstance(a,pd.DataFrame) or isinstance(b,pd.DataFrame) else c.astype(float)*a+(~c.astype(bool))*b
def min_(a,b): return np.minimum(df(a),df(b))
def max_(a,b): return np.maximum(df(a),df(b))
NS = dict(F, rank=rank,ts_delay=ts_delay,ts_delta=ts_delta,ts_sum=ts_sum,ts_mean=ts_mean,ts_std_dev=ts_std_dev,
  ts_min=ts_min,ts_max=ts_max,ts_product=ts_product,ts_corr=ts_corr,ts_covariance=ts_covariance,ts_rank=ts_rank,
  ts_arg_max=ts_arg_max,ts_arg_min=ts_arg_min,ts_decay_linear=ts_decay_linear,sign=sign,abs=abs_,log=log,scale=scale,
  signed_power=signed_power,if_else=if_else,min=min_,max=max_)
def evaluate(expr):
    # translate FastExpr -> python (only identifier-and-operator syntax; chained '<' not present)
    s=sec.reindex(cols)
    x = eval(expr, {"__builtins__":{}}, NS)
    x = df(x).astype(float).replace([np.inf,-np.inf],np.nan)
    return x
def sector_demean(x):
    return x - x.T.groupby(sec.values).transform("mean").T
def simulate(x, decay):
    x = sector_demean(x)                          # group_neutralize(x, sector)
    x = x.sub(x.mean(axis=1),axis=0)
    if decay>0:
        x = sum(x.shift(i)*(decay-i) for i in range(decay))/ (decay*(decay+1)/2)
    w = x.div(x.abs().sum(axis=1),axis=0)
    w = w.clip(-0.08,0.08); w = w.div(w.abs().sum(axis=1),axis=0)   # truncation 0.08
    pnl = (w.shift(1)*RET).sum(axis=1).iloc[260:]   # delay 1, skip warmup
    pnl = pnl[w.shift(1).iloc[260:].abs().sum(axis=1)>0]
    to = (w.diff().abs().sum(axis=1)/2).iloc[260:].mean()
    return pnl, to
def stats(pnl,to):
    sh = pnl.mean()/pnl.std()*np.sqrt(252); ar = pnl.mean()*252
    fit = sh*np.sqrt(abs(ar)/max(to,0.125))
    return sh,ar,to,fit
if __name__=="__main__":
    exprs=[l.strip() for l in open("candidates.txt") if l.strip()]
    rows=[]
    for i,e in enumerate(exprs):
        try: x=evaluate(e)
        except Exception as ex: print("ERR",i,repr(ex)[:80]); continue
        if x.notna().sum().sum()<1000: continue
        for dec in (0,3,6):
            pnl,to=simulate(x,dec)
            if len(pnl)<500 or not np.isfinite(pnl.std()) or pnl.std()==0: continue
            sh,ar,to,fit=stats(pnl,to)
            h=pnl.iloc[-len(pnl)//3:]; sh_oos=h.mean()/h.std()*np.sqrt(252)
            rows.append(dict(idx=i,decay=dec,sharpe=sh,ann_ret=ar,turnover=to,fitness=fit,sharpe_last_third=sh_oos,expr=e))
        print(i,end=" ",flush=True)
    R=pd.DataFrame(rows); R.to_json("proxy_results_all.json",orient="records",indent=1)
    R=R[R.turnover<=0.70]
    R.sort_values("fitness",ascending=False).to_csv("proxy_results.csv",index=False)
    print(); print(R.sort_values("fitness",ascending=False).head(15).drop(columns="expr").round(3))
