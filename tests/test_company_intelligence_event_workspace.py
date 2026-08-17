"""E1 flagship: AAPL FY2026 Q3 through event_workspace.v1 and the production reader."""
from __future__ import annotations

import gzip
import json
from hashlib import sha256
from pathlib import Path

import pytest

from engine.company_intelligence.contracts import (
    stable_event_id,
    validate_context,
    validate_manifest,
)
from engine.company_intelligence.event_id_adapter import (
    EventAliasIndex,
    aliases_for,
    public_wire_alias,
)
from engine.company_intelligence.event_workspace import (
    AAPL_ACCESSION,
    AAPL_CALL_DATE,
    AAPL_CIK,
    FLAGSHIP_EVENT_ID,
    LIVE_CIE_ALIAS,
    LIVE_NARRATIVE_ALIAS,
    LIVE_PUBLIC_SLUG,
    apple_registry,
    flagship_fiscal_period,
    write_workspace_generation,
)
from engine.company_intelligence.event_workspace_build import build_event_workspace
from engine.company_intelligence.identity import company_id_for_cik
from engine.company_intelligence.resolution import claim_citations_pending
from engine.company_intelligence.views import build_bundle, write_generation
from engine.neuralweb import company_intelligence_reader as reader


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "company_intelligence"
EXHIBIT = FIXTURES / "aapl_fy2026_q3_ex99_1.htm"
TRANSCRIPT = FIXTURES / "aapl_fy2026_q3.json.gz"
FILING = FIXTURES / "aapl_fy2026_q3_filing.json"
COLLECTOR = FIXTURES / "aapl_edgar_8k_collector_legacy.json"
BASE = "https://company-intelligence.example/company_intelligence"
CLOCK = "2026-08-16T18:00:00Z"


def _filing() -> dict:
    return json.loads(FILING.read_text(encoding="utf-8"))


def _transcript() -> tuple[dict, str]:
    raw = gzip.decompress(TRANSCRIPT.read_bytes())
    return json.loads(raw.decode("utf-8")), sha256(raw).hexdigest()


def _collector_rows() -> list[dict]:
    return [json.loads(COLLECTOR.read_text(encoding="utf-8"))]


def _build_flagship(*, exhibit_body: str | None = None, prior_sha: str | None = None) -> dict:
    tx, tx_sha = _transcript()
    return build_event_workspace(
        registry=apple_registry(),
        ticker="AAPL",
        asof=AAPL_CALL_DATE,
        fiscal_period=flagship_fiscal_period(),
        exhibit_body=exhibit_body if exhibit_body is not None else EXHIBIT.read_text(encoding="utf-8"),
        filing=_filing(),
        transcript=tx,
        transcript_sha256=tx_sha,
        observed_at=CLOCK,
        source_available_at="2026-07-30T16:30:00Z",
        collector_rows=_collector_rows(),
        wire_record_found=False,
        prior_source_sha256=prior_sha,
    )


def _published_workspaces(tmp_path: Path, *payloads: dict) -> dict[str, bytes]:
    out = tmp_path / "company_intelligence"
    mapping = {payload["event_id"]: payload for payload in payloads}
    generation = write_workspace_generation(out, mapping)
    generation_id = generation.name
    files = {
        f"{BASE}/event_workspaces/manifest.json": (out / "event_workspaces" / "manifest.json").read_bytes(),
        f"{BASE}/event_workspaces/generations/{generation_id}/manifest.json": (
            generation / "manifest.json"
        ).read_bytes(),
    }
    for event_id in mapping:
        files[f"{BASE}/event_workspaces/generations/{generation_id}/workspaces/{event_id}.json"] = (
            generation / "workspaces" / f"{event_id}.json"
        ).read_bytes()
    return files


def _wire_remote(monkeypatch, files: dict[str, bytes]) -> list[str]:
    calls: list[str] = []
    reader.clear_company_intelligence_cache()
    monkeypatch.setattr(reader, "_public_base_url", lambda: BASE)

    def fake_fetch(url: str, *, limit: int) -> bytes:
        calls.append(url)
        assert url in files, url
        assert len(files[url]) <= limit
        return files[url]

    monkeypatch.setattr(reader, "_fetch_bytes", fake_fetch)
    return calls


def test_minting_aapl_q3_under_aapl_yields_canonical_event_and_keeps_cie_bytes() -> None:
    registry = apple_registry()
    resolved = registry.resolve_ticker("AAPL", asof=AAPL_CALL_DATE)
    assert resolved is not None
    assert resolved.company_id == company_id_for_cik(AAPL_CIK)
    aliases = aliases_for(resolved.company_id, flagship_fiscal_period(), ("AAPL",))
    assert aliases.canonical_event_id == FLAGSHIP_EVENT_ID
    assert LIVE_CIE_ALIAS == stable_event_id("AAPL", 2026, 3)
    assert LIVE_CIE_ALIAS in aliases.company_intelligence_ids
    assert LIVE_NARRATIVE_ALIAS in aliases.earnings_narrative_keys
    assert LIVE_PUBLIC_SLUG in aliases.public_slugs
    assert public_wire_alias("AAPL", flagship_fiscal_period()) == LIVE_PUBLIC_SLUG
    index = EventAliasIndex()
    index.register(aliases)
    assert index.to_canonical(LIVE_CIE_ALIAS) == FLAGSHIP_EVENT_ID
    assert index.to_canonical(LIVE_NARRATIVE_ALIAS) == FLAGSHIP_EVENT_ID
    assert index.to_canonical(LIVE_PUBLIC_SLUG) == FLAGSHIP_EVENT_ID
    assert index.to_canonical(FLAGSHIP_EVENT_ID) == FLAGSHIP_EVENT_ID


def test_flagship_binds_the_8k_by_cik_and_accession_not_filing_date() -> None:
    payload = _build_flagship()
    filing = payload["completeness"]["filing"]["filing_key"]
    assert filing["cik"] == AAPL_CIK
    assert filing["accession"] == AAPL_ACCESSION
    assert filing["accession"] != payload["fiscal_period"]["calendar_end"]
    collector = next(source for source in payload["sources"] if source["kind"] == "edgar_collector")
    assert collector["receipt_state"] == "typed_absence"
    assert collector["typed_absence"]["reason"] == "unjoinable_filing_identity"
    assert "collector_filing_unjoinable" in payload["warnings"]
    # The live parquet row is dated 2026-04-30; joining on that date would
    # silently miss the July print.  The bound accession is independent of it.
    assert json.loads(COLLECTOR.read_text())["filing_date"] == "2026-04-30"
    assert "accession" not in json.loads(COLLECTOR.read_text())


def test_glance_facts_are_byte_replayed_spans_or_typed_absences() -> None:
    payload = _build_flagship()
    revenue = next(fact for fact in payload["facts"] if fact["fact_id"] == "fact_revenue_gaap")
    assert revenue["value"] == 109417.0
    assert revenue["basis"] == "gaap"
    assert revenue["source_span"]["receipt_state"] == "byte_replayed"
    assert "$109417" not in json.dumps(revenue["source_span"])  # table scale is millions

    claims = {claim["claim_id"]: claim for claim in payload["claims"]}
    assert "$109.4 billion in revenue, up 16%" in claims["claim_revenue_lede"]["text"]
    assert claims["claim_iphone_yoy"]["source_span"]["receipt_state"] == "byte_replayed"
    assert claims["claim_mac_yoy"]["text"] == "growing an impressive 29%"
    assert claims["claim_services_revenue"]["text"] == "$30.7 billion"
    assert "two and a half billion" in claims["claim_install_base"]["text"]
    assert "remarkably better than we thought" in claims["claim_demand_vs_supply"]["text"]
    assert claims["claim_memory_flood"]["text"] == "100-year flood"
    assert "two and a half percentage points" in claims["claim_fx_headwind"]["text"]
    for claim in claims.values():
        assert claim.get("typed_absence") is None
        assert claim["source_span"]["receipt_state"] == "byte_replayed"

    questions = next(fact for fact in payload["facts"] if fact["metric"] == "questions_count")
    assert "typed_absence" in questions
    assert questions["typed_absence"]["reason"] == "no_span_addressable_evidence"
    assert "questions_count_unstructured" in payload["warnings"]
    assert "wire_record_not_found" in payload["warnings"]


def test_claim_citations_pending_is_derived_on_v2_and_v1_still_requires_true() -> None:
    payload = _build_flagship()
    assert payload["claim_citations_pending"] is False
    # The helper the freeze names still fail-closes on an empty claim set.
    assert claim_citations_pending([]) is True

    contexts, manifest = build_bundle(
        [{
            "document_ticker": "AAPL",
            "company_name": "Apple Inc.",
            "fiscal_year": 2026,
            "fiscal_quarter": 3,
            "call_date": "2026-07-30",
            "updated_at": "2026-08-01T12:00:00Z",
            "summary": "Source-authored summary.",
        }],
        tx_index={"schema": "mastermind.tx-index/v1", "symbols": {"AAPL": ["2026Q3"]}},
        earnings_manifest={"schema": "earnings_intelligence_manifest.v3", "generated_at": "2026-08-01T12:00:00Z"},
        as_of="2026-08-02",
    )
    validate_context(contexts["AAPL"])
    validate_manifest({**manifest, "files": manifest.get("files") or {}}, allow_unmaterialized_files=True)
    assert contexts["AAPL"]["history"][0]["claim_citations_pending"] is True
    broken = json.loads(json.dumps(contexts["AAPL"]))
    broken["history"][0]["claim_citations_pending"] = payload["claim_citations_pending"]
    with pytest.raises(Exception):
        validate_context(broken)


def test_no_beat_miss_without_basis_match_and_consensus_is_unlicensed() -> None:
    payload = _build_flagship()
    delta = payload["deltas"][0]
    assert delta["basis_match"] is False
    assert "beat" not in delta and "miss" not in delta and "beat_miss" not in delta
    assert delta["consensus"]["reason"] == "missing_source"
    assert payload["authority"] == "context_only"
    assert payload["prophet_flags"] == {
        "may_rank": False,
        "may_size": False,
        "may_gate": False,
        "prophet_authority": False,
    }


def test_read_event_workspace_observes_generation_and_source_sha_correction(tmp_path, monkeypatch) -> None:
    original = _build_flagship()
    original_sha = original["_source_sha256"]
    files = _published_workspaces(tmp_path, original)
    _wire_remote(monkeypatch, files)

    first = reader.read_event_workspace({"event_id": LIVE_CIE_ALIAS})
    assert first["available"] is True
    workspace = first["workspace"]
    assert workspace["event_id"] == FLAGSHIP_EVENT_ID
    assert workspace["lifecycle"]["state"] == "complete"
    first_generation = workspace["generation_id"]
    assert first["receipt"]["generation_id"] == first_generation

    via_slug = reader.read_event_workspace({"event_id": LIVE_PUBLIC_SLUG})
    assert via_slug["workspace"]["event_id"] == FLAGSHIP_EVENT_ID
    via_narrative = reader.read_event_workspace({"event_id": LIVE_NARRATIVE_ALIAS})
    assert via_narrative["workspace"]["event_id"] == FLAGSHIP_EVENT_ID

    amended_body = EXHIBIT.read_text(encoding="utf-8") + "\n<!-- restatement -->\n"
    corrected = _build_flagship(exhibit_body=amended_body, prior_sha=original_sha)
    assert corrected["event_id"] == FLAGSHIP_EVENT_ID
    assert corrected["lifecycle"]["state"] == "corrected"
    assert corrected["_source_sha256"] != original_sha

    files = _published_workspaces(tmp_path, corrected)
    reader.clear_company_intelligence_cache()
    _wire_remote(monkeypatch, files)
    second = reader.read_event_workspace({"event_id": FLAGSHIP_EVENT_ID})
    assert second["available"] is True
    assert second["workspace"]["event_id"] == FLAGSHIP_EVENT_ID
    assert second["workspace"]["lifecycle"]["state"] == "corrected"
    assert second["workspace"]["generation_id"] != first_generation
    assert second["receipt"]["generation_id"] == second["workspace"]["generation_id"]


def test_v1_teaser_reader_is_not_the_workspace_consumer(tmp_path, monkeypatch) -> None:
    contexts, manifest = build_bundle(
        [{
            "document_ticker": "AAPL",
            "company_name": "Apple Inc.",
            "fiscal_year": 2026,
            "fiscal_quarter": 3,
            "call_date": "2026-07-30",
            "updated_at": "2026-08-01T12:00:00Z",
            "summary": "Source-authored summary.",
        }],
        tx_index={"schema": "mastermind.tx-index/v1", "symbols": {"AAPL": ["2026Q3"]}},
        earnings_manifest={"schema": "earnings_intelligence_manifest.v3", "generated_at": "2026-08-01T12:00:00Z"},
        as_of="2026-08-02",
    )
    out = tmp_path / "company_intelligence"
    generation = write_generation(out, contexts, manifest)
    generation_id = manifest["generation_id"]
    files = {
        f"{BASE}/manifest.json": (out / "manifest.json").read_bytes(),
        f"{BASE}/generations/{generation_id}/manifest.json": (generation / "manifest.json").read_bytes(),
        f"{BASE}/generations/{generation_id}/companies/AAPL.json": (generation / "companies" / "AAPL.json").read_bytes(),
    }
    _wire_remote(monkeypatch, files)
    teaser = reader.read_company_intelligence({"ticker": "AAPL"})
    assert teaser["available"] is True
    assert teaser["history"][0]["claim_citations_pending"] is True
    assert "workspace" not in teaser
    dumped = json.dumps(teaser)
    assert "event_workspace.v1" not in dumped
    assert "evt_cik0000320193_2026q3_results" not in dumped
