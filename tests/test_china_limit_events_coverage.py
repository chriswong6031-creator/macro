"""limit_events must reach back to each name's store start — no SILENT per-name holes.

data/china_microstructure/limit_events.parquet is built once by
scripts/backfill_china_limit_tape.py and then only ever APPENDED to, over a ~20-session
window, by scripts/build_china_microstructure.build_increment.  A ticker whose parquet lands
in data/china_stocks_raw after that one-shot run could therefore only ever receive a 20-day
tail — and no row at all when it had no limit event inside it.  Measured 2026-08-08: the raw
store grew 1,592 -> 1,842 names on 2026-08-05 and 314 names (264 with no row whatsoever) held
no pre-2026-07 history, while limit_tape's own ``backfill`` flag read True for all 3,751
market-days — a per-MARKET-DAY column that can never express a per-NAME hole.

Pinned here, fully offline on synthetic OHLCV:
  • a store-newcomer's FULL history is detected and lands in limit_events;
  • the tape's aggregation is unchanged by it (its historical rows keep the universe that
    produced them — the hole is DISCLOSED, not silently papered over);
  • the hole is disclosed per name in the site packet and as a GitHub annotation;
  • a name already known to the store is NOT re-scanned from 2011 every night;
  • an unreadable/missing events store is a cold start, not 1,800 newcomers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_china_microstructure as bcm


# ── fixtures ──────────────────────────────────────────────────────────────────

# The synthetic universe: 400 sessions ending on a fixed date, so the builder's own
# auto-detected scan date and its NIGHTLY_LOOKBACK window are deterministic.
SERIES_DAYS = 400
SERIES_END = "2026-08-07"
BARS = pd.bdate_range(end=SERIES_END, periods=SERIES_DAYS)
FIRST_BAR = BARS[0]
WINDOW_FLOOR = pd.Timestamp(SERIES_END) - pd.Timedelta(days=bcm.NIGHTLY_LOOKBACK * 2)


def _limit_up_series() -> pd.DataFrame:
    """A main-board name that seals the +10% limit on EVERY bar (unambiguous events)."""
    close = [round(10.0 * (1.10 ** i), 2) for i in range(SERIES_DAYS)]
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": [1_000] * SERIES_DAYS}, index=BARS)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A tmp raw store + tmp microstructure outputs, wired into the builder's constants."""
    raw = tmp_path / "china_stocks_raw"
    out = tmp_path / "china_microstructure"
    site = tmp_path / "site"
    raw.mkdir(parents=True)
    monkeypatch.setattr(bcm, "ROOT", tmp_path)
    monkeypatch.setattr(bcm, "RAW_DIR", raw)
    monkeypatch.setattr(bcm, "OUT_DIR", out)
    monkeypatch.setattr(bcm, "TAPE_PATH", out / "limit_tape.parquet")
    monkeypatch.setattr(bcm, "EVENTS_PATH", out / "limit_events.parquet")
    monkeypatch.setattr(bcm, "SITE_DIR", site)
    monkeypatch.setattr(bcm, "JSON_PATH", site / "microstructure.json")
    return tmp_path, raw, out


def _seed_events(out: Path, tickers: list[str], date: str = SERIES_END) -> None:
    """An existing events store — what makes a NEW ticker a store-newcomer."""
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"date": pd.Timestamp(date), "ticker": t, "board": "main",
                   "limit_width": 10.0, "event": "sealed_up", "lianban_count": 1,
                   "close_off_limit_pct": 0.0} for t in tickers]).to_parquet(
        out / "limit_events.parquet", index=False)


# ── the defect ────────────────────────────────────────────────────────────────

def test_store_newcomer_gets_its_full_history_not_a_20_day_tail(store, capsys):
    tmp, raw, out = store
    _limit_up_series().to_parquet(raw / "600001.SS.parquet")
    _limit_up_series().to_parquet(raw / "600002.SS.parquet")
    _seed_events(out, ["600001.SS"])                      # 600002 is the newcomer

    res = bcm.build_increment(target_date=None)
    assert res["status"] == "ok"

    ev = pd.read_parquet(out / "limit_events.parquet")
    new = ev[ev["ticker"] == "600002.SS"]
    old = ev[ev["ticker"] == "600001.SS"]
    assert new["date"].min() <= FIRST_BAR + pd.Timedelta(days=7)   # back to its store start
    assert len(new) > 300                                          # not a 20-day tail
    # the name already in the store is scanned over the WINDOW only — no full re-sweep
    assert old["date"].min() >= WINDOW_FLOOR
    assert res["newcomer_tickers"] == 1 and res["newcomer_history_events"] > 300


def test_the_hole_is_disclosed_per_name_and_as_an_annotation(store, capsys):
    tmp, raw, out = store
    _limit_up_series().to_parquet(raw / "600001.SS.parquet")
    _limit_up_series().to_parquet(raw / "600002.SS.parquet")
    _seed_events(out, ["600001.SS"])

    bcm.build_increment(target_date=None)

    packet = json.loads((tmp / "site" / "microstructure.json").read_text())
    assert packet["newcomer_backfill"]["tickers"] == ["600002.SS"]
    assert any("store-newcomer" in g for g in packet["data_gaps"])

    lines = capsys.readouterr().out.splitlines()
    ann = [ln for ln in lines if "cn-limit-newcomer-backfill" in ln]
    assert ann, "the newcomer hole must raise a GitHub annotation"
    assert ann[0].startswith("::warning "), \
        "an annotation GitHub can parse must START its line (never through a logger)"


def test_the_tape_is_not_re_aggregated_from_newcomer_history(store):
    """A newcomer's back history must not mint old tape rows computed from that name alone."""
    tmp, raw, out = store
    _limit_up_series().to_parquet(raw / "600001.SS.parquet")
    _limit_up_series().to_parquet(raw / "600002.SS.parquet")
    _seed_events(out, ["600001.SS"])

    bcm.build_increment(target_date=None)

    tape = pd.read_parquet(out / "limit_tape.parquet")
    assert tape["date"].min() >= WINDOW_FLOOR, \
        "the tape must keep the universe that produced its historical rows"


def test_a_known_ticker_is_never_rescanned_from_the_tape_floor(store):
    tmp, raw, out = store
    _limit_up_series().to_parquet(raw / "600001.SS.parquet")
    _seed_events(out, ["600001.SS"])

    res = bcm.build_increment(target_date=None)
    assert res["newcomer_tickers"] == 0 and res["newcomer_history_events"] == 0
    ev = pd.read_parquet(out / "limit_events.parquet")
    assert ev["date"].min() >= WINDOW_FLOOR                     # window only, no full re-sweep


def test_missing_events_store_is_a_cold_start_not_1800_newcomers(store):
    """An unreadable store must not be read as 'every name is new' — that is the backfill's job."""
    tmp, raw, out = store
    _limit_up_series().to_parquet(raw / "600001.SS.parquet")

    assert bcm._known_event_tickers() == set()
    res = bcm.build_increment(target_date=None)
    assert res["newcomer_tickers"] == 0
    ev = pd.read_parquet(out / "limit_events.parquet")
    assert ev["date"].min() >= WINDOW_FLOOR                       # window only, no 2011 sweep


def test_newcomer_scan_is_capped_per_run(store, monkeypatch):
    tmp, raw, out = store
    for i in range(1, 5):
        _limit_up_series().to_parquet(raw / f"60000{i}.SS.parquet")
    _seed_events(out, ["600001.SS"])
    monkeypatch.setattr(bcm, "NEWCOMER_SCAN_CAP", 2)

    res = bcm.build_increment(target_date=None)
    assert res["newcomer_tickers"] == 2                          # 3 newcomers, 2 this run
    packet = json.loads((tmp / "site" / "microstructure.json").read_text())
    assert packet["newcomer_backfill"]["deferred_over_cap"] == 1
