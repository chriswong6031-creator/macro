"""Narrative-Dominance Index (NDI) — how policy/geo-narrative-driven the tape is.

LEAF · DISPLAY/CONTEXT-ONLY · NO-OP GATE · FAMILY RETIRED. Stage 3a of the
narrative framework (memory narrative-quant-framework). Blends the text-uncertainty
regime (EPU + the GPR THREAT component) with the market vol regime (VIX percentile)
into one 0-100 "how narrative-dominated is the regime right now" read — a STATE
variable, never a direction.

RETIREMENT RECORD (D7, 2026-07-02):
  Gate A (narrative_regime_phase0.py, 2026-06) falsified EPU+GPR on forward vol
  incremental over VIX. Gate D7 (narrative_realign_phase0.py, 2026-07-02) ran ONE
  salvage pass of the VIX-orthogonal NDI residual against two VIX-blind targets:
    (a) 21d forward cross-sectional sector-ETF dispersion — no horizon cleared FDR
        (best q=0.41 at h=5d), and the first-half IC sign was NEGATIVE (IC=-0.010)
        while the full-sample IC was positive — sign-unstable across halves. RETIRE.
    (b) Complacency-fade timing (SPY below trailing 6m mean) — all ICs near-zero,
        no horizon excl0. RETIRE.
  The SF-Fed Daily News Sentiment residual (SFED_resid) got the same single pass on
  the same targets: all ICs null, no excl0 at any horizon. RETIRE.

  Result: the lexical-uncertainty family (EPU/GPR NDI + SFED sentiment-z) is
  RETIRED. It ships as a display banner only; `gate_multiplier` is PERMANENTLY
  pinned to 1.0. This module must NOT be revived or promoted without re-running a
  full pre-registered harness on out-of-sample data — the D7 data is now in-sample.

  DO NOT modify `gate_multiplier` or `gate_status` in this file. The
  `_FAMILY_RETIRED` flag is a machine-readable guard the test suite asserts.

LEAF discipline: imports only lib.config + lib.store; nothing in the scoring core
imports it. Returns plain data or None; never raises into the build.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from lib import config, store

log = logging.getLogger(__name__)

SCHEMA = "narrative_regime.v1"

# D7 retirement flag — machine-readable guard. Set True 2026-07-02 after D7 salvage
# falsified both VIX-blind targets for EPU+GPR residual AND SFED sentiment residual.
# Tests assert this is True and that gate_multiplier == 1.0 simultaneously.
_FAMILY_RETIRED = True
_RETIRE_DATE = "2026-07-02"
_RETIRE_REASON = (
    "D7 salvage 2026-07-02: VIX-orthogonal NDI residual and SFED sentiment residual "
    "both null on (a) forward cross-sectional sector dispersion (best FDR q=0.41, "
    "sign-unstable halves) and (b) complacency-fade timing (IC near-zero, no excl0). "
    "Family retired — no further promotion without out-of-sample pre-registered harness."
)

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
            # Permanently pinned: Gate A (phase0) and D7 salvage both falsified the
            # lexical-uncertainty family. gate_multiplier MUST remain 1.0 forever;
            # gate_status MUST remain "retired". Tests assert both invariants.
            "gate_multiplier": 1.0,
            "gate_status": "retired",
            "family_retired": _FAMILY_RETIRED,
            "retire_date": _RETIRE_DATE,
            "retire_reason": _RETIRE_REASON,
            "disclaimer": DISCLAIMER_TEXT,
            "disclaimer_zh": DISCLAIMER_TEXT_ZH,
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("narrative_regime.compute failed (%s)", e)
        return None
