"""Gap-aware resume state (v2) for collectors/massive_stock_day.

Regression suite for the 2026-07-03 coverage-gap incident: the v1 scalar
`last_captured_date` state was advanced past a 110-day hole by a smoke test, so a
resumed backfill skipped 2026-03-13→2026-06-30 forever while the manifest claimed
freshness.  These tests pin the v2 semantics: `processed_days` is a per-day set,
target selection is a set difference (interior holes are fetched like the leading
edge), confirmed-empty days are recorded, errored days are retried, and a legacy v1
state file is migrated from the actual parquets — never trusted.

All S3 access is stubbed (fetch_aggs/latest_available/enabled monkeypatched); the
store goes to a tmp dir via a patched config.data_dir.
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

import collectors.massive_stock_day as msd

# Ten consecutive weekdays: Mon 2026-06-01 … Fri 2026-06-12.
DAYS = [date.fromisoformat(s) for s in
        ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05",
         "2026-06-08", "2026-06-09", "2026-06-10", "2026-06-11", "2026-06-12"]]


def _day_frame(d: date) -> pd.DataFrame:
    """A two-ticker whole-market day frame in the raw fetch_aggs schema."""
    return pd.DataFrame({
        "ticker": ["SPY", "AAPL"],
        "open": [500.0, 200.0], "high": [505.0, 202.0],
        "low": [495.0, 198.0], "close": [502.0, 201.0],
        "volume": [1_000_000, 2_000_000], "transactions": [10_000, 20_000],
    })


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Tmp store + stubbed S3 layer.  Returns a dict the tests mutate to steer the
    fake fetch: holidays (empty frames) and failures (raise)."""
    monkeypatch.setattr(msd.config, "data_dir", lambda: tmp_path)
    # These tests are about resume-state semantics, not the store-absent fence: their
    # synthetic store is two tickers, and the real floor (~100 parquets, sized to tell a
    # restored store from a checkout holding only the committed sidecars) would read a
    # legitimate 2-file store as a throwaway checkout and short-circuit every case.
    # tests/test_massive_stock_day_fence.py owns the fence itself.
    monkeypatch.setattr(msd, "_MIN_STORE_FILES", 1)
    monkeypatch.setattr(msd, "enabled", lambda: True)
    monkeypatch.setattr(msd, "latest_available", lambda *a, **k: DAYS[-1])
    ctl = {"holidays": set(), "fail": set(), "calls": []}

    def fake_fetch(d, product="stock_day", underlyings=None, use_cache=True):
        ctl["calls"].append(d)
        if d in ctl["fail"]:
            raise OSError("S3 403")
        if d in ctl["holidays"]:
            return pd.DataFrame()
        return _day_frame(d)

    monkeypatch.setattr(msd, "fetch_aggs", fake_fetch)
    return ctl


def _spy_days() -> list[date]:
    df = msd.load_ticker("SPY")
    return sorted(t.date() for t in pd.to_datetime(df.index))


def test_smoke_then_full_backfill_fills_the_middle(store):
    """THE incident regression: a smoke capture at the tip must not make a later
    full backfill skip everything before it."""
    smoke = msd.backfill(start=DAYS[7], end=DAYS[9])
    assert smoke["days_fetched"] == 3
    # v1 would now resume at DAYS[9]+1 and fetch NOTHING; v2 targets the missing 7.
    full = msd.backfill(start=DAYS[0], end=DAYS[9])
    assert full["days_fetched"] == 7
    assert _spy_days() == DAYS


def test_confirmed_empty_day_recorded_and_not_reprobed(store):
    store["holidays"] = {DAYS[2]}
    r = msd.backfill(start=DAYS[0], end=DAYS[4])
    assert r["days_fetched"] == 4 and r["days_skipped"] == 1
    store["calls"].clear()
    r2 = msd.backfill(start=DAYS[0], end=DAYS[4])
    assert store["calls"] == []            # nothing re-probed, holiday included
    assert r2["days_fetched"] == 0


def test_failed_day_not_recorded_and_retried(store):
    store["fail"] = {DAYS[2]}
    r = msd.backfill(start=DAYS[0], end=DAYS[4])
    assert r["days_failed"] == 1 and r["days_remaining"] == 1
    assert DAYS[2] not in msd._processed_days()
    store["fail"].clear()
    r2 = msd.backfill(start=DAYS[0], end=DAYS[4])
    assert r2["days_fetched"] == 1 and r2["days_remaining"] == 0
    assert _spy_days() == DAYS[:5]


def test_max_days_cap_reports_remaining(store):
    r = msd.backfill(start=DAYS[0], end=DAYS[9], max_days=3)
    assert r["days_fetched"] == 3
    assert r["days_remaining"] == 7


def test_incremental_self_heals_interior_hole(store):
    # Seed a store with an interior two-day hole + a missing leading edge.
    for d in [DAYS[0], DAYS[3], DAYS[4]]:
        msd.backfill(start=d, end=d)
    store["calls"].clear()
    r = msd.run_incremental()
    # Window = [min(processed) … latest_available] = DAYS[0]..DAYS[9]:
    # the hole (d1, d2) AND the edge (d5..d9) are both fetched.
    assert r["days_fetched"] == 7
    assert _spy_days() == DAYS


def test_incremental_already_current_short_circuits(store):
    msd.backfill(start=DAYS[0], end=DAYS[9])
    store["calls"].clear()
    r = msd.run_incremental()
    assert r.get("already_current") is True
    assert store["calls"] == []


def test_legacy_v1_state_migrated_from_parquets_not_trusted(store):
    """A v1 state whose scalar claims the tip must be rebuilt from actual content."""
    msd.backfill(start=DAYS[0], end=DAYS[2])
    # Forge the incident: v1-style state claiming the whole window is done.
    msd._backfill_state_path().write_text(
        json.dumps({"last_captured_date": DAYS[9].isoformat()}))
    processed = msd._processed_days()
    assert processed == set(DAYS[:3])       # from parquets, not the scalar's claim
    upgraded = json.loads(msd._backfill_state_path().read_text())
    assert upgraded["version"] == msd.STATE_VERSION
    # And a follow-up backfill fetches the 7 days the v1 scalar would have hidden.
    r = msd.backfill(start=DAYS[0], end=DAYS[9])
    assert r["days_fetched"] == 7


def test_manifest_carries_coverage_and_anchor_truth(store):
    store["holidays"] = {DAYS[1]}
    msd.backfill(start=DAYS[0], end=DAYS[4])
    mf = json.loads(msd._manifest_path().read_text())
    cov = mf["coverage"]
    assert cov["first_day"] == DAYS[0].isoformat()
    assert cov["last_day"] == DAYS[4].isoformat()
    assert cov["n_processed_days"] == 5
    assert cov["max_missing_run_weekdays"] == 0     # holiday was processed, not missing
    anchor = mf["anchor"]
    assert anchor["ticker"] == "SPY"
    assert anchor["n_rows"] == 4                     # 5 days minus the holiday
    assert anchor["last"] == DAYS[4].isoformat()


def test_manifest_reports_interior_missing_run(store):
    # Process the edges only; the middle 6 weekdays were never attempted.
    msd.backfill(start=DAYS[0], end=DAYS[1])
    msd.backfill(start=DAYS[8], end=DAYS[9])
    mf = json.loads(msd._manifest_path().read_text())
    assert mf["coverage"]["max_missing_run_weekdays"] == 6
    assert mf["coverage"]["missing_sample"][0] == DAYS[2].isoformat()
