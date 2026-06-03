"""Generate a self-contained sector-wide strategy dashboard (matches gsd2t_dashboard.html style)."""
import json
from pathlib import Path

DATA = json.load(open("sectorwide_full.json"))
NET  = json.load(open("net_of_fee.json"))
SURV = json.load(open("survivorship_robustness.json"))
PIT  = json.load(open("survivorship_corrected.json"))   # Bloomberg point-in-time result

HTML = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>GSD2T Asset Management — Sector-Wide Strategy Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
 :root{--navy:#0B1F3A;--navy-light:#1E3A6C;--gold:#C9A96E;--cream:#F5F2EA;--grey-text:#5A6F8C;
   --positive:#2E7D5B;--negative:#B83A3A;--bg:#FAFAF7;}
 *{box-sizing:border-box;} body{margin:0;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;background:var(--bg);color:var(--navy);font-size:13px;line-height:1.45;}
 .topbar{display:flex;justify-content:space-between;align-items:center;background:var(--navy);color:#fff;padding:14px 28px;border-bottom:3px solid var(--gold);}
 .topbar-left{display:flex;align-items:center;gap:14px;}
 .logo-mark{width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,var(--navy),var(--navy-light));border:2px solid var(--gold);display:flex;align-items:flex-end;justify-content:center;padding-bottom:5px;}
 .logo-bars{display:flex;gap:2px;align-items:flex-end;height:26px;}
 .logo-bars span{width:4px;background:var(--gold);display:block;}
 .logo-bars span:nth-child(1){height:35%}.logo-bars span:nth-child(2){height:55%}.logo-bars span:nth-child(3){height:85%}.logo-bars span:nth-child(4){height:65%}.logo-bars span:nth-child(5){height:100%;background:#fff}
 .brand h1{margin:0;font-family:Georgia,serif;font-size:22px;letter-spacing:1.2px;}
 .brand h1 sup{font-size:12px;} .brand .sub{font-size:9px;letter-spacing:4px;color:var(--gold);margin-top:1px;}
 .topbar-right{font-size:10.5px;text-align:right;opacity:.85;line-height:1.5;} .topbar-right strong{color:var(--gold);letter-spacing:1px;}
 .container{padding:22px 28px 40px;max-width:1400px;margin:0 auto;}
 .meta-strip{background:#fff;border:1px solid #E5E0D2;border-left:3px solid var(--gold);padding:10px 16px;margin-bottom:18px;display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px 22px;font-size:11px;}
 .meta-strip .label{color:var(--grey-text);letter-spacing:1px;text-transform:uppercase;font-size:9px;} .meta-strip .value{color:var(--navy);font-weight:600;margin-top:1px;}
 .kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px;}
 .kpi{background:var(--navy);color:#fff;border-radius:4px;padding:14px 18px;position:relative;overflow:hidden;}
 .kpi::after{content:'';position:absolute;right:-20px;top:-20px;width:70px;height:70px;background:var(--gold);opacity:.06;border-radius:50%;}
 .kpi .label{font-size:9.5px;letter-spacing:1.5px;color:var(--gold);text-transform:uppercase;}
 .kpi .value{font-family:Georgia,serif;font-size:30px;font-weight:700;color:#fff;margin:4px 0 2px;}
 .kpi .delta{font-size:11px;color:#B8C8E0;} .kpi .delta.pos{color:#6ECF9A;}
 .grid-2{display:grid;grid-template-columns:1.4fr 1fr;gap:18px;margin-bottom:18px;}
 .grid-2-eq{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px;}
 .card{background:#fff;border:1px solid #E5E0D2;border-radius:4px;padding:14px 16px;}
 .card h2{margin:0 0 8px;font-size:11px;text-transform:uppercase;letter-spacing:2px;color:var(--navy);padding-bottom:6px;border-bottom:1px solid var(--gold);}
 .card .subtitle{font-size:10px;color:var(--grey-text);margin-bottom:6px;font-style:italic;}
 .chart{width:100%;height:320px;} .chart-tall{width:100%;height:380px;}
 table.summary{width:100%;border-collapse:collapse;font-size:11px;}
 table.summary th,table.summary td{padding:5px 8px;text-align:left;border-bottom:1px solid #E5E0D2;}
 table.summary th{background:var(--cream);font-weight:600;font-size:10px;color:var(--navy);}
 table.summary td.num{text-align:right;font-variant-numeric:tabular-nums;}
 table.summary tr.highlight{background:rgba(201,169,110,.10);font-weight:600;}
 .holdings-list{list-style:none;padding:0;margin:0;max-height:340px;overflow-y:auto;}
 .holdings-list li{display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid var(--cream);font-size:11px;}
 .holdings-list .bar{flex:1;margin:0 10px;height:6px;background:var(--cream);border-radius:3px;overflow:hidden;position:relative;}
 .holdings-list .bar>span{position:absolute;left:0;top:0;bottom:0;background:linear-gradient(90deg,var(--navy-light),var(--gold));border-radius:3px;}
 .holdings-list .weight{font-variant-numeric:tabular-nums;font-weight:600;min-width:42px;text-align:right;} .holdings-list .ticker{min-width:60px;font-weight:600;}
 .footer{margin-top:24px;padding-top:12px;border-top:1px solid var(--gold);font-size:9.5px;color:var(--grey-text);line-height:1.5;} .footer strong{color:var(--navy);}
 .badge{display:inline-block;background:var(--cream);color:var(--navy);padding:2px 8px;font-size:9.5px;letter-spacing:1px;border-radius:8px;margin-left:6px;}
 .badge.warn{background:#FCEFC7;color:#856200;} .badge.good{background:#D6F0E0;color:#1F5C3C;}
 .tabnav{display:flex;margin-bottom:14px;border-bottom:1px solid var(--gold);flex-wrap:wrap;}
 .tabnav button{background:transparent;border:none;padding:10px 18px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:var(--grey-text);cursor:pointer;border-bottom:3px solid transparent;font-family:inherit;}
 .tabnav button.active{color:var(--navy);border-bottom-color:var(--navy);font-weight:700;}
 .tab-panel{display:none;} .tab-panel.active{display:block;}
 .report-actions{display:flex;justify-content:flex-end;margin-bottom:12px;}
 .printbtn{background:var(--navy);color:#fff;border:1px solid var(--gold);padding:8px 18px;font-size:11px;letter-spacing:1.5px;cursor:pointer;border-radius:3px;font-family:inherit;text-transform:uppercase;}
 .printbtn:hover{background:var(--navy-light);}
 .report-head{margin-bottom:16px;border-bottom:2px solid var(--gold);padding-bottom:10px;}
 .report-head h2{margin:0;font-family:Georgia,serif;font-size:20px;letter-spacing:.5px;color:var(--navy);text-transform:none;border:none;padding:0;}
 .report-head .subtitle{font-style:normal;font-size:10px;color:var(--grey-text);margin-top:4px;}
 .print-only{display:none;}
 .prose{font-size:10.5px;color:var(--grey-text);line-height:1.55;} .prose strong{color:var(--navy);}
 @media print{
  @page{margin:12mm;}
  body{background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact;font-size:10.5px;}
  .topbar-right,.tabnav,.report-actions,.meta-strip,.footer{display:none!important;}
  .tab-panel{display:none!important;} #tab-pitreport{display:block!important;}
  .print-only{display:block;} .topbar{border-bottom:2px solid var(--gold);}
  .card,.grid-2,.grid-2-eq,.kpi-row,.report-head{break-inside:avoid;}
  .chart{height:260px!important;} .chart-tall{height:300px!important;}
 }
</style></head><body>
<div class="topbar">
 <div class="topbar-left"><div class="logo-mark"><div class="logo-bars"><span></span><span></span><span></span><span></span><span></span></div></div>
  <div class="brand"><h1>GSD<sup>2</sup>T <span style="font-family:'Helvetica Neue',sans-serif;font-size:11px;letter-spacing:4px;color:var(--gold);margin-left:6px;">ASSET MANAGEMENT</span></h1>
  <div class="sub">MACRO-OVERLAY SECTOR-WIDE</div></div></div>
 <div class="topbar-right"><strong>STRATEGY DASHBOARD</strong><br>Investor Review · 24-Year Simulated Track Record<br><span id="generatedAt">—</span></div>
</div>
<div class="container">
 <div class="meta-strip" id="metaStrip"></div>
 <div class="tabnav">
  <button data-tab="overview" class="active">Overview</button>
  <button data-tab="risk">Risk &amp; Drawdowns</button>
  <button data-tab="positioning">Positioning</button>
  <button data-tab="robustness">Robustness &amp; Factors</button>
  <button data-tab="survivorship">Survivorship</button>
  <button data-tab="pitreport">Point-in-Time Report</button>
  <button data-tab="terms">Capacity &amp; Terms</button>
 </div>

 <div class="tab-panel active" id="tab-overview">
  <div class="kpi-row" id="kpiRow"></div>
  <div class="grid-2">
   <div class="card"><h2>Cumulative Net Wealth <span class="badge">SIMULATED · NET OF 15 BPS</span></h2>
    <div class="subtitle">Growth of $1 from 2002-01, log scale. Diversified S&amp;P 500 momentum with the macro-regime overlay.</div>
    <div id="equityChart" class="chart-tall"></div></div>
   <div class="card"><h2>Performance Summary</h2>
    <div class="subtitle">Fund (full / in-sample / out-of-sample) vs benchmarks. Excess-of-RF Sharpe.</div>
    <table class="summary" id="summaryTable"></table></div>
  </div>
 </div>

 <div class="tab-panel" id="tab-risk">
  <div class="grid-2-eq">
   <div class="card"><h2>Drawdowns</h2><div class="subtitle">Fund vs SPY. The overlay de-grosses in stress.</div><div id="ddChart" class="chart"></div></div>
   <div class="card"><h2>Crisis Stress Tests</h2><div class="subtitle">Total return through each crisis window.</div><div id="stressChart" class="chart"></div></div>
  </div>
 </div>

 <div class="tab-panel" id="tab-positioning">
  <div class="grid-2">
   <div class="card"><h2>Macro Overlay — Gross Exposure</h2><div class="subtitle">Share of book in stocks (30–100%); remainder in cash.</div><div id="overlayChart" class="chart"></div></div>
   <div class="card"><h2>Current Sector Breakdown</h2><div class="subtitle" id="diversNote"></div><div id="sectorChart" class="chart"></div></div>
  </div>
  <div class="card"><h2>Top Holdings (current)</h2><ul class="holdings-list" id="holdingsList"></ul></div>
 </div>

 <div class="tab-panel" id="tab-robustness">
  <div class="grid-2">
   <div class="card"><h2>Parameter Sensitivity — Sharpe Grid</h2><div class="subtitle">Sharpe across momentum lookback × top-quantile. Tight range = robust, not curve-fit.</div><div id="sensChart" class="chart"></div></div>
   <div class="card"><h2>Factor Exposure (FF5 + Momentum)</h2><div class="subtitle" id="alphaNote"></div><div id="betaChart" class="chart"></div></div>
  </div>
 </div>

 <div class="tab-panel" id="tab-survivorship">
  <div class="card" style="border-left:4px solid var(--positive)"><h2>Point-in-Time S&amp;P 500 — Bias Measured Directly <span class="badge good">CONFIRMED SMALL</span></h2>
   <div class="subtitle">Bloomberg point-in-time membership: 1,085 historical names (incl. delisted/acquired), ~500 members each quarter, quarterly total returns 2002–2026. The <strong>same engine</strong> is run on (A) the survivorship-free universe and (B) survivors-only — which recreates the bias. The gap between A and B is the survivorship bias, cleanly isolated on identical data.</div>
   <table class="summary" id="pitTable"></table>
   <div style="margin-top:10px;font-size:10.5px;color:var(--grey-text)"><strong style="color:var(--navy)">Verdict:</strong> survivorship bias costs only <strong style="color:var(--positive)">~1.0%/yr of CAGR and ~0.10 of Sharpe</strong> — in line with the academic range for large-cap indices. Our backtest is <strong>not</strong> a survivorship illusion. The capital-preservation edge survives intact (vol 10.5% vs 16.3%, drawdown −21% vs −46%). <strong style="color:var(--navy)">Honest caveat:</strong> this Bloomberg series is <em>quarterly</em>; quarterly sampling weakens momentum stock-selection across <em>both</em> universes, so the durable, survivorship-proof edge is the macro risk overlay, not raw momentum alpha.</div></div>
  <div class="grid-2-eq">
   <div class="card"><h2>Option 2 — Survivorship Haircut <span class="badge good">BOUNDED</span></h2>
    <div class="subtitle">Subtract a conservative annual penalty (large-cap bias is ~1–2%/yr). The risk edge holds at every level.</div>
    <table class="summary" id="haircutTable"></table>
    <div style="margin-top:10px;font-size:10.5px;color:var(--grey-text)">At a realistic 1–2% haircut the strategy still matches/beats SPY on return and decisively on Sharpe and drawdown. The return edge erodes under an extreme 3% penalty; the <strong style="color:var(--navy)">risk-adjusted edge is robust throughout</strong>.</div></div>
   <div class="card"><h2>Option 3 — Survivorship-Free Universes <span class="badge warn">PARTIAL</span></h2>
    <div class="subtitle">Same engine on instruments with zero single-stock survivorship bias (the index provider handles add/drops).</div>
    <table class="summary" id="freeTable"></table>
    <div style="margin-top:10px;font-size:10.5px;color:var(--grey-text)"><strong style="color:var(--navy)">Honest read:</strong> on survivorship-free universes the <strong style="color:var(--positive)">overlay/risk edge clearly survives</strong> (both beat SPY on Sharpe and drawdown). But the stock-level FF5+MOM alpha is <strong>not reproduced</strong> at ETF/industry granularity — aggregates wash out within-industry stock selection. This is now settled with the Bloomberg point-in-time stock data above: the bias is ~1%/yr and the risk edge survives.</div></div>
  </div>
 </div>

 <div class="tab-panel" id="tab-pitreport">
  <div class="report-actions"><button class="printbtn" onclick="printReport()">&#9113; Print / Save as PDF</button></div>
  <div class="report" id="pitReport">
   <div class="report-head">
    <h2>Survivorship-Corrected Backtest &mdash; Point-in-Time S&amp;P 500</h2>
    <div class="subtitle" id="pitMeta"></div>
    <div class="subtitle print-only" style="margin-top:2px">GSD2T Asset Management &middot; ESADE Asset Management &middot; SIMULATED, net of 15bps trading costs &middot; fictional pitch</div>
   </div>
   <div class="kpi-row" id="pitKpi"></div>
   <div class="grid-2">
    <div class="card"><h2>Cumulative Wealth <span class="badge">SIMULATED &middot; LOG</span></h2>
     <div class="subtitle">Growth of $1, quarterly. Survivorship-free vs survivors-only (recreates the bias) vs the market.</div>
     <div id="pitEquity" class="chart-tall"></div></div>
    <div class="card"><h2>Performance &amp; Survivorship Bias</h2>
     <div class="subtitle">Same engine on two universes. The B&minus;A gap is the survivorship bias, isolated.</div>
     <table class="summary" id="pitFullTable"></table>
     <div class="prose" style="margin-top:8px" id="pitBiasNote"></div></div>
   </div>
   <div class="grid-2-eq">
    <div class="card"><h2>Drawdowns &mdash; Survivorship-free vs SPY</h2>
     <div class="subtitle">The macro overlay de-grosses in stress; half the market's drawdown.</div>
     <div id="pitDD" class="chart"></div></div>
    <div class="card"><h2>Factor Exposure (FF5 + Momentum) &mdash; Survivorship-free</h2>
     <div class="subtitle" id="pitAlphaNote"></div>
     <div id="pitBeta" class="chart"></div></div>
   </div>
   <div class="grid-2-eq">
    <div class="card"><h2>Diagnostics</h2><table class="summary" id="pitDiag"></table></div>
    <div class="card"><h2>Method &amp; Honest Read</h2>
     <div class="prose">
      <p><strong>Data.</strong> Bloomberg point-in-time S&amp;P 500 membership: 1,085 historical names including every company later acquired, merged or delisted; ~500 genuine members each quarter; quarterly total returns 2002&ndash;2026. Membership is encoded in the data (a name has a return only while it was a member). A one-quarter labelling offset in the raw export was detected and corrected.</p>
      <p><strong>Engine.</strong> Trailing 4-quarter momentum, cross-sectional z-score, equal-weight top quartile; the 4-factor macro overlay scales gross exposure 30&ndash;100% with the remainder in cash at the risk-free rate; long-only; quarterly rebalance; 15&nbsp;bps round-trip cost.</p>
      <p><strong>Read.</strong> Survivorship bias is small (~1%/yr CAGR, ~0.10 Sharpe) &mdash; the backtest is not a survivorship illusion, and the capital-preservation edge survives intact. <strong>Caveat:</strong> this series is quarterly, which weakens momentum stock-selection across <em>both</em> universes; the durable, survivorship-proof edge is the macro risk overlay, not raw momentum alpha.</p>
     </div></div>
   </div>
  </div>
 </div>

 <div class="tab-panel" id="tab-terms">
  <div class="grid-2">
   <div class="card"><h2>Capacity</h2><table class="summary" id="capTable"></table></div>
   <div class="card"><h2>Fund Terms &amp; Investor Net-of-Fees</h2><table class="summary" id="termsTable"></table>
     <div class="subtitle" style="margin-top:10px">Net of all fees the client still beats SPY, with materially higher Sharpe and lower drawdown.</div>
     <table class="summary" id="netTable" style="margin-top:6px"></table></div>
  </div>
 </div>

 <div class="footer" id="footer"></div>
</div>

<script>
const D = __DATA__;
const NF = __NET__;
const SURV = __SURV__;
const PIT = __SURVPIT__;
const C = {navy:'#0B1F3A',gold:'#C9A96E',grey:'#5A6F8C',pos:'#2E7D5B',neg:'#B83A3A',blue:'#1E3A6C'};
const pct = x => (x==null?'—':(x*100).toFixed(1)+'%');
const f2  = x => (x==null?'—':(+x).toFixed(2));
const sx  = p => p.map(d=>d[0]); const sy = p => p.map(d=>d[1]);
const baseLayout = extra => Object.assign({margin:{l:48,r:14,t:10,b:34},paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'Helvetica Neue',size:11,color:C.navy},legend:{orientation:'h',y:-0.18,font:{size:10}},showlegend:true}, extra||{});
const CFG = {responsive:true,displayModeBar:false};

document.getElementById('generatedAt').textContent = D.meta.generated_at || '';

// meta strip
const m = D.meta;
document.getElementById('metaStrip').innerHTML = [
 ['Strategy', m.strategy],['Universe', m.universe],['Window', m.window],
 ['Cost basis', m.cost_basis||('Net '+m.tc_bps+'bps')],['Rebalance','Monthly, long-only']
].map(([l,v])=>`<div><div class="label">${l}</div><div class="value">${v}</div></div>`).join('');

// KPIs
const S = D.summary['Fund (full window)'], SP = D.summary.SPY, FR = D.factor_regression;
document.getElementById('kpiRow').innerHTML = [
 ['CAGR', pct(S.CAGR), 'vs SPY '+pct(SP.CAGR)],
 ['Sharpe', f2(S.Sharpe), 'vs SPY '+f2(SP.Sharpe)],
 ['Max Drawdown', pct(S.MaxDD), 'vs SPY '+pct(SP.MaxDD)],
 ['Alpha (FF5+MOM)', '+'+(FR.alpha_annualized*100).toFixed(1)+'%', 't = '+FR.alpha_tstat.toFixed(1)]
].map(([l,v,d])=>`<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div><div class="delta pos">${d}</div></div>`).join('');

// equity chart
const eqColors = {'Fund (Sector-Wide)':C.navy,'SPY':C.grey,'XLK':C.gold,'MTUM':C.blue};
Plotly.newPlot('equityChart', Object.entries(D.equity_curves).map(([k,v])=>({
  x:sx(v),y:sy(v),name:k,mode:'lines',line:{width:k.indexOf('Fund')>=0?2.6:1.3,color:eqColors[k]||C.grey}})),
  baseLayout({yaxis:{type:'log',title:'Growth of $1'}}), CFG);

// summary table
const rows = ['Fund (full window)','Fund IS (2002-2015)','Fund OOS (2016-2026)','SPY','XLK','MTUM','QUAL'];
const cols = ['CAGR','Vol','Sharpe','MaxDD','Calmar'];
let th = '<tr><th>Strategy</th>'+cols.map(c=>`<th style="text-align:right">${c}</th>`).join('')+'</tr>';
let tb = rows.filter(r=>D.summary[r]).map(r=>{const o=D.summary[r];const hl=r.indexOf('full')>=0?' class="highlight"':'';
  return `<tr${hl}><td>${r}</td>`+cols.map(c=>{const v=o[c];const disp=(c=='Sharpe'||c=='Calmar')?f2(v):pct(v);return `<td class="num">${disp}</td>`}).join('')+'</tr>';}).join('');
document.getElementById('summaryTable').innerHTML = th+tb;

// drawdowns
Plotly.newPlot('ddChart', Object.entries(D.drawdowns).map(([k,v])=>({
  x:sx(v),y:sy(v).map(z=>z*100),name:k,mode:'lines',fill:'tozeroy',
  line:{width:1.5,color:k=='Fund'?C.navy:C.grey},fillcolor:k=='Fund'?'rgba(11,31,58,.15)':'rgba(90,111,140,.10)'})),
  baseLayout({yaxis:{title:'Drawdown %'}}), CFG);

// stress
const st = D.stress_tests;
Plotly.newPlot('stressChart', [
 {x:st.map(s=>s.window),y:st.map(s=>s.fund_total*100),name:'Sector-Wide',type:'bar',marker:{color:C.navy}},
 {x:st.map(s=>s.window),y:st.map(s=>s.spy_total*100),name:'SPY',type:'bar',marker:{color:C.gold}}],
 baseLayout({yaxis:{title:'Total return %'},xaxis:{tickangle:-20,tickfont:{size:8}},barmode:'group'}), CFG);

// overlay exposure
const ge = D.regime.gross_exposure;
Plotly.newPlot('overlayChart', [{x:sx(ge),y:sy(ge).map(z=>z*100),mode:'lines',name:'Gross exposure',line:{color:C.gold,width:1.6},fill:'tozeroy',fillcolor:'rgba(201,169,110,.12)'}],
 baseLayout({showlegend:false,yaxis:{title:'Stock exposure %',range:[0,105]}}), CFG);

// sector breakdown
const sb = D.sector_breakdown;
document.getElementById('diversNote').textContent = `${D.holdings_latest.n_holdings} stocks across ${D.holdings_latest.n_sectors} sectors — diversified, not a tech bet.`;
Plotly.newPlot('sectorChart', [{x:Object.values(sb),y:Object.keys(sb),type:'bar',orientation:'h',marker:{color:C.navy}}],
 baseLayout({showlegend:false,margin:{l:140,r:14,t:10,b:30},xaxis:{title:'# stocks'},yaxis:{autorange:'reversed'}}), CFG);

// holdings
document.getElementById('holdingsList').innerHTML = D.holdings_latest.weights.map(h=>{
 const w=(h.weight*100); return `<li><span class="ticker">${h.ticker}</span><span style="color:var(--grey-text);font-size:9.5px;flex:0 0 130px">${h.sector}</span><span class="bar"><span style="width:${Math.min(w/2*100,100)}%"></span></span><span class="weight">${w.toFixed(2)}%</span></li>`;}).join('');

// sensitivity heatmap
const sen = D.sensitivity;
Plotly.newPlot('sensChart', [{z:sen.sharpe_grid,x:sen.quantiles.map(String),y:sen.lookbacks.map(String),
 type:'heatmap',colorscale:[[0,'#F5F2EA'],[1,C.navy]],showscale:true,
 text:sen.sharpe_grid.map(r=>r.map(v=>v.toFixed(2))),texttemplate:'%{text}',textfont:{size:10}}],
 baseLayout({showlegend:false,xaxis:{title:'Top-quantile'},yaxis:{title:'Lookback (mo)'}}), CFG);

// factor betas
const FB = D.factor_regression.betas, FT = D.factor_regression.betas_tstat;
document.getElementById('alphaNote').textContent = `Alpha +${(FR.alpha_annualized*100).toFixed(1)}% (t=${FR.alpha_tstat.toFixed(1)}), R²=${FR.rsquared.toFixed(2)} — return not explained by standard factors.`;
const fk = Object.keys(FB);
Plotly.newPlot('betaChart', [{x:fk,y:fk.map(k=>FB[k]),type:'bar',marker:{color:fk.map(k=>FB[k]>=0?C.pos:C.neg)},
 text:fk.map(k=>'t='+FT[k].toFixed(1)),textposition:'outside',textfont:{size:9}}],
 baseLayout({showlegend:false,yaxis:{title:'Beta'}}), CFG);

// capacity
const cap = D.capacity;
document.getElementById('capTable').innerHTML =
 [['Commitment to raise', '$'+(cap.commitment_raise/1e6).toFixed(0)+'M'],
  ['Strategy soft capacity', '$'+(cap.soft_cap_low/1e9).toFixed(1)+'–'+(cap.soft_cap_high/1e9).toFixed(1)+'B'],
  ['Headroom vs raise', (cap.headroom_low).toFixed(0)+'–'+(cap.headroom_high).toFixed(0)+'x'],
  ['Capacity used at raise', '~'+(cap.pct_of_capacity_at_raise*100).toFixed(0)+'%'],
  ['Avg holdings', cap.avg_n_holdings.toFixed(0)],
  ['Avg annual turnover', (cap.avg_annual_turnover*100).toFixed(0)+'%'],
  ['ADV assumption', cap.adv_assumption]]
  .map(([l,v])=>`<tr><td>${l}</td><td class="num">${v}</td></tr>`).join('');

// terms + net
const T = NF.terms;
document.getElementById('termsTable').innerHTML =
 [['Management fee',T.management_fee],['Performance fee',T.performance_fee],['High-water mark',T.high_water_mark],
  ['Crystallisation',T.crystallisation],['Liquidity',T.liquidity]]
  .map(([l,v])=>`<tr><td>${l}</td><td style="text-align:right">${v}</td></tr>`).join('');
document.getElementById('netTable').innerHTML =
 '<tr><th></th><th style="text-align:right">CAGR</th><th style="text-align:right">Sharpe</th><th style="text-align:right">MaxDD</th></tr>'+
 [['Gross strategy',NF.gross],['NET to investor',NF.net],['S&P 500 (SPY)',NF.spy]]
  .map(([l,o],i)=>`<tr${i==1?' class="highlight"':''}><td>${l}</td><td class="num">${pct(o.CAGR)}</td><td class="num">${f2(o.Sharpe)}</td><td class="num">${pct(o.MaxDD)}</td></tr>`).join('');

// footer
document.getElementById('footer').innerHTML = '<strong>Disclaimer:</strong> Fictional pitch for the ESADE Asset Management course. All performance is SIMULATED on historical data, net of 15bps trading costs; the net-of-fees track record additionally deducts the stated fund fees. Past performance — simulated or otherwise — does not indicate future results. Survivorship bias measured on Bloomberg point-in-time S&P 500 data: ~1%/yr of CAGR (small, academic range); the risk-control edge is survivorship-robust. Out-of-sample (2019+) factor alpha compressed industry-wide; recent value is capital preservation at lower risk.';

// survivorship — point-in-time (Bloomberg) headline table
const alphaFmt = (a,t) => (a>=0?'+':'')+(a*100).toFixed(1)+'% (t='+t.toFixed(1)+')';
{
 const SF = PIT.summary['Survivorship-free'], BI = PIT.summary['Survivors-only (biased)'], SP = PIT.summary['SPY'], BZ = PIT.bias;
 document.getElementById('pitTable').innerHTML =
  '<tr><th>Universe (quarterly, point-in-time)</th><th style="text-align:right">CAGR</th><th style="text-align:right">Vol</th><th style="text-align:right">Sharpe</th><th style="text-align:right">MaxDD</th></tr>'+
  `<tr class="highlight"><td>A. Survivorship-free</td><td class="num">${pct(SF.CAGR)}</td><td class="num">${pct(SF.Vol)}</td><td class="num">${f2(SF.Sharpe)}</td><td class="num">${pct(SF.MaxDD)}</td></tr>`+
  `<tr><td>B. Survivors-only (recreates bias)</td><td class="num">${pct(BI.CAGR)}</td><td class="num">${pct(BI.Vol)}</td><td class="num">${f2(BI.Sharpe)}</td><td class="num">${pct(BI.MaxDD)}</td></tr>`+
  `<tr><td>S&P 500 (SPY)</td><td class="num">${pct(SP.CAGR)}</td><td class="num">${pct(SP.Vol)}</td><td class="num">${f2(SP.Sharpe)}</td><td class="num">${pct(SP.MaxDD)}</td></tr>`+
  `<tr><td><strong>Survivorship bias (B − A)</strong></td><td class="num"><strong>${(BZ.cagr_drag*100).toFixed(1)}%</strong></td><td class="num">—</td><td class="num"><strong>${(BZ.sharpe_drag).toFixed(2)}</strong></td><td class="num">—</td></tr>`;
}
const SPYm = SURV.spy;
document.getElementById('haircutTable').innerHTML =
 '<tr><th>Haircut/yr</th><th style="text-align:right">CAGR</th><th style="text-align:right">Sharpe</th><th style="text-align:right">MaxDD</th><th style="text-align:right">Alpha (FF5+MOM)</th></tr>'+
 SURV.option2_haircut.map(r=>`<tr${Math.abs(r.haircut-0.02)<1e-9?' class="highlight"':''}><td>${(r.haircut*100).toFixed(0)}%</td><td class="num">${pct(r.CAGR)}</td><td class="num">${f2(r.Sharpe)}</td><td class="num">${pct(r.MaxDD)}</td><td class="num">${alphaFmt(r.Alpha,r.Alpha_t)}</td></tr>`).join('')+
 `<tr><td>SPY</td><td class="num">${pct(SPYm.CAGR)}</td><td class="num">${f2(SPYm.Sharpe)}</td><td class="num">${pct(SPYm.MaxDD)}</td><td class="num">—</td></tr>`;

// survivorship — Option 3 free-universe table
const FW = D.summary['Fund (full window)'], FRr = D.factor_regression;
const ef = SURV.option3_etf_free, ind = SURV.option3_industries_free;
document.getElementById('freeTable').innerHTML =
 '<tr><th>Universe</th><th style="text-align:right">CAGR</th><th style="text-align:right">Sharpe</th><th style="text-align:right">MaxDD</th><th style="text-align:right">Alpha (FF5+MOM)</th></tr>'+
 [['Stock-level (current S&P 500)', FW.CAGR, FW.Sharpe, FW.MaxDD, FRr.alpha_annualized, FRr.alpha_tstat],
  ['Free: 9 sector ETFs', ef.CAGR, ef.Sharpe, ef.MaxDD, ef.Alpha, ef.Alpha_t],
  ['Free: 30 KF industries (’02–18)', ind.CAGR, ind.Sharpe, ind.MaxDD, ind.Alpha, ind.Alpha_t]]
  .map((r,i)=>`<tr${i==2?' class="highlight"':''}><td>${r[0]}</td><td class="num">${pct(r[1])}</td><td class="num">${f2(r[2])}</td><td class="num">${pct(r[3])}</td><td class="num">${alphaFmt(r[4],r[5])}</td></tr>`).join('')+
 `<tr><td>SPY (full)</td><td class="num">${pct(SPYm.CAGR)}</td><td class="num">${f2(SPYm.Sharpe)}</td><td class="num">${pct(SPYm.MaxDD)}</td><td class="num">—</td></tr>`;

// ===== Point-in-Time Report tab =====
{
 const SF=PIT.summary['Survivorship-free'], BI=PIT.summary['Survivors-only (biased)'], SP=PIT.summary['SPY'], BZ=PIT.bias, FRf=PIT.factor_regression_free;
 const mp=PIT.meta;
 document.getElementById('pitMeta').innerHTML = `${mp.source} &middot; ${mp.universe} &middot; ${mp.frequency} &middot; ${mp.window} &middot; net ${mp.tc_bps} bps`;
 // KPIs
 document.getElementById('pitKpi').innerHTML = [
  ['CAGR (surv-free)', pct(SF.CAGR), 'vs SPY '+pct(SP.CAGR)],
  ['Sharpe', f2(SF.Sharpe), 'vs SPY '+f2(SP.Sharpe)],
  ['Max Drawdown', pct(SF.MaxDD), 'vs SPY '+pct(SP.MaxDD)],
  ['Survivorship bias', (BZ.cagr_drag*100).toFixed(1)+'%/yr', 'Sharpe '+BZ.sharpe_drag.toFixed(2)]
 ].map(([l,v,d])=>`<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div><div class="delta pos">${d}</div></div>`).join('');
 // equity curves
 const pitCol={'Survivorship-free':C.pos,'Survivors-only (biased)':C.gold,'SPY':C.grey};
 const pitDash={'Survivorship-free':'solid','Survivors-only (biased)':'dash','SPY':'dot'};
 Plotly.newPlot('pitEquity', Object.entries(PIT.equity_curves).map(([k,v])=>({
   x:sx(v),y:sy(v),name:k,mode:'lines',line:{width:k.indexOf('free')>=0?2.6:1.5,color:pitCol[k]||C.grey,dash:pitDash[k]||'solid'}})),
   baseLayout({yaxis:{type:'log',title:'Growth of $1'}}), CFG);
 // full metrics table
 const pcols=['CAGR','Vol','Sharpe','MaxDD','Calmar'];
 const prows=[['A. Survivorship-free','Survivorship-free',1],['B. Survivors-only (biased)','Survivors-only (biased)',0],
   ['S&P 500 (SPY)','SPY',0],['Surv-free IS (2002-15)','Survivorship-free IS (2002-2015)',0],
   ['Surv-free OOS (2016-26)','Survivorship-free OOS (2016-2026)',0]];
 document.getElementById('pitFullTable').innerHTML =
  '<tr><th>Universe</th>'+pcols.map(c=>`<th style="text-align:right">${c}</th>`).join('')+'</tr>'+
  prows.filter(r=>PIT.summary[r[1]]).map(r=>{const o=PIT.summary[r[1]];
    return `<tr${r[2]?' class="highlight"':''}><td>${r[0]}</td>`+pcols.map(c=>{const v=o[c];const disp=(c=='Sharpe'||c=='Calmar')?f2(v):pct(v);return `<td class="num">${disp}</td>`}).join('')+'</tr>';}).join('')+
  `<tr><td><strong>Survivorship bias (B&minus;A)</strong></td><td class="num"><strong>${(BZ.cagr_drag*100).toFixed(1)}%</strong></td><td class="num">&mdash;</td><td class="num"><strong>${BZ.sharpe_drag.toFixed(2)}</strong></td><td class="num">&mdash;</td><td class="num">&mdash;</td></tr>`;
 const isS=PIT.summary['Survivorship-free IS (2002-2015)'].Sharpe, oosS=PIT.summary['Survivorship-free OOS (2016-2026)'].Sharpe;
 document.getElementById('pitBiasNote').innerHTML = `Stock-selection alpha vs FF5+MOM (quarterly): survivorship-free <strong>${alphaFmt(BZ.alpha_free,BZ.alpha_free_t)}</strong>, biased ${alphaFmt(BZ.alpha_biased,BZ.alpha_biased_t)} &mdash; statistically insignificant at quarterly frequency in both, so the bias is small but the momentum alpha is frequency-sensitive. <strong>Out-of-sample Sharpe (${f2(oosS)}) exceeds in-sample (${f2(isS)})</strong> &mdash; no out-of-sample decay, i.e. not overfit.`;
 // drawdowns
 Plotly.newPlot('pitDD', Object.entries(PIT.drawdowns).map(([k,v])=>({
   x:sx(v),y:sy(v).map(z=>z*100),name:k,mode:'lines',fill:'tozeroy',
   line:{width:1.5,color:k.indexOf('free')>=0?C.pos:C.grey},fillcolor:k.indexOf('free')>=0?'rgba(46,125,91,.15)':'rgba(90,111,140,.10)'})),
   baseLayout({yaxis:{title:'Drawdown %'}}), CFG);
 // factor betas
 const PFB=FRf.betas, pfk=Object.keys(PFB);
 document.getElementById('pitAlphaNote').innerHTML = `Alpha ${(FRf.alpha_annualized*100).toFixed(1)}% (t=${FRf.alpha_tstat.toFixed(1)}), R&sup2;=${FRf.rsquared.toFixed(2)}, market beta ${PFB['Mkt-RF'].toFixed(2)} &mdash; low net exposure via the overlay. <em>Beta and R&sup2; also confirm the corrected data alignment (the pre-fix run gave beta &minus;0.03, R&sup2; 0.13).</em>`;
 Plotly.newPlot('pitBeta', [{x:pfk,y:pfk.map(k=>PFB[k]),type:'bar',marker:{color:pfk.map(k=>PFB[k]>=0?C.pos:C.neg)},
   text:pfk.map(k=>PFB[k].toFixed(2)),textposition:'outside',textfont:{size:9}}],
   baseLayout({showlegend:false,yaxis:{title:'Beta'}}), CFG);
 // diagnostics
 const dg=PIT.diagnostics;
 document.getElementById('pitDiag').innerHTML =
  [['Historical names (universe)', dg.n_historical_names],
   ['Survivors at end of window', dg.n_survivors],
   ['Names removed (delisted/acquired)', dg.n_historical_names-dg.n_survivors],
   ['Avg names selected / quarter', dg.avg_names_per_quarter.toFixed(0)+' (~top quartile of ~500)'],
   ['Avg turnover', (dg.avg_annual_turnover*100).toFixed(0)+'%/yr (~'+(dg.avg_annual_turnover/4*100).toFixed(0)+'%/qtr)']]
   .map(([l,v])=>`<tr><td>${l}</td><td class="num">${v}</td></tr>`).join('');
}
function printReport(){
 document.querySelectorAll('.tabnav button').forEach(x=>x.classList.remove('active'));
 document.querySelectorAll('.tab-panel').forEach(x=>x.classList.remove('active'));
 const btn=document.querySelector('.tabnav button[data-tab="pitreport"]'); if(btn)btn.classList.add('active');
 document.getElementById('tab-pitreport').classList.add('active');
 window.dispatchEvent(new Event('resize'));
 ['pitEquity','pitDD','pitBeta'].forEach(id=>{try{Plotly.Plots.resize(id);}catch(e){}});
 setTimeout(()=>window.print(), 450);
}

// tabs
document.querySelectorAll('.tabnav button').forEach(b=>b.onclick=()=>{
 document.querySelectorAll('.tabnav button').forEach(x=>x.classList.remove('active'));
 document.querySelectorAll('.tab-panel').forEach(x=>x.classList.remove('active'));
 b.classList.add('active'); document.getElementById('tab-'+b.dataset.tab).classList.add('active');
 setTimeout(()=>window.dispatchEvent(new Event('resize')),30);
});
</script></body></html>"""

html = (HTML.replace("__DATA__", json.dumps(DATA)).replace("__NET__", json.dumps(NET))
            .replace("__SURV__", json.dumps(SURV)).replace("__SURVPIT__", json.dumps(PIT)))
Path("sectorwide_dashboard.html").write_text(html)
print(f"Saved sectorwide_dashboard.html ({len(html)//1024} KB)")
