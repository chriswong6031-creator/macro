"""FIF-1R2 contract closure: temporal, evidence, admission, determinism, tamper."""
from __future__ import annotations

import copy
from decimal import ROUND_DOWN, getcontext
import json
import os
from pathlib import Path
import subprocess

import pytest

from engine.fundamental_forensics.financial_intelligence_packet import (
    PACKET_MAX_EVIDENCE_NODES,
    PACKET_MAX_METRICS,
    PACKET_MAX_PERIODS,
    PACKET_MAX_SERIALIZED_BYTES,
    PacketEvidenceDigests,
    PacketQueryRequest,
    admit_filing_package_fixture_bytes,
    assemble_financial_intelligence_packet,
    assert_formula_evidence_closed,
    canonical_packet_bytes,
    digest_builder_source,
    formula_leaves,
    load_core_registry,
    load_filing_package_fixture,
    load_packet_schema,
    validate_packet,
    validate_packet_semantics,
)
from engine.fundamental_forensics.query import PeriodRequest, QueryPolicy
from engine.fundamental_forensics.raw_ledger import (
    FactContext,
    RawFactLedger,
)
from engine.fundamental_forensics.synthetic_filing_package import (
    build_multihop_revenue_fixture,
    build_synthetic_filing_package_fixture,
    filing as synthetic_filing,
    usd_fact,
)
from tests.test_fundamental_forensics_financial_intelligence_packet import (
    BUILDER_PATH,
    COMPANYFACTS_WITNESS,
    GOLDEN_PATH,
    LEDGER_PATH,
    PYTHON,
    ROOT,
    SCHEMA_PATH,
    SUBMISSIONS_WITNESS,
    _build,
    _cell,
    _context,
    _input_digests,
)


CATALOG_AVAILABLE = "2026-08-02T00:00:00Z"
T0_SOURCE = "2024-01-01T00:00:00Z"
T1_SOURCE = "2024-12-31T23:59:59Z"
T2_SOURCE = "2025-12-31T23:59:59Z"
T2_RECORDED = "2026-08-03T12:00:00Z"
T3_SOURCE = "2025-12-31T23:59:59Z"
T3_RECORDED = "2026-08-05T12:00:02Z"
RULE_PRE_RECORDED = "2026-08-01T12:00:02Z"


def test_four_state_two_clock_revenue_and_receivables() -> None:
    t0 = _build(policy="latest_known_as_of", source_event_cutoff=T0_SOURCE, system_recorded_cutoff=T2_RECORDED)
    t1 = _build(policy="latest_known_as_of", source_event_cutoff=T1_SOURCE, system_recorded_cutoff=T2_RECORDED)
    t2 = _build(policy="latest_known_as_of", source_event_cutoff=T2_SOURCE, system_recorded_cutoff=T2_RECORDED)
    t3 = _build(policy="latest_known_as_of", source_event_cutoff=T3_SOURCE, system_recorded_cutoff=T3_RECORDED)
    assert _cell(t0, "revenue", "FY2023")["non_value_state"] == "missing"
    assert _cell(t0, "accounts_receivable_net", "2023-12-31")["non_value_state"] == "missing"
    assert _cell(t1, "revenue", "FY2023")["value"] == "1050"
    assert _cell(t1, "accounts_receivable_net", "2023-12-31")["value"] == "120"
    assert _cell(t2, "revenue", "FY2023")["value"] == "1050"
    assert _cell(t2, "accounts_receivable_net", "2023-12-31")["value"] == "120"
    assert "1060" not in canonical_packet_bytes(t2).decode("utf-8")
    assert "121" not in {
        _cell(t2, "accounts_receivable_net", "2023-12-31")["value"],
        *{row["revised_value"] for row in t2["revisions"] if row["metric_id"] == "accounts_receivable_net"},
    }
    assert t2["revisions"] == []
    assert _cell(t3, "revenue", "FY2023")["value"] == "1060"
    assert _cell(t3, "accounts_receivable_net", "2023-12-31")["value"] == "121"
    assert t3["revisions"]


def test_latest_restated_respects_cutoffs() -> None:
    leaked = _build(policy="latest_restated", source_event_cutoff=T2_SOURCE, system_recorded_cutoff=T2_RECORDED)
    assert _cell(leaked, "revenue", "FY2023")["non_value_state"] == "missing"
    known = _build(policy="latest_restated", source_event_cutoff=T3_SOURCE, system_recorded_cutoff=T3_RECORDED)
    assert _cell(known, "revenue", "FY2023")["value"] == "1060"
    assert known["query"]["evaluation_mode"] == "historical_replay"


def test_rule_availability_pre_and_post_catalog() -> None:
    pre = _build(policy="latest_known_as_of", source_event_cutoff=T3_SOURCE, system_recorded_cutoff=RULE_PRE_RECORDED)
    post = _build(policy="latest_known_as_of", source_event_cutoff=T1_SOURCE, system_recorded_cutoff=T2_RECORDED)
    assert _cell(pre, "revenue", "FY2023")["non_value_state"] == "unsupported"
    assert _cell(post, "revenue", "FY2023")["value"] == "1050"
    assert CATALOG_AVAILABLE < T2_RECORDED


def test_formula_uses_historically_admissible_dependencies() -> None:
    t2 = _build(
        policy="latest_known_as_of",
        source_event_cutoff=T2_SOURCE,
        system_recorded_cutoff=T2_RECORDED,
        metrics=("gross_margin", "revenue"),
        periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
    )
    t3 = _build(
        policy="latest_known_as_of",
        source_event_cutoff=T3_SOURCE,
        system_recorded_cutoff=T3_RECORDED,
        metrics=("gross_margin", "revenue"),
        periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
    )
    assert _cell(t2, "revenue", "FY2023")["value"] == "1050"
    assert _cell(t3, "revenue", "FY2023")["value"] == "1060"
    assert _cell(t2, "gross_margin", "FY2023")["value"] != _cell(t3, "gross_margin", "FY2023")["value"]


def test_null_states_do_not_collapse() -> None:
    missing = _cell(_build(source_event_cutoff=T0_SOURCE, system_recorded_cutoff=T2_RECORDED), "revenue", "FY2023")
    unsupported = _cell(_build(), "CustomerCount", "FY2023")
    not_applicable = _cell(_build(), "revenue", "2023-12-31")
    zero = _build(
        fixture=__import__(
            "tests.test_fundamental_forensics_financial_intelligence_packet",
            fromlist=["_income_fixture"],
        )._income_fixture(revenue="0", gross_profit="10"),
        metrics=("gross_margin",),
        periods=(PeriodRequest.duration("2024-01-01", "2024-12-31", label="FY2024"),),
        source_event_cutoff="2026-12-31T23:59:59Z",
        input_digests=PacketEvidenceDigests(),
    )
    not_evaluable = _cell(zero, "gross_margin", "FY2024")
    assert missing["non_value_state"] == "missing"
    assert unsupported["non_value_state"] == "unsupported"
    assert not_applicable["non_value_state"] == "not_applicable"
    assert not_evaluable["non_value_state"] == "not_evaluable"
    assert len({missing["non_value_state"], unsupported["non_value_state"], not_applicable["non_value_state"], not_evaluable["non_value_state"]}) == 4


def test_multihop_revision_lineage_and_cutoff() -> None:
    fixture = build_multihop_revenue_fixture()
    mid = _build(
        fixture=fixture,
        metrics=("revenue",),
        periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        source_event_cutoff="2026-08-05T12:00:02Z",
        system_recorded_cutoff=T3_RECORDED,
        input_digests=PacketEvidenceDigests(),
    )
    hops = [row for row in mid["revisions"] if row["metric_id"] == "revenue"]
    assert {row["revision_hop"] for row in hops} == {1, 2}
    assert {row["event_type"] for row in hops} == {"restatement", "amendment"}
    selected = next(row for row in hops if row["used_as_selected_value"] is True)
    assert selected["revised_value"] == "1070"
    assert selected["revision_hop"] == 2
    assert len(selected["lineage_occurrence_ids"]) == 3
    before_c = _build(
        fixture=fixture,
        metrics=("revenue",),
        periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        source_event_cutoff="2025-12-31T23:59:59Z",
        system_recorded_cutoff=T2_RECORDED,
        input_digests=PacketEvidenceDigests(),
    )
    assert _cell(before_c, "revenue", "FY2023")["value"] == "1050"
    assert before_c["revisions"] == []


def test_revision_and_extension_are_request_scoped() -> None:
    packet = _build(metrics=("revenue",), periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),))
    assert all(row["metric_id"] == "revenue" for row in packet["revisions"])
    assert packet["coverage"]["unmapped_extension_concept_count"] == 0
    with_custom = _build(metrics=("CustomerCount",), periods=(PeriodRequest.instant("2024-12-31", label="2024-12-31"),))
    assert with_custom["coverage"]["unmapped_extension_concept_count"] == 1


def test_evidence_graph_closes_and_has_no_orphans() -> None:
    packet = _build()
    validate_packet_semantics(packet)
    gm = _cell(packet, "gross_margin", "FY2023")
    leaves = formula_leaves(packet, gm)
    assert {leaf["metric_id"] for leaf in leaves} == {"gross_profit", "revenue"}
    assert all(leaf["provenance_kind"] == "direct" for leaf in leaves)
    nested = _build(metrics=("net_debt",), periods=(PeriodRequest.instant("2024-12-31", label="2024-12-31"),))
    net = _cell(nested, "net_debt", "2024-12-31")
    nested_leaves = formula_leaves(nested, net)
    assert {leaf["metric_id"] for leaf in nested_leaves} == {
        "short_term_debt",
        "long_term_debt_current",
        "long_term_debt",
        "cash_and_cash_equivalents",
    }
    fixture = load_filing_package_fixture(LEDGER_PATH)
    for leaf in [*leaves, *nested_leaves]:
        for occurrence_id in leaf["source_occurrence_ids"]:
            assert fixture.ledger.by_id(occurrence_id) is not None


def test_request_rejects_duplicates_and_over_bounds() -> None:
    period = PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023")
    policy = QueryPolicy(source_snapshot_at=T3_SOURCE, recorded_at=T3_RECORDED, selection="latest_known_as_of")
    with pytest.raises(ValueError, match="duplicate metric"):
        PacketQueryRequest(policy=policy, metrics=("revenue", "revenue"), periods=(period,))
    with pytest.raises(ValueError, match="duplicate semantic period"):
        PacketQueryRequest(
            policy=policy,
            metrics=("revenue",),
            periods=(period, PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023-dup")),
        )
    with pytest.raises(ValueError, match="PACKET_MAX_METRICS"):
        PacketQueryRequest(
            policy=policy,
            metrics=tuple(f"m{i}" for i in range(PACKET_MAX_METRICS + 1)),
            periods=(period,),
        )
    extra_periods = tuple(
        PeriodRequest.duration(f"{2000 + i}-01-01", f"{2000 + i}-12-31", label=f"FY{2000 + i}")
        for i in range(PACKET_MAX_PERIODS + 1)
    )
    with pytest.raises(ValueError, match="PACKET_MAX_PERIODS"):
        PacketQueryRequest(policy=policy, metrics=("revenue",), periods=extra_periods)


def test_evidence_amplification_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "engine.fundamental_forensics.financial_intelligence_packet.PACKET_MAX_EVIDENCE_NODES",
        1,
    )
    with pytest.raises(ValueError, match="PACKET_MAX_EVIDENCE_NODES"):
        _build(metrics=("net_debt",), periods=(PeriodRequest.instant("2024-12-31", label="2024-12-31"),))


def test_duplicate_dependency_and_cycle_are_rejected() -> None:
    packet = _build(metrics=("gross_margin",), periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),))
    formula = _cell(packet, "gross_margin", "FY2023")
    dup = copy.deepcopy(packet)
    dup["cells"][0]["dependency_cell_ids"] = list(formula["dependency_cell_ids"]) + list(formula["dependency_cell_ids"])
    with pytest.raises(ValueError, match="duplicate dependency"):
        assert_formula_evidence_closed(dup["cells"], dup["evidence_cells"])
    cyclic = copy.deepcopy(packet)
    cyclic["cells"][0]["dependency_cell_ids"] = [cyclic["cells"][0]["cell_id"]]
    with pytest.raises(ValueError, match="cycle"):
        assert_formula_evidence_closed(cyclic["cells"], cyclic["evidence_cells"])


def test_malformed_fixture_admission_matrix() -> None:
    good = LEDGER_PATH.read_bytes()
    with pytest.raises(ValueError, match="empty"):
        admit_filing_package_fixture_bytes(b"")
    with pytest.raises(ValueError, match="UTF-8"):
        admit_filing_package_fixture_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="trailing"):
        admit_filing_package_fixture_bytes(good + b"\n{}")
    with pytest.raises(ValueError, match="duplicate object key"):
        admit_filing_package_fixture_bytes(b'{"schema":"x","schema":"y"}')
    oversized = b"{" + (b"a" * (8 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="bounded byte size"):
        admit_filing_package_fixture_bytes(oversized)


def test_mixed_entity_is_rejected() -> None:
    fixture = build_synthetic_filing_package_fixture()
    foreign_ctx = FactContext(
        context_id="c-foreign",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier="0000000042",
        start="2023-01-01",
        end="2023-12-31",
    )
    foreign_filing = synthetic_filing(
        accession="0000000042-24-000001",
        document_id="other.htm",
        accepted_at="2024-02-15T16:00:00Z",
        recorded_at="2024-02-15T16:05:00Z",
        filed_at="2024-02-15",
        entity_id="0000000042",
    )
    foreign = usd_fact(
        foreign_filing,
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        foreign_ctx,
        "9",
        source_span=(0, 1),
        source_occurrence_key="foreign-revenue",
    )
    with pytest.raises(ValueError, match="entity"):
        assemble_financial_intelligence_packet(
            entity=fixture.entity,
            ledger=RawFactLedger((*fixture.ledger.events, foreign)),
            filing_metadata=fixture.filing_metadata,
            query_request=PacketQueryRequest(
                policy=QueryPolicy(source_snapshot_at=T3_SOURCE, recorded_at=T3_RECORDED, selection="latest_known_as_of"),
                metrics=("revenue",),
                periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
            ),
            metric_registry=load_core_registry(ROOT),
            context=_context(),
            input_digests=PacketEvidenceDigests(),
        )


def test_decimal_timezone_env_and_hashseed_do_not_change_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected = canonical_packet_bytes(_build())
    ctx = getcontext()
    old_prec, old_rounding = ctx.prec, ctx.rounding
    ctx.prec = 7
    ctx.rounding = ROUND_DOWN
    try:
        assert canonical_packet_bytes(_build()) == expected
    finally:
        ctx.prec = old_prec
        ctx.rounding = old_rounding
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    monkeypatch.setenv("LANG", "C")
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    assert canonical_packet_bytes(_build()) == expected
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "3"
    env["TZ"] = "America/New_York"
    out = tmp_path / "other.json"
    subprocess.run(
        [
            PYTHON,
            str(ROOT / "scripts" / "build_financial_intelligence_packet.py"),
            "--ledger",
            str(LEDGER_PATH),
            "--companyfacts-witness",
            str(COMPANYFACTS_WITNESS),
            "--submissions-witness",
            str(SUBMISSIONS_WITNESS),
            "--policy",
            "latest_known_as_of",
            "--source-event-cutoff",
            T3_SOURCE,
            "--system-recorded-cutoff",
            T3_RECORDED,
            "--repo-root",
            str(ROOT),
            "--output",
            str(out),
        ],
        check=True,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert out.read_bytes().strip() == expected


def test_semantic_tampering_is_rejected() -> None:
    packet = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    schema = load_packet_schema(SCHEMA_PATH)
    validate_packet(packet, schema)
    cases = {
        "value": ("cells", 0, "value"),
        "source_digest": ("cells", 0, "source_digest"),
        "content_sha256": (None, None, "content_sha256"),
        "packet_id": (None, None, "packet_id"),
        "query_digest": ("receipts", None, "query_request_digest"),
        "coverage": ("coverage", None, "source_trace_complete_count"),
        "authority": ("authority", None, "class"),
    }
    for name, (section, index, field) in cases.items():
        tampered = copy.deepcopy(packet)
        if section is None:
            tampered[field] = "0" * 64 if "sha" in field or field == "content_sha256" else "fip_" + "0" * 24
            if field == "packet_id":
                tampered[field] = "fip_" + "0" * 24
        elif index is None:
            if field == "source_trace_complete_count":
                tampered[section][field] = tampered[section][field] + 1
            elif field == "query_request_digest":
                tampered[section][field] = "0" * 64
            else:
                tampered[section][field] = "tradeable"
        else:
            valued = next(i for i, cell in enumerate(tampered["cells"]) if cell["value"] is not None)
            if field == "value":
                tampered["cells"][valued]["value"] = "1"
            elif field == "source_digest":
                tampered["cells"][valued]["source_digest"] = "0" * 64
        with pytest.raises(ValueError):
            validate_packet_semantics(tampered)


def test_relative_delta_is_a_ratio_not_a_percent() -> None:
    packet = _build()
    revenue_rev = next(item for item in packet["revisions"] if item["metric_id"] == "revenue")
    assert revenue_rev["root_value"] == "1050"
    assert revenue_rev["prior_value"] == "1050"
    assert revenue_rev["revised_value"] == "1060"
    assert revenue_rev["absolute_delta"] == "10"
    assert revenue_rev["relative_delta"].startswith("0.009523809523809523809523809523")
    assert "percentage_delta" not in revenue_rev


def test_equal_value_restatement_is_still_a_revision() -> None:
    packet = _build()
    gp = next(item for item in packet["revisions"] if item["metric_id"] == "gross_profit")
    assert gp["root_value"] == gp["prior_value"] == gp["revised_value"] == "500"
    assert gp["absolute_delta"] == "0"
    assert gp["relative_delta"] == "0"
    assert gp["root_occurrence_id"] != gp["revised_occurrence_id"]


def test_packet_byte_ceiling_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "engine.fundamental_forensics.financial_intelligence_packet.PACKET_MAX_SERIALIZED_BYTES",
        64,
    )
    with pytest.raises(ValueError, match="PACKET_MAX_SERIALIZED_BYTES"):
        _build()
    assert PACKET_MAX_SERIALIZED_BYTES == 2 * 1024 * 1024


def test_builder_digest_ignores_fixture_authoring_module() -> None:
    from engine.fundamental_forensics.synthetic_filing_package import build_synthetic_filing_package_fixture as ctor
    first = digest_builder_source(BUILDER_PATH.read_bytes())
    _ = ctor
    second = digest_builder_source(BUILDER_PATH.read_bytes())
    assert first == second
    assert "build_synthetic_filing_package_fixture" not in BUILDER_PATH.read_text(encoding="utf-8")


def test_error_strings_do_not_leak_paths() -> None:
    with pytest.raises(ValueError) as exc:
        admit_filing_package_fixture_bytes(b"")
    text = str(exc.value)
    assert str(ROOT) not in text
    assert str(LEDGER_PATH) not in text
    home = os.environ.get("HOME")
    if home:
        assert home not in text
