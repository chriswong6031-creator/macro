from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from engine.company_intelligence.views import build_bundle as build_company_bundle
from engine.company_intelligence.views import write_generation as write_company_generation
from engine.company_theme_exposure.contracts import ContractError, canonical_json_bytes, canonical_json_sha256, validate_exposure, validate_manifest
from engine.company_theme_exposure.health import validate_generation
from engine.company_theme_exposure.views import build_bundle, load_company_generation, write_generation
from engine.company_theme_exposure.views import _active_membership, _canonical_theme_ids, _crosswalk_index, _theme_state_receipt
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
    return {
        "schema": "neuralweb.theme_state.v1", "as_of": as_of, "stale_legs": stale_legs or [],
        "n_themes": 1, "themes": [{"theme_id": "canonical_theme"}],
        "authority": {"is_context_only": True},
    }


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
        "theme_id": "canonical_theme", "name_en": "Canonical Theme", "name_zh": "规范主题", "basket_id": "mapped", "mapping_qualifier": "curated",
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
        assert manifest["status"] == "partial" and warning in manifest["warnings"]
        assert exposures["AAPL"]["status"] == "partial"
        assert warning in exposures["AAPL"]["warnings"]
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


def test_lossy_crosswalk_membership_carries_a_bounded_proxy_qualifier() -> None:
    membership = {
        "baskets": {"managed_care": {"members": []}, "reshoring": {"members": []}},
    }
    crosswalk = {
        "version": 1,
        "themes": [
            {"id": "medical_devices", "foresight_id": "medical_devices", "name_en": "Medical Devices", "name_zh": "医疗器械", "basket_ids": ["managed_care"], "note": "No dedicated basket; managed_care is the closest healthcare basket."},
            {"id": "copper", "foresight_id": "copper", "name_en": "Copper", "name_zh": "铜", "basket_ids": ["reshoring"], "note": "reshoring basket is the closest match."},
        ],
        "unmapped_baskets": [],
    }
    index = _crosswalk_index(crosswalk, membership)
    assert index["managed_care"]["mapping_qualifier"] == "proxy"
    assert index["reshoring"]["mapping_qualifier"] == "proxy"


def test_live_theme_inputs_are_closed_accounted_and_contract_valid() -> None:
    """Guard the exact production inputs, not only synthetic fixtures."""
    root = Path(__file__).resolve().parents[1]
    ci_workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for live_input in (
        "data/baskets/membership.json",
        "config/theme_crosswalk.yml",
        "data/neuralweb/theme_state.json",
    ):
        assert f'- "{live_input}"' in ci_workflow
    membership = json.loads((root / "data/baskets/membership.json").read_text(encoding="utf-8"))
    crosswalk = yaml.safe_load((root / "config/theme_crosswalk.yml").read_text(encoding="utf-8"))
    theme_state = json.loads((root / "data/neuralweb/theme_state.json").read_text(encoding="utf-8"))

    assert isinstance(membership, dict) and isinstance(crosswalk, dict) and isinstance(theme_state, dict)
    curated = date.fromisoformat(membership["curated"])
    theme_by_basket = _crosswalk_index(crosswalk, membership)
    explicit_unmapped = {item["id"] for item in crosswalk["unmapped_baskets"]}
    known_baskets = set(membership["baskets"])

    assert len(known_baskets) == 47
    assert len(theme_by_basket) == 18
    assert len(explicit_unmapped) == 29
    assert set(theme_by_basket).isdisjoint(explicit_unmapped)
    assert set(theme_by_basket) | explicit_unmapped == known_baskets
    assert {item["mapping_qualifier"] for item in theme_by_basket.values()} <= {"direct", "proxy", "curated"}
    assert theme_by_basket["managed_care"]["mapping_qualifier"] == "proxy"
    assert theme_by_basket["reshoring"]["mapping_qualifier"] == "proxy"

    active = _active_membership(membership, as_of=curated)
    active_count = sum(len(baskets) for baskets in active.values())
    mapped_count = sum(len(baskets & set(theme_by_basket)) for baskets in active.values())
    unmapped_count = active_count - mapped_count
    assert (active_count, mapped_count, unmapped_count) == (1009, 246, 763)
    assert len(active) == 691
    assert sum(not bool(baskets & set(theme_by_basket)) for baskets in active.values()) == 489

    assert theme_state["schema"] == "neuralweb.theme_state.v1"
    state_as_of = date.fromisoformat(theme_state["as_of"])
    receipt, warnings = _theme_state_receipt(
        theme_state,
        as_of=state_as_of,
        canonical_theme_ids=_canonical_theme_ids(crosswalk),
    )
    expected_state = "stale" if theme_state.get("stale_legs") else "fresh"
    assert receipt["status"] == expected_state
    assert warnings == (["theme_state_stale"] if expected_state == "stale" else [])


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
    assert validate_generation(tmp_path / "out")["status"] == "partial"
    (generation / "companies" / "AAPL.json").write_text("{}")
    assert validate_generation(tmp_path / "out")["status"] == "degraded"


@pytest.mark.parametrize(
    "state",
    [
        _state(as_of="2026-02-03"),
        {"schema": "neuralweb.theme_state.v1", "as_of": "2026-02-02", "n_themes": 0, "themes": [], "authority": {"is_context_only": True}},
    ],
)
def test_future_or_structurally_empty_theme_state_is_never_fresh(tmp_path, state) -> None:
    contexts, ci_manifest = _company_tree(tmp_path / "company")
    exposures, manifest = build_bundle(
        contexts, company_manifest=ci_manifest, membership=_membership(), crosswalk=_crosswalk(), theme_state=state, as_of="2026-02-02",
    )
    assert manifest["status"] == "partial"
    assert exposures["AAPL"]["theme_state"]["status"] == "invalid"


def test_unmapped_and_no_membership_coverage_are_explicitly_distinct(tmp_path) -> None:
    contexts, ci_manifest = _company_tree(tmp_path / "company")
    membership = _membership()
    membership["baskets"]["unmapped"]["members"].append({"ticker": "NVDA", "added": "2025-01-01", "removed": None})
    exposures, manifest = build_bundle(
        contexts, company_manifest=ci_manifest, membership=membership, crosswalk=_crosswalk(), theme_state=_state(), as_of="2026-02-02",
    )
    assert exposures["AAPL"]["coverage"] == {
        "status": "mixed", "active_basket_count": 2, "mapped_basket_count": 1, "unmapped_basket_count": 1,
    }
    assert exposures["AAPL"]["warnings"] == ["active_membership_unmapped"]
    assert exposures["NVDA"]["coverage"]["status"] == "unmapped_only"
    assert manifest["coverage"]["unmapped_membership_count"] == 2
    assert manifest["warnings"] == ["active_memberships_unmapped"]


@pytest.mark.parametrize(
    "member",
    [
        {"ticker": "../AAPL", "added": "2025-01-01", "removed": "2026-01-01"},
        {"ticker": "AAPL", "added": "2025-01-01", "removed": "not-a-date"},
        {"ticker": "AAPL", "added": "not-a-date", "removed": None},
    ],
)
def test_malformed_member_rows_fail_closed_even_when_removed(tmp_path, member) -> None:
    contexts, ci_manifest = _company_tree(tmp_path / "company")
    membership = _membership()
    membership["baskets"]["mapped"]["members"] = [member]
    with pytest.raises(ContractError, match="member"):
        build_bundle(
            contexts, company_manifest=ci_manifest, membership=membership, crosswalk=_crosswalk(), theme_state=_state(), as_of="2026-02-02",
        )


def test_writer_rejects_mutated_object_stale_generation_and_swapped_ticker(tmp_path) -> None:
    exposures, manifest = _bundle(tmp_path)
    exposures["AAPL"]["exposures"][0]["mapping_qualifier"] = "direct"
    with pytest.raises(ContractError, match="generation_id does not bind"):
        write_generation(tmp_path / "mutated", exposures, manifest)
    exposures, manifest = _bundle(tmp_path / "fresh")
    swapped = dict(exposures)
    swapped["AAPL"] = exposures["NVDA"]
    with pytest.raises(ContractError, match="filename ticker"):
        write_generation(tmp_path / "swapped", swapped, manifest)


def test_health_rejects_same_generation_with_changed_object_or_swapped_path(tmp_path) -> None:
    exposures, manifest = _bundle(tmp_path)
    generation = write_generation(tmp_path / "out", exposures, manifest)
    marker = json.loads((tmp_path / "out" / "manifest.json").read_text())
    aapl = generation / "companies" / "AAPL.json"
    nvda = generation / "companies" / "NVDA.json"
    aapl_body, nvda_body = aapl.read_bytes(), nvda.read_bytes()
    aapl.write_bytes(nvda_body)
    nvda.write_bytes(aapl_body)
    # Forge both receipts to isolate the filename/payload guard from the byte guard.
    from hashlib import sha256
    marker["files"]["companies/AAPL.json"] = {"sha256": sha256(nvda_body).hexdigest(), "bytes": len(nvda_body)}
    marker["files"]["companies/NVDA.json"] = {"sha256": sha256(aapl_body).hexdigest(), "bytes": len(aapl_body)}
    forged_marker = canonical_json_bytes(marker)
    (tmp_path / "out" / "manifest.json").write_bytes(forged_marker)
    (generation / "manifest.json").write_bytes(forged_marker)
    health = validate_generation(tmp_path / "out")
    assert health["status"] == "degraded"
    assert any("filename ticker" in warning for warning in health["warnings"])


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
    assert marker["warnings"] == ["active_memberships_unmapped", "theme_state_missing"]
