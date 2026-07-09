"""engine/basket_turn_cohort.py — basket_turn.v1 qledger family (FTR W9).

FTR W9 grading pack — cohort-level qledger claims for the basket turn-watch
K-of-N confluence organ (FTR W4).

DOCTRINE (FT-R9)
----------------
Grading unit is the CATALYST-DAY COHORT, not the per-basket event.  All baskets
that reach IGNITION on the same session form one cohort.  The claim is on the
cohort equal-weight basket-EW return versus SPY over 21 trading days.

Co-firing baskets share members and a common catalyst; per-basket claims would
inflate N in violation of the DT-R14 / ticker-cluster-time-confound law.
WATCH rows never generate claims — only IGNITION-day cohorts register.

PRE-DECLARED REGISTRATION TEXT (verbatim per masterplan W4/FT-R9)
------------------------------------------------------------------
  "Sector-level standalone washout→turn construction printed NULL
  (Oracle P8 P-W1/S-W3; DO_NOT_REBUILD 'Washout × turn'). This K-of-N
  confluence family tests whether basket-granularity multi-leg confluence
  differs.  Expected-NULL forward meter: claims accrue from ship date, no
  backfill.  Promotion question earliest 2027, n≥8 distinct shock episodes."

CLAIM DESIGN
-----------
  desk / family  : basket_turn.v1
  scope_type     : basket
  scope_key      : the cohort-date ISO string (one claim per cohort-day)
  direction      : +1 always (claim: cohort EW > SPY at 21d)
  horizon_d      : 21 (chassis grades at 5d + 21d automatically)
  bench          : SPY (the cohort EW basket is the subject; SPY is bench)
  timestamp_quality : CRAWL_BOUNDED — ledger rows are EOD; no look-ahead
  subject        : virtual "basket_ew:{cohort_id}" — a composite ticker the
                   grader measures directly from the member close prices; the
                   qledger chassis cannot price virtual composites, so we store
                   cohort metadata in `extra` and the grading runner computes
                   excess_vs_spy in W9 analysis sessions.  scope_key carries
                   the cohort_id so the claim is uniquely keyed per date.
  NOTE           : Because the subject is a composite (not a single priceable
                   ticker in the parquet store), this claim registers with
                   scope_type="basket" and scope_key=cohort_id.  Standard
                   chassis grading (which grades single tickers) will not auto-
                   grade these claims; a dedicated analysis pass at the
                   2026-10-15 clock reads the ledger and grades cohort returns
                   directly.  The claim is still CRAWL_BOUNDED (gradeable=True)
                   so the chassis does not reject it; it simply won't produce
                   grade rows until the analysis pass runs.

NIGHTLY WRITER
--------------
Reads data/basket_turn/ledger.jsonl (produced by engine/basket_turn_watch.py).
Groups IGNITION-state rows by date → one cohort per date.
Registers one qledger claim per cohort-date with keep-first idempotency.
Gated on COLLECT_LANE=nightly (same gate as the source ledger writer).

NO BACKFILL — first claims accrue from SHIP_DATE.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────────────
SHIP_DATE = "2026-07-09"

QLEDGER_DESK   = "basket_turn.v1"
QLEDGER_FAMILY = "basket_turn.v1"

# Path to the turn-watch ledger (written by engine/basket_turn_watch.py)
_TURN_WATCH_LEDGER_DIR  = "basket_turn"
_TURN_WATCH_LEDGER_FILE = "ledger.jsonl"

# Path for the cohort claims state log (kept for ops visibility, NOT the claims store)
_COHORT_LOG_DIR  = "basket_turn"
_COHORT_LOG_FILE = "cohort_claims_log.jsonl"

# ── house laws ─────────────────────────────────────────────────────────────────
AUTHORITY = {
    "tier":          "display",
    "horizon_role":  "context",
    "may_rank":      False,
    "may_gate":      False,
    "may_size":      False,
    "may_escalate":  False,
}

REGISTRATION_NOTE = (
    "Sector-level standalone washout→turn construction printed NULL "
    "(Oracle P8 P-W1/S-W3; DO_NOT_REBUILD 'Washout × turn'). "
    "This K-of-N confluence family tests whether basket-granularity multi-leg "
    "confluence differs. Expected-NULL forward meter: claims accrue from ship "
    "date (2026-07-09), no backfill. "
    "Promotion question earliest 2027, n≥8 distinct shock episodes (PS-R8)."
)

# ── COLLECT_LANE gate ──────────────────────────────────────────────────────────

def _ledger_advance_enabled() -> bool:
    """True only when running in the nightly engine lane (FT-R5)."""
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"


# ── ledger helpers ─────────────────────────────────────────────────────────────

def _turn_watch_ledger_path(data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else config.data_dir()
    return root / _TURN_WATCH_LEDGER_DIR / _TURN_WATCH_LEDGER_FILE


def _cohort_log_path(data_root: Path | None = None) -> Path:
    root = data_root if data_root is not None else config.data_dir()
    p = root / _COHORT_LOG_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p / _COHORT_LOG_FILE


def load_turn_watch_ledger(data_root: Path | None = None) -> list[dict]:
    """Load all rows from data/basket_turn/ledger.jsonl."""
    p = _turn_watch_ledger_path(data_root)
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


def _load_cohort_log(data_root: Path | None = None) -> set[str]:
    """Return set of cohort_ids already registered (keep-first guard)."""
    p = _cohort_log_path(data_root)
    seen: set[str] = set()
    if not p.exists():
        return seen
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            cid = row.get("cohort_id")
            if cid:
                seen.add(cid)
        except json.JSONDecodeError:
            continue
    return seen


# ── cohort formation ───────────────────────────────────────────────────────────

def form_cohorts(
    ledger_rows: list[dict],
    ship_date: str = SHIP_DATE,
) -> list[dict]:
    """Group IGNITION-state ledger rows by date to form cohorts.

    Rules (FT-R9):
    - Only IGNITION rows form claims (WATCH rows are excluded).
    - All baskets with state=IGNITION on the same session form ONE cohort.
    - No backfill: dates before SHIP_DATE are excluded.
    - Returns list of cohort dicts sorted by cohort_date ascending.

    Each cohort dict:
        cohort_id   : str — ISO date string (the cohort key, also claim scope_key)
        cohort_date : str — ISO date
        basket_ids  : list[str] — all IGNITION baskets that fired on this date
        n_baskets   : int
        legs        : dict[basket_id -> legs dict] — constituent leg evidence
    """
    ship_ts = pd.Timestamp(ship_date).date()
    by_date: dict[str, list[dict]] = {}

    for row in ledger_rows:
        state = row.get("state")
        if state != "IGNITION":
            continue
        dt = row.get("date") or row.get("as_of")
        if not dt:
            continue
        try:
            row_date = date.fromisoformat(str(dt))
        except ValueError:
            continue
        if row_date < ship_ts:
            continue
        by_date.setdefault(str(dt), []).append(row)

    cohorts: list[dict] = []
    for dt_str in sorted(by_date):
        rows_on_day = by_date[dt_str]
        basket_ids = [r.get("basket_id") for r in rows_on_day if r.get("basket_id")]
        legs_map = {
            r.get("basket_id"): r.get("legs", {})
            for r in rows_on_day
            if r.get("basket_id")
        }
        cohorts.append({
            "cohort_id":   dt_str,
            "cohort_date": dt_str,
            "basket_ids":  sorted(basket_ids),
            "n_baskets":   len(basket_ids),
            "legs":        legs_map,
        })
    return cohorts


# ── qledger registration ───────────────────────────────────────────────────────

def register_cohort_claims(
    cohorts: list[dict],
    data_root: Path | None = None,
) -> list[dict]:
    """Register one qledger claim per IGNITION-day cohort (keep-first).

    Only cohorts with cohort_date >= SHIP_DATE are registered (enforced in
    form_cohorts, double-checked here).  Returns list of newly registered
    claim dicts (empty list when COLLECT_LANE gate is not set or no new cohorts).

    Claim design:
      desk/family    : basket_turn.v1
      scope_type     : basket
      scope_key      : cohort_date (ISO string — one claim per cohort-day)
      direction      : +1 (cohort EW > SPY at 21d)
      horizon_d      : 21
      bench          : SPY
      timestamp_quality : CRAWL_BOUNDED
      extra          : basket_ids, n_baskets, registration_note
    """
    if not _ledger_advance_enabled():
        log.debug("basket_turn_cohort: COLLECT_LANE gate not set — skipping claim registration")
        return []

    if not cohorts:
        return []

    from engine import qledger as q

    ship_ts = date.fromisoformat(SHIP_DATE)
    existing_cohort_ids = _load_cohort_log(data_root)

    claims_to_register: list[dict] = []
    new_cohort_ids: list[str] = []

    for cohort in cohorts:
        cid = cohort.get("cohort_id")
        if not cid:
            continue
        # No backfill guard (double-check)
        try:
            cdate = date.fromisoformat(cid)
        except ValueError:
            continue
        if cdate < ship_ts:
            continue
        # Keep-first
        if cid in existing_cohort_ids:
            continue

        extra: dict[str, Any] = {
            "cohort_id":         cid,
            "basket_ids":        cohort.get("basket_ids", []),
            "n_baskets":         cohort.get("n_baskets", 0),
            "registration_note": REGISTRATION_NOTE,
            "authority":         AUTHORITY,
            "horizon_role":      "21d_excess_vs_spy",
            "grading_note": (
                "Subject is equal-weight composite of IGNITION-day basket members; "
                "not a single priceable ticker.  Standard qledger chassis will not "
                "auto-grade this claim.  Dedicated analysis pass at 2026-10-15 clock "
                "grades cohort EW returns directly from price store."
            ),
        }

        claim = q.make_claim(
            desk=QLEDGER_DESK,
            asof=cid,
            scope_type="basket",
            scope_key=cid,
            direction=1,      # +1: cohort EW return > SPY over 21d
            horizon_d=21,
            timestamp_quality="CRAWL_BOUNDED",
            bench="SPY",
            claim_family=QLEDGER_FAMILY,
            extra=extra,
        )
        claims_to_register.append(claim)
        new_cohort_ids.append(cid)

    if not claims_to_register:
        return []

    registered = q.register_batch(claims_to_register, root=data_root, dedupe=True)

    # Append cohort log for keep-first bookkeeping
    log_path = _cohort_log_path(data_root)
    with log_path.open("a", encoding="utf-8") as fh:
        for cid in new_cohort_ids:
            fh.write(json.dumps({"cohort_id": cid, "registered": True}) + "\n")

    n_open = sum(1 for r in registered if r.get("status") == "open")
    log.info(
        "basket_turn_cohort: %d cohorts processed → %d new qledger claims (open)",
        len(new_cohort_ids), n_open,
    )
    return registered


# ── nightly entry point ────────────────────────────────────────────────────────

def nightly_run(data_root: Path | None = None) -> dict[str, Any]:
    """Nightly build step: read turn-watch ledger, form cohorts, register claims.

    Gated on COLLECT_LANE=nightly (FT-R5).  Exit-0-always: any error is
    captured, a ::warning:: is emitted, and the summary dict carries ok=False.

    Returns summary dict for the build log.
    """
    try:
        ledger_rows = load_turn_watch_ledger(data_root)
        if not ledger_rows:
            log.info("basket_turn_cohort: turn-watch ledger empty or absent — no claims to register")
            return {"ok": True, "n_ledger_rows": 0, "n_cohorts": 0, "n_claims_registered": 0}

        ignition_rows = [r for r in ledger_rows if r.get("state") == "IGNITION"]
        log.info(
            "basket_turn_cohort: ledger has %d rows, %d IGNITION",
            len(ledger_rows), len(ignition_rows),
        )

        cohorts = form_cohorts(ledger_rows)
        log.info("basket_turn_cohort: formed %d cohort(s)", len(cohorts))

        if not _ledger_advance_enabled():
            log.info("basket_turn_cohort: COLLECT_LANE gate not set — cohort formation ran but no claims registered (nightly-only)")
            return {
                "ok": True,
                "n_ledger_rows": len(ledger_rows),
                "n_cohorts": len(cohorts),
                "n_claims_registered": 0,
                "gate_skipped": True,
            }

        registered = register_cohort_claims(cohorts, data_root=data_root)
        n_registered = len([r for r in registered if r.get("status") == "open"])

        return {
            "ok": True,
            "n_ledger_rows": len(ledger_rows),
            "n_ignition_rows": len(ignition_rows),
            "n_cohorts": len(cohorts),
            "n_claims_registered": n_registered,
        }
    except Exception as exc:  # noqa: BLE001 — exit-0-always
        import sys
        print(f"::warning::basket_turn_cohort.nightly_run failed: {exc}", file=sys.stderr)
        log.warning("basket_turn_cohort.nightly_run failed: %s", exc)
        return {"ok": False, "error": str(exc)}
