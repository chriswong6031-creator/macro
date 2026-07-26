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
