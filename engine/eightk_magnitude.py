"""engine/eightk_magnitude.py — W1c: 8-K Item 1.01/2.03 contract-dollar magnitude.

Computes per-member contract_dollar_z (log-scale z-score vs the member's own trailing
baseline), theme roll-up, and a PRE-DRIFT flag that fires when a large-$ event arrives
while analyst consensus is still flat/absent (the filing-time front-run window).

Display-only. None on shortfall (n < BASELINE_MIN events for the member).
Forward-graded ledger seeded day 1, keyed (theme, asof).

Data path:
  data/edgar/material_8k_events.parquet  (collectors/edgar_8k.py)
  data/finnhub/recommendation.parquet    (engine/analyst_revisions.py)
  data/baskets/membership.json

Ledger path:
  data/eightk_magnitude/log.jsonl        (append-only, dedup by (theme, asof))
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# --- tuning constants -------------------------------------------------------
BASELINE_MIN = 3          # min prior 1.01/2.03 events before z is meaningful
BASELINE_WINDOW_DAYS = 365  # trailing window to build per-member baseline
LARGE_Z_THRESHOLD = 1.5   # z >= this -> "large" event for pre-drift flag
RECENT_WINDOW_DAYS = 45   # look-back for "current" events
# ----------------------------------------------------------------------------


def _load_events() -> pd.DataFrame | None:
    p = config.data_dir() / "edgar" / "material_8k_events.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        if df.empty:
            return None
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("eightk_magnitude: cannot read material_8k_events: %s", e)
        return None


def _load_membership() -> dict:
    try:
        return json.loads(
            (config.data_dir() / "baskets" / "membership.json").read_text()
        ).get("baskets", {})
    except Exception:  # noqa: BLE001
        return {}


def _theme_members(mem: dict) -> dict[str, list[str]]:
    """basket_id -> [active tickers]."""
    out: dict[str, list[str]] = {}
    for bid, b in mem.items():
        tickers = [
            m["ticker"]
            for m in b.get("members", [])
            if m.get("ticker") and not m.get("removed")
        ]
        if tickers:
            out[bid] = tickers
    return out


def _contract_z_for_member(
    ticker: str,
    events_1x: pd.DataFrame,
    today: pd.Timestamp,
) -> float | None:
    """Log-scale z-score of the most recent qualifying contract amount vs trailing baseline.

    Qualifying row = extraction_ok==True AND amount_usd > 0.
    Baseline = log(amount_usd) over [today-BASELINE_WINDOW_DAYS .. today-RECENT_WINDOW_DAYS].
    Current  = log(amount_usd) over [today-RECENT_WINDOW_DAYS .. today].

    Returns None when:
      - no current qualifying event exists, OR
      - fewer than BASELINE_MIN baseline events (insufficient history), OR
      - baseline std == 0 (all amounts identical — degenerate).
    """
    tk_rows = events_1x[events_1x["ticker"] == ticker].copy()
    if tk_rows.empty:
        return None

    tk_rows["d"] = pd.to_datetime(tk_rows["filing_date"], errors="coerce")
    tk_rows = tk_rows.dropna(subset=["d"])

    baseline_lo = today - pd.Timedelta(days=BASELINE_WINDOW_DAYS)
    recent_lo = today - pd.Timedelta(days=RECENT_WINDOW_DAYS)

    # Baseline: older than RECENT_WINDOW_DAYS but within BASELINE_WINDOW_DAYS
    baseline = tk_rows[
        (tk_rows["d"] >= baseline_lo) & (tk_rows["d"] < recent_lo)
    ]
    current = tk_rows[tk_rows["d"] >= recent_lo]

    # Need a qualifying extraction_ok=True amount in the current window
    if "extraction_ok" in current.columns:
        cur_ok = current[current["extraction_ok"] == True]  # noqa: E712
    else:
        cur_ok = pd.DataFrame()
    if cur_ok.empty or cur_ok["amount_usd"].dropna().empty:
        return None

    if len(baseline) < BASELINE_MIN:
        return None  # insufficient history -> None per spec

    if "extraction_ok" in baseline.columns:
        base_ok = baseline[baseline["extraction_ok"] == True]  # noqa: E712
    else:
        base_ok = pd.DataFrame()
    base_amounts = base_ok["amount_usd"].dropna()
    if len(base_amounts) < BASELINE_MIN:
        return None

    # Log-scale z
    log_base = base_amounts.apply(lambda x: math.log(x) if x > 0 else None).dropna()
    if len(log_base) < BASELINE_MIN:
        return None

    mu = log_base.mean()
    sigma = log_base.std(ddof=1)
    if sigma == 0 or math.isnan(sigma):
        return None

    # Use the largest current amount (most material event in window)
    best_cur = cur_ok["amount_usd"].dropna().max()
    if best_cur <= 0:
        return None

    z = (math.log(best_cur) - mu) / sigma
    return round(z, 3)


def _consensus_flat(ticker: str, rev_map: dict[str, dict]) -> bool:
    """True when analyst consensus for ticker is flat/absent.

    'Flat' = direction is 'stable' (rev_delta == 0 or None) or ticker not in revision_map.
    Absent (ticker not in rev_map at all) also counts as flat — no movement detected.
    """
    rec = rev_map.get(ticker)
    if rec is None:
        return True  # absent = no revision signal = flat
    return rec.get("direction", "stable") == "stable"


def _load_revision_map() -> dict[str, dict]:
    """Load analyst revision map; returns empty dict on any failure (graceful)."""
    try:
        from engine.analyst_revisions import revision_map
        return revision_map()
    except Exception as e:  # noqa: BLE001
        log.debug("eightk_magnitude: analyst_revisions unavailable: %s", e)
        return {}


def compute_eightk_magnitude(
    write_ledger: bool = True,
    _rev_map_override: dict[str, dict] | None = None,
) -> dict | None:
    """Compute contract-dollar magnitude panel + pre-drift flags.

    Returns a display-only dict with:
      asof:    ISO date string
      themes:  {basket_id: {contract_dollar_z, pre_drift, extraction_ok_pct,
                            top_ticker, top_amount_usd, n_events}}
      summary: {n_themes_active, n_predrift, n_extraction_ok}

    Returns None on shortfall (no events or no membership).

    _rev_map_override: inject a pre-built revision map (used in tests to avoid
    live data access without needing to patch an internal import).
    """
    today = pd.Timestamp(date.today())

    events = _load_events()
    if events is None:
        log.info("eightk_magnitude: no material_8k_events, returning None")
        return None

    mem = _load_membership()
    theme_tickers = _theme_members(mem)
    if not theme_tickers:
        log.info("eightk_magnitude: no basket membership, returning None")
        return None

    # Filter to 1.01 / 2.03 rows only (the contract-class items)
    events_1x = events[
        events["items"].str.contains(r"1\.01|2\.03", na=False)
    ].copy()

    # Load analyst revision map (fails gracefully — flat=True for all missing)
    if _rev_map_override is not None:
        rev_map = _rev_map_override
    else:
        rev_map = _load_revision_map()

    theme_results: dict[str, dict] = {}
    n_predrift = 0
    n_extraction_ok = 0

    for bid, tickers in theme_tickers.items():
        # Per-theme aggregation: take the highest z across members
        best_z: float | None = None
        best_ticker: str | None = None
        best_amount: float | None = None
        any_predrift = False
        n_events_total = 0
        n_ok = 0
        n_ok_total = 0

        # Count recent events for this theme
        theme_recent = events_1x[
            events_1x["ticker"].isin(tickers)
        ].copy()
        if not theme_recent.empty:
            theme_recent["d"] = pd.to_datetime(theme_recent["filing_date"], errors="coerce")
            recent_lo = today - pd.Timedelta(days=RECENT_WINDOW_DAYS)
            recent_rows = theme_recent[theme_recent["d"] >= recent_lo]
            n_events_total = len(recent_rows)
            if "extraction_ok" in recent_rows.columns:
                n_ok_total = int(recent_rows["extraction_ok"].sum())

        for tk in tickers:
            z = _contract_z_for_member(tk, events_1x, today)
            if z is None:
                continue

            # Top amount for this ticker in recent window
            tk_recent = events_1x[events_1x["ticker"] == tk].copy()
            tk_recent["d"] = pd.to_datetime(tk_recent["filing_date"], errors="coerce")
            recent_lo = today - pd.Timedelta(days=RECENT_WINDOW_DAYS)
            if "extraction_ok" in tk_recent.columns:
                cur_ok = tk_recent[
                    (tk_recent["d"] >= recent_lo) & (tk_recent["extraction_ok"] == True)  # noqa: E712
                ]
            else:
                cur_ok = pd.DataFrame()
            top_amount = cur_ok["amount_usd"].dropna().max() if not cur_ok.empty else None

            if best_z is None or z > best_z:
                best_z = z
                best_ticker = tk
                best_amount = float(top_amount) if top_amount is not None else None

            # Pre-drift: large z AND flat consensus
            if z >= LARGE_Z_THRESHOLD and _consensus_flat(tk, rev_map):
                any_predrift = True

            n_ok += 1

        if best_z is None:
            # No z computable for any member — still emit if there are recent events
            if n_events_total == 0:
                continue
            theme_results[bid] = {
                "contract_dollar_z": None,
                "pre_drift": False,
                "top_ticker": None,
                "top_amount_usd": None,
                "n_events": n_events_total,
                "n_extraction_ok": n_ok_total,
                "extraction_ok_pct": 0.0,
            }
            continue

        extraction_ok_pct = round(n_ok_total / n_events_total * 100, 1) if n_events_total else 0.0
        theme_results[bid] = {
            "contract_dollar_z": best_z,
            "pre_drift": any_predrift,
            "top_ticker": best_ticker,
            "top_amount_usd": best_amount,
            "n_events": n_events_total,
            "n_extraction_ok": n_ok_total,
            "extraction_ok_pct": extraction_ok_pct,
        }
        if any_predrift:
            n_predrift += 1
        n_extraction_ok += n_ok_total

    if not theme_results:
        log.info("eightk_magnitude: no theme results computed")
        return None

    asof = today.date().isoformat()
    payload = {
        "asof": asof,
        "large_z_threshold": LARGE_Z_THRESHOLD,
        "themes": theme_results,
        "summary": {
            "n_themes_active": len(theme_results),
            "n_predrift": n_predrift,
            "n_extraction_ok": n_extraction_ok,
        },
    }

    if write_ledger:
        try:
            _append_ledger(payload)
        except Exception as e:  # noqa: BLE001
            log.warning("eightk_magnitude ledger append failed: %s", e)

    return payload


# ---------------------------------------------------------------------------
# Forward-graded ledger — M4 mandate (masterplan §2 R-M4)
# ---------------------------------------------------------------------------
# Keyed (theme, asof). Dedup: skip if (theme, asof) already present.
# Fields: theme, asof, contract_dollar_z, pre_drift, extraction_ok (bool from extraction_ok_pct>0).
# Phase-0 grades only extraction_ok=True rows (extraction_ok_pct > 0).
# ---------------------------------------------------------------------------

def _append_ledger(payload: dict) -> None:
    """Append one ledger row per (theme, asof) — idempotent across re-runs."""
    d = config.data_dir() / "eightk_magnitude"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "log.jsonl"

    asof = payload.get("asof", date.today().isoformat())

    # Build seen-pairs set for dedup
    seen: set[tuple[str, str]] = set()
    if p.exists():
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                t, a = e.get("theme"), e.get("asof")
                if t and a:
                    seen.add((t, a))
            except Exception:  # noqa: BLE001
                continue

    rows_written = 0
    with p.open("a", encoding="utf-8") as fh:
        for theme, td in payload.get("themes", {}).items():
            key = (theme, asof)
            if key in seen:
                continue
            z = td.get("contract_dollar_z")
            pre_drift = bool(td.get("pre_drift", False))
            n_ok = td.get("n_extraction_ok", 0)
            n_events = td.get("n_events", 0)
            extraction_ok = n_ok > 0
            row = {
                "theme": theme,
                "asof": asof,
                "contract_dollar_z": z,
                "pre_drift": pre_drift,
                "extraction_ok": extraction_ok,
                "n_extraction_ok": n_ok,
                "n_events": n_events,
                "top_ticker": td.get("top_ticker"),
                "top_amount_usd": td.get("top_amount_usd"),
                "logged_at": datetime.now(timezone.utc).isoformat(),
                # Phase-0 grades only extraction_ok=True rows (per M4 mandate)
                "grade_eligible": extraction_ok,
            }
            fh.write(json.dumps(row, default=str) + "\n")
            seen.add(key)
            rows_written += 1

    log.info("eightk_magnitude ledger: +%d rows (asof=%s)", rows_written, asof)
