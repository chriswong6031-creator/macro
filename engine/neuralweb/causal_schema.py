"""engine.neuralweb.causal_schema — Mechanism-card schema, validators, and instrument library.

Schema: neuralweb.causal_mechanism_card.v1

CHF-R7 rulings
--------------
- Frozen environment map: frozen_hash is computed from the canonical JSON of the
  split set AT MINT TIME; any card whose hash doesn't match its own map is tamper-
  evidence and is rejected by validate_card().
- Authority block copied verbatim from the MPC pattern (tier display, not_a_signal
  True, may_rank/gate/size/escalate False, forbidden_uses list).
- Falsifiers: ≥2 mandatory.
- Status machine (CHF-R17): statuses = inbox → deduped → skeptic_passed → filed |
  decayed | rejected.  Transitions carry actor ∈ {script, operator, fable}; an actor
  value of 'llm' (or any other unlisted value) attempting ANY transition raises.
- Banned words (RUL-CC-5): caused/proved/proof/validated replaced with lawful phrasing
  in claim_en, claim_zh, and falsifiers text on validation.

CHF-R9: instrument library loaded from config/causal_instruments.yml; validator
enforces mandatory exogeneity_class and required_confounds for surprise_component and
endogenous_reaction instruments.

Public API
----------
validate_card(card) -> list[str]  (empty list = valid)
transition_card(card, to, actor, reason) -> dict (mutated copy)
canonical_card(card) -> str
load_instruments(root) -> list[dict]
validate_instruments(instruments) -> list[str]
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema identity
# ---------------------------------------------------------------------------

SCHEMA = "neuralweb.causal_mechanism_card.v1"

# ---------------------------------------------------------------------------
# Vocabulary constants
# ---------------------------------------------------------------------------

VALID_FAMILIES = frozenset({
    "liquidity_transmission",
    "macro_transmission",
    "rotation_transfer",
    "entry_quality",
    "exit_fragility",
    "confluence_independence",
    "factor_mirage",
    "context_organ",
    "null_mining",
})

VALID_SOURCES = frozenset({"llm_proposed", "operator", "scout_edge"})

# Status machine (CHF-R17)
VALID_STATUSES = frozenset({"inbox", "deduped", "skeptic_passed", "filed", "decayed", "rejected"})

# Allowed forward transitions: {from_status: {to_statuses}}
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "inbox": frozenset({"deduped", "rejected"}),
    "deduped": frozenset({"skeptic_passed", "rejected"}),
    "skeptic_passed": frozenset({"filed", "rejected"}),
    "filed": frozenset({"decayed", "rejected"}),
    "decayed": frozenset(),   # terminal
    "rejected": frozenset(),  # terminal
}

# Allowed actors (CHF-R17) — 'llm' is NEVER allowed
ALLOWED_ACTORS = frozenset({"script", "operator", "fable"})

# Minimum falsifiers required
MIN_FALSIFIERS = 2

# Minimum min_n floor (house floor)
MIN_N_FLOOR = 25

# ---------------------------------------------------------------------------
# Authority block (verbatim from MPC pattern — CHF-R7)
# ---------------------------------------------------------------------------

AUTHORITY_BLOCK: dict[str, Any] = {
    "tier": "display",
    "horizon_role": "context",
    "weights": "none",
    "scored_path_surfaces": [],
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "display_only": True,
    "not_a_signal": True,
    "forbidden_uses": [
        "ranking",
        "sizing",
        "alert_escalation",
        "claim_validation",
        "board_ordering",
        "mastermind_arming",
    ],
}

# ---------------------------------------------------------------------------
# Banned-word sanitizer (RUL-CC-5)
# ---------------------------------------------------------------------------

# Each tuple: (banned, lawful_replacement)
_BANNED_SUBSTITUTIONS = [
    ("proved", "is consistent with"),
    ("proof", "evidence"),
    ("caused", "co-moved with"),
    ("validated", "tested"),
]


def _sanitize_text(text: str) -> str:
    """Replace banned words with lawful phrasing (RUL-CC-5).

    Applied to claim_en, claim_zh, and falsifier text.  Case-insensitive
    replacement using both word-boundary (\b) and non-word-character boundary
    patterns, so banned words adjacent to CJK characters or punctuation are
    also caught.  Grammatical output is preserved.
    """
    import re
    result = text
    for banned, replacement in _BANNED_SUBSTITUTIONS:
        # Primary: word-boundary match (works for ASCII contexts)
        wb_pattern = re.compile(r"\b" + re.escape(banned) + r"\b", re.IGNORECASE)
        new_result = wb_pattern.sub(replacement, result)
        if new_result == result:
            # Fallback: match when surrounded by non-alpha or start/end of string
            # (covers banned words adjacent to CJK characters)
            fb_pattern = re.compile(
                r"(?<![a-zA-Z])" + re.escape(banned) + r"(?![a-zA-Z])",
                re.IGNORECASE,
            )
            new_result = fb_pattern.sub(replacement, result)
        result = new_result
    return result


def _contains_banned(text: str) -> list[str]:
    """Return list of banned words found in text (before sanitization)."""
    import re
    found = []
    for banned, _ in _BANNED_SUBSTITUTIONS:
        # Check word-boundary first, then fallback for CJK adjacency
        if re.search(r"\b" + re.escape(banned) + r"\b", text, re.IGNORECASE):
            found.append(banned)
        elif re.search(
            r"(?<![a-zA-Z])" + re.escape(banned) + r"(?![a-zA-Z])",
            text,
            re.IGNORECASE,
        ):
            found.append(banned)
    return found

# ---------------------------------------------------------------------------
# Frozen environment-map hash (CHF-R7)
# ---------------------------------------------------------------------------

def _compute_env_hash(environment_map: dict) -> str:
    """Compute SHA-256 of the canonical JSON of the environment split set.

    The canonical form sorts both the dict keys and the list values within
    should_hold and should_break so the hash is stable regardless of insertion
    order.
    """
    canonical = {
        "should_hold": sorted(environment_map.get("should_hold", [])),
        "should_break": sorted(environment_map.get("should_break", [])),
    }
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Canonical card (for dedup hashing)
# ---------------------------------------------------------------------------

def canonical_card(card: dict) -> str:
    """Return the canonical JSON string for dedup hashing.

    Uses sort_keys + separators to produce a deterministic string that is
    stable across Python dict insertion orders.  The 'status', 'lineage.pack_id',
    and mutable provenance fields are intentionally INCLUDED so the hash changes
    if the card's content changes — this is the DEDUP hash, not the TAMPER hash.
    """
    return json.dumps(card, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      default=str)

# ---------------------------------------------------------------------------
# CLAIM_SHAPES import (for exit-a validation)
# ---------------------------------------------------------------------------

def _get_claim_shapes() -> frozenset[str]:
    """Import CLAIM_SHAPES from metabolism; fall back to the known set if unavailable."""
    try:
        from engine.neuralweb.metabolism import CLAIM_SHAPES  # type: ignore[import]
        return CLAIM_SHAPES
    except Exception:  # noqa: BLE001
        # Fallback in case of import issues — mirrors metabolism.py CLAIM_SHAPES
        return frozenset({"lead_lag", "conditional_regime", "entry_quality", "sector_conditional"})

# ---------------------------------------------------------------------------
# Card validator
# ---------------------------------------------------------------------------

def validate_card(card: dict) -> list[str]:
    """Validate a mechanism card dict against the neuralweb.causal_mechanism_card.v1 schema.

    Returns a list of error strings (empty list = valid).
    """
    errors: list[str] = []

    if not isinstance(card, dict):
        return ["card must be a dict"]

    # --- Required top-level fields ---
    required_fields = [
        "mechanism_id", "family", "claim_en", "claim_zh",
        "causal_graph", "environment_map", "falsifiers", "test_spec",
        "lineage", "status",
    ]
    for field in required_fields:
        if field not in card:
            errors.append(f"missing required field: {field}")

    if errors:
        # Can't validate further if required fields are missing
        return errors

    # --- mechanism_id ---
    mid = card["mechanism_id"]
    if not isinstance(mid, str) or not mid:
        errors.append("mechanism_id must be a non-empty string")

    # --- family ---
    family = card["family"]
    if family not in VALID_FAMILIES:
        errors.append(f"family: must be one of {sorted(VALID_FAMILIES)}, got {family!r}")

    # --- claim_en / claim_zh ---
    for field in ("claim_en", "claim_zh"):
        val = card[field]
        if not isinstance(val, str) or not val:
            errors.append(f"{field}: must be a non-empty string")
        else:
            banned = _contains_banned(val)
            if banned:
                errors.append(
                    f"{field}: contains banned word(s) {banned} (RUL-CC-5); "
                    f"call _sanitize_text() before validation"
                )

    # --- causal_graph ---
    cg = card["causal_graph"]
    if not isinstance(cg, dict):
        errors.append("causal_graph must be a dict")
    else:
        for cgf in ("cause", "target"):
            if not cg.get(cgf):
                errors.append(f"causal_graph.{cgf}: required non-empty string")
        for cglist in ("mediators", "confounders", "colliders_to_avoid"):
            if not isinstance(cg.get(cglist, []), list):
                errors.append(f"causal_graph.{cglist}: must be a list")

    # --- environment_map ---
    em = card["environment_map"]
    if not isinstance(em, dict):
        errors.append("environment_map must be a dict")
    else:
        for emf in ("should_hold", "should_break"):
            if not isinstance(em.get(emf, []), list):
                errors.append(f"environment_map.{emf}: must be a list")
        # Frozen hash check (CHF-R7 tamper evidence)
        stored_hash = em.get("frozen_hash")
        if not stored_hash:
            errors.append("environment_map.frozen_hash: required; compute with _compute_env_hash()")
        else:
            expected_hash = _compute_env_hash(em)
            if stored_hash != expected_hash:
                errors.append(
                    f"environment_map.frozen_hash mismatch: stored={stored_hash!r}, "
                    f"expected={expected_hash!r} — environment map was altered after mint"
                )

    # --- falsifiers ---
    falsifiers = card["falsifiers"]
    if not isinstance(falsifiers, list):
        errors.append("falsifiers must be a list")
    elif len(falsifiers) < MIN_FALSIFIERS:
        errors.append(
            f"falsifiers: at least {MIN_FALSIFIERS} required, got {len(falsifiers)}"
        )
    else:
        for i, f in enumerate(falsifiers):
            if not isinstance(f, str) or not f:
                errors.append(f"falsifiers[{i}]: must be a non-empty string")
            else:
                banned = _contains_banned(f)
                if banned:
                    errors.append(
                        f"falsifiers[{i}]: contains banned word(s) {banned} (RUL-CC-5)"
                    )

    # --- test_spec ---
    ts = card["test_spec"]
    if not isinstance(ts, dict):
        errors.append("test_spec must be a dict")
    else:
        exit_path = ts.get("exit_path")
        if exit_path not in ("a", "b"):
            errors.append(f"test_spec.exit_path: must be 'a' or 'b', got {exit_path!r}")

        # exit-a specific: claim_shape must be in CLAIM_SHAPES
        if exit_path == "a":
            cs = ts.get("claim_shape")
            if not cs:
                errors.append("test_spec.claim_shape: required for exit_path='a'")
            else:
                claim_shapes = _get_claim_shapes()
                if cs not in claim_shapes:
                    errors.append(
                        f"test_spec.claim_shape: must be one of {sorted(claim_shapes)}, "
                        f"got {cs!r}"
                    )
        # exit-b specific: domain_harness ref
        elif exit_path == "b":
            if not ts.get("domain_harness"):
                errors.append("test_spec.domain_harness: required for exit_path='b'")

        # horizon_d
        hdv = ts.get("horizon_d")
        if hdv is not None and not isinstance(hdv, int):
            errors.append("test_spec.horizon_d: must be an integer")

        # min_n floor
        min_n = ts.get("min_n")
        if min_n is not None:
            if not isinstance(min_n, int):
                errors.append("test_spec.min_n: must be an integer")
            elif min_n < MIN_N_FLOOR:
                errors.append(
                    f"test_spec.min_n: {min_n} is below house floor {MIN_N_FLOOR}; "
                    f"clamp to {MIN_N_FLOOR} before validation"
                )

    # --- lineage ---
    lin = card["lineage"]
    if not isinstance(lin, dict):
        errors.append("lineage must be a dict")
    else:
        source = lin.get("source")
        if source not in VALID_SOURCES:
            errors.append(
                f"lineage.source: must be one of {sorted(VALID_SOURCES)}, got {source!r}"
            )

    # --- status ---
    status = card["status"]
    if status not in VALID_STATUSES:
        errors.append(
            f"status: must be one of {sorted(VALID_STATUSES)}, got {status!r}"
        )

    return errors


def sanitize_card(card: dict) -> dict:
    """Return a copy of the card with banned words replaced in text fields (RUL-CC-5)."""
    import copy
    c = copy.deepcopy(card)
    for field in ("claim_en", "claim_zh"):
        if isinstance(c.get(field), str):
            c[field] = _sanitize_text(c[field])
    falsifiers = c.get("falsifiers")
    if isinstance(falsifiers, list):
        c["falsifiers"] = [
            _sanitize_text(f) if isinstance(f, str) else f
            for f in falsifiers
        ]
    return c

# ---------------------------------------------------------------------------
# Status machine transition (CHF-R17)
# ---------------------------------------------------------------------------

class IllegalTransition(Exception):
    """Raised when a status transition is illegal."""


def transition_card(card: dict, to: str, actor: str, reason: str) -> dict:
    """Return a mutated copy of the card with updated status.

    Enforces:
    - actor must be in ALLOWED_ACTORS (CHF-R17: 'llm' or any unlisted actor raises)
    - to must be a valid status
    - the transition must be allowed from the current status

    Does NOT write to disk.  The caller is responsible for persistence.
    """
    import copy

    # CHF-R17: LLM actor law — any non-allowed actor raises
    if actor not in ALLOWED_ACTORS:
        raise IllegalTransition(
            f"actor={actor!r} is not allowed (CHF-R17); "
            f"LLMs may not transition card status; "
            f"allowed actors: {sorted(ALLOWED_ACTORS)}"
        )

    if to not in VALID_STATUSES:
        raise IllegalTransition(
            f"target status {to!r} is not a valid status; "
            f"valid: {sorted(VALID_STATUSES)}"
        )

    current = card.get("status")
    if current not in _ALLOWED_TRANSITIONS:
        raise IllegalTransition(
            f"current status {current!r} is not a known status; "
            f"valid: {sorted(VALID_STATUSES)}"
        )

    allowed = _ALLOWED_TRANSITIONS[current]
    if to not in allowed:
        raise IllegalTransition(
            f"transition {current!r} → {to!r} is not allowed; "
            f"allowed from {current!r}: {sorted(allowed) or '(terminal)'}"
        )

    c = copy.deepcopy(card)
    c["status"] = to
    # Append transition event to lineage history
    if not isinstance(c.get("lineage"), dict):
        c["lineage"] = {}
    history = c["lineage"].get("transitions", [])
    history.append({"from": current, "to": to, "actor": actor, "reason": reason})
    c["lineage"]["transitions"] = history
    return c

# ---------------------------------------------------------------------------
# Instrument library (CHF-R9)
# ---------------------------------------------------------------------------

VALID_EXOGENEITY_CLASSES = frozenset({"timing_only", "surprise_component", "endogenous_reaction"})

# Classes that require non-empty required_confounds
_CONFOUNDS_REQUIRED_CLASSES = frozenset({"surprise_component", "endogenous_reaction"})


def load_instruments(root: str | Path | None = None) -> list[dict]:
    """Load config/causal_instruments.yml from the repo root.

    Returns an empty list if the file is absent (absent-safe).
    """
    if root is None:
        root = Path(__file__).resolve().parents[2]
    p = Path(root) / "config" / "causal_instruments.yml"
    if not p.exists():
        log.warning("causal_instruments.yml not found at %s", p)
        return []
    try:
        import yaml  # type: ignore[import]
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data.get("instruments", []) if isinstance(data, dict) else []
    except Exception as exc:  # noqa: BLE001
        log.warning("load_instruments: could not load %s: %s", p, exc)
        return []


def validate_instruments(instruments: list[dict]) -> list[str]:
    """Validate the instrument library entries.

    Returns a list of error strings (empty = all valid).
    """
    errors: list[str] = []
    for i, entry in enumerate(instruments):
        iid = entry.get("instrument_id", f"[index {i}]")
        prefix = f"instruments[{iid}]"

        eclass = entry.get("exogeneity_class")
        if not eclass:
            errors.append(f"{prefix}: missing required field exogeneity_class")
        elif eclass not in VALID_EXOGENEITY_CLASSES:
            errors.append(
                f"{prefix}: exogeneity_class must be one of "
                f"{sorted(VALID_EXOGENEITY_CLASSES)}, got {eclass!r}"
            )
        else:
            # required_confounds must be non-empty for surprise_component and endogenous_reaction
            if eclass in _CONFOUNDS_REQUIRED_CLASSES:
                confounds = entry.get("required_confounds", [])
                if not isinstance(confounds, list) or not confounds:
                    errors.append(
                        f"{prefix}: required_confounds must be a non-empty list "
                        f"for exogeneity_class={eclass!r}"
                    )

    return errors
