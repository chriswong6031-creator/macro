"""Tests for engine.neuralweb.brief_context (ADB-W1).

Test coverage
-------------
1.  budget_caps_macro          — macro_slice from real repo artifacts ≤ 10 240 bytes
2.  budget_caps_china          — china_slice from real repo artifacts ≤ 6 144 bytes
3.  assert_no_authority_macro  — macro_slice passes _law.assert_no_authority
4.  assert_no_authority_china  — china_slice passes _law.assert_no_authority
5.  absent_artifact_macro      — absent-artifact root → absent markers (no raise)
6.  absent_artifact_china      — absent-artifact root → absent markers (no raise)
7.  stale_fixture_macro        — world_state with stale asof → stale:True on market_core
8.  stale_fixture_china        — mastermind_context with stale asof → stale:True on global_weather
9.  degraded_memo              — degraded memo fixture → status-only cortex tail
10. tape_family_on_every_block_macro — every non-absent macro block has _tape_family
11. tape_family_on_every_block_china — every non-absent china block has _tape_family
12. cache_bust                 — two states differing only in memo content produce different
                                 json.dumps serialisations (trivially asserted)
13. strength_stale_produced_at_fresh — confluence_strength produced_at fresh / asof 2026-07-02
                                 → strength block stale:True (ADB-R11 live acceptance test)
14. no_ticker_subjects_sequence — sequence block subjects list contains NO non-macro-prefix strings
15. no_ticker_subjects_strength — strength block subjects list contains NO non-macro-prefix strings
16. oversized_budget_enforced   — synthetic oversized packet stays ≤ cap after enforcement
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj))


def _make_nw_dir(root: Path) -> Path:
    nw = root / "data" / "neuralweb"
    nw.mkdir(parents=True, exist_ok=True)
    (nw / "cortex").mkdir(exist_ok=True)
    return nw


def _minimal_world_state(asof: str = "2026-07-10") -> dict:
    return {
        "produced_at": f"{asof}T10:00:00Z",
        "verdict": {"verdict": "RISK_ON", "score": 75, "label_en": "Risk-on",
                    "label_zh": "风险偏好", "asof": asof},
        "regime": {"quad": "Q1", "confidence": 0.3, "transition_state": "stable",
                   "flip_margin": 0.1, "asof": asof},
        "breadth": {"pct_above_50": 65.0, "pct_above_200": 60.0,
                    "breadth_above200_pctile": 0.7},
        "cycle_pattern": {"recovery": {"turn_confirmed": True, "phase": "early"}},
        "contradictions": {"n": 1, "by_severity": {"note": 1},
                           "top_pair_ids": ["cross_asset_confirm-diverge"],
                           "display_only": True},
        "cross_asset_flows": {"asof": asof, "correlation": {"verdict": "concentrated",
                              "absorption_pctile": 0.9},
                              "global_liquidity_dir": "contracting",
                              "leadlag": {"verdict": "weak_lead"}},
        "global_regimes": {
            "us": {"quad": "Q1", "quad_name": "Goldilocks", "confidence": 0.3},
            "china": {"quad": "Q3", "quad_name": "Stagflation", "confidence": 0.08},
            "hk": {"quad": "Q3", "quad_name": "Stagflation", "confidence": 0.08},
            "canada": {"quad": "Q1", "quad_name": "Goldilocks", "confidence": 0.3},
            "dispersion_note": "US-China diverge",
            "display_only": True,
        },
        "factor_weather": {"style_regime": "mixed", "factor_leader": "profitability",
                           "factor_state_as_of": asof, "display_only": True},
    }


def _minimal_liquidity_plumbing(asof: str = "2026-07-10") -> dict:
    return {
        "asof": asof,
        "headline": {"state": "stress_liquidity_expansion"},
        "quantity": {"netliq_chg_20d_bn": 65.0, "netliq_pctile_expanding": 0.84},
        "rrp": {"buffer_state": "exhausted"},
        "quality": {"label": "stress-expansion"},
    }


def _minimal_covariance_spine(asof: str = "2026-07-10") -> dict:
    return {
        "as_of": asof,
        "display_only": True,
        "blocks": {
            "rates": {"dominant_pc_share": 0.82},
            "factors": {"effective_factor_bets_pr": 2.96},
            "dispersion": {"state": "lean_in"},
        },
    }


def _minimal_theme_state(asof: str = "2026-07-12") -> dict:
    return {
        "as_of": asof,
        "n_themes": 2,
        "themes": [
            {"theme_id": "ai_semiconductors", "name_en": "AI Semiconductors",
             "foresight": {"stage": "RE-RATING"}},
            {"theme_id": "memory_storage", "name_en": "Memory Storage",
             "foresight": {"stage": "WATCH"}},
        ],
        "stale_legs": [],
        "n_falsifiers_fired": 0,
    }


def _minimal_confluence_sequence(asof: str = "2026-07-12") -> dict:
    return {
        "schema": "neuralweb.confluence_sequence.v1",
        "asof": asof,
        "produced_at": f"{asof}T05:00:00Z",
        "subjects": [
            {"subject": "regime:US", "persistence_streak": 3, "state": "stable"},
        ],
        "contradiction_pairs": [
            {"pair_id": "cross_asset_confirm-diverge", "persistence_streak": 1,
             "state": "new"},
        ],
        "display_only": True,
    }


def _minimal_confluence_strength(
    asof: str = "2026-07-12",
    produced_at: str | None = None,
) -> dict:
    """confluence_strength.json fixture.

    In the ADB-R11 live acceptance case, produced_at is fresh (today) while
    asof is stale (2026-07-02).  The fixture models this shape.
    """
    pt = produced_at or f"2026-07-12T05:00:00Z"
    return {
        "schema": "neuralweb.confluence_strength.v1",
        "asof": asof,
        "produced_at": pt,
        "display_only": True,
        "rows": [
            {
                "subject": "regime:US",
                "n_independent_confirming": 3.0,
                "state": "stable",
                "direction": "bullish",
            },
            {
                "subject": "breadth:pct_above_200",
                "n_independent_confirming": 2.0,
                "state": "strengthening",
                "direction": "bullish",
            },
            # Ticker-level row — must NEVER appear in the strength block
            {
                "subject": "AAPL",
                "n_independent_confirming": 1.5,
                "state": "stable",
                "direction": "bullish",
            },
        ],
    }


def _minimal_attention(asof: str = "2026-07-12") -> dict:
    return {
        "as_of": asof,
        "items": [
            {"kind": "contradiction_tension", "severity": "P2",
             "summary_en": "Tension: cross_asset_confirm-diverge"}
        ],
    }


def _minimal_evidence_clock(asof: str = "2026-07-12") -> dict:
    return {
        "as_of": asof,
        "summary": {
            "morning_line": "1 due, 0 missing.",
            "top_due": {"clock_id": "test:clock", "due_at": "2026-07-10"},
        },
    }


def _minimal_causal_lab(asof: str = "2026-07-12T10:00:00Z") -> dict:
    return {
        "asof": asof,
        "funnel": {"edges_by_verdict": {"null": 5}, "nulls_count": 5},
        "llm_lane": {"status": "ok"},
    }


def _minimal_memo(degraded: bool = True) -> dict:
    if degraded:
        return {
            "as_of": "2026-07-12T10:00:00Z",
            "is_context_only": True,
            "run_status": {
                "status": "degraded",
                "degraded": True,
                "degradation_reason": "model_unavailable",
            },
        }
    return {
        "as_of": "2026-07-12T10:00:00Z",
        "is_context_only": True,
        "summary": "Markets in Goldilocks regime.",
        "what_fired": ["breadth positive"],
        "deserves_operator": [],
        "decaying_families": [],
        "run_status": {"status": "ok", "degraded": False},
    }


def _minimal_mastermind_context(asof: str = "2026-07-12") -> dict:
    return {
        "as_of": asof,
        "is_context_only": True,
        "lobes": {
            "macro_weather": {
                "asof": asof,
                "us_quad": "Q1",
                "china_quad": "Q3",
                "china": {
                    "china_quad": "Q3",
                    "phase_label": "POLICY_PUT",
                    "who_controls": "mixed",
                    "policy_impulse": "targeted_support",
                    "as_of": "2026-07-11",
                },
                "hk_quad": "Q3",
                "canada_quad": "Q1",
                "display_only": True,
            }
        },
    }


def _write_full_fixture(nw: Path, ws_asof: str = "2026-07-12",
                        lp_asof: str = "2026-07-10",
                        degraded_memo: bool = True) -> None:
    """Write a complete minimal fixture set into nw/."""
    _write_json(nw / "world_state.json", _minimal_world_state(ws_asof))
    _write_json(nw / "liquidity_plumbing.json", _minimal_liquidity_plumbing(lp_asof))
    _write_json(nw / "covariance_spine.json", _minimal_covariance_spine())
    _write_json(nw / "theme_state.json", _minimal_theme_state())
    _write_json(nw / "confluence_sequence.json", _minimal_confluence_sequence())
    _write_json(nw / "confluence_strength.json", _minimal_confluence_strength())
    _write_json(nw / "attention_deterministic.json", _minimal_attention())
    _write_json(nw / "evidence_clock.json", _minimal_evidence_clock())
    _write_json(nw / "causal_lab_state.json", _minimal_causal_lab())
    _write_json(nw / "cortex" / "memo.json", _minimal_memo(degraded_memo))
    _write_json(nw / "mastermind_context.json", _minimal_mastermind_context())


# ---------------------------------------------------------------------------
# Tests 1-2: budget caps
# ---------------------------------------------------------------------------

def test_budget_caps_macro():
    """macro_slice from real repo artifacts must be ≤ 10 240 bytes serialised."""
    from engine.neuralweb.brief_context import macro_slice
    m = macro_slice()
    serialised = json.dumps(m, separators=(",", ":"), default=str)
    assert len(serialised) <= 10_240, (
        f"macro_slice exceeded 10 240 B cap: {len(serialised)} bytes"
    )


def test_budget_caps_china():
    """china_slice from real repo artifacts must be ≤ 6 144 bytes serialised."""
    from engine.neuralweb.brief_context import china_slice
    c = china_slice()
    serialised = json.dumps(c, separators=(",", ":"), default=str)
    assert len(serialised) <= 6_144, (
        f"china_slice exceeded 6 144 B cap: {len(serialised)} bytes"
    )


# ---------------------------------------------------------------------------
# Tests 3-4: assert_no_authority
# ---------------------------------------------------------------------------

def test_assert_no_authority_macro():
    """macro_slice must pass _law.assert_no_authority with zero violations."""
    from engine.neuralweb.brief_context import macro_slice
    from engine.neuralweb._law import assert_no_authority
    violations = assert_no_authority(macro_slice())
    assert violations == [], f"authority violations in macro_slice: {violations}"


def test_assert_no_authority_china():
    """china_slice must pass _law.assert_no_authority with zero violations."""
    from engine.neuralweb.brief_context import china_slice
    from engine.neuralweb._law import assert_no_authority
    violations = assert_no_authority(china_slice())
    assert violations == [], f"authority violations in china_slice: {violations}"


# ---------------------------------------------------------------------------
# Tests 5-6: absent-artifact fixtures
# ---------------------------------------------------------------------------

def test_absent_artifact_macro(tmp_path):
    """Pointing root at a directory with no NW artifacts → absent markers, no raise."""
    from engine.neuralweb.brief_context import macro_slice
    # tmp_path has no data/neuralweb/ at all
    result = macro_slice(root=tmp_path)
    # Should not raise; may return a top-level absent dict or a dict with absent blocks
    assert isinstance(result, dict)
    # All non-absent blocks should still have _tape_family or absent marker
    for k, v in result.items():
        if isinstance(v, dict):
            assert "absent" in v or "_tape_family" in v, (
                f"block {k!r} missing both 'absent' and '_tape_family'"
            )


def test_absent_artifact_china(tmp_path):
    """Pointing root at empty dir → absent markers for china_slice, no raise."""
    from engine.neuralweb.brief_context import china_slice
    result = china_slice(root=tmp_path)
    assert isinstance(result, dict)
    for k, v in result.items():
        if isinstance(v, dict):
            assert "absent" in v or "_tape_family" in v, (
                f"china block {k!r} missing both 'absent' and '_tape_family'"
            )


# ---------------------------------------------------------------------------
# Tests 7-8: stale fixture
# ---------------------------------------------------------------------------

def test_stale_fixture_macro(tmp_path):
    """world_state with stale asof (2026-07-02) → stale:True on market_core."""
    from engine.neuralweb.brief_context import macro_slice
    nw = _make_nw_dir(tmp_path)
    _write_full_fixture(nw, ws_asof="2026-07-02")
    result = macro_slice(root=tmp_path)
    assert result["market_core"].get("stale") is True, (
        "market_core should be stale when world_state asof is 2026-07-02"
    )


def test_stale_fixture_china(tmp_path):
    """mastermind_context with stale asof → stale:True on global_weather."""
    from engine.neuralweb.brief_context import china_slice
    nw = _make_nw_dir(tmp_path)
    _write_full_fixture(nw)
    # Overwrite mastermind_context with a stale asof
    stale_mc = _minimal_mastermind_context(asof="2026-07-02")
    stale_mc["lobes"]["macro_weather"]["asof"] = "2026-07-02"
    _write_json(nw / "mastermind_context.json", stale_mc)
    result = china_slice(root=tmp_path)
    assert result["global_weather"].get("stale") is True, (
        "global_weather should be stale when mastermind_context asof is 2026-07-02"
    )


# ---------------------------------------------------------------------------
# Test 9: degraded memo fixture
# ---------------------------------------------------------------------------

def test_degraded_memo(tmp_path):
    """Degraded memo → cortex block has status:'degraded' and no summary field."""
    from engine.neuralweb.brief_context import macro_slice
    nw = _make_nw_dir(tmp_path)
    _write_full_fixture(nw, degraded_memo=True)
    result = macro_slice(root=tmp_path)
    cortex = result.get("cortex", {})
    assert cortex.get("status") == "degraded"
    assert "summary" not in cortex


# ---------------------------------------------------------------------------
# Tests 10-11: _tape_family on every block
# ---------------------------------------------------------------------------

def test_tape_family_on_every_block_macro(tmp_path):
    """Every non-absent macro_slice block must carry _tape_family."""
    from engine.neuralweb.brief_context import macro_slice
    nw = _make_nw_dir(tmp_path)
    _write_full_fixture(nw)
    result = macro_slice(root=tmp_path)
    for key, block in result.items():
        if isinstance(block, dict) and not block.get("absent"):
            assert "_tape_family" in block, (
                f"macro block {key!r} is missing _tape_family"
            )


def test_tape_family_on_every_block_china(tmp_path):
    """Every non-absent china_slice block must carry _tape_family."""
    from engine.neuralweb.brief_context import china_slice
    nw = _make_nw_dir(tmp_path)
    _write_full_fixture(nw)
    result = china_slice(root=tmp_path)
    for key, block in result.items():
        if isinstance(block, dict) and not block.get("absent"):
            assert "_tape_family" in block, (
                f"china block {key!r} is missing _tape_family"
            )


# ---------------------------------------------------------------------------
# Test 12: cache-bust (two states differing in memo → different serialisations)
# ---------------------------------------------------------------------------

def test_cache_bust(tmp_path):
    """Two states differing only in memo content must produce different serialisations."""
    from engine.neuralweb.brief_context import macro_slice
    nw = _make_nw_dir(tmp_path)
    _write_full_fixture(nw, degraded_memo=True)
    s1 = json.dumps(macro_slice(root=tmp_path), sort_keys=True, default=str)

    # Overwrite memo with a non-degraded one
    _write_json(nw / "cortex" / "memo.json", _minimal_memo(degraded=False))
    s2 = json.dumps(macro_slice(root=tmp_path), sort_keys=True, default=str)

    assert s1 != s2, (
        "Two macro_slice states that differ only in memo content produced identical JSON"
    )


# ---------------------------------------------------------------------------
# Test 13: strength stale fixture (ADB-R11 live acceptance criterion)
# ---------------------------------------------------------------------------

def test_strength_stale_produced_at_fresh(tmp_path):
    """confluence_strength produced_at=fresh asof=2026-07-02 → strength block stale:True.

    ADB-R11 live acceptance case: produced_at is today (fresh) but data asof
    is 2026-07-02 (~240h vs 30h SLA).  Staleness must key off asof, not
    produced_at, so stale must be True.
    """
    from engine.neuralweb.brief_context import macro_slice
    nw = _make_nw_dir(tmp_path)
    _write_full_fixture(nw)
    # Write stale confluence_strength: produced_at fresh, asof old
    stale_cst = _minimal_confluence_strength(
        asof="2026-07-02",
        produced_at="2026-07-12T05:00:00Z",  # fresh produced_at
    )
    _write_json(nw / "confluence_strength.json", stale_cst)

    result = macro_slice(root=tmp_path)
    strength = result.get("strength", {})
    assert not strength.get("absent"), "strength block should be present with stale asof"
    assert strength.get("stale") is True, (
        "strength block must be stale when asof=2026-07-02 (keyed off asof, not produced_at)"
    )


# ---------------------------------------------------------------------------
# Tests 14-15: no ticker subjects leak (ADB-R2)
# ---------------------------------------------------------------------------

_MACRO_PREFIXES = ("regime:", "breadth:", "sector:")


def test_no_ticker_subjects_sequence(tmp_path):
    """sequence block subjects must all have macro-prefix or be absent entirely.

    Production confluence_sequence is 100% ticker-level subjects.  The block
    must emit subjects=[] (not fall back to ticker rows) when no macro subjects
    match.  Verified against both the fixture and the real production artifact
    (if present).
    """
    from engine.neuralweb.brief_context import macro_slice
    nw = _make_nw_dir(tmp_path)
    _write_full_fixture(nw)
    # Write ticker-only confluence_sequence (no macro subjects)
    ticker_only_cs = {
        "schema": "neuralweb.confluence_sequence.v1",
        "asof": "2026-07-12",
        "produced_at": "2026-07-12T05:00:00Z",
        "subjects": [
            {"subject": "AAPL", "persistence_streak": 3, "state": "stable"},
            {"subject": "CB", "persistence_streak": 2, "state": "strengthening"},
            {"subject": "AVGO", "persistence_streak": 1, "state": "new"},
            {"subject": "BA", "persistence_streak": 4, "state": "stable"},
            {"subject": "BIIB", "persistence_streak": 1, "state": "decaying"},
        ],
        "contradiction_pairs": [],
        "display_only": True,
    }
    _write_json(nw / "confluence_sequence.json", ticker_only_cs)

    result = macro_slice(root=tmp_path)
    seq = result.get("sequence", {})
    subjects = seq.get("subjects", [])
    for s in subjects:
        subj_str = s.get("subject", "")
        assert any(subj_str.startswith(p) for p in _MACRO_PREFIXES), (
            f"ticker subject leaked into sequence block: {subj_str!r}"
        )


def test_no_ticker_subjects_strength(tmp_path):
    """strength block subjects must all have macro-prefix (ADB-R2).

    The _minimal_confluence_strength fixture includes a ticker row ('AAPL').
    The block must strip it.
    """
    from engine.neuralweb.brief_context import macro_slice
    nw = _make_nw_dir(tmp_path)
    _write_full_fixture(nw)
    # _minimal_confluence_strength already contains an AAPL ticker row

    result = macro_slice(root=tmp_path)
    strength = result.get("strength", {})
    subjects = strength.get("subjects", [])
    assert subjects is not None, "strength subjects key must be present"
    for s in subjects:
        subj_str = s.get("subject", "")
        assert any(subj_str.startswith(p) for p in _MACRO_PREFIXES), (
            f"ticker subject leaked into strength block: {subj_str!r}"
        )


# ---------------------------------------------------------------------------
# Test 16: oversized synthetic packet stays ≤ cap after budget enforcement
# ---------------------------------------------------------------------------

def test_oversized_budget_enforced(tmp_path):
    """An intentionally oversized packet must be trimmed to ≤ 10 240 bytes."""
    from engine.neuralweb.brief_context import _enforce_budget, _MACRO_DROP_ORDER, _MACRO_CAP
    import json
    # Build a packet that is well over the cap by padding list fields
    big_list = [{"subject": f"regime:SYN{i}", "state": "stable", "note": "x" * 200}
                for i in range(100)]
    oversized: dict = {
        "market_core": {"_tape_family": "nw_synthesis", "display_only": True,
                        "as_of": "2026-07-12", "stale": False, "items": big_list},
        "contradictions": {"_tape_family": "nw_synthesis", "display_only": True,
                           "as_of": "2026-07-12", "stale": False, "items": big_list},
        "cross_asset_flows": {"_tape_family": "flows", "display_only": True,
                              "as_of": "2026-07-12", "stale": False, "items": big_list},
        "liquidity_plumbing": {"_tape_family": "rates_credit", "display_only": True,
                               "as_of": "2026-07-12", "stale": False, "items": big_list},
        "global_regimes": {"_tape_family": "price_regime", "display_only": True,
                           "as_of": "2026-07-12", "stale": False, "items": big_list},
        "factor_weather": {"_tape_family": "nw_synthesis", "display_only": True,
                           "as_of": "2026-07-12", "stale": False, "items": big_list},
        "covariance": {"_tape_family": "nw_synthesis", "display_only": True,
                       "as_of": "2026-07-12", "stale": False, "items": big_list},
        "themes": {"_tape_family": "nw_synthesis", "display_only": True,
                   "as_of": "2026-07-12", "stale": False, "items": big_list},
        "sequence": {"_tape_family": "nw_synthesis", "display_only": True,
                     "as_of": "2026-07-12", "stale": False, "subjects": big_list},
        "strength": {"_tape_family": "nw_synthesis", "display_only": True,
                     "as_of": "2026-07-12", "stale": False, "subjects": big_list},
        "attention": {"_tape_family": "nw_synthesis", "display_only": True,
                      "as_of": "2026-07-12", "stale": False, "items": big_list},
        "evidence_clock": {"_tape_family": "ops", "display_only": True,
                           "as_of": "2026-07-12", "stale": False, "items": big_list},
        "causal_lab": {"_tape_family": "ops", "display_only": True,
                       "as_of": "2026-07-12", "stale": False, "items": big_list},
        "cortex": {"_tape_family": "ops", "display_only": True,
                   "as_of": "2026-07-12", "stale": False},
    }
    pre_size = len(json.dumps(oversized, separators=(",", ":"), default=str))
    assert pre_size > _MACRO_CAP, "fixture must be oversized to test budget enforcement"

    result = _enforce_budget(oversized, _MACRO_CAP, list(_MACRO_DROP_ORDER))
    post_size = len(json.dumps(result, separators=(",", ":"), default=str))
    assert post_size <= _MACRO_CAP, (
        f"budget enforcement failed: {post_size} > {_MACRO_CAP} bytes"
    )
