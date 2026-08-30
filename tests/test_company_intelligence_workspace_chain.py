"""IMCE A5C: the manifest chain + the ONE shared disposition-aware reader.

Covers frozen spec A (v2 manifest chain schema), D (shared reader
capabilities: three-way disposition, verified predecessor walk, per-event
ordered source revisions with consecutive-carry dedupe), and the D3
retirement of the duplicate GET implementation in
scripts/build_cycle_pattern_imce_prospective.py.

No network: every fetch in this file is served by an in-process stub keyed
by exact URL, monkeypatched onto ``reader._fetch_bytes`` — the SAME
hardened fetch helper the model-facing reader functions use (MAJOR-7: there
is only ONE fetch implementation in company_intelligence_reader.py; the
producer-facing primitives this file exercises route through it via
``_fetch_bytes``'s ``allow_404`` parameter, exactly like
tests/test_company_intelligence_neural_reader.py's own
``monkeypatch.setattr(reader, "_fetch_bytes", ...)`` pattern for the
model-facing path).
"""
from __future__ import annotations

from hashlib import sha256
import json as jsonlib
from pathlib import Path

import pytest

from engine.company_intelligence.contracts import canonical_json_bytes
from engine.company_intelligence.event_workspace import (
    MANIFEST_SCHEMA_V1,
    MANIFEST_SCHEMA_V2,
    validate_workspace_manifest,
    write_workspace_generation,
)
from engine.neuralweb import company_intelligence_reader as reader
from engine.prophet_lab.intelligence_vector import (
    IntelligenceVectorContractError,
    build_earnings_intelligence_vector,
)
from engine.us_candidate_episode import episode_id as b1_episode_id
from lib.dataos.identity import IssuerMaster

BASE = "https://company-intelligence-chain.example/company_intelligence"
EVENT_ID = "evt_cik0000320193_2026q3_results"
_MINTED_WORKSPACE_BYTES: dict[tuple[str, str], bytes] = {}


def _raw_workspace(
    *,
    source_available_at: str,
    observed_at: str | None = None,
    source_sha256: str = "d" * 64,
    accession: str = "0000000000-26-000001",
    form: str = "8-K",
    state: str = "complete",
    event_id: str = EVENT_ID,
    fact_value: int = 100,
    include_issuer_release: bool = True,
) -> dict:
    """A minimal event_workspace.v1 body — only the keys this test's own
    machinery (validate_event_workspace + the chain-walk itself) reads or
    checks are populated meaningfully; everything else is a closed-set
    placeholder (validate_event_workspace does not inspect issuer/
    fiscal_period/completeness substructure at all)."""
    return {
        "schema": "event_workspace.v1",
        "event_id": event_id,
        "aliases": [],
        "issuer": {"company_id": "cik:0000320193", "display_name": "Test Co", "listings": []},
        "fiscal_period": {"year": 2026, "quarter": 3, "calendar_end": "2026-06-27"},
        "lifecycle": {"state": state, "observed_at": observed_at or source_available_at,
                      "source_available_at": source_available_at},
        "completeness": {},
        "facts": [{
            "schema": "event_fact.v1", "metric": "revenue", "value": fact_value,
            "unit": "USD", "period": "2026Q3", "basis": "reported",
            "source_span": {"document_id": "doc:1", "text": "never project source spans"},
        }],
        "deltas": [],
        "guidance": [],
        "claims": [],
        "sources": ([{
            "kind": "issuer_release", "document_id": "doc:1",
            "filing_key": {"cik": "0000320193", "accession": accession},
            "source_sha256": source_sha256, "form": form, "url": None,
            "receipt_state": "byte_replayed",
        }] if include_issuer_release else [{
            "kind": "transcript", "document_id": "doc:body:1",
            "source_sha256": source_sha256, "receipt_state": "byte_replayed",
            "body": "body-only revision that must never enter D5",
        }]),
        "warnings": [],
        "generation_id": "",
        "generated_at": source_available_at,
        "authority": "context_only",
        "prophet_flags": {"may_rank": False, "may_size": False, "may_gate": False, "prophet_authority": False},
        "claim_citations_pending": False,
        "qa_exchanges": [],
    }


def _mint(
    tmp_path: Path,
    workspaces: dict[str, dict],
    *,
    generated_at: str,
    previous_generation_id: str | None = None,
    previous_manifest_sha256: str | None = None,
) -> tuple[str, dict]:
    """Mint one real, contract-valid generation via the real writer; return
    (generation_id, manifest_dict)."""
    out = tmp_path / "company_intelligence"
    generation_dir = write_workspace_generation(
        out, workspaces, generated_at=generated_at,
        previous_generation_id=previous_generation_id,
        previous_manifest_sha256=previous_manifest_sha256,
    )
    manifest = jsonlib.loads((generation_dir / "manifest.json").read_text(encoding="utf-8"))
    for event_id in workspaces:
        _MINTED_WORKSPACE_BYTES[(generation_dir.name, event_id)] = (
            generation_dir / "workspaces" / f"{event_id}.json"
        ).read_bytes()
    return generation_dir.name, manifest


def _server(objects: dict[str, dict], *, marker_generation_id: str | None, fetch_calls: list[str] | None = None):
    """objects: generation_id -> {"manifest": dict, "workspaces": {event_id: dict}}.

    Returns a stand-in for ``reader._fetch_bytes(url, *, limit, allow_404=False)``
    — the ONE shared fetch helper (MAJOR-7) — resolving canonical JSON bytes
    for each known object, or the ``allow_404``/raise contract on a miss.
    *fetch_calls*, when supplied, records every URL fetched (MAJOR-8(a)
    single-fetch-per-hop verification).
    """

    def fake_fetch_bytes(url: str, *, limit: int, allow_404: bool = False) -> bytes | None:
        if fetch_calls is not None:
            fetch_calls.append(url)
        body: bytes | None = None
        if url == f"{BASE}/event_workspaces/manifest.json":
            if marker_generation_id is not None:
                body = canonical_json_bytes(objects[marker_generation_id]["manifest"])
        else:
            for generation_id, bundle in objects.items():
                if url == f"{BASE}/event_workspaces/generations/{generation_id}/manifest.json":
                    body = canonical_json_bytes(bundle["manifest"])
                    break
                for event_id, ws in bundle["workspaces"].items():
                    if url == f"{BASE}/event_workspaces/generations/{generation_id}/workspaces/{event_id}.json":
                        body = (
                            canonical_json_bytes(ws)
                            if bundle.get("serve_workspace_overrides") is True
                            else _MINTED_WORKSPACE_BYTES.get(
                                (generation_id, event_id), canonical_json_bytes(ws),
                            )
                        )
                        break
                if body is not None:
                    break
        if body is None:
            if allow_404:
                return None
            raise reader.CompanyIntelligenceReadError(f"404: {url}")
        return body

    return fake_fetch_bytes


# ---------------------------------------------------------------------------
# A: manifest v2 chain schema
# ---------------------------------------------------------------------------

def test_v2_manifest_carries_both_chain_keys_and_v1_stays_valid_without_them(tmp_path: Path) -> None:
    ws = _raw_workspace(source_available_at="2026-07-30T16:30:00Z")
    gen_id, manifest = _mint(tmp_path, {EVENT_ID: ws}, generated_at="2026-07-30T16:30:00Z")
    assert manifest["schema"] == MANIFEST_SCHEMA_V2
    assert manifest["previous_generation_id"] is None
    assert manifest["previous_manifest_sha256"] is None
    validate_workspace_manifest(manifest)  # does not raise

    # A v1 manifest (no chain keys at all) stays independently valid — the
    # chain root/backward-compatible generation (A2).
    v1_manifest = {k: v for k, v in manifest.items() if k not in ("previous_generation_id", "previous_manifest_sha256")}
    v1_manifest["schema"] = MANIFEST_SCHEMA_V1
    validate_workspace_manifest(v1_manifest)  # does not raise


def test_second_generation_folds_previous_generation_id_into_identity(tmp_path: Path) -> None:
    """A4: identical content atop a DIFFERENT predecessor must mint a
    DISTINCT generation_id (never collide with the content-only hash)."""
    ws = _raw_workspace(source_available_at="2026-07-30T16:30:00Z")
    gen_a, _ = _mint(tmp_path, {EVENT_ID: ws}, generated_at="2026-07-30T16:30:00Z", previous_generation_id=None)
    gen_b, _ = _mint(
        tmp_path, {EVENT_ID: ws}, generated_at="2026-07-30T16:30:00Z",
        previous_generation_id="a" * 24, previous_manifest_sha256="b" * 64,
    )
    assert gen_a != gen_b


def test_semantic_noop_short_circuits_atop_the_same_predecessor(tmp_path: Path) -> None:
    """A4: unchanged content atop the SAME predecessor reproduces the exact
    same generation_id — the no-op preservation the chain fold must not
    break."""
    ws = _raw_workspace(source_available_at="2026-07-30T16:30:00Z")
    gen_1, _ = _mint(
        tmp_path, {EVENT_ID: ws}, generated_at="2026-07-30T16:30:00Z",
        previous_generation_id="a" * 24, previous_manifest_sha256="b" * 64,
    )
    gen_2, _ = _mint(
        tmp_path, {EVENT_ID: ws}, generated_at="2026-07-30T16:30:00Z",
        previous_generation_id="a" * 24, previous_manifest_sha256="b" * 64,
    )
    assert gen_1 == gen_2


# ---------------------------------------------------------------------------
# D2: chain walk — v1 root, ordering, dedupe, integrity failures
# ---------------------------------------------------------------------------

def test_v1_root_terminates_the_walk_and_is_readable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = _raw_workspace(source_available_at="2026-01-30T16:30:00Z", source_sha256="a" * 64)
    gen_id, manifest = _mint(tmp_path, {EVENT_ID: ws}, generated_at="2026-01-30T16:30:00Z")
    v1_manifest = dict(manifest)
    v1_manifest["schema"] = MANIFEST_SCHEMA_V1
    del v1_manifest["previous_generation_id"]
    del v1_manifest["previous_manifest_sha256"]

    objects = {gen_id: {"manifest": v1_manifest, "workspaces": {EVENT_ID: ws | {"generation_id": gen_id}}}}
    monkeypatch.setattr(reader, "_fetch_bytes", _server(objects, marker_generation_id=gen_id))

    revisions = reader.read_event_source_revisions(EVENT_ID, base_url=BASE)
    assert len(revisions) == 1
    assert revisions[0]["generation_id"] == gen_id
    assert revisions[0]["source_available_at"] == "2026-01-30T16:30:00Z"


def test_chain_walk_returns_oldest_to_newest_across_v2_generations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws1 = _raw_workspace(source_available_at="2026-01-30T16:30:00Z", source_sha256="a" * 64)
    ws2 = _raw_workspace(source_available_at="2026-01-31T09:00:00Z", source_sha256="b" * 64, form="8-K/A")

    gen1, man1 = _mint(tmp_path, {EVENT_ID: ws1}, generated_at="2026-01-30T16:30:00Z")
    gen1_sha = sha256(canonical_json_bytes(man1)).hexdigest()
    gen2, man2 = _mint(
        tmp_path, {EVENT_ID: ws2}, generated_at="2026-01-31T09:00:00Z",
        previous_generation_id=gen1, previous_manifest_sha256=gen1_sha,
    )

    objects = {
        gen1: {"manifest": man1, "workspaces": {EVENT_ID: ws1 | {"generation_id": gen1}}},
        gen2: {"manifest": man2, "workspaces": {EVENT_ID: ws2 | {"generation_id": gen2}}},
    }
    fetch_calls: list[str] = []
    monkeypatch.setattr(reader, "_fetch_bytes", _server(objects, marker_generation_id=gen2, fetch_calls=fetch_calls))

    revisions = reader.read_event_source_revisions(EVENT_ID, base_url=BASE)
    assert [r["generation_id"] for r in revisions] == [gen1, gen2]
    # MAJOR-8(a): the 2-generation chain costs exactly 2 manifest GETs (one
    # per generation), never 4 (no re-fetch of a predecessor already
    # fetched+verified as the next hop's own "current" manifest).
    manifest_fetches = [url for url in fetch_calls if url.endswith("/manifest.json") and "/generations/" in url]
    assert len(manifest_fetches) == 2
    assert [r["source_sha256"] for r in revisions] == ["a" * 64, "b" * 64]
    assert revisions[0]["source_available_at"] < revisions[1]["source_available_at"]


def test_carried_forward_generations_create_no_phantom_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Chain/carry interplay (WORLD STATE): consecutive generations carrying
    a BYTE-IDENTICAL workspace for this event (a carry-forward hop) must
    dedupe to ONE revision, never two."""
    ws = _raw_workspace(source_available_at="2026-01-30T16:30:00Z", source_sha256="a" * 64)
    ws3 = _raw_workspace(source_available_at="2026-04-30T16:30:00Z", source_sha256="c" * 64)

    gen1, man1 = _mint(tmp_path, {EVENT_ID: ws}, generated_at="2026-01-30T16:30:00Z")
    gen1_sha = sha256(canonical_json_bytes(man1)).hexdigest()
    # gen2 carries the SAME event body forward unchanged (byte-identical),
    # alongside an unrelated second event so the nest content genuinely
    # differs and gen2 != gen1.
    other = _raw_workspace(source_available_at="2026-02-01T00:00:00Z", event_id="evt_cik0000000001_2026q1_results")
    gen2, man2 = _mint(
        tmp_path, {EVENT_ID: dict(ws, generation_id=gen1), "evt_cik0000000001_2026q1_results": other},
        generated_at="2026-02-01T00:00:00Z", previous_generation_id=gen1, previous_manifest_sha256=gen1_sha,
    )
    gen2_sha = sha256(canonical_json_bytes(man2)).hexdigest()
    gen3, man3 = _mint(
        tmp_path, {EVENT_ID: ws3, "evt_cik0000000001_2026q1_results": other},
        generated_at="2026-04-30T16:30:00Z", previous_generation_id=gen2, previous_manifest_sha256=gen2_sha,
    )

    objects = {
        gen1: {"manifest": man1, "workspaces": {EVENT_ID: ws | {"generation_id": gen1}}},
        gen2: {"manifest": man2, "workspaces": {
            EVENT_ID: ws | {"generation_id": gen1},
            "evt_cik0000000001_2026q1_results": other | {"generation_id": gen2},
        }},
        gen3: {"manifest": man3, "workspaces": {
            EVENT_ID: ws3 | {"generation_id": gen3},
            "evt_cik0000000001_2026q1_results": other | {"generation_id": gen2},
        }},
    }
    monkeypatch.setattr(reader, "_fetch_bytes", _server(objects, marker_generation_id=gen3))

    revisions = reader.read_event_source_revisions(EVENT_ID, base_url=BASE)
    # gen1 and gen2 both carry source_sha256="a"*64 for this event — deduped
    # to ONE revision; gen3 introduces "c"*64 — a genuine second revision.
    assert [r["source_sha256"] for r in revisions] == ["a" * 64, "c" * 64]
    assert len(revisions) == 2


def test_read_all_event_source_revisions_matches_per_event_walks_at_one_fetch_cost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production incident addendum (2026-08-23): read_all_event_source_
    revisions must extract EXACTLY the same per-event revisions as separate
    per-event read_event_source_revisions calls would — while costing ONE
    manifest fetch per generation TOTAL, never per event. A live measurement
    against the post-incident ~170-generation backfilled chain found a
    single-event walk cost 153 SECONDS; the A5B nightly builder was paying
    that once per candidate (~8), which is the O(events x hops) cost this
    fix collapses to O(hops)."""
    event_id_2 = "evt_cik0000000002_2026q2_results"
    ws1_a = _raw_workspace(source_available_at="2026-01-30T16:30:00Z", source_sha256="a" * 64, event_id=EVENT_ID)
    ws2_a = _raw_workspace(source_available_at="2026-02-01T00:00:00Z", source_sha256="e" * 64, event_id=event_id_2)
    ws1_b = _raw_workspace(source_available_at="2026-01-30T16:30:00Z", source_sha256="a" * 64, event_id=EVENT_ID)  # unchanged carry
    ws2_b = _raw_workspace(
        source_available_at="2026-02-02T00:00:00Z", source_sha256="f" * 64, event_id=event_id_2, form="8-K/A",
    )

    gen1, man1 = _mint(tmp_path, {EVENT_ID: ws1_a, event_id_2: ws2_a}, generated_at="2026-02-01T00:00:00Z")
    gen1_sha = sha256(canonical_json_bytes(man1)).hexdigest()
    gen2, man2 = _mint(
        tmp_path, {EVENT_ID: ws1_b, event_id_2: ws2_b}, generated_at="2026-02-02T00:00:00Z",
        previous_generation_id=gen1, previous_manifest_sha256=gen1_sha,
    )

    objects = {
        gen1: {"manifest": man1, "workspaces": {
            EVENT_ID: ws1_a | {"generation_id": gen1}, event_id_2: ws2_a | {"generation_id": gen1},
        }},
        gen2: {"manifest": man2, "workspaces": {
            EVENT_ID: ws1_b | {"generation_id": gen2}, event_id_2: ws2_b | {"generation_id": gen2},
        }},
    }

    def _manifest_fetch_count(calls: list[str]) -> int:
        return len([u for u in calls if u.endswith("/manifest.json") and "/generations/" in u])

    # Per-event walks (the OLD pattern) — each pays its OWN 2-manifest-fetch
    # cost for this 2-generation chain (MAJOR-8(a)), 4 total across both.
    per_event_calls_1: list[str] = []
    monkeypatch.setattr(reader, "_fetch_bytes", _server(objects, marker_generation_id=gen2, fetch_calls=per_event_calls_1))
    per_event_1 = reader.read_event_source_revisions(EVENT_ID, base_url=BASE)
    per_event_calls_2: list[str] = []
    monkeypatch.setattr(reader, "_fetch_bytes", _server(objects, marker_generation_id=gen2, fetch_calls=per_event_calls_2))
    per_event_2 = reader.read_event_source_revisions(event_id_2, base_url=BASE)
    assert _manifest_fetch_count(per_event_calls_1) == 2
    assert _manifest_fetch_count(per_event_calls_2) == 2

    # ONE shared walk (the fix) — must extract the SAME per-event results,
    # at HALF the total manifest-fetch cost (2, not 4).
    shared_calls: list[str] = []
    monkeypatch.setattr(reader, "_fetch_bytes", _server(objects, marker_generation_id=gen2, fetch_calls=shared_calls))
    shared = reader.read_all_event_source_revisions((EVENT_ID, event_id_2), base_url=BASE)

    assert shared[EVENT_ID] == per_event_1
    assert shared[event_id_2] == per_event_2
    assert _manifest_fetch_count(shared_calls) == 2  # NOT 4


def test_read_all_event_source_revisions_includes_every_requested_id_even_with_none_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An event_id with no revisions anywhere in the walked chain still
    appears in the result, mapped to an empty list — a caller must always
    be able to index the result by every id it asked for."""
    ws = _raw_workspace(source_available_at="2026-01-30T16:30:00Z", source_sha256="a" * 64, event_id=EVENT_ID)
    gen1, man1 = _mint(tmp_path, {EVENT_ID: ws}, generated_at="2026-01-30T16:30:00Z")
    objects = {gen1: {"manifest": man1, "workspaces": {EVENT_ID: ws | {"generation_id": gen1}}}}
    monkeypatch.setattr(reader, "_fetch_bytes", _server(objects, marker_generation_id=gen1))

    never_represented = "evt_cik0000000009_2029q1_results"
    result = reader.read_all_event_source_revisions((EVENT_ID, never_represented), base_url=BASE)
    assert result[EVENT_ID][0]["source_sha256"] == "a" * 64
    assert result[never_represented] == []


def test_chain_link_to_a_nonexistent_generation_is_a_typed_hard_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = _raw_workspace(source_available_at="2026-01-30T16:30:00Z")
    gen1, man1 = _mint(
        tmp_path, {EVENT_ID: ws}, generated_at="2026-01-30T16:30:00Z",
        previous_generation_id="0" * 24, previous_manifest_sha256="f" * 64,
    )
    objects = {gen1: {"manifest": man1, "workspaces": {EVENT_ID: ws | {"generation_id": gen1}}}}
    monkeypatch.setattr(reader, "_fetch_bytes", _server(objects, marker_generation_id=gen1))

    with pytest.raises(reader.WorkspaceChainIntegrityError):
        reader.read_event_source_revisions(EVENT_ID, base_url=BASE)


def test_chain_link_with_a_wrong_hash_is_a_typed_hard_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws1 = _raw_workspace(source_available_at="2026-01-30T16:30:00Z", source_sha256="a" * 64)
    ws2 = _raw_workspace(source_available_at="2026-01-31T09:00:00Z", source_sha256="b" * 64)
    gen1, man1 = _mint(tmp_path, {EVENT_ID: ws1}, generated_at="2026-01-30T16:30:00Z")
    # Deliberately WRONG previous_manifest_sha256 — does not match gen1's
    # real bytes.
    gen2, man2 = _mint(
        tmp_path, {EVENT_ID: ws2}, generated_at="2026-01-31T09:00:00Z",
        previous_generation_id=gen1, previous_manifest_sha256="0" * 64,
    )
    objects = {
        gen1: {"manifest": man1, "workspaces": {EVENT_ID: ws1 | {"generation_id": gen1}}},
        gen2: {"manifest": man2, "workspaces": {EVENT_ID: ws2 | {"generation_id": gen2}}},
    }
    monkeypatch.setattr(reader, "_fetch_bytes", _server(objects, marker_generation_id=gen2))

    with pytest.raises(reader.WorkspaceChainIntegrityError):
        reader.read_event_source_revisions(EVENT_ID, base_url=BASE)


def test_chain_walk_never_reads_a_generation_it_has_not_verified() -> None:
    """No candidate exists at all (clean 404 marker) -> empty history, never
    an exception — the FIRST-EVER discovery case must not be treated as a
    chain integrity failure."""
    def fake_fetch_bytes(url: str, *, limit: int, allow_404: bool = False) -> bytes | None:
        if allow_404:
            return None
        raise reader.CompanyIntelligenceReadError(f"404: {url}")

    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(reader, "_fetch_bytes", fake_fetch_bytes)
        assert reader.read_event_source_revisions(EVENT_ID, base_url=BASE) == []


def test_max_hops_bound_is_a_typed_hard_failure_not_an_unbounded_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MAJOR-8(c): a 4-generation chain against an artificially tiny
    max_hops=3 bound refuses with a typed integrity error rather than
    walking further — the bound is genuinely enforced, not decorative."""
    ws1 = _raw_workspace(source_available_at="2026-01-01T00:00:00Z", source_sha256="a" * 64)
    ws2 = _raw_workspace(source_available_at="2026-02-01T00:00:00Z", source_sha256="b" * 64)
    ws3 = _raw_workspace(source_available_at="2026-03-01T00:00:00Z", source_sha256="c" * 64)
    ws4 = _raw_workspace(source_available_at="2026-04-01T00:00:00Z", source_sha256="d" * 64)

    gen1, man1 = _mint(tmp_path, {EVENT_ID: ws1}, generated_at="2026-01-01T00:00:00Z")
    gen1_sha = sha256(canonical_json_bytes(man1)).hexdigest()
    gen2, man2 = _mint(
        tmp_path, {EVENT_ID: ws2}, generated_at="2026-02-01T00:00:00Z",
        previous_generation_id=gen1, previous_manifest_sha256=gen1_sha,
    )
    gen2_sha = sha256(canonical_json_bytes(man2)).hexdigest()
    gen3, man3 = _mint(
        tmp_path, {EVENT_ID: ws3}, generated_at="2026-03-01T00:00:00Z",
        previous_generation_id=gen2, previous_manifest_sha256=gen2_sha,
    )
    gen3_sha = sha256(canonical_json_bytes(man3)).hexdigest()
    gen4, man4 = _mint(
        tmp_path, {EVENT_ID: ws4}, generated_at="2026-04-01T00:00:00Z",
        previous_generation_id=gen3, previous_manifest_sha256=gen3_sha,
    )

    objects = {
        gen1: {"manifest": man1, "workspaces": {EVENT_ID: ws1 | {"generation_id": gen1}}},
        gen2: {"manifest": man2, "workspaces": {EVENT_ID: ws2 | {"generation_id": gen2}}},
        gen3: {"manifest": man3, "workspaces": {EVENT_ID: ws3 | {"generation_id": gen3}}},
        gen4: {"manifest": man4, "workspaces": {EVENT_ID: ws4 | {"generation_id": gen4}}},
    }
    monkeypatch.setattr(reader, "_fetch_bytes", _server(objects, marker_generation_id=gen4))

    with pytest.raises(reader.WorkspaceChainIntegrityError):
        reader.read_event_source_revisions(EVENT_ID, base_url=BASE, max_hops=3)

    # A bound comfortably above the chain's real depth succeeds normally.
    revisions = reader.read_event_source_revisions(EVENT_ID, base_url=BASE, max_hops=10)
    assert len(revisions) == 4


# ---------------------------------------------------------------------------
# D2(a): three-way disposition
# ---------------------------------------------------------------------------

def test_load_workspace_with_disposition_three_way() -> None:
    def stub_found(event_id):
        return {"event_id": event_id}

    def stub_not_published(event_id):
        raise reader.WorkspaceChainNotPublished("clean 404")

    def stub_network_error(event_id):
        raise TimeoutError("connection timed out")

    ws, disp = reader.load_workspace_with_disposition("e1", fetch=stub_found)
    assert disp == "found" and ws is not None

    ws, disp = reader.load_workspace_with_disposition("e1", fetch=stub_not_published)
    assert disp == "not_published" and ws is None

    ws, disp = reader.load_workspace_with_disposition("e1", fetch=stub_network_error)
    assert disp == "fetch_failed" and ws is None


# ---------------------------------------------------------------------------
# D3: single shared seam — the duplicate GET implementation is retired
# ---------------------------------------------------------------------------

def test_raw_fetch_workspace_no_longer_exists_in_the_builder_module() -> None:
    import scripts.build_cycle_pattern_imce_prospective as b

    assert not hasattr(b, "_raw_fetch_workspace")
    # The builder's own disposition wrapper and its NotPublished marker are
    # now aliases of the ONE shared reader implementation, not lookalikes.
    assert b._NotPublished is reader.WorkspaceChainNotPublished


def test_refresh_script_prior_loaders_are_aliases_of_the_shared_reader() -> None:
    import scripts.refresh_event_workspaces as refresh_mod

    # _raw_load_prior_workspace stays a THIN DELEGATOR (not a retired name)
    # — it exists, but its body is one line calling the shared reader.
    assert refresh_mod._raw_load_prior_workspace is not None
    assert refresh_mod._PriorWorkspaceNotPublished is reader.WorkspaceChainNotPublished


# ---------------------------------------------------------------------------
# NEW-MINOR-18 (Opus red-team verification round 2, 2026-08-23): the chain
# link's hash must be over the marker's own RAW bytes as fetched, never a
# re-serialization of the parsed dict — re-serializing is not guaranteed
# byte-identical to what R2 actually stores (key order, whitespace, a field
# the reader silently drops) and would mint a chain link that never
# verifies against the real object.
# ---------------------------------------------------------------------------

def test_fetch_current_workspace_marker_raw_returns_the_exact_fetched_bytes(monkeypatch) -> None:
    parsed = {
        "schema": MANIFEST_SCHEMA_V2, "generation_id": "d" * 24, "generated_at": "2026-07-30T16:30:00Z",
        "authority": "context_only", "status": "ready", "event_count": 0, "files": {},
        "previous_generation_id": None, "previous_manifest_sha256": None,
    }
    # Deliberately NOT canonical_json_bytes(parsed) — extra whitespace and a
    # different key order than the canonical form, exactly the kind of
    # byte-for-byte divergence a real R2 object can carry relative to any
    # local re-serialization of its parsed contents.
    non_canonical_body = (
        b'{\n  "generation_id": "' + b"d" * 24 + b'",\n  "schema": "' + MANIFEST_SCHEMA_V2.encode() + b'",\n'
        b'  "generated_at": "2026-07-30T16:30:00Z", "authority": "context_only", "status": "ready",\n'
        b'  "event_count": 0, "files": {}, "previous_generation_id": null, "previous_manifest_sha256": null\n}\n'
    )
    assert non_canonical_body != canonical_json_bytes(parsed), "fixture must actually diverge from the canonical form"

    def fake_fetch_bytes(url: str, *, limit: int, allow_404: bool = False) -> bytes | None:
        assert url == f"{BASE}/event_workspaces/manifest.json"
        return non_canonical_body

    monkeypatch.setattr(reader, "_fetch_bytes", fake_fetch_bytes)
    result = reader.fetch_current_workspace_marker_raw(base_url=BASE)
    assert result is not None
    raw_bytes, marker = result
    # The RAW bytes returned are byte-IDENTICAL to what the server sent —
    # never a re-serialization — so hashing them reproduces a hash a real
    # verifier could check against the object's own stored bytes.
    assert raw_bytes == non_canonical_body
    assert sha256(raw_bytes).hexdigest() != sha256(canonical_json_bytes(parsed)).hexdigest()
    assert marker["generation_id"] == "d" * 24

    # The thin-wrapper contract: fetch_current_workspace_marker (still used
    # wherever only the parsed dict is needed) returns just the parsed half.
    assert reader.fetch_current_workspace_marker(base_url=BASE) == marker


def test_fetch_current_workspace_marker_raw_clean_404_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(reader, "_fetch_bytes", lambda url, *, limit, allow_404=False: None)
    assert reader.fetch_current_workspace_marker_raw(base_url=BASE) is None
    assert reader.fetch_current_workspace_marker(base_url=BASE) is None


# ---------------------------------------------------------------------------
# D5 Task 2 — the pure Earnings projection over the real revision-chain reader
# ---------------------------------------------------------------------------

_D5_GENERATION_ID = "peg:" + "e" * 64


def _d5_episode(*, cut: str = "2026-01-31T12:00:00Z") -> dict:
    anchor = {
        "kind": "reset_low",
        "time": cut,
        "price": "100.0000",
        "basis": "turn_watch.reset_low",
        "source_receipt": "sha256:" + "f" * 64,
    }
    return {
        "schema": "prophet.candidate_episode/v1",
        "episode_id": b1_episode_id("SEC:US-XNAS-AAPL", "epoch_0", anchor, 1),
        "company_id": "ISS:US:320193",
        "security_id": "SEC:US-XNAS-AAPL",
        "identity_epoch": "epoch_0",
        "opened_at": cut,
        "opened_session": cut[:10],
        "structural_anchor": anchor,
        "expert_events": ["radar:event:content-addressed-1"],
    }


def _d5_issuer_master() -> IssuerMaster:
    return IssuerMaster.from_records([{
        "security_id": "SEC:US-XNAS-AAPL",
        "issuer_id": "ISS:US:320193",
        "issuer_state": "active",
        "listing_key": "US:XNAS:AAPL",
        "issuer_cik": "0000320193",
    }])


def _d5_project(*, episode: dict | None = None, read_revisions=None) -> dict:
    return build_earnings_intelligence_vector(
        episode=episode or _d5_episode(),
        episode_generation_id=_D5_GENERATION_ID,
        episode_known_at="2026-01-30T20:05:00Z",
        issuer_master=_d5_issuer_master(),
        find_event_id=lambda company_id: EVENT_ID,
        read_revisions=read_revisions or (
            lambda event_id: reader.read_event_source_revisions(event_id, base_url=BASE)
        ),
    )


def _chain_objects(*bundles: tuple[str, dict, dict]) -> dict[str, dict]:
    return {
        generation_id: {
            "manifest": manifest,
            "workspaces": {EVENT_ID: workspace | {"generation_id": generation_id}},
        }
        for generation_id, manifest, workspace in bundles
    }


def test_real_revision_reader_rejects_foreign_body_at_the_receipted_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = _raw_workspace(
        source_available_at="2026-01-30T20:00:00Z",
        observed_at="2026-01-30T20:02:00Z",
    )
    generation_id, manifest = _mint(
        tmp_path, {EVENT_ID: requested}, generated_at="2026-01-30T20:03:00Z",
    )
    foreign = _raw_workspace(
        source_available_at="2026-01-30T20:00:00Z",
        observed_at="2026-01-30T20:02:00Z",
        event_id="evt_cik9999999999_2026q3_results",
    )
    foreign["issuer"]["company_id"] = "cik:9999999999"
    objects = _chain_objects((generation_id, manifest, foreign))
    objects[generation_id]["serve_workspace_overrides"] = True
    monkeypatch.setattr(
        reader, "_fetch_bytes",
        _server(objects, marker_generation_id=generation_id),
    )

    with pytest.raises(
        reader.WorkspaceChainIntegrityError,
        match="workspace.*(bytes|sha256).*manifest receipt",
    ):
        reader.read_event_source_revisions(EVENT_ID, base_url=BASE)


def test_revision_reader_rejects_same_address_workspace_byte_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipted = _raw_workspace(
        source_available_at="2026-01-30T20:00:00Z",
        observed_at="2026-01-30T20:02:00Z",
        fact_value=100,
    )
    generation_id, manifest = _mint(
        tmp_path, {EVENT_ID: receipted}, generated_at="2026-01-30T20:03:00Z",
    )
    substituted = jsonlib.loads(
        _MINTED_WORKSPACE_BYTES[(generation_id, EVENT_ID)]
    )
    substituted["facts"] = [dict(receipted["facts"][0], value=999)]
    substituted["schema"] = "dummy_workspace.v1"
    substituted["sources"][0]["source_sha256"] = "b" * 64
    assert len(canonical_json_bytes(substituted)) == manifest["files"][
        f"workspaces/{EVENT_ID}.json"
    ]["bytes"]
    monkeypatch.setattr(
        reader,
        "_fetch_bytes",
        _server(
            {
                generation_id: {
                    "manifest": manifest,
                    "workspaces": {EVENT_ID: substituted},
                    "serve_workspace_overrides": True,
                },
            },
            marker_generation_id=generation_id,
        ),
    )

    with pytest.raises(
        reader.WorkspaceChainIntegrityError,
        match="workspace.*sha256.*manifest receipt",
    ):
        reader.read_event_source_revisions(EVENT_ID, base_url=BASE)


def test_d5_same_address_workspace_substitution_is_receipted_pending_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipted = _raw_workspace(
        source_available_at="2026-01-30T20:00:00Z",
        observed_at="2026-01-30T20:02:00Z",
        fact_value=100,
    )
    generation_id, manifest = _mint(
        tmp_path, {EVENT_ID: receipted}, generated_at="2026-01-30T20:03:00Z",
    )
    substituted = jsonlib.loads(
        _MINTED_WORKSPACE_BYTES[(generation_id, EVENT_ID)]
    )
    substituted["facts"] = [dict(receipted["facts"][0], value=999)]
    substituted["schema"] = "dummy_workspace.v1"
    substituted["sources"][0]["source_sha256"] = "b" * 64
    assert len(canonical_json_bytes(substituted)) == manifest["files"][
        f"workspaces/{EVENT_ID}.json"
    ]["bytes"]
    monkeypatch.setattr(
        reader,
        "_fetch_bytes",
        _server(
            {
                generation_id: {
                    "manifest": manifest,
                    "workspaces": {EVENT_ID: substituted},
                    "serve_workspace_overrides": True,
                },
            },
            marker_generation_id=generation_id,
        ),
    )

    payload = _d5_project()
    family = payload["evidence_families"][0]
    assert family["coverage"] == {
        "state": "UNKNOWN",
        "basis": "correction_chain_integrity",
    }
    assert family["correction"] == {
        "state_at_decision": "PENDING",
        "current_state": "UNKNOWN",
        "decision_version_ref_ids": [],
        "later_correction_ref_ids": [],
    }
    assert all(item["value_state"] == "ABSENT" for item in family["observations"])
    assert all(
        set(item["absence_reasons"]) == {"UNESTIMABLE", "CORRECTION_PENDING"}
        for item in family["observations"]
    )
    assert payload["assembly_receipt"]["errors"][0]["type"] == (
        "WorkspaceChainIntegrityError"
    )
    serialized = jsonlib.dumps(family, sort_keys=True)
    assert "999" not in serialized
    assert "dummy_workspace" not in serialized
    assert "b" * 64 not in serialized


def test_d5_decision_value_stays_at_n_while_n_plus_1_is_observed_correction_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws1 = _raw_workspace(
        source_available_at="2026-01-30T20:00:00Z", observed_at="2026-01-30T20:02:00Z",
        source_sha256="a" * 64, fact_value=100,
    )
    ws2 = _raw_workspace(
        source_available_at="2026-02-01T20:00:00Z", observed_at="2026-02-01T20:02:00Z",
        source_sha256="b" * 64, fact_value=120,
    )
    gen1, man1 = _mint(tmp_path, {EVENT_ID: ws1}, generated_at="2026-01-30T20:03:00Z")
    gen2, man2 = _mint(
        tmp_path, {EVENT_ID: ws2}, generated_at="2026-02-01T20:03:00Z",
        previous_generation_id=gen1,
        previous_manifest_sha256=sha256(canonical_json_bytes(man1)).hexdigest(),
    )
    assert ws1["facts"][0]["value"] != ws2["facts"][0]["value"]
    monkeypatch.setattr(
        reader, "_fetch_bytes",
        _server(
            _chain_objects((gen1, man1, ws1), (gen2, man2, ws2)),
            marker_generation_id=gen1,
        ),
    )
    initial_payload = _d5_project()
    initial_family = initial_payload["evidence_families"][0]
    initial_fact = next(
        item for item in initial_family["observations"]
        if item["native_metric_id"] == "fact:revenue"
    )
    fetch_calls: list[str] = []
    monkeypatch.setattr(
        reader, "_fetch_bytes",
        _server(_chain_objects((gen1, man1, ws1), (gen2, man2, ws2)),
                marker_generation_id=gen2, fetch_calls=fetch_calls),
    )

    corrected_payload = _d5_project()
    family = corrected_payload["evidence_families"][0]
    fact = next(item for item in family["observations"] if item["native_metric_id"] == "fact:revenue")
    assert fact["value"] == 100
    assert fact == initial_fact
    assert fact["observation_id"] == initial_fact["observation_id"]
    assert fact["correction_lineage_state"] == "NONE_IN_CHAIN"
    assert corrected_payload["projection_id"] != initial_payload["projection_id"]
    assert family["correction"]["state_at_decision"] == "NONE"
    assert family["correction"]["current_state"] == "CORRECTED"
    decision_refs = set(family["correction"]["decision_version_ref_ids"])
    later_refs = set(family["correction"]["later_correction_ref_ids"])
    assert decision_refs and later_refs and decision_refs.isdisjoint(later_refs)
    source_refs = {item["source_ref_id"]: item for item in family["source_refs"]}
    assert {source_refs[ref]["version_or_generation"] for ref in decision_refs} == {gen1}
    assert {source_refs[ref]["version_or_generation"] for ref in later_refs} == {gen2}
    assert family["point_in_time"]["corrected_at"]["value"] == "2026-02-01T20:03:00Z"

    # The adapter calls the real reader ONCE. The reader in turn fetches each
    # immutable manifest and workspace exactly once per verified chain hop.
    for generation_id in (gen1, gen2):
        manifest_url = f"{BASE}/event_workspaces/generations/{generation_id}/manifest.json"
        workspace_url = f"{BASE}/event_workspaces/generations/{generation_id}/workspaces/{EVENT_ID}.json"
        assert fetch_calls.count(manifest_url) == 1
        assert fetch_calls.count(workspace_url) == 1


def test_d5_body_only_generations_collapse_to_not_observable_never_no_correction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws1 = _raw_workspace(
        source_available_at="2026-01-30T20:00:00Z", source_sha256="a" * 64,
        fact_value=100, include_issuer_release=False,
    )
    ws2 = _raw_workspace(
        source_available_at="2026-02-01T20:00:00Z", source_sha256="b" * 64,
        fact_value=120, include_issuer_release=False,
    )
    gen1, man1 = _mint(tmp_path, {EVENT_ID: ws1}, generated_at="2026-01-30T20:03:00Z")
    gen2, man2 = _mint(
        tmp_path, {EVENT_ID: ws2}, generated_at="2026-02-01T20:03:00Z",
        previous_generation_id=gen1,
        previous_manifest_sha256=sha256(canonical_json_bytes(man1)).hexdigest(),
    )
    monkeypatch.setattr(
        reader, "_fetch_bytes",
        _server(_chain_objects((gen1, man1, ws1), (gen2, man2, ws2)), marker_generation_id=gen2),
    )
    revisions = reader.read_event_source_revisions(EVENT_ID, base_url=BASE)
    assert len(revisions) == 1 and revisions[0]["source_sha256"] is None

    family = _d5_project()["evidence_families"][0]
    assert all(
        observation["correction_lineage_state"] == "NOT_OBSERVABLE"
        for observation in family["observations"]
    )


def test_d5_source_before_cut_but_observed_after_is_typed_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws = _raw_workspace(
        source_available_at="2026-01-31T10:00:00Z",
        observed_at="2026-01-31T13:00:00Z",
    )
    gen, manifest = _mint(tmp_path, {EVENT_ID: ws}, generated_at="2026-01-31T13:01:00Z")
    monkeypatch.setattr(
        reader, "_fetch_bytes",
        _server(_chain_objects((gen, manifest, ws)), marker_generation_id=gen),
    )
    family = _d5_project()["evidence_families"][0]
    assert family["coverage"]["state"] == "COVERED"
    assert family["point_in_time"]["decision_admissibility"] == "AFTER_DECISION_CUT"
    assert family["observations"][0]["value_state"] == "ABSENT"
    assert family["observations"][0]["absence_reasons"] == ["NOT_CAPTURED_AT_DECISION"]


@pytest.mark.parametrize("missing_clock", ["source_available_at", "observed_at", "generated_at"])
def test_d5_unknown_clock_is_typed_and_names_the_missing_clock(
    missing_clock: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _raw_workspace(source_available_at="2026-01-30T20:00:00Z")
    generation_id, manifest = _mint(
        tmp_path, {EVENT_ID: workspace}, generated_at="2026-01-30T20:03:00Z",
    )
    served_workspace = workspace | {
        "generation_id": generation_id,
        "generated_at": "2026-01-30T20:03:00Z",
        "lifecycle": dict(workspace["lifecycle"]),
    }
    if missing_clock == "generated_at":
        served_workspace["generated_at"] = None
    else:
        served_workspace["lifecycle"][missing_clock] = None
    revision = {
        "generation_id": generation_id,
        "source_sha256": "d" * 64,
        "source_available_at": served_workspace["lifecycle"]["source_available_at"],
        "observed_at": served_workspace["lifecycle"]["observed_at"],
        "lifecycle_state": "complete",
        "form": "8-K",
        "workspace": served_workspace,
    }

    family = _d5_project(read_revisions=lambda event_id: [revision])["evidence_families"][0]
    assert family["coverage"]["state"] == "UNKNOWN"
    assert family["point_in_time"]["decision_admissibility"] == "UNKNOWN"
    assert family["point_in_time"]["missing_clocks"] == [missing_clock]
    assert family["observations"][0]["value_state"] == "ABSENT"
    assert family["observations"][0]["absence_reasons"] == ["UNKNOWN"]


def test_d5_equal_clock_distinct_revisions_are_conflicted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws1 = _raw_workspace(
        source_available_at="2026-01-30T20:00:00Z",
        observed_at="2026-01-30T20:02:00Z", source_sha256="a" * 64, fact_value=100,
    )
    ws2 = _raw_workspace(
        source_available_at="2026-01-30T20:00:00Z",
        observed_at="2026-01-30T20:02:00Z", source_sha256="b" * 64, fact_value=120,
    )
    gen1, man1 = _mint(tmp_path, {EVENT_ID: ws1}, generated_at="2026-01-30T20:03:00Z")
    gen2, man2 = _mint(
        tmp_path, {EVENT_ID: ws2}, generated_at="2026-01-30T20:04:00Z",
        previous_generation_id=gen1,
        previous_manifest_sha256=sha256(canonical_json_bytes(man1)).hexdigest(),
    )
    monkeypatch.setattr(
        reader, "_fetch_bytes",
        _server(_chain_objects((gen1, man1, ws1), (gen2, man2, ws2)), marker_generation_id=gen2),
    )
    family = _d5_project()["evidence_families"][0]
    assert family["coverage"]["state"] == "UNKNOWN"
    assert family["point_in_time"]["decision_admissibility"] == "UNVERIFIABLE"
    assert family["observations"][0]["value_state"] == "ABSENT"
    assert family["observations"][0]["absence_reasons"] == ["CONFLICTED"]


@pytest.mark.parametrize("failure_kind", ["missing_predecessor", "wrong_hash", "hop_bound"])
def test_d5_real_reader_integrity_failures_never_degrade_to_empty_healthy_evidence(
    failure_kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ws1 = _raw_workspace(source_available_at="2026-01-30T20:00:00Z", source_sha256="a" * 64)
    ws2 = _raw_workspace(source_available_at="2026-02-01T20:00:00Z", source_sha256="b" * 64)
    if failure_kind == "missing_predecessor":
        current_id, current_manifest = _mint(
            tmp_path, {EVENT_ID: ws1}, generated_at="2026-01-30T20:03:00Z",
            previous_generation_id="0" * 24, previous_manifest_sha256="f" * 64,
        )
        objects = _chain_objects((current_id, current_manifest, ws1))
        real_read = lambda event_id: reader.read_event_source_revisions(event_id, base_url=BASE)
    else:
        gen1, man1 = _mint(tmp_path, {EVENT_ID: ws1}, generated_at="2026-01-30T20:03:00Z")
        gen2, man2 = _mint(
            tmp_path, {EVENT_ID: ws2}, generated_at="2026-02-01T20:03:00Z",
            previous_generation_id=gen1,
            previous_manifest_sha256=(
                "0" * 64 if failure_kind == "wrong_hash"
                else sha256(canonical_json_bytes(man1)).hexdigest()
            ),
        )
        current_id = gen2
        objects = _chain_objects((gen1, man1, ws1), (gen2, man2, ws2))
        max_hops = 1 if failure_kind == "hop_bound" else 500
        real_read = lambda event_id: reader.read_event_source_revisions(
            event_id, base_url=BASE, max_hops=max_hops,
        )
    monkeypatch.setattr(
        reader, "_fetch_bytes", _server(objects, marker_generation_id=current_id),
    )

    payload = _d5_project(read_revisions=real_read)
    family = payload["evidence_families"][0]
    assert family["coverage"]["state"] == "UNKNOWN"
    assert family["observations"][0]["value_state"] == "ABSENT"
    assert set(family["observations"][0]["absence_reasons"]) == {
        "UNESTIMABLE", "CORRECTION_PENDING",
    }
    assert payload["assembly_receipt"]["errors"][0]["type"] == "WorkspaceChainIntegrityError"


@pytest.mark.parametrize("failure", [
    "chain link names generation 'missing', which does not exist",
    "previous_manifest_sha256 does not match predecessor bytes",
    "predecessor chain exceeds the 3-hop bound without reaching a root",
])
def test_d5_chain_integrity_failure_is_sanitized_unestimable_receipt(failure: str) -> None:
    def broken_reader(event_id: str):
        raise reader.WorkspaceChainIntegrityError(
            failure + " at /private/worktree/secret and https://internal.invalid/object"
        )

    payload = _d5_project(read_revisions=broken_reader)
    family = payload["evidence_families"][0]
    assert family["coverage"]["state"] == "UNKNOWN"
    assert set(family["observations"][0]["absence_reasons"]) == {
        "UNESTIMABLE", "CORRECTION_PENDING",
    }
    receipt = jsonlib.dumps(payload["assembly_receipt"], sort_keys=True)
    assert "WorkspaceChainIntegrityError" in receipt
    assert "/private/" not in receipt
    assert "https://" not in receipt
