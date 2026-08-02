from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from engine.company_intelligence.views import build_bundle as build_company_bundle, write_generation as write_company_generation
from engine.company_institutional_context.contracts import ContractError, canonical_json_bytes, canonical_json_sha256, validate_context, validate_manifest
from engine.company_institutional_context.health import validate_generation
from engine.company_institutional_context.views import aligned_consensus_period, build_bundle, load_company_intelligence, load_config, write_generation
from scripts.build_company_institutional_context import main as build_cli


def _company_tree(tmp_path: Path):
    history = [
        {"document_ticker": "AAPL", "fiscal_year": 2026, "fiscal_quarter": 1, "call_date": "2026-01-29", "updated_at": "2026-08-02T00:00:00Z", "summary": "AAPL source", "raw_source_url": "https://issuer.example/aapl"},
        {"document_ticker": "NVDA", "fiscal_year": 2026, "fiscal_quarter": 1, "call_date": "2026-02-20", "updated_at": "2026-08-02T00:00:00Z", "summary": "NVDA source", "raw_source_url": "https://issuer.example/nvda"},
        {"document_ticker": "MSFT", "fiscal_year": 2026, "fiscal_quarter": 1, "call_date": "2026-01-28", "updated_at": "2026-08-02T00:00:00Z", "summary": "MSFT source", "raw_source_url": "https://issuer.example/msft"},
        {"document_ticker": "GOOG", "fiscal_year": 2026, "fiscal_quarter": 1, "call_date": "2026-02-04", "updated_at": "2026-08-02T00:00:00Z", "summary": "GOOG source", "raw_source_url": "https://issuer.example/goog"},
        {"document_ticker": "GOOGL", "fiscal_year": 2026, "fiscal_quarter": 1, "call_date": "2026-02-04", "updated_at": "2026-08-02T00:00:00Z", "summary": "GOOGL source", "raw_source_url": "https://issuer.example/googl"},
    ]
    contexts, manifest = build_company_bundle(history, tx_index={"schema": "mastermind.tx-index/v1", "documents": []}, generated_at="2026-08-02T00:00:00Z", as_of="2026-08-02")
    write_company_generation(tmp_path, contexts, manifest)
    return load_company_intelligence(tmp_path)


def _config(*, add_missing: bool = False):
    funds = {
        "alpha": {"name": "Alpha Fund", "style": "quality_growth"},
        "closed": {"name": "Closed Fund", "style": "macro", "status": "closed"},
    }
    if add_missing:
        funds["missing"] = {"name": "Missing Fund", "style": "value"}
    return {"smart_money": {"funds": funds}}


def _universe(path: Path) -> None:
    pd.DataFrame([
        {"ticker": "AAPL", "name": "Apple Inc.", "active": True},
        {"ticker": "NVDA", "name": "NVIDIA Corporation", "active": True},
        {"ticker": "MSFT", "name": "Microsoft Corporation", "active": True},
        {"ticker": "GOOG", "name": "Alphabet Inc.", "active": True},
    ]).to_parquet(path)


def _snapshot(path: Path, manager: str, period: str, filing_date: str, rows: list[dict]) -> None:
    root = path / manager
    root.mkdir(parents=True, exist_ok=True)
    for row in rows:
        row.update({"fund_slug": manager, "period_end": period, "filing_date": filing_date, "as_of": period, "sh_type": row.get("sh_type", "SH")})
    pd.DataFrame(rows).to_parquet(root / f"{period}.parquet")


def _rows(*, shares_a: float, shares_b: float = 0.0, nvda: float = 0.0, goog: float = 0.0):
    result = [{"cusip": "037833100", "issuer": "APPLE INC", "shares": shares_a, "value_usd": shares_a * 10}]
    if shares_b:
        result.append({"cusip": "037833101", "issuer": "APPLE INC", "shares": shares_b, "value_usd": shares_b * 10})
    if nvda:
        result.append({"cusip": "67066G104", "issuer": "NVIDIA CORP", "shares": nvda, "value_usd": nvda * 20})
    if goog:
        result.append({"cusip": "02079K107", "issuer": "ALPHABET INC", "shares": goog, "value_usd": goog * 30})
    return result


def _bundle(tmp_path: Path, *, missing: bool = False):
    contexts, ci = _company_tree(tmp_path / "company")
    snapshot_root = tmp_path / "smart_money"
    _snapshot(snapshot_root, "alpha", "2025-12-31", "2026-02-14", _rows(shares_a=5, nvda=1, goog=2))
    _snapshot(snapshot_root, "alpha", "2026-03-31", "2026-05-15", _rows(shares_a=7, shares_b=3, nvda=1, goog=3))
    # An early individual Q2 filing is deliberately present but cannot affect
    # the Q1 consensus before the full 45-day Q2 reporting window closes.
    _snapshot(snapshot_root, "alpha", "2026-06-30", "2026-07-10", _rows(shares_a=1, nvda=9, goog=1))
    # This record must never enter the active consensus, regardless of its size.
    _snapshot(snapshot_root, "closed", "2026-03-31", "2026-04-01", _rows(shares_a=999))
    universe = tmp_path / "membership.parquet"
    _universe(universe)
    config = _config(add_missing=missing)
    generated, manifest = build_bundle(
        contexts, company_manifest=ci, smart_money_config=config["smart_money"]["funds"],
        smart_money_config_sha256=canonical_json_sha256(config), share_class_equivalence_sha256="b" * 64, universe_membership_sha256="a" * 64,
        snapshot_root=snapshot_root, universe_membership=universe, as_of="2026-08-02",
    )
    return generated, manifest, snapshot_root, universe, config


def test_aligned_period_never_admits_early_q2_reporters() -> None:
    assert aligned_consensus_period("2026-08-02") == ("2026-03-31", "2025-12-31", "2026-05-15")
    assert aligned_consensus_period("2026-08-14")[0] == "2026-06-30"


def test_coverage_aligned_context_excludes_closed_and_collapses_share_classes(tmp_path) -> None:
    contexts, manifest, _root, _universe_path, _config_payload = _bundle(tmp_path)
    aapl = contexts["AAPL"]
    assert manifest["consensus_period"] == "2026-03-31"
    assert aapl["coverage"] == {
        "configured_manager_count": 2, "active_manager_count": 1, "closed_manager_count": 1,
        "reporting_manager_count": 1, "missing_manager_count": 0, "comparison_reporting_manager_count": 1,
        "comparison_missing_manager_count": 0, "resolved_position_count": 3, "unresolved_position_count": 0,
    }
    assert len(aapl["positions"]) == 1
    assert aapl["positions"][0]["manager"] == "alpha"
    assert aapl["positions"][0]["shares"] == 10
    assert aapl["positions"][0]["action"] == "add"
    assert aapl["period"]["consensus_available_on"] == "2026-05-15"
    assert aapl["period"]["latest_reporting_filing_date"] == "2026-05-15"
    assert aapl["trend"]["direction"] == "accumulating"
    assert contexts["MSFT"]["status"] == "no_covered_holder"
    assert contexts["MSFT"]["positions"] == []
    assert contexts["GOOG"]["positions"] == contexts["GOOGL"]["positions"]
    assert "closed" not in {row["manager"] for row in aapl["positions"]}
    assert manifest["source"]["snapshot_index"]["manager_count"] == 1
    validate_context(aapl)
    validate_manifest(manifest, allow_unmaterialized_files=True)


def test_incomplete_current_quarter_is_quarantined_and_never_becomes_consensus(tmp_path) -> None:
    contexts, manifest, _root, _universe_path, _config_payload = _bundle(tmp_path, missing=True)
    aapl = contexts["AAPL"]
    assert manifest["status"] == "partial"
    assert aapl["period"]["consensus_available_on"] is None
    assert aapl["coverage"]["missing_manager_count"] == 1
    assert "current_snapshots_missing" in aapl["warnings"]
    assert aapl["trend"]["direction"] is None
    assert aapl["trend"]["status"] == "insufficient_coverage"


def test_missing_comparison_snapshot_never_mints_a_new_action(tmp_path) -> None:
    contexts, manifest, root, universe, config = _bundle(tmp_path)
    (root / "alpha" / "2025-12-31.parquet").unlink()
    ci_contexts, ci = _company_tree(tmp_path / "reloaded-company")
    generated, _manifest = build_bundle(
        ci_contexts, company_manifest=ci, smart_money_config=config["smart_money"]["funds"],
        smart_money_config_sha256=canonical_json_sha256(config), share_class_equivalence_sha256="b" * 64, universe_membership_sha256="a" * 64,
        snapshot_root=root, universe_membership=universe, as_of="2026-08-02",
    )
    assert generated["AAPL"]["positions"][0]["action"] == "unavailable"
    assert "comparison_snapshots_missing" in generated["AAPL"]["warnings"]


def test_contract_refuses_unknowns_signal_claims_and_period_end_availability(tmp_path) -> None:
    contexts, _manifest, _root, _universe_path, _config_payload = _bundle(tmp_path)
    payload = json.loads(json.dumps(contexts["AAPL"]))
    payload["signal"] = "buy"
    with pytest.raises(ContractError, match="fields mismatch"):
        validate_context(payload)
    payload = json.loads(json.dumps(contexts["AAPL"]))
    payload["period"]["consensus_available_on"] = payload["period"]["consensus_period"]
    with pytest.raises(ContractError, match="public filing date"):
        validate_context(payload)


def test_immutable_identity_health_and_corruption_detection(tmp_path) -> None:
    contexts, manifest, _root, _universe_path, _config_payload = _bundle(tmp_path)
    generation = write_generation(tmp_path / "out", contexts, manifest)
    marker = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert validate_generation(tmp_path / "out")["status"] == "ready"
    assert generation.name == marker["generation_id"]
    (generation / "companies" / "AAPL.json").write_text("{}")
    assert validate_generation(tmp_path / "out")["status"] == "degraded"


def test_generation_identity_changes_when_pinned_company_tree_changes(tmp_path) -> None:
    first, first_manifest, _root, _universe_path, _config_payload = _bundle(tmp_path / "first")
    second, second_manifest, _root, _universe_path, _config_payload = _bundle(tmp_path / "second")
    # Different immutable CI sources necessarily produce separately addressable sidecars.
    assert first_manifest["generation_id"] == second_manifest["generation_id"]
    assert first["AAPL"]["company_intelligence"]["generation_id"] == second["AAPL"]["company_intelligence"]["generation_id"]
    changed = json.loads(json.dumps(second["AAPL"]))
    changed["positions"][0]["shares"] = 11
    with pytest.raises(ContractError, match="generation_id"):
        write_generation(tmp_path / "bad", {**second, "AAPL": changed}, second_manifest)


def test_cli_uses_verified_ci_tree_and_config_receipts(tmp_path) -> None:
    contexts, ci = _company_tree(tmp_path / "company")
    root = tmp_path / "smart_money"
    _snapshot(root, "alpha", "2025-12-31", "2026-02-14", _rows(shares_a=5))
    _snapshot(root, "alpha", "2026-03-31", "2026-05-15", _rows(shares_a=7))
    universe = tmp_path / "membership.parquet"
    _universe(universe)
    config = tmp_path / "config.yml"
    config.write_text(yaml.safe_dump(_config(), sort_keys=False))
    output = tmp_path / "out"
    assert build_cli([
        "--company-intelligence-dir", str(tmp_path / "company"), "--smart-money-config", str(config),
        "--snapshot-root", str(root), "--universe-membership", str(universe), "--out-dir", str(output), "--as-of", "2026-08-02",
    ]) == 0
    marker = json.loads((output / "manifest.json").read_text())
    assert marker["source"]["smart_money_config"]["sha256"] == canonical_json_sha256(_config())
