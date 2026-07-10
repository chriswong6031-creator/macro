"""engine/prophet_bridge.py — Prophet Origination Bridge (W1, display-only).

Converts us_standouts.json buy-lane entries into prophet.trade_plan/v1 envelopes
and resolves option contracts from the ThetaData EOD store.

PUBLIC API
----------
originate_plans(standouts_path, asof, existing_ids, thetadata_store) -> list[dict]
    Return a list of new prophet.trade_plan/v1 dicts.  IDs already in
    existing_ids are skipped (duplicate-suppression contract).

resolve_option(ticker, direction, entry, horizon_days, signal_date,
               thetadata_store, asof) -> dict | None
    Return an option_contract dict or None when the store lacks the symbol.

PICK RULE (pre-registered, display-only)
-----------------------------------------
OURS: selection rule documented here; all levels are display-only.

1. Source: site/factordata/us_standouts.json buy[] lane (nightly artifact).
2. Filter:
     a. conviction.band != "low"
     b. gate_go == True  → act_level >= 2  AND conviction.score >= 0  (normal mode)
        gate_go == False → act_level >= 2  OR  conviction.score >= 60 (caution mode)
   Reason: gate_go=False is a macro-caution flag; tighten score threshold, but
   don't eliminate imminent-entry (act_level>=2) setups entirely.
3. Sort: descending by conviction.score; ties broken by act_level descending.
4. Take up to N_CANDIDATES (default 6).
5. Exclude entries where entry_signal is null.
6. Exclude entries where dir != "up" (only BULL universe currently).

GEOMETRY RULES (OURS — display-only, pre-registered)
------------------------------------------------------
  invalidation = hold.invalidation if present
                 else max-protective of (20d swing low, entry − 2×ATR14)
                    for BULL: max(swing_low, entry − 2×ATR14)  [closest to entry]
                    for BEAR: min(swing_high, entry + 2×ATR14) [closest to entry]
  R = |entry − invalidation|  (risk unit)
  T1 = entry + 1.5 × R  (BULL)  or  entry − 1.5 × R  (BEAR)
  T2 = entry + 3.0 × R  (BULL)  or  entry − 3.0 × R  (BEAR)
  horizon_days = 45 default
  min_hold_days = 10 default

ID STABILITY
------------
  <TICKER>-<DIRECTION>-<signal_date>
  signal_date = us_standouts as_of field (or hold.anchor if present).
  Plans persist across runs until invalidated/expired/T2-hit.
  Re-origination is suppressed when the ID already exists in existing_ids.

OPTION RESOLUTION (display-only)
---------------------------------
  expiry   = nearest monthly expiry >= signal_date + horizon_days + 15d
  strike   = nearest strike to 0.60-delta CALL (BULL) / PUT (BEAR)
             if greeks available; else first OTM strike from EOD data
  premium  = latest EOD mid-price (bid+ask)/2 at the chosen strike/expiry
  Null + honest note when store lacks the symbol or no greeks row found.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

N_CANDIDATES = 6          # max picks per run
HORIZON_DAYS_DEFAULT = 45
MIN_HOLD_DAYS_DEFAULT = 10
T1_MULTIPLIER = 1.5
T2_MULTIPLIER = 3.0
ATR_MULTIPLIER = 2.0       # invalidation = entry ± 2×ATR14 (protective backstop)
TARGET_DELTA = 0.60        # nearest-delta strike for option resolution

# Monthly expiry calendar helper: US options use 3rd Friday of month.
# We find the first monthly expiry >= min_expiry_date.
_MONTHS = range(1, 13)


def _third_friday(year: int, month: int) -> date:
    """Return the 3rd Friday of the given month/year."""
    first = date(year, month, 1)
    # weekday(): Mon=0 ... Fri=4
    day_of_week = first.weekday()
    # days until first Friday
    days_to_friday = (4 - day_of_week) % 7
    first_friday = first + timedelta(days=days_to_friday)
    return first_friday + timedelta(weeks=2)


def _next_monthly_expiry(min_date: date) -> date:
    """Return the nearest monthly (3rd Friday) expiry >= min_date."""
    y, m = min_date.year, min_date.month
    for _ in range(24):  # search up to 2 years
        tf = _third_friday(y, m)
        if tf >= min_date:
            return tf
        m += 1
        if m > 12:
            m = 1
            y += 1
    raise ValueError(f"Could not find monthly expiry after {min_date}")


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _swing_low_20d(price_history: pd.DataFrame, asof: str) -> float | None:
    """Return the 20-day swing low (lowest close) on or before asof."""
    try:
        asof_ts = pd.Timestamp(asof)
        mask = price_history.index <= asof_ts
        subset = price_history[mask].tail(20)
        if subset.empty:
            return None
        return float(subset["close"].min())
    except Exception:
        return None


def _swing_high_20d(price_history: pd.DataFrame, asof: str) -> float | None:
    """Return the 20-day swing high (highest close) on or before asof."""
    try:
        asof_ts = pd.Timestamp(asof)
        mask = price_history.index <= asof_ts
        subset = price_history[mask].tail(20)
        if subset.empty:
            return None
        return float(subset["close"].max())
    except Exception:
        return None


def compute_geometry(
    entry: float,
    direction: str,  # "BULL" or "BEAR"
    atr_pct: float | None,
    hold_invalidation: float | None,
    price_history: pd.DataFrame | None,
    asof: str,
) -> dict[str, float | None]:
    """
    OURS: Compute invalidation, T1, T2 from the pre-registered geometry rules.

    Returns a dict with keys: invalidation, t1, t2, r_unit.
    All values are floats or None.
    """
    atr_abs = (entry * atr_pct / 100.0) if atr_pct else None

    # --- Compute protective invalidation ---
    if hold_invalidation is not None:
        # Use swing-structure hard invalidation from hold field (preferred)
        invalidation = float(hold_invalidation)
    else:
        # Fallback: max-protective of (20d swing level, entry ± 2×ATR14)
        if direction == "BULL":
            swing = _swing_low_20d(price_history, asof) if price_history is not None else None
            atr_stop = (entry - ATR_MULTIPLIER * atr_abs) if atr_abs else None
            candidates = [c for c in [swing, atr_stop] if c is not None]
            # Most protective = highest (closest to entry from below)
            invalidation = max(candidates) if candidates else None
        else:  # BEAR
            swing = _swing_high_20d(price_history, asof) if price_history is not None else None
            atr_stop = (entry + ATR_MULTIPLIER * atr_abs) if atr_abs else None
            candidates = [c for c in [swing, atr_stop] if c is not None]
            # Most protective = lowest (closest to entry from above)
            invalidation = min(candidates) if candidates else None

    if invalidation is None:
        return {"invalidation": None, "t1": None, "t2": None, "r_unit": None}

    r_unit = abs(entry - invalidation)

    if direction == "BULL":
        t1 = entry + T1_MULTIPLIER * r_unit
        t2 = entry + T2_MULTIPLIER * r_unit
    else:
        t1 = entry - T1_MULTIPLIER * r_unit
        t2 = entry - T2_MULTIPLIER * r_unit

    return {
        "invalidation": round(invalidation, 4),
        "t1": round(t1, 4),
        "t2": round(t2, 4),
        "r_unit": round(r_unit, 4),
    }


# ---------------------------------------------------------------------------
# Pick selection
# ---------------------------------------------------------------------------

def select_candidates(
    standouts: dict,
    n: int = N_CANDIDATES,
) -> list[dict]:
    """
    Apply the pre-registered pick rule to us_standouts.json and return
    a filtered, sorted list of at most n buy entries.

    OURS (pre-registered pick rule):
      gate_go=True  → act_level >= 2 AND band != 'low'
      gate_go=False → (act_level >= 2 OR score >= 60) AND band != 'low'
    """
    gate_go: bool = standouts.get("gate_go", False)
    buys: list[dict] = standouts.get("buy", [])

    selected: list[dict] = []
    for b in buys:
        # entry_signal null => skip
        es = b.get("entry_signal")
        if not es:
            continue
        # direction filter — only BULL universe
        if b.get("dir", "up") != "up":
            continue
        conv = b.get("conviction") or {}
        band = conv.get("band", "")
        score = conv.get("score", 0) or 0
        act_level = es.get("act_level", 0) or 0

        if band == "low":
            continue

        if gate_go:
            if not (act_level >= 2):
                continue
        else:
            # caution mode: OR logic
            if not (act_level >= 2 or score >= 60):
                continue

        selected.append(b)

    # Sort: score desc, then act_level desc
    selected.sort(key=lambda x: (
        -(x.get("conviction") or {}).get("score", 0),
        -((x.get("entry_signal") or {}).get("act_level") or 0),
    ))
    return selected[:n]


# ---------------------------------------------------------------------------
# Thesis template (deterministic, no LLM)
# ---------------------------------------------------------------------------

_VALIDATED_PAT = re.compile(r"\b(validated|已验证)\b", re.IGNORECASE)
_VALIDATED_PAT_ZH = re.compile(r"已验证", re.IGNORECASE)
_VALIDATED_PAT_EN = re.compile(r"\bvalidated\b", re.IGNORECASE)


def _sanitize_thesis_text(text: str) -> str:
    """Strip forbidden 'validated'/'已验证' tokens from thesis driver/caution strings.

    The plan JSON is rendered user-facing (terminal oracle-tab). House law forbids
    affirmative 'validated' claims outside the allowlist gate. Source conviction
    drivers/cautions may carry these tokens (e.g. 'validated risk gate: trim').
    Replace them with 'risk gate' to preserve the semantic content without the claim.
    """
    return _VALIDATED_PAT.sub("risk gate", text)


def _sanitize_thesis_text_zh(text: str) -> str:
    """ZH counterpart of _sanitize_thesis_text — replaces forbidden tokens with ZH equivalents.
    '已验证' → '风险管控'; 'validated' (EN in ZH context) → '风险管控'."""
    text = _VALIDATED_PAT_ZH.sub("风险管控", text)
    text = _VALIDATED_PAT_EN.sub("风险管控", text)
    return text


def _build_thesis(ticker: str, b: dict) -> str:
    """
    OURS: Build a 2-3 sentence deterministic thesis woven from the candidate's
    actual drivers, cautions, and technical flags (above200, weekly_bull, coiled,
    washout_ctx, dc phase).  Mechanical, specific, no predictive claims, no
    "validated".  Display-only.
    """
    conv = b.get("conviction") or {}
    es = b.get("entry_signal") or {}
    hold = b.get("hold") or {}
    drivers = conv.get("drivers", []) or []
    cautions = conv.get("cautions", []) or []
    score = conv.get("score", "N/A")
    band = conv.get("band", "N/A")

    # ── Sentence 1: technical setup summary ──────────────────────────────────
    tech_flags: list[str] = []
    if es.get("above200"):
        tech_flags.append("above 200-day moving average")
    if es.get("weekly_bull"):
        tech_flags.append("weekly structure bullish")
    if es.get("coiled"):
        tech_flags.append("coiled compression setup")
    washout = es.get("washout_ctx") or hold.get("washout_ctx")
    if washout:
        tech_flags.append("post-washout recovery context")
    dc_phase = hold.get("dc_phase") or es.get("dc_phase")
    if dc_phase:
        tech_flags.append(f"Donchian phase: {dc_phase}")

    entry_grade = es.get("entry_grade") or ""
    archetype = b.get("archetype") or b.get("setup_type") or ""

    s1_parts = [f"{ticker} — conviction {score}/100 ({band})"]
    if tech_flags:
        s1_parts.append(f"Technical context: {'; '.join(tech_flags[:3])}.")
    elif entry_grade:
        s1_parts.append(f"Entry grade: {entry_grade}.")
    if archetype:
        s1_parts.append(f"Setup type: {archetype}.")
    sentence1 = " ".join(s1_parts).strip()

    # ── Sentence 2: conviction drivers (actual strings from the engine) ───────
    sentence2 = ""
    if drivers:
        sanitized = [_sanitize_thesis_text(str(d)) for d in drivers[:3]]
        sentence2 = f"Drivers: {'; '.join(sanitized)}."

    # ── Sentence 3: cautions and trust tier ──────────────────────────────────
    sentence3_parts: list[str] = []
    if cautions:
        sanitized_c = [_sanitize_thesis_text(str(c)) for c in cautions[:2]]
        sentence3_parts.append(f"Cautions: {'; '.join(sanitized_c)}.")
    trust = (conv.get("trust_tier") or {}).get("en", "")
    if trust:
        sentence3_parts.append(f"Trust tier: {trust}.")
    sentence3 = " ".join(sentence3_parts)

    # ── Assemble + honesty footer ─────────────────────────────────────────────
    parts = [sentence1]
    if sentence2:
        parts.append(sentence2)
    if sentence3:
        parts.append(sentence3)
    parts.append(
        "DISPLAY-ONLY: machine-generated from factor scores; no forward return"
        " guarantee; display-tier artifact."
    )
    return " ".join(parts)


def _build_thesis_zh(ticker: str, b: dict) -> str:
    """ZH counterpart of _build_thesis — same deterministic template, translated strings.
    Data interpolation (ticker, score, prices) is unchanged; no LLM at runtime."""
    conv = b.get("conviction") or {}
    es = b.get("entry_signal") or {}
    hold = b.get("hold") or {}
    drivers_zh = conv.get("drivers_zh", []) or conv.get("drivers", []) or []
    cautions_zh = conv.get("cautions_zh", []) or conv.get("cautions", []) or []
    score = conv.get("score", "N/A")
    band = conv.get("band", "N/A")

    # Band translation map
    _BAND_ZH = {"high": "高", "constructive": "积极", "neutral": "中性",
                "caution": "留意", "avoid": "回避"}
    band_zh = _BAND_ZH.get(str(band), str(band))

    tech_flags_zh: list[str] = []
    if es.get("above200"):
        tech_flags_zh.append("站上200日均线")
    if es.get("weekly_bull"):
        tech_flags_zh.append("周线结构看多")
    if es.get("coiled"):
        tech_flags_zh.append("盘整蓄势形态")
    washout = es.get("washout_ctx") or hold.get("washout_ctx")
    if washout:
        tech_flags_zh.append("超跌回暖背景")
    dc_phase = hold.get("dc_phase") or es.get("dc_phase")
    if dc_phase:
        tech_flags_zh.append(f"唐奇安阶段: {dc_phase}")

    entry_grade = es.get("entry_grade") or ""
    archetype = b.get("archetype") or b.get("setup_type") or ""

    s1_parts = [f"{ticker} — 确信度 {score}/100（{band_zh}）"]
    if tech_flags_zh:
        s1_parts.append(f"技术背景: {'; '.join(tech_flags_zh[:3])}。")
    elif entry_grade:
        s1_parts.append(f"入场评级: {entry_grade}。")
    if archetype:
        s1_parts.append(f"形态类型: {archetype}。")
    sentence1 = " ".join(s1_parts).strip()

    sentence2 = ""
    if drivers_zh:
        sanitized = [_sanitize_thesis_text_zh(str(d)) for d in drivers_zh[:3]]
        sentence2 = f"驱动因素: {'; '.join(sanitized)}。"

    sentence3_parts: list[str] = []
    if cautions_zh:
        sanitized_c = [_sanitize_thesis_text_zh(str(c)) for c in cautions_zh[:2]]
        sentence3_parts.append(f"注意事项: {'; '.join(sanitized_c)}。")
    trust_zh = (conv.get("trust_tier") or {}).get("zh", "")
    if trust_zh:
        sentence3_parts.append(f"可信度: {trust_zh}。")
    sentence3 = " ".join(sentence3_parts)

    parts = [sentence1]
    if sentence2:
        parts.append(sentence2)
    if sentence3:
        parts.append(sentence3)
    parts.append("仅供展示：由因子分数机器生成；无前瞻收益保证；展示层级输出。")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Content blocks: what_to_do_now, profit_plan
# (deterministic templates — NO LLM — keyed to phase + price levels)
# ---------------------------------------------------------------------------

def _fmt_price(price: float | None) -> str:
    """Format a price for display, or return '—' if None."""
    if price is None:
        return "—"
    return f"${price:.2f}"


def _build_what_to_do_now(
    phase: str,
    entry: float | None,
    trigger: float | None,
    invalidation: float | None,
    t1: float | None,
    t2: float | None,
    tranche: int = 1,
) -> list[str]:
    """
    OURS: Build 2-3 numbered actionable lines keyed to lifecycle phase.
    Phase-dependent templates with price levels interpolated from plan fields.
    Display-only — no predictive claims.

    Returns a list of strings (one per numbered bullet).
    """
    trigger_str = _fmt_price(trigger)
    t1_str = _fmt_price(t1)
    t2_str = _fmt_price(t2)
    inval_str = _fmt_price(invalidation)

    if phase == "pre_trigger":
        lines = [
            f"Watch for price to reach the trigger level ({trigger_str}) before"
            f" entering. No position until trigger is confirmed.",
            f"Keep size small on initial entry; the buy zone extends from trigger"
            f" up to {t1_str} (T1). There is no need to rush.",
        ]
        if t2 is not None:
            lines.append(
                f"If trigger confirms, scale in gradually. Invalidation is"
                f" {inval_str}; exit on a close below that level."
            )
        return lines

    if phase in ("triggered_pre_t1", "triggered_pre_t1"):
        lines = [
            f"Trigger is confirmed. Hold the current position and let the trade"
            f" advance toward T1 ({t1_str}).",
            f"Add to the position on short-term pullbacks as long as price remains"
            f" above {inval_str} (invalidation level).",
        ]
        if t2 is not None:
            lines.append(
                f"Continue building as the move confirms. Full position size"
                f" targets T2 at {t2_str}. Do not chase — add into weakness."
            )
        return lines

    if phase in ("at_t1", "between_t1_t2"):
        lines = [
            f"T1 ({t1_str}) has been reached. Scale out approximately 40% of the"
            f" position here and trail stop to entry ({_fmt_price(entry)}).",
        ]
        if t2 is not None:
            lines.append(
                f"Hold the remaining position for T2 ({t2_str}). Trail stop"
                f" to breakeven to protect against a reversal."
            )
        lines.append(
            f"T2 at {t2_str} — let remaining position run unless price closes"
            f" back below {t1_str}."
            if t2 is not None else
            f"No T2 defined. Consider closing fully or trailing stop closely."
        )
        return lines[:3]

    if phase == "post_t1_failed_hold":
        return [
            f"Trade gave back gains after T1. Reduce exposure — trim to a smaller"
            f" position or exit if price closes below entry ({_fmt_price(entry)}).",
            f"Invalidation is {inval_str}. A close below that level is a full exit"
            f" signal.",
            f"Do not add here. Re-assess if price reclaims {t1_str} (T1) on volume.",
        ]

    if phase in ("at_t2", "post_t2"):
        lines = [
            f"T2 ({t2_str}) has been reached. Close the majority of the position"
            f" (approximately 60–80%).",
            f"Trail stop on any remaining shares to protect profits. Consider"
            f" a hard stop at T1 ({t1_str}) for the residual position.",
        ]
        return lines

    if phase == "overtime":
        return [
            f"Trade has exceeded its intended horizon without reaching T1 ({t1_str})."
            f" Reassess thesis strength.",
            f"Trim position to reduce time-decay risk. A close below"
            f" {inval_str} (invalidation) is a full exit signal.",
            f"Do not add to the position in overtime. Either T1 is reached soon"
            f" or the setup is deferred.",
        ]

    if phase == "invalidated":
        return [
            f"Invalidation level ({inval_str}) has been breached."
            f" Exit the full position.",
            f"This plan is no longer active. Do not hold through invalidation.",
        ]

    # Fallback for unknown phases
    return [
        f"Monitor price relative to trigger ({trigger_str}) and T1 ({t1_str}).",
        f"Exit on a close below invalidation ({inval_str}).",
    ]


def _build_what_to_do_now_zh(
    phase: str,
    entry: float | None,
    trigger: float | None,
    invalidation: float | None,
    t1: float | None,
    t2: float | None,
    tranche: int = 1,
) -> list[str]:
    """ZH counterpart of _build_what_to_do_now — translated template strings,
    identical data interpolation. No LLM at runtime."""
    trigger_str = _fmt_price(trigger)
    t1_str = _fmt_price(t1)
    t2_str = _fmt_price(t2)
    inval_str = _fmt_price(invalidation)

    if phase == "pre_trigger":
        lines = [
            f"等待价格触及触发点（{trigger_str}）后再入场，触发确认前不建仓。",
            f"初始建仓保持小仓位；买入区间从触发点延伸至 {t1_str}（T1），无需急于入场。",
        ]
        if t2 is not None:
            lines.append(
                f"触发确认后逐步加仓。止损参考位为 {inval_str}，收盘跌破该位即离场。"
            )
        return lines

    if phase in ("triggered_pre_t1",):
        lines = [
            f"触发点已确认。持有当前仓位，等待价格向 T1（{t1_str}）推进。",
            f"只要价格维持在 {inval_str}（无效化位）上方，可在短期回调中加仓。",
        ]
        if t2 is not None:
            lines.append(
                f"行情持续确认后继续加仓，目标 T2 为 {t2_str}。勿追高，回调时加仓。"
            )
        return lines

    if phase in ("at_t1", "between_t1_t2"):
        lines = [
            f"T1（{t1_str}）已达到。在此减仓约 40%，将止损上移至入场位（{_fmt_price(entry)}）。",
        ]
        if t2 is not None:
            lines.append(
                f"剩余仓位持有待 T2（{t2_str}）。将止损移至盈亏平衡点以防反转。"
            )
        lines.append(
            f"T2 目标为 {t2_str}——除非价格收盘回落至 {t1_str} 下方，否则让剩余仓位继续运行。"
            if t2 is not None else
            f"无 T2 目标。考虑全部平仓或紧追止损。"
        )
        return lines[:3]

    if phase == "post_t1_failed_hold":
        return [
            f"T1 后涨幅回吐。减少敞口——减仓或若价格收盘跌破入场位（{_fmt_price(entry)}）则离场。",
            f"无效化位为 {inval_str}，收盘跌破该位即全部离场。",
            f"不要在此加仓。若价格放量重新站上 {t1_str}（T1），再重新评估。",
        ]

    if phase in ("at_t2", "post_t2"):
        lines = [
            f"T2（{t2_str}）已达到。平掉大部分仓位（约 60–80%）。",
            f"剩余仓位追踪止损以保护盈利。考虑将止损硬停在 T1（{t1_str}）。",
        ]
        return lines

    if phase == "overtime":
        return [
            f"交易超出预期持有周期但未达 T1（{t1_str}）。重新评估论点。",
            f"减仓以降低时间风险。收盘跌破 {inval_str}（无效化位）即全部离场。",
            f"超时期间不要加仓。等待 T1 尽快达到，否则该形态推迟执行。",
        ]

    if phase == "invalidated":
        return [
            f"无效化位（{inval_str}）已被突破，全部离场。",
            f"该计划已失效，不要持仓硬撑。",
        ]

    # Fallback
    return [
        f"监测价格相对于触发点（{trigger_str}）和 T1（{t1_str}）的表现。",
        f"收盘跌破无效化位（{inval_str}）即离场。",
    ]


def _build_profit_plan(
    phase: str,
    entry: float | None,
    t1: float | None,
    t2: float | None,
    p1: float | None = None,
    p2: float | None = None,
) -> list[dict]:
    """
    OURS: Build profit-taking plan rows.

    Each row: {level: float|None, label: str, action: str, status: str}
    status ∈ ACTIVE | PENDING | DONE
    Derived from geometry/phase.  Display-only.
    """
    rows: list[dict] = []

    # T1 row
    t1_status: str
    if phase in ("at_t1", "between_t1_t2", "post_t1_failed_hold", "at_t2", "post_t2"):
        t1_status = "DONE"
    elif phase == "invalidated":
        t1_status = "DONE"  # plan terminated
    else:
        t1_status = "ACTIVE"  # awaiting T1

    rows.append({
        "level": t1,
        "label": "T1",
        "action": "Scale out 40%, trail stop to entry",
        "status": t1_status,
    })

    # T2 row (only if T2 is defined)
    if t2 is not None:
        t2_status: str
        if phase in ("at_t2", "post_t2"):
            t2_status = "DONE"
        elif phase in ("at_t1", "between_t1_t2"):
            # T1 done, T2 next
            t2_status = "ACTIVE"
        else:
            t2_status = "PENDING"
        rows.append({
            "level": t2,
            "label": "T2",
            "action": "Close remaining 60%, exit full position",
            "status": t2_status,
        })

    return rows


def _build_profit_plan_zh(
    phase: str,
    entry: float | None,
    t1: float | None,
    t2: float | None,
    p1: float | None = None,
    p2: float | None = None,
) -> list[dict]:
    """ZH counterpart of _build_profit_plan — same row structure, translated action strings.
    label stays "T1"/"T2" (universal); action_zh added per row. No LLM at runtime."""
    rows: list[dict] = []

    t1_status: str
    if phase in ("at_t1", "between_t1_t2", "post_t1_failed_hold", "at_t2", "post_t2"):
        t1_status = "DONE"
    elif phase == "invalidated":
        t1_status = "DONE"
    else:
        t1_status = "ACTIVE"

    rows.append({
        "level": t1,
        "label": "T1",
        "action": "减仓 40%，将止损上移至入场位",
        "status": t1_status,
    })

    if t2 is not None:
        t2_status: str
        if phase in ("at_t2", "post_t2"):
            t2_status = "DONE"
        elif phase in ("at_t1", "between_t1_t2"):
            t2_status = "ACTIVE"
        else:
            t2_status = "PENDING"
        rows.append({
            "level": t2,
            "label": "T2",
            "action": "平仓剩余 60%，全部离场",
            "status": t2_status,
        })

    return rows


# ---------------------------------------------------------------------------
# ID construction
# ---------------------------------------------------------------------------

def _make_id(ticker: str, direction: str, signal_date: str) -> str:
    """Stable plan ID: <TICKER>-<DIRECTION>-<signal_date>."""
    clean_date = signal_date.replace("-", "")
    return f"{ticker}-{direction}-{clean_date}"


# ---------------------------------------------------------------------------
# Option resolution
# ---------------------------------------------------------------------------

def _load_greeks(ticker: str, thetadata_store: str, asof: str) -> pd.DataFrame | None:
    """Load greeks for the asof year; return None if not found."""
    year = asof[:4]
    path = Path(thetadata_store) / "greeks" / ticker / f"{year}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        return df
    except Exception as e:
        log.warning("prophet_bridge: failed to load greeks for %s: %s", ticker, e)
        return None


def _load_eod(ticker: str, thetadata_store: str, asof: str) -> pd.DataFrame | None:
    """Load EOD for the asof year; return None if not found."""
    year = asof[:4]
    path = Path(thetadata_store) / "eod" / ticker / f"{year}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        return df
    except Exception as e:
        log.warning("prophet_bridge: failed to load EOD for %s: %s", ticker, e)
        return None


def resolve_option(
    ticker: str,
    direction: str,
    entry: float,
    horizon_days: int,
    signal_date: str,
    thetadata_store: str | None,
    asof: str,
) -> dict | None:
    """
    Resolve an option contract for the plan.

    Returns option_contract dict or None + logs an honest note.

    OURS (display-only):
      right    = C (BULL) / P (BEAR)
      expiry   = nearest monthly >= signal_date + horizon_days + 15d
      strike   = nearest strike to 0.60-delta; else first OTM strike from EOD
      premium  = EOD mid (bid+ask)/2 at the chosen contract on asof date
    """
    if not thetadata_store:
        log.info("prophet_bridge: THETADATA_STORE not set; option rec skipped for %s", ticker)
        return None

    right = "C" if direction == "BULL" else "P"
    try:
        sig = date.fromisoformat(signal_date)
    except ValueError:
        log.warning("prophet_bridge: bad signal_date %r for %s", signal_date, ticker)
        return None

    min_expiry = sig + timedelta(days=horizon_days + 15)
    try:
        target_expiry = _next_monthly_expiry(min_expiry)
    except ValueError as e:
        log.warning("prophet_bridge: expiry search failed for %s: %s", ticker, e)
        return None

    expiry_str = target_expiry.isoformat()

    # --- Try to find the 0.60-delta strike from greeks ---
    greeks = _load_greeks(ticker, thetadata_store, asof)
    if greeks is not None:
        asof_ts = pd.Timestamp(asof)
        exp_ts = pd.Timestamp(target_expiry)

        mask = (
            (greeks["date"] == asof_ts)
            & (greeks["expiration"] == exp_ts)
            & (greeks["right"] == right)
        )
        subset = greeks[mask]

        if not subset.empty:
            # For CALL: want delta closest to +0.60
            # For PUT: want delta closest to -0.60
            target_delta_val = TARGET_DELTA if right == "C" else -TARGET_DELTA
            idx = (subset["delta"] - target_delta_val).abs().idxmin()
            row = subset.loc[idx]
            strike = float(row["strike"])
            bid = float(row.get("bid", 0) or 0)
            ask = float(row.get("ask", 0) or 0)
            premium = round((bid + ask) / 2, 4) if (bid or ask) else None
            return {
                "right": right,
                "strike": strike,
                "expiry": expiry_str,
                "entry_premium": premium,
                "freshness": "EOD mark",
                "delta_approx": round(float(row["delta"]), 4),
                "note": f"delta-targeted ({TARGET_DELTA:.2f})",
            }

    # --- Fallback: first OTM strike from EOD ---
    eod = _load_eod(ticker, thetadata_store, asof)
    if eod is not None:
        asof_ts = pd.Timestamp(asof)
        exp_ts = pd.Timestamp(target_expiry)

        if "date" in eod.columns:
            date_col = "date"
        elif "Date" in eod.columns:
            date_col = "Date"
        else:
            date_col = None

        if date_col:
            mask = (
                (eod[date_col] == asof_ts)
                & (eod.get("expiration", eod.get("Expiration", pd.Series(dtype=object))) == exp_ts)
                & (eod.get("right", eod.get("Right", pd.Series(dtype=object))) == right)
            )
            subset = eod[mask]
            if not subset.empty:
                # First OTM: CALL above entry, PUT below entry
                strike_col = "strike" if "strike" in subset.columns else "Strike"
                if right == "C":
                    otm = subset[subset[strike_col] >= entry]
                else:
                    otm = subset[subset[strike_col] <= entry]
                if not otm.empty:
                    row = otm.iloc[0] if right == "C" else otm.iloc[-1]
                    strike = float(row[strike_col])
                    bid = float(row.get("bid", 0) or 0)
                    ask = float(row.get("ask", 0) or 0)
                    premium = round((bid + ask) / 2, 4) if (bid or ask) else None
                    return {
                        "right": right,
                        "strike": strike,
                        "expiry": expiry_str,
                        "entry_premium": premium,
                        "freshness": "EOD mark",
                        "delta_approx": None,
                        "note": "greeks unavailable; first-OTM strike from EOD",
                    }

    log.info(
        "prophet_bridge: no option data for %s %s %s in store %s; rec=null",
        ticker, right, expiry_str, thetadata_store,
    )
    return None


# ---------------------------------------------------------------------------
# Plan origination
# ---------------------------------------------------------------------------

def _load_price_history(ticker: str) -> pd.DataFrame | None:
    """Load price history from baskets/ohlcv → stocks fallback."""
    repo = Path(__file__).resolve().parent.parent
    for sub in ["data/baskets/ohlcv", "data/stocks"]:
        p = repo / sub / f"{ticker}.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                if not isinstance(df.index, pd.DatetimeIndex):
                    if "date" in df.columns:
                        df = df.set_index("date")
                    elif "Date" in df.columns:
                        df = df.set_index("Date")
                df.index = pd.to_datetime(df.index)
                return df
            except Exception as e:
                log.warning("prophet_bridge: price history load failed %s: %s", ticker, e)
    return None


def originate_plans(
    standouts_path: str | Path,
    asof: str,
    existing_ids: set[str],
    thetadata_store: str | None = None,
) -> list[dict]:
    """
    Read us_standouts.json, apply the pick rule, and return new
    prophet.trade_plan/v1 dicts for IDs not in existing_ids.

    Parameters
    ----------
    standouts_path : path to site/factordata/us_standouts.json
    asof           : ISO-8601 date string — sole time anchor
    existing_ids   : set of plan IDs already persisted (duplicate suppression)
    thetadata_store: path to ThetaData EOD store root

    Returns
    -------
    list of prophet.trade_plan/v1 dicts (validated before return)
    """
    from engine.options_structure import validate_trade_plan  # noqa: PLC0415

    standouts_path = Path(standouts_path)
    with standouts_path.open(encoding="utf-8") as f:
        standouts = json.load(f)

    standouts_asof = standouts.get("as_of", asof)

    candidates = select_candidates(standouts, n=N_CANDIDATES)
    log.info(
        "prophet_bridge: %d candidates selected (gate_go=%s)",
        len(candidates), standouts.get("gate_go"),
    )

    plans: list[dict] = []
    for b in candidates:
        ticker: str = b["ticker"]
        direction = "BULL"  # all dir="up" entries

        # Signal date: use hold.anchor if present, else standouts as_of
        hold = b.get("hold") or {}
        anchor = hold.get("anchor")
        signal_date = anchor if anchor else standouts_asof

        plan_id = _make_id(ticker, direction, signal_date)

        if plan_id in existing_ids:
            log.info("prophet_bridge: suppressing duplicate %s", plan_id)
            continue

        es = b.get("entry_signal") or {}
        conv = b.get("conviction") or {}

        # Entry: spot from entry_signal (latest close proxy)
        spot = es.get("spot")
        if spot is None:
            log.warning("prophet_bridge: no spot for %s; skipping", ticker)
            continue
        entry = float(spot)

        # Trigger: chase_above breakout level if present, else entry
        chase_above = es.get("chase_above")
        trigger = float(chase_above) if chase_above else entry

        # Confidence from conviction score (0-100 → capped at 92 in engine)
        confidence = min(float(conv.get("score", 60)), 92.0)

        # Price history for swing-level geometry fallback
        ph = _load_price_history(ticker)

        # ATR from entry_signal.atr_pct
        atr_pct = es.get("atr_pct")

        # Geometry
        geo = compute_geometry(
            entry=entry,
            direction=direction,
            atr_pct=float(atr_pct) if atr_pct else None,
            hold_invalidation=hold.get("invalidation"),
            price_history=ph,
            asof=standouts_asof,
        )

        # Option contract
        opt = resolve_option(
            ticker=ticker,
            direction=direction,
            entry=entry,
            horizon_days=HORIZON_DAYS_DEFAULT,
            signal_date=signal_date,
            thetadata_store=thetadata_store,
            asof=standouts_asof,
        )

        # ── Content blocks (deterministic, NO LLM) ─────────────────────────
        # Origination phase is always pre_trigger; content blocks are keyed
        # to phase so they can be regenerated by the management engine later.
        init_phase = "pre_trigger"
        t1_price = geo["t1"]
        t2_price = geo["t2"]

        what_to_do_now = _build_what_to_do_now(
            phase=init_phase,
            entry=entry,
            trigger=trigger,
            invalidation=geo["invalidation"],
            t1=t1_price,
            t2=t2_price,
            tranche=1,
        )
        what_to_do_now_zh = _build_what_to_do_now_zh(
            phase=init_phase,
            entry=entry,
            trigger=trigger,
            invalidation=geo["invalidation"],
            t1=t1_price,
            t2=t2_price,
            tranche=1,
        )
        profit_plan = _build_profit_plan(
            phase=init_phase,
            entry=entry,
            t1=t1_price,
            t2=t2_price,
            p1=0.0,
            p2=0.0 if t2_price is not None else None,
        )
        profit_plan_zh = _build_profit_plan_zh(
            phase=init_phase,
            entry=entry,
            t1=t1_price,
            t2=t2_price,
            p1=0.0,
            p2=0.0 if t2_price is not None else None,
        )

        # Build the plan dict
        plan: dict[str, Any] = {
            "schema": "prophet.trade_plan/v1",
            "id": plan_id,
            "asof": asof,
            "asset": ticker,
            "direction": direction,
            "thesis": _build_thesis(ticker, b),
            "thesis_zh": _build_thesis_zh(ticker, b),
            "source_engines": ["us_standouts_buy_lane", "neural_web"],
            "trigger": round(trigger, 4),
            "entry": round(entry, 4),
            "invalidation": geo["invalidation"],
            "targets": [
                t for t in [t1_price, t2_price] if t is not None
            ],
            "horizon_days": HORIZON_DAYS_DEFAULT,
            "min_hold_days": MIN_HOLD_DAYS_DEFAULT,
            "tranche": 1,
            "option_contract": opt,
            "management_ref": f"prophet/state/{plan_id}.json",
            "authority_tier": "display",
            "reliability": {
                "plan": (
                    "display — us_standouts buy-lane originated; display-only until"
                    " forward ledger gate passes"
                ),
                "option_premium": (
                    "EOD mark — delayed; not NBBO-live; display-only"
                )
                if opt
                else "null — symbol not in ThetaData store",
            },
            # signal_date is the issuance anchor read by compute_management_state
            # (plan.get('signal_date')).  The underscore alias is kept for display.
            "signal_date": signal_date,
            # ── Content blocks (optional; graceful fallback on absence) ───────
            # These are regenerated by the management engine on each nightly run
            # with the current phase.  display-only artifact.
            "what_to_do_now": what_to_do_now,       # list[str] — numbered bullets (EN)
            "what_to_do_now_zh": what_to_do_now_zh, # list[str] — numbered bullets (ZH)
            "profit_plan": profit_plan,              # list[{level, label, action, status}] (EN)
            "profit_plan_zh": profit_plan_zh,        # list[{level, label, action, status}] (ZH)
            # Extra metadata (display)
            "_signal_date": signal_date,
            "_conviction_score": conv.get("score"),
            "_act_level": es.get("act_level"),
            "_r_unit": geo["r_unit"],
            "_gate_go": standouts.get("gate_go"),
        }

        # Validate
        from engine.options_structure import validate_trade_plan as _vtp  # noqa: PLC0415
        errs = _vtp(plan)
        if errs:
            log.warning(
                "prophet_bridge: plan %s failed validation: %s", plan_id, errs
            )
            continue

        plans.append(plan)
        existing_ids.add(plan_id)
        log.info(
            "prophet_bridge: originated plan %s entry=%.2f inval=%s T1=%s T2=%s opt=%s",
            plan_id,
            entry,
            geo["invalidation"],
            geo["t1"],
            geo["t2"],
            "Y" if opt else "N",
        )

    return plans
