"""China AI-supply weekly slice confirmer — global AI-semis → CN CPO/PCB/storage_chip.

VALIDATED (#773, scripts/china_global_theme_backtest.py):
  SMH + SOXX + TSM 4-week log-momentum → next-week EW return of THS AI-supply baskets
  (cpo/pcb/storage_chip/adv_pkg/liquid_cool/aidc/ai).
  t-stat = 3.27 on cpo (univariate), survives the horse-race (SPY + CN-universe controls),
  survives the pre-2024 split (not just a 2024 AI-run artifact).

DISPLAY + JSON CHIP ONLY: no name-level gating, no score weighting.
Target pages: subsectors_china (THS concept board) and baskets_china_ths.
Targets by basket_id: ths_cpo, ths_pcb, ths_storage_chip (and secondarily
  ths_adv_pkg, ths_liquid_cool, ths_aidc, ths_ai).

Passport:
  basis: measured
  validation: scripts/china_global_theme_backtest.py, #773 (t=3.27, horse-race stable)
  consumers: subsectors_china board chip, baskets_china_ths board chip (display only)
  note: theme-slice unit only; does NOT gate name selection or name ranking.

Never raises. Degrades gracefully when Yahoo/semis parquets are absent.
"""
from __future__ import annotations

import logging
from datetime import date, timezone, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "cn_ai_semis_confirmer.v1"

# Validated targets (the baskets where t=3.27 survives the horse race)
AI_SUPPLY_BASKETS = frozenset([
    "ths_cpo", "ths_pcb", "ths_storage_chip",
    "ths_adv_pkg", "ths_liquid_cool", "ths_aidc", "ths_ai",
])

# Momentum window (weeks) — from the validated backtest
_MOM_WK = 4
# Signal threshold: treat the EW 4w log-momentum as ON when positive, OFF when negative.
# The backtest validated a linear relationship; we discretize to ON/OFF for the chip.
_SEMIS = ["SMH", "SOXX", "TSM"]


def _weekly_last_friday(s: pd.Series) -> pd.Series:
    """Resample to weekly, anchoring on Friday close (W-FRI). Matches the backtest."""
    s = s.dropna().sort_index()
    return s.resample("W-FRI").last().dropna()


def _read_close(name: str) -> pd.Series | None:
    """Read a yahoo close series. None on any miss."""
    try:
        p = config.data_dir() / "yahoo" / f"{name}.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        col = "close" if "close" in df.columns else df.columns[0]
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if s.empty:
            return None
        s.index = pd.to_datetime(s.index)
        return s.sort_index()
    except Exception as e:  # noqa: BLE001
        log.debug("cn_ai_semis_confirmer: read %s failed (%s)", name, e)
        return None


def compute() -> dict:
    """Compute the current global AI-semis confirmer state.

    Returns a JSON-serializable dict with:
      on: bool — True when the 4-week log-momentum of EW(SMH+SOXX+TSM) is positive
      semis_mom_4w: float | None — the raw 4-week log-momentum value
      as_of: str — date of the most recent data point
      targets: list[str] — basket IDs this confirmer applies to
      schema, passport

    Validated: scripts/china_global_theme_backtest.py #773.
    """
    try:
        series = [_read_close(s) for s in _SEMIS]
        valid = [s for s in series if s is not None]
        if len(valid) < 2:     # need at least 2 of 3 semis names
            return _null("semis parquets unavailable (<2 of 3 found)")

        # Align and compute EW return index, then resample to weekly
        aligned = pd.concat(valid, axis=1).ffill().dropna()
        if aligned.empty or len(aligned) < _MOM_WK * 7 + 14:
            return _null("insufficient history for 4-week momentum")

        ew_ret = (1 + aligned.pct_change()).product(axis=1) ** (1 / aligned.shape[1])
        ew_level = ew_ret.cumprod()
        weekly = _weekly_last_friday(ew_level)
        if len(weekly) < _MOM_WK + 2:
            return _null("not enough weekly bars")

        # 4-week log-momentum (the validated signal)
        mom_4w = float(np.log(weekly.iloc[-1] / weekly.iloc[-1 - _MOM_WK]))
        as_of = str(weekly.index[-1].date())

        on = bool(mom_4w > 0)
        state = "ON" if on else "OFF"
        label_en = f"Global AI-semis tailwind: {state} (SMH/SOXX/TSM 4w-mom {mom_4w:+.3f})"
        label_zh = (f"全球AI半导体顺风：{'开启' if on else '关闭'}"
                    f"（SMH/SOXX/TSM 4周动量 {mom_4w:+.3f}）")

        return {
            "schema": SCHEMA,
            "on": on,
            "state": state,
            "semis_mom_4w": round(mom_4w, 4),
            "as_of": as_of,
            "targets": sorted(AI_SUPPLY_BASKETS),
            "label_en": label_en,
            "label_zh": label_zh,
            "built": datetime.now(timezone.utc).isoformat(),
            "passport": {
                "basis": "measured",
                "validation": ("scripts/china_global_theme_backtest.py #773: "
                               "t=3.27 (cpo), horse-race stable, pre-2024 split survives"),
                "consumers": ["subsectors_china board chip", "baskets_china_ths board chip"],
                "display_only": True,
                "unit": "theme-slice (weekly, EW THS AI-supply basket return)",
                "note": "Does NOT gate name selection or name ranking. Chip only.",
            },
        }
    except Exception as e:  # noqa: BLE001 — confirmer is additive, never fatal
        log.warning("cn_ai_semis_confirmer.compute failed (%s)", e)
        return _null(str(e))


def _null(reason: str) -> dict:
    return {
        "schema": SCHEMA, "on": None, "state": "unavailable",
        "semis_mom_4w": None, "as_of": None,
        "targets": sorted(AI_SUPPLY_BASKETS),
        "label_en": "Global AI-semis confirmer: unavailable",
        "label_zh": "全球AI半导体确认器：不可用",
        "degraded_reason": reason,
        "passport": {"basis": "measured", "display_only": True, "degraded": True},
    }


def is_target_basket(basket_id: str) -> bool:
    """Return True when basket_id is an AI-supply target for this confirmer."""
    return str(basket_id) in AI_SUPPLY_BASKETS
