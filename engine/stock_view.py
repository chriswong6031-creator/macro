"""Unified per-stock **view model** — the single render contract for all 5 markets.

``build_view(rec, market)`` is a THIN, PURE projection over the already-assembled
per-ticker record (US ``site/stockdata/<T>.json`` and the ex-US equivalents). It does
**not** compute any new signal — it reads ``rec["conviction"]`` (the canonical verdict
spine from :mod:`engine.stock_score`) plus the other panels already on ``rec`` and
reshapes them into ONE declarative model the shared ``site/stockview.js`` renders.

Why this exists (research: ``optimized-yawning-wand.md`` §2/§7): the five analyzer
pages each cloned the verdict/conviction renderer and drifted. Routing every page
through one model emitted here makes drift structurally impossible (the layout is a
projection of this dict's field order) and makes the page unable to contradict the
engine. Per-market truth (CN mean-reversion, HK no-alpha, valuation neutrality) flows
through as DATA — labels come from the record, never from template strings.

Contract:
* Output rides **additively** as ``rec["view"]`` — old templates ignore it.
* Every user-facing string carries an ``_zh`` sibling (bilingual, baked at build).
* Everything is present-gated: a missing leg is simply absent, never rendered as a
  neutral placeholder. Degrades to the always-present cycle/ladder spine on a
  close-only record with no conviction block.
* The ONE headline verb is ``conviction.verdict`` — every dissenting read becomes a
  ``falsifier`` (a "what would flip this"), never a second competing verb.
* The Conflict/Neutral state and the per-verdict gloss are computed HERE (engine side)
  and shipped as data, so ``stockview.js`` never re-derives a second opinion.
"""
from __future__ import annotations

from typing import Any

SCHEMA = "stock_view.v1"


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _num(x: Any) -> float | None:
    try:
        v = float(x)
        return None if v != v else v          # NaN guard
    except (TypeError, ValueError):
        return None


def _g(d: Any, *keys: str, default: Any = None) -> Any:
    """Safe nested getter: _g(rec, 'ladder', 'entry', 'tag')."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def _pct_str(v: float | None, dp: int = 0) -> str | None:
    if v is None:
        return None
    return f"{v:+.{dp}f}%"


# ---------------------------------------------------------------------------
# per-verdict plain-English gloss (≤12 words). Keyed on the EXACT verdict string
# emitted by engine.stock_score.verdict() so a test can assert coverage and the
# gloss can never drift into a 5th competing headline. Unknown verdict → ("","").
# ---------------------------------------------------------------------------
_VERDICT_GLOSS: dict[str, tuple[str, str]] = {
    "High-conviction leader":
        ("A validated leader you can own here — the edge cleared the forward-IC gate.",
         "已验证的领先股，可在此持有——优势已通过前瞻 IC 检验。"),
    "High-confluence leader (context)":
        ("A leader on every gauge — context until the forward-edge gate clears; see the Entry gauge for timing.",
         "各项量表均领先——在前瞻优势验证通过前仅作情境；择时请看入场量表。"),
    "Constructive — building a base":
        ("Improving, not yet a leader — building a base.",
         "正在改善但尚未领先——正在筑底。"),
    "Leader · poor entry — wait for a base":
        ("Great company, bad price — wait for a pullback.",
         "好公司但价位不佳——等待回撤。"),
    "Leader · entry unknown — confirm timing":
        ("A leader, but timing data is missing — confirm the entry.",
         "领先股，但缺时机数据——请先确认入场。"),
    "Leader · earnings imminent — wait or size down":
        ("A leader into earnings — a coin-flip event; wait or size down.",
         "领先股临近财报——二元事件；等待或减仓。"),
    "Leader · accounting warning — verify before buying":
        ("Strong tape, weak books — verify the accounting first.",
         "走势强但账目存疑——买入前先核实财务。"),
    "Leader · accounting watch — confirm before adding":
        ("Strong tape, minor accounting flags — confirm before adding.",
         "走势强但财务有瑕疵——加仓前先确认。"),
    "Leader · weak fundamentals — higher-risk":
        ("Strong price, soft fundamentals — higher-risk buy.",
         "价格强但基本面偏弱——风险偏高的买入。"),
    "Extended — don't chase; wait for a pullback":
        ("Ran too far, too fast — don't chase; wait for a dip.",
         "涨得太快太远——勿追高；等待回撤。"),
    "Strong name · wrong tape — wait for a base":
        ("Good company, bad trend — wait for it to bottom.",
         "好公司但趋势不利——等待筑底。"),
    "Strong name · elevated-risk tape — smaller size, confirm":
        ("A leader into a shaky tape — smaller size, confirm first.",
         "领先股但盘面动荡——减小仓位并确认。"),
    "Hold off — timing against you":
        ("Timing is against you right now — stand aside.",
         "当前时机不利——暂时观望。"),
    "Avoid — downtrend":
        ("In a downtrend — avoid until it bottoms.",
         "处于下行趋势——筑底前回避。"),
    "Lagging — relative weakness":
        ("Lagging the market — relative weakness.",
         "跑输大盘——相对弱势。"),
    "Neutral — no clear edge":
        ("No clear edge either way — neutral.",
         "多空均无明显优势——中性。"),
    # ---- shared / CN cycle-anchored verbs (the A-share book leads with the cycle/timing) ----
    "Extended — wait for a pullback":
        ("Ran too far, too fast — wait for a pullback, don't chase.",
         "涨得太快太远——等待回撤，勿追高。"),
    "Downtrend — avoid":
        ("In a downtrend — avoid until it bottoms.",
         "处于下行趋势——筑底前回避。"),
    "Topping — take profits, don't add":
        ("Rolling over off a high — take profits, don't add.",
         "高位见顶回落——止盈，勿加仓。"),
    "Verify accounting before buying":
        ("Accounting flag — verify the books before buying.",
         "财务质量警示——买入前先核实账目。"),
    "Reversal buy — washed out and turning up":
        ("Washed out and turning up — the cycle and the A-share reversal edge agree.",
         "超跌企稳上行——周期与 A 股反转优势一致。"),
    "Buy zone · earnings imminent — wait or size down":
        ("In a buy zone, but earnings are tomorrow — a coin-flip event; wait or size down.",
         "处于买入区，但明日财报——二元事件；等待或减小仓位。"),
    "Buy zone · stressed tape — smaller size, confirm":
        ("In a buy zone, but the tape is stressed (QVIX) — smaller size, confirm first.",
         "处于买入区，但盘面承压（QVIX）——减小仓位并先确认。"),
    "Buy zone — cycle turning up":
        ("The cycle is turning up — a buy zone here; selection is light, so size accordingly.",
         "周期上行——此处为买入区；选股信号偏弱，按此控制仓位。"),
    "Uptrend — hold, add on dips":
        ("In an uptrend — hold and add on dips, don't chase the spike.",
         "处于上行趋势——持有并在回调时加仓，勿追急涨。"),
    "Basing near a low — reversal setting up":
        ("Basing near a low with the reversal edge present — get ready for the turn.",
         "底部区域且具备反转优势——准备迎接拐点。"),
    "Basing near a low — get ready":
        ("Basing near a low — get ready, wait for the turn to confirm.",
         "底部区域——准备就绪，等待拐点确认。"),
    "Countertrend bounce — not a base yet":
        ("A bounce inside a downtrend — not a base yet; don't mistake it for the turn.",
         "下行趋势中的反弹——尚未筑底；勿误判为拐点。"),
    "Reversal candidate — selection edge":
        ("Carries the A-share reversal selection edge — a candidate; confirm timing.",
         "具备 A 股反转选股优势——候选项；请确认时机。"),
    "Ran hot — limited reversal edge":
        ("Already run up — limited mean-reversion edge left (not weakness vs the index).",
         "涨幅已大——均值回归空间有限（并非相对大盘弱势）。"),
    # ---- HK screen verbs (never a "buy") ----
    "Mainland is accumulating — flow screen":
        ("Mainland money is buying it — a flow screen, not a pick.",
         "南向资金正在加仓——资金筛选，非买入建议。"),
    "Cheap H vs its A twin — value screen":
        ("The HK line is cheaper than its mainland twin — value screen.",
         "H 股较其 A 股折价——价值筛选。"),
    "Relative-strength standout — screen, not a validated pick":
        ("Leads on price strength — a screen, not a validated pick.",
         "价格强度突出——筛选项，非已验证买入。"),
    "Well-positioned for the regime — exposure screen":
        ("Fits the current macro regime — an exposure screen.",
         "契合当前宏观环境——敞口筛选。"),
    "Exposure name — context only":
        ("An exposure name — context only, no selection edge.",
         "敞口标的——仅供参考，无选股优势。"),
}


def _gloss(verdict_en: str | None) -> tuple[str, str]:
    if not verdict_en:
        return ("", "")
    return _VERDICT_GLOSS.get(verdict_en, ("", ""))


# ---------------------------------------------------------------------------
# DECISION — the one headline + timing sub-line + size + why + conflict state
# ---------------------------------------------------------------------------
_BULL_LABEL = {
    "entry": ("Good entry point", "入场点良好"),
    "quality": ("Durable fundamentals", "基本面稳健"),
    "tailwind": ("Sector / theme tailwind", "行业／主题顺风"),
}


def _why(conv: dict) -> list[dict]:
    """Bulls — the constructive drivers, plain + bilingual. The first driver is the
    selection-axis KIND string (e.g. 'residual momentum'); the rest are axis names."""
    out: list[dict] = []
    for d in (conv.get("drivers") or []):
        if d in _BULL_LABEL:
            en, zh = _BULL_LABEL[d]
            out.append({"en": en, "zh": zh})
        elif d:                                # a selection-leg kind label
            out.append({"en": f"Leads on {d}", "zh": f"{d}领先"})
    return out


_HIGH_SEV_KEYS = ("accounting", "parabolic", "downtrend", "cycle", "chasing", "追高",
                  "抛物线", "财务", "下行")


def _falsifiers(rec: dict, conv: dict) -> list[dict]:
    """What would flip the thesis — the dissenting reads, collected into ONE list so
    none renders a competing verb. Cautions (already bilingual) lead; dt_contra and
    fragility add numeric payloads so an operator can judge severity."""
    out: list[dict] = []
    caut = conv.get("cautions") or []
    caut_zh = conv.get("cautions_zh") or []
    for i, en in enumerate(caut):
        zh = caut_zh[i] if i < len(caut_zh) else en
        sev = "high" if any(k in (en + zh) for k in _HIGH_SEV_KEYS) else "med"
        out.append({"en": en, "zh": zh, "severity": sev})

    dtc = rec.get("dt_contra") or {}
    dtc_state = dtc.get("state")
    if dtc_state in ("dtc-fade",):
        pct = _num(dtc.get("ext_pctile"))
        tail = f" (top {pct:.0f}% extension)" if pct is not None else ""
        out.append({"en": f"Contrarian fade risk{tail}",
                    "zh": f"逆向回吐风险{('（扩张前' + format(pct, '.0f') + '%）') if pct is not None else ''}",
                    "severity": "med", "payload": {"ext_pctile": pct}})

    frag = rec.get("fragility") or {}
    if frag and not isinstance(frag, dict):
        frag = {"flag": bool(frag)}
    if frag.get("flag") or frag.get("rs_pctile") is not None:
        rs = _num(frag.get("rs_pctile")); dtc_cover = _num(frag.get("days_to_cover"))
        bits = []
        if rs is not None:
            bits.append(f"RS top {rs:.0f}%")
        if dtc_cover is not None:
            bits.append(f"{dtc_cover:.0f}d to cover")
        tail = " · ".join(bits)
        out.append({"en": f"Crowded & fragile — {tail}" if tail else "Crowded & fragile",
                    "zh": f"拥挤且脆弱 — {tail}" if tail else "拥挤且脆弱",
                    "severity": "med",
                    "payload": {"rs_pctile": rs, "days_to_cover": dtc_cover}})
    return out


def _conflict(conv: dict, falsifiers: list[dict]) -> tuple[str, list[dict]]:
    """Engine-emitted page state (NOT derived in JS). 'conflict' = a real edge fights a
    cap (timing/quality/risk); 'neutral' = no clear lean; else 'ok'. Also enforces the
    verb↔size coherence read: a constructive band sized below a quarter is a conflict."""
    band = conv.get("band")
    sel_t = _tier(_g(conv, "axes", "selection", "z"))
    size_pct = _num(_g(conv, "size", "pct"))
    pillars: list[dict] = []
    # which pillars are fighting a positive selection edge
    if sel_t in ("high", "mid"):
        if conv.get("cycle_blocked"):
            pillars.append({"en": "timing", "zh": "时机"})
        flags = _g(conv, "axes", "quality", "flags", default={}) or {}
        if flags.get("accounting") == "warn":
            pillars.append({"en": "accounting", "zh": "财务质量"})
        if _tier(_g(conv, "axes", "quality", "z")) == "low":
            pillars.append({"en": "fundamentals", "zh": "基本面"})
    has_edge = sel_t in ("high", "mid")
    if has_edge and (pillars or (size_pct is not None and size_pct < 25)):
        return "conflict", pillars
    if band in ("neutral", "low", "na"):
        return "neutral", []
    return "ok", pillars


def _tier(z: float | None) -> str:
    if z is None:
        return "na"
    if z >= 1.0:
        return "high"
    if z >= 0.25:
        return "mid"
    if z <= -0.5:
        return "low"
    return "flat"


# The NAME lane (the "what"): the band word reframed so the 0-100 score reads as a
# RANK of name strength, never as a buy-conviction. (The headline verb is the "when".)
_NAME_LABEL = {
    "high":         ("Strong name", "强势个股"),
    "constructive": ("Solid name", "稳健个股"),
    "neutral":      ("Average name", "中等个股"),
    "low":          ("Weak name", "偏弱个股"),
    "na":           ("—", "—"),
}


_AVOID_STATES = {"DECLINE", "ROLLING OVER"}


def _action(conv: dict, rec: dict) -> dict:
    """The ACT-NOW lane (the "when / how much"): one buy-frame verb derived from the
    size + cycle block + band + trust tier. Decoupled from the NAME rank so a strong
    name in a bad tape reads 'Strong name (rank) · WAIT (act)' instead of a green
    'High conviction' badge fighting a 0% size.

    Verb demotion precedence (lower = stronger):
      0. avoid/0% size            → WAIT or AVOID (existing gate)
      1. HK screen tier           → WATCH (existing gate)
      2. hard_down                → AVOID (existing gate)
      3. TRIM ONLY (new B2+B3)    → TRIM ONLY (demotes BUY only; see below)
      4. default                  → BUY

    TRIM ONLY trigger (strictly demotion-only, never escalation):
      extension read is parabolic or stretched (own-history ext grade)
      AND hold state is intact or launched (structure has not broken; W6-C).
      Meaning: "already ran but structure intact — do not add, trim into strength."
      Never fires on a WAIT/AVOID/WATCH path (no escalation possible).
      Source keys: rec["ext"]["grade"] (parabolic|stretched) and
                   rec["hold"]["state"] (intact|launched).
    """
    size = conv.get("size") or {}
    pct = _num(size.get("pct"))
    bucket = size.get("bucket")
    band = conv.get("band")
    blocked = bool(conv.get("cycle_blocked"))
    has_edge = _tier(_g(conv, "axes", "selection", "z")) in ("high", "mid")
    trust = conv.get("trust_tier") or {}
    tier = trust.get("tier") if isinstance(trust, dict) else trust
    no_buy = tier in ("screen",)                          # HK: never a buy verb
    entry = _g(rec, "ladder", "entry", default={}) or {}
    # AVOID (vs a mere WAIT) needs an edge-less name AND a hard-down read: weak band, an
    # explicit avoid tag, or a downtrend cycle — a neutral-band downtrend isn't a 'wait'.
    hard_down = band in ("low", "na") or (not has_edge and (
        entry.get("tag") == "AVOID" or entry.get("urgency") in ("avoid", "exit")
        or _g(rec, "ladder", "state") in _AVOID_STATES))

    def _a(en, zh, tone):
        return {"verb": en, "verb_zh": zh, "tone": tone}

    if bucket == "avoid" or pct == 0 or pct is None:
        if has_edge and blocked:                          # the NVDA case
            return _a("WAIT", "等待", "wait")
        if hard_down:
            return _a("AVOID", "回避", "avoid")
        return _a("WAIT", "等待", "wait")
    if no_buy:
        return _a("WATCH", "观察", "screen")
    if hard_down:
        return _a("AVOID", "回避", "avoid")
    # ── TRIM ONLY (B2+B3): demotion from BUY when already-ran + structure intact ──
    # Source: rec["ext"]["grade"] for extension read; rec["hold"]["state"] for
    # hold/basing state (W6-C tracker).  Both keys may be absent (fail-open: no TRIM).
    # This can ONLY demote BUY — it never escalates a WAIT/AVOID/WATCH verb.
    _ext_grade = _g(rec, "ext", "grade")
    _hold_state = _g(rec, "hold", "state")
    _is_extended = _ext_grade in ("parabolic", "stretched")
    _hold_intact = _hold_state in ("intact", "launched")
    if _is_extended and _hold_intact:
        return _a("TRIM ONLY", "只减仓", "trim")
    return _a("BUY", "买入", "go")


def _conflict_note(state: str, pillars: list[dict]) -> tuple[str | None, str | None]:
    """The one-line BRIDGE that reconciles the two lanes: why a top-ranked name is
    not a buy right now. Renders only in the conflict state."""
    if state != "conflict":
        return None, None
    pe = ", ".join(p["en"] for p in pillars) or "the tape"
    pz = "、".join(p["zh"] for p in pillars) or "盘面"
    return (f"Top board rank, but {pe} blocks a buy now — the rank measures the name, "
            "not the moment.",
            f"板内排名靠前，但{pz}阻碍当前买入——排名衡量个股，而非买入时机。")


def _decision(rec: dict, conv: dict, falsifiers: list[dict]) -> dict:
    lad = rec.get("ladder") or {}
    entry = lad.get("entry") or {}
    size = conv.get("size") or {}
    gloss_en, gloss_zh = _gloss(conv.get("verdict"))
    state, conflict_pillars = _conflict(conv, falsifiers)
    name_en, name_zh = _NAME_LABEL.get(conv.get("band") or "na", _NAME_LABEL["na"])
    cn_en, cn_zh = _conflict_note(state, conflict_pillars)

    timing = {
        "state": lad.get("state"),
        "state_label": lad.get("label") or lad.get("state"),
        "action": lad.get("action"),
        "tag": entry.get("tag"), "tag_zh": entry.get("tag_zh"),
        "urgency": entry.get("urgency"),
        "text": entry.get("text"), "text_zh": entry.get("text_zh"),
        "eq_grade": lad.get("eq_grade"), "eq_badge": lad.get("eq_badge"),
        "eq_dir": lad.get("eq_dir"),
        "bc_score": lad.get("bc_score"), "bc_grade": lad.get("bc_grade"),
        "capped_by_entry": bool(size.get("capped_by_entry")),
    }
    return {
        "headline": conv.get("verdict"), "headline_zh": conv.get("verdict_zh"),
        "gloss": gloss_en, "gloss_zh": gloss_zh,
        "band": conv.get("band"), "band_en": conv.get("band_en"),
        "band_zh": conv.get("band_zh"), "score": conv.get("score"),
        # NAME lane (the "what") — the score reframed as a board RANK of name strength.
        "name_label": name_en, "name_label_zh": name_zh,
        "rank_note": "board rank", "rank_note_zh": "板内排名",
        # ACT-NOW lane (the "when / how much") — one buy-frame verb, decoupled from rank.
        "action": _action(conv, rec),
        "trust": conv.get("trust_tier"), "regime": conv.get("regime"),
        "size": size, "timing": timing,
        "why": _why(conv),
        "state": state, "conflict_pillars": conflict_pillars,
        "conflict_note": cn_en, "conflict_note_zh": cn_zh,
    }


# ---------------------------------------------------------------------------
# FINGERPRINT — the 4 conviction axes, selection labelled by its firing leg
# ---------------------------------------------------------------------------
_AXIS_LABEL = {
    "entry": ("Entry timing", "入场时机"),
    "tailwind": ("Sector / theme", "行业／主题"),
    "quality": ("Quality / durability", "质量／持久性"),
}


def _fingerprint(conv: dict) -> dict:
    ax = conv.get("axes") or {}
    out: list[dict] = []
    sel = ax.get("selection") or {}
    out.append({"key": "selection",
                "label": sel.get("kind") or "edge",
                "label_zh": sel.get("kind_zh") or "优势",
                "pct": sel.get("pct"), "z": sel.get("z"),
                "tier": _g(conv, "trust_tier", "tier")})
    for k in ("entry", "tailwind", "quality"):
        a = ax.get(k) or {}
        en, zh = _AXIS_LABEL[k]
        out.append({"key": k, "label": en, "label_zh": zh,
                    "pct": a.get("pct"), "z": a.get("z"),
                    "flags": a.get("flags") if k == "quality" else None})
    return {"axes": out}


# ---------------------------------------------------------------------------
# EVIDENCE — one read per orthogonal dimension (present-gated). Each: a compact
# chip {label,value,tone,gloss} + an optional `detail` the deep layer expands.
# ---------------------------------------------------------------------------
def _dim(label, label_zh, value, value_zh, tone="neutral", gloss="", gloss_zh="",
         **extra) -> dict:
    d = {"label": label, "label_zh": label_zh, "value": value, "value_zh": value_zh,
         "tone": tone, "gloss": gloss, "gloss_zh": gloss_zh}
    d.update({k: v for k, v in extra.items() if v is not None})
    return d


def _ev_trend(rec: dict) -> dict | None:
    tech = rec.get("tech") or {}
    above = tech.get("above200")
    pv = _num(tech.get("pct_vs_200dma"))
    if above is None and pv is None:
        return None
    up = bool(above) if above is not None else (pv is not None and pv >= 0)
    reg = (_g(rec, "ladder", "regime") or "").lower()
    big = {"bull": ("with-trend", "顺势"), "bear": ("counter-trend", "逆势")}.get(reg)
    val = ("Up" if up else "Down") + (f" · {pv:+.0f}% vs 200-day" if pv is not None else "")
    val_zh = ("上行" if up else "下行") + (f" · 较200日均线 {pv:+.0f}%" if pv is not None else "")
    if big:
        val += f" · {big[0]}"; val_zh += f" · {big[1]}"
    adx = _num(tech.get("adx14"))               # trend STRENGTH (main's richer technicals)
    if adx is not None:
        if adx >= 25:
            val += " · strong"; val_zh += " · 强趋势"
        elif adx < 18:
            val += " · choppy"; val_zh += " · 震荡"
    return _dim("Trend", "趋势", val, val_zh, tone="good" if up else "bad",
                gloss="Where price sits vs its 200-day average, and how strong the trend is (ADX).",
                gloss_zh="价格相对200日均线的位置，以及趋势强度（ADX）。")


def _ev_momentum(rec: dict) -> dict | None:
    mtf = rec.get("mtf") or {}
    parts, parts_zh = [], []
    for k, lab, lab_zh in (("D", "Daily", "日线"), ("3D", "3-Day", "3日"), ("W", "Weekly", "周线")):
        leg = mtf.get(k) or {}
        mp = leg.get("macd_pos")
        if mp is None:
            continue
        arrow = "▲" if mp else "▼"
        parts.append(f"{lab} {arrow}"); parts_zh.append(f"{lab_zh} {arrow}")
    if not parts:
        return None
    ups = sum(1 for p in parts if "▲" in p)
    tone = "good" if ups >= 2 else "bad" if ups == 0 else "neutral"
    return _dim("Momentum", "动量", " · ".join(parts), " · ".join(parts_zh), tone=tone,
                gloss="Trend strength across daily/3-day/weekly clocks.",
                gloss_zh="日线／3日／周线三个周期的动量方向。", expand="mtf")


def _ev_extension(rec: dict) -> dict | None:
    grade = _g(rec, "ext", "grade")
    pv = _num(_g(rec, "tech", "pct_vs_200dma"))
    if grade is None and pv is None:
        return None
    if grade == "parabolic" or (pv is not None and pv >= 30):
        return _dim("Extension", "拉伸", "Parabolic — chase-risk", "抛物线 — 追高风险",
                    tone="bad", gloss="Ran too far above trend — high pullback risk.",
                    gloss_zh="远高于趋势——回撤风险高。")
    if grade == "stretched" or (pv is not None and pv >= 25):
        return _dim("Extension", "拉伸", "Stretched", "拉伸偏高", tone="warn",
                    gloss="Somewhat extended above trend.", gloss_zh="略高于趋势。")
    return _dim("Extension", "拉伸", "In-trend", "趋势内", tone="good",
                gloss="Not over-extended — room within trend.", gloss_zh="未过度拉伸。")


def _ev_rel_strength(rec: dict, market: str) -> dict | None:
    a = rec.get("alpha")
    # the written record carries alpha as a dict {alpha,entry,sector_rank,...}; a
    # normalized rec (unit tests, close-only) may carry a bare float — handle both.
    if isinstance(a, dict):
        az = _num(a.get("alpha")); rank = a.get("sector_rank"); n = a.get("n") or a.get("sector_n")
    else:
        az = _num(a); rank = n = None
    if az is None and rank is None:
        return None
    tone = "good" if (az is not None and az > 0.3) else "bad" if (az is not None and az < -0.3) else "neutral"
    bits, bits_zh = [], []
    if az is not None:
        bits.append(f"alpha z {az:+.2f}"); bits_zh.append(f"阿尔法 z {az:+.2f}")
    if rank is not None and n:
        bits.append(f"#{rank}/{n} in sector"); bits_zh.append(f"行业第 {rank}/{n}")
    # CN reverses: high relative strength is a FADE, not a buy
    g = ("Price strength vs sector — context."
         if market.upper() != "CN" else
         "In A-shares high relative strength tends to FADE, not persist.")
    g_zh = ("相对行业的价格强度——参考。" if market.upper() != "CN"
            else "A股中相对强度高往往回归，而非持续。")
    return _dim("Relative strength", "相对强度", " · ".join(bits), " · ".join(bits_zh),
                tone="neutral" if market.upper() in ("CN", "HK") else tone, gloss=g, gloss_zh=g_zh)


def _ev_valuation(rec: dict, market: str) -> dict | None:
    val = rec.get("valuation") or {}
    vz = _num(val.get("value_z"))
    if vz is None:
        return None
    cheap = vz > 0
    # CN/HK: cheapness is NOT a validated buy → neutral tone, never green
    neutral_mkt = market.upper() in ("CN", "HK")
    tone = "neutral" if neutral_mkt else ("good" if cheap else "warn")
    val_s = ("Cheap vs market" if cheap else "Rich vs market")
    val_zh = ("较大盘便宜" if cheap else "较大盘偏贵")
    g = ("Cheap/rich vs the market — context, not a buy signal."
         if not neutral_mkt else
         "Cheapness alone is not a validated buy in this market.")
    g_zh = ("相对大盘的估值——参考，非买入信号。" if not neutral_mkt
            else "在该市场仅凭便宜并非已验证的买入理由。")
    return _dim("Valuation", "估值", val_s, val_zh, tone=tone, gloss=g, gloss_zh=g_zh)


def _ev_quality(rec: dict, conv: dict) -> dict | None:
    acct = _g(conv, "axes", "quality", "flags", "accounting")
    qz = _num(_g(conv, "axes", "quality", "z"))
    if acct is None and qz is None:
        return None
    if acct == "warn":
        return _dim("Quality", "质量", "Accounting warning", "财务质量警示", tone="bad",
                    gloss="Accounting flags — verify before trusting the numbers.",
                    gloss_zh="财务质量警示——核实后再信赖数据。")
    if acct == "watch":
        return _dim("Quality", "质量", "Accounting watch", "财务质量关注", tone="warn",
                    gloss="Minor accounting flags — keep an eye on them.",
                    gloss_zh="轻微财务瑕疵——留意。")
    t = _tier(qz)
    val, val_zh, tone = (("Durable", "稳健", "good") if t in ("high", "mid")
                         else ("Weak", "偏弱", "bad") if t == "low"
                         else ("Mixed", "中性", "neutral"))
    return _dim("Quality", "质量", val, val_zh, tone=tone,
                gloss="Business durability — will it survive the hold.",
                gloss_zh="业务的持久性——能否撑过持有期。")


def _ev_positioning(rec: dict) -> dict | None:
    pos = rec.get("positioning") or {}
    sh = pos.get("short") or {}
    ins = pos.get("insider") or {}
    bits, bits_zh, tone = [], [], "neutral"
    nb = _num(ins.get("net_mcap_bps"))
    if nb is not None and nb != 0:
        bits.append(f"insider {'buying' if nb > 0 else 'selling'}")
        bits_zh.append(f"内部人{'买入' if nb > 0 else '卖出'}")
        tone = "good" if nb > 0 else "warn"
    sp = _num(sh.get("pct_float"))
    if sp is not None:
        bits.append(f"short {sp:.0f}% float"); bits_zh.append(f"做空 {sp:.0f}% 流通")
        if sp >= 10 and tone == "neutral":
            tone = "warn"
    if not bits:
        return None
    return _dim("Positioning", "持仓", " · ".join(bits), " · ".join(bits_zh), tone=tone,
                gloss="Insider buying (an edge) and short interest (a risk).",
                gloss_zh="内部人买入（优势）与做空比例（风险）。")


def _ev_volatility(rec: dict, conv: dict) -> dict | None:
    ant = rec.get("anticipation") or {}
    hz = (ant.get("horizons") or {}).get("medium") or {}
    if not isinstance(hz, dict):
        hz = {}
    dip = _num(hz.get("dd_avg")) if hz.get("dd_avg") is not None else _num(hz.get("dd_med_pct"))
    worst = _num(hz.get("dd_tail")) if hz.get("dd_tail") is not None else _num(hz.get("dd_p10_pct"))
    size = conv.get("size") or {}
    bits, bits_zh = [], []
    if dip is not None:
        bits.append(f"typical dip {dip:.0f}%"); bits_zh.append(f"常见回撤 {dip:.0f}%")
    if worst is not None:
        bits.append(f"bad-case {worst:.0f}%"); bits_zh.append(f"极端 {worst:.0f}%")
    sp = size.get("pct")
    if sp is not None:
        bits.append(f"→ suggested size {sp}%"); bits_zh.append(f"→ 建议仓位 {sp}%")
    if not bits:
        return None
    return _dim("Risk & size", "风险与仓位", " · ".join(bits), " · ".join(bits_zh),
                tone="neutral",
                gloss="Expected downside drives how big to size.",
                gloss_zh="预期下行决定建议仓位大小。", expand="cone")


# vol-squeeze states (engine/vol_squeeze) → one timing read. A directionally-agnostic
# compression→expansion confirmer that main computes for every market off close-only OHLCV.
_SQUEEZE = {
    "COILED": ("Coiled — compression", "压缩蓄势", "warn"),
    "COMPRESSED": ("Compressing", "压缩中", "neutral"),
    "FIRED_UP": ("Fired ↑ — broke out", "向上突破", "good"),
    "FIRED_DOWN": ("Fired ↓ — broke down", "向下破位", "bad"),
    "EXPANSION": ("Expansion — move underway", "扩张 — 行情进行中", "neutral"),
}


def _ev_squeeze(rec: dict) -> dict | None:
    sq = rec.get("vol_squeeze") or {}
    st = sq.get("state")
    lab = _SQUEEZE.get(st) if st else None
    if not lab:
        return None                                  # NONE / absent → no chip
    en, zh, tone = lab
    days = sq.get("days_compressed")
    if st in ("COILED", "COMPRESSED") and days:
        en += f" {int(days)}d"; zh += f" {int(days)}天"
    if st in ("FIRED_UP", "FIRED_DOWN") and sq.get("volume_confirmed") is False:
        en += " (unconfirmed)"; zh += "（未确认）"
    return _dim("Vol squeeze", "波动压缩", en, zh, tone=tone,
                gloss="Compression → a move is loading; direction unconfirmed until it breaks.",
                gloss_zh="波动压缩——更大行情正在蓄势；突破前方向未定。", expand="cone")


def _ev_ownership(rec: dict) -> dict | None:
    ff = rec.get("fund_flows") or []
    sm = rec.get("smart_money") or {}
    bo = rec.get("beneficial_ownership") or {}
    n_funds = len(ff) if isinstance(ff, list) else 0
    n_hold = sm.get("n_holders")
    if not n_funds and not n_hold and bo.get("signal") != "high":
        return None
    bits, bits_zh = [], []
    if n_funds:
        bits.append(f"{n_funds} active funds"); bits_zh.append(f"{n_funds} 家主动基金")
    if n_hold:
        bits.append(f"{n_hold} 13F holders"); bits_zh.append(f"{n_hold} 家 13F 持有人")
    # multi-quarter "Historical institutional increase/decrease" trend (lagged context)
    tr = sm.get("trend") or {}
    if tr.get("direction") in ("accumulating", "distributing"):
        h0, h1, nq = tr.get("holders_first"), tr.get("holders_last"), tr.get("n_quarters")
        d_en = "accumulating" if tr["direction"] == "accumulating" else "distributing"
        d_zh = "加仓中" if tr["direction"] == "accumulating" else "减仓中"
        bits.append(f"{d_en} ({h0}→{h1} funds, {nq}Q)")
        bits_zh.append(f"{d_zh}（{h0}→{h1} 家，{nq}季）")
    # quality-weighted clustering: how many BACKTEST-SKILLED (A/B-grade) funds are
    # buying — "not all managers are equal" (engine/manager_quality.py, descriptive)
    qc = sm.get("quality_cluster") or {}
    nqb = qc.get("n_quality_buyers")
    if nqb:
        bits.append(f"{nqb} top-grade fund{'s' if nqb != 1 else ''} buying")
        bits_zh.append(f"{nqb} 家高评级基金买入")
    # 13D/G beneficial-ownership regime — only the SIGNAL (activist 13D / 13G→13D
    # flip) surfaces; custodian/index 13G aggregation is filtered out as noise.
    if bo.get("signal") == "high":
        filer = (bo.get("latest_filer") or "").title().strip()
        tag = "13G→13D flip" if bo.get("is_flip") else "activist 13D"
        tag_zh = "13G→13D 转换" if bo.get("is_flip") else "维权 13D"
        bits.append(f"{tag}{f' ({filer})' if filer else ''}")
        bits_zh.append(f"{tag_zh}{f'（{filer}）' if filer else ''}")
    hhi = _num(sm.get("ownership_hhi"))
    if hhi is not None:
        conc = ("top-heavy" if hhi >= 0.18 else "broadly held" if hhi <= 0.08 else "moderate")
        conc_zh = ("高度集中" if hhi >= 0.18 else "分散持有" if hhi <= 0.08 else "中等集中")
        bits.append(conc); bits_zh.append(conc_zh)
    return _dim("Ownership & flow", "持股与资金", " · ".join(bits), " · ".join(bits_zh),
                tone="neutral", gloss="Who owns it and how concentrated; multi-quarter 13F holder trend (lagged ~45d) + how many backtest-skilled funds are buying (descriptive context).",
                gloss_zh="谁在持有、集中度如何；多季度 13F 持有人趋势（滞后约45天）以及有多少回测优质基金在买入（仅供参考）。", expand="ownership")


_DUR_ZH = {"neutral": "中性久期", "long": "长久期", "short": "短久期"}


def _ev_macro(rec: dict) -> dict | None:
    ms = rec.get("macro_sensitivity") or {}
    if not ms:
        return None
    rb = _num(ms.get("rate_beta")); dur = ms.get("duration")
    bits, bits_zh = [], []
    if rb is not None:
        bits.append(f"rate β {rb:+.2f}"); bits_zh.append(f"利率β {rb:+.2f}")
    if dur:
        bits.append(f"{dur}-duration"); bits_zh.append(_DUR_ZH.get(dur, dur))
    if not bits:
        return None
    return _dim("Macro exposure", "宏观敞口", " · ".join(bits), " · ".join(bits_zh),
                tone="neutral",
                gloss="Rate / inflation sensitivity — context, never scored.",
                gloss_zh="利率／通胀敏感度——参考，不计分。", expand="macro")


def _ev_catalyst(rec: dict, conv: dict) -> dict | None:
    earn = rec.get("earnings") or {}
    nd = earn.get("next_date")
    ed = _num(rec.get("earnings_days"))
    basis = _g(conv, "axes", "selection", "basis") or []
    ev_legs = [b for b in basis if b.get("leg") in ("sue", "revision")]
    if nd is None and not ev_legs:
        return None
    bits, bits_zh = [], []
    if nd:
        soon = ed is not None and 0 <= ed <= 8
        bits.append(f"earnings {nd}" + (f" ({int(ed)}d)" if ed is not None and ed >= 0 else ""))
        bits_zh.append(f"财报 {nd}" + (f"（{int(ed)}天）" if ed is not None and ed >= 0 else ""))
    for b in ev_legs:
        bits.append(f"{b.get('label')} {b.get('z'):+.1f}")
        bits_zh.append(f"{b.get('label_zh')} {b.get('z'):+.1f}")
    tone = "warn" if (ed is not None and 0 <= ed <= 3) else "neutral"
    return _dim("Catalyst", "催化", " · ".join(bits), " · ".join(bits_zh), tone=tone,
                gloss="Next earnings date and any earnings/revision edge.",
                gloss_zh="下次财报日期与盈利／评级优势。")


def _evidence(rec: dict, conv: dict, market: str) -> dict:
    ev = {
        "trend": _ev_trend(rec),
        "momentum": _ev_momentum(rec),
        "extension": _ev_extension(rec),
        "rel_strength": _ev_rel_strength(rec, market),
        "valuation": _ev_valuation(rec, market),
        "quality": _ev_quality(rec, conv),
        "positioning": _ev_positioning(rec),
        "squeeze": _ev_squeeze(rec),
        "volatility": _ev_volatility(rec, conv),
        "ownership": _ev_ownership(rec),
        "macro": _ev_macro(rec),
        "catalyst": _ev_catalyst(rec, conv),
    }
    return {k: v for k, v in ev.items() if v is not None}


# ---------------------------------------------------------------------------
# COUNTRY SLOT — a cards[] union. Each card builder is market-agnostic: it fires
# only when its data field is present, so US (none present) yields []. Labels are
# DATA, so a ported template can never carry the wrong country's copy.
# ---------------------------------------------------------------------------
def _card_commodity_beta(rec: dict) -> dict | None:
    fb = rec.get("factor_beta") or {}
    if not fb:
        return None
    rows = []
    for key, en, zh in (("oil", "Oil β", "原油 β"), ("gold", "Gold β", "黄金 β"),
                        ("cad", "FX β", "汇率 β")):
        v = _num(fb.get(key))
        if v is not None:
            rows.append({"k": en, "k_zh": zh, "v": f"{v:+.2f}", "v_zh": f"{v:+.2f}"})
    if not rows:
        return None
    prim = fb.get("primary_label")
    foot = (f"Primary driver: {prim}" if prim else None)
    return {"kind": "commodity_beta", "title": "Commodity / FX exposure",
            "title_zh": "商品／汇率敞口", "rows": rows, "coloring": "neutral",
            "footnote": foot, "footnote_zh": (f"主要驱动：{prim}" if prim else None)}


def _card_val_band(rec: dict) -> dict | None:
    vp = rec.get("val_pctile") or {}
    rows = []
    for key, en, zh in (("pe", "P/E", "市盈率"), ("pb", "P/B", "市净率"), ("ps", "P/S", "市销率")):
        leg = vp.get(key) or {}
        pct = _num(leg.get("pctile"))
        if pct is not None:
            rows.append({"k": en, "k_zh": zh, "v": f"{pct:.0f}%ile",
                         "v_zh": f"第 {pct:.0f} 百分位", "color": "neutral"})
    if not rows:
        return None
    return {"kind": "val_band", "title": "Valuation band · own 5-year range",
            "title_zh": "估值带 · 自身5年区间", "rows": rows, "coloring": "neutral",
            "footnote": "Where it sits in its own history (cheapness ≠ a buy).",
            "footnote_zh": "处于自身历史区间的位置（便宜≠买入）。"}


def _card_margin_fin(rec: dict) -> dict | None:
    pos = rec.get("positioning") or {}
    bal = _num(pos.get("fin_balance_yi"))
    if bal is None:
        return None
    rows = [{"k": "Financing balance", "k_zh": "融资余额",
             "v": f"{bal:.1f} 亿", "v_zh": f"{bal:.1f} 亿"}]
    chg = _num(pos.get("chg_pct"))
    if chg is not None:
        rows.append({"k": "20-day change", "k_zh": "20日变化",
                     "v": (f"{chg:+.0f}% · " + ("leveraging up" if chg > 0 else "deleveraging")),
                     "v_zh": (f"{chg:+.0f}% · " + ("杠杆上升" if chg > 0 else "去杠杆")),
                     "color": "neutral"})
    return {"kind": "margin_fin", "title": "Margin positioning · leveraged financing",
            "title_zh": "融资融券 · 杠杆资金", "rows": rows, "coloring": "neutral",
            "footnote": None, "footnote_zh": None}


def _card_global_beta(rec: dict) -> dict | None:
    gb = rec.get("global_beta") or {}
    beta = _num(gb.get("beta"))
    if beta is None:
        return None
    role = gb.get("role")
    role_map = {"amplifier": ("Amplifier — moves more with global risk", "放大器 — 随全球风险放大"),
                "cushion": ("Cushion — domestic-defensive", "缓冲 — 内需防御"),
                "neutral": ("Neutral global-risk exposure", "中性全球风险敞口")}
    rows = [{"k": "Global-risk β", "k_zh": "全球风险 β", "v": f"{beta:+.2f}", "v_zh": f"{beta:+.2f}"}]
    rl, rl_zh = role_map.get(role, (role or "", role or ""))
    return {"kind": "global_beta", "title": "Global-risk beta · amplifier vs cushion",
            "title_zh": "全球风险 β · 放大器或缓冲", "rows": rows, "coloring": "neutral",
            "footnote": rl, "footnote_zh": rl_zh}


def _card_ah_premium(rec: dict) -> dict | None:
    ah = rec.get("ah_premium") or {}
    prem = _num(ah.get("premium_pct"))
    if prem is None:
        return None
    chg = _num(ah.get("chg_1y"))
    # rising premium = the H line getting relatively cheaper-to-dearer; rising = bad for H buyers
    rows = [{"k": "A/H premium", "k_zh": "A/H 溢价", "v": f"{prem:+.0f}%", "v_zh": f"{prem:+.0f}%"}]
    if chg is not None:
        rows.append({"k": "1-year change", "k_zh": "一年变化", "v": f"{chg:+.0f}%",
                     "v_zh": f"{chg:+.0f}%", "color": "down" if chg > 0 else "up"})
    cheap_h = prem > 0
    foot = ("→ the H/HK line is the cheaper one" if cheap_h
            else "→ the A-share is the cheaper line")
    foot_zh = ("→ H/港股为更便宜的一侧" if cheap_h else "→ A股为更便宜的一侧")
    return {"kind": "ah_premium", "title": "A/H premium · mainland A vs HK-listed H",
            "title_zh": "A/H 溢价 · A股 与 H股", "rows": rows, "coloring": "neutral",
            "footnote": foot, "footnote_zh": foot_zh}


def _country_slot(rec: dict) -> dict:
    builders = (_card_commodity_beta, _card_val_band, _card_margin_fin,
                _card_global_beta, _card_ah_premium)
    cards = [c for c in (b(rec) for b in builders) if c is not None]
    return {"cards": cards}


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------
def build_view(rec: dict, market: str) -> dict:
    """Project an assembled per-ticker ``rec`` into the canonical render model.

    Pure + additive. Safe on a record with no ``conviction`` block (close-only
    markets): falls back to the cycle/ladder spine so the page still renders a
    headline. Always returns a dict; never raises on missing legs."""
    rec = rec or {}
    m = (market or "US").upper()
    conv = rec.get("conviction") or {}

    falsifiers = _falsifiers(rec, conv) if conv else []

    if conv:
        decision = _decision(rec, conv, falsifiers)
        fingerprint = _fingerprint(conv)
    else:
        # close-only fallback: drive the headline off the cycle ladder alone.
        lad = rec.get("ladder") or {}
        entry = lad.get("entry") or {}
        decision = {
            "headline": lad.get("summary_line") or entry.get("tag"),
            "headline_zh": entry.get("tag_zh"),
            "gloss": "", "gloss_zh": "",
            "band": "na", "band_en": "—", "band_zh": "—", "score": None,
            # no conviction block → no rank lane and no buy-frame action; JS renders
            # the single-lane (ladder-spine) layout when these are absent.
            "name_label": None, "name_label_zh": None,
            "rank_note": None, "rank_note_zh": None, "action": None,
            "trust": None, "regime": None, "size": {},
            "timing": {"state": lad.get("state"),
                       "state_label": lad.get("label") or lad.get("state"),
                       "tag": entry.get("tag"), "tag_zh": entry.get("tag_zh"),
                       "urgency": entry.get("urgency"),
                       "text": entry.get("text"), "text_zh": entry.get("text_zh")},
            "why": [], "state": "neutral", "conflict_pillars": [],
            "conflict_note": None, "conflict_note_zh": None,
        }
        fingerprint = {"axes": []}

    return {
        "schema": SCHEMA,
        "market": m,
        "decision": decision,
        "fingerprint": fingerprint,
        "falsifiers": falsifiers,
        "evidence": _evidence(rec, conv, m),
        "country_slot": _country_slot(rec),
    }
