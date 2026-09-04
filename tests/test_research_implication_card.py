"""Contract tests for deterministic, non-authoritative research implication cards."""

from __future__ import annotations

from copy import deepcopy
import json
import re
import shutil
from pathlib import Path

import pytest

from engine import research_implication_card as ric
from engine.research_implication_card import (
    AUTHORITY_KEYS,
    CARD_SCHEMA,
    CardContractError,
    adapt_hincl2_event_study,
    adapt_synthetic_control,
    compute_card_id,
    sha256_file,
    validate_card,
)

ROOT = Path(__file__).resolve().parents[1]


def _coded(items: list[dict], code: str) -> dict:
    """Return one exact coded contract entry."""
    matches = [item for item in items if item["code"] == code]
    assert len(matches) == 1, f"expected one {code!r} entry, got {len(matches)}"
    return matches[0]


def _assert_closed_false_authority(card: dict) -> None:
    assert set(card["authority"]) == set(AUTHORITY_KEYS)
    assert all(value is False for value in card["authority"].values())


def _copy_inputs(root: Path, destination: Path, paths: tuple[str, ...]) -> None:
    for relative in paths:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)


SC_INPUTS = (
    "data/experiments/synthetic_control_phase0_results.json",
    "scripts/synthetic_control_phase0.py",
    "engine/synthetic_control.py",
    "research/SYNTHETIC_CONTROL_PHASE0.md",
)


def test_real_synthetic_control_card_preserves_failed_diagnostic_truth() -> None:
    card = adapt_synthetic_control(ROOT)

    assert card["schema"] == CARD_SCHEMA
    assert re.fullmatch(r"ric_[0-9a-f]{64}", card["card_id"])
    assert card["method_family"] == "synthetic_control"
    assert card["study_run_id"] == "synthetic_control_phase0@2026-08-06"
    assert card["selected_result_id"] == "sp_pure_adds/sc_nnls/0_5"
    assert card["cutoff"] == "2026-07-02"
    assert card["sample_n"] == 303
    assert card["effective_n"] is None
    assert _coded(card["null_reasons"], "effective_n")["reason"] == "NOT_REPORTED"

    assert _coded(card["outputs"], "cumulative_abnormal_return")[
        "value"
    ] == pytest.approx(0.030151770605652363)
    assert _coded(card["outputs"], "monthly_newey_west_t")["value"] == 8.291
    assert _coded(card["outputs"], "monthly_observation_count")["value"] == 52
    assert _coded(card["placebos_or_counterexamples"], "placebo_mean")[
        "value"
    ] == pytest.approx(0.0019683084431491495)
    assert _coded(card["placebos_or_counterexamples"], "placebo_standard_deviation")[
        "value"
    ] == pytest.approx(0.006137674112846566)
    assert _coded(card["placebos_or_counterexamples"], "placebo_empirical_p")[
        "value"
    ] == pytest.approx(0.009950248756218905)

    assert card["quality"] == "DIAGNOSTIC_FAILED"
    assert card["evidence_tier"] == "DIAGNOSTIC"
    assert (
        _coded(card["diagnostics"], "PC1_positive_control_survives")["passed"] is True
    )
    assert _coded(card["diagnostics"], "PC2_estimators_unbiased")["passed"] is False
    assert _coded(card["diagnostics"], "PC3_sc_not_noisier")["passed"] is True
    assert _coded(card["diagnostics"], "F1_falsifier_holds")["passed"] is True
    assert card["ordered_effect_path"] is None

    result_receipt = next(
        artifact
        for artifact in card["source_artifacts"]
        if artifact["role"] == "result"
    )
    assert result_receipt == {
        "role": "result",
        "path": "data/experiments/synthetic_control_phase0_results.json",
        "sha256": "f759bdd72de5370e597459dc0630bb1f880e8a38be9b8882a1c75f54872af1e2",
        "as_of": "2026-07-02",
        "as_of_reason": None,
        "rights": "REPOSITORY_INTERNAL",
    }
    _assert_closed_false_authority(card)


def test_real_event_study_card_preserves_episode_n_and_typed_incompleteness() -> None:
    card = adapt_hincl2_event_study(ROOT)

    assert card["schema"] == CARD_SCHEMA
    assert re.fullmatch(r"ric_[0-9a-f]{64}", card["card_id"])
    assert card["method_family"] == "event_study"
    assert card["study_run_id"] == "hincl2_event_study@2026-07-03"
    assert card["selected_result_id"] == "announce/h20"
    assert card["cutoff"] == "2026-07-03"
    assert card["sample_n"] == 282
    assert card["effective_n"] == 74

    assert (
        _coded(card["outputs"], "mean_cumulative_abnormal_return")["value"] == -0.08812
    )
    assert _coded(card["uncertainty"], "hac_mean")["value"] == -0.08812
    assert _coded(card["uncertainty"], "hac_standard_error")["value"] == 0.05317
    assert _coded(card["uncertainty"], "hac_t_statistic")["value"] == -1.657
    assert _coded(card["uncertainty"], "hac_p_value")["value"] == 0.0975
    assert _coded(card["uncertainty"], "mean_ci90")["value"] == [
        -0.18053,
        -0.08441,
        -0.01389,
    ]
    assert _coded(card["diagnostics"], "deflated_sharpe_ratio")["value"] == 0.0
    assert _coded(card["diagnostics"], "bh_fdr_announce_reject")["value"] is False
    assert _coded(card["diagnostics"], "bh_fdr_announce_q")["value"] == 0.962
    assert _coded(card["diagnostics"], "panel_coverage_fraction")["value"] == 0.6194

    path = card["ordered_effect_path"]
    assert path["evidence_status"] == "EXPLORATORY_NON_GATED"
    assert path["selected_horizon"] == 20
    assert path["sample_basis"]["en"].startswith("Equal-weighted across events")
    assert "episode" in path["comparison_note"]["en"].lower()
    assert path["accessible_name"]["zh"]
    selected_point = next(
        point
        for point in path["points"]
        if point["horizon"] == path["selected_horizon"]
    )
    assert selected_point == {"horizon": 20, "value": -0.02168, "n": 276}

    assert card["quality"] == "ARTIFACT_INCOMPLETE"
    assert card["evidence_tier"] == "DIAGNOSTIC"
    missing = {item["code"]: item for item in card["missingness"]}
    assert missing["hk_stocks_ext_digest"]["reason"] == "INPUT_DIGEST_MISSING"
    assert missing["hk_stocks_ext_rights"]["reason"] == "RIGHTS_RECEIPT_MISSING"
    assert all(
        "causal treatment" not in text.lower() for text in card["question"].values()
    )
    assert all(
        "causal treatment" not in text.lower() for text in card["estimand"].values()
    )

    effect_path = card["ordered_effect_path"]
    assert effect_path["owner_supplied"] is True
    assert effect_path["x_unit"] == "trading_day_relative_to_announcement"
    assert effect_path["y_unit"] == "cumulative_abnormal_return"
    assert effect_path["points"][0] == {"horizon": -10, "value": -0.02479, "n": 275}
    assert effect_path["points"][-1] == {"horizon": 60, "value": -0.08366, "n": 276}
    assert [point["horizon"] for point in effect_path["points"]] == sorted(
        point["horizon"] for point in effect_path["points"]
    )

    result_receipt = next(
        artifact
        for artifact in card["source_artifacts"]
        if artifact["role"] == "result"
    )
    assert result_receipt["sha256"] == (
        "f415b2c4cf9b12fbc8e4dd9e3a30a51c736c93f4ffbc3f818392b4796ea81139"
    )
    roster_receipt = next(
        artifact
        for artifact in card["source_artifacts"]
        if artifact["role"] == "event_roster"
    )
    assert roster_receipt["path"] == "data/hk_connect_roster/roster.parquet"
    assert roster_receipt["sha256"] == (
        "b0816afacd9537fac58c193f511ec919bccda4fc58a5921bd1096221fa35b148"
    )
    benchmark_receipt = next(
        artifact
        for artifact in card["source_artifacts"]
        if artifact["role"] == "benchmark"
    )
    assert benchmark_receipt["path"] == "data/hk/_HSI.parquet"
    assert benchmark_receipt["sha256"] == (
        "184cbdcf2437c9d8de172535cd87515b020708c9c441406391faa4aa895a1e45"
    )
    _assert_closed_false_authority(card)


def test_real_card_localized_contract_text_has_actual_chinese_copy() -> None:
    localized_values: list[dict[str, str]] = []
    for card in (adapt_synthetic_control(ROOT), adapt_hincl2_event_study(ROOT)):
        localized_values.extend(
            [card["question"], card["estimand"], *card["limitations"]]
        )
        for collection in (
            "outputs",
            "uncertainty",
            "diagnostics",
            "placebos_or_counterexamples",
        ):
            for item in card[collection]:
                localized_values.append(item["label"])
                if "detail" in item:
                    localized_values.append(item["detail"])
        for collection in ("exclusions", "missingness", "null_reasons"):
            localized_values.extend(item["detail"] for item in card[collection])

    assert localized_values
    for value in localized_values:
        assert value["en"].strip()
        assert re.search(r"[\u4e00-\u9fff]", value["zh"]), value


def test_replay_is_deterministic_and_byte_equivalent() -> None:
    first = [adapt_synthetic_control(ROOT), adapt_hincl2_event_study(ROOT)]
    second = [adapt_synthetic_control(ROOT), adapt_hincl2_event_study(ROOT)]

    first_bytes = json.dumps(
        first, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    second_bytes = json.dumps(
        second, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert first_bytes == second_bytes


def test_result_digest_participates_in_card_identity() -> None:
    card = adapt_synthetic_control(ROOT)
    result = next(item for item in card["source_artifacts"] if item["role"] == "result")

    mutated_id = compute_card_id(
        adapter_version=card["adapter_version"],
        method_family=card["method_family"],
        study_run_id=card["study_run_id"],
        result_artifact_path=result["path"],
        verified_result_artifact_sha256="0" * 64,
        selected_result_id=card["selected_result_id"],
    )
    assert mutated_id != card["card_id"]


def test_adapter_refuses_in_place_result_mutation(tmp_path: Path) -> None:
    _copy_inputs(ROOT, tmp_path, SC_INPUTS)
    result_path = tmp_path / "data/experiments/synthetic_control_phase0_results.json"
    result_path.write_bytes(result_path.read_bytes() + b"\n")

    with pytest.raises(CardContractError, match="artifact digest mismatch"):
        adapt_synthetic_control(tmp_path)


def test_selected_result_drift_never_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _copy_inputs(ROOT, tmp_path, SC_INPUTS)
    result_path = tmp_path / "data/experiments/synthetic_control_phase0_results.json"
    artifact = json.loads(result_path.read_text(encoding="utf-8"))
    del artifact["families"]["sp_pure_adds"]["arms"]["sc_nnls"]["real"]["0_5"]
    result_path.write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr(ric, "_SC_RESULT_SHA256", sha256_file(result_path))

    with pytest.raises(CardContractError, match="frozen synthetic-control result"):
        adapt_synthetic_control(tmp_path)


def test_missing_statistic_never_becomes_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _copy_inputs(ROOT, tmp_path, SC_INPUTS)
    result_path = tmp_path / "data/experiments/synthetic_control_phase0_results.json"
    artifact = json.loads(result_path.read_text(encoding="utf-8"))
    del artifact["families"]["sp_pure_adds"]["arms"]["sc_nnls"]["real"]["0_5"]["t"]
    result_path.write_text(json.dumps(artifact), encoding="utf-8")
    monkeypatch.setattr(ric, "_SC_RESULT_SHA256", sha256_file(result_path))

    with pytest.raises(CardContractError, match="frozen synthetic-control result"):
        adapt_synthetic_control(tmp_path)


def test_failed_required_diagnostic_cannot_be_upgraded_to_complete() -> None:
    card = adapt_synthetic_control(ROOT)
    card["quality"] = "COMPLETE"

    with pytest.raises(CardContractError, match="failed diagnostic"):
        validate_card(card)


def test_missing_input_receipts_force_artifact_incomplete() -> None:
    card = adapt_hincl2_event_study(ROOT)
    card["quality"] = "COMPLETE"

    with pytest.raises(CardContractError, match="missingness"):
        validate_card(card)


def test_true_or_extra_authority_is_rejected() -> None:
    true_authority = adapt_synthetic_control(ROOT)
    true_authority["authority"]["trading_authority"] = True
    with pytest.raises(CardContractError, match="all authority flags"):
        validate_card(true_authority)

    extra_authority = adapt_synthetic_control(ROOT)
    extra_authority["authority"]["promotion_authority"] = False
    with pytest.raises(CardContractError, match="authority keys are not closed"):
        validate_card(extra_authority)


def test_extra_or_prohibited_top_level_field_is_rejected() -> None:
    card = adapt_synthetic_control(ROOT)
    card["rank"] = 1

    with pytest.raises(CardContractError, match="prohibited"):
        validate_card(card)


def test_ordered_effect_path_requires_unique_increasing_owner_horizons() -> None:
    card = adapt_hincl2_event_study(ROOT)
    duplicate = deepcopy(card["ordered_effect_path"]["points"][0])
    card["ordered_effect_path"]["points"].append(duplicate)

    with pytest.raises(CardContractError, match="unique and increasing"):
        validate_card(card)


def test_return_fraction_interval_requires_three_ordered_quantiles() -> None:
    card = adapt_hincl2_event_study(ROOT)
    interval = _coded(card["uncertainty"], "mean_ci90")

    interval["value"] = [-0.18, -0.08]
    with pytest.raises(CardContractError, match="three ordered quantiles"):
        validate_card(card)

    interval["value"] = [-0.18, -0.01, -0.08]
    with pytest.raises(CardContractError, match="three ordered quantiles"):
        validate_card(card)


def test_null_source_as_of_requires_a_typed_reason() -> None:
    card = adapt_hincl2_event_study(ROOT)
    roster = next(
        source
        for source in card["source_artifacts"]
        if source["role"] == "event_roster"
    )
    assert roster["as_of"] is None
    assert roster["as_of_reason"]["en"]
    assert roster["as_of_reason"]["zh"]

    roster["as_of_reason"] = None
    with pytest.raises(CardContractError, match="null as_of requires"):
        validate_card(card)


def test_counterexample_receipts_preserve_resolution_and_split_magnitudes() -> None:
    synthetic = adapt_synthetic_control(ROOT)
    event = adapt_hincl2_event_study(ROOT)

    assert _coded(synthetic["placebos_or_counterexamples"], "empirical_p_floor")[
        "value"
    ] == pytest.approx(0.004975124378109453)
    assert (
        _coded(event["placebos_or_counterexamples"], "split_half_first_mean")["value"]
        == -0.00785
    )
    assert (
        _coded(event["placebos_or_counterexamples"], "split_half_second_mean")["value"]
        == -0.16839
    )


def test_fixed_adapter_order_is_not_metric_ranking() -> None:
    envelope = getattr(ric, "build_research_implication_cards")(ROOT)

    assert envelope["schema"] == ric.ENVELOPE_SCHEMA
    assert [card["method_family"] for card in envelope["cards"]] == [
        "synthetic_control",
        "event_study",
    ]
    assert (
        envelope["cards"][0]["outputs"][0]["value"]
        > envelope["cards"][1]["outputs"][0]["value"]
    )


def test_measurement_builder_writes_same_contract_machine_projection(
    tmp_path: Path,
) -> None:
    from scripts import build_measurement as measurement

    envelope = ric.build_research_implication_cards(ROOT)
    output_path = tmp_path / "measurementdata" / "research_implication_cards.json"
    getattr(measurement, "write_research_implication_projection")(envelope, output_path)

    projected = json.loads(output_path.read_text(encoding="utf-8"))
    js_payload = json.loads(
        re.search(
            r"window\.MEASUREMENT=(.+);$",
            measurement.emit_js({"research_implications": envelope}),
            re.DOTALL | re.MULTILINE,
        ).group(1)
    )
    assert projected == envelope
    assert js_payload["research_implications"] == projected
    assert [card["card_id"] for card in projected["cards"]] == [
        card["card_id"] for card in js_payload["research_implications"]["cards"]
    ]
