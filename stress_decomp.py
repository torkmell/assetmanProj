"""Decompose each crisis window for V1: did the protection hold, and WHERE did it come from —
the overlay (cutting equity) or the defensive sleeve (bonds+gold)? Focus on whether the recent,
more-correlated drawdowns (2018/2020/2022) break the edge.
"""
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
CACHE=Path("data_cache")
def me(idx): return pd.to_datetime(idx).to_period("M").to_timestamp("M")
prices=pd.read_csv(CACHE/"prices_sp500_monthly.csv",index_col=0,parse_dates=True)
bench=pd.read_csv(CACHE/"prices_benchmarks_monthly.csv",index_col=0,parse_dates=True)
vix=pd.read_csv(CACHE/"prices_vix_monthly.csv",index_col=0,parse_dates=True); vix.columns=["VIX"]
macro_px=pd.read_csv(CACHE/"macro_proxies_monthly.csv",index_col=0,parse_dates=True)
cons=pd.read_csv(CACHE/"sp500_constituents.csv")
defv=pd.read_csv(CACHE/"defensive_monthly.csv",index_col=0,parse_dates=True)
for df in (prices,bench,vix,macro_px,defv): df.index=me(df.index)
universe=[t for t in cons["ticker"] if t in prices.columns]; returns=prices[universe].pct_change(); spy=bench["SPY"].pct_change()
def rz(s,w=60,mp=24): return (s-s.rolling(w,min_periods=mp).mean())/s.rolling(w,min_periods=mp).std()
idx=vix.index; c=pd.DataFrame(index=idx); c["vix"]=-rz(vix["VIX"])
cred=np.log(macro_px["IEF"]).reindex(idx).ffill()-np.log(macro_px["HYG"]).reindex(idx).ffill()
c["credit"]=-rz(cred.diff(12)); c["yield"]=-rz(macro_px["^TNX"].reindex(idx).ffill().diff(12))
spx=macro_px["^GSPC"].reindex(idx).ffill(); c["trend"]=rz(np.log(spx).diff(1).shift(1).rolling(11).sum())
score=c.mean(axis=1).clip(-2,2).shift(1); gross=np.clip(0.65+0.175*score,0.3,1.0)
def momentum(r,lb=12,sk=1): return np.log1p(r).shift(sk).rolling(lb-sk).sum()
def zcs(p): return p.sub(p.mean(axis=1),axis=0).div(p.std(axis=1),axis=0)
ief_ret=macro_px["IEF"].pct_change(); dret=defv.pct_change()
defensive_ret=dret.mean(axis=1).reindex(returns.index).fillna(ief_ret).fillna(rz(macro_px["IEF"]).reindex(returns.index)*0)
defensive_ret=dret.mean(axis=1).reindex(returns.index).fillna(ief_ret).fillna(0.0)
sig=zcs(momentum(returns)); rk=sig.rank(axis=1,pct=True); mask=(rk>=0.75).astype(float)
w=mask.div(mask.sum(axis=1).replace(0,np.nan),axis=0).fillna(0)
wL=w.mul(gross.reindex(w.index).ffill().clip(0,1),axis=0); R=returns.reindex_like(wL).fillna(0)
equity_leg=(wL.shift(1).fillna(0)*R).sum(axis=1)            # return from the held stocks
cashw=(1.0-wL.sum(axis=1)).clip(lower=0)
sleeve_leg=cashw.shift(1).fillna(0)*defensive_ret.reindex(wL.index).fillna(0)  # return from the bonds+gold sleeve
turn=(wL-wL.shift(1)).abs().sum(axis=1)
port=equity_leg+sleeve_leg-turn*(15/10000.0)
expo=wL.sum(axis=1)                                          # realised equity exposure

windows={"Dot-com 00-02":("2000-09-30","2002-10-31"),"GFC 07-09":("2007-10-31","2009-02-28"),
 "Euro 2011":("2011-07-31","2011-09-30"),"China 15-16":("2015-08-31","2016-02-29"),
 "Vol-spike 2018":("2018-10-31","2018-12-31"),"COVID 2020":("2020-02-29","2020-04-30"),"2022 bear":("2021-12-31","2022-09-30")}
def tot(s,a,b): seg=s.loc[a:b].dropna(); return float((1+seg).prod()-1) if len(seg) else np.nan

print("="*104)
print("CRISIS DECOMPOSITION — where the protection comes from (V1, SIMULATED)")
print("="*104)
print(f"{'Window':16}{'Fund':>8}{'SPY':>8}{'Protect':>9}{'AvgEqExp':>9}{'EquityLeg':>10}{'SleeveLeg':>10}{'Stk-Bond corr':>14}")
for nm,(a,b) in windows.items():
    f=tot(port,a,b); s=tot(spy,a,b); el=tot(equity_leg,a,b); sl=tot(sleeve_leg,a,b)
    ae=expo.loc[a:b].mean()
    # stock-bond correlation in the window (SPY monthly vs defensive sleeve monthly)
    seg=pd.concat([spy.loc[a:b],defensive_ret.loc[a:b]],axis=1).dropna(); corr=seg.iloc[:,0].corr(seg.iloc[:,1]) if len(seg)>2 else np.nan
    print(f"{nm:16}{f*100:7.1f}%{s*100:7.1f}%{(f-s)*100:+8.1f}%{ae*100:8.0f}%{el*100:9.1f}%{sl*100:9.1f}%{corr:>13.2f}")
print("\nProtect = Fund total minus SPY total (positive = we lost less / gained more).")
print("EquityLeg = return from held stocks; SleeveLeg = return from bonds+gold sleeve.")
print("Stk-Bond corr = SPY vs defensive-sleeve monthly correlation in that window (high = the hedge is failing).")
