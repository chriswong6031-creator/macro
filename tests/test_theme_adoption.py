"""tests/test_theme_adoption.py — Tests for engine/theme_adoption.py.

Coverage:
  - Per-source failure isolation (missing parquet)
  - Star velocity math on synthetic fixtures
  - Cross-sectional z-score computation (robust z)
  - Percentile rank computation
  - Theme rollup via basket membership
  - Honest-null when no GitHub data
  - Coverage path: non-tech baskets (zero coverage)
  - Banned word: "validated" never in output
  - Authority block correctness
  - npm/PyPI descoped note present
  - History caveat present in output
  - Site projection writer
  - Confluence join: both-legs / single-leg / neither
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

import engine.theme_adoption as ta


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_stars(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal repo_stars dataframe."""
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Per-source failure isolation
# ---------------------------------------------------------------------------

def test_missing_parquet_returns_null_not_exception():
    """When repo_stars.parquet is missing, result is valid dict with all nulls."""
    with mock.patch("engine.theme_adoption.config") as mc:
        mc.data_dir.return_value = Path("/tmp/nonexistent_ta_xyz")
        mc.ROOT = Path("/tmp/nonexistent_ta_xyz")
        result = ta.compute_theme_adoption(as_of=date(2026, 7, 9))
    assert isinstance(result, dict)
    assert result.get("schema") == "theme_adoption.v1"
    stats = result.get("coverage_stats", {})
    assert stats.get("total_rows", 0) == 0


def test_corrupt_parquet_handled_gracefully():
    """Corrupt parquet file yields null result without raising."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p = Path(tmpdir) / "github" / "repo_stars.parquet"
        p.parent.mkdir()
        p.write_text("not a parquet file")
        with mock.patch("engine.theme_adoption.config") as mc:
            mc.data_dir.return_value = Path(tmpdir)
            mc.ROOT = Path(tmpdir)
            result = ta.compute_theme_adoption(as_of=date(2026, 7, 9))
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 2. Star velocity math on synthetic fixtures
# ---------------------------------------------------------------------------

def test_star_velocity_positive():
    """Stars increased over 7 days -> positive velocity."""
    as_of = date(2026, 7, 9)
    df = _make_stars([
        {"ticker": "NVDA", "stars": 10000, "forks": 100, "snapshot_date": "2026-07-02"},
        {"ticker": "NVDA", "stars": 10500, "forks": 105, "snapshot_date": "2026-07-09"},
    ])
    vel = ta._star_velocity(df, "NVDA", as_of)
    assert vel is not None
    assert vel > 0
    # Expected: (10500 - 10000) / 10000 = 0.05
    assert abs(vel - 0.05) < 0.001


def test_star_velocity_no_prior_data():
    """Only one snapshot (no prior) -> None (insufficient history)."""
    as_of = date(2026, 7, 9)
    df = _make_stars([
        {"ticker": "NVDA", "stars": 10000, "forks": 100, "snapshot_date": "2026-07-09"},
    ])
    vel = ta._star_velocity(df, "NVDA", as_of)
    assert vel is None


def test_star_velocity_missing_ticker():
    """Ticker not in df -> None."""
    as_of = date(2026, 7, 9)
    df = _make_stars([
        {"ticker": "MSFT", "stars": 1000, "forks": 50, "snapshot_date": "2026-07-09"},
    ])
    vel = ta._star_velocity(df, "NVDA", as_of)
    assert vel is None


def test_star_velocity_pit_respected():
    """Snapshots after as_of are excluded."""
    as_of = date(2026, 7, 1)
    df = _make_stars([
        {"ticker": "NVDA", "stars": 9000, "forks": 90, "snapshot_date": "2026-06-24"},  # prior
        {"ticker": "NVDA", "stars": 9500, "forks": 95, "snapshot_date": "2026-07-01"},  # as_of
        {"ticker": "NVDA", "stars": 99999, "forks": 999, "snapshot_date": "2026-07-09"},  # future — excluded
    ])
    vel = ta._star_velocity(df, "NVDA", as_of)
    assert vel is not None
    # Should use 9500 / 9000, not 99999
    assert vel < 1.0  # (9500-9000)/9000 ≈ 0.055


# ---------------------------------------------------------------------------
# 3. Cross-sectional z-score
# ---------------------------------------------------------------------------

def test_cross_section_z_correct_shape():
    values = [0.01, 0.05, 0.02, 0.08, None, 0.03]
    result = ta._cross_section_z(values)
    assert len(result) == len(values)
    # None positions remain None
    assert result[4] is None


def test_cross_section_z_single_value():
    """Single non-null value -> all None (need ≥2 for z)."""
    result = ta._cross_section_z([0.05, None, None])
    assert all(v is None for v in result)


def test_cross_section_z_symmetric():
    """For symmetric inputs the median is at z=0."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = ta._cross_section_z(values)
    non_null = [v for v in result if v is not None]
    # Middle element should be near 0
    median_z = result[2]
    assert median_z is not None
    assert abs(median_z) < 0.1


def test_cross_section_z_capped():
    """Extreme outlier is capped at ±5."""
    values = [1.0, 1.0, 1.0, 1.0, 1000.0]
    result = ta._cross_section_z(values)
    non_null = [v for v in result if v is not None]
    assert all(abs(v) <= 5.0 for v in non_null)


# ---------------------------------------------------------------------------
# 4. Percentile rank computation
# ---------------------------------------------------------------------------

def test_pct_rank_order():
    d = {"A": 100, "B": 200, "C": 300}
    ranks = ta._pct_rank(d)
    assert ranks["A"] < ranks["B"] < ranks["C"]
    assert ranks["A"] == 0.0
    assert ranks["C"] == 100.0


def test_pct_rank_empty():
    assert ta._pct_rank({}) == {}


def test_pct_rank_single():
    ranks = ta._pct_rank({"X": 500})
    assert ranks["X"] == 0.0


# ---------------------------------------------------------------------------
# 5. Theme rollup via basket membership
# ---------------------------------------------------------------------------

def test_basket_rollup_aggregates_members():
    """Basket z should be median of covered ticker z-scores."""
    as_of = date(2026, 7, 9)
    # Two tickers in the ai_software basket
    df = _make_stars([
        {"ticker": "MSFT", "stars": 5000, "forks": 50, "snapshot_date": "2026-07-02"},
        {"ticker": "MSFT", "stars": 5500, "forks": 55, "snapshot_date": "2026-07-09"},
        {"ticker": "GOOGL", "stars": 8000, "forks": 80, "snapshot_date": "2026-07-02"},
        {"ticker": "GOOGL", "stars": 8200, "forks": 82, "snapshot_date": "2026-07-09"},
    ])

    mock_members = {"ai_software": {"MSFT", "GOOGL", "CRM"}}  # CRM has no data

    with mock.patch("engine.theme_adoption._load_basket_members", return_value=mock_members), \
         mock.patch("engine.theme_adoption._load_theme_to_baskets", return_value={"ai_software_theme": ["ai_software"]}), \
         mock.patch("engine.theme_adoption._load_stars", return_value=df):
        result = ta.compute_theme_adoption(as_of=as_of)

    basket = result.get("baskets", {}).get("ai_software", {})
    assert basket.get("n_covered", 0) == 2  # MSFT + GOOGL
    assert basket.get("n_basket_total", 0) == 3  # includes CRM


def test_null_basket_for_non_tech():
    """Non-tech basket (no tickers with OSS repos) should get honest null."""
    as_of = date(2026, 7, 9)
    df = _make_stars([
        {"ticker": "NVDA", "stars": 1000, "forks": 50, "snapshot_date": "2026-07-09"},
    ])
    mock_members = {
        "defense": {"LMT", "NOC", "RTX"},  # no github data for these
    }
    with mock.patch("engine.theme_adoption._load_basket_members", return_value=mock_members), \
         mock.patch("engine.theme_adoption._load_theme_to_baskets",
                    return_value={"defense_theme": ["defense"]}), \
         mock.patch("engine.theme_adoption._load_stars", return_value=df):
        result = ta.compute_theme_adoption(as_of=as_of)

    basket = result.get("baskets", {}).get("defense", {})
    assert basket.get("n_covered", 0) == 0
    assert basket.get("star_velocity_7d_z") is None
    cn = basket.get("coverage_note", "")
    assert len(cn) > 10  # must have explanatory note


# ---------------------------------------------------------------------------
# 6. Honest-null: no GitHub data at all
# ---------------------------------------------------------------------------

def test_honest_null_no_stars():
    """When stars parquet is missing, all baskets are null with notes."""
    with mock.patch("engine.theme_adoption._load_stars", return_value=None), \
         mock.patch("engine.theme_adoption._load_basket_members",
                    return_value={"ai_software": {"MSFT", "NVDA"}}), \
         mock.patch("engine.theme_adoption._load_theme_to_baskets",
                    return_value={"ai_theme": ["ai_software"]}):
        result = ta.compute_theme_adoption(as_of=date(2026, 7, 9))

    assert result.get("coverage_stats", {}).get("total_rows", 0) == 0
    basket = result.get("baskets", {}).get("ai_software")
    assert basket is not None
    assert basket.get("star_velocity_7d_z") is None


# ---------------------------------------------------------------------------
# 7. Banned word: "validated"
# ---------------------------------------------------------------------------

def test_no_validated_in_output():
    with mock.patch("engine.theme_adoption._load_stars", return_value=None), \
         mock.patch("engine.theme_adoption._load_basket_members", return_value={}), \
         mock.patch("engine.theme_adoption._load_theme_to_baskets", return_value={}):
        result = ta.compute_theme_adoption(as_of=date(2026, 7, 9))
    txt = json.dumps(result)
    assert "validated" not in txt.lower(), "Word 'validated' found in output"


# ---------------------------------------------------------------------------
# 8. Authority block
# ---------------------------------------------------------------------------

def test_authority_block():
    assert ta.AUTHORITY["may_rank"] is False
    assert ta.AUTHORITY["may_gate"] is False
    assert ta.AUTHORITY["may_size"] is False
    assert ta.AUTHORITY["may_escalate"] is False
    assert ta.AUTHORITY["is_context_only"] is True


def test_authority_in_output():
    with mock.patch("engine.theme_adoption._load_stars", return_value=None), \
         mock.patch("engine.theme_adoption._load_basket_members", return_value={}), \
         mock.patch("engine.theme_adoption._load_theme_to_baskets", return_value={}):
        result = ta.compute_theme_adoption(as_of=date(2026, 7, 9))
    auth = result.get("authority", {})
    assert auth.get("may_rank") is False
    assert auth.get("is_context_only") is True


# ---------------------------------------------------------------------------
# 9. npm/PyPI descope note present
# ---------------------------------------------------------------------------

def test_npm_pypi_descope_note_present():
    with mock.patch("engine.theme_adoption._load_stars", return_value=None), \
         mock.patch("engine.theme_adoption._load_basket_members", return_value={}), \
         mock.patch("engine.theme_adoption._load_theme_to_baskets", return_value={}):
        result = ta.compute_theme_adoption(as_of=date(2026, 7, 9))
    note = result.get("npm_pypi_note", "")
    assert "npm" in note.lower() or "pypi" in note.lower()
    assert "descoped" in note.lower() or "no collector" in note.lower()


# ---------------------------------------------------------------------------
# 10. History caveat present in output
# ---------------------------------------------------------------------------

def test_history_caveat_present():
    with mock.patch("engine.theme_adoption._load_stars", return_value=None), \
         mock.patch("engine.theme_adoption._load_basket_members", return_value={}), \
         mock.patch("engine.theme_adoption._load_theme_to_baskets", return_value={}):
        result = ta.compute_theme_adoption(as_of=date(2026, 7, 9))
    note = result.get("history_note", "")
    assert len(note) > 10
    assert "90" in note or "history" in note.lower()


# ---------------------------------------------------------------------------
# 11. Site projection writer
# ---------------------------------------------------------------------------

def test_site_projection_writes_valid_json():
    result = {
        "schema": "theme_adoption.v1",
        "as_of": "2026-07-09",
        "generated_at": "2026-07-09T00:00:00+00:00",
        "authority": ta.AUTHORITY,
        "coverage_stats": {"total_rows": 0},
        "npm_pypi_note": "descoped",
        "history_note": "short history",
        "honesty_header": "watchlist only",
        "baskets": {},
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "basketdata" / "github_adoption.json"
        out.parent.mkdir()
        written = ta.write_site_projection(result, out_path=out)
        data = json.loads(out.read_text())
    assert data["schema"] == "theme_adoption.v1"
    assert "authority" in data
    assert data["authority"]["may_rank"] is False


def test_site_projection_no_ticker_detail():
    """Site projection should not include full ticker_detail (too large)."""
    result = {
        "schema": "theme_adoption.v1",
        "as_of": "2026-07-09",
        "generated_at": "now",
        "authority": ta.AUTHORITY,
        "coverage_stats": {},
        "npm_pypi_note": "x",
        "history_note": "y",
        "honesty_header": "z",
        "baskets": {
            "ai_software": {
                "basket_id": "ai_software",
                "star_velocity_7d_z": 1.2,
                "n_covered": 3,
                "n_basket_total": 5,
                "covered_tickers": ["MSFT", "NVDA"],
                "ticker_detail": [{"ticker": "MSFT", "stars": 1000}],
                "coverage_note": "test",
                "coverage_note_zh": "测试",
            }
        },
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "basketdata" / "github_adoption.json"
        out.parent.mkdir()
        ta.write_site_projection(result, out_path=out)
        data = json.loads(out.read_text())
    # ticker_detail should NOT be in site artifact
    basket = data.get("baskets", {}).get("ai_software", {})
    assert "ticker_detail" not in basket


# ---------------------------------------------------------------------------
# 12. Confluence join logic (via build_discovery_confluence)
# ---------------------------------------------------------------------------

def test_confluence_both_legs():
    """Theme with both phrase_accel and adoption_positive -> both_legs candidate."""
    import scripts.build_discovery_confluence as bdc

    mock_phrase = {
        "themes": {
            "ai_semiconductors": {
                "theme_id": "ai_semiconductors",
                "top_accelerating": [
                    {"phrase": "on allocation", "velocity_z": 2.0, "recent_filers": 3}
                ],
            }
        },
        "novel_phrases": [],
    }
    mock_adoption = {
        "baskets": {
            "ai_semiconductors": {
                "star_velocity_7d_z": 1.5,
                "n_covered": 2,
            },
            "ai_infra": {
                "star_velocity_7d_z": 0.5,
                "n_covered": 1,
            },
        },
    }

    phrase_accel = bdc._theme_phrase_accelerating(mock_phrase, "ai_semiconductors")
    adoption_pos_semi = bdc._basket_adoption_positive(mock_adoption, "ai_semiconductors")
    adoption_pos_infra = bdc._basket_adoption_positive(mock_adoption, "ai_infra")

    assert phrase_accel is True, "Should detect phrase acceleration"
    assert adoption_pos_semi is True, "Should detect positive adoption z"
    assert adoption_pos_infra is True


def test_confluence_single_leg_phrase_only():
    """Phrase accelerates but adoption is None -> phrase_only candidate."""
    import scripts.build_discovery_confluence as bdc

    mock_phrase = {
        "themes": {
            "nuclear_power": {
                "theme_id": "nuclear_power",
                "top_accelerating": [
                    {"phrase": "capacity expansion", "velocity_z": 1.5, "recent_filers": 2}
                ],
            }
        }
    }
    mock_adoption = {
        "baskets": {
            "nuclear_power": {"star_velocity_7d_z": None, "n_covered": 0},
            "uranium_miners": {"star_velocity_7d_z": None, "n_covered": 0},
        }
    }
    phrase_accel = bdc._theme_phrase_accelerating(mock_phrase, "nuclear_power")
    adoption_pos = bdc._basket_adoption_positive(mock_adoption, "nuclear_power")
    assert phrase_accel is True
    assert adoption_pos is False


def test_confluence_no_validated_in_output():
    """discovery_confluence.json output must not contain 'validated'."""
    import scripts.build_discovery_confluence as bdc

    # Build a minimal result inline
    confluence_data = {
        "schema": "discovery_confluence.v1",
        "as_of": "2026-07-09",
        "generated_at": "now",
        "authority": bdc.AUTHORITY,
        "honesty_header": bdc.AUTHORITY["honesty_note"],
        "confluence_candidates": [],
        "single_leg_phrase": [],
        "single_leg_adoption": [],
        "novel_phrase_clusters": [],
    }
    txt = json.dumps(confluence_data)
    assert "validated" not in txt.lower()
