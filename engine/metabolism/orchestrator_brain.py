"""engine.metabolism.orchestrator_brain — System-prompt builder stub (V2-A).

_build_orchestrator_system(model, role, lobe) is the ONE versioned helper
imported by every orchestrator-tier reasoner (organism_state pass, agenda, dream)
so the persona is consistent across all LLM calls.  Full prompt engine is V2-D;
here we ship the STUB that handles the required V2-A agenda call.

What this stub does (per R-V2-2, §3 of V2 masterplan):
  1. Role line from config/metabolism_roles.yml (or a default role).
  2. If model is Opus-class → prepend config/fable_mode_core.md (IMMUTABLE).
  3. A small quoted slice of standing laws from ruling_graph.yml (by topic tags).
  4. Byte-capped context (mirrors propose.py's [:6000] discipline).

NEVER reads ~/.  All paths relative to repo root.
NEVER-RAISE: returns a minimal safe prompt on any failure.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Byte cap for the organism-state slice injected into the system prompt
_ORGANISM_STATE_BYTE_CAP = 6000
# Byte cap for the ruling graph slice
_RULING_SLICE_BYTE_CAP = 2000
# Byte cap for the ACTIVE_BUILD_MAP slice
_ABM_BYTE_CAP = 1500

# Opus-class model name substrings
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
    # Unknown model → inject to be safe
    return True


def _read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None


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


def _load_ruling_slice(root: Path) -> str:
    """Load a small slice of standing laws from ruling_graph.yml.

    Selects rulings tagged with metabolism/autonomic-loop/display-only topics.
    Byte-capped.
    """
    p = root / "config" / "ruling_graph.yml"
    if not p.exists():
        return "(ruling_graph.yml not found)"
    try:
        import yaml  # noqa: PLC0415
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        rulings = raw.get("rulings") or []
        if isinstance(rulings, dict):
            rulings = list(rulings.values())

        target_tags = {
            "display-only", "autonomic", "metabolism", "gauntlet",
            "signal-origination", "llm-origination", "stateless",
        }
        selected: list[str] = []
        for r in rulings:
            if not isinstance(r, dict):
                continue
            tags = set(r.get("tags") or [])
            title = str(r.get("title") or r.get("short_name") or "")
            ruling = str(r.get("ruling") or "")
            if tags & target_tags:
                snippet = f"[{r.get('short_name', title)}] {ruling}"
                selected.append(snippet[:300])
            if len("\n".join(selected).encode()) >= _RULING_SLICE_BYTE_CAP:
                break

        if not selected:
            # Fallback: the most important standing laws, hard-coded
            selected = [
                "[R-AUT-1] The signal path stays deterministic; the loop authors CODE, not signals. "
                "No loop-authored change may make an LLM originate a runtime signal/score/escalation.",
                "[gauntlet-is-promotion-gate] Gauntlet = promotion gate, not build gate. "
                "A null never blocks building or accrual.",
                "[display-only-until-gauntleted] All outputs are display-only until gauntleted. "
                "LLMs may only de-escalate calibrated keys — never originate signals, scores, or escalations.",
            ]

        slice_text = "\n".join(selected)
        if len(slice_text.encode()) > _RULING_SLICE_BYTE_CAP:
            slice_text = slice_text.encode()[:_RULING_SLICE_BYTE_CAP].decode(errors="replace")
        return slice_text
    except Exception as exc:  # noqa: BLE001
        log.warning("orchestrator_brain: cannot load ruling slice — %s", exc)
        return "(ruling slice unavailable)"


def _load_abm_slice(root: Path) -> str:
    """Load a byte-capped slice of ACTIVE_BUILD_MAP.md."""
    p = root / "docs" / "ACTIVE_BUILD_MAP.md"
    if not p.exists():
        return "(ACTIVE_BUILD_MAP.md not found)"
    try:
        text = p.read_text(encoding="utf-8")
        encoded = text.encode()
        if len(encoded) > _ABM_BYTE_CAP:
            text = encoded[:_ABM_BYTE_CAP].decode(errors="replace") + "\n… (truncated)"
        return text
    except Exception as exc:  # noqa: BLE001
        log.warning("orchestrator_brain: cannot load ACTIVE_BUILD_MAP — %s", exc)
        return "(ACTIVE_BUILD_MAP unavailable)"


def _build_orchestrator_system(
    model: str | None = None,
    role: str | None = None,
    lobe: str | None = None,
    root: Path | None = None,
    organism_state: dict | None = None,
) -> str:
    """Build the orchestrator system prompt.

    Parameters
    ----------
    model : str | None
        Resolved model ID.  Used to decide whether to inject fable_mode_core.md.
    role : str | None
        Role key in metabolism_roles.yml (defaults to 'orchestrator').
    lobe : str | None
        Target lobe (used to scope the case-law slice; currently unused in stub).
    root : Path | None
        Repo root override (for testing).
    organism_state : dict | None
        If provided, a byte-capped slice is injected.

    Returns
    -------
    str
        The complete system prompt.  NEVER raises.
    """
    try:
        repo = _repo_root(root)
        parts: list[str] = []

        # 1. Fable-mode doctrine (Opus-class models only)
        if _is_opus_class(model):
            fable_text = _load_fable_mode_core(repo)
            if fable_text:
                parts.append("## Fable Mode Doctrine (vendored)\n\n" + fable_text)

        # 2. Role line
        role_text = _load_role(repo, role)
        parts.append(f"## Role\n\n{role_text}")

        # 3. Standing laws slice
        ruling_slice = _load_ruling_slice(repo)
        parts.append(f"## Standing Laws (from ruling_graph)\n\n{ruling_slice}")

        # 4. Organism-state slice (byte-capped)
        if organism_state:
            try:
                os_text = json.dumps(organism_state, indent=2, ensure_ascii=False)
                encoded = os_text.encode()
                if len(encoded) > _ORGANISM_STATE_BYTE_CAP:
                    os_text = encoded[:_ORGANISM_STATE_BYTE_CAP].decode(errors="replace") + "\n… (truncated)"
                parts.append(f"## Organism State (current)\n\n```json\n{os_text}\n```")
            except Exception as exc:  # noqa: BLE001
                log.warning("orchestrator_brain: organism_state serialization failed — %s", exc)

        # 5. ACTIVE_BUILD_MAP slice
        abm_slice = _load_abm_slice(repo)
        parts.append(f"## Active Build Map (collision check)\n\n{abm_slice}")

        # 6. INERTNESS reminder
        parts.append(
            "## INERTNESS CONSTRAINT\n\n"
            "You are operating in Phase V2-A: ZERO authority.  You read, compute, and reason.\n"
            "You write the agenda artifact ONLY.  You dispatch nothing, grant nothing, "
            "open no PR, touch no lobe roster.  The agenda is a PROPOSAL consumed by "
            "later (still-inert) stages."
        )

        return "\n\n---\n\n".join(parts)

    except Exception as exc:  # noqa: BLE001
        log.warning("orchestrator_brain._build_orchestrator_system: failed — %s", exc)
        return (
            "You are the Metabolism Orchestrator (V2-A, INERT).  "
            "Write a ranked agenda artifact only.  Dispatch nothing, grant nothing."
        )
