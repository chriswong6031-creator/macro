"""Pure W5A synthetic Operating Cortex conformance kernel.

The kernel consumes only caller-supplied synthetic evidence and the exact W4A
episodic-retrieval dependency graph.  It performs structural citation, salience,
contradiction, missingness, and falsifier audits.  It has no discovery, prose
generation, clock, filesystem, network, store, service, or emission capability.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
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
        "source_authenticity_established": False,
        "citation_entailment_evaluated": False,
        "evidence_population_complete": False,
        "contradiction_population_complete": False,
        "missingness_population_complete": False,
        "falsifier_population_complete": False,
        "attention_quality_evaluated": False,
        "forecast_input_eligible": False,
        "aggregate_eligible": False,
        "skill_claim_eligible": False,
    }
)

SALIENCE_WEIGHTS: Mapping[str, str] = MappingProxyType(
    {
        "freshness": "0.250000000000000000",
        "source_quality": "0.200000000000000000",
        "episode_relevance": "0.150000000000000000",
        "contradiction_relevance": "0.150000000000000000",
        "missingness_relevance": "0.150000000000000000",
        "falsifier_relevance": "0.100000000000000000",
    }
)

_MAX_REGISTRATION_BYTES = 256 * 1024
_MAX_PACKET_BYTES = 2 * 1024 * 1024
_MAX_SOURCE_BYTES = 64 * 1024
_MAX_AGGREGATE_SOURCE_BYTES = 4 * 1024 * 1024
_MAX_EVIDENCE = 64
_MAX_CLAIMS = 128
_MAX_REFS = 8
_MAX_KINDS = 16
_MAX_CONTRADICTION_GROUPS = 128
_MAX_EPISODES = 33
_MAX_STRING = 256
_MAX_DEPTH = 16
_MAX_NODES = 16_384

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

# These concepts are intentionally unavailable to this structural kernel.  The
# boundary applies to caller-defined identifiers and UTF-8 source bytes, not to
# exact W2/W4 dependency identifiers such as ``mmforecast_*``.
_FORBIDDEN_TOKEN = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:actions?|buys?|sells?|holds?|holding|long|short|"
    r"outcomes?|labels?|bullish|bearish|forecasts?|directions?|pnl|p\s*&\s*l|"
    r"profits?|loss(?:es)?|returns?|trades?|positions?|targets?|recommendations?)"
    r"(?:$|[^a-z0-9])"
)

_REGISTRATION_FIELDS = frozenset(
    {
        "schema",
        "operating_cortex_registration_id",
        "registration_key",
        "registered_at",
        "retrieval_registration_id",
        "retrieval_registration_sha256",
        "required_evidence_kinds",
        "salience_policy",
        "citation_policy",
        "implementation",
        "input_profile",
        "claims",
        "emission_enabled",
        "authority",
    }
)
_SALIENCE_POLICY_FIELDS = frozenset(
    {"components", "weights", "missing_component", "ordering", "numeric_convention"}
)
_CITATION_POLICY_FIELDS = frozenset(
    {"closure", "entailment", "source_profile", "withholding_precedence"}
)
_IMPLEMENTATION_FIELDS = frozenset({"producer_code_sha256", "producer_config_sha256"})
_CLAIM_FIELDS = frozenset(CLAIMS)

_PACKET_FIELDS = frozenset(
    {
        "schema",
        "operating_cortex_packet_id",
        "operating_cortex_registration_id",
        "retrieval_registration_id",
        "episodic_retrieval_record_id",
        "trial_registration_id",
        "assembled_at",
        "episode_scope",
        "source_manifests",
        "evidence_cards",
        "claim_inputs",
        "attention_queue",
        "contradictions",
        "missingness",
        "falsifier_audit",
        "citation_projection",
        "scorecards",
        "input_profile",
        "claims",
        "emission_enabled",
        "authority",
    }
)
_EVIDENCE_FIELDS = frozenset(
    {
        "evidence_id",
        "episode_forecast_id",
        "evidence_kind",
        "source_id",
        "source_sha256",
        "citations",
        "stance",
        "contradiction_group_id",
        "salience_components",
    }
)
_CITATION_FIELDS = frozenset({"byte_start", "byte_end"})
_CLAIM_INPUT_FIELDS = frozenset(
    {
        "claim_id",
        "episode_forecast_id",
        "evidence_ids",
        "required_evidence_kinds",
        "falsifier_evidence_ids",
    }
)


class MarketMemoryOperatingCortexContractError(ValueError):
    """A W5A structural cortex value is unsafe or ambiguous."""


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

    def visit(item: object, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > _MAX_NODES:
            _fail(f"{field} exceeds {_MAX_NODES} JSON nodes")
        if depth > _MAX_DEPTH:
            _fail(f"{field} exceeds depth {_MAX_DEPTH}")
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str or len(key) > _MAX_STRING:
                    _fail(f"{field} contains an invalid key")
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str and len(item) > _MAX_STRING:
            _fail(f"{field} contains a string longer than {_MAX_STRING}")
        elif item is not None and type(item) not in {str, int, bool}:
            _fail(f"{field} contains a non-JSON scalar")

    visit(value, 0)


def _canonical_bytes(value: object, *, field: str, maximum: int) -> bytes:
    _resource_guard(value, field=field)
    try:
        body = forward.canonical_json_bytes(value)
    except (forward.MarketMemoryForwardContractError, RecursionError) as exc:
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


def _opaque(value: object, *, field: str) -> str:
    text = _match(value, _OPAQUE, field=field)
    if _FORBIDDEN_TOKEN.search(text.replace("_", " ").replace("-", " ")):
        _fail(f"{field} contains a forbidden semantic token")
    return text


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


def _authority(value: object) -> dict[str, Any]:
    expected = dict(forward.AUTHORITY)
    if not _exact_equal(
        value, expected, field="authority", maximum=_MAX_REGISTRATION_BYTES
    ):
        _fail("authority must equal the frozen W2 zero-authority block")
    return expected


def _claims(value: object) -> dict[str, bool]:
    payload = _require_fields(value, _CLAIM_FIELDS, field="claims")
    expected = dict(CLAIMS)
    if payload != expected:
        _fail("all W5A evidence and authority claims must remain false")
    return expected


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


def _registration_sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_bytes(
            value, field="retrieval registration", maximum=_MAX_REGISTRATION_BYTES
        )
    ).hexdigest()


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


def _fixed_salience_policy() -> dict[str, Any]:
    return {
        "components": list(SALIENCE_WEIGHTS),
        "weights": dict(SALIENCE_WEIGHTS),
        "missing_component": "abstain",
        "ordering": "score_desc_then_evidence_id_then_abstained_evidence_id",
        "numeric_convention": NUMERIC_CONVENTION,
    }


def _fixed_citation_policy() -> dict[str, Any]:
    return {
        "closure": "exact_source_sha256_and_half_open_byte_spans",
        "entailment": "not_evaluated",
        "source_profile": "caller_supplied_synthetic_exact_bytes",
        "withholding_precedence": [
            "evidence_reference_missing",
            "required_evidence_kind_missing",
            "citation_not_closed",
            "falsifier_reference_missing",
        ],
    }


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
    """Build an inert W5A registration over one exact W4A registration."""

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
    payload: dict[str, Any] = {
        "schema": OPERATING_CORTEX_REGISTRATION_SCHEMA,
        "operating_cortex_registration_id": "",
        "registration_key": registration_key,
        "registered_at": registered_at,
        "retrieval_registration_id": joined["retrieval_registration_id"],
        "retrieval_registration_sha256": _registration_sha(joined),
        "required_evidence_kinds": kinds,
        "salience_policy": _fixed_salience_policy(),
        "citation_policy": _fixed_citation_policy(),
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
    """Validate a self-authenticating W5A registration without dependency joins."""

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
    salience = _require_fields(
        payload["salience_policy"], _SALIENCE_POLICY_FIELDS, field="salience_policy"
    )
    citation = _require_fields(
        payload["citation_policy"], _CITATION_POLICY_FIELDS, field="citation_policy"
    )
    implementation = _require_fields(
        payload["implementation"], _IMPLEMENTATION_FIELDS, field="implementation"
    )
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
            re.compile(r"mmretrievalregistration_[a-f0-9]{64}\Z"),
            field="retrieval_registration_id",
        ),
        "retrieval_registration_sha256": _sha(
            payload["retrieval_registration_sha256"],
            field="retrieval_registration_sha256",
        ),
        "required_evidence_kinds": _sorted_unique_opaque(
            payload["required_evidence_kinds"],
            field="required_evidence_kinds",
            minimum=1,
            maximum=_MAX_KINDS,
        ),
        "salience_policy": dict(salience),
        "citation_policy": dict(citation),
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
        _fail("salience policy differs from the frozen six-component W5A policy")
    if clean["citation_policy"] != _fixed_citation_policy():
        _fail("citation policy differs from the frozen structural W5A policy")
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
    if clean["retrieval_registration_sha256"] != _registration_sha(joined):
        _fail("cortex registration differs from exact W4A registration bytes")
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


def _exact_sources(
    value: Mapping[str, bytes],
) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        _fail("exact_source_bytes must be a plain source_id to bytes mapping")
    if len(value) > _MAX_EVIDENCE:
        _fail("exact_source_bytes contains too many sources")
    sources: dict[str, bytes] = {}
    total = 0
    for raw_id in sorted(value):
        source_id = _opaque(raw_id, field="exact_source_bytes source_id")
        body = value[raw_id]
        if type(body) is not bytes or not body or len(body) > _MAX_SOURCE_BYTES:
            _fail("each exact source must contain 1..64 KiB bytes")
        total += len(body)
        if total > _MAX_AGGREGATE_SOURCE_BYTES:
            _fail("aggregate exact source bytes exceed 4 MiB")
        text = body.decode("latin-1")
        if _FORBIDDEN_TOKEN.search(text):
            _fail("synthetic exact source bytes contain a forbidden semantic token")
        sources[source_id] = bytes(body)
    manifests = [
        {
            "source_id": source_id,
            "source_sha256": hashlib.sha256(body).hexdigest(),
            "byte_length": len(body),
        }
        for source_id, body in sources.items()
    ]
    return sources, manifests


def _clean_evidence(
    value: Sequence[Mapping[str, Any]],
    *,
    episode_scope: set[str],
    sources: Mapping[str, bytes],
) -> list[dict[str, Any]]:
    if type(value) not in {list, tuple} or len(value) > _MAX_EVIDENCE:
        _fail("evidence_cards must contain at most 64 rows")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        row = _require_fields(item, _EVIDENCE_FIELDS, field=f"evidence_cards[{index}]")
        evidence_id = _opaque(
            row["evidence_id"], field=f"evidence_cards[{index}].evidence_id"
        )
        episode_id = _match(
            row["episode_forecast_id"],
            _FORECAST_ID,
            field=f"evidence_cards[{index}].episode_forecast_id",
        )
        if episode_id not in episode_scope:
            _fail("evidence card episode is outside exact W4A episode scope")
        source_id = _opaque(
            row["source_id"], field=f"evidence_cards[{index}].source_id"
        )
        if source_id not in sources:
            _fail("evidence card references an absent exact source")
        source_sha = _sha(
            row["source_sha256"], field=f"evidence_cards[{index}].source_sha256"
        )
        if source_sha != hashlib.sha256(sources[source_id]).hexdigest():
            _fail("evidence card source hash differs from exact source bytes")
        citations_raw = row["citations"]
        if type(citations_raw) is not list or len(citations_raw) > _MAX_REFS:
            _fail("evidence citations must contain at most 8 spans")
        citations: list[dict[str, int]] = []
        for citation_index, raw in enumerate(citations_raw):
            citation = _require_fields(
                raw,
                _CITATION_FIELDS,
                field=f"evidence_cards[{index}].citations[{citation_index}]",
            )
            start = _exact_int(
                citation["byte_start"],
                field="byte_start",
                minimum=0,
                maximum=len(sources[source_id]),
            )
            end = _exact_int(
                citation["byte_end"],
                field="byte_end",
                minimum=1,
                maximum=len(sources[source_id]),
            )
            if start >= end:
                _fail("citation spans must be non-empty half-open byte intervals")
            citations.append({"byte_start": start, "byte_end": end})
        if citations != sorted(
            citations, key=lambda span: (span["byte_start"], span["byte_end"])
        ) or len({(span["byte_start"], span["byte_end"]) for span in citations}) != len(
            citations
        ):
            _fail("citation spans must be sorted and unique")
        stance = row["stance"]
        if stance not in {"supports", "challenges", "neutral"}:
            _fail("evidence stance must be supports, challenges, or neutral")
        group = row["contradiction_group_id"]
        if group is not None:
            group = _opaque(
                group, field=f"evidence_cards[{index}].contradiction_group_id"
            )
        if stance in {"supports", "challenges"} and group is None:
            _fail("supporting and challenging evidence requires a contradiction group")
        if stance == "neutral" and group is not None:
            _fail("neutral evidence cannot claim a contradiction group")
        components = _require_dict(
            row["salience_components"], field="salience_components"
        )
        if set(components) != set(SALIENCE_WEIGHTS):
            _fail("salience components must contain the frozen six component names")
        clean_components: dict[str, str | None] = {}
        for component in SALIENCE_WEIGHTS:
            raw_component = components[component]
            if raw_component is None:
                clean_components[component] = None
            else:
                clean_components[component] = _q18_unit(
                    raw_component, field=f"salience_components.{component}"
                )[0]
        rows.append(
            {
                "evidence_id": evidence_id,
                "episode_forecast_id": episode_id,
                "evidence_kind": _opaque(row["evidence_kind"], field="evidence_kind"),
                "source_id": source_id,
                "source_sha256": source_sha,
                "citations": citations,
                "stance": stance,
                "contradiction_group_id": group,
                "salience_components": clean_components,
            }
        )
    ids = [row["evidence_id"] for row in rows]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        _fail("evidence cards must be sorted by unique evidence_id")
    if (
        len(
            {
                row["contradiction_group_id"]
                for row in rows
                if row["contradiction_group_id"] is not None
            }
        )
        > _MAX_CONTRADICTION_GROUPS
    ):
        _fail("contradiction groups exceed the bound")
    return rows


def _clean_claim_inputs(
    value: Sequence[Mapping[str, Any]], *, episode_scope: set[str]
) -> list[dict[str, Any]]:
    if type(value) not in {list, tuple} or len(value) > _MAX_CLAIMS:
        _fail("claim_inputs must contain at most 128 rows")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        row = _require_fields(item, _CLAIM_INPUT_FIELDS, field=f"claim_inputs[{index}]")
        episode_id = _match(
            row["episode_forecast_id"], _FORECAST_ID, field="claim episode"
        )
        if episode_id not in episode_scope:
            _fail("claim episode is outside exact W4A episode scope")
        rows.append(
            {
                "claim_id": _opaque(row["claim_id"], field="claim_id"),
                "episode_forecast_id": episode_id,
                "evidence_ids": _sorted_unique_opaque(
                    row["evidence_ids"],
                    field="claim evidence_ids",
                    minimum=1,
                    maximum=_MAX_REFS,
                ),
                "required_evidence_kinds": _sorted_unique_opaque(
                    row["required_evidence_kinds"],
                    field="claim required_evidence_kinds",
                    minimum=1,
                    maximum=_MAX_KINDS,
                ),
                "falsifier_evidence_ids": _sorted_unique_opaque(
                    row["falsifier_evidence_ids"],
                    field="claim falsifier_evidence_ids",
                    minimum=0,
                    maximum=_MAX_REFS,
                ),
            }
        )
    ids = [row["claim_id"] for row in rows]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        _fail("claim inputs must be sorted by unique claim_id")
    return rows


def _attention(evidence: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    abstained: list[dict[str, Any]] = []
    for row in evidence:
        components = row["salience_components"]
        if any(components[name] is None for name in SALIENCE_WEIGHTS):
            abstained.append(
                {
                    "evidence_id": row["evidence_id"],
                    "episode_forecast_id": row["episode_forecast_id"],
                    "salience_score": None,
                    "status": "abstained",
                    "reason": "missing_salience_component",
                }
            )
            continue
        with localcontext(_DECIMAL_CONTEXT):
            total = sum(
                Decimal(components[name]) * Decimal(weight)
                for name, weight in SALIENCE_WEIGHTS.items()
            )
        scored.append(
            {
                "evidence_id": row["evidence_id"],
                "episode_forecast_id": row["episode_forecast_id"],
                "salience_score": _q18_text(total, field="salience_score"),
                "status": "scored",
                "reason": None,
            }
        )
    scored.sort(key=lambda row: (-Decimal(row["salience_score"]), row["evidence_id"]))
    abstained.sort(key=lambda row: row["evidence_id"])
    return scored + abstained


def _contradictions(evidence: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, list[str]]] = {}
    for row in evidence:
        group_id = row["contradiction_group_id"]
        if group_id is None:
            continue
        group = groups.setdefault(group_id, {"supports": [], "challenges": []})
        group[row["stance"]].append(row["evidence_id"])
    rows = []
    for group_id, group in sorted(groups.items()):
        if len(group["supports"]) > _MAX_REFS or len(group["challenges"]) > _MAX_REFS:
            _fail("each contradiction stance exceeds the 8-reference bound")
        if group["supports"] and group["challenges"]:
            rows.append(
                {
                    "contradiction_group_id": group_id,
                    "supports_evidence_ids": sorted(group["supports"]),
                    "challenges_evidence_ids": sorted(group["challenges"]),
                    "status": "structural_conflict",
                }
            )
    return rows


def _missingness(
    episode_scope: Sequence[str],
    evidence: Sequence[Mapping[str, Any]],
    required_kinds: Sequence[str],
) -> list[dict[str, Any]]:
    supplied: dict[str, set[str]] = {episode_id: set() for episode_id in episode_scope}
    for row in evidence:
        supplied[row["episode_forecast_id"]].add(row["evidence_kind"])
    return [
        {
            "episode_forecast_id": episode_id,
            "required_evidence_kinds": list(required_kinds),
            "supplied_required_evidence_kinds": sorted(
                supplied[episode_id] & set(required_kinds)
            ),
            "missing_required_evidence_kinds": sorted(
                set(required_kinds) - supplied[episode_id]
            ),
            "scope": "supplied_synthetic_evidence_only",
        }
        for episode_id in episode_scope
    ]


def _falsifier_audit(
    claims: Sequence[Mapping[str, Any]], evidence_by_id: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for claim in claims:
        expected = claim["falsifier_evidence_ids"]
        supplied = [
            evidence_id
            for evidence_id in expected
            if evidence_id in evidence_by_id
            and evidence_by_id[evidence_id]["episode_forecast_id"]
            == claim["episode_forecast_id"]
        ]
        missing = sorted(set(expected) - set(supplied))
        rows.append(
            {
                "claim_id": claim["claim_id"],
                "registered_falsifier_evidence_ids": list(expected),
                "supplied_falsifier_evidence_ids": supplied,
                "missing_falsifier_evidence_ids": missing,
                "status": (
                    "not_registered"
                    if not expected
                    else "complete"
                    if not missing
                    else "incomplete"
                ),
                "generation": "never_generated",
            }
        )
    return rows


def _citation_projection(
    claims: Sequence[Mapping[str, Any]], evidence_by_id: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for claim in claims:
        referenced = [
            evidence_by_id.get(evidence_id) for evidence_id in claim["evidence_ids"]
        ]
        reason: str | None = None
        if any(
            item is None or item["episode_forecast_id"] != claim["episode_forecast_id"]
            for item in referenced
        ):
            reason = "evidence_reference_missing"
        present_kinds = {
            item["evidence_kind"] for item in referenced if item is not None
        }
        if (
            reason is None
            and not set(claim["required_evidence_kinds"]) <= present_kinds
        ):
            reason = "required_evidence_kind_missing"
        if reason is None and any(not item["citations"] for item in referenced):
            reason = "citation_not_closed"
        missing_falsifiers = [
            evidence_id
            for evidence_id in claim["falsifier_evidence_ids"]
            if evidence_id not in evidence_by_id
            or evidence_by_id[evidence_id]["episode_forecast_id"]
            != claim["episode_forecast_id"]
        ]
        if reason is None and missing_falsifiers:
            reason = "falsifier_reference_missing"
        citations = []
        if reason is None:
            for item in referenced:
                for span in item["citations"]:
                    citations.append(
                        {
                            "evidence_id": item["evidence_id"],
                            "source_id": item["source_id"],
                            "source_sha256": item["source_sha256"],
                            "byte_start": span["byte_start"],
                            "byte_end": span["byte_end"],
                        }
                    )
        rows.append(
            {
                "claim_id": claim["claim_id"],
                "episode_forecast_id": claim["episode_forecast_id"],
                "status": "available" if reason is None else "withheld",
                "withholding_reason": reason,
                "citation_refs": citations,
                "entailment": "not_evaluated",
            }
        )
    return rows


def _scorecards(projection: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    denominator = len(projection)
    numerator = sum(row["status"] == "withheld" for row in projection)
    if denominator:
        with localcontext(_DECIMAL_CONTEXT):
            value = Decimal(numerator) / Decimal(denominator)
        unsupported = {
            "status": "computed",
            "value_decimal": _q18_text(value, field="structural_unsupported_rate"),
            "numerator": numerator,
            "denominator": denominator,
            "scope": "supplied_synthetic_claims_only",
        }
    else:
        unsupported = {
            "status": "abstained",
            "value_decimal": None,
            "numerator": 0,
            "denominator": 0,
            "scope": "supplied_synthetic_claims_only",
        }
    return {
        "structural_unsupported_rate": unsupported,
        "attention_quality": {
            "status": "not_evaluated",
            "value": None,
            "reason": "no_labeled_attention_outcomes",
        },
    }


def _derive_packet(
    *,
    registration: Mapping[str, Any],
    episodic_record: Mapping[str, Any],
    evidence_cards: Sequence[Mapping[str, Any]],
    exact_source_bytes: Mapping[str, bytes],
    claim_inputs: Sequence[Mapping[str, Any]],
    assembled_at: str,
) -> dict[str, Any]:
    assembled = _utc(assembled_at, field="assembled_at")
    retrieved = _utc(episodic_record["retrieved_at"], field="retrieved_at")
    if assembled < retrieved:
        _fail("assembled_at cannot precede exact W4A retrieval")
    scope = [
        episodic_record["query"]["forecast_id"],
        *episodic_record["selected_forecast_ids"],
    ]
    if len(scope) > _MAX_EPISODES or len(scope) != len(set(scope)):
        _fail("exact W4A episode scope is invalid or exceeds 33 ids")
    sources, manifests = _exact_sources(exact_source_bytes)
    evidence = _clean_evidence(
        evidence_cards, episode_scope=set(scope), sources=sources
    )
    claims = _clean_claim_inputs(claim_inputs, episode_scope=set(scope))
    used_source_ids = {row["source_id"] for row in evidence}
    if used_source_ids != set(sources):
        _fail("exact source bytes must contain every and only evidence-card sources")
    registered_kinds = set(registration["required_evidence_kinds"])
    if any(
        not set(claim["required_evidence_kinds"]) <= registered_kinds
        for claim in claims
    ):
        _fail("claim required evidence kinds must be preregistered")
    evidence_by_id = {row["evidence_id"]: row for row in evidence}
    projection = _citation_projection(claims, evidence_by_id)
    return {
        "schema": OPERATING_CORTEX_PACKET_SCHEMA,
        "operating_cortex_packet_id": "",
        "operating_cortex_registration_id": registration[
            "operating_cortex_registration_id"
        ],
        "retrieval_registration_id": episodic_record["retrieval_registration_id"],
        "episodic_retrieval_record_id": episodic_record["episodic_retrieval_record_id"],
        "trial_registration_id": episodic_record["trial_registration_id"],
        "assembled_at": assembled_at,
        "episode_scope": scope,
        "source_manifests": manifests,
        "evidence_cards": evidence,
        "claim_inputs": claims,
        "attention_queue": _attention(evidence),
        "contradictions": _contradictions(evidence),
        "missingness": _missingness(
            scope, evidence, registration["required_evidence_kinds"]
        ),
        "falsifier_audit": _falsifier_audit(claims, evidence_by_id),
        "citation_projection": projection,
        "scorecards": _scorecards(projection),
        "input_profile": INPUT_PROFILE,
        "claims": dict(CLAIMS),
        "emission_enabled": False,
        "authority": dict(forward.AUTHORITY),
    }


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
    evidence_cards: Sequence[Mapping[str, Any]],
    exact_source_bytes: Mapping[str, bytes],
    claim_inputs: Sequence[Mapping[str, Any]],
    assembled_at: str,
) -> dict[str, Any]:
    """Build one inert packet after first revalidating the complete W4/W2 join."""

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
        _fail(
            "cortex registration and episodic record do not share exact W4A registration"
        )
    payload = _derive_packet(
        registration=registration,
        episodic_record=episodic,
        evidence_cards=evidence_cards,
        exact_source_bytes=exact_source_bytes,
        claim_inputs=claim_inputs,
        assembled_at=assembled_at,
    )
    payload["operating_cortex_packet_id"] = _content_id(
        "mmcortexpacket_",
        payload,
        field="operating_cortex_packet_id",
        maximum=_MAX_PACKET_BYTES,
    )
    return validate_operating_cortex_packet(payload)


def validate_operating_cortex_packet(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate packet identity and all self-contained structural projections."""

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
        re.compile(r"mmretrievalregistration_[a-f0-9]{64}\Z"),
        field="retrieval_registration_id",
    )
    _match(
        payload["episodic_retrieval_record_id"],
        re.compile(r"mmepisodicretrieval_[a-f0-9]{64}\Z"),
        field="episodic_retrieval_record_id",
    )
    _match(
        payload["trial_registration_id"],
        re.compile(r"mmtrial_[a-f0-9]{64}\Z"),
        field="trial_registration_id",
    )
    _utc(payload["assembled_at"], field="assembled_at")
    if (
        type(payload["episode_scope"]) is not list
        or not 1 <= len(payload["episode_scope"]) <= _MAX_EPISODES
    ):
        _fail("episode_scope must contain 1..33 forecast ids")
    scope = [
        _match(item, _FORECAST_ID, field="episode_scope")
        for item in payload["episode_scope"]
    ]
    if len(scope) != len(set(scope)):
        _fail("episode_scope must be unique")
    manifests = payload["source_manifests"]
    if type(manifests) is not list or len(manifests) > _MAX_EVIDENCE:
        _fail("source_manifests exceeds its bound")
    source_ids = []
    for index, item in enumerate(manifests):
        row = _require_fields(
            item,
            frozenset({"source_id", "source_sha256", "byte_length"}),
            field=f"source_manifests[{index}]",
        )
        source_ids.append(_opaque(row["source_id"], field="source_id"))
        _sha(row["source_sha256"], field="source_sha256")
        _exact_int(
            row["byte_length"],
            field="byte_length",
            minimum=1,
            maximum=_MAX_SOURCE_BYTES,
        )
    if source_ids != sorted(source_ids) or len(source_ids) != len(set(source_ids)):
        _fail("source manifests must be sorted and unique")
    manifest_by_id = {row["source_id"]: row for row in manifests}
    for name in (
        "evidence_cards",
        "claim_inputs",
        "attention_queue",
        "contradictions",
        "missingness",
        "falsifier_audit",
        "citation_projection",
    ):
        if type(payload[name]) is not list:
            _fail(f"{name} must be an array")
    if (
        len(payload["evidence_cards"]) > _MAX_EVIDENCE
        or len(payload["claim_inputs"]) > _MAX_CLAIMS
    ):
        _fail("packet evidence or claim input bound exceeded")
    evidence: list[dict[str, Any]] = []
    for index, item in enumerate(payload["evidence_cards"]):
        row = _require_fields(item, _EVIDENCE_FIELDS, field=f"evidence_cards[{index}]")
        evidence_id = _opaque(row["evidence_id"], field="evidence_id")
        episode_id = _match(
            row["episode_forecast_id"], _FORECAST_ID, field="episode_forecast_id"
        )
        if episode_id not in scope:
            _fail("evidence card episode is outside packet scope")
        source_id = _opaque(row["source_id"], field="source_id")
        source_sha = _sha(row["source_sha256"], field="source_sha256")
        manifest = manifest_by_id.get(source_id)
        if manifest is None or manifest["source_sha256"] != source_sha:
            _fail("evidence card does not close to its source manifest")
        citations_raw = row["citations"]
        if type(citations_raw) is not list or len(citations_raw) > _MAX_REFS:
            _fail("evidence citations exceed their bound")
        citations = []
        for citation_index, raw in enumerate(citations_raw):
            citation = _require_fields(
                raw,
                _CITATION_FIELDS,
                field=f"evidence_cards[{index}].citations[{citation_index}]",
            )
            start = _exact_int(
                citation["byte_start"],
                field="byte_start",
                minimum=0,
                maximum=manifest["byte_length"],
            )
            end = _exact_int(
                citation["byte_end"],
                field="byte_end",
                minimum=1,
                maximum=manifest["byte_length"],
            )
            if start >= end:
                _fail("citation spans must be non-empty half-open byte intervals")
            citations.append({"byte_start": start, "byte_end": end})
        if citations != sorted(
            citations, key=lambda span: (span["byte_start"], span["byte_end"])
        ) or len({(span["byte_start"], span["byte_end"]) for span in citations}) != len(
            citations
        ):
            _fail("citation spans must be sorted and unique")
        stance = row["stance"]
        group = row["contradiction_group_id"]
        if stance not in {"supports", "challenges", "neutral"}:
            _fail("evidence stance is invalid")
        if group is not None:
            group = _opaque(group, field="contradiction_group_id")
        if (stance in {"supports", "challenges"}) != (group is not None):
            _fail("evidence stance and contradiction group are inconsistent")
        components = _require_dict(
            row["salience_components"], field="salience_components"
        )
        if set(components) != set(SALIENCE_WEIGHTS):
            _fail("salience components differ from the frozen six")
        clean_components = {}
        for component in SALIENCE_WEIGHTS:
            raw_component = components[component]
            clean_components[component] = (
                None
                if raw_component is None
                else _q18_unit(raw_component, field=f"salience.{component}")[0]
            )
        evidence.append(
            {
                "evidence_id": evidence_id,
                "episode_forecast_id": episode_id,
                "evidence_kind": _opaque(row["evidence_kind"], field="evidence_kind"),
                "source_id": source_id,
                "source_sha256": source_sha,
                "citations": citations,
                "stance": stance,
                "contradiction_group_id": group,
                "salience_components": clean_components,
            }
        )
    evidence_ids = [row["evidence_id"] for row in evidence]
    if evidence_ids != sorted(evidence_ids) or len(evidence_ids) != len(
        set(evidence_ids)
    ):
        _fail("evidence cards must be sorted by unique evidence_id")
    claim_inputs = _clean_claim_inputs(
        payload["claim_inputs"], episode_scope=set(scope)
    )
    if not payload["missingness"]:
        _fail("missingness must project every episode")
    first_missingness = _require_dict(payload["missingness"][0], field="missingness[0]")
    required_kinds = _sorted_unique_opaque(
        first_missingness.get("required_evidence_kinds"),
        field="missingness required_evidence_kinds",
        minimum=1,
        maximum=_MAX_KINDS,
    )
    evidence_by_id = {row["evidence_id"]: row for row in evidence}
    expected_projection = _citation_projection(claim_inputs, evidence_by_id)
    expected_sections = {
        "evidence_cards": evidence,
        "claim_inputs": claim_inputs,
        "attention_queue": _attention(evidence),
        "contradictions": _contradictions(evidence),
        "missingness": _missingness(scope, evidence, required_kinds),
        "falsifier_audit": _falsifier_audit(claim_inputs, evidence_by_id),
        "citation_projection": expected_projection,
    }
    for name, expected in expected_sections.items():
        if not _exact_equal(
            payload[name],
            expected,
            field=f"packet internal {name}",
            maximum=_MAX_PACKET_BYTES,
        ):
            _fail(f"packet {name} differs from its structural inputs")
    scorecards = _require_fields(
        payload["scorecards"],
        frozenset({"structural_unsupported_rate", "attention_quality"}),
        field="scorecards",
    )
    attention_quality = _require_fields(
        scorecards["attention_quality"],
        frozenset({"status", "value", "reason"}),
        field="attention_quality",
    )
    if attention_quality != {
        "status": "not_evaluated",
        "value": None,
        "reason": "no_labeled_attention_outcomes",
    }:
        _fail("attention quality must remain exactly not_evaluated")
    if not _exact_equal(
        scorecards,
        _scorecards(expected_projection),
        field="packet internal scorecards",
        maximum=_MAX_PACKET_BYTES,
    ):
        _fail("packet scorecards differ from citation projection")
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
    exact_source_bytes: Mapping[str, bytes],
) -> dict[str, Any]:
    """Rebuild a packet from exact W4/W2 and source dependencies and require identity."""

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
    clean = validate_operating_cortex_packet(value)
    expected = _derive_packet(
        registration=registration,
        episodic_record=episodic,
        evidence_cards=clean["evidence_cards"],
        exact_source_bytes=exact_source_bytes,
        claim_inputs=clean["claim_inputs"],
        assembled_at=clean["assembled_at"],
    )
    expected["operating_cortex_packet_id"] = _content_id(
        "mmcortexpacket_",
        expected,
        field="operating_cortex_packet_id",
        maximum=_MAX_PACKET_BYTES,
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
    exact_source_bytes: Mapping[str, bytes],
) -> dict[str, Any]:
    """Strictly load a packet and fully revalidate all exact dependencies."""

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
        exact_source_bytes=exact_source_bytes,
    )


class OperatingCortexReader:
    """Immutable, capability-limited reader over one fully rejoined packet."""

    __slots__ = ("__packet", "__sealed")

    def __init__(self, packet: Mapping[str, Any], **join_dependencies: Any) -> None:
        clean = validate_operating_cortex_packet_join(packet, **join_dependencies)
        object.__setattr__(self, "_OperatingCortexReader__packet", clean)
        object.__setattr__(self, "_OperatingCortexReader__sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_OperatingCortexReader__sealed", False):
            raise AttributeError("OperatingCortexReader is immutable")
        object.__setattr__(self, name, value)

    def _read(self, field: str) -> Any:
        return copy.deepcopy(self.__packet[field])

    def read_attention_queue(self) -> list[dict[str, Any]]:
        return self._read("attention_queue")

    def read_episode_scope(self) -> list[str]:
        return self._read("episode_scope")

    def read_contradictions(self) -> list[dict[str, Any]]:
        return self._read("contradictions")

    def read_missingness(self) -> list[dict[str, Any]]:
        return self._read("missingness")

    def read_falsifier_audit(self) -> list[dict[str, Any]]:
        return self._read("falsifier_audit")

    def read_citation_projection(self) -> list[dict[str, Any]]:
        return self._read("citation_projection")

    def read_scorecards(self) -> dict[str, Any]:
        return self._read("scorecards")


__all__ = [
    "CLAIMS",
    "INPUT_PROFILE",
    "NUMERIC_CONVENTION",
    "OPERATING_CORTEX_PACKET_SCHEMA",
    "OPERATING_CORTEX_REGISTRATION_SCHEMA",
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
