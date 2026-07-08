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


# --------------------------------------------------------------------------- #
# W0 Stage B-e — register_batch, next-bar fill discontinuity, regime stamps
# --------------------------------------------------------------------------- #
def _mk_claim(asof="2026-02-02", key="CARR", h=21, salt=""):
    return q.make_claim(desk="altdata", asof=asof, scope_type="entity",
                        scope_key=key, direction=1, horizon_d=h,
                        timestamp_quality="CRAWL_BOUNDED", sector=None,
                        extra={"salt": salt} if salt else None) | (
                            {"salt": salt} if salt else {})


@pytest.fixture
def null_regime(monkeypatch):
    """Hermetic regime stamps: the vector lookup returns all-None (no store)."""
    q._regime_stamp_cached.cache_clear()
    import engine.regime_vector as rv
    monkeypatch.setattr(rv, "get_vector_for_date",
                        lambda asof, data_dir=None: {k: None for k in
                                                     q._REGIME_STAMP_KEYS})
    yield
    q._regime_stamp_cached.cache_clear()


def test_register_batch_equivalent_to_loop(prices, null_regime, tmp_path):
    """N register() calls and one register_batch() produce identical stores
    (modulo the registration timestamp)."""
    claims = [_mk_claim(salt=f"s{i}") for i in range(5)]
    loop_root = tmp_path / "loop"
    batch_root = tmp_path / "batch"
    for c in claims:
        q.register(dict(c), root=loop_root)
    q.register_batch([dict(c) for c in claims], root=batch_root)

    a = q.load_claims(loop_root)
    b = q.load_claims(batch_root)
    assert len(a) == len(b) == 5
    strip = lambda r: {k: v for k, v in r.items() if k != "timestamp"}  # noqa: E731
    assert [strip(r) for r in a] == [strip(r) for r in b]


def test_register_batch_error_isolation(prices, null_regime, tmp_path):
    """One malformed entry must not sink the batch: its slot reports error,
    every other claim still registers."""
    good1, good2 = _mk_claim(salt="a"), _mk_claim(salt="b")
    results = q.register_batch([good1, "not-a-claim", good2], root=tmp_path)
    assert len(results) == 3
    assert results[0].get("status") == q.STATUS_OPEN
    assert results[1].get("status") == "error" and results[1].get("error")
    assert results[2].get("status") == q.STATUS_OPEN
    assert len(q.load_claims(tmp_path)) == 2


def test_register_batch_dedupe_keep_first(prices, null_regime, tmp_path):
    """Dedupe by claim_id: the store's existing row wins; within a batch the
    first occurrence wins — later duplicates return the stored row."""
    c = _mk_claim(salt="dup")
    first = q.register(dict(c), root=tmp_path)
    results = q.register_batch([dict(c), dict(c)], root=tmp_path)
    assert len(q.load_claims(tmp_path)) == 1
    assert all(r["claim_id"] == first["claim_id"] for r in results)
    assert all(r["timestamp"] == first["timestamp"] for r in results)


def test_register_batch_one_store_read(prices, null_regime, tmp_path, monkeypatch):
    """The batch loads the store ONCE regardless of batch size — the whole
    point of §5.2 (register() is O(file) per call)."""
    calls = {"n": 0}
    real = q.load_claims

    def counting(root=None):
        calls["n"] += 1
        return real(root)

    monkeypatch.setattr(q, "load_claims", counting)
    q.register_batch([_mk_claim(salt=f"x{i}") for i in range(10)], root=tmp_path)
    assert calls["n"] == 1


def test_fwd_ret_next_bar_vs_legacy(prices, tmp_path):
    """The stamped discontinuity: next_bar enters at the FIRST close STRICTLY
    AFTER the asof; asof_legacy entered at the close ON/BEFORE it."""
    s = prices["CARR"]
    asof = str(s.index[10].date())
    legacy = q._fwd_ret("CARR", tmp_path, asof, 5,
                        fill_convention=q.FILL_ASOF_LEGACY)
    nxt = q._fwd_ret("CARR", tmp_path, asof, 5)

    e0_legacy = float(s.iloc[10])
    e0_next = float(s.iloc[11])
    assert e0_legacy != e0_next
    # exits: legacy anchored at asof+5d, next_bar anchored at fill+5d
    end_leg = s[s.index <= s.index[10] + pd.Timedelta(days=5)].iloc[-1]
    end_nxt = s[s.index <= s.index[11] + pd.Timedelta(days=5)].iloc[-1]
    assert legacy == pytest.approx(round(end_leg / e0_legacy - 1.0, 6))
    assert nxt == pytest.approx(round(end_nxt / e0_next - 1.0, 6))
    # (on this constant-drift fixture the two RATIOS coincide even though the
    # entry bars differ — the window-pinning asserts above are the proof of
    # the convention change, not the return values)


def test_fwd_ret_next_bar_requires_covered_exit(prices, tmp_path):
    """Never grade a shortened window: when the series ends before fill+h the
    next-bar path returns None instead of grading to the last available bar."""
    s = prices["CARR"]
    late_asof = str(s.index[-2].date())     # fill = last bar; fill+21d uncovered
    assert q._fwd_ret("CARR", tmp_path, late_asof, 21) is None


def test_grade_rows_carry_fill_convention(prices, null_regime, tmp_path):
    """New grade rows are stamped next_bar + entry_fill_date; the discontinuity
    is visible, never silent."""
    c = q.register(_mk_claim(asof="2026-02-02", h=21), root=tmp_path)
    rows = q.grade_claim(c, root=tmp_path, today=date(2026, 6, 1))
    assert rows, "expected matured grade rows"
    s = prices["CARR"]
    expected_fill = str(s[s.index > pd.Timestamp("2026-02-02")].index[0].date())
    for r in rows:
        assert r["fill_convention"] == q.FILL_NEXT_BAR
        assert r["entry_fill_date"] == expected_fill


def test_track_record_counts_convention_and_unstamped(prices, null_regime, tmp_path):
    """compute_track_record prints the per-convention grade split (missing
    field == asof_legacy) and the §3.4 residual unstamped-claim count."""
    c = q.register(_mk_claim(asof="2026-02-02", h=21), root=tmp_path)
    rows = q.grade_claim(c, root=tmp_path, today=date(2026, 6, 1))
    gp = tmp_path / "data" / "qledger" / "grades.jsonl"
    gp.parent.mkdir(parents=True, exist_ok=True)
    with gp.open("w", encoding="utf-8") as fh:
        legacy = {"claim_id": "deadbeef", "horizon_d": 5, "excess": 0.01,
                  "hit": True}          # pre-B-e row: no fill_convention
        fh.write(json.dumps(legacy) + "\n")
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    tr = q.compute_track_record(tmp_path)
    conv = tr["counts"]["grades_by_fill_convention"]
    assert conv.get(q.FILL_ASOF_LEGACY) == 1
    assert conv.get(q.FILL_NEXT_BAR) == len(rows)
    # null_regime fixture → the registered claim carries no vector stamp
    assert tr["counts"]["n_claims_unstamped_regime"] == 1


def test_regime_stamp_on_register(prices, tmp_path, monkeypatch):
    """Claims registered while the persisted vector covers their asof carry the
    full PIT stamp; the lookup is called with the claim's own asof."""
    q._regime_stamp_cached.cache_clear()
    import engine.regime_vector as rv
    seen = {}

    def fake(asof, data_dir=None):
        seen["asof"] = asof
        return {"rate_pressure": "neutral", "quad_hard_label": "Q1",
                "fused_risk_label": None, "vol_regime": "normalizing",
                "risk_radar_state": "calm", "regime_vector_degraded": 0,
                "vector_asof": "2026-02-02", "staleness_hours": 0.0}

    monkeypatch.setattr(rv, "get_vector_for_date", fake)
    stored = q.register(_mk_claim(asof="2026-02-02"), root=tmp_path)
    q._regime_stamp_cached.cache_clear()
    assert seen["asof"] == "2026-02-02"
    assert stored["rate_pressure"] == "neutral"
    assert stored["vector_asof"] == "2026-02-02"
    assert stored["species_id"] is None and stored["archetype"] is None


def test_backfill_regime_stamps_null_only(prices, tmp_path, monkeypatch):
    """Backfill fills ONLY missing stamps (keep-FIRST): an existing non-null
    value is never altered; the residual unstamped count is honest."""
    q._regime_stamp_cached.cache_clear()
    import engine.regime_vector as rv
    covered = {"rate_pressure": "pressure", "quad_hard_label": "Q2",
               "fused_risk_label": "risk_on", "vol_regime": "warning",
               "risk_radar_state": "watch", "regime_vector_degraded": 0,
               "vector_asof": "2026-02-02", "staleness_hours": 0.0}
    monkeypatch.setattr(
        rv, "get_vector_for_date",
        lambda asof, data_dir=None: (dict(covered) if asof == "2026-02-02"
                                     else {k: None for k in q._REGIME_STAMP_KEYS}))

    p = tmp_path / "data" / "qledger" / "claims.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    row_a = {"claim_id": "a1", "asof": "2026-02-02", "status": "open"}
    row_b = {"claim_id": "b2", "asof": "2026-02-02", "status": "open",
             "vector_asof": "2026-01-30", "rate_pressure": "keepme"}
    row_c = {"claim_id": "c3", "asof": "1999-01-01", "status": "open"}
    with p.open("w", encoding="utf-8") as fh:
        for r in (row_a, row_b, row_c):
            fh.write(json.dumps(r) + "\n")

    out = q.backfill_regime_stamps(tmp_path)
    q._regime_stamp_cached.cache_clear()
    # W1: return dict now includes n_precoverage
    assert out["n_claims"] == 3
    assert out["n_backfilled"] == 1
    assert out["n_unstamped"] == 1
    assert "n_precoverage" in out  # W1 addition
    rows = {r["claim_id"]: r for r in q.load_claims(tmp_path)}
    assert rows["a1"]["rate_pressure"] == "pressure"          # filled
    assert rows["a1"]["vector_asof"] == "2026-02-02"
    # W1 R-CI3: backfilled row must carry regime_stamp_basis='recomputed_history'
    assert rows["a1"].get("regime_stamp_basis") == "recomputed_history", (
        f"R-CI3 provenance: expected recomputed_history, got {rows['a1'].get('regime_stamp_basis')}"
    )
    assert rows["b2"]["rate_pressure"] == "keepme"            # never altered
    assert rows["b2"]["vector_asof"] == "2026-01-30"
    # b2 already had vector_asof → NOT backfilled → must NOT have regime_stamp_basis set by backfill
    assert rows["b2"].get("regime_stamp_basis") is None       # keep-FIRST: already stamped
    assert rows["c3"].get("vector_asof") is None              # honest residual (precoverage)


def test_backfill_regime_stamps_skips_a_share_hk(prices, tmp_path, monkeypatch):
    """Claims with .SS, .SZ, or .HK symbols must be skipped — they must not
    receive US regime_vector rich stamps.  The skipped count must be logged.
    """
    q._regime_stamp_cached.cache_clear()
    import engine.regime_vector as rv
    covered = {"rate_pressure": "pressure", "quad_hard_label": "Q2",
               "fused_risk_label": "risk_on", "vol_regime": "warning",
               "risk_radar_state": "watch", "regime_vector_degraded": 0,
               "vector_asof": "2026-02-02", "staleness_hours": 0.0}
    monkeypatch.setattr(
        rv, "get_vector_for_date",
        lambda asof, data_dir=None: dict(covered))

    p = tmp_path / "data" / "qledger" / "claims.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)

    # US claim — should receive stamp
    row_us = {"claim_id": "us1", "asof": "2026-02-02", "scope": {"type": "entity", "key": "AAPL"}}
    # A-share claims — must be skipped
    row_ss = {"claim_id": "ss1", "asof": "2026-02-02", "scope": {"type": "entity", "key": "600519.SS"}}
    row_sz = {"claim_id": "sz1", "asof": "2026-02-02", "scope": {"type": "entity", "key": "300725.SZ"}}
    # HK claim — must be skipped
    row_hk = {"claim_id": "hk1", "asof": "2026-02-02", "scope": {"type": "entity", "key": "0700.HK"}}

    with p.open("w", encoding="utf-8") as fh:
        for r in (row_us, row_ss, row_sz, row_hk):
            fh.write(json.dumps(r) + "\n")

    out = q.backfill_regime_stamps(tmp_path)
    q._regime_stamp_cached.cache_clear()

    # Only the US claim was backfilled
    assert out["n_backfilled"] == 1, f"Expected 1 backfilled (US only), got: {out}"

    rows = {r["claim_id"]: r for r in q.load_claims(tmp_path)}
    assert rows["us1"].get("vector_asof") == "2026-02-02", "US claim must receive stamp"
    assert rows["ss1"].get("vector_asof") is None, ".SS claim must be skipped"
    assert rows["sz1"].get("vector_asof") is None, ".SZ claim must be skipped"
    assert rows["hk1"].get("vector_asof") is None, ".HK claim must be skipped"


def test_w1_backfill_regime_stamps_basis_recomputed_history(prices, tmp_path, monkeypatch):
    """W1 R-CI3: backfill_regime_stamps sets regime_stamp_basis='recomputed_history'
    on backfilled rows.  Pre-existing basis values are never overwritten (keep-FIRST).
    Claims predating coverage stay null + are counted in n_precoverage.
    The returned dict includes n_precoverage.
    """
    q._regime_stamp_cached.cache_clear()
    import engine.regime_vector as rv
    covered = {
        "rate_pressure": "hot", "quad_hard_label": "Q3",
        "fused_risk_label": "risk_on", "vol_regime": "calm",
        "risk_radar_state": "neutral", "regime_vector_degraded": 0,
        "vector_asof": "2026-05-15", "staleness_hours": 0.0,
    }
    # Monkeypatch: 2026-05-15 covered; 1998-01-01 pre-coverage (returns nulls)
    monkeypatch.setattr(
        rv, "get_vector_for_date",
        lambda asof, data_dir=None: (
            dict(covered) if asof == "2026-05-15"
            else {k: None for k in q._REGIME_STAMP_KEYS}
        ),
    )

    p = tmp_path / "data" / "qledger" / "claims.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)

    # row_a: no stamps, covered date → should be backfilled + get recomputed_history basis
    row_a = {"claim_id": "a1", "asof": "2026-05-15", "scope": {"type": "entity", "key": "NVDA"}}
    # row_b: pre-existing basis value → basis must not be overwritten
    row_b = {
        "claim_id": "b2", "asof": "2026-05-15",
        "scope": {"type": "entity", "key": "AAPL"},
        "regime_stamp_basis": "pit_live", "vector_asof": None,
    }
    # row_c: predates coverage → stays null, counted in n_precoverage
    row_c = {"claim_id": "c3", "asof": "1998-01-01", "scope": {"type": "entity", "key": "IBM"}}

    with p.open("w", encoding="utf-8") as fh:
        for r in (row_a, row_b, row_c):
            fh.write(json.dumps(r) + "\n")

    out = q.backfill_regime_stamps(tmp_path)
    q._regime_stamp_cached.cache_clear()

    assert out["n_claims"] == 3
    assert out["n_backfilled"] == 2  # a1 and b2 both got stamps
    assert out["n_unstamped"] == 1   # c3 stays unstamped
    assert "n_precoverage" in out
    assert out["n_precoverage"] == 1  # c3 predates coverage

    rows = {r["claim_id"]: r for r in q.load_claims(tmp_path)}

    # a1: backfilled → must have recomputed_history basis
    assert rows["a1"].get("vector_asof") == "2026-05-15"
    assert rows["a1"].get("regime_stamp_basis") == "recomputed_history", (
        f"R-CI3: expected recomputed_history, got {rows['a1'].get('regime_stamp_basis')}"
    )

    # b2: had regime_stamp_basis='pit_live' pre-set but vector_asof=None
    # → the lying label is normalised to 'recomputed_history' (values are
    #   demonstrably recomputed; keep-FIRST only applies to rows that had
    #   a non-None vector_asof, i.e. were genuinely PIT-stamped)
    assert rows["b2"].get("regime_stamp_basis") == "recomputed_history", (
        f"R-CI3 basis normalisation: pit_live with vector_asof=None must become "
        f"recomputed_history, got {rows['b2'].get('regime_stamp_basis')}"
    )

    # c3: predates coverage → vector_asof stays None
    assert rows["c3"].get("vector_asof") is None
