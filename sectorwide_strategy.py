# %% [markdown]
# # Sector-wide strategy (the diversified S1) + Dow Jones generalisation test
# Same engine as S1 (12-1 momentum, equal-weight top quartile, identical macro overlay,
# long-only, 15bps). Universes:
#   Tech (baseline S1) · Sector-wide S&P 500 (new flagship) · Dow Jones 30 (generalisation)
# Reports full / in-sample / out-of-sample, alpha vs FF5+MOM, stress tests, and the
# current sector diversification of the broad book.

import io, urllib.request, warnings
from pathlib import Path
import numpy as np, pandas as pd
import statsmodels.api as sm
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")

CACHE = Path("data_cache"); DATA_ROOT = Path(__file__).resolve().parent / "course_data"
TC_BPS = 15; START = "2002-01-31"; IS_END = "2018-12-31"; OOS_START = "2019-01-31"
def me(idx): return pd.to_datetime(idx).to_period("M").to_timestamp("M")

# ----------------------------------------------------------------- cached data
prices  = pd.read_csv(CACHE/"prices_sp500_monthly.csv", index_col=0, parse_dates=True)
bench   = pd.read_csv(CACHE/"prices_benchmarks_monthly.csv", index_col=0, parse_dates=True)
vix     = pd.read_csv(CACHE/"prices_vix_monthly.csv", index_col=0, parse_dates=True)
macro_px= pd.read_csv(CACHE/"macro_proxies_monthly.csv", index_col=0, parse_dates=True)
cons    = pd.read_csv(CACHE/"sp500_constituents.csv")
vix.columns=["VIX"]
for df in (prices,bench,vix,macro_px): df.index = me(df.index)
secmap = dict(zip(cons["ticker"], cons["sector"]))

# ----------------------------------------------------------------- Dow Jones 30 (Wikipedia) + prices
def get_dow():
    p = CACHE/"dow_constituents.csv"
    if p.exists(): return pd.read_csv(p)["ticker"].tolist()
    req = urllib.request.Request("https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
                                 headers={"User-Agent":"Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=40).read().decode()
    tabs = pd.read_html(io.StringIO(html))
    comp = next(t for t in tabs if any("Symbol" in str(c) for c in t.columns))
    symcol = [c for c in comp.columns if "Symbol" in str(c)][0]
    tickers = [str(s).split(":")[-1].strip().replace(".","-") for s in comp[symcol]]
    pd.DataFrame({"ticker":tickers}).to_csv(p, index=False)
    return tickers

dow = get_dow()
have = [t for t in dow if t in prices.columns]
missing = [t for t in dow if t not in prices.columns]
if missing:
    dp = CACHE/"prices_dow_extra_monthly.csv"
    if dp.exists():
        extra = pd.read_csv(dp, index_col=0, parse_dates=True)
    else:
        import yfinance as yf
        raw = yf.download(missing, start="2000-01-01", interval="1mo", auto_adjust=True, progress=False, group_by="ticker")
        extra = pd.DataFrame({t: raw[t]["Close"] for t in missing if t in raw.columns.levels[0]})
        extra = extra.resample("ME").last(); extra.to_csv(dp)
    extra.index = me(extra.index)
    dow_prices = pd.concat([prices[have], extra.reindex(prices.index)], axis=1)
else:
    dow_prices = prices[have]
dow_tickers = [t for t in dow if t in dow_prices.columns]

# ----------------------------------------------------------------- engine (same as S1)
def rolling_zscore(s,w=60,mp=24): return (s-s.rolling(w,min_periods=mp).mean())/s.rolling(w,min_periods=mp).std()
def build_overlay():
    idx=vix.index; c=pd.DataFrame(index=idx)
    c["vix"]=-rolling_zscore(vix["VIX"])
    cred=np.log(macro_px["IEF"]).reindex(idx).ffill()-np.log(macro_px["HYG"]).reindex(idx).ffill()
    c["credit"]=-rolling_zscore(cred.diff(12))
    c["yield"]=-rolling_zscore(macro_px["^TNX"].reindex(idx).ffill().diff(12))
    spx=macro_px["^GSPC"].reindex(idx).ffill()
    c["trend"]=rolling_zscore(np.log(spx).diff(1).shift(1).rolling(11).sum())
    return np.clip(0.65+0.175*c.mean(axis=1).clip(-2,2).shift(1),0.3,1.0)
gross=build_overlay()
def zscore_cs(p): return p.sub(p.mean(axis=1),axis=0).div(p.std(axis=1),axis=0)
def momentum(r): return np.log1p(r).shift(1).rolling(11).sum()
def qw(s,q=0.25):
    rk=s.rank(axis=1,pct=True); w=(rk>=1-q).astype(float); return w.div(w.sum(axis=1).replace(0,np.nan),axis=0).fillna(0)
def run(returns, rf):
    wL=qw(zscore_cs(momentum(returns))); g=gross.reindex(wL.index).fillna(0).clip(lower=0); wL=wL.mul(g,axis=0)
    R=returns.reindex_like(wL).fillna(0); port=(wL.shift(1).fillna(0)*R).sum(axis=1)
    cash=(1.0-wL.sum(axis=1)).clip(lower=0); port=port+cash.shift(1).fillna(0)*rf.reindex(wL.index).fillna(0)
    tc=(wL-wL.shift(1)).abs().sum(axis=1)*(TC_BPS/10000.0)
    return port-tc, wL

# ----------------------------------------------------------------- factors / metrics
def load_ff():
    ff5=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Research_Data_5_Factors_2x3_daily.CSV",skiprows=3,index_col=0)
    ff5.columns=[c.strip() for c in ff5.columns]; ff5.index=pd.to_datetime(ff5.index.astype(str),format="%Y%m%d"); ff5/=100.0
    mom=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Momentum_Factor_daily.CSV",skiprows=13,index_col=0,skipfooter=2,engine="python")
    mom.columns=["Mom"]; mom=mom.dropna(); mom.index=pd.to_datetime(mom.index.astype(str).str.strip(),format="%Y%m%d",errors="coerce"); mom=mom.dropna()/100.0
    m=(1+ff5.join(mom,how="inner")).resample("ME").prod()-1; m.index=me(m.index); return m
ff=load_ff(); rf=ff["RF"]
def perf(r, lo=START, hi=None):
    r=r.loc[lo:hi].dropna()
    if len(r)<12: return {k:np.nan for k in ["CAGR","Vol","Sharpe","MaxDD","Calmar","Alpha","Alpha_t"]}
    cum=(1+r).cumprod(); cagr=cum.iloc[-1]**(12/len(r))-1; vol=r.std()*np.sqrt(12)
    ex=r-rf.reindex(r.index).fillna(0); sh=(ex.mean()*12)/(ex.std()*np.sqrt(12)); dd=(cum/cum.cummax()-1).min()
    cols=["Mkt-RF","SMB","HML","RMW","CMA","Mom"]; d=pd.concat([ex.rename("y"),ff[cols]],axis=1).dropna()
    res=sm.OLS(d["y"],sm.add_constant(d[cols])).fit(cov_type="HAC",cov_kwds={"maxlags":6})
    return {"CAGR":cagr,"Vol":vol,"Sharpe":sh,"MaxDD":dd,"Calmar":cagr/abs(dd) if dd<0 else np.nan,
            "Alpha":res.params["const"]*12,"Alpha_t":res.tvalues["const"]}

# ----------------------------------------------------------------- universes & runs
tech=[t for t in cons[cons["sector"]=="Information Technology"]["ticker"] if t in prices.columns]
broad=[t for t in cons["ticker"] if t in prices.columns]
r_tech,_=run(prices[tech].pct_change(),rf)
r_broad,wL_broad=run(prices[broad].pct_change(),rf)
r_dow,_=run(dow_prices[dow_tickers].pct_change(),rf)
spy=bench["SPY"].pct_change()
runs={"Tech (S1 baseline)":r_tech,"Sector-wide S&P 500":r_broad,"Dow Jones 30":r_dow,"SPY":spy}

# ----------------------------------------------------------------- report tables
def table(title, window_lo, window_hi):
    print("\n"+"="*112+f"\n{title}\n"+"-"*112)
    print(f"{'Strategy':24s}{'CAGR':>8}{'Vol':>7}{'Sharpe':>8}{'MaxDD':>8}{'Calmar':>8}{'Alpha (FF5+MOM)':>22}")
    for n,r in runs.items():
        m=perf(r,window_lo,window_hi)
        a = "—" if n=="SPY" else f"{m['Alpha']*100:+.1f}% (t={m['Alpha_t']:.1f})"
        print(f"{n:24s}{m['CAGR']*100:7.1f}%{m['Vol']*100:6.1f}%{m['Sharpe']:8.2f}{m['MaxDD']*100:7.0f}%{m['Calmar']:8.2f}{a:>22}")

print(f"Universe sizes: Tech={len(tech)}, Sector-wide={len(broad)}, Dow Jones={len(dow_tickers)}")
table("FULL SAMPLE 2002-2026", START, None)
table("IN-SAMPLE 2002-2018", START, IS_END)
table("OUT-OF-SAMPLE 2019-2026", OOS_START, None)

# ----------------------------------------------------------------- stress tests (sector-wide flagship vs SPY)
windows={"Dot-com (2000-2002)":("2000-09-30","2002-10-31"),"GFC (2007-2009)":("2007-10-31","2009-02-28"),
         "Vol spike 2018":("2018-10-31","2018-12-31"),"COVID 2020":("2020-02-29","2020-04-30"),
         "2022 bear":("2021-12-31","2022-09-30")}
print("\n"+"="*112+"\nSTRESS TESTS — Sector-wide vs SPY (total return through each crisis)\n"+"-"*112)
print(f"{'Window':22s}{'Sector-wide':>14}{'SPY':>10}")
for w,(s,e) in windows.items():
    sw=(1+r_broad.loc[s:e].dropna()).prod()-1; sp=(1+spy.loc[s:e].dropna()).prod()-1
    print(f"{w:22s}{sw*100:13.1f}%{sp*100:9.1f}%")

# ----------------------------------------------------------------- diversification of the broad book NOW
latest=wL_broad.dropna(how="all").iloc[-1]; held=latest[latest>0]
secs=pd.Series({t:secmap.get(t,"?") for t in held.index}).value_counts()
print("\n"+"="*112+f"\nSECTOR-WIDE current book: {len(held)} stocks across {secs.size} sectors (diversified, not a tech bet)\n"+"-"*112)
print(secs.to_string())

# ----------------------------------------------------------------- plot
fig,ax=plt.subplots(figsize=(12,6))
for n,r in runs.items():
    c=(1+r.loc[START:].dropna()).cumprod()
    style=dict(lw=2.2,color="tab:red") if n=="Sector-wide S&P 500" else (dict(lw=1.2,ls="--",color="black") if n=="SPY" else dict(lw=1.3))
    ax.plot(c.index,c.values,label=n,**style)
ax.set_yscale("log"); ax.set_title("Sector-wide flagship vs Tech vs Dow Jones vs SPY — growth of $1 (log, net)")
ax.set_ylabel("Growth of $1"); ax.legend(fontsize=9); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig("fig_sectorwide.png",dpi=140)
print("\nSaved fig_sectorwide.png")
