"""IMCE A5C: the manifest chain + the ONE shared disposition-aware reader.

Covers frozen spec A (v2 manifest chain schema), D (shared reader
capabilities: three-way disposition, verified predecessor walk, per-event
ordered source revisions with consecutive-carry dedupe), and the D3
retirement of the duplicate GET implementation in
scripts/build_cycle_pattern_imce_prospective.py.

No network: every fetch in this file is served by an in-process ``fake_get``
stub keyed by exact URL, monkeypatched onto ``requests.get`` (the same
pattern tests/test_refresh_event_workspaces.py already uses — the reader's
new primitives use the identical plain ``requests.get(url, headers=...,
timeout=...)`` call shape, not the hardened streaming ``_fetch_bytes`` path
the model-facing reader functions use).
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

BASE = "https://company-intelligence-chain.example/company_intelligence"
EVENT_ID = "evt_cik0000320193_2026q3_results"


def _raw_workspace(
    *,
    source_available_at: str,
    observed_at: str | None = None,
    source_sha256: str = "d" * 64,
    accession: str = "0000000000-26-000001",
    form: str = "8-K",
    state: str = "complete",
    event_id: str = EVENT_ID,
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
        "facts": [],
        "deltas": [],
        "guidance": [],
        "claims": [],
        "sources": [{
            "kind": "issuer_release", "document_id": "doc:1",
            "filing_key": {"cik": "0000320193", "accession": accession},
            "source_sha256": source_sha256, "form": form, "url": None,
            "receipt_state": "byte_replayed",
        }],
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
    return generation_dir.name, manifest


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: object = None):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400 and self.status_code != 404:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> object:
        return self._payload


def _server(objects: dict[str, dict], *, marker_generation_id: str | None):
    """objects: generation_id -> {"manifest": dict, "workspaces": {event_id: dict}}."""

    def fake_get(url: str, *, headers=None, timeout=None):
        if url == f"{BASE}/event_workspaces/manifest.json":
            if marker_generation_id is None:
                return _FakeResponse(status_code=404)
            return _FakeResponse(status_code=200, payload=objects[marker_generation_id]["manifest"])
        for generation_id, bundle in objects.items():
            if url == f"{BASE}/event_workspaces/generations/{generation_id}/manifest.json":
                return _FakeResponse(status_code=200, payload=bundle["manifest"])
            for event_id, ws in bundle["workspaces"].items():
                if url == f"{BASE}/event_workspaces/generations/{generation_id}/workspaces/{event_id}.json":
                    return _FakeResponse(status_code=200, payload=ws)
        return _FakeResponse(status_code=404)

    return fake_get


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
    monkeypatch.setattr("requests.get", _server(objects, marker_generation_id=gen_id))

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
    monkeypatch.setattr("requests.get", _server(objects, marker_generation_id=gen2))

    revisions = reader.read_event_source_revisions(EVENT_ID, base_url=BASE)
    assert [r["generation_id"] for r in revisions] == [gen1, gen2]
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
    monkeypatch.setattr("requests.get", _server(objects, marker_generation_id=gen3))

    revisions = reader.read_event_source_revisions(EVENT_ID, base_url=BASE)
    # gen1 and gen2 both carry source_sha256="a"*64 for this event — deduped
    # to ONE revision; gen3 introduces "c"*64 — a genuine second revision.
    assert [r["source_sha256"] for r in revisions] == ["a" * 64, "c" * 64]
    assert len(revisions) == 2


def test_chain_link_to_a_nonexistent_generation_is_a_typed_hard_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = _raw_workspace(source_available_at="2026-01-30T16:30:00Z")
    gen1, man1 = _mint(
        tmp_path, {EVENT_ID: ws}, generated_at="2026-01-30T16:30:00Z",
        previous_generation_id="0" * 24, previous_manifest_sha256="f" * 64,
    )
    objects = {gen1: {"manifest": man1, "workspaces": {EVENT_ID: ws | {"generation_id": gen1}}}}
    monkeypatch.setattr("requests.get", _server(objects, marker_generation_id=gen1))

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
    monkeypatch.setattr("requests.get", _server(objects, marker_generation_id=gen2))

    with pytest.raises(reader.WorkspaceChainIntegrityError):
        reader.read_event_source_revisions(EVENT_ID, base_url=BASE)


def test_chain_walk_never_reads_a_generation_it_has_not_verified() -> None:
    """No candidate exists at all (clean 404 marker) -> empty history, never
    an exception — the FIRST-EVER discovery case must not be treated as a
    chain integrity failure."""
    def fake_get(url, *, headers=None, timeout=None):
        return _FakeResponse(status_code=404)

    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr("requests.get", fake_get)
        assert reader.read_event_source_revisions(EVENT_ID, base_url=BASE) == []


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
