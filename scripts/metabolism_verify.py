"""scripts/metabolism_verify.py — VERIFY stage entrypoint (A6).

After a proposal's check_by date arrives, re-grades the realized fitness delta
vs the registered contract using engine.metabolism.verify.verify_proposal().

KILL SWITCH: first action is metabolism_guard.is_paused() → clean journaled
no-op + exit 0 when paused.

Usage (single-cycle):
    python -m scripts.metabolism_verify
        --cycle-id <cycle_id>
        --contract-file <path to docket entry JSON>
        [--root /path/to/repo]
        [--today YYYY-MM-DD]
        [--dry-run]

Usage (cron / scan mode — no --cycle-id required):
    python -m scripts.metabolism_verify --scan [--root ...] [--today ...] [--dry-run]

    Scans data/metabolism/dockets/ for all cycles whose fitness contracts have
    a check_by date that has arrived, and runs VERIFY on each.  Skips cycles
    that already have a verify record.  Exits 0 always (NEVER raises).

Exit 0 always (NEVER raises).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("metabolism_verify")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def _scan_pending_cycles(root: Path, today: str | None) -> list[tuple[str, dict]]:
    """Return (cycle_id, contract) pairs whose check_by has arrived and are unverified.

    Scans data/metabolism/dockets/<cycle_id>.json for registered fitness
    contracts.  Skips cycles that already have a verify record at
    data/metabolism/verify/<cycle_id>.json.  Never raises.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    today_str = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dockets_dir = root / "data" / "metabolism" / "dockets"
    verify_dir = root / "data" / "metabolism" / "verify"
    pending: list[tuple[str, dict]] = []

    if not dockets_dir.exists():
        log.info("metabolism_verify scan: no dockets dir — nothing to do")
        return pending

    for docket_path in sorted(dockets_dir.glob("*.json")):
        cycle_id = docket_path.stem
        # Skip if already verified
        if (verify_dir / f"{cycle_id}.json").exists():
            log.debug("metabolism_verify scan: %s already verified — skip", cycle_id)
            continue
        try:
            docket = json.loads(docket_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("metabolism_verify scan: cannot read docket %s: %s", docket_path, exc)
            continue

        # Collect all contracts from proposals in this docket
        proposals = docket.get("proposals") or []
        docket_lobe = str(docket.get("lobe") or "").strip()
        for proposal in proposals:
            contract = proposal.get("fitness_contract") or {}
            if not isinstance(contract, dict):
                continue
            # Contracts minted before the lobe key existed inherit the
            # docket-level lobe, else verify writes lobe="" strategic-memory
            # rows that the per-lobe PROPOSE filter drops.
            if docket_lobe and not contract.get("lobe"):
                contract["lobe"] = docket_lobe
            check_by = contract.get("check_by")
            if not check_by:
                continue
            if check_by <= today_str:
                pending.append((cycle_id, contract))
                break  # one verify per docket cycle_id (the workflow loops if needed)

    return pending


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Metabolism VERIFY stage (A6)")
    parser.add_argument("--cycle-id", default=None,
                        help="Cycle ID from the journal (omit with --scan for cron mode)")
    parser.add_argument("--scan", action="store_true",
                        help="Scan all dockets for cycles ready to verify (cron mode)")
    parser.add_argument("--contract-file", default=None,
                        help="Path to the proposal's fitness contract JSON")
    parser.add_argument("--root", default=None)
    parser.add_argument("--today", default=None, help="Override today's date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build verify record but do not write to disk")
    args = parser.parse_args(argv)

    if not args.cycle_id and not args.scan:
        log.error("metabolism_verify: --cycle-id or --scan is required")
        return 0  # NEVER-RAISE: exit 0, log the error

    root = Path(args.root) if args.root else _ROOT

    # ── KILL SWITCH (first action, before any work) ────────────────────────
    from scripts.metabolism_guard import is_paused, pause_reason  # type: ignore[import]

    if is_paused():
        log.info("metabolism_verify: %s — no-op exit 0", pause_reason())
        # Phase-A inertness contract: a paused single-cycle invocation journals
        # noop_paused so the cycle's journal shows verify was reached and
        # deliberately skipped (scan mode has no cycle to journal against).
        if args.cycle_id:
            try:
                from scripts.metabolism_journal import finish_stage  # type: ignore[import]
                finish_stage(args.cycle_id, "verify", status="noop_paused",
                             note=pause_reason(), root=root)
            except Exception as exc:  # noqa: BLE001
                log.warning("metabolism_verify: paused-journal write failed: %s", exc)
        return 0

    # ── Scan mode: iterate all pending cycles ─────────────────────────────
    if args.scan:
        pending = _scan_pending_cycles(root, args.today)
        if not pending:
            log.info("metabolism_verify scan: no cycles ready to verify today")
            return 0
        for cycle_id, contract in pending:
            _run_single(cycle_id, contract, root, args.today, args.dry_run)
        return 0

    # ── Single-cycle mode ─────────────────────────────────────────────────
    cycle_id = args.cycle_id  # guaranteed non-None here (check above)
    contract: dict = {}
    if args.contract_file:
        try:
            contract = json.loads(Path(args.contract_file).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("metabolism_verify: could not load contract file: %s", exc)
            from scripts.metabolism_journal import finish_stage  # type: ignore[import]
            finish_stage(cycle_id, "verify", status="failed",
                         note=f"contract load error: {exc}", root=root)
            return 0
    _run_single(cycle_id, contract, root, args.today, args.dry_run)
    return 0


def _build_triage_context(root: Path, today: str | None = None) -> dict:
    """Deterministically populate regime/estimator triage flags from committed stores.

    Reads data/regime/regime_one.json (written nightly by the regime engine) and
    extracts the flip_attribution.flipped boolean.  This is a deterministic read —
    no LLM involvement, no origination.

    Staleness: a stale ``flipped=False`` is the only dangerous direction (it would
    let a regime-era miss auto-revert), so when ``flip_attribution.asof`` lags
    ``today`` by more than one calendar day the read fails TOWARD caution
    (``regime_change_suspected=True``), routing the miss to operator_tap rather
    than a clean-overfit auto-revert.  A stale ``flipped=True`` already holds the
    kill, so it needs no special handling.

    Absence/unreadability returns an empty context.  NOTE: an empty context is
    NOT an operator_tap fallback — verify.py reads missing flags as False, so a
    clean-miss is then triaged as clean-overfit (the pre-existing no-context
    default).  The ``asof`` is always logged so staleness is auditable.

    Returns a dict suitable for passing as context= to verify_proposal().
    NEVER raises.
    """
    try:
        p = root / "data" / "regime" / "regime_one.json"
        if not p.exists():
            log.info("metabolism_verify: regime_one.json absent — triage context empty "
                     "(missing flags read as False → clean-overfit default)")
            return {}
        d = json.loads(p.read_text(encoding="utf-8"))
        flip = (d.get("flip_attribution") or {})
        flipped = bool(flip.get("flipped", False))
        degraded = bool(d.get("degraded", False))
        asof = str(flip.get("asof") or d.get("asof") or "")

        stale = _regime_asof_is_stale(asof, today)
        suspected = bool(flipped or degraded or stale)
        log.info(
            "metabolism_verify: regime_one flipped=%s degraded=%s asof=%s stale=%s "
            "→ regime_change_suspected=%s",
            flipped, degraded, asof or "(none)", stale, suspected,
        )
        return {
            "regime_change_suspected": suspected,
            "estimator_broken_suspected": False,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_verify: _build_triage_context failed (%s) — context empty", exc)
        return {}


def _regime_asof_is_stale(asof: str, today: str | None = None) -> bool:
    """True when the regime asof lags today by more than one calendar day, or is
    missing/unparseable.  Fails toward stale=True so a garbled asof routes misses
    to caution (operator_tap).  NEVER raises."""
    try:
        from datetime import datetime, timezone
        if not asof:
            return True
        ad = datetime.fromisoformat(asof.replace("Z", "+00:00")).date()
        td = (datetime.fromisoformat(today).date() if today
              else datetime.now(timezone.utc).date())
        return (td - ad).days > 1
    except Exception:  # noqa: BLE001
        return True


def _run_single(
    cycle_id: str,
    contract: dict,
    root: Path,
    today: str | None,
    dry_run: bool,
) -> None:
    """Run verify for one cycle_id.  Never raises."""
    from scripts.metabolism_journal import start_stage, finish_stage  # type: ignore[import]

    # ── Stage start ───────────────────────────────────────────────────────
    start_stage(cycle_id, "verify", root=root)

    # ── Verify ────────────────────────────────────────────────────────────
    try:
        from engine.metabolism.verify import verify_proposal, write_verify_record  # type: ignore[import]

        # Populate regime/estimator triage flags from deterministic committed stores
        # (measurement-lens law: separate mechanism-false vs regime-change vs estimator-broken).
        triage_context = _build_triage_context(root, today)

        record = verify_proposal(
            cycle_id=cycle_id,
            contract=contract,
            context=triage_context,
            root=root,
            today=today,
        )

        if dry_run:
            log.info("metabolism_verify [dry-run]: %s", json.dumps(record, indent=2, default=str))
        else:
            out_path = write_verify_record(record, root)
            log.info("metabolism_verify: wrote %s", out_path)

        action = record.get("triage", {}).get("action", "")
        log.info("metabolism_verify: cycle=%s action=%s classification=%s",
                 cycle_id, action,
                 record.get("triage", {}).get("classification", ""))

        artifact = str(root / "data" / "metabolism" / "verify" / f"{cycle_id}.json")
        finish_stage(cycle_id, "verify", status="done",
                     artifacts=[artifact] if not dry_run else [],
                     root=root)

    except Exception as exc:  # noqa: BLE001
        log.error("metabolism_verify: unexpected error: %s", exc)
        finish_stage(cycle_id, "verify", status="failed", note=str(exc), root=root)


if __name__ == "__main__":
    sys.exit(main())
