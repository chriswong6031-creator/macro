"""Central-Bank Desk — realized policy rates, last-change, 3m trend, BS impulse, next meeting.

ADDITIVE / pure-leaf: imports nothing from the scoring core. Reads stores via lib.store.
IRD-R7: DESCRIPTIVE ONLY — realized levels, realized changes, published dates.
No policy-intent prediction, no decision forecasting, no consensus surprise scoring.

Public function
---------------
snapshot() — list of CB rows (one per configured CB with available data).

Sources (all verified in store, 2026-07-12):
  FED  : FRED/DFF (daily fed funds effective rate)
  ECB  : FRED/ECBDFR (ECB deposit facility rate, daily)
  BoJ  : FRED/IRSTCI01JPM156N (BoJ policy rate, monthly; published as 3m interbank proxy)
  BoE  : FRED/IR3TIB01GBM156N (BoE 3m interbank, monthly)
  SNB  : FRED/IR3TIB01CHM156N (SNB 3m target, monthly)
  BoC  : FRED/IR3TIB01CAM156N (BoC 3m interbank, monthly)
  RBA  : FRED/IR3TIB01AUM156N (RBA cash rate proxy via 3m interbank, monthly)
Balance-sheet (impulse only where clean FRED series exist):
  FED  : WALCL (weekly), ECB: ECBASSETSW (weekly), BoJ: JPNASSETS (monthly)
  All others: honestly null (BoE annual-only on FRED; PBoC no clean keyless series).
CB meeting dates: data/intl_risk/cb_calendar.yml
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from lib import store

log = logging.getLogger(__name__)

_CALENDAR_PATH = Path(__file__).resolve().parent.parent / "data" / "intl_risk" / "cb_calendar.yml"

# ---------------------------------------------------------------------------
# CB configuration
# ---------------------------------------------------------------------------
# Each entry: id, name_en, name_zh, country, rate_series, rate_store, cadence,
# bs_series, bs_store, bs_unit_mult (for USD/billion normalization, optional).
# Monthly FRED series (IR3TIB01*) lag ~1 month — disclosed in each row.

_CB_SPECS: list[dict[str, Any]] = [
    {
        "id": "FED",
        "name_en": "Federal Reserve (FOMC)",
        "name_zh": "美联储（FOMC）",
        "country": "US",
        "rate_series": "DFF",
        "rate_store": "fred",
        "rate_col": "fed_funds",
        "rate_cadence": "daily",
        "bs_series": "WALCL",
        "bs_store": "fred",
        "bs_unit": "USD billions (×1, raw WALCL is in billions)",
        "calendar_key": "FOMC",
    },
    {
        "id": "ECB",
        "name_en": "European Central Bank",
        "name_zh": "欧洲央行",
        "country": "XM",
        "rate_series": "ECBDFR",
        "rate_store": "fred",
        "rate_col": "ez_short",
        "rate_cadence": "daily",
        "bs_series": "ECBASSETSW",
        "bs_store": "fred",
        "bs_unit": "EUR billions",
        "calendar_key": "ECB",
    },
    {
        "id": "BOJ",
        "name_en": "Bank of Japan",
        "name_zh": "日本银行",
        "country": "JP",
        "rate_series": "IRSTCI01JPM156N",
        "rate_store": "fred",
        "rate_col": "jp_short",
        "rate_cadence": "monthly",
        "bs_series": "JPNASSETS",
        "bs_store": "fred",
        "bs_unit": "JPY trillions",
        "calendar_key": "BoJ",
    },
    {
        "id": "BOE",
        "name_en": "Bank of England",
        "name_zh": "英格兰银行",
        "country": "GB",
        "rate_series": "IR3TIB01GBM156N",
        "rate_store": "fred",
        "rate_col": "gb_short",
        "rate_cadence": "monthly",
        "bs_series": None,   # BoE: annual-only on FRED — honest null
        "bs_store": None,
        "bs_unit": None,
        "calendar_key": "BoE",
    },
    {
        "id": "SNB",
        "name_en": "Swiss National Bank",
        "name_zh": "瑞士国家银行",
        "country": "CH",
        "rate_series": "IR3TIB01CHM156N",
        "rate_store": "fred",
        "rate_col": "ch_short",
        "rate_cadence": "monthly",
        "bs_series": None,   # SNB: no clean keyless series
        "bs_store": None,
        "bs_unit": None,
        "calendar_key": "SNB",
    },
    {
        "id": "BOC",
        "name_en": "Bank of Canada",
        "name_zh": "加拿大央行",
        "country": "CA",
        "rate_series": "IR3TIB01CAM156N",
        "rate_store": "fred",
        "rate_col": "ca_short",
        "rate_cadence": "monthly",
        "bs_series": None,
        "bs_store": None,
        "bs_unit": None,
        "calendar_key": "BoC",
    },
    {
        "id": "RBA",
        "name_en": "Reserve Bank of Australia",
        "name_zh": "澳大利亚储备银行",
        "country": "AU",
        "rate_series": "IR3TIB01AUM156N",
        "rate_store": "fred",
        "rate_col": "au_short",
        "rate_cadence": "monthly",
        "bs_series": None,
        "bs_store": None,
        "bs_unit": None,
        "calendar_key": "RBA",
    },
]

# Stale tolerance: daily series stale if last obs > 12 days old;
# monthly series stale if > 75 days old (lag ~1mo is expected).
_STALE_DAYS = {"daily": 12, "monthly": 75}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r(v, nd: int = 3) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if not math.isfinite(f) else round(f, nd)
    except (TypeError, ValueError):
        return None


def _load_rate(spec: dict, gaps: list[str]) -> pd.Series | None:
    """Load the policy rate series; fail-open."""
    df = store.read(spec["rate_store"], spec["rate_series"])
    if df is None or df.empty:
        gaps.append(f"{spec['id']}: rate series {spec['rate_series']} absent")
        return None
    col = spec.get("rate_col") or df.columns[0]
    if col not in df.columns:
        col = df.columns[0]
    s = df[col].astype(float).dropna()
    return s if not s.empty else None


def _last_change(s: pd.Series, min_bp: float = 1.0) -> dict | None:
    """Detect the most recent step change in a rate series.

    A 'change' = a day where the rate differs from the previous day by >= min_bp bps.
    Returns {date, direction, bp, prev_rate, new_rate} or None if no change found
    in last 5 years.
    """
    if s is None or len(s) < 2:
        return None
    s = s.dropna()
    # 5-year window to bound the search
    cutoff = s.index[-1] - pd.Timedelta(days=5 * 365)
    s_rec = s[s.index >= cutoff]
    if len(s_rec) < 2:
        s_rec = s

    diff = s_rec.diff().dropna()
    changes = diff[diff.abs() >= min_bp / 100.0]  # min_bp is in bps; rate in pct
    if changes.empty:
        return None
    last_chg = changes.iloc[-1]
    chg_date = changes.index[-1]
    chg_bp = _r(float(last_chg) * 100.0, 1)  # convert pp to bp
    prev_rate = _r(float(s_rec.loc[chg_date] - last_chg))
    new_rate = _r(float(s_rec.loc[chg_date]))
    direction = "hike" if last_chg > 0 else "cut"
    return {
        "date": str(chg_date.date()),
        "direction": direction,
        "bp": chg_bp,
        "prev_rate": prev_rate,
        "new_rate": new_rate,
    }


def _trend_3m(s: pd.Series, cadence: str = "daily") -> str | None:
    """3-month trend of policy rate: 'hiking' | 'easing' | 'hold'.

    Parameters
    ----------
    s:
        Rate series (policy rate values, not changes).
    cadence:
        'daily' → lookback ~63 business days (≈ 3 months).
        'monthly' → lookback 3 observations (≈ 3 months of monthly data).
        Using 63 obs on a monthly series would read ~5y of history,
        causing a mistaken 'hiking' read while the rate has been flat 24 months.
    """
    if s is None or len(s) < 2:
        return None
    # Cadence-aware lookback: daily ≈ 63 business days, monthly ≈ 3 rows
    n_lookback = 3 if cadence == "monthly" else 63
    n = min(n_lookback, len(s))
    chg = float(s.iloc[-1]) - float(s.iloc[-n])
    if chg > 0.10 / 100:  # > 10bps
        return "hiking"
    if chg < -0.10 / 100:  # < -10bps
        return "easing"
    return "hold"


def _bs_impulse(spec: dict, gaps: list[str]) -> dict | None:
    """Compute 13w and 52w balance-sheet impulse (% change) for CBs with BS series.

    Returns {impulse_13w, impulse_52w, level, asof, unit} or None.
    """
    if not spec.get("bs_series") or not spec.get("bs_store"):
        return None
    df = store.read(spec["bs_store"], spec["bs_series"])
    if df is None or df.empty:
        gaps.append(f"{spec['id']}: BS series {spec['bs_series']} absent")
        return None
    s = df.iloc[:, 0].astype(float).dropna()
    if s.empty:
        gaps.append(f"{spec['id']}: BS series empty")
        return None

    def _imp(weeks: int) -> float | None:
        n = min(weeks, len(s) - 1)
        if n < 1:
            return None
        v = float(s.iloc[-1]) / float(s.iloc[-1 - n]) - 1.0
        return _r(v * 100.0, 2) if math.isfinite(v) else None

    return {
        "impulse_13w": _imp(13),
        "impulse_52w": _imp(52),
        "level": _r(float(s.iloc[-1]), 1),
        "asof": str(s.index[-1].date()),
        "unit": spec.get("bs_unit", "local currency"),
        "series": spec["bs_series"],
        "gap_note": None,
    }


def _next_meeting(cb_key: str, calendar: dict, today: date) -> dict | None:
    """Find the next scheduled meeting date from the calendar YAML.

    Returns a dict with keys 'date' (ISO string) and 'days' (calendar days until
    the meeting).  The surface (intl.html.j2 and macro.html.j2) consumes the 'days'
    key for countdown display; do not rename it without updating both templates.
    """
    cb_data = calendar.get("banks", {}).get(cb_key)
    if cb_data is None:
        return None
    dates_raw = cb_data.get("dates", [])
    upcoming: list[date] = []
    for d in dates_raw:
        try:
            dt = date.fromisoformat(str(d))
            if dt >= today:
                upcoming.append(dt)
        except (ValueError, TypeError):
            continue
    if not upcoming:
        return None
    nxt = min(upcoming)
    return {
        "date": str(nxt),
        "days": (nxt - today).days,
    }


def _load_calendar() -> dict:
    """Load the CB meeting calendar YAML. Fail-open: returns {} if absent."""
    try:
        with open(_CALENDAR_PATH) as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        log.warning("cb_desk: calendar load failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# snapshot() — public function
# ---------------------------------------------------------------------------

def snapshot() -> dict:
    """Central-Bank Desk snapshot (IRD-R7 — descriptive only).

    Returns:
      cbs: list of per-CB dicts (one per configured CB with available rate data)
      gaps: list of notes on missing series
      n_cbs: int (cbs with data)
      as_of: ISO date of most recent observation across all CBs
      built: ISO timestamp
      note: honesty disclaimer (no predictions)
    """
    gaps: list[str] = []
    calendar = _load_calendar()
    today = datetime.now(timezone.utc).date()
    rows: list[dict] = []

    for spec in _CB_SPECS:
        rate_s = _load_rate(spec, gaps)
        if rate_s is None:
            gaps.append(f"{spec['id']}: skipped (no rate data)")
            continue

        # Policy rate level
        policy_rate = _r(float(rate_s.iloc[-1]), 4)
        asof = str(rate_s.index[-1].date())
        cadence = spec.get("rate_cadence", "daily")
        age_days = (pd.Timestamp(today) - rate_s.index[-1]).days
        stale = age_days > _STALE_DAYS.get(cadence, 30)

        # Last change
        lc = _last_change(rate_s)

        # 3m trend — pass cadence so monthly series use 3-obs lookback not 63
        trend = _trend_3m(rate_s, cadence=cadence)

        # BS impulse (where available)
        bs = _bs_impulse(spec, gaps)
        if bs is None and spec.get("bs_series"):
            # Already added to gaps in _bs_impulse
            pass
        if bs is None:
            bs_out = None
            bs_gap = f"{spec['id']}: balance-sheet series not available (honest null)"
        else:
            bs_out = bs
            bs_gap = None
        if bs_gap:
            gaps.append(bs_gap)

        # Next meeting
        nxt = _next_meeting(spec["calendar_key"], calendar, today)

        row: dict[str, Any] = {
            "id": spec["id"],
            "name_en": spec["name_en"],
            "name_zh": spec["name_zh"],
            "country": spec["country"],
            "policy_rate": policy_rate,
            "rate_unit": "percent",
            "source": {
                "series": spec["rate_series"],
                "store": spec["rate_store"],
                "cadence": cadence,
            },
            "last_change": lc,
            "trend_3m": trend,
            "bs_impulse": bs_out,
            "next_meeting": nxt,
            "asof": asof,
            "stale": stale,
        }
        rows.append(row)

    # Most recent observation across all CBs
    asof_dates: list[str] = [r["asof"] for r in rows if r.get("asof")]
    as_of = max(asof_dates) if asof_dates else "n/a"

    return {
        "cbs": rows,
        "n_cbs": len(rows),
        "gaps": gaps,
        "as_of": as_of,
        "built": datetime.now(timezone.utc).isoformat(),
        "bs_note": (
            "Balance-sheet impulse available for: FED (WALCL), ECB (ECBASSETSW), "
            "BoJ (JPNASSETS). "
            "BoE: FRED provides annual-only balance-sheet data — honest null. "
            "PBoC: no clean keyless balance-sheet series available — honest null. "
            "SNB/BoC/RBA: no balance-sheet series configured — honest null."
        ),
        "irdr7_note": (
            "IRD-R7: This desk is DESCRIPTIVE. "
            "It reports realized policy rates, observed changes, and published meeting dates. "
            "No policy-intent projection, no forward guidance scoring, "
            "no consensus-surprise computation (no free consensus source)."
        ),
    }
