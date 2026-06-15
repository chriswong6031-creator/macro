"""S&P / Macro Vector — dashboard page builder (Phase 3 surface).

Self-contained: renders site/spvector.html from engine.equity_alloc.vector_alloc
(the validated de-risk + Fed-put-gated re-deploy strategy). Deliberately NOT a clone
of the 70KB build_vector.py — a lean standalone page (Plotly via CDN, dark theme,
no theme.css coupling) so it can't break the macro/BTC builds. Honest by design: the
hero says "drawdown/Sharpe engine, not a CAGR-beater" and the page surfaces the
bull-market lag, the carry-vs-alpha split, the bear-episode ledger, and the tax note.

Run: python -m scripts.build_spvector
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from engine import equity_alloc as ea
from engine.validation import backtest_core
from lib import config

COST_BPS = 3.0
TY = ea.TRADING_YEAR


def _series_json(s: pd.Series) -> dict:
    s = s.dropna()
    return {"x": [d.strftime("%Y-%m-%d") for d in s.index], "y": [round(float(v), 4) for v in s.values]}


def build() -> str:
    from engine.inputs import build_features
    from engine.conditions import conditions_frame
    from lib import store
    f = build_features(); cf = conditions_frame(f); reg = store.read("regime", "regime_history")
    spy = ea.index_close("SPY"); bills = ea.bill_yield()
    rs = ea.risk_score(f, reg, cf)
    alloc = ea.vector_alloc(spy, f=f, regime=reg, cf=cf)
    sc = ea.summarize(spy, alloc, "Vector", cash_yield=bills, cost_bps=COST_BPS)

    bt = backtest_core(spy, alloc, cost_bps=COST_BPS, cash_yield=bills)
    eq = (1 + bt["net"]).cumprod(); hodl = (1 + bt["hold"]).cumprod()
    dd_s = (eq / eq.cummax() - 1) * 100
    dd_h = (hodl / hodl.cummax() - 1) * 100
    rs_on_spy = rs.reindex(spy.index, method="ffill")
    pos = bt["pos"]

    # current reading
    cur_score = float(rs_on_spy.dropna().iloc[-1])
    cur_w = float(pos.dropna().iloc[-1]) * 100
    for thr, _en, _zh in ((25, "LOW — fully invested", "低 — 满仓"),
                          (50, "ELEVATED — trim", "偏高 — 减仓"),
                          (75, "HIGH — de-risk", "高 — 降低风险"),
                          (1e9, "EXTREME — defensive", "极端 — 防御")):
        if cur_score < thr:
            band = f'<span class="l-en">{_en}</span><span class="l-zh">{_zh}</span>'
            break
    asof = spy.index[-1].strftime("%Y-%m-%d")

    # weekly-ish downsample for chart payloads (every 5 trading days, aligned)
    st = 5
    eq_j = _series_json(eq.iloc[::st]); ho_j = _series_json(hodl.iloc[::st])
    al_j = _series_json(pos.iloc[::st]); sc_j = _series_json(rs_on_spy.iloc[::st])
    dds_j = _series_json(dd_s.iloc[::st]); ddh_j = _series_json(dd_h.iloc[::st])

    episodes = ea.bear_episodes(spy, 0.20)
    ep_rows = "".join(
        f"<tr><td>{e['peak']}</td><td>{e['trough']}</td><td class='neg'>{e['drawdown_pct']}%</td></tr>"
        for e in episodes)

    def card(label_en, label_zh, v, bh, fmt="{:.2f}", good_high=True):
        better = (v > bh) if good_high else (v < bh)
        return (f"<div class='card'><div class='lbl'><span class='l-en'>{label_en}</span>"
                f"<span class='l-zh'>{label_zh}</span></div>"
                f"<div class='big {'win' if better else 'mut'}'>{fmt.format(v)}</div>"
                f"<div class='sub'><span class='l-en'>buy &amp; hold</span><span class='l-zh'>买入持有</span> "
                f"{fmt.format(bh)}</div></div>")

    cards = (card("CAGR", "年化收益", sc["cagr"], sc["hodl_cagr"], "{:.1f}%") +
             card("Sharpe", "夏普比率", sc["sharpe"], sc["hodl_sharpe"], "{:.2f}") +
             card("Max drawdown", "最大回撤", sc["maxdd"], sc["hodl_maxdd"], "{:.0f}%", good_high=True) +
             card("Turnover/yr", "年换手", sc["turnover_annual"], 0.03, "{:.1f}x", good_high=False))

    payload = json.dumps({"eq": eq_j, "ho": ho_j, "al": al_j, "rs": sc_j, "dds": dds_j, "ddh": ddh_j})
    html = _TMPL.format(asof=asof, cur_score=f"{cur_score:.0f}", cur_w=f"{cur_w:.0f}", band=band,
                        cards=cards, ep_rows=ep_rows,
                        nocarry=f"{sc['cagr_nocarry']:.1f}", years=f"{sc['years']:.0f}",
                        inmkt=f"{sc['time_in_market']:.0f}")
    html = html.replace("__PAYLOAD__", payload)   # JSON braces collide with .format -> replace separately
    out = config.ROOT / "site" / "spvector.html"
    out.write_text(html)
    return str(out)


_TMPL = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>S&amp;P / Macro Vector — index allocation</title>
<script>try{{var t=localStorage.getItem('theme');if(t)document.documentElement.setAttribute('data-theme',t);var l=localStorage.getItem('lang');if(l)document.documentElement.setAttribute('data-lang',l);}}catch(e){{}}</script>
<!-- fallback base palette (mirrors theme.css dark) so the page stays styled even if theme.css fails to load; theme.css overrides + handles light mode -->
<style>:root{{--bg:#0f1115;--panel:#181b21;--panel2:#1e222a;--line:#2a2f3a;--text:#d7dce3;--muted:#8b93a1}}</style>
<link rel="stylesheet" href="theme.css">
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.27.0/plotly.min.js"></script>
<style>
/* page-local accents + aliases onto the shared theme.css palette so dark/light
   both work (--bg/--panel/--line/--text/--muted come from theme.css). */
:root{{--tx:var(--text);--mut:var(--muted);--blue:#388bfd;--grn:#3fb950;--red:#f85149;--amb:#d29922}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);font:15px/1.6 -apple-system,Segoe UI,Inter,sans-serif}}
.wrap{{max-width:1080px;margin:0 auto;padding:28px 20px 60px}}
h1{{font-size:26px;margin:0 0 4px}}.tag{{color:var(--amb);font-weight:600}}.mutline{{color:var(--mut);margin:0 0 22px}}
.hero{{display:flex;flex-wrap:wrap;gap:16px;align-items:stretch;margin-bottom:22px}}
.dial{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 22px;min-width:230px;flex:1}}
.dial .s{{font-size:44px;font-weight:700}}.dial .w{{font-size:15px;color:var(--mut)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;flex:2;min-width:300px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 14px}}
.card .lbl{{color:var(--mut);font-size:12px}}.card .big{{font-size:24px;font-weight:700}}.card .sub{{color:var(--mut);font-size:12px}}
.win{{color:var(--grn)}}.mut{{color:var(--tx)}}.neg{{color:var(--red)}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 22px;margin:16px 0}}
.panel h2{{font-size:17px;margin:0 0 10px}}.chart{{height:340px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line)}}
.note{{border-left:3px solid var(--amb);padding:4px 0 4px 14px;margin:10px 0;color:#d7dce2}}
.note.r{{border-color:var(--red)}}.note.b{{border-color:var(--blue)}}
a{{color:var(--blue)}}
</style></head><body><div class="wrap">
<nav class="site-nav">
  <div class="nav-links">
    <a class="nav-link" href="index.html">🏠 <span class="l-en">Home</span><span class="l-zh">首页</span></a>
    <div class="nav-dd">
      <a class="nav-link active" href="macro.html">🇺🇸 <span class="l-en">US Macro</span><span class="l-zh">美国宏观</span> <span class="caret">▾</span></a>
      <div class="nav-dd-menu">
        <a href="macro.html">📊 <span class="l-en">Macro dashboard</span><span class="l-zh">宏观仪表盘</span></a>
        <a href="spvector.html">📈 <span class="l-en">S&amp;P / Macro Vector</span><span class="l-zh">标普宏观向量</span></a>
        <a href="gex.html">🧲 <span class="l-en">GEX magnets</span><span class="l-zh">Gamma磁吸</span></a>
      </div>
    </div>
    <a class="nav-link" href="vector.html">₿ <span class="l-en">Bitcoin Vector</span><span class="l-zh">比特币向量</span></a>
    <a class="nav-link" href="etfs.html">🐳 <span class="l-en">ETF flows</span><span class="l-zh">ETF 资金流</span></a>
    <a class="nav-link" href="china.html">🇨🇳 <span class="l-en">China</span><span class="l-zh">中国A股</span></a>
    <a class="nav-link" href="hk.html">🇭🇰 <span class="l-en">Hong Kong</span><span class="l-zh">香港</span></a>
    <a class="nav-link" href="commodities.html">🛢 <span class="l-en">Commodities</span><span class="l-zh">大宗商品</span></a>
    <a class="nav-link" href="forex.html">💱 <span class="l-en">Forex</span><span class="l-zh">外汇</span></a>
    <a class="nav-link" href="bonds.html">🏛️ <span class="l-en">Bonds</span><span class="l-zh">债券</span></a>
    <a class="nav-link" href="discovery.html">🏆 <span class="l-en">Alpha leaders</span><span class="l-zh">阿尔法领先股</span></a>
    <a class="nav-link" href="brief.html">📰 <span class="l-en">Brief</span><span class="l-zh">简报</span></a>
    <a class="nav-link" href="history.html">📈 <span class="l-en">History</span><span class="l-zh">历史</span></a>
  </div>
  <div class="nav-search">
    <span class="mag">🔎</span>
    <input type="text" autocomplete="off" aria-label="Search stocks"
      placeholder="Search any stock, ETF, commodity or crypto…" data-ph-zh="搜索任意股票、ETF、商品或加密货币…">
    <div class="nav-sugg"></div>
  </div>
  <div class="nav-ctrls">
    <button class="theme-switch" aria-label="Toggle dark / light mode">
      <span class="ic sun">☀️</span><span class="ic moon">🌙</span><span class="knob"></span>
    </button>
    <div class="lang-toggle" role="group" aria-label="Language">
      <span class="pill"></span>
      <span class="opt en-opt" data-l="en">EN</span>
      <span class="opt zh-opt" data-l="zh">中文</span>
    </div>
  </div>
</nav>
<h1>S&amp;P / Macro Vector</h1>
<p class="mutline"><span class="l-en">Tactical allocation: a broad US index &harr; T-bills.</span><span class="l-zh">战术配置：宽基美股指数 &harr; 国库券。</span> <span class="tag"><span class="l-en">A drawdown / Sharpe engine — not a CAGR-beater.</span><span class="l-zh">回撤 / 夏普引擎 — 并非跑赢年化收益的工具。</span></span> &nbsp;<span class="l-en">as of</span><span class="l-zh">截至</span> {asof}</p>

<div class="hero">
  <div class="dial">
    <div class="lbl" style="color:var(--mut);font-size:12px"><span class="l-en">MACRO RISK SCORE (0-100)</span><span class="l-zh">宏观风险评分（0-100）</span></div>
    <div class="s">{cur_score}</div>
    <div class="w">{band}</div>
    <div class="w" style="margin-top:8px"><span class="l-en">recommended equity weight:</span><span class="l-zh">建议股票权重：</span> <b style="color:var(--tx)">{cur_w}%</b> &nbsp;/&nbsp; <span class="l-en">rest in T-bills</span><span class="l-zh">其余配置国库券</span></div>
  </div>
  <div class="cards">{cards}</div>
</div>

<div class="note b"><span class="l-en">Honest framing: the CAGR above includes the T-bill carry earned on the de-risked sleeve; net of carry (~{nocarry}% no-carry CAGR) it roughly matches buy &amp; hold. The robust, verified edge is the higher Sharpe and the ~40% shallower max drawdown. Stays ~{inmkt}% invested; it WILL lag the index in prolonged bulls — that give-up is the premium paid for crash protection, banked when the cycle breaks.</span><span class="l-zh">诚实说明：上方年化收益包含降险仓位在国库券上赚取的利息；扣除利息后（约 {nocarry}% 的无息年化收益）大致与买入持有持平。经验证的稳健优势在于更高的夏普比率与约浅 40% 的最大回撤。约保持 {inmkt}% 仓位；在长期牛市中它必然跑输指数 — 这一让渡是为崩盘保护支付的保费，在周期破裂时兑现。</span></div>

<div class="panel"><h2><span class="l-en">Growth of $1 — Vector vs buy &amp; hold (log scale)</span><span class="l-zh">$1 增长 — Vector 对比买入持有（对数刻度）</span></h2><div id="eqc" class="chart"></div></div>
<div class="panel"><h2><span class="l-en">Allocation &amp; macro risk score over time</span><span class="l-zh">配置与宏观风险评分随时间变化</span></h2><div id="alc" class="chart"></div></div>
<div class="panel"><h2><span class="l-en">Underwater (drawdown) — Vector vs buy &amp; hold</span><span class="l-zh">水下（回撤）— Vector 对比买入持有</span></h2><div id="ddc" class="chart"></div></div>

<div class="panel"><h2><span class="l-en">Independent bear episodes ({years}yr) — the true sample size</span><span class="l-zh">独立熊市事件（{years} 年）— 真正的样本量</span></h2>
<table><tr><th><span class="l-en">peak</span><span class="l-zh">峰值</span></th><th><span class="l-en">trough</span><span class="l-zh">谷底</span></th><th><span class="l-en">S&amp;P drawdown</span><span class="l-zh">标普回撤</span></th></tr>{ep_rows}</table>
<p class="w" style="color:var(--mut);font-size:13px;margin-top:8px"><span class="l-en">Only ~4 independent &ge;20% bears govern a get-out/get-back-in switch — effective-N, not the day count, bounds confidence. Validated via leave-one-crisis-out + an AQR-style permutation null (real Sharpe &amp; drawdown beat every random-timing shuffle, p=0.0). See reports/spvector-phase3-audit.md.</span><span class="l-zh">仅约 4 次独立的 &ge;20% 熊市决定了离场/回场的切换 — 有效样本量（而非天数）限定置信度。通过留一危机交叉验证 + AQR 式置换零假设检验（真实夏普与回撤击败每一次随机择时洗牌，p=0.0）。详见 reports/spvector-phase3-audit.md。</span></p></div>

<div class="note r"><span class="l-en">Taxable-account warning: switching realizes short-term capital gains that buy &amp; hold defers — best run in a tax-advantaged account. The low ~1.5x/yr turnover keeps this manageable.</span><span class="l-zh">应税账户提示：切换会实现买入持有所递延的短期资本利得 — 最好在税收优惠账户中运行。约 1.5 倍/年的低换手使其可控。</span></div>
<p class="w" style="color:var(--mut);font-size:13px"><span class="l-en">Macro legs (NFCI / recession-prob / Sahm / EBP) are revised FRED series, PIT-lagged per-leg by publication delay; ALFRED point-in-time vintages are the last honesty upgrade. Reports: spvector-baseline / phase1 / phase2 / phase3-audit. Research: research/SP_VECTOR_VIABILITY.md.</span><span class="l-zh">宏观分项（NFCI / 衰退概率 / Sahm / EBP）为可修订的 FRED 序列，按各自发布延迟做时点滞后；ALFRED 时点历史版本是最后一项诚实升级。报告：spvector-baseline / phase1 / phase2 / phase3-audit。研究：research/SP_VECTOR_VIABILITY.md。</span></p>

<script>
var D=__PAYLOAD__;
var L={{paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{{color:'#8b949e',size:11}},margin:{{l:48,r:16,t:8,b:30}},
        legend:{{orientation:'h',y:1.12,x:0}},xaxis:{{gridcolor:'#262d38'}},yaxis:{{gridcolor:'#262d38'}}}};
function cp(o){{return JSON.parse(JSON.stringify(o));}}
var l1=cp(L);l1.yaxis.type='log';
Plotly.newPlot('eqc',[
 {{x:D.eq.x,y:D.eq.y,name:'Vector',line:{{color:'#3fb950',width:2}}}},
 {{x:D.ho.x,y:D.ho.y,name:'Buy & hold',line:{{color:'#8b949e',width:1.5}}}}],l1,{{displayModeBar:false,responsive:true}});
var l2=cp(L);l2.yaxis={{gridcolor:'#262d38',title:'equity weight',range:[0,1.05]}};l2.yaxis2={{overlaying:'y',side:'right',title:'risk score',range:[0,100],showgrid:false}};
Plotly.newPlot('alc',[
 {{x:D.al.x,y:D.al.y,name:'equity weight',fill:'tozeroy',line:{{color:'#388bfd',width:1}}}},
 {{x:D.rs.x,y:D.rs.y,name:'risk score',yaxis:'y2',line:{{color:'#d29922',width:1.5}}}}],l2,{{displayModeBar:false,responsive:true}});
Plotly.newPlot('ddc',[
 {{x:D.ddh.x,y:D.ddh.y,name:'Buy & hold',fill:'tozeroy',line:{{color:'#8b949e',width:1}}}},
 {{x:D.dds.x,y:D.dds.y,name:'Vector',fill:'tozeroy',line:{{color:'#3fb950',width:1.5}}}}],cp(L),{{displayModeBar:false,responsive:true}});
// translate the in-chart legend + axis titles on language toggle (trace 'Vector' is a product name, kept)
function spLangText(){{
  var zh=document.documentElement.getAttribute('data-lang')==='zh';
  var bh=zh?'买入持有':'Buy & hold', ew=zh?'股票权重':'equity weight', rsc=zh?'风险评分':'risk score';
  try{{
    Plotly.restyle('eqc',{{name:bh}},[1]);
    Plotly.restyle('ddc',{{name:bh}},[0]);
    Plotly.restyle('alc',{{name:ew}},[0]); Plotly.restyle('alc',{{name:rsc}},[1]);
    Plotly.relayout('alc',{{'yaxis.title':ew,'yaxis2.title':rsc}});
  }}catch(e){{}}
}}
spLangText();
document.addEventListener('langchange',spLangText);
</script>
<script src="theme.js"></script>
</div></body></html>"""


def main() -> int:
    out = build()
    print(f"[built] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
