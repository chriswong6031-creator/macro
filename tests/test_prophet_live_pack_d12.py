"""D12 regression: one impossible close-store tip must not stamp or contaminate the US pack."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from engine.prophet_live import armed_pack as AP
import scripts.build_prophet_live_pack as B


def _series(last: str, *, n: int = 80) -> pd.Series:
    idx = pd.bdate_range(end=pd.Timestamp(last), periods=n)
    # Replace the final label so we can deliberately model a weekend/non-session row.
    idx = pd.DatetimeIndex([*idx[:-1], pd.Timestamp(last)])
    return pd.Series(range(100, 100 + n), index=idx, dtype="float64")


def test_as_of_date_ignores_one_non_session_tip_but_keeps_the_real_store_tip():
    good = _series("2026-08-07")
    saturday = _series("2026-08-08")
    got = AP.as_of_date([good, saturday], completed_through="2026-08-07")
    assert got == "2026-08-07"


def test_as_of_date_rejects_a_future_session_but_does_not_fake_freshness():
    stale_good = _series("2026-07-31")
    future_monday = _series("2026-08-10")
    got = AP.as_of_date([stale_good, future_monday], completed_through="2026-08-07")
    assert got == "2026-07-31", "a stale valid store must remain honestly stale"


def test_split_completed_series_quarantines_non_session_and_not_yet_completed_names():
    series = {
        "GOOD": _series("2026-08-07"),
        "SAT": _series("2026-08-08"),
        "FUTURE": _series("2026-08-10"),
    }
    valid, invalid = B._split_completed_series(series, completed_through="2026-08-07")
    assert set(valid) == {"GOOD"}
    assert set(invalid) == {"SAT", "FUTURE"}


def test_invalid_tip_name_is_an_explicit_non_verdict_not_dormant():
    s = _series("2026-08-08")
    rec = AP.stale_record("BAD", s, 0)
    rec["skip"] = "invalid_series_tip"
    entry = AP.name_entry(rec, None)
    assert entry["state"] == "stale"
    assert entry["skip"] == "invalid_series_tip"


def test_completion_clock_matches_the_incident_shape():
    # 08:00 ET Monday: Friday is the last completed session; Monday itself is not.
    from engine.prophet_live import live_states as LS

    now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    assert LS.last_completed_session(now) == "2026-08-07"
