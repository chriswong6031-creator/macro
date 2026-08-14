"""Fail-closed tests for the append-only W1-A1 miner-roster overlay."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile

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

    sealed: dict[str, str] = {}
    for relative in pilot.W1A1_SEALED_W1_SHA256:
        if relative == pilot.W1A1_GOLD_DISCLOSURE_PATH:
            continue
        frozen = root / relative
        frozen.parent.mkdir(parents=True, exist_ok=True)
        frozen.write_bytes(f"sealed:{relative}".encode("utf-8"))
        sealed[relative] = _sha256(frozen)

    original = "# sealed GOLD dossier\n\nstanding authority\n\n## Identity\n"
    before_sha = hashlib.sha256(original.encode("utf-8")).hexdigest()
    monkeypatch.setattr(pilot, "W1A1_GOLD_MD_BEFORE_SHA256", before_sha)
    sealed[pilot.W1A1_GOLD_DISCLOSURE_PATH] = before_sha
    monkeypatch.setattr(pilot, "W1A1_SEALED_W1_SHA256", sealed)
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
        "schema": pilot.W1A1_RECEIPT_SCHEMA,
        "amendment_id": pilot.AMENDMENT_ID,
        "asof": pilot.W1A1_ASOF,
        "pull_request": 9999,
        "registration_commit": "3" * 40,
        "prerequisite_merges": {"pr_5613": "1" * 40, "pr_5632": "2" * 40},
        "identity_receipt": copy.deepcopy(pilot.W1A1_IDENTITY_RECEIPT),
        "miner_probe_roster": {
            "sealed_w1": list(pilot.W1_SEALED_MINER_PROBE),
            "effective_w1a1": list(pilot.W1A1_EFFECTIVE_MINER_PROBE),
        },
        "partition_treatment": copy.deepcopy(pilot.W1A1_PARTITION_TREATMENT),
        "procedural_deviation": {
            "status": "DISCLOSED_PRE_REGISTRATION_IMPLEMENTATION_EXPOSURE",
            "write_scope": "no repository artifacts written",
            "observed_scope": "implementation outputs printed before registration",
            "consequence": "B is permanently design-touched and nonconfirmatory",
        },
        "rank_context": {
            "method": "B-only hypothetical insertion",
            "frozen_reference_rows": 2780,
            "hypothetical_joint_rows": 2781,
            "only_B_persisted": True,
            "w1_percentiles_rewritten": False,
            "univ_ew_recomputed": False,
            "dealer_context_disclosure": "frozen ranks retain GOLD dealer context",
            "reference_sha256": copy.deepcopy(pilot.W1A1_REFERENCE_SHA256),
        },
        "price_input": {
            "path": "data/baskets/ohlcv/B.parquet",
            "price_plane_id": "baskets_ohlcv_v1",
            "prefix_asof": pilot.W1A1_ASOF,
            "prefix_sha256": "6d8988fc8ec3990d3a5c2a6d5f4bb31d94b3ab46ac49978d21fb3770482ae8db",
            "seed_container_sha256": "dc126c36c6fa07b37ca212051d2a194758725330bfed9c5b6112701b12be6b5f",
            "file_sha256_at_run": "4" * 64,
            "file_rows_at_run": 3172,
            "file_last_date_at_run": pilot.W1A1_ASOF,
            "rows_used": 3172,
            "first_date": "2014-01-02",
            "last_date_used": pilot.W1A1_ASOF,
        },
        "sealed_w1_sha256": copy.deepcopy(sealed),
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
        "trial_budget": "one deterministic descriptive configuration, no sweep",
        "authority": authority_block(),
    }
    _write_receipt(root, payload)
    return payload


def test_current_miner_probe_requires_complete_closed_receipt(tmp_path, monkeypatch):
    _closed_fixture(tmp_path, monkeypatch)
    assert pilot.current_miner_probe(tmp_path) == pilot.W1A1_EFFECTIVE_MINER_PROBE


@pytest.mark.parametrize(
    "keys,value,match",
    (
        (("schema",), "wrong", "receipt schema"),
        (("identity_receipt", "B", "edgar_cik"), "1591588", "identity receipt"),
        (("partition_treatment", "B_design_touched"), False, "partition quarantine"),
        (("prerequisite_merges", "pr_5632"), "not-a-sha", "prerequisite merge"),
        (("rank_context", "w1_percentiles_rewritten"), True, "rank context"),
        (("price_input", "prefix_sha256"), "0" * 64, "price-input"),
        (("sealed_w1_sha256", "data/stock_identity/constants/si_constants_v1.json"),
         "0" * 64, "sealed W1 hash receipt"),
    ),
)
def test_current_miner_probe_rejects_governance_tampering(
    tmp_path, monkeypatch, keys, value, match
):
    payload = copy.deepcopy(_closed_fixture(tmp_path, monkeypatch))
    target = payload
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    _write_receipt(tmp_path, payload)
    with pytest.raises(ValueError, match=match):
        pilot.current_miner_probe(tmp_path)


def test_current_miner_probe_rejects_actual_sealed_artifact_drift(tmp_path, monkeypatch):
    _closed_fixture(tmp_path, monkeypatch)
    frozen = tmp_path / "data/stock_identity/constants/si_constants_v1.json"
    frozen.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="sealed W1 artifact drifted"):
        pilot.current_miner_probe(tmp_path)


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


def test_b_compute_hygiene_fails_before_history_is_consumed(monkeypatch):
    monkeypatch.setattr(builder.hyg_mod, "COMPUTE_BLOCKLIST", {"B": "verified block"})
    monkeypatch.setattr(
        builder.hyg_mod,
        "check_symbol",
        lambda *args, **kwargs: {
            "flags": ["compute_blocklisted"],
            "notes": {"compute_blocklisted": "verified block"},
            "compute_eligible": False,
        },
    )
    with pytest.raises(SystemExit, match="pre-read compute hygiene gate"):
        builder._validate_compute_hygiene("B", pd.Timestamp("2014-01-02"))


def test_b_logical_prefix_digest_ignores_later_appends_but_detects_revisions():
    columns = ["open", "high", "low", "close", "volume"]
    prefix = pd.DataFrame(
        [[1.0, 2.0, 0.5, 1.5, 100.0], [1.5, 2.5, 1.0, 2.0, 120.0]],
        index=pd.DatetimeIndex(["2026-08-12", "2026-08-13"], name="Date"),
        columns=columns,
    )
    appended = pd.concat(
        [
            prefix,
            pd.DataFrame(
                [[2.0, 3.0, 1.5, 2.5, 140.0]],
                index=pd.DatetimeIndex(["2026-08-14"], name="Date"),
                columns=columns,
            ),
        ]
    )
    assert builder._ohlcv_prefix_sha256(appended.loc[:"2026-08-13"]) == (
        builder._ohlcv_prefix_sha256(prefix)
    )
    revised = prefix.copy()
    revised.loc[pd.Timestamp("2026-08-12"), "close"] = 1.5000001
    assert builder._ohlcv_prefix_sha256(revised) != builder._ohlcv_prefix_sha256(prefix)


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
    # Reproduce the sealed episode artifact's accidental physical RangeIndex. The
    # consumer-visible pandas schema excludes it, and an additive index=False file is
    # still logically schema-compatible.
    frozen.to_parquet(frozen_path, index=True)
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

    import pyarrow.parquet as pq

    assert "__index_level_0__" in pq.read_schema(frozen_path).names
    assert "__index_level_0__" not in pq.read_schema(written).names

    wrong = normalized.copy()
    wrong["authority_can_rank"] = 0
    wrong_path = tmp_path / "wrong.parquet"
    wrong.to_parquet(wrong_path, index=False)
    with pytest.raises(SystemExit, match="logical-type drift"):
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
    lock_key = hashlib.sha256(str(repo.resolve()).encode("utf-8")).hexdigest()[:16]
    assert (Path(tempfile.gettempdir()) / f"stock-identity-w1a1-{lock_key}.lock").exists()
