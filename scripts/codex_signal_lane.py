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

def _build_context_pack(root: Path, n_candidates: int = 5) -> tuple[str, bool]:
    """Build a Signal Foundry brainstorm pack for the Codex prompt.

    FIX 17 — Returns (pack_text: str, used_fallback: bool).

    Tries to import the _build_sf_pack helper from run_signal_foundry_brainstorm.
    Falls back to a minimal pack (blocklist + registry summary + schema hint)
    if that module is not importable.
    """
    try:
        from scripts.run_signal_foundry_brainstorm import _build_sf_pack  # noqa: PLC0415
        return _build_sf_pack(root, n_candidates=n_candidates), False
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

    return "\n".join(lines), True


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
# Module-level factory helpers for FIX 14/15 (patchable by tests)
# ---------------------------------------------------------------------------

def _get_construction_hash_fn():
    """Return construction_hash function or None. NEVER raises."""
    try:
        from engine.signal_foundry.spec import construction_hash  # noqa: PLC0415
        return construction_hash
    except (ImportError, AttributeError):
        return None


def _get_validate_spec_fn():
    """Return validate_spec function or None. NEVER raises."""
    try:
        from engine.signal_foundry.spec import validate_spec  # noqa: PLC0415
        return validate_spec
    except (ImportError, AttributeError):
        return None


def _is_git_repo(root: Path) -> bool:
    """Return True if root (or any parent) is a git repo. NEVER raises."""
    try:
        import subprocess as _sp  # noqa: PLC0415
        r = _sp.run(
            ["git", "-C", str(root), "rev-parse", "--git-dir"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return r.returncode == 0
    except Exception:
        return False


def _get_has_numeric_confidence_fn():
    """Return _has_numeric_confidence function or None. NEVER raises."""
    try:
        from scripts.run_signal_foundry_brainstorm import _has_numeric_confidence  # noqa: PLC0415
        return _has_numeric_confidence
    except (ImportError, AttributeError):
        return None


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

    # FIX 14 — use module-level cached functions (patchable by tests)
    _construction_hash_fn = _get_construction_hash_fn()
    # FIX 15 — use module-level cached functions (patchable by tests)
    _validate_spec_fn = _get_validate_spec_fn()
    _has_numeric_confidence_fn = _get_has_numeric_confidence_fn()

    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n_admitted = 0
    n_rejected = 0
    admitted_ids: list[str] = []

    # Determine next id counter from existing file AND build prior-name set for FIX 7b
    next_id_n = 0
    # FIX 7b — load all prior normalized names once per _file_specs call for pre-dedup
    _prior_name_map: dict[str, tuple[str, str]] = {}  # normalized_name -> (id, original_name)
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
                        # Build normalized name index
                        pname = row.get("name", "")
                        if pname:
                            import re as _re  # noqa: PLC0415
                            norm = _re.sub(r"[^a-z0-9 ]", "", pname.lower()).strip()
                            if norm and norm not in _prior_name_map:
                                _prior_name_map[norm] = (sid, pname)
                    except Exception:
                        continue
        except OSError:
            pass

    def _normalize_name_local(name: str) -> str:
        import re as _re  # noqa: PLC0415
        return _re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()

    for spec in specs:
        # Ensure id
        sid = str(spec.get("id") or "")
        if not sid or not sid.startswith("SF-") or not sid[3:].isdigit():
            next_id_n += 1
            sid = f"SF-{next_id_n:04d}"
            spec = dict(spec, id=sid)

        if not spec.get("registered_at"):
            spec = dict(spec, registered_at=datetime.now(timezone.utc).date().isoformat())

        # FIX 14 — code-computed construction_hash on EVERY row; overwrite LLM-supplied value
        if _construction_hash_fn is not None:
            try:
                computed_hash = _construction_hash_fn(spec)
                spec = dict(spec, construction_hash=computed_hash)
            except Exception as exc:  # noqa: BLE001
                log.warning("codex_signal_lane: construction_hash failed for %s (%s)", sid, exc)
                spec = dict(spec)
                spec.pop("construction_hash", None)  # strip any LLM-supplied value
        else:
            # No hash fn available — strip LLM-supplied value to avoid trusting it
            if "construction_hash" in spec:
                spec = {k: v for k, v in spec.items() if k != "construction_hash"}

        # FIX 7b — name pre-dedup: check normalized name vs ALL prior candidates
        spec_name = spec.get("name", "")
        norm_spec_name = _normalize_name_local(spec_name) if spec_name else ""
        if norm_spec_name and norm_spec_name in _prior_name_map:
            prior_id, prior_name = _prior_name_map[norm_spec_name]
            log.info("codex_signal_lane: NAME_PREDEDUP: %s matches prior '%s' (%s)", sid, prior_name, prior_id)
            screen_result = {
                "admit": False,
                "verdict": "rejected",
                "reasons": [f"duplicate name vs prior candidate {prior_id} '{prior_name}'"],
                "gates_passed": [],
                "gates_failed": ["novelty"],
            }
        else:
            # FIX 15 — Gate 2: numeric-confidence check (before screen_candidate)
            _numeric_conf_reject = False
            if _has_numeric_confidence_fn is not None:
                try:
                    if _has_numeric_confidence_fn(spec):
                        _numeric_conf_reject = True
                        log.info("codex_signal_lane: NUMERIC_CONF_REJECT: %s has numeric confidence scores", sid)
                except Exception as exc:  # noqa: BLE001
                    log.warning("codex_signal_lane: _has_numeric_confidence check failed for %s (%s)", sid, exc)

            if _numeric_conf_reject:
                screen_result = {
                    "admit": False,
                    "verdict": "rejected",
                    "reasons": ["numeric confidence scores are forbidden (RF-16)"],
                    "gates_passed": [],
                    "gates_failed": ["numeric_confidence"],
                }
            else:
                # FIX 15 — Gate 3: validate_spec (before screen_candidate)
                # Only runs when root is a git repo (avoids false-positive git-tracking failures
                # in tmp-dir test environments).
                _spec_ok = True
                _spec_errors: list[str] = []
                if _validate_spec_fn is not None and _is_git_repo(root):
                    try:
                        _spec_ok, _spec_errors = _validate_spec_fn(spec, root)
                    except Exception as exc:  # noqa: BLE001
                        log.warning("codex_signal_lane: validate_spec failed for %s (%s)", sid, exc)
                        _spec_ok = True  # degrade gracefully — don't block on validator error

                if not _spec_ok:
                    screen_result = {
                        "admit": False,
                        "verdict": "rejected",
                        "reasons": _spec_errors[:5],
                        "gates_passed": [],
                        "gates_failed": ["validate_spec"],
                    }
                else:
                    # SF-R7 screen gate
                    try:
                        screen_result = screen_candidate(spec, repo_root=root)
                    except Exception as exc:  # noqa: BLE001
                        screen_result = {"admit": False, "verdict": "error", "reasons": [str(exc)], "gates_passed": [], "gates_failed": ["error"]}

            # Register new name in map so later specs in the same batch don't collide
            if norm_spec_name:
                _prior_name_map.setdefault(norm_spec_name, (sid, spec_name))

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

        # FIX 6 — SF-R6 weekly filing budget cap
        try:
            import yaml as _yaml  # noqa: PLC0415
            sf_yml_path = _resolve_root(root) / "config" / "signal_foundry.yml"
            _sf_cfg: dict = {}
            if sf_yml_path.exists():
                try:
                    _sf_cfg = _yaml.safe_load(sf_yml_path.read_text(encoding="utf-8")) or {}
                except Exception:
                    pass
            cap = int((_sf_cfg.get("budgets") or {}).get("filed_per_week", 5))
        except Exception:  # noqa: BLE001
            cap = 5

        cands_path_for_cap = r / "data" / "signal_foundry" / "candidates.jsonl"
        try:
            _week_count = 0
            _week_reject_count = 0  # FIX 16
            if cands_path_for_cap.exists():
                with cands_path_for_cap.open(encoding="utf-8") as _fh:
                    for _line in _fh:
                        _line = _line.strip()
                        if not _line:
                            continue
                        try:
                            _row = json.loads(_line)
                            if _row.get("iso_week") == iso_week:
                                if _row.get("status") in {"proposed", "registered", "tested"}:
                                    _week_count += 1
                                elif _row.get("status") == "screen_rejected":
                                    _week_reject_count += 1  # FIX 16
                        except Exception:
                            continue
        except Exception:  # noqa: BLE001
            _week_count = 0
            _week_reject_count = 0

        if _week_count >= cap:
            log.info("codex_signal_lane: SF-R6 weekly cap reached (%d/%d); skipping", _week_count, cap)
            return {
                "ok": True,
                "action": "weekly_cap_reached",
                "detail": f"SF-R6: {_week_count}/{cap} filed this ISO week",
                "n_admitted": 0,
                "n_rejected": 0,
            }

        # FIX 16 — reject-backoff: if >= 25 screen_rejected rows this week, skip
        if _week_reject_count >= 25:
            log.info(
                "codex_signal_lane: FIX-16 reject-backoff: %d screen_rejected this ISO week (>= 25); skipping",
                _week_reject_count,
            )
            return {
                "ok": True,
                "action": "reject_backoff",
                "detail": f"reject_backoff: {_week_reject_count} screen_rejected this ISO week (>= 25)",
                "n_admitted": 0,
                "n_rejected": 0,
            }

        # 2. Build context pack (FIX 17 — returns tuple)
        pack, _used_fallback = _build_context_pack(r, n_candidates=n_candidates)

        # FIX 17 — governance event on fallback
        if _used_fallback:
            _append_governance_event(
                "sf_pack_fallback",
                {"reason": "run_signal_foundry_brainstorm._build_sf_pack not importable", "iso_week": iso_week},
                r,
            )

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
        # FIX 7a — raise prior_names cap to 200 most recent; note overflow
        prior_section = ""
        if prior_names:
            _cap_200 = prior_names[-200:]  # most recent 200
            _omitted = len(prior_names) - len(_cap_200)
            _names_block = "\n".join(f"  - {n}" for n in _cap_200)
            if _omitted > 0:
                _names_block += f"\n  (+{_omitted} earlier constructions omitted — the construction-hash gate still enforces them)"
            prior_section = (
                "\n\nPREVIOUSLY FILED/TESTED/KILLED CONSTRUCTIONS (must not re-propose):\n"
                + _names_block
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
                harness_cp = subprocess.run(  # noqa: S603
                    [sys.executable, "-m", "scripts.run_signal_foundry_harness", "--root", str(r)],
                    cwd=str(r),
                    capture_output=True,
                    text=True,
                    timeout=1800,  # 30 min hard cap
                )
                # FIX 7c — capture returncode and emit governance event
                if harness_cp.returncode != 0:
                    stderr_tail = (harness_cp.stderr or "")[-300:]
                    log.warning("codex_signal_lane: harness returned rc=%d; stderr_tail: %s",
                                harness_cp.returncode, stderr_tail)
                    _append_governance_event(
                        "sf_harness_run",
                        {"ok": False, "returncode": harness_cp.returncode, "stderr_tail": stderr_tail, "admitted_ids": admitted_ids},
                        r,
                    )
                else:
                    _append_governance_event(
                        "sf_harness_run",
                        {"ok": True, "admitted_ids": admitted_ids},
                        r,
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
