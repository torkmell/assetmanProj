"""Capacity-derivation graphic (slide-ready) — shows the quantitative basis step by step,
so the capacity claim is a derivation, not an assertion. Output: fig_capacity_calc.png
"""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

NAVY="#0B1F3A"; GOLD="#C9A96E"; GREY="#5A6F8C"; WHITE="#FFFFFF"; LGOLD="#8a6d10"
def esc(s): return s.replace("$","\\$")   # literal dollar, not mathtext
plt.rcParams.update({"font.family":"DejaVu Sans"})
fig,ax=plt.subplots(figsize=(5.8,7.2)); ax.set_xlim(0,10); ax.set_ylim(0,14.4); ax.axis("off")

ax.text(5,13.9,"CAPACITY — THE CALCULATION",ha="center",va="center",fontsize=13.5,color=NAVY,fontweight="bold")
ax.text(5,13.35,"measured from data, not assumed",ha="center",va="center",fontsize=9.5,color=GREY,style="italic")

# (box_top, label, value, sub, facecolor, value_color, height)
boxes=[
 (12.3,"ADV PER NAME (measured)","$150M – $300M",None,NAVY,WHITE,1.5),
 (9.5 ,"TRADEABLE PER NAME","$15M – $30M",None,NAVY,WHITE,1.5),
 (6.7 ,"SOFT CAPACITY","$1.7B – $3.3B",None,NAVY,WHITE,1.5),
 (3.8 ,"HEADROOM vs the $100M raise","17 – 33×","only ~3–6% of capacity used",GOLD,NAVY,1.9),
]
ops=[("× 5% of ADV × 2-day window",10.15),("× ~111 holdings",7.35),("÷ $100M raise",4.50)]
for ty,label,value,sub,fc,vc,h in boxes:
    ax.add_patch(FancyBboxPatch((1.0,ty-h),8.0,h,boxstyle="round,pad=0.02,rounding_size=0.18",
                 facecolor=fc,edgecolor=GOLD,linewidth=1.7,zorder=2))
    lc=GOLD if fc==NAVY else NAVY
    ax.text(5,ty-0.36,label,ha="center",va="center",fontsize=9.5,color=lc,fontweight="bold",zorder=3)
    vy=ty-0.95 if sub is None else ty-1.0
    ax.text(5,vy,esc(value),ha="center",va="center",fontsize=21,color=vc,fontweight="bold",family="serif",zorder=3)
    if sub: ax.text(5,ty-1.62,sub,ha="center",va="center",fontsize=9,color=NAVY,fontweight="bold",zorder=3)
# operation connectors in the gaps
for txt,y in ops:
    ax.add_patch(FancyArrowPatch((2.6,y+0.42),(2.6,y-0.42),arrowstyle="-|>",mutation_scale=15,color=GREY,lw=1.7,zorder=1))
    ax.text(3.0,y,esc(txt),ha="left",va="center",fontsize=9.5,color=LGOLD,style="italic",zorder=4)
ax.text(5,0.95,esc("The full $100M deploys in daily-liquid large-caps —"),ha="center",va="center",fontsize=9.5,color=NAVY,fontweight="bold")
ax.text(5,0.5,"we never approach our own market impact.",ha="center",va="center",fontsize=9.5,color=NAVY,fontweight="bold")
fig.tight_layout(); fig.savefig("fig_capacity_calc.png",dpi=170,bbox_inches="tight"); plt.close(fig)
print("Saved fig_capacity_calc.png")
