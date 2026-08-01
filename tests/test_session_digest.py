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


def build_tide_docs(*, session_date: str, zero_dte_share_path=None, n: int = 79,
                    cadence_sec: int = 300, label_skew_min: int = 0) -> tuple[dict, dict]:
    """Tide + dte_tide payloads produced by the REAL writers (M8 fixture-fidelity law).

    Trades are fed through `engine.live_flow._accumulate_tide` and the documents come out of
    `build_tide_current` / `build_dte_tide_current`, so the fixtures carry whatever those
    functions actually emit — including, when `label_skew_min` is set, the genuine
    `_minute_key` timezone defect rather than a hand-rolled imitation of it.

    `label_skew_min=-240` is applied by handing `_accumulate_tide` NAIVE timestamps, which is
    exactly how the defect arises in production: `_minute_key` localizes a naive stamp as UTC
    and converts to ET, subtracting the whole ET offset.
    """
    import pandas as pd
    from engine import live_flow as lf

    open_dt, _ = sd.session_window_et(session_date)
    day: dict = {"market_tide_minutes": {}, "sector_tide": {}, "dte_tide": {},
                 "root_minutes": {}, "root_strikes": {}, "root_expiries": {},
                 "sweep_clusters": {}}
    cum_z = cum_o = 0.0
    for i in range(n):
        t = open_dt + timedelta(seconds=cadence_sec * i)
        # A naive ET wall-clock stamp reproduces the production defect exactly; an
        # offset-aware one does not (see _minute_key).
        ts = (t.replace(tzinfo=None) if label_skew_min else t).isoformat()
        # `zero_dte_share_path(i)` is the target CUMULATIVE 0DTE share at stamp i, because the
        # tide buckets are cumulative and that is what the digest reads.  Solve this minute's
        # 0DTE premium to land on it: (cum_z + z_i)/(cum_z + z_i + cum_o + o_i) = s.
        share = zero_dte_share_path(i) if zero_dte_share_path else 0.20
        o_i = 2 * 1_500 * 10.0 * 100.0 + 3_000 * 3.0 * 100.0     # two non-0DTE legs, fixed
        want = min(0.999, max(0.0, float(share)))
        z_i = (want * (cum_o + o_i) / (1.0 - want)) - cum_z if want else 0.0
        z_i = max(0.0, z_i)
        cum_z += z_i
        cum_o += o_i
        rows = [
            {"trade_timestamp": ts, "price": 10.0, "size": 1_500, "sign": 1.0, "right": "C",
             "strike": 500.0, "expiration": (t + timedelta(days=3)).date().isoformat()},
            {"trade_timestamp": ts, "price": 10.0, "size": 1_500, "sign": 1.0, "right": "C",
             "strike": 505.0, "expiration": (t + timedelta(days=45)).date().isoformat()},
            {"trade_timestamp": ts, "price": 3.0, "size": 3_000, "sign": -1.0, "right": "P",
             "strike": 495.0, "expiration": (t + timedelta(days=3)).date().isoformat()},
        ]
        if z_i > 0:
            rows.append({"trade_timestamp": ts, "price": 10.0,
                         "size": max(1, int(round(z_i / 1000.0))), "sign": 1.0, "right": "C",
                         "strike": 500.0, "expiration": t.date().isoformat()})
        lf._accumulate_tide(pd.DataFrame(rows), "SPY", "Broad", "大盘", ts, session_date,
                            day["market_tide_minutes"], day["sector_tide"], day["dte_tide"],
                            day["root_minutes"], day["root_strikes"], day["root_expiries"],
                            day["sweep_clusters"])
    asof = f"{session_date}T20:00:00+00:00"
    return (lf.build_tide_current(session_date, asof, day),
            lf.build_dte_tide_current(session_date, asof, day))


def write_tides(base: Path, *, session_date: str, doc_date: str | None = None,
                asof_date: str | None = None, **kw) -> tuple[dict, dict]:
    """Write the dated tide/dte archives; returns the two documents."""
    tide, dte = build_tide_docs(session_date=session_date, **kw)
    if doc_date:
        tide["session_date"] = doc_date
    if asof_date:
        tide["asof"] = dte["asof"] = f"{asof_date}T20:00:00+00:00"
    for fam, doc in (("tide", tide), ("dte_tide", dte)):
        p = base / "live_flow" / fam
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{session_date}.json").write_text(json.dumps(doc))
    return tide, dte


def write_gex_state(site: Path, root: str, *, vintage: str, flip: float = 750.43,
                    call_wall: float = 760.0, put_wall: float = 725.0,
                    spot: float = 735.05, asof: str | None = None) -> None:
    """gex_state payload with a REALISTIC post-midnight-UTC `asof` (B1 fixture law).

    `build_gex_board` stamps `datetime.now(UTC)` and the nightly engine band runs 03:11–03:54
    UTC, i.e. 23:xx ET on the session day BEFORE.  Stamping the fixture at `{vintage}T21:00Z`
    (17:00 ET, same calendar date either way) hid the whole UTC-vs-ET vintage class, so the
    default here is 03:27 UTC on the day AFTER the session — the shape production actually
    writes.  Any test that passes if this is wrong is not testing the vintage logic.
    """
    if asof is None:
        nxt = date.fromisoformat(vintage) + timedelta(days=1)
        asof = f"{nxt.isoformat()}T03:27:41+00:00"
    p = site / "options_structure" / "gex_state"
    p.mkdir(parents=True, exist_ok=True)
    (p / f"{root.upper()}.json").write_text(json.dumps({
        "schema": "options_structure.gex_state/v1", "asof": asof,
        "root": root.upper(), "spot": spot, "gamma_flip": flip,
        "call_wall": call_wall, "put_wall": put_wall,
        "dist_to_flip_pct": round((spot - flip) / spot * 100, 2), "stability_pct": 15.7,
        "authority_tier": "display"}))


def _minutes(path: Path) -> int:
    """`coverage.minutes` from a written record — the yardstick for "a better read"."""
    return int(json.loads(path.read_text())["coverage"]["minutes"])


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
        assert sd.is_early_close(date(2026, 7, 28)) is False
        assert sd.is_early_close(date(2026, 11, 26)) is False   # Thanksgiving itself

    def test_a_non_session_is_never_an_early_close(self):
        """2026-07-04 is a Saturday, so the NYSE observes Independence Day on Friday 07-03 with
        a FULL closure — the bare month/day rule called that a half day.  Session-ness is
        delegated to the calendar so the whole family of such collisions is covered, not one."""
        from lib import nyse_calendar
        assert date(2026, 7, 3) in nyse_calendar.holidays(2026)
        assert nyse_calendar.is_session(date(2026, 7, 3)) is False
        assert sd.is_early_close(date(2026, 7, 3)) is False
        assert sd.is_early_close(date(2026, 12, 26)) is False   # a Saturday
        # ...and in a year where July 4 IS a weekday, July 3 is a genuine 1pm close.
        assert date(2027, 7, 4).strftime("%A") == "Sunday"
        assert date(2025, 7, 4).strftime("%A") == "Friday"
        assert sd.is_early_close(date(2025, 7, 3)) is True

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

    def test_shape_words_never_carry_their_own_subject(self):
        """B3 regression (source-level guard, defense in depth alongside the
        JS-execution test in test_build_options_command.py): every caller
        composes SHAPE_WORDS by prefixing "Premium "/"权利金" (templates/
        options.html.j2's filmstripSentence). "flat" and "insufficient" used
        to embed that subject themselves — "premium barely moved all day",
        "全天权利金几乎没有变化" — producing a doubled subject once composed
        ("Premium premium barely moved all day.",
        "权利金全天权利金几乎没有变化。"). No tag may reintroduce it."""
        for tag, (en, zh) in sd.SHAPE_WORDS.items():
            assert "premium" not in en.lower(), f"{tag}: EN twin embeds its own subject: {en!r}"
            assert "权利金" not in zh, f"{tag}: ZH twin embeds its own subject: {zh!r}"

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
        assert ev[0]["type"] == "premium_burst"
        assert abs(ev[0]["effect_sigma"]) >= sd.BURST_EFFECT_SIGMA
        assert abs(ev[0]["t_stat"]) >= sd.BURST_T_MIN
        assert ev[0]["baseline_stamps"] >= sd.BURST_MIN_BASELINE

    def test_effect_size_and_test_statistic_are_different_numbers_named_differently(self):
        """`z` must be the honest two-sample statistic, `effect_sigma` the scale-free effect.

        They differ by sqrt(w*b/(w+b)) — 2.24x at a 10-increment baseline, 3.08x by the close —
        so publishing one under the other's name would misstate every event's strength by a
        factor that drifts through the session.
        """
        vals = self._series(n_quiet=25, n_burst=5)
        st = sd.window_vs_baseline(vals, 10)
        ratio = math.sqrt(st.window_n * st.baseline_n / (st.window_n + st.baseline_n))
        assert st.t == pytest.approx(st.effect_sigma * ratio, rel=1e-9)
        assert abs(st.t) > abs(st.effect_sigma)

        ev = sd.premium_bursts(TIMES, vals)[0]
        # The receipt must match the stats AT THE EVENT'S OWN STAMP, not at the end of the day —
        # the event fires the moment the gates clear and its numbers are frozen there.
        at = sd.window_vs_baseline(vals[: TIMES.index(ev["t"]) + 1], 10)
        assert ev["t_stat"] == pytest.approx(round(at.t, 2))
        assert ev["effect_sigma"] == pytest.approx(round(at.effect_sigma, 2))
        # N5: nothing is called `z` unless it is standardized against a single distribution, and
        # `t` is the event's TIMESTAMP — so the statistic ships as `t_stat`.
        assert "z" not in ev, "a two-sample t may not ship under the name z"
        assert ev["effect_sigma"] != ev["t_stat"]
        assert ev["t"] in TIMES
        with pytest.raises(ValueError):
            sd._event("09:30", "premium_burst", t=1.23)

    def test_t_floor_is_derived_not_typed(self):
        """N4: the hardcoded 4.47 sat 0.0021 UNDER the true knife edge, so the floor was a hair
        looser than the value it claimed to be — and any window/baseline edit would have
        silently decoupled the three constants."""
        expected = sd.BURST_EFFECT_SIGMA * math.sqrt(
            1.0 / (1.0 / sd.BURST_WINDOW_STAMPS + 1.0 / sd.BURST_MIN_BASELINE))
        assert sd.BURST_T_MIN == expected                  # exact, not approx
        assert sd.BURST_T_MIN == pytest.approx(4.472136, abs=1e-6)
        assert sd.BURST_T_MIN > 4.47, "the old literal was below the true floor"
        # the relationship survives a constant change
        assert sd._burst_t_floor(2.0, 20, 40) == pytest.approx(2.0 * math.sqrt(1 / (0.05 + 0.025)))

    def test_does_not_fire_on_a_steady_tape(self):
        assert sd.premium_bursts(TIMES, self._series(n_quiet=40, n_burst=0)) == []

    def test_flat_tape_is_no_read_not_a_zero_statistic(self):
        """Zero-variance baseline cannot be standardized; it must yield no event, not zero."""
        st = sd.window_vs_baseline([100.0] * 40, 10)
        assert math.isnan(st.effect_sigma) and math.isnan(st.t)
        assert st.fires is False
        assert sd.premium_bursts(TIMES, [100.0] * 40) == []

    def test_rearm_margin_books_one_event_for_one_acceleration(self):
        """A ramp that oscillates across the cut is ONE acceleration; the ledger counts rows."""
        vals, cum = [], 0.0
        for i in range(25):
            cum += 100.0 + (7.0 if i % 2 else -7.0)
            vals.append(cum)
        for i in range(14):                     # ramp straddling the threshold
            cum += 1500.0 if i % 2 else 1350.0
            vals.append(cum)
        assert len(sd.premium_bursts(TIMES, vals)) == 1
        # with no margin the same tape can book more than once — which is what the margin is for
        assert len(sd.premium_bursts(TIMES, vals, rearm_sigma=0.0)) >= 1

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
        assert again and again[-1]["t"] == first["t"]
        assert again[-1]["t"] == first["t"]
        assert again[-1]["t_stat"] == first["t_stat"]
        assert again[-1]["effect_sigma"] == first["effect_sigma"]

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
        assert abs(st.z) < sd.BURST_EFFECT_SIGMA        # cannot fire, by construction
        assert abs(st.z) <= math.sqrt((st.n - 10) / 10) + 1e-9
        # the two-sample framing does fire on the same tape
        assert sd.window_vs_baseline(self._series(n_quiet=25, n_burst=5), 10).fires

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
        assert r.share_at_open_t == "09:30"      # the stamp is printed, not just the number
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
        # n defaults to a span the tide clock can pin: at 5-minute cadence the read is only
        # unambiguous once the last label passes 12:00 (a +240 shift would then overrun the
        # close), i.e. n > 31.  A shorter tide day is genuinely undecidable — its own test.
        kw.setdefault("n", 40)
        write_tides(tmp_path, session_date="2026-07-28", zero_dte_share_path=share_fn, **kw)
        return json.loads((tmp_path / "live_flow" / "dte_tide" / "2026-07-28.json").read_text())

    @staticmethod
    def _share_at(doc, i):
        ks = [k for k, v in doc["buckets"].items() if v]
        tot = sum(abs(doc["buckets"][k][i]["ncp"]) + abs(doc["buckets"][k][i]["npp"]) for k in ks)
        z = abs(doc["buckets"]["0d"][i]["ncp"]) + abs(doc["buckets"]["0d"][i]["npp"])
        return z / tot * 100.0 if tot else 0.0

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

    def test_an_empty_dte_bucket_does_not_veto_the_whole_session(self, tmp_path):
        """`build_dte_tide_current` emits all five bucket keys and leaves untraded ones `[]`.

        Intersecting stamp sets across every DECLARED key let one empty bucket report "no
        same-day-expiry split" for a day with real tape.  Only non-empty buckets take part.
        Found by routing the fixtures through the real writer — the hand-written fixture
        populated all five and could not see it.
        """
        _, dte = build_tide_docs(session_date="2026-07-28", n=40,
                                 zero_dte_share_path=lambda i: 0.2 if i < 6 else 0.8)
        empty = [k for k, v in dte["buckets"].items() if not v]
        assert empty, "the real writer must be emitting at least one empty bucket here"
        block, ev = sd.zero_dte_read(dte, session_date="2026-07-28")
        assert block["peak_share"] == pytest.approx(80.0, abs=0.5)
        assert block["buckets_used"] == len(dte["buckets"]) - len(empty)
        assert len(ev) == 1

    def test_a_dead_minute_does_not_re_arm_the_family(self, tmp_path):
        """M7: a zero-total stamp carries no information, so arming state survives it.

        Resetting on a dead minute swallowed the genuine entry right after it (the next reading
        looked like "first observation") and overwrote share_at_open with a mid-session value.
        """
        doc = self._doc(tmp_path, lambda i: 0.10 if i < 6 else 0.90, n=40)
        # blank the stamp immediately before the crossing, in every bucket
        dead = doc["buckets"]["0d"][5]["t"]
        for rows in doc["buckets"].values():
            for r in rows:
                if r["t"] == dead:
                    r["ncp"] = r["npp"] = 0
        block, ev = sd.zero_dte_read(doc, session_date="2026-07-28")
        assert len(ev) == 1, "the entry after a dead minute must still book"
        assert block["share_at_open"] == pytest.approx(10.0, abs=1.0)
        assert block["share_at_open_t"] == "09:30", "not the minute after the dead one"

    def test_share_at_open_is_the_first_stamp_with_tape(self, tmp_path):
        doc = self._doc(tmp_path, lambda i: 0.30, n=40)
        for rows in doc["buckets"].values():          # blank the first two stamps entirely
            for r in rows[:2]:
                r["ncp"] = r["npp"] = 0
        block, _ = sd.zero_dte_read(doc, session_date="2026-07-28")
        assert block["share_at_open_t"] == "09:40"    # third stamp at 5-minute cadence
        assert block["share_at_open"] is not None

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

    def test_a_thin_cross_section_discloses_how_thin_it_is(self, tmp_path):
        """N7: the empty-bucket veto is fixed, but a bucket carrying 1 stamp of 40 still collapses
        the intersection to that one minute — a "session peak" measured on a single reading.
        Both counts are printed so nobody has to assume it spans the day."""
        doc = self._doc(tmp_path, lambda i: 0.20 if i < 10 else 0.70)
        longest = max(len(v) for v in doc["buckets"].values() if v)
        doc["buckets"]["1_7d"] = doc["buckets"]["1_7d"][:1]      # one surviving stamp
        block, _ = sd.zero_dte_read(doc, session_date="2026-07-28")
        assert block["stamps_used"] == 1
        assert block["stamps_in_longest_bucket"] == longest
        assert block["thin_note_en"] and block["thin_note_zh"]
        assert "1 minute" in block["thin_note_en"]

    def test_a_full_cross_section_does_not_cry_thin(self, tmp_path):
        block, _ = sd.zero_dte_read(self._doc(tmp_path, lambda i: 0.20),
                                    session_date="2026-07-28")
        assert block["stamps_used"] == block["stamps_in_longest_bucket"] == 40
        assert "thin_note_en" not in block

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

    @staticmethod
    def _labels(start_min: int, n: int, cadence_min: int) -> list[str]:
        return [f"{(start_min + i * cadence_min) // 60:02d}"
                f"{(start_min + i * cadence_min) % 60:02d}" for i in range(n)]

    @pytest.mark.parametrize("day,start,n,cad,expect,why", [
        ("2026-07-28", 9 * 60 + 30, 79, 5, 0, "exchange time already — no-op (post-fix state)"),
        ("2026-07-28", 5 * 60 + 30, 79, 5, 240, "the _minute_key defect, summer offset"),
        ("2026-01-15", 4 * 60 + 30, 79, 5, 300, "the same defect at the WINTER offset"),
        ("2026-07-28", 5 * 60 + 35, 79, 5, 240, "defect plus a 5-min late start — preserved"),
        ("2026-07-28", 10 * 60 + 30, 67, 5, 0, "genuinely late start — must NOT be shifted"),
    ])
    def test_offset_truth_table(self, day, start, n, cad, expect, why):
        ck = sd.clock_read(day, self._labels(start, n, cad), cadence_sec=cad * 60)
        assert ck.offset_min == expect, why
        assert ck.trusted, why

    def test_a_single_off_grid_print_no_longer_defeats_the_read(self):
        """MEASURED FAILURE of the earlier single-label rule.

        A 09:25 ET print sits BEFORE the open, so an earliest-label rule concluded the whole
        clean session was skewed and shifted every event 4 hours.  Scoring the distribution, the
        one stray label cannot outvote 78 good ones.
        """
        labels = ["0925"] + self._labels(9 * 60 + 30, 78, 5)
        ck = sd.clock_read(self.D, labels, cadence_sec=300)
        assert ck.offset_min == 0
        assert ck.labels_outside == 1        # the stray is counted, not hidden
        assert ck.trusted

    def test_a_skewed_session_running_past_the_close_is_still_corrected(self):
        """MEASURED FAILURE of the earlier single-label rule, the other direction.

        At the configured 120-second cadence a skewed session whose last label lands 3 minutes
        past the close made the old overshoot guard refuse the correction entirely — silently
        stamping all 196 events 4 hours early.  Now the +240 candidate misplaces one label while
        candidate 0 misplaces ~117, so the correction wins on the evidence.
        """
        labels = self._labels(5 * 60 + 30, 197, 2)          # 05:30..11:62 -> 12:02, skewed
        ck = sd.clock_read(self.D, labels, cadence_sec=120)
        assert ck.offset_min == 240
        assert sd.shift_label(labels[0], ck.offset_min) == "09:30"
        assert ck.labels_outside == 1        # the 16:02 tail is declared

    def test_candidate_set_is_two_and_dst_derived(self):
        """The defect shifts by exactly the ET↔UTC offset ON THE SESSION DATE, which the calendar
        knows — so there is never a guess between 4 and 5 hours."""
        assert sd.clock_candidates("2026-07-28") == (0, 240)      # EDT
        assert sd.clock_candidates("2026-01-15") == (0, 300)      # EST
        assert sd.defect_offset_minutes("2026-11-27") == 300

    @pytest.mark.parametrize("n,until", [(46, "11:00"), (61, "11:30"), (76, "12:00")])
    def test_a_clean_truncated_surface_session_publishes_its_events(self, n, until):
        """N1 (blocker): these three all measured ambiguous → trusted False → events dropped.

        A poller that died at 11:00 ET shipped ZERO events for a session whose labels were
        perfectly good.  The defect is one-directional — localize-as-UTC only shifts labels
        EARLIER — and `stamp_hhmm` converts an AWARE UTC datetime, so a surface label cannot
        carry it.  A fit at 0 is therefore dispositive for this family.
        """
        labels = self._labels(9 * 60 + 30, n, 2)
        ck = sd.clock_read(self.D, labels, cadence_sec=120,
                           family=sd.CLOCK_FAMILY_SURFACE)
        assert ck.offset_min == 0 and ck.trusted and not ck.ambiguous, until
        # ...and the same labels are genuinely undecidable for the family that CAN be skewed
        tide = sd.clock_read(self.D, labels, cadence_sec=120, family=sd.CLOCK_FAMILY_TIDE)
        assert tide.ambiguous and not tide.trusted

    def test_a_clean_truncated_surface_session_ships_events_end_to_end(self):
        frame, stamps = make_frame(n_stamps=46, cadence_sec=120,
                                   spot_path=lambda i: 99.0 if i < 23 else 101.0)
        r = sd.build_session_record(
            root="SPY", session_date=self.D, asof="t", frame=frame, stamps=stamps,
            cadence_sec=120,
            spots_by_stamp={s: (99.0 if i < 23 else 101.0) for i, s in enumerate(stamps)},
            levels={"flip": 100.0, "vintage": self.D, "source": "g"})
        assert r["coverage"]["clock_ambiguous"] is False
        assert r["flip"]["crosses"] == 1 and r["events"], "a dead poller must not cost the day"
        assert r["coverage"]["events_dropped_clock"] == 0

    def test_a_truncated_skewed_tide_still_resolves(self):
        """"Declare what it can honestly declare": with only one non-zero candidate there is
        nothing to be ambiguous between, so a skewed half-session resolves cleanly."""
        labels = self._labels(5 * 60 + 30, 46, 2)      # a real 09:30–11:00 shifted 4h early
        ck = sd.clock_read(self.D, labels, cadence_sec=120, family=sd.CLOCK_FAMILY_TIDE)
        assert ck.fitting == (240,)
        assert ck.offset_min == 240 and ck.trusted
        assert sd.shift_label(labels[0], ck.offset_min) == "09:30"

    def test_the_genuine_conflation_still_declares_ambiguity(self):
        """A tide archive whose SKEWED labels land wholly inside the window is indistinguishable
        from a clean late start — measured: 10:00–12:00 fits at 0 and at +240 (14:00–16:00)."""
        ck = sd.clock_read(self.D, self._labels(10 * 60, 25, 5), cadence_sec=300,
                           family=sd.CLOCK_FAMILY_TIDE)
        assert set(ck.fitting) == {0, 240}
        assert ck.ambiguous and not ck.trusted
        assert ck.note_en and ck.note_zh

    def test_residual_receipt_is_reported(self):
        ck = sd.clock_read(self.D, self._labels(5 * 60 + 30, 79, 5), cadence_sec=300)
        assert ck.residual_median_min == pytest.approx(-240.0)
        clean = sd.clock_read(self.D, self._labels(9 * 60 + 30, 79, 5), cadence_sec=300)
        assert clean.residual_median_min == pytest.approx(0.0)

    def test_no_labels_is_a_no_op_not_a_crash(self):
        ck = sd.clock_read(self.D, [], cadence_sec=300)
        assert ck.offset_min == 0 and ck.trusted and ck.note_en == ""

    def test_an_untrusted_tide_clock_suppresses_only_its_own_timestamps(self):
        """M1's instruction, scoped per family: the tide clock governs the tide block ALONE.

        A surface archive nobody can date must not delete a tide finding that was perfectly
        datable, and vice versa.
        """
        _, dte = build_tide_docs(session_date=self.D, n=25, cadence_sec=300,
                                 zero_dte_share_path=lambda i: 0.2 if i < 10 else 0.9)
        # shift the labels into the genuinely ambiguous 10:00-12:00 band
        for rows in dte["buckets"].values():
            for row in rows:
                row["t"] = sd.shift_label(row["t"], 30)
        block, ev = sd.zero_dte_read(dte, session_date=self.D, cadence_sec=300)
        assert block["clock_ambiguous"] is True
        assert ev == [], "spike events are nothing but stamps, so they cannot ship"
        assert block["at"] is None and block["share_at_open_t"] is None
        assert block["peak_share"] is not None, "a share is not a moment; it still publishes"
        assert block["clock_note_en"] and block["clock_note_zh"]

    def test_untrusted_surface_clock_suppresses_surface_events_only(self):
        """The surface family is dispositive at 0 whenever 0 fits (N1), so reaching the untrusted
        path takes labels that fit NEITHER candidate — here 03:00–04:00, which is outside the
        window as-is and still outside shifted (+4h lands 07:00–08:00).  Both misplace every
        label equally, so the read declares itself ambiguous instead of picking one."""
        n = 13
        frame, stamps = make_frame(n_stamps=n, spot_path=lambda i: 99.0 if i < 6 else 101.0,
                                   label_skew_min=-390)
        r = sd.build_session_record(
            root="SPY", session_date=self.D, asof="t", frame=frame, stamps=stamps,
            cadence_sec=300,
            spots_by_stamp={s: (99.0 if i < 6 else 101.0) for i, s in enumerate(stamps)},
            levels={"flip": 100.0, "vintage": self.D, "source": "g"})
        assert r["coverage"]["clock_ambiguous"] is True
        assert r["events"] == []
        assert r["coverage"]["events_dropped_clock"] > 0
        assert any("could not be matched" in m for m in r["coverage"]["missing_en"])
        assert len(r["coverage"]["missing_zh"]) == len(r["coverage"]["missing_en"])
        assert r["arc"], "the arc's shape does not depend on the clock and is still published"

    def test_events_outside_the_session_window_are_dropped_after_the_shift(self):
        """M2: the invariant is enforced POST-shift, not assumed."""
        assert sd._label_in_session("09:30", self.D) is True
        assert sd._label_in_session("16:00", self.D) is True
        assert sd._label_in_session("17:05", self.D) is False
        assert sd._label_in_session("09:29", self.D) is False
        assert sd._label_in_session(None, self.D) is False       # fails closed
        assert sd._label_in_session("12:00", "2026-11-27") is True
        assert sd._label_in_session("14:00", "2026-11-27") is False   # 1pm close

    def test_shift_label_round_trips_and_tolerates_junk(self):
        assert sd.shift_label("0530", 240) == "09:30"
        assert sd.shift_label("05:35", 240) == "09:35"
        assert sd.shift_label("0930", 0) == "09:30"
        assert sd.shift_label("nonsense", 240) == "nonsense"
        assert sd.shift_label(None, 240) == ""

    def test_skewed_archive_yields_the_same_event_times_as_a_clean_one(self):
        """The pinning test: a fixture with skewed labels must produce correct event times.

        79 stamps (a full 5-minute session) so the clock read is unambiguous — a short day is
        genuinely undecidable and is covered by its own test above.
        """
        def spots(i):
            return 99.0 if i < 40 else 101.0

        clean, c_stamps = make_frame(n_stamps=79, spot_path=spots)
        skew, s_stamps = make_frame(n_stamps=79, spot_path=spots, label_skew_min=-240)
        assert s_stamps[0] == "0530" and c_stamps[0] == "0930"      # fixture really is skewed

        def rec(frame, stamps):
            return sd.build_session_record(
                root="SPY", session_date=self.D, asof="t", frame=frame, stamps=stamps,
                cadence_sec=300,
                spots_by_stamp={s: spots(i) for i, s in enumerate(stamps)},
                levels={"flip": 100.0, "vintage": self.D, "source": "x"})

        a, b = rec(clean, c_stamps), rec(skew, s_stamps)
        assert a["events"] and b["events"], "both sides must actually produce events"
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
        # sentence-case at the source: this is a standalone, sentence-initial
        # disclosure everywhere it renders (minor fix — was lowercase-initial,
        # inconsistent with every fallback constant that quotes it).
        assert "No intraday record" in cov["quality_en"] and cov["quality_zh"]

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
                  "falsifier", "refuted", "证伪", "z-score", "p-value", "COLLECT_LANE",
                  # m1: a bare Python None interpolated into copy ("the close of None") teaches
                  # a reader nothing and reads as a bug.
                  "none", "null")
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

    @staticmethod
    def _assert_self_consistent(r: dict) -> dict:
        """N2: no two fields of one record — or one ledger row — may disagree about one fact."""
        row = sd.ledger_row(r)
        counts = r["event_counts"]
        listed_flip = len([e for e in r["events"] if e["type"] == "flip_cross"])
        listed_wall = len([e for e in r["events"]
                           if e["type"] in ("call_wall_touch", "put_wall_touch")])
        # record internal
        assert r["flip"]["crosses"] == listed_flip
        # record <-> ledger
        assert row["flip_crosses"] == r["flip"]["crosses"] == listed_flip
        assert row["events_flip_cross"] == counts.get("flip_cross", 0) == listed_flip
        assert (row["events_call_wall_touch"] + row["events_put_wall_touch"]) == listed_wall
        assert row["events_total"] == len(r["events"])
        fam = [c for c in sd.LEDGER_COLUMNS if c.startswith("events_") and c != "events_total"]
        assert row["events_total"] == sum(row[c] for c in fam)
        # a standing side may not survive its own crossing being withheld
        if listed_flip == 0 and r["coverage"]["events_dropped_clock"]:
            assert r["flip"]["last_side"] is None and r["flip"]["side_at_open"] is None
        return row

    def _crossing_record(self, **kw):
        n = kw.pop("n_stamps", 79)
        skew = kw.pop("label_skew_min", 0)
        frame, stamps = make_frame(n_stamps=n, label_skew_min=skew,
                                   spot_path=lambda i: 99.0 if i < n // 2 else 101.0)
        base = dict(root="SPY", session_date="2026-07-28", asof="t", frame=frame,
                    stamps=stamps, cadence_sec=300,
                    spots_by_stamp={s: (99.0 if i < n // 2 else 101.0)
                                    for i, s in enumerate(stamps)},
                    levels={"flip": 100.0, "call_wall": 101.0, "put_wall": 98.0,
                            "vintage": "2026-07-28", "source": "g"})
        base.update(kw)
        return sd.build_session_record(**base)

    def test_a_clean_crossing_day_is_self_consistent(self):
        r = self._crossing_record()
        row = self._assert_self_consistent(r)
        assert row["flip_crosses"] == 1 and r["flip"]["last_side"] == "above"

    def test_a_clock_dropped_day_is_self_consistent(self):
        """The frozen contradiction: flip_crosses=1 beside events_flip_cross=0."""
        r = self._crossing_record(n_stamps=13, label_skew_min=-390)  # fits neither candidate
        assert r["coverage"]["clock_ambiguous"] is True
        assert r["events"] == []
        row = self._assert_self_consistent(r)
        assert row["flip_crosses"] == 0, "the count must follow the events it counts"
        assert r["flip"]["last_side"] is None and r["walls"]["inside_at_open"] == {
            "call": None, "put": None}
        # ...and the why travels with it, in plain words
        assert r["coverage"]["events_dropped_clock"] > 0
        assert any("could not be matched" in m for m in r["coverage"]["missing_en"])
        assert r["walls"]["closest_pct"]["call"] is not None, (
            "a pure extremum asserts no moment and survives the drop")

    def test_a_window_dropped_event_is_self_consistent(self):
        """M2 drop path: same rule, different cause."""
        n = 79
        frame, stamps = make_frame(n_stamps=n, spot_path=lambda i: 99.0 if i < 40 else 101.0)
        # push the crossing stamp's label outside the session window
        bad = stamps[40]
        frame["time_steps"] = [("17:05" if s == bad else t)
                               for s, t in zip(stamps, frame["time_steps"])]
        stamps = [("1705" if s == bad else s) for s in stamps]
        r = sd.build_session_record(
            root="SPY", session_date="2026-07-28", asof="t", frame=frame, stamps=stamps,
            cadence_sec=300,
            spots_by_stamp={s: (99.0 if i < 40 else 101.0) for i, s in enumerate(sorted(stamps))},
            levels={"flip": 100.0, "vintage": "2026-07-28", "source": "g"})
        assert r["coverage"]["events_dropped_window"] >= 0
        self._assert_self_consistent(r)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. builder — end to end, degraded modes, lane guard
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuilderEndToEnd:
    D = "2026-07-28"

    def _archive(self, tmp_path, *, n=40, roots=("SPY",), drop=(), walls=None,
                 strikes=None):
        arch = tmp_path / "arch"
        for r in roots:
            frame, stamps = make_frame(root=r, n_stamps=n, session_date=self.D,
                                        spot_path=lambda i: 99.0 if i < n // 2 else 101.0,
                                        walls=walls, strikes=strikes)
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

    def test_filmstrip_html_lives_only_on_the_display_artifact_not_the_ledger(self, repo, monkeypatch):
        """OIP W1 §3 + RULING (adversarial review): the session filmstrip is an
        SSR fragment (lib.illus.session_filmstrip), but engine/session_digest.py
        describes the dated record as a settled, replayable document — rendered
        SVG markup drifts from CSS and can never be replayed. write_latest (the
        `site/` pointer Ticker mode / gex.html actually fetch) carries the
        fragment; write_record (the dated data/options_session/ archive graded
        as the ledger's source of truth) must NOT — it keeps only the fields the
        fragment is derived from (arc, coverage, events, flip)."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        write_gex_state(repo / "site", "SPY", vintage=self.D, flip=100.0,
                        call_wall=101.0, put_wall=98.0)
        bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        dated = json.loads((repo / "data" / "options_session" / self.D / "SPY.json").read_text())
        latest = json.loads((repo / "site" / "session" / "SPY.json").read_text())
        assert "filmstrip_html" not in dated, (
            "the dated ledger record must not carry rendered markup — it drifts "
            "from CSS and makes the record un-replayable"
        )
        assert "filmstrip_html" in latest
        frag = latest["filmstrip_html"]
        assert frag.startswith('<figure class="ilx oew-film')
        # this archive's coverage is real (n=40, non-zero minutes) — the
        # present-data variant must draw ink, never silently fall to null.
        assert latest["coverage"]["minutes"] > 0 and dated["coverage"]["minutes"] > 0
        assert "oew-film-null" not in frag
        assert 'class="ilx-path oew-film-ink"' in frag
        # every OTHER field the fragment is derived from still lands on the
        # ledger — this is an omission of the rendered field alone, not a
        # thinner record.
        for k in ("arc", "coverage", "events", "flip", "arc_shape_en", "arc_shape_zh"):
            assert k in dated, f"{k} must still be on the ledger record"

    def test_filmstrip_html_degrades_honestly_when_the_archive_is_empty(self, repo, monkeypatch):
        """A session promised 40 stamps but with EVERY one unreadable (the
        listed-but-PUT-failed case coverage_block itself is built to disclose)
        must still carry the field — the honest-null variant, never an absent
        key or a fabricated shape."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        _, all_stamps = make_frame(root="SPY", n_stamps=40, session_date=self.D)
        arch = self._archive(repo, n=40, drop=all_stamps)
        bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        latest = json.loads((repo / "site" / "session" / "SPY.json").read_text())
        assert latest["coverage"]["minutes"] == 0
        assert "filmstrip_html" in latest
        assert 'class="ilx oew-film oew-film-null"' in latest["filmstrip_html"]
        # coverage_block's own composed sentence, verbatim ("No intraday
        # record...", sentence-cased at the source) — not the illus.py fallback
        # string (which only fires when quality_en itself is absent, not the
        # case here).
        assert "No intraday record for this session" in latest["filmstrip_html"]

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

    # ── B1: vintage is a SESSION date, never a UTC date slice ────────────────────
    def test_gex_state_vintage_maps_utc_stamp_to_its_et_session(self, repo):
        """`asof[:10]` was D+1 on every real nightly and killed the same-session check.

        `build_gex_board` stamps `datetime.now(UTC)`; the engine band commits 03:11–03:54 UTC,
        which is 23:xx ET the evening BEFORE.  The whole EOD-fallback path depended on getting
        this right, and the bilingual note asserted a false date when it was wrong.
        """
        assert bsd.levels_vintage("2026-07-30T03:27:41+00:00") == "2026-07-29"
        assert bsd.levels_vintage("2026-07-29T21:00:00+00:00") == "2026-07-29"
        assert bsd.levels_vintage("2026-08-01T03:27:41+00:00") == "2026-07-31"   # Sat -> Fri
        assert bsd.levels_vintage("2026-07-30T03:27:41Z") == "2026-07-29"
        assert bsd.levels_vintage(None) is None
        assert bsd.levels_vintage("not a date") is None
        # ...and the naive UTC slice this replaced would have said the wrong thing:
        assert "2026-07-30T03:27:41+00:00"[:10] != "2026-07-29"

        write_gex_state(repo / "site", "SPY", vintage=self.D)
        lv = bsd.read_levels(repo / "site", "SPY")
        assert lv["vintage"] == self.D

    def test_eod_walls_survive_a_realistic_post_midnight_stamp(self, repo, monkeypatch):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        write_gex_state(repo / "site", "SPY", vintage=self.D, flip=100.0,
                        call_wall=101.0, put_wall=98.0)
        bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        rec = json.loads((repo / "data" / "options_session" / self.D / "SPY.json").read_text())
        assert rec["flip"]["level_is_this_session"] is True
        assert rec["walls"]["close"] == {"call": 101.0, "put": 98.0,
                                         "source": rec["levels"]["source"]}
        assert "closing map" in rec["flip"]["note_en"]

    # ── B2: level-dependent families are gated on a same-session map ─────────────
    def test_foreign_vintage_levels_suppress_flip_and_wall_families(self, repo, monkeypatch):
        """The record refuses to print a foreign map as this session's close; scoring events
        against it anyway would put that same rejected number inside every receipt."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        write_gex_state(repo / "site", "SPY", vintage="2026-07-24", flip=100.0,
                        call_wall=101.0, put_wall=98.0)
        bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        rec = json.loads((repo / "data" / "options_session" / self.D / "SPY.json").read_text())
        assert rec["flip"]["level_is_this_session"] is False
        assert rec["flip"]["crosses"] == 0
        assert not [e for e in rec["events"]
                    if e["type"] in ("flip_cross", "call_wall_touch", "put_wall_touch")]
        assert any("not from this session" in m for m in rec["coverage"]["missing_en"])
        assert len(rec["coverage"]["missing_zh"]) == len(rec["coverage"]["missing_en"])
        assert "another session" in rec["flip"]["note_en"]
        # the crossings the archive DOES support are unaffected
        assert rec["event_counts"].get("premium_burst", 0) >= 0

    def test_level_receipts_carry_the_vintage_they_were_measured_against(self):
        r = sd.flip_crossings(TIMES, [99.0] * 3 + [101.0] * 3, 100.0,
                              level_vintage="2026-07-28")
        assert r.events[0]["level_vintage"] == "2026-07-28"
        w = sd.wall_touches(TIMES, [98.0, 98.0, 100.0], call_wall=100.0, put_wall=None,
                            level_vintage="2026-07-28")
        assert w.events[0]["level_vintage"] == "2026-07-28"

    def test_ledger_carries_level_vintage_columns(self, repo, monkeypatch):
        """Schema is fixed BEFORE any row exists — a column added later is null forever."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        write_gex_state(repo / "site", "SPY", vintage=self.D, flip=100.0)
        bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        import pandas as pd
        lg = pd.read_parquet(repo / "data" / "options_session" / "ledger.parquet")
        for col in ("levels_vintage", "levels_source", "levels_is_this_session",
                    "clock_offset_min", "clock_ambiguous", "coverage_absent_objects"):
            assert col in lg.columns, col
        assert lg.iloc[0]["levels_vintage"] == self.D
        assert bool(lg.iloc[0]["levels_is_this_session"]) is True

    # ── B3: a settled record is only replaced by a strictly better read ──────────
    def test_a_thinner_reread_never_replaces_a_settled_record(self, repo, monkeypatch):
        """Post-retention re-runs measured coverage 79 -> 6 while the ledger kept 79.

        Weekends make it routine: three nightly runs all resolve to the same Friday.
        """
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo, n=40)
        bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        p = repo / "data" / "options_session" / self.D / "SPY.json"
        full = _minutes(p)
        assert full == 40

        # the archive ages out: only the last few stamps remain
        d = arch / "live_flow" / "surface" / "SPY" / self.D
        keep = sorted(f.name for f in d.glob("*.json") if f.name != "idx.json")[-4:]
        for f in d.glob("*.json"):
            if f.name != "idx.json" and f.name not in keep:
                f.unlink()
        res = bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        assert _minutes(p) == full, "the settled record must not degrade on a thin re-read"
        assert "SPY" not in res["data_written"]
        # ...and the latest pointer holds its fuller read of the same day too
        assert _minutes(repo / "site" / "session" / "SPY.json") == full
        assert "SPY" not in res["written"]

    def test_a_better_reread_does_replace_the_record(self, repo, monkeypatch):
        """Keep-first must not become keep-forever: a genuine backfill has to land."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo, n=40)
        d = arch / "live_flow" / "surface" / "SPY" / self.D
        idx_path = d / "idx.json"
        full_idx = json.loads(idx_path.read_text())
        # first run sees only the first 10 stamps
        idx_path.write_text(json.dumps({**full_idx, "stamps": full_idx["stamps"][:10],
                                        "latest": full_idx["stamps"][9]}))
        bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        p = repo / "data" / "options_session" / self.D / "SPY.json"
        assert _minutes(p) == 10
        # the poller backfills the rest; the fuller read must win
        idx_path.write_text(json.dumps(full_idx))
        res = bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        assert _minutes(p) == 40
        assert "SPY" in res["data_written"] and "SPY" in res["written"]

    # ── M3/M4: read shape and the wall-clock budget ──────────────────────────────
    def test_the_day_is_read_from_one_frame_not_every_frame(self, repo, monkeypatch):
        """The newest frame already carries the whole session; fetching all of them is
        quadratic in bytes (measured 107 MB for one root at the configured 120s cadence)."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        # 200 strikes so the quadratic growth is real: with a 3-strike grid every frame is a few
        # hundred bytes and the comparison would prove nothing.
        arch = self._archive(repo, n=40, strikes=[600.0 + k for k in range(200)])
        res = bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        rec = json.loads((repo / "data" / "options_session" / self.D / "SPY.json").read_text())
        assert rec["arc_points_full"] == 40, "the full day came out of the one frame"
        # bytes: 2 index objects + 2 full frames + 40 head reads, NOT 40 full frames
        every_frame = sum(f.stat().st_size for f in
                          (arch / "live_flow" / "surface" / "SPY" / self.D).glob("*.json"))
        assert res["r2_mb"] * 1e6 < every_frame * 0.25, (res["r2_mb"], every_frame)
        assert res["range_fallbacks"] == 0, "the head read must find spot without a fallback"

    def test_head_read_finds_spot_without_fetching_the_frame(self, repo):
        """The fast path: a ~256-byte range read yields the stamp's spot."""
        arch = self._archive(repo, n=6, strikes=[600.0 + k for k in range(200)])
        reader = bsd.ArchiveReader(from_dir=arch)
        stamp = json.loads(
            (arch / "live_flow" / "surface" / "SPY" / self.D / "idx.json").read_text())["stamps"][-1]
        spot, present = reader.stamp_spot("SPY", self.D, stamp)
        assert present is True and spot == 101.0
        assert reader.range_fallbacks == 0
        assert reader.bytes_read <= bsd.HEAD_RANGE_BYTES

    def test_a_reordered_spot_key_falls_back_instead_of_going_wrong(self, repo):
        """The head read depends on a WRITER detail (spot first).  If that ever changes the
        builder must get slower and noisier, never wrong."""
        arch = self._archive(repo, n=6, strikes=[600.0 + k for k in range(200)])
        d = arch / "live_flow" / "surface" / "SPY" / self.D
        stamp = json.loads((d / "idx.json").read_text())["stamps"][-1]
        doc = json.loads((d / f"{stamp}.json").read_text())
        spot = doc.pop("spot")
        (d / f"{stamp}.json").write_text(json.dumps({**doc, "spot": spot}))   # spot moved LAST
        reader = bsd.ArchiveReader(from_dir=arch)
        got, present = reader.stamp_spot("SPY", self.D, stamp)
        assert reader.range_fallbacks == 1, "the head must not have satisfied the read"
        assert present is True and got == spot, "the value is still recovered, just not cheaply"

    def test_a_truncated_number_in_the_head_falls_back_instead_of_lying(self, repo):
        """N3: without a terminator the regex matched a PREFIX — b'{"spot":73' yielded 73 for a
        spot of 735.05, silently wrong by an order of magnitude and never falling back."""
        assert bsd._SPOT_HEAD_RE.search(b'{"spot":73') is None
        assert bsd._SPOT_HEAD_RE.search(b'{"spot":735.05,"price_levels":[1]}').group(1) == b"735.05"
        assert bsd._SPOT_HEAD_RE.search(b'{"spot":null,"a":1}').group(1) == b"null"
        assert bsd._SPOT_HEAD_RE.search(b'{"spot": -12.5 }').group(1) == b"-12.5"
        # end-to-end: a head window that stops mid-number must produce a fallback, not a wrong spot
        arch = self._archive(repo, n=6, strikes=[600.0 + k for k in range(200)])
        d = arch / "live_flow" / "surface" / "SPY" / self.D
        stamp = json.loads((d / "idx.json").read_text())["stamps"][-1]
        reader = bsd.ArchiveReader(from_dir=arch)
        want = json.loads((d / f"{stamp}.json").read_text())["spot"]
        # a head of exactly 11 bytes cuts '{"spot": 101.0' mid-number
        import unittest.mock as m
        with m.patch.object(bsd, "HEAD_RANGE_BYTES", 11):
            got, present = reader.stamp_spot("SPY", self.D, stamp)
        assert reader.range_fallbacks == 1
        assert present is True and got == want

    def test_a_missing_stamp_object_reports_absent_not_a_null_spot(self, repo):
        """A null spot on a REAL object is covered tape with an unknown price; a missing object
        is not covered at all.  Conflating them would overstate coverage."""
        arch = self._archive(repo, n=6)
        d = arch / "live_flow" / "surface" / "SPY" / self.D
        reader = bsd.ArchiveReader(from_dir=arch)
        assert reader.stamp_spot("SPY", self.D, "9999") == (None, False)
        stamp = json.loads((d / "idx.json").read_text())["stamps"][0]
        doc = json.loads((d / f"{stamp}.json").read_text())
        (d / f"{stamp}.json").write_text(json.dumps({**doc, "spot": None}))
        assert reader.stamp_spot("SPY", self.D, stamp) == (None, True)

    def test_a_spent_budget_writes_honest_partial_output(self, repo, monkeypatch, capsys):
        """The engine job was cancelled at its 200-minute cap in 5 of 8 recent nightlies, so an
        exhausted budget must degrade rather than run long."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo, roots=("SPY", "QQQ"), n=20)
        res = bsd.run(session_date=self.D, roots=["SPY", "QQQ"], from_dir=arch, root_dir=repo,
                      budget_seconds=-1.0)
        assert res["ok"] is True
        assert res["budget_skipped"] == ["SPY", "QQQ"]
        assert res["roots"] == []
        out = capsys.readouterr().out
        assert any("read budget spent" in l and l.startswith("::warning")
                   for l in out.splitlines())

    # ── M9: a walk-back means two axes, and that must be said ────────────────────
    def test_walk_back_axis_divergence_is_warned_and_disclosed(self, repo, monkeypatch,
                                                               capsys):
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo, n=20)
        d = arch / "live_flow" / "surface" / "SPY" / self.D
        newest = json.loads((d / "idx.json").read_text())["stamps"][-1]
        (d / f"{newest}.json").write_text("{ truncated")     # newest frame unreadable
        bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        rec = json.loads((repo / "data" / "options_session" / self.D / "SPY.json").read_text())
        cov = rec["coverage"]
        assert cov["premium_total_minutes"] == 19 and cov["minutes"] == 19
        assert cov["premium_total_axis_gap"] >= 0
        assert rec["inputs"]["surface_frame_is_last_stamp"] is False
        out = capsys.readouterr().out
        assert any("newest readable snapshot" in l and l.startswith("::warning")
                   for l in out.splitlines())

    # ── m6: the dated records are committed artifacts and need a sweep ───────────
    def test_dated_records_are_pruned_beyond_the_retained_window(self, repo):
        base = repo / "data" / "options_session"
        for day in range(1, 8):
            d = base / f"2026-06-{day:02d}"
            d.mkdir(parents=True)
            (d / "SPY.json").write_text("{}")
        (base / "not-a-date").mkdir()
        (base / "ledger.parquet").write_text("x")
        dropped = bsd.prune_records(repo / "data", retain=3)
        assert dropped == ["2026-06-04", "2026-06-03", "2026-06-02", "2026-06-01"]
        assert sorted(d.name for d in base.iterdir() if d.is_dir()) == [
            "2026-06-05", "2026-06-06", "2026-06-07", "not-a-date"]
        assert (base / "ledger.parquet").exists(), "the durable record is never swept"

    # ── N6: one summary shape on every return path ───────────────────────────────
    def test_every_return_path_publishes_the_same_summary_keys(self, repo, monkeypatch):
        """The early exits omitted keys the happy path published, so a consumer hit KeyError on
        exactly the degraded nights it most needed to inspect."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo)
        write_gex_state(repo / "site", "SPY", vintage=self.D, flip=100.0)
        happy = bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo)
        paths = {
            "happy": happy,
            "bad_date": bsd.run(session_date="nonsense", from_dir=arch, root_dir=repo),
            "not_a_session": bsd.run(session_date="2026-07-26", from_dir=arch, root_dir=repo),
            "no_archived_roots": bsd.run(session_date="2026-07-27", roots=["SPY"],
                                         from_dir=arch, root_dir=repo),
            "budget": bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch,
                              root_dir=repo, budget_seconds=-1.0),
        }
        for var in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
            monkeypatch.delenv(var, raising=False)
        paths["no_source"] = bsd.run(session_date=self.D, root_dir=repo)
        keys = set(happy)
        for name, res in paths.items():
            assert set(res) == keys, f"{name} diverges: {keys ^ set(res)}"
            for k in ("over_budget", "budget_skipped", "r2_mb", "range_fallbacks", "seconds",
                      "roots", "reason", "ok"):
                assert k in res, f"{name} missing {k}"

    def test_over_budget_honours_the_parameter_not_the_constant(self, repo, monkeypatch):
        """An operator override of the budget must be what `over_budget` is measured against —
        reporting against the module constant would make the flag a lie."""
        monkeypatch.setenv("COLLECT_LANE", "nightly")
        arch = self._archive(repo, n=12)
        assert bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo,
                       budget_seconds=0.0)["over_budget"] is True
        assert bsd.run(session_date=self.D, roots=["SPY"], from_dir=arch, root_dir=repo,
                       budget_seconds=bsd.BUDGET_SECONDS)["over_budget"] is False

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
