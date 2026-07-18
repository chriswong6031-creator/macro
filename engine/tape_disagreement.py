"""engine/tape_disagreement.py — tape_disagreement.v1 survival ledger (FTR W9).

FTR W9 grading pack — disagreement-event recording with explicit censoring and
Kaplan-Meier estimation as the analysis convention.

DEFINITION OF A DISAGREEMENT EVENT (deterministic, from committed artifacts)
------------------------------------------------------------------------------
A disagreement event is a (basket, date) pair where:
    turn_watch state == IGNITION   (from data/basket_turn/ledger.jsonl)
    AND
    slow_reco NOT IN {"enter", "accumulate"}  (from baskets.json site artifact)

Both conditions are read from committed artifacts only.  No fusion threshold,
no LLM-emitted states.  The slow_reco is the `reco` field on each basket row
in site/basketdata/baskets.json (build_baskets.py output, nightly-stamped).

OUTCOME TRACKING
----------------
For each event, outcome at +10 and +21 sessions:
    slow_state_flipped   — reco moved to "enter" or "accumulate" by that session
    tape_faded           — basket EW vs SPY negative over the window
    unresolved           — neither state flipped nor tape definitively faded
                           (window elapsed but no strong signal; censored=False)

CENSORING CONVENTION
--------------------
- Outcomes are only recorded when the observation window has elapsed.
- An event whose +21-session window has not yet elapsed gets
  outcome_10d=None, outcome_21d=None (right-censored, explicit).
- The Kaplan-Meier convention (analysis pass only, at 2026-10-15 clock)
  handles censored rows — the nightly writer only appends rows and updates
  outcomes as they mature.

ALLOCATION-FLIP LATENCY NOTE
-----------------------------
Allocation-headline flips are structurally ≥22 sessions (SKIP_D=21 in
narrative_rotation.py).  This family is a LATENCY METER for basket-level
reco, not an allocation-flip predictor.  The analysis at 2026-10-15 will
report allocation-level flip rates separately as a documented structural zero.

PLACEBO
-------
The existing qledger placebo sampler requires structural extension for
basket/composite scopes.  Registered with a deferred note per the brief:
"placebo: deferred to first grading read 2026-10-15 — wire existing
random-basket + time-shifted sampler when the qledger placebo extension is
available (R-TIL-6 pattern)."

NIGHTLY WRITER
--------------
Gated on COLLECT_LANE=nightly (FT-R5).
Appends new disagreement events (keep-first per basket+date).
Updates outcome columns for matured rows each nightly run.
Writes to data/basket_turn/disagreement_ledger.jsonl.
No backfill — events only from SHIP_DATE.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────────────
SHIP_DATE = "2026-07-09"

# Slow reco values that do NOT count as "aligned with tape"
# A disagreement fires when reco is NOT in this set
SLOW_RECO_ALIGNED = frozenset({"enter", "accumulate"})

# Outcome window lengths (trading sessions)
OUTCOME_WINDOWS = (10, 21)

_LEDGER_DIR  = "basket_turn"
_LEDGER_FILE = "disagreement_ledger.jsonl"

# ── authority block ────────────────────────────────────────────────────────────
AUTHORITY = {
    "tier":          "display",
    "horizon_role":  "context",
    "may_rank":      False,
    "may_gate":      False,
    "may_size":      False,
    "may_escalate":  False,
}

REGISTRATION_NOTE = (
    "tape_disagreement.v1 — disagreement-day records: basket IGNITION while "
    "slow reco NOT IN {enter, accumulate}. "
    "Outcome tracking: slow_state_flipped / tape_faded / unresolved "
    "at +10 and +21 sessions, with explicit right-censoring. "
    "Analysis convention: Kaplan-Meier survival estimation (analysis pass at "
    "2026-10-15 clock). "
    "Allocation-headline flips are structurally ≥22 sessions (SKIP_D=21): "
    "this family is a LATENCY METER for basket-level reco, not an "
    "allocation-flip predictor. "
    "Placebo: deferred to first grading read 2026-10-15 (wire existing "
    "random-basket + time-shifted sampler when qledger placebo extension is "
    "available; R-TIL-6 pattern)."
)

from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled


# ── path helpers ───────────────────────────────────────────────────────────────

def _ledger_path(data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else config.data_dir()
    p = root / _LEDGER_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p / _LEDGER_FILE


# ── ledger I/O ─────────────────────────────────────────────────────────────────

def load_ledger(data_root: Path | None = None) -> list[dict]:
    """Load all disagreement ledger rows. Returns [] if absent/corrupt."""
    p = _ledger_path(data_root)
    if not p.exists():
        return []
    rows: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _write_ledger(rows: list[dict], data_root: Path | None = None) -> None:
    """Write ledger atomically via temp-file + os.replace."""
    p = _ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(r, default=str) for r in rows)
    if content:
        content += "\n"
    fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=".tape_disagree_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, p)
    except Exception:  # noqa: BLE001
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── event detection ────────────────────────────────────────────────────────────

def _load_turn_watch_ledger(data_root: Path | None = None) -> list[dict]:
    """Load data/basket_turn/ledger.jsonl (produced by basket_turn_watch.py)."""
    root = data_root if data_root is not None else config.data_dir()
    p = root / "basket_turn" / "ledger.jsonl"
    if not p.exists():
        return []
    rows: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _load_baskets_site_artifact(root: Path | None = None) -> dict[str, dict]:
    """Load site/basketdata/baskets.json and return {basket_id: theme_dict}.

    The ``reco`` field is a THEME-level property, not a basket-level property.
    It lives at ``data["theme_intel"]["themes"]`` — a list of dicts with an
    ``id`` field that matches the basket id for scored baskets.

    Returns {} if absent (graceful degradation — events cannot be formed
    without the slow-reco artifact).
    """
    r = root or config.ROOT
    cfg = config.load()
    site_dir = r / cfg.get("storage", {}).get("site_dir", "site")
    p = site_dir / "basketdata" / "baskets.json"
    if not p.exists():
        log.warning("tape_disagreement: baskets.json not found at %s — no events formed", p)
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        # reco is a theme-level property in data["theme_intel"]["themes"]
        themes_list = raw.get("theme_intel", {}).get("themes") or []
        return {t.get("id", ""): t for t in themes_list if t.get("id")}
    except Exception as exc:  # noqa: BLE001
        log.warning("tape_disagreement: failed to load baskets.json: %s", exc)
        return {}


def detect_disagreement_events(
    as_of: str,
    turn_watch_rows: list[dict],
    baskets_map: dict[str, dict],
    ship_date: str = SHIP_DATE,
) -> list[dict]:
    """Detect disagreement events for a given session date.

    A disagreement event fires when:
        turn_watch state == IGNITION
        AND slow_reco NOT IN {"enter", "accumulate"}

    Parameters
    ----------
    as_of : str
        ISO date of the session being evaluated.
    turn_watch_rows : list[dict]
        All rows from data/basket_turn/ledger.jsonl.
    baskets_map : dict[str, dict]
        {basket_id: basket_dict} from site/basketdata/baskets.json.
    ship_date : str
        No events before this date.

    Returns
    -------
    list[dict] — one dict per disagreement event, with:
        basket_id, event_date, turn_watch_state, slow_reco,
        legs (from turn-watch row), outcome_10d, outcome_21d
        (both None — to be filled by nightly outcome-update pass)
    """
    ship_ts = date.fromisoformat(ship_date)
    try:
        as_of_date = date.fromisoformat(as_of)
    except ValueError:
        return []
    if as_of_date < ship_ts:
        return []

    # Filter turn-watch rows for the given date and IGNITION state
    ignition_today = [
        r for r in turn_watch_rows
        if r.get("state") == "IGNITION"
        and (r.get("date") or r.get("as_of")) == as_of
    ]

    events: list[dict] = []
    for row in ignition_today:
        basket_id = row.get("basket_id")
        if not basket_id:
            continue

        slow_reco = None
        if basket_id in baskets_map:
            slow_reco = baskets_map[basket_id].get("reco")

        # A disagreement fires when slow_reco is NOT an aligned state
        # (also fires when slow_reco is absent — we record the null honestly)
        if slow_reco in SLOW_RECO_ALIGNED:
            continue

        events.append({
            "basket_id":         basket_id,
            "event_date":        as_of,
            "turn_watch_state":  "IGNITION",
            "slow_reco":         slow_reco,
            "legs":              row.get("legs", {}),
            # Outcomes filled by the outcome-update pass when windows mature
            "outcome_10d":       None,
            "outcome_21d":       None,
            # Censoring metadata
            "censored_10d":      True,    # right-censored until +10 sessions have elapsed
            "censored_21d":      True,    # right-censored until +21 sessions have elapsed
            "registered_note":   REGISTRATION_NOTE,
        })
    return events


# ── outcome update ─────────────────────────────────────────────────────────────

def _load_membership(data_root: Path | None = None) -> dict[str, dict]:
    """Load data/baskets/membership.json and return {basket_id: basket_dict}.

    This is the canonical member source (mirrors basket_turn_watch.py usage).
    Returns {} if absent.
    """
    root = data_root if data_root is not None else config.data_dir()
    p = root / "baskets" / "membership.json"
    if not p.exists():
        log.warning("tape_disagreement: membership.json not found at %s", p)
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw.get("baskets") or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("tape_disagreement: failed to load membership.json: %s", exc)
        return {}


def _active_tickers(basket_id: str, data_root: Path | None = None) -> list[str]:
    """Return currently active (non-removed) member tickers for a basket.

    Reads from data/baskets/membership.json (canonical member source, mirrors
    basket_turn_watch._active_tickers).
    """
    membership = _load_membership(data_root)
    basket = membership.get(basket_id, {})
    members = basket.get("members") or []
    return [
        m["ticker"]
        for m in members
        if m.get("removed") is None and m.get("ticker")
    ]


def _basket_ew_vs_spy_return(
    basket_id: str,
    event_date: str,
    n_sessions: int,
    baskets_map: dict[str, dict],
    data_root: Path | None = None,
) -> float | None:
    """Compute equal-weight basket return vs SPY over n_sessions from event_date.

    Members are sourced from data/baskets/membership.json (the canonical member
    store — basket_turn_watch uses the same source).  The ``baskets_map`` arg
    (theme-level artifact keyed by basket id) is intentionally not used for
    member lookup: it does not carry a member list.

    SPY lives at data/yahoo/SPY.parquet (not data/stocks/).

    Returns the EW basket excess return (basket_ew_ret - spy_ret), or None if
    price data is insufficient.
    """
    tickers = _active_tickers(basket_id, data_root)
    if not tickers:
        return None

    root = data_root if data_root is not None else config.data_dir()
    stocks_dir = root / "stocks"

    try:
        event_ts = pd.Timestamp(event_date)
        event_ts = event_ts.normalize()
    except Exception:  # noqa: BLE001
        return None

    member_rets: list[float] = []
    for ticker in tickers:
        p = stocks_dir / f"{ticker}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p, columns=["close"])
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            df = df[~df.index.duplicated(keep="last")]
            df = df[df.index >= event_ts]
            if len(df) < n_sessions + 1:
                continue
            entry_price = float(df["close"].iloc[0])
            exit_price  = float(df["close"].iloc[n_sessions])
            if entry_price > 0:
                member_rets.append(exit_price / entry_price - 1.0)
        except Exception:  # noqa: BLE001
            continue

    if not member_rets:
        return None

    basket_ew = sum(member_rets) / len(member_rets)

    # SPY lives at data/yahoo/SPY.parquet (not data/stocks/)
    spy_p = root / "yahoo" / "SPY.parquet"
    if not spy_p.exists():
        return None
    try:
        spy_df = pd.read_parquet(spy_p, columns=["close"])
        spy_df.index = pd.to_datetime(spy_df.index)
        spy_df = spy_df.sort_index()
        spy_df = spy_df[~spy_df.index.duplicated(keep="last")]
        spy_df = spy_df[spy_df.index >= event_ts]
        if len(spy_df) < n_sessions + 1:
            return None
        spy_entry = float(spy_df["close"].iloc[0])
        spy_exit  = float(spy_df["close"].iloc[n_sessions])
        if spy_entry <= 0:
            return None
        spy_ret = spy_exit / spy_entry - 1.0
    except Exception:  # noqa: BLE001
        return None

    return round(basket_ew - spy_ret, 6)


def _reco_flipped(
    basket_id: str,
    event_date: str,
    n_sessions: int,
    data_root: Path | None = None,
) -> bool | None:
    """Check whether the slow reco transitioned to enter/accumulate within n_sessions.

    The basket-level reco history is NOT currently persisted in the committed
    store (the nightly builds overwrite baskets.json).  Without a PIT reco
    history this outcome leg cannot be computed from committed data.

    Returns None (honest null) — the structural latency constraint is printed
    in the registration note as a known limitation.  Once a PIT reco history
    is committed (future scope), this function will be wired.
    """
    # NOTE: reco history would need a PIT ledger committed nightly.
    # Until then, return None (honest null, explicitly censored).
    return None


def _spy_trading_sessions_since(
    event_date: str,
    as_of: str,
    data_root: Path | None = None,
) -> int:
    """Count trading sessions elapsed since event_date by counting SPY parquet rows.

    Uses the SPY price index (data/yahoo/SPY.parquet) as the authoritative
    trading-session clock, not pd.bdate_range (which includes holidays).
    Returns -1 if SPY data is unavailable.
    """
    root = data_root if data_root is not None else config.data_dir()
    spy_p = root / "yahoo" / "SPY.parquet"
    if not spy_p.exists():
        return -1
    try:
        spy_df = pd.read_parquet(spy_p, columns=["close"])
        spy_df.index = pd.to_datetime(spy_df.index)
        spy_df = spy_df.sort_index()
        spy_df = spy_df[~spy_df.index.duplicated(keep="last")]
        event_ts = pd.Timestamp(event_date).normalize()
        as_of_ts = pd.Timestamp(as_of).normalize()
        # Count rows strictly after event_date up through as_of
        window = spy_df[(spy_df.index > event_ts) & (spy_df.index <= as_of_ts)]
        return len(window)
    except Exception:  # noqa: BLE001
        return -1


def update_outcomes(
    rows: list[dict],
    baskets_map: dict[str, dict],
    as_of: str,
    data_root: Path | None = None,
) -> list[dict]:
    """Update outcome columns for rows whose observation windows have elapsed.

    Maturity clock: counts rows in the SPY parquet strictly after event_date
    (data/yahoo/SPY.parquet), NOT pd.bdate_range — holidays are excluded.

    For each row:
    - If +10 sessions have elapsed since event_date AND outcome_10d is None:
      compute and fill outcome_10d.  Mark censored_10d=False.
    - If +21 sessions have elapsed since event_date AND outcome_21d is None:
      compute and fill outcome_21d.  Mark censored_21d=False.

    Censoring semantics (KM convention):
        censored=True  means event-not-yet-observed (right-censored).
        censored=False means the outcome window has elapsed.
        When excess is None (price data insufficient), outcome stays None and
        censored stays True so the row re-evaluates next nightly run.  Only
        a definitive outcome (tape_faded, slow_state_flipped, or
        unresolved when excess IS available) closes the row.

    Outcome vocabulary:
        slow_state_flipped  — reco moved to enter/accumulate (PIT ledger req'd)
        tape_faded          — basket EW vs SPY < 0 over the window
        unresolved          — window elapsed, excess computed, no strong signal
    """
    updated_rows: list[dict] = []
    for row in rows:
        row = dict(row)  # shallow copy — do not mutate in place
        event_date = row.get("event_date")
        if not event_date:
            updated_rows.append(row)
            continue

        basket_id = row.get("basket_id", "")
        elapsed = _spy_trading_sessions_since(event_date, as_of, data_root)

        for n_sessions, outcome_key, censored_key in [
            (10, "outcome_10d", "censored_10d"),
            (21, "outcome_21d", "censored_21d"),
        ]:
            if row.get(outcome_key) is not None:
                # Already filled — do not overwrite
                continue

            if elapsed < 0 or elapsed < n_sessions:
                # Window not yet elapsed; row stays censored=True, outcome=None
                continue

            # Outcome 1: slow_state_flipped (requires PIT reco history — honest null)
            flipped = _reco_flipped(basket_id, event_date, n_sessions, data_root)

            # Outcome 2: tape_faded (EW vs SPY < 0 over window)
            excess = _basket_ew_vs_spy_return(
                basket_id, event_date, n_sessions, baskets_map, data_root
            )

            # When excess is None (price data missing), leave outcome unset so
            # the row re-evaluates next night (KM: censored=True until observable).
            if flipped is None and excess is None:
                continue

            # Window has elapsed with observable data — record outcome
            row[censored_key] = False

            if flipped is True:
                row[outcome_key] = "slow_state_flipped"
            elif excess is not None and excess < 0:
                row[outcome_key] = "tape_faded"
            else:
                # Window elapsed, excess computed, no strong signal
                row[outcome_key] = "unresolved"

            # Record the raw return for analysis
            if excess is not None:
                row[f"excess_vs_spy_{n_sessions}d"] = excess

        updated_rows.append(row)
    return updated_rows


# ── nightly writer ─────────────────────────────────────────────────────────────

def nightly_run(
    as_of: str | None = None,
    data_root: Path | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Nightly build step: detect new disagreement events and update outcomes.

    Gated on COLLECT_LANE=nightly (FT-R5).  Exit-0-always: any error is
    captured, a ::warning:: is emitted, and the summary dict carries ok=False.

    Returns summary dict for the build log.
    """
    try:
        if as_of is None:
            as_of = date.today().isoformat()

        if not _ledger_advance_enabled():
            log.info(
                "tape_disagreement: COLLECT_LANE gate not set — detection ran "
                "but no ledger writes (nightly-only)"
            )
            return {
                "ok": True,
                "gate_skipped": True,
                "n_new_events": 0,
                "n_outcome_updates": 0,
            }

        r = root or config.ROOT
        turn_watch_rows = _load_turn_watch_ledger(data_root)
        baskets_map = _load_baskets_site_artifact(r)

        # 1. Detect new disagreement events for today
        new_events = detect_disagreement_events(
            as_of=as_of,
            turn_watch_rows=turn_watch_rows,
            baskets_map=baskets_map,
        )

        # 2. Load existing ledger
        existing_rows = load_ledger(data_root)

        # Keep-first: index existing rows by (basket_id, event_date)
        existing_keys: set[tuple[str, str]] = {
            (r.get("basket_id", ""), r.get("event_date", ""))
            for r in existing_rows
        }

        appended = 0
        for ev in new_events:
            key = (ev.get("basket_id", ""), ev.get("event_date", ""))
            if key not in existing_keys:
                existing_rows.append(ev)
                existing_keys.add(key)
                appended += 1

        # 3. Update outcomes for matured rows
        updated_rows = update_outcomes(
            rows=existing_rows,
            baskets_map=baskets_map,
            as_of=as_of,
            data_root=data_root,
        )

        outcome_updates = sum(
            1 for old, new in zip(existing_rows, updated_rows)
            if old.get("outcome_10d") != new.get("outcome_10d")
            or old.get("outcome_21d") != new.get("outcome_21d")
        )

        # 4. Write ledger atomically
        _write_ledger(updated_rows, data_root)

        log.info(
            "tape_disagreement: %d new events, %d outcome updates, %d total rows",
            appended, outcome_updates, len(updated_rows),
        )

        return {
            "ok": True,
            "n_new_events": appended,
            "n_outcome_updates": outcome_updates,
            "n_total_rows": len(updated_rows),
        }

    except Exception as exc:  # noqa: BLE001 — exit-0-always
        import sys
        print(f"::warning::tape_disagreement.nightly_run failed: {exc}", file=sys.stderr)
        log.warning("tape_disagreement.nightly_run failed: %s", exc)
        return {"ok": False, "error": str(exc)}
