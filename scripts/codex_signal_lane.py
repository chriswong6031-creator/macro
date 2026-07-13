"""scripts/codex_signal_lane.py — Signal Foundry brainstorm lane via Codex (CRX-R1/R2/R3).

Public API:
    run_once(root=None, dry_run=False) -> dict

Honors SIGNAL_FOUNDRY_PAUSED exactly like run_signal_foundry_brainstorm.py
(SF-R5: only runs when the env var is the exact string 'false').

SF write fence (SF-R10): writes ONLY to:
  - data/signal_foundry/candidates.jsonl
  - data/signal_foundry/governance.jsonl
  - data/codex_lane/ (loop journal, usage state)

Exit 0 always (never-raise public interface).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------

def _resolve_root(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# SF-R5: SIGNAL_FOUNDRY_PAUSED gate (fail-closed — mirrors run_signal_foundry_brainstorm.py)
# ---------------------------------------------------------------------------

def _is_sf_paused() -> bool:
    """Return True if the Signal Foundry is paused.

    Runs ONLY when SIGNAL_FOUNDRY_PAUSED is exactly 'false'.
    Any other value (including unset) -> paused.
    """
    val = os.environ.get("SIGNAL_FOUNDRY_PAUSED", "")
    return val.strip().lower() != "false"


# ---------------------------------------------------------------------------
# Config helper (guarded import)
# ---------------------------------------------------------------------------

def _load_cfg(root: Path) -> dict:
    try:
        from engine.codex_lane.budget import load_cfg  # noqa: PLC0415
        return load_cfg(root)
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_signal_lane: could not load cfg (%s); using defaults", exc)
        return {
            "budget_pct": 85,
            "max_sessions_per_window": 10,
            "session_timeout_min": 25,
            "signals_per_run": 5,
            "codex_model": "",
            "sandbox": "workspace-write",
            "network": True,
        }


# ---------------------------------------------------------------------------
# note_result (guarded)
# ---------------------------------------------------------------------------

def _note_result(run: dict, root: Path) -> None:
    try:
        from engine.codex_lane.budget import note_result  # noqa: PLC0415
        note_result({**run, "lane": "signals"}, root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_signal_lane: note_result failed (%s)", exc)


# ---------------------------------------------------------------------------
# Build SF context pack (reuse helpers from run_signal_foundry_brainstorm if importable)
# ---------------------------------------------------------------------------

def _build_context_pack(root: Path, n_candidates: int = 5) -> str:
    """Build a Signal Foundry brainstorm pack for the Codex prompt.

    Tries to import the _build_sf_pack helper from run_signal_foundry_brainstorm.
    Falls back to a minimal pack (blocklist + registry summary + schema hint)
    if that module is not importable.
    """
    try:
        from scripts.run_signal_foundry_brainstorm import _build_sf_pack  # noqa: PLC0415
        return _build_sf_pack(root, n_candidates=n_candidates)
    except Exception as exc:  # noqa: BLE001
        log.info("codex_signal_lane: _build_sf_pack not importable (%s); building minimal pack", exc)

    # Minimal fallback pack
    lines: list[str] = [
        "=== SIGNAL FOUNDRY BRAINSTORM PACK (minimal fallback) ===",
        f"ISO Date: {datetime.now(timezone.utc).date().isoformat()}",
        "",
        f"MISSION: Propose {n_candidates} novel Signal Foundry candidate specs.",
    ]

    # Blocklist themes
    bl_path = root / "config" / "signal_foundry_blocklist.yml"
    if bl_path.exists():
        try:
            import yaml  # noqa: PLC0415
            bl = yaml.safe_load(bl_path.read_text(encoding="utf-8")) or {}
            lines.append("\nBLOCKLIST THEMES (never propose these):")
            for entry in bl.get("entries", []):
                reason = entry.get("reason", "")
                patterns = entry.get("match", {}).get("any_of", [])[:3]
                lines.append(f"  - {reason} (patterns: {patterns})")
        except Exception:
            lines.append("  (blocklist not loadable)")

    # Existing candidate ids/names (dedup memory — CRX-R3)
    cands_path = root / "data" / "signal_foundry" / "candidates.jsonl"
    if cands_path.exists():
        lines.append("\nEXISTING SF CANDIDATES (do not duplicate):")
        try:
            with cands_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        sid = row.get("id") or row.get("spec_id") or ""
                        name = row.get("name", "")
                        chash = row.get("construction_hash", "")
                        if sid or name:
                            lines.append(f"  SF: {sid} {name} (hash={chash[:8] if chash else 'N/A'})")
                    except Exception:
                        continue
        except OSError:
            lines.append("  (candidates.jsonl not readable)")

    # Spec schema hint
    lines.append("""
SPEC JSON SCHEMA (emit exactly this structure):
{
  "id": "SF-NNNN",
  "name": "short english name",
  "name_zh": "chinese name",
  "market": "US macro",
  "thesis": "one sentence causal thesis",
  "mechanism": "mechanism description",
  "seed_provenance": {"source": "<source>", "ref": "<ref>"},
  "data": [{"path": "data/<store>/<file>.parquet", "column": "<col>", "pit": "proxy|lagged|release_lag|clean"}],
  "feature": {"pipeline": [["<transform>", {"<param>": <value>}]]},
  "target": {"path": "data/yahoo/SPY.parquet", "kind": "excess_return", "horizon_d": 21},
  "universe": "single_series",
  "baseline": "buy_and_hold",
  "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
  "horizon_role": "swing",
  "orthogonality_note": "what makes this distinct",
  "evidence_note": "basis"
}

FORBIDDEN: numeric confidence scores (RF-16), 'validated' claims, paths to untracked stores.
WHITELISTED transforms: zscore, pctile_rank, diff, pct_change, sma, ema, ratio, spread, lag, sign, clip, rolling_corr, rolling_vol, drawdown
""")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON array parser (mirrors run_signal_foundry_brainstorm._parse_json_array)
# ---------------------------------------------------------------------------

def _parse_json_array(text: str) -> list[dict]:
    """Defensively parse a JSON array from Codex output."""
    text = text.strip()

    # Direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return [c for c in obj if isinstance(c, dict)]
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    for fence in ("```json", "```"):
        if fence in text:
            start = text.find(fence) + len(fence)
            end = text.rfind("```")
            if end > start:
                inner = text[start:end].strip()
                try:
                    obj = json.loads(inner)
                    if isinstance(obj, list):
                        return [c for c in obj if isinstance(c, dict)]
                except json.JSONDecodeError:
                    pass

    # Find first [ ... ]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            if isinstance(obj, list):
                return [c for c in obj if isinstance(c, dict)]
        except json.JSONDecodeError:
            pass

    return []


# ---------------------------------------------------------------------------
# Next SF-NNNN id helper (mirrors run_signal_foundry_brainstorm._next_sf_id)
# ---------------------------------------------------------------------------

def _next_sf_id(candidates_path: Path) -> str:
    max_n = 0
    if candidates_path.exists():
        try:
            with candidates_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        sid = str(row.get("id") or row.get("spec_id") or "")
                        if sid.startswith("SF-") and sid[3:].isdigit():
                            n = int(sid[3:])
                            if n > max_n:
                                max_n = n
                    except Exception:
                        continue
        except OSError:
            pass
    return f"SF-{max_n + 1:04d}"


# ---------------------------------------------------------------------------
# Screen + file specs (reuse _file_specs if available, else inline)
# ---------------------------------------------------------------------------

def _file_specs(
    specs: list[dict],
    candidates_path: Path,
    root: Path,
    iso_week: str,
    dry_run: bool,
) -> tuple[int, int, list[str]]:
    """Apply screen gate (SF-R7) and file admitted specs.

    Returns (n_admitted, n_rejected, admitted_ids).

    Always uses the inline writer so that provenance: {"generator": "codex_chatgpt"}
    is stamped on EVERY row (admitted and rejected) regardless of whether
    run_signal_foundry_brainstorm is importable.

    The brainstorm module is reused ONLY for context-pack building and the spec schema
    (via _build_sf_pack / stamp_gates_hash); screen_candidate is the sole admission gate.

    The admitted row shape mirrors run_signal_foundry_brainstorm._file_specs exactly:
        {**spec_stamped, status, proposed_at, iso_week, screen_result}
    plus provenance: {"generator": "codex_chatgpt"}.

    admitted_ids contains only the ids appended by THIS call (not pre-existing same-week rows).
    """
    try:
        from engine.signal_foundry.screen import screen_candidate  # noqa: PLC0415
    except ImportError:
        log.warning("codex_signal_lane: screen_candidate not importable; filing all as screen_rejected")
        return 0, len(specs), []

    try:
        from engine.signal_foundry.spec import stamp_gates_hash  # noqa: PLC0415
    except ImportError:
        stamp_gates_hash = None  # type: ignore[assignment]

    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n_admitted = 0
    n_rejected = 0
    admitted_ids: list[str] = []

    # Determine next id counter from existing file
    next_id_n = 0
    if candidates_path.exists():
        try:
            with candidates_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        sid = str(row.get("id") or row.get("spec_id") or "")
                        if sid.startswith("SF-") and sid[3:].isdigit():
                            n = int(sid[3:])
                            if n > next_id_n:
                                next_id_n = n
                    except Exception:
                        continue
        except OSError:
            pass

    for spec in specs:
        # Ensure id
        sid = str(spec.get("id") or "")
        if not sid or not sid.startswith("SF-") or not sid[3:].isdigit():
            next_id_n += 1
            sid = f"SF-{next_id_n:04d}"
            spec = dict(spec, id=sid)

        if not spec.get("registered_at"):
            spec = dict(spec, registered_at=datetime.now(timezone.utc).date().isoformat())

        # SF-R7 screen gate
        try:
            screen_result = screen_candidate(spec, repo_root=root)
        except Exception as exc:  # noqa: BLE001
            screen_result = {"admit": False, "verdict": "error", "reasons": [str(exc)], "gates_passed": [], "gates_failed": ["error"]}

        if screen_result.get("admit"):
            spec_stamped = dict(spec)
            if stamp_gates_hash is not None:
                try:
                    spec_stamped = stamp_gates_hash(spec)
                except Exception:
                    pass
            row: dict = {
                **spec_stamped,
                "status": "proposed",
                "proposed_at": ts,
                "iso_week": iso_week,
                "provenance": {"generator": "codex_chatgpt"},
                "screen_result": {
                    "verdict": screen_result.get("verdict"),
                    "gates_passed": screen_result.get("gates_passed", []),
                    "gates_failed": screen_result.get("gates_failed", []),
                },
            }
            log.info("codex_signal_lane: ADMITTED: %s '%s'", sid, spec.get("name", ""))
            if not dry_run:
                with candidates_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
            admitted_ids.append(sid)
            n_admitted += 1
        else:
            row = {
                "id": sid,
                "name": spec.get("name", ""),
                "status": "screen_rejected",
                "proposed_at": ts,
                "iso_week": iso_week,
                "provenance": {"generator": "codex_chatgpt"},
                "screen_result": {
                    "verdict": screen_result.get("verdict"),
                    "reasons": screen_result.get("reasons", []),
                    "gates_passed": screen_result.get("gates_passed", []),
                    "gates_failed": screen_result.get("gates_failed", []),
                },
            }
            log.info("codex_signal_lane: SCREEN_REJECTED: %s", sid)
            if not dry_run:
                with candidates_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
            n_rejected += 1

    return n_admitted, n_rejected, admitted_ids


# ---------------------------------------------------------------------------
# Governance event writer (SF-R10)
# ---------------------------------------------------------------------------

def _append_governance_event(
    event_type: str,
    evidence: dict,
    root: Path,
) -> None:
    """Append a governance event to data/signal_foundry/governance.jsonl (SF-R10)."""
    # Try to reuse helper from brainstorm
    try:
        from scripts.run_signal_foundry_brainstorm import _append_governance_event as _sf_gov  # noqa: PLC0415
        _sf_gov(event_type, evidence, root)
        return
    except ImportError:
        pass

    gov_path = root / "data" / "signal_foundry" / "governance.jsonl"
    try:
        gov_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event_type,
            "authored_by": "codex_signal_lane",
            "evidence": evidence,
        }
        with gov_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("codex_signal_lane: governance event write failed (%s)", exc)


# ---------------------------------------------------------------------------
# ISO week helper
# ---------------------------------------------------------------------------

def _current_iso_week() -> str:
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


# ---------------------------------------------------------------------------
# Main run_once
# ---------------------------------------------------------------------------

def run_once(root: Path | str | None = None, dry_run: bool = False) -> dict:
    """Run one iteration of the signal brainstorm lane.

    Returns dict: {ok, action, detail, n_admitted, n_rejected}.
    NEVER raises.
    """
    try:
        r = _resolve_root(root)
        cfg = _load_cfg(r)

        # SF-R5: honor SIGNAL_FOUNDRY_PAUSED (fail-closed)
        if _is_sf_paused():
            log.info("codex_signal_lane: SIGNAL_FOUNDRY_PAUSED not 'false'; skipping")
            return {
                "ok": True,
                "action": "skip",
                "detail": "SIGNAL_FOUNDRY_PAUSED is not 'false' (SF-R5)",
                "n_admitted": 0,
                "n_rejected": 0,
            }

        n_candidates = int(cfg.get("signals_per_run", 5))
        iso_week = _current_iso_week()

        # 2. Build context pack
        pack = _build_context_pack(r, n_candidates=n_candidates)

        # Get list of previously filed/tested/killed constructions for dedup prompt
        cands_path = r / "data" / "signal_foundry" / "candidates.jsonl"
        prior_names: list[str] = []
        prior_hashes: list[str] = []
        if cands_path.exists():
            try:
                with cands_path.open(encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                            name = row.get("name", "")
                            chash = row.get("construction_hash", "")
                            if name:
                                prior_names.append(name)
                            if chash:
                                prior_hashes.append(chash)
                        except Exception:
                            continue
            except OSError:
                pass

        # 3. Generator prompt
        prior_section = ""
        if prior_names:
            prior_section = (
                "\n\nPREVIOUSLY FILED/TESTED/KILLED CONSTRUCTIONS (must not re-propose):\n"
                + "\n".join(f"  - {n}" for n in prior_names[:50])
            )

        generator_prompt = (
            f"{pack}"
            f"{prior_section}"
            f"\n\nOUTPUT STRICT JSON array of up to {n_candidates} spec objects. "
            f"Do not include any text outside the JSON array. "
            f"Every spec must be novel — not re-proposing any previously filed/tested/killed construction listed above."
        )

        # 4. Run Codex
        if dry_run:
            log.info("codex_signal_lane: dry_run=True; skipping Codex call")
            return {
                "ok": True,
                "action": "dry_run",
                "detail": "dry_run: no Codex call",
                "n_admitted": 0,
                "n_rejected": 0,
            }

        try:
            from engine.codex_lane.runner import run_codex  # noqa: PLC0415
        except ImportError:
            return {
                "ok": False,
                "action": "error",
                "detail": "runner not importable",
                "n_admitted": 0,
                "n_rejected": 0,
            }

        timeout_s = int(cfg.get("session_timeout_min", 25)) * 60
        model = cfg.get("codex_model", "") or ""
        sandbox = cfg.get("sandbox", "workspace-write")
        network = bool(cfg.get("network", True))

        gen_run = run_codex(
            generator_prompt,
            cwd=str(r),
            timeout_s=timeout_s,
            model=model,
            sandbox=sandbox,
            network=network,
        )
        _note_result(gen_run, r)

        if not gen_run.get("ok"):
            err = gen_run.get("error_kind", "error")
            _append_governance_event(
                "sf_brainstorm_run",
                {"generator": "codex", "ok": False, "error_kind": err, "iso_week": iso_week},
                r,
            )
            return {
                "ok": False,
                "action": "error",
                "detail": f"Codex run failed: {err}",
                "n_admitted": 0,
                "n_rejected": 0,
            }

        # 5. Parse JSON array defensively
        final_msg = gen_run.get("final_message", "")
        specs = _parse_json_array(final_msg)
        if not specs:
            log.warning("codex_signal_lane: could not parse any specs from Codex output")
            _append_governance_event(
                "sf_brainstorm_run",
                {"generator": "codex", "ok": True, "specs_parsed": 0, "iso_week": iso_week},
                r,
            )
            return {
                "ok": True,
                "action": "no_specs",
                "detail": "Codex ran OK but no parseable spec array found",
                "n_admitted": 0,
                "n_rejected": 0,
            }

        # 6. Screen each spec and file
        n_admitted, n_rejected, admitted_ids = _file_specs(
            specs, cands_path, r, iso_week, dry_run
        )

        # 7. Governance event (SF-R10)
        _append_governance_event(
            "sf_brainstorm_run",
            {
                "generator": "codex",
                "ok": True,
                "specs_parsed": len(specs),
                "n_admitted": n_admitted,
                "n_rejected": n_rejected,
                "iso_week": iso_week,
                "admitted_ids": admitted_ids,
            },
            r,
        )

        # 8. Run harness for admitted ids (error-tolerated, skipped in dry_run)
        if admitted_ids and not dry_run:
            try:
                subprocess.run(  # noqa: S603
                    [sys.executable, "-m", "scripts.run_signal_foundry_harness", "--root", str(r)],
                    cwd=str(r),
                    capture_output=True,
                    text=True,
                    timeout=1800,  # 30 min hard cap
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("codex_signal_lane: harness run failed (%s); non-fatal", exc)

        return {
            "ok": True,
            "action": "brainstorm_done",
            "detail": f"specs={len(specs)} admitted={n_admitted} rejected={n_rejected}",
            "n_admitted": n_admitted,
            "n_rejected": n_rejected,
        }

    except Exception as exc:  # noqa: BLE001
        log.exception("codex_signal_lane: unexpected error in run_once: %s", exc)
        return {"ok": False, "action": "error", "detail": str(exc), "n_admitted": 0, "n_rejected": 0}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=None, help="Repo root")
    ap.add_argument("--dry-run", action="store_true", default=False)
    args = ap.parse_args(argv)

    result = run_once(root=args.root, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
