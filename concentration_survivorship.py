"""Does the concentration edge survive survivorship correction?
Runs the same quarterly engine at several concentration levels on TWO universes:
  A = survivorship-FREE (Bloomberg point-in-time members)
  B = survivors-only (recreates the bias)
If concentration's advantage is real it should persist in A; if it is a survivorship artifact
(concentrating into known survivors) it should shrink/vanish in A relative to B.
Output: concentration_survivorship.json
"""
import json, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
XLSX=Path(__file__).resolve().parent/"Total Returns Hard Copy.xlsx"
CACHE=Path("data_cache"); DATA_ROOT=Path(__file__).resolve().parent/"course_data"
START="2002-03-31"; IS_END="2015-12-31"; OOS_START="2016-03-31"; LB=4; PA=4
def me(idx): return pd.to_datetime(idx).to_period("M").to_timestamp("M")

# ---- point-in-time quarterly returns (calendar-corrected, as in survivorship_corrected.py) ----
raw=pd.read_excel(XLSX,sheet_name="Sheet1",header=None)
hdr=raw.iloc[0,1:].tolist(); names=raw.iloc[2:,0].astype(str).str.strip().tolist()
vals=raw.iloc[2:,1:].apply(pd.to_numeric,errors="coerce"); vals.index=names; vals.columns=hdr
def qend(l):
    l=str(l).strip()
    if l.startswith("Q"): return pd.Timestamp(int(l.split()[1]),int(l[1])*3,1)+pd.offsets.MonthEnd(0)
    return None
keep=[c for c in vals.columns if qend(c) is not None]
R=vals[keep].copy(); R.columns=[qend(c) for c in keep]; R=R.T.sort_index(); R=R[~R.index.duplicated()]
R.index=R.index+pd.offsets.QuarterEnd(1)

# ---- macro overlay (quarterly), rf, spy ----
vix=pd.read_csv(CACHE/"prices_vix_monthly.csv",index_col=0,parse_dates=True); vix.columns=["VIX"]; vix.index=me(vix.index)
mac=pd.read_csv(CACHE/"macro_proxies_monthly.csv",index_col=0,parse_dates=True); mac.index=me(mac.index)
bench=pd.read_csv(CACHE/"prices_benchmarks_monthly.csv",index_col=0,parse_dates=True); bench.index=me(bench.index)
def rz(s,w=60,mp=24): return (s-s.rolling(w,min_periods=mp).mean())/s.rolling(w,min_periods=mp).std()
idx=vix.index; c=pd.DataFrame(index=idx); c["vix"]=-rz(vix["VIX"])
cred=np.log(mac["IEF"]).reindex(idx).ffill()-np.log(mac["HYG"]).reindex(idx).ffill()
c["credit"]=-rz(cred.diff(12)); c["yield"]=-rz(mac["^TNX"].reindex(idx).ffill().diff(12))
spx=mac["^GSPC"].reindex(idx).ffill(); c["trend"]=rz(np.log(spx).diff(1).shift(1).rolling(11).sum())
score_m=c.mean(axis=1).clip(-2,2).shift(1); gross_q=np.clip(0.65+0.175*score_m,0.3,1.0).resample("QE").last()
def load_ff():
    ff5=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Research_Data_5_Factors_2x3_daily.CSV",skiprows=3,index_col=0)
    ff5.columns=[x.strip() for x in ff5.columns]; ff5.index=pd.to_datetime(ff5.index.astype(str),format="%Y%m%d"); ff5/=100.0
    return ff5
rf_q=(1+load_ff()["RF"]).resample("QE").prod()-1
spy_q=(1+bench["SPY"].pct_change()).resample("QE").prod()-1

def run(panel,q=None,n=None):
    dates=panel.index; prev=pd.Series(dtype=float); rets={}
    for i in range(LB,len(dates)-1):
        t,nxt=dates[i],dates[i+1]
        win=panel.iloc[i-LB+1:i+1]; valid=win.notna().all(axis=0)
        sig=(1+win).prod()[valid]
        if len(sig)<max((n or 0),20): continue
        z=(sig-sig.mean())/sig.std()
        sel=z.nlargest(n).index if n is not None else z[z>=z.quantile(1-q)].index
        g=float(gross_q.asof(t)) if pd.notna(gross_q.asof(t)) else 0.65
        w=pd.Series(g/len(sel),index=sel); r_next=panel.loc[nxt].reindex(sel); have=r_next.notna()
        port=float((w[have]*r_next[have]).sum())+ (1.0-float(w[have].sum()))*float(rf_q.get(nxt,0.0))
        rets[nxt]=port; prev=w
    return pd.Series(rets).sort_index()
def metrics(r):
    r=r.dropna(); cum=(1+r).cumprod(); cagr=cum.iloc[-1]**(PA/len(r))-1
    ex=r-rf_q.reindex(r.index).fillna(0); sh=(ex.mean()*PA)/(ex.std()*np.sqrt(PA)); dd=(cum/cum.cummax()-1).min()
    return {"CAGR":float(cagr),"Sharpe":float(sh),"MaxDD":float(dd),
            "OOS_Sharpe":float(((r.loc[OOS_START:]-rf_q.reindex(r.loc[OOS_START:].index).fillna(0)).mean()*PA)/((r.loc[OOS_START:]-rf_q.reindex(r.loc[OOS_START:].index).fillna(0)).std()*np.sqrt(PA)))}

survivors=R.columns[R.iloc[-1].notna()]
LEVELS=[("Top 25 names",dict(n=25)),("Top decile (~50)",dict(q=0.10)),
        ("Quartile (~125)",dict(q=0.25)),("Tercile (~165)",dict(q=0.33))]
out={"free":{},"biased":{}}
for lab,kw in LEVELS:
    out["free"][lab]=metrics(run(R,**kw).loc[START:])
    out["biased"][lab]=metrics(run(R[survivors],**kw).loc[START:])

def prem(d): return d["Top 25 names"]["Sharpe"]-d["Quartile (~125)"]["Sharpe"]
print("="*92)
print("DOES THE CONCENTRATION EDGE SURVIVE SURVIVORSHIP CORRECTION?  (quarterly, point-in-time)")
print("="*92)
for uni,title in [("biased","B · SURVIVORS-ONLY (biased)"),("free","A · SURVIVORSHIP-FREE")]:
    print(f"\n{title}")
    print(f"  {'Level':20}{'CAGR':>8}{'Sharpe':>8}{'MaxDD':>8}{'OOS Shp':>9}")
    for lab,_ in LEVELS:
        m=out[uni][lab]; print(f"  {lab:20}{m['CAGR']*100:7.1f}%{m['Sharpe']:8.2f}{m['MaxDD']*100:7.0f}%{m['OOS_Sharpe']:9.2f}")
    print(f"  -> Concentration premium (Top25 Sharpe - Quartile Sharpe): {prem(out[uni]):+.2f}")
print("\nIf the premium is large in B but small/negative in A, the concentration edge is mostly survivorship bias.")
Path("concentration_survivorship.json").write_text(json.dumps(out,indent=2,default=str))
print("Saved concentration_survivorship.json")
