# %% [markdown]
# # Broad multi-factor L/S — "L/S done right"
#
# Diagnosis from S2/S2a: long-short FAILED on the 73-stock tech universe because it was
# too concentrated and net-short the mega-caps. This script tests the fix:
#   - Broad, multi-sector universe (full S&P 500, ~500 names) for breadth + shortability
#   - SECTOR-NEUTRAL construction (rank within GICS sector) so we don't bet on sectors
#   - Dollar-neutral quintile L/S, with short-borrow cost
#
# Factors are price-based only (momentum + low-vol + low-beta) — the value/quality sleeves
# need fundamentals (Bloomberg/Compustat) and are specced separately.
#
# We run TWO broad versions — NOT sector-neutral vs sector-neutral — to isolate what the
# neutralisation actually buys, and compare both to the failed tech L/S (S2a).

# %%
import json
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.api as sm
import warnings
warnings.filterwarnings("ignore")

CACHE = Path("data_cache")
DATA_ROOT = Path(__file__).resolve().parent / "course_data"
TC_BPS = 15
BORROW_ANNUAL = 0.005   # 50 bps/yr borrow on the short sleeve (liquid large-cap)
START = "2002-01-31"

def to_month_end(idx):
    return pd.to_datetime(idx).to_period("M").to_timestamp("M")

# %% — Data
prices       = pd.read_csv(CACHE / "prices_sp500_monthly.csv", index_col=0, parse_dates=True)
benchmarks   = pd.read_csv(CACHE / "prices_benchmarks_monthly.csv", index_col=0, parse_dates=True)
macro_px     = pd.read_csv(CACHE / "macro_proxies_monthly.csv", index_col=0, parse_dates=True)
constituents = pd.read_csv(CACHE / "sp500_constituents.csv")
for df in (prices, benchmarks, macro_px):
    df.index = to_month_end(df.index)

# Universe: every S&P 500 name with price data and a known sector
sector_map = dict(zip(constituents["ticker"], constituents["sector"]))
universe = [t for t in prices.columns if t in sector_map]
prices = prices[universe]
returns = prices.pct_change()
log_ret = np.log1p(returns)
END = prices.index[-1]
print(f"Universe: {len(universe)} S&P 500 names across {constituents['sector'].nunique()} sectors")

# Market proxy for beta
mkt_ret = macro_px["^GSPC"].reindex(prices.index).ffill().pct_change()

# %% — Price factors
def zscore_cs(panel):
    z = panel.sub(panel.mean(axis=1), axis=0).div(panel.std(axis=1), axis=0)
    return z.clip(-3, 3)            # winsorise

# Momentum 12-1
mom    = log_ret.shift(1).rolling(11).sum()
mom_z  = zscore_cs(mom)
# Low volatility (negative of trailing 12m stdev)
vol12  = returns.shift(1).rolling(12).std()
lowvol_z = zscore_cs(-vol12)
# Low beta (negative of rolling 36m beta to market)
xy   = (returns.mul(mkt_ret, axis=0)).rolling(36, min_periods=24).mean()
ex   = returns.rolling(36, min_periods=24).mean()
em   = mkt_ret.rolling(36, min_periods=24).mean()
cov  = xy.sub(ex.mul(em, axis=0))
var  = mkt_ret.rolling(36, min_periods=24).var()
beta = cov.div(var, axis=0).shift(1)
lowbeta_z = zscore_cs(-beta)

# Equal-weight composite of the three sleeves
sleeves = [mom_z, lowvol_z, lowbeta_z]
comp = sum(s.fillna(0) for s in sleeves)
cnt  = sum(s.notna().astype(float) for s in sleeves)
composite = (comp / cnt).where(cnt >= 2)

# Sector-neutral version: demean composite within each GICS sector, each month
def sector_neutralise(score):
    out = score.copy()
    for sec in set(sector_map.values()):
        cols = [c for c in score.columns if sector_map.get(c) == sec]
        if len(cols) >= 3:
            out[cols] = score[cols].sub(score[cols].mean(axis=1), axis=0)
    return out
composite_sn = sector_neutralise(composite)

# %% — L/S engine (dollar-neutral quintiles)
def quintile_legs(scores, q=0.20):
    r = scores.rank(axis=1, pct=True)
    wL = (r >= 1 - q).astype(float)
    wS = (r <= q).astype(float)
    wL = wL.div(wL.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    wS = wS.div(wS.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    return wL, wS

def backtest_ls(scores, q=0.20):
    wL, wS = quintile_legs(scores, q=q)
    w_net = wL - wS                                   # dollar-neutral
    R = returns.reindex_like(w_net).fillna(0)
    gross = (w_net.shift(1).fillna(0) * R).sum(axis=1)
    dw = (w_net - w_net.shift(1)).abs().sum(axis=1)
    tc = dw * (TC_BPS / 10000.0)
    borrow = wS.shift(1).fillna(0).sum(axis=1) * (BORROW_ANNUAL / 12.0)
    net = gross - tc - borrow
    # realised beta of the long and short legs (for honesty)
    legL = (wL.shift(1).fillna(0) * R).sum(axis=1)
    legS = (wS.shift(1).fillna(0) * R).sum(axis=1)
    return pd.DataFrame({"net": net, "turnover": dw, "legL": legL, "legS": legS})

# %% — Metrics + factor alpha
def perf(r):
    r = r.dropna()
    if len(r) < 12:
        return {k: None for k in ["CAGR","Vol","Sharpe","MaxDD","Calmar","N"]}
    cum = (1 + r).cumprod()
    cagr = cum.iloc[-1] ** (12 / len(r)) - 1
    vol = r.std() * np.sqrt(12)
    sharpe = (r.mean() * 12) / vol if vol > 0 else np.nan      # L/S: already excess
    dd = (cum / cum.cummax() - 1).min()
    return {"CAGR": float(cagr), "Vol": float(vol), "Sharpe": float(sharpe),
            "MaxDD": float(dd), "Calmar": float(cagr/abs(dd)) if dd < 0 else None,
            "N": int(len(r))}

def load_ff_factors():
    ff5 = pd.read_csv(DATA_ROOT / "Folder_Macro_Factors_.187814089" / "content" / "F-F_Research_Data_5_Factors_2x3_daily.CSV",
                      skiprows=3, index_col=0)
    ff5.columns = [c.strip() for c in ff5.columns]
    ff5.index = pd.to_datetime(ff5.index.astype(str), format="%Y%m%d")
    ff5 = ff5 / 100.0
    mom = pd.read_csv(DATA_ROOT / "Folder_Macro_Factors_.187814089" / "content" / "F-F_Momentum_Factor_daily.CSV",
                      skiprows=13, index_col=0, skipfooter=2, engine="python")
    mom.columns = ["Mom"]; mom = mom.dropna()
    mom.index = pd.to_datetime(mom.index.astype(str).str.strip(), format="%Y%m%d", errors="coerce")
    mom = mom.dropna() / 100.0
    daily = ff5.join(mom, how="inner")
    monthly = (1 + daily).resample("ME").prod() - 1
    monthly.index = to_month_end(monthly.index)
    return monthly
factors_m = load_ff_factors()

def factor_alpha(ret):
    cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
    d = pd.concat([ret.rename("y"), factors_m[cols]], axis=1).dropna()
    X = sm.add_constant(d[cols])
    res = sm.OLS(d["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    return {"alpha_ann": float(res.params["const"]*12), "alpha_t": float(res.tvalues["const"]),
            "mkt_beta": float(res.params["Mkt-RF"]), "rsq": float(res.rsquared)}

# %% — Run
bt_raw = backtest_ls(composite)
bt_sn  = backtest_ls(composite_sn)
ret_raw = bt_raw.loc[START:END, "net"]
ret_sn  = bt_sn.loc[START:END, "net"]

m_raw, a_raw = perf(ret_raw), factor_alpha(ret_raw)
m_sn,  a_sn  = perf(ret_sn),  factor_alpha(ret_sn)

# Reference: the failed tech L/S (S2a) from the existing results
s2 = json.load(open("s2_variants_full.json"))["variants"]["S2a_2f_ls"]["metrics"]

# %% — Report
def fmt(name, m, a=None):
    line = (f"{name:42s}  CAGR={m['CAGR']*100:7.2f}%  Vol={m['Vol']*100:5.1f}%  "
            f"Sharpe={m['Sharpe']:6.2f}  MaxDD={m['MaxDD']*100:7.1f}%  "
            f"Calmar={(m['Calmar'] if m['Calmar'] is not None else float('nan')):5.2f}")
    if a:
        line += f"  | a={a['alpha_ann']*100:5.2f}% (t={a['alpha_t']:.2f})  netB={a['mkt_beta']:+.2f}"
    return line

print("\n" + "=" * 140)
print("BROAD MULTI-FACTOR L/S (mom + low-vol + low-beta) — full S&P 500, 2002-2026, dollar-neutral, 15bps + 50bps borrow")
print("=" * 140)
print(fmt("Tech L/S (S2a) — the FAILED version", {**s2, "Vol": s2.get("Vol", float('nan'))}))
print(fmt("Broad L/S — NOT sector-neutral", m_raw, a_raw))
print(fmt("Broad L/S — SECTOR-NEUTRAL", m_sn, a_sn))
print("\nNote: L/S Sharpe is on the self-financing spread (no RF). netB = market beta from FF5+MOM regression.")

# %% — JSON for the notebook/dashboard
def pairs(s):    return [[t.strftime("%Y-%m-%d"), float(v)] for t, v in s.dropna().items()]
def cum_pairs(s): return pairs((1 + s.dropna()).cumprod())
def dd_pairs(s):
    c = (1 + s.dropna()).cumprod()
    return pairs(c / c.cummax() - 1)

out = {
    "meta": {
        "title": "Broad multi-factor L/S — L/S done right",
        "universe": f"Full S&P 500 ({len(universe)} names, all sectors)",
        "factors": "Momentum (12-1), Low-vol (12m), Low-beta (36m) — price-based only",
        "window": f"{START[:7]} to {END:%Y-%m}",
        "construction": "Dollar-neutral quintile L/S; sector-neutral demeans within GICS",
        "tc_bps": TC_BPS, "borrow_annual": BORROW_ANNUAL,
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "note": "Price factors only. Value/quality sleeves require fundamentals (Bloomberg/Compustat).",
    },
    "strategies": {
        "tech_ls_failed": {"name": "Tech L/S (S2a) — failed", "metrics": s2},
        "broad_ls_raw":   {"name": "Broad L/S — not sector-neutral",
                           "metrics": {**m_raw, **a_raw},
                           "equity_curve": cum_pairs(ret_raw), "drawdown": dd_pairs(ret_raw)},
        "broad_ls_sn":    {"name": "Broad L/S — sector-neutral",
                           "metrics": {**m_sn, **a_sn},
                           "equity_curve": cum_pairs(ret_sn), "drawdown": dd_pairs(ret_sn)},
    },
}
Path("multifactor_ls.json").write_text(json.dumps(out, indent=2, default=str))
print(f"\nSaved multifactor_ls.json ({Path('multifactor_ls.json').stat().st_size/1024:.0f} KB)")
