# %% [markdown]
# # Persistence-filter sweep for the sector-rotation strategy
#
# Question: the regime flips month-to-month, driving 400-550% annual turnover.
# Does requiring a regime to PERSIST K months before we switch cut turnover AND
# improve risk-adjusted return (Sharpe)? We sweep K = 1 (no filter) .. 4.
#
# The filter is CAUSAL (walk-forward): the smoothed regime at month t uses only
# raw regime labels up to t, so it introduces no look-ahead — just a switch lag.

import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sector_rotation_backtest import (
    fetch_data, build_regimes, allocate_theory, allocate_empirical,
    backtest, metrics, START, IS_START, IS_END, OOS_START,
)

def apply_persistence(raw, k):
    """Switch to a new regime only after it has held for k consecutive months.
    Causal: walks forward using only past/current labels (no look-ahead). k=1 -> no filter."""
    active = raw.iloc[0]
    cand, run, out = None, 0, []
    for r in raw:
        if r == active:
            cand, run = None, 0
        else:
            if r == cand:
                run += 1
            else:
                cand, run = r, 1
            if run >= k:
                active, cand, run = r, None, 0
        out.append(active)
    return pd.Series(out, index=raw.index, name="regime")

# ---- data + raw regimes on the price grid ----
etf, spy, macro, rf, rf_label = fetch_data()
etf_ret = etf.pct_change()
spy_ret = spy.pct_change()
raw_reg = build_regimes(macro).reindex(etf_ret.index).ffill().dropna()
OOS_END = etf_ret.dropna(how="all").index.max()
print(f"rf source: {rf_label} | sample {raw_reg.index.min():%Y-%m}..{OOS_END:%Y-%m}")

def evaluate(W, label):
    ret, turn = backtest(W, etf_ret)
    full = metrics(ret.loc[START:OOS_END], rf, spy_ret)
    oos  = metrics(ret.loc[OOS_START:OOS_END], rf, spy_ret)
    return {
        "strategy": label,
        "Full CAGR": full["CAGR"], "Full Sharpe": full["Sharpe"], "Full MaxDD": full["MaxDD"],
        "Full Alpha": full["Alpha"], "OOS CAGR": oos["CAGR"], "OOS Sharpe": oos["Sharpe"],
        "Turnover": turn.loc[START:].mean() * 12,
        "n_switches": int((raw_reg != raw_reg.shift()).sum()),
    }

rows = []
switch_counts = {}
for k in [1, 2, 3, 4]:
    reg_k = apply_persistence(raw_reg, k)
    switch_counts[k] = int((reg_k != reg_k.shift()).sum())
    rB = evaluate(allocate_empirical(reg_k, etf_ret), f"B  K={k}")
    rA = evaluate(allocate_theory(reg_k, etf.columns), f"A  K={k}")
    rB["regime switches"] = switch_counts[k]; rA["regime switches"] = switch_counts[k]
    rows += [rB, rA]

df = pd.DataFrame(rows)
# SPY reference
spy_full = metrics(spy_ret.loc[START:OOS_END], rf, spy_ret)
spy_oos  = metrics(spy_ret.loc[OOS_START:OOS_END], rf, spy_ret)

def show(variant):
    d = df[df["strategy"].str.startswith(variant)].copy().set_index("strategy")
    out = pd.DataFrame({
        "regime switches": d["regime switches"].astype(int),
        "Turnover": (d["Turnover"]*100).map(lambda x: f"{x:5.0f}%"),
        "Full CAGR": (d["Full CAGR"]*100).map(lambda x: f"{x:5.1f}%"),
        "Full Sharpe": d["Full Sharpe"].map(lambda x: f"{x:4.2f}"),
        "Full MaxDD": (d["Full MaxDD"]*100).map(lambda x: f"{x:5.0f}%"),
        "Full Alpha": (d["Full Alpha"]*100).map(lambda x: f"{x:+4.1f}%"),
        "OOS CAGR": (d["OOS CAGR"]*100).map(lambda x: f"{x:5.1f}%"),
        "OOS Sharpe": d["OOS Sharpe"].map(lambda x: f"{x:4.2f}"),
    })
    return out

print("\n" + "="*100)
print("VARIANT B (empirical, walk-forward) — persistence sweep   [K=1 is the original, no filter]")
print("-"*100)
print(show("B").to_string())
print(f"\nSPY reference:  Full CAGR { spy_full['CAGR']*100:.1f}%  Full Sharpe {spy_full['Sharpe']:.2f}"
      f"  OOS CAGR {spy_oos['CAGR']*100:.1f}%  OOS Sharpe {spy_oos['Sharpe']:.2f}")

print("\n" + "="*100)
print("VARIANT A (theory) — persistence sweep")
print("-"*100)
print(show("A").to_string())

# ---- plot: Sharpe & turnover vs K (Variant B) ----
b = df[df["strategy"].str.startswith("B")].copy()
ks = [1,2,3,4]
fig, ax1 = plt.subplots(figsize=(8,5))
ax1.plot(ks, b["Full Sharpe"].values, "o-", color="tab:orange", label="Full Sharpe")
ax1.plot(ks, b["OOS Sharpe"].values, "s--", color="tab:red", label="OOS Sharpe")
ax1.axhline(spy_full["Sharpe"], color="tab:blue", ls=":", label="SPY Full Sharpe")
ax1.set_xlabel("Persistence K (months a regime must hold before switching)")
ax1.set_ylabel("Sharpe"); ax1.set_xticks(ks); ax1.legend(loc="upper left"); ax1.grid(alpha=0.3)
ax2 = ax1.twinx()
ax2.bar(ks, b["Turnover"].values*100, alpha=0.15, color="tab:gray")
ax2.set_ylabel("Annualised turnover (%)")
ax1.set_title("Variant B: Sharpe vs turnover across persistence filter K")
fig.tight_layout(); fig.savefig("fig_sr_persistence.png", dpi=140)
print("\nSaved fig_sr_persistence.png")
print(f"Regime switches by K: {switch_counts}")
