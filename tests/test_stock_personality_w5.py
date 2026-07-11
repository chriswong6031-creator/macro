"""Tests for W5 Oracle personality_context + NW world_state sub-block + spine adapter.

All tests are hermetic: synthetic in-memory fixtures, tmp_path I/O only,
no real market data loaded from disk.

Test coverage:
1.  personality_context_fabricated        — shares + coverage correct for synthetic complex
2.  personality_context_absent_agg        — absent aggregate ⇒ field absent on complex
3.  personality_context_zero_cov          — complex with no matched tickers ⇒ zero coverage block
4.  personality_context_top3              — top3 shares sum <= 1, descending order
5.  personality_context_tinderbox         — tinderbox_share computed correctly
6.  personality_context_event_ovr         — event_override_share computed correctly
7.  personality_context_confidence        — confidence_class always "descriptive"
8.  oracle_payload_valid_with_ctx         — validate_payload passes with personality_context
9.  oracle_payload_valid_without_ctx      — validate_payload passes with no personality_context
10. world_state_sp_summary_present        — stock_personality_summary block in world_state
11. world_state_sp_summary_absent         — absent aggregate ⇒ {"available": False}, no crash
12. world_state_sp_summary_keys           — correct keys when aggregate present
13. adapter_join_rows                     — adapt_personality_context emits rows by ticker
14. adapter_absent_aggregate              — absent aggregate ⇒ zero rows + gap note
15. payload_version_bumped                — PAYLOAD_VERSION now >= 1.2.0 (B1 member roll-up)
16. personality_as_of_present_fresh       — fresh aggregate ⇒ personality_as_of emitted
17. personality_stale_gate_omits_field    — stale aggregate ⇒ personality_context absent
18. personality_as_of_matches_aggregate   — personality_as_of matches aggregate.as_of
19. world_state_stale_gate_returns_null   — stale agg in world_state ⇒ available=false/stale
20. coverage_honesty_nondict_record       — non-dict per_ticker record excluded from coverage
21. share_denominators_field_emitted      — share_denominators present in output block
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# 1–7  personality_context unit tests
# ---------------------------------------------------------------------------

from engine.oracle.personality_context import (
    compute_personality_context_for_complex,
    append_personality_context,
)


def _make_complex_def(cid: str, members: list[str]) -> dict:
    return {"id": cid, "name": cid, "members": members}


def _make_per_ticker(ticker: str, arch: str | None = None,
                     chart: list | None = None, own: list | None = None,
                     modes: list | None = None) -> dict:
    return {
        "arch": arch,
        "dna": None,
        "chart": chart or [],
        "own": own or [],
        "micro": [],
        "modes": modes or ["normal"],
    }


# Theme-ticker map: node_a → [AAPL, MSFT], node_b → [GOOG]
_THEME_MAP = {
    "node_a": ["AAPL", "MSFT"],
    "node_b": ["GOOG"],
    "node_c": ["NFLX"],
}

_PER_TICKER = {
    "AAPL": _make_per_ticker("AAPL", arch="quality_compounder",
                             chart=["smooth_compounder_grind", "stair_step_leader"],
                             own=["passive_index_magnet"]),
    "MSFT": _make_per_ticker("MSFT", arch="quality_compounder",
                             chart=["smooth_compounder_grind"],
                             own=["passive_index_magnet"]),
    "GOOG": _make_per_ticker("GOOG", arch="secular_growth",
                             chart=["volatile_momentum_vehicle"],
                             own=["short_interest_tinderbox"],
                             modes=["event_override"]),
    "NFLX": _make_per_ticker("NFLX", arch="high_beta_momentum",
                             chart=["volatile_momentum_vehicle"],
                             own=[],
                             modes=["accumulation"]),
}


def test_personality_context_fabricated():
    """Correct archetype shares for a complex with known members."""
    cdef = _make_complex_def("test_complex", ["node_a", "node_b"])
    ctx = compute_personality_context_for_complex(cdef, _PER_TICKER, _THEME_MAP)
    assert ctx is not None
    # AAPL=quality_compounder, MSFT=quality_compounder, GOOG=secular_growth
    # archetype top = quality_compounder (2/3), secular_growth (1/3)
    archetypes = dict(ctx["dominant_member_archetypes"])
    assert "quality_compounder" in archetypes
    assert abs(archetypes["quality_compounder"] - 2 / 3) < 0.01
    # member_coverage: node_a (AAPL,MSFT present) + node_b (GOOG present) = 2/2
    assert ctx["member_coverage"] == 1.0


def test_personality_context_absent_agg(tmp_path):
    """Absent site aggregate ⇒ personality_context field NOT present on complex."""
    complexes = [{"id": "ai_compute", "name": "AI Compute", "state": "quiet"}]
    complexes_def = [_make_complex_def("ai_compute", ["node_a"])]
    result = append_personality_context(
        complexes, complexes_def, repo=tmp_path, site_aggregate=None
    )
    assert "personality_context" not in result[0]


def test_personality_context_zero_coverage():
    """Complex whose members have no ticker coverage emits zero-coverage block."""
    cdef = _make_complex_def("empty_complex", ["unknown_node"])
    ctx = compute_personality_context_for_complex(cdef, _PER_TICKER, _THEME_MAP)
    assert ctx is not None
    assert ctx["member_coverage"] == 0.0
    assert ctx["dominant_member_archetypes"] == []
    assert ctx["dominant_chart_labels"] == []
    assert ctx["tinderbox_share"] is None
    assert ctx["event_override_share"] is None
    assert ctx["confidence_class"] == "descriptive"


def test_personality_context_top3():
    """top3 shares are in descending order and each <= 1.0."""
    cdef = _make_complex_def("all_nodes", ["node_a", "node_b", "node_c"])
    ctx = compute_personality_context_for_complex(cdef, _PER_TICKER, _THEME_MAP)
    assert ctx is not None
    for key, share in ctx["dominant_member_archetypes"]:
        assert 0.0 <= share <= 1.0
    shares = [s for _, s in ctx["dominant_member_archetypes"]]
    assert shares == sorted(shares, reverse=True)


def test_personality_context_tinderbox():
    """tinderbox_share = correct fraction of covered members with tinderbox label."""
    # node_a=[AAPL,MSFT] (no tinderbox), node_b=[GOOG] (has tinderbox)
    cdef = _make_complex_def("tc_test", ["node_a", "node_b"])
    ctx = compute_personality_context_for_complex(cdef, _PER_TICKER, _THEME_MAP)
    # 1/3 tickers have tinderbox (GOOG)
    assert ctx is not None
    assert ctx["tinderbox_share"] is not None
    assert abs(ctx["tinderbox_share"] - 1 / 3) < 0.01


def test_personality_context_event_override():
    """event_override_share = correct fraction of covered members with event_override mode."""
    # GOOG has event_override; AAPL, MSFT do not → 1/3
    cdef = _make_complex_def("eo_test", ["node_a", "node_b"])
    ctx = compute_personality_context_for_complex(cdef, _PER_TICKER, _THEME_MAP)
    assert ctx is not None
    assert ctx["event_override_share"] is not None
    assert abs(ctx["event_override_share"] - 1 / 3) < 0.01


def test_personality_context_confidence_class():
    """confidence_class is always 'descriptive'."""
    for node_list in [["node_a"], ["node_b"], ["unknown_node"]]:
        cdef = _make_complex_def("cc_test", node_list)
        ctx = compute_personality_context_for_complex(cdef, _PER_TICKER, _THEME_MAP)
        if ctx is not None:
            assert ctx["confidence_class"] == "descriptive"
            assert "lineage" in ctx


# ---------------------------------------------------------------------------
# 8–9  Oracle contract tests
# ---------------------------------------------------------------------------

from engine.oracle.contract import validate_payload, PAYLOAD_VERSION
from datetime import date


_FRESH_ASOF = date.today().isoformat()


def _minimal_valid_payload() -> dict:
    return {
        "schema": "oracle_state.v1",
        "payload_version": PAYLOAD_VERSION,
        "asof": _FRESH_ASOF,
        "disclaimers": {
            "display_only": True,
            "error_rates": {
                "onset_to_confirmed_conversion": 0.45,
                "false_start_rate": 0.30,
            },
        },
        "active_episodes": [
            {
                "node": "ai_compute",
                "direction": "out",
                "tier": "onset",
                "onset_date": _FRESH_ASOF,
            }
        ],
    }


def test_oracle_payload_valid_with_personality_context():
    """validate_payload passes when complexes carry personality_context (additive)."""
    payload = _minimal_valid_payload()
    payload["complexes"] = [
        {
            "id": "ai_compute",
            "name": "AI Compute",
            "state": "quiet",
            "personality_context": {
                "dominant_member_archetypes": [["quality_compounder", 0.5]],
                "dominant_chart_labels": [["smooth_compounder_grind", 0.6]],
                "tinderbox_share": 0.1,
                "event_override_share": 0.05,
                "member_coverage": 0.7,
                "confidence_class": "descriptive",
                "lineage": "research/STOCK_PERSONALITY_MASTERPLAN_BY_FABLE.md R-SP19",
            },
        }
    ]
    ok, errs = validate_payload(
        payload,
        as_of_now=datetime.now(timezone.utc),
    )
    assert ok, f"payload with personality_context should pass; errors: {errs}"


def test_oracle_payload_valid_without_personality_context():
    """validate_payload passes when complexes carry NO personality_context (tolerant)."""
    payload = _minimal_valid_payload()
    payload["complexes"] = [
        {"id": "ai_compute", "name": "AI Compute", "state": "quiet"}
    ]
    ok, errs = validate_payload(
        payload,
        as_of_now=datetime.now(timezone.utc),
    )
    assert ok, f"payload without personality_context should also pass; errors: {errs}"


# ---------------------------------------------------------------------------
# 10–12  world_state sub-block tests
# ---------------------------------------------------------------------------

from engine.neuralweb.world_state import _compose_stock_personality_summary


def _write_sp_aggregate(root: Path, data: dict) -> None:
    p = root / "site" / "factordata" / "stock_personality.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))


def test_world_state_sp_summary_present(tmp_path):
    """stock_personality_summary is a dict when aggregate is present."""
    agg = {
        "schema": "stock_personality.v1",
        "as_of": _FRESH_ASOF,  # today — clock-independent vs the >2-trading-day gate
        "n_tickers": 5,
        "coverage": 0.9,
        "label_distributions": {
            "archetype": {"quality_compounder": 3, "cyclical": 2},
            "chart_personality": {"smooth_compounder_grind": 4, "event_gapper": 1},
        },
        "per_ticker": {
            "AAPL": {"arch": "quality_compounder", "own": [], "modes": ["normal"],
                     "chart": ["smooth_compounder_grind"], "dna": None, "micro": []},
            "GOOG": {"arch": "cyclical",
                     "own": ["short_interest_tinderbox"], "modes": ["event_override"],
                     "chart": ["event_gapper"], "dna": None, "micro": []},
        },
    }
    _write_sp_aggregate(tmp_path, agg)
    result = _compose_stock_personality_summary(root=tmp_path)
    assert isinstance(result, dict)
    assert result.get("available") is True
    assert result.get("display_only") is True


def test_world_state_sp_summary_absent(tmp_path):
    """Absent aggregate ⇒ {available: False}, no crash."""
    result = _compose_stock_personality_summary(root=tmp_path)
    assert isinstance(result, dict)
    assert result.get("available") is False
    assert result.get("display_only") is True


def test_world_state_sp_summary_keys(tmp_path):
    """Correct keys emitted when aggregate is present."""
    agg = {
        "schema": "stock_personality.v1",
        "as_of": _FRESH_ASOF,  # today — clock-independent vs the >2-trading-day gate
        "n_tickers": 2,
        "coverage": 1.0,
        "label_distributions": {
            "archetype": {"quality_compounder": 2},
            "chart_personality": {"smooth_compounder_grind": 1},
        },
        "per_ticker": {
            "AAPL": {"arch": "quality_compounder", "own": ["short_interest_tinderbox"],
                     "modes": ["event_override"], "chart": [], "dna": None, "micro": []},
            "MSFT": {"arch": "quality_compounder", "own": [], "modes": ["normal"],
                     "chart": ["smooth_compounder_grind"], "dna": None, "micro": []},
        },
    }
    _write_sp_aggregate(tmp_path, agg)
    result = _compose_stock_personality_summary(root=tmp_path)
    expected_keys = {
        "available", "as_of", "n_tickers", "coverage",
        "top_archetype_shares", "top_chart_shares",
        "n_tinderbox", "n_event_override", "display_only",
    }
    assert expected_keys == set(result.keys())
    assert result["n_tinderbox"] == 1
    assert result["n_event_override"] == 1
    assert result["as_of"] == _FRESH_ASOF


# ---------------------------------------------------------------------------
# 13–14  adapt_personality_context (spine adapter) tests
# ---------------------------------------------------------------------------

from engine.neuralweb.query import adapt_personality_context


def _write_sp_agg_for_query(root: Path, per_ticker: dict, as_of: str = "2026-07-06") -> None:
    agg = {
        "schema": "stock_personality.v1",
        "as_of": as_of,
        "n_tickers": len(per_ticker),
        "coverage": 1.0,
        "label_distributions": {},
        "per_ticker": per_ticker,
    }
    p = root / "site" / "factordata" / "stock_personality.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(agg))


def test_adapter_join_rows(tmp_path):
    """adapt_personality_context emits one row per ticker, ungraded-honest."""
    per_ticker = {
        "AAPL": {"arch": "quality_compounder", "dna": None,
                 "chart": ["smooth_compounder_grind"], "own": [],
                 "micro": [], "modes": ["normal"]},
        "NVDA": {"arch": "high_beta_momentum", "dna": None,
                 "chart": ["volatile_momentum_vehicle"], "own": ["short_interest_tinderbox"],
                 "micro": [], "modes": ["event_override"]},
    }
    _write_sp_agg_for_query(tmp_path, per_ticker)
    df, gaps = adapt_personality_context(root=tmp_path)
    assert len(df) == 2
    assert set(df["symbol"]) == {"AAPL", "NVDA"}
    # All rows: ungraded-honest
    assert (df["outcome_graded"] == False).all()
    assert (df["direction"] == 0).all()
    assert (df["size_binding"] == False).all()
    assert (df["ledger"] == "personality_context").all()
    # Archetype carried for cortex surface
    aapl_row = df[df["symbol"] == "AAPL"].iloc[0]
    assert aapl_row["archetype"] == "quality_compounder"
    # Gap note present
    assert any("context rows emitted" in g for g in gaps)


def test_adapter_absent_aggregate(tmp_path):
    """Absent aggregate ⇒ zero rows + gap note."""
    df, gaps = adapt_personality_context(root=tmp_path)
    assert len(df) == 0
    assert any("absent" in g for g in gaps)


# ---------------------------------------------------------------------------
# 15  payload_version sanity
# ---------------------------------------------------------------------------

def test_payload_version_bumped():
    """PAYLOAD_VERSION must be >= 1.2.0 (B1 member roll-up minor bump)."""
    from engine.oracle.contract import PAYLOAD_VERSION
    parts = [int(x) for x in PAYLOAD_VERSION.split(".")]
    major, minor, patch = parts[0], parts[1], parts[2]
    # Must be at least 1.2.0
    assert (major, minor) >= (1, 2), (
        f"PAYLOAD_VERSION {PAYLOAD_VERSION} should be >= 1.2.0 after B1 roll-up"
    )


# ---------------------------------------------------------------------------
# 16–21  Staleness gate + honesty tests (Opus review findings 1, 2, 3, 6)
# ---------------------------------------------------------------------------

from engine.oracle.personality_context import (
    append_personality_context,
    _is_aggregate_stale,
)
from datetime import date, timedelta


def _make_aggregate(as_of: str, per_ticker: dict | None = None) -> dict:
    """Build a minimal site aggregate dict with given as_of."""
    return {
        "schema": "stock_personality.v1",
        "as_of": as_of,
        "n_tickers": 1,
        "coverage": 1.0,
        "label_distributions": {
            "archetype": {"quality_compounder": 1},
            "chart_personality": {"smooth_compounder_grind": 1},
        },
        "per_ticker": per_ticker if per_ticker is not None else {
            "AAPL": _make_per_ticker("AAPL", arch="quality_compounder",
                                     chart=["smooth_compounder_grind"])
        },
    }


# A fresh as_of = today (0 trading days stale)
_TODAY_ISO = date.today().isoformat()
# A stale as_of = 10 calendar days ago (always > 2 trading days)
_STALE_ISO = (date.today() - timedelta(days=10)).isoformat()


def test_personality_as_of_present_fresh():
    """Fresh aggregate ⇒ personality_context is emitted and contains personality_as_of."""
    complexes = [{"id": "ai_compute", "name": "AI Compute", "state": "quiet"}]
    complexes_def = [_make_complex_def("ai_compute", ["node_a"])]
    agg = _make_aggregate(_TODAY_ISO)

    result = append_personality_context(
        complexes, complexes_def, repo="/dev/null",
        site_aggregate=agg,
        theme_ticker_map=_THEME_MAP,
    )
    ctx = result[0].get("personality_context")
    assert ctx is not None, "Fresh aggregate must emit personality_context"
    assert ctx.get("personality_as_of") == _TODAY_ISO, (
        f"personality_as_of should equal aggregate as_of ({_TODAY_ISO}); "
        f"got {ctx.get('personality_as_of')!r}"
    )


def test_personality_stale_gate_omits_field():
    """Stale aggregate (>2 trading days) ⇒ personality_context field absent on complex.

    This test FAILS on pre-fix code (before the staleness gate was added to
    append_personality_context) — the field would be present even for stale aggregates.
    """
    complexes = [{"id": "ai_compute", "name": "AI Compute", "state": "quiet"}]
    complexes_def = [_make_complex_def("ai_compute", ["node_a"])]
    agg = _make_aggregate(_STALE_ISO)  # 10 calendar days ago — clearly stale

    result = append_personality_context(
        complexes, complexes_def, repo="/dev/null",
        site_aggregate=agg,
        theme_ticker_map=_THEME_MAP,
    )
    assert "personality_context" not in result[0], (
        f"Stale aggregate (as_of={_STALE_ISO}) must NOT emit personality_context; "
        f"got: {result[0].get('personality_context')}"
    )


def test_personality_as_of_matches_aggregate():
    """personality_as_of in the emitted block matches the aggregate's as_of."""
    complexes = [{"id": "ai_compute", "name": "AI Compute", "state": "quiet"}]
    complexes_def = [_make_complex_def("ai_compute", ["node_a"])]
    # Use yesterday: guaranteed 1 trading day stale (fresh)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    agg = _make_aggregate(yesterday)

    result = append_personality_context(
        complexes, complexes_def, repo="/dev/null",
        site_aggregate=agg,
        theme_ticker_map=_THEME_MAP,
    )
    ctx = result[0].get("personality_context")
    # Note: yesterday may or may not be stale depending on weekday — only assert if present
    if ctx is not None:
        assert ctx.get("personality_as_of") == yesterday


def test_world_state_stale_gate_returns_null(tmp_path):
    """world_state._compose_stock_personality_summary with stale as_of ⇒ available=False.

    This test FAILS on pre-fix code (before the staleness gate was added to
    _compose_stock_personality_summary) — available=True would be returned for stale data.
    """
    stale_agg = {
        "schema": "stock_personality.v1",
        "as_of": _STALE_ISO,  # 10 calendar days ago — clearly stale
        "n_tickers": 2,
        "coverage": 1.0,
        "label_distributions": {
            "archetype": {"quality_compounder": 2},
            "chart_personality": {"smooth_compounder_grind": 1},
        },
        "per_ticker": {
            "AAPL": {"arch": "quality_compounder", "own": [], "modes": ["normal"],
                     "chart": [], "dna": None, "micro": []},
        },
    }
    _write_sp_aggregate(tmp_path, stale_agg)
    result = _compose_stock_personality_summary(root=tmp_path)
    assert result.get("available") is False, (
        f"Stale aggregate (as_of={_STALE_ISO}) must return available=False; got {result}"
    )
    assert result.get("note") == "stale", f"Expected note='stale'; got {result.get('note')!r}"
    assert result.get("as_of") == _STALE_ISO


def test_coverage_honesty_nondict_record():
    """Non-dict per_ticker record must NOT count as covered (finding 6).

    Pre-fix behavior: a ticker present in per_ticker but with a non-dict value
    (e.g. None or a string) would count toward n_nodes_with_data, producing
    coverage=1.0 with empty shares.  Post-fix: such records are excluded.
    """
    per_ticker_with_nondict = {
        "AAPL": None,   # non-dict — should NOT count as covered
        "MSFT": "bad",  # non-dict — should NOT count as covered
        "GOOG": _make_per_ticker("GOOG", arch="secular_growth"),  # usable
    }
    theme_map = {
        "node_a": ["AAPL", "MSFT"],  # both non-dict → node_a NOT covered
        "node_b": ["GOOG"],          # dict → node_b covered
    }
    cdef = _make_complex_def("test_cov", ["node_a", "node_b"])
    ctx = compute_personality_context_for_complex(cdef, per_ticker_with_nondict, theme_map)
    assert ctx is not None
    # node_b is covered (GOOG is a dict), node_a is not → coverage = 1/2 = 0.5
    assert ctx["member_coverage"] == 0.5, (
        f"Expected coverage=0.5 (only node_b covered); got {ctx['member_coverage']}"
    )
    # Shares should reflect GOOG only — 1 ticker covered
    archetypes = dict(ctx["dominant_member_archetypes"])
    assert "secular_growth" in archetypes


def test_share_denominators_field_emitted():
    """share_denominators honesty field is present in the emitted block."""
    cdef = _make_complex_def("test_sd", ["node_a", "node_b"])
    ctx = compute_personality_context_for_complex(cdef, _PER_TICKER, _THEME_MAP)
    assert ctx is not None
    sd = ctx.get("share_denominators")
    assert isinstance(sd, dict), f"share_denominators must be a dict; got {type(sd)}"
    assert sd.get("archetypes_and_flags") == "covered_tickers"
    assert sd.get("chart_labels") == "label_emissions"
