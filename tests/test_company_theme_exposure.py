from __future__ import annotations

import json

import pytest
import yaml

from engine.company_intelligence.views import build_bundle as build_company_bundle
from engine.company_intelligence.views import write_generation as write_company_generation
from engine.company_theme_exposure.contracts import ContractError, canonical_json_sha256, validate_exposure, validate_manifest
from engine.company_theme_exposure.health import validate_generation
from engine.company_theme_exposure.views import build_bundle, load_company_generation, write_generation
from scripts.build_company_theme_exposure import main as build_cli


def _company_tree(tmp_path, *, summary: str = "source summary"):
    history = [
        {
            "document_ticker": "AAPL", "fiscal_year": 2026, "fiscal_quarter": 1,
            "call_date": "2026-01-29", "updated_at": "2026-02-01T00:00:00Z",
            "summary": summary, "raw_source_url": "https://issuer.example/aapl",
        },
        {
            "document_ticker": "NVDA", "fiscal_year": 2026, "fiscal_quarter": 1,
            "call_date": "2026-02-20", "updated_at": "2026-02-01T00:00:00Z",
            "summary": "another source summary", "raw_source_url": "https://issuer.example/nvda",
        },
    ]
    contexts, descriptor = build_company_bundle(
        history,
        tx_index={"schema": "mastermind.tx-index/v1", "documents": []},
        generated_at="2026-02-02T00:00:00Z",
        as_of="2026-02-02",
    )
    write_company_generation(tmp_path, contexts, descriptor)
    return load_company_generation(tmp_path)


def _membership():
    return {
        "version": "fixture",
        "curated": "2026-02-02",
        "baskets": {
            "mapped": {"members": [
                {"ticker": "AAPL", "added": "2025-01-01", "removed": None},
                {"ticker": "NVDA", "added": "2025-01-01", "removed": "2026-01-01"},
            ]},
            "unmapped": {"members": [{"ticker": "AAPL", "added": "2025-01-01", "removed": None}]},
        },
    }


def _crosswalk():
    return {
        "version": 1,
        "themes": [{
            "id": "canonical_theme", "foresight_id": "canonical_theme",
            "name_en": "Canonical Theme", "name_zh": "规范主题", "basket_ids": ["mapped"],
        }],
        "unmapped_baskets": [{"id": "unmapped", "reason": "explicitly outside the canonical theme registry"}],
    }


def _state(*, as_of: str = "2026-02-02", stale_legs=None):
    return {"schema": "neuralweb.theme_state.v1", "as_of": as_of, "stale_legs": stale_legs or [], "themes": []}


def _bundle(tmp_path, **kwargs):
    contexts, ci_manifest = _company_tree(tmp_path / "company", **kwargs)
    return build_bundle(
        contexts, company_manifest=ci_manifest, membership=_membership(), crosswalk=_crosswalk(),
        theme_state=_state(), as_of="2026-02-02",
    )


def test_active_membership_crosswalk_and_ci_event_are_exactly_receipted(tmp_path) -> None:
    contexts, ci_manifest = _company_tree(tmp_path / "company")
    exposures, manifest = build_bundle(
        contexts, company_manifest=ci_manifest, membership=_membership(), crosswalk=_crosswalk(),
        theme_state=_state(), as_of="2026-02-02",
    )
    aapl = exposures["AAPL"]
    assert aapl["exposures"] == [{
        "theme_id": "canonical_theme", "name_en": "Canonical Theme", "name_zh": "规范主题", "basket_id": "mapped",
    }]
    # NVDA was removed: no historical membership leakage into current exposure.
    assert exposures["NVDA"]["exposures"] == []
    assert aapl["company_intelligence"] == {
        "generation_id": ci_manifest["generation_id"],
        "context_sha256": canonical_json_sha256(contexts["AAPL"]),
        "latest_event_id": contexts["AAPL"]["latest_event_id"],
        "latest_event_call_date": "2026-01-29",
    }
    assert manifest["source"]["company_intelligence"]["sha256"] == canonical_json_sha256(ci_manifest)
    assert manifest["source"]["membership"]["sha256"] == canonical_json_sha256(_membership())
    assert manifest["source"]["crosswalk"]["sha256"] == canonical_json_sha256(_crosswalk())
    assert manifest["exposure_count"] == 1


def test_missing_stale_or_invalid_theme_state_is_honest_partial_and_contains_no_model_output(tmp_path) -> None:
    contexts, ci_manifest = _company_tree(tmp_path / "company")
    for state, warning in (
        (None, "theme_state_missing"),
        ({"schema": "wrong", "as_of": "2026-02-02"}, "theme_state_invalid"),
        (_state(as_of="2026-01-01"), "theme_state_stale"),
    ):
        exposures, manifest = build_bundle(
            contexts, company_manifest=ci_manifest, membership=_membership(), crosswalk=_crosswalk(),
            theme_state=state, as_of="2026-02-02",
        )
        assert manifest["status"] == "partial" and manifest["warnings"] == [warning]
        assert exposures["AAPL"]["status"] == "partial"
        assert exposures["AAPL"]["warnings"] == [warning]
        assert not {"score", "signal", "ranking", "recommendation", "stage"} & set(exposures["AAPL"])


def test_crosswalk_requires_all_baskets_to_be_explicitly_mapped_or_unmapped(tmp_path) -> None:
    contexts, ci_manifest = _company_tree(tmp_path / "company")
    broken = _crosswalk()
    broken["unmapped_baskets"] = []
    with pytest.raises(ContractError, match="does not account"):
        build_bundle(
            contexts, company_manifest=ci_manifest, membership=_membership(), crosswalk=broken,
            theme_state=_state(), as_of="2026-02-02",
        )


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda payload: payload.__setitem__("score", 99), "fields mismatch"),
        (lambda payload: payload["exposures"][0].__setitem__("signal", "buy"), "fields mismatch"),
        (lambda payload: payload["company_intelligence"].__setitem__("peer_readthrough", "supplier"), "fields mismatch"),
        (lambda payload: payload.__setitem__("authority", "ranking"), "context_only"),
    ],
)
def test_closed_contract_refuses_scores_signals_and_relationship_claims(tmp_path, mutate, match) -> None:
    exposures, _ = _bundle(tmp_path)
    payload = json.loads(json.dumps(exposures["AAPL"]))
    mutate(payload)
    with pytest.raises(ContractError, match=match):
        validate_exposure(payload)


def test_company_generation_change_readdresses_sidecar_and_preserves_latest_identity(tmp_path) -> None:
    first_contexts, first_ci = _company_tree(tmp_path / "first", summary="first")
    second_contexts, second_ci = _company_tree(tmp_path / "second", summary="corrected")
    first, first_manifest = build_bundle(
        first_contexts, company_manifest=first_ci, membership=_membership(), crosswalk=_crosswalk(), theme_state=_state(), as_of="2026-02-02",
    )
    second, second_manifest = build_bundle(
        second_contexts, company_manifest=second_ci, membership=_membership(), crosswalk=_crosswalk(), theme_state=_state(), as_of="2026-02-02",
    )
    assert first_ci["generation_id"] != second_ci["generation_id"]
    assert first_manifest["generation_id"] != second_manifest["generation_id"]
    assert second["AAPL"]["company_intelligence"]["generation_id"] == second_ci["generation_id"]
    assert first["AAPL"]["company_intelligence"]["latest_event_id"] == second["AAPL"]["company_intelligence"]["latest_event_id"]


def test_immutable_write_and_health_verify_marker_tree(tmp_path) -> None:
    exposures, manifest = _bundle(tmp_path)
    generation = write_generation(tmp_path / "out", exposures, manifest)
    marker = json.loads((tmp_path / "out" / "manifest.json").read_text())
    validate_manifest(marker)
    assert generation.name == marker["generation_id"]
    assert validate_generation(tmp_path / "out")["status"] == "ready"
    (generation / "companies" / "AAPL.json").write_text("{}")
    assert validate_generation(tmp_path / "out")["status"] == "degraded"


def test_cli_builds_from_verified_ci_tree_and_missing_state_becomes_partial(tmp_path) -> None:
    _company_tree(tmp_path / "company")
    membership = tmp_path / "membership.json"
    crosswalk = tmp_path / "crosswalk.yml"
    membership.write_text(json.dumps(_membership()))
    crosswalk.write_text(yaml.safe_dump(_crosswalk(), sort_keys=False))
    output = tmp_path / "out"
    assert build_cli([
        "--company-intelligence-dir", str(tmp_path / "company"),
        "--membership", str(membership),
        "--crosswalk", str(crosswalk),
        "--theme-state", str(tmp_path / "theme_state.json"),
        "--out-dir", str(output),
        "--as-of", "2026-02-02",
    ]) == 0
    marker = json.loads((output / "manifest.json").read_text())
    assert marker["status"] == "partial"
    assert marker["warnings"] == ["theme_state_missing"]
