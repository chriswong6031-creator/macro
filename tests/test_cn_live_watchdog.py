"""CN-PR-4 — sentinel surface + rescue classifier."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from lib import cn_calendar
from scripts import cn_live_rescue as rescue
from scripts import freshness_sentinel as fs
from tests.test_freshness_sentinel import (
    CN_PATH,
    NOW,
    _cn_board,
    _fresh_results,
)

UTC = timezone.utc


def _surface() -> dict:
    return next(s for s in fs.SURFACES if s["id"] == "cn_board_live")


def test_surface_id_is_cn_board_live_not_a_prophet_live_substring() -> None:
    s = _surface()
    assert s["id"] == "cn_board_live"
    assert "prophet_live" not in s["id"]
    assert s["path"] == CN_PATH
    assert s["kind"] == "live_file"
    assert s["absent_ok"] is True
    assert s["calendar"] == "cn"
    assert s["asof_field"] == "session"
    assert s["sla"]["by_cst"] == "15:20"
    assert s["sla"]["sessions_required"] == 3
    assert "client_path" not in s["sla"]


def test_absent_cn_board_is_a_normal_state_not_blindness() -> None:
    results = _fresh_results()
    results["cn_board_live"] = fs.FetchResult(
        error="served read failed: FileNotFoundError: [Errno 2] …"
    )
    report = fs.evaluate(results, NOW)
    c = report["surfaces"]["cn_board_live"]
    assert c["status"] == "indeterminate"
    assert c["absent"] is True
    assert "cn_board_live" not in report["stale_surfaces"]
    alerts, state = fs.decide_alerts(report, {}, NOW)
    assert "cn_board_live" not in (state.get("blind_counts") or {})
    assert alerts == []


def test_cn_asof_uses_the_mainland_calendar_not_nyse() -> None:
    """Golden Week 2026: Oct 1–7 closed on the mainland, NYSE open Oct 1–2.

    An artifact still on 2026-09-30 is current on the mainland calendar and
    two NYSE sessions behind. The CN surface must stay ok — that is the
    reason calendar=cn exists.
    """
    golden = datetime(2026, 10, 5, 2, 0, tzinfo=UTC)
    results = _fresh_results()
    results["cn_board_live"] = _cn_board("2026-09-30")
    c = fs.evaluate(results, golden)["surfaces"]["cn_board_live"]
    assert c["status"] == "ok"
    assert c["asof"] == "2026-09-30"
    assert c["asof_sessions_behind"] == 0
    # Positive control: the same stamp against NYSE would be 2 behind.
    assert fs.sessions_behind("2026-09-30", golden) == 2
    assert fs.sessions_behind("2026-09-30", golden, calendar="cn") == 0


def test_two_missed_mainland_sessions_breach() -> None:
    results = _fresh_results()
    results["cn_board_live"] = _cn_board("2026-08-05")  # Wed; NOW is Sat → Thu+Fri
    c = fs.evaluate(results, NOW)["surfaces"]["cn_board_live"]
    assert c["status"] == "stale"
    assert c["asof_sessions_behind"] == 2
    assert "mainland session" in c["detail"]


def test_intraday_tick_does_not_stamp_the_close_board_sla() -> None:
    rec = fs.record_first_fresh({}, fs.evaluate(_fresh_results(), NOW), NOW)
    sessions = rec.get("sessions") or {}
    for per in sessions.values():
        assert "cn_board_live" not in per


def test_close_board_by_1520_cst_is_met() -> None:
    # 07:10Z = 15:10 CST on the session day.
    results = _fresh_results()
    results["cn_board_live"] = _cn_board(
        "2026-08-07", first_close_board_at="2026-08-07T07:10:00Z",
    )
    report = fs.evaluate(results, NOW)
    rec = fs.record_first_fresh({}, report, NOW)
    entry = rec["sessions"]["2026-08-07"]["cn_board_live"]
    assert entry["met"] is True
    assert entry["by_cst"] == "15:20"
    assert entry["first_fresh_cst"] == "15:10"
    assert "by_et" not in entry


def test_close_board_after_1520_cst_is_missed() -> None:
    results = _fresh_results()
    results["cn_board_live"] = _cn_board(
        "2026-08-07", first_close_board_at="2026-08-07T07:25:00Z",
    )
    rec = fs.record_first_fresh({}, fs.evaluate(results, NOW), NOW)
    assert rec["sessions"]["2026-08-07"]["cn_board_live"]["met"] is False
    assert rec["sessions"]["2026-08-07"]["cn_board_live"]["first_fresh_cst"] == "15:25"


def test_sla_summary_exposes_by_cst_and_walks_the_cn_calendar() -> None:
    block = fs.sla_summary({}, NOW)["cn_board_live"]
    assert block["by_cst"] == "15:20"
    assert block["sessions_required"] == 3
    assert "by_et" not in block
    # NOW is Saturday 2026-08-08 → last completed mainland session is Friday.
    assert block["recent"][0]["session"] == "2026-08-07"
    assert block["consecutive_met"] == 0


def test_cn_session_n_back_walks_weekends_and_golden_week() -> None:
    fri = date(2026, 8, 7)
    assert cn_calendar.session_n_back(fri, 0) == fri
    assert cn_calendar.session_n_back(fri, 1) == date(2026, 8, 6)
    assert cn_calendar.session_n_back(date(2026, 10, 8), 1) == date(2026, 9, 30)
    assert cn_calendar.session_n_back(date(2026, 8, 8), 0) is None  # Saturday
    try:
        cn_calendar.session_n_back(fri, -1)
    except ValueError:
        pass
    else:
        raise AssertionError("negative n must raise")


# --------------------------------------------------------------------------- #
# Rescue classifier
# --------------------------------------------------------------------------- #
def test_rescue_is_classify_only() -> None:
    assert rescue.classify({})["alert_only"] is True
    assert rescue.classify({})["schema"] == "cn_live_rescue.classify/v1"


def test_rescue_pack_missing() -> None:
    v = rescue.classify({"pack": {"present": False}})
    assert v["stage"] == "pack_missing"
    assert "build_cn_live_pack" in v["lever"]


def test_rescue_evaluator_dead_is_quiet_on_lunch_and_holiday() -> None:
    missing = {"artifact": {"present": False}}
    assert rescue.classify({**missing, "market_phase": "morning"})["stage"] == "evaluator_dead"
    assert rescue.classify({**missing, "market_phase": "session_break"})["stage"] == "ok"
    assert rescue.classify({**missing, "market_phase": "holiday"})["stage"] == "ok"
    stale_tick = {
        "market_phase": "afternoon",
        "artifact": {"present": True, "tick_age_sec": 21 * 60},
    }
    assert rescue.classify(stale_tick)["stage"] == "evaluator_dead"
    stale_tick["market_phase"] = "session_break"
    assert rescue.classify(stale_tick)["stage"] == "ok"


def test_rescue_quotes_stale() -> None:
    v = rescue.classify({
        "market_phase": "afternoon",
        "artifact": {"present": True, "tick_age_sec": 60, "quote_age_sec_p50": 40 * 60},
    })
    assert v["stage"] == "quotes_stale"


def test_rescue_publish_failed() -> None:
    v = rescue.classify({
        "artifact": {"present": True, "tick_age_sec": 60},
        "r2_states": {"present": True, "built_at": "A"},
        "served": {"present": True, "built_at": "B"},
    })
    assert v["stage"] == "publish_failed"


def test_rescue_route_broken() -> None:
    v = rescue.classify({
        "artifact": {"present": True, "tick_age_sec": 60},
        "route": {"status": 401},
    })
    assert v["stage"] == "route_broken"


def test_rescue_client_stale() -> None:
    v = rescue.classify({
        "artifact": {"present": True, "tick_age_sec": 60, "session": "2026-08-18"},
        "client": {"page_session": "2026-08-17"},
    })
    assert v["stage"] == "client_stale"


def test_rescue_settlement_late_only_after_noon_utc() -> None:
    obs = {
        "artifact": {"present": True, "tick_age_sec": 60},
        "asia_close": {"success": False},
    }
    morning = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
    noon = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    assert rescue.classify(obs, now=morning)["stage"] == "ok"
    assert rescue.classify(obs, now=noon)["stage"] == "settlement_late"


def test_rescue_cli_classify_round_trips(tmp_path) -> None:
    bag = tmp_path / "obs.json"
    bag.write_text('{"pack": {"present": false}}', encoding="utf-8")
    assert rescue.main(["--classify", "--input", str(bag)]) == 0
    with pytest.raises(SystemExit) as exc:
        rescue.main([])
    assert exc.value.code == 2
