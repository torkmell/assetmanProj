"""Concentration & weighting tests on the V1 (defensive-sleeve) engine, so the Q&A numbers are
consistent with the pitched flagship. Reports CAGR/Vol/Sharpe/MaxDD/alpha/IS/OOS + avg # names.
Output: concentration_v1.json
"""
import json, warnings
from pathlib import Path
import numpy as np, pandas as pd, statsmodels.api as sm
warnings.filterwarnings("ignore")
CACHE=Path("data_cache"); DATA_ROOT=Path(__file__).resolve().parent/"course_data"
TC_BPS=15; START="2002-01-31"; IS_END="2015-12-31"; OOS_START="2016-01-31"
def me(idx): return pd.to_datetime(idx).to_period("M").to_timestamp("M")

prices=pd.read_csv(CACHE/"prices_sp500_monthly.csv",index_col=0,parse_dates=True)
bench=pd.read_csv(CACHE/"prices_benchmarks_monthly.csv",index_col=0,parse_dates=True)
vix=pd.read_csv(CACHE/"prices_vix_monthly.csv",index_col=0,parse_dates=True); vix.columns=["VIX"]
macro_px=pd.read_csv(CACHE/"macro_proxies_monthly.csv",index_col=0,parse_dates=True)
cons=pd.read_csv(CACHE/"sp500_constituents.csv")
defv=pd.read_csv(CACHE/"defensive_monthly.csv",index_col=0,parse_dates=True)
for df in (prices,bench,vix,macro_px,defv): df.index=me(df.index)
universe=[t for t in cons["ticker"] if t in prices.columns]
returns=prices[universe].pct_change(); spy=bench["SPY"].pct_change()

def rz(s,w=60,mp=24): return (s-s.rolling(w,min_periods=mp).mean())/s.rolling(w,min_periods=mp).std()
idx=vix.index; c=pd.DataFrame(index=idx); c["vix"]=-rz(vix["VIX"])
cred=np.log(macro_px["IEF"]).reindex(idx).ffill()-np.log(macro_px["HYG"]).reindex(idx).ffill()
c["credit"]=-rz(cred.diff(12)); c["yield"]=-rz(macro_px["^TNX"].reindex(idx).ffill().diff(12))
spx=macro_px["^GSPC"].reindex(idx).ffill(); c["trend"]=rz(np.log(spx).diff(1).shift(1).rolling(11).sum())
score=c.mean(axis=1).clip(-2,2).shift(1); gross=np.clip(0.65+0.175*score,0.3,1.0)
def momentum(r,lb=12,sk=1): return np.log1p(r).shift(sk).rolling(lb-sk).sum()
def zcs(p): return p.sub(p.mean(axis=1),axis=0).div(p.std(axis=1),axis=0)
def load_ff():
    ff5=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Research_Data_5_Factors_2x3_daily.CSV",skiprows=3,index_col=0)
    ff5.columns=[x.strip() for x in ff5.columns]; ff5.index=pd.to_datetime(ff5.index.astype(str),format="%Y%m%d"); ff5/=100.0
    mom=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Momentum_Factor_daily.CSV",skiprows=13,index_col=0,skipfooter=2,engine="python")
    mom.columns=["Mom"]; mom=mom.dropna(); mom.index=pd.to_datetime(mom.index.astype(str).str.strip(),format="%Y%m%d",errors="coerce"); mom=mom.dropna()/100.0
    m=(1+ff5.join(mom,how="inner")).resample("ME").prod()-1; m.index=me(m.index); return m
ff=load_ff(); rf=ff["RF"]
dret=defv.pct_change(); ief_ret=macro_px["IEF"].pct_change()
defensive_ret=dret.mean(axis=1).reindex(returns.index).fillna(ief_ret).fillna(rf)
sig=zcs(momentum(returns))

def run(q=None,n=None,weighting="equal"):
    rk=sig.rank(axis=1,pct=True)
    if n is not None:
        rnk=sig.rank(axis=1,ascending=False); mask=(rnk<=n).astype(float)
    else:
        mask=(rk>=1-q).astype(float)
    if weighting=="equal":
        w=mask.div(mask.sum(axis=1).replace(0,np.nan),axis=0)
    else:
        vol=returns.rolling(12,min_periods=6).std(); iv=(1.0/vol).where(mask>0); w=iv.div(iv.sum(axis=1),axis=0)
    w=w.fillna(0); wL=w.mul(gross.reindex(w.index).ffill().clip(0,1),axis=0)
    R=returns.reindex_like(wL).fillna(0); port=(wL.shift(1).fillna(0)*R).sum(axis=1)
    cashw=(1.0-wL.sum(axis=1)).clip(lower=0); port=port+cashw.shift(1).fillna(0)*defensive_ret.reindex(wL.index).fillna(0)
    turn=(wL-wL.shift(1)).abs().sum(axis=1); port=port-turn*(TC_BPS/10000.0)
    avg_n=(wL>0).sum(axis=1).loc[START:].mean()
    return port, avg_n, turn.loc[START:].mean()*12
def metrics(r):
    r=r.dropna(); cum=(1+r).cumprod(); cagr=cum.iloc[-1]**(12/len(r))-1; vol=r.std()*np.sqrt(12)
    ex=r-rf.reindex(r.index).fillna(0); sh=(ex.mean()*12)/(ex.std()*np.sqrt(12)); dd=(cum/cum.cummax()-1).min()
    return {"CAGR":float(cagr),"Vol":float(vol),"Sharpe":float(sh),"MaxDD":float(dd)}
def alpha(r):
    cols=["Mkt-RF","SMB","HML","RMW","CMA","Mom"]; d=pd.concat([(r-rf.reindex(r.index)).rename("y"),ff[cols]],axis=1).dropna()
    res=sm.OLS(d["y"],sm.add_constant(d[cols])).fit(cov_type="HAC",cov_kwds={"maxlags":6}); return float(res.params["const"]*12),float(res.tvalues["const"])

VAR=[("Top 25 names (high-conviction)",dict(n=25)),
     ("Top decile (q=0.10, ~50)",dict(q=0.10)),
     ("Quartile (q=0.25) — V1 FLAGSHIP",dict(q=0.25)),
     ("Tercile (q=0.33, ~165)",dict(q=0.33)),
     ("Quartile + inverse-vol weight",dict(q=0.25,weighting="invvol"))]
END=prices.index[-1]; results={}
for name,kw in VAR:
    port,avgn,annto=run(**kw); r=port.loc[START:END]; a,at=alpha(r)
    results[name]={"full":metrics(r),"is":metrics(port.loc[START:IS_END]),"oos":metrics(port.loc[OOS_START:]),
                   "alpha":a,"alpha_t":at,"avg_n":float(avgn),"ann_turnover":float(annto)}
results["S&P 500 (SPY)"]={"full":metrics(spy.loc[START:END]),"is":metrics(spy.loc[START:IS_END]),"oos":metrics(spy.loc[OOS_START:]),"alpha":None,"alpha_t":None,"avg_n":0,"ann_turnover":0}

print("="*104)
print("CONCENTRATION & WEIGHTING — on the V1 (defensive-sleeve) engine · 2002-2026 · net 15bps")
print("="*104)
print(f"{'Variant':34}{'#names':>7}{'CAGR':>7}{'Vol':>7}{'Sharpe':>8}{'MaxDD':>7}{'Alpha':>9}{'(t)':>6}{'IS':>6}{'OOS':>6}")
for name,o in results.items():
    f=o["full"]; a=f"{o['alpha']*100:+.1f}%" if o["alpha"] is not None else "  —"; at=f"{o['alpha_t']:.1f}" if o["alpha_t"] is not None else " —"
    nn=f"{o['avg_n']:.0f}" if o['avg_n'] else "—"
    print(f"{name:34}{nn:>7}{f['CAGR']*100:6.1f}%{f['Vol']*100:6.1f}%{f['Sharpe']:8.2f}{f['MaxDD']*100:6.0f}%{a:>9}{at:>6}{o['is']['Sharpe']:6.2f}{o['oos']['Sharpe']:6.2f}")
Path("concentration_v1.json").write_text(json.dumps(results,indent=2,default=str))
print("\nSaved concentration_v1.json")
