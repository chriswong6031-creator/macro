"""Tests for the Stage Analysis research index (SGA-2 §F): engine/stage_research.py.

Covers the index shape, provider-flag derivation, the trading-verb / advice scrub,
missing-seed fail-open, and the atomic artifact write.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from engine import stage_research as R


def _seed_research(root: Path, rows: list[dict]) -> None:
    d = root / "stage_analysis" / "backfill"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(d / "research.parquet")


def _base_row(**over) -> dict:
    row = {
        "tickerb": "AAPL US",
        "ticker_ui": "AAPL",
        "summary_thesis_answer": "Apple designs premium consumer hardware and services.",
        "claude_reasoning_analysis": None,
        "openai_reasoning_analysis": None,
        "gemini_reasoning_research_url": None,
        "model_used": "google/gemini-2.5-pro",
        "tier": 1,
        "response_type": "short_summary_thesis",
    }
    row.update(over)
    return row


# ------------------------------------------------------------------ scrub ----

def test_scrub_removes_trading_verbs_and_advice():
    """Bare trading verbs + whole advice phrases are neutralized; text stays readable."""
    src = ("We recommend investors buy the dip; our price target implies upside. "
           "Traders should accumulate and go long here.")
    out = R._scrub_advice(src)
    low = out.lower()
    for banned in ("price target", "buy the dip", "we recommend", "should accumulate"):
        assert banned not in low
    # bare imperative verbs are gone
    assert " buy " not in f" {low} "
    assert " accumulate " not in f" {low} "
    # scrub is idempotent
    assert R._scrub_advice(out) == out
    # fail-open on None
    assert R._scrub_advice(None) is None


def test_scrub_preserves_long_short_term_adjectives():
    """Bare 'long'/'short' must NOT be mapped (item 8): the old bare-verb map
    corrupted 'long-term' -> 'watch-term'. Non-advice adjectives survive intact,
    while genuine trading constructs ('go long', 'a long position') are scrubbed."""
    # Adjectives survive verbatim.
    assert R._scrub_advice("strong long-term growth") == "strong long-term growth"
    assert R._scrub_advice("a short-term dip in margins") == "a short-term dip in margins"
    assert R._scrub_advice("management took a long view") == "management took a long view"
    # Genuine trading constructs are still neutralized.
    for src in ("Traders should go long here.", "We took a long position.",
                "Go short the laggards."):
        out = R._scrub_advice(src).lower()
        assert "go long" not in out and "go short" not in out
        assert "a long position" not in out


def test_thesis_in_index_is_scrubbed(tmp_path):
    """Advice language in the seed thesis never reaches the built index."""
    _seed_research(tmp_path, [
        _base_row(summary_thesis_answer=(
            "Strong buy: investors should buy this name; price target well above spot.")),
    ])
    art = R.build_research_index(root=tmp_path)
    thesis = art["items"][0]["thesis_summary"].lower()
    for banned in ("strong buy", "should buy", "price target"):
        assert banned not in thesis


# ------------------------------------------------------------------ shape ----

def test_index_shape_and_fields(tmp_path):
    """Each item carries the full contract field set; envelope is display-tier."""
    _seed_research(tmp_path, [_base_row()])
    art = R.build_research_index(root=tmp_path)
    assert art["schema"] == "research_index.v1"
    assert art["is_context_only"] is True and art["display_only"] is True
    assert art["count"] == 1
    it = art["items"][0]
    assert set(it) == {"tickerb", "ticker_ui", "region", "thesis_summary",
                       "model_used", "tier", "has_openai", "has_claude",
                       "has_gemini", "research_url"}
    assert it["ticker_ui"] == "AAPL"
    assert it["tier"] == 1
    # FIX 1c: region derived from the Bloomberg suffix ("AAPL US" -> USA).
    assert it["region"] == "USA"
    assert art["has_region"] is True
    assert art["region_counts"]["USA"] == 1


def test_region_from_bloomberg_suffix(tmp_path):
    """FIX 1c positive control — the suffix→region map fires across all three
    regions (US bare + US suffix → USA, London/Paris/Frankfurt → EUROPE,
    HK/Shanghai/Korea → ASIA), and region_counts tallies them."""
    _seed_research(tmp_path, [
        _base_row(ticker_ui="AAPL", tickerb="AAPL US"),      # USA
        _base_row(ticker_ui="MSFT", tickerb="MSFT"),         # bare → USA
        _base_row(ticker_ui="SHOP", tickerb="SHOP CN"),      # Canada → USA (N.Amer)
        _base_row(ticker_ui="HSBC", tickerb="HSBA LN"),      # London → EUROPE
        _base_row(ticker_ui="SAP",  tickerb="SAP GY"),       # Frankfurt → EUROPE
        _base_row(ticker_ui="TCEHY", tickerb="700 HK"),      # Hong Kong → ASIA
        _base_row(ticker_ui="SAMS", tickerb="005930 KS"),    # Korea → ASIA
        _base_row(ticker_ui="RELI", tickerb="RELIANCE IN"),  # India → ASIA
    ])
    art = R.build_research_index(root=tmp_path)
    by = {i["ticker_ui"]: i["region"] for i in art["items"]}
    assert by["AAPL"] == "USA" and by["MSFT"] == "USA" and by["SHOP"] == "USA"
    assert by["HSBC"] == "EUROPE" and by["SAP"] == "EUROPE"
    assert by["TCEHY"] == "ASIA" and by["SAMS"] == "ASIA" and by["RELI"] == "ASIA"
    assert art["has_region"] is True and art["region_scheme"] == "bloomberg_suffix"
    assert art["region_counts"] == {"USA": 3, "EUROPE": 2, "ASIA": 3}


def test_provider_flags_derived(tmp_path):
    """has_openai/claude/gemini derive from reasoning columns AND model_used."""
    _seed_research(tmp_path, [
        _base_row(ticker_ui="G", tickerb="G", model_used="google/gemini-2.5-pro",
                  gemini_reasoning_research_url="https://x/y"),
        _base_row(ticker_ui="O", tickerb="O", model_used="perplexity/sonar-pro-search"),
        _base_row(ticker_ui="C", tickerb="C", model_used="anthropic/claude-opus-4",
                  claude_reasoning_analysis="deep reasoning here"),
    ])
    art = R.build_research_index(root=tmp_path)
    by = {i["ticker_ui"]: i for i in art["items"]}
    assert by["G"]["has_gemini"] is True and by["G"]["research_url"] == "https://x/y"
    assert by["O"]["has_openai"] is True          # sonar/perplexity -> openai-family flag
    assert by["C"]["has_claude"] is True


def test_dedupe_prefers_thesis_then_broader_tier(tmp_path):
    """Two rows for one ticker collapse to the one with a thesis / broader tier."""
    _seed_research(tmp_path, [
        _base_row(ticker_ui="DUP", tickerb="DUP", tier=2, summary_thesis_answer=None),
        _base_row(ticker_ui="DUP", tickerb="DUP", tier=1,
                  summary_thesis_answer="Has a real thesis."),
    ])
    art = R.build_research_index(root=tmp_path)
    assert art["count"] == 1
    it = art["items"][0]
    assert it["thesis_summary"] == "Has a real thesis."
    assert it["tier"] == 1


def test_missing_seed_fail_open(tmp_path):
    """No research seed -> empty index, writes the scaffold, never raises."""
    art = R.build_research_index(root=tmp_path)
    assert art["count"] == 0 and art["items"] == []
    assert art["is_context_only"] is True
    assert (tmp_path / "stage_analysis" / "research_index.json").exists()


def test_thesis_truncated(tmp_path):
    """An over-long thesis is truncated to the display cap with an ellipsis."""
    long = "Apple makes phones. " * 200
    _seed_research(tmp_path, [_base_row(summary_thesis_answer=long)])
    art = R.build_research_index(root=tmp_path)
    t = art["items"][0]["thesis_summary"]
    assert len(t) <= R._MAX_THESIS_CHARS + 1     # +1 for the ellipsis char
    assert t.endswith("…")
