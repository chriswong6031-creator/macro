"""engine/cycle_pattern/consumer_authority.py — CPI consumer-authority validator.

THE single canonical implementation of consumer-vocabulary validation for the
CPI truth registry (data/cycle_pattern/truths.jsonl). Reused by BOTH:

  - engine/cycle_pattern/truths.py's validate_truth() (write-time gate for
    every append_truth()/transition_truth() call), and
  - scripts/check_cycle_pattern_authority.py (CI-wired registry scan).

Never duplicate this vocabulary logic elsewhere — extend this module instead.

Background: research/imce/IMCE_A2_CPI_TRUTH_VOCABULARY_AUDIT_V1.md found the
registry answering to TWO disagreeing, undocumented vocabularies (17/29 rows
used config/cycle_pattern/truth_schema.md's prose list; 11/29 used
config/cycle_pattern/consumer_matrix.yml's `surfaces:` section) plus one
row (CPI-016) with a wholly private vocabulary invented by a single writer
script — and NO code path anywhere checked a consumer token's identity
against any named vocabulary (A2 finding F4). Sol's CPI-H1 rulings (see
research/imce/IMCE_D1C_RELEASE_RECORD.md) made
config/cycle_pattern/consumer_matrix.yml THE single canonical registry and
this module its sole enforcement point.

Design (CPI-H1 rulings, referenced by number below):
  1. consumer_matrix.yml `surfaces:` is the canonical token vocabulary.
  5. Every truth row's forbidden_consumers must carry all four universal
     money-path tokens (board_rank, oracle_escalation,
     sector_central_direction_score, position_sizing), regardless of status
     or effect_class.
  6. A `promoted_null`-status row may never grant neuralweb_context in
     allowed_consumers — the matrix's promoted_null class forbid wins over
     any row-level grant (A2 finding F6).
  8. Row allowlists are least-privilege subsets of their status class.

  Fable adjudication (2026-08-21, extending rulings 6+8): the neuralweb_context
  check below is matrix-DRIVEN, not a hardcoded single-status allowlist — it
  checks, for a row's actual status, whether that status's artifact_classes
  entry in consumer_matrix.yml forbids neuralweb_context, and if so rejects a
  row-level grant. Originally implemented as a promoted_null-only hardcoded
  set (the only status A2's F6 enumerated); Fable adjudicated that the
  identical defect exists one class over — the `candidates`/`retired`
  classes also forbid neuralweb_context in the matrix, and a row of that
  status granting it is the same "matrix wins" violation, not a different
  rule. This is still a bounded, single-token check (not a general
  row-allowed ⊆ class-allowed subset check for every token) — it only ever
  fires for neuralweb_context, driven by whatever the matrix currently says
  for that one token per class, so it self-updates if the matrix's per-class
  forbids change and needs no further hardcoded edits here.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MATRIX_PATH = _REPO_ROOT / "config" / "cycle_pattern" / "consumer_matrix.yml"

# Universal money-path forbids: every truth row, regardless of status or
# effect_class, must carry all four in forbidden_consumers (CPI-H1 ruling 5).
UNIVERSAL_MONEY_PATH_FORBIDS: frozenset[str] = frozenset({
    "board_rank",
    "oracle_escalation",
    "sector_central_direction_score",
    "position_sizing",
})

# The specific token this module additionally cross-checks against each
# row's status-class forbid (CPI-H1 ruling 6 / A2 finding F6, generalized by
# Fable adjudication 2026-08-21 — see the module docstring). Kept as a named
# constant rather than inlined so the intent ("this one token, matrix-driven,
# per class") stays legible.
_CLASS_CONDITIONAL_TOKEN = "neuralweb_context"


class ConsumerAuthorityError(ValueError):
    """Raised when a truth row's consumer vocabulary violates the matrix."""


@lru_cache(maxsize=8)
def _load_matrix_cached(path_str: str) -> dict[str, Any]:
    with open(path_str, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_matrix(path: Path | None = None) -> dict[str, Any]:
    """Load and return the parsed consumer_matrix.yml (cached by path)."""
    p = Path(path) if path else MATRIX_PATH
    return _load_matrix_cached(str(p))


def canonical_tokens(path: Path | None = None) -> frozenset[str]:
    """Union of every token named in the matrix's surfaces: registry.

    This is the FULL canonical vocabulary — any allowed_consumers or
    forbidden_consumers token not in this set is either a retired alias
    (see RETIRED_ALIASES below) or a true orphan.
    """
    matrix = load_matrix(path)
    tokens: set[str] = set()
    for group_name, group in matrix.get("surfaces", {}).items():
        tokens.update(group)
    return frozenset(tokens)


def retired_aliases(path: Path | None = None) -> dict[str, str | None]:
    """Return the matrix's documented retired_aliases map (old -> new|None)."""
    matrix = load_matrix(path)
    return dict(matrix.get("retired_aliases", {}))


# The matrix's artifact_classes entry names do not all match the truth
# `status` enum (engine/cycle_pattern/truths.py VALID_STATUSES) verbatim:
# the matrix names its Research Factory candidate-artifact class "candidates"
# (plural — pre-dates CPI-H1, and tests/test_check_cycle_pattern_authority.py
# pins that exact spelling), while the truth status value is "candidate"
# (singular). Every other status name matches its matrix class name exactly.
# Without this bridge, class_allowed_consumers("candidate")/
# class_forbidden_consumers("candidate") silently returned an empty result
# (no matching `class:` entry) — discovered when Fable's adjudication
# extending the neuralweb_context/class-forbid check to the candidates class
# needed a candidate-status row to actually resolve against it.
_STATUS_TO_CLASS_NAME: dict[str, str] = {"candidate": "candidates"}


def class_allowed_consumers(status: str, path: Path | None = None) -> frozenset[str]:
    class_name = _STATUS_TO_CLASS_NAME.get(status, status)
    matrix = load_matrix(path)
    for entry in matrix.get("artifact_classes", []):
        if entry.get("class") == class_name:
            return frozenset(entry.get("allowed_consumers", []))
    return frozenset()


def class_forbidden_consumers(status: str, path: Path | None = None) -> frozenset[str]:
    class_name = _STATUS_TO_CLASS_NAME.get(status, status)
    matrix = load_matrix(path)
    for entry in matrix.get("artifact_classes", []):
        if entry.get("class") == class_name:
            return frozenset(entry.get("forbidden_consumers", []))
    return frozenset()


def validate_consumer_vocabulary(row: dict[str, Any], *, path: Path | None = None) -> None:
    """Validate a single truth row's allowed_consumers/forbidden_consumers.

    Raises ConsumerAuthorityError on any violation:
      - any token (allowed or forbidden) not in the canonical matrix
        vocabulary — retired aliases get a specific "use X instead" (or
        "retired outright") message rather than a generic orphan message;
      - forbidden_consumers missing any of the four universal money-path
        tokens (CPI-H1 ruling 5);
      - allowed_consumers containing neuralweb_context on a status whose
        matrix artifact_classes entry forbids it (CPI-H1 ruling 6 / A2 F6,
        generalized by Fable adjudication to every class the matrix names,
        not just promoted_null — currently promoted_null, candidates, and
        retired/superseded).

    Does NOT check required-field presence, enum validity, falsifiers, or
    evidence_refs — those remain engine/cycle_pattern/truths.py's
    validate_truth() responsibility. This function is consumer-vocabulary
    ONLY, so it can be reused standalone by the CI-wired registry scan
    without pulling in the full truth schema.
    """
    tid = row.get("truth_id", "?")
    status = row.get("status", "?")
    allowed = row.get("allowed_consumers") or []
    forbidden = row.get("forbidden_consumers") or []
    canonical = canonical_tokens(path)
    aliases = retired_aliases(path)

    for token in list(allowed) + list(forbidden):
        if token in canonical:
            continue
        if token in aliases:
            target = aliases[token]
            hint = f"use {target!r} instead" if target else (
                "retired outright, no replacement — not an established pipeline "
                "surface (CPI-H1 ruling 4); a real future surface needs its own "
                "reviewed registration in config/cycle_pattern/consumer_matrix.yml"
            )
            raise ConsumerAuthorityError(
                f"{tid}: token {token!r} is a retired alias ({hint}) — see "
                f"research/imce/IMCE_A2_CPI_TRUTH_VOCABULARY_AUDIT_V1.md / "
                f"research/imce/IMCE_D1C_RELEASE_RECORD.md"
            )
        raise ConsumerAuthorityError(
            f"{tid}: token {token!r} is not in the canonical "
            f"config/cycle_pattern/consumer_matrix.yml vocabulary (orphan token) "
            f"— register it in the matrix's surfaces: section first"
        )

    missing_universal = UNIVERSAL_MONEY_PATH_FORBIDS - set(forbidden)
    if missing_universal:
        raise ConsumerAuthorityError(
            f"{tid}: forbidden_consumers missing universal money-path token(s) "
            f"required on every row (CPI-H1 ruling 5): {sorted(missing_universal)}"
        )

    class_forbidden = class_forbidden_consumers(status, path)
    if _CLASS_CONDITIONAL_TOKEN in class_forbidden and _CLASS_CONDITIONAL_TOKEN in allowed:
        raise ConsumerAuthorityError(
            f"{tid}: status={status!r} rows may not grant {_CLASS_CONDITIONAL_TOKEN} in "
            f"allowed_consumers — the matrix's {status} class forbid wins over "
            f"any row-level grant (CPI-H1 ruling 6 / A2 finding F6; extended to "
            f"non-promoted_null classes by Fable adjudication 2026-08-21)"
        )


def validate_registry(rows: list[dict[str, Any]], *, path: Path | None = None) -> list[str]:
    """Validate consumer vocabulary for every row given; return error strings.

    Empty list = every row passes. Does not de-duplicate by truth_id/version
    — callers deciding whether to check only latest-version rows (the usual
    choice, since historical append-only rows predating a heal can never be
    corrected in place) must filter `rows` themselves before calling this.
    """
    errors: list[str] = []
    for row in rows:
        try:
            validate_consumer_vocabulary(row, path=path)
        except ConsumerAuthorityError as exc:
            errors.append(str(exc))
    return errors
