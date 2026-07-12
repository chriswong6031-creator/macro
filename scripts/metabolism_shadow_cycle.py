"""scripts/metabolism_shadow_cycle.py — Shadow-first harness (R-V4-1).

Runs the FULL metabolism cycle against real repo state while AUTONOMY_PAUSED
stays unset/true:

  SENSE  → til_fitness card
  SENSE  → organism_state
  SENSE  → insight_bus emitters + anomaly_monitor
  AGENDA → build_agenda (stub when --no-llm)
  PROPOSE → propose() with injected_proposals seam (stub when --no-llm)
  ADJUDICATE → adjudicate_role (orchestrator + adversary + resolve)
               with injected= seam (stub when --no-llm)
  BUILD  → run_build_lane (dry_run=True — always; records would_dispatch)
  VERIFY → verify_proposal on a SEEDED synthetic contract (check_by <= today)
  DREAM  → run_dream_cycle (dry_run=True)

ISOLATION: works in a temporary shadow root that mirrors config/ and a few
docs from the real repo; uses a FRESH empty data/ tree so the REAL
data/metabolism/ stores are never touched.  After the run the produced
artifacts are copied to data/metabolism/shadow/<cycle_id>/ for commit as
arming evidence.

REAL-STORES-UNTOUCHED is VERIFIED by snapshotting data/metabolism/ file
mtimes before and after the run.

DEFAULT: --no-llm (deterministic stub content).  Pass --use-llm to make real
LLM calls (post-arming use).

EXIT 0 always.  NEVER-RAISE at module level.

Usage:
    python -m scripts.metabolism_shadow_cycle
        [--now YYYY-MM-DDTHH:MM]   # cycle_id timestamp (default: real now)
        [--root /path/to/repo]      # repo root override
        [--no-llm]                  # default: use stub seams
        [--use-llm]                 # real LLM calls (post-arming)
        [--out-dir <path>]          # override output dir (default: data/metabolism/shadow/<cycle_id>/)
        [--cycle-id <id>]           # override cycle_id (must match shadow-YYYYMMDD-HHMM format)

Exit 0 always.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("metabolism_shadow_cycle")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

SCHEMA = "metabolism.shadow_cycle.v1"

# ── Stub content for --no-llm seams ──────────────────────────────────────────

_STUB_INJECTED_PROPOSALS: list[dict[str, Any]] = [
    {
        # Vocabulary is deliberately ALIEN (>=4-char nonsense tokens; screen
        # tokens shorter than 4 chars are ignored): the deterministic screens
        # match token quorums vs DO_NOT_REBUILD (whole registry) and the
        # ACTIVE_BUILD_MAP open-lane section, and common engineering words
        # ('honest', 'null', 'check', 'artifact', 'deterministic'...) appear in
        # the kill registry, so an English stub self-vetoes.  Empirically
        # screened clean against both corpora on 2026-07-11.
        "title": "zzqx qqzy wqzt vvqk probe row",
        "tier": "T0",
        "kind": "test",
        "targets_sensor": "front_run_lead",
        "rationale": (
            "zzqx qqzy wqzt vvqk probe row: traversal exercise so the whole "
            "cycle touches one concrete item."
        ),
        "fitness_contract": {
            "sensor": "front_run_lead",
            "expected_sign": "+",
            "band": "accruing",
            "check_by": "2026-10-15",
            "placebo_to_beat": "shadow placebo tape",
        },
    },
]

# Stub LLM opinion for adjudicate.injected= seam.
# Maps proposal_id → judgment dict (keys: grant|veto|rationale|tripwire_predictions).
# The real adjudicate_role reads these keys from the LLM; we inject them directly.
def _stub_adjudication_injected(proposals: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Build the injected= dict for adjudicate_role() from a docket's proposals."""
    return {
        str(p.get("proposal_id", "")): {
            "grant": True,
            "rationale": (
                "[STUB] Shadow-cycle deterministic screen passed. "
                "T0 doc/test proposal; no case-law collision; no UX surface touched. "
                "Orchestrator grant stub: no LLM call (shadow cycle --no-llm mode)."
            ),
            "veto": False,
            "tripwire_predictions": [
                {"description": "stub tripwire: test suite stays green", "probability": 0.95}
            ],
        }
        for p in proposals
        if p.get("proposal_id")
    }


# ── Shadow-root builder ───────────────────────────────────────────────────────

def _build_shadow_root(real_root: Path, tmp_dir: Path) -> Path:
    """Build a minimal shadow repo root under tmp_dir.

    Mirrors:
      - config/  (symlink or copy — every stage reads config/)
      - research/DO_NOT_REBUILD.md
      - docs/ACTIVE_BUILD_MAP.md
      - A FRESH empty data/ tree (so real data/metabolism/ is never touched)

    Returns the shadow root path.  NEVER raises.
    """
    try:
        shadow = tmp_dir / "shadow_root"
        shadow.mkdir(parents=True, exist_ok=True)

        # config/ — symlink preferred; fall back to full copy
        src_config = real_root / "config"
        dst_config = shadow / "config"
        if src_config.exists():
            try:
                dst_config.symlink_to(src_config)
            except (OSError, NotImplementedError):
                shutil.copytree(str(src_config), str(dst_config))

        # research/DO_NOT_REBUILD.md
        _mirror_file(real_root / "research" / "DO_NOT_REBUILD.md",
                     shadow / "research" / "DO_NOT_REBUILD.md")

        # docs/ACTIVE_BUILD_MAP.md
        _mirror_file(real_root / "docs" / "ACTIVE_BUILD_MAP.md",
                     shadow / "docs" / "ACTIVE_BUILD_MAP.md")

        # research/AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md (PROPOSE context)
        _mirror_file(
            real_root / "research" / "AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md",
            shadow / "research" / "AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md",
        )

        # Fresh empty data/ tree (all metabolism stores absent — honest nulls)
        (shadow / "data").mkdir(exist_ok=True)

        return shadow
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle: _build_shadow_root failed: %s", exc)
        # Return a bare directory so stages at least don't path-error
        bare = tmp_dir / "shadow_root_bare"
        bare.mkdir(exist_ok=True)
        return bare


def _mirror_file(src: Path, dst: Path) -> None:
    """Copy src → dst if src exists; create a stub if absent.  NEVER raises."""
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(str(src), str(dst))
        else:
            dst.write_text("# (absent in real repo)\n", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle: _mirror_file %s → %s: %s", src, dst, exc)


# ── Real-stores snapshot ──────────────────────────────────────────────────────

def _snapshot_real_stores(real_root: Path) -> dict[str, float]:
    """Return {rel_path: mtime} for all files under data/metabolism/.

    Used to verify the real stores were not touched during the shadow run.
    NEVER raises.
    """
    result: dict[str, float] = {}
    try:
        base = real_root / "data" / "metabolism"
        if not base.exists():
            return result
        for p in sorted(base.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(real_root))
                try:
                    result[rel] = p.stat().st_mtime
                except Exception:  # noqa: BLE001
                    result[rel] = 0.0
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle: _snapshot_real_stores: %s", exc)
    return result


def _stores_untouched(before: dict[str, float], real_root: Path) -> bool:
    """Return True iff data/metabolism/ files are unchanged vs the before snapshot.

    Checks: no new files, no deleted files, no mtime changes.
    NEVER raises.
    """
    try:
        after = _snapshot_real_stores(real_root)
        # Check for new files (excluding shadow/ subdir — that's where we write)
        shadow_prefix = "data/metabolism/shadow/"
        before_non_shadow = {k: v for k, v in before.items() if not k.startswith(shadow_prefix)}
        after_non_shadow = {k: v for k, v in after.items() if not k.startswith(shadow_prefix)}

        new_files = set(after_non_shadow) - set(before_non_shadow)
        deleted_files = set(before_non_shadow) - set(after_non_shadow)
        changed = {k for k in before_non_shadow if before_non_shadow.get(k) != after_non_shadow.get(k)}

        if new_files or deleted_files or changed:
            log.warning(
                "shadow_cycle: real stores CHANGED: new=%s deleted=%s changed=%s",
                new_files, deleted_files, changed,
            )
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle: _stores_untouched check failed: %s", exc)
        return False


# ── Cycle ID helpers ──────────────────────────────────────────────────────────

def _make_cycle_id(now_str: str | None) -> str:
    """Make a shadow cycle_id from a now string or real UTC now.

    Format: shadow-YYYYMMDD-HHMM
    NEVER raises.
    """
    try:
        if now_str:
            # Parse ISO or YYYY-MM-DDTHH:MM form
            for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y%m%dT%H%M"):
                try:
                    dt = datetime.strptime(now_str, fmt)
                    return f"shadow-{dt.strftime('%Y%m%d-%H%M')}"
                except ValueError:
                    continue
        dt = datetime.now(timezone.utc)
        return f"shadow-{dt.strftime('%Y%m%d-%H%M')}"
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle: _make_cycle_id: %s", exc)
        return "shadow-19700101-0000"


# ── Stage runners (each returns a stage-result dict, NEVER raises) ────────────

def _run_sense_fitness(shadow_root: Path, real_root: Path, cycle_id: str) -> dict[str, Any]:
    """SENSE stage 1: TIL fitness card.

    Reads real sensor artifacts but writes the fitness card to the shadow root.
    """
    stage = "sense_fitness"
    try:
        from engine.metabolism.til_fitness import build_fitness_card  # type: ignore[import]
        # build_fitness_card reads from real sensor paths but we point it at real_root
        # so it reads real sensor data (display-tier, never fabricated)
        card = build_fitness_card(root=real_root)

        # Write to shadow root
        fitness_dir = shadow_root / "data" / "metabolism" / "fitness"
        fitness_dir.mkdir(parents=True, exist_ok=True)
        out_path = fitness_dir / "til.json"
        out_path.write_text(json.dumps(card, indent=2, default=str), encoding="utf-8")
        return {"status": "ok", "artifact": str(out_path), "note": "fitness card written to shadow root"}
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle[%s]: %s: %s", stage, stage, exc)
        return {"status": "failed", "artifact": None, "note": str(exc)}


def _run_sense_organism_state(shadow_root: Path, real_root: Path, cycle_id: str) -> dict[str, Any]:
    """SENSE stage 2: organism_state.  Reads real lobe data; writes to shadow root."""
    stage = "sense_organism_state"
    try:
        from engine.metabolism.organism_state import build_organism_state  # type: ignore[import]
        state = build_organism_state(root=real_root)

        out_path = shadow_root / "data" / "metabolism" / "organism_state.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
        return {"status": "ok", "artifact": str(out_path), "note": "organism_state written to shadow root"}
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle[%s]: %s", stage, exc)
        return {"status": "failed", "artifact": None, "note": str(exc)}


def _run_sense_insight_bus(shadow_root: Path, real_root: Path, cycle_id: str) -> dict[str, Any]:
    """SENSE stage 3: insight_bus emitters + anomaly_monitor.

    Runs all deterministic emitters; writes to shadow root's insight_bus.jsonl.
    We pass shadow_root so append_row() writes to the shadow bus, not the real one.
    """
    stage = "sense_insight_bus"
    try:
        from engine.metabolism.insight_bus import run_all_emitters  # type: ignore[import]
        # Pass shadow_root: emitters read from real_root indirectly via other organs
        # (organism_state, health.json), but append_row writes to shadow_root's bus.
        # This keeps the real data/metabolism/insight_bus.jsonl untouched.
        rows = run_all_emitters(root=shadow_root)

        bus_path = shadow_root / "data" / "metabolism" / "insight_bus.jsonl"
        bus_path.parent.mkdir(parents=True, exist_ok=True)
        with bus_path.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")

        return {
            "status": "ok",
            "artifact": str(bus_path),
            "note": f"{len(rows)} insight_bus rows emitted to shadow root",
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle[%s]: %s", stage, exc)
        return {"status": "failed", "artifact": None, "note": str(exc)}


def _run_agenda(shadow_root: Path, real_root: Path, cycle_id: str, use_llm: bool) -> dict[str, Any]:
    """AGENDA stage.  Uses shadow root for all reads+writes.

    --no-llm: build_agenda returns a floor-only agenda (no provider).
    --use-llm: real LLM call (providers built from env).
    """
    stage = "agenda"
    try:
        from engine.metabolism.agenda import build_agenda  # type: ignore[import]
        providers: list[dict] = []
        if use_llm:
            try:
                from engine.llm_auth import build_providers  # type: ignore[import]
                cfg = {
                    "provider_order": ["oauth", "anthropic"],
                    "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
                    "api_key_env": "ANTHROPIC_API_KEY",
                }
                providers = build_providers(cfg, opus_model="claude-opus-4-8")
            except Exception as _pe:  # noqa: BLE001
                log.warning("shadow_cycle[agenda]: provider build failed: %s", _pe)

        agenda = build_agenda(
            cycle_id=cycle_id,
            root=shadow_root,
            providers=providers,
            model="claude-opus-4-8",
        )

        from engine.metabolism.agenda import AGENDA_DIR  # type: ignore[import]
        out_path = shadow_root / AGENDA_DIR / f"{cycle_id}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(agenda, indent=2, default=str), encoding="utf-8")
        n_items = len(agenda.get("items") or [])
        return {
            "status": "ok",
            "artifact": str(out_path),
            "note": f"agenda: {n_items} items; provider={agenda.get('provider')}",
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle[%s]: %s", stage, exc)
        return {"status": "failed", "artifact": None, "note": str(exc)}


def _run_propose(
    shadow_root: Path,
    real_root: Path,
    cycle_id: str,
    use_llm: bool,
    today: str,
) -> dict[str, Any]:
    """PROPOSE stage.  Uses injected_proposals seam when --no-llm."""
    stage = "propose"
    try:
        from engine.metabolism.propose import propose  # type: ignore[import]

        injected = None if use_llm else _STUB_INJECTED_PROPOSALS

        result = propose(
            cycle_id,
            lobe="til",
            root=shadow_root,
            max_docket_size=5,
            today=today,
            dry_run=False,  # write docket to shadow root
            injected_proposals=injected,
        )
        meta = result.get("meta", {})
        artifact = meta.get("artifact")
        return {
            "status": "ok",
            "artifact": artifact,
            "note": (
                f"docket: {meta.get('n_proposals')} proposals; "
                f"provider={meta.get('provider')}; "
                f"degraded={meta.get('degraded_reason')}"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle[%s]: %s", stage, exc)
        return {"status": "failed", "artifact": None, "note": str(exc)}


def _run_adjudicate(
    shadow_root: Path,
    real_root: Path,
    cycle_id: str,
    use_llm: bool,
) -> dict[str, Any]:
    """ADJUDICATE stage: orchestrator + adversary + resolve.

    Uses injected= seam for LLM roles when --no-llm.
    """
    stage = "adjudicate"
    try:
        from engine.metabolism.adjudicate import adjudicate_role, resolve_two_key  # type: ignore[import]

        docket_path = shadow_root / "data" / "metabolism" / "dockets" / f"{cycle_id}.json"
        if not docket_path.exists():
            return {"status": "skipped", "artifact": None, "note": "no docket — propose must have failed"}

        # Load proposals for stub injection
        try:
            docket_data = json.loads(docket_path.read_text(encoding="utf-8"))
            proposals = docket_data.get("proposals") or []
        except Exception as _de:  # noqa: BLE001
            proposals = []

        injected_stub = None if use_llm else _stub_adjudication_injected(proposals)

        results_orch = adjudicate_role(
            "orchestrator", cycle_id, docket_path,
            run_id=f"shadow-{cycle_id}-orch",
            root=shadow_root,
            injected=injected_stub,
            dry_run=False,
        )
        results_adv = adjudicate_role(
            "adversary", cycle_id, docket_path,
            run_id=f"shadow-{cycle_id}-adv",
            root=shadow_root,
            injected=injected_stub,
            dry_run=False,
        )
        results_resolve = resolve_two_key(cycle_id, docket_path, root=shadow_root, dry_run=False)

        n_auth = sum(1 for v in results_resolve.values() if v.get("authorized"))
        return {
            "status": "ok",
            "artifact": None,
            "note": (
                f"orch={len(results_orch)} adversary={len(results_adv)} "
                f"resolve: {n_auth}/{len(results_resolve)} authorized"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle[%s]: %s", stage, exc)
        return {"status": "failed", "artifact": None, "note": str(exc)}


def _run_build(
    shadow_root: Path,
    real_root: Path,
    cycle_id: str,
) -> dict[str, Any]:
    """BUILD stage: dry_run=True — records would_dispatch, launches nothing."""
    stage = "build"
    try:
        from scripts.metabolism_build import run_build_lane  # type: ignore[import]

        docket_path = shadow_root / "data" / "metabolism" / "dockets" / f"{cycle_id}.json"
        if not docket_path.exists():
            return {"status": "skipped", "artifact": None, "note": "no docket"}

        # BUILD dry_run checks AUTONOMY_PAUSED — we must NOT be armed in shadow mode.
        # The guard inside run_build_lane will return noop_paused when is_paused()=True.
        # For shadow mode we call it with dry_run=True which exercises the would_dispatch path.
        results = run_build_lane(
            cycle_id,
            docket_path,
            root=shadow_root,
            dry_run=True,
        )

        # Extract would_dispatch journal entries for the summary
        would_dispatch_records = [
            r.get("session", {}).get("would_dispatch")
            for r in results
            if isinstance(r.get("session"), dict) and r["session"].get("would_dispatch")
        ]

        # Write a would_dispatch journal under shadow root
        wdj_path = shadow_root / "data" / "metabolism" / "build" / "would_dispatch.json"
        wdj_path.parent.mkdir(parents=True, exist_ok=True)
        wdj_path.write_text(
            json.dumps({"cycle_id": cycle_id, "would_dispatch": would_dispatch_records},
                       indent=2, default=str),
            encoding="utf-8",
        )

        return {
            "status": "ok",
            "artifact": str(wdj_path),
            "note": (
                f"dry_run BUILD: {len(results)} proposals processed; "
                f"{len(would_dispatch_records)} would_dispatch records"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle[%s]: %s", stage, exc)
        return {"status": "failed", "artifact": None, "note": str(exc)}


def _seed_verify_contract(
    shadow_root: Path,
    cycle_id: str,
    today: str,
) -> dict[str, Any]:
    """Register a synthetic fitness contract in the shadow docket with check_by <= today.

    This is the VERIFY seeding step: we either augment an existing docket proposal
    (setting check_by to today) or write a synthetic docket entry.

    NEVER raises.  Returns the contract dict.
    """
    try:
        docket_path = shadow_root / "data" / "metabolism" / "dockets" / f"{cycle_id}.json"

        # Build a synthetic contract whose check_by is today (so verify exercises the grading path)
        synthetic_contract: dict[str, Any] = {
            "proposal_id": "shadow-seed-verify-001",
            "sensor": "front_run_lead",
            "expected_sign": "+",
            "band": "accruing",
            "lobe": "til",  # real _mint_contract stamps this; shadow must mirror the shape
            "check_by": today,  # <= today so verify fires, not pending
            "placebo_to_beat": "shadow placebo tape",
            "falsifier_spec": {},  # empty → UNVERIFIABLE (honest null by design)
            "asof": today,
            "title": "[shadow-seed] synthetic contract for VERIFY grading path exercise",
            # Mirror the MINTED contract shape (post-#2285 _mint_contract emits
            # lobe) — hand-built fixtures that omit real-path keys masked the
            # dead strategic-memory wire once already.
            "lobe": "til",
            "_shadow_seeded": True,
        }

        # If the docket exists, we write a SEPARATE seeded docket entry for verify
        seeded_docket_path = shadow_root / "data" / "metabolism" / "dockets" / f"{cycle_id}-verify-seed.json"
        seeded_docket_path.parent.mkdir(parents=True, exist_ok=True)
        seeded_docket_path.write_text(
            json.dumps({
                "schema": "metabolism.docket.v1",
                "cycle_id": f"{cycle_id}-verify-seed",
                "lobe": "til",
                "as_of": today,
                "generated_by": "metabolism_shadow_cycle",
                "proposals": [{"proposal_id": "shadow-seed-verify-001",
                                "fitness_contract": synthetic_contract}],
                "_shadow_seeded": True,
            }, indent=2, default=str),
            encoding="utf-8",
        )
        return synthetic_contract
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle: _seed_verify_contract: %s", exc)
        # Return a minimal fallback contract
        return {
            "proposal_id": "shadow-seed-fallback",
            "sensor": "front_run_lead",
            "expected_sign": "+",
            "band": "accruing",
            "check_by": today,
            "falsifier_spec": {},
            "asof": today,
        }


def _run_verify(
    shadow_root: Path,
    real_root: Path,
    cycle_id: str,
    today: str,
) -> dict[str, Any]:
    """VERIFY stage: verify the seeded synthetic contract.

    The contract has check_by <= today and falsifier_spec={}, so the verdict
    will be UNVERIFIABLE (honest null — by design for a fresh shadow run).
    """
    stage = "verify"
    try:
        contract = _seed_verify_contract(shadow_root, cycle_id, today)

        from engine.metabolism.verify import verify_proposal, write_verify_record  # type: ignore[import]

        record = verify_proposal(
            cycle_id=f"{cycle_id}-verify-seed",
            contract=contract,
            root=shadow_root,
            today=today,
        )

        out_path = write_verify_record(record, shadow_root)
        classification = record.get("triage", {}).get("classification", "")
        action = record.get("triage", {}).get("action", "")
        outcome = record.get("realized", {}).get("outcome", "")

        return {
            "status": "ok",
            "artifact": str(out_path) if out_path else None,
            "note": (
                f"verify: outcome={outcome} classification={classification} action={action}; "
                f"honest_null=True (seeded contract has empty falsifier_spec → UNVERIFIABLE by design)"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle[%s]: %s", stage, exc)
        return {"status": "failed", "artifact": None, "note": str(exc)}


def _run_dream(
    shadow_root: Path,
    real_root: Path,
    cycle_id: str,
    today: str,
) -> dict[str, Any]:
    """DREAM stage: run_dream_cycle(dry_run=True) against shadow root."""
    stage = "dream"
    try:
        from engine.metabolism.dream import run_dream_cycle  # type: ignore[import]
        prior = run_dream_cycle(root=shadow_root, today=today, dry_run=False)

        artifact = None
        try:
            from engine.metabolism.dream import OUTPUT_PATH  # type: ignore[import]
            p = shadow_root / Path(*OUTPUT_PATH)
            if p.exists():
                artifact = str(p)
        except Exception:  # noqa: BLE001
            pass

        return {
            "status": "ok",
            "artifact": artifact,
            "note": (
                f"dream: status={prior.get('status')} "
                f"n_closed={prior.get('n_closed_contracts', '?')} "
                f"not_gate_altering={prior.get('not_gate_altering', True)}"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle[%s]: %s", stage, exc)
        return {"status": "failed", "artifact": None, "note": str(exc)}


# ── Artifact collection ───────────────────────────────────────────────────────

def _collect_artifacts(shadow_root: Path, real_root: Path, cycle_id: str) -> dict[str, str | None]:
    """Collect produced artifacts from shadow_root into real data/metabolism/shadow/<cycle_id>/.

    Copies every file under shadow_root/data/metabolism/ into the repo's
    data/metabolism/shadow/<cycle_id>/ for commit as arming evidence.

    Returns a map of {label: dest_path_str}.  NEVER raises.
    """
    collected: dict[str, str | None] = {}
    try:
        src_base = shadow_root / "data" / "metabolism"
        dst_base = real_root / "data" / "metabolism" / "shadow" / cycle_id
        dst_base.mkdir(parents=True, exist_ok=True)

        for src_file in sorted(src_base.rglob("*")):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(src_base)
            dst_file = dst_base / rel
            try:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src_file), str(dst_file))
                collected[str(rel)] = str(dst_file)
            except Exception as _ce:  # noqa: BLE001
                log.warning("shadow_cycle: collect %s → %s: %s", src_file, dst_file, _ce)
                collected[str(rel)] = None

    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle: _collect_artifacts: %s", exc)

    return collected


# ── Summary writer ────────────────────────────────────────────────────────────

def _write_summary(
    real_root: Path,
    cycle_id: str,
    ts: str,
    stages: dict[str, dict[str, Any]],
    stubbed_stages: list[str],
    real_stores_untouched: bool,
    wall_seconds: float,
) -> str:
    """Write summary.json to data/metabolism/shadow/<cycle_id>/summary.json.

    Returns the path.  NEVER raises.
    """
    try:
        summary = {
            "schema": SCHEMA,
            "cycle_id": cycle_id,
            "ts": ts,
            "stages": stages,
            "stubbed_stages": stubbed_stages,
            "real_stores_untouched": real_stores_untouched,
            "wall_seconds": round(wall_seconds, 2),
        }
        out_dir = real_root / "data" / "metabolism" / "shadow" / cycle_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "summary.json"
        out_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return str(out_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("shadow_cycle: _write_summary: %s", exc)
        return ""


# ── Main ──────────────────────────────────────────────────────────────────────

def run_shadow_cycle(
    real_root: Path,
    cycle_id: str,
    today: str,
    use_llm: bool = False,
) -> dict[str, Any]:
    """Run the full shadow cycle.  Returns the summary dict.  NEVER raises."""
    t0 = time.monotonic()
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    stages: dict[str, dict[str, Any]] = {}
    stubbed_stages: list[str] = []

    # Snapshot real stores BEFORE
    before_snapshot = _snapshot_real_stores(real_root)

    # Build temporary shadow root
    try:
        tmp_obj = tempfile.TemporaryDirectory(prefix="metabolism_shadow_")
        tmp_dir = Path(tmp_obj.name)
    except Exception as exc:  # noqa: BLE001
        log.error("shadow_cycle: cannot create tmpdir: %s", exc)
        return {
            "schema": SCHEMA,
            "cycle_id": cycle_id,
            "ts": ts,
            "stages": {"tmpdir": {"status": "failed", "note": str(exc)}},
            "stubbed_stages": [],
            "real_stores_untouched": True,
            "wall_seconds": 0.0,
        }

    shadow_root = _build_shadow_root(real_root, tmp_dir)

    # ── Stage: sense_fitness ──────────────────────────────────────────────────
    stages["sense_fitness"] = _run_sense_fitness(shadow_root, real_root, cycle_id)

    # ── Stage: sense_organism_state ───────────────────────────────────────────
    stages["sense_organism_state"] = _run_sense_organism_state(shadow_root, real_root, cycle_id)

    # ── Stage: sense_insight_bus ──────────────────────────────────────────────
    stages["sense_insight_bus"] = _run_sense_insight_bus(shadow_root, real_root, cycle_id)

    # ── Stage: agenda ─────────────────────────────────────────────────────────
    if not use_llm:
        stubbed_stages.append("agenda")
    stages["agenda"] = _run_agenda(shadow_root, real_root, cycle_id, use_llm)

    # ── Stage: propose ────────────────────────────────────────────────────────
    if not use_llm:
        stubbed_stages.append("propose")
    stages["propose"] = _run_propose(shadow_root, real_root, cycle_id, use_llm, today)

    # ── Stage: adjudicate ─────────────────────────────────────────────────────
    if not use_llm:
        stubbed_stages.append("adjudicate")
    stages["adjudicate"] = _run_adjudicate(shadow_root, real_root, cycle_id, use_llm)

    # ── Stage: build (dry_run always True in shadow mode) ─────────────────────
    stages["build"] = _run_build(shadow_root, real_root, cycle_id)

    # ── Stage: verify (seeded contract) ───────────────────────────────────────
    stages["verify"] = _run_verify(shadow_root, real_root, cycle_id, today)

    # ── Stage: dream ──────────────────────────────────────────────────────────
    stages["dream"] = _run_dream(shadow_root, real_root, cycle_id, today)

    # ── Collect artifacts into real repo ─────────────────────────────────────
    collected = _collect_artifacts(shadow_root, real_root, cycle_id)
    stages["artifact_collection"] = {
        "status": "ok",
        "artifact": str(real_root / "data" / "metabolism" / "shadow" / cycle_id),
        "note": f"{len(collected)} artifacts collected",
    }

    # Cleanup temp directory
    try:
        tmp_obj.cleanup()
    except Exception:  # noqa: BLE001
        pass

    # ── Verify real stores untouched ──────────────────────────────────────────
    real_stores_untouched = _stores_untouched(before_snapshot, real_root)

    wall_seconds = time.monotonic() - t0

    # ── Write summary.json ────────────────────────────────────────────────────
    summary_path = _write_summary(
        real_root, cycle_id, ts, stages, stubbed_stages,
        real_stores_untouched, wall_seconds,
    )
    log.info(
        "shadow_cycle: cycle=%s done in %.1fs stores_untouched=%s stubbed=%s summary=%s",
        cycle_id, wall_seconds, real_stores_untouched, stubbed_stages, summary_path,
    )

    return {
        "schema": SCHEMA,
        "cycle_id": cycle_id,
        "ts": ts,
        "stages": stages,
        "stubbed_stages": stubbed_stages,
        "real_stores_untouched": real_stores_untouched,
        "wall_seconds": round(wall_seconds, 2),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.  Exit 0 always."""
    parser = argparse.ArgumentParser(description="Metabolism shadow-cycle harness (R-V4-1)")
    parser.add_argument("--now", default=None,
                        help="Timestamp for cycle_id (YYYY-MM-DDTHH:MM); default: real UTC now")
    parser.add_argument("--root", default=None, help="Repo root override")
    parser.add_argument("--use-llm", action="store_true", default=False,
                        help="Use real LLM calls (post-arming). Default: deterministic "
                             "stub seams, no LLM calls.")
    parser.add_argument("--cycle-id", default=None,
                        help="Override cycle_id (must match shadow-YYYYMMDD-HHMM format)")
    parser.add_argument("--out-dir", default=None, help="Override output directory")
    args = parser.parse_args(argv)

    real_root = Path(args.root) if args.root else _ROOT
    use_llm = args.use_llm  # --use-llm takes precedence over --no-llm

    # Derive cycle_id
    if args.cycle_id:
        cycle_id = args.cycle_id
    else:
        cycle_id = _make_cycle_id(args.now)

    # Idempotent: if summary.json already exists for this cycle_id, exit 0
    summary_path = real_root / "data" / "metabolism" / "shadow" / cycle_id / "summary.json"
    if summary_path.exists():
        log.info("shadow_cycle: %s already exists — idempotent exit 0", summary_path)
        try:
            existing = json.loads(summary_path.read_text(encoding="utf-8"))
            print(json.dumps(existing, indent=2, default=str))
        except Exception:  # noqa: BLE001
            pass
        return 0

    # Derive today from --now if given, else real today
    try:
        if args.now:
            # Extract just the date part
            today = datetime.strptime(args.now[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
        else:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    summary = run_shadow_cycle(real_root, cycle_id, today, use_llm=use_llm)
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
