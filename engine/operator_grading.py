"""engine/operator_grading.py — DQ-2 Operator-action grading harness.

NW Rails post-Fable queue PR-1.

Loads the operator action ledger (data/operator/action_ledger.jsonl, gitignored
server-local) and grades operator decisions against the qledger claims/grades
corpus.  Produces a vintage-stamped artifact at data/governance/operator_grading.json.

MONITORING ONLY — zero allocation authority.  Display-only until the Wilson
floor of n>=25 graded operator ACTIONS per contrast is reached.  Today the
ledger is hours old so the artifact ships in accruing state; that is CORRECT.

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

Floor (binding): no Wilson statistic is computed or serialized below n>=25
graded operator ACTIONS per contrast.  Below floor each contrast carries
{state:'accruing', n_actions, n_matched, n_graded}.

At or above the floor, each contrast publishes Wilson 95% score intervals with
BH q=0.10 across the 3 contrasts.  The floor's own semantics apply — these are
per-action observation counts, not per-matched-claim counts.

Per-action aggregation rule (BINDING — documented here and in artifact meta):
  An action with K matched graded claims contributes EXACTLY ONE observation
  to a contrast's outcome aggregation.  Its per-action outcome is the MEAN hit
  value across its K graded claims, thresholded at 0.5 to produce a boolean
  (>=0.5 → True, <0.5 → False).  No action is double-weighted regardless of
  how many claims it matches.  The floor count (n>=25) is over DISTINCT actions
  having at least one graded matched claim.

Match-window approximation note (KNOWN — 30-day tolerance):
  The claim-matching rule allows an action to match a claim up to 30 days after
  the claim's check_by date ("immediately precedes" tolerance).  This is a
  known approximation that may admit marginally late action-claim pairings.
  The artifact meta carries a 'match_window_note' field to record this.

Statistics at floor (>=25 per-action observations per contrast):
  - Rate (proportion of per-action observations that are hits / correct)
  - Wilson 95% score interval (lo, hi) from engine.grading_stats.wilson_ci
  - Exact two-sided binomial p-value:
      C1: null p = 0.5 (chance accuracy for overrode-accuracy)
      C2: null p = acted_cohort observed rate (conditional-null approximation —
          noted in artifact meta; this cohort rate is the base against which
          the dismissed-action hit rate is compared)
      C3: null p = dismissed_cohort observed failure rate (same approximation)
  - BH-adjusted p across the 3 contrasts at q=0.10 (from engine.btc_override_ledger._bh)

Claim-matching rule: an action row matches a claim whose surface field equals the
action's surface AND whose claim window (timestamp → check_by) contains or
immediately precedes the action ts.  Unmatched actions are counted and reported;
never silently dropped.

BH is IMPORTED from engine.btc_override_ledger — never re-implemented.
The family size is fixed at 3 (= declared budget) for BH correction.
"""
from __future__ import annotations

import json
import logging
import math
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
WILSON_FLOOR = 25       # minimum graded operator ACTIONS per contrast for any stats
FDR_Q = 0.10            # Benjamini-Hochberg FDR level
_ACTION_HIT_THRESHOLD = 0.5   # mean-claim-hit >= threshold → per-action hit=True

_DEFAULT_LEDGER = Path("data") / "operator" / "action_ledger.jsonl"
_CLAIMS_PATH = Path("data") / "qledger" / "claims.jsonl"
_GRADES_PATH = Path("data") / "qledger" / "grades.jsonl"
_TRIAL_LEDGER_PATH = Path("data") / "trial_ledger.jsonl"

VALID_ACTIONS = frozenset({"acted", "dismissed", "overrode", "snoozed"})

# ---------------------------------------------------------------------------
# Import BH from btc_override_ledger BY IMPORT — never re-impl
# _bootstrap_null is intentionally NOT imported: it is a BTC ATH-gated
# price-path simulator with no mapping to operator-action grading.
# At the floor, contrasts publish Wilson intervals per the PR-0 ratification.
# ---------------------------------------------------------------------------
try:
    from engine.btc_override_ledger import _bh  # noqa: F401
    _BH_IMPORTED = True
except ImportError:
    log.warning("operator_grading: could not import _bh from "
                "engine.btc_override_ledger — stats will be unavailable")
    _bh = None  # type: ignore[assignment]
    _BH_IMPORTED = False


# ---------------------------------------------------------------------------
# Wilson CI — import canonical helper
# ---------------------------------------------------------------------------
try:
    from engine.grading_stats import wilson_ci as _wilson_ci
except ImportError:
    def _wilson_ci(k: int, n: int, z: float = 1.96):  # type: ignore[misc]
        """Fallback Wilson score interval when engine.grading_stats is unavailable."""
        if n == 0:
            return None
        p = k / n
        denom = 1.0 + z * z / n
        centre = (p + z * z / (2 * n)) / denom
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
        lo = max(0.0, centre - half)
        hi = min(1.0, centre + half)
        return (round(lo, 3), round(hi, 3))


# ---------------------------------------------------------------------------
# Exact two-sided binomial p-value
# ---------------------------------------------------------------------------
def _binom_pvalue(k: int, n: int, p0: float) -> float:
    """Exact two-sided binomial p-value for k successes in n trials under null p=p0.

    Uses scipy.stats.binomtest when available; falls back to a pure-Python
    implementation (summation of binom pmf terms at least as extreme as observed).
    """
    try:
        from scipy.stats import binomtest
        return float(binomtest(k, n, p0, alternative="two-sided").pvalue)
    except Exception:  # noqa: BLE001
        # Pure-Python fallback: sum all P(X=j) where P(X=j) <= P(X=k)
        # under Binomial(n, p0)
        def _log_binom(nn: int, kk: int) -> float:
            return (math.lgamma(nn + 1)
                    - math.lgamma(kk + 1)
                    - math.lgamma(nn - kk + 1))

        if n == 0:
            return 1.0
        log_p0 = math.log(p0) if p0 > 0 else -1e300
        log_q0 = math.log(1 - p0) if p0 < 1 else -1e300

        def _pmf(j: int) -> float:
            return math.exp(_log_binom(n, j) + j * log_p0 + (n - j) * log_q0)

        p_obs = _pmf(k)
        total = sum(_pmf(j) for j in range(n + 1) if _pmf(j) <= p_obs + 1e-12)
        return min(1.0, total)


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

    Known approximation: the 30-day tolerance may admit marginally late pairings.
    This is documented in the module docstring and in the artifact meta field
    'match_window_note'.

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
# Per-action outcome aggregation
# ---------------------------------------------------------------------------
def _action_hit(
    action: dict,
    matched_ids: list[str],
    grades: dict[str, list[dict]],
) -> bool | None:
    """Compute the single per-action hit boolean.

    Per-action aggregation rule (BINDING):
      Mean the hit values across all graded matched claims for this action;
      threshold at _ACTION_HIT_THRESHOLD (0.5) to produce a boolean.
      If no matched claims have a grade, returns None (ungraded — not counted
      toward the floor).
    """
    hit_values: list[float] = []
    for cid in matched_ids:
        grade_rows = grades.get(cid, [])
        if not grade_rows:
            continue
        best_grade = max(grade_rows, key=lambda r: r.get("horizon_d", 0))
        hit = best_grade.get("hit")
        if hit is None:
            continue
        hit_values.append(float(bool(hit)))

    if not hit_values:
        return None
    mean_hit = sum(hit_values) / len(hit_values)
    return mean_hit >= _ACTION_HIT_THRESHOLD


def _action_direction_hit(
    action: dict,
    matched_ids: list[str],
    grades: dict[str, list[dict]],
) -> bool | None:
    """Compute per-action C1 accuracy boolean.

    Aggregates matched-claim hit values to a single per-action boolean per the
    per-action aggregation rule, then computes C1 accuracy: correct if
    (direction==1 and per-action-hit) or (direction==-1 and not per-action-hit).
    Returns None if direction is indeterminate or no graded claims exist.
    """
    direction = _parse_direction(action.get("direction_note", ""))
    if direction is None:
        return None
    action_hit = _action_hit(action, matched_ids, grades)
    if action_hit is None:
        return None
    if direction == 1:
        return action_hit
    else:  # direction == -1
        return not action_hit


# ---------------------------------------------------------------------------
# Contrast computation
# ---------------------------------------------------------------------------
def _compute_contrasts(
    actions: list[dict],
    claims: dict[str, dict],
    grades: dict[str, list[dict]],
) -> dict:
    """Match actions to claims/grades and compute the three pre-declared contrasts.

    Per-action aggregation: each action contributes at most ONE observation per
    contrast.  Multi-claim actions are aggregated before counting.  The floor
    (n>=25) is over distinct graded actions, not over matched claim count.

    Returns a dict with:
      n_actions_total      : total action rows loaded
      n_unmatched_actions  : actions with no matching claim (reported, not dropped)
      n_matched_actions    : actions with >=1 matching claim
      contrasts            : dict with C1, C2, C3 entries
    """
    n_total = len(actions)
    n_unmatched = 0
    n_matched = 0

    # Per-contrast accumulators (one entry per distinct action, after aggregation)
    # C1: overrode accuracy — per-action correct bool
    c1_graded: list[bool] = []
    c1_overrode_total = 0

    # C2/C3: dismissed vs acted per-action hit bools
    c2_dismissed_graded: list[bool] = []
    c2_acted_graded: list[bool] = []
    n_dismissed_actions = 0
    n_acted_actions = 0

    for action in actions:
        matched_ids = _match_action_to_claims(action, claims)
        if not matched_ids:
            n_unmatched += 1
            continue

        n_matched += 1
        action_type = action.get("action", "")

        # C1: overrode actions
        if action_type == "overrode":
            c1_overrode_total += 1
            correct = _action_direction_hit(action, matched_ids, grades)
            if correct is not None:
                c1_graded.append(correct)

        # C2/C3: dismissed vs acted
        if action_type == "dismissed":
            n_dismissed_actions += 1
            ah = _action_hit(action, matched_ids, grades)
            if ah is not None:
                c2_dismissed_graded.append(ah)
        elif action_type == "acted":
            n_acted_actions += 1
            ah = _action_hit(action, matched_ids, grades)
            if ah is not None:
                c2_acted_graded.append(ah)

    # Also count unmatched action types (for accruing state reporting)
    for action in actions:
        atype = action.get("action", "")
        if not _match_action_to_claims(action, claims):
            if atype == "dismissed":
                n_dismissed_actions += 1
            elif atype == "acted":
                n_acted_actions += 1
            elif atype == "overrode":
                c1_overrode_total += 1

    # Build contrast results
    contrasts = {}

    # --- C1: overrode_accuracy ---
    n_c1_graded_actions = len(c1_graded)

    if n_c1_graded_actions < WILSON_FLOOR:
        contrasts["C1_overrode_accuracy"] = {
            "state": "accruing",
            "description": "operator direction vs machine-claim graded outcome at horizon",
            "n_actions": c1_overrode_total,
            "n_matched": n_c1_graded_actions,
            "n_graded": n_c1_graded_actions,
            "floor": WILSON_FLOOR,
        }
    else:
        n_correct = sum(1 for v in c1_graded if v)
        rate = n_correct / n_c1_graded_actions
        wci = _wilson_ci(n_correct, n_c1_graded_actions)
        p_raw = _binom_pvalue(n_correct, n_c1_graded_actions, 0.5)
        contrasts["C1_overrode_accuracy"] = {
            "state": "computed",
            "description": "operator direction vs machine-claim graded outcome at horizon",
            "n_actions": n_c1_graded_actions,
            "n_correct": n_correct,
            "rate": round(rate, 4),
            "wilson_lo": wci[0] if wci else None,
            "wilson_hi": wci[1] if wci else None,
            "null_p": 0.5,
            "p_raw": round(p_raw, 6),
            "p_bh": None,   # filled after BH pass
            "bh_rejected": None,
        }

    # --- C2: dismissed_then_worked ---
    n_dismissed_graded = len(c2_dismissed_graded)
    n_acted_graded = len(c2_acted_graded)

    if n_dismissed_graded < WILSON_FLOOR or n_acted_graded < WILSON_FLOOR:
        contrasts["C2_dismissed_then_worked"] = {
            "state": "accruing",
            "description": "hit rate for dismissed actions vs acted base rate",
            "n_actions": n_dismissed_actions,
            "n_matched": n_dismissed_graded,
            "n_graded": n_dismissed_graded,
            "n_base_actions": n_acted_actions,
            "n_base_matched": n_acted_graded,
            "n_base_graded": n_acted_graded,
            "floor": WILSON_FLOOR,
        }
    else:
        dismissed_hits = sum(1 for v in c2_dismissed_graded if v)
        dismissed_hit_rate = dismissed_hits / n_dismissed_graded
        acted_hit_rate = sum(1 for v in c2_acted_graded if v) / n_acted_graded
        wci = _wilson_ci(dismissed_hits, n_dismissed_graded)
        # C2 null p = acted-cohort observed rate (conditional-null approximation)
        p_raw = _binom_pvalue(dismissed_hits, n_dismissed_graded, acted_hit_rate)
        contrasts["C2_dismissed_then_worked"] = {
            "state": "computed",
            "description": "hit rate for dismissed actions vs acted base rate",
            "n_actions": n_dismissed_graded,
            "n_dismissed_graded": n_dismissed_graded,
            "dismissed_hit_rate": round(dismissed_hit_rate, 4),
            "n_acted_graded": n_acted_graded,
            "acted_hit_rate": round(acted_hit_rate, 4),
            "rate": round(dismissed_hit_rate, 4),
            "wilson_lo": wci[0] if wci else None,
            "wilson_hi": wci[1] if wci else None,
            "null_p": round(acted_hit_rate, 6),
            "null_p_note": (
                "conditional-null approximation: acted-cohort observed rate used "
                "as null p; this is an approximation, not an independent baseline"
            ),
            "p_raw": round(p_raw, 6),
            "p_bh": None,
            "bh_rejected": None,
        }

    # --- C3: acted_then_failed ---
    n_acted_c3 = n_acted_graded
    n_dismissed_c3 = n_dismissed_graded

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
        acted_fails = sum(1 for v in c2_acted_graded if not v)
        acted_fail_rate = acted_fails / n_acted_c3
        dismissed_fail_rate = sum(1 for v in c2_dismissed_graded if not v) / n_dismissed_c3
        wci = _wilson_ci(acted_fails, n_acted_c3)
        # C3 null p = dismissed-cohort observed failure rate (conditional-null approximation)
        p_raw = _binom_pvalue(acted_fails, n_acted_c3, dismissed_fail_rate)
        contrasts["C3_acted_then_failed"] = {
            "state": "computed",
            "description": "failure rate for acted actions vs dismissed base rate",
            "n_actions": n_acted_c3,
            "n_acted_graded": n_acted_c3,
            "acted_fail_rate": round(acted_fail_rate, 4),
            "n_dismissed_graded": n_dismissed_c3,
            "dismissed_fail_rate": round(dismissed_fail_rate, 4),
            "rate": round(acted_fail_rate, 4),
            "wilson_lo": wci[0] if wci else None,
            "wilson_hi": wci[1] if wci else None,
            "null_p": round(dismissed_fail_rate, 6),
            "null_p_note": (
                "conditional-null approximation: dismissed-cohort observed failure rate "
                "used as null p; this is an approximation, not an independent baseline"
            ),
            "p_raw": round(p_raw, 6),
            "p_bh": None,
            "bh_rejected": None,
        }

    # --- BH pass across computed contrasts ---
    computed_p_raws = {
        k: v["p_raw"]
        for k, v in contrasts.items()
        if v.get("state") == "computed" and v.get("p_raw") is not None
    }
    if computed_p_raws and _bh is not None:
        bh_results = _bh(computed_p_raws, q=FDR_Q, m=FDR_BUDGET)
        for k, bh in bh_results.items():
            contrasts[k]["p_bh"] = bh.get("p_bh")
            contrasts[k]["bh_rejected"] = bh.get("significant_at_q")

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

    Keyword sets (case-insensitive):
      Positive (return 1): agree, long, buy, bullish, up, confirm, yes
      Negative (return -1): disagree, short, sell, bearish, down, reject, no
      Both or neither: return None (ambiguous / indeterminate)
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
        "ledger_file": ledger_path.name,
        "ledger_present": ledger_present,
        "n_actions_total": result["n_actions_total"],
        "n_unmatched_actions": result["n_unmatched_actions"],
        "n_matched_actions": result["n_matched_actions"],
        "n_claims_loaded": len(claims),
        "n_grades_loaded": sum(len(v) for v in grades.values()),
        "contrasts": result["contrasts"],
        "authority": (
            "MONITORING ONLY — display-only until Wilson floor "
            f"(n>={WILSON_FLOOR} graded operator actions per contrast) is reached. "
            "Zero allocation authority. Nothing in sizing/allocation reads this file."
        ),
        "meta": {
            "per_action_aggregation": (
                "Each action contributes exactly one observation per contrast. "
                "Multi-claim actions: mean hit across graded claims, "
                f"thresholded at {_ACTION_HIT_THRESHOLD} for hit-style booleans."
            ),
            "match_window_note": (
                "30-day 'immediately precedes' tolerance on claim check_by is a "
                "known approximation that may admit marginally late action-claim pairings."
            ),
            "dead_name_coverage_pct": None,
            "dead_name_coverage_note": "not_applicable_operator_ledger",
            "conditional_null_approximation": (
                "C2/C3 null p uses the comparison cohort's observed rate as the null; "
                "this is a conditional-null approximation, not an independent baseline."
            ),
        },
    }

    return out
