"""Compute the strategy's CURRENT positioning and indicator readings (latest available month),
so the team can answer 'what is your book doing right now?' with real numbers.
Output: current_state.json + console summary.
"""
import json, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
CACHE=Path("data_cache")
def me(idx): return pd.to_datetime(idx).to_period("M").to_timestamp("M")
vix=pd.read_csv(CACHE/"prices_vix_monthly.csv",index_col=0,parse_dates=True); vix.columns=["VIX"]; vix.index=me(vix.index)
mac=pd.read_csv(CACHE/"macro_proxies_monthly.csv",index_col=0,parse_dates=True); mac.index=me(mac.index)
def rz(s,w=60,mp=24): return (s-s.rolling(w,min_periods=mp).mean())/s.rolling(w,min_periods=mp).std()
idx=vix.index; c=pd.DataFrame(index=idx)
c["vix"]=-rz(vix["VIX"])
cred=np.log(mac["IEF"]).reindex(idx).ffill()-np.log(mac["HYG"]).reindex(idx).ffill()
c["credit"]=-rz(cred.diff(12)); c["yield"]=-rz(mac["^TNX"].reindex(idx).ffill().diff(12))
spx=mac["^GSPC"].reindex(idx).ffill(); c["trend"]=rz(np.log(spx).diff(1).shift(1).rolling(11).sum())
score=c.mean(axis=1).clip(-2,2).shift(1)
gross=np.clip(0.65+0.175*score,0.3,1.0)

last=gross.dropna().index[-1]
g=float(gross.loc[last]); sc=float(score.loc[last]); comps=c.shift(1).loc[last]
raw_vix=float(vix["VIX"].ffill().loc[last]); raw_tnx=float(mac["^TNX"].ffill().loc[last])

def lean(z):  # z-scored component -> risk-on/off reading
    if z>=0.5: return "clearly risk-ON"
    if z>=0.1: return "mildly risk-on"
    if z>-0.1: return "neutral"
    if z>-0.5: return "mildly risk-off"
    return "clearly risk-OFF"

print("="*70)
print(f"CURRENT POSITIONING — as of {last:%B %Y} (latest available data)")
print("="*70)
print(f"  Composite regime score : {sc:+.2f}  (range -2 calm-stress to +2)")
print(f"  -> GROSS EQUITY EXPOSURE: {g*100:.0f}%   (defensive sleeve: {(1-g)*100:.0f}%)")
print(f"\n  Indicator readings (z-scores; + = risk-on, - = risk-off):")
labels={"vix":"VIX / equity fear","credit":"Credit stress (IEF-HYG)","yield":"Rate direction (10Y)","trend":"Market trend (S&P 500)"}
for k in ["vix","credit","yield","trend"]:
    z=float(comps[k]); print(f"    {labels[k]:28} {z:+.2f}   {lean(z)}")
print(f"\n  Raw context: VIX ~{raw_vix:.0f}, 10Y yield ~{raw_tnx:.1f}%")
print(f"\n  Recent exposure path (last 8 months):")
for d,v in gross.dropna().tail(8).items(): print(f"    {d:%Y-%m}: {v*100:.0f}% equities")

out={"as_of":last.strftime("%Y-%m"),"gross_exposure":g,"defensive_sleeve":1-g,"composite_score":sc,
     "components":{k:float(comps[k]) for k in ["vix","credit","yield","trend"]},
     "component_reading":{k:lean(float(comps[k])) for k in ["vix","credit","yield","trend"]},
     "raw":{"vix":raw_vix,"tnx":raw_tnx},
     "recent_path":[[d.strftime("%Y-%m"),float(v)] for d,v in gross.dropna().tail(12).items()]}
Path("current_state.json").write_text(json.dumps(out,indent=2))
print("\nSaved current_state.json")
