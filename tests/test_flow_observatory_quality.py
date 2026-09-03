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

from datetime import date

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
def _snap(*, today: date, cn_asof: str | None, sb_asof: str | None, hk_asof: str | None,
         sb_live: bool = True, seats: dict | None = None, seats_asof: str | None = "2026-08-30",
         cn_names_n: int = 100, ashare_sectors_rows=None) -> dict:
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
        "seats_by_ticker": seats or {},
        "seats_as_of": seats_asof,
        "pulse": None, "confluence": None, "momentum": None,
        "note": "n",
    }


def _v2(*, today: date, log_rows=None, **snap_kwargs) -> dict:
    snap = _snap(today=today, **snap_kwargs)
    return build_v2(snap, log_rows=log_rows or [], market_session=snap.get("as_of"),
                    generated_at=f"{today.isoformat()}T12:00:00+00:00", today=today,
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


# ── F7: date regression → REVISED ────────────────────────────────────────────────────────
def test_f7_date_regression_is_revised():
    today = date(2026, 9, 2)
    result = fo_quality.classify_leg(
        "cn_large_order_proxy", "2026-08-28", {"n_observed": 100},
        {"prev_effective_date": "2026-09-01"}, today)   # 08-28 < 09-01: backward move
    assert result["status"] == fo_quality.REVISED
    assert result["reasons"] == ["date_regression"]
    assert result["confidence"] == "LOW"


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
    assert 'fv-watermark' in html
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
# §5 test 5 — worst-of rollup excludes HISTORICAL_ONLY and event-window legs
# ══════════════════════════════════════════════════════════════════════════════════════
def test_publication_state_excludes_historical_only_and_event_window_legs():
    # every REAL leg is HISTORICAL_ONLY/event-window -> desk itself is HISTORICAL_ONLY,
    # never a fabricated HEALTHY for a desk with nothing live to be healthy about.
    assert fo_quality.publication_state(
        {"nb_aggregate": "HISTORICAL_ONLY", "lhb_inst_seats": "HEALTHY"}) == "HISTORICAL_ONLY"
    # a STALE lhb_inst_seats-adjacent read must never leak in — lhb_inst_seats has no STALE
    # state by construction (classify_leg never emits it), but the ROLLUP must ALSO ignore
    # it even if some future caller passed a bogus value for it.
    assert fo_quality.publication_state(
        {"cn_large_order_proxy": "HEALTHY", "lhb_inst_seats": "STALE",
        "nb_aggregate": "HISTORICAL_ONLY"}) == "HEALTHY"
    assert fo_quality.publication_state(
        {"cn_large_order_proxy": "STALE", "sb_aggregate": "DEGRADED",
        "nb_aggregate": "HISTORICAL_ONLY", "lhb_inst_seats": "HEALTHY"}) == "STALE"


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
# §5 test 7 — escalation: consecutive_degraded_sessions >= 2 emits the ::error line
# ══════════════════════════════════════════════════════════════════════════════════════
def test_consecutive_degraded_sessions_walks_back_through_the_log():
    log_rows = [
        {"session": "2026-08-31", "health": {"publication_state": "STALE"}},
        {"session": "2026-09-01", "health": {"publication_state": "DEGRADED"}},
    ]
    n = fo_quality.consecutive_degraded_sessions(log_rows, "2026-09-02", "STALE")
    assert n == 3   # 08-31, 09-01, and the current session all non-healthy


def test_a_single_bad_session_does_not_escalate():
    n = fo_quality.consecutive_degraded_sessions([], "2026-09-02", "DEGRADED")
    assert n == 1
    assert fo_quality.should_escalate({"consecutive_degraded_sessions": 1}) is False
    assert fo_quality.should_escalate({"consecutive_degraded_sessions": 2}) is True


def test_builder_emits_column_zero_error_annotation_on_escalation(capsys):
    from scripts import build_flow_velocity as bfv

    v2_snap = {
        "health": {"publication_state": "STALE", "consecutive_degraded_sessions": 2,
                  "reasons": ["one_session_behind"]},
        "sources": [{"source_id": "cn_large_order_proxy", "status": "STALE"},
                   {"source_id": "sb_aggregate", "status": "HEALTHY"}],
    }
    bfv._escalate_if_degraded(v2_snap)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    ann = [ln for ln in lines if ln.startswith("::")]
    assert len(ann) == 1, f"expected exactly 1 column-zero annotation, got {lines}"
    assert ann[0].startswith("::error title=flow-observatory-degraded::cn_large_order_proxy "
                             "STALE for 2 sessions")


def test_builder_is_silent_when_only_one_session_is_degraded(capsys):
    from scripts import build_flow_velocity as bfv

    v2_snap = {"health": {"publication_state": "DEGRADED", "consecutive_degraded_sessions": 1,
                          "reasons": []},
              "sources": [{"source_id": "cn_large_order_proxy", "status": "DEGRADED"}]}
    bfv._escalate_if_degraded(v2_snap)
    assert not [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]


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
