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

from engine import ignition_features as ig
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


# RE-DERIVED under the abs-session anchor (era abs-session-2026-08-06). The 2D/3D buckets are
# no longer phased to the series' first timestamp, so a fixture's phase index shifts; each
# triple was re-measured against the CURRENT confluence_tiers math to isolate the SAME leg it
# always isolated. The wave/amp/drift shapes are untouched — only `phase` moved (+1, +1, +2),
# which is precisely the re-phase the anchor change predicts.
#   R_POS      -> 2D cross-up on the last COMPLETED bucket = True,  3D K 30.41 >= D 28.23
#                 (was phase=5, K 30.46 >= D 28.41 pre-anchor)
#   R_NO_CROSS -> 2D cross-up = False,                              3D K 54.51 >= D 32.78
#                 (was phase=7, K 51.46 >= D 29.07 pre-anchor)
#   R_NO_STOCH -> 2D cross-up = True,                               3D K 37.45 <  D 48.69
#                 (was phase=4, K 33.66 <  D 50.06 pre-anchor)
R_POS = dict(wave=18, amp=0.08, drift=0.0016, phase=6)
R_NO_CROSS = dict(wave=18, amp=0.08, drift=0.0016, phase=8)
R_NO_STOCH = dict(wave=12, amp=0.04, drift=0.0016, phase=6)


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
        """Guards against completed_tf silently degrading into _tf_bars. A series whose last
        bar OPENS its 2-session bucket leaves that bucket in progress, so a spike ON that bar
        must move the raw read and leave the completed read byte-identical.

        RE-DERIVED under the abs-session anchor: "in progress" is now the last bar's session
        POSITION (``pos % 2 == 0`` opens a 2-bucket), not the series' length parity.
        """
        from engine.confluence_tiers import _tf_bars
        from engine.session_anchor import session_positions
        base = _wave(n=430, **R_POS)
        pos = session_positions(base.index)
        opening = np.where(pos % 2 == 0)[0]          # last bar OPENS its bucket -> in progress
        base = base.iloc[:opening[-1] + 1]
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
        """The truncation is CONDITIONAL, not unconditional — dropping a bucket that has in
        fact closed would delay every Door R fire by a session.

        RE-DERIVED under the abs-session anchor. The condition is no longer the series'
        LENGTH parity (which is what mattered when bins were phased to the series start): a
        bucket spans reference positions [b*n, b*n+n-1], so it closes when the last session's
        POSITION sits on b*n+n-1. This test picks its last bar by that arithmetic, so it
        keeps testing "a closed bucket survives" rather than a length coincidence.

        It is also the regression guard for the index-semantics change: `_tf_bars` used to be
        indexed by pandas' bin START and is now indexed by each bucket's LAST SESSION, and
        `completed_tf` reads that index. The old "label + n-1 business days" test applied to
        the new index drops closed buckets — this test reds on exactly that.
        """
        from engine.confluence_tiers import _tf_bars
        from engine.session_anchor import session_positions
        base = _wave(n=430, **R_POS)
        # trim to a last bar that CLOSES its 2-session bucket
        pos = session_positions(base.index)
        closed = np.where(pos % 2 == 1)[0]
        base = base.iloc[:closed[-1] + 1]
        raw, _ = _tf_bars(base, 2)
        comp, _ = pdz.completed_tf(base, 2)
        assert len(comp) == len(raw), "a CLOSED tail bucket must survive the truncation"
        # and the complement: one session earlier the bucket is still open, so it is dropped
        open_tail = base.iloc[:-1]
        raw_o, _ = _tf_bars(open_tail, 2)
        comp_o, _ = pdz.completed_tf(open_tail, 2)
        assert len(comp_o) == len(raw_o) - 1, "an OPEN tail bucket must be dropped"


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
        # Six members, not five: the theme must clear THRUST_MIN_MEMBERS or the thrust feature
        # degrades to `thin_membership` and the invariance check below goes dark.
        root = _seed_root(tmp_path, _rotation_doc(
            {"Software": ["TAAA", "TBBB", "TCCC", "TDDD", "RAAA", "RBBB"]}))
        _seed_volumes(root, px.index, {"TAAA": list(range(10, 130, 10))})
        _seed_foresight(root, [("software_platforms", "Software", "RE-RATING")])
        # Every feature source is seeded, INCLUDING the W8 ignition store: an invariance test
        # whose features all degraded to null would pass no matter what the computer did.
        _seed_ohlcv(root, {t: _coil_ohlc(px.index, quiet=q) for t, q in
                           (("TAAA", 45), ("TBBB", 0), ("TCCC", 45), ("TDDD", 0),
                            ("RAAA", 45), ("RBBB", 0))})
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

    def test_the_ignition_features_actually_computed_in_this_fixture(self, tmp_path, monkeypatch,
                                                                     off_lane):
        """Guards the invariance tests above from going dark. If the ignition store stopped
        resolving, every W8 key would be null, both runs would still agree, and the invariance
        claim would hold vacuously over features that never ran."""
        on, _ = self._run_pair(tmp_path, monkeypatch)
        rows = [r["features"] for r in on["flags"][pdz.DOOR_T]]
        assert any(r["coil_compressed"] is not None for r in rows), "coil never computed"
        assert any(r["coil_compressed"] is True for r in rows), "no compressed name in fixture"
        assert any(r["coil_compressed"] is False for r in rows), "no uncompressed name in fixture"
        assert all(r["theme_thrust_state"] is not None for r in rows), "thrust never computed"

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
        # The crash path must not manufacture a measured negative either. `foresight_covered`
        # is the ONE deliberate False in the block (a coverage flag); every other key — the W8
        # states included — is null, so a reader can never mistake "the computer died" for
        # "this name is not compressed" or "this theme is quiet".
        assert row["coil_compressed"] is None and row["coil_bars_compressed"] is None
        assert row["theme_thrust_state"] is None and row["theme_thrust_frac"] is None
        assert [k for k, v in row.items()
                if k in pdz.FEATURE_KEYS and v is not None] == ["foresight_covered"]


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


# --------------------------------------------------------------------------- #
# W8 ignition features (prereg §10 addendum, 2026-08-05)
# --------------------------------------------------------------------------- #
def _coil_ohlc(index: pd.DatetimeIndex, *, quiet: int, expand: int = 0) -> pd.DataFrame:
    """close/high/low on ``index``: a loud regime, then ``quiet`` calm sessions, then
    ``expand`` sessions of range expansion.

    Deterministic (no RNG). The loud regime fills the 252-session ATR reference window with big
    true ranges, so the calm phase ranks under p25 while steady drift keeps price above a rising
    50dMA — both S-COIL legs hold. ``quiet=0`` never compresses; a long enough ``expand`` tail
    lifts ATR back out of compression while the trailing 21-session count is still positive,
    which is the compressed-THEN-EXPANDING case.
    """
    n = len(index)
    loud = n - quiet - expand
    rets = ([0.030 * (1 if i % 2 == 0 else -1) for i in range(loud)] + [0.0015] * quiet
            + [0.045 * (1 if i % 2 == 0 else -1) for i in range(expand)])
    close = 100.0 * np.exp(np.cumsum(rets))
    w = np.array([0.020] * loud + [0.0004] * quiet + [0.030] * expand)
    return pd.DataFrame({"close": close, "high": close * (1 + w), "low": close * (1 - w)},
                        index=index)


def _flat_ohlc(index: pd.DatetimeIndex, *, jump: bool) -> pd.DataFrame:
    """A member flat at 100 — nobody above its own 20d high — optionally stepping up on the
    FINAL bar, which is what carries a theme's above-20d-high fraction from 0 to 1."""
    v = np.full(len(index), 100.0)
    if jump:
        v[-1] = 130.0
    return pd.DataFrame({"close": v, "high": v, "low": v * 0.999}, index=index)


def _seed_ohlcv(root: Path, frames: dict[str, pd.DataFrame]) -> None:
    """Write per-ticker OHLCV parquets where `_RecordedFeatures._ohlcv` reads them."""
    p = root / Path(*pdz.OHLCV_DIR)
    p.mkdir(parents=True, exist_ok=True)
    for t, d in frames.items():
        d.to_parquet(p / f"{t}.parquet")


class TestCoilFeature:
    """S-COIL compression state for the flag's own name, at the flag bar."""

    def _run(self, tmp_path, monkeypatch, frames, tickers=("FLAG",)):
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        px = _universe(list(tickers))
        root = _seed_root(tmp_path, _rotation_doc({"Software": list(tickers)}))
        _seed_ohlcv(root, {t: f(px.index) for t, f in frames.items()})
        run = pdz.emit(root, dry_run=True, universe=px)
        return run, {r["ticker"]: r["features"] for r in run["flags"][pdz.DOOR_T]}

    def test_a_compressed_name_records_the_state_and_the_bar_count(self, tmp_path, monkeypatch,
                                                                    off_lane):
        _, feats = self._run(tmp_path, monkeypatch,
                             {"FLAG": lambda i: _coil_ohlc(i, quiet=45)})
        f = feats["FLAG"]
        assert f["coil_compressed"] is True
        assert f["coil_bars_compressed"] == 21
        assert f["coil_reason"] is None

    def test_a_never_compressed_name_records_a_measured_False(self, tmp_path, monkeypatch,
                                                               off_lane):
        """False here is a MEASUREMENT, and it is only legible as one because the uncomputable
        cases below record null instead."""
        _, feats = self._run(tmp_path, monkeypatch,
                             {"FLAG": lambda i: _coil_ohlc(i, quiet=0)})
        f = feats["FLAG"]
        assert f["coil_compressed"] is False
        assert f["coil_bars_compressed"] == 0
        assert f["coil_reason"] is None

    def test_a_compressed_then_expanding_name_separates_the_two_fields(self, tmp_path,
                                                                        monkeypatch, off_lane):
        """The state and the count are INDEPENDENT readings, and this is the case that proves
        it in the direction the partial-run fixture cannot: range expansion has lifted the name
        out of compression at the flag bar (`coil_compressed False`) while the trailing 21
        sessions still hold a positive compressed count. A single boolean would have collapsed
        these two facts into one, which is why the count is recorded rather than a threshold."""
        _, feats = self._run(tmp_path, monkeypatch,
                             {"FLAG": lambda i: _coil_ohlc(i, quiet=45, expand=15)})
        f = feats["FLAG"]
        assert f["coil_compressed"] is False
        assert f["coil_bars_compressed"] == 18
        assert f["coil_bars_compressed"] >= ig.COMP_MIN, (
            "still ARMED by S-COIL's own >=10-of-21 run while no longer compressed — exactly "
            "the state a boolean-only record would have erased")
        assert f["coil_reason"] is None

    def test_absent_store_entry_is_null_with_a_reason_never_False(self, tmp_path, monkeypatch,
                                                                   off_lane):
        _, feats = self._run(tmp_path, monkeypatch, {})          # nothing seeded
        f = feats["FLAG"]
        assert f["coil_compressed"] is None, "an unmeasurable name is NOT an uncompressed name"
        assert f["coil_bars_compressed"] is None
        assert f["coil_reason"] == "ohlcv_absent"

    def test_short_history_is_null_with_a_reason(self, tmp_path, monkeypatch, off_lane):
        """The floor's whole purpose: `coil_compression` is a boolean AND, so a warming-up name
        would otherwise record a confident 'not compressed, 0 bars'."""
        short = pdz.MIN_HISTORY + 5
        assert short < ig.COIL_MIN_SESSIONS, "fixture must sit below the coil floor"
        _, feats = self._run(tmp_path, monkeypatch,
                             {"FLAG": lambda i: _coil_ohlc(i, quiet=45).tail(short)})
        f = feats["FLAG"]
        assert f["coil_compressed"] is None and f["coil_bars_compressed"] is None
        assert f["coil_reason"] == "short_history"

    def test_a_store_that_stops_before_the_flag_bar_is_null_never_a_stale_read(
            self, tmp_path, monkeypatch, off_lane):
        """Carrying the last available session forward would date-shift the feature onto a bar
        the name did not trade — the same rule `_turnover` applies to admission-day volume."""
        _, feats = self._run(tmp_path, monkeypatch,
                             {"FLAG": lambda i: _coil_ohlc(i, quiet=45).iloc[:-3]})
        f = feats["FLAG"]
        assert f["coil_compressed"] is None
        assert f["coil_reason"] == "no_bar_on_flag_date"

    def test_an_interior_hole_does_not_manufacture_an_uncompressed_reading(
            self, tmp_path, monkeypatch, off_lane):
        """Holes are DROPPED, not held. Held as NaN they propagate through every rolling window
        covering them, and because the detector is a boolean AND that lands as `False` — this
        exact fixture reads (True, 21) when dropped and (False, 15) when held, i.e. the hole
        would invent a measured negative for a genuinely compressed name."""
        def _holed(index):
            d = _coil_ohlc(index, quiet=45).copy()
            d.iloc[-6, d.columns.get_loc("close")] = np.nan
            return d

        _, feats = self._run(tmp_path, monkeypatch, {"FLAG": _holed})
        f = feats["FLAG"]
        assert f["coil_compressed"] is True, "a hole must not read as 'not compressed'"
        assert f["coil_bars_compressed"] == 21
        assert f["coil_reason"] is None

    def test_an_unreadable_parquet_is_a_disclosed_null(self, tmp_path, monkeypatch, off_lane):
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        px = _universe(["FLAG"])
        root = _seed_root(tmp_path, _rotation_doc({"Software": ["FLAG"]}))
        p = root / Path(*pdz.OHLCV_DIR)
        p.mkdir(parents=True, exist_ok=True)
        (p / "FLAG.parquet").write_bytes(b"not a parquet file")
        run = pdz.emit(root, dry_run=True, universe=px)
        f = run["flags"][pdz.DOOR_T][0]["features"]
        assert f["coil_compressed"] is None
        assert f["coil_reason"] == "read_failed"
        assert run["feature_source"]["ignition"]["null_reasons"] == {"read_failed": 1}

    def test_the_declared_reason_vocabulary_is_exactly_what_the_code_emits(
            self, tmp_path, monkeypatch, off_lane):
        """`COIL_REASONS` is a CONTRACT, not a comment: every slug in it must be reachable and
        every slug the code emits must be in it. A declared-but-unreachable slug over-claims in
        the prereg; an emitted-but-undeclared one is an undocumented null."""
        seen = set()
        for sub, frames in (("absent", {}),
                            ("stale", {"FLAG": lambda i: _coil_ohlc(i, quiet=45).iloc[:-3]}),
                            ("short", {"FLAG": lambda i: _coil_ohlc(i, quiet=45).tail(120)})):
            _, feats = self._run(tmp_path / sub, monkeypatch, frames)
            seen.add(feats["FLAG"]["coil_reason"])
        seen.add("read_failed")   # exercised by the test above
        assert seen == set(pdz.COIL_REASONS), (
            f"declared-not-reached={set(pdz.COIL_REASONS) - seen}, "
            f"reached-not-declared={seen - set(pdz.COIL_REASONS)}")

    def test_the_run_document_discloses_what_the_store_offered(self, tmp_path, monkeypatch,
                                                                off_lane):
        run, _ = self._run(tmp_path, monkeypatch, {"FLAG": lambda i: _coil_ohlc(i, quiet=45)},
                           tickers=("FLAG", "GONE"))
        d = run["feature_source"]["ignition"]
        assert d["consulted"] is True
        assert d["tickers_read"] == 2 and d["tickers_ok"] == 1
        assert d["null_reasons"] == {"ohlcv_absent": 1}, "nulls are COUNTED, not swallowed"
        assert d["coil_min_sessions"] == ig.COIL_MIN_SESSIONS


class TestThemeThrustFeature:
    """S-THRUST-LAG thrust reading for the flag's own theme, at the flag bar."""

    MEMBERS = [f"M{i}" for i in range(8)]

    def _run(self, tmp_path, monkeypatch, *, jump: bool, seeded: int | None = None,
             members=None):
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        members = list(members or self.MEMBERS)
        px = _universe(members)
        root = _seed_root(tmp_path, _rotation_doc({"Software": members}))
        take = members if seeded is None else members[:seeded]
        _seed_ohlcv(root, {t: _flat_ohlc(px.index, jump=jump) for t in take})
        run = pdz.emit(root, dry_run=True, universe=px)
        return run, {r["ticker"]: r["features"] for r in run["flags"][pdz.DOOR_T]}

    def test_a_thrusting_theme_reads_thrusting(self, tmp_path, monkeypatch, off_lane):
        _, feats = self._run(tmp_path, monkeypatch, jump=True)
        f = feats["M0"]
        assert f["theme_thrust_state"] == "thrusting"
        assert f["theme_thrust_frac"] == 1.0
        assert f["theme_thrust_reason"] is None

    def test_a_quiet_theme_reads_quiet(self, tmp_path, monkeypatch, off_lane):
        _, feats = self._run(tmp_path, monkeypatch, jump=False)
        f = feats["M0"]
        assert f["theme_thrust_state"] == "quiet"
        assert f["theme_thrust_frac"] == 0.0
        assert f["theme_thrust_reason"] is None

    def test_every_flag_in_a_theme_reads_the_same_thrust(self, tmp_path, monkeypatch, off_lane):
        """The reading belongs to the THEME, not the row — it is computed once and shared, so
        two flags in one theme can never disagree about their theme's state."""
        _, feats = self._run(tmp_path, monkeypatch, jump=True)
        states = {t: (f["theme_thrust_state"], f["theme_thrust_frac"]) for t, f in feats.items()}
        assert len(feats) >= 2 and len(set(states.values())) == 1, states

    def test_thin_membership_is_null_with_a_reason_never_quiet(self, tmp_path, monkeypatch,
                                                                off_lane):
        """Below the stand-in's own readability floor a fraction is an artefact of its
        denominator, so it is a disclosed null — NOT the "quiet" a real reading would print."""
        seeded = ig.THRUST_MIN_MEMBERS - 2
        _, feats = self._run(tmp_path, monkeypatch, jump=True, seeded=seeded)
        f = feats["M0"]
        assert f["theme_thrust_state"] is None
        assert f["theme_thrust_frac"] is None
        assert f["theme_thrust_reason"] == "thin_membership"

    def test_no_covered_member_is_a_disclosed_null(self, tmp_path, monkeypatch, off_lane):
        _, feats = self._run(tmp_path, monkeypatch, jump=True, seeded=0)
        f = feats["M0"]
        assert f["theme_thrust_state"] is None
        assert f["theme_thrust_reason"] == "no_covered_member"

    def test_a_name_in_no_hot_theme_records_no_theme(self, tmp_path, monkeypatch, off_lane):
        """Door R fires on names outside every hot theme; those have no theme to read."""
        _patch_gate_by_prefix(monkeypatch)
        px = _mixed_universe()
        root = _seed_root(tmp_path, _rotation_doc({"Software": ["TAAA", "TBBB"]}))
        run = pdz.emit(root, dry_run=True, universe=px)
        rows = [r for r in run["flags"][pdz.DOOR_R] if not r["features"].get("theme")]
        assert rows, "fixture must produce a Door R flag outside every hot theme"
        f = rows[0]["features"]
        assert f["theme_thrust_state"] is None and f["theme_thrust_frac"] is None
        assert f["theme_thrust_reason"] == "no_theme"
        assert f["theme_thrust_reason"] in pdz.THRUST_REASONS

    def test_a_universe_shorter_than_the_thrust_window_is_a_disclosed_null(self):
        """`short_history` is NOT reachable through `emit()` — MIN_HISTORY (159) exceeds
        THRUST_MIN_SESSIONS (27), so any tape that can produce a flag is long enough. It is a
        defensive guard against an IndexError, reached here by driving the computer directly so
        the declared slug is neither dead nor untested."""
        assert pdz.MIN_HISTORY > ig.THRUST_MIN_SESSIONS, "premise of this test"
        px = _universe(["M0"], n=ig.THRUST_MIN_SESSIONS - 1)
        fx = pdz._RecordedFeatures(Path("."), px, {"M0": {"theme": "Software",
                                                          "themes_hit": ["Software"]}})
        out = fx._thrust("Software")
        assert out["theme_thrust_state"] is None and out["theme_thrust_frac"] is None
        assert out["theme_thrust_reason"] == "short_history"

    def test_the_declared_thrust_vocabulary_is_exactly_what_the_code_emits(
            self, tmp_path, monkeypatch, off_lane):
        seen = set()
        _, feats = self._run(tmp_path / "thin", monkeypatch, jump=True,
                             seeded=ig.THRUST_MIN_MEMBERS - 2)
        seen.add(feats["M0"]["theme_thrust_reason"])
        _, feats = self._run(tmp_path / "none", monkeypatch, jump=True, seeded=0)
        seen.add(feats["M0"]["theme_thrust_reason"])
        _patch_gate_by_prefix(monkeypatch)
        px = _mixed_universe()
        root = _seed_root(tmp_path / "notheme", _rotation_doc({"Software": ["TAAA", "TBBB"]}))
        run = pdz.emit(root, dry_run=True, universe=px)
        seen |= {r["features"]["theme_thrust_reason"] for r in run["flags"][pdz.DOOR_R]
                 if not r["features"].get("theme")}
        seen.add("short_history")   # exercised by the test above
        assert seen == set(pdz.THRUST_REASONS), (
            f"declared-not-reached={set(pdz.THRUST_REASONS) - seen}, "
            f"reached-not-declared={seen - set(pdz.THRUST_REASONS)}")

    def test_a_member_with_a_hole_is_excluded_rather_than_counted_as_below(
            self, tmp_path, monkeypatch, off_lane):
        """Strict coverage, matching the relay feature: a hole would make the 20d-high test read
        False and quietly deflate the fraction for a name nobody could measure."""
        from engine import signal_gate
        monkeypatch.setattr(signal_gate, "gate", lambda t, c: _buyable())
        members = self.MEMBERS
        px = _universe(members)
        frames = {t: _flat_ohlc(px.index, jump=True) for t in members}
        holed = frames["M7"].copy()
        holed.iloc[-4, holed.columns.get_loc("close")] = np.nan
        frames["M7"] = holed
        root = _seed_root(tmp_path, _rotation_doc({"Software": members}))
        _seed_ohlcv(root, frames)
        run = pdz.emit(root, dry_run=True, universe=px)
        f = {r["ticker"]: r["features"] for r in run["flags"][pdz.DOOR_T]}["M0"]
        # 7 covered members all jump -> 7/7, not 7/8: the holed name leaves the denominator too.
        assert f["theme_thrust_frac"] == 1.0
        assert f["theme_thrust_state"] == "thrusting"


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


# =========================================================================== #
# Door W — washout-turn entries, fully aligned (prereg §10)
# =========================================================================== #

class TestDoorWAlignment:
    """door_w_aligned is a PURE recompute from price — no artifact read, definite-True only.

    The pin is CONSISTENCY: on any series, each leg must equal an independent canon
    computation (grid_series + _line_sig, line>sig on the LAST completed bar). Hardcoding a
    True fixture is a trap — clean synthetic ramps annihilate Wilder RSI (zero-loss windows
    go NaN), so expected values are DERIVED, never assumed. aligned=True reachability is
    exercised through the candidates tests and was verified on live data (MCD 2/2) at build.
    """

    @staticmethod
    def _expected_leg(px, grid):
        from engine import stock_events as se
        bars = se.grid_series(px, grid)
        if bars is None or len(bars) < se.MIN_DEPTH_OBS:
            return None
        line, sig = se._line_sig(bars)
        if len(line) == 0:
            return None
        lv, sv = float(line.iloc[-1]), float(sig.iloc[-1])
        if lv != lv or sv != sv:
            return None
        return bool(lv > sv)

    @pytest.mark.parametrize("shape", ["riser", "faller", "zigzag_turn", "choppy"])
    def test_each_leg_matches_the_independent_canon_computation(self, shape):
        idx = pd.bdate_range("2020-01-01", periods=430)
        n = np.arange(len(idx), dtype=float)
        series = {
            "riser":       100.0 + 0.25 * n + 3.0 * np.sin(n / 9.0),
            "faller":      250.0 - 0.25 * n + 3.0 * np.sin(n / 9.0),
            "zigzag_turn": 150.0 - 0.10 * n + 2.0 * np.sin(n / 7.0)
                           + np.cumsum(np.where(n < 360, 0.0,
                                                np.where((n % 5) == 4, -1.5, 2.0))),
            "choppy":      120.0 + 8.0 * np.sin(n / 23.0) + 2.0 * np.sin(n / 5.0),
        }[shape]
        px = pd.Series(series, index=idx)
        out = pdz.door_w_aligned(px)
        exp_2b = self._expected_leg(px, "2B")
        exp_3b = self._expected_leg(px, "3B")
        assert out["align_2b"] is exp_2b and out["align_3b"] is exp_3b
        expected_class = sum(1 for v in (exp_2b, exp_3b) if v is True)
        assert out["align_class"] == expected_class
        assert out["aligned"] is (exp_2b is True and exp_3b is True)

    def test_a_definite_faller_is_not_aligned(self):
        idx = pd.bdate_range("2020-01-01", periods=430)
        n = np.arange(len(idx), dtype=float)
        px = pd.Series(250.0 - 0.25 * n + 3.0 * np.sin(n / 9.0), index=idx)
        out = pdz.door_w_aligned(px)
        assert out["aligned"] is False and out["align_class"] == 0

    def test_unreadable_series_never_counts_as_aligned(self):
        idx = pd.bdate_range("2024-01-01", periods=12)
        px = pd.Series(np.linspace(10, 11, len(idx)), index=idx)
        out = pdz.door_w_aligned(px)
        assert out["align_2b"] is None and out["align_3b"] is None
        assert out["aligned"] is False


class TestDoorWCandidates:
    """The three frozen legs (prereg §10.1) filter exactly as registered."""

    @staticmethod
    def _arm(monkeypatch, receipts_by_sym, aligned_by_sym=None, universe=None):
        import engine.mtf_upturn as _mtu
        import engine.washout_turn as _wt
        uni = universe or {s: ["b1"] for s in receipts_by_sym}
        idx = pd.bdate_range("2020-01-01", periods=300)
        dummy = pd.Series(np.linspace(90, 110, len(idx)), index=idx)
        monkeypatch.setattr(pdz, "washout_universe",
                            lambda droot: (uni, {"ok": True, "universe_n": len(uni)}))
        monkeypatch.setattr(_mtu, "_load_close", lambda sym, root=None: dummy.copy())
        monkeypatch.setattr(_wt, "_deepen_close", lambda sym, close, root=None: close)
        monkeypatch.setattr(_wt, "compute_symbol_washout",
                            lambda close, deep=None, _m=receipts_by_sym, _c=[0]:
                            _pop_receipt(_m, _c))
        al = aligned_by_sym or {}
        monkeypatch.setattr(
            pdz, "door_w_aligned",
            lambda close, _a=al, _c=[0]: _pop_aligned(_a, _c))

    def test_fires_fresh_aligned_turn_and_sorts_deepest_first(self, tmp_path, monkeypatch):
        rec = {"AAA": _w_receipt(depth=9.0), "BBB": _w_receipt(depth=3.0)}
        self._arm(monkeypatch, rec)
        got = pdz.door_w_candidates(tmp_path)
        ticks = [t for _, t, _ in sorted(got["candidates"])]
        assert ticks == ["BBB", "AAA"], "deepest depth_pctile must sort FIRST"
        assert got["disclosure"]["state_turn"] == 2
        assert got["disclosure"]["fresh"] == 2 and got["disclosure"]["aligned"] == 2

    def test_stale_cross_is_filtered_by_the_freshness_leg(self, tmp_path, monkeypatch):
        rec = {"AAA": _w_receipt(weeks=pdz.WASHOUT_FRESH_WEEKS + 1)}
        self._arm(monkeypatch, rec)
        got = pdz.door_w_candidates(tmp_path)
        assert got["candidates"] == []
        assert got["disclosure"]["state_turn"] == 1 and got["disclosure"]["fresh"] == 0

    def test_non_turn_state_is_filtered(self, tmp_path, monkeypatch):
        rec = {"AAA": None}
        self._arm(monkeypatch, rec)
        got = pdz.door_w_candidates(tmp_path)
        assert got["candidates"] == [] and got["disclosure"]["state_turn"] == 0

    def test_misaligned_turn_is_filtered(self, tmp_path, monkeypatch):
        rec = {"AAA": _w_receipt()}
        self._arm(monkeypatch, rec,
                  aligned_by_sym={"AAA": {"align_2b": True, "align_3b": False,
                                          "align_class": 1, "aligned": False}})
        got = pdz.door_w_candidates(tmp_path)
        assert got["candidates"] == []
        assert got["disclosure"]["fresh"] == 1 and got["disclosure"]["aligned"] == 0

    def test_unreadable_depth_sorts_last_never_first(self, tmp_path, monkeypatch):
        rec = {"AAA": _w_receipt(depth=None), "BBB": _w_receipt(depth=8.0)}
        self._arm(monkeypatch, rec)
        got = pdz.door_w_candidates(tmp_path)
        ticks = [t for _, t, _ in sorted(got["candidates"])]
        assert ticks == ["BBB", "AAA"]


def _w_receipt(depth=9.4, weeks=0):
    return {"state": pdz.DOOR_W and "WASHOUT_TURN", "since": "2026-07-31",
            "weeks_since_cross": weeks, "depth_pctile": depth,
            "depth_pctile_at_cross": depth, "weekly_cb": True, "drawdown_pct": -19.7,
            "stoch_k": 44.1, "stoch_d": 40.2, "history_weeks": 3000,
            "history_start": "1968-01-05", "data_through": "2026-07-31"}


def _pop_receipt(mapping, counter):
    syms = sorted(mapping)
    sym = syms[counter[0] % len(syms)]
    counter[0] += 1
    return mapping[sym]


def _pop_aligned(mapping, counter):
    default = {"align_2b": True, "align_3b": True, "align_class": 2, "aligned": True}
    if not mapping:
        return dict(default)
    syms = sorted(mapping)
    sym = syms[counter[0] % len(syms)]
    counter[0] += 1
    return mapping.get(sym, dict(default))


class TestDoorWPrereg:
    """The prereg and the code cannot drift apart silently."""

    def test_prereg_section_10_exists_with_the_frozen_legs(self):
        doc = (REPO / "research" / "PROPHET_DOORS_PREREG.md").read_text(encoding="utf-8")
        assert "§10 Door W" in doc
        assert "§10.1" in doc and "§10.6 Prospective only" in doc
        assert "WASHOUT_FRESH_WEEKS = 2" in doc

    def test_constants_match_the_registration_literals(self):
        # Literals on purpose (a constant read back from the module is a vacuous guard).
        assert pdz.WASHOUT_FRESH_WEEKS == 2
        assert tuple(pdz.WASHOUT_ALIGN_GRIDS) == ("2B", "3B")
        assert pdz.DOOR_W == "W" and pdz.DOOR_W in pdz.DOORS
