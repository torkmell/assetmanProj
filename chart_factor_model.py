"""Column chart of the V1 factor regression (Fama-French 5 + Momentum): factor betas with t-stats,
alpha annotated. Also a return-attribution view. Output: fig_factor_model.png, fig_factor_attribution.png
"""
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd, statsmodels.api as sm
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
CACHE=Path("data_cache"); DATA_ROOT=Path(__file__).resolve().parent/"course_data"
TC_BPS=15; START="2002-01-31"
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
sig=zcs(momentum(returns)); rk=sig.rank(axis=1,pct=True); mask=(rk>=0.75).astype(float)
w=mask.div(mask.sum(axis=1).replace(0,np.nan),axis=0).fillna(0)
wL=w.mul(gross.reindex(w.index).ffill().clip(0,1),axis=0); R=returns.reindex_like(wL).fillna(0)
port=(wL.shift(1).fillna(0)*R).sum(axis=1)
cashw=(1.0-wL.sum(axis=1)).clip(lower=0); port=port+cashw.shift(1).fillna(0)*defensive_ret.reindex(wL.index).fillna(0)
turn=(wL-wL.shift(1)).abs().sum(axis=1); port=port-turn*(TC_BPS/10000.0)
ret=port.loc[START:prices.index[-1]]
cols=["Mkt-RF","SMB","HML","RMW","CMA","Mom"]
d=pd.concat([(ret-rf.reindex(ret.index)).rename("y"),ff[cols]],axis=1).dropna()
res=sm.OLS(d["y"],sm.add_constant(d[cols])).fit(cov_type="HAC",cov_kwds={"maxlags":6})
betas={k:res.params[k] for k in cols}; tvals={k:res.tvalues[k] for k in cols}
alpha=res.params["const"]*12; alpha_t=res.tvalues["const"]; r2=res.rsquared

NAVY="#0B1F3A"; GOLD="#C9A96E"; POS="#2E7D5B"; NEG="#B83A3A"; GREY="#5A6F8C"
labels={"Mkt-RF":"Market","SMB":"Size\n(SMB)","HML":"Value\n(HML)","RMW":"Profitability\n(RMW)","CMA":"Investment\n(CMA)","Mom":"Momentum"}

# ---- Chart 1: factor betas ----
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":12})
fig,ax=plt.subplots(figsize=(9.5,5.6))
xs=list(betas.keys()); ys=[betas[k] for k in xs]; colors=[POS if v>=0 else NEG for v in ys]
bars=ax.bar(range(len(xs)),ys,color=colors,edgecolor=NAVY,linewidth=0.8,width=0.62,zorder=3)
for i,k in enumerate(xs):
    v=betas[k]; off=0.03 if v>=0 else -0.03; va="bottom" if v>=0 else "top"
    ax.text(i,v+off,f"β={v:.2f}\n(t={tvals[k]:.1f})",ha="center",va=va,fontsize=9.5,color=NAVY,fontweight="bold")
ax.axhline(0,color="#333",lw=1)
ax.set_xticks(range(len(xs))); ax.set_xticklabels([labels[k] for k in xs],fontsize=10.5)
ax.set_ylabel("Factor exposure (β)",fontsize=12,color=NAVY)
ax.set_ylim(min(ys)-0.18, max(ys)+0.28)
ax.set_title("GSD²T factor exposures — Fama-French 5 + Momentum",fontsize=14,color=NAVY,fontweight="bold",pad=14)
ax.text(0.5,0.93,f"Alpha = +{alpha*100:.1f}% / yr  (t = {alpha_t:.1f}) · R² = {r2:.2f} · SIMULATED 2002–2026, Newey-West SEs",
        transform=ax.transAxes,ha="center",fontsize=10.5,color=GOLD,fontweight="bold")
for s in ["top","right"]: ax.spines[s].set_visible(False)
ax.grid(axis="y",alpha=0.25,zorder=0)
fig.tight_layout(); fig.savefig("fig_factor_model.png",dpi=160); plt.close(fig)
print(f"Saved fig_factor_model.png  (alpha +{alpha*100:.1f}%, t={alpha_t:.1f}, R2={r2:.2f})")
print("betas:",{k:round(v,2) for k,v in betas.items()})

# ---- Chart 2: return attribution (alpha as a column, in %/yr) ----
contrib={k:betas[k]*ff[k].reindex(d.index).mean()*12*100 for k in cols}
items=[("Alpha",alpha*100,GOLD)]+[(labels[k].replace("\n"," "),contrib[k],POS if contrib[k]>=0 else NEG) for k in cols]
fig,ax=plt.subplots(figsize=(9.5,5.6))
xs2=[it[0] for it in items]; ys2=[it[1] for it in items]; cs2=[it[2] for it in items]
ax.bar(range(len(xs2)),ys2,color=cs2,edgecolor=NAVY,linewidth=0.8,width=0.62,zorder=3)
for i,v in enumerate(ys2):
    ax.text(i,v+(0.15 if v>=0 else -0.15),f"{v:+.1f}%",ha="center",va="bottom" if v>=0 else "top",fontsize=10,color=NAVY,fontweight="bold")
ax.axhline(0,color="#333",lw=1)
ax.set_xticks(range(len(xs2))); ax.set_xticklabels(xs2,fontsize=9.5,rotation=15,ha="right")
ax.set_ylabel("Annualised return contribution (%)",fontsize=12,color=NAVY)
ax.set_title("Where the return comes from — alpha vs factor contributions",fontsize=14,color=NAVY,fontweight="bold",pad=12)
for s in ["top","right"]: ax.spines[s].set_visible(False)
ax.grid(axis="y",alpha=0.25,zorder=0)
fig.tight_layout(); fig.savefig("fig_factor_attribution.png",dpi=160); plt.close(fig)
print("Saved fig_factor_attribution.png")
