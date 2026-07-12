"""engine/washout_counter_read.py — RC-R11 washout counter-read chip.

When the risk layer prints an extreme (growth-scare score ≥ 90) while the primary
index (SPY) sits at a depth extreme (IHM washout_turn state when live; interim:
63d drawdown percentile ≥ p90 depth), emit a compact JSON block labeling this as
a capitulation-zone reading.

DISPLAY/CONTEXT TIER ONLY. No rank, gate, size, or stance change.
Ledgered (append-only, fire-only rows).
Expected-NULL: most nights fired=false, no ledger row.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

log = logging.getLogger("washout_counter_read")

# Threshold constants
_SCARE_P90 = 90.0          # growth-scare score threshold for firing
_DEPTH_P10 = 10.0          # IHM depth_pctile ≤ this is washout territory
_DRAWDOWN_P90 = 90.0       # 63d drawdown percentile threshold for fallback
_MAX_EVENT_DAYS = 5        # recent_events: look back this many trading days
_HISTORY_WINDOW = 252      # days of price history for fallback pctile
_DRAWDOWN_WINDOW = 63      # days for drawdown rolling max


def compute(
    risk_radar: "dict | None",
    index_momentum: "dict | None",
    *,
    price_fallback: "pd.Series | None" = None,
    as_of: "str | None" = None,
) -> dict:
    """Returns the counter-read block (always a dict, never raises).

    Output schema:
    {
        "schema": "washout_counter_read.v1",
        "as_of": "YYYY-MM-DD",
        "fired": bool,
        "scare_pctile": float | None,   # growth scare score (0-100)
        "depth_basis": "ihm_washout_turn" | "drawdown_63d_pctile" | None,
        "depth_value": float | None,    # depth_pctile for IHM; 63d drawdown percentile for fallback
        "index": "SPY" | None,
        "is_context_only": True,
    }
    """
    _as_of = as_of or str(date.today())
    _base: dict = {
        "schema": "washout_counter_read.v1",
        "as_of": _as_of,
        "fired": False,
        "scare_pctile": None,
        "depth_basis": None,
        "depth_value": None,
        "index": None,
        "is_context_only": True,
    }

    try:
        # Step 1: extract growth scare score
        scare_pctile = _extract_growth_scare(risk_radar)
        _base["scare_pctile"] = scare_pctile

        if scare_pctile is None or scare_pctile < _SCARE_P90:
            return _base

        # Step 2: check depth extreme via IHM, then fallback
        depth_basis, depth_value, index = _extract_depth(
            index_momentum, price_fallback, _as_of
        )

        if depth_basis is not None:
            _base.update(
                fired=True,
                depth_basis=depth_basis,
                depth_value=depth_value,
                index=index,
            )
        # else: scare ≥ 90 but no depth extreme — fired stays False

    except Exception as exc:  # noqa: BLE001 — never raises
        log.warning("washout_counter_read.compute failed: %s", exc)

    return _base


def _extract_growth_scare(risk_radar: "dict | None") -> "float | None":
    """Return the growth scare score (0-100) or None if absent."""
    if not isinstance(risk_radar, dict):
        return None
    scares = risk_radar.get("scares")
    if not isinstance(scares, list):
        return None
    for s in scares:
        if isinstance(s, dict) and s.get("scare") == "growth":
            val = s.get("score")
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
    return None


def _extract_depth(
    index_momentum: "dict | None",
    price_fallback: "pd.Series | None",
    as_of: str,
) -> "tuple[str | None, float | None, str | None]":
    """Return (depth_basis, depth_value, index_ticker) or (None, None, None)."""

    # --- IHM primary path ---
    if isinstance(index_momentum, dict):
        result = _check_ihm_spy(index_momentum, as_of)
        if result[0] is not None:
            return result

    # --- 63d drawdown fallback ---
    if price_fallback is not None:
        result = _check_drawdown_fallback(price_fallback)
        if result[0] is not None:
            return result

    return None, None, None


def _check_ihm_spy(
    index_momentum: dict, as_of: str
) -> "tuple[str | None, float | None, str | None]":
    """Check IHM SPY data for washout condition.

    Returns (depth_basis, depth_value, "SPY") or (None, None, None).
    """
    indices = index_momentum.get("indices")
    if not isinstance(indices, dict):
        return None, None, None

    spy = indices.get("SPY")
    if not isinstance(spy, dict):
        return None, None, None

    grids = spy.get("grids")
    if not isinstance(grids, dict):
        return None, None, None

    grid_1d = grids.get("1D")
    if not isinstance(grid_1d, dict):
        return None, None, None

    # Path A: current depth_pctile ≤ 10
    depth_pctile = grid_1d.get("depth_pctile")
    if depth_pctile is not None:
        try:
            dp = float(depth_pctile)
            if dp <= _DEPTH_P10:
                return "ihm_washout_turn", dp, "SPY"
        except (TypeError, ValueError):
            pass

    # Path B: recent_events has a washout_turn bull event within 5 trading days
    recent_events = grid_1d.get("recent_events")
    if isinstance(recent_events, list):
        cutoff = _trading_days_ago(as_of, _MAX_EVENT_DAYS)
        for evt in recent_events:
            if not isinstance(evt, dict):
                continue
            if evt.get("quality_tag") != "washout_turn":
                continue
            if evt.get("direction") != "bull":
                continue
            evt_date = evt.get("date") or evt.get("as_of") or ""
            if str(evt_date) >= cutoff:
                evt_depth = evt.get("depth_pctile")
                try:
                    ev_dp = float(evt_depth) if evt_depth is not None else None
                except (TypeError, ValueError):
                    ev_dp = None
                return "ihm_washout_turn", ev_dp, "SPY"

    return None, None, None


def _check_drawdown_fallback(
    price_fallback: "pd.Series",
) -> "tuple[str | None, float | None, str | None]":
    """Use SPY close series to compute 63d drawdown percentile fallback.

    Returns ("drawdown_63d_pctile", pctile_value, "SPY") if ≥ p90, else (None, None, None).
    """
    try:
        import numpy as np

        closes = price_fallback.dropna()
        if len(closes) < _DRAWDOWN_WINDOW + 1:
            return None, None, None

        rolling_max = closes.rolling(_DRAWDOWN_WINDOW).max()
        drawdown_series = closes / rolling_max - 1.0  # 0 to negative floats

        # Current drawdown (most negative = worst)
        current_dd = float(drawdown_series.iloc[-1])

        # Historical percentile: what fraction of the last 252 drawdown values
        # are LESS negative (shallower) than the current value?
        # Drawdowns are 0 to negative; current_dd MORE negative = deeper extreme.
        # pctile = fraction where history > current_dd (shallower), scaled 0-100.
        # A "depth extreme" (p90+) means current is more negative than 90% of history.
        history = drawdown_series.iloc[-_HISTORY_WINDOW:]
        history = history.dropna()
        if len(history) < 20:
            return None, None, None

        # Fraction of history that is SHALLOWER (less negative / closer to 0) than current
        pctile = float(np.mean(history > current_dd) * 100.0)
        # "≥ p90 depth" means current is worse than 90% of history
        if pctile >= _DRAWDOWN_P90:
            return "drawdown_63d_pctile", round(pctile, 1), "SPY"
    except Exception as exc:  # noqa: BLE001
        log.warning("washout_counter_read drawdown fallback failed: %s", exc)

    return None, None, None


def _trading_days_ago(as_of: str, n: int) -> str:
    """Return an ISO date string approximately n trading days before as_of.

    Uses calendar days × 1.5 as a conservative approximation (no holiday calendar).
    """
    try:
        base = date.fromisoformat(as_of)
        # approx: 5 trading days ≈ 7 calendar days; use 2*n for safety
        return str(base - timedelta(days=n * 2))
    except (ValueError, TypeError):
        return "1970-01-01"


def append_ledger(block: dict, data_dir: "str | Path") -> None:
    """Append a fired block to data/washout_counter_read/ledger.jsonl.

    Append-only. Only called when block["fired"] is True.
    RC-R2 law: rows append, supersede by reference, never re-dated/deleted.
    """
    data_dir = Path(data_dir)
    ledger_dir = data_dir / "washout_counter_read"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = ledger_dir / "ledger.jsonl"

    line = json.dumps(block, separators=(",", ":"), ensure_ascii=False)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    log.info("washout_counter_read ledger appended: as_of=%s", block.get("as_of"))
