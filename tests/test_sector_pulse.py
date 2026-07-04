"""Tests for engine.sector_pulse — the shared sector-rotation data product.

Covers:
  - heat tier classification boundaries (all five tiers, with and without archive history)
  - rank-delta and score-delta computation from synthetic archive snapshots
  - short-history / None-safety (fewer archive rows than the look-back requires)
  - ticker mapping respects added/removed dates (live members only)
  - write_pulse contract: schema/as_of present, valid JSON
  - never-fatal: archive entirely absent / corrupted → None/empty, never raises

All tests are hermetic (monkeypatched); no real file I/O or network calls.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from datetime import date

import pandas as pd
import pytest

import engine.sector_pulse as sp


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_theme(tid: str, score: int, rank: int, label: str = "dominant",
                reco: str = "accumulate", net_ad: int = 5,
                delta_5d: float = 0.02, rank_5d: int = 0,
                pct50: float = 0.8, clean_entry_flag: bool = True,
                momentum_score: float = 0.7, long_sign: int = 1) -> dict:
    """Build a minimal theme_intel theme entry sufficient for _build_theme_row."""
    return {
        "id": tid,
        "name": f"Theme {tid}",
        "name_zh": f"主题 {tid}",
        "category": "Tech",
        "score": score,
        "rank": rank,
        "label": label,
        "reco": reco,
        "net_ad": net_ad,
        "delta_5d": delta_5d,
        "rank_5d": rank_5d,
        "perf": {"5d": {"rel": delta_5d, "ret": delta_5d + 0.01},
                 "20d": {"rel": 0.05, "ret": 0.06},
                 "60d": {"rel": 0.03, "ret": 0.04},
                 "ytd": {"rel": 0.1, "ret": 0.12}},
        "breadth": {"pct50": pct50, "pct200": 0.7, "nh": 5, "nl": 0, "n": 20},
        "textures": {
            "clean_entry": {"flag": clean_entry_flag, "quality": 0.75},
            "rollover_risk": {"risk": 0.1, "band": "low"},
            "bull_age": {"days": 30},
            "overbought": {"value": 0.4},
        },
        "mtf": {
            "momentum_score": momentum_score,
            "trend_aligned": True,
            "confluence": {"long_sign": long_sign, "grade": "CONFIRM"},
        },
    }


def _make_ti(themes: list[dict]) -> dict:
    """Wrap themes into a minimal theme_intel payload."""
    return {
        "as_of": "2026-07-02",
        "themes": themes,
        "rotation_5d": {"climbers": [], "fallers": []},
    }


def _make_archive_df(rows: list[dict]) -> pd.DataFrame:
    """Build a synthetic signal-archive DataFrame with snapshot_json column.

    Each row in `rows` is {asof, themes: [{id, score, rank}, ...]}.
    """
    records = []
    for r in rows:
        snap = {"as_of": r["asof"], "themes": r["themes"]}
        records.append({"asof": r["asof"], "snapshot_json": json.dumps(snap)})
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Heat tier classification
# ---------------------------------------------------------------------------

class TestHeatTier:
    def test_broken_label_always_broken(self):
        tier = sp._heat_tier(rank=1, n_themes=20, label="deteriorating",
                             rank_delta_5d=5, score_delta_5d=10.0)
        assert tier == "broken"

    def test_broken_overrides_top_rank(self):
        # Even rank=1 deteriorating is "broken", not "hot"
        assert sp._heat_tier(1, 20, "deteriorating", None, None) == "broken"

    def test_cooling_from_label(self):
        # label=fading with no rank drop → cooling
        tier = sp._heat_tier(rank=5, n_themes=20, label="fading",
                             rank_delta_5d=0, score_delta_5d=0.0)
        assert tier == "cooling"

    def test_cooling_from_rank_drop(self):
        # rank_delta_5d <= -3 → cooling (rank worsened: was rank 5, now rank 8 → delta = -3)
        tier = sp._heat_tier(rank=8, n_themes=20, label="emerging",
                             rank_delta_5d=-3, score_delta_5d=0.0)
        assert tier == "cooling"

    def test_cooling_beats_hot(self):
        # Top-quartile emerging but rank dropped 3+ → cooling, not hot
        tier = sp._heat_tier(rank=2, n_themes=20, label="emerging",
                             rank_delta_5d=-4, score_delta_5d=0.0)
        assert tier == "cooling"

    def test_heating_rank_delta(self):
        # rank improved 3+ positions AND label is emerging → heating
        tier = sp._heat_tier(rank=5, n_themes=20, label="emerging",
                             rank_delta_5d=4, score_delta_5d=0.0)
        assert tier == "heating"

    def test_heating_score_delta(self):
        # score jumped 6+ points AND label is dominant → heating
        tier = sp._heat_tier(rank=5, n_themes=20, label="dominant",
                             rank_delta_5d=0, score_delta_5d=7.0)
        assert tier == "heating"

    def test_heating_requires_upward_label(self):
        # rank improved 5 positions but label is neutral → not heating
        tier = sp._heat_tier(rank=5, n_themes=20, label="neutral",
                             rank_delta_5d=5, score_delta_5d=10.0)
        # Should be idle (not heating, not hot, not cooling, not broken)
        assert tier in ("idle", "hot")   # hot possible if in top quartile
        # rank=5 in 20 themes → top_n = 5 → just at boundary; neutral label → not hot
        assert tier == "idle"

    def test_hot_top_quartile_dominant(self):
        # rank=4, n=20 → top_n=5, dominant, no rank drop → hot
        tier = sp._heat_tier(rank=4, n_themes=20, label="dominant",
                             rank_delta_5d=0, score_delta_5d=0.0)
        assert tier == "hot"

    def test_hot_boundary_exact(self):
        # rank=5, n=20 → top_n=5 → exactly at boundary → hot
        tier = sp._heat_tier(rank=5, n_themes=20, label="emerging",
                             rank_delta_5d=0, score_delta_5d=0.0)
        assert tier == "hot"

    def test_hot_boundary_just_outside(self):
        # rank=6, n=20 → top_n=5 → just outside → idle
        tier = sp._heat_tier(rank=6, n_themes=20, label="dominant",
                             rank_delta_5d=0, score_delta_5d=0.0)
        assert tier == "idle"

    def test_idle_mid_rank_neutral(self):
        tier = sp._heat_tier(rank=15, n_themes=30, label="neutral",
                             rank_delta_5d=1, score_delta_5d=2.0)
        assert tier == "idle"

    def test_none_deltas_treated_as_zero(self):
        # None deltas (short history) → treated as 0, shouldn't crash
        tier = sp._heat_tier(rank=15, n_themes=30, label="emerging",
                             rank_delta_5d=None, score_delta_5d=None)
        # Not heating (delta=0 < 3), not cooling, not broken → idle or hot depending on rank
        assert tier in ("idle",)   # rank=15 in 30 → top_n=7 → not hot

    def test_none_deltas_top_rank_hot(self):
        # None deltas at top-quartile dominant → hot (not enough history, but current state hot)
        tier = sp._heat_tier(rank=2, n_themes=20, label="dominant",
                             rank_delta_5d=None, score_delta_5d=None)
        assert tier == "hot"


# ---------------------------------------------------------------------------
# Archive snapshot helpers
# ---------------------------------------------------------------------------

class TestArchiveHelpers:
    def test_rank_map_at_returns_correct_session(self):
        snaps = [
            {"asof": "2026-06-26", "themes": [{"id": "t1", "rank": 10}, {"id": "t2", "rank": 5}]},
            {"asof": "2026-06-27", "themes": [{"id": "t1", "rank": 8}, {"id": "t2", "rank": 6}]},
            {"asof": "2026-06-28", "themes": [{"id": "t1", "rank": 3}, {"id": "t2", "rank": 9}]},
        ]
        # offset=1 → row at index -(1+1) = -2 → "2026-06-27"
        m = sp._rank_map_at(snaps, 1)
        assert m["t1"] == 8
        assert m["t2"] == 6

        # offset=2 → row at index -(2+1) = -3 → "2026-06-26"
        m2 = sp._rank_map_at(snaps, 2)
        assert m2["t1"] == 10

    def test_rank_map_at_short_history_returns_empty(self):
        snaps = [{"asof": "2026-06-28", "themes": [{"id": "t1", "rank": 3}]}]
        # offset=5 → need 6 rows, only 1 → empty
        assert sp._rank_map_at(snaps, 5) == {}

    def test_score_map_at_returns_correct_value(self):
        snaps = [
            {"asof": "2026-06-25", "themes": [{"id": "t1", "score": 60}]},
            {"asof": "2026-06-28", "themes": [{"id": "t1", "score": 70}]},
        ]
        m = sp._score_map_at(snaps, 1)
        assert m["t1"] == 60

    def test_score_map_at_too_short_returns_empty(self):
        snaps = []
        assert sp._score_map_at(snaps, 5) == {}


# ---------------------------------------------------------------------------
# build_theme_row rank/score delta computation
# ---------------------------------------------------------------------------

class TestBuildThemeRow:
    def _make_maps(self, tid: str, rank_1d: int, rank_5d: int, rank_20d: int,
                   score_5d: float, score_20d: float):
        return (
            {tid: rank_1d},
            {tid: rank_5d},
            {tid: rank_20d},
            {tid: score_5d},
            {tid: score_20d},
        )

    def test_rank_delta_positive_means_improved(self):
        th = _make_theme("t1", score=75, rank=3, label="dominant")
        r1, r5, r20, s5, s20 = self._make_maps("t1", 5, 8, 12, 68, 60)
        row = sp._build_theme_row(th, 20, r1, r5, r20, s5, s20)
        # rank_delta_1d = rank_1d_ago - rank_now = 5 - 3 = +2 (improved by 2 positions)
        assert row["rank_delta_1d"] == 2
        # rank_delta_5d = 8 - 3 = +5
        assert row["rank_delta_5d"] == 5
        # rank_delta_20d = 12 - 3 = +9
        assert row["rank_delta_20d"] == 9
        # score_delta_5d = 75 - 68 = +7
        assert row["score_delta_5d"] == 7
        # score_delta_20d = 75 - 60 = +15
        assert row["score_delta_20d"] == 15

    def test_rank_delta_negative_means_fell(self):
        th = _make_theme("t1", score=50, rank=10, label="neutral")
        r1, r5, r20, s5, s20 = self._make_maps("t1", 7, 5, 3, 55, 60)
        row = sp._build_theme_row(th, 20, r1, r5, r20, s5, s20)
        # rank worsened: was rank 5, now rank 10 → delta = 5 - 10 = -5
        assert row["rank_delta_5d"] == -5
        # score fell: was 55, now 50 → delta = 50 - 55 = -5
        assert row["score_delta_5d"] == -5

    def test_none_when_ticker_not_in_archive(self):
        th = _make_theme("t1", score=70, rank=5, label="emerging")
        row = sp._build_theme_row(th, 20, {}, {}, {}, {}, {})
        assert row["rank_delta_1d"] is None
        assert row["rank_delta_5d"] is None
        assert row["rank_delta_20d"] is None
        assert row["score_delta_5d"] is None
        assert row["score_delta_20d"] is None

    def test_heat_tier_computed(self):
        # rank=2, 20 themes, dominant, rank improved 5 → heating
        th = _make_theme("t1", score=80, rank=2, label="dominant")
        r1, r5, r20, s5, s20 = self._make_maps("t1", 4, 7, 10, 74, 65)
        row = sp._build_theme_row(th, 20, r1, r5, r20, s5, s20)
        # rank_delta_5d = 7 - 2 = 5 ≥ 3, dominant → heating
        assert row["heat"] == "heating"

    def test_clean_entry_extracted(self):
        th = _make_theme("t1", score=70, rank=5, label="dominant", clean_entry_flag=True)
        row = sp._build_theme_row(th, 20, {}, {}, {}, {}, {})
        assert row["clean_entry"]["flag"] is True

    def test_momentum_score_extracted(self):
        th = _make_theme("t1", score=70, rank=5, label="dominant", momentum_score=0.65)
        row = sp._build_theme_row(th, 20, {}, {}, {}, {}, {})
        assert row["momentum_score"] == pytest.approx(0.65)


# ---------------------------------------------------------------------------
# build_pulse integration (monkeypatched)
# ---------------------------------------------------------------------------

class TestBuildPulse:
    def test_returns_none_when_no_theme_intel(self, monkeypatch):
        monkeypatch.setattr(sp, "_load_theme_intel", lambda r: None)
        assert sp.build_pulse("us") is None

    def test_returns_none_when_themes_empty(self, monkeypatch):
        monkeypatch.setattr(sp, "_load_theme_intel", lambda r: {"as_of": "2026-07-02", "themes": []})
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: [])
        assert sp.build_pulse("us") is None

    def test_basic_payload_shape(self, monkeypatch):
        themes = [
            _make_theme("t1", 80, 1, "dominant"),
            _make_theme("t2", 60, 2, "emerging"),
            _make_theme("t3", 40, 3, "neutral"),
        ]
        monkeypatch.setattr(sp, "_load_theme_intel", lambda r: _make_ti(themes))
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: [])
        result = sp.build_pulse("us")
        assert result is not None
        assert result["schema"] == sp.SCHEMA
        assert result["as_of"] == "2026-07-02"
        assert result["region"] == "us"
        assert result["n_themes"] == 3
        assert len(result["themes"]) == 3
        # sorted by rank ascending
        assert [r["rank"] for r in result["themes"]] == [1, 2, 3]
        assert "heating" in result
        assert "cooling" in result

    def test_heating_cooling_lists_correct(self, monkeypatch):
        # t1: dominant, rank 1; 5-session rank delta = 5 - 1 = +4 → heating
        # t2: fading, rank 5, no rank drop → cooling (from label alone)
        # t3: neutral, rank 15/20, rank_delta_5d = 15 - 15 = 0 → idle
        #     (t3 rank stays flat at 15, so delta = 0, no cooling trigger)
        themes = [
            _make_theme("t1", 80, 1, "dominant"),
            _make_theme("t2", 65, 5, "fading"),
            _make_theme("t3", 45, 15, "neutral"),
        ]
        # 7 archive rows so we have 5-session look-back; t3 stays flat at rank 15
        old_snap = {"asof": "2026-06-25",
                    "themes": [{"id": "t1", "rank": 5, "score": 73},
                                {"id": "t2", "rank": 4, "score": 62},
                                {"id": "t3", "rank": 15, "score": 43}]}
        archive_rows = [old_snap] * 6 + [
            {"asof": "2026-07-02", "themes": [{"id": "t1", "rank": 1, "score": 80},
                                               {"id": "t2", "rank": 5, "score": 65},
                                               {"id": "t3", "rank": 15, "score": 45}]}
        ]
        monkeypatch.setattr(sp, "_load_theme_intel", lambda r: _make_ti(themes))
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: archive_rows)
        result = sp.build_pulse("us")
        assert "t1" in result["heating"]
        assert "t2" in result["cooling"]
        assert "t3" not in result["heating"]
        assert "t3" not in result["cooling"]

    def test_short_history_none_deltas(self, monkeypatch):
        # Only 3 archive rows — not enough for 5-session look-back (needs 6)
        # Rows sorted oldest→newest; _rank_map_at(snaps, 1) → snaps[-2] = "2026-07-01"
        themes = [_make_theme("t1", 70, 1, "dominant")]
        archive_rows = [
            {"asof": "2026-06-30", "themes": [{"id": "t1", "rank": 3, "score": 63}]},
            {"asof": "2026-07-01", "themes": [{"id": "t1", "rank": 2, "score": 67}]},
            {"asof": "2026-07-02", "themes": [{"id": "t1", "rank": 1, "score": 70}]},
        ]
        monkeypatch.setattr(sp, "_load_theme_intel", lambda r: _make_ti(themes))
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: archive_rows)
        result = sp.build_pulse("us")
        t1_row = result["themes"][0]
        # 5-session look-back needs 6 rows; only 3 → None
        assert t1_row["rank_delta_5d"] is None
        assert t1_row["score_delta_5d"] is None
        # 1-session look-back needs 2 rows; we have 3 → resolves.
        # snaps[-2] = "2026-07-01" row, rank=2; current rank=1 → delta = 2 - 1 = +1
        assert t1_row["rank_delta_1d"] == 1

    def test_never_raises_on_malformed_theme(self, monkeypatch):
        # One bad theme, one good — bad one should be skipped, good one returned
        bad_theme = {"id": None}  # will cause issues in _build_theme_row
        good_theme = _make_theme("t1", 70, 1, "dominant")
        monkeypatch.setattr(sp, "_load_theme_intel",
                            lambda r: _make_ti([bad_theme, good_theme]))
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: [])
        result = sp.build_pulse("us")
        # Should return a result with just the good theme (bad silently dropped)
        assert result is not None
        ids = [r["id"] for r in result["themes"]]
        assert "t1" in ids

    def test_never_raises_when_archive_missing(self, monkeypatch):
        """Archive entirely absent → graceful degradation, not an exception."""
        themes = [_make_theme("t1", 70, 1, "dominant")]
        monkeypatch.setattr(sp, "_load_theme_intel", lambda r: _make_ti(themes))
        # Simulate load_archive raising (e.g. parquet corrupt / module missing)
        monkeypatch.setattr(sp, "_load_archive_snapshots",
                            lambda r: (_ for _ in ()).throw(RuntimeError("archive dead")))

        def _bad_snapshots(r):
            raise RuntimeError("archive dead")

        monkeypatch.setattr(sp, "_load_archive_snapshots", _bad_snapshots)
        # build_pulse catches all exceptions; _load_archive_snapshots failing should
        # propagate through _build_theme_row with all-None deltas
        # Actually _load_archive_snapshots is called inside build_pulse which has a
        # top-level try/except — let's verify it doesn't raise to caller
        try:
            result = sp.build_pulse("us")
            # Either None (if exception propagated to top) or a valid result with None deltas
            if result is not None:
                assert result["schema"] == sp.SCHEMA
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"build_pulse raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# Ticker membership (live members only)
# ---------------------------------------------------------------------------

class TestTickerThemes:
    def _make_membership(self, today: str = "2026-07-02") -> dict:
        return {
            "baskets": {
                "t1": {
                    "name": "Theme One",
                    "members": [
                        {"ticker": "AAPL", "added": "2023-01-01", "removed": None},
                        {"ticker": "MSFT", "added": "2023-01-01", "removed": "2025-01-01"},  # removed
                        {"ticker": "NVDA", "added": "2026-06-01", "removed": None},
                    ]
                },
                "t2": {
                    "name": "Theme Two",
                    "members": [
                        {"ticker": "AAPL", "added": "2024-01-01", "removed": None},
                        {"ticker": "GOOG", "added": "2023-01-01", "removed": None},
                    ]
                },
            }
        }

    def test_live_members_excludes_removed(self):
        membership = self._make_membership()
        live = sp._live_members(membership, today_iso="2026-07-02")
        # MSFT removed before today → not in t1
        t1_tickers = {m["ticker"] for m in live["t1"]}
        assert "MSFT" not in t1_tickers
        assert "AAPL" in t1_tickers
        assert "NVDA" in t1_tickers

    def test_live_members_respects_added_date(self):
        # A member added AFTER today should not appear
        membership = {
            "baskets": {
                "t1": {"name": "T1", "members": [
                    {"ticker": "FUTR", "added": "2027-01-01", "removed": None},
                    {"ticker": "NOW", "added": "2026-01-01", "removed": None},
                ]}
            }
        }
        live = sp._live_members(membership, today_iso="2026-07-02")
        t1_tickers = {m["ticker"] for m in live["t1"]}
        assert "FUTR" not in t1_tickers
        assert "NOW" in t1_tickers

    def test_ticker_themes_monkeypatched(self, monkeypatch):
        membership = self._make_membership()
        monkeypatch.setattr(sp, "_load_membership", lambda: membership)
        monkeypatch.setattr(sp, "_load_theme_intel", lambda r: None)  # us → no filter
        result = sp.ticker_themes("us")
        # AAPL is in both t1 and t2
        assert set(result["AAPL"]) == {"t1", "t2"}
        # GOOG is only in t2
        assert result["GOOG"] == ["t2"]
        # MSFT removed → not present
        assert "MSFT" not in result

    def test_ticker_themes_empty_on_missing_membership(self, monkeypatch):
        monkeypatch.setattr(sp, "_load_membership", lambda: {})
        result = sp.ticker_themes("us")
        assert result == {}

    def test_ticker_themes_never_raises(self, monkeypatch):
        def _bad():
            raise RuntimeError("disk error")
        monkeypatch.setattr(sp, "_load_membership", _bad)
        result = sp.ticker_themes("us")
        assert result == {}


# ---------------------------------------------------------------------------
# for_ticker
# ---------------------------------------------------------------------------

class TestForTicker:
    def test_returns_strongest_theme(self, monkeypatch):
        themes = [
            _make_theme("t1", 80, 1, "dominant"),   # rank 1 — strongest
            _make_theme("t2", 60, 3, "emerging"),
        ]
        monkeypatch.setattr(sp, "_load_theme_intel", lambda r: _make_ti(themes))
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: [])
        monkeypatch.setattr(sp, "_load_membership", lambda: {
            "baskets": {
                "t1": {"name": "T1", "members": [{"ticker": "AAPL", "added": "2023-01-01", "removed": None}]},
                "t2": {"name": "T2", "members": [{"ticker": "AAPL", "added": "2023-01-01", "removed": None}]},
            }
        })
        result = sp.for_ticker("AAPL", "us")
        assert result is not None
        # t1 has rank=1 (best) → should be selected
        assert result["id"] == "t1"
        assert set(result["theme_ids"]) == {"t1", "t2"}

    def test_returns_none_for_unknown_ticker(self, monkeypatch):
        themes = [_make_theme("t1", 80, 1, "dominant")]
        monkeypatch.setattr(sp, "_load_theme_intel", lambda r: _make_ti(themes))
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: [])
        monkeypatch.setattr(sp, "_load_membership", lambda: {
            "baskets": {"t1": {"name": "T1", "members": [
                {"ticker": "AAPL", "added": "2023-01-01", "removed": None}]}}
        })
        assert sp.for_ticker("XYZ_NOT_FOUND", "us") is None

    def test_for_ticker_never_raises(self, monkeypatch):
        monkeypatch.setattr(sp, "_load_membership", lambda: (_ for _ in ()).throw(IOError()))

        def _bad_membership():
            raise IOError("disk error")

        monkeypatch.setattr(sp, "_load_membership", _bad_membership)
        result = sp.for_ticker("AAPL", "us")
        assert result is None  # graceful degradation


# ---------------------------------------------------------------------------
# write_pulse: file contract
# ---------------------------------------------------------------------------

class TestWritePulse:
    def _make_full_ti(self, n: int = 5) -> dict:
        themes = [_make_theme(f"t{i}", score=80 - i * 5, rank=i,
                              label="dominant" if i <= 2 else "neutral")
                  for i in range(1, n + 1)]
        return _make_ti(themes)

    def test_writes_valid_json_with_schema_and_asof(self, monkeypatch):
        ti = self._make_full_ti(4)
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: [])
        with tempfile.TemporaryDirectory() as tmpdir:
            sp.write_pulse(ti, "us", tmpdir)
            p = Path(tmpdir) / "sector_pulse.json"
            assert p.exists(), "sector_pulse.json not created"
            payload = json.loads(p.read_text())
            assert payload["schema"] == sp.SCHEMA
            assert "as_of" in payload
            assert isinstance(payload["themes"], list)
            assert len(payload["themes"]) == 4

    def test_writes_regional_filename_for_non_us(self, monkeypatch):
        ti = self._make_full_ti(3)
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: [])
        with tempfile.TemporaryDirectory() as tmpdir:
            sp.write_pulse(ti, "china", tmpdir)
            p = Path(tmpdir) / "sector_pulse_china.json"
            assert p.exists(), "sector_pulse_china.json not created"
            payload = json.loads(p.read_text())
            assert payload["region"] == "china"

    def test_schema_field_present_and_versioned(self, monkeypatch):
        ti = self._make_full_ti(2)
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: [])
        with tempfile.TemporaryDirectory() as tmpdir:
            sp.write_pulse(ti, "us", tmpdir)
            payload = json.loads((Path(tmpdir) / "sector_pulse.json").read_text())
            assert payload["schema"] == 1  # SCHEMA constant

    def test_as_of_in_output(self, monkeypatch):
        ti = self._make_full_ti(2)
        ti["as_of"] = "2026-07-02"
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: [])
        with tempfile.TemporaryDirectory() as tmpdir:
            sp.write_pulse(ti, "us", tmpdir)
            payload = json.loads((Path(tmpdir) / "sector_pulse.json").read_text())
            assert payload["as_of"] == "2026-07-02"

    def test_heating_cooling_in_output(self, monkeypatch):
        # Make one heating theme (dominant, rank 1, big rank delta)
        themes = [
            _make_theme("t1", 85, 1, "dominant"),
            _make_theme("t2", 55, 5, "fading"),
        ]
        ti = _make_ti(themes)
        # Provide 6 archive rows so 5-session delta resolves
        old_themes_row = [{"id": "t1", "rank": 6, "score": 78},
                          {"id": "t2", "rank": 3, "score": 60}]
        archive_rows = [{"asof": f"2026-06-{20+i}", "themes": old_themes_row} for i in range(6)] + [
            {"asof": "2026-07-02", "themes": [{"id": "t1", "rank": 1, "score": 85},
                                               {"id": "t2", "rank": 5, "score": 55}]}
        ]
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: archive_rows)
        with tempfile.TemporaryDirectory() as tmpdir:
            sp.write_pulse(ti, "us", tmpdir)
            payload = json.loads((Path(tmpdir) / "sector_pulse.json").read_text())
            assert "t1" in payload["heating"]
            assert "t2" in payload["cooling"]

    def test_never_fatal_on_empty_themes(self, monkeypatch):
        ti = {"as_of": "2026-07-02", "themes": []}
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: [])
        with tempfile.TemporaryDirectory() as tmpdir:
            # Should not raise; file should not be written (no themes)
            try:
                sp.write_pulse(ti, "us", tmpdir)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"write_pulse raised on empty themes: {exc}")
            p = Path(tmpdir) / "sector_pulse.json"
            # No themes → no file written
            assert not p.exists()

    def test_never_fatal_on_archive_error(self, monkeypatch):
        ti = self._make_full_ti(2)

        def _bad_archive(r):
            raise RuntimeError("disk error")

        monkeypatch.setattr(sp, "_load_archive_snapshots", _bad_archive)
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                sp.write_pulse(ti, "us", tmpdir)
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"write_pulse raised on archive error: {exc}")
            # File may or may not exist depending on how the exception propagates
            # but the call itself must never raise


# ---------------------------------------------------------------------------
# _load_archive_snapshots: graceful on missing archive
# ---------------------------------------------------------------------------

class TestLoadArchiveSnapshots:
    def test_empty_on_no_archive(self, monkeypatch):
        """When signal_archive returns None, result should be []."""
        from engine import signal_archive
        monkeypatch.setattr(signal_archive, "load_archive", lambda label, **kw: None)
        result = sp._load_archive_snapshots("us")
        assert result == []

    def test_empty_on_import_error(self, monkeypatch):
        """Even if signal_archive itself can't be imported, returns []."""
        import builtins
        orig_import = builtins.__import__

        def _block_import(name, *args, **kwargs):
            if "signal_archive" in name:
                raise ImportError("not available")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _block_import)
        result = sp._load_archive_snapshots("us")
        assert result == []

    def test_rows_sorted_oldest_first(self, monkeypatch):
        """Rows returned from load_archive_snapshots should be sorted oldest→newest."""
        from engine import signal_archive
        # Simulate out-of-order archive rows
        df = pd.DataFrame([
            {"asof": "2026-06-28", "snapshot_json": json.dumps(
                {"as_of": "2026-06-28", "themes": [{"id": "t1", "rank": 5, "score": 60}]})},
            {"asof": "2026-06-25", "snapshot_json": json.dumps(
                {"as_of": "2026-06-25", "themes": [{"id": "t1", "rank": 8, "score": 55}]})},
            {"asof": "2026-07-02", "snapshot_json": json.dumps(
                {"as_of": "2026-07-02", "themes": [{"id": "t1", "rank": 2, "score": 70}]})},
        ])
        monkeypatch.setattr(signal_archive, "load_archive", lambda label, **kw: df)
        rows = sp._load_archive_snapshots("us")
        asofs = [r["asof"] for r in rows]
        assert asofs == sorted(asofs)   # oldest → newest


# ---------------------------------------------------------------------------
# merge_pulse_into_theme_intel: W4 velocity merge into theme_intel rows
# ---------------------------------------------------------------------------

class TestMergePulseIntoThemeIntel:
    """build_baskets calls merge_pulse_into_theme_intel() after write_pulse().

    The function mutates the theme_intel dict IN PLACE, adding pulse_* keys
    to each theme row. Keys use the pulse_ prefix to avoid shadowing the
    existing rank_5d / delta_5d keys that theme_scoring already writes.
    """

    def test_merges_heat_and_deltas_when_archive_available(self, monkeypatch):
        """When archive history is sufficient, heat and rank delta keys are set."""
        themes = [
            _make_theme("t1", score=80, rank=1, label="dominant"),
            _make_theme("t2", score=55, rank=5, label="fading"),
        ]
        ti = _make_ti(themes)
        # Provide 6 archive rows so the 5-session look-back resolves.
        old_row = [{"id": "t1", "rank": 6, "score": 73},
                   {"id": "t2", "rank": 3, "score": 60}]
        archive = [{"asof": f"2026-06-{20+i}", "themes": old_row} for i in range(6)] + [
            {"asof": "2026-07-02", "themes": [{"id": "t1", "rank": 1, "score": 80},
                                               {"id": "t2", "rank": 5, "score": 55}]}
        ]
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: archive)
        sp.merge_pulse_into_theme_intel(ti, "us")

        t1 = ti["themes"][0]
        # heat is set (dominant, rank improved 5 positions → heating)
        assert t1["pulse_heat"] in ("heating", "hot", "cooling", "broken", "idle")
        # rank_delta_5d: 6 - 1 = +5
        assert t1["pulse_rank_delta_5d"] == 5
        # score_delta_5d: 80 - 73 = +7
        assert t1["pulse_score_delta_5d"] == 7
        # t2 has fading label → cooling
        t2 = ti["themes"][1]
        assert t2["pulse_heat"] == "cooling"

    def test_sets_none_deltas_when_insufficient_archive(self, monkeypatch):
        """Fewer archive rows than needed → None for 5d deltas (history accruing)."""
        themes = [_make_theme("t1", score=70, rank=1, label="dominant")]
        ti = _make_ti(themes)
        # Only 3 rows — not enough for offset=5 (needs 6)
        archive = [{"asof": f"2026-06-{28+i}", "themes": [{"id": "t1", "rank": 2, "score": 65}]}
                   for i in range(3)]
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: archive)
        sp.merge_pulse_into_theme_intel(ti, "us")

        t1 = ti["themes"][0]
        assert t1["pulse_rank_delta_5d"] is None
        assert t1["pulse_score_delta_5d"] is None
        # heat is still set (falls back to 0 for None deltas)
        assert "pulse_heat" in t1

    def test_never_fatal_when_archive_raises(self, monkeypatch):
        """An archive error leaves theme_intel without pulse_ keys but never raises."""
        themes = [_make_theme("t1", score=70, rank=1, label="dominant")]
        ti = _make_ti(themes)

        def _bad_archive(r):
            raise RuntimeError("disk dead")

        monkeypatch.setattr(sp, "_load_archive_snapshots", _bad_archive)
        try:
            sp.merge_pulse_into_theme_intel(ti, "us")
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"merge_pulse_into_theme_intel raised: {exc}")
        # Function is additive; theme_intel themes are still intact
        assert len(ti["themes"]) == 1

    def test_additive_never_overwrites_existing_keys(self, monkeypatch):
        """If a theme row already has pulse_heat set, setdefault must not overwrite it."""
        themes = [_make_theme("t1", score=70, rank=1, label="dominant")]
        ti = _make_ti(themes)
        ti["themes"][0]["pulse_heat"] = "SENTINEL"
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: [])
        sp.merge_pulse_into_theme_intel(ti, "us")
        # setdefault semantics: pre-existing value preserved
        assert ti["themes"][0]["pulse_heat"] == "SENTINEL"

    def test_heat_key_present_in_all_themes(self, monkeypatch):
        """Every theme row gets a pulse_heat key after the merge, even with no archive."""
        themes = [
            _make_theme("t1", 80, 1, "dominant"),
            _make_theme("t2", 60, 3, "emerging"),
            _make_theme("t3", 40, 6, "neutral"),
        ]
        ti = _make_ti(themes)
        monkeypatch.setattr(sp, "_load_archive_snapshots", lambda r: [])
        sp.merge_pulse_into_theme_intel(ti, "us")
        for th in ti["themes"]:
            assert "pulse_heat" in th, f"pulse_heat missing from theme {th['id']}"


# ---------------------------------------------------------------------------
# AST guard: no module-level logging.disable
# ---------------------------------------------------------------------------

def test_no_module_level_logging_disable():
    """Confirm sector_pulse.py does not call logging.disable() at module level.

    The AST lint gate in CI enforces this; this test provides the same check
    in-process so failures appear directly in the pytest output.
    """
    import ast
    src = Path(__file__).parent.parent / "engine" / "sector_pulse.py"
    tree = ast.parse(src.read_text())
    # Walk the module body (not inside functions/classes) for logging.disable calls
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if (isinstance(call.func, ast.Attribute)
                    and call.func.attr == "disable"
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "logging"):
                pytest.fail(
                    f"logging.disable() found at module level (line {node.lineno})")
