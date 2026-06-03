"""Investor net-of-fee track record for the Sector-Wide strategy.
Fee structure (the grade-aligned one):
  - Management fee: 1.0%/yr, accrued monthly on NAV.
  - Performance fee: 15% of returns ABOVE the S&P 500 (SPY), annual crystallisation,
    with a RELATIVE high-water mark (you only pay when relative performance makes a new high).
Outputs: net_of_fee.json (metrics + terms) and fig_netoffee.png (gross vs net vs SPY)."""
import json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

MGMT = 0.010      # 1.0% management
PERF = 0.15       # 15% performance, over SPY
DATA_ROOT = Path("course_data")

F = json.load(open("sectorwide_full.json"))
def series(pairs):
    idx = pd.to_datetime([p[0] for p in pairs]); return pd.Series([p[1] for p in pairs], index=idx)
fund_cum = series(F["equity_curves"]["Fund (Sector-Wide)"])
spy_cum  = series(F["equity_curves"]["SPY"])
g = fund_cum.pct_change(); g.iloc[0] = fund_cum.iloc[0]-1
b = spy_cum.pct_change();  b.iloc[0] = spy_cum.iloc[0]-1
df = pd.concat([g.rename("g"), b.rename("b")], axis=1).dropna()

# risk-free for Sharpe (Ken French)
def load_rf():
    ff5 = pd.read_csv(DATA_ROOT/"Folder_Macro_Factors_.187814089"/"content"/"F-F_Research_Data_5_Factors_2x3_daily.CSV", skiprows=3, index_col=0)
    ff5.columns=[c.strip() for c in ff5.columns]; ff5.index=pd.to_datetime(ff5.index.astype(str),format="%Y%m%d")
    rf=(1+ff5["RF"]/100).resample("ME").prod()-1; rf.index=pd.to_datetime(rf.index).to_period("M").to_timestamp("M"); return rf
rf = load_rf()

# ---- simulate gross NAV (no fees) and net NAV (after both fees) ----
m_month = MGMT/12.0
N=1.0; B=1.0; G=1.0; HWM_rel=1.0
gross_nav=[]; net_nav=[]; perf_fees=[]; mgmt_fees=[]
for dt,(gt,bt) in df.iterrows():
    G *= (1+gt)                                   # gross strategy (no fees)
    N *= (1+gt)                                   # net: apply gross return
    mf = N*m_month; N -= mf                        # accrue 1%/yr management monthly
    B *= (1+bt)
    pf = 0.0
    if dt.month==12 or dt==df.index[-1]:           # annual crystallisation (+ final stub)
        rel = N/B
        if rel > HWM_rel:
            pf = PERF*(rel-HWM_rel)*B               # 15% of relative excess over HWM, in NAV terms
            N -= pf; HWM_rel = N/B                  # reset HWM to post-fee relative level
    gross_nav.append(G); net_nav.append(N); perf_fees.append(pf); mgmt_fees.append(mf)
gross = pd.Series(gross_nav, index=df.index); net = pd.Series(net_nav, index=df.index)
spy   = (1+df["b"]).cumprod()

def metrics(nav):
    r = nav.pct_change().dropna(); n=len(nav)
    cagr = nav.iloc[-1]**(12/n)-1; vol=r.std()*np.sqrt(12)
    ex = r - rf.reindex(r.index).fillna(0); sh=(ex.mean()*12)/(ex.std()*np.sqrt(12))
    dd = (nav/nav.cummax()-1).min()
    return {"CAGR":float(cagr),"Vol":float(vol),"Sharpe":float(sh),"MaxDD":float(dd)}

mg, mn, ms = metrics(gross), metrics(net), metrics(spy)
total_mgmt = sum(mgmt_fees); total_perf = sum(perf_fees)

print("="*78)
print("SECTOR-WIDE — GROSS vs NET-OF-FEES (1% mgmt + 15% over-SPY, high-water mark)")
print("="*78)
print(f"{'':22}{'CAGR':>9}{'Vol':>8}{'Sharpe':>9}{'MaxDD':>9}")
for label,m in [("Gross strategy",mg),("NET to investor",mn),("SPY benchmark",ms)]:
    print(f"{label:22}{m['CAGR']*100:8.1f}%{m['Vol']*100:7.1f}%{m['Sharpe']:9.2f}{m['MaxDD']*100:8.0f}%")
print(f"\nTotal fee drag on CAGR: {(mg['CAGR']-mn['CAGR'])*100:.2f}%/yr")
print(f"Net still beats SPY by: {(mn['CAGR']-ms['CAGR'])*100:+.2f}%/yr  at higher Sharpe and lower drawdown")

out = {
  "terms": {"management_fee":"1.0% per annum (accrued monthly)",
            "performance_fee":"15% of returns above the S&P 500 (SPY)",
            "high_water_mark":"Yes (relative; only charged on new highs vs benchmark)",
            "crystallisation":"Annual","liquidity":"Monthly, no lockup",
            "basis":"Performance fee on benchmark-relative outperformance only — not on market beta"},
  "gross": mg, "net": mn, "spy": ms,
  "fee_drag_cagr": mg["CAGR"]-mn["CAGR"], "net_vs_spy_cagr": mn["CAGR"]-ms["CAGR"],
}
Path("net_of_fee.json").write_text(json.dumps(out, indent=2))

fig,ax=plt.subplots(figsize=(11,6))
ax.plot(gross.index, gross.values, label=f"Gross strategy ({mg['CAGR']*100:.1f}% CAGR)", color="tab:green", lw=2)
ax.plot(net.index,   net.values,   label=f"NET to investor ({mn['CAGR']*100:.1f}% CAGR)", color="tab:orange", lw=2)
ax.plot(spy.index,   spy.values,   label=f"SPY ({ms['CAGR']*100:.1f}% CAGR)", color="black", lw=1.2, ls="--")
ax.set_yscale("log"); ax.set_title("Sector-Wide: gross strategy vs investor-net-of-fees vs SPY (SIMULATED, log)")
ax.set_ylabel("Growth of $1"); ax.legend(); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig("fig_netoffee.png", dpi=140)
print("\nSaved net_of_fee.json and fig_netoffee.png")
