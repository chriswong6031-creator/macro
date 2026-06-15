"""Narrative-Dominance Index (NDI) — how policy/geo-narrative-driven the tape is.

LEAF · DISPLAY/CONTEXT-ONLY · NO-OP GATE. Stage 3a of the narrative framework
(memory narrative-quant-framework). Blends the text-uncertainty regime (EPU + the
GPR THREAT component) with the market vol regime (VIX percentile) into one 0-100
"how narrative-dominated is the regime right now" read — a STATE variable, never a
direction.

Its only intended downstream use is a SUBTRACT-ONLY conditioner on the existing
momentum/technical signals (down-weight conviction, raise the confirmation bar when
narrative dominates). That wiring is GATED: `gate_multiplier` is hard-pinned to 1.0
(a no-op) until scripts/narrative_regime_phase0.py shows the text-uncertainty leg
adds forward-realized-vol content INCREMENTAL OVER VIX (Gate A) and that existing
signals degrade more in the narrative regime than in plain high-VIX (Gate B). The
honest prior (and the framework's own skeptic) is that this bar is NOT cleared —
that NDI is redundant with the dashboard's existing vol zoo — in which case NDI
stays a display banner and `gate_multiplier` stays 1.0 forever.

LEAF discipline: imports only lib.config + lib.store; nothing in the scoring core
imports it. Returns plain data or None; never raises into the build.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from lib import config, store

log = logging.getLogger(__name__)

SCHEMA = "narrative_regime.v1"

DISCLAIMER_TEXT = (
    "Context only — not a signal. The Narrative-Dominance Index blends policy "
    "uncertainty (EPU), geopolitical-threat risk (GPR-threat) and the market vol "
    "regime (VIX) into a 0-100 read of how NARRATIVE-driven the tape is. It measures "
    "forward VOLATILITY / risk, NOT market direction, and it does not (yet) change "
    "any score: it is shown as context while we test whether it adds anything beyond "
    "VIX. The gate that would let it down-weight momentum conviction is pinned OFF."
)
DISCLAIMER_TEXT_ZH = (
    "仅作背景，非信号。叙事主导指数将政策不确定性（EPU）、地缘威胁风险（GPR-威胁）与市场波动"
    "环境（VIX）合成为 0-100 的“行情受叙事驱动程度”读数。它度量的是前瞻波动率／风险，而非市场"
    "方向，且暂不改变任何评分：在验证它是否优于 VIX 之前仅作背景显示。允许其下调动量信心的闸门"
    "目前关闭。")


def _pct_of_history(series, value) -> float | None:
    """Full-history percentile (0-100) of `value` within `series`. None if thin."""
    try:
        import pandas as pd
        s = pd.to_numeric(series, errors="coerce").dropna()
        if len(s) < 250 or value is None or pd.isna(value):
            return None
        return round(float((s <= float(value)).mean()) * 100, 1)
    except Exception:  # noqa: BLE001
        return None


def _latest(group: str, name: str, col: str):
    """(latest_value, asof_date) for a stored series column, or (None, None)."""
    try:
        df = store.read(group, name)
        if df is None or df.empty or col not in df.columns:
            return None, None, None
        s = df[col].dropna()
        if s.empty:
            return None, None, df
        return float(s.iloc[-1]), s.index.max().date(), df
    except Exception:  # noqa: BLE001
        return None, None, None


def _band(ndi: float | None) -> str:
    if ndi is None:
        return "unknown"
    return "high" if ndi >= 80 else ("elevated" if ndi >= 50 else "calm")


def compute(asof: date | str | None = None) -> dict | None:
    """Build the NDI from the EPU/GPR uncertainty store + VIX. Returns the display
    dict (legs + composite + the pinned no-op gate) or None if no data. Never raises.
    """
    try:
        legs: dict = {}
        pcts: list[float] = []

        epu_v, epu_d, epu_df = _latest("uncertainty", "epu_us", "epu")
        if epu_v is not None:
            p = _pct_of_history(epu_df["epu"], epu_v)
            if p is not None:
                legs["epu"] = {"value": round(epu_v, 1), "pct": p, "asof": str(epu_d)}
                pcts.append(p)

        gpr_v, gpr_d, gpr_df = _latest("uncertainty", "gpr", "gpr")
        if gpr_v is not None and gpr_df is not None:
            # the THREAT component is the validated reversible-scare reader; prefer it.
            tcol = "gpr_threat" if "gpr_threat" in gpr_df.columns else "gpr"
            tv = float(gpr_df[tcol].dropna().iloc[-1])
            p = _pct_of_history(gpr_df[tcol], tv)
            if p is not None:
                lean = None
                if {"gpr_threat", "gpr_act"} <= set(gpr_df.columns):
                    last = gpr_df.dropna(subset=["gpr"]).iloc[-1]
                    t, a = float(last["gpr_threat"]), float(last["gpr_act"])
                    lean = "threat" if t > a else ("act" if a > t else "balanced")
                legs["gpr_threat"] = {"value": round(tv, 1), "pct": p,
                                      "asof": str(gpr_d), "lean": lean}
                pcts.append(p)

        vix_v, vix_d, vix_df = _latest("fred", "VIXCLS", "vix_close")
        if vix_v is not None:
            p = _pct_of_history(vix_df["vix_close"], vix_v)
            if p is not None:
                legs["vix"] = {"value": round(vix_v, 1), "pct": p, "asof": str(vix_d)}
                pcts.append(p)

        if not pcts:
            return None
        ndi = round(sum(pcts) / len(pcts), 1)
        return {
            "schema": SCHEMA,
            "is_context_only": True,
            "asof": (str(asof) if asof else str(date.today())),
            "built": datetime.now(timezone.utc).isoformat(),
            "ndi": ndi,
            "band": _band(ndi),
            "legs": legs,
            # P2 hook — pinned to 1.0 (no-op) until Gate A & Gate B clear. NEVER read
            # by any scoring module today; tests assert it stays 1.0.
            "gate_multiplier": 1.0,
            "gate_status": "pinned_off",
            "disclaimer": DISCLAIMER_TEXT,
            "disclaimer_zh": DISCLAIMER_TEXT_ZH,
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("narrative_regime.compute failed (%s)", e)
        return None
