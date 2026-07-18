"""engine/flip_confirmation.py — T+1 sector-flip confirmation lens.

Policy-Shock Regime program §4 W1-C (PR #2008).

A violent one-day sector-leadership flip is detected when the daily return
spread between the defensive composite (equal-weight XLP/XLU/XLV) and the
offense composite (equal-weight SMH/XLK) exceeds |z| >= 2.5 against the
trailing 252-day history of the same spread.

The NIGHT AFTER a flip this module computes four T+1 attribution legs:
  spread_persistence  — sign of next-day spread (same direction? + magnitude)
  absorption_delta    — change in market_drivers absorption_pctile day-over-day
  leadership_continuity — did the winning composite also win T+1? (recorded field)
  breadth_follow_through — omitted honestly (no intraday breadth series available)

Verdict vocabulary v1.1 — 3-way taxonomy on z-scale follow-through
(descriptive only, never a recommendation):
  CONFIRMED — sign(t1_spread)==sign(event_spread) AND |t1_z| >= 0.5
  MIXED     — sign(t1_spread)==sign(event_spread) AND |t1_z| < 0.5
               (leadership continued but follow-through weak)
  FADED     — opposite sign (regardless of magnitude)

Ledger: data/flip_confirmation/events.jsonl — append-only, keep-first per
event date. NIGHTLY is the sole writer. LEDGER STARTS EMPTY AT SHIP DATE
(2026-07-09) — only events on or after SHIP_DATE are written here.
The 2024→ historical scan is in-memory only, embedded in the site artifact.

qledger family: flip_confirmation.v1 (Round-2 design, Amendment PS-A2)
  ONE claim per event, horizon_d=21 (chassis auto-grades at 5d and 21d via
  in_scope_horizons(21) = [5, 21] — no double-counting).

  Claims are ONLY registered for CONFIRMED and FADED verdicts.
  MIXED events abstain (weak follow-through makes no directional call).

  Priceable proxy pair (D4 — macro claims must name a machine-checkable
  observable):
    subject (scope_key): XLP  — defensive composite proxy
    bench:               XLK  — offense composite proxy
  proxy_note: the true composite is EW(XLP,XLU,XLV) − EW(SMH,XLK); the
    scorable proxy is XLP-vs-XLK (both priceable in the parquet store).

  Direction semantics (grade_claim: direction=+1 → subject outperforms bench):
    event_z > 0 (defensives won T+0) → predict XLP outperforms XLK → direction = +1
    event_z < 0 (offense won T+0)    → predict XLP underperforms XLK → direction = -1

  timestamp_quality: CRAWL_BOUNDED (the z-score fires when the bar closes;
    that closing price IS the event — no look-ahead, immediately gradeable)

Historical descriptive scan: detect_since() sweeps 2024→ and returns all
flip events with their T+1 verdicts for the UI base-rate table. This is
labeled DESCRIPTIVE and never constitutes a registered claim.

Amendment PS-A2 (2026-07-09): see research/POLICY_SHOCK_REGIME_MASTERPLAN_BY_FABLE.md §4 W1-C.
Round-2 (same day): claims re-registered as one 21d claim per CONFIRMED/FADED
  event on the priceable XLP-vs-XLK proxy pair; MIXED abstains.
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


from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled

# ── configuration ──────────────────────────────────────────────────────────────
DEFENSIVE = ("XLP", "XLU", "XLV")   # equal-weight defensive composite
OFFENSE   = ("SMH", "XLK")           # equal-weight offense composite

Z_THRESH   = 2.5     # |z| >= this → flip event
Z_WINDOW   = 252     # history used for z-score normalisation
Z_MINPER   = 126     # min_periods so early history is excluded gracefully

# SHIP_DATE: ledger (events.jsonl) and qledger writes start here.
# Events before this date appear in the descriptive scan (site artifact) only.
SHIP_DATE = "2026-07-09"

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
    """1-day return spread (defensive − offense) and its rolling z-score.

    NOTE: the rolling window is trailing-inclusive of the current bar, meaning
    the event-day bar itself is included in the mean/std used to normalise it.
    This is conservative (self-inclusion slightly deflates extreme z-values) and
    introduces no look-ahead (the bar is already closed when we compute). The
    event set is identical to the window-excluded alternative on all historical
    test dates; this choice is documented, not changed. (Amendment PS-A2.)
    """
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


def _verdict_for_t1(*, event_z: float, t1_spread: float, t1_z: float) -> str:
    """Descriptive vocabulary v1.1: CONFIRMED | MIXED | FADED.

    3-way taxonomy on z-scale follow-through (PS-A2, 2026-07-09):
      CONFIRMED — sign(t1_spread)==sign(event_spread) AND |t1_z| >= 0.5
                  (leadership continued with measurable follow-through)
      MIXED     — sign(t1_spread)==sign(event_spread) AND |t1_z| < 0.5
                  (leadership continued but follow-through weak / subdued)
      FADED     — opposite sign (reversal, regardless of magnitude)

    t1_z is the T+1 spread z-score from the same rolling apparatus used for
    event detection, looked up at the T+1 bar date.
    """
    same_sign = (event_z > 0 and t1_spread > 0) or (event_z < 0 and t1_spread < 0)
    if not same_sign:
        return "FADED"
    if abs(t1_z) >= 0.5:
        return "CONFIRMED"
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

    t1_date   = later[0]
    t1_spread = float(spread.loc[t1_date])
    t1_dir    = "defensive" if t1_spread > 0 else "offense"
    leadership_continuity = (t1_dir == direction)

    # T+1 z-score from the same rolling apparatus (PS-A2 v1.1 verdict rule)
    t1_z_val = float(z.loc[t1_date]) if t1_date in z.index else 0.0

    abs_delta = _absorption_delta(event_date, t1_date)

    verdict = _verdict_for_t1(
        event_z=z_val,
        t1_spread=t1_spread,
        t1_z=t1_z_val,
    )

    event["t1_attribution"] = {
        "t1_date": t1_date.date().isoformat(),
        "t1_z": round(t1_z_val, 4),
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

        # full descriptive scan since 2024 (in-memory only; never writes data/)
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

    Only writes events with event_date >= SHIP_DATE.
    Gated by COLLECT_LANE=nightly: returns 0 (no-op) outside the nightly lane.
    Returns the number of NEW rows written.
    """
    if not _ledger_advance_enabled():
        log.debug(
            "flip_confirmation.append_ledger: skipped (COLLECT_LANE != nightly)"
        )
        return 0
    path = _ledger_path(root)
    existing = _load_ledger(path)
    written = 0
    ship_ts = pd.Timestamp(SHIP_DATE).date()
    with path.open("a", encoding="utf-8") as fh:
        for ev in events:
            key = str(ev.get("event_date", ""))
            if not key or key in existing:
                continue
            # forward-only: skip any event before the ship date
            try:
                ev_date = date.fromisoformat(key)
            except ValueError:
                continue
            if ev_date < ship_ts:
                continue
            fh.write(json.dumps(ev, ensure_ascii=False, default=_json_default) + "\n")
            existing[key] = ev
            written += 1
    return written


# ── qledger registration ───────────────────────────────────────────────────────

def register_claims(events: list[dict], root: Path | None = None) -> list[dict]:
    """Register one qledger claim per CONFIRMED or FADED flip event at horizon_d=21.

    Only registers events with event_date >= SHIP_DATE (forward-only accrual).
    MIXED events abstain (weak follow-through makes no directional call).

    The chassis grades each 21d claim at BOTH 5d and 21d automatically via
    in_scope_horizons(21) = [5, 21] — one claim row per event, no double-counting.

    Claim design (Round-2, Amendment PS-A2):
      desk       : flip_confirmation.v1
      scope_type : macro
      scope_key  : XLP   — subject leg (priceable; grade_claim uses scope.key as
                            the ticker); XLP is the defensive composite proxy
      bench      : XLK   — offense composite proxy (priceable)
      proxy_note : true composite is EW(XLP,XLU,XLV) − EW(SMH,XLK); XLP-vs-XLK
                   is the machine-gradeable proxy (D4 requirement)
      direction  :
        event_z > 0 (defensives won T+0) → XLP should outperform XLK → +1
        event_z < 0 (offense won T+0)    → XLP should underperform XLK → -1
        (grade_claim: direction=+1 → excess=subject_ret−bench_ret > 0 is a hit)
      horizon_d  : 21 (grades at 5d + 21d automatically)
      timestamp_quality: CRAWL_BOUNDED — the z-score fires when the daily bar
                closes; the closing price IS the event (no look-ahead, no
                embargo needed). CRAWL_BOUNDED claims are gradeable=True so
                the standard qledger grading machinery matures them at 5d/21d.
    """
    from engine import qledger as q  # local import — avoids circular at module level

    ship_ts = pd.Timestamp(SHIP_DATE).date()
    claims_in = []
    for ev in events:
        asof = ev.get("event_date")
        if not asof:
            continue
        # forward-only: skip historical events (descriptive scan only)
        try:
            ev_date = date.fromisoformat(str(asof))
        except ValueError:
            continue
        if ev_date < ship_ts:
            continue

        # MIXED abstains — weak follow-through makes no directional call
        verdict = ev.get("verdict")
        if verdict == "MIXED":
            continue
        # Events with no verdict (T+1 not yet available) also abstain — no
        # directional call possible without a verdict.
        if verdict not in ("CONFIRMED", "FADED"):
            continue

        # direction semantics: predict the side that won T+0 keeps winning T+1
        # grade_claim computes excess = XLP_ret - XLK_ret; +1 → excess > 0 is hit
        direction = 1 if ev.get("direction") == "defensive" else -1

        extra = {
            "z": ev.get("z"),
            "flip_direction": ev.get("direction"),
            "verdict": verdict,
            "proxy_note": (
                "true composite is EW(XLP,XLU,XLV) − EW(SMH,XLK); "
                "scorable proxy is XLP-vs-XLK (both priceable in the store)"
            ),
        }
        # ONE claim per event at horizon_d=21; chassis grades at 5d + 21d
        claims_in.append(q.make_claim(
            desk=QLEDGER_DESK,
            asof=asof,
            scope_type="macro",
            scope_key="XLP",          # priceable subject ticker (D4)
            direction=direction,
            horizon_d=21,
            timestamp_quality="CRAWL_BOUNDED",
            bench="XLK",              # priceable bench ticker (offense proxy, D4)
            claim_family=QLEDGER_FAMILY,
            extra=extra,
        ))
    if not claims_in:
        return []
    return q.register_batch(claims_in, root=root, dedupe=True)


# ── nightly entry point ────────────────────────────────────────────────────────

def nightly_run(root: Path | None = None) -> dict[str, Any]:
    """Nightly build step: detect events >= SHIP_DATE, append ledger, register
    one CRAWL_BOUNDED qledger claim per CONFIRMED/FADED event at horizon_d=21
    (chassis grades at 5d + 21d automatically via in_scope_horizons).
    MIXED events abstain (no claim registered).

    The 2024→ descriptive scan is run once for the summary stats but events
    before SHIP_DATE are NEVER written to data/; they appear only in the site
    artifact (flip_confirmation_data.json `descriptive_scan` block).

    Called by scripts/build_flip_confirmation.py.
    Returns a summary dict for the build log.
    """
    try:
        # full descriptive scan for stats; ledger/claims filtered to >= SHIP_DATE
        events = detect_since("2024-01-01")
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
