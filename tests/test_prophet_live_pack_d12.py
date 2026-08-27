"""D12 regression: one impossible close-store tip must not stamp or contaminate the US pack."""
from __future__ import annotations

from datetime import datetime, timezone
import inspect

import pandas as pd

from engine.prophet_live import armed_pack as AP
import scripts.build_prophet_live_pack as B


def _series(last: str, *, n: int = 80) -> pd.Series:
    idx = pd.bdate_range(end=pd.Timestamp(last), periods=n)
    # Replace the final label so we can deliberately model a weekend/non-session row.
    idx = pd.DatetimeIndex([*idx[:-1], pd.Timestamp(last)])
    return pd.Series(range(100, 100 + n), index=idx, dtype="float64")


def _valid_tip(series: dict[str, pd.Series], completed_through: str) -> str | None:
    valid, _invalid = B._split_completed_series(
        series, completed_through=completed_through
    )
    return AP.as_of_date(valid.values())


def test_us_pack_ignores_one_non_session_tip_but_keeps_the_real_store_tip():
    got = _valid_tip(
        {"GOOD": _series("2026-08-07"), "SAT": _series("2026-08-08")},
        "2026-08-07",
    )
    assert got == "2026-08-07"


def test_us_pack_ignores_a_non_session_even_when_it_is_before_the_bound():
    got = _valid_tip(
        {"GOOD": _series("2026-07-31"), "SAT": _series("2026-08-01")},
        "2026-08-03",
    )
    assert got == "2026-07-31"


def test_us_pack_rejects_a_future_session_but_does_not_fake_freshness():
    got = _valid_tip(
        {"STALE": _series("2026-07-31"), "FUTURE": _series("2026-08-10")},
        "2026-08-07",
    )
    assert got == "2026-07-31", "a stale valid store must remain honestly stale"


def test_shared_as_of_date_remains_calendar_neutral_for_cn_and_other_callers():
    # CN and other shared callers do not pass the US completion bound. Their historical
    # behavior remains raw store-tip selection; D12 must not silently impose NYSE law.
    friday = _series("2026-08-07")
    saturday = _series("2026-08-08")
    assert AP.as_of_date([friday, saturday]) == "2026-08-08"


def test_split_completed_series_quarantines_non_session_and_not_yet_completed_names():
    series = {
        "GOOD": _series("2026-08-07"),
        "SAT": _series("2026-08-08"),
        "FUTURE": _series("2026-08-10"),
    }
    valid, invalid = B._split_completed_series(series, completed_through="2026-08-07")
    assert set(valid) == {"GOOD"}
    assert set(invalid) == {"SAT", "FUTURE"}


def test_split_completed_series_quarantines_nat_tip_without_crashing():
    malformed = pd.Series([101.0], index=pd.DatetimeIndex([pd.NaT]))
    valid, invalid = B._split_completed_series(
        {"GOOD": _series("2026-08-07"), "MALFORMED": malformed},
        completed_through="2026-08-07",
    )
    assert set(valid) == {"GOOD"}
    assert set(invalid) == {"MALFORMED"}


def test_invalid_tip_name_is_an_explicit_non_verdict_not_dormant():
    s = _series("2026-08-08")
    rec = AP.stale_record("BAD", s, 0)
    rec["skip"] = "invalid_series_tip"
    entry = B._name_entry(rec, None)
    assert entry["state"] == "stale"
    assert entry["skip"] == "invalid_series_tip"


def test_completion_clock_matches_the_incident_shape():
    # 08:00 ET Monday: Friday is the last completed session; Monday itself is not.
    from engine.prophet_live import live_states as LS

    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    assert LS.last_completed_session(now) == "2026-08-07"


def test_build_filters_invalid_series_before_selecting_tip_or_submitting_gate_work():
    source = inspect.getsource(B.build)
    completion = source.index("completed_through = LS.last_completed_session(now)")
    split = source.index("series, invalid_series = _split_completed_series")
    tip = source.index("tip = AP.as_of_date(series.values())")
    fresh_loop = source.index("for tkr, s in series.items():", tip)
    assert completion < split < tip < fresh_loop
    assert 'recs[tkr]["skip"] = "invalid_series_tip"' in source
