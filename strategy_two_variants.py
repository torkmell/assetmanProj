# %% [markdown]
# # S2 fix attempts — quick comparison
#
# S2a: drop reversal; keep momentum + low-vol; L/S top quintile vs bottom quintile, dollar-neutral
# S2b: drop reversal; keep momentum + low-vol; long-only top quintile, no shorts
# S2c (bonus): long-only top quintile by **multi-factor** (mom + low-vol) **with macro overlay**
#               — direct comparison vs S1 (long-only momentum + macro overlay)

# %%
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import warnings
warnings.filterwarnings("ignore")

CACHE = Path("data_cache")
DATA_ROOT = Path(__file__).resolve().parent / "course_data"  # bundled course data inside the repo

def to_month_end(idx):
    return pd.to_datetime(idx).to_period("M").to_timestamp("M")

prices       = pd.read_csv(CACHE / "prices_sp500_monthly.csv", index_col=0, parse_dates=True)
benchmarks   = pd.read_csv(CACHE / "prices_benchmarks_monthly.csv", index_col=0, parse_dates=True)
vix          = pd.read_csv(CACHE / "prices_vix_monthly.csv", index_col=0, parse_dates=True)
constituents = pd.read_csv(CACHE / "sp500_constituents.csv")
macro_px     = pd.read_csv(CACHE / "macro_proxies_monthly.csv", index_col=0, parse_dates=True)
vix.columns  = ["VIX"]
for df in (prices, benchmarks, vix, macro_px):
    df.index = to_month_end(df.index)

tech_tickers = [t for t in constituents[constituents["sector"] == "Information Technology"]["ticker"].tolist()
                if t in prices.columns]
prices_tech = prices[tech_tickers]
returns_tech = prices_tech.pct_change()
log_ret_tech = np.log1p(returns_tech)

# %% — macro composite (same recipe)
def rolling_zscore(s, w=60, mp=24):
    return (s - s.rolling(w, min_periods=mp).mean()) / s.rolling(w, min_periods=mp).std()
def build_macro(vix_s, mx):
    idx = vix_s.index; c = pd.DataFrame(index=idx)
    c["vix"] = -rolling_zscore(vix_s)
    cred = np.log(mx["IEF"]).reindex(idx).ffill() - np.log(mx["HYG"]).reindex(idx).ffill()
    c["credit"] = -rolling_zscore(cred.diff(12))
    tnx = mx["^TNX"].reindex(idx).ffill()
    c["yield"] = -rolling_zscore(tnx.diff(12))
    spx = mx["^GSPC"].reindex(idx).ffill()
    c["trend"] = rolling_zscore(np.log(spx).diff(1).shift(1).rolling(11).sum())
    return c.mean(axis=1).clip(-2, 2).shift(1)
macro_score = build_macro(vix["VIX"], macro_px)
gross_macro = np.clip(0.65 + 0.175 * macro_score, 0.3, 1.0)

# %% — factors
def zscore_cs(p):
    return p.sub(p.mean(axis=1), axis=0).div(p.std(axis=1), axis=0)
mom_12_1 = log_ret_tech.shift(1).rolling(11).sum()
mom_z    = zscore_cs(mom_12_1)
vol_12   = returns_tech.shift(1).rolling(12).std()
lowvol_z = zscore_cs(-vol_12)

# 2-factor composite (no reversal)
comp = pd.DataFrame(0.0, index=prices_tech.index, columns=prices_tech.columns)
cnt  = pd.DataFrame(0.0, index=prices_tech.index, columns=prices_tech.columns)
for fz in [mom_z, lowvol_z]:
    comp = comp.add(fz.fillna(0), fill_value=0)
    cnt  = cnt.add(fz.notna().astype(float), fill_value=0)
composite_2 = comp.div(cnt).where(cnt >= 2)

# %% — engine
def qw_long(scores, q=0.20):
    r = scores.rank(axis=1, pct=True); m = r >= (1 - q)
    w = m.astype(float)
    return w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
def qw_short(scores, q=0.20):
    r = scores.rank(axis=1, pct=True); m = r <= q
    w = m.astype(float)
    return w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)

TC = 15

def backtest(scores, mode, q=0.20, gross_scalar=None, rf=None):
    wL = qw_long(scores, q=q)
    wS = qw_short(scores, q=q) if mode == "ls" else pd.DataFrame(0.0, index=wL.index, columns=wL.columns)
    if gross_scalar is not None:
        s = gross_scalar.reindex(wL.index).fillna(0.0).clip(lower=0)
        wL = wL.mul(s, axis=0); wS = wS.mul(s, axis=0)
    w_net = wL - wS
    R = returns_tech.reindex_like(w_net).fillna(0)
    port_gross = (w_net.shift(1).fillna(0) * R).sum(axis=1)
    if mode == "long_only" and gross_scalar is not None and rf is not None:
        cash_w = (1.0 - wL.sum(axis=1)).clip(lower=0)
        port_gross = port_gross + (cash_w.shift(1).fillna(0) * rf.reindex(w_net.index).fillna(0))
    dw = (w_net - w_net.shift(1)).abs().sum(axis=1)
    tc = dw * (TC / 10000.0)
    return pd.DataFrame({"net_return": port_gross - tc, "turnover": dw})

def perf(r, rf=None):
    r = r.dropna()
    if len(r) < 12: return {k: None for k in ["CAGR","Vol","Sharpe","MaxDD","Calmar","Turnover"]}
    cum = (1 + r).cumprod()
    cagr = cum.iloc[-1] ** (12 / len(r)) - 1
    vol = r.std() * np.sqrt(12)
    if rf is not None:
        ex = r - rf.reindex(r.index).fillna(0)
        sharpe = (ex.mean() * 12) / (ex.std() * np.sqrt(12))
    else:
        sharpe = (r.mean() * 12) / (r.std() * np.sqrt(12))
    dd = (cum / cum.cummax() - 1).min()
    return {"CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "MaxDD": dd, "Calmar": cagr/abs(dd) if dd<0 else np.nan}

# %% — RF
ff5 = pd.read_csv(DATA_ROOT / "Folder_Macro_Factors_.187814089" / "content" / "F-F_Research_Data_5_Factors_2x3_daily.CSV",
                  skiprows=3, index_col=0)
ff5.columns = [c.strip() for c in ff5.columns]
ff5.index = pd.to_datetime(ff5.index.astype(str), format="%Y%m%d")
rf = (1 + ff5["RF"]/100).resample("ME").prod() - 1
rf.index = to_month_end(rf.index)

# %% — Variants
START = "2002-01-31"

# S2 ORIGINAL — 3-factor L/S (rebuild for reference)
reversal_z = zscore_cs(-returns_tech)
comp3 = pd.DataFrame(0.0, index=prices_tech.index, columns=prices_tech.columns)
cnt3  = pd.DataFrame(0.0, index=prices_tech.index, columns=prices_tech.columns)
for fz in [mom_z, lowvol_z, reversal_z]:
    comp3 = comp3.add(fz.fillna(0), fill_value=0)
    cnt3  = cnt3.add(fz.notna().astype(float), fill_value=0)
comp3 = comp3.div(cnt3).where(cnt3 >= 3)
bt_S2_orig = backtest(comp3, mode="ls", q=0.20)
ret_S2_orig = bt_S2_orig.loc[START:, "net_return"]

# S2a — 2-factor (mom + low-vol) L/S
bt_S2a = backtest(composite_2, mode="ls", q=0.20)
ret_S2a = bt_S2a.loc[START:, "net_return"]

# S2b — 2-factor (mom + low-vol) long-only, no overlay
bt_S2b = backtest(composite_2, mode="long_only", q=0.25, rf=rf)
ret_S2b = bt_S2b.loc[START:, "net_return"]

# S2c — 2-factor long-only + macro overlay (direct head-to-head vs S1)
bt_S2c = backtest(composite_2, mode="long_only", q=0.25, gross_scalar=gross_macro, rf=rf)
ret_S2c = bt_S2c.loc[START:, "net_return"]

# S1 reference — pure momentum long-only + macro overlay (winner from before)
bt_S1_ref = backtest(mom_z, mode="long_only", q=0.25, gross_scalar=gross_macro, rf=rf)
ret_S1_ref = bt_S1_ref.loc[START:, "net_return"]

# %% — Report
def line(name, r, turnover):
    m = perf(r, rf=rf)
    ann_to = turnover.loc[START:].mean() * 12 if turnover is not None else None
    return f"{name:55s}  CAGR={m['CAGR']*100:6.2f}%  Vol={m['Vol']*100:5.1f}%  Sharpe={m['Sharpe']:5.2f}  MaxDD={m['MaxDD']*100:6.1f}%  Calmar={m['Calmar']:5.2f}  TO={ann_to*100:6.0f}%"

print("=" * 130)
print("S2 FIX EXPERIMENTS — same tech universe, same window, same TC (15 bps)")
print("=" * 130)
print(line("S2 original  (mom+lowvol+reversal, L/S quintile)", ret_S2_orig, bt_S2_orig["turnover"]))
print(line("S2a          (mom+lowvol, L/S quintile)         ", ret_S2a,     bt_S2a["turnover"]))
print(line("S2b          (mom+lowvol, long-only top quartile)", ret_S2b,    bt_S2b["turnover"]))
print(line("S2c          (mom+lowvol, long-only + macro)     ", ret_S2c,    bt_S2c["turnover"]))
print(line("S1 reference (pure momentum, long-only + macro)  ", ret_S1_ref, bt_S1_ref["turnover"]))
print("\nNote: Sharpe is excess-of-RF. All strategies run 2002-01 to 2026-05 on 73-stock tech universe.")

# Save full time series for the comparison dashboard
def pairs(s):
    return [[t.strftime("%Y-%m-%d"), float(v)] for t, v in s.dropna().items()]
def cum_pairs(s):
    return pairs((1 + s.dropna()).cumprod())
def dd_pairs(s):
    cum = (1 + s.dropna()).cumprod()
    return pairs(cum / cum.cummax() - 1)

def metrics_with_turnover(r, turnover):
    m = perf(r, rf=rf)
    for kk in m:
        if isinstance(m[kk], (np.floating,)): m[kk] = float(m[kk])
    m["Turnover"] = float(turnover.loc[START:].mean() * 12) if turnover is not None else None
    return m

out = {
    "variants": {
        "S2_original": {
            "name": "S2 original: 3-factor L/S",
            "description": "Momentum + low-vol + reversal composite, L/S top vs bottom quintile, dollar-neutral.",
            "category": "rejected",
            "verdict": "FAILED — reversal cancels momentum; L/S in tech is broken",
            "metrics": metrics_with_turnover(ret_S2_orig, bt_S2_orig["turnover"]),
            "equity_curve": cum_pairs(ret_S2_orig),
            "drawdown":     dd_pairs(ret_S2_orig),
        },
        "S2a_2f_ls": {
            "name": "S2a: 2-factor L/S",
            "description": "Drop reversal; momentum + low-vol composite, L/S top vs bottom quintile.",
            "category": "rejected",
            "verdict": "FAILED — short side concentration in tech is the real problem",
            "metrics": metrics_with_turnover(ret_S2a, bt_S2a["turnover"]),
            "equity_curve": cum_pairs(ret_S2a),
            "drawdown":     dd_pairs(ret_S2a),
        },
        "S2b_2f_lo": {
            "name": "S2b: 2-factor long-only",
            "description": "Drop reversal AND short side; momentum + low-vol composite, long top quartile, no overlay.",
            "category": "considered",
            "verdict": "Works (0.92 Sharpe) but -50% MaxDD; needs overlay",
            "metrics": metrics_with_turnover(ret_S2b, bt_S2b["turnover"]),
            "equity_curve": cum_pairs(ret_S2b),
            "drawdown":     dd_pairs(ret_S2b),
        },
        "S2c_2f_lo_macro": {
            "name": "S2c: 2-factor long-only + macro overlay",
            "description": "Add macro overlay to S2b; momentum + low-vol, long top quartile, gross exposure scaled by macro composite.",
            "category": "contender",
            "verdict": "VIABLE — Sharpe 0.95, MaxDD -27%. Trades 3pp/yr CAGR for hair of Sharpe vs S1.",
            "metrics": metrics_with_turnover(ret_S2c, bt_S2c["turnover"]),
            "equity_curve": cum_pairs(ret_S2c),
            "drawdown":     dd_pairs(ret_S2c),
        },
        "S1_ref": {
            "name": "S1: Macro-Overlay Tech (pure momentum)",
            "description": "Pure 12-1m momentum, long top quartile, gross exposure scaled by macro composite.",
            "category": "contender",
            "verdict": "PITCHED — highest CAGR (16.1%) and Calmar (0.57); cleanest narrative",
            "metrics": metrics_with_turnover(ret_S1_ref, bt_S1_ref["turnover"]),
            "equity_curve": cum_pairs(ret_S1_ref),
            "drawdown":     dd_pairs(ret_S1_ref),
        },
    },
    "meta": {
        "window": f"{START[:7]} to {prices_tech.index[-1]:%Y-%m}",
        "universe": f"S&P 500 ∩ GICS Tech ({len(tech_tickers)} stocks)",
        "tc_bps": TC,
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
    },
}
Path("s2_variants_full.json").write_text(json.dumps(out, indent=2, default=str))
print(f"\nSaved s2_variants_full.json ({Path('s2_variants_full.json').stat().st_size / 1024:.0f} KB)")
