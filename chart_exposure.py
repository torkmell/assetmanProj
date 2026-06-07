"""Macro-overlay exposure dial — equity exposure over time (30% floor to 100%), current data.
The gap between the line and 100% is the DEFENSIVE SLEEVE (Treasuries + gold), not cash.
Output: fig_exposure.png
"""
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
CACHE=Path("data_cache"); START="2002-01-31"
def me(idx): return pd.to_datetime(idx).to_period("M").to_timestamp("M")
vix=pd.read_csv(CACHE/"prices_vix_monthly.csv",index_col=0,parse_dates=True); vix.columns=["VIX"]; vix.index=me(vix.index)
mac=pd.read_csv(CACHE/"macro_proxies_monthly.csv",index_col=0,parse_dates=True); mac.index=me(mac.index)
def rz(s,w=60,mp=24): return (s-s.rolling(w,min_periods=mp).mean())/s.rolling(w,min_periods=mp).std()
idx=vix.index; c=pd.DataFrame(index=idx); c["vix"]=-rz(vix["VIX"])
cred=np.log(mac["IEF"]).reindex(idx).ffill()-np.log(mac["HYG"]).reindex(idx).ffill()
c["credit"]=-rz(cred.diff(12)); c["yield"]=-rz(mac["^TNX"].reindex(idx).ffill().diff(12))
spx=mac["^GSPC"].reindex(idx).ffill(); c["trend"]=rz(np.log(spx).diff(1).shift(1).rolling(11).sum())
score=c.mean(axis=1).clip(-2,2).shift(1); gross=np.clip(0.65+0.175*score,0.3,1.0).loc[START:]*100

NAVY="#0B1F3A"; GREEN="#2E7D5B"; RED="#B83A3A"; FILL="#C9CDD6"
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":12})
fig,ax=plt.subplots(figsize=(7.8,4.3))
ax.fill_between(gross.index,gross.values,30,color=FILL,alpha=0.55,zorder=1)
ax.plot(gross.index,gross.values,color=NAVY,lw=1.9,zorder=3)
ax.axhline(100,color=GREEN,lw=1.3,ls=(0,(2,2)),zorder=2)
ax.axhline(30,color=RED,lw=1.3,ls=(0,(2,2)),zorder=2)
ax.text(gross.index[6],101.5,"Fully invested (calm)",color=GREEN,fontsize=11,fontweight="bold",va="bottom")
ax.text(gross.index[6],31.5,"Floor 30% (max stress)",color=RED,fontsize=11,fontweight="bold",va="bottom")
# annotate that the gap to 100% is the defensive sleeve
ax.annotate("Gap to 100% = defensive sleeve\n(Treasuries + gold, not cash)",
            xy=(gross.index[int(len(gross)*0.46)],42),fontsize=9.5,color="#5A6F8C",ha="left",va="center",style="italic")
ax.set_ylabel("Equity exposure (%)",fontsize=12,color=NAVY)
ax.set_ylim(26,104); ax.set_yticks([30,50,70,90,100])
for sp in ["top","right"]: ax.spines[sp].set_visible(False)
ax.grid(axis="y",alpha=0.18)
fig.tight_layout(); fig.savefig("fig_exposure.png",dpi=160); plt.close(fig)
print(f"Saved fig_exposure.png  (exposure range {gross.min():.0f}%-{gross.max():.0f}%, avg {gross.mean():.0f}%)")
