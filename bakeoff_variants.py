"""Strategy-variant bake-off on the LIVE MONTHLY engine (mirrors sectorwide_full.py).
Tests the team's ideas head-to-head vs the current strategy:
  V0 Baseline      : equal-weight top quartile, symmetric overlay, cash sleeve (current)
  V1 Defensive     : de-risked sleeve earns Treasuries+gold (TLT/GLD/IEF) instead of cash
  V2 Inverse-vol   : risk-parity weights within the book instead of equal weight
  V3 Asymmetric    : overlay near fully-invested in calm, hard de-risk only in stress (less cash)
  V4 Concentration : top decile / quartile / tercile
  V5 Combined      : asymmetric overlay + inverse-vol + defensive sleeve
Each reports CAGR / Vol / Sharpe / MaxDD / alpha(FF5+MOM) for full, IS and OOS, plus avg cash.
Output: bakeoff_variants.json + fig_bakeoff.png
"""
import json, warnings
from pathlib import Path
import numpy as np, pandas as pd
import statsmodels.api as sm
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
returns=prices[universe].pct_change()

# ---- engine ----
def rz(s,w=60,mp=24): return (s-s.rolling(w,min_periods=mp).mean())/s.rolling(w,min_periods=mp).std()
def build_score():
    idx=vix.index; c=pd.DataFrame(index=idx)
    c["vix"]=-rz(vix["VIX"])
    cred=np.log(macro_px["IEF"]).reindex(idx).ffill()-np.log(macro_px["HYG"]).reindex(idx).ffill()
    c["credit"]=-rz(cred.diff(12)); c["yield"]=-rz(macro_px["^TNX"].reindex(idx).ffill().diff(12))
    spx=macro_px["^GSPC"].reindex(idx).ffill(); c["trend"]=rz(np.log(spx).diff(1).shift(1).rolling(11).sum())
    return c.mean(axis=1).clip(-2,2).shift(1)
score=build_score()
gross_sym = np.clip(0.65+0.175*score,0.3,1.0)
gross_asym = pd.Series(np.where(score>=0, 0.90+0.10*np.clip(score,0,1), np.clip(0.90+0.45*score,0.20,0.90)), index=score.index)

def momentum(r,lb=12,sk=1): return np.log1p(r).shift(sk).rolling(lb-sk).sum()
def zscore_cs(p): return p.sub(p.mean(axis=1),axis=0).div(p.std(axis=1),axis=0)

# defensive sleeve return: equal-weight available of TLT/GLD each month, IEF then RF as fallback
dret=defv.pct_change(); ief_ret=macro_px["IEF"].pct_change()
defensive_ret=dret.mean(axis=1)            # mean skips NaN -> uses whatever is available

# factors / rf
def load_ff():
    ff5=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Research_Data_5_Factors_2x3_daily.CSV",skiprows=3,index_col=0)
    ff5.columns=[c.strip() for c in ff5.columns]; ff5.index=pd.to_datetime(ff5.index.astype(str),format="%Y%m%d"); ff5/=100.0
    mom=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Momentum_Factor_daily.CSV",skiprows=13,index_col=0,skipfooter=2,engine="python")
    mom.columns=["Mom"]; mom=mom.dropna(); mom.index=pd.to_datetime(mom.index.astype(str).str.strip(),format="%Y%m%d",errors="coerce"); mom=mom.dropna()/100.0
    m=(1+ff5.join(mom,how="inner")).resample("ME").prod()-1; m.index=me(m.index); return m
ff=load_ff(); rf=ff["RF"]
defensive_ret=defensive_ret.reindex(returns.index).fillna(ief_ret).fillna(rf)

def backtest(q=0.25, weighting="equal", gross=gross_sym, sleeve=rf, lb=12):
    sig=zscore_cs(momentum(returns,lb)); rk=sig.rank(axis=1,pct=True)
    mask=(rk>=1-q).astype(float)
    if weighting=="equal":
        w=mask.div(mask.sum(axis=1).replace(0,np.nan),axis=0)
    else:  # inverse-vol risk parity within the selected book
        vol=returns.rolling(12,min_periods=6).std(); iv=(1.0/vol).where(mask>0)
        w=iv.div(iv.sum(axis=1),axis=0)
    w=w.fillna(0)
    wL=w.mul(gross.reindex(w.index).ffill().clip(0,1),axis=0)
    R=returns.reindex_like(wL).fillna(0)
    port=(wL.shift(1).fillna(0)*R).sum(axis=1)
    cash=(1.0-wL.sum(axis=1)).clip(lower=0)
    port=port+cash.shift(1).fillna(0)*sleeve.reindex(wL.index).fillna(0)
    turn=(wL-wL.shift(1)).abs().sum(axis=1)
    return port-turn*(TC_BPS/10000.0), wL

def metrics(r):
    r=r.dropna(); cum=(1+r).cumprod(); cagr=cum.iloc[-1]**(12/len(r))-1; vol=r.std()*np.sqrt(12)
    ex=r-rf.reindex(r.index).fillna(0); sh=(ex.mean()*12)/(ex.std()*np.sqrt(12))
    dd=(cum/cum.cummax()-1).min()
    return {"CAGR":float(cagr),"Vol":float(vol),"Sharpe":float(sh),"MaxDD":float(dd)}
def alpha(r):
    cols=["Mkt-RF","SMB","HML","RMW","CMA","Mom"]
    d=pd.concat([(r-rf.reindex(r.index)).rename("y"),ff[cols]],axis=1).dropna()
    res=sm.OLS(d["y"],sm.add_constant(d[cols])).fit(cov_type="HAC",cov_kwds={"maxlags":6})
    return float(res.params["const"]*12), float(res.tvalues["const"])

VAR={
 "V0 Baseline (current)":      dict(q=0.25,weighting="equal", gross=gross_sym, sleeve=rf),
 "V1 Defensive sleeve":        dict(q=0.25,weighting="equal", gross=gross_sym, sleeve=defensive_ret),
 "V2 Inverse-vol weighting":   dict(q=0.25,weighting="invvol",gross=gross_sym, sleeve=rf),
 "V3 Asymmetric overlay":      dict(q=0.25,weighting="equal", gross=gross_asym,sleeve=rf),
 "V4a Concentration q=0.10":   dict(q=0.10,weighting="equal", gross=gross_sym, sleeve=rf),
 "V4b Concentration q=0.33":   dict(q=0.33,weighting="equal", gross=gross_sym, sleeve=rf),
 "V5 Combined (asym+iv+def)":  dict(q=0.25,weighting="invvol",gross=gross_asym,sleeve=defensive_ret),
}
results={}; curves={}
for name,kw in VAR.items():
    port,wL=backtest(**kw); r=port.loc[START:prices.index[-1]]
    a,at=alpha(r)
    avg_cash=float((1.0-wL.sum(axis=1)).clip(lower=0).loc[START:].mean())
    results[name]={"full":metrics(r),"is":metrics(port.loc[START:IS_END]),"oos":metrics(port.loc[OOS_START:]),
                   "alpha":a,"alpha_t":at,"avg_cash":avg_cash}
    curves[name]=(1+r).cumprod()
spy=bench["SPY"].pct_change().loc[START:prices.index[-1]]; results["S&P 500 (SPY)"]={"full":metrics(spy),"is":metrics(bench["SPY"].pct_change().loc[START:IS_END]),"oos":metrics(bench["SPY"].pct_change().loc[OOS_START:]),"alpha":None,"alpha_t":None,"avg_cash":0.0}
curves["S&P 500 (SPY)"]=(1+spy).cumprod()

# ---- report ----
print("="*108)
print("VARIANT BAKE-OFF — live monthly engine, 2002-2026, net 15bps (GROSS of fund fees)")
print("="*108)
print(f"{'Variant':30}{'CAGR':>7}{'Vol':>7}{'Sharpe':>8}{'MaxDD':>7}{'Alpha':>9}{'(t)':>6}{'IS Shp':>8}{'OOS Shp':>9}{'AvgCash':>9}")
for name,o in results.items():
    f=o["full"]; a=f"{o['alpha']*100:+.1f}%" if o["alpha"] is not None else "  —"; at=f"{o['alpha_t']:.1f}" if o["alpha_t"] is not None else " —"
    print(f"{name:30}{f['CAGR']*100:6.1f}%{f['Vol']*100:6.1f}%{f['Sharpe']:8.2f}{f['MaxDD']*100:6.0f}%{a:>9}{at:>6}{o['is']['Sharpe']:8.2f}{o['oos']['Sharpe']:9.2f}{o['avg_cash']*100:8.0f}%")

Path("bakeoff_variants.json").write_text(json.dumps({k:v for k,v in results.items()},indent=2,default=str))

fig,ax=plt.subplots(figsize=(12,6.5))
order=list(VAR.keys())+["S&P 500 (SPY)"]
cmap=plt.cm.viridis(np.linspace(0,0.85,len(VAR)))
for i,name in enumerate(order):
    c=curves[name]
    if name=="S&P 500 (SPY)": ax.plot(c.index,c.values,color="black",lw=1.3,ls="--",label=f"{name} ({results[name]['full']['CAGR']*100:.1f}%, SR {results[name]['full']['Sharpe']:.2f})")
    elif name=="V1 Defensive sleeve": ax.plot(c.index,c.values,color="crimson",lw=2.8,zorder=5,label=f"{name} ({results[name]['full']['CAGR']*100:.1f}%, SR {results[name]['full']['Sharpe']:.2f})")
    else: ax.plot(c.index,c.values,color=cmap[i],lw=1.5,label=f"{name} ({results[name]['full']['CAGR']*100:.1f}%, SR {results[name]['full']['Sharpe']:.2f})")
ax.set_yscale("log"); ax.set_title("Variant bake-off — growth of $1 (SIMULATED, monthly, net 15bps)")
ax.set_ylabel("Growth of $1 (log)"); ax.legend(fontsize=8,loc="upper left"); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig("fig_bakeoff.png",dpi=140)
print("\nSaved bakeoff_variants.json and fig_bakeoff.png")
