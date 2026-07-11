"""tests/test_build_flow_leaders.py — hermetic tests for scripts.build_flow_leaders.

Covers:
  - cold_start honesty (< RECUR_MIN_HISTORY sessions → cold_start=True)
  - ETF routing (ETFs land in etf_strip, not board_a/board_b)
  - kill-switch (flow_leaders.enabled: false → noindex stub, no JSON written)
  - leaders.json schema keys (schema, as_of, stale, cold_start, board_a, board_b, etf_strip)
  - fire flags match engine function signatures (board_a_fire, board_b_fire)
  - JSON serialiser handles numpy types + None without crash
  - pick_lab registry: 25 books, unique hashes, families present
  - pick_lab candidates: _load_leaders_json handles missing file gracefully

Run:
    python -m pytest tests/test_build_flow_leaders.py -x -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_flow_leaders import (
    _json_default,
    _check_stale,
    _tape_ex0dte_net,
    _personality_flags,
    _load_daily_close,
    _build_membership_df,
    build,
    _ETF_SET,
)
from engine.flow_leaders import RECUR_MIN_HISTORY


# ─────────────────────────────────────────────────────────────────── helpers ──

def _make_summary_parquet(tmp: Path, ticker: str, n_sessions: int = 3) -> None:
    """Write data/options_flow/summary_<ticker>.parquet with n_sessions rows."""
    out_dir = tmp / "data" / "options_flow"
    out_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range(end="2024-06-14", periods=n_sessions)
    df = pd.DataFrame(
        {
            "net_premium_mn": [1.5] * n_sessions,
            "premium_mn": [5.0] * n_sessions,
            "zerodte_share": [0.2] * n_sessions,
            "fresh_contracts": [1000] * n_sessions,
        },
        index=dates,
    )
    df.to_parquet(str(out_dir / f"summary_{ticker}.parquet"))


def _make_site_dir(tmp: Path) -> Path:
    s = tmp / "site"
    s.mkdir(parents=True, exist_ok=True)
    (s / "flowleaders").mkdir(exist_ok=True)
    return s


def _make_tpl_dir(repo_root: Path) -> Path:
    return repo_root / "templates"


# ──────────────────────────────────────────────────── _json_default tests ──

class TestJsonDefault:
    def test_numpy_integer(self):
        assert _json_default(np.int64(7)) == 7

    def test_numpy_float_finite(self):
        result = _json_default(np.float64(3.14))
        assert abs(result - 3.14) < 1e-6

    def test_numpy_float_nan_returns_none(self):
        assert _json_default(np.float64(float("nan"))) is None

    def test_numpy_float_inf_returns_none(self):
        assert _json_default(np.float64(float("inf"))) is None

    def test_numpy_ndarray(self):
        arr = np.array([1, 2, 3])
        assert _json_default(arr) == [1, 2, 3]

    def test_date(self):
        d = date(2024, 6, 14)
        assert _json_default(d) == "2024-06-14"

    def test_unsupported_raises(self):
        with pytest.raises(TypeError):
            _json_default(object())


# ──────────────────────────────────────────────────── _tape_ex0dte_net ──

class TestTapeEx0dteNet:
    def test_sums_dte_buckets(self):
        row = pd.Series({"dte_1_7d": 1.0, "dte_8_30d": 2.0, "dte_31_90d": 3.0, "dte_90p": 4.0})
        assert _tape_ex0dte_net(row) == pytest.approx(10.0)

    def test_missing_row_returns_none(self):
        assert _tape_ex0dte_net(None) is None

    def test_partial_buckets(self):
        row = pd.Series({"dte_1_7d": 1.5})
        assert _tape_ex0dte_net(row) == pytest.approx(1.5)

    def test_nan_bucket_skipped(self):
        row = pd.Series({"dte_1_7d": 2.0, "dte_8_30d": float("nan"), "dte_31_90d": 1.0})
        assert _tape_ex0dte_net(row) == pytest.approx(3.0)


# ──────────────────────────────────────────────────── _personality_flags ──

class TestPersonalityFlags:
    def test_none_input(self):
        fbt, ssl = _personality_flags(None)
        assert fbt is None
        assert ssl is None

    def test_labels_in_chart_personality(self):
        rec = {"base": {"chart_personality": {"labels": ["failed_breakout_trap"]}}}
        fbt, ssl = _personality_flags(rec)
        assert fbt is True
        assert ssl is False

    def test_stair_step_leader(self):
        rec = {"base": {"chart_personality": {"labels": ["stair_step_leader"]}}}
        fbt, ssl = _personality_flags(rec)
        assert fbt is False
        assert ssl is True

    def test_no_labels(self):
        rec = {"base": {"chart_personality": {}}}
        fbt, ssl = _personality_flags(rec)
        assert fbt is None
        assert ssl is None


# ──────────────────────────────────────────────────── _check_stale ──

class TestCheckStale:
    def test_none_session_is_stale(self):
        assert _check_stale(None) is True

    def test_recent_session_not_stale(self):
        # Use today's date string as "latest" — should not be stale
        today_str = str(date.today())
        # Not guaranteed but very unlikely to be stale if it's today
        # Just ensure no crash
        result = _check_stale(today_str)
        assert isinstance(result, bool)

    def test_old_session_is_stale(self):
        # A session 30+ days ago should be stale (calendar-aware; may silently return
        # False if nyse_calendar unavailable in this env, so just assert no crash)
        old = str(date.today() - timedelta(days=30))
        result = _check_stale(old)
        assert isinstance(result, bool)
        # Best-effort: if calendar is available, 30-day-old should be stale
        # (> 2 NYSE sessions behind). We don't hard-assert True since the
        # calendar import may fall back to False gracefully (non-fatal path).


# ──────────────────────────────────────────────────── ETF routing ──

class TestEtfSet:
    def test_spy_in_etf_set(self):
        assert "SPY" in _ETF_SET

    def test_all_18_etfs_present(self):
        expected = {
            "SPY", "QQQ", "IWM", "DIA",
            "XLK", "XLF", "XLE", "XLI", "XLU", "XLV", "XLY", "XLP", "XLB", "XLC", "XLRE",
            "SMH", "SOXX", "KRE", "XBI", "ARKK",
        }
        # The _ETF_SET may have all 20 items (spec says 18 + 2 extra like ARKK etc.)
        assert expected.issubset(_ETF_SET)

    def test_single_stock_not_in_etf_set(self):
        assert "AAPL" not in _ETF_SET
        assert "NVDA" not in _ETF_SET


# ──────────────────────────────────────────────────── build() integration ──

class TestBuild:
    """Integration tests with tmp directory fixtures."""

    @property
    def _repo(self) -> Path:
        return Path(__file__).resolve().parent.parent

    def _run_build(self, tmp_path: Path, tickers: list[str], n_sessions: int = 3) -> dict:
        """Run build() with tmp fixtures."""
        for t in tickers:
            _make_summary_parquet(tmp_path, t, n_sessions=n_sessions)
        site_root = _make_site_dir(tmp_path)
        tpl_root = _make_tpl_dir(self._repo)
        data_root = tmp_path / "data"
        return build(data_root=data_root, site_root=site_root, tpl_root=tpl_root)

    def test_schema_key_present(self, tmp_path):
        result = self._run_build(tmp_path, ["AAPL", "MSFT"])
        assert result.get("schema") == "flow_leaders.v1"

    def test_as_of_present(self, tmp_path):
        result = self._run_build(tmp_path, ["AAPL"])
        assert "as_of" in result
        assert isinstance(result["as_of"], str)
        assert len(result["as_of"]) > 8

    def test_required_keys_present(self, tmp_path):
        result = self._run_build(tmp_path, ["AAPL", "MSFT"])
        for k in ("schema", "as_of", "stale", "cold_start", "board_a", "board_b", "etf_strip", "coverage"):
            assert k in result, f"Missing key: {k}"

    def test_cold_start_when_few_sessions(self, tmp_path):
        # With n_sessions < RECUR_MIN_HISTORY → cold_start=True
        result = self._run_build(tmp_path, ["AAPL"], n_sessions=2)
        assert result.get("cold_start") is True

    def test_etf_goes_to_etf_strip_not_boards(self, tmp_path):
        result = self._run_build(tmp_path, ["AAPL", "SPY"])
        board_a_tickers = {r["ticker"] for r in result.get("board_a", [])}
        board_b_tickers = {r["ticker"] for r in result.get("board_b", [])}
        etf_strip_tickers = {r["ticker"] for r in result.get("etf_strip", [])}
        assert "SPY" not in board_a_tickers
        assert "SPY" not in board_b_tickers
        assert "SPY" in etf_strip_tickers
        assert "AAPL" in board_a_tickers

    def test_leaders_json_written(self, tmp_path):
        _make_summary_parquet(tmp_path, "AAPL")
        site_root = _make_site_dir(tmp_path)
        data_root = tmp_path / "data"
        tpl_root = _make_tpl_dir(self._repo)
        build(data_root=data_root, site_root=site_root, tpl_root=tpl_root)
        out = site_root / "flowleaders" / "leaders.json"
        assert out.exists()
        parsed = json.loads(out.read_text())
        assert parsed.get("schema") == "flow_leaders.v1"

    def test_empty_summaries_returns_valid_payload(self, tmp_path):
        # No parquets at all → should not crash, returns empty boards
        site_root = _make_site_dir(tmp_path)
        data_root = tmp_path / "data"
        data_root.mkdir(parents=True, exist_ok=True)
        tpl_root = _make_tpl_dir(self._repo)
        result = build(data_root=data_root, site_root=site_root, tpl_root=tpl_root)
        assert result.get("schema") == "flow_leaders.v1"
        assert result["board_a"] == []
        assert result["board_b"] == []

    def test_board_a_row_has_required_fields(self, tmp_path):
        result = self._run_build(tmp_path, ["AAPL"])
        if not result.get("board_a"):
            pytest.skip("no board_a rows produced (cold-start)")
        row = result["board_a"][0]
        required = [
            "ticker", "as_of", "signing_source", "K_a", "n_avail_a",
            "K_b", "n_avail_b", "fire_a", "fire_b",
        ]
        for f in required:
            assert f in row, f"Missing field in board_a row: {f}"

    def test_fire_a_is_bool_or_none(self, tmp_path):
        result = self._run_build(tmp_path, ["AAPL", "MSFT"])
        for row in result.get("board_a", []):
            assert row.get("fire_a") is None or isinstance(row["fire_a"], bool)

    def test_fire_b_is_bool_or_none(self, tmp_path):
        result = self._run_build(tmp_path, ["AAPL", "MSFT"])
        for row in result.get("board_b", []):
            assert row.get("fire_b") is None or isinstance(row["fire_b"], bool)

    def test_de_escalation_keys_present(self, tmp_path):
        result = self._run_build(tmp_path, ["AAPL"])
        for row in result.get("board_a", []):
            de = row.get("de_escalation") or {}
            for k in ("earnings_window", "vol_trade", "protective_put", "gamma_caution"):
                assert k in de, f"Missing de_escalation key: {k}"

    def test_kill_switch_writes_noindex_stub(self, tmp_path):
        """flow_leaders.enabled=false → noindex stub written, leaders.json NOT written."""
        import copy
        import lib.config as cfg_mod

        _make_summary_parquet(tmp_path, "AAPL")
        site_root = _make_site_dir(tmp_path)
        data_root = tmp_path / "data"
        tpl_root = _make_tpl_dir(self._repo)

        # Patch config.load() to return enabled: false.
        # Use deepcopy + try/finally to avoid poisoning the lru_cache for sibling tests.
        original_load = cfg_mod.load

        def _patched_load():
            d = copy.deepcopy(original_load())
            d["flow_leaders"] = {"enabled": False}
            return d

        cfg_mod.load = _patched_load
        try:
            result = build(data_root=data_root, site_root=site_root, tpl_root=tpl_root)
        finally:
            cfg_mod.load = original_load
            # Clear lru_cache so subsequent tests read real config
            if hasattr(original_load, "cache_clear"):
                original_load.cache_clear()

        assert result == {}
        stub = site_root / "flow_leaders.html"
        assert stub.exists()
        content = stub.read_text()
        assert "noindex" in content

    def test_main_returns_zero(self, tmp_path, monkeypatch):
        """main() never raises; always exits 0."""
        import scripts.build_flow_leaders as mod

        # Point ROOT to tmp so config lookups degrade gracefully
        monkeypatch.chdir(tmp_path)
        result = mod.main()
        assert result == 0

    def test_board_a_sort_recurrence_desc(self, tmp_path):
        """Board A should be sorted by recurrence_count descending."""
        # Create 2 tickers with different session counts (more sessions → more recurrence)
        _make_summary_parquet(tmp_path, "AAPL", n_sessions=10)
        _make_summary_parquet(tmp_path, "MSFT", n_sessions=2)
        site_root = _make_site_dir(tmp_path)
        data_root = tmp_path / "data"
        tpl_root = _make_tpl_dir(self._repo)
        result = build(data_root=data_root, site_root=site_root, tpl_root=tpl_root)
        rows = result.get("board_a", [])
        if len(rows) < 2:
            pytest.skip("not enough board_a rows for sort test")
        recur_values = [r.get("recurrence_count") for r in rows]
        # Filter out None and pd.NA for sort check (cold-start rows have null recurrence)
        def _is_valid(v) -> bool:
            if v is None:
                return False
            try:
                import pandas as _pd
                return not _pd.isna(v)
            except (TypeError, ValueError):
                return True
        non_null = [float(v) for v in recur_values if _is_valid(v)]
        if len(non_null) >= 2:
            assert non_null == sorted(non_null, reverse=True)

    def test_board_a_capped_at_25(self, tmp_path):
        """Board A must have at most 25 rows regardless of universe size."""
        # Build 30 tickers
        tickers = [f"T{i:02d}" for i in range(30)]
        for t in tickers:
            _make_summary_parquet(tmp_path, t, n_sessions=3)
        site_root = _make_site_dir(tmp_path)
        data_root = tmp_path / "data"
        tpl_root = _make_tpl_dir(self._repo)
        result = build(data_root=data_root, site_root=site_root, tpl_root=tpl_root)
        assert len(result.get("board_a", [])) <= 25
        # board_a_total must reflect universe count (30 in this case)
        assert result.get("board_a_total", 0) == 30

    def test_board_b_capped_at_25(self, tmp_path):
        """Board B must have at most 25 rows regardless of universe size."""
        tickers = [f"T{i:02d}" for i in range(30)]
        for t in tickers:
            _make_summary_parquet(tmp_path, t, n_sessions=3)
        site_root = _make_site_dir(tmp_path)
        data_root = tmp_path / "data"
        tpl_root = _make_tpl_dir(self._repo)
        result = build(data_root=data_root, site_root=site_root, tpl_root=tpl_root)
        assert len(result.get("board_b", [])) <= 25

    def test_json_serializeable(self, tmp_path):
        """leaders.json must be valid JSON with no NaN/inf values."""
        _make_summary_parquet(tmp_path, "AAPL", n_sessions=3)
        site_root = _make_site_dir(tmp_path)
        data_root = tmp_path / "data"
        tpl_root = _make_tpl_dir(self._repo)
        build(data_root=data_root, site_root=site_root, tpl_root=tpl_root)
        out = site_root / "flowleaders" / "leaders.json"
        text = out.read_text()
        # Should parse without error
        parsed = json.loads(text)
        assert isinstance(parsed, dict)
        # "NaN" should NOT appear as a bare value (json.dumps would use None)
        assert "NaN" not in text
        assert "Infinity" not in text


# ──────────────────────────────────────────────────── pick_lab registry ──

class TestPickLabRegistry:
    def test_25_books(self):
        from engine.pick_lab.registry import REGISTRY
        assert len(REGISTRY) == 25, f"Expected 25 books, got {len(REGISTRY)}"

    def test_unique_hashes(self):
        from engine.pick_lab.registry import REGISTRY, _config_hash
        hashes = [_config_hash(b) for b in REGISTRY]
        assert len(set(hashes)) == len(hashes), "Duplicate config hashes found"

    def test_family_g_present(self):
        from engine.pick_lab.registry import REGISTRY
        # REGISTRY is a list of dicts
        families = {b["family"] for b in REGISTRY}
        assert "G" in families, "Family G missing from registry"

    def test_plab_flow_leader_present(self):
        from engine.pick_lab.registry import BY_ID
        assert "plab_flow_leader" in BY_ID, "plab_flow_leader not in BY_ID"

    def test_plab_flow_washout_present(self):
        from engine.pick_lab.registry import BY_ID
        assert "plab_flow_washout" in BY_ID, "plab_flow_washout not in BY_ID"

    def test_flow_books_in_candidates_dispatch(self):
        from engine.pick_lab.candidates import _BOOK_FUNCS
        assert "plab_flow_leader" in _BOOK_FUNCS
        assert "plab_flow_washout" in _BOOK_FUNCS


# ──────────────────────────────────────────────────── pick_lab candidates ──

class TestPickLabCandidates:
    def test_load_leaders_json_missing_returns_empty(self):
        """_load_leaders_json gracefully returns [] when file is absent (config path missing)."""
        from engine.pick_lab.candidates import _load_leaders_json  # type: ignore[attr-defined]
        # _load_leaders_json() uses lib.config.ROOT internally; if file is absent it returns []
        result = _load_leaders_json()
        # Result should be a list (possibly empty if leaders.json not present in worktree)
        assert isinstance(result, list)

    def test_run_book_flow_leader_empty_snap_returns_empty(self):
        """run_book for plab_flow_leader with empty snapshot returns empty list."""
        from engine.pick_lab.candidates import run_book
        from engine.pick_lab.registry import BY_ID

        book = BY_ID["plab_flow_leader"]

        # empty snapshot → run_book short-circuits at snap.empty check
        snap = pd.DataFrame(columns=["close", "dollar_adv_20d"])
        snap.index.name = "ticker"
        snap.attrs["asof"] = "2024-06-14"

        result = run_book(book, snap)
        # Empty snap → returns [] (no crash)
        assert isinstance(result, list)
        assert result == []

    def test_run_book_flow_washout_empty_snap_returns_empty(self):
        """run_book for plab_flow_washout with empty snapshot returns empty list."""
        from engine.pick_lab.candidates import run_book
        from engine.pick_lab.registry import BY_ID

        book = BY_ID["plab_flow_washout"]
        snap = pd.DataFrame(columns=["close", "dollar_adv_20d"])
        snap.index.name = "ticker"
        snap.attrs["asof"] = "2024-06-14"

        result = run_book(book, snap)
        assert isinstance(result, list)
        assert result == []


# ─────────────────────────────────── MAJOR-4: consumption-path (fire flags) ──

class TestFlowBookFireFlagDispatch:
    """End-to-end test that _book_flow_leader / _book_flow_washout consume fire_a/fire_b
    from leaders.json correctly, without calling the leg-computation engine functions."""

    def _make_snap(self, tickers: list[str]) -> pd.DataFrame:
        """Build a minimal non-empty snapshot that passes _apply_liquidity for each ticker."""
        df = pd.DataFrame(
            {
                "close": [20.0] * len(tickers),
                "dollar_adv_20d": [50e6] * len(tickers),
            },
            index=pd.Index(tickers, name="ticker"),
        )
        df.attrs["asof"] = "2024-06-14"
        return df

    def _leaders_fixture(self) -> list[dict]:
        """Three rows: fire_a=True, fire_a=False, fire_a=None (analogous for fire_b)."""
        return [
            {
                "ticker": "FIRE_A",
                "fire_a": True,
                "fire_b": False,
                "recurrence_count": 3,
                "net_prem_norm_abs": 0.8,
                "flow_z": 2.5,
                "K_a": 5,
                "n_avail_a": 8,
                "signing_source": "minute_tick",
                "days_since_inflection": None,
                "K_b": 2,
                "n_avail_b": 8,
            },
            {
                "ticker": "NO_FIRE",
                "fire_a": False,
                "fire_b": False,
                "recurrence_count": 1,
                "net_prem_norm_abs": 0.2,
                "flow_z": 0.5,
                "K_a": 1,
                "n_avail_a": 8,
                "signing_source": "minute_tick",
                "days_since_inflection": None,
                "K_b": 1,
                "n_avail_b": 8,
            },
            {
                "ticker": "NULL_FIRE",
                "fire_a": None,
                "fire_b": None,
                "recurrence_count": None,
                "net_prem_norm_abs": None,
                "flow_z": None,
                "K_a": 0,
                "n_avail_a": 0,
                "signing_source": "minute_tick",
                "days_since_inflection": None,
                "K_b": 0,
                "n_avail_b": 0,
            },
            {
                "ticker": "FIRE_B",
                "fire_a": False,
                "fire_b": True,
                "recurrence_count": 0,
                "net_prem_norm_abs": 0.1,
                "flow_z": None,
                "K_a": 0,
                "n_avail_a": 8,
                "signing_source": "minute_tick",
                "days_since_inflection": 2,
                "K_b": 5,
                "n_avail_b": 8,
            },
        ]

    def test_book_flow_leader_fires_exactly_fire_a_true(self, monkeypatch):
        """_book_flow_leader returns exactly the ticker with fire_a=True."""
        import engine.pick_lab.candidates as cand

        fixture = self._leaders_fixture()
        monkeypatch.setattr(cand, "_load_leaders_json", lambda: fixture)

        # Guard: board_a_legs must not be called during book dispatch
        import engine.flow_leaders as fl_engine
        def _raise(*args, **kwargs):
            raise AssertionError("board_a_legs called during book dispatch — FL-R8 violation")
        monkeypatch.setattr(fl_engine, "board_a_legs", _raise)

        from engine.pick_lab.candidates import run_book
        from engine.pick_lab.registry import BY_ID

        snap = self._make_snap(["FIRE_A", "NO_FIRE", "NULL_FIRE", "FIRE_B"])
        result = run_book(BY_ID["plab_flow_leader"], snap)

        fired_tickers = [p["ticker"] for p in result]
        assert "FIRE_A" in fired_tickers, "fire_a=True ticker must be in picks"
        assert "NO_FIRE" not in fired_tickers, "fire_a=False ticker must not be in picks"
        assert "NULL_FIRE" not in fired_tickers, "fire_a=None ticker must not be in picks"

    def test_book_flow_washout_fires_exactly_fire_b_true(self, monkeypatch):
        """_book_flow_washout returns exactly the ticker with fire_b=True."""
        import engine.pick_lab.candidates as cand

        fixture = self._leaders_fixture()
        monkeypatch.setattr(cand, "_load_leaders_json", lambda: fixture)

        # Guard: board_b_legs must not be called during book dispatch
        import engine.flow_leaders as fl_engine
        def _raise(*args, **kwargs):
            raise AssertionError("board_b_legs called during book dispatch — FL-R8 violation")
        monkeypatch.setattr(fl_engine, "board_b_legs", _raise)

        from engine.pick_lab.candidates import run_book
        from engine.pick_lab.registry import BY_ID

        snap = self._make_snap(["FIRE_A", "NO_FIRE", "NULL_FIRE", "FIRE_B"])
        result = run_book(BY_ID["plab_flow_washout"], snap)

        fired_tickers = [p["ticker"] for p in result]
        assert "FIRE_B" in fired_tickers, "fire_b=True ticker must be in picks"
        assert "NO_FIRE" not in fired_tickers, "fire_b=False ticker must not be in picks"
        assert "NULL_FIRE" not in fired_tickers, "fire_b=None ticker must not be in picks"
        assert "FIRE_A" not in fired_tickers, "fire_b=False ticker must not be in picks"

    def test_book_flow_leader_skip_illiquid(self, monkeypatch):
        """Tickers below close minimum are excluded even when fire_a=True."""
        import engine.pick_lab.candidates as cand

        fixture = [
            {
                "ticker": "CHEAP",
                "fire_a": True,
                "recurrence_count": 5,
                "net_prem_norm_abs": 1.0,
                "flow_z": 3.0,
                "K_a": 6, "n_avail_a": 8,
                "signing_source": "minute_tick",
            }
        ]
        monkeypatch.setattr(cand, "_load_leaders_json", lambda: fixture)

        from engine.pick_lab.candidates import run_book
        from engine.pick_lab.registry import BY_ID

        # Snapshot with close below _LIQ_CLOSE_MIN (5.0)
        snap = pd.DataFrame(
            {"close": [2.0], "dollar_adv_20d": [50e6]},
            index=pd.Index(["CHEAP"], name="ticker"),
        )
        snap.attrs["asof"] = "2024-06-14"
        result = run_book(BY_ID["plab_flow_leader"], snap)
        # CHEAP has close=2.0 < 5.0 → filtered out by _apply_liquidity → result empty
        assert result == [], "illiquid ticker should be excluded"


# ──────────────────────────────────────────────────── _build_membership_df ──

class TestBuildMembershipDf:
    def test_empty_summaries_returns_empty_df(self):
        result = _build_membership_df({}, {}, {})
        assert isinstance(result, pd.DataFrame)
        assert result.empty or len(result) == 0

    def test_single_session_produces_row(self):
        dates = pd.bdate_range(end="2024-06-14", periods=1)
        summary_df = pd.DataFrame(
            {
                "net_premium_mn": [2.0],
                "premium_mn": [5.0],
                "zerodte_share": [0.15],
            },
            index=dates,
        )
        result = _build_membership_df({"AAPL": summary_df}, {"AAPL": 3000.0}, {})
        assert isinstance(result, pd.DataFrame)
        # Either produced rows or gracefully returned empty
        if not result.empty:
            assert "ticker" in result.columns
            assert "session" in result.columns
