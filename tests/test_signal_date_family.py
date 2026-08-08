"""The §7 signal-date family: `date` / `signal_date` / `confirmed_date` / `recorded_at`.

A marker has THREE dates and a provenance stamp, and before 2026-08-08 only one of them
had a name. `date` is the 3D bucket's OPEN label (R-SQ2); the bucket's own close lands up
to two sessions later; the buy-filter LABEL is not knowable for ~8 daily sessions. Three
surfaces each read a different one as "the signal date" — the chart marker, the Golden
Oracle panel, and the early-dot lane — with no field saying which was which. Measured on
the committed 2026-08-07 NVDA file: `date` 2026-08-05, bucket close 2026-08-07, buy-filter
label still pending.

THE FENCE these tests exist for (the outage class). `daily.yml` was dead 2026-08-03..08-06
and artifacts published days after the sessions they describe. A signal evaluated N days
late must still be dated by its OWN bucket close — never by the run that happened to
evaluate it. That is the per-date-ledger-can-still-be-run-date-stamped defect, and
`test_signal_date_is_the_bucket_close_never_the_run_date` /
`test_a_late_run_moves_only_recorded_at` are written to go RED if the run date ever leaks
into a signal anchor.

Network-free: real NYSE sessions (the era `sq-abs-session-2026-08-06` grid is cut on the
absolute session calendar, so a `pd.bdate_range` fixture would not reproduce production's
bucket composition — see tests/test_signal_quality_no_leak.py).
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from engine import marker_integrity as mi
from engine import signal_quality as sq
from lib import nyse_calendar
from scripts import validate_signals as vs

_SESSIONS = pd.DatetimeIndex(pd.to_datetime(
    nyse_calendar.sessions_between(date(2024, 1, 1), date(2027, 12, 31))))

_NEW_FIELDS = {"signal_date", "confirmed_date", "recorded_at"}
_LEGACY_BUY_KEYS = {"date", "type", "quality", "reason", "reasons"}


def _tape(n: int = 800) -> pd.Series:
    """A deterministic sine tape on real NYSE sessions — the no-leak fixture's shape."""
    t = np.arange(n)
    idx = _SESSIONS[:n]
    return pd.Series(100 + 10 * np.sin(t / 25) + 0.10 * t + 3 * np.sin(t / 6), index=idx)


def _analyzed(close: pd.Series | None = None) -> dict:
    close = _tape() if close is None else close
    res = sq.analyze("TESTUS", close)
    assert res, "fixture tape must produce a payload"
    assert res["markers"], "fixture tape must produce markers"
    return res


def _plus_days(stamp: str, days: int) -> str:
    return (date.fromisoformat(stamp) + timedelta(days=days)).isoformat()


def _legacy(markers: list[dict]) -> list[dict]:
    """The same markers as they were PUBLISHED before the date family existed."""
    return [{k: v for k, v in m.items() if k not in _NEW_FIELDS} for m in markers]


# --------------------------------------------------------------------------- #
# the fence: a late run may never re-date a signal
# --------------------------------------------------------------------------- #
def test_signal_date_is_the_bucket_close_never_the_run_date():
    """The outage shape: evaluation runs days after the bucket closed.

    `signal_date` must be the bucket's own last session. If it is ever stamped with the
    run date — or silently left as the bucket's OPEN label — this goes red.
    """
    close = _tape()
    res = _analyzed(close)
    tape_last = str(close.index[-1].date())

    # The run happens FIVE DAYS after the last session on the tape (the 08-03..08-06
    # blackout, evaluated on 08-08).
    run_stamp = _plus_days(tape_last, 5)
    out = mi.merge_payload(None, res, run_stamp=run_stamp)

    for m in out["markers"]:
        assert m["signal_date"] is not None, f"{m['date']}: knowability date must be derivable"
        # the bucket close, resolved independently by the standalone resolver
        expected = sq.marker_last_session(close, m["date"])
        assert m["signal_date"] == str(expected.date())
        # ...which is NEVER the run date, and never after the tape it was drawn from
        assert m["signal_date"] != run_stamp, "run date leaked into the signal anchor"
        assert m["signal_date"] <= tape_last
        # the label is the bucket OPEN; the signal is its CLOSE; open never follows close
        assert m["date"] <= m["signal_date"]

    # Not vacuous: the two dates must actually DIFFER somewhere, or a revert to
    # `signal_date = date` would pass every assertion above.
    assert any(m["signal_date"] != m["date"] for m in out["markers"]), \
        "fixture must contain a bucket whose OPEN label and close differ"


def test_a_late_run_moves_only_recorded_at():
    """Same tape, two run dates: every signal anchor is byte-identical; only provenance moves."""
    close = _tape()
    tape_last = str(close.index[-1].date())

    on_time = mi.merge_payload(None, _analyzed(close), run_stamp=tape_last)
    five_days_late = mi.merge_payload(None, _analyzed(close), run_stamp=_plus_days(tape_last, 5))

    assert [_ for _ in _legacy(on_time["markers"])] == _legacy(five_days_late["markers"])
    assert ([m["signal_date"] for m in on_time["markers"]]
            == [m["signal_date"] for m in five_days_late["markers"]])
    assert ([m["confirmed_date"] for m in on_time["markers"] if m["type"] in ("buy", "rebuy")]
            == [m["confirmed_date"] for m in five_days_late["markers"]
                if m["type"] in ("buy", "rebuy")])
    # only the provenance stamp knows the run was late — which is what makes the lag
    # measurable after the fact
    assert {m["recorded_at"] for m in on_time["markers"]} == {tape_last}
    assert {m["recorded_at"] for m in five_days_late["markers"]} == {_plus_days(tape_last, 5)}


def test_recorded_at_is_sticky_so_publication_lag_stays_measurable():
    """A marker already rendered keeps its ORIGINAL stamp when a later run re-merges it."""
    close = _tape()
    tape_last = str(close.index[-1].date())
    first = mi.merge_payload(None, _analyzed(close), run_stamp=tape_last)

    later = mi.merge_payload(first, _analyzed(close), run_stamp=_plus_days(tape_last, 9))
    assert {m["recorded_at"] for m in later["markers"]} == {tape_last}, \
        "a re-merge back-stamped markers it did not first publish"


def test_markers_published_before_the_field_disclose_null_not_a_back_stamp():
    """The legacy corpus: every marker already on disk predates `recorded_at`.

    Back-stamping them with tonight's run would manufacture a publication lag of zero for
    the exact outage window this field exists to measure.
    """
    close = _tape()
    res = _analyzed(close)
    prev = {"asof": res["asof"], "anchor_era": res["anchor_era"],
            "markers": _legacy(res["markers"])}

    out = mi.merge_payload(prev, res, run_stamp=_plus_days(res["asof"], 3))
    assert {m["recorded_at"] for m in out["markers"]} == {None}
    # the derived dates, by contrast, ARE backfilled — they are functions of `date`
    assert all(m["signal_date"] is not None for m in out["markers"])
    assert out["pit"]["last_night"]["date_backfilled"] > 0


# --------------------------------------------------------------------------- #
# the emitted fields ARE the documented resolvers
# --------------------------------------------------------------------------- #
def test_emitted_dates_match_the_standalone_resolvers():
    """`analyze` derives both dates in-loop; the resolvers re-derive them from scratch.

    They read the same `_bucket_last_session` grid, so any drift between them is a bug in
    one of the two — and consumers use both (boards call the resolvers, the chart file
    carries the fields).
    """
    close = _tape()
    res = _analyzed(close)
    for m in res["markers"]:
        expected = sq.marker_last_session(close, m["date"])
        assert m["signal_date"] == str(expected.date())
        if m["type"] in ("buy", "rebuy"):
            got = sq.confirmation_date(close, m["date"])
            assert m["confirmed_date"] == (str(got.date()) if got is not None else None)


def test_confirmed_date_is_null_while_the_window_is_open_then_fills_in():
    """A marker inside its own confirmation window publishes a null, and later names the date.

    This is the NVDA 2026-08-05 shape: `quality` already reads 'block', `reasons` carries
    'pending confirmation', and the confirmation close has not printed. The null must fill
    in on a later night WITHOUT the marker's own dates ever moving.
    """
    full = _tape()
    # Cut the tape at a marker's OWN bucket close: that bucket is then the last one on the
    # frame, so bar i+CONFIRM_BARS does not exist and the window is open by construction —
    # no searching, no skip. (Re-cutting is safe: under the absolute session anchor the
    # grid is a function of (calendar, date) alone, so the marker keeps its label.)
    pending_marker = cut_at = None
    for m in reversed([m for m in _analyzed(full)["markers"] if m["type"] in ("buy", "rebuy")]):
        pos = int(full.index.get_indexer([pd.Timestamp(m["signal_date"])])[0])
        if pos >= 400 and pos <= len(full) - 30 and m["confirmed_date"] is not None:
            pending_marker, cut_at = m, pos + 1
            break
    assert pending_marker is not None, "fixture tape must carry a confirmable mid-tape buy"

    early = mi.merge_payload(None, _analyzed(full.iloc[:cut_at]), run_stamp="2026-08-03")
    row = [m for m in early["markers"] if m["date"] == pending_marker["date"]][0]
    assert row["confirmed_date"] is None, "an open window must publish a disclosed null"

    # the confirmation window prints; the SAME marker is re-merged from the fuller tape
    later = mi.merge_payload(early, _analyzed(full), run_stamp="2026-08-08")
    grown = [m for m in later["markers"] if m["date"] == pending_marker["date"]][0]
    assert grown["date"] == row["date"]                    # never re-dated
    assert grown["signal_date"] == row["signal_date"]      # never re-dated
    assert grown["recorded_at"] == "2026-08-03"            # first publication, not tonight
    assert grown["confirmed_date"] == pending_marker["confirmed_date"], \
        "the null must fill in with the date the full tape confirms"
    assert grown["confirmed_date"] > grown["signal_date"], \
        "confirmation cannot precede the bucket close it confirms"
    assert later["pit"]["last_night"]["date_backfilled"] >= 1


def test_a_published_date_is_never_re_dated_by_a_recompute():
    """Backfill fills HOLES only — a non-null published date is frozen (the RC-R2 law)."""
    prev = {"asof": "2026-07-10", "anchor_era": "e1",
            "markers": [{"date": "2026-07-01", "type": "buy", "quality": "take",
                         "signal_date": "2026-07-03", "confirmed_date": "2026-07-09",
                         "recorded_at": "2026-07-09"}]}
    new = {"asof": "2026-07-14", "anchor_era": "e1",
           "markers": [{"date": "2026-07-01", "type": "buy", "quality": "take",
                        "signal_date": "2026-07-06", "confirmed_date": "2026-07-13"}]}
    out = mi.merge_payload(prev, new, run_stamp="2026-07-14")
    got = out["markers"][0]
    assert got["signal_date"] == "2026-07-03"
    assert got["confirmed_date"] == "2026-07-09"
    assert got["recorded_at"] == "2026-07-09"
    assert out["pit"]["last_night"]["date_backfilled"] == 0


# --------------------------------------------------------------------------- #
# additive-only
# --------------------------------------------------------------------------- #
def test_the_change_is_additive_only_against_the_published_shape():
    """Merging a LEGACY payload adds keys and alters NOTHING the site already rendered."""
    close = _tape()
    res = _analyzed(close)
    legacy_markers = _legacy(res["markers"])
    prev = {"asof": res["asof"], "anchor_era": res["anchor_era"], "markers": legacy_markers}

    out = mi.merge_payload(prev, res, run_stamp="2026-08-08")
    assert len(out["markers"]) == len(legacy_markers)
    for before, after in zip(legacy_markers, out["markers"]):
        # every previously published key survives with its exact value
        for k, v in before.items():
            assert after[k] == v, f"legacy field {k} mutated on {before['date']}"
        # and the ONLY additions are the date family
        assert set(after) - set(before) <= _NEW_FIELDS


def test_marker_key_sets_are_exactly_the_documented_contract():
    res = _analyzed()
    for m in res["markers"]:
        if m["type"] in ("buy", "rebuy"):
            assert set(m) - _NEW_FIELDS <= _LEGACY_BUY_KEYS
            assert "signal_date" in m and "confirmed_date" in m
        else:
            # sell/cut run no buy filter, so they carry no confirmation to date
            assert set(m) == {"date", "type", "signal_date"}


def test_payload_with_the_new_fields_validates_against_the_published_schema():
    """SCHEMA.json is `additionalProperties: false` — the contract of record must know them."""
    out = mi.merge_payload(None, _analyzed(), run_stamp="2026-08-08")
    out = dict(out, ticker="TESTUS")
    validator = vs._validator_for(vs.load_schema(), "perTicker")
    assert vs._schema_errors(validator, out, "fixture") == []
    assert vs.check_markers(out["markers"], "fixture") == []


def test_validator_rejects_a_confirmation_date_on_a_sell():
    """`confirmed_date` is a buy-filter verdict field — sell/cut may not carry one."""
    bad = [{"date": "2026-07-01", "type": "sell", "confirmed_date": "2026-07-09"}]
    errs = vs.check_markers(bad, "fixture")
    assert any("confirmed_date" in e for e in errs)
    validator = vs._validator_for(vs.load_schema(), "marker")
    assert vs._schema_errors(validator, bad[0], "fixture") != []
