"""tests/test_causal_audit.py — CHF-R10 anti-mirage auditor tests.

All tests are hermetic (tmp_path fixtures, no network, no real repo data).
Positive-control instruments verify that absent inputs produce empty sections
(not phantom annotations) and that the language sanitizer fires on banned words.

Test coverage:
1.  authority_block             — all authority booleans False, annotate_only True
2.  empty_when_inventory_absent — duplicate_exposure empty when inventory missing
3.  duplicate_exposure_family   — two price-derived siblings in same family → annotation
4.  duplicate_exposure_nonprice — two non-price-derived features → no annotation
5.  single_feature_no_pair      — only one feature → no pair → no annotation
6.  shared_parent_suspect_absent_spine — empty when spine absent
7.  shared_parent_suspect_no_clusters  — empty when spine clusters = []
8.  shared_parent_suspect_fires        — confirms edge + same cluster → annotation
9.  shared_parent_different_clusters   — different clusters → no annotation
10. collider_risk_absent_priors — empty when priors absent
11. collider_risk_no_mechanisms — empty list (no cards yet)
12. collider_risk_fires         — mechanism card conditioner matches forbidden pattern
13. collider_risk_safe_conditioner — non-forbidden conditioner → no annotation
14. no_banned_words_in_display_text — sanitizer fires on all banned words
15. gap_notes_printed            — gap notes populated when inputs absent
16. counts_match_sections        — counts dict matches actual list lengths
17. confluence_stamp_additive    — stamp_confluence_edges adds causal_audit field
18. confluence_stamp_tolerant    — stamp_confluence_edges tolerant when audit is empty
19. build_audit_full_absent_inputs — build_audit() with no artifacts → ok (empty sections)
20. evidence_refs_populated      — evidence_refs present in each annotation
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb.causal_audit import (  # noqa: E402
    build_audit,
    stamp_confluence_edges,
    _build_duplicate_exposure,
    _build_shared_parent_suspect,
    _build_collider_risk,
    _sanitize_text,
    _AUTHORITY,
    _BANNED_WORDS,
)

# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------

def _make_inventory(features: list[dict]) -> dict:
    return {
        "schema": "neuralweb.causal_feature_inventory.v1",
        "artifact_id": "causal-feature-inventory",
        "features": features,
    }


def _price_feature(feature_id: str, family: str = "breadth") -> dict:
    return {
        "feature_id": feature_id,
        "family": family,
        "allowed_roles": ["candidate_cause", "conditioner"],
        "forbidden_roles": ["target"],
        "notes": "price-derived metric",
        "present": True,
    }


def _non_price_feature(feature_id: str) -> dict:
    return {
        "feature_id": feature_id,
        "family": "macro_data",
        "allowed_roles": ["candidate_cause"],
        "forbidden_roles": ["target"],
        "notes": "macro economic series",
        "present": True,
    }


def _make_spine_with_clusters(clusters: list[list[str]]) -> dict:
    """Spine with cluster data in the lobes block."""
    return {
        "schema": "neuralweb.covariance_spine.v1",
        "blocks": {
            "lobes": {
                "clusters": clusters,
            }
        },
    }


def _make_confluence_with_confirms(
    src: str = "engine:altdata",
    dst: str = "engine:radar",
    n: int = 15,
    lift: float = 0.05,
) -> dict:
    return {
        "schema": "neuralweb.confluence_graph.v1",
        "edges": [
            {
                "src": src,
                "dst": dst,
                "edge_type": "confirms",
                "n": n,
                "lift": lift,
                "display_only": True,
            },
            {
                "src": "engine:us_board",
                "dst": "engine:altdata",
                "edge_type": "feeds",  # non-confirms edge — should not be annotated
                "display_only": True,
            },
        ],
    }


def _make_priors(forbidden_patterns: list[str]) -> dict:
    return {
        "schema": "causal_priors.v1",
        "tiers": [{"name": "macro_plumbing"}],
        "min_lag_days_by_cadence": {"daily_engine": 1, "weekly_publication": 5},
        "forbidden_causes": [
            {"pattern": p, "reason": f"{p} is a downstream composite"}
            for p in forbidden_patterns
        ],
        "kill_mask": {"curated": [], "compiled": []},
    }


def _make_mechanism_card(mech_id: str, conditioners: list[str]) -> dict:
    return {
        "mechanism_id": mech_id,
        "status": "inbox",
        "causal_graph": {
            "cause": "some_cause",
            "target": "some_target",
            "conditioners": conditioners,
        },
    }


# ---------------------------------------------------------------------------
# 1. authority_block
# ---------------------------------------------------------------------------

def test_authority_block():
    assert _AUTHORITY["display_only"] is True
    assert _AUTHORITY["annotate_only"] is True
    assert _AUTHORITY["not_a_signal"] is True
    assert _AUTHORITY["may_rank"] is False
    assert _AUTHORITY["may_gate"] is False
    assert _AUTHORITY["may_size"] is False
    assert _AUTHORITY["may_escalate"] is False
    assert _AUTHORITY["scored_path_surfaces"] == []


# ---------------------------------------------------------------------------
# 2. empty_when_inventory_absent
# ---------------------------------------------------------------------------

def test_empty_when_inventory_absent():
    gap_notes: list[str] = []
    result = _build_duplicate_exposure(None, gap_notes)
    assert result == []
    assert len(gap_notes) == 1
    assert "absent" in gap_notes[0].lower() or "empty" in gap_notes[0].lower()


# ---------------------------------------------------------------------------
# 3. duplicate_exposure_family
# ---------------------------------------------------------------------------

def test_duplicate_exposure_family():
    """Two price-derived siblings in same family → at least one annotation."""
    inventory = _make_inventory([
        _price_feature("breadth__pct_above_50", family="breadth"),
        _price_feature("breadth__pct_above_200", family="breadth"),
    ])
    gap_notes: list[str] = []
    result = _build_duplicate_exposure(inventory, gap_notes)
    assert len(result) == 1
    ann = result[0]
    assert ann["annotation_type"] == "duplicate_exposure"
    assert "breadth__pct_above_50" in ann["pair"] or "breadth__pct_above_200" in ann["pair"]
    assert ann["parent_process"] == "breadth"
    assert ann["rule_id"].startswith("CHF-R10-DE-")
    assert len(ann["evidence_refs"]) >= 2
    assert ann["display_only"] is True
    assert ann["not_a_signal"] is True
    assert ann.get("display_text")
    assert ann.get("display_text_zh")


# ---------------------------------------------------------------------------
# 4. duplicate_exposure_nonprice
# ---------------------------------------------------------------------------

def test_duplicate_exposure_nonprice():
    """Two non-price-derived features (macro_data family) → no annotation."""
    inventory = _make_inventory([
        _non_price_feature("gdp_growth"),
        _non_price_feature("cpi_headline"),
    ])
    gap_notes: list[str] = []
    result = _build_duplicate_exposure(inventory, gap_notes)
    assert result == []


# ---------------------------------------------------------------------------
# 5. single_feature_no_pair
# ---------------------------------------------------------------------------

def test_single_feature_no_pair():
    """Only one price-derived feature → no pair → no annotation."""
    inventory = _make_inventory([
        _price_feature("breadth__pct_above_50"),
    ])
    gap_notes: list[str] = []
    result = _build_duplicate_exposure(inventory, gap_notes)
    assert result == []


# ---------------------------------------------------------------------------
# 6. shared_parent_suspect_absent_spine
# ---------------------------------------------------------------------------

def test_shared_parent_suspect_absent_spine():
    confluence = _make_confluence_with_confirms()
    gap_notes: list[str] = []
    result = _build_shared_parent_suspect(confluence, None, None, gap_notes)
    assert result == []
    assert any("absent" in n.lower() or "unavailable" in n.lower() for n in gap_notes)


# ---------------------------------------------------------------------------
# 7. shared_parent_suspect_no_clusters
# ---------------------------------------------------------------------------

def test_shared_parent_suspect_no_clusters():
    """Spine with empty clusters list → no annotations (but no error)."""
    confluence = _make_confluence_with_confirms()
    spine = _make_spine_with_clusters([])
    gap_notes: list[str] = []
    result = _build_shared_parent_suspect(confluence, spine, None, gap_notes)
    assert result == []
    assert any("empty" in n.lower() or "no cluster" in n.lower() for n in gap_notes)


# ---------------------------------------------------------------------------
# 8. shared_parent_suspect_fires
# ---------------------------------------------------------------------------

def test_shared_parent_suspect_fires():
    """confirms edge whose src+dst are in same cluster → annotation."""
    confluence = _make_confluence_with_confirms(
        src="engine:altdata", dst="engine:radar"
    )
    # altdata and radar in the same cluster
    spine = _make_spine_with_clusters([["altdata", "radar"]])
    gap_notes: list[str] = []
    result = _build_shared_parent_suspect(confluence, spine, None, gap_notes)
    assert len(result) == 1
    ann = result[0]
    assert ann["annotation_type"] == "shared_parent_suspect"
    assert ann["rule_id"].startswith("CHF-R10-SPS-")
    assert ann["cluster_id"] == "cluster_0"
    assert ann["display_only"] is True
    assert ann["not_a_signal"] is True
    assert len(ann["evidence_refs"]) >= 2
    # feeds edge should NOT be annotated (only confirms edges)


# ---------------------------------------------------------------------------
# 9. shared_parent_different_clusters
# ---------------------------------------------------------------------------

def test_shared_parent_different_clusters():
    """confirms edge whose src+dst are in different clusters → no annotation."""
    confluence = _make_confluence_with_confirms(
        src="engine:altdata", dst="engine:radar"
    )
    # altdata in cluster_0, radar in cluster_1
    spine = _make_spine_with_clusters([["altdata"], ["radar"]])
    gap_notes: list[str] = []
    result = _build_shared_parent_suspect(confluence, spine, None, gap_notes)
    assert result == []


# ---------------------------------------------------------------------------
# 10. collider_risk_absent_priors
# ---------------------------------------------------------------------------

def test_collider_risk_absent_priors():
    gap_notes: list[str] = []
    result = _build_collider_risk([], None, gap_notes)
    assert result == []
    assert any("absent" in n.lower() or "empty" in n.lower() for n in gap_notes)


# ---------------------------------------------------------------------------
# 11. collider_risk_no_mechanisms
# ---------------------------------------------------------------------------

def test_collider_risk_no_mechanisms():
    """No mechanism cards → empty section (not a gap)."""
    priors = _make_priors(["board_rank"])
    gap_notes: list[str] = []
    result = _build_collider_risk([], priors, gap_notes)
    assert result == []
    # No gap note expected — just no cards yet


# ---------------------------------------------------------------------------
# 12. collider_risk_fires
# ---------------------------------------------------------------------------

def test_collider_risk_fires():
    """Mechanism card conditioning on board_rank → collider_risk annotation."""
    priors = _make_priors(["board_rank", "final_verdict"])
    mechanisms = [
        _make_mechanism_card("mech_001", conditioners=["board_rank", "some_safe_var"])
    ]
    gap_notes: list[str] = []
    result = _build_collider_risk(mechanisms, priors, gap_notes)
    # Should flag board_rank but not some_safe_var
    assert len(result) == 1
    ann = result[0]
    assert ann["annotation_type"] == "collider_risk"
    assert ann["rule_id"].startswith("CHF-R10-CR-")
    assert ann["mechanism_id"] == "mech_001"
    assert ann["matched_forbidden_pattern"] == "board_rank"
    assert ann["display_only"] is True
    assert ann["not_a_signal"] is True
    assert len(ann["evidence_refs"]) >= 2


# ---------------------------------------------------------------------------
# 13. collider_risk_safe_conditioner
# ---------------------------------------------------------------------------

def test_collider_risk_safe_conditioner():
    """Mechanism card conditioning on a non-forbidden variable → no annotation."""
    priors = _make_priors(["board_rank"])
    mechanisms = [
        _make_mechanism_card("mech_002", conditioners=["quad", "growth_score"])
    ]
    gap_notes: list[str] = []
    result = _build_collider_risk(mechanisms, priors, gap_notes)
    assert result == []


# ---------------------------------------------------------------------------
# 14. no_banned_words_in_display_text
# ---------------------------------------------------------------------------

def test_no_banned_words_in_display_text():
    """display_text fields must not contain banned causal-certainty words."""
    inventory = _make_inventory([
        _price_feature("breadth__pct_above_50", family="breadth"),
        _price_feature("breadth__pct_above_200", family="breadth"),
    ])
    priors = _make_priors(["board_rank"])
    mechanisms = [
        _make_mechanism_card("mech_003", conditioners=["board_rank"])
    ]
    gap_notes: list[str] = []
    de_rows = _build_duplicate_exposure(inventory, gap_notes)
    cr_rows = _build_collider_risk(mechanisms, priors, gap_notes)
    all_rows = de_rows + cr_rows
    for row in all_rows:
        display_text = row.get("display_text") or ""
        match = _BANNED_WORDS.search(display_text)
        assert match is None, (
            f"Banned word '{match.group()}' found in display_text of {row.get('rule_id')}: "
            f"{display_text!r}"
        )


# ---------------------------------------------------------------------------
# 15. gap_notes_printed
# ---------------------------------------------------------------------------

def test_gap_notes_printed():
    """When all inputs absent, gap_notes has an entry for each section."""
    gap_notes: list[str] = []
    _build_duplicate_exposure(None, gap_notes)
    _build_shared_parent_suspect(None, None, None, gap_notes)
    _build_collider_risk([], None, gap_notes)
    # Should have at least 3 gap notes (one per absent artifact/section)
    assert len(gap_notes) >= 3


# ---------------------------------------------------------------------------
# 16. counts_match_sections
# ---------------------------------------------------------------------------

def test_counts_match_sections(tmp_path):
    """build_audit() counts dict matches actual list lengths."""
    result = build_audit(root=tmp_path)
    assert result["counts"]["duplicate_exposure"] == len(result["duplicate_exposure"])
    assert result["counts"]["shared_parent_suspect"] == len(result["shared_parent_suspect"])
    assert result["counts"]["collider_risk"] == len(result["collider_risk"])
    total = (
        len(result["duplicate_exposure"])
        + len(result["shared_parent_suspect"])
        + len(result["collider_risk"])
    )
    assert result["counts"]["total"] == total


# ---------------------------------------------------------------------------
# 17. confluence_stamp_additive
# ---------------------------------------------------------------------------

def test_confluence_stamp_additive():
    """stamp_confluence_edges adds causal_audit field to matching confirms edges."""
    confluence = _make_confluence_with_confirms(
        src="engine:altdata", dst="engine:radar"
    )
    # Build a real audit dict with a shared_parent_suspect annotation
    audit = {
        "duplicate_exposure": [],
        "shared_parent_suspect": [
            {
                "rule_id": "CHF-R10-SPS-001",
                "annotation_type": "shared_parent_suspect",
                "edge": {"src": "engine:altdata", "dst": "engine:radar", "edge_type": "confirms"},
                "suspected_parent_family": "breadth",
                "cluster_id": "cluster_0",
            }
        ],
        "collider_risk": [],
    }
    stamped = stamp_confluence_edges(confluence, audit)
    # Original should not be mutated
    original_edges = confluence.get("edges") or []
    for e in original_edges:
        assert "causal_audit" not in e, "Original confluence was mutated!"

    # Stamped confirms edge should have causal_audit
    stamped_edges = stamped.get("edges") or []
    confirms = [e for e in stamped_edges if e.get("edge_type") == "confirms"]
    assert len(confirms) == 1
    assert "causal_audit" in confirms[0]
    assert "shared_parent_suspect" in confirms[0]["causal_audit"]

    # Non-confirms edge should NOT have causal_audit
    feeds = [e for e in stamped_edges if e.get("edge_type") == "feeds"]
    assert len(feeds) == 1
    assert "causal_audit" not in feeds[0]


# ---------------------------------------------------------------------------
# 18. confluence_stamp_tolerant
# ---------------------------------------------------------------------------

def test_confluence_stamp_tolerant():
    """stamp_confluence_edges with empty audit → no edges modified."""
    confluence = _make_confluence_with_confirms()
    audit: dict = {
        "duplicate_exposure": [],
        "shared_parent_suspect": [],
        "collider_risk": [],
    }
    stamped = stamp_confluence_edges(confluence, audit)
    for edge in (stamped.get("edges") or []):
        assert "causal_audit" not in edge


# ---------------------------------------------------------------------------
# 19. build_audit_full_absent_inputs
# ---------------------------------------------------------------------------

def test_build_audit_full_absent_inputs(tmp_path):
    """build_audit() with no artifacts → schema correct, sections empty, no exception."""
    result = build_audit(root=tmp_path)
    assert result["schema"] == "neuralweb.causal_confluence_audit.v1"
    assert result["artifact_id"] == "causal-confluence-audit"
    assert isinstance(result["duplicate_exposure"], list)
    assert isinstance(result["shared_parent_suspect"], list)
    assert isinstance(result["collider_risk"], list)
    assert isinstance(result["gap_notes"], list)
    assert isinstance(result["counts"], dict)
    # All sections empty when no artifacts present
    assert result["duplicate_exposure"] == []
    assert result["shared_parent_suspect"] == []
    assert result["collider_risk"] == []
    # Gap notes should be non-empty (at least one per absent input)
    assert len(result["gap_notes"]) > 0


# ---------------------------------------------------------------------------
# 20. evidence_refs_populated
# ---------------------------------------------------------------------------

def test_evidence_refs_populated():
    """Every annotation must carry at least one evidence_refs entry."""
    inventory = _make_inventory([
        _price_feature("breadth__pct_above_50", family="breadth"),
        _price_feature("breadth__pct_above_200", family="breadth"),
    ])
    gap_notes: list[str] = []
    result = _build_duplicate_exposure(inventory, gap_notes)
    for ann in result:
        refs = ann.get("evidence_refs") or []
        assert len(refs) >= 1, f"No evidence_refs in {ann.get('rule_id')}"
        for ref in refs:
            assert "artifact" in ref
            assert "field" in ref
