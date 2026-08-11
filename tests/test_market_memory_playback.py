"""Hostile W3A tests for exact actual-output playback catalog pages."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from engine.neuralweb import market_memory as mm
from engine.neuralweb import market_memory_pit as pit
from engine.neuralweb import market_memory_playback as playback
from engine.neuralweb import market_memory_trusted as trusted
from tests.test_market_memory_pit import CUTOFF, _packet, _rebuild
from tests.test_market_memory_trusted import (
    CAPTURE_CLOCK,
    _candidate,
    _capture,
    _missing_packet_from_trusted,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = (
    ROOT / "contracts" / "market_memory" / "operational_playback_catalog.v1.schema.json"
)
W3A_CI_PATHS = (
    "app/market_memory.py",
    "app/deploy/update.sh",
    "engine/neuralweb/market_memory_pit.py",
    "engine/neuralweb/market_memory_playback.py",
    "engine/neuralweb/market_memory_trusted.py",
    "contracts/market_memory/operational_playback_catalog.v1.schema.json",
    "tests/test_market_memory_pit.py",
    "tests/test_market_memory_playback.py",
    "tests/test_market_memory_playback_api.py",
    "tests/test_market_memory_trusted.py",
    "research/KONSEKI_CLEAN_ROOM_MARKET_MEMORY_AND_COGNITIVE_ARCHITECTURE_FOR_FABLE_2026-08-08.md",
)


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _packet_at(seconds: int) -> mm.AsKnownAtContext:
    base = _packet()
    sources = copy.deepcopy(base["source_receipts"])
    for source in sources:
        source["age_at_cutoff_seconds"] += seconds
    return _rebuild(
        base,
        as_known_at=_utc(CUTOFF + timedelta(seconds=seconds)),
        source_receipts=sources,
    )


def _capture_w1a(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    *,
    seconds: int,
) -> pit.StoredMarketMemoryContext:
    packet = _packet_at(seconds)
    monkeypatch.setattr(
        pit,
        "_utc_now",
        lambda: CUTOFF + timedelta(seconds=seconds + 30),
    )
    return pit.capture_context(root, packet)


def _composite(tmp_path: Path) -> tuple[trusted.CompositeAsKnownAtReader, Path, Path]:
    w1a_root = tmp_path / "w1a"
    trusted_root = tmp_path / "trusted-v1"
    trusted.initialize_trusted_store(trusted_root)
    return (
        trusted.CompositeAsKnownAtReader(w1a_root, trusted_root),
        w1a_root,
        trusted_root,
    )


def _schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = {str(key).lower() for key in value}
        for nested in value.values():
            keys.update(_all_keys(nested))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for nested in value:
            keys.update(_all_keys(nested))
        return keys
    return set()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def test_catalog_is_schema_valid_content_addressed_and_value_free(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader, w1a_root, _trusted_root = _composite(tmp_path)
    older = _capture_w1a(monkeypatch, w1a_root, seconds=0)
    newer = _capture_w1a(monkeypatch, w1a_root, seconds=60)

    catalog = playback.read_operational_playback_catalog(
        reader=reader,
        subject=newer.packet["subject"],
        limit=1,
    )

    _schema_validator().validate(catalog)
    assert playback.validate_operational_playback_catalog(catalog) == catalog
    assert catalog["catalog_id"] == playback._content_id(catalog)
    assert catalog["entries"][0]["context_id"] == newer.packet["context_id"]
    assert catalog["selection"] == {
        "offset": 0,
        "limit": 1,
        "ordering": "as_known_at_desc.event_time_desc.query_id_asc.context_id_asc.v1",
        "total_matching": 2,
        "returned": 1,
        "truncated": True,
        "continuation": {
            "subject": newer.packet["subject"],
            "w1a_generation_id": catalog["generations"][0]["generation_id"],
            "trusted_generation_id": catalog["generations"][1]["generation_id"],
            "offset": 1,
            "limit": 1,
        },
    }
    assert catalog["coverage"] == {
        "receipt_index_scan_complete": True,
        "returned_entries_packet_closure_validated": True,
        "off_page_packets_validated": False,
        "captured_opportunity_population_complete": False,
        "historical_coverage_complete": False,
        "cross_store_atomic_snapshot": False,
    }
    assert catalog["authority"] == dict(mm.AUTHORITY)
    assert catalog["entries"][0]["capture_provenance"] == [
        {
            "profile": pit.STORE_PROFILE,
            "capture_id": newer.capture_receipt["capture_id"],
            "captured_at": newer.capture_receipt["captured_at"],
        }
    ]
    assert [row["domain"] for row in catalog["entries"][0]["domain_states"]] == list(
        mm.CANONICAL_CONTEXT_DOMAINS
    )
    assert {row["status"] for row in catalog["entries"][0]["domain_states"]} == {
        "missing"
    }
    forbidden = {
        "value",
        "object_key",
        "source_evidence",
        "source_receipts",
        "feature_receipts",
        "outcome",
        "outcomes",
        "score",
        "scores",
        "open_interest",
        "ticker",
        "path",
    }
    assert not (_all_keys(catalog) & forbidden)
    assert older.packet["context_id"] not in {
        row["context_id"] for row in catalog["entries"]
    }


def test_generation_pair_and_offset_keep_pages_stable_after_head_advance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader, w1a_root, _trusted_root = _composite(tmp_path)
    oldest = _capture_w1a(monkeypatch, w1a_root, seconds=0)
    middle = _capture_w1a(monkeypatch, w1a_root, seconds=60)
    first = playback.read_operational_playback_catalog(
        reader=reader, subject=middle.packet["subject"], limit=1
    )
    recipe = first["selection"]["continuation"]
    assert recipe is not None

    newest = _capture_w1a(monkeypatch, w1a_root, seconds=120)
    continued = playback.read_operational_playback_catalog(
        reader=reader,
        subject=recipe["subject"],
        w1a_generation_id=recipe["w1a_generation_id"],
        trusted_generation_id=recipe["trusted_generation_id"],
        offset=recipe["offset"],
        limit=recipe["limit"],
    )
    current = playback.read_operational_playback_catalog(
        reader=reader, subject=newest.packet["subject"], limit=100
    )

    assert continued["selection"]["total_matching"] == 2
    assert continued["entries"][0]["context_id"] == oldest.packet["context_id"]
    assert continued["selection"]["continuation"] is None
    assert current["selection"]["total_matching"] == 3
    assert current["entries"][0]["context_id"] == newest.packet["context_id"]


def test_unpinned_offset_partial_pins_and_bad_pagination_reject(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader, w1a_root, _trusted_root = _composite(tmp_path)
    stored = _capture_w1a(monkeypatch, w1a_root, seconds=0)
    first = playback.read_operational_playback_catalog(
        reader=reader, subject=stored.packet["subject"]
    )
    w1a_id = first["generations"][0]["generation_id"]

    with pytest.raises(playback.MarketMemoryPlaybackContractError, match="offset zero"):
        playback.read_operational_playback_catalog(
            reader=reader, subject=stored.packet["subject"], offset=1
        )
    with pytest.raises(
        playback.MarketMemoryPlaybackContractError, match="supplied together"
    ):
        playback.read_operational_playback_catalog(
            reader=reader,
            subject=stored.packet["subject"],
            w1a_generation_id=w1a_id,
        )
    for field, value in (
        ("offset", True),
        ("offset", -1),
        ("limit", False),
        ("limit", 101),
    ):
        kwargs = {field: value}
        with pytest.raises(playback.MarketMemoryPlaybackContractError):
            playback.read_operational_playback_catalog(
                reader=reader,
                subject=stored.packet["subject"],
                **kwargs,
            )


def test_absent_subject_is_exact_empty_without_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader, w1a_root, _trusted_root = _composite(tmp_path)
    _capture_w1a(monkeypatch, w1a_root, seconds=0)
    absent = {
        "subject_id": "mmsecurity_" + "a" * 64,
        "instrument_id": "mmsecurity_" + "b" * 64,
    }

    catalog = playback.read_operational_playback_catalog(reader=reader, subject=absent)

    assert catalog["selection"]["total_matching"] == 0
    assert catalog["selection"]["returned"] == 0
    assert catalog["selection"]["continuation"] is None
    assert catalog["entries"] == []
    assert catalog["replay_policy"]["nearest_fallback"] is False
    assert catalog["replay_policy"]["latest_fallback"] is False


def test_returned_packet_reads_have_an_aggregate_byte_bound(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader, w1a_root, _trusted_root = _composite(tmp_path)
    stored = _capture_w1a(monkeypatch, w1a_root, seconds=0)
    monkeypatch.setattr(playback, "_MAX_RETURNED_PACKET_BYTES", 1)

    with pytest.raises(pit.MarketMemoryStoreError, match="aggregate byte bound"):
        playback.read_operational_playback_catalog(
            reader=reader, subject=stored.packet["subject"]
        )


def test_w3a_contract_runtime_and_tests_share_the_market_memory_ci_gate() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    jobs = (ROOT / ".github/ci/legacy-jobs.yml").read_text(encoding="utf-8")
    lane = jobs.split("  market-memory-contract:", 1)[1].split("\n  group-pulse:", 1)[0]

    for path in W3A_CI_PATHS:
        assert f'      - "{path}"' in workflow, f"missing W3A CI trigger: {path}"
    assert "tests/test_market_memory_playback.py" in lane
    assert "tests/test_market_memory_playback_api.py" in lane


def test_unequal_same_query_packets_across_stores_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = _candidate(monkeypatch, tmp_path)
    trusted_stored = _capture(candidate)
    conflicting = _missing_packet_from_trusted(trusted_stored.packet)
    w1a_root = tmp_path / "conflict-w1a"
    monkeypatch.setattr(pit, "_utc_now", lambda: CAPTURE_CLOCK)
    pit.capture_context(w1a_root, conflicting)
    reader = trusted.CompositeAsKnownAtReader(w1a_root, candidate.public)

    with pytest.raises(pit.MarketMemoryStoreError, match="ambiguously published"):
        playback.read_operational_playback_catalog(
            reader=reader, subject=trusted_stored.packet["subject"]
        )


def test_identical_cross_store_query_keeps_both_capture_provenances(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader, w1a_root, _trusted_root = _composite(tmp_path)
    stored = _capture_w1a(monkeypatch, w1a_root, seconds=0)
    w1a_generation = reader.w1a.read_pinned_generation()
    w1a_receipt = stored.capture_receipt
    trusted_capture_id = "mmcapture_" + "c" * 64
    trusted_store_id = "mmstore_" + "d" * 64
    trusted_generation = pit.PinnedGenerationSnapshot(
        profile=trusted.TRUSTED_STORE_PROFILE,
        store_id=trusted_store_id,
        generation_id="mmgeneration_" + "e" * 64,
        generation_sha256="f" * 64,
        captures=(
            pit.PinnedCaptureIndexEntry(
                query_id=w1a_receipt["query_id"],
                context_id=w1a_receipt["context_id"],
                capture_id=trusted_capture_id,
                packet_sha256=w1a_receipt["packet_sha256"],
            ),
        ),
    )
    trusted_receipt = copy.deepcopy(w1a_receipt)
    trusted_receipt.update(
        {
            "store_id": trusted_store_id,
            "capture_id": trusted_capture_id,
            "captured_at": _utc(CUTOFF + timedelta(seconds=31)),
        }
    )
    trusted_stored = pit.StoredMarketMemoryContext(stored.packet, trusted_receipt)
    w1a_load = reader.w1a.read_stored_from_pinned_generation
    loaded_profiles: list[str] = []

    def load_w1a(
        generation: pit.PinnedGenerationSnapshot, *, query_id: str
    ) -> pit.StoredMarketMemoryContext:
        loaded_profiles.append(pit.STORE_PROFILE)
        return w1a_load(generation, query_id=query_id)

    def load_trusted(
        generation: pit.PinnedGenerationSnapshot, *, query_id: str
    ) -> pit.StoredMarketMemoryContext:
        loaded_profiles.append(trusted.TRUSTED_STORE_PROFILE)
        return trusted_stored

    monkeypatch.setattr(reader.w1a, "read_stored_from_pinned_generation", load_w1a)
    monkeypatch.setattr(
        reader.trusted,
        "read_pinned_generation",
        lambda *, generation_id=None: trusted_generation,
    )
    monkeypatch.setattr(
        reader.trusted,
        "read_pinned_capture_receipt",
        lambda generation, *, query_id: copy.deepcopy(trusted_receipt),
    )
    monkeypatch.setattr(
        reader.trusted,
        "read_stored_from_pinned_generation",
        load_trusted,
    )

    catalog = playback.build_operational_playback_catalog(
        reader=reader,
        w1a_generation=w1a_generation,
        trusted_generation=trusted_generation,
        subject=stored.packet["subject"],
    )

    assert catalog["selection"]["total_matching"] == 1
    assert catalog["entries"][0]["capture_provenance"] == [
        {
            "profile": pit.STORE_PROFILE,
            "capture_id": w1a_receipt["capture_id"],
            "captured_at": w1a_receipt["captured_at"],
        },
        {
            "profile": trusted.TRUSTED_STORE_PROFILE,
            "capture_id": trusted_capture_id,
            "captured_at": trusted_receipt["captured_at"],
        },
    ]
    assert loaded_profiles == [pit.STORE_PROFILE, trusted.TRUSTED_STORE_PROFILE]

    def missing_w1a(
        generation: pit.PinnedGenerationSnapshot, *, query_id: str
    ) -> pit.StoredMarketMemoryContext:
        raise pit.MarketMemoryStoreError("alternate W1A packet is missing")

    monkeypatch.setattr(reader.w1a, "read_stored_from_pinned_generation", missing_w1a)
    with pytest.raises(pit.MarketMemoryStoreError, match="alternate W1A packet"):
        playback.build_operational_playback_catalog(
            reader=reader,
            w1a_generation=w1a_generation,
            trusted_generation=trusted_generation,
            subject=stored.packet["subject"],
        )


def test_schema_runtime_parity_for_strict_shape_policy_and_authority(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader, w1a_root, _trusted_root = _composite(tmp_path)
    stored = _capture_w1a(monkeypatch, w1a_root, seconds=0)
    catalog = playback.read_operational_playback_catalog(
        reader=reader, subject=stored.packet["subject"]
    )
    validator = _schema_validator()
    mutations = []
    extra = copy.deepcopy(catalog)
    extra["unexpected"] = False
    mutations.append(extra)
    wrong_mode = copy.deepcopy(catalog)
    wrong_mode["mode"] = "public_reconstruction"
    mutations.append(wrong_mode)
    authority = copy.deepcopy(catalog)
    authority["authority"]["proposal_weight"] = 1
    mutations.append(authority)
    coverage = copy.deepcopy(catalog)
    coverage["coverage"]["historical_coverage_complete"] = True
    mutations.append(coverage)
    domain_order = copy.deepcopy(catalog)
    domain_order["entries"][0]["domain_states"].reverse()
    mutations.append(domain_order)
    provenance = copy.deepcopy(catalog)
    provenance["entries"][0]["capture_provenance"][0].pop("captured_at")
    mutations.append(provenance)
    timestamp = copy.deepcopy(catalog)
    timestamp["entries"][0]["as_known_at"] = (
        timestamp["entries"][0]["as_known_at"].removesuffix("Z") + "+00:00"
    )
    mutations.append(timestamp)
    zero_fraction = copy.deepcopy(catalog)
    zero_fraction["entries"][0]["as_known_at"] = (
        zero_fraction["entries"][0]["as_known_at"].removesuffix("Z") + ".000000Z"
    )
    mutations.append(zero_fraction)
    duplicate_profile = copy.deepcopy(catalog)
    second_capture = copy.deepcopy(
        duplicate_profile["entries"][0]["capture_provenance"][0]
    )
    second_capture["capture_id"] = "mmcapture_" + "9" * 64
    duplicate_profile["entries"][0]["capture_provenance"].append(second_capture)
    mutations.append(duplicate_profile)
    reversed_profiles = copy.deepcopy(catalog)
    first_capture = reversed_profiles["entries"][0]["capture_provenance"][0]
    trusted_capture = copy.deepcopy(first_capture)
    trusted_capture["profile"] = trusted.TRUSTED_STORE_PROFILE
    trusted_capture["capture_id"] = "mmcapture_" + "8" * 64
    reversed_profiles["entries"][0]["capture_provenance"] = [
        trusted_capture,
        first_capture,
    ]
    mutations.append(reversed_profiles)

    for mutation in mutations:
        mutation["catalog_id"] = playback._content_id(mutation)
        with pytest.raises(playback.MarketMemoryPlaybackContractError):
            playback.validate_operational_playback_catalog(mutation)
        with pytest.raises(ValidationError):
            validator.validate(mutation)


def test_runtime_rejects_impossible_totals_and_untyped_snapshot_arguments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader, w1a_root, _trusted_root = _composite(tmp_path)
    stored = _capture_w1a(monkeypatch, w1a_root, seconds=0)
    catalog = playback.read_operational_playback_catalog(
        reader=reader, subject=stored.packet["subject"]
    )
    impossible = copy.deepcopy(catalog)
    impossible["selection"]["limit"] = 1
    impossible["selection"]["total_matching"] = 2
    impossible["selection"]["returned"] = 1
    impossible["selection"]["truncated"] = True
    impossible["selection"]["continuation"] = {
        "subject": impossible["subject"],
        "w1a_generation_id": impossible["generations"][0]["generation_id"],
        "trusted_generation_id": impossible["generations"][1]["generation_id"],
        "offset": 1,
        "limit": 1,
    }
    impossible["catalog_id"] = playback._content_id(impossible)
    with pytest.raises(
        playback.MarketMemoryPlaybackContractError, match="exceeds pinned"
    ):
        playback.validate_operational_playback_catalog(impossible)

    with pytest.raises(
        playback.MarketMemoryPlaybackContractError, match="PinnedGenerationSnapshot"
    ):
        playback.build_operational_playback_catalog(
            reader=reader,
            w1a_generation={},  # type: ignore[arg-type]
            trusted_generation=reader.trusted.read_pinned_generation(),
            subject=stored.packet["subject"],
        )


def test_runtime_recomputes_query_id_from_catalog_subject_and_entry_clocks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader, w1a_root, _trusted_root = _composite(tmp_path)
    stored = _capture_w1a(monkeypatch, w1a_root, seconds=0)
    catalog = playback.read_operational_playback_catalog(
        reader=reader, subject=stored.packet["subject"]
    )
    relabelled = copy.deepcopy(catalog)
    relabelled["subject"] = {
        "subject_id": "mmsecurity_" + "7" * 64,
        "instrument_id": "mmsecurity_" + "8" * 64,
    }
    relabelled["catalog_id"] = playback._content_id(relabelled)
    changed_clock = copy.deepcopy(catalog)
    changed_clock["entries"][0]["event_time"] = "2026-08-07T19:59:59Z"
    changed_clock["catalog_id"] = playback._content_id(changed_clock)

    for hostile in (relabelled, changed_clock):
        _schema_validator().validate(hostile)
        with pytest.raises(
            playback.MarketMemoryPlaybackContractError, match="query_id does not bind"
        ):
            playback.validate_operational_playback_catalog(hostile)


def test_receipt_scan_count_and_aggregate_byte_bounds_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader, w1a_root, _trusted_root = _composite(tmp_path)
    stored = _capture_w1a(monkeypatch, w1a_root, seconds=0)
    monkeypatch.setattr(playback, "_MAX_SCAN_RECEIPTS", 0)
    with pytest.raises(pit.MarketMemoryStoreError, match="entry bound"):
        playback.read_operational_playback_catalog(
            reader=reader, subject=stored.packet["subject"]
        )

    monkeypatch.setattr(
        playback,
        "_MAX_SCAN_RECEIPTS",
        2 * pit._MAX_GENERATION_CAPTURES,
    )
    monkeypatch.setattr(playback, "_MAX_SCAN_RECEIPT_BYTES", 1)
    with pytest.raises(pit.MarketMemoryStoreError, match="byte bound"):
        playback.read_operational_playback_catalog(
            reader=reader, subject=stored.packet["subject"]
        )


def test_strict_loader_bounds_duplicates_nonfinite_and_canonical_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader, w1a_root, _trusted_root = _composite(tmp_path)
    stored = _capture_w1a(monkeypatch, w1a_root, seconds=0)
    catalog = playback.read_operational_playback_catalog(
        reader=reader, subject=stored.packet["subject"]
    )
    body = _canonical_bytes(catalog)

    assert playback.load_operational_playback_catalog_json(body) == catalog
    hostile = (
        b'{"schema":"market_memory.operational_playback_catalog.v1",'
        b'"schema":"market_memory.operational_playback_catalog.v1"}'
    )
    for payload in (
        json.dumps(catalog, indent=2).encode(),
        hostile,
        body.replace(b'"offset":0', b'"offset":NaN'),
        b"\xef\xbb\xbf" + body,
        b"x" * (playback._MAX_CATALOG_BYTES + 1),
    ):
        with pytest.raises(playback.MarketMemoryPlaybackContractError):
            playback.load_operational_playback_catalog_json(payload)
    with pytest.raises(playback.MarketMemoryPlaybackContractError):
        playback.load_operational_playback_catalog_json(bytearray(body))  # type: ignore[arg-type]


def test_read_is_pure_and_public_surface_has_no_reconstruction_scoring_or_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reader, w1a_root, trusted_root = _composite(tmp_path)
    stored = _capture_w1a(monkeypatch, w1a_root, seconds=0)
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    playback.read_operational_playback_catalog(
        reader=reader, subject=stored.packet["subject"]
    )

    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert w1a_root != trusted_root
    assert playback.__all__ == [
        "ACTUAL_OUTPUT_MODE",
        "OPERATIONAL_PLAYBACK_CATALOG_SCHEMA",
        "MarketMemoryPlaybackContractError",
        "build_operational_playback_catalog",
        "load_operational_playback_catalog_json",
        "read_operational_playback_catalog",
        "validate_operational_playback_catalog",
    ]
    public_names = {name.lower() for name in playback.__all__}
    for forbidden in (
        "reconstruct",
        "nearest",
        "latest",
        "score",
        "aggregate",
        "skill",
        "baseline",
        "outcome",
        "write",
        "capture",
        "store",
    ):
        assert not any(forbidden in name for name in public_names)
