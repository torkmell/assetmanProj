"""Second bake-off: selection-signal and exposure-scaling improvements, ALL layered on V1
(defensive sleeve). Live monthly engine, 2002-2026, net 15bps, GROSS of fund fees.

  V1 Defensive (reference)   : equal-weight top quartile, symmetric overlay, defensive sleeve
  W1 Risk-managed momentum   : cut equity exposure when the momentum book's realized vol spikes (Barroso 2015)
  W2 Volatility targeting    : scale the book to ~10% realized vol (Moreira-Muir 2017)
  W3 Defensive-momentum tilt : selection = momentum minus a low-beta tilt (BAB)
  W4 Quality-momentum (proxy): selection = momentum + price-based quality (low-vol + return-stability)
  W5 Combined (winners stacked)
Long-only, NO leverage (all exposure scales capped at 1.0). Reports full/IS/OOS + alpha + avg cash.
Output: bakeoff_improvements.json + fig_bakeoff_improvements.png
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
mkt=bench["SPY"].pct_change()

def rz(s,w=60,mp=24): return (s-s.rolling(w,min_periods=mp).mean())/s.rolling(w,min_periods=mp).std()
def build_score():
    idx=vix.index; c=pd.DataFrame(index=idx); c["vix"]=-rz(vix["VIX"])
    cred=np.log(macro_px["IEF"]).reindex(idx).ffill()-np.log(macro_px["HYG"]).reindex(idx).ffill()
    c["credit"]=-rz(cred.diff(12)); c["yield"]=-rz(macro_px["^TNX"].reindex(idx).ffill().diff(12))
    spx=macro_px["^GSPC"].reindex(idx).ffill(); c["trend"]=rz(np.log(spx).diff(1).shift(1).rolling(11).sum())
    return c.mean(axis=1).clip(-2,2).shift(1)
score=build_score(); gross_sym=np.clip(0.65+0.175*score,0.3,1.0)
def momentum(r,lb=12,sk=1): return np.log1p(r).shift(sk).rolling(lb-sk).sum()
def zcs(p): return p.sub(p.mean(axis=1),axis=0).div(p.std(axis=1),axis=0)

def load_ff():
    ff5=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Research_Data_5_Factors_2x3_daily.CSV",skiprows=3,index_col=0)
    ff5.columns=[c.strip() for c in ff5.columns]; ff5.index=pd.to_datetime(ff5.index.astype(str),format="%Y%m%d"); ff5/=100.0
    mom=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Momentum_Factor_daily.CSV",skiprows=13,index_col=0,skipfooter=2,engine="python")
    mom.columns=["Mom"]; mom=mom.dropna(); mom.index=pd.to_datetime(mom.index.astype(str).str.strip(),format="%Y%m%d",errors="coerce"); mom=mom.dropna()/100.0
    m=(1+ff5.join(mom,how="inner")).resample("ME").prod()-1; m.index=me(m.index); return m
ff=load_ff(); rf=ff["RF"]
dret=defv.pct_change(); ief_ret=macro_px["IEF"].pct_change()
defensive_ret=dret.mean(axis=1).reindex(returns.index).fillna(ief_ret).fillna(rf)

# ---- selection signals (all point-in-time) ----
mom_z = zcs(momentum(returns))
beta  = returns.rolling(36,min_periods=18).cov(mkt).div(mkt.rolling(36,min_periods=18).var(),axis=0)
vol12 = returns.rolling(12,min_periods=6).std()
consist = (returns>0).rolling(12,min_periods=6).mean()
quality_z = 0.5*zcs(-vol12) + 0.5*zcs(consist)          # price-based quality proxy
score_W3 = mom_z - 0.5*zcs(beta)                          # defensive-momentum tilt (favor low beta)
score_W4 = mom_z + quality_z                             # quality-momentum (proxy)
score_W5 = mom_z + 0.5*quality_z - 0.25*zcs(beta)        # combined selection

def book_weights(sel_score,q=0.25):
    rk=sel_score.rank(axis=1,pct=True); mask=(rk>=1-q).astype(float)
    return mask.div(mask.sum(axis=1).replace(0,np.nan),axis=0).fillna(0)

def run(sel_score=mom_z,q=0.25,gross=gross_sym,sleeve=defensive_ret,extra_scale=None):
    w=book_weights(sel_score,q)
    expo=gross.reindex(w.index).ffill().clip(0,1)
    if extra_scale is not None: expo=(expo*extra_scale.reindex(w.index).ffill()).clip(0,1)
    wL=w.mul(expo,axis=0)
    R=returns.reindex_like(wL).fillna(0)
    port=(wL.shift(1).fillna(0)*R).sum(axis=1)
    cash=(1.0-wL.sum(axis=1)).clip(lower=0)
    port=port+cash.shift(1).fillna(0)*sleeve.reindex(wL.index).fillna(0)
    turn=(wL-wL.shift(1)).abs().sum(axis=1)
    return port-turn*(TC_BPS/10000.0), wL

# exposure-scaling signals (two-pass; long-only so capped at 1.0 = no leverage)
book_full,_=run(mom_z,gross=pd.Series(1.0,index=score.index))          # full-invested momentum book
rv_book=book_full.rolling(6,min_periods=3).std()*np.sqrt(12)
rm_scale=np.clip(0.14/rv_book.shift(1),0.3,1.0)                          # risk-managed momentum
v1_port,_=run()                                                          # V1 baseline portfolio
rv_v1=v1_port.rolling(6,min_periods=3).std()*np.sqrt(12)
vt_scale=np.clip(0.10/rv_v1.shift(1),0.3,1.0)                            # vol targeting

def metrics(r):
    r=r.dropna(); cum=(1+r).cumprod(); cagr=cum.iloc[-1]**(12/len(r))-1; vol=r.std()*np.sqrt(12)
    ex=r-rf.reindex(r.index).fillna(0); sh=(ex.mean()*12)/(ex.std()*np.sqrt(12)); dd=(cum/cum.cummax()-1).min()
    return {"CAGR":float(cagr),"Vol":float(vol),"Sharpe":float(sh),"MaxDD":float(dd)}
def alpha(r):
    cols=["Mkt-RF","SMB","HML","RMW","CMA","Mom"]; d=pd.concat([(r-rf.reindex(r.index)).rename("y"),ff[cols]],axis=1).dropna()
    res=sm.OLS(d["y"],sm.add_constant(d[cols])).fit(cov_type="HAC",cov_kwds={"maxlags":6}); return float(res.params["const"]*12),float(res.tvalues["const"])

VAR={
 "V1 Defensive (reference)":   dict(sel_score=mom_z),
 "W1 Risk-managed momentum":   dict(sel_score=mom_z,  extra_scale=rm_scale),
 "W2 Volatility targeting":    dict(sel_score=mom_z,  extra_scale=vt_scale),
 "W3 Defensive-mom tilt":      dict(sel_score=score_W3),
 "W4 Quality-momentum (proxy)":dict(sel_score=score_W4),
 "W5 Combined (RM+qual+def)":  dict(sel_score=score_W5, extra_scale=rm_scale),
}
results={}; curves={}
for name,kw in VAR.items():
    port,wL=run(**kw); r=port.loc[START:prices.index[-1]]; a,at=alpha(r)
    avg_cash=float((1.0-wL.sum(axis=1)).clip(lower=0).loc[START:].mean())
    results[name]={"full":metrics(r),"is":metrics(port.loc[START:IS_END]),"oos":metrics(port.loc[OOS_START:]),"alpha":a,"alpha_t":at,"avg_cash":avg_cash}
    curves[name]=(1+r).cumprod()
spy=mkt.loc[START:prices.index[-1]]
results["S&P 500 (SPY)"]={"full":metrics(spy),"is":metrics(mkt.loc[START:IS_END]),"oos":metrics(mkt.loc[OOS_START:]),"alpha":None,"alpha_t":None,"avg_cash":0.0}; curves["S&P 500 (SPY)"]=(1+spy).cumprod()

print("="*112)
print("IMPROVEMENTS BAKE-OFF (all layered on V1 defensive sleeve) — monthly, 2002-2026, net 15bps")
print("="*112)
print(f"{'Variant':30}{'CAGR':>7}{'Vol':>7}{'Sharpe':>8}{'MaxDD':>7}{'Alpha':>9}{'(t)':>6}{'IS Shp':>8}{'OOS Shp':>9}{'AvgCash':>9}")
for name,o in results.items():
    f=o["full"]; a=f"{o['alpha']*100:+.1f}%" if o["alpha"] is not None else "  —"; at=f"{o['alpha_t']:.1f}" if o["alpha_t"] is not None else " —"
    print(f"{name:30}{f['CAGR']*100:6.1f}%{f['Vol']*100:6.1f}%{f['Sharpe']:8.2f}{f['MaxDD']*100:6.0f}%{a:>9}{at:>6}{o['is']['Sharpe']:8.2f}{o['oos']['Sharpe']:9.2f}{o['avg_cash']*100:8.0f}%")

Path("bakeoff_improvements.json").write_text(json.dumps(results,indent=2,default=str))
fig,ax=plt.subplots(figsize=(12,6.5))
cmap=plt.cm.plasma(np.linspace(0,0.8,len(VAR)))
for i,name in enumerate(list(VAR.keys())+["S&P 500 (SPY)"]):
    c=curves[name]
    if name=="S&P 500 (SPY)": ax.plot(c.index,c.values,color="black",lw=1.3,ls="--",label=f"{name} (SR {results[name]['full']['Sharpe']:.2f})")
    elif name.startswith("V1"): ax.plot(c.index,c.values,color="crimson",lw=2.4,label=f"{name} (SR {results[name]['full']['Sharpe']:.2f})")
    else: ax.plot(c.index,c.values,color=cmap[i],lw=1.5,label=f"{name} (SR {results[name]['full']['Sharpe']:.2f})")
ax.set_yscale("log"); ax.set_title("Improvements bake-off — growth of $1 (SIMULATED, monthly, net 15bps)")
ax.set_ylabel("Growth of $1 (log)"); ax.legend(fontsize=8,loc="upper left"); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig("fig_bakeoff_improvements.png",dpi=140)
print("\nSaved bakeoff_improvements.json and fig_bakeoff_improvements.png")
