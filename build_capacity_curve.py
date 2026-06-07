"""Capacity curve — net Sharpe vs AUM, using the square-root market-impact law (course L7).
The single most important capacity diagnostic. Output: capacity_curve.json + fig_capacity_curve.png
"""
import json
import numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

V=json.load(open("v1_flagship.json")); F=json.load(open("sectorwide_full.json"))
SR_GROSS=V["summary"]["Fund (full)"]["Sharpe"]; SIGMA=V["summary"]["Fund (full)"]["Vol"]
SR_SPY=V["summary"]["SPY"]["Sharpe"]; N_HELD=F["capacity"]["avg_n_holdings"]
ANN_TO_2WAY=V["ops"]["avg_annual_turnover"]                 # ~3.8 (sum |dw|, two-way)
TO_ONEWAY_M=(ANN_TO_2WAY/2)/12.0                            # one-way monthly fraction traded
ADV=150e6                                                   # measured median $ADV per name (conservative)
SIG_DAILY=0.02; Y=1.0                                       # large-cap daily vol; square-root constant

# impact(Q) = sigma_daily * Y * sqrt(Q/V); annual cost = one-way annual turnover * impact-per-trade
def net_sharpe(aum):
    per_name_trade=aum*TO_ONEWAY_M/N_HELD                   # $ traded per name per monthly rebalance
    participation=per_name_trade/ADV                        # fraction of one day's ADV
    impact=SIG_DAILY*Y*np.sqrt(max(participation,0))        # price impact per trade (fraction)
    ann_cost=(ANN_TO_2WAY/2)*impact                         # annual return drag from impact
    return SR_GROSS-ann_cost/SIGMA, participation/2.0       # /2 = daily participation over 2-day execution

grid=[1e8,2.5e8,5e8,1e9,1.7e9,3.3e9,5e9,1e10,2.5e10,5e10]
rows=[]
for a in grid:
    sr,dadv=net_sharpe(a); rows.append({"AUM":a,"daily_pct_ADV":dadv,"net_sharpe":float(sr)})
soft_lo,soft_hi=F["capacity"]["soft_cap_low"],F["capacity"]["soft_cap_high"]

print("="*64)
print("CAPACITY CURVE — net Sharpe vs AUM (square-root impact, ADV=$150M)")
print("="*64)
print(f"{'AUM':>10}{'daily %ADV':>12}{'net Sharpe':>12}")
for r in rows:
    a=r["AUM"]; lab=f"${a/1e9:.1f}B" if a>=1e9 else f"${a/1e6:.0f}M"
    print(f"{lab:>10}{r['daily_pct_ADV']*100:11.2f}%{r['net_sharpe']:12.2f}")
print(f"\n5%-ADV soft cap region: ${soft_lo/1e9:.1f}-{soft_hi/1e9:.1f}B  |  raise = $100M  |  gross Sharpe {SR_GROSS:.2f}, market {SR_SPY:.2f}")

json.dump({"grid":rows,"soft_cap_low":soft_lo,"soft_cap_high":soft_hi,"sr_gross":SR_GROSS,"sr_spy":SR_SPY,
           "assumptions":{"adv_per_name":ADV,"daily_vol":SIG_DAILY,"n_held":N_HELD,"ann_turnover_2way":ANN_TO_2WAY}},
          open("capacity_curve.json","w"),indent=2)

NAVY="#0B1F3A"; GOLD="#C9A96E"; GREY="#5A6F8C"; POS="#2E7D5B"
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":12})
fig,ax=plt.subplots(figsize=(8.2,4.6))
xs=[r["AUM"] for r in rows]; ys=[r["net_sharpe"] for r in rows]
ax.plot(xs,ys,"-o",color=NAVY,lw=2.2,ms=5,zorder=3,label="Net Sharpe (after impact)")
ax.axhline(SR_SPY,color=GREY,ls=":",lw=1.4,label=f"S&P 500 ({SR_SPY:.2f})")
ax.axvspan(soft_lo,soft_hi,color=GOLD,alpha=0.18,zorder=1)
ax.axvline(1e8,color=POS,ls="--",lw=1.4)
ax.text(1.05e8,0.66,"$100M raise",color=POS,fontsize=10,rotation=90,va="bottom")
ax.text(np.sqrt(soft_lo*soft_hi),SR_GROSS+0.005,"5%-ADV soft cap\n$1.7–3.3B",color="#8a6d10",fontsize=9,ha="center",va="bottom")
ax.set_xscale("log"); ax.set_xlabel("AUM (log scale)"); ax.set_ylabel("Net Sharpe ratio")
ax.set_ylim(0.55,SR_GROSS+0.10); ax.grid(alpha=0.25,zorder=0); ax.legend(loc="lower left",fontsize=10)
ax.set_title("Capacity curve — net Sharpe vs AUM (SIMULATED, square-root impact)",fontsize=13,color=NAVY)
import matplotlib.ticker as mt
ax.xaxis.set_major_formatter(mt.FuncFormatter(lambda x,_: f"${x/1e9:.0f}B" if x>=1e9 else f"${x/1e6:.0f}M"))
fig.tight_layout(); fig.savefig("fig_capacity_curve.png",dpi=160); plt.close(fig)
print("Saved capacity_curve.json and fig_capacity_curve.png")
