from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from engine.earnings_narrative.contracts import canonical_json_bytes
from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.generation import EvidencePair, write_generation
from engine.earnings_narrative.story_store import write_story_packet_generation
from engine.earnings_transcript_intake import canonical_body_sha256
from scripts import publish_earnings_story_packets_r2 as publisher
from scripts import stage_earnings_story_press as ingress


ROOT = Path(__file__).resolve().parents[1]


def _body(*, sparse: bool = False) -> dict[str, Any]:
    segments = [
        {
            "speaker": "Chief Executive Officer",
            "role": "executive",
            "text": "Revenue grew 12% to 120 million, while gross margin reached 45%.",
        },
        {
            "speaker": "Chief Financial Officer",
            "role": "executive",
            "text": "For the full year, we expect revenue of 500 million and an operating margin of 20%.",
        },
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


def _write_evidence(root: Path, body: dict[str, Any]) -> dict[str, Any]:
    body_sha = canonical_body_sha256(body)
    generated_at = "2026-02-01T00:00:00Z"
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


def _current(tmp_path: Path, *, sparse: bool = False) -> tuple[Path, Path, dict, dict]:
    evidence = tmp_path / "evidence"
    store = tmp_path / "story"
    _write_evidence(evidence, _body(sparse=sparse))
    _generation, manifest = write_story_packet_generation(store, evidence)
    index = manifest["packets"]["AAPL/2026Q1"]
    packet = json.loads((store / index["object_key"]).read_text(encoding="utf-8"))
    return evidence, store, manifest, packet


def _r2_objects(evidence: Path, store: Path, manifest: dict) -> dict[str, bytes]:
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
    return objects


class _R2:
    def __init__(self, objects: dict[str, bytes], *, root_etags: list[str] | None = None) -> None:
        self.objects = dict(objects)
        self.root_etags = list(root_etags or ['"stable-root"'])
        self.root_reads = 0

    def get_object(self, *, Bucket: str, Key: str):  # noqa: N803
        body = self.objects.get(Key)
        if body is None:
            raise RuntimeError("missing")
        result = {"Body": io.BytesIO(body)}
        if Key == f"{publisher.PREFIX}/manifest.json":
            offset = min(self.root_reads, len(self.root_etags) - 1)
            result["ETag"] = self.root_etags[offset]
            self.root_reads += 1
        return result

    def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str | None = None):  # noqa: N803
        assert ContinuationToken is None
        return {
            "IsTruncated": False,
            "Contents": [{"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)],
        }


def _ids(manifest: dict, packet: dict) -> dict[str, str]:
    return {
        "generation_id": manifest["generation_id"],
        "packet_id": packet["packet_id"],
        "story_revision_id": packet["story"]["story_revision_id"],
    }


def _stub_stage(monkeypatch: pytest.MonkeyPatch, calls: list[dict]) -> None:
    def stage(root, cfg, *, slot, admission_receipt, staging_dir):
        destination = Path(staging_dir)
        destination.mkdir(parents=True)
        calls.append({"root": root, "slot": slot, "admission": admission_receipt})
        item = {
            "id": slot["id"],
            "status": "passed",
            "slot": slot,
            "provenance": {"admission_receipt": admission_receipt},
        }
        summary = {
            "planned": 1,
            "passed": 1,
            "quarantined": 0,
            "items": [{"id": slot["id"], "status": "passed"}],
            "writer_state": {"calls": 1, "token_budget": 12_000},
        }
        (destination / f"{slot['id']}.json").write_text(
            json.dumps(item) + "\n", encoding="utf-8",
        )
        (destination / "_run_summary.json").write_text(
            json.dumps(summary) + "\n", encoding="utf-8",
        )
        return summary

    monkeypatch.setattr(ingress, "run_admitted_earnings_staging", stage)


def test_exact_current_packet_is_full_audited_derived_and_staged_once(tmp_path, monkeypatch) -> None:
    evidence, store, manifest, packet = _current(tmp_path)
    calls: list[dict] = []
    _stub_stage(monkeypatch, calls)
    destination = tmp_path / "isolated-stage"

    result = ingress.stage_exact_current_story(
        **_ids(manifest, packet),
        staging_dir=destination,
        root=ROOT,
        s3=_R2(_r2_objects(evidence, store, manifest)),
        bucket="bucket",
    )

    assert len(calls) == 1
    assert calls[0]["slot"] == packet["press_slot"]
    assert calls[0]["admission"]["limits"] == {
        "max_candidates": 1,
        "max_model_calls": 1,
        "max_tokens": 12_000,
    }
    assert result["operation"] == "stage_only" and result["allow_emit"] is False
    assert result["staging"]["story_root_current_after_stage"] is True
    staged = json.loads(next(path for path in destination.glob("*.json") if not path.name.startswith("_")).read_text())
    assert staged["story_root_current_after_stage"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("generation_id", "0" * 32),
        ("packet_id", "storypacket_" + "0" * 32),
        ("story_revision_id", "storyrev_" + "0" * 32),
    ],
)
def test_stale_or_mismatched_immutable_id_makes_zero_stage_calls(tmp_path, monkeypatch, field, value) -> None:
    evidence, store, manifest, packet = _current(tmp_path)
    calls: list[dict] = []
    _stub_stage(monkeypatch, calls)
    requested = _ids(manifest, packet)
    requested[field] = value

    with pytest.raises(publisher.ImmutableAddressIntegrityError):
        ingress.stage_exact_current_story(
            **requested,
            staging_dir=tmp_path / "isolated-stage",
            root=ROOT,
            s3=_R2(_r2_objects(evidence, store, manifest)),
            bucket="bucket",
        )
    assert calls == []


def test_historical_root_rollback_makes_zero_stage_calls(tmp_path, monkeypatch) -> None:
    evidence, store, first_manifest, first_packet = _current(tmp_path)
    first_objects = _r2_objects(evidence, store, first_manifest)

    corrected_body = _body()
    corrected_body["segments"][1]["text"] = (
        "For the full year, we expect revenue of 510 million and an operating margin of 21%."
    )
    _write_evidence(evidence, corrected_body)
    _generation, current_manifest = write_story_packet_generation(store, evidence)
    current_objects = _r2_objects(evidence, store, current_manifest)
    del current_objects[publisher._journal_key("anchors", current_manifest["generation_id"])]
    transition = publisher._transition_receipt(current_manifest)
    commit = publisher._commit_receipt(transition)
    current_objects[
        publisher._journal_key("transitions", first_manifest["generation_id"])
    ] = canonical_json_bytes(transition)
    current_objects[
        publisher._journal_key("commits", current_manifest["generation_id"])
    ] = canonical_json_bytes(commit)
    objects = {**first_objects, **current_objects}
    # Preserve every immutable generation, but expose the byte-valid old root.
    objects[f"{publisher.PREFIX}/manifest.json"] = canonical_json_bytes(first_manifest)

    calls: list[dict] = []
    _stub_stage(monkeypatch, calls)
    with pytest.raises(
        publisher.ImmutableAddressIntegrityError,
        match="behind or outside|not the finalized publication journal tip",
    ):
        ingress.stage_exact_current_story(
            **_ids(first_manifest, first_packet),
            staging_dir=tmp_path / "rolled-back-stage",
            root=ROOT,
            s3=_R2(objects),
            bucket="bucket",
        )
    assert calls == []


def test_malformed_id_is_rejected_before_any_r2_read_or_stage(tmp_path, monkeypatch) -> None:
    calls: list[dict] = []
    _stub_stage(monkeypatch, calls)

    class _NeverR2:
        def get_object(self, **_kwargs):
            raise AssertionError("malformed identifiers must fail before R2")

    with pytest.raises(ingress.EarningsStoryIngressError, match="generation_id"):
        ingress.stage_exact_current_story(
            generation_id="../current",
            packet_id="storypacket_" + "0" * 32,
            story_revision_id="storyrev_" + "0" * 32,
            staging_dir=tmp_path / "isolated-stage",
            root=ROOT,
            s3=_NeverR2(),
            bucket="bucket",
        )
    assert calls == []


def test_tampered_packet_object_and_tier_c_make_zero_stage_calls(tmp_path, monkeypatch) -> None:
    calls: list[dict] = []
    _stub_stage(monkeypatch, calls)

    evidence, store, manifest, packet = _current(tmp_path)
    objects = _r2_objects(evidence, store, manifest)
    packet_key = f"{publisher.PREFIX}/{manifest['packets']['AAPL/2026Q1']['object_key']}"
    objects[packet_key] = canonical_json_bytes({"tampered": True})
    with pytest.raises(publisher.ImmutableAddressIntegrityError):
        ingress.stage_exact_current_story(
            **_ids(manifest, packet),
            staging_dir=tmp_path / "tampered-stage",
            root=ROOT,
            s3=_R2(objects),
            bucket="bucket",
        )

    sparse_evidence, sparse_store, sparse_manifest, sparse_packet = _current(tmp_path / "sparse", sparse=True)
    assert sparse_packet["promotion"]["tier"] == "C"
    with pytest.raises(Exception, match="Tier B"):
        ingress.stage_exact_current_story(
            **_ids(sparse_manifest, sparse_packet),
            staging_dir=tmp_path / "tier-c-stage",
            root=ROOT,
            s3=_R2(_r2_objects(sparse_evidence, sparse_store, sparse_manifest)),
            bucket="bucket",
        )
    assert calls == []


def test_root_etag_race_immediately_before_writer_makes_zero_stage_calls(tmp_path, monkeypatch) -> None:
    evidence, store, manifest, packet = _current(tmp_path)
    calls: list[dict] = []
    _stub_stage(monkeypatch, calls)
    # Hydration and each currentness proof bracket the journal listing with
    # root reads.  The sixth read is the pre-writer proof.
    r2 = _R2(
        _r2_objects(evidence, store, manifest),
        root_etags=['"stable"'] * 5 + ['"moved"'],
    )
    with pytest.raises(publisher.ImmutableAddressIntegrityError, match="no longer matches"):
        ingress.stage_exact_current_story(
            **_ids(manifest, packet),
            staging_dir=tmp_path / "race-stage",
            root=ROOT,
            s3=r2,
            bucket="bucket",
        )
    assert calls == []


def test_post_call_root_race_quarantines_artifact_and_fails(tmp_path, monkeypatch) -> None:
    evidence, store, manifest, packet = _current(tmp_path)
    calls: list[dict] = []
    _stub_stage(monkeypatch, calls)
    destination = tmp_path / "post-call-race"
    # The eighth root read begins the proof after the single bounded stage call.
    r2 = _R2(
        _r2_objects(evidence, store, manifest),
        root_etags=['"stable"'] * 7 + ['"moved"'],
    )
    with pytest.raises(ingress.EarningsStoryIngressError, match="moved during"):
        ingress.stage_exact_current_story(
            **_ids(manifest, packet),
            staging_dir=destination,
            root=ROOT,
            s3=r2,
            bucket="bucket",
        )
    assert len(calls) == 1
    staged = json.loads(next(path for path in destination.glob("*.json") if not path.name.startswith("_")).read_text())
    summary = json.loads((destination / "_run_summary.json").read_text())
    assert staged["status"] == "quarantined"
    assert staged["story_root_current_after_stage"] is False
    assert summary["passed"] == 0 and summary["quarantined"] == 1
    assert summary["story_root_current_after_stage"] is False


def test_cli_failure_writes_a_safe_machine_readable_artifact(tmp_path, monkeypatch, capsys) -> None:
    destination = tmp_path / "runner" / "earnings-story-press-stage"
    monkeypatch.setattr(ingress, "_runner_destination", lambda: destination)
    monkeypatch.setattr(
        ingress,
        "stage_exact_current_story",
        lambda **_kwargs: (_ for _ in ()).throw(ingress.EarningsStoryIngressError("stale root")),
    )
    ids = {
        "generation_id": "a" * 32,
        "packet_id": "storypacket_" + "b" * 32,
        "story_revision_id": "storyrev_" + "c" * 32,
    }
    rc = ingress.main([
        "--generation-id", ids["generation_id"],
        "--packet-id", ids["packet_id"],
        "--story-revision-id", ids["story_revision_id"],
    ])
    assert rc == 1
    failure = json.loads((destination / "_ingress_failure.json").read_text())
    assert failure["schema"] == "earnings.press_stage_failure/v1"
    assert failure["operation"] == "stage_only" and failure["allow_emit"] is False
    assert {key: failure[key] for key in ids} == ids
    assert failure["error_type"] == "EarningsStoryIngressError"
    assert "stale root" in failure["error"]
    assert "::error title=earnings_story_press_stage::" in capsys.readouterr().out
