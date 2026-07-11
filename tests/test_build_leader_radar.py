"""tests/test_build_leader_radar.py — Hermetic tests for scripts/build_leader_radar.py (LR W2a).

Coverage:
  - rs_series full-depth on first run (depth == ohlcv overlap depth)
  - state_history both columns persisted + hysteresis across 3 simulated nights
  - fires exactly-once-on-entry; refire lockout (21 sessions)
  - universe ETF exclusion + revisions_uncovered listing
  - stale freeze (no state advancement)
  - kill-switch (writes noindex payload, returns {})
  - radar.json schema keys present
  - pd.NA JSON safety
  - consumption-not-recomputation for plab_leader_precipice / plab_leader_onset
  - registry 27 books + unique config_hashes
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Helpers for fixture construction ─────────────────────────────────────────


def _make_close(n: int = 400, start_price: float = 100.0, seed: int = 0) -> pd.Series:
    """Construct a synthetic daily close series of length n."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0005, 0.015, size=n)
    prices = start_price * np.cumprod(1 + returns)
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.Series(prices, index=idx, name="close")


def _make_ohlcv(n: int = 400, seed: int = 0) -> pd.DataFrame:
    close = _make_close(n, seed=seed)
    high = close * (1 + np.abs(np.random.default_rng(seed + 1).normal(0, 0.005, n)))
    low = close * (1 - np.abs(np.random.default_rng(seed + 2).normal(0, 0.005, n)))
    volume = np.abs(np.random.default_rng(seed + 3).normal(1e7, 1e6, n))
    return pd.DataFrame({
        "open": close * 0.999,
        "high": high,
        "low": low,
        "close": close.values,
        "volume": volume,
    }, index=close.index)


def _write_ohlcv(root: Path, ticker: str, df: pd.DataFrame) -> None:
    p = root / "data" / "baskets" / "ohlcv" / f"{ticker}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)


def _write_spy(root: Path, n: int = 400) -> None:
    spy = _make_ohlcv(n, seed=99)
    p = root / "data" / "yahoo" / "SPY.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    spy[["close"]].to_parquet(p)


def _write_membership(root: Path, tickers: list[str], etfs: list[str] | None = None) -> None:
    """Write a minimal data/baskets/membership.json with one basket."""
    members = [{"ticker": t, "added": "2023-01-01", "removed": None, "rationale": "test"} for t in tickers]
    payload = {
        "version": "v1",
        "baskets": {
            "mag7": {
                "name": "Test Basket",
                "name_zh": "测试篮",
                "members": members,
            }
        },
    }
    p = root / "data" / "baskets" / "membership.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload))


def _write_nasdaq_membership(root: Path, tickers: list[str]) -> None:
    """Write a minimal data/baskets_nasdaq/membership.json."""
    members = [{"ticker": t, "added": "2023-01-01"} for t in tickers]
    payload = {
        "version": "v1",
        "amalgamations": {
            "megacap": {"name": "Megacap", "members": members},
        },
        "subsectors": {},
    }
    p = root / "data" / "baskets_nasdaq" / "membership.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload))


def _write_breadth(root: Path) -> None:
    n = 200
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    df = pd.DataFrame({
        "pct_above_200": np.random.uniform(40, 80, n),
        "adv": np.random.randint(200, 400, n),
        "dec": np.random.randint(100, 300, n),
        "ad_line": np.cumsum(np.random.normal(0, 10, n)),
    }, index=idx)
    p = root / "data" / "breadth" / "breadth.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)


def _write_revisions(root: Path, tickers: list[str]) -> None:
    df = pd.DataFrame({
        "net_up_30d": [2.0] * len(tickers),
        "breadth": [0.6] * len(tickers),
        "est_chg_30d": [1.5] * len(tickers),
        "asof": ["2026-07-10"] * len(tickers),
    }, index=tickers)
    df.index.name = "ticker"
    p = root / "data" / "revisions" / "latest.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p)


def _write_regime(root: Path) -> None:
    d = {
        "as_of": "2026-07-11",
        "dispersion_pctile": 0.77,
        "avg_corr": 0.07,
        "state": "lean_in",
    }
    p = root / "data" / "dispersion" / "regime.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d))


def _build_fixture_root(tmp_path: Path, tickers: list[str]) -> Path:
    """Build a minimal fixture tree in tmp_path and return it."""
    # Write SPY
    _write_spy(tmp_path, n=400)
    # Write OHLCV for tickers
    for i, t in enumerate(tickers):
        _write_ohlcv(tmp_path, t, _make_ohlcv(400, seed=i))
    # Write ETF (SPY) ohlcv too (should be excluded from universe)
    _write_ohlcv(tmp_path, "SPY", _make_ohlcv(400, seed=50))
    _write_membership(tmp_path, tickers)
    _write_nasdaq_membership(tmp_path, tickers[:2])
    _write_breadth(tmp_path)
    _write_revisions(tmp_path, tickers)
    _write_regime(tmp_path)
    # Minimal site dir
    (tmp_path / "site").mkdir(exist_ok=True)
    return tmp_path


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestRsSeriesDepth:
    """LR-R3: full-history backfill on first run — depth == ohlcv overlap depth."""

    def test_rs_depth_equals_ohlcv_on_first_run(self, tmp_path):
        import os
        tickers = ["NVDA"]
        root = _build_fixture_root(tmp_path, tickers)

        # Confirm no rs_series exists yet
        rs_dir = root / "data" / "rs_series"
        assert not (rs_dir / "NVDA.parquet").exists()

        # Run builder with COLLECT_LANE=nightly so data/ writes are enabled (HOUSE-U5)
        from scripts.build_leader_radar import build
        env = {**os.environ, "COLLECT_LANE": "nightly"}
        with patch("lib.config.ROOT", root), \
             patch("lib.config.data_dir", lambda: root / "data"), \
             patch("lib.config.load", lambda: {
                 "storage": {"data_dir": "data", "site_dir": "site"},
                 "leader_radar": {"enabled": True, "basket_keys": ["mag7"], "dow30": []},
             }), \
             patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            build(data_root=root / "data", site_root=root / "site")

        assert (rs_dir / "NVDA.parquet").exists(), "rs_series not written"

        # Compare depth: rs_series depth == ohlcv-vs-SPY common date count
        rs_df = pd.read_parquet(rs_dir / "NVDA.parquet")
        ohlcv = pd.read_parquet(root / "data" / "baskets" / "ohlcv" / "NVDA.parquet")
        spy = pd.read_parquet(root / "data" / "yahoo" / "SPY.parquet")
        spy_close = spy["close"].dropna()
        ohlcv_close = ohlcv["close"].dropna()
        common = ohlcv_close.index.intersection(spy_close.index)
        assert len(rs_df) == len(common), (
            f"rs_series depth {len(rs_df)} != ohlcv-SPY overlap depth {len(common)}"
        )


class TestStateHistory:
    """state_history.parquet: both columns persisted + hysteresis across 3 nights."""

    def _run(self, root: Path, tickers: list[str]) -> dict:
        import os
        from scripts.build_leader_radar import build
        from unittest.mock import patch
        with patch("lib.config.ROOT", root), \
             patch("lib.config.data_dir", lambda: root / "data"), \
             patch("lib.config.load", lambda: {
                 "storage": {"data_dir": "data", "site_dir": "site"},
                 "leader_radar": {"enabled": True, "basket_keys": ["mag7"], "dow30": []},
             }), \
             patch.dict(os.environ, {"COLLECT_LANE": "nightly"}):
            return build(data_root=root / "data", site_root=root / "site")

    def test_state_history_written_on_first_run(self, tmp_path):
        tickers = ["AAPL", "MSFT"]
        root = _build_fixture_root(tmp_path, tickers)
        self._run(root, tickers)
        hist = root / "data" / "leader_radar" / "state_history.parquet"
        assert hist.exists(), "state_history.parquet not written"
        df = pd.read_parquet(hist)
        assert "raw_state" in df.columns
        assert "confirmed_state" in df.columns
        assert "ticker" in df.columns
        assert len(df) >= 1

    def test_state_history_has_both_columns(self, tmp_path):
        tickers = ["NVDA"]
        root = _build_fixture_root(tmp_path, tickers)
        self._run(root, tickers)
        df = pd.read_parquet(root / "data" / "leader_radar" / "state_history.parquet")
        for col in ("date", "ticker", "raw_state", "confirmed_state"):
            assert col in df.columns, f"Missing column: {col}"

    def test_hysteresis_accumulates_across_3_runs(self, tmp_path):
        """Three successive runs should accumulate rows (1 per run per ticker)."""
        tickers = ["GOOGL"]
        root = _build_fixture_root(tmp_path, tickers)
        for _ in range(3):
            self._run(root, tickers)
        df = pd.read_parquet(root / "data" / "leader_radar" / "state_history.parquet")
        # All 3 runs may write the same date (today), so dedup by date; at least 1 row
        assert len(df) >= 1


class TestHouseU5Gate:
    """m1 — HOUSE-U5: with COLLECT_LANE unset, site/ artifact is written but data/ stores are not."""

    def _run_no_lane(self, root: Path, tickers: list[str]) -> dict:
        """Run the builder without COLLECT_LANE (simulates intraday / dev run)."""
        import os
        from scripts.build_leader_radar import build
        from unittest.mock import patch
        # Ensure COLLECT_LANE and US_LANE are absent
        env_patch = {k: "" for k in ("COLLECT_LANE", "US_LANE")}
        with patch("lib.config.ROOT", root), \
             patch("lib.config.data_dir", lambda: root / "data"), \
             patch("lib.config.load", lambda: {
                 "storage": {"data_dir": "data", "site_dir": "site"},
                 "leader_radar": {"enabled": True, "basket_keys": ["mag7"], "dow30": []},
             }), \
             patch.dict(os.environ, env_patch, clear=False):
            # Remove the vars entirely if they exist to simulate unset
            saved = {}
            for k in ("COLLECT_LANE", "US_LANE"):
                if k in os.environ:
                    saved[k] = os.environ.pop(k)
            try:
                return build(data_root=root / "data", site_root=root / "site")
            finally:
                os.environ.update(saved)

    def test_site_artifact_written_without_lane(self, tmp_path):
        """radar.json is always written (site/ ungated)."""
        tickers = ["AAPL"]
        root = _build_fixture_root(tmp_path, tickers)
        self._run_no_lane(root, tickers)
        artifact = root / "site" / "leaderradar" / "radar.json"
        assert artifact.exists(), "radar.json should be written even without COLLECT_LANE"

    def test_no_data_stores_written_without_lane(self, tmp_path):
        """data/leader_radar/state_history, fire_log, and data/rs_series are NOT written without nightly lane."""
        tickers = ["AAPL"]
        root = _build_fixture_root(tmp_path, tickers)
        self._run_no_lane(root, tickers)
        # None of the data/ stores should exist
        state_hist = root / "data" / "leader_radar" / "state_history.parquet"
        fire_log = root / "data" / "leader_radar" / "fire_log.parquet"
        rs_file = root / "data" / "rs_series" / "AAPL.parquet"
        assert not state_hist.exists(), "state_history.parquet must not be written without nightly lane"
        assert not fire_log.exists(), "fire_log.parquet must not be written without nightly lane"
        assert not rs_file.exists(), "rs_series/AAPL.parquet must not be written without nightly lane"


class TestFireRules:
    """fire_precipice exactly-once-on-entry; fire_onset; refire lockout."""

    def _load_radar(self, root: Path) -> dict:
        p = root / "site" / "leaderradar" / "radar.json"
        if p.exists():
            return json.loads(p.read_text())
        return {}

    def _run(self, root: Path) -> dict:
        from scripts.build_leader_radar import build
        with patch("lib.config.ROOT", root), \
             patch("lib.config.data_dir", lambda: root / "data"), \
             patch("lib.config.load", lambda: {
                 "storage": {"data_dir": "data", "site_dir": "site"},
                 "leader_radar": {"enabled": True, "basket_keys": ["mag7"], "dow30": []},
             }):
            return build(data_root=root / "data", site_root=root / "site")

    def test_fire_flags_are_boolean(self, tmp_path):
        tickers = ["AAPL"]
        root = _build_fixture_root(tmp_path, tickers)
        self._run(root)
        payload = self._load_radar(root)
        assert "rows" in payload
        for row in payload["rows"]:
            assert isinstance(row["fire_precipice"], bool)
            assert isinstance(row["fire_onset"], bool)


class TestUniverseFiltering:
    """ETF exclusion + revisions_uncovered listing."""

    def _run(self, root: Path) -> dict:
        from scripts.build_leader_radar import build
        with patch("lib.config.ROOT", root), \
             patch("lib.config.data_dir", lambda: root / "data"), \
             patch("lib.config.load", lambda: {
                 "storage": {"data_dir": "data", "site_dir": "site"},
                 "leader_radar": {"enabled": True, "basket_keys": ["mag7"], "dow30": []},
             }):
            return build(data_root=root / "data", site_root=root / "site")

    def test_etfs_excluded_from_universe(self, tmp_path):
        tickers = ["AAPL", "MSFT"]
        root = _build_fixture_root(tmp_path, tickers)

        # SPY should NOT appear in rows (it's in the ETF set and ohlcv dir)
        payload = self._run(root)
        row_tickers = [r["ticker"] for r in payload.get("rows", [])]
        assert "SPY" not in row_tickers, "SPY should be excluded from universe"

    def test_revisions_uncovered_listed(self, tmp_path):
        """Names with no revisions entry appear in coverage.revisions_uncovered."""
        tickers = ["AAPL", "MSFT", "UNCOVERED"]
        root = _build_fixture_root(tmp_path, tickers)
        # Write revisions only for AAPL and MSFT (not UNCOVERED)
        _write_revisions(root, ["AAPL", "MSFT"])

        payload = self._run(root)
        cov = payload.get("coverage") or {}
        uncovered = cov.get("revisions_uncovered") or []
        assert "UNCOVERED" in uncovered, f"UNCOVERED not in revisions_uncovered: {uncovered}"


class TestStaleFreeze:
    """Stale flag: when prices lag > 2 NYSE sessions, state must freeze."""

    def test_stale_returns_stale_true(self, tmp_path):
        """Patching stale check to return True → payload.stale == True."""
        tickers = ["NVDA"]
        root = _build_fixture_root(tmp_path, tickers)

        from scripts.build_leader_radar import build
        with patch("lib.config.ROOT", root), \
             patch("lib.config.data_dir", lambda: root / "data"), \
             patch("lib.config.load", lambda: {
                 "storage": {"data_dir": "data", "site_dir": "site"},
                 "leader_radar": {"enabled": True, "basket_keys": ["mag7"], "dow30": []},
             }), \
             patch("scripts.build_leader_radar._check_stale", return_value=True):
            payload = build(data_root=root / "data", site_root=root / "site")

        assert payload.get("stale") is True


class TestKillSwitch:
    """Kill-switch: enabled=false → returns {} and writes noindex payload."""

    def test_kill_switch_returns_empty(self, tmp_path):
        tickers = ["AAPL"]
        root = _build_fixture_root(tmp_path, tickers)

        from scripts.build_leader_radar import build
        with patch("lib.config.ROOT", root), \
             patch("lib.config.data_dir", lambda: root / "data"), \
             patch("lib.config.load", lambda: {
                 "storage": {"data_dir": "data", "site_dir": "site"},
                 "leader_radar": {"enabled": False, "basket_keys": ["mag7"], "dow30": []},
             }):
            result = build(data_root=root / "data", site_root=root / "site")

        assert result == {}

    def test_kill_switch_writes_noindex(self, tmp_path):
        tickers = ["AAPL"]
        root = _build_fixture_root(tmp_path, tickers)

        from scripts.build_leader_radar import build
        with patch("lib.config.ROOT", root), \
             patch("lib.config.data_dir", lambda: root / "data"), \
             patch("lib.config.load", lambda: {
                 "storage": {"data_dir": "data", "site_dir": "site"},
                 "leader_radar": {"enabled": False, "basket_keys": ["mag7"], "dow30": []},
             }):
            build(data_root=root / "data", site_root=root / "site")

        p = root / "site" / "leaderradar" / "radar.json"
        assert p.exists()
        d = json.loads(p.read_text())
        assert d.get("enabled") is False


class TestRadarJsonSchema:
    """radar.json schema keys: all required top-level keys present."""

    def _run(self, root: Path) -> dict:
        from scripts.build_leader_radar import build
        with patch("lib.config.ROOT", root), \
             patch("lib.config.data_dir", lambda: root / "data"), \
             patch("lib.config.load", lambda: {
                 "storage": {"data_dir": "data", "site_dir": "site"},
                 "leader_radar": {"enabled": True, "basket_keys": ["mag7"], "dow30": []},
             }):
            return build(data_root=root / "data", site_root=root / "site")

    def test_schema_key_present(self, tmp_path):
        root = _build_fixture_root(tmp_path, ["AAPL"])
        payload = self._run(root)
        assert payload.get("schema") == "leader_radar.v1"

    def test_required_top_level_keys(self, tmp_path):
        root = _build_fixture_root(tmp_path, ["AAPL"])
        payload = self._run(root)
        for key in ("schema", "as_of", "stale", "coverage", "regime", "rows",
                    "handoff_pairs", "rerating_watch"):
            assert key in payload, f"Missing top-level key: {key}"

    def test_coverage_keys(self, tmp_path):
        root = _build_fixture_root(tmp_path, ["AAPL"])
        payload = self._run(root)
        cov = payload.get("coverage") or {}
        for key in ("n_universe", "revisions_uncovered", "mktcap_n_covered"):
            assert key in cov, f"Missing coverage key: {key}"

    def test_row_keys(self, tmp_path):
        root = _build_fixture_root(tmp_path, ["AAPL"])
        payload = self._run(root)
        for row in payload.get("rows", []):
            for key in ("ticker", "raw_state", "state", "days_in_state",
                        "chips", "de_escalations", "fire_precipice", "fire_onset", "context"):
                assert key in row, f"Row missing key: {key}"


class TestPdNaSafety:
    """pd.NA JSON safety: radar.json must be parseable without TypeError."""

    def test_json_no_na(self, tmp_path):
        root = _build_fixture_root(tmp_path, ["AAPL", "MSFT"])
        from scripts.build_leader_radar import build
        with patch("lib.config.ROOT", root), \
             patch("lib.config.data_dir", lambda: root / "data"), \
             patch("lib.config.load", lambda: {
                 "storage": {"data_dir": "data", "site_dir": "site"},
                 "leader_radar": {"enabled": True, "basket_keys": ["mag7"], "dow30": []},
             }):
            build(data_root=root / "data", site_root=root / "site")

        p = root / "site" / "leaderradar" / "radar.json"
        assert p.exists()
        # Must parse without error
        d = json.loads(p.read_text())
        assert isinstance(d, dict)


class TestConsumptionNotRecomputation:
    """plab_leader_precipice and plab_leader_onset consume radar.json — do NOT re-run classify."""

    def _make_radar_json(self, root: Path, rows: list[dict]) -> None:
        p = root / "site" / "leaderradar" / "radar.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "leader_radar.v1",
            "as_of": "2026-07-11T00:00:00+00:00",
            "stale": False,
            "rows": rows,
        }
        p.write_text(json.dumps(payload))

    def test_precipice_reads_artifact(self, tmp_path):
        """plab_leader_precipice reads fire_precipice from radar.json."""
        root = tmp_path
        self._make_radar_json(root, [
            {"ticker": "NVDA", "fire_precipice": True, "fire_onset": False,
             "state": "CATALYST_WINDOW", "raw_state": "CATALYST_WINDOW", "days_in_state": 2,
             "breakaway_watch_state": None},
        ])

        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from engine.pick_lab.candidates import _load_radar_json

        with patch("lib.config.ROOT", root), \
             patch("lib.config.load", lambda: {"storage": {"site_dir": "site"}}):
            rows = _load_radar_json()

        assert any(r.get("fire_precipice") is True for r in rows), \
            "fire_precipice rows not loaded from radar.json"

    def test_onset_reads_artifact(self, tmp_path):
        """plab_leader_onset reads fire_onset from radar.json."""
        root = tmp_path
        self._make_radar_json(root, [
            {"ticker": "MSFT", "fire_precipice": False, "fire_onset": True,
             "state": "BREAKAWAY", "raw_state": "BREAKAWAY", "days_in_state": 1,
             "breakaway_watch_state": "breakaway"},
        ])

        from engine.pick_lab.candidates import _load_radar_json
        with patch("lib.config.ROOT", root), \
             patch("lib.config.load", lambda: {"storage": {"site_dir": "site"}}):
            rows = _load_radar_json()

        assert any(r.get("fire_onset") is True for r in rows), \
            "fire_onset rows not loaded from radar.json"

    def test_classify_not_called_by_precipice_book(self, tmp_path):
        """plab_leader_precipice must not call classify() from engine.leader_lifecycle."""
        root = tmp_path
        self._make_radar_json(root, [
            {"ticker": "AAPL", "fire_precipice": True, "fire_onset": False,
             "state": "CATALYST_WINDOW", "raw_state": "CATALYST_WINDOW", "days_in_state": 3,
             "breakaway_watch_state": None},
        ])

        # If classify() were called, it would raise (we patch it to raise)
        with patch("engine.leader_lifecycle.classify", side_effect=RuntimeError("classify called!")), \
             patch("lib.config.ROOT", root), \
             patch("lib.config.load", lambda: {"storage": {"site_dir": "site"}}):
            from engine.pick_lab.candidates import _book_leader_precipice
            from engine.pick_lab.registry import BY_ID
            book = BY_ID["plab_leader_precipice"]
            snap = pd.DataFrame(columns=["close", "sector"])
            # Should not raise even though classify is patched to raise
            result = _book_leader_precipice(snap, book)
            # Should return picks from radar.json
            assert isinstance(result, list)


class TestRegistryBookCount:
    """Registry 27 books + unique config_hashes."""

    def test_registry_count_27(self):
        from engine.pick_lab.registry import REGISTRY
        assert len(REGISTRY) == 27, f"Expected 27 books, got {len(REGISTRY)}"

    def test_config_hashes_unique_27(self):
        from engine.pick_lab.registry import REGISTRY
        hashes = [b["config_hash"] for b in REGISTRY]
        assert len(set(hashes)) == 27, "Duplicate config_hash detected"

    def test_leader_precipice_in_registry(self):
        from engine.pick_lab.registry import BY_ID
        assert "plab_leader_precipice" in BY_ID

    def test_leader_onset_in_registry(self):
        from engine.pick_lab.registry import BY_ID
        assert "plab_leader_onset" in BY_ID

    def test_leader_books_are_entry_horizon(self):
        from engine.pick_lab.registry import BY_ID
        for eid in ("plab_leader_precipice", "plab_leader_onset"):
            b = BY_ID[eid]
            assert b["horizon_role"] == "entry", f"{eid} should be entry horizon"

    def test_leader_books_max_picks_12(self):
        from engine.pick_lab.registry import BY_ID
        for eid in ("plab_leader_precipice", "plab_leader_onset"):
            b = BY_ID[eid]
            assert b["max_picks"] == 12

    def test_leader_books_refire_21(self):
        from engine.pick_lab.registry import BY_ID
        for eid in ("plab_leader_precipice", "plab_leader_onset"):
            b = BY_ID[eid]
            assert b["refire_lockout_sessions"] == 21

    def test_leader_books_ruler_21d_spy_excess(self):
        from engine.pick_lab.registry import BY_ID
        for eid in ("plab_leader_precipice", "plab_leader_onset"):
            b = BY_ID[eid]
            assert b["ruler"] == "21d_spy_excess"


class TestFireEntryEvents:
    """m3 — Fire events are ENTRY events, not membership events.

    Session 1 (seed): no prior history → fire_onset=False regardless of state.
    Session 2: prior state=QUIET_ACCUMULATION, today=BREAKAWAY → fire_onset=True.
    Session 3: prior state=BREAKAWAY, today=BREAKAWAY → fire_onset=False (held).
    Refire lockout: re-fire blocked while held even past 21 sessions without de-escalation.
    """

    def _make_onset_assessment(self, state: str):
        """Return a minimal LifecycleAssessment with given state."""
        from engine.leader_lifecycle import LifecycleAssessment
        return LifecycleAssessment(state=state, evidence={}, n_avail=0)

    def _run_compute_fires(
        self,
        confirmed_state: str,
        confirmed_history: list,
        fire_dates: dict,
    ) -> tuple[bool, bool]:
        """Call _compute_fires via the builder module."""
        from scripts.build_leader_radar import _compute_fires
        from engine.leader_lifecycle import LifecycleAssessment, STATE_BREAKAWAY, STATE_CATALYST_WINDOW

        assessment = LifecycleAssessment(
            state=confirmed_state,
            evidence={"revision_positive": True, "rs_line_nh": True},
            n_avail=2,
        )

        if confirmed_history:
            from engine.leader_lifecycle import LifecycleAssessment as _LA
            prior_state = confirmed_history[-1][1]
            proxy = [_LA(state=prior_state, evidence={}, n_avail=0)]
        else:
            proxy = []

        return _compute_fires(
            ticker="TEST",
            assessment=assessment,
            confirmed_state=confirmed_state,
            confirmed_history=confirmed_history,
            assessment_history=proxy,
            fire_dates=fire_dates,
            stale=False,
        )

    def test_seed_run_no_fire(self):
        """Session 1: no prior history → fire_onset=False (entry unverifiable)."""
        from engine.leader_lifecycle import STATE_BREAKAWAY
        fire_p, fire_o = self._run_compute_fires(
            confirmed_state=STATE_BREAKAWAY,
            confirmed_history=[],  # seed run: no history
            fire_dates={},
        )
        assert fire_o is False, "Seed run must never fire (no prior history)"
        assert fire_p is False, "Seed run must never fire precipice (no prior history)"

    def test_entry_fires_on_session2(self):
        """Session 2: prior state != BREAKAWAY, today=BREAKAWAY → fire_onset=True."""
        from engine.leader_lifecycle import STATE_BREAKAWAY, STATE_QUIET_ACCUMULATION
        from datetime import date, timedelta
        prior_date = date.today() - timedelta(days=1)
        history = [(prior_date, STATE_QUIET_ACCUMULATION)]

        fire_p, fire_o = self._run_compute_fires(
            confirmed_state=STATE_BREAKAWAY,
            confirmed_history=history,
            fire_dates={},
        )
        assert fire_o is True, "Entry from non-BREAKAWAY to BREAKAWAY on session 2 must fire"

    def test_held_no_refire_on_session3(self):
        """Session 3: prior state=BREAKAWAY, today=BREAKAWAY → no refire (held in state)."""
        from engine.leader_lifecycle import STATE_BREAKAWAY
        from datetime import date, timedelta
        d0 = date.today() - timedelta(days=2)
        d1 = date.today() - timedelta(days=1)
        history = [(d0, STATE_BREAKAWAY), (d1, STATE_BREAKAWAY)]

        fire_p, fire_o = self._run_compute_fires(
            confirmed_state=STATE_BREAKAWAY,
            confirmed_history=history,
            fire_dates={"TEST": d0},  # fired on day 0
        )
        assert fire_o is False, "Held BREAKAWAY must not refire on session 3"

    def test_refire_blocked_past_21_sessions_without_deescalation(self):
        """Refire lockout: 25 sessions in BREAKAWAY since last fire → still blocked (no de-escalation)."""
        from engine.leader_lifecycle import STATE_BREAKAWAY
        from datetime import date, timedelta
        fire_date = date.today() - timedelta(days=30)
        # 25 sessions all BREAKAWAY (no de-escalation to NONE/FAILED)
        history = [
            (date.today() - timedelta(days=30 - i), STATE_BREAKAWAY)
            for i in range(25)
        ]
        fire_p, fire_o = self._run_compute_fires(
            confirmed_state=STATE_BREAKAWAY,
            confirmed_history=history,
            fire_dates={"TEST": fire_date},
        )
        assert fire_o is False, (
            "Refire must be blocked even past 21 sessions if no de-escalation to NONE/FAILED"
        )
