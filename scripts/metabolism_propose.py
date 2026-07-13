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
  4.5 attention.propose_skip(lobe)        → DORMANT skip: write empty docket, journal; skip LLM
  5. engine.metabolism.propose.propose()   → build docket, register contracts, write
     (with max_docket_size scaled by attention.effective_docket_size for non-DORMANT lobes)

The heavy logic lives in engine.metabolism.propose (pure, hermetic-testable).
This wrapper owns the kill-switch, budget, preflight, attention gate, and journal,
mirroring scripts/metabolism_verify.py.

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


def _load_max_docket_size(root: Path, override: int | None, lobe: str = _LOBE) -> int:
    if override is not None:
        return int(override)
    try:
        from scripts.metabolism_budget import _load_config  # type: ignore[import]
        cfg = _load_config(root)
        lobe_cfg = (cfg.get("lobe_caps") or {}).get(lobe) or {}
        return int(lobe_cfg.get("max_docket_size", cfg.get("max_docket_size", 5)))
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_propose: could not read max_docket_size (%s) — default 5", exc)
        return 5


def _discover_loop_managed_lobes(root: Path) -> list[str]:
    """Discover loop-managed lobe IDs from config/lobe_charters.yml.

    Returns lobe IDs whose lifecycle_state is in ("probation","active") AND
    fitness_sensors are structured (list of dicts with id+store keys).
    The 'til' lobe is ALWAYS included first (backward compat guarantee).
    NEVER raises.
    """
    try:
        import yaml  # noqa: PLC0415
        charters_path = root / "config" / "lobe_charters.yml"
        if not charters_path.exists():
            return [_LOBE]
        data = yaml.safe_load(charters_path.read_text(encoding="utf-8"))
        charters = (data or {}).get("charters") or {}
        loop_managed: list[str] = []
        for lobe_id, charter in charters.items():
            lc_state = (charter or {}).get("lifecycle_state") or ""
            if lc_state not in ("probation", "active"):
                continue
            sensors = (charter or {}).get("fitness_sensors") or []
            if not isinstance(sensors, list) or not sensors:
                continue
            # Structured = all items are dicts with id+store
            if not all(isinstance(s, dict) and "id" in s and "store" in s for s in sensors):
                continue
            loop_managed.append(lobe_id)

        # 'til' must be present and first (backward compat)
        if _LOBE not in loop_managed:
            loop_managed = [_LOBE] + loop_managed
        else:
            loop_managed = [_LOBE] + [l for l in loop_managed if l != _LOBE]

        return loop_managed
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_propose: _discover_loop_managed_lobes: %s — default [til]", exc)
        return [_LOBE]


def _run_all_lobes(args: "argparse.Namespace", root: Path) -> int:  # noqa: F821
    """Run the single-lobe propose flow for every loop-managed lobe.

    The first lobe (always 'til') keeps the bare base cycle_id (backward compat).
    Every subsequent lobe gets cycle_id = f"{base_cycle_id}-{lobe_id}".
    Per-lobe failures isolate (log + continue).
    NEVER raises.

    Returns 0 always.
    """
    try:
        from scripts.metabolism_journal import new_cycle_id  # type: ignore[import]
        base_cycle = args.cycle_id or new_cycle_id()
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_propose --all-lobes: could not get base cycle_id: %s", exc)
        base_cycle = f"cycle-{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    loop_managed = _discover_loop_managed_lobes(root)
    log.info(
        "metabolism_propose --all-lobes: base_cycle=%s lobes=%s",
        base_cycle, loop_managed,
    )

    # ── R-V9-2 stage-local heal: agenda-branch artifacts never reach main, so
    # this checkout may lack the allocation.  Rebuild structural-only once
    # (writes data/metabolism/attention_allocation.json — rides the propose
    # branch commit; the LLM discretion layer stays agenda-stage-only).
    _alloc: dict | None = None
    try:
        from engine.metabolism import attention as _attn_heal  # noqa: PLC0415
        _alloc = _attn_heal.effective_allocation(cycle_id=base_cycle, root=root)
    except Exception as _he:  # noqa: BLE001
        log.warning(
            "metabolism_propose --all-lobes: attention heal failed (%s) — "
            "per-call defaults apply", _he,
        )

    for i, lobe_id in enumerate(loop_managed):
        # First lobe keeps the bare base cycle_id (backward compat guarantee)
        cycle_id = base_cycle if i == 0 else f"{base_cycle}-{lobe_id}"
        try:
            log.info(
                "metabolism_propose --all-lobes: running lobe=%s cycle_id=%s",
                lobe_id, cycle_id,
            )

            # ── Attention gate (R-V9-3): check if lobe should be skipped ────────
            _attn_skip = False
            _attn_skip_reason = ""
            try:
                from engine.metabolism import attention as _attn  # noqa: PLC0415
                _attn_skip, _attn_skip_reason = _attn.propose_skip(
                    lobe_id, root=root, allocation=_alloc,
                )
            except Exception as _ae:  # noqa: BLE001
                log.warning(
                    "metabolism_propose --all-lobes: attention.propose_skip failed for "
                    "lobe=%s (%s) — proceeding", lobe_id, _ae,
                )
                _attn_skip, _attn_skip_reason = False, "attention_error"

            if _attn_skip:
                log.info(
                    "metabolism_propose --all-lobes: lobe=%s ATTENTION SKIP reason=%s — "
                    "writing empty docket", lobe_id, _attn_skip_reason,
                )
                _write_attention_skip_docket(cycle_id, lobe_id, _attn_skip_reason, root=root)
                continue

            # ── Normal single-lobe path ──────────────────────────────────────────
            import copy  # noqa: PLC0415
            lobe_args = copy.copy(args)
            lobe_args.lobe = lobe_id
            lobe_args.cycle_id = cycle_id
            lobe_args.all_lobes = False  # prevent recursive call
            _run_single_lobe(lobe_args, root, lobe_id, cycle_id)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "metabolism_propose --all-lobes: lobe=%s cycle=%s failed: %s",
                lobe_id, cycle_id, exc,
            )
            # Per-lobe failure isolates — continue to next lobe

    return 0


def _write_attention_skip_docket(
    cycle_id: str,
    lobe_id: str,
    skip_reason: str,
    *,
    root: Path,
) -> None:
    """Write an empty docket for a DORMANT-skipped lobe and journal the skip.

    The empty docket (proposals=[]) is required so downstream ADJUDICATE
    discovery (which reads data/metabolism/dockets/<cycle_id>.json) never
    breaks on a missing file.  NEVER raises.
    """
    try:
        from engine.metabolism.propose import build_docket, write_docket  # type: ignore[import]
        empty_docket = build_docket(
            cycle_id,
            [],
            root=root,
            max_docket_size=0,
            lobe=lobe_id,
            degraded_reason=f"attention_dormant_skip:{skip_reason}",
        )
        # Override notes to reflect the skip clearly.
        empty_docket["notes"] = (
            f"attention_dormant_skip: lobe={lobe_id} reason={skip_reason} "
            "— no LLM call made (R-V9-3 / R-V9-7)"
        )
        written = write_docket(empty_docket, root=root)
        log.info(
            "metabolism_propose: attention skip docket written: lobe=%s path=%s",
            lobe_id, written,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "metabolism_propose: _write_attention_skip_docket lobe=%s: %s", lobe_id, exc,
        )

    # Journal the skip (R-V9-7: never silent).
    try:
        from scripts.metabolism_journal import finish_stage  # type: ignore[import]
        finish_stage(
            cycle_id, "propose", "done",
            note=f"attention_skip lobe={lobe_id} reason={skip_reason}",
            root=root,
        )
    except Exception as exc:  # noqa: BLE001
        # Fallback: append to data/metabolism/attention_skips.jsonl
        try:
            import json as _json  # noqa: PLC0415
            from datetime import datetime, timezone  # noqa: PLC0415
            skips_path = root / "data" / "metabolism" / "attention_skips.jsonl"
            skips_path.parent.mkdir(parents=True, exist_ok=True)
            row = {
                "cycle_id": cycle_id,
                "lobe": lobe_id,
                "reason": skip_reason,
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            with skips_path.open("a", encoding="utf-8") as _fh:
                _fh.write(_json.dumps(row, separators=(",", ":")) + "\n")
        except Exception as _fe:  # noqa: BLE001
            log.warning(
                "metabolism_propose: attention skip journal fallback also failed: %s / %s",
                exc, _fe,
            )


def _run_single_lobe(args: "argparse.Namespace", root: Path, lobe: str, cycle_id: str) -> None:  # noqa: F821
    """Run the propose flow for a single lobe.  NEVER raises.

    Extracted from main() to allow --all-lobes to reuse it.
    """
    try:
        from scripts.metabolism_guard import is_paused, pause_reason  # type: ignore[import]
        from scripts.metabolism_journal import (  # type: ignore[import]
            start_stage, finish_stage,
        )

        # ── Gate 1: KILL SWITCH ────────────────────────────────────────────
        if is_paused():
            log.info("metabolism_propose[%s]: %s — no-op", lobe, pause_reason())
            finish_stage(cycle_id, _STAGE, status="noop_paused", note=pause_reason(), root=root)
            return

        # ── Gate 2: per-lobe circuit breaker ─────────────────────────────
        try:
            from scripts.metabolism_budget import (  # type: ignore[import]
                is_lobe_paused, init_cycle, check_cap, record_spend,
            )
            if is_lobe_paused(lobe, root=root):
                reason = f"lobe '{lobe}' circuit breaker tripped — no-op"
                log.warning("metabolism_propose[%s]: %s", lobe, reason)
                finish_stage(cycle_id, _STAGE, status="noop_paused", note=reason, root=root)
                return

            # ── Gate 3: budget cap ────────────────────────────────────────
            init_cycle(cycle_id, root=root)
            cap = check_cap(cycle_id, root=root)
            if cap.get("over_cap"):
                reason = (f"budget over cap (usd_remaining={cap.get('usd_remaining')}, "
                          f"token_remaining={cap.get('token_remaining')}) — no-op")
                log.warning("metabolism_propose[%s]: %s", lobe, reason)
                finish_stage(cycle_id, _STAGE, status="noop_paused", note=reason, root=root)
                return
        except Exception as exc:  # noqa: BLE001
            log.warning("metabolism_propose[%s]: budget layer error (%s) — proceeding cautiously",
                        lobe, exc)

        # ── Gate 4: OAuth preflight ───────────────────────────────────────
        if not args.dry_run:
            try:
                from scripts.preflight_claude_auth import check_auth  # type: ignore[import]
                auth = check_auth(lane=args.lane, root=root)
                if not auth.get("auth_ok"):
                    reason = f"preflight auth failed: {auth.get('reason')}"
                    log.warning("metabolism_propose[%s]: %s", lobe, reason)
                    finish_stage(cycle_id, _STAGE, status="noop_paused", note=reason, root=root)
                    return
            except Exception as exc:  # noqa: BLE001
                log.warning("metabolism_propose[%s]: preflight error (%s) — treating as failed",
                            lobe, exc)
                finish_stage(cycle_id, _STAGE, status="noop_paused",
                             note=f"preflight error: {exc}", root=root)
                return

        # ── Stage start ───────────────────────────────────────────────────
        start_stage(cycle_id, _STAGE, root=root)
        max_docket_size = _load_max_docket_size(root, args.max_docket_size, lobe=lobe)

        # ── Attention docket scaling (R-V9, G5 cap-asymmetry) ────────────
        # Scale the base docket size down by the lobe's attention band.
        # Guarded: on any failure, use the unscaled base size.
        _base_docket_size = max_docket_size
        try:
            from engine.metabolism import attention as _attn_scale  # noqa: PLC0415
            # R-V9-2 stage-local heal: idempotent — loads the allocation when
            # present (the --all-lobes heal already wrote it), rebuilds
            # structural-only otherwise (direct single-lobe invocation).
            _alloc_sl = _attn_scale.effective_allocation(cycle_id=cycle_id, root=root)
            max_docket_size = _attn_scale.effective_docket_size(
                lobe, _base_docket_size, root=root, allocation=_alloc_sl,
            )
            if max_docket_size != _base_docket_size:
                try:
                    _band = _attn_scale.band_for(lobe, allocation=_alloc_sl, root=root)
                except Exception:  # noqa: BLE001
                    _band = "STANDARD"
                log.info(
                    "metabolism_propose[%s]: attention band=%s docket %d→%d",
                    lobe, _band, _base_docket_size, max_docket_size,
                )
        except Exception as _ae:  # noqa: BLE001
            log.warning(
                "metabolism_propose[%s]: attention docket scaling failed (%s) — "
                "using base size %d", lobe, _ae, _base_docket_size,
            )
            max_docket_size = _base_docket_size

        # ── PROPOSE ───────────────────────────────────────────────────────
        from engine.metabolism.propose import propose  # type: ignore[import]

        applier_proposals: list | None = None
        try:
            from engine.metabolism.applier import consume_charter_proposals  # type: ignore[import]
            _armed = not is_paused()
            applier_proposals = consume_charter_proposals(
                root=root,
                dry_run=args.dry_run,
                armed=_armed,
            )
            if applier_proposals:
                log.info(
                    "metabolism_propose[%s]: applier injected %d proposal(s)",
                    lobe, len(applier_proposals),
                )
        except Exception as _ae:  # noqa: BLE001
            log.warning("metabolism_propose[%s]: applier error (%s) — skipping injected",
                        lobe, _ae)
            applier_proposals = None

        result = propose(
            cycle_id, lobe=lobe, root=root,
            max_docket_size=max_docket_size,
            today=args.today, run_id=_run_id(), dry_run=args.dry_run,
            injected_proposals=applier_proposals if applier_proposals else None,
        )
        meta = result.get("meta", {})

        try:
            from scripts.metabolism_budget import record_spend  # type: ignore[import]
            record_spend(cycle_id, _STAGE, tokens=_EST_TOKENS_PER_CALL,
                         note=f"propose lobe={lobe} n={meta.get('n_proposals')}", root=root)
        except Exception:  # noqa: BLE001
            pass

        log.info(
            "metabolism_propose[%s]: cycle=%s proposals=%s rejected=%s registered=%s "
            "provider=%s degraded=%s",
            lobe, cycle_id, meta.get("n_proposals"), meta.get("n_rejected"),
            meta.get("registered"), meta.get("provider"), meta.get("degraded_reason"),
        )
        artifact = meta.get("artifact")
        finish_stage(
            cycle_id, _STAGE, status="done",
            artifacts=[artifact] if artifact else [],
            next_stage="adjudicate",
            note=(f"docket {meta.get('n_proposals')} proposal(s); "
                  f"lobe={lobe}; provider={meta.get('provider')}"),
            root=root,
        )
        if artifact:
            print(artifact)

    except Exception as exc:  # noqa: BLE001
        log.error("metabolism_propose[%s]: unexpected error: %s", lobe, exc)
        try:
            from scripts.metabolism_journal import finish_stage  # type: ignore[import]
            finish_stage(cycle_id, _STAGE, status="failed", note=str(exc), root=root)
        except Exception:  # noqa: BLE001
            pass


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
    parser.add_argument("--all-lobes", action="store_true",
                        help=(
                            "Iterate ALL loop-managed lobes (structured sensors + active/probation). "
                            "Each runs as its own --lobe invocation with cycle_id=<base>-<lobe_id>. "
                            "The first lobe (til) keeps the bare base cycle_id for backward compat. "
                            "Per-lobe failures isolate (continue). "
                            "Switches metabolism-propose.yml to multi-lobe iteration (R-V6-5)."
                        ))
    parser.add_argument("--dry-run", action="store_true",
                        help="Build docket but do not register contracts or write")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _ROOT

    # ── --all-lobes: iterate loop-managed lobes ─────────────────────────────
    if args.all_lobes:
        return _run_all_lobes(args, root)

    # ── Single-lobe path (backward compat) ──────────────────────────────────
    try:
        from scripts.metabolism_journal import new_cycle_id  # type: ignore[import]
        cycle_id = args.cycle_id or new_cycle_id()
    except Exception as exc:  # noqa: BLE001
        log.error("metabolism_propose: could not get cycle_id: %s", exc)
        return 0

    lobe = args.lobe or _LOBE
    _run_single_lobe(args, root, lobe, cycle_id)
    return 0


def _run_id() -> str | None:
    """Best-effort run id from the GH Actions env (for docket provenance)."""
    import os
    rid = os.environ.get("GITHUB_RUN_ID")
    return f"{rid}-propose" if rid else None


if __name__ == "__main__":
    sys.exit(main())
