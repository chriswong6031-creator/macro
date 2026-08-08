"""tests/test_prophet_live_evaluator.py — Prophet Live P0 gates G0.2, G0.3, G0.5, G0.6.

The */5 lane's job is to say one of six honest things about a name, or say nothing.
This file pins the four ways it could stop being honest:

  G0.2 LEDGER LAW      it writes no ``data/`` path and commits nothing, ever.
  G0.3 DEGRADATION     a stale pack darks the WHOLE artifact; a stale or missing
                       quote darks THAT NAME and leaves the rest live. No path
                       invents a state, and every dark carries a reason.
  G0.5 DEBOUNCE        one pass above a trigger is never a public state; two are; a
                       breach through the buffer on EITHER edge fades and a marginal
                       one does not; a re-cross pays two again.
  G0.6 VOCABULARY      fired / confirmed / refuted / validated / 证伪 appear nowhere
                       in the payload or the module.

EVERY TEST PINS ITS CLOCK. The ET window, the confirm cutoff and the last-completed-
session gate are all wall-clock logic, so a fixture with a bare date literal is a
scheduled red waiting for a Tuesday. ``NOW`` is passed explicitly everywhere and the
session-date fixtures are derived from it, never from ``datetime.now``.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.prophet_live import live_states as LS  # noqa: E402

#: 2026-07-29 is a Wednesday; 14:00Z is 10:00 ET, inside the window and before the
#: 15:30 confirm cutoff. Every other timestamp in this file is derived from it.
NOW = datetime(2026, 7, 29, 14, 0, tzinfo=timezone.utc)
SESSION = "2026-07-29"
#: The last COMPLETED session at NOW — what a fresh pack's as_of must equal.
LAST_SESSION = LS.last_completed_session(NOW)

CFG = LS.live_cfg({"prophet_live": {"debounce_passes": 2, "fade_buffer_pct": 0.5,
                                    "quote_max_age_min": 12,
                                    "confirm_window_start": "15:30"}})


def _at(hh: int, mm: int) -> datetime:
    """NOW's date at hh:mm ET, as UTC."""
    et = LS.et_clock(NOW).replace(hour=hh, minute=mm, second=0, microsecond=0)
    return et.astimezone(timezone.utc)


def near(trigger: float = 100.0, hi: float | None = None) -> dict:
    # band_lo_px 0 / band_hi_px +15% mirror what the pack publishes for a name that
    # was NOT buyable at the close (interval.in_probed_band explains the asymmetry).
    return {"state": "near", "center_buyable": False, "as_of_close": 95.0,
            "bar_date": LAST_SESSION, "probed": True, "buyable_in_band": True,
            "trigger_px": trigger, "fade_hi_px": hi,
            "band_lo_px": 0.0, "band_hi_px": 109.25}


def buyable(fade: float | None = 90.0, hi: float | None = 110.0) -> dict:
    return {"state": "buyable", "center_buyable": True, "as_of_close": 100.0,
            "bar_date": LAST_SESSION, "probed": True, "buyable_in_band": True,
            "fade_px": fade, "fade_hi_px": hi,
            "band_lo_px": 85.0, "band_hi_px": 115.0}


def no_lower_edge(hi: float | None = 110.0) -> dict:
    """A cross-class name whose buyable region has NO bound inside the band.

    What an append-semantics probe publishes when its own anchor at the as-of close is
    buyable (``armed_pack.probe_name`` bisects a lower edge only when the buyable run
    starts ABOVE grid[0]): ``buyable_in_band`` true, ``trigger_px`` absent. The evaluator
    reads named keys only, so this is exactly the entry it will be handed.
    """
    return {"state": "near", "center_buyable": False, "as_of_close": 95.0,
            "bar_date": LAST_SESSION, "probed": True, "buyable_in_band": True,
            "trigger_px": None, "fade_hi_px": hi,
            "band_lo_px": 0.0, "band_hi_px": 115.0}


def dormant() -> dict:
    return {"state": "dormant", "center_buyable": False, "as_of_close": 50.0,
            "bar_date": LAST_SESSION, "probed": True, "buyable_in_band": False,
            "band_lo_px": 0.0, "band_hi_px": 57.5}


def pack(names: dict, as_of: str | None = None) -> dict:
    return {"schema": "prophet_live.armed/v1", "as_of": as_of or LAST_SESSION,
            "built_at": "2026-07-28T22:30:00Z", "names": names,
            "meta": {"universe_n": 1742, "probed_n": len(names), "armed_n": len(names),
                     "skipped": {"probe_cap": 1176}}}


def quotes(**px: float) -> dict:
    return {t: {"price": v, "prev_close": v, "change_pct": 0.0, "ts_ms": None,
                "source": "quotes"} for t, v in px.items()}


def _run(p, q, prev=None, *, now=NOW, age=1.0):
    return LS.evaluate(p, q, prev, now=now, cfg=CFG, quote_asof="2026-07-29T13:58:00Z",
                       delay_min=15, quote_age_of=lambda _q: age)


# ─────────────────────────────────────────────────────────────────────────────
# G0.5 — debounce
# ─────────────────────────────────────────────────────────────────────────────

def test_one_pass_above_the_trigger_is_not_a_public_state():
    art = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0))
    st = art["states"]["AAA"]
    assert st["state"] == "near"                       # NOT forming
    assert st["internal"] == LS.CROSSING_UNCONFIRMED
    assert st["passes"] == 1
    assert st["state"] in LS.PUBLIC_STATES
    kinds = [e["kind"] for e in art["events"]]
    assert kinds == [LS.CROSSING_UNCONFIRMED]


def test_two_consecutive_passes_promote_to_forming():
    first = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0))
    second = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.5), first)
    st = second["states"]["AAA"]
    assert st["state"] == "forming" and st["passes"] == 2 and st["entered"] == "cross"
    assert [e["kind"] for e in second["events"]] == ["forming"]
    ev = second["events"][0]
    for field in ("ticker", "kind", "ts", "price", "quote_age_min", "passes"):
        assert field in ev, field
    assert ev["from"] == "near"


def test_a_drop_through_the_buffer_fades_and_resets_the_counter():
    a = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0))
    b = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), a)
    assert b["states"]["AAA"]["state"] == "forming"
    # Inside the 0.5% hysteresis band: still forming, counter preserved. The pass is
    # SUPPRESSED, not silent — it spools one internal marker so the suppression can be
    # measured, exactly as the three other debounced transitions do.
    c = _run(pack({"AAA": near(100.0)}), quotes(AAA=99.8), b)
    assert c["states"]["AAA"]["state"] == "forming" and c["states"]["AAA"]["passes"] == 2
    assert [e["kind"] for e in c["events"]] == [LS.FADE_UNCONFIRMED]
    # Through the buffer: faded, counter cleared.
    d = _run(pack({"AAA": near(100.0)}), quotes(AAA=99.0), c)
    assert d["states"]["AAA"]["state"] == "faded" and d["states"]["AAA"]["passes"] == 0
    assert [e["kind"] for e in d["events"]] == ["faded"]


def test_a_suppressed_fade_is_measurable_and_never_a_public_state():
    """The fourth internal marker (RULING, W-L0 gate 5).

    Every other debounced transition already spooled the pass it suppressed —
    crossing / at_risk / recovery — and the whole point of that set is measuring whether
    the debounce earns its keep. The fade path suppressed passes silently, so the one
    hysteresis nobody could audit was the one the reader sees most.
    """
    a = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0))
    b = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), a)
    assert b["states"]["AAA"]["state"] == "forming"
    c = _run(pack({"AAA": near(100.0)}), quotes(AAA=99.8), b)   # inside the 0.5% buffer
    st = c["states"]["AAA"]
    assert st["state"] == "forming", "a suppressed pass is not a public state change"
    assert st["internal"] == LS.FADE_UNCONFIRMED
    assert LS.FADE_UNCONFIRMED not in LS.PUBLIC_STATES
    assert LS.FADE_UNCONFIRMED in LS.EVENT_KINDS
    # `via` is a display field the P1 strip reads to choose "Fell back" vs "Ran past".
    # Nothing has faded, so it stays OFF the payload and rides the spool row instead.
    assert "via" not in st, st
    ev = [e for e in c["events"] if e["kind"] == LS.FADE_UNCONFIRMED]
    assert len(ev) == 1 and ev[0]["via"] == "drop" and ev[0]["from"] == "forming"
    # One row per marker per name per session: an oscillating price must not drown the
    # very measurement the marker exists for. Gate 2 DEBOUNCES the fade rather than
    # holding inside the buffer forever, so a second CONSECUTIVE failing pass is a real
    # fade now and cannot be the dedup probe. The honest probe is the oscillation the
    # marker was written for: a holding pass (which clears the failing counter) and then
    # a fresh suppressed one, which must NOT spool the marker a second time.
    d = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), c)
    assert d["states"]["AAA"]["state"] == "forming" and d["states"]["AAA"]["fails"] == 0
    e = _run(pack({"AAA": near(100.0)}), quotes(AAA=99.75), d)
    assert e["states"]["AAA"]["state"] == "forming"
    assert e["states"]["AAA"]["internal"] == LS.FADE_UNCONFIRMED
    assert [ev["kind"] for ev in e["events"]] == []
    # Two consecutive failing passes ARE persistent, and gate 2 fades on the second.
    f = _run(pack({"AAA": near(100.0)}), quotes(AAA=99.7), e)
    assert f["states"]["AAA"]["state"] == "faded" and f["states"]["AAA"]["via"] == "drop"


def test_a_re_cross_pays_two_fresh_passes():
    a = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0))
    b = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), a)
    faded = _run(pack({"AAA": near(100.0)}), quotes(AAA=99.0), b)
    assert faded["states"]["AAA"]["state"] == "faded"
    one = _run(pack({"AAA": near(100.0)}), quotes(AAA=100.5), faded)
    assert one["states"]["AAA"]["state"] == "near"      # one pass is not enough again
    assert one["states"]["AAA"]["passes"] == 1
    two = _run(pack({"AAA": near(100.0)}), quotes(AAA=100.5), one)
    assert two["states"]["AAA"]["state"] == "forming"


def test_a_new_session_does_not_inherit_yesterdays_debounce():
    a = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0))
    tomorrow = NOW + timedelta(days=1)
    fresh = _run(pack({"AAA": near(100.0)}, as_of=LS.last_completed_session(tomorrow)),
                 quotes(AAA=101.0), a, now=tomorrow)
    assert fresh["states"]["AAA"]["passes"] == 1        # not 2
    assert fresh["states"]["AAA"]["state"] == "near"
    assert fresh["meta"]["session_et"] != a["meta"]["session_et"]


def test_above_the_upper_edge_is_not_forming():
    """The don't-chase case: past fade_hi the gate tops out, so nothing is forming."""
    a = _run(pack({"AAA": near(100.0, hi=105.0)}), quotes(AAA=106.0))
    b = _run(pack({"AAA": near(100.0, hi=105.0)}), quotes(AAA=106.0), a)
    assert b["states"]["AAA"]["state"] != "forming"


def test_a_formed_name_that_runs_away_fades_via_overrun_not_drop():
    """M3: `faded` alone claimed "fell through the buffer" for a name that ran UP.

    Same public state, but the reason axis matters: P1 display reads a drop as "it
    came back to you" and an overrun as "don't chase", and the ledger cannot separate
    the two populations without it.

    Both breaches here are DECISIVE — over `fade_hi_px * 1.005`, under
    `trigger * 0.995` — so the axis is read off the pass that actually publishes
    `faded`. A marginal breach no longer publishes one at all (W-L0 gate 2); that is
    the next test, and 105.5 against a 105.0 edge used to live in THIS one.
    """
    a = _run(pack({"AAA": near(100.0, hi=105.0)}), quotes(AAA=101.0))
    b = _run(pack({"AAA": near(100.0, hi=105.0)}), quotes(AAA=101.0), a)
    assert b["states"]["AAA"]["state"] == "forming"
    up = _run(pack({"AAA": near(100.0, hi=105.0)}), quotes(AAA=106.0), b)   # > 105.525
    assert up["states"]["AAA"]["state"] == "faded" and up["states"]["AAA"]["via"] == "overrun"
    assert up["events"][0]["via"] == "overrun"
    down = _run(pack({"AAA": near(100.0, hi=105.0)}), quotes(AAA=98.0), b)  # < 99.5
    assert down["states"]["AAA"]["state"] == "faded" and down["states"]["AAA"]["via"] == "drop"
    assert down["events"][0]["via"] == "drop"


def test_a_marginal_overrun_holds_the_state_and_fades_only_on_a_second_failing_pass():
    """W-L0 gate 2 (CSP-R2): the hysteresis buffer is TWO-SIDED, not lower-edge only.

    105.5 against a 105.0 upper edge is +0.48% — INSIDE the 0.5% buffer — and it used
    to publish `faded` on ONE pass, because only the band below the trigger preserved
    the state. A name the same distance UNDER the trigger held. That asymmetry is the
    killed 1-tick public flip, on the edge P1 reads as "don't chase", and this test is
    the one that used to assert the defect.
    """
    entry = near(100.0, hi=105.0)
    a = _run(pack({"AAA": entry}), quotes(AAA=101.0))
    b = _run(pack({"AAA": entry}), quotes(AAA=101.0), a)
    assert b["states"]["AAA"]["state"] == "forming" and b["states"]["AAA"]["passes"] == 2
    # One marginal overrun: the PUBLIC state holds, and the suppression is COUNTABLE —
    # gate 5's fourth marker, which until now only the drop edge could earn. A
    # suppression nobody records is a suppression nobody can measure, and the upper edge
    # was exactly the half of the buffer no spool row could see.
    c = _run(pack({"AAA": entry}), quotes(AAA=105.5), b)          # +0.48% over the edge
    st = c["states"]["AAA"]
    assert st["state"] == "forming", "a sub-buffer overrun published a 1-tick fade"
    assert st["passes"] == 2 and st["fails"] == 1
    assert "via" not in st, "nothing faded, so there is no breach side to name"
    assert st["internal"] == LS.FADE_UNCONFIRMED
    ev = [e for e in c["events"] if e["kind"] == LS.FADE_UNCONFIRMED]
    assert len(ev) == 1 and ev[0]["via"] == "overrun" and ev[0]["from"] == "forming"
    # A SECOND consecutive failing pass is not marginal any more — it is persistent.
    d = _run(pack({"AAA": entry}), quotes(AAA=105.4), c)
    assert d["states"]["AAA"]["state"] == "faded" and d["states"]["AAA"]["via"] == "overrun"
    assert d["states"]["AAA"]["passes"] == 0
    assert [e["kind"] for e in d["events"]] == ["faded"]
    # And the episode spools ONE faded row: a later failing pass re-publishes the same
    # public state, so the ledger is not handed the same fade twice.
    e = _run(pack({"AAA": entry}), quotes(AAA=105.45), d)
    assert e["states"]["AAA"]["state"] == "faded"
    assert e["events"] == []


def test_a_cross_name_does_not_flap_on_a_sub_buffer_straddle_of_either_edge():
    """The cross path's twin of the board path's four-cent straddle (CSP-R2).

    A price oscillating across an edge inside the buffer must publish exactly ONE
    public state, and that has to be true of the UPPER edge as well as the lower —
    the upper one was the hole. Neither series may put a second state on the strip.
    """
    entry = near(100.0, hi=105.0)
    for series in ((100.2, 99.8), (104.8, 105.2)):     # straddles lo, then hi
        a = _run(pack({"AAA": entry}), quotes(AAA=101.0))
        prev = _run(pack({"AAA": entry}), quotes(AAA=101.0), a)
        assert prev["states"]["AAA"]["state"] == "forming", series
        states: list[str] = []
        kinds: list[str] = []
        for n in range(6):
            prev = _run(pack({"AAA": entry}), quotes(AAA=series[n % 2]), prev)
            states.append(prev["states"]["AAA"]["state"])
            kinds.extend(ev["kind"] for ev in prev["events"])
        assert set(states) == {"forming"}, (series, states)
        # Nothing PUBLIC moved, and the six passes spool exactly ONE row: the first
        # suppressed pass earns gate 5's marker and the dedup swallows the rest, so an
        # oscillating price can neither flap the strip nor drown its own measurement.
        assert kinds == [LS.FADE_UNCONFIRMED], (series, kinds)


def test_the_cross_counter_survives_a_marginal_breach_of_either_edge():
    """The hold preserves `passes`, so a name that dips over an edge and comes back is
    not made to re-earn a cross it already banked — and the SINCE clock does not
    restart, because the reader was never told anything new."""
    entry = near(100.0, hi=105.0)
    a = _run(pack({"AAA": entry}), quotes(AAA=101.0), now=_at(10, 0))
    b = _run(pack({"AAA": entry}), quotes(AAA=101.0), a, now=_at(10, 5))
    assert b["states"]["AAA"]["state"] == "forming" and b["states"]["AAA"]["passes"] == 2
    since = b["states"]["AAA"]["since_ts"]
    over = _run(pack({"AAA": entry}), quotes(AAA=105.5), b, now=_at(10, 10))   # above hi
    under = _run(pack({"AAA": entry}), quotes(AAA=99.8), b, now=_at(10, 10))   # below lo
    for st in (over["states"]["AAA"], under["states"]["AAA"]):
        assert st["state"] == "forming" and st["passes"] == 2 and st["fails"] == 1
        assert st["since_ts"] == since
    # Back inside the interval: the banked passes carry, so it is still forming.
    back = _run(pack({"AAA": entry}), quotes(AAA=102.0), over, now=_at(10, 15))
    st = back["states"]["AAA"]
    assert st["state"] == "forming" and st["passes"] == 3 and st["fails"] == 0
    assert st["since_ts"] == since


# ─────────────────────────────────────────────────────────────────────────────
# B2 — outside the probed band the pack knows nothing
# ─────────────────────────────────────────────────────────────────────────────

def test_a_board_name_gapping_below_its_band_reports_no_verdict_not_forming():
    """The reproduced fabrication: -30% satisfied "no breach recorded" and read forming.

    UNKNOWN, not dark (W-L0 gate 5): the quote arrived and it is fresh, so counting this
    under ``dark_counts`` would feed the strip's "N could not be read this pass" footer
    and its half-the-names cliff with a name that read perfectly.
    """
    art = _run(pack({"BBB": buyable()}), quotes(BBB=70.0))     # band_lo_px 85.0
    assert art["states"]["BBB"] == {"state": "unknown", "reason": "out_of_band",
                                    "price": 70.0, "quote_age_min": 1.0}
    assert art["meta"]["dark_counts"] == {}
    assert art["meta"]["unknown_counts"] == {"out_of_band": 1}


def test_a_name_with_no_fade_edge_can_still_leave_its_band():
    """fade_px None used to make at_risk unreachable at ANY price, forever."""
    entry = buyable(fade=None, hi=None)
    inside = _run(pack({"BBB": entry}), quotes(BBB=90.0))
    assert inside["states"]["BBB"]["state"] == "forming"
    outside = _run(pack({"BBB": entry}), quotes(BBB=84.0))     # below band_lo_px 85.0
    assert outside["states"]["BBB"]["state"] == "unknown"
    assert outside["states"]["BBB"]["reason"] == "out_of_band"


def test_a_runaway_past_the_band_top_reports_no_verdict_rather_than_extrapolating():
    """+25% with fade_hi None read forming, where the real gate says False at +25%."""
    entry = near(100.0, hi=None)                              # band_hi_px 109.25
    ok = _run(pack({"AAA": entry}), quotes(AAA=108.0))
    assert ok["states"]["AAA"]["state"] == "near"              # 1 pass, in band
    past = _run(pack({"AAA": entry}), quotes(AAA=118.75))      # +25% on a 95 close
    assert past["states"]["AAA"]["state"] == "unknown"
    assert past["states"]["AAA"]["reason"] == "out_of_band"


def test_a_non_buyable_name_below_its_close_reports_no_verdict():
    """W-L0 gate 5: `dormant`/`near` never assert over the never-probed down-region.

    A cross-class span starts AT the as-of close and runs UP, so the pack measured
    nothing below it. The 0 in ``band_lo_px`` is the published span's sentinel, not a
    floor, and it used to be read as permission to keep answering down there — the
    argument being that the centre verdict settles the whole region for "a gate whose
    product structure is a cross UP". The gate's buyable set is an INTERVAL (this pack
    publishes an upper edge and an ``irregular`` state), so it does not.
    """
    art = _run(pack({"AAA": near(100.0)}), quotes(AAA=40.0))   # as_of_close 95.0
    st = art["states"]["AAA"]
    assert st["state"] == "unknown" and st["reason"] == "below_probe_floor"
    assert st["price"] == 40.0
    assert art["meta"]["unknown_counts"] == {"below_probe_floor": 1}
    assert art["meta"]["dark_counts"] == {}                    # the tape was fine
    assert "cross_level_px" not in st, "a non-verdict hangs no level"
    assert "since_ts" not in st, "a non-verdict has nothing to time"
    # AT the close it is measured again, so the verdict comes back.
    at_close = _run(pack({"AAA": near(100.0)}), quotes(AAA=95.0))
    assert at_close["states"]["AAA"]["state"] == "near"


def test_a_dormant_name_below_its_close_reports_no_verdict():
    """The gate names `dormant` specifically: nothing in the band is buyable is a claim
    about the BAND, and below the close there is no band."""
    art = _run(pack({"CCC": dormant()}), quotes(CCC=45.0))     # as_of_close 50.0
    assert art["states"]["CCC"]["state"] == "unknown"
    assert art["states"]["CCC"]["reason"] == "below_probe_floor"
    still = _run(pack({"CCC": dormant()}), quotes(CCC=52.0))   # inside the swept span
    assert still["states"]["CCC"]["state"] == "dormant"


def test_a_dip_out_of_the_swept_band_does_not_restart_the_since_clock():
    """`unknown` is a non-verdict, so it chains ``prior_public`` exactly as dark does.

    Without the read-through, a name that dips outside its band for one pass and returns
    to the SAME public state would restart the SINCE column — the clock would time the
    round trip instead of the state, which is what P1 prints.
    """
    a = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), now=_at(10, 0))
    assert a["states"]["BBB"]["state"] == "forming"
    since = a["states"]["BBB"]["since_ts"]
    gap = _run(pack({"BBB": buyable()}), quotes(BBB=70.0), a, now=_at(10, 5))
    assert gap["states"]["BBB"]["state"] == "unknown"
    assert "since_ts" not in gap["states"]["BBB"]
    assert gap["states"]["BBB"]["prior_public"] == "forming"
    back = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), gap, now=_at(10, 10))
    assert back["states"]["BBB"]["state"] == "forming"
    assert back["states"]["BBB"]["since_ts"] == since


def test_a_name_that_crossed_today_still_fades_below_its_close():
    """The floor rule must not delete a published cross's own fall-back.

    `faded` is arithmetic over the level this lane published and a price it measured,
    not a claim about the gate's verdict at today's price — and a trigger sitting
    fractionally above the close is the common case, so darkening the region below the
    close would take the "Fell back" row away from most names that ever fade.
    """
    a = _run(pack({"AAA": near(96.0)}), quotes(AAA=96.5))      # as_of_close 95.0
    b = _run(pack({"AAA": near(96.0)}), quotes(AAA=96.5), a)
    assert b["states"]["AAA"]["state"] == "forming"
    c = _run(pack({"AAA": near(96.0)}), quotes(AAA=94.0), b)   # below the close
    assert c["states"]["AAA"]["state"] == "faded" and c["states"]["AAA"]["via"] == "drop"


def test_a_name_whose_interval_holds_is_never_dormant_for_want_of_a_lower_edge():
    """W-L0 gate 5(b): the live lie. `dormant` used to fire on `lo is None`.

    A cross-class name whose buyable region has no bound inside the band is buyable from
    the probe floor up — its interval HOLDS at the live price — and the branch keyed on
    `lo is None` ran BEFORE the one that asks whether it holds, so the strip said
    "nothing forming" about a name that was forming. `dormant` means one thing only:
    nothing in the armed band is buyable.
    """
    entry = no_lower_edge()
    one = _run(pack({"AAA": entry}), quotes(AAA=100.0))       # close 95, fade_hi 110
    assert one["states"]["AAA"]["state"] == "near"            # 1 pass — debounce, not dormant
    assert one["states"]["AAA"]["internal"] == LS.CROSSING_UNCONFIRMED
    two = _run(pack({"AAA": entry}), quotes(AAA=100.0), one)
    assert two["states"]["AAA"]["state"] == "forming"
    assert two["states"]["AAA"]["entered"] == "cross"
    # No lower edge exists, so no cross level is published — a level only exists where
    # the interval has a bound (module docstring: LEVELS).
    assert "cross_level_px" not in two["states"]["AAA"]
    assert two["states"]["AAA"]["fade_hi_px"] == 110.0


def test_a_name_with_no_lower_edge_still_leaves_its_interval_upward():
    """The other half of the same branch: with `lo` None the hysteresis test used to
    evaluate `float(None)`, so a name that ran past its upper edge died in the handler
    and shipped `dark` with an eval_error rather than the overrun it was."""
    entry = no_lower_edge(hi=110.0)
    a = _run(pack({"AAA": entry}), quotes(AAA=100.0))
    b = _run(pack({"AAA": entry}), quotes(AAA=100.0), a)
    assert b["states"]["AAA"]["state"] == "forming"
    up = _run(pack({"AAA": entry}), quotes(AAA=111.0), b)     # over fade_hi, inside band
    st = up["states"]["AAA"]
    assert st["state"] == "faded" and st["via"] == "overrun"
    assert "reason" not in st, st


def test_an_unbounded_interval_does_not_extrapolate_below_the_probe_floor():
    """Where (a) and (b) meet: with no lower edge the interval reads as buyable all the
    way down, so the floor check has to be asked BEFORE membership or the lane would
    publish `forming` off a region the probe never swept."""
    entry = no_lower_edge()
    a = _run(pack({"AAA": entry}), quotes(AAA=90.0))          # below the 95 close
    b = _run(pack({"AAA": entry}), quotes(AAA=90.0), a)
    assert b["states"]["AAA"]["state"] == "unknown"
    assert b["states"]["AAA"]["reason"] == "below_probe_floor"


def test_a_pack_without_band_fields_still_evaluates():
    """Schema skew must not dark a whole universe — nor unknown one.

    A pack built before the band fields published no span, so there is no floor to name
    and `probe_floor` refuses to invent one: the old behaviour stands rather than
    declaring every name below its close unmeasured on a schema skew.
    """
    entry = {k: v for k, v in near(100.0).items()
             if k not in ("band_lo_px", "band_hi_px")}
    art = _run(pack({"AAA": entry}), quotes(AAA=101.0))
    assert art["states"]["AAA"]["state"] == "near"
    low = _run(pack({"AAA": entry}), quotes(AAA=40.0))
    assert low["states"]["AAA"]["state"] == "near"
    assert low["meta"]["unknown_counts"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# Board members
# ─────────────────────────────────────────────────────────────────────────────

def test_a_board_name_holding_reads_forming_on_its_first_pass():
    """Pinned change: `passes` is now a COUNT on the board path too, not None.

    The board path used to carry `passes: None` because it had no debounce at all —
    which is precisely the M2 defect. It now counts consecutive holds so recovery from
    at_risk can be debounced symmetrically.
    """
    art = _run(pack({"BBB": buyable()}), quotes(BBB=100.0))
    st = art["states"]["BBB"]
    assert st["state"] == "forming" and st["entered"] == "board"
    assert st["passes"] == 1 and st["fails"] == 0


def test_a_decisive_breach_of_the_fade_level_is_at_risk_immediately():
    """Past the hysteresis buffer there is nothing marginal to debounce."""
    art = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=85.5))
    st = art["states"]["BBB"]
    assert st["state"] == "at_risk" and st["via"] == "drop" and st["fails"] == 1
    ev = art["events"][0]
    assert ev["kind"] == "at_risk" and ev["via"] == "drop" and ev["entered"] == "board"


def test_a_board_name_does_not_flap_on_a_four_cent_straddle():
    """M2 / CSP-R2: 90.02 vs 89.98 on a 90.00 fade level must not flip the state.

    This is the reviewer's reproduction. Before the board-path debounce every pass
    published the opposite state, on a name that is already on a live board.
    """
    prev = None
    states: list[str] = []
    kinds: list[str] = []
    for n in range(6):
        px = 90.02 if n % 2 == 0 else 89.98
        art = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=px), prev)
        states.append(art["states"]["BBB"]["state"])
        kinds.extend(e["kind"] for e in art["events"])
        prev = art
    # The PUBLIC state never moves, however many times the price crosses the level.
    assert set(states) == {"forming"}, states
    # And the spool gets one row for the board reading plus ONE internal marker for
    # the whole oscillation — a row per tick would drown the debounce measurement.
    assert kinds == ["forming", LS.AT_RISK_UNCONFIRMED], kinds


def test_two_consecutive_marginal_failing_passes_do_publish_at_risk():
    """Debounce delays a marginal breach; it must not swallow a persistent one."""
    a = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=100.0))
    b = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=89.98), a)
    assert b["states"]["BBB"]["state"] == "forming"          # 1 failing pass
    assert b["states"]["BBB"]["internal"] == LS.AT_RISK_UNCONFIRMED
    c = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=89.97), b)
    assert c["states"]["BBB"]["state"] == "at_risk"          # 2 failing passes
    assert c["states"]["BBB"]["fails"] == 2


def test_a_board_name_first_seen_breaching_is_not_handed_a_free_forming():
    """W-L0: the optimistic first-pass default.

    The debounce holds a state the reader ALREADY HAS; on the day's first pass there is
    none, so defaulting to `forming` published the opposite of the one thing this pass
    measured. The side rides along or the card chip would call an overrun a fall-back.
    """
    art = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=89.98))
    st = art["states"]["BBB"]
    assert st["state"] == "at_risk" and st["via"] == "drop"
    assert st["fails"] == 1                                  # marginal, not decisive
    assert "internal" not in st, "the marker names a SUPPRESSED pass; this one published"
    assert [e["kind"] for e in art["events"]] == ["at_risk"]
    over = _run(pack({"BBB": buyable(fade=90.0, hi=110.0)}), quotes(BBB=110.2))
    assert over["states"]["BBB"]["state"] == "at_risk"
    assert over["states"]["BBB"]["via"] == "overrun"


def test_a_dark_gap_does_not_hand_a_breaching_board_name_a_free_forming():
    """The same lie, one pass later: `prev_state` is "dark" after a quote hiccup, which
    is not in (forming, at_risk), so the default fired there too. Read the last state
    that reported a verdict instead."""
    a = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=89.98))
    assert a["states"]["BBB"]["state"] == "at_risk"
    gap = _run(pack({"BBB": buyable(fade=90.0)}), {}, a)      # quote goes missing
    assert gap["states"]["BBB"]["state"] == "dark"
    back = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=89.98), gap)
    assert back["states"]["BBB"]["state"] == "at_risk"
    assert back["states"]["BBB"]["internal"] == LS.AT_RISK_UNCONFIRMED


def test_recovery_from_at_risk_is_debounced_symmetrically():
    a = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=85.0))
    assert a["states"]["BBB"]["state"] == "at_risk"
    b = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=90.05), a)   # marginal
    assert b["states"]["BBB"]["state"] == "at_risk"
    assert b["states"]["BBB"]["internal"] == LS.RECOVERY_UNCONFIRMED
    c = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=90.06), b)
    assert c["states"]["BBB"]["state"] == "forming"
    # A decisive move back inside resolves in one pass.
    d = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=100.0), a)
    assert d["states"]["BBB"]["state"] == "forming"


def test_a_board_name_running_past_the_top_is_at_risk_via_overrun():
    """The not-topped veto bites on the way up too — at_risk, not forming."""
    art = _run(pack({"BBB": buyable(hi=110.0)}), quotes(BBB=112.0))
    st = art["states"]["BBB"]
    assert st["state"] == "at_risk" and st["via"] == "overrun"


def test_dormant_names_produce_no_events():
    art = _run(pack({"CCC": dormant()}), quotes(CCC=50.0))
    assert art["states"]["CCC"]["state"] == "dormant"
    assert art["events"] == []


# ─────────────────────────────────────────────────────────────────────────────
# The level on the row — P1's CROSS LEVEL column
#
# The number the strip prints is the pack's armed edge, and the SAME edge means
# opposite things on the two kinds of row: a cross level for a name off tonight's
# board (`cross_level_px`), a fade level for a name on it (`fade_px`). These pin the
# honest pair, its absence wherever there is no level, that the level is never
# re-rounded into a price the gate would reject, and that the bare name `cross_px` —
# the LEDGER's field, a price rather than a level — never appears in this payload.
# ─────────────────────────────────────────────────────────────────────────────

def test_a_cross_candidate_publishes_the_armed_trigger_as_cross_level_px():
    """The lowest provisional close that flips the gate true — what the strip prints."""
    a = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0))
    b = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), a)
    for art, state in ((a, "near"), (b, "forming")):
        st = art["states"]["AAA"]
        assert st["state"] == state
        assert st["cross_level_px"] == 100.0, st
        assert "fade_px" not in st, "a cross row must not carry a board name's level"


def test_a_board_name_publishes_the_same_edge_as_fade_px_not_cross_level_px():
    """Below it TONIGHT'S VERDICT flips false — it is not a cross level for that row."""
    art = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=100.0))
    st = art["states"]["BBB"]
    assert st["state"] == "forming" and st["entered"] == "board"
    assert st["fade_px"] == 90.0, st
    assert "cross_level_px" not in st, "the board row's fade level was published as a cross"
    # And on the way out, where the number is the one the reader most needs.
    risk = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=85.0))["states"]["BBB"]
    assert risk["state"] == "at_risk" and risk["fade_px"] == 90.0
    assert "cross_level_px" not in risk


def test_the_column_label_comes_off_key_presence_with_nothing_re_derived():
    """The two lower-edge keys are mutually exclusive, so presence IS the label."""
    art = _run(pack({"AAA": near(100.0), "BBB": buyable(fade=90.0)}),
               quotes(AAA=101.0, BBB=100.0))
    labels = {}
    for tkr, st in art["states"].items():
        keys = {"cross_level_px", "fade_px"} & set(st)
        assert len(keys) == 1, (tkr, st)
        labels[tkr] = keys.pop()
    assert labels == {"AAA": "cross_level_px", "BBB": "fade_px"}


def test_the_upper_edge_rides_along_as_fade_hi_px_and_is_absent_when_unbounded():
    """What a ``via:"overrun"`` row ran past — the pack's own name for the number."""
    over = _run(pack({"AAA": near(100.0, hi=105.0)}), quotes(AAA=101.0))["states"]["AAA"]
    assert over["fade_hi_px"] == 105.0 and over["cross_level_px"] == 100.0
    board = _run(pack({"BBB": buyable(hi=110.0)}), quotes(BBB=100.0))["states"]["BBB"]
    assert board["fade_hi_px"] == 110.0
    # Unbounded above inside the band ⇒ no key, never 0 and never null-as-a-number.
    open_top = _run(pack({"AAA": near(100.0, hi=None)}), quotes(AAA=101.0))["states"]["AAA"]
    assert "fade_hi_px" not in open_top and open_top["cross_level_px"] == 100.0


def test_no_level_key_when_the_pack_armed_none():
    """Absent, never 0 or null-as-a-number — the two are different claims."""
    # Nothing in the band is buyable: there is no crossable level to name.
    cold = _run(pack({"CCC": dormant()}), quotes(CCC=50.0))["states"]["CCC"]
    assert cold["state"] == "dormant"
    for key in ("cross_level_px", "fade_px", "fade_hi_px"):
        assert key not in cold, key
    # A board name unbounded BELOW inside the band has no lower edge — and must not
    # borrow the cross vocabulary to say so.
    no_lo = _run(pack({"BBB": buyable(fade=None, hi=110.0)}),
                 quotes(BBB=100.0))["states"]["BBB"]
    assert no_lo["state"] == "forming"
    assert "fade_px" not in no_lo and "cross_level_px" not in no_lo
    assert no_lo["fade_hi_px"] == 110.0        # the edge it DOES have still ships
    # A level only exists where the INTERVAL does. `buyable_in_band: False` says no
    # probed price in the band is buyable, so a surviving edge field (a schema skew
    # across pack vintages is the reachable route) must not be republished as a level
    # the reader can act on — "below 90 the verdict flips" against "the verdict is
    # false everywhere in band" is a contradiction, and the pack wins.
    contradiction = {**buyable(fade=90.0, hi=110.0), "buyable_in_band": False}
    stale_edge = _run(pack({"BBB": contradiction}), quotes(BBB=100.0))["states"]["BBB"]
    assert stale_edge["state"] != "dark"       # still evaluated, just levelless
    for key in ("cross_level_px", "fade_px", "fade_hi_px"):
        assert key not in stale_edge, key


def test_a_row_with_no_verdict_carries_no_level_whatever_the_reason():
    """A row that reports no verdict has nothing to hang a level on (G0.3)."""
    p = pack({"AAA": near(100.0),                       # no quote at all
              "BBB": buyable(),                         # gapped below its band
              "IRR": {"state": "irregular", "center_buyable": True, "as_of_close": 10.0,
                      "probed": True, "buyable_in_band": None},
              "UNP": {"state": "dormant", "center_buyable": False, "as_of_close": 10.0,
                      "probed": False, "skip": "probe_cap", "buyable_in_band": True,
                      "trigger_px": 11.0, "fade_hi_px": 12.0}})
    art = _run(p, quotes(BBB=70.0, IRR=10.0, UNP=11.5))
    assert "UNP" not in art["states"], "an unprobed name is not evaluated at all"
    stale = LS.evaluate(pack({"AAA": near(100.0)}), quotes(AAA=101.0), None, now=NOW,
                        cfg=CFG, quote_asof="x", delay_min=15,
                        quote_age_of=lambda _q: 45.0)
    rows = list(art["states"].values()) + list(stale["states"].values())
    reasons = {r["reason"] for r in rows}
    assert reasons == {"no_quote", "out_of_band", "irregular_gate", "stale_quote"}, reasons
    for st in rows:
        assert st["state"] in LS.NO_VERDICT_STATES
        for key in ("cross_level_px", "fade_px", "fade_hi_px"):
            assert key not in st, (st, key)
    # …and the two are kept apart: only a LANE failure is dark (module: UNKNOWN IS NOT
    # DARK), so the strip's "could not be read" count never absorbs a coverage limit.
    by_reason = {r["reason"]: r["state"] for r in rows}
    assert by_reason == {"no_quote": "dark", "stale_quote": "dark",
                         "irregular_gate": "dark", "out_of_band": "unknown"}, by_reason


def test_the_level_is_republished_verbatim_never_re_rounded():
    """A published level must be a price the GATE accepts, so it ships exactly as armed.

    The pack already rounds each edge INTO the buyable region at 4 dp, and publishes
    the full-precision bisected value when a rounding step would cross the as-of close
    (``armed_pack._side_safe_round``). Rounding again here can only move a level the
    wrong way: ``round(100.00004, 4)`` is 100.0, a tenth of a cent BELOW the trigger,
    which is a price the gate rejects — printed as the level to act on.
    """
    from engine.prophet_live import interval as INTERVAL

    cross = near(100.00004, hi=105.00006)
    st = _run(pack({"AAA": cross}), quotes(AAA=101.0))["states"]["AAA"]
    assert st["cross_level_px"] == 100.00004 and st["fade_hi_px"] == 105.00006
    # The invariant behind the digits, asserted against the ONE interval reader.
    assert INTERVAL.interval_contains(cross, st["cross_level_px"]) is True
    assert INTERVAL.interval_contains(cross, st["fade_hi_px"]) is True

    board = buyable(fade=90.00004, hi=110.00006)
    bst = _run(pack({"BBB": board}), quotes(BBB=100.0))["states"]["BBB"]
    assert bst["fade_px"] == 90.00004 and bst["fade_hi_px"] == 110.00006
    assert INTERVAL.interval_contains(board, bst["fade_px"]) is True
    assert INTERVAL.interval_contains(board, bst["fade_hi_px"]) is True
    # `price` still rounds to the pack's display precision — that is a QUOTE, not a
    # threshold, and rounding it cannot misstate a level.
    assert bst["price"] == 100.0


def test_every_non_dark_row_with_an_interval_carries_exactly_one_lower_level():
    """The level is a fact about the pack, so it cannot depend on which branch ran."""
    p = pack({"AAA": near(100.0, hi=105.0), "BBB": buyable(fade=90.0), "CCC": dormant()})
    a = _run(p, quotes(AAA=101.0, BBB=100.0, CCC=50.0))     # near / forming / dormant
    b = _run(p, quotes(AAA=101.0, BBB=85.0, CCC=50.0), a)   # forming / at_risk
    c = _run(p, quotes(AAA=99.0, BBB=100.0, CCC=50.0), b)   # faded / forming
    seen: set[str] = set()
    for art in (a, b, c):
        for tkr, st in art["states"].items():
            seen.add(st["state"])
            keys = {"cross_level_px", "fade_px"} & set(st)
            want = set() if tkr == "CCC" else {"fade_px" if tkr == "BBB" else "cross_level_px"}
            assert keys == want, (tkr, st)
    assert seen == {"near", "forming", "faded", "at_risk", "dormant"}, seen


def test_no_payload_field_is_named_cross_px_and_no_level_reaches_an_event_row():
    """``cross_px`` belongs to the LEDGER, where it is a price — never to this artifact.

    ``reconcile_prophet_live`` sets ``cross_px = first_px``, the price the tape actually
    printed at the first cross, and leans on it in ``FIRST_WINS`` and in the
    ``close_vs_cross_pct``/``fill_vs_cross_pct`` derivations. The armed LEVEL therefore
    ships as ``cross_level_px`` (operator ruling 2026-07-30): the two names no longer
    collide, so a join across artifact and ledger cannot compare a threshold to a fill.
    Two ways that could regress — reviving the bare name here, or a wholesale
    ``{**new}`` in ``transitions`` pushing the level into the spool the ledger reads —
    and this pins both.
    """
    a = _run(pack({"AAA": near(100.0, hi=105.0), "BBB": buyable(fade=90.0)}),
             quotes(AAA=101.0, BBB=85.0))
    b = _run(pack({"AAA": near(100.0, hi=105.0), "BBB": buyable(fade=90.0)}),
             quotes(AAA=101.0, BBB=85.0), a)
    # The level really is being published, or the rest of this proves nothing.
    assert b["states"]["AAA"]["cross_level_px"] == 100.0
    for art in (a, b):
        assert '"cross_px"' not in json.dumps(art), "the ledger's field name is back"
    evs = a["events"] + b["events"]
    assert evs, "fixture produced no events"
    for ev in evs:
        for key in ("cross_level_px", "fade_px", "fade_hi_px"):
            assert key not in ev, (ev, key)
        assert ev["price"] in (101.0, 85.0)      # the row still carries the TAPE price


# ─────────────────────────────────────────────────────────────────────────────
# The confirm window
# ─────────────────────────────────────────────────────────────────────────────

def test_confirming_into_close_only_from_the_cutoff_and_only_while_conditions_hold():
    early = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), now=_at(15, 0))
    assert "confirming_into_close" not in early["states"]["BBB"]
    late = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), now=_at(15, 45))
    assert late["states"]["BBB"]["confirming_into_close"] is True
    assert "confirming_into_close" in [e["kind"] for e in late["events"]]
    # Conditions no longer met => no flag, however late it is.
    broken = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=86.0), now=_at(15, 45))
    assert "confirming_into_close" not in broken["states"]["BBB"]


def test_confirming_into_close_never_fires_on_an_unconfirmed_cross():
    """M4: the flag used to key off `holds` alone, so a single 15:31 print produced a
    confirming-into-close event for a cross the lane had not published yet."""
    one = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), now=_at(15, 45))
    st = one["states"]["AAA"]
    assert st["state"] == "near" and st["internal"] == LS.CROSSING_UNCONFIRMED
    assert "confirming_into_close" not in st
    assert "confirming_into_close" not in [e["kind"] for e in one["events"]]
    two = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), one, now=_at(15, 50))
    assert two["states"]["AAA"]["state"] == "forming"
    assert two["states"]["AAA"]["confirming_into_close"] is True


def test_every_event_row_says_whether_it_was_a_cross_or_a_board_name():
    """M5: without `entered` the ledger's headline population is non-crosses.

    The P0 receipt was ~108 board first-pass rows against 2 real intraday crosses.
    """
    a = _run(pack({"AAA": near(100.0), "BBB": buyable(fade=90.0)}),
             quotes(AAA=101.0, BBB=85.0))
    b = _run(pack({"AAA": near(100.0), "BBB": buyable(fade=90.0)}),
             quotes(AAA=101.0, BBB=85.0), a)
    by_kind = {e["kind"]: e for e in a["events"] + b["events"]}
    assert by_kind["at_risk"]["entered"] == "board"
    assert by_kind["crossing_unconfirmed"]["entered"] == "cross"
    assert by_kind["forming"]["entered"] == "cross"
    for ev in a["events"] + b["events"]:
        assert ev["entered"] in ("cross", "board"), ev


def test_the_flag_fires_once_not_on_every_later_pass():
    a = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), now=_at(15, 35))
    b = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), a, now=_at(15, 40))
    assert "confirming_into_close" in [e["kind"] for e in a["events"]]
    assert "confirming_into_close" not in [e["kind"] for e in b["events"]]


# ─────────────────────────────────────────────────────────────────────────────
# since_ts — the P1 SINCE column (design spec §6.6)
#
# The column answers ONE question: when did this name enter the state it is in now?
# So the field is carried while the PUBLIC state persists and re-stamped when it
# changes, and it is read off the pass clock rather than multiplied out of `passes`
# (a late cron and a board name's day-first counter both make that arithmetic lie).
# Every pass below therefore pins its own clock — two passes sharing NOW could not
# tell a carry from a re-stamp.
# ─────────────────────────────────────────────────────────────────────────────

def test_since_ts_is_the_pass_that_established_the_state_not_a_derived_duration():
    """The establishing pass's own `pass_ts`, to the second, on both entry paths."""
    board = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), now=_at(10, 0))
    assert board["states"]["BBB"]["since_ts"] == board["meta"]["pass_ts"]
    one = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), now=_at(10, 0))
    two = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), one, now=_at(10, 5))
    assert two["states"]["AAA"]["state"] == "forming"
    assert two["states"]["AAA"]["since_ts"] == two["meta"]["pass_ts"]
    assert two["states"]["AAA"]["since_ts"].endswith("Z")


def test_since_ts_is_carried_forward_while_the_public_state_is_unchanged():
    """Three passes of an unchanged `forming` keep the FIRST one's stamp."""
    a = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), now=_at(10, 0))
    b = _run(pack({"BBB": buyable()}), quotes(BBB=100.5), a, now=_at(10, 5))
    c = _run(pack({"BBB": buyable()}), quotes(BBB=101.0), b, now=_at(10, 11))
    since = a["states"]["BBB"]["since_ts"]
    assert b["states"]["BBB"]["since_ts"] == since
    assert c["states"]["BBB"]["since_ts"] == since
    # And it is NOT passes x 5 min: this cron landed 6 minutes late on the third pass,
    # so the derived duration (3 passes => 15 min) would have been a fabricated clock.
    assert c["states"]["BBB"]["passes"] == 3
    assert since == a["meta"]["pass_ts"] != c["meta"]["pass_ts"]


def test_since_ts_resets_when_the_public_state_changes():
    """near -> forming -> faded: each published state owns its own clock."""
    one = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), now=_at(10, 0))
    two = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), one, now=_at(10, 5))
    three = _run(pack({"AAA": near(100.0)}), quotes(AAA=99.0), two, now=_at(10, 10))
    assert [one["states"]["AAA"]["state"], two["states"]["AAA"]["state"],
            three["states"]["AAA"]["state"]] == ["near", "forming", "faded"]
    # near -> forming IS a public change even though it is the debounce landing: the
    # reader is being told something new, so the SINCE clock restarts with it.
    assert two["states"]["AAA"]["since_ts"] != one["states"]["AAA"]["since_ts"]
    assert two["states"]["AAA"]["since_ts"] == two["meta"]["pass_ts"]
    assert three["states"]["AAA"]["since_ts"] == three["meta"]["pass_ts"]


def test_since_ts_survives_an_internals_only_change():
    """passes 1 -> 2 under an unchanged public `near` is not a state change.

    A 105.0 print with fade_hi 105.0 holds, so the cross debounce banks a pass and the
    internal marker moves, while the published state stays `near` both times.
    """
    entry = near(100.0, hi=105.0)
    cfg3 = LS.live_cfg({"prophet_live": {"debounce_passes": 3, "fade_buffer_pct": 0.5,
                                         "quote_max_age_min": 12,
                                         "confirm_window_start": "15:30"}})

    def run3(prev, now):
        return LS.evaluate(pack({"AAA": entry}), quotes(AAA=101.0), prev, now=now,
                           cfg=cfg3, quote_asof="x", delay_min=15,
                           quote_age_of=lambda _q: 1.0)

    a = run3(None, _at(10, 0))
    b = run3(a, _at(10, 5))
    for art in (a, b):
        st = art["states"]["AAA"]
        assert st["state"] == "near" and st["internal"] == LS.CROSSING_UNCONFIRMED
    assert a["states"]["AAA"]["passes"] == 1 and b["states"]["AAA"]["passes"] == 2
    assert b["states"]["AAA"]["since_ts"] == a["states"]["AAA"]["since_ts"]


def test_the_confirming_flag_does_not_reset_since_ts():
    """`confirming_into_close` is a flag on `forming`, not a state — the clock holds."""
    a = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), now=_at(15, 20))
    b = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), a, now=_at(15, 35))
    assert "confirming_into_close" not in a["states"]["BBB"]
    assert b["states"]["BBB"]["confirming_into_close"] is True
    assert b["states"]["BBB"]["state"] == a["states"]["BBB"]["state"] == "forming"
    assert b["states"]["BBB"]["since_ts"] == a["states"]["BBB"]["since_ts"]


def test_a_new_session_restamps_since_ts():
    """Same public state across the day boundary, new clock — yesterday's entry time
    describes yesterday's tape. Free: `prev_states` resolves only within the session."""
    a = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), now=_at(10, 0))
    tomorrow = NOW + timedelta(days=1)
    fresh = _run(pack({"BBB": buyable()}, as_of=LS.last_completed_session(tomorrow)),
                 quotes(BBB=100.0), a, now=tomorrow)
    assert fresh["meta"]["session_et"] != a["meta"]["session_et"]
    assert fresh["states"]["BBB"]["state"] == a["states"]["BBB"]["state"] == "forming"
    assert fresh["states"]["BBB"]["since_ts"] == fresh["meta"]["pass_ts"]
    assert fresh["states"]["BBB"]["since_ts"] != a["states"]["BBB"]["since_ts"]


def test_a_dark_row_publishes_no_since_ts_of_its_own():
    """Dark is not a public state, so there is nothing to time — and a dark row with a
    since_ts would be the guess G0.3 forbids. It carries its predecessor's, labelled."""
    a = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), now=_at(10, 0))
    dark = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), a, now=_at(10, 5), age=99.0)
    st = dark["states"]["BBB"]
    assert st["state"] == "dark" and st["reason"] == "stale_quote"
    assert "since_ts" not in st
    assert st["prior_public"] == "forming"
    assert st["prior_since_ts"] == a["states"]["BBB"]["since_ts"]
    # With no history at all a dark row stays the minimal {state, reason} dict.
    cold = _run(pack({"IRR": {"state": "irregular", "center_buyable": True,
                              "as_of_close": 10.0, "probed": True,
                              "buyable_in_band": None}}), quotes(IRR=10.0))
    assert cold["states"]["IRR"] == {"state": "dark", "reason": "irregular_gate"}


def test_a_quote_hiccup_does_not_restart_the_since_clock():
    """The chosen dark-pass rule: back in the SAME public state => the ORIGINAL stamp.

    The per-name twin of dark_artifact's whole-artifact carry — a missing quote must not
    cost the session its history, and a re-stamp here would print "entered forming at
    10:15" for a name that entered it at 10:00. Two dark passes chain the carry.
    """
    a = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), now=_at(10, 0))
    d1 = _run(pack({"BBB": buyable()}), {}, a, now=_at(10, 5))
    d2 = _run(pack({"BBB": buyable()}), {}, d1, now=_at(10, 10))
    assert d1["states"]["BBB"]["reason"] == "no_quote"
    assert d2["states"]["BBB"]["prior_since_ts"] == a["states"]["BBB"]["since_ts"]
    back = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), d2, now=_at(10, 15))
    assert back["states"]["BBB"]["state"] == "forming"
    assert back["states"]["BBB"]["since_ts"] == a["states"]["BBB"]["since_ts"]


def test_coming_back_from_dark_into_a_different_state_restamps():
    """The honest half of the same rule: we did not see the transition, so the clock
    starts at the pass that actually published this state."""
    a = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=100.0), now=_at(10, 0))
    dark = _run(pack({"BBB": buyable(fade=90.0)}), {}, a, now=_at(10, 5))
    assert dark["states"]["BBB"]["prior_public"] == "forming"
    back = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=86.0), dark, now=_at(10, 10))
    assert back["states"]["BBB"]["state"] == "at_risk"          # decisive breach
    assert back["states"]["BBB"]["since_ts"] == back["meta"]["pass_ts"]
    assert back["states"]["BBB"]["since_ts"] != a["states"]["BBB"]["since_ts"]


def test_every_non_dark_state_carries_a_since_ts():
    """One law, no per-state exceptions — the display picks its rows, not the payload."""
    p = pack({"AAA": near(100.0), "BBB": buyable(), "CCC": dormant()})
    art = _run(p, quotes(AAA=101.0, BBB=100.0, CCC=50.0), now=_at(10, 0))
    seen = set()
    for tkr, st in art["states"].items():
        assert st["state"] != "dark", tkr
        assert st["since_ts"] == art["meta"]["pass_ts"], tkr
        seen.add(st["state"])
    assert seen == {"near", "forming", "dormant"}


def test_since_ts_rides_through_a_whole_artifact_dark_pass(monkeypatch, tmp_path):
    """A stale PACK carries `states` into `prev_states` verbatim, so the stamp survives
    a whole-artifact dark exactly as the debounce counter does."""
    import scripts.prophet_live_evaluator as E
    from engine.prophet_live import r2io

    store: dict[str, dict] = {}
    packs = {"good": pack({"BBB": buyable()}),
             "stale": pack({"BBB": buyable()}, as_of="2026-01-02")}
    which = {"k": "good"}
    monkeypatch.setattr(E.r2io, "client", lambda: object())
    monkeypatch.setattr(E.r2io, "get_json", lambda key, **kw:
                        packs[which["k"]] if key == r2io.PACK_KEY else store.get(key))
    monkeypatch.setattr(E.r2io, "put_json",
                        lambda key, payload, **kw: store.__setitem__(key, payload) or True)
    monkeypatch.setattr(E.LV, "load_live_quotes",
                        lambda root: {"quotes": quotes(BBB=100.0), "asof": "x",
                                      "source": "t"})
    monkeypatch.setattr(E, "quote_ager", lambda live, now: (lambda q: 1.0))

    E.run(tmp_path, now=_at(10, 0), cfg={"prophet_live": {}})
    since = store[r2io.LIVE_KEY]["states"]["BBB"]["since_ts"]
    which["k"] = "stale"
    E.run(tmp_path, now=_at(10, 5), cfg={"prophet_live": {}})
    assert store[r2io.LIVE_KEY]["prev_states"]["BBB"]["since_ts"] == since
    which["k"] = "good"
    E.run(tmp_path, now=_at(10, 10), cfg={"prophet_live": {}})
    assert store[r2io.LIVE_KEY]["states"]["BBB"]["since_ts"] == since


# ─────────────────────────────────────────────────────────────────────────────
# G0.3 — honest degradation
# ─────────────────────────────────────────────────────────────────────────────

def test_a_stale_pack_darks_the_whole_artifact():
    """Yesterday's triggers are NEVER evaluated against today's tape."""
    old = (datetime.fromisoformat(LAST_SESSION) - timedelta(days=7)).date().isoformat()
    art = _run(pack({"AAA": near(100.0)}, as_of=old), quotes(AAA=101.0))
    assert art["status"] == "dark" and art["reason"] == "stale_pack"
    assert art["states"] == {}
    assert art["meta"]["pack_as_of"] == old
    assert art["meta"]["expected_session"] == LAST_SESSION
    assert old in art["meta"]["detail"] and LAST_SESSION in art["meta"]["detail"]


def test_a_missing_pack_darks_the_whole_artifact():
    for empty in (None, {}, {"as_of": LAST_SESSION}):
        art = _run(empty, quotes(AAA=101.0))
        assert art["status"] == "dark" and art["reason"] == "no_pack"
        assert art["states"] == {}


def test_one_stale_quote_darks_that_name_only():
    p = pack({"AAA": near(100.0), "BBB": buyable()})
    ages = {"AAA": 45.0, "BBB": 2.0}
    art = LS.evaluate(p, quotes(AAA=101.0, BBB=100.0), None, now=NOW, cfg=CFG,
                      quote_asof="x", delay_min=15,
                      quote_age_of=lambda q: ages[  # keyed off the price we set
                          "AAA" if q["price"] == 101.0 else "BBB"])
    assert art["status"] == "live"
    assert art["states"]["AAA"] == {"state": "dark", "reason": "stale_quote",
                                    "quote_age_min": 45.0}
    assert art["states"]["BBB"]["state"] == "forming"
    assert art["meta"]["dark_counts"] == {"stale_quote": 1}


def test_a_missing_quote_darks_that_name_with_a_reason():
    art = _run(pack({"AAA": near(100.0), "BBB": buyable()}), quotes(BBB=100.0))
    assert art["states"]["AAA"] == {"state": "dark", "reason": "no_quote"}
    assert art["states"]["BBB"]["state"] == "forming"
    assert art["meta"]["dark_counts"] == {"no_quote": 1}


def test_an_unknown_quote_age_is_stale_not_fresh():
    art = LS.evaluate(pack({"AAA": near(100.0)}), quotes(AAA=101.0), None, now=NOW,
                      cfg=CFG, quote_asof=None, delay_min=15, quote_age_of=lambda q: None)
    assert art["states"]["AAA"]["state"] == "dark"
    assert art["states"]["AAA"]["reason"] == "stale_quote"


def test_an_unprobed_name_is_counted_as_coverage_not_evaluated():
    """The pack never swept it, so the tape cannot settle it — and it is not "dormant"."""
    p = pack({"UNP": {"state": "dormant", "center_buyable": False, "as_of_close": 10.0,
                      "probed": False, "skip": "probe_cap"},
              "STL": {"state": "dormant", "center_buyable": False, "as_of_close": 10.0,
                      "probed": False, "skip": "stale_series"},
              "AAA": near(100.0)})
    art = _run(p, quotes(UNP=10.0, STL=10.0, AAA=101.0))
    assert "UNP" not in art["states"] and "STL" not in art["states"]
    assert set(art["states"]) == {"AAA"}
    assert art["meta"]["unprobed"] == {"probe_cap": 1, "stale_series": 1}
    assert art["meta"]["unprobed_n"] == 2
    assert art["meta"]["evaluated_n"] == 1


def test_an_irregular_gate_darks_the_name_with_its_own_reason():
    """Non-single-interval structure ships no threshold, so no state can be inferred."""
    p = pack({"IRR": {"state": "irregular", "center_buyable": True, "as_of_close": 10.0,
                      "probed": True, "buyable_in_band": None}})
    art = _run(p, quotes(IRR=10.0))
    assert art["states"]["IRR"] == {"state": "dark", "reason": "irregular_gate"}
    assert art["meta"]["dark_counts"] == {"irregular_gate": 1}


def test_every_dark_state_carries_a_reason_and_no_price():
    p = pack({"A": near(100.0), "B": buyable(), "C": dormant()})
    art = _run(p, {})                     # no quotes at all
    assert art["meta"]["dark_counts"] == {"no_quote": 3}
    for tkr, st in art["states"].items():
        assert st["state"] == "dark"
        assert st.get("reason"), tkr
        assert "price" not in st, tkr     # a dark row never carries a number


def test_the_freshness_stamp_and_delay_ride_on_every_payload():
    art = _run(pack({"BBB": buyable()}), quotes(BBB=100.0))
    m = art["meta"]
    assert m["quote_asof"] == "2026-07-29T13:58:00Z"
    assert m["delay_min"] == 15          # house delayMin convention: the VENDOR floor
    assert m["pass_ts"].endswith("Z") and m["session_et"] == SESSION
    assert m["pack_as_of"] == LAST_SESSION and m["expected_session"] == LAST_SESSION
    assert art["states"]["BBB"]["quote_age_min"] == 1.0    # measured, per name


# ─────────────────────────────────────────────────────────────────────────────
# Window + clock
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("hh,mm,inside", [
    (9, 20, False), (9, 25, True), (10, 0, True), (16, 15, True),
    (16, 24, True),     # inside the cron-drift grace
    (16, 40, False), (8, 25, False), (17, 30, False)])
def test_window_is_evaluated_on_the_eastern_clock(hh, mm, inside):
    assert LS.in_window(_at(hh, mm), CFG) is inside


def test_the_window_means_the_same_thing_in_both_dst_regimes():
    """A UTC-pinned window would be an hour wrong for half the year."""
    for month in (1, 7):     # EST and EDT
        et = datetime(2026, month, 15, 10, 0, tzinfo=LS._ET)   # 10:00 ET, a weekday
        assert LS.in_window(et.astimezone(timezone.utc), CFG), month
        pre = datetime(2026, month, 15, 8, 30, tzinfo=LS._ET)
        assert not LS.in_window(pre.astimezone(timezone.utc), CFG), month


def test_weekends_stand_the_lane_down():
    sat = datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc)     # Saturday
    assert LS.et_clock(sat).weekday() == 5
    assert LS.in_window(sat, CFG) is False


def test_last_completed_session_is_the_prior_session_during_rth():
    """During RTH today's bar does not exist yet — the pack is armed on yesterday."""
    assert LS.last_completed_session(NOW) == "2026-07-28"
    # After the close-plus-settle buffer the same day counts.
    assert LS.last_completed_session(_at(18, 0)) == "2026-07-29"
    # A Monday morning reaches back over the weekend.
    monday = datetime(2026, 8, 3, 14, 0, tzinfo=timezone.utc)
    assert LS.last_completed_session(monday) == "2026-07-31"


# ─────────────────────────────────────────────────────────────────────────────
# G0.6 — vocabulary law
# ─────────────────────────────────────────────────────────────────────────────

#: Word-boundary matched, so the internal ``crossing_unconfirmed`` marker survives:
#: saying we have NOT confirmed something is the honest form, and it is spool-only
#: telemetry that never reaches a public ``state``. Claiming a confirmation is what
#: is banned — only the nightly build confirms anything.
FORBIDDEN_WORDS = ("fired", "confirmed", "refuted", "validated", "thesis")
FORBIDDEN_SUBSTRINGS = ("falsif", "证伪")


def test_public_states_are_the_agreed_seven():
    """`unknown` joined the contract in W-L0 gate 5 — the honest answer where the pack
    measured nothing. It renders nowhere today; a surface that renders it owes EN+ZH
    glance-tier copy, in plain words and never this token."""
    assert LS.PUBLIC_STATES == ("dormant", "near", "forming", "faded", "at_risk",
                                "unknown", "dark")
    assert LS.NO_VERDICT_STATES == ("dark", "unknown")
    for marker in LS.INTERNAL_MARKERS:
        assert marker not in LS.PUBLIC_STATES, marker
        assert marker in LS.EVENT_KINDS, marker


def test_no_forbidden_vocabulary_in_a_payload():
    # BBB holds so a PUBLIC forming exists and the confirming flag can fire (M4 means
    # a 1-pass cross no longer produces one, so the fixture has to earn it).
    p = pack({"AAA": near(100.0), "BBB": buyable(), "CCC": dormant()})
    a = _run(p, quotes(AAA=101.0, BBB=100.0, CCC=50.0), now=_at(15, 45))
    b = _run(p, quotes(AAA=101.0, BBB=86.0, CCC=50.0), a, now=_at(15, 50))
    blob = (json.dumps(a) + json.dumps(b)).lower()
    for word in FORBIDDEN_WORDS:
        assert not re.search(rf"\b{word}\b", blob), word
    for sub in FORBIDDEN_SUBSTRINGS:
        assert sub not in blob, sub
    # `confirming_into_close` is the sanctioned form — a projection window, not a verdict.
    assert "confirming_into_close" in json.dumps(a)
    assert LS.CROSSING_UNCONFIRMED in blob      # internal marker, deliberately kept


def test_no_forbidden_vocabulary_in_any_emittable_string():
    """AST sweep of the STRING LITERALS that can reach a payload.

    Docstrings and comments are excluded on purpose — the module docstring names the
    banned words precisely because it states the law. What must never carry them is a
    literal the code can emit, which is the one copy-paste away from a P1 surface.
    """
    import ast
    for rel in ("engine/prophet_live/live_states.py",
                "scripts/prophet_live_evaluator.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        # Docstring NODES, not their cleaned text: ast.get_docstring() dedents, so
        # comparing values would never match and the whole sweep would fail on the
        # module docstring that states this very law.
        docs: set[int] = set()
        for n in ast.walk(tree):
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef)) and n.body:
                first = n.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                        and isinstance(first.value.value, str):
                    docs.add(id(first.value))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docs:
                continue
            low = node.value.lower()
            for word in FORBIDDEN_WORDS:
                assert not re.search(rf"\b{word}\b", low), \
                    f"{rel}:{node.lineno} {word!r} in {node.value!r}"
            for sub in FORBIDDEN_SUBSTRINGS:
                assert sub not in low, f"{rel}:{node.lineno} {sub!r} in {node.value!r}"


# ─────────────────────────────────────────────────────────────────────────────
# G0.2 — ledger law
# ─────────────────────────────────────────────────────────────────────────────

WORKFLOW = ROOT / ".github" / "workflows" / "prophet-live.yml"


def test_the_workflow_cannot_commit_anything():
    text = WORKFLOW.read_text(encoding="utf-8")
    for banned in ("git add", "git commit", "git push", "contents: write",
                   "actions: write", "HEAD:main"):
        assert banned not in text, banned
    assert "contents: read" in text


def test_the_workflow_runs_off_the_render_pool_and_is_kill_switched():
    text = WORKFLOW.read_text(encoding="utf-8")
    runners = [ln.split("runs-on:")[1].split("#")[0].strip() for ln in text.splitlines()
               if "runs-on:" in ln]
    # ~80 runs a day on the self-hosted pool would eat the nightly's render budget.
    assert runners == ["ubuntu-latest"], runners
    assert "vars.PROPHET_LIVE_DISABLED != 'true'" in text
    assert "group: prophet-live" in text and "cancel-in-progress: false" in text


def test_the_workflow_installs_no_pandas():
    """~80 runs a day cannot pay a 40s pandas install, and nothing here needs it."""
    line = next(ln for ln in WORKFLOW.read_text(encoding="utf-8").splitlines()
                if "pip install" in ln)
    assert "pandas" not in line and "numpy" not in line
    assert "pyyaml" in line and "boto3" in line


def test_the_workflow_crons_span_both_dst_regimes():
    crons = re.findall(r'- cron: "([^"]+)"', WORKFLOW.read_text(encoding="utf-8"))
    hours: set[int] = set()
    for c in crons:
        assert c.endswith("* * 1-5"), c
        for part in c.split()[1].split(","):
            if part.startswith("*/"):
                continue
            if "-" in part:
                lo, hi = (int(x) for x in part.split("-"))
                hours.update(range(lo, hi + 1))
            else:
                hours.add(int(part))
    # 13:25Z-21:15Z covers 09:25-16:15 ET under BOTH EDT and EST.
    assert min(hours) == 13 and max(hours) == 21


def test_the_evaluator_module_imports_no_data_writer():
    """G0.2 at the AST level: no write call and no ledger/store module in the closure."""
    import ast
    banned_calls = {"to_parquet", "to_csv", "write_text", "write_bytes", "open",
                    "mkdir", "enqueue", "append_jsonl"}
    banned_modules = {"pandas", "numpy", "pyarrow",
                      "engine.grading", "engine.marketing.outbox",
                      "scripts.build_stock_library", "engine.prophet_live.armed_pack"}
    for rel in ("scripts/prophet_live_evaluator.py",
                "engine/prophet_live/live_states.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                assert name not in banned_calls, f"{rel}:{node.lineno} calls {name}()"
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name not in banned_modules, f"{rel}: imports {a.name}"
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert mod not in banned_modules, f"{rel}: imports from {mod}"
                for a in node.names:
                    full = f"{mod}.{a.name}"
                    assert full not in banned_modules, f"{rel}: imports {full}"
    # live_states reads the interval contract from the stdlib-only sibling, NOT from
    # armed_pack — the latter imports pandas, which this lane does not install. Asserted
    # over the PARSED imports, not a source substring: the substring form redded on a
    # line wrap, which pins formatting rather than the law it exists for.
    src = (ROOT / "engine" / "prophet_live" / "live_states.py").read_text(encoding="utf-8")
    imported: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module == "engine.prophet_live.interval":
            imported |= {a.name for a in node.names}
    assert {"in_probed_band", "interval_contains", "lower_edge", "probe_floor"} <= imported


def test_the_evaluator_imports_with_pandas_blocked():
    """The workflow installs pyyaml+boto3 only, so the closure must survive without
    pandas. An importorskip-shaped hole here would disarm the whole file silently;
    this runs the real import in a clean interpreter with pandas/numpy/pyarrow made
    unimportable, which is what the runner actually looks like.
    """
    probe = ROOT / "tests" / "fixtures" / "prophet_live" / "import_probe.py"
    r = subprocess.run([sys.executable, str(probe)], cwd=ROOT,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "prophet-live thin import OK" in r.stdout, r.stdout + r.stderr


def test_the_evaluator_publishes_only_the_two_runtime_keys(monkeypatch, tmp_path, capsys):
    import scripts.prophet_live_evaluator as E
    from engine.prophet_live import r2io

    p = pack({"AAA": near(100.0)})
    puts: list[str] = []
    monkeypatch.setattr(E.r2io, "client", lambda: object())
    monkeypatch.setattr(E.r2io, "get_json",
                        lambda key, **kw: p if key == r2io.PACK_KEY else None)
    monkeypatch.setattr(E.r2io, "put_json",
                        lambda key, payload, **kw: puts.append(key) or True)
    monkeypatch.setattr(E.LV, "load_live_quotes",
                        lambda root: {"quotes": quotes(AAA=101.0), "asof": None,
                                      "source": "test"})
    monkeypatch.setattr(E, "quote_ager", lambda live, now: (lambda q: 1.0))

    assert E.run(tmp_path, now=NOW, cfg={"prophet_live": {}}) == 0
    assert puts[0] == r2io.LIVE_KEY
    assert len(puts) == 2 and puts[1].startswith(r2io.EVENTS_PREFIX + "/" + SESSION + "/")
    assert puts[1].endswith(".json")
    # Nothing was created under the repo root it was handed.
    assert not (tmp_path / "data").exists()


def test_no_publish_env_refuses_every_write(monkeypatch, capsys):
    """B4 belt: a receipt or rehearsal must not be able to write the real spool.

    The event spool is the ledger's raw input; a fabricated row joined to real closes
    cannot be told from a genuine one afterwards. The reconciler's LEDGER_FLOOR_SESSION
    is the braces.
    """
    from engine.prophet_live import r2io

    wrote: list[str] = []

    class _S3:
        def put_object(self, **kw):      # noqa: ANN003
            wrote.append(kw["Key"])

    monkeypatch.setenv("PROPHET_LIVE_NO_PUBLISH", "1")
    assert r2io.put_json("live_flow/whatever.json", {"a": 1}, s3=_S3()) is False
    assert wrote == [], "wrote to R2 with the kill switch set"
    out = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert out and out[0].startswith("::warning title=prophet-live::")
    # Unset (and the falsy spellings) leave the real publish path alone.
    for value in ("0", "false", ""):
        monkeypatch.setenv("PROPHET_LIVE_NO_PUBLISH", value)
        assert r2io.put_json("live_flow/whatever.json", {"a": 1}, s3=_S3()) is True
    assert len(wrote) == 3


def test_the_events_spool_is_one_object_per_pass_never_read_modify_write():
    from engine.prophet_live import r2io
    a = r2io.events_key("2026-07-29", "100005")
    b = r2io.events_key("2026-07-29", "100505")
    assert a != b
    assert a == "live_flow/prophet_live_events/2026-07-29/100005.json"


def test_an_eventless_pass_publishes_the_state_map_but_no_spool_object(monkeypatch, tmp_path):
    import scripts.prophet_live_evaluator as E
    from engine.prophet_live import r2io

    puts: list[str] = []
    monkeypatch.setattr(E.r2io, "client", lambda: object())
    monkeypatch.setattr(E.r2io, "get_json",
                        lambda key, **kw: pack({"CCC": dormant()}) if key == r2io.PACK_KEY else None)
    monkeypatch.setattr(E.r2io, "put_json", lambda key, payload, **kw: puts.append(key) or True)
    monkeypatch.setattr(E.LV, "load_live_quotes",
                        lambda root: {"quotes": quotes(CCC=50.0), "asof": None, "source": "t"})
    monkeypatch.setattr(E, "quote_ager", lambda live, now: (lambda q: 1.0))
    assert E.run(tmp_path, now=NOW, cfg={"prophet_live": {}}) == 0
    assert puts == [r2io.LIVE_KEY]


def test_out_of_window_stands_down_with_a_line_start_notice(capsys, tmp_path):
    import scripts.prophet_live_evaluator as E
    assert E.run(tmp_path, now=_at(3, 0), cfg={"prophet_live": {}}) == 0
    out = [ln for ln in capsys.readouterr().out.splitlines() if "::" in ln]
    assert out and out[0].startswith("::notice title=prophet-live::")
    assert "standing down" in out[0]


def test_a_stale_pack_annotation_is_a_bare_line_start_warning(monkeypatch, capsys, tmp_path):
    """The logger-prefix trap: ``log.warning("::warning …")`` is silently dropped."""
    import scripts.prophet_live_evaluator as E
    from engine.prophet_live import r2io

    old = (datetime.fromisoformat(LAST_SESSION) - timedelta(days=7)).date().isoformat()
    monkeypatch.setattr(E.r2io, "client", lambda: object())
    monkeypatch.setattr(E.r2io, "get_json", lambda key, **kw:
                        pack({"AAA": near(100.0)}, as_of=old) if key == r2io.PACK_KEY else None)
    monkeypatch.setattr(E.r2io, "put_json", lambda key, payload, **kw: True)
    monkeypatch.setattr(E.LV, "load_live_quotes",
                        lambda root: {"quotes": quotes(AAA=101.0), "asof": None, "source": "t"})
    monkeypatch.setattr(E, "quote_ager", lambda live, now: (lambda q: 1.0))
    assert E.run(tmp_path, now=NOW, cfg={"prophet_live": {}}) == 0
    warn = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert warn and warn[0].startswith("::warning title=prophet-live::")
    assert "stale_pack" in warn[0]


def test_coverage_is_disclosed_every_pass(monkeypatch, tmp_path):
    import scripts.prophet_live_evaluator as E
    from engine.prophet_live import r2io

    published: list[dict] = []
    monkeypatch.setattr(E.r2io, "client", lambda: object())
    monkeypatch.setattr(E.r2io, "get_json", lambda key, **kw:
                        pack({"AAA": near(100.0)}) if key == r2io.PACK_KEY else None)
    monkeypatch.setattr(E.r2io, "put_json",
                        lambda key, payload, **kw: published.append(payload) or True)
    monkeypatch.setattr(E.LV, "load_live_quotes",
                        lambda root: {"quotes": quotes(AAA=101.0), "asof": None, "source": "t"})
    monkeypatch.setattr(E, "quote_ager", lambda live, now: (lambda q: 1.0))
    E.run(tmp_path, now=NOW, cfg={"prophet_live": {}})
    cov = published[0]["meta"]["coverage"]
    # ONE definition of unprobed (m10): it comes from live_states' own walk of the
    # pack, not a second universe_n - probed_n subtraction in the script.
    assert cov["pack_universe_n"] == 1742 and cov["pack_probed_n"] == 1
    assert cov["unprobed_n"] == published[0]["meta"]["unprobed_n"] == 0
    assert cov["pack_skipped"] == {"probe_cap": 1176}


def test_a_dark_pass_does_not_wipe_the_sessions_debounce(monkeypatch, tmp_path):
    """m4: one stale-quote artifact used to cost the session every banked pass.

    The dark PUT replaced `states` with {}, so the next pass found no predecessor and
    every name that had already banked a confirming pass restarted from zero.
    """
    import scripts.prophet_live_evaluator as E
    from engine.prophet_live import r2io

    store: dict[str, dict] = {}
    packs = {"good": pack({"AAA": near(100.0)}),
             "stale": pack({"AAA": near(100.0)}, as_of="2026-01-02")}
    which = {"k": "good"}
    monkeypatch.setattr(E.r2io, "client", lambda: object())
    monkeypatch.setattr(E.r2io, "get_json", lambda key, **kw:
                        packs[which["k"]] if key == r2io.PACK_KEY else store.get(key))
    monkeypatch.setattr(E.r2io, "put_json",
                        lambda key, payload, **kw: store.__setitem__(key, payload) or True)
    monkeypatch.setattr(E.LV, "load_live_quotes",
                        lambda root: {"quotes": quotes(AAA=101.0), "asof": "x",
                                      "source": "t"})
    monkeypatch.setattr(E, "quote_ager", lambda live, now: (lambda q: 1.0))

    E.run(tmp_path, now=_at(10, 0), cfg={"prophet_live": {}})
    assert store[r2io.LIVE_KEY]["states"]["AAA"]["passes"] == 1

    which["k"] = "stale"                       # a dark pass lands in the middle
    E.run(tmp_path, now=_at(10, 5), cfg={"prophet_live": {}})
    dark = store[r2io.LIVE_KEY]
    assert dark["status"] == "dark" and dark["states"] == {}
    assert dark["prev_states"]["AAA"]["passes"] == 1        # history, explicitly labelled
    assert dark["meta"]["quote_asof"] == "x"               # freshness rides even on dark

    which["k"] = "good"
    E.run(tmp_path, now=_at(10, 10), cfg={"prophet_live": {}})
    st = store[r2io.LIVE_KEY]["states"]["AAA"]
    assert st["passes"] == 2 and st["state"] == "forming"


def test_a_dark_artifact_carries_its_freshness_stamps():
    """m3: a consumer must see HOW stale the tape was when we declined to speak."""
    art = LS.dark_artifact("no_pack", now=NOW, cfg=CFG, quote_asof="2026-07-29T13:58:00Z",
                           delay_min=15)
    assert art["meta"]["quote_asof"] == "2026-07-29T13:58:00Z"
    assert art["meta"]["delay_min"] == 15
    assert art["meta"]["session_phase"] == "rth"
    assert art["states"] == {} and "prev_states" not in art


def test_the_lane_stands_down_on_a_market_holiday():
    """m8: a weekday check alone published ~80 passes against a tape that never opened."""
    from lib.nyse_calendar import is_session
    thanksgiving = datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc)   # 10:00 ET Thu
    assert LS.et_clock(thanksgiving).weekday() < 5
    assert not is_session(LS.et_clock(thanksgiving).date())
    assert LS.in_window(thanksgiving, CFG) is False
    # The next real session is fine.
    assert LS.in_window(datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc), CFG) is True


def test_session_phase_separates_preopen_prints_from_rth():
    """m8: a state formed at 09:27 is a different claim from one formed at 11:00."""
    assert LS.session_phase(_at(9, 27)) == "preopen"
    assert LS.session_phase(_at(9, 30)) == "rth"
    assert LS.session_phase(_at(11, 0)) == "rth"
    art = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), now=_at(9, 27))
    assert art["meta"]["session_phase"] == "preopen"


def test_config_block_defaults_resolve_from_config_yml():
    import yaml
    cfg = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
    block = cfg["prophet_live"]
    resolved = LS.live_cfg(cfg)
    assert resolved["debounce_passes"] == block["debounce_passes"] == 2
    assert resolved["window_et"] == {"start": "09:25", "end": "16:15"}
    assert resolved["confirm_window_start"] == "15:30"
    # THE FRESHNESS CEILING IS DERIVED (P0 fix 2026-07-30), so config.yml must NOT pin
    # it: quote_max_age_min = live.delayed_min + quote_slack_min. A fixed number under
    # a delayed feed is an off switch, not a gate — see live_cfg's docstring.
    assert "quote_max_age_min" not in block
    assert resolved["quote_max_age_min"] == cfg["live"]["delayed_min"] + block["quote_slack_min"]
    assert resolved["quote_max_age_min"] == 25
    # A partial override must not drop the sibling keys of a nested block.
    part = LS.live_cfg({"prophet_live": {"window_et": {"end": "16:00"}}})
    assert part["window_et"] == {"start": "09:25", "end": "16:00"}
