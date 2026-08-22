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

  Fable adjudication (2026-08-21, extending rulings 6+8) originally added a
  bounded, neuralweb_context-only class-conditional check here (matrix-
  driven per-class forbid, not a hardcoded promoted_null-only set). CPI-H1.1
  (below) SUPERSEDES that single-token mechanism with the general
  row-allowed ⊆ class-allowed subset check — ruling 6's neuralweb_context
  case is now just one instance of ruling 8's general invariant, not a
  separate code path.

  Fable adjudication round 2 (2026-08-21, Opus red-team closure): HARD checks
  added — allowed_consumers may never contain a surfaces:money_path token
  (a row may forbid money-path surfaces, never grant them), and
  allowed_consumers/forbidden_consumers may never overlap on any token (the
  matrix's own stated "disjoint lists" design principle). An unmapped/typo'd
  status now RAISES rather than silently returning an empty class-forbid set
  (_require_class_entry). allowed_consumers/forbidden_consumers are
  type-validated as lists of strings.

  CPI-H1.1 (Sol adjudication, 2026-08-21/22, class-envelope closure):
  ruling 8's least-privilege class-subset invariant —
  set(row.allowed_consumers) <= set(status_class.allowed_consumers) — is now
  HARD, not advisory. The 7 rows escalated at the CPI-H1 heal
  (CPI-002/004/005/008/011/014/015, research/imce/IMCE_D1C_RELEASE_RECORD.md)
  were adjudicated as legitimate specialized display consumers, not leaks —
  the matrix's `display`/`promoted_null` class envelopes were the
  incomplete half, and were amended in config/cycle_pattern/consumer_matrix.yml
  to cover exactly those rows' pre-existing grants. The WARN-tier
  `advisory_class_subset_violations()` function this module used to carry is
  RETIRED — its check was promoted into validate_consumer_vocabulary() below
  rather than left standing as a second, shadowing WARN path for the same
  invariant. Both reuse call sites (engine/cycle_pattern/truths.py's
  validate_truth() and scripts/check_cycle_pattern_authority.py's
  scan_registry_vocabulary()) inherit the HARD check automatically because
  both already route through validate_consumer_vocabulary()/
  validate_registry() — no call-site logic change was needed there beyond
  removing the now-dead separate advisory reporting path.
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


def money_path_tokens(path: Path | None = None) -> frozenset[str]:
    """The matrix's surfaces:money_path group.

    These four tokens must never appear in ANY row's allowed_consumers
    (Fable adjudication, 2026-08-21 — the matrix's own disjoint-lists design
    principle, machine-enforced going forward).
    """
    matrix = load_matrix(path)
    return frozenset(matrix.get("surfaces", {}).get("money_path", []))


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


def _class_entry(status: str, path: Path | None = None) -> dict[str, Any] | None:
    """Return the matrix artifact_classes entry for status, or None if unmapped."""
    class_name = _STATUS_TO_CLASS_NAME.get(status, status)
    matrix = load_matrix(path)
    for entry in matrix.get("artifact_classes", []):
        if entry.get("class") == class_name:
            return entry
    return None


def _require_class_entry(status: str, path: Path | None = None) -> dict[str, Any]:
    """Return the matrix artifact_classes entry for status; RAISE if unmapped.

    An unmapped status is never treated as "no class-level forbids" (a
    vacuous empty frozenset that would silently disable every class-driven
    check for that row) — Fable adjudication (2026-08-21, MINOR-1): a typo'd
    or genuinely-new-but-unregistered status must fail loudly, not pass by
    accident.
    """
    entry = _class_entry(status, path)
    if entry is None:
        class_name = _STATUS_TO_CLASS_NAME.get(status, status)
        raise ConsumerAuthorityError(
            f"status={status!r} has no matching config/cycle_pattern/"
            f"consumer_matrix.yml artifact_classes entry (looked for "
            f"class: {class_name!r}) — register a matching class before "
            f"using this status, or fix the typo"
        )
    return entry


def class_allowed_consumers(status: str, path: Path | None = None) -> frozenset[str]:
    """Raises ConsumerAuthorityError if `status` has no matching matrix class."""
    return frozenset(_require_class_entry(status, path).get("allowed_consumers", []))


def class_forbidden_consumers(status: str, path: Path | None = None) -> frozenset[str]:
    """Raises ConsumerAuthorityError if `status` has no matching matrix class."""
    return frozenset(_require_class_entry(status, path).get("forbidden_consumers", []))


def _require_string_list(value: Any, field_name: str, tid: str) -> list[str]:
    """Validate `value` is a list of str; raise a clear ConsumerAuthorityError otherwise.

    Fable adjudication (2026-08-21, MINOR-2): `None` or a bare string used to
    be silently accepted (`row.get(field) or []` treats None as empty; a bare
    str like "measurement_page" would iterate CHARACTER BY CHARACTER — a
    silent, dangerous misparse, not a clean rejection).
    """
    if not isinstance(value, list):
        raise ConsumerAuthorityError(
            f"{tid}: {field_name} must be a list of strings, got "
            f"{type(value).__name__} ({value!r})"
        )
    non_strings = [v for v in value if not isinstance(v, str)]
    if non_strings:
        raise ConsumerAuthorityError(
            f"{tid}: {field_name} must contain only strings, found non-string "
            f"entries: {non_strings!r}"
        )
    return value


def validate_consumer_vocabulary(row: dict[str, Any], *, path: Path | None = None) -> None:
    """Validate a single truth row's allowed_consumers/forbidden_consumers.

    Raises ConsumerAuthorityError on any violation:
      - allowed_consumers/forbidden_consumers not present as a list of
        strings (Fable adjudication, MINOR-2);
      - any token (allowed or forbidden) not in the canonical matrix
        vocabulary — retired aliases get a specific "use X instead" (or
        "retired outright") message rather than a generic orphan message;
      - allowed_consumers containing a money-path token, or
        allowed_consumers/forbidden_consumers overlapping on any token
        (Fable adjudication, MAJOR-1 — the matrix's own disjoint-lists
        design principle);
      - forbidden_consumers missing any of the four universal money-path
        tokens (CPI-H1 ruling 5);
      - a status with no matching consumer_matrix.yml artifact_classes
        entry (Fable adjudication, MINOR-1 — never a silent no-op);
      - allowed_consumers containing any token outside the row's status
        class's matrix allowed_consumers list (CPI-H1 ruling 8, promoted
        from WARN-tier advisory to HARD by CPI-H1.1, Sol adjudication
        2026-08-21/22). This is a general subset check — it supersedes and
        subsumes the earlier neuralweb_context-only class-conditional check
        (CPI-H1 ruling 6 / A2 F6): neuralweb_context on promoted_null/
        candidate/retired/superseded fails the same way any other
        out-of-class token would, because none of those classes list it in
        their matrix allowed_consumers.

    Does NOT check required-field presence, enum validity, falsifiers, or
    evidence_refs — those remain engine/cycle_pattern/truths.py's
    validate_truth() responsibility. This function is consumer-vocabulary
    ONLY, so it can be reused standalone by the CI-wired registry scan
    without pulling in the full truth schema.
    """
    tid = row.get("truth_id", "?")
    status = row.get("status", "?")
    allowed = _require_string_list(row.get("allowed_consumers"), "allowed_consumers", tid)
    forbidden = _require_string_list(row.get("forbidden_consumers"), "forbidden_consumers", tid)
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

    # Money-path leak on the allow side (MAJOR-1 / Fable adjudication): the
    # matrix's surfaces:money_path group must never be grantable — only
    # forbid-able. This is a stricter, allow-side mirror of the universal
    # forbid check below.
    leaked = set(allowed) & money_path_tokens(path)
    if leaked:
        raise ConsumerAuthorityError(
            f"{tid}: allowed_consumers grants money-path token(s) "
            f"{sorted(leaked)} — surfaces:money_path tokens in "
            f"config/cycle_pattern/consumer_matrix.yml may never appear in "
            f"allowed_consumers, only forbidden_consumers"
        )

    # allowed_consumers and forbidden_consumers must be disjoint per row —
    # the matrix's own stated design principle ("Allowed/forbidden lists are
    # DISJOINT"), now machine-enforced (MAJOR-1 / Fable adjudication).
    overlap = set(allowed) & set(forbidden)
    if overlap:
        raise ConsumerAuthorityError(
            f"{tid}: allowed_consumers and forbidden_consumers overlap on "
            f"{sorted(overlap)} — a token cannot be simultaneously granted "
            f"and barred on the same row"
        )

    missing_universal = UNIVERSAL_MONEY_PATH_FORBIDS - set(forbidden)
    if missing_universal:
        raise ConsumerAuthorityError(
            f"{tid}: forbidden_consumers missing universal money-path token(s) "
            f"required on every row (CPI-H1 ruling 5): {sorted(missing_universal)}"
        )

    # Least-privilege class-subset invariant (CPI-H1 ruling 8): a row's
    # allowed_consumers must be a SUBSET of its status class's matrix
    # allowed_consumers. Promoted from a WARN-tier advisory
    # (advisory_class_subset_violations(), retired by this heal) to a HARD
    # check by CPI-H1.1 (Sol adjudication, 2026-08-21/22) — see module
    # docstring. class_allowed_consumers() raises ConsumerAuthorityError
    # itself if `status` has no matching matrix class (MINOR-1), so an
    # unmapped/typo'd status still fails loudly rather than vacuously here.
    # This subsumes the former neuralweb_context-only class-conditional
    # check: any class that forbids/omits a token from its own
    # allowed_consumers now rejects a row-level grant of that token,
    # uniformly, not just for neuralweb_context.
    #
    # NIT-2 (2026-08-22): this call is now the SOLE reachable path from
    # validate_consumer_vocabulary() into _require_class_entry()'s unknown-
    # status guard (MINOR-1) — nothing else in this function calls
    # class_allowed_consumers()/class_forbidden_consumers(). A future
    # refactor that removes or short-circuits this subset check must keep an
    # equivalent call so an unmapped/typo'd status still raises rather than
    # silently passing; TestUnknownStatusRaises in
    # tests/test_cpi_h1_consumer_authority.py pins this behavior.
    class_allowed = class_allowed_consumers(status, path)
    extra = set(allowed) - class_allowed
    if extra:
        raise ConsumerAuthorityError(
            f"{tid}: status={status!r} row's allowed_consumers grants "
            f"{sorted(extra)} outside the {status!r} class's matrix "
            f"allowed_consumers {sorted(class_allowed)} (CPI-H1 ruling 8, "
            f"promoted WARN->HARD by CPI-H1.1, Sol adjudication "
            f"2026-08-21/22) — either the row is over-privileged for its "
            f"status, or the class envelope in "
            f"config/cycle_pattern/consumer_matrix.yml needs a reviewed "
            f"amendment before this token can be granted"
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
