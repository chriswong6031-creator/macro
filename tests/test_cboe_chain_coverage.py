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
    CHAIN_429_COOLDOWN_LADDER_S,
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


# ------------------------------------------- 2026-07-30 ≥3-min 429: the cooldown LADDER
# 07-27 was a ~1-min flap that one 60s cooldown cleared. 07-30 held the 429 continuously
# for ≥3 min (23:42:32Z→23:45:33Z+, run 30590845976) and outlasted it, costing putcall +
# gex/gex_SPX/gex_SPY/gex_QQQ/gex_IWM the session. These pin the 60s→300s escalation.

def test_gex_second_cooldown_recovers_a_long_429_window(monkeypatch):
    """The 07-30 shape: the window outlasts the 60s pass and lifts only during the
    300s one. The symbol must be recovered, and ONLY the still-failing symbol may be
    re-swept on the second pass (a healthy symbol is never re-fetched)."""
    import engine.gex_engine as gex_engine
    monkeypatch.setattr(gex_engine, "compute_gex",
                        lambda chain, spot, cfg: {"spot": spot, "net_gex_bn": 1.0})
    sleeps: list[float] = []
    monkeypatch.setattr(cboe.time, "sleep", sleeps.append)
    calls: list[tuple[str, int | None]] = []

    def fake_chain(self, symbol, retries=None):
        calls.append((symbol, retries))
        if symbol == "_SPX" and len(sleeps) < 2:   # still inside the ≥3-min window
            raise RuntimeError("HTTP 429")
        return _stub_chain(), 100.0

    monkeypatch.setattr(GexAdapter, "_chain", fake_chain)
    out = GexAdapter().fetch()

    assert {"gex_SPX", "gex"} <= set(out)          # recovered on the 300s pass
    assert sleeps == list(CHAIN_429_COOLDOWN_LADDER_S) == [CHAIN_429_COOLDOWN_S, 300.0]
    # both recovery passes are single-attempt, and target only the failed symbol
    post_cooldown = [c for c in calls if c[1] == 1]
    assert post_cooldown == [("_SPX", 1), ("_SPX", 1)]


def test_gex_ladder_stops_as_soon_as_the_set_empties(monkeypatch):
    """A window that lifts on the FIRST pass must not spend the 300s sleep — the
    07-27 shape keeps its old cost, only the long window pays the ladder."""
    import engine.gex_engine as gex_engine
    monkeypatch.setattr(gex_engine, "compute_gex",
                        lambda chain, spot, cfg: {"spot": spot, "net_gex_bn": 1.0})
    sleeps: list[float] = []
    monkeypatch.setattr(cboe.time, "sleep", sleeps.append)

    def fake_chain(self, symbol, retries=None):
        if symbol in ("_SPX", "SPY") and retries is None:
            raise RuntimeError("HTTP 429")
        return _stub_chain(), 100.0

    monkeypatch.setattr(GexAdapter, "_chain", fake_chain)
    out = GexAdapter().fetch()
    assert {"gex_SPX", "gex_SPY"} <= set(out)
    assert sleeps == [CHAIN_429_COOLDOWN_S]        # never reached the 300s rung


def test_putcall_spx_leg_walks_to_the_second_cooldown(monkeypatch):
    """putcall is all-or-nothing on _SPX — the leg that killed 07-27 AND 07-30. It
    must walk the whole ladder before giving the session up."""
    sleeps: list[float] = []
    monkeypatch.setattr(cboe.time, "sleep", sleeps.append)
    attempts: list[int | None] = []

    def fake_volumes(self, symbol, retries=None):
        if symbol != "_SPX":
            return 10.0, 20.0
        attempts.append(retries)
        if len(sleeps) < 2:                        # still inside the ≥3-min window
            raise RuntimeError("HTTP 429")
        return 100.0, 50.0

    monkeypatch.setattr(PutCallAdapter, "_chain_volumes", fake_volumes)
    snap = PutCallAdapter().fetch()["putcall"]
    assert float(snap["index_pc_ratio"].iloc[0]) == 2.0
    assert sleeps == list(CHAIN_429_COOLDOWN_LADDER_S)
    assert attempts == [None, 1, 1]                # first sweep + both ladder rungs


def test_putcall_exhausts_the_ladder_then_fails_the_source(monkeypatch):
    """A window outlasting BOTH rungs must still raise — an honest hole beats a
    fabricated row, and the coverage tripwire is what makes it loud."""
    sleeps: list[float] = []
    monkeypatch.setattr(cboe.time, "sleep", sleeps.append)

    def fake_volumes(self, symbol, retries=None):
        raise RuntimeError("HTTP 429 forever")

    monkeypatch.setattr(PutCallAdapter, "_chain_volumes", fake_volumes)
    with pytest.raises(RuntimeError, match="429"):
        PutCallAdapter().fetch()
    assert sleeps == list(CHAIN_429_COOLDOWN_LADDER_S)


# ------------------------------------- the 07-30 → 08-05 outage window is REGISTERED
# Five consecutive lost sessions from four distinct causes (429 flap; then three
# nights of collect-step crashes discarding the night's single checkpoint commit).
# The window ending 2026-08-05 is exactly those five sessions.

@pytest.fixture
def frozen_calendar_0805(monkeypatch):
    import lib.nyse_calendar as cal
    monkeypatch.setattr(cal, "expected_last_session",
                        lambda now=None: dt.date(2026, 8, 5))


OUTAGE_SESSIONS = [dt.date(2026, 7, 30), dt.date(2026, 7, 31),
                   dt.date(2026, 8, 3), dt.date(2026, 8, 4), dt.date(2026, 8, 5)]


def test_outage_window_dates_are_all_registered():
    """Every session lost in the 07-30→08-05 outage carries a disclosure string."""
    for d in OUTAGE_SESSIONS:
        assert d in KNOWN_PERMANENT_GAPS, f"{d} lost but not registered"
        assert len(KNOWN_PERMANENT_GAPS[d]) > 80, f"{d} registered without a cause"
    assert dt.date(2026, 7, 27) in KNOWN_PERMANENT_GAPS   # the original stays


def test_registered_outage_window_is_silent(monkeypatch, tmp_path, capsys,
                                            frozen_calendar_0805):
    """A store missing all five outage sessions must be QUIET — they are registered."""
    frames = {s: _frame([dt.date(2026, 7, 28), dt.date(2026, 7, 29)])
              for s in CHAIN_FAMILY_SERIES}
    _fake_store(monkeypatch, tmp_path, frames)
    assert check_chain_session_coverage() == []
    assert "::" not in capsys.readouterr().out


def test_registry_is_load_bearing_not_vacuous(monkeypatch, tmp_path, capsys,
                                              frozen_calendar_0805):
    """Mutation of the test above: drop ONE date from the registry and the same store
    must fire for exactly that date. Without this, the silence proves nothing."""
    frames = {s: _frame([dt.date(2026, 7, 28), dt.date(2026, 7, 29)])
              for s in CHAIN_FAMILY_SERIES}
    _fake_store(monkeypatch, tmp_path, frames)
    monkeypatch.delitem(cboe.KNOWN_PERMANENT_GAPS, dt.date(2026, 8, 4))
    problems = check_chain_session_coverage()
    assert {p["series"] for p in problems} == set(CHAIN_FAMILY_SERIES)
    assert all("2026-08-04" in p["reason"] for p in problems)
    assert all(str(d) not in p["reason"]                      # the rest stay silenced
               for p in problems for d in OUTAGE_SESSIONS if d != dt.date(2026, 8, 4))
    out = capsys.readouterr().out
    assert len([ln for ln in out.splitlines() if ln.startswith("::warning ")]) == 1


def test_tripwire_warning_names_the_cross_fill_remedy(monkeypatch, tmp_path, capsys,
                                                      frozen_calendar):
    """The remedy hint must point at the honest polygon cross-fill for gex_<name>
    holes — and stay a LINE-START annotation (a logger prefix would drop it)."""
    frames = _full_family()
    frames["gex_SPY"] = _frame(WINDOW[:-1])
    _fake_store(monkeypatch, tmp_path, frames)
    check_chain_session_coverage()
    warn = [ln for ln in capsys.readouterr().out.splitlines()
            if ln.startswith("::warning ")]
    assert len(warn) == 1
    assert "backfill_cboe_gex_20260730_from_polygon.py" in warn[0]
    assert "polygon_gex" in warn[0] and "session+1" in warn[0]


# ------------------------------------------------------- the 07-30 polygon cross-fill

def test_backfill_is_idempotent(monkeypatch, tmp_path, capsys):
    """Second run on the same store is a pure no-op: no duplicate row, no mutation."""
    import scripts.backfill_cboe_gex_20260730_from_polygon as bf
    from lib import config as _config
    _config.load()
    monkeypatch.setattr(_config, "ROOT", tmp_path)
    monkeypatch.setattr(_config, "data_dir", lambda: tmp_path)

    sym, session = "SPY", pd.Timestamp(bf.SESSION)
    cols = ["spot", "net_gex_bn", "gamma_flip", "gamma_regime", "n_strikes"]
    src = pd.DataFrame({"spot": [741.69], "net_gex_bn": [-6.15749],
                        "gamma_flip": [750.66], "gamma_regime": ["short"],
                        "n_strikes": [6249]},
                       index=pd.DatetimeIndex([pd.Timestamp(bf.POLYGON_STAMP)]))[cols]
    tgt = pd.DataFrame({"spot": [729.46, 747.03], "net_gex_bn": [-1.0, -2.0],
                        "gamma_flip": [730.0, 750.0], "gamma_regime": ["short", "short"],
                        "n_strikes": [100, 200]},
                       index=pd.to_datetime(["2026-07-29", "2026-07-31"]))[cols]
    yahoo = pd.DataFrame({"close": [729.46, 741.69, 747.03]},
                         index=pd.to_datetime(["2026-07-29", "2026-07-30", "2026-07-31"]))
    for grp, name, df in (("polygon_gex", f"summary_{sym}", src),
                          ("cboe", f"gex_{sym}", tgt), ("yahoo", sym, yahoo)):
        (tmp_path / grp).mkdir(parents=True, exist_ok=True)
        df.to_parquet(tmp_path / grp / f"{name}.parquet")

    first = bf.backfill(symbols=(sym,))
    assert [r["symbol"] for r in first["written"]] == [sym] and first["skipped"] == []
    after = _store.read("cboe", f"gex_{sym}")
    assert session in after.index and len(after) == 3
    assert after.index.is_monotonic_increasing
    assert float(after.loc[session, "spot"]) == 741.69     # the re-dated polygon row
    assert list(after.dtypes) == list(tgt.dtypes)          # nothing upcast
    snapshot = after.copy()

    second = bf.backfill(symbols=(sym,))
    assert second["written"] == [] and second["skipped"] == [sym]
    assert "SKIP" in capsys.readouterr().out
    pd.testing.assert_frame_equal(_store.read("cboe", f"gex_{sym}"), snapshot)


def test_backfill_refuses_the_wrong_session(monkeypatch, tmp_path):
    """The session-identity gate is the whole safety story: the polygon stamp is
    session+1, so a row whose spot does not match the target session's close must be
    REFUSED rather than written under the wrong date."""
    import scripts.backfill_cboe_gex_20260730_from_polygon as bf
    from lib import config as _config
    _config.load()
    monkeypatch.setattr(_config, "ROOT", tmp_path)
    monkeypatch.setattr(_config, "data_dir", lambda: tmp_path)

    sym = "SPY"
    cols = ["spot", "net_gex_bn"]
    # spot is the 07-29 close — i.e. the row stamped 07-30, one session off
    src = pd.DataFrame({"spot": [729.46], "net_gex_bn": [-6.0]},
                       index=pd.DatetimeIndex([pd.Timestamp(bf.POLYGON_STAMP)]))[cols]
    tgt = pd.DataFrame({"spot": [747.03], "net_gex_bn": [-2.0]},
                       index=pd.to_datetime(["2026-07-31"]))[cols]
    yahoo = pd.DataFrame({"close": [729.46, 741.69, 747.03]},
                         index=pd.to_datetime(["2026-07-29", "2026-07-30", "2026-07-31"]))
    for grp, name, df in (("polygon_gex", f"summary_{sym}", src),
                          ("cboe", f"gex_{sym}", tgt), ("yahoo", sym, yahoo)):
        (tmp_path / grp).mkdir(parents=True, exist_ok=True)
        df.to_parquet(tmp_path / grp / f"{name}.parquet")

    with pytest.raises(bf.BackfillPreconditionError, match="NOT the 2026-07-30 session"):
        bf.backfill(symbols=(sym,))
    assert pd.Timestamp(bf.SESSION) not in _store.read("cboe", f"gex_{sym}").index


def test_backfill_refuses_an_ambiguous_session_match(monkeypatch, tmp_path):
    """A spot inside the tolerance of the target session but CLOSER to a neighbour is
    ambiguous and must be refused. This is the real 08-05 case: the polygon row
    stamped 08-06 sits 0.175% from the 08-05 close (inside a 0.5% gate) but 0.025%
    from 08-04 — the tolerance alone would have written a live intraday snapshot as
    a session close."""
    import scripts.backfill_cboe_gex_20260730_from_polygon as bf
    from lib import config as _config
    _config.load()
    monkeypatch.setattr(_config, "ROOT", tmp_path)
    monkeypatch.setattr(_config, "data_dir", lambda: tmp_path)

    sym = "SPY"
    cols = ["spot", "net_gex_bn"]
    src = pd.DataFrame({"spot": [742.9], "net_gex_bn": [-6.0]},   # 0.16% from 07-30
                       index=pd.DatetimeIndex([pd.Timestamp(bf.POLYGON_STAMP)]))[cols]
    tgt = pd.DataFrame({"spot": [729.46], "net_gex_bn": [-2.0]},
                       index=pd.to_datetime(["2026-07-29"]))[cols]
    # 07-31's close sits nearer the source spot than 07-30's does
    yahoo = pd.DataFrame({"close": [729.46, 741.69, 742.95]},
                         index=pd.to_datetime(["2026-07-29", "2026-07-30", "2026-07-31"]))
    for grp, name, df in (("polygon_gex", f"summary_{sym}", src),
                          ("cboe", f"gex_{sym}", tgt), ("yahoo", sym, yahoo)):
        (tmp_path / grp).mkdir(parents=True, exist_ok=True)
        df.to_parquet(tmp_path / grp / f"{name}.parquet")

    with pytest.raises(bf.BackfillPreconditionError, match="ambiguous"):
        bf.backfill(symbols=(sym,))
    assert pd.Timestamp(bf.SESSION) not in _store.read("cboe", f"gex_{sym}").index
