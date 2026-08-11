"""Pure W5A synthetic Operating Cortex conformance kernel.

The kernel consumes caller-supplied, content-addressed evidence and claim cards
over one exact W4A episodic-retrieval record.  It performs structural byte-span
closure, salience, contradiction, missingness, falsifier, and citation audits.
It never evaluates semantic entailment or attention quality and has no clock,
filesystem, network, LLM, store, service, write, or emission capability.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation, localcontext
from types import MappingProxyType
from typing import Any, Final, NoReturn

from engine.neuralweb import market_memory_forward as forward
from engine.neuralweb import market_memory_retrieval as retrieval

OPERATING_CORTEX_REGISTRATION_SCHEMA = "market_memory.operating_cortex_registration.v1"
OPERATING_CORTEX_PACKET_SCHEMA = "market_memory.operating_cortex_packet.v1"
INPUT_PROFILE: Final = "synthetic_fixture_only"
NUMERIC_CONVENTION: Final = "decimal64_half_even_one_final_q18/v1"

CLAIMS: Mapping[str, bool] = MappingProxyType(
    {
        "operational_input_authenticated": False,
        "evidence_population_complete": False,
        "salience_component_provenance_authenticated": False,
        "citation_semantic_entailment_evaluated": False,
        "unsupported_claim_truth_evaluated": False,
        "attention_quality_evaluated": False,
        "learned_synthesis_performed": False,
        "hypotheses_generated": False,
        "forecast_input_eligible": False,
        "aggregate_eligible": False,
        "skill_claim_eligible": False,
        "prophet_input_eligible": False,
    }
)

SALIENCE_WEIGHTS: Mapping[str, str] = MappingProxyType(
    {
        "standardized_surprise": "0.250000000000000000",
        "change_hazard": "0.200000000000000000",
        "novelty": "0.150000000000000000",
        "disagreement": "0.150000000000000000",
        "materiality": "0.150000000000000000",
        "data_health_deficit": "0.100000000000000000",
    }
)

READ_TOOLS: tuple[str, ...] = (
    "read_attention_queue",
    "read_citation_projection",
    "read_contradictions",
    "read_episode_scope",
    "read_falsifier_audit",
    "read_missingness",
    "read_scorecards",
)

_MAX_REGISTRATION_BYTES = 262_144
_MAX_PACKET_BYTES = 2_097_152
_MAX_SOURCE_BYTES = 65_536
_MAX_AGGREGATE_SOURCE_BYTES = 4_194_304
_MAX_EVIDENCE = 64
_MAX_CLAIMS = 128
_MAX_REFS = 8
_MAX_KINDS = 16
_MAX_CONTRADICTIONS = 128
_MAX_EPISODES = 33
_MAX_STRING_BYTES = 256
_MAX_DEPTH = 16
_MAX_NODES = 16_384

BOUNDS: Mapping[str, int] = MappingProxyType(
    {
        "max_registration_bytes": _MAX_REGISTRATION_BYTES,
        "max_packet_bytes": _MAX_PACKET_BYTES,
        "max_source_bytes": _MAX_SOURCE_BYTES,
        "max_aggregate_source_bytes": _MAX_AGGREGATE_SOURCE_BYTES,
        "max_evidence_cards": _MAX_EVIDENCE,
        "max_claims": _MAX_CLAIMS,
        "max_evidence_card_refs": _MAX_REFS,
        "max_evidence_kinds": _MAX_KINDS,
        "max_contradictions": _MAX_CONTRADICTIONS,
        "max_episodes": _MAX_EPISODES,
        "max_string_bytes": _MAX_STRING_BYTES,
        "max_depth": _MAX_DEPTH,
        "max_nodes": _MAX_NODES,
    }
)

# External W4 dependencies and caller-supplied source bytes are revalidated by
# the exact join boundary.  The unsigned packet cannot carry either check as a
# portable authenticated fact, so every durable coverage claim remains false.
COVERAGE: Mapping[str, bool] = MappingProxyType(
    {
        "w4_exact_join_validated": False,
        "citation_byte_closure_validated": False,
        "evidence_population_complete": False,
        "citation_semantic_entailment_evaluated": False,
        "attention_quality_evaluated": False,
    }
)

_DECIMAL_CONTEXT = Context(
    prec=64,
    rounding=ROUND_HALF_EVEN,
    Emin=-999_999,
    Emax=999_999,
)
_QUANTUM = Decimal("0.000000000000000001")

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_OPAQUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_Q18_UNIT = re.compile(r"(?:0|1)\.[0-9]{18}\Z")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z")
_REGISTRATION_ID = re.compile(r"mmcortexregistration_[a-f0-9]{64}\Z")
_PACKET_ID = re.compile(r"mmcortexpacket_[a-f0-9]{64}\Z")
_FORECAST_ID = re.compile(r"mmforecast_[a-f0-9]{64}\Z")
_TRIAL_ID = re.compile(r"mmtrial_[a-f0-9]{64}\Z")
_RETRIEVAL_ID = re.compile(r"mmretrievalregistration_[a-f0-9]{64}\Z")
_EPISODIC_ID = re.compile(r"mmepisodicretrieval_[a-f0-9]{64}\Z")
_CITATION_ID = re.compile(r"mmcitation_[a-f0-9]{64}\Z")
_EVIDENCE_ID = re.compile(r"mmevidencecard_[a-f0-9]{64}\Z")
_CLAIM_ID = re.compile(r"mmclaim_[a-f0-9]{64}\Z")
_ATTENTION_ID = re.compile(r"mmattentionitem_[a-f0-9]{64}\Z")
_CONTRADICTION_ID = re.compile(r"mmcontradictiongroup_[a-f0-9]{64}\Z")

# Caller-controlled W5 codes and keys must not smuggle an action or authority
# capability through separator, compact, Unicode-compatibility, or camel form.
# Exact cited source bytes are deliberately excluded: closure proves integrity,
# never semantics, authority, or suitability.
_FORBIDDEN_WORDS = frozenset(
    {
        "action",
        "actions",
        "add",
        "added",
        "adding",
        "adds",
        "authority",
        "authoritative",
        "bearish",
        "bearishness",
        "bullish",
        "bullishness",
        "buy",
        "buying",
        "buys",
        "close",
        "closed",
        "closes",
        "closing",
        "direction",
        "directions",
        "escalate",
        "escalated",
        "escalates",
        "escalating",
        "execute",
        "executed",
        "executes",
        "executing",
        "execution",
        "exit",
        "exited",
        "exiting",
        "exits",
        "forecast",
        "forecasted",
        "forecasting",
        "forecasts",
        "gate",
        "gated",
        "gating",
        "hold",
        "holding",
        "holds",
        "label",
        "labels",
        "long",
        "longed",
        "longing",
        "longs",
        "loss",
        "losses",
        "originate",
        "originated",
        "originates",
        "originating",
        "origination",
        "outcome",
        "outcomes",
        "permission",
        "permissions",
        "permitted",
        "pnl",
        "position",
        "positions",
        "profit",
        "profits",
        "promote",
        "promoted",
        "promotes",
        "promoting",
        "promotion",
        "prophet",
        "rank",
        "ranked",
        "ranking",
        "ranks",
        "recommendation",
        "recommendations",
        "recommend",
        "recommended",
        "recommending",
        "recommends",
        "return",
        "returned",
        "returning",
        "returns",
        "select",
        "selected",
        "selecting",
        "selects",
        "sell",
        "selling",
        "sells",
        "short",
        "shorted",
        "shorting",
        "shorts",
        "size",
        "sized",
        "sizing",
        "sizes",
        "target",
        "targeted",
        "targeting",
        "targets",
        "trade",
        "traded",
        "trading",
        "trades",
        "train",
        "trained",
        "training",
        "trains",
        "trim",
        "trimmed",
        "trimming",
        "trims",
        "underweight",
        "veto",
        "vetoed",
        "vetoes",
        "vetoing",
        "write",
        "writes",
        "writing",
        "wrote",
        "overweight",
    }
)
_FORBIDDEN_COMPACT = frozenset(
    {
        "appendoutcome",
        "buysignal",
        "executeaction",
        "forecastcontext",
        "mayappendoutcome",
        "mayescalate",
        "mayexecute",
        "maygate",
        "mayoriginate",
        "mayrank",
        "mayselectoptionscandidate",
        "maysize",
        "maytrade",
        "maytrainprophet",
        "maywriteoptionsepisode",
        "outcomefree",
        "promotioneligible",
        "proposalweight",
        "recommendationengine",
        "sellsignal",
        "trainingeligible",
    }
)
_CAPABILITY_AFFIXES = frozenset(
    {
        "candidate",
        "context",
        "eligible",
        "engine",
        "free",
        "gate",
        "input",
        "may",
        "now",
        "signal",
        "token",
    }
)
_FORBIDDEN_COMPOUNDS = frozenset(
    {
        compound
        for forbidden in _FORBIDDEN_WORDS
        for affix in _CAPABILITY_AFFIXES
        for compound in (f"{affix}{forbidden}", f"{forbidden}{affix}")
    }
)

_REGISTRATION_FIELDS = frozenset(
    {
        "schema",
        "operating_cortex_registration_id",
        "registration_key",
        "registered_at",
        "retrieval_registration_id",
        "trial_registration_id",
        "trial_plan_sha256",
        "required_evidence_kinds",
        "salience_policy",
        "citation_policy",
        "read_tools",
        "bounds",
        "implementation",
        "input_profile",
        "claims",
        "emission_enabled",
        "authority",
    }
)
_PACKET_FIELDS = frozenset(
    {
        "schema",
        "operating_cortex_packet_id",
        "operating_cortex_registration_id",
        "retrieval_registration_id",
        "episodic_retrieval_record_id",
        "trial_registration_id",
        "subject",
        "produced_at",
        "episode_scope",
        "evidence_manifest",
        "attention_queue",
        "contradictions",
        "missingness",
        "falsifier_audit",
        "citation_projection",
        "unsupported_claim_scorecard",
        "attention_quality_scorecard",
        "read_tools",
        "coverage",
        "input_profile",
        "claims",
        "emission_enabled",
        "authority",
    }
)
_SUBJECT_FIELDS = frozenset({"subject_id", "instrument_id"})
_EPISODE_FIELDS = frozenset({"episode_role", "episode_forecast_id", "subject"})
_CITATION_FIELDS = frozenset(
    {
        "citation_id",
        "source_record_ref",
        "source_sha256",
        "source_bytes",
        "span_start_byte",
        "span_end_byte",
        "span_sha256",
        "known_at",
    }
)
_EVIDENCE_FIELDS = frozenset(
    {
        "evidence_card_id",
        "episode_role",
        "episode_forecast_id",
        "subject",
        "evidence_kind",
        "claim_key",
        "stance",
        "known_at",
        "salience_components",
        "citation",
    }
)
_EVIDENCE_INPUT_FIELDS = frozenset({"evidence_card", "exact_source_bytes"})
_CLAIM_FIELDS = frozenset(
    {
        "claim_id",
        "subject",
        "claim_key",
        "stance",
        "evidence_card_refs",
        "falsifier_code",
    }
)
_PROJECTION_FIELDS = frozenset(
    {
        *_CLAIM_FIELDS,
        "status",
        "withholding_reason",
        "citation_ids",
        "semantic_entailment_evaluated",
    }
)


class MarketMemoryOperatingCortexContractError(ValueError):
    """A W5A Operating Cortex value is unsafe, ambiguous, or inauthentic."""


def _fail(message: str) -> NoReturn:
    raise MarketMemoryOperatingCortexContractError(message)


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


def _resource_guard(value: object, *, field: str) -> None:
    nodes = 0

    def utf8_length(text: str, *, text_field: str) -> int:
        try:
            return len(text.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise MarketMemoryOperatingCortexContractError(
                f"{text_field} contains a surrogate code point"
            ) from exc

    def visit(item: object, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > _MAX_NODES:
            _fail(f"{field} exceeds {_MAX_NODES} JSON nodes")
        if depth > _MAX_DEPTH:
            _fail(f"{field} exceeds depth {_MAX_DEPTH}")
        if type(item) is dict:
            for key, child in item.items():
                if (
                    type(key) is not str
                    or utf8_length(key, text_field=f"{field} key") > _MAX_STRING_BYTES
                ):
                    _fail(f"{field} contains an invalid key")
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str:
            if utf8_length(item, text_field=field) > _MAX_STRING_BYTES:
                _fail(
                    f"{field} contains a string longer than {_MAX_STRING_BYTES} bytes"
                )
        elif item is not None and type(item) not in {int, bool}:
            _fail(f"{field} contains a non-JSON scalar")

    visit(value, 0)


def _canonical_bytes(value: object, *, field: str, maximum: int) -> bytes:
    _resource_guard(value, field=field)
    try:
        body = forward.canonical_json_bytes(value)
    except (
        forward.MarketMemoryForwardContractError,
        RecursionError,
        ValueError,
    ) as exc:
        raise MarketMemoryOperatingCortexContractError(
            f"{field} is not canonical JSON"
        ) from exc
    if len(body) > maximum:
        _fail(f"{field} exceeds its canonical byte bound")
    return body


def _detached(value: object, *, field: str, maximum: int) -> dict[str, Any]:
    return _require_dict(
        json.loads(_canonical_bytes(value, field=field, maximum=maximum)), field=field
    )


def _exact_equal(left: object, right: object, *, field: str, maximum: int) -> bool:
    return _canonical_bytes(
        left, field=f"{field} supplied", maximum=maximum
    ) == _canonical_bytes(right, field=f"{field} expected", maximum=maximum)


def _content_id(
    prefix: str, value: Mapping[str, Any], *, field: str, maximum: int
) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return (
        prefix
        + hashlib.sha256(
            _canonical_bytes(core, field=f"{field} preimage", maximum=maximum)
        ).hexdigest()
    )


def _match(value: object, pattern: re.Pattern[str], *, field: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(f"{field} is not canonical")
    return value


def _semantic_forms(text: str) -> tuple[set[str], str, set[str]]:
    normalized = unicodedata.normalize("NFKC", text)
    camel_split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", normalized)
    ordered_words = re.findall(r"[a-z0-9]+", camel_split.casefold())
    words = set(ordered_words)
    compact = "".join(ordered_words)
    contiguous_forms: set[str] = set()
    for start in range(len(ordered_words)):
        joined = ""
        for end in range(start, len(ordered_words)):
            joined += ordered_words[end]
            contiguous_forms.add(joined)
            contiguous_forms.add(re.sub(r"(?:v)?[0-9]+\Z", "", joined))
    return words, compact, contiguous_forms


def _compound_forms(words: set[str]) -> set[str]:
    """Return exact compact lexemes with only a trailing version marker removed."""

    forms = set(words)
    forms.update(re.sub(r"(?:v)?[0-9]+\Z", "", word) for word in words)
    return forms


def _opaque(value: object, *, field: str) -> str:
    if type(value) is not str:
        _fail(f"{field} is not canonical")
    try:
        raw = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise MarketMemoryOperatingCortexContractError(
            f"{field} is not canonical"
        ) from exc
    if len(raw) > 256:
        _fail(f"{field} exceeds its UTF-8 byte bound")
    words, compact, contiguous_forms = _semantic_forms(value)
    if (
        words & _FORBIDDEN_WORDS
        or contiguous_forms & _FORBIDDEN_WORDS
        or any(token in compact for token in _FORBIDDEN_COMPACT)
        or contiguous_forms & _FORBIDDEN_COMPACT
        or contiguous_forms & _FORBIDDEN_COMPOUNDS
        or _compound_forms(words) & _FORBIDDEN_COMPOUNDS
    ):
        _fail(f"{field} contains a forbidden action or authority token")
    return _match(value, _OPAQUE, field=field)


def _dependency_opaque(value: object, *, field: str) -> str:
    return _match(value, _OPAQUE, field=field)


def _sha(value: object, *, field: str) -> str:
    return _match(value, _SHA256, field=field)


def _exact_int(value: object, *, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(f"{field} must be an integer in [{minimum}, {maximum}]")
    return value


def _utc(value: object, *, field: str) -> datetime:
    if type(value) is not str or _UTC.fullmatch(value) is None:
        _fail(f"{field} must be a canonical UTC timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise MarketMemoryOperatingCortexContractError(f"{field} is invalid") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ") != value:
        _fail(f"{field} is not a real canonical UTC timestamp")
    return parsed


def _q18_unit(value: object, *, field: str) -> tuple[str, Decimal]:
    text = _match(value, _Q18_UNIT, field=field)
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise MarketMemoryOperatingCortexContractError(f"{field} is invalid") from exc
    if not number.is_finite() or not Decimal(0) <= number <= Decimal(1):
        _fail(f"{field} must be finite and in [0, 1]")
    if number == Decimal(1) and text != "1.000000000000000000":
        _fail(f"{field} exceeds one")
    return text, number


def _q18_text(value: Decimal, *, field: str) -> str:
    try:
        with localcontext(_DECIMAL_CONTEXT):
            rounded = value.quantize(_QUANTUM)
    except InvalidOperation as exc:
        raise MarketMemoryOperatingCortexContractError(
            f"{field} cannot be represented as q18"
        ) from exc
    text = format(rounded, "f")
    _q18_unit(text, field=field)
    return text


def _clean_subject(value: object, *, field: str) -> dict[str, str]:
    payload = _require_fields(value, _SUBJECT_FIELDS, field=field)
    return {
        "instrument_id": _dependency_opaque(
            payload["instrument_id"], field=f"{field}.instrument_id"
        ),
        "subject_id": _dependency_opaque(
            payload["subject_id"], field=f"{field}.subject_id"
        ),
    }


def _sorted_unique_opaque(
    value: object, *, field: str, minimum: int, maximum: int
) -> list[str]:
    if type(value) is not list or not minimum <= len(value) <= maximum:
        _fail(f"{field} must contain {minimum}..{maximum} values")
    rows = [
        _opaque(item, field=f"{field}[{index}]") for index, item in enumerate(value)
    ]
    if rows != sorted(rows) or len(rows) != len(set(rows)):
        _fail(f"{field} must be sorted and unique")
    return rows


def _claims(value: object) -> dict[str, bool]:
    payload = _require_fields(value, frozenset(CLAIMS), field="claims")
    expected = dict(CLAIMS)
    if any(
        type(payload[name]) is not bool or payload[name] is not required
        for name, required in expected.items()
    ):
        _fail("all W5A evidence and authority claims must remain false")
    return expected


def _coverage(value: object) -> dict[str, bool]:
    payload = _require_fields(value, frozenset(COVERAGE), field="coverage")
    expected = dict(COVERAGE)
    if any(
        type(payload[name]) is not bool or payload[name] is not required
        for name, required in expected.items()
    ):
        _fail("packet coverage differs from the frozen honest coverage block")
    return expected


def _authority(value: object) -> dict[str, Any]:
    expected = dict(forward.AUTHORITY)
    if not _exact_equal(
        value, expected, field="authority", maximum=_MAX_REGISTRATION_BYTES
    ):
        _fail("authority must equal the frozen W2 zero-authority block")
    return expected


def _fixed_salience_policy() -> dict[str, Any]:
    return {
        "components": list(SALIENCE_WEIGHTS),
        "weights": dict(SALIENCE_WEIGHTS),
        "missing_component": "abstain",
        "ordering": "score_desc_then_evidence_card_id_then_abstained_evidence_card_id",
        "numeric_convention": NUMERIC_CONVENTION,
    }


def _fixed_citation_policy() -> dict[str, Any]:
    return {
        "byte_closure": "source_sha256_length_and_half_open_span_sha256",
        "semantic_entailment": "not_evaluated",
        "withholding_precedence": [
            "evidence_reference_missing",
            "evidence_reference_mismatch",
            "required_evidence_kind_missing",
            "semantic_entailment_not_evaluated",
        ],
    }


def _joined_retrieval_registration(
    value: Mapping[str, Any], *, trial_registration: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        return retrieval.validate_retrieval_registration_join(
            value, trial_registration=trial_registration
        )
    except retrieval.MarketMemoryRetrievalContractError as exc:
        raise MarketMemoryOperatingCortexContractError(
            f"exact W4A retrieval registration join failed: {exc}"
        ) from exc


def build_operating_cortex_registration(
    *,
    retrieval_registration: Mapping[str, Any],
    trial_registration: Mapping[str, Any],
    registration_key: str,
    registered_at: str,
    required_evidence_kinds: Sequence[str],
    producer_code_sha256: str,
    producer_config_sha256: str,
) -> dict[str, Any]:
    """Build the frozen inert W5A registration over exact W4A/W2A owners."""

    joined = _joined_retrieval_registration(
        retrieval_registration, trial_registration=trial_registration
    )
    if type(required_evidence_kinds) not in {list, tuple}:
        _fail("required_evidence_kinds must be a list or tuple")
    kinds = _sorted_unique_opaque(
        list(required_evidence_kinds),
        field="required_evidence_kinds",
        minimum=1,
        maximum=_MAX_KINDS,
    )
    safe_registration_key = _opaque(registration_key, field="registration_key")
    payload: dict[str, Any] = {
        "schema": OPERATING_CORTEX_REGISTRATION_SCHEMA,
        "operating_cortex_registration_id": "",
        "registration_key": safe_registration_key,
        "registered_at": registered_at,
        "retrieval_registration_id": joined["retrieval_registration_id"],
        "trial_registration_id": joined["trial_registration_id"],
        "trial_plan_sha256": joined["trial_plan_sha256"],
        "required_evidence_kinds": kinds,
        "salience_policy": _fixed_salience_policy(),
        "citation_policy": _fixed_citation_policy(),
        "read_tools": list(READ_TOOLS),
        "bounds": dict(BOUNDS),
        "implementation": {
            "producer_code_sha256": producer_code_sha256,
            "producer_config_sha256": producer_config_sha256,
        },
        "input_profile": INPUT_PROFILE,
        "claims": dict(CLAIMS),
        "emission_enabled": False,
        "authority": dict(forward.AUTHORITY),
    }
    payload["operating_cortex_registration_id"] = _content_id(
        "mmcortexregistration_",
        payload,
        field="operating_cortex_registration_id",
        maximum=_MAX_REGISTRATION_BYTES,
    )
    return validate_operating_cortex_registration_join(
        payload,
        retrieval_registration=joined,
        trial_registration=trial_registration,
    )


def validate_operating_cortex_registration_record(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one self-authenticating frozen W5A registration."""

    payload = _require_fields(value, _REGISTRATION_FIELDS, field="cortex registration")
    _canonical_bytes(
        payload, field="cortex registration", maximum=_MAX_REGISTRATION_BYTES
    )
    if payload["schema"] != OPERATING_CORTEX_REGISTRATION_SCHEMA:
        _fail("operating cortex registration schema drift")
    registration_id = _match(
        payload["operating_cortex_registration_id"],
        _REGISTRATION_ID,
        field="operating_cortex_registration_id",
    )
    implementation = _require_fields(
        payload["implementation"],
        frozenset({"producer_code_sha256", "producer_config_sha256"}),
        field="implementation",
    )
    salience = _require_fields(
        payload["salience_policy"],
        frozenset(
            {
                "components",
                "weights",
                "missing_component",
                "ordering",
                "numeric_convention",
            }
        ),
        field="salience_policy",
    )
    citation = _require_fields(
        payload["citation_policy"],
        frozenset({"byte_closure", "semantic_entailment", "withholding_precedence"}),
        field="citation_policy",
    )
    bounds = _require_fields(payload["bounds"], frozenset(BOUNDS), field="bounds")
    clean: dict[str, Any] = {
        "schema": OPERATING_CORTEX_REGISTRATION_SCHEMA,
        "operating_cortex_registration_id": registration_id,
        "registration_key": _opaque(
            payload["registration_key"], field="registration_key"
        ),
        "registered_at": _utc(payload["registered_at"], field="registered_at").strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ),
        "retrieval_registration_id": _match(
            payload["retrieval_registration_id"],
            _RETRIEVAL_ID,
            field="retrieval_registration_id",
        ),
        "trial_registration_id": _match(
            payload["trial_registration_id"], _TRIAL_ID, field="trial_registration_id"
        ),
        "trial_plan_sha256": _sha(
            payload["trial_plan_sha256"], field="trial_plan_sha256"
        ),
        "required_evidence_kinds": _sorted_unique_opaque(
            payload["required_evidence_kinds"],
            field="required_evidence_kinds",
            minimum=1,
            maximum=_MAX_KINDS,
        ),
        "salience_policy": dict(salience),
        "citation_policy": dict(citation),
        "read_tools": list(payload["read_tools"])
        if type(payload["read_tools"]) is list
        else payload["read_tools"],
        "bounds": dict(bounds),
        "implementation": {
            "producer_code_sha256": _sha(
                implementation["producer_code_sha256"], field="producer_code_sha256"
            ),
            "producer_config_sha256": _sha(
                implementation["producer_config_sha256"], field="producer_config_sha256"
            ),
        },
        "input_profile": payload["input_profile"],
        "claims": _claims(payload["claims"]),
        "emission_enabled": payload["emission_enabled"],
        "authority": _authority(payload["authority"]),
    }
    if clean["salience_policy"] != _fixed_salience_policy():
        _fail("salience policy differs from the frozen six-component policy")
    if clean["citation_policy"] != _fixed_citation_policy():
        _fail("citation policy differs from the frozen closure policy")
    if clean["read_tools"] != list(READ_TOOLS):
        _fail("read_tools differ from the frozen seven-view surface")
    if clean["bounds"] != dict(BOUNDS):
        _fail("bounds differ from the frozen W5A limits")
    if (
        clean["input_profile"] != INPUT_PROFILE
        or clean["emission_enabled"] is not False
    ):
        _fail("operating cortex must remain synthetic and emission-disabled")
    if not _exact_equal(
        payload, clean, field="cortex registration", maximum=_MAX_REGISTRATION_BYTES
    ):
        _fail("operating cortex registration is not exact canonical JSON")
    expected_id = _content_id(
        "mmcortexregistration_",
        clean,
        field="operating_cortex_registration_id",
        maximum=_MAX_REGISTRATION_BYTES,
    )
    if registration_id != expected_id:
        _fail("operating_cortex_registration_id does not bind canonical content")
    return _detached(
        clean, field="cortex registration", maximum=_MAX_REGISTRATION_BYTES
    )


def validate_operating_cortex_registration_join(
    value: Mapping[str, Any],
    *,
    retrieval_registration: Mapping[str, Any],
    trial_registration: Mapping[str, Any],
) -> dict[str, Any]:
    """Rejoin a W5A registration to its exact W4A and W2A registrations."""

    joined = _joined_retrieval_registration(
        retrieval_registration, trial_registration=trial_registration
    )
    clean = validate_operating_cortex_registration_record(value)
    if clean["retrieval_registration_id"] != joined["retrieval_registration_id"]:
        _fail("cortex registration differs from exact W4A registration id")
    if clean["trial_registration_id"] != joined["trial_registration_id"]:
        _fail("cortex registration differs from exact W2A trial id")
    if clean["trial_plan_sha256"] != joined["trial_plan_sha256"]:
        _fail("cortex registration differs from exact W2A trial-plan bytes")
    if _utc(clean["registered_at"], field="registered_at") < _utc(
        joined["registered_at"], field="retrieval.registered_at"
    ):
        _fail("cortex registration cannot precede its retrieval registration")
    if _utc(clean["registered_at"], field="registered_at") >= _utc(
        trial_registration["splits"]["live_forward_start"],
        field="trial.live_forward_start",
    ):
        _fail("cortex registration must be frozen before W2A live forward")
    return clean


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _strict_json_object(body: bytes, *, field: str, maximum: int) -> dict[str, Any]:
    if type(body) is not bytes or not body or len(body) > maximum:
        _fail(f"{field} body is empty or exceeds its byte bound")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MarketMemoryOperatingCortexContractError(f"{field} is not UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_constant=lambda token: _fail(f"{field} contains non-finite {token}"),
        )
    except MarketMemoryOperatingCortexContractError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise MarketMemoryOperatingCortexContractError(
            f"{field} is not strict JSON"
        ) from exc
    return _require_dict(value, field=field)


def load_operating_cortex_registration_join_json(
    body: bytes,
    *,
    retrieval_registration: Mapping[str, Any],
    trial_registration: Mapping[str, Any],
) -> dict[str, Any]:
    """Strictly load and rejoin one W5A registration."""

    return validate_operating_cortex_registration_join(
        _strict_json_object(
            body, field="cortex registration", maximum=_MAX_REGISTRATION_BYTES
        ),
        retrieval_registration=retrieval_registration,
        trial_registration=trial_registration,
    )


def _validate_w4_join(
    episodic_retrieval_record: Mapping[str, Any],
    *,
    retrieval_registration: Mapping[str, Any],
    trial_registration: Mapping[str, Any],
    query_state_snapshot: Mapping[str, Any],
    query_forecast_record: Mapping[str, Any],
    query_exact_context_bytes: bytes,
    query_coordinates: Mapping[str, str | None],
    candidate_inputs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    try:
        return retrieval.validate_episodic_retrieval_record_join(
            episodic_retrieval_record,
            retrieval_registration=retrieval_registration,
            trial_registration=trial_registration,
            query_state_snapshot=query_state_snapshot,
            query_forecast_record=query_forecast_record,
            query_exact_context_bytes=query_exact_context_bytes,
            query_coordinates=query_coordinates,
            candidate_inputs=candidate_inputs,
        )
    except retrieval.MarketMemoryRetrievalContractError as exc:
        raise MarketMemoryOperatingCortexContractError(
            f"exact W4A episodic retrieval join failed: {exc}"
        ) from exc


def _episode_scope_from_record(
    episodic_record: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    query = episodic_record["query"]
    subject = _clean_subject(query["subject"], field="W4 query subject")
    scope = [
        {
            "episode_role": "query",
            "episode_forecast_id": query["forecast_id"],
            "subject": subject,
        }
    ]
    cutoffs = {query["forecast_id"]: query["decision_cutoff"]}
    candidates = {row["forecast_id"]: row for row in episodic_record["candidates"]}
    for forecast_id in episodic_record["selected_forecast_ids"]:
        candidate = candidates.get(forecast_id)
        if candidate is None:
            _fail("W4 selected forecast is absent from its candidate audit")
        candidate_subject = _clean_subject(
            candidate["subject"], field="W4 analogue subject"
        )
        if candidate_subject != subject:
            _fail("W4 episode scope does not retain the exact query subject")
        scope.append(
            {
                "episode_role": "analogue",
                "episode_forecast_id": forecast_id,
                "subject": candidate_subject,
            }
        )
        cutoffs[forecast_id] = candidate["decision_cutoff"]
    if len(scope) > _MAX_EPISODES or len(
        {row["episode_forecast_id"] for row in scope}
    ) != len(scope):
        _fail("exact W4A episode scope is invalid or exceeds 33 rows")
    return scope, cutoffs


def _clean_episode_scope(
    value: object, *, packet_subject: Mapping[str, str]
) -> list[dict[str, Any]]:
    if type(value) is not list or not 1 <= len(value) <= _MAX_EPISODES:
        _fail("episode_scope must contain 1..33 rows")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        row = _require_fields(raw, _EPISODE_FIELDS, field=f"episode_scope[{index}]")
        role = row["episode_role"]
        if type(role) is not str or role not in ("query", "analogue"):
            _fail("episode_role must be query or analogue")
        if (index == 0) != (role == "query"):
            _fail("episode_scope must contain exactly one leading query row")
        subject = _clean_subject(
            row["subject"], field=f"episode_scope[{index}].subject"
        )
        if subject != dict(packet_subject):
            _fail("episode_scope subject differs from exact packet subject")
        rows.append(
            {
                "episode_role": role,
                "episode_forecast_id": _match(
                    row["episode_forecast_id"],
                    _FORECAST_ID,
                    field=f"episode_scope[{index}].episode_forecast_id",
                ),
                "subject": subject,
            }
        )
    ids = [row["episode_forecast_id"] for row in rows]
    if len(ids) != len(set(ids)):
        _fail("episode_scope forecast ids must be unique")
    return rows


def _clean_citation(
    value: object,
    *,
    field: str,
    exact_source_bytes: bytes | None,
) -> dict[str, Any]:
    row = _require_fields(value, _CITATION_FIELDS, field=field)
    source_ref = _opaque(row["source_record_ref"], field=f"{field}.source_record_ref")
    known_at = _utc(row["known_at"], field=f"{field}.known_at").strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    start = _exact_int(
        row["span_start_byte"],
        field=f"{field}.span_start_byte",
        minimum=0,
        maximum=_MAX_SOURCE_BYTES,
    )
    if exact_source_bytes is None:
        source_length = _exact_int(
            row["source_bytes"],
            field=f"{field}.source_bytes",
            minimum=1,
            maximum=_MAX_SOURCE_BYTES,
        )
        source_sha = _sha(row["source_sha256"], field=f"{field}.source_sha256")
        span_sha = _sha(row["span_sha256"], field=f"{field}.span_sha256")
    else:
        if type(exact_source_bytes) is not bytes or not exact_source_bytes:
            _fail(f"{field} exact_source_bytes must contain 1..64 KiB bytes")
        if len(exact_source_bytes) > _MAX_SOURCE_BYTES:
            _fail(f"{field} exact_source_bytes exceeds 64 KiB")
        source_length = len(exact_source_bytes)
        source_sha = hashlib.sha256(exact_source_bytes).hexdigest()
        supplied_source_sha = row["source_sha256"]
        if type(supplied_source_sha) is not str or supplied_source_sha not in (
            "",
            source_sha,
        ):
            _fail(f"{field}.source_sha256 differs from exact source bytes")
        supplied_source_length = row["source_bytes"]
        if type(supplied_source_length) is not int or supplied_source_length not in (
            0,
            source_length,
        ):
            _fail(f"{field}.source_bytes differs from exact source length")
        span_sha = ""
    end = _exact_int(
        row["span_end_byte"],
        field=f"{field}.span_end_byte",
        minimum=1,
        maximum=source_length,
    )
    if start >= end:
        _fail("citation spans must be non-empty half-open byte intervals")
    if exact_source_bytes is not None:
        span_sha = hashlib.sha256(exact_source_bytes[start:end]).hexdigest()
        supplied_span_sha = row["span_sha256"]
        if type(supplied_span_sha) is not str or supplied_span_sha not in (
            "",
            span_sha,
        ):
            _fail(f"{field}.span_sha256 differs from exact span bytes")
    clean = {
        "citation_id": "",
        "source_record_ref": source_ref,
        "source_sha256": source_sha,
        "source_bytes": source_length,
        "span_start_byte": start,
        "span_end_byte": end,
        "span_sha256": span_sha,
        "known_at": known_at,
    }
    expected_id = _content_id(
        "mmcitation_", clean, field="citation_id", maximum=_MAX_SOURCE_BYTES * 2
    )
    supplied_id = row["citation_id"]
    if type(supplied_id) is not str or supplied_id not in ("", expected_id):
        _fail(f"{field}.citation_id does not bind canonical citation content")
    clean["citation_id"] = expected_id
    return clean


def _clean_evidence_card(
    value: object,
    *,
    field: str,
    scope_by_id: Mapping[str, Mapping[str, Any]],
    exact_source_bytes: bytes | None,
    cutoff_by_id: Mapping[str, str] | None,
) -> dict[str, Any]:
    row = _require_fields(value, _EVIDENCE_FIELDS, field=field)
    role = row["episode_role"]
    if type(role) is not str or role not in ("query", "analogue"):
        _fail(f"{field}.episode_role must be query or analogue")
    episode_id = _match(
        row["episode_forecast_id"],
        _FORECAST_ID,
        field=f"{field}.episode_forecast_id",
    )
    episode = scope_by_id.get(episode_id)
    if episode is None or episode["episode_role"] != role:
        _fail(f"{field} differs from exact W4 episode identity or role")
    subject = _clean_subject(row["subject"], field=f"{field}.subject")
    if subject != episode["subject"]:
        _fail(f"{field}.subject differs from exact W4 subject")
    known_at = _utc(row["known_at"], field=f"{field}.known_at").strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    if cutoff_by_id is not None and _utc(known_at, field=f"{field}.known_at") > _utc(
        cutoff_by_id[episode_id], field="episode.decision_cutoff"
    ):
        _fail(f"{field}.known_at exceeds its exact W4 episode decision cutoff")
    stance = row["stance"]
    if type(stance) is not str or stance not in (
        "supports",
        "challenges",
        "neutral",
    ):
        _fail(f"{field}.stance must be supports, challenges, or neutral")
    components = _require_dict(
        row["salience_components"], field=f"{field}.salience_components"
    )
    if set(components) != set(SALIENCE_WEIGHTS):
        _fail(f"{field}.salience_components differ from the frozen six names")
    clean_components: dict[str, str | None] = {}
    for name in SALIENCE_WEIGHTS:
        raw = components[name]
        clean_components[name] = (
            None
            if raw is None
            else _q18_unit(raw, field=f"{field}.salience_components.{name}")[0]
        )
    citation = _clean_citation(
        row["citation"],
        field=f"{field}.citation",
        exact_source_bytes=exact_source_bytes,
    )
    if citation["known_at"] != known_at:
        _fail(f"{field}.citation known_at must equal evidence known_at")
    clean: dict[str, Any] = {
        "evidence_card_id": "",
        "episode_role": role,
        "episode_forecast_id": episode_id,
        "subject": subject,
        "evidence_kind": _opaque(row["evidence_kind"], field=f"{field}.evidence_kind"),
        "claim_key": _opaque(row["claim_key"], field=f"{field}.claim_key"),
        "stance": stance,
        "known_at": known_at,
        "salience_components": clean_components,
        "citation": citation,
    }
    expected_id = _content_id(
        "mmevidencecard_",
        clean,
        field="evidence_card_id",
        maximum=_MAX_PACKET_BYTES,
    )
    supplied_id = row["evidence_card_id"]
    if type(supplied_id) is not str or supplied_id not in ("", expected_id):
        _fail(f"{field}.evidence_card_id does not bind canonical evidence content")
    clean["evidence_card_id"] = expected_id
    return clean


def _clean_evidence_inputs(
    value: Sequence[Mapping[str, Any]],
    *,
    episode_scope: Sequence[Mapping[str, Any]],
    cutoff_by_id: Mapping[str, str],
) -> list[dict[str, Any]]:
    if type(value) not in {list, tuple} or len(value) > _MAX_EVIDENCE:
        _fail("evidence_inputs must contain at most 64 wrappers")
    scope_by_id = {row["episode_forecast_id"]: row for row in episode_scope}
    cards: list[dict[str, Any]] = []
    source_refs: list[str] = []
    aggregate = 0
    for index, raw in enumerate(value):
        wrapper = _require_fields(
            raw, _EVIDENCE_INPUT_FIELDS, field=f"evidence_inputs[{index}]"
        )
        source = wrapper["exact_source_bytes"]
        if type(source) is not bytes or not source or len(source) > _MAX_SOURCE_BYTES:
            _fail("each evidence input must supply 1..64 KiB exact source bytes")
        aggregate += len(source)
        if aggregate > _MAX_AGGREGATE_SOURCE_BYTES:
            _fail("aggregate exact source bytes exceed 4 MiB")
        card = _clean_evidence_card(
            wrapper["evidence_card"],
            field=f"evidence_inputs[{index}].evidence_card",
            scope_by_id=scope_by_id,
            exact_source_bytes=source,
            cutoff_by_id=cutoff_by_id,
        )
        source_refs.append(card["citation"]["source_record_ref"])
        cards.append(card)
    if len(source_refs) != len(set(source_refs)):
        _fail("evidence_inputs contain duplicate exact source wrappers")
    cards.sort(key=lambda row: row["evidence_card_id"])
    ids = [row["evidence_card_id"] for row in cards]
    if len(ids) != len(set(ids)):
        _fail("evidence_inputs contain duplicate evidence cards")
    return cards


def _clean_evidence_manifest(
    value: object, *, episode_scope: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    if type(value) is not list or len(value) > _MAX_EVIDENCE:
        _fail("evidence_manifest must contain at most 64 cards")
    scope_by_id = {row["episode_forecast_id"]: row for row in episode_scope}
    cards = [
        _clean_evidence_card(
            raw,
            field=f"evidence_manifest[{index}]",
            scope_by_id=scope_by_id,
            exact_source_bytes=None,
            cutoff_by_id=None,
        )
        for index, raw in enumerate(value)
    ]
    ids = [row["evidence_card_id"] for row in cards]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        _fail("evidence_manifest must be sorted by unique evidence_card_id")
    refs = [row["citation"]["source_record_ref"] for row in cards]
    if len(refs) != len(set(refs)):
        _fail("evidence_manifest contains duplicate source_record_ref wrappers")
    return cards


def _clean_claim_card(
    value: object, *, field: str, packet_subject: Mapping[str, str]
) -> dict[str, Any]:
    row = _require_fields(value, _CLAIM_FIELDS, field=field)
    subject = _clean_subject(row["subject"], field=f"{field}.subject")
    if subject != dict(packet_subject):
        _fail(f"{field}.subject differs from exact W4 packet subject")
    stance = row["stance"]
    if type(stance) is not str or stance not in (
        "supports",
        "challenges",
        "neutral",
    ):
        _fail(f"{field}.stance must be supports, challenges, or neutral")
    refs_raw = row["evidence_card_refs"]
    if type(refs_raw) is not list or len(refs_raw) > _MAX_REFS:
        _fail(f"{field}.evidence_card_refs must contain 0..8 values")
    refs = [
        _match(item, _EVIDENCE_ID, field=f"{field}.evidence_card_refs[{index}]")
        for index, item in enumerate(refs_raw)
    ]
    if refs != sorted(refs) or len(refs) != len(set(refs)):
        _fail(f"{field}.evidence_card_refs must be sorted and unique")
    falsifier = row["falsifier_code"]
    if falsifier is not None:
        falsifier = _opaque(falsifier, field=f"{field}.falsifier_code")
    clean: dict[str, Any] = {
        "claim_id": "",
        "subject": subject,
        "claim_key": _opaque(row["claim_key"], field=f"{field}.claim_key"),
        "stance": stance,
        "evidence_card_refs": refs,
        "falsifier_code": falsifier,
    }
    expected_id = _content_id(
        "mmclaim_", clean, field="claim_id", maximum=_MAX_PACKET_BYTES
    )
    supplied_id = row["claim_id"]
    if type(supplied_id) is not str or supplied_id not in ("", expected_id):
        _fail(f"{field}.claim_id does not bind canonical claim content")
    clean["claim_id"] = expected_id
    return clean


def _clean_claim_cards(
    value: Sequence[Mapping[str, Any]], *, packet_subject: Mapping[str, str]
) -> list[dict[str, Any]]:
    if type(value) not in {list, tuple} or len(value) > _MAX_CLAIMS:
        _fail("claim_cards must contain at most 128 rows")
    rows = [
        _clean_claim_card(
            raw, field=f"claim_cards[{index}]", packet_subject=packet_subject
        )
        for index, raw in enumerate(value)
    ]
    rows.sort(key=lambda row: row["claim_id"])
    ids = [row["claim_id"] for row in rows]
    if len(ids) != len(set(ids)):
        _fail("claim_cards contain duplicate claims")
    return rows


def _attention(evidence: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    abstained: list[dict[str, Any]] = []
    for evidence_card in evidence:
        components = evidence_card["salience_components"]
        if any(components[name] is None for name in SALIENCE_WEIGHTS):
            core: dict[str, Any] = {
                "attention_item_id": "",
                "evidence_card_id": evidence_card["evidence_card_id"],
                "status": "abstained",
                "reason": "missing_salience_component",
                "salience_score_q18": None,
            }
            core["attention_item_id"] = _content_id(
                "mmattentionitem_",
                core,
                field="attention_item_id",
                maximum=_MAX_PACKET_BYTES,
            )
            abstained.append(core)
            continue
        with localcontext(_DECIMAL_CONTEXT):
            total = sum(
                (
                    Decimal(components[name]) * Decimal(weight)
                    for name, weight in SALIENCE_WEIGHTS.items()
                ),
                Decimal(0),
            )
        core = {
            "attention_item_id": "",
            "evidence_card_id": evidence_card["evidence_card_id"],
            "status": "scored",
            "reason": None,
            "salience_score_q18": _q18_text(total, field="salience_score_q18"),
        }
        core["attention_item_id"] = _content_id(
            "mmattentionitem_",
            core,
            field="attention_item_id",
            maximum=_MAX_PACKET_BYTES,
        )
        scored.append(core)
    # q18 unit strings have fixed width and lexical numeric order.  Two stable
    # string sorts avoid every dependency on the process-global Decimal context.
    scored.sort(key=lambda row: row["evidence_card_id"])
    scored.sort(key=lambda row: row["salience_score_q18"], reverse=True)
    abstained.sort(key=lambda row: row["evidence_card_id"])
    return scored + abstained


def _contradictions(claims: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], dict[str, list[str]]] = {}
    subjects: dict[tuple[str, str, str], dict[str, str]] = {}
    for claim in claims:
        subject = claim["subject"]
        key = (subject["subject_id"], subject["instrument_id"], claim["claim_key"])
        subjects[key] = dict(subject)
        group = groups.setdefault(key, {"supports": [], "challenges": []})
        if claim["stance"] in group:
            group[claim["stance"]].append(claim["claim_id"])
    rows: list[dict[str, Any]] = []
    for key in sorted(groups):
        group = groups[key]
        if not group["supports"] or not group["challenges"]:
            continue
        row: dict[str, Any] = {
            "contradiction_group_id": "",
            "subject": subjects[key],
            "claim_key": key[2],
            "supporting_claim_ids": sorted(group["supports"]),
            "challenging_claim_ids": sorted(group["challenges"]),
            "status": "structural_conflict",
        }
        row["contradiction_group_id"] = _content_id(
            "mmcontradictiongroup_",
            row,
            field="contradiction_group_id",
            maximum=_MAX_PACKET_BYTES,
        )
        rows.append(row)
    if len(rows) > _MAX_CONTRADICTIONS:
        _fail("contradictions exceed the frozen 128-row bound")
    rows.sort(key=lambda row: row["contradiction_group_id"])
    return rows


def _missingness(
    evidence: Sequence[Mapping[str, Any]], required_kinds: Sequence[str]
) -> list[dict[str, Any]]:
    supplied = {row["evidence_kind"] for row in evidence}
    return [
        {
            "evidence_kind": kind,
            "status": "present" if kind in supplied else "missing",
            "scope": "supplied_evidence_manifest_only",
        }
        for kind in required_kinds
    ]


def _falsifier_audit(claims: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "claim_id": claim["claim_id"],
            "falsifier_code": claim["falsifier_code"],
            "status": "not_registered"
            if claim["falsifier_code"] is None
            else "registered",
            "generation_performed": False,
        }
        for claim in claims
    ]


_STRUCTURAL_REASONS = (
    "evidence_reference_missing",
    "evidence_reference_mismatch",
    "required_evidence_kind_missing",
)


def _citation_projection(
    claims: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    required_kinds: Sequence[str],
) -> list[dict[str, Any]]:
    evidence_by_id = {row["evidence_card_id"]: row for row in evidence}
    rows: list[dict[str, Any]] = []
    for claim in claims:
        referenced = [evidence_by_id.get(ref) for ref in claim["evidence_card_refs"]]
        reason: str | None = None
        if not referenced or any(row is None for row in referenced):
            reason = "evidence_reference_missing"
        if reason is None and any(
            row["subject"] != claim["subject"]
            or row["claim_key"] != claim["claim_key"]
            or row["stance"] != claim["stance"]
            for row in referenced
        ):
            reason = "evidence_reference_mismatch"
        present_kinds = {row["evidence_kind"] for row in referenced if row is not None}
        if reason is None and not set(required_kinds) <= present_kinds:
            reason = "required_evidence_kind_missing"
        structurally_included = reason is None
        rows.append(
            {
                **copy.deepcopy(dict(claim)),
                "status": "included_structural_only"
                if structurally_included
                else "withheld",
                "withholding_reason": "semantic_entailment_not_evaluated"
                if structurally_included
                else reason,
                "citation_ids": sorted(
                    row["citation"]["citation_id"]
                    for row in referenced
                    if row is not None and row.get("citation") is not None
                )
                if structurally_included
                else [],
                "semantic_entailment_evaluated": False,
            }
        )
    return rows


def _unsupported_claim_scorecard(
    projection: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    total = len(projection)
    counts = {
        reason: sum(row["withholding_reason"] == reason for row in projection)
        for reason in _STRUCTURAL_REASONS
    }
    withheld = sum(counts.values())
    included = total - withheld
    rate: str | None = None
    if total:
        with localcontext(_DECIMAL_CONTEXT):
            rate = _q18_text(
                Decimal(withheld) / Decimal(total),
                field="structural_unsupported_rate_q18",
            )
    return {
        "status": "structural_only",
        "total": total,
        "included": included,
        "withheld": withheld,
        "counts_by_reason": counts,
        "structural_unsupported_rate_q18": rate,
    }


def _attention_quality_scorecard() -> dict[str, Any]:
    return {
        "status": "not_evaluated",
        "reason": "no_preregistered_attention_outcomes",
        "graded_items": 0,
        "precision_q18": None,
        "recall_q18": None,
        "false_positive_rate_q18": None,
        "ndcg_q18": None,
    }


def _derive_packet(
    *,
    registration: Mapping[str, Any],
    episodic_record: Mapping[str, Any],
    evidence_inputs: Sequence[Mapping[str, Any]],
    claim_cards: Sequence[Mapping[str, Any]],
    produced_at: str,
) -> dict[str, Any]:
    produced = _utc(produced_at, field="produced_at")
    retrieved = _utc(episodic_record["retrieved_at"], field="retrieved_at")
    if produced < retrieved:
        _fail("produced_at cannot precede exact W4A retrieval")
    episode_scope, cutoffs = _episode_scope_from_record(episodic_record)
    subject = episode_scope[0]["subject"]
    evidence = _clean_evidence_inputs(
        evidence_inputs, episode_scope=episode_scope, cutoff_by_id=cutoffs
    )
    claims = _clean_claim_cards(claim_cards, packet_subject=subject)
    projection = _citation_projection(
        claims, evidence, registration["required_evidence_kinds"]
    )
    return {
        "schema": OPERATING_CORTEX_PACKET_SCHEMA,
        "operating_cortex_packet_id": "",
        "operating_cortex_registration_id": registration[
            "operating_cortex_registration_id"
        ],
        "retrieval_registration_id": episodic_record["retrieval_registration_id"],
        "episodic_retrieval_record_id": episodic_record["episodic_retrieval_record_id"],
        "trial_registration_id": episodic_record["trial_registration_id"],
        "subject": subject,
        "produced_at": produced_at,
        "episode_scope": episode_scope,
        "evidence_manifest": evidence,
        "attention_queue": _attention(evidence),
        "contradictions": _contradictions(claims),
        "missingness": _missingness(evidence, registration["required_evidence_kinds"]),
        "falsifier_audit": _falsifier_audit(claims),
        "citation_projection": projection,
        "unsupported_claim_scorecard": _unsupported_claim_scorecard(projection),
        "attention_quality_scorecard": _attention_quality_scorecard(),
        "read_tools": list(READ_TOOLS),
        "coverage": dict(COVERAGE),
        "input_profile": INPUT_PROFILE,
        "claims": dict(CLAIMS),
        "emission_enabled": False,
        "authority": dict(forward.AUTHORITY),
    }


def build_operating_cortex_packet(
    *,
    operating_cortex_registration: Mapping[str, Any],
    retrieval_registration: Mapping[str, Any],
    trial_registration: Mapping[str, Any],
    episodic_retrieval_record: Mapping[str, Any],
    query_state_snapshot: Mapping[str, Any],
    query_forecast_record: Mapping[str, Any],
    query_exact_context_bytes: bytes,
    query_coordinates: Mapping[str, str | None],
    candidate_inputs: Sequence[Mapping[str, Any]],
    evidence_inputs: Sequence[Mapping[str, Any]],
    claim_cards: Sequence[Mapping[str, Any]],
    produced_at: str,
) -> dict[str, Any]:
    """Build one inert packet after revalidating the complete W4/W2 join."""

    episodic = _validate_w4_join(
        episodic_retrieval_record,
        retrieval_registration=retrieval_registration,
        trial_registration=trial_registration,
        query_state_snapshot=query_state_snapshot,
        query_forecast_record=query_forecast_record,
        query_exact_context_bytes=query_exact_context_bytes,
        query_coordinates=query_coordinates,
        candidate_inputs=candidate_inputs,
    )
    registration = validate_operating_cortex_registration_join(
        operating_cortex_registration,
        retrieval_registration=retrieval_registration,
        trial_registration=trial_registration,
    )
    if (
        registration["retrieval_registration_id"]
        != episodic["retrieval_registration_id"]
    ):
        _fail("cortex registration and packet do not share exact W4A registration")
    if registration["trial_registration_id"] != episodic["trial_registration_id"]:
        _fail("cortex registration and packet do not share exact W2A trial")
    payload = _derive_packet(
        registration=registration,
        episodic_record=episodic,
        evidence_inputs=evidence_inputs,
        claim_cards=claim_cards,
        produced_at=produced_at,
    )
    payload["operating_cortex_packet_id"] = _content_id(
        "mmcortexpacket_",
        payload,
        field="operating_cortex_packet_id",
        maximum=_MAX_PACKET_BYTES,
    )
    return validate_operating_cortex_packet(payload)


def _projection_claims(
    value: object, *, packet_subject: Mapping[str, str]
) -> list[dict[str, Any]]:
    if type(value) is not list or len(value) > _MAX_CLAIMS:
        _fail("citation_projection must contain at most 128 rows")
    claims: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        row = _require_fields(
            raw, _PROJECTION_FIELDS, field=f"citation_projection[{index}]"
        )
        claim = _clean_claim_card(
            {key: row[key] for key in _CLAIM_FIELDS},
            field=f"citation_projection[{index}].claim",
            packet_subject=packet_subject,
        )
        claims.append(claim)
    ids = [row["claim_id"] for row in claims]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        _fail("citation_projection must be sorted by unique claim_id")
    return claims


def validate_operating_cortex_packet(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate packet identity and every self-contained structural projection."""

    payload = _require_fields(value, _PACKET_FIELDS, field="operating cortex packet")
    _canonical_bytes(
        payload, field="operating cortex packet", maximum=_MAX_PACKET_BYTES
    )
    if payload["schema"] != OPERATING_CORTEX_PACKET_SCHEMA:
        _fail("operating cortex packet schema drift")
    packet_id = _match(
        payload["operating_cortex_packet_id"],
        _PACKET_ID,
        field="operating_cortex_packet_id",
    )
    _match(
        payload["operating_cortex_registration_id"],
        _REGISTRATION_ID,
        field="operating_cortex_registration_id",
    )
    _match(
        payload["retrieval_registration_id"],
        _RETRIEVAL_ID,
        field="retrieval_registration_id",
    )
    _match(
        payload["episodic_retrieval_record_id"],
        _EPISODIC_ID,
        field="episodic_retrieval_record_id",
    )
    _match(payload["trial_registration_id"], _TRIAL_ID, field="trial_registration_id")
    _utc(payload["produced_at"], field="produced_at")
    subject = _clean_subject(payload["subject"], field="packet.subject")
    scope = _clean_episode_scope(payload["episode_scope"], packet_subject=subject)
    evidence = _clean_evidence_manifest(
        payload["evidence_manifest"], episode_scope=scope
    )
    claims = _projection_claims(payload["citation_projection"], packet_subject=subject)
    missing_raw = payload["missingness"]
    if type(missing_raw) is not list or not 1 <= len(missing_raw) <= _MAX_KINDS:
        _fail("missingness must pin 1..16 required evidence kinds")
    required_kinds: list[str] = []
    for index, raw in enumerate(missing_raw):
        row = _require_fields(
            raw,
            frozenset({"evidence_kind", "status", "scope"}),
            field=f"missingness[{index}]",
        )
        required_kinds.append(
            _opaque(row["evidence_kind"], field=f"missingness[{index}].evidence_kind")
        )
    if required_kinds != sorted(required_kinds) or len(required_kinds) != len(
        set(required_kinds)
    ):
        _fail("missingness evidence kinds must be sorted and unique")
    expected_projection = _citation_projection(claims, evidence, required_kinds)
    expected_sections = {
        "episode_scope": scope,
        "evidence_manifest": evidence,
        "attention_queue": _attention(evidence),
        "contradictions": _contradictions(claims),
        "missingness": _missingness(evidence, required_kinds),
        "falsifier_audit": _falsifier_audit(claims),
        "citation_projection": expected_projection,
        "unsupported_claim_scorecard": _unsupported_claim_scorecard(
            expected_projection
        ),
        "attention_quality_scorecard": _attention_quality_scorecard(),
    }
    for name, expected in expected_sections.items():
        if not _exact_equal(
            payload[name],
            expected,
            field=f"packet internal {name}",
            maximum=_MAX_PACKET_BYTES,
        ):
            _fail(f"packet {name} differs from its content-bound inputs")
    if payload["read_tools"] != list(READ_TOOLS):
        _fail("packet read_tools differ from the frozen seven-view surface")
    _coverage(payload["coverage"])
    if (
        payload["input_profile"] != INPUT_PROFILE
        or payload["emission_enabled"] is not False
    ):
        _fail("operating cortex packet must remain synthetic and emission-disabled")
    _claims(payload["claims"])
    _authority(payload["authority"])
    expected_id = _content_id(
        "mmcortexpacket_",
        payload,
        field="operating_cortex_packet_id",
        maximum=_MAX_PACKET_BYTES,
    )
    if packet_id != expected_id:
        _fail("operating_cortex_packet_id does not bind canonical content")
    return _detached(
        payload, field="operating cortex packet", maximum=_MAX_PACKET_BYTES
    )


def validate_operating_cortex_packet_join(
    value: Mapping[str, Any],
    *,
    operating_cortex_registration: Mapping[str, Any],
    retrieval_registration: Mapping[str, Any],
    trial_registration: Mapping[str, Any],
    episodic_retrieval_record: Mapping[str, Any],
    query_state_snapshot: Mapping[str, Any],
    query_forecast_record: Mapping[str, Any],
    query_exact_context_bytes: bytes,
    query_coordinates: Mapping[str, str | None],
    candidate_inputs: Sequence[Mapping[str, Any]],
    evidence_inputs: Sequence[Mapping[str, Any]],
    claim_cards: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Rebuild a packet from every exact dependency and require byte identity."""

    clean = validate_operating_cortex_packet(value)
    expected = build_operating_cortex_packet(
        operating_cortex_registration=operating_cortex_registration,
        retrieval_registration=retrieval_registration,
        trial_registration=trial_registration,
        episodic_retrieval_record=episodic_retrieval_record,
        query_state_snapshot=query_state_snapshot,
        query_forecast_record=query_forecast_record,
        query_exact_context_bytes=query_exact_context_bytes,
        query_coordinates=query_coordinates,
        candidate_inputs=candidate_inputs,
        evidence_inputs=evidence_inputs,
        claim_cards=claim_cards,
        produced_at=clean["produced_at"],
    )
    if not _exact_equal(
        clean, expected, field="operating cortex exact joins", maximum=_MAX_PACKET_BYTES
    ):
        _fail("operating cortex packet differs from exact dependencies")
    return clean


def load_operating_cortex_packet_join_json(
    body: bytes,
    *,
    operating_cortex_registration: Mapping[str, Any],
    retrieval_registration: Mapping[str, Any],
    trial_registration: Mapping[str, Any],
    episodic_retrieval_record: Mapping[str, Any],
    query_state_snapshot: Mapping[str, Any],
    query_forecast_record: Mapping[str, Any],
    query_exact_context_bytes: bytes,
    query_coordinates: Mapping[str, str | None],
    candidate_inputs: Sequence[Mapping[str, Any]],
    evidence_inputs: Sequence[Mapping[str, Any]],
    claim_cards: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Strictly load a packet and fully revalidate every exact dependency."""

    return validate_operating_cortex_packet_join(
        _strict_json_object(
            body, field="operating cortex packet", maximum=_MAX_PACKET_BYTES
        ),
        operating_cortex_registration=operating_cortex_registration,
        retrieval_registration=retrieval_registration,
        trial_registration=trial_registration,
        episodic_retrieval_record=episodic_retrieval_record,
        query_state_snapshot=query_state_snapshot,
        query_forecast_record=query_forecast_record,
        query_exact_context_bytes=query_exact_context_bytes,
        query_coordinates=query_coordinates,
        candidate_inputs=candidate_inputs,
        evidence_inputs=evidence_inputs,
        claim_cards=claim_cards,
    )


class OperatingCortexReader:
    """Immutable capability-limited reader over exactly seven detached views."""

    __slots__ = (
        "__attention_queue",
        "__citation_projection",
        "__contradictions",
        "__episode_scope",
        "__falsifier_audit",
        "__missingness",
        "__scorecards",
        "__sealed",
    )

    def __init__(self, packet: Mapping[str, Any], **join_dependencies: Any) -> None:
        clean = validate_operating_cortex_packet_join(packet, **join_dependencies)
        views = {
            "attention_queue": clean["attention_queue"],
            "citation_projection": clean["citation_projection"],
            "contradictions": clean["contradictions"],
            "episode_scope": clean["episode_scope"],
            "falsifier_audit": clean["falsifier_audit"],
            "missingness": clean["missingness"],
            "scorecards": {
                "unsupported_claim_scorecard": clean["unsupported_claim_scorecard"],
                "attention_quality_scorecard": clean["attention_quality_scorecard"],
            },
        }
        for name, value in views.items():
            object.__setattr__(
                self,
                f"_OperatingCortexReader__{name}",
                _canonical_bytes(
                    value, field=f"reader {name}", maximum=_MAX_PACKET_BYTES
                ),
            )
        object.__setattr__(self, "_OperatingCortexReader__sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_OperatingCortexReader__sealed", False):
            raise AttributeError("OperatingCortexReader is immutable")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        raise AttributeError("OperatingCortexReader is immutable")

    def read_attention_queue(self) -> list[dict[str, Any]]:
        return json.loads(self.__attention_queue)

    def read_episode_scope(self) -> list[dict[str, Any]]:
        return json.loads(self.__episode_scope)

    def read_contradictions(self) -> list[dict[str, Any]]:
        return json.loads(self.__contradictions)

    def read_missingness(self) -> list[dict[str, Any]]:
        return json.loads(self.__missingness)

    def read_falsifier_audit(self) -> list[dict[str, Any]]:
        return json.loads(self.__falsifier_audit)

    def read_citation_projection(self) -> list[dict[str, Any]]:
        return json.loads(self.__citation_projection)

    def read_scorecards(self) -> dict[str, Any]:
        return json.loads(self.__scorecards)


__all__ = [
    "BOUNDS",
    "CLAIMS",
    "COVERAGE",
    "INPUT_PROFILE",
    "NUMERIC_CONVENTION",
    "OPERATING_CORTEX_PACKET_SCHEMA",
    "OPERATING_CORTEX_REGISTRATION_SCHEMA",
    "READ_TOOLS",
    "SALIENCE_WEIGHTS",
    "MarketMemoryOperatingCortexContractError",
    "OperatingCortexReader",
    "build_operating_cortex_packet",
    "build_operating_cortex_registration",
    "load_operating_cortex_packet_join_json",
    "load_operating_cortex_registration_join_json",
    "validate_operating_cortex_packet",
    "validate_operating_cortex_packet_join",
    "validate_operating_cortex_registration_join",
    "validate_operating_cortex_registration_record",
]
