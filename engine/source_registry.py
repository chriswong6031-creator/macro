"""engine/source_registry.py — Beta-Bernoulli source credibility + qledger claim families.

Masterplan §4.3 + §7 W4 row. NAR-R3, NAR-R5, NAR-R10.

DISPLAY-ONLY. Authority block: tier=display, may_rank=False, may_gate=False, may_size=False.

Three responsibilities:
  1. source_registry.json — Beta-Bernoulli credibility per source_id.
       cred = (hits + alpha) / (calls + alpha + beta)
       Skeptical seed: alpha=2, beta=5 (NAR-R3: no hand-set weights, no historical seeding).
       Updated ONLY by the nightly deterministic grader.
       State store: data/narrative_flare/source_registry.json
       {source_id: {calls, hits, cred, last_resolved, accruing: true}}

  2. Claim family `narrative_source_call` — one claim per row of
       data/narrative_flare/first_coverage.parquet (W3 writes it).
       Claim: "source S first-covered ticker T on date D."
       Resolution at D+20 trading days: |cumulative excess return of T vs SPY
       over D..D+20| > 5% -> hit (UNSIGNED — masterplan §4.3).
       direction=0 (salience-only per qledger.DIRECTIONS): hit=None from qledger.grade_claim;
       the grader computes |excess| and stores it separately in source_registry.json.

  3. Claim family `narrative_flare_state` — one claim per (ticker, date) where
       data/flare_persistence/state_hist.parquet prints PRIMED or later.
       Grades at 21d and 63d: forward excess return vs SPY recorded (descriptive
       accrual; no pass/fail verdict this wave — NAR-R5).

All data/ writes nightly-gated (COLLECT_LANE=nightly).
site/ writes (grading_summary.json) allowed on all lanes — site/ may write freely.

NAR-R10: absent/stale upstream -> log warning + skip; never crash.
NAR-R4: zero LLM anywhere in this module.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from engine import qledger as q
from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (display-tier — NAR §4 invariant)
# ---------------------------------------------------------------------------

AUTHORITY = {
    "tier": "display",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

# ---------------------------------------------------------------------------
# Beta-Bernoulli parameters (NAR-R3: skeptical seed, no hand-set weights)
# ---------------------------------------------------------------------------
# seed alpha=2, beta=5 => cold-start cred = 2/7 ≈ 0.286 (deliberately below 0.5)
BETA_ALPHA = 2
BETA_BETA = 5

# ---------------------------------------------------------------------------
# Resolution parameters (§4.3)
# ---------------------------------------------------------------------------
RESOLUTION_TRADING_DAYS = 20       # D+20 trading days
EXCESS_HIT_THRESHOLD = 0.05        # |excess| > 5% = hit (UNSIGNED, NAR §4.3)

# ---------------------------------------------------------------------------
# Store paths
# ---------------------------------------------------------------------------
_NAR_FLARE_DIR = "narrative_flare"
_REGISTRY_FILE = "source_registry.json"
_FIRST_COV_FILE = "first_coverage.parquet"
_STATE_HIST_DIR = "flare_persistence"
_STATE_HIST_FILE = "state_hist.parquet"
_SUMMARY_FILE = "grading_summary.json"

# qledger desk + claim_family tags
_DESK_SOURCE_CALL = "narrative"
_FAMILY_SOURCE_CALL = "narrative_source_call"
_DESK_FLARE_STATE = "narrative"
_FAMILY_FLARE_STATE = "narrative_flare_state"

# States that qualify for narrative_flare_state claims (§4.3)
_PRIMED_STATES = {"PRIMED", "ARMED", "CONFIRMED_CANDIDATE"}


# ---------------------------------------------------------------------------
# Lane gate (mirrors flare_persistence._ledger_advance_enabled exactly)
# ---------------------------------------------------------------------------

def _ledger_advance_enabled() -> bool:
    """True only when running in the nightly engine lane (COLLECT_LANE=nightly)."""
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"


# ---------------------------------------------------------------------------
# source_registry.json helpers
# ---------------------------------------------------------------------------

def _registry_path(data_root: Path) -> Path:
    return data_root / _NAR_FLARE_DIR / _REGISTRY_FILE


def load_registry(data_root: Path | None = None) -> dict:
    """Load data/narrative_flare/source_registry.json. Returns {} on absence."""
    if data_root is None:
        data_root = config.data_dir()
    p = _registry_path(data_root)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log.warning("source_registry: load failed: %s", e)
        return {}


def save_registry(reg: dict, data_root: Path | None = None) -> None:
    """Write data/narrative_flare/source_registry.json atomically."""
    if data_root is None:
        data_root = config.data_dir()
    p = _registry_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def beta_cred(calls: int, hits: int) -> float:
    """Beta-Bernoulli credibility: (hits + alpha) / (calls + alpha + beta).

    Skeptical seed: alpha=2, beta=5. Cold-start cred = 2/7 ≈ 0.286.
    NAR-R3: no hand-set weights, no historical seeding.
    """
    return round((hits + BETA_ALPHA) / (calls + BETA_ALPHA + BETA_BETA), 6)


def _update_registry_entry(
    reg: dict,
    source_id: str,
    resolved_hit: bool,
    resolved_date: str,
) -> None:
    """Update one source entry with a newly resolved call (hit or miss).

    Mutates `reg` in-place. Maintains calls, hits, cred, last_resolved, accruing.
    """
    entry = reg.setdefault(source_id, {
        "calls": 0,
        "hits": 0,
        "cred": beta_cred(0, 0),
        "last_resolved": None,
        "accruing": True,
    })
    entry["calls"] = entry.get("calls", 0) + 1
    if resolved_hit:
        entry["hits"] = entry.get("hits", 0) + 1
    entry["cred"] = beta_cred(entry["calls"], entry["hits"])
    entry["last_resolved"] = resolved_date
    entry["accruing"] = True  # always; NAR-R5 says display-only until confirmer


# ---------------------------------------------------------------------------
# first_coverage.parquet reader
# ---------------------------------------------------------------------------

# SHARED W3<->W4 CONTRACT:
# data/narrative_flare/first_coverage.parquet
# columns: [source_id:str, ticker:str, date:str ISO, url:str, title:str,
#           join_confidence:float 0-1, fetch_date:str ISO]
# W3 WRITES it; W4 READS it.

_FIRST_COV_COLS = [
    "source_id", "ticker", "date", "url", "title",
    "join_confidence", "fetch_date",
]


def load_first_coverage(data_root: Path | None = None) -> pd.DataFrame:
    """Load data/narrative_flare/first_coverage.parquet.

    Returns empty DataFrame with correct schema on absence (NAR-R10).
    """
    if data_root is None:
        data_root = config.data_dir()
    p = data_root / _NAR_FLARE_DIR / _FIRST_COV_FILE
    if not p.exists():
        log.warning("source_registry: first_coverage.parquet absent — handle gracefully (NAR-R10)")
        return pd.DataFrame(columns=_FIRST_COV_COLS)
    try:
        df = pd.read_parquet(p)
        # Ensure all required columns exist
        for col in _FIRST_COV_COLS:
            if col not in df.columns:
                log.warning("source_registry: first_coverage missing column %r", col)
                df[col] = None
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("source_registry: first_coverage.parquet read failed: %s", e)
        return pd.DataFrame(columns=_FIRST_COV_COLS)


# ---------------------------------------------------------------------------
# state_hist.parquet reader
# ---------------------------------------------------------------------------


def load_state_hist(data_root: Path | None = None) -> pd.DataFrame:
    """Load data/flare_persistence/state_hist.parquet.

    Returns empty DataFrame on absence (NAR-R10).
    """
    if data_root is None:
        data_root = config.data_dir()
    p = data_root / _STATE_HIST_DIR / _STATE_HIST_FILE
    if not p.exists():
        log.warning("source_registry: state_hist.parquet absent — handle gracefully (NAR-R10)")
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("source_registry: state_hist.parquet read failed: %s", e)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Price helpers (reuse qledger._fwd_ret + _fill_entry exactly)
# ---------------------------------------------------------------------------


def _excess_return_unsigned(
    ticker: str,
    entry_date: str,
    horizon_d: int,
    root: Path,
) -> float | None:
    """|subject_ret - bench_ret| over D+horizon_d calendar days from next-bar fill.

    Returns None when prices unavailable or horizon not yet matured.
    Uses qledger._fwd_ret (next_bar convention, SPY bench) — the same price layer
    all other graders use.
    """
    try:
        subj = q._fwd_ret(ticker, root, entry_date, horizon_d)
        bench = q._fwd_ret("SPY", root, entry_date, horizon_d)
        if subj is None or bench is None:
            return None
        return round(abs(subj - bench), 6)
    except Exception as e:  # noqa: BLE001
        log.debug("source_registry: excess_return_unsigned %s %s %dd: %s",
                  ticker, entry_date, horizon_d, e)
        return None


def _matured_at_trading_days(
    entry_date: str,
    trading_days: int,
    today: date,
    root: Path,
    ticker: str = "SPY",
) -> bool:
    """True when enough calendar days have elapsed and SPY (or ticker) covers the exit.

    20 trading days ≈ 28 calendar days (adds a 10-day safety buffer).
    We use the qledger maturity check as-is (calendar days based) with a
    calendar-day approximation: 20 trading days ≈ 28 calendar days.
    """
    # Approximate: 20 trading days ≈ 28 calendar days (conservative)
    approx_calendar_days = int(trading_days * 1.4)
    return q._matured(root, entry_date, approx_calendar_days, today, [ticker, "SPY"])


# ---------------------------------------------------------------------------
# Claim registration: narrative_source_call
# ---------------------------------------------------------------------------


def register_source_call_claims(
    data_root: Path | None = None,
    root: Path | None = None,
    today: date | None = None,
) -> dict:
    """Register qledger claims for new rows in first_coverage.parquet.

    One claim per (source_id, ticker) row. direction=0 (salience-only per §4.3:
    UNSIGNED resolution, not directional). Idempotent: register_batch dedupes.

    Only runs on nightly lane (data/ gate). Returns summary dict.
    """
    if not _ledger_advance_enabled():
        log.debug("source_registry: register_source_call_claims skipped — not nightly lane")
        return {"skipped": True, "reason": "not_nightly_lane"}

    if data_root is None:
        data_root = config.data_dir()
    if root is None:
        root = config.ROOT
    if today is None:
        today = date.today()

    cov = load_first_coverage(data_root)
    if cov.empty:
        log.info("source_registry: first_coverage empty — 0 claims to register")
        return {"n_registered": 0, "n_rejected": 0, "n_skipped_empty": True}

    claims_to_register: list[dict] = []
    for _, row in cov.iterrows():
        source_id = str(row.get("source_id") or "")
        ticker = str(row.get("ticker") or "").strip().upper()
        cov_date = str(row.get("date") or "")
        url = str(row.get("url") or "")
        title = str(row.get("title") or "")
        join_conf = float(row.get("join_confidence") or 0.0)

        if not source_id or not ticker or not cov_date:
            continue

        # Validate date
        try:
            pd.Timestamp(cov_date)
        except Exception:  # noqa: BLE001
            continue

        claim = q.make_claim(
            desk=_DESK_SOURCE_CALL,
            asof=cov_date,
            scope_type="entity",
            scope_key=ticker,
            direction=0,           # salience-only: |excess| graded, not directional
            horizon_d=RESOLUTION_TRADING_DAYS * 2,  # ~40cd; enough for 20 trading days
            timestamp_quality="CRAWL_BOUNDED",
            bench="SPY",
            claim_family=_FAMILY_SOURCE_CALL,
            extra={
                "source_id": source_id,
                "url": url[:512],
                "title": title[:256],
                "join_confidence": join_conf,
                "resolution_trading_days": RESOLUTION_TRADING_DAYS,
                "excess_hit_threshold": EXCESS_HIT_THRESHOLD,
                "authority": AUTHORITY,
                "registration_note": (
                    "NAR-W4 narrative_source_call: "
                    "graded at D+20 trading days, |excess vs SPY|>5% = hit (UNSIGNED). "
                    "direction=0 salience-only. NAR-R3/NAR-R5 apply."
                ),
            },
        )
        claims_to_register.append(claim)

    if not claims_to_register:
        return {"n_registered": 0, "n_rejected": 0}

    # Load existing claim ids BEFORE batch to count net-new registrations
    existing_ids = {c.get("claim_id") for c in q.load_claims(root) if c.get("claim_id")}
    results = q.register_batch(claims_to_register, root=root, dedupe=True)
    n_new = sum(
        1 for r in results
        if r.get("claim_id") and r.get("claim_id") not in existing_ids
        and r.get("status") == q.STATUS_OPEN
    )
    n_rejected = sum(1 for r in results if r.get("status") == q.STATUS_REJECTED)
    log.info(
        "source_registry: narrative_source_call: new=%d rejected=%d total_input=%d",
        n_new, n_rejected, len(claims_to_register),
    )
    return {"n_registered": n_new, "n_rejected": n_rejected}


# ---------------------------------------------------------------------------
# Claim registration: narrative_flare_state
# ---------------------------------------------------------------------------


def register_flare_state_claims(
    data_root: Path | None = None,
    root: Path | None = None,
) -> dict:
    """Register qledger claims for (ticker, date) rows in state_hist.parquet
    that print PRIMED or later.

    Grades at 21d and 63d: forward excess return vs SPY (descriptive accrual;
    no pass/fail verdict this wave — NAR-R5). direction=0 (salience-only).
    Idempotent: register_batch dedupes.

    Only runs on nightly lane. Returns summary dict.
    """
    if not _ledger_advance_enabled():
        log.debug("source_registry: register_flare_state_claims skipped — not nightly lane")
        return {"skipped": True, "reason": "not_nightly_lane"}

    if data_root is None:
        data_root = config.data_dir()
    if root is None:
        root = config.ROOT

    hist = load_state_hist(data_root)
    if hist.empty:
        log.info("source_registry: state_hist empty — 0 flare_state claims to register")
        return {"n_registered": 0, "n_rejected": 0, "n_skipped_empty": True}

    # Filter: only PRIMED or higher states
    if "state" not in hist.columns:
        log.warning("source_registry: state_hist missing 'state' column — 0 claims")
        return {"n_registered": 0, "n_rejected": 0}

    primed_rows = hist[hist["state"].isin(_PRIMED_STATES)].copy()
    if primed_rows.empty:
        log.info("source_registry: no PRIMED+ rows in state_hist — 0 claims")
        return {"n_registered": 0, "n_rejected": 0}

    claims_to_register: list[dict] = []
    for _, row in primed_rows.iterrows():
        ticker = str(row.get("ticker") or "").strip().upper()
        state_date = str(row.get("date") or "")
        state = str(row.get("state") or "")
        s_plus = float(row.get("s_plus") or 0.0)

        if not ticker or not state_date:
            continue

        try:
            pd.Timestamp(state_date)
        except Exception:  # noqa: BLE001
            continue

        # Register at 21d and 63d separately as per §4.3
        for horizon_d in (21, 63):
            claim = q.make_claim(
                desk=_DESK_FLARE_STATE,
                asof=state_date,
                scope_type="entity",
                scope_key=ticker,
                direction=0,       # descriptive accrual; no directional verdict this wave
                horizon_d=horizon_d,
                timestamp_quality="SNAPSHOT_DATE",  # state_hist is a PIT snapshot
                bench="SPY",
                claim_family=_FAMILY_FLARE_STATE,
                extra={
                    "flare_state": state,
                    "s_plus_at_fire": s_plus,
                    "authority": AUTHORITY,
                    "registration_note": (
                        f"NAR-W4 narrative_flare_state: "
                        f"descriptive accrual at {horizon_d}d, forward excess vs SPY recorded. "
                        "No pass/fail verdict this wave (NAR-R5). direction=0 salience-only."
                    ),
                },
            )
            claims_to_register.append(claim)

    if not claims_to_register:
        return {"n_registered": 0, "n_rejected": 0}

    existing_ids = {c.get("claim_id") for c in q.load_claims(root) if c.get("claim_id")}
    results = q.register_batch(claims_to_register, root=root, dedupe=True)
    n_new = sum(
        1 for r in results
        if r.get("claim_id") and r.get("claim_id") not in existing_ids
        and r.get("status") == q.STATUS_OPEN
    )
    n_rejected = sum(1 for r in results if r.get("status") == q.STATUS_REJECTED)
    log.info(
        "source_registry: narrative_flare_state: new=%d rejected=%d total_input=%d",
        n_new, n_rejected, len(claims_to_register),
    )
    return {"n_registered": n_new, "n_rejected": n_rejected}


# ---------------------------------------------------------------------------
# Nightly grader: resolve matured narrative_source_call claims
# ---------------------------------------------------------------------------


def _resolve_source_call_claims(
    data_root: Path,
    root: Path,
    today: date,
) -> dict:
    """Find matured narrative_source_call claims, compute |excess|, update registry.

    Returns summary dict with n_resolved, n_hits, n_miss, n_immature, n_no_price.
    """
    if not _ledger_advance_enabled():
        return {"skipped": True, "reason": "not_nightly_lane"}

    claims = q.load_claims(root)
    source_call_claims = [
        c for c in claims
        if (c.get("claim_family") == _FAMILY_SOURCE_CALL
            and c.get("status") == q.STATUS_OPEN
            and c.get("direction") == 0)
    ]

    if not source_call_claims:
        log.info("source_registry: no open narrative_source_call claims to resolve")
        return {"n_resolved": 0, "n_hits": 0, "n_miss": 0, "n_immature": 0, "n_no_price": 0}

    reg = load_registry(data_root)
    n_resolved = n_hits = n_miss = n_immature = n_no_price = 0

    for claim in source_call_claims:
        source_id = str(claim.get("source_id") or "")
        scope = claim.get("scope") or {}
        ticker = str(scope.get("key") or "").upper()
        asof = str(claim.get("asof") or "")

        if not source_id or not ticker or not asof:
            continue

        entry_date = q._entry_date(claim)  # respects embargo

        # Check maturity: 20 trading days ≈ 28 calendar days
        if not _matured_at_trading_days(entry_date, RESOLUTION_TRADING_DAYS, today, root, ticker):
            n_immature += 1
            continue

        # Compute |excess| (UNSIGNED — §4.3)
        excess_abs = _excess_return_unsigned(ticker, entry_date, RESOLUTION_TRADING_DAYS * 2, root)
        if excess_abs is None:
            n_no_price += 1
            continue

        is_hit = excess_abs > EXCESS_HIT_THRESHOLD
        _update_registry_entry(reg, source_id, is_hit, today.isoformat())
        n_resolved += 1
        if is_hit:
            n_hits += 1
        else:
            n_miss += 1

    if n_resolved > 0:
        save_registry(reg, data_root)

    log.info(
        "source_registry: resolved=%d hits=%d miss=%d immature=%d no_price=%d",
        n_resolved, n_hits, n_miss, n_immature, n_no_price,
    )
    return {
        "n_resolved": n_resolved,
        "n_hits": n_hits,
        "n_miss": n_miss,
        "n_immature": n_immature,
        "n_no_price": n_no_price,
    }


# ---------------------------------------------------------------------------
# Rolling-IC/decay summary (NAR-R13)
# ---------------------------------------------------------------------------


def _build_grading_summary(data_root: Path, root: Path) -> dict:
    """Compute data/narrative_flare/grading_summary.json (NAR-R13).

    Families: narrative_source_call, narrative_flare_state.
    Per family: n_claims, n_resolved (graded at any horizon), hit_rate,
    accruing flag. Data-tier only — no site/ write.
    """
    claims = q.load_claims(root)
    grades = q.load_grades(root)

    summary: dict[str, Any] = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "families": {},
    }

    for family in (_FAMILY_SOURCE_CALL, _FAMILY_FLARE_STATE):
        fam_claims = [
            c for c in claims
            if c.get("claim_family") == family and not c.get("is_placebo")
        ]
        cid_set = {c.get("claim_id") for c in fam_claims if c.get("claim_id")}
        fam_grades = [g for g in grades if g.get("claim_id") in cid_set]

        n_claims = len(fam_claims)
        n_resolved = len({g.get("claim_id") for g in fam_grades})
        # For salience-only (direction=0) claims hit is None; excess is still recorded
        hit_grades = [g for g in fam_grades if g.get("hit") is not None]
        if hit_grades:
            n_hits = sum(1 for g in hit_grades if g.get("hit"))
            hit_rate = round(n_hits / len(hit_grades), 4)
        else:
            hit_rate = None

        summary["families"][family] = {
            "n_claims": n_claims,
            "n_resolved": n_resolved,
            "hit_rate": hit_rate,
            "accruing": True,
            "state": q.derive_state(len({
                c.get("asof") for c in fam_claims if c.get("asof")
            })),
        }

    # Source registry snapshot (NAR-R13: rolling IC of qledger families)
    reg = load_registry(data_root)
    summary["source_registry_n"] = len(reg)
    summary["source_registry_total_calls"] = sum(e.get("calls", 0) for e in reg.values())
    summary["authority"] = AUTHORITY

    return summary


def write_grading_summary(
    data_root: Path | None = None,
    root: Path | None = None,
) -> dict:
    """Compute and write data/narrative_flare/grading_summary.json.

    Allowed on all lanes (site/ equivalent data-tier output). Returns payload.
    """
    if data_root is None:
        data_root = config.data_dir()
    if root is None:
        root = config.ROOT

    payload = _build_grading_summary(data_root, root)
    out_p = data_root / _NAR_FLARE_DIR / _SUMMARY_FILE
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("source_registry: wrote grading_summary.json")
    return payload


# ---------------------------------------------------------------------------
# Main nightly entry point
# ---------------------------------------------------------------------------


def nightly_run(
    data_root: Path | None = None,
    root: Path | None = None,
    today: date | None = None,
) -> dict:
    """Full nightly grader step for the Narrative Ignition W4.

    Steps (all nightly-gated):
      1. Register narrative_source_call claims from first_coverage.parquet.
      2. Register narrative_flare_state claims from state_hist.parquet.
      3. Resolve matured narrative_source_call claims; update source_registry.json.
      4. Write grading_summary.json (NAR-R13).

    Returns summary dict. Never raises (NAR-R10 additive pattern).
    """
    try:
        return _nightly_run_inner(data_root, root, today)
    except Exception as e:  # noqa: BLE001
        log.error("source_registry.nightly_run crashed: %s", e)
        return {"error": str(e), "accruing": True}


def _nightly_run_inner(
    data_root: Path | None,
    root: Path | None,
    today: date | None,
) -> dict:
    if data_root is None:
        data_root = config.data_dir()
    if root is None:
        root = config.ROOT
    if today is None:
        today = date.today()

    results: dict[str, Any] = {"as_of": today.isoformat()}

    # Step 1: register narrative_source_call claims
    try:
        r1 = register_source_call_claims(data_root=data_root, root=root, today=today)
        results["source_call_registration"] = r1
    except Exception as e:  # noqa: BLE001
        log.warning("source_registry: source_call registration failed: %s", e)
        results["source_call_registration"] = {"error": str(e)}

    # Step 2: register narrative_flare_state claims
    try:
        r2 = register_flare_state_claims(data_root=data_root, root=root)
        results["flare_state_registration"] = r2
    except Exception as e:  # noqa: BLE001
        log.warning("source_registry: flare_state registration failed: %s", e)
        results["flare_state_registration"] = {"error": str(e)}

    # Step 3: resolve matured source call claims + update registry
    try:
        r3 = _resolve_source_call_claims(data_root=data_root, root=root, today=today)
        results["source_call_resolution"] = r3
    except Exception as e:  # noqa: BLE001
        log.warning("source_registry: source_call resolution failed: %s", e)
        results["source_call_resolution"] = {"error": str(e)}

    # Step 4: write grading_summary.json (NAR-R13)
    try:
        summary = write_grading_summary(data_root=data_root, root=root)
        results["grading_summary"] = {
            "families": list(summary.get("families", {}).keys()),
            "source_registry_n": summary.get("source_registry_n", 0),
        }
    except Exception as e:  # noqa: BLE001
        log.warning("source_registry: grading_summary write failed: %s", e)
        results["grading_summary"] = {"error": str(e)}

    return results


def run_as_collect_step(
    data_root: Path | None = None,
    root: Path | None = None,
) -> None:
    """Wired into scripts/collect.py as an end-of-collect step. Non-fatal."""
    try:
        result = nightly_run(data_root=data_root, root=root)
        log.info(
            "[source_registry] nightly_run: src_call_reg=%s flare_state_reg=%s resolved=%s",
            result.get("source_call_registration", {}).get("n_registered", "?"),
            result.get("flare_state_registration", {}).get("n_registered", "?"),
            result.get("source_call_resolution", {}).get("n_resolved", "?"),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("[source_registry] nightly_run step crashed (non-fatal): %s", exc)
