from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

import pytest

from engine.earnings_narrative.extract import build_evidence_pair
from engine.earnings_narrative.generation import EvidencePair, write_generation
from engine.earnings_narrative.public_wire import (
    PublicWireContractError,
    build_public_wire_manifest,
    compile_public_wire_article,
    verify_public_wire_article,
    verify_public_wire_manifest,
)
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
    first = build(out_dir=out_dir, fetch=fetch, workers=1, company_reader=_current_company,
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
    assert "Revenue grew 12% to 120 million" in rendered
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
    prior_state = {
        "routes": {"AAPL": {"events": {"2025Q4": {"href": stale.name}}}},
    }
    publish_public_wire(publication, out_dir=out_dir, prior_state=prior_state, company_reader=_current_company,
                        now=datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert not stale.exists()


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


def test_public_wire_workflow_has_upstream_trigger_and_hourly_backstop() -> None:
    repo = Path(__file__).resolve().parents[1]
    workflow = (repo / ".github" / "workflows" / "earnings-public-wire.yml").read_text(encoding="utf-8")
    robots = (repo / "site" / "robots.txt").read_text(encoding="utf-8")
    assert "workflow_run:" in workflow
    assert 'workflows: ["earnings-story-packets", "company-intelligence"]' in workflow
    assert 'cron: "47 * * * *"' in workflow
    assert "python -m scripts.build_earnings_public_wire" in workflow
    assert "git add site/stocks/earnings" in workflow
    assert "data/earnings_public_wire" not in workflow
    assert "git add site/stocks/earnings site/sitemap.xml" not in workflow
    assert "--offline" not in workflow
    assert 'push_on_main_ok' in workflow
    assert 'push_retry_init "earnings public wire"' in workflow
    assert "while push_attempt" in workflow
    assert "push_do origin HEAD:main" in workflow
    assert "push_backoff" in workflow
    assert "Sitemap: https://www.mastermind-x.com/stocks/earnings/sitemap.xml" in robots
