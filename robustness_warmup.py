"""(b) Re-run V1 requiring ALL FOUR overlay factors to be live before the dial activates
(default to the 65% neutral baseline while they phase in 2002-04), and compare headline numbers
to the current V1. (a) Also regenerate the exposure chart starting 2004 (artifact-free).
"""
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd, statsmodels.api as sm
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
CACHE=Path("data_cache"); DATA_ROOT=Path("course_data")
TC_BPS=15; START="2002-01-31"
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

score_now=c.mean(axis=1).clip(-2,2).shift(1)                              # current: averages whatever is live
score_str=c.mean(axis=1).where(c.notna().all(axis=1)).clip(-2,2).shift(1) # strict: requires ALL 4 live
gross_now=np.clip(0.65+0.175*score_now,0.3,1.0)
gross_str=np.clip(0.65+0.175*score_str.fillna(0.0),0.3,1.0)               # default 65% neutral while phasing in

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
defensive_ret=dret.mean(axis=1).reindex(returns.index).fillna(ief_ret).fillna(0.0)
sig=zcs(momentum(returns)); mask=(sig.rank(axis=1,pct=True)>=0.75).astype(float)
w=mask.div(mask.sum(axis=1).replace(0,np.nan),axis=0).fillna(0); R=returns.reindex_like(w).fillna(0)
def run(gross):
    wL=w.mul(gross.reindex(w.index).ffill().clip(0,1),axis=0)
    port=(wL.shift(1).fillna(0)*R).sum(axis=1)
    cashw=(1.0-wL.sum(axis=1)).clip(lower=0); port=port+cashw.shift(1).fillna(0)*defensive_ret.reindex(wL.index).fillna(0)
    turn=(wL-wL.shift(1)).abs().sum(axis=1); return port-turn*(TC_BPS/10000.0)
def metrics(r):
    r=r.dropna(); cum=(1+r).cumprod(); cagr=cum.iloc[-1]**(12/len(r))-1; vol=r.std()*np.sqrt(12)
    ex=r-rf.reindex(r.index).fillna(0); sh=(ex.mean()*12)/(ex.std()*np.sqrt(12)); dd=(cum/cum.cummax()-1).min()
    return cagr,vol,sh,dd
def alpha(r):
    cols=["Mkt-RF","SMB","HML","RMW","CMA","Mom"]; d=pd.concat([(r-rf.reindex(r.index)).rename("y"),ff[cols]],axis=1).dropna()
    res=sm.OLS(d["y"],sm.add_constant(d[cols])).fit(cov_type="HAC",cov_kwds={"maxlags":6}); return res.params["const"]*12,res.tvalues["const"]

print("="*84)
print("(b) WARM-UP CHECK — does requiring all 4 overlay factors change the headline numbers?")
print("="*84)
print(f"{'Version':40}{'CAGR':>8}{'Vol':>7}{'Sharpe':>8}{'MaxDD':>8}{'Alpha':>9}")
for lab,g,win in [("Current overlay (2002 start)",gross_now,START),
                  ("Strict: all-4-live (2002 start)",gross_str,START),
                  ("Current overlay (2004 start)",gross_now,"2004-01-31"),
                  ("Strict: all-4-live (2004 start)",gross_str,"2004-01-31")]:
    r=run(g).loc[win:prices.index[-1]]; cg,vol,sh,dd=metrics(r); a,at=alpha(r)
    print(f"{lab:40}{cg*100:7.1f}%{vol*100:6.1f}%{sh:8.2f}{dd*100:7.0f}%{a*100:+7.1f}% ")
print(f"\nMax exposure — current: {gross_now.loc[START:].max()*100:.0f}%  |  strict: {gross_str.loc[START:].max()*100:.0f}%  |  both from 2004: {gross_now.loc['2004':].max()*100:.0f}%")

# (a) regenerate exposure chart starting 2004 (current overlay; identical to strict from 2004)
g=gross_now.loc["2004-01-31":]*100
NAVY="#0B1F3A"; GREEN="#2E7D5B"; RED="#B83A3A"; FILL="#C9CDD6"
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":12})
fig,ax=plt.subplots(figsize=(7.8,4.3))
ax.fill_between(g.index,g.values,30,color=FILL,alpha=0.55,zorder=1)
ax.plot(g.index,g.values,color=NAVY,lw=1.9,zorder=3)
ax.axhline(100,color=GREEN,lw=1.3,ls=(0,(2,2)),zorder=2); ax.axhline(30,color=RED,lw=1.3,ls=(0,(2,2)),zorder=2)
ax.text(g.index[4],101.5,"Fully invested (calm)",color=GREEN,fontsize=11,fontweight="bold",va="bottom")
ax.text(g.index[4],31.5,"Floor 30% (max stress)",color=RED,fontsize=11,fontweight="bold",va="bottom")
ax.annotate("Gap to 100% = defensive sleeve\n(Treasuries + gold, not cash)",xy=(g.index[int(len(g)*0.30)],44),fontsize=9.5,color="#5A6F8C",ha="left",va="center",style="italic")
ax.set_ylabel("Equity exposure (%)",fontsize=12,color=NAVY); ax.set_ylim(26,104); ax.set_yticks([30,50,70,90,100])
for sp in ["top","right"]: ax.spines[sp].set_visible(False)
ax.grid(axis="y",alpha=0.18); fig.tight_layout(); fig.savefig("fig_exposure.png",dpi=160); plt.close(fig)
print(f"\n(a) Saved fig_exposure.png starting 2004 — max now {g.max():.0f}% (no warm-up artifact).")
