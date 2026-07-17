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

    python -m scripts.metabolism_adjudicate --list-dockets --cycle-id <base_cycle_id>
        # prints every docket path on this checkout belonging to the base cycle:
        # <base>.json (til) + <base>-<lobe>.json per-lobe dockets (R-V6-5).
        # The workflow iterates these — the branch name alone carries only the
        # base id, so per-lobe dockets would otherwise never be ruled on.

Exit 0 always.
"""
from __future__ import annotations

import argparse
import json
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


def discover_cycle_dockets(root: Path, base_cycle_id: str) -> list[Path]:
    """Enumerate ALL docket files belonging to a propose branch's base cycle.

    A multi-lobe PROPOSE (R-V6-5) writes one docket per loop-managed lobe onto
    a SINGLE branch metabolism/propose-<base>: the base docket <base>.json
    (til, backward compat) plus per-lobe dockets <base>-<lobe_id>.json.
    ADJUDICATE must rule on every one of them — the branch name carries only
    the base id (first armed cycle 2026-07-13: the site-us-standouts /
    site-china-standouts dockets were silently never ruled on).

    Returns the base docket first (when present), then per-lobe dockets sorted
    by filename.  The "-" right after the base id keeps sibling cycles whose
    ids merely share a prefix (cycle-…-31 vs cycle-…-3198) out of each other's
    sweeps.  Missing dir / no matches → [].  NEVER raises.
    """
    out: list[Path] = []
    try:
        dockets_dir = root / "data" / "metabolism" / "dockets"
        base = dockets_dir / f"{base_cycle_id}.json"
        if base.is_file():
            out.append(base)
        out.extend(sorted(
            p for p in dockets_dir.glob(f"{base_cycle_id}-*.json") if p.is_file()
        ))
    except Exception as exc:  # noqa: BLE001
        log.warning("discover_cycle_dockets: %s", exc)
    return out


def _docket_lobe(docket_file: Path) -> str:
    """Lobe owning this docket, for the per-lobe circuit breaker (Gate 2).

    Per-lobe dockets (R-V6-5) carry their lobe in the docket body; fall back to
    'til' (the historical hardcode) when unreadable.  NEVER raises.
    """
    try:
        lobe = json.loads(Path(docket_file).read_text(encoding="utf-8")).get("lobe")
        return str(lobe) if lobe else _LOBE
    except Exception:  # noqa: BLE001
        return _LOBE


def _run_id(role: str, override: str | None) -> str | None:
    if override:
        return override
    rid = os.environ.get("GITHUB_RUN_ID")
    return f"{rid}-{role}" if rid else None


def _screen_reason_to_plain(screen_reason: str, orch_decision: str,
                             adv_veto: bool, has_llm_opinion: bool,
                             degraded: str | None = None,
                             *,
                             screen_allow: bool = True) -> str:
    """Map machine screen/adjudication reasons to operator-readable plain words.

    FIX 3: screen_allow (boolean from governance/screen data) drives the denial
    path instead of substring sniffing on screen_reason.  Substring sniffing on
    "collision" incorrectly matched the APPROVE sentinel "no case-law collision"
    (engine/metabolism/adjudicate.py:196).

    Rules (precedence order):
      1. DO_NOT_REBUILD collision → "collides with a standing kill ruling (DO_NOT_REBUILD)"
      2. ACTIVE_BUILD_MAP collision → "another open PR already covers this"
      3. screen_allow=False AND adversary vetoed → "safety screen and adversary review both denied"
      4. Adversary vetoed alone → "adversary review denied"
      5. screen_allow=False only → "safety screen denied: <reason>"
      6. Orchestrator denied (LLM) with screen approved → "the model denied; safety screen approved"
      7. Authorized → "authorized"
      Never raises.
    """
    try:
        r = str(screen_reason or "").lower()
        if "do_not_rebuild" in r or "do not rebuild" in r or "standing kill" in r:
            return "collides with a standing kill ruling (DO_NOT_REBUILD)"
        if "active_build_map" in r or "open lane" in r or "open pr already" in r:
            return "another open PR already covers this"
        # FIX 3: use screen_allow boolean directly — substring sniffing on "collision"
        # was incorrectly matching the APPROVE sentinel "no case-law collision".
        screen_denied = not screen_allow
        if screen_denied and adv_veto:
            return "safety screen and adversary review both denied"
        if screen_denied:
            short = str(screen_reason or "")[:80]
            return f"safety screen denied: {short}"
        if adv_veto and not has_llm_opinion:
            return f"adversary review denied (no model opinion — fail-closed)"
        if adv_veto:
            return "adversary review denied"
        if orch_decision == "deny":
            return "the model denied; safety screen approved"
        if orch_decision == "grant":
            return "authorized"
        return str(screen_reason or "")[:120]
    except Exception:  # noqa: BLE001
        return str(screen_reason or "")[:120]


def _derive_verdict_plain(
    pid: str,
    cycle_id: str,
    docket_path_str: str,
    *,
    root: "Path | None" = None,
) -> tuple[str, str]:
    """Return (decision, reason_plain) for a proposal after two-key resolve runs.

    decision: "authorized" | "denied" | "never_ruled"
    reason_plain: plain-word string (<=160 chars)
    NEVER raises.
    """
    try:
        from engine.metabolism.adjudicate import (  # noqa: PLC0415
            _events_for_target, _cycle_prefix, _target,
            _latest_row, EVT_ADJUDICATION, EVT_ADVERSARY,
            ROLE_ORCH, ROLE_ADV, ROLE_TWO_KEY,
        )
        from pathlib import Path as _Path  # noqa: PLC0415
        dp = _Path(docket_path_str) if docket_path_str else None
        if dp and dp.exists():
            import json as _json  # noqa: PLC0415
            docket = _json.loads(dp.read_text(encoding="utf-8"))
            prop = next((p for p in (docket.get("proposals") or [])
                         if str(p.get("proposal_id")) == pid), {})
            tier = str(prop.get("tier") or "T1").strip().upper()
        else:
            tier = "T1"

        all_rows = _events_for_target(root, _cycle_prefix(cycle_id))
        tgt = _target(cycle_id, pid)
        rows = [e for e in all_rows if e.get("target") == tgt]

        orch = _latest_row(rows, EVT_ADJUDICATION, ROLE_ORCH)
        adv = _latest_row(rows, EVT_ADVERSARY, ROLE_ADV)
        two_key = _latest_row(rows, EVT_ADJUDICATION, ROLE_TWO_KEY)

        if two_key:
            authorized = bool((two_key.get("after") or {}).get("authorized"))
            decision = "authorized" if authorized else "denied"
        elif orch:
            orch_decision = str((orch.get("after") or {}).get("decision") or "deny")
            adv_veto = bool((adv.get("after") or {}).get("veto")) if adv else (tier != "T0")
            # FIX 7: use "authorized" not "granted" — single vocabulary for rollup counters
            # and app.js statusCls.
            decision = "authorized" if (orch_decision == "grant" and not adv_veto) else "denied"
        else:
            # FIX 6: no governance rows means adjudication never ran — not a denial.
            return "never_ruled", "never reached adjudication — orchestrator/adversary did not run"

        orch_decision_str = str((orch.get("after") or {}).get("decision") or "deny") if orch else "deny"
        screen_allow = bool((orch.get("after") or {}).get("screen_allow", True)) if orch else True
        screen_reason = str((orch.get("after") or {}).get("screen_reason") or "") if orch else ""
        adv_veto_flag = bool((adv.get("after") or {}).get("veto")) if adv else (tier != "T0")
        has_llm_opinion = bool((orch.get("after") or {}).get("llm_opinion")) if orch else False
        degraded = None

        # FIX 3: pass screen_allow explicitly so the mapper uses the boolean rather than
        # substring-sniffing on screen_reason (which misclassified "no case-law collision").
        plain = _screen_reason_to_plain(
            screen_reason,
            orch_decision_str, adv_veto_flag, has_llm_opinion, degraded,
            screen_allow=screen_allow,
        )
        if decision == "authorized":
            plain = "authorized by orchestrator and adversary"
        return decision, plain[:160]
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_adjudicate._derive_verdict_plain(%s): %s", pid, exc)
        return "denied", "verdict derivation failed"


def _append_achievements_verdicts(
    cycle_id: str,
    docket_file: "Path",
    role: str,
    results: list,
    *,
    root: "Path | None" = None,
    usage_meta: "dict | None" = None,
) -> None:
    """Append verdict rows to journal achievements.verdicts after adjudication.

    Called once per role (orchestrator/adversary/resolve). The resolve role
    triggers the final verdict summary.
    usage_meta: optional {tokens, est_cost_usd} captured from the LLM call —
    written into each verdict row when present.
    NEVER raises.
    """
    try:
        import json as _json  # noqa: PLC0415
        from datetime import datetime, timezone  # noqa: PLC0415
        from scripts.metabolism_journal import _read_journal, _write_journal  # type: ignore[import]  # noqa: PLC0415

        j = _read_journal(cycle_id, root)
        achievements = j.get("achievements") or {}

        if role == "resolve":
            # Resolve stage: set final decision+reason for each proposal
            existing_verdicts = achievements.get("verdicts") or []
            existing_v_ids = {v.get("id") for v in existing_verdicts if v.get("id")}

            # Load docket to enumerate all proposals
            dp = docket_file
            try:
                proposals_raw = _json.loads(dp.read_text(encoding="utf-8")).get("proposals") or []
            except Exception:  # noqa: BLE001
                proposals_raw = []

            adjudicated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            docket_pids = {str(prop.get("proposal_id") or "") for prop in proposals_raw
                           if prop.get("proposal_id")}

            # Pre-compute optional cost fields from usage_meta (one LLM call per role)
            _v_tokens: "int | None" = None
            _v_cost: "float | None" = None
            if usage_meta:
                _raw_tok = usage_meta.get("tokens")
                _raw_inp = usage_meta.get("input_tokens")
                _raw_out = usage_meta.get("output_tokens")
                if _raw_tok is not None:
                    _v_tokens = int(_raw_tok)
                elif _raw_inp is not None or _raw_out is not None:
                    _v_tokens = int((_raw_inp or 0) + (_raw_out or 0))
                _raw_cost = usage_meta.get("est_cost_usd")
                if _raw_cost is not None:
                    _v_cost = float(_raw_cost)

            # Add verdicts for proposals that were actually adjudicated
            for prop in proposals_raw:
                pid = str(prop.get("proposal_id") or "")
                if not pid or pid in existing_v_ids:
                    continue
                decision, reason_plain = _derive_verdict_plain(
                    pid, cycle_id, str(dp), root=root,
                )
                vrow: dict = {
                    "id": pid,
                    "decision": decision,
                    "reason_plain": reason_plain[:160],
                    "adjudicated_at": adjudicated_at,
                }
                if _v_tokens is not None:
                    vrow["tokens"] = _v_tokens
                if _v_cost is not None:
                    vrow["est_cost_usd"] = _v_cost
                existing_verdicts.append(vrow)
                existing_v_ids.add(pid)

            # Mark proposals in achievements.proposals that have no verdict
            # (they were proposed but resolve never ran for them — multi-docket case)
            existing_proposals = achievements.get("proposals") or []
            never_ruled_at = adjudicated_at
            for prop_row in existing_proposals:
                pid = str(prop_row.get("id") or "")
                if not pid or pid in existing_v_ids:
                    continue
                existing_verdicts.append({
                    "id": pid,
                    "decision": "never_ruled",
                    "reason_plain": "adjudication did not reach this docket",
                    "adjudicated_at": never_ruled_at,
                })
                existing_v_ids.add(pid)

            achievements["verdicts"] = existing_verdicts

        j["achievements"] = achievements
        _write_journal(cycle_id, j, root)
        log.info(
            "metabolism_adjudicate: achievements.verdicts updated role=%s cycle=%s",
            role, cycle_id,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("metabolism_adjudicate._append_achievements_verdicts(%s): %s", cycle_id, exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Metabolism ADJUDICATE stage (A5)")
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--role", choices=_VALID_ROLES,
                        help="Required unless --list-dockets is given")
    parser.add_argument("--docket-file", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--lane", default="metabolism-adjudicate")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-dockets", action="store_true",
                        help=(
                            "Print every docket path for the base --cycle-id "
                            "(base + per-lobe, one per line, R-V6-5) and exit. "
                            "No guards, no journal — pure enumeration."
                        ))
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else _ROOT

    # ── --list-dockets: pure enumeration for the workflow's per-docket loop ─
    if args.list_dockets:
        for p in discover_cycle_dockets(root, args.cycle_id):
            try:
                print(p.relative_to(root))
            except ValueError:
                print(p)
        return 0

    if not args.role:
        parser.error("--role is required unless --list-dockets is given")

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
    # The lobe comes from the docket body (per-lobe dockets, R-V6-5); 'til'
    # remains the fallback so the historical single-lobe path is unchanged.
    _lobe = _docket_lobe(docket_file)
    try:
        from scripts.metabolism_budget import (  # type: ignore[import]
            is_lobe_paused, init_cycle, record_spend,
        )
        if is_lobe_paused(_lobe, root=root):
            reason = f"lobe '{_lobe}' circuit breaker tripped — no-op"
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
            # ── Achievements: append final verdicts after two-key resolve ─────
            # Aggregate adjudication cost from the budget ledger (orchestrator +
            # adversary LLM calls were recorded earlier; resolve makes no LLM call).
            _resolve_usage_meta: "dict | None" = None
            try:
                from scripts.metabolism_budget import _read_ledger as _bl  # type: ignore[import]  # noqa: PLC0415
                _bl_data = _bl(root)
                if _bl_data.get("cycle_id") == cycle_id:
                    _adj_entries = [
                        e for e in (_bl_data.get("entries") or [])
                        if str(e.get("stage") or "").startswith("adjudicate")
                    ]
                    _tot_tok = sum(int(e.get("tokens") or 0) for e in _adj_entries)
                    _tot_usd = sum(float(e.get("usd") or 0.0) for e in _adj_entries)
                    if _tot_tok or _tot_usd:
                        _resolve_usage_meta = {}
                        if _tot_tok:
                            _resolve_usage_meta["tokens"] = _tot_tok
                        if _tot_usd:
                            _resolve_usage_meta["est_cost_usd"] = round(_tot_usd, 6)
            except Exception:  # noqa: BLE001
                pass
            if not args.dry_run:
                _append_achievements_verdicts(
                    cycle_id, docket_file, "resolve", list(res.values()),
                    root=root, usage_meta=_resolve_usage_meta,
                )
        else:
            _adj_usage_out: list = []
            results = adjudicate_role(role, cycle_id, docket_file,
                                      run_id=run_id, root=root, dry_run=args.dry_run,
                                      _usage_out=_adj_usage_out)
            # ── Real token capture + cost recording ───────────────────────────
            _usage = _adj_usage_out[0] if _adj_usage_out else {}
            _input_tok = int(_usage.get("input_tokens") or 0)
            _output_tok = int(_usage.get("output_tokens") or 0)
            _cache_read = int(_usage.get("cache_read_tokens") or 0)
            _cache_create = int(_usage.get("cache_creation_tokens") or 0)
            _used_model = str(_usage.get("model") or "claude-opus-4-8")
            _real_tokens = (
                _input_tok + _output_tok
                if (_input_tok or _output_tok) else _EST_TOKENS_PER_CALL
            )

            _est_cost: float | None = None
            try:
                from lib.ai_costs import estimate_cost_usd as _est_fn  # type: ignore[import]
                _est_cost = _est_fn(
                    _used_model, _input_tok, _output_tok, _cache_read, _cache_create,
                    root=root,
                )
            except Exception:  # noqa: BLE001
                pass

            # FIX 5: pass usd ONLY for metered (claude_api/deepseek) lanes so the $25
            # circuit-breaker tracks billed dollars only.  Adjudicate uses OAuth by
            # default (subscription) — cost_basis tells us which.
            _adj_provider_name = _usage.get("provider") or "claude_oauth"
            _adj_cost_basis = (
                "metered"
                if _adj_provider_name in ("claude_api", "deepseek", "anthropic")
                else "subscription"
            )
            _is_adj_metered = _adj_cost_basis == "metered"
            _adj_budget_usd = (_est_cost if _est_cost is not None else 0.0) if _is_adj_metered else 0.0

            # Record token spend for the LLM roles (best-effort).
            try:
                if record_spend is not None:
                    record_spend(
                        cycle_id, stage,
                        tokens=_real_tokens,
                        usd=_adj_budget_usd,
                        note=f"{role} n={len(results)}",
                        root=root,
                    )
            except Exception:  # noqa: BLE001
                pass

            try:
                from lib.ai_costs import record_usage as _rec_usage  # type: ignore[import]
                _rec_usage(
                    lane="metabolism-adjudicate",
                    provider="claude_oauth",
                    model=_used_model,
                    input_tokens=_input_tok,
                    output_tokens=_output_tok,
                    cache_read_tokens=_cache_read,
                    cache_creation_tokens=_cache_create,
                    cost_basis="subscription",
                    cycle_id=cycle_id,
                    stage=stage,
                    est_cost_usd=_est_cost,
                    root=root,
                )
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
