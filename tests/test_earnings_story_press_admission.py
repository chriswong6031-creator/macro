from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path

import pytest

from engine.earnings_narrative.admission import (
    PRESS_ADMISSION_SCHEMA,
    ROOT_AUDIT_SCHEMA,
    build_press_admission,
    build_story_root_audit_binding,
    validate_press_admission,
    validate_story_root_audit_binding,
)
from engine.earnings_narrative.contracts import ContractError, canonical_json_bytes, sha256_bytes
from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.generation import EvidencePair, write_generation
from engine.earnings_narrative.story_store import write_story_packet_generation
from engine.earnings_transcript_intake import canonical_body_sha256
from scripts import publish_earnings_story_packets_r2 as publisher


def _body(*, sparse: bool = False, guidance: str = "For the full year, we expect revenue of 500 million and an operating margin of 20%.") -> dict:
    segments = [
        {
            "speaker": "Chief Executive Officer",
            "role": "executive",
            "text": "Revenue grew 12% to 120 million, while gross margin reached 45%.",
        },
        {"speaker": "Chief Financial Officer", "role": "executive", "text": guidance},
        {
            "speaker": "Chief Executive Officer",
            "role": "executive",
            "text": "We will invest 50 million in capacity and continue our share repurchase program.",
        },
    ]
    if sparse:
        segments = [{
            "speaker": "Chief Executive Officer",
            "role": "executive",
            "text": "Revenue was 100 million.",
        }]
    return {
        "schema": "mastermind.tx/v1",
        "ticker": "AAPL",
        "id": "2026Q1",
        "period": "Q1 FY2026",
        "date": "2026-01-30",
        "title": "AAPL earnings call",
        "segments": segments,
    }


def _write_evidence(root: Path, body: dict, *, generated_at: str) -> dict:
    body_sha = canonical_body_sha256(body)
    index = {
        "schema": "mastermind.tx-index/v1",
        "generated_at": generated_at,
        "symbols": {"AAPL": ["2026Q1"]},
        "revisions": {"AAPL/2026Q1": body_sha},
        "dates": {"AAPL/2026Q1": "2026-01-30"},
        "body_count": 1,
        "symbol_count": 1,
    }
    fact_pack, claim_graph = build_evidence_pair(
        body,
        index_payload=index,
        indexed_body_sha256=body_sha,
        index_generated_at=generated_at,
    )
    _generation, manifest = write_generation(
        root,
        [EvidencePair(fact_pack=fact_pack, claim_graph=claim_graph, transcript=body)],
        coverage={
            "selection_policy": "explicit_input",
            "batch_limit": 1,
            "historical_completeness": False,
            "index_body_count": 1,
            "index_generated_at": generated_at,
        },
    )
    return manifest


def _packet(store: Path, manifest: dict) -> dict:
    index = manifest["packets"]["AAPL/2026Q1"]
    receipt = manifest["files"][index["object_key"]]
    return json.loads((store / receipt["object_key"]).read_text(encoding="utf-8"))


def _current(tmp_path: Path, *, sparse: bool = False) -> tuple[Path, Path, dict, dict, dict]:
    evidence = tmp_path / "evidence"
    store = tmp_path / "story-packets"
    _write_evidence(evidence, _body(sparse=sparse), generated_at="2026-02-01T00:00:00Z")
    _generation, manifest = write_story_packet_generation(store, evidence)
    packet = _packet(store, manifest)
    audit = build_story_root_audit_binding(manifest, marker_etag='"stable"')
    return evidence, store, manifest, packet, audit


def test_stage_only_admission_binds_one_exact_current_tier_b_packet(tmp_path: Path) -> None:
    _evidence, _store, manifest, packet, audit = _current(tmp_path)
    admission = build_press_admission(audit, packet)
    assert admission["schema"] == PRESS_ADMISSION_SCHEMA
    assert admission["operation"] == "stage_only"
    assert admission["allow_emit"] is False
    assert admission["limits"] == {"max_candidates": 1, "max_model_calls": 1, "max_tokens": 12_000}
    assert admission["story_root"]["generation_id"] == manifest["generation_id"]
    assert admission["packet"]["packet_id"] == packet["packet_id"]
    assert admission["press_slot"]["sha256"] == sha256_bytes(canonical_json_bytes(packet["press_slot"]))
    validate_story_root_audit_binding(audit)
    validate_press_admission(admission, audit_binding=audit, packet=packet)
    with pytest.raises(TypeError):
        validate_press_admission(admission)


def test_admission_rejects_tier_c_and_legacy_packet_pointers(tmp_path: Path) -> None:
    _evidence, _store, _manifest, packet, audit = _current(tmp_path, sparse=True)
    assert packet["promotion"]["tier"] == "C"
    with pytest.raises(ContractError, match="Tier B"):
        build_press_admission(audit, packet)
    with pytest.raises(ContractError, match="must be an object"):
        build_press_admission(audit, "objects/not-a-packet.json")


def test_admission_rejects_historical_packet_and_accepts_verified_correction_parent(tmp_path: Path) -> None:
    evidence, store, _first_manifest, first_packet, _first_audit = _current(tmp_path)
    _write_evidence(
        evidence,
        _body(guidance="For the full year, we expect revenue of 510 million and an operating margin of 21%."),
        generated_at="2026-02-02T00:00:00Z",
    )
    _generation, current_manifest = write_story_packet_generation(store, evidence)
    corrected = _packet(store, current_manifest)
    current_audit = build_story_root_audit_binding(current_manifest, marker_etag='"corrected"')
    assert corrected["prior"]["packet_id"] == first_packet["packet_id"]
    assert build_press_admission(current_audit, corrected)["story"]["story_id"] == corrected["story"]["story_id"]
    forged_parent = deepcopy(corrected)
    forged_parent["prior"]["packet_id"] = "storypacket_" + "0" * 32
    with pytest.raises(ContractError):
        build_press_admission(current_audit, forged_parent)
    with pytest.raises(ContractError, match="current root receipt"):
        build_press_admission(current_audit, first_packet)


@pytest.mark.parametrize("field", ["root", "packet", "policy", "slot"])
def test_admission_rejects_root_packet_policy_and_slot_tamper(tmp_path: Path, field: str) -> None:
    _evidence, _store, _manifest, packet, audit = _current(tmp_path)
    admission = build_press_admission(audit, packet)
    forged = deepcopy(admission)
    if field == "root":
        forged["story_root"]["manifest_sha256"] = "0" * 64
    elif field == "packet":
        forged["packet"]["sha256"] = "0" * 64
    elif field == "policy":
        forged["policy"]["sha256"] = "0" * 64
    else:
        forged["press_slot"]["sha256"] = "0" * 64
    with pytest.raises(ContractError):
        validate_press_admission(forged, audit_binding=audit, packet=packet)


def test_admission_is_closed_against_manual_tier_paths_and_caller_slots(tmp_path: Path) -> None:
    _evidence, _store, _manifest, packet, audit = _current(tmp_path)
    admission = build_press_admission(audit, packet)
    for name, value in (
        ("tier", "A"),
        ("local_path", "/tmp/storypacket.json"),
        ("caller_slot", {"canonical_emit_allowed": True}),
    ):
        forged = deepcopy(admission)
        forged[name] = value
        with pytest.raises(ContractError, match="unsupported"):
            validate_press_admission(forged, audit_binding=audit, packet=packet)


class _Body:
    def __init__(self, value: bytes) -> None:
        self._value = value

    def read(self) -> bytes:
        return self._value


class _RootRaceR2:
    def __init__(
        self,
        first: dict,
        second: dict,
        objects: dict[str, bytes],
        *,
        initial_etag: str | None = '"root"',
        final_etag: str | None = '"root"',
    ) -> None:
        self.first = canonical_json_bytes(first)
        self.second = canonical_json_bytes(second)
        self.objects = objects
        self.root_reads = 0
        self.initial_etag = initial_etag
        self.final_etag = final_etag

    def get_object(self, *, Bucket: str, Key: str):  # noqa: N803
        if Key == f"{publisher.PREFIX}/manifest.json":
            self.root_reads += 1
            body = self.first if self.root_reads == 1 else self.second
            etag = self.initial_etag if self.root_reads == 1 else self.final_etag
            result = {"Body": _Body(body)}
            if etag is not None:
                result["ETag"] = etag
            return result
        if Key in self.objects:
            return {"Body": _Body(self.objects[Key])}
        raise RuntimeError("missing")

    def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str | None = None):  # noqa: N803
        assert ContinuationToken is None
        return {
            "IsTruncated": False,
            "Contents": [{"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)],
        }


class _VerifiedR2:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def get_object(self, *, Bucket: str, Key: str):  # noqa: N803
        body = self.objects.get(Key)
        if body is None:
            raise RuntimeError("missing")
        result = {"Body": io.BytesIO(body)}
        if Key == f"{publisher.PREFIX}/manifest.json":
            result["ETag"] = '"verified-root"'
        return result

    def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str | None = None):  # noqa: N803
        assert ContinuationToken is None
        return {
            "IsTruncated": False,
            "Contents": [{"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)],
        }


def _verified_r2(evidence: Path, store: Path, manifest: dict) -> _VerifiedR2:
    anchor = publisher._anchor_receipt(manifest)
    objects = {
        f"{publisher.PREFIX}/manifest.json": (store / "manifest.json").read_bytes(),
        f"{publisher.PREFIX}/generations/{manifest['generation_id']}/manifest.json": (
            store / "generations" / manifest["generation_id"] / "manifest.json"
        ).read_bytes(),
        publisher._journal_key("anchors", manifest["generation_id"]): canonical_json_bytes(anchor),
    }
    for receipt in manifest["files"].values():
        objects[f"{publisher.PREFIX}/{receipt['object_key']}"] = (store / receipt["object_key"]).read_bytes()
    evidence_manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
    objects[
        f"{publisher.EVIDENCE_PREFIX}/generations/{evidence_manifest['generation_id']}/manifest.json"
    ] = (evidence / "generations" / evidence_manifest["generation_id"] / "manifest.json").read_bytes()
    for receipt in evidence_manifest["files"].values():
        objects[f"{publisher.EVIDENCE_PREFIX}/{receipt['object_key']}"] = (
            evidence / receipt["object_key"]
        ).read_bytes()
    return _VerifiedR2(objects)


def test_transport_hydrates_and_replays_a_real_current_root(tmp_path: Path) -> None:
    evidence, store, manifest, packet, _audit = _current(tmp_path)
    binding = publisher.hydrate_and_verify_current_story_root(
        s3=_verified_r2(evidence, store, manifest), bucket="bucket",
    )
    assert binding["schema"] == ROOT_AUDIT_SCHEMA
    assert binding["generation_id"] == manifest["generation_id"]
    assert binding["marker_etag"] == '"verified-root"'
    validate_story_root_audit_binding(binding)
    validate_press_admission(build_press_admission(binding, packet), audit_binding=binding, packet=packet)


def _transport_manifest(generation: str) -> tuple[dict, dict[str, bytes]]:
    body = canonical_json_bytes({"packet": generation})
    digest = sha256_bytes(body)
    object_key = f"objects/{digest}.json"
    manifest = {
        "schema": "earnings.story_packet_catalog/v1",
        "generation_id": generation,
        "parent_generation_id": None,
        "status": "ready",
        "packets": {"earnings:AAPL/2026Q1": {"object": "packet"}},
        "files": {"packet": {"object_key": object_key, "sha256": digest, "bytes": len(body)}},
    }
    anchor = publisher._anchor_receipt(manifest)
    return manifest, {
        f"{publisher.PREFIX}/{object_key}": body,
        publisher._journal_key("anchors", generation): canonical_json_bytes(anchor),
    }


def test_transport_audit_rejects_a_root_race_before_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    first, objects = _transport_manifest("packet_one")
    second, _unused = _transport_manifest("packet_two")
    objects[f"{publisher.PREFIX}/generations/packet_one/manifest.json"] = canonical_json_bytes(first)

    def validate_manifest(value: object) -> None:
        assert isinstance(value, dict)
        assert value["schema"] == "earnings.story_packet_catalog/v1"

    def verify_store(_root: Path, *, manifest: dict) -> dict:
        return {"status": "ready", "packet_count": len(manifest["packets"])}

    monkeypatch.setattr(publisher, "_story_contracts", lambda: (validate_manifest, verify_store))
    monkeypatch.setattr(publisher, "_audit_bound_evidence", lambda *args, **kwargs: None)
    stable = publisher.hydrate_and_verify_current_story_root(
        s3=_RootRaceR2(first, first, objects), bucket="bucket",
    )
    assert stable["schema"] == ROOT_AUDIT_SCHEMA
    assert stable["generation_id"] == "packet_one"
    assert stable["marker_sha256"] == sha256_bytes(canonical_json_bytes(first))
    assert stable["marker_etag"] == '"root"'
    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="root changed during audit"):
        publisher.hydrate_and_verify_current_story_root(
            s3=_RootRaceR2(first, second, objects), bucket="bucket",
        )


def test_transport_audit_rejects_same_body_etag_move_and_missing_etag(monkeypatch: pytest.MonkeyPatch) -> None:
    first, objects = _transport_manifest("packet_one")
    objects[f"{publisher.PREFIX}/generations/packet_one/manifest.json"] = canonical_json_bytes(first)

    def validate_manifest(value: object) -> None:
        assert isinstance(value, dict)
        assert value["schema"] == "earnings.story_packet_catalog/v1"

    def verify_store(_root: Path, *, manifest: dict) -> dict:
        return {"status": "ready", "packet_count": len(manifest["packets"])}

    monkeypatch.setattr(publisher, "_story_contracts", lambda: (validate_manifest, verify_store))
    monkeypatch.setattr(publisher, "_audit_bound_evidence", lambda *args, **kwargs: None)
    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="root changed during audit"):
        publisher.hydrate_and_verify_current_story_root(
            s3=_RootRaceR2(first, first, objects, initial_etag='"v1"', final_etag='"v2"'),
            bucket="bucket",
        )
    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="ETag is absent"):
        publisher.hydrate_and_verify_current_story_root(
            s3=_RootRaceR2(first, first, objects, initial_etag=None), bucket="bucket",
        )
    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="ETag is absent"):
        publisher.hydrate_and_verify_current_story_root(
            s3=_RootRaceR2(first, first, objects, initial_etag='"v1"', final_etag=None),
            bucket="bucket",
        )


def test_root_audit_binding_is_closed(tmp_path: Path) -> None:
    _evidence, _store, _manifest, _packet_value, audit = _current(tmp_path)
    assert audit["schema"] == ROOT_AUDIT_SCHEMA
    forged = deepcopy(audit)
    forged["local_path"] = "/tmp/current-root"
    with pytest.raises(ContractError, match="unsupported"):
        validate_story_root_audit_binding(forged)
