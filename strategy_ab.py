# %% [markdown]
# # GSD2T — Strategy A vs Strategy B comparison
#
# **Strategy A:** Multi-factor equity L/S on S&P 500 (value, momentum, low-vol, reversal)
# **Strategy B:** Tech-sector L/S with VIX gross-exposure overlay
#
# Both report against a common dashboard data file (`strategy_comparison.json`).

# %%
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import statsmodels.api as sm
from scipy import stats
import warnings
warnings.filterwarnings("ignore")

CACHE = Path("data_cache")
DATA_ROOT = Path(__file__).resolve().parent / "course_data"  # bundled course data inside the repo
COURSE_DATA = DATA_ROOT / "Folder_Codes_amp_Data_.187814137" / "content"

# %% [markdown]
# ## 1. Load data

# %%
prices = pd.read_csv(CACHE / "prices_sp500_monthly.csv", index_col=0, parse_dates=True)
benchmarks = pd.read_csv(CACHE / "prices_benchmarks_monthly.csv", index_col=0, parse_dates=True)
vix = pd.read_csv(CACHE / "prices_vix_monthly.csv", index_col=0, parse_dates=True)
constituents = pd.read_csv(CACHE / "sp500_constituents.csv")
# Cached VIX file has column "^VIX"
vix.columns = ["VIX"] if vix.shape[1] == 1 else vix.columns

def to_month_end(idx):
    return pd.to_datetime(idx).to_period("M").to_timestamp("M")
prices.index = to_month_end(prices.index)
benchmarks.index = to_month_end(benchmarks.index)
vix.index = to_month_end(vix.index)

returns = prices.pct_change()

print(f"Prices: {prices.shape}, {prices.index.min():%Y-%m} to {prices.index.max():%Y-%m}")
print(f"VIX:    {vix.index.min():%Y-%m} to {vix.index.max():%Y-%m}")

# %% [markdown]
# ## 2. Factor construction
#
# All factors are computed at month-end *t* using only information through *t*. Returns realized in month *t+1*.
# Cross-sectional z-scores standardize each factor's scale before averaging into a composite.

# %%
def zscore_cs(panel):
    """Cross-sectional z-score: each row standardized across columns."""
    return panel.sub(panel.mean(axis=1), axis=0).div(panel.std(axis=1), axis=0)

# --- Momentum: 12m return, skip 1m
log_ret = np.log1p(returns)
mom = log_ret.shift(1).rolling(11).sum()
mom_z = zscore_cs(mom)

# --- Low-vol: inverse trailing 12m volatility
vol12 = returns.shift(1).rolling(12).std()
lowvol_z = zscore_cs(-vol12)  # invert: high score = LOW vol

# --- Short-term reversal: invert 1m return
reversal_z = zscore_cs(-returns.shift(0))  # already lagged via shift in backtest

# Note on the value factor:
# The course us_per.csv covers a 326-ticker US universe with point-in-time P/E ratios
# 2000-04/2020. Intersection with the current S&P 500 (503 names) is only ~52 tickers —
# the course panel is broader-US not S&P-500-specific, so a clean value factor on the
# pitched universe would require an external source (Compustat / SimFin). We disclose
# this in the deck and run the primary backtest with three price-based factors that have
# universal coverage and zero look-ahead concerns. Value is a Phase 2 enhancement.

factor_dict = {"momentum": mom_z, "lowvol": lowvol_z, "reversal": reversal_z}
composite = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
counts    = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
for fname, fz in factor_dict.items():
    fz_aligned = fz.reindex(index=prices.index, columns=prices.columns)
    composite = composite.add(fz_aligned.fillna(0), fill_value=0)
    counts    = counts.add(fz_aligned.notna().astype(float), fill_value=0)
composite_mean = composite.div(counts).where(counts > 0)
composite_strict = composite_mean.where(counts >= 3)  # require ALL 3 factors

print("Factor coverage at last available date:")
last_idx = prices.index[-2]
print(f"  Date: {last_idx:%Y-%m}")
print(f"  Momentum: {mom_z.loc[last_idx].notna().sum()} tickers")
print(f"  Low-vol:  {lowvol_z.loc[last_idx].notna().sum()} tickers")
print(f"  Reversal: {reversal_z.loc[last_idx].notna().sum()} tickers")
print(f"  Composite (3 of 3 factors): {composite_strict.loc[last_idx].notna().sum()} tickers")

# %% [markdown]
# ## 3. Strategy A: multi-factor L/S on S&P 500
#
# Long top quintile, short bottom quintile by composite score. Dollar-neutral.

# %%
def quintile_weights(scores, q=0.20):
    """Returns (long_w, short_w): each row sums to 1 across selected names."""
    ranks = scores.rank(axis=1, pct=True)
    long_mask  = ranks >= (1 - q)
    short_mask = ranks <= q
    long_w  = long_mask.astype(float).div(long_mask.sum(axis=1).replace(0, np.nan), axis=0)
    short_w = short_mask.astype(float).div(short_mask.sum(axis=1).replace(0, np.nan), axis=0)
    return long_w.fillna(0.0), short_w.fillna(0.0)

def backtest_ls(scores, returns_panel, q=0.20, gross_scalar=None, tc_bps=15, name="strategy"):
    """Long-short backtest. Returns dict with .returns, .turnover, .weights."""
    wL, wS = quintile_weights(scores, q=q)
    w_net = wL - wS  # dollar-neutral
    if gross_scalar is not None:
        s = gross_scalar.reindex(w_net.index).fillna(0.0)
        w_net = w_net.mul(s, axis=0)

    # Portfolio return in month t+1 from weights set at end of month t
    aligned = w_net.shift(1).fillna(0.0)
    R = returns_panel.reindex_like(aligned).fillna(0.0)
    port_gross = (aligned * R).sum(axis=1)

    # Turnover (sum of |Δw|)
    dw = (w_net - w_net.shift(1)).abs().sum(axis=1)
    tc = dw * (tc_bps / 10000.0)
    port_net = port_gross - tc

    return pd.DataFrame({
        "gross_return": port_gross,
        "tc":           tc,
        "net_return":   port_net,
        "turnover":     dw,
        "long_count":   (wL > 0).sum(axis=1),
        "short_count":  (wS > 0).sum(axis=1),
    })

START_A = "2001-01-31"
END_OOS = prices.index[-1]

bt_A = backtest_ls(composite_strict, returns, q=0.20, tc_bps=15)
print(f"\nStrategy A returns: {bt_A['net_return'].dropna().shape[0]} non-NaN months")
print(f"  Window: {START_A} to {END_OOS:%Y-%m-%d}")

# %% [markdown]
# ## 4. Strategy B: Tech L/S with VIX gross-exposure overlay
#
# Within the GICS Information Technology subset, rank by 12-1m momentum, long top quartile,
# short bottom quartile. Gross exposure scaled by VIX regime.

# %%
tech_tickers = constituents[constituents["sector"] == "Information Technology"]["ticker"].tolist()
tech_tickers = [t for t in tech_tickers if t in prices.columns]
print(f"Tech universe: {len(tech_tickers)} tickers")

returns_tech = returns[tech_tickers]
mom_tech = log_ret[tech_tickers].shift(1).rolling(11).sum()
mom_tech_z = zscore_cs(mom_tech)

# VIX regime to gross exposure mapping
vix_series = vix["VIX"].reindex(prices.index).ffill()

def vix_to_exposure(v):
    """Map VIX level to gross exposure. Lower VIX = full size."""
    out = pd.Series(index=v.index, dtype=float)
    out[v < 16]                = 1.00
    out[(v >= 16) & (v < 24)]  = 0.75
    out[(v >= 24) & (v < 32)]  = 0.40
    out[v >= 32]               = 0.00
    return out.shift(1)  # use prior month's VIX to decide this month's exposure

gross_B = vix_to_exposure(vix_series)
print(f"Mean gross exposure (Strategy B): {gross_B.mean():.2f}")
print(f"Months at full exposure: {(gross_B == 1.0).sum()} / {gross_B.notna().sum()}")
print(f"Months at zero exposure: {(gross_B == 0.0).sum()}")

bt_B = backtest_ls(mom_tech_z, returns_tech, q=0.25, gross_scalar=gross_B, tc_bps=15)

# %% [markdown]
# ## 5. Compare against benchmarks

# %%
spy_ret  = benchmarks["SPY"].pct_change()
xlk_ret  = benchmarks["XLK"].pct_change()
mtum_ret = benchmarks["MTUM"].pct_change()
qual_ret = benchmarks["QUAL"].pct_change()
vlue_ret = benchmarks["VLUE"].pct_change()
usmv_ret = benchmarks["USMV"].pct_change()

# %%
def perf_metrics(returns, periods_per_year=12, name="strategy"):
    r = returns.dropna()
    if len(r) < 12:
        return pd.Series({"CAGR": np.nan, "Vol": np.nan, "Sharpe": np.nan, "Sortino": np.nan,
                          "Calmar": np.nan, "MaxDD": np.nan, "HitRate": np.nan, "N_months": len(r)}, name=name)
    cum = (1 + r).cumprod()
    cagr = cum.iloc[-1] ** (periods_per_year / len(r)) - 1
    vol = r.std() * np.sqrt(periods_per_year)
    sharpe = (r.mean() * periods_per_year) / (r.std() * np.sqrt(periods_per_year)) if r.std() > 0 else np.nan
    downside = r[r < 0].std() * np.sqrt(periods_per_year)
    sortino = (r.mean() * periods_per_year) / downside if downside > 0 else np.nan
    dd = cum / cum.cummax() - 1
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else np.nan
    return pd.Series({
        "CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino,
        "Calmar": calmar, "MaxDD": max_dd, "HitRate": (r > 0).mean(), "N_months": len(r),
    }, name=name)

mask_full_A = (bt_A.index >= START_A) & (bt_A.index <= END_OOS)
ret_A_full = bt_A.loc[mask_full_A, "net_return"]
ret_B_full = bt_B.loc[START_A:END_OOS, "net_return"]

# Split A: pre-2020 vs post-2020 (just for OOS sanity check, not a model change)
mask_pre  = (bt_A.index >= START_A) & (bt_A.index <= "2019-12-31")
mask_post = (bt_A.index >= "2020-01-31") & (bt_A.index <= END_OOS)

summary = pd.concat([
    perf_metrics(bt_A.loc[mask_full_A, "net_return"], name="Strategy A (full 2001-2026)"),
    perf_metrics(bt_A.loc[mask_pre, "net_return"],    name="Strategy A IS (2001-2019)"),
    perf_metrics(bt_A.loc[mask_post, "net_return"],   name="Strategy A OOS (2020-2026)"),
    perf_metrics(ret_B_full,                          name="Strategy B (Tech+VIX, 2001-2026)"),
    perf_metrics(spy_ret.loc[START_A:END_OOS],        name="SPY"),
    perf_metrics(xlk_ret.loc[START_A:END_OOS],        name="XLK"),
    perf_metrics(mtum_ret.dropna(),                   name="MTUM (2013+)"),
    perf_metrics(qual_ret.dropna(),                   name="QUAL (2013+)"),
    perf_metrics(vlue_ret.dropna(),                   name="VLUE (2013+)"),
    perf_metrics(usmv_ret.dropna(),                   name="USMV (2011+)"),
], axis=1).T

ann_to_A = bt_A.loc[mask_full_A, "turnover"].mean() * 12
ann_to_B = bt_B.loc[START_A:END_OOS, "turnover"].mean() * 12

print("\n" + "=" * 92)
print("STRATEGY COMPARISON — HEADLINE METRICS (simulated, net of 15 bps round-trip)")
print("=" * 92)
print(summary.round(3).to_string())
print(f"\nAnnual turnover  A: {ann_to_A:.0%}   B: {ann_to_B:.0%}")

# %% [markdown]
# ## 6. Factor regression — alpha vs FF5+MOM

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
rf = factors_m["RF"]

def factor_regression(returns_series, factors_m, factor_cols=None):
    if factor_cols is None:
        factor_cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
    df = pd.concat([returns_series.rename("y"), factors_m[factor_cols]], axis=1).dropna()
    X = sm.add_constant(df[factor_cols])
    return sm.OLS(df["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 6})

# Net-of-RF excess returns
A_excess = ret_A_full - rf.reindex(ret_A_full.index)
B_excess = bt_B.loc[START_A:END_OOS, "net_return"] - rf.reindex(bt_B.loc[START_A:END_OOS].index)

model_A = factor_regression(A_excess.dropna(), factors_m)
model_B = factor_regression(B_excess.dropna(), factors_m)

print("\nStrategy A: alpha vs FF5+MOM")
print(f"  α (annualized): {model_A.params['const']*12*100:.2f}%   t={model_A.tvalues['const']:.2f}   R²={model_A.rsquared:.3f}")
print(f"  Betas: " + ", ".join(f"{k}={v:.2f}" for k, v in model_A.params.drop('const').items()))

print("\nStrategy B: alpha vs FF5+MOM")
print(f"  α (annualized): {model_B.params['const']*12*100:.2f}%   t={model_B.tvalues['const']:.2f}   R²={model_B.rsquared:.3f}")
print(f"  Betas: " + ", ".join(f"{k}={v:.2f}" for k, v in model_B.params.drop('const').items()))

# %% [markdown]
# ## 7. Stress windows

# %%
stress_windows = {
    "Dot-com (2000-09 to 2002-10)":        ("2000-09-30", "2002-10-31"),
    "GFC (2007-10 to 2009-02)":            ("2007-10-31", "2009-02-28"),
    "Eurozone (2011-07 to 2011-09)":       ("2011-07-31", "2011-09-30"),
    "China (2015-08 to 2016-02)":          ("2015-08-31", "2016-02-29"),
    "Vol spike (2018-10 to 2018-12)":      ("2018-10-31", "2018-12-31"),
    "COVID (2020-02 to 2020-04)":          ("2020-02-29", "2020-04-30"),
    "2022 bear (2021-12 to 2022-09)":      ("2021-12-31", "2022-09-30"),
}

stress_rows = []
for name, (s, e) in stress_windows.items():
    def tot(r): return (1 + r.loc[s:e].dropna()).prod() - 1
    def dd(r):
        cum = (1 + r.loc[s:e].dropna()).cumprod()
        return (cum / cum.cummax() - 1).min() if len(cum) else np.nan
    row = {
        "Window": name,
        "A_total": tot(ret_A_full),
        "B_total": tot(bt_B.loc[START_A:END_OOS, "net_return"]),
        "SPY_total": tot(spy_ret),
        "XLK_total": tot(xlk_ret),
        "A_dd": dd(ret_A_full),
        "B_dd": dd(bt_B.loc[START_A:END_OOS, "net_return"]),
    }
    stress_rows.append(row)
stress = pd.DataFrame(stress_rows).set_index("Window")
print("\nStress tests:")
print(stress.round(3).to_string())

# %% [markdown]
# ## 8. JSON export for the comparison dashboard

# %%
def ser_pairs(s):
    return [[ts.strftime("%Y-%m-%d"), float(v)] for ts, v in s.dropna().items()]

def cum_pairs(s):
    return ser_pairs((1 + s.dropna()).cumprod())

def dd_pairs(s):
    cum = (1 + s.dropna()).cumprod()
    return ser_pairs(cum / cum.cummax() - 1)

window_A = (ret_A_full.index >= START_A)
ret_A_for_export = ret_A_full[window_A]

dashboard = {
    "meta": {
        "fund_name": "GSD2T Asset Management",
        "comparison_label": "Strategy A (multi-factor L/S) vs Strategy B (tech+VIX)",
        "universe_size_A": int(prices.shape[1]),
        "universe_size_B": len(tech_tickers),
        "window": f"{START_A[:7]} to {END_OOS:%Y-%m}",
        "factors_A": "momentum (12-1m) + low-vol (12m) + short-term reversal (1m). Value factor dropped from primary backtest due to data overlap issues — see notes.",
        "vix_overlay_B": "Gross exposure: 100% if VIX<16, 75% if 16-24, 40% if 24-32, 0% if >=32. Lagged 1 month.",
        "tc_bps": 15,
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
    },
    "summary": [
        {"strategy": idx, **{k: (None if pd.isna(v) else float(v)) for k, v in row.items()}}
        for idx, row in summary.iterrows()
    ],
    "turnover": {"A": ann_to_A, "B": ann_to_B},
    "equity_curves": {
        "Strategy A":   cum_pairs(ret_A_for_export),
        "Strategy B":   cum_pairs(bt_B.loc[START_A:END_OOS, "net_return"]),
        "SPY":          cum_pairs(spy_ret.loc[START_A:END_OOS]),
        "XLK":          cum_pairs(xlk_ret.loc[START_A:END_OOS]),
    },
    "drawdowns": {
        "Strategy A": dd_pairs(ret_A_for_export),
        "Strategy B": dd_pairs(bt_B.loc[START_A:END_OOS, "net_return"]),
        "SPY":        dd_pairs(spy_ret.loc[START_A:END_OOS]),
    },
    "rolling_12m": {
        "Strategy A": ser_pairs((1 + ret_A_for_export).rolling(12).apply(lambda x: x.prod() - 1, raw=True)),
        "Strategy B": ser_pairs((1 + bt_B.loc[START_A:END_OOS, "net_return"]).rolling(12).apply(lambda x: x.prod() - 1, raw=True)),
        "SPY":        ser_pairs((1 + spy_ret.loc[START_A:END_OOS]).rolling(12).apply(lambda x: x.prod() - 1, raw=True)),
    },
    "vix_and_exposure": {
        "VIX":            ser_pairs(vix_series.loc[START_A:END_OOS]),
        "B_gross_exposure": ser_pairs(gross_B.loc[START_A:END_OOS]),
    },
    "factor_betas": {
        "Strategy A": {
            "alpha_ann": float(model_A.params["const"] * 12),
            "alpha_tstat": float(model_A.tvalues["const"]),
            "rsquared": float(model_A.rsquared),
            "betas": {k: float(v) for k, v in model_A.params.drop("const").items()},
            "tstats": {k: float(v) for k, v in model_A.tvalues.drop("const").items()},
        },
        "Strategy B": {
            "alpha_ann": float(model_B.params["const"] * 12),
            "alpha_tstat": float(model_B.tvalues["const"]),
            "rsquared": float(model_B.rsquared),
            "betas": {k: float(v) for k, v in model_B.params.drop("const").items()},
            "tstats": {k: float(v) for k, v in model_B.tvalues.drop("const").items()},
        },
    },
    "stress_tests": [
        {"window": idx, **{k: (None if pd.isna(v) else float(v)) for k, v in row.items()}}
        for idx, row in stress.iterrows()
    ],
    "factor_etf_comparison": {
        "MTUM": cum_pairs(mtum_ret.dropna()),
        "QUAL": cum_pairs(qual_ret.dropna()),
        "VLUE": cum_pairs(vlue_ret.dropna()),
        "USMV": cum_pairs(usmv_ret.dropna()),
    },
}

out_path = Path("strategy_comparison.json")
with open(out_path, "w") as f:
    json.dump(dashboard, f, indent=2, default=str)
print(f"\nWrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")
