"""engine.metabolism.dream — Weekly dream cycle (V2-D §3).

Stateless weekly pass that reads closed trial_ledger contracts + realized verify
outcomes → calibration curve of which proposal KINDS the proposer over/under-rates
→ data/metabolism/preference_prior.json (advisory only; NEVER gate-altering).

INERTNESS GUARANTEE:
  - Reads closed contracts + verify outcomes. Writes preference_prior.json only.
  - The prior is ADVISORY: marked not_gate_altering=True; it is appended to the
    next PROPOSE prompt as context, never as a rule change.
  - Subsumes the killed standalone preference-prior module + agenda-review.

HONEST NULL POLICY:
  If fewer than MIN_CLOSED_CONTRACTS mature contracts exist (most contracts
  pending until ~2026-10-15), the function outputs an honest 'insufficient_data'
  marker and writes a null prior — no fabricated calibration.

ANTI-ROT:
  The dream cycle triggers resummary of lessons.jsonl when it exceeds the byte cap
  (see engine.metabolism.memory.resummary_lessons).

OUTCOME PRIOR LEDGER (R-V8-10):
  data/metabolism/outcome_priors.jsonl is an append-only durable ledger: one row
  per newly-closed contract (proposal_id dedup; idempotent).  The preference prior
  is computed FROM this ledger so rotating trial_ledger.jsonl does not lobotomize
  the organism.  A one-time backfill from existing verify records runs on first use.

NEVER-RAISE CONTRACT: all public functions return safe fallbacks on any error.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# R-V5-4: import shared robust date parser
from engine.metabolism.verify import parse_check_by  # noqa: E402

log = logging.getLogger(__name__)

SCHEMA = "metabolism.preference_prior.v1"
OUTPUT_PATH = ("data", "metabolism", "preference_prior.json")

# R-V8-10: durable outcome-prior ledger (append-only; dedup by proposal_id)
OUTCOME_PRIORS_PATH = ("data", "metabolism", "outcome_priors.jsonl")

# Minimum number of CLOSED (check_by arrived) contracts before emitting calibration.
# Most contracts pending until ~2026-10-15; print accruing until then.
MIN_CLOSED_CONTRACTS = 10

# Advisory-only marker — asserted by tests and consumed by PROPOSE stage
NOT_GATE_ALTERING = True


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Outcome-prior ledger (R-V8-10) ────────────────────────────────────────────

def _outcome_priors_path(root: Path) -> Path:
    return root.joinpath(*OUTCOME_PRIORS_PATH)


def _load_outcome_prior_ids(root: Path) -> set[str]:
    """Load the set of proposal_ids already in outcome_priors.jsonl.  NEVER raises."""
    seen: set[str] = set()
    p = _outcome_priors_path(root)
    if not p.exists():
        return seen
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                pid = r.get("proposal_id")
                if pid:
                    seen.add(str(pid))
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        log.warning("dream._load_outcome_prior_ids: %s", exc)
    return seen


def _load_outcome_priors(root: Path) -> list[dict[str, Any]]:
    """Load all rows from outcome_priors.jsonl.  NEVER raises."""
    rows: list[dict[str, Any]] = []
    p = _outcome_priors_path(root)
    if not p.exists():
        return rows
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                rows.append(r)
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        log.warning("dream._load_outcome_priors: %s", exc)
    return rows


def _append_outcome_prior_row(root: Path, row: dict[str, Any]) -> None:
    """Append one row to outcome_priors.jsonl.  NEVER raises."""
    try:
        p = _outcome_priors_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("dream._append_outcome_prior_row: %s", exc)


def _build_prior_row(
    proposal_id: str,
    contract: dict[str, Any],
    verify_record: dict[str, Any],
    ts: str,
) -> dict[str, Any]:
    """Build one outcome_priors row from a verify record + the contract dict.

    Extracts kind, tier, lobe, sensors from the contract (which is the docket
    proposal snapshot embedded in the verify record).  Falls back to empty/unknown
    gracefully.
    """
    realized = verify_record.get("realized") or {}
    triage = verify_record.get("triage") or {}
    # sensors: may be a list under fitness_sensors, or a single sensor string
    sensors_raw = (
        contract.get("fitness_sensors")
        or contract.get("sensors")
        or []
    )
    if isinstance(sensors_raw, str):
        sensors_raw = [sensors_raw] if sensors_raw else []
    # Also include targets_sensor if present and not redundant
    target = contract.get("targets_sensor") or contract.get("sensor") or ""
    if target and target not in sensors_raw:
        sensors_raw = list(sensors_raw) + [target]

    return {
        "proposal_id": proposal_id,
        "kind": str(contract.get("kind") or contract.get("bucket") or "unknown"),
        "tier": str(contract.get("tier") or "unknown"),
        "lobe": str(contract.get("lobe") or contract.get("lobe_id") or ""),
        "sensors": [str(s) for s in sensors_raw if s],
        "outcome": str(realized.get("outcome") or "UNKNOWN"),
        "triage": str(triage.get("classification") or ""),
        "ts": ts,
    }


def _backfill_outcome_priors(root: Path) -> int:
    """One-time backfill: scan existing verify records and append any not yet in ledger.

    Safe to call repeatedly — idempotent due to proposal_id dedup.
    Returns number of rows newly appended.  NEVER raises.
    """
    try:
        existing_ids = _load_outcome_prior_ids(root)
        verify_dir = root / "data" / "metabolism" / "verify"
        if not verify_dir.exists():
            return 0
        added = 0
        ts = _now_iso()
        for f in sorted(verify_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("schema") != "metabolism.verify.v1":
                    continue
                proposal_id = str(data.get("proposal_id") or "")
                if not proposal_id or proposal_id in existing_ids:
                    continue
                realized = data.get("realized") or {}
                outcome = str(realized.get("outcome") or "")
                # Only backfill concluded (non-pending) records
                if not outcome or outcome == "PENDING":
                    continue
                contract = data.get("contract") or {}
                row = _build_prior_row(proposal_id, contract, data, ts)
                _append_outcome_prior_row(root, row)
                existing_ids.add(proposal_id)
                added += 1
            except Exception:  # noqa: BLE001
                continue
        if added:
            log.info("dream._backfill_outcome_priors: backfilled %d rows", added)
        return added
    except Exception as exc:  # noqa: BLE001
        log.warning("dream._backfill_outcome_priors: %s", exc)
        return 0


def _accrue_new_outcome_rows(
    root: Path,
    closed_contracts: list[dict[str, Any]],
    verify_outcomes: list[dict[str, Any]],
    ts: str,
) -> int:
    """Append any newly-closed contracts not yet in outcome_priors.jsonl.

    Returns count of newly appended rows.  NEVER raises.
    """
    try:
        existing_ids = _load_outcome_prior_ids(root)
        # Build verify outcome index
        outcome_index: dict[str, dict[str, Any]] = {}
        for v in verify_outcomes:
            key = str(v.get("proposal_id") or "")
            if key:
                outcome_index[key] = v

        added = 0
        for c in closed_contracts:
            proposal_id = str(
                c.get("proposal_id") or c.get("dedup_hash") or ""
            )
            if not proposal_id or proposal_id in existing_ids:
                continue
            v = outcome_index.get(proposal_id) or {}
            # Synthesize a row from contract + verify record
            row = _build_prior_row(proposal_id, c, v, ts)
            # If no verify record found, use contract outcome field if present
            if not v and c.get("outcome"):
                row["outcome"] = str(c["outcome"])
            _append_outcome_prior_row(root, row)
            existing_ids.add(proposal_id)
            added += 1
        return added
    except Exception as exc:  # noqa: BLE001
        log.warning("dream._accrue_new_outcome_rows: %s", exc)
        return 0


# ── Load closed contracts ─────────────────────────────────────────────────────

def _load_closed_contracts(root: Path, today: str) -> list[dict[str, Any]]:
    """Load trial_ledger contracts whose check_by has arrived (closed).

    Uses parse_check_by() for robust date comparison (R-V5-4): malformed
    check_by strings are excluded from calibration but counted in a
    "malformed" log rather than silently mis-ordered or included.

    Returns list of contract dicts.  NEVER raises.
    """
    closed: list[dict[str, Any]] = []
    malformed_count = 0
    today_date = parse_check_by(today)
    ledger_path = root / "data" / "trial_ledger.jsonl"
    if not ledger_path.exists():
        return closed
    try:
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                check_by_raw = r.get("check_by") or ""
                if not check_by_raw:
                    continue
                check_by_date = parse_check_by(str(check_by_raw))
                if check_by_date is None:
                    # Malformed check_by: exclude from calibration, count for logging
                    malformed_count += 1
                    continue
                # Closed = check_by has arrived and outcome is known
                if today_date is not None and check_by_date <= today_date and r.get("outcome"):
                    closed.append(r)
                elif today_date is None and str(check_by_raw) <= today and r.get("outcome"):
                    # Fallback string compare if today itself is malformed (should not happen)
                    closed.append(r)
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        log.warning("dream._load_closed_contracts: %s", exc)
    if malformed_count:
        log.warning(
            "dream._load_closed_contracts: excluded %d contracts with malformed check_by "
            "(R-V5-4: non-parseable dates excluded from calibration)",
            malformed_count,
        )
    return closed


def _load_verify_outcomes(root: Path) -> list[dict[str, Any]]:
    """Load all verify records from data/metabolism/verify/.  NEVER raises."""
    outcomes: list[dict[str, Any]] = []
    verify_dir = root / "data" / "metabolism" / "verify"
    if not verify_dir.exists():
        return outcomes
    for f in verify_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("schema") == "metabolism.verify.v1":
                outcomes.append(data)
        except Exception:  # noqa: BLE001
            continue
    return outcomes


# ── Calibration curve ─────────────────────────────────────────────────────────

def _build_calibration(
    closed_contracts: list[dict[str, Any]],
    verify_outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a calibration curve by proposal KIND.

    For each construction kind, compute the hit rate (confirmed / total closed).
    Returns a dict with per-kind stats.  NEVER raises.
    """
    # Index verify outcomes by cycle_id + proposal_id for O(1) lookup
    outcome_index: dict[str, dict[str, Any]] = {}
    for v in verify_outcomes:
        key = f"{v.get('cycle_id')}:{v.get('proposal_id')}"
        outcome_index[key] = v

    kind_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "confirmed": 0})
    tier_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "confirmed": 0})

    for c in closed_contracts:
        kind = str(c.get("kind") or c.get("bucket") or "unknown")
        tier = str(c.get("tier") or "unknown")
        cycle_id = str(c.get("cycle_id") or "")
        proposal_id = str(c.get("proposal_id") or c.get("dedup_hash") or "")
        key = f"{cycle_id}:{proposal_id}"

        v = outcome_index.get(key)
        confirmed = (
            v is not None
            and (v.get("realized") or {}).get("outcome") == "CONFIRMED"
            and (v.get("triage") or {}).get("classification") == "confirmed"
        )

        kind_counts[kind]["total"] += 1
        tier_counts[tier]["total"] += 1
        if confirmed:
            kind_counts[kind]["confirmed"] += 1
            tier_counts[tier]["confirmed"] += 1

    def _hit_rate(d: dict[str, int]) -> float | None:
        if d["total"] == 0:
            return None
        return round(d["confirmed"] / d["total"], 3)

    calibration: dict[str, Any] = {
        "by_kind": {
            k: {"total": v["total"], "confirmed": v["confirmed"], "hit_rate": _hit_rate(v)}
            for k, v in kind_counts.items()
        },
        "by_tier": {
            k: {"total": v["total"], "confirmed": v["confirmed"], "hit_rate": _hit_rate(v)}
            for k, v in tier_counts.items()
        },
        "overall": {
            "total": sum(v["total"] for v in kind_counts.values()),
            "confirmed": sum(v["confirmed"] for v in kind_counts.values()),
            "hit_rate": None,
        },
    }
    total = calibration["overall"]["total"]
    confirmed = calibration["overall"]["confirmed"]
    if total > 0:
        calibration["overall"]["hit_rate"] = round(confirmed / total, 3)
    return calibration


# ── Calibration from outcome_priors ledger (R-V8-10/R-V8-12) ─────────────────

def _build_calibration_from_priors(
    prior_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build calibration buckets from outcome_priors.jsonl rows.

    Computes:
      - by_kind: {kind → {total, confirmed, hit_rate}}
      - by_lobe_sensor: {"{lobe}:{sensor}" → {total, confirmed, hit_rate}}
      - overall: aggregate

    A row is "confirmed" when outcome == "CONFIRMED" (case-insensitive).
    NEVER raises.
    """
    kind_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "confirmed": 0}
    )
    lobe_sensor_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "confirmed": 0}
    )

    for row in prior_rows:
        outcome = str(row.get("outcome") or "").upper()
        triage = str(row.get("triage") or "").lower()

        # R-V8-11 / FIX-4: UNVERIFIABLE outcomes are excluded from BOTH numerator
        # and denominator — an un-evaluable outcome is not evidence the construction
        # is bad.  Only CONFIRMED and FALSIFIER_TRIPPED count.
        if outcome == "UNVERIFIABLE":
            continue

        # A hit requires outcome=='CONFIRMED' AND triage=='confirmed' (conjunction).
        is_confirmed = outcome == "CONFIRMED" and triage == "confirmed"

        kind = str(row.get("kind") or "unknown")
        lobe = str(row.get("lobe") or "")
        sensors = row.get("sensors") or []
        if isinstance(sensors, str):
            sensors = [sensors] if sensors else []

        kind_counts[kind]["total"] += 1
        if is_confirmed:
            kind_counts[kind]["confirmed"] += 1

        # Per (lobe, sensor) bucket — one entry per sensor
        sensor_list = [str(s) for s in sensors if s]
        if not sensor_list:
            sensor_list = ["_no_sensor"]
        for sensor in sensor_list:
            key = f"{lobe}:{sensor}"
            lobe_sensor_counts[key]["total"] += 1
            if is_confirmed:
                lobe_sensor_counts[key]["confirmed"] += 1

    def _hit_rate(d: dict[str, int]) -> float | None:
        if d["total"] == 0:
            return None
        return round(d["confirmed"] / d["total"], 3)

    total_all = sum(v["total"] for v in kind_counts.values())
    confirmed_all = sum(v["confirmed"] for v in kind_counts.values())

    return {
        "by_kind": {
            k: {"total": v["total"], "confirmed": v["confirmed"], "hit_rate": _hit_rate(v)}
            for k, v in kind_counts.items()
        },
        "by_lobe_sensor": {
            k: {"total": v["total"], "confirmed": v["confirmed"], "hit_rate": _hit_rate(v)}
            for k, v in lobe_sensor_counts.items()
        },
        "overall": {
            "total": total_all,
            "confirmed": confirmed_all,
            "hit_rate": round(confirmed_all / total_all, 3) if total_all > 0 else None,
        },
    }


# ── Advisory-only observations ─────────────────────────────────────────────────

def _build_advisory_observations(calibration: dict[str, Any]) -> list[str]:
    """Derive advisory observations from the calibration curve.

    These are plain-English notes for the PROPOSE stage — never rules.
    NEVER raises.
    """
    observations: list[str] = []
    by_kind = calibration.get("by_kind") or {}
    for kind, stats in by_kind.items():
        hr = stats.get("hit_rate")
        total = stats.get("total", 0)
        if total < 5 or hr is None:
            continue
        if hr < 0.3:
            observations.append(
                f"[advisory] '{kind}' proposals have a low confirmation rate "
                f"({hr:.0%} of {total} closed). Consider raising the bar "
                f"or checking whether the construction is repeating a dead pattern."
            )
        elif hr > 0.7:
            observations.append(
                f"[advisory] '{kind}' proposals have a high confirmation rate "
                f"({hr:.0%} of {total} closed). This kind tends to earn its contract."
            )
    return observations


# ── Main dream function ───────────────────────────────────────────────────────

def run_dream_cycle(
    root: Path | None = None,
    today: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run one weekly dream cycle pass.

    Reads closed trial_ledger contracts + verify outcomes.
    Writes data/metabolism/preference_prior.json.
    Triggers anti-rot resummary of lessons.jsonl if needed.

    Returns the preference_prior dict.  NEVER raises.

    The prior carries not_gate_altering=True — it is ADVISORY ONLY.
    """
    try:
        repo = _repo_root(root)
        ts = _now_iso()
        if today is None:
            today = _today_str()

        # Check is_paused (INERTNESS: no-op when paused)
        try:
            from scripts.metabolism_guard import is_paused  # type: ignore[import]
            if is_paused():
                log.info("dream: AUTONOMY_PAUSED — skipping cycle")
                return _paused_prior(ts)
        except Exception:  # noqa: BLE001
            # FAIL-CLOSED (R-AUT-2): if the guard is unavailable, treat as PAUSED
            # unless AUTONOMY_PAUSED is explicitly 'false'.
            import os as _os
            if _os.environ.get("AUTONOMY_PAUSED", "").strip().lower() != "false":
                log.info("dream: guard unavailable + not explicitly armed — skipping (fail-closed)")
                return _paused_prior(ts)

        # R-V8-10: one-time backfill from existing verify records (idempotent)
        if not dry_run:
            _backfill_outcome_priors(repo)

        # Load closed contracts + verify outcomes
        closed = _load_closed_contracts(repo, today)
        outcomes = _load_verify_outcomes(repo)

        # R-V8-10: accrue new closed contracts to the durable ledger
        if not dry_run:
            _accrue_new_outcome_rows(repo, closed, outcomes, ts)

        # Build calibration FROM the durable ledger (not from live trial_ledger rows)
        prior_rows = _load_outcome_priors(repo)
        n_prior_rows = len(prior_rows)

        # Honest null: not enough mature data yet
        if n_prior_rows < MIN_CLOSED_CONTRACTS:
            prior = _insufficient_data_prior(ts, n_closed=n_prior_rows)
            if not dry_run:
                _write_prior(prior, repo)
            # Anti-rot check even on insufficient data
            _maybe_resummary(repo)
            return prior

        # Build calibration from durable prior ledger (R-V8-10: rotation-proof)
        calibration = _build_calibration_from_priors(prior_rows)
        observations = _build_advisory_observations(calibration)

        prior: dict[str, Any] = {
            "schema": SCHEMA,
            "ts": ts,
            "as_of": today,
            "not_gate_altering": NOT_GATE_ALTERING,
            "note": (
                "Advisory calibration from closed trial contracts. "
                "This prior is context-only — it NEVER alters gates, thresholds, "
                "or authority surfaces. It is appended to the next PROPOSE prompt."
            ),
            "n_closed_contracts": n_prior_rows,
            "n_verify_outcomes": len(outcomes),
            "calibration": calibration,
            "advisory_observations": observations,
            "authority": {
                "is_context_only": True,
                "may_rank": False,
                "may_gate": False,
                "may_size": False,
                "may_escalate": False,
                "display_only": True,
                "not_a_signal": True,
                "tier": "shadow",
                "not_gate_altering": True,
            },
        }

        if not dry_run:
            _write_prior(prior, repo)

        # Anti-rot: trigger re-summarization of lessons.jsonl if needed
        _maybe_resummary(repo)

        log.info(
            "dream: wrote preference_prior (n_prior_rows=%d, n_outcomes=%d)",
            n_prior_rows, len(outcomes),
        )
        return prior

    except Exception as exc:  # noqa: BLE001
        log.warning("dream.run_dream_cycle: %s", exc)
        return _error_prior(str(exc))


def _paused_prior(ts: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "ts": ts,
        "not_gate_altering": NOT_GATE_ALTERING,
        "status": "paused",
        "note": "AUTONOMY_PAUSED — dream cycle skipped.",
        "authority": {"is_context_only": True, "not_gate_altering": True, "display_only": True},
    }


def _insufficient_data_prior(ts: str, n_closed: int) -> dict[str, Any]:
    """Honest null prior when fewer than MIN_CLOSED_CONTRACTS mature contracts exist."""
    return {
        "schema": SCHEMA,
        "ts": ts,
        "not_gate_altering": NOT_GATE_ALTERING,
        "status": "insufficient_data",
        "n_closed_contracts": n_closed,
        "min_required": MIN_CLOSED_CONTRACTS,
        "note": (
            f"Insufficient closed contracts for calibration: {n_closed} of "
            f"{MIN_CLOSED_CONTRACTS} required. Most contracts pending until "
            f"~2026-10-15 (typical check_by horizon). Accruing — no fabricated calibration."
        ),
        "calibration": None,
        "advisory_observations": [],
        "authority": {
            "is_context_only": True,
            "may_rank": False,
            "may_gate": False,
            "may_size": False,
            "may_escalate": False,
            "display_only": True,
            "not_a_signal": True,
            "tier": "shadow",
            "not_gate_altering": True,
        },
    }


def _error_prior(error: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "ts": _now_iso(),
        "not_gate_altering": NOT_GATE_ALTERING,
        "status": "error",
        "error": error,
        "note": "Dream cycle errored — prior not updated.",
        "authority": {"is_context_only": True, "not_gate_altering": True, "display_only": True},
    }


def _write_prior(prior: dict[str, Any], repo: Path) -> None:
    """Atomically write preference_prior.json.  NEVER raises."""
    try:
        p = repo.joinpath(*OUTPUT_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(prior, indent=2, default=str), encoding="utf-8")
        tmp.replace(p)
    except Exception as exc:  # noqa: BLE001
        log.warning("dream._write_prior: %s", exc)


def _maybe_resummary(repo: Path) -> None:
    """Trigger anti-rot resummary of lessons.jsonl if it exceeds the byte cap."""
    try:
        from engine.metabolism.memory import _needs_resummary  # type: ignore[import]
        if _needs_resummary(repo):
            # Detection + log only. The actual anti-rot resummary of lessons.jsonl
            # runs in scripts/metabolism_dream.py:_maybe_resummary (which owns the
            # rewrite). This engine helper does NOT mutate any artifact — it is a
            # pure detector so the caller can log/branch. (No flag is written here.)
            log.info("dream: lessons.jsonl exceeds byte cap — resummary due (runs in dream script)")
    except Exception:  # noqa: BLE001
        pass


def load_preference_prior(root: Path | None = None) -> dict[str, Any]:
    """Load the current preference_prior.json, or return empty dict.  NEVER raises."""
    try:
        repo = _repo_root(root)
        p = repo.joinpath(*OUTPUT_PATH)
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("dream.load_preference_prior: %s", exc)
        return {}


def load_outcome_priors(root: Path | None = None) -> list[dict[str, Any]]:
    """Load all rows from data/metabolism/outcome_priors.jsonl.  NEVER raises."""
    return _load_outcome_priors(_repo_root(root))


def get_calibration_from_priors(root: Path | None = None) -> dict[str, Any]:
    """Load outcome_priors.jsonl and return calibration buckets.  NEVER raises.

    Returns a calibration dict with by_kind, by_lobe_sensor, and overall keys.
    Returns an empty dict when the ledger is absent or empty.
    """
    try:
        rows = load_outcome_priors(root)
        if not rows:
            return {}
        return _build_calibration_from_priors(rows)
    except Exception as exc:  # noqa: BLE001
        log.warning("dream.get_calibration_from_priors: %s", exc)
        return {}
