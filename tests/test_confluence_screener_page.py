"""Tests for scripts.build_confluence_screener.

Headless-safe: no network, no site/ writes (tmp_path for any output),
does not depend on real artifact files.

The DOM-leak acceptance test verifies that gated tickers NEVER appear in the
public rendered HTML. They may appear only in the separate server-protected
/premiumdata/ payload returned to entitled sessions.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import sys
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from scripts.build_confluence_screener import (
    PAYLOAD_URL,
    build_context,
    build_premium_payload,
    render_html,
)

# ── Synthetic artifact ───────────────────────────────────────────────────────

# Three legs that combos can reference
_LEGS = [
    {"leg_id": "leg0", "signal_id": "s0", "tf": "D",
     "display_en": "Golden Cross",     "display_zh": "黄金交叉"},
    {"leg_id": "leg1", "signal_id": "s1", "tf": "W",
     "display_en": "Weekly Uptrend",   "display_zh": "周线上升趋势"},
    {"leg_id": "leg2", "signal_id": "s2", "tf": "D",
     "display_en": "RSI Curl",         "display_zh": "RSI上卷"},
]

_H21_VALID = {
    "n": 30,
    "wr_mc_test": 0.70,
    "wr_mc_train": 0.60,
    "n_test": 15,
    "months_test": 12,
    "n_train": 40,
    "months_train": 36,
}

def _make_raw(*, free_active=("FREEAA",), gated2_active=("GATEDBB",),
              gated3_active=("GATEDCC",)):
    """Build a synthetic tech_confluence-shaped artifact with 4 eligible combos
    (rank_score ordering: rank1=0.5, rank2=0.3, rank3=0.2, rank4=0.1) and one
    inactive combo to verify n_active_total counting.
    """
    return {
        "generated_utc": "2026-07-19T04:00:00Z",
        "universe_n": 226,
        "split_date": "2018-01-01",
        "legs": _LEGS,
        "combos": {
            "long": [
                # Rank 1 (highest rank_score, free)
                {
                    "id": "L0001",
                    "name_en": "Golden cross + weekly uptrend",
                    "name_zh": "黄金交叉+周线上升",
                    "legs": [0, 1],
                    "h21": _H21_VALID,
                    "rank_score": 0.5,
                    "active_now": list(free_active),
                    "n_fires": 100,
                    "first_fire": "2005-03-01",
                    "last_fire": "2026-07-15",
                    "fires_per_year": 3.5,
                    "edge_wr_test": 0.20,
                    "consistent": True,
                },
                # Rank 2 (gated)
                {
                    "id": "L0002",
                    "name_en": "RSI curl + golden cross",
                    "name_zh": "RSI上卷+黄金交叉",
                    "legs": [2, 0],
                    "h21": _H21_VALID,
                    "rank_score": 0.3,
                    "active_now": list(gated2_active),
                    "n_fires": 80,
                    "first_fire": "2008-01-01",
                    "last_fire": "2026-07-14",
                    "fires_per_year": 2.8,
                    "edge_wr_test": 0.15,
                    "consistent": False,
                },
                # Rank 3 (gated)
                {
                    "id": "L0003",
                    "name_en": "Weekly uptrend + RSI curl",
                    "name_zh": "周线上升+RSI上卷",
                    "legs": [1, 2],
                    "h21": _H21_VALID,
                    "rank_score": 0.2,
                    "active_now": list(gated3_active),
                    "n_fires": 60,
                    "first_fire": "2010-06-01",
                    "last_fire": "2026-07-13",
                    "fires_per_year": 2.0,
                    "edge_wr_test": 0.10,
                    "consistent": True,
                },
                # Rank 4 — would be rank 4 if there were more
                {
                    "id": "L0004",
                    "name_en": "Fourth combo",
                    "name_zh": "第四组合",
                    "legs": [0],
                    "h21": _H21_VALID,
                    "rank_score": 0.1,
                    "active_now": ["RANKFOUR"],
                    "n_fires": 40,
                    "first_fire": "2012-01-01",
                    "last_fire": "2026-07-12",
                    "fires_per_year": 1.5,
                    "edge_wr_test": 0.05,
                    "consistent": False,
                },
                # Inactive combo (should NOT count toward n_active_total)
                {
                    "id": "L0005",
                    "name_en": "Inactive combo",
                    "name_zh": "非活跃组合",
                    "legs": [0],
                    "h21": _H21_VALID,
                    "rank_score": 0.99,  # high score but inactive
                    "active_now": [],    # empty → should be excluded
                    "n_fires": 200,
                    "first_fire": "2000-01-01",
                    "last_fire": "2026-06-01",
                    "fires_per_year": 10.0,
                    "edge_wr_test": 0.30,
                    "consistent": True,
                },
                # Null h21 combo (should be excluded)
                {
                    "id": "L0006",
                    "name_en": "Null h21 combo",
                    "name_zh": "空h21组合",
                    "legs": [0],
                    "h21": {"wr_mc_test": None, "wr_mc_train": 0.55},
                    "rank_score": 0.8,
                    "active_now": ["NULLTST"],
                    "n_fires": 50,
                    "first_fire": "2015-01-01",
                    "last_fire": "2026-07-10",
                    "fires_per_year": 2.0,
                    "edge_wr_test": 0.12,
                    "consistent": True,
                },
            ],
            "short": [],
        },
    }


_ROOT = Path(__file__).resolve().parent.parent


# ── build_context tests ──────────────────────────────────────────────────────

def test_build_context_rank1_has_active_tickers():
    raw = _make_raw()
    ctx = build_context(raw, {})
    combos = ctx["combos"]
    assert len(combos) == 3  # top 3
    rank1 = combos[0]
    assert rank1["rank"] == 1
    assert rank1["is_free"] is True
    tickers = [t["ticker"] for t in rank1["active_tickers"]]
    assert "FREEAA" in tickers


def test_build_context_gated_combos_have_empty_active_tickers():
    raw = _make_raw()
    ctx = build_context(raw, {})
    combos = ctx["combos"]
    for c in combos[1:]:
        assert c["active_tickers"] == [], (
            f"Rank {c['rank']} combo should have empty active_tickers, got: {c['active_tickers']}"
        )


def test_build_context_n_active_total():
    raw = _make_raw()
    ctx = build_context(raw, {})
    # 4 combos have active_now and valid h21 (L0001, L0002, L0003, L0004)
    # L0005 is inactive (empty active_now), L0006 has null wr_mc_test
    assert ctx["n_active_total"] == 4


def test_build_context_sort_by_rank_score():
    raw = _make_raw()
    ctx = build_context(raw, {})
    scores = [c["combo_id"] for c in ctx["combos"]]
    # L0001 has rank_score 0.5, L0002 has 0.3, L0003 has 0.2
    assert scores == ["L0001", "L0002", "L0003"]


def test_build_context_none_raw():
    ctx = build_context(None, {})
    assert ctx["combos"] == []
    assert ctx["n_active_total"] == 0
    assert ctx["asof"] is None


def test_build_context_name_map_used():
    name_map = {"FREEAA": "Free Company Alpha"}
    raw = _make_raw()
    ctx = build_context(raw, name_map)
    tickers = ctx["combos"][0]["active_tickers"]
    assert tickers[0]["name"] == "Free Company Alpha"


def test_build_context_win_rate_pct():
    raw = _make_raw()
    ctx = build_context(raw, {})
    c = ctx["combos"][0]
    # wr_mc_test=0.70 → 70.0
    assert abs(c["wr_test_pct"] - 70.0) < 0.01
    # wr_mc_train=0.60 → 60.0
    assert abs(c["wr_train_pct"] - 60.0) < 0.01


def test_build_context_active_count_for_gated():
    """Gated combos must still expose active_count (the integer) — only tickers are hidden."""
    raw = _make_raw(gated2_active=("GATEDBB",), gated3_active=("GATEDCC", "GATEDDD"))
    ctx = build_context(raw, {})
    assert ctx["combos"][1]["active_count"] == 1
    assert ctx["combos"][2]["active_count"] == 2


# ── protected payload tests ─────────────────────────────────────────────────

def test_premium_payload_contains_only_gated_top_three_tickers():
    raw = _make_raw()
    payload = build_premium_payload(raw, {"GATEDBB": "Gated B"})

    assert payload["schema"] == "tier_payload.v1"
    assert payload["page"] == "confluence_screener"
    assert payload["gated"] is True
    assert payload["required_tier"] == "essential"
    assert payload["built"] == "2026-07-19T04:00:00Z"
    assert [combo["combo_id"] for combo in payload["combos"]] == ["L0002", "L0003"]

    payload_text = repr(payload)
    assert "GATEDBB" in payload_text
    assert "GATEDCC" in payload_text
    assert "Gated B" in payload_text
    assert "FREEAA" not in payload_text
    assert "RANKFOUR" not in payload_text


def test_premium_payload_none_raw_overwrites_with_empty_fail_soft_payload():
    payload = build_premium_payload(None, {})
    assert payload["schema"] == "tier_payload.v1"
    assert payload["gated"] is True
    assert payload["combos"] == []
    assert payload["built"] == ""


# ── render_html DOM-leak tests ───────────────────────────────────────────────

def _rendered_html():
    raw = _make_raw()
    ctx = build_context(raw, {})
    return render_html(_ROOT, ctx)


def test_render_html_free_ticker_present():
    html = _rendered_html()
    assert "FREEAA" in html


def test_render_html_gated_tickers_absent():
    """Critical: GATEDBB and GATEDCC must NOT appear anywhere in the rendered HTML."""
    html = _rendered_html()
    assert "GATEDBB" not in html, "GATED ticker leaked into rendered HTML!"
    assert "GATEDCC" not in html, "GATED ticker leaked into rendered HTML!"


def test_render_html_has_protected_payload_hydration_contract():
    html = _rendered_html()
    assert PAYLOAD_URL in html
    assert 'data-confluence-combo="L0002"' in html
    assert 'data-confluence-combo="L0003"' in html
    assert "credentials: 'same-origin'" in html
    assert "freshSession" in html
    assert "mdx-auth" in html
    assert "tier_payload.v1" in html
    assert 'id="confluence-paid-cta"' in html


def test_render_html_og_meta_present():
    html = _rendered_html()
    assert "og/confluence_screener.png" in html
    assert "summary_large_image" in html


def test_render_html_empty_context_no_exception():
    """empty context (raw=None) must render without exception."""
    ctx = build_context(None, {})
    html = render_html(_ROOT, ctx)
    assert html  # non-empty


def test_render_html_no_validated_word():
    """House law: the word 'validated' must not appear in user-facing rendered HTML."""
    html = _rendered_html()
    assert "validated" not in html.lower()


def test_render_html_is_html():
    html = _rendered_html()
    assert "<!DOCTYPE html>" in html or "<!doctype html>" in html.lower()


def test_shipped_shell_and_protected_payload_are_paired():
    """The committed artifact pair must stay deployable between nightly runs."""
    html = (_ROOT / "site" / "confluence_screener.html").read_text(encoding="utf-8")
    payload = json.loads(
        (_ROOT / "site" / "premiumdata" / "confluence_screener.json")
        .read_text(encoding="utf-8")
    )

    assert payload["schema"] == "tier_payload.v1"
    assert payload["page"] == "confluence_screener"
    assert payload["gated"] is True
    assert payload["required_tier"] == "essential"
    assert PAYLOAD_URL in html
    for combo in payload["combos"]:
        assert combo["active_count"] == len(combo["active_tickers"])
        assert f'data-confluence-combo="{combo["combo_id"]}"' in html
