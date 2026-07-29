"""Hot Tape fat lane — the nightly context pack (engine/marketing/hot_tape_pack.py).

Builds a synthetic daily store in tmp_path and asserts the stat kit the §2.D
devices depend on: streak length and rarity dates, Wilder RSI against an
independently coded reference, ATH distance and the correction/bear/round
levels, the ADV floor, the reference/earnings joins, split suspicion, and
determinism.

pandas/numpy/pyarrow are PLAIN imports on purpose. This suite belongs to the
fat CI lane; an importorskip here would let the whole file go dark the first
time the lane's dependency list drifts (the unrun-suite rot class). Every
fixture date is derived from today.

Run: .venv/bin/python -m pytest tests/test_marketing_hot_tape_pack.py -q
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from engine.marketing import hot_tape as HT
from engine.marketing import hot_tape_pack as HP


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic store
# ─────────────────────────────────────────────────────────────────────────────

N_ROWS = 320


def _weekdays(n: int, end: date | None = None) -> list[date]:
    """`n` consecutive weekdays ending at the most recent weekday on/before end."""
    cursor = end or date.today()
    while cursor.weekday() >= 5:
        cursor -= timedelta(days=1)
    out: list[date] = []
    while len(out) < n:
        if cursor.weekday() < 5:
            out.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(out))


DATES = _weekdays(N_ROWS)
TIP = DATES[-1]


def _write(tmp_path, ticker: str, closes, volume=5_000_000, dates=None,
           store_rel: str = HP.STORE_REL, index_name: str = "date",
           with_open: bool = True) -> None:
    """One synthetic parquet in `store_rel`, shaped like that store.

    The three stores disagree: massive names its index "date" and carries
    open+transactions, the curated trees name it "Date" and data/stocks has no
    `open` column at all. The scan must read all three.
    """
    closes = [float(c) for c in closes]
    idx = pd.DatetimeIndex(pd.to_datetime(dates or _weekdays(len(closes))),
                           name=index_name)
    cols = {
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": np.full(len(closes), int(volume), dtype="int64"),
    }
    if with_open:
        cols["open"] = closes
        cols["transactions"] = np.full(len(closes), 10_000, dtype="int64")
    df = pd.DataFrame(cols, index=idx)
    store = tmp_path / store_rel
    store.mkdir(parents=True, exist_ok=True)
    df.to_parquet(store / f"{ticker}.parquet")


def _base_series(n: int = N_ROWS, start: float = 100.0) -> list[float]:
    """A gently alternating walk with no runs longer than 2 and no big jumps."""
    out = [start]
    for i in range(1, n):
        out.append(out[-1] * (1.004 if i % 2 else 0.996))
    return out


def _streak_series() -> tuple[list[float], date]:
    """Exactly 8 down days into the tip, and exactly one 9-day down run before it.

    Built from an explicit step-direction list so both runs have hard edges: an
    accidental extra down day on either side would turn the 9-run into a 10-run
    and quietly move last_run_ge, which is the fact the copy layer says "its
    longest red run since <date>" from.
    """
    older_end = N_ROWS - 1 - 78               # ~78 weekdays back, inside the window
    steps = [1 if i % 2 else -1 for i in range(N_ROWS - 1)]   # step i: close i -> i+1
    for i in range(older_end - 9, older_end):                 # 9 down days
        steps[i] = -1
    steps[older_end - 10] = 1                                 # hard edge before
    steps[older_end] = 1                                      # hard edge after
    for i in range(N_ROWS - 9, N_ROWS - 1):                   # 8 down days into the tip
        steps[i] = -1
    steps[N_ROWS - 10] = 1                                    # hard edge before
    closes = [100.0]
    for step in steps:
        closes.append(closes[-1] * (1.01 if step > 0 else 0.98))
    return closes, DATES[older_end]


def _rsi_reference(closes, period: int = 14) -> float:
    """Wilder RSI, coded independently of the implementation under test."""
    gains, losses = [], []
    for prev, cur in zip(closes, closes[1:]):
        delta = cur - prev
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_g / avg_l))


@pytest.fixture()
def store(tmp_path):
    """Six synthetic tickers covering every branch of the scan."""
    streak_closes, older_run_end = _streak_series()
    _write(tmp_path, "STRK", streak_closes)

    # Oversold then recovering: RSI dips under 30 mid-window, back above by the tip.
    osc = _base_series()
    for i in range(150, 175):
        osc[i] = osc[i - 1] * 0.97
    for i in range(175, N_ROWS):
        osc[i] = osc[i - 1] * 1.004
    _write(tmp_path, "OSC", osc)

    # A peak 30% above the tip, then a flat drift down.
    peak = _base_series()
    for i in range(100, 140):
        peak[i] = peak[i - 1] * 1.01
    top = max(peak[:141])
    for i in range(141, N_ROWS):
        peak[i] = top / 1.3 * (1.0 + 0.0001 * ((i % 3) - 1))
    _write(tmp_path, "PEAK", peak)

    _write(tmp_path, "TINY", _base_series(), volume=100)          # under the ADV floor
    _write(tmp_path, "SPLT", _base_series()[:-1] + [20.0])        # a 5x-style jump
    _write(tmp_path, "GAPY", _base_series(),                      # a torn history
           dates=_weekdays(120, TIP - timedelta(days=400)) + _weekdays(200, TIP))
    (tmp_path / HP.STORE_REL / "_manifest.json").write_text("{}", encoding="utf-8")
    return {"root": tmp_path, "older_run_end": older_run_end,
            "streak_closes": streak_closes, "osc": osc, "peak": peak}


def _build(root, **over):
    cfg = {"universe": {"min_adv_dollars": 25_000_000, "max_tickers": 3000,
                        "workers": 1}}
    cfg["universe"].update(over)
    return HP.build_pack(root, cfg=cfg,
                         now=datetime(2000, 1, 1, tzinfo=timezone.utc))


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStoreAbsent:
    def test_a_fresh_checkout_is_quiet(self, tmp_path):
        pack = HP.build_pack(tmp_path)
        assert pack["error"] == "store absent"
        assert pack["tickers"] == {}

    def test_write_pack_reports_the_error(self, tmp_path):
        assert HP.write_pack(tmp_path) == {"error": "store absent"}


class TestPackShape:
    def test_schema_and_tip(self, store):
        pack = _build(store["root"])
        assert pack["schema"] == "marketing.hot_tape_pack/v1"
        assert pack["trade_date"] == TIP.isoformat()
        assert pack["sources"]["store_last_date"] == TIP.isoformat()
        assert pack["n_tickers"] == len(pack["tickers"])

    def test_every_documented_field_is_present(self, store):
        rec = _build(store["root"])["tickers"]["STRK"]
        for field in ("last_date", "last_close", "prev_close", "streak", "ath",
                      "ath_date", "high_52w", "high_52w_date", "low_52w",
                      "low_52w_date", "pct_from_ath", "ma20", "ma50", "ma200",
                      "rsi14", "rsi_avg_gain", "rsi_avg_loss", "rsi_low_1y",
                      "rsi_low_1y_date", "rsi_high_1y", "rsi_high_1y_date",
                      "last_rsi_le_30", "last_rsi_ge_70", "max_up_1d", "max_dn_1d",
                      "max_up_5d", "max_dn_5d", "round_above", "round_below",
                      "px_correction", "px_bear", "adv20_dollars", "adv_rank",
                      "mcap_usd", "shares_est", "sector", "sp500",
                      "earn_next_date", "earn_next_time", "window_start",
                      "suspect"):
            assert field in rec, field

    def test_the_pack_reads_with_the_json_module_alone(self, store):
        res = HP.write_pack(store["root"],
                            cfg={"universe": {"workers": 1}})
        assert res.get("error") is None
        obj = json.loads((store["root"] / HP.OUT_REL).read_text(encoding="utf-8"))
        assert obj["schema"] == "marketing.hot_tape_pack/v1"
        assert HT.load_pack(store["root"])["trade_date"] == TIP.isoformat()

    def test_determinism(self, store):
        a = _build(store["root"])
        b = _build(store["root"])
        a.pop("built_at"), b.pop("built_at")
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_the_process_pool_path_matches_the_serial_path(self, store):
        serial = _build(store["root"], workers=1)
        pooled = _build(store["root"], workers=4)
        serial.pop("built_at"), pooled.pop("built_at")
        assert json.dumps(serial, sort_keys=True) == json.dumps(pooled, sort_keys=True)


class TestLiquidity:
    def test_the_adv_floor_drops_illiquid_names(self, store):
        pack = _build(store["root"])
        assert "TINY" not in pack["tickers"]
        assert "STRK" in pack["tickers"]

    def test_adv_rank_is_dense_and_starts_at_one(self, store):
        pack = _build(store["root"])
        ranks = sorted(r["adv_rank"] for r in pack["tickers"].values())
        assert ranks == list(range(1, len(ranks) + 1))

    def test_max_tickers_cuts_by_rank(self, store):
        pack = _build(store["root"], max_tickers=2)
        assert len(pack["tickers"]) == 2
        assert {r["adv_rank"] for r in pack["tickers"].values()} == {1, 2}

    def test_a_heatmap_name_survives_the_floor(self, store):
        root = store["root"]
        (root / "site" / "marketdata").mkdir(parents=True, exist_ok=True)
        (root / "site" / "marketdata" / "sp500_heatmap.json").write_text(json.dumps({
            "asof": TIP.isoformat(), "size_basis": "weight_proxy",
            "tiles": [{"t": "TINY", "name": "Tiny Co", "sector": "Utilities",
                       "industry": "Utilities - Regulated", "size": 0.1,
                       "perf": {"1D": -1.0}}],
        }), encoding="utf-8")
        pack = _build(root)
        assert "TINY" in pack["tickers"]
        assert pack["tickers"]["TINY"]["sector"] == "Utilities"
        assert pack["tickers"]["TINY"]["sp500"] is True
        assert pack["sources"]["heatmap_asof"] == TIP.isoformat()


class TestStreaks:
    def test_the_current_run_length(self, store):
        rec = _build(store["root"])["tickers"]["STRK"]
        assert rec["streak"]["dir"] == "down"
        assert rec["streak"]["len"] == 8

    def test_rarity_points_at_the_older_run(self, store):
        rec = _build(store["root"])["tickers"]["STRK"]
        assert rec["streak"]["last_run_ge"]["9"] == store["older_run_end"].isoformat()
        assert set(rec["streak"]["last_run_ge"]) == {"9", "10", "11", "12"}
        assert rec["streak"]["last_run_ge"]["10"] is None

    def test_a_quiet_name_has_a_short_run(self, store):
        rec = _build(store["root"])["tickers"]["OSC"]
        assert rec["streak"]["len"] >= 1


class TestRsi:
    def test_matches_an_independent_wilder_implementation(self, store):
        rec = _build(store["root"])["tickers"]["OSC"]
        assert rec["rsi14"] == pytest.approx(_rsi_reference(store["osc"]), abs=0.5)

    def test_the_averages_support_a_live_one_step(self, store):
        """The radar steps RSI forward from these two numbers."""
        rec = _build(store["root"])["tickers"]["OSC"]
        assert rec["rsi_avg_gain"] > 0
        assert rec["rsi_avg_loss"] > 0
        stepped = HT._rsi_step(rec, 0.0)
        assert stepped == pytest.approx(rec["rsi14"], abs=2.0)

    def test_the_oversold_date_is_the_previous_episode(self, store):
        rec = _build(store["root"])["tickers"]["OSC"]
        assert rec["rsi14"] > 30
        assert rec["last_rsi_le_30"] is not None
        assert rec["last_rsi_le_30"] < TIP.isoformat()

    def test_one_year_extremes_carry_dates(self, store):
        rec = _build(store["root"])["tickers"]["OSC"]
        assert rec["rsi_low_1y"] <= rec["rsi14"] <= rec["rsi_high_1y"]
        assert date.fromisoformat(rec["rsi_low_1y_date"]) <= TIP


class TestLevels:
    def test_ath_distance_and_thresholds(self, store):
        rec = _build(store["root"])["tickers"]["PEAK"]
        ath = max(store["peak"])
        assert rec["ath"] == pytest.approx(ath, abs=0.01)
        assert rec["px_correction"] == pytest.approx(ath * 0.9, abs=0.01)
        assert rec["px_bear"] == pytest.approx(ath * 0.8, abs=0.01)
        assert rec["pct_from_ath"] == pytest.approx(
            (rec["last_close"] - ath) / ath * 100.0, abs=0.05)
        assert rec["pct_from_ath"] < -20

    def test_round_levels_straddle_the_close(self, store):
        rec = _build(store["root"])["tickers"]["PEAK"]
        assert rec["round_below"] < rec["last_close"] < rec["round_above"]

    @pytest.mark.parametrize("price,below,above", [
        (42.0, 40.0, 45.0),        # step 5 under $50
        (84.2, 80.0, 90.0),        # step 10 under $200
        (201.4, 200.0, 225.0),     # step 25 under $500
        (615.3, 600.0, 650.0),     # step 50 under $1000
        (1234.0, 1200.0, 1300.0),  # step 100 under $5000
        (7100.0, 7000.0, 7500.0),  # step 500 above
        (100.0, 90.0, 110.0),      # exactly on a level: both sides are strict
    ])
    def test_round_level_steps(self, price, below, above):
        assert HP.round_levels(price) == (below, above)

    def test_extremes_carry_pct_and_date(self, store):
        rec = _build(store["root"])["tickers"]["STRK"]
        assert rec["max_dn_1d"]["pct"] < 0
        assert rec["max_up_1d"]["pct"] > 0
        assert date.fromisoformat(rec["max_dn_1d"]["date"]) <= TIP
        assert rec["max_dn_5d"]["pct"] <= rec["max_dn_1d"]["pct"]

    def test_moving_averages(self, store):
        rec = _build(store["root"])["tickers"]["OSC"]
        closes = pd.Series(store["osc"])
        assert rec["ma20"] == pytest.approx(closes.tail(20).mean(), abs=0.01)
        assert rec["ma200"] == pytest.approx(closes.tail(200).mean(), abs=0.01)


class TestGuards:
    def test_a_split_sized_jump_sets_suspect(self, store):
        pack = _build(store["root"])
        assert pack["tickers"]["SPLT"]["suspect"] is True
        assert pack["tickers"]["STRK"]["suspect"] is False

    def test_the_dense_window_starts_after_the_gap(self, store):
        rec = _build(store["root"])["tickers"]["GAPY"]
        assert rec["window_start"] > (TIP - timedelta(days=390)).isoformat()
        assert rec["window_start"] <= TIP.isoformat()

    def test_an_unbroken_history_keeps_its_whole_window(self, store):
        rec = _build(store["root"])["tickers"]["STRK"]
        assert rec["window_start"] == DATES[0].isoformat()

    def test_a_corrupt_parquet_is_skipped_not_fatal(self, store):
        (store["root"] / HP.STORE_REL / "JUNK.parquet").write_bytes(b"not a parquet")
        pack = _build(store["root"])
        assert "JUNK" not in pack["tickers"]
        assert "STRK" in pack["tickers"]

    def test_a_date_column_store_is_read_like_an_indexed_one(self, tmp_path):
        closes = _base_series(40)
        df = pd.DataFrame({
            "date": pd.to_datetime(_weekdays(40)),
            "open": closes, "high": closes, "low": closes, "close": closes,
            "volume": np.full(40, 5_000_000, dtype="int64"),
            "transactions": np.full(40, 1000, dtype="int64"),
        })
        store = tmp_path / HP.STORE_REL
        store.mkdir(parents=True)
        df.to_parquet(store / "COLD.parquet")
        pack = _build(tmp_path)
        assert pack["tickers"]["COLD"]["last_date"] == _weekdays(40)[-1].isoformat()

    def test_the_budget_writes_a_partial_pack(self, store, capsys):
        pack = HP.build_pack(store["root"],
                             cfg={"universe": {"workers": 1, "budget_s": -1}})
        assert pack.get("truncated") is True
        out = capsys.readouterr().out
        assert any(line.startswith("::warning") for line in out.splitlines())


class TestFreshestSourceWins:
    """M12 — per ticker, the store whose LAST BAR IS NEWEST takes the record.

    Scanning data/massive_stock_day alone stamped the 2026-07-28 pack with
    trade_date 2026-07-02 (18 sessions stale) while both curated trees carried
    2026-07-27, so bridge_ok came back False and the whole §2.D device library
    was suppressed for exactly the names the program exists to post about.
    """

    @staticmethod
    def _stale_dates(n: int, back: int):
        """`n` weekdays ending `back` weekdays before the shared TIP."""
        end = TIP
        for _ in range(back):
            end -= timedelta(days=1)
            while end.weekday() >= 5:
                end -= timedelta(days=1)
        return _weekdays(n, end)

    def test_a_stale_massive_record_loses_to_a_fresh_curated_one(self, tmp_path):
        closes = _base_series(60)
        _write(tmp_path, "DUAL", closes, dates=self._stale_dates(60, 18))
        _write(tmp_path, "DUAL", closes, store_rel="data/stocks",
               index_name="Date", with_open=False, dates=_weekdays(60))
        pack = _build(tmp_path)
        assert pack["tickers"]["DUAL"]["last_date"] == TIP.isoformat()
        assert pack["trade_date"] == TIP.isoformat()

    def test_one_fresh_tree_lifts_the_whole_pack_tip(self, tmp_path):
        """The tip is a max over records, so a single current name is enough to
        expose every laggard — which is why M1's per-record gate exists."""
        _write(tmp_path, "OLDONLY", _base_series(60), dates=self._stale_dates(60, 3))
        _write(tmp_path, "FRESH", _base_series(60), store_rel="data/baskets/ohlcv",
               index_name="Date", dates=_weekdays(60))
        pack = _build(tmp_path)
        assert pack["trade_date"] == TIP.isoformat()
        assert pack["tickers"]["OLDONLY"]["last_date"] < TIP.isoformat()

    def test_a_ticker_only_in_a_curated_tree_is_scanned(self, tmp_path):
        _write(tmp_path, "BASKETONLY", _base_series(60),
               store_rel="data/baskets/ohlcv", index_name="Date")
        pack = _build(tmp_path)
        assert "BASKETONLY" in pack["tickers"]

    def test_a_stocks_shaped_frame_without_open_is_read(self, tmp_path):
        """data/stocks carries no `open`; the pack's stats only need closes."""
        _write(tmp_path, "NOOPEN", _base_series(60), store_rel="data/stocks",
               index_name="Date", with_open=False)
        rec = _build(tmp_path)["tickers"]["NOOPEN"]
        assert rec["last_date"] == TIP.isoformat()
        assert rec["rsi14"] is not None and rec["ma20"] is not None

    def test_the_store_universe_is_a_union(self, tmp_path):
        _write(tmp_path, "AAA", _base_series(30))
        _write(tmp_path, "AAA", _base_series(30), store_rel="data/stocks",
               index_name="Date", with_open=False)
        _write(tmp_path, "BBB", _base_series(30), store_rel="data/baskets/ohlcv",
               index_name="Date")
        found = HP.store_universe(tmp_path)
        assert set(found) == {"AAA", "BBB"}
        assert [p.parent.name for p in found["AAA"]] == ["stocks", "massive_stock_day"]

    def test_polygon_test_symbols_never_enter_the_universe(self, tmp_path):
        """ZAZZT held adv_rank 1 in the shipped pack on a $615B fake ADV."""
        _write(tmp_path, "STRK", _base_series(60))
        for junk in ("ZAZZT", "ZVZZT", "ZXZZT"):
            _write(tmp_path, junk, _base_series(60), volume=50_000_000)
        assert set(HP.store_universe(tmp_path)) == {"STRK"}
        pack = _build(tmp_path)
        assert set(pack["tickers"]) == {"STRK"}
        assert pack["tickers"]["STRK"]["adv_rank"] == 1

    def test_a_record_far_behind_the_tip_is_dropped(self, tmp_path):
        _write(tmp_path, "FRESH", _base_series(60))
        _write(tmp_path, "NEARLY", _base_series(60), dates=self._stale_dates(60, 9))
        _write(tmp_path, "DEAD", _base_series(60), dates=self._stale_dates(60, 40))
        pack = _build(tmp_path)
        assert set(pack["tickers"]) == {"FRESH", "NEARLY"}
        assert sorted(r["adv_rank"] for r in pack["tickers"].values()) == [1, 2]

    def test_the_lag_ceiling_is_configurable(self, tmp_path):
        _write(tmp_path, "FRESH", _base_series(60))
        _write(tmp_path, "NEARLY", _base_series(60), dates=self._stale_dates(60, 9))
        pack = _build(tmp_path, max_lag_weekdays=3)
        assert set(pack["tickers"]) == {"FRESH"}

    def test_the_shipped_budget_matches_the_config(self):
        from pathlib import Path as _Path

        cfg = HT.load_config(_Path(__file__).resolve().parent.parent)
        assert cfg["universe"]["budget_s"] == HP.DEFAULT_BUDGET_S == 240
        assert (cfg["universe"]["max_lag_weekdays"]
                == HP.DEFAULT_MAX_LAG_WEEKDAYS
                == HT.DEFAULTS["universe"]["max_lag_weekdays"] == 10)


class TestJoins:
    @staticmethod
    def _reference(root, rows):
        path = root / HP.REFERENCE_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).set_index("ticker").to_parquet(path)

    @staticmethod
    def _earnings(root, rows):
        path = root / HP.EARNINGS_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).set_index("ticker").to_parquet(path)

    def test_mcap_and_shares(self, store):
        root = store["root"]
        self._reference(root, [{"ticker": "STRK", "gics_sector": "Information Technology",
                                "market_cap_usd": 3.0e11, "asof": TIP.isoformat()}])
        pack = _build(root)
        rec = pack["tickers"]["STRK"]
        assert rec["mcap_usd"] == 300_000_000_000
        assert rec["shares_est"] == pytest.approx(3.0e11 / rec["last_close"], rel=1e-6)
        assert pack["sources"]["mcap_asof"] == TIP.isoformat()
        assert pack["tickers"]["OSC"]["mcap_usd"] is None

    def test_shares_est_is_withheld_when_the_asof_lags_the_store(self, store):
        """C1 — shares = mcap / close is only an identity on ONE session.

        A 2026-07-27 reference cap divided by a 2026-07-02 close inflated JPM's
        share count 6.5%, and the mcap-milestone detector then manufactured a
        "$JPM just crossed $1 trillion" post at an actual $942B. No alignment,
        no share count — and the milestone branch dies with it, by design.
        """
        root = store["root"]
        older = (TIP - timedelta(days=25)).isoformat()
        self._reference(root, [{"ticker": "STRK", "gics_sector": "Information Technology",
                                "market_cap_usd": 3.0e11, "asof": older}])
        pack = _build(root)
        rec = pack["tickers"]["STRK"]
        assert pack["sources"]["mcap_asof"] == older
        assert rec["mcap_usd"] == 300_000_000_000     # honest on its own asof
        assert rec["shares_est"] is None
        # …and the detector that depends on it simply never fires.
        now = datetime(TIP.year, TIP.month, TIP.day, 15, 10, tzinfo=timezone.utc)
        quotes = {"STRK": {"price": rec["last_close"] * 1.4,
                           "prev_close": rec["last_close"],
                           "change_pct": 40.0,
                           "ts_ms": int(now.timestamp() * 1000), "source": "quotes"}}
        events = HT.detect_events(quotes, pack=pack, now=now, cfg=HT.DEFAULTS)
        assert [e for e in events if e.facts.get("kind") == "mcap"] == []

    def test_shares_est_is_present_when_the_dates_agree(self, store):
        root = store["root"]
        self._reference(root, [{"ticker": "STRK", "gics_sector": "Information Technology",
                                "market_cap_usd": 3.0e11, "asof": TIP.isoformat()}])
        rec = _build(root)["tickers"]["STRK"]
        assert rec["shares_est"] == pytest.approx(3.0e11 / rec["last_close"], rel=1e-6)

    def test_earnings(self, store):
        root = store["root"]
        when = (TIP + timedelta(days=9)).isoformat()
        self._earnings(root, [{"ticker": "STRK", "next_date": when,
                               "next_time": "time-after-hours",
                               "eps_forecast": 1.2, "surprises_json": "[]",
                               "as_of": TIP.isoformat()}])
        pack = _build(root)
        assert pack["tickers"]["STRK"]["earn_next_date"] == when
        assert pack["tickers"]["STRK"]["earn_next_time"] == "time-after-hours"
        assert pack["sources"]["earnings_asof"] == TIP.isoformat()

    def test_missing_join_files_are_not_fatal(self, store):
        pack = _build(store["root"])
        assert pack["sources"]["mcap_asof"] is None
        assert pack["tickers"]["STRK"]["mcap_usd"] is None
        assert pack["tickers"]["STRK"]["earn_next_date"] is None


class TestRadarHandoff:
    """The pack must satisfy the detectors that consume it."""

    def test_bridge_ok_against_a_freshly_built_pack(self, store):
        pack = _build(store["root"])
        # The synthetic tip IS the most recent weekday, so a radar running on
        # the next session bridges cleanly.
        nxt = TIP + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        now = datetime(nxt.year, nxt.month, nxt.day, 15, 10, tzinfo=timezone.utc)
        assert HT.bridge_ok(pack, now) is True
        stale = datetime(nxt.year, nxt.month, nxt.day, 15, 10,
                         tzinfo=timezone.utc) + timedelta(days=30)
        assert HT.bridge_ok(pack, stale) is False

    def test_detectors_run_against_the_real_pack(self, store):
        pack = _build(store["root"])
        rec = pack["tickers"]["STRK"]
        now = datetime(TIP.year, TIP.month, TIP.day, 15, 10, tzinfo=timezone.utc)
        quotes = {"STRK": {"price": rec["last_close"] * 0.92,
                           "prev_close": rec["last_close"],
                           "change_pct": -8.0,
                           "ts_ms": int(now.timestamp() * 1000),
                           "source": "quotes"}}
        rec["adv_rank"] = 1
        events = HT.detect_events(quotes, pack=pack, now=now, cfg=HT.DEFAULTS)
        triggers = {e.trigger for e in events}
        assert "mover_drop" in triggers
        mover = [e for e in events if e.trigger == "mover_drop"][0]
        assert mover.facts["streak_extends"]["len_today"] == 9
        assert math.isclose(mover.facts["pct"], -8.0)

    def test_no_nan_or_inf_leaks_into_the_pack(self, store):
        blob = json.dumps(_build(store["root"]))
        assert "NaN" not in blob and "Infinity" not in blob


class TestEntryPoint:
    def test_main_never_raises_and_exits_zero(self, monkeypatch, tmp_path):
        monkeypatch.setattr(HP, "write_pack",
                            lambda *a, **k: {"error": "store absent"})
        assert HP.main() == 0


# ─────────────────────────────────────────────────────────────────────────────
# chart_render's no-pandas fallback (the ubuntu radar host runs pyarrow only)
# ─────────────────────────────────────────────────────────────────────────────

class _BlockPandas:
    """Meta-path hook that makes `import pandas` raise, as on the radar host."""

    def find_module(self, name, path=None):  # pragma: no cover - py<3.12 shim
        return self if name == "pandas" or name.startswith("pandas.") else None

    def find_spec(self, name, path=None, target=None):
        if name == "pandas" or name.startswith("pandas."):
            raise ImportError("pandas blocked (radar-host simulation)")
        return None

    def load_module(self, name):  # pragma: no cover - py<3.12 shim
        raise ImportError("pandas blocked (radar-host simulation)")


class TestChartRenderPyarrowParity:
    """The pyarrow fallback must return EXACTLY what the pandas path returns.

    The Hot Tape radar lane installs pyyaml+requests+pyarrow and no pandas, so
    load_closes/load_ohlcv fall back to _load_*_pyarrow there. A silent
    divergence (ordering, NaN handling, the open proxy) would draw a wrong
    candle on a posted card — pin byte-equality on both store shapes.
    """

    @staticmethod
    def _write_stores(root):
        import numpy as _np
        days = pd.bdate_range(end=pd.Timestamp(date.today()), periods=40)
        rng = _np.random.default_rng(7)
        closes = 100 + _np.cumsum(rng.normal(0, 1.0, len(days)))
        # massive-style: lowercase `date` index name, full OHLCV + a NaN row
        massive = root / "data" / "massive_stock_day"
        massive.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame({
            "open": closes - 0.5, "high": closes + 1.0, "low": closes - 1.0,
            "close": closes, "volume": (rng.integers(1_000, 9_000, len(days))).astype("int64"),
            "transactions": (rng.integers(10, 90, len(days))).astype("int64"),
        }, index=pd.Index(days, name="date"))
        df.loc[df.index[5], "close"] = float("nan")
        df.to_parquet(massive / "MASS.parquet")
        # stocks-style: capitalized `Date` index name, NO open column
        stocks = root / "data" / "stocks"
        stocks.mkdir(parents=True, exist_ok=True)
        df2 = pd.DataFrame({
            "close": closes, "high": closes + 0.8, "low": closes - 0.8,
            "volume": (rng.integers(1_000, 9_000, len(days))).astype("int64"),
        }, index=pd.Index(days, name="Date"))
        df2.to_parquet(stocks / "STCK.parquet")

    def test_fallback_matches_pandas_for_both_loaders(self, tmp_path, monkeypatch):
        import sys
        from engine.marketing import chart_render as CR

        self._write_stores(tmp_path)
        # The massive store is opt-in (see TestMassiveStoreIsOptIn); this parity
        # check is about the pyarrow reader, so it asks for both trees.
        wide = CR.HOT_TAPE_PRICE_SUBDIRS

        def _snapshot():
            return {
                "closes_mass": CR.load_closes("MASS", tmp_path, n=30, subdirs=wide),
                "closes_stck": CR.load_closes("STCK", tmp_path, n=30, subdirs=wide),
                "ohlcv_mass": CR.load_ohlcv("MASS", tmp_path, n=30, subdirs=wide),
                "ohlcv_stck": CR.load_ohlcv("STCK", tmp_path, n=30, subdirs=wide),
            }

        with_pandas = _snapshot()
        assert all(v is not None for v in with_pandas.values())

        blocker = _BlockPandas()
        saved = {k: v for k, v in sys.modules.items()
                 if k == "pandas" or k.startswith("pandas.")}
        try:
            for k in saved:
                monkeypatch.delitem(sys.modules, k, raising=False)
            monkeypatch.setattr(sys, "meta_path", [blocker] + sys.meta_path)
            without_pandas = _snapshot()
        finally:
            sys.modules.update(saved)

        for key, expect in with_pandas.items():
            got = without_pandas[key]
            assert got is not None, key
            assert got == expect, f"{key}: pyarrow fallback diverged from pandas"


class TestMassiveStoreIsOptIn:
    """M13 — data/massive_stock_day belongs to the Hot Tape radar, not to
    every chart_render caller.

    The store is neither split-adjusted nor kept current (18 sessions stale on
    2026-07-28), so putting it in the module default silently changed the bars
    under the nightly cards, the brain chart and the watchlist grid to answer a
    question only the radar was asking.
    """

    @staticmethod
    def _massive_only(root):
        import numpy as _np
        days = pd.bdate_range(end=pd.Timestamp(date.today()), periods=40)
        closes = 100 + _np.cumsum(_np.random.default_rng(3).normal(0, 1.0, len(days)))
        massive = root / "data" / "massive_stock_day"
        massive.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({
            "open": closes - 0.5, "high": closes + 1.0, "low": closes - 1.0,
            "close": closes, "volume": _np.full(len(days), 1000, dtype="int64"),
        }, index=pd.Index(days, name="date")).to_parquet(massive / "WIDE.parquet")

    def test_the_default_order_stops_at_the_curated_trees(self, tmp_path):
        from engine.marketing import chart_render as CR

        self._massive_only(tmp_path)
        assert CR._PRICE_SUBDIRS == ("data/baskets/ohlcv", "data/stocks")
        assert CR._price_parquet("WIDE", tmp_path) is None
        assert CR.load_closes("WIDE", tmp_path, n=30) is None
        assert CR.load_ohlcv("WIDE", tmp_path, n=30) is None
        assert CR.load_ohlcv_windowed("WIDE", tmp_path) is None

    def test_the_hot_tape_order_reaches_it(self, tmp_path):
        from engine.marketing import chart_render as CR

        self._massive_only(tmp_path)
        wide = CR.HOT_TAPE_PRICE_SUBDIRS
        assert wide == (*CR._PRICE_SUBDIRS, "data/massive_stock_day")
        assert CR._price_parquet("WIDE", tmp_path, wide) is not None
        assert CR.load_closes("WIDE", tmp_path, n=30, subdirs=wide) is not None
        assert CR.load_ohlcv("WIDE", tmp_path, n=30, subdirs=wide) is not None
        assert CR.load_ohlcv_windowed("WIDE", tmp_path, subdirs=wide) is not None

    def test_the_radar_is_the_only_caller_that_opts_in(self):
        """One grep, one lane: if a second module wants the wide tail it has to
        say so here, in a test, rather than by moving the module default."""
        import re as _re
        from pathlib import Path as _Path

        root = _Path(__file__).resolve().parent.parent
        callers = set()
        for path in list((root / "engine").rglob("*.py")) + \
                list((root / "scripts").rglob("*.py")) + list((root / "app").rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if _re.search(r"HOT_TAPE_PRICE_SUBDIRS|subdirs\s*=", text):
                callers.add(path.relative_to(root).as_posix())
        callers.discard("engine/marketing/chart_render.py")
        assert callers == {"scripts/hot_tape_radar.py"}, callers
