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


def _build_flagship(
    *, exhibit_body: str | None = None, prior_sha: str | None = None, prior_state: str | None = None,
    filing_overrides: dict | None = None,
) -> dict:
    tx, tx_sha = _transcript()
    filing = _filing()
    if filing_overrides:
        filing = {**filing, **filing_overrides}
    return build_event_workspace(
        registry=apple_registry(),
        ticker="AAPL",
        asof=AAPL_CALL_DATE,
        fiscal_period=flagship_fiscal_period(),
        exhibit_body=exhibit_body if exhibit_body is not None else EXHIBIT.read_text(encoding="utf-8"),
        filing=filing,
        transcript=tx,
        transcript_sha256=tx_sha,
        observed_at=CLOCK,
        source_available_at="2026-07-30T16:30:00Z",
        collector_rows=_collector_rows(),
        wire_record_found=False,
        prior_source_sha256=prior_sha,
        prior_lifecycle_state=prior_state,
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

    questions_count_facts = [fact for fact in payload["facts"] if fact["metric"] == "questions_count"]
    assert questions_count_facts == []
    assert "questions_count_unstructured" not in payload["warnings"]
    assert "wire_record_not_found" in payload["warnings"]
    qa = payload["qa_exchanges"]
    assert len(qa) == 7
    assert all(item["topics"] == ["unavailable"] for item in qa)
    assert sum(len(item["question_spans"]) for item in qa) == 32
    assert sum(len(item["answer_spans"]) for item in qa) == 36
    assert sum(len(item["respondents"]) for item in qa) == 26
    assert qa[0]["questioner"]["name"] == "Amit Daryanani"
    assert [row["name"] for row in qa[0]["respondents"]] == ["Kevan Parekh", "Tim Cook", "Tim Cook"]
    assert all(item["provenance"]["provider"] is None and item["provenance"]["model"] is None for item in qa)
    assert payload["prophet_flags"] == {
        "may_rank": False, "may_size": False, "may_gate": False, "prophet_authority": False,
    }


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


def test_prior_lifecycle_state_corrected_is_sticky_when_sha_unchanged() -> None:
    """A5C BLOCKER-1 (Opus red-team, 2026-08-23): sha unchanged from the
    prior build, but prior_lifecycle_state="corrected" -> the rebuild stays
    "corrected" instead of re-deriving "complete" from scratch."""
    original = _build_flagship()
    original_sha = original["_source_sha256"]
    amended_body = EXHIBIT.read_text(encoding="utf-8") + "\n<!-- restatement -->\n"
    corrected = _build_flagship(exhibit_body=amended_body, prior_sha=original_sha)
    assert corrected["lifecycle"]["state"] == "corrected"
    corrected_sha = corrected["_source_sha256"]

    # Same (already-corrected) source rebuilt again: sha UNCHANGED relative
    # to the prior generation, but prior_lifecycle_state == "corrected".
    rebuilt = _build_flagship(exhibit_body=amended_body, prior_sha=corrected_sha, prior_state="corrected")
    assert rebuilt["lifecycle"]["state"] == "corrected"
    assert rebuilt["_source_sha256"] == corrected_sha

    # Without the fix (prior_state=None, the pre-A5C default), the SAME
    # unchanged-source rebuild derives from scratch and lands on "complete"
    # — this is the regression the fix closes, pinned as a live contrast.
    unfixed_would_be = _build_flagship(exhibit_body=amended_body, prior_sha=corrected_sha, prior_state=None)
    assert unfixed_would_be["lifecycle"]["state"] == "complete"


def test_prior_lifecycle_state_only_sticks_on_corrected_not_other_states() -> None:
    """A "complete" (or any non-"corrected") prior_lifecycle_state must NOT
    trigger the sticky re-transition — only an actual prior correction is
    carried forward."""
    original = _build_flagship()
    original_sha = original["_source_sha256"]
    rebuilt = _build_flagship(prior_sha=original_sha, prior_state="complete")
    assert rebuilt["lifecycle"]["state"] == "complete"


def test_issuer_release_source_row_carries_the_bound_filing_form() -> None:
    """A5C BLOCKER-1 (1b): the bound filing's own SEC-assigned form travels
    into the published issuer_release source row (previously dropped),
    giving IMCE A5C a second durable safety signal alongside lifecycle.state."""
    payload = _build_flagship()
    release = next(source for source in payload["sources"] if source["kind"] == "issuer_release")
    assert release["form"] == "8-K"
    assert json.loads(FILING.read_text(encoding="utf-8"))["form"] == release["form"]


def test_published_form_is_the_raw_filing_value_not_the_binder_internal_default() -> None:
    """NEW-2 fix (Opus red-team round 2, 2026-08-23): falsified the round-1
    claim that "missing/blank form is unsafe" reaches the gate — five
    `or "8-K"` sites (engine/earnings_release/binding.py:266;
    event_workspace_build.py; refresh_event_workspaces.py x3) manufactured
    the literal safe value from absence, so None could never actually reach
    it. bind_release_document DOES still default an empty/missing form to
    "8-K" internally (for its own document-identity/is_amendment purposes —
    that default is left alone since nothing else in this module reads
    bound.revision.form/.is_amendment), but the PUBLISHED issuer_release
    source row now comes from the RAW filing mapping, decoupled from that
    internal default: a filing genuinely lacking a form publishes form=None,
    not the manufactured "8-K". Discovery
    (refresh_event_workspaces._select_newest_results_rows) pre-filters
    candidates to {"8-K", "8-K/A"} so this shape should be unreachable on
    the real nightly path — this test documents the producer's own
    defaulting honestly rather than asserting it away."""
    payload = _build_flagship(filing_overrides={"form": ""})
    release = next(source for source in payload["sources"] if source["kind"] == "issuer_release")
    assert release["form"] is None  # NOT "8-K" — the binder's internal default never leaks into publication


def test_published_form_reflects_a_genuine_amendment_form() -> None:
    """Sibling regression: a filing genuinely marked "8-K/A" publishes
    "8-K/A" verbatim — the raw-filing sourcing is not itself lossy, only
    non-inventive."""
    payload = _build_flagship(filing_overrides={"form": "8-K/A"})
    release = next(source for source in payload["sources"] if source["kind"] == "issuer_release")
    assert release["form"] == "8-K/A"


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


# ---------------------------------------------------------------------------
# E2-D: Selector, ticker-keyed reader, public glance projection
# ---------------------------------------------------------------------------

from engine.company_intelligence.event_workspace import (  # noqa: E402
    SelectedEvent,
    WorkspaceError,
    select_current_event_from_aliases,
)


Q2_EVENT_ID = "evt_cik0000320193_2026q2_results"
Q2_NARRATIVE_ALIAS = "AAPL/2026Q2"


def _clone_as_q2(flagship: dict) -> dict:
    """Produce a minimal valid Q2 workspace derived from the flagship."""
    import copy
    q2 = copy.deepcopy(flagship)
    q2["event_id"] = Q2_EVENT_ID
    q2["fiscal_period"] = {**q2["fiscal_period"], "quarter": 2}
    q2["aliases"] = [Q2_NARRATIVE_ALIAS]
    # Lower revenue so Q2 is clearly distinct.
    for fact in q2.get("facts") or []:
        if fact.get("metric") == "revenue":
            fact["value"] = 90000.0
    q2["generation_id"] = ""
    q2["qa_exchanges"] = []
    q2.pop("_source_sha256", None)
    q2.pop("_aliases", None)
    return q2


# ── A: Q2 + Q3 published → Q3 selected; revenue 109417 ──────────────────────


def test_select_picks_q3_when_q2_and_q3_both_published(tmp_path, monkeypatch) -> None:
    """Two events in one generation — Q3 must win; revenue must come from Q3."""
    flagship = _build_flagship()
    q2 = _clone_as_q2(flagship)
    files = _published_workspaces(tmp_path, flagship, q2)
    _wire_remote(monkeypatch, files)

    result = reader.read_current_event_workspace({"ticker": "AAPL"})
    assert result["available"] is True
    assert result["event_id"] == FLAGSHIP_EVENT_ID
    assert result["event_alias"] == LIVE_NARRATIVE_ALIAS
    workspace = result["workspace"]
    revenue = next(f for f in workspace["facts"] if f["metric"] == "revenue")
    assert revenue["value"] == 109417.0


def test_select_current_event_picks_greatest_period() -> None:
    """Unit test: alias list with Q2 and Q3 → Q3 selected."""
    aliases = {
        Q2_NARRATIVE_ALIAS: Q2_EVENT_ID,
        LIVE_NARRATIVE_ALIAS: FLAGSHIP_EVENT_ID,
    }
    selected = select_current_event_from_aliases("AAPL", aliases)
    assert isinstance(selected, SelectedEvent)
    assert selected.event_id == FLAGSHIP_EVENT_ID
    assert selected.ticker == "AAPL"
    assert selected.year == 2026
    assert selected.quarter == 3
    assert selected.alias == LIVE_NARRATIVE_ALIAS


# ── B: same-period multiple canonical owners → ambiguous ──────────────────


def test_select_raises_ambiguous_for_duplicate_period_canonical_ids() -> None:
    """A period with two distinct canonical ids must raise WorkspaceError."""
    aliases_seq = [
        (LIVE_NARRATIVE_ALIAS, FLAGSHIP_EVENT_ID),
        (LIVE_NARRATIVE_ALIAS, "evt_cik0000320193_2026q3_v2"),  # different id
    ]
    with pytest.raises(WorkspaceError, match="ambiguous"):
        select_current_event_from_aliases("AAPL", aliases_seq)


def test_select_accepts_same_period_same_canonical_id_twice() -> None:
    """Dual-class aliases both resolving to ONE id must NOT be ambiguous."""
    aliases_seq = [
        (LIVE_NARRATIVE_ALIAS, FLAGSHIP_EVENT_ID),
        (LIVE_NARRATIVE_ALIAS, FLAGSHIP_EVENT_ID),  # same id → no conflict
    ]
    selected = select_current_event_from_aliases("AAPL", aliases_seq)
    assert selected.event_id == FLAGSHIP_EVENT_ID


def test_select_ignores_non_canonical_event_ids() -> None:
    """Narrative aliases that do not resolve to evt_cik… ids are skipped."""
    aliases = {
        "AAPL/2026Q2": "not-a-canonical-id",
        LIVE_NARRATIVE_ALIAS: FLAGSHIP_EVENT_ID,
    }
    selected = select_current_event_from_aliases("AAPL", aliases)
    assert selected.event_id == FLAGSHIP_EVENT_ID
    assert selected.quarter == 3
    """No alias for the ticker → WorkspaceError containing 'does not cover'."""
    with pytest.raises(WorkspaceError, match="does not cover"):
        select_current_event_from_aliases("AAPL", {})


def test_select_ignores_other_ticker_aliases() -> None:
    """GOOG/2026Q3 must not be admitted when selecting AAPL."""
    aliases = {"GOOG/2026Q3": "evt_cik0001652044_2026q3_results"}
    with pytest.raises(WorkspaceError, match="does not cover"):
        select_current_event_from_aliases("AAPL", aliases)


def test_select_raises_workspace_error_on_invalid_ticker() -> None:
    """Invalid ticker (with ..) → WorkspaceError via safe_ticker."""
    with pytest.raises(WorkspaceError):
        select_current_event_from_aliases("AAPL..", {})


def test_select_accepts_mapping_and_sequence_forms() -> None:
    """Both Mapping[str,str] and list-of-pairs must work."""
    good_mapping = {LIVE_NARRATIVE_ALIAS: FLAGSHIP_EVENT_ID}
    good_seq = [(LIVE_NARRATIVE_ALIAS, FLAGSHIP_EVENT_ID)]
    from_map = select_current_event_from_aliases("AAPL", good_mapping)
    from_seq = select_current_event_from_aliases("AAPL", good_seq)
    assert from_map.event_id == from_seq.event_id == FLAGSHIP_EVENT_ID


# ── G: same event correction — generation changes, event_id stays ─────────


def test_read_current_event_workspace_reflects_corrected_generation(tmp_path, monkeypatch) -> None:
    original = _build_flagship()
    files_a = _published_workspaces(tmp_path, original)
    _wire_remote(monkeypatch, files_a)

    result_a = reader.read_current_event_workspace({"ticker": "AAPL"})
    assert result_a["available"] is True
    gen_a = result_a["workspace"]["generation_id"]

    original_sha = original["_source_sha256"]
    amended_body = EXHIBIT.read_text(encoding="utf-8") + "\n<!-- restatement -->\n"
    corrected = _build_flagship(exhibit_body=amended_body, prior_sha=original_sha)
    assert corrected["event_id"] == FLAGSHIP_EVENT_ID
    assert corrected["_source_sha256"] != original_sha

    files_b = _published_workspaces(tmp_path, corrected)
    reader.clear_company_intelligence_cache()
    _wire_remote(monkeypatch, files_b)

    result_b = reader.read_current_event_workspace({"ticker": "AAPL"})
    assert result_b["available"] is True
    assert result_b["event_id"] == FLAGSHIP_EVENT_ID
    assert result_b["event_alias"] == LIVE_NARRATIVE_ALIAS
    assert result_b["workspace"]["generation_id"] != gen_a
    assert result_b["workspace"]["lifecycle"]["state"] == "corrected"


# ── I: reader does not call read_company_intelligence ────────────────────────


def test_read_current_event_workspace_does_not_call_v1_reader(tmp_path, monkeypatch) -> None:
    flagship = _build_flagship()
    files = _published_workspaces(tmp_path, flagship)
    _wire_remote(monkeypatch, files)

    called: list[bool] = []
    monkeypatch.setattr(reader, "read_company_intelligence", lambda *a, **kw: called.append(True) or {})

    result = reader.read_current_event_workspace({"ticker": "AAPL"})
    assert result["available"] is True
    assert called == [], "read_current_event_workspace must not call read_company_intelligence"


def test_read_current_event_workspace_not_covered_returns_exact_note(tmp_path, monkeypatch) -> None:
    flagship = _build_flagship()
    files = _published_workspaces(tmp_path, flagship)
    _wire_remote(monkeypatch, files)

    result = reader.read_current_event_workspace({"ticker": "TSLA"})
    assert result["available"] is False
    assert result["ticker"] == "TSLA"
    assert result["note"] == "Event workspace does not cover this ticker"


# ── C-F: public glance projection unit tests ──────────────────────────────


def _build_workspace_reader_result(tmp_path: Path) -> dict:
    """Build a fully-stamped workspace reader result from the flagship."""
    flagship = _build_flagship()
    out = tmp_path / "company_intelligence"
    gen_dir = write_workspace_generation(out, {flagship["event_id"]: flagship})
    workspace = json.loads(
        (gen_dir / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_bytes()
    )
    return {
        "available": True,
        "ticker": "AAPL",
        "event_id": FLAGSHIP_EVENT_ID,
        "event_alias": LIVE_NARRATIVE_ALIAS,
        "workspace": workspace,
        "is_context_only": True,
        "display_only": True,
        "authority": "context_only",
        "untrusted_source_data": True,
        "receipt": {"generation_id": gen_dir.name},
        "note": "context only",
    }


from app.company_intelligence import _public_workspace_glance  # noqa: E402


def test_public_glance_leak_denylist_and_required_content(tmp_path) -> None:
    """(C) Projection must contain required tokens and omit forbidden ones."""
    result = _build_workspace_reader_result(tmp_path)
    glance = _public_workspace_glance(result)
    # Use ensure_ascii=False so Unicode characters (en-dash, middle-dot) are
    # not escaped and can be found by simple string membership tests.
    dumped = json.dumps(glance, sort_keys=True, ensure_ascii=False)

    # Required content
    assert FLAGSHIP_EVENT_ID in dumped
    assert result["receipt"]["generation_id"] in dumped
    assert "$109.4B" in dumped
    assert "9\u201311%" in dumped  # en-dash in range
    assert "unlicensed" in dumped
    assert "not_joined" in dumped
    assert LIVE_NARRATIVE_ALIAS in dumped  # event_alias

    # Forbidden: URLs and internal/private fields
    for forbidden in (
        "r2.dev",
        "workspace_url",
        "marker_url",
        "source_sha256",
        "text_sha256",
        "segment_sha256",
        "span_start_byte",
        "locator",
        "score_overlay",
        "prophet",
        "http://",
        "https://",
    ):
        assert forbidden not in dumped, f"forbidden token {forbidden!r} found in glance"

    # warnings object must not appear in output
    assert '"warnings"' not in dumped

    # beat / miss / bullish / v1 summary / unbounded reported claim_text must not appear
    for bad in ("beat", "miss", "bullish", '"summary"', "claim_text"):
        assert bad not in dumped, f"forbidden token {bad!r} found in glance"


def test_public_glance_revenue_formatted_correctly(tmp_path) -> None:
    """Revenue $109.4B with +16% YoY must appear in reported."""
    result = _build_workspace_reader_result(tmp_path)
    glance = _public_workspace_glance(result)

    reported = glance["reported"]
    assert len(reported) == 1
    item = reported[0]
    assert item["metric"] == "revenue"
    assert item["label"] == "Revenue"
    assert item["value"] == "$109.4B \u00b7 +16%"
    assert item["receipt_state"] == "byte_replayed"
    assert "claim_text" not in item


def test_public_glance_guidance_formatted_correctly(tmp_path) -> None:
    """Guidance 9–11% with Q4 label must appear."""
    result = _build_workspace_reader_result(tmp_path)
    glance = _public_workspace_glance(result)

    assert len(glance["guidance"]) == 1
    g = glance["guidance"][0]
    assert g["value"] == "9\u201311%"
    assert g["label"] == "Q4 revenue growth"
    assert g["receipt_state"] == "byte_replayed"


def test_public_glance_watch_items_have_closed_map_labels(tmp_path) -> None:
    """Watch items carry Supply constraint / Memory cost/flood / FX headwind."""
    result = _build_workspace_reader_result(tmp_path)
    glance = _public_workspace_glance(result)

    watch_labels = {w["label"] for w in glance["watch"]}
    assert "Supply constraint" in watch_labels
    assert "Memory cost/flood" in watch_labels
    assert "FX headwind" in watch_labels
    # claim_revenue_lede must NOT appear
    watch_ids = {w["id"] for w in glance["watch"]}
    assert "claim_revenue_lede" not in watch_ids


def test_public_glance_coverage_states(tmp_path) -> None:
    """(D+E) Market reaction must be not_joined; consensus must be unlicensed."""
    result = _build_workspace_reader_result(tmp_path)
    glance = _public_workspace_glance(result)

    by_id = {s["id"]: s for s in glance["coverage_states"]}
    assert by_id["consensus"]["state"] == "unlicensed"
    assert by_id["reaction"]["state"] == "not_joined"
    # Neither beat nor miss should appear anywhere in the output
    dumped = json.dumps(glance)
    assert "beat" not in dumped
    assert "miss" not in dumped


def test_public_glance_reaction_does_not_borrow_public_wire(tmp_path) -> None:
    """(D) Market reaction state derives from completeness.reaction, not public_wire."""
    result = _build_workspace_reader_result(tmp_path)
    # Even if the workspace had public_wire as present, reaction stays not_joined.
    workspace = result["workspace"]
    for source in workspace.get("sources") or []:
        if source.get("kind") == "public_wire":
            source["receipt_state"] = "byte_replayed"  # simulate wire present
    glance = _public_workspace_glance(result)
    by_id = {s["id"]: s for s in glance["coverage_states"]}
    assert by_id["reaction"]["state"] == "not_joined"


def test_public_glance_questions_count_from_accepted_qa_exchanges(tmp_path) -> None:
    """Accepted Q&A publishes a derived exchange count, never overlay 14."""
    result = _build_workspace_reader_result(tmp_path)
    glance = _public_workspace_glance(result)
    qs = next((s for s in glance["coverage_states"] if s["id"] == "questions_count"), None)
    assert qs is not None
    assert qs["state"] == "7 exchanges"
    dumped = json.dumps(glance)
    assert ": 14" not in dumped
    assert '"questions_count": 14' not in dumped
    assert "unavailable" not in dumped
    assert "a8ff5d03" not in dumped
    assert "source_span" not in dumped
    assert "run_id" not in dumped


def test_public_glance_questions_count_typed_absence_is_unstructured() -> None:
    """Empty Q&A with a questions_count typed absence stays unstructured, never 14."""
    glance = _public_workspace_glance({
        "available": True,
        "ticker": "DHI",
        "event_id": "evt_cik0000882184_2026q3_results",
        "workspace": {
            "completeness": {"consensus": {"status": "unlicensed"}, "reaction": {"status": "not_joined"}},
            "facts": [{
                "metric": "questions_count",
                "typed_absence": {"reason": "no_transcript", "subject": "questions_count"},
            }],
            "qa_exchanges": [],
            "lifecycle": {"state": "complete"},
            "fiscal_period": {"year": 2026, "quarter": 3},
            "aliases": ["DHI/2026Q3"],
            "claims": [],
            "guidance": [],
            "sources": [],
        },
        "receipt": {"generation_id": "0" * 24},
        "is_context_only": True,
        "display_only": True,
        "authority": "context_only",
    })
    qs = next((s for s in glance["coverage_states"] if s["id"] == "questions_count"), None)
    assert qs is not None
    assert qs["state"] == "unstructured"
    assert "14" not in json.dumps(glance)


def test_public_glance_same_event_correction_updates_value_not_id(tmp_path) -> None:
    """Same event_id, corrected lifecycle, new revenue — no second event."""
    result = _build_workspace_reader_result(tmp_path)
    glance_a = _public_workspace_glance(result)
    assert glance_a["event_id"] == FLAGSHIP_EVENT_ID
    result["workspace"]["lifecycle"]["state"] = "corrected"
    for fact in result["workspace"].get("facts") or []:
        if fact.get("metric") == "revenue":
            fact["value"] = 120000.0
    glance_b = _public_workspace_glance(result)
    assert glance_b["event_id"] == FLAGSHIP_EVENT_ID
    assert glance_b["lifecycle_state"] == "corrected"
    assert glance_b["reported"][0]["value"].startswith("$120B")
    assert glance_a["reported"][0]["value"] != glance_b["reported"][0]["value"]


def test_public_glance_source_states_omit_private_fields(tmp_path) -> None:
    """source_states carry only kind and status; no URLs, hashes, or accession."""
    result = _build_workspace_reader_result(tmp_path)
    glance = _public_workspace_glance(result)
    for s in glance["source_states"]:
        assert set(s.keys()) == {"kind", "status"}
    statuses = {s["kind"]: s["status"] for s in glance["source_states"]}
    assert statuses.get("issuer_release") == "present"
    assert statuses.get("transcript") == "present"
    assert statuses.get("public_wire") == "absent"
    assert statuses.get("edgar_collector") == "not_joined"


def test_write_workspace_generation_refuses_alias_collision_before_marker(tmp_path) -> None:
    """Two valid canonical workspaces claiming the same AAPL/YYYYQn alias fail closed.

    The collision must raise before ``event_workspaces/manifest.json`` advances.
    """
    import copy

    first = _build_flagship()
    second = copy.deepcopy(first)
    second["event_id"] = "evt_cik0000320193_2026q3_alt"
    second["qa_exchanges"] = []
    second["aliases"] = [LIVE_NARRATIVE_ALIAS]
    extra = dict(second.get("_aliases") or {})
    extra["canonical_event_id"] = second["event_id"]
    extra["company_intelligence_ids"] = []
    extra["earnings_narrative_keys"] = [LIVE_NARRATIVE_ALIAS]
    extra["public_slugs"] = []
    extra["tickers"] = ["AAPL"]
    second["_aliases"] = extra

    out = tmp_path / "company_intelligence"
    nest_manifest = out / "event_workspaces" / "manifest.json"
    assert not nest_manifest.exists()
    with pytest.raises(WorkspaceError, match="already owned"):
        write_workspace_generation(out, {
            first["event_id"]: first,
            second["event_id"]: second,
        })
    assert not nest_manifest.exists()
    generations = out / "event_workspaces" / "generations"
    assert not generations.exists() or list(generations.iterdir()) == []


def test_write_workspace_generation_same_alias_same_event_is_idempotent(tmp_path) -> None:
    """AAPL/2026Q3 in both aliases[] and _aliases is one owner, not a collision."""
    flagship = _build_flagship()
    out = tmp_path / "company_intelligence"
    generation = write_workspace_generation(out, {flagship["event_id"]: flagship})
    manifest = json.loads((out / "event_workspaces" / "manifest.json").read_text())
    assert manifest["aliases"][LIVE_NARRATIVE_ALIAS] == FLAGSHIP_EVENT_ID
    assert (generation / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").is_file()


def test_read_current_rejects_issuer_ticker_mismatch_as_verification(tmp_path, monkeypatch) -> None:
    """Manifest alias for AAPL must not succeed if the loaded issuer listings omit AAPL."""
    import copy

    flagship = copy.deepcopy(_build_flagship())
    listings = list(flagship["issuer"]["listings"])
    listings[0] = {**listings[0], "ticker": "MSFT"}
    flagship["issuer"]["listings"] = listings
    files = _published_workspaces(tmp_path, flagship)
    _wire_remote(monkeypatch, files)

    result = reader.read_current_event_workspace({"ticker": "AAPL"})
    assert result["available"] is False
    assert result["ticker"] == "AAPL"
    assert result["note"] != "Event workspace does not cover this ticker"
    assert "listings" in result["note"]


def test_read_current_rejects_fiscal_period_mismatch_as_verification(tmp_path, monkeypatch) -> None:
    """Selected AAPL/2026Q3 must not succeed if the loaded workspace is Q2."""
    import copy

    flagship = copy.deepcopy(_build_flagship())
    flagship["fiscal_period"] = {**flagship["fiscal_period"], "quarter": 2}
    files = _published_workspaces(tmp_path, flagship)
    _wire_remote(monkeypatch, files)

    result = reader.read_current_event_workspace({"ticker": "AAPL"})
    assert result["available"] is False
    assert result["note"] != "Event workspace does not cover this ticker"
    assert "fiscal period" in result["note"]


def test_read_current_rejects_alias_not_owned_by_workspace_as_verification(tmp_path, monkeypatch) -> None:
    """Manifest T/YYYYQn that is absent from the loaded workspace aliases is 503, not 404."""
    import copy

    flagship = copy.deepcopy(_build_flagship())
    flagship["aliases"] = [alias for alias in flagship["aliases"] if alias != LIVE_NARRATIVE_ALIAS]
    files = _published_workspaces(tmp_path, flagship)
    _wire_remote(monkeypatch, files)

    result = reader.read_current_event_workspace({"ticker": "AAPL"})
    assert result["available"] is False
    assert result["note"] != "Event workspace does not cover this ticker"
    assert "selected alias" in result["note"]


def test_public_glance_typed_absent_lede_omits_growth(tmp_path) -> None:
    """Revenue dollars may publish; +16% must not if the lede loses exact evidence."""
    result = _build_workspace_reader_result(tmp_path)
    for claim in result["workspace"]["claims"]:
        if claim.get("claim_id") == "claim_revenue_lede":
            claim["source_span"] = {
                "receipt_state": "typed_absence",
                "rights_profile": "rp_public_primary_v1",
            }
    glance = _public_workspace_glance(result)
    assert glance["reported"][0]["value"] == "$109.4B"
    assert "+16%" not in glance["reported"][0]["value"]
    assert "claim_text" not in glance["reported"][0]


def test_public_glance_address_only_guidance_is_omitted(tmp_path) -> None:
    result = _build_workspace_reader_result(tmp_path)
    for item in result["workspace"]["guidance"]:
        item["source_span"]["receipt_state"] = "address_only"
    glance = _public_workspace_glance(result)
    assert glance["guidance"] == []


def test_public_glance_non_public_guidance_is_omitted(tmp_path) -> None:
    result = _build_workspace_reader_result(tmp_path)
    for item in result["workspace"]["guidance"]:
        item["source_span"]["rights_profile"] = "rp_internal_v1"
    glance = _public_workspace_glance(result)
    assert glance["guidance"] == []


def test_public_glance_watch_text_is_bounded(tmp_path) -> None:
    result = _build_workspace_reader_result(tmp_path)
    for claim in result["workspace"]["claims"]:
        if claim.get("claim_id") == "claim_demand_vs_supply":
            claim["text"] = "x" * 800
    glance = _public_workspace_glance(result)
    watch = next(item for item in glance["watch"] if item["id"] == "claim_demand_vs_supply")
    assert len(watch["value"]) == 500
    assert "x" * 501 not in json.dumps(glance)


def test_public_glance_watch_list_is_capped(tmp_path) -> None:
    result = _build_workspace_reader_result(tmp_path)
    extras = []
    for index in range(6):
        extras.append({
            "claim_id": f"claim_demand_extra_{index}",
            "metric": "demand_vs_supply",
            "kind": "quote",
            "text": f"constraint {index}",
            "source_span": {
                "receipt_state": "byte_replayed",
                "rights_profile": "rp_public_primary_v1",
            },
        })
    result["workspace"]["claims"] = extras + list(result["workspace"]["claims"])
    glance = _public_workspace_glance(result)
    assert len(glance["watch"]) == 3


def test_public_glance_reported_omits_claim_text(tmp_path) -> None:
    result = _build_workspace_reader_result(tmp_path)
    glance = _public_workspace_glance(result)
    dumped = json.dumps(glance)
    assert "claim_text" not in dumped
    assert glance["reported"][0]["value"] == "$109.4B \u00b7 +16%"
