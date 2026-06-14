"""Forex Vector MTF — cycle-ladder + multi-timeframe technical read on the
FX-CALIBRATED cycle preset (cycles.analyze(kind="fx")).

Unlike the commodities MTF (equity preset), FX runs a MEASURED preset
(CYCLE_PRESETS["fx"], research/FOREX_DASHBOARD.md): across the G10 majors the daily
cycle low recurs ~35 trading days apart (IQR 25-47 — wider/noisier than equities) and
the intermediate cycle is ~34 weeks (vs ~16-26 for equities). The per-timeframe
RSI/Stoch/MACD states, the 2W/ME long timeframes, and the confluence verdict are
asset-agnostic and reused verbatim from engine.commodity_mtf.

Recomputed each build, never persisted. {} on any failure / too-short series.
"""
from __future__ import annotations

import pandas as pd

from engine import cycles, commodity_mtf

# the verdict fusion reads the ladder/mtf/cycle out of `a` (no re-run of cycles), so it
# is kind-agnostic — reuse it verbatim (FX macro-fusion zeroes out; pure technical read).
confluence_verdict = commodity_mtf.confluence_verdict


def mtf_ladder(close: pd.Series, high: pd.Series | None = None) -> dict:
    """Full cycle-ladder + 5-timeframe MTF for one pair on the FX preset."""
    try:
        c = close.dropna()
        h = (high if high is not None else close).dropna()
        a = cycles.analyze(c, h, kind="fx")              # FX-calibrated, NOT equity
        if not a or not a.get("ladder"):
            return {}
        a.setdefault("mtf", {}).update(commodity_mtf._long_timeframes(c))
        return a
    except Exception:  # noqa: BLE001 — overlay must never break the build
        return {}
