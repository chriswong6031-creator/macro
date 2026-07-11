"""scripts/metabolism_propose.py — PROPOSE stage entrypoint (A4).

Stateless lobe-brain: reads the TIL fitness card + masterplan + case law and
emits a structured DOCKET at data/metabolism/dockets/<cycle_id>.json, each
proposal carrying a pre-committed fitness contract registered to the trial
ledger (R-AUT-8).

GUARD ORDER (fail-closed at every gate; NEVER raises; always exits 0):
  1. metabolism_guard.is_paused()          → clean journaled no-op (INERT default)
  2. metabolism_budget.is_lobe_paused(til) → circuit-breaker paused → no-op
  3. metabolism_budget over-cap check      → over budget → no-op
  4. preflight_claude_auth.check_auth()    → token unhealthy → no-op + operator alert
  5. engine.metabolism.propose.propose()   → build docket, register contracts, write

The heavy logic lives in engine.metabolism.propose (pure, hermetic-testable).
This wrapper owns the kill-switch, budget, preflight, and journal, mirroring
scripts/metabolism_verify.py.

Usage:
    python -m scripts.metabolism_propose
        [--cycle-id <cycle_id>]        # default: a fresh new_cycle_id()
        [--root /path/to/repo]
        [--today YYYY-MM-DD]
        [--max-docket-size N]          # default: config metabolism_budget.yml
        [--lane metabolism-propose]
        [--dry-run]

Exit 0 always.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("metabolism_propose")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

_LOBE = "til"
_STAGE = "propose"

# Conservative token estimate for one Opus PROPOSE call (system+context+reply),
# used only for budget accounting when the provider does not report usage.
_EST_TOKENS_PER_CALL = 30_000


def _load_max_docket_size(root: Path, override: int | None) -> int:
    if override is not None:
        return int(override)
    try:
        from scripts.metabolism_budget import _load_config  # type: ignore[import]
        cfg = _load_config(root)
        lobe_cfg = (cfg.get("lobe_caps") or {}).get(_LOBE) or {}
        return int(lobe_cfg.get("max_docket_size", cfg.get("max_docket_size", 5)))
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_propose: could not read max_docket_size (%s) — default 5", exc)
        return 5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Metabolism PROPOSE stage (A4)")
    parser.add_argument("--cycle-id", default=None, help="Cycle ID (default: fresh)")
    parser.add_argument("--root", default=None)
    parser.add_argument("--today", default=None, help="Override today (YYYY-MM-DD)")
    parser.add_argument("--max-docket-size", type=int, default=None)
    parser.add_argument("--lane", default="metabolism-propose")
    parser.add_argument("--lobe", default=None,
                        help="Lobe to drive (default: til). Use a different lobe id to run "
                             "the charter-driven prompt and accrual-honesty gate for that lobe.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build docket but do not register contracts or write")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _ROOT

    from scripts.metabolism_guard import is_paused, pause_reason  # type: ignore[import]
    from scripts.metabolism_journal import (  # type: ignore[import]
        start_stage, finish_stage, new_cycle_id,
    )

    cycle_id = args.cycle_id or new_cycle_id()

    # ── Gate 1: KILL SWITCH (first action, before any work) ─────────────────
    if is_paused():
        log.info("metabolism_propose: %s — no-op exit 0", pause_reason())
        finish_stage(cycle_id, _STAGE, status="noop_paused", note=pause_reason(), root=root)
        return 0

    # ── Gate 2: per-lobe circuit breaker ────────────────────────────────────
    try:
        from scripts.metabolism_budget import (  # type: ignore[import]
            is_lobe_paused, init_cycle, check_cap, record_spend,
        )
        if is_lobe_paused(_LOBE, root=root):
            reason = f"lobe '{_LOBE}' circuit breaker tripped — no-op"
            log.warning("metabolism_propose: %s", reason)
            finish_stage(cycle_id, _STAGE, status="noop_paused", note=reason, root=root)
            return 0

        # ── Gate 3: budget cap ──────────────────────────────────────────────
        init_cycle(cycle_id, root=root)
        cap = check_cap(cycle_id, root=root)
        if cap.get("over_cap"):
            reason = (f"budget over cap (usd_remaining={cap.get('usd_remaining')}, "
                      f"token_remaining={cap.get('token_remaining')}) — no-op")
            log.warning("metabolism_propose: %s", reason)
            finish_stage(cycle_id, _STAGE, status="noop_paused", note=reason, root=root)
            return 0
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_propose: budget layer error (%s) — proceeding cautiously", exc)

    # ── Gate 4: OAuth preflight (A2) ────────────────────────────────────────
    if not args.dry_run:
        try:
            from scripts.preflight_claude_auth import check_auth  # type: ignore[import]
            auth = check_auth(lane=args.lane, root=root)
            if not auth.get("auth_ok"):
                reason = f"preflight auth failed: {auth.get('reason')}"
                log.warning("metabolism_propose: %s", reason)
                finish_stage(cycle_id, _STAGE, status="noop_paused", note=reason, root=root)
                return 0
        except Exception as exc:  # noqa: BLE001
            log.warning("metabolism_propose: preflight error (%s) — treating as failed", exc)
            finish_stage(cycle_id, _STAGE, status="noop_paused",
                         note=f"preflight error: {exc}", root=root)
            return 0

    # ── Stage start ─────────────────────────────────────────────────────────
    start_stage(cycle_id, _STAGE, root=root)
    max_docket_size = _load_max_docket_size(root, args.max_docket_size)

    # ── PROPOSE ─────────────────────────────────────────────────────────────
    try:
        from engine.metabolism.propose import propose  # type: ignore[import]

        # Charter-proposal + lifecycle-docket applier (R-V4-9).
        # Injects consumed items as proposals only when armed (not paused).
        # The applier itself is NEVER-RAISE and emits plan records even in shadow.
        applier_proposals: list | None = None
        try:
            from engine.metabolism.applier import consume_charter_proposals  # type: ignore[import]
            _armed = not is_paused()  # armed when not paused
            applier_proposals = consume_charter_proposals(
                root=root,
                dry_run=args.dry_run,
                armed=_armed,
            )
            if applier_proposals:
                log.info(
                    "metabolism_propose: applier injected %d proposal(s)",
                    len(applier_proposals),
                )
        except Exception as _ae:  # noqa: BLE001
            log.warning("metabolism_propose: applier error (%s) — skipping injected proposals", _ae)
            applier_proposals = None

        result = propose(
            cycle_id, lobe=args.lobe or _LOBE, root=root,
            max_docket_size=max_docket_size,
            today=args.today, run_id=_run_id(), dry_run=args.dry_run,
            injected_proposals=applier_proposals if applier_proposals else None,
        )
        meta = result.get("meta", {})

        # Record the token spend against the budget ledger (best-effort).
        try:
            record_spend(cycle_id, _STAGE, tokens=_EST_TOKENS_PER_CALL,
                         note=f"propose n={meta.get('n_proposals')}", root=root)
        except Exception:  # noqa: BLE001
            pass

        log.info(
            "metabolism_propose: cycle=%s proposals=%s rejected=%s registered=%s "
            "provider=%s degraded=%s",
            cycle_id, meta.get("n_proposals"), meta.get("n_rejected"),
            meta.get("registered"), meta.get("provider"), meta.get("degraded_reason"),
        )
        artifact = meta.get("artifact")
        finish_stage(
            cycle_id, _STAGE, status="done",
            artifacts=[artifact] if artifact else [],
            next_stage="adjudicate",
            note=(f"docket {meta.get('n_proposals')} proposal(s); "
                  f"provider={meta.get('provider')}"),
            root=root,
        )
        # Emit the docket path on stdout for the workflow to pick up.
        if artifact:
            print(artifact)
    except Exception as exc:  # noqa: BLE001
        log.error("metabolism_propose: unexpected error: %s", exc)
        finish_stage(cycle_id, _STAGE, status="failed", note=str(exc), root=root)

    return 0


def _run_id() -> str | None:
    """Best-effort run id from the GH Actions env (for docket provenance)."""
    import os
    rid = os.environ.get("GITHUB_RUN_ID")
    return f"{rid}-propose" if rid else None


if __name__ == "__main__":
    sys.exit(main())
