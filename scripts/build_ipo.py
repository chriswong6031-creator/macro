"""IPO Radar — DISPLAY-ONLY page builder (site/ipo.html).

Renders the honest IPO context page from engine.ipo_radar. The thesis (see
research/IPO_RADAR.md): the day-1 pop is predictable but accrues to the rationed
offer price (uncapturable without allocation), and held from the first close IPOs
underperform — so this is an AVOIDANCE + CONTEXT tool, never a buy signal and never
scored. The page leads with that disclaimer and the aftermarket reality check.

Light by design: it reuses the validated macro de-risk score from
data/regime/spvector_latest.json (written by build_spvector, which runs just before
this in the build_vector hook) rather than rebuilding features — so it costs a
parquet read, the IPO-calendar refresh, and three small relative-strength reads.

Refreshes the Nasdaq IPO calendar (collectors.ipo_calendar) best-effort: if the CI
IP is bot-walled it keeps the committed seed. Writes data/regime/ipo_latest.json
for the landing-hub card. Run: python -m scripts.build_ipo
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from engine import ipo_hk
from engine import ipo_lockup as il
from engine import ipo_radar as ir
from lib import config
from scripts.build_vector import _html, _dx, _plot_y, PLOT, C

# bilingual maps (engine stays language-neutral; the build localises)
BAND_ZH = {"OPEN": "开启", "SHUT": "关闭", "MIXED": "混合", "unknown": "未知"}
BAND_COLOR = {"OPEN": "#1FA971", "MIXED": C["amber"], "SHUT": C["red"], "unknown": C["muted"]}
STATE_ZH = {"constructive": "偏好", "neutral": "中性", "cautious": "谨慎", "hostile": "不利"}
STATE_COLOR = {"constructive": "#1FA971", "neutral": C["muted"], "cautious": C["amber"], "hostile": C["red"]}
LEG_ZH = {
    "Macro risk backdrop": "宏观风险背景",
    "Volatility (VIX)": "波动率（VIX）",
    "Credit appetite (HY vs IG)": "信用偏好（高收益 vs 投资级）",
    "Small-cap leadership (IWM vs SPY)": "小盘领先（IWM vs SPY）",
    "Speculative appetite (high-beta vs low-vol)": "投机偏好（高贝塔 vs 低波）",
    "IPO basket trend (IPO vs SPY)": "新股篮子趋势（IPO vs SPY）",
}
LEG_NOTE_ZH = {
    "validated de-risk score (reused, not new)": "复用已验证的降险评分（非新建）",
    "low vol = receptive tape": "低波动 = 接纳新股的盘面",
    "high-yield leading = risk-on credit": "高收益领先 = 信用风险偏好",
    "small-caps leading = appetite for risk/new names": "小盘领先 = 对风险/新名的偏好",
    "high-beta leading = speculative bid": "高贝塔领先 = 投机性买盘",
    "recent-IPO ETF leading = aftermarket demand": "新股ETF领先 = 二级市场需求",
}
SIZE_ZH = {"mega": "超大型", "large": "大型", "mid": "中型", "small": "小型"}
PACE_ZH = {"busy": "繁忙", "normal": "正常", "quiet": "清淡"}
VERDICT_ZH = {"trails": "跑输", "tracks": "持平", "beats": "跑赢"}
AFTER_COLOR = {"trails": C["red"], "tracks": C["amber"], "beats": "#1FA971"}
# lock-up status → (EN label, ZH label, colour)
LOCK_STATUS = {
    "approaching": ("⚠ approaching", "⚠ 临近解禁", C["amber"]),
    "just-expired": ("📉 overhang active", "📉 解禁压力中", C["red"]),
    "locked": ("🔒 locked", "🔒 锁定中", C["muted"]),
    "expired": ("expired", "已解禁", C["faint"]),
}
# price-revision (partial-adjustment) label → (EN, ZH, colour)
REV_LABEL = {
    "above-range": ("▲ above range", "▲ 高于区间", "#1FA971"),
    "top-half": ("top of range", "区间上沿", "#1FA971"),
    "bottom-half": ("bottom of range", "区间下沿", C["amber"]),
    "below-range": ("▼ below range", "▼ 低于区间", C["red"]),
}
HK_VERDICT_ZH = {"receptive": "接纳", "mixed": "混合", "poor": "低迷", "unavailable": "不可用"}
HK_VERDICT_COLOR = {"receptive": "#1FA971", "mixed": C["amber"], "poor": C["red"], "unavailable": C["muted"]}
HK_LEG_ZH = {
    "Southbound flow (20d net)": "南向资金（20日净额）",
    "Subscription funding (1M HIBOR)": "认购融资成本（1个月 HIBOR）",
    "HKD peg pressure": "港元联系汇率压力",
    "HK risk appetite": "香港风险偏好",
}
HK_NOTE_ZH = ("仅为流动性背景 —— 香港在结构上更适合散户参与（公开发售部分＋回拨机制、公开的"
              "超额认购倍数、暗盘），但这些免密钥的一级市场数据目前失效／受阻，故此处是发行环境而非"
              "交易级信号。从不计分。")


def _pct(x, signed=True) -> str:
    if x is None:
        return "—"
    return f"{x * 100:+.1f}%" if signed else f"{x * 100:.1f}%"


def _usd(v) -> str:
    if v is None:
        return "—"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:.0f}M"
    return f"${v:,.0f}"


def _leg_value_disp(leg) -> str:
    v = leg["value"]
    if v is None:
        return "—"
    if leg["key"] == "macro":
        return f"{int(v)}/100"
    if leg["key"] == "vix":
        return f"{v}"
    return f"{v:+.1f}%"   # relative-strength legs


def _risk_score_from_spvector() -> float | None:
    p = config.data_dir() / "regime" / "spvector_latest.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None
    for k in ("risk_score", "score"):
        if d.get(k) is not None:
            return float(d[k])
    return None


def _chart_aftermarket() -> str | None:
    """IPO / FPX / SPY rebased to 100 over the last 5 years — the honest visual."""
    try:
        import pandas as pd
        import plotly.graph_objects as go
        from lib import store

        def cl(t):
            df = store.read("yahoo", t)
            return None if df is None or df.empty or "close" not in df else df["close"].astype(float).dropna()

        spy = cl("SPY")
        if spy is None or spy.empty:
            return None
        start = spy.index[-1] - pd.DateOffset(years=5)
        fig = go.Figure()
        for t, label, color, w in [("SPY", "S&P 500", C["priceln"], 1.5),
                                   ("FPX", "First Trust IPOX-100", C["indigo"], 1.4),
                                   ("IPO", "Renaissance IPO ETF", C["blue"], 1.9)]:
            s = cl(t)
            if s is None:
                continue
            s = s[s.index >= start]
            if s.empty:
                continue
            s = s / float(s.iloc[0]) * 100.0
            fig.add_trace(go.Scatter(x=_dx(s.index), y=_plot_y(s, 1), name=label,
                                     line={"color": color, "width": w}))
        fig.update_yaxes(title_text="Rebased to 100")
        fig.update_layout(**{**PLOT, "height": 340, "margin": {"l": 48, "r": 24, "t": 28, "b": 28}})
        return _html(fig)
    except Exception:  # noqa: BLE001 — chart must never break the page
        return None


def _lockup_vm() -> dict:
    """Lock-up expiry overhang calendar (Phase 2). Confirms exact lock-up days for the
    actionable window via the prospectus (bandwidth-capped), falls back to the 180d
    standard. Never raises."""
    try:
        from collectors.ipo_calendar import load_calendar
        cal = load_calendar()
    except Exception:  # noqa: BLE001
        return {"rows": [], "summary": {}}
    if cal is None or cal.empty:
        return {"rows": [], "summary": {}}
    lk = None
    try:
        from collectors.ipo_prospectus import fetch_lockups, load_lockups
        fetch_lockups(il.actionable_tickers(cal), cap=12)   # confirm the near-window set
        lk = load_lockups()
    except Exception:  # noqa: BLE001
        try:
            from collectors.ipo_prospectus import load_lockups
            lk = load_lockups()
        except Exception:  # noqa: BLE001
            lk = None
    rows = il.lockup_rows(cal, lk)
    # focus on the actionable + near-future window: recently-expired → approaching → soon-locked
    win = [r for r in rows if -il.RECENT_DAYS <= r["days_to"] <= 120][:24]
    out = []
    for r in win:
        dt = r["days_to"]
        sl, slz, col = LOCK_STATUS.get(r["status"], ("", "", C["muted"]))
        out.append({
            "ticker": r["ticker"] or "—", "company": r["company"] or "—",
            "priced_date": r["priced_date"], "expiry_date": r["expiry_date"],
            "days_to": dt,
            "days_en": ("today" if dt == 0 else (f"in {dt}d" if dt > 0 else f"{-dt}d ago")),
            "days_zh": ("今天" if dt == 0 else (f"{dt}天后" if dt > 0 else f"{-dt}天前")),
            "status_en": sl, "status_zh": slz, "color": col,
            "lockup_days": r["lockup_days"],
            "confirmed": r["source"] == "confirmed",
            "size": _usd(r["size_usd"]),
        })
    phase0 = None
    try:
        p = config.data_dir() / "ipo" / "lockup_phase0.json"
        if p.exists():
            phase0 = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        phase0 = None
    return {"rows": out, "summary": il.summary(rows), "phase0": phase0}


def _hk_vm() -> dict:
    """Hong Kong IPO liquidity-backdrop view-model (Phase 3). Display-only."""
    try:
        b = ipo_hk.hk_backdrop()
    except Exception:  # noqa: BLE001
        return {"available": False}
    if not b.get("available"):
        return {"available": False}
    try:
        from engine import i18n
        tr = i18n.tr
    except Exception:  # noqa: BLE001
        def tr(x):
            return x
    legs = []
    for l in b["legs"]:
        v = l["value"]
        if l["key"] == "southbound":
            vdisp = f"{v:+,} {'HK$mn'}"
            vzh = vdisp
        elif l["key"] == "hibor":
            vdisp = f"{v:.2f}%"
            vzh = vdisp
        else:                                   # peg / risk are text values → glossary
            vdisp, vzh = str(v), tr(str(v))
        legs.append({
            "label": l["label"], "label_zh": HK_LEG_ZH.get(l["label"], l["label"]),
            "value": vdisp, "value_zh": vzh,
            "state": l["state"], "state_zh": STATE_ZH.get(l["state"], l["state"]),
            "color": STATE_COLOR.get(l["state"], C["muted"]), "note": l["note"],
        })
    return {"available": True, "verdict": b["verdict"].upper(),
            "verdict_zh": HK_VERDICT_ZH.get(b["verdict"], b["verdict"]),
            "color": HK_VERDICT_COLOR.get(b["verdict"], C["muted"]),
            "legs": legs, "as_of": b.get("as_of"),
            "note": b["note"], "note_zh": HK_NOTE_ZH}


def build() -> str:
    # refresh the calendar (best-effort; keeps the committed seed if CI is walled)
    try:
        from collectors.ipo_calendar import fetch_ipo_calendar
        fetch_ipo_calendar()
    except Exception:  # noqa: BLE001
        pass

    snap = ir.radar_snapshot(risk_score=_risk_score_from_spvector())
    win, after, pipe = snap["window"], snap["aftermarket"], snap["pipeline"]

    # window view-model
    legs = []
    for l in win["legs"]:
        legs.append({
            "label": l["label"], "label_zh": LEG_ZH.get(l["label"], l["label"]),
            "value_disp": _leg_value_disp(l),
            "state": l["state"], "state_zh": STATE_ZH.get(l["state"], l["state"]),
            "color": STATE_COLOR.get(l["state"], C["muted"]),
            "note": l["note"], "note_zh": LEG_NOTE_ZH.get(l["note"], l["note"]),
        })
    window = {
        "band": win["band"], "band_zh": BAND_ZH.get(win["band"], win["band"]),
        "color": BAND_COLOR.get(win["band"], C["muted"]),
        "constructive": win["constructive"], "hostile": win["hostile"], "n_legs": win["n_legs"],
        "legs": legs,
    }

    # aftermarket view-model
    after_rows = []
    for r in after.get("rows", []):
        after_rows.append({"ticker": r["ticker"], "label": r["label"],
                           "c1": _pct(r.get("1y")), "c3": _pct(r.get("3y")), "c5": _pct(r.get("5y")),
                           "is_ipo": r["ticker"] == "IPO"})
    aftermarket = {
        "rows": after_rows, "verdict": after.get("verdict"),
        "verdict_zh": VERDICT_ZH.get(after.get("verdict"), after.get("verdict")),
        "verdict_color": AFTER_COLOR.get(after.get("verdict"), C["muted"]),
        "ipo_5y": _pct(after.get("ipo_5y")), "spy_5y": _pct(after.get("spy_5y")),
        "gap_5y": (f"{after['gap_5y'] * 100:+.1f}" if after.get("gap_5y") is not None else None),
    }

    # pipeline tiles
    pipeline = dict(pipe)
    if pipe.get("available"):
        pipeline["median_op_size_disp"] = _usd(pipe.get("median_op_size_90d"))
        pipeline["pace_zh"] = PACE_ZH.get(pipe.get("pace"), pipe.get("pace"))

    # recent / upcoming tables
    recent = []
    for r in snap["recent"]:
        rev = r.get("revision")
        rev_en, rev_zh, rev_col = ("—", "—", C["muted"])
        rev_pct = ""
        if rev:
            rev_en, rev_zh, rev_col = REV_LABEL.get(rev["label"], ("—", "—", C["muted"]))
            if rev.get("pct") is not None:
                rev_pct = f" {rev['pct'] * 100:+.0f}%"
        recent.append({
            "ticker": r["ticker"] or "—", "company": r["company"] or "—",
            "exchange": r["exchange"] or "", "offer": _usd(r["offer_price"]).replace("$", "$") if r["offer_price"] else "—",
            "offer_price": (f"${r['offer_price']:.2f}" if r["offer_price"] else "—"),
            "size": _usd(r["size_usd"]), "size_band": r["size_band"],
            "size_band_zh": SIZE_ZH.get(r["size_band"], r["size_band"] or ""),
            "date": r["priced_date"], "days_since": r["days_since"],
            "is_spac": r["is_spac"], "since_offer": _pct(r["since_offer"]),
            "since_color": ("#1FA971" if (r["since_offer"] or 0) > 0 else C["red"]) if r["since_offer"] is not None else C["muted"],
            "rev_en": rev_en, "rev_zh": rev_zh, "rev_col": rev_col, "rev_pct": rev_pct,
            "has_rev": bool(rev),
        })
    upcoming = []
    for r in snap["upcoming"]:
        rng = ("—" if r["range_low"] is None else
               (f"${r['range_low']:.0f}–{r['range_high']:.0f}" if r["range_low"] != r["range_high"]
                else f"${r['range_low']:.0f}"))
        upcoming.append({
            "ticker": r["ticker"] or "—", "company": r["company"] or "—",
            "exchange": r["exchange"] or "", "range": rng,
            "size": _usd(r["size_usd"]), "size_band_zh": SIZE_ZH.get(r["size_band"], r["size_band"] or ""),
            "date": r["expected_date"] or "—", "is_spac": r["is_spac"],
        })

    lockvm = _lockup_vm()

    vm = {
        "as_of": snap.get("as_of") or "—", "built": snap["built"],
        "window": window, "aftermarket": aftermarket, "pipeline": pipeline,
        "recent": recent, "upcoming": upcoming,
        "lockups": lockvm["rows"], "lockup_summary": lockvm["summary"],
        "lockup_phase0": lockvm.get("phase0"),
        "hk": _hk_vm(),
        "chart_aftermarket": _chart_aftermarket(),
    }

    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    html = env.get_template("ipo.html.j2").render(**vm, C=C)
    out = config.ROOT / "site" / "ipo.html"
    out.write_text(html)

    # landing-hub snapshot
    snap_out = {
        "date": snap.get("as_of"),
        "window_band": window["band"],
        "ipo_5y": after.get("ipo_5y"), "spy_5y": after.get("spy_5y"), "gap_5y": after.get("gap_5y"),
        "priced_90d": pipe.get("priced_90d"), "spac_pct_90d": pipe.get("spac_pct_90d"),
        "upcoming_n": pipe.get("upcoming_n"),
        "verdict": after.get("verdict"),
        "lockups_approaching": lockvm["summary"].get("approaching"),
        "lockups_just_expired": lockvm["summary"].get("just_expired"),
        "next_lockup": lockvm["summary"].get("next_ticker"),
        "next_lockup_date": lockvm["summary"].get("next_date"),
        "built": snap["built"],
    }
    snap_dir = config.data_dir() / "regime"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "ipo_latest.json").write_text(json.dumps(snap_out, indent=2))
    return str(out)


def main() -> int:
    out = build()
    print(f"[built] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
