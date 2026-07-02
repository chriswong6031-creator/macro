"""scripts/backfill_qledger_us.py — W1 US adapter + idempotent backfill.

Populates data/qledger/claims.jsonl from three source ledgers:

  ALTDATA  — data/altdata/theses.jsonl  (133 theses; PIT entry_levels present,
              falsifier.check.kind == rel_return vs SPY; desk="altdata").
             All theses have lean="overweight" → direction=+1.  The claim's
             horizon_d comes from the thesis horizon_d; grader's 5/21d passes
             give shadow grades immediately.

  RADAR    — data/radar/edge_snapshots.jsonl  (~2,489 rows, 12 snapshot dates;
             horizon_d absent on legacy rows → treated as horizon_d=63 so they
             grade at 5/21/63; desk="radar").
             Direction is derived from the snapshot state:
               POSITIVE_DIVERGENCE / CONFIRMED_UP   → +1
               NEGATIVE_DIVERGENCE / CONFIRMED_DOWN → -1
             scope: kind="ticker" → entity; kind="basket" → basket.
             The honest-n rule: one claim per (date,subject) → n_dates dedup
             works naturally because each claim carries its snapshot asof date.

  POLICY   — data/policy_intent/theses.jsonl (13 theses; desk="policy").
             Mapping:
               falsifier.check.kind == "rel_return" AND subject resolves in
               the price layer → gradeable entity claim, direction from lean
               (overweight → +1, underweight → -1).
               falsifier.check.kind == "soft" OR subject NOT in price layer →
               direction=0 (salience-only / display-only) with extra flag
               ungradeable_soft=True; these are explicitly display-only claims
               and are reported in counts.n_rejected as soft-dark (they pass
               register() with direction=0 and status=open, so they are not
               technically rejected — they are recorded as salience-only per D4:
               "the fraction that goes dark under this constraint is itself
               logged and reported").

All adapters are idempotent — stable claim_ids derived from source row ids let
register() dedup freely.  Re-running the backfill is safe.

Usage:
  python -m scripts.backfill_qledger_us [--root PATH] [--desk altdata|radar|policy|all]

The nightly collect pipeline calls this after the collect step so that any new
snapshot or thesis is picked up on the first overnight run after W1 ships.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# Engine imports — must NOT import from the nightly runner or render layers.
from engine.qledger import (
    TIMESTAMP_QUALITY,
    make_claim,
    register,
)
from engine.ai_desk import _close_series
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Horizon constants
# ---------------------------------------------------------------------------
# Legacy radar snapshots lack an explicit horizon_d.  They are treated as 63d
# (SEED_HORIZON_D from radar.py) so they grade at 5/21/63d via in_scope_horizons.
_RADAR_DEFAULT_HORIZON_D = 63

# Radar states → direction
_BULLISH_STATES = {"POSITIVE_DIVERGENCE", "CONFIRMED_UP"}
_BEARISH_STATES = {"NEGATIVE_DIVERGENCE", "CONFIRMED_DOWN"}

# timestamp_quality for all three source types ([P2] / §2.2)
_TQ_ALTDATA = "DISCLOSURE_DATE"    # thesis logged_at is a disclosure-style stamp;
                                   # +1bd embargo applied to entry anchor (PIT fix)
_TQ_RADAR   = "SNAPSHOT_DATE"     # edge_snapshots are point-in-time display snapshots;
                                   # but we need them gradeable — snapshots are *display*
                                   # readings so CRAWL_BOUNDED is correct (crawl time
                                   # is the bound, no embargo needed for nightly reads).
                                   # Override: use CRAWL_BOUNDED so they grade.
_TQ_RADAR   = "CRAWL_BOUNDED"     # corrected: snapshot accrual = crawl-bounded nightly
_TQ_POLICY  = "DISCLOSURE_DATE"   # policy theses are analyst-stamped; +1bd entry anchor


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows


def _ticker_priceable(ticker: str, root: Path) -> bool:
    """True when the price layer can resolve this ticker."""
    try:
        s = _close_series(ticker, root)
        return s is not None and not s.empty
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# ALTDATA adapter
# ---------------------------------------------------------------------------

def _altdata_direction(thesis: dict) -> int:
    """All current altdata theses are overweight → +1.
    Future: underweight → -1, neutral → 0.
    """
    lean = str(thesis.get("lean") or "").lower()
    if lean == "overweight":
        return 1
    if lean == "underweight":
        return -1
    return 0  # neutral / salience-only


def _altdata_entry_levels(thesis: dict) -> tuple[float | None, float | None]:
    """Extract (subject_level, bench_level) from thesis entry_levels.
    The altdata schema uses ticker-keyed dict: {TICKER: price, SPY: price}.
    """
    el = thesis.get("entry_levels") or {}
    ticker = thesis.get("ticker", "")
    subj = el.get(ticker)
    bench = el.get("SPY")
    return (
        float(subj) if subj is not None else None,
        float(bench) if bench is not None else None,
    )


def backfill_altdata(root: Path, *, dry_run: bool = False) -> int:
    """Register all open altdata theses as qledger claims. Returns count registered."""
    src = root / "data" / "altdata" / "theses.jsonl"
    theses = _load_jsonl(src)
    if not theses:
        log.warning("backfill_altdata: %s empty or missing", src)
        return 0

    registered = 0
    for thesis in theses:
        status = thesis.get("status", "open")
        if status not in ("open",):
            # closed/scored theses are historical; we still register them to
            # preserve the dark-fraction audit but they won't generate new grades.
            pass

        ticker = thesis.get("ticker", "").strip()
        asof = str(thesis.get("state_asof") or "").strip()
        if not ticker or not asof:
            log.debug("altdata skip: missing ticker/asof in %s", thesis.get("id"))
            continue

        horizon_d = int(thesis.get("horizon_d") or 63)
        direction = _altdata_direction(thesis)
        subj_level, bench_level = _altdata_entry_levels(thesis)
        check_by = thesis.get("check_by")
        falsifier = thesis.get("falsifier")

        # Stable claim_id from source id (the thesis id already encodes
        # date+ticker+desk so it is a perfect salt for idempotency).
        source_id = str(thesis.get("id") or "")

        claim = make_claim(
            desk="altdata",
            asof=asof,
            scope_type="entity",
            scope_key=ticker,
            direction=direction,
            horizon_d=horizon_d,
            timestamp_quality=_TQ_ALTDATA,
            subject_level=subj_level,
            bench_level=bench_level,
            bench="SPY",
            falsifier=falsifier,
            check_by=check_by,
            extra={
                "source_id": source_id,
                "channels": thesis.get("channels"),
                "convergence_score": thesis.get("convergence_score"),
                "original_status": status,
            },
        )
        # Use source_id as salt so claim_id is stable across re-runs
        claim["salt"] = source_id

        if not dry_run:
            stored = register(claim, root)
            log.debug("altdata: %s → claim_id=%s status=%s",
                      source_id, stored.get("claim_id"), stored.get("status"))
        registered += 1

    log.info("backfill_altdata: processed %d theses", registered)
    return registered


# ---------------------------------------------------------------------------
# RADAR adapter
# ---------------------------------------------------------------------------

def _radar_direction(state: str) -> int:
    """Mirror radar_ic._BULLISH_STATES / _BEARISH_STATES semantics exactly."""
    if state in _BULLISH_STATES:
        return 1
    if state in _BEARISH_STATES:
        return -1
    return 0  # unknown state → salience-only


def _radar_scope_type(kind: str) -> str:
    """kind='ticker' → entity; kind='basket' → basket (D4 scope mapping)."""
    if kind == "ticker":
        return "entity"
    return "basket"


def _radar_claim_salt(row: dict) -> str:
    """Stable salt: date|subject|state so a state-change on the same date
    creates a distinct claim rather than deduping to the same id."""
    return f"{row.get('date')}|{row.get('subject')}|{row.get('state')}"


def backfill_radar(root: Path, *, dry_run: bool = False) -> int:
    """Register all radar edge_snapshots as qledger claims. Returns count processed."""
    src = root / "data" / "radar" / "edge_snapshots.jsonl"
    snapshots = _load_jsonl(src)
    if not snapshots:
        log.warning("backfill_radar: %s empty or missing", src)
        return 0

    registered = 0
    for row in snapshots:
        date_str = str(row.get("date") or "").strip()
        kind = str(row.get("kind") or "").strip()
        subject = str(row.get("subject") or "").strip()
        ticker = str(row.get("ticker") or "").strip()
        state = str(row.get("state") or "").strip()

        if not date_str or not subject or not ticker:
            log.debug("radar skip: missing fields in %s", row)
            continue

        # horizon_d: stamped since #904; legacy rows → RADAR_DEFAULT_HORIZON_D
        horizon_d = int(row.get("horizon_d") or _RADAR_DEFAULT_HORIZON_D)
        direction = _radar_direction(state)
        scope_type = _radar_scope_type(kind)
        salt = _radar_claim_salt(row)

        claim = make_claim(
            desk="radar",
            asof=date_str,
            scope_type=scope_type,
            scope_key=ticker,           # grade against the proxy ticker
            direction=direction,
            horizon_d=horizon_d,
            timestamp_quality=_TQ_RADAR,
            bench="SPY",
            extra={
                "source_subject": subject,  # basket_id or ticker name
                "edge_score": row.get("edge_score"),
                "state": state,
                "kind": kind,
            },
        )
        claim["salt"] = salt

        if not dry_run:
            stored = register(claim, root)
            log.debug("radar: %s|%s → claim_id=%s status=%s",
                      date_str, subject, stored.get("claim_id"), stored.get("status"))
        registered += 1

    log.info("backfill_radar: processed %d snapshots", registered)
    return registered


# ---------------------------------------------------------------------------
# POLICY adapter
# ---------------------------------------------------------------------------

def _policy_direction(thesis: dict, priceable: bool) -> int:
    """Direction from lean, but only for priceable + rel_return theses.
    soft or not-priceable → 0 (salience-only).
    """
    check_kind = (thesis.get("falsifier") or {}).get("check", {}).get("kind", "soft")
    if check_kind == "soft" or not priceable:
        return 0  # display-only salience
    lean = str(thesis.get("lean") or "").lower()
    if lean == "overweight":
        return 1
    if lean == "underweight":
        return -1
    return 0


def _policy_entry_levels(thesis: dict) -> tuple[float | None, float | None]:
    """Extract (subject_level, bench_level) from policy entry_levels.
    Policy schema uses ticker-keyed dict similar to altdata.
    """
    el = thesis.get("entry_levels") or {}
    ticker = thesis.get("subject", "")
    subj = el.get(ticker)
    bench = el.get("SPY")
    return (
        float(subj) if subj is not None else None,
        float(bench) if bench is not None else None,
    )


def backfill_policy(root: Path, *, dry_run: bool = False) -> int:
    """Register all policy theses as qledger claims. Returns count processed.

    Subject→proxy map (D4):
      - If falsifier.check.kind == "rel_return" AND subject resolves in the
        price layer → entity claim with direction from lean, fully gradeable.
      - Otherwise (soft falsifier or no price series) → direction=0,
        ungradeable_soft=True, display-only.  The dark fraction is tracked
        via these direction=0 claims (D4: "logged and reported").

    Note: BIL, ITA, GLD lack local price series at W1 time.  Their rel_return
    theses that ALSO lack series degrade to direction=0 display-only.  The
    ITA and GLD theses with kind=soft are already display-only by falsifier.
    """
    src = root / "data" / "policy_intent" / "theses.jsonl"
    theses = _load_jsonl(src)
    if not theses:
        log.warning("backfill_policy: %s empty or missing", src)
        return 0

    registered = 0
    dark_count = 0
    for thesis in theses:
        subject = str(thesis.get("subject") or "").strip()
        asof = str(thesis.get("state_asof") or "").strip()
        if not subject or not asof:
            log.debug("policy skip: missing subject/asof in %s", thesis.get("id"))
            continue

        horizon_d = int(thesis.get("horizon_d") or 63)
        check_kind = (thesis.get("falsifier") or {}).get("check", {}).get("kind", "soft")
        priceable = _ticker_priceable(subject, root)

        direction = _policy_direction(thesis, priceable)
        is_dark = direction == 0
        if is_dark:
            dark_count += 1

        subj_level, bench_level = _policy_entry_levels(thesis)
        check_by = thesis.get("check_by")
        falsifier = thesis.get("falsifier")
        source_id = str(thesis.get("id") or "")

        claim = make_claim(
            desk="policy",
            asof=asof,
            scope_type="entity",
            scope_key=subject,
            direction=direction,
            horizon_d=horizon_d,
            timestamp_quality=_TQ_POLICY,
            subject_level=subj_level,
            bench_level=bench_level,
            bench="SPY",
            falsifier=falsifier,
            check_by=check_by,
            extra={
                "source_id": source_id,
                "lean": thesis.get("lean"),
                "conviction": thesis.get("conviction"),
                "actor": thesis.get("actor"),
                "check_kind": check_kind,
                # D4: explicitly flag soft/unresolvable claims for dark-fraction report
                "ungradeable_soft": is_dark,
            },
        )
        claim["salt"] = source_id

        if not dry_run:
            stored = register(claim, root)
            log.debug("policy: %s/%s → claim_id=%s direction=%d dark=%s",
                      source_id, subject, stored.get("claim_id"), direction, is_dark)
        registered += 1

    log.info("backfill_policy: processed %d theses (%d dark/salience-only)",
             registered, dark_count)
    return registered


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Idempotent backfill of qledger claims from US source ledgers."
    )
    parser.add_argument("--root", default=None,
                        help="Repo root path (default: config.ROOT)")
    parser.add_argument("--desk", default="all",
                        choices=["altdata", "radar", "policy", "all"],
                        help="Which desk(s) to backfill (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and validate but do not write claims")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    root = Path(args.root) if args.root else config.ROOT
    desk = args.desk
    dry = args.dry_run

    if dry:
        log.info("DRY RUN — no writes")

    total = 0
    if desk in ("altdata", "all"):
        total += backfill_altdata(root, dry_run=dry)
    if desk in ("radar", "all"):
        total += backfill_radar(root, dry_run=dry)
    if desk in ("policy", "all"):
        total += backfill_policy(root, dry_run=dry)

    log.info("backfill complete: %d source rows processed", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
