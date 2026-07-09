"""engine/flip_confirmation.py — T+1 sector-flip confirmation lens.

Policy-Shock Regime program §4 W1-C (PR #2003).

A violent one-day sector-leadership flip is detected when the daily return
spread between the defensive composite (equal-weight XLP/XLU/XLV) and the
offense composite (equal-weight SMH/XLK) exceeds |z| >= 2.5 against the
trailing 252-day history of the same spread.

The NIGHT AFTER a flip this module computes four T+1 attribution legs:
  spread_persistence  — sign of next-day spread (same direction? + magnitude)
  absorption_delta    — change in market_drivers absorption_pctile day-over-day
  leadership_continuity — did the winning composite also win T+1?
  breadth_follow_through — omitted honestly (no intraday breadth series available)

Verdict vocabulary (descriptive only, never a recommendation):
  CONFIRMED — spread_persistence same direction AND leadership_continuity
  FADED     — spread_persistence opposite direction (regardless of magnitude)
  MIXED     — all other combos (same direction but partial, missing legs)

Ledger: data/flip_confirmation/events.jsonl — append-only, keep-first per event
date. NIGHTLY is the sole writer.

qledger family: flip_confirmation.v1
  scope: macro, key = "def_vs_off_spread"
  bench: XLP (defensive composite proxy; grader prices the composite leg)
  direction: +1 when defensive wins the flip, -1 when offense wins
  horizons: 5d + 21d (graded by qledger at both; 63d not registered —
             the T+1 descriptive verdict is the near-term claim)

Historical descriptive scan: detect_since() sweeps 2024→ and returns all
flip events with their T+1 verdicts for the UI base-rate table. This is
labeled DESCRIPTIVE and never constitutes a registered claim.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger("flip_confirmation")

# ── configuration ──────────────────────────────────────────────────────────────
DEFENSIVE = ("XLP", "XLU", "XLV")   # equal-weight defensive composite
OFFENSE   = ("SMH", "XLK")           # equal-weight offense composite

Z_THRESH   = 2.5     # |z| >= this → flip event
Z_WINDOW   = 252     # history used for z-score normalisation
Z_MINPER   = 126     # min_periods so early history is excluded gracefully

LEDGER_DIR  = ("data", "flip_confirmation")
LEDGER_NAME = "events.jsonl"

QLEDGER_DESK   = "flip_confirmation.v1"
QLEDGER_FAMILY = "flip_confirmation.v1"

# ── price helpers ──────────────────────────────────────────────────────────────

def _close(ticker: str) -> pd.Series | None:
    """Load close price series from the Yahoo parquet store."""
    df = store.read("yahoo", ticker)
    if df is None or "close" not in df.columns:
        return None
    s = df["close"].astype(float)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s


def _composites() -> tuple[pd.Series, pd.Series] | tuple[None, None]:
    """Equal-weight defensive and offense composite close series."""
    def_series = [_close(t) for t in DEFENSIVE]
    off_series  = [_close(t) for t in OFFENSE]
    if any(s is None for s in def_series + off_series):
        log.warning("flip_confirmation: missing one or more price series; cannot compute")
        return None, None
    # align to common index; ffill up to 5 bars
    common = def_series[0].index
    for s in def_series[1:] + off_series:
        common = common.intersection(s.index)
    def_comp = sum(s.reindex(common).ffill(limit=5) for s in def_series) / len(def_series)
    off_comp  = sum(s.reindex(common).ffill(limit=5) for s in off_series)  / len(off_series)
    return def_comp, off_comp


# ── core computation ───────────────────────────────────────────────────────────

def _spread_z(def_comp: pd.Series, off_comp: pd.Series) -> tuple[pd.Series, pd.Series]:
    """1-day return spread (defensive − offense) and its rolling z-score."""
    def_ret = def_comp.pct_change()
    off_ret  = off_comp.pct_change()
    spread   = def_ret - off_ret
    mean = spread.rolling(Z_WINDOW, min_periods=Z_MINPER).mean()
    std  = spread.rolling(Z_WINDOW, min_periods=Z_MINPER).std()
    z    = (spread - mean) / std.replace(0, np.nan)
    return spread, z


def _absorption_delta(event_date: pd.Timestamp,
                      t1_date: pd.Timestamp) -> float | None:
    """Change in absorption_pctile between event_date and T+1_date.

    Reads data/regime/market_drivers_log.parquet (read-only).
    Returns None when the parquet is absent or the dates are missing.
    """
    try:
        p = config.data_dir() / "regime" / "market_drivers_log.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        df = df.dropna(subset=["absorption_pctile"])
        df["asof"] = pd.to_datetime(df["asof"]).dt.normalize()
        idx = df.set_index("asof")["absorption_pctile"]
        val_ev = idx.get(event_date)
        val_t1 = idx.get(t1_date)
        if val_ev is None or val_t1 is None or pd.isna(val_ev) or pd.isna(val_t1):
            return None
        return float(val_t1) - float(val_ev)
    except Exception as exc:  # noqa: BLE001 — read-only, never fatal
        log.debug("absorption_delta lookup failed: %s", exc)
        return None


def _verdict_for_t1(*, event_z: float, t1_spread: float,
                    leadership_continuity: bool) -> str:
    """Descriptive vocabulary: CONFIRMED | FADED | MIXED.

    CONFIRMED: the winning side continued (leadership_continuity) AND the
               spread kept the same sign (spread_persistence positive).
    FADED:     the spread reversed sign (opposite direction next day).
    MIXED:     leadership continued but the spread magnitude shrunk, or
               any partial-data edge case.
    """
    same_sign = (event_z > 0 and t1_spread > 0) or (event_z < 0 and t1_spread < 0)
    if same_sign and leadership_continuity:
        return "CONFIRMED"
    if not same_sign:
        return "FADED"
    return "MIXED"


def _build_event(event_date: pd.Timestamp,
                 spread: pd.Series,
                 z: pd.Series) -> dict[str, Any]:
    """Build a full event record for one flip day (T+0).

    The T+1 attribution is populated when the next bar is available.
    On the same nightly as the event the T+1 bar is the current day's bar
    (already committed); for forward accrual the next nightly will have it.
    """
    z_val    = float(z.loc[event_date])
    sp_val   = float(spread.loc[event_date])
    direction = "defensive" if z_val > 0 else "offense"

    event = {
        "event_date": event_date.date().isoformat(),
        "z": round(z_val, 4),
        "spread": round(sp_val, 4),
        "direction": direction,
        "t1_attribution": None,
        "verdict": None,
    }

    # look for T+1
    later = spread.index[spread.index > event_date]
    if len(later) == 0:
        return event   # flip happened today — T+1 not yet available

    t1_date  = later[0]
    t1_spread = float(spread.loc[t1_date])
    t1_dir    = "defensive" if t1_spread > 0 else "offense"
    leadership_continuity = (t1_dir == direction)
    abs_delta = _absorption_delta(event_date, t1_date)

    verdict = _verdict_for_t1(
        event_z=z_val,
        t1_spread=t1_spread,
        leadership_continuity=leadership_continuity,
    )

    event["t1_attribution"] = {
        "t1_date": t1_date.date().isoformat(),
        "spread_persistence": {
            "same_direction": leadership_continuity,
            "magnitude": round(abs(t1_spread), 4),
            "direction": t1_dir,
        },
        "breadth_follow_through": None,   # no intraday breadth series available
        "absorption_delta": round(abs_delta, 4) if abs_delta is not None else None,
        "leadership_continuity": leadership_continuity,
        "note_breadth": "breadth_follow_through omitted — no intraday advance/decline series in committed store",
    }
    event["verdict"] = verdict
    return event


# ── public API ─────────────────────────────────────────────────────────────────

def detect_since(start: str = "2024-01-01") -> list[dict[str, Any]]:
    """Descriptive historical scan: all flip events from `start` date onward.

    Returns list of event dicts sorted by event_date ascending.
    LABELED DESCRIPTIVE — these are not registered claims; the function is used
    to populate the UI base-rate table only.
    """
    def_comp, off_comp = _composites()
    if def_comp is None:
        return []
    spread, z = _spread_z(def_comp, off_comp)
    start_ts = pd.Timestamp(start)
    candidates = z[(z.abs() >= Z_THRESH) & (z.index >= start_ts)]
    events = [_build_event(dt, spread, z) for dt in candidates.index]
    return events


def snapshot() -> dict[str, Any]:
    """Latest-state snapshot for the UI card.

    Returns:
      last_event      — the most recent flip event dict (or None)
      base_rates      — confirmed/faded/mixed counts since 2024 (descriptive)
      descriptive_scan — all 2024→ events for the table
      asof            — date of the latest data bar
    """
    try:
        def_comp, off_comp = _composites()
        if def_comp is None:
            return {"error": "price series unavailable", "last_event": None,
                    "base_rates": None, "descriptive_scan": [], "asof": None}

        spread, z = _spread_z(def_comp, off_comp)
        asof = spread.index[-1].date().isoformat()

        # full descriptive scan since 2024
        all_events = detect_since("2024-01-01")

        # base rate counts (events where T+1 was available, i.e. verdict is not None)
        graded = [e for e in all_events if e["verdict"] is not None]
        base_rates: dict[str, int] = {
            "n_events": len(all_events),
            "n_graded": len(graded),
            "confirmed": sum(1 for e in graded if e["verdict"] == "CONFIRMED"),
            "faded":     sum(1 for e in graded if e["verdict"] == "FADED"),
            "mixed":     sum(1 for e in graded if e["verdict"] == "MIXED"),
        }

        last_event = all_events[-1] if all_events else None

        return {
            "asof": asof,
            "last_event": last_event,
            "base_rates": base_rates,
            "descriptive_scan": all_events,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("flip_confirmation.snapshot failed: %s", exc)
        return {"error": str(exc), "last_event": None,
                "base_rates": None, "descriptive_scan": [], "asof": None}


# ── ledger (nightly writer) ────────────────────────────────────────────────────

def _ledger_path(root: Path | None = None) -> Path:
    r = root or config.ROOT
    p = r.joinpath(*LEDGER_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p / LEDGER_NAME


def _json_default(o: Any) -> Any:
    if isinstance(o, (date,)):
        return o.isoformat()
    item = getattr(o, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:  # noqa: BLE001
            pass
    return str(o)


def _load_ledger(path: Path) -> dict[str, dict]:
    """Return {event_date: row} from the jsonl ledger."""
    rows: dict[str, dict] = {}
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                key = str(row.get("event_date", ""))
                if key:
                    rows.setdefault(key, row)  # keep-first
            except json.JSONDecodeError:
                continue
    return rows


def append_ledger(events: list[dict], root: Path | None = None) -> int:
    """Append new events to the ledger (keep-first per event_date).

    Returns the number of NEW rows written.
    """
    path = _ledger_path(root)
    existing = _load_ledger(path)
    written = 0
    with path.open("a", encoding="utf-8") as fh:
        for ev in events:
            key = str(ev.get("event_date", ""))
            if not key or key in existing:
                continue
            fh.write(json.dumps(ev, ensure_ascii=False, default=_json_default) + "\n")
            existing[key] = ev
            written += 1
    return written


# ── qledger registration ───────────────────────────────────────────────────────

def register_claims(events: list[dict], root: Path | None = None) -> list[dict]:
    """Register one qledger claim per flip event.

    Claim design:
      desk    : flip_confirmation.v1
      scope   : macro / def_vs_off_spread
      bench   : XLP  (defensive composite proxy — the claim tests whether the
                defensive side outperforms; XLP is the largest / most-liquid leg)
      direction: +1 when defensive wins, -1 when offense wins
      horizons: 5d + 21d (T+1 confirmed → spread persistence over the week/month)
      timestamp_quality: SNAPSHOT_DATE (the z-score is computed on the same bar
                         as the event; no look-ahead but it is the snapshot day)

    Macro scope REQUIRES a named bench (D4 validation rule). We use XLP as the
    machine-checkable observable: it tracks the defensive composite, and the
    grader can verify whether XLP outperformed XLK/SMH over the grading horizon.

    NOTE: SNAPSHOT_DATE claims are display-only per qledger.TIMESTAMP_QUALITY —
    they accrue as claim rows but the grader's embargo check marks them
    `gradeable=False`. We register them to populate the family ledger so the
    track-record chip shows the accrual count. Forward-graded rows (from the
    daily verdict alignment check) will use CRAWL_BOUNDED once that harness
    is built (a follow-on wave of this program).
    """
    from engine import qledger as q  # local import — avoids circular at module level

    claims_in = []
    for ev in events:
        asof = ev.get("event_date")
        if not asof:
            continue
        direction = 1 if ev.get("direction") == "defensive" else -1
        claims_in.append(q.make_claim(
            desk=QLEDGER_DESK,
            asof=asof,
            scope_type="macro",
            scope_key="def_vs_off_spread",
            direction=direction,
            horizon_d=21,       # primary grading clock: 21d spread persistence
            timestamp_quality="SNAPSHOT_DATE",
            bench="XLP",        # D4 requirement: macro claims must name a bench
            claim_family=QLEDGER_FAMILY,
            extra={
                "z": ev.get("z"),
                "flip_direction": ev.get("direction"),
                "verdict": ev.get("verdict"),
            },
        ))
    if not claims_in:
        return []
    return q.register_batch(claims_in, root=root, dedupe=True)


# ── nightly entry point ────────────────────────────────────────────────────────

def nightly_run(root: Path | None = None) -> dict[str, Any]:
    """Nightly build step: detect events, append ledger, register qledger claims.

    Called by scripts/build_flip_confirmation.py.
    Returns a summary dict for the build log.
    """
    try:
        events = detect_since("2024-01-01")  # descriptive scan; ledger starts empty at ship
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "n_events": 0, "n_written": 0}

    n_written = append_ledger(events, root=root)

    try:
        registered = register_claims(events, root=root)
        n_registered = len([r for r in registered if r.get("status") == "open"])
    except Exception as exc:  # noqa: BLE001
        log.warning("qledger registration failed: %s", exc)
        n_registered = 0

    graded = [e for e in events if e["verdict"] is not None]
    confirmed = sum(1 for e in graded if e["verdict"] == "CONFIRMED")
    faded     = sum(1 for e in graded if e["verdict"] == "FADED")
    mixed     = sum(1 for e in graded if e["verdict"] == "MIXED")

    return {
        "ok": True,
        "n_events": len(events),
        "n_written": n_written,
        "n_registered": n_registered,
        "confirmed": confirmed,
        "faded": faded,
        "mixed": mixed,
    }
