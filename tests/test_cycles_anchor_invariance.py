"""A cycle-ladder read is a function of the PRICE HISTORY, never of the caller's slice.

Binding ruling: ``research/CYCLES_SESSION_ANCHOR_ADJUDICATION_BY_FABLE.md``
(era ``cyc-abs-session-2026-08-06``, ship requirement 3).

THE DEFECT THESE PIN. ``cycles.mtf_snapshot`` cut its 3D leg with ``resample(tf3)``
(``tf3`` PARAMETERIZED from CYCLE_PRESETS — the literal-grep escapee) and
``calibrate_ladder`` cut its own ``resample("3B")`` on a walk-forward window whose start
slides every 5 bars; ``leader_lifecycle.tf_state_2d`` did the same on ``"2B"``. All three
phased their bins to the SERIES' FIRST timestamp: one dropped leading bar flipped the 3B
``_tf_state`` on 99/99 deep US names (mod-3 fingerprint) and the 2B state on 93/99
(mod-2), the walk-forward re-phased its grid INTRA-RUN, and crypto's ``"3D"`` calendar
bins rode pandas' ``origin='start_day'`` — the same disease in day units.

WHAT INVARIANCE MEANS HERE, EXACTLY (the confluence battery's split, restated): the
repair removes the STRUCTURAL slice-dependence — bucket membership is now a function of
``(calendar, date)`` alone. It does not remove the NUMERICAL one: every indicator here is
EWM-based, so truncation perturbs values by an amount that DECAYS with depth. Deep
fixtures therefore assert bit-exact equality; the shallow fixture asserts the GRID exact
and the residual is named, bounded, and decaying — never hidden in a loose tolerance.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from engine import commodity_mtf, cycles, ticker_alerts
from engine.cycles import ANCHOR_ERA, _anchor_bars
from engine.leader_lifecycle import tf_state_2d
from engine.session_anchor import session_positions
from lib import nyse_calendar

# Real NYSE sessions — real phases, real holidays, so a bucket boundary in a test means
# the same thing it means in production.
_SESSIONS = pd.DatetimeIndex(pd.to_datetime(
    nyse_calendar.sessions_between(date(2005, 1, 1), date(2026, 8, 4))))


def _sess(n: int) -> pd.DatetimeIndex:
    return _SESSIONS[len(_SESSIONS) - n:]


def _walk(idx: pd.DatetimeIndex, lg: np.ndarray, seed: int, vol: float) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.exp(lg + np.cumsum(rng.normal(0.0, vol, len(idx)))), index=idx)


def _uptrend(n: int = 900, seed: int = 1) -> pd.Series:
    """(a) smooth uptrend + sinusoid — crosses fire regularly."""
    idx = _sess(n); i = np.arange(n)
    return _walk(idx, 0.5 * i / n + 0.12 * np.sin(2 * np.pi * i / 45), seed, 0.006)


def _down_then_v(n: int = 900, seed: int = 2) -> pd.Series:
    """(b) long downtrend then a V — a fresh cross near the END, the repaint-prone shape."""
    idx = _sess(n); i = np.arange(n)
    lg = np.where(i < n * 0.8, -0.8 * i / n, -0.64 + 2.2 * (i - n * 0.8) / n)
    return _walk(idx, lg, seed, 0.007)


def _holiday_span(seed: int = 3) -> pd.Series:
    """(c) certainly contains Thanksgiving/Christmas/July-4 weeks — the short weeks whose
    bins the old calendar-anchored resample mis-split."""
    idx = _SESSIONS[(_SESSIONS >= pd.Timestamp("2021-06-01"))
                    & (_SESSIONS <= pd.Timestamp("2025-01-31"))]
    i = np.arange(len(idx))
    return _walk(idx, 0.3 * i / len(idx) + 0.15 * np.sin(2 * np.pi * i / 38), seed, 0.008)


def _halted(n: int = 900, seed: int = 4) -> pd.Series:
    """(d) three sessions missing mid-stream — dates present in the REFERENCE but absent
    from the series; the buckets must simply skip them."""
    s = _uptrend(n, seed)
    return s.drop(s.index[[400, 401, 402]])


DEEP_FIXTURES = {
    "uptrend_sinusoid": _uptrend(),
    "downtrend_then_V": _down_then_v(),
    "holiday_span": _holiday_span(),
    "halted_3_sessions": _halted(),
}

#: ladder/alignment fields the anchor determines (scalar, non-length-encoding). `bars`-like
#: depth disclosures and prose lines are compared through these, not re-listed.
_LADDER_FIELDS = ("state", "score", "dir", "signal_date", "age_days", "prev_state",
                  "anchor_era")
_ALIGN_FIELDS = ("tier", "aligned", "near", "score", "quality", "weekly", "three_day",
                 "daily", "overextended", "blocked")


def _dict_diff(a: dict, b: dict) -> dict:
    keys = set(a) | set(b)
    return {k: (a.get(k), b.get(k)) for k in keys if a.get(k) != b.get(k)}


# --------------------------------------------------------------------------- #
# 1. the grid itself — exact, at every depth, every market form
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(DEEP_FIXTURES))
@pytest.mark.parametrize("k", [1, 2, 3, 4, 5, 6])
def test_3b_bars_are_identical_on_the_shared_tail_regardless_of_leading_history(name, k):
    """``_anchor_bars(c[k:]) == _anchor_bars(c)`` except for the leading bucket(s) the
    truncation ate. This is the whole repair, asserted at the grid layer."""
    c = DEEP_FIXTURES[name]
    a, b = _anchor_bars(c, "3B"), _anchor_bars(c.iloc[k:], "3B")
    # truncation may eat at most ceil(k/3)+... leading buckets; nothing else may move
    assert len(a) - len(b) <= (k // 3) + 1
    tail = min(len(a), len(b))
    pd.testing.assert_series_equal(a.iloc[-tail:], b.iloc[-tail:], check_freq=False)


def test_bucket_ids_are_session_positions_over_n_and_skip_halts():
    """The geometry pin (R-CY2): every bucket holds consecutive session-positions // 3,
    labels are the bucket's last TRADED session, ascending; a halted session simply
    leaves a 2-session bucket — never a re-phased grid."""
    c = _halted()
    bars = _anchor_bars(c, "3B")
    assert bars.index.is_monotonic_increasing and bars.index.is_unique
    assert set(bars.index).issubset(set(c.index)), "labels must be traded sessions"
    got = session_positions(bars.index) // 3
    assert len(np.unique(got)) == len(got), "one row per absolute bucket"
    # the halted sessions' bucket still exists (2 of its 3 sessions traded)
    halted_bucket = (session_positions(pd.DatetimeIndex([_uptrend().index[400]])) // 3)[0]
    assert halted_bucket in set(got)


def test_crypto_calendar_day_buckets_are_epoch_anchored_and_start_invariant():
    """R-CY1's second clause: a 24/7 series buckets by (d − 1970-01-01).days // 3 —
    pandas' fixed-freq bins default to origin='start_day', the same series-start disease
    in day units."""
    idx = pd.date_range("2023-01-01", periods=900, freq="D")
    rng = np.random.default_rng(7)
    c = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 900))), index=idx)
    a = _anchor_bars(c, "3D")
    for k in (1, 2, 3, 4, 5):
        b = _anchor_bars(c.iloc[k:], "3D")
        tail = min(len(a), len(b))
        pd.testing.assert_series_equal(a.iloc[-tail:], b.iloc[-tail:], check_freq=False)
    # the phase is the EPOCH's, not the series': bucket id of the first bar is derivable
    # from its date alone
    first_id = (idx[0].normalize() - pd.Timestamp("1970-01-01")).days // 3
    assert first_id == 6452  # 19358 days // 3 — arithmetic a reader can check


def test_the_old_resample_grid_really_was_slice_phased():
    """Regression witness: the defect exists in the retired construction, so this battery
    is pinning a repair, not a tautology."""
    c = _uptrend()
    old_a = c.resample("3B").last().dropna()
    old_b = c.iloc[1:].resample("3B").last().dropna()
    tail = min(len(old_a), len(old_b))
    assert not old_a.iloc[-tail:].index.equals(old_b.iloc[-tail:].index), (
        "resample('3B') bins no longer phase to the series start — pandas changed; "
        "re-adjudicate the anchor's premise")


# --------------------------------------------------------------------------- #
# 2. mtf_snapshot / analyze — the payload layer, deep = bit-exact
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(DEEP_FIXTURES))
@pytest.mark.parametrize("k", [1, 2, 3, 4, 5, 6])
def test_mtf_3d_state_is_bit_identical_on_a_deep_series(name, k):
    c = DEEP_FIXTURES[name]
    a, b = cycles.mtf_snapshot(c), cycles.mtf_snapshot(c.iloc[k:])
    assert _dict_diff(a["3D"], b["3D"]) == {}, (
        f"{name}: dropping {k} leading bar(s) changed the 3D state — the bucket grid is "
        f"still phased to the caller's slice")


@pytest.mark.parametrize("k", [1, 2, 3])
def test_analyze_ladder_and_alignment_are_invariant_on_a_deep_series(k):
    """The board surface: state, score, signal_date (the ladder-log key) and the
    bottoming-alignment admission fields may not move when a caller loads less leading
    history. Before the era, the signal_date walk-back compared a full-history grid
    against per-step re-phased 600-bar-window grids."""
    c = _uptrend()
    a, b = cycles.analyze(c), cycles.analyze(c.iloc[k:])
    la, lb = a["ladder"], b["ladder"]
    assert {f: (la.get(f), lb.get(f)) for f in _LADDER_FIELDS
            if la.get(f) != lb.get(f)} == {}
    aa, ab = la.get("alignment") or {}, lb.get("alignment") or {}
    assert {f: (aa.get(f), ab.get(f)) for f in _ALIGN_FIELDS
            if aa.get(f) != ab.get(f)} == {}


def test_the_residual_slice_sensitivity_is_ewm_memory_and_decays_with_depth():
    """Name the residual instead of hiding it (the confluence battery's discipline).
    The 3D GRID is exact at every depth; the VALUES on it carry EWM memory that decays.
    If the deep drift ever stops being zero, the anchor is leaking again."""
    drift = {}
    for n in (300, 500, 900):
        c = _uptrend(n)
        a = cycles.mtf_snapshot(c)["3D"].get("spark_hist") or [0.0]
        b = cycles.mtf_snapshot(c.iloc[6:])["3D"].get("spark_hist") or [0.0]
        drift[n] = abs(a[-1] - b[-1])
    assert drift[900] == 0.0, "at 900 bars EWM memory must be below display precision"
    assert drift[900] <= drift[500] <= drift[300], f"drift is not decaying: {drift}"


def test_tf_state_2d_is_invariant_and_rides_the_same_era():
    """leader_lifecycle's 2B oscillator (93/99 flipped at k=1 pre-era) reads the same
    absolute grid; its era is cycles.ANCHOR_ERA by import, pinned here."""
    c = _uptrend()
    for k in (1, 2, 3):
        assert _dict_diff(tf_state_2d(c), tf_state_2d(c.iloc[k:])) == {}, (
            f"tf_state_2d moved on a {k}-bar leading drop")
    from engine import leader_lifecycle
    assert leader_lifecycle._anchor_bars is cycles._anchor_bars


# --------------------------------------------------------------------------- #
# 3. calibrate_ladder — the walk-forward window reads THE grid (R-CY6a)
# --------------------------------------------------------------------------- #

def test_a_slid_calibration_window_reads_the_same_3d_grid_as_a_fixed_one():
    """calibrate_ladder's `sub` starts at max(0, i-600) and slides every step=5 bars
    (5 mod 3 = 2): under the old resample every step re-phased the 3D bins INTRA-RUN.
    Absolute buckets are window-independent, so the shared tail of any two windows'
    grids is identical — the structural healing, asserted directly."""
    c = _uptrend(1400)
    for i in (700, 705, 710, 1000):
        fixed = _anchor_bars(c.iloc[max(0, i - 600): i + 1], "3B")
        slid = _anchor_bars(c.iloc[max(0, i - 590): i + 1], "3B")
        tail = min(len(fixed), len(slid))
        pd.testing.assert_series_equal(fixed.iloc[-tail:], slid.iloc[-tail:],
                                       check_freq=False)


def test_calibrate_ladder_cells_carry_the_era_inside_the_cell():
    """R-CY4: the artifact's top level is iterated by state-name consumers, so the era
    lives INSIDE each per-state stats dict, never as a root key."""
    rng = np.random.default_rng(11)
    idx = _sess(1300); i = np.arange(1300)
    c = pd.Series(100 * np.exp(0.2 * np.sin(2 * np.pi * i / 90)
                               + np.cumsum(rng.normal(0.0002, 0.009, 1300))), index=idx)
    cal = cycles.calibrate_ladder({"A": c, "B": c * 1.01}, step=7)
    assert cal, "fixture produced no calibratable states — regenerate it"
    for state, cell in cal.items():
        assert cell["anchor_era"] == ANCHOR_ERA, f"{state} cell missing the era fence"
        assert "n" in cell and "hit_pct" in cell


# --------------------------------------------------------------------------- #
# 4. the ladder log crosses the era ONCE (R-CY5)
# --------------------------------------------------------------------------- #

def _row(asset, day, state, era=ANCHOR_ERA, prev=""):
    return {"asset": asset, "signal_date": day, "state": state, "prev_state": prev,
            "action": "", "label": state, "urgency": "", "score": 0, "dir": "neutral",
            "asof": day, "anchor_era": era}


@pytest.fixture()
def _log(tmp_path, monkeypatch):
    p = tmp_path / "ladder_log.parquet"
    monkeypatch.setattr(ticker_alerts, "_ladder_path", lambda: p)
    return p


def _seed_pre_era(p, asset="NVDA", day="2026-08-03", state="BOTTOM WATCH"):
    """A pre-era store: the anchor_era column does not exist at all (schema tolerance is
    part of the contract — the live parquet predates the column)."""
    pd.DataFrame([{"asset": asset, "signal_date": day, "state": state, "prev_state": "",
                   "action": "", "label": state, "urgency": "", "score": 0,
                   "dir": "neutral", "asof": day}]).to_parquet(p)


def test_a_pure_rekey_across_the_era_seam_is_skipped_and_counted(_log):
    """Same asset, same standing state, walk-back date moved 2 sessions with the grid:
    the (asset, signal_date, state) dedup would mint a duplicate 'Signal: X' card —
    the seam guard refuses it."""
    _seed_pre_era(_log)
    added = ticker_alerts.write_ladder_log_batch([_row("NVDA", "2026-08-05", "BOTTOM WATCH")])
    assert added == 0
    df = pd.read_parquet(_log)
    assert len(df) == 1, "the re-keyed image must not append"
    assert "anchor_era" not in df.columns or df["anchor_era"].isna().all()


def test_a_genuine_state_change_at_the_seam_appends(_log):
    _seed_pre_era(_log)
    added = ticker_alerts.write_ladder_log_batch(
        [_row("NVDA", "2026-08-05", "CONFIRMING TURN", prev="BOTTOM WATCH")])
    assert added == 1
    df = pd.read_parquet(_log)
    assert set(df["state"]) == {"BOTTOM WATCH", "CONFIRMING TURN"}
    got = df[df["state"] == "CONFIRMING TURN"].iloc[0]
    assert got["anchor_era"] == ANCHOR_ERA, "post-era rows must carry the cohort fence"


def test_a_rekey_beyond_the_tolerance_appends(_log):
    """5+ calendar days apart is a re-print, not the cutover's re-keyed image."""
    _seed_pre_era(_log, day="2026-07-28")
    added = ticker_alerts.write_ladder_log_batch([_row("NVDA", "2026-08-05", "BOTTOM WATCH")])
    assert added == 1


def test_a_same_era_whipsaw_inside_the_tolerance_appends(_log):
    """After cutover every stored row carries the era: the guard is dormant and a genuine
    A→B→A whipsaw keeps its full timeline."""
    ticker_alerts.write_ladder_log_batch([_row("NVDA", "2026-08-03", "BOTTOM WATCH")])
    ticker_alerts.write_ladder_log_batch(
        [_row("NVDA", "2026-08-04", "CONFIRMING TURN", prev="BOTTOM WATCH")])
    added = ticker_alerts.write_ladder_log_batch(
        [_row("NVDA", "2026-08-05", "BOTTOM WATCH", prev="CONFIRMING TURN")])
    assert added == 1
    assert len(pd.read_parquet(_log)) == 3


def test_exact_duplicate_keys_still_dedup(_log):
    ticker_alerts.write_ladder_log_batch([_row("NVDA", "2026-08-05", "BOTTOM WATCH")])
    added = ticker_alerts.write_ladder_log_batch([_row("NVDA", "2026-08-05", "BOTTOM WATCH")])
    assert added == 0 and len(pd.read_parquet(_log)) == 1


def test_ladder_row_copies_the_era_from_the_ladder_payload():
    lad = {"state": "BOTTOM WATCH", "signal_date": "2026-08-05", "anchor_era": ANCHOR_ERA}
    r = ticker_alerts.ladder_row("NVDA", lad, "2026-08-05")
    assert r["anchor_era"] == ANCHOR_ERA
    # a payload without the field (exotic caller) degrades to the pre-era sentinel
    assert ticker_alerts.ladder_row("NVDA", {"state": "X", "signal_date": "2026-08-05"},
                                    "2026-08-05")["anchor_era"] == ""


# --------------------------------------------------------------------------- #
# 5. the fortnight fold (R-CY8)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(DEEP_FIXTURES))
def test_commodity_fortnight_bars_are_start_invariant(name):
    """pandas pairs W-FRI weeks into '2W-FRI' fortnights phased to the series start; the
    absolute epoch-Friday id (1970-01-02) removes the phase. Shared-tail equality after a
    5-bar truncation is the pin."""
    c = DEEP_FIXTURES[name]
    a, b = commodity_mtf._fortnight_last(c), commodity_mtf._fortnight_last(c.iloc[5:])
    tail = min(len(a), len(b))
    pd.testing.assert_series_equal(a.iloc[-tail:], b.iloc[-tail:], check_freq=False)


def test_commodity_fortnight_grid_geometry():
    w_labels = _uptrend().resample("W-FRI").last().dropna().index
    f = commodity_mtf._fortnight_last(_uptrend())
    assert set(f.index).issubset(set(w_labels)), "fortnight labels are W-FRI labels"
    ids = (f.index - commodity_mtf._EPOCH_FRIDAY).days // 14
    assert len(np.unique(ids)) == len(ids), "one row per absolute fortnight"
    gaps = f.index.to_series().diff().dropna().dt.days
    assert set(gaps.unique()) <= {7, 14}, (
        "consecutive fortnight labels must be one or two W-FRI steps apart "
        f"(live tail may sit mid-pair), saw {sorted(gaps.unique())}")


# --------------------------------------------------------------------------- #
# 6. the era stamp reaches every payload (R-CY4)
# --------------------------------------------------------------------------- #

def test_anchor_era_is_on_the_analyze_root_and_the_ladder_payload():
    a = cycles.analyze(_uptrend())
    # the ROOT key is named distinctly: the libraries spread this dict into a record that
    # also carries the CASCADE's `anchor_era` (confluence block), and a graded row must be
    # placeable against both eras
    assert a["cycle_anchor_era"] == ANCHOR_ERA
    assert "anchor_era" not in a
    assert a["ladder"]["anchor_era"] == ANCHOR_ERA
    # deliberately NOT inside the mtf dict — builders JSON-dump a["mtf"] wholesale into
    # mtf_json payloads whose clients iterate timeframe keys (R-CY4)
    assert "anchor_era" not in a["mtf"]


def test_market_threading_reaches_the_snapshot(monkeypatch):
    """R-CY3: the CN/HK/CA builders pass their market; the grid must actually route it
    to session_positions rather than swallowing the keyword."""
    seen = {}
    real = cycles.session_positions

    def spy(idx, market="US"):
        seen["market"] = market
        return real(idx, "US")        # any fixed reference keeps the test hermetic

    monkeypatch.setattr(cycles, "session_positions", spy)
    cycles.mtf_snapshot(_uptrend(200), market="HK")
    assert seen.get("market") == "HK"
