# %% [markdown]
# # GSD2T Macro-Overlay Tech — Full Institutional Appendix
#
# Strategy 1 ("Macro-Overlay Tech") with full backtest hygiene:
# - Walk-forward IS / OOS split
# - Parameter sensitivity grid
# - Deflated Sharpe Ratio
# - Capacity analysis at $100M / soft cap
# - Factor regression with Newey-West HAC standard errors
# - Stress scenarios
#
# Output: `gsd2t_full.json` consumed by the S1-focused dashboard.

# %%
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import statsmodels.api as sm
from scipy import stats
import warnings
warnings.filterwarnings("ignore")

CACHE = Path("data_cache")
DATA_ROOT = Path(__file__).resolve().parent / "course_data"  # bundled course data inside the repo

def to_month_end(idx):
    return pd.to_datetime(idx).to_period("M").to_timestamp("M")

# %%
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

# %% [markdown]
# ## Macro composite — same recipe as strategies_tech.py

# %%
def rolling_zscore(s, w=60, mp=24):
    return (s - s.rolling(w, min_periods=mp).mean()) / s.rolling(w, min_periods=mp).std()

def build_macro(vix_s, mx):
    idx = vix_s.index
    comp = pd.DataFrame(index=idx)
    comp["vix"] = -rolling_zscore(vix_s)
    cred = np.log(mx["IEF"]).reindex(idx).ffill() - np.log(mx["HYG"]).reindex(idx).ffill()
    comp["credit"] = -rolling_zscore(cred.diff(12))
    tnx = mx["^TNX"].reindex(idx).ffill()
    comp["yield"] = -rolling_zscore(tnx.diff(12))
    spx = mx["^GSPC"].reindex(idx).ffill()
    comp["trend"] = rolling_zscore(np.log(spx).diff(1).shift(1).rolling(11).sum())
    return comp.mean(axis=1).clip(-2, 2).shift(1), comp

macro_score, macro_components = build_macro(vix["VIX"], macro_px)

def macro_to_exposure(s):
    return np.clip(0.65 + 0.175 * s, 0.3, 1.0)
gross_macro = macro_to_exposure(macro_score)

# %% [markdown]
# ## Backtest engine

# %%
def zscore_cs(panel):
    return panel.sub(panel.mean(axis=1), axis=0).div(panel.std(axis=1), axis=0)

def signal_momentum(returns, lookback=12, skip=1):
    log_r = np.log1p(returns)
    return log_r.shift(skip).rolling(lookback - skip).sum()

def quantile_weights_long(scores, q=0.25):
    ranks = scores.rank(axis=1, pct=True)
    mask = ranks >= (1 - q)
    w = mask.astype(float)
    return w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)

TC_BPS = 15

def backtest_macro_overlay(returns_panel, lookback=12, skip=1, q=0.25,
                            gross_scalar=None, tc_bps=TC_BPS, rf=None):
    mom = signal_momentum(returns_panel, lookback=lookback, skip=skip)
    mom_z = zscore_cs(mom)
    wL = quantile_weights_long(mom_z, q=q)
    if gross_scalar is not None:
        s = gross_scalar.reindex(wL.index).fillna(0.0).clip(lower=0.0)
        wL = wL.mul(s, axis=0)
    R = returns_panel.reindex_like(wL).fillna(0.0)
    port_gross = (wL.shift(1).fillna(0.0) * R).sum(axis=1)
    if rf is not None and gross_scalar is not None:
        cash_w = (1.0 - wL.sum(axis=1)).clip(lower=0.0)
        port_gross = port_gross + (cash_w.shift(1).fillna(0.0) * rf.reindex(wL.index).fillna(0.0))
    dw = (wL - wL.shift(1)).abs().sum(axis=1)
    tc = dw * (tc_bps / 10000.0)
    port_net = port_gross - tc
    return pd.DataFrame({
        "gross_return": port_gross, "tc": tc, "net_return": port_net,
        "turnover": dw, "weights": wL.sum(axis=1),
    }), wL

# %% [markdown]
# ## Run primary backtest

# %%
def load_rf_monthly():
    ff5 = pd.read_csv(DATA_ROOT / "Folder_Macro_Factors_.187814089" / "content" / "F-F_Research_Data_5_Factors_2x3_daily.CSV",
                      skiprows=3, index_col=0)
    ff5.columns = [c.strip() for c in ff5.columns]
    ff5.index = pd.to_datetime(ff5.index.astype(str), format="%Y%m%d")
    rf = (1 + ff5["RF"] / 100.0).resample("ME").prod() - 1
    rf.index = to_month_end(rf.index)
    return rf
rf = load_rf_monthly()

bt, wL = backtest_macro_overlay(returns_tech, lookback=12, skip=1, q=0.25,
                                  gross_scalar=gross_macro, rf=rf, tc_bps=TC_BPS)

START_DT = "2002-01-31"
END_DT   = prices_tech.index[-1]
ret = bt.loc[START_DT:END_DT, "net_return"]

# %%
def perf_metrics(returns, periods_per_year=12, rf_series=None):
    r = returns.dropna()
    if len(r) < 12:
        return {k: None for k in ["CAGR","Vol","Sharpe","Sortino","Calmar","MaxDD","HitRate","N_months"]}
    cum = (1 + r).cumprod()
    cagr = cum.iloc[-1] ** (periods_per_year / len(r)) - 1
    vol = r.std() * np.sqrt(periods_per_year)
    if rf_series is not None:
        excess = r - rf_series.reindex(r.index).fillna(0)
        sharpe = (excess.mean() * periods_per_year) / (excess.std() * np.sqrt(periods_per_year))
    else:
        sharpe = (r.mean() * periods_per_year) / (r.std() * np.sqrt(periods_per_year))
    downside = r[r < 0].std() * np.sqrt(periods_per_year)
    sortino = (r.mean() * periods_per_year) / downside if downside > 0 else np.nan
    dd = cum / cum.cummax() - 1
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else np.nan
    return {"CAGR": float(cagr), "Vol": float(vol), "Sharpe": float(sharpe),
            "Sortino": float(sortino) if pd.notna(sortino) else None,
            "Calmar": float(calmar) if pd.notna(calmar) else None,
            "MaxDD": float(max_dd), "HitRate": float((r > 0).mean()),
            "N_months": int(len(r))}

primary = perf_metrics(ret, rf_series=rf)
print("Primary backtest (2002-2026):", primary)

# %% [markdown]
# ## Walk-forward IS / OOS split
# IS: 2002-01 to 2015-12 (14 years). OOS: 2016-01 to 2026-05 (10.5 years).

# %%
IS_END   = "2015-12-31"
OOS_START = "2016-01-31"
is_metrics  = perf_metrics(bt.loc[START_DT:IS_END,  "net_return"], rf_series=rf)
oos_metrics = perf_metrics(bt.loc[OOS_START:END_DT, "net_return"], rf_series=rf)
print(f"\nIS  (2002-2015): {is_metrics}")
print(f"OOS (2016-2026): {oos_metrics}")

# %% [markdown]
# ## Parameter sensitivity — Sharpe across (lookback, quantile) grid

# %%
lookbacks = [6, 9, 12, 15, 18]
quantiles = [0.20, 0.25, 0.33]
sens = {}
for lb in lookbacks:
    for qq in quantiles:
        b, _ = backtest_macro_overlay(returns_tech, lookback=lb, skip=1, q=qq,
                                       gross_scalar=gross_macro, rf=rf, tc_bps=TC_BPS)
        m = perf_metrics(b.loc[START_DT:END_DT, "net_return"], rf_series=rf)
        sens[(lb, qq)] = m["Sharpe"]

sens_grid = np.array([[sens[(lb, qq)] for qq in quantiles] for lb in lookbacks])
print(f"\nSharpe sensitivity grid (rows: lookback {lookbacks}, cols: quartile {quantiles})")
print(np.round(sens_grid, 2))
print(f"Min/Max/Mean: {sens_grid.min():.2f} / {sens_grid.max():.2f} / {sens_grid.mean():.2f}")

# %% [markdown]
# ## Deflated Sharpe Ratio (Bailey & López de Prado 2014)

# %%
def deflated_sharpe(returns, n_trials, benchmark_sr=0.0):
    r = returns.dropna()
    n = len(r)
    sr = (r.mean() / r.std()) * np.sqrt(12)
    skew = stats.skew(r)
    kurt = stats.kurtosis(r, fisher=True)
    emc = 0.5772156649
    if n_trials > 1:
        emax = benchmark_sr + ((1 - emc) * stats.norm.ppf(1 - 1.0 / n_trials)
                               + emc * stats.norm.ppf(1 - 1.0 / (n_trials * np.e)))
    else:
        emax = benchmark_sr
    var = (1 - skew * sr + (kurt / 4.0) * sr**2) / (n - 1)
    if var > 0:
        z = (sr - emax) / np.sqrt(var)
        psr = stats.norm.cdf(z)
    else:
        psr = np.nan
    return float(sr), float(emax), float(psr)

n_trials = len(lookbacks) * len(quantiles)
sr_obs, sr_thr, psr = deflated_sharpe(ret - rf.reindex(ret.index), n_trials=n_trials)
print(f"\nDSR: observed SR={sr_obs:.2f}, threshold (n={n_trials})={sr_thr:.2f}, PSR={psr:.3f}")

# %% [markdown]
# ## Factor regression

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
rf_aligned = factors_m["RF"]

cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
df = pd.concat([(ret - rf_aligned.reindex(ret.index)).rename("y"), factors_m[cols]], axis=1).dropna()
X = sm.add_constant(df[cols])
model = sm.OLS(df["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
print(f"\nFactor regression: α = {model.params['const']*12*100:.2f}% (t={model.tvalues['const']:.2f}), R²={model.rsquared:.3f}")

# %% [markdown]
# ## Capacity analysis (at $100M)

# %%
avg_n_long = (wL > 0).sum(axis=1).loc[START_DT:END_DT].mean()
avg_monthly_turnover = bt.loc[START_DT:END_DT, "turnover"].mean()

# Average daily volume estimates for tech stocks — large caps are >$500M ADV
# Conservative: assume average tech stock has $300M ADV (smaller caps in S&P tech)
fund_nav = 100_000_000
avg_adv_per_stock = 300_000_000
max_pct_adv = 0.05
days_to_trade = 2
per_name_capacity = avg_adv_per_stock * max_pct_adv * days_to_trade  # $30M
typical_position_size = fund_nav / avg_n_long  # ~$5.6M at $100M
headroom = per_name_capacity / typical_position_size
soft_cap = per_name_capacity * avg_n_long

print(f"\nCapacity: avg holdings {avg_n_long:.1f}, avg monthly turnover {avg_monthly_turnover:.1%}")
print(f"Typical position at $100M: ${typical_position_size/1e6:.1f}M")
print(f"Per-name 5%-ADV × 2-day capacity: ${per_name_capacity/1e6:.0f}M  → headroom {headroom:.1f}×")
print(f"Implied soft AUM cap: ${soft_cap/1e9:.2f}B")

# %% [markdown]
# ## Stress tests

# %%
stress_windows = {
    "Dot-com (2000-09 → 2002-10)":      ("2000-09-30", "2002-10-31"),
    "GFC (2007-10 → 2009-02)":          ("2007-10-31", "2009-02-28"),
    "Eurozone (2011-07 → 2011-09)":     ("2011-07-31", "2011-09-30"),
    "China (2015-08 → 2016-02)":        ("2015-08-31", "2016-02-29"),
    "Vol spike (2018-10 → 2018-12)":    ("2018-10-31", "2018-12-31"),
    "COVID (2020-02 → 2020-04)":        ("2020-02-29", "2020-04-30"),
    "2022 bear (2021-12 → 2022-09)":    ("2021-12-31", "2022-09-30"),
}
spy_ret = benchmarks["SPY"].pct_change()
xlk_ret = benchmarks["XLK"].pct_change()
stress_rows = []
for w, (s, e) in stress_windows.items():
    def tot(r): return (1 + r.loc[s:e].dropna()).prod() - 1
    def dd(r):
        c = (1 + r.loc[s:e].dropna()).cumprod()
        return (c / c.cummax() - 1).min() if len(c) else np.nan
    stress_rows.append({
        "window": w,
        "fund_total": tot(ret), "spy_total": tot(spy_ret), "xlk_total": tot(xlk_ret),
        "fund_dd": dd(ret), "spy_dd": dd(spy_ret), "xlk_dd": dd(xlk_ret),
    })

# %% [markdown]
# ## Holdings snapshot — most recent

# %%
latest_idx = wL.dropna(how="all").iloc[-1].name
latest = wL.loc[latest_idx]
holdings = [{"sector": "Information Technology", "ticker": k, "weight": float(v)}
            for k, v in latest[latest > 0].sort_values(ascending=False).items()]
print(f"\nLatest holdings ({latest_idx:%Y-%m}): {len(holdings)} positions")

# Rolling 12m
roll12_fund = (1 + ret).rolling(12).apply(lambda x: x.prod() - 1, raw=True)
roll12_mkt  = (1 + spy_ret.loc[START_DT:END_DT]).rolling(12).apply(lambda x: x.prod() - 1, raw=True)
roll12_xlk  = (1 + xlk_ret.loc[START_DT:END_DT]).rolling(12).apply(lambda x: x.prod() - 1, raw=True)

# %% [markdown]
# ## JSON export

# %%
def pairs(s):
    return [[t.strftime("%Y-%m-%d"), float(v)] for t, v in s.dropna().items()]
def cum_pairs(s):
    return pairs((1 + s.dropna()).cumprod())
def dd_pairs(s):
    cum = (1 + s.dropna()).cumprod()
    return pairs(cum / cum.cummax() - 1)

output = {
    "meta": {
        "fund_name": "GSD2T Asset Management",
        "strategy": "Macro-Overlay Tech",
        "universe": f"S&P 500 ∩ GICS Information Technology ({len(tech_tickers)} stocks)",
        "window": f"{START_DT[:7]} to {END_DT:%Y-%m}",
        "tc_bps": TC_BPS,
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
    },
    "summary": {
        "Fund (full window)":  primary,
        "Fund IS (2002-2015)": is_metrics,
        "Fund OOS (2016-2026)": oos_metrics,
        "SPY":  perf_metrics(spy_ret.loc[START_DT:END_DT], rf_series=rf),
        "XLK":  perf_metrics(xlk_ret.loc[START_DT:END_DT], rf_series=rf),
        "MTUM": perf_metrics(benchmarks["MTUM"].pct_change().dropna(), rf_series=rf),
        "QUAL": perf_metrics(benchmarks["QUAL"].pct_change().dropna(), rf_series=rf),
        "USMV": perf_metrics(benchmarks["USMV"].pct_change().dropna(), rf_series=rf),
    },
    "equity_curves": {
        "Fund (Macro-Overlay Tech)": cum_pairs(ret),
        "SPY":  cum_pairs(spy_ret.loc[START_DT:END_DT]),
        "XLK":  cum_pairs(xlk_ret.loc[START_DT:END_DT]),
        "MTUM": cum_pairs(benchmarks["MTUM"].pct_change().dropna()),
        "QUAL": cum_pairs(benchmarks["QUAL"].pct_change().dropna()),
        "USMV": cum_pairs(benchmarks["USMV"].pct_change().dropna()),
    },
    "drawdowns": {
        "Fund": dd_pairs(ret),
        "SPY":  dd_pairs(spy_ret.loc[START_DT:END_DT]),
        "XLK":  dd_pairs(xlk_ret.loc[START_DT:END_DT]),
    },
    "rolling_12m": {
        "Fund": pairs(roll12_fund),
        "SPY":  pairs(roll12_mkt),
        "XLK":  pairs(roll12_xlk),
    },
    "regime": {
        "score":          pairs(macro_score.loc[START_DT:END_DT]),
        "gross_exposure": pairs(gross_macro.loc[START_DT:END_DT]),
        "components": {
            "vix":    pairs(macro_components["vix"].loc[START_DT:END_DT]),
            "credit": pairs(macro_components["credit"].loc[START_DT:END_DT]),
            "yield":  pairs(macro_components["yield"].loc[START_DT:END_DT]),
            "trend":  pairs(macro_components["trend"].loc[START_DT:END_DT]),
        },
    },
    "holdings_latest": {
        "as_of": latest_idx.strftime("%Y-%m-%d"),
        "weights": holdings,
    },
    "stress_tests": stress_rows,
    "sensitivity": {
        "lookbacks": lookbacks,
        "quantiles": quantiles,
        "sharpe_grid": sens_grid.round(3).tolist(),
        "min_sharpe": float(sens_grid.min()),
        "max_sharpe": float(sens_grid.max()),
        "mean_sharpe": float(sens_grid.mean()),
    },
    "deflated_sharpe": {
        "observed_sr":  sr_obs,
        "threshold_sr": sr_thr,
        "psr":          psr,
        "n_trials":     n_trials,
    },
    "factor_regression": {
        "alpha_annualized":  float(model.params["const"] * 12),
        "alpha_tstat":       float(model.tvalues["const"]),
        "rsquared":          float(model.rsquared),
        "betas":             {k: float(v) for k, v in model.params.drop("const").items()},
        "betas_tstat":       {k: float(v) for k, v in model.tvalues.drop("const").items()},
    },
    "capacity": {
        "fund_nav":              fund_nav,
        "avg_n_holdings":        float(avg_n_long),
        "avg_monthly_turnover":  float(avg_monthly_turnover),
        "avg_annual_turnover":   float(avg_monthly_turnover * 12),
        "typical_position_size": float(typical_position_size),
        "per_name_capacity":     float(per_name_capacity),
        "headroom_at_100m":      float(headroom),
        "implied_soft_aum_cap":  float(soft_cap),
    },
    "vix_path": pairs(vix["VIX"].loc[START_DT:END_DT]),
}

# Round all numeric values in summary for cleanliness
out_path = Path("gsd2t_full.json")
out_path.write_text(json.dumps(output, indent=2, default=str))
print(f"\nWrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")

# %% [markdown]
# ## Print headline summary

# %%
print("\n" + "=" * 80)
print(f"GSD2T MACRO-OVERLAY TECH — INSTITUTIONAL APPENDIX")
print("=" * 80)
print(f"CAGR:              {primary['CAGR']*100:.1f}%  vs SPY {output['summary']['SPY']['CAGR']*100:.1f}%")
print(f"Sharpe:            {primary['Sharpe']:.2f}  vs SPY {output['summary']['SPY']['Sharpe']:.2f}")
print(f"MaxDD:             {primary['MaxDD']*100:.1f}%  vs SPY {output['summary']['SPY']['MaxDD']*100:.1f}%")
print(f"Alpha vs FF5+MOM:  {model.params['const']*12*100:.2f}%  (t={model.tvalues['const']:.2f}, R²={model.rsquared:.2f})")
print(f"IS Sharpe:         {is_metrics['Sharpe']:.2f}")
print(f"OOS Sharpe:        {oos_metrics['Sharpe']:.2f}")
print(f"Sensitivity grid:  {sens_grid.min():.2f} - {sens_grid.max():.2f} (15 trials)")
print(f"PSR (vs n={n_trials}): {psr:.3f}")
print(f"Soft AUM cap:      ${soft_cap/1e9:.2f}B  ({headroom:.1f}× headroom at $100M)")
