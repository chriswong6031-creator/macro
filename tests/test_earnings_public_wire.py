from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

import pytest
import yaml

from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.generation import EvidencePair, write_generation
from engine.earnings_narrative.public_wire import (
    PublicWireContractError,
    build_public_wire_manifest,
    compile_public_wire_article,
    verify_public_wire_article,
    verify_public_wire_manifest,
)
from engine.earnings_narrative.context_packets import (
    CONTEXT_MANIFEST_SCHEMA,
    MAX_CONTEXT_FACTS,
    WEEKLY_INTELLIGENCE_SCHEMA,
    EarningsContextContractError,
    build_context_manifest,
    build_context_generation,
    build_context_packet,
    build_weekly_intelligence,
    canonical_json_bytes as context_json_bytes,
    select_public_facts,
    validate_context_packet,
    validate_context_manifest,
    validate_weekly_intelligence,
)
from engine.neuralweb.earnings_context_reader import read_earnings_evidence
from engine.earnings_narrative.story_store import write_story_packet_generation
from engine.earnings_transcript_intake import canonical_body_sha256
from scripts.build_earnings_public_wire import (
    DEFAULT_SOURCE_BASE,
    MAX_MANIFEST_BYTES,
    ROUTE_CATALOG_FILENAME,
    PublicWireBuildError,
    _view_article,
    build,
    build_company_alignment,
    fetch_current_publication,
    publish_public_wire,
)


def _body() -> dict:
    return {
        "schema": "mastermind.tx/v1",
        "ticker": "AAPL",
        "id": "2026Q1",
        "period": "Q1 FY2026",
        "date": "2026-01-30",
        "title": "AAPL earnings call",
        "segments": [
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
            {
                "speaker": "Research Analyst",
                "role": "analyst",
                "text": "Can you discuss customer demand and the 10% slowdown in Europe?",
            },
            {
                "speaker": "Chief Financial Officer",
                "role": "executive",
                "text": "Demand remains strong, but supply constraints could pressure margins by 200 bps.",
            },
        ],
    }


def _story_packet(tmp_path: Path) -> tuple[dict, dict, bytes, bytes]:
    body = _body()
    body_sha = canonical_body_sha256(body)
    index = {
        "schema": "mastermind.tx-index/v1",
        "generated_at": "2026-02-01T00:00:00Z",
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
        index_generated_at=index["generated_at"],
    )
    evidence = tmp_path / "evidence"
    write_generation(
        evidence,
        [EvidencePair(fact_pack=fact_pack, claim_graph=claim_graph, transcript=body)],
        coverage={
            "selection_policy": "explicit_input",
            "batch_limit": 1,
            "historical_completeness": False,
            "index_body_count": 1,
            "index_generated_at": index["generated_at"],
        },
    )
    store = tmp_path / "story-packets"
    _generation, manifest = write_story_packet_generation(store, evidence)
    manifest_raw = (store / "manifest.json").read_bytes()
    entry = manifest["packets"]["AAPL/2026Q1"]
    packet_raw = (store / entry["object_key"]).read_bytes()
    return json.loads(packet_raw), manifest, manifest_raw, packet_raw


def _article(tmp_path: Path) -> tuple[dict, dict, bytes, bytes]:
    packet, manifest, manifest_raw, packet_raw = _story_packet(tmp_path)
    entry = manifest["packets"]["AAPL/2026Q1"]
    receipt = manifest["files"][entry["object_key"]]
    article = compile_public_wire_article(
        packet,
        policy_snapshot=manifest["policy"]["snapshot"],
        generation_id=manifest["generation_id"],
        object_key=entry["object_key"],
        object_sha256=receipt["sha256"],
        object_bytes=receipt["bytes"],
    )
    return article, manifest, manifest_raw, packet_raw


def test_public_wire_compiler_only_emits_exact_approved_evidence(tmp_path: Path) -> None:
    article, manifest, manifest_raw, _packet_raw = _article(tmp_path)
    verify_public_wire_article(article)
    assert article["admission"]["status"] == "verified_exact_evidence"
    assert article["admission"]["copy_scope"] == "approved_spans_only"
    assert article["execution"]["model_calls"] == 0
    assert article["event"]["slug"] == "aapl-2026q1-call-record"
    assert article["facts"]
    visible_claims = {fact["quote"]["claim_id"] for fact in article["facts"]}
    visible_claims |= {item["claim_id"] for fact in article["facts"] for item in fact["numeric"]}
    assert visible_claims
    assert all(fact["quote"]["receipt"]["source_sha256"] == article["source"]["body_sha256"] for fact in article["facts"])
    assert all(item["receipt"]["source_sha256"] == article["source"]["body_sha256"] for fact in article["facts"] for item in fact["numeric"])

    publication = build_public_wire_manifest(
        [article],
        source_generation_id=manifest["generation_id"],
        source_manifest_sha256=sha256(manifest_raw).hexdigest(),
        source_packet_count=1,
        source_packet_manifest_schema=manifest["schema"],
    )
    verify_public_wire_manifest(publication)
    assert publication["routes"] == [{
        "article_id": article["article_id"],
        "url_path": "/stocks/earnings/aapl-2026q1-call-record.html",
        "canonical": "https://www.mastermind-x.com/stocks/earnings/aapl-2026q1-call-record.html",
        "lastmod": "2026-02-01T00:00:00Z",
    }]


def test_public_wire_rejects_tampered_or_nonempty_source_ready_copy(tmp_path: Path) -> None:
    article, _manifest, _raw, _packet_raw = _article(tmp_path)
    forged = deepcopy(article)
    forged["facts"][0]["quote"]["text"] = "Revenue reached 999 million."
    with pytest.raises(PublicWireContractError):
        verify_public_wire_article(forged)

    packet, manifest, _manifest_raw, _packet_raw = _story_packet(tmp_path / "second")
    forged_packet = deepcopy(packet)
    forged_packet["story"]["copy"]["headline"] = "A model-written headline"
    entry = manifest["packets"]["AAPL/2026Q1"]
    receipt = manifest["files"][entry["object_key"]]
    with pytest.raises(PublicWireContractError):
        compile_public_wire_article(
            forged_packet,
            policy_snapshot=manifest["policy"]["snapshot"],
            generation_id=manifest["generation_id"],
            object_key=entry["object_key"],
            object_sha256=receipt["sha256"],
            object_bytes=receipt["bytes"],
        )


def _remote(manifest: dict, manifest_raw: bytes, packet_raw: bytes) -> tuple[dict[str, bytes], str]:
    entry = manifest["packets"]["AAPL/2026Q1"]
    immutable = f"{DEFAULT_SOURCE_BASE}/earnings_story_packets/generations/{manifest['generation_id']}/manifest.json"
    return {
        f"{DEFAULT_SOURCE_BASE}/earnings_story_packets/manifest.json": manifest_raw,
        immutable: manifest_raw,
        f"{DEFAULT_SOURCE_BASE}/earnings_story_packets/{entry['object_key']}": packet_raw,
    }, f"{DEFAULT_SOURCE_BASE}/earnings_story_packets/{entry['object_key']}"


def _current_company(_params: dict) -> dict:
    return {
        "available": True,
        "generation_id": "c" * 24,
        "company": {"display_name": "Apple Inc."},
        "latest_event": {"fiscal_year": 2026, "fiscal_quarter": 1, "call_date": "2026-01-30"},
        "history": [{"fiscal_year": 2026, "fiscal_quarter": 1, "call_date": "2026-01-30"}],
    }


def test_wire_builder_verifies_immutable_generation_aligns_and_persists_only_redacted_state(tmp_path: Path) -> None:
    _article_payload, manifest, manifest_raw, packet_raw = _article(tmp_path / "source")
    remote, packet_url = _remote(manifest, manifest_raw, packet_raw)
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return remote[url]

    publication = fetch_current_publication(fetch=fetch, workers=1)
    assert publication["schema"] == "earnings.public_wire_manifest/v1"
    assert len(publication["articles"]) == 1
    assert packet_url in calls

    out_dir = tmp_path / "site" / "stocks" / "earnings"
    dossier = out_dir.parent / "AAPL.html"
    dossier.parent.mkdir(parents=True, exist_ok=True)
    dossier.write_text("<!doctype html><title>AAPL — Apple Inc. | MastermindX</title>", encoding="utf-8")
    root_sitemap = tmp_path / "site" / "sitemap.xml"
    root_sitemap.write_text("root sitemap stays untouched", encoding="utf-8")
    private_dir = tmp_path / "private-earnings"
    first = build(out_dir=out_dir, fetch=fetch, workers=1, company_reader=_current_company,
                  private_out_dir=private_dir,
                  now=datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert first.source == "remote"
    assert (out_dir / "index.html").exists()
    assert (out_dir / "aapl-2026q1-call-record.html").exists()
    assert (out_dir / "feed.xml").exists()
    assert "/stocks/earnings/aapl-2026q1-call-record.html" in (out_dir / "sitemap.xml").read_text(encoding="utf-8")
    assert root_sitemap.read_text(encoding="utf-8") == "root sitemap stays untouched"
    assert not (out_dir / "article_manifest.json").exists()
    assert not (out_dir / "publications").exists()
    public_routes = json.loads((out_dir / ROUTE_CATALOG_FILENAME).read_text(encoding="utf-8"))
    assert public_routes["schema"] == "earnings.public_wire_routes/v1"
    assert public_routes["company_generation_id"] == "c" * 24
    assert re.fullmatch(r"[0-9a-f]{64}", public_routes["renderer_version"])
    assert public_routes["routes"]["AAPL"]["company_name"] == "Apple Inc."
    event = public_routes["routes"]["AAPL"]["events"]["2026Q1"]
    assert event == {
        "href": "aapl-2026q1-call-record.html", "period": "Q1 FY2026", "date": "2026-01-30",
        "transcript_id": "2026Q1", "dossier_available": True,
    }
    assert public_routes["routes"]["AAPL"]["latest"] == event
    public_route_bytes = (out_dir / ROUTE_CATALOG_FILENAME).read_bytes()
    for private_token in (b"facts", b"receipt", b"object_key", b"source_sha256", b"/data/tx/"):
        assert private_token not in public_route_bytes
    rendered = (out_dir / "aapl-2026q1-call-record.html").read_text(encoding="utf-8")
    assert "Apple Inc." in rendered
    assert "A model-written" not in rendered
    view = _view_article(publication["articles"][0], alignment={"company_name": "Apple Inc."})
    public_quotes = [fact["quote"]["text"] for fact in view["public_facts"]]
    locked_quotes = [fact["quote"]["text"] for fact in view["locked_facts"]]
    assert public_quotes and locked_quotes
    assert all(quote in rendered for quote in public_quotes)
    assert all(quote not in rendered for quote in locked_quotes)
    assert "Member evidence layer" in rendered
    assert "/api/earnings/v1/records/aapl-2026q1-call-record" in rendered
    payload_path = private_dir / "records" / "aapl-2026q1-call-record.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "earnings.tier_payload/v1"
    assert payload["public_facts"] == 2
    assert payload["locked_facts"] == len(locked_quotes)
    assert all(quote in payload["facts_html"] for quote in locked_quotes)
    assert all(quote not in payload["facts_html"] for quote in public_quotes)
    weekly_page = out_dir / "weekly" / "2026-01-26.html"
    assert weekly_page.is_file()
    weekly_markup = weekly_page.read_text(encoding="utf-8")
    assert "The week in management language" in weekly_markup
    assert public_quotes[0] in weekly_markup
    assert all(quote not in weekly_markup for quote in locked_quotes)
    assert "/stocks/earnings/weekly/2026-01-26.html" in (out_dir / "sitemap.xml").read_text(encoding="utf-8")
    assert not (tmp_path / "site" / "premiumdata" / "earnings").exists()
    context_path = private_dir / "context" / "latest.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    assert context["schema"] == CONTEXT_MANIFEST_SCHEMA
    receipt = context["objects"]["AAPL"]
    context_packet = json.loads((context_path.parent / receipt["path"]).read_text(encoding="utf-8"))
    assert context_packet["authority"]["prophet_authority"] is False
    assert context["execution"]["model_calls"] == 0
    assert '../AAPL.html?from=earnings-wire&amp;tx=2026Q1' in rendered
    assert "utm_source=earnings_wire" in rendered

    calls.clear()
    unchanged = build(out_dir=out_dir, fetch=fetch, workers=1, company_reader=_current_company,
                      now=datetime(2026, 2, 1, 1, tzinfo=timezone.utc))
    assert unchanged.source == "unchanged"
    assert packet_url not in calls, "same verified generation must not hydrate packets again"

    calls.clear()
    forced = build(
        out_dir=out_dir, fetch=fetch, workers=1, company_reader=_current_company,
        force=True, now=datetime(2026, 2, 1, 1, 15, tzinfo=timezone.utc),
    )
    assert forced.source == "remote"
    assert packet_url in calls, "--force must deliberately bypass the generation fast path"

    stale_renderer = json.loads((out_dir / ROUTE_CATALOG_FILENAME).read_text(encoding="utf-8"))
    stale_renderer["renderer_version"] = "0" * 64
    (out_dir / ROUTE_CATALOG_FILENAME).write_text(
        json.dumps(stale_renderer, sort_keys=True, separators=(",", ":")), encoding="utf-8",
    )
    calls.clear()
    rerendered = build(out_dir=out_dir, fetch=fetch, workers=1, company_reader=_current_company,
                       now=datetime(2026, 2, 1, 1, 30, tzinfo=timezone.utc))
    assert rerendered.source == "remote"
    assert packet_url in calls, "renderer changes must invalidate the source-generation fast path"

    def newer_company(params: dict) -> dict:
        result = _current_company(params)
        result["generation_id"] = "d" * 24
        return result

    calls.clear()
    refreshed = build(out_dir=out_dir, fetch=fetch, workers=1, company_reader=newer_company,
                      now=datetime(2026, 2, 1, 2, tzinfo=timezone.utc))
    assert refreshed.source == "remote"
    assert packet_url in calls
    assert json.loads((out_dir / ROUTE_CATALOG_FILENAME).read_text(encoding="utf-8"))["company_generation_id"] == "d" * 24


def test_wire_rejects_mutable_marker_mismatch_before_packet_hydration(tmp_path: Path) -> None:
    _article_payload, manifest, manifest_raw, packet_raw = _article(tmp_path)
    remote, packet_url = _remote(manifest, manifest_raw, packet_raw)
    forged = json.loads(manifest_raw)
    forged["generated_at"] = "2026-02-02T00:00:00Z"
    remote[next(key for key in remote if "/generations/" in key)] = json.dumps(forged, sort_keys=True, separators=(",", ":")).encode()
    calls: list[str] = []
    with pytest.raises(PublicWireBuildError):
        fetch_current_publication(fetch=lambda url: calls.append(url) or remote[url], workers=1)
    assert packet_url not in calls


def test_wire_caps_and_stale_existing_fallback_fail_closed(tmp_path: Path) -> None:
    out_dir = tmp_path / "site" / "stocks" / "earnings"
    with pytest.raises(PublicWireBuildError):
        build(out_dir=out_dir, fetch=lambda _url: b"x" * (MAX_MANIFEST_BYTES + 1), workers=1)

    _article_payload, manifest, manifest_raw, packet_raw = _article(tmp_path / "source")
    remote, _packet = _remote(manifest, manifest_raw, packet_raw)
    (out_dir.parent / "AAPL.html").parent.mkdir(parents=True, exist_ok=True)
    (out_dir.parent / "AAPL.html").write_text("<title>AAPL — Apple Inc.</title>", encoding="utf-8")
    build(out_dir=out_dir, fetch=lambda url: remote[url], workers=1, company_reader=_current_company,
          now=datetime(2026, 2, 1, tzinfo=timezone.utc))
    before = (out_dir / "index.html").read_bytes()
    retained = build(out_dir=out_dir, fetch=lambda _url: (_ for _ in ()).throw(RuntimeError("offline")), workers=1,
                     now=datetime(2026, 2, 2, 12, tzinfo=timezone.utc))
    assert retained.source == "existing"
    assert (out_dir / "index.html").read_bytes() == before
    with pytest.raises(PublicWireBuildError, match="older than 48 hours"):
        build(out_dir=out_dir, fetch=lambda _url: (_ for _ in ()).throw(RuntimeError("offline")), workers=1,
              now=datetime(2026, 2, 3, 1, tzinfo=timezone.utc))


def test_company_alignment_requires_latest_event_not_only_history(tmp_path: Path) -> None:
    article, manifest, manifest_raw, _packet = _article(tmp_path)
    publication = build_public_wire_manifest(
        [article], source_generation_id=manifest["generation_id"], source_manifest_sha256=sha256(manifest_raw).hexdigest(),
        source_packet_count=1, source_packet_manifest_schema=manifest["schema"],
    )
    out_dir = tmp_path / "site" / "stocks" / "earnings"
    (out_dir.parent / "AAPL.html").parent.mkdir(parents=True, exist_ok=True)
    (out_dir.parent / "AAPL.html").write_text("<title>AAPL — Apple Inc.</title>", encoding="utf-8")
    alignment = build_company_alignment(publication, out_dir=out_dir, company_reader=lambda _params: {
        "available": True, "company": {"display_name": "Apple Inc."},
        "latest_event": {"fiscal_year": 2026, "fiscal_quarter": 2, "call_date": "2026-04-29"},
        "history": [
            {"fiscal_year": 2026, "fiscal_quarter": 2, "call_date": "2026-04-29"},
            {"fiscal_year": 2026, "fiscal_quarter": 1, "call_date": "2026-01-30"},
        ],
    })
    row = alignment[article["article_id"]]
    assert row["alignment_status"] == "historical_only"
    assert row["dossier_available"] is False


def test_publish_removes_stale_article_named_by_prior_redacted_routes(tmp_path: Path) -> None:
    article, manifest, manifest_raw, _packet = _article(tmp_path)
    publication = build_public_wire_manifest(
        [article], source_generation_id=manifest["generation_id"], source_manifest_sha256=sha256(manifest_raw).hexdigest(),
        source_packet_count=1, source_packet_manifest_schema=manifest["schema"],
    )
    out_dir = tmp_path / "site" / "stocks" / "earnings"
    (out_dir.parent / "AAPL.html").parent.mkdir(parents=True, exist_ok=True)
    (out_dir.parent / "AAPL.html").write_text("<title>AAPL — Apple Inc.</title>", encoding="utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)
    stale = out_dir / "aapl-2025q4-call-record.html"
    stale.write_text("obsolete", encoding="utf-8")
    private_dir = tmp_path / "private-earnings"
    stale_payload = private_dir / "records" / "aapl-2025q4-call-record.json"
    stale_payload.parent.mkdir(parents=True, exist_ok=True)
    stale_payload.write_text("{}", encoding="utf-8")
    prior_state = {
        "routes": {"AAPL": {"events": {"2025Q4": {"href": stale.name}}}},
    }
    publish_public_wire(publication, out_dir=out_dir, prior_state=prior_state, company_reader=_current_company,
                        private_out_dir=private_dir,
                        now=datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert not stale.exists()
    assert not stale_payload.exists()


def test_preview_prefers_management_material_evidence_over_boilerplate_or_qa(tmp_path: Path) -> None:
    article, _manifest, _raw, _packet = _article(tmp_path)
    forged = deepcopy(article)
    forged["facts"][0]["quote"]["text"] = "Operator: this replay contains forward-looking statements and safe harbor language."
    forged["facts"][0]["role"] = "analyst"
    forged["facts"][1]["quote"]["text"] = "Revenue grew 12% to 120 million and gross margin reached 45%."
    forged["facts"][1]["role"] = "executive"
    for fact in forged["facts"][2:]:
        fact["quote"]["text"] = "Operator: thank you for joining the replay and safe harbor statement."
        fact["role"] = "analyst"
    view = _view_article(forged, alignment={"company_name": "Apple Inc.", "dossier_available": False})
    assert view["preview_quote"].startswith("Revenue grew")
    assert "apple inc" in view["search_text"]


def test_exact_evidence_context_and_weekly_contracts_are_deterministic_and_context_only(tmp_path: Path) -> None:
    article, manifest, manifest_raw, _packet = _article(tmp_path)
    publication = build_public_wire_manifest(
        [article], source_generation_id=manifest["generation_id"],
        source_manifest_sha256=sha256(manifest_raw).hexdigest(), source_packet_count=1,
        source_packet_manifest_schema=manifest["schema"],
    )
    packet = build_context_packet(article)
    assert packet["schema"] == "earnings.context_packet/v1"
    assert packet["authority"] == {
        "class": "context_only", "may_add_candidate": False, "may_rank": False,
        "may_size": False, "may_gate": False, "may_escalate": False,
        "prophet_authority": False,
    }
    assert packet["execution"]["model_calls"] == 0
    assert len(packet["facts"]) <= MAX_CONTEXT_FACTS
    assert all(fact["quote"]["receipt"]["source_sha256"] == packet["source"]["source_sha256"] for fact in packet["facts"])

    context = build_context_manifest(publication)
    validate_context_manifest(context)
    assert context_json_bytes(context) == context_json_bytes(build_context_manifest(publication))
    assert context["objects"]["AAPL"]["context_id"] == packet["context_id"]

    weeks = build_weekly_intelligence(publication)
    assert len(weeks) == 1
    weekly = weeks[0]
    validate_weekly_intelligence(weekly)
    assert weekly["schema"] == WEEKLY_INTELLIGENCE_SCHEMA
    assert weekly["week_start"] == "2026-01-26"
    assert weekly["week_end"] == "2026-02-01"
    assert weekly["coverage"]["call_records"] == 1
    assert weekly["authority"]["may_rank"] is False
    assert weekly["disclosures"]["selection"] == "editorial_relevance_not_opportunity_rank"
    approved_public_claims = {
        fact["claim_id"] for fact in select_public_facts(article["facts"])
    }
    assert {
        fact["claim_id"]
        for record in weekly["notable_records"]
        for fact in record["facts"]
    } <= approved_public_claims

    with pytest.raises(EarningsContextContractError):
        validate_context_manifest({**context, "combined_rating": 99})


def test_context_packet_rejects_semantically_forged_nested_facts_even_with_rebound_id(tmp_path: Path) -> None:
    article, _manifest, _manifest_raw, _packet = _article(tmp_path)
    forged = deepcopy(build_context_packet(article))
    forged["facts"] = ["not a receipt-bound exact fact"]
    forged["categories"] = []
    forged["context_id"] = "earnctx_" + ("0" * 32)
    forged["context_id"] = "earnctx_" + sha256(context_json_bytes(forged)).hexdigest()[:32]
    with pytest.raises(EarningsContextContractError, match="exact facts invalid"):
        validate_context_packet(forged)


def test_neuralweb_exact_evidence_reader_hash_verifies_one_ticker_object(tmp_path: Path) -> None:
    article, manifest, manifest_raw, _packet = _article(tmp_path / "source")
    publication = build_public_wire_manifest(
        [article], source_generation_id=manifest["generation_id"],
        source_manifest_sha256=sha256(manifest_raw).hexdigest(), source_packet_count=1,
        source_packet_manifest_schema=manifest["schema"],
    )
    catalog, packets = build_context_generation(publication)
    private_root = tmp_path / "private-stage"
    directory = private_root / "context"
    directory.mkdir(parents=True)
    (directory / "latest.json").write_bytes(context_json_bytes(catalog))
    for ticker, packet in packets.items():
        (directory / catalog["objects"][ticker]["path"]).write_bytes(context_json_bytes(packet))

    result = read_earnings_evidence({"ticker": "aapl"}, root=private_root)
    assert result["available"] is True
    assert result["ticker"] == "AAPL"
    assert result["permissions"]["may_rank"] is False
    assert result["facts"][0]["quote"]["receipt"]["source_sha256"] == result["receipts"]["source_sha256"]

    before_ingestion = read_earnings_evidence(
        {"ticker": "AAPL", "as_of": "2026-01-31"}, root=private_root,
    )
    assert before_ingestion["available"] is False
    assert "point-in-time" in before_ingestion["note"]
    known_by_cutoff = read_earnings_evidence(
        {"ticker": "AAPL", "as_of": "2026-02-01T23:59:59Z"}, root=private_root,
    )
    assert known_by_cutoff["available"] is True

    object_path = directory / catalog["objects"]["AAPL"]["path"]
    object_path.write_bytes(object_path.read_bytes().replace(b"Revenue", b"REVENUe", 1))
    rejected = read_earnings_evidence({"ticker": "AAPL"}, root=private_root)
    assert rejected["available"] is False
    assert "integrity failure" in rejected["note"]


def test_committed_wire_is_redacted_and_uses_dedicated_sitemap_only() -> None:
    repo = Path(__file__).resolve().parents[1]
    wire = repo / "site" / "stocks" / "earnings"
    catalog = wire / ROUTE_CATALOG_FILENAME
    if not catalog.is_file():
        pytest.skip("committed public wire is not hydrated")
    assert not (repo / "data" / "earnings_public_wire").exists()
    assert not (wire / "article_manifest.json").exists()
    assert not (wire / "publications").exists()
    for candidate in wire.glob("*.json"):
        body = candidate.read_bytes()
        for private_token in (b'"facts"', b'"receipt"', b'"object_key"', b'"source_sha256"', b'"/data/tx/'):
            assert private_token not in body, candidate
    state = json.loads(catalog.read_text(encoding="utf-8"))
    assert state["schema"] == "earnings.public_wire_routes/v1"
    sitemap = (wire / "sitemap.xml").read_text(encoding="utf-8")
    assert "/stocks/earnings/index.html" in sitemap
    assert "/stocks/earnings/" not in (repo / "site" / "sitemap.xml").read_text(encoding="utf-8")
    for ticker, row in state["routes"].items():
        for tx, event in row["events"].items():
            page = wire / event["href"]
            markup = page.read_text(encoding="utf-8")
            assert f"tx={tx}" in markup
            if event["dossier_available"]:
                assert f'../{ticker}.html?from=earnings-wire&amp;tx={tx}' in markup
            else:
                assert "utm_source=earnings_wire" in markup


def test_wire_filter_hidden_state_wins_over_card_layout() -> None:
    """Filtering must hide cards visually, not just update the result count."""
    repo = Path(__file__).resolve().parents[1]
    css = (repo / "templates" / "earnings_wire" / "earnings-wire.css").read_text(encoding="utf-8")
    committed_css = (repo / "site" / "stocks" / "earnings" / "assets" / "earnings-wire.css").read_text(
        encoding="utf-8"
    )
    script = (repo / "templates" / "earnings_wire" / "earnings-wire.js").read_text(encoding="utf-8")
    assert "card.hidden=!match" in script
    assert ".ew-card[hidden]{display:none!important}" in css
    assert ".ew-card[hidden]{display:none!important}" in committed_css


def test_member_gate_never_flashes_at_a_signed_in_reader() -> None:
    """The gate must not paint while the entitlement answer is still in flight.

    2026-08-04 (operator, on a call-record page opened logged in): "for a split second
    it will show the gating container and then it will disappear". The gate ships in
    the HTML and earnings-wire.js removes it only after auth settles AND the payload
    fetch returns — up to 3s of auth wait plus a round trip, all of it painted.

    Three legs hold this up, and each one is load-bearing on its own:
      1. a synchronous <head> script that reads the Supabase session COOKIE (theme.js
         uses cookie storage, so this is answerable before first paint) and holds the
         gate back — but ONLY when a session exists, so anonymous readers and crawlers
         are untouched;
      2. a CSS rule keyed to that hold and nothing else;
      3. an unconditional release on the failure path, ahead of every early return in
         revealSignin — the signed-in-but-not-entitled reader hits the FIRST of those
         returns, so a release placed after them would hide the gate from exactly the
         reader it is meant for.
    """
    repo = Path(__file__).resolve().parents[1]
    template = (repo / "templates" / "earnings_wire" / "earnings_wire_article.html.j2").read_text(
        encoding="utf-8"
    )
    css_paths = (
        repo / "templates" / "earnings_wire" / "earnings-wire.css",
        repo / "site" / "stocks" / "earnings" / "assets" / "earnings-wire.css",
    )
    js_paths = (
        repo / "templates" / "earnings_wire" / "earnings-wire.js",
        repo / "site" / "stocks" / "earnings" / "assets" / "earnings-wire.js",
    )

    # 1 — the pre-paint hold, gated on a real session cookie and self-expiring.
    assert "sb-[^=;]*-auth-token" in template
    assert "d.setAttribute('data-earnings-member','pending')" in template
    assert "d.removeAttribute('data-earnings-member')" in template
    assert "},8000);" in template, "the boot script must expire its own hold"

    # 2 — one rule, keyed to the hold. Anything broader would be an entitlement
    #     check in CSS, and the locked excerpts are not in this document anyway.
    rule = 'html[data-earnings-member="pending"] .ewa-member-gate{display:none}'
    for path in css_paths:
        css = path.read_text(encoding="utf-8")
        assert rule in css, path
        assert css.count("data-earnings-member") == 1, path

    # 3 — release before the early returns, not after them. Comments are stripped
    #     first: the guard has to read the code, not the prose explaining it.
    for path in js_paths:
        script = path.read_text(encoding="utf-8")
        halves = script.split("function revealSignin(){", 1)
        assert len(halves) == 2, path
        body = halves[1].split("\n  }", 1)[0]
        body = "\n".join(re.sub(r"//.*$", "", line) for line in body.splitlines())
        release = body.index("removeAttribute('data-earnings-member')")
        assert release < body.index("return"), f"{path}: gate release sits behind an early return"


def test_wire_header_cta_keeps_contrast_against_estate_link_rule() -> None:
    """The estate-wide anchor color must not turn the blue header CTA text blue."""
    repo = Path(__file__).resolve().parents[1]
    rule = ".earnings-wire .public-nav-cta,.earnings-wire .public-nav-cta:hover{color:#fff}"
    template_css = (repo / "templates" / "earnings_wire" / "earnings-wire.css").read_text(encoding="utf-8")
    committed_css = (repo / "site" / "stocks" / "earnings" / "assets" / "earnings-wire.css").read_text(
        encoding="utf-8"
    )
    assert rule in template_css
    assert rule in committed_css


def test_wire_light_theme_status_text_meets_normal_text_contrast() -> None:
    """Tiny provenance labels must remain legible on both light surfaces."""
    repo = Path(__file__).resolve().parents[1]

    def luminance(hex_color: str) -> float:
        channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [
            channel / 12.92 if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def contrast(a: str, b: str) -> float:
        lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
        return (lighter + 0.05) / (darker + 0.05)

    for relative in (
        "templates/earnings_wire/earnings-wire.css",
        "site/stocks/earnings/assets/earnings-wire.css",
    ):
        css = (repo / relative).read_text(encoding="utf-8")
        override = re.search(
            r'html\[data-theme="light"\] \.earnings-wire\{([^}]+)\}',
            css,
        )
        assert override, relative
        colors = dict(re.findall(r"--([\w-]+):(#(?:[0-9a-fA-F]{6}))", override.group(1)))
        for token in ("ew-accent", "ew-hot", "ew-warm", "ew-quiet"):
            assert token in colors, (relative, token)
            assert contrast(colors[token], "#ffffff") >= 4.5, (relative, token)
            assert contrast(colors[token], "#f6f7fa") >= 4.5, (relative, token)


def test_wire_article_has_one_localized_breadcrumb_and_source_language() -> None:
    repo = Path(__file__).resolve().parents[1]
    article = (repo / "templates/earnings_wire/earnings_wire_article.html.j2").read_text(
        encoding="utf-8"
    )
    index = (repo / "templates/earnings_wire/earnings_wire_index.html.j2").read_text(
        encoding="utf-8"
    )
    facts = (repo / "templates/earnings_wire/_facts.html.j2").read_text(encoding="utf-8")
    css = (repo / "templates/earnings_wire/earnings-wire.css").read_text(encoding="utf-8")

    assert "{% block breadcrumb %}{% endblock %}" in article
    assert article.count('<nav class="ewa-crumb"') == 1
    assert 'aria-label="Breadcrumb"' in article
    assert 'aria-label="{{ t(' not in article
    assert 'aria-current="page"' in article
    assert '<blockquote lang="en">' in facts
    assert '<blockquote lang="en">' in index
    assert "overflow-x:auto" in css
    assert "justify-content:flex-start" in css


def test_public_wire_workflow_has_upstream_trigger_and_hourly_backstop() -> None:
    repo = Path(__file__).resolve().parents[1]
    workflow = (repo / ".github" / "workflows" / "earnings-public-wire.yml").read_text(encoding="utf-8")
    robots = (repo / "site" / "robots.txt").read_text(encoding="utf-8")
    assert "workflow_run:" in workflow
    assert "push:" in workflow
    assert 'workflows: ["earnings-story-packets", "company-intelligence"]' in workflow
    assert 'cron: "47 * * * *"' in workflow
    assert "python -m scripts.build_earnings_public_wire" in workflow
    assert "--private-out-dir" in workflow
    assert "python -m scripts.publish_earnings_private_store" in workflow
    assert "git add site/stocks/earnings" in workflow
    assert "site/premiumdata/earnings" not in workflow
    assert "data/earnings_public_wire" not in workflow
    assert "git add site/stocks/earnings site/sitemap.xml" not in workflow
    assert "--offline" not in workflow
    assert 'push_on_main_ok' in workflow
    assert 'push_retry_init "earnings public wire"' in workflow
    assert "while push_attempt" in workflow
    assert "push_fetch_main_for_rebase" in workflow
    assert "git reset --hard origin/main" in workflow
    assert "git clean -fd -- site/stocks/earnings" in workflow
    assert "push_staged_clean site/stocks/earnings" in workflow
    assert workflow.index("python -m scripts.publish_earnings_private_store") < workflow.index(
        "git add site/stocks/earnings"
    )
    assert workflow.index("while push_attempt") < workflow.index("python -m scripts.build_earnings_public_wire")
    assert workflow.index("git reset --hard origin/main") < workflow.index("python -m scripts.build_earnings_public_wire")
    assert "git pull --rebase" not in workflow
    assert "push_abort_rebase" not in workflow
    assert "push_do origin HEAD:main" in workflow
    assert "push_backoff" in workflow
    assert "Sitemap: https://www.mastermind-x.com/stocks/earnings/sitemap.xml" in robots


def test_public_wire_retry_budget_covers_fresh_main_regeneration_and_private_containment() -> None:
    """The 420s shared deadline starts before a ~13-minute generation.

    A ref-lock loss must buy one full rebuild from the winning main, not consume
    the default budget before the loop reaches its first push.
    """
    repo = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load(
        (repo / ".github" / "workflows" / "earnings-public-wire.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["publish"]
    publish = next(step for step in job["steps"] if step.get("name") == "regenerate current wire from latest main and publish")
    run = publish["run"]

    assert job["timeout-minutes"] == 40
    assert "PUSH_BUDGET_SECS=1980" in run
    assert "PUSH_MAX_ATTEMPTS=2" in run
    assert run.index("PUSH_BUDGET_SECS=1980") < run.index('push_retry_init "earnings public wire"')
    assert run.index("PUSH_MAX_ATTEMPTS=2") < run.index('push_retry_init "earnings public wire"')
    assert 2 * 13 * 60 < 1980 < job["timeout-minutes"] * 60
    assert run.index("git reset --hard origin/main") < run.index(
        "python -m scripts.build_earnings_public_wire"
    )
    assert run.index("python -m scripts.publish_earnings_private_store") < run.index(
        "git add site/stocks/earnings"
    )
    assert "git add site/stocks/earnings site/premiumdata/earnings" not in run
    assert "git pull --rebase" not in run
    assert "push_abort_rebase" not in run
