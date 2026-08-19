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
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from engine.government_revenue import identity_atlas as ia
from engine.government_revenue.entity_resolution import (
    load_recipient_entity_graph,
    resolve_recipient,
)
import scripts.mint_defense21_recipient_graph as mint

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")


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


def _fake_bwxt_fetch(url: str) -> bytes:
    """A fetch stub whose bodies satisfy the mint script's own content
    assertions (registrant named in the 10-K, every canonical name in the
    Ex.21 body, every UEI paired with its own recipient_name in its award
    body, every admitted UEI in the children-endpoint body) without reaching
    the network."""
    if url == mint.BWXT_10K_URL:
        return b"BWX TECHNOLOGIES, INC. is the registrant of this report."
    if url == mint.BWXT_EX21_URL:
        names = " ".join(name for _uei, _slug, name, _award_id in mint.BWXT_SUBSIDIARIES)
        return f"EXHIBIT 21.1 {names}".encode("utf-8")
    if url == mint.BWXT_CHILDREN_URL:
        rows = [{"uei": uei} for uei, _slug, _name, _award_id in mint.BWXT_SUBSIDIARIES]
        return json.dumps(rows).encode("utf-8")
    for uei, _slug, name, award_id in mint.BWXT_SUBSIDIARIES:
        if url == mint._award_url(award_id):
            return json.dumps({"recipient": {"uei": uei, "recipient_name": name.upper()}}).encode(
                "utf-8"
            )
    return f"body-for:{url}".encode("utf-8")


def test_5_defense19_rows_survive_byte_identical_in_defense21():
    base = _base_graph(graph_id="recipient-graph:reviewed:2026-08-08:defense19-v1")

    merged = mint.build_defense21_graph(base_graph=base, fetch=_fake_bwxt_fetch)
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


def test_fix4_mint_refuses_an_award_receipt_that_does_not_name_its_own_uei():
    with pytest.raises(ValueError, match="does not contain its own UEI"):
        mint._assert_award_body_names_its_uei(
            uei="WJYVCPD5HKK7", body=b'{"recipient": {"uei": "SOME0THERUEI"}}', award_id="test"
        )
    # Passes silently when the body genuinely names the UEI.
    mint._assert_award_body_names_its_uei(
        uei="WJYVCPD5HKK7", body=b'{"recipient": {"uei": "WJYVCPD5HKK7"}}', award_id="test"
    )


def test_fix4_mint_refuses_ex21_evidence_missing_an_admitted_entity():
    names = " ".join(name for _uei, _slug, name, _award_id in mint.BWXT_SUBSIDIARIES[:-1])
    with pytest.raises(ValueError, match="missing"):
        mint._assert_ex21_names_every_admitted_entity(body=names.encode("utf-8"))
    # Passes silently when every admitted name is present.
    mint._assert_ex21_names_every_admitted_entity(body=_fake_bwxt_fetch(mint.BWXT_EX21_URL))


def test_fix4_mint_refuses_a_children_receipt_missing_an_admitted_uei():
    incomplete = json.dumps([{"uei": "WJYVCPD5HKK7"}]).encode("utf-8")
    with pytest.raises(ValueError, match="missing"):
        mint._assert_children_receipt_lists_every_admitted_uei(body=incomplete)
    # Passes silently when every admitted UEI is listed.
    mint._assert_children_receipt_lists_every_admitted_uei(
        body=_fake_bwxt_fetch(mint.BWXT_CHILDREN_URL)
    )


def test_fixC_mint_refuses_a_10k_receipt_that_does_not_name_the_registrant():
    with pytest.raises(ValueError, match="registrant"):
        mint._assert_10k_names_the_registrant(body=b"This filing is about a different company.")
    # Passes silently on either the registrant name or its CIK.
    mint._assert_10k_names_the_registrant(body=b"BWX Technologies, Inc. annual report")
    mint._assert_10k_names_the_registrant(body=f"CIK {mint.BWXT_CIK}".encode("utf-8"))
    # And on the real fixture body used by the happy-path mint tests.
    mint._assert_10k_names_the_registrant(body=_fake_bwxt_fetch(mint.BWXT_10K_URL))


def test_fixC_mint_refuses_a_permuted_uei_entity_pairing():
    """The right UEI and award id, paired with the WRONG canonical_name, must
    fail -- ``_assert_award_body_names_its_uei`` alone cannot catch this,
    since the UEI genuinely is in the body; only the recipient_name<->
    canonical_name pairing check can.
    """
    uei, _slug, correct_name, award_id = mint.BWXT_SUBSIDIARIES[0]
    _other_uei, _other_slug, wrong_name, _other_award_id = mint.BWXT_SUBSIDIARIES[1]
    assert correct_name != wrong_name

    happy_body = json.dumps({"recipient": {"uei": uei, "recipient_name": correct_name.upper()}}).encode(
        "utf-8"
    )
    # Happy path: passes silently.
    mint._assert_award_body_matches_paired_entity(
        uei=uei, canonical_name=correct_name, body=happy_body, award_id=award_id
    )
    # Permuted: same UEI, same award id, but the WRONG canonical_name paired
    # against it (as if a row in BWXT_SUBSIDIARIES had its
    # (slug, canonical_name) swapped with a neighbor's).
    with pytest.raises(ValueError, match="does not match"):
        mint._assert_award_body_matches_paired_entity(
            uei=uei, canonical_name=wrong_name, body=happy_body, award_id=award_id
        )
    # A body with no recipient_name at all must also fail, not degrade silently.
    with pytest.raises(ValueError, match="carries no recipient.recipient_name"):
        mint._assert_award_body_matches_paired_entity(
            uei=uei,
            canonical_name=correct_name,
            body=json.dumps({"recipient": {"uei": uei}}).encode("utf-8"),
            award_id=award_id,
        )
    # Non-JSON body must fail loudly rather than pass silently.
    with pytest.raises(ValueError, match="not valid JSON"):
        mint._assert_award_body_matches_paired_entity(
            uei=uei, canonical_name=correct_name, body=b"not json", award_id=award_id
        )


def test_fixC_mint_exercises_every_bwxt_content_assertion_end_to_end_without_the_network():
    """Happy-path build with canned, real-shaped bodies exercises every
    content assertion FIX-4/FIX-C added -- 10-K registrant, Ex.21 completeness,
    parent-plane children completeness, per-award UEI presence, and the
    UEI<->entity pairing -- in one pass, without a re-mint against the network.
    """
    evidence_rows, _companies, entity_rows, identifier_rows, edge_rows, known_at = (
        mint.build_bwxt_rows(fetch=_fake_bwxt_fetch)
    )
    assert known_at != "PENDING"
    assert len(entity_rows) == 6  # issuer + 5 admitted subsidiaries
    assert len(identifier_rows) == 5
    assert len(edge_rows) == 6
    mint._assert_no_refused_identifiers(identifier_rows)

    # A permuted (slug, canonical_name) pairing across BWXT_SUBSIDIARIES must
    # fail the whole walk -- prove it by permuting the fetch stub's own pairing
    # for one award and re-running build_bwxt_rows.
    def _permuted_fetch(url: str) -> bytes:
        for uei, _slug, _name, award_id in mint.BWXT_SUBSIDIARIES:
            if url == mint._award_url(award_id):
                # Pair this UEI with the WRONG canonical_name -- swap in the
                # next entity's name in the tuple list.
                index = [row[3] for row in mint.BWXT_SUBSIDIARIES].index(award_id)
                wrong_name = mint.BWXT_SUBSIDIARIES[(index + 1) % len(mint.BWXT_SUBSIDIARIES)][2]
                return json.dumps(
                    {"recipient": {"uei": uei, "recipient_name": wrong_name.upper()}}
                ).encode("utf-8")
        return _fake_bwxt_fetch(url)

    with pytest.raises(ValueError, match="does not match"):
        mint.build_bwxt_rows(fetch=_permuted_fetch)

    # A wrong-registrant 10-K must also fail the whole walk.
    def _wrong_registrant_fetch(url: str) -> bytes:
        if url == mint.BWXT_10K_URL:
            return b"This is the 10-K of an entirely unrelated company."
        return _fake_bwxt_fetch(url)

    with pytest.raises(ValueError, match="registrant"):
        mint.build_bwxt_rows(fetch=_wrong_registrant_fetch)


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

    # Adjudicated 2026-08-18 (finding B6): a scope-observed, non-curated
    # identifier is NEVER named at issuer level -- discovery scope is a fuzzy
    # association, not issuer proof.  Sikorsky must not appear anywhere named,
    # under any field, curated or otherwise.
    assert lmt["unresolved_identifiers"] == []
    blob = json.dumps(lmt)
    assert "SIKORSKY" not in blob
    assert "SIKORSKY0001" not in blob
    # It still surfaces, but only as an aggregate count with no name attached.
    gap_codes = {gap["code"] for gap in lmt["gaps"]}
    assert "observed_identifiers_without_reviewed_path" in gap_codes
    observed_gap = next(
        gap for gap in lmt["gaps"] if gap["code"] == "observed_identifiers_without_reviewed_path"
    )
    assert "1" in observed_gap["text_en"]
    # Never attached to the reviewed entity's identifiers.
    reviewed_values = {ident["value"] for ident in lmt["entities"][0]["identifiers"]}
    assert "SIKORSKY0001" not in reviewed_values


# ===========================================================================
# FIX-5 — the plane clock, not the graph's own clock, gates admission
# ===========================================================================


def test_future_known_graph_degrades_every_issuer_to_not_asserted():
    """A graph minted ahead of the plane clock must fail the SAME
    future-known-graph gate the candidates plane already enforces
    (entity_resolution.load_recipient_entity_graph) -- never render
    "reviewed" just because the graph's own clock says so.
    """
    graph = _base_graph(graph_id="recipient-graph:reviewed:2026-08-08:defense19-v1")
    graph["companies"][0]["ticker"] = "TICK"
    plane_as_of = "2026-07-01T23:59:59+00:00"  # strictly before graph_known_at

    payload = ia.build_identity_atlas(
        graph=graph,
        generated_at="2026-08-19T00:00:00+00:00",
        graph_as_of=plane_as_of,
    )
    assert payload["graph_status"] != "ready"
    for row in payload["issuers"]:
        assert row["issuer_attribution"] == "not_asserted"
        assert row["entities"] == []
        assert row["legal_issuer"]["state"] == "not_asserted"


def test_graph_as_of_none_falls_back_to_the_graph_s_own_clock():
    """Without an explicit plane clock the projector still works standalone
    (e.g. a bare call, or the disk wrapper's default) -- it evaluates the
    graph at its own construction instant rather than refusing outright."""
    graph = _base_graph()
    payload = ia.build_identity_atlas(
        graph=graph, generated_at="2026-08-19T00:00:00+00:00", graph_as_of=None
    )
    assert payload["graph_status"] == "ready"
    tick = next(row for row in payload["issuers"] if row["ticker"] == "TICK")
    assert tick["issuer_attribution"] == "reviewed"


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


# ===========================================================================
# FIX-3 — artifact <-> UI contract, pinned permanently
# ===========================================================================
#
# A minimal node harness (same shape as
# tests/test_government_revenue_dossier_ui.py::_run_atlas) that renders the
# SHIPPED factory against the COMMITTED data/government_revenue/identity_atlas.json
# -- never a fixture, never a mock. If the projector's field names and the UI's
# accessors ever drift again (the exact defect FIX-2 fixed), this test catches
# it directly against the real artifact, not a hand-authored stand-in.

DOSSIER_JS_PATH = ROOT / "templates" / "government-revenue-dossiers.js"
COMMITTED_ATLAS_PATH = ROOT / "data" / "government_revenue" / "identity_atlas.json"


def _committed_atlas_node_script(body: str) -> str:
    dossier_js = DOSSIER_JS_PATH.read_text(encoding="utf-8")
    atlas = json.loads(COMMITTED_ATLAS_PATH.read_text(encoding="utf-8"))
    scaffold = """
        var window=globalThis;
        var ATLAS=__ATLAS__;
        window.fetch=function(url){return Promise.resolve({ok:true,status:200,json:function(){return Promise.resolve(ATLAS)}})};
        __DOSSIER_JS__
        function obj(x){return !!x&&typeof x==='object'&&!Array.isArray(x)}
        function arr(x){return Array.isArray(x)?x:[]}
        function esc(x){return String(x==null?'':x).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
        function text(x,fb){return x==null||x===''?(fb==null?'\\u2014':fb):String(x)}
        function n(x){if(x==null||x===''||typeof x==='boolean')return null;var v=Number(x);return Number.isFinite(v)?v:null}
        function date(x){return String(x||'\\u2014').slice(0,10)}
        function tr(en,cn){return LANG==='zh'?cn:en}
        function zhOn(){return LANG==='zh'}
        function safeUrl(x){try{var u=new URL(String(x||''),'https://example.invalid/');return u.protocol==='https:'?u.href:''}catch(e){return''}}
        function host(){var h={innerHTML:'',classes:{}};h.classList={add:function(k){h.classes[k]=true},remove:function(){for(var i=0;i<arguments.length;i++)delete h.classes[arguments[i]]}};return h}
        function mount(ticker){var h=host();var ui=window.createGovernmentRevenueIdentityAtlas({obj:obj,arr:arr,esc:esc,text:text,n:n,date:date,tr:tr,zh:zhOn,safeUrl:safeUrl,host:function(){return h}});ui.loadCompany(ticker);return{host:h,ui:ui}}
        __BODY__
    """
    return (
        textwrap.dedent(scaffold)
        .replace("__ATLAS__", json.dumps(atlas))
        .replace("__DOSSIER_JS__", dossier_js)
        .replace("__BODY__", textwrap.dedent(body))
    )


def _run_committed_atlas(tmp_path: Path, body: str) -> dict:
    path = tmp_path / "committed_atlas.js"
    path.write_text(_committed_atlas_node_script(body), encoding="utf-8")
    result = subprocess.run(["node", str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@needs_node
def test_committed_atlas_renders_the_pilots_through_the_shipped_ui_factory(tmp_path: Path):
    body = """
        var LANG='en';
        var list=['IRDM','HII','LMT','GE','BWXT','SPR'],out={},i=0,current;
        function step(){
          if(i>=list.length){process.stdout.write(JSON.stringify(out));return}
          var ticker=list[i++];current=host();
          var ui=window.createGovernmentRevenueIdentityAtlas({obj:obj,arr:arr,esc:esc,text:text,n:n,date:date,tr:tr,zh:zhOn,safeUrl:safeUrl,host:function(){return current}});
          ui.loadCompany(ticker);
          setTimeout(function(){out[ticker]=current.innerHTML;step()},20);
        }
        step();
    """
    out = _run_committed_atlas(tmp_path, body)

    irdm, bwxt = out["IRDM"], out["BWXT"]
    for html, ticker in ((irdm, "IRDM"), (bwxt, "BWXT")):
        assert "atlas-hop reviewed" in html, ticker
        assert "State unclear" not in html, ticker
        # Only GE/SPR may carry a break state; a fully reviewed pilot's chain
        # must never print an unresolved rung (FIX-B).
        assert "atlas-hop unresolved" not in html, ticker
        assert "Not asserted" not in html.split('<p class="atlas-read">')[0], (
            f"{ticker}: legal issuer hop must not misread the reviewed issuer as unresolved"
        )
        # At least one real 64-hex content_sha256 renders inside a receipt
        # expand -- pins evidenceCode() reading `content_sha256`; silently
        # reverting it to the nonexistent `.sha256` field must fail this.
        receipts = "".join(
            re.findall(r'<details class="atlas-receipt">.*?</details>', html, flags=re.S)
        )
        assert re.search(r"sha256: [0-9a-f]{64}", receipts), (
            f"{ticker}: no real 64-hex sha256 found inside a receipt expand"
        )

    ge = out["GE"]
    assert (
        "Public security: verified · Government recipient attribution: unresolved · "
        "Exact issuer attribution: not asserted"
    ) in ge
    assert "no reviewed exact recipient → legal entity → GE Aerospace path." in ge
    assert "atlas-entity" not in ge

    spr = out["SPR"]
    assert "Listing terminated" in spr
    assert "atlas-hop historic" in spr
    assert "Reviewed issuer path" not in spr

    # No pilot anywhere prints the "unclear" fallback -- pins the whole
    # artifact<->UI field-name contract in one place, permanently.
    for ticker, html in out.items():
        assert "State unclear" not in html, ticker
