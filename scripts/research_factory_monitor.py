"""scripts/research_factory_monitor.py — Paper monitor CLI (W6, RF-8/RF-9/RF-10/RF-5).

Wraps engine.research_factory.monitor.run_monitor() with forward-ledger
discipline (RF-8):

  DEFAULT: --dry-run (prints rows, writes NOTHING under data/).
  --write:  appends paper_monitor.jsonl keep-first per (candidate_id, as_of),
            refreshes each candidate's track/<id>.json, appends a health.v1 row
            via build_research_factory_health.compute_health (imported; not forked),
            and writes mechanical transitions (paper→human_review,
            deferred→human_review) to transitions.jsonl.

Exit code: 0 always in nightly context (internal errors logged, non-fatal, RF-8).
Never transitions a candidate to 'retired' — that is human-only (RF-5).

Charter: research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md §6 W6,
rulings RF-5, RF-8, RF-9, RF-10.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger("research_factory_monitor")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_RF_DIR = ROOT / "data" / "research_factory"
DEFAULT_ORACLE_LIVE_LEDGER = (
    ROOT / "data" / "oracle" / "compounds" / "live_ledger.jsonl"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        level=level,
        stream=sys.stderr,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_iso() -> str:
    from datetime import date
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Track file refresh
# ---------------------------------------------------------------------------


def _refresh_track_file(
    rf_dir: Path,
    monitor_row: dict,
    dry_run: bool,
) -> None:
    """Refresh data/research_factory/track/<candidate_id>.json from the monitor row.

    The experiments-registry overlay reads this file each build to surface
    the latest paper status — we must keep it current.

    Never edits registry_seed.json from the monitor (RF-8 / §spec).
    """
    cid = monitor_row.get("candidate_id", "?")
    track_dir = rf_dir / "track"
    track_path = track_dir / f"{cid}.json"

    if dry_run:
        log.info("[DRY-RUN] Would refresh track file: %s", track_path)
        return

    # Load existing track (preserve existing fields written by decide.py)
    existing: dict = {}
    if track_path.exists():
        try:
            existing = json.loads(track_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    # Update with monitor state
    observed = monitor_row.get("observed_metric") or {}
    n = observed.get("n") or 0
    metric_value = observed.get("value")

    ep_key = observed.get("name") or "primary_metric"
    existing.update(
        {
            "paper_status": monitor_row.get("paper_status"),
            "monitor_action": monitor_row.get("action"),
            "monitor_as_of": monitor_row.get("as_of"),
            "n_matured": n,
            "observed_metric_value": metric_value,
            "decay_flags": monitor_row.get("decay_flags") or [],
            "data_health_flags": monitor_row.get("data_health_flags") or [],
            "falsifier_verdict": monitor_row.get("falsifier_verdict"),
            # Keep schema + authority from original
        }
    )
    if "schema" not in existing:
        existing["schema"] = "research_factory.track.v1"
    if "authority" not in existing:
        existing["authority"] = "display_only"
    if "candidate_id" not in existing:
        existing["candidate_id"] = cid

    try:
        track_dir.mkdir(parents=True, exist_ok=True)
        import os, tempfile
        fd, tmp = tempfile.mkstemp(dir=str(track_dir), prefix=".tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(existing, fh, indent=2, default=str)
            os.replace(tmp, str(track_path))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        log.info("Refreshed track file: %s", track_path)
    except Exception as exc:
        log.error("Failed to refresh track file %s: %s", track_path, exc)


# ---------------------------------------------------------------------------
# Transition writer
# ---------------------------------------------------------------------------


def _write_transition(
    rf_dir: Path,
    t_row: dict,
    existing_transitions: list[dict],
    dry_run: bool,
) -> bool:
    """Append a transition row to transitions.jsonl.

    Idempotency: skip if a transition with the same (candidate_id, from, to,
    as_of[:10]) already exists (same-day duplicate guard).

    Returns True if written or True if dry-run.
    """
    from engine.research_factory import ledger as rf_ledger
    from engine.research_factory.schema import validate_transition

    cid = t_row.get("candidate_id", "?")
    as_of_date = str(t_row.get("as_of", ""))[:10]

    # Same-day idempotency guard
    for existing_t in existing_transitions:
        if (
            existing_t.get("candidate_id") == cid
            and existing_t.get("from") == t_row.get("from")
            and existing_t.get("to") == t_row.get("to")
            and str(existing_t.get("as_of", ""))[:10] == as_of_date
        ):
            log.info(
                "[SKIP] Transition %s→%s for %s as_of %s already exists",
                t_row.get("from"), t_row.get("to"), cid, as_of_date,
            )
            return True

    errs = validate_transition(t_row)
    if errs:
        log.error("Transition schema violations for %s: %s", cid, errs)
        return False

    # Defense-in-depth (RF-5): route through the state-machine allowlist so a
    # future edit constructing a non-allowlisted (from, to, actor) raises here
    # instead of slipping past schema-only validation.
    from engine.research_factory.state import IllegalTransition, transition as rf_transition
    try:
        rf_transition(
            from_state=t_row.get("from"),
            to_state=t_row.get("to"),
            actor=t_row.get("actor", "script"),
            transition_row=t_row,
        )
    except IllegalTransition as exc:
        log.error("Actor-law violation for %s: %s", cid, exc)
        return False

    if dry_run:
        log.info(
            "[DRY-RUN] Would write transition %s→%s for %s",
            t_row.get("from"), t_row.get("to"), cid,
        )
        return True

    try:
        rf_ledger.append_row(
            rf_dir / "transitions.jsonl",
            t_row,
            validate_fn=validate_transition,
        )
        log.info(
            "Wrote transition %s→%s for %s",
            t_row.get("from"), t_row.get("to"), cid,
        )
        return True
    except Exception as exc:
        log.error("Failed to write transition for %s: %s", cid, exc)
        return False


# ---------------------------------------------------------------------------
# Health row appender
# ---------------------------------------------------------------------------


def _append_health_row(rf_dir: Path, dry_run: bool) -> None:
    """Invoke build_research_factory_health.compute_health and append the row.

    Imports the existing function — never forks it (RF-8 / spec).
    Forward-ledger keep-first per (as_of).
    """
    try:
        from engine.research_factory import ledger as rf_ledger
        from engine.research_factory.schema import validate_health
        from scripts.build_research_factory_health import compute_health, _load_challenges

        candidates = rf_ledger.load_jsonl(rf_dir / "candidates.jsonl")
        transitions = rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")
        challenges = _load_challenges(rf_dir / "challenges")

        as_of = _now_iso()
        health_row = compute_health(
            candidates=candidates,
            transitions=transitions,
            challenges=challenges,
            as_of=as_of,
        )

        errs = validate_health(health_row)
        if errs:
            log.error("Health row validation failed: %s", errs)
            return

        health_path = rf_dir / "health.jsonl"

        if dry_run:
            log.info("[DRY-RUN] Would append health row as_of=%s", as_of)
            return

        # Keep-first per as_of (RF-8)
        existing = rf_ledger.load_forward_ledger(health_path, key_fields=("as_of",))
        existing_as_ofs = {r.get("as_of") for r in existing}
        if as_of in existing_as_ofs:
            log.info("[SKIP] Health row as_of=%s already in health.jsonl (keep-first)", as_of)
            return

        rf_ledger.append_row(health_path, health_row, validate_fn=validate_health)
        log.info("Appended health row to %s (as_of=%s)", health_path, as_of)

    except Exception as exc:
        log.error("Health row build failed (non-fatal): %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(
    rf_dir: Path,
    oracle_live_ledger_path: Path | None,
    as_of: str | None,
    write: bool,
    verbose: bool,
) -> int:
    """Run the paper monitor.  Returns 0 always (non-fatal, RF-8)."""
    _setup_logging(verbose)

    dry_run = not write

    if dry_run:
        log.info(
            "research_factory_monitor: DRY-RUN mode (default). "
            "Use --write to commit forward ledger rows."
        )
    else:
        log.info("research_factory_monitor: --write mode (nightly forward ledger).")

    # Resolve paths
    if oracle_live_ledger_path is None:
        oracle_live_ledger_path = DEFAULT_ORACLE_LIVE_LEDGER

    today = as_of or _today_iso()

    try:
        from engine.research_factory.monitor import run_monitor
        monitor_rows, transition_rows = run_monitor(
            rf_dir=rf_dir,
            oracle_live_ledger_path=oracle_live_ledger_path,
            as_of=today,
        )
    except Exception as exc:
        log.error("run_monitor failed (non-fatal): %s", exc, exc_info=True)
        return 0  # RF-8: exit 0 always in nightly context

    if not monitor_rows:
        log.info("No paper/awaiting_data/deferred candidates found — nothing to monitor.")
        if not dry_run:
            _append_health_row(rf_dir, dry_run=False)
        return 0

    # Print rows (always)
    log.info("Monitor produced %d rows, %d transitions.", len(monitor_rows), len(transition_rows))
    for row in monitor_rows:
        cid = row.get("candidate_id", "?")
        action = row.get("action", "?")
        status = row.get("paper_status", "?")
        decay = row.get("decay_flags") or []
        log.info(
            "  candidate=%s status=%s action=%s decay_flags=%s",
            cid, status, action, decay,
        )

    if dry_run:
        log.info("[DRY-RUN] No files written. Rows above are display-only.")
        return 0

    # --write path: commit forward ledger rows
    try:
        from engine.research_factory import ledger as rf_ledger
        from engine.research_factory.schema import validate_paper_monitor

        paper_monitor_path = rf_dir / "paper_monitor.jsonl"

        # Load existing paper_monitor rows for keep-first dedup
        existing_pm = rf_ledger.load_forward_ledger(
            paper_monitor_path, key_fields=("candidate_id", "as_of")
        )
        existing_pm_keys = {
            (r.get("candidate_id"), r.get("as_of")) for r in existing_pm
        }

        for row in monitor_rows:
            cid = row.get("candidate_id")
            row_as_of = row.get("as_of")
            key = (cid, row_as_of)

            if key in existing_pm_keys:
                log.info(
                    "[SKIP] paper_monitor row for %s as_of=%s already exists (keep-first)",
                    cid, row_as_of,
                )
                continue

            try:
                errs = validate_paper_monitor(row)
                if errs:
                    log.error("paper_monitor row for %s failed validation: %s", cid, errs)
                    continue
                rf_ledger.append_row(
                    paper_monitor_path, row, validate_fn=validate_paper_monitor
                )
                log.info("Appended paper_monitor row for %s as_of=%s", cid, row_as_of)
                existing_pm_keys.add(key)

                # Refresh track file for the experiments-registry overlay
                _refresh_track_file(rf_dir, row, dry_run=False)

            except Exception as exc:
                log.error(
                    "Failed to write paper_monitor row for %s: %s (non-fatal)", cid, exc
                )

    except Exception as exc:
        log.error("paper_monitor.jsonl write loop failed (non-fatal): %s", exc, exc_info=True)

    # Write mechanical transitions (paper→human_review, deferred→human_review)
    try:
        from engine.research_factory import ledger as rf_ledger
        existing_transitions = rf_ledger.load_jsonl(rf_dir / "transitions.jsonl")

        for t_row in transition_rows:
            _write_transition(rf_dir, t_row, existing_transitions, dry_run=False)

    except Exception as exc:
        log.error("Transition writes failed (non-fatal): %s", exc, exc_info=True)

    # Append health row (must come AFTER all other writes so funnel counts are fresh)
    _append_health_row(rf_dir, dry_run=False)

    log.info("research_factory_monitor complete.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--write",
        action="store_true",
        default=False,
        help=(
            "Append rows to paper_monitor.jsonl, refresh track files, and append "
            "health.v1 row (RF-8: default is --dry-run; --write is nightly-only)"
        ),
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Explicit dry-run flag (default behavior — for clarity in scripts)",
    )
    ap.add_argument(
        "--rf-dir",
        type=Path,
        default=None,
        help="Override data/research_factory/ directory",
    )
    ap.add_argument(
        "--oracle-live-ledger",
        type=Path,
        default=None,
        help="Override path to data/oracle/compounds/live_ledger.jsonl",
    )
    ap.add_argument(
        "--as-of",
        default=None,
        help="Date override (YYYY-MM-DD) for monitor rows",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Verbose logging (DEBUG level)",
    )
    return ap


def main() -> int:
    ap = _build_parser()
    args = ap.parse_args()

    rf_dir = args.rf_dir or DEFAULT_RF_DIR
    oracle_path = args.oracle_live_ledger or None

    # RF-8: --write takes precedence; dry_run is the default
    write = args.write

    try:
        return run(
            rf_dir=rf_dir,
            oracle_live_ledger_path=oracle_path,
            as_of=args.as_of,
            write=write,
            verbose=args.verbose,
        )
    except Exception as exc:
        # RF-8: exit 0 always in nightly context
        logging.getLogger("research_factory_monitor").error(
            "Unhandled error (non-fatal, exit 0): %s", exc, exc_info=True
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
