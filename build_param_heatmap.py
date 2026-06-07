"""Parameter-stability heatmap generated DIRECTLY from the committed grid in
sectorwide_full.json (with macro overlay), so the figure, the bullet text (0.93-1.00),
and the code all agree. 5 lookbacks x 3 diversified quantiles = 15 settings.
Output: fig_param_heatmap.png
"""
import json
import numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

S=json.load(open("sectorwide_full.json"))["sensitivity"]
lbs=S["lookbacks"]; qs=S["quantiles"]; grid=np.array(S["sharpe_grid"])  # rows=lookback, cols=quantile
lo,hi=grid.min(),grid.max()
NAVY="#0B1F3A"; GOLD="#C9A96E"
fig,ax=plt.subplots(figsize=(5.3,3.4))
im=ax.imshow(grid,cmap="YlGnBu",aspect="auto",vmin=0.90,vmax=1.02)
ax.set_xticks(range(len(qs))); ax.set_xticklabels([f"Top {int(q*100)}%" for q in qs],fontsize=10)
ax.set_yticks(range(len(lbs))); ax.set_yticklabels([f"{lb}-1" for lb in lbs],fontsize=10)
ax.set_xlabel("Selection quantile",fontsize=10); ax.set_ylabel("Momentum lookback (months)",fontsize=10)
ax.set_title(f"Core-momentum Sharpe across {grid.size} settings — a plateau",fontsize=11.5,color=NAVY,fontweight="bold",pad=8)
for i in range(len(lbs)):
    for j in range(len(qs)):
        v=grid[i,j]; ax.text(j,i,f"{v:.2f}",ha="center",va="center",fontsize=11,
                             color="white" if v>0.985 else NAVY,fontweight="bold")
# highlight the flagship cell: 12-1, Top 25%
fi=lbs.index(12); fj=qs.index(0.25)
ax.add_patch(Rectangle((fj-0.5,fi-0.5),1,1,fill=False,edgecolor=GOLD,lw=3))
cb=fig.colorbar(im,ax=ax,fraction=0.046,pad=0.04); cb.ax.tick_params(labelsize=8)
fig.tight_layout(); fig.savefig("fig_param_heatmap.png",dpi=180,bbox_inches="tight"); plt.close(fig)
print(f"Saved fig_param_heatmap.png  | grid {grid.shape} range {lo:.2f}-{hi:.2f}  flagship cell(12-1,T25)={grid[fi,fj]:.2f}")
