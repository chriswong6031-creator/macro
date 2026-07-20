"""tests/test_track_ledger_emitters.py — the four Track-record popup ledger emitters
(track_ledger/v1). Covers, per market: schema/v1 shape, compact row keys, status
vocabulary, matured-vs-early marking, locked/suspended flags, truncation disclosure,
JSON round-trip (the numpy-scalar trap), and summary consistency with rows.

House law: NEVER write real data/ or site/ stores (MM_DATA_GUARD kills the build on
store mutation). Every store root here is a monkeypatched tmp_path; the US/CN emitters
are driven with patched price/board sources; the HK/CA path is exercised through the
pure engine.track_ledger.from_board_ledger_grade() converter (no I/O at all).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import track_ledger as tl  # noqa: E402


# ===========================================================================
# 0. shared module — pyify (the numpy trap), wilson, build_shell
# ===========================================================================

class TestPyifyNumpyTrap:
    def test_numpy_scalars_become_pure_python(self):
        out = tl.pyify({"a": np.float64(1.5), "b": np.int64(7), "c": np.bool_(True)})
        assert out == {"a": 1.5, "b": 7, "c": True}
        assert isinstance(out["a"], float) and isinstance(out["b"], int)
        assert isinstance(out["c"], bool)

    def test_nan_and_inf_become_null(self):
        out = tl.pyify({"x": float("nan"), "y": np.float64("nan"), "z": float("inf")})
        assert out["x"] is None and out["y"] is None and out["z"] is None

    def test_pandas_na_nat_become_null(self):
        assert tl.pyify(pd.NaT) is None
        assert tl.pyify(pd.NA) is None

    def test_nested_lists_and_dicts(self):
        out = tl.pyify([{"n": np.int64(3)}, [np.float64(2.0), None]])
        assert out == [{"n": 3}, [2.0, None]]

    def test_result_is_json_dumpable_without_default(self):
        doc = tl.pyify({"v": np.float64(0.68), "bad": float("nan"), "t": "AAA"})
        s = json.dumps(doc)  # must NOT raise, must NOT emit bare NaN
        assert "NaN" not in s


class TestWilson:
    def test_zero_n_returns_none(self):
        assert tl.wilson_ci(0, 0) == (None, None)

    def test_bounds_ordered_and_in_unit_range(self):
        lo, hi = tl.wilson_ci(6, 10)
        assert 0.0 <= lo <= hi <= 1.0


class TestBuildShell:
    def _doc(self, rows, **kw):
        return tl.build_shell(
            "US", "2026-07-20", "scored",
            {"code": "SPY", "en": "S&P 500", "zh": "标普500"},
            {"win_rate": 0.6}, rows, grain="episode", **kw,
        )

    def test_schema_and_top_level_shape(self):
        d = self._doc([{"t": "A", "d": "2026-07-01", "st": "up", "fl": []}])
        assert d["schema"] == "track_ledger/v1"
        assert d["market"] == "US"
        assert d["state"] == "scored"
        assert set(d.keys()) == {"schema", "market", "as_of", "state", "bench",
                                 "summary", "rows", "meta"}
        assert d["bench"]["code"] == "SPY"

    def test_truncation_disclosure(self):
        rows = [{"t": f"T{i}", "d": f"2026-01-{(i % 28) + 1:02d}", "st": "up", "fl": []}
                for i in range(tl.MAX_ROWS + 123)]
        d = self._doc(rows)
        assert len(d["rows"]) == tl.MAX_ROWS
        assert d["meta"]["truncated"] == 123
        assert d["meta"]["n_total"] == tl.MAX_ROWS + 123

    def test_rows_sorted_newest_first(self):
        rows = [{"t": "OLD", "d": "2026-01-01", "st": "up", "fl": []},
                {"t": "NEW", "d": "2026-07-01", "st": "up", "fl": []}]
        d = self._doc(rows)
        assert d["rows"][0]["t"] == "NEW"

    def test_survivorship_and_grain_in_meta(self):
        d = self._doc([], survivorship={"n_skipped_no_price": np.int64(2)})
        assert d["meta"]["grain"] == "episode"
        assert d["meta"]["survivorship"]["n_skipped_no_price"] == 2
        assert isinstance(d["meta"]["survivorship"]["n_skipped_no_price"], int)


# ===========================================================================
# 1. US — grade_us_board.emit_ledger (buy-lane EPISODE grain)
# ===========================================================================

def _us_boards() -> list[dict]:
    """Two-date board history. AAA on both dates (still on board → onboard). BBB only on
    the first date (exited). CCC only on the first date, has NO price column (survivorship
    skip)."""
    return [
        {"as_of": "2026-06-01", "rows": [
            {"lane": "buy", "ticker": "AAA", "sector": "Tech", "position": 0, "align_tier": "T1"},
            {"lane": "buy", "ticker": "BBB", "sector": "Energy", "position": 1, "align_tier": "T2"},
            {"lane": "buy", "ticker": "CCC", "sector": "Health", "position": 2, "align_tier": None},
            {"lane": "watch", "ticker": "ZZZ", "sector": "X", "position": 0},
        ]},
        {"as_of": "2026-06-20", "rows": [
            {"lane": "buy", "ticker": "AAA", "sector": "Tech", "position": 0, "align_tier": "T1"},
        ]},
    ]


def _us_closes() -> pd.DataFrame:
    idx = pd.to_datetime(["2026-06-01", "2026-06-10", "2026-06-20", "2026-06-30"])
    # AAA rises; BBB falls hard (stopped). CCC absent (no column → skipped).
    return pd.DataFrame({
        "AAA": [100.0, 104.0, 108.0, 110.0],   # +10% → up
        "BBB": [50.0, 47.0, 44.0, 43.0],       # −14% → stopped
    }, index=idx)


def _run_us_emit(monkeypatch, tmp_path, retro_rows=None):
    from scripts import grade_us_board as gub
    # retro_grades store: matured 21d excess join for (first_surfaced, ticker).
    retro = tmp_path / "retro_grades.parquet"
    if retro_rows:
        pd.DataFrame(retro_rows).to_parquet(retro, index=False)
    monkeypatch.setattr(gub, "RETRO_PARQUET", retro)
    return gub.emit_ledger(_us_boards(), _us_closes())


class TestUSEmitLedger:
    def test_schema_and_grain(self, monkeypatch, tmp_path):
        d = _run_us_emit(monkeypatch, tmp_path)
        assert d["schema"] == "track_ledger/v1"
        assert d["market"] == "US"
        assert d["meta"]["grain"] == "episode"
        assert d["bench"] == {"code": "SPY", "en": "S&P 500", "zh": "标普500"}

    def test_compact_row_keys(self, monkeypatch, tmp_path):
        d = _run_us_emit(monkeypatch, tmp_path)
        row = d["rows"][0]
        for k in ("t", "d", "st"):  # required-non-null keys
            assert k in row and row[k] is not None
        for k in ("nm", "sec", "grp", "e", "l", "p", "x", "dy", "m", "rk", "tr", "fl"):
            assert k in row

    def test_status_vocabulary_and_marking(self, monkeypatch, tmp_path):
        d = _run_us_emit(monkeypatch, tmp_path)
        by_t = {r["t"]: r for r in d["rows"]}
        assert by_t["AAA"]["st"] == "onboard"          # on the current board
        assert by_t["BBB"]["st"] == "stopped"          # −14% < −2
        assert "CCC" not in by_t                        # no price → survivorship skip
        for r in d["rows"]:
            assert r["st"] in tl.STATUS_VOCAB

    def test_survivorship_skip_counted(self, monkeypatch, tmp_path):
        d = _run_us_emit(monkeypatch, tmp_path)
        assert d["summary"]["n_skipped_no_price"] == 1
        assert d["meta"]["survivorship"]["n_skipped_no_price"] == 1

    def test_matured_excess_join(self, monkeypatch, tmp_path):
        # BBB matured with 21d excess_spy = -0.05 (fraction) → x = -5.0 pct, m True.
        d = _run_us_emit(monkeypatch, tmp_path, retro_rows=[
            {"as_of": "2026-06-01", "ticker": "BBB", "horizon": 21, "lane": "buy", "excess_spy": -0.05},
            {"as_of": "2026-06-01", "ticker": "BBB", "horizon": 5, "lane": "buy", "excess_spy": 0.9},  # wrong horizon
        ])
        bbb = {r["t"]: r for r in d["rows"]}["BBB"]
        assert bbb["m"] is True
        assert bbb["x"] == -5.0
        # AAA has no matured row → m False, x None
        aaa = {r["t"]: r for r in d["rows"]}["AAA"]
        assert aaa["m"] is False and aaa["x"] is None

    def test_summary_consistency_with_rows(self, monkeypatch, tmp_path):
        d = _run_us_emit(monkeypatch, tmp_path)
        resolved = [r for r in d["rows"] if r["st"] in ("up", "stopped", "flat")]
        s = d["summary"]
        assert s["n_resolved"] == len(resolved)
        assert s["n_up"] == sum(1 for r in resolved if r["st"] == "up")
        assert s["n_stopped"] == sum(1 for r in resolved if r["st"] == "stopped")
        assert s["n_onboard"] == sum(1 for r in d["rows"] if r["st"] == "onboard")

    def test_json_round_trip(self, monkeypatch, tmp_path):
        d = _run_us_emit(monkeypatch, tmp_path, retro_rows=[
            {"as_of": "2026-06-01", "ticker": "BBB", "horizon": 21, "lane": "buy", "excess_spy": -0.05},
        ])
        s = json.dumps(d)  # numpy trap: must not raise
        assert "NaN" not in s
        assert json.loads(s)["schema"] == "track_ledger/v1"

    def test_empty_boards_degrades(self, monkeypatch, tmp_path):
        from scripts import grade_us_board as gub
        monkeypatch.setattr(gub, "RETRO_PARQUET", tmp_path / "nope.parquet")
        d = gub.emit_ledger([], _us_closes())
        assert d["schema"] == "track_ledger/v1"
        assert d["state"] == "accruing"
        assert d["rows"] == []


# ===========================================================================
# 2. CN — build_china_library.emit_cn_track_ledger (board_day×ticker grain)
# ===========================================================================

def _cn_board_parquet(tmp_path: Path) -> Path:
    d = tmp_path / "china_standout_track"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "board.parquet"
    pd.DataFrame([
        {"date": "2026-06-01", "ticker": "600519.SS", "board_rank": 1, "tier": "T1"},  # matured beat
        {"date": "2026-06-01", "ticker": "300750.SZ", "board_rank": 2, "tier": "T2"},  # matured lag
        {"date": "2026-07-15", "ticker": "601318.SS", "board_rank": 1, "tier": "T1"},  # early
        {"date": "2026-07-15", "ticker": "000001.SZ", "board_rank": 3, "tier": "T3"},  # locked
    ]).to_parquet(p, index=False)
    return p


def _ohlc(idx, closes):
    """Realistic OHLC: high/low straddle close so _t1_fill does NOT read locked-limit
    (high==low==close is the locked test). open present so fill = true open."""
    return pd.DataFrame({
        "open": [c for c in closes],
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": [c for c in closes],
    }, index=idx)


def _cn_price_frame(ticker: str):
    """Synthetic OHLC per ticker. 600519 rises a lot, 300750 falls; 601318 recent (early);
    000001 is locked-limit at T+1 (high==low==close)."""
    if ticker == "600519.SS":
        idx = pd.to_datetime(["2026-06-01"] + [f"2026-06-{d:02d}" for d in range(2, 30)])
        return _ohlc(idx, [100.0 + i * 2 for i in range(len(idx))])
    if ticker == "300750.SZ":
        idx = pd.to_datetime(["2026-06-01"] + [f"2026-06-{d:02d}" for d in range(2, 30)])
        return _ohlc(idx, [200.0 - i * 1.5 for i in range(len(idx))])
    if ticker == "601318.SS":
        idx = pd.to_datetime(["2026-07-15", "2026-07-16", "2026-07-17"])
        return _ohlc(idx, [40.0, 41.0, 42.0])
    if ticker == "000001.SZ":
        idx = pd.to_datetime(["2026-07-15", "2026-07-16"])
        # T+1 bar (07-16) prints high==low==close → locked-limit, unfillable
        return pd.DataFrame({"open": [10.0, 11.0], "high": [10.0, 11.0],
                             "low": [10.0, 11.0], "close": [10.0, 11.0]}, index=idx)
    return None


def _cn_bench_series():
    idx = pd.to_datetime(["2026-06-01"] + [f"2026-06-{d:02d}" for d in range(2, 30)]
                         + ["2026-07-15", "2026-07-16", "2026-07-17"])
    return pd.Series([3000.0 + i for i in range(len(idx))], index=idx)


def _run_cn_emit(monkeypatch, tmp_path, bt=None):
    from scripts import build_china_library as bcl
    from engine import china_standout_track as cst
    p = _cn_board_parquet(tmp_path)
    monkeypatch.setattr(cst, "_store_path", lambda: p)
    monkeypatch.setattr(cst, "_price_frame", _cn_price_frame)
    monkeypatch.setattr(cst, "_bench_close", _cn_bench_series)
    buy = [{"ticker": "600519.SS", "name": "Kweichow Moutai", "sector": "Staples"},
           {"ticker": "300750.SZ", "name": "CATL", "sector": "Industrials"}]
    # write to tmp site
    site = tmp_path / "site"
    (site / "factordata").mkdir(parents=True, exist_ok=True)
    ok = bcl.emit_cn_track_ledger(site, bt, buy)
    doc = json.loads((site / "factordata" / "cn_track_ledger.json").read_text())
    return ok, doc


class TestCNEmitLedger:
    def test_schema_grain_bench(self, monkeypatch, tmp_path):
        ok, d = _run_cn_emit(monkeypatch, tmp_path)
        assert ok is True
        assert d["schema"] == "track_ledger/v1"
        assert d["market"] == "CN"
        assert d["meta"]["grain"] == "board_day"
        assert d["bench"] == {"code": "510300.SS", "en": "CSI 300", "zh": "沪深300"}

    def test_matured_beat_and_lag(self, monkeypatch, tmp_path):
        _ok, d = _run_cn_emit(monkeypatch, tmp_path)
        by = {r["t"]: r for r in d["rows"]}
        assert by["600519.SS"]["m"] is True
        assert by["600519.SS"]["st"] == "beat"      # rose fast → positive excess
        assert by["300750.SZ"]["m"] is True
        assert by["300750.SZ"]["st"] == "lag"       # fell → negative excess

    def test_early_row_marking(self, monkeypatch, tmp_path):
        _ok, d = _run_cn_emit(monkeypatch, tmp_path)
        by = {r["t"]: r for r in d["rows"]}
        assert by["601318.SS"]["m"] is False
        assert by["601318.SS"]["st"] == "early"

    def test_locked_limit_flag_and_exclusion(self, monkeypatch, tmp_path):
        _ok, d = _run_cn_emit(monkeypatch, tmp_path)
        by = {r["t"]: r for r in d["rows"]}
        assert "locked" in by["000001.SZ"]["fl"]
        assert d["summary"]["n_locked_excluded"] == 1
        # a locked row must not inflate the interim/ matured counts
        assert d["summary"]["n_matured"] == 2  # only the two June names matured

    def test_status_vocabulary(self, monkeypatch, tmp_path):
        _ok, d = _run_cn_emit(monkeypatch, tmp_path)
        for r in d["rows"]:
            assert r["st"] in tl.STATUS_VOCAB
            assert set(r["fl"]).issubset(set(tl.FLAG_VOCAB))

    def test_state_from_bt_selector(self, monkeypatch, tmp_path):
        # scored 21d block present (n>=8, hit_vs_csi300 set) → state scored
        bt = {"available": True, "by_horizon": {"21d": {"n": 20, "hit_vs_csi300": 0.55}}}
        _ok, d = _run_cn_emit(monkeypatch, tmp_path, bt=bt)
        assert d["state"] == "scored"
        # interim available with n>=8 → interim
        bt2 = {"available": True, "by_horizon": {"21d": {"n": 3, "note": "accruing"}},
               "interim": {"available": True, "n": 12, "hit_vs_csi300": 0.5}}
        _ok2, d2 = _run_cn_emit(monkeypatch, tmp_path, bt=bt2)
        assert d2["state"] == "interim"
        # nothing → accruing
        _ok3, d3 = _run_cn_emit(monkeypatch, tmp_path, bt=None)
        assert d3["state"] == "accruing"

    def test_json_round_trip(self, monkeypatch, tmp_path):
        _ok, d = _run_cn_emit(monkeypatch, tmp_path)
        s = json.dumps(d)
        assert "NaN" not in s
        assert json.loads(s)["market"] == "CN"

    def test_no_real_store_written(self, monkeypatch, tmp_path):
        # emitter must write ONLY under the tmp site we pass — assert file lives there.
        _ok, _d = _run_cn_emit(monkeypatch, tmp_path)
        assert (tmp_path / "site" / "factordata" / "cn_track_ledger.json").exists()


# ===========================================================================
# 3. HK / CA — engine.track_ledger.from_board_ledger_grade (pure converter)
# ===========================================================================

def _grade_dict(market: str) -> dict:
    """Shape-faithful board_ledger.grade(market) output: 21d horizon list of per-row
    dicts (date, ticker, board_pos, group, edge_z, fwd_ret, bench_ret, excess_ret,
    suspended)."""
    return {
        "market": market, "available": True, "n_calls": 4, "n_graded": 2, "n_suspended": 1,
        "survivorship": "no_dead_name_store",
        "by_horizon": {
            "5d": [], "10d": [], "63d": [],
            "21d": [
                {"date": "2026-06-01", "ticker": "0700.HK", "board_pos": 1, "group": "entry_open",
                 "edge_z": 1.2, "fwd_ret": 0.08, "bench_ret": 0.02, "excess_ret": 0.06,
                 "suspended": False},   # matured beat
                {"date": "2026-06-01", "ticker": "0005.HK", "board_pos": 2, "group": "setting_up",
                 "edge_z": 0.5, "fwd_ret": -0.03, "bench_ret": 0.01, "excess_ret": -0.04,
                 "suspended": False},   # matured lag
                {"date": "2026-07-15", "ticker": "9988.HK", "board_pos": 1, "group": "entry_open",
                 "edge_z": 0.9, "fwd_ret": None, "bench_ret": None, "excess_ret": None,
                 "suspended": False},   # early
                {"date": "2026-07-15", "ticker": "3690.HK", "board_pos": 3, "group": "watch",
                 "edge_z": None, "fwd_ret": None, "bench_ret": None, "excess_ret": None,
                 "suspended": True},    # suspended
            ],
        },
    }


def _scorecard(status="accruing"):
    return {"market": "HK", "status": status, "first_read_est": "2026-08-24"}


class TestFromBoardLedgerGrade:
    def _doc(self, market="HK", status="accruing"):
        return tl.from_board_ledger_grade(
            market, _grade_dict(market), _scorecard(status),
            bench={"code": "_HSI", "en": "Hang Seng", "zh": "恒生指数"},
            name_lookup={"0700.HK": {"nm": "Tencent", "sec": "Tech", "grp": "entry_open"}},
            as_of="2026-07-15",
        )

    def test_schema_and_shape(self):
        d = self._doc()
        assert d["schema"] == "track_ledger/v1"
        assert d["market"] == "HK"
        assert d["meta"]["grain"] == "board_day"
        assert d["bench"]["zh"] == "恒生指数"

    def test_matured_beat_lag_marking(self):
        by = {r["t"]: r for r in self._doc()["rows"]}
        assert by["0700.HK"]["m"] is True and by["0700.HK"]["st"] == "beat"
        assert by["0700.HK"]["x"] == 6.0          # 0.06 * 100
        assert by["0005.HK"]["m"] is True and by["0005.HK"]["st"] == "lag"
        assert by["0005.HK"]["x"] == -4.0

    def test_early_row_null_excess(self):
        by = {r["t"]: r for r in self._doc()["rows"]}
        assert by["9988.HK"]["m"] is False
        assert by["9988.HK"]["st"] == "early"
        assert by["9988.HK"]["x"] is None

    def test_suspended_flag_and_exclusion(self):
        d = self._doc()
        by = {r["t"]: r for r in d["rows"]}
        assert by["3690.HK"]["fl"] == ["susp"]
        assert d["summary"]["n_suspended"] == 1
        # suspended row excluded from matured beat/lag counts
        assert d["summary"]["n_matured"] == 2
        assert d["summary"]["n_beat"] == 1 and d["summary"]["n_lag"] == 1

    def test_status_and_flag_vocabulary(self):
        d = self._doc()
        for r in d["rows"]:
            assert r["st"] in tl.STATUS_VOCAB
            assert set(r["fl"]).issubset(set(tl.FLAG_VOCAB))

    def test_name_lookup_applied(self):
        by = {r["t"]: r for r in self._doc()["rows"]}
        assert by["0700.HK"]["nm"] == "Tencent"
        assert by["0700.HK"]["sec"] == "Tech"

    def test_state_passthrough(self):
        assert self._doc(status="accruing")["state"] == "accruing"
        assert self._doc(status="scored")["state"] == "scored"

    def test_summary_consistency(self):
        d = self._doc()
        beats = sum(1 for r in d["rows"] if r["st"] == "beat")
        lags = sum(1 for r in d["rows"] if r["st"] == "lag")
        assert d["summary"]["n_beat"] == beats
        assert d["summary"]["n_lag"] == lags

    def test_ca_bench_labels(self):
        d = tl.from_board_ledger_grade(
            "CA", _grade_dict("CA"), _scorecard(),
            bench={"code": "_GSPTSE", "en": "S&P/TSX Composite", "zh": "多伦多综指"},
        )
        assert d["market"] == "CA"
        assert d["bench"]["en"] == "S&P/TSX Composite"

    def test_json_round_trip(self):
        s = json.dumps(self._doc())
        assert "NaN" not in s
        assert json.loads(s)["schema"] == "track_ledger/v1"

    def test_unavailable_grade_degrades(self):
        d = tl.from_board_ledger_grade(
            "HK", {"available": False, "note": "no data"}, _scorecard(),
            bench={"code": "_HSI", "en": "Hang Seng", "zh": "恒生指数"},
        )
        assert d["schema"] == "track_ledger/v1"
        assert d["rows"] == []
        assert d["state"] == "accruing"


# ===========================================================================
# 4. atomic write — tmp+rename, never open('w') truncation
# ===========================================================================

class TestAtomicWrite:
    def test_writes_and_no_tmp_left(self, tmp_path):
        out = tmp_path / "factordata" / "x_track_ledger.json"
        doc = tl.build_shell("US", "2026-07-20", "scored", {"code": "SPY"}, {}, [], "episode")
        assert tl.atomic_write(out, doc) is True
        assert out.exists()
        assert not list(out.parent.glob("*.tmp"))  # tmp file cleaned up by os.replace
        assert json.loads(out.read_text())["schema"] == "track_ledger/v1"
