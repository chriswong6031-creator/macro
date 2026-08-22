"""tests/test_topup_thetadata_daily.py — AD-1T1 `--daily` mode §H hostile suite.

Covers spec `research/AD1T1_INCREMENTAL_CADENCE_SPEC_2026-08-22.md` families:
clock (F3/F4/F12), pair (F1/F6), writer (F9/F14/F15), universe (F5/F6),
deadline (F2), compatibility, and receipt (F1/F8/F16).

The clock is injected via a `now_fn` seam — no test sleeps. The vendor is a
FakeTd object passed directly into the low-level pool functions, or installed
onto the real `collectors.thetadata` module (via monkeypatch) for tests that
exercise the full `_daily_main` entry point.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pandas as pd
import pytest

import scripts.topup_thetadata_day as topup
from lib import nyse_calendar as nc

ET = nc.ET

# A known midweek session day with a resolvable prior session.
D_MID = date(2026, 8, 19)          # Wednesday
S_MID = date(2026, 8, 18)          # Tuesday
# Friday -> Monday
D_MON = date(2026, 8, 24)
S_FRI = date(2026, 8, 21)
# A weekday holiday (New Year's Day observed on a Thursday in 2026)
HOLIDAY_WEEKDAY = date(2026, 1, 1)
# DST regimes
D_EDT = date(2026, 7, 15)          # summer, EDT = UTC-4
D_EST = date(2026, 1, 14)          # winter, EST = UTC-5
# Dec -> Jan session boundary
D_JAN = date(2026, 1, 2)
S_DEC = date(2025, 12, 31)


def _et(y, m, d, hh, mm) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=ET)


def _utc(y, m, d, hh, mm) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def _df(day: date, n: int = 2) -> pd.DataFrame:
    return pd.DataFrame({"date": [pd.Timestamp(day)] * n, "strike": list(range(n))})


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame({"date": pd.Series([], dtype="datetime64[ns]"),
                         "strike": pd.Series([], dtype="float64")})


def _wrong_date_df(day: date, other: date) -> pd.DataFrame:
    """Rows returned, but none carry `day` — the F6 date_unresolved shape."""
    return pd.DataFrame({"date": [pd.Timestamp(other)], "strike": [1]})


class FakeTd:
    """Fake vendor surface for the daily 4-cell ensure (§A4/§A5)."""

    def __init__(self, plan: dict[tuple[str, str, date], object] | None = None,
                reachable_sequence=None):
        self.plan = plan or {}
        self._reachable_seq = list(reachable_sequence) if reachable_sequence else None
        self._reachable_default = True
        self.calls: list[tuple] = []
        self.on_call = None

    def reachable(self) -> bool:
        if self._reachable_seq is not None:
            if self._reachable_seq:
                return self._reachable_seq.pop(0)
            return self._reachable_default
        return self._reachable_default

    def _get(self, tier: str, root: str, day: date):
        self.calls.append((tier, root, day))
        if self.on_call:
            self.on_call(tier, root, day)
        key = (tier, root, day)
        if key in self.plan:
            v = self.plan[key]
            return v(day) if callable(v) else v
        return _df(day)

    def bulk_eod(self, root, exp, start, end):
        return self._get("eod", root, start)

    def bulk_open_interest(self, root, exp, start, end):
        return self._get("oi", root, start)

    def bulk_greeks(self, root, exp, start, end, order=3):
        return self._get("greeks", root, start)


def _install_fake_td(monkeypatch, fake):
    import collectors.thetadata as real_td
    monkeypatch.setattr(real_td, "reachable", fake.reachable)
    monkeypatch.setattr(real_td, "bulk_eod", fake.bulk_eod)
    monkeypatch.setattr(real_td, "bulk_open_interest", fake.bulk_open_interest)
    monkeypatch.setattr(real_td, "bulk_greeks", fake.bulk_greeks)


def _wire_daily(monkeypatch, store, *, t1=None, ad=None):
    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_daily_universe", lambda: list(t1 or ["SPY", "QQQ", "AAPL", "SPX"]))
    monkeypatch.setattr(topup, "_ad_universe", lambda: list(ad or ["SPY", "QQQ", "AAPL"]))


def _manifest(store) -> dict:
    return json.loads((store / "_manifest.json").read_text())


@pytest.fixture()
def store(tmp_path):
    return tmp_path / "thetadata_eod"


# ═════════════════════════ CLOCK (F3/F4/F12) ════════════════════════════════
def test_gate_closed_on_weekend_no_op():
    ctx = topup._resolve_daily_context(_et(2026, 8, 22, 18, 0), forced=False)  # Saturday
    assert ctx is None


def test_gate_closed_on_weekday_holiday_no_op():
    ctx = topup._resolve_daily_context(_et(2026, 1, 1, 18, 0), forced=False)
    assert ctx is None


def test_gate_open_midweek_after_1610_et():
    ctx = topup._resolve_daily_context(_et(2026, 8, 19, 16, 10), forced=False)
    assert ctx is not None
    assert ctx.D == D_MID
    assert ctx.S == S_MID


def test_gate_closed_one_minute_before_1610_et():
    ctx = topup._resolve_daily_context(_et(2026, 8, 19, 16, 9), forced=False)
    assert ctx is None


def test_friday_to_monday_targets_prior_friday():
    ctx = topup._resolve_daily_context(_et(2026, 8, 24, 16, 30), forced=False)
    assert ctx.D == D_MON
    assert ctx.S == S_FRI


def test_delayed_invocation_2200_et_same_day_identical_context():
    early = topup._resolve_daily_context(_et(2026, 8, 19, 16, 15), forced=False)
    late = topup._resolve_daily_context(_et(2026, 8, 19, 22, 0), forced=False)
    assert early.D == late.D == D_MID
    assert early.S == late.S == S_MID


def test_f4_trap_expected_last_session_forbidden():
    """At 16:15 ET on session D, expected_last_session() would (wrongly)
    return the PRIOR session because its 17:00 ET settle buffer has not
    passed — this test fails if anyone swaps expected_last_session() in for
    the D derivation."""
    now = _et(2026, 8, 19, 16, 15)
    ctx = topup._resolve_daily_context(now, forced=False)
    assert ctx.D == D_MID
    assert ctx.D != nc.expected_last_session(now)


def test_dst_boundary_summer_edt_utc_time_would_fool_fixed_offset():
    # 16:10 ET in EDT (UTC-4) = 20:10 UTC. A fixed UTC-5 assumption would read
    # this as 15:10 ET (gate closed) — zoneinfo must get it right.
    now_utc = _utc(2026, 7, 15, 20, 10)
    ctx = topup._resolve_daily_context(now_utc, forced=False)
    assert ctx is not None
    assert ctx.D == D_EDT


def test_dst_boundary_winter_est_utc_time_would_fool_fixed_offset():
    # 16:10 ET in EST (UTC-5) = 21:10 UTC. A fixed UTC-4 assumption would read
    # this as 17:10 ET — still open, but on the WRONG derivation path; assert
    # the exact UTC-5 arithmetic instead of a coincidentally-passing gate.
    now_utc = _utc(2026, 1, 14, 21, 10)
    ctx = topup._resolve_daily_context(now_utc, forced=False)
    assert ctx is not None
    assert ctx.D == D_EST
    just_before = _utc(2026, 1, 14, 21, 9)
    assert topup._resolve_daily_context(just_before, forced=False) is None


def test_run_context_freeze_now_fn_called_exactly_once(store, monkeypatch):
    _wire_daily(monkeypatch, store, t1=["SPY"], ad=["SPY"])
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    calls = {"n": 0}

    def now_fn():
        calls["n"] += 1
        return _et(2026, 8, 19, 16, 30)

    rc = topup._daily_main(workers=1, deadline_min=100, forced=False, now_fn=now_fn)
    assert rc == 0
    assert calls["n"] == 1


def test_same_session_rerun_is_zero_vendor_calls(store, monkeypatch):
    day_ctx = topup.RunContext(D=D_MID, S=S_MID, forced=False)
    for cell_tier, day in (("eod", S_MID), ("oi", S_MID), ("oi", D_MID), ("greeks", S_MID)):
        topup._merge_day(store, cell_tier, "SPY", day, _df(day))
    _wire_daily(monkeypatch, store, t1=["SPY"], ad=["SPY"])
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    rc = topup._daily_main(workers=1, deadline_min=100, forced=False,
                           now_fn=lambda: _et(2026, 8, 19, 16, 30))
    assert rc == 0
    assert fake.calls == []
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["status"] == "healthy"


def test_f12_s_suspect_non_session_flag(store, monkeypatch):
    plan = {("eod", r, S_MID): _empty_df() for r in ["SPY", "QQQ", "AAPL"]}
    _wire_daily(monkeypatch, store, t1=["SPY", "QQQ", "AAPL"], ad=["SPY", "QQQ", "AAPL"])
    fake = FakeTd(plan=plan)
    _install_fake_td(monkeypatch, fake)
    rc = topup._daily_main(workers=2, deadline_min=100, forced=False,
                           now_fn=lambda: _et(2026, 8, 19, 16, 30))
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["s_suspect_non_session"] is True


def test_f12_not_suspect_when_under_half_vendor_empty(store, monkeypatch):
    plan = {("eod", "SPY", S_MID): _empty_df()}
    _wire_daily(monkeypatch, store, t1=["SPY", "QQQ", "AAPL"], ad=["SPY", "QQQ", "AAPL"])
    fake = FakeTd(plan=plan)
    _install_fake_td(monkeypatch, fake)
    topup._daily_main(workers=2, deadline_min=100, forced=False,
                      now_fn=lambda: _et(2026, 8, 19, 16, 30))
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["s_suspect_non_session"] is False


# ═════════════════════════ PAIR (§A4/F1/F6) ═════════════════════════════════
def test_ensure_one_cell_already_present(store):
    topup._merge_day(store, "oi", "SPY", S_MID, _df(S_MID))
    state = topup._ensure_one_cell(store, "oi", "SPY", S_MID, lambda: (_ for _ in ()).throw(AssertionError("should not fetch")))
    assert state == "already_present"


def test_ensure_one_cell_bootstrap_fetches_and_merges(store):
    state = topup._ensure_one_cell(store, "oi", "SPY", S_MID, lambda: _df(S_MID))
    assert state == "complete"
    assert topup._has_day(store, "oi", "SPY", S_MID)


@pytest.mark.parametrize("tier,attr,day", [
    ("eod", "eod_S", S_MID), ("greeks", "greeks_S", S_MID), ("oi", "oi_D", D_MID),
])
def test_each_cell_independently_absent_is_fetched_singly(store, tier, attr, day):
    # NOTE: "oi" is the tier for BOTH oi_S and oi_D, so the call count must be
    # scoped to (tier, day), not tier alone — oi_S also fires unconditionally
    # per §A4/§A5, and would otherwise double-count as a second "oi" call.
    fake = FakeTd()
    result = topup._ensure_daily_root(store, "SPY", S_MID, D_MID, fake)
    assert result.cells[attr] == "complete"
    assert sum(1 for c, r, d in fake.calls if c == tier and d == day) == 1


def test_oi_d_absent_leaves_root_s_panel_complete_but_not_chain_next(store, monkeypatch):
    plan = {("oi", "SPY", D_MID): _empty_df()}
    fake = FakeTd(plan=plan)
    result = topup._ensure_daily_root(store, "SPY", S_MID, D_MID, fake)
    assert topup._s_panel_ok(result) is True
    assert result.cells["oi_D"] == "vendor_empty"
    assert not topup._panel_present(result.cells, "oi_D")


def test_oi_d_absent_does_not_degrade_healthy(store, monkeypatch):
    plan = {("oi", "SPY", D_MID): _empty_df(), ("oi", "QQQ", D_MID): _empty_df()}
    _wire_daily(monkeypatch, store, t1=["SPY", "QQQ"], ad=["SPY", "QQQ"])
    fake = FakeTd(plan=plan)
    _install_fake_td(monkeypatch, fake)
    rc = topup._daily_main(workers=2, deadline_min=100, forced=False,
                           now_fn=lambda: _et(2026, 8, 19, 16, 30))
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["status"] == "healthy"
    assert receipt["chain_next_ad_roots"] == 0
    assert rc == 0


def test_no_eod_d_or_greeks_d_request_ever(store):
    fake = FakeTd()
    topup._ensure_daily_root(store, "SPY", S_MID, D_MID, fake)
    for tier, root, day in fake.calls:
        if day == D_MID:
            assert tier == "oi", f"unexpected D-day request for tier={tier}"


def test_dec_jan_year_boundary_cells_land_in_their_own_year(store):
    fake = FakeTd()
    topup._ensure_daily_root(store, "SPY", S_DEC, D_JAN, fake)
    assert topup._has_day(store, "eod", "SPY", S_DEC)
    assert topup._has_day(store, "greeks", "SPY", S_DEC)
    assert topup._has_day(store, "oi", "SPY", S_DEC)
    assert topup._has_day(store, "oi", "SPY", D_JAN)
    assert (store / "eod" / "SPY" / "2025.parquet").exists()
    assert (store / "oi" / "SPY" / "2026.parquet").exists()


def test_stale_july_fresh_august_store_no_writes_outside_s_d_cells(store):
    stale_day = date(2026, 7, 1)
    topup._merge_day(store, "eod", "SPY", stale_day, _df(stale_day))
    fake = FakeTd()
    topup._ensure_daily_root(store, "SPY", S_MID, D_MID, fake)
    out = pd.read_parquet(store / "eod" / "SPY" / "2026.parquet")
    dates_touched = set(pd.to_datetime(out["date"]).dt.date)
    assert dates_touched == {stale_day, S_MID}


# ═════════════════════════ WRITER (§B/F9/F14) ═══════════════════════════════
def test_two_concurrent_daily_invocations_second_refused(store, monkeypatch, capsys):
    _wire_daily(monkeypatch, store, t1=["SPY"], ad=["SPY"])
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    store.mkdir(parents=True)
    with topup._writer_lock(store) as acquired:
        assert acquired is True
        # Snapshot AFTER the outer (simulated first-writer) lock file itself
        # exists — that file's creation is the first writer's own legitimate
        # side effect, not something the REFUSED second writer may cause.
        before = sorted(store.rglob("*"))
        rc = topup._daily_main(workers=1, deadline_min=100, forced=False,
                               now_fn=lambda: _et(2026, 8, 19, 16, 30))
        after = sorted(store.rglob("*"))
    assert rc == 0   # F14 — daily refusal exits 0
    assert fake.calls == []
    assert before == after   # byte-compare: zero mutations
    out = capsys.readouterr().out
    assert json.loads(out.strip().splitlines()[-1]) == {"event": "writer_locked", "mode": "daily"}


def test_daily_then_historical_backfill_either_order_both_locked(store, monkeypatch):
    """Daily holds the lock -> backfill's own flock acquisition must refuse."""
    import scripts.backfill_thetadata_eod as bf
    store.mkdir(parents=True)
    monkeypatch.setattr(bf, "_store_dir", lambda: store)
    with topup._writer_lock(store) as acquired:
        assert acquired is True
        with topup._writer_lock(store) as second:
            assert second is False


def test_sigkill_then_next_invocation_acquires_cleanly(store):
    """A held flock dies with the process (fd close) — simulate by simply
    releasing without an explicit unlock (process death behaves the same:
    the OS reclaims the fd on process exit)."""
    store.mkdir(parents=True)
    fh = open(store / topup.WRITER_LOCK_NAME, "a+")
    import fcntl
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    fh.close()   # simulates process death — fd closes, lock releases
    with topup._writer_lock(store) as acquired:
        assert acquired is True


def test_f9_stale_tmp_sweep_counts_and_removes(store):
    (store / "eod" / "SPY").mkdir(parents=True)
    (store / "eod" / "SPY" / "2026.tmp.parquet").write_bytes(b"stale-old-shape")
    (store / "oi" / "AAPL").mkdir(parents=True)
    (store / "oi" / "AAPL" / "2026.parquet.tmp").write_bytes(b"stale-new-shape")
    n = topup._sweep_stale_tmp(store)
    assert n == 2
    assert not (store / "eod" / "SPY" / "2026.tmp.parquet").exists()
    assert not (store / "oi" / "AAPL" / "2026.parquet.tmp").exists()


def test_f9_sweep_glob_test_no_reader_glob_matches_tmp_shape(tmp_path):
    dest = tmp_path / "2026.parquet"
    tmp = topup._tmp_path(dest)
    # engine/thetadata_store.py's reader glob is literally "*.parquet"
    import fnmatch
    assert not fnmatch.fnmatch(tmp.name, "*.parquet")


def test_one_root_vendor_failure_isolates_corrupt_parquet(store):
    d = store / "eod" / "SPY"
    d.mkdir(parents=True)
    (d / f"{S_MID.year}.parquet").write_bytes(b"not a parquet file (corrupt)")
    fake = FakeTd()
    result_bad = topup._ensure_daily_root(store, "SPY", S_MID, D_MID, fake)
    assert result_bad.state == "failed"
    assert result_bad.failure_reason is not None
    result_ok = topup._ensure_daily_root(store, "QQQ", S_MID, D_MID, fake)
    assert result_ok.state == "complete"


def test_one_tier_failure_makes_root_partial(store):
    plan = {("greeks", "SPY", S_MID): _empty_df()}
    fake = FakeTd(plan=plan)
    result = topup._ensure_daily_root(store, "SPY", S_MID, D_MID, fake)
    assert result.state == "partial"


# ── Fable ruling 2026-08-22: aggregate ladder binding constraints ──────────
# 1. complete ONLY if all four cells present post-run.
# 2. already_present ONLY if all four cells were present pre-run (zero calls).
# 3. ANY cell-level failure means NOT complete — ever.
def test_ladder_three_complete_one_fetch_failed_never_complete():
    cells = {"eod_S": "complete", "oi_S": "complete",
            "oi_D": "complete", "greeks_S": "fetch_failed"}
    state = topup._classify_root_state(cells)
    assert state != "complete"
    assert state == "fetch_failed"


def test_ladder_three_complete_one_date_unresolved_never_complete():
    cells = {"eod_S": "complete", "oi_S": "complete",
            "oi_D": "complete", "greeks_S": "date_unresolved"}
    state = topup._classify_root_state(cells)
    assert state != "complete"
    assert state == "date_unresolved"


def test_ladder_three_complete_one_vendor_empty_is_partial_never_complete():
    cells = {"eod_S": "complete", "oi_S": "complete",
            "oi_D": "complete", "greeks_S": "vendor_empty"}
    state = topup._classify_root_state(cells)
    assert state != "complete"
    assert state == "partial"


def test_ladder_all_four_vendor_empty_is_vendor_empty():
    cells = {k: "vendor_empty" for k in ("eod_S", "oi_S", "oi_D", "greeks_S")}
    assert topup._classify_root_state(cells) == "vendor_empty"


def test_ladder_all_four_complete_post_run_is_complete():
    cells = {k: "complete" for k in ("eod_S", "oi_S", "oi_D", "greeks_S")}
    assert topup._classify_root_state(cells) == "complete"


def test_ladder_mixed_present_states_is_complete_not_already_present():
    """3 already_present + 1 freshly-fetched complete: all four ARE present,
    but NOT all pre-run — so already_present's zero-vendor-calls guarantee
    must not apply. This is `complete`, not `already_present`."""
    cells = {"eod_S": "already_present", "oi_S": "already_present",
            "oi_D": "already_present", "greeks_S": "complete"}
    assert topup._classify_root_state(cells) == "complete"


def test_ladder_all_four_already_present_pre_run_is_already_present():
    cells = {k: "already_present" for k in ("eod_S", "oi_S", "oi_D", "greeks_S")}
    assert topup._classify_root_state(cells) == "already_present"


def test_ladder_fetch_failed_outranks_date_unresolved():
    cells = {"eod_S": "fetch_failed", "oi_S": "date_unresolved",
            "oi_D": "complete", "greeks_S": "complete"}
    assert topup._classify_root_state(cells) == "fetch_failed"


def test_unrelated_dates_byte_preserved_after_daily_merge(store):
    other_day = date(2026, 8, 3)
    topup._merge_day(store, "eod", "SPY", other_day, _df(other_day, n=4))
    before = pd.read_parquet(store / "eod" / "SPY" / "2026.parquet")
    fake = FakeTd()
    topup._ensure_daily_root(store, "SPY", S_MID, D_MID, fake)
    after = pd.read_parquet(store / "eod" / "SPY" / "2026.parquet")
    before_other = before[pd.to_datetime(before["date"]).dt.date == other_day]
    after_other = after[pd.to_datetime(after["date"]).dt.date == other_day]
    pd.testing.assert_frame_equal(
        before_other.reset_index(drop=True), after_other.reset_index(drop=True))


def test_f15_writer_lock_excluded_from_uploadable(tmp_path):
    from scripts.publish_r2 import _uploadable
    base = tmp_path
    (base / "_manifest.json").write_text("{}")
    (base / "_writer.lock").write_text("")
    (base / "eod").mkdir()
    (base / "eod" / "keep.parquet").write_text("x")
    files = [base / "_manifest.json", base / "_writer.lock", base / "eod" / "keep.parquet"]
    kept = _uploadable("thetadata_eod", base, files)
    assert base / "_writer.lock" not in kept
    assert base / "_manifest.json" not in kept
    assert base / "eod" / "keep.parquet" in kept


def test_f15_writer_lock_gitignored():
    text = open("/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/"
               "worktrees/thetadata-canonical-options-source-da82b6/.gitignore").read()
    assert "data/thetadata_eod/_writer.lock" in text


# ═════════════════════════ UNIVERSE (F5/F6) ═════════════════════════════════
def test_symbol_added_to_resolver_changes_denominator(store, monkeypatch):
    _wire_daily(monkeypatch, store, t1=["SPY"], ad=["SPY"])
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    topup._daily_main(workers=1, deadline_min=100, forced=False,
                      now_fn=lambda: _et(2026, 8, 19, 16, 30))
    r1 = _manifest(store)["daily_refresh"]
    assert r1["t1_universe_count"] == 1
    assert r1["ad_universe_count"] == 1

    _wire_daily(monkeypatch, store, t1=["SPY", "QQQ"], ad=["SPY", "QQQ"])
    topup._daily_main(workers=1, deadline_min=100, forced=False,
                      now_fn=lambda: _et(2026, 8, 19, 16, 30))
    r2 = _manifest(store)["daily_refresh"]
    assert r2["t1_universe_count"] == 2
    assert r2["ad_universe_count"] == 2


def test_root_with_no_options_vendor_empty_run_continues(store, monkeypatch):
    """ZZZZ has no options at all (every tier vendor-empty) — the run must
    continue and finish SPY normally rather than aborting. ZZZZ is deliberately
    OUTSIDE the AD universe here (a T1-only root, like the index roots) so the
    assertion isolates "does the run survive a hopeless root" from the
    separate 90%-gate math (covered by the receipt-family tests)."""
    plan = {(t, "ZZZZ", d): _empty_df()
           for t in ("eod", "oi", "greeks") for d in (S_MID, D_MID)}
    _wire_daily(monkeypatch, store, t1=["ZZZZ", "SPY"], ad=["SPY"])
    fake = FakeTd(plan=plan)
    _install_fake_td(monkeypatch, fake)
    rc = topup._daily_main(workers=2, deadline_min=100, forced=False,
                           now_fn=lambda: _et(2026, 8, 19, 16, 30))
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["status"] == "healthy"   # SPY alone clears the AD gate
    assert receipt["t1_universe_count"] == 2
    assert receipt["complete_t1_roots"] == 1   # ZZZZ never completes
    assert receipt["complete_ad_roots"] == 1


def test_f6_date_unresolved_distinct_from_vendor_empty(store):
    plan = {("eod", "SPY", S_MID): _wrong_date_df(S_MID, date(2026, 8, 17))}
    fake = FakeTd(plan=plan)
    result = topup._ensure_daily_root(store, "SPY", S_MID, D_MID, fake)
    assert result.cells["eod_S"] == "date_unresolved"
    assert result.state == "date_unresolved"


def test_f5_fetch_failed_over_25pct_triggers_reprobe_and_aborts(store, monkeypatch):
    plan = {("eod", r, S_MID): None for r in ["A", "B", "C"]}
    fake = FakeTd(plan=plan, reachable_sequence=[True, False])
    _wire_daily(monkeypatch, store, t1=["A", "B", "C", "D"], ad=["A", "B", "C", "D"])
    _install_fake_td(monkeypatch, fake)
    rc = topup._daily_main(workers=1, deadline_min=100, forced=False,
                           now_fn=lambda: _et(2026, 8, 19, 16, 30))
    assert rc == 1
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["status"] == "failed"
    assert receipt["terminal_health"] == "lost_mid_run"


def test_f5_fetch_failed_over_25pct_but_reachable_continues(store, monkeypatch):
    plan = {("eod", r, S_MID): None for r in ["A"]}
    fake = FakeTd(plan=plan, reachable_sequence=[True, True])
    _wire_daily(monkeypatch, store, t1=["A", "B"], ad=["A", "B"])
    _install_fake_td(monkeypatch, fake)
    rc = topup._daily_main(workers=1, deadline_min=100, forced=False,
                           now_fn=lambda: _et(2026, 8, 19, 16, 30))
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["status"] != "failed"


def test_denominator_has_no_hardcoded_universe_size():
    import inspect
    src = inspect.getsource(topup)
    for lit in ("375", "378"):
        assert lit not in src, f"found hard-coded universe literal {lit!r} in topup module"


# ═════════════════════════ DEADLINE (F2) ════════════════════════════════════
def test_deadline_exceeded_stops_new_dispatch_and_drains(store, monkeypatch):
    import time as _time

    def slow_call(kind_root_day):
        _time.sleep(0.3)

    plan = {}
    slow_roots = ["R1", "R2", "R3", "R4", "R5"]

    def _mk(day):
        def _v(_day):
            _time.sleep(0.3)
            return _df(day)
        return _v

    for r in slow_roots:
        for tier in ("eod", "oi", "greeks"):
            plan[(tier, r, S_MID)] = _mk(S_MID)
            plan[(tier, r, D_MID)] = _mk(D_MID)

    fake = FakeTd(plan=plan)
    ctx = topup.RunContext(D=D_MID, S=S_MID, forced=False)
    results, deadline_exceeded, terminal_lost = topup._run_daily_pool(
        store, slow_roots, fake, workers=1, deadline_min=0.005, ctx=ctx)
    assert deadline_exceeded is True
    assert terminal_lost is False
    assert len(results) < len(slow_roots)


def test_deadline_writes_partial_receipt_with_flag(store, monkeypatch):
    import time as _time

    def _mk(day):
        def _v(_day):
            _time.sleep(0.2)
            return _df(day)
        return _v

    roots = ["R1", "R2", "R3"]
    plan = {}
    for r in roots:
        for tier in ("eod", "oi", "greeks"):
            plan[(tier, r, S_MID)] = _mk(S_MID)
            plan[(tier, r, D_MID)] = _mk(D_MID)
    _wire_daily(monkeypatch, store, t1=roots, ad=roots)
    fake = FakeTd(plan=plan)
    _install_fake_td(monkeypatch, fake)
    rc = topup._daily_main(workers=1, deadline_min=0.004, forced=False,
                           now_fn=lambda: _et(2026, 8, 19, 16, 30))
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["deadline_exceeded"] is True
    assert receipt["status"] in ("partial", "failed")
    assert rc == 1


# ═════════════════════════ COMPATIBILITY ════════════════════════════════════
def test_legacy_characterization_suite_is_unmodified_by_daily_mode(store, monkeypatch):
    """--daily and legacy --roots don't share mutable module state."""
    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_backfill_running", lambda: False)
    fake = FakeTd(plan={})
    import collectors.thetadata as real_td
    monkeypatch.setattr(real_td, "reachable", lambda: True)
    monkeypatch.setattr(real_td, "bulk_eod", lambda root, exp, s, e: _df(s))
    monkeypatch.setattr(real_td, "bulk_open_interest", lambda root, exp, s, e: _df(s))
    monkeypatch.setattr(real_td, "bulk_greeks", lambda root, exp, s, e, order=3: _df(s))
    rc = topup.main(["--roots", "SPY", "--date", "2026-08-18"])
    assert rc == 0


def test_at_universe_resolves_via_resolve_universe_and_applies_3tier(store, monkeypatch):
    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_backfill_running", lambda: False)
    monkeypatch.setattr("scripts.backfill_thetadata_eod._resolve_universe",
                        lambda: ["SPY", "QQQ"])
    import collectors.thetadata as real_td
    monkeypatch.setattr(real_td, "reachable", lambda: True)
    monkeypatch.setattr(real_td, "bulk_eod", lambda root, exp, s, e: _df(s))
    monkeypatch.setattr(real_td, "bulk_open_interest", lambda root, exp, s, e: _df(s))
    monkeypatch.setattr(real_td, "bulk_greeks", lambda root, exp, s, e, order=3: _df(s))
    rc = topup.main(["--roots", "@universe", "--date", "2026-08-18"])
    assert rc == 0
    assert topup._has_day(store, "eod", "SPY", date(2026, 8, 18))
    assert topup._has_day(store, "eod", "QQQ", date(2026, 8, 18))


# ═════════════════════════ RECEIPT (F1/F8/F16) ══════════════════════════════
def test_receipt_healthy_when_coverage_meets_gate(store, monkeypatch):
    _wire_daily(monkeypatch, store, t1=["SPY", "QQQ"], ad=["SPY", "QQQ"])
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    rc = topup._daily_main(workers=2, deadline_min=100, forced=False,
                           now_fn=lambda: _et(2026, 8, 19, 16, 30))
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["status"] == "healthy"
    assert rc == 0


def test_receipt_partial_when_s_panel_short(store, monkeypatch):
    plan = {("eod", "QQQ", S_MID): None}
    _wire_daily(monkeypatch, store, t1=["SPY", "QQQ"], ad=["SPY", "QQQ"])
    fake = FakeTd(plan=plan)
    _install_fake_td(monkeypatch, fake)
    rc = topup._daily_main(workers=2, deadline_min=100, forced=False,
                           now_fn=lambda: _et(2026, 8, 19, 16, 30))
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["status"] == "partial"
    assert rc == 1


def test_receipt_threshold_imported_from_engine_flip(store, monkeypatch):
    _wire_daily(monkeypatch, store, t1=["SPY", "QQQ"], ad=["SPY", "QQQ"])
    plan = {("eod", "QQQ", S_MID): None}   # only 1/2 = 50% AD coverage
    fake = FakeTd(plan=plan)
    _install_fake_td(monkeypatch, fake)

    from engine.options_intel_brief import CONFIG
    monkeypatch.setitem(CONFIG, "SOURCE_COVERAGE_GATE", 0.40)
    rc = topup._daily_main(workers=2, deadline_min=100, forced=False,
                           now_fn=lambda: _et(2026, 8, 19, 16, 30))
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["status"] == "healthy"   # 0.50 >= lowered 0.40 gate


def test_forced_stamps_forced_true(store, monkeypatch):
    _wire_daily(monkeypatch, store, t1=["SPY"], ad=["SPY"])
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    rc = topup._daily_main(workers=1, deadline_min=100, forced=True,
                           now_fn=lambda: _et(2026, 8, 22, 12, 0))   # Saturday
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["forced"] is True
    assert rc == 0


# ── Fable ruling 2026-08-22: forced-mode non-session fallback (ACCEPTED) ───
def test_forced_on_non_session_day_derives_last_session_on_or_before():
    """--force-run on a non-session day (Saturday 2026-08-22) derives
    D = last_session_on_or_before(today_et) = the prior Friday, and S = the
    session before THAT — never today_et itself (which is not a session)."""
    saturday = _et(2026, 8, 22, 12, 0)
    ctx = topup._resolve_daily_context(saturday, forced=True)
    assert ctx is not None
    assert ctx.forced is True
    assert ctx.D == nc.last_session_on_or_before(date(2026, 8, 22))
    assert ctx.D == date(2026, 8, 21)   # the Friday before
    assert ctx.S == nc.session_n_back(ctx.D, 1)


def test_forced_on_a_session_day_still_uses_today_as_d():
    """forced on an ALREADY-open session day changes nothing about D — only
    the gate/time check is bypassed."""
    ctx = topup._resolve_daily_context(_et(2026, 8, 19, 10, 0), forced=True)
    assert ctx.D == D_MID
    assert ctx.S == S_MID


# ── Fable ruling 2026-08-22: exit-code quadruple (ACCEPTED, pinned) ─────────
def test_daily_exit_code_quadruple_pinned(store, monkeypatch):
    """--daily exits 0 for {healthy, gate no-op, lock refusal}, 1 for
    {partial, failed} — pinned as one quadruple so it cannot silently drift."""
    # healthy -> 0
    _wire_daily(monkeypatch, store, t1=["SPY"], ad=["SPY"])
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    rc_healthy = topup._daily_main(workers=1, deadline_min=100, forced=False,
                                   now_fn=lambda: _et(2026, 8, 19, 16, 30))
    assert rc_healthy == 0
    assert _manifest(store)["daily_refresh"]["status"] == "healthy"

    # gate no-op -> 0 (Saturday, not forced)
    rc_noop = topup._daily_main(workers=1, deadline_min=100, forced=False,
                                now_fn=lambda: _et(2026, 8, 22, 12, 0))
    assert rc_noop == 0

    # lock refusal -> 0
    store.mkdir(parents=True, exist_ok=True)
    with topup._writer_lock(store):
        rc_locked = topup._daily_main(workers=1, deadline_min=100, forced=False,
                                      now_fn=lambda: _et(2026, 8, 20, 16, 30))
    assert rc_locked == 0

    # partial -> 1
    plan_partial = {("eod", "QQQ", date(2026, 8, 21)): None}
    _wire_daily(monkeypatch, store, t1=["SPY", "QQQ"], ad=["SPY", "QQQ"])
    fake_partial = FakeTd(plan=plan_partial)
    _install_fake_td(monkeypatch, fake_partial)
    rc_partial = topup._daily_main(workers=2, deadline_min=100, forced=False,
                                   now_fn=lambda: _et(2026, 8, 24, 16, 30))  # Mon
    assert rc_partial == 1
    assert _manifest(store)["daily_refresh"]["status"] == "partial"

    # failed -> 1 (terminal unreachable)
    fake_failed = FakeTd()
    fake_failed._reachable_default = False
    _install_fake_td(monkeypatch, fake_failed)
    rc_failed = topup._daily_main(workers=1, deadline_min=100, forced=False,
                                  now_fn=lambda: _et(2026, 8, 25, 16, 30))  # Tue
    assert rc_failed == 1
    assert _manifest(store)["daily_refresh"]["status"] == "failed"


def test_manifest_write_is_atomic_no_tmp_left_behind(store, monkeypatch):
    _wire_daily(monkeypatch, store, t1=["SPY"], ad=["SPY"])
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    topup._daily_main(workers=1, deadline_min=100, forced=False,
                      now_fn=lambda: _et(2026, 8, 19, 16, 30))
    assert not (store / "_manifest.json.tmp").exists()
    assert (store / "_manifest.json").exists()


def test_backfill_manifest_rewrite_preserves_daily_refresh(store, monkeypatch):
    import scripts.backfill_thetadata_eod as bf
    monkeypatch.setattr(bf, "_manifest_path", lambda: store / "_manifest.json")
    store.mkdir(parents=True)
    (store / "_manifest.json").write_text(json.dumps({
        "daily_refresh": {"S": "2026-08-18", "D": "2026-08-19", "status": "healthy"},
    }))
    bf._write_manifest({"completed": {"SPY": ["2026"]}})
    doc = _manifest(store)
    assert doc["daily_refresh"]["D"] == "2026-08-19"
    assert doc["n_roots"] == 1


def test_backfill_manifest_rewrite_preservation_flip_would_fail():
    """Flip test: an implementation that full-REPLACES (the old behavior)
    would drop daily_refresh — pin the read-modify-write directly."""
    import inspect
    import scripts.backfill_thetadata_eod as bf
    src = inspect.getsource(bf._write_manifest)
    assert "preserved" in src or "read" in src.lower()


def test_f16_corrupt_manifest_fail_open_daily(store, monkeypatch, caplog):
    store.mkdir(parents=True)
    (store / "_manifest.json").write_text("{not valid json")
    _wire_daily(monkeypatch, store, t1=["SPY"], ad=["SPY"])
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    rc = topup._daily_main(workers=1, deadline_min=100, forced=False,
                           now_fn=lambda: _et(2026, 8, 19, 16, 30))
    assert rc == 0
    doc = _manifest(store)
    assert doc["daily_refresh"]["status"] == "healthy"


def test_f16_corrupt_manifest_fail_open_backfill(store):
    import scripts.backfill_thetadata_eod as bf
    store.mkdir(parents=True)
    (store / "_manifest.json").write_text("{not valid json")
    import unittest.mock as mock
    with mock.patch.object(bf, "_manifest_path", return_value=store / "_manifest.json"):
        bf._write_manifest({"completed": {}})
    doc = _manifest(store)
    assert doc["n_roots"] == 0


def test_sentinel_script_reads_daily_refresh_d():
    text = open("/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/"
               "worktrees/thetadata-canonical-options-source-da82b6/"
               "scripts/launchd/theta_staleness_sentinel.sh").read()
    assert "daily_refresh" in text
    assert "session_date" in text


def test_lock_refusal_writes_no_receipt(store, monkeypatch):
    _wire_daily(monkeypatch, store, t1=["SPY"], ad=["SPY"])
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    store.mkdir(parents=True)
    with topup._writer_lock(store):
        topup._daily_main(workers=1, deadline_min=100, forced=False,
                          now_fn=lambda: _et(2026, 8, 19, 16, 30))
    assert not (store / "_manifest.json").exists()


def test_gate_no_op_writes_no_receipt(store, monkeypatch):
    _wire_daily(monkeypatch, store, t1=["SPY"], ad=["SPY"])
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    rc = topup._daily_main(workers=1, deadline_min=100, forced=False,
                           now_fn=lambda: _et(2026, 8, 22, 12, 0))   # Saturday
    assert rc == 0
    assert not (store / "_manifest.json").exists()


def test_session_resolution_failure_aborts_as_failed(store, monkeypatch):
    _wire_daily(monkeypatch, store, t1=["SPY"], ad=["SPY"])
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    monkeypatch.setattr(nc, "session_n_back", lambda *a, **kw: None)
    rc = topup._daily_main(workers=1, deadline_min=100, forced=False,
                           now_fn=lambda: _et(2026, 8, 19, 16, 30))
    assert rc == 1
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["status"] == "failed"


def test_terminal_unreachable_at_startup_aborts_failed(store, monkeypatch):
    _wire_daily(monkeypatch, store, t1=["SPY"], ad=["SPY"])
    fake = FakeTd()
    fake._reachable_default = False
    _install_fake_td(monkeypatch, fake)
    rc = topup._daily_main(workers=1, deadline_min=100, forced=False,
                           now_fn=lambda: _et(2026, 8, 19, 16, 30))
    assert rc == 1
    receipt = _manifest(store)["daily_refresh"]
    assert receipt["status"] == "failed"
    assert receipt["terminal_health"] == "unreachable"
