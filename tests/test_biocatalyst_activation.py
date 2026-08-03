from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os

import pytest

from engine.biocatalyst.activation import (
    ActivationError,
    CloudflareControlPlane,
    ControlPlaneConfig,
    activation_target_binding_sha256,
    check_activation,
    heartbeat_activation,
    seal_activation,
    validate_activation_gate,
    validate_activation_heartbeat,
    validate_local_activation,
)
from scripts.biocatalyst_activation import main
from engine.sector_intelligence import canonical_json_bytes, canonical_json_sha256


ACCOUNT_ID = "a" * 32
WORKER_TOKEN_ID = "b" * 32
ENDPOINT = f"https://{ACCOUNT_ID}.r2.cloudflarestorage.com"
NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


class FakeControlPlane:
    def __init__(self) -> None:
        self.token = {
            "id": WORKER_TOKEN_ID,
            "status": "active",
            "policies": [
                {
                    "effect": "allow",
                    "permission_groups": [
                        {"name": "Workers R2 Storage Bucket Item Write"}
                    ],
                    "resources": {
                        f"com.cloudflare.edge.r2.bucket.{ACCOUNT_ID}_default_biocatalyst-private": "*"
                    },
                }
            ],
        }
        self.locks = [
            {
                "id": "biocatalyst-indefinite",
                "enabled": True,
                "prefix": "biocatalyst/",
                "condition": {"type": "Indefinite"},
            }
        ]
        self.lifecycle: list[dict[str, object]] = []
        self.calls: list[str] = []

    def get_worker_token(self):
        self.calls.append("token")
        return deepcopy(self.token)

    def get_lock_rules(self):
        self.calls.append("locks")
        return deepcopy(self.locks)

    def get_lifecycle_rules(self):
        self.calls.append("lifecycle")
        return deepcopy(self.lifecycle)


class FakeObjectPlane:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.head_calls = 0
        self.get_calls: list[str] = []
        self.put_calls: list[tuple[str, bytes, str]] = []

    def head_bucket(self) -> None:
        self.head_calls += 1

    def get_bytes(self, key: str) -> bytes | None:
        self.get_calls.append(key)
        return self.objects.get(key)

    def put_if_absent(self, key: str, data: bytes, *, content_type: str) -> bool:
        self.put_calls.append((key, data, content_type))
        if key in self.objects:
            return False
        self.objects[key] = data
        return True


class FakeHttpTransport:
    def __init__(self, control: FakeControlPlane) -> None:
        self.control = control
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def request(self, method: str, url: str, *, headers):
        self.calls.append((method, url, dict(headers)))
        if url.endswith(f"/tokens/{WORKER_TOKEN_ID}"):
            result = self.control.token
        elif url.endswith("/lock"):
            result = {"rules": self.control.locks}
        elif url.endswith("/lifecycle"):
            result = {"rules": self.control.lifecycle}
        else:  # pragma: no cover - test adapter guard
            raise AssertionError(url)
        return 200, json.dumps({"success": True, "result": result}).encode("utf-8")


def _config() -> ControlPlaneConfig:
    return ControlPlaneConfig(
        account_id=ACCOUNT_ID,
        bucket="biocatalyst-private",
        jurisdiction="default",
        endpoint=ENDPOINT,
        worker_token_id=WORKER_TOKEN_ID,
        gate_ttl_seconds=86400,
        heartbeat_ttl_seconds=3600,
    )


def _environment() -> dict[str, str]:
    return {
        "BIOCATALYST_R2_CONTROL_ACCOUNT_ID": ACCOUNT_ID,
        "BIOCATALYST_R2_BUCKET": "biocatalyst-private",
        "BIOCATALYST_R2_ENDPOINT": ENDPOINT,
        "BIOCATALYST_R2_ACCESS_KEY_ID": WORKER_TOKEN_ID,
        "BIOCATALYST_R2_JURISDICTION": "default",
    }


def _rehash(document: dict, field: str) -> None:
    document.pop(field, None)
    document[field] = canonical_json_sha256(document)


def test_ttl_defaults_and_bounds_keep_control_heartbeats_short() -> None:
    defaults = ControlPlaneConfig.from_environment(_environment())
    assert defaults.gate_ttl_seconds == 86400
    assert defaults.heartbeat_ttl_seconds == 7200
    invalid = _environment()
    invalid["BIOCATALYST_R2_HEARTBEAT_TTL_SECONDS"] = "7201"

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_CONTROL_CONFIG_INVALID"):
        ControlPlaneConfig.from_environment(invalid)

    userinfo = _environment()
    userinfo["BIOCATALYST_R2_ENDPOINT"] = (
        f"https://embedded@{ACCOUNT_ID}.r2.cloudflarestorage.com"
    )
    with pytest.raises(ActivationError, match="BIOCATALYST_R2_CONTROL_CONFIG_INVALID"):
        ControlPlaneConfig.from_environment(userinfo)


def test_check_is_read_only_and_emits_a_hashed_dark_preflight() -> None:
    control = FakeControlPlane()
    objects = FakeObjectPlane()

    preflight = check_activation(_config(), control, objects, now=NOW)

    assert objects.head_calls == 1
    assert objects.get_calls == []
    assert objects.put_calls == []
    assert preflight["activation"] == {
        "source_collection": False,
        "ledger_accrual": False,
        "public_pointer_advanced": False,
    }
    assert preflight["retention"]["lock_rule_ids"] == ["biocatalyst-indefinite"]
    assert preflight["target"]["config_binding_sha256"] == activation_target_binding_sha256(
        ACCOUNT_ID, "biocatalyst-private", ENDPOINT, "default", WORKER_TOKEN_ID
    )


def test_cloudflare_control_adapter_uses_only_injected_read_transport() -> None:
    source = FakeControlPlane()
    transport = FakeHttpTransport(source)
    control = CloudflareControlPlane(_config(), "separate-control-token", transport=transport)

    check_activation(_config(), control, FakeObjectPlane(), now=NOW)

    assert [method for method, _, _ in transport.calls] == ["GET", "GET", "GET"]
    assert all(url.startswith("https://api.cloudflare.com/client/v4/accounts/") for _, url, _ in transport.calls)
    assert all(headers["Authorization"] == "Bearer separate-control-token" for _, _, headers in transport.calls)
    assert "cf-r2-jurisdiction" not in transport.calls[0][2]
    assert [headers["cf-r2-jurisdiction"] for _, _, headers in transport.calls[1:]] == [
        "default",
        "default",
    ]


def test_cloudflare_control_adapter_rejects_duplicate_json_keys() -> None:
    class DuplicateKeyTransport:
        def request(self, method, url, *, headers):
            return 200, b'{"success":true,"success":true,"result":{}}'

    control = CloudflareControlPlane(
        _config(), "separate-control-token", transport=DuplicateKeyTransport()
    )

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_CONTROL_RESPONSE_INVALID"):
        control.get_worker_token()


def test_cloudflare_control_adapter_bounds_pathological_json_depth() -> None:
    class DeepTransport:
        def request(self, method, url, *, headers):
            depth = 1500
            body = b'{"success":true,"result":' + b"[" * depth + b"0" + b"]" * depth + b"}"
            return 200, body

    control = CloudflareControlPlane(
        _config(), "separate-control-token", transport=DeepTransport()
    )

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_CONTROL_RESPONSE_INVALID"):
        control.get_worker_token()


def test_check_rejects_a_matching_lifecycle_expiration_before_data_plane() -> None:
    control = FakeControlPlane()
    control.lifecycle = [
        {
            "id": "dangerous-expiry",
            "enabled": True,
            "conditions": {"prefix": "biocatalyst/"},
            "deleteObjectsTransition": {"condition": {"type": "Age", "maxAge": 1}},
        }
    ]
    objects = FakeObjectPlane()

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_LIFECYCLE_DELETE_PRESENT"):
        check_activation(_config(), control, objects, now=NOW)

    assert objects.head_calls == 0
    assert objects.put_calls == []


@pytest.mark.parametrize(
    "prefix",
    ("", "b", "biocatalyst", "biocatalyst/", "biocatalyst/private"),
)
def test_check_rejects_lifecycle_deletion_with_any_protected_prefix_overlap(prefix) -> None:
    control = FakeControlPlane()
    control.lifecycle = [
        {
            "id": "overlapping-expiry",
            "enabled": True,
            "conditions": {"prefix": prefix},
            "deleteObjectsTransition": {"condition": {"type": "Age", "maxAge": 1}},
        }
    ]

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_LIFECYCLE_DELETE_PRESENT"):
        check_activation(_config(), control, FakeObjectPlane(), now=NOW)


def test_lock_prefix_must_cover_all_protected_keys_and_accepts_cloudflare_age_shape() -> None:
    control = FakeControlPlane()
    control.locks = [
        {
            "id": "finite-lock",
            "enabled": True,
            "prefix": "biocatalyst/private",
            "condition": {"type": "Age", "maxAgeSeconds": 3600},
        },
        {
            "id": "covering-lock",
            "enabled": True,
            "prefix": "biocatalyst",
            "condition": {"type": "Indefinite"},
        },
    ]

    preflight = check_activation(_config(), control, FakeObjectPlane(), now=NOW)
    assert preflight["retention"]["lock_rule_ids"] == ["covering-lock"]

    control.locks[0]["condition"] = {"type": "Age", "maxAge": 3600}
    with pytest.raises(ActivationError, match="BIOCATALYST_R2_CONTROL_RESPONSE_INVALID"):
        check_activation(_config(), control, FakeObjectPlane(), now=NOW)


@pytest.mark.parametrize("kind", ("lock", "lifecycle"))
def test_check_rejects_duplicate_control_rule_ids(kind: str) -> None:
    control = FakeControlPlane()
    if kind == "lock":
        control.locks.append(deepcopy(control.locks[0]))
    else:
        rule = {
            "id": "duplicate",
            "enabled": False,
            "conditions": {"prefix": "other/"},
        }
        control.lifecycle = [deepcopy(rule), deepcopy(rule)]

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_CONTROL_RESPONSE_INVALID"):
        check_activation(_config(), control, FakeObjectPlane(), now=NOW)


def test_check_rejects_worker_token_with_an_extra_grant() -> None:
    control = FakeControlPlane()
    control.token["policies"][0]["permission_groups"].append({"name": "Workers R2 Storage Write"})

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_WORKER_TOKEN_SCOPE_INVALID"):
        check_activation(_config(), control, FakeObjectPlane(), now=NOW)


def test_check_rejects_worker_token_bound_to_the_wrong_bucket_resource() -> None:
    control = FakeControlPlane()
    control.token["policies"][0]["resources"] = {
        f"com.cloudflare.edge.r2.bucket.{ACCOUNT_ID}_default_other-private": "*"
    }

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_WORKER_TOKEN_SCOPE_INVALID"):
        check_activation(_config(), control, FakeObjectPlane(), now=NOW)


def test_seal_is_conditional_create_with_exact_readback_and_gate() -> None:
    control = FakeControlPlane()
    objects = FakeObjectPlane()
    preflight = check_activation(_config(), control, objects, now=NOW)

    gate = seal_activation(_config(), preflight, objects, now=NOW)

    assert len(objects.put_calls) == 1
    key, receipt, content_type = objects.put_calls[0]
    assert key == gate["receipt_key"]
    assert content_type == "application/json"
    assert objects.objects[key] == receipt
    assert gate["state"] == "ready"
    validate_activation_gate(gate, now=NOW)


def test_seal_rejects_an_immutable_receipt_collision() -> None:
    control = FakeControlPlane()
    objects = FakeObjectPlane()
    preflight = check_activation(_config(), control, objects, now=NOW)
    objects.objects[f"biocatalyst/activation-preflight/{preflight['preflight_id']}.json"] = b"different"

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_RECEIPT_COLLISION"):
        seal_activation(_config(), preflight, objects, now=NOW)

    assert objects.put_calls == []


@pytest.mark.parametrize("seal_time", (NOW - timedelta(seconds=1), NOW + timedelta(seconds=301)))
def test_seal_rejects_future_or_stale_preflight_before_any_receipt_write(seal_time) -> None:
    control = FakeControlPlane()
    objects = FakeObjectPlane()
    preflight = check_activation(_config(), control, objects, now=NOW)

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_TIME_INVALID"):
        seal_activation(_config(), preflight, objects, now=seal_time)

    assert objects.put_calls == []


def test_heartbeat_is_read_only_has_a_short_lease_and_cannot_outlive_the_gate() -> None:
    control = FakeControlPlane()
    objects = FakeObjectPlane()
    preflight = check_activation(_config(), control, objects, now=NOW)
    gate = seal_activation(_config(), preflight, objects, now=NOW)
    puts_before = len(objects.put_calls)

    heartbeat = heartbeat_activation(
        _config(), gate, control, objects, now=NOW + timedelta(minutes=5)
    )

    assert len(objects.put_calls) == puts_before
    assert gate["valid_until"] == "2026-08-03T12:00:00Z"
    assert heartbeat["valid_until"] == "2026-08-02T13:05:00Z"
    validate_activation_heartbeat(heartbeat, gate, now=NOW + timedelta(minutes=5))
    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_HEARTBEAT_STALE"):
        validate_activation_heartbeat(heartbeat, gate, now=NOW + timedelta(hours=1, minutes=5, seconds=1))


def test_gate_and_heartbeat_expiry_boundaries_are_exclusive() -> None:
    control = FakeControlPlane()
    objects = FakeObjectPlane()
    preflight = check_activation(_config(), control, objects, now=NOW)
    gate = seal_activation(_config(), preflight, objects, now=NOW)
    heartbeat = heartbeat_activation(_config(), gate, control, objects, now=NOW)

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_HEARTBEAT_STALE"):
        validate_activation_gate(
            gate,
            now=datetime.fromisoformat(gate["valid_until"].replace("Z", "+00:00")),
        )
    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_HEARTBEAT_STALE"):
        validate_activation_heartbeat(
            heartbeat,
            gate,
            now=datetime.fromisoformat(
                heartbeat["valid_until"].replace("Z", "+00:00")
            ),
        )


def test_hashed_documents_cannot_extend_hard_or_configured_lease_limits() -> None:
    control = FakeControlPlane()
    objects = FakeObjectPlane()
    preflight = check_activation(_config(), control, objects, now=NOW)
    gate = seal_activation(_config(), preflight, objects, now=NOW)
    heartbeat = heartbeat_activation(_config(), gate, control, objects, now=NOW)

    long_gate = deepcopy(gate)
    long_gate["valid_until"] = "2027-08-02T12:00:00Z"
    _rehash(long_gate, "gate_payload_sha256")
    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_TIME_INVALID"):
        validate_activation_gate(long_gate, now=NOW)

    long_heartbeat = deepcopy(heartbeat)
    long_heartbeat["valid_until"] = "2026-08-02T15:00:00Z"
    _rehash(long_heartbeat, "heartbeat_payload_sha256")
    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_HEARTBEAT_INVALID"):
        validate_activation_heartbeat(long_heartbeat, gate, now=NOW)

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_TIME_INVALID"):
        validate_local_activation(
            replace(_config(), gate_ttl_seconds=3600),
            gate,
            heartbeat,
            now=NOW,
        )

    short_gate_config = replace(_config(), gate_ttl_seconds=3600)
    short_gate = seal_activation(short_gate_config, preflight, objects, now=NOW)
    short_heartbeat = heartbeat_activation(
        short_gate_config, short_gate, control, objects, now=NOW
    )
    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_HEARTBEAT_INVALID"):
        validate_local_activation(
            replace(short_gate_config, heartbeat_ttl_seconds=300),
            short_gate,
            short_heartbeat,
            now=NOW,
        )


def test_heartbeat_rejects_a_tampered_gate_without_data_plane_calls() -> None:
    control = FakeControlPlane()
    objects = FakeObjectPlane()
    preflight = check_activation(_config(), control, objects, now=NOW)
    gate = seal_activation(_config(), preflight, objects, now=NOW)
    gate["target_binding_sha256"] = "0" * 64
    heads_before = objects.head_calls

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_GATE_INVALID"):
        heartbeat_activation(_config(), gate, control, objects, now=NOW + timedelta(minutes=1))

    assert objects.head_calls == heads_before


def test_gate_and_heartbeat_reject_future_timestamps() -> None:
    control = FakeControlPlane()
    objects = FakeObjectPlane()
    preflight = check_activation(_config(), control, objects, now=NOW)
    gate = seal_activation(_config(), preflight, objects, now=NOW)
    heartbeat = heartbeat_activation(
        _config(), gate, control, objects, now=NOW + timedelta(minutes=5)
    )

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_TIME_INVALID"):
        validate_activation_gate(gate, now=NOW - timedelta(seconds=1))
    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_HEARTBEAT_INVALID"):
        validate_activation_heartbeat(heartbeat, gate, now=NOW + timedelta(minutes=4))

    pre_gate_heartbeat = dict(heartbeat)
    pre_gate_heartbeat["checked_at"] = "2026-08-02T11:59:00Z"
    pre_gate_heartbeat["valid_until"] = "2026-08-02T12:59:00Z"
    _rehash(pre_gate_heartbeat, "heartbeat_payload_sha256")
    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_HEARTBEAT_INVALID"):
        validate_activation_heartbeat(pre_gate_heartbeat, gate, now=NOW)


def test_local_validation_is_file_only_and_constructs_no_remote_clients(tmp_path, capsys) -> None:
    control = FakeControlPlane()
    objects = FakeObjectPlane()
    live_now = datetime.now(timezone.utc).replace(microsecond=0)
    preflight = check_activation(_config(), control, objects, now=live_now)
    gate = seal_activation(_config(), preflight, objects, now=live_now)
    heartbeat = heartbeat_activation(_config(), gate, control, objects, now=live_now)
    gate_path = tmp_path / "gate.json"
    heartbeat_path = tmp_path / "heartbeat.json"
    gate_path.write_bytes(canonical_json_bytes(gate))
    heartbeat_path.write_bytes(canonical_json_bytes(heartbeat))
    calls_before = (list(control.calls), objects.head_calls, list(objects.get_calls), list(objects.put_calls))

    result = main(
        [
            "--mode", "validate",
            "--gate-file", str(gate_path),
            "--heartbeat-file", str(heartbeat_path),
        ],
        environ=_environment(),
    )

    assert result == 0
    assert '"state":"ready"' in capsys.readouterr().out
    assert calls_before == (control.calls, objects.head_calls, objects.get_calls, objects.put_calls)
    validate_local_activation(_config(), gate, heartbeat, now=live_now)


@pytest.mark.parametrize("link_kind", ("symlink", "hardlink"))
def test_local_validation_rejects_linked_activation_artifacts(
    tmp_path, capsys, link_kind: str
) -> None:
    control = FakeControlPlane()
    objects = FakeObjectPlane()
    live_now = datetime.now(timezone.utc).replace(microsecond=0)
    preflight = check_activation(_config(), control, objects, now=live_now)
    gate = seal_activation(_config(), preflight, objects, now=live_now)
    heartbeat = heartbeat_activation(_config(), gate, control, objects, now=live_now)
    canonical_gate = tmp_path / "canonical-gate.json"
    linked_gate = tmp_path / "linked-gate.json"
    heartbeat_path = tmp_path / "heartbeat.json"
    canonical_gate.write_bytes(canonical_json_bytes(gate))
    heartbeat_path.write_bytes(canonical_json_bytes(heartbeat))
    if link_kind == "symlink":
        linked_gate.symlink_to(canonical_gate)
    else:
        os.link(canonical_gate, linked_gate)

    result = main(
        [
            "--mode",
            "validate",
            "--gate-file",
            str(linked_gate),
            "--heartbeat-file",
            str(heartbeat_path),
        ],
        environ=_environment(),
    )

    assert result == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == (
        "biocatalyst-activation: BIOCATALYST_R2_ACTIVATION_GATE_INVALID"
    )


@pytest.mark.parametrize(
    "gate_bytes",
    (
        b'{"contract_id":"one","contract_id":"two"}',
        b"x" * 65537,
        b"[" * 1500 + b"0" + b"]" * 1500,
    ),
    ids=("duplicate-key", "oversized", "pathological-depth"),
)
def test_local_validation_rejects_malformed_bounded_gate_files(
    tmp_path, capsys, gate_bytes: bytes
) -> None:
    gate_path = tmp_path / "gate.json"
    heartbeat_path = tmp_path / "heartbeat.json"
    gate_path.write_bytes(gate_bytes)
    heartbeat_path.write_text("{}", encoding="utf-8")

    result = main(
        [
            "--mode",
            "validate",
            "--gate-file",
            str(gate_path),
            "--heartbeat-file",
            str(heartbeat_path),
        ],
        environ=_environment(),
    )

    assert result == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == (
        "biocatalyst-activation: BIOCATALYST_R2_ACTIVATION_GATE_INVALID"
    )


@pytest.mark.parametrize(
    ("label", "config_overrides", "environment_overrides"),
    (
        (
            "account",
            {
                "account_id": "c" * 32,
                "endpoint": f"https://{'c' * 32}.r2.cloudflarestorage.com",
            },
            {
                "BIOCATALYST_R2_CONTROL_ACCOUNT_ID": "c" * 32,
                "BIOCATALYST_R2_ENDPOINT": f"https://{'c' * 32}.r2.cloudflarestorage.com",
            },
        ),
        (
            "bucket",
            {"bucket": "biocatalyst-private-other"},
            {"BIOCATALYST_R2_BUCKET": "biocatalyst-private-other"},
        ),
        (
            "endpoint",
            {
                "jurisdiction": "eu",
                "endpoint": f"https://{ACCOUNT_ID}.eu.r2.cloudflarestorage.com",
            },
            {
                "BIOCATALYST_R2_JURISDICTION": "eu",
                "BIOCATALYST_R2_ENDPOINT": f"https://{ACCOUNT_ID}.eu.r2.cloudflarestorage.com",
            },
        ),
        (
            "access_key",
            {"worker_token_id": "d" * 32},
            {"BIOCATALYST_R2_ACCESS_KEY_ID": "d" * 32},
        ),
    ),
)
def test_local_validation_rejects_each_wrong_target_without_remote_calls(
    tmp_path, capsys, label, config_overrides, environment_overrides
) -> None:
    control = FakeControlPlane()
    objects = FakeObjectPlane()
    live_now = datetime.now(timezone.utc).replace(microsecond=0)
    preflight = check_activation(_config(), control, objects, now=live_now)
    gate = seal_activation(_config(), preflight, objects, now=live_now)
    heartbeat = heartbeat_activation(_config(), gate, control, objects, now=live_now)
    gate_path = tmp_path / f"{label}-gate.json"
    heartbeat_path = tmp_path / f"{label}-heartbeat.json"
    gate_path.write_bytes(canonical_json_bytes(gate))
    heartbeat_path.write_bytes(canonical_json_bytes(heartbeat))
    base = _config()
    wrong_config = ControlPlaneConfig(
        account_id=config_overrides.get("account_id", base.account_id),
        bucket=config_overrides.get("bucket", base.bucket),
        jurisdiction=config_overrides.get("jurisdiction", base.jurisdiction),
        endpoint=config_overrides.get("endpoint", base.endpoint),
        worker_token_id=config_overrides.get("worker_token_id", base.worker_token_id),
        gate_ttl_seconds=base.gate_ttl_seconds,
        heartbeat_ttl_seconds=base.heartbeat_ttl_seconds,
    )
    environment = _environment()
    environment.update(environment_overrides)
    calls_before = (list(control.calls), objects.head_calls, list(objects.get_calls), list(objects.put_calls))

    with pytest.raises(ActivationError, match="BIOCATALYST_R2_ACTIVATION_GATE_INVALID"):
        validate_local_activation(wrong_config, gate, heartbeat, now=live_now)
    result = main(
        [
            "--mode", "validate",
            "--gate-file", str(gate_path),
            "--heartbeat-file", str(heartbeat_path),
        ],
        environ=environment,
        control_plane=control,
        object_plane=objects,
    )

    assert result == 2
    assert "BIOCATALYST_R2_ACTIVATION_GATE_INVALID" in capsys.readouterr().err
    assert calls_before == (control.calls, objects.head_calls, objects.get_calls, objects.put_calls)


def test_cli_check_uses_injected_planes_and_never_constructs_network_clients(capsys) -> None:
    control = FakeControlPlane()
    objects = FakeObjectPlane()

    result = main(
        ["--mode", "check"],
        environ=_environment(),
        control_plane=control,
        object_plane=objects,
    )

    assert result == 0
    assert '"contract_id":"biocatalyst_retention_preflight.v1"' in capsys.readouterr().out
    assert objects.put_calls == []
