"""Hermetic tests for engine/qledger.py — the Universal Scoreboard contract
(§2.2, D2/D3/D4/D10 of QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md).

All tests are self-contained: tmp_path store, synthetic prices monkeypatched
onto the shared parquet layer. No live data, no network, no side-effects on the
real data/qledger or site/qledger.

Assertions:
  * schema validation — scope types, directions, timestamp_quality, macro-D4.
  * registrar — idempotent, persists rejects for the dark-fraction audit.
  * embargo logic — the [P2] enum (CRAWL/PUBLISHER/DISCLOSURE/EVENT/SNAPSHOT).
  * multi-horizon grading — [5,21,63] capped by horizon_d; excess/control/hit.
  * Wilson CI lower bound.
  * state derivation UNGRADED/ACCRUING/GRADED on honest n_dates.
  * track-record aggregation — n_dates is DISTINCT dates (overlap illusion).
  * placebo slot excluded from headline stats.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from engine import qledger as q


# --------------------------------------------------------------------------- #
# synthetic price layer
# --------------------------------------------------------------------------- #
def _mk_series(start: str, days: int, start_px: float, drift: float) -> pd.Series:
    idx = pd.bdate_range(start=start, periods=days)
    vals = [start_px * (1.0 + drift) ** i for i in range(days)]
    return pd.Series(vals, index=idx)


@pytest.fixture
def prices(monkeypatch):
    """Install synthetic closes for a subject, its bench (SPY), and a control
    (XLI). Subject rises fastest → positive excess over both."""
    store = {
        "CARR": _mk_series("2026-01-01", 120, 100.0, 0.010),   # +1.0%/bd
        "SPY":  _mk_series("2026-01-01", 120, 400.0, 0.002),   # +0.2%/bd
        "XLI":  _mk_series("2026-01-01", 120, 100.0, 0.004),   # +0.4%/bd
        "LOSER": _mk_series("2026-01-01", 120, 50.0, -0.005),  # falls
    }

    def _series(ticker, root):
        return store.get(ticker)

    # Every price read in the suite funnels through engine.ai_desk._close_series:
    # ai_desk._level_asof calls it directly, and desk_scorer.close_at/covers (which
    # ai_desk_scorer re-exports) resolve it via `from engine import ai_desk as _desk`.
    # Patching the one canonical accessor covers all legs.
    monkeypatch.setattr("engine.ai_desk._close_series", _series)
    return store


# --------------------------------------------------------------------------- #
# schema validation
# --------------------------------------------------------------------------- #
def test_validate_good_entity_claim():
    c = q.make_claim(desk="altdata", asof="2026-06-19", scope_type="entity",
                     scope_key="CARR", direction=1, horizon_d=63,
                     timestamp_quality="DISCLOSURE_DATE", sector="Industrials")
    ok, reason = q._validate_claim(c)
    assert ok, reason
    assert c["control"] == "XLI"        # sector-matched control resolved
    assert c["bench"] == "SPY"


@pytest.mark.parametrize("mut, field", [
    ({"desk": ""}, "desk"),
    ({"scope": {"type": "planet", "key": "X"}}, "scope.type"),
    ({"direction": 2}, "direction"),
    ({"horizon_d": 0}, "horizon_d"),
    ({"timestamp_quality": "BOGUS"}, "timestamp_quality"),
    ({"timestamp_quality": "CORRUPTED"}, "CORRUPTED"),
])
def test_validate_rejects_bad_fields(mut, field):
    c = q.make_claim(desk="d", asof="2026-06-19", scope_type="entity",
                     scope_key="X", direction=1, horizon_d=21,
                     timestamp_quality="CRAWL_BOUNDED")
    c.update(mut)
    ok, reason = q._validate_claim(c)
    assert not ok


def test_macro_claim_requires_named_observable():
    # D4: macro claim with default SPY bench is rejected.
    bad = q.make_claim(desk="policy", asof="2026-06-18", scope_type="macro",
                       scope_key="rate-cut", direction=1, horizon_d=126,
                       timestamp_quality="DISCLOSURE_DATE")
    ok, reason = q._validate_claim(bad)
    assert not ok and "machine-checkable" in reason

    # naming an observable makes it valid.
    good = q.make_claim(desk="policy", asof="2026-06-18", scope_type="macro",
                        scope_key="2y-yield", direction=-1, horizon_d=126,
                        timestamp_quality="DISCLOSURE_DATE", bench="DGS2")
    ok, reason = q._validate_claim(good)
    assert ok, reason
    assert good["bench"] == "DGS2"


# --------------------------------------------------------------------------- #
# registrar
# --------------------------------------------------------------------------- #
def test_register_persists_and_is_idempotent(tmp_path):
    c = q.make_claim(desk="altdata", asof="2026-06-19", scope_type="entity",
                     scope_key="CARR", direction=1, horizon_d=63,
                     timestamp_quality="DISCLOSURE_DATE", sector="Industrials")
    r1 = q.register(c, root=tmp_path)
    r2 = q.register(c, root=tmp_path)     # same logical claim
    assert r1["claim_id"] == r2["claim_id"]
    claims = q.load_claims(tmp_path)
    assert len(claims) == 1               # deduped
    assert claims[0]["status"] == q.STATUS_OPEN


def test_register_persists_rejects_for_audit(tmp_path):
    bad = q.make_claim(desk="policy", asof="2026-06-18", scope_type="macro",
                       scope_key="vibes", direction=1, horizon_d=63,
                       timestamp_quality="DISCLOSURE_DATE")   # no observable
    stored = q.register(bad, root=tmp_path)
    assert stored["status"] == q.STATUS_REJECTED
    assert "reject_reason" in stored
    # rejects ARE persisted (D4 dark-fraction numerator)
    assert len(q.load_claims(tmp_path)) == 1


def test_placebo_slot_rides_through(tmp_path):
    c = q.make_claim(desk="altdata", asof="2026-06-19", scope_type="entity",
                     scope_key="CARR", direction=1, horizon_d=21,
                     timestamp_quality="CRAWL_BOUNDED", is_placebo=True)
    stored = q.register(c, root=tmp_path)
    assert stored["is_placebo"] is True


# --------------------------------------------------------------------------- #
# embargo
# --------------------------------------------------------------------------- #
def test_embargo_matrix():
    def q_of(tq):
        return q.make_claim(desk="d", asof="2026-06-19", scope_type="entity",
                            scope_key="CARR", direction=1, horizon_d=21,
                            timestamp_quality=tq)
    assert q._embargo_ok(q_of("CRAWL_BOUNDED")) == (True, False)
    assert q._embargo_ok(q_of("PUBLISHER_STATED")) == (True, True)
    assert q._embargo_ok(q_of("DISCLOSURE_DATE")) == (True, True)
    assert q._embargo_ok(q_of("EVENT_DATE")) == (False, False)   # never an anchor
    assert q._embargo_ok(q_of("SNAPSHOT_DATE")) == (False, False)  # display-only


def test_disclosure_entry_shifts_one_bd():
    c = q.make_claim(desk="d", asof="2026-06-19", scope_type="entity",
                     scope_key="CARR", direction=1, horizon_d=21,
                     timestamp_quality="DISCLOSURE_DATE")
    # 2026-06-19 is a Friday → +1bd == 2026-06-22 (Monday)
    assert q._entry_date(c) == "2026-06-22"
    # CRAWL_BOUNDED anchors at asof
    c2 = dict(c, timestamp_quality="CRAWL_BOUNDED")
    assert q._entry_date(c2) == "2026-06-19"


# --------------------------------------------------------------------------- #
# grading
# --------------------------------------------------------------------------- #
def test_grade_multi_horizon_capped_by_horizon_d(prices, tmp_path):
    c = q.make_claim(desk="altdata", asof="2026-02-02", scope_type="entity",
                     scope_key="CARR", direction=1, horizon_d=63,
                     timestamp_quality="CRAWL_BOUNDED", sector="Industrials")
    stored = q.register(c, root=tmp_path)
    rows = q.grade_claim(stored, root=tmp_path, today=date(2026, 6, 1))
    hs = sorted(r["horizon_d"] for r in rows)
    assert hs == [5, 21, 63]              # all three in-scope + matured
    for r in rows:
        assert r["excess"] > 0            # CARR beats SPY
        assert r["hit"] is True
        assert r["control_ret"] is not None
        assert r["embargo_applied"] is False


def test_grade_horizon_d_below_5_grades_at_own_clock(prices, tmp_path):
    c = q.make_claim(desk="d", asof="2026-02-02", scope_type="entity",
                     scope_key="CARR", direction=1, horizon_d=3,
                     timestamp_quality="CRAWL_BOUNDED")
    rows = q.grade_claim(q.register(c, root=tmp_path), root=tmp_path,
                         today=date(2026, 6, 1))
    assert sorted(r["horizon_d"] for r in rows) == [3]


def test_grade_short_horizon_only_5d(prices, tmp_path):
    c = q.make_claim(desk="d", asof="2026-02-02", scope_type="entity",
                     scope_key="CARR", direction=1, horizon_d=21,
                     timestamp_quality="CRAWL_BOUNDED")
    rows = q.grade_claim(q.register(c, root=tmp_path), root=tmp_path,
                         today=date(2026, 6, 1))
    assert sorted(r["horizon_d"] for r in rows) == [5, 21]


def test_grade_direction_short_hit(prices, tmp_path):
    c = q.make_claim(desk="d", asof="2026-02-02", scope_type="entity",
                     scope_key="LOSER", direction=-1, horizon_d=21,
                     timestamp_quality="CRAWL_BOUNDED")
    rows = q.grade_claim(q.register(c, root=tmp_path), root=tmp_path,
                         today=date(2026, 6, 1))
    assert rows and all(r["excess"] < 0 and r["hit"] is True for r in rows)


def test_grade_salience_only_has_null_hit(prices, tmp_path):
    c = q.make_claim(desk="china_intel", asof="2026-02-02", scope_type="entity",
                     scope_key="CARR", direction=0, horizon_d=21,
                     timestamp_quality="CRAWL_BOUNDED")
    rows = q.grade_claim(q.register(c, root=tmp_path), root=tmp_path,
                         today=date(2026, 6, 1))
    assert rows and all(r["hit"] is None for r in rows)


def test_grade_not_matured_returns_empty(prices, tmp_path):
    c = q.make_claim(desk="d", asof="2026-05-28", scope_type="entity",
                     scope_key="CARR", direction=1, horizon_d=63,
                     timestamp_quality="CRAWL_BOUNDED")
    # today only ~4 days later → nothing matured
    rows = q.grade_claim(q.register(c, root=tmp_path), root=tmp_path,
                         today=date(2026, 6, 1))
    assert rows == []


def test_event_date_not_gradeable(prices, tmp_path):
    c = q.make_claim(desk="d", asof="2026-02-02", scope_type="entity",
                     scope_key="CARR", direction=1, horizon_d=21,
                     timestamp_quality="EVENT_DATE")
    rows = q.grade_claim(q.register(c, root=tmp_path), root=tmp_path,
                         today=date(2026, 6, 1))
    assert rows == []


# --------------------------------------------------------------------------- #
# Wilson CI
# --------------------------------------------------------------------------- #
def test_wilson_ci_low():
    assert q.wilson_ci_low(0, 0) is None
    # all hits, small n → lower bound well below 1
    assert 0.0 < q.wilson_ci_low(5, 5) < 1.0
    # 50/50 large n → near 0.5 but below
    lo = q.wilson_ci_low(50, 100)
    assert 0.35 < lo < 0.5
    # zero hits → lower bound 0
    assert q.wilson_ci_low(0, 10) == 0.0


# --------------------------------------------------------------------------- #
# state derivation
# --------------------------------------------------------------------------- #
def test_derive_state():
    assert q.derive_state(0) == q.STATE_UNGRADED
    assert q.derive_state(1) == q.STATE_ACCRUING
    assert q.derive_state(24) == q.STATE_ACCRUING
    assert q.derive_state(25) == q.STATE_GRADED
    assert q.derive_state(100) == q.STATE_GRADED


# --------------------------------------------------------------------------- #
# track-record aggregation — the honest-n contract
# --------------------------------------------------------------------------- #
def _seed_graded(tmp_path, prices, asofs, desk="altdata", direction=1,
                 ticker="CARR", sector="Industrials"):
    """Register + grade a claim per asof, appending grades to the store."""
    grades_p = tmp_path.joinpath(*q._GRADES_FILE)
    grades_p.parent.mkdir(parents=True, exist_ok=True)
    for i, a in enumerate(asofs):
        c = q.make_claim(desk=desk, asof=a, scope_type="entity", scope_key=ticker,
                         direction=direction, horizon_d=21,
                         timestamp_quality="CRAWL_BOUNDED", sector=sector,
                         claim_family=desk)
        c["salt"] = str(i)
        stored = q.register(c, root=tmp_path)
        rows = q.grade_claim(stored, root=tmp_path, today=date(2026, 6, 1))
        with grades_p.open("a") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")


def test_track_record_counts_distinct_dates(prices, tmp_path):
    # Two DISTINCT asof dates → n_dates == 2 even though many obs (5d + 21d each).
    _seed_graded(tmp_path, prices, ["2026-02-02", "2026-02-09"])
    tr = q.compute_track_record(tmp_path)
    d21 = tr["by_desk"]["altdata"]["21"]
    assert d21["n_dates"] == 2
    assert d21["n_obs"] == 2              # one 21d obs per date
    assert d21["hit_rate"] == 1.0        # CARR beats SPY both dates
    assert d21["state"] == q.STATE_ACCRUING
    assert d21["wilson_ci_low"] is not None
    # 5d block also present
    assert tr["by_desk"]["altdata"]["5"]["n_dates"] == 2


def test_track_record_overlap_does_not_inflate_n(prices, tmp_path):
    # SAME asof registered twice under different salt → distinct claim rows, but
    # ONE date cluster → n_dates must stay 1 (the overlap illusion, §5).
    _seed_graded(tmp_path, prices, ["2026-02-02", "2026-02-02"])
    tr = q.compute_track_record(tmp_path)
    d21 = tr["by_desk"]["altdata"]["21"]
    assert d21["n_obs"] == 2             # two observations
    assert d21["n_dates"] == 1           # but ONE honest independent date


def test_track_record_graded_state_at_25_dates(prices, tmp_path):
    asofs = [d.date().isoformat() for d in pd.bdate_range("2026-02-02", periods=25)]
    _seed_graded(tmp_path, prices, asofs)
    tr = q.compute_track_record(tmp_path)
    assert tr["by_desk"]["altdata"]["21"]["state"] == q.STATE_GRADED


def test_placebo_excluded_from_headline(prices, tmp_path):
    grades_p = tmp_path.joinpath(*q._GRADES_FILE)
    grades_p.parent.mkdir(parents=True, exist_ok=True)
    # one real hit + one placebo hit under same desk
    for placebo in (False, True):
        c = q.make_claim(desk="altdata", asof="2026-02-02", scope_type="entity",
                         scope_key="CARR", direction=1, horizon_d=21,
                         timestamp_quality="CRAWL_BOUNDED", is_placebo=placebo)
        c["salt"] = "pl" if placebo else "real"
        stored = q.register(c, root=tmp_path)
        with grades_p.open("a") as fh:
            for r in q.grade_claim(stored, root=tmp_path, today=date(2026, 6, 1)):
                fh.write(json.dumps(r) + "\n")
    tr = q.compute_track_record(tmp_path)
    # only the non-placebo claim contributes to the headline n_obs at 21d
    assert tr["by_desk"]["altdata"]["21"]["n_obs"] == 1
    assert tr["counts"]["n_placebo"] == 1


def test_emit_writes_track_record(prices, tmp_path):
    _seed_graded(tmp_path, prices, ["2026-02-02"])
    payload = q.emit_track_record(tmp_path)
    out = tmp_path.joinpath(*q._TRACK_FILE)
    assert out.exists()
    disk = json.loads(out.read_text())
    assert disk["counts"]["n_claims"] == payload["counts"]["n_claims"]
    assert "by_desk" in disk and "by_family" in disk


def test_ungraded_family_state(tmp_path):
    # registered but nothing graded → no grades → family absent (UNGRADED is the
    # UI default for absent families); counts still reflect the open claim.
    c = q.make_claim(desk="policy", asof="2026-06-18", scope_type="macro",
                     scope_key="2y", direction=-1, horizon_d=63,
                     timestamp_quality="DISCLOSURE_DATE", bench="DGS2")
    q.register(c, root=tmp_path)
    tr = q.compute_track_record(tmp_path)
    assert tr["counts"]["n_claims"] == 1
    assert tr["counts"]["n_grades"] == 0
    assert q.derive_state(0) == q.STATE_UNGRADED
