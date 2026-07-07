"""S&P / Macro Vector — US allocation deep-dive page builder.

Renders site/spvector.html (the US equivalent of the Bitcoin vector_allocation
page) from engine.equity_alloc.vector_alloc — the validated de-risk + Fed-put-gated
re-deploy strategy (Phases 0-3, PIT-confirmed). Reached from a card on macro.html,
exactly like the BTC "Allocation strategy" card. House Jinja style; reuses the
build_vector Plotly size-helpers + light palette so it stays light on weight and
consistent with the Bitcoin allocation page.

Honest by design: the strategy is a DRAWDOWN / SHARPE engine, not a CAGR-beater.
The page surfaces the per-leg risk breakdown, the bull-market lag, the carry-vs-
alpha split, the after-tax drag, the bear-episode ledger, and the rule-book.

Also writes data/regime/spvector_latest.json for the landing-hub US "stock/vector"
card. Run: python -m scripts.build_spvector
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from engine import equity_alloc as ea
from engine.validation import backtest_core
from lib import config
from lib.pages import write_page
# Reuse the size-disciplined Plotly helpers + light palette (no edits to build_vector).
from scripts.build_vector import _html, _plot_y, _dx, _plot_idx, _runs, PLOT, C

COST_BPS = 3.0
# SCENARIO ASSUMPTION — not a tax ruling. Symbolic short-term cap-gains rate
# for the after-tax sensitivity section.  Change to run alternative scenarios;
# default 0.35 preserved so existing outputs are unchanged.  (RUL-F3.10)
ST_TAX_SCENARIO = 0.35

LEG_COLORS = {"drawdown": C["red"], "recession": C["amber"], "nfci": C["indigo"],
              "hy_widening": "#D98C00", "liquidity": C["r3"]}
LEG_ZH = {"drawdown": "宏观压力回撤计", "recession": "衰退风险",
          "nfci": "金融条件（紧且收紧）", "hy_widening": "信用压力（高收益利差走阔）",
          "liquidity": "净流动性收缩"}
LEG_ORDER = ["drawdown", "recession", "hy_widening", "nfci", "liquidity"]


# --------------------------------------------------------------------------- #
# charts
# --------------------------------------------------------------------------- #
def _chart_strategy(spy: pd.Series, alloc: pd.Series, rs_on_spy: pd.Series,
                    eq: pd.Series, bench_label: str = "S&P 500",
                    strat_label: str = "Vector strategy") -> str:
    """SPY price + strategy equity overlay, price panel shaded by allocation
    (green=fully in / amber=trimmed / clear=defensive) with buy/sell markers at
    every allocation change; risk row two-toned at the de-risk midpoint; allocation
    step row. Linear price axis; 1Y/5Y/10Y/All buttons rescale on zoom."""
    d = pd.DataFrame({"close": spy,
                      "alloc": alloc.reindex(spy.index).ffill().fillna(1.0),
                      "risk": rs_on_spy.reindex(spy.index).ffill()}).dropna(subset=["close"])
    eqr = eq.reindex(d.index)
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.5, 0.28, 0.22],
                        vertical_spacing=0.04)
    shade = {1.0: "rgba(34,170,94,0.13)", 0.66: "rgba(245,173,66,0.10)",
             0.33: "rgba(245,173,66,0.20)"}  # 0.0 = clear
    for start, end, lvl in _runs(d["alloc"].round(2)):
        fc = shade.get(round(lvl, 2))
        if fc:
            fig.add_shape(type="rect", xref="x", yref="y domain", x0=start, x1=end,
                          y0=0, y1=1, fillcolor=fc, line_width=0, layer="below")
    pidx = _plot_idx(d.index)
    pxs = _dx(pidx)
    fig.add_trace(go.Scatter(x=pxs, y=_plot_y(d["close"].reindex(pidx), 0), name=bench_label,
                             line={"color": C["priceln"], "width": 1.4}), row=1, col=1)
    scale = d["close"].iloc[0] / eqr.iloc[0]
    sx = eqr * scale
    fig.add_trace(go.Scatter(x=pxs, y=_plot_y(sx.reindex(pidx), 0), name=strat_label,
                             line={"color": C["blue"], "width": 1.8}), row=1, col=1)
    chg = d["alloc"].diff()
    for mask, sym, col, nm, off in [
        (chg > 0, "triangle-up", "#1FA971", "Buy / add", 0.965),
        (chg < 0, "triangle-down", C["red"], "Sell / trim", 1.035),
    ]:
        idx = d.index[mask.fillna(False).to_numpy()]
        if len(idx):
            to = d["alloc"].reindex(idx)
            fr = to - chg.reindex(idx)
            txt = [f"{a:.0%} → {b:.0%}" for a, b in zip(fr, to)]
            fig.add_trace(go.Scatter(
                x=idx, y=d["close"].reindex(idx) * off, mode="markers", name=nm,
                marker={"symbol": sym, "color": col, "size": 7,
                        "line": {"width": 0.5, "color": "#fff"}},
                text=txt, hovertemplate="%{x|%b %d %Y} · " + nm + " %{text}<extra></extra>",
            ), row=1, col=1)
    ri = d["risk"].reindex(pidx)
    fig.add_trace(go.Scatter(x=pxs, y=_plot_y(ri.where(ri < 50), 0), name="Risk (calm)",
                             line={"color": C["blue"], "width": 1.4}, showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=pxs, y=_plot_y(ri.where(ri >= 50), 0), name="Risk (stress)",
                             line={"color": C["red"], "width": 1.4}, showlegend=False), row=2, col=1)
    for thr in (25, 50, 75):
        fig.add_hline(y=thr, line={"color": C["faint"], "width": 1, "dash": "dot"}, row=2, col=1)
    fig.add_trace(go.Scatter(x=pxs, y=_plot_y(d["alloc"].reindex(pidx), 2), name="Equity weight",
                             line={"color": C["indigo"], "width": 1.2, "shape": "hv"},
                             fill="tozeroy", fillcolor="rgba(40,95,255,0.10)",
                             showlegend=False), row=3, col=1)
    now = d.index.max()
    btns, default_xr, default_yr = [], None, None
    for label, dd in [("1Y", 365), ("5Y", 1825), ("10Y", 3650), ("All", None)]:
        x0 = d.index.min() if dd is None else max(d.index.min(), now - pd.Timedelta(days=dd))
        w = (d.index >= x0)
        lo = float(min(d["close"][w].min(), sx[w].min()))
        hi = float(max(d["close"][w].max(), sx[w].max()))
        xr = [x0.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")]
        yr = [lo * 0.92, hi * 1.08]
        btns.append({"label": label, "method": "relayout",
                     "args": [{"xaxis.range": xr, "xaxis2.range": xr,
                               "xaxis3.range": xr, "yaxis.range": yr}]})
        if label == "5Y":
            default_xr, default_yr = xr, yr
    fig.update_yaxes(title_text=bench_label, range=default_yr, row=1, col=1)
    fig.update_xaxes(range=default_xr)
    fig.update_yaxes(title_text="Risk", range=[0, 100], row=2, col=1)
    fig.update_yaxes(title_text="Equity", range=[-0.05, 1.05], row=3, col=1)
    fig.update_layout(
        **{**PLOT, "height": 480, "margin": {"l": 48, "r": 52, "t": 44, "b": 28}},
        updatemenus=[{
            "type": "buttons", "direction": "right", "showactive": True, "active": 1,
            "x": 1, "xanchor": "right", "y": 1.02, "yanchor": "bottom",
            "bgcolor": "rgba(255,255,255,0.7)", "bordercolor": C["grid"],
            "borderwidth": 1, "font": {"size": 10, "color": C["text"]},
            "pad": {"t": 2, "b": 2, "l": 4, "r": 4}, "buttons": btns,
        }],
    )
    return _html(fig)


def _chart_growth(eq: pd.Series, hodl: pd.Series, strat_label: str = "Vector") -> str:
    e, h = eq.iloc[::5], hodl.iloc[::5]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=_dx(e.index), y=_plot_y(e, 2), name=strat_label,
                             line={"color": C["blue"], "width": 2}))
    fig.add_trace(go.Scatter(x=_dx(h.index), y=_plot_y(h, 2), name="Buy & hold",
                             line={"color": C["priceln"], "width": 1.5}))
    fig.update_yaxes(type="log")
    fig.update_layout(**{**PLOT, "height": 300})
    return _html(fig)


def _chart_dd(dd_s: pd.Series, dd_h: pd.Series, strat_label: str = "Vector") -> str:
    s, h = dd_s.iloc[::5], dd_h.iloc[::5]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=_dx(h.index), y=_plot_y(h, 1), name="Buy & hold", fill="tozeroy",
                             line={"color": C["priceln"], "width": 1}, fillcolor="rgba(154,164,178,0.25)"))
    fig.add_trace(go.Scatter(x=_dx(s.index), y=_plot_y(s, 1), name=strat_label, fill="tozeroy",
                             line={"color": C["blue"], "width": 1.5}, fillcolor="rgba(40,95,255,0.12)"))
    fig.update_layout(**{**PLOT, "height": 300})
    return _html(fig)


# --------------------------------------------------------------------------- #
# builder
# --------------------------------------------------------------------------- #
def build() -> str:
    from engine.inputs import build_features
    from engine.conditions import conditions_frame
    from engine.dislocation import master_switch_frame
    from lib import store
    from jinja2 import Environment, FileSystemLoader

    f = build_features(); cf = conditions_frame(f); reg = store.read("regime", "regime_history")
    spy = ea.index_close("SPY"); bills = ea.bill_yield()
    rs = ea.risk_score(f, reg, cf)
    rl = ea.risk_legs(f, reg, cf)
    alloc = ea.vector_alloc(spy, f=f, regime=reg, cf=cf)
    sc = ea.summarize(spy, alloc, "Vector", cash_yield=bills, cost_bps=COST_BPS, bootstrap=True)
    if sc.get("bootstrap"):
        ci = sc["bootstrap"]["sharpe_ci"]
        sc["boot_sharpe_lo"], sc["boot_sharpe_hi"] = ci[0], ci[2]
    at = ea.after_tax(spy, alloc, bills, st_rate=ST_TAX_SCENARIO, cost_bps=COST_BPS)

    bt = backtest_core(spy, alloc, cost_bps=COST_BPS, cash_yield=bills)
    eq = (1 + bt["net"]).cumprod(); hodl = (1 + bt["hold"]).cumprod()
    dd_s = (eq / eq.cummax() - 1) * 100
    dd_h = (hodl / hodl.cummax() - 1) * 100
    rs_on_spy = rs.reindex(spy.index, method="ffill")

    # current reading
    score = round(float(rs_on_spy.dropna().iloc[-1]))
    a = alloc.dropna()
    equity_w = round(float(a.iloc[-1]) * 100)
    cash_w = 100 - equity_w
    asof = spy.index[-1].strftime("%b %d, %Y")

    if score < 25:
        band_key, band_label, band_label_zh, band_color = "low", "LOW — fully invested", "低 — 满仓", "#1FA971"
    elif score < 50:
        band_key, band_label, band_label_zh, band_color = "elevated", "ELEVATED — trim", "偏高 — 减仓", C["amber"]
    elif score < 75:
        band_key, band_label, band_label_zh, band_color = "high", "HIGH — de-risk", "高 — 降险", "#D98C00"
    else:
        band_key, band_label, band_label_zh, band_color = "extreme", "EXTREME — defensive", "极端 — 防守", C["red"]

    # last allocation change
    chg = a.diff()
    sw = chg[chg != 0].dropna()
    last_switch = None
    if len(sw):
        d0 = sw.index[-1]
        last_switch = {"date": d0.strftime("%Y-%m-%d"),
                       "frm": round(float(a.shift(1).loc[d0]) * 100),
                       "to": round(float(a.loc[d0]) * 100)}

    bands = [
        {"label": "Low", "label_zh": "低", "rng": "< 25", "weight": 100, "cur": score < 25},
        {"label": "Elevated", "label_zh": "偏高", "rng": "25–50", "weight": 66, "cur": 25 <= score < 50},
        {"label": "High", "label_zh": "高", "rng": "50–75", "weight": 33, "cur": 50 <= score < 75},
        {"label": "Extreme", "label_zh": "极端", "rng": "≥ 75", "weight": 0, "cur": score >= 75},
    ]
    bi = next(i for i, b in enumerate(bands) if b["cur"])
    if bi < 3:
        nxt = bands[bi + 1]
        next_note = f"Next de-risk: a sustained score above {(25, 50, 75)[bi]} trims equity to {nxt['weight']}%."
        next_note_zh = f"下一步降险：分数持续高于 {(25, 50, 75)[bi]} 时，股票权重降至 {nxt['weight']}%。"
    else:
        next_note = "Fully defensive; a validated capitulation washout (Fed-put present) can re-deploy to fully invested."
        next_note_zh = "完全防守；经验证的投降式恐慌底（美联储看跌在场）可再部署至满仓。"

    # dislocation / capitulation chips
    cap_now = int(cf["capitulation_score"].dropna().iloc[-1]) if "capitulation_score" in cf and cf["capitulation_score"].notna().any() else 0
    put_absent = False
    try:
        pa = master_switch_frame(f)["put_absent"].dropna()
        put_absent = bool(pa.iloc[-1]) if len(pa) else False
    except Exception:  # noqa: BLE001 — never let the chip break the build
        put_absent = False
    if put_absent:
        disloc_verdict, disloc_verdict_zh = "stand aside", "观望"
    elif cap_now >= 2:
        disloc_verdict, disloc_verdict_zh = "buyable washout", "可买入恐慌底"
    else:
        disloc_verdict, disloc_verdict_zh = "calm", "平静"

    # leg breakdown view-model (canonical order, then any extras)
    legs = []
    order = LEG_ORDER + [n for n in rl["legs"] if n not in LEG_ORDER]
    for n in order:
        lg = rl["legs"].get(n)
        if not lg:
            continue
        legs.append({"key": n, "label": lg["label"], "label_zh": LEG_ZH.get(n, lg["label"]),
                     "value": lg["value"], "points": lg["points"], "weight": lg["weight"],
                     "lag": lg["lag"], "active": lg["active"],
                     "color": LEG_COLORS.get(n, C["muted"])})

    episodes = ea.bear_episodes(spy, 0.20)

    # LLM context / knife-veto overlay — firewalled, LIVE-ONLY (never in the backtest):
    # if the engine is taking a buyable-washout redeploy but the LLM reads the shock as a
    # regime break, defer the buy. Off (no DeepSeek key) -> mechanical recommendation stands.
    # Logged forward for future validation. (engine.spvector_overlay; preserved across the merge.)
    #
    # W7 #33 spvector veto fix: `on_stress_day` was always False (default), making
    # context_snapshot() skip event_snapshot() and always use the FOMC digest whose
    # shock_reversible is always 'unknown' → 0 vetoes in 202 log rows. Fix: derive
    # `on_stress_day` from the SAME mechanical capitulation trigger the redeploy leg
    # uses (capitulation_score >= 2: VRP-pctile>0.90 / VIX>30 / COT washout). This is
    # a DEFINED stress flag with a real definition; the LLM veto remains LOG-ONLY
    # (shadow) — it never moves a live weight until the overlay log accrues precision.
    overlay = {"enabled": False}
    try:
        from engine import spvector_overlay as sov
        glide_w = float(ea.glide_path(rs).reindex(spy.index, method="ffill").fillna(1.0).iloc[-1])
        # Determine stress day from the mechanical capitulation_score (same trigger as redeploy)
        _cap_score = cf.get("capitulation_score")
        _is_stress_day = bool(
            _cap_score is not None
            and _cap_score.notna().any()
            and int(_cap_score.dropna().iloc[-1]) >= 2
        )
        overlay = sov.live_overlay(
            glide_w, float(alloc.iloc[-1]),
            snapshot=sov.context_snapshot(on_stress_day=_is_stress_day),
        )
        sov.log_overlay(overlay, asof=spy.index[-1].strftime("%Y-%m-%d"))
    except Exception:  # noqa: BLE001 — advisory overlay must never break the page
        overlay = {"enabled": False}

    charts = {"strategy": _chart_strategy(spy, alloc, rs_on_spy, eq),
              "growth": _chart_growth(eq, hodl), "dd": _chart_dd(dd_s, dd_h)}

    vm = {
        "as_of": asof, "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "price": float(spy.iloc[-1]),
        "score": score, "band_label": band_label, "band_label_zh": band_label_zh,
        "band_key": band_key, "band_color": band_color,
        "equity_w": equity_w, "cash_w": cash_w,
        "last_switch": last_switch, "next_note": next_note, "next_note_zh": next_note_zh,
        "legs": legs,
        "disloc": {"verdict": disloc_verdict, "verdict_zh": disloc_verdict_zh,
                   "put_absent": put_absent, "capitulation": cap_now},
        "sc": sc, "at": at, "bands": bands, "episodes": episodes, "charts": charts,
        "overlay": overlay,
    }

    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001 — i18n absent -> English-only, still builds
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    html = env.get_template("spvector.html.j2").render(**vm, C=C)
    out = config.ROOT / "site" / "spvector.html"
    write_page(out, html)

    # snapshot for the landing-hub US allocation/vector card
    snap = {"date": spy.index[-1].strftime("%Y-%m-%d"), "score": score,
            "band": band_key, "band_label": band_label, "equity_w": equity_w,
            "cash_w": cash_w, "stance": f"{equity_w}% equity",
            "cagr": sc["cagr"], "sharpe": sc["sharpe"], "maxdd": sc["maxdd"],
            # alias keys read by build_vector._spvector_state (hub S&P Vector card)
            "equity_weight": equity_w, "risk_score": score, "asof": spy.index[-1].strftime("%Y-%m-%d")}
    snap_dir = config.data_dir() / "regime"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "spvector_latest.json").write_text(json.dumps(snap, indent=2))
    return str(out)


def main() -> int:
    out = build()
    print(f"[built] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
