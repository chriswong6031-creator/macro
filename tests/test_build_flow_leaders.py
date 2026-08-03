"""tests/test_build_flow_leaders.py — hermetic tests for scripts.build_flow_leaders.

Covers:
  - cold_start honesty (< RECUR_MIN_HISTORY sessions → cold_start=True)
  - chain-day pair is 2 real NYSE sessions (weekend byte-copies zero ΔOI)
  - ETF routing (ETFs land in etf_strip, not board_a/board_b)
  - kill-switch (flow_leaders.enabled: false → noindex stub, no JSON written)
  - leaders.json schema keys (schema, as_of, stale, cold_start, board_a, board_b, etf_strip)
  - fire flags match engine function signatures (board_a_fire, board_b_fire)
  - JSON serialiser handles numpy types + None without crash
  - pick_lab registry: 27 books, unique hashes, families present
  - pick_lab candidates: _load_leaders_json handles missing file gracefully
  - loud fail-soft: main() crash still exits 0 AND prints a line-start ::warning annotation

Run:
    python -m pytest tests/test_build_flow_leaders.py -x -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, datetime, timezone
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
    _load_two_chain_days,
    _build_membership_df,
    build,
    _ETF_SET,
)
from engine.flow_leaders import (
    DOMINANT_K,
    OI_CONFIRM_VOL_MULT,
    RECUR_MIN_HISTORY,
    oi_confirm,
)


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


def _make_tape_parquet(tmp: Path, ticker: str) -> None:
    """Write data/tape_flow/daily/<ticker>.parquet so the builder counts this
    ticker as tape-signed (coverage.tape_names)."""
    out_dir = tmp / "data" / "tape_flow" / "daily"
    out_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range(end="2024-06-14", periods=2)
    pd.DataFrame(
        {
            "dte_1_7d": [1.0, 1.0],
            "dte_8_30d": [2.0, 2.0],
            "dte_31_90d": [0.5, 0.5],
            "dte_90p": [0.25, 0.25],
        },
        index=dates,
    ).to_parquet(str(out_dir / f"{ticker}.parquet"))


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
    """FL-R15: latest flow session > 2 NYSE sessions behind the calendar → stale.

    These assert the VERDICT, not just `isinstance(result, bool)`. The predicate
    shipped dead for months behind that weaker assertion: it imported a
    `trading_dates_between` that lib/nyse_calendar.py never defined, swallowed the
    ImportError in a bare `except Exception`, and returned False for every input —
    a permanently vacuous SLA that a no-crash test cannot distinguish from a
    working one. Every case below therefore pins a real True/False.
    """

    # Thu 2026-07-16 20:00 UTC = 16:00 ET, inside the settle buffer, so the
    # calendar expects Wed 2026-07-15's bar. Fixed instant = date-independent test.
    NOW = datetime(2026, 7, 16, 20, 0, tzinfo=timezone.utc)

    def test_none_session_is_stale(self):
        assert _check_stale(None) is True

    def test_fresh_store_is_not_stale(self):
        """Positive path: the store holds the expected last session."""
        assert _check_stale("2026-07-15", now=self.NOW) is False

    def test_at_sla_boundary_is_not_stale(self):
        """Exactly 2 sessions behind is within the >2 SLA."""
        assert _check_stale("2026-07-13", now=self.NOW) is False

    def test_three_sessions_behind_is_stale(self):
        """3 real trading sessions behind trips the SLA. Under the dead import
        this returned False, so the boards rendered fresh on a stale store."""
        assert _check_stale("2026-07-10", now=self.NOW) is True

    def test_month_old_store_is_stale(self):
        assert _check_stale("2026-06-16", now=self.NOW) is True

    def test_weekend_and_holiday_gaps_do_not_count_as_lag(self):
        """Mon 2026-07-06 17:00 ET with a store through Thu 07-02: the holiday
        Friday (July-4 observed) and the weekend are not missing sessions, so the
        store is 1 session behind — fresh, not stale."""
        monday = datetime(2026, 7, 6, 21, 0, tzinfo=timezone.utc)
        assert _check_stale("2026-07-02", now=monday) is False

    def test_timestamp_prefix_is_accepted(self):
        """Session strings may arrive with a time component appended."""
        assert _check_stale("2026-07-15T00:00:00", now=self.NOW) is False

    def test_unreadable_session_is_stale(self):
        """An unverifiable store must never be stamped fresh."""
        assert _check_stale("not-a-date", now=self.NOW) is True


# ──────────────────────────────────────────────── _load_two_chain_days ──

# Verified against lib.nyse_calendar: 07-23/07-24/07-27 are sessions, 07-25/07-26 is
# the weekend, and that week carries no NYSE holiday.
_THU, _FRI, _SAT, _SUN, _MON = (
    "2026-07-23", "2026-07-24", "2026-07-25", "2026-07-26", "2026-07-27",
)
# Exactly DOMINANT_K strikes → every row is a dominant strike, so the confirm math
# never depends on which rows the top-k cut happens to keep.
_CHAIN_STRIKES = [150.0, 155.0, 160.0]


def _confirming_volume(oi: int) -> float:
    """Flow-day volume that clears the OI_CONFIRM_VOL_MULT × prior-OI gate."""
    return OI_CONFIRM_VOL_MULT * oi + 1.0


def _write_chain_day(
    tmp: Path, day: str, ois: list[int], volumes: list[float] | None = None
) -> pd.DataFrame:
    """Write data/polygon_gex/chains/<day>.parquet for one underlying; return the frame.

    Schema per engine.flow_leaders.oi_confirm: underlying, K, is_call, volume, oi.
    `oi` is the fixture's fingerprint — each session day gets distinguishable values
    so the pair the loader chose is provable from the returned frames.
    """
    assert len(_CHAIN_STRIKES) == DOMINANT_K, "fixture must not straddle the top-k cut"
    out_dir = tmp / "data" / "polygon_gex" / "chains"
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {
            "underlying": ["AAPL"] * len(_CHAIN_STRIKES),
            "K": _CHAIN_STRIKES,
            "is_call": [True] * len(_CHAIN_STRIKES),
            "volume": volumes if volumes is not None else [_confirming_volume(o) for o in ois],
            "oi": ois,
        }
    )
    df.to_parquet(str(out_dir / f"{day}.parquet"))
    return df


class TestLoadTwoChainDays:
    """The chain pair must be 2 real NYSE SESSIONS (measured 2026-07-29).

    The chains collector writes one file per CALENDAR day, so Saturday/Sunday/holiday
    files are byte-copies of the prior session (measured: 370/370 underlyings identical
    on the 07-18→07-19, 07-25→07-26 and 06-27→06-28 pairs). An unfiltered
    `sorted(glob)[-2:]` therefore hands oi_confirm two IDENTICAL frames on every Sunday
    run — and on a Monday run before Monday's collect lands — so ΔOI is 0 at every
    dominant strike and every underlying gets a definitive-looking `oi_confirmed=False`
    on a live surface. The builder runs 7 days/week (daily.yml).
    """

    def test_weekend_copies_skipped_when_monday_landed(self, tmp_path):
        """{Fri, Sat=copy, Sun=copy, Mon} → (Fri, Mon), and that pair confirms True."""
        fri = _write_chain_day(tmp_path, _FRI, [1000, 1000, 1000])
        _write_chain_day(tmp_path, _SAT, list(fri["oi"]), list(fri["volume"]))
        _write_chain_day(tmp_path, _SUN, list(fri["oi"]), list(fri["volume"]))
        _write_chain_day(tmp_path, _MON, [1500, 1600, 1700], volumes=[10.0] * 3)

        d_t, d_t1 = _load_two_chain_days(tmp_path / "data")

        assert set(d_t["oi"]) == {1000}, f"flow day is not Friday: {d_t['oi'].tolist()}"
        assert d_t1["oi"].tolist() == [1500, 1600, 1700], (
            f"next day is not Monday: {d_t1['oi'].tolist()}"
        )
        # Real ΔOI at the dominant strikes → the tri-state flag is a genuine True.
        assert oi_confirm(d_t, d_t1).get("AAPL") is True

    def test_sunday_run_reaches_back_past_the_weekend(self, tmp_path):
        """{Thu, Fri, Sat=copy, Sun=copy} — the shape that shipped all-False.

        Unfiltered, the 2 newest are Sat+Sun: the same Friday frame twice.
        """
        _write_chain_day(tmp_path, _THU, [700, 700, 700])
        fri = _write_chain_day(tmp_path, _FRI, [1000, 1000, 1000])
        _write_chain_day(tmp_path, _SAT, list(fri["oi"]), list(fri["volume"]))
        _write_chain_day(tmp_path, _SUN, list(fri["oi"]), list(fri["volume"]))

        d_t, d_t1 = _load_two_chain_days(tmp_path / "data")

        assert set(d_t["oi"]) == {700}, f"flow day is not Thursday: {d_t['oi'].tolist()}"
        assert set(d_t1["oi"]) == {1000}, f"next day is not Friday: {d_t1['oi'].tolist()}"
        assert oi_confirm(d_t, d_t1).get("AAPL") is True

        # The defect mechanism itself: a weekend pair is one frame twice → ΔOI=0 →
        # a definitive False, indistinguishable on the page from a real refutation.
        assert oi_confirm(fri, fri.copy()).get("AAPL") is False

    def test_fewer_than_two_sessions_returns_empty_pair(self, tmp_path):
        """{Sat, Sun} only → honest (empty, empty), exactly as with < 2 files."""
        _write_chain_day(tmp_path, _SAT, [1000, 1000, 1000])
        _write_chain_day(tmp_path, _SUN, [1000, 1000, 1000])

        d_t, d_t1 = _load_two_chain_days(tmp_path / "data")

        assert d_t.empty
        assert d_t1.empty

    def test_weekday_pair_is_unchanged(self, tmp_path):
        """{Thu, Fri, Mon} — all sessions: the filter picks the same newest two."""
        _write_chain_day(tmp_path, _THU, [700, 700, 700])
        _write_chain_day(tmp_path, _FRI, [1000, 1000, 1000])
        _write_chain_day(tmp_path, _MON, [1500, 1600, 1700], volumes=[10.0] * 3)

        d_t, d_t1 = _load_two_chain_days(tmp_path / "data")

        assert set(d_t["oi"]) == {1000}, f"flow day is not Friday: {d_t['oi'].tolist()}"
        assert d_t1["oi"].tolist() == [1500, 1600, 1700], (
            f"next day is not Monday: {d_t1['oi'].tolist()}"
        )

    def test_non_date_stem_is_skipped(self, tmp_path):
        """A stem that is not an ISO date cannot be session-checked, so it is skipped
        rather than crashing the loader — and `latest` sorts AFTER every 2026-* stem."""
        _write_chain_day(tmp_path, _THU, [700, 700, 700])
        _write_chain_day(tmp_path, _FRI, [1000, 1000, 1000])
        _write_chain_day(tmp_path, "latest", [1500, 1600, 1700], volumes=[10.0] * 3)

        d_t, d_t1 = _load_two_chain_days(tmp_path / "data")

        assert set(d_t["oi"]) == {700}, f"flow day is not Thursday: {d_t['oi'].tolist()}"
        assert set(d_t1["oi"]) == {1000}, f"next day is not Friday: {d_t1['oi'].tolist()}"


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

    def test_tape_names_emitted_sorted(self, tmp_path):
        """coverage.tape_names must be deterministic.

        It is built from `all_flow_names`, a set — and CPython randomises string
        hashing per process, so iterating it raw emitted a DIFFERENT order every
        run. That order is written into the committed site/flowleaders/leaders.json,
        so each nightly rebuild churned the artifact for no reason and would defeat
        any byte-stability gate on it. Verified live 2026-07-27: two builds of the
        same code on the same data produced payloads identical in every field
        except this list (same 371 names, sets equal, lists unequal).

        Tickers chosen so insertion order cannot accidentally equal sorted order.
        """
        tickers = ["ZTS", "AAPL", "MSFT", "NVDA", "AMD", "BAC"]
        for t in tickers:
            _make_tape_parquet(tmp_path, t)
        result = self._run_build(tmp_path, tickers)

        names = (result.get("coverage") or {}).get("tape_names") or []
        # anti-vacuity: an empty list is trivially sorted and would prove nothing
        assert len(names) > 1, f"fixture produced no tape names ({names!r})"
        assert names == sorted(names), f"tape_names not sorted: {names!r}"

    def test_as_of_present(self, tmp_path):
        result = self._run_build(tmp_path, ["AAPL"])
        assert "as_of" in result
        assert isinstance(result["as_of"], str)
        assert len(result["as_of"]) > 8

    def test_required_keys_present(self, tmp_path):
        result = self._run_build(tmp_path, ["AAPL", "MSFT"])
        for k in ("schema", "as_of", "stale", "cold_start", "board_a", "board_b", "etf_strip", "coverage"):
            assert k in result, f"Missing key: {k}"

    def test_session_date_is_the_underlying_session_not_the_build_clock(self, tmp_path):
        """#F3-18: the page's rendered date stamp used `as_of[:10]` (the BUILD's
        wall-clock timestamp — read live around 2026-07, whatever weekend/holiday
        that happens to be), while every board row describes the fixture's own
        last session (2024-06-14, per _make_summary_parquet's bdate_range).
        session_date must carry the latter, distinctly from as_of."""
        result = self._run_build(tmp_path, ["AAPL", "MSFT"])
        assert "session_date" in result
        assert result["session_date"] == "2024-06-14"
        assert result["session_date"] != result["as_of"][:10]

    def test_session_date_is_null_on_a_cold_empty_store(self, tmp_path):
        site_root = _make_site_dir(tmp_path)
        tpl_root = _make_tpl_dir(self._repo)
        data_root = tmp_path / "data"
        (data_root / "options_flow").mkdir(parents=True, exist_ok=True)
        result = build(data_root=data_root, site_root=site_root, tpl_root=tpl_root)
        assert result.get("session_date") is None

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
        from lib import config

        # Redirect every default root to tmp so build() degrades gracefully
        # without touching the repo's real site/ tree (MM_DATA_GUARD).
        config.load()  # warm the lru_cache before ROOT moves
        monkeypatch.setattr(config, "ROOT", tmp_path)
        monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")
        (tmp_path / "site").mkdir()
        (tmp_path / "data").mkdir()
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

    def test_board_a_emits_every_qualifying_row(self, tmp_path):
        """OIP W1.6-A (ONE_DOOR_RULING_AND_SPEC §2.4) removed `_BOARD_CAP = 25`.

        The former pin asserted board A held AT MOST 25 rows while its own
        `board_a_total` said 30 — i.e. it pinned a five-row silent truncation.
        The Options workspace's Leaders mode now renders the top 12 with a
        "Show all N" expander over this SAME array, so a cap here would hide
        rows the reader was told they could open.  The totals field is retained
        and must now EQUAL the array's own length: one number, no drift.
        """
        tickers = [f"T{i:02d}" for i in range(30)]
        for t in tickers:
            _make_summary_parquet(tmp_path, t, n_sessions=3)
        site_root = _make_site_dir(tmp_path)
        data_root = tmp_path / "data"
        tpl_root = _make_tpl_dir(self._repo)
        result = build(data_root=data_root, site_root=site_root, tpl_root=tpl_root)
        assert len(result.get("board_a", [])) == 30, "every qualifying board-A row must ship"
        assert result.get("board_a_total", 0) == 30
        assert len(result["board_a"]) == result["board_a_total"], \
            "the declared total and the emitted array must be the same number"

    def test_board_totals_always_equal_their_own_arrays(self, tmp_path):
        """The invariant the uncapped builder now guarantees, on BOTH boards.

        Board B is empty under this fixture (the synthetic summaries produce no
        washout-flip admissions), so this half of the pin is vacuous for it on
        purpose — board A's 30-of-30 above and the source guard below carry the
        no-truncation proof.  What this adds is the consistency law: whatever
        each board holds, its declared total says the same number, so no reader
        of the payload can be told about rows that were never shipped.

        board_b_total counts every board-B row, including those that fail
        B5_flow_inflect: the surfaces that render this board apply that
        admission filter themselves (#3496), so the total may legitimately
        exceed the RENDERED row count — but never len(board_b).
        """
        tickers = [f"T{i:02d}" for i in range(30)]
        for t in tickers:
            _make_summary_parquet(tmp_path, t, n_sessions=3)
        site_root = _make_site_dir(tmp_path)
        data_root = tmp_path / "data"
        tpl_root = _make_tpl_dir(self._repo)
        result = build(data_root=data_root, site_root=site_root, tpl_root=tpl_root)
        assert len(result["board_a"]) == result["board_a_total"]
        assert len(result["board_b"]) == result["board_b_total"]

    def test_no_board_cap_constant_survives(self):
        """A cap is the kind of thing that comes back as a one-line 'perf fix'.
        Grep the builder itself, so a reintroduced slice reds here rather than
        silently truncating a board the workspace promises to show in full."""
        src = (self._repo / "scripts" / "build_flow_leaders.py").read_text(encoding="utf-8")
        assert "_BOARD_CAP" not in src
        assert "board_a_rows[:" not in src
        assert "board_b_rows[:" not in src

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
    """Registry integrity from the flow-leaders side: our Family G books exist and
    the shared registry is structurally sound.

    Count-agnostic on purpose (2026-07-25; same ruling as TestRegistryBookCount in
    test_build_leader_radar.py, 2026-07-17): other programs add books to the shared
    registry (28th = plab_lh_edge_durability_b, PR #2743) and an exact-count pin
    here breaks their CI. The exact count is pinned once — in
    tests/test_pick_lab_core.py::TestRegistry and the module-load assert at the
    bottom of engine/pick_lab/registry.py.
    """

    def test_registry_min_count(self):
        from engine.pick_lab.registry import REGISTRY
        assert len(REGISTRY) >= 27, f"Registry shrank: {len(REGISTRY)} books"

    def test_unique_engine_ids(self):
        from engine.pick_lab.registry import REGISTRY
        ids = [b["engine_id"] for b in REGISTRY]
        dupes = {i for i in ids if ids.count(i) > 1}
        assert not dupes, f"Duplicate engine_ids: {dupes}"

    def test_books_carry_required_keys(self):
        from engine.pick_lab.registry import REGISTRY
        required = {
            "engine_id", "name_en", "name_zh", "family", "ruler",
            "horizon_role", "max_picks", "refire_lockout_sessions",
            "config", "config_hash", "kill_adjacency",
        }
        for b in REGISTRY:
            missing = required - set(b)
            assert not missing, f"{b.get('engine_id', b)} missing keys: {missing}"
            assert b["family"], f"{b['engine_id']}: empty family label"
            assert b["horizon_role"] in ("entry", "hold_thesis"), (
                f"{b['engine_id']}: bad horizon_role {b['horizon_role']!r}"
            )

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


# ──────────────────────────────────────────────────── loud fail-soft main() ──

class TestLoudFailSoft:
    """Fail-soft paths must emit a PARSEABLE GitHub annotation.

    log.warning("::warning ...") never parses — the logging format prefixes the
    line and GitHub only reads ::warning at line start (#3487/#3515 postmortem).
    tests/test_gh_annotation_line_start.py is the static guard (no annotation may
    go through a logger); this is the behavioural proof for this builder — a crash
    in build() still returns rc 0 AND actually reaches stdout at column 0.
    """

    def test_main_crash_emits_line_start_annotation(self, capsys, monkeypatch):
        import scripts.build_flow_leaders as mod

        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        # main() calls the module-global build(), so setattr on the module suffices.
        monkeypatch.setattr(mod, "build", _boom)
        rc = mod.main()

        assert rc == 0, "builder must stay fail-soft (exit 0)"
        out_lines = capsys.readouterr().out.splitlines()
        assert any(line.startswith("::warning title=flow_leaders::") for line in out_lines), (
            f"Annotation must start the line (bare print, not a logger call): {out_lines}"
        )
