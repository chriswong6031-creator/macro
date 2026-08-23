from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

import scripts.research.dislocation_p0_s1f_shadow_triage as shadow


BASE = Path("research/dislocation_intelligence/p0_s1f")


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "manifest_path": BASE / "S1F_CANONICAL_SOURCE_PACKET_MANIFEST.json",
        "selection_path": BASE / "S1F_EXACT70_SOURCE_MANIFEST.json",
        "receipt_path": BASE / "S1F_EXACT70_SELECTION_RECEIPT.json",
        "batch_path": BASE / "S1F_EXACT70_AUDIT_BATCH_PLAN.json",
        "replay_path": BASE / "S1F_CANONICAL_OWNER_REPLAY_PROOF.json",
        "ruleset_path": BASE / "S1F_TRIAGE_RULESET.json",
        "source_root": BASE / "work/source_owner_attempt2/source_packets",
        "output_dir": tmp_path / "out",
    }


def _source_root_with_index(tmp_path: Path, mutate) -> Path:
    original = BASE / "work/source_owner_attempt2/source_packets"
    result = tmp_path / "source_packets"
    result.mkdir()
    (result / "packets").symlink_to(original / "packets")
    (result / "primary").symlink_to(original / "primary")
    index = json.loads((original / "packet_index.json").read_text(encoding="utf-8"))
    mutate(index)
    (result / "packet_index.json").write_text(json.dumps(index), encoding="utf-8")
    return result


def _frozen_values() -> tuple[dict, dict, dict]:
    return tuple(
        json.loads((BASE / name).read_text(encoding="utf-8"))
        for name in (
            "S1F_CANONICAL_SOURCE_PACKET_MANIFEST.json",
            "S1F_EXACT70_SOURCE_MANIFEST.json",
            "S1F_EXACT70_AUDIT_BATCH_PLAN.json",
        )
    )


def test_frozen_shadow_triage_replays_all70_and_reruns_byte_identically(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    first = shadow.run(**paths)
    first_bytes = {name: path.read_bytes() for name, path in (("triage", first["triage_path"]), ("bundle", first["bundle_path"]))}
    second = shadow.run(**paths)
    assert {name: path.read_bytes() for name, path in (("triage", second["triage_path"]), ("bundle", second["bundle_path"]))} == first_bytes
    triage = first["triage"]
    assert triage["packet_count"] == len(triage["triage"]) == 70
    assert triage["exact_fts_matched_document_count"] == 129
    assert triage["additive_primary_context_count"] == 70
    assert triage["primary_document_substitution"] is False
    assert [row["packet_id"] for row in triage["triage"]] == [row["packet_id"] for row in first["bundle"]["packets"]]
    assert first["bundle"]["shadow_triage_included"] is False
    assert not shadow._contains_forbidden(triage)
    assert not shadow._contains_forbidden(first["bundle"])


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda index: index["packets"][0]["documents"][0].__setitem__("source_path", "packets/not-present.source"), "S1F_SHADOW_PACKET_SOURCE_PATH_MISSING"),
        (lambda index: index["packets"][0]["documents"][0].__setitem__("document_sha256", "0" * 64), "S1F_SHADOW_PACKET_INDEX_DOCUMENT_BINDING_MISMATCH"),
        (lambda index: index["packets"].__setitem__(slice(0, 2), list(reversed(index["packets"][:2]))), "S1F_SHADOW_PACKET_ORDER_MISMATCH"),
        (lambda index: index["packets"][0].__setitem__("primary_document_substitution", True), "S1F_SHADOW_PRIMARY_SUBSTITUTION"),
        (lambda index: index.__setitem__("packets", index["packets"][:-1]), "S1F_SHADOW_PACKET_INDEX_CARDINALITY_MISMATCH"),
    ],
)
def test_shadow_triage_fails_closed_for_source_path_hash_order_substitution_and_all70_coverage(tmp_path: Path, mutate, code: str) -> None:
    paths = _paths(tmp_path)
    paths["source_root"] = _source_root_with_index(tmp_path, mutate)
    with pytest.raises(shadow.ShadowTriageBlocked, match=code):
        shadow.run(**paths)


def test_shadow_triage_fails_closed_for_manifest_and_ruleset_hash_drift(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    mutated_manifest = tmp_path / "manifest.json"
    mutated_manifest.write_bytes(paths["manifest_path"].read_bytes() + b" ")
    paths["manifest_path"] = mutated_manifest
    with pytest.raises(shadow.ShadowTriageBlocked, match="S1F_SHADOW_MANIFEST_FILE_HASH_MISMATCH"):
        shadow.run(**paths)

    paths = _paths(tmp_path)
    mutated_ruleset = tmp_path / "ruleset.json"
    ruleset = json.loads(paths["ruleset_path"].read_text(encoding="utf-8"))
    ruleset["default"]["category"] = "MUTATED"
    mutated_ruleset.write_text(json.dumps(ruleset), encoding="utf-8")
    paths["ruleset_path"] = mutated_ruleset
    with pytest.raises(shadow.ShadowTriageBlocked, match="S1F_SHADOW_RULESET_FILE_HASH_MISMATCH"):
        shadow.run(**paths)


def test_shadow_triage_rejects_frozen_batch_identity_mutation_even_when_rehashed() -> None:
    _manifest, selection, batch = _frozen_values()
    altered = deepcopy(batch)
    altered["batches"][0]["packets"][0]["accession"] = "0000000000-99-999999"
    altered.pop("batch_plan_sha256")
    altered["batch_plan_sha256"] = shadow._digest(altered)
    expected = [(row["cik"], row["accession"]) for row in selection["candidates"]]
    with pytest.raises(shadow.ShadowTriageBlocked, match="S1F_SHADOW_BATCH_EXACT70_IDENTITY_MISMATCH"):
        shadow._validate_batch_identities(altered, expected)


def test_shadow_triage_rejects_forbidden_output_from_frozen_triage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    actual = shadow.triage_packet

    def contaminated(packet):
        value = actual(packet)
        value["price"] = "forbidden"
        return value

    monkeypatch.setattr(shadow, "triage_packet", contaminated)
    with pytest.raises(shadow.ShadowTriageBlocked, match="S1F_SHADOW_TRIAGE_OUTPUT_FORBIDDEN_OR_UNBOUND"):
        shadow.run(**_paths(tmp_path))


def test_shadow_triage_rejects_forbidden_source_mount(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    source_root = _source_root_with_index(tmp_path, lambda index: None)
    (source_root / "price").mkdir()
    paths["source_root"] = source_root
    with pytest.raises(shadow.ShadowTriageBlocked, match="S1F_SHADOW_SOURCE_FIREWALL_FORBIDDEN_MOUNT"):
        shadow.run(**paths)
