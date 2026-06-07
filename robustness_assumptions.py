"""Stress-test the two unvalidated assumptions on the V1 engine:
  Test 1 — transaction cost: re-run at 15 / 30 / 50 / 100 bps.
  Test 2 — overlay calibration: 3x3 grid over baseline (0.55/0.65/0.75) x slope (0.125/0.175/0.225).
Reports CAGR / Sharpe / MaxDD so we can see if the edge is a plateau or a knife-edge.
"""
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
CACHE=Path("data_cache"); DATA_ROOT=Path(__file__).resolve().parent/"course_data"
START="2002-01-31"; IS_END="2015-12-31"; OOS_START="2016-01-31"
def me(idx): return pd.to_datetime(idx).to_period("M").to_timestamp("M")
prices=pd.read_csv(CACHE/"prices_sp500_monthly.csv",index_col=0,parse_dates=True)
bench=pd.read_csv(CACHE/"prices_benchmarks_monthly.csv",index_col=0,parse_dates=True)
vix=pd.read_csv(CACHE/"prices_vix_monthly.csv",index_col=0,parse_dates=True); vix.columns=["VIX"]
macro_px=pd.read_csv(CACHE/"macro_proxies_monthly.csv",index_col=0,parse_dates=True)
cons=pd.read_csv(CACHE/"sp500_constituents.csv")
defv=pd.read_csv(CACHE/"defensive_monthly.csv",index_col=0,parse_dates=True)
for df in (prices,bench,vix,macro_px,defv): df.index=me(df.index)
universe=[t for t in cons["ticker"] if t in prices.columns]; returns=prices[universe].pct_change()
def rz(s,w=60,mp=24): return (s-s.rolling(w,min_periods=mp).mean())/s.rolling(w,min_periods=mp).std()
idx=vix.index; c=pd.DataFrame(index=idx); c["vix"]=-rz(vix["VIX"])
cred=np.log(macro_px["IEF"]).reindex(idx).ffill()-np.log(macro_px["HYG"]).reindex(idx).ffill()
c["credit"]=-rz(cred.diff(12)); c["yield"]=-rz(macro_px["^TNX"].reindex(idx).ffill().diff(12))
spx=macro_px["^GSPC"].reindex(idx).ffill(); c["trend"]=rz(np.log(spx).diff(1).shift(1).rolling(11).sum())
score=c.mean(axis=1).clip(-2,2).shift(1)
def momentum(r,lb=12,sk=1): return np.log1p(r).shift(sk).rolling(lb-sk).sum()
def zcs(p): return p.sub(p.mean(axis=1),axis=0).div(p.std(axis=1),axis=0)
def load_ff():
    ff5=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Research_Data_5_Factors_2x3_daily.CSV",skiprows=3,index_col=0)
    ff5.columns=[x.strip() for x in ff5.columns]; ff5.index=pd.to_datetime(ff5.index.astype(str),format="%Y%m%d"); ff5/=100.0
    return (1+ff5["RF"]).resample("ME").prod()-1
rf=load_ff(); rf.index=me(rf.index)
dret=defv.pct_change(); ief_ret=macro_px["IEF"].pct_change()
defensive_ret=dret.mean(axis=1).reindex(returns.index).fillna(ief_ret).fillna(0.0)
sig=zcs(momentum(returns)); rk=sig.rank(axis=1,pct=True); mask=(rk>=0.75).astype(float)
w=mask.div(mask.sum(axis=1).replace(0,np.nan),axis=0).fillna(0)
R=returns.reindex_like(w).fillna(0)

def run(tc_bps=15, base=0.65, slope=0.175):
    gross=np.clip(base+slope*score,0.3,1.0)
    wL=w.mul(gross.reindex(w.index).ffill().clip(0,1),axis=0)
    port=(wL.shift(1).fillna(0)*R).sum(axis=1)
    cashw=(1.0-wL.sum(axis=1)).clip(lower=0); port=port+cashw.shift(1).fillna(0)*defensive_ret.reindex(wL.index).fillna(0)
    turn=(wL-wL.shift(1)).abs().sum(axis=1); port=port-turn*(tc_bps/10000.0)
    return port.loc[START:prices.index[-1]]
def metrics(r):
    r=r.dropna(); cum=(1+r).cumprod(); cagr=cum.iloc[-1]**(12/len(r))-1
    ex=r-rf.reindex(r.index).fillna(0); sh=(ex.mean()*12)/(ex.std()*np.sqrt(12)); dd=(cum/cum.cummax()-1).min()
    return cagr,sh,dd

import json
print("="*70)
print("TEST 1 — TRANSACTION-COST ROBUSTNESS (base 0.65, slope 0.175)")
print("="*70)
print(f"{'Cost (bps)':>12}{'CAGR':>9}{'Sharpe':>9}{'MaxDD':>9}")
tcost=[]
for tc in [15,30,50,100]:
    cg,sh,dd=metrics(run(tc_bps=tc)); print(f"{tc:>12}{cg*100:8.1f}%{sh:9.2f}{dd*100:8.0f}%")
    tcost.append({"bps":tc,"CAGR":float(cg),"Sharpe":float(sh),"MaxDD":float(dd)})

print("\n"+"="*70)
print("TEST 2 — OVERLAY-CALIBRATION ROBUSTNESS (Sharpe grid, tc=15)")
print("="*70)
bases=[0.55,0.65,0.75]; slopes=[0.125,0.175,0.225]
print(f"{'base|slope':>12}"+"".join(f"{s:>9}" for s in slopes))
grid=[]; shs=[]
for b in bases:
    row=[]
    for s in slopes:
        _,sh,_=metrics(run(base=b,slope=s)); row.append(float(sh))
    grid.append(row); shs+=row
    print(f"{b:>12}"+"".join(f"{x:9.2f}" for x in row))
print(f"\nSharpe range across the 9 overlay settings: {min(shs):.2f} – {max(shs):.2f}")
print("(Current strategy = base 0.65, slope 0.175.)")

Path("robustness_assumptions.json").write_text(json.dumps({
  "tcost":tcost,
  "overlay":{"bases":bases,"slopes":slopes,"sharpe_grid":grid,"min":float(min(shs)),"max":float(max(shs)),
             "current_base":0.65,"current_slope":0.175}
}, indent=2))
print("Saved robustness_assumptions.json")
