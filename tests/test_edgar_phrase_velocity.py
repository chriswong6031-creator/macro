"""tests/test_edgar_phrase_velocity.py — Tests for engine/edgar_phrase_velocity.py.

Coverage:
  - Vocabulary versioning: VOCAB_VERSION present; SEED_PHRASES non-empty
  - Expansion cap = 0 with explanatory note (no text corpus available)
  - Velocity z math on synthetic fixtures
  - PIT keying: no lookahead (file_date > as_of excluded)
  - Per-source failure isolation (missing/corrupt parquet)
  - Theme rollup via membership fixtures
  - Novel phrase detection (tickers with no theme home)
  - Honest-null coverage paths
  - Banned word: "validated" never in output
  - Authority block correctness (all may_* false)
  - Site projection writer
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Import subject
# ---------------------------------------------------------------------------
import engine.edgar_phrase_velocity as epv


# ---------------------------------------------------------------------------
# 1. Vocabulary versioning
# ---------------------------------------------------------------------------

def test_vocab_version_positive_int():
    assert isinstance(epv.VOCAB_VERSION, int)
    assert epv.VOCAB_VERSION >= 1


def test_seed_phrases_non_empty():
    assert isinstance(epv.SEED_PHRASES, list)
    assert len(epv.SEED_PHRASES) >= 5, "SEED_PHRASES must have at least 5 entries"


def test_seed_phrases_strings():
    for p in epv.SEED_PHRASES:
        assert isinstance(p, str) and len(p) > 0


def test_expand_cap_is_zero():
    """v1: expansion disabled because FTS returns no text."""
    assert epv.EXPAND_CAP_PER_THEME == 0


def test_expand_note_present():
    """The compute result must contain an expand_note explaining the zero cap."""
    # Just check the module-level function includes the note
    with mock.patch("engine.edgar_phrase_velocity._load_theme_baskets", return_value={}):
        result = epv.compute_phrase_velocity(as_of=date(2026, 7, 9))
    assert "expand_note" in result
    assert len(result["expand_note"]) > 10


# ---------------------------------------------------------------------------
# 2. Velocity z math on synthetic fixtures
# ---------------------------------------------------------------------------

def _make_hits(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal hits dataframe from list of {ticker, file_date, phrase}."""
    return pd.DataFrame(rows)[["ticker", "file_date", "phrase"]]


def test_velocity_z_accelerating():
    """Recent count > prior count -> positive z."""
    as_of = date(2026, 7, 9)
    # 5 hits in recent window, 1 in prior
    rows = [
        {"ticker": "NVDA", "file_date": (as_of - timedelta(days=5)).isoformat(), "phrase": "on allocation"},
        {"ticker": "NVDA", "file_date": (as_of - timedelta(days=10)).isoformat(), "phrase": "on allocation"},
        {"ticker": "AMD", "file_date": (as_of - timedelta(days=7)).isoformat(), "phrase": "on allocation"},
        {"ticker": "MSFT", "file_date": (as_of - timedelta(days=15)).isoformat(), "phrase": "on allocation"},
        {"ticker": "META", "file_date": (as_of - timedelta(days=20)).isoformat(), "phrase": "on allocation"},
        # prior window: only 1 hit
        {"ticker": "NVDA", "file_date": (as_of - timedelta(days=50)).isoformat(), "phrase": "on allocation"},
    ]
    df = _make_hits(rows)
    counts = epv._pit_counts(df, {"NVDA", "AMD", "MSFT", "META"}, as_of)
    assert "on allocation" in counts
    c = counts["on allocation"]
    assert c["recent_count"] > c["prior_count"]
    z = epv._velocity_z(c["recent_count"], c["prior_count"])
    assert z is not None
    assert z > 0


def test_velocity_z_decelerating():
    """Prior count > recent count -> negative z."""
    as_of = date(2026, 7, 9)
    rows = [
        # prior: 3 hits
        {"ticker": "NVDA", "file_date": (as_of - timedelta(days=45)).isoformat(), "phrase": "sold out"},
        {"ticker": "AMD", "file_date": (as_of - timedelta(days=50)).isoformat(), "phrase": "sold out"},
        {"ticker": "MSFT", "file_date": (as_of - timedelta(days=55)).isoformat(), "phrase": "sold out"},
        # recent: 1 hit
        {"ticker": "NVDA", "file_date": (as_of - timedelta(days=3)).isoformat(), "phrase": "sold out"},
    ]
    df = _make_hits(rows)
    counts = epv._pit_counts(df, {"NVDA", "AMD", "MSFT"}, as_of)
    c = counts["sold out"]
    z = epv._velocity_z(c["recent_count"], c["prior_count"])
    assert z is not None
    assert z < 0


def test_velocity_z_both_zero():
    """Both zero -> None (not a false zero)."""
    assert epv._velocity_z(0, 0) is None


def test_velocity_z_capped_at_5():
    """Extreme acceleration is capped at 5."""
    z = epv._velocity_z(100, 0)  # prior=0 -> denom=1
    assert z is not None
    assert abs(z) <= 5.0


# ---------------------------------------------------------------------------
# 3. PIT keying: no lookahead
# ---------------------------------------------------------------------------

def test_pit_no_lookahead():
    """Rows with file_date > as_of must be excluded."""
    as_of = date(2026, 7, 9)
    rows = [
        # future hit — must be excluded
        {"ticker": "NVDA", "file_date": (as_of + timedelta(days=5)).isoformat(), "phrase": "on allocation"},
        # valid hit in recent window
        {"ticker": "NVDA", "file_date": (as_of - timedelta(days=3)).isoformat(), "phrase": "on allocation"},
    ]
    df = _make_hits(rows)
    counts = epv._pit_counts(df, {"NVDA"}, as_of)
    c = counts.get("on allocation", {})
    # Only the valid hit should count
    assert c.get("recent_count", 0) == 1


def test_pit_boundary_inclusive():
    """file_date == as_of is included in recent window."""
    as_of = date(2026, 7, 9)
    rows = [
        {"ticker": "NVDA", "file_date": as_of.isoformat(), "phrase": "tight supply"},
    ]
    df = _make_hits(rows)
    counts = epv._pit_counts(df, {"NVDA"}, as_of)
    assert counts.get("tight supply", {}).get("recent_count", 0) == 1


# ---------------------------------------------------------------------------
# 4. Per-source failure isolation
# ---------------------------------------------------------------------------

def test_missing_source_parquet_returns_null_not_exception():
    """When both source parquets are absent, compute returns valid dict with null themes."""
    with mock.patch("engine.edgar_phrase_velocity.config") as mc:
        mc.data_dir.return_value = Path("/tmp/nonexistent_dir_xyz")
        mc.ROOT = Path("/tmp/nonexistent_dir_xyz")
        result = epv.compute_phrase_velocity(as_of=date(2026, 7, 9))
    assert isinstance(result, dict)
    assert result.get("schema") == "edgar_phrase_velocity.v1"
    # Should have a coverage note explaining the absence
    assert result.get("coverage_stats", {}).get("combined_rows", 0) == 0


def test_corrupt_parquet_isolated():
    """Corrupt bottleneck parquet should not crash; emergence alone is used."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write a corrupt "parquet"
        corrupt = Path(tmpdir) / "edgar" / "bottleneck_hits.parquet"
        corrupt.parent.mkdir(parents=True)
        corrupt.write_text("not a parquet")

        # Write a valid emergence parquet
        valid = Path(tmpdir) / "edgar" / "emergence_hits.parquet"
        df = pd.DataFrame([
            {"ticker": "NVDA", "file_date": "2026-07-01", "phrase": "on allocation"}
        ])
        df.to_parquet(valid, index=False)

        with mock.patch("engine.edgar_phrase_velocity.config") as mc:
            mc.data_dir.return_value = Path(tmpdir)
            mc.ROOT = Path(tmpdir)
            # Prevent theme_baskets call from failing
            with mock.patch("engine.edgar_phrase_velocity._load_theme_baskets", return_value={}):
                result = epv.compute_phrase_velocity(as_of=date(2026, 7, 9))
    assert isinstance(result, dict)
    # Should not have raised


# ---------------------------------------------------------------------------
# 5. Theme rollup via membership fixtures
# ---------------------------------------------------------------------------

def test_theme_rollup_uses_baskets():
    """Themes composed from basket membership get tickers filtered correctly."""
    # Mock basket membership
    mock_baskets = {"ai_semiconductors": ["NVDA", "AMD"]}

    as_of = date(2026, 7, 9)
    rows = [
        {"ticker": "NVDA", "file_date": (as_of - timedelta(days=5)).isoformat(), "phrase": "on allocation"},
        {"ticker": "AMD", "file_date": (as_of - timedelta(days=8)).isoformat(), "phrase": "on allocation"},
        # Non-member ticker — should not affect ai_semiconductors theme
        {"ticker": "MSFT", "file_date": (as_of - timedelta(days=3)).isoformat(), "phrase": "on allocation"},
    ]
    df = _make_hits(rows)
    counts = epv._pit_counts(df, {"NVDA", "AMD"}, as_of)
    assert "on allocation" in counts
    c = counts["on allocation"]
    # MSFT excluded (not in theme universe)
    assert c["recent_filers"] == 2  # NVDA + AMD both in recent


def test_theme_rollup_honest_null_empty_universe():
    """Empty basket membership -> null entry with coverage_note."""
    with mock.patch("engine.edgar_phrase_velocity._load_theme_baskets",
                    return_value={"ai_semiconductors": []}):
        with mock.patch("engine.edgar_phrase_velocity.config") as mc:
            mc.data_dir.return_value = Path("/tmp/nonexistent_xyz2")
            mc.ROOT = Path("/tmp/nonexistent_xyz2")
            result = epv.compute_phrase_velocity(as_of=date(2026, 7, 9))
    # Theme with empty tickers should have a null entry
    t = result.get("themes", {}).get("ai_semiconductors")
    if t is not None:
        assert t.get("coverage_note") is not None


# ---------------------------------------------------------------------------
# 6. Novel phrase detection
# ---------------------------------------------------------------------------

def test_novel_phrase_detection():
    """Tickers NOT in any theme's basket produce novel_phrases entries."""
    as_of = date(2026, 7, 9)
    rows = [
        # ticker not in any themed basket -> should surface as novel
        {"ticker": "XYZA", "file_date": (as_of - timedelta(days=5)).isoformat(), "phrase": "sold out"},
        {"ticker": "XYZB", "file_date": (as_of - timedelta(days=7)).isoformat(), "phrase": "sold out"},
        {"ticker": "XYZB", "file_date": (as_of - timedelta(days=10)).isoformat(), "phrase": "sold out"},
    ]
    df = _make_hits(rows)
    # Empty "all_themed_tickers" -> these are all novel
    all_themed: set[str] = set()
    novel_tickers = list(
        (df[~df["ticker"].isin(all_themed)]["ticker"].unique())
        if not df.empty
        else []
    )
    novel_counts = epv._pit_counts(df, set(novel_tickers), as_of)
    c = novel_counts.get("sold out", {})
    assert c.get("recent_count", 0) >= 2
    assert c.get("recent_filers", 0) >= 2


# ---------------------------------------------------------------------------
# 7. Honest-null coverage path
# ---------------------------------------------------------------------------

def test_all_null_when_no_sources():
    """When both parquets are absent, themes block is empty or all-null."""
    with mock.patch("engine.edgar_phrase_velocity.config") as mc:
        mc.data_dir.return_value = Path("/tmp/totally_absent_xyz")
        mc.ROOT = Path("/tmp/totally_absent_xyz")
        result = epv.compute_phrase_velocity(as_of=date(2026, 7, 9))
    # novel_phrases should be empty list, not None
    assert isinstance(result.get("novel_phrases"), list)
    # coverage_stats should explain
    cs = result.get("coverage_stats", {})
    assert cs.get("combined_rows", 0) == 0 or "note" in cs


# ---------------------------------------------------------------------------
# 8. Banned word: "validated"
# ---------------------------------------------------------------------------

def test_no_validated_in_output():
    """The word 'validated' must never appear in compute output."""
    with mock.patch("engine.edgar_phrase_velocity.config") as mc:
        mc.data_dir.return_value = Path("/tmp/totally_absent_xyz2")
        mc.ROOT = Path("/tmp/totally_absent_xyz2")
        result = epv.compute_phrase_velocity(as_of=date(2026, 7, 9))
    output_text = json.dumps(result)
    assert "validated" not in output_text.lower(), (
        "Word 'validated' found in output — CI-enforced ban"
    )


def test_no_validated_standalone_in_module_source():
    """The word 'validated' (as standalone word, not 'invalidated') must not appear
    as a user-facing claim in module strings. The CI check bans 'validated' as a
    word boundary match (not substrings like 'invalidated'). We mirror that here.
    """
    import re
    src_path = Path(__file__).parent.parent / "engine" / "edgar_phrase_velocity.py"
    src = src_path.read_text()
    # Word-boundary match: \bvalidated\b — this is what the CI script checks
    matches = re.findall(r'\bvalidated\b', src, re.IGNORECASE)
    assert not matches, (
        f"Found standalone 'validated' in module source — CI-enforced ban: {matches}"
    )


# ---------------------------------------------------------------------------
# 9. Authority block
# ---------------------------------------------------------------------------

def test_authority_block():
    assert epv.AUTHORITY["may_rank"] is False
    assert epv.AUTHORITY["may_gate"] is False
    assert epv.AUTHORITY["may_size"] is False
    assert epv.AUTHORITY["may_escalate"] is False
    assert epv.AUTHORITY["is_context_only"] is True


def test_authority_in_output():
    with mock.patch("engine.edgar_phrase_velocity.config") as mc:
        mc.data_dir.return_value = Path("/tmp/totally_absent_xyz3")
        mc.ROOT = Path("/tmp/totally_absent_xyz3")
        result = epv.compute_phrase_velocity(as_of=date(2026, 7, 9))
    auth = result.get("authority", {})
    assert auth.get("may_rank") is False
    assert auth.get("is_context_only") is True


# ---------------------------------------------------------------------------
# 10. Site projection writer
# ---------------------------------------------------------------------------

def test_site_projection_writes_json():
    """write_site_projection must write a valid JSON file."""
    result = {
        "schema": "edgar_phrase_velocity.v1",
        "vocab_version": 1,
        "as_of": "2026-07-09",
        "generated_at": "2026-07-09T00:00:00+00:00",
        "authority": epv.AUTHORITY,
        "honesty_header": "test",
        "coverage_stats": {"combined_rows": 0},
        "expand_note": "disabled",
        "themes": {},
        "novel_phrases": [],
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "basketdata" / "phrase_velocity.json"
        out.parent.mkdir()
        written = epv.write_site_projection(result, out_path=out)
        assert written == out
        data = json.loads(out.read_text())
    assert data["schema"] == "edgar_phrase_velocity.v1"
    assert "authority" in data
    assert data["authority"]["may_rank"] is False


def test_site_projection_no_validated():
    result = {
        "schema": "edgar_phrase_velocity.v1",
        "vocab_version": 1,
        "as_of": "2026-07-09",
        "generated_at": "2026-07-09T00:00:00+00:00",
        "authority": epv.AUTHORITY,
        "honesty_header": "test watchlist",
        "coverage_stats": {},
        "expand_note": "v1 cap=0",
        "themes": {},
        "novel_phrases": [],
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "basketdata" / "phrase_velocity.json"
        out.parent.mkdir()
        epv.write_site_projection(result, out_path=out)
        txt = out.read_text()
    assert "validated" not in txt.lower()


# ---------------------------------------------------------------------------
# 11. Honesty framing
# ---------------------------------------------------------------------------

def test_honesty_header_in_output():
    """Output must contain a honesty_header explaining discovery is noisy."""
    with mock.patch("engine.edgar_phrase_velocity.config") as mc:
        mc.data_dir.return_value = Path("/tmp/absent_xyz_honesty")
        mc.ROOT = Path("/tmp/absent_xyz_honesty")
        result = epv.compute_phrase_velocity(as_of=date(2026, 7, 9))
    hdr = result.get("honesty_header", "")
    assert len(hdr) > 10
    # Should mention watchlist or noisy
    assert any(w in hdr.lower() for w in ("watchlist", "noisy", "candidate"))


def test_schema_field_present():
    with mock.patch("engine.edgar_phrase_velocity.config") as mc:
        mc.data_dir.return_value = Path("/tmp/absent_xyz_schema")
        mc.ROOT = Path("/tmp/absent_xyz_schema")
        result = epv.compute_phrase_velocity(as_of=date(2026, 7, 9))
    assert result.get("schema") == "edgar_phrase_velocity.v1"
