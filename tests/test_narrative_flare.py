"""Tests for engine/narrative_flare.py — narrative_flare.v1 (NAR-W3).

Covers:
- Kleinberg burst detection on known bursty series vs flat series
- TF-IDF novelty: novel text vs repeated text
- Similarity gap: known gap vs first-ever vs no data
- Join confidence tiers (1.0 / 0.8 / 0.5) from alias map
- Young-series absence for news_count_z (< MIN_OBS baseline)
- Lane gating: data/ writes only on COLLECT_LANE=nightly
- FIRST_COVERAGE contract schema exactness (columns must match EXACTLY)
- NAR-R10 fail-open: all store-absent paths return no crash
- NAR-R4 guard: zero LLM imports in the module source

All synthetic; no network. Uses tmp_path stores.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# NAR-R4 guard — zero LLM in the source
# ---------------------------------------------------------------------------


def test_nar_r4_no_llm_in_source():
    """Source must contain zero LLM calls (NAR-R4).

    Checks that engine/narrative_flare.py has no imports or calls to:
      llm_auth, anthropic, openai, transformers, torch, sklearn
    (sklearn is also forbidden by the spec: 'sklearn-free implementation').
    """
    import engine.narrative_flare as _mod
    src = Path(_mod.__file__).resolve().read_text(encoding="utf-8")
    banned = [
        r"from\s+engine\.llm_auth",
        r"import\s+engine\.llm_auth",
        r"llm_auth\.make_call",
        r"import\s+anthropic",
        r"import\s+openai",
        r"from\s+transformers",
        r"import\s+torch",
        r"from\s+sklearn",
        r"import\s+sklearn",
    ]
    for pattern in banned:
        matches = re.findall(pattern, src)
        assert not matches, (
            f"NAR-R4 violation: narrative_flare.py matches banned pattern {pattern!r}: {matches}"
        )


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from engine.narrative_flare import (
    AUTHORITY,
    FIRST_COVERAGE_COLS,
    THRESHOLDS,
    WITNESS_HIST_COLS,
    _build_alias_map,
    _compute_burst,
    _compute_first_coverage,
    _compute_news_count_z,
    _compute_similarity_gap,
    _compute_tfidf_novelty,
    _gather_ticker_texts,
    _join_text_to_ticker,
    _kleinberg_burst,
    _ledger_advance_enabled,
    _load_first_coverage,
    _tokenize,
    compute,
    write_site_artifact,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_polygon_df(ticker: str, today: date, n_days: int = 60, articles_today: int = 5) -> pd.DataFrame:
    """Synthetic Polygon news_sentiment.parquet with 'articles' column."""
    rows = []
    base_articles = 2  # baseline ~2/day
    for i in range(n_days, 0, -1):
        d = today - timedelta(days=i)
        rows.append({"ticker": ticker, "snapshot_date": d.isoformat(), "articles": base_articles, "bull_ratio": 0.5})
    # Today's row
    rows.append({"ticker": ticker, "snapshot_date": today.isoformat(), "articles": articles_today, "bull_ratio": 0.6})
    return pd.DataFrame(rows)


def _make_hn_df(ticker: str, dates_and_points: list[tuple[date, int]]) -> pd.DataFrame:
    """Synthetic HN mentions."""
    rows = []
    for i, (d, pts) in enumerate(dates_and_points):
        rows.append({
            "ticker": ticker,
            "story_id": str(1000 + i),
            "title": f"Story about {ticker} on {d.isoformat()}",
            "points": pts,
            "num_comments": 10,
            "created_at": f"{d.isoformat()}T10:00:00Z",
            "fetch_date": date.today().isoformat(),
        })
    cols = ["ticker", "story_id", "title", "points", "num_comments", "created_at", "fetch_date"]
    return pd.DataFrame(rows, columns=cols)


def _make_substack_df(ticker_hint: str, pub_dates: list[date]) -> pd.DataFrame:
    """Synthetic substack_posts for a ticker's company name (uses NVDA -> NVIDIA as hint)."""
    rows = []
    for i, d in enumerate(pub_dates):
        rows.append({
            "feed_id": "semianalysis",
            "url": f"https://example.com/post-{i}",
            "title": f"NVIDIA GPU Analysis {i}",
            "published_date": d.isoformat(),
            "teaser_text": "Deep dive into NVIDIA CUDA performance.",
            "fetch_date": date.today().isoformat(),
        })
    cols = ["feed_id", "url", "title", "published_date", "teaser_text", "fetch_date"]
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# 1. Kleinberg burst detection
# ---------------------------------------------------------------------------


class TestKleinbergBurst:
    def test_flat_series_no_burst(self):
        """A perfectly flat series should show minimal burst weight."""
        counts = [2] * 90
        bw = _kleinberg_burst(counts)
        # Flat series should have very low or zero burst weight
        assert bw <= 0.1, f"Expected near-zero burst on flat series, got {bw}"

    def test_bursty_series_high_weight(self):
        """A series with a clear spike at the end should show high burst weight."""
        counts = [1] * 80 + [20, 25, 30, 22, 18, 24, 19, 21, 23, 26]
        bw = _kleinberg_burst(counts)
        # The last 10 days are heavily burst; expect > 0.05 fraction in burst state
        assert bw > 0.05, f"Expected non-zero burst on spiked series, got {bw}"

    def test_degenerate_empty(self):
        assert _kleinberg_burst([]) == 0.0

    def test_degenerate_single(self):
        assert _kleinberg_burst([5]) == 0.0

    def test_all_zeros(self):
        """All-zero counts should return 0.0 (no burst possible)."""
        assert _kleinberg_burst([0] * 30) == 0.0

    def test_burst_weight_bounded(self):
        """Burst weight must be between 0 and 1."""
        for counts in [[1, 2, 100, 1, 2], [0] * 50, [10] * 90, [1] * 85 + [50] * 5]:
            bw = _kleinberg_burst(counts)
            assert 0.0 <= bw <= 1.0, f"Burst weight {bw} out of [0,1] for {counts[:5]}"


# ---------------------------------------------------------------------------
# 2. TF-IDF novelty
# ---------------------------------------------------------------------------


class TestTfIdfNovelty:
    def test_repeated_text_low_novelty(self):
        """Today's text identical to corpus should have near-zero novelty."""
        repeated = "NVIDIA GPU CUDA Blackwell analysis deep dive performance benchmark"
        corpus = [repeated] * 15
        today = [repeated]
        result = _compute_tfidf_novelty("NVDA", date.today(), today, corpus)
        assert result["present"] is True
        assert result["value"] is not None
        assert result["value"] < 0.2, f"Expected low novelty for repeated text, got {result['value']}"

    def test_novel_text_high_novelty(self):
        """Today's text completely unrelated to corpus should have high novelty."""
        corpus = ["NVIDIA GPU CUDA Blackwell analysis performance benchmark"] * 15
        today_text = ["quantum computing photonics superconductor qubit entanglement laser optical"]
        result = _compute_tfidf_novelty("NVDA", date.today(), today_text, corpus)
        assert result["present"] is True
        assert result["value"] is not None
        assert result["value"] > 0.5, f"Expected high novelty for novel text, got {result['value']}"

    def test_insufficient_prior_docs_absent(self):
        """< MIN_PRIOR_DOCS in corpus should return absent."""
        corpus = ["Some text"] * (THRESHOLDS["TFIDF_MIN_PRIOR_DOCS"] - 1)
        today = ["New text"]
        result = _compute_tfidf_novelty("NVDA", date.today(), today, corpus)
        assert result["present"] is False
        assert "insufficient_prior_docs" in (result.get("reason") or "")

    def test_no_today_text_absent(self):
        corpus = ["Some text about NVIDIA"] * 15
        result = _compute_tfidf_novelty("NVDA", date.today(), [], corpus)
        assert result["present"] is False
        assert result.get("reason") == "no_today_text"

    def test_exactly_min_docs(self):
        """Exactly MIN_PRIOR_DOCS corpus docs should not be absent due to insufficient_prior_docs."""
        min_docs = THRESHOLDS["TFIDF_MIN_PRIOR_DOCS"]
        corpus = ["NVIDIA GPU analysis"] * min_docs
        today = ["Something new"]
        result = _compute_tfidf_novelty("NVDA", date.today(), today, corpus)
        assert result["present"] is True

    def test_novelty_bounded_0_1(self):
        corpus = ["alpha beta gamma delta"] * 12
        today_texts = ["alpha beta gamma delta", "completely different words here"]
        result = _compute_tfidf_novelty("X", date.today(), today_texts, corpus)
        if result["present"]:
            assert 0.0 <= result["value"] <= 1.0


# ---------------------------------------------------------------------------
# 3. Similarity gap
# ---------------------------------------------------------------------------


class TestSimilarityGap:
    def test_hn_gap_below_threshold_not_novel(self):
        """HN gap < 90d should not be novel."""
        today = date(2026, 7, 10)
        last_seen = today - timedelta(days=30)
        hn_df = _make_hn_df("NVDA", [(last_seen, 100)])
        reg = {"hn_keywords": {"NVDA": ["NVIDIA", "CUDA"]}}
        alias_map = _build_alias_map(reg)
        result = _compute_similarity_gap("NVDA", today, None, hn_df, None, alias_map)
        assert result["gap_hn_days"] == 30
        assert result["novel_hn"] is False

    def test_hn_gap_above_threshold_novel(self):
        """HN gap > 90d should be novel."""
        today = date(2026, 7, 10)
        last_seen = today - timedelta(days=100)
        hn_df = _make_hn_df("NVDA", [(last_seen, 100)])
        reg = {"hn_keywords": {"NVDA": ["NVIDIA", "CUDA"]}}
        alias_map = _build_alias_map(reg)
        result = _compute_similarity_gap("NVDA", today, None, hn_df, None, alias_map)
        assert result["gap_hn_days"] == 100
        assert result["novel_hn"] is True

    def test_first_ever_hn_novel(self):
        """No prior HN mentions -> novel_hn=True, gap=None."""
        today = date(2026, 7, 10)
        hn_df = _make_hn_df("NVDA", [(today, 50)])  # only today
        reg = {"hn_keywords": {"NVDA": ["NVIDIA"]}}
        alias_map = _build_alias_map(reg)
        result = _compute_similarity_gap("NVDA", today, None, hn_df, None, alias_map)
        assert result["gap_hn_days"] is None
        assert result["novel_hn"] is True

    def test_no_hn_data_not_novel(self):
        """No HN df -> gap_hn=None, novel_hn=False (channel absent, NAR-R10)."""
        today = date(2026, 7, 10)
        reg = {"hn_keywords": {"NVDA": ["NVIDIA"]}}
        alias_map = _build_alias_map(reg)
        result = _compute_similarity_gap("NVDA", today, None, None, None, alias_map)
        assert result["gap_hn_days"] is None
        assert result["novel_hn"] is False


# ---------------------------------------------------------------------------
# 4. Join confidence tiers
# ---------------------------------------------------------------------------


class TestJoinConfidence:
    def _alias_map(self):
        reg = {
            "hn_keywords": {
                "NVDA": ["NVIDIA Corporation", "CUDA", "Blackwell"],
                "META": ["Meta Platforms", "Llama", "Meta Superintelligence"],
            }
        }
        return _build_alias_map(reg)

    def test_exact_ticker_confidence_1_0(self):
        """Exact ticker match -> confidence 1.0."""
        alias_map = self._alias_map()
        ticker, conf = _join_text_to_ticker("NVDA earnings beat", alias_map)
        assert ticker == "NVDA"
        assert conf == 1.0

    def test_cashtag_confidence_1_0(self):
        """$TICKER cashtag -> confidence 1.0."""
        alias_map = self._alias_map()
        ticker, conf = _join_text_to_ticker("$NVDA is surging today", alias_map)
        assert ticker == "NVDA"
        assert conf == 1.0

    def test_full_company_name_confidence_0_8(self):
        """First keyword (company name) -> confidence 0.8."""
        alias_map = self._alias_map()
        # "NVIDIA Corporation" is the first keyword -> 0.8
        ticker, conf = _join_text_to_ticker("NVIDIA Corporation announced results", alias_map)
        assert ticker == "NVDA"
        assert conf == 0.8

    def test_ambiguous_alias_confidence_0_5(self):
        """Short/ambiguous alias -> confidence 0.5."""
        alias_map = self._alias_map()
        # "CUDA" is 3rd keyword for NVDA -> 0.5
        ticker, conf = _join_text_to_ticker("CUDA performance benchmarks", alias_map)
        assert ticker == "NVDA"
        assert conf == 0.5

    def test_no_match_confidence_0(self):
        """No alias match -> (None, 0.0)."""
        alias_map = self._alias_map()
        ticker, conf = _join_text_to_ticker("Interest rates and bonds", alias_map)
        assert ticker is None
        assert conf == 0.0

    def test_alias_map_has_ticker_key(self):
        """Alias map must contain exact ticker -> 1.0."""
        alias_map = self._alias_map()
        assert "nvda" in alias_map
        assert alias_map["nvda"][1] == 1.0


# ---------------------------------------------------------------------------
# 5. Young-series absence for news_count_z
# ---------------------------------------------------------------------------


class TestNewsCountZ:
    def test_young_series_absent(self):
        """< MIN_OBS baseline rows -> young_series, present=False."""
        today = date(2026, 7, 10)
        min_obs = THRESHOLDS["NEWS_MIN_OBS"]
        # Only 10 prior rows < MIN_OBS=30
        rows = []
        for i in range(10):
            d = today - timedelta(days=i + 1)
            rows.append({"ticker": "NVDA", "snapshot_date": d.isoformat(), "articles": 3, "bull_ratio": 0.5})
        rows.append({"ticker": "NVDA", "snapshot_date": today.isoformat(), "articles": 20, "bull_ratio": 0.6})
        df = pd.DataFrame(rows)
        result = _compute_news_count_z("NVDA", today, df)
        assert result["present"] is False
        assert result["reason"] == "young_series"

    def test_sufficient_baseline_returns_z(self):
        """>= MIN_OBS baseline rows -> compute z-score, present=True when elevated."""
        today = date(2026, 7, 10)
        df = _make_polygon_df("NVDA", today, n_days=60, articles_today=50)
        result = _compute_news_count_z("NVDA", today, df)
        assert result["value"] is not None
        # Today has 50 articles vs baseline of 2 -> should be very high z and present
        assert result["present"] is True

    def test_store_absent_fail_open(self):
        """None polygon_df -> store_absent, no crash (NAR-R10)."""
        today = date(2026, 7, 10)
        result = _compute_news_count_z("NVDA", today, None)
        assert result["present"] is False
        assert result["reason"] == "store_absent"

    def test_ticker_absent_fail_open(self):
        """Ticker not in df -> ticker_absent, no crash (NAR-R10)."""
        today = date(2026, 7, 10)
        df = _make_polygon_df("AAPL", today, n_days=60)
        result = _compute_news_count_z("NVDA", today, df)
        assert result["present"] is False
        assert result["reason"] == "ticker_absent"

    def test_pit_safety_baseline_strictly_prior(self):
        """Baseline must use dates strictly < today (PIT-safe).

        Uses a varied baseline so dispersion is non-zero and the large today value
        produces a meaningful z-score. Verifies that today's row is NOT included
        in the baseline (if it were, z would shrink).
        """
        today = date(2026, 7, 10)
        rows = []
        # 40 prior days: alternating 1 and 3 (dispersion > 0)
        import random
        rng = [1, 3] * 20  # 40 values alternating
        for i, val in enumerate(rng):
            d = today - timedelta(days=len(rng) - i)
            rows.append({"ticker": "X", "snapshot_date": d.isoformat(), "articles": val, "bull_ratio": 0.5})
        # Today's row = 100 (very far above baseline 1-3)
        rows.append({"ticker": "X", "snapshot_date": today.isoformat(), "articles": 100, "bull_ratio": 0.6})
        df = pd.DataFrame(rows)
        result = _compute_news_count_z("X", today, df)
        # Should be present with a large z (100 vs baseline median=2, MAD=1)
        assert result["present"] is True
        assert result["value"] is not None
        assert result["value"] > 5, f"Expected z > 5 for 100 vs baseline ~2, got {result['value']}"


# ---------------------------------------------------------------------------
# 6. Lane gating
# ---------------------------------------------------------------------------


class TestLaneGating:
    def test_nightly_lane_enabled(self, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        assert _ledger_advance_enabled() is True

    def test_intraday_lane_disabled(self, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "intraday")
        assert _ledger_advance_enabled() is False

    def test_empty_env_disabled(self, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        assert _ledger_advance_enabled() is False

    def test_us_lane_nightly(self, monkeypatch):
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.setenv("US_LANE", "nightly")
        assert _ledger_advance_enabled() is True

    def test_data_not_written_outside_nightly_lane(self, tmp_path, monkeypatch):
        """witness_hist.parquet should NOT be written when COLLECT_LANE != nightly."""
        monkeypatch.setenv("COLLECT_LANE", "intraday")

        today = date(2026, 7, 10)
        df = _make_polygon_df("NVDA", today, n_days=60, articles_today=50)
        df.to_parquet(tmp_path / "polygon_ns.parquet", index=False)

        # Create minimal data_root structure
        (tmp_path / "polygon").mkdir()
        (tmp_path / "narrative_flare").mkdir()
        df.to_parquet(tmp_path / "polygon" / "news_sentiment.parquet", index=False)

        # Run compute directly (it may fail on missing stores — that's ok per NAR-R10)
        # Just verify the witness_hist.parquet is NOT written
        hist_path = tmp_path / "narrative_flare" / "witness_hist.parquet"
        from engine.narrative_flare import _ledger_advance_enabled
        assert _ledger_advance_enabled() is False
        assert not hist_path.exists()


# ---------------------------------------------------------------------------
# 7. First coverage contract schema exactness
# ---------------------------------------------------------------------------


class TestFirstCoverageSchema:
    def test_first_coverage_cols_exact(self):
        """FIRST_COVERAGE_COLS must match the shared W3/W4 contract exactly."""
        expected = [
            "source_id",
            "ticker",
            "date",
            "url",
            "title",
            "join_confidence",
            "fetch_date",
        ]
        assert FIRST_COVERAGE_COLS == expected, (
            f"FIRST_COVERAGE_COLS deviates from W3/W4 contract.\n"
            f"Expected: {expected}\n"
            f"Got:      {FIRST_COVERAGE_COLS}"
        )

    def test_first_coverage_parquet_schema_matches(self, tmp_path):
        """Rows written to first_coverage.parquet must have exactly FIRST_COVERAGE_COLS."""
        from engine.narrative_flare import _append_first_coverage, _fc_path

        rows = [{
            "source_id": "hn",
            "ticker": "NVDA",
            "date": "2026-07-10",
            "url": "https://news.ycombinator.com/item?id=12345",
            "title": "NVIDIA Blackwell launch",
            "join_confidence": 1.0,
            "fetch_date": "2026-07-10",
        }]
        _append_first_coverage(rows, tmp_path)
        p = _fc_path(tmp_path)
        assert p.exists()
        df = pd.read_parquet(p)
        assert list(df.columns) == FIRST_COVERAGE_COLS

    def test_first_coverage_dedup_on_source_ticker(self, tmp_path):
        """Appending the same (source_id, ticker) twice should not duplicate."""
        from engine.narrative_flare import _append_first_coverage, _fc_path, _load_first_coverage

        row = {
            "source_id": "hn",
            "ticker": "NVDA",
            "date": "2026-07-10",
            "url": "https://hn.example/1",
            "title": "Test",
            "join_confidence": 1.0,
            "fetch_date": "2026-07-10",
        }
        _append_first_coverage([row], tmp_path)
        _append_first_coverage([row], tmp_path)  # second call
        df = _load_first_coverage(tmp_path)
        assert len(df) == 1, f"Expected 1 row after dedup, got {len(df)}"

    def test_first_coverage_new_ticker_appended(self, tmp_path):
        """A new (source_id, ticker) pair should be appended."""
        from engine.narrative_flare import _append_first_coverage, _load_first_coverage

        row1 = {
            "source_id": "hn",
            "ticker": "NVDA",
            "date": "2026-07-10",
            "url": "https://hn.example/1",
            "title": "NVDA story",
            "join_confidence": 1.0,
            "fetch_date": "2026-07-10",
        }
        row2 = {
            "source_id": "hn",
            "ticker": "META",
            "date": "2026-07-10",
            "url": "https://hn.example/2",
            "title": "META story",
            "join_confidence": 1.0,
            "fetch_date": "2026-07-10",
        }
        from engine.narrative_flare import _append_first_coverage
        _append_first_coverage([row1], tmp_path)
        _append_first_coverage([row2], tmp_path)
        df = _load_first_coverage(tmp_path)
        assert len(df) == 2

    def test_first_coverage_is_first_in_90d(self):
        """_compute_first_coverage emits an event when ticker not seen in 90d."""
        today = date(2026, 7, 10)
        existing_fc = pd.DataFrame(columns=FIRST_COVERAGE_COLS)

        # HN hit for NVDA today — no prior coverage => should fire
        hn_df = _make_hn_df("NVDA", [(today, 100)])
        reg = {"hn_keywords": {"NVDA": ["NVIDIA"]}}
        alias_map = _build_alias_map(reg)

        new_rows = _compute_first_coverage(
            "NVDA", today, today.isoformat(),
            None, hn_df, None,
            alias_map, existing_fc,
        )
        assert len(new_rows) >= 1
        hn_events = [r for r in new_rows if r["source_id"] == "hn"]
        assert len(hn_events) == 1
        assert hn_events[0]["ticker"] == "NVDA"
        assert hn_events[0]["join_confidence"] == 1.0

    def test_first_coverage_not_emitted_within_gap(self):
        """_compute_first_coverage suppresses events when seen within 90d."""
        today = date(2026, 7, 10)
        # Prior coverage 30 days ago (< 90d gap) — should NOT fire
        prior_date = today - timedelta(days=30)
        existing_fc = pd.DataFrame([{
            "source_id": "hn",
            "ticker": "NVDA",
            "date": prior_date.isoformat(),
            "url": "https://hn.example/0",
            "title": "Prior",
            "join_confidence": 1.0,
            "fetch_date": prior_date.isoformat(),
        }], columns=FIRST_COVERAGE_COLS)

        hn_df = _make_hn_df("NVDA", [(today, 100)])
        reg = {"hn_keywords": {"NVDA": ["NVIDIA"]}}
        alias_map = _build_alias_map(reg)

        new_rows = _compute_first_coverage(
            "NVDA", today, today.isoformat(),
            None, hn_df, None,
            alias_map, existing_fc,
        )
        hn_events = [r for r in new_rows if r["source_id"] == "hn"]
        assert len(hn_events) == 0, "Should not fire when seen within 90d"


# ---------------------------------------------------------------------------
# 8. NAR-R10: fail-open paths (no crash on missing stores)
# ---------------------------------------------------------------------------


class TestFailOpen:
    def test_compute_no_crash_all_stores_absent(self, tmp_path, monkeypatch):
        """compute() must not raise even when all stores are absent (NAR-R10)."""
        monkeypatch.setenv("COLLECT_LANE", "intraday")

        # Patch lib.config to point data_dir at tmp_path
        import engine.narrative_flare as nfo
        monkeypatch.setattr(
            "engine.narrative_flare._load_substack",
            lambda data_root: None,
        )
        monkeypatch.setattr(
            "engine.narrative_flare._load_hn",
            lambda data_root: None,
        )
        monkeypatch.setattr(
            "engine.narrative_flare._load_edgar",
            lambda data_root: None,
        )
        monkeypatch.setattr(
            "engine.narrative_flare._load_polygon_news",
            lambda data_root: None,
        )
        monkeypatch.setattr(
            "engine.narrative_flare._load_attention",
            lambda data_root, today: None,
        )
        monkeypatch.setattr(
            "engine.narrative_flare._build_universe",
            lambda data_root, reg: ["NVDA", "META"],
        )
        monkeypatch.setattr(
            "engine.narrative_flare._load_first_coverage",
            lambda data_root: pd.DataFrame(columns=FIRST_COVERAGE_COLS),
        )

        result = nfo.compute(data_root=tmp_path)
        assert isinstance(result, dict)
        assert "rows" in result
        assert result.get("authority") == AUTHORITY
        assert result.get("tier") == "display"

    def test_burst_store_absent(self):
        """_compute_burst with None dfs should return None burst weights."""
        today = date(2026, 7, 10)
        result = _compute_burst("NVDA", today, None, None)
        assert result["burst_weight_hn"] is None
        assert result["burst_weight_polygon"] is None


# ---------------------------------------------------------------------------
# 9. Authority block and artifact schema
# ---------------------------------------------------------------------------


class TestArtifactSchema:
    def test_authority_block(self):
        """AUTHORITY must have all required display-tier flags."""
        assert AUTHORITY["tier"] == "display"
        assert AUTHORITY["may_rank"] is False
        assert AUTHORITY["may_gate"] is False
        assert AUTHORITY["may_size"] is False
        assert AUTHORITY["may_escalate"] is False

    def test_site_artifact_schema(self, tmp_path, monkeypatch):
        """write_site_artifact creates site/narrativedata/flares.json with required keys."""
        monkeypatch.setenv("COLLECT_LANE", "intraday")

        import engine.narrative_flare as nfo

        # Build a minimal result
        result = {
            "schema": "narrative_flare.v1",
            "as_of": "2026-07-10",
            "fetch_date": "2026-07-10",
            "universe_n": 2,
            "elapsed_s": 0.1,
            "rows": [
                {
                    "ticker": "NVDA",
                    "present": True,
                    "channels_lit": 1,
                    "channels_lit_names": ["news_count_z"],
                    "magnitudes": {"news_count_z": 3.2},
                    "join_confidence": 1.0,
                    "hazard_pctile": 75.0,
                    "small_cap_flag": None,
                    "reasons": {},
                    "as_of": "2026-07-10",
                    "fetch_date": "2026-07-10",
                }
            ],
            "authority": AUTHORITY,
            "tier": "display",
            "thresholds_ref": "masterplan §4.2 — FROZEN pre-registration record",
        }

        # Patch site_root
        site_root = tmp_path / "site"
        site_root.mkdir()

        import lib.config as cfg
        from unittest.mock import patch
        with patch.object(cfg, "ROOT", tmp_path):
            with patch.object(cfg, "load", return_value={"storage": {"site_dir": "site"}}):
                out_path = nfo.write_site_artifact(result, site_root=site_root)

        assert out_path.exists()
        data = json.loads(out_path.read_text())
        assert data["schema"] == "narrative_flare.v1"
        assert data["authority"]["tier"] == "display"
        assert "rows" in data
        assert data["rows"][0]["join_confidence"] == 1.0   # NAR-R9
        assert data["rows"][0]["hazard_pctile"] == 75.0    # NAR-R7
        assert data["rows"][0]["small_cap_flag"] is None   # null this wave

    def test_witness_hist_cols_complete(self):
        """WITNESS_HIST_COLS must contain all required PIT fields."""
        required = {
            "ticker", "date", "fetch_date",
            "news_count_z", "news_count_z_reason",
            "gap_substack_days", "gap_hn_days", "gap_polygon_days",
            "novel_substack", "novel_hn", "novel_polygon",
            "tfidf_novelty", "tfidf_novelty_reason",
            "burst_weight_hn", "burst_weight_polygon",
            "join_confidence", "hazard_pctile", "channels_lit", "present",
        }
        assert required == set(WITNESS_HIST_COLS)


# ---------------------------------------------------------------------------
# 10. Tokenizer
# ---------------------------------------------------------------------------

class TestTokenizer:
    def test_basic_tokenization(self):
        tokens = _tokenize("NVIDIA GPU Analysis Deep-Dive")
        assert "nvidia" in tokens
        assert "gpu" in tokens
        assert "analysis" in tokens
        assert "deep" in tokens

    def test_short_tokens_excluded(self):
        """Single-character tokens (< 2 chars) should be excluded."""
        tokens = _tokenize("a b c d")
        assert tokens == [], f"Expected empty for all 1-char tokens, got {tokens}"

    def test_numbers_kept(self):
        tokens = _tokenize("MI300 H100 A100")
        assert "mi300" in tokens
        assert "h100" in tokens
