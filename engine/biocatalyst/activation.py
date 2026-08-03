"""Dark, fail-closed retention verification for the BioCatalyst R2 lane.

This module deliberately has no collection, ledger, publication, delete, or
pointer-advance operation.  ``check_activation`` can only read the Cloudflare
control plane and issue a data-plane ``HeadBucket``.  ``seal_activation`` is
the sole mutation and can only create an immutable receipt with conditional
create and exact readback.  ``heartbeat_activation`` is read-only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable
from urllib.parse import urlsplit

from engine.sector_intelligence import canonical_json_bytes, canonical_json_sha256, validate_contract


_ACCOUNT_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_BUCKET_RE = re.compile(
    r"(?!.*\.\.)(?!.*\.-)(?!.*-\.)[a-z0-9](?:[a-z0-9.-]{1,61})[a-z0-9]"
)
_PREFIX = "biocatalyst/"
_WORKER_PERMISSION = "Workers R2 Storage Bucket Item Write"
_CONTROL_HOST = "https://api.cloudflare.com/client/v4"
_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_MAX_CONTROL_RESPONSE_BYTES = 1024 * 1024
_MAX_RECEIPT_BYTES = 65536
_MAX_PREFLIGHT_AGE_SECONDS = 300
_MAX_GATE_TTL_SECONDS = 86400
_MAX_HEARTBEAT_TTL_SECONDS = 7200


class ActivationError(RuntimeError):
    """A bounded, secret-free B4E failure code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ControlPlaneConfig:
    """The independently configured control-plane target to verify."""

    account_id: str
    bucket: str
    jurisdiction: str
    endpoint: str
    worker_token_id: str
    gate_ttl_seconds: int = 86400
    heartbeat_ttl_seconds: int = 7200

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> "ControlPlaneConfig":
        required = (
            "BIOCATALYST_R2_CONTROL_ACCOUNT_ID",
            "BIOCATALYST_R2_BUCKET",
            "BIOCATALYST_R2_ENDPOINT",
            "BIOCATALYST_R2_ACCESS_KEY_ID",
        )
        if any(not environ.get(name, "").strip() for name in required):
            raise ActivationError("BIOCATALYST_R2_CONTROL_CONFIG_INVALID")
        raw_gate_ttl = environ.get(
            "BIOCATALYST_R2_ACTIVATION_GATE_TTL_SECONDS", "86400"
        ).strip()
        raw_heartbeat_ttl = environ.get(
            "BIOCATALYST_R2_HEARTBEAT_TTL_SECONDS", "7200"
        ).strip()
        try:
            gate_ttl = int(raw_gate_ttl)
            heartbeat_ttl = int(raw_heartbeat_ttl)
        except ValueError:
            raise ActivationError("BIOCATALYST_R2_CONTROL_CONFIG_INVALID") from None
        config = cls(
            account_id=environ["BIOCATALYST_R2_CONTROL_ACCOUNT_ID"].strip(),
            bucket=environ["BIOCATALYST_R2_BUCKET"].strip(),
            jurisdiction=environ.get("BIOCATALYST_R2_JURISDICTION", "default").strip(),
            endpoint=environ["BIOCATALYST_R2_ENDPOINT"].strip(),
            worker_token_id=environ["BIOCATALYST_R2_ACCESS_KEY_ID"].strip(),
            gate_ttl_seconds=gate_ttl,
            heartbeat_ttl_seconds=heartbeat_ttl,
        )
        config.validate()
        return config

    def validate(self) -> None:
        if (
            not _ACCOUNT_ID_RE.fullmatch(self.account_id)
            or not _ACCOUNT_ID_RE.fullmatch(self.worker_token_id)
            or not _BUCKET_RE.fullmatch(self.bucket)
            or self.jurisdiction not in {"default", "eu", "fedramp"}
            or not 300 <= self.gate_ttl_seconds <= 86400
            or not 300 <= self.heartbeat_ttl_seconds <= 7200
        ):
            raise ActivationError("BIOCATALYST_R2_CONTROL_CONFIG_INVALID")
        expected_host = (
            f"{self.account_id}.r2.cloudflarestorage.com"
            if self.jurisdiction == "default"
            else f"{self.account_id}.{self.jurisdiction}.r2.cloudflarestorage.com"
        )
        try:
            parsed = urlsplit(self.endpoint)
            endpoint_valid = (
                parsed.scheme == "https"
                and parsed.hostname == expected_host
                and parsed.username is None
                and parsed.password is None
                and parsed.port is None
                and parsed.path in {"", "/"}
                and not parsed.query
                and not parsed.fragment
            )
        except (TypeError, ValueError):
            endpoint_valid = False
        if not endpoint_valid:
            raise ActivationError("BIOCATALYST_R2_CONTROL_CONFIG_INVALID")

    @property
    def worker_resource(self) -> str:
        return (
            "com.cloudflare.edge.r2.bucket."
            f"{self.account_id}_{self.jurisdiction}_{self.bucket}"
        )

    @property
    def binding_sha256(self) -> str:
        return activation_target_binding_sha256(
            self.account_id,
            self.bucket,
            self.endpoint,
            self.jurisdiction,
            self.worker_token_id,
        )


def activation_target_binding_sha256(
    account_id: str,
    bucket: str,
    endpoint: str,
    jurisdiction: str,
    worker_token_id: str,
) -> str:
    """Return the secret-free target identity workers must match against a gate."""

    config = ControlPlaneConfig(
        account_id=account_id,
        bucket=bucket,
        jurisdiction=jurisdiction,
        endpoint=endpoint,
        worker_token_id=worker_token_id,
        gate_ttl_seconds=300,
        heartbeat_ttl_seconds=300,
    )
    config.validate()
    return canonical_json_sha256(
        {
            "account_id": config.account_id,
            "bucket": config.bucket,
            "endpoint": config.endpoint,
            "jurisdiction": config.jurisdiction,
            "required_prefix": _PREFIX,
            "worker_resource": config.worker_resource,
            "worker_token_id": config.worker_token_id,
        }
    )


@runtime_checkable
class HttpTransport(Protocol):
    """Injected, minimal Cloudflare API transport; never receives raw output."""

    def request(self, method: str, url: str, *, headers: Mapping[str, str]) -> tuple[int, bytes]: ...


@runtime_checkable
class ControlPlane(Protocol):
    def get_worker_token(self) -> Mapping[str, Any]: ...

    def get_lock_rules(self) -> Sequence[Mapping[str, Any]]: ...

    def get_lifecycle_rules(self) -> Sequence[Mapping[str, Any]]: ...


@runtime_checkable
class ObjectPlane(Protocol):
    """The only S3 operations the B4E verifier can request."""

    def head_bucket(self) -> None: ...

    def get_bytes(self, key: str) -> bytes | None: ...

    def put_if_absent(self, key: str, data: bytes, *, content_type: str) -> bool: ...


class CloudflareControlPlane:
    """Read-only Cloudflare control-plane client over an injected transport."""

    def __init__(
        self,
        config: ControlPlaneConfig,
        control_api_token: str,
        *,
        transport: HttpTransport,
    ) -> None:
        config.validate()
        if not isinstance(control_api_token, str) or not control_api_token.strip():
            raise ActivationError("BIOCATALYST_R2_CONTROL_CONFIG_INVALID")
        self._config = config
        self._token = control_api_token.strip()
        self._transport = transport

    def _get(self, path: str, *, r2_jurisdiction: bool = False) -> Mapping[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        if r2_jurisdiction:
            # Cloudflare's jurisdictional R2 bucket-control endpoints require
            # this header even though the account token endpoint does not.
            headers["cf-r2-jurisdiction"] = self._config.jurisdiction
        try:
            status, body = self._transport.request(
                "GET",
                f"{_CONTROL_HOST}{path}",
                headers=headers,
            )
        except ActivationError:
            raise
        except Exception:
            raise ActivationError("BIOCATALYST_R2_CONTROL_PLANE_UNAVAILABLE") from None
        if (
            status != 200
            or not isinstance(body, bytes)
            or len(body) > _MAX_CONTROL_RESPONSE_BYTES
        ):
            raise ActivationError("BIOCATALYST_R2_CONTROL_PLANE_UNAVAILABLE")
        payload = _parse_json_object(
            body,
            "BIOCATALYST_R2_CONTROL_RESPONSE_INVALID",
            max_bytes=_MAX_CONTROL_RESPONSE_BYTES,
        )
        if payload.get("success") is not True:
            raise ActivationError("BIOCATALYST_R2_CONTROL_RESPONSE_INVALID")
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise ActivationError("BIOCATALYST_R2_CONTROL_RESPONSE_INVALID")
        return result

    def get_worker_token(self) -> Mapping[str, Any]:
        return self._get(f"/accounts/{self._config.account_id}/tokens/{self._config.worker_token_id}")

    def get_lock_rules(self) -> Sequence[Mapping[str, Any]]:
        result = self._get(
            f"/accounts/{self._config.account_id}/r2/buckets/{self._config.bucket}/lock",
            r2_jurisdiction=True,
        )
        rules = result.get("rules")
        if not isinstance(rules, list) or not all(isinstance(rule, Mapping) for rule in rules):
            raise ActivationError("BIOCATALYST_R2_CONTROL_RESPONSE_INVALID")
        return rules

    def get_lifecycle_rules(self) -> Sequence[Mapping[str, Any]]:
        result = self._get(
            f"/accounts/{self._config.account_id}/r2/buckets/{self._config.bucket}/lifecycle",
            r2_jurisdiction=True,
        )
        rules = result.get("rules")
        if not isinstance(rules, list) or not all(isinstance(rule, Mapping) for rule in rules):
            raise ActivationError("BIOCATALYST_R2_CONTROL_RESPONSE_INVALID")
        return rules


def _utc(now: datetime | None) -> datetime:
    value = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_TIME_INVALID")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _parse_json_object(
    value: bytes,
    code: str,
    *,
    max_bytes: int = _MAX_RECEIPT_BYTES,
) -> Mapping[str, Any]:
    """Parse a bounded JSON object without duplicate-key ambiguity."""

    if not isinstance(value, bytes) or len(value) > max_bytes:
        raise ActivationError(code)

    def reject_constant(_: str) -> None:
        raise ValueError("non-finite JSON")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result

    try:
        parsed = json.loads(
            value.decode("utf-8"),
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, RecursionError):
        raise ActivationError(code) from None
    if not isinstance(parsed, Mapping):
        raise ActivationError(code)
    return parsed


def _activation_flags() -> dict[str, bool]:
    return {
        "source_collection": False,
        "ledger_accrual": False,
        "public_pointer_advanced": False,
    }


def _with_payload_hash(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    document = dict(payload)
    document[field] = canonical_json_sha256(document)
    return document


def _validate_hashed(
    document: Mapping[str, Any], *, contract_id: str, hash_field: str, code: str
) -> None:
    try:
        validate_contract(contract_id, document)
        actual = document.get(hash_field)
        without_hash = {key: value for key, value in document.items() if key != hash_field}
        if not isinstance(actual, str) or actual != canonical_json_sha256(without_hash):
            raise ValueError("hash mismatch")
    except ActivationError:
        raise
    except Exception:
        raise ActivationError(code) from None


def validate_retention_preflight(preflight: Mapping[str, Any]) -> None:
    _validate_hashed(
        preflight,
        contract_id="biocatalyst_retention_preflight.v1",
        hash_field="preflight_payload_sha256",
        code="BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID",
    )


def _normalise_worker_token(
    token: Mapping[str, Any], config: ControlPlaneConfig
) -> dict[str, str]:
    try:
        token_id = token["id"]
        status = token["status"]
        policies = token["policies"]
        if (
            token_id != config.worker_token_id
            or status != "active"
        ):
            raise ActivationError("BIOCATALYST_R2_WORKER_TOKEN_INVALID")
        if (
            not isinstance(policies, list)
            or len(policies) != 1
            or not isinstance(policies[0], Mapping)
        ):
            raise ValueError
        policy = policies[0]
        groups = policy["permission_groups"]
        resources = policy["resources"]
        if (
            policy.get("effect") != "allow"
            or not isinstance(groups, list)
            or len(groups) != 1
            or not isinstance(groups[0], Mapping)
            or groups[0].get("name") != _WORKER_PERMISSION
            or not isinstance(resources, Mapping)
            or set(resources) != {config.worker_resource}
            or resources[config.worker_resource] != "*"
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ActivationError("BIOCATALYST_R2_WORKER_TOKEN_SCOPE_INVALID") from None
    normal = {
        "effect": "allow",
        "permission_group": _WORKER_PERMISSION,
        "resource": config.worker_resource,
    }
    return {
        "token_id_sha256": canonical_json_sha256(token_id),
        "policy_sha256": canonical_json_sha256(normal),
        "resource_sha256": canonical_json_sha256(config.worker_resource),
        "permission_group": _WORKER_PERMISSION,
    }


def _normalise_condition(value: Any, *, age_field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("type"), str):
        raise ActivationError("BIOCATALYST_R2_CONTROL_RESPONSE_INVALID")
    kind = value["type"]
    if kind == "Indefinite":
        if set(value) != {"type"}:
            raise ActivationError("BIOCATALYST_R2_CONTROL_RESPONSE_INVALID")
        return {"type": kind}
    age = value.get(age_field)
    if (
        kind == "Age"
        and isinstance(age, int)
        and not isinstance(age, bool)
        and age >= 0
    ):
        if set(value) != {"type", age_field}:
            raise ActivationError("BIOCATALYST_R2_CONTROL_RESPONSE_INVALID")
        return {"type": kind, age_field: age}
    if kind == "Date" and isinstance(value.get("date"), str) and value["date"]:
        if set(value) != {"type", "date"}:
            raise ActivationError("BIOCATALYST_R2_CONTROL_RESPONSE_INVALID")
        return {"type": kind, "date": value["date"]}
    raise ActivationError("BIOCATALYST_R2_CONTROL_RESPONSE_INVALID")


def _prefix_covers_required(prefix: str) -> bool:
    """Return whether a rule prefix covers every key in the protected prefix."""

    return _PREFIX.startswith(prefix)


def _prefix_overlaps_required(prefix: str) -> bool:
    """Return whether a rule can affect any key in the protected prefix."""

    return _PREFIX.startswith(prefix) or prefix.startswith(_PREFIX)


def _normalise_locks(rules: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    normal: list[dict[str, Any]] = []
    selected: list[str] = []
    seen_ids: set[str] = set()
    for rule in rules:
        try:
            identifier = rule["id"]
            enabled = rule["enabled"]
            prefix = rule.get("prefix", "")
            if (
                not isinstance(identifier, str)
                or not identifier
                or len(identifier) > 128
                or not isinstance(enabled, bool)
                or not isinstance(prefix, str)
                or identifier in seen_ids
            ):
                raise ValueError
            seen_ids.add(identifier)
            condition = _normalise_condition(
                rule["condition"], age_field="maxAgeSeconds"
            )
        except (KeyError, TypeError, ValueError):
            raise ActivationError("BIOCATALYST_R2_CONTROL_RESPONSE_INVALID") from None
        normalized = {
            "id": identifier,
            "enabled": enabled,
            "prefix": prefix,
            "condition": condition,
        }
        normal.append(normalized)
        if (
            enabled
            and condition["type"] == "Indefinite"
            and _prefix_covers_required(prefix)
        ):
            selected.append(identifier)
    normal.sort(key=lambda rule: rule["id"])
    selected.sort()
    if not selected:
        raise ActivationError("BIOCATALYST_R2_RETENTION_LOCK_MISSING")
    return normal, selected


def _normalise_transition(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ActivationError("BIOCATALYST_R2_CONTROL_RESPONSE_INVALID")
    raw = value.get("condition", value)
    return _normalise_condition(raw, age_field="maxAge")


def _normalise_lifecycle(rules: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normal: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for rule in rules:
        try:
            identifier = rule["id"]
            enabled = rule["enabled"]
            conditions = rule.get("conditions", {})
            if (
                not isinstance(identifier, str)
                or not identifier
                or len(identifier) > 128
                or not isinstance(enabled, bool)
                or not isinstance(conditions, Mapping)
                or identifier in seen_ids
            ):
                raise ValueError
            seen_ids.add(identifier)
            prefix = conditions.get("prefix", "")
            if not isinstance(prefix, str):
                raise ValueError
            deletion = _normalise_transition(rule.get("deleteObjectsTransition"))
        except (KeyError, TypeError, ValueError):
            raise ActivationError("BIOCATALYST_R2_CONTROL_RESPONSE_INVALID") from None
        if enabled and deletion is not None and _prefix_overlaps_required(prefix):
            raise ActivationError("BIOCATALYST_R2_LIFECYCLE_DELETE_PRESENT")
        normal.append(
            {
                "id": identifier,
                "enabled": enabled,
                "prefix": prefix,
                "delete_objects_transition": deletion,
            }
        )
    normal.sort(key=lambda rule: rule["id"])
    return normal


def _read_data_plane(object_plane: ObjectPlane) -> None:
    try:
        result = object_plane.head_bucket()
    except ActivationError:
        raise
    except Exception:
        raise ActivationError("BIOCATALYST_R2_DATA_PLANE_INVALID") from None
    if result is False:
        raise ActivationError("BIOCATALYST_R2_DATA_PLANE_INVALID")


def check_activation(
    config: ControlPlaneConfig,
    control_plane: ControlPlane,
    object_plane: ObjectPlane,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read-only verify the independent R2 retention configuration."""

    config.validate()
    checked_at = _utc(now)
    try:
        token = control_plane.get_worker_token()
        locks = control_plane.get_lock_rules()
        lifecycle = control_plane.get_lifecycle_rules()
    except ActivationError:
        raise
    except Exception:
        raise ActivationError("BIOCATALYST_R2_CONTROL_PLANE_UNAVAILABLE") from None
    if not isinstance(token, Mapping) or not isinstance(locks, Sequence) or not isinstance(lifecycle, Sequence):
        raise ActivationError("BIOCATALYST_R2_CONTROL_RESPONSE_INVALID")
    worker_token = _normalise_worker_token(token, config)
    normalized_locks, selected_locks = _normalise_locks(locks)
    normalized_lifecycle = _normalise_lifecycle(lifecycle)
    _read_data_plane(object_plane)
    base = {
        "contract_id": "biocatalyst_retention_preflight.v1",
        "schema_version": "1.0.0",
        "checked_at": _timestamp(checked_at),
        "provider": "cloudflare_r2",
        "target": {
            "config_binding_sha256": config.binding_sha256,
            "account_id_sha256": canonical_json_sha256(config.account_id),
            "bucket_sha256": canonical_json_sha256(config.bucket),
            "endpoint_sha256": canonical_json_sha256(config.endpoint),
            "jurisdiction": config.jurisdiction,
        },
        "worker_token": worker_token,
        "retention": {
            "required_prefix": _PREFIX,
            "lock_rule_ids": selected_locks,
            "lock_rules_sha256": canonical_json_sha256(normalized_locks),
            "lifecycle_rules_sha256": canonical_json_sha256(normalized_lifecycle),
            "lifecycle_expiration_absent": True,
        },
        "activation": _activation_flags(),
        "hash_scope": "canonical_payload_excluding_preflight_payload_sha256",
    }
    preflight_id = canonical_json_sha256(base)[:24]
    preflight = {"preflight_id": f"r2_preflight_{preflight_id}", **base}
    preflight = _with_payload_hash(preflight, "preflight_payload_sha256")
    validate_retention_preflight(preflight)
    return preflight


def _receipt_key(preflight: Mapping[str, Any]) -> str:
    identifier = preflight.get("preflight_id")
    if not isinstance(identifier, str) or not re.fullmatch(r"r2_preflight_[a-f0-9]{24}", identifier):
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID")
    return f"biocatalyst/activation-preflight/{identifier}.json"


def _get_bytes(object_plane: ObjectPlane, key: str, code: str) -> bytes | None:
    try:
        value = object_plane.get_bytes(key)
    except Exception:
        raise ActivationError(code) from None
    if value is not None and (
        not isinstance(value, bytes) or len(value) > _MAX_RECEIPT_BYTES
    ):
        raise ActivationError(code)
    return value


def seal_activation(
    config: ControlPlaneConfig,
    preflight: Mapping[str, Any],
    object_plane: ObjectPlane,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Conditionally create and read back a private retention receipt."""

    config.validate()
    issued_at = _utc(now)
    validate_retention_preflight(preflight)
    checked_at = _parse_timestamp(preflight.get("checked_at"))
    preflight_age = (issued_at - checked_at).total_seconds()
    if preflight_age < 0 or preflight_age > _MAX_PREFLIGHT_AGE_SECONDS:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_TIME_INVALID")
    if preflight["target"]["config_binding_sha256"] != config.binding_sha256:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID")
    key = _receipt_key(preflight)
    receipt = canonical_json_bytes(preflight)
    if len(receipt) > _MAX_RECEIPT_BYTES:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID")
    existing = _get_bytes(object_plane, key, "BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID")
    if existing is None:
        try:
            created = object_plane.put_if_absent(
                key, receipt, content_type="application/json"
            )
        except Exception:
            raise ActivationError("BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID") from None
        if created is not True:
            existing = _get_bytes(object_plane, key, "BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID")
            if existing != receipt:
                raise ActivationError("BIOCATALYST_R2_ACTIVATION_RECEIPT_COLLISION")
    elif existing != receipt:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_RECEIPT_COLLISION")
    readback = _get_bytes(object_plane, key, "BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID")
    if readback != receipt:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID")
    base = {
        "contract_id": "biocatalyst_activation_gate.v1",
        "schema_version": "1.0.0",
        "state": "ready",
        "issued_at": _timestamp(issued_at),
        "valid_until": _timestamp(issued_at + timedelta(seconds=config.gate_ttl_seconds)),
        "preflight_id": preflight["preflight_id"],
        "preflight_payload_sha256": preflight["preflight_payload_sha256"],
        "target_binding_sha256": config.binding_sha256,
        "receipt_key": key,
        "receipt_sha256": _sha256_bytes(receipt),
        "activation": _activation_flags(),
        "hash_scope": "canonical_payload_excluding_gate_payload_sha256",
    }
    activation_id = canonical_json_sha256(base)[:24]
    gate = {"activation_id": f"r2_activation_{activation_id}", **base}
    gate = _with_payload_hash(gate, "gate_payload_sha256")
    validate_activation_gate(
        gate,
        now=issued_at,
        max_ttl_seconds=config.gate_ttl_seconds,
    )
    return gate


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_TIME_INVALID") from None
    if parsed.tzinfo is None:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_TIME_INVALID")
    return parsed.astimezone(timezone.utc)


def validate_activation_gate(
    gate: Mapping[str, Any],
    *,
    now: datetime | None = None,
    max_ttl_seconds: int = _MAX_GATE_TTL_SECONDS,
) -> None:
    _validate_hashed(
        gate,
        contract_id="biocatalyst_activation_gate.v1",
        hash_field="gate_payload_sha256",
        code="BIOCATALYST_R2_ACTIVATION_GATE_INVALID",
    )
    issued_at = _parse_timestamp(gate.get("issued_at"))
    valid_until = _parse_timestamp(gate.get("valid_until"))
    current = _utc(now)
    if (
        not isinstance(max_ttl_seconds, int)
        or isinstance(max_ttl_seconds, bool)
        or not 1 <= max_ttl_seconds <= _MAX_GATE_TTL_SECONDS
        or valid_until <= issued_at
        or (valid_until - issued_at).total_seconds() > max_ttl_seconds
        or issued_at > current
    ):
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_TIME_INVALID")
    # valid_until is an exclusive lease boundary. At the exact timestamp the
    # root must already have issued a replacement gate.
    if current >= valid_until:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_HEARTBEAT_STALE")


def heartbeat_activation(
    config: ControlPlaneConfig,
    gate: Mapping[str, Any],
    control_plane: ControlPlane,
    object_plane: ObjectPlane,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read-only recheck control/data planes and the sealed activation receipt."""

    checked_at = _utc(now)
    validate_activation_gate(
        gate,
        now=checked_at,
        max_ttl_seconds=config.gate_ttl_seconds,
    )
    if gate.get("target_binding_sha256") != config.binding_sha256:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
    receipt = _get_bytes(
        object_plane,
        str(gate.get("receipt_key", "")),
        "BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID",
    )
    if receipt is None or _sha256_bytes(receipt) != gate.get("receipt_sha256"):
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID")
    saved_preflight = _parse_json_object(
        receipt, "BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID"
    )
    validate_retention_preflight(saved_preflight)
    if (
        saved_preflight.get("preflight_id") != gate.get("preflight_id")
        or saved_preflight.get("preflight_payload_sha256") != gate.get("preflight_payload_sha256")
    ):
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_RECEIPT_INVALID")
    fresh = check_activation(config, control_plane, object_plane, now=checked_at)
    if fresh["target"]["config_binding_sha256"] != gate["target_binding_sha256"]:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
    if fresh["worker_token"] != saved_preflight["worker_token"] or fresh["retention"] != saved_preflight["retention"]:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_HEARTBEAT_INVALID")
    base = {
        "contract_id": "biocatalyst_activation_heartbeat.v1",
        "schema_version": "1.0.0",
        "activation_id": gate["activation_id"],
        "checked_at": _timestamp(checked_at),
        "valid_until": _timestamp(
            min(
                checked_at + timedelta(seconds=config.heartbeat_ttl_seconds),
                _parse_timestamp(gate["valid_until"]),
            )
        ),
        "state": "ready",
        "target_binding_sha256": config.binding_sha256,
        "receipt_sha256": gate["receipt_sha256"],
        "activation": _activation_flags(),
        "hash_scope": "canonical_payload_excluding_heartbeat_payload_sha256",
    }
    heartbeat_id = canonical_json_sha256(base)[:24]
    heartbeat = {"heartbeat_id": f"r2_heartbeat_{heartbeat_id}", **base}
    heartbeat = _with_payload_hash(heartbeat, "heartbeat_payload_sha256")
    validate_activation_heartbeat(
        heartbeat,
        gate,
        now=checked_at,
        max_ttl_seconds=config.heartbeat_ttl_seconds,
        gate_max_ttl_seconds=config.gate_ttl_seconds,
    )
    return heartbeat


def validate_activation_heartbeat(
    heartbeat: Mapping[str, Any],
    gate: Mapping[str, Any],
    *,
    now: datetime | None = None,
    max_ttl_seconds: int = _MAX_HEARTBEAT_TTL_SECONDS,
    gate_max_ttl_seconds: int = _MAX_GATE_TTL_SECONDS,
) -> None:
    """Validate a worker heartbeat against its exact immutable activation gate."""

    validate_activation_gate(
        gate,
        now=now,
        max_ttl_seconds=gate_max_ttl_seconds,
    )
    _validate_hashed(
        heartbeat,
        contract_id="biocatalyst_activation_heartbeat.v1",
        hash_field="heartbeat_payload_sha256",
        code="BIOCATALYST_R2_ACTIVATION_HEARTBEAT_INVALID",
    )
    checked_at = _parse_timestamp(heartbeat.get("checked_at"))
    valid_until = _parse_timestamp(heartbeat.get("valid_until"))
    gate_issued_at = _parse_timestamp(gate.get("issued_at"))
    gate_valid_until = _parse_timestamp(gate.get("valid_until"))
    current = _utc(now)
    if (
        not isinstance(max_ttl_seconds, int)
        or isinstance(max_ttl_seconds, bool)
        or not 1 <= max_ttl_seconds <= _MAX_HEARTBEAT_TTL_SECONDS
        or checked_at < gate_issued_at
        or checked_at > current
        or valid_until <= checked_at
        or (valid_until - checked_at).total_seconds() > max_ttl_seconds
        or valid_until > gate_valid_until
        or heartbeat.get("activation_id") != gate.get("activation_id")
        or heartbeat.get("target_binding_sha256") != gate.get("target_binding_sha256")
        or heartbeat.get("receipt_sha256") != gate.get("receipt_sha256")
    ):
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_HEARTBEAT_INVALID")
    if current >= valid_until:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_HEARTBEAT_STALE")


def validate_local_activation(
    config: ControlPlaneConfig,
    gate: Mapping[str, Any],
    heartbeat: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> None:
    """Validate sealed artifacts and their local R2 identity without I/O."""

    config.validate()
    validate_activation_gate(
        gate,
        now=now,
        max_ttl_seconds=config.gate_ttl_seconds,
    )
    if gate.get("target_binding_sha256") != config.binding_sha256:
        raise ActivationError("BIOCATALYST_R2_ACTIVATION_GATE_INVALID")
    validate_activation_heartbeat(
        heartbeat,
        gate,
        now=now,
        max_ttl_seconds=config.heartbeat_ttl_seconds,
        gate_max_ttl_seconds=config.gate_ttl_seconds,
    )
