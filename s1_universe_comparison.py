# %% [markdown]
# # S1 engine — universe / structure comparison
# Run the SAME engine (12-1 momentum, equal-weight top quartile, same macro overlay)
# changing ONE thing at a time:
#   Baseline : S&P 500 Tech, long-only          (= the pitched S1)
#   (1)      : S&P 600 Small-cap, long-only      (down-cap, less efficient universe)
#   (2)      : S&P 500 Tech, LONG-SHORT          (add shorting to S1)
#   (3)      : S&P 500 all sectors, long-only    (sector-wide, not just tech)
# Everything else (signal, overlay, costs, window) is held fixed.

import io, urllib.request, warnings
from pathlib import Path
import numpy as np, pandas as pd
import statsmodels.api as sm
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")

CACHE = Path("data_cache"); DATA_ROOT = Path(__file__).resolve().parent / "course_data"
TC_BPS = 15; START = "2002-01-31"; OOS_START = "2019-01-31"
def me(idx): return pd.to_datetime(idx).to_period("M").to_timestamp("M")

# ----------------------------------------------------------------- data (cached)
prices  = pd.read_csv(CACHE/"prices_sp500_monthly.csv", index_col=0, parse_dates=True)
bench   = pd.read_csv(CACHE/"prices_benchmarks_monthly.csv", index_col=0, parse_dates=True)
vix     = pd.read_csv(CACHE/"prices_vix_monthly.csv", index_col=0, parse_dates=True)
macro_px= pd.read_csv(CACHE/"macro_proxies_monthly.csv", index_col=0, parse_dates=True)
cons    = pd.read_csv(CACHE/"sp500_constituents.csv")
vix.columns=["VIX"]
for df in (prices,bench,vix,macro_px): df.index = me(df.index)
secmap = dict(zip(cons["ticker"], cons["sector"]))

# ----------------------------------------------------------------- S&P 600 small-cap pull (Wikipedia + yfinance)
def get_sp600():
    p = CACHE/"sp600_constituents.csv"
    if p.exists(): return pd.read_csv(p)
    req = urllib.request.Request("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
                                 headers={"User-Agent":"Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=40).read().decode()
    df = pd.read_html(io.StringIO(html))[0]
    df = df[["Symbol","Security","GICS Sector"]].copy()
    df.columns = ["ticker","name","sector"]
    df["ticker"] = df["ticker"].str.replace(".","-",regex=False)
    df.to_csv(p, index=False); return df

def get_sp600_prices(tickers):
    p = CACHE/"prices_sp600_monthly.csv"
    if p.exists(): return pd.read_csv(p, index_col=0, parse_dates=True)
    import yfinance as yf
    raw = yf.download(tickers, start="2000-01-01", interval="1mo",
                      auto_adjust=True, progress=False, group_by="ticker")
    close = pd.DataFrame({t: raw[t]["Close"] for t in tickers if t in raw.columns.levels[0]})
    close = close.resample("ME").last(); close.to_csv(p); return close

sp600 = get_sp600()
sc_prices = get_sp600_prices(sp600["ticker"].tolist()); sc_prices.index = me(sc_prices.index)

# ----------------------------------------------------------------- S1 ENGINE (copied verbatim from strategy_one_full)
def rolling_zscore(s, w=60, mp=24): return (s - s.rolling(w,min_periods=mp).mean())/s.rolling(w,min_periods=mp).std()
def build_overlay():
    idx = vix.index; c = pd.DataFrame(index=idx)
    c["vix"] = -rolling_zscore(vix["VIX"])
    cred = np.log(macro_px["IEF"]).reindex(idx).ffill() - np.log(macro_px["HYG"]).reindex(idx).ffill()
    c["credit"] = -rolling_zscore(cred.diff(12))
    c["yield"]  = -rolling_zscore(macro_px["^TNX"].reindex(idx).ffill().diff(12))
    spx = macro_px["^GSPC"].reindex(idx).ffill()
    c["trend"]  = rolling_zscore(np.log(spx).diff(1).shift(1).rolling(11).sum())
    score = c.mean(axis=1).clip(-2,2).shift(1)
    return np.clip(0.65 + 0.175*score, 0.3, 1.0)
gross = build_overlay()

def zscore_cs(p): return p.sub(p.mean(axis=1),axis=0).div(p.std(axis=1),axis=0)
def momentum(returns): return np.log1p(returns).shift(1).rolling(11).sum()
def qw(scores, q=0.25, top=True):
    r = scores.rank(axis=1,pct=True); m = (r>=1-q) if top else (r<=q)
    w = m.astype(float); return w.div(w.sum(axis=1).replace(0,np.nan),axis=0).fillna(0)

def run(returns, mode="long_only", rf=None):
    mom = zscore_cs(momentum(returns))
    wL = qw(mom, top=True)
    wS = qw(mom, top=False) if mode=="long_short" else pd.DataFrame(0.0, index=wL.index, columns=wL.columns)
    g = gross.reindex(wL.index).fillna(0).clip(lower=0)
    wL = wL.mul(g,axis=0); wS = wS.mul(g,axis=0)
    w = wL - wS
    R = returns.reindex_like(w).fillna(0)
    port = (w.shift(1).fillna(0)*R).sum(axis=1)
    if mode=="long_only" and rf is not None:
        cash = (1.0 - wL.sum(axis=1)).clip(lower=0)
        port = port + cash.shift(1).fillna(0)*rf.reindex(w.index).fillna(0)
    tc = (w - w.shift(1)).abs().sum(axis=1)*(TC_BPS/10000.0)
    return (port - tc)

# ----------------------------------------------------------------- metrics + alpha
def load_ff():
    ff5 = pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Research_Data_5_Factors_2x3_daily.CSV", skiprows=3, index_col=0)
    ff5.columns=[c.strip() for c in ff5.columns]; ff5.index=pd.to_datetime(ff5.index.astype(str),format="%Y%m%d"); ff5/=100.0
    mom=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Momentum_Factor_daily.CSV",skiprows=13,index_col=0,skipfooter=2,engine="python")
    mom.columns=["Mom"]; mom=mom.dropna(); mom.index=pd.to_datetime(mom.index.astype(str).str.strip(),format="%Y%m%d",errors="coerce"); mom=mom.dropna()/100.0
    m=(1+ff5.join(mom,how="inner")).resample("ME").prod()-1; m.index=me(m.index); return m
ff = load_ff(); rf = ff["RF"]

def perf(r, lo=START, hi=None):
    r = r.loc[lo:hi].dropna()
    cum=(1+r).cumprod(); cagr=cum.iloc[-1]**(12/len(r))-1; vol=r.std()*np.sqrt(12)
    ex=r-rf.reindex(r.index).fillna(0); sh=(ex.mean()*12)/(ex.std()*np.sqrt(12))
    dd=(cum/cum.cummax()-1).min()
    cols=["Mkt-RF","SMB","HML","RMW","CMA","Mom"]
    d=pd.concat([ex.rename("y"),ff[cols]],axis=1).dropna()
    res=sm.OLS(d["y"],sm.add_constant(d[cols])).fit(cov_type="HAC",cov_kwds={"maxlags":6})
    return {"CAGR":cagr,"Vol":vol,"Sharpe":sh,"MaxDD":dd,"Calmar":cagr/abs(dd) if dd<0 else np.nan,
            "Alpha":res.params["const"]*12,"Alpha_t":res.tvalues["const"]}

# ----------------------------------------------------------------- build universes & run
tech  = [t for t in cons[cons["sector"]=="Information Technology"]["ticker"] if t in prices.columns]
broad = [t for t in cons["ticker"] if t in prices.columns]
small = [t for t in sc_prices.columns if sc_prices[t].notna().sum()>36]

ret_tech  = prices[tech].pct_change()
ret_broad = prices[broad].pct_change()
ret_small = sc_prices[small].pct_change()

strategies = {
    "S1 — Tech, long-only (PITCHED)":      run(ret_tech,  "long_only", rf),
    "(1) Small-cap 600, long-only":        run(ret_small, "long_only", rf),
    "(2) S1 + shorting (Tech, L/S)":       run(ret_tech,  "long_short"),
    "(3) Sector-wide S&P 500, long-only":  run(ret_broad, "long_only", rf),
}
spy = bench["SPY"].pct_change()

# ----------------------------------------------------------------- report
def fmt_row(name, r):
    m=perf(r); mo=perf(r, lo=OOS_START)
    return [name, f"{m['CAGR']*100:5.1f}%", f"{m['Vol']*100:4.1f}%", f"{m['Sharpe']:.2f}",
            f"{m['MaxDD']*100:5.0f}%", f"{m['Calmar']:.2f}", f"{m['Alpha']*100:+5.1f}% (t={m['Alpha_t']:.1f})",
            f"{mo['Sharpe']:.2f}"]
hdr=["Strategy","CAGR","Vol","Sharpe","MaxDD","Calmar","Alpha vs FF5+MOM","OOS Shrp"]
rows=[fmt_row(n,r) for n,r in strategies.items()]
m_spy=perf(spy); mo_spy=perf(spy,lo=OOS_START)
rows.append(["SPY (benchmark)", f"{m_spy['CAGR']*100:5.1f}%", f"{m_spy['Vol']*100:4.1f}%",
             f"{m_spy['Sharpe']:.2f}", f"{m_spy['MaxDD']*100:5.0f}%", f"{m_spy['Calmar']:.2f}",
             "—", f"{mo_spy['Sharpe']:.2f}"])
w=[max(len(str(r[i])) for r in [hdr]+rows) for i in range(len(hdr))]
print("\n"+"="*120)
print("S1 ENGINE — UNIVERSE / STRUCTURE COMPARISON  (same momentum + macro overlay, 2002-2026, net 15bps)")
print("="*120)
print("  ".join(str(hdr[i]).ljust(w[i]) for i in range(len(hdr))))
print("-"*120)
for r in rows: print("  ".join(str(r[i]).ljust(w[i]) for i in range(len(hdr))))
print(f"\nUniverse sizes: Tech={len(tech)}, Small-cap 600={len(small)}, Broad S&P500={len(broad)}")
print("Note: small-cap uses CURRENT S&P 600 (survivorship-dirty, quick test); L/S is dollar-neutral (loses equity premium).")

# ----------------------------------------------------------------- plot
fig,ax=plt.subplots(figsize=(12,6))
for n,r in strategies.items():
    c=(1+r.loc[START:].dropna()).cumprod(); ax.plot(c.index,c.values,label=n,lw=2 if "PITCHED" in n else 1.4)
cs=(1+spy.loc[START:].dropna()).cumprod(); ax.plot(cs.index,cs.values,label="SPY",color="black",lw=1.2,ls="--")
ax.set_yscale("log"); ax.set_title("S1 engine across universes & structures — growth of $1 (log, net of costs)")
ax.set_ylabel("Growth of $1"); ax.legend(fontsize=9); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig("fig_s1_universe_comparison.png",dpi=140)
print("\nSaved fig_s1_universe_comparison.png")
