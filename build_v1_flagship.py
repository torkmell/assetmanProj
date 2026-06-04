"""Compute the V1 (defensive-sleeve) flagship's full, self-consistent numbers for the pitch deck:
metrics (full/IS/OOS), factor alpha, equity curve, drawdowns, stress tests, turnover, avg cash,
and an investor net-of-fee track record (1% mgmt + 15% over SPY, relative high-water mark).
Output: v1_flagship.json
"""
import json, warnings
from pathlib import Path
import numpy as np, pandas as pd, statsmodels.api as sm
warnings.filterwarnings("ignore")
CACHE=Path("data_cache"); DATA_ROOT=Path(__file__).resolve().parent/"course_data"
TC_BPS=15; START="2002-01-31"; IS_END="2015-12-31"; OOS_START="2016-01-31"
MGMT=0.010; PERF=0.15
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

# ---- V1 backtest (equal-weight top quartile, macro overlay, defensive sleeve) ----
sig=zcs(momentum(returns)); rk=sig.rank(axis=1,pct=True); mask=(rk>=0.75).astype(float)
w=mask.div(mask.sum(axis=1).replace(0,np.nan),axis=0).fillna(0)
wL=w.mul(gross.reindex(w.index).ffill().clip(0,1),axis=0)
R=returns.reindex_like(wL).fillna(0)
port=(wL.shift(1).fillna(0)*R).sum(axis=1)
cashw=(1.0-wL.sum(axis=1)).clip(lower=0)
port=port+cashw.shift(1).fillna(0)*defensive_ret.reindex(wL.index).fillna(0)
turn=(wL-wL.shift(1)).abs().sum(axis=1); port=port-turn*(TC_BPS/10000.0)
END=prices.index[-1]; ret=port.loc[START:END]

def metrics(r):
    r=r.dropna(); cum=(1+r).cumprod(); cagr=cum.iloc[-1]**(12/len(r))-1; vol=r.std()*np.sqrt(12)
    ex=r-rf.reindex(r.index).fillna(0); sh=(ex.mean()*12)/(ex.std()*np.sqrt(12)); dd=(cum/cum.cummax()-1).min()
    dn=ex[ex<0].std()*np.sqrt(12); sortino=(ex.mean()*12)/dn if dn>0 else None
    return {"CAGR":float(cagr),"Vol":float(vol),"Sharpe":float(sh),"Sortino":float(sortino) if sortino else None,
            "MaxDD":float(dd),"Calmar":float(cagr/abs(dd)) if dd<0 else None,"HitRate":float((r>0).mean())}
prim=metrics(ret); ism=metrics(port.loc[START:IS_END]); oosm=metrics(port.loc[OOS_START:END])
cols=["Mkt-RF","SMB","HML","RMW","CMA","Mom"]
d=pd.concat([(ret-rf.reindex(ret.index)).rename("y"),ff[cols]],axis=1).dropna()
res=sm.OLS(d["y"],sm.add_constant(d[cols])).fit(cov_type="HAC",cov_kwds={"maxlags":6})

# stress windows
windows={"Dot-com (00-02)":("2000-09-30","2002-10-31"),"GFC (07-09)":("2007-10-31","2009-02-28"),
 "Euro (2011)":("2011-07-31","2011-09-30"),"China (15-16)":("2015-08-31","2016-02-29"),
 "Volmageddon (18)":("2018-10-31","2018-12-31"),"COVID (2020)":("2020-02-29","2020-04-30"),"2022 bear":("2021-12-31","2022-09-30")}
def tot(r,s,e): seg=r.loc[s:e].dropna(); return float((1+seg).prod()-1) if len(seg) else None
stress=[{"window":k,"fund":tot(ret,s,e),"spy":tot(spy,s,e)} for k,(s,e) in windows.items()]

# net-of-fee (1% mgmt monthly + 15% over SPY, relative HWM, annual crystallisation)
fund_cum=(1+ret).cumprod(); spy_seg=spy.loc[ret.index]
g=ret.copy(); b=spy_seg.copy(); df=pd.concat([g.rename("g"),b.rename("b")],axis=1).dropna()
m_month=MGMT/12.0; N=1.0;B=1.0;G=1.0;HWM=1.0; gnav=[];nnav=[];tot_m=0;tot_p=0
for dt,(gt,bt) in df.iterrows():
    G*=(1+gt); N*=(1+gt); mf=N*m_month; N-=mf; tot_m+=mf; B*=(1+bt); pf=0.0
    if dt.month==12 or dt==df.index[-1]:
        rel=N/B
        if rel>HWM: pf=PERF*(rel-HWM)*B; N-=pf; HWM=N/B; tot_p+=pf
    gnav.append(G); nnav.append(N)
gross_nav=pd.Series(gnav,index=df.index); net_nav=pd.Series(nnav,index=df.index)
def navmetrics(nav):
    r=nav.pct_change().dropna(); n=len(nav); cagr=nav.iloc[-1]**(12/n)-1; vol=r.std()*np.sqrt(12)
    ex=r-rf.reindex(r.index).fillna(0); sh=(ex.mean()*12)/(ex.std()*np.sqrt(12)); dd=(nav/nav.cummax()-1).min()
    return {"CAGR":float(cagr),"Vol":float(vol),"Sharpe":float(sh),"MaxDD":float(dd)}
mg=navmetrics(gross_nav); mn=navmetrics(net_nav); ms=metrics(spy_seg)

avg_cash=float(cashw.loc[START:END].mean()); avg_to=float(turn.loc[START:END].mean())
def pairs(s): return [[t.strftime("%Y-%m-%d"),float(v)] for t,v in s.dropna().items()]
out={
 "meta":{"strategy":"GSD2T Macro-Overlay Sector-Wide + Defensive Sleeve (V1)","window":f"{START[:7]} to {END:%Y-%m}",
   "universe":f"Full S&P 500 (~{len(universe)} names)","tc_bps":TC_BPS,
   "note":"SIMULATED, net of 15bps trading costs, GROSS of fund fees (except the net-of-fee block)."},
 "summary":{"Fund (full)":prim,"Fund IS (2002-2015)":ism,"Fund OOS (2016-2026)":oosm,"SPY":metrics(spy.loc[START:END])},
 "alpha":{"annualized":float(res.params["const"]*12),"tstat":float(res.tvalues["const"]),"rsquared":float(res.rsquared),
   "betas":{k:float(v) for k,v in res.params.drop("const").items()}},
 "equity_curves":{"Fund (V1)":pairs(fund_cum),"SPY":pairs((1+spy.loc[ret.index]).cumprod())},
 "drawdowns":{"Fund":pairs(fund_cum/fund_cum.cummax()-1),"SPY":pairs((1+spy.loc[ret.index]).cumprod()/(1+spy.loc[ret.index]).cumprod().cummax()-1)},
 "stress":stress,
 "net_of_fee":{"gross":mg,"net":mn,"spy":ms,"fee_drag_cagr":mg["CAGR"]-mn["CAGR"],"net_vs_spy":mn["CAGR"]-ms["CAGR"],
   "total_mgmt_per_dollar":float(tot_m),"total_perf_per_dollar":float(tot_p)},
 "ops":{"avg_cash":avg_cash,"avg_monthly_turnover":avg_to,"avg_annual_turnover":avg_to*12},
}
Path("v1_flagship.json").write_text(json.dumps(out,indent=2,default=str))
print("V1 FLAGSHIP — self-consistent numbers")
print(f"  CAGR {prim['CAGR']*100:.1f}%  Vol {prim['Vol']*100:.1f}%  Sharpe {prim['Sharpe']:.2f}  MaxDD {prim['MaxDD']*100:.0f}%")
print(f"  Alpha {res.params['const']*12*100:+.1f}% (t={res.tvalues['const']:.1f})  IS {ism['Sharpe']:.2f}  OOS {oosm['Sharpe']:.2f}")
print(f"  NET to investor: {mn['CAGR']*100:.1f}% CAGR (gross {mg['CAGR']*100:.1f}%, SPY {ms['CAGR']*100:.1f}%)  fee drag {(mg['CAGR']-mn['CAGR'])*100:.2f}%/yr")
print(f"  Avg cash {avg_cash*100:.0f}%  Ann. turnover {avg_to*12*100:.0f}%")
print("Saved v1_flagship.json")
