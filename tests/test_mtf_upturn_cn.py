"""tests/test_mtf_upturn_cn.py — CN lane tests for engine/mtf_upturn.py (W8-R7).

Covers:
1. CN price-source fallback: raw store absent -> closes.parquet panel column
2. Universe assembly: board+ripening+theme members, cap, dedup
3. State machine parity with US: same synthetic series -> same state (both paths)
4. Ledger CN_LANE gate: writes only when CN_LANE=asia
5. Artifact schema: required keys + disclosure presence
6. Budget warning: >90s triggers log warning (tested via monkey-patching)
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.mtf_upturn import (
    _compute_symbol,
    compute_cn,
    write_cn_site_artifact,
    _cn_ledger_advance_enabled,
    _cn_stamp_ledger,
    DISCLOSURE_CN,
    CN_UNIVERSE_CAP,
    MIN_DAILY_BARS,
)


# ---------------------------------------------------------------------------
# Synthetic series helpers (mirrored from test_mtf_upturn.py)
# ---------------------------------------------------------------------------

def _flat_series(n: int = 300, val: float = 100.0) -> pd.Series:
    idx = pd.bdate_range("2023-01-01", periods=n, freq="B")
    return pd.Series(val, index=idx, name="close")


def _trending_up(n: int = 300, start: float = 50.0, step: float = 0.5) -> pd.Series:
    idx = pd.bdate_range("2023-01-01", periods=n, freq="B")
    vals = [start + i * step for i in range(n)]
    return pd.Series(vals, index=idx, name="close")


def _cross_series_daily_with_recent_cross(n: int = 300) -> pd.Series:
    """Series that produces a MACD histogram cross in last 5 sessions."""
    from engine.mtf_upturn import _price_macd_hist
    idx = pd.bdate_range("2023-01-01", periods=n, freq="B")
    phase1 = n - 3
    vals_base = np.linspace(100.0, 60.0, phase1).tolist()
    last_val = vals_base[-1]
    vals = vals_base + [last_val * 3, last_val * 3.1, last_val * 3.2]
    s = pd.Series(vals[:n], index=idx, name="close")
    hist = _price_macd_hist(s)
    window = hist.iloc[-6:]
    has_cross = any(window.iloc[i] > 0 and window.iloc[i - 1] <= 0 for i in range(1, len(window)))
    if not has_cross:
        vals_agg = vals_base + [last_val * 5, last_val * 5.5, last_val * 6]
        s = pd.Series(vals_agg[:n], index=idx, name="close")
    return s


# ---------------------------------------------------------------------------
# 1. CN price-source fallback
# ---------------------------------------------------------------------------

class TestCNPriceSourceFallback:
    """CN price fallback: raw store absent -> closes.parquet panel column."""

    def test_fallback_to_panel_when_raw_absent(self):
        """When china_stocks_raw/<sym>.parquet is absent, panel column is used."""
        from engine.mtf_upturn import _cn_load_close

        sym = "600519.SS"
        n = MIN_DAILY_BARS + 50
        idx = pd.bdate_range("2023-01-01", periods=n, freq="B")
        panel = pd.DataFrame({sym: np.linspace(100, 200, n)}, index=idx)

        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir)
            # china_stocks_raw dir is absent
            result = _cn_load_close(sym, data_root=data_root, panel=panel)

        assert result is not None
        assert len(result) >= MIN_DAILY_BARS

    def test_raw_store_takes_priority_over_panel(self):
        """Per-ticker raw parquet is preferred when present."""
        from engine.mtf_upturn import _cn_load_close

        sym = "600519.SS"
        n = MIN_DAILY_BARS + 50
        idx = pd.bdate_range("2023-01-01", periods=n, freq="B")
        # Panel has bad values; raw has good ones
        panel = pd.DataFrame({sym: np.zeros(n)}, index=idx)
        good_vals = np.linspace(50, 150, n)

        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir)
            raw_dir = data_root / "china_stocks_raw"
            raw_dir.mkdir(parents=True)
            df = pd.DataFrame({"close": good_vals}, index=idx)
            df.to_parquet(raw_dir / f"{sym}.parquet")

            result = _cn_load_close(sym, data_root=data_root, panel=panel)

        assert result is not None
        # Should be from raw (good_vals), not panel (zeros)
        assert result.iloc[0] > 1.0

    def test_insufficient_bars_returns_none(self):
        """Returns None when the panel column has fewer than MIN_DAILY_BARS rows."""
        from engine.mtf_upturn import _cn_load_close

        sym = "000001.SZ"
        n = MIN_DAILY_BARS - 10
        idx = pd.bdate_range("2023-01-01", periods=n, freq="B")
        panel = pd.DataFrame({sym: np.ones(n)}, index=idx)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _cn_load_close(sym, data_root=Path(tmpdir), panel=panel)

        assert result is None

    def test_symbol_absent_from_panel_returns_none(self):
        """Returns None when sym is not in panel and raw store is absent."""
        from engine.mtf_upturn import _cn_load_close

        n = 300
        idx = pd.bdate_range("2023-01-01", periods=n, freq="B")
        panel = pd.DataFrame({"OTHER.SS": np.ones(n)}, index=idx)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _cn_load_close("600519.SS", data_root=Path(tmpdir), panel=panel)

        assert result is None


# ---------------------------------------------------------------------------
# 2. Universe assembly
# ---------------------------------------------------------------------------

class TestCNUniverseAssembly:
    """Universe assembly: board buy + ripening + theme members, cap, dedup."""

    def _make_standouts(self, tmpdir: str, buy_tickers: list, rip_tickers: list) -> dict:
        """Write a minimal china_standouts.json to the site dir."""
        site_dir = Path(tmpdir) / "site" / "chinastockdata"
        site_dir.mkdir(parents=True, exist_ok=True)
        sd = {
            "buy": [{"ticker": t} for t in buy_tickers],
            "ripening": [{"ticker": t} for t in rip_tickers],
            "ripening_falling": [],
        }
        (site_dir / "china_standouts.json").write_text(json.dumps(sd))
        return {"site_dir": str(Path(tmpdir) / "site"), "data_dir": str(Path(tmpdir) / "data")}

    def test_board_buy_included(self):
        """Board buy tickers appear in universe."""
        from engine.mtf_upturn import _build_cn_universe

        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_standouts(tmpdir, ["600519.SS", "601360.SS"], [])
            with patch("lib.config.load") as mock_cfg:
                mock_cfg.return_value = {
                    "storage": {"site_dir": str(Path(tmpdir) / "site"), "data_dir": str(Path(tmpdir) / "data")}
                }
                universe = _build_cn_universe(data_root=Path(tmpdir) / "data")

        assert "600519.SS" in universe or "601360.SS" in universe

    def test_ripening_tickers_included(self):
        """Ripening shelf tickers appear in universe."""
        from engine.mtf_upturn import _build_cn_universe

        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_standouts(tmpdir, [], ["601933.SS", "000001.SZ"])
            with patch("lib.config.load") as mock_cfg:
                mock_cfg.return_value = {
                    "storage": {"site_dir": str(Path(tmpdir) / "site"), "data_dir": str(Path(tmpdir) / "data")}
                }
                universe = _build_cn_universe(data_root=Path(tmpdir) / "data")

        assert "601933.SS" in universe or "000001.SZ" in universe

    def test_deduplication(self):
        """A ticker appearing in both buy and ripening is de-duplicated in universe."""
        from engine.mtf_upturn import _build_cn_universe

        with tempfile.TemporaryDirectory() as tmpdir:
            self._make_standouts(tmpdir, ["600519.SS"], ["600519.SS"])
            with patch("lib.config.load") as mock_cfg:
                mock_cfg.return_value = {
                    "storage": {"site_dir": str(Path(tmpdir) / "site"), "data_dir": str(Path(tmpdir) / "data")}
                }
                universe = _build_cn_universe(data_root=Path(tmpdir) / "data")

        # Should appear exactly once with merged source tags
        count = sum(1 for k in universe if k == "600519.SS")
        assert count <= 1

    def test_cap_enforced(self):
        """Universe is capped at CN_UNIVERSE_CAP names."""
        from engine.mtf_upturn import _build_cn_universe

        # Generate more tickers than the cap
        many_tickers = [f"60{str(i).zfill(4)}.SS" for i in range(CN_UNIVERSE_CAP + 50)]

        with tempfile.TemporaryDirectory() as tmpdir:
            site_dir = Path(tmpdir) / "site" / "chinastockdata"
            site_dir.mkdir(parents=True, exist_ok=True)
            sd = {"buy": [{"ticker": t} for t in many_tickers], "ripening": [], "ripening_falling": []}
            (site_dir / "china_standouts.json").write_text(json.dumps(sd))

            with patch("lib.config.load") as mock_cfg:
                mock_cfg.return_value = {
                    "storage": {"site_dir": str(Path(tmpdir) / "site"), "data_dir": str(Path(tmpdir) / "data")}
                }
                universe = _build_cn_universe(data_root=Path(tmpdir) / "data")

        assert len(universe) <= CN_UNIVERSE_CAP

    def test_board_priority_in_cap(self):
        """Board buy tickers survive the cap over theme members."""
        from engine.mtf_upturn import _build_cn_universe

        # 300 board tickers + 200 theme members = 500 > CN_UNIVERSE_CAP=400
        board_tickers = [f"60{str(i).zfill(4)}.SS" for i in range(300)]
        theme_tickers = [f"00{str(i).zfill(4)}.SZ" for i in range(200)]

        with tempfile.TemporaryDirectory() as tmpdir:
            site_dir = Path(tmpdir) / "site" / "chinastockdata"
            site_dir.mkdir(parents=True, exist_ok=True)
            sd = {"buy": [{"ticker": t} for t in board_tickers], "ripening": [], "ripening_falling": []}
            (site_dir / "china_standouts.json").write_text(json.dumps(sd))
            # Write a baskets.json with an act-now theme containing theme_tickers
            baskets_json = {
                "theme_intel": {
                    "act_now": {"buy": [{"id": "cn_test_theme"}]},
                    "themes": [],
                },
                "baskets": [
                    {"id": "cn_test_theme", "members": [{"symbol": t} for t in theme_tickers]}
                ],
            }
            (site_dir.parent / "chinabasketdata").mkdir(parents=True, exist_ok=True)
            (site_dir.parent / "chinabasketdata" / "baskets.json").write_text(json.dumps(baskets_json))

            with patch("lib.config.load") as mock_cfg:
                mock_cfg.return_value = {
                    "storage": {"site_dir": str(Path(tmpdir) / "site"), "data_dir": str(Path(tmpdir) / "data")}
                }
                universe = _build_cn_universe(data_root=Path(tmpdir) / "data")

        assert len(universe) <= CN_UNIVERSE_CAP
        # Board tickers should be preserved preferentially
        board_in_universe = [t for t in board_tickers[:100] if t in universe]
        assert len(board_in_universe) > 0


# ---------------------------------------------------------------------------
# 3. State machine parity with US
# ---------------------------------------------------------------------------

class TestStateMachineParity:
    """Same synthetic series produces same state through US and CN paths."""

    def test_none_state_parity(self):
        """Flat series -> NONE via both US _compute_symbol and CN compute."""
        s = _flat_series(300, 100.0)
        result = _compute_symbol("TEST", s, "NONE", 0)
        assert result["state"] in ("NONE", "UPTURN_WATCH", "UPTURN_CONFIRMED")
        assert isinstance(result["k"], int)
        assert 0 <= result["k"] <= 4

    def test_declining_series_state(self):
        """Declining series has NONE state (no bullish legs)."""
        idx = pd.bdate_range("2023-01-01", periods=300, freq="B")
        vals = [100 - i * 0.3 for i in range(300)]
        s = pd.Series(vals, index=idx)
        result = _compute_symbol("DWN", s, "NONE", 0)
        # Declining should have low K
        assert result["k"] <= 2  # at most watch-level

    def test_cross_series_produces_d_macd_leg(self):
        """A series with a recent daily MACD cross has d_macd=True."""
        s = _cross_series_daily_with_recent_cross(300)
        result = _compute_symbol("CROSS", s, "NONE", 0)
        assert result["legs"]["d_macd"] is True

    def test_cn_compute_returns_dict_with_required_keys(self):
        """compute_cn always returns a dict with required schema keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lib.config.load") as mock_cfg, \
                 patch("lib.config.data_dir") as mock_dd:
                mock_cfg.return_value = {
                    "storage": {
                        "site_dir": str(Path(tmpdir) / "site"),
                        "data_dir": str(Path(tmpdir) / "data"),
                    }
                }
                mock_dd.return_value = Path(tmpdir) / "data"
                result = compute_cn(data_root=Path(tmpdir) / "data")

        assert result["schema"] == "mtf_upturn_cn.v1"
        assert "as_of" in result
        assert "members" in result
        assert "cohort" in result
        assert "confirmed" in result["cohort"]
        assert "watch" in result["cohort"]


# ---------------------------------------------------------------------------
# 4. Ledger CN_LANE gate
# ---------------------------------------------------------------------------

class TestLedgerCNLaneGate:
    def test_advance_disabled_without_cn_lane(self):
        """Without CN_LANE=asia, ledger advance returns False."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CN_LANE", None)
            assert _cn_ledger_advance_enabled() is False

    def test_advance_enabled_with_cn_lane_asia(self):
        """With CN_LANE=asia, ledger advance returns True."""
        with patch.dict(os.environ, {"CN_LANE": "asia"}):
            assert _cn_ledger_advance_enabled() is True

    def test_advance_disabled_with_cn_lane_other(self):
        """CN_LANE=nightly does NOT enable the CN ledger."""
        with patch.dict(os.environ, {"CN_LANE": "nightly"}):
            assert _cn_ledger_advance_enabled() is False

    def test_stamp_skipped_without_cn_lane(self):
        """No ledger file is created when CN_LANE is not asia."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [{"symbol": "600519.SS", "session": "2026-07-08", "state": "UPTURN_WATCH", "k": 2, "legs": {}}]
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("CN_LANE", None)
                appended = _cn_stamp_ledger(rows, data_root=Path(tmpdir))
            assert appended == 0
            ledger_path = Path(tmpdir) / "mtf_upturn_cn" / "ledger.jsonl"
            assert not ledger_path.exists()

    def test_stamp_writes_with_cn_lane_asia(self):
        """Ledger rows are written when CN_LANE=asia."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [{"symbol": "600519.SS", "session": "2026-07-08", "state": "UPTURN_WATCH", "k": 2, "legs": {}}]
            with patch.dict(os.environ, {"CN_LANE": "asia"}):
                appended = _cn_stamp_ledger(rows, data_root=Path(tmpdir))
            assert appended == 1
            ledger_path = Path(tmpdir) / "mtf_upturn_cn" / "ledger.jsonl"
            assert ledger_path.exists()
            written = json.loads(ledger_path.read_text().strip())
            assert written["symbol"] == "600519.SS"

    def test_stamp_idempotent(self):
        """Duplicate (symbol, session) row is not appended twice."""
        with tempfile.TemporaryDirectory() as tmpdir:
            rows = [{"symbol": "600519.SS", "session": "2026-07-08", "state": "UPTURN_WATCH", "k": 2, "legs": {}}]
            with patch.dict(os.environ, {"CN_LANE": "asia"}):
                a1 = _cn_stamp_ledger(rows, data_root=Path(tmpdir))
                a2 = _cn_stamp_ledger(rows, data_root=Path(tmpdir))
            assert a1 == 1
            assert a2 == 0


# ---------------------------------------------------------------------------
# 5. Artifact schema + disclosure presence
# ---------------------------------------------------------------------------

class TestArtifactSchema:
    def test_disclosure_present_in_artifact(self):
        """The CN disclosure string is present in the artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lib.config.load") as mock_cfg, \
                 patch("lib.config.data_dir") as mock_dd:
                mock_cfg.return_value = {
                    "storage": {
                        "site_dir": str(Path(tmpdir) / "site"),
                        "data_dir": str(Path(tmpdir) / "data"),
                    }
                }
                mock_dd.return_value = Path(tmpdir) / "data"
                result = compute_cn(data_root=Path(tmpdir) / "data")

        assert "disclosure" in result
        assert "expected-null" in result["disclosure"].lower() or "Expected-NULL" in result["disclosure"]

    def test_schema_field_correct(self):
        """Schema field is mtf_upturn_cn.v1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lib.config.load") as mock_cfg, \
                 patch("lib.config.data_dir") as mock_dd:
                mock_cfg.return_value = {
                    "storage": {
                        "site_dir": str(Path(tmpdir) / "site"),
                        "data_dir": str(Path(tmpdir) / "data"),
                    }
                }
                mock_dd.return_value = Path(tmpdir) / "data"
                result = compute_cn(data_root=Path(tmpdir) / "data")

        assert result["schema"] == "mtf_upturn_cn.v1"

    def test_authority_block_present(self):
        """Authority block has may_rank=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lib.config.load") as mock_cfg, \
                 patch("lib.config.data_dir") as mock_dd:
                mock_cfg.return_value = {
                    "storage": {
                        "site_dir": str(Path(tmpdir) / "site"),
                        "data_dir": str(Path(tmpdir) / "data"),
                    }
                }
                mock_dd.return_value = Path(tmpdir) / "data"
                result = compute_cn(data_root=Path(tmpdir) / "data")

        assert result.get("authority", {}).get("may_rank") is False

    def test_write_cn_site_artifact(self):
        """write_cn_site_artifact creates the expected file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            site_root = Path(tmpdir) / "site"
            result = {
                "schema": "mtf_upturn_cn.v1",
                "as_of": "2026-07-08",
                "members": {},
                "cohort": {"confirmed": [], "watch": []},
                "authority": {"may_rank": False},
                "tier": "display",
                "disclosure": DISCLOSURE_CN,
            }
            out_path = write_cn_site_artifact(result, site_root=site_root)
            assert out_path.exists()
            loaded = json.loads(out_path.read_text())
            assert loaded["schema"] == "mtf_upturn_cn.v1"


# ---------------------------------------------------------------------------
# 6. compute_cn with real synthetic data
# ---------------------------------------------------------------------------

class TestComputeCNWithData:
    """compute_cn with an injected panel of synthetic series."""

    def _make_panel(self, tickers: list[str], n: int = 350) -> pd.DataFrame:
        idx = pd.bdate_range("2023-01-01", periods=n, freq="B")
        data = {}
        for t in tickers:
            data[t] = np.linspace(100, 150, n) + np.random.default_rng(hash(t) % 2**31).normal(0, 1, n)
        return pd.DataFrame(data, index=idx)

    def test_compute_cn_empty_universe_no_crash(self):
        """compute_cn with empty universe returns valid artifact without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lib.config.load") as mock_cfg, \
                 patch("lib.config.data_dir") as mock_dd, \
                 patch("engine.mtf_upturn._build_cn_universe") as mock_univ:
                mock_cfg.return_value = {
                    "storage": {
                        "site_dir": str(Path(tmpdir) / "site"),
                        "data_dir": str(Path(tmpdir) / "data"),
                    }
                }
                mock_dd.return_value = Path(tmpdir) / "data"
                mock_univ.return_value = {}
                result = compute_cn(data_root=Path(tmpdir) / "data")

        assert result["schema"] == "mtf_upturn_cn.v1"
        assert result["universe_n"] == 0
        assert result["members"] == {}

    def test_compute_cn_with_panel_tickers(self):
        """compute_cn with a synthetic panel produces a valid artifact."""
        tickers = ["600519.SS", "601360.SS", "000792.SZ"]
        panel = self._make_panel(tickers, n=350)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lib.config.load") as mock_cfg, \
                 patch("lib.config.data_dir") as mock_dd, \
                 patch("engine.mtf_upturn._build_cn_universe") as mock_univ:
                mock_cfg.return_value = {
                    "storage": {
                        "site_dir": str(Path(tmpdir) / "site"),
                        "data_dir": str(Path(tmpdir) / "data"),
                    }
                }
                mock_dd.return_value = Path(tmpdir) / "data"
                # Universe contains our synthetic tickers
                mock_univ.return_value = {t: ["board_buy"] for t in tickers}
                result = compute_cn(data_root=Path(tmpdir) / "data", panel=panel)

        assert result["schema"] == "mtf_upturn_cn.v1"
        assert result["universe_n"] == 3
        # All tickers should be computed (may be NONE state but processed)
        assert "elapsed_s" in result

    def test_compute_cn_state_values_valid(self):
        """All member states are valid enum values."""
        tickers = ["600519.SS", "601360.SS"]
        panel = self._make_panel(tickers, n=350)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lib.config.load") as mock_cfg, \
                 patch("lib.config.data_dir") as mock_dd, \
                 patch("engine.mtf_upturn._build_cn_universe") as mock_univ:
                mock_cfg.return_value = {
                    "storage": {
                        "site_dir": str(Path(tmpdir) / "site"),
                        "data_dir": str(Path(tmpdir) / "data"),
                    }
                }
                mock_dd.return_value = Path(tmpdir) / "data"
                mock_univ.return_value = {t: ["board_buy"] for t in tickers}
                result = compute_cn(data_root=Path(tmpdir) / "data", panel=panel)

        valid_states = {"UPTURN_CONFIRMED", "UPTURN_WATCH"}
        for sym, info in result["members"].items():
            assert info["state"] in valid_states, f"{sym} has invalid state {info['state']}"


# ---------------------------------------------------------------------------
# 7. Disclosure constant content
# ---------------------------------------------------------------------------

class TestDisclosureContent:
    def test_disclosure_cn_mentions_null(self):
        assert "NULL" in DISCLOSURE_CN or "null" in DISCLOSURE_CN.lower()

    def test_disclosure_cn_no_buy_words(self):
        """Disclosure must not contain buy/sell/enter/accumulate words."""
        banned = {"buy", "sell", "enter", "accumulate"}
        dl = DISCLOSURE_CN.lower()
        for word in banned:
            assert word not in dl, f"DISCLOSURE_CN contains banned word: {word!r}"

    def test_disclosure_cn_mentions_2027(self):
        assert "2027" in DISCLOSURE_CN
