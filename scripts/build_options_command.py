"""Build the Options workspace -> site/options.html  (OEU lane M-CMD).

THE CANONICAL OPTIONS SURFACE. One page, four modes (Daily Brief / Scanner /
Ticker / Leaders), assembled STRICTLY by re-serialising stores that other
builders already wrote.  Ruling: research/options_estate/OEU_MASTERPLAN.md §2.
Pinned design: research/options_estate/WORKSPACE_DESIGN_SPEC.md (markup and CSS
copied from mockups/oeu_workspace/options_mockup.html).

CONTRACT — read before changing anything here
─────────────────────────────────────────────
1. NO NEW DERIVATIONS.  Every state word on this page is an EXISTING payload
   enum rendered through an EXISTING house label map (the maps are cited inline
   against the template that already ships them).  This builder computes no
   scores, no rankings, no fused composites, and NO THRESHOLD BANDS
   (WORKSPACE_DESIGN_SPEC §0.13).  The one numeric filter it applies —
   |dist_to_flip_pct| <= 1 for the "sitting near a flip level" rail group — is
   the options_screener page's OWN shipped `nearflip` preset value
   (templates/options_screener.html.j2:959), reused rather than reinvented.
2. THE FOUR POSTURE READINGS ARE CO-DISPLAYED, NEVER FUSED.  They are four
   independent payload states printed side by side.  Nothing averages them.
3. DISPLAY TIER ONLY.  Nothing here feeds rank / size / gate.  The word
   "validated" never appears in user copy; the console's vetted glyph is gated
   on the vol payload's own `scored` flag exactly as gex.html gates its badge,
   and it prints a glyph, never the word.
4. O(SECONDS).  Pure JSON reads + re-serialisation.  No engine work, no network.
   Runs AFTER build_flow_desk / build_options_screener / build_flow_leaders /
   build_market_structure so it never renders a generation-stale page.
5. FAIL-SOFT, NEVER FAKE.  A missing store degrades exactly one section to its
   honest empty state and is named in the session-stamp quality receipt.  The
   builder always exits 0 — it can never break the nightly deploy.

Payload law (spec §6): the Brief and the whole persistent chrome are baked
inline; Scanner / Ticker / Leaders payloads are lazy-fetched by the page on mode
activation with plain fetch() — never a JS-injected <script> loader (that
bypasses asset stamping, #3372).

Run:  python -m scripts.build_options_command
      python -m scripts.build_options_command --out /tmp/options.html
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from lib import nyse_calendar, options_coverage  # noqa: E402

log = logging.getLogger("build_options_command")

_REPO_ROOT = Path(__file__).resolve().parent.parent

# The four index products the ruling pins for the Brief's close row.
INDEX_KEYS = ("SPX", "SPY", "QQQ", "IWM")

# Weekday names — EN comes from the stdlib, ZH from this fixed map (7 entries,
# a closed vocabulary, not a translation of free text).
_WEEKDAY_ZH = {
    "Monday": "周一", "Tuesday": "周二", "Wednesday": "周三", "Thursday": "周四",
    "Friday": "周五", "Saturday": "周六", "Sunday": "周日",
}

# ── EXISTING house label maps, reused verbatim ──────────────────────────────
# tape intensity: templates/flow_desk.html.j2:329-330 (_band_en / _band_zh)
_INTENSITY_EN = {"heavy": "Heavy", "busy": "Busy", "average": "Average",
                 "light": "Light", "quiet": "Quiet", "building": "Building"}
_INTENSITY_ZH = {"heavy": "汹涌", "busy": "活跃", "average": "中等",
                 "light": "清淡", "quiet": "冷清", "building": "积累中"}

# dealer gamma regime: templates/market_structure.html.j2:197-226 ships the
# plain-word states ("Dealers absorbing moves" / "做市商正在吸收波动" and the
# amplifying twin) AND the stance correspondence used below (long -> watch,
# short -> protect gains).  Condensed here to the console's one-word slot.
_GAMMA_STATE_EN = {"long": "Absorbing", "short": "Amplifying"}
_GAMMA_STATE_ZH = {"long": "吸收波动", "short": "放大波动"}
# Index-card regime headline: pinned by WORKSPACE_DESIGN_SPEC §5.1.
_REGIME_HEAD_EN = {"long": "Calm — moves get damped", "short": "Jumpy — moves get amplified"}
_REGIME_HEAD_ZH = {"long": "平静 — 波动被抑制", "short": "剧烈 — 波动被放大"}
# The consequence clause each regime carries (pinned, mockup lines 926/942).
_REGIME_CLAUSE_EN = {"long": "Dips tend to get bought here.", "short": "Swings run larger than usual."}
_REGIME_CLAUSE_ZH = {"long": "此区间回调通常被买回。", "short": "波动幅度大于平常。"}
# Stance follows the regime word 1:1 — the correspondence market_structure.html.j2
# already ships (long -> "watch", short -> the caution/protect chip).  Neither
# maps to "Act": no escalation is introduced by this page.
_REGIME_STANCE = {"long": "watch", "short": "protect"}

# net-premium tone: flow_desk emits 'pos~' / 'neg~' / 'neutral'.
_TONE_EN = {"pos~": "call-leaning", "neg~": "put-leaning", "neutral": "two-sided"}
_TONE_ZH = {"pos~": "偏看涨", "neg~": "偏看跌", "neutral": "双向"}
# sector bar fill class + tone chip
_TONE_CLS = {"pos~": "buy", "neg~": "sell", "neutral": "mix"}

# Same-day-expiry explanation.  Plain words only: the acronym this line used to
# carry ("0DTE") is banned vocabulary on BOTH the glance tier and the hover tier
# of this workspace (tests/test_build_options_command.py's two sweeps), because
# it was never a definition here — just the plain phrase with the jargon riding
# along beside it, which discloses nothing to the reader who needed it.  The
# term's sanctioned home is Tier 3, where a page actually explains it:
# content/seo/learn/options/zero-dte-regime.md.
#
# Standalone-safe in all three call sites (the pips-cell tip with and without a
# share prefix, and the top-movers caution chip), so the subject stays explicit
# rather than leaning on a "these contracts" antecedent a fourth caller might
# not supply.  templates/options.html.j2's `ZDTE` JS constant is the client-side
# twin of these two strings and carries the same wording verbatim.
#
# This line USED to be copied verbatim from templates/flow_leaders.html.j2:361,
# which still ships the acronym form (in a visible chip label, "0DTE-heavy", not
# only in its tip).  That is a real gap on a surface with its own lane and its
# own guard — do NOT resync these two by copying that version back here.
_ZERODTE_TIP_EN = ("Same-day contracts are usually day-trading, "
                   "not positioning for a move.")
_ZERODTE_TIP_ZH = "当日到期合约通常用于日内交易，而非布局趋势。"

# The nearflip rail group reuses the screener's own shipped preset value.
_NEAR_FLIP_PCT = 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Loading — every read is fail-soft and records what was missing
# ─────────────────────────────────────────────────────────────────────────────
def _load(path: Path) -> object | None:
    """Read a JSON store; return None (never raise) when absent or malformed."""
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("unreadable store %s: %s", path, exc)
        return None


def load_stores(root: Path) -> dict:
    """Load every store the workspace reads.  Absent stores come back as None."""
    site = root / "site"
    data = root / "data"
    gex: dict[str, dict] = {}
    for key in INDEX_KEYS:
        payload = _load(site / "gex" / f"{key}.json")
        if isinstance(payload, dict):
            gex[key] = payload
    return {
        "flow_desk": _load(site / "flow_desk.json"),
        "screener": _load(site / "screenerdata" / "rows.json"),
        "leaders": _load(site / "flowleaders" / "leaders.json"),
        "market_structure": _load(data / "market_structure" / "latest.json"),
        "vol": _load(site / "vol" / "regime.json"),
        "gex": gex,
        "gex_index": _load(site / "gex" / "index.json"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# AD-1 · Options Intelligence Brief — pass-through adapter
# (contracts/options/OPTIONS_INTEL_BRIEF_V1.md; design: frozen AD-1 board spec).
# This adapter computes NOTHING: every score/order/state/text on the board is
# copied verbatim from site/options_intel_brief.json.  Everything below is
# PRESENTATION ONLY — sign-based glyph lookups, pip counts (the house's own
# _pips() linear encoding) and closed-vocabulary word maps — never a new
# threshold, never a re-ranking, never a re-ordering.
#
# load_intel_brief() is a DELIBERATELY SEPARATE loader, not a load_stores()
# member: tests/test_render_options_workspace_scope.py pins load_stores()'s
# literal source AND a runtime probe of what it reads 1:1 against that test
# file's own WORKSPACE_STORES map — a file this packet's scope excludes
# touching.  Loading the brief through its own function keeps that pinned
# store set exactly as it was.
# ─────────────────────────────────────────────────────────────────────────────
def load_intel_brief(root: Path) -> dict | None:
    """Fail-soft loader for the AD-1 board artifact.  Missing/corrupt -> None;
    the board then renders its own honest 'unavailable' state — the contract
    has no board_state for a missing file, so absence is a consumer-side
    concern, same _load() convention as every other store this builder reads."""
    return _load(root / "site" / "options_intel_brief.json")


_AIB_STATE_SLUG = {"LONG": "up", "SHORT": "down", "VOLATILITY": "vol", "RISK_ONLY": "risk"}

_AIB_BAND_EN = {"tentative": "Tentative", "moderate": "Moderate", "firm": "Firm"}
_AIB_BAND_ZH = {"tentative": "初步", "moderate": "中等", "firm": "稳健"}

# contract §5 `horizon` enum -> plain words.  Closed vocabulary lookup, the
# same pattern as this file's _INTENSITY_EN / _GAMMA_STATE_EN maps above.
_AIB_HORIZON_EN = {
    "next_5_sessions": "next 5 sessions",
    "through_event_close": "through the event close",
    "next_session": "next session",
}
_AIB_HORIZON_ZH = {
    "next_5_sessions": "未来5个交易日",
    "through_event_close": "至事件收盘前",
    "next_session": "下一交易日",
}

# The frozen AD-1 board design spec's Prophet closed vocabulary, transcribed
# verbatim (contract §5 prophet_state enum -> plain words; display-only, zero
# rank authority per the contract's own authority table §6).
_AIB_PROPHET_EN = {
    "EXTENDED": "Already extended — not a fresh entry",
    "ALREADY_OPEN": "Plan already running",
    "NOT_READY": "Entry not ready yet",
    "READY": "Entry window open",
    # B1-B4 fix follow-up (contract §5 Prophet mapping note): OTHER covers a
    # lawful-but-unmapped record (e.g. a closed hold/partial plan) — "On the
    # board" implied active coverage that isn't there; the corrected words name
    # the state honestly instead.
    "OTHER": "Reviewed · no entry call",
    "UNAVAILABLE": "No read",
}
_AIB_PROPHET_ZH = {
    "EXTENDED": "已过度延伸——非新入场点",
    "ALREADY_OPEN": "计划已在运行",
    "NOT_READY": "入场尚未就绪",
    "READY": "入场窗口开放",
    "OTHER": "已评估 · 无入场判定",
    "UNAVAILABLE": "暂无读数",
}

# The frozen design spec's degraded closed vocabulary.  STALE_SOURCE keys off
# board_state (contract: it carries no board_reason); the other three key off
# board_reason under board_state DEGRADED.
_AIB_DEGRADED_EN = {
    "STALE_SOURCE": "Source data is stale — holding the last good session.",
    "ELIGIBILITY_COLLAPSE": "Too few names have complete data today — cards withheld.",
    "MIXED_VINTAGE": "Evidence dates disagree — cards withheld until they settle.",
    "NO_SETTLED_OI_PAIR": "Waiting for the next position count to settle this session.",
}
_AIB_DEGRADED_ZH = {
    "STALE_SOURCE": "数据源过期——保留最近有效交易日。",
    "ELIGIBILITY_COLLAPSE": "今日完整数据的名称过少——暂不展示卡片。",
    "MIXED_VINTAGE": "证据日期不一致——待结算后展示。",
    "NO_SETTLED_OI_PAIR": "等待下一次持仓统计以结算本交易日。",
}
# Fallback for a board_state/board_reason pair the design spec's table does
# not name (e.g. INSUFFICIENT_COVERAGE) — never blank, never a machine slug.
_AIB_DEGRADED_FALLBACK_EN = "This board is unavailable for this close."
_AIB_DEGRADED_FALLBACK_ZH = "本次收盘该板块暂不可用。"

# gex_confirm's OWN verdict vocabulary (engine/gex_confirm.py:49-53), reused
# verbatim per the design spec's "mechanics: verdict words only ... reuse
# existing gex vocab" instruction.  Transcribed rather than imported:
# engine.gex_confirm pulls in numpy/pandas, and this module must stay
# importable in the thin-pack CI env that stubs only jinja2
# (tests/test_render_options_workspace_scope.py's _import_builder, #3977).
_AIB_GEX_VERDICT_EN = {"confirm": "Options confirm", "neutral": "Options neutral", "caution": "Options caution"}
_AIB_GEX_VERDICT_ZH = {"confirm": "期权确认", "neutral": "期权中性", "caution": "期权警示"}

_AIB_LEG_VERDICT_EN = {"aligned": "aligned", "one_sided": "one-sided", "not_aligned": "not aligned"}
_AIB_LEG_VERDICT_ZH = {"aligned": "一致", "one_sided": "单边", "not_aligned": "不一致"}

# Display-only strength cut for the tier-2 Q_oi/Q_skew plain-word lines.
# Reuses the contract's OWN frozen Q_TH (OPTIONS_INTEL_BRIEF_V1.md §3) as the
# bucket boundary instead of inventing a new one — a word choice for display,
# never a second direction gate. Direction authority stays 100% with the
# producer (contract §6): this never feeds back into state/order/score.
_AIB_Q_STRENGTH_TH = 0.50

# ── AD-1 B5 (product exposure) closed vocabularies — every one a lookup on a
# verbatim producer field (contracts/options/OPTIONS_INTEL_BRIEF_V1.md §5a).
# No logic, no thresholds, no sorting: same pass-through law as the tables above.

# Band 2 · directional watch — `direction` (LONG/SHORT only; VOLATILITY/RISK_ONLY
# never reach the watch strip per the producer's own composition rule).
_AIB_WATCH_DIR_EN = {"LONG": "Upside", "SHORT": "Downside"}
_AIB_WATCH_DIR_ZH = {"LONG": "上行", "SHORT": "下行"}
_AIB_WATCH_DIR_SLUG = {"LONG": "up", "SHORT": "down"}

# Band 3 · event group — keyed on `event.event_premium_state` (strictly
# cross-sectional; never "underpriced/overpriced", never "historical move says").
_AIB_EVENT_STATE_EN = {
    "HIGH": "Priced above event peers",
    "NORMAL": "In line with event peers",
    "LOW": "Priced below event peers",
    None: "No event reading",
}
_AIB_EVENT_STATE_ZH = {
    "HIGH": "高于同期事件同类",
    "NORMAL": "与同期事件同类持平",
    "LOW": "低于同期事件同类",
    None: "暂无事件读数",
}
# Event rail empty-state: two distinct causes never collapse into one sentence.
_AIB_EVENT_EMPTY_EN = {
    "NONE": "No name has an event inside the window.",
    "UNKNOWN": "Event calendar not loaded — no event reading today.",
}
_AIB_EVENT_EMPTY_ZH = {
    "NONE": "窗口内没有名称有事件。",
    "UNKNOWN": "事件日历未加载——今日无事件读数。",
}

# Band 3 · risk group — keyed on `crowding.fired[]` leg codes (c1/c2/c3); multiple
# fires join with " · ".
_AIB_CROWD_EN = {
    "c1": "Same-day bets crowded",
    "c2": "Expensive options at a high",
    "c3": "Busy and expensive for days",
}
_AIB_CROWD_ZH = {
    "c1": "当日到期押注拥挤",
    "c2": "高位时期权偏贵",
    "c3": "连日活跃且偏贵",
}


def _aib_leg(evidence: list, name: str) -> tuple[str, str, float | None, int | None]:
    """(glyph, css class, raw signed value, history_n) for one Q leg.

    A verbatim SIGN read of a number the producer already computed and shipped
    in `evidence[]`.  No new threshold: positive/negative/zero-or-absent is the
    entire rule, mirroring this file's other pure sign->class lookups (e.g.
    build_bets' net-premium tone)."""
    for e in (evidence or []):
        if isinstance(e, dict) and e.get("name") == name:
            val = _num(e.get("value"))
            hist = e.get("history_n")
            hist = hist if isinstance(hist, int) else None
            if val is None or val == 0:
                return "▬", "flat", val, hist
            return ("▲", "up", val, hist) if val > 0 else ("▼", "down", val, hist)
    return "▬", "flat", None, None


def _aib_leg_verdict(oi_val: float | None, skew_val: float | None) -> str:
    """'aligned' both legs agree in sign; 'one_sided' only one leg moved;
    'not_aligned' otherwise (disagree, or neither moved).  Sign comparison
    only — never a magnitude threshold, never the direction gate itself."""
    oi_sign = None if not oi_val else (1 if oi_val > 0 else -1)
    sk_sign = None if not skew_val else (1 if skew_val > 0 else -1)
    if oi_sign is not None and sk_sign is not None:
        return "aligned" if oi_sign == sk_sign else "not_aligned"
    if oi_sign is not None or sk_sign is not None:
        return "one_sided"
    return "not_aligned"


def _aib_strength_word(value: float | None) -> tuple[str, str]:
    v = abs(value) if value is not None else 0.0
    return ("sharply", "显著") if v >= _AIB_Q_STRENGTH_TH else ("modestly", "温和")


def _aib_q_oi_line(val: float | None, n: int | None) -> tuple[str, str]:
    """Detail (tier 2) plain-word law: 'Open interest grew on the call/put
    side' + strength word; never 'buying/selling' (design spec)."""
    if val is None:
        return "No open-interest read available.", "暂无未平仓量读数。"
    word_en, word_zh = _aib_strength_word(val)
    side_en, side_zh = ("call", "看涨") if val >= 0 else ("put", "看跌")
    hist_en = f" ({n} sessions of history)" if n else ""
    hist_zh = f"（{n} 个历史交易日）" if n else ""
    return (f"Open interest grew on the {side_en} side, {word_en}{hist_en}.",
            f"未平仓量在{side_zh}方向增长，{word_zh}{hist_zh}。")


def _aib_q_skew_line(val: float | None, n: int | None) -> tuple[str, str]:
    """Detail (tier 2) plain-word law: 'Downside skew flattened/steepened
    unusually' + strength word (design spec)."""
    if val is None:
        return "No skew-change read available.", "暂无偏度变化读数。"
    word_en, word_zh = _aib_strength_word(val)
    move_en, move_zh = ("flattened", "走平") if val >= 0 else ("steepened", "走陡")
    hist_en = f" ({n} sessions of history)" if n else ""
    hist_zh = f"（{n} 个历史交易日）" if n else ""
    return (f"Downside skew {move_en} unusually, {word_en}{hist_en}.",
            f"下行偏度{move_zh}异常，{word_zh}{hist_zh}。")


def _aib_card(card: dict) -> dict:
    """One card's whole presentation context.  Every field is either copied
    verbatim from `card` or a closed-vocabulary / sign-only lookup on a
    verbatim field — no score, order, or state is computed here."""
    direction = card.get("direction")
    evidence = card.get("evidence") if isinstance(card.get("evidence"), list) else []
    oi_glyph, oi_cls, oi_val, oi_n = _aib_leg(evidence, "Q_oi")
    sk_glyph, sk_cls, sk_val, sk_n = _aib_leg(evidence, "Q_skew")
    verdict = _aib_leg_verdict(oi_val, sk_val)
    horizon = card.get("horizon")
    band = card.get("evidence_confidence_band")
    prophet = card.get("prophet_state")
    why_now = card.get("why_now") if isinstance(card.get("why_now"), list) else []
    move = _num(card.get("market_implied_move_pct"))
    mech = card.get("mechanics_context") if isinstance(card.get("mechanics_context"), dict) else {}
    gex_verdict = mech.get("gex_confirm_verdict")
    trigger = card.get("trigger_watch") if isinstance(card.get("trigger_watch"), dict) else {}
    invalidation = card.get("invalidation_watch") if isinstance(card.get("invalidation_watch"), dict) else {}
    oi_line_en, oi_line_zh = _aib_q_oi_line(oi_val, oi_n)
    skew_line_en, skew_line_zh = _aib_q_skew_line(sk_val, sk_n)
    why_lead = why_now[0] if why_now and isinstance(why_now[0], dict) else {}

    return {
        "signal_id": card.get("signal_id") or "—",
        "research_priority_score": card.get("research_priority_score"),
        "board_rank": card.get("board_rank"),
        "symbol": card.get("symbol") or "—",
        "direction": direction,
        "state_slug": _AIB_STATE_SLUG.get(direction, "vol"),
        "display_state_en": card.get("display_state_en") or "—",
        "display_state_zh": card.get("display_state_zh") or card.get("display_state_en") or "—",
        "oi_glyph": oi_glyph, "oi_cls": oi_cls,
        "skew_glyph": sk_glyph, "skew_cls": sk_cls,
        "leg_verdict_en": _AIB_LEG_VERDICT_EN[verdict], "leg_verdict_zh": _AIB_LEG_VERDICT_ZH[verdict],
        "pips": _pips(_num(card.get("evidence_strength"))), "pips_total": 5,
        "band_slug": band if band in _AIB_BAND_EN else "",
        "band_en": _AIB_BAND_EN.get(band, "—"), "band_zh": _AIB_BAND_ZH.get(band, "—"),
        "why_lead_en": why_lead.get("en") or "Evidence detail is in the receipt below.",
        "why_lead_zh": why_lead.get("zh") or "证据详情见下方回执。",
        "horizon_en": _AIB_HORIZON_EN.get(horizon, "—"), "horizon_zh": _AIB_HORIZON_ZH.get(horizon, "—"),
        "move_pct": (f"{move * 100:.1f}" if move is not None else None),
        "fresh_until": card.get("fresh_until") or "—",
        "prophet_en": _AIB_PROPHET_EN.get(prophet, _AIB_PROPHET_EN["UNAVAILABLE"]),
        "prophet_zh": _AIB_PROPHET_ZH.get(prophet, _AIB_PROPHET_ZH["UNAVAILABLE"]),
        "prophet_asof": card.get("prophet_asof"),
        "crowding": bool(card.get("crowding")),
        "detail": {
            "oi_line_en": oi_line_en, "oi_line_zh": oi_line_zh,
            "skew_line_en": skew_line_en, "skew_line_zh": skew_line_zh,
            "mechanics_en": _AIB_GEX_VERDICT_EN.get(gex_verdict),
            "mechanics_zh": _AIB_GEX_VERDICT_ZH.get(gex_verdict),
            "why_now": [w for w in why_now if isinstance(w, dict) and w.get("en")],
            "trigger_en": trigger.get("en") or "—", "trigger_zh": trigger.get("zh") or "—",
            "invalidation_en": invalidation.get("en") or "—", "invalidation_zh": invalidation.get("zh") or "—",
        },
    }


def _aib_watch_row(card: dict) -> dict:
    """Band 2 row — verbatim board_rank/symbol + a closed-vocab direction word.
    LONG/SHORT only (the producer's own composition rule; `.get` with no
    default would KeyError on an unexpected enum, so this falls back to the
    slug/word for LONG rather than raise on a display-only path)."""
    direction = card.get("direction")
    return {
        "board_rank": card.get("board_rank"),
        "symbol": card.get("symbol") or "—",
        "dir_slug": _AIB_WATCH_DIR_SLUG.get(direction, "up"),
        "dir_en": _AIB_WATCH_DIR_EN.get(direction, _AIB_WATCH_DIR_EN["LONG"]),
        "dir_zh": _AIB_WATCH_DIR_ZH.get(direction, _AIB_WATCH_DIR_ZH["LONG"]),
    }


def _aib_event_row(card: dict) -> dict:
    """Band 3 · event group row — verbatim fields + a closed-vocab state lookup
    on `event.event_premium_state`. `move_pct` reuses the card's own
    `market_implied_move_pct` (the only move-percent field the contract ships;
    there is no separate figure inside the `event` sub-object) through the
    same formatting convention `_aib_card` already uses."""
    event = card.get("event") if isinstance(card.get("event"), dict) else {}
    state = event.get("event_premium_state")
    move = _num(card.get("market_implied_move_pct"))
    return {
        "symbol": card.get("symbol") or "—",
        "state_en": _AIB_EVENT_STATE_EN.get(state, _AIB_EVENT_STATE_EN[None]),
        "state_zh": _AIB_EVENT_STATE_ZH.get(state, _AIB_EVENT_STATE_ZH[None]),
        "event_date": event.get("event_date") or "—",
        "move_pct": (f"{move * 100:.1f}" if move is not None else None),
        "board_rank": card.get("board_rank"),
    }


def _aib_risk_row(card: dict) -> dict:
    """Band 3 · risk group row — `cause` joins every fired crowd leg's closed-vocab
    word with ' · ' (contract §5a); `crowding.fired[]` is always non-empty on a
    risk_warnings row by construction (the producer only routes a card here when
    `crowding is not None`, which itself requires >=1 fired leg)."""
    crowding = card.get("crowding") if isinstance(card.get("crowding"), dict) else {}
    fired = crowding.get("fired") if isinstance(crowding.get("fired"), list) else []
    cause_en = " · ".join(_AIB_CROWD_EN[f] for f in fired if f in _AIB_CROWD_EN)
    cause_zh = " · ".join(_AIB_CROWD_ZH[f] for f in fired if f in _AIB_CROWD_ZH)
    return {
        "symbol": card.get("symbol") or "—",
        "cause_en": cause_en or "—", "cause_zh": cause_zh or "—",
        "board_rank": card.get("board_rank"),
    }


def build_aib(intel_brief: dict | None) -> dict:
    """The AD-1 board's whole template context.

    `intel_brief` is the parsed site/options_intel_brief.json artifact, or
    None when load_intel_brief() could not read it (its fail-soft contract).
    """
    if not isinstance(intel_brief, dict):
        return {
            "available": False, "healthy": False,
            "as_of_session": None, "oi_counted_date": None, "pending_session": None,
            "eligible": 0, "present": 0, "overflow": 0,
            "board_state": None, "board_reason": None, "receipt_id": None,
            "cards": [],
            "empty_kind": "degraded",
            "degraded_en": "No options intelligence brief is available for this close.",
            "degraded_zh": "本次收盘暂无期权情报简报。",
            "watch": [], "watch_overflow": 0, "no_directional": False,
            "events": [], "events_overflow": 0,
            "events_empty_en": _AIB_EVENT_EMPTY_EN["NONE"], "events_empty_zh": _AIB_EVENT_EMPTY_ZH["NONE"],
            "risks": [], "risks_overflow": 0,
            "control": None,
        }

    board_state = intel_brief.get("board_state")
    board_reason = intel_brief.get("board_reason")
    eligibility = intel_brief.get("eligibility") if isinstance(intel_brief.get("eligibility"), dict) else {}
    opportunities = intel_brief.get("opportunities") if isinstance(intel_brief.get("opportunities"), list) else []
    cards = [_aib_card(c) for c in opportunities if isinstance(c, dict)]

    # §5.2 no-signal law: OK and NO_SIGNAL are BOTH healthy outcomes — the
    # producer sets NO_SIGNAL exactly when a healthy session had nothing to
    # say ("a first-class OK-shaped outcome"), so an empty board under either
    # state is the healthy-quiet scene, never the degraded one.  Everything
    # else (STALE_SOURCE / DEGRADED / INSUFFICIENT_COVERAGE) is degraded.
    healthy = board_state in ("OK", "NO_SIGNAL")
    empty_kind = degraded_en = degraded_zh = None
    if not cards:
        if healthy:
            empty_kind = "quiet"
        else:
            empty_kind = "degraded"
            if board_state == "STALE_SOURCE":
                degraded_en, degraded_zh = _AIB_DEGRADED_EN["STALE_SOURCE"], _AIB_DEGRADED_ZH["STALE_SOURCE"]
            elif board_reason in _AIB_DEGRADED_EN:
                degraded_en, degraded_zh = _AIB_DEGRADED_EN[board_reason], _AIB_DEGRADED_ZH[board_reason]
            else:
                degraded_en, degraded_zh = _AIB_DEGRADED_FALLBACK_EN, _AIB_DEGRADED_FALLBACK_ZH

    # ── AD-1 B5 · Band 2 — directional watch (verbatim array order; contract §5a) ──
    watch_raw = intel_brief.get("directional_watch") if isinstance(intel_brief.get("directional_watch"), list) else []
    watch = [_aib_watch_row(c) for c in watch_raw if isinstance(c, dict)]
    no_directional = (intel_brief.get("directional_qualified_count") or 0) == 0

    # ── Band 3 · event group ──
    event_raw = intel_brief.get("event_board") if isinstance(intel_brief.get("event_board"), list) else []
    events = [_aib_event_row(c) for c in event_raw if isinstance(c, dict)]
    # "any card" carrying EVENT_STATE_UNKNOWN — the producer stamps this
    # null_reason on EVERY card uniformly when the calendar never loaded, so any
    # exposed array (opportunities/watch/risk/no_signal_exemplar) tells the truth.
    unknown_probe = list(opportunities) + list(watch_raw)
    risk_raw = intel_brief.get("risk_warnings") if isinstance(intel_brief.get("risk_warnings"), list) else []
    unknown_probe += risk_raw
    no_sig_raw = intel_brief.get("no_signal_exemplar")
    if isinstance(no_sig_raw, dict):
        unknown_probe.append(no_sig_raw)
    events_unknown = any(isinstance(c, dict) and c.get("null_reason") == "EVENT_STATE_UNKNOWN" for c in unknown_probe)
    events_empty_key = "UNKNOWN" if events_unknown else "NONE"

    # ── Band 3 · risk group ──
    risks = [_aib_risk_row(c) for c in risk_raw if isinstance(c, dict)]

    # ── Band 4 · control ──
    control = None
    if isinstance(no_sig_raw, dict):
        reason = no_sig_raw.get("no_signal_reason") if isinstance(no_sig_raw.get("no_signal_reason"), dict) else {}
        control = {
            "symbol": no_sig_raw.get("symbol") or "—",
            "reason_en": reason.get("en") or "—",
            "reason_zh": reason.get("zh") or reason.get("en") or "—",
        }

    return {
        "available": True, "healthy": healthy,
        "as_of_session": intel_brief.get("as_of_session"),
        "oi_counted_date": intel_brief.get("oi_counted_date"),
        "pending_session": intel_brief.get("pending_session"),
        "eligible": eligibility.get("eligible") or 0,
        "present": eligibility.get("present") or 0,
        "overflow": intel_brief.get("opportunities_overflow") or 0,
        "board_state": board_state, "board_reason": board_reason,
        "receipt_id": intel_brief.get("receipt_id") or "",
        "cards": cards,
        "empty_kind": empty_kind,
        "degraded_en": degraded_en, "degraded_zh": degraded_zh,
        "watch": watch, "watch_overflow": intel_brief.get("directional_watch_overflow") or 0,
        "no_directional": no_directional,
        "events": events, "events_overflow": intel_brief.get("event_board_overflow") or 0,
        "events_empty_en": _AIB_EVENT_EMPTY_EN[events_empty_key], "events_empty_zh": _AIB_EVENT_EMPTY_ZH[events_empty_key],
        "risks": risks, "risks_overflow": intel_brief.get("risk_board_overflow") or 0,
        "control": control,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Small formatting helpers (display only)
# ─────────────────────────────────────────────────────────────────────────────
def _num(value) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        return None if out != out else out  # NaN check
    except (TypeError, ValueError):
        return None


def money_mn(value) -> str:
    """$-format a figure already denominated in millions.  '—' when absent."""
    v = _num(value)
    if v is None:
        return "—"
    sign = "−" if v < 0 else ""
    a = abs(v)
    if a >= 1000:
        return f"{sign}${a / 1000:.1f}B"
    if a >= 1:
        return f"{sign}${a:.0f}M"
    return f"{sign}${a * 1000:.0f}K"


def signed_money_mn(value) -> str:
    """Like money_mn but keeps an explicit + on positives (net-premium column)."""
    v = _num(value)
    if v is None:
        return "—"
    return ("+" if v > 0 else "") + money_mn(v)


def price(value) -> str:
    v = _num(value)
    if v is None:
        return "—"
    if abs(v) >= 1000:
        return f"{v:,.2f}"
    return f"{v:,.2f}" if abs(v) < 100 else f"{v:,.2f}"


def level(value) -> str:
    """Strike-style level: drop a trailing .0 the way the chains report them."""
    v = _num(value)
    if v is None:
        return "—"
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def pct(value, digits: int = 1) -> str:
    v = _num(value)
    return "—" if v is None else f"{v:.{digits}f}%"


def _day(value) -> str | None:
    """The YYYY-MM-DD session-date prefix of a store's own stamp, or None.

    Stores stamp themselves inconsistently — a bare date here, a full ISO
    timestamp there.  Both name one session; reducing them to the same
    comparable key lets the receipt say which stores disagree instead of
    silently printing several vintages as one close (#F2-02/#F2-03).
    """
    if not isinstance(value, str) or len(value) < 10:
        return None
    day = value[:10]
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return None
    return day


def _pips(fraction, total: int = 5) -> int:
    """Position on a bounded 0..1 scale, as a count of filled segments.

    A LINEAR ENCODING of the value on its own natural scale — not a threshold
    band.  A present reading always lights at least one segment so "on" is never
    invisible; the unfilled remainder stays a visible tile (spec §1.2).
    """
    f = _num(fraction)
    if f is None:
        return 0
    f = min(max(f, 0.0), 1.0)
    return max(1, min(total, int(round(f * total)))) if f > 0 else 0


# ─────────────────────────────────────────────────────────────────────────────
# Session receipt + coverage (the close line's honesty fact)
# ─────────────────────────────────────────────────────────────────────────────
def _source_asof(payload) -> str | None:
    """A store's own session stamp, whatever it calls it.  None when unreadable."""
    if not isinstance(payload, dict):
        return None
    for key in ("asof", "as_of", "session", "date", "built"):
        v = payload.get(key)
        if isinstance(v, str) and v[:4].isdigit():
            return v[:10]
    return None


def _gex_index_asof(payload) -> str | None:
    """site/gex/index.json is a LIST of per-symbol rows, each carrying its own `asof`."""
    if not isinstance(payload, list) or not payload:
        return None
    stamps = [r.get("asof") for r in payload
              if isinstance(r, dict) and isinstance(r.get("asof"), str)]
    return max(stamps) if stamps else None


def _source_n(payload, key: str) -> int | None:
    """A store's own covered-names count.  None (never 0) when it does not publish one."""
    if not isinstance(payload, dict):
        return None
    v = payload.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return int(v)


def build_session(stores: dict, missing: list[str], intel_brief: dict | None = None) -> dict:
    """The session stamp: date, OI vintage, coverage share, quality word.

    `intel_brief` is OPTIONAL and additive — the AD-1 board (built separately,
    see build_aib()) is not one of this function's six existing stores.  When
    its own as_of_session disagrees with the page date, that mismatch joins
    the SAME stale-notes census below (cheap reuse of an existing pattern);
    a caller that never passes it (every pre-existing call site) sees no
    behaviour change at all.

    ONE SESSION DATE, CROSS-CHECKED (#F2-03/#F2-04).  The page date is the flow
    desk's own `asof` — the settled close the Brief is written against.  The
    screener export and the index-levels manifest each carry their OWN stamp,
    and those CAN drift apart (a rebuilt levels board, a scanner export from a
    later run).  When either disagrees with the page date, the mismatch is
    NAMED in the receipt and the quality word degrades to Partial — three
    vintages must never be presented silently as one settled close.

    Coverage numerator/denominator both come from ONE payload (the screener
    export) so the fraction is internally consistent: how many of the names we
    track reported a chain dated to the SCREENER'S OWN most recent close (which
    may not be the page date — see the mismatch note above).  Stale rows are
    the remainder, and the Scanner's per-row age column explains each one.
    """
    fd = stores.get("flow_desk") or {}
    sc = stores.get("screener") or {}
    gex_index = stores.get("gex_index")

    session_date = _day(fd.get("asof")) if isinstance(fd, dict) else None
    weekday_en = weekday_zh = ""
    if session_date:
        try:
            wd = datetime.strptime(session_date, "%Y-%m-%d").strftime("%A")
            weekday_en, weekday_zh = wd, _WEEKDAY_ZH.get(wd, "")
        except ValueError:
            pass

    # OI vintage — the options-chain snapshot the levels were measured from.
    oi_vintage = None
    if isinstance(gex_index, list) and gex_index:
        stamps = sorted({_day(e.get("asof")) for e in gex_index
                         if isinstance(e, dict) and _day(e.get("asof"))})
        oi_vintage = stamps[-1] if stamps else None

    covered = universe = None
    coverage_asof = None
    rows = sc.get("rows") if isinstance(sc, dict) else None
    if isinstance(rows, list) and rows:
        stamps = [_day(r.get("asof")) for r in rows if isinstance(r, dict) and _day(r.get("asof"))]
        universe = len(rows)
        if stamps:
            coverage_asof = max(stamps)
            covered = sum(1 for s in stamps if s == coverage_asof)

    coverage_pct = None
    if covered is not None and universe:
        coverage_pct = round(covered / universe * 100, 1)

    # Quality word — a PRESENCE census over the stores PLUS a VINTAGE-AGREEMENT
    # census, never a threshold on a value.  The receipt names exactly what is
    # absent, stale, or dated to a different close than the page's own
    # (#vacuous-green: emit the census, never a bare count).
    stale_notes_en: list[str] = []
    stale_notes_zh: list[str] = []
    leaders = stores.get("leaders")
    if isinstance(leaders, dict) and leaders.get("stale"):
        stale_notes_en.append("the leader boards are from an earlier session")
        stale_notes_zh.append("领头股榜单来自更早的场次")

    if session_date:
        if coverage_asof and coverage_asof != session_date:
            stale_notes_en.append(
                f"the options scanner's freshest chain is dated {coverage_asof}, not {session_date}")
            stale_notes_zh.append(f"期权筛选表的最新期权链日期为 {coverage_asof}，而非 {session_date}")
        if oi_vintage and oi_vintage != session_date:
            stale_notes_en.append(
                f"the index levels were last measured {oi_vintage}, not {session_date}")
            stale_notes_zh.append(f"指数水位的最近测算日期为 {oi_vintage}，而非 {session_date}")
        if isinstance(intel_brief, dict):
            ib_asof = _day(intel_brief.get("as_of_session"))
            if ib_asof and ib_asof != session_date:
                stale_notes_en.append(
                    f"the options intelligence brief is dated {ib_asof}, not {session_date}")
                stale_notes_zh.append(f"期权情报简报日期为 {ib_asof}，而非 {session_date}")

    if missing:
        stale_notes_en.append("some sections could not be built for this close")
        stale_notes_zh.append("部分板块本次收盘无法生成")

    if stale_notes_en:
        quality_en, quality_zh = "Partial", "部分"
        tip_en = ("Not everything reported for this close: "
                  + "; ".join(stale_notes_en)
                  + ". Every affected section says so where it sits.")
        tip_zh = "本次收盘并非所有数据都已送达：" + "；".join(stale_notes_zh) + "。受影响的板块会在原处说明。"
    else:
        quality_en, quality_zh = "Complete", "完整"
        tip_en = ("Every source reported on time, for the same close, and inside its normal "
                  "range. Nothing was estimated or carried over from an older session.")
        tip_zh = "所有数据源均按时送达、对应同一次收盘且处于正常范围。没有任何数值是估算或沿用旧场次的。"

    if covered is not None and universe:
        cov_tip_en = (f"{covered} of the {universe} names we track reported a complete options "
                      f"chain dated {coverage_asof}. The filled part of this line is that share; "
                      "the gap on the right is what is missing.")
        cov_tip_zh = (f"我们跟踪的 {universe} 个标的中，有 {covered} 个提供了截至 {coverage_asof} "
                      "的完整期权链。此线的填充部分即该比例，右侧空缺为缺失部分。")
    else:
        # No coverage number — the line stays fully hatched rather than pretending
        # to be complete, and says why.
        cov_tip_en = ("We could not count how many names reported a complete options chain for "
                      "this close, so this line is left empty rather than shown as full.")
        cov_tip_zh = "我们无法统计本次收盘有多少标的提供了完整期权链，因此此线留空，而非显示为完整。"

    return {
        "date": session_date,
        "weekday_en": weekday_en,
        "weekday_zh": weekday_zh,
        "oi_vintage": oi_vintage,
        "covered": covered,
        "universe": universe,
        # The vintage the coverage fraction was actually counted at — pinned so
        # a caller can check it against the page date instead of assuming.
        "coverage_asof": coverage_asof,
        "coverage_pct": coverage_pct,
        "quality_en": quality_en,
        "quality_zh": quality_zh,
        "quality_tip_en": tip_en,
        "quality_tip_zh": tip_zh,
        "cov_tip_en": cov_tip_en,
        "cov_tip_zh": cov_tip_zh,
        # OIP R8 — the shared options coverage object, ADDITIVE. Every key above is
        # untouched; no surface reads this yet (later waves adopt it). One comparable
        # shape across build_options_command / build_gex_board / build_options_screener /
        # build_flow_desk, so the estate can print one honest coverage sentence instead
        # of four incomparable ones. See lib/options_coverage.py.
        "coverage_v1": options_coverage.coverage_object(
            universe_name_en="Options names we track",
            universe_name_zh="我们跟踪的期权标的",
            universe_n=universe,
            covered_n=covered,
            asof=coverage_asof or session_date,
            sources=[
                options_coverage.source(
                    "flow_desk", "Options tape", "期权成交",
                    asof=_source_asof(stores.get("flow_desk")),
                    # minor 6 (review): flow_desk.json publishes n_names under `read`,
                    # not at the top level, so this was always None.
                    n=_source_n((stores.get("flow_desk") or {}).get("read")
                                if isinstance(stores.get("flow_desk"), dict) else None,
                                "n_names"),
                ),
                options_coverage.source(
                    "screener", "Scanner rows", "筛选表标的",
                    asof=coverage_asof, n=universe,
                ),
                options_coverage.source(
                    "leaders", "Flow leaders", "资金领跑",
                    asof=_source_asof(stores.get("leaders")),
                    # leaders.json counts its universe as coverage.n_universe
                    n=_source_n((stores.get("leaders") or {}).get("coverage")
                                if isinstance(stores.get("leaders"), dict) else None,
                                "n_universe"),
                ),
                options_coverage.source(
                    "market_structure", "Index structure", "指数结构",
                    asof=_source_asof(stores.get("market_structure")),
                ),
                options_coverage.source(
                    "vol", "Volatility regime", "波动状态",
                    asof=_source_asof(stores.get("vol")),
                ),
                options_coverage.source(
                    "gex", "Dealer positioning", "做市商持仓",
                    # minor 6 (review): site/gex/index.json is a LIST of per-symbol rows,
                    # so _source_asof (a dict reader) always returned None. Read the asof
                    # off the first row, and count the board's real breadth from the list
                    # rather than the 4 index payloads the Brief happens to inline.
                    asof=_gex_index_asof(stores.get("gex_index")),
                    n=(len(stores.get("gex_index"))
                       if isinstance(stores.get("gex_index"), list)
                       else None),
                ),
            ],
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# The posture console — four co-displayed readings, never fused
# ─────────────────────────────────────────────────────────────────────────────
def build_posture(stores: dict) -> list[dict]:
    """Four independent payload states, side by side.  No arithmetic between them.

    Each cell: an EXISTING label, that source's OWN state word, a linear pip
    position on that reading's OWN scale, and a supporting figure.  Nothing here
    is combined, ranked, or scored.
    """
    fd = stores.get("flow_desk") or {}
    read = fd.get("read") if isinstance(fd, dict) else None
    read = read if isinstance(read, dict) else {}
    ms = stores.get("market_structure") or {}
    gamma = ms.get("gamma") if isinstance(ms, dict) else None
    gamma = gamma if isinstance(gamma, dict) else {}
    vol = stores.get("vol") or {}
    snapshot = vol.get("snapshot") if isinstance(vol, dict) else None
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    game_plan = vol.get("game_plan") if isinstance(vol, dict) else None
    game_plan = game_plan if isinstance(game_plan, dict) else {}

    cells: list[dict] = []

    # 1 · Whole market — the vol-regime verdict, verbatim from its own payload.
    verdict = game_plan.get("verdict") if isinstance(game_plan.get("verdict"), dict) else {}
    risk_score = _num(snapshot.get("risk_score"))
    vix = _num(snapshot.get("vix"))
    cells.append({
        "label_en": "Whole market", "label_zh": "整体市场",
        # The vol desk's own bilingual verdict, verbatim.  Never the raw `regime`
        # enum — that is a machine slug and the doctrine bans it on the glance
        # tier in either language.
        "state_en": verdict.get("en") or "—", "state_zh": verdict.get("zh") or verdict.get("en") or "—",
        "pips": _pips(risk_score), "pips_total": 5,
        # The vetted glyph mirrors gex.html's own gate: it appears only when the
        # payload says this reading is scored.  It is a glyph, never the word.
        "vetted": bool(game_plan.get("scored") or snapshot.get("scored_active")),
        # A proper-noun index level needs no translation and carries no slug.
        "note_en": (f"VIX {vix:.1f}" if vix is not None else ""),
        "note_zh": (f"VIX {vix:.1f}" if vix is not None else ""),
        "tip_en": (f"Where the volatility surface sits on a calm-to-stressed scale, {_pips(risk_score)} of 5. "
                   "It reads what index options cost against how much the market has actually been moving."),
        "tip_zh": (f"波动率曲面在平静至紧张刻度上的位置：5 格中第 {_pips(risk_score)} 格。"
                   "它衡量的是指数期权的价格相对市场实际波动幅度的水平。"),
        "available": bool(verdict.get("en")),
    })

    # 2 · S&P dealers — the shock-absorber state and how long it has held.
    regime = gamma.get("regime")
    pctile = _num(gamma.get("net_gex_pctile"))
    days = gamma.get("days_in_regime")
    cells.append({
        "label_en": "S&P dealers", "label_zh": "标普做市商",
        "state_en": _GAMMA_STATE_EN.get(regime, "—"),
        "state_zh": _GAMMA_STATE_ZH.get(regime, "—"),
        "pips": _pips(None if pctile is None else pctile / 100.0), "pips_total": 5,
        "vetted": False,
        "note_en": (f"{days} day{'' if days == 1 else 's'} in this state" if days is not None else ""),
        "note_zh": (f"该状态已持续 {days} 天" if days is not None else ""),
        "tip_en": ("Dealer net gamma sits at the "
                   f"{pctile:.0f}th percentile of its own history — {_pips(pctile / 100.0)} of 5 "
                   "toward absorbing. Model estimate: real dealer books are unobservable."
                   if pctile is not None else
                   "Model estimate: real dealer books are unobservable."),
        "tip_zh": (f"做市商净 Gamma 处于自身历史的第 {pctile:.0f} 百分位 — 吸收方向 5 格中第 "
                   f"{_pips(pctile / 100.0)} 格。模型估算：真实做市商持仓不可观测。"
                   if pctile is not None else "模型估算：真实做市商持仓不可观测。"),
        "available": regime in _GAMMA_STATE_EN,
    })

    # 3 · Today's tape — the flow desk's own intensity band and score.
    intensity_key = read.get("intensity_key")
    score = _num(read.get("intensity_score"))
    gross = _num(read.get("gross_premium_mn"))
    cells.append({
        "label_en": "Today's tape", "label_zh": "今日盘面",
        "state_en": _INTENSITY_EN.get(intensity_key, "—"),
        "state_zh": _INTENSITY_ZH.get(intensity_key, "—"),
        "pips": _pips(None if score is None else score / 100.0), "pips_total": 5,
        "vetted": False,
        "note_en": (f"{money_mn(gross)} traded" if gross is not None else ""),
        "note_zh": (f"成交 {money_mn(gross)}" if gross is not None else ""),
        "tip_en": (f"{money_mn(gross)} of options premium traded — "
                   f"{score:.0f} of 100 on the quiet-to-frantic scale this desk already publishes."
                   if score is not None else "How busy the options tape was, on this desk's own scale."),
        "tip_zh": (f"期权权利金成交 {money_mn(gross)} — 本台既有的清淡至狂热刻度上 100 分中的 {score:.0f} 分。"
                   if score is not None else "期权盘面的繁忙程度，采用本台既有刻度。"),
        "available": intensity_key in _INTENSITY_EN,
    })

    # 4 · Same-day bets — the share itself, on its own 0–100% scale.
    #     DELIBERATELY NOT BANDED: no payload publishes a 0DTE state word, and
    #     §0.13 forbids this builder inventing one.  The reading is the share,
    #     with its meaning in the supporting line and the hover.
    share = _num(read.get("zerodte_share"))
    cells.append({
        "label_en": "Same-day bets", "label_zh": "当日到期押注",
        "state_en": (f"{share * 100:.0f}% of premium" if share is not None else "—"),
        "state_zh": (f"占权利金 {share * 100:.0f}%" if share is not None else "—"),
        "pips": _pips(share), "pips_total": 5,
        "vetted": False,
        "note_en": "expiring the same day", "note_zh": "当日到期",
        "tip_en": (f"{share * 100:.0f}% of today's options premium went to contracts expiring the "
                   f"same day. {_ZERODTE_TIP_EN}" if share is not None else _ZERODTE_TIP_EN),
        "tip_zh": (f"今日 {share * 100:.0f}% 的期权权利金流向当日到期的合约。{_ZERODTE_TIP_ZH}"
                   if share is not None else _ZERODTE_TIP_ZH),
        "available": share is not None,
    })
    return cells


# ─────────────────────────────────────────────────────────────────────────────
# Brief · what changed
# ─────────────────────────────────────────────────────────────────────────────
def build_changed(stores: dict) -> dict:
    """Day-over-day chips, from the only two stores that publish real deltas.

    A chip is emitted ONLY where a payload carries an actual change plus copy we
    can state plainly.  Nothing is inferred; an unrecognised state-change key is
    skipped rather than machine-phrased at the user.

    EACH CHIP CARRIES ITS OWN COMPARISON DATE IN ITS OWN TOOLTIP (#F2-14) — a
    panel-level "since X's close" header previously applied ONE baseline to
    both chips even though the tape chip is always vs flow_desk's own prior
    close while the regime-flip chip's baseline is whatever market_structure
    last completed, which can sit several sessions back after a build gap.  The
    regime-flip chip is WITHHELD entirely when that baseline is not the
    immediately preceding NYSE session — a stale attribution is worse than a
    missing chip.
    """
    fd = stores.get("flow_desk") or {}
    read = fd.get("read") if isinstance(fd, dict) else None
    read = read if isinstance(read, dict) else {}
    ms = stores.get("market_structure") or {}
    changes = ms.get("state_changes") if isinstance(ms, dict) else None
    changes = changes if isinstance(changes, dict) else {}

    chips: list[dict] = []

    # Tape, day over day — flow_desk's own dod_key, phrased with the fragments
    # templates/flow_desk.html.j2:343-344 already ships.  Always vs the single
    # immediately-prior close, by flow_desk's own dod convention.
    dod_key = read.get("dod_key")
    dod_pct = _num(read.get("dod_pct"))
    dod_copy = {
        "heavier": ("u", "Tape got heavier", "盘面更重"),
        "lighter": ("d", "Tape eased off", "盘面回落"),
        "steady": ("f", "Tape held steady", "盘面持平"),
    }
    if dod_key in dod_copy:
        arrow, en, zh = dod_copy[dod_key]
        gross = money_mn(read.get("gross_premium_mn"))
        chips.append({
            "arrow": arrow, "en": en, "zh": zh,
            "tip_en": (f"Options premium traded: {gross} this close, "
                       f"{dod_pct:+.0f}% against the previous close."
                       if dod_pct is not None else f"Options premium traded: {gross} this close."),
            "tip_zh": (f"期权权利金成交额：本次收盘 {gross}，较上次收盘 {dod_pct:+.0f}%。"
                       if dod_pct is not None else f"期权权利金成交额：本次收盘 {gross}。"),
        })

    # Dealer regime flips — market_structure publishes these with their own
    # bilingual note; only the gamma_regime key has plain-word chip copy.  Trust
    # the comparison only when vs_asof really is the session immediately before
    # market_structure's own asof; a multi-session build gap makes the "since"
    # attribution unsound, so withhold the chip rather than mislabel it.
    vs_asof = _day(changes.get("vs_asof"))
    ms_asof = _day(ms.get("asof")) if isinstance(ms, dict) else None
    baseline_sound = False
    if vs_asof and ms_asof:
        try:
            expected_prev = nyse_calendar.last_session_on_or_before(
                datetime.strptime(ms_asof, "%Y-%m-%d").date() - timedelta(days=1))
            baseline_sound = vs_asof == str(expected_prev)
        except ValueError:
            baseline_sound = False

    if baseline_sound:
        vs_stamp_en = f" Comparison baseline: {vs_asof}'s close."
        vs_stamp_zh = f" 对比基准：{vs_asof} 收盘。"
        for item in (changes.get("items") or []):
            if not isinstance(item, dict) or item.get("key") != "gamma_regime":
                continue
            to = item.get("to")
            if to == "short":
                chips.append({"arrow": "d", "en": "Dealers now amplify moves", "zh": "做市商转为放大波动",
                              "tip_en": (item.get("note_en") or "") + vs_stamp_en,
                              "tip_zh": (item.get("note_zh") or "") + vs_stamp_zh})
            elif to == "long":
                chips.append({"arrow": "u", "en": "Dealers now absorb moves", "zh": "做市商转为吸收波动",
                              "tip_en": (item.get("note_en") or "") + vs_stamp_en,
                              "tip_zh": (item.get("note_zh") or "") + vs_stamp_zh})

    return {"chips": chips[:5], "asof": read.get("asof")}


# ─────────────────────────────────────────────────────────────────────────────
# Brief · index close row
# ─────────────────────────────────────────────────────────────────────────────
def build_indexes(stores: dict) -> list[dict]:
    """SPX / SPY / QQQ / IWM: regime word, position against the flip, levels."""
    out: list[dict] = []
    for key in INDEX_KEYS:
        payload = (stores.get("gex") or {}).get(key)
        if not isinstance(payload, dict):
            continue
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        em = payload.get("expected_move") if isinstance(payload.get("expected_move"), dict) else {}
        regime = summary.get("regime")
        if regime not in _REGIME_HEAD_EN:
            continue
        dist = _num(summary.get("dist_to_flip_pct"))
        if dist is None:
            side_en = side_zh = ""
        elif dist >= 0:
            side_en = f"Closed {abs(dist):.1f}% above the flip."
            side_zh = f"收于翻转位上方 {abs(dist):.1f}%。"
        else:
            side_en = f"Closed {abs(dist):.1f}% below the flip."
            side_zh = f"收于翻转位下方 {abs(dist):.1f}%。"
        out.append({
            "sym": key,
            "name_en": meta.get("en") or key,
            "name_zh": meta.get("zh") or meta.get("en") or key,
            "spot": price(summary.get("spot")),
            "head_en": _REGIME_HEAD_EN[regime], "head_zh": _REGIME_HEAD_ZH[regime],
            "line_en": (side_en + " " + _REGIME_CLAUSE_EN[regime]).strip(),
            "line_zh": (side_zh + _REGIME_CLAUSE_ZH[regime]).strip(),
            "floor": level(summary.get("put_wall")),
            "flip": level(summary.get("gamma_flip")),
            "ceiling": level(summary.get("call_wall")),
            "stance": _REGIME_STANCE[regime],
            "em": (f"±{_num(em.get('daily_pct')):.2f}%" if _num(em.get("daily_pct")) is not None else "—"),
            "asof": meta.get("asof"),
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Brief · sector bars + biggest bets
# ─────────────────────────────────────────────────────────────────────────────
def build_sectors(stores: dict) -> dict | None:
    """Shared-scale premium bars.  Bar length is a pure length encoding."""
    fd = stores.get("flow_desk") or {}
    heat = fd.get("sector_heatmap") if isinstance(fd, dict) else None
    if not isinstance(heat, list) or not heat:
        return None
    rows = [r for r in heat if isinstance(r, dict) and _num(r.get("gross_premium_mn")) is not None]
    if not rows:
        return None
    rows.sort(key=lambda r: _num(r.get("gross_premium_mn")) or 0.0, reverse=True)
    top = _num(rows[0].get("gross_premium_mn")) or 0.0
    total = sum(_num(r.get("gross_premium_mn")) or 0.0 for r in rows)
    out = []
    for r in rows:
        v = _num(r.get("gross_premium_mn")) or 0.0
        tone = r.get("tone")
        out.append({
            "sector": r.get("sector") or "—",
            "width": round(v / top * 100, 1) if top else 0.0,
            "val": money_mn(v),
            "cls": _TONE_CLS.get(tone, "mix"),
            "tone_en": {"pos~": "buying ~", "neg~": "selling ~"}.get(tone, "mixed"),
            "tone_zh": {"pos~": "买入 ~", "neg~": "卖出 ~"}.get(tone, "混合"),
        })
    top2 = None
    if total > 0 and len(rows) >= 2:
        top2 = round(sum((_num(r.get("gross_premium_mn")) or 0.0) for r in rows[:2]) / total * 100)
    return {"rows": out, "top2_pct": top2, "asof": rows[0].get("asof")}


def build_bets(stores: dict) -> dict | None:
    """Biggest single net-premium marks, with the flow desk's own caution flags."""
    fd = stores.get("flow_desk") or {}
    movers = fd.get("top_movers") if isinstance(fd, dict) else None
    if not isinstance(movers, list) or not movers:
        return None
    out = []
    for m in movers[:10]:
        if not isinstance(m, dict):
            continue
        net = _num(m.get("net_premium_mn"))
        # The lean word comes from the SIGN OF THE DISPLAYED NUMBER — the rule
        # flow_desk.html.j2:610-616 already ships for this same board.  Do NOT
        # use `tone` here: top_movers emits 'neg' (no tilde) where the sector
        # heatmap emits 'neg~', so a shared map silently mislabels put-leaning
        # names as two-sided.
        tone = "pos~" if (net or 0) > 0 else ("neg~" if (net or 0) < 0 else "neutral")
        cautions = []
        if m.get("zerodte_dominated"):
            cautions.append({"en": "Same-day heavy", "zh": "当日到期为主",
                             "warn": False, "tip_en": _ZERODTE_TIP_EN, "tip_zh": _ZERODTE_TIP_ZH})
        share = _num(m.get("zerodte_share"))
        out.append({
            "sym": m.get("ticker") or "—",
            "amt": signed_money_mn(net),
            "sign": "pos" if (net or 0) > 0 else ("neg" if (net or 0) < 0 else ""),
            "tone_en": _TONE_EN.get(tone, "two-sided"),
            "tone_zh": _TONE_ZH.get(tone, "双向"),
            "share_en": (f"{share * 100:.0f}% same-day" if share is not None else ""),
            "share_zh": (f"{share * 100:.0f}% 当日到期" if share is not None else ""),
            "cautions": cautions,
        })
    return {"rows": out, "asof": movers[0].get("asof") if isinstance(movers[0], dict) else None}


# ─────────────────────────────────────────────────────────────────────────────
# Brief · names-for-tomorrow rail
# ─────────────────────────────────────────────────────────────────────────────
def build_rail(stores: dict) -> dict:
    """Three research groups, each a straight read of an existing board.

    Group B mirrors flow_leaders.html.j2's own admission rule exactly — the
    corrected washout-flip verdict B5, not days_since_inflection (#3496).
    Group C reuses the screener's shipped `nearflip` preset value.
    """
    leaders = stores.get("leaders") if isinstance(stores.get("leaders"), dict) else {}
    sc = stores.get("screener") if isinstance(stores.get("screener"), dict) else {}

    board_a = leaders.get("board_a") if isinstance(leaders.get("board_a"), list) else []
    board_b = leaders.get("board_b") if isinstance(leaders.get("board_b"), list) else []
    rows = sc.get("rows") if isinstance(sc.get("rows"), list) else []

    a = [r.get("ticker") for r in board_a[:6] if isinstance(r, dict) and r.get("ticker")]
    b = [r.get("ticker") for r in board_b
         if isinstance(r, dict) and r.get("B5_flow_inflect") and r.get("ticker")][:6]

    near = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        d = _num(r.get("dist_to_flip_pct"))
        if d is not None and abs(d) <= _NEAR_FLIP_PCT and r.get("ticker"):
            near.append((abs(d), r["ticker"]))
    near.sort()
    c = [t for _d, t in near[:6]]

    return {
        "a": a, "b": b, "c": c,
        "asof": leaders.get("as_of", "")[:10] if isinstance(leaders.get("as_of"), str) else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Context assembly
# ─────────────────────────────────────────────────────────────────────────────
def _missing_stores(stores: dict) -> list[str]:
    """Content-aware presence census (#F2-02).

    A store that is PRESENT but carries no usable rows/boards/payloads is
    exactly as unusable to the page as an absent one — `{"rows": []}` and
    `{"board_a": [], "board_b": []}` are truthy dicts that a bare `if not
    stores.get(key)` check waves through as "fine".
    """
    missing: list[str] = []

    fd = stores.get("flow_desk")
    if not (isinstance(fd, dict) and fd.get("read")):
        missing.append("flow_desk")

    sc = stores.get("screener")
    if not (isinstance(sc, dict) and sc.get("rows")):
        missing.append("screener")

    ld = stores.get("leaders")
    if not (isinstance(ld, dict) and (ld.get("board_a") or ld.get("board_b"))):
        missing.append("leaders")

    if not stores.get("market_structure"):
        missing.append("market_structure")
    if not stores.get("vol"):
        missing.append("vol")
    if not stores.get("gex"):
        missing.append("gex")
    if not stores.get("gex_index"):
        missing.append("gex_index")

    return missing


def build_context(root: Path, stores: dict | None = None, intel_brief: dict | None = None) -> dict:
    """Assemble the whole workspace context from the committed stores.

    `intel_brief` is the AD-1 board's OWN artifact (site/options_intel_brief.json),
    kept OUT of `stores`/load_stores() on purpose — see the AD-1 section above.
    Default None: every pre-existing caller that never passes it renders the
    board in its honest "unavailable" state, with zero other behaviour change.
    """
    stores = load_stores(root) if stores is None else stores

    missing = _missing_stores(stores)

    session = build_session(stores, missing, intel_brief)
    changed = build_changed(stores)
    indexes = build_indexes(stores)
    sectors = build_sectors(stores)
    bets = build_bets(stores)
    rail = build_rail(stores)

    leaders = stores.get("leaders") if isinstance(stores.get("leaders"), dict) else {}
    n_boards = sum(1 for k in ("board_a", "board_b") if leaders.get(k))

    return {
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "session": session,
        "posture": build_posture(stores),
        "changed": changed,
        "indexes": indexes,
        "sectors": sectors,
        "bets": bets,
        "rail": rail,
        "aib": build_aib(intel_brief),
        "counts": {
            "scanner": session.get("universe"),
            "ticker": "SPY" if "SPY" in (stores.get("gex") or {}) else (INDEX_KEYS[0]),
            "leaders": n_boards or None,
            # Flow mode's tab figure is the COVERED-SECTOR count (ONE_DOOR spec
            # §2.0.1) — counted with build_sectors' own filter, so the tab and the
            # panel it opens can never disagree about how many sectors reported.
            # The mode's rows themselves are lazy-fetched client-side; this is the
            # only thing about Flow the chrome needs to know.
            "flow": (len(sectors["rows"]) if sectors and sectors.get("rows") else None),
        },
        "missing": missing,
        # Direction honesty, straight from the flow desk's own fields (#F2-01/
        # #F2-09) — rendered next to the sector/bets tone chips rather than
        # loaded and left unused.
        "direction_note": (stores.get("flow_desk") or {}).get("direction_note")
        if isinstance(stores.get("flow_desk"), dict) else None,
        "direction_reliable": (stores.get("flow_desk") or {}).get("direction_reliable")
        if isinstance(stores.get("flow_desk"), dict) else None,
        # OIP W1 §2.3: Ticker-mode search/typeahead reuses gex.html's own manifest
        # rather than growing a second, possibly-drifting universe. That array is
        # ALREADY on disk — scripts.build_gex_board writes it, unconditionally,
        # every run, as site/gex/index.json (which load_stores() above already
        # reads into stores["gex_index"] for the Brief's index cards) — so this is
        # a second consumer of an existing artifact, not a new derivation, and no
        # new site/gex/_manifest.json side-file is needed (build_gex_board.py is
        # unchanged). One producer, one array, two consumers.
        #
        # Addition-2 fix (PR #4123 adversarial review round 2): embed a SLIM
        # key/en/zh projection, not the full manifest row. setupTickerSearch()
        # (this page's own client JS, below) reads only m.key/m.en/m.zh — the
        # other 23 fields on a real gex_index row (spot, iv30, gamma_flip,
        # call_wall, put_wall, max_pain, asof, ...) are build-time-frozen prices
        # that nothing in this workspace reads, yet were shipping in full: 649
        # rows x 26 fields grew this page 123,775 -> 544,320 bytes, ~26.8KB
        # gzipped of dead weight on every load, and worse, looked live (a future
        # reader could plausibly reach for `m.spot` from this manifest and get a
        # stale, build-time number on a page whose Ticker mode otherwise only
        # ever shows live-fetched prices). The full stores["gex_index"] list
        # itself is untouched — the Brief's index cards above still consume it
        # whole; only this second, JS-search-only consumer's own copy is slimmed.
        "ticker_manifest_json": json.dumps(
            [
                {"key": m.get("key"), "en": m.get("en"), "zh": m.get("zh")}
                for m in (stores.get("gex_index") or [])
            ],
            default=float,
        ),
        # Flow mode renders sector names CLIENT-side from the lazy-fetched
        # flow_desk.json, so it cannot reach the Jinja td()/tr() globals the
        # baked Brief uses one tab away. This tiny map (≤ a dozen sectors)
        # carries the same LEX translations to the client; a name the LEX
        # doesn't know degrades to its English form, exactly like td().
        "sector_zh_json": _sector_zh_json(stores),
    }


def _sector_zh_json(stores: dict) -> str:
    try:
        from engine.i18n import tr  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return "{}"
    names = {
        str(r.get("sector"))
        for r in ((stores.get("flow_desk") or {}).get("sector_heatmap") or [])
        if r.get("sector")
    }
    return json.dumps({n: tr(n) for n in sorted(names)}, ensure_ascii=False)


def render(root: Path, stores: dict | None = None, intel_brief: dict | None = None) -> str:
    """Render options.html.j2 and return the HTML string."""
    ctx = build_context(root, stores, intel_brief)
    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=True,
    )
    try:
        sys.path.insert(0, str(root))
        from engine import i18n  # noqa: PLC0415
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        # Template defines t() locally; td() is only used for sector display names
        # and degrades to English-only, never to a crash.
        env.globals.update(td=lambda s, *a, **k: s, tr=lambda s, *a, **k: s)
    return env.get_template("options.html.j2").render(**ctx)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the Options workspace page.")
    ap.add_argument("--root", default=str(_REPO_ROOT), help="repo root")
    ap.add_argument("--out", default=None, help="output path (default site/options.html)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(args.root).resolve()
    out_path = Path(args.out) if args.out else (root / "site" / "options.html")

    # CONTRACT (docstring §5): the builder always exits 0.  write_page and the
    # logging pass used to sit OUTSIDE this fence — along with a second, fully
    # redundant re-read of every store purely to log a line — so an exception
    # in either one propagated out of main() despite the contract's promise
    # (#F2-08).  One store load, one context build, one fence.
    try:
        stores = load_stores(root)
        intel_brief = load_intel_brief(root)
        html = render(root, stores=stores, intel_brief=intel_brief)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        # write_page is the ONLY write path. The fail-soft law above covers a
        # RENDER failure (keep the previous page); it never licensed shipping a
        # rendered page without the data-base shim, which is what the raw-write
        # fallback here did — silently, since the render lane's
        # inject_data_base sweep healed the committed copy afterwards.
        from lib.pages import write_page  # noqa: PLC0415
        write_page(out_path, html)

        ctx = build_context(root, stores, intel_brief)
        sess = ctx["session"]
        log.info(
            "options workspace -> %s | session=%s coverage=%s/%s (%s%%) quality=%s missing=%s aib=%s",
            out_path, sess.get("date"), sess.get("covered"), sess.get("universe"),
            sess.get("coverage_pct"), sess.get("quality_en"), ctx["missing"] or "none",
            ctx["aib"].get("board_state") if ctx["aib"].get("available") else "unavailable",
        )
        if ctx["missing"]:
            print("::warning title=build_options_command::degraded sections — missing stores: "
                  + ", ".join(ctx["missing"]))
    except Exception as exc:  # noqa: BLE001
        # Display-tier surface: never break the nightly deploy.  The last
        # committed options.html stands.
        log.error("render failed — keeping the previous page: %s", exc, exc_info=True)
        print(f"::warning title=build_options_command::render failed ({exc}); previous page kept")
        return 0

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
