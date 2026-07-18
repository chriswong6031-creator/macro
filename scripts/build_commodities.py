"""Build the Commodity Vector dashboard -> site/commodities.html.

Standalone like build_vector.py (shares only the parquet store + theme assets).
Recomputes the commodity signal engine every build for daily freshness, reads the
weekly calibration verdicts (data/commodity/calibration.json) when present, builds a
per-asset + commodity-complex view-model, renders light-theme Plotly charts, fills
templates/commodities.html.j2, and writes data/commodity/latest.json for the hub card.

One page, four-asset selector (gold/silver/oil/copper) + a commodity-complex regime
hero. Every per-signal claim carries its MEASURED calibration verdict (house rule).

Usage: python -m scripts.build_commodities
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_commodities")

# shared Glassnode light palette (same as build_vector for a consistent product)
C = {
    "blue": "#285FFF", "indigo": "#4559DC",
    "r1": "#E2E7FC", "r2": "#B8C6FA", "r3": "#8FA5F6", "r4": "#6888FB", "r5": "#285FFF",
    "ink": "#0B1733", "text": "#344054", "muted": "#6F6F6F", "faint": "#A0A0A0",
    "red": "#D30B0B", "redfill": "#FEB5B5", "amber": "#F5AD42", "green": "#1a7f43",
    "grid": "#EAECF0", "card": "#FFFFFF", "bg": "#F7F8FA", "gold": "#C8A53B",
}
PLOT = dict(
    template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font={"size": 11, "color": C["text"], "family": "Inter, sans-serif"},
    margin={"l": 48, "r": 52, "t": 10, "b": 28},
    legend={"orientation": "h", "y": 1.12, "x": 0},
    xaxis={"gridcolor": C["grid"], "zeroline": False},
    yaxis={"gridcolor": C["grid"], "zeroline": False},
)

# per-asset display metadata
META = {
    "gold":   {"label": "Gold",   "zh": "黄金", "unit": "$/oz",  "color": C["gold"]},
    "silver": {"label": "Silver", "zh": "白银", "unit": "$/oz",  "color": "#9AA4B2"},
    "copper": {"label": "Copper", "zh": "铜",   "unit": "$/lb",  "color": "#B5651D"},
    "oil":    {"label": "Oil · WTI", "zh": "原油", "unit": "$/bbl", "color": "#1F2933"},
}
ORDER = ["gold", "silver", "copper", "oil"]

# Honest, calibration-derived interpretations (en, zh). These are stable facts from
# scripts.calibrate_commodities — they tell the user how to READ each signal per asset.
DRIVER_INTERP = {
    "gold":   ("Contrarian here — when gold's macro backdrop looks supportive it has usually already run.",
               "此处为逆向 — 当黄金宏观背景看似有利时，往往已经上涨。"),
    "silver": ("Context only — silver's macro link is unstable; lean on the gold/silver ratio.",
               "仅作背景 — 白银的宏观联系不稳定；以金银比为准。"),
    "copper": ("Directional — an improving growth + softer-dollar backdrop tends to precede copper gains.",
               "有方向性 — 增长改善与美元走软的背景往往领先铜价上涨。"),
    "oil":    ("CONFIRMED leader — oil's dollar + inflation + growth axis genuinely leads forward returns.",
               "已确认领先 — 原油的美元+通胀+增长轴确实领先未来收益。"),
}
SHOCK_INTERP = {
    "gold":   ("Bids PERSIST — an unexplained bid (e.g. central-bank buying) has historically carried forward (+8%/126d at the high band).",
               "买盘持续 — 无法解释的买盘（如央行购金）历史上会延续（高档 +8%/126天）。"),
    "silver": ("Washouts bounce — a deep negative shock preceded +14%/126d; upside shocks are noisier.",
               "超卖反弹 — 深度负冲击后未来126天 +14%；上行冲击噪声更大。"),
    "copper": ("Context only — an unexplained copper bid has NOT reliably carried forward (high-shock band ~+6%/126d, ~51% hit; fails split-half). Read the driver/positioning instead.",
               "仅作背景 — 无法解释的铜买盘并未可靠延续（高冲击档约 +6%/126天、胜率约51%；未通过前后半段检验）。以驱动/持仓为准。"),
    "oil":    ("Bids FADE — war / supply premia mean-revert (high shock → −4%/126d); washouts bounce (+13%).",
               "买盘消退 — 战争/供给溢价均值回归（高冲击→126天 −4%）；超卖反弹（+13%）。"),
}
TREND_INTERP = {
    "gold":   ("12-month trend works — up-trend preceded +7.8%/126d (75% hit).", "12个月趋势有效 — 上涨趋势后126天 +7.8%（胜率75%）。"),
    "silver": ("12-month trend works directionally for silver.", "12个月趋势对白银有方向性。"),
    "copper": ("12-month trend is weak/unstable for copper — context.", "12个月趋势对铜较弱/不稳 — 仅作背景。"),
    "oil":    ("INVERTED — oil mean-reverts; a 12-month down-trend preceded +11%/126d. Read as contrarian.",
               "反向 — 原油均值回归；12个月下跌趋势后126天 +11%。作逆向解读。"),
}


def _html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"displayModeBar": False, "responsive": True})


# recent-disruptions tilt for the conviction engine's alerts factor (keyword-signed,
# severity-weighted, recency-decayed) -> [-1, 1].
_BULL_KW = ("(up)", "tailwind", "exogenous bid", "→ buy", "buy zone", "bottoming",
            "low_risk", "low risk", "expansion", "intact", "confirmed", "silver cheap",
            "widening", "accumulat", "turned tailwind", "rally")
_BEAR_KW = ("(down)", "headwind", "exogenous pressure", "→ 0%", "high_risk", "high risk",
            "topping", "rolling over", "broken", "silver rich", "narrowing", "→ sell",
            "decline", "fragile", "washout", "crowded long")


def _event_sign(e: dict) -> int:
    h = (str(e.get("headline", "")) + " " + str(e.get("detail", ""))).lower()
    pos = any(k in h for k in _BULL_KW)
    neg = any(k in h for k in _BEAR_KW)
    return 1 if (pos and not neg) else (-1 if (neg and not pos) else 0)


def alert_tilt(events: list, asset: str, asof: pd.Timestamp, days: int = 30) -> float:
    sev_w = {"high": 1.0, "medium": 0.5, "info": 0.15}
    cutoff = asof - pd.Timedelta(days=days)
    num = 0.0
    for e in events:
        if e.get("asset") != asset:
            continue
        ts = pd.Timestamp(e["ts"])
        if ts < cutoff or ts > asof:
            continue
        s = _event_sign(e)
        if not s:
            continue
        decay = math.exp(-(asof - ts).days / (days / 2.0))
        num += s * sev_w.get(e.get("severity"), 0.3) * decay
    return float(math.tanh(num / 2.0))


def _r(v, n=2):
    return round(float(v), n) if v is not None and pd.notna(v) else None


# --------------------------------------------------------------------------- #
# alert timeline (mirrors build_vector._group_timeline)
# --------------------------------------------------------------------------- #
TYPE_LABEL = {"residual_shock": "Shock", "price_shock": "Shock", "risk_regime": "Risk",
              "risk_extreme": "Risk", "driver_shift": "Driver", "trend_flip": "Trend",
              "momentum": "Momentum", "structure": "Structure", "allocation": "Allocation",
              "positioning": "COT", "value": "Value", "complex_regime": "Complex"}
FILTER_OF = {"residual_shock": "shock", "price_shock": "shock", "risk_regime": "risk",
             "risk_extreme": "risk", "driver_shift": "driver", "trend_flip": "driver",
             "allocation": "alloc"}


def _group_timeline(events: list[dict]) -> list[dict]:
    days: dict[str, list] = {}
    for e in events:
        ts = pd.Timestamp(e["ts"])
        e = {**e, "label": TYPE_LABEL.get(e["type"], e["type"]),
             "filter": FILTER_OF.get(e["type"], "other"),
             "asset_label": META.get(e.get("asset"), {}).get("label", e.get("asset", "")),
             "time": ts.strftime("%H:%M UTC") if (ts.hour or ts.minute) else "",
             "daylabel": ts.strftime("%a %b %d")}
        days.setdefault(ts.strftime("%Y-%m-%d"), []).append(e)
    return [{"day": d, "daylabel": evs[0]["daylabel"], "events": evs}
            for d, evs in sorted(days.items(), reverse=True)]


def _tail_years(df: pd.DataFrame, years: float) -> pd.DataFrame:
    cutoff = df.index.max() - pd.Timedelta(days=int(365 * years))
    return df.loc[df.index >= cutoff]


# --- plotly weight helpers (mirror scripts/build_vector.py) ---------------- #
def _plot_idx(index, daily_days: int = 400, weekly_days: int = 1825,
              weekly_step: int = 7, monthly_step: int = 30):
    """Resolution-adaptive index for the heavy full-history overlay charts: daily
    for the last ~400d, ~weekly out to 5y, ~monthly before that. Older points are
    sub-pixel at 5Y/All zoom and the recent window stays full daily, so the line
    is visually identical at every zoom — but ~5x fewer points get serialized
    (plotly emits one full date-string + value array PER trace)."""
    if len(index) == 0:
        return index
    end = index.max()
    d0 = end - pd.Timedelta(days=daily_days)
    w0 = end - pd.Timedelta(days=weekly_days)
    daily = index[index >= d0]
    weekly = index[(index < d0) & (index >= w0)][::weekly_step]
    monthly = index[index < w0][::monthly_step]
    return monthly.union(weekly).union(daily)


def _plot_y(s: pd.Series, n: int):
    """Round a y-series to n places and return a plain Python list (NaN -> null).
    plotly base64-packs numpy float64 arrays at a fixed ~10.7 chars/point whatever
    the value; a rounded text list is smaller and shrinks with fewer decimals.
    n<=0 emits ints."""
    if n <= 0:
        return [None if pd.isna(v) else int(round(float(v))) for v in s]
    return [None if pd.isna(v) else round(float(v), n) for v in s]


def _dx(index):
    """Date-only x strings ('2015-08-17') for a daily DatetimeIndex — plotly's
    default datetime serialization emits the full '...T00:00:00.000' per point PER
    trace, so date strings ~halve every x array while still rendering on a normal
    plotly date axis."""
    return [t.strftime("%Y-%m-%d") for t in index]


def _pdec(s) -> int:
    """Decimals giving a price series ~5 significant figures regardless of
    magnitude (copper ~4.5 -> 4dp, gold ~2000 -> 1dp)."""
    a = np.abs(pd.Series(s).to_numpy(dtype="float64"))
    a = a[np.isfinite(a) & (a > 0)]
    if a.size == 0:
        return 2
    return max(0, 4 - int(np.floor(np.log10(float(np.median(a))))))


# --------------------------------------------------------------------------- #
# charts
# --------------------------------------------------------------------------- #
def chart_price(df: pd.DataFrame, asset: str, years: float = 6) -> str:
    """Price (log) + Risk Index area (right axis) + shock markers. Shows the
    risk gauge and the residual-shock episodes against price."""
    d = _tail_years(df, years)
    meta = META[asset]
    # downsample only the heavy full-history line traces; the sparse shock markers
    # below stay full-resolution and exact.
    pidx = _plot_idx(d.index)
    px = _dx(pidx)
    pdec = _pdec(d["close"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=px, y=_plot_y(d["close"].reindex(pidx), pdec), name=meta["label"],
                             line={"color": meta["color"], "width": 1.8}, yaxis="y"))
    if "risk_index" in d:
        fig.add_trace(go.Scatter(x=px, y=_plot_y(d["risk_index"].reindex(pidx), 1), name="Risk Index",
                                 line={"color": C["red"], "width": 0}, fill="tozeroy",
                                 fillcolor="rgba(211,11,11,0.07)", yaxis="y2",
                                 hovertemplate="Risk %{y:.0f}<extra></extra>"))
    if "shock_state" in d:
        bid = d[d["shock_state"] == "exogenous_bid"]
        prs = d[d["shock_state"] == "exogenous_pressure"]
        if len(bid):
            fig.add_trace(go.Scatter(x=_dx(bid.index), y=_plot_y(bid["close"], pdec), mode="markers", name="Exogenous bid",
                                     marker={"color": C["blue"], "size": 5, "symbol": "triangle-up"}, yaxis="y"))
        if len(prs):
            fig.add_trace(go.Scatter(x=_dx(prs.index), y=_plot_y(prs["close"], pdec), mode="markers", name="Exogenous pressure",
                                     marker={"color": C["red"], "size": 5, "symbol": "triangle-down"}, yaxis="y"))
    fig.update_layout(**{**PLOT, "height": 300,
                         "yaxis": {"type": "log", "gridcolor": C["grid"], "title": meta["unit"]},
                         "yaxis2": {"overlaying": "y", "side": "right", "range": [0, 100],
                                    "showgrid": False, "title": "Risk"}})
    return _html(fig)


def chart_complex(results: dict) -> str:
    """Rebased relative performance of the four commodities (last ~2y) — the
    commodity-complex at a glance."""
    fig = go.Figure()
    for a in ORDER:
        s = _tail_years(results[a][["close"]], 2)["close"]
        if s.empty:
            continue
        rb = 100 * s / s.iloc[0]
        pidx = _plot_idx(s.index)
        fig.add_trace(go.Scatter(x=_dx(pidx), y=_plot_y(rb.reindex(pidx), 2), name=META[a]["label"],
                                 line={"color": META[a]["color"], "width": 1.8}))
    fig.add_hline(y=100, line={"color": C["faint"], "width": 1, "dash": "dot"})
    fig.update_layout(**{**PLOT, "height": 300,
                         "yaxis": {"title": "Rebased = 100", "gridcolor": C["grid"]}})
    return _html(fig)


# --------------------------------------------------------------------------- #
# backtest (inline fallback when calibration.json is absent)
# --------------------------------------------------------------------------- #
def backtest(close: pd.Series, alloc: pd.Series) -> dict:
    ret = close.pct_change().fillna(0)
    pos = alloc.shift(1).reindex(ret.index).ffill().fillna(0)
    eq = (1 + pos * ret).cumprod()
    hold = (1 + ret).cumprod()
    yrs = (close.index[-1] - close.index[0]).days / 365.25

    def cagr(e):
        return round(100 * ((e.iloc[-1]) ** (1 / yrs) - 1), 1) if yrs > 0 and e.iloc[-1] > 0 else None

    def shp(r):
        return round(r.mean() / r.std() * np.sqrt(252), 2) if r.std() else None

    def mdd(e):
        return round(100 * float((e / e.cummax() - 1).min()), 1)

    return {"cagr": cagr(eq), "hold_cagr": cagr(hold), "sharpe": shp(pos * ret),
            "hold_sharpe": shp(ret), "maxdd": mdd(eq), "hold_maxdd": mdd(hold),
            "time_in_market": round(100 * (pos > 0).mean(), 1)}


# --------------------------------------------------------------------------- #
# view-model
# --------------------------------------------------------------------------- #
def _oil_supply_read() -> dict | None:
    """EIA Weekly Petroleum Status physical-BALANCE read for the oil page.

    DISPLAY-ONLY context (engine.commodity_supply_context): each inventory is shown as
    a SEASONAL-ANOMALY z (deviation from its 5y same-week-of-year norm — a winter draw
    is normal), plus days-of-supply, Cushing (WTI delivery point) and SPR. Physical
    balance is NOT a price-direction signal, so it is neutral-colored and never fed to
    conviction / alerts / latest.json."""
    from lib import store
    from engine import commodity_supply_context as _sc

    def col(name: str) -> pd.Series | None:
        d = store.read("eia", name)
        return None if d is None or d.empty else d.iloc[:, 0]

    def rz(v: float | None) -> float | None:
        return None if v is None else round(v, 2)

    crude = col("crude_stocks")
    if crude is None or _sc.last_value(crude) is None:
        return None
    scfg = config.load()["eia"]["supply"]
    yrs, dosw = scfg.get("seasonal_years", 5), scfg.get("dos_window_weeks", 4)

    cushing, gasoline, distillate = col("cushing_stocks"), col("gasoline_stocks"), col("distillate_stocks")
    zmap = {"crude": _sc.seasonal_z(crude, yrs), "cushing": _sc.seasonal_z(cushing, yrs),
            "gasoline": _sc.seasonal_z(gasoline, yrs), "distillate": _sc.seasonal_z(distillate, yrs)}
    bz = _sc.balance_z(zmap)

    out = {"crude_stocks_mb": round(_sc.last_value(crude) / 1000, 1),
           "crude_z": rz(zmap["crude"]),
           "balance_z": rz(bz), "balance_word": _sc.balance_word(bz),
           "caveat_en": _sc.SUPPLY_CAVEAT["en"], "caveat_zh": _sc.SUPPLY_CAVEAT["zh"]}
    d4 = _sc.delta_4w(crude)
    if d4 is not None:
        out["crude_chg_4w_mb"], out["draw"] = round(d4 / 1000, 1), d4 < 0
    # Cushing — WTI delivery-point stress
    if zmap["cushing"] is not None:
        out["cushing_mb"], out["cushing_z"] = round(_sc.last_value(cushing) / 1000, 1), rz(zmap["cushing"])
    # product inventories (seasonal-z) + product days-of-cover
    if zmap["gasoline"] is not None:
        out["gasoline_z"] = rz(zmap["gasoline"])
    if zmap["distillate"] is not None:
        out["distillate_z"] = rz(zmap["distillate"])
    for k, st, dm in (("days_supply", crude, col("refinery_inputs")),
                      ("gasoline_days", gasoline, col("gasoline_supplied")),
                      ("distillate_days", distillate, col("distillate_supplied"))):
        dos = _sc.days_of_supply(st, dm, dosw)
        if dos is not None:
            out[k] = dos
    # production + refinery throughput
    prod = col("crude_production")
    if prod is not None and _sc.last_value(prod) is not None:
        out["production_mbd"] = round(_sc.last_value(prod) / 1000, 2)
        pc = _sc.delta_4w(prod)
        if pc is not None:
            out["production_chg_4w"] = round(pc / 1000, 2)
    util = col("refinery_util")
    if util is not None and _sc.last_value(util) is not None:
        out["refinery_util"] = round(_sc.last_value(util), 1)
    # SPR 4-week change — government supply add (release) / withdraw (refill)
    spr_d = _sc.delta_4w(col("spr_stocks"))
    if spr_d is not None:
        out["spr_chg_4w_mb"] = round(spr_d / 1000, 1)
    return out


def _carry_read(asset: str) -> dict | None:
    """Roll-yield carry snapshot for an asset (Phase 1 — research/QUANT_FACTOR_EXPANSION.md)."""
    p = config.data_dir() / "commodity_carry" / f"{asset}.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    if df.empty or "roll_yield_ann" not in df.columns:
        return None
    ccfg = config.load()["commodities"]["carry"]
    ry = df["roll_yield_ann"]
    last = float(ry.iloc[-1])
    pct = float(ry.tail(ccfg["pctile_lookback_d"]).rank(pct=True).iloc[-1])
    out = {"roll_ann": round(last * 100, 1),
           "state": "backwardation" if last > ccfg["backwardation_ann"] else "contango",
           "pctile": int(round(pct * 100)),
           "front": round(float(df["front"].iloc[-1]), 2),
           "second": round(float(df["second"].iloc[-1]), 2)}
    # validated honesty layer (scripts/commodity_carry_phase0.py): carry ≠ direction.
    from engine import commodity_carry_context as _cc
    out["caveat_en"], out["caveat_zh"] = _cc.CARRY_CAVEAT["en"], _cc.CARRY_CAVEAT["zh"]
    if asset == "oil":   # deep 38y EIA percentile context (panel otherwise ranks ~18mo)
        deep = _cc.deep_oil_context(out["roll_ann"])
        if deep:
            out["deep"] = deep
    return out


def asset_vm(asset: str, df: pd.DataFrame, calib: dict, drivers: dict | None = None,
             extras: dict | None = None, conv_calib: dict | None = None,
             alert_tilt_val: float | None = None) -> dict:
    last = df.iloc[-1]
    close = df["close"]
    chg = _r(100 * (close.iloc[-1] / close.iloc[-22] - 1), 1)  # ~1-month
    cal_a = calib.get("assets", {}).get(asset, {})
    verdicts = {s: e.get("verdict", "") for s, e in cal_a.get("signals", {}).items()}
    if cal_a.get("risk_drawdown"):
        verdicts["risk_index"] = cal_a["risk_drawdown"].get("verdict", "")
    score = cal_a.get("allocation", {}).get("optimal") or backtest(close, df["alloc_optimal"])

    alloc_pct = int(round(100 * (last.get("alloc_optimal") or 0)))
    risk_on = last.get("risk_regime") == "low_risk"
    vm = {
        "key": asset, "label": META[asset]["label"], "zh": META[asset]["zh"],
        "unit": META[asset]["unit"], "price": _r(close.iloc[-1], 2), "chg": chg,
        # canonical front-month futures symbol so live.js refreshes the price tile
        "sym": {"gold": "GC=F", "silver": "SI=F", "copper": "HG=F", "oil": "CL=F"}.get(asset),
        "alloc_pct": alloc_pct, "market_mode": last.get("market_mode", "—"),
        "risk_on": risk_on, "risk_index": _r(last.get("risk_index"), 0),
        "risk_word": "Calm" if risk_on else "Elevated",
        "cycle_pos": _r(100 * (last.get("cycle_position") or 0), 0),
        "ts_trend": last.get("ts_trend", "—"), "ts_momentum": _r(last.get("ts_momentum"), 2),
        "momentum": _r(last.get("momentum"), 2), "momentum_state": last.get("momentum_state", "—"),
        "structure": _r(last.get("structure"), 2), "structure_state": last.get("structure_state", "—"),
        "driver_score": _r(last.get("driver_score"), 2), "driver_state": last.get("driver_state", "—"),
        "shock_z": _r(last.get("shock_z"), 2), "shock_state": last.get("shock_state", "—"),
        "decoupled": bool(last.get("decoupled")) if pd.notna(last.get("decoupled")) else False,
        "driver_corr": _r(last.get("driver_corr"), 2),
        "pos_pctile": _r(last.get("pos_pctile"), 0), "pos_state": last.get("pos_state", "—"),
        "verdicts": verdicts, "score": score,
        "driver_interp": DRIVER_INTERP[asset], "shock_interp": SHOCK_INTERP[asset],
        "trend_interp": TREND_INTERP[asset],
        "signals": cal_a.get("signals", {}),
        "chart": chart_price(df, asset),
    }
    # asset-specific extras
    if asset in ("gold", "silver") and "gsr_pctile" in df:
        vm["gsr_pctile"] = _r(last.get("gsr_pctile"), 0)
        vm["gsr_state"] = last.get("gsr_state", "—")
    if asset == "oil" and "bw_change" in df:
        vm["bw_change"] = _r(last.get("bw_change"), 2)
        vm["bw_pctile"] = _r(last.get("bw_spread_pctile"), 0)
    cy = _carry_read(asset)
    if cy:
        vm["carry"] = cy
    if asset == "oil":
        sup = _oil_supply_read()
        if sup:
            vm["supply"] = sup

    # --- macro cycle-ladder + multi-timeframe technical confluence -------------
    # Ported from engine.cycles via engine.commodity_mtf — the SAME calibrated
    # daily/weekly cycle + RSI/StochRSI/MACD engine the stock analyzer runs (equity
    # preset). The confluence verdict fuses this asset's measured calibration
    # polarity (oil trend contrarian, gold driver contrarian, ...). The signals
    # frame keeps only close, so feed close as the high series (commodity OHLC is
    # synthesized from close anyway — see commodity_inputs.load_price).
    from engine import commodity_mtf
    mtf_a = commodity_mtf.mtf_ladder(close)
    verdict = commodity_mtf.confluence_verdict(mtf_a, asset, last, cal_a)
    _TF = (("D", "Daily", "日线"), ("3D", "3-Day", "3日"), ("W", "Weekly", "周线"),
           ("2W", "Biweekly", "双周"), ("ME", "Monthly", "月线"))
    mtf_rows = []
    for key, lbl, lbl_zh in _TF:
        s = (mtf_a.get("mtf") or {}).get(key) or {}
        if not s:
            continue
        macd = ("up" if s.get("macd_cross_up") or s.get("macd_curl_up") else
                "down" if s.get("macd_cross_dn") or s.get("macd_curl_dn") else
                "pos" if s.get("macd_pos") else "neg")
        mtf_rows.append({"key": key, "label": lbl, "label_zh": lbl_zh,
                         "rsi14": s.get("rsi14"), "rsi5": s.get("rsi5"),
                         "stoch": s.get("stoch"), "macd": macd,
                         "trend": (verdict.get("per_tf") or {}).get(key, "flat")})
    lad = mtf_a.get("ladder") or {}
    vm["verdict"] = verdict
    vm["mtf_rows"] = mtf_rows
    vm["ladder"] = {
        "summary_line": lad.get("summary_line"), "summary_line_zh": lad.get("summary_line_zh"),
        "regime_line": lad.get("regime_line"), "regime_line_zh": lad.get("regime_line_zh"),
        "next": lad.get("next"), "next_zh": lad.get("next_zh"),
        "entry_text": (lad.get("entry") or {}).get("text"),
        "entry_text_zh": (lad.get("entry") or {}).get("text_zh"),
    }

    # --- forward-looking multi-factor CONVICTION verdict ----------------------
    # Strong Buy/Buy/Hold/Sell/Strong Sell, cycle position + time-to-turn, and a
    # weighted factor breakdown (technicals + macro + carry/risk/liquidity + value
    # + shocks/alerts), every weight a MEASURED forward-return strength.
    if drivers is not None and extras is not None:
        from engine import commodity_conviction
        conv = commodity_conviction.conviction(asset, df, drivers, extras, mtf_a,
                                               alert_tilt_val, conv_calib)
        vm["conviction"] = conv
    # --- technical arming block (Policy-Shock W1-B, display-only) -------------
    # Deterministic per-asset stoch + basing detector. Never feeds scoring.
    from engine import commodity_signals as _cs
    _arm_cfg = config.load()["commodities"]
    vm["arming"] = _cs.technical_arming(df, _arm_cfg)

    # dollar sensitivity (display-only, from the forex Dollar Desk transmission)
    vm["dollar_corr"], vm["dollar_stable"] = None, None
    try:
        from lib import forex_link
        _ck = {"gold": "GC=F", "copper": "HG=F", "oil": "CL=F"}.get(asset)
        _ac = forex_link.asset_corr(_ck) if _ck else None
        if _ac:
            vm["dollar_corr"], vm["dollar_stable"] = _ac["corr"], _ac["stable"]
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    return vm


FAVORED = {
    "Reflation": ["copper", "oil", "silver"],
    "Stagflation": ["gold", "silver"],
    "Goldilocks": ["gold", "copper"],
    "Deflation-scare": ["gold"],
    "Neutral": [],
}

# --------------------------------------------------------------------------- #
# Bilingual label dicts — NEVER emit raw slugs to the page
# --------------------------------------------------------------------------- #
MEMBER_LABELS: dict[str, tuple[str, str]] = {
    "gold":        ("Gold", "黄金"),
    "silver":      ("Silver", "白银"),
    "platinum":    ("Platinum", "铂金"),
    "palladium":   ("Palladium", "钯金"),
    "copper":      ("Copper", "铜"),
    "oil":         ("Oil · WTI", "原油 · WTI"),
    "natgas":      ("Natural Gas", "天然气"),
    "gasoline":    ("Gasoline", "汽油"),
    "heating_oil": ("Heating Oil", "取暖油"),
    "corn":        ("Corn", "玉米"),
    "wheat":       ("Wheat", "小麦"),
    "soybeans":    ("Soybeans", "大豆"),
    "live_cattle": ("Live Cattle", "活牛"),
    "coffee":      ("Coffee", "咖啡"),
    "sugar":       ("Sugar", "白糖"),
    "cocoa":       ("Cocoa", "可可"),
    "cotton":      ("Cotton", "棉花"),
}

MOMENTUM_STATE_LABELS: dict[str, tuple[str, str]] = {
    "bull":    ("Momentum up", "短期动量向上"),
    "bear":    ("Momentum down", "短期动量转弱"),
    "neutral": ("Mixed", "中性"),
}

SHOCK_STATE_LABELS: dict[str, tuple[str, str]] = {
    "exogenous_bid":      ("Unexplained bid", "异常买盘"),
    "exogenous_pressure": ("Unexplained selling", "异常抛压"),
    "washout":            ("Washing out", "洗盘"),
    "blowoff":            ("Blow-off", "喷发"),
    "normal":             ("—", "—"),
}

CYCLE_PHASE_LABELS: dict[str, tuple[str, str]] = {
    "Trough":    ("Cycle low", "周期底部"),
    "Downturn":  ("Rolling over", "见顶回落"),
    "Recovery":  ("Recovering", "复苏中"),
    "Expansion": ("Advancing", "上行"),
    "Peak":      ("Cycle high", "周期顶部"),
}

# Confluence state → plain action phrase (en, zh)
_CONF_STATE_ACTION: dict[str, tuple[str, str]] = {
    "Washout bottom forming":     ("Watch for the turn", "关注底部转势"),
    "Washing out — high risk":    ("Don't catch the knife", "勿接下落飞刀"),
    "Basing — early bottom signs":("Watch — too early to act", "观望，尚早"),
    "Extended — late cycle":      ("Don't chase — watch for a turn", "勿追高，等待拐点"),
    "Blowing off — extended":     ("Take profits, don't add", "减仓，勿追加"),
    "Euphoric top — rolling over":("Take profits — reduce exposure", "获利了结，降低风险"),
    "Neutral":                    ("Watch — not enough signal yet", "观望——信号不足"),
}

# Grid groupings: class → (en_label, zh_label)
_GRID_GROUPS: list[tuple[str, str, str, list[str]]] = [
    ("energy",   "Energy",       "能源",      ["oil", "natgas", "gasoline", "heating_oil"]),
    ("metals",   "Metals",       "金属",      ["gold", "silver", "platinum", "palladium", "copper"]),
    ("grains",   "Grains & Softs","谷物与软商品",
     ["corn", "wheat", "soybeans", "live_cattle", "coffee", "sugar", "cocoa", "cotton"]),
]


def _plain_mom_state(s: str | None) -> tuple[str, str]:
    if not s:
        return ("—", "—")
    return MOMENTUM_STATE_LABELS.get(s, (s, s))


def _plain_shock(s: str | None) -> tuple[str, str]:
    if not s:
        return ("—", "—")
    return SHOCK_STATE_LABELS.get(s, (s, s))


def _plain_cycle(s: str | None) -> tuple[str, str]:
    if not s:
        return ("—", "—")
    return CYCLE_PHASE_LABELS.get(s, (s, s))


def _conf_action(state: str | None) -> tuple[str, str]:
    if not state:
        return ("Watch — not enough signal yet", "观望——信号不足")
    return _CONF_STATE_ACTION.get(state, ("Watch — not enough signal yet", "观望——信号不足"))


def _mtf_grade_plain(grade: str | None) -> tuple[str, str]:
    """Convert MTF grade slug to plain bilingual pair."""
    _map: dict[str, tuple[str, str]] = {
        "TREND-FOLLOW": ("Go with the trend", "顺势而为"),
        "BUY-THE-DIP":  ("Dip is buyable", "回调可买"),
        "CAUTION":      ("Wait — signals mixed", "等待——信号混乱"),
        "AVOID":        ("Stand aside", "按兵不动"),
        "WAIT":         ("Watch — wait", "观望等待"),
    }
    if not grade:
        return ("Mixed — wait", "混合——等待")
    return _map.get(grade.upper(), (grade, grade))


# --------------------------------------------------------------------------- #
# sector_stance helper
# --------------------------------------------------------------------------- #
def sector_stance(conf: dict, breadth: dict) -> dict:
    """Return the plain-word sector stance for the hero section.

    tone ∈ {act, getready, watch, protect, standaside}
    Rules (in priority order):
      1. Many members Euphoric/Extended → protect
      2. Many Washout bottom-forming     → getready
      3. 12-mo broad but short-term thin (n_bull_momentum/n_members < 0.4) → watch
      4. Broad + strong momentum         → act
      else                               → standaside
    """
    _null = {
        "word_en": "Stand aside", "word_zh": "按兵不动",
        "sub_en":  "Not enough signal to read the complex right now.",
        "sub_zh":  "目前信号不足，无法判断大宗商品整体走势。",
        "tone":    "standaside",
    }
    try:
        members_conf = (conf.get("members") or []) if isinstance(conf, dict) else []
        n_members = max(1, breadth.get("n_members") or 1)
        n_bull = breadth.get("n_bull_momentum") or 0
        n_up = breadth.get("n_up_trend") or 0

        top_states = {"Blowing off — extended", "Extended — late cycle",
                      "Euphoric top — rolling over"}
        bottom_states = {"Washout bottom forming", "Basing — early bottom signs"}

        n_top = sum(1 for m in members_conf if (m.get("state") or "") in top_states)
        n_bot = sum(1 for m in members_conf if (m.get("state") or "") in bottom_states)

        frac_top = n_top / n_members
        frac_bot = n_bot / n_members
        frac_up  = n_up  / n_members
        frac_mom = n_bull / n_members

        if frac_top >= 0.25:
            return {
                "word_en": "Protect gains",  "word_zh": "保护利润",
                "sub_en":  f"{n_top} of {int(n_members)} commodities are stretched or euphoric — trim, don't add.",
                "sub_zh":  f"{int(n_members)}个品种中有{n_top}个处于超买或亢奋状态——减仓，勿追加。",
                "tone":    "protect",
            }
        if frac_bot >= 0.20:
            return {
                "word_en": "Get ready",  "word_zh": "准备就绪",
                "sub_en":  f"{n_bot} of {int(n_members)} commodities are washing out or basing — watch for early turns.",
                "sub_zh":  f"{int(n_members)}个品种中有{n_bot}个正在洗盘或筑底——关注早期转势信号。",
                "tone":    "getready",
            }
        if frac_up >= 0.6 and frac_mom < 0.4:
            return {
                "word_en": "Watch — don't chase",  "word_zh": "观望，勿追高",
                "sub_en":  (f"Long-term trends are broad ({int(n_up)}/{int(n_members)} trending up), "
                            f"but short-term momentum is thin ({int(n_bull)}/{int(n_members)}). "
                            "Not a fresh breakout — late-move divergence."),
                "sub_zh":  (f"长期趋势广泛（{int(n_members)}个中有{int(n_up)}个向上），"
                            f"但短期动量偏弱（{int(n_bull)}/{int(n_members)}）。"
                            "并非新突破——后期走势背离。"),
                "tone":    "watch",
            }
        if frac_up >= 0.5 and frac_mom >= 0.4:
            return {
                "word_en": "Act",  "word_zh": "行动",
                "sub_en":  (f"Broad trend ({int(n_up)}/{int(n_members)} up) with solid momentum "
                            f"({int(n_bull)}/{int(n_members)}) — the complex is in sync."),
                "sub_zh":  (f"趋势广泛（{int(n_up)}/{int(n_members)}向上），"
                            f"动量稳健（{int(n_bull)}/{int(n_members)}）——整体共振。"),
                "tone":    "act",
            }
        return _null
    except Exception:  # noqa: BLE001 — always returns a safe dict
        return _null


# --------------------------------------------------------------------------- #
# build_sector_vm  — the new P4 view model
# --------------------------------------------------------------------------- #
def build_sector_vm(
    index_snap: dict,
    conf: dict,
    _cycle_positions: dict,
    member_results: dict,
    assets: list[dict],
    cfg_com: dict,
) -> dict:
    """Build the full P4 sector view model passed to the template as `vm`.

    Returns a JSON/None-safe dict; never raises.
    """
    try:
        return _build_sector_vm_inner(
            index_snap, conf, _cycle_positions, member_results, assets, cfg_com
        )
    except Exception as e:  # noqa: BLE001
        log.warning("build_sector_vm failed (%s)", e)
        return {}


def _build_sector_vm_inner(
    index_snap: dict,
    conf: dict,
    _cycle_positions: dict,
    member_results: dict,
    assets: list[dict],
    cfg_com: dict,
) -> dict:
    breadth_snap = index_snap.get("breadth") or {}
    idx_snap     = index_snap.get("index") or {}
    members_conf = (conf.get("members") or []) if isinstance(conf, dict) else []

    # --- stance ---------------------------------------------------------------
    stance = sector_stance(conf, breadth_snap)

    # --- breadth block --------------------------------------------------------
    n_members = breadth_snap.get("n_members") or 0
    breadth_vm = {
        "n_up_trend":      breadth_snap.get("n_up_trend") or 0,
        "n_members":       n_members,
        "n_bull_momentum": breadth_snap.get("n_bull_momentum") or 0,
        "n_low_risk":      breadth_snap.get("n_low_risk") or 0,
        "trend_diversity": _r(breadth_snap.get("trend_diversity"), 2),
    }

    # --- index block ----------------------------------------------------------
    grade  = idx_snap.get("mtf", {}).get("grade")
    mtf_plain_en, mtf_plain_zh = _mtf_grade_plain(grade)
    shock_en, shock_zh = _plain_shock(idx_snap.get("shock_state"))
    vel = idx_snap.get("velocity") or {}
    index_vm = {
        "ew":          idx_snap.get("ew"),
        "chg_1m_pct":  idx_snap.get("chg_1m_pct"),
        "ts_trend":    idx_snap.get("ts_trend"),
        "mtf_en":      mtf_plain_en,
        "mtf_zh":      mtf_plain_zh,
        "velocity_20": vel.get("r20"),
        "shock_state": idx_snap.get("shock_state"),
        "shock_en":    shock_en,
        "shock_zh":    shock_zh,
        "benchmarks":  idx_snap.get("benchmarks") or {},
    }

    # --- cycle summary --------------------------------------------------------
    phases: dict[str, list[str]] = {}
    for name, pos_data in _cycle_positions.items():
        if not isinstance(pos_data, dict):
            continue
        phase = pos_data.get("phase")
        if phase:
            phases.setdefault(phase, []).append(name)

    cycle_summary: list[dict] = []
    for phase, names in sorted(phases.items()):
        phase_en, phase_zh = _plain_cycle(phase)
        cycle_summary.append({
            "phase": phase, "phase_en": phase_en, "phase_zh": phase_zh,
            "names_en": [MEMBER_LABELS.get(n, (n.replace("_"," ").title(), n))[0] for n in names],
            "names_zh": [MEMBER_LABELS.get(n, (n.replace("_"," ").title(), n))[1] for n in names],
        })

    # --- board (tops + bottoms) -----------------------------------------------
    top_states   = {"Blowing off — extended", "Extended — late cycle", "Euphoric top — rolling over"}
    bottom_states = {"Washout bottom forming", "Basing — early bottom signs",
                     "Washing out — high risk"}

    def _board_entry(m: dict) -> dict:
        name = m.get("name", "")
        en, zh = MEMBER_LABELS.get(name, (name.replace("_", " ").title(), name))
        state = m.get("state") or "Neutral"
        action_en, action_zh = _conf_action(state)
        # pick the dominant score side
        bot_score = m.get("bottom_score") or 0
        top_score = m.get("top_score") or 0
        score = top_score if state in top_states else bot_score
        # fired receipt — de-slug labels already embedded in commodity_confluence._LABELS
        bottom_fired = m.get("bottom_fired") or []
        top_fired    = m.get("top_fired") or []
        receipt = top_fired if state in top_states else bottom_fired
        return {
            "name":        name,
            "label_en":    en,
            "label_zh":    zh,
            "state":       state,
            "action_en":   action_en,
            "action_zh":   action_zh,
            "score":       _r(score, 0),
            "receipt":     receipt,  # each is {code, label_en, label_zh}
        }

    tops    = sorted(
        [_board_entry(m) for m in members_conf if (m.get("state") or "") in top_states],
        key=lambda x: -(x["score"] or 0)
    )
    bottoms = sorted(
        [_board_entry(m) for m in members_conf if (m.get("state") or "") in bottom_states],
        key=lambda x: -(x["score"] or 0)
    )
    board = {"tops": tops, "bottoms": bottoms}

    # --- heat grid ------------------------------------------------------------
    # Build lookup: name → member_results last-row fields
    mem_lookup: dict[str, dict] = {}
    for name, df in member_results.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        last = df.iloc[-1]
        cl = df["close"].dropna()
        chg = _r(100 * (cl.iloc[-1] / cl.iloc[-23] - 1), 1) if len(cl) >= 23 else None
        mom_state = str(last.get("momentum_state", "") or "")
        shock_st  = str(last.get("shock_state", "") or "")
        cycle_ph  = (_cycle_positions.get(name) or {}).get("phase")
        # tone class for the cell left-border
        if mom_state == "bull":
            tone = "c-up"
        elif shock_st in ("washout", "blowoff"):
            tone = "c-wash"
        elif mom_state == "bear":
            tone = "c-dn"
        else:
            tone = "c-flat"

        mom_en, mom_zh = _plain_mom_state(mom_state if mom_state else None)
        cyc_en, cyc_zh = _plain_cycle(cycle_ph)
        chg_sign = "up" if (chg or 0) >= 0 else "dn"

        mem_lookup[name] = {
            "chg_1m_pct": chg,
            "chg_sign":   chg_sign,
            "tone":       tone,
            "state_short_en": mom_en,
            "state_short_zh": mom_zh,
            "cycle_phase_en": cyc_en,
            "cycle_phase_zh": cyc_zh,
        }

    grid: list[dict] = []
    for grp_key, grp_en, grp_zh, grp_members in _GRID_GROUPS:
        cells: list[dict] = []
        for name in grp_members:
            en, zh = MEMBER_LABELS.get(name, (name.replace("_", " ").title(), name))
            info = mem_lookup.get(name, {})
            cells.append({
                "name":         name,
                "label_en":     en,
                "label_zh":     zh,
                "chg_1m_pct":   info.get("chg_1m_pct"),
                "chg_sign":     info.get("chg_sign", "up"),
                "tone":         info.get("tone", "c-flat"),
                "state_short_en": info.get("state_short_en", "—"),
                "state_short_zh": info.get("state_short_zh", "—"),
                "cycle_phase_en": info.get("cycle_phase_en", "—"),
                "cycle_phase_zh": info.get("cycle_phase_zh", "—"),
            })
        grid.append({
            "group":    grp_key,
            "group_en": grp_en,
            "group_zh": grp_zh,
            "members":  cells,
        })

    # --- detail panels --------------------------------------------------------
    # Build a conf_by_name lookup
    conf_by_name = {m.get("name", ""): m for m in members_conf}
    core4 = {"gold", "silver", "copper", "oil"}
    assets_by_key = {a["key"]: a for a in assets}

    # --- MTF ladder for all 17 members -----------------------------------------
    import time as _time
    from engine import commodity_mtf as _cmtf
    _TF = (("D", "Daily", "日线"), ("3D", "3-Day", "3日"), ("W", "Weekly", "周线"),
           ("2W", "Biweekly", "双周"), ("ME", "Monthly", "月线"))
    _member_mtf: dict[str, dict] = {}
    _t_mtf0 = _time.time()
    for _mname, _mdf in member_results.items():
        if not isinstance(_mdf, pd.DataFrame) or _mdf.empty or "close" not in _mdf.columns:
            continue
        try:
            _close = _mdf["close"].dropna()
            if len(_close) < 20:
                continue
            _mtf_a = _cmtf.mtf_ladder(_close)
            _mtf_rows: list[dict] = []
            for _key, _lbl, _lbl_zh in _TF:
                _s = (_mtf_a.get("mtf") or {}).get(_key) or {}
                if not _s:
                    continue
                _macd = ("up" if _s.get("macd_cross_up") or _s.get("macd_curl_up") else
                         "down" if _s.get("macd_cross_dn") or _s.get("macd_curl_dn") else
                         "pos" if _s.get("macd_pos") else "neg")
                _mtf_rows.append({
                    "key": _key, "label": _lbl, "label_zh": _lbl_zh,
                    "rsi14": _s.get("rsi14"), "rsi5": _s.get("rsi5"),
                    "stoch": _s.get("stoch"), "macd": _macd,
                    "trend": ((_mtf_a.get("ladder") or {}).get("per_tf") or {}).get(_key, "flat"),
                })
            _member_mtf[_mname] = {"mtf_rows": _mtf_rows, "verdict": _cmtf.confluence_verdict(_mtf_a, _mname)}
        except Exception:  # noqa: BLE001 — per-member, never fatal
            pass
    log.info("[timing] member MTF ladder (%d members) in %.1fs",
             len(_member_mtf), _time.time() - _t_mtf0)

    detail: list[dict] = []
    # Iterate over all 17 members in a stable display order
    all_names = [n for _, _, _, ns in _GRID_GROUPS for n in ns]
    for name in all_names:
        en, zh = MEMBER_LABELS.get(name, (name.replace("_", " ").title(), name))
        df = member_results.get(name)
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            detail.append({"name": name, "label_en": en, "label_zh": zh, "available": False})
            continue
        last = df.iloc[-1]
        cl = df["close"].dropna()
        chg = _r(100 * (cl.iloc[-1] / cl.iloc[-23] - 1), 1) if len(cl) >= 23 else None

        # confluence call
        mconf = conf_by_name.get(name, {})
        state = mconf.get("state") or "Neutral"
        action_en, action_zh = _conf_action(state)
        bot_score = mconf.get("bottom_score")
        top_score = mconf.get("top_score")
        bottom_fired = mconf.get("bottom_fired") or []
        top_fired    = mconf.get("top_fired") or []

        # cycle clock
        pos_data = _cycle_positions.get(name) or {}
        cycle_phase = pos_data.get("phase")
        cyc_en, cyc_zh = _plain_cycle(cycle_phase)
        cycle_hazard = bool(pos_data.get("hazard_3m"))

        # shock/driver
        shock_st  = str(last.get("shock_state", "") or "")
        shock_en, shock_zh = _plain_shock(shock_st if shock_st else None)

        # MTF rows: use the pre-computed ladder for all members; fall back to
        # the fully-calibrated asset_vm for core-4 (carries confluence_verdict).
        a_vm = assets_by_key.get(name)
        if a_vm and (a_vm.get("mtf_rows") or []):
            mtf_rows = a_vm.get("mtf_rows", [])
            verdict  = a_vm.get("verdict", {})
        else:
            _mem_mtf_entry = _member_mtf.get(name, {})
            mtf_rows = _mem_mtf_entry.get("mtf_rows", [])
            verdict  = _mem_mtf_entry.get("verdict", {})
        conviction = (a_vm or {}).get("conviction")

        entry: dict = {
            "name":       name,
            "label_en":   en,
            "label_zh":   zh,
            "available":  True,
            "price":      _r(cl.iloc[-1], 2) if len(cl) > 0 else None,
            "chg_1m_pct": chg,
            "action_en":  action_en,
            "action_zh":  action_zh,
            "state":      state,
            "bot_score":  _r(bot_score, 0),
            "top_score":  _r(top_score, 0),
            "bottom_fired": bottom_fired,
            "top_fired":    top_fired,
            "cycle_phase":  cycle_phase,
            "cycle_phase_en": cyc_en,
            "cycle_phase_zh": cyc_zh,
            "cycle_hazard": cycle_hazard,
            "shock_state":  shock_st,
            "shock_en":     shock_en,
            "shock_zh":     shock_zh,
            "mtf_rows":     mtf_rows,
            "verdict":      verdict,
            "is_core4":     name in core4,
        }
        if name in core4 and a_vm:
            entry["conviction"] = conviction
        detail.append(entry)

    return {
        "stance":        stance,
        "breadth":       breadth_vm,
        "index":         index_vm,
        "cycle_summary": cycle_summary,
        "board":         board,
        "grid":          grid,
        "detail":        detail,
    }


def complex_vm(results: dict, calib: dict) -> dict:
    cx = results["_complex"]
    last = cx.iloc[-1]
    regime = last.get("complex_regime", "Neutral")
    return {
        "regime": regime,
        "dollar_dir": "weakening" if last.get("dollar_dir", 0) < 0 else ("strengthening" if last.get("dollar_dir", 0) > 0 else "flat"),
        "growth_dir": "rising" if last.get("growth_dir", 0) > 0 else ("falling" if last.get("growth_dir", 0) < 0 else "flat"),
        "favored": [META[a]["label"] for a in FAVORED.get(regime, [])],
        "gsr": _r(last.get("gold_silver_ratio"), 1) if "gold_silver_ratio" in cx else _r(last.get("gsr"), 1),
        "copper_gold": _r(last.get("copper_gold"), 4),
        "chart": chart_complex(results),
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    from engine import commodity_signals, commodity_inputs, commodity_conviction
    from engine import commodity_alerts
    try:
        inputs = commodity_inputs.load_all()
        results = commodity_signals.compute_all(inputs)
    except Exception as e:  # noqa: BLE001 — never break the site build
        log.error("commodity engine failed (%s); skipping commodities page", e)
        return 0
    drivers = next(iter(inputs.values()))["drivers"] if inputs else {}
    extras = commodity_conviction.load_macro_extras()
    conv_calib = commodity_conviction.load_calibration()
    # roll-yield carry / term structure (Phase 1; weekly-cached, additive)
    try:
        from collectors.commodity_carry import fetch_carry
        fetch_carry()
    except Exception as e:  # noqa: BLE001 — additive, never break the page
        log.warning("commodity carry fetch failed (%s)", e)

    outdir = config.data_dir() / "commodity"
    outdir.mkdir(parents=True, exist_ok=True)
    cpath = outdir / "calibration.json"
    calib = json.loads(cpath.read_text()) if cpath.exists() else {"assets": {}, "meta": {}}

    # alerts rebuilt ONCE — feeds both the conviction disruptions-tilt and the timeline
    acfg = config.load()["commodities"]["alerts"]
    try:
        all_events = commodity_alerts.rebuild(results)
    except Exception as e:  # noqa: BLE001 — optional, never break the page
        log.warning("commodity alerts rebuild failed (%s)", e)
        all_events = commodity_alerts.load_events()
    asof_ts = results["gold"].index.max()
    tilts = {a: alert_tilt(all_events, a, asof_ts) for a in ORDER}

    assets = [asset_vm(a, results[a], calib, drivers, extras, conv_calib, tilts.get(a))
              for a in ORDER if a in results]
    cx = complex_vm(results, calib)

    # --- commodity SECTOR INDEX + breadth / trend-diversity / velocity ---------
    # Display-tier (engine/commodity_index.py). DATA-ONLY this build — the page still
    # renders the core four until the UI revamp; this emits signals_index.parquet +
    # the index/breadth snapshot for the hub + the cycle.html regime bridge. Reuses
    # the already-computed core frames; computes the 13 expansion members once.
    index_snap: dict = {}
    try:
        import time as _time
        from engine import commodity_index
        cfg_com = config.load()["commodities"]
        _t0 = _time.time()
        members_ai = commodity_inputs.load_members(cfg_com)
        member_results = {n: (results[n] if n in results
                              else commodity_signals.compute_asset(ai, cfg_com))
                          for n, ai in members_ai.items()}
        benchmarks = {}
        for _t in cfg_com.get("index", {}).get("benchmarks", []):
            try:
                benchmarks[_t] = commodity_inputs.load_price(_t)["close"].rename(_t)
            except Exception:  # noqa: BLE001 — benchmark optional
                pass
        index_snap = commodity_index.build_index(member_results, benchmarks, cfg_com)
        log.info("[timing] commodity index+breadth (%d members) in %.1fs",
                 len(member_results), _time.time() - _t0)
    except Exception as e:  # noqa: BLE001 — additive, never break the page
        log.warning("commodity index build failed (%s)", e)

    # --- Structural-clock bridge (P3 inbound): cycle → commodity cycle_positions.json ---
    # Writes data/commodity/cycle_positions.json consumed by commodity_confluence below.
    _cycle_positions: dict = {}
    try:
        import time as _time
        from engine import commodity_cycle_state
        _tcc0 = _time.time()
        _cycle_positions = commodity_cycle_state.write_cycle_positions()
        log.info("[timing] commodity cycle_positions (%d members) in %.1fs",
                 len(_cycle_positions), _time.time() - _tcc0)
    except Exception as _cce:  # noqa: BLE001 — additive, never break the page
        log.warning("commodity cycle_positions build failed (%s)", _cce)

    # --- Durable-bottom / Euphoric-top Confluence Organ (display-tier) ---------
    # engine/commodity_confluence.py — deterministic, no scored authority.
    # Emitted to both complex_latest.json and latest.json for hub consumption.
    conf: dict = {}
    _idx_ew_series = None
    try:
        import time as _time
        from engine import commodity_confluence
        _tc0 = _time.time()
        _idx_ew_series = commodity_index.composite_series(member_results, cfg_com).get("idx_ew")
        conf = commodity_confluence.build_confluence(
            member_results,
            cfg_com,
            index_close=_idx_ew_series,
            breadth=index_snap.get("breadth"),
        )
        log.info("[timing] commodity confluence (%d members) in %.1fs",
                 len(member_results), _time.time() - _tc0)
    except Exception as _ce:  # noqa: BLE001 — display-tier, never break the page
        log.warning("commodity confluence build failed (%s)", _ce)

    # Serialize downsampled tail of idx_ew for the sparkline (last ~120 points,
    # rebased to 100). Falls back to None; template drops the spark if absent.
    idx_ew_spark: list[float] | None = None
    try:
        if _idx_ew_series is not None and len(_idx_ew_series.dropna()) >= 10:
            _spark_s = _idx_ew_series.dropna().tail(120)
            _base = float(_spark_s.iloc[0])
            if _base and _base != 0:
                _rebased = (100.0 * _spark_s / _base).round(2)
                idx_ew_spark = [None if pd.isna(v) else float(v) for v in _rebased]
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass

    recent_events = commodity_alerts.recent(all_events, acfg["timeline_days"])
    timeline = _group_timeline(recent_events)

    # Phase 6 (annotation-only, default OFF): upcoming catalysts (keyless, always on)
    # + optional news annotation of the most recent shock events when enabled.
    from engine import commodity_news
    ncfg = config.load().get("commodity_news", {})
    catalysts = commodity_news.upcoming_catalysts(horizon_days=ncfg.get("catalysts_horizon_days", 14))
    news_disclaimer = commodity_news.DISCLAIMER_TEXT
    if commodity_news.enabled():
        annotated = 0
        for day in timeline:
            for e in day["events"]:
                if e["type"] in ("residual_shock", "price_shock") and e.get("asset") in META and annotated < 6:
                    try:  # annotation is best-effort context — never break the page build
                        ann = commodity_news.annotate_event(e["asset"], pd.Timestamp(e["ts"]).date(),
                                                            e.get("headline", ""))
                        if ann and ann.get("headlines"):
                            e["news"] = ann
                    except Exception as ex:  # noqa: BLE001
                        log.warning("news annotation failed for %s (%s)", e.get("asset"), ex)
                    annotated += 1

    as_of = results["gold"].index.max().strftime("%b %d, %Y")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    span = calib.get("meta", {}).get("split", "")
    cal_span = (f"{results['gold'].index.min().date()}..{results['gold'].index.max().date()}")

    # --- P4 sector view model (new 5-section UI) ------------------------------
    try:
        cfg_com = config.load()["commodities"]
        vm = build_sector_vm(index_snap, conf, _cycle_positions, member_results, assets, cfg_com)
    except Exception as _ve:  # noqa: BLE001 — additive, never break the page
        log.warning("build_sector_vm failed (%s)", _ve)
        vm = {}

    # i18n + jinja
    from engine.i18n import tr, td
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td)
    env.filters["money"] = lambda v: ("—" if v is None else f"${v:,.2f}")
    try:
        html = env.get_template("commodities.html.j2").render(
            C=C, as_of=as_of, built=built, cal_span=cal_span, complex=cx,
            assets=assets, order=ORDER, timeline=timeline,
            timeline_days=acfg["timeline_days"], n_alerts=len(recent_events),
            catalysts=catalysts, news_disclaimer=news_disclaimer,
            vm=vm, idx_ew_spark=idx_ew_spark)
    except Exception as _re:  # noqa: BLE001 — never crash the whole site build
        log.error("commodities template render failed (%s); skipping page write", _re)
        return 0
    site = config.ROOT / config.load()["storage"]["site_dir"]
    write_page(site / "commodities.html", html)
    log.info("wrote %s/commodities.html (%d KB)", site, len(html) // 1024)

    # hub latest.json (consumed by build_vector's hub card; runs before build_vector)
    _asof_raw = results["gold"].index.max()
    latest = {"date": as_of, "asof": _asof_raw.strftime("%Y-%m-%d"),
              "regime": cx["regime"], "favored": cx["favored"],
              "index": index_snap.get("index", {}), "breadth": index_snap.get("breadth", {}),
              "confluence": conf,
              "assets": {a["key"]: {"label": a["label"], "price": a["price"], "chg": a["chg"],
                                    "alloc": a["alloc_pct"], "risk": a["risk_word"],
                                    "trend": a["ts_trend"],
                                    "action": (a.get("conviction") or {}).get("action"),
                                    "conviction": (a.get("conviction") or {}).get("score")}
                         for a in assets}}
    # ratios block: copper_gold and gold_silver — reuse series already computed
    # by complex_vm (cx already holds live gsr and copper_gold scalar values,
    # but we need 20d pct-change; read from the underlying results frames directly).
    try:
        def _ratio_block(series_vals: "pd.Series") -> dict:
            """Compute {value, chg_20d_pct, dir} for a ratio series (last row)."""
            s = series_vals.dropna()
            val = float(s.iloc[-1]) if len(s) >= 1 else None
            chg = None
            direction = "flat"
            if val is not None and len(s) >= 21:
                prev = float(s.iloc[-21])
                if prev and prev != 0:
                    chg = round(100.0 * (val - prev) / abs(prev), 2)
                    if chg > 1.0:
                        direction = "up"
                    elif chg < -1.0:
                        direction = "down"
            return {"value": round(val, 4) if val is not None else None,
                    "chg_20d_pct": chg, "dir": direction}

        if "gold" not in results:
            log.warning("commodity ratios block: gold series absent — ratios omitted")
            raise KeyError("gold")
        _gold_close = results["gold"]["close"]
        _silver_close = results["silver"]["close"] if "silver" in results else None
        _copper_close = results["copper"]["close"] if "copper" in results else None

        ratios: dict = {}
        if _copper_close is not None:
            _cg = _copper_close / _gold_close
            ratios["copper_gold"] = _ratio_block(_cg)
        if _silver_close is not None:
            _gs = _gold_close / _silver_close
            ratios["gold_silver"] = _ratio_block(_gs)

        if ratios:
            latest["ratios"] = ratios
    except Exception as _re:  # noqa: BLE001 — fail-open; block is additive
        log.warning("commodity ratios block failed (%s) — omitted from latest.json", _re)

    (outdir / "latest.json").write_text(json.dumps(latest, indent=2, default=str))

    # complex_latest.json — the commodity-complex quadrant + sector index + breadth,
    # consumed by engine/regime_prior.py so the cycle.html disagreement banner can
    # cross-check the commodity read (P3 bridge). Display-tier, additive.
    complex_latest = {"asof": _asof_raw.strftime("%Y-%m-%d"),
                      "complex_regime": cx["regime"],
                      "dollar_dir": cx["dollar_dir"], "growth_dir": cx["growth_dir"],
                      "index": index_snap.get("index", {}),
                      "breadth": index_snap.get("breadth", {}),
                      "members": index_snap.get("members", []),
                      "confluence": conf,
                      "cycle_positions": _cycle_positions}
    (outdir / "complex_latest.json").write_text(json.dumps(complex_latest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
