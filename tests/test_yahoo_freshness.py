"""collectors/yahoo.check_yahoo_freshness — the store-level tripwire for the
engine-critical yahoo names (^GSPC incident: seeded once by a one-shot script,
never in any config ticker group, frozen 2026-06-12→07-16 with eight engine
consumers reading it). detect_stale_series only sees frames a fetch returned,
so only a store-vs-NYSE-calendar read catches this class. No network."""
import datetime as dt

import pandas as pd

from collectors.yahoo import ENGINE_CRITICAL_SERIES, check_yahoo_freshness
from lib import store as _store


def _fake_store(monkeypatch, tmp_path, frames: dict):
    """Point the parquet store at tmp_path and seed data/yahoo/<name>.parquet frames.

    Also redirects config.ROOT: store.write_status/read_status resolve
    data/run_status.json off ROOT (no root= param), and the freshness
    tripwire writes that surface — unredirected it dirties the REAL
    data/run_status.json."""
    from lib import config as _config
    _config.load()  # warm the lru cache before ROOT is patched
    monkeypatch.setattr(_config, "ROOT", tmp_path)
    monkeypatch.setattr(_config, "data_dir", lambda: tmp_path)
    (tmp_path / "yahoo").mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        safe = name.replace("^", "_")
        df.to_parquet(tmp_path / "yahoo" / f"{safe}.parquet")


def _frame(end: str, periods: int = 2000) -> pd.DataFrame:
    idx = pd.date_range(end=end, periods=periods, freq="B")
    return pd.DataFrame({"close": range(periods)}, index=idx)


def test_yahoo_freshness_clean_store(monkeypatch, tmp_path):
    import lib.nyse_calendar as cal
    monkeypatch.setattr(cal, "expected_last_session", lambda now=None: dt.date(2026, 7, 13))
    _fake_store(monkeypatch, tmp_path,
                {s: _frame("2026-07-13") for s in ENGINE_CRITICAL_SERIES})
    assert check_yahoo_freshness() == []


def test_yahoo_freshness_flags_frozen_tail(monkeypatch, tmp_path):
    """The exact ^GSPC failure: a deep-history store whose tail froze a month ago
    must trip a NAMED stale_series entry even though no fetch ever returns it."""
    import lib.nyse_calendar as cal
    monkeypatch.setattr(cal, "expected_last_session", lambda now=None: dt.date(2026, 7, 13))
    frames = {s: _frame("2026-07-13") for s in ENGINE_CRITICAL_SERIES}
    frames["^GSPC"] = _frame("2026-06-12")   # frozen tail, one month behind
    _fake_store(monkeypatch, tmp_path, frames)
    problems = {p["series"]: p["reason"] for p in check_yahoo_freshness()}
    assert set(problems) == {"^GSPC"}
    assert "stale" in problems["^GSPC"]
    # the tripwire rides the existing run_status stale_series health surface
    surfaced = {e["series"] for e in _store.read_status().get("stale_series", [])}
    assert "^GSPC" in surfaced


def test_yahoo_freshness_flags_stub_and_missing(monkeypatch, tmp_path):
    import lib.nyse_calendar as cal
    monkeypatch.setattr(cal, "expected_last_session", lambda now=None: dt.date(2026, 7, 13))
    frames = {s: _frame("2026-07-13") for s in ENGINE_CRITICAL_SERIES}
    frames["SPY"] = _frame("2026-07-13", periods=3)   # stub re-seed (row floor)
    frames.pop("^VIX")                                # absent from the store entirely
    _fake_store(monkeypatch, tmp_path, frames)
    problems = {p["series"]: p["reason"] for p in check_yahoo_freshness()}
    assert set(problems) == {"SPY", "^VIX"}
    assert "row floor" in problems["SPY"]
    assert "missing" in problems["^VIX"]


def test_yahoo_freshness_tolerates_weekend_gap(monkeypatch, tmp_path):
    """A store last written Friday checked on Monday-expected-Friday must be clean:
    the lag is counted in NYSE sessions, not calendar days."""
    import lib.nyse_calendar as cal
    # expected last session Fri 2026-07-10; store also ends 07-10 → 0 sessions behind
    monkeypatch.setattr(cal, "expected_last_session", lambda now=None: dt.date(2026, 7, 10))
    _fake_store(monkeypatch, tmp_path,
                {s: _frame("2026-07-10") for s in ENGINE_CRITICAL_SERIES})
    assert check_yahoo_freshness() == []
