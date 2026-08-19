"""Hostile test matrix for the D2 Identity Atlas — frozen spec §5.

Every test here is fixture-driven: none asserts against live nightly-advanced
data, apart from the committed reviewed recipient graph itself (whose only
role is proving defense21-v1 is actually admissible and free of GE/refused
rows -- a static, point-in-time fact about a committed file, not a live read).
"""
from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import pytest

from engine.government_revenue import identity_atlas as ia
from engine.government_revenue.entity_resolution import (
    load_recipient_entity_graph,
    resolve_recipient,
)
import scripts.mint_defense21_recipient_graph as mint


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_SHA = "a" * 64


# ---------------------------------------------------------------------------
# Fixture graph builders
# ---------------------------------------------------------------------------


def _temporal(**values):
    row = {
        "known_at": "2026-08-01T00:00:00+00:00",
        "valid_from": "2020-01-01T00:00:00+00:00",
        "valid_to": None,
        "evidence_refs": ["evidence:primary"],
    }
    row.update(values)
    return row


def _evidence_row(evidence_id: str, sha: str = EVIDENCE_SHA, **overrides) -> dict:
    row = {
        "evidence_id": evidence_id,
        "source_ref": f"recipient-evidence:sha256:{sha}",
        "publisher": "SEC",
        "evidence_class": "official_filing",
        "record_id": "0000000000-25-000001",
        "url": "https://www.sec.gov/Archives/edgar/data/1/test.htm",
        "content_sha256": sha,
        "byte_length": 100,
        "retrieved_at": "2025-01-01T00:00:00+00:00",
        "claim_scopes": [
            "public_company", "legal_entity", "exact_identifier", "ownership", "review_action",
        ],
        "known_at": "2026-08-01T00:00:00+00:00",
        "valid_from": "2020-01-01T00:00:00+00:00",
        "valid_to": None,
    }
    row.update(overrides)
    return row


def _base_graph(*, graph_id: str = "recipient-graph:unit:2026-08-01") -> dict:
    """One reviewed issuer (TICK) with one subsidiary and one identifier."""
    return {
        "contract": "government_recipient_entity_graph.v1",
        "schema_version": "1.1.0",
        "graph_id": graph_id,
        "graph_known_at": "2026-08-01T12:00:00+00:00",
        "graph_effective_at": "2026-08-01T12:00:00+00:00",
        "evidence": [_evidence_row("evidence:primary")],
        "companies": [
            {
                "company_id": "central:TICK",
                "ticker": "TICK",
                "verification_state": "reviewed",
                **_temporal(),
            }
        ],
        "legal_entities": [
            {
                "entity_id": "legal:tick:tick-corp",
                "canonical_name": "TICK Corp",
                "verification_state": "reviewed",
                **_temporal(),
            }
        ],
        "identifiers": [
            {
                "identifier_id": "identifier:tick:uei1",
                "entity_id": "legal:tick:tick-corp",
                "namespace": "sam_uei",
                "value": "TCKA00000001",
                "verification_state": "reviewed",
                **_temporal(),
            }
        ],
        "ownership_edges": [
            {
                "edge_id": "issuer-identity:tick:tick-corp",
                "child_entity_id": "legal:tick:tick-corp",
                "parent_company_id": "central:TICK",
                "relationship": "issuer_legal_entity",
                "economic_share": 1.0,
                "verification_state": "reviewed",
                **_temporal(),
            }
        ],
        "blocks": [],
        "conflicts": [],
        "overrides": [],
    }


def _empty_graph() -> dict:
    graph = _base_graph()
    graph["companies"] = []
    graph["legal_entities"] = []
    graph["identifiers"] = []
    graph["ownership_edges"] = []
    return graph


def _dossier_award(*, ticker: str, uei: str, name: str) -> dict:
    return {
        "collection_scope_tickers": [ticker],
        "recipient": {"uei": uei, "name": name},
    }


# ===========================================================================
# 1. SPR cannot appear live
# ===========================================================================


def test_1_spr_never_appears_live():
    curated = {
        "issuers": {
            "SPR": {
                "public_security_state": "listing_terminated",
                "listing_events": [
                    {"event": "acquisition_close", "effective_at": "2025-12-08"}
                ],
            }
        }
    }
    payload = ia.build_identity_atlas(
        graph=_empty_graph(), curated=curated, generated_at="2026-08-19T00:00:00+00:00"
    )
    spr = next(row for row in payload["issuers"] if row["ticker"] == "SPR")
    assert spr["public_security"]["state"] == "listing_terminated"
    assert spr["issuer_attribution"] == "not_asserted"
    assert spr["listing_events"]


def test_1_fail_closed_curated_live_claim_for_a_ticker_absent_from_si():
    curated = {"issuers": {"SPR": {"public_security_state": "verified_live"}}}
    with pytest.raises(ValueError, match="absent from the Stock Identity snapshot"):
        ia.build_identity_atlas(
            graph=_empty_graph(),
            si_snapshot=[],
            curated=curated,
            generated_at="2026-08-19T00:00:00+00:00",
        )


def test_1_committed_atlas_spr_record_matches(tmp_path):
    """Same assertion against the real committed graph + curated file."""
    graph = json.loads((ROOT / "data/government_revenue/recipient_entity_graph.json").read_text())
    curated = json.loads((ROOT / "data/government_revenue/identity_atlas_curated.json").read_text())
    payload = ia.build_identity_atlas(
        graph=graph, curated=curated, generated_at="2026-08-19T00:00:00+00:00"
    )
    spr = next(row for row in payload["issuers"] if row["ticker"] == "SPR")
    assert spr["public_security"]["state"] == "listing_terminated"
    assert spr["issuer_attribution"] == "not_asserted"


# ===========================================================================
# 2. GE not backdated across separation
# ===========================================================================


def test_2_ge_not_asserted_with_separation_events_and_no_graph_rows():
    graph = json.loads((ROOT / "data/government_revenue/recipient_entity_graph.json").read_text())
    curated = json.loads((ROOT / "data/government_revenue/identity_atlas_curated.json").read_text())

    # No GE rows anywhere in the reviewed graph.
    assert not [c for c in graph["companies"] if c.get("ticker") == "GE"]
    assert not [e for e in graph["legal_entities"] if "ge" in e.get("entity_id", "").split(":")]

    payload = ia.build_identity_atlas(
        graph=graph, curated=curated, generated_at="2026-08-19T00:00:00+00:00"
    )
    ge = next(row for row in payload["issuers"] if row["ticker"] == "GE")
    assert ge["issuer_attribution"] == "not_asserted"
    assert ge["separation_events"], "GE must carry the curated separation boundary"
    effective_dates = {event.get("effective_at") for event in ge["separation_events"]}
    assert "2023-01-03" in effective_dates
    assert "2024-04-02" in effective_dates
    # Fixture requirement: no ownership interval for ANY GE entity is ever
    # emitted without an explicit reviewed edge -- structurally guaranteed
    # because `entities` is populated only by walking the reviewed graph.
    assert ge["entities"] == []


def test_2_ge_gap_language_is_plain_and_never_backdates():
    curated = {
        "issuers": {
            "GE": {
                "attribution_reason_en": "no reviewed exact recipient path",
                "attribution_reason_zh": "不存在已审核的精确受益人路径",
                "separation_events": [
                    {
                        "event": "spin_off",
                        "spinco": "GE HealthCare Technologies Inc.",
                        "effective_at": "2023-01-03",
                        "headline_en": "GE HealthCare spin-off completed.",
                        "headline_zh": "GE HealthCare分拆完成。",
                    },
                    {
                        "event": "spin_off",
                        "spinco": "GE Vernova Inc.",
                        "effective_at": "2024-04-02",
                        "headline_en": "GE Vernova spin-off completed.",
                        "headline_zh": "GE Vernova分拆完成。",
                    },
                ],
                "gaps": [
                    {
                        "code": "no_reviewed_exact_path",
                        "text_en": "No reviewed exact recipient → legal entity → GE Aerospace path.",
                        "text_zh": "不存在已审核的“精确受益人 → 法律实体 → GE Aerospace”路径。",
                    }
                ],
            }
        }
    }
    payload = ia.build_identity_atlas(
        graph=_empty_graph(), curated=curated, generated_at="2026-08-19T00:00:00+00:00"
    )
    ge = next(row for row in payload["issuers"] if row["ticker"] == "GE")
    assert ge["entities"] == []
    assert ge["gaps"] == [
        {
            "code": "no_reviewed_exact_path",
            "text_en": "No reviewed exact recipient → legal entity → GE Aerospace path.",
            "text_zh": "不存在已审核的“精确受益人 → 法律实体 → GE Aerospace”路径。",
        }
    ]
    assert ge["attribution_reason_en"] == "no reviewed exact recipient path"
    assert ge["attribution_reason_zh"] == "不存在已审核的精确受益人路径"
    for event in ge["separation_events"]:
        assert event["headline_en"]
        assert event["headline_zh"]


# ===========================================================================
# 3. IRDM clocks untouched — write path + byte-exact round-trip
# ===========================================================================


def test_3_projector_never_writes_anything():
    source = inspect.getsource(ia)
    for banned in ("write_text(", "open(", ".write(", "json.dump("):
        assert banned not in source, f"identity_atlas.py must never write; found {banned!r}"


def test_3_irdm_p00032_fixture_round_trips_byte_identical(tmp_path):
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True)
    graph = _base_graph()
    graph["companies"][0]["ticker"] = "IRDM"
    graph["companies"][0]["company_id"] = "central:IRDM"
    graph["ownership_edges"][0]["parent_company_id"] = "central:IRDM"
    (data_dir / "recipient_entity_graph.json").write_text(json.dumps(graph), encoding="utf-8")

    # A workspace event carrying the exact P00032 clocks named in the spec's
    # acceptance gate -- untouched by this build, and never referenced by the
    # Atlas output.
    dossiers = {
        "awards": [
            {
                "collection_scope_tickers": ["IRDM"],
                "recipient": {"uei": "IRDM00000001", "name": "IRIDIUM SATELLITE LLC"},
                "p00032_probe": {
                    "effective_at": "2026-05-12",
                    "known_at": "2026-08-12T23:50:04.442107+00:00",
                    "is_late_discovery": True,
                    "federal_action_obligation": 18416666.66,
                },
            }
        ]
    }
    dossiers_raw = json.dumps(dossiers, sort_keys=True)
    (data_dir / "dossiers.json").write_text(dossiers_raw, encoding="utf-8")

    before = (data_dir / "dossiers.json").read_bytes()
    payload = ia.build_identity_atlas_payload(root=tmp_path, generated_at="2026-08-19T00:00:00+00:00")
    after = (data_dir / "dossiers.json").read_bytes()

    assert before == after, "dossiers.json must round-trip byte-identical through an atlas build"
    assert not (data_dir / "workspace.json").exists()
    assert not (data_dir / "candidate_ledger.jsonl").exists()
    irdm = next(row for row in payload["issuers"] if row["ticker"] == "IRDM")
    # The award's P00032 clocks never entered the payload at all.
    blob = json.dumps(payload)
    assert "18416666.66" not in blob
    assert "P00032" not in blob


# ===========================================================================
# 4. HII sibling non-leak — structurally no event/award references
# ===========================================================================


def test_4_projector_signature_takes_no_workspace_or_event_input():
    params = set(inspect.signature(ia.build_identity_atlas).parameters)
    for banned in ("workspace", "events", "award_events", "candidates"):
        assert banned not in params


def test_4_atlas_payload_never_carries_a_workspace_event_or_impact_leak():
    """A synthetic HII sibling recipient must never leak a workspace event id.

    Evidence rows legitimately CITE a USAspending award URL as documentary
    proof of ownership (that is the whole point of the receipt) -- what must
    never appear is a workspace EVENT reference (``govws-*``) or the
    event-side impact field this module never reads.
    """
    graph = json.loads((ROOT / "data/government_revenue/recipient_entity_graph.json").read_text())
    curated = json.loads((ROOT / "data/government_revenue/identity_atlas_curated.json").read_text())
    dossier_awards = [
        _dossier_award(ticker="HII", uei="HII00000099", name="A HII SIBLING RECIPIENT"),
    ]
    payload = ia.build_identity_atlas(
        graph=graph,
        curated=curated,
        dossier_awards=dossier_awards,
        generated_at="2026-08-19T00:00:00+00:00",
    )
    blob = json.dumps(payload)
    assert "govws-" not in blob
    assert "listed_company_impacts" not in blob
    hii = next(row for row in payload["issuers"] if row["ticker"] == "HII")
    assert hii["issuer_attribution"] == "reviewed"


def test_4_schema_carries_no_event_or_award_reference_fields():
    schema = json.loads(
        (ROOT / "contracts/government_revenue/government_revenue_identity_atlas.v1.schema.json").read_text()
    )
    blob = json.dumps(schema)
    for banned in ("event_id", "award_key", "generated_award_id", "action_id", "listed_company_impacts"):
        assert banned not in blob, f"schema must never declare an event/award reference field: {banned}"


# ===========================================================================
# 5. Correction cannot overwrite an interval
# ===========================================================================


def test_5_defense19_rows_survive_byte_identical_in_defense21():
    base = _base_graph(graph_id="recipient-graph:reviewed:2026-08-08:defense19-v1")

    def fake_fetch(url: str) -> bytes:
        return f"body-for:{url}".encode("utf-8")

    merged = mint.build_defense21_graph(base_graph=base, fetch=fake_fetch)
    for table, id_field in mint._ROW_ID_FIELD.items():
        base_rows = {row[id_field]: row for row in base[table]}
        merged_rows = {row[id_field]: row for row in merged[table]}
        for row_id, row in base_rows.items():
            assert merged_rows[row_id] == row, f"{table} row {row_id} mutated"


def test_5_mutated_historical_row_fails_the_byte_preservation_pin():
    base = _base_graph(graph_id="recipient-graph:reviewed:2026-08-08:defense19-v1")
    mutated_base = copy.deepcopy(base)
    mutated_base["legal_entities"][0]["known_at"] = "2099-01-01T00:00:00+00:00"

    with pytest.raises(ValueError, match="mutated"):
        mint._assert_base_rows_untouched(base, mutated_base)


def test_5_committed_defense21_admits_and_preserves_defense19_shape():
    """The real published graph loads clean and is not defense19 itself."""
    graph = json.loads((ROOT / "data/government_revenue/recipient_entity_graph.json").read_text())
    loaded = load_recipient_entity_graph(graph, as_of=graph["graph_known_at"])
    assert loaded["status"] == "ready"
    assert graph["graph_id"] == "recipient-graph:reviewed:2026-08-19:defense21-v1"
    assert graph["graph_id"] != "recipient-graph:reviewed:2026-08-08:defense19-v1"


# ===========================================================================
# 6. No unreviewed grc1-*
# ===========================================================================


def test_6_refused_bwxt_identifiers_resolve_to_no_issuer():
    graph = json.loads((ROOT / "data/government_revenue/recipient_entity_graph.json").read_text())
    as_of = graph["graph_known_at"]
    loaded = load_recipient_entity_graph(graph, as_of=as_of)
    assert loaded["status"] == "ready"
    for index, refused in enumerate(("MMACD85DT5D5", "PM7HBL2KDX46", "URJ3CAC3MSH8")):
        record = {
            "source_award_key": f"award:refused-{index}",
            "recipient_name": "REFUSED RECIPIENT",
            "recipient_uei": refused,
            "effective_at": as_of,
            "known_at": as_of,
            "amount": 1.0,
        }
        resolved = resolve_recipient(record, loaded, as_of=as_of)
        assert resolved["issuer"] is None, f"{refused} must not resolve to any issuer"


def test_6_candidate_builders_do_not_import_the_atlas_module():
    import scripts.build_government_revenue_candidates as candidate_builder
    import engine.government_revenue.candidates as candidate_engine

    for module in (candidate_builder, candidate_engine):
        source = inspect.getsource(module)
        assert "identity_atlas" not in source, (
            f"{module.__name__} must never import the Atlas — candidates and the "
            "Atlas are independent read paths over the same reviewed graph"
        )


# ===========================================================================
# 7. LMT entities distinct — no name-normalization merge
# ===========================================================================


def test_7_sikorsky_named_identifier_stays_unresolved_never_auto_attaches():
    graph = _base_graph()
    graph["companies"][0]["ticker"] = "LMT"
    graph["companies"][0]["company_id"] = "central:LMT"
    graph["legal_entities"][0]["entity_id"] = "legal:lmt:lockheed-martin-corp"
    graph["legal_entities"][0]["canonical_name"] = "LOCKHEED MARTIN CORP"
    graph["identifiers"][0]["entity_id"] = "legal:lmt:lockheed-martin-corp"
    graph["ownership_edges"][0]["parent_company_id"] = "central:LMT"
    graph["ownership_edges"][0]["child_entity_id"] = "legal:lmt:lockheed-martin-corp"

    dossier_awards = [
        _dossier_award(ticker="LMT", uei="TCKA00000001", name="LOCKHEED MARTIN CORP"),
        _dossier_award(ticker="LMT", uei="SIKORSKY0001", name="SIKORSKY AIRCRAFT CORPORATION"),
    ]
    payload = ia.build_identity_atlas(
        graph=graph, dossier_awards=dossier_awards, generated_at="2026-08-19T00:00:00+00:00"
    )
    lmt = next(row for row in payload["issuers"] if row["ticker"] == "LMT")

    # Exactly one reviewed entity -- never split or merged by a matching name.
    assert len(lmt["entities"]) == 1
    assert lmt["entities"][0]["canonical_name"] == "LOCKHEED MARTIN CORP"
    assert lmt["entities"][0]["identifiers"] == [
        {
            "value": "TCKA00000001",
            "namespace": "sam_uei",
            "verification_state": "reviewed",
            "evidence": lmt["entities"][0]["identifiers"][0]["evidence"],
        }
    ]

    unresolved_values = {row["value"] for row in lmt["unresolved_identifiers"]}
    assert "SIKORSKY0001" in unresolved_values
    sikorsky_row = next(
        row for row in lmt["unresolved_identifiers"] if row["value"] == "SIKORSKY0001"
    )
    assert sikorsky_row["observed_name"] == "SIKORSKY AIRCRAFT CORPORATION"
    # Never attached to the reviewed entity's identifiers.
    reviewed_values = {ident["value"] for ident in lmt["entities"][0]["identifiers"]}
    assert "SIKORSKY0001" not in reviewed_values


# ===========================================================================
# General projector sanity — schema, content id, determinism
# ===========================================================================


def test_committed_identity_atlas_json_is_schema_valid_and_content_addressed():
    path = ROOT / "data" / "government_revenue" / "identity_atlas.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert ia.is_valid_identity_atlas_payload(payload)
    for ticker in ia.PILOT_TICKERS:
        assert any(row["ticker"] == ticker for row in payload["issuers"]), (
            f"pilot {ticker} missing from the committed Identity Atlas"
        )


def test_projector_is_deterministic_given_identical_inputs():
    graph = _base_graph()
    curated = {"issuers": {}}
    payload_a = ia.build_identity_atlas(
        graph=graph, curated=curated, generated_at="2026-08-19T00:00:00+00:00"
    )
    payload_b = ia.build_identity_atlas(
        graph=graph, curated=curated, generated_at="2026-08-19T00:00:00+00:00"
    )
    assert payload_a == payload_b
    assert payload_a["content_id"] == payload_b["content_id"]
