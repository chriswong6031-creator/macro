"""engine.metabolism.orchestrator_brain — System-prompt builder (V2-D, extends V2-A stub).

_build_orchestrator_system(model, role, lobe) is the ONE versioned helper
imported by every orchestrator-tier reasoner (organism_state pass, agenda, dream)
so the persona is consistent across all LLM calls.

Full prompt engine (V2-D §3):
  1. ROLE + DOCTRINE: role line from config/metabolism_roles.yml.
     If model is Opus-class (startswith 'claude-opus') → PREPEND config/fable_mode_core.md.
     If Fable-class → OMIT. Default-inject whenever NOT-provably-Fable.
  2. STANDING LAWS: load-bearing rulings BY ID from config/ruling_graph.yml
     (NW-ART1 signal ban, HOUSE-U4 gauntlet-is-promotion-gate,
      RUL-U10 UI-restraint/language-law, NW-U11 stateless-cattle/retire-one).
     Quote-verified from the graph — one source of truth, not paraphrased.
  3. ORGANISM-STATE SLICE: organism_state.json rollup + lobe raw deltas,
     byte-capped [:6000].
  4. CASE-LAW SLICE: ruling rows whose target/tags match the lobe + whole
     DO_NOT_REBUILD.md.
  5. LOBE CHARTER (config/lobe_charters.yml, tolerant if absent) +
     RECENT LESSONS (lessons.jsonl tail) + fitness-contract requirement.

Byte-capped throughout. Template code is FIXED; every injected part is an
artifact the loop edits.

NEVER reads ~/.  All paths relative to repo root.
NEVER-RAISE: returns a minimal safe prompt on any failure.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Byte caps
_ORGANISM_STATE_BYTE_CAP = 6000
_RULING_SLICE_BYTE_CAP = 3000
_ABM_BYTE_CAP = 1500
_DO_NOT_REBUILD_BYTE_CAP = 2000
_LESSONS_BYTE_CAP = 2000
_CHARTER_BYTE_CAP = 1000

# Ruling IDs for the 5 standing laws (quote-verified from ruling_graph.yml)
_STANDING_LAW_IDS = [
    "NW-ART1",    # R-AUT-1 equivalent: signal/origination ban
    "HOUSE-U4",   # gauntlet-is-promotion-gate (display-only until gauntleted)
    "RUL-U10",    # UI-restraint / language law (plain language; banned words include the v-word)
    "NW-U11",     # stateless-cattle / retire-one-to-file-one (cortex machine-trial law)
    "CONST-ART1", # Origination Ban — A7 permanently refused (constitutional)
]

# Opus-class model name substrings (not Fable)
_OPUS_SUBSTRINGS = ("opus", "claude-3-opus", "claude-opus")


def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _is_opus_class(model: str | None) -> bool:
    """Return True if the model is Opus-class (not provably Fable).

    Fable-class model ids contain 'fable'.  Everything else that contains
    'opus' is Opus-class.  Unknown / None → treat as Opus-class (default inject).
    """
    if not model:
        return True  # default inject when unknown
    model_lower = model.lower()
    if "fable" in model_lower:
        return False
    if any(s in model_lower for s in _OPUS_SUBSTRINGS):
        return True
    # Unknown model → inject to be safe (default inject whenever NOT-provably-Fable)
    return True


def _read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None


def _byte_cap(text: str, cap: int) -> str:
    encoded = text.encode()
    if len(encoded) <= cap:
        return text
    return encoded[:cap].decode(errors="replace") + "\n… (truncated)"


# ── Part 1: Role + Doctrine ────────────────────────────────────────────────────

def _load_role(root: Path, role: str | None) -> str:
    """Load the role line from config/metabolism_roles.yml."""
    roles_path = root / "config" / "metabolism_roles.yml"
    default_role = (
        "You are the Metabolism Orchestrator — a stateless reasoning agent "
        "that reads the whole-organism state, inspects the insight bus, and "
        "emits a ranked agenda of proposed work items.  You write artifacts only; "
        "you dispatch nothing, grant nothing, open no PR, touch no lobe roster."
    )
    if not roles_path.exists():
        return default_role
    try:
        import yaml  # noqa: PLC0415
        raw = yaml.safe_load(roles_path.read_text(encoding="utf-8")) or {}
        roles = raw.get("roles") or {}
        role_key = role or "orchestrator"
        role_text = roles.get(role_key) or roles.get("orchestrator") or default_role
        return str(role_text)
    except Exception as exc:  # noqa: BLE001
        log.warning("orchestrator_brain: cannot load roles — %s", exc)
        return default_role


def _load_fable_mode_core(root: Path) -> str:
    """Load the vendored fable-mode doctrine (config/fable_mode_core.md)."""
    p = root / "config" / "fable_mode_core.md"
    if not p.exists():
        log.warning("orchestrator_brain: fable_mode_core.md not found at %s", p)
        return "# Fable Mode Core\n(file not found — check config/fable_mode_core.md)\n"
    return _read_text(p) or ""


# ── Part 2: Standing Laws (quote-verified from ruling_graph.yml) ───────────────

def _load_standing_laws(root: Path) -> str:
    """Pull the 5 load-bearing standing laws BY ID from ruling_graph.yml.

    Quote-verified — the ruling text is taken verbatim from the graph,
    never paraphrased.  Returns a formatted block even on partial failure.
    """
    p = root / "config" / "ruling_graph.yml"
    if not p.exists():
        return _fallback_standing_laws()
    try:
        import yaml  # noqa: PLC0415
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        rulings = raw.get("rulings") or []
        if isinstance(rulings, dict):
            rulings = list(rulings.values())

        # Index by ruling_id for O(n) single pass
        by_id: dict[str, dict[str, Any]] = {}
        for r in rulings:
            if isinstance(r, dict) and r.get("ruling_id"):
                by_id[r["ruling_id"]] = r

        lines: list[str] = []
        for rid in _STANDING_LAW_IDS:
            r = by_id.get(rid)
            if not r:
                lines.append(f"[{rid}] (not found in ruling_graph)")
                continue
            short = r.get("short_name") or rid
            title = r.get("title") or ""
            ruling_text = str(r.get("ruling") or "").strip()
            snippet = f"[{rid} | {short}]\nTitle: {title}\nRuling: {ruling_text}"
            lines.append(snippet[:500])

        result = "\n\n".join(lines)
        return _byte_cap(result, _RULING_SLICE_BYTE_CAP)

    except Exception as exc:  # noqa: BLE001
        log.warning("orchestrator_brain: cannot load standing laws — %s", exc)
        return _fallback_standing_laws()


def _fallback_standing_laws() -> str:
    """Hard-coded fallback for the 5 standing laws when ruling_graph is unavailable."""
    return (
        "[NW-ART1] No LLM origination: No LLM may invent a signal, trade, or escalation. "
        "This prohibition is permanent across all authority rungs. Classified A7 ORIGINATE — banned.\n\n"
        "[HOUSE-U4] Gauntlet-is-promotion-gate: All signals are display-only until gauntleted. "
        "Pre-registered gates required. Nulls printed, not hidden. LLMs may only de-escalate "
        "calibrated keys — never originate signals, scores, or escalations.\n\n"
        "[RUL-U10] Language law: The word 'v*lidated' (check_validated_claims) must appear "
        "nowhere in any artifact. Plain-language box mandatory in every report.\n\n"
        "[NW-U11] Retire-one-to-file-one: Machine trials graded ONLY on post-registration data. "
        "Hard proposal budget per cycle; retire-one-to-file-one beyond budget.\n\n"
        "[CONST-ART1] Origination ban (constitutional): A7/ORIGINATE permanently refused. "
        "No amount of evidence can override this refusal."
    )


# ── Part 3: Organism-state slice ───────────────────────────────────────────────

def _build_state_slice(
    root: Path,
    lobe: str | None,
    organism_state: dict | None,
) -> str:
    """Build the organism-state + lobe-deltas slice, byte-capped."""
    parts: list[str] = []

    # Whole-organism rollup (caller may pass it; else load from disk)
    state = organism_state
    if state is None:
        state_path = root / "data" / "metabolism" / "organism_state.json"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                log.warning("orchestrator_brain: organism_state load failed — %s", exc)

    if state:
        try:
            os_text = json.dumps(state, indent=2, ensure_ascii=False)
            os_text = _byte_cap(os_text, _ORGANISM_STATE_BYTE_CAP)
            parts.append(f"### Organism state (rollup)\n\n```json\n{os_text}\n```")
        except Exception as exc:  # noqa: BLE001
            log.warning("orchestrator_brain: organism_state serialization failed — %s", exc)

    # Lobe-specific raw deltas (the fitness card for this lobe)
    if lobe:
        fitness_path = root / "data" / "metabolism" / "fitness" / f"{lobe}.json"
        if fitness_path.exists():
            try:
                lobe_text = fitness_path.read_text(encoding="utf-8")
                lobe_text = _byte_cap(lobe_text, 2000)
                parts.append(f"### Lobe fitness card: {lobe}\n\n```json\n{lobe_text}\n```")
            except Exception as exc:  # noqa: BLE001
                log.warning("orchestrator_brain: lobe card load failed — %s", exc)

    if not parts:
        return "(organism state unavailable — accruing)"
    return "\n\n".join(parts)


# ── Part 4: Case-law slice ─────────────────────────────────────────────────────

def _load_case_law_slice(root: Path, lobe: str | None) -> str:
    """Load ruling rows matching the lobe + DO_NOT_REBUILD.md.

    The deterministic screen in adjudicate.py is the HARD floor;
    this slice only informs the LLM.
    """
    parts: list[str] = []

    # DO_NOT_REBUILD.md (always included, byte-capped)
    dnr_path = root / "research" / "DO_NOT_REBUILD.md"
    if dnr_path.exists():
        try:
            dnr_text = dnr_path.read_text(encoding="utf-8")
            dnr_text = _byte_cap(dnr_text, _DO_NOT_REBUILD_BYTE_CAP)
            parts.append(f"### DO_NOT_REBUILD kills\n\n{dnr_text}")
        except Exception as exc:  # noqa: BLE001
            log.warning("orchestrator_brain: DO_NOT_REBUILD load failed — %s", exc)

    # Ruling rows matching the lobe (by match_terms / owner_program)
    if lobe:
        graph_path = root / "config" / "ruling_graph.yml"
        if graph_path.exists():
            try:
                import yaml  # noqa: PLC0415
                raw = yaml.safe_load(graph_path.read_text(encoding="utf-8")) or {}
                rulings = raw.get("rulings") or []
                if isinstance(rulings, dict):
                    rulings = list(rulings.values())

                lobe_lower = lobe.lower()
                selected: list[str] = []
                for r in rulings:
                    if not isinstance(r, dict):
                        continue
                    haystack = " ".join([
                        str(r.get("match_terms") or ""),
                        str(r.get("owner_program") or ""),
                        str(r.get("title") or ""),
                    ]).lower()
                    if lobe_lower in haystack:
                        rid = r.get("ruling_id", "")
                        ruling_text = str(r.get("ruling") or "").strip()
                        selected.append(f"[{rid}] {ruling_text}"[:300])
                    if len("\n".join(selected).encode()) >= 2000:
                        break

                if selected:
                    lobe_laws = _byte_cap("\n".join(selected), 2000)
                    parts.append(f"### Rulings relevant to lobe: {lobe}\n\n{lobe_laws}")
            except Exception as exc:  # noqa: BLE001
                log.warning("orchestrator_brain: lobe ruling slice failed — %s", exc)

    return "\n\n".join(parts) if parts else "(case-law slice unavailable)"


# ── Part 5: Lobe charter + lessons + contract requirement ─────────────────────

def _load_lobe_charter(root: Path, lobe: str | None) -> str:
    """Load lobe charter from config/lobe_charters.yml (tolerant if absent)."""
    if not lobe:
        return "(no lobe specified)"
    charter_path = root / "config" / "lobe_charters.yml"
    if not charter_path.exists():
        return "(config/lobe_charters.yml not yet present — V2-C artifact)"
    try:
        import yaml  # noqa: PLC0415
        raw = yaml.safe_load(charter_path.read_text(encoding="utf-8")) or {}
        charters = raw.get("charters") or raw.get("lobes") or {}
        entry = charters.get(lobe)
        if entry is None:
            return f"(no charter registered for lobe: {lobe})"
        charter_text = json.dumps(entry, indent=2, ensure_ascii=False)
        return _byte_cap(charter_text, _CHARTER_BYTE_CAP)
    except Exception as exc:  # noqa: BLE001
        log.warning("orchestrator_brain: lobe charter load failed — %s", exc)
        return "(lobe charter unavailable)"


def _load_recent_lessons(root: Path) -> str:
    """Load the tail of lessons.jsonl (VERIFY appends), byte-capped."""
    lessons_path = root / "data" / "metabolism" / "lessons.jsonl"
    if not lessons_path.exists():
        return "(lessons.jsonl not yet present — accruing as VERIFY runs)"
    try:
        text = lessons_path.read_text(encoding="utf-8")
        # Take the tail: last _LESSONS_BYTE_CAP bytes
        encoded = text.encode()
        if len(encoded) > _LESSONS_BYTE_CAP:
            tail = encoded[-_LESSONS_BYTE_CAP:].decode(errors="replace")
            return "(tail) " + tail
        return text
    except Exception as exc:  # noqa: BLE001
        log.warning("orchestrator_brain: lessons.jsonl load failed — %s", exc)
        return "(lessons unavailable)"


_FITNESS_CONTRACT_REQUIREMENT = """\
FITNESS CONTRACT REQUIREMENT (mandatory on every proposal):
Every proposal MUST carry a fitness_contract field with:
  - sensor: which TIL fitness sensor it improves
  - expected_sign: direction of expected improvement
  - band: numeric band (e.g., [0.05, null] for IC > 5%)
  - check_by: ISO date when outcome is graded (typically 90-180 days out)
  - placebo_to_beat: a placebo or null benchmark
  - falsifier_spec: a qledger-compatible check dict
A proposal with no fitness_contract is automatically rejected by the adjudicator."""


# ── Main builder ───────────────────────────────────────────────────────────────

def _build_orchestrator_system(
    model: str | None = None,
    role: str | None = None,
    lobe: str | None = None,
    root: Path | None = None,
    organism_state: dict | None = None,
) -> str:
    """Build the orchestrator system prompt (full V2-D §3 spec).

    Parameters
    ----------
    model : str | None
        Resolved model ID.  Used to decide whether to inject fable_mode_core.md.
        Opus-class (contains 'opus' or unknown) → inject.
        Fable-class (contains 'fable') → OMIT.
    role : str | None
        Role key in metabolism_roles.yml (defaults to 'orchestrator').
    lobe : str | None
        Target lobe. Used to scope the case-law slice + charter + lobe card.
    root : Path | None
        Repo root override (for testing).
    organism_state : dict | None
        If provided, used directly (caller may pre-load it).
        If None, loaded from data/metabolism/organism_state.json.

    Returns
    -------
    str
        The complete system prompt.  NEVER raises.
    """
    try:
        repo = _repo_root(root)
        parts: list[str] = []

        # ── Part 1: Fable-mode doctrine (Opus-class models only) ──────────────
        if _is_opus_class(model):
            fable_text = _load_fable_mode_core(repo)
            if fable_text:
                parts.append("## Fable Mode Doctrine (vendored)\n\n" + fable_text)

        # ── Part 1b: Role line ─────────────────────────────────────────────────
        role_text = _load_role(repo, role)
        parts.append(f"## Role\n\n{role_text}")

        # ── Part 1c: Context Freshness header (R-V3-1) — right after Role/Doctrine,
        #    before Organism State, so the loop sees staleness before reasoning on data.
        try:
            from engine.metabolism import provenance as _prov  # noqa: PLC0415
            # Use real repo-relative paths so provenance can resolve file mtime.
            # Logical keys (e.g. "organism_state") resolve to nonexistent paths
            # and always yield age_days=None / staleness_reason="unknown-age".
            _freshness_blocks: list[dict] = [
                {"name": "organism_state", "source": "data/metabolism/organism_state.json",  "text": ""},
                {"name": "lessons",        "source": "data/metabolism/lessons.jsonl",         "text": ""},
                {"name": "case_law",       "source": "config/ruling_graph.yml",               "text": ""},
                {"name": "trajectory",     "source": "data/metabolism/trajectory.jsonl",      "text": ""},
            ]
            if lobe:
                _freshness_blocks.append(
                    {"name": "fitness", "source": f"data/metabolism/fitness/{lobe}.json", "text": ""}
                )
            _stamped = _prov.stamp_context(_freshness_blocks, root=repo)
            _freshness_header = _prov.render_freshness_header(_stamped)
            parts.append(f"## Context Freshness\n\n{_freshness_header}")
        except Exception as _exc:  # noqa: BLE001
            log.warning("orchestrator_brain: freshness header failed — %s", _exc)
            parts.append("## Context Freshness\n\n(freshness header unavailable)")

        # ── Part 2: Standing laws (quote-verified from ruling_graph.yml) ───────
        laws_text = _load_standing_laws(repo)
        parts.append(f"## Standing Laws (quote-verified from ruling_graph.yml)\n\n{laws_text}")

        # ── Part 3: Organism-state slice (byte-capped [:6000]) ─────────────────
        state_text = _build_state_slice(repo, lobe, organism_state)
        parts.append(f"## Organism State\n\n{state_text}")

        # ── Part 4: Case-law slice (lobe-scoped + DO_NOT_REBUILD) ──────────────
        case_law_text = _load_case_law_slice(repo, lobe)
        parts.append(f"## Case Law (lobe-scoped + DO_NOT_REBUILD)\n\n{case_law_text}")

        # ── Part 5a: Lobe charter (config/lobe_charters.yml, tolerant if absent)
        charter_text = _load_lobe_charter(repo, lobe)
        parts.append(f"## Lobe Charter\n\n{charter_text}")

        # ── Part 5b: Recent lessons — relevance-ranked recall (R-V3-2) ─────────
        try:
            from engine.metabolism import recall as _recall  # noqa: PLC0415
            lessons_text = _recall.recall_lessons(
                lobe=lobe,
                byte_budget=_LESSONS_BYTE_CAP,
                root=repo,
            )
        except Exception as _exc:  # noqa: BLE001
            log.warning("orchestrator_brain: recall.recall_lessons failed — %s", _exc)
            lessons_text = _load_recent_lessons(repo)
        parts.append(f"## Recent Lessons (from VERIFY outcomes)\n\n{lessons_text}")

        # ── Part 5c: Fitness-contract requirement ───────────────────────────────
        parts.append(f"## Fitness Contract Requirement\n\n{_FITNESS_CONTRACT_REQUIREMENT}")

        # ── Part 5d: Trajectory + strategic gap (R-V3-4) ───────────────────────
        try:
            from engine.metabolism import strategic as _strategic  # noqa: PLC0415
            _gap_text = _strategic.build_strategic_gap(organism_state, root=repo)
            _traj_parts: list[str] = [_gap_text]
            if lobe:
                _traj_text = _strategic.build_trajectory_block(lobe, root=repo)
                _traj_parts.append(_traj_text)
            parts.append(
                "## Trajectory & Strategic Gap\n\n" + "\n\n".join(_traj_parts)
            )
        except Exception as _exc:  # noqa: BLE001
            log.warning("orchestrator_brain: trajectory/strategic-gap failed — %s", _exc)
            parts.append("## Trajectory & Strategic Gap\n\n(unavailable)")

        # ── ACTIVE_BUILD_MAP collision check ────────────────────────────────────
        abm_path = repo / "docs" / "ACTIVE_BUILD_MAP.md"
        if abm_path.exists():
            try:
                abm_text = abm_path.read_text(encoding="utf-8")
                abm_text = _byte_cap(abm_text, _ABM_BYTE_CAP)
                parts.append(f"## Active Build Map (collision check)\n\n{abm_text}")
            except Exception as exc:  # noqa: BLE001
                log.warning("orchestrator_brain: ACTIVE_BUILD_MAP load failed — %s", exc)

        # ── INERTNESS reminder ──────────────────────────────────────────────────
        parts.append(
            "## INERTNESS CONSTRAINT\n\n"
            "You are INERT. You read, compute, and reason.\n"
            "You write the named artifact ONLY. You dispatch nothing, grant nothing, "
            "open no PR, touch no lobe roster. You never originate a signal, score, "
            "or escalation. The word flagged by check_validated_claims must never appear "
            "in your output."
        )

        return "\n\n---\n\n".join(parts)

    except Exception as exc:  # noqa: BLE001
        log.warning("orchestrator_brain._build_orchestrator_system: failed — %s", exc)
        return (
            "You are the Metabolism Orchestrator (V2-D, INERT).  "
            "Write the named artifact only.  Dispatch nothing, grant nothing.  "
            "Never originate signals, scores, or escalations."
        )
