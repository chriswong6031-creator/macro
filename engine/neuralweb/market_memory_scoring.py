"""Pure W2B1 synthetic-only per-event scoring contracts.

This module adds two inert, content-addressed records over the W2A forward
contracts: an exact baseline forecast bundle and a score for one outcome
revision.  It deliberately does not add an opportunity writer, operational
seal, store, clock, filesystem root, environment switch, API, service,
scheduler, aggregate, comparison delta, winner, skill claim, fitting routine,
or promotion path.

All callers must supply already-built W2A records and exact W1 context bytes.
Only ``synthetic_fixture_only`` inputs are admitted.  Missing, censored,
abstained, and unavailable states remain explicit; a missing score is never
coerced to zero.  Decimal arithmetic runs under one fixed local context and a
zero-probability categorical forecast produces explicit positive infinity
without clipping.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation, localcontext
from itertools import pairwise
from types import MappingProxyType
from typing import Any, Final, NoReturn

from engine.neuralweb import market_memory_forward as forward

BASELINE_FORECAST_BUNDLE_SCHEMA = "market_memory.baseline_forecast_bundle.v1"
EVENT_SCORE_RECORD_SCHEMA = "market_memory.event_score_record.v1"

INPUT_PROFILE: Final = "synthetic_fixture_only"
NUMERIC_CONVENTION: Final = "decimal64_half_even_q18/v1"
CLAIMS: Mapping[str, bool] = MappingProxyType(
    {
        "operational_seal_authenticated": False,
        "opportunity_population_complete": False,
        "aggregate_eligible": False,
        "skill_claim_eligible": False,
    }
)

_MAX_BODY_BYTES = 256 * 1024
_MAX_ABSOLUTE_NUMBER = 10**15
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
_OPAQUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_BUNDLE_ID = re.compile(r"mmbaselinebundle_[a-f0-9]{64}\Z")
_SCORE_ID = re.compile(r"mmeventscore_[a-f0-9]{64}\Z")
_FORECAST_ID = re.compile(r"mmforecast_[a-f0-9]{64}\Z")
_FORECAST_KEY = re.compile(r"mmforecastkey_[a-f0-9]{64}\Z")
_TRIAL_ID = re.compile(r"mmtrial_[a-f0-9]{64}\Z")
_STATE_ID = re.compile(r"mmstate_[a-f0-9]{64}\Z")
_CONTEXT_ID = re.compile(r"mmctx_[a-f0-9]{64}\Z")
_EVENT_ID = re.compile(r"mmoutcomeevent_[a-f0-9]{64}\Z")
_OUTCOME_ID = re.compile(r"mmoutcome_[a-f0-9]{64}\Z")
_DECIMAL_TEXT = re.compile(r"(?:0|[1-9][0-9]*)\.[0-9]{18}\Z")

_DECIMAL_CONTEXT = Context(
    prec=64,
    rounding=ROUND_HALF_EVEN,
    Emin=-999_999,
    Emax=999_999,
)
_QUANTUM = Decimal("0.000000000000000001")

_FORMULAS: Final = {
    "squared_error": ("squared_error", "squared_error.v1"),
    "absolute_error": ("absolute_error", "absolute_error.v1"),
    "pinball_loss": ("mean_pinball_loss", "mean_pinball_loss.v1"),
    "log_loss": ("multiclass_log_loss", "multiclass_log_loss.v1"),
    "brier_score": ("multiclass_brier_sum", "multiclass_brier_sum.v1"),
}
_FORMULA_VERSIONS = {formula: version for formula, version in _FORMULAS.values()}
_UNAVAILABLE_REASONS = frozenset(
    {
        "baseline_input_unavailable",
        "baseline_model_unavailable",
        "quality_gate_failed",
        "policy_expired",
    }
)
_OUTCOME_REASONS = frozenset(
    {
        "source_window_incomplete",
        "instrument_unavailable",
        "event_invalidated",
        "coverage_ended",
        "source_unavailable",
        "source_not_published",
        "identity_unresolved",
        "quality_gate_failed",
    }
)
_NOT_SCORED_REASONS = frozenset(
    {
        "forecast_abstained",
        "baseline_unavailable",
        "outcome_censored",
        "outcome_missing",
    }
)

_BUNDLE_FIELDS = frozenset(
    {
        "schema",
        "baseline_forecast_bundle_id",
        "forecast_id",
        "forecast_key",
        "trial_registration_id",
        "state_snapshot_id",
        "context_id",
        "outcome_event_id",
        "target_sha256",
        "outcome_definition_sha256",
        "decision_cutoff",
        "sealed_at",
        "horizon_start",
        "horizon_end",
        "evaluation_at",
        "baseline_rows",
        "input_profile",
        "claims",
        "emission_enabled",
        "authority",
    }
)
_BASELINE_ROW_FIELDS = frozenset(
    {
        "baseline_id",
        "baseline_version",
        "config_sha256",
        "producer_code_sha256",
        "fit",
        "disposition",
        "unavailable_reason",
        "predictive_distribution",
    }
)
_FIT_FIELDS = frozenset({"kind", "cutoff", "artifact_sha256"})
_DISTRIBUTION_FIELDS = frozenset({"kind", "point", "quantiles", "probabilities"})
_QUANTILE_FIELDS = frozenset({"level", "value"})
_PROBABILITY_FIELDS = frozenset({"category", "probability"})
_CLAIM_FIELDS = frozenset(CLAIMS)

_EVENT_SCORE_FIELDS = frozenset(
    {
        "schema",
        "event_score_record_id",
        "baseline_forecast_bundle_id",
        "forecast_id",
        "forecast_key",
        "trial_registration_id",
        "state_snapshot_id",
        "context_id",
        "outcome_event_id",
        "outcome_record_id",
        "outcome_revision_number",
        "target_sha256",
        "outcome_definition_sha256",
        "decision_cutoff",
        "sealed_at",
        "horizon_start",
        "horizon_end",
        "evaluation_at",
        "outcome_status",
        "outcome_reason",
        "outcome_recorded_at",
        "evaluated_at",
        "evaluator_code_sha256",
        "evaluator_config_sha256",
        "formula",
        "formula_version",
        "numeric_convention",
        "orientation",
        "candidate_score",
        "baseline_scores",
        "input_profile",
        "claims",
        "emission_enabled",
        "authority",
    }
)
_SCORE_FIELDS = frozenset({"disposition", "not_scored_reason", "score_value"})
_SCORE_VALUE_FIELDS = frozenset({"kind", "decimal"})
_BASELINE_SCORE_FIELDS = frozenset(
    {
        "baseline_id",
        "baseline_version",
        "config_sha256",
        "disposition",
        "not_scored_reason",
        "score_value",
    }
)


class MarketMemoryScoringContractError(ValueError):
    """A W2B1 scoring value is unsafe, ambiguous, or non-canonical."""


def _fail(message: str) -> NoReturn:
    raise MarketMemoryScoringContractError(message)


def _forward_error(exc: Exception, *, field: str) -> NoReturn:
    raise MarketMemoryScoringContractError(
        f"{field} fails its W2A owner: {exc}"
    ) from exc


def _require_dict(value: object, *, field: str) -> dict[str, Any]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        _fail(f"{field} must be a plain JSON object with string keys")
    return value


def _require_fields(
    value: object, fields: frozenset[str], *, field: str
) -> dict[str, Any]:
    payload = _require_dict(value, field=field)
    if set(payload) != fields:
        missing = sorted(fields - set(payload))
        extra = sorted(set(payload) - fields)
        _fail(f"{field} fields are not canonical; missing={missing}, extra={extra}")
    return payload


def _canonical_bytes(value: object, *, field: str) -> bytes:
    try:
        return forward.canonical_json_bytes(value)
    except forward.MarketMemoryForwardContractError as exc:
        _forward_error(exc, field=field)


def _detached(value: object, *, field: str) -> dict[str, Any]:
    return _require_dict(json.loads(_canonical_bytes(value, field=field)), field=field)


def _exact_equal(left: object, right: object, *, field: str) -> bool:
    return _canonical_bytes(left, field=f"{field} supplied") == _canonical_bytes(
        right, field=f"{field} expected"
    )


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + hashlib.sha256(_canonical_bytes(core, field=field)).hexdigest()


def _match(value: object, pattern: re.Pattern[str], *, field: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(f"{field} has invalid syntax")
    return value


def _sha256(value: object, *, field: str) -> str:
    return _match(value, _SHA256, field=field)


def _opaque(value: object, *, field: str, maximum: int = 256) -> str:
    clean = _match(value, _OPAQUE, field=field)
    if len(clean.encode("utf-8")) > maximum:
        _fail(f"{field} exceeds its UTF-8 byte bound")
    return clean


def _number(value: object, *, field: str) -> int | float:
    if type(value) not in {int, float}:
        _fail(f"{field} must be a JSON number, not bool")
    if type(value) is float and not math.isfinite(value):
        _fail(f"{field} must be finite")
    if not -_MAX_ABSOLUTE_NUMBER <= value <= _MAX_ABSOLUTE_NUMBER:
        _fail(f"{field} exceeds the numeric bound")
    return value


def _utc(value: object, *, field: str) -> datetime:
    text = _match(value, _UTC_TIMESTAMP, field=field)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise MarketMemoryScoringContractError(f"{field} is not a timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail(f"{field} must be UTC")
    return parsed.astimezone(timezone.utc)


def _validate_claims(value: object) -> dict[str, bool]:
    payload = _require_fields(value, _CLAIM_FIELDS, field="claims")
    expected = dict(CLAIMS)
    if not _exact_equal(payload, expected, field="claims"):
        _fail("W2B1 claims must remain exactly false")
    return expected


def _validate_authority(value: object) -> dict[str, Any]:
    expected = dict(forward.AUTHORITY)
    if type(value) is not dict or not _exact_equal(value, expected, field="authority"):
        _fail("W2B1 authority must equal the W2A frozen zero-authority contract")
    return expected


def _validate_distribution(
    value: object, *, spec: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    payload = _require_fields(
        value, _DISTRIBUTION_FIELDS, field="predictive_distribution"
    )
    kind = payload["kind"]
    if kind not in {"scalar", "quantiles", "categorical"}:
        _fail("predictive_distribution.kind is unsupported")
    raw_quantiles = payload["quantiles"]
    raw_probabilities = payload["probabilities"]
    if type(raw_quantiles) is not list or len(raw_quantiles) > 32:
        _fail("predictive_distribution.quantiles exceeds its array bound")
    if type(raw_probabilities) is not list or len(raw_probabilities) > 32:
        _fail("predictive_distribution.probabilities exceeds its array bound")

    quantiles: list[dict[str, Any]] = []
    for item in raw_quantiles:
        row = _require_fields(item, _QUANTILE_FIELDS, field="forecast quantile")
        level = _number(row["level"], field="forecast quantile level")
        if not 0 < level < 1:
            _fail("forecast quantile level must be strictly between zero and one")
        quantiles.append(
            {"level": level, "value": _number(row["value"], field="quantile value")}
        )
    levels = [row["level"] for row in quantiles]
    if levels != sorted(set(levels)):
        _fail("forecast quantile levels must be sorted and unique")
    if any(left["value"] > right["value"] for left, right in pairwise(quantiles)):
        _fail("forecast quantile values must be nondecreasing")

    probabilities: list[dict[str, Any]] = []
    for item in raw_probabilities:
        row = _require_fields(
            item, _PROBABILITY_FIELDS, field="forecast category probability"
        )
        probability = _number(row["probability"], field="category probability")
        if not 0 <= probability <= 1:
            _fail("forecast category probability is outside [0,1]")
        probabilities.append(
            {
                "category": _opaque(row["category"], field="forecast category"),
                "probability": probability,
            }
        )
    categories = [row["category"] for row in probabilities]
    if categories != sorted(set(categories)):
        _fail("forecast categories must be sorted and unique")

    if kind == "scalar":
        point: int | float | None = _number(payload["point"], field="forecast point")
        if quantiles or probabilities:
            _fail("scalar forecast cannot carry quantiles or probabilities")
    elif kind == "quantiles":
        point = None
        if payload["point"] is not None or not quantiles or probabilities:
            _fail("quantile forecast must carry only quantiles")
    else:
        point = None
        if payload["point"] is not None or quantiles or len(probabilities) < 2:
            _fail("categorical forecast must carry only category probabilities")
        if not math.isclose(
            sum(float(row["probability"]) for row in probabilities),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            _fail("forecast category probabilities must sum to one")

    clean = {
        "kind": kind,
        "point": point,
        "quantiles": quantiles,
        "probabilities": probabilities,
    }
    if not _exact_equal(payload, clean, field="predictive_distribution"):
        _fail("predictive_distribution is not exact canonical JSON")
    if spec is not None:
        if clean["kind"] != spec["kind"]:
            _fail("predictive distribution kind differs from preregistration")
        if kind == "quantiles" and levels != spec["quantile_levels"]:
            _fail("predictive distribution quantile grid differs from preregistration")
        if kind == "categorical" and categories != spec["categories"]:
            _fail("predictive distribution categories differ from preregistration")
    return clean


def _validate_fit(value: object, *, decision_cutoff: datetime) -> dict[str, Any]:
    payload = _require_fields(value, _FIT_FIELDS, field="baseline fit")
    kind = payload["kind"]
    if kind == "fixed_rule":
        if payload["cutoff"] is not None or payload["artifact_sha256"] is not None:
            _fail("fixed_rule baseline fit cannot carry cutoff or artifact")
        return {"kind": kind, "cutoff": None, "artifact_sha256": None}
    if kind != "predecision_fit":
        _fail("baseline fit kind is unsupported")
    cutoff = _utc(payload["cutoff"], field="baseline fit cutoff")
    if cutoff > decision_cutoff:
        _fail("baseline fit cutoff is later than forecast decision_cutoff")
    return {
        "kind": kind,
        "cutoff": payload["cutoff"],
        "artifact_sha256": _sha256(
            payload["artifact_sha256"], field="baseline fit artifact_sha256"
        ),
    }


def _validate_baseline_rows(
    value: object,
    *,
    decision_cutoff: datetime,
    distribution_spec: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if type(value) is not list or not 1 <= len(value) <= 32:
        _fail("baseline_rows is outside its array bound")
    rows: list[dict[str, Any]] = []
    for item in value:
        payload = _require_fields(item, _BASELINE_ROW_FIELDS, field="baseline row")
        disposition = payload["disposition"]
        if disposition == "issued":
            if (
                payload["unavailable_reason"] is not None
                or payload["predictive_distribution"] is None
            ):
                _fail("issued baseline requires a distribution and null reason")
            distribution = _validate_distribution(
                payload["predictive_distribution"], spec=distribution_spec
            )
            reason = None
        elif disposition == "unavailable":
            if (
                payload["unavailable_reason"] not in _UNAVAILABLE_REASONS
                or payload["predictive_distribution"] is not None
            ):
                _fail(
                    "unavailable baseline requires a canonical reason and null distribution"
                )
            distribution = None
            reason = payload["unavailable_reason"]
        else:
            _fail("baseline disposition must be issued or unavailable")
        clean = {
            "baseline_id": _opaque(payload["baseline_id"], field="baseline_id"),
            "baseline_version": _opaque(
                payload["baseline_version"], field="baseline_version"
            ),
            "config_sha256": _sha256(
                payload["config_sha256"], field="baseline config_sha256"
            ),
            "producer_code_sha256": _sha256(
                payload["producer_code_sha256"], field="baseline producer_code_sha256"
            ),
            "fit": _validate_fit(payload["fit"], decision_cutoff=decision_cutoff),
            "disposition": disposition,
            "unavailable_reason": reason,
            "predictive_distribution": distribution,
        }
        if not _exact_equal(payload, clean, field="baseline row"):
            _fail("baseline row is not exact canonical JSON")
        rows.append(clean)
    identities = [row["baseline_id"] for row in rows]
    if identities != sorted(set(identities)):
        _fail("baseline_rows must be sorted and unique by baseline_id")
    return rows


def _clean_trial(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return forward.validate_trial_registration(value)
    except forward.MarketMemoryForwardContractError as exc:
        _forward_error(exc, field="trial_registration")


def _clean_forecast_join(
    value: Mapping[str, Any],
    *,
    trial_registration: Mapping[str, Any],
    state_snapshot: Mapping[str, Any],
    exact_context_bytes: bytes,
) -> dict[str, Any]:
    try:
        return forward.validate_forecast_record_join(
            value,
            trial_registration=trial_registration,
            state_snapshot=state_snapshot,
            exact_context_bytes=exact_context_bytes,
        )
    except forward.MarketMemoryForwardContractError as exc:
        _forward_error(exc, field="forecast_record")


def _clean_outcome_join(
    value: Mapping[str, Any],
    *,
    forecast_record: Mapping[str, Any],
    trial_registration: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        return forward.validate_outcome_record_join(
            value,
            forecast_record=forecast_record,
            trial_registration=trial_registration,
        )
    except forward.MarketMemoryForwardContractError as exc:
        _forward_error(exc, field="outcome_record")


def build_baseline_forecast_bundle(
    *,
    trial_registration: Mapping[str, Any],
    state_snapshot: Mapping[str, Any],
    forecast_record: Mapping[str, Any],
    exact_context_bytes: bytes,
    baseline_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build an inert synthetic baseline bundle for one exact W2A forecast."""

    trial = _clean_trial(trial_registration)
    forecast = _clean_forecast_join(
        forecast_record,
        trial_registration=trial,
        state_snapshot=state_snapshot,
        exact_context_bytes=exact_context_bytes,
    )
    if isinstance(baseline_rows, (str, bytes, bytearray)) or not isinstance(
        baseline_rows, Sequence
    ):
        _fail("baseline_rows must be a sequence of plain JSON objects")
    if any(type(row) is not dict for row in baseline_rows):
        _fail("baseline_rows entries must be plain JSON objects")
    rows = [copy.deepcopy(row) for row in baseline_rows]
    payload: dict[str, Any] = {
        "schema": BASELINE_FORECAST_BUNDLE_SCHEMA,
        "baseline_forecast_bundle_id": "",
        "forecast_id": forecast["forecast_id"],
        "forecast_key": forecast["forecast_key"],
        "trial_registration_id": trial["trial_registration_id"],
        "state_snapshot_id": forecast["state_snapshot_id"],
        "context_id": forecast["context_id"],
        "outcome_event_id": forecast["outcome_event_id"],
        "target_sha256": forecast["target_sha256"],
        "outcome_definition_sha256": forecast["outcome_definition_sha256"],
        "decision_cutoff": forecast["decision_cutoff"],
        "sealed_at": forecast["sealed_at"],
        "horizon_start": forecast["horizon_start"],
        "horizon_end": forecast["horizon_end"],
        "evaluation_at": forecast["evaluation_at"],
        "baseline_rows": rows,
        "input_profile": INPUT_PROFILE,
        "claims": dict(CLAIMS),
        "emission_enabled": False,
        "authority": dict(forward.AUTHORITY),
    }
    payload["baseline_forecast_bundle_id"] = _content_id(
        "mmbaselinebundle_", payload, field="baseline_forecast_bundle_id"
    )
    return validate_baseline_forecast_bundle_join(
        payload,
        trial_registration=trial,
        state_snapshot=state_snapshot,
        forecast_record=forecast,
        exact_context_bytes=exact_context_bytes,
    )


def validate_baseline_forecast_bundle_record(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and detach a self-authenticating baseline bundle."""

    payload = _require_fields(value, _BUNDLE_FIELDS, field="baseline_forecast_bundle")
    _canonical_bytes(payload, field="baseline_forecast_bundle")
    if payload["schema"] != BASELINE_FORECAST_BUNDLE_SCHEMA:
        _fail("baseline forecast bundle schema drift")
    bundle_id = _match(
        payload["baseline_forecast_bundle_id"],
        _BUNDLE_ID,
        field="baseline_forecast_bundle_id",
    )
    decision = _utc(payload["decision_cutoff"], field="bundle decision_cutoff")
    sealed = _utc(payload["sealed_at"], field="bundle sealed_at")
    start = _utc(payload["horizon_start"], field="bundle horizon_start")
    end = _utc(payload["horizon_end"], field="bundle horizon_end")
    evaluation = _utc(payload["evaluation_at"], field="bundle evaluation_at")
    if not decision <= sealed < start < end or evaluation != end:
        _fail("baseline bundle clocks differ from a valid sealed forecast horizon")
    rows = _validate_baseline_rows(payload["baseline_rows"], decision_cutoff=decision)
    if payload["input_profile"] != INPUT_PROFILE:
        _fail("baseline bundle input_profile must remain synthetic_fixture_only")
    clean: dict[str, Any] = {
        "schema": BASELINE_FORECAST_BUNDLE_SCHEMA,
        "baseline_forecast_bundle_id": bundle_id,
        "forecast_id": _match(
            payload["forecast_id"], _FORECAST_ID, field="forecast_id"
        ),
        "forecast_key": _match(
            payload["forecast_key"], _FORECAST_KEY, field="forecast_key"
        ),
        "trial_registration_id": _match(
            payload["trial_registration_id"], _TRIAL_ID, field="trial_registration_id"
        ),
        "state_snapshot_id": _match(
            payload["state_snapshot_id"], _STATE_ID, field="state_snapshot_id"
        ),
        "context_id": _match(payload["context_id"], _CONTEXT_ID, field="context_id"),
        "outcome_event_id": _match(
            payload["outcome_event_id"], _EVENT_ID, field="outcome_event_id"
        ),
        "target_sha256": _sha256(payload["target_sha256"], field="target_sha256"),
        "outcome_definition_sha256": _sha256(
            payload["outcome_definition_sha256"], field="outcome_definition_sha256"
        ),
        "decision_cutoff": payload["decision_cutoff"],
        "sealed_at": payload["sealed_at"],
        "horizon_start": payload["horizon_start"],
        "horizon_end": payload["horizon_end"],
        "evaluation_at": payload["evaluation_at"],
        "baseline_rows": rows,
        "input_profile": INPUT_PROFILE,
        "claims": _validate_claims(payload["claims"]),
        "emission_enabled": False,
        "authority": _validate_authority(payload["authority"]),
    }
    if payload["emission_enabled"] is not False:
        _fail("baseline bundle emission must remain disabled")
    if not _exact_equal(payload, clean, field="baseline_forecast_bundle"):
        _fail("baseline forecast bundle is not exact canonical JSON")
    expected_id = _content_id(
        "mmbaselinebundle_", clean, field="baseline_forecast_bundle_id"
    )
    if bundle_id != expected_id:
        _fail("baseline_forecast_bundle_id does not bind canonical content")
    return _detached(clean, field="baseline_forecast_bundle")


def validate_baseline_forecast_bundle_join(
    value: Mapping[str, Any],
    *,
    trial_registration: Mapping[str, Any],
    state_snapshot: Mapping[str, Any],
    forecast_record: Mapping[str, Any],
    exact_context_bytes: bytes,
) -> dict[str, Any]:
    """Revalidate a bundle against the exact W2A trial/state/forecast/context."""

    clean = validate_baseline_forecast_bundle_record(value)
    trial = _clean_trial(trial_registration)
    forecast = _clean_forecast_join(
        forecast_record,
        trial_registration=trial,
        state_snapshot=state_snapshot,
        exact_context_bytes=exact_context_bytes,
    )
    joins = {
        "forecast_id": forecast["forecast_id"],
        "forecast_key": forecast["forecast_key"],
        "trial_registration_id": trial["trial_registration_id"],
        "state_snapshot_id": forecast["state_snapshot_id"],
        "context_id": forecast["context_id"],
        "outcome_event_id": forecast["outcome_event_id"],
        "target_sha256": forecast["target_sha256"],
        "outcome_definition_sha256": forecast["outcome_definition_sha256"],
        "decision_cutoff": forecast["decision_cutoff"],
        "sealed_at": forecast["sealed_at"],
        "horizon_start": forecast["horizon_start"],
        "horizon_end": forecast["horizon_end"],
        "evaluation_at": forecast["evaluation_at"],
    }
    for field, expected in joins.items():
        if clean[field] != expected:
            _fail(f"baseline bundle {field} differs from exact forecast/trial join")
    expected_refs = trial["baselines"]
    supplied_refs = [
        {
            "baseline_id": row["baseline_id"],
            "baseline_version": row["baseline_version"],
            "config_sha256": row["config_sha256"],
        }
        for row in clean["baseline_rows"]
    ]
    if not _exact_equal(supplied_refs, expected_refs, field="baseline identities"):
        _fail(
            "baseline rows are missing, extra, reordered, or drifted from preregistration"
        )
    _validate_baseline_rows(
        clean["baseline_rows"],
        decision_cutoff=_utc(forecast["decision_cutoff"], field="decision_cutoff"),
        distribution_spec=trial["distribution"],
    )
    return clean


def _strict_json_object(body: bytes, *, field: str) -> dict[str, Any]:
    if type(body) is not bytes:
        _fail(f"{field} JSON body must be bytes")
    if not body or len(body) > _MAX_BODY_BYTES:
        _fail(f"{field} JSON body is empty or exceeds its byte bound")
    if body.startswith(b"\xef\xbb\xbf"):
        _fail(f"{field} JSON body must not carry a UTF-8 BOM")

    def reject_constant(value: str) -> NoReturn:
        _fail(f"{field} JSON contains non-finite constant {value}")

    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                _fail(f"{field} JSON contains duplicate key {key!r}")
            result[key] = item
        return result

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise MarketMemoryScoringContractError(
            f"{field} JSON is not valid UTF-8"
        ) from exc
    except MarketMemoryScoringContractError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise MarketMemoryScoringContractError(
            f"{field} JSON is not one exact JSON document"
        ) from exc
    payload = _require_dict(value, field=field)
    canonical = _canonical_bytes(payload, field=field)
    if body != canonical:
        _fail(f"{field} JSON body must be exact canonical JSON bytes")
    return payload


def load_baseline_forecast_bundle_join_json(
    body: bytes,
    *,
    trial_registration: Mapping[str, Any],
    state_snapshot: Mapping[str, Any],
    forecast_record: Mapping[str, Any],
    exact_context_bytes: bytes,
) -> dict[str, Any]:
    """Strictly parse a bundle and revalidate every immutable W2A join."""

    return validate_baseline_forecast_bundle_join(
        _strict_json_object(body, field="baseline_forecast_bundle"),
        trial_registration=trial_registration,
        state_snapshot=state_snapshot,
        forecast_record=forecast_record,
        exact_context_bytes=exact_context_bytes,
    )


def _validate_outcome_value(
    value: object, *, target: Mapping[str, Any]
) -> dict[str, Any]:
    fields = frozenset({"value_type", "value", "unit"})
    payload = _require_fields(value, fields, field="outcome_value")
    if payload["value_type"] != target["value_type"]:
        _fail("outcome value_type differs from preregistered target")
    if payload["unit"] != target["unit"]:
        _fail("outcome unit differs from preregistered target")
    if target["value_type"] == "string":
        clean_value: str | int | float = _opaque(
            payload["value"], field="outcome category", maximum=128
        )
        if clean_value not in target["categories"]:
            _fail("outcome category was not preregistered")
    elif target["value_type"] == "integer":
        if type(payload["value"]) is not int:
            _fail("integer outcome must be int, not bool")
        clean_value = _number(payload["value"], field="integer outcome")
    else:
        clean_value = _number(payload["value"], field="numeric outcome")
    clean = {
        "value_type": target["value_type"],
        "value": clean_value,
        "unit": target["unit"],
    }
    if not _exact_equal(payload, clean, field="outcome_value"):
        _fail("outcome_value is not exact canonical JSON")
    return clean


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite() or value < 0:
        _fail("finite proper score must be nonnegative")
    with localcontext(_DECIMAL_CONTEXT):
        clean = value.quantize(_QUANTUM)
    if clean.is_zero():
        clean = Decimal(0).quantize(_QUANTUM)
    text = format(clean, ".18f")
    if _DECIMAL_TEXT.fullmatch(text) is None:
        _fail("score could not be encoded as canonical nonnegative decimal")
    return text


def _finite_score(value: Decimal) -> dict[str, str]:
    return {"kind": "finite", "decimal": _decimal_text(value)}


def score_predictive_distribution(
    *,
    trial_registration: Mapping[str, Any],
    predictive_distribution: Mapping[str, Any],
    outcome_value: Mapping[str, Any],
) -> dict[str, Any]:
    """Score one distribution under its exact preregistered proper-score rule."""

    trial = _clean_trial(trial_registration)
    distribution = _validate_distribution(
        predictive_distribution, spec=trial["distribution"]
    )
    outcome = _validate_outcome_value(outcome_value, target=trial["target"])
    formula, version = _FORMULAS[trial["proper_score"]["name"]]

    with localcontext(_DECIMAL_CONTEXT) as context:
        if formula in {"squared_error", "absolute_error"}:
            prediction = _decimal(distribution["point"])
            observed = _decimal(outcome["value"])
            error = prediction - observed
            raw_score = error * error if formula == "squared_error" else abs(error)
            score_value = _finite_score(raw_score)
        elif formula == "mean_pinball_loss":
            observed = _decimal(outcome["value"])
            total = Decimal(0)
            for row in distribution["quantiles"]:
                level = _decimal(row["level"])
                quantile = _decimal(row["value"])
                if observed >= quantile:
                    total += level * (observed - quantile)
                else:
                    total += (Decimal(1) - level) * (quantile - observed)
            raw_score = total / Decimal(len(distribution["quantiles"]))
            score_value = _finite_score(raw_score)
        elif formula == "multiclass_log_loss":
            probability = next(
                _decimal(row["probability"])
                for row in distribution["probabilities"]
                if row["category"] == outcome["value"]
            )
            if probability.is_zero():
                score_value = {"kind": "positive_infinity", "decimal": None}
            else:
                try:
                    raw_score = -probability.ln(context=context)
                except InvalidOperation as exc:
                    raise MarketMemoryScoringContractError(
                        "categorical probability cannot be scored"
                    ) from exc
                score_value = _finite_score(raw_score)
        else:
            total = Decimal(0)
            for row in distribution["probabilities"]:
                observed = (
                    Decimal(1) if row["category"] == outcome["value"] else Decimal(0)
                )
                error = _decimal(row["probability"]) - observed
                total += error * error
            score_value = _finite_score(total)
    return {
        "formula": formula,
        "formula_version": version,
        "numeric_convention": NUMERIC_CONVENTION,
        "orientation": "lower_is_better",
        "score_value": score_value,
    }


def _validate_score_value(value: object) -> dict[str, str | None]:
    payload = _require_fields(value, _SCORE_VALUE_FIELDS, field="score_value")
    if payload["kind"] == "positive_infinity":
        if payload["decimal"] is not None:
            _fail("positive infinity score requires null decimal")
        return {"kind": "positive_infinity", "decimal": None}
    if payload["kind"] != "finite" or type(payload["decimal"]) is not str:
        _fail("score_value kind is unsupported")
    text = payload["decimal"]
    if not 20 <= len(text) <= 50 or _DECIMAL_TEXT.fullmatch(text) is None:
        _fail("finite score decimal is not canonical")
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise MarketMemoryScoringContractError(
            "finite score decimal is invalid"
        ) from exc
    if _decimal_text(parsed) != text:
        _fail("finite score decimal has a non-canonical spelling")
    return {"kind": "finite", "decimal": text}


def _validate_score(
    value: object, *, allowed_reasons: frozenset[str], field: str
) -> dict[str, Any]:
    payload = _require_fields(value, _SCORE_FIELDS, field=field)
    if payload["disposition"] == "scored":
        if payload["not_scored_reason"] is not None or payload["score_value"] is None:
            _fail(f"{field} scored disposition requires a value and null reason")
        score_value = _validate_score_value(payload["score_value"])
        reason = None
    elif payload["disposition"] == "not_scored":
        if (
            payload["not_scored_reason"] not in allowed_reasons
            or payload["score_value"] is not None
        ):
            _fail(f"{field} not_scored disposition requires a canonical reason")
        score_value = None
        reason = payload["not_scored_reason"]
    else:
        _fail(f"{field} disposition is unsupported")
    return {
        "disposition": payload["disposition"],
        "not_scored_reason": reason,
        "score_value": score_value,
    }


def _validate_baseline_scores(value: object) -> list[dict[str, Any]]:
    if type(value) is not list or not 1 <= len(value) <= 32:
        _fail("baseline_scores is outside its array bound")
    rows: list[dict[str, Any]] = []
    for item in value:
        payload = _require_fields(item, _BASELINE_SCORE_FIELDS, field="baseline score")
        score = _validate_score(
            {
                "disposition": payload["disposition"],
                "not_scored_reason": payload["not_scored_reason"],
                "score_value": payload["score_value"],
            },
            allowed_reasons=frozenset(
                {"baseline_unavailable", "outcome_censored", "outcome_missing"}
            ),
            field="baseline score",
        )
        clean = {
            "baseline_id": _opaque(payload["baseline_id"], field="baseline_id"),
            "baseline_version": _opaque(
                payload["baseline_version"], field="baseline_version"
            ),
            "config_sha256": _sha256(
                payload["config_sha256"], field="baseline config_sha256"
            ),
            **score,
        }
        if not _exact_equal(payload, clean, field="baseline score"):
            _fail("baseline score is not exact canonical JSON")
        rows.append(clean)
    ids = [row["baseline_id"] for row in rows]
    if ids != sorted(set(ids)):
        _fail("baseline_scores must be sorted and unique by baseline_id")
    return rows


def _not_scored(reason: str) -> dict[str, Any]:
    return {
        "disposition": "not_scored",
        "not_scored_reason": reason,
        "score_value": None,
    }


def _scored(score_value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "disposition": "scored",
        "not_scored_reason": None,
        "score_value": copy.deepcopy(dict(score_value)),
    }


def _score_components(
    *,
    trial: Mapping[str, Any],
    forecast: Mapping[str, Any],
    outcome: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if outcome["status"] != "complete":
        reason = f"outcome_{outcome['status']}"
        candidate = _not_scored(reason)
    elif forecast["disposition"] == "abstained":
        candidate = _not_scored("forecast_abstained")
    else:
        assert forecast["predictive_distribution"] is not None
        assert outcome["outcome_value"] is not None
        candidate_result = score_predictive_distribution(
            trial_registration=trial,
            predictive_distribution=forecast["predictive_distribution"],
            outcome_value=outcome["outcome_value"],
        )
        candidate = _scored(candidate_result["score_value"])

    baseline_scores: list[dict[str, Any]] = []
    for baseline in bundle["baseline_rows"]:
        identity = {
            "baseline_id": baseline["baseline_id"],
            "baseline_version": baseline["baseline_version"],
            "config_sha256": baseline["config_sha256"],
        }
        if outcome["status"] != "complete":
            score = _not_scored(f"outcome_{outcome['status']}")
        elif baseline["disposition"] == "unavailable":
            score = _not_scored("baseline_unavailable")
        else:
            assert baseline["predictive_distribution"] is not None
            assert outcome["outcome_value"] is not None
            result = score_predictive_distribution(
                trial_registration=trial,
                predictive_distribution=baseline["predictive_distribution"],
                outcome_value=outcome["outcome_value"],
            )
            score = _scored(result["score_value"])
        baseline_scores.append({**identity, **score})
    return candidate, baseline_scores


def _assemble_event_score(
    *,
    trial: Mapping[str, Any],
    forecast: Mapping[str, Any],
    outcome: Mapping[str, Any],
    bundle: Mapping[str, Any],
    evaluated_at: str,
    evaluator_code_sha256: str,
    evaluator_config_sha256: str,
) -> dict[str, Any]:
    evaluated = _utc(evaluated_at, field="evaluated_at")
    recorded = _utc(outcome["recorded_at"], field="outcome recorded_at")
    if evaluated < recorded:
        _fail("evaluated_at cannot precede outcome recorded_at")
    candidate_score, baseline_scores = _score_components(
        trial=trial, forecast=forecast, outcome=outcome, bundle=bundle
    )
    formula, version = _FORMULAS[trial["proper_score"]["name"]]
    payload: dict[str, Any] = {
        "schema": EVENT_SCORE_RECORD_SCHEMA,
        "event_score_record_id": "",
        "baseline_forecast_bundle_id": bundle["baseline_forecast_bundle_id"],
        "forecast_id": forecast["forecast_id"],
        "forecast_key": forecast["forecast_key"],
        "trial_registration_id": trial["trial_registration_id"],
        "state_snapshot_id": forecast["state_snapshot_id"],
        "context_id": forecast["context_id"],
        "outcome_event_id": forecast["outcome_event_id"],
        "outcome_record_id": outcome["outcome_record_id"],
        "outcome_revision_number": outcome["revision_number"],
        "target_sha256": forecast["target_sha256"],
        "outcome_definition_sha256": forecast["outcome_definition_sha256"],
        "decision_cutoff": forecast["decision_cutoff"],
        "sealed_at": forecast["sealed_at"],
        "horizon_start": forecast["horizon_start"],
        "horizon_end": forecast["horizon_end"],
        "evaluation_at": forecast["evaluation_at"],
        "outcome_status": outcome["status"],
        "outcome_reason": outcome["reason"],
        "outcome_recorded_at": outcome["recorded_at"],
        "evaluated_at": evaluated_at,
        "evaluator_code_sha256": evaluator_code_sha256,
        "evaluator_config_sha256": evaluator_config_sha256,
        "formula": formula,
        "formula_version": version,
        "numeric_convention": NUMERIC_CONVENTION,
        "orientation": "lower_is_better",
        "candidate_score": candidate_score,
        "baseline_scores": baseline_scores,
        "input_profile": INPUT_PROFILE,
        "claims": dict(CLAIMS),
        "emission_enabled": False,
        "authority": dict(forward.AUTHORITY),
    }
    payload["event_score_record_id"] = _content_id(
        "mmeventscore_", payload, field="event_score_record_id"
    )
    return payload


def build_event_score_record(
    *,
    trial_registration: Mapping[str, Any],
    state_snapshot: Mapping[str, Any],
    forecast_record: Mapping[str, Any],
    exact_context_bytes: bytes,
    outcome_record: Mapping[str, Any],
    baseline_forecast_bundle: Mapping[str, Any],
    evaluated_at: str,
    evaluator_code_sha256: str,
    evaluator_config_sha256: str,
) -> dict[str, Any]:
    """Build one score record for one exact W2A outcome revision."""

    trial = _clean_trial(trial_registration)
    forecast = _clean_forecast_join(
        forecast_record,
        trial_registration=trial,
        state_snapshot=state_snapshot,
        exact_context_bytes=exact_context_bytes,
    )
    outcome = _clean_outcome_join(
        outcome_record, forecast_record=forecast, trial_registration=trial
    )
    bundle = validate_baseline_forecast_bundle_join(
        baseline_forecast_bundle,
        trial_registration=trial,
        state_snapshot=state_snapshot,
        forecast_record=forecast,
        exact_context_bytes=exact_context_bytes,
    )
    payload = _assemble_event_score(
        trial=trial,
        forecast=forecast,
        outcome=outcome,
        bundle=bundle,
        evaluated_at=evaluated_at,
        evaluator_code_sha256=_sha256(
            evaluator_code_sha256, field="evaluator_code_sha256"
        ),
        evaluator_config_sha256=_sha256(
            evaluator_config_sha256, field="evaluator_config_sha256"
        ),
    )
    return validate_event_score_record_join(
        payload,
        trial_registration=trial,
        state_snapshot=state_snapshot,
        forecast_record=forecast,
        exact_context_bytes=exact_context_bytes,
        outcome_record=outcome,
        baseline_forecast_bundle=bundle,
    )


def validate_event_score_record(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and detach one self-authenticating per-event score record."""

    payload = _require_fields(value, _EVENT_SCORE_FIELDS, field="event_score_record")
    _canonical_bytes(payload, field="event_score_record")
    if payload["schema"] != EVENT_SCORE_RECORD_SCHEMA:
        _fail("event score record schema drift")
    record_id = _match(
        payload["event_score_record_id"], _SCORE_ID, field="event_score_record_id"
    )
    outcome_revision = payload["outcome_revision_number"]
    if type(outcome_revision) is not int or not 1 <= outcome_revision <= 1_000_000:
        _fail("outcome_revision_number must be a bounded int, not bool")
    decision = _utc(payload["decision_cutoff"], field="score decision_cutoff")
    sealed = _utc(payload["sealed_at"], field="score sealed_at")
    start = _utc(payload["horizon_start"], field="score horizon_start")
    end = _utc(payload["horizon_end"], field="score horizon_end")
    evaluation = _utc(payload["evaluation_at"], field="score evaluation_at")
    recorded = _utc(payload["outcome_recorded_at"], field="score outcome_recorded_at")
    evaluated = _utc(payload["evaluated_at"], field="score evaluated_at")
    if not decision <= sealed < start < end or evaluation != end:
        _fail("event score forecast clocks are invalid")
    if evaluated < recorded:
        _fail("event score evaluated_at precedes outcome_recorded_at")
    status = payload["outcome_status"]
    reason = payload["outcome_reason"]
    if status == "complete":
        if reason is not None:
            _fail("complete score outcome requires null reason")
    elif status == "censored":
        if reason not in {
            "source_window_incomplete",
            "instrument_unavailable",
            "event_invalidated",
            "coverage_ended",
        }:
            _fail("censored score outcome requires a canonical censored reason")
    elif status == "missing":
        if reason not in {
            "source_unavailable",
            "source_not_published",
            "identity_unresolved",
            "quality_gate_failed",
        }:
            _fail("missing score outcome requires a canonical missing reason")
    else:
        _fail("event score outcome_status is unsupported")
    formula = payload["formula"]
    if formula not in _FORMULA_VERSIONS:
        _fail("event score formula is unsupported")
    if payload["formula_version"] != _FORMULA_VERSIONS[formula]:
        _fail("event score formula_version does not match formula")
    if payload["numeric_convention"] != NUMERIC_CONVENTION:
        _fail("event score numeric_convention drift")
    if payload["orientation"] != "lower_is_better":
        _fail("event score orientation drift")
    candidate = _validate_score(
        payload["candidate_score"],
        allowed_reasons=frozenset(
            {"forecast_abstained", "outcome_censored", "outcome_missing"}
        ),
        field="candidate_score",
    )
    baselines = _validate_baseline_scores(payload["baseline_scores"])
    if status in {"censored", "missing"}:
        expected_reason = f"outcome_{status}"
        if candidate["not_scored_reason"] != expected_reason or any(
            row["not_scored_reason"] != expected_reason for row in baselines
        ):
            _fail(
                "non-complete outcome must leave every event score explicitly unscored"
            )
    else:
        if candidate["not_scored_reason"] not in {None, "forecast_abstained"}:
            _fail("complete outcome has an impossible candidate score reason")
        if any(
            row["not_scored_reason"] not in {None, "baseline_unavailable"}
            for row in baselines
        ):
            _fail("complete outcome has an impossible baseline score reason")
    if formula != "multiclass_log_loss" and any(
        score_value is not None and score_value["kind"] == "positive_infinity"
        for score_value in [
            candidate["score_value"],
            *(row["score_value"] for row in baselines),
        ]
    ):
        _fail("positive infinity is only valid for unclipped multiclass log loss")
    if payload["input_profile"] != INPUT_PROFILE:
        _fail("event score input_profile must remain synthetic_fixture_only")
    if payload["emission_enabled"] is not False:
        _fail("event score emission must remain disabled")
    clean: dict[str, Any] = {
        "schema": EVENT_SCORE_RECORD_SCHEMA,
        "event_score_record_id": record_id,
        "baseline_forecast_bundle_id": _match(
            payload["baseline_forecast_bundle_id"],
            _BUNDLE_ID,
            field="baseline_forecast_bundle_id",
        ),
        "forecast_id": _match(
            payload["forecast_id"], _FORECAST_ID, field="forecast_id"
        ),
        "forecast_key": _match(
            payload["forecast_key"], _FORECAST_KEY, field="forecast_key"
        ),
        "trial_registration_id": _match(
            payload["trial_registration_id"], _TRIAL_ID, field="trial_registration_id"
        ),
        "state_snapshot_id": _match(
            payload["state_snapshot_id"], _STATE_ID, field="state_snapshot_id"
        ),
        "context_id": _match(payload["context_id"], _CONTEXT_ID, field="context_id"),
        "outcome_event_id": _match(
            payload["outcome_event_id"], _EVENT_ID, field="outcome_event_id"
        ),
        "outcome_record_id": _match(
            payload["outcome_record_id"], _OUTCOME_ID, field="outcome_record_id"
        ),
        "outcome_revision_number": outcome_revision,
        "target_sha256": _sha256(payload["target_sha256"], field="target_sha256"),
        "outcome_definition_sha256": _sha256(
            payload["outcome_definition_sha256"], field="outcome_definition_sha256"
        ),
        "decision_cutoff": payload["decision_cutoff"],
        "sealed_at": payload["sealed_at"],
        "horizon_start": payload["horizon_start"],
        "horizon_end": payload["horizon_end"],
        "evaluation_at": payload["evaluation_at"],
        "outcome_status": status,
        "outcome_reason": reason,
        "outcome_recorded_at": payload["outcome_recorded_at"],
        "evaluated_at": payload["evaluated_at"],
        "evaluator_code_sha256": _sha256(
            payload["evaluator_code_sha256"], field="evaluator_code_sha256"
        ),
        "evaluator_config_sha256": _sha256(
            payload["evaluator_config_sha256"], field="evaluator_config_sha256"
        ),
        "formula": formula,
        "formula_version": payload["formula_version"],
        "numeric_convention": NUMERIC_CONVENTION,
        "orientation": "lower_is_better",
        "candidate_score": candidate,
        "baseline_scores": baselines,
        "input_profile": INPUT_PROFILE,
        "claims": _validate_claims(payload["claims"]),
        "emission_enabled": False,
        "authority": _validate_authority(payload["authority"]),
    }
    if not _exact_equal(payload, clean, field="event_score_record"):
        _fail("event score record is not exact canonical JSON")
    expected_id = _content_id("mmeventscore_", clean, field="event_score_record_id")
    if record_id != expected_id:
        _fail("event_score_record_id does not bind canonical content")
    return _detached(clean, field="event_score_record")


def validate_event_score_record_join(
    value: Mapping[str, Any],
    *,
    trial_registration: Mapping[str, Any],
    state_snapshot: Mapping[str, Any],
    forecast_record: Mapping[str, Any],
    exact_context_bytes: bytes,
    outcome_record: Mapping[str, Any],
    baseline_forecast_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute one score against every exact W2A and W2B1 dependency."""

    clean = validate_event_score_record(value)
    trial = _clean_trial(trial_registration)
    forecast = _clean_forecast_join(
        forecast_record,
        trial_registration=trial,
        state_snapshot=state_snapshot,
        exact_context_bytes=exact_context_bytes,
    )
    outcome = _clean_outcome_join(
        outcome_record, forecast_record=forecast, trial_registration=trial
    )
    bundle = validate_baseline_forecast_bundle_join(
        baseline_forecast_bundle,
        trial_registration=trial,
        state_snapshot=state_snapshot,
        forecast_record=forecast,
        exact_context_bytes=exact_context_bytes,
    )
    expected = _assemble_event_score(
        trial=trial,
        forecast=forecast,
        outcome=outcome,
        bundle=bundle,
        evaluated_at=clean["evaluated_at"],
        evaluator_code_sha256=clean["evaluator_code_sha256"],
        evaluator_config_sha256=clean["evaluator_config_sha256"],
    )
    if not _exact_equal(clean, expected, field="event score exact join"):
        _fail("event score differs from recomputed exact dependency join")
    return clean


def load_event_score_record_join_json(
    body: bytes,
    *,
    trial_registration: Mapping[str, Any],
    state_snapshot: Mapping[str, Any],
    forecast_record: Mapping[str, Any],
    exact_context_bytes: bytes,
    outcome_record: Mapping[str, Any],
    baseline_forecast_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Strictly parse one score and revalidate every immutable dependency."""

    return validate_event_score_record_join(
        _strict_json_object(body, field="event_score_record"),
        trial_registration=trial_registration,
        state_snapshot=state_snapshot,
        forecast_record=forecast_record,
        exact_context_bytes=exact_context_bytes,
        outcome_record=outcome_record,
        baseline_forecast_bundle=baseline_forecast_bundle,
    )


__all__ = [
    "BASELINE_FORECAST_BUNDLE_SCHEMA",
    "CLAIMS",
    "EVENT_SCORE_RECORD_SCHEMA",
    "INPUT_PROFILE",
    "NUMERIC_CONVENTION",
    "MarketMemoryScoringContractError",
    "build_baseline_forecast_bundle",
    "build_event_score_record",
    "load_baseline_forecast_bundle_join_json",
    "load_event_score_record_join_json",
    "score_predictive_distribution",
    "validate_baseline_forecast_bundle_join",
    "validate_baseline_forecast_bundle_record",
    "validate_event_score_record",
    "validate_event_score_record_join",
]
