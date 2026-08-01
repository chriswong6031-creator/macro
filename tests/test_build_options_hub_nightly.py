"""tests/test_build_options_hub_nightly.py — scripts/build_options_hub_nightly.py.

OEU bug-wave finding: the published options_hub/gex/{ROOT}.json carries a
headline `asof` and a self-consistent `coverage` block (both computed live from
the greeks/OI read for that session), but its `history` tail comes from a
SEPARATELY-CADENCED store (data/polygon_gex/summary_{ROOT}.parquet) that can lag
behind by one or more sessions with nothing in the payload disclosing the gap —
a reader sees one "asof" and a stale history tail contradicting it.

_attach_gex_history is the one place `history` is joined onto the live gex
payload (scripts/build_options_hub_nightly.build_root, CONTRACT v2). This
suite pins:
  - history is still OMITTED (not set to null) when the store is absent —
    CONTRACT v2's own frontend-checks-key-presence rule, unchanged.
  - when history IS attached, coverage now carries `history_asof` — the tail's
    own last date — so asof vs coverage.asof vs coverage.history_asof can be
    reconciled by a reader instead of silently disagreeing.
"""
from __future__ import annotations

from scripts.build_options_hub_nightly import _attach_gex_history


def test_history_omitted_key_stays_omitted_when_store_absent():
    """CONTRACT v2: absent polygon_gex parquet -> 'history' key ABSENT, never
    null — the frontend checks key presence. Must not regress."""
    payload = {"schema": "options_hub.gex/v1", "asof": "2026-07-23",
               "coverage": {"asof": "2026-07-23", "n_contracts": 100}}
    out = _attach_gex_history(payload, None)
    assert "history" not in out
    assert "history_asof" not in out["coverage"]
    assert out == payload


def test_history_attached_discloses_its_own_last_date():
    payload = {"schema": "options_hub.gex/v1", "asof": "2026-07-23",
               "coverage": {"asof": "2026-07-23", "oi_date": "t-1", "n_contracts": 9959}}
    hist = [{"date": "2026-07-18"}, {"date": "2026-07-19"}, {"date": "2026-07-20"}]
    out = _attach_gex_history(payload, hist)
    assert out["history"] == hist
    assert out["coverage"]["history_asof"] == "2026-07-20"
    # The live-computed fields must be untouched — this only ADDS a fact.
    assert out["coverage"]["asof"] == "2026-07-23"
    assert out["asof"] == "2026-07-23"


def test_history_asof_reveals_the_lag_against_the_live_asof():
    """The exact defect: asof=2026-07-23 while history[-1].date=2026-07-20 —
    three real sessions absent from the series the headline claims to
    summarise.  Reconciling that gap now only needs coverage.history_asof."""
    payload = {"schema": "options_hub.gex/v1", "asof": "2026-07-23",
               "coverage": {"asof": "2026-07-23", "since": "2026-07-23"}}
    hist = [{"date": "2026-07-18"}, {"date": "2026-07-19"}, {"date": "2026-07-20"}]
    out = _attach_gex_history(payload, hist)
    assert out["asof"] != out["coverage"]["history_asof"]
    assert out["coverage"]["history_asof"] == "2026-07-20"


def test_empty_history_list_discloses_a_null_history_asof():
    """hist == [] (not None) — the store IS reachable but empty.  history_asof
    must be null, not crash on an index into an empty list."""
    payload = {"coverage": {"asof": "2026-07-23"}}
    out = _attach_gex_history(payload, [])
    assert out["history"] == []
    assert out["coverage"]["history_asof"] is None


def test_original_payload_dict_is_not_mutated():
    """build_root's own callers may hold a reference to the pre-attach payload
    (the fail-soft path re-uses it on exception) — _attach_gex_history must
    return a NEW dict, never mutate the caller's in place."""
    payload = {"coverage": {"asof": "2026-07-23"}}
    out = _attach_gex_history(payload, [{"date": "2026-07-20"}])
    assert "history" not in payload
    assert "history_asof" not in payload["coverage"]
    assert out is not payload


# ── WP-GEX-DATES (Options Superintelligence R0.10) ───────────────────────────
# The dated gex_history snapshots gained a sessions index (dates.json) + a
# bounded self-heal. These pin the pure pieces: the index shape law (newest
# first, latest == dates[0], junk dropped), the validator (reject, never
# coerce), the calendar-driven miss computation (weekends are NOT holes — the
# long-lived "2026-07-18 hole" note was a Saturday; the real hole is 07-20),
# and the point-in-time trim on healed payloads (a late-published snapshot
# must not carry history rows after the date it claims to describe).

from scripts.build_options_hub_nightly import (  # noqa: E402
    build_gex_dates_index,
    is_gex_dates,
    gex_history_missed_sessions,
    _trim_history_to,
)


def test_gex_dates_index_sorts_newest_first_and_drops_junk():
    idx = build_gex_dates_index(
        ["2026-07-17", "2026-07-21", "2026-07-21", "not-a-date", None, ""],
        root="SPY", asof="2026-07-31T02:00:00+00:00",
    )
    assert idx["schema"] == "options_hub.gex_dates/v1"
    assert idx["dates"] == ["2026-07-21", "2026-07-17"]
    assert idx["latest"] == "2026-07-21"
    assert idx["count"] == 2
    assert idx["root"] == "SPY"
    assert is_gex_dates(idx)


def test_gex_dates_index_empty_is_valid_with_null_latest():
    idx = build_gex_dates_index([], root="NOPE", asof="")
    assert idx["dates"] == []
    assert idx["latest"] is None
    assert idx["count"] == 0
    assert is_gex_dates(idx)


def test_is_gex_dates_rejects_rather_than_coerces():
    good = {"root": "SPY", "dates": ["2026-07-21", "2026-07-17"], "latest": "2026-07-21"}
    assert is_gex_dates(good)
    assert not is_gex_dates({**good, "dates": ["2026-07-17", "2026-07-21"]})  # wrong order
    assert not is_gex_dates({**good, "latest": "2026-07-17"})                  # latest != dates[0]
    assert not is_gex_dates({**good, "dates": ["2026-07-21", "junk"]})         # non-date entry
    assert not is_gex_dates({"dates": ["2026-07-21"], "latest": "2026-07-21"})  # no root
    assert not is_gex_dates({"root": "SPY", "dates": [], "latest": "2026-07-21"})
    assert not is_gex_dates(None)


def test_missed_sessions_finds_the_real_hole_and_ignores_weekends():
    # Live plane as verified 2026-07-31: snapshots exist for every session in
    # the epoch→asof window EXCEPT Monday 2026-07-20. 07-18/19 and 07-25/26 are
    # weekends — the calendar must not report them as holes.
    existing = ["2026-07-30", "2026-07-29", "2026-07-28", "2026-07-27",
                "2026-07-24", "2026-07-23", "2026-07-22", "2026-07-21",
                "2026-07-17"]
    missed = gex_history_missed_sessions(existing, "2026-07-30")
    assert missed == ["2026-07-20"]


def test_missed_sessions_includes_a_suppressed_tonight_and_orders_newest_first():
    missed = gex_history_missed_sessions(["2026-07-17"], "2026-07-21")
    assert missed == ["2026-07-21", "2026-07-20"]


def test_missed_sessions_empty_plane_expects_every_session_since_epoch():
    missed = gex_history_missed_sessions([], "2026-07-20")
    assert missed == ["2026-07-20", "2026-07-17"]


def test_trim_history_cuts_future_rows_and_restates_history_asof():
    payload = {
        "asof": "2026-07-20",
        "coverage": {"asof": "2026-07-20", "history_asof": "2026-07-30"},
        "history": [{"date": "2026-07-17"}, {"date": "2026-07-20"},
                    {"date": "2026-07-21"}, {"date": "2026-07-30"}],
    }
    out = _trim_history_to(payload, "2026-07-20")
    assert [h["date"] for h in out["history"]] == ["2026-07-17", "2026-07-20"]
    assert out["coverage"]["history_asof"] == "2026-07-20"
    # PIT law: the original dict is not mutated (fail-soft callers may reuse it).
    assert [h["date"] for h in payload["history"]][-1] == "2026-07-30"
    assert payload["coverage"]["history_asof"] == "2026-07-30"


def test_trim_history_all_future_leaves_empty_history_and_null_asof():
    payload = {"history": [{"date": "2026-07-21"}], "coverage": {}}
    out = _trim_history_to(payload, "2026-07-20")
    assert out["history"] == []
    assert out["coverage"]["history_asof"] is None


def test_trim_history_without_history_key_is_a_no_op():
    payload = {"asof": "2026-07-20", "coverage": {"asof": "2026-07-20"}}
    out = _trim_history_to(payload, "2026-07-20")
    assert "history" not in out
    assert out == payload
