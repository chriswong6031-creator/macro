"""R2-boundary safety for collectors/massive_stock_day (2026-07-04→07-29 freeze).

The store is R2-canonical: the nightly collect job restores it, upserts the new trading
days on top, and publishes the delta back.  Five properties make that round trip safe,
and each is pinned here.

  1. STORE-ABSENT FENCE — the collector refuses to run on a tree that lacks the store
     its committed resume state claims.  Fetching there would write parquets into a
     checkout the next `actions/checkout` wipes AND record those days in the state file
     that DOES get committed; the days then sit inside processed_days forever, below the
     incremental's set difference, never fetched again.  Silent, unrecoverable.
  2. The fence fires BEFORE the credentials check, so a fully credentialed throwaway
     checkout refuses too — creds are not the thing that makes a run safe.
  3. TIP-FIRST — a capped run fetches days above the high-water mark before any interior
     backlog, so a stale-state-manufactured backlog cannot starve today's bar.
  4. An unreadable local parquet is left alone, never overwritten with one day's rows.
  5. A blocked NIGHTLY emits a column-0 ::warning; graceful degradation swallowing the
     RuntimeError into run_status.json is exactly how this froze for 21 nights.

All S3 access is stubbed and the store goes to a tmp dir via a patched config.data_dir —
nothing here touches the real data/ tree.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import collectors.massive_stock_day as msd


@pytest.fixture()
def store(tmp_path, monkeypatch) -> Path:
    """Tmp store dir + a clean lane env.  Returns the store directory itself."""
    monkeypatch.setattr(msd.config, "data_dir", lambda: tmp_path)
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    return msd._store_dir()


def _seed_state(processed: list[str]) -> Path:
    """Write the committed-style v2 resume state; returns its path."""
    p = msd._backfill_state_path()
    p.write_text(json.dumps({"version": msd.STATE_VERSION,
                             "last_captured_date": processed[-1],
                             "processed_days": processed}, indent=2))
    return p


def _bar(day: str) -> pd.DataFrame:
    return pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0],
         "volume": [1], "transactions": [1]},
        index=pd.DatetimeIndex([pd.Timestamp(day)], name="date"))


def _tiny_parquet(ticker: str, day: str = "2026-06-01") -> None:
    _bar(day).to_parquet(msd._ticker_path(ticker))


def _day_frame(_d: date) -> pd.DataFrame:
    """One raw whole-market day in the fetch_aggs schema (non-empty, so max_days bites:
    an empty frame counts as 'skipped', not 'fetched', and would never trip the cap)."""
    return pd.DataFrame({"ticker": ["SPY"], "open": [1.0], "high": [1.0], "low": [1.0],
                         "close": [1.0], "volume": [1], "transactions": [1]})


# --- 1 + 2: the fence -------------------------------------------------------


def test_store_absent_fence_blocks_and_writes_nothing(store, monkeypatch):
    state = _seed_state(["2026-06-01", "2026-06-02", "2026-06-03"])
    before = state.read_bytes()

    def boom(*_a, **_k):
        raise AssertionError("fence must fire before ANY creds/network work")

    monkeypatch.setattr(msd, "enabled", boom)
    monkeypatch.setattr(msd, "latest_available", boom)
    monkeypatch.setattr(msd, "fetch_aggs", boom)

    assert msd.run_incremental() == {"blocked": "store_absent"}
    assert msd.backfill() == {"blocked": "store_absent"}
    # The two committed sidecars are what a bad run would poison. Neither moved.
    assert state.read_bytes() == before
    assert not msd._manifest_path().exists()


def test_fence_also_refuses_a_legacy_v1_state(store, monkeypatch):
    # A v1 scalar claims coverage just as loudly — and _processed_days() would migrate
    # it by SCANNING and SAVING, so the fence must never route through that path.
    state = msd._backfill_state_path()
    state.write_text(json.dumps({"last_captured_date": "2026-06-03"}))
    before = state.read_bytes()
    monkeypatch.setattr(msd, "enabled", lambda: True)
    assert msd.run_incremental() == {"blocked": "store_absent"}
    assert state.read_bytes() == before


def test_populated_store_passes_the_fence_to_the_creds_check(store, monkeypatch):
    # 100 real parquets is heavy for a unit test; move the floor instead.
    monkeypatch.setattr(msd, "_MIN_STORE_FILES", 3)
    _seed_state(["2026-06-01"])
    for t in ("SPY", "QQQ", "AAPL"):
        _tiny_parquet(t)
    monkeypatch.setattr(msd, "enabled", lambda: False)
    # Fence cleared => execution reaches the NEXT gate, which is credentials.
    assert msd.run_incremental() == {"blocked": "no_creds"}


def test_virgin_state_is_not_fenced(store, monkeypatch):
    # Empty store + no resume state = a legitimate first bootstrap, not a lost restore.
    # Over-fencing here would brick the store's own genesis.
    monkeypatch.setattr(msd, "enabled", lambda: False)
    assert msd.run_incremental() == {"blocked": "no_creds"}


# --- 3: tip-first ordering --------------------------------------------------


def test_capped_run_fetches_the_tip_before_the_interior_backlog(store, monkeypatch):
    monkeypatch.setattr(msd, "_MIN_STORE_FILES", 1)
    _tiny_parquet("SPY")
    # Processed: Mon/Tue 06-01,06-02 then Mon/Tue 06-15,06-16 — an 8-weekday interior
    # hole (06-03…06-12) sitting below a tip of 06-16, with 6 fresh days above it.
    _seed_state(["2026-06-01", "2026-06-02", "2026-06-15", "2026-06-16"])
    calls: list[date] = []

    def fake_fetch(d, product="stock_day", underlyings=None, use_cache=True):
        calls.append(d)
        return _day_frame(d)

    monkeypatch.setattr(msd, "enabled", lambda: True)
    monkeypatch.setattr(msd, "latest_available", lambda *a, **k: date(2026, 6, 24))
    monkeypatch.setattr(msd, "fetch_aggs", fake_fetch)

    msd.run_incremental(max_days=8, pace_s=0)

    above_tip = [date(2026, 6, d) for d in (17, 18, 19, 22, 23, 24)]
    assert calls[:6] == above_tip                                  # tip first, ascending
    assert calls[6:] == [date(2026, 6, 3), date(2026, 6, 4)]       # then the hole, oldest first


def test_uncapped_run_still_covers_the_whole_backlog(store, monkeypatch):
    # Tip-first is an ORDERING, not a filter: nothing may be dropped.
    monkeypatch.setattr(msd, "_MIN_STORE_FILES", 1)
    _tiny_parquet("SPY")
    _seed_state(["2026-06-01", "2026-06-02", "2026-06-15", "2026-06-16"])
    calls: list[date] = []

    def fake_fetch(d, product="stock_day", underlyings=None, use_cache=True):
        calls.append(d)
        return _day_frame(d)

    monkeypatch.setattr(msd, "enabled", lambda: True)
    monkeypatch.setattr(msd, "latest_available", lambda *a, **k: date(2026, 6, 24))
    monkeypatch.setattr(msd, "fetch_aggs", fake_fetch)

    r = msd.run_incremental(max_days=None, pace_s=0)

    assert r["days_remaining"] == 0
    assert sorted(calls) == [d.date() for d in pd.bdate_range("2026-06-03", "2026-06-24")
                             if d.date() not in (date(2026, 6, 15), date(2026, 6, 16))]


# --- 4: corrupt-parquet fallback --------------------------------------------


def test_unreadable_parquet_is_left_untouched(store, caplog):
    path = msd._ticker_path("SPY")
    path.write_bytes(b"this is not a parquet file")
    before = path.read_bytes()
    with caplog.at_level(logging.WARNING, logger=msd.log.name):
        msd._upsert_ticker("SPY", _bar("2026-06-02"))
    # Overwriting would trade a 5-year history for one bar — and then publish it.
    assert path.read_bytes() == before
    assert any("unreadable" in r.getMessage() for r in caplog.records)


# --- 5: the blocked-nightly annotation --------------------------------------


def test_blocked_nightly_annotates_and_still_raises(store, monkeypatch, capsys):
    monkeypatch.setattr(msd, "enabled", lambda: False)
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    with pytest.raises(RuntimeError, match="massive_stock_day: no_creds"):
        msd.MassiveStockDayAdapter().fetch()
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]
    assert len(lines) == 1
    assert lines[0].startswith("::warning title=massive_stock_day feed blocked::no_creds")


def test_blocked_off_lane_stays_silent_and_still_raises(store, monkeypatch, capsys):
    # asia/weekly/manual lanes legitimately run without MASSIVE_S3_* — no crying wolf.
    monkeypatch.setattr(msd, "enabled", lambda: False)
    with pytest.raises(RuntimeError):
        msd.MassiveStockDayAdapter().fetch()
    assert "::" not in capsys.readouterr().out


# --- manifest: the recent-window continuity figure --------------------------


def test_manifest_reports_a_clean_recent_window_over_an_older_gap(store):
    # A gap deep in history plus a continuous tip: the full-history figure stays honest
    # (it is what a stale/mid-backfill state snapshot inflates) while the recent figure
    # — the one audit_r2's coverage probe gates on — reads clean.
    _tiny_parquet("SPY")
    old = [d.date() for d in pd.bdate_range("2026-01-05", "2026-01-09")]
    recent = [d.date() for d in pd.bdate_range("2026-03-02", "2026-07-02")]
    msd._write_manifest(1, recent[-1], set(old + recent))
    cov = json.loads(msd._manifest_path().read_text())["coverage"]
    assert cov["max_missing_run_weekdays"] > 5
    assert cov["max_missing_run_weekdays_recent"] == 0
    assert cov["recent_window_bdays"] == 90          # plumbed from config.yml quality


def test_manifest_recent_window_sees_a_tip_adjacent_hole(store):
    _tiny_parquet("SPY")
    days = [d.date() for d in pd.bdate_range("2026-03-02", "2026-07-02")]
    # Drop a 10-weekday run right below the tip — the incident class.
    hole = set(d.date() for d in pd.bdate_range("2026-06-15", "2026-06-26"))
    msd._write_manifest(1, days[-1], {d for d in days if d not in hole})
    cov = json.loads(msd._manifest_path().read_text())["coverage"]
    assert cov["max_missing_run_weekdays_recent"] == 10
