"""collectors/cboe session-coverage tripwire + 429-cooldown sweep (2026-07-27 miss).

The 07-27 whole-family miss was silent through every layer: putcall FAILED but
graceful degradation kept the run green; gex returned 7/10 symbols so the source was
'ok' and detect_stale_series (returned-frames only) saw nothing; the cor/vol tripwire
does not cover this family; and by the next evening the tail was fresh again, so any
last-obs check was permanently green. These tests pin the two fixes: (a) membership
coverage of the last N NYSE sessions with LINE-START ::warning/::error annotations,
(b) the one-cooldown second sweep that gives a flapping 429 window a spaced retry.
No network."""
import datetime as dt

import pandas as pd
import pytest

import collectors.cboe as cboe
from collectors.cboe import (
    CHAIN_429_COOLDOWN_S,
    CHAIN_FAMILY_SERIES,
    KNOWN_PERMANENT_GAPS,
    GexAdapter,
    PutCallAdapter,
    check_chain_session_coverage,
)
from lib import store as _store

# frozen window: expected last session Mon 2026-07-13 -> last 5 sessions
WINDOW = [dt.date(2026, 7, d) for d in (7, 8, 9, 10, 13)]


def _fake_store(monkeypatch, tmp_path, frames: dict):
    """Point the parquet store at tmp_path and seed data/cboe/<name>.parquet frames.

    Also redirects config.ROOT: store.write_status/read_status resolve
    data/run_status.json off ROOT, and the tripwire writes that surface —
    unredirected it dirties the REAL data/run_status.json."""
    from lib import config as _config
    _config.load()  # warm the lru cache before ROOT is patched
    monkeypatch.setattr(_config, "ROOT", tmp_path)
    monkeypatch.setattr(_config, "data_dir", lambda: tmp_path)
    (tmp_path / "cboe").mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        df.to_parquet(tmp_path / "cboe" / f"{name}.parquet")


def _frame(days: list[dt.date]) -> pd.DataFrame:
    idx = pd.to_datetime(sorted(days))
    return pd.DataFrame({"v": range(len(idx))}, index=idx)


@pytest.fixture
def frozen_calendar(monkeypatch):
    import lib.nyse_calendar as cal
    monkeypatch.setattr(cal, "expected_last_session",
                        lambda now=None: dt.date(2026, 7, 13))


def _full_family(days=None):
    return {s: _frame(days or WINDOW) for s in CHAIN_FAMILY_SERIES}


def test_clean_store_is_silent(monkeypatch, tmp_path, capsys, frozen_calendar):
    _fake_store(monkeypatch, tmp_path, _full_family())
    assert check_chain_session_coverage() == []
    assert "::" not in capsys.readouterr().out


def test_replay_2026_07_27_shape(monkeypatch, tmp_path, capsys, frozen_calendar):
    """The exact event: putcall + gex + gex_SPX/gex_SPY/gex_MSFT all lose the latest
    session while the other symbols carry it — must fire per-series entries, ONE
    line-start ::warning, and the whole-family ::error escalation."""
    frames = _full_family()
    for s in ("putcall", "gex", "gex_SPX", "gex_SPY", "gex_MSFT"):
        frames[s] = _frame(WINDOW[:-1])   # missing Mon 2026-07-13
    _fake_store(monkeypatch, tmp_path, frames)
    problems = {p["series"]: p["reason"] for p in check_chain_session_coverage()}
    assert set(problems) == {"putcall", "gex", "gex_SPX", "gex_SPY", "gex_MSFT"}
    assert all("2026-07-13" in r for r in problems.values())
    out = capsys.readouterr().out
    warn = [ln for ln in out.splitlines() if "::warning " in ln]
    err = [ln for ln in out.splitlines() if "::error " in ln]
    assert len(warn) == 1 and len(err) == 1
    # the annotation LAW: '::' must start the line or GitHub silently drops it
    assert warn[0].startswith("::warning title=cboe-session-miss::")
    assert err[0].startswith("::error title=cboe-session-miss::")
    assert "putcall" in warn[0] and "2026-07-13" in warn[0]
    assert "2026-07-13" in err[0]
    # rides the existing run_status stale_series health surface too
    surfaced = {e["series"] for e in _store.read_status().get("stale_series", [])}
    assert {"putcall", "gex", "gex_SPX"} <= surfaced


def test_interior_hole_still_fires(monkeypatch, tmp_path, capsys, frozen_calendar):
    """The day-after shape: tail fresh again (07-13 present) but one session inside
    the window missing. A tail-age check is green here — membership must not be."""
    frames = _full_family()
    frames["gex_SPX"] = _frame([d for d in WINDOW if d != dt.date(2026, 7, 9)])
    _fake_store(monkeypatch, tmp_path, frames)
    problems = check_chain_session_coverage()
    assert [p["series"] for p in problems] == ["gex_SPX"]
    assert "2026-07-09" in problems[0]["reason"]
    warn = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::warning ")]
    assert len(warn) == 1 and "gex_SPX" in warn[0]


def test_known_gap_registry_suppresses(monkeypatch, tmp_path, capsys, frozen_calendar):
    """A hole registered in KNOWN_PERMANENT_GAPS (the disclosure note) goes quiet —
    and the real registry must carry the 2026-07-27 event."""
    frames = _full_family()
    for s in ("putcall", "gex", "gex_SPX"):
        frames[s] = _frame(WINDOW[:-1])
    _fake_store(monkeypatch, tmp_path, frames)
    monkeypatch.setitem(cboe.KNOWN_PERMANENT_GAPS, dt.date(2026, 7, 13), "test gap")
    assert check_chain_session_coverage() == []
    assert "::" not in capsys.readouterr().out
    assert dt.date(2026, 7, 27) in KNOWN_PERMANENT_GAPS  # the real disclosure stays


def test_weekend_rows_cannot_mask(monkeypatch, tmp_path, frozen_calendar):
    """Sat/Sun-dated snapshot rows (the runner writes one per RUN day) must not
    satisfy a missing Friday session — membership is by session date."""
    frames = _full_family()
    frames["putcall"] = _frame(
        [d for d in WINDOW if d != dt.date(2026, 7, 10)]
        + [dt.date(2026, 7, 11), dt.date(2026, 7, 12)])   # weekend snapshots present
    _fake_store(monkeypatch, tmp_path, frames)
    problems = check_chain_session_coverage()
    assert [p["series"] for p in problems] == ["putcall"]
    assert "2026-07-10" in problems[0]["reason"]


def test_young_series_owes_only_its_era(monkeypatch, tmp_path, capsys, frozen_calendar):
    frames = _full_family()
    frames["gex_MSFT"] = _frame(WINDOW[3:])   # first row mid-window
    _fake_store(monkeypatch, tmp_path, frames)
    assert check_chain_session_coverage() == []
    assert "::" not in capsys.readouterr().out


def test_missing_from_store_fires(monkeypatch, tmp_path, capsys, frozen_calendar):
    frames = _full_family()
    frames.pop("putcall")
    _fake_store(monkeypatch, tmp_path, frames)
    problems = check_chain_session_coverage()
    assert [(p["series"], p["reason"]) for p in problems] == [
        ("putcall", "missing from store")]
    warn = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::warning ")]
    assert len(warn) == 1


# ------------------------------------------------------------- 429 cooldown sweep

def _stub_chain(spot: float = 100.0) -> pd.DataFrame:
    horizon = pd.Timestamp(dt.date.today()) + pd.Timedelta(days=5)
    return pd.DataFrame({
        "K": [95.0, 100.0, 105.0, 110.0],
        "T": [0.01] * 4,
        "iv": [0.2] * 4,
        "oi": [100.0] * 4,
        "gamma": [0.01] * 4,
        "is_call": [True, False, True, False],
        "expiry": [horizon] * 4,
    })


def test_gex_cooldown_sweep_recovers_flapped_symbols(monkeypatch):
    """First sweep loses _SPX + SPY to a flapping 429 window; the single-attempt
    post-cooldown sweep recovers them (retries=1, one sleep of the cooldown)."""
    import engine.gex_engine as gex_engine
    monkeypatch.setattr(gex_engine, "compute_gex",
                        lambda chain, spot, cfg: {"spot": spot, "net_gex_bn": 1.0})
    sleeps: list[float] = []
    monkeypatch.setattr(cboe.time, "sleep", sleeps.append)

    calls: list[tuple[str, int | None]] = []

    def fake_chain(self, symbol, retries=None):
        calls.append((symbol, retries))
        if symbol in ("_SPX", "SPY") and retries is None:
            raise RuntimeError("HTTP 429")
        return _stub_chain(), 100.0

    monkeypatch.setattr(GexAdapter, "_chain", fake_chain)
    out = GexAdapter().fetch()
    assert {"gex_SPX", "gex_SPY", "gex", "gex_QQQ", "gex_MSFT"} <= set(out)
    assert sleeps == [CHAIN_429_COOLDOWN_S]
    assert ("_SPX", 1) in calls and ("SPY", 1) in calls  # second sweep is single-attempt


def test_gex_no_failures_no_sleep(monkeypatch):
    import engine.gex_engine as gex_engine
    monkeypatch.setattr(gex_engine, "compute_gex",
                        lambda chain, spot, cfg: {"spot": spot})
    sleeps: list[float] = []
    monkeypatch.setattr(cboe.time, "sleep", sleeps.append)
    monkeypatch.setattr(GexAdapter, "_chain",
                        lambda self, symbol, retries=None: (_stub_chain(), 100.0))
    out = GexAdapter().fetch()
    assert "gex" in out and sleeps == []


def test_putcall_spx_leg_gets_one_spaced_retry(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(cboe.time, "sleep", sleeps.append)
    attempts: list[int | None] = []

    def fake_volumes(self, symbol, retries=None):
        if symbol == "_SPX":
            attempts.append(retries)
            if retries is None:
                raise RuntimeError("HTTP 429")
            return 100.0, 50.0
        return 10.0, 20.0

    monkeypatch.setattr(PutCallAdapter, "_chain_volumes", fake_volumes)
    frames = PutCallAdapter().fetch()
    snap = frames["putcall"]
    assert float(snap["index_pc_ratio"].iloc[0]) == 2.0
    assert sleeps == [CHAIN_429_COOLDOWN_S]
    assert attempts == [None, 1]


def test_putcall_still_fails_source_when_retry_fails(monkeypatch):
    """Second _SPX failure must still raise — the source reports FAILED (the
    coverage tripwire is what makes the resulting hole loud)."""
    monkeypatch.setattr(cboe.time, "sleep", lambda s: None)

    def fake_volumes(self, symbol, retries=None):
        raise RuntimeError("HTTP 429")

    monkeypatch.setattr(PutCallAdapter, "_chain_volumes", fake_volumes)
    with pytest.raises(RuntimeError):
        PutCallAdapter().fetch()
