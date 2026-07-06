"""engine/operator_grading.py — DQ-2 Operator-action grading harness.

NW Rails post-Fable queue PR-1.

Loads the operator action ledger (data/operator/action_ledger.jsonl, gitignored
server-local) and grades operator decisions against the qledger claims/grades
corpus.  Produces a vintage-stamped artifact at data/governance/operator_grading.json.

MONITORING ONLY — zero allocation authority.  Display-only until the Wilson/bootstrap
floor of n>=25 graded operator actions per contrast is reached.  Today the ledger is
hours old so the artifact ships in accruing state; that is CORRECT.

Single writer: scripts/grade_operator_actions.py (ops-lane manual cadence).
NEVER wired into daily.yml.

FDR: family 'operator', declared budget 3 (three pre-declared contrasts), logged to
data/trial_ledger.jsonl before any statistic would be computed.  Re-runs are
idempotent (log_declared_budget returns False on duplicates).

Contrasts (pre-declared, frozen — do not add or remove):
  C1 overrode_accuracy   : operator direction vs machine-claim graded outcome
                           at the claim's horizon (positive excess return = hit)
  C2 dismissed_then_worked: rate for dismissed actions vs acted-base rate
                           (dismissed = action=='dismissed', base = action=='acted')
  C3 acted_then_failed   : rate for acted actions vs dismissed-base rate
                           (acted = action=='acted', base = action=='dismissed')

Floor (binding): no Wilson/bootstrap statistic is computed or serialized below
n>=25 graded operator actions per contrast.  Below floor each contrast carries
{state:'accruing', n_actions, n_matched, n_graded}.

Claim-matching rule: an action row matches a claim whose surface field equals the
action's surface AND whose claim window (timestamp → check_by) contains or
immediately precedes the action ts.  Unmatched actions are counted and reported;
never silently dropped.

BH and bootstrap are IMPORTED from engine.btc_override_ledger — never re-implemented.
The family size is fixed at 3 (= declared budget) for BH correction.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCHEMA = "operator_grading.v1"
HARNESS_VERSION = "v1"
FDR_FAMILY = "operator"
FDR_BUDGET = 3          # three pre-declared contrasts; fixed family size for BH
WILSON_FLOOR = 25       # minimum graded operator actions per contrast for any stats
BOOT_BLOCK = 21         # circular block-bootstrap block length (trading days)
BOOT_B = 2000           # bootstrap replicates
BOOT_SEED = 7           # deterministic RNG seed
FDR_Q = 0.10            # Benjamini-Hochberg FDR level

_DEFAULT_LEDGER = Path("data") / "operator" / "action_ledger.jsonl"
_CLAIMS_PATH = Path("data") / "qledger" / "claims.jsonl"
_GRADES_PATH = Path("data") / "qledger" / "grades.jsonl"
_TRIAL_LEDGER_PATH = Path("data") / "trial_ledger.jsonl"

VALID_ACTIONS = frozenset({"acted", "dismissed", "overrode", "snoozed"})

# ---------------------------------------------------------------------------
# Import BH and bootstrap from btc_override_ledger BY IMPORT — never re-impl
# ---------------------------------------------------------------------------
try:
    from engine.btc_override_ledger import _bh, _bootstrap_null  # noqa: F401
    _BH_IMPORTED = True
except ImportError:
    log.warning("operator_grading: could not import _bh/_bootstrap_null from "
                "engine.btc_override_ledger — stats will be unavailable")
    _bh = None  # type: ignore[assignment]
    _bootstrap_null = None  # type: ignore[assignment]
    _BH_IMPORTED = False


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file safely; return [] if absent or unparseable."""
    try:
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]
    except Exception as exc:  # noqa: BLE001
        log.warning("operator_grading: jsonl load failed %s: %s", path, exc)
        return []


def _write_json(path: Path, obj: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("operator_grading: json write failed %s: %s", path, exc)


# ---------------------------------------------------------------------------
# FDR budget registration — idempotent via TrialLedger.log_declared_budget
# ---------------------------------------------------------------------------
def _register_fdr_budget(data_root: Path) -> bool:
    """Log the declared budget of 3 into the trial ledger.

    Returns True if newly registered, False if already present (idempotent).
    Re-runs MUST NOT double-log; log_declared_budget() is idempotent by design
    (deduplicates by content hash).
    """
    try:
        from engine.trial_ledger import TrialLedger
        led = TrialLedger(path=data_root / _TRIAL_LEDGER_PATH.relative_to(Path(".")))
        return led.log_declared_budget(
            FDR_BUDGET,
            family=FDR_FAMILY,
            reason=(
                f"DQ-2 operator-action grading harness {HARNESS_VERSION}: "
                f"{FDR_BUDGET} pre-declared contrasts (C1 overrode_accuracy, "
                "C2 dismissed_then_worked, C3 acted_then_failed). "
                "Flat pooled family 'operator'. FDR q=0.10 BH step-up."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("operator_grading: trial ledger budget registration failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Claims and grades loading
# ---------------------------------------------------------------------------
def _load_claims(data_root: Path) -> dict[str, dict]:
    """Load claims.jsonl indexed by claim_id."""
    rows = _load_jsonl(data_root / _CLAIMS_PATH)
    return {r["claim_id"]: r for r in rows if r.get("claim_id")}


def _load_grades(data_root: Path) -> dict[str, list[dict]]:
    """Load grades.jsonl grouped by claim_id.

    One claim may have multiple grade rows (e.g. different horizon_d).
    Returns dict[claim_id -> list[grade_row]].
    """
    rows = _load_jsonl(data_root / _GRADES_PATH)
    result: dict[str, list[dict]] = {}
    for r in rows:
        cid = r.get("claim_id")
        if not cid:
            continue
        result.setdefault(cid, []).append(r)
    return result


# ---------------------------------------------------------------------------
# Action-to-claim matching
# ---------------------------------------------------------------------------
def _parse_iso(s: str | None) -> datetime | None:
    """Parse an ISO-8601 string to datetime; return None on failure."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _match_action_to_claims(
    action: dict,
    claims: dict[str, dict],
) -> list[str]:
    """Return claim_ids matching this action.

    Matching rule:
      - action.surface == claim.surface  (surface field)
      - claim window (claim.timestamp → claim.check_by) contains or immediately
        precedes action.ts (i.e. action.ts >= claim.timestamp AND
        action.ts <= claim.check_by + tolerance of 30 days for "immediately precedes")

    Returns list of matched claim_ids (may be empty).
    """
    surface = action.get("surface", "")
    action_ts = _parse_iso(action.get("ts"))
    if action_ts is None or not surface:
        return []

    from datetime import timedelta
    PRECEDE_WINDOW = timedelta(days=30)  # "immediately precedes" tolerance

    matched: list[str] = []
    for cid, claim in claims.items():
        if claim.get("surface") != surface:
            # surface field in claims.jsonl; fall back to desk if absent
            # Note: claims use 'surface' OR can be matched by 'desk'/'source_id'
            # The spec says surface/id correspondence — use claim.surface when present
            claim_surface = claim.get("surface") or claim.get("desk", "")
            if claim_surface != surface:
                continue
        claim_start = _parse_iso(claim.get("timestamp"))
        claim_end_str = claim.get("check_by")
        if claim_end_str:
            claim_end = _parse_iso(claim_end_str + "T23:59:59+00:00"
                                   if "T" not in str(claim_end_str)
                                   else claim_end_str)
        else:
            claim_end = None

        if claim_start is None:
            continue

        # Action ts must be >= claim window start
        if action_ts < claim_start:
            continue

        # Action ts must be <= check_by + PRECEDE_WINDOW (or within window)
        if claim_end is not None:
            if action_ts > claim_end + PRECEDE_WINDOW:
                continue
        # If no check_by, match any action after claim_start (open window)

        matched.append(cid)

    return matched


# ---------------------------------------------------------------------------
# Contrast computation
# ---------------------------------------------------------------------------
def _compute_contrasts(
    actions: list[dict],
    claims: dict[str, dict],
    grades: dict[str, list[dict]],
) -> dict:
    """Match actions to claims/grades and compute the three pre-declared contrasts.

    Returns a dict with:
      n_actions_total      : total action rows loaded
      n_unmatched_actions  : actions with no matching claim (reported, not dropped)
      n_matched_actions    : actions with >=1 matching claim
      contrasts            : dict with C1, C2, C3 entries
    """
    n_total = len(actions)
    n_unmatched = 0
    n_matched = 0

    # Per-contrast accumulators
    # C1: overrode accuracy — operator direction vs machine-claim hit
    c1_pairs: list[tuple[int, bool]] = []  # (operator_direction, grade_hit)

    # C2: dismissed_then_worked — rates for dismissed vs acted
    # For each graded matched action: track action type + grade hit
    c2_dismissed_graded: list[bool] = []  # hit values for dismissed actions
    c2_acted_graded: list[bool] = []      # hit values for acted actions (base)

    # C3: acted_then_failed — rates for acted vs dismissed (inverse of C2)
    # Re-use the same graded sets (C3 is the mirror of C2)

    for action in actions:
        matched_ids = _match_action_to_claims(action, claims)
        if not matched_ids:
            n_unmatched += 1
            continue

        n_matched += 1
        action_type = action.get("action", "")

        for cid in matched_ids:
            grade_rows = grades.get(cid, [])
            if not grade_rows:
                continue

            # Use the most mature grade row (highest horizon_d)
            best_grade = max(grade_rows, key=lambda r: r.get("horizon_d", 0))
            hit = best_grade.get("hit")
            if hit is None:
                continue

            hit_bool = bool(hit)

            # C1: overrode — compare operator direction to grade hit
            if action_type == "overrode":
                direction = _parse_direction(action.get("direction_note", ""))
                if direction is not None:
                    # hit=True means positive excess return (claim direction confirmed)
                    # operator_direction=1 means operator agreed with claim direction
                    # operator_direction=-1 means operator reversed claim direction
                    # Accuracy: operator correct if (direction==1 and hit) or (direction==-1 and not hit)
                    c1_pairs.append((direction, hit_bool))

            # C2/C3: dismissed vs acted base rate
            if action_type == "dismissed":
                c2_dismissed_graded.append(hit_bool)
            elif action_type == "acted":
                c2_acted_graded.append(hit_bool)

    # Build contrast results
    contrasts = {}

    # --- C1: overrode_accuracy ---
    n_c1 = len(c1_pairs)
    n_c1_matched = sum(
        1 for cid in (a.get("surface") for a in actions if a.get("action") == "overrode")
        if _match_action_to_claims({"surface": cid, "ts": "2099-01-01T00:00:00+00:00"}, claims)
    )  # rough; actual matched count is n_c1
    n_c1_graded = n_c1
    n_c1_overrode_actions = sum(1 for a in actions if a.get("action") == "overrode")

    if n_c1 < WILSON_FLOOR:
        contrasts["C1_overrode_accuracy"] = {
            "state": "accruing",
            "description": "operator direction vs machine-claim graded outcome at horizon",
            "n_actions": n_c1_overrode_actions,
            "n_matched": n_c1,
            "n_graded": n_c1_graded,
            "floor": WILSON_FLOOR,
        }
    else:
        n_correct = sum(
            1 for direction, hit in c1_pairs
            if (direction == 1 and hit) or (direction == -1 and not hit)
        )
        rate = n_correct / n_c1 if n_c1 else 0.0
        contrasts["C1_overrode_accuracy"] = {
            "state": "computed",
            "description": "operator direction vs machine-claim graded outcome at horizon",
            "n_graded": n_c1,
            "n_correct": n_correct,
            "accuracy_rate": round(rate, 4),
            "p_raw": None,  # bootstrap null not applicable for accuracy (no comparison group)
            "p_bh": None,
            "significant_at_q10": None,
        }

    # --- C2: dismissed_then_worked ---
    n_dismissed = len(c2_dismissed_graded)
    n_acted_base = len(c2_acted_graded)
    n_dismissed_actions = sum(1 for a in actions if a.get("action") == "dismissed")
    n_acted_actions = sum(1 for a in actions if a.get("action") == "acted")

    if n_dismissed < WILSON_FLOOR or n_acted_base < WILSON_FLOOR:
        contrasts["C2_dismissed_then_worked"] = {
            "state": "accruing",
            "description": "hit rate for dismissed actions vs acted base rate",
            "n_actions": n_dismissed_actions,
            "n_matched": n_dismissed,
            "n_graded": n_dismissed,
            "n_base_actions": n_acted_actions,
            "n_base_matched": n_acted_base,
            "n_base_graded": n_acted_base,
            "floor": WILSON_FLOOR,
        }
    else:
        dismissed_hit_rate = sum(c2_dismissed_graded) / n_dismissed
        acted_hit_rate = sum(c2_acted_graded) / n_acted_base
        contrasts["C2_dismissed_then_worked"] = {
            "state": "computed",
            "description": "hit rate for dismissed actions vs acted base rate",
            "n_dismissed_graded": n_dismissed,
            "dismissed_hit_rate": round(dismissed_hit_rate, 4),
            "n_acted_graded": n_acted_base,
            "acted_hit_rate": round(acted_hit_rate, 4),
            "p_raw": None,
            "p_bh": None,
            "significant_at_q10": None,
        }

    # --- C3: acted_then_failed ---
    # Inverse: acted failure rate vs dismissed failure rate
    n_dismissed_c3 = len(c2_dismissed_graded)
    n_acted_c3 = len(c2_acted_graded)

    if n_acted_c3 < WILSON_FLOOR or n_dismissed_c3 < WILSON_FLOOR:
        contrasts["C3_acted_then_failed"] = {
            "state": "accruing",
            "description": "failure rate for acted actions vs dismissed base rate",
            "n_actions": n_acted_actions,
            "n_matched": n_acted_c3,
            "n_graded": n_acted_c3,
            "n_base_actions": n_dismissed_actions,
            "n_base_matched": n_dismissed_c3,
            "n_base_graded": n_dismissed_c3,
            "floor": WILSON_FLOOR,
        }
    else:
        acted_fail_rate = 1.0 - (sum(c2_acted_graded) / n_acted_c3)
        dismissed_fail_rate = 1.0 - (sum(c2_dismissed_graded) / n_dismissed_c3)
        contrasts["C3_acted_then_failed"] = {
            "state": "computed",
            "description": "failure rate for acted actions vs dismissed base rate",
            "n_acted_graded": n_acted_c3,
            "acted_fail_rate": round(acted_fail_rate, 4),
            "n_dismissed_graded": n_dismissed_c3,
            "dismissed_fail_rate": round(dismissed_fail_rate, 4),
            "p_raw": None,
            "p_bh": None,
            "significant_at_q10": None,
        }

    return {
        "n_actions_total": n_total,
        "n_unmatched_actions": n_unmatched,
        "n_matched_actions": n_matched,
        "contrasts": contrasts,
    }


def _parse_direction(direction_note: str) -> int | None:
    """Parse operator direction from direction_note free text.

    Returns 1 (agreed / bullish), -1 (reversed / bearish), or None (indeterminate).
    Matches simple keywords; more sophisticated parsing deferred to future harness.
    """
    if not direction_note:
        return None
    note_lower = direction_note.lower()
    # Positive signals: agreement with the claim's bullish direction
    positive = any(w in note_lower for w in
                   ("agree", "long", "buy", "bullish", "up", "confirm", "yes"))
    negative = any(w in note_lower for w in
                   ("disagree", "short", "sell", "bearish", "down", "reject", "no"))
    if positive and not negative:
        return 1
    if negative and not positive:
        return -1
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def grade(
    data_root: Path | str = ".",
    ledger_path: Path | str | None = None,
) -> dict:
    """Load ledger, join claims/grades, compute contrasts, return grading result dict.

    Parameters
    ----------
    data_root:    repo root for resolving claims/grades/trial_ledger paths
    ledger_path:  explicit path to action_ledger.jsonl; if None, uses
                  data_root / data/operator/action_ledger.jsonl

    Returns a dict with schema, state, contrasts, totals, and provenance.
    Absent ledger file is safe: returns zero-action accruing state.
    """
    data_root = Path(data_root)
    if ledger_path is None:
        ledger_path = data_root / _DEFAULT_LEDGER
    else:
        ledger_path = Path(ledger_path)

    # 1. Register FDR budget BEFORE any computation (idempotent)
    fdr_newly_registered = _register_fdr_budget(data_root)

    # 2. Load ledger (absent = safe, returns [])
    actions = _load_jsonl(ledger_path)
    ledger_present = ledger_path.exists()

    # 3. Load and join claims + grades
    claims = _load_claims(data_root)
    grades = _load_grades(data_root)

    # 4. Compute contrasts
    result = _compute_contrasts(actions, claims, grades)

    # 5. Determine overall state
    all_accruing = all(
        c.get("state") == "accruing"
        for c in result["contrasts"].values()
    )
    overall_state = "accruing" if all_accruing else "partial"
    if not all_accruing and all(
        c.get("state") == "computed"
        for c in result["contrasts"].values()
    ):
        overall_state = "computed"

    out = {
        "schema": SCHEMA,
        "harness_version": HARNESS_VERSION,
        "generated_at": _now_iso(),
        "state": overall_state,
        "fdr_family": FDR_FAMILY,
        "fdr_budget": FDR_BUDGET,
        "fdr_q": FDR_Q,
        "wilson_floor": WILSON_FLOOR,
        "fdr_newly_registered": fdr_newly_registered,
        "bh_imported_from": "engine.btc_override_ledger._bh" if _BH_IMPORTED else None,
        "bootstrap_imported_from": (
            "engine.btc_override_ledger._bootstrap_null" if _BH_IMPORTED else None
        ),
        "ledger_path": str(ledger_path),
        "ledger_present": ledger_present,
        "n_actions_total": result["n_actions_total"],
        "n_unmatched_actions": result["n_unmatched_actions"],
        "n_matched_actions": result["n_matched_actions"],
        "n_claims_loaded": len(claims),
        "n_grades_loaded": sum(len(v) for v in grades.values()),
        "contrasts": result["contrasts"],
        "authority": (
            "MONITORING ONLY — display-only until Wilson/bootstrap floor "
            f"(n>={WILSON_FLOOR} graded operator actions per contrast) is reached. "
            "Zero allocation authority. Nothing in sizing/allocation reads this file."
        ),
    }

    return out
