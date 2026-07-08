"""China board-ORDER forward ledger — the CN-1 grader truth pass (masterplan §W6-CN).

Pins the conventions locked in the same pass as the #791 store-group fix:
  • the ledger reads the china_stocks store (per-name), not china (30 ETFs) — the dead-on-arrival
    bug that made n_graded=0 forever;
  • grading is CSI300-relative (510300.SS), fill-realistic (T+1 (H+L)/2), excludes locked-limit
    entry bars, and is NEVER anchored on a §7 marker date.
"""
import numpy as np
import pandas as pd
import pytest

from lib import config, store
from engine import china_standout_track as t


def _mk_ohlc(dates, closes, *, flat_at=None):
    """Build an OHLC frame; ``flat_at`` (index int) forces a locked-limit bar (h==l==c)."""
    closes = np.asarray(closes, dtype=float)
    df = pd.DataFrame({
        "close": closes,
        "high": closes * 1.01,
        "low": closes * 0.99,
        "volume": np.full(len(closes), 1e6),
    }, index=pd.DatetimeIndex(dates, name="Date"))
    if flat_at is not None:
        df.iloc[flat_at, [df.columns.get_loc("high"), df.columns.get_loc("low")]] = closes[flat_at]
    return df


@pytest.fixture
def cn_store(tmp_path, monkeypatch):
    """A synthetic china_stocks + china (CSI300 ETF) store 130 sessions long. Defaults the session
    guard to SETTLED (no run_status stub) so append tests are deterministic; the partial-session
    tests override read_status explicitly."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    import lib.store as lstore
    monkeypatch.setattr(lstore, "read_status", lambda: {})   # no panel stamp → assumed settled
    dates = pd.bdate_range("2026-01-01", periods=130)
    return tmp_path, dates


def test_store_group_names_resolve(cn_store):
    """The #791 fix: per-NAME board tickers resolve in china_stocks (they never do in china)."""
    tmp_path, dates = cn_store
    df = _mk_ohlc(dates, np.linspace(10, 11, len(dates)))
    store.upsert("china_stocks", "600000.SS", df)
    assert t._price_frame("600000.SS") is not None            # names resolve now
    assert store.read("china", "600000.SS") is None           # the old (broken) group is empty


def test_grade_is_csi300_relative_and_fill_realistic(cn_store):
    """A matured row is graded on the T+1 (H+L)/2 fill, EXCESS over CSI300 — matches manual math."""
    tmp_path, dates = cn_store
    name_px = 10.0 * (1.02 ** np.arange(len(dates)))          # steady +2%/session name
    bench_px = 10.0 * (1.01 ** np.arange(len(dates)))         # slower CSI300
    store.upsert("china_stocks", "600001.SS", _mk_ohlc(dates, name_px))
    store.upsert("china", t._BENCH, _mk_ohlc(dates, bench_px)[["close", "volume"]])

    d0 = dates[0]
    ex, pinned = t._fwd_excess("600001.SS", d0, 21, t._bench_close())
    # manual: fill = T+1 (H+L)/2, exit = close at +21 sessions after d0
    df = t._price_frame("600001.SS")
    t1 = df.index[df.index > d0][0]
    fill = (df.loc[t1, "high"] + df.loc[t1, "low"]) / 2.0
    fwd = df["close"][df.index > d0]
    name_ret = fwd.iloc[21] / fill - 1.0
    b = t._bench_close(); bs = b[b.index > d0]
    bench_ret = bs.iloc[21] / bs.iloc[0] - 1.0
    assert ex == pytest.approx(name_ret - bench_ret, abs=1e-9)
    assert ex > 0                                             # faster name beats CSI300


def test_locked_limit_entry_excluded(cn_store):
    """A T+1 bar that is locked limit (high==low==close) is UNFILLABLE → excluded (None), not graded."""
    tmp_path, dates = cn_store
    px = 10.0 * (1.02 ** np.arange(len(dates)))
    df = _mk_ohlc(dates, px, flat_at=1)                       # T+1 (index 1) is locked
    store.upsert("china_stocks", "600002.SS", df)
    store.upsert("china", t._BENCH, _mk_ohlc(dates, px)[["close", "volume"]])
    ex, _ = t._fwd_excess("600002.SS", dates[0], 21, t._bench_close())
    assert ex is None                                        # fabricating a fill here is forbidden


def test_pinned_reference_close_flagged_not_graded_from_pin(cn_store):
    """A board-date close pinned at its own high is FLAGGED, but the grade still uses the T+1 fill."""
    tmp_path, dates = cn_store
    px = 10.0 * (1.02 ** np.arange(len(dates)))
    df = _mk_ohlc(dates, px)
    df.iloc[0, df.columns.get_loc("high")] = df.iloc[0, df.columns.get_loc("close")]  # d0 close==high
    store.upsert("china_stocks", "600003.SS", df)
    store.upsert("china", t._BENCH, _mk_ohlc(dates, px)[["close", "volume"]])
    ex, pinned = t._fwd_excess("600003.SS", dates[0], 21, t._bench_close())
    assert pinned is True and ex is not None                 # flagged, still graded from the T+1 fill


def test_grade_never_anchors_on_marker_date_leak(cn_store):
    """SYNTHETIC LOOK-AHEAD LEAK TEST — the grade must be knowable at the board close.

    Construct a name that is FLAT up to and including the board date, then jumps the day AFTER.
    A leaky grader that resolved the label with the next bar (signal_quality.py:161 'take' rule)
    would see the jump; the honest ledger anchors on the board-date close and measures from the T+1
    FILL, so the forward return is real and forward — it must equal the manual forward-from-fill
    number, never a value that peeks at the board-date bar's own future."""
    tmp_path, dates = cn_store
    px = np.full(len(dates), 10.0)
    px[1] = 12.0                                            # the JUMP lands on the T+1 fill bar
    px[2:] = 13.0 * (1.001 ** np.arange(len(dates) - 2))    # keep drifting so fill != d0 close
    store.upsert("china_stocks", "600004.SS", _mk_ohlc(dates, px))
    store.upsert("china", t._BENCH, _mk_ohlc(dates, np.full(len(dates), 10.0))[["close", "volume"]])
    d0 = dates[0]
    ex, _ = t._fwd_excess("600004.SS", d0, 21, t._bench_close())
    df = t._price_frame("600004.SS")
    t1 = df.index[df.index > d0][0]
    fill = (df.loc[t1, "high"] + df.loc[t1, "low"]) / 2.0    # T+1 fill sees the post-jump price (~12)
    fwd = df["close"][df.index > d0]
    manual = fwd.iloc[21] / fill - 1.0                       # bench flat → excess == name return
    assert ex == pytest.approx(manual, abs=1e-9)
    # the anchor is strictly the T+1 fill (~12): the return is NOT computed off the stale d0 close
    # (10.0), which would have manufactured a spuriously LARGER "gain" the moment the name jumped.
    stale = fwd.iloc[21] / px[0] - 1.0
    assert stale > ex                                        # the leaky base overstates the return
    assert ex != pytest.approx(stale, abs=1e-3)


def test_session_guard_flags_and_refuses_partial_board(cn_store, monkeypatch):
    """A price panel collected before the A-share close settled (<07:00 UTC on the board date) is a
    PARTIAL SESSION → append_board refuses it (replacing the keep-first accident)."""
    tmp_path, dates = cn_store
    import lib.store as lstore
    monkeypatch.setattr(lstore, "read_status", lambda: {"sources": {
        "china_stocks": {"checked_at": "2026-07-02T02:37:00+00:00", "last_date": "2026-07-02"}}})
    sess = t.session_status("2026-07-02")
    assert sess["partial_session"] is True and sess["collected_hour_utc"] == 2
    n = t.append_board([{"ticker": "600000.SS", "price": 10.0}], asof="2026-07-02", lane="asia")
    assert n == 0                                          # refused — no mid-session board in the ledger
    assert not t._store_path().exists()                   # nothing was written


def test_session_guard_accepts_settled_board(cn_store, monkeypatch):
    """A panel collected AFTER the close settled (or a prior-session board) is NOT partial → appends."""
    tmp_path, dates = cn_store
    import lib.store as lstore
    monkeypatch.setattr(lstore, "read_status", lambda: {"sources": {
        "china_stocks": {"checked_at": "2026-07-02T12:30:00+00:00", "last_date": "2026-07-02"}}})
    sess = t.session_status("2026-07-02")
    assert sess["partial_session"] is False
    n = t.append_board([{"ticker": "600000.SS", "price": 10.0}], asof="2026-07-02", lane="asia")
    assert n == 1                                          # settled → logged


def test_ledger_append_gated_to_asia_lane(cn_store):
    """Explicit lane gate: a render lane (lane != 'asia') never persists a board."""
    tmp_path, dates = cn_store
    n = t.append_board([{"ticker": "600000.SS", "price": 10.0}], asof=str(dates[0].date()),
                       lane="render")
    assert n == 0 and not t._store_path().exists()
    # lane=None preserves the legacy (asia-build) call
    n2 = t.append_board([{"ticker": "600000.SS", "price": 10.0}], asof=str(dates[0].date()), lane=None)
    assert n2 == 1


def test_grade_end_to_end_publishes_conventions(cn_store):
    """grade() over a real (matured) synthetic ledger publishes the honest convention block + a
    Wilson-CI hit rate vs CSI300, and resolves prices (n>0) — proving the ledger is no longer dead."""
    tmp_path, dates = cn_store
    store.upsert("china", t._BENCH, _mk_ohlc(dates, 10.0 * (1.005 ** np.arange(len(dates))))[["close", "volume"]])
    rows = []
    rng = np.random.default_rng(0)
    for i in range(20):
        tk = f"60{i:04d}.SS"
        drift = 1.0 + (0.02 if i < 10 else 0.001)            # first 10 beat, rest lag
        store.upsert("china_stocks", tk, _mk_ohlc(dates, 10.0 * (drift ** np.arange(len(dates)))))
        rows.append({"ticker": tk, "price": 10.0, "signal": {"tier_cascade": "T2"},
                     "setup": "reversal", "extension": {"extended": i >= 10}, "washout_2w": False})
    t.append_board(rows, asof=str(dates[0].date()))
    g = t.grade()
    assert g["available"] and g["grading"]["benchmark"] == t._BENCH
    assert g["grading"]["relative"] and g["grading"]["marker_dates"] == "forbidden"
    h21 = g["by_horizon"]["21d"]
    assert h21["n"] >= t._MIN_GRADED                          # NOT perma-accruing anymore
    assert 0.0 <= h21["hit_vs_csi300"] <= 1.0
    assert h21["hit_ci"][0] <= h21["hit_vs_csi300"] <= h21["hit_ci"][1]
    assert g["n_graded"] > 0


# ---------------------------------------------------------------------------
# Interim (unrealized) mark-to-latest-close read — shown before 21d maturities land
# ---------------------------------------------------------------------------

def test_interim_excess_marks_to_latest_and_aligns_window(cn_store):
    """_interim_excess marks the T+1 fill to the LATEST close (open-ended, not a fixed horizon),
    CSI300-relative — and when the name's store is STALER than the bench it aligns BOTH to the
    name's last bar so the excess isn't measured over mismatched windows."""
    tmp_path, dates = cn_store
    store.upsert("china", t._BENCH, _mk_ohlc(dates, 10.0 * (1.005 ** np.arange(len(dates))))[["close", "volume"]])
    n_sess = 5                                                # name store ends far before the bench's
    store.upsert("china_stocks", "600100.SS", _mk_ohlc(dates[:n_sess], 10.0 * (1.03 ** np.arange(n_sess))))
    d0 = dates[0]
    ex, pinned, days = t._interim_excess("600100.SS", d0, t._bench_close())
    # manual math, aligned to the name's LAST bar (not the bench's later last)
    df = t._price_frame("600100.SS")
    t1 = df.index[df.index > d0][0]
    fill = (df.loc[t1, "high"] + df.loc[t1, "low"]) / 2.0
    common_last = df.index[-1]
    name_ret = df["close"].loc[common_last] / fill - 1.0
    bsl = t._bench_close(); bsl = bsl[(bsl.index > d0) & (bsl.index <= common_last)]
    bench_ret = bsl.iloc[-1] / bsl.iloc[0] - 1.0
    assert ex == pytest.approx(name_ret - bench_ret, abs=1e-9)
    assert days == n_sess - 1                                 # forward sessions after d0 so far
    assert ex > 0                                             # the faster name is ahead of CSI300


def test_interim_grade_publishes_unrealized_else_accruing(cn_store):
    """interim_grade aggregates the unrealized read: once >= _MIN_GRADED names resolve it publishes
    a Wilson-CI hit rate carrying the explicit unrealized flag; below that it stays 'accruing'."""
    tmp_path, dates = cn_store
    store.upsert("china", t._BENCH, _mk_ohlc(dates, 10.0 * (1.002 ** np.arange(len(dates))))[["close", "volume"]])
    rows = []
    for i in range(12):
        tk = f"60{i:04d}.SS"
        drift = 1.0 + (0.02 if i < 8 else 0.001)             # 8 beat CSI300, 4 lag
        store.upsert("china_stocks", tk, _mk_ohlc(dates[:6], 10.0 * (drift ** np.arange(6))))  # 6-session stores
        rows.append({"ticker": tk, "price": 10.0, "signal": {"tier_cascade": "T2"},
                     "setup": "reversal", "extension": {"extended": False}, "washout_2w": False})
    t.append_board(rows, asof=str(dates[0].date()))
    ig = t.interim_grade()
    assert ig["available"] and ig["unrealized"] is True
    assert ig["n"] >= t._MIN_GRADED
    assert 0.0 <= ig["hit_vs_csi300"] <= 1.0
    assert ig["hit_ci"][0] <= ig["hit_vs_csi300"] <= ig["hit_ci"][1]
    assert ig["max_days_held"] >= ig["median_days_held"] >= 1


# ---------------------------------------------------------------------------
# W0.2a — new append_board fields + grade() stratification tests
# ---------------------------------------------------------------------------

def test_append_board_w02a_new_fields_present(cn_store):
    """W0.2a: append_board logs the new schema fields (ticks, provisional, ext_score,
    washout_2w, hold_state, entry_status) via the schema-union pd.concat pattern."""
    tmp_path, dates = cn_store
    rows = [{
        "ticker": "600001.SS",
        "price": 10.0,
        "signal": {"tier_cascade": "T1", "ticks": 3, "provisional": False},
        "setup": "reversal",
        "extension": {"extended": False, "score": 0.15},
        "washout_2w": True,
        "coiled": {"coiled": True, "star": False, "cohort": 0.7, "fire": False, "fire_ticks": None},
        "hold": {"state": "intact"},
        "entry_signal": {"status": "buy_now"},
    }]
    n = t.append_board(rows, asof=str(dates[0].date()))
    assert n == 1
    df = pd.read_parquet(t._store_path())
    row = df.iloc[0]
    assert int(row["ticks"]) == 3
    assert bool(row["provisional"]) is False
    assert abs(float(row["ext_score"]) - 0.15) < 1e-9
    assert bool(row["washout_2w"]) is True
    assert str(row["hold_state"]) == "intact"
    assert str(row["entry_status"]) == "buy_now"


def test_append_board_hold_state_none_when_absent(cn_store):
    """W0.2a: hold_state is None (not a crash) when the row has no 'hold' key — the
    placeholder schema survives missing values until W0.1 wires the real HOLD builder."""
    tmp_path, dates = cn_store
    rows = [{"ticker": "600002.SS", "price": 10.0, "signal": {"tier_cascade": "T2"},
             "setup": "reversal", "extension": {"extended": False}, "washout_2w": False}]
    t.append_board(rows, asof=str(dates[0].date()))
    df = pd.read_parquet(t._store_path())
    # hold_state must be None / NaN (not a KeyError or crash)
    assert df.iloc[0].get("hold_state") is None or pd.isna(df.iloc[0].get("hold_state", None))


def test_slice_table_stratifies_correctly(cn_store):
    """W0.2a: _slice_table returns honest hit-stats per stratum; NaN grouping key → 'None'."""
    import pandas as pd
    g = pd.DataFrame({
        "tier": ["T1", "T1", "T2", "T2", None],
        "fwd": [0.05, 0.03, -0.01, 0.02, 0.01],
    })
    sliced = t._slice_table(g, "tier")
    assert set(sliced.keys()) == {"T1", "T2", "None"}
    assert sliced["T1"]["n"] == 2
    assert sliced["T1"]["hit_rate"] == 1.0                # both T1 rows beat CSI300
    assert sliced["T2"]["hit_rate"] == 0.5                # 1/2 T2 rows beat CSI300
    assert 0.0 <= sliced["T2"]["wilson_lo"] <= sliced["T2"]["hit_rate"]


def test_grade_w02a_stratification_keys_present(cn_store):
    """W0.2a: grade() by_horizon blocks include by_tier, by_washout_2w, by_coiled,
    by_hold_state, by_entry_status once the ledger matures (n >= _MIN_GRADED)."""
    tmp_path, dates = cn_store
    store.upsert("china", t._BENCH, _mk_ohlc(dates, 10.0 * (1.005 ** np.arange(len(dates))))[["close", "volume"]])
    rows = []
    for i in range(20):
        tk = f"61{i:04d}.SS"
        store.upsert("china_stocks", tk, _mk_ohlc(dates, 10.0 * ((1.02 if i < 10 else 1.001) ** np.arange(len(dates)))))
        rows.append({
            "ticker": tk, "price": 10.0,
            "signal": {"tier_cascade": "T1" if i < 10 else "T2", "ticks": i, "provisional": False},
            "setup": "reversal",
            "extension": {"extended": i >= 15, "score": 0.8 if i >= 15 else 0.1},
            "washout_2w": i < 10,
            "coiled": {"coiled": i < 5, "star": False, "cohort": 0.5, "fire": False, "fire_ticks": None},
            "entry_signal": {"status": "buy_now" if i < 15 else "extended"},
        })
    t.append_board(rows, asof=str(dates[0].date()))
    g = t.grade()
    h21 = g.get("by_horizon", {}).get("21d", {})
    assert "by_tier" in h21, "by_tier stratification missing from grade() output"
    assert "by_washout_2w" in h21, "by_washout_2w stratification missing"
    assert "by_coiled" in h21, "by_coiled stratification missing"
    assert "by_hold_state" in h21, "by_hold_state stratification missing"
    assert "by_entry_status" in h21, "by_entry_status stratification missing"
    # the T1/T2 strata actually populated (rows had both)
    if h21.get("by_tier"):
        assert "T1" in h21["by_tier"] or "T2" in h21["by_tier"]


# ===========================================================================
# W0 Stage B-d: CN-native spine axes, regime stamps, species/archetype,
# dtype hardening tests
# ===========================================================================

def _mk_ohlc_with_path(dates, closes_fn, *, flat_t1=False):
    """Build an OHLC frame where closes_fn(i) → close at bar i.
    If flat_t1=True, bar index 1 (T+1) is a locked-limit bar (h==l==c).
    """
    closes = np.array([closes_fn(i) for i in range(len(dates))], dtype=float)
    df = pd.DataFrame({
        "close": closes,
        "high": closes * 1.01,
        "low": closes * 0.99,
        "volume": np.full(len(closes), 1e6),
    }, index=pd.DatetimeIndex(dates, name="Date"))
    if flat_t1:
        df.iloc[1, df.columns.get_loc("high")] = closes[1]
        df.iloc[1, df.columns.get_loc("low")] = closes[1]
    return df


# ---------------------------------------------------------------------------
# Scope-1: CN-native terminal state from T+1 HL2 fill
# ---------------------------------------------------------------------------

def test_cn_terminal_state_clean_liftoff(cn_store):
    """A name that surges +20% within 21d from the T+1 fill → CLEAN_LIFTOFF (clean8_21)."""
    tmp_path, dates = cn_store
    # First 5 bars flat at 10, then shoot to 15 (>8%) on bar 5 → CLEAN_LIFTOFF
    closes = np.full(len(dates), 10.0)
    closes[5:] = 15.0  # +50% by bar 5 from T+1 fill
    df = _mk_ohlc(dates, closes)
    store.upsert("china_stocks", "699001.SS", df)
    d0 = dates[0]
    spine = t._cn_spine_axes("699001.SS", d0)
    assert spine["fill_basis"] == "t1_hl2"
    assert spine["terminal_state_clean8_21"] == "CLEAN_LIFTOFF", (
        f"Expected CLEAN_LIFTOFF, got {spine['terminal_state_clean8_21']}"
    )


def test_cn_terminal_state_stopped(cn_store):
    """A name that falls -6% on bar 2 from T+1 fill → STOPPED."""
    tmp_path, dates = cn_store
    closes = np.full(len(dates), 10.0)
    closes[2] = 9.3   # < 10 * 0.95 = 9.5 → STOPPED at bar 2
    df = _mk_ohlc(dates, closes)
    store.upsert("china_stocks", "699002.SS", df)
    d0 = dates[0]
    spine = t._cn_spine_axes("699002.SS", d0)
    assert spine["terminal_state_clean8_21"] == "STOPPED", (
        f"Expected STOPPED, got {spine['terminal_state_clean8_21']}"
    )


def test_cn_terminal_state_cushioned_then_stopped(cn_store):
    """A name that hits +7% (cushioned) then later drops to 94% → post_cushion_breach=True."""
    tmp_path, dates = cn_store
    # T+1 fill: bar 1, close ~10.0 (hl2)
    # Bar 3 (T+3): close = 10.75 → +7.5% > CUSHION_BARRIER (1.05) → cushioned
    # Bar 8 (T+8): close = 9.40 → < STOP_BARRIER (0.95) → stopped after cushion
    closes = np.full(len(dates), 10.0)
    closes[3] = 10.75  # cushion trigger
    closes[4:8] = 10.5
    closes[8:] = 9.4   # stop trigger after cushion
    df = _mk_ohlc(dates, closes)
    store.upsert("china_stocks", "699003.SS", df)
    d0 = dates[0]
    spine = t._cn_spine_axes("699003.SS", d0)
    # terminal_state_clean8_21: cushioned then stopped within 21 bars → STOPPED
    # (stop wins: barrier race checks stop first, cushion bar < stop bar)
    assert spine["terminal_state_clean8_21"] == "STOPPED", (
        f"Expected STOPPED (cushioned then stopped), got {spine['terminal_state_clean8_21']}"
    )
    # post_cushion_breach: cushioned (bar 3) then stop (bar 8 < fill price) → True
    assert spine["post_cushion_breach"] is True, (
        f"Expected post_cushion_breach=True, got {spine['post_cushion_breach']}"
    )


def test_cn_terminal_state_locked_limit_all_null(cn_store):
    """A locked-limit T+1 bar (h==l==c) → all spine axes are None (unfillable)."""
    tmp_path, dates = cn_store
    closes = np.full(len(dates), 10.0)
    closes[1:] = 10.8  # locked limit up: bar 1 high==low==close
    df = _mk_ohlc(dates, closes, flat_at=1)   # existing fixture helper
    store.upsert("china_stocks", "699004.SS", df)
    d0 = dates[0]
    spine = t._cn_spine_axes("699004.SS", d0)
    # fill_basis is always set even for locked rows
    assert spine["fill_basis"] == "t1_hl2"
    # All axes null (unfillable)
    assert spine["terminal_state_clean15_126"] is None
    assert spine["terminal_state_clean8_21"] is None
    assert spine["post_cushion_breach"] is None
    for h in (5, 10, 21, 63):
        assert spine[f"fwd_mfe_{h}"] is None, f"fwd_mfe_{h} should be None for locked-limit row"


def test_cn_terminal_state_straddle_stop_wins(cn_store):
    """Straddle tie: if stop and cushion both trigger on the same bar, stop wins → STOPPED."""
    tmp_path, dates = cn_store
    # This shouldn't happen since stop_mult=0.95 < cushion_mult=1.05, so a single close
    # cannot simultaneously be ≤0.95 and ≥1.05. But test that stop check runs FIRST
    # in the sequential scan (i.e., if close ≤ stop_b, it's STOPPED, not checked for cushion).
    # Simulate: bar 3 drops to exactly stop_b = fill * 0.95
    closes = np.full(len(dates), 10.0)
    fill_approx = 10.0  # T+1 hl2 with equal h/l
    closes[3] = fill_approx * 0.95  # exactly at stop barrier
    df = _mk_ohlc(dates, closes)
    store.upsert("china_stocks", "699005.SS", df)
    d0 = dates[0]
    spine = t._cn_spine_axes("699005.SS", d0)
    # Close ≤ stop_b → STOPPED; the cushion check is never reached on this bar
    assert spine["terminal_state_clean8_21"] == "STOPPED"


# ---------------------------------------------------------------------------
# Scope-1b: fwd_mfe from CN fill
# ---------------------------------------------------------------------------

def test_cn_fwd_mfe_correct(cn_store):
    """fwd_mfe_5 is the max of the 5 bars after T+2, normalized to T+1 HL2 fill."""
    tmp_path, dates = cn_store
    # T+1 fill at bar 1: high=10.1, low=9.9 → hl2 fill = 10.0
    # Bars T+2..T+6 (bars 2..6): closes = [11, 10, 9.5, 10.5, 10.2]
    # max of bars 2..6 = 11 → fwd_mfe_5 = (11 / 10.0) - 1 = 0.10
    closes = [10.0, 10.0, 11.0, 10.0, 9.5, 10.5, 10.2] + [10.2] * (len(dates) - 7)
    df = _mk_ohlc(dates, closes)
    store.upsert("china_stocks", "699010.SS", df)
    d0 = dates[0]
    spine = t._cn_spine_axes("699010.SS", d0)
    fill = (df.loc[dates[1], "high"] + df.loc[dates[1], "low"]) / 2.0
    expected_mfe5 = max(0.0, max(df.loc[dates[2:7], "close"]) / fill - 1.0)
    assert spine["fwd_mfe_5"] == pytest.approx(expected_mfe5, abs=1e-9), (
        f"Expected fwd_mfe_5={expected_mfe5}, got {spine['fwd_mfe_5']}"
    )


def test_cn_fwd_mfe_not_matured_returns_none(cn_store):
    """fwd_mfe_63 is None when fewer than 63 bars are available after T+2."""
    tmp_path, dates = cn_store
    # cn_store has 130 bars; use a date near the end so mfe_63 can't mature.
    closes = np.full(len(dates), 10.0)
    df = _mk_ohlc(dates, closes)
    store.upsert("china_stocks", "699011.SS", df)
    # Use a d0 with only ~20 bars ahead → mfe_63 can't mature but mfe_5/10 can
    d0 = dates[-25]
    spine = t._cn_spine_axes("699011.SS", d0)
    assert spine["fwd_mfe_63"] is None, "Expected None when mfe_63 can't mature"


# ---------------------------------------------------------------------------
# Scope-2: regime stamps via append_board + grade() backfill
# ---------------------------------------------------------------------------

def test_append_board_stamps_us_regime_columns(cn_store, monkeypatch):
    """append_board stamps us_* regime columns on new rows using PIT get_vector_for_date."""
    tmp_path, dates = cn_store
    # Patch regime stamp to return a controlled value
    fake_stamp = {
        "us_rate_pressure": "neutral",
        "us_quad_hard_label": "Q2",
        "us_fused_risk_label": "green",
        "us_vol_regime": "compressed",
        "us_risk_radar_state": "risk_on",
        "us_regime_vector_degraded": False,
        "vector_asof": "2026-01-02",
        "staleness_hours": 16.0,
    }
    monkeypatch.setattr(t, "_regime_stamp_for_date", lambda d: fake_stamp)
    rows = [{"ticker": "699020.SS", "price": 10.0, "signal": {"tier_cascade": "T1"},
             "setup": "reversal", "extension": {"extended": False}, "washout_2w": False}]
    t.append_board(rows, asof=str(dates[0].date()))
    df = pd.read_parquet(t._store_path())
    row = df.iloc[0]
    assert str(row["us_rate_pressure"]) == "neutral"
    assert str(row["us_quad_hard_label"]) == "Q2"
    assert str(row["vector_asof"]) == "2026-01-02"
    assert abs(float(row["staleness_hours"]) - 16.0) < 1e-6


def test_grade_backfills_null_stamps_only(cn_store, monkeypatch):
    """grade() backfills null us_* stamp cols from vector, but does NOT overwrite non-null stamps."""
    tmp_path, dates = cn_store
    # Append a row with null regime stamps (legacy row)
    rows = [{"ticker": "699021.SS", "price": 10.0, "signal": {"tier_cascade": "T1"},
             "setup": "reversal", "extension": {"extended": False}, "washout_2w": False}]
    monkeypatch.setattr(t, "_regime_stamp_for_date", lambda d: t._regime_stamp_null())
    t.append_board(rows, asof=str(dates[0].date()))
    # Now patch regime to return a real value for the grade() backfill
    fake_stamp = {
        "us_rate_pressure": "pressure",
        "us_quad_hard_label": "Q3",
        "us_fused_risk_label": "yellow",
        "us_vol_regime": "elevated",
        "us_risk_radar_state": "risk_off",
        "us_regime_vector_degraded": False,
        "vector_asof": "2026-01-01",
        "staleness_hours": 8.0,
    }
    monkeypatch.setattr(t, "_regime_stamp_for_date", lambda d: fake_stamp)
    # Set up price data so grade() can run
    closes = 10.0 * (1.005 ** np.arange(len(dates)))
    store.upsert("china_stocks", "699021.SS", _mk_ohlc(dates, closes))
    store.upsert("china", t._BENCH, _mk_ohlc(dates, closes)[["close", "volume"]])
    g = t.grade()
    assert g["available"]
    # Re-read to confirm backfill was written
    df2 = pd.read_parquet(t._store_path())
    row = df2.iloc[0]
    assert str(row["us_rate_pressure"]) == "pressure", "Backfill should have populated null stamp"


def test_grade_unstamped_count_reported(cn_store, monkeypatch):
    """grade() reports n_unstamped (rows where us_rate_pressure is still null after backfill)."""
    tmp_path, dates = cn_store
    rows = [{"ticker": "699022.SS", "price": 10.0, "signal": {"tier_cascade": "T2"},
             "setup": "reversal", "extension": {"extended": False}, "washout_2w": False}]
    # Both append and grade return null stamps → row stays unstamped
    monkeypatch.setattr(t, "_regime_stamp_for_date", lambda d: t._regime_stamp_null())
    t.append_board(rows, asof=str(dates[0].date()))
    closes = 10.0 * (1.01 ** np.arange(len(dates)))
    store.upsert("china_stocks", "699022.SS", _mk_ohlc(dates, closes))
    store.upsert("china", t._BENCH, _mk_ohlc(dates, closes)[["close", "volume"]])
    g = t.grade()
    assert "n_unstamped" in g, "grade() must report n_unstamped"
    assert g["n_unstamped"] >= 1, "Expected at least 1 unstamped row when vector unavailable"


# ---------------------------------------------------------------------------
# Scope-3: stratifier columns (species_id, archetype)
# ---------------------------------------------------------------------------

def test_stratifier_cols_present_and_nullable(cn_store):
    """species_id and archetype are present in the parquet after append_board and are null."""
    tmp_path, dates = cn_store
    rows = [{"ticker": "699030.SS", "price": 10.0, "signal": {"tier_cascade": "T1"},
             "setup": "reversal", "extension": {"extended": False}, "washout_2w": False}]
    t.append_board(rows, asof=str(dates[0].date()))
    df = pd.read_parquet(t._store_path())
    assert "species_id" in df.columns, "species_id column missing"
    assert "archetype" in df.columns, "archetype column missing"
    # Must be null (documented constraint — multiple species bind this ledger)
    val_sid = df.iloc[0]["species_id"]
    val_arch = df.iloc[0]["archetype"]
    assert val_sid is None or pd.isna(val_sid), f"species_id must be null, got {val_sid!r}"
    assert val_arch is None or pd.isna(val_arch), f"archetype must be null, got {val_arch!r}"


def test_grade_includes_species_archetype_slice_tables(cn_store):
    """grade() by_horizon blocks include by_species_id and by_archetype stratifiers."""
    tmp_path, dates = cn_store
    store.upsert("china", t._BENCH, _mk_ohlc(dates, 10.0 * (1.005 ** np.arange(len(dates))))[["close", "volume"]])
    rows = []
    for i in range(20):
        tk = f"699031{i:02d}.SS"
        store.upsert("china_stocks", tk, _mk_ohlc(dates, 10.0 * (1.02 ** np.arange(len(dates)))))
        rows.append({"ticker": tk, "price": 10.0,
                     "signal": {"tier_cascade": "T1"}, "setup": "reversal",
                     "extension": {"extended": False}, "washout_2w": False})
    t.append_board(rows, asof=str(dates[0].date()))
    g = t.grade()
    h21 = g.get("by_horizon", {}).get("21d", {})
    assert "by_species_id" in h21, "by_species_id stratifier missing from grade() output"
    assert "by_archetype" in h21, "by_archetype stratifier missing from grade() output"


# ---------------------------------------------------------------------------
# Scope-4: own-market regime documented null
# ---------------------------------------------------------------------------

def test_own_market_regime_is_null_with_note(cn_store):
    """own_market_regime is always null; own_market_regime_note documents the constraint."""
    tmp_path, dates = cn_store
    rows = [{"ticker": "699040.SS", "price": 10.0, "signal": {"tier_cascade": "T1"},
             "setup": "reversal", "extension": {"extended": False}, "washout_2w": False}]
    t.append_board(rows, asof=str(dates[0].date()))
    df = pd.read_parquet(t._store_path())
    row = df.iloc[0]
    val = row.get("own_market_regime")
    assert val is None or pd.isna(val), f"own_market_regime must be null, got {val!r}"
    note = row.get("own_market_regime_note")
    assert note and "recomputed" in str(note).lower(), (
        f"own_market_regime_note must document the non-PIT constraint, got {note!r}"
    )


# ---------------------------------------------------------------------------
# Scope-5: fill_basis provenance column
# ---------------------------------------------------------------------------

def test_fill_basis_column_always_t1_hl2(cn_store):
    """fill_basis is always 't1_hl2' on new rows and after grade() write-back."""
    tmp_path, dates = cn_store
    rows = [{"ticker": "699050.SS", "price": 10.0, "signal": {"tier_cascade": "T1"},
             "setup": "reversal", "extension": {"extended": False}, "washout_2w": False}]
    t.append_board(rows, asof=str(dates[0].date()))
    df = pd.read_parquet(t._store_path())
    assert str(df.iloc[0]["fill_basis"]) == "t1_hl2", (
        f"fill_basis must be 't1_hl2', got {df.iloc[0]['fill_basis']!r}"
    )
    # Also present after grade() runs on live price data
    closes = 10.0 * (1.01 ** np.arange(len(dates)))
    store.upsert("china_stocks", "699050.SS", _mk_ohlc(dates, closes))
    store.upsert("china", t._BENCH, _mk_ohlc(dates, closes)[["close", "volume"]])
    t.grade()
    df2 = pd.read_parquet(t._store_path())
    assert str(df2.iloc[0]["fill_basis"]) == "t1_hl2"


# ---------------------------------------------------------------------------
# Scope-6: dtype hardening round-trip
# ---------------------------------------------------------------------------

def test_dtype_hardening_roundtrip(cn_store):
    """Write all-null frame → read → string cell write must not raise TypeError.

    Validates the _coerce_object_cols pattern: an all-NaN column loaded from parquet
    is typed float64; pandas 3.x refuses string writes to it. _coerce_object_cols must
    convert it to object dtype before any cell assignment.
    """
    tmp_path, dates = cn_store
    # Write a minimal parquet with all spine/regime cols as NaN (float64 on reload)
    import pyarrow as pa
    import pyarrow.parquet as pq
    schema = pa.schema([
        pa.field("date", pa.string()),
        pa.field("ticker", pa.string()),
        pa.field("own_market_regime", pa.float64()),        # all-NaN → float64
        pa.field("terminal_state_clean15_126", pa.float64()),
        pa.field("post_cushion_breach", pa.float64()),
        pa.field("fill_basis", pa.float64()),
    ])
    tbl = pa.table({
        "date": ["2026-01-05"],
        "ticker": ["699060.SS"],
        "own_market_regime": [float("nan")],
        "terminal_state_clean15_126": [float("nan")],
        "post_cushion_breach": [float("nan")],
        "fill_basis": [float("nan")],
    }, schema=schema)
    p = t._store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(tbl, p)
    # Now read and try to write a string — this is the exact pandas 3.x failure mode.
    df = pd.read_parquet(p)
    df = t._coerce_object_cols(df)
    # Should not raise TypeError
    try:
        df.at[0, "own_market_regime"] = "null_documented"
        df.at[0, "terminal_state_clean15_126"] = "CLEAN_LIFTOFF"
        df.at[0, "post_cushion_breach"] = True
        df.at[0, "fill_basis"] = "t1_hl2"
    except TypeError as e:
        pytest.fail(f"_coerce_object_cols did not prevent dtype TypeError: {e}")


def test_schema_union_with_legacy_store(cn_store):
    """append_board with a legacy parquet (missing spine/regime cols) performs schema union
    without dropping existing columns or crashing."""
    tmp_path, dates = cn_store
    # Write a legacy minimal parquet (pre-B-d schema: only date + ticker + board_rank)
    legacy = pd.DataFrame([{"date": "2025-12-01", "ticker": "699070.SS", "board_rank": 1}])
    p = t._store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    legacy.to_parquet(p, index=False)
    # Now append a B-d row → schema union should preserve the legacy row + add new cols
    rows = [{"ticker": "699071.SS", "price": 10.0, "signal": {"tier_cascade": "T1"},
             "setup": "reversal", "extension": {"extended": False}, "washout_2w": False}]
    n = t.append_board(rows, asof=str(dates[0].date()))
    assert n == 2, f"Expected 2 total rows after schema-union append, got {n}"
    df = pd.read_parquet(p)
    assert "fill_basis" in df.columns, "fill_basis missing from schema-union result"
    # Legacy row should have null in new cols (NaN or None — both acceptable)
    legacy_row = df[df["ticker"] == "699070.SS"].iloc[0]
    val = legacy_row.get("fill_basis")
    assert val is None or pd.isna(val), f"legacy row fill_basis should be null, got {val!r}"
