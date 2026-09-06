"""Flow Observatory V2 W2 — binding per-leg source quality states and fail-visible
publication on flow_velocity.html (research/flow_observatory/W2_SPEC.md).

Written against the frozen spec's nine fixtures (§4) and ten test obligations (§5). The
motivating defect (mission brief / #4676): the 2026-07/08 12-day A-share freeze rendered as
confidently current beside a live Southbound leg — nothing anywhere went red, because
``lib.desk_guard.stale_legs`` only ever emitted an advisory ``::warning`` with no page
branch. F1 below is that exact shape (measured 12-session CN gap against a current HK leg)
reproduced as a fixture: it must now render STALE, with a chip, a section watermark, and a
replaced hero verdict — machine (``sources[].status``/``publication_state``) and UI
(``ui_state``/chip class/watermark) reading the SAME verdict.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from jinja2 import Environment, FileSystemLoader

from engine import i18n
from lib import cn_calendar, hk_calendar
from pathlib import Path

from engine.flow_observatory import changes as fo_changes
from engine.flow_observatory import quality as fo_quality
from engine.flow_observatory.contract import (
    QUADRANT_LABELS,
    STATUS_WORD,
    ContractError,
    build_sources,
    build_v2,
    validate,
)
from scripts.build_vector import C

ROOT = Path(__file__).resolve().parent.parent
TMPL = ROOT / "templates"


def _render(v2, built="test"):
    env = Environment(loader=FileSystemLoader(str(TMPL)), autoescape=True)
    env.globals.update(td=i18n.td, tr=i18n.tr, quadrant_labels=QUADRANT_LABELS,
                       status_word=STATUS_WORD)
    return env.get_template("flow_velocity.html.j2").render(C=C, snap=v2, built=built)


# ── shared fixture: a minimal-but-real desk snapshot, every leg controllable ───────────
# S2 fixture repair: most fixtures below are not testing the lhb_inst_seats leg at all, so
# they should get its ORDINARY HEALTHY/event-window reading by default — S2 makes an
# UNREADABLE lhb_inst_seats degrade the desk-wide publication_state rollup (capped at
# DEGRADED), so a fixture that means "no seats today" must now say so EXPLICITLY by passing
# `seats={}` (falsy but not None) rather than relying on the old "seats or {}" collapse,
# which could not distinguish "omitted" from "explicitly none".
_DEFAULT_PRESENT_SEATS = {"600104.SS": {"inst_net_yi": 1.0, "n_buy": 1, "n_sell": 0, "dir": "buy"}}


def _snap(*, today: date, cn_asof: str | None, sb_asof: str | None, hk_asof: str | None,
         sb_live: bool = True, seats: dict | None = None, seats_asof: str | None = "2026-08-30",
         cn_names_n: int = 100, ashare_sectors_rows=None) -> dict:
    seats_final = seats if seats is not None else _DEFAULT_PRESENT_SEATS
    rows = ashare_sectors_rows if ashare_sectors_rows is not None else [
        {"id": "cn_autos", "name": "Autos", "name_zh": "汽车", "n_members": 10,
         "vel": 1.2, "accel": 0.01, "rate_now": 1.0, "rate_4wk": 1.5, "rate_norm": 0.2,
         "rate_rel": 1.2, "state": "above norm, rising", "state_zh": "高于常态·升温",
         "members": [], "inst_attention": 0},
    ]
    return {
        "as_of": cn_asof,
        "aggregate": [
            {"key": "southbound", "label": "Southbound", "label_zh": "南向",
             "live": sb_live, "as_of": sb_asof, "spark": None, "flow_1m_b": 2.0,
             "pos_days_20": 10, "vel": {"1w": 0.1, "1m": 0.2, "3m": 0.1}, "accel": 0.01,
             "vel_primary": 0.2, "primary": "1m",
             "state": "above norm, rising", "state_zh": "高于常态·升温"},
            {"key": "northbound", "label": "Northbound", "label_zh": "北向",
             "live": False, "as_of": None, "frozen_since": "2024-08-16",
             "note": "discontinued", "note_zh": "已停止"},
        ],
        "ashare_names": {"cadence": "daily", "as_of": cn_asof, "n": cn_names_n, "n_unscored": 0,
                        "primary": "4wk", "note": "n", "note_zh": "n",
                        "market_read": None, "inflow": [], "outflow": []},
        "ashare_sectors": {"cadence": "daily", "as_of": cn_asof, "n": len(rows), "n_unscored": 0,
                          "primary": "4wk", "note": "s", "note_zh": "s", "rows": rows},
        "hk_names": ({"as_of": hk_asof, "n": 200, "n_sized": 190, "note": "h",
                     "buying": [], "selling": [], "depth": 20, "vel_ready": True,
                     "basis": "b", "basis_zh": "b"} if hk_asof else None),
        "seats_by_ticker": seats_final,
        "seats_as_of": seats_asof,
        "pulse": None, "confluence": None, "momentum": None,
        "note": "n",
    }


def _v2(*, today: date, log_rows=None, **snap_kwargs) -> dict:
    """B1 repair: threads a real tz-aware ``now`` (noon UTC on ``today``) through
    ``build_v2`` instead of the old bare-date ``today=`` param — noon UTC is always past
    both CN close+settle (17:00 CST) and HK close+settle (17:30 HKT) on the SAME calendar
    date (CST/HKT are both UTC+8, and noon+8h=20:00 never rolls to the next day), so every
    existing fixture below that was tuned against the OLD ``last_session_on_or_before(today)``
    reading keeps its exact expected gap counts — the fix only changes HOW the anchor is
    computed (via the calendar's own settle-buffer-aware ``expected_last_session``), not
    WHAT day it resolves to for these already-past-close fixtures. Tests exercising the
    settle-buffer/timezone correctness itself (B1 tests a-d below) construct their own
    ``now`` datetimes directly instead of going through this helper.
    """
    snap = _snap(today=today, **snap_kwargs)
    now_dt = datetime(today.year, today.month, today.day, 12, 0, 0, tzinfo=timezone.utc)
    return build_v2(snap, log_rows=log_rows or [], market_session=snap.get("as_of"),
                    generated_at=now_dt.isoformat(timespec="seconds"), now=now_dt,
                    seats_as_of=snap.get("seats_as_of"))


# ══════════════════════════════════════════════════════════════════════════════════════
# §5 test 1 — each fixture F1..F9 → exact expected per-leg status + publication_state
# ══════════════════════════════════════════════════════════════════════════════════════

# ── F1: partial freeze (#4676 shape) — cn legs 12 CN-sessions behind a current sb ───────
def test_f1_partial_freeze_cn_stale_hk_current():
    today = date(2026, 9, 2)
    cn_newest = cn_calendar.last_session_on_or_before(today)
    cn_stale_date = cn_calendar.session_n_back(cn_newest, 12)
    assert cn_calendar.sessions_between(cn_stale_date, cn_newest) == 12

    v2 = _v2(today=today, cn_asof=cn_stale_date.isoformat(),
             sb_asof=today.isoformat(), hk_asof=today.isoformat())
    by_id = {s["source_id"]: s for s in v2["sources"]}
    assert by_id["cn_large_order_proxy"]["status"] == fo_quality.STALE
    assert by_id["cn_large_order_proxy"]["gap_sessions"] == 12
    assert by_id["sb_aggregate"]["status"] == fo_quality.HEALTHY
    assert v2["publication_state"] == fo_quality.STALE


# ── F2: total freeze — every live leg > 10 CALENDAR days old (wall-clock backstop) ──────
def test_f2_total_freeze_via_the_full_pipeline_ends_up_stale():
    """Integration-level F2: every live leg dated a month back. In the REAL calendars a
    span this long always crosses real trading sessions too, so cn_large_order_proxy /
    sb_aggregate / hk_sb_holdings land on STALE via their OWN per-leg session-gap rule —
    the observable desk-wide outcome (every live leg STALE, publication_state STALE) is
    what F2 requires; the dedicated wall-clock-ONLY override is unit-tested in isolation
    below (test_desk_backstop_floors_a_leg_whose_own_session_gap_reads_healthy), the one
    scenario (an extended closure the calendar module does not know as a holiday) where
    the per-leg session gap alone would NOT have caught it."""
    today = date(2026, 9, 2)
    old = "2026-08-01"   # >10 calendar days before today, and many real sessions too
    v2 = _v2(today=today, cn_asof=old, sb_asof=old, hk_asof=old,
             seats={"600104.SS": {"inst_net_yi": 1.0, "n_buy": 1, "n_sell": 0, "dir": "buy"}})
    by_id = {s["source_id"]: s for s in v2["sources"]}
    assert by_id["cn_large_order_proxy"]["status"] == fo_quality.STALE
    assert by_id["sb_aggregate"]["status"] == fo_quality.STALE
    assert by_id["hk_sb_holdings"]["status"] == fo_quality.STALE
    # exempt legs: nb_aggregate (HISTORICAL_ONLY) and lhb_inst_seats (event-window) never
    # get floored by the backstop, regardless of how stale everything else is.
    assert by_id["nb_aggregate"]["status"] == fo_quality.HISTORICAL_ONLY
    assert by_id["lhb_inst_seats"]["status"] == fo_quality.HEALTHY
    assert v2["publication_state"] == fo_quality.STALE


def test_desk_backstop_floors_a_leg_whose_own_session_gap_reads_healthy():
    """The scenario the wall-clock backstop exists for: an extended closure LONGER than
    any holiday the trading calendar knows about, where the per-leg session-gap math
    legitimately reads 0 missed sessions throughout (nothing traded, so nothing was
    "missed") — the backstop is the ONLY thing that still calls this STALE past 10
    elapsed calendar days (masterplan §5 / spec §1 last bullet, "the ONLY calendar-day
    rule"). Exercised directly against ``apply_desk_backstop`` with a pre-classified
    HEALTHY leg — the real per-leg classify_leg path cannot construct this case against
    the REAL calendars (their longest closure is Golden Week, ~8 days, inside the
    10-day budget), which is exactly why the backstop is a SEPARATE, wall-clock-only
    rule rather than something folded into the per-leg calendar math."""
    today = date(2026, 9, 2)
    old_date = "2026-08-01"   # 32 calendar days back
    healthy_leg = {"status": fo_quality.HEALTHY, "confidence": "HIGH", "reasons": [],
                  "gap_sessions": 0}
    lhb_leg = dict(healthy_leg)
    historical_leg = {"status": fo_quality.HISTORICAL_ONLY, "confidence": "HIGH",
                      "reasons": ["discontinued"], "gap_sessions": None}
    out = fo_quality.apply_desk_backstop(
        {"cn_large_order_proxy": healthy_leg, "lhb_inst_seats": lhb_leg,
        "nb_aggregate": historical_leg},
        {"cn_large_order_proxy": old_date, "lhb_inst_seats": old_date,
        "nb_aggregate": "2024-08-16"},
        today)
    assert out["cn_large_order_proxy"]["status"] == fo_quality.STALE
    assert "desk_backstop" in out["cn_large_order_proxy"]["reasons"]
    assert out["cn_large_order_proxy"]["confidence"] == "LOW"
    # exempt legs pass through UNCHANGED — same object, not even a new dict.
    assert out["lhb_inst_seats"] is lhb_leg
    assert out["nb_aggregate"] is historical_leg


def test_desk_backstop_does_not_fire_inside_its_own_budget():
    today = date(2026, 9, 2)
    healthy_leg = {"status": fo_quality.HEALTHY, "confidence": "HIGH", "reasons": [],
                  "gap_sessions": 0}
    out = fo_quality.apply_desk_backstop(
        {"cn_large_order_proxy": healthy_leg}, {"cn_large_order_proxy": "2026-08-25"}, today)
    assert out["cn_large_order_proxy"] is healthy_leg   # 8 days — inside budget, untouched


# ── F3: Golden Week — CN closure produces NO false staleness ────────────────────────────
def test_f3_golden_week_no_false_staleness_either_calendar():
    today = date(2026, 10, 5)   # inside the CN Golden Week closure (Oct 1-7)
    cn_last_before_closure = cn_calendar.last_session_on_or_before(date(2026, 9, 30))
    assert cn_last_before_closure.isoformat() == "2026-09-30"
    hk_today_session = hk_calendar.last_session_on_or_before(today)   # HK trades this week

    v2 = _v2(today=today, cn_asof=cn_last_before_closure.isoformat(),
             sb_asof=hk_today_session.isoformat(), hk_asof=hk_today_session.isoformat())
    by_id = {s["source_id"]: s for s in v2["sources"]}
    assert by_id["cn_large_order_proxy"]["status"] == fo_quality.HEALTHY
    assert by_id["sb_aggregate"]["status"] == fo_quality.HEALTHY
    assert by_id["hk_sb_holdings"]["status"] in (fo_quality.HEALTHY,)
    assert v2["publication_state"] == fo_quality.HEALTHY


# ── F4: coverage collapse — scored names at 50% of trailing median → DEGRADED ───────────
def test_f4_coverage_collapse_degrades_a_healthy_leg():
    today = date(2026, 9, 2)
    result = fo_quality.classify_leg(
        "cn_large_order_proxy", today.isoformat(), {"n_observed": 500},
        {"trailing_median": 1000, "trailing_n": 20}, today)
    assert result["status"] == fo_quality.DEGRADED
    assert "coverage_collapse" in result["reasons"]
    assert result["confidence"] == "LOW"


def test_f4_insufficient_history_skips_the_collapse_check():
    today = date(2026, 9, 2)
    result = fo_quality.classify_leg(
        "cn_large_order_proxy", today.isoformat(), {"n_observed": 10},
        {"trailing_median": 1000, "trailing_n": 3}, today)   # <5 sessions of history
    assert result["status"] == fo_quality.HEALTHY   # check skipped, not falsely collapsed
    assert result["confidence"] == "MEDIUM"          # but confidence is downgraded


# ── F5: unreadable as_of → UNAVAILABLE with reason; page still renders ──────────────────
def test_f5_unreadable_as_of_is_unavailable_not_silently_skipped():
    today = date(2026, 9, 2)
    result = fo_quality.classify_leg(
        "cn_large_order_proxy", "not-a-date", {"n_observed": 100}, {}, today)
    assert result["status"] == fo_quality.UNAVAILABLE
    assert result["reasons"] == ["unreadable_as_of"]
    assert result["confidence"] == "INSUFFICIENT"
    assert result["gap_sessions"] is None


# ── F6: northbound → HISTORICAL_ONLY (existing behavior preserved) ──────────────────────
def test_f6_northbound_is_always_historical_only_never_stale():
    today = date(2026, 9, 2)
    result = fo_quality.classify_leg("nb_aggregate", "2024-08-16", {}, {}, today)
    assert result["status"] == fo_quality.HISTORICAL_ONLY
    result_no_data = fo_quality.classify_leg("nb_aggregate", None, {}, {}, today)
    assert result_no_data["status"] == fo_quality.HISTORICAL_ONLY


# ── F7 (S1 repair) — date regression is a FLAG, never a status override ────────────────
# S1: a backward-moving effective_date can only ever WORSEN the gap-based status (floored
# at DEGRADED), never replace it outright. The literal "REVISED" status string is reserved
# for the one case where nothing else would have surfaced the leg's trouble: the gap verdict
# ALONE reads HEALTHY. Every leg also gains a "revised": True flag regardless of which
# branch fires, so a consumer can always tell a regression happened even when the status
# itself stayed DEGRADED/STALE.
def test_f7_regression_on_a_healthy_gap_reads_the_literal_revised_status():
    today = date(2026, 9, 2)   # a CN session day — gap 0 against its own date is HEALTHY
    result = fo_quality.classify_leg(
        "cn_large_order_proxy", "2026-09-02", {"n_observed": 100},
        {"prev_effective_date": "2026-09-03"}, today)   # 09-02 < 09-03: backward move
    assert result["gap_sessions"] == 0   # the gap verdict alone WOULD have been HEALTHY
    assert result["status"] == fo_quality.REVISED
    assert result["reasons"] == ["date_regression"]
    assert result["confidence"] == "LOW"
    assert result["revised"] is True


def test_f7_regression_on_a_degraded_gap_floors_at_degraded_never_masks_it_as_revised():
    """The S1 defect this repair closes: a leg that is ALREADY behind on the calendar and
    ALSO regressed must never read as the milder-looking bare "REVISED" — that would let a
    materially worse read (the number itself moved backward AND is stale) publish as if it
    were merely a benign correction."""
    today = date(2026, 9, 2)
    cn_newest = cn_calendar.last_session_on_or_before(today)
    one_behind = cn_calendar.session_n_back(cn_newest, 1)
    result = fo_quality.classify_leg(
        "cn_large_order_proxy", one_behind.isoformat(), {"n_observed": 100},
        {"prev_effective_date": "2026-09-03"}, today)   # regression on top of a 1-session gap
    assert result["gap_sessions"] == 1
    assert result["status"] == fo_quality.DEGRADED   # NEVER the literal "REVISED" string
    assert "date_regression" in result["reasons"]
    assert result["revised"] is True
    assert result["confidence"] == "LOW"


def test_f7_regression_on_a_stale_gap_stays_stale_never_downgrades_to_revised():
    today = date(2026, 9, 2)
    cn_newest = cn_calendar.last_session_on_or_before(today)
    twelve_behind = cn_calendar.session_n_back(cn_newest, 12)
    result = fo_quality.classify_leg(
        "cn_large_order_proxy", twelve_behind.isoformat(), {"n_observed": 100},
        {"prev_effective_date": "2026-09-03"}, today)
    assert result["gap_sessions"] == 12
    assert result["status"] == fo_quality.STALE   # a regression can only WORSEN, never mask
    assert "date_regression" in result["reasons"]
    assert result["revised"] is True


def test_ui_state_revised_word_only_reachable_when_status_is_not_stale_or_unavailable():
    """S1's ui_state guarantee, checked directly: the literal "revised" ui_state can only
    ever be reached via the literal "REVISED" status (which S1 restricts to the
    gap-verdict-was-HEALTHY case) — a STALE/UNAVAILABLE regressed leg's ui_state stays
    "stale"/"unavailable", never "revised"."""
    from engine.flow_observatory.contract import ui_state_from_status
    assert ui_state_from_status(fo_quality.REVISED) == "revised"
    assert ui_state_from_status(fo_quality.STALE) == "stale"
    assert ui_state_from_status(fo_quality.UNAVAILABLE) == "unavailable"


def test_publication_state_never_emits_the_literal_revised_value():
    """S1: 'publication_state rollup input maps any revised-flagged leg at min DEGRADED and
    NEVER emits a literal REVISED top-level value' — even when the ONLY non-healthy leg in
    the whole desk is literally REVISED (the highest-severity candidate by construction),
    the desk-wide rollup must read DEGRADED, never the bare string 'REVISED'."""
    result = fo_quality.publication_state(
        {"cn_large_order_proxy": "REVISED", "sb_aggregate": "HEALTHY",
        "hk_sb_holdings": "HEALTHY", "nb_aggregate": "HISTORICAL_ONLY"})
    assert result == fo_quality.DEGRADED
    assert result != "REVISED"


# ── F8: missing source WITH last-good state_log history → UNAVAILABLE + change row ──────
def test_f8_missing_source_with_history_is_unavailable_and_logs_a_change_row():
    log_rows = [{"session": "2026-09-01", "written_at": "x", "themes": {}, "aggregate": {},
               "market_read": {},
               "health": {"publication_state": "HEALTHY",
                          "legs": {"sb_aggregate": {"status": "HEALTHY",
                                                    "effective_date": "2026-09-01",
                                                    "coverage_n": 1}}}}]
    hist = fo_changes.leg_quality_history(log_rows, "sb_aggregate", "2026-09-02")
    assert hist["prev_effective_date"] == "2026-09-01"

    today = date(2026, 9, 2)
    result = fo_quality.classify_leg("sb_aggregate", None, {"n_observed": None}, {}, today)
    assert result["status"] == fo_quality.UNAVAILABLE

    cs = fo_changes.compute_changes(
        {"session": "2026-09-02", "themes": {}, "legs": {"sb_aggregate": "UNAVAILABLE"}},
        log_rows)
    assert cs["quality_transitions"] == [
        {"kind": "quality", "id": "sb_aggregate", "from_status": "HEALTHY",
         "to_status": "UNAVAILABLE"}]
    assert cs["material_change"] is True


# ── F9: missing source, NO history at all → UNAVAILABLE, no fabricated zero-flow ────────
def test_f9_missing_source_no_history_never_fakes_a_zero_flow_claim():
    today = date(2026, 9, 2)
    v2 = _v2(today=today, cn_asof=None, sb_asof=today.isoformat(), hk_asof=today.isoformat(),
             cn_names_n=0, ashare_sectors_rows=[])
    # ashare_names/ashare_sectors carry no as_of at all this run -> cn leg UNAVAILABLE
    by_id = {s["source_id"]: s for s in v2["sources"]}
    assert by_id["cn_large_order_proxy"]["status"] == fo_quality.UNAVAILABLE
    assert by_id["cn_large_order_proxy"]["coverage"]["n_observed"] is None
    assert v2["market_read"]["themes"]["quality"] == "unavailable"
    # the breadth object still declares an honest denominator (0 real themes this run,
    # never a fabricated positive/negative/neutral count standing in for "no data").
    themes_mr = v2["market_read"]["themes"]["absolute_breadth"]
    assert themes_mr["denominator"] == 0
    assert themes_mr["positive"] == themes_mr["negative"] == 0
    # the page still renders (never an empty "no flow" page) and says unavailable somewhere.
    html = _render(v2)
    assert "unavailable" in html or "不可用" in html


# ══════════════════════════════════════════════════════════════════════════════════════
# §5 test 2 — machine/UI agreement: F1's rendered page carries the stale chip, the
# section watermark, and the stale hero form — and NOT the healthy verdict sentence.
# ══════════════════════════════════════════════════════════════════════════════════════
def test_f1_rendered_page_shows_stale_chip_watermark_and_hero_form_not_healthy_verdict():
    today = date(2026, 9, 2)
    cn_newest = cn_calendar.last_session_on_or_before(today)
    cn_stale_date = cn_calendar.session_n_back(cn_newest, 12)
    v2 = _v2(today=today, cn_asof=cn_stale_date.isoformat(),
             sb_asof=today.isoformat(), hk_asof=today.isoformat())
    html = _render(v2)

    # trust chip: STALE class present, with the pinned state word.
    assert 'fv-src--stale' in html
    assert f"stale — showing {cn_stale_date.isoformat()}" in html
    assert f"已过期 · 显示{cn_stale_date.isoformat()}数据" in html

    # section watermark (quadrant + groups sections, both fed by cn_large_order_proxy).
    # NIT repair: `'fv-watermark' in html` used to be vacuous — the class name ALSO appears
    # verbatim in the page's own <style> block regardless of whether the macro ever fired,
    # so the assertion was true even on a page with NO watermark rendered. Assert the actual
    # rendered ELEMENT (the macro's own opening tag) instead.
    assert '<div class="fv-watermark">' in html
    assert f"Showing last good data from {cn_stale_date.isoformat()} — source behind." in html
    assert f"显示{cn_stale_date.isoformat()}最近有效数据 — 数据源滞后。" in html

    # hero stale form REPLACES the verdict sentence; the healthy sentence must be absent.
    assert "Source data is behind — showing the last good read from" in html
    assert "数据源滞后——显示" in html
    assert "Stand aside — data behind" in html
    assert "暂缓 — 数据滞后" in html
    hero_html = html.split('id="sources"')[0]
    assert "Large-order pressure ran" not in hero_html
    assert "Main-force flow was a net seller in all" not in hero_html


# ══════════════════════════════════════════════════════════════════════════════════════
# S4/S5/S6 — hero + watermark scoping repair (rendered-page tests)
# ══════════════════════════════════════════════════════════════════════════════════════
def test_s5_unavailable_cn_proxy_shows_the_unavailable_hero_form_never_prints_from_dash():
    """S5: when cn_large_order_proxy is UNAVAILABLE there is no date at all — the OLD hero
    code fell back through `_stale_leg.effective_date -> snap.as_of -> '—'`, which could
    print the literal, meaningless "showing the last good read from —." The unavailable
    form never mentions a date at all."""
    today = date(2026, 9, 2)
    v2 = _v2(today=today, cn_asof=None, sb_asof=today.isoformat(), hk_asof=today.isoformat(),
             cn_names_n=0, ashare_sectors_rows=[])
    by_id = {s["source_id"]: s for s in v2["sources"]}
    assert by_id["cn_large_order_proxy"]["status"] == fo_quality.UNAVAILABLE
    html = _render(v2)
    hero_html = html.split('id="sources"')[0]
    assert "from —" not in hero_html and "from None" not in hero_html
    assert "A-share flow source is unavailable — no current read." in hero_html
    assert "A股资金数据源不可用——暂无当前读数。" in hero_html
    assert "Stand aside — no data" in hero_html
    assert "暂缓 — 暂无数据" in hero_html
    # the STALE hero form's own copy must NOT also appear (mutually exclusive branches).
    assert "Source data is behind" not in hero_html


def test_s4_cross_border_stale_leg_leaves_the_hero_verdict_intact_and_watermarks_its_own_section():
    """The G-attack shape: cn_large_order_proxy is perfectly CURRENT (the hero's own data
    source), sb_aggregate is STALE. The hero verdict must stay the ORDINARY (non-stale)
    form — a cross-border leg's own trouble must never replace a verdict about a DIFFERENT,
    healthy leg — while #channels (sb_aggregate's own section) IS watermarked and the small
    hero notice chip appears."""
    today = date(2026, 9, 2)
    sb_newest = cn_calendar.last_session_on_or_before(today)   # sb anchors off its own date
    stale_sb = date(2026, 8, 1)   # far enough back to read STALE on the HK calendar too
    v2 = _v2(today=today, cn_asof=today.isoformat(), sb_asof=stale_sb.isoformat(),
             hk_asof=today.isoformat())
    by_id = {s["source_id"]: s for s in v2["sources"]}
    assert by_id["cn_large_order_proxy"]["status"] == fo_quality.HEALTHY
    assert by_id["sb_aggregate"]["status"] == fo_quality.STALE
    html = _render(v2)
    hero_html = html.split('id="sources"')[0]
    # the verdict sentence stayed intact — no stale/unavailable hero replacement fired.
    assert "Source data is behind" not in hero_html
    assert "A-share flow source is unavailable" not in hero_html
    # the small cross-border notice chip DID fire.
    assert "Cross-border data behind — see sources" in hero_html
    assert "跨境数据滞后——见数据来源" in hero_html
    # #channels (sb_aggregate's OWN section) is watermarked; #quadrant/#groups (cn proxy's
    # sections) are NOT — the scoping split is the whole point of S4.
    channels_html = html.split('id="channels"')[1] if 'id="channels"' in html else ""
    quadrant_html = html.split('id="quadrant"')[1].split('id="groups"')[0] if 'id="quadrant"' in html else ""
    assert '<div class="fv-watermark">' in channels_html
    assert '<div class="fv-watermark">' not in quadrant_html


def test_s6_unavailable_fed_section_shows_the_unavailable_watermark_wording():
    today = date(2026, 9, 2)
    v2 = _v2(today=today, cn_asof=today.isoformat(), sb_asof=None, hk_asof=today.isoformat())
    by_id = {s["source_id"]: s for s in v2["sources"]}
    assert by_id["sb_aggregate"]["status"] == fo_quality.UNAVAILABLE
    html = _render(v2)
    channels_html = html.split('id="channels"')[1] if 'id="channels"' in html else ""
    assert "Source unavailable — this section has no current data." in channels_html
    assert "数据源不可用——本节暂无当前数据。" in channels_html


def test_b4_light_stale_chip_uses_a_diagonal_hatch_mechanically_distinct_from_behind():
    """B4 repair: light STALE must be a mechanically distinct treatment (diagonal hatch on
    a deepened brown-amber ink) from light DEGRADED/"behind" (a flat tint) — not the same
    mechanism at adjacent parameters. Checked at the CSS-source level (the mechanism is
    identical across every render, so this does not need a screenshot to pin regression);
    the actual visual dual-theme evidence lives in verify_shots/flow_observatory/w2/."""
    today = date(2026, 9, 2)
    cn_newest = cn_calendar.last_session_on_or_before(today)
    cn_stale_date = cn_calendar.session_n_back(cn_newest, 12)
    v2 = _v2(today=today, cn_asof=cn_stale_date.isoformat(),
             sb_asof=today.isoformat(), hk_asof=today.isoformat())
    html = _render(v2)
    # the light-scoped deepened-ink expression (var(--warn) mixed with var(--ink) — NOT a
    # hand-picked hex; inlined at each use site rather than a named custom property, since
    # the design-system law forbids a NEW literal-valued custom property outside theme.css
    # and this page does not itself link theme.css — see the CSS comment above .fv-src--stale).
    assert "color-mix(in srgb,var(--warn) 65%,var(--ink))" in html
    assert "repeating-linear-gradient(-45deg" in html   # the hatch mechanism itself
    # the light "behind" (DEGRADED) rule stays a flat color-mix tint — no hatch keyword
    # anywhere near its own selector (a crude but effective mechanical-distinctness check:
    # the hatch gradient function name must not appear inside the --behind rule's own text).
    behind_rule = html.split('.fv-src--behind{')[1].split('}')[0] if '.fv-src--behind{' in html else ""
    assert "repeating-linear-gradient" not in behind_rule


# ══════════════════════════════════════════════════════════════════════════════════════
# §5 test 3 — holiday fixture (F3) produces zero DEGRADED/STALE (both calendars)
# ══════════════════════════════════════════════════════════════════════════════════════
def test_golden_week_produces_zero_degraded_or_stale_statuses():
    today = date(2026, 10, 5)
    cn_last = cn_calendar.last_session_on_or_before(date(2026, 9, 30))
    hk_today_session = hk_calendar.last_session_on_or_before(today)
    v2 = _v2(today=today, cn_asof=cn_last.isoformat(),
             sb_asof=hk_today_session.isoformat(), hk_asof=hk_today_session.isoformat())
    bad = [s for s in v2["sources"] if s["status"] in (fo_quality.DEGRADED, fo_quality.STALE)]
    assert bad == [], f"unexpected degraded/stale legs during Golden Week: {bad}"


# ══════════════════════════════════════════════════════════════════════════════════════
# §5 test 4 — trading-day gap math: a weekend gap ≠ staleness; a 1-session CN gap ≠ a
# 1-session HK gap on the SAME two calendar dates (independent calendars, spec §1).
# ══════════════════════════════════════════════════════════════════════════════════════
def test_weekend_gap_is_not_staleness():
    friday = date(2026, 9, 4)     # a Friday CN/HK trading day
    sunday = date(2026, 9, 6)     # weekend, not itself a session
    assert cn_calendar.is_session(friday) and not cn_calendar.is_session(sunday)
    result = fo_quality.classify_leg("cn_large_order_proxy", friday.isoformat(),
                                     {"n_observed": 100}, {}, sunday)
    assert result["status"] == fo_quality.HEALTHY
    assert result["gap_sessions"] == 0


def test_same_two_calendar_dates_gap_differently_on_cn_vs_hk():
    """2026-12-25 is a CN trading day (no Christmas holiday) but an HK holiday; 2026-12-26
    is a weekend for both. Same effective_date/today pair -> CN sees a 1-session gap
    (DEGRADED), HK sees a 0-session gap (HEALTHY) — proof the two legs never share a
    calendar (spec §1: "trading-day math ... NEVER the same calendar")."""
    effective = date(2026, 12, 24)
    today = date(2026, 12, 26)
    assert cn_calendar.is_session(date(2026, 12, 25)) is True
    assert hk_calendar.is_session(date(2026, 12, 25)) is False

    cn_result = fo_quality.classify_leg("cn_large_order_proxy", effective.isoformat(),
                                        {"n_observed": 100}, {}, today)
    hk_result = fo_quality.classify_leg("sb_aggregate", effective.isoformat(),
                                        {"n_observed": 1}, {}, today)
    assert cn_result["gap_sessions"] == 1 and cn_result["status"] == fo_quality.DEGRADED
    assert hk_result["gap_sessions"] == 0 and hk_result["status"] == fo_quality.HEALTHY


# ══════════════════════════════════════════════════════════════════════════════════════
# B1 repair — the real defect: the OLD gap math walked `last_session_on_or_before(today)`
# against a bare calendar date, which (a) counts a session that has not yet CLOSED as
# already published (no settle-buffer awareness at all) and (b) fed a bare UTC date
# straight into an Asia calendar with no timezone conversion. Every test below constructs
# a REAL tz-aware UTC `now` instant and checks the calendar-correct answer.
# ══════════════════════════════════════════════════════════════════════════════════════
def test_b1a_pre_close_session_morning_build_holding_yesterdays_bar_is_healthy():
    """The exact defect this repair closes: a build that runs at 09:00 CST on a session
    day (BEFORE that day's 17:00 close+settle) must not treat today's still-open session as
    already-published. Store holds YESTERDAY's (the last CLOSED session's) bar -> HEALTHY,
    gap 0. Under the OLD code (`last_session_on_or_before(today_d)` on the bare UTC date),
    this same instant read gap=1/DEGRADED — over-reporting staleness by exactly one session,
    which is the "gap math counts an unclosed session" defect named in the mission brief.
    """
    now = datetime(2026, 9, 2, 1, 0, 0, tzinfo=timezone.utc)   # 09:00 CST — market open, not closed
    assert now.astimezone(cn_calendar.CST).time().hour == 9
    result = fo_quality.classify_leg("cn_large_order_proxy", "2026-09-01",
                                     {"n_observed": 100}, {}, now)
    assert result["status"] == fo_quality.HEALTHY
    assert result["gap_sessions"] == 0


def test_b1b_monday_morning_build_holding_fridays_bar_is_healthy():
    """Monday pre-close (before Monday's own session has closed) -> the expected session is
    still FRIDAY's, not Monday's — a weekend must not manufacture a phantom gap either."""
    now = datetime(2026, 8, 31, 0, 30, 0, tzinfo=timezone.utc)   # 08:30 CST Monday, pre-close
    result = fo_quality.classify_leg("cn_large_order_proxy", "2026-08-28",   # last Friday
                                     {"n_observed": 100}, {}, now)
    assert result["status"] == fo_quality.HEALTHY
    assert result["gap_sessions"] == 0


def test_b1c_post_close_pre_collection_window_reads_degraded_not_stale_or_healthy():
    """After a session day's close+settle has passed, that day's own bar IS expected —
    a store still holding only the PRIOR session's bar (collection has not run yet this
    evening) legitimately reads a 1-session gap. This is the honest DEGRADED window between
    a market's close and the nightly collector's run — not a bug, and asserted here as
    ACCEPTABLE (not something to silence): a build in this window should say "one session
    behind", not claim HEALTHY (which would hide a real, if temporary, lag) and not claim
    STALE (which would over-alarm for an ordinary same-evening collection delay)."""
    now = datetime(2026, 9, 2, 10, 0, 0, tzinfo=timezone.utc)   # 18:00 CST — well past close+settle
    result = fo_quality.classify_leg("cn_large_order_proxy", "2026-09-01",   # T-1, not yet T
                                     {"n_observed": 100}, {}, now)
    assert result["gap_sessions"] == 1
    assert result["status"] == fo_quality.DEGRADED


def test_b1d_a_2300_utc_build_does_not_under_or_over_count_on_either_calendar():
    """Pins one concrete instant (23:00 UTC, 2026-12-25) where the UTC calendar DATE (Dec
    25, a CN session day) differs from the LOCAL CST/HKT date the instant actually falls on
    (Dec 26, 07:00 local — both zones are UTC+8) — the exact shape that would silently break
    if a bare UTC date were substituted for a real local-time conversion. CN and HK read
    DIFFERENT answers from the SAME instant because Dec 25 is a CN session but an HK
    holiday (matching test_same_two_calendar_dates_gap_differently_on_cn_vs_hk's fixture),
    proving both calendars route the same `now` through their OWN independent tz handling
    rather than a shared/borrowed date."""
    now = datetime(2026, 12, 25, 23, 0, 0, tzinfo=timezone.utc)
    assert now.astimezone(cn_calendar.CST) == now.astimezone(hk_calendar.HKT)   # same offset
    assert now.astimezone(cn_calendar.CST).date() == date(2026, 12, 26)   # local date rolled over
    assert cn_calendar.expected_last_session(now) == date(2026, 12, 25)   # CN: Dec25 was a session
    assert hk_calendar.expected_last_session(now) == date(2026, 12, 24)   # HK: Dec25 was a holiday

    cn_result = fo_quality.classify_leg("cn_large_order_proxy", "2026-12-24",
                                        {"n_observed": 100}, {}, now)
    hk_result = fo_quality.classify_leg("sb_aggregate", "2026-12-24",
                                        {"n_observed": 1}, {}, now)
    assert cn_result["gap_sessions"] == 1 and cn_result["status"] == fo_quality.DEGRADED
    assert hk_result["gap_sessions"] == 0 and hk_result["status"] == fo_quality.HEALTHY


# ══════════════════════════════════════════════════════════════════════════════════════
# §5 test 5 — worst-of rollup excludes HISTORICAL_ONLY; S2 caps (not excludes) lhb_inst_seats
# ══════════════════════════════════════════════════════════════════════════════════════
def test_publication_state_excludes_historical_only_legs():
    # every REAL leg is HISTORICAL_ONLY/event-window -> desk itself is HISTORICAL_ONLY,
    # never a fabricated HEALTHY for a desk with nothing live to be healthy about.
    assert fo_quality.publication_state(
        {"nb_aggregate": "HISTORICAL_ONLY", "lhb_inst_seats": "HEALTHY"}) == "HISTORICAL_ONLY"
    assert fo_quality.publication_state(
        {"cn_large_order_proxy": "STALE", "sb_aggregate": "DEGRADED",
        "nb_aggregate": "HISTORICAL_ONLY", "lhb_inst_seats": "HEALTHY"}) == "STALE"


def test_s2_lhb_inst_seats_enters_the_rollup_capped_at_degraded_not_excluded():
    """S2 ruling: an UNAVAILABLE (unreadable) lhb_inst_seats really does degrade the desk,
    so it now ENTERS the worst-of rollup — but its contribution is CAPPED at DEGRADED
    severity/value, so the event-window leg alone can never headline the whole page as
    STALE/UNAVAILABLE while every primary lens (large-order proxy, southbound, holdings) is
    current. Both shapes required by the mission: (1) the cap FIRING (all other legs
    healthy, lhb unavailable -> DEGRADED, not UNAVAILABLE); (2) the cap NEVER outranking a
    genuinely worse live leg (a real STALE leg still wins over the capped lhb contribution).
    """
    # shape 1: the cap fires — lhb's own UNAVAILABLE would be severity 3 uncapped, but caps
    # down to DEGRADED (severity 1) since every other live leg is HEALTHY.
    assert fo_quality.publication_state(
        {"cn_large_order_proxy": "HEALTHY", "sb_aggregate": "HEALTHY",
        "hk_sb_holdings": "HEALTHY", "lhb_inst_seats": "UNAVAILABLE",
        "nb_aggregate": "HISTORICAL_ONLY"}) == fo_quality.DEGRADED
    # shape 2: a real STALE leg still wins — the capped lhb contribution never outranks it.
    assert fo_quality.publication_state(
        {"cn_large_order_proxy": "STALE", "lhb_inst_seats": "UNAVAILABLE"}) == fo_quality.STALE
    # a HEALTHY lhb_inst_seats (the ordinary case) contributes nothing at all — unchanged.
    assert fo_quality.publication_state(
        {"cn_large_order_proxy": "HEALTHY", "lhb_inst_seats": "HEALTHY"}) == fo_quality.HEALTHY


# ══════════════════════════════════════════════════════════════════════════════════════
# §5 test 6 — STALE leg -> market_read.themes.quality == "stale"; validate() rejects a
# payload claiming HEALTHY publication_state over a STALE proxy leg.
# ══════════════════════════════════════════════════════════════════════════════════════
def test_stale_proxy_sets_market_read_quality_and_validate_rejects_healthy_over_it():
    today = date(2026, 9, 2)
    cn_newest = cn_calendar.last_session_on_or_before(today)
    cn_stale_date = cn_calendar.session_n_back(cn_newest, 12)
    v2 = _v2(today=today, cn_asof=cn_stale_date.isoformat(),
             sb_asof=today.isoformat(), hk_asof=today.isoformat())
    assert v2["market_read"]["themes"]["quality"] == "stale"
    assert v2["market_read"]["names"]["quality"] == "stale"
    validate(v2)   # must NOT raise — the payload is internally consistent

    tampered = dict(v2)
    tampered["publication_state"] = "HEALTHY"   # lie: claim healthy over a STALE proxy
    with pytest.raises(ContractError):
        validate(tampered)


def test_validate_rejects_an_unknown_status_value():
    today = date(2026, 9, 2)
    v2 = _v2(today=today, cn_asof=today.isoformat(), sb_asof=today.isoformat(),
             hk_asof=today.isoformat())
    v2["sources"][0]["status"] = "SORT_OF_OK"
    with pytest.raises(ContractError):
        validate(v2)


def test_validate_rejects_publication_state_inconsistent_with_worst_of():
    today = date(2026, 9, 2)
    v2 = _v2(today=today, cn_asof=today.isoformat(), sb_asof=today.isoformat(),
             hk_asof=today.isoformat())
    assert v2["publication_state"] == "HEALTHY"
    v2["publication_state"] = "DEGRADED"   # inconsistent with an all-HEALTHY sources[]
    with pytest.raises(ContractError):
        validate(v2)


# ══════════════════════════════════════════════════════════════════════════════════════
# S3 — validate() hardening: five checks, each with its own failing-first tamper below.
# ══════════════════════════════════════════════════════════════════════════════════════
def _healthy_v2():
    today = date(2026, 9, 2)
    return _v2(today=today, cn_asof=today.isoformat(), sb_asof=today.isoformat(),
              hk_asof=today.isoformat())


def test_s3a_validate_rejects_a_null_status_on_any_source():
    v2 = _healthy_v2()
    validate(v2)   # must NOT raise before the tamper
    v2["sources"][0]["status"] = None
    with pytest.raises(ContractError):
        validate(v2)


def test_s3b_validate_rejects_a_payload_missing_publication_state_entirely():
    v2 = _healthy_v2()
    del v2["publication_state"]   # previously only checked "if present" — a soft miss
    with pytest.raises(ContractError):
        validate(v2)


def test_s3c_validate_rejects_market_read_quality_not_reflecting_an_unavailable_proxy():
    """The pre-repair check only ever covered the STALE case; an UNAVAILABLE proxy's
    market_read.quality going missing/wrong went unnoticed by validate() (even though
    contract.build_v2 already sets it correctly in production)."""
    today = date(2026, 9, 2)
    v2 = _v2(today=today, cn_asof=None, sb_asof=today.isoformat(), hk_asof=today.isoformat(),
             cn_names_n=0, ashare_sectors_rows=[])
    by_id = {s["source_id"]: s for s in v2["sources"]}
    assert by_id["cn_large_order_proxy"]["status"] == fo_quality.UNAVAILABLE
    assert v2["market_read"]["themes"]["quality"] == "unavailable"
    validate(v2)   # must NOT raise — production already sets this correctly
    v2["market_read"]["themes"]["quality"] = "healthy"   # lie: mask the unavailable proxy
    with pytest.raises(ContractError):
        validate(v2)


def test_s3d_validate_rejects_health_publication_state_disagreeing_with_top_level():
    v2 = _healthy_v2()
    validate(v2)   # must NOT raise before the tamper
    v2["health"]["publication_state"] = "STALE"   # disagrees with the top-level HEALTHY
    with pytest.raises(ContractError):
        validate(v2)


def test_s3e_validate_rejects_a_ui_state_disagreeing_with_its_own_status():
    v2 = _healthy_v2()
    validate(v2)   # must NOT raise before the tamper
    v2["sources"][0]["ui_state"] = "stale"   # status is still HEALTHY/"current" underneath
    with pytest.raises(ContractError):
        validate(v2)


# ══════════════════════════════════════════════════════════════════════════════════════
# §5 test 7 (B2 repair) — escalation is keyed on BUILD RUNS (written_at date), NEVER the
# market session: a frozen `session` must not also freeze the escalation streak.
# ══════════════════════════════════════════════════════════════════════════════════════
def test_consecutive_degraded_sessions_walks_runs_not_the_market_session():
    """The accelerator lives in the newest row's health.runs (B2) — not keyed by `session`.
    Three runs (08-31, 09-01, the current 09-02 run) all non-healthy -> streak 3, even
    though every row here would share the SAME frozen `session` in the real #4676 shape
    this repair exists to fix."""
    log_rows = [
        {"session": "2026-07-24", "written_at": "2026-09-01T02:00:00+00:00",
         "health": {"publication_state": "DEGRADED",
                    "runs": [{"run_date": "2026-08-31", "publication_state": "STALE", "legs": {}},
                             {"run_date": "2026-09-01", "publication_state": "DEGRADED", "legs": {}}]}},
    ]
    n = fo_quality.consecutive_degraded_sessions(log_rows, "2026-09-02", "STALE")
    assert n == 3   # 08-31, 09-01, and the current run (09-02) all non-healthy


def test_consecutive_degraded_sessions_stops_at_the_first_healthy_run():
    log_rows = [
        {"session": "s", "written_at": "2026-09-01T02:00:00+00:00",
         "health": {"runs": [{"run_date": "2026-08-30", "publication_state": "HEALTHY", "legs": {}},
                             {"run_date": "2026-08-31", "publication_state": "STALE", "legs": {}}]}},
    ]
    n = fo_quality.consecutive_degraded_sessions(log_rows, "2026-09-01", "STALE")
    assert n == 2   # 08-31 + current; 08-30 HEALTHY breaks the backward walk


def test_a_single_bad_run_does_not_escalate():
    n = fo_quality.consecutive_degraded_sessions([], "2026-09-02", "DEGRADED")
    assert n == 1
    assert fo_quality.should_escalate({"consecutive_degraded_sessions": 1}) is False
    assert fo_quality.should_escalate({"consecutive_degraded_sessions": 2}) is True


def test_leg_consecutive_bad_runs_tracks_per_leg_not_the_desk_wide_count():
    """B2: 'per-leg run-streaks tracked the same way' — a leg's own streak can legitimately
    differ from the desk-wide worst-of rollup. cn has been bad for 3 runs; sb only went bad
    on the CURRENT run — its own streak must read 1, not borrow cn's 3."""
    log_rows = [
        {"session": "s", "written_at": "2026-09-01T02:00:00+00:00",
         "health": {"runs": [
             {"run_date": "2026-08-31", "publication_state": "STALE",
              "legs": {"cn_large_order_proxy": "STALE", "sb_aggregate": "HEALTHY"}},
             {"run_date": "2026-09-01", "publication_state": "STALE",
              "legs": {"cn_large_order_proxy": "STALE", "sb_aggregate": "HEALTHY"}},
         ]}},
    ]
    cn_n = fo_quality.leg_consecutive_bad_runs(log_rows, "cn_large_order_proxy", "2026-09-02", "STALE")
    sb_n = fo_quality.leg_consecutive_bad_runs(log_rows, "sb_aggregate", "2026-09-02", "DEGRADED")
    assert cn_n == 3
    assert sb_n == 1


def test_builder_emits_column_zero_error_annotation_with_per_leg_run_count(capsys):
    """B2/SF-8 repair: the annotation wording is '<leg> <status> ×<n> runs' (the false
    'for N sessions' claim is gone), and each bad leg's own ``n`` comes from its OWN run
    streak (``leg_consecutive_bad_runs``), never a borrowed desk-wide count."""
    from scripts import build_flow_velocity as bfv

    log_rows = [
        {"session": "s", "written_at": "2026-09-01T02:00:00+00:00",
         "health": {"runs": [
             {"run_date": "2026-08-31", "publication_state": "STALE",
              "legs": {"cn_large_order_proxy": "STALE"}},
         ]}},
    ]
    v2_snap = {
        "health": {"publication_state": "STALE", "consecutive_degraded_sessions": 2,
                  "reasons": ["one_session_behind"]},
        "sources": [{"source_id": "cn_large_order_proxy", "status": "STALE"},
                   {"source_id": "sb_aggregate", "status": "HEALTHY"}],
    }
    bfv._escalate_if_degraded(v2_snap, log_rows=log_rows, run_date="2026-09-02")
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    ann = [ln for ln in lines if ln.startswith("::")]
    assert len(ann) == 1, f"expected exactly 1 column-zero annotation, got {lines}"
    assert ann[0] == ("::error title=flow-observatory-degraded::cn_large_order_proxy "
                      "STALE ×2 runs")


def test_builder_is_silent_when_only_one_run_is_degraded(capsys):
    from scripts import build_flow_velocity as bfv

    v2_snap = {"health": {"publication_state": "DEGRADED", "consecutive_degraded_sessions": 1,
                          "reasons": []},
              "sources": [{"source_id": "cn_large_order_proxy", "status": "DEGRADED"}]}
    bfv._escalate_if_degraded(v2_snap, log_rows=[], run_date="2026-09-02")
    assert not [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]


# ── B2 freeze simulation — the real #4676 shape: frozen market_session, advancing builds ──
def test_freeze_simulation_escalation_fires_from_night_2_onward(tmp_path):
    """Simulates the #4676 12-night freeze end to end through the REAL append_state_log +
    quality pipeline: the market ``session`` (and every leg date) stays FROZEN across 12
    simulated nightly builds, but each night is still a DISTINCT build RUN (advancing
    written_at). Before B2, ``consecutive_degraded_sessions`` walked ``session`` and could
    never see past night 1 (the session never changes, so the streak could never grow past
    1) — under the B2 fix, escalation fires from night 2 onward instead."""
    data_root = tmp_path
    frozen_session = "2026-07-24"   # the market never advances during the freeze
    leg_results = {"cn_large_order_proxy": "STALE", "sb_aggregate": "HEALTHY",
                   "hk_sb_holdings": "HEALTHY", "nb_aggregate": "HISTORICAL_ONLY",
                   "lhb_inst_seats": "HEALTHY"}
    escalated_nights = []
    for night in range(1, 13):
        run_date = f"2026-08-{night:02d}"
        written_at = f"{run_date}T02:00:00+00:00"
        log_rows = fo_changes.read_state_log(data_root)   # PRIOR runs only — this run isn't in yet
        pub_state = fo_quality.publication_state(leg_results)
        assert pub_state == fo_quality.STALE
        health = fo_quality.compute_health(
            pub_state, {lid: {"status": s, "reasons": []} for lid, s in leg_results.items()},
            log_rows, run_date)
        if fo_quality.should_escalate(health):
            escalated_nights.append(night)
        entry = {"themes": {}, "aggregate": {}, "market_read": {},
                "health": {"publication_state": pub_state,
                           "legs": {lid: {"status": s} for lid, s in leg_results.items()}}}
        fo_changes.append_state_log(frozen_session, entry, data_root, require_lane=False,
                                    written_at=written_at)
    assert 1 not in escalated_nights   # night 1: only 1 run measured so far, no escalation
    assert escalated_nights == list(range(2, 13))   # every remaining night escalates


# ══════════════════════════════════════════════════════════════════════════════════════
# §5 test 8 — UNAVAILABLE never yields zero-filled breadth
# ══════════════════════════════════════════════════════════════════════════════════════
def test_unavailable_proxy_never_yields_a_fabricated_positive_zero_breadth():
    """A real absent-panel run: 0 themes this build (denominator 0, honestly), never a
    faked '0 positive / 0 negative / all-neutral' reading that would look like a measured
    'flow is flat' verdict instead of 'we have nothing to measure this run'."""
    today = date(2026, 9, 2)
    v2 = _v2(today=today, cn_asof=None, sb_asof=today.isoformat(), hk_asof=today.isoformat(),
             cn_names_n=0, ashare_sectors_rows=[])
    themes_mr = v2["market_read"]["themes"]
    assert themes_mr["quality"] == "unavailable"
    for bucket in ("absolute_breadth", "relative_breadth"):
        b = themes_mr[bucket]
        assert b["positive"] + b["negative"] + b["neutral"] + b["missing"] == b["denominator"]
    assert v2["sources"][0]["source_id"] == "cn_large_order_proxy"
    assert v2["sources"][0]["status"] == fo_quality.UNAVAILABLE
    assert v2["sources"][0]["coverage"]["n_observed"] is None   # never coerced to 0


# ══════════════════════════════════════════════════════════════════════════════════════
# §5 test 10 — existing suites stay green (desk_guard tests untouched, out of scope)
# ══════════════════════════════════════════════════════════════════════════════════════
def test_desk_guard_constants_are_untouched_by_this_wave():
    """OUT OF SCOPE guard: this wave must never edit lib/desk_guard.py's own budgets — its
    advisory path stands unchanged (spec §1: 'desk_guard's existing 4-day/10-day constants
    stay untouched for its own advisory path')."""
    from lib import desk_guard
    assert desk_guard.LEG_LAG_MAX_DAYS == 4
    assert desk_guard.DESK_MAX_AGE_DAYS == 10


# ══════════════════════════════════════════════════════════════════════════════════════
# additional contract-shape coverage: ui_state mapping table (spec §2, exact)
# ══════════════════════════════════════════════════════════════════════════════════════
def test_ui_state_mapping_table_is_exact():
    from engine.flow_observatory.contract import ui_state_from_status
    assert ui_state_from_status("HEALTHY") == "current"
    assert ui_state_from_status("HEALTHY", ["expected_t_minus_1"]) == "expected_lag"
    assert ui_state_from_status("DEGRADED") == "behind"
    assert ui_state_from_status("STALE") == "stale"
    assert ui_state_from_status("UNAVAILABLE") == "unavailable"
    assert ui_state_from_status("HISTORICAL_ONLY") == "historical"
    assert ui_state_from_status("REVISED") == "revised"


def _hk_session_n_back(last, n):
    """hk_calendar has no session_n_back (unlike cn_calendar) — walk backward by hand."""
    from datetime import timedelta
    d, found = last, 0
    while found < n:
        d -= timedelta(days=1)
        if hk_calendar.is_session(d):
            found += 1
    return d


def test_hk_sb_holdings_expected_t_minus_1_is_healthy_not_degraded():
    today = date(2026, 9, 2)
    hk_newest = hk_calendar.last_session_on_or_before(today)
    hk_t_minus_1 = _hk_session_n_back(hk_newest, 1)
    result = fo_quality.classify_leg("hk_sb_holdings", hk_t_minus_1.isoformat(),
                                     {"n_observed": 400}, {}, today)
    assert result["status"] == fo_quality.HEALTHY
    assert result["reasons"] == ["expected_t_minus_1"]
    from engine.flow_observatory.contract import ui_state_from_status
    assert ui_state_from_status(result["status"], result["reasons"]) == "expected_lag"


def test_lhb_inst_seats_absent_is_unavailable_present_is_healthy_event_window():
    today = date(2026, 9, 2)
    absent = fo_quality.classify_leg("lhb_inst_seats", None, {}, {"present": False}, today)
    assert absent["status"] == fo_quality.UNAVAILABLE
    present = fo_quality.classify_leg("lhb_inst_seats", "2026-08-20",
                                      {"n_observed": 5}, {"present": True}, today)
    assert present["status"] == fo_quality.HEALTHY
    assert present["reasons"] == ["event_window"]
    # a quiet event-window stretch never reads STALE regardless of how old the date is.
    stale_shaped = fo_quality.classify_leg("lhb_inst_seats", "2020-01-01",
                                           {"n_observed": 5}, {"present": True}, today)
    assert stale_shaped["status"] == fo_quality.HEALTHY
