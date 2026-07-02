"""Tests for collectors/edgar_rpo.py — universe union + negative-cache additions (W5a follow-up).

Covers:
  (1) _rpo_universe() includes config.themes members (not just RPO_BASKETS)
  (2) None-safe: bare `some_theme:` YAML key (yields None) doesn't crash collect
  (3) Negative cache: known-empty tickers are suppressed within TTL
  (4) Negative cache: expired entries are re-probed
  (5) Negative cache: ticker that starts filing is cleared from negative cache
  (6) fetch_rpo drip logic: stale check + neg-cache skip + no-data recording
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest

import collectors.edgar_rpo as rpo_mod
from collectors.edgar_rpo import (
    _is_no_data_fresh,
    _load_no_data_cache,
    _rpo_universe,
    _save_no_data_cache,
    fetch_rpo,
)


# ---------------------------------------------------------------------------
# (1) Universe union: config.themes members are included
# ---------------------------------------------------------------------------

class TestRpoUniverse:
    """_rpo_universe() should union basket members with config.themes tickers."""

    def test_includes_theme_members(self, monkeypatch, tmp_path):
        """Tickers from config.themes appear in the universe."""
        monkeypatch.setattr(
            rpo_mod.config, "data_dir", lambda: tmp_path
        )
        monkeypatch.setattr(
            rpo_mod.config, "load",
            lambda: {
                "themes": {
                    "defense_aerospace": {"tickers": ["LMT", "RTX", "NOC", "GD"]},
                    "robotics_automation": {"tickers": ["ROK", "ISRG"]},
                }
            },
        )
        # No membership.json — only themes leg
        universe = _rpo_universe()
        assert "LMT" in universe
        assert "RTX" in universe
        assert "NOC" in universe
        assert "ROK" in universe
        assert "ISRG" in universe

    def test_deduped(self, monkeypatch, tmp_path):
        """Tickers appearing in both baskets and themes are deduplicated."""
        monkeypatch.setattr(rpo_mod.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(
            rpo_mod.config, "load",
            lambda: {
                "themes": {
                    "cybersecurity": {"tickers": ["CRWD", "PANW"]},
                }
            },
        )
        # Create membership.json with CRWD in ai_software
        membership = {
            "baskets": {
                "ai_software": {
                    "members": [
                        {"ticker": "CRWD", "removed": False},
                        {"ticker": "MSFT", "removed": False},
                    ]
                }
            }
        }
        (tmp_path / "baskets").mkdir(parents=True, exist_ok=True)
        (tmp_path / "baskets" / "membership.json").write_text(json.dumps(membership))

        universe = _rpo_universe()
        # CRWD appears in both basket and theme — must be present exactly once
        assert universe.count("CRWD") == 1
        assert "MSFT" in universe
        assert "PANW" in universe

    def test_none_safe_bare_theme_key(self, monkeypatch, tmp_path):
        """A bare `some_theme:` YAML key (None value) must not crash collect."""
        monkeypatch.setattr(rpo_mod.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(
            rpo_mod.config, "load",
            lambda: {
                "themes": {
                    "bare_key_theme": None,           # bare `bare_key_theme:` in YAML
                    "valid_theme": {"tickers": ["NVDA"]},
                }
            },
        )
        # Should not raise; bare key is safely skipped
        universe = _rpo_universe()
        assert "NVDA" in universe

    def test_empty_themes_graceful(self, monkeypatch, tmp_path):
        """No themes key in config → empty universe (no crash)."""
        monkeypatch.setattr(rpo_mod.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(rpo_mod.config, "load", lambda: {})
        universe = _rpo_universe()
        assert isinstance(universe, list)

    def test_sorted_output(self, monkeypatch, tmp_path):
        """Universe is returned sorted (deterministic ordering)."""
        monkeypatch.setattr(rpo_mod.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(
            rpo_mod.config, "load",
            lambda: {"themes": {"t": {"tickers": ["ZZZ", "AAA", "MMM"]}}},
        )
        universe = _rpo_universe()
        assert universe == sorted(universe)


# ---------------------------------------------------------------------------
# (2-4) Negative cache helpers
# ---------------------------------------------------------------------------

class TestNoDataCache:
    """_is_no_data_fresh, _load_no_data_cache, _save_no_data_cache."""

    def test_fresh_entry_is_suppressed(self):
        """A timestamp recorded moments ago is within TTL."""
        ts = datetime.now(tz=timezone.utc).isoformat()
        assert _is_no_data_fresh(ts) is True

    def test_expired_entry_is_not_fresh(self):
        """A timestamp > NO_DATA_TTL_DAYS old is stale."""
        old = (datetime.now(tz=timezone.utc) - timedelta(days=91)).isoformat()
        assert _is_no_data_fresh(old) is False

    def test_border_case_exactly_ttl(self):
        """Exactly NO_DATA_TTL_DAYS old is NOT fresh (timedelta comparison is strict <)."""
        exact = (datetime.now(tz=timezone.utc) - timedelta(days=rpo_mod.NO_DATA_TTL_DAYS)).isoformat()
        assert _is_no_data_fresh(exact) is False

    def test_invalid_timestamp_returns_false(self):
        """Corrupted timestamp → False (safe default: re-probe)."""
        assert _is_no_data_fresh("not-a-date") is False
        assert _is_no_data_fresh("") is False

    def test_round_trip_save_load(self, tmp_path, monkeypatch):
        """Saving then loading the negative cache returns the same data."""
        monkeypatch.setattr(rpo_mod.config, "data_dir", lambda: tmp_path)
        cache = {"LMT": "2026-01-01T00:00:00+00:00", "RTX": "2026-06-01T12:00:00+00:00"}
        _save_no_data_cache(cache)
        loaded = _load_no_data_cache()
        assert loaded == cache

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        """No rpo_no_data.json → empty dict (no crash)."""
        monkeypatch.setattr(rpo_mod.config, "data_dir", lambda: tmp_path)
        assert _load_no_data_cache() == {}

    def test_corrupted_file_returns_empty(self, tmp_path, monkeypatch):
        """Corrupted JSON → empty dict (no crash)."""
        monkeypatch.setattr(rpo_mod.config, "data_dir", lambda: tmp_path)
        (tmp_path / "edgar").mkdir(parents=True, exist_ok=True)
        (tmp_path / "edgar" / "rpo_no_data.json").write_text("not valid json{{")
        assert _load_no_data_cache() == {}


# ---------------------------------------------------------------------------
# (5-6) fetch_rpo integration — drip with negative cache
# ---------------------------------------------------------------------------

class TestFetchRpoDrip:
    """fetch_rpo: neg-cache suppresses re-probes; cleared when ticker starts filing."""

    def _make_cik(self, tickers):
        """Return a fake CIK map for the given tickers."""
        return {t: i + 1000 for i, t in enumerate(tickers)}

    def test_known_empty_ticker_skipped(self, tmp_path, monkeypatch):
        """A ticker in the negative cache (fresh) is NOT re-probed."""
        monkeypatch.setattr(rpo_mod.config, "data_dir", lambda: tmp_path)
        monkeypatch.setattr(rpo_mod.config, "load", lambda: {"themes": {}})

        # Pre-populate negative cache for LMT (fresh)
        fresh_ts = datetime.now(tz=timezone.utc).isoformat()
        _save_no_data_cache({"LMT": fresh_ts})

        cik_map = self._make_cik(["LMT", "NVDA"])
        probe_calls = []

        def fake_rpo_for(cik_val):
            probe_calls.append(cik_val)
            return []

        monkeypatch.setattr(rpo_mod, "_cik_map", lambda: cik_map)
        monkeypatch.setattr(rpo_mod, "_rpo_for", fake_rpo_for)
        monkeypatch.setattr(
            rpo_mod.config, "load",
            lambda: {"themes": {"t": {"tickers": ["LMT", "NVDA"]}}},
        )

        fetch_rpo(max_new=10)

        # LMT should NOT have been probed (in fresh neg-cache)
        probed_ciks = set(probe_calls)
        lmt_cik = cik_map["LMT"]
        assert lmt_cik not in probed_ciks, "LMT in fresh negative cache should be skipped"

    def test_expired_neg_cache_entry_is_reprobed(self, tmp_path, monkeypatch):
        """A ticker with an expired negative-cache entry IS re-probed."""
        monkeypatch.setattr(rpo_mod.config, "data_dir", lambda: tmp_path)

        old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=100)).isoformat()
        _save_no_data_cache({"LMT": old_ts})

        cik_map = self._make_cik(["LMT"])
        probe_calls = []

        def fake_rpo_for(cik_val):
            probe_calls.append(cik_val)
            return []

        monkeypatch.setattr(rpo_mod, "_cik_map", lambda: cik_map)
        monkeypatch.setattr(rpo_mod, "_rpo_for", fake_rpo_for)
        monkeypatch.setattr(
            rpo_mod.config, "load",
            lambda: {"themes": {"t": {"tickers": ["LMT"]}}},
        )

        fetch_rpo(max_new=10)
        assert cik_map["LMT"] in probe_calls, "Expired neg-cache entry should be re-probed"

    def test_empty_result_adds_to_neg_cache(self, tmp_path, monkeypatch):
        """A ticker that returns [] from EDGAR is added to the negative cache."""
        monkeypatch.setattr(rpo_mod.config, "data_dir", lambda: tmp_path)

        cik_map = self._make_cik(["LMT"])
        monkeypatch.setattr(rpo_mod, "_cik_map", lambda: cik_map)
        monkeypatch.setattr(rpo_mod, "_rpo_for", lambda cik_val: [])
        monkeypatch.setattr(
            rpo_mod.config, "load",
            lambda: {"themes": {"t": {"tickers": ["LMT"]}}},
        )

        fetch_rpo(max_new=10)

        neg = _load_no_data_cache()
        assert "LMT" in neg, "LMT returned no rows → should be in negative cache"
        assert _is_no_data_fresh(neg["LMT"]), "Newly recorded entry should be fresh"

    def test_ticker_starting_to_file_clears_neg_cache(self, tmp_path, monkeypatch):
        """When a ticker that was neg-cached starts returning rows, it is cleared."""
        monkeypatch.setattr(rpo_mod.config, "data_dir", lambda: tmp_path)

        # LMT was in negative cache (expired so it gets probed)
        old_ts = (datetime.now(tz=timezone.utc) - timedelta(days=100)).isoformat()
        _save_no_data_cache({"LMT": old_ts})

        cik_map = self._make_cik(["LMT"])
        monkeypatch.setattr(rpo_mod, "_cik_map", lambda: cik_map)
        # Now LMT returns data
        monkeypatch.setattr(
            rpo_mod, "_rpo_for",
            lambda cik_val: [{"fy": 2024, "rpo": 50_000_000_000.0, "revenue": 70_000_000_000.0}],
        )
        monkeypatch.setattr(
            rpo_mod.config, "load",
            lambda: {"themes": {"t": {"tickers": ["LMT"]}}},
        )

        fetch_rpo(max_new=10)

        neg = _load_no_data_cache()
        assert "LMT" not in neg, "LMT that started filing should be cleared from neg-cache"
        cache_path = tmp_path / "edgar" / "rpo.parquet"
        assert cache_path.exists(), "rpo.parquet should have been written"
        df = pd.read_parquet(cache_path)
        assert "LMT" in df["ticker"].values

    def test_max_new_respected(self, tmp_path, monkeypatch):
        """fetch_rpo only fetches up to max_new tickers per run."""
        monkeypatch.setattr(rpo_mod.config, "data_dir", lambda: tmp_path)

        tickers = [f"T{i}" for i in range(20)]
        cik_map = self._make_cik(tickers)
        probe_calls = []

        def fake_rpo_for(cik_val):
            probe_calls.append(cik_val)
            return []

        monkeypatch.setattr(rpo_mod, "_cik_map", lambda: cik_map)
        monkeypatch.setattr(rpo_mod, "_rpo_for", fake_rpo_for)
        monkeypatch.setattr(
            rpo_mod.config, "load",
            lambda: {"themes": {"t": {"tickers": tickers}}},
        )

        fetch_rpo(max_new=5)
        assert len(probe_calls) <= 5, f"max_new=5 but {len(probe_calls)} tickers were probed"
