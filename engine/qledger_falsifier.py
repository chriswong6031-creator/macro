"""engine.qledger_falsifier — Falsifier auto-evaluation for qledger claims (TIL W6, PR-H).

Judge #4: closes the pre-registration loop.

qledger claims carry `falsifier` (a dict with text + check spec) and `check_by`
(the date at which the check should be evaluated) that NOTHING currently evaluates
(verified: grade_qledger.py grades price returns only).

This engine reads claims.jsonl, finds claims whose:
  1. check_by has arrived (check_by <= today)
  2. falsifier is a non-null dict with a `check` subdict
  3. not already evaluated in falsifier_evaluations.jsonl for this claim_id

And evaluates the `check` spec, emitting one of:
  FALSIFIER_TRIPPED  — the falsifying condition was observed (claim was wrong)
  CONFIRMED          — the check passed (claim survived)
  UNVERIFIABLE       — missing data / unparseable spec / "soft" kind

Output: data/qledger/falsifier_evaluations.jsonl (append-only, one row per
  claim_id evaluated in this run). Parallel artifact — NEVER modifies
  claims.jsonl or grades.jsonl.

Supported check kinds:
  rel_return   — price return of subject_ticker vs benchmark (vs field) over
                 horizon_d. subject_ticker in data/yahoo/<T>.parquet required.
                 op in {">", "<", ">=", "<="}. threshold is a float fraction.
  soft         — UNVERIFIABLE by construction (check.reason carries the reason).
  (unknown)    — UNVERIFIABLE.

Cap per-run evaluations at MAX_PER_RUN (default 2000) with a cursor stored in
`last_processed_idx` in the artifact so the first run over 10.9k claims does not
blow the nightly budget. Progress logged.

Authority: is_context_only=True, all promotion flags False.
No LLM calls. Tolerant reader (missing input -> UNVERIFIABLE, not crash).
Always exits 0.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)


from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARTIFACT_ID = "qledger-falsifier-evaluations"
OUTPUT_PATH = ("data", "qledger", "falsifier_evaluations.jsonl")

MAX_PER_RUN = 2000  # cap per-run evaluations to protect nightly budget

OUTCOME_TRIPPED = "FALSIFIER_TRIPPED"
OUTCOME_CONFIRMED = "CONFIRMED"
OUTCOME_UNVERIFIABLE = "UNVERIFIABLE"

AUTHORITY_BLOCK: dict[str, Any] = {
    "is_context_only": True,
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "tier": "shadow",
    "forbidden_uses": [
        "ranking", "sizing", "alert_escalation", "board_ordering",
        "mastermind_arming", "scored_path",
    ],
}


# ---------------------------------------------------------------------------
# Price helpers (PIT-safe, reuse foresight_grader pattern)
# ---------------------------------------------------------------------------

def _closes(ticker: str, root: Path) -> pd.Series | None:
    """Read close series from data/yahoo/<ticker>.parquet."""
    p = root / "data" / "yahoo" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    col = "close" if "close" in df.columns else (
        "close_price" if "close_price" in df.columns else None
    )
    if col is None:
        return None
    s = df[col].dropna()
    if not len(s):
        return None
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _price_at_or_after(s: pd.Series | None, target: pd.Timestamp,
                       window_days: int = 5) -> float | None:
    """First close on or after target, within window_days. None if unavailable."""
    if s is None or s.empty:
        return None
    within = s[(s.index >= target) & (s.index <= target + pd.Timedelta(days=window_days))]
    if within.empty:
        return None
    return float(within.iloc[0])


def _price_at_or_before(s: pd.Series | None, target: pd.Timestamp,
                        window_days: int = 5) -> float | None:
    """Last close on or before target, within window_days prior. None if unavailable."""
    if s is None or s.empty:
        return None
    within = s[(s.index >= target - pd.Timedelta(days=window_days)) & (s.index <= target)]
    if within.empty:
        return None
    return float(within.iloc[-1])


# ---------------------------------------------------------------------------
# Evaluators per check kind
# ---------------------------------------------------------------------------

def _eval_rel_return(check: dict, asof: str, check_by: str, root: Path) -> tuple[str, str]:
    """Evaluate a rel_return check spec.

    Returns (outcome, detail).
    FALSIFIER_TRIPPED if op(realized_excess, threshold) is True (the falsifier fired).
    CONFIRMED if the check condition was NOT met (thesis survived).
    UNVERIFIABLE if price data absent or incomplete.

    Logic:
      - Fetch subject_ticker close series from data/yahoo/
      - Fetch vs (benchmark) close series
      - Compute realized relative return from asof+1 to check_by
      - Apply op + threshold
    """
    subject = str(check.get("subject_ticker") or "").strip()
    vs = str(check.get("vs") or "SPY").strip()
    op = str(check.get("op") or "").strip()
    try:
        threshold = float(check["threshold"])
    except (KeyError, TypeError, ValueError):
        return OUTCOME_UNVERIFIABLE, "missing or non-numeric threshold"

    if not subject:
        return OUTCOME_UNVERIFIABLE, "missing subject_ticker"
    if op not in ("<", ">", "<=", ">="):
        return OUTCOME_UNVERIFIABLE, f"unknown op: {op!r}"

    subject_s = _closes(subject, root)
    bench_s = _closes(vs, root)

    if subject_s is None:
        return OUTCOME_UNVERIFIABLE, f"no price data for subject {subject!r}"
    if bench_s is None:
        return OUTCOME_UNVERIFIABLE, f"no price data for benchmark {vs!r}"

    # Entry: first close AFTER asof (next-bar convention, PIT-safe)
    asof_ts = pd.Timestamp(asof)
    check_by_ts = pd.Timestamp(check_by)

    # Use start = first close strictly AFTER asof (next-bar)
    after_asof = subject_s[subject_s.index > asof_ts]
    if after_asof.empty:
        return OUTCOME_UNVERIFIABLE, f"no close after asof {asof!r} for {subject!r}"
    entry_ts = after_asof.index[0]

    # Exit: first close at/near check_by (within 5 trading days)
    p_sub_entry = _price_at_or_after(subject_s, entry_ts, window_days=0)
    p_bench_entry = _price_at_or_after(bench_s, entry_ts, window_days=0)
    p_bench_exit = _price_at_or_before(bench_s, check_by_ts, window_days=5)

    # Fetch subject exit price (separate series read for PIT safety)
    sub_exit_s = _closes(subject, root)
    p_sub_exit2 = _price_at_or_before(sub_exit_s, check_by_ts, window_days=5)

    if any(p is None for p in (p_sub_entry, p_sub_exit2, p_bench_entry, p_bench_exit)):
        return OUTCOME_UNVERIFIABLE, (
            f"missing price at entry/exit: "
            f"sub_entry={p_sub_entry}, sub_exit={p_sub_exit2}, "
            f"bench_entry={p_bench_entry}, bench_exit={p_bench_exit}"
        )

    if p_sub_entry <= 0 or p_bench_entry <= 0:
        return OUTCOME_UNVERIFIABLE, "entry price <= 0"

    sub_ret = p_sub_exit2 / p_sub_entry - 1.0
    bench_ret = p_bench_exit / p_bench_entry - 1.0
    excess = sub_ret - bench_ret

    # Apply the check condition: if it evaluates True, the FALSIFIER TRIPPED
    # (the falsifying condition was observed)
    triggered = _apply_op(op, excess, threshold)
    if triggered:
        return (
            OUTCOME_TRIPPED,
            f"falsifier condition met: {subject} excess {excess:.4f} {op} {threshold:.4f} "
            f"(sub_ret={sub_ret:.4f}, bench_ret={bench_ret:.4f})"
        )
    else:
        return (
            OUTCOME_CONFIRMED,
            f"falsifier condition NOT met: {subject} excess {excess:.4f} NOT {op} {threshold:.4f} "
            f"(sub_ret={sub_ret:.4f}, bench_ret={bench_ret:.4f})"
        )


def _apply_op(op: str, value: float, threshold: float) -> bool:
    if op == "<":
        return value < threshold
    if op == ">":
        return value > threshold
    if op == "<=":
        return value <= threshold
    if op == ">=":
        return value >= threshold
    return False


def evaluate_check(check: dict | None, asof: str, check_by: str, root: Path) -> tuple[str, str]:
    """Dispatch to the appropriate evaluator based on check.kind.
    Returns (outcome, detail). Always returns, never raises.
    """
    if check is None or not isinstance(check, dict):
        return OUTCOME_UNVERIFIABLE, "check spec is null or not a dict"

    kind = str(check.get("kind") or "").strip().lower()

    if kind == "rel_return":
        try:
            return _eval_rel_return(check, asof, check_by, root)
        except Exception as e:  # noqa: BLE001
            log.debug("rel_return eval exception: %s", e)
            return OUTCOME_UNVERIFIABLE, f"eval error: {e}"

    if kind == "soft":
        reason = check.get("reason") or "soft check — not machine-evaluable"
        return OUTCOME_UNVERIFIABLE, f"soft check: {reason}"

    return OUTCOME_UNVERIFIABLE, f"unknown check kind: {kind!r}"


# ---------------------------------------------------------------------------
# Claim reading helpers
# ---------------------------------------------------------------------------

def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _load_evaluated_ids(p: Path) -> set[str]:
    """Return set of claim_ids already in the evaluations tape."""
    seen: set[str] = set()
    if not p.exists():
        return seen
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            cid = str(row.get("claim_id") or "")
            if cid:
                seen.add(cid)
        except Exception:  # noqa: BLE001
            continue
    return seen


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def evaluate_falsifiers(
    root: Path,
    today: str | None = None,
    max_per_run: int = MAX_PER_RUN,
    dry_run: bool = False,
) -> dict:
    """Evaluate falsifier check specs for all due claims not yet evaluated.

    Returns a summary dict:
        as_of, n_claims_checked, n_tripped, n_confirmed, n_unverifiable,
        n_skipped_already_done, n_capped (hit the max_per_run limit)
    """
    if today is None:
        today = date.today().isoformat()

    claims_path = root / "data" / "qledger" / "claims.jsonl"
    eval_path = root.joinpath(*OUTPUT_PATH)

    claims = _read_jsonl(claims_path)
    if not claims:
        log.info("qledger_falsifier: claims.jsonl absent — nothing to do")
        return _null_summary(today, "claims.jsonl absent or empty")

    already_done = _load_evaluated_ids(eval_path)
    log.info("qledger_falsifier: %d total claims, %d already evaluated",
             len(claims), len(already_done))

    # Filter to due-and-not-done claims
    due: list[dict] = []
    for c in claims:
        cid = str(c.get("claim_id") or "")
        if cid in already_done:
            continue
        check_by = str(c.get("check_by") or "")
        if not check_by or check_by > today:
            continue
        falsifier = c.get("falsifier")
        if falsifier is None or falsifier == "" or falsifier == "null":
            continue
        if not isinstance(falsifier, dict):
            continue
        check = falsifier.get("check")
        if not isinstance(check, dict):
            # Only text — UNVERIFIABLE but still evaluated
            pass
        due.append(c)

    n_total_due = len(due)
    n_capped = max(0, n_total_due - max_per_run)
    to_eval = due[:max_per_run]

    log.info("qledger_falsifier: %d due claims, evaluating %d (cap=%d, capped=%d)",
             n_total_due, len(to_eval), max_per_run, n_capped)

    n_tripped = n_confirmed = n_unverifiable = 0
    new_rows: list[dict] = []
    ts_now = datetime.now(timezone.utc).isoformat()

    for claim in to_eval:
        cid = str(claim.get("claim_id") or "")
        asof = str(claim.get("asof") or "")
        check_by = str(claim.get("check_by") or "")
        falsifier = claim.get("falsifier", {})
        check = falsifier.get("check") if isinstance(falsifier, dict) else None

        outcome, detail = evaluate_check(check, asof, check_by, root)

        if outcome == OUTCOME_TRIPPED:
            n_tripped += 1
        elif outcome == OUTCOME_CONFIRMED:
            n_confirmed += 1
        else:
            n_unverifiable += 1

        row = {
            "claim_id": cid,
            "as_of": today,
            "check_by": check_by,
            "evaluated_at": ts_now,
            "outcome": outcome,
            "detail": detail,
            "desk": claim.get("desk"),
            "scope": claim.get("scope"),
            "asof_claim": asof,
            "falsifier_text": (falsifier.get("text") if isinstance(falsifier, dict) else None),
            "check_kind": (check.get("kind") if isinstance(check, dict) else None),
            "schema": "qledger.falsifier_eval.v1",
        }
        new_rows.append(row)

    if new_rows and not dry_run:
        if _ledger_advance_enabled():
            eval_path.parent.mkdir(parents=True, exist_ok=True)
            with eval_path.open("a", encoding="utf-8") as fh:
                for row in new_rows:
                    fh.write(json.dumps(row, separators=(",", ":")) + "\n")
            log.info("qledger_falsifier: wrote %d evaluations to %s", len(new_rows), eval_path)
        else:
            log.debug(
                "qledger_falsifier.evaluate_falsifiers: write skipped "
                "(COLLECT_LANE != nightly)"
            )
    elif new_rows:
        log.info("qledger_falsifier: dry_run — would write %d evaluations", len(new_rows))

    summary = {
        "as_of": today,
        "n_claims_checked": len(to_eval),
        "n_tripped": n_tripped,
        "n_confirmed": n_confirmed,
        "n_unverifiable": n_unverifiable,
        "n_skipped_already_done": len(already_done),
        "n_total_due": n_total_due,
        "n_capped": n_capped,
        "authority": AUTHORITY_BLOCK,
        "schema": "qledger.falsifier_eval.v1",
        "note": (
            "UNVERIFIABLE outcomes printed, not hidden. "
            f"Cap={max_per_run}/run; cursor advances each nightly run until all due claims "
            f"are evaluated. Soft checks are always UNVERIFIABLE. "
            f"n_capped={n_capped} due claims deferred to next run."
        ),
    }
    return summary


def _null_summary(today: str, reason: str) -> dict:
    return {
        "as_of": today,
        "n_claims_checked": 0,
        "n_tripped": 0,
        "n_confirmed": 0,
        "n_unverifiable": 0,
        "n_skipped_already_done": 0,
        "n_total_due": 0,
        "n_capped": 0,
        "authority": AUTHORITY_BLOCK,
        "schema": "qledger.falsifier_eval.v1",
        "note": f"Honest null — {reason}.",
    }
