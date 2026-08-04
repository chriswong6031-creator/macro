"""Prophet W3 shadow doors — Door T (theme-relay) + Door R (re-arm).

Covers, per the build brief:
  1. Door T fire condition — positive + negative per leg (membership, eligible, is_buyable).
  2. Door R fire condition — positive + negative per leg (eligible / ticks / above200 /
     weekly_bull / 2D completed cross / 3D StochRSI K>=D).
  3. Cap (25/door/night, overflow COUNTED and announced) + dedupe (<21 sessions).
  4. Nightly guard — an off-lane append is a no-op and leaves no file behind.
  5. Grading math vs a hand-computed case (next-bar fill, H sessions, excess vs SPY).
  6. NO AUTHORITY — the pick chain must not import prophet_doors.

Door R's technical legs are pinned on DETERMINISTIC synthetic paths (sine-modulated drift;
piecewise-constant returns are unusable because a constant RSI makes StochRSI NaN). The three
parameter sets below were measured against the frozen helper math at authoring time and each
isolates ONE leg.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import prophet_doors as pdz

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #
def _wave(n: int = 430, *, wave: int, amp: float, drift: float, phase: int,
          start: str = "2022-01-03") -> pd.Series:
    """Sine-modulated exponential drift on a business-day index — deterministic, no RNG."""
    vals = [100.0 * math.exp(drift * i) * (1.0 + amp * math.sin(2 * math.pi * (i + phase) / wave))
            for i in range(n)]
    return pd.Series(vals, index=pd.bdate_range(start, periods=n), dtype=float)


# Measured against the frozen confluence_tiers math at authoring time:
#   R_POS      -> 2D cross-up on the last COMPLETED bucket = True,  3D K 30.46 >= D 28.41
#   R_NO_CROSS -> 2D cross-up = False,                              3D K 51.46 >= D 29.07
#   R_NO_STOCH -> 2D cross-up = True,                               3D K 33.66 <  D 50.06
R_POS = dict(wave=18, amp=0.08, drift=0.0016, phase=5)
R_NO_CROSS = dict(wave=18, amp=0.08, drift=0.0016, phase=7)
R_NO_STOCH = dict(wave=12, amp=0.04, drift=0.0016, phase=4)


def _verdict(**over) -> dict:
    """A signal_gate-shaped verdict. Defaults are the Door R ran-shape (stale but intact)."""
    v = {"eligible": False, "tier_cascade": None, "tier_sub": None, "ticks": 7,
         "above200": True, "weekly_bull": True, "hist_d2": 0.5, "hist_d3": -0.2}
    v.update(over)
    return v


def _buyable(**over) -> dict:
    """A verdict that passes the incumbent Door T trigger (eligible + buyable tier)."""
    return _verdict(eligible=True, tier_cascade="T2", ticks=0, **over)


def _rotation_doc(members_by_theme: dict[str, list[str]], asof: str = "2026-07-31",
                  extra_themes: list[str] | None = None) -> dict:
    """Minimal subsector_rotation.json: themes ranked by emerging_score, members per subsector."""
    themes, subs = [], []
    ordered = list(members_by_theme)
    for i, th in enumerate(ordered):
        themes.append({"theme": th, "emerging_score": 10.0 - i})
        subs.append({"key": f"sub{i}", "theme": th,
                     "members": [{"t": t} for t in members_by_theme[th]]})
    for j, th in enumerate(extra_themes or []):
        themes.append({"theme": th, "emerging_score": -1.0 - j})
        subs.append({"key": f"cold{j}", "theme": th, "members": [{"t": f"COLD{j}"}]})
    return {"asof": asof, "themes": themes, "subsectors": subs}


def _seed_root(tmp_path: Path, rotation: dict | None) -> Path:
    if rotation is not None:
        p = tmp_path / "site" / "marketdata"
        p.mkdir(parents=True, exist_ok=True)
        (p / "subsector_rotation.json").write_text(json.dumps(rotation), encoding="utf-8")
    return tmp_path


def _universe(tickers: list[str], n: int = 430) -> pd.DataFrame:
    """Wide close frame — content is irrelevant wherever gate() is patched, but the frame must
    clear MIN_HISTORY and carry a real session index (dedupe counts sessions on it)."""
    idx = pd.bdate_range("2022-01-03", periods=n)
    return pd.DataFrame(
        {t: 100.0 * np.exp(np.linspace(0, 0.4, n)) * (1 + 0.01 * (i + 1)) for i, t in enumerate(tickers)},
        index=idx,
    )


@pytest.fixture
def nightly(monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.delenv("US_LANE", raising=False)


@pytest.fixture
def off_lane(monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)


# =========================================================================== #
# 1. Door T — fire condition, leg by leg
# =========================================================================== #
class TestDoorTLegs:
    def test_fires_on_eligible_buyable_tiers(self):
        for tier in ("T1", "T2", "T3"):
            assert pdz.door_t_fires(_verdict(eligible=True, tier_cascade=tier)) is True, tier

    def test_does_not_fire_on_t4(self):
        """T4 fires off the 2D StochRSI and is deliberately outside BUYABLE_TIERS."""
        assert pdz.door_t_fires(_verdict(eligible=True, tier_cascade="T4")) is False

    def test_does_not_fire_when_not_eligible(self):
        assert pdz.door_t_fires(_verdict(eligible=False, tier_cascade="T2")) is False

    def test_does_not_fire_without_a_cascade_tier(self):
        assert pdz.door_t_fires(_verdict(eligible=True, tier_cascade=None)) is False

    def test_none_verdict_is_not_a_fire(self):
        assert pdz.door_t_fires(None) is False


class TestDoorTMembership:
    def test_top_k_members_present_cold_theme_absent(self, tmp_path):
        doc = _rotation_doc({"Software": ["MSFT", "CRM"], "Big Data": ["SNOW"]},
                            extra_themes=["Coal"])
        root = _seed_root(tmp_path, doc)
        members, disc = pdz.theme_membership(root, asof=pd.Timestamp("2026-07-31"), k=2)
        assert disc["ok"] is True
        assert set(members) == {"MSFT", "CRM", "SNOW"}
        assert members["MSFT"]["theme_rank"] == 1
        assert members["SNOW"]["theme_rank"] == 2
        assert "COLD0" not in members

    def test_theme_outside_top_k_is_not_membership(self, tmp_path):
        doc = _rotation_doc({"Software": ["MSFT"], "Big Data": ["SNOW"]})
        root = _seed_root(tmp_path, doc)
        members, _ = pdz.theme_membership(root, asof=pd.Timestamp("2026-07-31"), k=1)
        assert set(members) == {"MSFT"}

    def test_multi_theme_member_records_its_best_rank(self, tmp_path):
        doc = _rotation_doc({"Software": ["MSFT"], "Big Data": ["MSFT"]})
        root = _seed_root(tmp_path, doc)
        members, _ = pdz.theme_membership(root, asof=pd.Timestamp("2026-07-31"), k=2)
        assert members["MSFT"]["theme_rank"] == 1
        assert members["MSFT"]["themes_hit"] == ["Big Data", "Software"]

    def test_absent_artifact_fails_soft_and_discloses(self, tmp_path):
        members, disc = pdz.theme_membership(tmp_path, asof=pd.Timestamp("2026-07-31"))
        assert members == {}
        assert disc["ok"] is False
        assert "absent" in disc["reason"]

    def test_stale_artifact_fails_soft_and_discloses(self, tmp_path):
        doc = _rotation_doc({"Software": ["MSFT"]}, asof="2026-06-01")
        root = _seed_root(tmp_path, doc)
        members, disc = pdz.theme_membership(root, asof=pd.Timestamp("2026-07-31"))
        assert members == {}
        assert disc["ok"] is False
        assert "stale" in disc["reason"]
        assert disc["age_days"] > pdz.THEME_MAX_AGE_DAYS

    def test_fresh_artifact_is_not_stale(self, tmp_path):
        doc = _rotation_doc({"Software": ["MSFT"]}, asof="2026-07-29")
        root = _seed_root(tmp_path, doc)
        members, disc = pdz.theme_membership(root, asof=pd.Timestamp("2026-07-31"))
        assert disc["ok"] is True and members


def test_door_t_emits_nothing_when_theme_source_is_stale(tmp_path, monkeypatch, off_lane, capsys):
    """Fail-soft is a REAL no-op on the door, not just a flag on the disclosure."""
    from engine import signal_gate
    monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
    px = _universe(["AAA", "BBB"])
    # staleness is measured against the TAPE, so the fixture date is derived from it
    stale = str((px.index[-1] - pd.Timedelta(days=90)).date())
    root = _seed_root(tmp_path, _rotation_doc({"Software": ["AAA", "BBB"]}, asof=stale))
    run = pdz.emit(root, dry_run=True, universe=px)
    assert run["flags"][pdz.DOOR_T] == []
    assert run["theme_source"]["ok"] is False
    line = [ln for ln in capsys.readouterr().out.splitlines() if "prophet_doors_theme" in ln]
    assert line and line[0].startswith("::warning"), "annotation must start the line"


# =========================================================================== #
# 2. Door R — fire condition, leg by leg
# =========================================================================== #
class TestDoorRStructuralLegs:
    """The four verdict-shaped legs. Each negative flips exactly one leg off the positive."""

    def _series(self):
        return _wave(**R_POS)

    def test_fires_on_the_full_ran_shape(self):
        legs = pdz.door_r_legs(_verdict(), self._series())
        assert legs["fires"] is True
        assert legs["ticks"] == 7

    def test_eligible_name_does_not_fire(self):
        """Door R is the re-arm on a name the incumbent gate is NOT offering today."""
        legs = pdz.door_r_legs(_verdict(eligible=True), self._series())
        assert legs["not_eligible"] is False and legs["fires"] is False

    @pytest.mark.parametrize("ticks", [None, 0, 2, 16, 40])
    def test_ticks_outside_the_window_do_not_fire(self, ticks):
        legs = pdz.door_r_legs(_verdict(ticks=ticks), self._series())
        assert legs["ticks_in_window"] is False and legs["fires"] is False

    @pytest.mark.parametrize("ticks", [3, 7, 15])
    def test_ticks_on_the_window_bounds_fire(self, ticks):
        legs = pdz.door_r_legs(_verdict(ticks=ticks), self._series())
        assert legs["ticks_in_window"] is True and legs["fires"] is True

    @pytest.mark.parametrize("bad", [False, None])
    def test_above200_must_be_literally_true(self, bad):
        """`is True` is deliberate — an unanalysed None must never read as an intact trend."""
        legs = pdz.door_r_legs(_verdict(above200=bad), self._series())
        assert legs["above200"] is False and legs["fires"] is False

    @pytest.mark.parametrize("bad", [False, None])
    def test_weekly_bull_must_be_literally_true(self, bad):
        legs = pdz.door_r_legs(_verdict(weekly_bull=bad), self._series())
        assert legs["weekly_bull"] is False and legs["fires"] is False

    def test_thin_history_does_not_fire(self):
        legs = pdz.door_r_legs(_verdict(), _wave(n=120, **R_POS))
        assert legs["fires"] is False

    def test_none_verdict_does_not_fire(self):
        assert pdz.door_r_legs(None, self._series())["fires"] is False


class TestDoorRTechnicalLegs:
    def test_positive_case_both_technical_legs_hold(self):
        legs = pdz.door_r_legs(_verdict(), _wave(**R_POS))
        assert legs["x2d_completed"] is True
        assert legs["stoch3d_kd"] is True
        assert legs["k3"] >= legs["d3"]
        assert legs["fires"] is True

    def test_no_2d_cross_on_the_completed_bucket_does_not_fire(self):
        """Stoch leg holds; the 2D re-cross has NOT printed on the last completed bucket."""
        legs = pdz.door_r_legs(_verdict(), _wave(**R_NO_CROSS))
        assert legs["stoch3d_kd"] is True
        assert legs["x2d_completed"] is False
        assert legs["fires"] is False

    def test_bearish_3d_stochrsi_does_not_fire(self):
        """2D re-cross printed, but the 3D StochRSI has K < D — not constructive."""
        legs = pdz.door_r_legs(_verdict(), _wave(**R_NO_STOCH))
        assert legs["x2d_completed"] is True
        assert legs["stoch3d_kd"] is False
        assert legs["k3"] < legs["d3"]
        assert legs["fires"] is False


class TestCompletedBucketIsPointInTime:
    """The whole point of completed_tf: never fire off the in-progress resample tail."""

    def test_in_progress_tail_bucket_is_dropped(self):
        from engine.confluence_tiers import _tf_bars
        base = _wave(n=430, **R_POS)
        for n in (2, 3):
            raw, _ = _tf_bars(base, n)
            comp, ck = pdz.completed_tf(base, n)
            assert len(comp) in (len(raw), len(raw) - 1)
            assert len(comp) == len(ck)
            tail_close = comp.index[-1] + pd.tseries.offsets.BDay(n - 1)
            assert base.index.max() >= tail_close, "a completed bucket must have closed"

    def test_in_progress_tail_is_excluded_from_the_completed_read(self):
        """Guards against completed_tf silently degrading into _tf_bars. An ODD-length series
        leaves the final 2B bucket holding one bar, so a spike ON that bar must move the raw
        read and leave the completed read byte-identical."""
        from engine.confluence_tiers import _tf_bars
        base = _wave(n=429, **R_POS)                 # odd -> final 2B bucket is in progress
        raw, _ = _tf_bars(base, 2)
        comp, _ = pdz.completed_tf(base, 2)
        assert len(comp) == len(raw) - 1, "this fixture must exercise the truncation"

        spiked = base.copy()
        spiked.iloc[-1] *= 3.0
        raw_s, _ = _tf_bars(spiked, 2)
        comp_s, _ = pdz.completed_tf(spiked, 2)
        assert float(raw_s.iloc[-1]) != pytest.approx(float(raw.iloc[-1])), \
            "the raw read sees the in-progress bar"
        assert comp_s.equals(comp), "the completed read must not see the in-progress bar"

    def test_closed_tail_bucket_is_kept(self):
        """The truncation is conditional, not unconditional — an EVEN-length series closes its
        final 2B bucket, and dropping it would delay every fire by a session."""
        from engine.confluence_tiers import _tf_bars
        base = _wave(n=430, **R_POS)
        raw, _ = _tf_bars(base, 2)
        comp, _ = pdz.completed_tf(base, 2)
        assert len(comp) == len(raw)


# =========================================================================== #
# 3. Cap + dedupe
# =========================================================================== #
class TestCapAndDedupe:
    def _patch_gate(self, monkeypatch, verdict):
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: verdict)

    def test_door_t_capped_with_counted_overflow(self, tmp_path, monkeypatch, off_lane, capsys):
        tickers = [f"T{i:02d}" for i in range(pdz.MAX_FLAGS_PER_DOOR + 7)]
        self._patch_gate(monkeypatch, _buyable())
        root = _seed_root(tmp_path, _rotation_doc({"Software": tickers}))
        run = pdz.emit(root, dry_run=True, universe=_universe(tickers))
        assert run["candidates"][pdz.DOOR_T] == len(tickers)
        assert len(run["flags"][pdz.DOOR_T]) == pdz.MAX_FLAGS_PER_DOOR
        assert run["overflow"][pdz.DOOR_T] == 7
        line = [ln for ln in capsys.readouterr().out.splitlines() if "prophet_doors_cap" in ln]
        assert line, "an overflow must never be silent"
        assert line[0].startswith("::warning"), "annotation must start the line"
        assert "7 candidate(s) dropped" in line[0]

    def test_cap_keeps_the_hottest_theme_first(self, tmp_path, monkeypatch, off_lane):
        hot = [f"H{i:02d}" for i in range(pdz.MAX_FLAGS_PER_DOOR)]
        warm = ["W00", "W01"]
        self._patch_gate(monkeypatch, _buyable())
        root = _seed_root(tmp_path, _rotation_doc({"Software": hot, "Big Data": warm}))
        run = pdz.emit(root, dry_run=True, universe=_universe(hot + warm))
        kept = {r["ticker"] for r in run["flags"][pdz.DOOR_T]}
        assert kept == set(hot)
        assert run["overflow"][pdz.DOOR_T] == len(warm)

    def test_recent_prior_flag_is_deduped(self, tmp_path, monkeypatch, nightly):
        self._patch_gate(monkeypatch, _buyable())
        root = _seed_root(tmp_path, _rotation_doc({"Software": ["AAA", "BBB"]}))
        px = _universe(["AAA", "BBB"])
        asof = px.index[-1]
        # index[-(N+1)] sits exactly N sessions before the last bar
        recent = px.index[-pdz.DEDUPE_SESSIONS]                 # 20 sessions back — inside window
        assert pdz._sessions_since(px.index, recent, asof) == pdz.DEDUPE_SESSIONS - 1
        pdz.append_flags([{"schema": pdz.SCHEMA, "date": str(recent.date()),
                           "door": pdz.DOOR_T, "ticker": "AAA", "features": {}}], root)
        run = pdz.emit(root, dry_run=True, universe=px)
        assert {r["ticker"] for r in run["flags"][pdz.DOOR_T]} == {"BBB"}
        assert run["deduped"][pdz.DOOR_T] == 1

    def test_prior_flag_past_the_window_re_fires(self, tmp_path, monkeypatch, nightly):
        self._patch_gate(monkeypatch, _buyable())
        root = _seed_root(tmp_path, _rotation_doc({"Software": ["AAA"]}))
        px = _universe(["AAA"])
        old = px.index[-(pdz.DEDUPE_SESSIONS + 1)]             # 21 sessions back — window passed
        assert pdz._sessions_since(px.index, old, px.index[-1]) == pdz.DEDUPE_SESSIONS
        pdz.append_flags([{"schema": pdz.SCHEMA, "date": str(old.date()),
                           "door": pdz.DOOR_T, "ticker": "AAA", "features": {}}], root)
        run = pdz.emit(root, dry_run=True, universe=px)
        assert {r["ticker"] for r in run["flags"][pdz.DOOR_T]} == {"AAA"}
        assert run["deduped"][pdz.DOOR_T] == 0

    def test_dedupe_is_scoped_to_one_door(self, tmp_path, monkeypatch, nightly):
        """A Door R flag must not suppress a Door T flag on the same ticker."""
        self._patch_gate(monkeypatch, _buyable())
        root = _seed_root(tmp_path, _rotation_doc({"Software": ["AAA"]}))
        px = _universe(["AAA"])
        pdz.append_flags([{"schema": pdz.SCHEMA, "date": str(px.index[-2].date()),
                           "door": pdz.DOOR_R, "ticker": "AAA", "features": {}}], root)
        run = pdz.emit(root, dry_run=True, universe=px)
        assert {r["ticker"] for r in run["flags"][pdz.DOOR_T]} == {"AAA"}


# =========================================================================== #
# 4. Nightly guard — the ledger law
# =========================================================================== #
class TestNightlyGuard:
    ROW = [{"schema": pdz.SCHEMA, "date": "2026-07-31", "door": "T",
            "ticker": "AAA", "features": {}}]

    def test_off_lane_append_is_a_no_op(self, tmp_path, off_lane):
        assert pdz.append_flags(self.ROW, tmp_path) == 0
        assert not pdz.flags_path(tmp_path).exists(), "off-lane must leave no file behind"

    @pytest.mark.parametrize("lane", ["render", "intraday", ""])
    def test_non_nightly_lanes_are_refused(self, tmp_path, monkeypatch, lane):
        monkeypatch.setenv("COLLECT_LANE", lane)
        monkeypatch.delenv("US_LANE", raising=False)
        assert pdz.append_flags(self.ROW, tmp_path) == 0
        assert not pdz.flags_path(tmp_path).exists()

    def test_nightly_lane_appends(self, tmp_path, nightly):
        assert pdz.append_flags(self.ROW, tmp_path) == 1
        assert len(pdz.load_flags(tmp_path)) == 1

    def test_append_is_additive_never_a_rewrite(self, tmp_path, nightly):
        pdz.append_flags(self.ROW, tmp_path)
        pdz.append_flags([{**self.ROW[0], "ticker": "BBB"}], tmp_path)
        assert [r["ticker"] for r in pdz.load_flags(tmp_path)] == ["AAA", "BBB"]

    def test_off_lane_status_write_is_a_no_op(self, tmp_path, off_lane):
        assert pdz.write_status({"schema": pdz.SCHEMA}, tmp_path) is False
        assert not pdz.status_path(tmp_path).exists()

    def test_off_lane_emit_writes_nothing_at_all(self, tmp_path, monkeypatch, off_lane):
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        root = _seed_root(tmp_path, _rotation_doc({"Software": ["AAA"]}))
        run = pdz.emit(root, dry_run=False, universe=_universe(["AAA"]))
        assert run["flags"][pdz.DOOR_T], "the door still COMPUTES off-lane; it just discards"
        assert run["appended"] == 0
        assert not pdz.ledger_dir(root).exists()

    def test_grader_append_is_nightly_gated(self, tmp_path, off_lane):
        from scripts import grade_prophet_doors as gpd
        assert gpd.append_grades([{"schema": gpd.GRADE_SCHEMA, "ticker": "AAA"}], tmp_path) == 0
        assert not gpd.grades_path(tmp_path).exists()

    def test_nightly_emit_writes_only_under_data_prophet_doors(self, tmp_path, monkeypatch,
                                                              nightly):
        """Scope fence: this lane owns exactly one directory — no site/, no board, no plans."""
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        root = _seed_root(tmp_path, _rotation_doc({"Software": ["AAA"]}))
        before = {p for p in root.rglob("*") if p.is_file()}
        pdz.emit(root, dry_run=False, universe=_universe(["AAA"]))
        created = {p for p in root.rglob("*") if p.is_file()} - before
        assert created, "the nightly lane must actually accrue"
        for p in created:
            assert p.parent == pdz.ledger_dir(root), f"unexpected write outside the lane: {p}"


# =========================================================================== #
# 5. Grading math vs a hand-computed case
# =========================================================================== #
class TestGradingMath:
    def _pair(self, n=120, name_r=0.01, spy_r=0.002):
        idx = pd.bdate_range("2026-01-05", periods=n)
        name = pd.Series([100.0 * (1 + name_r) ** i for i in range(n)], index=idx)
        spy = pd.Series([400.0 * (1 + spy_r) ** i for i in range(n)], index=idx)
        return idx, name, spy

    def test_next_bar_fill_and_excess_vs_spy(self):
        """Hand-computed: entry = close[i+1] (NEXT bar), mark = close[i+1+H],
        fwd_ret = mark/entry - 1, excess = fwd_ret(name) - fwd_ret(SPY)."""
        from scripts import grade_prophet_doors as gpd
        idx, name, spy = self._pair()
        i = 50
        flag_date = idx[i]
        marks = gpd.grade_flag(name, spy, flag_date)
        assert set(marks) == {10, 21}
        for h in (10, 21):
            m = marks[h]
            entry = float(name.iloc[i + 1])
            mark = float(name.iloc[i + 1 + h])
            b_entry = float(spy.iloc[i + 1])
            b_mark = float(spy.iloc[i + 1 + h])
            assert m["fill_date"] == str(idx[i + 1].date())
            assert m["mark_date"] == str(idx[i + 1 + h].date())
            assert m["entry_price"] == pytest.approx(entry, rel=1e-9)
            assert m["fwd_ret"] == pytest.approx(mark / entry - 1.0, abs=1e-6)
            assert m["bench_ret"] == pytest.approx(b_mark / b_entry - 1.0, abs=1e-6)
            assert m["excess_spy"] == pytest.approx(
                (mark / entry - 1.0) - (b_mark / b_entry - 1.0), abs=1e-6)
        # closed form on this fixture: (1.01^H - 1) - (1.002^H - 1)
        assert marks[10]["excess_spy"] == pytest.approx(1.01 ** 10 - 1.002 ** 10, abs=1e-6)
        assert marks[21]["excess_spy"] == pytest.approx(1.01 ** 21 - 1.002 ** 21, abs=1e-6)

    def test_entry_is_never_the_signal_bar(self):
        """A same-bar fill would be look-ahead; forward_metrics' next-bar convention forbids it."""
        from scripts import grade_prophet_doors as gpd
        idx, name, spy = self._pair()
        m = gpd.grade_flag(name, spy, idx[50])[10]
        assert m["entry_price"] != pytest.approx(float(name.iloc[50]), rel=1e-9)
        assert m["entry_price"] == pytest.approx(float(name.iloc[51]), rel=1e-9)

    def test_unmatured_horizons_are_absent_not_short_marked(self):
        from scripts import grade_prophet_doors as gpd
        idx, name, spy = self._pair(n=70)
        marks = gpd.grade_flag(name, spy, idx[55])          # 14 bars of forward room
        assert 10 in marks and 21 not in marks

    def test_missing_bench_yields_null_excess_not_a_crash(self):
        from scripts import grade_prophet_doors as gpd
        idx, name, _ = self._pair()
        m = gpd.grade_flag(name, None, idx[50])[10]
        assert m["bench_ret"] is None and m["excess_spy"] is None
        assert m["fwd_ret"] is not None

    def test_run_grades_matured_flags_and_freezes_them(self, tmp_path, nightly, monkeypatch):
        from scripts import grade_prophet_doors as gpd
        idx, name, spy = self._pair()
        px = pd.DataFrame({"AAA": name})
        monkeypatch.setattr(gpd, "load_bench", lambda root=None: spy)
        pdz.append_flags([{"schema": pdz.SCHEMA, "date": str(idx[50].date()),
                           "door": pdz.DOOR_T, "ticker": "AAA", "features": {}}], tmp_path)
        first = gpd.run(tmp_path, dry_run=False, universe=px)
        assert first["new_grades"] == 2 and first["appended"] == 2
        # one-grader law: a second pass re-grades nothing
        second = gpd.run(tmp_path, dry_run=False, universe=px)
        assert second["new_grades"] == 0
        assert len(gpd.load_grades(tmp_path)) == 2

    def test_run_on_an_empty_ledger_is_a_clean_no_op(self, tmp_path, nightly):
        from scripts import grade_prophet_doors as gpd
        doc = gpd.run(tmp_path, dry_run=False)
        assert doc["n_flags"] == 0 and doc["new_grades"] == 0
        assert "prospective" in doc["note"]


# =========================================================================== #
# 6. NO AUTHORITY — the pick chain must not read this lane
# =========================================================================== #
PICK_CHAIN = (
    "scripts/build_stock_library.py",
    "engine/us_board_rank.py",
    "engine/prophet_bridge.py",
    "engine/signal_gate.py",
)


@pytest.mark.parametrize("rel", PICK_CHAIN)
def test_no_authority_pick_chain_never_imports_prophet_doors(rel):
    """Doors T/R are SHADOW-ACCRUAL: no board membership, no plan origination, no rank/gate/
    size influence. The fence is that nothing in the pick chain can even see them. Promotion
    requires PROPHET_DOORS_PREREG.md §4 plus an operator-ratified adjudication."""
    src = (REPO / rel).read_text(encoding="utf-8")
    assert "prophet_doors" not in src, f"{rel} references prophet_doors — shadow lane has authority"
    assert not re.search(r"import\s+.*\bprophet_doors\b", src), \
        f"{rel} imports prophet_doors (regex) — zero-authority invariant violated"


def test_no_authority_doors_do_not_import_the_board_or_bridge():
    """Reverse fence: the doors read the validated gate (signal_gate / confluence_tiers) and
    nothing else from the pick chain — no board ranker, no plan bridge, no library builder."""
    import_lines = "\n".join(
        ln for ln in (REPO / "engine" / "prophet_doors.py").read_text(encoding="utf-8").splitlines()
        if ln.strip().startswith(("import ", "from "))
    )
    for forbidden in ("build_stock_library", "us_board_rank", "prophet_bridge"):
        assert forbidden not in import_lines, f"prophet_doors must not import {forbidden}"


def test_no_authority_grader_stays_policy_free():
    """Fixed-horizon marks only — no stops, no exits. track_scoring carries that machinery and
    is deliberately NOT used here (grading a policy instead of the door)."""
    src = (REPO / "scripts" / "grade_prophet_doors.py").read_text(encoding="utf-8")
    import_lines = "\n".join(ln for ln in src.splitlines()
                             if ln.strip().startswith(("import ", "from ")))
    assert "track_scoring" not in import_lines
    assert "stop_level" not in src and "early_exit" not in src
