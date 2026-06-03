"""P&L chart for the pitched fund (S1), built from gsd2t_full.json.
Outputs fig_pnl.png — cumulative dollar P&L on a $100M notional + annual P&L bars."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

NAV0 = 100_000_000   # $100M starting notional (matches the capacity analysis)

d = json.load(open("gsd2t_full.json"))
ec = d["equity_curves"]["Fund (Macro-Overlay Tech)"]
spy = d["equity_curves"]["SPY"]

def to_series(pairs):
    idx = pd.to_datetime([p[0] for p in pairs])
    return pd.Series([p[1] for p in pairs], index=idx)

cum   = to_series(ec)        # growth of $1 (cumulative)
cum_s = to_series(spy)
# monthly returns from the cumulative curve
ret   = cum.pct_change(); ret.iloc[0] = cum.iloc[0] - 1.0

# NAV and cumulative dollar P&L (reinvested)
nav      = NAV0 * cum
pnl_cum  = nav - NAV0
nav_spy  = NAV0 * cum_s
pnl_spy  = nav_spy - NAV0

# Annual P&L in %
ann = (1 + ret).groupby(ret.index.year).prod() - 1

# ---- Figure: 2 panels ----
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8),
                               gridspec_kw={"height_ratios": [2, 1]})
fig.suptitle("GSD2T Macro-Overlay Tech — Simulated P&L  (SIMULATED, $100M notional, net of costs)",
             fontsize=13, fontweight="bold")

# Panel 1: cumulative dollar P&L
m_usd = FuncFormatter(lambda x, _: f"${x/1e6:,.0f}M")
ax1.fill_between(pnl_cum.index, pnl_cum.values/1e6, 0, alpha=0.25, color="tab:green")
ax1.plot(pnl_cum.index, pnl_cum.values/1e6, color="tab:green", lw=2, label="GSD2T Fund")
ax1.plot(pnl_spy.index, pnl_spy.values/1e6, color="tab:blue", lw=1.3, ls="--", label="SPY (same $100M)")
ax1.axhline(0, color="k", lw=0.7)
ax1.set_ylabel("Cumulative P&L ($M)")
ax1.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"${x:,.0f}M"))
ax1.legend(loc="upper left"); ax1.grid(alpha=0.3)
final = pnl_cum.iloc[-1]
ax1.annotate(f"  ${final/1e6:,.0f}M",
             (pnl_cum.index[-1], pnl_cum.iloc[-1]/1e6),
             color="tab:green", fontweight="bold", va="center")

# Panel 2: annual P&L bars (green/red)
colors = ["tab:green" if v >= 0 else "tab:red" for v in ann.values]
ax2.bar(ann.index, ann.values*100, color=colors, alpha=0.85)
ax2.axhline(0, color="k", lw=0.7)
ax2.set_ylabel("Annual P&L (%)"); ax2.set_xlabel("Year")
for x, v in zip(ann.index, ann.values):
    ax2.annotate(f"{v*100:.0f}", (x, v*100), ha="center",
                 va="bottom" if v >= 0 else "top", fontsize=7)
ax2.grid(alpha=0.3, axis="y")

fig.tight_layout(rect=[0, 0, 1, 0.97])
fig.savefig("fig_pnl.png", dpi=140)
print("Wrote fig_pnl.png")
print(f"Final cumulative P&L on $100M: ${final/1e6:,.1f}M  (NAV ${nav.iloc[-1]/1e6:,.0f}M)")
print(f"SPY same period:               ${pnl_spy.iloc[-1]/1e6:,.1f}M")
print(f"Best year:  {ann.idxmax()}  {ann.max()*100:+.1f}%")
print(f"Worst year: {ann.idxmin()}  {ann.min()*100:+.1f}%")
print(f"Positive years: {(ann>0).sum()}/{len(ann)}")
