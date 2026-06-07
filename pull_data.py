# %% [markdown]
# # Data pull — S&P 500 universe via yfinance
#
# Pulls:
# - S&P 500 membership + GICS sectors (public index membership, cached in data_cache/;
#   Bloomberg point-in-time membership is used separately for the survivorship correction)
# - Monthly adjusted close prices for each ticker, 2000-01 to today
# - SPY, XLK, MTUM, QUAL, VLUE, USMV (benchmarks)
# - ^VIX (CBOE VIX)
#
# Outputs to `data_cache/`:
# - `sp500_constituents.csv`  (Ticker, Sector, Industry, Name)
# - `prices_monthly.csv`       (date index, ticker columns, adjusted close)
# - `benchmarks_monthly.csv`   (date index, SPY/XLK/MTUM/QUAL/VLUE/USMV)
# - `vix_monthly.csv`          (date index, VIX close)

# %%
import os
import time
import io
import urllib.request
from pathlib import Path
import pandas as pd
import numpy as np
import yfinance as yf

CACHE = Path("data_cache")
CACHE.mkdir(exist_ok=True)
START = "2000-01-01"
END   = "2026-06-01"

# %% [markdown]
# ## 1. S&P 500 membership + GICS sectors (public index data, cached)

# %%
def get_sp500_constituents():
    # Universe = current S&P 500 membership with GICS sectors (public index data),
    # committed to the repo at data_cache/sp500_constituents.csv. The rigorous,
    # point-in-time membership used for the survivorship correction comes from Bloomberg.
    cache_path = CACHE / "sp500_constituents.csv"
    if cache_path.exists():
        print(f"Using S&P 500 membership: {cache_path}")
        return pd.read_csv(cache_path)
    raise FileNotFoundError(
        f"{cache_path} not found. Provide the S&P 500 membership list with columns "
        "ticker,name,sector,industry (public index membership + GICS sectors). "
        "It is committed to the repo, so this should not normally occur."
    )

constituents = get_sp500_constituents()
print(f"Constituents: {len(constituents)}")
print(f"Sectors:\n{constituents['sector'].value_counts()}")
tech_tickers = constituents[constituents["sector"] == "Information Technology"]["ticker"].tolist()
print(f"\nTech universe (GICS IT): {len(tech_tickers)}")

# %% [markdown]
# ## 2. Bulk download monthly prices

# %%
def download_prices(tickers, start, end, label, retries=3):
    cache_path = CACHE / f"prices_{label}_monthly.csv"
    if cache_path.exists():
        print(f"Using cached prices: {cache_path}")
        return pd.read_csv(cache_path, index_col=0, parse_dates=True)

    print(f"Downloading {len(tickers)} tickers (label={label}), {start} to {end}...")
    # yfinance's auto_adjust=True returns split & dividend-adjusted close
    px = yf.download(
        tickers, start=start, end=end,
        interval="1mo", auto_adjust=True, progress=False, group_by="ticker", threads=True,
    )
    # If single ticker, columns are flat; if multi, MultiIndex
    if isinstance(px.columns, pd.MultiIndex):
        # Extract just the Close column for each ticker
        close = pd.DataFrame({t: px[t]["Close"] for t in tickers if t in px.columns.levels[0]})
    else:
        close = px[["Close"]].rename(columns={"Close": tickers[0]})
    close.index = pd.to_datetime(close.index)
    # Normalize to month-end alignment
    close = close.resample("ME").last()
    close.to_csv(cache_path)
    print(f"Saved: {cache_path} (shape {close.shape})")
    return close

# Universe price pull — full S&P 500
universe_tickers = constituents["ticker"].tolist()
prices_all = download_prices(universe_tickers, START, END, "sp500")

# Benchmarks
bench_tickers = ["SPY", "XLK", "MTUM", "QUAL", "VLUE", "USMV"]
benchmarks = download_prices(bench_tickers, START, END, "benchmarks")

# VIX
vix = download_prices(["^VIX"], START, END, "vix")
vix.columns = ["VIX"]

# %% [markdown]
# ## 3. Sanity checks and report

# %%
print("=" * 70)
print("DATA PULL SUMMARY")
print("=" * 70)
print(f"Universe prices: {prices_all.shape[0]} months × {prices_all.shape[1]} tickers")
print(f"  Date range: {prices_all.index.min():%Y-%m} to {prices_all.index.max():%Y-%m}")
# coverage per ticker
coverage = prices_all.notna().sum() / len(prices_all)
print(f"  Tickers with >80% coverage: {(coverage > 0.8).sum()}")
print(f"  Tickers with >50% coverage: {(coverage > 0.5).sum()}")

# Sanity check on a few well-known tickers
for t in ["AAPL", "MSFT", "AMZN", "JPM"]:
    if t in prices_all.columns:
        s = prices_all[t].dropna()
        if len(s):
            print(f"  {t}: {len(s)} months, "
                  f"first ${s.iloc[0]:.2f} ({s.index[0]:%Y-%m}), "
                  f"last ${s.iloc[-1]:.2f} ({s.index[-1]:%Y-%m})")

print(f"\nBenchmarks: {benchmarks.shape}")
print(f"  Tickers: {list(benchmarks.columns)}")
for t in benchmarks.columns:
    s = benchmarks[t].dropna()
    if len(s):
        print(f"  {t}: {s.index[0]:%Y-%m} to {s.index[-1]:%Y-%m} ({len(s)} pts)")

print(f"\nVIX: {vix.shape[0]} months, {vix.index.min():%Y-%m} to {vix.index.max():%Y-%m}")
print(f"  VIX range: {vix['VIX'].min():.1f} to {vix['VIX'].max():.1f}")

# Tech subset
tech_present = [t for t in tech_tickers if t in prices_all.columns]
print(f"\nTech subset: {len(tech_present)} / {len(tech_tickers)} GICS Tech tickers available in price data")
