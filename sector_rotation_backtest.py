# %% [markdown]
# # Macro-Regime Sector-Rotation Backtest (long-only, US equity sectors)
#
# Tests whether rotating across the 9 SPDR Select Sector ETFs by macro regime
# generates alpha vs the S&P 500. Design is FROZEN on 2000-01..2018-12 and then
# run UNCHANGED out-of-sample 2019-01..latest. In-sample and OOS reported side by side.
#
# DETERMINISM: no stochastic components; seed set for safety. Data is cached to
# `data_cache/` so reruns are reproducible offline.
#
# LOOK-AHEAD GUARDS (re-stated where enforced):
#   [G1] Macro series lagged 1 month before any use (publication-delay proxy) -> build_regimes()
#   [G2] Regime at month-end t drives weights HELD over t+1: portfolio = W.shift(1) * R -> backtest()
#   [G3] Variant B uses an EXPANDING window of only past, realised (regime -> next-month) returns;
#        no full-sample statistic enters any pre-rebalance decision -> allocate_empirical()
#   [G4] Transaction cost charged on the turnover of the rebalance that PRECEDES the holding month.
#
# If a required series is unavailable the script raises (it does not silently assume).

# %%
import sys, time, io, urllib.request, warnings
from pathlib import Path
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")
np.random.seed(42)  # determinism (no random component, set for safety)

# ----------------------------------------------------------------------------- PARAMETERS (defined once)
ETFS        = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
BENCH       = "SPY"
START       = "2000-01-31"          # strategy start (regime needs ~25m macro history)
IS_START    = "2000-01-31"
IS_END      = "2018-12-31"          # design frozen on/through here
OOS_START   = "2019-01-31"
DATA_START  = "1998-01-01"          # raw pull start (ETFs from 1998-12; macro from 1998-01)
MACRO_LAG   = 1                     # [G1] months to lag macro for publication delay
TOPN_B      = 4                     # Variant B: number of top sectors to hold
COST_PER_TURN = 0.0005              # 10bps round-trip = 0.0005 * sum|dw| (counts both sides). Parameter.
CACHE       = Path("data_cache"); CACHE.mkdir(exist_ok=True)

# Economic rationale for the a-priori regime map (Variant A):
#   Goldilocks  (growth up, inflation down): cyclical growth + rate-sensitive -> Tech, Discretionary, Industrials, Financials
#   Reflation   (growth up, inflation up)  : real assets + cyclicals          -> Energy, Materials, Financials, Industrials
#   Stagflation (growth down, inflation up): defensives + real assets         -> Energy, Materials, Staples, Health, Utilities
#   Slowdown    (growth down, inflation dn): defensives                       -> Staples, Utilities, Health
REGIME_MAP_A = {
    "Goldilocks":  ["XLK", "XLY", "XLI", "XLF"],
    "Reflation":   ["XLE", "XLB", "XLF", "XLI"],
    "Stagflation": ["XLE", "XLB", "XLP", "XLV", "XLU"],
    "Slowdown":    ["XLP", "XLU", "XLV"],
}
REGIMES = list(REGIME_MAP_A.keys())

def to_month_end(idx):
    return pd.to_datetime(idx).to_period("M").to_timestamp("M")

# ----------------------------------------------------------------------------- DATA
def _fred_csv(code, timeout=60):
    """Robust FRED fetch via the public CSV endpoint (fallback for flaky pandas-datareader)."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={code}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        df = pd.read_csv(io.StringIO(r.read().decode()))
    df.columns = ["date", code]
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")[code].apply(pd.to_numeric, errors="coerce").dropna()

def fetch_fred(code, tries=3):
    """Spec asks for pandas-datareader; we try it first, then the CSV endpoint, then raise."""
    import datetime as dt
    for i in range(tries):
        try:
            import pandas_datareader.data as web
            s = web.DataReader(code, "fred", dt.datetime(1998, 1, 1), dt.datetime(2100, 1, 1))
            return s[code] if isinstance(s, pd.DataFrame) else s
        except Exception:
            time.sleep(2)
    for i in range(tries):                     # fallback: direct CSV
        try:
            return _fred_csv(code)
        except Exception:
            time.sleep(2)
    raise RuntimeError(f"FRED series '{code}' unavailable after retries — STOPPING (no silent assumption).")

def fetch_data():
    """Returns (etf_prices_monthly, spy_monthly, macro_df, rf_monthly_decimal, rf_label)."""
    # --- ETF + benchmark prices (daily ADJUSTED close -> month-end) ---
    px_path = CACHE / "sector_etf_prices_monthly.csv"
    if px_path.exists():
        prices = pd.read_csv(px_path, index_col=0, parse_dates=True)
    else:
        import yfinance as yf
        raw = yf.download(ETFS + [BENCH], start=DATA_START, interval="1d",
                          auto_adjust=True, progress=False, group_by="ticker")
        close = pd.DataFrame({t: raw[t]["Close"] for t in ETFS + [BENCH] if t in raw.columns.levels[0]})
        prices = close.resample("ME").last()
        prices.to_csv(px_path)
    prices.index = to_month_end(prices.index)
    missing = [t for t in ETFS + [BENCH] if t not in prices.columns]
    if missing:
        raise RuntimeError(f"Price series unavailable: {missing} — STOPPING.")

    # --- Macro (FRED): INDPRO growth, CPIAUCSL inflation ---
    macro_path = CACHE / "macro_indpro_cpi.csv"
    if macro_path.exists():
        macro = pd.read_csv(macro_path, index_col=0, parse_dates=True)
    else:
        indpro = fetch_fred("INDPRO").rename("INDPRO")
        cpi    = fetch_fred("CPIAUCSL").rename("CPIAUCSL")
        macro = pd.concat([indpro, cpi], axis=1).dropna()
        macro.index = to_month_end(macro.index)
        macro.to_csv(macro_path)
    macro.index = to_month_end(macro.index)

    # --- Risk-free rate: DGS3MO -> TB3MS -> 0 (spec: "DGS3MO or assume 0, state which") ---
    rf_path = CACHE / "rf_monthly.csv"
    rf_label = None
    if rf_path.exists():
        rf = pd.read_csv(rf_path, index_col=0, parse_dates=True).iloc[:, 0]
        rf_label = "cached rf"
    else:
        rf = None
        for code in ["DGS3MO", "TB3MS"]:
            try:
                raw = fetch_fred(code)
                raw.index = to_month_end(raw.index)
                rf = (raw.resample("ME").last() / 100.0) / 12.0   # annual % -> monthly decimal
                rf_label = f"FRED {code}"
                break
            except Exception:
                continue
        if rf is None:
            rf = pd.Series(0.0, index=prices.index); rf_label = "ASSUMED ZERO (FRED rf unavailable)"
        rf.to_csv(rf_path)
    rf = rf.reindex(prices.index).ffill().fillna(0.0)

    spy = prices[BENCH]
    etf = prices[ETFS]
    return etf, spy, macro, rf, rf_label

# ----------------------------------------------------------------------------- REGIMES
def build_regimes(macro):
    """[G1] Lag macro 1 month, compute 12m YoY, compare to its trailing-12m average."""
    m = macro.copy()
    m.index = to_month_end(m.index)
    m = m.reindex(pd.date_range(m.index.min(), m.index.max(), freq="ME")).ffill()
    m_lagged = m.shift(MACRO_LAG)                          # [G1] publication-delay proxy

    def state(series):
        yoy = series.pct_change(12)
        avg = yoy.rolling(12).mean()
        rising = (yoy > avg).where(yoy.notna() & avg.notna())   # NaN where inputs invalid (no spurious False)
        return yoy, avg, rising

    _, _, g_rising = state(m_lagged["INDPRO"])
    _, _, i_rising = state(m_lagged["CPIAUCSL"])

    def label(g_up, i_up):
        if g_up and not i_up: return "Goldilocks"
        if g_up and i_up:     return "Reflation"
        if (not g_up) and i_up:return "Stagflation"
        return "Slowdown"

    reg = pd.Series([label(g, i) if pd.notna(g) and pd.notna(i) else np.nan
                     for g, i in zip(g_rising, i_rising)], index=m_lagged.index, name="regime")
    return reg.dropna()

# ----------------------------------------------------------------------------- ALLOCATION
def allocate_theory(regimes, cols):
    """Variant A: fixed a-priori equal weights per regime."""
    W = pd.DataFrame(0.0, index=regimes.index, columns=cols)
    for dt_, r in regimes.items():
        favoured = REGIME_MAP_A[r]
        W.loc[dt_, favoured] = 1.0 / len(favoured)
    return W

def allocate_empirical(regimes, etf_returns, topn=TOPN_B, min_obs=3):
    """[G3] Variant B: strictly walk-forward. At each month-end t, for the CURRENT regime,
    rank sectors by their historical mean NEXT-month return in that regime, using ONLY
    realised data up to t (expanding window). Equal-weight the top N."""
    cols = etf_returns.columns
    # next-month return realised AFTER the regime is observed at u  (return over u -> u+1)
    nxt = etf_returns.shift(-1)
    reg_aligned = regimes.reindex(etf_returns.index)
    W = pd.DataFrame(0.0, index=regimes.index, columns=cols)
    for t in regimes.index:
        cur = regimes.loc[t]
        # past months u (strictly < t) in the same regime whose next-month return is known by t
        hist_mask = (reg_aligned.index < t) & (reg_aligned == cur) & nxt.notna().all(axis=1)
        hist = nxt.loc[hist_mask]
        if len(hist) >= min_obs:
            means = hist.mean()
            winners = means.sort_values(ascending=False).head(topn).index
            W.loc[t, winners] = 1.0 / len(winners)
        else:
            W.loc[t] = 1.0 / len(cols)          # prior: equal-weight all until enough history
    return W

def allocate_equal(index, cols):
    """Control: equal-weight all 9 sectors, always."""
    return pd.DataFrame(1.0 / len(cols), index=index, columns=cols)

# ----------------------------------------------------------------------------- BACKTEST
def backtest(W, etf_returns, cost_per_turn=COST_PER_TURN):
    """[G2] hold next month: gross = (W.shift(1) * R).sum.
       [G4] cost charged on the turnover of the rebalance preceding the holding month."""
    W = W.reindex(etf_returns.index).ffill().fillna(0.0)
    R = etf_returns.reindex(W.index).fillna(0.0)
    gross = (W.shift(1) * R).sum(axis=1)
    turn  = (W - W.shift(1)).abs().sum(axis=1)            # one-way+other-way = round-trip turnover
    cost  = (cost_per_turn * turn).shift(1).fillna(0.0)   # [G4]
    net   = gross - cost
    return net, turn

# ----------------------------------------------------------------------------- METRICS
def metrics(ret, rf, bench_ret, periods=12):
    r = ret.dropna()
    if len(r) < 12:
        return {k: np.nan for k in ["CAGR","Vol","Sharpe","Sortino","MaxDD","Calmar","Alpha","Beta","IR","N"]}
    rf_a = rf.reindex(r.index).fillna(0.0)
    bm   = bench_ret.reindex(r.index)
    cum  = (1 + r).cumprod()
    cagr = cum.iloc[-1] ** (periods / len(r)) - 1
    vol  = r.std() * np.sqrt(periods)
    ex   = r - rf_a
    sharpe = (ex.mean() * periods) / (ex.std() * np.sqrt(periods)) if ex.std() > 0 else np.nan
    dn   = ex[ex < 0].std() * np.sqrt(periods)
    sortino = (ex.mean() * periods) / dn if dn > 0 else np.nan
    dd   = (cum / cum.cummax() - 1).min()
    calmar = cagr / abs(dd) if dd < 0 else np.nan
    # alpha/beta vs SPY (OLS of excess strat on excess bench)
    import statsmodels.api as sm
    d = pd.concat([(r - rf_a).rename("y"), (bm - rf_a).rename("x")], axis=1).dropna()
    res = sm.OLS(d["y"], sm.add_constant(d["x"])).fit()
    alpha_ann = res.params["const"] * periods
    beta = res.params["x"]
    active = (r - bm).dropna()
    ir = (active.mean() * periods) / (active.std() * np.sqrt(periods)) if active.std() > 0 else np.nan
    return {"CAGR": cagr, "Vol": vol, "Sharpe": sharpe, "Sortino": sortino, "MaxDD": dd,
            "Calmar": calmar, "Alpha": alpha_ann, "Beta": beta, "IR": ir, "N": len(r)}

def window_table(rets_dict, rf, spy_ret, lo, hi):
    rows = {}
    for name, r in rets_dict.items():
        rows[name] = metrics(r.loc[lo:hi], rf, spy_ret.loc[lo:hi])
    df = pd.DataFrame(rows).T
    fmt = df.copy()
    for c in ["CAGR","Vol","MaxDD","Alpha"]: fmt[c] = (df[c]*100).map(lambda x: f"{x:6.1f}%")
    for c in ["Sharpe","Sortino","Calmar","Beta","IR"]: fmt[c] = df[c].map(lambda x: f"{x:5.2f}")
    fmt["N"] = df["N"].map(lambda x: f"{int(x)}")
    return df, fmt[["CAGR","Vol","Sharpe","Sortino","MaxDD","Calmar","Alpha","Beta","IR","N"]]

# ----------------------------------------------------------------------------- PLOTS
def make_plots(rets_dict, spy_ret, regimes, etf_returns, oos_start):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    series = {**rets_dict, "SPY": spy_ret}
    colors = {"Variant A (theory)": "tab:green", "Variant B (empirical)": "tab:orange",
              "Equal-weight": "tab:gray", "SPY": "tab:blue"}
    oos = pd.Timestamp(oos_start)

    # 1. cumulative growth (log) with IS/OOS shading
    fig, ax = plt.subplots(figsize=(12, 6))
    for n, r in series.items():
        c = (1 + r.loc[START:].dropna()).cumprod()
        ax.plot(c.index, c.values, label=n, color=colors.get(n), lw=2 if "Variant" in n else 1.4)
    ax.axvspan(oos, c.index.max(), color="gold", alpha=0.10, label="OOS (2019+)")
    ax.set_yscale("log"); ax.set_title("Growth of $1 — net of costs (log scale; gold = out-of-sample)")
    ax.set_ylabel("Growth of $1"); ax.legend(ncol=3, fontsize=9); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig("fig_sr_growth.png", dpi=140); plt.close(fig)

    # 2. drawdowns
    fig, ax = plt.subplots(figsize=(12, 5))
    for n, r in series.items():
        c = (1 + r.loc[START:].dropna()).cumprod(); dd = c/c.cummax() - 1
        ax.plot(dd.index, dd.values*100, label=n, color=colors.get(n), lw=1.6)
    ax.axvline(oos, color="k", ls=":", lw=1)
    ax.set_title("Drawdowns (%)"); ax.set_ylabel("Drawdown %"); ax.legend(ncol=4, fontsize=9); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig("fig_sr_drawdown.png", dpi=140); plt.close(fig)

    # 3. regime timeline shaded with SPY overlaid
    fig, ax = plt.subplots(figsize=(13, 5))
    spy_cum = (1 + spy_ret.loc[START:].dropna()).cumprod()
    ax.plot(spy_cum.index, spy_cum.values, color="black", lw=1.4, label="SPY (growth of $1)")
    ax.set_yscale("log")
    band = {"Goldilocks": "tab:green", "Reflation": "gold",
            "Stagflation": "tab:red", "Slowdown": "tab:blue"}
    reg = regimes.loc[START:]
    for r_lbl, col in band.items():
        in_r = reg == r_lbl
        # shade contiguous spans
        start = None
        for dt_, flag in in_r.items():
            if flag and start is None: start = dt_
            if (not flag) and start is not None:
                ax.axvspan(start, dt_, color=col, alpha=0.18); start = None
        if start is not None: ax.axvspan(start, in_r.index[-1], color=col, alpha=0.18)
    handles = [plt.Rectangle((0,0),1,1, color=c, alpha=0.3) for c in band.values()]
    ax.legend(handles + [plt.Line2D([0],[0], color="black")],
              list(band.keys()) + ["SPY"], ncol=5, fontsize=9, loc="upper left")
    ax.set_title("Macro-regime timeline (shaded) with SPY overlaid — sanity check")
    fig.tight_layout(); fig.savefig("fig_sr_regime.png", dpi=140); plt.close(fig)

    # 4. average sector return by regime (heatmap, annualised, descriptive)
    reg_aligned = regimes.reindex(etf_returns.index)
    grid = pd.DataFrame({rg: etf_returns[reg_aligned == rg].mean()*12 for rg in REGIMES})
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(grid.values*100, cmap="RdYlGn", aspect="auto")
    ax.set_xticks(range(len(REGIMES))); ax.set_xticklabels(REGIMES, rotation=20)
    ax.set_yticks(range(len(grid.index))); ax.set_yticklabels(grid.index)
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            ax.text(j, i, f"{grid.values[i,j]*100:.0f}", ha="center", va="center", fontsize=8)
    ax.set_title("Avg annualised sector return by regime (%)"); fig.colorbar(im, label="% ann.")
    fig.tight_layout(); fig.savefig("fig_sr_heatmap.png", dpi=140); plt.close(fig)
    return grid

# ----------------------------------------------------------------------------- MAIN
def main():
    print("=" * 96)
    print("PACKAGE VERSIONS (reproducibility)")
    import matplotlib, statsmodels
    mods = {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__,
            "matplotlib": matplotlib.__version__, "statsmodels": statsmodels.__version__}
    try:
        import yfinance, pandas_datareader
        mods["yfinance"] = yfinance.__version__; mods["pandas_datareader"] = pandas_datareader.__version__
    except Exception: pass
    print("  " + " | ".join(f"{k}={v}" for k, v in mods.items()))

    etf, spy, macro, rf, rf_label = fetch_data()
    etf_ret = etf.pct_change()
    spy_ret = spy.pct_change()
    regimes = build_regimes(macro)
    # align regimes to the price month-end grid
    regimes = regimes.reindex(etf_ret.index).ffill().dropna()
    OOS_END = etf_ret.dropna(how="all").index.max()       # handle later-than-expected end gracefully
    print(f"\nRisk-free source: {rf_label}")
    print(f"Sample: {regimes.index.min():%Y-%m} .. {OOS_END:%Y-%m}  (OOS = {OOS_START[:7]} onward)")

    # Regime timeline output
    regimes.rename("regime").to_csv(CACHE / "regime_timeline.csv")
    print("\nRegime timeline (first/last 3):")
    print(pd.concat([regimes.head(3), regimes.tail(3)]).to_string())

    # Allocations
    W_A = allocate_theory(regimes, etf.columns)
    W_B = allocate_empirical(regimes, etf_ret)
    W_E = allocate_equal(regimes.index, etf.columns)

    rA, tA = backtest(W_A, etf_ret)
    rB, tB = backtest(W_B, etf_ret)
    rE, tE = backtest(W_E, etf_ret)
    rets = {"Variant A (theory)": rA, "Variant B (empirical)": rB, "Equal-weight": rE}

    # Reports over three windows
    for title, lo, hi in [("FULL SAMPLE", START, OOS_END),
                          ("IN-SAMPLE 2000-2018", IS_START, IS_END),
                          ("OUT-OF-SAMPLE 2019-present", OOS_START, OOS_END)]:
        df, fmt = window_table({**rets, "SPY": spy_ret}, rf, spy_ret, lo, hi)
        lo_s, hi_s = pd.Timestamp(lo).strftime("%Y-%m"), pd.Timestamp(hi).strftime("%Y-%m")
        print("\n" + "=" * 96 + f"\n{title}  ({lo_s} .. {hi_s})\n" + "-" * 96)
        print(fmt.to_string())

    # Turnover (annualised)
    print("\n" + "=" * 96 + "\nANNUALISED TURNOVER")
    for n, t in {"Variant A": tA, "Variant B": tB, "Equal-weight": tE}.items():
        print(f"  {n:14s}: {t.loc[START:].mean()*12*100:6.1f}%")

    # Mean strategy return by regime + % months per regime
    print("\n" + "=" * 96 + "\nMEAN MONTHLY RETURN BY REGIME (net) & REGIME FREQUENCY")
    reg_full = regimes.loc[START:OOS_END]
    freq = reg_full.value_counts(normalize=True).reindex(REGIMES) * 100
    by_reg = pd.DataFrame({
        "% months": freq.round(1),
        "Var A (mo%)": pd.Series({rg: rA.loc[START:][reg_full == rg].mean()*100 for rg in REGIMES}).round(2),
        "Var B (mo%)": pd.Series({rg: rB.loc[START:][reg_full == rg].mean()*100 for rg in REGIMES}).round(2),
        "SPY (mo%)":   pd.Series({rg: spy_ret.loc[START:][reg_full == rg].mean()*100 for rg in REGIMES}).round(2),
    })
    print(by_reg.to_string())

    grid = make_plots(rets, spy_ret, regimes, etf_ret, OOS_START)
    print("\nSaved plots: fig_sr_growth.png, fig_sr_drawdown.png, fig_sr_regime.png, fig_sr_heatmap.png")
    print("Saved regime timeline: data_cache/regime_timeline.csv")
    print("\nReminder: ALL results are SIMULATED on historical data; design frozen pre-2019, OOS run unchanged.")

if __name__ == "__main__":
    main()
