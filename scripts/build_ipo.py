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
from lib.pages import write_page
from scripts.build_vector import C

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
# plain-word EN for the "what changed" chips (avoid the raw slug in user text)
VERDICT_ZH_EN = {"trails": "trailing", "tracks": "tracking", "beats": "beating"}
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
# per-HK-leg plain-word ZH notes (engine `note` is EN; the build localises)
HK_LEG_NOTE_ZH = {
    "mainland capital into HK = primary-market fuel": "内地资金流入香港 = 一级市场的燃料",
    "cheap HK$ funding = leveraged retail subscription": "港元融资便宜 = 散户杠杆认购活跃",
    "inflow side supports issuance": "资金流入一侧支撑新股发行",
    "risk-on tape welcomes new issues": "风险偏好升温的盘面欢迎新股",
}
# missing-HK-leg plain disclosure (HIBOR is the only leg realistically absent keylessly)
HK_MISSING_NOTE_EN = "Subscription-funding cost unavailable — this read excludes it."
HK_MISSING_NOTE_ZH = "认购融资成本数据缺失 —— 本读数未纳入。"

# ---- plain-word STANCE doctrine (glance-tier "so what do I do") -------------- #
# Act / Get ready / Watch — don't chase / Protect gains / Stand aside / Ignore
STANCE = {
    "act":        ("Act", "出手"),
    "ready":      ("Get ready", "准备"),
    "watch":      ("Watch — don't chase", "观望，别追"),
    "protect":    ("Protect gains", "保护利润"),
    "aside":      ("Stand aside", "靠边站"),
    "ignore":     ("Ignore", "忽略"),
    # panel-specific plain lines within the same doctrine
    "no_chase":   ("Don't chase the basket", "别追新股篮子"),
    "no_lunch":   ("Still no free lunch", "仍非免费午餐"),
    "hot_aside":  ("Stand aside on hot deals", "热门新股靠边站"),
    "normal":     ("Normal issuance", "发行正常"),
}


def _window_stance(band: str) -> tuple[str, str]:
    if band == "SHUT":
        return STANCE["aside"]
    return STANCE["watch"]          # OPEN / MIXED / unknown → watch, don't chase


def _aftermarket_stance(verdict: str | None) -> tuple[str, str]:
    if verdict == "trails":
        return STANCE["no_chase"]
    if verdict == "beats":
        return STANCE["no_lunch"]
    return STANCE["watch"]          # tracks / None


def _pipeline_stance(froth_flags: list) -> tuple[str, str]:
    if "spac" in (froth_flags or []):
        return STANCE["hot_aside"]
    return STANCE["normal"]


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


def _read_prior_snapshot() -> dict | None:
    """The PRIOR ipo_latest.json (read BEFORE this run overwrites it) for the
    'what changed' diff. Fully defensive — None on miss/malformed."""
    try:
        p = config.data_dir() / "regime" / "ipo_latest.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) else None
    except Exception:  # noqa: BLE001
        return None


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
    """IPO / FPX / SPY rebased to 100 over the last 5 years — the honest visual.

    Renders via the house ilx / Signal-Ink SVG format (lib.illus), NOT Plotly: the
    page drops the Plotly head include. Each series is rebased to 100 at its own start
    of the 5y window. Never raises — returns None on any failure (page must render)."""
    try:
        import pandas as pd
        from lib import store
        from lib.illus import illus

        def cl(t):
            df = store.read("yahoo", t)
            return None if df is None or df.empty or "close" not in df else df["close"].astype(float).dropna()

        spy = cl("SPY")
        if spy is None or spy.empty:
            return None
        start = spy.index[-1] - pd.DateOffset(years=5)
        series = []
        # SPY muted, IPO (Renaissance) the highlighted line, FPX (IPOX) the secondary
        for t, le, lz, color in [("SPY", "S&P 500", "标普500", C["priceln"]),
                                 ("IPO", "Renaissance IPO ETF", "文艺复兴新股ETF", C["blue"]),
                                 ("FPX", "First Trust IPOX-100", "IPOX-100", C["indigo"])]:
            s = cl(t)
            if s is None or s.empty:
                continue
            s = s[s.index >= start]
            if s.empty or float(s.iloc[0]) <= 0:
                continue
            s = s / float(s.iloc[0]) * 100.0
            series.append({
                "label_en": le, "label_zh": lz, "color": color,
                "dates": [d.strftime("%Y-%m-%d") for d in s.index],
                "vals": [float(v) for v in s.values],
            })
        if not series:
            return None
        aria_en = ("Five-year total-return paths of the Renaissance IPO ETF, the First "
                   "Trust IPOX-100 and the S&P 500, each rebased to 100 at the start.")
        aria_zh = "文艺复兴新股ETF、First Trust IPOX-100 与标普500 近五年归一至100的走势对比。"
        return illus(series, kind="multi", height=300,
                     unit_en="Rebased to 100", unit_zh="归一至100",
                     aria_en=aria_en, aria_zh=aria_zh)
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
        return {"rows": [], "summary": {}, "raw": []}
    if cal is None or cal.empty:
        return {"rows": [], "summary": {}, "raw": []}
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
    return {"rows": out, "summary": il.summary(rows), "phase0": phase0, "raw": rows}


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
            "color": STATE_COLOR.get(l["state"], C["muted"]),
            "note": l["note"], "note_zh": HK_LEG_NOTE_ZH.get(l["note"], l["note"]),
        })
    st_en, st_zh = _window_stance("OPEN" if b["verdict"] == "receptive"
                                  else "SHUT" if b["verdict"] == "poor" else "MIXED")
    out = {"available": True, "verdict": b["verdict"].upper(),
           "verdict_zh": HK_VERDICT_ZH.get(b["verdict"], b["verdict"]),
           "color": HK_VERDICT_COLOR.get(b["verdict"], C["muted"]),
           "legs": legs, "as_of": b.get("as_of"),
           "n_legs": b.get("n_legs"), "n_expected": b.get("n_expected"),
           "low_confidence": bool(b.get("low_confidence")),
           "missing_legs": b.get("missing_legs") or [],
           "stance_en": st_en, "stance_zh": st_zh,
           "note": b["note"], "note_zh": HK_NOTE_ZH}
    if out["missing_legs"]:
        out["missing_note_en"] = HK_MISSING_NOTE_EN
        out["missing_note_zh"] = HK_MISSING_NOTE_ZH
    return out


# --------------------------------------------------------------------------- #
# glance-tier view-models (hero / avoid / changed / lockup timeline)
# --------------------------------------------------------------------------- #
def _build_hero(win: dict, after: dict, pipe: dict, lk_summary: dict,
                as_of: str | None) -> dict:
    """Top-of-page glance verdict — ≤~32 words, NO citations/jargon/bare-% stats.
    Composed dynamically from band + aftermarket verdict + the next lock-up cliff."""
    band = win.get("band", "unknown")
    bw_en, bw_zh = {
        "OPEN": ("Window open", "窗口开启"), "SHUT": ("Window shut", "窗口关闭"),
        "MIXED": ("Window mixed", "窗口混合"),
    }.get(band, ("Window unclear", "窗口不明"))
    st_en, st_zh = _window_stance(band)

    # opening clause: the issuance window state, in plain words
    if band == "OPEN":
        c_en, c_zh = "The issuance window is open", "新股发行窗口开启"
    elif band == "SHUT":
        c_en, c_zh = "The issuance window is shut", "新股发行窗口关闭"
    elif band == "MIXED":
        c_en, c_zh = "The issuance window is mixed", "新股发行窗口喜忧参半"
    else:
        c_en, c_zh = "The issuance backdrop is unclear", "发行背景尚不明朗"

    parts_en, parts_zh = [c_en], [c_zh]
    verdict = after.get("verdict")
    if verdict == "trails":
        parts_en.append("but new listings bought in the market have lagged the S&P")
        parts_zh.append("但在二级市场买入的新股跑输了标普")
    elif verdict == "beats":
        parts_en.append("and the new-issue basket has kept pace with the market")
        parts_zh.append("且新股篮子与大盘同步")

    # next lock-up cliff (only if genuinely near)
    nd = lk_summary.get("next_days")
    ntk = lk_summary.get("next_ticker")
    if ntk and nd is not None and nd <= 10:
        if nd <= 1:
            parts_en.append("and a big lock-up unlocks this week")
            parts_zh.append("且本周有大额解禁")
        else:
            parts_en.append(f"and a big lock-up unlocks in {nd} days")
            parts_zh.append(f"且 {nd} 天后有大额解禁")

    line_en = " — ".join([parts_en[0], ", ".join(parts_en[1:])]) if len(parts_en) > 1 else parts_en[0]
    line_zh = " —— ".join([parts_zh[0], "，".join(parts_zh[1:])]) if len(parts_zh) > 1 else parts_zh[0]
    line_en = f"{line_en}. {st_en}."
    line_zh = f"{line_zh}。{st_zh}。"

    return {
        "band": band, "band_word_en": bw_en, "band_word_zh": bw_zh,
        "band_color": BAND_COLOR.get(band, C["muted"]),
        "line_en": line_en, "line_zh": line_zh,
        "stance_en": st_en, "stance_zh": st_zh,
        "asof": as_of or "—",
    }


def _build_avoid(after: dict, pipe: dict, lk_summary: dict,
                 as_of: str | None) -> dict:
    """The AVOID panel — deterministic, display-only. Plain-word items, no bare stats
    beyond the honest anchor figures. Falls back to a calm 'nothing urgent' item."""
    items = []
    appr = lk_summary.get("approaching") or 0
    just = lk_summary.get("just_expired") or 0
    nd = lk_summary.get("next_days")
    ntk = lk_summary.get("next_ticker")
    nsize = lk_summary.get("next_size_usd")

    # 1) lock-up cliff
    if (appr + just) > 0:
        tone = "red" if (nd is not None and nd <= 7) else "warn"
        if ntk and lk_summary.get("next_date"):
            when = _lockup_when_en(lk_summary.get("next_date"), nd)
            sz = f" (~{_usd(nsize)})" if nsize else ""
            det_en = f"{ntk} unlocks {when}{sz}; {appr} more within 45 days."
            det_zh = f"{ntk} 于{_lockup_when_zh(lk_summary.get('next_date'), nd)}解禁{('（约' + _usd(nsize) + '）') if nsize else ''}；45 天内还有 {appr} 只。"
        else:
            det_en = f"{appr} names unlock within 45 days; {just} just expired."
            det_zh = f"45 天内有 {appr} 只解禁；{just} 只刚刚解禁。"
        items.append({
            "icon": "🔓",
            "title_en": "Names near un-lock — don't add into the cliff",
            "title_zh": "临近解禁 —— 勿加仓",
            "detail_en": det_en, "detail_zh": det_zh, "tone": tone,
        })

    # 2) aftermarket reality check
    if after.get("verdict") == "trails":
        items.append({
            "icon": "📉",
            "title_en": "Don't chase new-issue baskets",
            "title_zh": "别追新股篮子",
            "detail_en": "Recent-IPO ETF returned about −3%/yr vs the S&P +13%/yr over five years.",
            "detail_zh": "近五年新股ETF年化约 −3%，而标普约 +13%。",
            "tone": "warn",
        })

    # 3) frothy issuance / SPAC share
    flags = pipe.get("froth_flags") or []
    if "spac" in flags:
        spac_pct = pipe.get("spac_pct_90d")
        wr = pipe.get("withdraw_rate_90d")
        det_en = (f"About half of recent deals are blank-check SPACs ({spac_pct}%)"
                  if spac_pct is not None else "A large share of recent deals are blank-check SPACs")
        det_zh = (f"近期约一半新股为空白支票SPAC（{spac_pct}%）"
                  if spac_pct is not None else "近期大量新股为空白支票SPAC")
        if wr is not None:
            det_en += f"; ~{wr}% of filed deals were pulled."
            det_zh += f"；约 {wr}% 的申报交易被撤回。"
        else:
            det_en += "."
            det_zh += "。"
        items.append({
            "icon": "🎈",
            "title_en": "Frothy issuance — stand aside on hot deals",
            "title_zh": "发行泡沫 —— 热门票靠边站",
            "detail_en": det_en, "detail_zh": det_zh, "tone": "warn",
        })

    if not items:
        items.append({
            "icon": "✓",
            "title_en": "Nothing urgent to avoid — watch the calendar.",
            "title_zh": "暂无紧急规避项 —— 关注日历",
            "detail_en": "", "detail_zh": "", "tone": "calm",
        })

    return {"items": items, "asof": as_of or "—"}


def _build_changed(prior: dict | None, win: dict, after: dict, pipe: dict,
                   lk_summary: dict) -> dict:
    """'What changed' strip — diff the PRIOR ipo_latest.json snapshot against the
    current read. Fully defensive: a missing/malformed prior → has_prior False."""
    if not isinstance(prior, dict) or not prior:
        return {"has_prior": False, "items": []}
    items = []
    try:
        # band flip
        pb, cb = prior.get("window_band"), win.get("band")
        if pb and cb and pb != cb:
            tone = "up" if cb == "OPEN" else "down" if cb == "SHUT" else "flat"
            items.append({"en": f"Window flipped {pb} → {cb}",
                          "zh": f"窗口切换 {BAND_ZH.get(pb, pb)} → {BAND_ZH.get(cb, cb)}",
                          "tone": tone})
        # aftermarket verdict flip
        pv, cv = prior.get("verdict"), after.get("verdict")
        if pv and cv and pv != cv:
            tone = "up" if cv == "beats" else "down" if cv == "trails" else "flat"
            items.append({"en": f"Aftermarket read moved {VERDICT_ZH_EN.get(pv, pv)} → {VERDICT_ZH_EN.get(cv, cv)}",
                          "zh": f"二级市场读数变为 {VERDICT_ZH.get(pv, pv)} → {VERDICT_ZH.get(cv, cv)}",
                          "tone": tone})
        # SPAC share crossing 40 (either direction)
        ps, cs = prior.get("spac_pct_90d"), pipe.get("spac_pct_90d")
        if ps is not None and cs is not None and (ps >= 40) != (cs >= 40):
            up = cs >= 40
            items.append({"en": ("SPAC share crossed above 40%" if up else "SPAC share fell below 40%"),
                          "zh": ("SPAC 占比升破 40%" if up else "SPAC 占比回落至 40% 以下"),
                          "tone": "down" if up else "up"})
        # next lock-up ticker change
        pnt, cnt = prior.get("next_lockup"), lk_summary.get("next_ticker")
        if pnt and cnt and pnt != cnt:
            items.append({"en": f"Next lock-up is now {cnt} (was {pnt})",
                          "zh": f"下一解禁现为 {cnt}（此前 {pnt}）", "tone": "flat"})
        # large lockups_approaching delta (±5)
        pa, ca = prior.get("lockups_approaching"), lk_summary.get("approaching")
        if pa is not None and ca is not None and abs(ca - pa) >= 5:
            up = ca > pa
            items.append({"en": f"Lock-ups approaching {'rose' if up else 'fell'} {pa} → {ca}",
                          "zh": f"临近解禁 {'增至' if up else '降至'} {pa} → {ca}",
                          "tone": "down" if up else "up"})
    except Exception:  # noqa: BLE001 — a diff must never break the page
        pass
    return {"has_prior": True, "items": items}


def _build_lockup_timeline(rows: list, lk_summary: dict) -> dict:
    """Data for an inline-SVG lock-up timeline (the template draws the SVG).
    markers = window rows with −30≤days_to≤120 (cap 24); pos_frac normalises the
    120-day forward + 30-day trailing horizon to [0,1]."""
    horizon = 120
    markers = []
    for r in rows:
        dt = r.get("days_to")
        if dt is None or not (-30 <= dt <= horizon):
            continue
        sz = r.get("size_usd")
        try:
            szf = float(sz)
            if szf != szf:      # NaN
                szf = None
        except (TypeError, ValueError):
            szf = None
        bucket = ("sm" if szf is None else
                  "sm" if szf < 1e8 else "md" if szf < 5e8 else "lg")
        pos = (dt + 30) / 150.0
        pos = 0.0 if pos < 0 else 1.0 if pos > 1 else pos
        markers.append({
            "ticker": r.get("ticker") or "—", "company": r.get("company") or "—",
            "expiry_date": r.get("expiry_date"), "days_to": dt,
            "pos_frac": round(pos, 4),
            "size_usd": szf, "size_disp": _usd(szf),
            "size_bucket": bucket, "status": r.get("status"),
            "confirmed": r.get("source") == "confirmed",
        })
        if len(markers) >= 24:
            break
    nxt = None
    if lk_summary.get("next_ticker"):
        nxt = {
            "ticker": lk_summary.get("next_ticker"), "date": lk_summary.get("next_date"),
            "days_to": lk_summary.get("next_days"),
            "size_disp": _usd(lk_summary.get("next_size_usd")),
        }
    return {
        "horizon_days": horizon, "markers": markers, "next": nxt,
        "approaching": lk_summary.get("approaching") or 0,
        "just_expired": lk_summary.get("just_expired") or 0,
        "confirmed": lk_summary.get("confirmed") or 0,
    }


def _lockup_when_en(date_iso: str | None, days: int | None) -> str:
    """Plain 'unlocks <when>' clause: prefers a short month-day, falls back to relative."""
    if date_iso:
        try:
            import pandas as pd
            return pd.to_datetime(date_iso).strftime("%b %-d")
        except Exception:  # noqa: BLE001
            pass
    if days is None:
        return "soon"
    return "today" if days == 0 else (f"in {days} days" if days > 0 else f"{-days} days ago")


def _lockup_when_zh(date_iso: str | None, days: int | None) -> str:
    if date_iso:
        try:
            import pandas as pd
            d = pd.to_datetime(date_iso)
            return f"{d.month}月{d.day}日"
        except Exception:  # noqa: BLE001
            pass
    if days is None:
        return "近期"
    return "今天" if days == 0 else (f"{days}天后" if days > 0 else f"{-days}天前")


def build() -> str:
    # read the PRIOR snapshot BEFORE anything overwrites it (for the 'what changed' strip)
    prior_snap = _read_prior_snapshot()

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
    win_st_en, win_st_zh = _window_stance(win["band"])
    window = {
        "band": win["band"], "band_zh": BAND_ZH.get(win["band"], win["band"]),
        "color": BAND_COLOR.get(win["band"], C["muted"]),
        "constructive": win["constructive"], "hostile": win["hostile"], "n_legs": win["n_legs"],
        # coverage disclosure (item 4h): lets the template print "partial read — N of M inputs"
        "n_expected": win.get("n_expected"), "low_confidence": bool(win.get("low_confidence")),
        "stance_en": win_st_en, "stance_zh": win_st_zh,
        "legs": legs,
    }

    # aftermarket view-model
    after_rows = []
    for r in after.get("rows", []):
        after_rows.append({"ticker": r["ticker"], "label": r["label"],
                           "c1": _pct(r.get("1y")), "c3": _pct(r.get("3y")), "c5": _pct(r.get("5y")),
                           "is_ipo": r["ticker"] == "IPO"})
    after_st_en, after_st_zh = _aftermarket_stance(after.get("verdict"))
    aftermarket = {
        "rows": after_rows, "verdict": after.get("verdict"),
        "verdict_zh": VERDICT_ZH.get(after.get("verdict"), after.get("verdict")),
        "verdict_color": AFTER_COLOR.get(after.get("verdict"), C["muted"]),
        "ipo_5y": _pct(after.get("ipo_5y")), "spy_5y": _pct(after.get("spy_5y")),
        "gap_5y": (f"{after['gap_5y'] * 100:+.1f}" if after.get("gap_5y") is not None else None),
        "stance_en": after_st_en, "stance_zh": after_st_zh,
    }

    # pipeline tiles
    pipeline = dict(pipe)
    pipe_st_en, pipe_st_zh = _pipeline_stance(pipe.get("froth_flags"))
    pipeline["stance_en"], pipeline["stance_zh"] = pipe_st_en, pipe_st_zh
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
    lk_summary = lockvm["summary"]
    as_of = snap.get("as_of")

    # glance-tier view-models (hero verdict, AVOID panel, what-changed strip, timeline)
    hero = _build_hero(win, after, pipe, lk_summary, as_of)
    avoid = _build_avoid(after, pipe, lk_summary, as_of)
    changed = _build_changed(prior_snap, win, after, pipe, lk_summary)
    lockup_timeline = _build_lockup_timeline(lockvm.get("raw") or [], lk_summary)

    # `avoid`/`changed` carry an "items" key. The template accesses that key via SUBSCRIPT
    # (`avoid['items']` / `changed['items']`) precisely so Jinja never resolves `.items` to
    # the built-in dict method — so they stay plain dicts, consistent with every other vm.
    vm = {
        "as_of": as_of or "—", "built": snap["built"],
        "window": window, "aftermarket": aftermarket, "pipeline": pipeline,
        "recent": recent, "upcoming": upcoming,
        "lockups": lockvm["rows"], "lockup_summary": lk_summary,
        "lockup_phase0": lockvm.get("phase0"),
        "lockup_timeline": lockup_timeline,
        "hero": hero,
        "avoid": avoid, "changed": changed,
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
    write_page(out, html)

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
