"""Nightly grader for the foresight policy-calendar forward ledger (PR-A2).

End-of-collect step.  For every row in
data/foresight/policy_calendar_ledger.jsonl whose next_comment_close_date has
PASSED, checks whether the predicted comment-close event actually appears in
data/federal_register/documents.parquet for that theme/basket_id.

Grade definition (date-accuracy check):
  accurate   : the federal_register store has >= 1 document for this
               basket_id (theme) with comments_close_on == next_comment_close_date.
  inaccurate : no such document exists after the date has passed (the
               predicted close date was wrong, cancelled, or extended).
  pending    : next_comment_close_date has not passed yet.

Writes graded_date (ISO date string) and accurate (bool | null) back into each
row of the JSONL file.  IDEMPOTENT: skips rows that already have graded_date.
SINGLE-WRITER: called only from scripts/collect.py end-of-collect block,
  nightly lane only (COLLECT_LANE=nightly gate).  asia-close / weekly /
  intl_etf lanes are no-ops so the ledger is never advanced intraday.
NEVER RAISES: wrapped entirely; non-fatal.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)


def _ledger_path(root: Path) -> Path:
    return root / "data" / "foresight" / "policy_calendar_ledger.jsonl"


def _fed_reg_path(root: Path) -> Path:
    return root / "data" / "federal_register" / "documents.parquet"


def grade_matured_rows(root: Path | None = None) -> int:
    """Grade matured, ungraded rows.  Returns count of newly graded rows."""
    if root is None:
        root = Path(__file__).resolve().parent.parent

    p = _ledger_path(root)
    if not p.exists():
        return 0

    try:
        lines = p.read_text().splitlines()
        rows = [json.loads(l) for l in lines if l.strip()]
    except Exception as e:  # noqa: BLE001
        log.warning("grade_policy_calendar: ledger read failed: %s", e)
        return 0

    today = date.today()

    # Identify matured + ungraded rows
    to_grade = [
        (i, r) for i, r in enumerate(rows)
        if r.get("next_comment_close_date")
        and r["next_comment_close_date"] < today.isoformat()
        and r.get("graded_date") is None
    ]
    if not to_grade:
        log.debug("grade_policy_calendar: no matured ungraded rows (total=%d)", len(rows))
        return 0

    # Load federal_register documents once
    fr_path = _fed_reg_path(root)
    if not fr_path.exists():
        log.warning("grade_policy_calendar: federal_register/documents.parquet absent; skipping")
        return 0

    try:
        import pandas as pd  # noqa: PLC0415
        fr = pd.read_parquet(fr_path, columns=["basket_id", "comments_close_on"])
        # Build a set of (basket_id, comments_close_on) for fast lookup
        fr = fr.dropna(subset=["basket_id", "comments_close_on"])
        known_closes: set[tuple[str, str]] = set(
            zip(fr["basket_id"].astype(str), fr["comments_close_on"].astype(str))
        )
    except Exception as e:  # noqa: BLE001
        log.warning("grade_policy_calendar: federal_register load failed: %s", e)
        return 0

    n_new = 0
    graded_today = today.isoformat()
    for idx, row in to_grade:
        theme = row.get("theme", "")
        close_date = row["next_comment_close_date"]
        accurate = (theme, close_date) in known_closes
        rows[idx]["graded_date"] = graded_today
        rows[idx]["accurate"] = accurate
        n_new += 1

    if n_new:
        try:
            p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            log.info("grade_policy_calendar: graded %d rows (total=%d)", n_new, len(rows))
        except Exception as e:  # noqa: BLE001
            log.warning("grade_policy_calendar: ledger write failed: %s", e)
            return 0

    return n_new


def run_as_collect_step() -> None:
    """End-of-collect hook — must never raise."""
    try:
        n = grade_matured_rows()
        log.debug("grade_policy_calendar collect step: %d newly graded", n)
    except Exception as exc:  # noqa: BLE001
        log.error("[grade_policy_calendar] step crashed (non-fatal): %s", exc)
