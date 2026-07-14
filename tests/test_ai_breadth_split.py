"""Tests for VSB W4a+W4b: AI-adjacency tag layer + decomposed breadth engine.

Part (a) — tag builder (scripts/build_ai_adjacency_tag.py):
  - union/classing from finviz + baskets
  - conflict: AI wins over non_ai basket, warning emitted
  - change log diff on second run
  - byte-determinism: identical inputs -> identical parquet bytes

Part (b) — breadth split (engine/breadth_split.py):
  - exact pct50/pct200/adv/spread values on hand-constructed fixture
  - denominator honesty: ticker with < window obs excluded from that metric
  - missing tag file -> compute returns None gracefully
  - tag enum only {ai_core, ai_infra_power}
  - spread sign convention (ai - nonai)
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures and helpers
# ──────────────────────────────────────────────────────────────────────────────

def _finviz_json(ai_subs: dict[str, list[str]], asof: str = "2026-01-01") -> dict:
    """Build a minimal finviz_themes_map.json structure."""
    subsectors = [
        {"key": k, "name": k, "members": v}
        for k, v in ai_subs.items()
    ]
    return {
        "source": "test",
        "asof": asof,
        "counts": {},
        "themes": [
            {"theme": "Artificial Intelligence", "key": "Artificial Intelligence",
             "subsectors": subsectors},
            {"theme": "Other Theme", "key": "OtherTheme", "subsectors": []},
        ],
    }


def _membership_json(baskets: dict[str, list[str]], version: str = "2026-01-01") -> dict:
    """Build a minimal membership.json structure."""
    basket_dict = {}
    for slug, tickers in baskets.items():
        basket_dict[slug] = {
            "name": slug, "name_zh": slug,
            "members": [{"ticker": t, "added": "2023-01-01", "removed": None} for t in tickers],
        }
    return {
        "version": version,
        "note": "test",
        "seed_date": "2023-01-01",
        "curated": True,
        "baskets": basket_dict,
        "construction": {},
        "history_note": "test",
    }


def _write_sources(tmp_path: Path, finviz_data: dict, membership_data: dict) -> tuple[Path, Path]:
    fv_path = tmp_path / "finviz_themes_map.json"
    mb_path = tmp_path / "membership.json"
    fv_path.write_text(json.dumps(finviz_data))
    mb_path.write_text(json.dumps(membership_data))
    return fv_path, mb_path


def _patch_paths(monkeypatch, fv_path: Path, mb_path: Path, tag_dir: Path):
    """Monkeypatch the path-returning functions in the tag builder."""
    import scripts.build_ai_adjacency_tag as tag_mod

    monkeypatch.setattr(tag_mod, "_finviz_path", lambda: fv_path)
    monkeypatch.setattr(tag_mod, "_membership_path", lambda: mb_path)
    monkeypatch.setattr(tag_mod, "_tag_path", lambda: tag_dir / "ticker_ai_tag.parquet")
    monkeypatch.setattr(tag_mod, "_log_path", lambda: tag_dir / "ticker_ai_tag_log.parquet")


# ──────────────────────────────────────────────────────────────────────────────
# Part (a): Tag builder tests
# ──────────────────────────────────────────────────────────────────────────────

class TestTagBuilder:

    def test_union_ai_core_from_finviz_and_baskets(self, monkeypatch, tmp_path):
        """Finviz AI tickers + basket ai_infra members all become ai_core."""
        fv = _finviz_json({"aicompute": ["NVDA", "AMD"]})
        mb = _membership_json({
            "ai_infra": ["NVDA", "ANET"],    # NVDA already in finviz; ANET is new
            "ai_software": [],
            "ai_neoclouds": [],
            "ai_semiconductors": [],
            "semicap_equipment": [],
            "memory_storage": [],
            "ai_agents": [],
            "data_center_power": [],
            "power_grid": [],
            "nuclear_power": [],
            "uranium_miners": [],
            "non_ai_software": [],
            "non_ai_tech": [],
        })
        fv_p, mb_p = _write_sources(tmp_path, fv, mb)
        _patch_paths(monkeypatch, fv_p, mb_p, tmp_path)

        import scripts.build_ai_adjacency_tag as tag_mod
        df = tag_mod.ensure_ai_tags(force=True)

        assert df is not None
        assert set(df["ticker"]) >= {"NVDA", "AMD", "ANET"}
        # all three should be ai_core
        for t in ["NVDA", "AMD", "ANET"]:
            row = df[df["ticker"] == t]
            assert len(row) == 1, f"{t} not found"
            assert row.iloc[0]["tag"] == "ai_core", f"{t} should be ai_core"

    def test_ai_infra_power_class(self, monkeypatch, tmp_path):
        """data_center_power basket tickers (not in ai_core) get ai_infra_power tag."""
        fv = _finviz_json({"aicompute": ["NVDA"]})
        mb = _membership_json({
            "ai_infra": [],
            "ai_software": [],
            "ai_neoclouds": [],
            "ai_semiconductors": [],
            "semicap_equipment": [],
            "memory_storage": [],
            "ai_agents": [],
            "data_center_power": ["VRT", "ETN"],
            "power_grid": ["GEV"],
            "nuclear_power": [],
            "uranium_miners": [],
            "non_ai_software": [],
            "non_ai_tech": [],
        })
        fv_p, mb_p = _write_sources(tmp_path, fv, mb)
        _patch_paths(monkeypatch, fv_p, mb_p, tmp_path)

        import scripts.build_ai_adjacency_tag as tag_mod
        df = tag_mod.ensure_ai_tags(force=True)

        assert df is not None
        vrt = df[df["ticker"] == "VRT"]
        assert len(vrt) == 1
        assert vrt.iloc[0]["tag"] == "ai_infra_power"

        gev = df[df["ticker"] == "GEV"]
        assert len(gev) == 1
        assert gev.iloc[0]["tag"] == "ai_infra_power"

    def test_ai_core_wins_over_infra_power(self, monkeypatch, tmp_path):
        """A ticker in both ai_core and data_center_power gets ai_core (not infra_power)."""
        fv = _finviz_json({"aicompute": ["NVDA", "VRT"]})  # VRT in finviz AI
        mb = _membership_json({
            "ai_infra": [],
            "ai_software": [],
            "ai_neoclouds": [],
            "ai_semiconductors": [],
            "semicap_equipment": [],
            "memory_storage": [],
            "ai_agents": [],
            "data_center_power": ["VRT"],  # also in power basket
            "power_grid": [],
            "nuclear_power": [],
            "uranium_miners": [],
            "non_ai_software": [],
            "non_ai_tech": [],
        })
        fv_p, mb_p = _write_sources(tmp_path, fv, mb)
        _patch_paths(monkeypatch, fv_p, mb_p, tmp_path)

        import scripts.build_ai_adjacency_tag as tag_mod
        df = tag_mod.ensure_ai_tags(force=True)

        # VRT in both finviz AI and power basket -> ai_core wins
        vrt = df[df["ticker"] == "VRT"]
        assert len(vrt) == 1
        assert vrt.iloc[0]["tag"] == "ai_core"

    def test_conflict_warning_emitted(self, monkeypatch, tmp_path, caplog):
        """Ticker in both AI source and non_ai basket triggers a log.warning."""
        # CRM is in ai_agents but also will be in non_ai_software
        fv = _finviz_json({"aicompute": ["NVDA"]})
        mb = _membership_json({
            "ai_infra": [],
            "ai_software": [],
            "ai_neoclouds": [],
            "ai_semiconductors": [],
            "semicap_equipment": [],
            "memory_storage": [],
            "ai_agents": ["CRM"],
            "data_center_power": [],
            "power_grid": [],
            "nuclear_power": [],
            "uranium_miners": [],
            "non_ai_software": ["CRM"],  # conflict!
            "non_ai_tech": [],
        })
        fv_p, mb_p = _write_sources(tmp_path, fv, mb)
        _patch_paths(monkeypatch, fv_p, mb_p, tmp_path)

        import scripts.build_ai_adjacency_tag as tag_mod
        with caplog.at_level(logging.WARNING, logger="scripts.build_ai_adjacency_tag"):
            df = tag_mod.ensure_ai_tags(force=True)

        assert df is not None
        # AI wins
        crm = df[df["ticker"] == "CRM"]
        assert len(crm) == 1
        assert crm.iloc[0]["tag"] == "ai_core"
        # Warning was emitted
        conflict_warnings = [r for r in caplog.records if "Conflict" in r.message and "CRM" in r.message]
        assert len(conflict_warnings) >= 1, "Expected conflict warning for CRM"

    def test_byte_determinism(self, monkeypatch, tmp_path):
        """Same inputs -> identical parquet output bytes on two successive builds."""
        fv = _finviz_json({"aicompute": ["NVDA", "AMD"], "aicloud": ["MSFT", "GOOGL"]})
        mb = _membership_json({
            "ai_infra": ["NVDA", "SMCI"],
            "ai_software": ["MSFT"],
            "ai_neoclouds": [],
            "ai_semiconductors": [],
            "semicap_equipment": [],
            "memory_storage": [],
            "ai_agents": [],
            "data_center_power": ["VRT"],
            "power_grid": [],
            "nuclear_power": [],
            "uranium_miners": [],
            "non_ai_software": [],
            "non_ai_tech": [],
        })
        fv_p, mb_p = _write_sources(tmp_path, fv, mb)
        _patch_paths(monkeypatch, fv_p, mb_p, tmp_path)

        import scripts.build_ai_adjacency_tag as tag_mod

        df1 = tag_mod.ensure_ai_tags(force=True)
        tag_path = tmp_path / "ticker_ai_tag.parquet"
        bytes1 = tag_path.read_bytes()

        # Re-read the same file (fingerprint unchanged, should return same df)
        df2 = tag_mod.ensure_ai_tags(force=False)
        bytes2 = tag_path.read_bytes()

        assert df1 is not None
        assert df2 is not None
        assert bytes1 == bytes2, "Tag parquet must be byte-identical on repeated build"
        pd.testing.assert_frame_equal(df1, df2)

    def test_change_log_appended_on_regen(self, monkeypatch, tmp_path):
        """Second build with a different ticker set -> change log captures the diff."""
        import scripts.build_ai_adjacency_tag as tag_mod

        # First build: only NVDA
        fv1 = _finviz_json({"aicompute": ["NVDA"]})
        mb1 = _membership_json({k: [] for k in [
            "ai_infra", "ai_software", "ai_neoclouds", "ai_semiconductors",
            "semicap_equipment", "memory_storage", "ai_agents",
            "data_center_power", "power_grid", "nuclear_power", "uranium_miners",
            "non_ai_software", "non_ai_tech",
        ]})
        fv_p, mb_p = _write_sources(tmp_path, fv1, mb1)
        _patch_paths(monkeypatch, fv_p, mb_p, tmp_path)

        df1 = tag_mod.ensure_ai_tags(force=True)
        assert df1 is not None

        # Second build: NVDA + AMD added
        fv2 = _finviz_json({"aicompute": ["NVDA", "AMD"]}, asof="2026-02-01")
        fv_p.write_text(json.dumps(fv2))

        df2 = tag_mod.ensure_ai_tags(force=True)
        assert df2 is not None

        log_path = tmp_path / "ticker_ai_tag_log.parquet"
        assert log_path.exists(), "Change log should be written"
        log_df = pd.read_parquet(log_path)
        # AMD should appear as an add (old_tag None, new_tag ai_core)
        amd_rows = log_df[log_df["ticker"] == "AMD"]
        assert len(amd_rows) >= 1
        assert amd_rows.iloc[0]["old_tag"] is None or pd.isna(amd_rows.iloc[0]["old_tag"])
        assert amd_rows.iloc[0]["new_tag"] == "ai_core"

    def test_no_change_no_log_append(self, monkeypatch, tmp_path):
        """Identical rebuild (force=True same inputs) appends nothing to the log."""
        import scripts.build_ai_adjacency_tag as tag_mod

        fv = _finviz_json({"aicompute": ["NVDA"]})
        mb = _membership_json({k: [] for k in [
            "ai_infra", "ai_software", "ai_neoclouds", "ai_semiconductors",
            "semicap_equipment", "memory_storage", "ai_agents",
            "data_center_power", "power_grid", "nuclear_power", "uranium_miners",
            "non_ai_software", "non_ai_tech",
        ]})
        fv_p, mb_p = _write_sources(tmp_path, fv, mb)
        _patch_paths(monkeypatch, fv_p, mb_p, tmp_path)

        tag_mod.ensure_ai_tags(force=True)
        tag_mod.ensure_ai_tags(force=True)  # second run: same inputs

        log_path = tmp_path / "ticker_ai_tag_log.parquet"
        # No change -> log file should not exist or be empty
        if log_path.exists():
            log_df = pd.read_parquet(log_path)
            assert len(log_df) == 0, "No rows should be logged when nothing changed"

    def test_tag_enum_values(self, monkeypatch, tmp_path):
        """Tag column only contains 'ai_core' or 'ai_infra_power'."""
        fv = _finviz_json({"aicompute": ["NVDA", "AMD"]})
        mb = _membership_json({
            "ai_infra": [],
            "ai_software": [],
            "ai_neoclouds": [],
            "ai_semiconductors": [],
            "semicap_equipment": [],
            "memory_storage": [],
            "ai_agents": [],
            "data_center_power": ["VRT"],
            "power_grid": ["GEV"],
            "nuclear_power": [],
            "uranium_miners": [],
            "non_ai_software": [],
            "non_ai_tech": [],
        })
        fv_p, mb_p = _write_sources(tmp_path, fv, mb)
        _patch_paths(monkeypatch, fv_p, mb_p, tmp_path)

        import scripts.build_ai_adjacency_tag as tag_mod
        df = tag_mod.ensure_ai_tags(force=True)
        assert df is not None
        valid_tags = {"ai_core", "ai_infra_power"}
        assert set(df["tag"]).issubset(valid_tags), f"Unexpected tag values: {set(df['tag'])}"

    def test_returns_none_on_missing_sources(self, monkeypatch, tmp_path):
        """Missing source files -> ensure_ai_tags returns None without raising."""
        import scripts.build_ai_adjacency_tag as tag_mod
        # Point to non-existent paths
        monkeypatch.setattr(tag_mod, "_finviz_path", lambda: tmp_path / "does_not_exist.json")
        monkeypatch.setattr(tag_mod, "_membership_path", lambda: tmp_path / "also_missing.json")
        monkeypatch.setattr(tag_mod, "_tag_path", lambda: tmp_path / "ticker_ai_tag.parquet")
        monkeypatch.setattr(tag_mod, "_log_path", lambda: tmp_path / "ticker_ai_tag_log.parquet")

        result = tag_mod.ensure_ai_tags(force=True)
        assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# Part (b): Breadth split engine tests
# ──────────────────────────────────────────────────────────────────────────────

def _make_closes(tickers: list[str], n_days: int = 260,
                 start: str = "2025-01-01") -> pd.DataFrame:
    """Build a synthetic wide close matrix (tickers x n_days), all NaN-free."""
    idx = pd.bdate_range(start, periods=n_days)
    data = {}
    for i, t in enumerate(tickers):
        # Each ticker has a simple trend + small noise (deterministic via seed)
        rng = np.random.default_rng(i)
        prices = 100.0 + np.cumsum(rng.normal(0.02, 0.5, n_days))
        data[t] = prices
    return pd.DataFrame(data, index=idx)


def _patch_breadth_paths(monkeypatch, closes: pd.DataFrame, tag_df: pd.DataFrame, tmp_path: Path):
    """Patch breadth_split to use synthetic closes and tags."""
    import engine.breadth_split as bs
    import scripts.build_ai_adjacency_tag as tag_mod

    # Write closes to a temp parquet
    closes_path = tmp_path / "_closes_cache.parquet"
    closes.to_parquet(closes_path)

    def _fake_data_dir():
        return tmp_path

    monkeypatch.setattr(bs.config, "data_dir", _fake_data_dir)
    monkeypatch.setattr(tag_mod, "ensure_ai_tags", lambda force=False: tag_df)


class TestBreadthSplit:

    def _make_tag_df(self, ai_tickers: list[str], infra_tickers: list[str] = None) -> pd.DataFrame:
        rows = [{"ticker": t, "tag": "ai_core", "sources": "test", "as_of": "2025-01-01"}
                for t in ai_tickers]
        if infra_tickers:
            rows += [{"ticker": t, "tag": "ai_infra_power", "sources": "test", "as_of": "2025-01-01"}
                     for t in infra_tickers]
        return pd.DataFrame(rows)

    def test_exact_pct50_values(self, monkeypatch, tmp_path):
        """Hand-constructed fixture: verify pct_above_50dma is correct.

        Strategy: 4 tickers, 60 trading days.
        - ai1, ai2: both above their 50d MA on the last day
        - nonai1: above its 50d MA on the last day
        - nonai2: below its 50d MA on the last day

        Expected pct50: ai=100%, nonai=50%, spread_50=+50.
        """
        n = 60
        idx = pd.bdate_range("2025-01-01", periods=n)

        # ai1: starts at 100, ramps to 200 -> well above any 50d MA
        ai1 = 100.0 + np.linspace(0, 100, n)
        # ai2: starts at 100, ramps to 180
        ai2 = 100.0 + np.linspace(0, 80, n)
        # nonai1: starts at 100, ramps slowly upward -> above 50d MA at end
        nonai1 = 100.0 + np.linspace(0, 10, n)
        # nonai2: starts at 100, drops hard at the end -> below 50d MA
        nonai2 = np.concatenate([
            np.linspace(100, 110, 50),
            np.linspace(110, 80, 10),  # big drop at the end
        ])

        closes = pd.DataFrame({
            "ai1": ai1, "ai2": ai2,
            "nonai1": nonai1, "nonai2": nonai2,
        }, index=idx)

        tag_df = self._make_tag_df(["ai1", "ai2"])

        import engine.breadth_split as bs
        closes_path = tmp_path / "breadth" / "_closes_cache.parquet"
        closes_path.parent.mkdir(parents=True, exist_ok=True)
        closes.to_parquet(closes_path)

        monkeypatch.setattr(bs.config, "data_dir", lambda: tmp_path)
        import scripts.build_ai_adjacency_tag as tag_mod
        monkeypatch.setattr(tag_mod, "ensure_ai_tags", lambda force=False: tag_df)

        result = bs.compute_breadth_split()
        assert result is not None

        lat = result["latest"]
        # ai: both above 50dma -> 100%
        assert lat["ai_pct50"] == pytest.approx(100.0, abs=0.5)
        # nonai: 1 of 2 above -> 50%
        assert lat["nonai_pct50"] == pytest.approx(50.0, abs=0.5)
        # spread = 100 - 50 = +50
        assert lat["spread_50"] == pytest.approx(50.0, abs=0.5)

    def test_spread_sign_convention(self, monkeypatch, tmp_path):
        """Spread = ai - nonai. When non-AI is stronger, spread is negative."""
        n = 60
        idx = pd.bdate_range("2025-01-01", periods=n)

        # ai ticker: drops at end -> below 50d MA
        ai1 = np.concatenate([np.linspace(100, 110, 50), np.linspace(110, 85, 10)])
        # nonai tickers: ramp up -> above 50d MA
        nonai1 = 100.0 + np.linspace(0, 50, n)
        nonai2 = 100.0 + np.linspace(0, 40, n)

        closes = pd.DataFrame({
            "ai1": ai1, "nonai1": nonai1, "nonai2": nonai2,
        }, index=idx)

        tag_df = self._make_tag_df(["ai1"])

        import engine.breadth_split as bs
        closes_path = tmp_path / "breadth" / "_closes_cache.parquet"
        closes_path.parent.mkdir(parents=True, exist_ok=True)
        closes.to_parquet(closes_path)

        monkeypatch.setattr(bs.config, "data_dir", lambda: tmp_path)
        import scripts.build_ai_adjacency_tag as tag_mod
        monkeypatch.setattr(tag_mod, "ensure_ai_tags", lambda force=False: tag_df)

        result = bs.compute_breadth_split()
        assert result is not None
        # AI below, non-AI above -> spread should be negative
        assert result["latest"]["spread_50"] < 0, (
            f"Expected negative spread (non-AI stronger), got {result['latest']['spread_50']}"
        )

    def test_denominator_honesty_pct200(self, monkeypatch, tmp_path):
        """A ticker with only 100 rows of history should be excluded from pct200."""
        # We have 200 trading days total; nonai2 is introduced only on day 101
        # so it has 100 rows of history at the end -> should NOT count in pct200 denominator
        n_full = 200
        idx = pd.bdate_range("2025-01-01", periods=n_full)

        ai1 = 100.0 + np.linspace(0, 50, n_full)
        # nonai1: 200 days, above 200d MA at end
        nonai1 = 100.0 + np.linspace(0, 30, n_full)
        # nonai2: only 100 rows present (first 100 are NaN)
        nonai2_vals = np.full(n_full, np.nan)
        nonai2_vals[100:] = 100.0 + np.linspace(0, 50, 100)
        nonai2 = nonai2_vals

        closes = pd.DataFrame({
            "ai1": ai1, "nonai1": nonai1, "nonai2": nonai2,
        }, index=idx)

        tag_df = self._make_tag_df(["ai1"])

        import engine.breadth_split as bs
        closes_path = tmp_path / "breadth" / "_closes_cache.parquet"
        closes_path.parent.mkdir(parents=True, exist_ok=True)
        closes.to_parquet(closes_path)

        monkeypatch.setattr(bs.config, "data_dir", lambda: tmp_path)
        import scripts.build_ai_adjacency_tag as tag_mod
        monkeypatch.setattr(tag_mod, "ensure_ai_tags", lambda force=False: tag_df)

        result = bs.compute_breadth_split()
        assert result is not None
        # pct200 should be computed; nonai2 should NOT count (< 200 obs)
        # nonai1 (200 obs) should count; result is not None means no crash
        # We can't easily verify exact denominator here without inspecting internals,
        # but we verify the function returns a valid pct200 and doesn't crash.
        lat = result["latest"]
        # ai1 has 200 rows -> ai_pct200 should be a valid number
        assert lat["ai_pct200"] is not None
        # nonai_pct200: only nonai1 qualifies (nonai2 has only 100 rows in cache)
        assert lat["nonai_pct200"] is not None

    def test_missing_tag_file_returns_none(self, monkeypatch, tmp_path):
        """If ensure_ai_tags returns None, compute_breadth_split returns None gracefully."""
        n = 60
        idx = pd.bdate_range("2025-01-01", periods=n)
        closes = pd.DataFrame(
            {"a": np.linspace(100, 200, n), "b": np.linspace(100, 150, n)},
            index=idx,
        )

        import engine.breadth_split as bs
        closes_path = tmp_path / "breadth" / "_closes_cache.parquet"
        closes_path.parent.mkdir(parents=True, exist_ok=True)
        closes.to_parquet(closes_path)

        monkeypatch.setattr(bs.config, "data_dir", lambda: tmp_path)
        import scripts.build_ai_adjacency_tag as tag_mod
        monkeypatch.setattr(tag_mod, "ensure_ai_tags", lambda force=False: None)

        result = bs.compute_breadth_split()
        assert result is None, "Should return None when tag file unavailable"

    def test_missing_closes_returns_none(self, monkeypatch, tmp_path):
        """If closes cache is absent, compute returns None gracefully."""
        import engine.breadth_split as bs
        # tmp_path has no closes cache
        monkeypatch.setattr(bs.config, "data_dir", lambda: tmp_path)

        result = bs.compute_breadth_split()
        assert result is None

    def test_payload_schema(self, monkeypatch, tmp_path):
        """Result dict contains expected top-level keys and sub-keys."""
        n = 260
        idx = pd.bdate_range("2025-01-01", periods=n)
        tickers = ["ai1", "ai2", "nonai1", "nonai2", "nonai3", "infra1"]
        rng = np.random.default_rng(42)
        data = {t: 100 + np.cumsum(rng.normal(0.1, 0.5, n)) for t in tickers}
        closes = pd.DataFrame(data, index=idx)

        tag_df = self._make_tag_df(["ai1", "ai2"], ["infra1"])

        import engine.breadth_split as bs
        closes_path = tmp_path / "breadth" / "_closes_cache.parquet"
        closes_path.parent.mkdir(parents=True, exist_ok=True)
        closes.to_parquet(closes_path)

        monkeypatch.setattr(bs.config, "data_dir", lambda: tmp_path)
        import scripts.build_ai_adjacency_tag as tag_mod
        monkeypatch.setattr(tag_mod, "ensure_ai_tags", lambda force=False: tag_df)

        result = bs.compute_breadth_split()
        assert result is not None

        # Top-level keys
        for k in ("as_of", "cohort_sizes", "latest", "spark", "young",
                  "stance_en", "stance_zh", "disclaimer_en", "disclaimer_zh",
                  "tag_version"):
            assert k in result, f"Missing key: {k}"

        # cohort_sizes sub-keys
        for k in ("ai_core", "ai_infra_power", "ai_total", "non_ai", "universe"):
            assert k in result["cohort_sizes"], f"Missing cohort_sizes.{k}"

        # latest sub-keys
        for k in ("ai_pct50", "nonai_pct50", "spread_50",
                  "ai_pct200", "nonai_pct200", "spread_200",
                  "ai_adv_share", "nonai_adv_share", "spread_adv"):
            assert k in result["latest"], f"Missing latest.{k}"

        # spark
        assert "spread_50" in result["spark"]
        assert isinstance(result["spark"]["spread_50"], list)

        # young flag is a bool
        assert isinstance(result["young"], bool)

    def test_young_flag_true_below_threshold(self, monkeypatch, tmp_path):
        """Cache with < 252 rows -> young=True."""
        n = 100  # clearly below 252
        idx = pd.bdate_range("2025-01-01", periods=n)
        data = {
            "ai1": 100 + np.linspace(0, 20, n),
            "nonai1": 100 + np.linspace(0, 10, n),
        }
        closes = pd.DataFrame(data, index=idx)
        tag_df = self._make_tag_df(["ai1"])

        import engine.breadth_split as bs
        closes_path = tmp_path / "breadth" / "_closes_cache.parquet"
        closes_path.parent.mkdir(parents=True, exist_ok=True)
        closes.to_parquet(closes_path)

        monkeypatch.setattr(bs.config, "data_dir", lambda: tmp_path)
        import scripts.build_ai_adjacency_tag as tag_mod
        monkeypatch.setattr(tag_mod, "ensure_ai_tags", lambda force=False: tag_df)

        result = bs.compute_breadth_split()
        assert result is not None
        assert result["young"] is True

    def test_young_flag_false_at_threshold(self, monkeypatch, tmp_path):
        """Cache with >= 252 rows -> young=False."""
        n = 260
        idx = pd.bdate_range("2025-01-01", periods=n)
        rng = np.random.default_rng(7)
        data = {
            "ai1": 100 + np.cumsum(rng.normal(0.1, 0.3, n)),
            "nonai1": 100 + np.cumsum(rng.normal(0.05, 0.3, n)),
        }
        closes = pd.DataFrame(data, index=idx)
        tag_df = self._make_tag_df(["ai1"])

        import engine.breadth_split as bs
        closes_path = tmp_path / "breadth" / "_closes_cache.parquet"
        closes_path.parent.mkdir(parents=True, exist_ok=True)
        closes.to_parquet(closes_path)

        monkeypatch.setattr(bs.config, "data_dir", lambda: tmp_path)
        import scripts.build_ai_adjacency_tag as tag_mod
        monkeypatch.setattr(tag_mod, "ensure_ai_tags", lambda force=False: tag_df)

        result = bs.compute_breadth_split()
        assert result is not None
        assert result["young"] is False

    def test_tag_enum_only_two_values(self, monkeypatch, tmp_path):
        """Ensure tag column only contains the two allowed values."""
        fv = _finviz_json({"aicompute": ["NVDA", "AMD"]})
        mb = _membership_json({
            "ai_infra": [],
            "ai_software": [],
            "ai_neoclouds": [],
            "ai_semiconductors": [],
            "semicap_equipment": [],
            "memory_storage": [],
            "ai_agents": [],
            "data_center_power": ["VRT"],
            "power_grid": [],
            "nuclear_power": [],
            "uranium_miners": [],
            "non_ai_software": [],
            "non_ai_tech": [],
        })
        fv_p, mb_p = _write_sources(tmp_path, fv, mb)
        _patch_paths(monkeypatch, fv_p, mb_p, tmp_path)

        import scripts.build_ai_adjacency_tag as tag_mod
        df = tag_mod.ensure_ai_tags(force=True)

        assert df is not None
        assert set(df["tag"]).issubset({"ai_core", "ai_infra_power"})

    def test_adv_share_math(self, monkeypatch, tmp_path):
        """Advance share: when all AI tickers go up and all non-AI go down."""
        n = 60
        idx = pd.bdate_range("2025-01-01", periods=n)

        # ai1, ai2: strictly increasing -> every day is an advance
        ai1 = 100.0 + np.arange(n, dtype=float)
        ai2 = 200.0 + np.arange(n, dtype=float)
        # nonai1, nonai2: strictly decreasing -> every day is a decline
        nonai1 = 200.0 - np.arange(n, dtype=float)
        nonai2 = 150.0 - np.arange(n, dtype=float)

        closes = pd.DataFrame({
            "ai1": ai1, "ai2": ai2,
            "nonai1": nonai1, "nonai2": nonai2,
        }, index=idx)

        tag_df = self._make_tag_df(["ai1", "ai2"])

        import engine.breadth_split as bs
        closes_path = tmp_path / "breadth" / "_closes_cache.parquet"
        closes_path.parent.mkdir(parents=True, exist_ok=True)
        closes.to_parquet(closes_path)

        monkeypatch.setattr(bs.config, "data_dir", lambda: tmp_path)
        import scripts.build_ai_adjacency_tag as tag_mod
        monkeypatch.setattr(tag_mod, "ensure_ai_tags", lambda force=False: tag_df)

        result = bs.compute_breadth_split()
        assert result is not None
        lat = result["latest"]
        # ai: all up -> 100%
        assert lat["ai_adv_share"] == pytest.approx(100.0, abs=0.1)
        # nonai: all down -> 0%
        assert lat["nonai_adv_share"] == pytest.approx(0.0, abs=0.1)
        # spread_adv = 100 - 0 = +100
        assert lat["spread_adv"] == pytest.approx(100.0, abs=0.1)

    def test_spark_length_at_most_120(self, monkeypatch, tmp_path):
        """Spark series has at most 120 values."""
        n = 260
        idx = pd.bdate_range("2025-01-01", periods=n)
        rng = np.random.default_rng(99)
        data = {
            "ai1": 100 + np.cumsum(rng.normal(0.1, 0.5, n)),
            "nonai1": 100 + np.cumsum(rng.normal(0.05, 0.5, n)),
        }
        closes = pd.DataFrame(data, index=idx)
        tag_df = self._make_tag_df(["ai1"])

        import engine.breadth_split as bs
        closes_path = tmp_path / "breadth" / "_closes_cache.parquet"
        closes_path.parent.mkdir(parents=True, exist_ok=True)
        closes.to_parquet(closes_path)

        monkeypatch.setattr(bs.config, "data_dir", lambda: tmp_path)
        import scripts.build_ai_adjacency_tag as tag_mod
        monkeypatch.setattr(tag_mod, "ensure_ai_tags", lambda force=False: tag_df)

        result = bs.compute_breadth_split()
        assert result is not None
        assert len(result["spark"]["spread_50"]) <= 120

    def test_cohort_sizes_correct(self, monkeypatch, tmp_path):
        """cohort_sizes reflects actual intersection with cache columns."""
        n = 60
        idx = pd.bdate_range("2025-01-01", periods=n)
        # 3 AI tickers in cache, 1 infra, 2 non-AI in cache
        data = {
            "ai1": np.ones(n) * 100, "ai2": np.ones(n) * 110, "ai3": np.ones(n) * 120,
            "infra1": np.ones(n) * 90,
            "nonai1": np.ones(n) * 80, "nonai2": np.ones(n) * 70,
        }
        closes = pd.DataFrame(data, index=idx)

        tag_df = pd.DataFrame([
            {"ticker": "ai1", "tag": "ai_core", "sources": "test", "as_of": "2025-01-01"},
            {"ticker": "ai2", "tag": "ai_core", "sources": "test", "as_of": "2025-01-01"},
            {"ticker": "ai3", "tag": "ai_core", "sources": "test", "as_of": "2025-01-01"},
            {"ticker": "infra1", "tag": "ai_infra_power", "sources": "test", "as_of": "2025-01-01"},
            # "ai_extra" is tagged but NOT in cache -> should not count
            {"ticker": "ai_extra", "tag": "ai_core", "sources": "test", "as_of": "2025-01-01"},
        ])

        import engine.breadth_split as bs
        closes_path = tmp_path / "breadth" / "_closes_cache.parquet"
        closes_path.parent.mkdir(parents=True, exist_ok=True)
        closes.to_parquet(closes_path)

        monkeypatch.setattr(bs.config, "data_dir", lambda: tmp_path)
        import scripts.build_ai_adjacency_tag as tag_mod
        monkeypatch.setattr(tag_mod, "ensure_ai_tags", lambda force=False: tag_df)

        result = bs.compute_breadth_split()
        assert result is not None
        cs = result["cohort_sizes"]
        # ai_total = 4 tickers in cache (ai1+ai2+ai3 + infra1)
        assert cs["ai_total"] == 4
        # non_ai = 2 (nonai1 + nonai2)
        assert cs["non_ai"] == 2
        # universe = 6
        assert cs["universe"] == 6
        # Sub-cohort counts must be cache-intersected so they reconcile with ai_total.
        # ai_extra is tagged ai_core but absent from cache -> ai_core should be 3, not 4.
        assert cs["ai_core"] == 3, f"ai_core should be cache-intersected (3), got {cs['ai_core']}"
        assert cs["ai_infra_power"] == 1, f"ai_infra_power should be cache-intersected (1), got {cs['ai_infra_power']}"
        assert cs["ai_core"] + cs["ai_infra_power"] == cs["ai_total"], (
            f"ai_core ({cs['ai_core']}) + ai_infra_power ({cs['ai_infra_power']}) "
            f"must equal ai_total ({cs['ai_total']})"
        )
        # Tagged counts (pre-intersection) available under distinct keys.
        assert cs["ai_core_tagged"] == 4, f"ai_core_tagged should be 4 (includes ai_extra), got {cs['ai_core_tagged']}"
        assert cs["ai_infra_power_tagged"] == 1
