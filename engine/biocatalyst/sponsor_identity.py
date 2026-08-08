"""Reviewed sponsor -> ticker candidate map for BioCatalyst post-selection context.

This module reads one bounded, curated, PR-reviewed lookup. It is deliberately
NOT a point-in-time identity service and NOT an inferred join:

* a row written by a model is a CANDIDATE, and a candidate never resolves;
* only a row a named human admitted in review (``reviewed_admitted``) resolves;
* everything else returns unavailable WITH A REASON, never a guess;
* ambiguity (several issuers, a subsidiary, a JV, a rename) is queued for a
  reviewer with its competing candidates recorded, never silently picked; and
* every link carries an effective interval, so a later rename or ticker reuse
  cannot rewrite what the map said earlier.

It collects nothing, connects to nothing, persists nothing, exposes no route,
and starts no process. It exists so BioCatalyst can explain a name AFTER
Prophet selects it; it may never originate, rank, reorder, size, or gate a
candidate, and it is wired to no scoring path.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as _dt
import json
from pathlib import Path
from typing import Any, Mapping, Sequence
import unicodedata

import yaml

from engine.sector_intelligence.contracts import (
    ContractRegistry,
    ContractValidationError,
    ValidationIssue,
)


SPONSOR_TICKER_MAP_CONTRACT_ID = "biocatalyst_sponsor_ticker_map.v1"
SPONSOR_TICKER_MAP_PATH = "config/biocatalyst_sponsor_ticker_map.yml"
BASKET_MEMBERSHIP_PATH = "data/baskets/membership.json"

# The tradeable healthcare universe this map is scoped to. Widening it is a
# reviewed act: it changes which tickers a row is even allowed to name.
HEALTHCARE_BASKETS = ("big_pharma", "managed_care", "obesity_glp1", "us_sector_health")

REVIEW_STATES = (
    "candidate_unreviewed",
    "reviewed_admitted",
    "reviewed_rejected",
    "ambiguous_queued",
)
# The whole point of the lane: one review state resolves, three do not.
RESOLVABLE_REVIEW_STATES = frozenset({"reviewed_admitted"})
CANDIDATE_ONLY_STATE = "candidate_map_no_admitted_rows"

UNAVAILABLE_SPONSOR_UNKNOWN = "sponsor_not_in_reviewed_map"
UNAVAILABLE_OUTSIDE_INTERVAL = "outside_effective_interval"
UNAVAILABLE_AWAITING_REVIEW = "row_awaiting_human_review"
UNAVAILABLE_REJECTED = "row_rejected_in_review"
UNAVAILABLE_AMBIGUOUS = "row_ambiguous_queued_for_review"
RESOLVED_REASON = "row_admitted_in_human_review"

_UNAVAILABLE_BY_REVIEW_STATE = {
    "candidate_unreviewed": UNAVAILABLE_AWAITING_REVIEW,
    "reviewed_rejected": UNAVAILABLE_REJECTED,
    "ambiguous_queued": UNAVAILABLE_AMBIGUOUS,
}

# A read of a curated config file, not a document reader for arbitrary input.
MAP_MAX_BYTES = 256 * 1024
MEMBERSHIP_MAX_BYTES = 4 * 1024 * 1024


class SponsorIdentityError(ValueError):
    """Raised when the map cannot be read at all."""


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _repo_root(repo_root: Path | str | None) -> Path:
    return Path(repo_root) if repo_root is not None else _default_repo_root()


def _read_bounded_text(path: Path, limit: int) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SponsorIdentityError(f"cannot read {path.name}: {exc}") from exc
    if len(raw) > limit:
        raise SponsorIdentityError(f"{path.name} exceeds {limit} bytes")
    try:
        return raw.decode("utf-8")
    except UnicodeError as exc:
        raise SponsorIdentityError(f"{path.name} must be UTF-8: {exc}") from exc


def normalized_sponsor_key(sponsor_name: str) -> str:
    """Return a deterministic collision key for a sponsor string.

    This is used ONLY to detect two rows that differ by case, width, or
    whitespace and would confuse a reviewer. It is never a lookup path: no
    caller resolves through it, and no token is dropped or stemmed.
    """

    folded = unicodedata.normalize("NFKC", sponsor_name).casefold()
    return " ".join(folded.split())


def _parse_date(value: object) -> _dt.date | None:
    if not isinstance(value, str):
        return None
    try:
        return _dt.date.fromisoformat(value)
    except ValueError:
        return None


def healthcare_universe_tickers(repo_root: Path | str | None = None) -> tuple[str, ...]:
    """Derive the declared healthcare ticker universe from the basket file.

    The list is READ at validation time, never hardcoded here, so a basket
    edit cannot leave the map silently claiming a ticker that left the
    universe.
    """

    root = _repo_root(repo_root)
    text = _read_bounded_text(root / BASKET_MEMBERSHIP_PATH, MEMBERSHIP_MAX_BYTES)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SponsorIdentityError(f"basket membership is not JSON: {exc}") from exc
    baskets = payload.get("baskets") if isinstance(payload, Mapping) else None
    if not isinstance(baskets, Mapping):
        raise SponsorIdentityError("basket membership must declare a baskets object")
    tickers: set[str] = set()
    for basket in HEALTHCARE_BASKETS:
        entry = baskets.get(basket)
        if not isinstance(entry, Mapping):
            raise SponsorIdentityError(f"basket {basket!r} is missing from membership")
        members = entry.get("members")
        if not isinstance(members, Sequence) or isinstance(members, (str, bytes)):
            raise SponsorIdentityError(f"basket {basket!r} must declare a member list")
        for member in members:
            if not isinstance(member, Mapping):
                raise SponsorIdentityError(f"basket {basket!r} member must be an object")
            ticker = member.get("ticker")
            if not isinstance(ticker, str) or not ticker:
                raise SponsorIdentityError(f"basket {basket!r} member must declare a ticker")
            tickers.add(ticker)
    return tuple(sorted(tickers))


def _row_shape_issues(index: int, row: Mapping[str, Any]) -> list[ValidationIssue]:
    """Return review-grammar failures for one row."""

    base = f"$.rows[{index}]"
    issues: list[ValidationIssue] = []
    review_state = row.get("review_state")
    ticker = row.get("ticker")
    review = row.get("review") if isinstance(row.get("review"), Mapping) else {}
    reviewed = any(review.get(key) is not None for key in ("reviewed_by", "reviewed_at", "review_reference"))
    fully_reviewed = all(
        review.get(key) is not None for key in ("reviewed_by", "reviewed_at", "review_reference")
    )
    has_ambiguity_reason = "ambiguity_reason" in row

    if review_state == "candidate_unreviewed":
        if ticker is None:
            issues.append(_issue(f"{base}.ticker", "sponsor_map.candidate_ticker", "a candidate row must name the ticker it proposes"))
        if reviewed:
            issues.append(_issue(f"{base}.review", "sponsor_map.unreviewed_review_block", "an unreviewed row must leave every review field null"))
        if has_ambiguity_reason:
            issues.append(_issue(f"{base}.ambiguity_reason", "sponsor_map.ambiguity_reason_scope", "ambiguity_reason belongs only to an ambiguous_queued row"))
    elif review_state == "reviewed_admitted":
        if ticker is None:
            issues.append(_issue(f"{base}.ticker", "sponsor_map.admitted_ticker", "an admitted row must name exactly one ticker"))
        if not fully_reviewed:
            issues.append(_issue(f"{base}.review", "sponsor_map.admitted_review_block", "an admitted row must record reviewer, review time, and review reference"))
        if has_ambiguity_reason:
            issues.append(_issue(f"{base}.ambiguity_reason", "sponsor_map.ambiguity_reason_scope", "ambiguity_reason belongs only to an ambiguous_queued row"))
    elif review_state == "reviewed_rejected":
        if ticker is not None:
            issues.append(_issue(f"{base}.ticker", "sponsor_map.rejected_ticker", "a rejected row must not keep a resolved ticker"))
        if not fully_reviewed:
            issues.append(_issue(f"{base}.review", "sponsor_map.rejected_review_block", "a rejected row must record reviewer, review time, and review reference"))
        if has_ambiguity_reason:
            issues.append(_issue(f"{base}.ambiguity_reason", "sponsor_map.ambiguity_reason_scope", "ambiguity_reason belongs only to an ambiguous_queued row"))
    elif review_state == "ambiguous_queued":
        if ticker is not None:
            issues.append(_issue(f"{base}.ticker", "sponsor_map.ambiguous_ticker", "an ambiguous row must not resolve a ticker"))
        if not has_ambiguity_reason:
            issues.append(_issue(f"{base}.ambiguity_reason", "sponsor_map.ambiguity_reason_required", "an ambiguous row must record why it is ambiguous"))
        if reviewed:
            issues.append(_issue(f"{base}.review", "sponsor_map.queued_review_block", "a queued row must leave every review field null"))
        if row.get("confidence_class") != "unresolved":
            issues.append(_issue(f"{base}.confidence_class", "sponsor_map.ambiguous_confidence", "an ambiguous row must carry confidence_class unresolved"))

    valid_from = _parse_date(row.get("valid_from"))
    valid_to = _parse_date(row.get("valid_to")) if row.get("valid_to") is not None else None
    if valid_from is None:
        issues.append(_issue(f"{base}.valid_from", "sponsor_map.valid_from", "valid_from must be an ISO calendar date"))
    if row.get("valid_to") is not None and valid_to is None:
        issues.append(_issue(f"{base}.valid_to", "sponsor_map.valid_to", "valid_to must be an ISO calendar date or null"))
    if valid_from is not None and valid_to is not None and valid_to <= valid_from:
        issues.append(_issue(f"{base}.valid_to", "sponsor_map.interval_order", "valid_to must be strictly after valid_from"))
    return issues


def _interval_issues(rows: Sequence[Mapping[str, Any]]) -> list[ValidationIssue]:
    """Reject overlapping effective intervals for one sponsor string."""

    issues: list[ValidationIssue] = []
    by_sponsor: dict[str, list[tuple[int, _dt.date, _dt.date | None]]] = {}
    for index, row in enumerate(rows):
        sponsor = row.get("sponsor_name")
        valid_from = _parse_date(row.get("valid_from"))
        if not isinstance(sponsor, str) or valid_from is None:
            continue
        valid_to = _parse_date(row.get("valid_to")) if row.get("valid_to") is not None else None
        by_sponsor.setdefault(sponsor, []).append((index, valid_from, valid_to))
    for sponsor, spans in sorted(by_sponsor.items()):
        ordered = sorted(spans, key=lambda item: (item[1], item[0]))
        for (_, first_from, first_to), (second_index, second_from, _) in zip(ordered, ordered[1:]):
            if first_to is None or second_from < first_to:
                issues.append(
                    _issue(
                        f"$.rows[{second_index}].valid_from",
                        "sponsor_map.interval_overlap",
                        f"effective intervals for sponsor {sponsor!r} must not overlap",
                    )
                )
    return issues


def sponsor_ticker_map_semantic_issues(
    document: Any, *, repo_root: Path | str | None = None
) -> list[ValidationIssue]:
    """Return deterministic semantic failures for a sponsor -> ticker map."""

    if not isinstance(document, Mapping):
        return [_issue("$", "sponsor_map.document", "sponsor ticker map must be a JSON object")]
    issues: list[ValidationIssue] = []

    universe = healthcare_universe_tickers(repo_root)
    universe_set = set(universe)
    declared = document.get("universe")
    if isinstance(declared, Mapping):
        baskets = declared.get("baskets")
        if list(baskets or []) != sorted(HEALTHCARE_BASKETS):
            issues.append(_issue("$.universe.baskets", "sponsor_map.universe_baskets", "universe.baskets must list the declared healthcare baskets in sorted order"))
        if declared.get("distinct_ticker_count") != len(universe):
            issues.append(_issue("$.universe.distinct_ticker_count", "sponsor_map.universe_count", f"distinct_ticker_count must equal the {len(universe)} tickers derived from the basket file"))

    rows = document.get("rows")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return issues + [_issue("$.rows", "sponsor_map.rows", "rows must be a list")]
    if any(not isinstance(row, Mapping) for row in rows):
        return issues + [_issue("$.rows", "sponsor_map.row_object", "every row must be an object")]

    state = document.get("state")
    keys = [(row.get("sponsor_name"), row.get("valid_from")) for row in rows]
    if len(set(keys)) != len(keys):
        issues.append(_issue("$.rows", "sponsor_map.row_unique", "each row must be unique on (sponsor_name, valid_from)"))
    if keys != sorted(keys, key=lambda item: (str(item[0]), str(item[1]))):
        issues.append(_issue("$.rows", "sponsor_map.row_order", "rows must be sorted by (sponsor_name, valid_from)"))

    effective_at = _parse_date(str(document.get("effective_at", ""))[:10])
    collisions: dict[str, dict[str, set[str]]] = {}
    claimed: set[str] = set()
    for index, row in enumerate(rows):
        base = f"$.rows[{index}]"
        issues.extend(_row_shape_issues(index, row))

        ticker = row.get("ticker")
        if isinstance(ticker, str):
            claimed.add(ticker)
            if ticker not in universe_set:
                issues.append(_issue(f"{base}.ticker", "sponsor_map.ticker_universe", f"ticker {ticker!r} is outside the declared healthcare universe"))
        for candidate in row.get("candidate_tickers") or []:
            if isinstance(candidate, str):
                if candidate not in universe_set:
                    issues.append(_issue(f"{base}.candidate_tickers", "sponsor_map.candidate_universe", f"candidate ticker {candidate!r} is outside the declared healthcare universe"))

        provenance = row.get("provenance")
        kind = provenance.get("kind") if isinstance(provenance, Mapping) else None
        if row.get("review_state") in {"candidate_unreviewed", "ambiguous_queued"} and kind != "model_suggested_candidate":
            issues.append(_issue(f"{base}.provenance.kind", "sponsor_map.candidate_provenance", "an unreviewed or queued row must declare model_suggested_candidate provenance"))
        valid_from = _parse_date(row.get("valid_from"))
        if kind == "model_suggested_candidate" and valid_from is not None and effective_at is not None and valid_from < effective_at:
            issues.append(_issue(f"{base}.valid_from", "sponsor_map.no_backdating", "a model-suggested row may not back-date its effective interval"))

        if state == CANDIDATE_ONLY_STATE and row.get("review_state") == "reviewed_admitted":
            issues.append(_issue(f"{base}.review_state", "sponsor_map.self_promotion", "a candidate-only map may not contain an admitted row"))

        sponsor = row.get("sponsor_name")
        if isinstance(sponsor, str) and isinstance(ticker, str):
            collisions.setdefault(normalized_sponsor_key(sponsor), {}).setdefault(sponsor, set()).add(ticker)

    # Two rows for the SAME exact string across non-overlapping intervals are a
    # rename or ticker reuse and are lawful. Two rows that differ only by case,
    # width, or whitespace and claim different tickers are a near-duplicate a
    # reviewer must reconcile before either can be admitted.
    for key, by_exact_name in sorted(collisions.items()):
        tickers = {ticker for names in by_exact_name.values() for ticker in names}
        if len(by_exact_name) > 1 and len(tickers) > 1:
            issues.append(_issue("$.rows", "sponsor_map.normalized_collision", f"sponsor key {key!r} is written {len(by_exact_name)} ways claiming {sorted(tickers)}"))

    unmapped = document.get("unmapped_universe_tickers")
    if isinstance(unmapped, Sequence) and not isinstance(unmapped, (str, bytes)):
        expected = sorted(universe_set - claimed)
        if list(unmapped) != expected:
            issues.append(_issue("$.unmapped_universe_tickers", "sponsor_map.unmapped_complement", "unmapped_universe_tickers must be exactly the sorted universe tickers no row claims"))

    issues.extend(_interval_issues(rows))
    return sorted(set(issues))


def validate_sponsor_ticker_map(document: Any, *, repo_root: Path | str | None = None) -> None:
    """Fail closed unless schema and review-grammar controls both hold."""

    root = _repo_root(repo_root)
    registry = ContractRegistry(root)
    schema_issues = list(registry.issues(SPONSOR_TICKER_MAP_CONTRACT_ID, document))
    semantic_issues = (
        sponsor_ticker_map_semantic_issues(document, repo_root=root)
        if isinstance(document, Mapping)
        else [_issue("$", "sponsor_map.document", "sponsor ticker map must be a JSON object")]
    )
    issues = tuple(sorted(set(schema_issues + semantic_issues)))
    if issues:
        raise ContractValidationError(SPONSOR_TICKER_MAP_CONTRACT_ID, issues)


def load_sponsor_ticker_map(repo_root: Path | str | None = None) -> dict[str, Any]:
    """Read and validate the committed map. Never returns an unvalidated document."""

    root = _repo_root(repo_root)
    text = _read_bounded_text(root / SPONSOR_TICKER_MAP_PATH, MAP_MAX_BYTES)
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SponsorIdentityError(f"sponsor ticker map is not YAML: {exc}") from exc
    if not isinstance(document, dict):
        raise SponsorIdentityError("sponsor ticker map must be a mapping")
    validate_sponsor_ticker_map(document, repo_root=root)
    return document


@dataclass(frozen=True)
class SponsorResolution:
    """One fail-closed answer: an admitted ticker, or unavailable with a reason."""

    status: str
    reason: str
    sponsor_name: str
    as_of: str
    ticker: str | None = None
    review_state: str | None = None
    candidate_tickers: tuple[str, ...] = ()
    ambiguity_reason: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None

    @property
    def available(self) -> bool:
        return self.status == "resolved"


def _unavailable(sponsor_name: str, as_of: str, reason: str, **extra: Any) -> SponsorResolution:
    return SponsorResolution(status="unavailable", reason=reason, sponsor_name=sponsor_name, as_of=as_of, **extra)


def resolve_sponsor(
    sponsor_name: str,
    *,
    as_of: str,
    document: Mapping[str, Any] | None = None,
    repo_root: Path | str | None = None,
) -> SponsorResolution:
    """Resolve one exact ClinicalTrials.gov lead-sponsor string to a ticker.

    Only a ``reviewed_admitted`` row whose effective interval covers ``as_of``
    resolves. Every other case returns ``status="unavailable"`` with the reason
    a caller can print. There is no fallback, no nearest match, and no guess.
    """

    root = _repo_root(repo_root)
    payload = load_sponsor_ticker_map(root) if document is None else document
    as_of_date = _parse_date(as_of)
    if as_of_date is None:
        raise SponsorIdentityError("as_of must be an ISO calendar date")
    if not isinstance(sponsor_name, str) or not sponsor_name:
        raise SponsorIdentityError("sponsor_name must be a non-empty string")

    matches = [row for row in payload.get("rows", []) if row.get("sponsor_name") == sponsor_name]
    if not matches:
        return _unavailable(sponsor_name, as_of, UNAVAILABLE_SPONSOR_UNKNOWN)

    covering: list[Mapping[str, Any]] = []
    for row in matches:
        valid_from = _parse_date(row.get("valid_from"))
        valid_to = _parse_date(row.get("valid_to")) if row.get("valid_to") is not None else None
        if valid_from is None or as_of_date < valid_from:
            continue
        if valid_to is not None and as_of_date >= valid_to:
            continue
        covering.append(row)
    if not covering:
        return _unavailable(sponsor_name, as_of, UNAVAILABLE_OUTSIDE_INTERVAL)
    if len(covering) > 1:
        return _unavailable(
            sponsor_name,
            as_of,
            UNAVAILABLE_AMBIGUOUS,
            candidate_tickers=tuple(sorted(str(row["ticker"]) for row in covering if row.get("ticker"))),
            ambiguity_reason="multiple_matching_issuers",
        )

    row = covering[0]
    review_state = row.get("review_state")
    candidates = tuple(row.get("candidate_tickers") or ())
    if review_state not in RESOLVABLE_REVIEW_STATES:
        return _unavailable(
            sponsor_name,
            as_of,
            _UNAVAILABLE_BY_REVIEW_STATE.get(str(review_state), UNAVAILABLE_AWAITING_REVIEW),
            review_state=review_state if isinstance(review_state, str) else None,
            candidate_tickers=candidates,
            ambiguity_reason=row.get("ambiguity_reason"),
            valid_from=row.get("valid_from"),
            valid_to=row.get("valid_to"),
        )
    return SponsorResolution(
        status="resolved",
        reason=RESOLVED_REASON,
        sponsor_name=sponsor_name,
        as_of=as_of,
        ticker=row.get("ticker"),
        review_state="reviewed_admitted",
        candidate_tickers=candidates,
        valid_from=row.get("valid_from"),
        valid_to=row.get("valid_to"),
    )


def review_queue(document: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Return the rows a human still has to decide, in file order."""

    return tuple(
        row
        for row in document.get("rows", [])
        if row.get("review_state") in {"candidate_unreviewed", "ambiguous_queued"}
    )
