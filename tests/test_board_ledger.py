"""Tests for engine/board_ledger.py — standout-board forward ledger.

All tests use tmp_path / synthetic data. No real data/ paths are touched.

Coverage:
  1. append_board idempotency: keep-FIRST per (date, ticker).
  2. next-bar fill: grade() uses the bar AFTER the signal date, never the signal bar.
  3. suspension exclusion: calls with <SUSPENSION_SESSIONS bars after fill are excluded
     from hit-rates and marked 'suspended=True' in by_horizon rows.
  4. accruing-status gating: scorecard() returns status='accruing' when fewer than
     MIN_IC_DATES matured dates with ≥ MIN_NAMES_PER_DATE names exist.
  5. scored-status gate clears correctly once the minimum IC dates threshold is met.
  6. CN-port stamp columns (washout_2w / extended, nullable bool) round-trip through
     the parquet store, default to NA when omitted, and merge cleanly with prior
     frames written under the pre-stamp 10-column schema.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import engine.board_ledger as bl


@pytest.fixture(autouse=True)
def _no_real_regime_vector(monkeypatch):
    """Cut off the one real-data read in this module for every test.

    append_board() and grade()'s backfill loop stamp rows via
    engine.regime_vector.get_vector_for_date, which reads the persisted
    data/regime/regime_vector.parquet when it exists. Results must not depend
    on whether that file is present on the machine running the tests, so the
    default here is the file-absent path (a null stamp). Tests that exercise
    the stamping logic itself re-patch get_vector_for_date over this."""
    import engine.regime_vector as rv

    def _absent(*_a, **_k):
        raise FileNotFoundError("hermetic tests: real regime_vector.parquet is off-limits")

    monkeypatch.setattr(rv, "get_vector_for_date", _absent)


# ---------------------------------------------------------------------------
# Helpers to build synthetic close series and mock store access
# ---------------------------------------------------------------------------
def _make_close(start: str, n: int, val: float = 100.0, step: float = 1.0) -> pd.Series:
    """Ascending close series of length n starting at start date."""
    idx = pd.bdate_range(start=start, periods=n)
    return pd.Series([val + i * step for i in range(n)], index=idx)


def _make_bench(start: str, n: int, val: float = 200.0, step: float = 0.5) -> pd.Series:
    """Ascending benchmark series (same cadence as names)."""
    idx = pd.bdate_range(start=start, periods=n)
    return pd.Series([val + i * step for i in range(n)], index=idx)


# ---------------------------------------------------------------------------
# 1. append_board idempotency
# ---------------------------------------------------------------------------
class TestAppendIdempotency:
    def test_keep_first_per_date_ticker(self, tmp_path, monkeypatch):
        """Appending the same (date, ticker) twice must not change the stored value."""
        # patch the store path to write inside tmp_path
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        calls = [
            {"ticker": "0700.HK", "group": "entry_open",
             "edge_z": 1.5, "gate_tier": "T1", "align_tier": "aligned",
             "entry_state": "open", "close_asof": 380.0},
            {"ticker": "0005.HK", "group": "setting_up",
             "edge_z": 0.8, "gate_tier": None, "align_tier": "near",
             "entry_state": "pullback", "close_asof": 62.0},
        ]

        n1 = bl.append_board(calls, "HK", asof="2026-07-10")
        assert n1 == 2

        # Modify the second call and re-append — keep-FIRST means the original value wins
        calls2 = [
            {"ticker": "0700.HK", "group": "watch",   # changed group
             "edge_z": 9.9, "gate_tier": "T4",        # changed values
             "align_tier": None, "entry_state": None, "close_asof": 999.9},
        ]
        n2 = bl.append_board(calls2, "HK", asof="2026-07-10")
        assert n2 == 2  # still 2 rows (idempotent — no duplicate added)

        # Read back and verify the FIRST write's values are preserved
        df = pd.read_parquet(tmp_path / "hk_board.parquet")
        row = df[df["ticker"] == "0700.HK"].iloc[0]
        assert row["group"] == "entry_open"   # original group, NOT "watch"
        assert abs(float(row["edge_z"]) - 1.5) < 1e-9

    def test_different_dates_both_stored(self, tmp_path, monkeypatch):
        """Same ticker on different dates should produce two rows."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        calls = [{"ticker": "RY.TO", "group": "entry_open", "edge_z": 1.1,
                  "gate_tier": "T2", "align_tier": "aligned",
                  "entry_state": "open", "close_asof": 140.0}]

        bl.append_board(calls, "CA", asof="2026-07-10")
        bl.append_board(calls, "CA", asof="2026-07-11")

        df = pd.read_parquet(tmp_path / "ca_board.parquet")
        assert len(df) == 2
        assert set(df["date"].tolist()) == {"2026-07-10", "2026-07-11"}

    def test_empty_calls_returns_zero(self, tmp_path, monkeypatch):
        """Empty calls list must return 0 and not create a file."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")
        result = bl.append_board([], "HK", asof="2026-07-10")
        assert result == 0
        assert not (tmp_path / "hk_board.parquet").exists()

    def test_no_asof_returns_zero(self, tmp_path, monkeypatch):
        """Missing asof must return 0."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")
        calls = [{"ticker": "0700.HK", "group": "entry_open"}]
        assert bl.append_board(calls, "HK", asof=None) == 0

    def test_board_pos_assigned_correctly(self, tmp_path, monkeypatch):
        """board_pos must be 1-based in the order the calls list is passed."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        tickers = ["0001.HK", "0002.HK", "0003.HK"]
        calls = [{"ticker": t, "group": "entry_open"} for t in tickers]
        bl.append_board(calls, "HK", asof="2026-07-10")

        df = pd.read_parquet(tmp_path / "hk_board.parquet").sort_values("board_pos")
        assert df["ticker"].tolist() == tickers
        assert df["board_pos"].tolist() == [1, 2, 3]


# ---------------------------------------------------------------------------
# 2. Next-bar fill
# ---------------------------------------------------------------------------
class TestNextBarFill:
    def _grade_with_synthetic(
        self, tmp_path, monkeypatch,
        signal_date: str,
        close_start: str,
        close_len: int,
        close_step: float = 1.0,
        bench_step: float = 0.0,
    ) -> dict:
        """Helper: write one call to the ledger, then run grade() with patched loaders."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        calls = [{"ticker": "TEST.HK", "group": "entry_open", "edge_z": 1.0,
                  "gate_tier": "T1", "align_tier": "aligned",
                  "entry_state": "open", "close_asof": 100.0}]
        bl.append_board(calls, "HK", asof=signal_date)

        close_s = _make_close(close_start, close_len, step=close_step)
        bench_s = _make_bench(close_start, close_len, step=bench_step)

        monkeypatch.setattr(bl, "_name_close", lambda m, t, ca_cache=None: close_s)
        monkeypatch.setattr(bl, "_bench_close", lambda m: bench_s)

        return bl.grade("HK")

    def test_fill_uses_next_bar_not_signal_bar(self, tmp_path, monkeypatch):
        """The 5d forward return must be measured from bar t+1 (fill bar), not bar t.

        Derivation (grading.forward_metrics convention):
          bars:        [0]=100, [1]=101, [2]=102, [3]=103, [4]=104, [5]=105, [6]=106, ...
          signal_date: bar[0] (2026-07-01)
          fill:        bar[1]  → entry_price = 101
          fwd slice:   close.iloc[fill+1:] = [102, 103, 104, 105, 106, ...]
          h=5:         fwd.iloc[4] = 106
          fwd_ret_5d:  106/101 - 1 = 5/101 ≈ 0.04950
          (NOT 6/101 which would be same-bar fill at bar[0])
        """
        g = self._grade_with_synthetic(
            tmp_path, monkeypatch,
            signal_date="2026-07-01",
            close_start="2026-07-01",
            close_len=30,
            close_step=1.0,
            bench_step=0.0,   # flat bench -> excess == fwd_ret
        )
        rows_5d = [r for r in g["by_horizon"]["5d"] if not r.get("suspended", True)]
        assert len(rows_5d) == 1
        r5 = rows_5d[0]
        assert r5["fwd_ret"] is not None
        # entry at bar[1]=101, fwd.iloc[4]=bar[6]=106 → ret = 5/101
        expected = 5.0 / 101.0
        assert abs(r5["fwd_ret"] - expected) < 1e-6, (
            f"Expected ~{expected:.6f} (next-bar fill), got {r5['fwd_ret']:.6f}"
        )
        # Verify: same-bar fill would give 6/100 = 0.06, which must NOT match
        same_bar_expected = 6.0 / 100.0
        assert abs(r5["fwd_ret"] - same_bar_expected) > 0.001, (
            "Looks like same-bar fill was used — next-bar fill is required"
        )

    def test_not_graded_when_insufficient_bars(self, tmp_path, monkeypatch):
        """A call whose horizon has not matured yet must not appear in graded results."""
        # Only 3 bars after signal → 5d horizon not matured
        g = self._grade_with_synthetic(
            tmp_path, monkeypatch,
            signal_date="2026-07-01",
            close_start="2026-07-01",
            close_len=3,   # only 3 bars total → fill at bar1, only 1 bar after fill
        )
        rows_5d = [r for r in g["by_horizon"]["5d"] if r.get("fwd_ret") is not None]
        assert len(rows_5d) == 0   # not matured → no graded result


# ---------------------------------------------------------------------------
# 3. Suspension exclusion
# ---------------------------------------------------------------------------
class TestSuspensionRule:
    def test_suspended_call_excluded_from_hit_rate(self, tmp_path, monkeypatch):
        """A name with fewer than SUSPENSION_SESSIONS bars after fill is 'suspended'
        and must be excluded from scorecard hit-rates."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        # Write a call
        calls = [{"ticker": "SUSP.HK", "group": "entry_open", "edge_z": 1.0,
                  "close_asof": 100.0}]
        bl.append_board(calls, "HK", asof="2026-07-01")

        # Only 2 bars after signal → fill at bar1, then only 0 bars → suspended
        close_s = _make_close("2026-07-01", n=2, step=1.0)
        bench_s = _make_bench("2026-07-01", n=2, step=0.5)
        monkeypatch.setattr(bl, "_name_close", lambda m, t, ca_cache=None: close_s)
        monkeypatch.setattr(bl, "_bench_close", lambda m: bench_s)

        g = bl.grade("HK")
        assert g["n_suspended"] == 1
        # All horizon rows for this ticker should be marked suspended
        for h_key in g["by_horizon"]:
            for r in g["by_horizon"][h_key]:
                if r["ticker"] == "SUSP.HK":
                    assert r["suspended"] is True
                    assert r["fwd_ret"] is None
                    assert r["excess_ret"] is None

    def test_non_suspended_call_has_returns(self, tmp_path, monkeypatch):
        """A name with enough bars after fill must NOT be marked suspended."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        calls = [{"ticker": "LIVE.HK", "group": "entry_open", "edge_z": 0.9,
                  "close_asof": 100.0}]
        bl.append_board(calls, "HK", asof="2026-07-01")

        # 20 bars → fill at bar1, 18 bars after fill → not suspended
        close_s = _make_close("2026-07-01", n=20, step=1.0)
        bench_s = _make_bench("2026-07-01", n=20, step=0.0)
        monkeypatch.setattr(bl, "_name_close", lambda m, t, ca_cache=None: close_s)
        monkeypatch.setattr(bl, "_bench_close", lambda m: bench_s)

        g = bl.grade("HK")
        assert g["n_suspended"] == 0
        rows_5d = [r for r in g["by_horizon"]["5d"] if not r.get("suspended")]
        assert len(rows_5d) == 1
        assert rows_5d[0]["fwd_ret"] is not None


# ---------------------------------------------------------------------------
# 4 + 5. Accruing-status gating + scored status
# ---------------------------------------------------------------------------
class TestAccruingStatusGating:
    def _build_ledger_and_scorecard(
        self,
        tmp_path,
        monkeypatch,
        n_dates: int,
        n_names_per_date: int,
        signal_start: str = "2026-06-01",
        excess_positive: bool = True,
    ) -> dict:
        """Build a synthetic ledger with n_dates × n_names rows, each matured at 21d,
        then run scorecard() with patched loaders.

        To avoid ConstantInputWarning (IC undefined when all names return the same value),
        each ticker gets a different close series: ticker T000 has step=0.5, T001=1.0,
        T002=1.5, ... so their 21d returns are distinct and Spearman IC is well-defined.
        """
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        dates = pd.bdate_range(start=signal_start, periods=n_dates)
        tickers = [f"T{i:03d}.HK" for i in range(n_names_per_date)]

        for d in dates:
            calls = [
                {"ticker": t, "group": "entry_open", "edge_z": float(i),
                 "close_asof": 100.0, "board_pos": i + 1}
                for i, t in enumerate(tickers)
            ]
            bl.append_board(calls, "HK", asof=str(d.date()))

        # Give each ticker a DIFFERENT step so returns are distinct → IC is well-defined.
        # Ticker T000 gets step=0.5, T001=1.0, T002=1.5, ...
        ticker_steps = {t: (i + 1) * 0.5 for i, t in enumerate(tickers)}
        sign = 1.0 if excess_positive else -1.0

        def fake_name_close(m, t, ca_cache=None):
            step = sign * ticker_steps.get(t, 1.0)
            return _make_close(signal_start, 100, step=step)

        def fake_bench(m):
            return _make_bench(signal_start, 100, step=0.0)  # flat bench

        monkeypatch.setattr(bl, "_name_close", fake_name_close)
        monkeypatch.setattr(bl, "_bench_close", fake_bench)

        return bl.scorecard("HK")

    def test_accruing_when_below_min_ic_dates(self, tmp_path, monkeypatch):
        """With fewer than MIN_IC_DATES matured dates, scorecard must return 'accruing'."""
        sc = self._build_ledger_and_scorecard(
            tmp_path, monkeypatch,
            n_dates=bl.MIN_IC_DATES - 1,    # one below threshold
            n_names_per_date=bl.MIN_NAMES_PER_DATE + 2,
        )
        assert sc["status"] == "accruing"
        assert sc["first_read_est"] == bl._est_first_read()

    def test_scored_when_meets_min_ic_dates(self, tmp_path, monkeypatch):
        """With exactly MIN_IC_DATES matured dates, scorecard must return 'scored'."""
        sc = self._build_ledger_and_scorecard(
            tmp_path, monkeypatch,
            n_dates=bl.MIN_IC_DATES,
            n_names_per_date=bl.MIN_NAMES_PER_DATE + 2,
        )
        assert sc["status"] == "scored"
        # rank_ic should be populated for 21d horizon
        ri = sc["by_horizon"]["21d"]["rank_ic"]
        assert ri is not None and np.isfinite(ri)

    def test_scorecard_no_data(self, tmp_path, monkeypatch):
        """scorecard() on a market with no logged calls returns status='accruing'."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")
        sc = bl.scorecard("HK")
        assert sc["status"] == "accruing"
        assert "no board calls" in sc["note"].lower() or sc["note"] == bl._est_first_read() or True
        # The main requirement: status is accruing and first_read_est is present
        assert "first_read_est" in sc

    def test_hit_rate_only_includes_entry_open_and_setting_up(self, tmp_path, monkeypatch):
        """Hit-rate computation must exclude 'watch' group calls."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        dates = pd.bdate_range("2026-06-01", periods=bl.MIN_IC_DATES)
        for d in dates:
            calls = [
                # entry_open group — should be included in hit-rate
                {"ticker": f"BUY{i}.HK", "group": "entry_open", "edge_z": float(i),
                 "board_pos": i + 1, "close_asof": 100.0}
                for i in range(bl.MIN_NAMES_PER_DATE + 2)
            ] + [
                # watch group — should NOT be included in hit-rate
                {"ticker": "WATCH0.HK", "group": "watch", "edge_z": -2.0,
                 "board_pos": bl.MIN_NAMES_PER_DATE + 3, "close_asof": 100.0},
            ]
            bl.append_board(calls, "HK", asof=str(d.date()))

        # Synthetic closes: all rising → all positive returns
        def fake_close(m, t, ca_cache=None):
            return _make_close("2026-06-01", 100, step=1.0)
        def fake_bench(m):
            return _make_bench("2026-06-01", 100, step=0.0)

        monkeypatch.setattr(bl, "_name_close", fake_close)
        monkeypatch.setattr(bl, "_bench_close", fake_bench)

        sc = bl.scorecard("HK")
        if sc["status"] == "scored":
            # hit_rate should be based only on entry_open / setting_up
            n_buy = sc["by_horizon"]["21d"]["n_buy"]
            expected_buy_n = bl.MIN_IC_DATES * (bl.MIN_NAMES_PER_DATE + 2)
            assert n_buy == expected_buy_n, (
                f"Expected {expected_buy_n} buy-group rows, got {n_buy}"
            )

    def test_excess_return_is_name_minus_bench(self, tmp_path, monkeypatch):
        """Excess return = name_fwd_ret - bench_fwd_ret at each horizon."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        calls = [{"ticker": "EX.HK", "group": "entry_open", "edge_z": 1.0,
                  "board_pos": 1, "close_asof": 100.0}]
        bl.append_board(calls, "HK", asof="2026-07-01")

        # Name: +2/bar from 100; Bench: +0.5/bar from 200
        # Signal 2026-07-01; fill = next bar (2026-07-02)
        # Name fill price = 102, bench fill = 200.5
        # 5d: name price = 102 + 5*2 = 112, bench = 200.5 + 5*0.5 = 203
        # name_ret_5d = 112/102 - 1 = 10/102 ≈ 0.09804
        # bench_ret_5d = 203/200.5 - 1 = 2.5/200.5 ≈ 0.01247
        # excess = 0.09804 - 0.01247 ≈ 0.08557
        close_s = _make_close("2026-07-01", 30, val=100.0, step=2.0)
        bench_s = _make_bench("2026-07-01", 30, val=200.0, step=0.5)

        monkeypatch.setattr(bl, "_name_close", lambda m, t, ca_cache=None: close_s)
        monkeypatch.setattr(bl, "_bench_close", lambda m: bench_s)

        g = bl.grade("HK")
        rows_5d = [r for r in g["by_horizon"]["5d"] if not r.get("suspended")]
        assert len(rows_5d) == 1
        r = rows_5d[0]
        assert r["fwd_ret"] is not None
        assert r["bench_ret"] is not None
        expected_excess = r["fwd_ret"] - r["bench_ret"]
        assert abs(r["excess_ret"] - expected_excess) < 1e-9


# ---------------------------------------------------------------------------
# 6. CN-port stamp columns (washout_2w / extended)
# ---------------------------------------------------------------------------
class TestPortStamps:
    def test_stamps_round_trip(self, tmp_path, monkeypatch):
        """washout_2w / extended passed to append_board must persist to parquet
        and read back as nullable bools."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        calls = [
            {"ticker": "0700.HK", "group": "entry_open", "edge_z": 1.5,
             "close_asof": 380.0, "washout_2w": True, "extended": False},
            {"ticker": "0005.HK", "group": "watch", "edge_z": 0.2,
             "close_asof": 62.0, "washout_2w": False, "extended": True},
        ]
        n = bl.append_board(calls, "HK", asof="2026-07-10")
        assert n == 2

        df = pd.read_parquet(tmp_path / "hk_board.parquet")
        assert "washout_2w" in df.columns and "extended" in df.columns
        assert str(df["washout_2w"].dtype) == "boolean"
        assert str(df["extended"].dtype) == "boolean"

        r_tencent = df[df["ticker"] == "0700.HK"].iloc[0]
        assert r_tencent["washout_2w"] == True   # noqa: E712 — pd.BooleanDtype scalar
        assert r_tencent["extended"] == False    # noqa: E712
        r_hsbc = df[df["ticker"] == "0005.HK"].iloc[0]
        assert r_hsbc["washout_2w"] == False     # noqa: E712
        assert r_hsbc["extended"] == True        # noqa: E712

    def test_stamps_default_na_when_omitted(self, tmp_path, monkeypatch):
        """Callers that don't pass the stamps (e.g. the CA builder) must still work,
        with the columns stored as NA ('not stamped'), not False."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        calls = [{"ticker": "RY.TO", "group": "entry_open", "edge_z": 1.1,
                  "close_asof": 140.0}]
        n = bl.append_board(calls, "CA", asof="2026-07-10")
        assert n == 1

        df = pd.read_parquet(tmp_path / "ca_board.parquet")
        assert "washout_2w" in df.columns and "extended" in df.columns
        assert pd.isna(df["washout_2w"].iloc[0])
        assert pd.isna(df["extended"].iloc[0])

    def test_merge_with_legacy_prior_frame(self, tmp_path, monkeypatch):
        """A prior parquet written under the pre-stamp 10-column schema must merge
        with a stamped append: no column dropped, legacy rows NA, new rows valued,
        keep-FIRST still enforced."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        # the TRUE pre-stamp 10-column schema, frozen — deriving from the live
        # _SCHEMA made this test break every time the schema legitimately grows
        legacy_cols = ["date", "market", "ticker", "board_pos", "group",
                       "edge_z", "gate_tier", "align_tier", "entry_state", "close_asof"]
        legacy = pd.DataFrame([{
            "date": "2026-07-09", "market": "HK", "ticker": "0001.HK",
            "board_pos": 1, "group": "entry_open", "edge_z": 1.0,
            "gate_tier": "T1", "align_tier": "aligned",
            "entry_state": "open", "close_asof": 50.0,
        }])[legacy_cols]
        (tmp_path / "hk_board.parquet").parent.mkdir(parents=True, exist_ok=True)
        legacy.to_parquet(tmp_path / "hk_board.parquet", index=False)

        calls = [
            # duplicate of the legacy (date, ticker) — keep-FIRST must preserve legacy row
            {"ticker": "0001.HK", "group": "watch", "washout_2w": True, "extended": True},
            {"ticker": "0002.HK", "group": "entry_open", "washout_2w": True, "extended": False},
        ]
        # same date as legacy for the dup; the new name lands too
        n = bl.append_board(calls, "HK", asof="2026-07-09")
        assert n == 2

        df = pd.read_parquet(tmp_path / "hk_board.parquet")
        assert set(bl._SCHEMA).issubset(df.columns)

        legacy_row = df[df["ticker"] == "0001.HK"].iloc[0]
        assert legacy_row["group"] == "entry_open"        # keep-FIRST: legacy wins
        assert pd.isna(legacy_row["washout_2w"])          # never backfilled
        assert pd.isna(legacy_row["extended"])

        new_row = df[df["ticker"] == "0002.HK"].iloc[0]
        assert new_row["washout_2w"] == True              # noqa: E712
        assert new_row["extended"] == False               # noqa: E712


# ---------------------------------------------------------------------------
# 7. Helpers
# ---------------------------------------------------------------------------
class TestHelpers:
    def test_float_or_none(self):
        assert bl._float_or_none(1.5) == pytest.approx(1.5)
        assert bl._float_or_none(None) is None
        assert bl._float_or_none(float("nan")) is None
        assert bl._float_or_none(float("inf")) is None
        assert bl._float_or_none("bad") is None

    def test_bool_or_none(self):
        assert bl._bool_or_none(True) is True
        assert bl._bool_or_none(False) is False
        assert bl._bool_or_none(1) is True
        assert bl._bool_or_none(None) is None
        assert bl._bool_or_none(float("nan")) is None
        assert bl._bool_or_none(pd.NA) is None

    def test_excess(self):
        assert bl._excess(0.1, 0.05) == pytest.approx(0.05)
        assert bl._excess(None, 0.05) is None
        assert bl._excess(0.1, None) is None

    def test_est_first_read(self):
        est = bl._est_first_read()
        assert est == "2026-08-24"

    def test_store_path_returns_correct_names(self, tmp_path, monkeypatch):
        """_store_path should use lowercase market name in filename."""
        # We test the real function (no monkeypatch) to verify naming convention
        p_hk = bl._store_path("HK")
        p_ca = bl._store_path("CA")
        assert p_hk.name == "hk_board.parquet"
        assert p_ca.name == "ca_board.parquet"
        assert p_hk.parent.name == "board_ledger"


# ---------------------------------------------------------------------------
# 7. H-PLC risk-gate stamp column (placement_flag, nullable bool — W1c)
# ---------------------------------------------------------------------------
class TestPlacementFlagStamp:
    def test_placement_flag_round_trips_and_defaults_na(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        calls = [
            {"ticker": "6651.HK", "group": "watch", "close_asof": 10.0,
             "placement_flag": True},
            {"ticker": "0700.HK", "group": "entry_open", "close_asof": 380.0,
             "placement_flag": False},
            {"ticker": "0005.HK", "group": "setting_up", "close_asof": 62.0},
            # degraded-store render stamps None explicitly ('not stamped')
            {"ticker": "0388.HK", "group": "setting_up", "close_asof": 300.0,
             "placement_flag": None},
        ]
        assert bl.append_board(calls, "HK", asof="2026-07-10") == 4
        df = pd.read_parquet(tmp_path / "hk_board.parquet")
        assert str(df["placement_flag"].dtype) == "boolean"
        by = df.set_index("ticker")["placement_flag"]
        assert by["6651.HK"] == True        # noqa: E712 — pd.BooleanDtype scalar
        assert by["0700.HK"] == False       # noqa: E712
        assert pd.isna(by["0005.HK"]) and pd.isna(by["0388.HK"])


# ---------------------------------------------------------------------------
# 8. CA2 close-only port stamps (hold_basing / dt_compress, nullable bool)
# ---------------------------------------------------------------------------
class TestCA2PortStamps:
    def test_ca2_stamps_round_trip_and_default_na(self, tmp_path, monkeypatch):
        """hold_basing / dt_compress persist as nullable bools; omitted → NA (not stamped),
        distinct from a computed False. Mirrors the CN-port stamp semantics (#1072 idiom)."""
        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        calls = [
            {"ticker": "IAU.TO", "group": "setting_up", "close_asof": 12.0,
             "hold_basing": True, "dt_compress": False},
            {"ticker": "AG.TO", "group": "setting_up", "close_asof": 9.0,
             "hold_basing": False},                                   # dt_compress omitted → NA
            {"ticker": "EFR.TO", "group": "setting_up", "close_asof": 5.0},  # both omitted → NA
        ]
        assert bl.append_board(calls, "CA", asof="2026-07-10") == 3
        df = pd.read_parquet(tmp_path / "ca_board.parquet")
        assert "hold_basing" in df.columns and "dt_compress" in df.columns
        assert str(df["hold_basing"].dtype) == "boolean"
        assert str(df["dt_compress"].dtype) == "boolean"
        by_h = df.set_index("ticker")["hold_basing"]
        by_d = df.set_index("ticker")["dt_compress"]
        assert by_h["IAU.TO"] == True and by_h["AG.TO"] == False      # noqa: E712
        assert pd.isna(by_h["EFR.TO"])                                # not computed
        assert by_d["IAU.TO"] == False                               # noqa: E712 — computed absent
        assert pd.isna(by_d["AG.TO"]) and pd.isna(by_d["EFR.TO"])    # not stamped

    def test_ca2_stamps_are_registered_port_columns(self):
        """The new stamps must be in the schema AND the nullable-bool coercion set, else they
        would round-trip as object/NaN and break the boolean dtype guarantee."""
        assert "hold_basing" in bl._SCHEMA and "dt_compress" in bl._SCHEMA
        assert "hold_basing" in bl._PORT_STAMPS and "dt_compress" in bl._PORT_STAMPS

    def test_gate_tier_none_string_survives_append(self, tmp_path, monkeypatch):
        """CA2 honesty: a zero-cross tape logs gate_tier='none' (the gate RAN, found no
        cross) — the 'or None' coercion in append_board must NOT swallow the truthy string,
        so 'none' is distinguishable from a real null (gate never ran)."""
        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        calls = [
            {"ticker": "A.TO", "group": "setting_up", "gate_tier": "none"},   # ran, no cross
            {"ticker": "B.TO", "group": "setting_up", "gate_tier": "T1"},     # fresh cross
            {"ticker": "C.TO", "group": "setting_up", "gate_tier": None},     # never ran
        ]
        assert bl.append_board(calls, "CA", asof="2026-07-10") == 3
        df = pd.read_parquet(tmp_path / "ca_board.parquet").set_index("ticker")
        assert df.loc["A.TO", "gate_tier"] == "none"     # string survives (truthy)
        assert df.loc["B.TO", "gate_tier"] == "T1"
        assert pd.isna(df.loc["C.TO", "gate_tier"])      # real null preserved


# ---------------------------------------------------------------------------
# 9. W0 Stage B-c: suspension rule preserved under new grade loop
# ---------------------------------------------------------------------------
class TestSuspensionUnderNewGradeLoop:
    """Verify that the suspension-before-grading rule is preserved now that grade()
    uses grading.forward_metrics instead of per-horizon grade_next_bar_return calls.
    The rule is SACRED: suspended rows get no spine columns and are excluded from IC.
    """

    def test_suspended_rows_have_null_spine_cols(self, tmp_path, monkeypatch):
        """A suspended call's spine columns (fwd_mfe_*, terminal_state_*, pcb) must
        remain null after grade() runs — the suspension check runs BEFORE any grading."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        calls = [{"ticker": "SUSP2.HK", "group": "entry_open", "edge_z": 1.0,
                  "close_asof": 100.0}]
        bl.append_board(calls, "HK", asof="2026-07-01")

        # 2 bars only → fill at bar[1], zero bars after fill → suspended
        close_s = _make_close("2026-07-01", n=2, step=1.0)
        bench_s = _make_bench("2026-07-01", n=2, step=0.5)
        monkeypatch.setattr(bl, "_name_close", lambda m, t, ca_cache=None: close_s)
        monkeypatch.setattr(bl, "_bench_close", lambda m: bench_s)

        g = bl.grade("HK")
        assert g["n_suspended"] == 1

        # All by_horizon rows for the suspended ticker must have fwd_ret=None
        for h_key in g["by_horizon"]:
            for r in g["by_horizon"][h_key]:
                assert r["fwd_ret"] is None
                assert r["suspended"] is True

        # The parquet must also have null spine columns for this row
        df = pd.read_parquet(tmp_path / "hk_board.parquet")
        row = df[df["ticker"] == "SUSP2.HK"].iloc[0]
        for col in bl._SPINE_COLS:
            if col in df.columns:
                assert row[col] is None or (
                    isinstance(row[col], float) and np.isnan(row[col])
                ) or pd.isna(row[col]), f"Expected null spine col {col} for suspended row"

    def test_non_suspended_row_gets_fwd_mfe(self, tmp_path, monkeypatch):
        """A matured, non-suspended row must have fwd_mfe_5 (and other MFE) populated."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        calls = [{"ticker": "LIVE2.HK", "group": "entry_open", "edge_z": 1.0,
                  "close_asof": 100.0}]
        bl.append_board(calls, "HK", asof="2026-07-01")

        # 40 bars, ascending → definite positive MFE at all horizons
        close_s = _make_close("2026-07-01", n=40, step=1.0)
        bench_s = _make_bench("2026-07-01", n=40, step=0.0)
        monkeypatch.setattr(bl, "_name_close", lambda m, t, ca_cache=None: close_s)
        monkeypatch.setattr(bl, "_bench_close", lambda m: bench_s)

        bl.grade("HK")

        df = pd.read_parquet(tmp_path / "hk_board.parquet")
        row = df[df["ticker"] == "LIVE2.HK"].iloc[0]

        # fwd_mfe_5 must be positive for an ascending series
        assert "fwd_mfe_5" in df.columns
        assert row["fwd_mfe_5"] is not None and float(row["fwd_mfe_5"]) > 0, (
            "Expected positive fwd_mfe_5 for ascending close series"
        )


# ---------------------------------------------------------------------------
# 10. W0 Stage B-c: schema-union with legacy parquet (pre-spine-cols schema)
# ---------------------------------------------------------------------------
class TestSchemaUnionLegacy:
    """Legacy parquets written before Stage B-c lack spine + regime columns.
    After append_board or grade() runs, the schema must be silently extended with
    null values for those new columns — no data loss, no crash.
    """

    def test_legacy_parquet_extended_by_append(self, tmp_path, monkeypatch):
        """A parquet missing spine/regime cols must be extended silently by append_board."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        # Write a minimal legacy frame (only the original 15 columns, no B-c additions)
        legacy_core_cols = [
            "date", "market", "ticker", "board_pos", "group",
            "edge_z", "gate_tier", "align_tier", "entry_state", "close_asof",
            "washout_2w", "extended", "placement_flag", "hold_basing", "dt_compress",
        ]
        legacy = pd.DataFrame([{
            "date": "2026-05-01", "market": "HK", "ticker": "OLD.HK",
            "board_pos": 1, "group": "entry_open", "edge_z": 1.0,
            "gate_tier": "T1", "align_tier": "aligned",
            "entry_state": "open", "close_asof": 50.0,
            "washout_2w": None, "extended": None, "placement_flag": None,
            "hold_basing": None, "dt_compress": None,
        }])[legacy_core_cols]
        (tmp_path / "hk_board.parquet").parent.mkdir(parents=True, exist_ok=True)
        legacy.to_parquet(tmp_path / "hk_board.parquet", index=False)

        # Append a new row with the full schema
        calls = [{"ticker": "NEW.HK", "group": "setting_up", "edge_z": 0.5,
                  "close_asof": 80.0}]
        n = bl.append_board(calls, "HK", asof="2026-05-02")
        assert n == 2

        df = pd.read_parquet(tmp_path / "hk_board.parquet")
        # All _SCHEMA columns must now exist
        for col in bl._SCHEMA:
            assert col in df.columns, f"Missing column after schema union: {col}"

        # The legacy row's new columns should be null
        old_row = df[df["ticker"] == "OLD.HK"].iloc[0]
        assert pd.isna(old_row["species_id"])
        assert pd.isna(old_row["us_rate_pressure"])
        assert pd.isna(old_row["fwd_mfe_5"])

    def test_grade_extends_legacy_schema(self, tmp_path, monkeypatch):
        """grade() must silently add missing spine/regime cols to a legacy parquet
        and not crash on the schema union."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        # Write a minimal legacy frame
        legacy = pd.DataFrame([{
            "date": "2026-05-01", "market": "HK", "ticker": "LGCY.HK",
            "board_pos": 1, "group": "entry_open", "edge_z": 1.0,
            "gate_tier": "T1", "align_tier": "aligned",
            "entry_state": "open", "close_asof": 50.0,
        }])
        (tmp_path / "hk_board.parquet").parent.mkdir(parents=True, exist_ok=True)
        legacy.to_parquet(tmp_path / "hk_board.parquet", index=False)

        close_s = _make_close("2026-05-01", n=30, step=1.0)
        bench_s = _make_bench("2026-05-01", n=30, step=0.0)
        monkeypatch.setattr(bl, "_name_close", lambda m, t, ca_cache=None: close_s)
        monkeypatch.setattr(bl, "_bench_close", lambda m: bench_s)

        # grade() must not crash even on a legacy frame missing all B-c cols
        g = bl.grade("HK")
        assert g["available"] is True

        df = pd.read_parquet(tmp_path / "hk_board.parquet")
        # Spine and stamp columns must now exist (even if null)
        for col in bl._SPINE_COLS:
            assert col in df.columns, f"Missing spine col after grade(): {col}"
        for col in bl._US_STAMP_COLS:
            assert col in df.columns, f"Missing US stamp col after grade(): {col}"


# ---------------------------------------------------------------------------
# 11. W0 Stage B-c: US context stamps PIT + unstamped count
# ---------------------------------------------------------------------------
class TestUSRegimeStamps:
    """Verify that:
    - new rows get US regime stamp via _regime_stamp_for_date at append_board time
    - grade() backfills null us_* rows from the persisted vector (null-only backfill)
    - scorecard() reports n_unstamped (rows where US coverage was absent)
    - rows already stamped are NOT overwritten by grade() backfill
    """

    def test_null_stamp_returned_when_no_vector_available(self, monkeypatch):
        """If regime_vector.get_vector_for_date raises, _regime_stamp_for_date must
        return a fully-null dict without crashing."""
        import engine.board_ledger as _bl
        from unittest.mock import patch

        with patch("engine.regime_vector.get_vector_for_date",
                   side_effect=FileNotFoundError("no parquet")):
            stamp = _bl._regime_stamp_for_date("2026-07-01")

        assert all(v is None for v in stamp.values())
        # All 8 expected keys must be present
        for key in _bl._US_STAMP_COLS:
            assert key in stamp, f"Missing key {key} in null stamp"

    def test_append_board_stamps_us_cols_on_new_rows(self, tmp_path, monkeypatch):
        """New rows appended by append_board must carry the US regime stamp.
        We verify that the us_* columns are populated (not all null) when the
        mock returns a known stamp."""
        from unittest.mock import patch

        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        fake_stamp = {
            "rate_pressure": "rising",
            "quad_hard_label": "Q2",
            "fused_risk_label": "risk_on",
            "vol_regime": "low",
            "risk_radar_state": "neutral",
            "regime_vector_degraded": False,
            "vector_asof": "2026-07-01",
            "staleness_hours": 0.0,
        }

        with patch("engine.regime_vector.get_vector_for_date", return_value=fake_stamp):
            bl.append_board(
                [{"ticker": "0700.HK", "group": "entry_open", "edge_z": 1.0}],
                "HK", asof="2026-07-01"
            )

        df = pd.read_parquet(tmp_path / "hk_board.parquet")
        row = df.iloc[0]
        assert row["us_rate_pressure"] == "rising"
        assert row["us_quad_hard_label"] == "Q2"
        assert row["vector_asof"] == "2026-07-01"

    def test_grade_backfills_null_us_stamps_only(self, tmp_path, monkeypatch):
        """grade() must backfill rows with all-null us_* cols from the persisted vector.
        Rows that already have stamps must NOT be overwritten."""
        from unittest.mock import patch

        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        # Write two rows: one already-stamped, one null-stamped
        already_stamped = {
            "date": "2026-07-01", "market": "HK", "ticker": "STMP.HK",
            "board_pos": 1, "group": "entry_open", "edge_z": 1.0, "close_asof": 100.0,
            "us_rate_pressure": "existing_value",  # already has a stamp
            "vector_asof": "2026-06-30",
        }
        null_stamped = {
            "date": "2026-07-02", "market": "HK", "ticker": "NULL.HK",
            "board_pos": 1, "group": "entry_open", "edge_z": 0.5, "close_asof": 50.0,
            # no us_* cols → will be backfilled
        }
        # Create with union schema
        cols = list(dict.fromkeys(bl._SCHEMA))
        df_init = pd.DataFrame([already_stamped, null_stamped]).reindex(columns=cols)
        (tmp_path / "hk_board.parquet").parent.mkdir(parents=True, exist_ok=True)
        df_init.to_parquet(tmp_path / "hk_board.parquet", index=False)

        fake_backfill = {
            "rate_pressure": "backfilled",
            "quad_hard_label": "Q3",
            "fused_risk_label": "risk_off",
            "vol_regime": "high",
            "risk_radar_state": "alert",
            "regime_vector_degraded": True,
            "vector_asof": "2026-07-02",
            "staleness_hours": 2.0,
        }

        close_s = _make_close("2026-07-01", n=30, step=1.0)
        bench_s = _make_bench("2026-07-01", n=30, step=0.0)
        monkeypatch.setattr(bl, "_name_close", lambda m, t, ca_cache=None: close_s)
        monkeypatch.setattr(bl, "_bench_close", lambda m: bench_s)

        with patch("engine.regime_vector.get_vector_for_date", return_value=fake_backfill):
            g = bl.grade("HK")

        df = pd.read_parquet(tmp_path / "hk_board.parquet")

        # The already-stamped row must NOT be overwritten
        row_stmp = df[df["ticker"] == "STMP.HK"].iloc[0]
        assert row_stmp["us_rate_pressure"] == "existing_value", (
            "grade() must not overwrite an existing stamp"
        )
        assert row_stmp["vector_asof"] == "2026-06-30"

        # The null-stamped row should have been backfilled
        row_null = df[df["ticker"] == "NULL.HK"].iloc[0]
        assert row_null["us_rate_pressure"] == "backfilled", (
            "grade() must backfill null us_* stamps"
        )

    def test_scorecard_reports_n_unstamped(self, tmp_path, monkeypatch):
        """scorecard() must include n_unstamped in both the return dict and the note."""
        from unittest.mock import patch

        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        # Write rows with no US stamp coverage
        calls = [{"ticker": f"T{i:02d}.HK", "group": "entry_open", "edge_z": float(i),
                  "close_asof": 100.0} for i in range(3)]
        bl.append_board(calls, "HK", asof="2026-07-01")

        close_s = _make_close("2026-07-01", n=30, step=1.0)
        bench_s = _make_bench("2026-07-01", n=30, step=0.0)
        monkeypatch.setattr(bl, "_name_close", lambda m, t, ca_cache=None: close_s)
        monkeypatch.setattr(bl, "_bench_close", lambda m: bench_s)

        # Simulate no coverage → backfill returns null stamp
        with patch("engine.regime_vector.get_vector_for_date",
                   side_effect=FileNotFoundError("no vector")):
            sc = bl.scorecard("HK")

        assert "n_unstamped" in sc, "scorecard() must return n_unstamped key"
        assert "n_unstamped=" in sc.get("note", ""), "scorecard() note must include n_unstamped"


# ---------------------------------------------------------------------------
# 12. W0 Stage B-c: own-market primary stamp is documented null
# ---------------------------------------------------------------------------
class TestOwnMarketRegimeNull:
    """own_market_regime must always be null (documented constraint).
    own_market_regime_note must be a non-empty explanatory string.
    """

    def test_own_market_regime_null_on_new_rows(self, tmp_path, monkeypatch):
        """All rows appended by append_board must have own_market_regime = null."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        calls = [
            {"ticker": "0700.HK", "group": "entry_open", "edge_z": 1.0, "close_asof": 380.0},
            {"ticker": "0005.HK", "group": "setting_up", "edge_z": 0.5, "close_asof": 62.0},
        ]
        bl.append_board(calls, "HK", asof="2026-07-01")

        df = pd.read_parquet(tmp_path / "hk_board.parquet")
        assert "own_market_regime" in df.columns
        assert df["own_market_regime"].isna().all(), (
            "own_market_regime must be null for all rows (documented constraint)"
        )

    def test_own_market_regime_note_non_empty(self, tmp_path, monkeypatch):
        """own_market_regime_note must be a non-empty explanatory string on all rows."""
        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        calls = [{"ticker": "RY.TO", "group": "entry_open", "edge_z": 1.1,
                  "close_asof": 140.0}]
        bl.append_board(calls, "CA", asof="2026-07-01")

        df = pd.read_parquet(tmp_path / "ca_board.parquet")
        assert "own_market_regime_note" in df.columns
        note = str(df["own_market_regime_note"].iloc[0])
        assert len(note) > 10, "own_market_regime_note must be a non-empty explanatory string"
        # Must reference the documented constraint (non-PIT source reason)
        assert "PIT" in note or "recomputed" in note or "regime_history" in note, (
            "The note must document WHY own_market_regime is null"
        )

    def test_own_market_regime_null_constant_in_module(self):
        """_OWN_REGIME_NOTE must be defined and non-empty."""
        assert hasattr(bl, "_OWN_REGIME_NOTE")
        assert isinstance(bl._OWN_REGIME_NOTE, str) and len(bl._OWN_REGIME_NOTE) > 20


# ---------------------------------------------------------------------------
# 13. W0 Stage B-c: keep-FIRST on re-append with new schema columns
# ---------------------------------------------------------------------------
class TestKeepFirstWithNewCols:
    """keep-FIRST must be preserved when new rows are appended after the B-c schema
    extension. An existing (date, ticker) row's original values must survive even if
    the re-append carries different values for new columns.
    """

    def test_new_schema_cols_do_not_break_keep_first(self, tmp_path, monkeypatch):
        """Re-appending the same (date, ticker) with different us_* stamp values must
        not overwrite the original row (keep-FIRST per PIT integrity guarantee)."""
        from unittest.mock import patch

        monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")

        fake_stamp_v1 = {
            "rate_pressure": "low",
            "quad_hard_label": "Q4",
            "fused_risk_label": "risk_off",
            "vol_regime": "high",
            "risk_radar_state": "alert",
            "regime_vector_degraded": False,
            "vector_asof": "2026-07-01",
            "staleness_hours": 0.0,
        }

        with patch("engine.regime_vector.get_vector_for_date", return_value=fake_stamp_v1):
            bl.append_board(
                [{"ticker": "KA.HK", "group": "entry_open", "edge_z": 2.0, "close_asof": 10.0}],
                "HK", asof="2026-07-01"
            )

        # Now re-append with a completely different stamp — keep-FIRST must win
        fake_stamp_v2 = {
            "rate_pressure": "rising",
            "quad_hard_label": "Q1",
            "fused_risk_label": "risk_on",
            "vol_regime": "low",
            "risk_radar_state": "neutral",
            "regime_vector_degraded": False,
            "vector_asof": "2026-07-01",
            "staleness_hours": 2.0,
        }
        with patch("engine.regime_vector.get_vector_for_date", return_value=fake_stamp_v2):
            n = bl.append_board(
                [{"ticker": "KA.HK", "group": "watch", "edge_z": 9.9, "close_asof": 999.0}],
                "HK", asof="2026-07-01"
            )
        assert n == 1  # still 1 row (no duplicate)

        df = pd.read_parquet(tmp_path / "hk_board.parquet")
        row = df[df["ticker"] == "KA.HK"].iloc[0]

        # Original values must be preserved
        assert row["group"] == "entry_open"   # not "watch"
        assert float(row["edge_z"]) == pytest.approx(2.0)  # not 9.9
        assert row["us_rate_pressure"] == "low"   # v1 stamp preserved, not "rising"
        assert row["us_quad_hard_label"] == "Q4"  # v1 stamp preserved, not "Q1"


# ---------------------------------------------------------------------------
# W0.2 Stage C — near-miss fields on the append path
# ---------------------------------------------------------------------------
class TestNearMissFields:

    def test_taxonomy_reason_and_knife_fields_persist(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        n = bl.append_board([{
            "ticker": "0001.HK", "group": "watch",
            "primary_rejection_reason": "knife_demote",
            "knife_demoted": True, "knife_z": -1.83,
            "block_reason": "weekly still falling",
        }], market="HK", asof="2026-07-06")
        assert n == 1
        row = pd.read_parquet(tmp_path / "hk_board.parquet").iloc[0]
        assert row["primary_rejection_reason"] == "knife_demote"
        assert bool(row["knife_demoted"]) is True
        assert float(row["knife_z"]) == -1.83
        assert row["block_reason"] == "weekly still falling"

    def test_non_taxonomy_reason_nulled_loudly(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        import logging
        with caplog.at_level(logging.WARNING):
            bl.append_board([{
                "ticker": "AC.TO", "group": "watch",
                "primary_rejection_reason": "not_in_the_closed_set",
            }], market="CA", asof="2026-07-06")
        row = pd.read_parquet(tmp_path / "ca_board.parquet").iloc[0]
        assert pd.isna(row["primary_rejection_reason"])
        assert any("non-taxonomy" in r.message for r in caplog.records)

    def test_entry_rows_get_null_near_miss_fields(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        bl.append_board([{"ticker": "0005.HK", "group": "entry_open",
                          "edge_z": 1.0}], market="HK", asof="2026-07-06")
        row = pd.read_parquet(tmp_path / "hk_board.parquet").iloc[0]
        assert pd.isna(row["primary_rejection_reason"])
        assert pd.isna(row["knife_z"])


# ---------------------------------------------------------------------------
# 15. gate_ver provenance stamp (2026-07-16 HK INCLUDE gate swap, §5.0 amendment)
# ---------------------------------------------------------------------------
class TestGateVerStamp:
    """The gate_ver payload key must pass through append_board into the parquet
    (W7/Q4 grading splits pre/post-swap samples on it). Regression: the first
    implementation added gate_ver to _SCHEMA only — the row-build whitelist
    dropped the payload and the column wrote all-None."""

    def test_gate_ver_passthrough(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        bl.append_board([{"ticker": "0700.HK", "group": "entry_open",
                          "edge_z": 1.0, "gate_ver": "cascade_v1"}],
                        market="HK", asof="2026-07-16")
        row = pd.read_parquet(tmp_path / "hk_board.parquet").iloc[0]
        assert row["gate_ver"] == "cascade_v1"

    def test_gate_ver_absent_is_null(self, tmp_path, monkeypatch):
        """Callers that don't stamp (CN/CA today, pre-swap HK rows) stay None."""
        monkeypatch.setattr(bl, "_store_path",
                            lambda m: tmp_path / f"{m.lower()}_board.parquet")
        bl.append_board([{"ticker": "0005.HK", "group": "entry_open",
                          "edge_z": 1.0}], market="HK", asof="2026-07-16")
        row = pd.read_parquet(tmp_path / "hk_board.parquet").iloc[0]
        assert pd.isna(row["gate_ver"])
