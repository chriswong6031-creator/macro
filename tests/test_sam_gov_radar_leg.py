"""Quota-aware SamGovAdapter (radar leg) — 2026-08-05 key integration.

Measured reality: a free personal SAM.gov key allows ~10 requests/DAY and the
key is shared with the 30-minute government-revenue-live lane. These tests pin
the four disciplines that make the radar leg live inside that budget:

  1. batch-first — one comma-joined ncode request covers every code; accepted
     only when returned rows span ≥2 distinct NAICS (list-handling proof);
  2. component rotation — codes sharing a basket travel together; the cursor
     resumes across nights under SAM_NIGHT_BUDGET;
  3. 429 = stop — the first quota rejection aborts the sweep (single attempt);
  4. merge — only fully-fetched baskets are recomputed; unrefreshed rows
     survive ≤ SAM_MERGE_KEEP_D days via the as_of sidecar.

All hermetic: fake key via env, _search monkeypatched, tmp_path root.
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest
import requests

from collectors import sam_gov as sg


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

MAP = {
    "111111": ["alpha"],                # component 1: alpha+beta welded by 222222
    "222222": ["alpha", "beta"],
    "333333": ["beta"],
    "444444": ["gamma"],                # component 2
    "555555": ["delta"],                # component 3
}


def _opp(naics: str, posted: str, typ: str = "Presolicitation") -> dict:
    return {"naicsCode": naics, "postedDate": posted, "type": typ, "title": "t"}


def _wire(tmp_path, monkeypatch, naics_map=None):
    """Point config at tmp_path, install the naics map + a fake key."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")
    d = tmp_path / "data" / "sam_gov"
    d.mkdir(parents=True, exist_ok=True)
    (d / "naics_themes.json").write_text(json.dumps({"naics": naics_map or MAP}))
    monkeypatch.setenv("SAM_API_KEY", "SAM-test-key")
    return d


def _http_429() -> requests.HTTPError:
    r = requests.Response()
    r.status_code = 429
    return requests.HTTPError("HTTP 429", response=r)


# ---------------------------------------------------------------------------
# coverage_groups
# ---------------------------------------------------------------------------

def test_coverage_groups_weld_codes_sharing_a_basket():
    groups = sg.coverage_groups(MAP)
    as_sets = [set(g) for g in groups]
    assert {"111111", "222222", "333333"} in as_sets, "alpha/beta codes must travel together"
    assert {"444444"} in as_sets
    assert {"555555"} in as_sets
    assert len(groups) == 3
    # deterministic across calls
    assert groups == sg.coverage_groups(MAP)


# ---------------------------------------------------------------------------
# batch path
# ---------------------------------------------------------------------------

def test_batch_accepted_single_request(tmp_path, monkeypatch):
    d = _wire(tmp_path, monkeypatch)
    calls: list[str] = []
    recent = (pd.Timestamp.utcnow().date() - pd.Timedelta(days=5)).isoformat()

    def fake_search(self, naics, pf, pt):
        calls.append(naics)
        # rows spanning ≥2 distinct codes = the API honoured the list
        return [_opp("111111", recent), _opp("444444", recent)]

    monkeypatch.setattr(sg.SamGovAdapter, "_search", fake_search)
    out = sg.SamGovAdapter().fetch()
    assert len(calls) == 1, "batch must spend exactly ONE request"
    assert "," in calls[0] and calls[0].count(",") == len(MAP) - 1
    ing = out["sam_gov__ingest"]
    assert int(ing["requests"].iloc[0]) == 1
    assert int(ing["quota_blocked"].iloc[0]) == 0
    cur = json.loads((d / "naics_cursor.json").read_text())
    assert cur["batch_ok"] is True
    # every basket was covered → parquet written with fresh as_of for the baskets
    # that actually had notices (beta/delta had zero → correctly no row, no stamp)
    meta = json.loads((d / "opp_velocity_meta.json").read_text())
    assert set(meta["as_of"]) == {"alpha", "gamma"}


def test_batch_rejected_single_code_falls_back_to_rotation(tmp_path, monkeypatch):
    d = _wire(tmp_path, monkeypatch)
    calls: list[str] = []
    recent = (pd.Timestamp.utcnow().date() - pd.Timedelta(days=5)).isoformat()

    def fake_search(self, naics, pf, pt):
        calls.append(naics)
        if "," in naics:
            # server treated the list as a literal → one distinct code only
            return [_opp("111111", recent)]
        return [_opp(naics, recent)]

    monkeypatch.setattr(sg.SamGovAdapter, "_search", fake_search)
    monkeypatch.setattr(sg.time, "sleep", lambda s: None)
    sg.SamGovAdapter().fetch()
    assert "," in calls[0], "first call is the batch probe"
    assert all("," not in c for c in calls[1:]), "fallback must be per-code"
    cur = json.loads((d / "naics_cursor.json").read_text())
    assert cur["batch_ok"] is False and cur["batch_checked"]


def test_failed_batch_not_retried_within_retest_window(tmp_path, monkeypatch):
    d = _wire(tmp_path, monkeypatch)
    (d / "naics_cursor.json").write_text(json.dumps(
        {"batch_ok": False, "batch_checked": date.today().isoformat(), "group_idx": 0}))
    calls: list[str] = []
    recent = (pd.Timestamp.utcnow().date() - pd.Timedelta(days=5)).isoformat()

    def fake_search(self, naics, pf, pt):
        calls.append(naics)
        return [_opp(naics, recent)]

    monkeypatch.setattr(sg.SamGovAdapter, "_search", fake_search)
    monkeypatch.setattr(sg.time, "sleep", lambda s: None)
    sg.SamGovAdapter().fetch()
    assert all("," not in c for c in calls), (
        "a batch probe that failed today must not re-spend a request tonight"
    )


# ---------------------------------------------------------------------------
# quota stop + rotation
# ---------------------------------------------------------------------------

def test_first_429_stops_the_sweep(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    calls: list[str] = []

    def fake_search(self, naics, pf, pt):
        calls.append(naics)
        raise _http_429()

    monkeypatch.setattr(sg.SamGovAdapter, "_search", fake_search)
    out = sg.SamGovAdapter().fetch()   # must NOT raise — quota night is a degrade
    assert len(calls) == 1, f"429 must stop spending immediately (made {len(calls)} calls)"
    ing = out["sam_gov__ingest"]
    assert int(ing["quota_blocked"].iloc[0]) == 1
    assert int(ing["opps"].iloc[0]) == 0


def test_rotation_cursor_covers_all_groups_across_nights(tmp_path, monkeypatch):
    d = _wire(tmp_path, monkeypatch)
    # force rotation path: batch known-failed, retest not due
    (d / "naics_cursor.json").write_text(json.dumps(
        {"batch_ok": False, "batch_checked": date.today().isoformat(), "group_idx": 0}))
    # shrink budget so one 3-code group fills night 1; groups 2+3 fill night 2
    monkeypatch.setattr(sg, "SAM_NIGHT_BUDGET", 3)
    monkeypatch.setattr(sg.time, "sleep", lambda s: None)
    recent = (pd.Timestamp.utcnow().date() - pd.Timedelta(days=5)).isoformat()
    nightly_calls: list[list[str]] = []

    def fake_search(self, naics, pf, pt):
        nightly_calls[-1].append(naics)
        return [_opp(naics, recent)]

    monkeypatch.setattr(sg.SamGovAdapter, "_search", fake_search)

    nightly_calls.append([])
    sg.SamGovAdapter().fetch()      # night 1
    # keep batch marked failed+fresh so night 2 also skips the probe
    cur = json.loads((d / "naics_cursor.json").read_text())
    cur.update({"batch_ok": False, "batch_checked": date.today().isoformat()})
    (d / "naics_cursor.json").write_text(json.dumps(cur))
    nightly_calls.append([])
    sg.SamGovAdapter().fetch()      # night 2

    n1, n2 = (set(c) for c in nightly_calls)
    assert n1 == {"111111", "222222", "333333"}, "night 1 = the welded 3-code component"
    assert n2 == {"444444", "555555"}, "night 2 resumes at the cursor"
    assert len(nightly_calls[0]) <= 3 and len(nightly_calls[1]) <= 3


def test_oversized_group_still_runs_alone(tmp_path, monkeypatch):
    """A component larger than the budget must still run (alone) — otherwise its
    baskets would never refresh."""
    d = _wire(tmp_path, monkeypatch)
    (d / "naics_cursor.json").write_text(json.dumps(
        {"batch_ok": False, "batch_checked": date.today().isoformat(), "group_idx": 0}))
    monkeypatch.setattr(sg, "SAM_NIGHT_BUDGET", 2)   # smaller than the 3-code component
    monkeypatch.setattr(sg.time, "sleep", lambda s: None)
    recent = (pd.Timestamp.utcnow().date() - pd.Timedelta(days=5)).isoformat()
    calls: list[str] = []

    def fake_search(self, naics, pf, pt):
        calls.append(naics)
        return [_opp(naics, recent)]

    monkeypatch.setattr(sg.SamGovAdapter, "_search", fake_search)
    sg.SamGovAdapter().fetch()
    assert set(calls) == {"111111", "222222", "333333"}, (
        "the oversized component must run whole, and nothing else that night"
    )


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

def _vel(rows: dict[str, tuple[int, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"basket_id": b, "recent_count": rc, "prior_count": pc, "n_members": 0, "covered": ""}
         for b, (rc, pc) in rows.items()]).set_index("basket_id")


def test_merge_upserts_covered_and_keeps_fresh_uncovered():
    today = date(2026, 8, 10)
    old = _vel({"alpha": (5, 3), "gamma": (2, 2)})
    meta = {"as_of": {"alpha": "2026-08-01", "gamma": "2026-08-08"}}
    new = _vel({"alpha": (9, 4)})
    merged, meta_out = sg.merge_velocity(new, {"alpha", "beta"}, old, meta, today)
    assert int(merged.loc["alpha", "recent_count"]) == 9, "covered basket takes tonight's row"
    assert "gamma" in merged.index, "2-day-old uncovered row survives (≤ keep window)"
    assert meta_out["as_of"]["alpha"] == "2026-08-10"
    assert meta_out["as_of"]["gamma"] == "2026-08-08"


def test_merge_ages_out_stale_uncovered_rows():
    today = date(2026, 8, 10)
    old = _vel({"gamma": (2, 2)})
    meta = {"as_of": {"gamma": "2026-08-01"}}   # 9 days > SAM_MERGE_KEEP_D
    merged, meta_out = sg.merge_velocity(pd.DataFrame(), set(), old, meta, today)
    assert merged.empty
    assert meta_out["as_of"] == {}


def test_merge_removes_covered_basket_with_zero_notices():
    """A covered basket that now has ZERO early notices was refreshed-to-empty —
    its old row must not linger."""
    today = date(2026, 8, 10)
    old = _vel({"alpha": (5, 3)})
    meta = {"as_of": {"alpha": "2026-08-09"}}
    merged, meta_out = sg.merge_velocity(pd.DataFrame(), {"alpha"}, old, meta, today)
    assert merged.empty
    assert "alpha" not in meta_out["as_of"]


def test_partial_component_never_updates_its_baskets(tmp_path, monkeypatch):
    """Quota dies mid-component → that component's baskets keep their previous
    row (a half-fetched basket velocity would understate both windows)."""
    d = _wire(tmp_path, monkeypatch)
    (d / "naics_cursor.json").write_text(json.dumps(
        {"batch_ok": False, "batch_checked": date.today().isoformat(), "group_idx": 0}))
    monkeypatch.setattr(sg.time, "sleep", lambda s: None)
    # seed an existing parquet + fresh meta for alpha/beta
    old = _vel({"alpha": (7, 7), "beta": (4, 4)})
    old.to_parquet(d / "opp_velocity.parquet")
    (d / "opp_velocity_meta.json").write_text(json.dumps(
        {"as_of": {"alpha": date.today().isoformat(), "beta": date.today().isoformat()}}))
    recent = (pd.Timestamp.utcnow().date() - pd.Timedelta(days=5)).isoformat()
    calls: list[str] = []

    def fake_search(self, naics, pf, pt):
        calls.append(naics)
        if len(calls) == 2:
            raise _http_429()         # quota dies on the component's 2nd code
        return [_opp(naics, recent), _opp(naics, recent), _opp(naics, recent)]

    monkeypatch.setattr(sg.SamGovAdapter, "_search", fake_search)
    sg.SamGovAdapter().fetch()
    kept = pd.read_parquet(d / "opp_velocity.parquet")
    if "basket_id" in kept.columns:
        kept = kept.set_index("basket_id")
    assert int(kept.loc["alpha", "recent_count"]) == 7, (
        "half-fetched component must NOT overwrite its baskets"
    )
    assert int(kept.loc["beta", "recent_count"]) == 4


# ---------------------------------------------------------------------------
# workflow gate (shape pin — the hour window is load-bearing quota policy)
# ---------------------------------------------------------------------------

def test_govrev_lane_carries_sam_quota_gate():
    from pathlib import Path
    wf = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "government-revenue-live.yml"
    text = wf.read_text()
    assert "SAM quota gate" in text, "the 30-min lane must carry the quota gate"
    assert 'case "$hh" in' in text and "00|01)" in text, (
        "scheduled SAM polls must be restricted to the 00-01 UTC window "
        "(radar-first allocation of the shared ~10/day key)"
    )
