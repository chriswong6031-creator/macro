"""Fail-closed tests for the append-only W1-A1 miner-roster overlay."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import pandas as pd

from engine.stock_identity import pilot
from engine.stock_identity.authority import authority_block
from scripts import stock_identity_build_w1a1 as builder


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_receipt(root: Path, payload: dict) -> None:
    path = root / pilot.RECEIPT_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _closed_fixture(root: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    generated: dict[str, str] = {}
    for relative in pilot.W1A1_GENERATED_OUTPUT_PATHS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"governed:{relative}".encode("utf-8"))
        generated[relative] = _sha256(path)

    original = "# sealed GOLD dossier\n\nstanding authority\n\n## Identity\n"
    before_sha = hashlib.sha256(original.encode("utf-8")).hexdigest()
    monkeypatch.setattr(pilot, "W1A1_GOLD_MD_BEFORE_SHA256", before_sha)
    block = "\n".join(
        (
            pilot.W1A1_GOLD_ANNOTATION_BEGIN,
            "> additive wrong-issuer disclosure",
            pilot.W1A1_GOLD_ANNOTATION_END,
        )
    )
    annotated = original.replace("\n\n## Identity", f"\n\n{block}\n\n## Identity")
    gold = root / pilot.W1A1_GOLD_DISCLOSURE_PATH
    gold.parent.mkdir(parents=True, exist_ok=True)
    gold.write_text(annotated, encoding="utf-8")

    payload = {
        "amendment_id": pilot.AMENDMENT_ID,
        "miner_probe_roster": {
            "sealed_w1": list(pilot.W1_SEALED_MINER_PROBE),
            "effective_w1a1": list(pilot.W1A1_EFFECTIVE_MINER_PROBE),
        },
        "registered_output_paths": list(pilot.W1A1_REGISTERED_OUTPUT_PATHS),
        "generated_output_sha256": generated,
        "disclosure_only": {
            "path": pilot.W1A1_GOLD_DISCLOSURE_PATH,
            "before_sha256": before_sha,
            "after_sha256": _sha256(gold),
            "marker_begin": pilot.W1A1_GOLD_ANNOTATION_BEGIN,
            "marker_end": pilot.W1A1_GOLD_ANNOTATION_END,
            "restores_original_when_removed": True,
            "gold_svg_unchanged": True,
        },
        "measured_rows_mutated": False,
        "authority": authority_block(),
    }
    _write_receipt(root, payload)
    return payload


def test_current_miner_probe_requires_complete_closed_receipt(tmp_path, monkeypatch):
    _closed_fixture(tmp_path, monkeypatch)
    assert pilot.current_miner_probe(tmp_path) == pilot.W1A1_EFFECTIVE_MINER_PROBE


def test_current_miner_probe_rejects_omitted_governed_output(tmp_path, monkeypatch):
    payload = _closed_fixture(tmp_path, monkeypatch)
    payload = copy.deepcopy(payload)
    payload["generated_output_sha256"].pop(pilot.W1A1_GENERATED_OUTPUT_PATHS[-1])
    _write_receipt(tmp_path, payload)
    with pytest.raises(ValueError, match="hash closure is incomplete"):
        pilot.current_miner_probe(tmp_path)


def test_current_miner_probe_rejects_path_traversal_key(tmp_path, monkeypatch):
    payload = _closed_fixture(tmp_path, monkeypatch)
    payload = copy.deepcopy(payload)
    payload["generated_output_sha256"]["../escape"] = "0" * 64
    _write_receipt(tmp_path, payload)
    with pytest.raises(ValueError, match="hash closure is incomplete"):
        pilot.current_miner_probe(tmp_path)


def test_current_miner_probe_rejects_substituted_disclosure_path(tmp_path, monkeypatch):
    payload = _closed_fixture(tmp_path, monkeypatch)
    payload = copy.deepcopy(payload)
    payload["disclosure_only"]["path"] = "research/stock_identity/dossiers/B.md"
    _write_receipt(tmp_path, payload)
    with pytest.raises(ValueError, match="disclosure path drifted"):
        pilot.current_miner_probe(tmp_path)


def test_current_miner_probe_rejects_nonreversible_disclosure(tmp_path, monkeypatch):
    payload = _closed_fixture(tmp_path, monkeypatch)
    payload = copy.deepcopy(payload)
    gold = tmp_path / pilot.W1A1_GOLD_DISCLOSURE_PATH
    gold.write_text("tampered outside marker\n" + gold.read_text(encoding="utf-8"), encoding="utf-8")
    payload["disclosure_only"]["after_sha256"] = _sha256(gold)
    _write_receipt(tmp_path, payload)
    with pytest.raises(ValueError, match="does not restore the sealed dossier"):
        pilot.current_miner_probe(tmp_path)


def test_authority_frame_rejects_nulls_and_integer_zero():
    columns = {
        f"authority_{key}": pd.Series([False], dtype=bool)
        for key in authority_block()
    }
    valid = pd.DataFrame(columns)
    builder._assert_zero_authority_frame(valid, "valid")

    nullish = valid.astype(object)
    nullish.loc[0, "authority_can_rank"] = None
    with pytest.raises(SystemExit, match="non-null boolean"):
        builder._assert_zero_authority_frame(nullish, "nullish")

    integer_zero = valid.copy()
    integer_zero["authority_can_rank"] = 0
    with pytest.raises(SystemExit, match="non-null boolean"):
        builder._assert_zero_authority_frame(integer_zero, "integer")


def test_additive_schema_is_normalized_then_reopened_exactly(tmp_path):
    frozen = pd.DataFrame(
        {
            "when": pd.Series([pd.Timestamp("2020-01-01")], dtype="datetime64[us]"),
            "label": pd.Series(["sealed"], dtype="str"),
            "note": pd.Series([None], dtype=object),
            "authority_can_rank": pd.Series([False], dtype=bool),
        }
    )
    frozen_path = tmp_path / "frozen.parquet"
    frozen.to_parquet(frozen_path, index=False)
    candidate = pd.DataFrame(
        {
            "when": pd.Series([pd.Timestamp("2026-08-13")], dtype="datetime64[ms]"),
            "label": ["B"],
            "note": [None],
            "authority_can_rank": [False],
        }
    )
    normalized = builder._schema_like(candidate, frozen_path, "candidate")
    builder._validate_schema_like(normalized, pd.read_parquet(frozen_path), "candidate")

    written = tmp_path / "candidate.parquet"
    normalized.to_parquet(written, index=False)
    builder._validate_parquet_schema_like(written, frozen_path, "candidate")

    wrong = normalized.copy()
    wrong["authority_can_rank"] = 0
    wrong_path = tmp_path / "wrong.parquet"
    wrong.to_parquet(wrong_path, index=False)
    with pytest.raises(SystemExit, match="serialized logical-type drift"):
        builder._validate_parquet_schema_like(wrong_path, frozen_path, "wrong")


def test_b_only_dossier_overrides_disclose_rank_and_open_gap_semantics():
    generic = "\n".join(
        (
            "# B — Identity Atlas v0 dossier",
            builder._GENERIC_PERCENTILE_PROSE,
            builder._GENERIC_B_GAP_PROSE,
        )
    )
    amended = builder._apply_b_dossier_disclosures(generic)
    assert "W1-A1 addendum" in amended
    assert "only B was ranked and no W1 row was recomputed or rewritten" in amended
    assert "opening print is compared with the previous close" in amended
    assert "close-to-close proxy" not in amended


def test_post_publish_validation_failure_rolls_back_the_whole_amendment(
    tmp_path, monkeypatch
):
    outputs = (
        "data/receipt.json",
        "data/B.parquet",
        "research/B.md",
    )
    disclosure = "research/GOLD.md"
    stage = tmp_path / "stage"
    repo = tmp_path / "repo"
    for relative in outputs:
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"staged:{relative}", encoding="utf-8")
    staged_gold = stage / "GOLD.annotated.md"
    staged_gold.write_text("annotated", encoding="utf-8")
    original_gold = repo / disclosure
    original_gold.parent.mkdir(parents=True, exist_ok=True)
    original_gold.write_text("sealed", encoding="utf-8")

    monkeypatch.setattr(builder, "REPO_ROOT", repo)
    monkeypatch.setattr(builder, "OUTPUT_PATHS", outputs)
    monkeypatch.setattr(builder, "RECEIPT_RELATIVE_PATH", outputs[0])
    monkeypatch.setattr(builder, "DISCLOSURE_ONLY_PATH", disclosure)
    monkeypatch.setattr(builder, "_validate_outputs_absent", lambda: None)
    monkeypatch.setattr(builder, "_validate_frozen_hashes", lambda **kwargs: None)

    def fail_closure(_receipt):
        raise SystemExit("forced post-publish closure failure")

    monkeypatch.setattr(builder, "_validate_published", fail_closure)
    with pytest.raises(SystemExit, match="forced post-publish"):
        builder._publish(stage, staged_gold, {"test": True})

    assert original_gold.read_text(encoding="utf-8") == "sealed"
    assert all(not (repo / relative).exists() for relative in outputs)
