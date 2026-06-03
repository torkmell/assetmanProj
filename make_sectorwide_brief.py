"""High-level Word brief for the Sector-Wide (diversified) strategy — the new flagship."""
import json
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

F = json.load(open("sectorwide_full.json"))
NF = json.load(open("net_of_fee.json"))
S = F["summary"]["Fund (full window)"]; SPY = F["summary"]["SPY"]; FR = F["factor_regression"]
CAP = F["capacity"]; SENS = F["sensitivity"]; HL = F["holdings_latest"]; SEC = F["sector_breakdown"]
IS = F["summary"]["Fund IS (2002-2015)"]; OOS = F["summary"]["Fund OOS (2016-2026)"]

doc = Document()
doc.styles["Normal"].font.name = "Calibri"; doc.styles["Normal"].font.size = Pt(11)
def body(t, bold=False, italic=False, size=11):
    p = doc.add_paragraph(); r = p.add_run(t); r.bold=bold; r.italic=italic; r.font.size=Pt(size); return p
def bullet(t): doc.add_paragraph(t, style="List Bullet")
def table(headers, rows, style="Light Grid Accent 1"):
    t = doc.add_table(rows=1, cols=len(headers)); t.style = style
    for i,h in enumerate(headers):
        c=t.rows[0].cells[i]; c.text=""; run=c.paragraphs[0].add_run(h); run.bold=True
    for row in rows:
        cs=t.add_row().cells
        for i,v in enumerate(row): cs[i].text=str(v)
    return t

doc.add_heading("GSD2T — Sector-Wide Strategy (Diversified Macro-Overlay)", level=0)
sub=doc.add_paragraph(); r=sub.add_run("Team brief · ESADE Asset Management · The diversified flagship")
r.italic=True; r.font.size=Pt(11); r.font.color.rgb=RGBColor(0x55,0x55,0x55)
n=doc.add_paragraph(); rn=n.add_run("All performance is SIMULATED (2002–2026), net of 15bps trading costs, GROSS of fund fees. The fund is fictional.")
rn.italic=True; rn.font.size=Pt(9); rn.font.color.rgb=RGBColor(0x88,0x88,0x88)

doc.add_heading("1. The strategy in one paragraph", 1)
body("We buy the strongest-performing stocks across the WHOLE S&P 500 (all 11 sectors), then "
     "use a simple macroeconomic “risk dial” to decide how much to hold in stocks versus cash. "
     "It is the same engine as our tech strategy, applied to a diversified universe. The result: "
     "broad-market beating, risk-adjusted returns from a portfolio that is genuinely diversified "
     "— not a sector bet — with strong downside protection in every major crisis.")

doc.add_heading("2. How it works — two layers", 1)
bullet("Layer 1 – Stock selection: pick the strongest stocks by 12-month price momentum, across all sectors.")
bullet("Layer 2 – Macro overlay: a 4-factor “risk dial” scales total exposure between 30% and 100% (rest in cash).")
body("Position per stock = (equal weight within the chosen stocks) × (macro exposure level).", italic=True)

doc.add_heading("3. Layer 1 — Stock selection (momentum factor)", 1)
table(["Item","Detail"], [
    ["Universe", f"Full S&P 500 — all 11 sectors (~500 stocks)"],
    ["Factor", "12-minus-1 month price momentum"],
    ["How computed", "Total return over the last 12 months, excluding the most recent month"],
    ["Ranking", "Each stock z-scored against the universe each month"],
    ["Selection", f"Hold the top quartile — currently {HL['n_holdings']} stocks across {HL['n_sectors']} sectors"],
    ["Weighting", "Equal weight within the selected stocks"],
])

doc.add_heading("4. Layer 2 — The macro overlay (4 factors)", 1)
body("Four economically-motivated signals, each z-scored over a rolling 5-year window, averaged "
     "into one composite “risk score”. Three are stress signals (turn risk down); one is trend (turn risk up).")
table(["Macro factor","Captures","Data","Direction"], [
    ["VIX","Equity fear / volatility","CBOE VIX","High → de-risk"],
    ["Credit","Credit stress","IEF vs HYG ETFs","Widening → de-risk"],
    ["Yield","Rate tightening","10-year Treasury yield","Rising → de-risk"],
    ["Trend","Market momentum","S&P 500 index","Up → risk-on"],
])
table(["Risk score","Stock exposure","Cash"], [["+2 calm","100%","0%"],["0 neutral","65%","35%"],["−2 stress","30%","70%"]])

doc.add_heading("5. Weighting", 1)
body("Weight per stock = (1 / number held) × macro exposure.", bold=True)
bullet(f"Currently {HL['n_holdings']} stocks held; equal-weight → each ~{100/HL['n_holdings']:.1f}% at full exposure (built-in ~1% single-name cap).")
bullet("No leverage, no shorting; rebalanced monthly; 15 bps round-trip trading cost.")
body("Current sector spread of the book (diversified, not a tech bet):", italic=True)
table(["Sector","# stocks"], [[k, v] for k,v in list(SEC.items())])

doc.add_heading("6. Data sources", 1)
table(["Data","Source","Used for"], [
    ["Stock prices (monthly, adjusted)","yfinance","Momentum, returns"],
    ["VIX, IEF, HYG, 10Y yield, S&P 500","yfinance","Macro overlay"],
    ["Fama-French 5 + Momentum, risk-free","Ken French library","Risk-free & alpha test"],
])

doc.add_heading("7. Results (simulated, 2002–2026, net of trading costs)", 1)
table(["Metric","Sector-Wide","S&P 500 (SPY)"], [
    ["CAGR", f"{S['CAGR']*100:.1f}%", f"{SPY['CAGR']*100:.1f}%"],
    ["Sharpe ratio", f"{S['Sharpe']:.2f}", f"{SPY['Sharpe']:.2f}"],
    ["Max drawdown", f"{S['MaxDD']*100:.0f}%", f"{SPY['MaxDD']*100:.0f}%"],
    ["Alpha vs FF5+Momentum", f"+{FR['alpha_annualized']*100:.1f}% (t={FR['alpha_tstat']:.1f})", "—"],
    ["Capacity vs $100M raise", f"${CAP['soft_cap_low']/1e9:.0f}-{CAP['soft_cap_high']/1e9:.0f}B "
        f"({CAP['headroom_low']:.0f}-{CAP['headroom_high']:.0f}x headroom)", "—"],
])
body("It generalises: the same engine gives a ~1.0 Sharpe with significant alpha on the tech universe "
     "(0.93) and even the Dow Jones 30 (0.99) — strong evidence it is a real effect, not a tech bet.", italic=True)
body(f"On the $100M commitment we are raising, the strategy runs at roughly "
     f"{CAP['pct_of_capacity_at_raise']*100:.0f}% of capacity — {CAP['headroom_low']:.0f}-{CAP['headroom_high']:.0f}x headroom. "
     "We can deploy the full $100M immediately in daily-liquid large-caps and never need to soft-close early.", italic=True)

doc.add_heading("8. Fund terms (aligned with our liquidity)", 1)
T = NF["terms"]
table(["Term","What we charge"], [
    ["Management fee", T["management_fee"]],
    ["Performance fee", T["performance_fee"]],
    ["High-water mark", T["high_water_mark"]],
    ["Crystallisation", T["crystallisation"]],
    ["Liquidity", T["liquidity"]],
])
body("Why not 2/20: the strategy is daily-liquid and partly factor-replicable, so we charge below "
     "hedge-fund terms and the performance fee applies ONLY to returns above the S&P 500 — we do not "
     "charge an alpha fee on market beta you can buy for 5 bps, and the high-water mark means we only "
     "get paid on new highs versus the benchmark.", italic=True)

body("What the investor actually receives (simulated, net of all fees):", bold=True)
G, N2, SP = NF["gross"], NF["net"], NF["spy"]
table(["", "CAGR", "Sharpe", "Max drawdown"], [
    ["Gross strategy",   f"{G['CAGR']*100:.1f}%",  f"{G['Sharpe']:.2f}",  f"{G['MaxDD']*100:.0f}%"],
    ["NET to investor",  f"{N2['CAGR']*100:.1f}%", f"{N2['Sharpe']:.2f}", f"{N2['MaxDD']*100:.0f}%"],
    ["S&P 500 (SPY)",    f"{SP['CAGR']*100:.1f}%", f"{SP['Sharpe']:.2f}", f"{SP['MaxDD']*100:.0f}%"],
])
body(f"After all fees the client still beats the S&P 500 ({N2['CAGR']*100:.1f}% vs {SP['CAGR']*100:.1f}%), "
     f"but the real value is risk: Sharpe {N2['Sharpe']:.2f} vs {SP['Sharpe']:.2f} and a {N2['MaxDD']*100:.0f}% "
     f"drawdown versus {SP['MaxDD']*100:.0f}%. We are paid for risk-adjusted outperformance, not raw return.",
     italic=True)

doc.add_heading("9. Honest notes (for the team)", 1)
bullet("Returns are NET of trading costs but GROSS of fund management/performance fees and taxes; investor net is lower once we set fees.")
bullet(f"In-sample Sharpe {IS['Sharpe']:.2f}, out-of-sample {OOS['Sharpe']:.2f}; parameter-robust ({SENS['min_sharpe']:.2f}–{SENS['max_sharpe']:.2f} across 15 settings).")
bullet("2019–2024 was a mega-cap-growth 'factor drought': out-of-sample we preserved capital and kept pace at lower risk, but the factor alpha compressed industry-wide. We disclose this.")
bullet("Universe uses current S&P 500 constituents (survivorship bias disclosed, not yet corrected).")

d=doc.add_paragraph(); rd=d.add_run("Disclaimer: Fictional pitch for the ESADE Asset Management course. Not investment advice. "
    "All performance is simulated; past performance does not indicate future results.")
rd.italic=True; rd.font.size=Pt(8); rd.font.color.rgb=RGBColor(0x88,0x88,0x88)

doc.save("SectorWide_Strategy_Overview.docx")
print("Saved SectorWide_Strategy_Overview.docx")
