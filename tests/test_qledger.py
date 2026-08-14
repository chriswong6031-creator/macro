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
# §3 promotion gate — the bound is a PROPORTION, so the null is a coin, not zero
#
# 2026-08-03 experiments audit: the gate tested `wilson_ci_low > 0` on the Wilson lower
# bound of a HIT-RATE, which lives in [0, 1]. Any nonzero hit count cleared it — the gate
# could not fail. It opened radar@5d on 2026-07-28 (a live alert fired) at hit=51.0%, whose
# CI [0.340, 0.693] brackets 0.5 outright, with mean excess NEGATIVE at -0.26%.
# --------------------------------------------------------------------------- #
def _seed_family(tmp_path, *, n_dates: int, n_hits: int, family: str = "radar",
                 horizon: int = 5) -> None:
    """Write claims + grades directly: one claim per distinct asof date, `n_hits` of them
    directional hits. promotion_check reads only these two files — no price layer needed.

    Grade rows carry an EXPLICIT clock stamp (v1/trading_days/US) rather than
    the pre-P0a unstamped shape. This suite tests §3 Wilson-CI/date-floor
    mechanics, which are clock-basis-agnostic; stamping keeps that true after
    P0c-2 (CEO ruling 2026-08-13 §5), which withdraws promotion AUTHORITY from
    a legacy-only basis specifically — see tests/test_qledger_horizon_clock.py
    for that contract. An unstamped fixture here would silently start testing
    the P0c-2 boundary instead of the CI math these tests are named for."""
    d = tmp_path / "data" / "qledger"
    d.mkdir(parents=True, exist_ok=True)
    claims, grades = [], []
    for i in range(n_dates):
        cid = f"{family}_{i:04d}"
        asof = (pd.Timestamp("2026-01-05") + pd.Timedelta(days=7 * i)).date().isoformat()
        claims.append({"claim_id": cid, "desk": family, "asof": asof,
                       "scope": {"type": "entity", "key": "SUBJ"}, "direction": 1,
                       "horizon_d": horizon, "bench": "SPY", "control": "CTRL",
                       "timestamp_quality": "CRAWL_BOUNDED", "is_placebo": False,
                       "status": "open", "claim_family": family,
                       "timestamp": "2026-01-01T00:00:00+00:00"})
        hit = i < n_hits
        grades.append({"claim_id": cid, "horizon_d": horizon,
                       "graded_at": "2026-06-01T00:00:00+00:00",
                       "subject_ret": 0.05 if hit else -0.03, "bench_ret": 0.01,
                       "control_ret": 0.02,
                       "excess": 0.04 if hit else -0.04, "hit": hit,
                       "embargo_applied": False,
                       "horizon_unit": q.HORIZON_UNIT_TRADING,
                       "clock_version": q.CLOCK_V1, "clock_market": q.MARKET_US})
    (d / "claims.jsonl").write_text("".join(json.dumps(r) + "\n" for r in claims))
    (d / "grades.jsonl").write_text("".join(json.dumps(r) + "\n" for r in grades))


def test_promotion_gate_refuses_a_coin_flip_hit_rate(tmp_path):
    """radar@5d as it actually stood: 27 date-clusters at ~51%. NOT eligible."""
    _seed_family(tmp_path, n_dates=27, n_hits=14)          # 14/27 = 51.9%
    r = q.promotion_check("radar", 5, root=tmp_path)

    assert r.n_dates == 27 >= q.PROMOTION_MIN_DATES         # criterion 1 clears...
    assert r.wilson_ci_low == pytest.approx(0.3399, abs=1e-3)   # ...the live CI-low exactly
    assert r.wilson_ci_low > 0, (
        "the OLD predicate — this is why `> 0` was vacuous: the bound is a proportion")
    assert not r.eligible, (
        f"a hit-rate CI that brackets 0.5 is consistent with no skill at all. "
        f"ci_low={r.wilson_ci_low}, reason={r.reason}")
    assert r.demote is True
    assert "coin" in r.reason.lower()


def test_promotion_gate_admits_a_hit_rate_that_clears_the_coin(tmp_path):
    """The floor is a bar, not a wall: 75% over 27 dates puts the whole CI above 0.5."""
    _seed_family(tmp_path, n_dates=27, n_hits=20)          # 20/27 = 74.1%
    r = q.promotion_check("radar", 5, root=tmp_path)

    assert r.n_dates == 27
    assert r.wilson_ci_low == pytest.approx(0.5532, abs=1e-3)
    assert r.wilson_ci_low > q.PROMOTION_MIN_CI_LOW
    assert r.eligible, f"ci_low={r.wilson_ci_low} clears 0.5 — reason={r.reason}"
    assert not r.demote


def test_promotion_gate_still_needs_the_date_floor(tmp_path):
    """A great hit-rate on too few clusters is still refused on criterion 1."""
    _seed_family(tmp_path, n_dates=10, n_hits=9)
    r = q.promotion_check("radar", 5, root=tmp_path)
    assert not r.eligible and "n_dates=10" in r.reason


# --------------------------------------------------------------------------- #
# P0c-1 — control_only hit counting must be DIRECTION-CORRECT
# research/PREREG_P0C1_DIRECTION_CORRECT_CONTROL_HITS.md
#
# THE DEFECT: `if ctrl_excess > 0: hits += 1` never read the claim's own
# `direction`, so a direction=-1 (bearish) call that correctly called
# subject_ret < control_ret scored subj-ctrl<0 -> a MISS, and a WRONG bearish
# call scored a HIT — an inverted hit series for any family holding short
# claims. Fixed to `direction * (subject_ret - control_ret) > 0`. A second,
# smaller fault in the same branch: `bench_ret` was gated on but never used,
# so a row with a valid control leg but a null bench silently fell through to
# the primary-hit fallback instead of being scored on the control leg.
# --------------------------------------------------------------------------- #
def _seed_control_rows(tmp_path, rows, *, family: str = "ctrlfam",
                       horizon: int = 21) -> None:
    """Write claims + grades directly for control_only=True fixtures — no price
    layer needed, promotion_check reads only the two store files. `rows` is a
    list of per-claim dicts; each may set `family` (default the `family` kwarg),
    `claim_id`, `asof` (default one distinct date per row, 7 days apart),
    `direction` (default 1), `subject_ret`, `control_ret`, `bench_ret` (default
    0.01), and `hit` (the PRIMARY, bench-relative hit stored on the row —
    defaults to True so the outer `if hit is not None` gate in promotion_check
    does not itself exclude the row; these fixtures exist to exercise the
    control-LEG logic specifically, not the primary-hit gate).

    Grade rows carry an EXPLICIT clock stamp (v1/trading_days/US), same
    rationale as `_seed_family` above: this suite (P0c-1, direction-correct
    control-only hit counting) is clock-basis-agnostic and must stay that way
    after P0c-2 (CEO ruling 2026-08-13 §5) withdraws promotion AUTHORITY from
    an unstamped/legacy basis specifically."""
    d = tmp_path / "data" / "qledger"
    d.mkdir(parents=True, exist_ok=True)
    claims, grades = [], []
    for i, r in enumerate(rows):
        fam = r.get("family", family)
        cid = r.get("claim_id") or f"{fam}_{i:04d}"
        asof = r.get("asof") or (
            pd.Timestamp("2026-01-05") + pd.Timedelta(days=7 * i)
        ).date().isoformat()
        claims.append({"claim_id": cid, "desk": fam, "asof": asof,
                       "scope": {"type": "entity", "key": "SUBJ"},
                       "direction": r.get("direction", 1),
                       "horizon_d": horizon, "bench": "SPY", "control": "CTRL",
                       "timestamp_quality": "CRAWL_BOUNDED", "is_placebo": False,
                       "status": "open", "claim_family": fam,
                       "timestamp": "2026-01-01T00:00:00+00:00"})
        grades.append({"claim_id": cid, "horizon_d": horizon,
                       "graded_at": "2026-06-01T00:00:00+00:00",
                       "subject_ret": r.get("subject_ret"),
                       "bench_ret": r.get("bench_ret", 0.01),
                       "control_ret": r.get("control_ret"),
                       "excess": r.get("excess", 0.0),
                       "hit": r.get("hit", True),
                       "embargo_applied": False,
                       "horizon_unit": q.HORIZON_UNIT_TRADING,
                       "clock_version": q.CLOCK_V1, "clock_market": q.MARKET_US})
    (d / "claims.jsonl").write_text("".join(json.dumps(x) + "\n" for x in claims))
    (d / "grades.jsonl").write_text("".join(json.dumps(x) + "\n" for x in grades))


def test_p0c1_mirrored_bullish_and_bearish_produce_the_same_control_only_hit_rate(
        tmp_path):
    """Mechanical acceptance #1/#2 (prereg §6). Same magnitudes: a direction=+1
    family whose subject beats control by 0.05, and a direction=-1 family whose
    subject TRAILS control by the same 0.05, are both 30/30 CORRECT calls and
    must produce the SAME control-only hit rate — proven via an identical
    Wilson CI lower bound at identical n_dates. Before the fix the bearish
    family scored 0/30 (raw ctrl_excess = subj-ctrl = -0.05, and the old
    `if ctrl_excess > 0` never read direction), inverted."""
    rows = (
        [{"family": "bull", "direction": 1, "subject_ret": 0.06,
         "control_ret": 0.01} for _ in range(30)] +
        [{"family": "bear", "direction": -1, "subject_ret": 0.01,
         "control_ret": 0.06} for _ in range(30)]
    )
    _seed_control_rows(tmp_path, rows)

    r_bull = q.promotion_check("bull", 21, root=tmp_path, control_only=True)
    r_bear = q.promotion_check("bear", 21, root=tmp_path, control_only=True)

    assert r_bull.n_dates == r_bear.n_dates == 30
    assert r_bull.eligible is True and r_bear.eligible is True, (
        r_bull.reason, r_bear.reason)
    assert r_bull.wilson_ci_low == pytest.approx(r_bear.wilson_ci_low)
    # mechanical acceptance #2: the bearish family of CORRECT calls reads as a
    # near-1.0 hit rate, not 0.0 — this is the inversion, caught.
    assert r_bear.wilson_ci_low == pytest.approx(q.wilson_ci_low(30, 30))


def test_p0c1_salience_direction_zero_family_yields_no_directional_hits_and_no_denominator_inflation(  # noqa: E501
        tmp_path):
    """Mechanical acceptance #3: a direction=0 (salience) family must contribute
    NO directional hit and must NOT inflate the control-only denominator, even
    when the row's primary `hit` field is not None (defensive: in production
    grade_claim() already stores hit=None for direction=0 salience claims, but
    this function's control-only semantics must not silently depend on that
    upstream invariant — prereg §2/§5)."""
    rows = [{"direction": 0, "subject_ret": 0.06, "control_ret": 0.01, "hit": True}
           for _ in range(30)]
    _seed_control_rows(tmp_path, rows, family="salience")
    r = q.promotion_check("salience", 21, root=tmp_path, control_only=True)

    assert r.n_dates == 30            # n_dates is untouched — same claim set
    assert r.wilson_ci_low is None    # no directional hits recorded
    assert r.eligible is False
    assert "no directional hits" in r.reason
    assert "graded_hits=0" in r.reason


def test_p0c1_missing_control_leg_changes_neither_numerator_nor_denominator(
        tmp_path):
    """Mechanical acceptance #4. A null `control_ret` row must not move the
    control-only hit rate at all — proven by adding such rows on the SAME date
    clusters an already-scored family holds (so n_dates cannot move either) and
    checking the Wilson CI lower bound is unchanged. Before the fix these rows
    fell back to the primary `hit` field (`elif hit: hits += 1`), silently
    mixing bench-relative outcomes into the control-only rate."""
    dates = [(pd.Timestamp("2026-01-05") + pd.Timedelta(days=7 * i)).date().isoformat()
            for i in range(25)]
    base_rows = [{"family": "base", "direction": 1, "subject_ret": 0.06,
                 "control_ret": 0.01, "asof": d, "claim_id": f"base_{i}"}
                for i, d in enumerate(dates)]
    plus_rows = [{"family": "plus", "direction": 1, "subject_ret": 0.06,
                 "control_ret": 0.01, "asof": d, "claim_id": f"plus_{i}"}
                for i, d in enumerate(dates)]
    # extra null-control rows, reusing the FIRST 10 dates already counted above
    # — under the pre-fix fallback these would have counted as hits (hit=True).
    extra_null_rows = [{"family": "plus", "direction": 1, "subject_ret": 0.06,
                        "control_ret": None, "hit": True,
                        "asof": dates[i], "claim_id": f"plusnull_{i}"}
                       for i in range(10)]
    _seed_control_rows(tmp_path, base_rows + plus_rows + extra_null_rows)

    baseline = q.promotion_check("base", 21, root=tmp_path, control_only=True)
    plus = q.promotion_check("plus", 21, root=tmp_path, control_only=True)

    assert plus.n_dates == baseline.n_dates == 25, (
        "the extra null-control rows reuse EXISTING dates — n_dates must not "
        "move because of them")
    assert plus.wilson_ci_low == baseline.wilson_ci_low, (
        "a null control_ret row must change neither the numerator nor the "
        "denominator of the control-only hit rate")


def test_p0c1_exact_zero_control_excess_is_not_a_hit(tmp_path):
    """Mechanical acceptance #5. `raw_control_excess == 0` exactly is NOT a hit
    (strict inequality, prereg §2/§5) — but the row IS scoreable (a valid
    control leg), so it still counts in the denominator, driving the hit rate
    down rather than being silently dropped."""
    rows = [{"direction": 1, "subject_ret": 0.03, "control_ret": 0.03}
           for _ in range(25)]
    _seed_control_rows(tmp_path, rows, family="zero")
    r = q.promotion_check("zero", 21, root=tmp_path, control_only=True)

    assert r.n_dates == 25
    assert r.wilson_ci_low is not None          # rows WERE scoreable...
    assert r.wilson_ci_low == q.wilson_ci_low(0, 25)   # ...but zero hits
    assert r.eligible is False


def test_p0c1_null_bench_ret_does_not_block_a_control_leg_scored_row(tmp_path):
    """The second fault named in the prereg: `bench_ret` used to be gated on but
    never used in the comparison, so a row with a VALID control leg but a NULL
    bench silently fell through to the `elif hit: hits += 1` fallback. `hit`
    (the PRIMARY, bench-relative outcome) is deliberately set to a MISS here
    while the control-leg call is a correct HIT — a coincidental match on the
    same value would prove nothing. The row must now be scored on the control
    leg, exactly like any other row, regardless of bench_ret."""
    rows = [{"direction": 1, "subject_ret": 0.06, "control_ret": 0.01,
            "bench_ret": None, "hit": False}
           for _ in range(25)]
    _seed_control_rows(tmp_path, rows, family="nullbench")
    r = q.promotion_check("nullbench", 21, root=tmp_path, control_only=True)

    assert r.n_dates == 25
    assert r.eligible is True, (
        "a valid control leg with a null bench must be scored on the control "
        f"leg, not fall back to the primary (bench-relative) hit. "
        f"reason={r.reason}")
    assert r.wilson_ci_low == pytest.approx(q.wilson_ci_low(25, 25))


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
