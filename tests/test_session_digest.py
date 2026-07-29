"""tests/test_session_digest.py — OIP E1 session digest (engine + builder).

Fixtures are materialized with the REAL surface writer (`scripts.build_flow_surface`'s
`append_stamp` / `frame_for_stamp` / `build_index`), not hand-written dicts.  That is
deliberate: the digest's whole job is reading another builder's output, and a hand-written
fixture would keep passing after the writer's contract moved.  If the writer changes shape,
these tests break — which is the point.

Sections:
  1. session window + early close (DST-safe, exchange-calendar-derived)
  2. unit discipline (the x100 class, fixture AND prod shapes)
  3. arc: column sums, downsampling, shape truth table
  4. event families: truth table (fires / does not fire / hysteresis) per family
  5. clock-label normalization (the `_minute_key` timezone defect)
  6. coverage: promised vs read, gaps, plain words
  7. record + ledger row shape, plain-word twins, no banned vocabulary
  8. builder: end-to-end, degraded modes, lane guard, idempotence, latest-pointer
  9. wiring conformance (daily.yml / dag.yml / synapse.yml presence)

Run: .venv/bin/python -m pytest tests/test_session_digest.py -q
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import session_digest as sd            # noqa: E402
from scripts import build_flow_surface as bfs      # noqa: E402
from scripts import build_session_digest as bsd    # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# fixture helpers — production-shaped by construction
# ═══════════════════════════════════════════════════════════════════════════════

def make_frame(
    *,
    root: str = "SPY",
    session_date: str = "2026-07-28",
    cadence_sec: int = 300,
    n_stamps: int = 79,
    spot_path=None,
    net_path=None,
    strikes=None,
    walls: dict | None = None,
    label_skew_min: int = 0,
) -> tuple[dict, list[str]]:
    """(full-day surface frame, stamp list) built through the real writer.

    `spot_path(i)` and `net_path(i, strike)` are callables so a test can shape exactly the
    price/premium path its truth-table row needs.  `label_skew_min` shifts the emitted labels
    to reproduce the `_minute_key` timezone defect.
    """
    strikes = strikes if strikes is not None else [730.0, 735.0, 740.0]
    open_dt, _ = sd.session_window_et(session_date)
    frame, stamps = None, []
    for i in range(n_stamps):
        t = open_dt + timedelta(seconds=cadence_sec * i)
        mins = (t.hour * 60 + t.minute + label_skew_min) % (24 * 60)
        stamp = f"{mins // 60:02d}{mins % 60:02d}"
        step = f"{mins // 60:02d}:{mins % 60:02d}"
        net = {k: (net_path(i, k) if net_path else 1000.0 * (i + 1)) for k in strikes}
        frame = bfs.append_stamp(
            frame, stamp=stamp, time_step=step, net_by_strike=net,
            spot=(spot_path(i) if spot_path else None),
            asof=t.isoformat(timespec="seconds"), cadence_sec=cadence_sec,
            session_date=session_date, root=root,
            greek_by_strike=({"gex": {k: 1.0 for k in strikes}} if walls else None),
            walls=walls, coverage=(0.8 if walls else None))
        stamps.append(stamp)
    bfs.validate_frame_dims(frame)
    return frame, stamps


def write_archive(base: Path, frame: dict, stamps: list[str], *, root: str,
                  session_date: str, cadence_sec: int = 300,
                  drop_stamps: tuple[str, ...] = ()) -> None:
    """Write the frame out in the exact R2 key layout, via the real per-stamp writer."""
    d = base / "live_flow" / "surface" / root.upper() / session_date
    d.mkdir(parents=True, exist_ok=True)
    for s in stamps:
        if s in drop_stamps:
            continue
        (d / f"{s}.json").write_text(json.dumps(bfs.frame_for_stamp(frame, s)))
    (d / "idx.json").write_text(json.dumps(bfs.build_index(
        frame, session_date=session_date, cadence_sec=cadence_sec, root=root.upper())))
    (d.parent / "dates.json").write_text(json.dumps(bfs.build_dates_index(
        [session_date], root=root.upper(), cadence_sec=cadence_sec, asof=frame["asof"])))


def write_tides(base: Path, *, session_date: str, zero_dte_share_path=None,
                n: int = 79, cadence_sec: int = 300, label_skew_min: int = 0,
                doc_date: str | None = None, asof_date: str | None = None) -> None:
    """Dated tide + dte_tide archives in the payload shape `engine/live_flow` emits."""
    open_dt, _ = sd.session_window_et(session_date)
    mins, buckets = [], {b: [] for b in ("0d", "1_7d", "8_30d", "31_90d", "90p")}
    c_ncp = c_npp = 0.0
    for i in range(n):
        t = open_dt + timedelta(seconds=cadence_sec * i)
        m = (t.hour * 60 + t.minute + label_skew_min) % (24 * 60)
        lbl = f"{m // 60:02d}:{m % 60:02d}"
        c_ncp += 4_000_000
        c_npp += -1_200_000
        mins.append({"t": lbl, "ncp": round(c_ncp), "npp": round(c_npp),
                     "gross": round(abs(c_ncp) + abs(c_npp)), "vol": 1000})
        share = zero_dte_share_path(i) if zero_dte_share_path else 0.20
        others = 10_000_000.0
        zero = others * share / max(1e-9, (1.0 - share))
        buckets["0d"].append({"t": lbl, "ncp": round(zero), "npp": 0})
        for b in ("1_7d", "8_30d", "31_90d", "90p"):
            buckets[b].append({"t": lbl, "ncp": round(others / 4.0), "npp": 0})
    asof = f"{asof_date or session_date}T20:00:00+00:00"
    for fam, doc in (("tide", {"schema": "live_flow.tide/v1", "asof": asof,
                               "session_date": doc_date or session_date,
                               "minutes": mins, "spy": [], "sectors": [],
                               "top_net_impact": [{"root": "SPY",
                                                   "net_prem_soft": 1.0, "gross": 2.0}]}),
                     ("dte_tide", {"schema": "live_flow.dte_tide/v1", "asof": asof,
                                   "buckets": buckets})):
        p = base / "live_flow" / fam
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{session_date}.json").write_text(json.dumps(doc))


def write_gex_state(site: Path, root: str, *, vintage: str, flip: float = 750.43,
                    call_wall: float = 760.0, put_wall: float = 725.0,
                    spot: float = 735.05) -> None:
    p = site / "options_structure" / "gex_state"
    p.mkdir(parents=True, exist_ok=True)
    (p / f"{root.upper()}.json").write_text(json.dumps({
        "schema": "options_structure.gex_state/v1", "asof": f"{vintage}T21:00:00+00:00",
        "root": root.upper(), "spot": spot, "gamma_flip": flip,
        "call_wall": call_wall, "put_wall": put_wall,
        "dist_to_flip_pct": round((spot - flip) / spot * 100, 2), "stability_pct": 15.7,
        "authority_tier": "display"}))


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """An isolated repo root with config-shaped site/ + data/ dirs."""
    (tmp_path / "site").mkdir()
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(bsd.config, "ROOT", tmp_path, raising=False)
    monkeypatch.setattr(bsd.config, "load",
                        lambda: {"storage": {"site_dir": "site", "data_dir": "data"}})
    return tmp_path


# ═══════════════════════════════════════════════════════════════════════════════
# 1. session window
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionWindow:
    def test_window_is_et_wall_clock_on_both_sides_of_dst(self):
        """09:30-16:00 ET holds in July (EDT) and January (EST) alike.

        A UTC-pinned window silently slides an hour at each DST boundary; deriving the window
        by localizing ET clock times onto the date cannot.
        """
        for d in ("2026-01-15", "2026-07-15"):
            o, c = sd.session_window_et(d)
            assert (o.hour, o.minute) == (9, 30), d
            assert (c.hour, c.minute) == (16, 0), d
            assert o.tzinfo is sd.ET
        # ...and the two dates really are different UTC offsets, so the test has teeth.
        assert (sd.session_window_et("2026-01-15")[0].utcoffset()
                != sd.session_window_et("2026-07-15")[0].utcoffset())

    def test_expected_stamps_regular_and_early_close(self):
        assert sd.expected_stamps("2026-07-28", 300) == 79      # 390 min / 5 + 1
        assert sd.expected_stamps("2026-11-27", 300) == 43      # 1pm close: 210/5 + 1
        assert sd.session_window_label("2026-11-27") == "09:30–13:00 ET"

    def test_early_close_recognition(self):
        assert sd.is_early_close(date(2026, 11, 27)) is True    # Friday after Thanksgiving
        assert sd.is_early_close(date(2026, 12, 24)) is True
        assert sd.is_early_close(date(2026, 7, 3)) is True
        assert sd.is_early_close(date(2026, 7, 28)) is False
        assert sd.is_early_close(date(2026, 11, 26)) is False   # Thanksgiving itself

    def test_bad_cadence_yields_no_denominator(self):
        """A cadence of 0 must not become a division-by-zero or a fabricated denominator."""
        assert sd.expected_stamps("2026-07-28", 0) == 0
        assert sd.expected_stamps("2026-07-28", -5) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. unit discipline — the x100 class, against fixture AND prod shapes
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnitDiscipline:
    def test_fraction_to_percent_rejects_percent_input(self):
        assert sd.pct_from_fraction(0.82, field="greek_coverage") == 82.0
        assert sd.pct_from_fraction(None, field="x") is None
        with pytest.raises(sd.UnitError):
            sd.pct_from_fraction(82.0, field="greek_coverage")

    def test_require_pct_rejects_order_of_magnitude_slip(self):
        assert sd.require_pct(61.4, field="share", hard_max=100.0) == 61.4
        with pytest.raises(sd.UnitError):
            sd.require_pct(6140.0, field="share", hard_max=100.0)

    def test_prod_gex_state_units_are_percent_and_coverage_is_fraction(self):
        """Assert the real committed stores, not just fixtures.

        `dist_to_flip_pct`/`stability_pct` in `gex_state` are PERCENTS and the surface frame's
        greek `coverage` is a FRACTION.  This test reads the prod payloads so a producer-side
        unit flip is caught here rather than after it has multiplied a payload by 100.
        """
        p = ROOT / "site" / "options_structure" / "gex_state" / "SPY.json"
        if not p.exists():
            pytest.skip("prod gex_state store absent in this checkout")
        doc = json.loads(p.read_text())
        for k in ("dist_to_flip_pct", "stability_pct"):
            if doc.get(k) is not None:
                assert sd.require_pct(doc[k], field=k) == doc[k]
                with pytest.raises(sd.UnitError):
                    sd.pct_from_fraction(abs(doc[k]) + 1.0, field=k)
        frame, stamps = make_frame(walls={"flip": 1.0, "callWall": 2.0, "putWall": 0.5},
                                   n_stamps=3)
        cov = bfs.frame_for_stamp(frame, stamps[-1]).get("coverage") or {}
        assert 0.0 <= cov["greeks"] <= 1.0
        assert sd.pct_from_fraction(cov["greeks"], field="greeks") == 80.0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. arc
# ═══════════════════════════════════════════════════════════════════════════════

class TestArc:
    def test_column_net_and_gross_sum_the_right_axis(self):
        frame, _ = make_frame(n_stamps=4, strikes=[100.0, 200.0],
                              net_path=lambda i, k: (i + 1) * (1.0 if k == 100.0 else -1.0))
        assert sd.column_net(frame) == [0.0, 0.0, 0.0, 0.0]        # +n and -n cancel
        assert sd.column_gross(frame) == [2.0, 4.0, 6.0, 8.0]      # magnitudes do not

    def test_gross_is_the_pocket_denominator_not_net(self):
        """Two large opposite-signed strikes net to ~0; a net denominator would exceed 100%."""
        frame, _ = make_frame(n_stamps=1, strikes=[100.0, 200.0],
                              net_path=lambda i, k: 1e6 if k == 100.0 else -1e6)
        assert sd.column_net(frame) == [0.0]
        assert sd.column_gross(frame) == [2e6]

    def test_downsample_keeps_both_endpoints(self):
        rows = list(range(500))
        out = sd.downsample(rows, 80)
        assert len(out) <= 82 and out[0] == 0 and out[-1] == 499
        assert out == sorted(out)
        assert sd.downsample(rows, 0) == rows          # disabled cap is a pass-through
        assert sd.downsample([1, 2], 80) == [1, 2]     # under the cap, untouched

    def test_arc_carries_appendix_b_keys_with_nulls_printed(self):
        frame, _ = make_frame(n_stamps=8)
        arc, nets = sd.build_arc(frame)
        assert len(nets) == 8
        for row in arc:
            assert set(row) == {"t", "net", "ncp", "npp"}
            # ncp/npp are PRINTED as null, never omitted: a consumer written against the
            # Appendix-B sketch reads None instead of raising, and the gap stays visible.
            assert row["ncp"] is None and row["npp"] is None
            assert row["net"] is not None

    @pytest.mark.parametrize("tag,net_fn,gross", [
        ("insufficient", lambda i: float(i), None),
        ("flat", lambda i: float(i), 10_000.0),
        ("one_way", lambda i: 1000.0 * i, None),
        ("reversal", lambda i: (1000.0 * i if i < 10 else 1000.0 * (20 - i)), None),
        ("late_build", lambda i: (10.0 * i if i < 14 else 10.0 * 14 + 900.0 * (i - 13)), None),
    ])
    def test_shape_truth_table(self, tag, net_fn, gross):
        n = 4 if tag == "insufficient" else 20
        vals = [net_fn(i) for i in range(n)]
        assert sd.classify_arc(vals, gross).tag == tag

    def test_two_sided_shape(self):
        vals = [0, 100, 200, 300, -300, -200, 400, 500, -400, -100, 300, 350]
        assert sd.classify_arc([float(v) for v in vals]).tag == "two_sided"

    def test_every_shape_tag_has_a_plain_word_twin(self):
        for tag in sd.SHAPE_WORDS:
            en, zh = sd.SHAPE_WORDS[tag]
            assert en and zh and en != zh
            assert not any(ch.isupper() for ch in en.replace("0DTE", ""))  # no enum shouting
        shape = sd.classify_arc([1000.0 * i for i in range(20)])
        assert shape.en in [w[0] for w in sd.SHAPE_WORDS.values()]
        assert shape.receipts["points"] == 20

    def test_shape_flat_test_is_skipped_without_a_denominator(self):
        """No gross → no flat claim.  'Barely moved' is absolute; guessing it is worse than null."""
        vals = [float(i) for i in range(20)]
        assert sd.classify_arc(vals, None).tag != "flat"
        assert "peak_over_gross" not in sd.classify_arc(vals, None).receipts


# ═══════════════════════════════════════════════════════════════════════════════
# 4. event families — truth table per family
# ═══════════════════════════════════════════════════════════════════════════════

TIMES = [f"{9 + (30 + 5 * i) // 60:02d}:{(30 + 5 * i) % 60:02d}" for i in range(80)]


class TestFlipCrossings:
    FLIP = 100.0

    def test_fires_on_a_real_cross(self):
        spots = [99.0] * 5 + [101.0] * 5
        r = sd.flip_crossings(TIMES, spots, self.FLIP)
        assert r.crosses == 1 and r.last_side == "above"
        assert r.events[0]["type"] == "flip_cross"
        assert r.events[0]["level"] == 100.0 and r.events[0]["side"] == "above"

    def test_does_not_fire_when_price_stays_one_side(self):
        r = sd.flip_crossings(TIMES, [101.0] * 10, self.FLIP)
        assert r.crosses == 0 and r.events == []
        # ...and the standing side is still reported, so "no events" cannot be misread as
        # "no level" (the honesty hole ENTER-only semantics would otherwise open).
        assert r.last_side == "above" and r.side_at_open == "above"

    def test_hysteresis_swallows_dead_band_jitter(self):
        """Within band_pct of the flip, the side is held — jitter must not mint crossings."""
        band = sd.FLIP_BAND_PCT / 100.0 * self.FLIP     # 0.05% of 100 = 0.05
        spots = [99.99, 100.01, 99.99, 100.02, 99.98]   # all inside the dead band
        assert max(abs(s - self.FLIP) for s in spots) < band * 2
        r = sd.flip_crossings(TIMES, spots, self.FLIP)
        assert r.crosses == 0
        assert r.last_side == "below", "the armed side must be HELD, not repeatedly re-taken"
        # a clean break clear of the band does fire, from the same jittery start
        assert sd.flip_crossings(TIMES, spots + [101.0], self.FLIP).crosses == 1

    def test_first_observation_arms_and_never_fires(self):
        r = sd.flip_crossings(TIMES, [101.0], self.FLIP)
        assert r.crosses == 0 and r.side_at_open == "above"

    def test_absent_level_or_spots_yields_nothing_not_zero(self):
        assert sd.flip_crossings(TIMES, [101.0, 99.0], None).crosses == 0
        assert sd.flip_crossings(TIMES, [101.0, 99.0], 0.0).last_side is None
        assert sd.flip_crossings(TIMES, [None, None], self.FLIP).last_side is None

    def test_gaps_are_skipped_never_interpolated(self):
        """A None in the middle must not be read as a value, and must not hide a cross."""
        r = sd.flip_crossings(TIMES, [99.0, None, None, 101.0], self.FLIP)
        assert r.crosses == 1
        assert r.events[0]["t"] == TIMES[3]      # stamped where the reading actually is


class TestWallTouches:
    def test_fires_on_enter_only(self):
        # within_pct 0.25% of 100 = 0.25 → inside is [99.75, 100.25]
        spots = [98.0, 98.0, 99.9, 99.9, 98.0, 99.8]
        r = sd.wall_touches(TIMES, spots, call_wall=100.0, put_wall=None)
        assert [e["t"] for e in r.events] == [TIMES[2], TIMES[5]]
        assert all(e["type"] == "call_wall_touch" for e in r.events)

    def test_does_not_fire_when_never_near(self):
        r = sd.wall_touches(TIMES, [90.0] * 10, call_wall=100.0, put_wall=None)
        assert r.events == []
        assert r.closest_pct["call"] == 10.0        # ...but how close it got is recorded

    def test_opening_inside_the_band_arms_and_is_recorded(self):
        r = sd.wall_touches(TIMES, [100.0, 100.0, 100.0], call_wall=100.0, put_wall=None)
        assert r.events == []                       # no fabricated 09:30 touch
        assert r.inside_at_open["call"] is True     # but the standing state is printed

    def test_both_walls_evaluated_independently(self):
        r = sd.wall_touches(TIMES, [95.0, 100.0, 95.0, 90.0],
                            call_wall=100.0, put_wall=90.0)
        assert {e["type"] for e in r.events} == {"call_wall_touch", "put_wall_touch"}

    def test_zero_or_absent_wall_is_ignored(self):
        assert sd.wall_touches(TIMES, [1.0, 2.0], call_wall=0.0, put_wall=None).events == []
        assert sd.wall_touches(TIMES, [1.0, 2.0], call_wall=None, put_wall=None).events == []


class TestPremiumBursts:
    @staticmethod
    def _series(n_quiet=25, n_burst=5, quiet=100.0, burst=5000.0, jitter=7.0):
        vals, cum = [], 0.0
        for i in range(n_quiet):
            cum += quiet + (jitter if i % 2 else -jitter)
            vals.append(cum)
        for i in range(n_burst):
            cum += burst
            vals.append(cum)
        return vals

    def test_fires_on_a_sustained_pace_change(self):
        ev = sd.premium_bursts(TIMES, self._series())
        assert len(ev) == 1
        assert ev[0]["type"] == "premium_burst" and abs(ev[0]["z"]) >= sd.BURST_Z
        assert ev[0]["baseline_stamps"] >= sd.BURST_MIN_BASELINE

    def test_does_not_fire_on_a_steady_tape(self):
        assert sd.premium_bursts(TIMES, self._series(n_quiet=40, n_burst=0)) == []

    def test_flat_tape_is_no_read_not_a_zero_z(self):
        """Zero-variance baseline cannot be z-scored; it must yield no event, not z=0."""
        z, _, _ = sd.window_vs_baseline_z([100.0] * 40, 10)
        assert math.isnan(z)
        assert sd.premium_bursts(TIMES, [100.0] * 40) == []

    def test_hysteresis_books_one_event_per_run(self):
        """A run above threshold books once; it re-arms only after |z| drops back below."""
        vals = self._series(n_quiet=25, n_burst=20)     # a long burst = one run
        assert len(sd.premium_bursts(TIMES, vals)) == 1

        two = self._series(n_quiet=25, n_burst=5)
        base = two[-1]
        for i in range(14):                            # quiet stretch: |z| falls, re-arms
            base += 100.0 + (7.0 if i % 2 else -7.0)
            two.append(base)
        # The second burst must clear a baseline that now CONTAINS the first burst, so an
        # identical repeat is (correctly) no longer unusual — it takes a bigger one to book.
        for _ in range(6):
            base += 40_000.0
            two.append(base)
        assert len(sd.premium_bursts(TIMES, two)) == 2

    def test_a_repeat_of_the_same_burst_is_no_longer_unusual(self):
        """Not a bug: once the day has seen a burst, an identical one is within its baseline.

        Guards against someone 'fixing' this into a per-run absolute threshold, which would
        turn one busy afternoon into a stream of identical events.
        """
        two = self._series(n_quiet=25, n_burst=5)
        base = two[-1]
        for i in range(14):
            base += 100.0 + (7.0 if i % 2 else -7.0)
            two.append(base)
        for _ in range(5):                             # SAME size as the first burst
            base += 5000.0
            two.append(base)
        assert len(sd.premium_bursts(TIMES, two)) == 1

    def test_replay_uses_only_the_tape_realized_so_far(self):
        """Truncating the series after an event must not move or remove that event.

        If the derivation peeked at later stamps, an event's timestamp would depend on data
        that did not exist when it fired — and the record would not be replayable.
        """
        vals = self._series(n_quiet=25, n_burst=5)
        first = sd.premium_bursts(TIMES, vals)[0]
        idx = TIMES.index(first["t"])
        again = sd.premium_bursts(TIMES, vals[: idx + 1])
        assert again and again[-1]["t"] == first["t"] and again[-1]["z"] == first["z"]

    def test_min_baseline_blocks_an_early_false_positive(self):
        """Three quiet opening stamps must not make the fourth a 40-sigma event."""
        assert sd.premium_bursts(TIMES, [0.0, 1.0, 2.0, 3.0, 500.0]) == []

    def test_self_inclusive_baseline_would_have_been_structurally_dead(self):
        """Documents WHY the two-sample divergence exists (see window_vs_baseline_z).

        The ported TS formula scores the window against a distribution containing it, capping
        z at sqrt((n-w)/w) — under 2 until n >= 50 increments, i.e. no burst bookable before
        mid-afternoon at 5-minute cadence, however violent the tape.
        """
        vals = self._series(n_quiet=15, n_burst=5)      # 20 increments
        st = sd.slope_stats(vals, 10)                   # faithful TS port
        assert abs(st.z) < sd.BURST_Z                   # cannot fire, by construction
        assert abs(st.z) <= math.sqrt((st.n - 10) / 10) + 1e-9
        # the two-sample framing does fire on the same tape
        z, _, _ = sd.window_vs_baseline_z(self._series(n_quiet=25, n_burst=5), 10)
        assert abs(z) >= sd.BURST_Z

    def test_slope_stats_matches_the_ts_population_sigma_convention(self):
        st = sd.slope_stats([0.0, 1.0, 2.0, 10.0], 2)
        deltas = [1.0, 1.0, 8.0]
        mean = sum(deltas) / 3
        var = sum((d - mean) ** 2 for d in deltas) / 3      # population, not sample
        assert st.mean == pytest.approx(mean)
        assert st.std == pytest.approx(math.sqrt(var))
        assert st.n == 3


# 21 strikes so that a UNIFORM distribution puts only 3/21 = 14.3% in any 3-strike band —
# comfortably under POCKET_SHARE_PCT.  With ten strikes a flat grid already reads 30%, which
# is within a whisker of the threshold and makes "spread" untestable.
STRIKES21 = [700.0 + 5 * k for k in range(21)]
PEAK_BAND = (745.0, 750.0, 755.0)      # the centre 3-strike band the pocket search will find


def pocket_frame(shares, *, scale=1e7, n=None):
    """A frame whose peak-band share follows `shares(i)` (0..1) at every stamp."""
    n = n if n is not None else 8
    others = len(STRIKES21) - len(PEAK_BAND)

    def net(i, k):
        s = shares(i)
        return (scale * s / len(PEAK_BAND) if k in PEAK_BAND
                else scale * (1.0 - s) / others)

    return make_frame(n_stamps=n, strikes=STRIKES21, net_path=net)[0]


def test_pocket_fixture_is_honest_about_its_own_baseline():
    """The fixture's 'spread' state must really be under the threshold, or the family's
    negative tests would pass for the wrong reason."""
    r = sd.hot_pockets(pocket_frame(lambda i: 0.15))
    assert r.share_at_open < sd.POCKET_SHARE_PCT, r.share_at_open


class TestHotPockets:
    def test_fires_when_premium_concentrates(self):
        """Spread first, then bunched: the ENTER is what gets stamped."""
        r = sd.hot_pockets(pocket_frame(lambda i: 0.15 if i < 4 else 0.80))
        assert len(r.events) == 1 and r.events[0]["type"] == "hot_pocket"
        assert r.events[0]["share"] >= sd.POCKET_SHARE_PCT
        assert r.events[0]["level"] == 750.0     # the centre of PEAK_BAND
        assert r.events[0]["band_strikes"] == 2 * sd.POCKET_BAND_STRIKES + 1
        assert r.peak_share >= sd.POCKET_SHARE_PCT and r.peak_level == 750.0

    def test_does_not_fire_when_premium_is_spread(self):
        r = sd.hot_pockets(pocket_frame(lambda i: 0.15))
        assert r.events == []
        assert r.peak_share is not None       # ...but the peak is still on the record

    def test_already_concentrated_at_the_open_records_a_level_not_an_event(self):
        r = sd.hot_pockets(pocket_frame(lambda i: 0.80))
        assert r.events == []                 # no moment of entry exists to stamp
        assert r.share_at_open >= sd.POCKET_SHARE_PCT
        assert r.peak_share >= sd.POCKET_SHARE_PCT

    def test_hysteresis_books_one_event_while_the_share_sits_on_the_line(self):
        """A share jittering across the threshold booked 5 events before the re-arm margin."""
        thresh = sd.POCKET_SHARE_PCT / 100.0

        def shares(i):
            if i < 3:
                return 0.15                                   # start clear of the line
            return thresh + (0.005 if i % 2 else -0.002)       # then straddle it

        frame = pocket_frame(shares, n=20)
        assert len(sd.hot_pockets(frame).events) == 1
        # with the margin removed the same tape chatters — which is what the margin is for
        assert len(sd.hot_pockets(frame, rearm_pct=0.0).events) > 1

    def test_re_arms_after_the_share_drops_clear(self):
        def shares(i):
            return {0: 0.15, 1: 0.15, 2: 0.80, 3: 0.80, 4: 0.10, 5: 0.10, 6: 0.80}.get(i, 0.1)
        r = sd.hot_pockets(pocket_frame(shares, n=7))
        assert len(r.events) == 2

    def test_thin_column_cannot_book_a_pocket(self):
        """One contract at the open is trivially 100% of its column; that is not a finding."""
        thin = pocket_frame(lambda i: 0.15 if i < 4 else 0.80, scale=1_000.0)
        assert sd.hot_pockets(thin).events == []
        assert sd.hot_pockets(thin, min_total=0.0).events != []

    def test_empty_frame_is_safe(self):
        for bad in ({}, {"price_levels": [], "grids": {}}):
            r = sd.hot_pockets(bad)
            assert r.events == [] and r.peak_share is None


class TestZeroDte:
    def _doc(self, tmp_path, share_fn, **kw):
        write_tides(tmp_path, session_date="2026-07-28", zero_dte_share_path=share_fn, **kw)
        return json.loads((tmp_path / "live_flow" / "dte_tide" / "2026-07-28.json").read_text())

    def test_fires_when_the_share_crosses_up(self, tmp_path):
        doc = self._doc(tmp_path, lambda i: 0.20 if i < 10 else 0.70)
        block, ev = sd.zero_dte_read(doc, session_date="2026-07-28")
        assert len(ev) == 1 and ev[0]["type"] == "zero_dte_spike"
        assert block["peak_share"] >= sd.ZERO_DTE_SHARE_PCT
        assert block["scope"] == "market"          # never presented as per-root

    def test_does_not_fire_below_threshold(self, tmp_path):
        block, ev = sd.zero_dte_read(self._doc(tmp_path, lambda i: 0.20),
                                     session_date="2026-07-28")
        assert ev == [] and block["peak_share"] == pytest.approx(20.0, abs=0.2)

    def test_already_above_at_the_first_stamp_records_a_level_not_an_event(self, tmp_path):
        block, ev = sd.zero_dte_read(self._doc(tmp_path, lambda i: 0.80),
                                     session_date="2026-07-28")
        assert ev == []                             # nothing entered; nothing invented
        assert block["share_at_open"] >= sd.ZERO_DTE_SHARE_PCT
        assert block["peak_share"] >= sd.ZERO_DTE_SHARE_PCT

    def test_other_session_archive_is_refused_in_plain_words(self, tmp_path):
        """Mixed-asof guard: an archive stamped for another session is not this session's."""
        doc = self._doc(tmp_path, lambda i: 0.80, asof_date="2026-07-27")
        block, ev = sd.zero_dte_read(doc, session_date="2026-07-28")
        assert block["peak_share"] is None and ev == []
        assert "another session" in block["note_en"] and block["note_zh"]

    def test_absent_or_malformed_archive_degrades_to_plain_words(self):
        for bad in (None, {}, {"buckets": None}, {"buckets": {"1_7d": []}}):
            block, ev = sd.zero_dte_read(bad, session_date="2026-07-28")
            assert block["peak_share"] is None and ev == []
            assert block["note_en"] and block["note_zh"]

    def test_share_uses_one_stamp_across_buckets(self, tmp_path):
        """A ratio built from two different clock readings is a fabricated ratio."""
        doc = self._doc(tmp_path, lambda i: 0.20 if i < 10 else 0.70)
        doc["buckets"]["1_7d"] = doc["buckets"]["1_7d"][:5]     # truncate one bucket
        block, _ = sd.zero_dte_read(doc, session_date="2026-07-28")
        # only the 5 stamps common to EVERY bucket may be used, so the late 70% is invisible
        assert block["peak_share"] == pytest.approx(20.0, abs=0.2)

    def test_every_event_type_has_a_plain_word_twin(self):
        for etype, (en, zh) in sd.EVENT_WORDS.items():
            assert en and zh and en != zh
            assert etype not in en and etype not in zh     # the key never leaks into the copy


# ═══════════════════════════════════════════════════════════════════════════════
# 5. clock-label normalization
# ═══════════════════════════════════════════════════════════════════════════════

class TestClockNormalization:
    """`engine/live_flow._minute_key` localizes naive ET timestamps as UTC, so tide/dte
    labels run a whole timezone offset early.  The correction must fix that, preserve a
    genuinely late start, and disarm itself once the producer is repaired."""

    D = "2026-07-28"

    @pytest.mark.parametrize("first,last,expect,why", [
        ("0930", "1600", 0, "already exchange time — no-op (and post-fix behaviour)"),
        ("0530", "1159", 240, "the _minute_key defect, summer offset"),
        ("0430", "1059", 300, "the same defect at the winter offset"),
        ("0535", "1204", 240, "defect plus a 5-minute late start — start preserved"),
        ("1030", "1600", 0, "genuinely late poller start — must NOT be shifted"),
        ("0530", "1500", 0, "correcting would overshoot the close — leave labels alone"),
    ])
    def test_offset_truth_table(self, first, last, expect, why):
        assert sd.clock_offset_minutes(self.D, first, last_label=last,
                                       cadence_sec=300) == expect, why

    def test_shift_label_round_trips_and_tolerates_junk(self):
        assert sd.shift_label("0530", 240) == "09:30"
        assert sd.shift_label("05:35", 240) == "09:35"
        assert sd.shift_label("0930", 0) == "09:30"
        assert sd.shift_label("nonsense", 240) == "nonsense"
        assert sd.shift_label(None, 240) == ""

    def test_skewed_archive_yields_the_same_event_times_as_a_clean_one(self):
        """The pinning test: a fixture with skewed labels must produce correct event times."""
        def spots(i):
            return 99.0 if i < 20 else 101.0

        clean, c_stamps = make_frame(n_stamps=40, spot_path=spots)
        skew, s_stamps = make_frame(n_stamps=40, spot_path=spots, label_skew_min=-240)
        assert s_stamps[0] == "0530" and c_stamps[0] == "0930"      # fixture really is skewed

        def rec(frame, stamps):
            return sd.build_session_record(
                root="SPY", session_date=self.D, asof="t", frame=frame, stamps=stamps,
                cadence_sec=300,
                spots_by_stamp={s: spots(i) for i, s in enumerate(stamps)},
                levels={"flip": 100.0, "vintage": self.D, "source": "x"})

        a, b = rec(clean, c_stamps), rec(skew, s_stamps)
        assert [e["t"] for e in a["events"]] == [e["t"] for e in b["events"]]
        assert a["arc"][0]["t"] == b["arc"][0]["t"] == "09:30"
        assert b["coverage"]["clock_offset_min"] == 240
        assert a["coverage"]["clock_offset_min"] == 0
        assert b["coverage"]["clock_note_en"] and b["coverage"]["clock_note_zh"]
        assert "clock_note_en" not in a["coverage"]


# ═══════════════════════════════════════════════════════════════════════════════
# 6. coverage
# ═══════════════════════════════════════════════════════════════════════════════

class TestCoverage:
    D = "2026-07-28"

    def test_full_session_reads_as_complete(self):
        _, stamps = make_frame(n_stamps=79)
        cov = sd.coverage_block(session_date=self.D, cadence_sec=300, stamps=stamps)
        assert cov["minutes"] == cov["expected"] == 79
        assert cov["gaps"] == 0 and cov["absent_objects"] == 0
        assert "whole session" in cov["quality_en"] and cov["quality_zh"]

    def test_partial_day_says_so(self):
        _, stamps = make_frame(n_stamps=20)
        cov = sd.coverage_block(session_date=self.D, cadence_sec=300, stamps=stamps)
        assert cov["minutes"] == 20 and cov["expected"] == 79
        assert "only part" in cov["quality_en"]

    def test_interior_hole_counts_as_a_gap_not_a_short_day(self):
        _, stamps = make_frame(n_stamps=79)
        holed = stamps[:30] + stamps[35:]
        cov = sd.coverage_block(session_date=self.D, cadence_sec=300, stamps=holed)
        assert cov["gaps"] == 5
        # ...whereas a session that merely stopped early has no interior gap
        early = sd.coverage_block(session_date=self.D, cadence_sec=300, stamps=stamps[:40])
        assert early["gaps"] == 0 and early["minutes"] == 40

    def test_promised_but_unreadable_objects_are_not_counted_as_covered(self):
        """The dated indexes are best-effort: a listed stamp whose PUT failed is a hole."""
        _, stamps = make_frame(n_stamps=79)
        read = stamps[:30] + stamps[32:]
        cov = sd.coverage_block(session_date=self.D, cadence_sec=300, stamps=stamps,
                                read_stamps=read)
        assert cov["promised"] == 79 and cov["minutes"] == 77
        assert cov["absent_objects"] == 2 and cov["gaps"] == 2
        assert cov["absent_note_en"] and cov["absent_note_zh"]

    def test_no_record_says_so_in_plain_words(self):
        cov = sd.coverage_block(session_date=self.D, cadence_sec=300, stamps=[])
        assert cov["minutes"] == 0 and cov["first"] is None
        assert "no intraday record" in cov["quality_en"] and cov["quality_zh"]

    def test_missing_inputs_are_listed_bilingually(self):
        cov = sd.coverage_block(session_date=self.D, cadence_sec=300, stamps=["0930"],
                                missing_en=["a thing"], missing_zh=["某项"])
        assert cov["missing_en"] == ["a thing"] and cov["missing_zh"] == ["某项"]


# ═══════════════════════════════════════════════════════════════════════════════
# 7. record + ledger row
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecord:
    D = "2026-07-28"

    def _record(self, **kw):
        frame, stamps = make_frame(n_stamps=40, spot_path=lambda i: 99.0 if i < 20 else 101.0)
        base = dict(root="SPY", session_date=self.D, asof="2026-07-29T01:00:00+00:00",
                    frame=frame, stamps=stamps, cadence_sec=300,
                    spots_by_stamp={s: (99.0 if i < 20 else 101.0)
                                    for i, s in enumerate(stamps)},
                    levels={"flip": 100.0, "call_wall": 101.0, "put_wall": 98.0,
                            "spot": 100.5, "vintage": self.D, "source": "gex_state"})
        base.update(kw)
        return sd.build_session_record(**base)

    def test_appendix_b_contract_keys_present(self):
        r = self._record()
        for k in ("root", "session_date", "arc", "events", "zero_dte", "walls", "flip",
                  "coverage", "asof", "schema"):
            assert k in r, k
        assert r["schema"] == "options_session.v1"
        assert set(r["walls"]) >= {"open", "close", "migrated"}
        assert set(r["flip"]) >= {"crosses", "last_side"}
        assert set(r["zero_dte"]) >= {"peak_share", "at"}
        assert set(r["coverage"]) >= {"minutes", "expected", "gaps"}

    def test_every_machine_key_travels_with_a_plain_word_twin(self):
        r = self._record()
        assert r["arc_shape_en"] and r["arc_shape_zh"]
        for e in r["events"]:
            assert e["label_en"] and e["label_zh"]
        for block in (r["walls"], r["flip"], r["levels"], r["coverage"], r["reliability"]):
            keys = set(block)
            assert any(k.endswith(("_en", "note_en", "quality_en", "basis_en")) for k in keys)
            assert any(k.endswith(("_zh", "note_zh", "quality_zh", "basis_zh")) for k in keys)

    def test_no_banned_vocabulary_in_any_user_facing_string(self):
        """A payload string is copy the moment a surface prints it.

        `validated` is CI-guarded house-wide; the rest are the doctrine's Tier-1 bans and this
        estate's internal slugs.  Machine keys (`type`, `arc_shape`, enum values) are exempt —
        they exist so a surface can look up the twin, and are asserted separately.
        """
        r = self._record()
        banned = ("validated", "n=", "FlowZ", "TSBrd", "NotTrap", "pain_dist", "wilson_",
                  "falsifier", "refuted", "证伪", "z-score", "p-value", "COLLECT_LANE")
        machine_keys = {"type", "arc_shape", "schema", "side", "last_side", "side_at_open",
                        "scope", "authority_tier", "source", "arc_method"}

        def walk(node, path=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    if k in machine_keys:
                        continue
                    walk(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")
            elif isinstance(node, str):
                low = node.lower()
                for b in banned:
                    assert b.lower() not in low, f"banned {b!r} in {path}: {node!r}"

        walk({k: v for k, v in r.items() if k != "inputs"})

    def test_no_direction_or_return_claim_language(self):
        r = self._record()
        blob = json.dumps(r, ensure_ascii=False).lower()
        for phrase in ("bullish", "bearish", "will rise", "will fall", "expect price",
                       "outperform", "target price", "buy ", "sell "):
            assert phrase not in blob, phrase

    def test_reference_levels_print_their_vintage(self):
        r = self._record()
        assert r["levels"]["vintage"] == self.D
        assert r["levels"]["basis_en"] and r["levels"]["basis_zh"]
        assert "closing map" in r["flip"]["note_en"]
        # a level map from another date must say which date, not pass as this session's
        other = self._record(levels={"flip": 100.0, "call_wall": 101.0, "put_wall": 98.0,
                                     "vintage": "2026-07-27", "source": "gex_state"})
        assert "2026-07-27" in other["flip"]["note_en"]
        assert other["walls"]["close"]["call"] is None      # not this session's close

    def test_greek_coverage_is_converted_at_the_ingestion_seam(self):
        """The archive's greek `coverage` is a FRACTION; the payload prints a PERCENT.

        The conversion goes through pct_from_fraction so a producer-side unit flip raises here
        instead of silently multiplying the number by 100 (the class that shipped twice).
        """
        frame, stamps = make_frame(n_stamps=6,
                                   walls={"flip": 100.0, "callWall": 101.0, "putWall": 98.0})
        per_stamp = bfs.frame_for_stamp(frame, stamps[-1])
        r = self._record(frame=per_stamp, stamps=stamps)
        assert r["walls"]["greek_coverage_pct"] == 80.0        # fixture writes 0.8
        # ...and a frame with no greek grids prints a null, not a zero
        plain, plain_stamps = make_frame(n_stamps=6)
        assert self._record(frame=bfs.frame_for_stamp(plain, plain_stamps[-1]),
                            stamps=plain_stamps)["walls"]["greek_coverage_pct"] is None

    def test_tide_from_another_session_is_disclosed_not_dropped(self):
        """A document that exists but belongs to another session is absent for this record."""
        r = self._record(tide_doc={"schema": "live_flow.tide/v1",
                                   "session_date": "2026-07-27",
                                   "minutes": [{"t": "16:00", "ncp": 1.0, "npp": 2.0}]})
        assert r["market"] is None
        assert any("market-wide" in m for m in r["coverage"]["missing_en"])
        assert len(r["coverage"]["missing_zh"]) == len(r["coverage"]["missing_en"])

    def test_wall_migration_is_null_not_false_when_unknowable(self):
        r = self._record(levels=None)
        assert r["walls"]["migrated"] is None
        assert "not enough of the record" in r["walls"]["note_en"]
        assert r["walls"]["note_zh"]

    def test_wall_migration_detected_from_intraday_archive(self):
        r = self._record(open_frame_walls={"callWall": 100.0, "putWall": 90.0},
                         close_frame_walls={"callWall": 105.0, "putWall": 90.0})
        assert r["walls"]["migrated"] is True
        assert r["walls"]["open"]["source"] == "intraday archive"
        same = self._record(open_frame_walls={"callWall": 100.0, "putWall": 90.0},
                            close_frame_walls={"callWall": 100.0, "putWall": 90.0})
        assert same["walls"]["migrated"] is False

    def test_empty_frame_produces_an_honest_record_not_a_crash(self):
        r = sd.build_session_record(root="SPY", session_date=self.D, asof="t", frame=None,
                                    stamps=[], cadence_sec=300)
        assert r["arc"] == [] and r["net_close"] is None
        assert r["arc_shape"] == "insufficient"
        assert r["coverage"]["minutes"] == 0
        assert r["events"] == [] and r["walls"]["migrated"] is None
        assert r["coverage"]["missing_en"]

    def test_absent_spot_path_is_disclosed(self):
        r = self._record(spots_by_stamp={})
        assert any("price path" in m for m in r["coverage"]["missing_en"])
        assert r["coverage"]["missing_zh"]
        assert r["flip"]["crosses"] == 0

    def test_determinism_same_inputs_same_record(self):
        a, b = self._record(), self._record()
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_arc_is_downsampled_to_the_cap(self):
        frame, stamps = make_frame(n_stamps=79)
        r = sd.build_session_record(root="SPY", session_date=self.D, asof="t", frame=frame,
                                    stamps=stamps, cadence_sec=300, arc_max_points=20)
        assert len(r["arc"]) <= 22 and r["arc_points_full"] == 79
        assert r["arc"][0]["t"] == "09:30" and r["arc"][-1]["t"] == "16:00"
        # the last arc point must agree with the record's own close
        assert r["arc"][-1]["net"] == r["net_close"]


class TestLedgerRow:
    def test_row_has_the_pinned_columns_and_agrees_with_the_record(self):
        frame, stamps = make_frame(n_stamps=40, spot_path=lambda i: 99.0 if i < 20 else 101.0)
        r = sd.build_session_record(
            root="SPY", session_date="2026-07-28", asof="t", frame=frame, stamps=stamps,
            cadence_sec=300,
            spots_by_stamp={s: (99.0 if i < 20 else 101.0) for i, s in enumerate(stamps)},
            levels={"flip": 100.0, "vintage": "2026-07-28", "source": "g"})
        row = sd.ledger_row(r)
        assert set(row) == set(sd.LEDGER_COLUMNS)
        assert row["date"] == "2026-07-28" and row["root"] == "SPY"
        assert row["events_total"] == len(r["events"])
        assert row["flip_crosses"] == r["flip"]["crosses"] == 1
        assert row["coverage_minutes"] == r["coverage"]["minutes"]
        assert row["arc_shape"] == r["arc_shape"]

    def test_counts_never_disagree_with_the_event_list(self):
        r = sd.build_session_record(root="SPY", session_date="2026-07-28", asof="t",
                                    frame=None, stamps=[], cadence_sec=300)
        row = sd.ledger_row(r)
        fam = [c for c in sd.LEDGER_COLUMNS if c.startswith("events_") and c != "events_total"]
        assert row["events_total"] == sum(row[c] for c in fam) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 8. builder — end to end, degraded modes, lane guard
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuilderEndToEnd:
    D = "2026-07-28"

    def _archive(self, tmp_path, *, n=40, roots=("SPY",), drop=(), walls=None):
        arch = tmp_path / "arch"
        for r in roots:
            frame, stamps = make_frame(root=r, n_stamps=n, session_date=self.D,
                                        spot_path=lambda i: 99.0 if i < n // 2 else 101.0,
                                        walls=walls)
            write_archive(arch, frame, stamps, root=r, session_date=self.D,
                          drop_stamps=drop)
        write_tides(arch, session_date=self.D,
                    zero_dte_share_path=lambda i: 0.2 if i < 10 else 0.7)
        return arch

    def test_happy_path_writes_records_ledger_and_latest(self, repo, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        write_gex_state(repo / "site", "SPY", vintage=self.D, flip=100.0,
                        call_wall=101.0, put_wall=98.0)
        res = bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        assert res["ok"] and res["roots"] == ["SPY"] and res["ledger_rows"] == 1
        rec = json.loads((repo / "data" / "options_session" / self.D / "SPY.json").read_text())
        assert rec["schema"] == "options_session.v1" and rec["flip"]["crosses"] == 1
        latest = json.loads((repo / "site" / "session" / "SPY.json").read_text())
        assert latest["session_date"] == self.D
        import pandas as pd
        lg = pd.read_parquet(repo / "data" / "options_session" / "ledger.parquet")
        assert list(lg.columns) == sd.LEDGER_COLUMNS and len(lg) == 1

    def test_lane_guard_off_lane_writes_zero_data(self, repo, monkeypatch):
        """House law: nightly is the sole writer of `data/`.  Off-lane refreshes only `site/`."""
        monkeypatch.delenv("COLLECT_LANE", raising=False)
        monkeypatch.delenv("US_LANE", raising=False)
        arch = self._archive(repo)
        res = bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        assert res["roots"] == ["SPY"]
        assert res["ledger_rows"] == -1
        assert not (repo / "data" / "options_session").exists()
        assert (repo / "site" / "session" / "SPY.json").exists()

    def test_ledger_is_idempotent_and_keeps_the_first_row(self, repo, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        import pandas as pd
        p = repo / "data" / "options_session" / "ledger.parquet"
        first = pd.read_parquet(p).iloc[0].to_dict()
        bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        after = pd.read_parquet(p)
        assert len(after) == 1
        assert after.iloc[0]["asof"] == first["asof"]     # the graded row was NOT rewritten

    def test_latest_pointer_never_regresses(self, repo, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        newer = "2026-07-29"
        frame, stamps = make_frame(root="SPY", n_stamps=20, session_date=newer)
        write_archive(arch, frame, stamps, root="SPY", session_date=newer)
        # dates.json now lists only the newer session; write both so discovery sees each
        (arch / "live_flow" / "surface" / "SPY" / "dates.json").write_text(json.dumps(
            bfs.build_dates_index([self.D, newer], root="SPY", cadence_sec=300,
                                  asof=frame["asof"])))
        bsd.run(session_date=newer, roots=["SPY"], from_dir=arch, root_dir=repo)
        assert json.loads((repo / "site" / "session" / "SPY.json").read_text())[
            "session_date"] == newer
        res = bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        assert json.loads((repo / "site" / "session" / "SPY.json").read_text())[
            "session_date"] == newer, "replaying an older date must not roll `latest` back"
        assert "SPY" not in res["written"]
        # ...but the older session's own dated record IS written, and the ledger gains it
        assert (repo / "data" / "options_session" / self.D / "SPY.json").exists()
        import pandas as pd
        assert len(pd.read_parquet(repo / "data" / "options_session" / "ledger.parquet")) == 2

    def test_non_session_date_is_refused(self, repo, monkeypatch, capsys):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        res = bsd.run(session_date="2026-07-26", from_dir=repo / "arch", root_dir=repo)
        assert res["reason"] == "not_a_session" and res["roots"] == []
        line = [l for l in capsys.readouterr().out.splitlines() if "::warning" in l]
        assert line and line[0].startswith("::warning")

    def test_absent_archive_source_degrades_without_a_traceback(self, repo, monkeypatch,
                                                                capsys):
        for var in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
            monkeypatch.delenv(var, raising=False)
        res = bsd.run(session_date=self.D, root_dir=repo)
        assert res["ok"] and res["reason"] == "no_archive_source"
        assert any(l.startswith("::warning") for l in capsys.readouterr().out.splitlines())

    def test_missing_date_in_the_archive_writes_nothing(self, repo, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        res = bsd.run(session_date="2026-07-27", roots=["SPY"], from_dir=arch, root_dir=repo)
        assert res["roots"] == [] and res["reason"] == "no_archived_roots"
        assert not (repo / "data" / "options_session" / "2026-07-27").exists()

    def test_absent_tide_archives_degrade_honestly(self, repo, monkeypatch, capsys):
        """The dated tide/dte families do not exist yet — the record must say so, not guess."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        for fam in ("tide", "dte_tide"):
            (arch / "live_flow" / fam / f"{self.D}.json").unlink()
        bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        rec = json.loads((repo / "data" / "options_session" / self.D / "SPY.json").read_text())
        assert rec["zero_dte"]["peak_share"] is None and rec["market"] is None
        assert rec["zero_dte"]["note_en"] and rec["zero_dte"]["note_zh"]
        joined = " ".join(rec["coverage"]["missing_en"])
        assert "same-day-expiry" in joined and "market-wide" in joined
        assert len(rec["coverage"]["missing_zh"]) == len(rec["coverage"]["missing_en"])
        assert any(l.startswith("::warning") for l in capsys.readouterr().out.splitlines())

    def test_partial_day_and_absent_objects_are_reported(self, repo, monkeypatch, capsys):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        _, all_stamps = make_frame(n_stamps=40, session_date=self.D)
        arch = self._archive(repo, n=40, drop=(all_stamps[10], all_stamps[11]))
        bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        rec = json.loads((repo / "data" / "options_session" / self.D / "SPY.json").read_text())
        cov = rec["coverage"]
        assert cov["promised"] == 40 and cov["minutes"] == 38 and cov["absent_objects"] == 2
        assert cov["absent_note_en"] and cov["absent_note_zh"]
        assert "only part" in cov["quality_en"]     # 38 of an expected 79
        out = capsys.readouterr().out
        assert any("could not be read back" in l and l.startswith("::warning")
                   for l in out.splitlines())

    def test_promised_session_with_no_index_is_annotated(self, repo, monkeypatch, capsys):
        """dates.json is best-effort: a listed session whose index PUT failed must be named."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        (arch / "live_flow" / "surface" / "SPY" / self.D / "idx.json").unlink()
        res = bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        assert res["roots"] == []
        assert any("promises this session" in l and l.startswith("::warning")
                   for l in capsys.readouterr().out.splitlines())

    def test_dry_run_writes_nothing(self, repo, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        res = bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo,
                      dry_run=True)
        assert res["roots"] == ["SPY"] and res["written"] == []
        assert not (repo / "data" / "options_session").exists()
        assert not (repo / "site" / "session").exists()

    def test_no_spot_scan_mode_costs_four_gets_and_says_what_is_missing(self, repo,
                                                                        monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo, n=40)
        res = bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo,
                      scan_spots=False)
        rec = json.loads((repo / "data" / "options_session" / self.D / "SPY.json").read_text())
        assert rec["flip"]["crosses"] == 0
        assert any("price path" in m for m in rec["coverage"]["missing_en"])
        assert res["r2_gets"] <= 10, res["r2_gets"]        # dates+idx+tide+dte+4 frames

    def test_prior_session_close_walls_become_this_session_open_walls(self, repo,
                                                                      monkeypatch):
        """Self-bootstrapping wall migration while the greek tap is dark."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        write_gex_state(repo / "site", "SPY", vintage=self.D, call_wall=101.0, put_wall=98.0)
        bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        nxt = "2026-07-29"
        frame, stamps = make_frame(root="SPY", n_stamps=20, session_date=nxt)
        write_archive(arch, frame, stamps, root="SPY", session_date=nxt)
        write_gex_state(repo / "site", "SPY", vintage=nxt, call_wall=104.0, put_wall=97.0)
        bsd.run(session_date=nxt, roots=["SPY"], from_dir=arch, root_dir=repo)
        rec = json.loads((repo / "data" / "options_session" / nxt / "SPY.json").read_text())
        assert rec["walls"]["open"] == {"call": 101.0, "put": 98.0,
                                        "source": f"prior session record ({self.D})"}
        assert rec["walls"]["close"]["call"] == 104.0
        assert rec["walls"]["migrated"] is True

    def test_prior_wall_lookup_session_filters_the_ledger(self, repo):
        """#3721 class: never take `.iloc[-1]` off a dated store without a session filter."""
        import pandas as pd
        p = repo / "data" / "options_session"
        p.mkdir(parents=True, exist_ok=True)
        rows = [
            {c: None for c in sd.LEDGER_COLUMNS} | {
                "date": "2026-07-24", "root": "SPY",       # Friday: a real session
                "wall_call_close": 111.0, "wall_put_close": 99.0},
            {c: None for c in sd.LEDGER_COLUMNS} | {
                "date": "2026-07-26", "root": "SPY",       # Sunday: must be ignored
                "wall_call_close": 222.0, "wall_put_close": 88.0},
        ]
        pd.DataFrame(rows, columns=sd.LEDGER_COLUMNS).to_parquet(p / "ledger.parquet")
        walls, src = bsd.prior_close_walls(repo / "data", "SPY", "2026-07-28")
        assert walls == {"call": 111.0, "put": 99.0}, "a weekend row must never be picked"
        assert "2026-07-24" in src

    def test_multiple_roots_and_one_bad_root_never_costs_the_others(self, repo, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo, roots=("SPY", "QQQ"))
        bad = arch / "live_flow" / "surface" / "QQQ" / self.D / "idx.json"
        bad.write_text("{ not json")
        res = bsd.run(session_date=self.D, roots=["SPY", "QQQ"], from_dir=arch, root_dir=repo)
        assert res["roots"] == ["SPY"]

    def test_index_reporting_another_session_is_refused(self, repo, monkeypatch, capsys):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        p = arch / "live_flow" / "surface" / "SPY" / self.D / "idx.json"
        doc = json.loads(p.read_text())
        doc["date"] = "2026-07-27"
        p.write_text(json.dumps(doc))
        res = bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        assert res["roots"] == []
        assert any("wrong date" in l for l in capsys.readouterr().out.splitlines())

    def test_selftest_and_cli_exit_zero(self, capsys):
        assert bsd.main(["--selftest"]) == 0
        assert "selftest OK" in capsys.readouterr().out

    def test_builder_never_raises_on_a_broken_archive(self, repo, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = repo / "arch"
        (arch / "live_flow" / "surface" / "SPY" / self.D).mkdir(parents=True)
        (arch / "live_flow" / "surface" / "SPY" / self.D / "idx.json").write_text(
            json.dumps({"date": self.D, "stamps": ["0930", "0935"], "latest": "0935",
                        "cadenceSec": 300}))
        res = bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        assert res["ok"]
        rec = json.loads((repo / "data" / "options_session" / self.D / "SPY.json").read_text())
        assert rec["arc"] == [] and rec["coverage"]["absent_objects"] == 2

    def test_default_session_date_is_calendar_derived(self):
        d = date.fromisoformat(bsd.default_session_date())
        from lib import nyse_calendar
        assert nyse_calendar.is_session(d)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. wiring conformance (§0.14)
# ═══════════════════════════════════════════════════════════════════════════════

class TestWiringConformance:
    """A builder nobody calls produces nothing.  Plain text-presence assertions."""

    DAILY = ROOT / ".github" / "workflows" / "daily.yml"
    DAG = ROOT / "config" / "dag.yml"
    SYNAPSE = ROOT / "config" / "synapse.yml"

    def test_wired_in_daily_yml(self):
        text = self.DAILY.read_text()
        assert "scripts.build_session_digest" in text, (
            "scripts.build_session_digest must be invoked in daily.yml — an unwired builder "
            "cannot advance the session ledger (OIP E1 §0.14)")

    def test_runs_after_the_gex_board_it_reads(self):
        """It reads site/options_structure/gex_state/*.json, which build_gex_board writes in
        the parallel band, so it must sit after the band barrier — represented here by
        build_options_command, the neighbouring post-barrier serial step."""
        text = self.DAILY.read_text()
        assert text.find("scripts.build_session_digest") > text.find(
            "scripts.build_options_command")

    def test_declared_in_dag_yml(self):
        assert "build_session_digest" in self.DAG.read_text(), (
            "build_session_digest needs a config/dag.yml entry or check_dag_conformance fails")

    def test_artifacts_registered_in_synapse(self):
        text = self.SYNAPSE.read_text()
        for needle in ("data/options_session/", "site/session/",
                       "options_session/ledger.parquet"):
            assert needle in text, f"{needle} must be registered in config/synapse.yml"

    def test_synapse_registry_still_validates(self):
        from engine.neuralweb import synapse
        reg = synapse.load_registry(ROOT)
        assert synapse.validate_registry(reg) == []

    def test_annotations_start_the_line(self, capsys):
        """A `::warning` through a logger is dropped silently by GitHub."""
        bsd._warn("session_digest", "probe")
        out = capsys.readouterr().out.splitlines()
        assert any(l.startswith("::warning title=session_digest::") for l in out)
        src = (ROOT / "scripts" / "build_session_digest.py").read_text()
        for level in ("debug", "info", "warning", "error", "critical", "exception"):
            assert f'log.{level}("::' not in src and f"log.{level}('::" not in src
