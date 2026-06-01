# %% [markdown]
# # GSD2T — Three strategies on the same Tech universe
#
# All three run on the 73 GICS Information Technology stocks in the S&P 500, monthly, 2001-2026.
# Clean apples-to-apples comparison: same data, same window, different signal architectures.
#
# - **Strategy 1: Macro-Overlay Tech (long-only)** — rank tech by 12-1m momentum, long top quartile,
#   gross exposure scaled by a macro regime composite.
# - **Strategy 2: Multi-Factor Tech L/S** — 3-factor composite (mom + low-vol + reversal) within
#   tech, long top quintile / short bottom quintile, dollar-neutral.
# - **Strategy 3: Tech + VIX L/S** — 12-1m momentum within tech, L/S top vs bottom quartile,
#   gross exposure scaled by VIX regime.

# %%
import json
import urllib.request
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import statsmodels.api as sm
import warnings
warnings.filterwarnings("ignore")
import yfinance as yf

CACHE = Path("data_cache")
CACHE.mkdir(exist_ok=True)
START = "2000-01-01"
END   = "2026-06-01"

# %% [markdown]
# ## 1. Load existing yfinance cache + pull macro proxies

# %%
prices       = pd.read_csv(CACHE / "prices_sp500_monthly.csv", index_col=0, parse_dates=True)
benchmarks   = pd.read_csv(CACHE / "prices_benchmarks_monthly.csv", index_col=0, parse_dates=True)
vix          = pd.read_csv(CACHE / "prices_vix_monthly.csv", index_col=0, parse_dates=True)
constituents = pd.read_csv(CACHE / "sp500_constituents.csv")
vix.columns  = ["VIX"]

def to_month_end(idx):
    return pd.to_datetime(idx).to_period("M").to_timestamp("M")
for df in (prices, benchmarks, vix):
    df.index = to_month_end(df.index)

# Pull macro proxies via yfinance (if not cached)
def pull_macro_proxies():
    cache_path = CACHE / "macro_proxies_monthly.csv"
    if cache_path.exists():
        print(f"Using cached macro proxies: {cache_path}")
        return pd.read_csv(cache_path, index_col=0, parse_dates=True)
    print("Pulling macro proxies (HYG, IEF, ^TNX, ^GSPC, LQD)...")
    tickers = ["HYG", "IEF", "^TNX", "^GSPC", "LQD"]
    raw = yf.download(tickers, start=START, end=END, interval="1mo",
                      auto_adjust=True, progress=False, group_by="ticker")
    if isinstance(raw.columns, pd.MultiIndex):
        df = pd.DataFrame({t: raw[t]["Close"] for t in tickers if t in raw.columns.levels[0]})
    else:
        df = raw[["Close"]].rename(columns={"Close": tickers[0]})
    df.index = to_month_end(df.index)
    df.to_csv(cache_path)
    return df

macro_px = pull_macro_proxies()
print(f"Macro proxies: {macro_px.shape}, cols={list(macro_px.columns)}")
print(f"Coverage: {macro_px.notna().sum().to_dict()}")

# %% [markdown]
# ## 2. Tech universe filter

# %%
tech_tickers = [t for t in constituents[constituents["sector"] == "Information Technology"]["ticker"].tolist()
                if t in prices.columns]
print(f"Tech universe: {len(tech_tickers)} tickers")

prices_tech = prices[tech_tickers]
returns_tech = prices_tech.pct_change()
log_ret_tech = np.log1p(returns_tech)

# %% [markdown]
# ## 3. Macro regime composite (yfinance-based, available through 2026)
#
# Four components, all lagged one month to avoid look-ahead, all z-scored on a rolling 60m window:
# 1. **VIX (inverted):** high VIX → risk-off → negative score
# 2. **Credit spread (HYG vs IEF):** rolling 12m return of IEF/HYG — when HYG underperforms IEF (credit stress), score → negative
# 3. **10Y yield change (12m):** rising real yields → risk-off → negative score
# 4. **SPX trend (12-1m log return):** positive trend → risk-on → positive score
#
# Composite is averaged across the 4 signals, clipped to [-2, 2], and lagged 1m.

# %%
def rolling_zscore(series, window=60, min_periods=24):
    mu = series.rolling(window, min_periods=min_periods).mean()
    sd = series.rolling(window, min_periods=min_periods).std()
    return (series - mu) / sd

def build_macro_composite(vix_s, macro_px):
    idx = vix_s.index
    components = pd.DataFrame(index=idx)

    # 1. VIX (inverted z-score)
    components["vix"] = -rolling_zscore(vix_s)
    # 2. Credit signal: 12m return of IEF / HYG (when HYG falls relative to IEF, credit stress)
    cred = np.log(macro_px["IEF"]).reindex(idx).ffill() - np.log(macro_px["HYG"]).reindex(idx).ffill()
    components["credit"] = -rolling_zscore(cred.diff(12))  # negative = wider spread = risk-off
    # 3. 10Y yield change (12m)
    tnx = macro_px["^TNX"].reindex(idx).ffill()
    components["yield"] = -rolling_zscore(tnx.diff(12))  # rising yields = risk-off
    # 4. SPX 12-1m trend
    spx = macro_px["^GSPC"].reindex(idx).ffill()
    components["trend"] = rolling_zscore(np.log(spx).diff(1).shift(1).rolling(11).sum())

    composite = components.mean(axis=1).clip(-2, 2).shift(1)  # lag 1m
    return composite, components

macro_composite, macro_components = build_macro_composite(vix["VIX"], macro_px)
print(f"\nMacro composite available from: {macro_composite.dropna().index.min():%Y-%m}")
print(f"Macro composite mean: {macro_composite.mean():.2f}, std: {macro_composite.std():.2f}")

def macro_to_exposure(score):
    """Map composite (-2..+2) to gross exposure (0.3..1.0)."""
    return np.clip(0.65 + 0.175 * score, 0.3, 1.0)

gross_macro = macro_to_exposure(macro_composite)
print(f"Mean gross exposure (Strategy 1, regime-on period): {gross_macro.loc['2002':].mean():.2f}")

# %% [markdown]
# ## 4. Signals — same building blocks for all strategies

# %%
def zscore_cs(panel):
    return panel.sub(panel.mean(axis=1), axis=0).div(panel.std(axis=1), axis=0)

mom_12_1   = log_ret_tech.shift(1).rolling(11).sum()
mom_z      = zscore_cs(mom_12_1)
vol_12     = returns_tech.shift(1).rolling(12).std()
lowvol_z   = zscore_cs(-vol_12)
reversal_z = zscore_cs(-returns_tech)

# 3-factor composite for Strategy 2
factor_dict = {"momentum": mom_z, "lowvol": lowvol_z, "reversal": reversal_z}
composite = pd.DataFrame(0.0, index=prices_tech.index, columns=prices_tech.columns)
counts    = pd.DataFrame(0.0, index=prices_tech.index, columns=prices_tech.columns)
for fz in factor_dict.values():
    composite = composite.add(fz.fillna(0), fill_value=0)
    counts    = counts.add(fz.notna().astype(float), fill_value=0)
composite_z = composite.div(counts).where(counts >= 3)

# %% [markdown]
# ## 5. Common backtest engine

# %%
def quantile_weights(scores, q=0.25, mode="long"):
    """mode='long' or 'short'."""
    ranks = scores.rank(axis=1, pct=True)
    if mode == "long":
        mask = ranks >= (1 - q)
    else:
        mask = ranks <= q
    w = mask.astype(float)
    return w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)

TC_BPS = 15  # round-trip transaction cost for single stocks

def backtest(scores_long, returns_panel, mode="long_only", q=0.25,
             scores_short=None, gross_scalar=None, tc_bps=TC_BPS, rf=None):
    """
    mode: 'long_only' or 'longshort'
    """
    wL = quantile_weights(scores_long, q=q, mode="long")
    if mode == "longshort":
        wS = quantile_weights(scores_short if scores_short is not None else scores_long,
                              q=q, mode="short")
    else:
        wS = pd.DataFrame(0.0, index=wL.index, columns=wL.columns)

    if gross_scalar is not None and mode == "long_only":
        s = gross_scalar.reindex(wL.index).fillna(0.0).clip(lower=0.0)
        wL = wL.mul(s, axis=0)
    if gross_scalar is not None and mode == "longshort":
        s = gross_scalar.reindex(wL.index).fillna(0.0).clip(lower=0.0)
        wL = wL.mul(s, axis=0)
        wS = wS.mul(s, axis=0)

    w_net = wL - wS
    R = returns_panel.reindex_like(w_net).fillna(0.0)
    port_gross = (w_net.shift(1).fillna(0.0) * R).sum(axis=1)

    # Cash sleeve for long-only with scaling
    if mode == "long_only" and gross_scalar is not None and rf is not None:
        cash_w = (1.0 - wL.sum(axis=1)).clip(lower=0.0)
        port_gross = port_gross + (cash_w.shift(1).fillna(0.0) * rf.reindex(w_net.index).fillna(0.0))

    dw = (w_net - w_net.shift(1)).abs().sum(axis=1)
    tc = dw * (tc_bps / 10000.0)
    port_net = port_gross - tc

    return pd.DataFrame({
        "gross_return": port_gross, "tc": tc, "net_return": port_net,
        "turnover": dw, "n_long": (wL > 0).sum(axis=1), "n_short": (wS > 0).sum(axis=1),
    }), w_net

# RF from FF data
DATA_ROOT = Path(__file__).resolve().parent / "course_data"  # bundled course data inside the repo
def load_rf_monthly():
    ff5 = pd.read_csv(DATA_ROOT / "Folder_Macro_Factors_.187814089" / "content" / "F-F_Research_Data_5_Factors_2x3_daily.CSV",
                      skiprows=3, index_col=0)
    ff5.columns = [c.strip() for c in ff5.columns]
    ff5.index = pd.to_datetime(ff5.index.astype(str), format="%Y%m%d")
    ff5 = ff5 / 100.0
    rf = (1 + ff5["RF"]).resample("ME").prod() - 1
    rf.index = to_month_end(rf.index)
    return rf
rf = load_rf_monthly()

# %% [markdown]
# ## 6. Run all three strategies

# %%
# Strategy 1: Macro-Overlay Tech (long-only)
bt1, w1 = backtest(mom_z, returns_tech, mode="long_only", q=0.25,
                    gross_scalar=gross_macro, rf=rf, tc_bps=TC_BPS)

# Strategy 2: Multi-Factor Tech L/S
bt2, w2 = backtest(composite_z, returns_tech, mode="longshort", q=0.20, tc_bps=TC_BPS)

# Strategy 3: Tech + VIX L/S
def vix_to_exposure(v):
    out = pd.Series(index=v.index, dtype=float)
    out[v < 16]                = 1.00
    out[(v >= 16) & (v < 24)]  = 0.75
    out[(v >= 24) & (v < 32)]  = 0.40
    out[v >= 32]               = 0.00
    return out.shift(1)
gross_vix = vix_to_exposure(vix["VIX"].reindex(prices_tech.index).ffill())
bt3, w3 = backtest(mom_z, returns_tech, mode="longshort", q=0.25,
                    gross_scalar=gross_vix, tc_bps=TC_BPS)

# %% [markdown]
# ## 7. Performance metrics

# %%
def perf_metrics(returns, periods_per_year=12, name=""):
    r = returns.dropna()
    if len(r) < 12:
        return pd.Series({k: np.nan for k in ["CAGR","Vol","Sharpe","Sortino","Calmar","MaxDD","HitRate","N_months"]}, name=name)
    cum = (1 + r).cumprod()
    cagr = cum.iloc[-1] ** (periods_per_year / len(r)) - 1
    vol = r.std() * np.sqrt(periods_per_year)
    sharpe = (r.mean() * periods_per_year) / (r.std() * np.sqrt(periods_per_year))
    downside = r[r < 0].std() * np.sqrt(periods_per_year)
    sortino = (r.mean() * periods_per_year) / downside if downside > 0 else np.nan
    dd = cum / cum.cummax() - 1
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else np.nan
    return pd.Series({
        "CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino,
        "Calmar": calmar, "MaxDD": max_dd, "HitRate": (r > 0).mean(),
        "N_months": len(r),
    }, name=name)

START_DT = "2002-01-31"  # warm-up done
END_DT   = prices_tech.index[-1]

ret1 = bt1.loc[START_DT:END_DT, "net_return"]
ret2 = bt2.loc[START_DT:END_DT, "net_return"]
ret3 = bt3.loc[START_DT:END_DT, "net_return"]

spy_ret = benchmarks["SPY"].pct_change()
xlk_ret = benchmarks["XLK"].pct_change()
mtum_ret = benchmarks["MTUM"].pct_change()
qual_ret = benchmarks["QUAL"].pct_change()
usmv_ret = benchmarks["USMV"].pct_change()

summary = pd.concat([
    perf_metrics(ret1, name="S1: Macro-Overlay Tech (long-only)"),
    perf_metrics(ret2, name="S2: Multi-Factor Tech L/S"),
    perf_metrics(ret3, name="S3: Tech + VIX L/S"),
    perf_metrics(spy_ret.loc[START_DT:END_DT], name="SPY"),
    perf_metrics(xlk_ret.loc[START_DT:END_DT], name="XLK (tech ETF)"),
    perf_metrics(mtum_ret.dropna(), name="MTUM"),
    perf_metrics(qual_ret.dropna(), name="QUAL"),
    perf_metrics(usmv_ret.dropna(), name="USMV"),
], axis=1).T

turnovers = {
    "S1": bt1.loc[START_DT:END_DT, "turnover"].mean() * 12,
    "S2": bt2.loc[START_DT:END_DT, "turnover"].mean() * 12,
    "S3": bt3.loc[START_DT:END_DT, "turnover"].mean() * 12,
}

print("\n" + "=" * 95)
print("GSD2T — THREE STRATEGIES ON S&P 500 TECH UNIVERSE (73 stocks)")
print("Simulated, monthly rebalance, net of 15 bps round-trip cost")
print("=" * 95)
print(summary.round(3).to_string())
print(f"\nAnnual turnover  S1: {turnovers['S1']:.1%}   S2: {turnovers['S2']:.1%}   S3: {turnovers['S3']:.1%}")

# %% [markdown]
# ## 8. Factor regression vs FF5+MOM

# %%
def load_ff_factors_monthly():
    ff5 = pd.read_csv(DATA_ROOT / "Folder_Macro_Factors_.187814089" / "content" / "F-F_Research_Data_5_Factors_2x3_daily.CSV",
                      skiprows=3, index_col=0)
    ff5.columns = [c.strip() for c in ff5.columns]
    ff5.index = pd.to_datetime(ff5.index.astype(str), format="%Y%m%d")
    ff5 = ff5 / 100.0
    mom = pd.read_csv(DATA_ROOT / "Folder_Macro_Factors_.187814089" / "content" / "F-F_Momentum_Factor_daily.CSV",
                      skiprows=13, index_col=0, skipfooter=2, engine="python")
    mom.columns = ["Mom"]
    mom = mom.dropna()
    mom.index = pd.to_datetime(mom.index.astype(str).str.strip(), format="%Y%m%d", errors="coerce")
    mom = mom.dropna() / 100.0
    daily = ff5.join(mom, how="inner")
    monthly = (1 + daily).resample("ME").prod() - 1
    monthly.index = to_month_end(monthly.index)
    return monthly
factors_m = load_ff_factors_monthly()

def alpha_regression(r, factors_m):
    cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
    df = pd.concat([r.rename("y"), factors_m[cols]], axis=1).dropna()
    X = sm.add_constant(df[cols])
    return sm.OLS(df["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 6})

rf_aligned = factors_m["RF"]
fr1 = alpha_regression(ret1 - rf_aligned.reindex(ret1.index), factors_m)
fr2 = alpha_regression(ret2 - rf_aligned.reindex(ret2.index), factors_m)
fr3 = alpha_regression(ret3 - rf_aligned.reindex(ret3.index), factors_m)

for name, fr in [("S1", fr1), ("S2", fr2), ("S3", fr3)]:
    print(f"\n{name}: alpha {fr.params['const']*12*100:.2f}% (t={fr.tvalues['const']:.2f}), R²={fr.rsquared:.2f}")
    print("  betas: " + ", ".join(f"{k}={v:+.2f}" for k, v in fr.params.drop('const').items()))

# %% [markdown]
# ## 9. Stress tests

# %%
stress_windows = {
    "Dot-com (2000-09 to 2002-10)":       ("2000-09-30", "2002-10-31"),
    "GFC (2007-10 to 2009-02)":           ("2007-10-31", "2009-02-28"),
    "Eurozone (2011-07 to 2011-09)":      ("2011-07-31", "2011-09-30"),
    "China (2015-08 to 2016-02)":         ("2015-08-31", "2016-02-29"),
    "Vol spike (2018-10 to 2018-12)":     ("2018-10-31", "2018-12-31"),
    "COVID (2020-02 to 2020-04)":         ("2020-02-29", "2020-04-30"),
    "2022 bear (2021-12 to 2022-09)":     ("2021-12-31", "2022-09-30"),
}
stress_rows = []
for w, (s, e) in stress_windows.items():
    def tot(r): return (1 + r.loc[s:e].dropna()).prod() - 1
    def dd(r):
        c = (1 + r.loc[s:e].dropna()).cumprod()
        return (c / c.cummax() - 1).min() if len(c) else np.nan
    stress_rows.append({
        "window": w,
        "S1_total": tot(ret1), "S2_total": tot(ret2), "S3_total": tot(ret3),
        "SPY_total": tot(spy_ret), "XLK_total": tot(xlk_ret),
        "S1_dd": dd(ret1), "S2_dd": dd(ret2), "S3_dd": dd(ret3),
    })
stress = pd.DataFrame(stress_rows).set_index("window")
print("\nStress tests:")
print(stress.round(3).to_string())

# %% [markdown]
# ## 10. JSON export

# %%
def ser_pairs(s):
    return [[ts.strftime("%Y-%m-%d"), float(v)] for ts, v in s.dropna().items()]
def cum_pairs(s):
    return ser_pairs((1 + s.dropna()).cumprod())
def dd_pairs(s):
    cum = (1 + s.dropna()).cumprod()
    return ser_pairs(cum / cum.cummax() - 1)

dashboard = {
    "meta": {
        "fund_name": "GSD2T Asset Management",
        "comparison_label": "Three strategies on the same S&P 500 Tech universe",
        "universe": f"S&P 500 ∩ GICS Information Technology ({len(tech_tickers)} stocks)",
        "window": f"{START_DT[:7]} to {END_DT:%Y-%m}",
        "tc_bps": TC_BPS,
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
    },
    "strategies": {
        "macro_overlay": {
            "name": "Macro-Overlay Tech",
            "description": "Long top quartile of tech stocks by 12-1m momentum. Gross exposure scaled by macro composite (VIX, credit, yield curve, SPX trend). Cash sleeve earns RF.",
            "universe_n": len(tech_tickers),
            "construction": "Long-only top quartile (≈18 stocks). Macro gross-exposure overlay in [30%, 100%].",
            "tc_bps": TC_BPS,
            "equity_curve": cum_pairs(ret1),
            "drawdown":     dd_pairs(ret1),
            "metrics": {
                "CAGR": float(summary.loc["S1: Macro-Overlay Tech (long-only)", "CAGR"]),
                "Vol": float(summary.loc["S1: Macro-Overlay Tech (long-only)", "Vol"]),
                "Sharpe": float(summary.loc["S1: Macro-Overlay Tech (long-only)", "Sharpe"]),
                "Sortino": float(summary.loc["S1: Macro-Overlay Tech (long-only)", "Sortino"]),
                "Calmar": float(summary.loc["S1: Macro-Overlay Tech (long-only)", "Calmar"]),
                "MaxDD": float(summary.loc["S1: Macro-Overlay Tech (long-only)", "MaxDD"]),
                "HitRate": float(summary.loc["S1: Macro-Overlay Tech (long-only)", "HitRate"]),
                "Turnover": float(turnovers["S1"]),
                "Alpha_ann": float(fr1.params["const"] * 12),
                "Alpha_t": float(fr1.tvalues["const"]),
            },
        },
        "multi_factor": {
            "name": "Multi-Factor Tech L/S",
            "description": "Cross-sectional 3-factor composite (momentum + low-vol + reversal) within tech. Long top quintile, short bottom quintile, dollar-neutral.",
            "universe_n": len(tech_tickers),
            "construction": "L/S top vs bottom quintile (≈15 long / 15 short). Dollar-neutral, no leverage.",
            "tc_bps": TC_BPS,
            "equity_curve": cum_pairs(ret2),
            "drawdown":     dd_pairs(ret2),
            "metrics": {
                "CAGR": float(summary.loc["S2: Multi-Factor Tech L/S", "CAGR"]),
                "Vol": float(summary.loc["S2: Multi-Factor Tech L/S", "Vol"]),
                "Sharpe": float(summary.loc["S2: Multi-Factor Tech L/S", "Sharpe"]),
                "Sortino": float(summary.loc["S2: Multi-Factor Tech L/S", "Sortino"]),
                "Calmar": float(summary.loc["S2: Multi-Factor Tech L/S", "Calmar"]),
                "MaxDD": float(summary.loc["S2: Multi-Factor Tech L/S", "MaxDD"]),
                "HitRate": float(summary.loc["S2: Multi-Factor Tech L/S", "HitRate"]),
                "Turnover": float(turnovers["S2"]),
                "Alpha_ann": float(fr2.params["const"] * 12),
                "Alpha_t": float(fr2.tvalues["const"]),
            },
        },
        "vix_overlay": {
            "name": "Tech + VIX L/S",
            "description": "Cross-sectional 12-1m momentum within tech. Long top quartile, short bottom quartile. Gross exposure scaled by VIX regime (100% if VIX<16, scaling to 0% above 32).",
            "universe_n": len(tech_tickers),
            "construction": "L/S top vs bottom quartile (≈18 long / 18 short). VIX overlay scales gross.",
            "tc_bps": TC_BPS,
            "equity_curve": cum_pairs(ret3),
            "drawdown":     dd_pairs(ret3),
            "metrics": {
                "CAGR": float(summary.loc["S3: Tech + VIX L/S", "CAGR"]),
                "Vol": float(summary.loc["S3: Tech + VIX L/S", "Vol"]),
                "Sharpe": float(summary.loc["S3: Tech + VIX L/S", "Sharpe"]),
                "Sortino": float(summary.loc["S3: Tech + VIX L/S", "Sortino"]),
                "Calmar": float(summary.loc["S3: Tech + VIX L/S", "Calmar"]),
                "MaxDD": float(summary.loc["S3: Tech + VIX L/S", "MaxDD"]),
                "HitRate": float(summary.loc["S3: Tech + VIX L/S", "HitRate"]),
                "Turnover": float(turnovers["S3"]),
                "Alpha_ann": float(fr3.params["const"] * 12),
                "Alpha_t": float(fr3.tvalues["const"]),
            },
        },
    },
    "benchmarks": {
        "SPY":  {"equity_curve": cum_pairs(spy_ret.loc[START_DT:END_DT]),
                 "drawdown":     dd_pairs(spy_ret.loc[START_DT:END_DT])},
        "XLK":  {"equity_curve": cum_pairs(xlk_ret.loc[START_DT:END_DT]),
                 "drawdown":     dd_pairs(xlk_ret.loc[START_DT:END_DT])},
        "MTUM": {"equity_curve": cum_pairs(mtum_ret.dropna()), "drawdown": []},
        "QUAL": {"equity_curve": cum_pairs(qual_ret.dropna()), "drawdown": []},
        "USMV": {"equity_curve": cum_pairs(usmv_ret.dropna()), "drawdown": []},
    },
    "benchmark_metrics": [
        {"name": "SPY",  **{k: float(v) for k, v in summary.loc["SPY"].items()}},
        {"name": "XLK",  **{k: float(v) for k, v in summary.loc["XLK (tech ETF)"].items()}},
        {"name": "MTUM", **{k: float(v) for k, v in summary.loc["MTUM"].items()}},
        {"name": "QUAL", **{k: float(v) for k, v in summary.loc["QUAL"].items()}},
        {"name": "USMV", **{k: float(v) for k, v in summary.loc["USMV"].items()}},
    ],
    "stress_tests": [
        {**{k: (None if pd.isna(v) else float(v)) for k, v in r.items()}, "window": idx}
        for idx, r in stress.iterrows()
    ],
    "macro_regime": {
        "score":          ser_pairs(macro_composite.loc[START_DT:END_DT]),
        "gross_exposure": ser_pairs(gross_macro.loc[START_DT:END_DT]),
    },
    "vix_path": ser_pairs(vix["VIX"].loc[START_DT:END_DT]),
}

out_path = Path("tech_comparison_data.json")
out_path.write_text(json.dumps(dashboard, indent=2, default=str))
print(f"\nWrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")
