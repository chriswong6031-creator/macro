"""scripts/grade_thematic.py — TIL W6 (PR-H) grading pack orchestrator.

Three stages run sequentially, all tolerant (failure = honest null + continue):

  Stage 1 — Crowd-arrival lead-lag grader (engine/foresight_leadlag.py)
    FIRST appends today's per-theme attention rows to
    data/foresight/earliness_log.jsonl via foresight_earliness (the display
    callers all pass write_log=False, so this call is the log's sole nightly
    advancer — without it the log never accrues and the grader below grades
    an empty tape forever).
    THEN reads the log, computes signed lead-days between flag date and
    attention leg crossings.
    Writes data/foresight/earliness_grades.json (non-append; stamped).

  Stage 2 — Placebo tape (engine/theme_placebo.py)
    On each new non-WATCH foresight flag: appends K=3 random peer themes +
    1 time-shifted variant to data/foresight/theme_placebo_tape.jsonl
    (append-only; deduped).

  Stage 3 — Falsifier auto-evaluation (engine/qledger_falsifier.py)
    Evaluates qledger claims whose check_by has arrived.
    Appends FALSIFIER_TRIPPED / CONFIRMED / UNVERIFIABLE rows to
    data/qledger/falsifier_evaluations.jsonl (append-only; capped).

run_stage(root) contract (TIL PR-0): W1/W2/W3 optional stages expose this
symbol. W6 is NOT an optional stage (it has its own daily.yml step and
dag.yml entry), but exposes run_stage() for parity and testability.

Daily.yml position: AFTER build_thematic_state (AFTER, non-fatal, engine lane).
Dag.yml: single new step grade_thematic (engine lane, after build_thematic_state).

House laws:
  - exit 0 always
  - no LLM calls
  - no scored-path consumers
  - authority block on every artifact: is_context_only=True, all flags False
  - envelope.stamp() on JSON artifact (earliness_grades.json)
  - atomic writes (write to .tmp then rename)
  - append-only tapes for JSONL outputs
  - no "validated" in user-facing text
  - EN/ZH data strings where surfaced; no translated title= attributes
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("grade_thematic")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically (write .tmp then rename) so a crash mid-write
    never leaves a half-written file on disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
                   encoding="utf-8")
    tmp.rename(path)


# ---------------------------------------------------------------------------
# Stage 1 — Crowd-arrival lead-lag grader
# ---------------------------------------------------------------------------

def _append_attention_log(root: Path) -> None:  # noqa: ARG001 — root kept for stage-signature parity
    """Append today's per-theme attention rows to data/foresight/earliness_log.jsonl.

    Producer half of stage 1. compute_foresight_earliness is the log's only
    writer, but every display caller (foresight_score/sizing/convergence)
    passes write_log=False — until this call was wired (2026-07-11) the log
    was NEVER written and the grader graded an empty tape every night
    (n_pending == n_flags forever). This script runs only in the nightly
    engine lane, so the forward ledger advances here (nightly-sole-advancer
    law). Idempotent: the append dedupes by (theme, asof).

    The log path resolves through lib.config.data_dir() (same as every leg
    the engine reads), not through --root; in production both are the repo
    checkout. Tolerant: failure logs a warning and grading proceeds against
    whatever log exists.
    """
    from engine.foresight_earliness import compute_foresight_earliness

    log.info("[W6 stage1] appending attention rows to earliness_log...")
    try:
        payload = compute_foresight_earliness(write_log=True)
        n_themes = len((payload or {}).get("themes") or {})
        log.info("[W6 stage1] attention append done (themes=%s)", n_themes)
    except Exception as exc:  # noqa: BLE001
        log.warning("[W6 stage1] attention log append failed (non-fatal, "
                    "grading proceeds on existing log): %s", exc)


def _stage1_lead_lag(root: Path) -> None:
    """Append today's attention rows, then compute earliness grades and
    write data/foresight/earliness_grades.json."""
    from engine.foresight_leadlag import compute_earliness_grades, ARTIFACT_ID, OUTPUT_PATH

    _append_attention_log(root)

    log.info("[W6 stage1] computing earliness grades...")
    try:
        artifact = compute_earliness_grades(root)
    except Exception as exc:  # noqa: BLE001
        log.error("[W6 stage1] compute_earliness_grades failed: %s", exc)
        artifact = {
            "as_of": None,
            "status": "error",
            "n_flags": 0,
            "n_pending": 0,
            "n_legs_arrived_total": 0,
            "authority": {
                "is_context_only": True,
                "may_rank": False,
                "may_gate": False,
                "may_size": False,
                "may_escalate": False,
            },
            "stale_legs": [f"stage1 compute error: {exc}"],
            "pooled_summary": None,
            "flag_grades": [],
            "schema": "foresight.earliness_grades.v1",
            "note": f"Error in stage 1: {exc}",
        }

    # Stamp with envelope
    try:
        from engine.neuralweb.envelope import stamp
        artifact = stamp(artifact, artifact_id=ARTIFACT_ID)
    except Exception as exc:  # noqa: BLE001
        log.warning("[W6 stage1] envelope stamp failed (non-fatal): %s", exc)

    out_path = root.joinpath(*OUTPUT_PATH)
    try:
        _atomic_write_json(out_path, artifact)
        log.info("[W6 stage1] wrote %s (n_flags=%s, n_pending=%s)",
                 out_path, artifact.get("n_flags"), artifact.get("n_pending"))
    except Exception as exc:  # noqa: BLE001
        log.error("[W6 stage1] write failed: %s", exc)


# ---------------------------------------------------------------------------
# Stage 2 — Placebo tape
# ---------------------------------------------------------------------------

def _stage2_placebo(root: Path) -> None:
    """Append placebo rows for new non-WATCH flags to theme_placebo_tape.jsonl."""
    from engine.theme_placebo import append_placebo_tape

    log.info("[W6 stage2] appending placebo tape...")
    try:
        summary = append_placebo_tape(root)
        log.info("[W6 stage2] placebo: n_new_flags=%s n_new_rows=%s n_watch_skipped=%s",
                 summary.get("n_new_flags"),
                 summary.get("n_new_placebo_rows"),
                 summary.get("n_watch_skipped"))
    except Exception as exc:  # noqa: BLE001
        log.error("[W6 stage2] append_placebo_tape failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Stage 3 — Falsifier auto-evaluation
# ---------------------------------------------------------------------------

def _stage3_falsifier(root: Path) -> None:
    """Evaluate qledger falsifier check specs for all due claims."""
    from engine.qledger_falsifier import evaluate_falsifiers

    log.info("[W6 stage3] evaluating qledger falsifiers...")
    try:
        summary = evaluate_falsifiers(root)
        log.info(
            "[W6 stage3] falsifier: checked=%s tripped=%s confirmed=%s "
            "unverifiable=%s capped=%s",
            summary.get("n_claims_checked"),
            summary.get("n_tripped"),
            summary.get("n_confirmed"),
            summary.get("n_unverifiable"),
            summary.get("n_capped"),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("[W6 stage3] evaluate_falsifiers failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Public run_stage() — TIL PR-0 contract (testability + optional dispatch)
# ---------------------------------------------------------------------------

def run_stage(root: Path) -> None:
    """TIL W6 grading pack. Never raises fatally.

    Runs all three stages (lead-lag grader, placebo tape, falsifier evaluation)
    in order. Each stage is independently try/except'd so a failure in one
    does not block the others.
    """
    _stage1_lead_lag(root)
    _stage2_placebo(root)
    _stage3_falsifier(root)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "TIL W6 (PR-H) grading pack: lead-lag grader + placebo tape + "
            "falsifier auto-evaluation. Always exits 0."
        )
    )
    parser.add_argument(
        "--root", default=None,
        help="Repo root (default: inferred from script location)",
    )
    parser.add_argument(
        "--stage", choices=["1", "2", "3", "all"], default="all",
        help="Run a specific stage only (default: all)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else _ROOT

    if args.stage in ("1", "all"):
        _stage1_lead_lag(root)
    if args.stage in ("2", "all"):
        _stage2_placebo(root)
    if args.stage in ("3", "all"):
        _stage3_falsifier(root)

    log.info("[grade_thematic] all stages complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
