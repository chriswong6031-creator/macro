"""tests/test_prophet_live_evaluator.py — Prophet Live P0 gates G0.2, G0.3, G0.5, G0.6.

The */5 lane's job is to say one of six honest things about a name, or say nothing.
This file pins the four ways it could stop being honest:

  G0.2 LEDGER LAW      it writes no ``data/`` path and commits nothing, ever.
  G0.3 DEGRADATION     a stale pack darks the WHOLE artifact; a stale or missing
                       quote darks THAT NAME and leaves the rest live. No path
                       invents a state, and every dark carries a reason.
  G0.5 DEBOUNCE        one pass above a trigger is never a public state; two are;
                       a drop through the buffer fades; a re-cross pays two again.
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
    # Inside the 0.5% hysteresis band: still forming, counter preserved.
    c = _run(pack({"AAA": near(100.0)}), quotes(AAA=99.8), b)
    assert c["states"]["AAA"]["state"] == "forming" and c["states"]["AAA"]["passes"] == 2
    assert c["events"] == []
    # Through the buffer: faded, counter cleared.
    d = _run(pack({"AAA": near(100.0)}), quotes(AAA=99.0), c)
    assert d["states"]["AAA"]["state"] == "faded" and d["states"]["AAA"]["passes"] == 0
    assert [e["kind"] for e in d["events"]] == ["faded"]


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
    """
    a = _run(pack({"AAA": near(100.0, hi=105.0)}), quotes(AAA=101.0))
    b = _run(pack({"AAA": near(100.0, hi=105.0)}), quotes(AAA=101.0), a)
    assert b["states"]["AAA"]["state"] == "forming"
    up = _run(pack({"AAA": near(100.0, hi=105.0)}), quotes(AAA=105.5), b)
    assert up["states"]["AAA"]["state"] == "faded" and up["states"]["AAA"]["via"] == "overrun"
    assert up["events"][0]["via"] == "overrun"
    down = _run(pack({"AAA": near(100.0, hi=105.0)}), quotes(AAA=98.0), b)
    assert down["states"]["AAA"]["state"] == "faded" and down["states"]["AAA"]["via"] == "drop"
    assert down["events"][0]["via"] == "drop"


# ─────────────────────────────────────────────────────────────────────────────
# B2 — outside the probed band the pack knows nothing
# ─────────────────────────────────────────────────────────────────────────────

def test_a_board_name_gapping_below_its_band_goes_dark_not_forming():
    """The reproduced fabrication: -30% satisfied "no breach recorded" and read forming."""
    art = _run(pack({"BBB": buyable()}), quotes(BBB=70.0))     # band_lo_px 85.0
    assert art["states"]["BBB"] == {"state": "dark", "reason": "out_of_band",
                                    "price": 70.0, "quote_age_min": 1.0}
    assert art["meta"]["dark_counts"] == {"out_of_band": 1}


def test_a_name_with_no_fade_edge_can_still_leave_its_band():
    """fade_px None used to make at_risk unreachable at ANY price, forever."""
    entry = buyable(fade=None, hi=None)
    inside = _run(pack({"BBB": entry}), quotes(BBB=90.0))
    assert inside["states"]["BBB"]["state"] == "forming"
    outside = _run(pack({"BBB": entry}), quotes(BBB=84.0))     # below band_lo_px 85.0
    assert outside["states"]["BBB"]["state"] == "dark"
    assert outside["states"]["BBB"]["reason"] == "out_of_band"


def test_a_runaway_past_the_band_top_goes_dark_rather_than_extrapolating():
    """+25% with fade_hi None read forming, where the real gate says False at +25%."""
    entry = near(100.0, hi=None)                              # band_hi_px 109.25
    ok = _run(pack({"AAA": entry}), quotes(AAA=108.0))
    assert ok["states"]["AAA"]["state"] == "near"              # 1 pass, in band
    past = _run(pack({"AAA": entry}), quotes(AAA=118.75))      # +25% on a 95 close
    assert past["states"]["AAA"]["state"] == "dark"
    assert past["states"]["AAA"]["reason"] == "out_of_band"


def test_a_non_buyable_name_stays_evaluable_below_its_close():
    """band_lo_px is 0 for those names: the centre verdict already answers downward."""
    art = _run(pack({"AAA": near(100.0)}), quotes(AAA=40.0))
    assert art["states"]["AAA"]["state"] == "near"
    assert art["meta"]["dark_counts"] == {}


def test_a_pack_without_band_fields_still_evaluates():
    """Schema skew must not dark a whole universe."""
    entry = {k: v for k, v in near(100.0).items()
             if k not in ("band_lo_px", "band_hi_px")}
    art = _run(pack({"AAA": entry}), quotes(AAA=101.0))
    assert art["states"]["AAA"]["state"] == "near"


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


def test_public_states_are_the_agreed_six():
    assert LS.PUBLIC_STATES == ("dormant", "near", "forming", "faded", "at_risk", "dark")
    assert LS.CROSSING_UNCONFIRMED not in LS.PUBLIC_STATES


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
    # armed_pack — the latter imports pandas, which this lane does not install.
    src = (ROOT / "engine" / "prophet_live" / "live_states.py").read_text(encoding="utf-8")
    assert ("from engine.prophet_live.interval import "
            "in_probed_band, interval_contains, lower_edge") in src


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
