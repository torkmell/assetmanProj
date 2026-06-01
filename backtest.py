# %% [markdown]
# # Meridian Sector Rotation Fund — Quant Appendix
#
# **Strategy:** Macro-Conditioned Cross-Sectional Sector Rotation
# **Universe:** 30 Fama–French industry portfolios (backtest proxy for the 11 SPDR sector ETFs we would trade live)
# **Backtest period:** 1990-01 to 2018-12 (industry data ends 2018-12)
# **Macro overlay period:** 2000-01 to 2018-12 (FRED macro series available from 1997, lagged + warm-up)
#
# **Two variants reported:**
# 1. Long-only with macro-scaled gross exposure (**the pitched fund**)
# 2. Market-neutral long-short (top decile vs bottom decile)
#
# All performance is **SIMULATED** on industry portfolio returns net of an assumed 10 bps round-trip transaction cost.
# No live or paper trading data is included.

# %% [markdown]
# ## 1. Setup

# %%
import os
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # non-interactive backend so plt.show() doesn't block
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy import stats
import statsmodels.api as sm
import warnings
warnings.filterwarnings("ignore")

plt.rcParams["figure.figsize"] = (11, 5)
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.3
plt.rcParams["font.size"] = 10

DATA_ROOT = Path(__file__).resolve().parent / "course_data"  # bundled course data inside the repo
RNG = np.random.default_rng(42)

# %% [markdown]
# ## 2. Data load
#
# Three sources:
# - **Industry returns:** Fama–French 30-industry monthly value-weighted returns (1926–2018)
# - **FF factors + momentum:** Daily, aggregated to monthly, used for risk-factor regression
# - **Macro composite:** FRED series (commodities, CPI, real rate, IP, credit spread, retail sales), 1997–2020

# %%
def load_ff_industries():
    path = DATA_ROOT / "Folder_Data_for_asset_allocat..._.187814149" / "content" / "ind30_m_vw_rets.csv"
    df = pd.read_csv(path, index_col=0)
    df.columns = [c.strip() for c in df.columns]
    df.index = pd.to_datetime(df.index.astype(str), format="%Y%m") + pd.offsets.MonthEnd(0)
    df = df / 100.0
    df = df.replace([-0.9999, -9.999], np.nan)
    return df

def load_ff_factors_monthly():
    """FF 5-factor daily + momentum daily, aggregated to monthly compounded returns."""
    ff5_path = DATA_ROOT / "Folder_Macro_Factors_.187814089" / "content" / "F-F_Research_Data_5_Factors_2x3_daily.CSV"
    mom_path = DATA_ROOT / "Folder_Macro_Factors_.187814089" / "content" / "F-F_Momentum_Factor_daily.CSV"

    ff5 = pd.read_csv(ff5_path, skiprows=3, index_col=0)
    ff5.columns = [c.strip() for c in ff5.columns]
    ff5.index = pd.to_datetime(ff5.index.astype(str), format="%Y%m%d")
    ff5 = ff5 / 100.0

    mom = pd.read_csv(mom_path, skiprows=13, index_col=0, skipfooter=2, engine="python")
    mom.columns = ["Mom"]
    mom = mom.dropna()
    mom.index = pd.to_datetime(mom.index.astype(str).str.strip(), format="%Y%m%d", errors="coerce")
    mom = mom.dropna()
    mom = mom / 100.0

    daily = ff5.join(mom, how="inner")
    monthly = (1 + daily).resample("ME").prod() - 1
    return monthly

def load_macro():
    """FRED macro series. Dates are dd/mm/yyyy. Returns a monthly DataFrame indexed by month-end."""
    path = DATA_ROOT / "Folder_Macro_Factors_.187814089" / "content" / "fred_data_macro_factors.csv"
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], format="%d/%m/%Y")
    df = df.set_index("date").sort_index()
    df = df.apply(pd.to_numeric, errors="coerce")
    df.index = df.index + pd.offsets.MonthEnd(0)
    return df

industries = load_ff_industries()
factors = load_ff_factors_monthly()
macro_raw = load_macro()

print(f"Industries: {industries.shape}, {industries.index.min():%Y-%m} to {industries.index.max():%Y-%m}")
print(f"FF factors monthly: {factors.shape}, {factors.index.min():%Y-%m} to {factors.index.max():%Y-%m}")
print(f"Macro raw: {macro_raw.shape}, {macro_raw.index.min():%Y-%m} to {macro_raw.index.max():%Y-%m}")
print("\nIndustry names:", list(industries.columns))

# %% [markdown]
# ## 3. Backtest window
#
# We restrict to **1990-01 to 2018-12** for relevance. Earlier data is used only for momentum signal warm-up.

# %%
START = "1990-01-31"
END   = "2018-12-31"
MACRO_START = "2000-01-31"   # macro overlay starts here once all FRED series are populated

rets = industries.loc[:END]
factors_m = factors.loc[:END]
print(f"Industry returns used: {rets.index.min():%Y-%m} to {rets.index.max():%Y-%m}")

# %% [markdown]
# ## 4. Signal construction
#
# ### 4a. Cross-sectional momentum
# Standard academic construction: trailing 12-month return, **skipping the most recent month** to avoid 1-month reversal contamination. We z-score across industries each month.

# %%
def momentum_score(returns, lookback=12, skip=1):
    """Trailing `lookback`-month compounded return, skipping the most recent `skip` months."""
    log_ret = np.log1p(returns)
    score = log_ret.shift(skip).rolling(lookback - skip).sum()
    return score

def cross_sectional_zscore(panel):
    return panel.sub(panel.mean(axis=1), axis=0).div(panel.std(axis=1), axis=0)

mom_12_1 = momentum_score(rets, lookback=12, skip=1)
mom_z = cross_sectional_zscore(mom_12_1)
print("Momentum signal sample (most recent 3 months, first 6 industries):")
print(mom_z.dropna(how="all").iloc[-3:, :6].round(2))

# %% [markdown]
# ### 4b. Macro regime composite
#
# Combines 4 standard macro variables into a single risk-on / risk-off score:
# - **Credit spread (BAA-10Y) z-score** — wider = risk-off
# - **Year-over-year industrial production growth** — negative = risk-off
# - **Real rate trend (12m change)** — rising real rates = risk-off
# - **Commodities momentum** — falling = risk-off (demand weakness)
#
# All inputs are **lagged by one month** to ensure we only use information available at the decision date.
# The composite is z-scored and bounded to [-2, 2], then mapped to a gross-exposure scalar in [0.3, 1.0].

# %%
def macro_regime_score(macro):
    m = macro.copy()
    # YoY IP growth
    ip_yoy = m["ip"].pct_change(12)
    # 12m change in real rate (sign inverted: rising real rates = risk-off => negative score)
    rr_chg = -m["real_rate"].diff(12)
    # Credit spread level z-score (sign inverted: higher spreads => negative score)
    credit_z = -((m["credit"] - m["credit"].rolling(60, min_periods=24).mean())
                 / m["credit"].rolling(60, min_periods=24).std())
    # Commodities momentum (12m log return)
    comm_mom = np.log(m["commodities"]).diff(12)

    components = pd.concat({
        "ip_yoy": (ip_yoy - ip_yoy.rolling(60, min_periods=24).mean()) / ip_yoy.rolling(60, min_periods=24).std(),
        "rr_chg": (rr_chg - rr_chg.rolling(60, min_periods=24).mean()) / rr_chg.rolling(60, min_periods=24).std(),
        "credit": credit_z,
        "comm":   (comm_mom - comm_mom.rolling(60, min_periods=24).mean()) / comm_mom.rolling(60, min_periods=24).std(),
    }, axis=1)

    composite = components.mean(axis=1).clip(-2, 2)
    # Lag by 1 month: use only information from prior month-end
    composite = composite.shift(1)
    return composite, components

regime_score, regime_components = macro_regime_score(macro_raw)
regime_score = regime_score.reindex(rets.index).ffill(limit=1)

# Map composite to gross exposure scalar in [0.3, 1.0]
def exposure_from_regime(score):
    # score in [-2, +2] -> exposure in [0.3, 1.0] via linear ramp
    return np.clip(0.65 + 0.175 * score, 0.3, 1.0)

gross_exposure = exposure_from_regime(regime_score)
print(f"Regime score available from: {regime_score.dropna().index.min():%Y-%m}")
print(f"Mean gross exposure (regime-on period): {gross_exposure.loc[MACRO_START:].mean():.2f}")

# %% [markdown]
# ## 5. Portfolio construction
#
# - **Long-only fund (PITCHED):** equal-weight the top quartile of industries by momentum, scale total gross exposure by the macro regime overlay (rest in cash earning RF).
# - **Long-short variant:** equal-weight long top quartile, short bottom quartile, dollar-neutral, no regime scaling.
#
# Rebalanced monthly. Weights computed at end of month *t* using signals known at *t*; returns realized over month *t+1*. **No look-ahead.**

# %%
def quartile_weights(scores, top=True, q=0.25):
    """Equal weight on assets in the top (or bottom) quantile each month."""
    ranks = scores.rank(axis=1, pct=True)
    if top:
        mask = ranks >= (1 - q)
    else:
        mask = ranks <= q
    w = mask.astype(float)
    w = w.div(w.sum(axis=1), axis=0)
    return w.fillna(0.0)

# Long-only weights: top quartile of momentum, equal-weighted within
w_long = quartile_weights(mom_z, top=True, q=0.25)
# Short-side weights for the long-short variant
w_short = quartile_weights(mom_z, top=False, q=0.25)

print(f"Long sleeve: avg {w_long.gt(0).sum(axis=1).mean():.1f} industries held / month")
print(f"Short sleeve: avg {w_short.gt(0).sum(axis=1).mean():.1f} industries held / month")

# %% [markdown]
# ## 6. Backtest engine
#
# Single function: takes weight matrix(es), returns matrix, transaction cost per round-trip.

# %%
TC_BPS = 10  # round-trip transaction cost in basis points (sector ETFs are very tight)

def backtest(weights_long, weights_short=None, returns=None, gross_scalar=None,
             tc_bps=TC_BPS, rf=None):
    """
    weights_long:  (T x N) DataFrame of long weights (sums to 1 each row, before scaling)
    weights_short: optional (T x N) DataFrame of short weights (sums to 1 each row, before scaling)
    gross_scalar:  optional (T,) Series in [0, 1+]. If provided, total gross = scalar; uninvested earns RF.
    Returns: dict with 'returns', 'turnover', 'weights' (post-scaling).
    """
    aligned_idx = weights_long.index.intersection(returns.index)
    wL = weights_long.loc[aligned_idx].fillna(0.0)
    wS = (weights_short.loc[aligned_idx].fillna(0.0)
          if weights_short is not None else pd.DataFrame(0.0, index=aligned_idx, columns=wL.columns))
    R  = returns.loc[aligned_idx].fillna(0.0)

    if gross_scalar is not None:
        scalar = gross_scalar.reindex(aligned_idx).fillna(1.0).clip(lower=0.0)
        wL = wL.mul(scalar, axis=0)
        # short sleeve typically not regime-scaled in the long-short variant; left as caller passes it

    w_net = wL - wS

    # Realized portfolio return over month t+1 from weights set at end of month t
    port_gross = (w_net.shift(1) * R).sum(axis=1)

    # Cash sleeve return (for long-only): (1 - gross_long) * rf, if rf supplied
    if rf is not None and weights_short is None and gross_scalar is not None:
        cash_w = (1.0 - wL.sum(axis=1)).clip(lower=0.0)
        rf_aligned = rf.reindex(aligned_idx).fillna(0.0)
        port_gross = port_gross + (cash_w.shift(1) * rf_aligned)

    # Turnover: sum |Δw| across assets each month (both legs)
    dw = (w_net - w_net.shift(1)).abs().sum(axis=1)
    tc = dw * (tc_bps / 10000.0)
    port_net = port_gross - tc

    out = pd.DataFrame({
        "gross_return": port_gross,
        "tc":           tc,
        "net_return":   port_net,
        "turnover":     dw,
    })
    return out, w_net

rf = factors_m["RF"]

# Baseline: momentum-only, no regime overlay, long-only top-quartile (1990-2018)
bt_baseline, _ = backtest(w_long, returns=rets)
# Pitched long-only fund: momentum + macro regime gross-exposure scaling + cash sleeve
bt_long_only, w_lo = backtest(w_long, returns=rets, gross_scalar=gross_exposure, rf=rf)
# Long-short variant: dollar-neutral, no regime scaling
bt_long_short, w_ls = backtest(w_long, weights_short=w_short, returns=rets)

# Benchmark = market total return (Mkt-RF + RF)
mkt_total = (factors_m["Mkt-RF"] + factors_m["RF"]).rename("Market")

print("Backtest variants computed:")
print(" - Baseline (long-only momentum, no overlay, 1990-2018)")
print(" - Long-only fund (momentum + macro overlay + cash, pitched)")
print(" - Long-short (dollar-neutral)")

# %% [markdown]
# ## 7. Performance metrics
#
# CAGR, vol, Sharpe, Sortino, Calmar, Max DD, average annual turnover, hit-rate.

# %%
def perf_metrics(returns, rf=None, periods_per_year=12, name="strategy"):
    r = returns.dropna()
    if rf is not None:
        rf_aligned = rf.reindex(r.index).fillna(0)
        excess = r - rf_aligned
    else:
        excess = r
    cum = (1 + r).cumprod()
    cagr = cum.iloc[-1] ** (periods_per_year / len(r)) - 1
    vol = r.std() * np.sqrt(periods_per_year)
    sharpe = (excess.mean() * periods_per_year) / (excess.std() * np.sqrt(periods_per_year))
    downside = r[r < 0].std() * np.sqrt(periods_per_year)
    sortino = (excess.mean() * periods_per_year) / downside if downside > 0 else np.nan
    dd = cum / cum.cummax() - 1
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else np.nan
    hit = (r > 0).mean()
    return pd.Series({
        "CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino,
        "Calmar": calmar, "MaxDD": max_dd, "HitRate": hit,
        "N_months": len(r),
    }, name=name)

window_full = slice(START, END)
window_macro = slice(MACRO_START, END)

summary = pd.concat([
    perf_metrics(bt_baseline.loc[window_full, "net_return"], rf, name="MOM-only (1990-18)"),
    perf_metrics(bt_long_only.loc[window_macro, "net_return"], rf, name="Long-Only + Macro (2000-18)"),
    perf_metrics(bt_long_short.loc[window_macro, "net_return"], rf=None, name="Long-Short (2000-18)"),
    perf_metrics(mkt_total.loc[window_macro], rf, name="Market (2000-18)"),
    perf_metrics(mkt_total.loc[window_full], rf, name="Market (1990-18)"),
], axis=1).T

# Add average annual turnover
summary["AvgAnnTurnover"] = [
    bt_baseline.loc[window_full, "turnover"].mean() * 12,
    bt_long_only.loc[window_macro, "turnover"].mean() * 12,
    bt_long_short.loc[window_macro, "turnover"].mean() * 12,
    np.nan,
    np.nan,
]
summary = summary[["N_months", "CAGR", "Vol", "Sharpe", "Sortino", "Calmar", "MaxDD", "HitRate", "AvgAnnTurnover"]]
print(summary.round(3).to_string())

# %% [markdown]
# ### 7a. Equity curves

# %%
fig, ax = plt.subplots(figsize=(11, 5.5))
def cum_curve(s, label):
    return (1 + s).cumprod().rename(label)

cum_curve(bt_long_only.loc[window_macro, "net_return"], "Long-Only + Macro").plot(ax=ax, lw=2, color="navy")
cum_curve(bt_long_short.loc[window_macro, "net_return"], "Long-Short").plot(ax=ax, lw=1.5, color="darkorange")
cum_curve(mkt_total.loc[window_macro], "Market (Mkt-RF + RF)").plot(ax=ax, lw=1.5, color="grey", linestyle="--")
ax.set_yscale("log")
ax.set_title("Meridian Sector Rotation — Cumulative Net Wealth (2000-01 to 2018-12)")
ax.set_ylabel("Growth of $1 (log scale)")
ax.legend(loc="upper left")
plt.tight_layout()
plt.savefig(DATA_ROOT / "Group_Project" / "fig_equity_curves.png", dpi=130)
plt.show()

# %% [markdown]
# ### 7b. Drawdowns

# %%
def drawdown_series(r):
    cum = (1 + r).cumprod()
    return cum / cum.cummax() - 1

fig, ax = plt.subplots(figsize=(11, 4))
drawdown_series(bt_long_only.loc[window_macro, "net_return"]).plot(ax=ax, label="Long-Only + Macro", color="navy")
drawdown_series(mkt_total.loc[window_macro]).plot(ax=ax, label="Market", color="grey", linestyle="--")
ax.fill_between(bt_long_only.loc[window_macro].index,
                drawdown_series(bt_long_only.loc[window_macro, "net_return"]).values, 0,
                color="navy", alpha=0.15)
ax.set_title("Drawdowns — Long-Only Fund vs Market")
ax.set_ylabel("Drawdown")
ax.legend()
plt.tight_layout()
plt.savefig(DATA_ROOT / "Group_Project" / "fig_drawdowns.png", dpi=130)
plt.show()

# %% [markdown]
# ## 8. Risk-factor regression (alpha vs FF5 + MOM)
#
# Does the strategy earn alpha *after* controlling for standard equity risk factors? If alpha collapses, the strategy is just repackaged factor beta.

# %%
def factor_regression(strat_excess, factors_m, factor_cols=None):
    if factor_cols is None:
        factor_cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
    df = pd.concat([strat_excess.rename("y"), factors_m[factor_cols]], axis=1).dropna()
    X = sm.add_constant(df[factor_cols])
    model = sm.OLS(df["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
    return model

strat_excess = bt_long_only.loc[window_macro, "net_return"] - rf.reindex(bt_long_only.loc[window_macro].index)
model = factor_regression(strat_excess, factors_m)
print(model.summary())
alpha_ann = model.params["const"] * 12
print(f"\nAnnualized alpha (long-only fund, 2000-2018): {alpha_ann*100:.2f}%   t-stat: {model.tvalues['const']:.2f}")

# %% [markdown]
# ## 9. Robustness
#
# ### 9a. Walk-forward / OOS test
# Split the sample at 2010-01. Calibrate the regime->exposure mapping coefficients in-sample (1997-2009) and apply unchanged out-of-sample (2010-2018). For this strategy the calibration is minimal (the regime score is constructed from rolling z-scores that themselves are sample-causal), so the OOS test mostly checks **stability of the edge**, not parameter overfitting.

# %%
oos_start = "2010-01-31"
oos_metrics = perf_metrics(bt_long_only.loc[oos_start:END, "net_return"], rf, name="Long-Only OOS (2010-18)")
is_metrics  = perf_metrics(bt_long_only.loc[MACRO_START:"2009-12-31", "net_return"], rf, name="Long-Only IS (2000-09)")
print(pd.concat([is_metrics, oos_metrics], axis=1).round(3).to_string())

# %% [markdown]
# ### 9b. Parameter sensitivity
# Vary the momentum lookback (6, 9, 12, 15 months) and the long-quartile cutoff (0.20, 0.25, 0.33). A robust edge survives small parameter changes; a fragile one disappears.

# %%
sens_rows = []
for lb in [6, 9, 12, 15]:
    for q in [0.20, 0.25, 0.33]:
        s = momentum_score(rets, lookback=lb, skip=1)
        sz = cross_sectional_zscore(s)
        wl = quartile_weights(sz, top=True, q=q)
        bt, _ = backtest(wl, returns=rets, gross_scalar=gross_exposure, rf=rf)
        m = perf_metrics(bt.loc[window_macro, "net_return"], rf, name=f"lb={lb},q={q}")
        sens_rows.append(m)
sens = pd.DataFrame(sens_rows)
sens["lookback"] = [int(n.split(",")[0].split("=")[1]) for n in sens.index]
sens["quartile"] = [float(n.split(",")[1].split("=")[1]) for n in sens.index]
pivot_sharpe = sens.pivot(index="lookback", columns="quartile", values="Sharpe")
print("Sharpe sensitivity (rows: lookback months, cols: top-quantile cutoff):")
print(pivot_sharpe.round(2))
print(f"\nMin Sharpe across grid: {pivot_sharpe.values.min():.2f}")
print(f"Max Sharpe across grid: {pivot_sharpe.values.max():.2f}")
print(f"Mean Sharpe across grid: {pivot_sharpe.values.mean():.2f}")

# %% [markdown]
# ### 9c. Deflated Sharpe Ratio
# Bailey & López de Prado (2014). Adjusts the Sharpe Ratio for the **number of trials** (12 in our parameter grid) and the **non-normality of returns**, giving the probability that the observed Sharpe exceeds a benchmark threshold under the null of zero true skill.

# %%
def deflated_sharpe(returns, n_trials=1, benchmark_sr=0.0):
    r = returns.dropna()
    n = len(r)
    sr = (r.mean() / r.std()) * np.sqrt(12)
    skew = stats.skew(r)
    kurt = stats.kurtosis(r, fisher=True)  # excess kurtosis
    # Expected max Sharpe under the null across n_trials independent strategies
    emc_gamma = 0.5772156649  # Euler-Mascheroni
    e_max_sr = (benchmark_sr +
                ((1 - emc_gamma) * stats.norm.ppf(1 - 1.0 / n_trials)
                 + emc_gamma * stats.norm.ppf(1 - 1.0 / (n_trials * np.e)))
                if n_trials > 1 else benchmark_sr)
    # Variance of the SR estimator (Lo 2002 + skew/kurt correction)
    var_sr = (1 - skew * sr + ((kurt) / 4.0) * sr**2) / (n - 1)
    z = (sr - e_max_sr) / np.sqrt(var_sr) if var_sr > 0 else np.nan
    psr = stats.norm.cdf(z)
    return sr, e_max_sr, psr

n_trials = len(sens)
sr_obs, sr_threshold, psr = deflated_sharpe(
    bt_long_only.loc[window_macro, "net_return"] - rf.reindex(bt_long_only.loc[window_macro].index),
    n_trials=n_trials, benchmark_sr=0.0)
print(f"Observed Sharpe (excess, 2000-18): {sr_obs:.2f}")
print(f"Expected max Sharpe under null across {n_trials} trials: {sr_threshold:.2f}")
print(f"Probabilistic Sharpe Ratio (deflated): {psr:.3f}   "
      f"=> probability the true Sharpe exceeds the multiple-testing threshold")

# %% [markdown]
# ## 10. Stress tests
#
# Performance during named crisis windows.

# %%
stress_windows = {
    "Dot-com (2000-09 to 2002-10)":      ("2000-09-30", "2002-10-31"),
    "GFC (2007-10 to 2009-02)":          ("2007-10-31", "2009-02-28"),
    "Eurozone (2011-07 to 2011-09)":     ("2011-07-31", "2011-09-30"),
    "China devaluation (2015-08 to 2016-02)": ("2015-08-31", "2016-02-29"),
    "Vol spike (2018-10 to 2018-12)":    ("2018-10-31", "2018-12-31"),
}

stress_rows = []
for name, (s, e) in stress_windows.items():
    seg_fund = bt_long_only.loc[s:e, "net_return"]
    seg_mkt  = mkt_total.loc[s:e]
    if len(seg_fund) == 0 or len(seg_mkt) == 0:
        continue
    fund_ret = (1 + seg_fund).prod() - 1
    mkt_ret  = (1 + seg_mkt).prod() - 1
    fund_dd  = (drawdown_series(seg_fund)).min()
    mkt_dd   = (drawdown_series(seg_mkt)).min()
    stress_rows.append({
        "Window": name,
        "Fund_Total": fund_ret,
        "Mkt_Total":  mkt_ret,
        "Outperf":    fund_ret - mkt_ret,
        "Fund_DD":    fund_dd,
        "Mkt_DD":     mkt_dd,
    })
stress = pd.DataFrame(stress_rows).set_index("Window")
print(stress.round(3).to_string())

# %% [markdown]
# ## 11. Capacity analysis
#
# **Tradable implementation:** 11 SPDR sector ETFs (XLE, XLF, XLK, XLI, XLY, XLP, XLV, XLU, XLB, XLRE, XLC). Each trades hundreds of millions of dollars in average daily volume.
#
# **Assumptions:**
# - Hold typically 7–8 industries (top quartile of 30, equal-weighted)
# - Avg ETF ADV per name: ~\$500M (conservative for the smaller sector ETFs; XLF and XLK trade multi-billion)
# - Rebalance: monthly
# - Avg monthly turnover (long sleeve, from the backtest): see below
# - Self-imposed limit: trade at most **5% of ADV** on any rebalance day to avoid market impact
#
# This gives a per-name daily capacity of ~$25M, and we can spread execution across 2–3 days. Total fund capacity well in excess of $1B.

# %%
avg_monthly_turnover = bt_long_only.loc[window_macro, "turnover"].mean()
avg_n_holdings = w_long.gt(0).sum(axis=1).loc[window_macro].mean()
print(f"Average one-sided monthly turnover (long sleeve, fraction of NAV traded): {avg_monthly_turnover:.2%}")
print(f"Average number of holdings: {avg_n_holdings:.1f}")
print(f"Average annual turnover: {avg_monthly_turnover * 12:.1%}")

fund_nav = 100_000_000  # USD 100M target
adv_per_etf = 500_000_000
max_pct_adv = 0.05
days_to_trade = 2
per_name_daily_capacity = adv_per_etf * max_pct_adv
per_name_rebalance_capacity = per_name_daily_capacity * days_to_trade
typical_position_size = fund_nav / avg_n_holdings
print(f"\nAt $100M NAV, typical position size: ${typical_position_size/1e6:.1f}M")
print(f"Per-name execution capacity (5% ADV x {days_to_trade} days): ${per_name_rebalance_capacity/1e6:.0f}M")
print(f"Headroom multiplier at $100M: {per_name_rebalance_capacity / typical_position_size:.1f}x")
print(f"Implied soft AUM cap (same execution constraint): "
      f"${per_name_rebalance_capacity * avg_n_holdings / 1e9:.1f}B")

# %% [markdown]
# ## 12. Headline summary table

# %%
print("=" * 78)
print("GSD2T SECTOR ROTATION — HEADLINE METRICS (SIMULATED, NET OF 10 BPS)")
print("=" * 78)
print(summary[["CAGR", "Vol", "Sharpe", "MaxDD", "Calmar", "AvgAnnTurnover"]].round(3).to_string())
print()
print(f"Long-only fund alpha vs FF5+MOM (2000-18, annualized): {alpha_ann*100:.2f}% "
      f"(t={model.tvalues['const']:.2f})")
print(f"Probabilistic Sharpe Ratio after deflating for {n_trials} trials: {psr:.3f}")
print()
print("Stress test summary:")
print(stress[["Fund_Total", "Mkt_Total", "Outperf"]].round(3).to_string())

# %% [markdown]
# ## 13. Dashboard data export
#
# Emits a single `dashboard_data.json` consumed by the static HTML dashboard.

# %%
def ser_to_pairs(s):
    """Convert a pandas Series (datetime index) into [[iso_date, value_or_None], ...]."""
    out = []
    for ts, v in s.dropna().items():
        out.append([ts.strftime("%Y-%m-%d"), float(v) if pd.notna(v) else None])
    return out

def cum_pairs(s):
    return ser_to_pairs((1 + s.dropna()).cumprod())

def dd_pairs(s):
    cum = (1 + s.dropna()).cumprod()
    return ser_to_pairs(cum / cum.cummax() - 1)

# Identify current top-quartile holdings (last available month)
latest = w_long.dropna(how="all").iloc[-1]
holdings = [{"sector": k, "weight": float(v)} for k, v in latest[latest > 0].sort_values(ascending=False).items()]

# Rolling 12m returns
roll12_fund = (1 + bt_long_only.loc[window_macro, "net_return"]).rolling(12).apply(lambda x: x.prod() - 1, raw=True)
roll12_mkt  = (1 + mkt_total.loc[window_macro]).rolling(12).apply(lambda x: x.prod() - 1, raw=True)

dashboard = {
    "meta": {
        "fund_name": "GSD2T Asset Management",
        "strategy": "Macro-Conditioned Sector Rotation",
        "backtest_window": f"{MACRO_START[:7]} to {END[:7]}",
        "baseline_window": f"{START[:7]} to {END[:7]}",
        "universe": "30 Fama-French industry portfolios (proxy); 11 SPDR sector ETFs (live implementation)",
        "tc_bps": TC_BPS,
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
    },
    "summary": summary.round(4).reset_index().rename(columns={"index": "strategy"}).to_dict(orient="records"),
    "equity_curves": {
        "Long-Only + Macro": cum_pairs(bt_long_only.loc[window_macro, "net_return"]),
        "Long-Short":        cum_pairs(bt_long_short.loc[window_macro, "net_return"]),
        "Market":            cum_pairs(mkt_total.loc[window_macro]),
        "MOM-only (full)":   cum_pairs(bt_baseline.loc[window_full, "net_return"]),
    },
    "drawdowns": {
        "Long-Only + Macro": dd_pairs(bt_long_only.loc[window_macro, "net_return"]),
        "Market":            dd_pairs(mkt_total.loc[window_macro]),
    },
    "regime": {
        "score":         ser_to_pairs(regime_score.loc[window_macro]),
        "gross_exposure": ser_to_pairs(gross_exposure.loc[window_macro]),
    },
    "rolling_12m": {
        "Fund":   ser_to_pairs(roll12_fund),
        "Market": ser_to_pairs(roll12_mkt),
    },
    "holdings_latest": {
        "as_of": latest.name.strftime("%Y-%m-%d"),
        "weights": holdings,
    },
    "stress_tests": [
        {"window": k, "fund_total": float(v["Fund_Total"]), "mkt_total": float(v["Mkt_Total"]),
         "outperf": float(v["Outperf"]), "fund_dd": float(v["Fund_DD"]), "mkt_dd": float(v["Mkt_DD"])}
        for k, v in stress.iterrows()
    ],
    "sensitivity": {
        "lookbacks":   sorted(sens["lookback"].unique().tolist()),
        "quartiles":   sorted(sens["quartile"].unique().tolist()),
        "sharpe_grid": pivot_sharpe.round(3).values.tolist(),  # rows: lookback, cols: quartile
    },
    "factor_regression": {
        "alpha_annualized":  float(alpha_ann),
        "alpha_tstat":       float(model.tvalues["const"]),
        "rsquared":          float(model.rsquared),
        "betas":             {k: float(v) for k, v in model.params.drop("const").items()},
        "betas_tstat":       {k: float(v) for k, v in model.tvalues.drop("const").items()},
    },
    "deflated_sharpe": {
        "observed_sr":   float(sr_obs),
        "threshold_sr":  float(sr_threshold),
        "psr":           float(psr),
        "n_trials":      int(n_trials),
    },
    "capacity": {
        "fund_nav":                       fund_nav,
        "avg_n_holdings":                 float(avg_n_holdings),
        "avg_monthly_turnover":           float(avg_monthly_turnover),
        "avg_annual_turnover":            float(avg_monthly_turnover * 12),
        "typical_position_size":          float(typical_position_size),
        "per_name_rebalance_capacity":    float(per_name_rebalance_capacity),
        "implied_soft_aum_cap":           float(per_name_rebalance_capacity * avg_n_holdings),
    },
}

out_path = DATA_ROOT / "Group_Project" / "dashboard_data.json"
with open(out_path, "w") as f:
    json.dump(dashboard, f, indent=2, default=str)
print(f"\nDashboard data exported to: {out_path}")
