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
    band = ("LOW — fully invested" if cur_score < 25 else "ELEVATED — trim" if cur_score < 50
            else "HIGH — de-risk" if cur_score < 75 else "EXTREME — defensive")
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

    def card(label, v, bh, fmt="{:.2f}", good_high=True):
        better = (v > bh) if good_high else (v < bh)
        return (f"<div class='card'><div class='lbl'>{label}</div>"
                f"<div class='big {'win' if better else 'mut'}'>{fmt.format(v)}</div>"
                f"<div class='sub'>buy &amp; hold {fmt.format(bh)}</div></div>")

    cards = (card("CAGR", sc["cagr"], sc["hodl_cagr"], "{:.1f}%") +
             card("Sharpe", sc["sharpe"], sc["hodl_sharpe"], "{:.2f}") +
             card("Max drawdown", sc["maxdd"], sc["hodl_maxdd"], "{:.0f}%", good_high=True) +
             card("Turnover/yr", sc["turnover_annual"], 0.03, "{:.1f}x", good_high=False))

    payload = json.dumps({"eq": eq_j, "ho": ho_j, "al": al_j, "rs": sc_j, "dds": dds_j, "ddh": ddh_j})
    html = _TMPL.format(asof=asof, cur_score=f"{cur_score:.0f}", cur_w=f"{cur_w:.0f}", band=band,
                        cards=cards, ep_rows=ep_rows,
                        nocarry=f"{sc['cagr_nocarry']:.1f}", years=f"{sc['years']:.0f}",
                        inmkt=f"{sc['time_in_market']:.0f}")
    html = html.replace("__PAYLOAD__", payload)   # JSON braces collide with .format -> replace separately
    out = config.ROOT / "site" / "spvector.html"
    out.write_text(html)
    # persist a tiny state file for the landing-hub card (build_vector._spvector_state)
    band_key = ("Low" if cur_score < 25 else "Elevated" if cur_score < 50
                else "High" if cur_score < 75 else "Extreme")
    (config.data_dir() / "regime").mkdir(parents=True, exist_ok=True)
    (config.data_dir() / "regime" / "spvector_latest.json").write_text(json.dumps(
        {"risk_score": round(cur_score, 1), "equity_weight": int(round(cur_w)),
         "band": f"{band_key} risk", "asof": asof}))
    return str(out)


_TMPL = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>S&amp;P / Macro Vector — index allocation</title>
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.27.0/plotly.min.js"></script>
<style>
:root{{--bg:#0e1117;--panel:#161b22;--line:#262d38;--tx:#e6edf3;--mut:#8b949e;--blue:#388bfd;--grn:#3fb950;--red:#f85149;--amb:#d29922}}
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
<h1>S&amp;P / Macro Vector</h1>
<p class="mutline">Tactical allocation: a broad US index &harr; T-bills. <span class="tag">A drawdown / Sharpe engine — not a CAGR-beater.</span> &nbsp;as of {asof}</p>

<div class="hero">
  <div class="dial">
    <div class="lbl" style="color:var(--mut);font-size:12px">MACRO RISK SCORE (0-100)</div>
    <div class="s">{cur_score}</div>
    <div class="w">{band}</div>
    <div class="w" style="margin-top:8px">recommended equity weight: <b style="color:var(--tx)">{cur_w}%</b> &nbsp;/&nbsp; rest in T-bills</div>
  </div>
  <div class="cards">{cards}</div>
</div>

<div class="note b">Honest framing: the CAGR above includes the T-bill carry earned on the de-risked sleeve; net of carry (~{nocarry}% no-carry CAGR) it roughly matches buy &amp; hold. The robust, verified edge is the higher Sharpe and the ~40% shallower max drawdown. Stays ~{inmkt}% invested; it WILL lag the index in prolonged bulls — that give-up is the premium paid for crash protection, banked when the cycle breaks.</div>

<div class="panel"><h2>Growth of $1 — Vector vs buy &amp; hold (log scale)</h2><div id="eqc" class="chart"></div></div>
<div class="panel"><h2>Allocation &amp; macro risk score over time</h2><div id="alc" class="chart"></div></div>
<div class="panel"><h2>Underwater (drawdown) — Vector vs buy &amp; hold</h2><div id="ddc" class="chart"></div></div>

<div class="panel"><h2>Independent bear episodes ({years}yr) — the true sample size</h2>
<table><tr><th>peak</th><th>trough</th><th>S&amp;P drawdown</th></tr>{ep_rows}</table>
<p class="w" style="color:var(--mut);font-size:13px;margin-top:8px">Only ~4 independent &ge;20% bears govern a get-out/get-back-in switch — effective-N, not the day count, bounds confidence. Validated via leave-one-crisis-out + an AQR-style permutation null (real Sharpe &amp; drawdown beat every random-timing shuffle, p=0.0). See reports/spvector-phase3-audit.md.</p></div>

<div class="note r">Taxable-account warning: switching realizes short-term capital gains that buy &amp; hold defers — best run in a tax-advantaged account. The low ~1.5x/yr turnover keeps this manageable.</div>
<p class="w" style="color:var(--mut);font-size:13px">Macro legs (NFCI / recession-prob / Sahm / EBP) are revised FRED series, PIT-lagged per-leg by publication delay; ALFRED point-in-time vintages are the last honesty upgrade. Reports: spvector-baseline / phase1 / phase2 / phase3-audit. Research: research/SP_VECTOR_VIABILITY.md.</p>

<script>
var D=__PAYLOAD__;
var L={{paper_bgcolor:'#161b22',plot_bgcolor:'#161b22',font:{{color:'#8b949e',size:11}},margin:{{l:48,r:16,t:8,b:30}},
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
</script>
</div></body></html>"""


def main() -> int:
    out = build()
    print(f"[built] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
