"""scripts/build_factor_deescalation_shadow.py — Dark A3 shadow-ledger scaffold.

LANE: §D PR-5, RUL-NW6 (NW_INTEGRATION_ADJUDICATION_BY_FABLE.md)

PURPOSE
-------
Dark scaffold for the factor de-escalation shadow ledger (A3 lane).

RUL-NW6 ACTIVATION FLOOR (non-negotiable, pre-committed)
---------------------------------------------------------
Minimum 25 episode-clustered would-have-fired events spanning ≥3 calendar months
(EI R6 convention), graded at the relevant hypothesis's own falsifier, THEN an
explicit Fable ruling before any clamp wiring.

This script stays DARK (writes nothing) until ALL of the following are true:
  1. A GATE-PASSED verdict file exists for H2 or H4:
       research/factor_intelligence/H2_VERDICT.md  (or H4_VERDICT.md)
     The file must contain a line matching '**Verdict:** GATE-PASSED'.
  2. An explicit Fable activation ruling has been issued.

TODAY'S REALITY: No GATE-PASSED verdict exists. Script prints honest status
and exits 0 without writing anything.

ACTIVATION TARGET (A3 clamp targets)
--------------------------------------
When activated (after a GATE-PASSED verdict + Fable ruling), this script
appends would-have-fired rows to:
  data/reflexes/factor_deescalation_shadow/firings.jsonl

Row schema (docket §11, pre-committed — DO NOT change without Fable ruling):
  ticker           : str   — ticker symbol
  as_of            : str   — ISO date YYYY-MM-DD (the fire date)
  primitive        : str   — which factor primitive triggered (e.g. 'alibi_share_20d')
  proposed_action  : str   — what the clamp would do (A3 clamp targets only)
  original_surface : str   — which display surface showed the original verdict
  original_verdict : str   — the verdict on that surface (e.g. 'tension', 'note')
  proposed_verdict : str   — what de-escalation would produce
  falsifier        : str   — the pre-registered falsifier text (from PREREGISTRATION.md)
  horizon_d        : int   — horizon in trading days for the falsifier
  gate_reference   : str   — which GATE-PASSED verdict unlocked this row

Idempotence: same-day re-runs must not duplicate rows.
  Key: (as_of, ticker, primitive) — composite key for deduplication.

A3 CLAMP TARGETS (ALLOWED targets; everything else is FORBIDDEN FOREVER)
-------------------------------------------------------------------------
  - altdata/narrative _reconcile displays
  - display chips (read-only display updates)

FORBIDDEN SURFACES (banned forever, even after activation):
  - board_ordering / us_standouts writes
  - top_setups
  - push_floor
  - alert escalation / alert_triage

USAGE
-----
  python -m scripts.build_factor_deescalation_shadow [--root PATH] [--as-of YYYY-MM-DD]

Exit codes
----------
  0 : Script completed (dark scaffold: no-op if no GATE-PASSED verdict).
  0 : Rows appended to shadow ledger (post-activation only).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCHEMA_VERSION = "factor_deescalation_shadow.v1"

# GATE-PASSED verdict files — one per hypothesis that can unlock this lane.
# The file must contain a line matching '**Verdict:** GATE-PASSED'.
_VERDICT_FILES = [
    "research/factor_intelligence/H2_VERDICT.md",
    "research/factor_intelligence/H4_VERDICT.md",
]
_GATE_PASSED_PATTERN = "**Verdict:** GATE-PASSED"

# Output path for shadow ledger rows.
_SHADOW_FIRINGS_REL = "data/reflexes/factor_deescalation_shadow/firings.jsonl"

# Required fields for the §11 row schema (pre-committed; do not add/remove
# without an explicit Fable ruling).
_ROW_FIELDS = (
    "ticker",
    "as_of",
    "primitive",
    "proposed_action",
    "original_surface",
    "original_verdict",
    "proposed_verdict",
    "falsifier",
    "horizon_d",
    "gate_reference",
)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _repo_root(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent


def _shadow_firings_path(repo: Path) -> Path:
    return repo / _SHADOW_FIRINGS_REL


# ---------------------------------------------------------------------------
# GATE-PASSED check
# ---------------------------------------------------------------------------


def _find_gate_passed_verdict(repo: Path) -> str | None:
    """Return the verdict file path (relative to repo) if a GATE-PASSED verdict
    is found, or None if no such file exists.

    We look for lines containing exactly the pattern '**Verdict:** GATE-PASSED'
    (the P3 deliverable naming convention from the masterplan §7).
    """
    for rel in _VERDICT_FILES:
        p = repo / rel
        if not p.exists():
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in content.splitlines():
            if _GATE_PASSED_PATTERN in line:
                return rel
    return None


# ---------------------------------------------------------------------------
# Idempotence helpers
# ---------------------------------------------------------------------------


def _load_existing_keys(path: Path) -> set[tuple[str, str, str]]:
    """Load (as_of, ticker, primitive) composite keys from existing ledger."""
    keys: set[tuple[str, str, str]] = set()
    if not path.exists():
        return keys
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
                as_of = str(rec.get("as_of") or "")
                ticker = str(rec.get("ticker") or "")
                primitive = str(rec.get("primitive") or "")
                if as_of and ticker and primitive:
                    keys.add((as_of, ticker, primitive))
            except (json.JSONDecodeError, KeyError):
                pass
    except OSError as exc:
        log.warning("build_factor_deescalation_shadow: could not read %s — %s", path, exc)
    return keys


def _validate_row(row: dict[str, Any]) -> None:
    """Raise ValueError if row is missing any required §11 field."""
    missing = [f for f in _ROW_FIELDS if f not in row]
    if missing:
        raise ValueError(f"Shadow row missing required §11 fields: {missing}")
    # Reject forbidden field names that would signal rank/score/recommendation
    forbidden_names = {"rank", "score", "recommendation"}
    present_forbidden = forbidden_names & set(row.keys())
    if present_forbidden:
        raise ValueError(
            f"Shadow row contains forbidden field names: {sorted(present_forbidden)} — "
            "rows must never contain rank/score/recommendation"
        )


def _append_row(path: Path, row: dict[str, Any]) -> None:
    """Append one JSON row to the shadow ledger."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, allow_nan=False) + "\n")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def build_factor_deescalation_shadow(
    root: Path | str | None = None,
    as_of_date: str | None = None,
    _synthetic_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the dark shadow-ledger scaffold.

    Returns a status dict describing what happened. Never raises.

    Parameters
    ----------
    root          : Repo root path (default: parent of scripts/).
    as_of_date    : ISO date YYYY-MM-DD (default: today UTC).
    _synthetic_rows : Internal-only parameter for testing — if provided AND a
                      GATE-PASSED verdict exists, these rows are written instead
                      of any real data source.  Not for production use.
    """
    repo = _repo_root(root)
    if as_of_date is None:
        as_of_date = datetime.now(timezone.utc).date().isoformat()

    # ------------------------------------------------------------------
    # Step 1: Check for a GATE-PASSED verdict.
    # ------------------------------------------------------------------
    gate_ref = _find_gate_passed_verdict(repo)
    if gate_ref is None:
        msg = (
            "build_factor_deescalation_shadow: DARK — no GATE-PASSED verdict found "
            f"(checked: {_VERDICT_FILES}). "
            "Writing nothing. Activate after H2/H4 GATE-PASSED + explicit Fable ruling (RUL-NW6)."
        )
        print(msg)
        log.info(msg)
        return {
            "status": "dark",
            "gate_passed": False,
            "gate_reference": None,
            "rows_written": 0,
            "message": msg,
        }

    # ------------------------------------------------------------------
    # Step 2: Gate is PASSED — append would-have-fired rows.
    # (In production, rows would be sourced from the factor panel and
    # the factor_intelligence_state artifact.  Today this body only
    # fires from tests via _synthetic_rows; real production sourcing
    # requires a separate Fable ruling defining the row-generation logic
    # once the activation floor is met.)
    # ------------------------------------------------------------------
    shadow_path = _shadow_firings_path(repo)
    existing_keys = _load_existing_keys(shadow_path)

    candidate_rows: list[dict[str, Any]] = _synthetic_rows or []
    n_written = 0
    n_skipped = 0

    for row in candidate_rows:
        try:
            _validate_row(row)
        except ValueError as exc:
            log.warning("build_factor_deescalation_shadow: skipping invalid row — %s", exc)
            n_skipped += 1
            continue

        key = (str(row.get("as_of") or ""), str(row.get("ticker") or ""), str(row.get("primitive") or ""))
        if key in existing_keys:
            n_skipped += 1
            continue

        try:
            _append_row(shadow_path, row)
            existing_keys.add(key)
            n_written += 1
        except OSError as exc:
            log.warning("build_factor_deescalation_shadow: failed to append row %s — %s", key, exc)

    result: dict[str, Any] = {
        "status": "active" if n_written > 0 or not candidate_rows else "active_no_new",
        "gate_passed": True,
        "gate_reference": gate_ref,
        "rows_written": n_written,
        "rows_skipped": n_skipped,
        "as_of": as_of_date,
    }
    log.info(
        "build_factor_deescalation_shadow: gate_ref=%s rows_written=%d rows_skipped=%d",
        gate_ref, n_written, n_skipped,
    )
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _main() -> None:
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [build_factor_deescalation_shadow] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description=(
            "Dark A3 shadow-ledger scaffold (RUL-NW6). "
            "Writes nothing unless a GATE-PASSED verdict file exists."
        )
    )
    parser.add_argument("--root", default=None, help="Repo root path")
    parser.add_argument("--as-of", default=None, dest="as_of", help="ISO date YYYY-MM-DD")
    args = parser.parse_args()

    result = build_factor_deescalation_shadow(root=args.root, as_of_date=args.as_of)
    print(json.dumps(result, allow_nan=False))
    sys.exit(0)


if __name__ == "__main__":
    _main()
