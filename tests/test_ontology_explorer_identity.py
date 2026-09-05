"""tests/test_ontology_explorer_identity.py — F04-X1 source identity (RED first).

A composed read is only as truthful as its claim about WHICH owner generation it
read. Two failure classes are specifically in scope, and they are different:

  * MID-READ MUTATION — the nightly rewrites an artifact between the composer's
    first and last read, so the response blends two generations. Detected by
    re-verifying the byte digest after composition, not by trusting a stat taken
    before it.
  * STABLE BUT MIXED GENERATION — nothing moves during the read, yet the two
    sources already disagree: the knowledge file is at one revision and the
    compiled state was built from another. Nothing is racing; the pair is simply
    incoherent, and a digest of "what I read" cannot notice that on its own.

Both must fail closed with a typed error, never a plausible blended answer.

The freshness clause is separate and deliberately modest: this process cannot
observe what the DEPLOYED checkout serves, so it must never claim to be fresher
than the canonical `/transmission.html` surface. Where the comparison cannot be
made, it reports that the verification is unavailable.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ontology_explorer_fixtures as fx  # noqa: E402


def _compose(root: Path, **kwargs):
    from engine.ontology_explorer import compose_snapshot
    return compose_snapshot(root, chain=kwargs.pop("chain", fx.SLUG), **kwargs)


# --------------------------------------------------------------------------
# the read receipt
# --------------------------------------------------------------------------
def test_every_source_read_is_receipted_with_its_own_digest(tmp_path):
    root = fx.build_root(tmp_path)
    snap = _compose(root)
    reads = {r["path"]: r for r in snap["source"]["reads"]}
    assert set(reads) == {
        f"knowledge/transmission/{fx.SLUG}.yaml",
        "data/transmission/chain_state.json",
    }
    for relpath, receipt in reads.items():
        raw = (root / relpath).read_bytes()
        assert receipt["sha256"] == hashlib.sha256(raw).hexdigest()
        assert receipt["bytes"] == len(raw)


def test_manifest_hash_is_a_function_of_the_read_digests(tmp_path):
    """The manifest hash must be reproducible from the receipts alone —
    otherwise a caller cannot check that two responses saw the same generation."""
    from engine.ontology_explorer import manifest_hash_for
    snap = _compose(fx.build_root(tmp_path))
    assert snap["source"]["source_manifest_hash"] == manifest_hash_for(snap["source"]["reads"])


def test_identical_sources_produce_an_identical_manifest_hash(tmp_path):
    a = _compose(fx.build_root(tmp_path / "a"))
    b = _compose(fx.build_root(tmp_path / "b"))
    assert a["source"]["source_manifest_hash"] == b["source"]["source_manifest_hash"]


def test_a_single_changed_byte_changes_the_manifest_hash(tmp_path):
    root_a = fx.build_root(tmp_path / "a")
    state = fx.chain_state()
    state["chains"][0]["nodes"][0]["receipts"][0]["value"] = 999.0
    root_b = fx.build_root(tmp_path / "b", state_doc=state)
    assert (_compose(root_a)["source"]["source_manifest_hash"]
            != _compose(root_b)["source"]["source_manifest_hash"])


def test_the_receipt_is_a_read_receipt_not_an_owner_generation(tmp_path):
    """Composing does not GENERATE anything the owners did not. The digest
    describes bytes this process read; it is never presented as a new owner
    generation, and the owner's own build stamp is carried through untouched."""
    root = fx.build_root(tmp_path)
    snap = _compose(root)
    assert snap["source"]["receipt_kind"] == "composed_read"
    assert snap["source"]["built"] == "2026-01-03 02:10 UTC"
    assert snap["source"]["asof"] == "2026-01-02"
    assert "owner_generation" not in snap["source"]


# --------------------------------------------------------------------------
# mutant class 1 — mid-read mutation
# --------------------------------------------------------------------------
def test_a_mid_read_mutation_fails_closed(tmp_path, monkeypatch):
    """The nightly rewrites the state file AFTER this process has read it, so the
    composed answer describes a generation that no longer exists. The composer
    must notice by re-reading, not by trusting a stat it took beforehand."""
    from engine import ontology_explorer as oe

    root = fx.build_root(tmp_path)
    target = root / "data" / "transmission" / "chain_state.json"
    original = oe._read_source

    def mutating_read(path: Path):
        result = original(path)
        if path.name == "chain_state.json":
            doc = fx.chain_state(confirmed=(True, True, True, True), state="expressed")
            target.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return result

    monkeypatch.setattr(oe, "_read_source", mutating_read)
    with pytest.raises(oe.SourceIncoherent) as excinfo:
        _compose(root)
    assert "mid_read_mutation" in str(excinfo.value)


def test_a_write_that_lands_before_its_own_read_is_covered_by_the_rev_check(tmp_path):
    """The honest limit of digest re-verification.

    If a source is rewritten BEFORE this process reads it, that read simply
    returns the newer generation and every digest stays stable afterwards — so
    re-reading cannot detect that a sibling artifact was read from the older
    generation. What closes that window is not the digest but the revision
    coherence check, which is why both exist and why neither is redundant.
    """
    from engine.ontology_explorer import SourceIncoherent
    root = fx.build_root(tmp_path, yaml_doc=fx.chain_yaml(rev=4),
                         state_doc=fx.chain_state(rev=5))
    with pytest.raises(SourceIncoherent) as excinfo:
        _compose(root)
    assert "rev_mismatch" in str(excinfo.value)


def test_a_stable_read_does_not_trip_the_mutation_detector(tmp_path):
    """The guard must not be so eager that an ordinary quiet read fails."""
    snap = _compose(fx.build_root(tmp_path))
    assert snap["source"]["source_manifest_hash"]


# --------------------------------------------------------------------------
# mutant class 2 — stable but mixed generation
# --------------------------------------------------------------------------
def test_a_revision_mismatch_between_knowledge_and_state_fails_closed(tmp_path):
    from engine.ontology_explorer import SourceIncoherent
    root = fx.build_root(
        tmp_path,
        yaml_doc=fx.chain_yaml(rev=3),
        state_doc=fx.chain_state(rev=2),
    )
    with pytest.raises(SourceIncoherent) as excinfo:
        _compose(root)
    assert "rev_mismatch" in str(excinfo.value)


def test_an_unknown_state_schema_fails_closed(tmp_path):
    from engine.ontology_explorer import SourceIncoherent
    state = fx.chain_state()
    state["schema"] = "transmission_chains.v99"
    with pytest.raises(SourceIncoherent) as excinfo:
        _compose(fx.build_root(tmp_path, state_doc=state))
    assert "schema_incompatible" in str(excinfo.value)


def test_a_node_in_state_that_the_knowledge_file_does_not_define_fails_closed(tmp_path):
    from engine.ontology_explorer import SourceIncoherent
    state = fx.chain_state()
    state["chains"][0]["nodes"].append(
        {"id": "ghost", "resolved": True, "confirmed": True, "receipts": []})
    with pytest.raises(SourceIncoherent) as excinfo:
        _compose(fx.build_root(tmp_path, state_doc=state))
    assert "unknown_node" in str(excinfo.value)


# --------------------------------------------------------------------------
# absence of the source at all
# --------------------------------------------------------------------------
def test_a_missing_knowledge_file_is_source_unavailable(tmp_path):
    from engine.ontology_explorer import SourceUnavailable
    root = fx.build_root(tmp_path)
    (root / "knowledge" / "transmission" / f"{fx.SLUG}.yaml").unlink()
    with pytest.raises(SourceUnavailable):
        _compose(root)


def test_a_missing_state_file_is_source_unavailable(tmp_path):
    from engine.ontology_explorer import SourceUnavailable
    root = fx.build_root(tmp_path)
    (root / "data" / "transmission" / "chain_state.json").unlink()
    with pytest.raises(SourceUnavailable):
        _compose(root)


def test_an_unparseable_state_file_is_source_unavailable(tmp_path):
    from engine.ontology_explorer import SourceUnavailable
    root = fx.build_root(tmp_path)
    (root / "data" / "transmission" / "chain_state.json").write_text("{ not json",
                                                                    encoding="utf-8")
    with pytest.raises(SourceUnavailable):
        _compose(root)


def test_a_chain_absent_from_the_state_file_is_source_unavailable(tmp_path):
    from engine.ontology_explorer import SourceUnavailable
    state = fx.chain_state()
    state["chains"] = []
    with pytest.raises(SourceUnavailable):
        _compose(fx.build_root(tmp_path, state_doc=state))


# --------------------------------------------------------------------------
# freshness — never claim to be fresher than the canonical surface
# --------------------------------------------------------------------------
def test_freshness_reports_verification_unavailable_not_a_comparison(tmp_path):
    """This process reads the checkout it is running from. It cannot observe
    what the deployed canonical surface is serving, and the deployed checkout may
    lag either way, so "fresher than /transmission.html" is not a claim it is in
    a position to make."""
    snap = _compose(fx.build_root(tmp_path))
    freshness = snap["source"]["freshness"]
    assert freshness["status"] == "verification_unavailable"
    assert freshness["compared_against"] is None
    blob = json.dumps(snap, ensure_ascii=False).lower()
    assert "fresher" not in blob
    assert "most recent" not in blob
    assert "up to date" not in blob


def test_freshness_states_the_source_age_it_can_actually_observe(tmp_path):
    snap = _compose(fx.build_root(tmp_path))
    freshness = snap["source"]["freshness"]
    assert isinstance(freshness["source_age_seconds"], int)
    assert freshness["source_age_basis"] == "chain_state.built"


def test_the_house_build_stamp_format_is_actually_parsed(tmp_path):
    """The compiled artifact stamps `built` as "2026-09-05 02:10 UTC", which
    `datetime.fromisoformat` cannot read. The first version of this composer
    caught that failure and reported an age of ZERO — rendering as "built just
    now", the most reassuring possible reading of a stamp it had not understood.
    """
    snap = _compose(fx.build_root(tmp_path))
    freshness = snap["source"]["freshness"]
    assert freshness["source_age_basis"] == "chain_state.built"
    assert isinstance(freshness["source_age_seconds"], int)
    assert freshness["source_age_seconds"] > 0


def test_an_unparseable_build_stamp_reports_no_age_rather_than_zero(tmp_path):
    state = fx.chain_state()
    state["built"] = "some day, probably"
    snap = _compose(fx.build_root(tmp_path, state_doc=state))
    freshness = snap["source"]["freshness"]
    assert freshness["source_age_seconds"] is None
    assert freshness["source_age_basis"] == "unparseable_build_stamp"
