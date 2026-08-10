"""W1B.1 current-only SPY identity/calendar evidence contract."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.neuralweb import market_memory as mm
from engine.neuralweb import market_memory_identity as identity

OBSERVED = datetime(2026, 8, 10, 19, 20, 30, 123456, tzinfo=timezone.utc)
OBSERVED_TEXT = "2026-08-10T19:20:30.123456Z"
VALID_THROUGH = "2026-08-10T19:20:30.123457Z"


def _fixed_clock(monkeypatch: pytest.MonkeyPatch, value: datetime = OBSERVED) -> None:
    monkeypatch.setattr(identity, "_utc_now", lambda: value)


def _build(monkeypatch: pytest.MonkeyPatch) -> identity.CanaryIdentityEvidence:
    _fixed_clock(monkeypatch)
    return identity.build_current_spy_identity()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _config_copy(tmp_path: Path, mutate) -> Path:
    raw = json.loads(identity.DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "canary.json"
    path.write_text(json.dumps(raw, allow_nan=False), encoding="utf-8")
    return path


def _all_missing_features(observed_at: str) -> list[dict]:
    return [
        {
            "feature_id": feature_id,
            "feature_role": "decision_time_context",
            "domain": spec.domain,
            "status": "missing",
            "value": None,
            "unit": spec.unit,
            "observed_at": observed_at,
            "pit_basis": "unknown",
            "transform_version": "market_memory.missing.v1",
            "source_receipt_ids": [],
            "missing_reason": "adapter_not_implemented",
            "quality": {
                "status": "missing",
                "flags": ["not_captured"],
                "staleness_seconds": None,
                "imputed": False,
            },
        }
        for feature_id, spec in mm.CANONICAL_FEATURE_REGISTRY.items()
    ]


def test_builds_exact_current_spy_packet_inputs_from_one_process_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def clock() -> datetime:
        nonlocal calls
        calls += 1
        return OBSERVED

    monkeypatch.setattr(identity, "_utc_now", clock)
    evidence = identity.build_current_spy_identity()

    assert calls == 1
    assert evidence.observed_at == OBSERVED_TEXT
    assert evidence.subject == {
        "subject_id": (
            "mmsecurity_5fc37e8db34f74314b654c910ea8bacf"
            "a7de8b5d2d067f2e5421c9d5745ceb4c"
        ),
        "instrument_id": (
            "mmsecurity_6f361f5bad9f06a3b2ff157585d5728f"
            "55f77198420959aadd8922d1045c3fea"
        ),
    }
    assert evidence.membership_artifact["symbol"] == "SPY"
    assert evidence.membership_artifact["mic"] == "ARCX"
    assert evidence.membership_artifact["currency"] == "USD"
    assert evidence.membership_artifact["membership_status"] == "market_scope"
    assert evidence.calendar_artifact["market_session"] == "XNYS_REGULAR"
    assert evidence.membership_artifact["valid_from"] == OBSERVED_TEXT
    assert evidence.membership_artifact["valid_through"] == VALID_THROUGH
    assert evidence.calendar_artifact["valid_from"] == OBSERVED_TEXT
    assert evidence.calendar_artifact["valid_through"] == VALID_THROUGH


def test_artifacts_hash_exact_canonical_bytes_and_receipts_bind_every_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _build(monkeypatch)
    receipts = {row["source_id"]: row for row in evidence.source_receipts}

    assert evidence.membership_artifact_bytes == _canonical_bytes(
        evidence.membership_artifact
    )
    assert evidence.calendar_artifact_bytes == _canonical_bytes(
        evidence.calendar_artifact
    )
    assert (
        receipts[identity.MEMBERSHIP_SOURCE_ID]["artifact_sha256"]
        == hashlib.sha256(evidence.membership_artifact_bytes).hexdigest()
    )
    assert (
        receipts[identity.CALENDAR_SOURCE_ID]["artifact_sha256"]
        == hashlib.sha256(evidence.calendar_artifact_bytes).hexdigest()
    )
    for receipt in receipts.values():
        assert receipt["receipt_id"] == mm._source_receipt_id(receipt)
        assert receipt["vintage_id"].startswith("mmv_")
        assert receipt["revision_id"].startswith("mmr_")
        assert receipt["identity_binding"][
            "content_sha256"
        ] == mm._identity_binding_sha256(receipt, receipt["identity_binding"])
    assert evidence.identity_receipt["receipt_id"] == mm._identity_receipt_id(
        evidence.identity_receipt
    )
    assert (
        evidence.config_sha256
        == hashlib.sha256(identity.DEFAULT_CONFIG_PATH.read_bytes()).hexdigest()
    )
    assert identity.validate_canary_identity_evidence(evidence) == evidence


def test_identity_inputs_pass_the_frozen_w0_packet_constructor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _build(monkeypatch)

    packet = mm.build_as_known_at_context(
        subject=copy.deepcopy(evidence.subject),
        event_time=evidence.observed_at,
        as_known_at=evidence.observed_at,
        mode="operational_pit",
        source_receipts=copy.deepcopy(list(evidence.source_receipts)),
        identity_receipt=copy.deepcopy(evidence.identity_receipt),
        feature_receipts=_all_missing_features(evidence.observed_at),
    )

    assert mm.validate_as_known_at_context(packet) == packet
    assert packet["authority"] == dict(mm.AUTHORITY)
    assert packet["identity_receipt"]["membership_status"] == "market_scope"
    assert packet["identity_receipt"]["pit_basis"] == "live_captured"


def test_calendar_and_derived_identity_are_honestly_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = _build(monkeypatch)
    receipts = {row["source_id"]: row for row in evidence.source_receipts}

    assert receipts[identity.MEMBERSHIP_SOURCE_ID]["quality"] == {
        "status": "ok",
        "flags": [],
        "staleness_seconds": 0,
        "imputed": False,
    }
    expected_degraded = {
        "status": "degraded",
        "flags": ["partial_coverage"],
        "staleness_seconds": 0,
        "imputed": False,
    }
    assert receipts[identity.CALENDAR_SOURCE_ID]["quality"] == expected_degraded
    assert evidence.calendar_artifact["quality"] == expected_degraded
    assert evidence.identity_receipt["quality"] == expected_degraded
    assert evidence.calendar_artifact["coverage"] == "full_day_closures_only"


def test_stable_ids_survive_later_actual_observations_but_receipts_append(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixed_clock(monkeypatch, OBSERVED)
    first = identity.build_current_spy_identity()
    _fixed_clock(monkeypatch, OBSERVED + timedelta(seconds=1))
    second = identity.build_current_spy_identity()

    assert second.subject == first.subject
    assert (
        second.membership_artifact["identity_version"]
        == first.membership_artifact["identity_version"]
    )
    assert (
        second.membership_artifact["universe_id"]
        == first.membership_artifact["universe_id"]
    )
    assert (
        second.calendar_artifact["calendar_id"]
        == first.calendar_artifact["calendar_id"]
    )
    assert second.observed_at != first.observed_at
    assert [row["receipt_id"] for row in second.source_receipts] != [
        row["receipt_id"] for row in first.source_receipts
    ]
    assert second.identity_receipt["receipt_id"] != first.identity_receipt["receipt_id"]


@pytest.mark.parametrize("symbol", ["AAPL", "spy", "", "SPY "])
def test_rejects_every_noncanonical_or_non_spy_subject(symbol: str) -> None:
    with pytest.raises(identity.MarketMemoryIdentityError, match="SPY"):
        identity.build_current_spy_identity(symbol)


@pytest.mark.parametrize(
    "as_of", ["2026-08-07T20:00:00Z", datetime(2026, 8, 7, tzinfo=timezone.utc)]
)
def test_rejects_historical_resolution(as_of: object) -> None:
    with pytest.raises(identity.MarketMemoryIdentityError, match="historical"):
        identity.build_current_spy_identity(as_of=as_of)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda raw: raw.update({"unknown": True}), "fields or schema"),
        (
            lambda raw: raw["subject"].update({"subject_id": "mmsecurity_" + "0" * 64}),
            "opaque IDs",
        ),
        (lambda raw: raw["subject"].update({"mic": "XNAS"}), "ARCX/USD"),
        (lambda raw: raw["subject"].update({"currency": "CAD"}), "ARCX/USD"),
        (
            lambda raw: raw["universe"].update({"membership_status": "member"}),
            "market_scope",
        ),
        (
            lambda raw: raw["calendar"].update({"market_session": "MARS_REGULAR"}),
            "market session",
        ),
        (
            lambda raw: raw["calendar"].update({"coverage": "complete"}),
            "overstate",
        ),
        (
            lambda raw: raw["calendar"]["quality"].update({"status": "ok"}),
            "partial coverage",
        ),
        (
            lambda raw: raw["authority"].update({"may_rank": True}),
            "context-only",
        ),
    ],
)
def test_rejects_tampered_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    _fixed_clock(monkeypatch)
    path = _config_copy(tmp_path, mutate)
    with pytest.raises(identity.MarketMemoryIdentityError, match=message):
        identity.build_current_spy_identity(config_path=path)


def test_rejects_duplicate_nonfinite_and_symlink_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _fixed_clock(monkeypatch)
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
    with pytest.raises(identity.MarketMemoryIdentityError, match="duplicate"):
        identity.build_current_spy_identity(config_path=duplicate)

    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"value":NaN}', encoding="utf-8")
    with pytest.raises(identity.MarketMemoryIdentityError, match="non-finite"):
        identity.build_current_spy_identity(config_path=nonfinite)

    linked = tmp_path / "linked.json"
    linked.symlink_to(identity.DEFAULT_CONFIG_PATH)
    with pytest.raises(identity.MarketMemoryIdentityError, match="non-symlink"):
        identity.build_current_spy_identity(config_path=linked)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda evidence: evidence.membership_artifact.update({"symbol": "AAPL"}),
        lambda evidence: setattr(
            evidence,
            "membership_artifact_bytes",
            evidence.membership_artifact_bytes + b"\n",
        ),
        lambda evidence: evidence.source_receipts[0].update(
            {"revision_id": "mmr_" + "0" * 64}
        ),
        lambda evidence: evidence.source_receipts[1]["identity_binding"].update(
            {"content_sha256": "0" * 64}
        ),
        lambda evidence: evidence.source_receipts[1].update(
            {
                "quality": {
                    "status": "ok",
                    "flags": [],
                    "staleness_seconds": 0,
                    "imputed": False,
                }
            }
        ),
        lambda evidence: evidence.identity_receipt.update(
            {
                "quality": {
                    "status": "ok",
                    "flags": [],
                    "staleness_seconds": 0,
                    "imputed": False,
                }
            }
        ),
        lambda evidence: evidence.calendar_artifact.update(
            {"market_session": "GLOBAL_24H"}
        ),
    ],
)
def test_validator_rejects_artifact_receipt_binding_and_quality_tamper(
    monkeypatch: pytest.MonkeyPatch, mutate
) -> None:
    evidence = copy.deepcopy(_build(monkeypatch))
    if mutate.__code__.co_names and "setattr" in mutate.__code__.co_names:
        # frozen dataclass fields cannot be reassigned through ordinary code;
        # object.__setattr__ models bytes received from an untrusted deserializer.
        object.__setattr__(
            evidence,
            "membership_artifact_bytes",
            evidence.membership_artifact_bytes + b"\n",
        )
    else:
        mutate(evidence)
    with pytest.raises(identity.MarketMemoryIdentityError):
        identity.validate_canary_identity_evidence(evidence)


@pytest.mark.parametrize(
    "clock",
    [
        OBSERVED.replace(tzinfo=None),
        datetime(2026, 8, 10, 12, 20, 30, tzinfo=timezone(timedelta(hours=-7))),
        datetime(9999, 1, 1, tzinfo=timezone.utc),
    ],
)
def test_rejects_non_utc_or_unrepresentable_process_clock(
    monkeypatch: pytest.MonkeyPatch, clock: datetime
) -> None:
    _fixed_clock(monkeypatch, clock)
    with pytest.raises(identity.MarketMemoryIdentityError, match="clock"):
        identity.build_current_spy_identity()
