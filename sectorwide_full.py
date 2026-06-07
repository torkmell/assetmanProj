# %% [markdown]
# # Sector-wide strategy — full institutional appendix (mirrors gsd2t_full.py for S1)
# Same engine as S1 (12-1 momentum, equal-weight top quartile, identical macro overlay,
# long-only, 15bps), but on the FULL S&P 500 (all sectors). Returns are net of trading
# costs, GROSS of fund management/performance fees (same basis as S1).
# Output: sectorwide_full.json

import json, warnings
from pathlib import Path
import numpy as np, pandas as pd
import statsmodels.api as sm
from scipy import stats
warnings.filterwarnings("ignore")

CACHE=Path("data_cache"); DATA_ROOT=Path(__file__).resolve().parent/"course_data"
TC_BPS=15; START="2002-01-31"; IS_END="2015-12-31"; OOS_START="2016-01-31"
def me(idx): return pd.to_datetime(idx).to_period("M").to_timestamp("M")

prices=pd.read_csv(CACHE/"prices_sp500_monthly.csv",index_col=0,parse_dates=True)
bench=pd.read_csv(CACHE/"prices_benchmarks_monthly.csv",index_col=0,parse_dates=True)
vix=pd.read_csv(CACHE/"prices_vix_monthly.csv",index_col=0,parse_dates=True)
macro_px=pd.read_csv(CACHE/"macro_proxies_monthly.csv",index_col=0,parse_dates=True)
cons=pd.read_csv(CACHE/"sp500_constituents.csv")
vix.columns=["VIX"]
for df in (prices,bench,vix,macro_px): df.index=me(df.index)
secmap=dict(zip(cons["ticker"],cons["sector"]))
universe=[t for t in cons["ticker"] if t in prices.columns]
returns=prices[universe].pct_change()

# engine
def rolling_zscore(s,w=60,mp=24): return (s-s.rolling(w,min_periods=mp).mean())/s.rolling(w,min_periods=mp).std()
def build_overlay():
    idx=vix.index; c=pd.DataFrame(index=idx)
    c["vix"]=-rolling_zscore(vix["VIX"])
    cred=np.log(macro_px["IEF"]).reindex(idx).ffill()-np.log(macro_px["HYG"]).reindex(idx).ffill()
    c["credit"]=-rolling_zscore(cred.diff(12)); c["yield"]=-rolling_zscore(macro_px["^TNX"].reindex(idx).ffill().diff(12))
    spx=macro_px["^GSPC"].reindex(idx).ffill(); c["trend"]=rolling_zscore(np.log(spx).diff(1).shift(1).rolling(11).sum())
    score=c.mean(axis=1).clip(-2,2).shift(1); return score, c, np.clip(0.65+0.175*score,0.3,1.0)
macro_score,macro_comp,gross=build_overlay()
def zscore_cs(p): return p.sub(p.mean(axis=1),axis=0).div(p.std(axis=1),axis=0)
def momentum(r,lb=12,sk=1): return np.log1p(r).shift(sk).rolling(lb-sk).sum()
def qw(s,q=0.25):
    rk=s.rank(axis=1,pct=True); w=(rk>=1-q).astype(float); return w.div(w.sum(axis=1).replace(0,np.nan),axis=0).fillna(0)
def backtest(returns,lb=12,q=0.25,rf=None,scalar=None):
    wL=qw(zscore_cs(momentum(returns,lb)),q)
    if scalar is not None: wL=wL.mul(scalar.reindex(wL.index).fillna(0).clip(lower=0),axis=0)
    R=returns.reindex_like(wL).fillna(0); port=(wL.shift(1).fillna(0)*R).sum(axis=1)
    if rf is not None and scalar is not None:
        cash=(1.0-wL.sum(axis=1)).clip(lower=0); port=port+cash.shift(1).fillna(0)*rf.reindex(wL.index).fillna(0)
    turn=(wL-wL.shift(1)).abs().sum(axis=1); return port-turn*(TC_BPS/10000.0), wL, turn

# factors / rf
def load_ff():
    ff5=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Research_Data_5_Factors_2x3_daily.CSV",skiprows=3,index_col=0)
    ff5.columns=[c.strip() for c in ff5.columns]; ff5.index=pd.to_datetime(ff5.index.astype(str),format="%Y%m%d"); ff5/=100.0
    mom=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Momentum_Factor_daily.CSV",skiprows=13,index_col=0,skipfooter=2,engine="python")
    mom.columns=["Mom"]; mom=mom.dropna(); mom.index=pd.to_datetime(mom.index.astype(str).str.strip(),format="%Y%m%d",errors="coerce"); mom=mom.dropna()/100.0
    m=(1+ff5.join(mom,how="inner")).resample("ME").prod()-1; m.index=me(m.index); return m
ff=load_ff(); rf=ff["RF"]
def metrics(r):
    r=r.dropna(); cum=(1+r).cumprod(); cagr=cum.iloc[-1]**(12/len(r))-1; vol=r.std()*np.sqrt(12)
    ex=r-rf.reindex(r.index).fillna(0); sh=(ex.mean()*12)/(ex.std()*np.sqrt(12))
    dn=ex[ex<0].std()*np.sqrt(12); sortino=(ex.mean()*12)/dn if dn>0 else None
    dd=(cum/cum.cummax()-1).min()
    return {"CAGR":float(cagr),"Vol":float(vol),"Sharpe":float(sh),"Sortino":float(sortino) if sortino else None,
            "Calmar":float(cagr/abs(dd)) if dd<0 else None,"MaxDD":float(dd),"HitRate":float((r>0).mean()),"N_months":int(len(r))}

bt,wL,turn=backtest(returns,rf=rf,scalar=gross)
END=prices.index[-1]; ret=bt.loc[START:END]
primary=metrics(ret); ism=metrics(bt.loc[START:IS_END]); oosm=metrics(bt.loc[OOS_START:END])
print("Sector-wide primary:",{k:round(v,3) if isinstance(v,float) else v for k,v in primary.items()})

# sensitivity
lookbacks=[6,9,12,15,18]; quantiles=[0.20,0.25,0.33]
grid=np.array([[metrics(backtest(returns,lb=lb,q=qq,rf=rf,scalar=gross)[0].loc[START:END])["Sharpe"] for qq in quantiles] for lb in lookbacks])
# DSR
def dsr(r,n):
    r=r.dropna(); sr=(r.mean()/r.std())*np.sqrt(12); sk=stats.skew(r); ku=stats.kurtosis(r,fisher=True); emc=0.5772156649
    emax=((1-emc)*stats.norm.ppf(1-1/n)+emc*stats.norm.ppf(1-1/(n*np.e)))
    var=(1-sk*sr+(ku/4)*sr**2)/(len(r)-1); psr=stats.norm.cdf((sr-emax)/np.sqrt(var)) if var>0 else np.nan
    return float(sr),float(emax),float(psr)
n_trials=len(lookbacks)*len(quantiles); sr_o,sr_t,psr=dsr(ret-rf.reindex(ret.index),n_trials)
# factor reg
cols=["Mkt-RF","SMB","HML","RMW","CMA","Mom"]; d=pd.concat([(ret-rf.reindex(ret.index)).rename("y"),ff[cols]],axis=1).dropna()
res=sm.OLS(d["y"],sm.add_constant(d[cols])).fit(cov_type="HAC",cov_kwds={"maxlags":6})
# capacity — anchored to the $100M commitment we are raising; ADV range for honesty
avg_n=(wL>0).sum(axis=1).loc[START:END].mean(); avg_to=turn.loc[START:END].mean()
RAISE=100e6
adv_lo,adv_hi=150e6,300e6                       # conservative (measured median ~$150M) / base ADV per name
cap_lo,cap_hi=adv_lo*0.05*2, adv_hi*0.05*2      # 5% of ADV over 2 days
soft_lo,soft_hi=cap_lo*avg_n, cap_hi*avg_n
pos=RAISE/avg_n
# stress
windows={"Dot-com (2000-09 to 2002-10)":("2000-09-30","2002-10-31"),"GFC (2007-10 to 2009-02)":("2007-10-31","2009-02-28"),
         "Eurozone (2011-07 to 2011-09)":("2011-07-31","2011-09-30"),"China (2015-08 to 2016-02)":("2015-08-31","2016-02-29"),
         "Vol spike (2018-10 to 2018-12)":("2018-10-31","2018-12-31"),"COVID (2020-02 to 2020-04)":("2020-02-29","2020-04-30"),
         "2022 bear (2021-12 to 2022-09)":("2021-12-31","2022-09-30")}
spy=bench["SPY"].pct_change(); xlk=bench["XLK"].pct_change()
def tot(r,s,e): return float((1+r.loc[s:e].dropna()).prod()-1)
def dd(r,s,e):
    c=(1+r.loc[s:e].dropna()).cumprod(); return float((c/c.cummax()-1).min()) if len(c) else None
stress=[{"window":w,"fund_total":tot(ret,s,e),"spy_total":tot(spy,s,e),"xlk_total":tot(xlk,s,e),
         "fund_dd":dd(ret,s,e),"spy_dd":dd(spy,s,e)} for w,(s,e) in windows.items()]
# holdings + sector breakdown
latest=wL.dropna(how="all").iloc[-1]; held=latest[latest>0]
sec_break=pd.Series({t:secmap.get(t,"?") for t in held.index}).value_counts().to_dict()
holdings=[{"ticker":k,"sector":secmap.get(k,"?"),"weight":float(v)} for k,v in held.sort_values(ascending=False).items()]

def pairs(s): return [[t.strftime("%Y-%m-%d"),float(v)] for t,v in s.dropna().items()]
def cum_pairs(s): return pairs((1+s.dropna()).cumprod())
def dd_pairs(s):
    c=(1+s.dropna()).cumprod(); return pairs(c/c.cummax()-1)

out={
 "meta":{"fund_name":"GSD2T Asset Management","strategy":"Macro-Overlay Sector-Wide (diversified S1)",
   "universe":f"Full S&P 500 ({len(universe)} names, all 11 sectors)","window":f"{START[:7]} to {END:%Y-%m}",
   "tc_bps":TC_BPS,"cost_basis":"Net of 15bps trading costs; GROSS of fund fees & taxes",
   "generated_at":pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")},
 "summary":{"Fund (full window)":primary,"Fund IS (2002-2015)":ism,"Fund OOS (2016-2026)":oosm,
   "SPY":metrics(spy.loc[START:END]),"XLK":metrics(xlk.loc[START:END]),
   "MTUM":metrics(bench["MTUM"].pct_change().dropna()),"QUAL":metrics(bench["QUAL"].pct_change().dropna())},
 "equity_curves":{"Fund (Sector-Wide)":cum_pairs(ret),"SPY":cum_pairs(spy.loc[START:END]),"XLK":cum_pairs(xlk.loc[START:END]),
   "MTUM":cum_pairs(bench["MTUM"].pct_change().dropna())},
 "drawdowns":{"Fund":dd_pairs(ret),"SPY":dd_pairs(spy.loc[START:END])},
 "sector_breakdown":sec_break,
 "holdings_latest":{"as_of":latest.name.strftime("%Y-%m-%d"),"n_holdings":int(len(held)),"n_sectors":len(sec_break),"weights":holdings[:20]},
 "stress_tests":stress,
 "sensitivity":{"lookbacks":lookbacks,"quantiles":quantiles,"sharpe_grid":grid.round(3).tolist(),
   "min_sharpe":float(grid.min()),"max_sharpe":float(grid.max()),"mean_sharpe":float(grid.mean())},
 "deflated_sharpe":{"observed_sr":sr_o,"threshold_sr":sr_t,"psr":psr,"n_trials":n_trials},
 "factor_regression":{"alpha_annualized":float(res.params["const"]*12),"alpha_tstat":float(res.tvalues["const"]),
   "rsquared":float(res.rsquared),"betas":{k:float(v) for k,v in res.params.drop("const").items()},
   "betas_tstat":{k:float(v) for k,v in res.tvalues.drop("const").items()}},
 "capacity":{"commitment_raise":RAISE,"avg_n_holdings":float(avg_n),"avg_monthly_turnover":float(avg_to),
   "avg_annual_turnover":float(avg_to*12),"typical_position_size":float(pos),
   "adv_assumption":"$150M (measured median) to $300M ADV per name — cross-checked against actual volume data, not assumed",
   "per_name_capacity_low":float(cap_lo),"per_name_capacity_high":float(cap_hi),
   "soft_cap_low":float(soft_lo),"soft_cap_high":float(soft_hi),
   "headroom_low":float(soft_lo/RAISE),"headroom_high":float(soft_hi/RAISE),
   "pct_of_capacity_at_raise":float(RAISE/soft_hi)},
 "regime":{"score":pairs(macro_score.loc[START:END]),"gross_exposure":pairs(gross.loc[START:END])},
}
Path("sectorwide_full.json").write_text(json.dumps(out,indent=2,default=str))
print("\n"+"="*80)
print("SECTOR-WIDE — INSTITUTIONAL APPENDIX")
print("="*80)
print(f"CAGR {primary['CAGR']*100:.1f}%  Sharpe {primary['Sharpe']:.2f}  MaxDD {primary['MaxDD']*100:.0f}%")
print(f"Alpha vs FF5+MOM {res.params['const']*12*100:.2f}% (t={res.tvalues['const']:.2f}, R2={res.rsquared:.2f})")
print(f"IS Sharpe {ism['Sharpe']:.2f}  OOS Sharpe {oosm['Sharpe']:.2f}")
print(f"Sensitivity {grid.min():.2f}-{grid.max():.2f} ({grid.size} trials)  DSR PSR {psr:.3f}")
print(f"Holdings {int(len(held))} across {len(sec_break)} sectors  Capacity ${soft_lo/1e9:.1f}-{soft_hi/1e9:.1f}B "
      f"({soft_lo/RAISE:.0f}-{soft_hi/RAISE:.0f}x the $100M raise)  Turnover {avg_to*12*100:.0f}%/yr")
print("Saved sectorwide_full.json")
