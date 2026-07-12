"""scripts/backfill_qledger_us.py — W1 US adapter + idempotent backfill.

Populates data/qledger/claims.jsonl from three source ledgers:

  ALTDATA  — data/altdata/theses.jsonl  (169 theses; PIT entry_levels present,
              falsifier.check.kind == rel_return vs SPY; desk="altdata").
             ALTDATA_REBOOT W2 (2026-07-12): each thesis is routed to a
             per-channel claim_family based on its highest-weight channel:
               altdata_event  — special_situation, material_8k, gov_contract*,
                                gov_grant*, fda_*, clinical_*, activist_13d
               altdata_flow   — darkpool_accum, unusual_options
               altdata_mid    — insider_cluster, insider_buy, app_demand, analyst*
               altdata_slow   — congress*, trump, lobbying*, smart_money_13f,
                                13f_add, patent_cluster, affiliation
               altdata_attention — retail_buzz (REVERSION: direction=-1, 5d)
             Legacy theses (pre-2026-07-12) carry claim_family=None or "altdata"
             and are registered unchanged (no retro-tagging; ledger is PIT).
             For each real claim, 2 matched placebo claims are emitted
             (is_placebo=True, placebo_path='altdata_matched').

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
import hashlib
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
    register_batch,
)
from engine.ai_desk import _close_series
from engine.altdata_ledger import (
    FAMILY_DIRECTION_OVERRIDE,
    FAMILY_HORIZON_D,
    assign_claim_family,
)
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
# Placebo helpers (ALTDATA_REBOOT W2 — research/ALTDATA_REBOOT.md §2.2)
# ---------------------------------------------------------------------------

# ACTIVATION date: new theses from 2026-07-12 get per-family routing + placebos.
# Legacy theses (pre-activation) are registered with claim_family=None→desk=altdata
# and receive NO placebos (the legacy family has no matched placebo tape).
_ACTIVATION_DATE = "2026-07-12"

# Liquid US universe for placebo ticker draws.  The real universe is data/universe.
# For the placebo draw we use a deterministic seed derived from (asof, real_ticker,
# family, i) so the same thesis always draws the same placebo tickers.
# The universe is loaded lazily once per backfill run.
_PLACEBO_UNIVERSE: list[str] | None = None

_PLACEBO_UNIVERSE_FALLBACK = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK.B", "JPM", "UNH",
    "XOM", "JNJ", "V", "PG", "MA", "HD", "CVX", "MRK", "PEP", "ABBV",
    "LLY", "AVGO", "KO", "COST", "MCD", "TMO", "WMT", "CSCO", "ACN", "BAC",
    "NKE", "ABT", "CRM", "NEE", "ORCL", "ADBE", "TXN", "BMY", "PM", "RTX",
    "HON", "IBM", "CAT", "DE", "UPS", "SPGI", "MMM", "ELV", "GS", "AXP",
]


def _load_placebo_universe(root: Path) -> list[str]:
    """Load the liquid US ticker universe for placebo draws.
    Falls back to a hardcoded S&P 50 list when the universe file is absent.
    """
    global _PLACEBO_UNIVERSE
    if _PLACEBO_UNIVERSE is not None:
        return _PLACEBO_UNIVERSE
    # Try the membership file (data/universe/membership.parquet or members.jsonl)
    for cand in [
        root / "data" / "universe" / "members.jsonl",
        root / "data" / "universe" / "membership.jsonl",
    ]:
        if cand.exists():
            try:
                tickers = []
                for line in cand.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    t = obj.get("ticker") or obj.get("symbol") or ""
                    if t:
                        tickers.append(t)
                if tickers:
                    _PLACEBO_UNIVERSE = tickers
                    log.debug("placebo universe: %d tickers from %s", len(tickers), cand)
                    return _PLACEBO_UNIVERSE
            except Exception:  # noqa: BLE001
                pass
    _PLACEBO_UNIVERSE = _PLACEBO_UNIVERSE_FALLBACK
    log.debug("placebo universe: fallback (%d tickers)", len(_PLACEBO_UNIVERSE))
    return _PLACEBO_UNIVERSE


def _placebo_tickers(
    asof: str, real_ticker: str, family: str, converging_tickers: set[str],
    universe: list[str], n: int = 2,
) -> list[str]:
    """Draw n distinct placebo tickers deterministically using hashlib.

    Tickers are drawn from `universe` excluding `converging_tickers` (the set of
    names that converged on this date, so the placebo is a genuine non-signal draw).
    The seed is derived from (asof, real_ticker, family) — reproducible across runs.
    """
    exclude = set(converging_tickers)
    candidates = [t for t in universe if t not in exclude and t != real_ticker]
    if not candidates:
        candidates = [t for t in universe if t != real_ticker]

    result: list[str] = []
    seen: set[str] = set()
    i = 0
    while len(result) < n and i < len(candidates) * 2 + n * 10:
        raw = f"{asof}|{real_ticker}|{family}|{i}"
        h = int(hashlib.sha256(raw.encode()).hexdigest(), 16)
        idx = h % len(candidates)
        t = candidates[idx]
        if t not in seen:
            result.append(t)
            seen.add(t)
        i += 1
    return result


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
    """Register all open altdata theses as qledger claims. Returns count registered.

    ALTDATA_REBOOT W2 (active 2026-07-12):
    - Theses on/after _ACTIVATION_DATE are routed to per-channel claim families
      (altdata_event / altdata_flow / altdata_mid / altdata_slow / altdata_attention).
    - Legacy theses (pre-activation or no claim_family in source) are registered
      with claim_family derived from thesis.claim_family (or desk=altdata fallback).
      No retro-tagging; ledger is append-only PIT.
    - For each new-family real claim, 2 matched placebo claims are emitted
      (is_placebo=True, placebo_path='altdata_matched').
    """
    src = root / "data" / "altdata" / "theses.jsonl"
    theses = _load_jsonl(src)
    if not theses:
        log.warning("backfill_altdata: %s empty or missing", src)
        return 0

    universe = _load_placebo_universe(root)
    # Build the set of converging tickers per asof date (for placebo exclusion).
    converging_by_date: dict[str, set[str]] = {}
    for thesis in theses:
        asof = str(thesis.get("state_asof") or "").strip()
        tk = thesis.get("ticker", "").strip()
        if asof and tk:
            converging_by_date.setdefault(asof, set()).add(tk)

    all_claims: list[dict] = []
    registered = 0

    for thesis in theses:
        ticker = thesis.get("ticker", "").strip()
        asof = str(thesis.get("state_asof") or "").strip()
        if not ticker or not asof:
            log.debug("altdata skip: missing ticker/asof in %s", thesis.get("id"))
            continue

        # Family routing: use claim_family from thesis if present (W2+), else
        # derive it from channels (for theses that already have the field from
        # build_theses). Legacy theses without claim_family stay as "altdata".
        chans = thesis.get("channels") or []
        thesis_family = thesis.get("claim_family")
        if thesis_family:
            family = thesis_family
        elif asof >= _ACTIVATION_DATE:
            # New-era thesis without claim_family stamped: derive from channels.
            family = assign_claim_family(chans)
        else:
            # Legacy pre-activation thesis: use the legacy family.
            family = "altdata"

        is_new_family = family not in ("altdata", None)

        # For attention family, direction overrides to -1 (fade the buzz).
        direction_override = FAMILY_DIRECTION_OVERRIDE.get(family)
        if direction_override is not None:
            direction = direction_override
        else:
            direction = _altdata_direction(thesis)

        horizon_d = FAMILY_HORIZON_D.get(family, int(thesis.get("horizon_d") or 63))
        subj_level, bench_level = _altdata_entry_levels(thesis)
        check_by = thesis.get("check_by")
        falsifier = thesis.get("falsifier")
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
            claim_family=family,
            extra={
                "source_id": source_id,
                "channels": chans,
                "convergence_score": thesis.get("convergence_score"),
                "original_status": thesis.get("status", "open"),
            },
        )
        # Use source_id as salt so claim_id is stable across re-runs
        claim["salt"] = source_id
        all_claims.append(claim)
        registered += 1

        # Emit 2 matched placebo claims for new-family real claims (W2 placebo tape).
        if is_new_family:
            converging = converging_by_date.get(asof, set())
            placebo_tks = _placebo_tickers(asof, ticker, family, converging, universe, n=2)
            for i, ptk in enumerate(placebo_tks):
                pclaim = make_claim(
                    desk="altdata",
                    asof=asof,
                    scope_type="entity",
                    scope_key=ptk,
                    direction=direction,
                    horizon_d=horizon_d,
                    timestamp_quality=_TQ_ALTDATA,
                    bench="SPY",
                    claim_family=family,
                    is_placebo=True,
                    extra={
                        "placebo_path": "altdata_matched",
                        "placebo_real_ticker": ticker,
                        "placebo_real_source_id": source_id,
                    },
                )
                pclaim["salt"] = f"{source_id}|placebo|{i}"
                all_claims.append(pclaim)

    if not dry_run:
        register_batch(all_claims, root)
        log.info("backfill_altdata: processed %d theses → %d claims (incl. placebos)",
                 registered, len(all_claims))
    else:
        log.info("backfill_altdata: dry_run — %d theses → %d claims (not written)",
                 registered, len(all_claims))
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
