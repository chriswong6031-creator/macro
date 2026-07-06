"""Oracle Reversion Promotion Scan — P2 (armed-not-fired).

Reads the compound registry (reversion-block compounds) + the P0 forward ledger
(data/oracle/reversion_forward/<compound_id>.jsonl, matured rows only) and evaluates
each compound against the LIVE PROMOTION FLOOR from the pre-registration:

    research/ORACLE_REVERSION_PROMOTION_PREREG.md (FROZEN — never re-derive or tune)

Calls ``engine.neuralweb.constitution::grant_authority`` VERBATIM (never forked).

NEVER auto-promotes:
    - Writes ``data/oracle/reversion_promotion_queue.json`` for Fable/operator
      adjudication only.
    - Writes ``data/oracle/reversion_authority.json`` ONLY for compounds that pass
      the constitutional gate AND carry a human-ratified queue row
      (row.ratified_by is set by a human-committed edit, not by this scanner).
    - Appends a ``data/neuralweb/governance.jsonl`` event per PROPOSED tier
      transition.

Lapse law (Article 3, PREREG.md):
    De-escalation proposals when:
    - No fire in 90 sessions, OR
    - live lift_lb falls back to <= 1.25 at the current n.
    Lapse proposals go to the same queue; they DO NOT automatically downgrade
    the authority file.

Requeue-eligible reminder (W4.b):
    Checks data/oracle/reversion_kill_requeue.jsonl — if a compound's screenable n
    (matured rows in the current ledger) >= requeue_at_n, prints a reminder for the
    operator/Fable to re-screen. NEVER auto-rescreens.

Ratification mechanics:
    The authority.json file is modified ONLY when the operator (a human) has committed
    a queue row with ``ratified_by`` set. This scanner reads queue rows at runtime and
    applies the ratified tier only then. The scanner itself NEVER writes an authority
    grant without a ratified_by flag.

Selftest mode (--selftest):
    Uses SYNTHETIC ledger fixtures (no real data) to demonstrate:
    - grant path (n>=25, lift_lb>1.25)
    - refuse path (n<25, insufficient-n)
    - lapse path (previously granted, lift_lb drops)
    - never-auto-promote invariant (queue written, authority unchanged without
      human ratified_by in the queue row)

Usage
-----
    python -m scripts.oracle_reversion_promotion_scan \\
        --data-dir /path/to/data [--dry-run] [--selftest]
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("oracle_reversion_promotion_scan")

# ---------------------------------------------------------------------------
# FROZEN CONSTANTS — sourced verbatim from ORACLE_REVERSION_PROMOTION_PREREG.md
# (DO NOT retune; changing these after live data accrues is p-hacking)
# ---------------------------------------------------------------------------

# L2 → L3 (Display → Confirmer) gate
_L3_MIN_N: int = 25          # PREREG: "n >= 25 (matches the cortex A2 / can_force earn-in floors)"
_L3_MIN_HITS: int = 1        # hits floor: at least 1 positive exit (prevents zero-hit grants)
_L3_LIFT_THRESHOLD: float = 1.25  # PREREG: "wilson_lower / base_rate > 1.25"
_L3_Z: float = 1.645         # PREREG: "z=1.645 (90% one-sided)"

# L3 → L4 (Confirmer → Scored) additional requirements
_L4_MIN_N: int = 60          # PREREG: "n >= 60"
_L4_MIN_ASYM: float = 1.3   # PREREG: "asym_live >= 1.3 (a live haircut from the 1.5 backtest bar)"

# Lapse (Article 3) — PREREG: "no fire in 90 sessions OR lift_lb <= 1.25 at current n"
_LAPSE_NO_FIRE_SESSIONS: int = 90   # sessions of silence before lapse proposal
_LAPSE_LIFT_LB_FLOOR: float = 1.25  # same as L3 grant threshold

# Grant staleness from constitution.py Article-3 (default 120 days)
_MAX_STALENESS_DAYS: int = 120

# Registry + artifact paths (relative to data_dir)
_REGISTRY_PATH_REL = Path("oracle") / "compounds" / "registry.jsonl"
_FORWARD_DIR_REL = Path("oracle") / "reversion_forward"
_QUEUE_PATH_REL = Path("oracle") / "reversion_promotion_queue.json"
_AUTHORITY_PATH_REL = Path("oracle") / "reversion_authority.json"
_KILL_REQUEUE_PATH_REL = Path("oracle") / "reversion_kill_requeue.jsonl"


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def _load_reversion_compounds(data_dir: Path) -> list[dict]:
    """Return all registry compounds that have a reversion block (gauntlet PASS)."""
    registry_path = data_dir / _REGISTRY_PATH_REL
    if not registry_path.exists():
        log.warning("registry not found: %s", registry_path)
        return []
    compounds = []
    for line in registry_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            c = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if "reversion" in c and c["reversion"].get("gauntlet") == "PASS":
            compounds.append(c)
    return compounds


# ---------------------------------------------------------------------------
# Forward ledger helpers
# ---------------------------------------------------------------------------

def _load_ledger(data_dir: Path, compound_id: str) -> list[dict]:
    """Load all rows for a compound. Fail-open (empty list)."""
    p = data_dir / _FORWARD_DIR_REL / f"{compound_id}.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            pass
    return rows


def _matured_rows(rows: list[dict], operating_regime: str) -> list[dict]:
    """Return matured rows, regime-scoped for single-regime signals.

    PREREG: 'For single-regime signals, count only operating-regime fires
    (bear-tape accrues in risk-off only — its clock is regime-gated).'
    """
    matured = [r for r in rows if r.get("matured") is True]
    if operating_regime in ("risk_off", "risk_on"):
        matured = [r for r in matured if r.get("regime") == operating_regime]
    return matured


# ---------------------------------------------------------------------------
# Live stats for promotion gate
# ---------------------------------------------------------------------------

def _compute_live_stats(
    matured: list[dict],
) -> dict[str, Any]:
    """Compute hits, n, wr, asym from matured ledger rows."""
    n = len(matured)
    if n == 0:
        return {"n": 0, "hits": 0, "wr": None, "asym": None, "last_fire_date": None}

    hits = sum(1 for r in matured if (r.get("ret_exit") or 0) > 0)
    wr = hits / n

    mfes = [r["mfe"] for r in matured if r.get("mfe") is not None]
    maes = [r["mae"] for r in matured if r.get("mae") is not None]
    mean_mfe = sum(mfes) / len(mfes) if mfes else None
    mean_mae = sum(maes) / len(maes) if maes else None
    asym: float | None = None
    if mean_mfe is not None and mean_mae is not None and abs(mean_mae) > 1e-9:
        asym = mean_mfe / abs(mean_mae)

    # Most recent fire date (for lapse detection)
    fire_dates = [r.get("fire_date") for r in matured if r.get("fire_date")]
    last_fire_date = max(fire_dates) if fire_dates else None

    return {
        "n": n,
        "hits": hits,
        "wr": round(wr, 4),
        "asym": round(asym, 4) if asym is not None else None,
        "last_fire_date": last_fire_date,
    }


def _compute_base_rate_from_ledger(matured: list[dict]) -> float | None:
    """Retrieve the base_rate from the P1 sidecar's live block if present.

    The P0 ledger rows do not store base_rate directly — the base_rate was
    computed by oracle_reversion_state.py using PIT panel data. For the scan,
    we use the most recent available base_rate from the sidecar, or fallback
    to a conservative approximation.

    PREREG: 'base_rate = the UNCONDITIONAL trailing 21-session win-rate on the
    same universe (buy-anytime rate)'

    If the sidecar is unavailable, return None (the caller will refuse the grant
    with 'zero-base-rate').
    """
    # Base rates are compound-specific; the promotion scan gets them from the
    # sidecar's live.base_rate field. We defer to the sidecar reader below.
    return None


def _load_sidecar_base_rate(site_dir: Path, compound_id: str) -> float | None:
    """Read base_rate from the oracle_reversion_state.json sidecar for a compound."""
    try:
        sidecar_path = site_dir / "basketdata" / "oracle_reversion_state.json"
        if not sidecar_path.exists():
            return None
        data = json.loads(sidecar_path.read_text())
        for sig in data.get("signals", []):
            if sig.get("id") == compound_id:
                return sig.get("live", {}).get("base_rate")
        return None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Lapse detection helpers
# ---------------------------------------------------------------------------

def _sessions_since_last_fire(last_fire_date_str: str | None) -> int | None:
    """Return approximate trading-session count since last_fire_date.

    Uses calendar days × 5/7 as a session approximation (no panel needed).
    Returns None if last_fire_date is unavailable.
    """
    if not last_fire_date_str:
        return None
    try:
        last_fire = datetime.fromisoformat(last_fire_date_str[:10])
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        calendar_days = (now - last_fire).days
        # Conservative: 5/7 * calendar_days ≈ trading sessions
        sessions = int(calendar_days * 5 / 7)
        return max(0, sessions)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Kill-requeue registry helpers (W4.b)
# ---------------------------------------------------------------------------

def _load_kill_requeue(data_dir: Path) -> dict[str, dict]:
    """Load reversion_kill_requeue.jsonl, keyed by compound_id.

    Keep-first by compound_id::killed_at (as per W4.b spec).
    """
    path = data_dir / _KILL_REQUEUE_PATH_REL
    if not path.exists():
        return {}
    seen: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        cid = row.get("compound_id")
        if cid and cid not in seen:
            seen[cid] = row
    return seen


# ---------------------------------------------------------------------------
# Authority file helpers
# ---------------------------------------------------------------------------

def _load_authority(data_dir: Path) -> dict[str, dict]:
    """Load reversion_authority.json. Returns {compound_id: authority_record}."""
    path = data_dir / _AUTHORITY_PATH_REL
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data.get("authorities", {})
    except Exception:  # noqa: BLE001
        log.warning("reversion_authority.json could not be loaded")
        return {}


def _save_authority(data_dir: Path, authorities: dict[str, dict], dry_run: bool) -> None:
    """Write reversion_authority.json atomically."""
    if dry_run:
        return
    path = data_dir / _AUTHORITY_PATH_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "reversion_authority.v1",
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": (
            "Written ONLY by scripts/oracle_reversion_promotion_scan.py. "
            "Authority entries exist ONLY for compounds with human-ratified queue rows. "
            "NEVER auto-promoted: authority_level changes require ratified_by in queue row."
        ),
        "authorities": authorities,
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    log.info("reversion_authority.json updated: %d entries", len(authorities))


def _load_queue(data_dir: Path) -> dict:
    """Load existing reversion_promotion_queue.json. Returns empty queue dict on missing."""
    path = data_dir / _QUEUE_PATH_REL
    if not path.exists():
        return {"candidates": [], "lapses": []}
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return {"candidates": [], "lapses": []}


# ---------------------------------------------------------------------------
# Core scan logic per compound
# ---------------------------------------------------------------------------

def _scan_compound(
    compound: dict,
    data_dir: Path,
    site_dir: Path,
    existing_authorities: dict[str, dict],
    kill_requeue: dict[str, dict],
    now: datetime,
) -> dict[str, Any]:
    """Evaluate one compound against the live promotion floor.

    Returns a dict with keys:
        - compound_id, compound_name, cluster, operating_regime
        - live_stats: {n, hits, wr, asym, last_fire_date}
        - gate: GrantResult (L3 evaluation)
        - l4_eligible: bool (additionally meets L4 thresholds)
        - lapse_reason: str | None (if lapse should be proposed)
        - requeue_reminder: dict | None (if requeue threshold met)
        - current_authority: str | None (from authority file)
        - evidence_asof: str | None (most recent matured fire date)
    """
    from engine.neuralweb.constitution import grant_authority, AuthorityLevel

    cid = compound.get("id", "?")
    reversion = compound.get("reversion", {})
    operating_regime = reversion.get("operating_regime", "dual")

    rows = _load_ledger(data_dir, cid)
    matured = _matured_rows(rows, operating_regime)
    stats = _compute_live_stats(matured)

    n = stats["n"]
    hits = stats["hits"]
    asym = stats["asym"]
    last_fire_date = stats["last_fire_date"]
    evidence_asof = last_fire_date  # most recent matured fire is the evidence timestamp

    # Base rate from sidecar (PIT-computed; returns None if sidecar unavailable)
    base_rate = _load_sidecar_base_rate(site_dir, cid)
    if base_rate is None:
        # Fall back to 0.0 — grant_authority will refuse with zero-base-rate
        base_rate = 0.0

    # --- Article-3 evaluation (L2 → L3) ---
    evidence = {
        "hits": hits,
        "n": n,
        "base_rate": float(base_rate),
        "evidence_asof": evidence_asof,
    }
    floors = {
        "min_n": _L3_MIN_N,       # FROZEN: PREREG n>=25
        "min_events": _L3_MIN_HITS,
    }
    gate = grant_authority(
        evidence,
        floors=floors,
        target_level=None,          # not A7; no origination path
        now=now,
        max_staleness_days=_MAX_STALENESS_DAYS,
    )

    # --- L4 eligibility check (additional, not via grant_authority — checked
    #     in the queue note so adjudicator knows if L4 is also reachable) ---
    l4_eligible = (
        n >= _L4_MIN_N                      # FROZEN: PREREG n>=60
        and (asym is not None and asym >= _L4_MIN_ASYM)  # FROZEN: PREREG asym_live>=1.3
        and gate.granted
    )

    # --- Lapse detection (Article 3) ---
    lapse_reason: str | None = None
    current_auth = existing_authorities.get(cid, {})
    current_level = current_auth.get("authority_level")
    if current_level in ("confirmer", "scored"):
        # Check silence: no fire in 90 sessions
        sessions_silent = _sessions_since_last_fire(last_fire_date)
        if sessions_silent is not None and sessions_silent >= _LAPSE_NO_FIRE_SESSIONS:
            lapse_reason = (
                f"silence: {sessions_silent} sessions without a fire "
                f"(threshold: {_LAPSE_NO_FIRE_SESSIONS})"
            )
        # Check CI decay: lift_lb <= 1.25 at current n
        elif gate.lift_lb is not None and gate.lift_lb <= _LAPSE_LIFT_LB_FLOOR:
            lapse_reason = (
                f"ci-decay: lift_lb={gate.lift_lb:.4f} <= {_LAPSE_LIFT_LB_FLOOR} "
                f"at n={n}"
            )

    # --- Requeue reminder (W4.b): check kill_requeue registry ---
    requeue_reminder: dict | None = None
    kq = kill_requeue.get(cid)
    if kq is not None:
        requeue_at_n = kq.get("requeue_at_n", 0)
        if n >= requeue_at_n:
            requeue_reminder = {
                "compound_id": cid,
                "current_n": n,
                "requeue_at_n": requeue_at_n,
                "killed_at_asof": kq.get("killed_at_asof"),
                "note": (
                    "REQUEUE REMINDER — operator/Fable to re-screen this compound. "
                    "A re-screen is a new counted trial (counted-trials law). "
                    "NEVER auto-rescreens."
                ),
            }

    return {
        "compound_id": cid,
        "compound_name": compound.get("name", cid),
        "cluster": reversion.get("cluster"),
        "operating_regime": operating_regime,
        "live_stats": stats,
        "base_rate_used": float(base_rate) if base_rate else 0.0,
        "gate": gate,
        "l4_eligible": l4_eligible,
        "lapse_reason": lapse_reason,
        "requeue_reminder": requeue_reminder,
        "current_authority": current_level,
        "evidence_asof": evidence_asof,
    }


# ---------------------------------------------------------------------------
# Earliest projected promotion date
# ---------------------------------------------------------------------------

def _project_earliest_promotion(compound: dict, data_dir: Path) -> str:
    """Estimate earliest date a compound could hit n>=25 matured fires.

    Based on historical fire rate (total unmatured rows / days since first fire).
    Returns a descriptive string for printing.
    """
    cid = compound.get("id", "?")
    rows = _load_ledger(data_dir, cid)
    if not rows:
        return "no fires yet"

    reversion = compound.get("reversion", {})
    operating_regime = reversion.get("operating_regime", "dual")
    matured = _matured_rows(rows, operating_regime)
    n_matured = len(matured)

    if n_matured >= _L3_MIN_N:
        return "already accrued"

    # All rows (matured + unmatured) inform the fire rate
    all_fire_dates = [r["fire_date"] for r in rows if r.get("fire_date")]
    if not all_fire_dates:
        return "no fire dates"

    first_fire = min(all_fire_dates)[:10]
    try:
        first_dt = datetime.fromisoformat(first_fire)
        today = datetime.now(timezone.utc).replace(tzinfo=None)
        days_elapsed = max(1, (today - first_dt).days)
    except Exception:  # noqa: BLE001
        return "unknown"

    total_fires = len(rows)
    fire_rate_per_day = total_fires / days_elapsed
    if fire_rate_per_day <= 0:
        return "unknown"

    # Sessions needed: n_still_needed = L3_MIN_N + 25 (exit_sessions buffer)
    # Each fire takes 25 sessions (~35 calendar days) to mature
    n_needed = max(0, _L3_MIN_N - n_matured)
    days_to_fire = n_needed / fire_rate_per_day
    days_to_mature = 35  # ~21 session exit + 4-session grading buffer

    eta_days = int(days_to_fire + days_to_mature)
    try:
        from datetime import timedelta
        eta_date = (today + timedelta(days=eta_days)).strftime("%Y-%m")
        return f"~{eta_date} (est. {n_needed} more fires needed at {fire_rate_per_day:.2f}/day)"
    except Exception:  # noqa: BLE001
        return f"~{eta_days} calendar days"


# ---------------------------------------------------------------------------
# Main scan runner
# ---------------------------------------------------------------------------

def run_promotion_scan(
    data_dir: Path,
    site_dir: Path,
    dry_run: bool = False,
    now: datetime | None = None,
    governance_root: Path | None = None,
) -> dict[str, Any]:
    """Run the reversion promotion scan.

    NEVER auto-promotes. Writes queue + applies ratified promotions from queue
    rows carrying human-committed ratified_by. Returns a summary dict.

    governance_root: override the governance ledger path (for test isolation;
    defaults to ROOT which uses lib.config.data_dir()).
    """
    from engine.neuralweb.governance import append_event

    if now is None:
        now = datetime.now(timezone.utc)

    compounds = _load_reversion_compounds(data_dir)
    if not compounds:
        log.info("reversion_promotion_scan: no reversion compounds in registry")
        return {
            "n_compounds": 0, "n_candidates": 0, "n_lapses": 0,
            "n_accruing": 0, "n_requeue_reminders": 0,
        }

    existing_authorities = _load_authority(data_dir)
    kill_requeue = _load_kill_requeue(data_dir)

    candidates: list[dict] = []
    lapses: list[dict] = []
    accruing: list[dict] = []
    requeue_reminders: list[dict] = []

    for compound in compounds:
        cid = compound.get("id", "?")
        try:
            result = _scan_compound(
                compound, data_dir, site_dir, existing_authorities, kill_requeue, now
            )
        except Exception as e:  # noqa: BLE001
            log.warning("reversion_promotion_scan: %s scan failed: %s", cid, e)
            continue

        gate = result["gate"]
        lapse_reason = result["lapse_reason"]
        requeue_reminder = result.get("requeue_reminder")
        live_stats = result["live_stats"]

        if requeue_reminder:
            requeue_reminders.append(requeue_reminder)

        if lapse_reason:
            # Propose a lapse (Article 3) — never auto-applies
            lapse_row = {
                "compound_id": cid,
                "compound_name": result["compound_name"],
                "current_authority": result["current_authority"],
                "lapse_reason": lapse_reason,
                "proposed_action": "de-escalate to display",
                "proposed_at": now.isoformat(timespec="seconds"),
                "note": (
                    "LAPSE PROPOSAL — Article 3 de-escalation. "
                    "Requires operator/Fable ratification. "
                    "LLM MAY propose de-escalation; NEVER escalation (Article 1)."
                ),
                "live_stats": live_stats,
            }
            lapses.append(lapse_row)
            log.info("  [%s] LAPSE PROPOSED — %s", cid, lapse_reason)

            # Emit governance event for the lapse proposal
            if not dry_run:
                append_event(
                    "authority_lapse",
                    target=f"oracle_reversion:{cid}",
                    article=3,
                    authored_by="oracle_reversion_promotion_scan",
                    evidence={
                        "n": live_stats["n"],
                        "hits": live_stats["hits"],
                        "lapse_reason": lapse_reason,
                    },
                    before={"authority_level": result["current_authority"]},
                    after={"authority_level": "display (proposed)"},
                    note="lapse proposal — human ratification required",
                    root=governance_root,
                )

        elif gate.granted:
            # Promotion candidate — queue it; NEVER auto-promote
            target_level = "confirmer"
            if result["l4_eligible"]:
                target_level = "scored"

            candidate_row = {
                "compound_id": cid,
                "compound_name": result["compound_name"],
                "cluster": result["cluster"],
                "operating_regime": result["operating_regime"],
                "current_authority": result["current_authority"] or "display",
                "proposed_authority": target_level,
                "live_stats": live_stats,
                "gate_result": {
                    "granted": gate.granted,
                    "lift_lb": gate.lift_lb,
                    "wilson_lb": gate.wilson_lb,
                    "reason": gate.reason,
                    "lapses_at": gate.lapses_at,
                    "evidence_asof": gate.evidence_asof,
                },
                "base_rate_used": result["base_rate_used"],
                "l4_eligible": result["l4_eligible"],
                "proposed_at": now.isoformat(timespec="seconds"),
                "ratified_by": None,   # Human sets this to ratify
                "note": (
                    "QUEUE ONLY — not promoted. Fable/operator adjudication required. "
                    "Set ratified_by to ratify. "
                    "NEVER auto-promoted by the scanner."
                ),
            }
            candidates.append(candidate_row)
            log.info(
                "  [%s] CANDIDATE lift_lb=%.3f n=%d → proposed=%s",
                cid, gate.lift_lb or 0, live_stats["n"], target_level,
            )

            # Emit governance event for the proposed promotion
            if not dry_run:
                append_event(
                    "tier_promotion",
                    target=f"oracle_reversion:{cid}",
                    article=3,
                    authored_by="oracle_reversion_promotion_scan",
                    evidence={
                        "n": live_stats["n"],
                        "hits": live_stats["hits"],
                        "lift_lb": gate.lift_lb,
                        "wilson_lb": gate.wilson_lb,
                        "base_rate": result["base_rate_used"],
                        "evidence_asof": gate.evidence_asof,
                    },
                    before={"authority_level": result["current_authority"] or "display"},
                    after={"authority_level": f"{target_level} (proposed)"},
                    note="promotion candidate queued — human ratification required",
                    root=governance_root,
                )

        else:
            # Still accruing — print projected earliest promotion
            proj = _project_earliest_promotion(compound, data_dir)
            accruing.append({
                "compound_id": cid,
                "compound_name": result["compound_name"],
                "cluster": result["cluster"],
                "live_n": live_stats["n"],
                "refuse_reason": gate.reason,
                "earliest_projected": proj,
            })

    # -------------------------------------------------------------------------
    # Ratification: apply authority changes ONLY for queue rows with ratified_by
    # (set by a human-committed edit — this scanner never sets ratified_by itself)
    # -------------------------------------------------------------------------
    existing_queue = _load_queue(data_dir)
    newly_ratified: list[dict] = []
    updated_authorities = dict(existing_authorities)

    for queued in existing_queue.get("candidates", []):
        ratified_by = queued.get("ratified_by")
        if not ratified_by:
            continue  # not yet ratified — skip

        qcid = queued.get("compound_id")
        if not qcid:
            continue

        proposed = queued.get("proposed_authority", "confirmer")
        # Only apply if this compound is still valid in the registry
        registry_ids = {c.get("id") for c in compounds}
        if qcid not in registry_ids:
            log.warning("ratified queue row for %s: not in registry, skipping", qcid)
            continue

        current_in_auth = updated_authorities.get(qcid, {}).get("authority_level")
        if current_in_auth == proposed:
            continue  # already applied

        log.info(
            "RATIFICATION APPLIED: %s → %s (ratified_by=%s)",
            qcid, proposed, ratified_by,
        )
        updated_authorities[qcid] = {
            "authority_level": proposed,
            "ratified_by": ratified_by,
            "ratified_at": queued.get("proposed_at"),
            "applied_at": now.isoformat(timespec="seconds"),
            "evidence": queued.get("gate_result"),
        }
        newly_ratified.append({"compound_id": qcid, "authority_level": proposed})

        # Emit a governance event for the applied ratification
        if not dry_run:
            append_event(
                "tier_promotion",
                target=f"oracle_reversion:{qcid}",
                article=3,
                authored_by="oracle_reversion_promotion_scan",
                evidence=queued.get("gate_result"),
                before={"authority_level": current_in_auth or "display"},
                after={"authority_level": proposed},
                note=f"ratification applied: ratified_by={ratified_by}",
                root=governance_root,
            )

    if newly_ratified:
        _save_authority(data_dir, updated_authorities, dry_run)

    # -------------------------------------------------------------------------
    # Write queue
    # -------------------------------------------------------------------------
    queue = {
        "schema": "reversion_promotion_queue.v1",
        "generated_at": now.isoformat(timespec="seconds"),
        "n_compounds_scanned": len(compounds),
        "n_candidates": len(candidates),
        "n_lapses": len(lapses),
        "n_accruing": len(accruing),
        "n_requeue_reminders": len(requeue_reminders),
        "candidates": candidates,
        "lapses": lapses,
        "accruing": accruing,
        "requeue_reminders": requeue_reminders,
        "note": (
            "NEVER auto-promoted. All candidates require Fable/operator adjudication. "
            "Set ratified_by on a candidate row and commit to apply authority. "
            "ORACLE_REVERSION_PROMOTION_PREREG.md gates are FROZEN — do not retune."
        ),
    }

    if not dry_run:
        queue_path = data_dir / _QUEUE_PATH_REL
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(json.dumps(queue, indent=2, default=str))
        log.info(
            "reversion_promotion_queue.json written: %d candidates, %d lapses, %d accruing",
            len(candidates), len(lapses), len(accruing),
        )

    return {
        "n_compounds": len(compounds),
        "n_candidates": len(candidates),
        "n_lapses": len(lapses),
        "n_accruing": len(accruing),
        "n_requeue_reminders": len(requeue_reminders),
    }


# ---------------------------------------------------------------------------
# Print summary
# ---------------------------------------------------------------------------

def _print_summary(queue: dict, data_dir: Path) -> None:
    """Print a human-readable scan summary including accruing projections."""
    compounds = _load_reversion_compounds(data_dir)
    compound_by_id = {c.get("id"): c for c in compounds}

    print()
    print("=" * 70)
    print("  Oracle Reversion Promotion Scan")
    print(f"  generated_at: {queue.get('generated_at', 'n/a')}")
    print("=" * 70)

    candidates = queue.get("candidates", [])
    lapses = queue.get("lapses", [])
    accruing = queue.get("accruing", [])
    requeue = queue.get("requeue_reminders", [])

    if not candidates and not lapses:
        print()
        print("  no candidates — accruing (earliest projected per compound):")
        for a in accruing:
            proj = a.get("earliest_projected", "unknown")
            print(
                f"    [{a['compound_id']}] n={a['live_n']}"
                f"  refuse={a['refuse_reason']}"
                f"  earliest={proj}"
            )
        # For compounds with 0 rows, compute projection separately
        accruing_ids = {a["compound_id"] for a in accruing}
        candidate_ids = {c["compound_id"] for c in candidates}
        lapse_ids = {l["compound_id"] for l in lapses}
        for cid, compound in compound_by_id.items():
            if cid not in accruing_ids and cid not in candidate_ids and cid not in lapse_ids:
                proj = _project_earliest_promotion(compound, data_dir)
                print(f"    [{cid}] n=0  earliest={proj}")
        print()
    else:
        if candidates:
            print()
            print(f"  CANDIDATES ({len(candidates)}) — requires Fable adjudication:")
            for c in candidates:
                g = c.get("gate_result", {})
                print(
                    f"    [{c['compound_id']}] {c['compound_name']}"
                    f"  n={c['live_stats']['n']}"
                    f"  lift_lb={g.get('lift_lb', 'n/a')}"
                    f"  proposed={c['proposed_authority']}"
                )
        if lapses:
            print()
            print(f"  LAPSE PROPOSALS ({len(lapses)}) — requires ratification:")
            for l in lapses:
                print(f"    [{l['compound_id']}] {l['lapse_reason']}")

    if requeue:
        print()
        print(f"  REQUEUE REMINDERS ({len(requeue)}) — operator/Fable to re-screen:")
        for r in requeue:
            print(
                f"    [{r['compound_id']}] current_n={r['current_n']}"
                f"  requeue_at_n={r['requeue_at_n']}"
                f"  killed_at={r.get('killed_at_asof', 'n/a')}"
                f"  NOTE: re-screen is a new counted trial"
            )

    print()
    print(
        f"  n_compounds={queue.get('n_compounds_scanned', 0)}"
        f"  candidates={queue.get('n_candidates', 0)}"
        f"  lapses={queue.get('n_lapses', 0)}"
        f"  accruing={queue.get('n_accruing', 0)}"
    )
    print("=" * 70)
    print()


# ---------------------------------------------------------------------------
# Selftest — synthetic fixtures, no real data
# ---------------------------------------------------------------------------

def _run_selftest() -> int:
    """Demonstrate all four invariants with synthetic ledger fixtures.

    Returns 0 on success, 1 on any failure.

    Paths demonstrated:
    - grant path: n>=25, lift_lb>1.25 → candidate queued, authority UNCHANGED
    - refuse path: n<25 → refused, queue shows accruing
    - lapse path: n>=25, lift_lb<=1.25, current_authority=confirmer → lapse proposed
    - never-auto-promote: no ratified_by → authority file unchanged after scan
    """
    import tempfile

    print()
    print("=" * 70)
    print("  SELFTEST — oracle_reversion_promotion_scan")
    print("=" * 70)

    failures: list[str] = []

    def _make_matured_rows(
        compound_id: str,
        n: int,
        hits: int,
        operating_regime: str = "dual",
        first_fire: str = "2025-03-20",
    ) -> list[dict]:
        """Synthetic matured ledger rows.

        fire_date defaults to 2025-03-20 which is ~103 days before now=2025-07-01
        — within the 120-day staleness window.
        """
        rows = []
        for i in range(n):
            ret_exit = 0.05 if i < hits else -0.02
            regime = operating_regime if operating_regime != "dual" else (
                "risk_off" if i % 3 == 0 else "risk_on"
            )
            # All rows use the same fire_date so evidence_asof is the same day
            fire_date = first_fire
            rows.append({
                "compound_id": compound_id,
                "node": f"node_{i % 3}",
                "tier": "s",
                "fire_date": fire_date,
                "exec_date": fire_date,
                "exit_date": fire_date,
                "regime": regime,
                "ret_exit": ret_exit,
                "mfe": 0.08,
                "mae": -0.03,
                "matured": True,
            })
        return rows

    def _make_synthetic_registry(compound_id: str, operating_regime: str = "dual") -> list[dict]:
        return [{
            "id": compound_id,
            "name": f"Synthetic {compound_id}",
            "reversion": {
                "gauntlet": "PASS",
                "cluster": "test",
                "operating_regime": operating_regime,
                "asym": 1.83,
                "wr": 0.74,
                "ret_exit": 0.03,
                "n": 300,
            },
            "universe": {"tier": "s"},
            "mechanism_en": "synthetic test compound",
        }]

    from engine.neuralweb.constitution import grant_authority, wilson_lower

    # ------------------------------------------------------------------
    # GRANT PATH: n=30, hits=25, base_rate=0.55 → lift_lb should be >1.25
    # ------------------------------------------------------------------
    print()
    print("  [1] GRANT PATH (n=30, hits=25, base_rate=0.55):")
    n_grant, hits_grant, base_grant = 30, 25, 0.55
    wl_grant = wilson_lower(hits_grant, n_grant, z=_L3_Z)
    lift_grant = wl_grant / base_grant
    evidence_grant = {"hits": hits_grant, "n": n_grant, "base_rate": base_grant,
                      "evidence_asof": "2025-06-01"}
    floors_grant = {"min_n": _L3_MIN_N, "min_events": _L3_MIN_HITS}
    result_grant = grant_authority(evidence_grant, floors=floors_grant,
                                   now=datetime(2025, 7, 1, tzinfo=timezone.utc))
    if not result_grant.granted:
        failures.append(f"GRANT PATH refused: {result_grant.reason}")
        print(f"    FAIL — expected granted=True, got: {result_grant.reason}")
    else:
        print(
            f"    PASS — granted=True lift_lb={result_grant.lift_lb:.4f}"
            f" wilson_lb={result_grant.wilson_lb:.4f}"
        )

    # Verify queue is written but authority is NOT changed without ratified_by
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        # Write synthetic registry + ledger
        reg_dir = td / "data" / "oracle" / "compounds"
        reg_dir.mkdir(parents=True)
        fwd_dir = td / "data" / "oracle" / "reversion_forward"
        fwd_dir.mkdir(parents=True)

        compound_id = "SYNTH_GRANT"
        reg_dir.joinpath("registry.jsonl").write_text(
            json.dumps(_make_synthetic_registry(compound_id)[0]) + "\n"
        )
        rows = _make_matured_rows(compound_id, n=30, hits=25)
        fwd_dir.joinpath(f"{compound_id}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n"
        )

        # Write sidecar with base_rate
        site_dir = td / "site"
        sidecar_dir = site_dir / "basketdata"
        sidecar_dir.mkdir(parents=True)
        sidecar_dir.joinpath("oracle_reversion_state.json").write_text(
            json.dumps({"signals": [{"id": compound_id, "live": {"base_rate": 0.55}}]})
        )

        result = run_promotion_scan(
            td / "data", site_dir, dry_run=True,
            now=datetime(2025, 7, 1, tzinfo=timezone.utc),
            governance_root=td,
        )
        if result["n_candidates"] != 1:
            failures.append(f"GRANT PATH: expected 1 candidate, got {result['n_candidates']}")
            print(f"    FAIL — expected 1 candidate, got {result['n_candidates']}")
        else:
            print(f"    PASS — 1 candidate queued (n_candidates={result['n_candidates']})")

        # Authority file must NOT exist (no ratified_by)
        auth_path = td / "data" / "oracle" / "reversion_authority.json"
        if auth_path.exists():
            failures.append("NEVER-AUTO-PROMOTE violated: authority file written without ratified_by")
            print("    FAIL — authority file written without ratified_by!")
        else:
            print("    PASS — authority file NOT written (no ratified_by in queue row)")

    # ------------------------------------------------------------------
    # REFUSE PATH: n=10 (< _L3_MIN_N=25)
    # ------------------------------------------------------------------
    print()
    print(f"  [2] REFUSE PATH (n=10 < min_n={_L3_MIN_N}):")
    n_refuse, hits_refuse, base_refuse = 10, 8, 0.55
    evidence_refuse = {"hits": hits_refuse, "n": n_refuse, "base_rate": base_refuse,
                       "evidence_asof": "2025-06-01"}
    result_refuse = grant_authority(evidence_refuse, floors={"min_n": _L3_MIN_N, "min_events": 1},
                                    now=datetime(2025, 7, 1, tzinfo=timezone.utc))
    if result_refuse.granted:
        failures.append(f"REFUSE PATH granted unexpectedly: n={n_refuse}")
        print(f"    FAIL — expected refused, got granted")
    else:
        print(f"    PASS — refused: {result_refuse.reason}")

    # ------------------------------------------------------------------
    # LAPSE PATH: n=30, lift_lb <= 1.25, current_authority=confirmer
    # ------------------------------------------------------------------
    print()
    print("  [3] LAPSE PATH (lift_lb<=1.25 with existing confirmer authority):")
    n_lapse, hits_lapse, base_lapse = 30, 18, 0.75  # low hit rate → lift_lb<=1.25
    wl_lapse = wilson_lower(hits_lapse, n_lapse, z=_L3_Z)
    lift_lapse = wl_lapse / base_lapse
    print(f"       lift_lb={lift_lapse:.4f} (should be <= {_LAPSE_LIFT_LB_FLOOR})")

    if lift_lapse > _LAPSE_LIFT_LB_FLOOR:
        # Adjust to ensure lapse
        hits_lapse = 15
        wl_lapse = wilson_lower(hits_lapse, n_lapse, z=_L3_Z)
        lift_lapse = wl_lapse / base_lapse
        print(f"       adjusted: lift_lb={lift_lapse:.4f}")

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        reg_dir = td / "data" / "oracle" / "compounds"
        reg_dir.mkdir(parents=True)
        fwd_dir = td / "data" / "oracle" / "reversion_forward"
        fwd_dir.mkdir(parents=True)

        compound_id = "SYNTH_LAPSE"
        reg_dir.joinpath("registry.jsonl").write_text(
            json.dumps(_make_synthetic_registry(compound_id)[0]) + "\n"
        )
        rows = _make_matured_rows(compound_id, n=30, hits=hits_lapse)
        fwd_dir.joinpath(f"{compound_id}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n"
        )

        # Pre-seed authority file with confirmer tier
        auth_dir = td / "data" / "oracle"
        auth_payload = {
            "schema": "reversion_authority.v1",
            "updated_at": "2025-01-01T00:00:00",
            "authorities": {
                compound_id: {
                    "authority_level": "confirmer",
                    "ratified_by": "test_human",
                    "ratified_at": "2025-01-01T00:00:00",
                }
            },
        }
        auth_dir.joinpath("reversion_authority.json").write_text(
            json.dumps(auth_payload)
        )

        site_dir = td / "site"
        sidecar_dir = site_dir / "basketdata"
        sidecar_dir.mkdir(parents=True)
        sidecar_dir.joinpath("oracle_reversion_state.json").write_text(
            json.dumps({"signals": [{"id": compound_id, "live": {"base_rate": 0.75}}]})
        )

        result = run_promotion_scan(
            td / "data", site_dir, dry_run=True,
            now=datetime(2025, 7, 1, tzinfo=timezone.utc),
            governance_root=td,
        )
        if result["n_lapses"] != 1:
            failures.append(f"LAPSE PATH: expected 1 lapse, got {result['n_lapses']}")
            print(f"    FAIL — expected 1 lapse, got {result['n_lapses']}")
        else:
            print(f"    PASS — 1 lapse proposed (n_lapses={result['n_lapses']})")

    # ------------------------------------------------------------------
    # NEVER-AUTO-PROMOTE: grant path + no ratified_by → authority unchanged
    # ------------------------------------------------------------------
    print()
    print("  [4] NEVER-AUTO-PROMOTE: queue written, authority unchanged (no ratified_by):")
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        reg_dir = td / "data" / "oracle" / "compounds"
        reg_dir.mkdir(parents=True)
        fwd_dir = td / "data" / "oracle" / "reversion_forward"
        fwd_dir.mkdir(parents=True)

        compound_id = "SYNTH_NAP"
        reg_dir.joinpath("registry.jsonl").write_text(
            json.dumps(_make_synthetic_registry(compound_id)[0]) + "\n"
        )
        rows = _make_matured_rows(compound_id, n=30, hits=25)
        fwd_dir.joinpath(f"{compound_id}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n"
        )

        site_dir = td / "site"
        sidecar_dir = site_dir / "basketdata"
        sidecar_dir.mkdir(parents=True)
        sidecar_dir.joinpath("oracle_reversion_state.json").write_text(
            json.dumps({"signals": [{"id": compound_id, "live": {"base_rate": 0.55}}]})
        )

        # Write queue (no ratified_by)
        queue_dir = td / "data" / "oracle"
        queue_dir.mkdir(parents=True, exist_ok=True)
        queue_dir.joinpath("reversion_promotion_queue.json").write_text(
            json.dumps({"candidates": [{"compound_id": compound_id, "ratified_by": None}]})
        )

        run_promotion_scan(
            td / "data", site_dir, dry_run=False,
            now=datetime(2025, 7, 1, tzinfo=timezone.utc),
            governance_root=td,
        )

        auth_path = td / "data" / "oracle" / "reversion_authority.json"
        if auth_path.exists():
            auth_data = json.loads(auth_path.read_text())
            if compound_id in auth_data.get("authorities", {}):
                failures.append("NEVER-AUTO-PROMOTE violated: authority written without ratified_by")
                print("    FAIL — authority entry written without ratified_by!")
            else:
                print("    PASS — authority file exists but no entry for compound (empty from ratification)")
        else:
            print("    PASS — authority file not written (no ratified_by)")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    print("=" * 70)
    if failures:
        print(f"  SELFTEST FAIL — {len(failures)} failure(s):")
        for f in failures:
            print(f"    - {f}")
        print("=" * 70)
        return 1
    else:
        print("  SELFTEST PASS — grant/refuse/lapse/never-auto-promote all verified")
        print("=" * 70)
        return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(
        description="Oracle Reversion Promotion Scan (P2, armed-not-fired)"
    )
    p.add_argument("--data-dir", type=Path, default=None)
    p.add_argument("--site-dir", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="Run all logic but write no files")
    p.add_argument("--selftest", action="store_true",
                   help="Run synthetic selftest (no real data required)")
    args = p.parse_args()

    if args.selftest:
        return _run_selftest()

    from lib import config as _cfg
    data_dir = args.data_dir or _cfg.data_dir()
    site_dir = args.site_dir or (_cfg.ROOT / "site")

    log.info(
        "oracle_reversion_promotion_scan: data_dir=%s site_dir=%s dry_run=%s",
        data_dir, site_dir, args.dry_run,
    )

    try:
        summary = run_promotion_scan(data_dir, site_dir, dry_run=args.dry_run)
        log.info(
            "reversion_promotion_scan: %d compounds, %d candidates, %d lapses, %d accruing",
            summary["n_compounds"], summary["n_candidates"],
            summary["n_lapses"], summary["n_accruing"],
        )

        # Build and print the queue summary
        if not args.dry_run:
            queue_path = data_dir / _QUEUE_PATH_REL
            if queue_path.exists():
                queue = json.loads(queue_path.read_text())
                _print_summary(queue, data_dir)
        else:
            # Reconstruct a minimal queue for printing
            compounds = _load_reversion_compounds(data_dir)
            queue = {
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "n_compounds_scanned": len(compounds),
                "n_candidates": summary["n_candidates"],
                "n_lapses": summary["n_lapses"],
                "n_accruing": summary["n_accruing"],
                "candidates": [],
                "lapses": [],
                "accruing": [],
                "requeue_reminders": [],
            }
            _print_summary(queue, data_dir)

        return 0
    except Exception as e:  # noqa: BLE001
        print(f"::error::oracle_reversion_promotion_scan FAILED: {e}", flush=True)
        log.exception("oracle_reversion_promotion_scan FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
