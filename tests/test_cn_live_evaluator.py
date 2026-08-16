"""CN-PR-1 replay battery — honesty cases the architecture names in §9."""
from __future__ import annotations

from datetime import datetime, timezone

from engine.prophet_live import cn_clock
from engine.prophet_live import cn_states as CS
from engine.prophet_live import live_states as LS

UTC = timezone.utc

# 2026-08-18 is a Tuesday session. Pack as_of must be last COMPLETED session
# (17:00 CST settle buffer → still yesterday through the live window).
MORNING = datetime(2026, 8, 18, 1, 45, tzinfo=UTC)       # 09:45 CST
LUNCH = datetime(2026, 8, 18, 4, 0, tzinfo=UTC)          # 12:00 CST
AFTERNOON = datetime(2026, 8, 18, 5, 30, tzinfo=UTC)     # 13:30 CST
POST = datetime(2026, 8, 18, 7, 5, tzinfo=UTC)           # 15:05 CST
DEADLINE = datetime(2026, 8, 18, 7, 14, tzinfo=UTC)      # 15:14 CST — still post_close
HOLIDAY = datetime(2026, 10, 1, 2, 0, tzinfo=UTC)
WEEKEND = datetime(2026, 8, 15, 2, 0, tzinfo=UTC)

CFG = LS.live_cfg({"live": {"delayed_min": 15}, "prophet_live": {"quote_slack_min": 10}})


def _asof(now: datetime) -> str:
    return cn_clock.last_completed_session(now)


def _entry(*, close: float = 10.0, trigger: float | None = 10.5,
           fade: float | None = None, probed: bool = True,
           buyable: bool = False, frozen: dict | None = None) -> dict:
    e = {
        "state": "buyable" if buyable else "dormant",
        "center_buyable": buyable,
        "as_of_close": close,
        "probed": probed,
        "buyable_in_band": True if (trigger or fade) else False,
        "trigger_px": trigger,
        "fade_px": fade,
        "fade_hi_px": close * 1.1,
        "band_lo_px": 0.0 if not buyable else close * 0.9,
        "band_hi_px": close * 1.1,
        "price_adjustment": "split_and_dividend_adjusted",
    }
    if frozen:
        e["frozen"] = frozen
    if not probed:
        e["skip"] = "probe_cap"
    return e


def _pack(names: dict, now: datetime) -> dict:
    return {"schema": CS.SCHEMA.replace("states", "armed"), "as_of": _asof(now),
            "price_adjustment": "split_and_dividend_adjusted",
            "names": names, "meta": {"universe_n": len(names), "probed_n": len(names),
                                     "armed_n": len(names)}}


def _quote(px: float, *, prev: float | None = None, ts: datetime | None = None,
           basis: str = "regular", delay_ago_min: float = 16.0, now: datetime = MORNING,
           status: str | None = None) -> dict:
    stamp = ts or (now.replace(tzinfo=UTC) if now.tzinfo else now)
    # A print `delay_ago_min` before `now`.
    from datetime import timedelta
    qts = stamp - timedelta(minutes=delay_ago_min)
    q = {"price": px, "prev_close": prev if prev is not None else 10.0,
         "price_basis": basis, "ts_ms": qts.timestamp() * 1000.0,
         "quote_ts": qts.isoformat().replace("+00:00", "Z")}
    if status:
        q["market_status"] = status
    return q


def _run(pack, quotes, prev=None, *, now=MORNING, delay=15.0):
    return CS.evaluate(pack, quotes, prev, now=now, cfg=CFG,
                       quote_asof="2026-08-18T01:40:00Z", delay_min=delay,
                       quote_age_of=lambda q: cn_clock.quote_age_min(
                           CS._quote_ts(q), now, delay_floor_min=delay))


def test_ordinary_morning_pass_evaluates_and_debounces() -> None:
    p = _pack({"600000.SS": _entry()}, MORNING)
    q = {"600000.SS": _quote(10.6, now=MORNING)}
    first = _run(p, q, now=MORNING)
    assert first["status"] == "live"
    assert first["market_phase"] == "morning"
    assert first["names"]["600000.SS"]["state"] == "near"
    second = _run(p, q, first, now=MORNING)
    assert second["names"]["600000.SS"]["state"] == "forming"


def test_lunch_freezes_public_state_and_is_not_stale() -> None:
    p = _pack({"600000.SS": _entry()}, LUNCH)
    # 11:29 CST print at 12:00 CST — freshest lawful print, must not dark.
    qts = datetime(2026, 8, 18, 3, 29, tzinfo=UTC)
    q = {"600000.SS": _quote(10.6, ts=qts, delay_ago_min=0, now=LUNCH)}
    live = _run(p, {"600000.SS": _quote(10.6, now=MORNING)}, now=MORNING)
    live = _run(p, {"600000.SS": _quote(10.6, now=MORNING)}, live, now=MORNING)
    assert live["names"]["600000.SS"]["state"] == "forming"
    frozen = _run(p, q, live, now=LUNCH)
    assert frozen["market_phase"] == "session_break"
    assert frozen["names"]["600000.SS"]["state"] == "forming"
    assert frozen["names"]["600000.SS"]["market_status"] == "session_break"
    assert frozen["events"] == []


def test_holiday_and_weekend_are_not_evaluable() -> None:
    assert cn_clock.phase(HOLIDAY) == "holiday"
    assert cn_clock.phase(WEEKEND) == "weekend"
    assert not cn_clock.is_evaluable(HOLIDAY)
    assert not cn_clock.is_evaluable(WEEKEND)


def test_limit_up_locked_is_a_real_price_with_an_overlay() -> None:
    p = _pack({"600000.SS": _entry(close=10.0, trigger=10.2)}, MORNING)
    q = {"600000.SS": _quote(11.0, prev=10.0, now=MORNING)}  # +10%
    art = _run(p, q, now=MORNING)
    st = art["names"]["600000.SS"]
    assert st["market_status"] == "limit_up_locked"
    assert st["state"] != "unavailable"


def test_limit_down_locked_overlay() -> None:
    p = _pack({"600000.SS": _entry(close=10.0, fade=9.2, buyable=True)}, MORNING)
    q = {"600000.SS": _quote(9.0, prev=10.0, now=MORNING)}
    art = _run(p, q, now=MORNING)
    assert art["names"]["600000.SS"]["market_status"] == "limit_down_locked"


def test_suspended_is_distinct_from_unavailable() -> None:
    p = _pack({"600000.SS": _entry()}, MORNING)
    q = {"600000.SS": _quote(10.0, now=MORNING, status="suspended")}
    art = _run(p, q, now=MORNING)
    assert art["names"]["600000.SS"]["market_status"] == "suspended_suspected"


def test_missing_quote_is_unavailable_never_yesterdays_price() -> None:
    p = _pack({"600000.SS": _entry()}, MORNING)
    art = _run(p, {}, now=MORNING)
    st = art["names"]["600000.SS"]
    assert st["state"] == "dark"
    assert st["reason"] == "no_quote"
    assert st["market_status"] == "unavailable"
    assert "price" not in st or st.get("price") in (None, 0, 0.0)


def test_stale_pack_darks_the_artifact_and_carries_debounce() -> None:
    p = _pack({"600000.SS": _entry()}, MORNING)
    p["as_of"] = "2026-08-01"
    prev = _run(_pack({"600000.SS": _entry()}, MORNING),
                {"600000.SS": _quote(10.6, now=MORNING)}, now=MORNING)
    art = _run(p, {"600000.SS": _quote(10.6, now=MORNING)}, prev, now=MORNING)
    assert art["status"] == "dark"
    assert art["reason"] == "stale_pack"
    assert "600000.SS" in art["prev_states"]


def test_no_pack_is_dark() -> None:
    art = _run(None, {}, now=MORNING)
    assert art["status"] == "dark" and art["reason"] == "no_pack"


def test_basis_mismatch_darks_the_name_not_the_artifact() -> None:
    p = _pack({"600000.SS": _entry(close=10.0)}, MORNING)
    q = {"600000.SS": _quote(10.6, prev=8.0, now=MORNING)}  # 25% gap
    art = _run(p, q, now=MORNING)
    assert art["status"] == "live"
    assert art["names"]["600000.SS"]["state"] == "dark"
    assert art["names"]["600000.SS"]["reason"] == "basis_mismatch"


def test_delay_aware_lunch_print_is_fresh() -> None:
    # 11:29 CST print at 13:02 CST with 15-min floor → lunch anchor 11:30 → ~1 min.
    now = datetime(2026, 8, 18, 5, 2, tzinfo=UTC)
    qts = datetime(2026, 8, 18, 3, 29, tzinfo=UTC)
    age = cn_clock.quote_age_min(qts, now, delay_floor_min=15.0)
    assert age is not None and age < 5.0


def test_close_board_requires_coverage_floor() -> None:
    names = {f"60000{i}.SS": _entry() for i in range(5)}
    p = _pack(names, POST)
    quotes = {t: _quote(10.6, ts=POST, delay_ago_min=0, now=POST, basis="regular")
              for t in list(names)[:3]}  # 3/5 = 60% < 80%
    art = _run(p, quotes, now=POST)
    assert art["close_board"] is None
    assert art["close_pending"] is True
    assert art["revision"] == "intraday_provisional"


def test_close_board_publishes_when_floor_clears() -> None:
    names = {f"60000{i}.SS": _entry(frozen={"lane": "featured", "score": 70})
             for i in range(5)}
    p = _pack(names, POST)
    quotes = {t: _quote(10.6, ts=POST, delay_ago_min=0, now=POST, basis="regular")
              for t in names}
    art = _run(p, quotes, now=POST)
    assert art["close_board"] is not None
    assert art["close_pending"] is False
    assert art["revision"] == "close_provisional"
    assert art["liveness"]["first_close_board_at"]
    assert art["close_board"]["lanes"]["featured"]


def test_partial_close_at_deadline_does_not_manufacture_a_close() -> None:
    names = {f"60000{i}.SS": _entry() for i in range(5)}
    p = _pack(names, DEADLINE)
    quotes = {t: _quote(10.6, ts=POST, delay_ago_min=0, now=DEADLINE, basis="regular")
              for t in list(names)[:2]}
    art = _run(p, quotes, now=DEADLINE)
    assert art["close_pending"] is True
    assert art["close_board"]["close_pending"] is True
    assert art["revision"] == "intraday_provisional"


def test_kill_during_write_leaves_previous_copy(tmp_path) -> None:
    import json
    import scripts.cn_live_evaluator as E

    dest = tmp_path / "cn_prophet_live.json"
    dest.write_text(json.dumps({"schema": "old"}), encoding="utf-8")
    payload = {"schema": CS.SCHEMA, "names": {"X": {"state": "forming"}}}
    assert E.publish_served(dest, payload) is True
    assert json.loads(dest.read_text(encoding="utf-8"))["schema"] == CS.SCHEMA
    # Unencodable payload must not truncate the previous copy.
    bad = {"schema": CS.SCHEMA, "x": float("nan")}
    assert E.publish_served(dest, bad) is False
    assert json.loads(dest.read_text(encoding="utf-8"))["schema"] == CS.SCHEMA


def test_duplicate_pass_is_idempotent_on_public_state() -> None:
    p = _pack({"600000.SS": _entry()}, MORNING)
    q = {"600000.SS": _quote(10.6, now=MORNING)}
    a = _run(p, q, now=MORNING)
    a = _run(p, q, a, now=MORNING)
    b = _run(p, q, a, now=MORNING)
    assert b["names"]["600000.SS"]["state"] == a["names"]["600000.SS"]["state"] == "forming"
    assert b["names"]["600000.SS"]["since_ts"] == a["names"]["600000.SS"]["since_ts"]


def test_unprobed_names_are_not_in_states() -> None:
    p = _pack({"600000.SS": _entry(probed=False), "600001.SS": _entry()}, MORNING)
    art = _run(p, {"600001.SS": _quote(10.6, now=MORNING)}, now=MORNING)
    assert "600000.SS" not in art["names"]
    assert art["meta"]["unprobed_n"] == 1
