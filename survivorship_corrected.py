"""Survivorship-corrected backtest on the Bloomberg point-in-time S&P 500 universe.

Input: 'Total Returns Hard Copy.xlsx' — 1,085 companies (full historical S&P 500,
incl. names that have since left), QUARTERLY total returns, Q1 2000 - Q2 2026.
Membership is point-in-time: a name has a return only for quarters it was a member,
so each quarter's universe = the ~500 names with a value that quarter.

We run the SAME quarterly engine on two universes:
  (A) SURVIVORSHIP-FREE  : point-in-time members each quarter (the honest test)
  (B) SURVIVORS-ONLY     : only names still in the index at the end (recreates the bias)
The gap between A and B is the survivorship bias, on identical data and frequency.

Engine (quarterly analog of the live monthly engine):
  - momentum = trailing 4-quarter total return (12m), 1-quarter implementation gap
  - cross-sectional z-score, equal-weight top quartile (q=0.25)
  - 4-factor macro overlay scales gross exposure 30-100%, rest in cash at RF
  - long-only, quarterly rebalance, 15 bps round-trip trading cost
Output: survivorship_corrected.json + fig_survivorship_corrected.png
"""
import json, warnings
from pathlib import Path
import numpy as np, pandas as pd
import statsmodels.api as sm
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
warnings.filterwarnings("ignore")

XLSX = Path(__file__).resolve().parent / "Total Returns Hard Copy.xlsx"   # bundled in the project
CACHE = Path("data_cache"); DATA_ROOT = Path(__file__).resolve().parent/"course_data"
TC_BPS = 15; Q = 0.25; LB = 4               # 4-quarter momentum
START = "2002-03-31"; IS_END = "2015-12-31"; OOS_START = "2016-03-31"
PA = 4                                       # periods per year (quarterly)

# ---------- 1. load the point-in-time quarterly returns ----------
raw = pd.read_excel(XLSX, sheet_name="Sheet1", header=None)
hdr = raw.iloc[0, 1:].tolist()
names = raw.iloc[2:, 0].astype(str).str.strip().tolist()
vals = raw.iloc[2:, 1:].apply(pd.to_numeric, errors="coerce")
vals.index = names; vals.columns = hdr

def qend(label):
    label = str(label).strip()
    if label.startswith("Q"):
        q = int(label[1]); y = int(label.split()[1])
        return pd.Timestamp(y, q*3, 1) + pd.offsets.MonthEnd(0)
    return None                              # drop non-quarter stub cols (e.g. 'Jan 2000')
cols = {c: qend(c) for c in vals.columns}
keep = [c for c, d in cols.items() if d is not None]
R = vals[keep].copy(); R.columns = [cols[c] for c in keep]
R = R.T.sort_index()                          # rows = quarter-end dates (asc), cols = names
R = R[~R.index.duplicated()]
# Calendar fix: Bloomberg stamps each L3M total return one quarter early relative to the
# benchmark/factor calendar (verified empirically: equal-weight universe vs SPY correlation
# jumps from 0.06 to 0.84 only under a +1 quarter shift; it also aligns delisting dates, e.g.
# Tiffany's last return -> Q4 2020 vs the Jan-2021 acquisition close). Shift one quarter forward.
R.index = R.index + pd.offsets.QuarterEnd(1)
print(f"Loaded {R.shape[1]} names x {R.shape[0]} quarters ({R.index.min():%Y-%m} to {R.index.max():%Y-%m})")

# ---------- 2. macro overlay (monthly engine, resampled to quarterly) ----------
def me(idx): return pd.to_datetime(idx).to_period("M").to_timestamp("M")
vix = pd.read_csv(CACHE/"prices_vix_monthly.csv", index_col=0, parse_dates=True); vix.columns=["VIX"]; vix.index=me(vix.index)
mac = pd.read_csv(CACHE/"macro_proxies_monthly.csv", index_col=0, parse_dates=True); mac.index=me(mac.index)
bench = pd.read_csv(CACHE/"prices_benchmarks_monthly.csv", index_col=0, parse_dates=True); bench.index=me(bench.index)
def rz(s, w=60, mp=24): return (s-s.rolling(w,min_periods=mp).mean())/s.rolling(w,min_periods=mp).std()
idx = vix.index; c = pd.DataFrame(index=idx)
c["vix"] = -rz(vix["VIX"])
cred = np.log(mac["IEF"]).reindex(idx).ffill() - np.log(mac["HYG"]).reindex(idx).ffill()
c["credit"] = -rz(cred.diff(12)); c["yield"] = -rz(mac["^TNX"].reindex(idx).ffill().diff(12))
spx = mac["^GSPC"].reindex(idx).ffill(); c["trend"] = rz(np.log(spx).diff(1).shift(1).rolling(11).sum())
score_m = c.mean(axis=1).clip(-2, 2).shift(1)
gross_m = np.clip(0.65 + 0.175*score_m, 0.3, 1.0)
gross_q = gross_m.resample("QE").last()       # exposure known at each quarter close
score_q = score_m.resample("QE").last()

# ---------- 3. risk-free + factors (monthly Ken French -> quarterly) ----------
def load_ff():
    ff5=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Research_Data_5_Factors_2x3_daily.CSV",skiprows=3,index_col=0)
    ff5.columns=[x.strip() for x in ff5.columns]; ff5.index=pd.to_datetime(ff5.index.astype(str),format="%Y%m%d"); ff5/=100.0
    mom=pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Momentum_Factor_daily.CSV",skiprows=13,index_col=0,skipfooter=2,engine="python")
    mom.columns=["Mom"]; mom=mom.dropna(); mom.index=pd.to_datetime(mom.index.astype(str).str.strip(),format="%Y%m%d",errors="coerce"); mom=mom.dropna()/100.0
    m=(1+ff5.join(mom,how="inner")).resample("ME").prod()-1; m.index=me(m.index); return m
ff_m = load_ff()
ff_q = (1+ff_m).resample("QE").prod()-1
rf_q = ff_q["RF"]
spy_q = (1+bench["SPY"].pct_change()).resample("QE").prod()-1

# ---------- 4. the quarterly backtest ----------
def run(panel, gross, rf):
    dates = panel.index; prev = pd.Series(dtype=float)
    rets = {}; nsel = {}; turns = {}
    for i in range(LB, len(dates)-1):
        t, nxt = dates[i], dates[i+1]
        win = panel.iloc[i-LB+1:i+1]                       # trailing 4 quarters incl. t
        valid = win.notna().all(axis=0)
        sig = (1+win).prod()[valid]                        # 4-quarter cumulative return
        if len(sig) < 20: continue
        z = (sig - sig.mean())/sig.std()
        sel = z[z >= z.quantile(1-Q)].index
        g = float(gross.asof(t)) if pd.notna(gross.asof(t)) else 0.65
        w = pd.Series(g/len(sel), index=sel)               # equal weight, scaled by exposure
        r_next = panel.loc[nxt].reindex(sel)
        have = r_next.notna()
        port = float((w[have]*r_next[have]).sum())
        cash_w = 1.0 - float(w[have].sum())                # macro cash + liquidated leavers
        port += cash_w*float(rf.get(nxt, 0.0))
        all_n = prev.index.union(w.index)
        turn = float((w.reindex(all_n).fillna(0) - prev.reindex(all_n).fillna(0)).abs().sum())
        rets[nxt] = port - turn*(TC_BPS/10000.0)
        nsel[nxt] = int(len(sel)); turns[nxt] = turn; prev = w
    return pd.Series(rets).sort_index(), pd.Series(nsel), pd.Series(turns)

def metrics(r):
    r = r.dropna(); cum = (1+r).cumprod(); n = len(r)
    cagr = cum.iloc[-1]**(PA/n)-1; vol = r.std()*np.sqrt(PA)
    ex = r - rf_q.reindex(r.index).fillna(0); sh = (ex.mean()*PA)/(ex.std()*np.sqrt(PA))
    dd = (cum/cum.cummax()-1).min()
    return {"CAGR":float(cagr),"Vol":float(vol),"Sharpe":float(sh),"MaxDD":float(dd),
            "Calmar":float(cagr/abs(dd)) if dd<0 else None,"HitRate":float((r>0).mean()),"N_quarters":int(n)}

# universe A: survivorship-free (all names, point-in-time)
rA, nA, tA = run(R, gross_q, rf_q)
# universe B: survivors-only (names still alive in the final quarter) -> recreates the bias
survivors = R.columns[R.iloc[-1].notna()]
rB, nB, tB = run(R[survivors], gross_q, rf_q)

def window(r): return r.loc[START:]
A = window(rA); B = window(rB); SPY = spy_q.loc[START:rA.index.max()]
mA, mB, mSPY = metrics(A), metrics(B), metrics(SPY)
mA_is, mA_oos = metrics(rA.loc[START:IS_END]), metrics(rA.loc[OOS_START:])

# ---------- 5. factor regression on the survivorship-free returns (quarterly) ----------
fcols = ["Mkt-RF","SMB","HML","RMW","CMA","Mom"]
d = pd.concat([(A - rf_q.reindex(A.index)).rename("y"), ff_q[fcols]], axis=1).dropna()
res = sm.OLS(d["y"], sm.add_constant(d[fcols])).fit(cov_type="HAC", cov_kwds={"maxlags":2})
alpha_a = float(res.params["const"]*PA); alpha_t = float(res.tvalues["const"])

# same for the biased universe (to show the inflation in alpha terms)
dB = pd.concat([(B - rf_q.reindex(B.index)).rename("y"), ff_q[fcols]], axis=1).dropna()
resB = sm.OLS(dB["y"], sm.add_constant(dB[fcols])).fit(cov_type="HAC", cov_kwds={"maxlags":2})
alphaB_a = float(resB.params["const"]*PA); alphaB_t = float(resB.tvalues["const"])

# ---------- 6. report ----------
print("\n"+"="*78)
print("SURVIVORSHIP-CORRECTED (quarterly, point-in-time S&P 500)")
print("="*78)
print(f"{'':26}{'CAGR':>8}{'Vol':>8}{'Sharpe':>8}{'MaxDD':>8}")
for lab,m in [("A. Survivorship-FREE",mA),("B. Survivors-only (biased)",mB),("S&P 500 (SPY)",mSPY)]:
    print(f"{lab:26}{m['CAGR']*100:7.1f}%{m['Vol']*100:7.1f}%{m['Sharpe']:8.2f}{m['MaxDD']*100:7.0f}%")
print(f"\nSurvivorship drag:  CAGR {(mB['CAGR']-mA['CAGR'])*100:+.2f}%/yr   Sharpe {mB['Sharpe']-mA['Sharpe']:+.2f}")
print(f"Alpha vs FF5+MOM (annualized):  FREE {alpha_a*100:+.2f}% (t={alpha_t:.2f})   BIASED {alphaB_a*100:+.2f}% (t={alphaB_t:.2f})")
print(f"IS Sharpe {mA_is['Sharpe']:.2f}   OOS Sharpe {mA_oos['Sharpe']:.2f}")
print(f"Avg names selected/qtr (free): {nA.loc[START:].mean():.0f}   Avg ann. turnover: {tA.loc[START:].mean()*PA*100:.0f}%")

def pairs(s): return [[t.strftime("%Y-%m-%d"), float(v)] for t,v in s.dropna().items()]
def cum_pairs(s): return pairs((1+s.dropna()).cumprod())
def dd_pairs(s): c=(1+s.dropna()).cumprod(); return pairs(c/c.cummax()-1)

out = {
 "meta":{"source":"Total Returns Hard Copy.xlsx (Bloomberg, point-in-time S&P 500)",
   "universe":f"{R.shape[1]} historical names; ~500 point-in-time members/quarter",
   "frequency":"Quarterly total returns","window":f"{START[:7]} to {rA.index.max():%Y-%m}",
   "engine":"4-quarter momentum, equal-weight top quartile, 4-factor macro overlay (30-100% gross), long-only, 15bps",
   "tc_bps":TC_BPS,"note":"Survivorship-free = point-in-time membership; Survivors-only recreates the bias on identical data."},
 "summary":{"Survivorship-free":mA,"Survivors-only (biased)":mB,"SPY":mSPY,
   "Survivorship-free IS (2002-2015)":mA_is,"Survivorship-free OOS (2016-2026)":mA_oos},
 "bias":{"cagr_drag":mB["CAGR"]-mA["CAGR"],"sharpe_drag":mB["Sharpe"]-mA["Sharpe"],
   "alpha_free":alpha_a,"alpha_free_t":alpha_t,"alpha_biased":alphaB_a,"alpha_biased_t":alphaB_t,
   "alpha_inflation":alphaB_a-alpha_a},
 "factor_regression_free":{"alpha_annualized":alpha_a,"alpha_tstat":alpha_t,"rsquared":float(res.rsquared),
   "betas":{k:float(v) for k,v in res.params.drop("const").items()}},
 "equity_curves":{"Survivorship-free":cum_pairs(A),"Survivors-only (biased)":cum_pairs(B),"SPY":cum_pairs(SPY)},
 "drawdowns":{"Survivorship-free":dd_pairs(A),"SPY":dd_pairs(SPY)},
 "diagnostics":{"avg_names_per_quarter":float(nA.loc[START:].mean()),"avg_annual_turnover":float(tA.loc[START:].mean()*PA),
   "n_historical_names":int(R.shape[1]),"n_survivors":int(len(survivors))},
}
Path("survivorship_corrected.json").write_text(json.dumps(out, indent=2, default=str))

# ---------- 7. chart ----------
fig,(ax1,ax2)=plt.subplots(2,1,figsize=(11,8),gridspec_kw={"height_ratios":[2,1]})
cA=(1+A).cumprod(); cB=(1+B).cumprod(); cS=(1+SPY).cumprod()
ax1.plot(cA.index,cA.values,color="tab:green",lw=2,label=f"Survivorship-free ({mA['CAGR']*100:.1f}% CAGR, SR {mA['Sharpe']:.2f})")
ax1.plot(cB.index,cB.values,color="tab:orange",lw=1.8,ls="--",label=f"Survivors-only / biased ({mB['CAGR']*100:.1f}%, SR {mB['Sharpe']:.2f})")
ax1.plot(cS.index,cS.values,color="black",lw=1.2,ls=":",label=f"S&P 500 ({mSPY['CAGR']*100:.1f}%, SR {mSPY['Sharpe']:.2f})")
ax1.set_yscale("log"); ax1.set_ylabel("Growth of $1 (log)"); ax1.legend(loc="upper left",fontsize=9)
ax1.set_title("Survivorship-corrected vs biased vs market (SIMULATED, quarterly, point-in-time S&P 500)")
ax1.grid(alpha=0.3)
ddA=cA/cA.cummax()-1; ddS=cS/cS.cummax()-1
ax2.fill_between(ddA.index,ddA.values,0,color="tab:green",alpha=0.4,label="Survivorship-free")
ax2.plot(ddS.index,ddS.values,color="black",lw=1,ls=":",label="S&P 500")
ax2.set_ylabel("Drawdown"); ax2.legend(loc="lower left",fontsize=9); ax2.grid(alpha=0.3)
fig.tight_layout(); fig.savefig("fig_survivorship_corrected.png",dpi=140)
print("\nSaved survivorship_corrected.json and fig_survivorship_corrected.png")
