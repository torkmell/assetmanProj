"""Regenerate fig_deck_stress.png from the corrected v1_flagship.json (dot-com clamped to its 2002 leg,
fund and SPY on the same dates). Matches the deck style; adds value labels and a SIMULATED tag.
"""
import json, matplotlib; matplotlib.use("Agg")
import numpy as np, matplotlib.pyplot as plt

V=json.load(open("v1_flagship.json")); st=V["stress"]
NAVY="#0B1F3A"; GOLD="#C9A96E"
# tidy display labels
disp={"Dot-com (2002 leg)":"Dot-com\n(2002)","GFC (07-09)":"GFC\n07-09","Euro (2011)":"Euro\n2011",
      "China (15-16)":"China\n15-16","Volmageddon (18)":"Vol-spike\n2018","COVID (2020)":"COVID\n2020","2022 bear":"2022\nbear"}
labels=[disp.get(s["window"],s["window"]) for s in st]
fund=[s["fund"]*100 for s in st]; spy=[s["spy"]*100 for s in st]

fig,ax=plt.subplots(figsize=(7.8,4.1)); x=np.arange(len(st)); ww=0.40
b1=ax.bar(x-ww/2,fund,ww,label="GSD2T",color=NAVY)
b2=ax.bar(x+ww/2,spy,ww,label="S&P 500",color=GOLD)
for bars in (b1,b2):
    for r in bars:
        h=r.get_height()
        ax.annotate(f"{h:.0f}",(r.get_x()+r.get_width()/2,h),ha="center",
                    va="top" if h<0 else "bottom",fontsize=7.5,color="#333",xytext=(0,-1 if h<0 else 1),textcoords="offset points")
ax.set_xticks(x); ax.set_xticklabels(labels,fontsize=8.5)
ax.axhline(0,color="#444",lw=.8); ax.set_ylabel("Total return %"); ax.legend(fontsize=10,loc="lower right")
ax.set_title("Crisis stress tests — total return through each window  (SIMULATED)",fontsize=11.5,color=NAVY)
ax.margins(y=0.12)
fig.tight_layout(); fig.savefig("fig_deck_stress.png",dpi=160); plt.close(fig)
print("Saved fig_deck_stress.png")
for s in st: print(f"  {s['window']:<18} fund {s['fund']*100:6.1f}%  spy {s['spy']*100:6.1f}%")
