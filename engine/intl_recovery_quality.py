"""Recovery-quality qualifiers for international market turn states.

The price-state engine answers a narrow question: has the broad index begun to
repair after a damaged/downward regime?  It does not, by itself, answer whether
that repair has healthy leadership or a supportive external backdrop.

This module keeps those authorities separate:

* price state remains the primary structural classifier;
* peer breadth and a market-specific leading-risk radar qualify recovery;
* geopolitical and election-cycle items are display-only context and never
  change the phase, score, probability, rank, or position size.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_HOT_RISK_STATES = {"elevated", "risk-off"}
_RISING_RISK_PHASES = {"rising", "peaking"}


def _mapping(value: Any) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def assess_recovery(
    state: Mapping | None,
    confirmation: Mapping | None = None,
    risk_radar: Mapping | None = None,
) -> dict:
    """Differentiate a repair attempt from a confirmed or failing recovery.

    This is intentionally a qualifier, not a replacement state machine.  It
    only returns a payload while the primary price state is ``recovery``.
    """
    st = _mapping(state)
    if st.get("state") != "recovery":
        return {}

    cf = _mapping(confirmation)
    w5 = _mapping(_mapping(cf.get("windows")).get("5d"))
    risk = _mapping(risk_radar)
    trajectory = _mapping(risk.get("trajectory"))

    breadth_n = int(_number(w5.get("available")) or 0)
    breadth_pct = _number(w5.get("breadth_pct"))
    breadth_median = _number(w5.get("median_return_pct"))
    direction = str(cf.get("direction") or "")

    breadth_fading = (
        direction == "broad_rebound_fading"
        or (
            breadth_n >= 3
            and (
                (breadth_pct is not None and breadth_pct <= 50.0)
                or (breadth_median is not None and breadth_median < 0.0)
            )
        )
    )
    breadth_followthrough = (
        breadth_n >= 3
        and breadth_pct is not None
        and breadth_pct >= 75.0
        and breadth_median is not None
        and breadth_median > 0.0
        and direction != "broad_rebound_fading"
    )
    breadth_failed = (
        direction == "broad_decline"
        or (
            breadth_n >= 3
            and breadth_pct is not None
            and breadth_pct <= 25.0
            and breadth_median is not None
            and breadth_median <= -3.0
        )
    )

    risk_state = str(risk.get("state") or "")
    risk_phase = str(trajectory.get("phase") or "")
    external_hot = risk_state in _HOT_RISK_STATES
    external_rising = risk_phase in _RISING_RISK_PHASES
    risk_state_zh = {
        "elevated": "偏高",
        "risk-off": "避险",
        "caution": "谨慎",
        "watch": "留意",
        "calm": "平静",
    }.get(risk_state, "偏高")
    dominant_en = str(risk.get("dominant_label_en") or "external pressure")
    dominant_zh = str(risk.get("dominant_label_zh") or "外部压力")

    mom20 = _number(st.get("mom20_pct"))
    price_failed = (
        st.get("above_ma20") is False
        or st.get("macd_state") == "bear"
        or (mom20 is not None and mom20 <= 0.0)
    )

    if price_failed or breadth_failed:
        phase = "failed_rebound"
        label_en, label_zh = "Rebound failed", "反弹失败"
        stance_en = "Stand aside — repair evidence has broken"
        stance_zh = "观望 — 修复证据已经破坏"
        read_en = (
            "The earlier bounce no longer has enough price or breadth support. "
            "Treat the repair attempt as failed until the index and leadership reclaim it."
        )
        read_zh = "此前反弹已失去足够的价格或广度支撑。在指数与领涨股重新收复前，视为修复尝试失败。"
        css, heat, lens_kind, glyph = "failed-rebound", "hot", "caution", "fall"
    elif breadth_fading and external_hot:
        phase = "rollover_risk"
        label_en, label_zh = "Fragile rebound", "脆弱反弹"
        stance_en = "Rollover risk — wait for breadth to re-accelerate"
        stance_zh = "再度转弱风险 — 等待广度重新加速"
        read_en = (
            f"The broad-index repair is still intact, but leadership is fading while "
            f"the external-risk radar is {risk_state or 'elevated'} ({dominant_en}). "
            "Treat this as a possible failed breakout, not a confirmed recovery."
        )
        read_zh = (
            f"宽基指数的修复尚未破坏，但领涨动能正在减弱，外部风险雷达为"
            f"{risk_state_zh}（{dominant_zh}）。应视为可能的假突破，而非已确认复苏。"
        )
        css, heat, lens_kind, glyph = "rollover-risk", "warm", "read", "stretch"
    elif breadth_followthrough and not external_hot and not external_rising:
        phase = "recovery_confirmed"
        label_en, label_zh = "Recovery gaining traction", "复苏逐步确认"
        stance_en = "Follow-through improving — still size for volatility"
        stance_zh = "跟进力度改善 — 仍需控制波动风险"
        read_en = (
            "The index repair now has broad short-term follow-through and the "
            "external-risk radar is not elevated. Recovery is gaining traction, "
            "though it is not yet a mature uptrend."
        )
        read_zh = "指数修复已获短期广度跟进，外部风险雷达亦未升高。复苏正在增强，但尚非成熟上升趋势。"
        css, heat, lens_kind, glyph = "recovery-confirmed", "cool", "record", "rise"
    else:
        phase = "repair_attempt"
        label_en, label_zh = "Repair attempt", "修复尝试"
        stance_en = "Unconfirmed — wait for breadth and external pressure to improve"
        stance_zh = "尚未确认 — 等待广度与外部压力改善"
        read_en = (
            "The index has repaired some technical damage, but confirmation is incomplete. "
            "Do not treat this as a durable recovery until leadership follows through and "
            "external pressure recedes."
        )
        read_zh = "指数已修复部分技术损伤，但确认仍不完整。在领涨股跟进、外部压力回落前，不应视为持久复苏。"
        css, heat, lens_kind, glyph = "repair-attempt", "warm", "define", "flat"

    return {
        "phase": phase,
        "label_en": label_en,
        "label_zh": label_zh,
        "stance_en": stance_en,
        "stance_zh": stance_zh,
        "read_en": read_en,
        "read_zh": read_zh,
        "css": css,
        "heat": heat,
        "lens_kind": lens_kind,
        "glyph": glyph,
        "evidence": {
            "breadth_fading": breadth_fading,
            "breadth_followthrough": breadth_followthrough,
            "breadth_failed": breadth_failed,
            "external_hot": external_hot,
            "external_rising": external_rising,
            "risk_state": risk_state or None,
            "risk_phase": risk_phase or None,
            "dominant_en": dominant_en if risk else None,
            "dominant_zh": dominant_zh if risk else None,
        },
    }


def macro_backdrop(
    rates_command: Mapping | None,
    *,
    as_of: Any = None,
) -> dict:
    """Build a display-only macro backdrop with explicit authority limits."""
    rc = _mapping(rates_command)
    board = _mapping(rc.get("board"))
    rate_row = _mapping(board.get("rate_path_row"))
    policy_row = _mapping(board.get("policy_row"))
    iran = _mapping(policy_row.get("iran_context"))

    items: list[dict] = []
    implied_bp = _number(_mapping(rate_row.get("implied_path")).get("m12"))
    policy_rate = _number(rate_row.get("policy_rate"))
    path_bp = _number(rate_row.get("implied_bp_12m"))
    if policy_rate is not None or path_bp is not None or implied_bp is not None:
        if path_bp is not None and path_bp > 25.0:
            label_en = "Rates restrictive / repricing higher"
            label_zh = "利率偏紧／定价上调"
        else:
            label_en = "Rates backdrop monitored"
            label_zh = "监测利率背景"
        detail_en = str(rate_row.get("headline_en") or "Measured rates context; display only.")
        detail_zh = str(rate_row.get("headline_zh") or "实测利率背景；仅作展示。")
        items.append({
            "key": "rates",
            "label_en": label_en,
            "label_zh": label_zh,
            "detail_en": detail_en,
            "detail_zh": detail_zh,
            "scored": False,
        })

    if iran:
        stale_days = int(_number(policy_row.get("intel_staleness_days")) or 0)
        items.append({
            "key": "iran_oil",
            "label_en": "Iran/oil tail risk unresolved",
            "label_zh": "伊朗／原油尾部风险未解",
            "detail_en": (
                "Qualitative, unsigned geopolitical condition; it cannot change the "
                f"market state or probability. Intel age: {stale_days}d."
            ),
            "detail_zh": f"定性、无方向的地缘条件；不得改变市场状态或概率。情报时效：{stale_days}天。",
            "scored": False,
            "stale_days": stale_days,
        })

    try:
        from engine.election_cycle import context as election_context

        election = election_context(as_of or rc.get("asof"))
    except Exception:
        election = {}
    if _mapping(election).get("is_midterm"):
        items.append({
            "key": "midterm",
            "label_en": "Midterm window monitored, not scored for HK",
            "label_zh": "监测中期选举窗口，但不计入港股评分",
            "detail_en": (
                "The calendar is visible as a sizing backdrop only. This repository's "
                "own test found no independent HK/EM midterm drawdown edge, so measured "
                "rates, dollar and breadth evidence take precedence."
            ),
            "detail_zh": "日历仅作仓位背景。本库检验未发现港股／新兴市场独立的中期选举回撤优势，故以实测利率、美元与广度为准。",
            "scored": False,
        })

    if not items:
        return {}

    labels_en = " · ".join(item["label_en"] for item in items)
    labels_zh = " · ".join(item["label_zh"] for item in items)
    return {
        "as_of": str(as_of or rc.get("asof") or "")[:10] or None,
        "items": items,
        "summary_en": labels_en,
        "summary_zh": labels_zh,
        "read_en": (
            "Macro backdrop is shown separately from the price state. Measured HK "
            "rate/FX pressure lives in the pullback radar; Iran/oil and the midterm "
            "calendar remain unscored context."
        ),
        "read_zh": "宏观背景与价格状态分开显示。实测港股利率／汇率压力归入回撤雷达；伊朗／原油及中期选举日历仅作未评分背景。",
        "display_only": True,
    }
