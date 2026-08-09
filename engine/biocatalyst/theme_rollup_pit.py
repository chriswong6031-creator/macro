"""Point-in-time theme rollup adapter for the BioCatalyst evidence plane.

WHAT THIS IS
    A pure, hermetic translation boundary.  It converts bounded
    ``trial_snapshot.v1`` reads plus a caller-supplied, reviewed membership
    binding into rows shaped exactly like the columns ``engine/theme_clinical``
    already consumes (``collectors/clinicaltrials_themes.STORE_COLS``), so the
    live theme layer can later be fed from a point-in-time, correction-aware
    plane by configuration rather than by a rewrite.

WHAT THIS IS NOT
    It originates no probability, ranking, score, size or escalation; it makes
    no issuer, ticker, sponsor-identity or security join; it opens no network
    connection, starts no process, activates no source and publishes nothing.
    Every emitted document is display/context tier and says so in its own
    authority block.  ``DNR:KILL-PHASE3-START-WEIGHT`` stands: phase counts here
    are context, never a scored catalyst leg.

HONEST COVERAGE
    BioCatalyst's live reach is a bounded fixed cohort against a registry of
    roughly half a million studies, and its transport is dark.  This adapter
    therefore does NOT replace the legacy theme store's numbers.  It computes,
    from real counts only, what fraction of each theme's rollup is backed by the
    point-in-time plane versus the legacy store, and publishes that fraction
    even — especially — when it is zero.  Fractions are floored, never rounded
    up, so a near-empty plane can never display as coverage it does not have.

MEMBERSHIP AUTHORITY
    An NCT identifier carries no theme by itself.  Theme membership arrives as
    an explicit binding whose ``source_record_ref`` must equal the snapshot's
    own ``source_record_ref``; a binding that does not match its evidence is
    dropped and counted under ``binding_evidence_mismatch``.  Modality-to-theme
    resolution reads only the reviewed ``config/clinical_modalities.yml``.
    Nothing here infers a mapping.

    That match is deliberately strict, and the consequence is deliberate too:
    when the registry record changes, its content hash changes, the existing
    binding stops matching, and the trial leaves the rollup until the binding is
    re-reviewed against the new record.  Membership is a reviewed admission, so
    it fails closed on unreviewed content rather than carrying a stale review
    forward silently.  The exclusion counter makes each such drop visible.

POINT-IN-TIME LAW
    A snapshot contributes to an ``as_of`` rollup only when its
    ``knowledge_cutoff`` is at or before ``as_of``.  When several knowable
    versions of the same trial exist, the latest knowable version wins and the
    superseded ones are counted, so a correction issued after ``as_of`` can
    never leak backwards into the rollup.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from engine.biocatalyst.trials import validate_trial_snapshot
from engine.sector_intelligence.contracts import (
    ContractError,
    ContractRegistry,
    ContractValidationError,
    ValidationIssue,
    canonical_json_sha256,
)


THEME_ROLLUP_PIT_CONTRACT_ID = "biocatalyst_theme_rollup_pit.v1"
THEME_ROLLUP_PIT_HASH_SCOPE = "canonical_payload_excluding_rollup_payload_sha256"
THEME_ROLLUP_PIT_ROW_SHAPE = "clinical_modality_monthly_store_columns.v1"
MODALITY_CONFIG_REF = "config/clinical_modalities.yml"
BINDING_REVIEW_STATE = "reviewed_config_query_membership"
PIT_PROVENANCE_PLANE = "biocatalyst_pit"
LEGACY_PROVENANCE_PLANE = "legacy_theme_store"

# The bounded product projection registers no studyFirstPostDate fact, so the
# registration date can only arrive with the reviewed membership binding that
# also carries its source-record evidence.  This module never derives one.
PIT_FIRST_POST_DATE_SOURCE = "reviewed_membership_binding"

_BINDING_KEYS = frozenset(
    {
        "nct_id",
        "modality_id",
        "study_first_post_date",
        "source_record_ref",
        "binding_review_state",
    }
)

_AUTHORITY: dict[str, Any] = {
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "is_context_only": True,
    "allowed_uses": ["context", "display", "explain"],
    "forbidden_uses": [
        "execute_trade",
        "gate_decision",
        "originate_signal",
        "raise_authority",
        "rank_security",
        "select_security",
        "size_position",
    ],
    "fused_obs_z_fence": "SEPARATE_DISPLAY_LEG — never fold into fused_obs_z",
}

_DISCLOSURE = (
    "Point-in-time theme rollup projected from BioCatalyst trial reads knowable "
    "at as_of. Display/context tier only — not a score, not a ranking, not a "
    "buy or sell signal. pit_backed_fraction is computed from real counts and "
    "floored, never rounded up: a zero means this theme has no point-in-time "
    "backing today and its numbers still come from the legacy theme store. "
    "Theme membership comes only from the reviewed modality config bound to its "
    "own source-record evidence; no issuer, ticker or security is joined here."
)
_DISCLOSURE_ZH = (
    "按 as_of 时点可知的 BioCatalyst 试验读数汇总的主题口径。仅供展示与背景参考——"
    "不是评分、不是排名、也不是买卖建议。pit_backed_fraction 由真实计数得出并向下取整，"
    "绝不向上取整：为零即表示该主题目前没有时点口径支撑，其数字仍来自旧主题库。"
    "主题归属仅来自经审阅的模态配置，并须与其来源记录凭证一致；此处不做任何发行人、"
    "股票代码或证券的关联。"
)

_PROVENANCE_VALUES = ("biocatalyst_pit", "legacy_theme_store", "mixed", "none")

_EXCLUSION_KEYS = (
    "binding_evidence_mismatch",
    "non_industry_sponsor",
    "not_knowable_at_as_of",
    "superseded_by_later_knowable_version",
    "unbound_nct",
    "unmapped_modality",
)
_ROW_NOTE_KEYS = ("rows_without_observed_enrollment", "rows_without_observed_phases")


class ThemeRollupPitError(ContractError):
    """A bounded, fail-closed point-in-time theme rollup construction failure."""


def _issue(path: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(path, code, message)


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _repo_root(repo_root: Path | str | None) -> Path:
    return Path(repo_root).resolve() if repo_root is not None else _default_repo_root()


# ---------------------------------------------------------------------------
# Reviewed membership vocabulary
# ---------------------------------------------------------------------------

def load_modality_theme_map(
    repo_root: Path | str | None = None,
) -> tuple[dict[str, str], str]:
    """Return the reviewed ``modality_id -> theme_id`` map and its vocabulary stamp.

    The map is read only from ``config/clinical_modalities.yml``.  Nothing is
    inferred, extended, or filled in from surrounding data.
    """

    path = _repo_root(repo_root) / MODALITY_CONFIG_REF
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ThemeRollupPitError(f"modality config unavailable: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ThemeRollupPitError("modality config must be a mapping")
    rows = payload.get("modalities")
    if not isinstance(rows, list) or not rows:
        raise ThemeRollupPitError("modality config must declare a non-empty modalities list")
    mapping: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ThemeRollupPitError("each modality row must be a mapping")
        modality_id = row.get("modality_id")
        theme_id = row.get("theme_id")
        if not isinstance(modality_id, str) or not isinstance(theme_id, str):
            raise ThemeRollupPitError("modality rows must declare modality_id and theme_id")
        if modality_id in mapping:
            raise ThemeRollupPitError(f"duplicate modality_id in config: {modality_id}")
        mapping[modality_id] = theme_id
    vocabulary_version = payload.get("vocabulary_version")
    if not isinstance(vocabulary_version, str) or not vocabulary_version:
        raise ThemeRollupPitError("modality config must declare a vocabulary_version")
    return mapping, vocabulary_version


# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------

def floor_fraction(numerator: int, denominator: int) -> float:
    """Floor ``numerator/denominator`` to six decimals — never round up.

    Rounding a sliver of coverage up to a printable number is exactly the way a
    dark plane comes to look like a covered one, so the truncation direction is
    part of the contract rather than a formatting detail.
    """

    if denominator <= 0:
        return 0.0
    if numerator <= 0:
        return 0.0
    if numerator >= denominator:
        return 1.0
    return math.floor((numerator / denominator) * 1_000_000) / 1_000_000


def provenance_label(n_pit: int, n_legacy: int) -> str:
    """Name the plane that produced a rollup value."""

    if n_pit > 0 and n_legacy > 0:
        return "mixed"
    if n_pit > 0:
        return PIT_PROVENANCE_PLANE
    if n_legacy > 0:
        return LEGACY_PROVENANCE_PLANE
    return "none"


def _parse_instant(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ThemeRollupPitError(f"{label} must be an ISO-8601 timestamp")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ThemeRollupPitError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _instant_or_none(value: object) -> datetime | None:
    try:
        return _parse_instant(value, label="instant")
    except ThemeRollupPitError:
        return None


def _parse_day(value: object, *, label: str) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ThemeRollupPitError(f"{label} must be a YYYY-MM-DD date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ThemeRollupPitError(f"{label} must be a YYYY-MM-DD date") from exc


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


# ---------------------------------------------------------------------------
# Binding normalization
# ---------------------------------------------------------------------------

def _normalized_bindings(
    membership_bindings: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    """Return reviewed bindings grouped by NCT, rejecting anything ambiguous."""

    if type(membership_bindings) not in (list, tuple):
        raise ThemeRollupPitError("membership_bindings must be a sequence")
    grouped: dict[str, list[dict[str, str]]] = {}
    seen: set[tuple[str, str]] = set()
    for binding in membership_bindings:
        if not isinstance(binding, Mapping) or set(binding) != _BINDING_KEYS:
            raise ThemeRollupPitError(
                "each membership binding must declare exactly "
                "nct_id, modality_id, study_first_post_date, source_record_ref, "
                "binding_review_state"
            )
        if binding.get("binding_review_state") != BINDING_REVIEW_STATE:
            raise ThemeRollupPitError(
                f"membership binding review state must be {BINDING_REVIEW_STATE}"
            )
        nct_id = binding.get("nct_id")
        modality_id = binding.get("modality_id")
        source_record_ref = binding.get("source_record_ref")
        if (
            not isinstance(nct_id, str)
            or not isinstance(modality_id, str)
            or not isinstance(source_record_ref, str)
        ):
            raise ThemeRollupPitError("membership binding fields must be strings")
        _parse_day(
            binding.get("study_first_post_date"), label="binding.study_first_post_date"
        )
        key = (nct_id, modality_id)
        if key in seen:
            raise ThemeRollupPitError(
                f"duplicate membership binding for {nct_id}/{modality_id}"
            )
        seen.add(key)
        grouped.setdefault(nct_id, []).append(
            {
                "nct_id": nct_id,
                "modality_id": modality_id,
                "study_first_post_date": str(binding["study_first_post_date"]),
                "source_record_ref": source_record_ref,
            }
        )
    for bindings in grouped.values():
        bindings.sort(key=lambda item: item["modality_id"])
    return grouped


# ---------------------------------------------------------------------------
# Row projection
# ---------------------------------------------------------------------------

def _observed(fact: object) -> Any:
    if isinstance(fact, Mapping) and fact.get("state") == "observed":
        return fact.get("value")
    return None


def _sponsor_class(snapshot: Mapping[str, Any]) -> str | None:
    sponsor = _observed((snapshot.get("facts") or {}).get("sponsor"))
    if isinstance(sponsor, Mapping):
        sponsor_class = sponsor.get("class")
        if isinstance(sponsor_class, str):
            return sponsor_class
    return None


def _phase_columns(snapshot: Mapping[str, Any]) -> tuple[str, bool, bool, bool, bool]:
    phases = _observed((snapshot.get("facts") or {}).get("phases"))
    if not isinstance(phases, list):
        return "", False, False, False, False
    values = [value for value in phases if isinstance(value, str)]
    return (
        "|".join(values),
        "PHASE1" in values,
        "PHASE2" in values,
        "PHASE3" in values,
        True,
    )


def _enrollment_target(snapshot: Mapping[str, Any]) -> tuple[int | None, bool]:
    enrollment = _observed((snapshot.get("facts") or {}).get("enrollment"))
    if isinstance(enrollment, Mapping):
        count = enrollment.get("count")
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            return count, True
    return None, False


def _row_sort_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (str(row["modality_id"]), str(row["nct_id"]))


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_theme_rollup_pit(
    snapshots: Sequence[Mapping[str, Any]],
    *,
    membership_bindings: Sequence[Mapping[str, Any]],
    as_of: str,
    legacy_modality_counts: Mapping[str, int],
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Project one point-in-time theme rollup from bounded trial reads.

    ``legacy_modality_counts`` are the real per-modality study counts the legacy
    store contributes today — the modality is the level at which that store
    actually counts, so the coverage denominator is observed rather than
    apportioned.  Every modality in the reviewed config must be present: a
    caller that cannot count its own store has no coverage claim to make, and a
    missing denominator would silently print as full point-in-time coverage.
    """

    root = _repo_root(repo_root)
    as_of_instant = _parse_instant(as_of, label="as_of")
    modality_theme, vocabulary_version = load_modality_theme_map(root)
    grouped_bindings = _normalized_bindings(membership_bindings)

    if type(snapshots) not in (list, tuple):
        raise ThemeRollupPitError("snapshots must be a sequence")
    if not isinstance(legacy_modality_counts, Mapping):
        raise ThemeRollupPitError("legacy_modality_counts must be a mapping")
    legacy_counts: dict[str, int] = {}
    for modality_id, count in legacy_modality_counts.items():
        if not isinstance(modality_id, str) or not _is_count(count):
            raise ThemeRollupPitError(
                "legacy_modality_counts must map modality_id to a non-negative integer"
            )
        if modality_id not in modality_theme:
            raise ThemeRollupPitError(
                f"legacy_modality_counts names an unconfigured modality: {modality_id}"
            )
        legacy_counts[modality_id] = int(count)
    missing = sorted(set(modality_theme) - set(legacy_counts))
    if missing:
        raise ThemeRollupPitError(
            "legacy_modality_counts must count every configured modality; "
            f"missing: {', '.join(missing)}"
        )

    excluded = {key: 0 for key in _EXCLUSION_KEYS}
    row_notes = {key: 0 for key in _ROW_NOTE_KEYS}
    # value = (rank, row, phases_observed, enrollment_observed); only the winning
    # version of a trial contributes to the row notes.
    best: dict[tuple[str, str], tuple[tuple[datetime, int], dict[str, Any], bool, bool]] = {}

    for snapshot in snapshots:
        validated = validate_trial_snapshot(snapshot)
        knowledge_cutoff = _parse_instant(
            validated["knowledge_cutoff"], label="snapshot.knowledge_cutoff"
        )
        if knowledge_cutoff > as_of_instant:
            excluded["not_knowable_at_as_of"] += 1
            continue
        nct_id = str(validated["nct_id"])
        bindings = grouped_bindings.get(nct_id)
        if not bindings:
            excluded["unbound_nct"] += 1
            continue
        matched = [
            binding
            for binding in bindings
            if binding["source_record_ref"] == validated["source_record_ref"]
        ]
        if not matched:
            excluded["binding_evidence_mismatch"] += 1
            continue
        sponsor_class = _sponsor_class(validated)
        if sponsor_class != "INDUSTRY":
            excluded["non_industry_sponsor"] += 1
            continue

        phases_raw, phase1, phase2, phase3, phases_observed = _phase_columns(validated)
        enrollment_target, enrollment_observed = _enrollment_target(validated)
        ingest_day = _parse_instant(
            validated["first_seen_at"], label="snapshot.first_seen_at"
        ).date().isoformat()
        ordinal = int(validated["source_version_ordinal"])

        for binding in matched:
            modality_id = binding["modality_id"]
            theme_id = modality_theme.get(modality_id)
            if theme_id is None:
                excluded["unmapped_modality"] += 1
                continue
            first_post = binding["study_first_post_date"]
            row = {
                "modality_id": modality_id,
                "theme_id": theme_id,
                "nct_id": nct_id,
                "study_first_post_date": first_post,
                "year_month": first_post[:7],
                "phases_raw": phases_raw,
                "phase1": phase1,
                "phase2": phase2,
                "phase3": phase3,
                "enrollment_target": enrollment_target,
                "sponsor_class": "INDUSTRY",
                "ingest_date": ingest_day,
                "vocabulary_version": vocabulary_version,
                "provenance_plane": PIT_PROVENANCE_PLANE,
                "knowledge_cutoff": str(validated["knowledge_cutoff"]),
                "source_version_ordinal": ordinal,
                "snapshot_ref": str(validated["snapshot_id"]),
                "source_record_ref": str(validated["source_record_ref"]),
            }
            key = (modality_id, nct_id)
            rank = (knowledge_cutoff, ordinal)
            previous = best.get(key)
            if previous is None:
                best[key] = (rank, row, phases_observed, enrollment_observed)
                continue
            # A second knowable version of the same trial is a correction, not a
            # second study: the latest knowable one wins and the other is counted.
            excluded["superseded_by_later_knowable_version"] += 1
            if rank > previous[0]:
                best[key] = (rank, row, phases_observed, enrollment_observed)

    for _, _, phases_observed, enrollment_observed in best.values():
        if not phases_observed:
            row_notes["rows_without_observed_phases"] += 1
        if not enrollment_observed:
            row_notes["rows_without_observed_enrollment"] += 1

    rows = sorted((entry[1] for entry in best.values()), key=_row_sort_key)

    themes = _theme_coverage(rows, modality_theme, legacy_counts)
    document: dict[str, Any] = {
        "contract_id": THEME_ROLLUP_PIT_CONTRACT_ID,
        "schema_version": "1.0.0",
        "as_of": as_of_instant.isoformat().replace("+00:00", "Z"),
        "vocabulary_version": vocabulary_version,
        "coverage_class": "current_only",
        "membership_authority": "reviewed_modality_config_only",
        "pit_key_policy": "knowledge_cutoff_at_or_before_as_of",
        "row_shape": THEME_ROLLUP_PIT_ROW_SHAPE,
        "authority": dict(_AUTHORITY),
        "themes": themes,
        "rows": rows,
        "excluded": excluded,
        "row_notes": row_notes,
        "disclosure": _DISCLOSURE,
        "disclosure_zh": _DISCLOSURE_ZH,
        "hash_scope": THEME_ROLLUP_PIT_HASH_SCOPE,
    }
    document["rollup_id"] = (
        f"biocatalyst_theme_rollup_pit_{canonical_json_sha256(document)[:24]}"
    )
    document["rollup_payload_sha256"] = canonical_json_sha256(document)
    validate_theme_rollup_pit(document, repo_root=root)
    return document


def _theme_coverage(
    rows: Sequence[Mapping[str, Any]],
    modality_theme: Mapping[str, str],
    legacy_counts: Mapping[str, int],
) -> list[dict[str, Any]]:
    """Compute the per-theme coverage disclosure from real counts only."""

    pit_by_modality: dict[str, int] = {}
    for row in rows:
        modality_id = str(row["modality_id"])
        pit_by_modality[modality_id] = pit_by_modality.get(modality_id, 0) + 1

    theme_ids = sorted(set(modality_theme.values()))
    coverage: list[dict[str, Any]] = []
    for theme_id in theme_ids:
        modalities = sorted(
            modality_id
            for modality_id, mapped in modality_theme.items()
            if mapped == theme_id
        )
        n_pit = sum(pit_by_modality.get(modality_id, 0) for modality_id in modalities)
        n_legacy = sum(int(legacy_counts.get(mid, 0)) for mid in modalities)
        n_total = n_pit + n_legacy
        modality_rows: list[dict[str, Any]] = []
        for modality_id in modalities:
            modality_pit = pit_by_modality.get(modality_id, 0)
            modality_legacy = int(legacy_counts.get(modality_id, 0))
            modality_total = modality_pit + modality_legacy
            modality_rows.append(
                {
                    "modality_id": modality_id,
                    "n_studies_pit": modality_pit,
                    "n_studies_legacy": modality_legacy,
                    "n_studies_total": modality_total,
                    "pit_backed_fraction": floor_fraction(modality_pit, modality_total),
                    "provenance": provenance_label(modality_pit, modality_legacy),
                }
            )
        coverage.append(
            {
                "theme_id": theme_id,
                "n_studies_pit": n_pit,
                "n_studies_legacy": n_legacy,
                "n_studies_total": n_total,
                "pit_backed_fraction": floor_fraction(n_pit, n_total),
                "provenance": provenance_label(n_pit, n_legacy),
                "modalities": modality_rows,
                "coverage_note": (
                    f"{n_pit} of {n_total} studies point-in-time backed; "
                    f"{n_legacy} from the legacy theme store"
                ),
                "coverage_note_zh": (
                    f"{n_total}个研究中有{n_pit}个具备时点口径支撑；"
                    f"{n_legacy}个来自旧主题库"
                ),
            }
        )
    return coverage


# ---------------------------------------------------------------------------
# Semantic validation
# ---------------------------------------------------------------------------

def theme_rollup_pit_semantic_issues(
    document: Mapping[str, Any],
) -> list[ValidationIssue]:
    """Return deterministic semantic failures for one point-in-time theme rollup."""

    if not isinstance(document, Mapping):
        return [
            _issue("$", "theme_rollup_pit.document", "rollup must be a JSON object")
        ]
    issues: list[ValidationIssue] = []
    as_of = _instant_or_none(document.get("as_of"))
    if as_of is None:
        issues.append(
            _issue("$.as_of", "theme_rollup_pit.as_of", "as_of must be an ISO-8601 timestamp")
        )

    rows = document.get("rows")
    themes = document.get("themes")
    if isinstance(rows, list):
        issues.extend(_row_issues(rows, as_of, document.get("vocabulary_version")))
    if isinstance(themes, list) and isinstance(rows, list):
        issues.extend(_coverage_issues(themes, rows))

    authority = document.get("authority")
    if isinstance(authority, Mapping):
        if authority.get("is_context_only") is not True or any(
            authority.get(flag) is not False
            for flag in ("may_rank", "may_gate", "may_size", "may_escalate")
        ):
            issues.append(
                _issue(
                    "$.authority",
                    "theme_rollup_pit.authority",
                    "rollup authority must stay context-only with every may_* flag false",
                )
            )

    try:
        identity = {
            key: value
            for key, value in document.items()
            if key not in ("rollup_id", "rollup_payload_sha256")
        }
        identity_sha256 = canonical_json_sha256(identity)
        content_sha256 = canonical_json_sha256(
            {
                key: value
                for key, value in document.items()
                if key != "rollup_payload_sha256"
            }
        )
    except ContractError:
        return sorted(
            set(
                issues
                + [
                    _issue(
                        "$",
                        "theme_rollup_pit.canonical_payload",
                        "rollup must be finite canonical JSON",
                    )
                ]
            )
        )
    if document.get("rollup_id") != f"biocatalyst_theme_rollup_pit_{identity_sha256[:24]}":
        issues.append(
            _issue(
                "$.rollup_id",
                "theme_rollup_pit.identity",
                "rollup_id must derive from the canonical payload excluding rollup_id and rollup_payload_sha256",
            )
        )
    if document.get("rollup_payload_sha256") != content_sha256:
        issues.append(
            _issue(
                "$.rollup_payload_sha256",
                "theme_rollup_pit.hash",
                "rollup_payload_sha256 must hash the canonical payload excluding only itself",
            )
        )
    return sorted(set(issues))


def _row_issues(
    rows: Sequence[Any],
    as_of: datetime | None,
    vocabulary_version: object,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    keys: list[tuple[str, str]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            issues.append(
                _issue(f"$.rows[{index}]", "theme_rollup_pit.row", "each row must be a JSON object")
            )
            continue
        keys.append((str(row.get("modality_id")), str(row.get("nct_id"))))
        cutoff = _instant_or_none(row.get("knowledge_cutoff"))
        if cutoff is None:
            issues.append(
                _issue(
                    f"$.rows[{index}].knowledge_cutoff",
                    "theme_rollup_pit.row_cutoff",
                    "row knowledge_cutoff must be an ISO-8601 timestamp",
                )
            )
        elif as_of is not None and cutoff > as_of:
            issues.append(
                _issue(
                    f"$.rows[{index}].knowledge_cutoff",
                    "theme_rollup_pit.row_not_knowable",
                    "a row knowable only after as_of must not appear in the rollup",
                )
            )
        first_post = row.get("study_first_post_date")
        if not isinstance(first_post, str) or row.get("year_month") != first_post[:7]:
            issues.append(
                _issue(
                    f"$.rows[{index}].year_month",
                    "theme_rollup_pit.row_year_month",
                    "year_month must be the calendar month of study_first_post_date",
                )
            )
        if row.get("vocabulary_version") != vocabulary_version:
            issues.append(
                _issue(
                    f"$.rows[{index}].vocabulary_version",
                    "theme_rollup_pit.row_vocabulary",
                    "every row must carry the rollup's vocabulary_version",
                )
            )
        if row.get("provenance_plane") != PIT_PROVENANCE_PLANE:
            issues.append(
                _issue(
                    f"$.rows[{index}].provenance_plane",
                    "theme_rollup_pit.row_provenance",
                    "every rollup row must name the point-in-time plane that produced it",
                )
            )
    if keys != sorted(keys):
        issues.append(
            _issue(
                "$.rows",
                "theme_rollup_pit.row_order",
                "rows must be sorted by modality_id then nct_id",
            )
        )
    if len(set(keys)) != len(keys):
        issues.append(
            _issue(
                "$.rows",
                "theme_rollup_pit.row_unique",
                "rows must hold one knowable version per modality_id and nct_id",
            )
        )
    return issues


def _coverage_issues(
    themes: Sequence[Any], rows: Sequence[Any]
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    observed_pit: dict[str, int] = {}
    for row in rows:
        if isinstance(row, Mapping):
            theme_id = str(row.get("theme_id"))
            observed_pit[theme_id] = observed_pit.get(theme_id, 0) + 1
    declared_theme_ids: list[str] = []
    for index, theme in enumerate(themes):
        if not isinstance(theme, Mapping):
            issues.append(
                _issue(
                    f"$.themes[{index}]",
                    "theme_rollup_pit.theme",
                    "each theme coverage entry must be a JSON object",
                )
            )
            continue
        theme_id = str(theme.get("theme_id"))
        declared_theme_ids.append(theme_id)
        n_pit = theme.get("n_studies_pit")
        n_legacy = theme.get("n_studies_legacy")
        n_total = theme.get("n_studies_total")
        if not (_is_count(n_pit) and _is_count(n_legacy) and _is_count(n_total)):
            issues.append(
                _issue(
                    f"$.themes[{index}]",
                    "theme_rollup_pit.theme_counts",
                    "theme coverage counts must be non-negative integers",
                )
            )
            continue
        if n_pit != observed_pit.get(theme_id, 0):
            issues.append(
                _issue(
                    f"$.themes[{index}].n_studies_pit",
                    "theme_rollup_pit.theme_pit_count",
                    "n_studies_pit must equal the number of point-in-time rows for the theme",
                )
            )
        if n_total != n_pit + n_legacy:
            issues.append(
                _issue(
                    f"$.themes[{index}].n_studies_total",
                    "theme_rollup_pit.theme_total",
                    "n_studies_total must equal n_studies_pit plus n_studies_legacy",
                )
            )
        if theme.get("pit_backed_fraction") != floor_fraction(n_pit, n_pit + n_legacy):
            issues.append(
                _issue(
                    f"$.themes[{index}].pit_backed_fraction",
                    "theme_rollup_pit.theme_fraction",
                    "pit_backed_fraction must be the floored point-in-time share of real counts",
                )
            )
        if theme.get("provenance") != provenance_label(n_pit, n_legacy):
            issues.append(
                _issue(
                    f"$.themes[{index}].provenance",
                    "theme_rollup_pit.theme_provenance",
                    "theme provenance must name the plane that produced its counts",
                )
            )
        modalities = theme.get("modalities")
        if isinstance(modalities, list):
            declared_legacy = sum(
                int(modality["n_studies_legacy"])
                for modality in modalities
                if isinstance(modality, Mapping)
                and _is_count(modality.get("n_studies_legacy"))
            )
            if declared_legacy != n_legacy:
                issues.append(
                    _issue(
                        f"$.themes[{index}].n_studies_legacy",
                        "theme_rollup_pit.theme_legacy_total",
                        "theme n_studies_legacy must equal the sum of its modality legacy counts",
                    )
                )
        issues.extend(_modality_coverage_issues(index, theme, rows, theme_id))
    for theme_id in sorted(observed_pit):
        if theme_id not in declared_theme_ids:
            issues.append(
                _issue(
                    "$.themes",
                    "theme_rollup_pit.theme_missing",
                    f"theme {theme_id} has rows but no coverage disclosure",
                )
            )
    if declared_theme_ids != sorted(declared_theme_ids):
        issues.append(
            _issue(
                "$.themes",
                "theme_rollup_pit.theme_order",
                "theme coverage entries must be sorted by theme_id",
            )
        )
    return issues


def _modality_coverage_issues(
    index: int,
    theme: Mapping[str, Any],
    rows: Sequence[Any],
    theme_id: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    modalities = theme.get("modalities")
    if not isinstance(modalities, list):
        return issues
    observed: dict[str, int] = {}
    for row in rows:
        if isinstance(row, Mapping) and str(row.get("theme_id")) == theme_id:
            modality_id = str(row.get("modality_id"))
            observed[modality_id] = observed.get(modality_id, 0) + 1
    for position, modality in enumerate(modalities):
        if not isinstance(modality, Mapping):
            continue
        modality_id = str(modality.get("modality_id"))
        n_pit = modality.get("n_studies_pit")
        n_legacy = modality.get("n_studies_legacy")
        if not (_is_count(n_pit) and _is_count(n_legacy)):
            continue
        if n_pit != observed.get(modality_id, 0):
            issues.append(
                _issue(
                    f"$.themes[{index}].modalities[{position}].n_studies_pit",
                    "theme_rollup_pit.modality_pit_count",
                    "modality n_studies_pit must equal its point-in-time row count",
                )
            )
        if modality.get("provenance") != provenance_label(n_pit, n_legacy):
            issues.append(
                _issue(
                    f"$.themes[{index}].modalities[{position}].provenance",
                    "theme_rollup_pit.modality_provenance",
                    "modality provenance must name the plane that produced its counts",
                )
            )
    return issues


def validate_theme_rollup_pit(
    document: Any, *, repo_root: Path | str | None = None
) -> None:
    """Fail closed unless schema and point-in-time semantic controls both hold."""

    root = _repo_root(repo_root)
    registry = ContractRegistry(root)
    schema_issues = list(registry.issues(THEME_ROLLUP_PIT_CONTRACT_ID, document))
    semantic_issues = (
        theme_rollup_pit_semantic_issues(document)
        if isinstance(document, Mapping)
        else [_issue("$", "theme_rollup_pit.document", "rollup must be a JSON object")]
    )
    issues = tuple(sorted(set(schema_issues + semantic_issues)))
    if issues:
        raise ContractValidationError(THEME_ROLLUP_PIT_CONTRACT_ID, issues)


# ---------------------------------------------------------------------------
# Consumption helpers — the shape engine/theme_clinical already reads
# ---------------------------------------------------------------------------

STORE_COLUMNS: tuple[str, ...] = (
    "modality_id",
    "theme_id",
    "nct_id",
    "study_first_post_date",
    "year_month",
    "phases_raw",
    "phase1",
    "phase2",
    "phase3",
    "enrollment_target",
    "sponsor_class",
    "ingest_date",
    "vocabulary_version",
)


def pit_rollup_rows(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return store-shaped rows, each still labelled with its producing plane.

    The column set matches ``collectors/clinicaltrials_themes.STORE_COLS``
    exactly, plus ``provenance_plane`` — so a consumer can union these rows with
    the legacy store without a schema change, and can never lose track of which
    plane produced a value.
    """

    if not isinstance(document, Mapping):
        raise ThemeRollupPitError("rollup must be a JSON object")
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise ThemeRollupPitError("rollup rows must be a list")
    projected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ThemeRollupPitError("each rollup row must be a JSON object")
        projected.append(
            {
                **{column: row.get(column) for column in STORE_COLUMNS},
                "provenance_plane": row.get("provenance_plane"),
            }
        )
    return projected


def theme_coverage_disclosure(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return ``theme_id -> coverage disclosure`` for a consuming rollup."""

    if not isinstance(document, Mapping):
        raise ThemeRollupPitError("rollup must be a JSON object")
    themes = document.get("themes")
    if not isinstance(themes, list):
        raise ThemeRollupPitError("rollup themes must be a list")
    disclosure: dict[str, dict[str, Any]] = {}
    for theme in themes:
        if not isinstance(theme, Mapping):
            raise ThemeRollupPitError("each theme coverage entry must be a JSON object")
        disclosure[str(theme.get("theme_id"))] = {
            "n_studies_pit": theme.get("n_studies_pit"),
            "n_studies_legacy": theme.get("n_studies_legacy"),
            "n_studies_total": theme.get("n_studies_total"),
            "pit_backed_fraction": theme.get("pit_backed_fraction"),
            "provenance": theme.get("provenance"),
            "coverage_note": theme.get("coverage_note"),
            "coverage_note_zh": theme.get("coverage_note_zh"),
        }
    return disclosure


def pit_row_counts_by_modality(
    document: Mapping[str, Any],
) -> dict[tuple[str, str], int]:
    """Return ``(theme_id, modality_id) -> point-in-time row count``."""

    counts: dict[tuple[str, str], int] = {}
    for row in pit_rollup_rows(document):
        key = (str(row.get("theme_id")), str(row.get("modality_id")))
        counts[key] = counts.get(key, 0) + 1
    return counts


__all__ = [
    "BINDING_REVIEW_STATE",
    "LEGACY_PROVENANCE_PLANE",
    "MODALITY_CONFIG_REF",
    "PIT_FIRST_POST_DATE_SOURCE",
    "PIT_PROVENANCE_PLANE",
    "STORE_COLUMNS",
    "THEME_ROLLUP_PIT_CONTRACT_ID",
    "ThemeRollupPitError",
    "build_theme_rollup_pit",
    "floor_fraction",
    "load_modality_theme_map",
    "pit_rollup_rows",
    "pit_row_counts_by_modality",
    "provenance_label",
    "theme_coverage_disclosure",
    "theme_rollup_pit_semantic_issues",
    "validate_theme_rollup_pit",
]
