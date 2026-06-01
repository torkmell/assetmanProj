# GSD2T Asset Management — Quant Fund Pitch

ESADE Asset Management Course · Group Project · Live pitch **10 June 2026**

Fictional quantitative hedge fund pitched as the course capstone. Strategy candidates were backtested on a 73-stock S&P 500 Tech universe with macroeconomic regime overlays. All performance is **SIMULATED**; the fund does not exist.

---

## Top-line results

Six strategy iterations were tested on the same universe and window (2002-01 to 2026-05, monthly, net of 15 bps round-trip cost). Two contenders emerged:

| Strategy | CAGR | Sharpe | MaxDD | Calmar | Status |
|---|---|---|---|---|---|
| **S1 — Macro-Overlay Tech (pure momentum, long-only)** | **16.1%** | **0.93** | **-28%** | **0.57** | **Pitched** |
| **S2c — Multi-Factor + Macro Overlay** | 12.9% | 0.95 | -27% | 0.48 | Viable alternative |
| S2 — 3-factor L/S | -12.6% | -0.49 | -97% | -0.13 | Rejected |
| S2a — 2-factor L/S | -12.1% | -0.37 | -98% | -0.12 | Rejected |
| S2b — 2-factor long-only (no overlay) | 18.8% | 0.92 | -50% | 0.38 | Rejected (no overlay = unacceptable DD) |
| S3 — Tech + VIX L/S | 4.9% | 0.39 | -42% | 0.12 | Rejected (lukewarm) |

Reference benchmarks (same window):
- SPY: 10.0% CAGR, 0.65 Sharpe, -51% MaxDD
- XLK: 13.4% CAGR, 0.72 Sharpe, -50% MaxDD
- MTUM: 16.2% CAGR, 1.00 Sharpe (gold standard factor ETF; we match it)

---

## Repository layout

```
.
├── README.md                            ← you are here
├── requirements.txt                     ← Python dependencies
├── .gitignore
│
├── pull_data.py                         ← yfinance data pull (S&P 500, benchmarks, VIX, macro proxies)
├── strategies_tech.py                   ← Three-strategy comparison on tech universe (S1/S2/S3)
├── strategy_one_full.py                 ← S1 with full hygiene: walk-forward, DSR, capacity, sensitivity
├── strategy_two_variants.py             ← S2 fix experiments (S2a, S2b, S2c)
├── backtest.py                          ← Original GSD2T v1 sector rotation backtest (superseded)
├── strategy_ab.py                       ← Earlier S&P-500-wide vs Tech-VIX comparison (superseded)
│
├── data_cache/                          ← Cached yfinance pulls (re-runnable via pull_data.py)
│   ├── sp500_constituents.csv
│   ├── prices_sp500_monthly.csv         ← 503 tickers × 317 months
│   ├── prices_benchmarks_monthly.csv    ← SPY, XLK, MTUM, QUAL, USMV, VLUE
│   ├── prices_vix_monthly.csv
│   └── macro_proxies_monthly.csv        ← HYG, IEF, ^TNX, ^GSPC, LQD
│
├── gsd2t_full.json                      ← Strategy 1 (pitched fund) full backtest data
├── strategies_full_comparison.json      ← All 6 iterations combined
├── tech_comparison_data.json            ← 3-strategy tech comparison
├── comparison_data.json                 ← Earlier comparison (different windows)
│
├── gsd2t_dashboard.html                 ← S1 full 5-tab dashboard (the pitched fund)
├── strategies_full_dashboard.html       ← All 6 strategy iterations (research transparency)
├── tech_comparison_dashboard.html       ← S1 vs S2 vs S3 (the 3-way that prompted the S1 pick)
├── comparison_dashboard.html            ← Earlier 3-way (mixed windows, superseded)
├── dashboard.html / dashboard_standalone.html  ← Original GSD2T v1 sector rotation (superseded)
│
├── GSD2T_OnePager.html                  ← Institutional one-pager (currently still describes v1 sector rotation)
└── gsd2t_logo.svg                       ← Fund logo
```

All HTML dashboards are **self-contained** (inline JSON, Plotly.js from CDN). Just double-click to open in any browser.

---

## How to run the backtest yourself

### 1. Clone and set up the environment

```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
python3 -m venv .venv
source .venv/bin/activate           # macOS / Linux
# .venv\Scripts\activate            # Windows
pip install -r requirements.txt
```

### 2. (Optional) Re-pull the data

The `data_cache/` directory already has all the data needed to reproduce the backtests. If you want to refresh from yfinance:

```bash
python pull_data.py
```

This pulls the current S&P 500 constituent list from Wikipedia, then downloads monthly adjusted-close prices for all ~500 stocks plus the benchmark ETFs and VIX. Takes ~2 minutes. Cache is written to `data_cache/`.

### 3. Run the strategies

```bash
# Strategy 1 — the pitched fund, with full hygiene
python strategy_one_full.py

# Three-strategy comparison (S1 / S2 / S3)
python strategies_tech.py

# Strategy 2 fix experiments (S2a / S2b / S2c)
python strategy_two_variants.py
```

Each script prints its results and writes a JSON file consumed by the corresponding dashboard.

### 4. View the dashboards

Just open the `.html` files in your browser:

- **`gsd2t_dashboard.html`** — the pitched fund (S1: Macro-Overlay Tech), 5 tabs, full institutional appendix
- **`strategies_full_dashboard.html`** — all six iterations side-by-side, the "research transparency" view
- **`tech_comparison_dashboard.html`** — the three-strategy view (S1/S2/S3) that prompted the S1 pick

---

## Strategy summary

### S1: Macro-Overlay Tech (the pitched fund)

- **Universe:** S&P 500 ∩ GICS Information Technology (73 stocks). Survivorship-biased to current constituents — disclosed.
- **Signal:** 12-month cross-sectional momentum skipping the most recent month, z-scored within the universe.
- **Position:** Long-only top quartile (≈18 stocks), equal-weight within the long sleeve.
- **Macro overlay:** Composite of four lagged regime signals — VIX (inverted), credit spread (HYG vs IEF), 10Y yield change, SPX 12-1m trend. Maps to gross exposure in [30%, 100%]; cash sleeve earns RF.
- **Rebalance:** Monthly. Transaction costs: 15 bps round-trip.
- **Result:** 16.1% CAGR, 0.93 Sharpe, -28.1% MaxDD. Significant alpha vs FF5+MOM (+5.79%, t=3.08). OOS Sharpe (1.20) materially exceeds IS (0.71).

### Why we rejected the L/S variants

Strategies 2, 2a, and 3 all use a long-short structure. The 73-stock tech universe is too concentrated (5-10 mega-caps drive most of the index's returns) for long-short to work — shorting any of those names during the 2018-2024 AI rally generated catastrophic drawdowns (-97% to -98%). This is consistent with the well-documented multi-factor L/S underperformance period at firms like AQR and Two Sigma.

The structural choice (long-only vs L/S) dominates the signal choice (momentum vs multi-factor) in this universe.

---

## Backtest hygiene (rubric checklist)

| Item | Status |
|---|---|
| Universe defined ex ante | ⚠ Current S&P 500 (survivorship — disclosed) |
| Point-in-time data | ✅ All price-based; no look-ahead in signals |
| Transaction costs | ✅ 15 bps round-trip |
| Net + gross reported | ✅ |
| Out-of-sample / walk-forward | ✅ IS 2002–15 / OOS 2016–26 |
| Deflated Sharpe Ratio | ✅ Reported (n=15 trials, PSR disclosed) |
| Capacity analysis | ✅ Soft cap ~$460M at 5%-ADV × 2-day execution |
| Stress scenarios | ✅ 7 named windows (Dot-com, GFC, Eurozone, China, Vol spike 2018, COVID, 2022 bear) |
| Factor regression | ✅ FF5+MOM with Newey-West HAC SEs |
| Simulated vs live labeled | ✅ Everywhere |

---

## Disclaimer

This repository is a **fictional pitch** prepared for the ESADE Asset Management course. It does not constitute investment advice or an offer to sell securities. The fund "GSD2T Asset Management" does not exist. All performance figures are **simulated** on historical data; past performance — simulated or otherwise — is not indicative of future results. Universe is biased to current S&P 500 constituents; survivorship bias is disclosed and not corrected.

---

## Team

GSD2T Asset Management · ESADE MSc · Live pitch 10 June 2026
