"""Prophet W3 shadow doors — Door T (theme-relay) + Door R (re-arm).

Covers, per the build brief:
  1. Door T fire condition — positive + negative per leg (membership, eligible, is_buyable).
  2. Door R fire condition — positive + negative per leg (eligible / ticks / above200 /
     weekly_bull / 2D completed cross / 3D StochRSI K>=D).
  3. Cap (25/door/night, overflow COUNTED and announced) + dedupe (<21 sessions).
  4. Nightly guard — an off-lane append is a no-op and leaves no file behind.
  5. Grading math vs a hand-computed case (next-bar fill, H sessions, excess vs SPY).
  6. NO AUTHORITY — the pick chain must not import prophet_doors.
  7. RECORDED FEATURES (prereg §9 addendum) — relay count/position, turnover-window honesty,
     foresight null disclosure, schema keys, and above all FIRE INVARIANCE: the fire set is
     byte-identical with the features on and off.

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


# =========================================================================== #
# 7. Recorded features — ANALYSIS ONLY (prereg §9 addendum, 2026-08-04)
# =========================================================================== #
def _relay_universe(breakouts: dict[str, int | None], n: int = 430) -> pd.DataFrame:
    """Close frame where each name prints EXACTLY ONE fresh 63-session high, ``offset``
    sessions back from the last bar (0 = the flag bar). ``None`` = never breaks out.

    A single upward step is the cleanest construction available: flat 100 before the step, flat
    101 from it. `close > max(prior 63 closes)` is then True on the step session and False
    everywhere else — the very next session's prior-63 window already contains the step, and
    before the step every comparison is 100 > 100. So a breakout DATE is exact, not approximate,
    and the relay arithmetic below can be pinned to a literal.
    """
    idx = pd.bdate_range("2022-01-03", periods=n)
    data = {}
    for t, off in breakouts.items():
        col = np.full(n, 100.0)
        if off is not None:
            col[n - 1 - off:] = 101.0
        data[t] = col
    return pd.DataFrame(data, index=idx)


def _seed_volumes(root: Path, index: pd.DatetimeIndex, vols: dict[str, list[float]],
                  *, end_offset: int = 0, group: str = "breadth") -> None:
    """Write a volume cache holding only the trailing sessions given, ending ``end_offset``
    sessions before the tape's last bar (0 = the cache reaches the flag bar)."""
    n = max(len(v) for v in vols.values())
    end = len(index) - end_offset
    frame = pd.DataFrame({t: [np.nan] * (n - len(v)) + [float(x) for x in v]
                          for t, v in vols.items()}, index=index[end - n:end])
    p = root / "data" / group
    p.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(p / pdz.VOLUME_CACHE_NAME)


def _seed_foresight(root: Path, themes: list[tuple[str, str, str]]) -> None:
    """Write a Foresight Desk artifact: (slug, display name, STAGE) triples."""
    p = root / "site" / "basketdata"
    p.mkdir(parents=True, exist_ok=True)
    (p / "foresight_cascade.json").write_text(
        json.dumps({"asof": "2026-08-04",
                    "themes": [{"theme": k, "name": nm, "stage": st} for k, nm, st in themes]}),
        encoding="utf-8")


def _patch_gate_by_prefix(monkeypatch):
    """T*-prefixed names get a Door T (eligible/buyable) verdict, everything else the Door R
    ran-shape. Lets one emit() exercise BOTH doors."""
    from engine import signal_gate
    monkeypatch.setattr(signal_gate, "gate",
                        lambda t, c: _buyable() if str(t).startswith("T") else _verdict())


def _mixed_universe(n: int = 430) -> pd.DataFrame:
    """Door T step-tape names + Door R wave names on one shared session index."""
    steps = _relay_universe({"TAAA": 1, "TBBB": 10, "TCCC": None, "TDDD": 4}, n=n)
    waves = pd.DataFrame({t: _wave(n=n, **R_POS).to_numpy() for t in ("RAAA", "RBBB")},
                         index=steps.index)
    return pd.concat([steps, waves], axis=1)


class TestFireInvariance:
    """THE load-bearing test of the addendum: recorded features change no flag, ever.

    The prereg froze the fire definitions before the first accrual row existed. Features were
    added after — so the claim "zero effect on fire/cap/dedupe" has to be checked, not asserted
    in a docstring. `emit(features=False)` skips the whole feature computer; the fire set it
    produces must be identical, and the feature keys must be purely ADDITIVE (no recorded
    fire field may be overwritten by a colliding feature name).
    """

    def _run_pair(self, tmp_path, monkeypatch):
        _patch_gate_by_prefix(monkeypatch)
        px = _mixed_universe()
        root = _seed_root(tmp_path, _rotation_doc(
            {"Software": ["TAAA", "TBBB", "TCCC", "TDDD", "RAAA"]}))
        _seed_volumes(root, px.index, {"TAAA": list(range(10, 130, 10))})
        _seed_foresight(root, [("software_platforms", "Software", "RE-RATING")])
        on = pdz.emit(root, dry_run=True, universe=px)
        off = pdz.emit(root, dry_run=True, universe=px, features=False)
        return on, off

    def test_fire_set_is_identical_with_features_on_and_off(self, tmp_path, monkeypatch, off_lane):
        on, off = self._run_pair(tmp_path, monkeypatch)
        # Not vacuous: an invariance test over an empty fire set proves nothing.
        assert on["flags"][pdz.DOOR_T] and on["flags"][pdz.DOOR_R], "both doors must fire here"
        for door in pdz.DOORS:
            assert ([r["ticker"] for r in on["flags"][door]]
                    == [r["ticker"] for r in off["flags"][door]]), door
        for key in ("candidates", "overflow", "deduped"):
            assert on[key] == off[key], key

    def test_features_are_purely_additive_never_an_overwrite(self, tmp_path, monkeypatch,
                                                             off_lane):
        """Every fire-recorded field survives byte-identical; the feature block is exactly the
        difference. A feature named e.g. `theme` would silently clobber a fire receipt."""
        on, off = self._run_pair(tmp_path, monkeypatch)
        for door in pdz.DOORS:
            for a, b in zip(on["flags"][door], off["flags"][door]):
                assert not (set(b["features"]) & set(pdz.FEATURE_KEYS)), \
                    "features=False must record no feature key"
                stripped = {k: v for k, v in a["features"].items() if k not in pdz.FEATURE_KEYS}
                assert stripped == b["features"], f"{door}/{a['ticker']} fire receipt changed"

    def test_a_broken_feature_source_cannot_change_a_flag(self, tmp_path, monkeypatch, off_lane):
        """Degrade-to-null, not degrade-to-crash: a raising feature leg records nulls and the
        night's flags are untouched."""
        _patch_gate_by_prefix(monkeypatch)
        px = _mixed_universe()
        root = _seed_root(tmp_path, _rotation_doc({"Software": ["TAAA", "TBBB", "TCCC"]}))
        good = pdz.emit(root, dry_run=True, universe=px)

        def _boom(self, ticker, theme):
            raise RuntimeError("relay input exploded")

        monkeypatch.setattr(pdz._RecordedFeatures, "_relay", _boom)
        bad = pdz.emit(root, dry_run=True, universe=px)
        for door in pdz.DOORS:
            assert ([r["ticker"] for r in bad["flags"][door]]
                    == [r["ticker"] for r in good["flags"][door]]), door
        row = bad["flags"][pdz.DOOR_T][0]["features"]
        assert all(k in row for k in pdz.FEATURE_KEYS), "a failed block is still a DISCLOSED null"
        assert row["relay_count_3d"] is None and row["turnover_pctile"] is None
        assert row["foresight_covered"] is False


class TestSchemaKeys:
    def test_every_emitted_flag_carries_every_feature_key(self, tmp_path, monkeypatch, off_lane):
        """Present-and-null, never absent: `features.get(k) is None` must mean "computed null",
        not "this row predates the addendum"."""
        _patch_gate_by_prefix(monkeypatch)
        px = _mixed_universe()
        root = _seed_root(tmp_path, _rotation_doc({"Software": ["TAAA", "TBBB", "RAAA"]}))
        run = pdz.emit(root, dry_run=True, universe=px)
        rows = run["flags"][pdz.DOOR_T] + run["flags"][pdz.DOOR_R]
        assert rows
        for r in rows:
            missing = [k for k in pdz.FEATURE_KEYS if k not in r["features"]]
            assert not missing, f"{r['door']}/{r['ticker']} missing {missing}"

    def test_run_document_discloses_each_feature_source(self, tmp_path, monkeypatch, off_lane):
        _patch_gate_by_prefix(monkeypatch)
        px = _mixed_universe()
        root = _seed_root(tmp_path, _rotation_doc({"Software": ["TAAA", "TBBB", "TCCC", "TDDD"]}))
        run = pdz.emit(root, dry_run=True, universe=px)
        src = run["feature_source"]
        assert src["enabled"] is True
        assert list(src["keys"]) == list(pdz.FEATURE_KEYS)
        assert src["relay"]["n_covered"] == 4
        # nothing seeded -> the reason is PRINTED, not silently swallowed
        assert src["turnover"]["ok"] is False and src["turnover"]["reason"]
        assert src["foresight"]["ok"] is False and src["foresight"]["reason"]


class TestRelayFeatures:
    """Relay count/position on a hand-constructed theme, pinned to literals.

    Fixture (offsets = sessions back from the flag bar):
      FLAG breaks out at 1, M1 at 1, M2 at 10, M3 never. Four covered members.
        relay_count_3d = OTHERS breaking out in the trailing 3 sessions        = {M1}     = 1
        relay_position = OTHERS breaking out strictly earlier, over n=4        = {M1,M2}/4 = 0.5
    FLAG's own breakout sits inside BOTH windows, so a self-inclusion bug reads 2 and 0.75 —
    the fixture discriminates the self-exclusion rule rather than merely exercising it.
    """
    THEME = "Software"
    OFFSETS = {"FLAG": 1, "M1": 1, "M2": 10, "M3": None}

    def _run(self, tmp_path, monkeypatch, offsets=None):
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        offsets = offsets or self.OFFSETS
        px = _relay_universe(offsets)
        root = _seed_root(tmp_path, _rotation_doc({self.THEME: list(offsets)}))
        run = pdz.emit(root, dry_run=True, universe=px)
        return {r["ticker"]: r["features"] for r in run["flags"][pdz.DOOR_T]}

    def test_count_and_position_on_a_constructed_theme(self, tmp_path, monkeypatch, off_lane):
        f = self._run(tmp_path, monkeypatch)["FLAG"]
        assert f["relay_members_covered"] == 4
        assert f["relay_count_3d"] == 1
        assert f["relay_position"] == 0.5

    def test_the_flags_own_breakout_is_excluded_from_its_own_relay(self, tmp_path, monkeypatch,
                                                                   off_lane):
        """M1 and FLAG break out on the same session, so their readings must differ by exactly
        the self-exclusion: M1 sees FLAG as a relay peer and vice versa."""
        feats = self._run(tmp_path, monkeypatch)
        assert feats["M1"]["relay_count_3d"] == 1 and feats["M1"]["relay_position"] == 0.5
        # M2 broke out 10 sessions back: FLAG and M1 are both later, so none is "earlier"
        # within its trailing-3 window but both are earlier than... M2? No — they are LATER.
        assert feats["M2"]["relay_count_3d"] == 2, "FLAG and M1 both printed inside 3 sessions"
        assert feats["M2"]["relay_position"] == 0.5, "FLAG and M1 printed before the flag bar"

    def test_denominator_is_the_theme_not_the_row(self, tmp_path, monkeypatch, off_lane):
        """One covered-member count for the whole theme on the night — the position numbers of
        two members of the same theme are comparable only if the denominator is shared."""
        feats = self._run(tmp_path, monkeypatch)
        assert {f["relay_members_covered"] for f in feats.values()} == {4}

    def test_first_mover_reads_zero(self, tmp_path, monkeypatch, off_lane):
        """The 0 end of the scale: nobody in the theme broke out before the flag bar."""
        feats = self._run(tmp_path, monkeypatch,
                          {"FLAG": 0, "M1": None, "M2": None, "M3": None})
        assert feats["FLAG"]["relay_position"] == 0.0
        assert feats["FLAG"]["relay_count_3d"] == 0

    def test_thin_theme_nulls_position_but_still_counts(self, tmp_path, monkeypatch, off_lane):
        """Below RELAY_MIN_MEMBERS a "position" is an artefact of the denominator, so it is
        null — but the raw count is not gated, and n is disclosed either way."""
        feats = self._run(tmp_path, monkeypatch, {"FLAG": 1, "M1": 1, "M2": 10})
        f = feats["FLAG"]
        assert f["relay_members_covered"] == 3 < pdz.RELAY_MIN_MEMBERS
        assert f["relay_position"] is None
        assert f["relay_count_3d"] == 1

    def test_a_peer_breaking_out_on_the_flag_bar_is_not_earlier(self, tmp_path, monkeypatch,
                                                                off_lane):
        """Simultaneous is not earlier. M3 prints its high on the flag bar itself: it is a
        relay peer inside the trailing-3 COUNT, but it did not precede the flag, so it must
        stay out of the POSITION numerator. Offsets: FLAG 5, M1 1, M2 10, M3 0, M4 never.
            count    = others in the trailing 3 sessions       = {M1, M3}     = 2
            position = others strictly earlier, over n=5       = {M1, M2}/5   = 0.4
        Counting the flag bar as "earlier" would read 0.6 — the fixture separates the two."""
        feats = self._run(tmp_path, monkeypatch,
                          {"FLAG": 5, "M1": 1, "M2": 10, "M3": 0, "M4": None})
        f = feats["FLAG"]
        assert f["relay_members_covered"] == 5
        assert f["relay_count_3d"] == 2
        assert f["relay_position"] == 0.4

    def test_breakout_is_a_new_high_not_a_standing_one(self, tmp_path, monkeypatch, off_lane):
        """A name parked AT its 63-session high for weeks is not relaying. Only the session the
        high was PRINTED counts, so a step 30 sessions back is outside the 21-session window."""
        feats = self._run(tmp_path, monkeypatch,
                          {"FLAG": 0, "M1": 30, "M2": 40, "M3": 50})
        assert feats["FLAG"]["relay_position"] == 0.0
        assert feats["FLAG"]["relay_count_3d"] == 0

    def test_a_name_in_no_hot_theme_records_disclosed_nulls(self, tmp_path, monkeypatch,
                                                            off_lane):
        """Door R fires on names with no theme at all — the null is disclosed, not absent."""
        _patch_gate_by_prefix(monkeypatch)
        px = _mixed_universe()
        root = _seed_root(tmp_path, _rotation_doc({"Software": ["TAAA", "TBBB"]}))
        run = pdz.emit(root, dry_run=True, universe=px)
        r = [x for x in run["flags"][pdz.DOOR_R] if x["ticker"] == "RBBB"]
        assert r, "the Door R no-theme case must actually fire"
        f = r[0]["features"]
        assert f["theme"] is None
        assert f["relay_count_3d"] is None and f["relay_position"] is None
        assert f["relay_members_covered"] is None
        assert f["foresight_stage"] is None and f["foresight_covered"] is False

    def test_door_r_uses_its_names_best_ranked_theme(self, tmp_path, monkeypatch, off_lane):
        """A Door R name that IS in a hot theme relays against that theme, same as Door T."""
        _patch_gate_by_prefix(monkeypatch)
        px = _mixed_universe()
        root = _seed_root(tmp_path, _rotation_doc(
            {"Software": ["TAAA", "TBBB", "TCCC", "TDDD", "RAAA"]}))
        run = pdz.emit(root, dry_run=True, universe=px)
        f = [x for x in run["flags"][pdz.DOOR_R] if x["ticker"] == "RAAA"][0]["features"]
        assert f["theme"] == "Software"
        assert f["relay_members_covered"] == 5
        assert f["relay_position"] is not None

    def test_a_member_with_a_hole_is_excluded_from_coverage(self, tmp_path, monkeypatch,
                                                            off_lane):
        """`close > NaN` is False, so a data hole would silently read as "did not break out".
        The strict-coverage rule turns that into an honest exclusion from the denominator."""
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        px = _relay_universe({"FLAG": 1, "M1": 1, "M2": 10, "M3": None, "M4": None})
        px.loc[px.index[-5], "M4"] = np.nan          # one hole inside the 84-session tail
        root = _seed_root(tmp_path, _rotation_doc({self.THEME: list(px.columns)}))
        run = pdz.emit(root, dry_run=True, universe=px)
        feats = {r["ticker"]: r["features"] for r in run["flags"][pdz.DOOR_T]}
        assert feats["FLAG"]["relay_members_covered"] == 4, "M4 is not measurable, not a zero"
        assert feats["M4"]["relay_members_covered"] == 4
        assert feats["FLAG"]["relay_position"] == 0.5


class TestTurnoverHonesty:
    """The roadmap names the volume-cache depth as debt: these caches were backfilled
    2026-05-19 and the median column holds ~51 non-null sessions. The feature records the
    window it actually used and never claims a 60-session read it cannot support."""

    def _run(self, tmp_path, monkeypatch, vols, *, end_offset=0):
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        px = _relay_universe({"FLAG": 1, "M1": 1, "M2": 10, "M3": None})
        root = _seed_root(tmp_path, _rotation_doc({"Software": list(px.columns)}))
        _seed_volumes(root, px.index, vols, end_offset=end_offset)
        run = pdz.emit(root, dry_run=True, universe=px)
        return {r["ticker"]: r["features"] for r in run["flags"][pdz.DOOR_T]}

    def test_short_cache_records_the_window_it_actually_had(self, tmp_path, monkeypatch,
                                                            off_lane):
        """12 sessions available, 60 requested -> the RECORDED window is 12. Six of the twelve
        sessions sit at or below the admission-day volume, so the percentile is 0.5."""
        vols = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 55]
        f = self._run(tmp_path, monkeypatch, {"FLAG": vols})["FLAG"]
        assert f["turnover_window"] == 12
        assert f["turnover_window"] < pdz.TURNOVER_WINDOW_MAX
        assert f["turnover_pctile"] == 0.5

    def test_window_is_capped_at_the_maximum_when_history_allows(self, tmp_path, monkeypatch,
                                                                 off_lane):
        """min(60, available) is a MINIMUM, not a floor: a deep cache is trimmed to 60."""
        vols = [float(i) for i in range(1, 91)]            # 90 sessions, ascending
        f = self._run(tmp_path, monkeypatch, {"FLAG": vols})["FLAG"]
        assert f["turnover_window"] == pdz.TURNOVER_WINDOW_MAX
        assert f["turnover_pctile"] == 1.0                 # the last bar is the window's max

    def test_no_admission_day_volume_is_null_never_a_stale_read(self, tmp_path, monkeypatch,
                                                                off_lane):
        """A cache that stops one session short has no admission-day volume. Reading the prior
        session's would fabricate the feature, so BOTH fields go null."""
        f = self._run(tmp_path, monkeypatch, {"FLAG": [10, 20, 30, 40, 50]},
                      end_offset=1)["FLAG"]
        assert f["turnover_pctile"] is None
        assert f["turnover_window"] is None

    def test_absent_cache_is_a_disclosed_null(self, tmp_path, monkeypatch, off_lane):
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        px = _relay_universe({"FLAG": 1, "M1": 1, "M2": 10, "M3": None})
        root = _seed_root(tmp_path, _rotation_doc({"Software": list(px.columns)}))
        run = pdz.emit(root, dry_run=True, universe=px)          # no volume cache seeded
        f = run["flags"][pdz.DOOR_T][0]["features"]
        assert f["turnover_pctile"] is None and f["turnover_window"] is None
        assert "absent" in run["feature_source"]["turnover"]["reason"]

    def test_a_single_observation_window_is_null_not_a_perfect_score(self, tmp_path, monkeypatch,
                                                                     off_lane):
        """A percentile over one observation is definitionally 1.0 and carries no information;
        recording it would put a top-decile-looking number on a name nobody measured."""
        f = self._run(tmp_path, monkeypatch, {"FLAG": [42.0]})["FLAG"]
        assert f["turnover_window"] == 1
        assert f["turnover_pctile"] is None


class TestForesightJoin:
    """Read-only join onto the Thematic Foresight Desk. The two taxonomies were built
    independently, so partial coverage is the expected state and must be DISCLOSED."""

    def _run(self, tmp_path, monkeypatch, themes=None, theme_name="Software"):
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        px = _relay_universe({"FLAG": 1, "M1": 1, "M2": 10, "M3": None})
        root = _seed_root(tmp_path, _rotation_doc({theme_name: list(px.columns)}))
        if themes is not None:
            _seed_foresight(root, themes)
        run = pdz.emit(root, dry_run=True, universe=px)
        return run, {r["ticker"]: r["features"] for r in run["flags"][pdz.DOOR_T]}

    def test_covered_theme_records_the_desk_stage(self, tmp_path, monkeypatch, off_lane):
        _, feats = self._run(tmp_path, monkeypatch,
                             [("ai_semiconductors", "AI Semiconductors", "RE-RATING"),
                              ("software_platforms", "Software", "BROADENING (text)")])
        assert feats["FLAG"]["foresight_stage"] == "BROADENING (text)"
        assert feats["FLAG"]["foresight_covered"] is True

    def test_join_normalises_punctuation_and_case(self, tmp_path, monkeypatch, off_lane):
        """The rotation artifact names themes in display form ("Defense & Aerospace"); the desk
        carries both a slug and a display name. Normalised-exact matches both, nothing else."""
        _, feats = self._run(tmp_path, monkeypatch,
                             [("defense_aerospace", "Defense & Aerospace", "WATCH")],
                             theme_name="Defense  &  AEROSPACE")
        assert feats["FLAG"]["foresight_stage"] == "WATCH"

    def test_slug_only_theme_also_joins(self, tmp_path, monkeypatch, off_lane):
        _, feats = self._run(tmp_path, monkeypatch,
                             [("nuclear_power", "Nuclear & SMR Power", "PRECIPICE (text)")],
                             theme_name="nuclear_power")
        assert feats["FLAG"]["foresight_stage"] == "PRECIPICE (text)"

    def test_uncovered_theme_is_a_disclosed_null_never_a_guess(self, tmp_path, monkeypatch,
                                                               off_lane):
        """No near-miss matching: a desk that does not cover the theme yields null + covered
        false. Fuzzy-joining "Software" onto "Semiconductor Equipment (WFE)" would invent
        coverage the desk never claimed."""
        _, feats = self._run(tmp_path, monkeypatch,
                             [("semicap_equipment", "Semiconductor Equipment (WFE)", "WATCH")])
        assert feats["FLAG"]["foresight_stage"] is None
        assert feats["FLAG"]["foresight_covered"] is False

    def test_a_NEAR_miss_theme_name_does_not_join(self, tmp_path, monkeypatch, off_lane):
        """The dangerous case an unrelated-names test cannot see: a rotation theme that SHARES
        a prefix and CONTAINS the desk theme as a substring. "Solar Inverters" normalises to
        `solarinverters`, the desk's Solar to `solar` — prefix or substring matching would join
        them and stamp a component sub-theme with the parent's stage. Exact-after-normalisation
        is the whole guard, so it needs a fixture that would survive the looser rules."""
        _, feats = self._run(tmp_path, monkeypatch,
                             [("solar", "Solar", "WATCH")],
                             theme_name="Solar Inverters")
        assert feats["FLAG"]["foresight_stage"] is None
        assert feats["FLAG"]["foresight_covered"] is False

    def test_absent_desk_artifact_discloses_its_reason(self, tmp_path, monkeypatch, off_lane):
        run, feats = self._run(tmp_path, monkeypatch)          # no artifact seeded
        assert feats["FLAG"]["foresight_stage"] is None
        assert feats["FLAG"]["foresight_covered"] is False
        assert "absent" in run["feature_source"]["foresight"]["reason"]

    def test_unreadable_desk_artifact_fails_soft(self, tmp_path, monkeypatch, off_lane):
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        px = _relay_universe({"FLAG": 1, "M1": 1, "M2": 10, "M3": None})
        root = _seed_root(tmp_path, _rotation_doc({"Software": list(px.columns)}))
        p = root / "site" / "basketdata"
        p.mkdir(parents=True, exist_ok=True)
        (p / "foresight_cascade.json").write_text("{not json", encoding="utf-8")
        run = pdz.emit(root, dry_run=True, universe=px)
        assert run["flags"][pdz.DOOR_T], "a broken desk must not close the door"
        assert run["flags"][pdz.DOOR_T][0]["features"]["foresight_covered"] is False
        assert "unreadable" in run["feature_source"]["foresight"]["reason"]

    def test_stageless_desk_theme_is_not_coverage(self, tmp_path, monkeypatch, off_lane):
        _, feats = self._run(tmp_path, monkeypatch, [("software_platforms", "Software", "")])
        assert feats["FLAG"]["foresight_covered"] is False


class TestFeatureScopeFences:
    """Structural fences: the features are analysis-tier and stay there."""

    def test_features_never_touch_the_grader(self):
        """The ruler grades price, not features. A grader that read a feature would be grading
        a filter it never pre-registered (prereg §2, one-grader law)."""
        src = (REPO / "scripts" / "grade_prophet_doors.py").read_text(encoding="utf-8")
        for key in pdz.FEATURE_KEYS:
            assert key not in src, f"grade_prophet_doors reads {key} — the ruler must stay blind"

    def test_feature_computation_runs_after_the_cap(self, tmp_path, monkeypatch, off_lane):
        """Bounded work: at most MAX_FLAGS_PER_DOOR rows per door are ever featurised, so an
        overflowing night costs the same as a quiet one."""
        seen: list[str] = []
        real = pdz._RecordedFeatures.compute

        def _spy(self, ticker, theme):
            seen.append(str(ticker))
            return real(self, ticker, theme)

        monkeypatch.setattr(pdz._RecordedFeatures, "compute", _spy)
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        tickers = [f"T{i:02d}" for i in range(pdz.MAX_FLAGS_PER_DOOR + 7)]
        root = _seed_root(tmp_path, _rotation_doc({"Software": tickers}))
        run = pdz.emit(root, dry_run=True, universe=_universe(tickers))
        assert run["overflow"][pdz.DOOR_T] == 7, "this fixture must actually overflow"
        assert len(seen) == pdz.MAX_FLAGS_PER_DOOR, "dropped candidates must never be featurised"
        assert set(seen) == {r["ticker"] for r in run["flags"][pdz.DOOR_T]}

    def test_deduped_candidates_are_never_featurised(self, tmp_path, monkeypatch, nightly):
        seen: list[str] = []
        real = pdz._RecordedFeatures.compute
        monkeypatch.setattr(pdz._RecordedFeatures, "compute",
                            lambda self, t, th: (seen.append(str(t)), real(self, t, th))[1])
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        root = _seed_root(tmp_path, _rotation_doc({"Software": ["AAA", "BBB"]}))
        px = _universe(["AAA", "BBB"])
        pdz.append_flags([{"schema": pdz.SCHEMA, "date": str(px.index[-2].date()),
                           "door": pdz.DOOR_T, "ticker": "AAA", "features": {}}], root)
        pdz.emit(root, dry_run=True, universe=px)
        assert seen == ["BBB"], "a deduped ticker must not be featurised"

    def test_feature_constants_are_documented_as_analysis_only(self):
        """The frozen door constants and the analysis constants live in separate, labelled
        blocks — a future edit must not be able to mistake one for the other."""
        src = (REPO / "engine" / "prophet_doors.py").read_text(encoding="utf-8")
        assert "RECORDED-FEATURE constants — ANALYSIS ONLY" in src
        assert "FROZEN construction constants" in src


def test_prereg_carries_the_recorded_features_addendum():
    """The features were registered BEFORE the first read, in the frozen document itself —
    that is what makes them analysis features rather than a post-hoc filter."""
    doc = (REPO / "research" / "PROPHET_DOORS_PREREG.md").read_text(encoding="utf-8")
    assert "Recorded features (2026-08-04 addendum)" in doc
    for key in pdz.FEATURE_KEYS:
        assert f"`{key}`" in doc, f"{key} is recorded but not pre-registered"
