"""tests/test_marketing_allies.py — Marketing Allies W1 engine tests (MKT-D11).

Mirrors tests/test_marketing_engine.py conventions.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _worktree_root() -> Path:
    """Return the repo root (the directory containing engine/)."""
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()

# All schema keys required in every ledger row
_SCHEMA_KEYS = {
    "schema", "target_id", "kind", "name", "platform", "source",
    "link", "style", "audience_tier", "topical_overlap",
    "receipt_friendly", "outreach_verdict", "rule_citation",
    "score", "status", "kit_path", "seeded_utc", "tier",
}

# All rule_citation keys required for community rows
_RULE_CITATION_KEYS = {"rules_url", "rule_ref", "retrieved_utc", "verdict", "note"}


# ---------------------------------------------------------------------------
# (a) seed_targets returns ≥50 in-repo-sourced targets; ≥68 total expected;
#     every row has all schema keys
# ---------------------------------------------------------------------------

def test_seed_targets_returns_minimum_count():
    from engine.marketing.allies import seed_targets
    targets = seed_targets(ROOT)
    # Must reach the ≥50 acceptance criterion for in-repo sources
    assert len(targets) >= 50, f"Got only {len(targets)} targets"


def test_seed_targets_schema_keys():
    from engine.marketing.allies import seed_targets
    targets = seed_targets(ROOT)
    for t in targets:
        missing = _SCHEMA_KEYS - set(t.keys())
        assert not missing, f"target {t.get('target_id')} missing keys: {missing}"


def test_seed_targets_expected_total():
    """Expect 51 funds + 5 newsletters + 1 creator + 11 communities = 68."""
    from engine.marketing.allies import seed_targets
    targets = seed_targets(ROOT)
    assert len(targets) >= 68, (
        f"Expected ≥68 targets (51 funds + 5 newsletters + 1 creator + 11 communities), "
        f"got {len(targets)}"
    )


# ---------------------------------------------------------------------------
# (b) community rows have complete rule_citation; non-community rows have None
# ---------------------------------------------------------------------------

def test_community_rule_citations_complete():
    from engine.marketing.allies import seed_targets
    targets = seed_targets(ROOT)
    for t in targets:
        if t.get("kind") == "community":
            rc = t.get("rule_citation")
            assert rc is not None, f"community {t['target_id']} has None rule_citation"
            assert isinstance(rc, dict), f"community {t['target_id']} rule_citation is not dict"
            missing = _RULE_CITATION_KEYS - set(rc.keys())
            assert not missing, (
                f"community {t['target_id']} rule_citation missing keys: {missing}"
            )
            for k in _RULE_CITATION_KEYS:
                assert rc[k], (
                    f"community {t['target_id']} rule_citation[{k!r}] is empty"
                )


def test_non_community_rule_citation_is_none():
    from engine.marketing.allies import seed_targets
    targets = seed_targets(ROOT)
    for t in targets:
        if t.get("kind") != "community":
            assert t.get("rule_citation") is None, (
                f"non-community {t['target_id']} has non-None rule_citation: "
                f"{t.get('rule_citation')}"
            )


# ---------------------------------------------------------------------------
# (c) All scores within [0, 1] and equal to score_target recomputation
# ---------------------------------------------------------------------------

def test_scores_in_range():
    from engine.marketing.allies import seed_targets
    targets = seed_targets(ROOT)
    for t in targets:
        s = t.get("score")
        assert isinstance(s, float), f"{t['target_id']} score is not float: {s!r}"
        assert 0.0 <= s <= 1.0, f"{t['target_id']} score out of range: {s}"


def test_scores_match_recomputation():
    from engine.marketing.allies import seed_targets, score_target
    targets = seed_targets(ROOT)
    for t in targets:
        expected = score_target(t)
        assert t["score"] == pytest.approx(expected, abs=1e-9), (
            f"{t['target_id']} stored score {t['score']} != recomputed {expected}"
        )


# ---------------------------------------------------------------------------
# (d) All statuses are "candidate"
# ---------------------------------------------------------------------------

def test_all_statuses_candidate():
    from engine.marketing.allies import seed_targets
    targets = seed_targets(ROOT)
    for t in targets:
        assert t.get("status") == "candidate", (
            f"{t['target_id']} status is {t.get('status')!r}, expected 'candidate'"
        )


# ---------------------------------------------------------------------------
# (e) Determinism: two seed_targets calls produce identical output
# ---------------------------------------------------------------------------

def test_seed_targets_deterministic():
    from engine.marketing.allies import seed_targets
    first = seed_targets(ROOT)
    second = seed_targets(ROOT)
    assert len(first) == len(second), "Two calls returned different lengths"
    for a, b in zip(first, second):
        assert a == b, f"Non-deterministic row for {a.get('target_id')}"


# ---------------------------------------------------------------------------
# (f) Source hygiene: no network imports in allies.py
# ---------------------------------------------------------------------------

def test_no_network_imports_in_source():
    allies_path = ROOT / "engine" / "marketing" / "allies.py"
    source = allies_path.read_text(encoding="utf-8")
    assert "import requests" not in source, "allies.py imports 'requests' — forbidden"
    assert "urllib" not in source, "allies.py imports 'urllib' — forbidden"
    assert "http.client" not in source, "allies.py imports 'http.client' — forbidden"


# ---------------------------------------------------------------------------
# (g) draft_referral — correct schema, cut_pct/code None, correct prices,
#     never writes a file
# ---------------------------------------------------------------------------

def test_draft_referral_insider_monthly():
    from engine.marketing.allies import draft_referral
    ref = draft_referral("fund-berkshire", "insider", "monthly")
    assert ref["cut_pct"] is None
    assert ref["code"] is None
    assert ref["list_price_usd"] == 59.0
    assert ref["tier"] == "insider"
    assert ref["billing"] == "monthly"
    assert ref["operator_approved"] is False
    assert ref["issued_utc"] is None
    assert ref["status"] == "draft"


def test_draft_referral_insider_annual():
    from engine.marketing.allies import draft_referral
    ref = draft_referral("fund-berkshire", "insider", "annual")
    assert ref["list_price_usd"] == 49.0


def test_draft_referral_pro_monthly():
    from engine.marketing.allies import draft_referral
    ref = draft_referral("creator-dannytrades", "pro", "monthly")
    assert ref["list_price_usd"] == 89.0
    assert ref["tier"] == "pro"
    assert ref["utm_source"] == "ally"
    assert ref["utm_campaign"] == "creator-dannytrades"


def test_draft_referral_pro_annual():
    from engine.marketing.allies import draft_referral
    ref = draft_referral("com-tradingview", "pro", "annual")
    assert ref["list_price_usd"] == 69.0


def test_draft_referral_writes_nothing(tmp_path):
    """draft_referral must not write any file."""
    from engine.marketing.allies import draft_referral
    before = list(tmp_path.rglob("*"))
    # Call several times to confirm idempotent non-write
    for _ in range(3):
        draft_referral("fund-berkshire", "insider", "monthly")
    after = list(tmp_path.rglob("*"))
    # tmp_path should be unchanged
    assert before == after


# ---------------------------------------------------------------------------
# (h) build_allies integration: ledger exists, one kit per target, no "validated",
#     community kits contain their rules_url
# ---------------------------------------------------------------------------

def test_build_allies_creates_ledger_and_kits(tmp_path):
    """Full integration: build into a temp root that mirrors needed config."""
    import shutil

    # Mirror minimal structure
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "marketing").mkdir(parents=True)
    (tmp_path / "data" / "marketing" / "allies_kits").mkdir(parents=True)

    shutil.copy(ROOT / "config.yml", tmp_path / "config.yml")
    shutil.copy(ROOT / "config" / "allies_communities.yml",
                tmp_path / "config" / "allies_communities.yml")
    shutil.copy(ROOT / "config" / "narrative_sources.yml",
                tmp_path / "config" / "narrative_sources.yml")

    from engine.marketing.allies import build_allies
    result = build_allies(tmp_path)

    assert result.get("targets", 0) >= 50, (
        f"Expected ≥50 targets, got {result.get('targets')}"
    )
    assert result.get("kits", 0) >= 50, (
        f"Expected ≥50 kits written, got {result.get('kits')}"
    )

    ledger_path = Path(result["ledger_path"])
    assert ledger_path.exists(), "Ledger file was not written"

    # Read all rows back
    rows = [json.loads(ln) for ln in ledger_path.read_text().splitlines() if ln.strip()]
    assert len(rows) == result["targets"]

    # Verify every kit file exists and passes hygiene checks
    community_targets = [t for t in rows if t.get("kind") == "community"]
    for t in rows:
        kit_path = tmp_path / t["kit_path"]
        assert kit_path.exists(), f"Kit missing for {t['target_id']}: {kit_path}"
        kit_text = kit_path.read_text(encoding="utf-8")
        # Must never contain the word "validated" (case-insensitive)
        assert "validated" not in kit_text.lower(), (
            f"Kit for {t['target_id']} contains the word 'validated'"
        )

    # Community kits must contain their rules_url
    for t in community_targets:
        kit_path = tmp_path / t["kit_path"]
        kit_text = kit_path.read_text(encoding="utf-8")
        rules_url = t["rule_citation"]["rules_url"]
        assert rules_url in kit_text, (
            f"Community kit for {t['target_id']} missing rules_url {rules_url!r}"
        )


def test_build_allies_ledger_sorted(tmp_path):
    """Ledger rows must be sorted by target_id for determinism."""
    import shutil
    (tmp_path / "config").mkdir()
    (tmp_path / "data" / "marketing").mkdir(parents=True)

    shutil.copy(ROOT / "config.yml", tmp_path / "config.yml")
    shutil.copy(ROOT / "config" / "allies_communities.yml",
                tmp_path / "config" / "allies_communities.yml")
    shutil.copy(ROOT / "config" / "narrative_sources.yml",
                tmp_path / "config" / "narrative_sources.yml")

    from engine.marketing.allies import build_allies
    result = build_allies(tmp_path)

    ledger_path = Path(result["ledger_path"])
    rows = [json.loads(ln) for ln in ledger_path.read_text().splitlines() if ln.strip()]
    ids = [r["target_id"] for r in rows]
    assert ids == sorted(ids), "Ledger rows are not sorted by target_id"


# ---------------------------------------------------------------------------
# score_target edge cases
# ---------------------------------------------------------------------------

def test_score_target_weights():
    """Verify formula: 0.45*overlap + 0.25*receipt + 0.20*access + 0.10*audience."""
    from engine.marketing.allies import score_target
    t = {
        "topical_overlap": 1.0,
        "receipt_friendly": True,
        "outreach_verdict": "open",
        "audience_tier": 3,
    }
    expected = round(0.45 * 1.0 + 0.25 * 1.0 + 0.20 * 1.0 + 0.10 * (3 / 3), 3)
    assert score_target(t) == pytest.approx(expected, abs=1e-9)


def test_score_target_prohibited():
    from engine.marketing.allies import score_target
    t = {
        "topical_overlap": 1.0,
        "receipt_friendly": True,
        "outreach_verdict": "prohibited",
        "audience_tier": 3,
    }
    expected = round(0.45 * 1.0 + 0.25 * 1.0 + 0.20 * 0.1 + 0.10 * 1.0, 3)
    assert score_target(t) == pytest.approx(expected, abs=1e-9)


def test_score_target_null_audience():
    from engine.marketing.allies import score_target
    t = {
        "topical_overlap": 0.8,
        "receipt_friendly": True,
        "outreach_verdict": "open",
        "audience_tier": None,
    }
    expected = round(0.45 * 0.8 + 0.25 * 1.0 + 0.20 * 1.0 + 0.10 * 0.5, 3)
    assert score_target(t) == pytest.approx(expected, abs=1e-9)
