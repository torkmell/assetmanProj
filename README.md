# GSD²T Asset Management — Quant Fund Pitch

ESADE Asset Management Course · Group Project · Live pitch **10 June 2026**

A fictional quantitative hedge fund pitched as the course capstone, seeking a hypothetical **USD 100M** commitment. All performance is **SIMULATED**; the fund does not exist.

---

## The strategy

**GSD²T — Macro-Overlay Equity Momentum (long-only, with a defensive Treasuries-and-gold sleeve).**

A systematic, long-only S&P 500 strategy with two layers and a risk-off sleeve:

1. **Selection** — 12-1 month cross-sectional momentum across the **whole S&P 500** (all 11 sectors), equal-weight top quartile (~125 names). Diversified, not a sector bet.
2. **Macro overlay** — a 4-factor regime "risk dial" (VIX, credit spread, 10Y yield change, index trend) scales gross equity exposure between **30% and 100%**.
3. **Defensive sleeve (the "V1" refinement)** — when the overlay de-risks, the un-invested capital earns **Treasuries + gold** (convexity in crises), not idle cash.

**The edge is capital preservation, not a faster signal:** disciplined, rules-based de-risking that most discretionary investors cannot execute under pressure. Long-only, no leverage, no shorting, monthly rebalance, 15 bps round-trip cost.

---

## Top-line results (SIMULATED, 2002–2026, net of 15 bps costs)

| | CAGR | Vol | Sharpe | Max DD | Alpha (FF5+Mom) |
|---|---|---|---|---|---|
| **GSD²T — gross strategy (V1)** | **14.9%** | 11.9% | **1.09** | **−21.2%** | **+5.4% (t=4.3)** |
| **GSD²T — net to investor** | **13.1%** | — | 0.96 | −23.5% | — |
| S&P 500 (SPY) | 10.0% | 15.1% | 0.60 | −50.8% | — |

- **In-sample / out-of-sample:** IS Sharpe 1.16 → **OOS Sharpe 1.01** — a modest step-down, not a collapse (OOS still beats the market's 0.86).
- **Risk:** roughly two-thirds of the market's volatility and **less than half its drawdown**.
- The strategy evolved from a narrower Tech-only prototype → full sector-wide → the V1 defensive sleeve (the current flagship). Earlier iterations are retained for research transparency.

---

## Honesty (rubric-aligned)

| Item | Status |
|---|---|
| Survivorship bias | ✅ **Corrected** — measured on Bloomberg point-in-time S&P 500 (1,085 names incl. delisted); bias is only ~1%/yr |
| Look-ahead | ✅ All signals lagged ≥1 month; trailing-only z-scores; 2000–01 reserved as warm-up |
| Transaction costs | ✅ 15 bps round-trip on all turnover; every figure is net of costs |
| Out-of-sample / train-test | ✅ IS 2002–15 / OOS 2016–26; OOS Sharpe **1.01 vs IS 1.16** — modest step-down, disclosed (still beats the market's 0.86) |
| Overfitting | ✅ Standard enhancements (risk-managed momentum, vol targeting, low-beta, quality) tested and **rejected** — none beat the simple design OOS |
| Factor regression | ✅ FF5 + Momentum with Newey-West HAC standard errors |
| Capacity | ✅ Soft cap **$1.7–3.3B** (5%-ADV × 2-day, ADV measured ~$150–300M per name), **17–33×** the $100M raise |
| Stress tests | ✅ 7 crisis windows (Dot-com, GFC, Eurozone, China, Vol-spike 2018, COVID, 2022) |
| Simulated vs live | ✅ Labelled everywhere; the fund is fictional |

---

## Fund terms

1.0% management + **15% performance over the S&P 500** (benchmark-relative), relative high-water mark, annual crystallisation, **monthly liquidity, no lock-up**. Net of all fees the investor still earns ~13.1% vs the market's 10.0%, at higher Sharpe and ~half the drawdown.

---

## Key files

```
Strategy & backtests
├── sectorwide_full.py            ← core sector-wide backtest (full institutional appendix)
├── build_v1_flagship.py          ← V1 (defensive sleeve) flagship: metrics, alpha, net-of-fee
├── survivorship_corrected.py     ← Bloomberg point-in-time survivorship test
├── bakeoff_variants.py           ← variant bake-off (how V1 was found)
├── bakeoff_improvements.py       ← enhancements tested on V1 (all rejected OOS)

Deliverables
├── GSD2T_Quant_Appendix.ipynb    ← quant appendix notebook (the .ipynb submission) + matching .pdf
├── GSD2T_Pitch_Deck.pptx         ← 15-slide pitch deck (export slides 1–15 to PDF for submission)
├── GSD2T_Pitch_Script.docx       ← run-of-show / speaker script + Q&A playbook
├── GSD2T_QA_Simulation.docx      ← 39-question Q&A preparation
├── sectorwide_dashboard.html     ← interactive dashboard (Overview, Risk, Survivorship, Point-in-Time, Terms)
├── SectorWide_Strategy_Overview.docx  ← strategy brief (incl. survivorship section)
├── Strategy_Refinement_Findings.docx  ← bake-off findings memo (V1 + enhancements)

Generators & data
├── make_sectorwide_brief.py / make_bakeoff_memo.py / make_sectorwide_dashboard.py / build_deck.py
├── data_cache/                   ← cached market data (prices, benchmarks, VIX, macro, defensive ETFs)
├── course_data/                  ← Ken French factors & course datasets
├── Total Returns Hard Copy.xlsx  ← Bloomberg point-in-time S&P 500 total returns
└── HOW_TO_RUN.md                 ← full reproducibility instructions
```

Earlier prototypes (Tech-only S1, long/short experiments, sector-rotation v1) remain in the repo for transparency but are **superseded** by the sector-wide + defensive-sleeve flagship above.

---

## How to run

Everything is self-contained and uses relative paths. See **[HOW_TO_RUN.md](HOW_TO_RUN.md)** for full steps. In short:

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python build_v1_flagship.py          # reproduce the flagship numbers
python build_deck.py                 # rebuild the pitch deck
```

All market data is cached, so it runs **fully offline**. The HTML dashboards are self-contained — just open them in a browser.

---

## AI-tool disclosure

AI assistants were used for code scaffolding, back-test engineering, and document drafting. All strategy decisions, data choices, and results were defined and verified by the team. No results were fabricated; every figure is reproducible from the committed code.

---

## Disclaimer

This repository is a **fictional pitch** prepared for the ESADE Asset Management course. It does not constitute investment advice or an offer to sell securities. The fund "GSD²T Asset Management" does not exist. All performance is **simulated** on historical data; past performance — simulated or otherwise — does not indicate future results.

## Team

GSD²T Asset Management · ESADE MSc · Live pitch 10 June 2026
