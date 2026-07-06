"""engine/long_hold_clocks.py — Long-Hold Thesis Layer W2 PR-J: two display-tier clocks.

DISPLAY-ONLY — zero scored-path consumers (LH-R1 firewall, G1-DEFERRED ruling
2026-07-06). These fields annotate the per-stock panel JSON; they must never feed
board ordering, alert triage, top-setups gates, or push floor.

Two clocks
----------
entry_clock
    Days since the name's most recent tactical entry-signal fire (the last §7
    buy/rebuy marker date from ``engine.signal_gate.gate()``). Follows the
    ``days_since_last_fire`` staleness convention from
    ``engine.neuralweb.decay`` (ISO date_last + integer days count).

    Source: ``signal_gate.gate(ticker, close)["last"]["date"]``
    Only populated when the last marker type is buy or rebuy (same condition
    used by the hold-engine anchor selection in build_stock_library.py).
    Half-life note: the entry signal window is ~1-6 trading bars (~3-18 days)
    per FRESH_TICKS in confluence_tiers; beyond that the arrow ages out of the
    board. The clock reports calendar days and is display annotation only.

thesis_clock (v1)
    Days since the latest EDGAR ``period_end`` with a positive fundamental
    delta, as reported in ``data/edgar/fundamentals_panel.parquet``.

    V1 definition (simple, documented, stamped v1):
        A period row is "positive delta" if ANY of the following holds:
          1. ROA improving: (ni / assets) > (ni_prior / assets_prior)
          2. CFO positive: cfo > 0
          3. Revenue growing: revenue > (revenue from the prior row)
        The latest ``period_end`` date satisfying this condition is the
        thesis anchor; the clock is calendar days from that date to today.

    PIT note: ``fundamentals_panel`` uses a ``asof_date = period_end + 120d``
    lag (collectors/edgar.py as_of_cross_section). The clock is NOT the lag
    date — it is the period_end itself (the end of the fiscal period that
    showed positive delta). The clock measures "how stale is the most recent
    positive period" from the analyst's perspective, not filing lag.

    Coverage note: when no row with positive delta is found the field is
    absent (not None); display layer should treat absence as "no confirmation
    in data history".

Both clocks carry firewall annotations:
    _horizon_role = "hold_thesis"
    _display_only = True
    _version       = "v1" (thesis_clock) / "v1" (entry_clock)

Callers
-------
entry_clock:  build_stock_library.py (per-ticker loop, after sig_verdict is built)
thesis_clock: engine/stock_fundamentals.py (panels(), after fundamentals_panel loaded)
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

log = logging.getLogger(__name__)

# ── shared buy-marker types (mirrors signal_gate._BUY_TYPES) ─────────────────
_BUY_TYPES: frozenset[str] = frozenset({"buy", "rebuy"})


# ---------------------------------------------------------------------------
# entry_clock
# ---------------------------------------------------------------------------

def entry_clock(sig_verdict: dict | None, today: date | None = None) -> dict[str, Any] | None:
    """Build the entry_clock chip for one ticker.

    Parameters
    ----------
    sig_verdict:
        The dict returned by ``engine.signal_gate.gate(ticker, close)``.
        May be None (thin history, no signal computed) — returns None.
    today:
        Reference date for the days count (default: ``date.today()``).

    Returns
    -------
    dict with keys:
        date_last_fire  str | None   ISO "YYYY-MM-DD" of the last buy/rebuy marker
        days_since      int | None   Calendar days since date_last_fire
        _horizon_role   "hold_thesis"
        _display_only   True
        _version        "v1"
    or None when there is no buy/rebuy marker in the verdict.

    Firewall: the returned dict MUST NOT be consumed by any entry-stack
    scored surface.  It is display annotation only.
    """
    if sig_verdict is None:
        return None
    last_m = sig_verdict.get("last") or {}
    if last_m.get("type") not in _BUY_TYPES:
        # No open buy marker; no clock to show.
        return None
    date_str = last_m.get("date")
    days: int | None = None
    if date_str:
        try:
            ref = today or date.today()
            fire = date.fromisoformat(str(date_str)[:10])
            days = (ref - fire).days
        except (ValueError, TypeError):
            pass
    return {
        "date_last_fire": date_str[:10] if date_str else None,
        "days_since": days,
        "_horizon_role": "hold_thesis",
        "_display_only": True,
        "_version": "v1",
    }


# ---------------------------------------------------------------------------
# thesis_clock helpers
# ---------------------------------------------------------------------------

def _num(x: Any) -> float | None:
    """Safe float conversion; returns None for nan/None/non-numeric."""
    try:
        v = float(x)
        import math
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _positive_delta(row: Any, prev_revenue: float | None) -> bool:
    """Return True if this fundamentals_panel row shows a positive fundamental delta.

    Criterion (v1, documented — ANY of):
    1. ROA improving: (ni / assets) > (ni_prior / assets_prior)
    2. CFO positive: cfo > 0
    3. Revenue growing: revenue > prev_revenue (prior row's revenue)
    """
    ni     = _num(row.get("ni"))
    assets = _num(row.get("assets"))
    ni_p   = _num(row.get("ni_prior"))
    asp    = _num(row.get("assets_prior"))
    cfo    = _num(row.get("cfo"))
    rev    = _num(row.get("revenue"))

    # 1. ROA improvement
    if (ni is not None and assets and assets > 0
            and ni_p is not None and asp and asp > 0):
        if ni / assets > ni_p / asp:
            return True

    # 2. CFO positive
    if cfo is not None and cfo > 0:
        return True

    # 3. Revenue growth vs prior row
    if (rev is not None and prev_revenue is not None
            and prev_revenue > 0 and rev > prev_revenue):
        return True

    return False


def thesis_clock_from_panel(
    ticker: str,
    panel_rows: list[dict],
    today: date | None = None,
) -> dict[str, Any] | None:
    """Build the thesis_clock chip for one ticker from fundamentals_panel rows.

    Parameters
    ----------
    ticker:
        Ticker string (used only for logging).
    panel_rows:
        List of dicts from ``fundamentals_panel.parquet`` for this ticker,
        sorted ascending by ``fy``.  Must carry at minimum the columns:
        fy, period_end, ni, assets, ni_prior, assets_prior, cfo, revenue.
    today:
        Reference date (default: ``date.today()``).

    Returns
    -------
    dict with keys:
        date_last_confirmation  str | None   ISO "YYYY-MM-DD" period_end
        days_since              int | None   Calendar days since that date
        definition_version      "v1"         Snapshot of the logic used
        definition_note         str          Plain-English summary of v1 criterion
        _horizon_role           "hold_thesis"
        _display_only           True
        _version                "v1"
    or None when no rows with computable delta are found.

    Firewall: the returned dict MUST NOT be consumed by any entry-stack
    scored surface.  It is display annotation only.
    """
    if not panel_rows:
        return None

    ref = today or date.today()
    best_period_end: date | None = None
    prev_rev: float | None = None

    for row in panel_rows:   # rows already ascending by fy
        has_positive = _positive_delta(row, prev_rev)
        raw_pe = row.get("period_end")
        if has_positive and raw_pe is not None:
            try:
                # period_end may be a Timestamp or string
                if hasattr(raw_pe, "date"):
                    pe = raw_pe.date()          # pandas Timestamp
                else:
                    pe = date.fromisoformat(str(raw_pe)[:10])
                # Keep the LATEST such period_end
                if best_period_end is None or pe > best_period_end:
                    best_period_end = pe
            except (ValueError, TypeError):
                pass
        # Advance prev_rev for the next iteration (revenue growing criterion)
        prev_rev = _num(row.get("revenue")) or prev_rev

    if best_period_end is None:
        return None

    days_since = (ref - best_period_end).days
    return {
        "date_last_confirmation": best_period_end.isoformat(),
        "days_since": days_since,
        "definition_version": "v1",
        "definition_note": (
            "Days since latest EDGAR fiscal-period-end with positive fundamental delta. "
            "Positive delta (v1): ROA improving OR CFO > 0 OR revenue growing vs prior year. "
            "Source: data/edgar/fundamentals_panel.parquet (period_end + 120d filing lag; "
            "PIT via asof_date). Display-only; not a validated signal."
        ),
        "_horizon_role": "hold_thesis",
        "_display_only": True,
        "_version": "v1",
    }


# ---------------------------------------------------------------------------
# Convenience loader for thesis_clock at panels() build time
# ---------------------------------------------------------------------------

def thesis_clocks_from_parquet(today: date | None = None) -> dict[str, dict]:
    """Load ``data/edgar/fundamentals_panel.parquet`` and return
    ``{ticker: thesis_clock_dict}`` for every ticker with computable data.

    Called from ``engine.stock_fundamentals.panels()`` (piggyback the existing
    build; no new builder script required).

    Returns an empty dict when the parquet is absent or unreadable.
    """
    try:
        from lib import config  # noqa: PLC0415 — deferred to keep engine import-time clean
        import pandas as pd     # noqa: PLC0415

        path = config.data_dir() / "edgar" / "fundamentals_panel.parquet"
        if not path.exists():
            return {}
        df = pd.read_parquet(path)
    except Exception as exc:
        log.warning("thesis_clocks_from_parquet: could not load fundamentals_panel (%s)", exc)
        return {}

    if df.empty or "ticker" not in df.columns:
        return {}

    ref = today or date.today()
    out: dict[str, dict] = {}

    for ticker, sub in df.sort_values("fy").groupby("ticker"):
        rows = sub.to_dict("records")
        chip = thesis_clock_from_panel(str(ticker), rows, today=ref)
        if chip is not None:
            out[str(ticker)] = chip

    log.info("thesis_clocks_from_parquet: built clocks for %d tickers", len(out))
    return out
