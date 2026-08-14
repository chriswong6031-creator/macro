"""P0d — THE MATCHED-CONTROL EVIDENCE CONTRACT.

Contract: research/PREREG_P0D_MATCHED_CONTROL_CONTRACT.md (clauses C1-C9).
Grounding census: research/EVAL_OS_P0D_CONTROL_CENSUS.md.

THE DEFECT THIS SUITE PINS. `promotion_check(control_only=True)` was the blanket
production call on every family, while the live store held 46,695 claims and
ZERO control legs (census §0). Three separate failures hid inside that one call:

  * the evaluation basis was decided by DATA, not policy — a family "graded vs
    matched control" purely because a caller passed a flag, and would have
    silently fallen back onto bench-relative outcomes on any row whose control
    leg was missing (the P0c-1 fallback, since removed);
  * the Wilson interval projected a rate measured on the CONTROLLED SUBSET onto
    the WHOLE family's date count (census D0-3) — n=37 stated as n=100;
  * nothing recorded WHEN matched-control evidence began, so a later import of
    old, control-carrying rows would have been indistinguishable from evidence
    accrued prospectively.

Every test below carries its MUTATION CONTROL in the docstring: the specific
edit to the guarded logic that must make THIS NAMED TEST FAIL. A green
assert-the-field-exists test is not a control and is not counted (C7).

Hermetic: every store is a tmp_path store built by hand or through the real
registrar; the price layer is monkeypatched. NOTHING here reads or asserts over
data/qledger — the nightly-appended store is never a fixture, and the
append-only law (P2) forbids assertions the nightly can falsify.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from engine import qledger as q
from lib.nyse_calendar import sessions_between


# --------------------------------------------------------------------------- #
# families — the REAL table entries, so these tests exercise the governed
# classification rather than a fixture's private vocabulary
# --------------------------------------------------------------------------- #
REQ_A = "stock_desk"            # matched_control_required
REQ_B = "demand_chain"          # matched_control_required
BENCH_FAM = "radar"             # benchmark_only
NA_FAM = "us_importance_v0"     # not_applicable
UNCLASSIFIED_FAM = "a_family_no_table_row_names"

CLOCK_T0 = "2025-01-01T00:00:00+00:00"


def _dates(n: int, start: str = "2025-02-03") -> list[str]:
    """`n` DISTINCT asof dates — one independent date cluster each ([P1]/§5)."""
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


def _claim(*, family: str, asof: str, direction: int = 1,
           control: str | None = "XLK", subject: str = "AAPL",
           bench: str = "SPY", horizon: int = 21,
           unit: str | None = "trading_days",
           timestamp: str | None = None, claim_id: str | None = None,
           is_placebo: bool = False, status: str = "open") -> dict:
    """One STORED claim row (the shape `_prepare_claim` persists).

    `timestamp` defaults to the asof date, i.e. registered the day the call was
    made — the prospective case. A test that wants a RETROSPECTIVE row passes a
    later timestamp explicitly (T5)."""
    cid = claim_id or f"{family}|{asof}|{direction}|{subject}|{control}"
    return {
        "claim_id": cid,
        "desk": family,
        "claim_family": family,
        "asof": asof,
        "scope": {"type": "entity", "key": subject},
        "direction": direction,
        "horizon_d": horizon,
        "horizon_unit": unit,
        "bench": bench,
        "control": control,
        "timestamp_quality": "CRAWL_BOUNDED",
        "is_placebo": is_placebo,
        "status": status,
        "timestamp": timestamp or f"{asof}T13:00:00+00:00",
    }


def _grade_row(claim: dict, horizon: int = 21, *,
               subject_ret: float = 0.06, control_ret: float | None = 0.01,
               bench_ret: float = 0.01, hit: bool | None = True) -> dict:
    """One grade row with the REAL clock stamps `grade_claim` writes, resolved
    through the same `claim_window` the grader uses — so `grade_clock_basis`
    reads these rows exactly as it reads production ones."""
    window = q.claim_window(claim, horizon)
    stamp: dict = {}
    if window is not None:
        stamp = {
            "horizon_unit": window.horizon_unit,
            "clock_version": window.clock_version,
            "clock_exit_date": window.exit_date.isoformat(),
            "clock_coverage_date": window.coverage_date.isoformat(),
            "clock_market": window.market,
        }
    return {
        "claim_id": claim["claim_id"],
        "horizon_d": horizon,
        "graded_at": "2025-12-01T00:00:00+00:00",
        "subject_ret": subject_ret,
        "bench_ret": bench_ret,
        "control_ret": control_ret,
        "excess": round((subject_ret or 0.0) - bench_ret, 6),
        "hit": hit,
        "embargo_applied": False,
        "fill_convention": q.FILL_NEXT_BAR,
        "entry_fill_date": window.fill_date.isoformat() if window else None,
        **stamp,
    }


def _write_store(root: Path, claims: list[dict], grades: list[dict]) -> None:
    d = Path(root) / "data" / "qledger"
    d.mkdir(parents=True, exist_ok=True)
    (d / "claims.jsonl").write_text(
        "".join(json.dumps(c) + "\n" for c in claims), encoding="utf-8")
    (d / "grades.jsonl").write_text(
        "".join(json.dumps(g) + "\n" for g in grades), encoding="utf-8")


def _start_clock(root: Path, family: str, *, when: str = CLOCK_T0,
                 control: str = "XLK", horizon: int = 21) -> dict:
    """Start a family's clock THROUGH THE REGISTRAR'S OWN WRITER — never by
    hand-writing the file, which is the retrospective stamping C3.1 forbids."""
    return q.record_control_clock_start(
        family, horizon_d=horizon, horizon_unit="trading_days",
        control=control, root=root, now=when)


def _clock_dir(root: Path) -> Path:
    return Path(root).joinpath(*q._CONTROL_CLOCK_DIR)


def _cohort(family: str, n: int, *, controlled: int, direction: int = 1,
            correct: bool = True, horizon: int = 21,
            start: str = "2025-02-03") -> tuple[list[dict], list[dict]]:
    """`n` prospective cohort claims on `n` distinct dates, the first
    `controlled` of them carrying a valid control leg AND a control return.

    An UNCONTROLLED member is a real registered claim with no control — it stays
    in the cohort and therefore in the coverage denominator (C4.1). Its grade
    row still carries the bench legs and a bench-relative `hit`, which is
    exactly the material a bench fallback would have eaten."""
    claims, grades = [], []
    for i, asof in enumerate(_dates(n, start)):
        has_ctrl = i < controlled
        c = _claim(family=family, asof=asof, direction=direction, horizon=horizon,
                   control="XLK" if has_ctrl else None)
        claims.append(c)
        # subject beats control by 0.05 for a correct +1 call; a correct -1 call
        # TRAILS the control by the same 0.05 (the mirrored pair, P0c-1 §2).
        if direction == 1:
            subj, ctrl = (0.06, 0.01) if correct else (0.01, 0.06)
        else:
            subj, ctrl = (0.01, 0.06) if correct else (0.06, 0.01)
        grades.append(_grade_row(
            c, horizon, subject_ret=subj,
            control_ret=ctrl if has_ctrl else None,
            bench_ret=0.0,
            # the BENCH-relative hit: deliberately True on every row, controlled
            # or not, so any fallback onto it would be visible as a pass.
            hit=True))
    return claims, grades


# --------------------------------------------------------------------------- #
# synthetic price layer (only the tests that call grade_claim need it)
# --------------------------------------------------------------------------- #
def _session_series(start: str, end: str, start_px: float, drift: float) -> pd.Series:
    idx = [pd.Timestamp(d) for d in
           sessions_between(date.fromisoformat(start), date.fromisoformat(end))]
    return pd.Series([start_px * (1.0 + drift) ** i for i in range(len(idx))],
                     index=pd.DatetimeIndex(idx))


@pytest.fixture
def prices(monkeypatch):
    store = {
        "AAPL": _session_series("2025-01-02", "2025-12-31", 100.0, 0.010),
        "SPY": _session_series("2025-01-02", "2025-12-31", 400.0, 0.002),
        "XLK": _session_series("2025-01-02", "2025-12-31", 100.0, 0.004),
        "XLV": _session_series("2025-01-02", "2025-12-31", 100.0, 0.003),
    }
    monkeypatch.setattr("engine.ai_desk._close_series",
                        lambda ticker, root: store.get(ticker))
    return store


# =========================================================================== #
# T1 — NO BENCH FALLBACK (adversarial control #1, contract C5.1)
# =========================================================================== #
def test_t1_required_family_with_zero_controls_refuses_before_the_clock_starts(tmp_path):
    """A required family with a PERFECT bench record and no control legs, before
    its clock has started, refuses on the matched-control basis and states that
    the evidence has not begun — never a miss, never a bench substitute.

    MUTATION CONTROL: route `CONTROL_POLICY_REQUIRED` to
    `promotion_check(..., control_only=False)` inside `promotion_check_dispatch`
    (the restored bench fallback). 30/30 bench hits then clear the §3 gate and
    this test fails on `eligible is False`.
    """
    claims, grades = _cohort(REQ_A, 30, controlled=0)
    _write_store(tmp_path, claims, grades)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)

    assert r.evidence_basis == q.EVIDENCE_BASIS_MATCHED_CONTROL
    assert r.eligible is False
    assert r.n_dates == 0
    assert r.current_state == q.STATE_UNGRADED
    assert "has not begun accruing" in r.reason
    assert "no bench substitute" in r.reason
    assert "PASS" not in r.reason, (
        "a refusal must never carry a pass sentence from the bench arm")
    # The bench record is genuinely strong — that is the whole point of the case.
    bench_view = q.promotion_check(REQ_A, 21, root=tmp_path, control_only=False)
    assert bench_view.eligible is True and bench_view.n_dates == 30


def test_t1_required_family_with_zero_controls_refuses_after_the_clock_starts(tmp_path):
    """Same store, clock STARTED: the cohort is now visible (30 dates) and the
    verdict is coverage 0.0 — `accruing_with_missing_control`, not a bench pass.

    MUTATION CONTROL: same as above (restore the bench fallback for required
    families) — this test then fails on `eligible is False`.
    """
    claims, grades = _cohort(REQ_A, 30, controlled=0)
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)

    assert r.evidence_basis == q.EVIDENCE_BASIS_MATCHED_CONTROL
    assert r.eligible is False
    assert r.n_cohort_dates == 30, "the issued cohort never leaves the denominator"
    assert r.n_controlled_dates == 0
    assert r.control_coverage == 0.0
    assert r.n_dates == 0, "the headline N of a matched verdict is the CONTROLLED count"
    assert r.reason.startswith("accruing_with_missing_control")
    assert r.control_clock_start == CLOCK_T0


# =========================================================================== #
# T2 — direction=-1 IS SCORED CORRECTLY VS THE CONTROL (#2, P0c-1's rule)
# =========================================================================== #
def test_t2_mirrored_bullish_and_bearish_cohorts_score_identically(tmp_path):
    """Two REQUIRED families holding mirrored calls — stock_desk bullish
    (subject beats control by 0.05) and demand_chain bearish (subject TRAILS
    control by 0.05) — are both 30/30 CORRECT and must produce the identical
    matched-control verdict. A correct bearish call is a HIT.

    MUTATION CONTROL: drop `direction *` from the matched arithmetic in
    `matched_control_check` (`if (subj - ctrl) > 0`). The bearish family then
    scores 0/30, its Wilson bound collapses, and this test fails on the equality
    of the two bounds (and on `r_bear.eligible`).
    """
    bull_c, bull_g = _cohort(REQ_A, 30, controlled=30, direction=1, correct=True)
    bear_c, bear_g = _cohort(REQ_B, 30, controlled=30, direction=-1, correct=True)
    _write_store(tmp_path, bull_c + bear_c, bull_g + bear_g)
    _start_clock(tmp_path, REQ_A)
    _start_clock(tmp_path, REQ_B)

    r_bull = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)
    r_bear = q.promotion_check_dispatch(REQ_B, 21, root=tmp_path)

    assert r_bull.n_dates == r_bear.n_dates == 30
    assert r_bull.control_coverage == r_bear.control_coverage == 1.0
    assert r_bull.eligible is True, r_bull.reason
    assert r_bear.eligible is True, r_bear.reason
    assert r_bull.wilson_ci_low == pytest.approx(r_bear.wilson_ci_low)


def test_t2_an_exact_zero_control_excess_is_not_a_hit(tmp_path):
    """Strict `>`: a subject that exactly matched its control did not beat it."""
    claims, grades = [], []
    for asof in _dates(30):
        c = _claim(family=REQ_A, asof=asof)
        claims.append(c)
        grades.append(_grade_row(c, subject_ret=0.02, control_ret=0.02,
                                 bench_ret=0.0, hit=True))
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)
    assert r.eligible is False
    assert r.wilson_ci_low is not None and r.wilson_ci_low < 0.5


# =========================================================================== #
# T3 — direction=0 CANNOT MANUFACTURE A CONTROL HIT (#3, C3.2(b))
# =========================================================================== #
def test_t3_salience_rows_enter_neither_numerator_denominator_nor_n_dates(tmp_path):
    """A required family's store also holding 20 salience (direction=0) rows on
    20 OTHER dates, every one of them control-carrying and control-beating: they
    contribute to NEITHER the numerator, NOR the denominator, NOR
    `n_controlled_dates`, NOR `n_cohort_dates`.

    MUTATION CONTROL: drop the `direction not in (1, -1)` cohort clause (C3.2(b))
    in `matched_control_check` — the "count them in" mutation. The salience dates
    then join the cohort, `n_cohort_dates` becomes 50 and `n_controlled_dates`
    50, and this test fails on both counts.

    NOTE ON WHERE THE EXCLUSION LIVES: the in-loop `if not direction: continue`
    (P0c-1's own guard, kept verbatim) is UNREACHABLE for these rows because the
    cohort clause already refuses them, so mutating the in-loop guard alone
    changes nothing. The cohort clause is therefore the guarded logic and the
    mutation named above is the one that bites.
    """
    claims, grades = _cohort(REQ_A, 30, controlled=30)
    for asof in _dates(20, "2025-06-01"):
        sal = _claim(family=REQ_A, asof=asof, direction=0,
                     claim_id=f"salience|{asof}")
        claims.append(sal)
        grades.append(_grade_row(sal, subject_ret=0.09, control_ret=0.01,
                                 bench_ret=0.0, hit=None))
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)

    assert r.n_cohort_dates == 30
    assert r.n_controlled_dates == 30
    assert r.n_dates == 30
    assert r.control_coverage == 1.0

    clean_c, clean_g = _cohort(REQ_A, 30, controlled=30)
    clean_root = tmp_path / "clean"
    _write_store(clean_root, clean_c, clean_g)
    _start_clock(clean_root, REQ_A)
    clean = q.promotion_check_dispatch(REQ_A, 21, root=clean_root)
    assert r.wilson_ci_low == pytest.approx(clean.wilson_ci_low), (
        "salience rows must not move the matched-control hit rate at all")


# =========================================================================== #
# T4 — POST-REGISTRATION CONTROL SELECTION IS IMPOSSIBLE (#4, C2.1)
# =========================================================================== #
def test_t4_reregistering_with_a_different_control_leaves_the_row_frozen(tmp_path):
    """`claim_id` excludes the control and dedupe is keep-FIRST, so a
    re-registration naming XLV returns the ORIGINAL XLK row and appends nothing.
    Choosing the control after seeing the outcome is structurally impossible.

    MUTATION CONTROL: make `register`'s dedupe keep-LAST (append the new row
    instead of returning the existing one). The store then holds two rows and the
    later control wins — this test fails on both `len(rows) == 1` and the control.
    """
    base = dict(desk=REQ_A, asof="2025-03-03", scope_type="entity",
                scope_key="AAPL", direction=1, horizon_d=21,
                horizon_unit="trading_days", timestamp_quality="CRAWL_BOUNDED",
                claim_family=REQ_A)
    first = q.register(q.make_claim(**base, control="XLK"), root=tmp_path)
    second = q.register(q.make_claim(**base, control="XLV"), root=tmp_path)

    rows = q.load_claims(tmp_path)
    assert len(rows) == 1, "a re-registration must never append a second row"
    assert rows[0]["control"] == "XLK"
    assert second["claim_id"] == first["claim_id"]
    assert second["control"] == "XLK"


def test_t4_grading_never_writes_back_into_claims(prices, tmp_path):
    """Grade rows are derived, never authoritative: `grade_claim` leaves
    claims.jsonl byte-identical. A grader that could touch the control leg would
    reopen post-hoc control selection through the back door."""
    stored = q.register(q.make_claim(
        desk=REQ_A, asof="2025-03-03", scope_type="entity", scope_key="AAPL",
        direction=1, horizon_d=21, horizon_unit="trading_days",
        timestamp_quality="CRAWL_BOUNDED", claim_family=REQ_A, control="XLK"),
        root=tmp_path)
    path = tmp_path / "data" / "qledger" / "claims.jsonl"
    before = path.read_bytes()

    rows = q.grade_claim(stored, root=tmp_path, today=date(2025, 6, 1))

    assert rows, "the fixture must actually grade, else this asserts nothing"
    assert all(r["control_ret"] is not None for r in rows)
    assert path.read_bytes() == before


# =========================================================================== #
# T5 — HISTORICAL BACKFILL CANNOT MINT AUTHORITY (#5, C3.2(e))
# =========================================================================== #
def test_t5_retrospectively_registered_controlled_rows_never_join_the_cohort(tmp_path):
    """30 perfectly controlled, perfectly correct claims whose registration
    stamps land AFTER their windows had already begun. They are excluded from
    the cohort, from the coverage accounting and from N — forever, because the
    predicate reads the claim's OWN registration stamp, not "today".

    MUTATION CONTROL: drop the `window.fill_date > ref_date` clause from
    `_cohort_prospective` (return True once the window resolves). The 30
    backfilled dates then join the cohort at coverage 1.0 and clear the gate —
    this test fails on `n_cohort_dates == 0` and on `eligible is False`.
    """
    claims, grades = [], []
    for asof in _dates(30, "2025-02-03"):
        late = (date.fromisoformat(asof) + timedelta(days=90)).isoformat()
        c = _claim(family=REQ_A, asof=asof, control="XLK",
                   timestamp=f"{late}T13:00:00+00:00")
        claims.append(c)
        grades.append(_grade_row(c, subject_ret=0.06, control_ret=0.01,
                                 bench_ret=0.0, hit=True))
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)

    assert r.eligible is False
    assert r.n_cohort_dates == 0
    assert r.n_controlled_dates == 0
    assert r.n_dates == 0
    assert r.control_coverage is None
    assert "EMPTY" in r.reason


def test_t5_registering_an_old_asof_claim_starts_no_clock(tmp_path):
    """The registrar half of the same rule: importing an old-asof controlled
    claim for a required family writes NO clock. A clock that a backfill could
    start would date the evidence to a window that had already resolved.

    MUTATION CONTROL: the same `_cohort_prospective` mutation — the import then
    starts the clock and this test fails on the clock file's absence.
    """
    q.register_batch([q.make_claim(
        desk=REQ_A, asof="2025-03-03", scope_type="entity", scope_key="AAPL",
        direction=1, horizon_d=21, horizon_unit="trading_days",
        timestamp_quality="CRAWL_BOUNDED", claim_family=REQ_A, control="XLK")],
        root=tmp_path)

    assert q.read_control_clock_start(REQ_A, tmp_path) is None
    assert not _clock_dir(tmp_path).exists()


# =========================================================================== #
# T6 — MISSING-CONTROL ROWS CANNOT VANISH FROM THE ACCOUNTING (#6, C4.1)
# =========================================================================== #
def test_t6_coverage_denominator_is_the_issued_cohort_not_the_controlled_subset(tmp_path):
    """37 controlled of a 100-date cohort reports coverage 0.37 and refuses,
    naming BOTH counts. This is census D0-3's denominator failure, pinned: the
    old path measured the rate on 37 and stated it at n=100.

    MUTATION CONTROL: compute coverage over the controlled subset
    (`n_controlled_dates / n_controlled_dates`, i.e. 37/37 = 1.0). The gate then
    passes the coverage clause and this test fails on `control_coverage == 0.37`.
    """
    claims, grades = _cohort(REQ_A, 100, controlled=37)
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)

    assert r.n_cohort_dates == 100
    assert r.n_controlled_dates == 37
    assert r.n_cohort_rows == 100
    assert r.n_controlled_rows == 37
    assert r.control_coverage == pytest.approx(0.37)
    assert r.eligible is False
    assert "37" in r.reason and "100" in r.reason
    assert r.reason.startswith("accruing_with_missing_control")
    # And the interval, when one exists, is projected onto the CONTROLLED count.
    assert r.n_dates == 37


def test_t6_wilson_interval_is_projected_onto_the_controlled_count_only(tmp_path):
    """C4.3 directly: the same 100% controlled hit rate reports a NARROWER
    interval at 100 controlled dates than at 30 — so a rate measured on 30 can
    never borrow a 100-row N."""
    small = tmp_path / "small"
    big = tmp_path / "big"
    for root, n in ((small, 30), (big, 100)):
        c, g = _cohort(REQ_A, n, controlled=n)
        _write_store(root, c, g)
        _start_clock(root, REQ_A)
    r_small = q.promotion_check_dispatch(REQ_A, 21, root=small)
    r_big = q.promotion_check_dispatch(REQ_A, 21, root=big)
    assert r_small.n_dates == 30 and r_big.n_dates == 100
    assert r_big.wilson_ci_low > r_small.wilson_ci_low


# =========================================================================== #
# T7 — RE-CLASSIFICATION IS GOVERNED (#7, C1.2/C1.3/C1.4)
# =========================================================================== #
def test_t7_family_control_policy_table_is_pinned_verbatim(tmp_path):
    """THE GOVERNED TABLE, pinned by exact content (census §4).

    Changing any line below is a GOVERNED ACT: the table, this test, and cited
    evidence move in ONE change. A silent policy move is how a family would
    acquire — or quietly lose — matched-control authority.

    MUTATION CONTROL: move any family between the three sets in
    `FAMILY_CONTROL_POLICY` — this test fails on the changed set.
    """
    required = {f for f, p in q.FAMILY_CONTROL_POLICY.items()
                if p == q.CONTROL_POLICY_REQUIRED}
    benchmark = {f for f, p in q.FAMILY_CONTROL_POLICY.items()
                 if p == q.CONTROL_POLICY_BENCHMARK_ONLY}
    not_applicable = {f for f, p in q.FAMILY_CONTROL_POLICY.items()
                      if p == q.CONTROL_POLICY_NOT_APPLICABLE}

    assert required == {"stock_desk", "demand_chain"}
    assert benchmark == {
        "intel_hub", "altdata", "altdata_event", "altdata_flow", "altdata_mid",
        "altdata_slow", "radar", "policy", "whitehouse", "thematic_desk",
        "basket_turn.v1", "flip_confirmation.v1"}
    assert not_applicable == {
        "china_news", "cn_importance_v0", "cn_importance_v0_pit",
        "us_importance_v0", "us_importance_v0_pit", "cn_special_sits",
        "narrative_source_call", "narrative_flare_state", "communique_diff",
        "missing_tape", "extraction_8k", "placebo"}
    assert (required | benchmark | not_applicable) == set(q.FAMILY_CONTROL_POLICY)
    assert q.CONTROL_COVERAGE_MIN == 0.95

    assert q.family_control_policy("stock_desk") == (q.CONTROL_POLICY_REQUIRED, True)
    assert q.family_control_policy("radar") == (q.CONTROL_POLICY_BENCHMARK_ONLY, True)
    assert q.family_control_policy(UNCLASSIFIED_FAM) == (
        q.CONTROL_POLICY_BENCHMARK_ONLY, False)
    assert q.family_control_policy(None) == (q.CONTROL_POLICY_BENCHMARK_ONLY, False)


def test_t7_a_benchmark_only_family_with_perfect_control_coverage_stays_benchmark(tmp_path):
    """100% of a `benchmark_only` family's rows carry valid, control-beating
    legs. It is STILL evaluated benchmark-relative, and its verdict is STILL
    labelled `benchmark`. Policy is not inferred from data (C1.4).

    MUTATION CONTROL: derive the policy from row contents in
    `promotion_check_dispatch` (e.g. treat a family whose rows carry controls as
    required). radar then routes to `matched_control_check`, reports
    `evidence_basis="matched_control"` (and, with no clock, "has not begun") —
    this test fails on the basis label.
    """
    claims, grades = _cohort(BENCH_FAM, 30, controlled=30)
    _write_store(tmp_path, claims, grades)

    r = q.promotion_check_dispatch(BENCH_FAM, 21, root=tmp_path)

    assert r.evidence_basis == q.EVIDENCE_BASIS_BENCHMARK
    assert r.evidence_basis != q.EVIDENCE_BASIS_MATCHED_CONTROL
    assert r.unclassified is False
    assert r.control_coverage is None, (
        "coverage is a matched-control concept; a bench verdict must not report one")
    assert r.n_dates == 30
    assert q.read_control_clock_start(BENCH_FAM, tmp_path) is None


# =========================================================================== #
# T8 — THE GATE CANNOT PASS UNDER A COVERAGE VIOLATION (#8, C4.2)
# =========================================================================== #
def test_t8_all_else_green_at_coverage_0_94_refuses(tmp_path):
    """47 controlled dates of 50 — every controlled call correct, N far above
    the 25-date floor, CI at the ceiling. Coverage 0.94 < 0.95 refuses.

    MUTATION CONTROL: delete the `coverage < CONTROL_COVERAGE_MIN` clause from
    `matched_control_check`'s refusal ladder. The verdict then passes on the
    remaining criteria and this test fails on `eligible is False`.
    """
    claims, grades = _cohort(REQ_A, 50, controlled=47)
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)

    assert r.control_coverage == pytest.approx(0.94)
    assert r.n_controlled_dates == 47 >= q.PROMOTION_MIN_DATES
    assert r.wilson_ci_low is not None and r.wilson_ci_low > q.PROMOTION_MIN_CI_LOW
    assert r.eligible is False, r.reason
    assert r.reason.startswith("accruing_with_missing_control")


def test_t8_full_coverage_above_the_date_floor_passes(tmp_path):
    """The floor is a bar, not a wall: coverage 1.0, 30 controlled dates, a hit
    rate whose whole interval clears the coin — the gate PASSES."""
    claims, grades = _cohort(REQ_A, 30, controlled=30)
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)

    assert r.control_coverage == 1.0
    assert r.n_controlled_dates == 30
    assert r.wilson_ci_low > q.PROMOTION_MIN_CI_LOW
    assert r.eligible is True, r.reason
    assert r.current_state == q.STATE_GRADED
    assert r.evidence_basis == q.EVIDENCE_BASIS_MATCHED_CONTROL


def test_t8_matched_gate_refuses_below_the_date_floor_with_honest_counts(tmp_path):
    """Full coverage, perfect calls, but only 10 controlled dates: refused on
    the 25-date floor, and the refusal states the honest controlled count."""
    claims, grades = _cohort(REQ_A, 10, controlled=10)
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)

    assert r.eligible is False
    assert r.control_coverage == 1.0
    assert r.n_controlled_dates == 10 and r.n_cohort_dates == 10
    assert r.current_state == q.STATE_ACCRUING
    assert "n_controlled_dates=10" in r.reason
    assert "15 more" in r.reason


def test_t8_a_coin_flip_matched_hit_rate_demotes(tmp_path):
    """Coverage and N clear their bars but the control-relative interval brackets
    0.5 — ineligible WITH `demote`, mirroring the bench gate's semantics."""
    good_c, good_g = _cohort(REQ_A, 15, controlled=15, correct=True)
    bad_c, bad_g = _cohort(REQ_A, 15, controlled=15, correct=False,
                           start="2025-06-01")
    _write_store(tmp_path, good_c + bad_c, good_g + bad_g)
    _start_clock(tmp_path, REQ_A)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)

    assert r.n_controlled_dates == 30 and r.control_coverage == 1.0
    assert r.wilson_ci_low <= q.PROMOTION_MIN_CI_LOW
    assert r.eligible is False and r.demote is True
    assert r.pinned_reason


# =========================================================================== #
# T9 — THE CLOCK IS WRITE-ONCE AND IS NEVER PRE-CREATED (C3.1/C3.4)
# =========================================================================== #
def test_t9_control_clock_is_write_once(tmp_path):
    """A second record returns the FIRST unchanged and ignores every argument. A
    clock that can be moved can be moved backwards."""
    first = q.record_control_clock_start(
        REQ_A, horizon_d=21, horizon_unit="trading_days", control="XLK",
        git_sha="deadbeef", root=tmp_path, now="2026-01-05T00:00:00+00:00")
    second = q.record_control_clock_start(
        REQ_A, horizon_d=63, horizon_unit="calendar_days", control="XLV",
        git_sha="cafef00d", root=tmp_path, now="2020-01-01T00:00:00+00:00")

    assert second == first
    assert second["first_controlled_prospective_registration_utc"] == \
        "2026-01-05T00:00:00+00:00"
    assert second["declared_horizon_d"] == 21
    assert second["horizon_unit"] == "trading_days"
    assert second["control"] == "XLK"
    assert second["git_sha"] == "deadbeef"
    assert second["claim_family"] == REQ_A
    assert q.read_control_clock_start(REQ_A, tmp_path) == first


def test_t9_the_gate_never_creates_a_clock(tmp_path):
    """Reading the gate is not an act of evidence. A required family with no
    clock reports "has not begun" and leaves the clock directory ABSENT — a
    timestamp minted by a read is retrospective stamping by another name."""
    claims, grades = _cohort(REQ_A, 30, controlled=30)
    _write_store(tmp_path, claims, grades)

    r = q.matched_control_check(REQ_A, 21, root=tmp_path)

    assert r.eligible is False
    assert "has not begun accruing" in r.reason
    assert r.control_clock_start is None
    assert not _clock_dir(tmp_path).exists(), (
        "the gate pre-created a clock directory — nothing but the registrar may")
    assert q.read_control_clock_start(REQ_A, tmp_path) is None


def test_t9_no_clock_file_is_ever_committed(tmp_path):
    """C3.4/C9: a clock file is written by the REGISTRAR at a real registration,
    so a COMMITTED one is a hand-written timestamp — the retrospective stamping
    this contract exists to forbid.

    Asserted over git's index, deliberately NOT over the filesystem: a nightly
    run in a live checkout may legitimately write an untracked clock file, and a
    test that a real registration turns red is a test that punishes the very
    event the contract is waiting for.
    """
    import shutil
    import subprocess
    repo = Path(__file__).resolve().parents[1]
    if shutil.which("git") is None or not (repo / ".git").exists():
        pytest.skip("no git checkout to interrogate")
    tracked = subprocess.run(
        ["git", "ls-files", "--", "data/qledger/control_evidence_clock_start"],
        cwd=repo, capture_output=True, text=True, timeout=60).stdout.split()
    assert tracked == [], f"clock files must never be committed: {tracked}"


# =========================================================================== #
# T10 — THE REGISTRAR HOOK (C3.1)
# =========================================================================== #
def _forward_claim(family: str, *, control: str | None, subject: str = "AAPL",
                   asof: str | None = None) -> dict:
    """A claim registered TODAY for today's asof — prospective by construction
    (its window fills on the next session, strictly after today)."""
    return q.make_claim(
        desk=family, asof=asof or date.today().isoformat(), scope_type="entity",
        scope_key=subject, direction=1, horizon_d=21,
        horizon_unit="trading_days", timestamp_quality="CRAWL_BOUNDED",
        claim_family=family, control=control)


def test_t10_registrar_starts_the_clock_once_on_the_first_controlled_claim(tmp_path):
    """`register_batch` of a prospective, controlled, required-family claim
    writes the clock EXACTLY ONCE, stamped with that claim's own control and
    declared horizon. A later registration with a different control does not
    move it.

    MUTATION CONTROL: see the sibling test below (removing the
    `policy == CONTROL_POLICY_REQUIRED` guard) — that mutation is caught there.
    A mutation that removes the hook call from `register_batch` fails THIS test
    on the clock's absence.
    """
    q.register_batch([_forward_claim(REQ_A, control="XLK")], root=tmp_path)

    rec = q.read_control_clock_start(REQ_A, tmp_path)
    assert rec is not None
    assert rec["claim_family"] == REQ_A
    assert rec["control"] == "XLK"
    assert rec["declared_horizon_d"] == 21
    assert rec["horizon_unit"] == "trading_days"
    assert rec["first_controlled_prospective_registration_utc"]
    assert len(list(_clock_dir(tmp_path).glob("*.json"))) == 1

    q.register_batch([_forward_claim(REQ_A, control="XLV", subject="MSFT")],
                     root=tmp_path)
    assert q.read_control_clock_start(REQ_A, tmp_path) == rec


def test_t10_registrar_starts_no_clock_for_benchmark_only_or_uncontrolled(tmp_path):
    """A `benchmark_only` family's control-carrying registration starts NOTHING,
    and neither does an UNCONTROLLED required-family registration. Whether a
    family accrues matched-control evidence is policy, not data (C1.4).

    MUTATION CONTROL: remove the `policy == CONTROL_POLICY_REQUIRED` guard from
    `_start_control_clocks_for`. radar then acquires a clock on registration and
    this test fails on `read_control_clock_start(BENCH_FAM) is None`.
    """
    q.register_batch([
        _forward_claim(BENCH_FAM, control="XLK"),      # benchmark_only + control
        _forward_claim(REQ_A, control=None),           # required, no control
        _forward_claim(REQ_B, control="AAPL"),         # required, control == subject
    ], root=tmp_path)

    assert q.read_control_clock_start(BENCH_FAM, tmp_path) is None
    assert q.read_control_clock_start(REQ_A, tmp_path) is None
    assert q.read_control_clock_start(REQ_B, tmp_path) is None
    assert not _clock_dir(tmp_path).exists()


def test_t10_registrar_hook_never_raises_into_registration(tmp_path, monkeypatch):
    """A clock-write failure must never take a ledger write down with it."""
    def _boom(*_a, **_k):
        raise RuntimeError("clock store exploded")
    monkeypatch.setattr(q, "record_control_clock_start", _boom)

    out = q.register_batch([_forward_claim(REQ_A, control="XLK")], root=tmp_path)

    assert len(out) == 1 and out[0]["status"] == "open"
    assert len(q.load_claims(tmp_path)) == 1


def test_t10_a_deduped_batch_starts_nothing(tmp_path):
    """The hook runs over NEWLY APPENDED rows only. Re-running a producer cannot
    re-stamp, and a batch that dedupes entirely appends nothing to reason over."""
    claim = _forward_claim(REQ_A, control="XLK")
    q.register_batch([claim], root=tmp_path)
    rec = q.read_control_clock_start(REQ_A, tmp_path)
    (tmp_path / "data" / "qledger" / "control_evidence_clock_start" /
     f"{REQ_A}.json").unlink()

    q.register_batch([claim], root=tmp_path)          # pure dedupe, nothing new

    assert rec is not None
    assert q.read_control_clock_start(REQ_A, tmp_path) is None
    assert len(q.load_claims(tmp_path)) == 1


# =========================================================================== #
# T11 — ALIAS NORMALISATION + CONTROL VALIDITY (D0-1/D0-2, C2.2/C2.3)
# =========================================================================== #
def test_t11_sector_alias_normalisation_and_refusals():
    """Census D0-2: the universe file speaks two sector vocabularies, and a naive
    join nulls on roughly half of it. Both vocabularies map; an unknown value and
    an ETF TICKER refuse — D0-1 (a producer handing an ETF ticker to a GICS-name
    map and getting None forever) stays impossible in both directions."""
    assert q.sector_gics_etf("Technology") == "XLK"
    assert q.sector_gics_etf("Information Technology") == "XLK"
    assert q.sector_gics_etf("Healthcare") == "XLV"
    assert q.sector_gics_etf("Health Care") == "XLV"
    assert q.sector_gics_etf("Consumer Cyclical") == "XLY"
    assert q.sector_gics_etf("Consumer Defensive") == "XLP"
    assert q.sector_gics_etf("Financial") == "XLF"
    assert q.sector_gics_etf("Basic Materials") == "XLB"

    assert q.sector_gics_etf(None) is None
    assert q.sector_gics_etf("") is None
    assert q.sector_gics_etf("QQQ") is None, (
        "an ETF ticker is not a sector name — census D0-1's defect class")
    assert q.sector_gics_etf("Nonexistent Sector") is None

    # `control_for_sector` is deliberately untouched (display-tier callers).
    assert q.control_for_sector("Information Technology") == "XLK"
    assert q.control_for_sector("Technology") is None


def test_t11_control_leg_validity_rejects_self_and_bench(tmp_path):
    """C2.2: a control equal to the subject nets the claim against itself; a
    control equal to the bench relabels the baseline. Both are missing-control."""
    ok = _claim(family=REQ_A, asof="2025-03-03", control="XLK",
                subject="AAPL", bench="SPY")
    assert q.control_leg_is_valid(ok) is True
    assert q.control_leg_is_valid(dict(ok, control="AAPL")) is False
    assert q.control_leg_is_valid(dict(ok, control="SPY")) is False
    assert q.control_leg_is_valid(dict(ok, control="aapl")) is False
    assert q.control_leg_is_valid(dict(ok, control=None)) is False
    assert q.control_leg_is_valid(dict(ok, control="  ")) is False


def test_t11_self_netted_control_rows_count_as_missing_control(tmp_path):
    """The validity rule reaches the ACCOUNTING, not just a predicate: a cohort
    whose rows all name the subject as their own control reports coverage 0 and
    refuses, even though every row carries a non-null `control_ret`."""
    claims, grades = [], []
    for asof in _dates(30):
        c = _claim(family=REQ_A, asof=asof, control="AAPL", subject="AAPL")
        claims.append(c)
        grades.append(_grade_row(c, subject_ret=0.06, control_ret=0.01,
                                 bench_ret=0.0, hit=True))
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)
    assert r.n_cohort_dates == 30
    assert r.n_controlled_dates == 0
    assert r.control_coverage == 0.0
    assert r.eligible is False


def test_t11_sector_of_ticker_reads_the_universe_and_fails_open(tmp_path):
    """`sector_of_ticker` returns the RAW vocabulary value (so a caller can tell
    `sector_absent` from `vocabulary_unmapped`, C2.4) and answers None — rather
    than raising — when the universe file is absent."""
    assert q.sector_of_ticker("AAPL", root=tmp_path) is None      # no file at all

    d = tmp_path / "u" / "data" / "universe"
    d.mkdir(parents=True)
    pd.DataFrame({"ticker": ["AAPL", "JNJ", "F"],
                  "sector": ["Technology", "Health Care", None]}).to_parquet(
        d / "membership.parquet")
    root = tmp_path / "u"

    assert q.sector_of_ticker("AAPL", root=root) == "Technology"
    assert q.sector_gics_etf(q.sector_of_ticker("AAPL", root=root)) == "XLK"
    assert q.sector_gics_etf(q.sector_of_ticker("JNJ", root=root)) == "XLV"
    assert q.sector_of_ticker("F", root=root) is None
    assert q.sector_of_ticker("ZZZZ", root=root) is None
    assert q.sector_of_ticker(None, root=root) is None


# =========================================================================== #
# T12 — DISPATCH LABELLING (C5.2/C5.3, C6.1)
# =========================================================================== #
def test_t12_not_applicable_family_never_becomes_eligible(tmp_path):
    """A `not_applicable` family handed a hand-crafted PASSING bench record
    still returns `evidence_basis="not_applicable"` and `eligible=False`. These
    are salience/descriptive species: there is no directional proposition to
    promote, whatever the numbers say.

    MUTATION CONTROL: drop the `not_applicable` branch from
    `promotion_check_dispatch` (label it `benchmark` and keep `pr.eligible`).
    30/30 bench hits then read as eligible and this test fails.
    """
    claims, grades = _cohort(NA_FAM, 30, controlled=0)
    _write_store(tmp_path, claims, grades)

    r = q.promotion_check_dispatch(NA_FAM, 21, root=tmp_path)

    assert r.evidence_basis == q.EVIDENCE_BASIS_NOT_APPLICABLE
    assert r.eligible is False
    assert r.demote is False
    assert r.reason.startswith("not_applicable family (salience/descriptive)")
    assert "placebo tape" in r.reason
    # the underlying bench record really would have passed
    assert q.promotion_check(NA_FAM, 21, root=tmp_path,
                             control_only=False).eligible is True


def test_t12_unclassified_family_is_benchmark_and_says_so(tmp_path):
    """C1.3: a family absent from the table runs benchmark mechanics, is
    LABELLED `unclassified`, and is structurally ineligible for matched-control
    authority (it can never reach `matched_control_check` at all)."""
    claims, grades = _cohort(UNCLASSIFIED_FAM, 30, controlled=30)
    _write_store(tmp_path, claims, grades)

    r = q.promotion_check_dispatch(UNCLASSIFIED_FAM, 21, root=tmp_path)

    assert r.evidence_basis == q.EVIDENCE_BASIS_BENCHMARK
    assert r.unclassified is True
    assert r.control_coverage is None
    assert q.read_control_clock_start(UNCLASSIFIED_FAM, tmp_path) is None


def test_promotion_result_as_dict_carries_every_p0d_key(tmp_path):
    """The payload is the contract's surface (C5.4): every consumer reading
    track_record.json / the readiness rows must be able to see the basis and the
    coverage accounting beside the numbers."""
    claims, grades = _cohort(REQ_A, 30, controlled=30)
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    d = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path).as_dict()
    for key in ("evidence_basis", "control_coverage", "n_cohort_dates",
                "n_controlled_dates", "n_cohort_rows", "n_controlled_rows",
                "control_clock_start", "unclassified"):
        assert key in d, key
    assert d["evidence_basis"] == q.EVIDENCE_BASIS_MATCHED_CONTROL
    assert d["control_coverage"] == 1.0
    assert d["control_clock_start"] == CLOCK_T0

    # A bench verdict keeps its previous shape and adds only the labels.
    bench = q.promotion_check(BENCH_FAM, 21, root=tmp_path).as_dict()
    assert bench["evidence_basis"] is None and bench["unclassified"] is False
    assert json.dumps(d) and json.dumps(bench)      # both stay JSON-serialisable


def test_a_required_family_straddling_two_clocks_is_promotable_per_basis(tmp_path):
    """P0a's per-market escape hatch inherits the P0d basis. A required family
    accruing on two EXPLICIT clocks refuses to pool (STATE_MIXED_CLOCK) and gets
    one MATCHED-CONTROL verdict per basis beside it — never a bench verdict,
    which is what routing it back through `promotion_check_by_market` would have
    produced. Unreachable on today's corpus and therefore exactly the kind of
    branch that ships dead if nothing exercises it.
    """
    claims, grades = [], []
    for i, asof in enumerate(_dates(30)):
        for unit in ("trading_days", "calendar_days"):
            c = _claim(family=REQ_A, asof=asof, unit=unit,
                       claim_id=f"{unit}|{asof}")
            claims.append(c)
            grades.append(_grade_row(c, subject_ret=0.06, control_ret=0.01,
                                     bench_ret=0.0, hit=True))
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    pooled = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)
    assert pooled.current_state == q.STATE_MIXED_CLOCK
    assert pooled.eligible is False
    assert pooled.evidence_basis == q.EVIDENCE_BASIS_MATCHED_CONTROL
    assert set(pooled.clock_prior_n_dates) == {
        "explicit_unit_v1:trading_days:US", "explicit_unit_v1:calendar_days:US"}

    entry = q.emit_ladder_states(root=tmp_path, families=[REQ_A])[REQ_A]["21"]
    per_basis = entry["by_clock_basis"]
    assert set(per_basis) == set(pooled.clock_prior_n_dates)
    for sub in per_basis.values():
        assert sub["evidence_basis"] == q.EVIDENCE_BASIS_MATCHED_CONTROL
        assert sub["control_coverage"] == 1.0
        assert sub["n_dates"] == 30
        assert sub["eligible"] is True


def test_production_emit_ladder_states_dispatches_by_policy(tmp_path):
    """C5.4 at the production call path: `emit_ladder_states` labels every
    family's verdict with its own evidence basis, and the blanket
    `control_only=True` call is gone."""
    claims, grades = _cohort(BENCH_FAM, 30, controlled=30)
    req_c, req_g = _cohort(REQ_A, 30, controlled=30, start="2025-07-01")
    na_c, na_g = _cohort(NA_FAM, 5, controlled=0, start="2025-09-01")
    _write_store(tmp_path, claims + req_c + na_c, grades + req_g + na_g)

    out = q.emit_ladder_states(root=tmp_path)

    assert out[BENCH_FAM]["21"]["evidence_basis"] == q.EVIDENCE_BASIS_BENCHMARK
    assert out[NA_FAM]["21"]["evidence_basis"] == q.EVIDENCE_BASIS_NOT_APPLICABLE
    assert out[NA_FAM]["21"]["eligible"] is False
    req = out[REQ_A]["21"]
    assert req["evidence_basis"] == q.EVIDENCE_BASIS_MATCHED_CONTROL
    assert req["eligible"] is False and req["control_clock_start"] is None
    assert "has not begun accruing" in req["reason"]
