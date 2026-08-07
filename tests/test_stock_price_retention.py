"""Retention fetch-set fix for collectors.sector_holdings.StockPriceAdapter
(data/stocks — the US single-stock deep-history store).

2026-08-03 adjudication: the adapter's fetch set used to be JUST top10_union() — the
union of the CURRENT top-20 holdings across the 11 sector SPDRs. A name that exited
every fund's top-20 silently left the fetch set and its parquet froze forever (measured:
QCOM/HOOD/MRVL/CVNA/HON/WDC froze 10-24 days at their exit dates; SATS 46 days), while
scripts/build_stock_library.py's universe() kept preferring the frozen deep store over
fresher breadth caches — nothing downstream ever noticed. The fix is
_fetch_universe(): today's top-N union PLUS every ticker still on disk, minus names
confirmed dead — so a dropped name keeps being fetched for as long as its parquet
exists. A freeze old enough that the cheap period='1mo' window (~30 calendar days of
reach) can no longer bridge back to the last stored bar routes to period='max' instead
(_needs_full's new stale-tip check, _MAX_WINDOW_BRIDGE_DAYS=21) so a resumed fetch
never strands an interior hole (the SATS class, 46 days frozen).

Pins (network-free — the download layer is stubbed; no wall-clock in any assertion):
1. _fetch_universe: union/dead-exclusion/union-wins-over-dead/sort — pure, no I/O.
2. _dead_tickers(): absent/corrupt/column-missing file -> frozenset(); a real file's
   ticker column is read and de-duplicated.
3. StockPriceAdapter.stored_series(): stems of data/stocks/*.parquet, skips leading-
   underscore stems, empty when the store dir does not exist.
4. _needs_full(ticker, today=...): the pre-existing missing/shallow/volume-sparse
   checks are unchanged; the NEW stale-tip bridge fires only when those three already
   passed, exactly at >_MAX_WINDOW_BRIDGE_DAYS calendar days before the injected
   `today` (boundary pinned at 21 not-flagged / 22 flagged).
5. One fetch()-level integration test: a stored-but-dropped ticker lands in the 1mo
   group, a >21d-stale stored ticker lands in the max group, a dead stored ticker is
   never requested at all, and the 0.7 completeness guard's denominator is the
   retention-expanded union (not the bare top10_union() count).
6. _report_missing_symbols (2026-08-06): the requested-vs-returned reconciliation the
   retention fetch shipped without — a bare line-start ::warning splitting the missing
   set into in-union (live provider failure) vs retained-off-union (delisted/renamed
   candidates, #4616/#4622), silent when nothing is missing, and actually REACHED by
   fetch() on the run that then dies on the 0.7 floor.

Run: .venv/bin/python -m pytest tests/test_stock_price_retention.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import sector_holdings as sh  # noqa: E402
from lib import config, store  # noqa: E402


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """The established idiom (tests/test_upsert_basis_guard.py): point lib.config's
    data_dir() at a tmp path so every store read/write in the module under test is
    hermetic — no repo state, no wall clock."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# 1. _fetch_universe — pure, no I/O
# ---------------------------------------------------------------------------


def test_fetch_universe_is_union_of_current_and_stored():
    out = sh._fetch_universe(["AAPL", "MSFT"], ["MSFT", "NVDA"], frozenset())
    assert out == ["AAPL", "MSFT", "NVDA"]


def test_fetch_universe_excludes_dead_names_from_the_stored_side():
    out = sh._fetch_universe(["AAPL"], ["AAPL", "DEADCO"], frozenset({"DEADCO"}))
    assert out == ["AAPL"]


def test_fetch_universe_union_side_wins_over_dead():
    # A dead-registry name STILL in the current top-N union is fetched anyway (ticker
    # reuse safety) — the union side always wins over the dead exclusion.
    out = sh._fetch_universe(["AAPL", "DEADCO"], [], frozenset({"DEADCO"}))
    assert out == ["AAPL", "DEADCO"]


def test_fetch_universe_is_sorted_and_deduplicated():
    out = sh._fetch_universe(["ZZZ", "AAPL", "AAPL"], ["MSFT", "ZZZ"], frozenset())
    assert out == ["AAPL", "MSFT", "ZZZ"]


def test_fetch_universe_empty_inputs_yield_empty():
    assert sh._fetch_universe([], [], frozenset()) == []


# ---------------------------------------------------------------------------
# 2. _dead_tickers()
# ---------------------------------------------------------------------------


def test_dead_tickers_absent_file_returns_empty(data_dir):
    assert sh._dead_tickers() == frozenset()


def test_dead_tickers_reads_and_dedupes_ticker_column(data_dir):
    edgar = data_dir / "edgar"
    edgar.mkdir()
    pd.DataFrame({
        "ticker": ["AAA", "BBB", "AAA"],
        "date": [pd.Timestamp("2026-01-01")] * 3,
        "close": [0.0, 0.0, 0.0],
        "source": ["imputed_bankruptcy"] * 3,
    }).to_parquet(edgar / "dead_name_prices.parquet")
    assert sh._dead_tickers() == frozenset({"AAA", "BBB"})


def test_dead_tickers_missing_ticker_column_returns_empty(data_dir):
    edgar = data_dir / "edgar"
    edgar.mkdir()
    pd.DataFrame({"foo": [1, 2]}).to_parquet(edgar / "dead_name_prices.parquet")
    assert sh._dead_tickers() == frozenset()


def test_dead_tickers_corrupt_file_returns_empty(data_dir):
    edgar = data_dir / "edgar"
    edgar.mkdir()
    (edgar / "dead_name_prices.parquet").write_bytes(b"not a parquet file")
    assert sh._dead_tickers() == frozenset()  # must not raise


# ---------------------------------------------------------------------------
# 3. StockPriceAdapter.stored_series()
# ---------------------------------------------------------------------------


def test_stored_series_lists_stocks_store_stems(data_dir):
    d = data_dir / "stocks"
    d.mkdir()
    for t in ["MSFT", "AAPL"]:
        pd.DataFrame({"close": [1.0]}, index=pd.bdate_range("2026-01-01", periods=1)).to_parquet(
            d / f"{t}.parquet")
    a = sh.StockPriceAdapter()
    assert a.stored_series() == ["AAPL", "MSFT"]  # sorted


def test_stored_series_empty_when_dir_absent(data_dir):
    a = sh.StockPriceAdapter()
    assert a.stored_series() == []


def test_stored_series_skips_underscore_stems(data_dir):
    d = data_dir / "stocks"
    d.mkdir()
    pd.DataFrame({"close": [1.0]}, index=pd.bdate_range("2026-01-01", periods=1)).to_parquet(
        d / "AAPL.parquet")
    (d / "_manifest.parquet").write_bytes(b"x")
    a = sh.StockPriceAdapter()
    assert a.stored_series() == ["AAPL"]


# ---------------------------------------------------------------------------
# 4. _needs_full(ticker, today=...) — injected today, no wall clock
# ---------------------------------------------------------------------------


def _seed(ticker: str, end: str, n: int = 400, volume_frac: float = 1.0) -> None:
    """Deep-enough-to-pass-the-shallow-check history ending exactly on `end`, ready
    for the stale-tip bridge check specifically. volume_frac<1 sparsens the tail of
    the volume column to exercise the pre-existing volume-share trigger."""
    idx = pd.date_range(end=end, periods=n, freq="D")
    if volume_frac >= 1.0:
        vol = 1_000_000
    else:
        cut = int(n * (1 - volume_frac))
        vol = [None] * cut + [1_000_000] * (n - cut)
    df = pd.DataFrame({"close": 100.0, "high": 101.0, "low": 99.0, "volume": vol}, index=idx)
    df.to_parquet(store._path("stocks", ticker))


def test_needs_full_false_when_deep_volume_rich_and_current(data_dir):
    _seed("AAPL", end="2026-08-03", n=400)
    a = sh.StockPriceAdapter()
    assert a._needs_full("AAPL", today=pd.Timestamp("2026-08-03")) is False


def test_needs_full_true_when_stale_tip_past_the_bridge(data_dir):
    _seed("QCOM", end="2026-06-01", n=400)  # deep + volume-rich, but frozen
    a = sh.StockPriceAdapter()
    assert a._needs_full("QCOM", today=pd.Timestamp("2026-08-03")) is True


def test_needs_full_boundary_21_days_not_flagged(data_dir):
    _seed("EDGE21", end="2026-07-13", n=400)  # exactly 21 calendar days before today
    a = sh.StockPriceAdapter()
    assert a._needs_full("EDGE21", today=pd.Timestamp("2026-08-03")) is False


def test_needs_full_boundary_22_days_flagged(data_dir):
    _seed("EDGE22", end="2026-07-12", n=400)  # 22 calendar days before today
    a = sh.StockPriceAdapter()
    assert a._needs_full("EDGE22", today=pd.Timestamp("2026-08-03")) is True


def test_needs_full_true_when_missing(data_dir):
    a = sh.StockPriceAdapter()
    assert a._needs_full("NOPE", today=pd.Timestamp("2026-08-03")) is True


def test_needs_full_true_when_shallow(data_dir):
    _seed("ISRG", end="2026-08-03", n=40)  # below _DEEP_MIN_ROWS
    a = sh.StockPriceAdapter()
    assert a._needs_full("ISRG", today=pd.Timestamp("2026-08-03")) is True


def test_needs_full_true_when_volume_sparse(data_dir):
    _seed("SPARSE", end="2026-08-03", n=400, volume_frac=0.5)  # current tip, but half volume missing
    a = sh.StockPriceAdapter()
    assert a._needs_full("SPARSE", today=pd.Timestamp("2026-08-03")) is True


def test_needs_full_existing_checks_take_priority_over_the_bridge(data_dir):
    # A shallow stub with an OLD tip must still return True via the shallow check
    # (order/semantics of the pre-existing checks stay untouched by the new one).
    _seed("STUB", end="2026-06-01", n=40)
    a = sh.StockPriceAdapter()
    assert a._needs_full("STUB", today=pd.Timestamp("2026-08-03")) is True


def test_needs_full_true_for_tz_aware_index_without_raising(data_dir):
    # Defensive tip parsing (2026-08-03 review fix): _needs_full is called from a
    # bare list comprehension in fetch() with no per-ticker try/except, so a stray
    # tz-aware stored index must degrade to True (routed to heal), never raise and
    # kill the run for every other ticker.
    idx = pd.date_range(end="2020-01-01", periods=400, freq="D", tz="UTC")
    df = pd.DataFrame({"close": 100.0, "high": 101.0, "low": 99.0, "volume": 1_000_000}, index=idx)
    df.to_parquet(store._path("stocks", "TZAWARE"))
    a = sh.StockPriceAdapter()
    assert a._needs_full("TZAWARE", today=pd.Timestamp("2026-08-03")) is True


def test_needs_full_true_for_all_nat_index_without_raising(data_dir):
    idx = pd.DatetimeIndex([pd.NaT] * 400)
    df = pd.DataFrame({"close": 100.0, "high": 101.0, "low": 99.0, "volume": 1_000_000}, index=idx)
    df.to_parquet(store._path("stocks", "ALLNAT"))
    a = sh.StockPriceAdapter()
    assert a._needs_full("ALLNAT", today=pd.Timestamp("2026-08-03")) is True


# ---------------------------------------------------------------------------
# 5. fetch() integration — retention set, heal-group split, dead exclusion,
#    0.7 guard denominator
# ---------------------------------------------------------------------------


def _yf_multi(frames_by_ticker: dict) -> pd.DataFrame:
    """Assemble a MultiIndex (ticker, field) frame like yf.download(group_by='ticker').
    A ticker absent from `frames_by_ticker` is absent from the result entirely (the
    KeyError this produces on lookup is exactly how _pull() skips a dropped name)."""
    parts = {}
    for t, df in frames_by_ticker.items():
        for c in df.columns:
            parts[(t, c)] = df[c]
    if not parts:
        return pd.DataFrame()
    out = pd.DataFrame(parts)
    out.columns = pd.MultiIndex.from_tuples(out.columns)
    return out


def _resp(stored: pd.DataFrame, tail: int) -> pd.DataFrame:
    """A raw yfinance-shaped window response sliced from the STORED frame's own tail
    (same basis — never trips the rebase/basis-shift guard, which is out of scope
    here)."""
    base = stored.tail(tail)
    close = base["close"].to_numpy()
    return pd.DataFrame({"Close": close, "High": close, "Low": close,
                         "Volume": 1e6}, index=base.index)


def test_fetch_retention_heal_split_and_zero_point_seven_guard_use_the_union(data_dir, monkeypatch, capsys):
    today = pd.Timestamp.now().normalize()  # only used to seed "genuinely current"
    # fixtures below — no assertion anywhere depends on knowing what "now" is.

    live1 = pd.DataFrame(
        {"close": 100.0, "high": 101.0, "low": 99.0, "volume": 1_000_000},
        index=pd.date_range(end=today, periods=400, freq="D"))
    live1.to_parquet(store._path("stocks", "LIVE1"))
    live2 = live1.copy()
    live2.to_parquet(store._path("stocks", "LIVE2"))
    dropped_fresh = live1.copy()
    dropped_fresh.to_parquet(store._path("stocks", "DROPPED_FRESH"))

    dropped_stale = pd.DataFrame(
        {"close": 50.0, "high": 51.0, "low": 49.0, "volume": 1_000_000},
        index=pd.date_range(end="2020-01-01", periods=400, freq="D"))  # always >21d stale
    dropped_stale.to_parquet(store._path("stocks", "DROPPED_STALE"))

    dropped_dead = pd.DataFrame(
        {"close": 10.0, "high": 11.0, "low": 9.0, "volume": 1_000_000},
        index=pd.date_range(end="2020-01-01", periods=10, freq="D"))
    dropped_dead.to_parquet(store._path("stocks", "DROPPED_DEAD"))

    monkeypatch.setattr(sh, "top10_union", lambda: ["LIVE1", "LIVE2"])
    monkeypatch.setattr(sh, "_dead_tickers", lambda: frozenset({"DROPPED_DEAD"}))

    calls: list[tuple[str, list[str]]] = []

    def fake_download(batch, period):
        calls.append((period, list(batch)))
        if period == "1mo":
            # LIVE2 silently missing from the response (simulates a yfinance drop).
            return _yf_multi({
                "LIVE1": _resp(live1, 20),
                "DROPPED_FRESH": _resp(dropped_fresh, 20),
            })
        # period == "max": DROPPED_STALE silently missing too.
        return _yf_multi({})

    a = sh.StockPriceAdapter()
    monkeypatch.setattr(a, "_download", fake_download)

    with pytest.raises(RuntimeError) as exc:
        a.fetch(full_history=False)

    # tickers = _fetch_universe(["LIVE1","LIVE2"], stored, dead) =
    #   {LIVE1,LIVE2,DROPPED_FRESH,DROPPED_STALE} (DROPPED_DEAD excluded) -> 4 names.
    assert [c[0] for c in calls] == ["1mo", "max"]
    period_1mo_batch, period_max_batch = calls[0][1], calls[1][1]
    assert set(period_1mo_batch) == {"LIVE1", "LIVE2", "DROPPED_FRESH"}, (
        "a stored-but-dropped-from-the-union ticker (DROPPED_FRESH) must still be "
        "requested, and land in the cheap 1mo group since it is fresh")
    assert set(period_max_batch) == {"DROPPED_STALE"}, (
        "a >21d-stale stored ticker must be routed to the full-history group")
    assert "DROPPED_DEAD" not in period_1mo_batch and "DROPPED_DEAD" not in period_max_batch, (
        "a dead-registry stored ticker must never be requested at all")

    # Only LIVE1 + DROPPED_FRESH actually returned data: 2/4. Against the retention
    # union (4) that is below the 0.7 floor (2 < 2.8) and must raise; against the bare
    # top10_union() count (2) it would NOT (2 >= 1.4) — the message pins which
    # denominator actually fired.
    assert "2/4" in str(exc.value)

    # The reconciliation must have ALREADY printed by the time the floor raised: a
    # run that dies on the floor is exactly the run whose per-name detail is worth
    # having. This is the call-site pin — deleting _report_missing_symbols' call in
    # fetch() reds here, not just in the unit tests below (a unit-only pin would be
    # vacuous about whether fetch() reaches it at all).
    ann = [ln for ln in capsys.readouterr().out.splitlines()
           if ln.startswith("::warning title=stocks collector missing symbols::")]
    assert len(ann) == 1, "fetch() must emit exactly one reconciliation annotation"
    # LIVE2 (in the union) and DROPPED_STALE (retained, off-union) both returned
    # nothing — one from each class, so the split counts are not interchangeable.
    assert "2 of 4 requested" in ann[0]
    assert "1 in today's top-N union" in ann[0]
    assert "1 retained off-union" in ann[0]
    body = ann[0].split("candidates): ", 1)[1]
    assert {t.strip() for t in body.split(",")} == {"DROPPED_STALE", "LIVE2"}


# ---------------------------------------------------------------------------
# 6. _report_missing_symbols — requested-vs-returned reconciliation (2026-08-06)
# ---------------------------------------------------------------------------


def test_report_missing_splits_union_and_retained(capsys):
    missing = sh._report_missing_symbols(
        ["AAPL", "QCOM", "SATS"], {"AAPL"}, ["AAPL", "QCOM"])
    assert missing == ["QCOM", "SATS"]
    line = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    assert len(line) == 1
    # Line-start bare print, per the annotation law (a logger-prefixed line is
    # silently dropped by GitHub — the defect class tests/test_gh_annotation_line_start
    # pins repo-wide).
    assert line[0].startswith("::warning title=stocks collector missing symbols::")
    assert "2 of 3 requested" in line[0]
    assert "1 in today's top-N union" in line[0]      # QCOM
    assert "1 retained off-union" in line[0]          # SATS


def test_report_missing_silent_when_everything_returned(capsys):
    assert sh._report_missing_symbols(["AAPL", "MSFT"], {"AAPL", "MSFT"}, ["AAPL"]) == []
    assert not [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]


def test_report_missing_all_retained_reports_zero_union(capsys):
    # The retention set's own class: nothing the desk currently holds is missing, but
    # four names kept alive purely because they still have a store returned nothing —
    # the delisted/renamed candidate signature, and the one the split exists to name.
    missing = sh._report_missing_symbols(
        ["AAPL", "QCOM", "HOOD", "MRVL", "SATS"], {"AAPL"}, ["AAPL"])
    assert missing == ["QCOM", "HOOD", "MRVL", "SATS"]
    line = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")][0]
    assert "0 in today's top-N union" in line
    assert "4 retained off-union" in line


def test_report_missing_preserves_requested_order_and_caps_display_at_15(capsys):
    # T1/T10/T11... share a prefix, so a substring check would pass even if T1 were
    # dropped from the shown set (it matches inside "T10"). Assert the exact token
    # list, the same trap tests/test_collector_freshness_disclosure.py pins for the
    # yahoo sibling.
    requested = [f"T{i}" for i in range(20)]
    missing = sh._report_missing_symbols(requested, set(), [])
    assert missing == requested          # requested order, not set order
    line = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")][0]
    assert "20 of 20 requested" in line
    assert "+5 more" in line
    body = line.split("candidates): ", 1)[1].split(", +", 1)[0]
    assert [t.strip() for t in body.split(",")] == requested[:15]


def test_report_missing_accepts_a_frames_dict_as_returned(capsys):
    # fetch() passes the frames DICT itself, not a key set — set(dict) must be the
    # keys. A regression to set(frames.values()) would make every ticker read missing.
    frames = {"AAPL": pd.DataFrame({"close": [1.0]}), "MSFT": pd.DataFrame({"close": [2.0]})}
    assert sh._report_missing_symbols(["AAPL", "MSFT"], frames, ["AAPL", "MSFT"]) == []
    assert not [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
