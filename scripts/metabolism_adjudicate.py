"""scripts/metabolism_adjudicate.py — ADJUDICATE stage entrypoint (A5).

Rules on a PROPOSE docket and writes the governance ROW-PAIR (R-AUT-6). Invoked
THREE times per cycle by the workflow, each with a DISTINCT run_id:

    --role orchestrator   → orchestrator grant/deny governance rows
    --role adversary      → adversary veto/non-veto rows + adversary ledger (R-AUT-9)
    --role resolve        → two-key resolution rows (deterministic; no LLM)

GUARD ORDER (fail-closed; NEVER raises; always exits 0):
  1. metabolism_guard.is_paused()          → clean journaled no-op (INERT default)
  2. metabolism_budget.is_lobe_paused(til) → circuit-breaker paused → no-op
  3. journal.is_stage_done(<role stage>)   → resume: already ruled → skip
  4. preflight_claude_auth.check_auth()     → (LLM roles only) token unhealthy → no-op
  5. engine.metabolism.adjudicate.*         → rule + write governance rows

The 'resolve' role is deterministic (reads the row-pair, no LLM, no preflight),
so it can always finish the two-key even if the token is unhealthy.

Usage:
    python -m scripts.metabolism_adjudicate
        --cycle-id <cycle_id>
        --role orchestrator|adversary|resolve
        [--docket-file <path>]      # default: data/metabolism/dockets/<cycle_id>.json
        [--run-id <id>]             # default: GITHUB_RUN_ID-<role>
        [--root /path] [--lane metabolism-adjudicate] [--dry-run]

Exit 0 always.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("metabolism_adjudicate")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

_LOBE = "til"
_EST_TOKENS_PER_CALL = 30_000
_VALID_ROLES = ("orchestrator", "adversary", "resolve")


def _default_docket(root: Path, cycle_id: str) -> Path:
    return root / "data" / "metabolism" / "dockets" / f"{cycle_id}.json"


def _run_id(role: str, override: str | None) -> str | None:
    if override:
        return override
    rid = os.environ.get("GITHUB_RUN_ID")
    return f"{rid}-{role}" if rid else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Metabolism ADJUDICATE stage (A5)")
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--role", required=True, choices=_VALID_ROLES)
    parser.add_argument("--docket-file", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--lane", default="metabolism-adjudicate")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _ROOT
    cycle_id = args.cycle_id
    role = args.role
    stage = f"adjudicate_{role}"
    docket_file = Path(args.docket_file) if args.docket_file else _default_docket(root, cycle_id)

    from scripts.metabolism_guard import is_paused, pause_reason  # type: ignore[import]
    from scripts.metabolism_journal import (  # type: ignore[import]
        start_stage, finish_stage, is_stage_done,
    )

    # ── Gate 1: KILL SWITCH ─────────────────────────────────────────────────
    if is_paused():
        log.info("metabolism_adjudicate[%s]: %s — no-op exit 0", role, pause_reason())
        finish_stage(cycle_id, stage, status="noop_paused", note=pause_reason(), root=root)
        return 0

    # ── Gate 2: per-lobe circuit breaker ────────────────────────────────────
    try:
        from scripts.metabolism_budget import (  # type: ignore[import]
            is_lobe_paused, init_cycle, record_spend,
        )
        if is_lobe_paused(_LOBE, root=root):
            reason = f"lobe '{_LOBE}' circuit breaker tripped — no-op"
            log.warning("metabolism_adjudicate[%s]: %s", role, reason)
            finish_stage(cycle_id, stage, status="noop_paused", note=reason, root=root)
            return 0
        init_cycle(cycle_id, root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_adjudicate: budget layer error (%s) — proceeding", exc)
        record_spend = None  # type: ignore[assignment]

    # ── Gate 3: resume (idempotence) ────────────────────────────────────────
    if is_stage_done(cycle_id, stage, root=root):
        log.info("metabolism_adjudicate[%s]: stage already done — skipping (resume)", role)
        return 0

    # ── Gate 4: preflight (LLM roles only) ──────────────────────────────────
    if role in ("orchestrator", "adversary") and not args.dry_run:
        try:
            from scripts.preflight_claude_auth import check_auth  # type: ignore[import]
            auth = check_auth(lane=args.lane, root=root)
            if not auth.get("auth_ok"):
                if auth.get("cli_missing"):
                    # CLI binary absent ≠ token dead: adjudicate LLM roles call
                    # the API via engine.llm_auth (SDK), never the CLI — proceed
                    # (mirror of the PROPOSE gate; llm_auth self-protects).
                    log.warning(
                        "metabolism_adjudicate[%s]: preflight CLI missing (%s) — "
                        "proceeding on SDK channel", role, auth.get("reason"),
                    )
                else:
                    reason = f"preflight auth failed: {auth.get('reason')}"
                    log.warning("metabolism_adjudicate[%s]: %s", role, reason)
                    finish_stage(cycle_id, stage, status="noop_paused", note=reason, root=root)
                    return 0
        except Exception as exc:  # noqa: BLE001
            log.warning("metabolism_adjudicate[%s]: preflight error (%s)", role, exc)
            finish_stage(cycle_id, stage, status="noop_paused",
                         note=f"preflight error: {exc}", root=root)
            return 0

    start_stage(cycle_id, stage, root=root)

    try:
        from engine.metabolism.adjudicate import (  # type: ignore[import]
            adjudicate_role, resolve_two_key,
        )
        run_id = _run_id(role, args.run_id)

        if role == "resolve":
            res = resolve_two_key(cycle_id, docket_file, root=root, dry_run=args.dry_run)
            n_auth = sum(1 for v in res.values() if v.get("authorized"))
            log.info("metabolism_adjudicate[resolve]: cycle=%s authorized=%d/%d",
                     cycle_id, n_auth, len(res))
            finish_stage(cycle_id, stage, status="done",
                         note=f"two_key resolved: {n_auth}/{len(res)} authorized",
                         next_stage="build", root=root)
        else:
            results = adjudicate_role(role, cycle_id, docket_file,
                                      run_id=run_id, root=root, dry_run=args.dry_run)
            # Record token spend for the LLM roles (best-effort).
            try:
                if record_spend is not None:
                    record_spend(cycle_id, stage, tokens=_EST_TOKENS_PER_CALL,
                                 note=f"{role} n={len(results)}", root=root)
            except Exception:  # noqa: BLE001
                pass
            log.info("metabolism_adjudicate[%s]: cycle=%s ruled=%d",
                     role, cycle_id, len(results))
            finish_stage(cycle_id, stage, status="done",
                         note=f"{role} ruled {len(results)} proposal(s)",
                         next_stage="adjudicate_resolve" if role == "adversary" else None,
                         root=root)
    except Exception as exc:  # noqa: BLE001
        log.error("metabolism_adjudicate[%s]: unexpected error: %s", role, exc)
        finish_stage(cycle_id, stage, status="failed", note=str(exc), root=root)

    return 0


if __name__ == "__main__":
    sys.exit(main())
