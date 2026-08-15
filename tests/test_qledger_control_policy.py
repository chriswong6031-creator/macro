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

import itertools
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from engine import qledger as q
from lib.nyse_calendar import sessions_between
from scripts import grade_qledger as grader


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
        "basket_turn.v1", "flip_confirmation.v1",
        # Live Entry Radar W5, prereg §17 (2026-08-15). Registration populates
        # `control` mechanically from the sector map; matched-control AUTHORITY
        # stays a later governed act pending prospective coverage (census §5).
        # C4_MTF_TURN@1 / F1_FUSION are deliberately absent — they never
        # register, so they have no population to classify.
        "entry_radar",
        "entry_radar_G0_GREY_DOT@1",
        "entry_radar_C1_1D_LIVE_WASHOUT@1",
        "entry_radar_C2_1D_TURN@1",
        "entry_radar_C3_1D_4H_RECOVERY@1",
        "entry_radar_C5_BOTTOM_WATCH@1"}
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


# =========================================================================== #
# REVIEW ROUND 1 (2026-08-14) — the defects an adversarial pass found in the
# first cut. Each is a way the accounting could be defeated WITHOUT anyone
# lying: an ordering, a granularity, a ratio, a label.
# =========================================================================== #
def _k_rows_per_date(family: str, n_dates: int, rows_per_date: int,
                     controlled_per_date: int, *, horizon: int = 21,
                     start: str = "2025-02-03") -> tuple[list[dict], list[dict]]:
    """`n_dates` dates × `rows_per_date` claims, `controlled_per_date` of which
    carry a control. The shape a single-name desk actually produces: a book of
    names each day, only some of them control-carrying."""
    names = ["AAPL", "MSFT", "NVDA", "AMD", "INTC",
             "CSCO", "ORCL", "IBM", "TXN", "QCOM"]
    claims, grades = [], []
    for asof in _dates(n_dates, start):
        for j in range(rows_per_date):
            has_ctrl = j < controlled_per_date
            c = _claim(family=family, asof=asof, horizon=horizon,
                       subject=names[j % len(names)],
                       control="XLK" if has_ctrl else None,
                       claim_id=f"{asof}|{j}")
            claims.append(c)
            grades.append(_grade_row(
                c, horizon, subject_ret=0.06,
                control_ret=0.01 if has_ctrl else None,
                bench_ret=0.0, hit=True))
    return claims, grades


def test_fix2_one_controlled_row_per_date_cannot_buy_full_coverage(tmp_path):
    """REVIEW FINDING 2 (BLOCKING). 30 dates × 10 claims with exactly ONE
    controlled row per date: the CALENDAR is fully covered but only 10% of the
    ISSUED COHORT is. The old date-only ratio reported coverage 1.0 and the gate
    PASSED — a matched-control promotion on a 90%-uncontrolled book, which is
    the subset selection C4.2 exists to forbid. `control_coverage` is now
    `min(date_coverage, row_coverage)`.

    MUTATION CONTROL: gate on the date ratio only (`coverage = date_coverage`).
    Coverage returns to 1.0, the gate passes, and this test fails on both
    `control_coverage == 0.1` and `eligible is False`.
    """
    claims, grades = _k_rows_per_date(REQ_A, 30, rows_per_date=10,
                                      controlled_per_date=1)
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)

    assert r.n_cohort_rows == 300 and r.n_controlled_rows == 30
    assert r.n_cohort_dates == 30 and r.n_controlled_dates == 30
    assert r.control_coverage == pytest.approx(0.1)
    assert r.eligible is False, r.reason
    assert r.reason.startswith("accruing_with_missing_control")
    assert "date=1.0" in r.reason and "row=0.1" in r.reason, (
        "both ratios must be disclosed, not just the one that gated")


def test_fix2_full_row_coverage_still_passes(tmp_path):
    """The min is a floor, not a wall: a book that is fully controlled on every
    date still passes, so the stricter ratio cannot make the gate unreachable."""
    claims, grades = _k_rows_per_date(REQ_A, 30, rows_per_date=10,
                                      controlled_per_date=10)
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)
    assert r.control_coverage == 1.0
    assert r.n_controlled_rows == 300
    assert r.eligible is True, r.reason


@pytest.fixture
def monotonic_now(monkeypatch):
    """Strictly-increasing registration stamps on TODAY's UTC date.

    A real batch produces increasing stamps, but two rows CAN collide on the
    same microsecond, which would make the instant-comparison mutation control
    below non-deterministic (equal stamps do not sort below the clock). Pinning
    the sequence removes that flake without weakening what is under test —
    registration still runs end to end through `_prepare_claim`, the append and
    the clock hook."""
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0,
                                              microsecond=0)
    counter = itertools.count()
    monkeypatch.setattr(
        q, "_now_iso",
        lambda: (base + timedelta(microseconds=next(counter))).isoformat())
    return base


def _register_mixed_batch(root: Path, *, one_by_one: bool) -> list[dict]:
    """A required family's real registration: 3 UNCONTROLLED claims first, then
    2 controlled ones, all on today's asof (prospective — they fill next
    session). Uncontrolled-first is the ordering that used to lose them."""
    today = date.today().isoformat()
    batch = [
        q.make_claim(desk=REQ_A, asof=today, scope_type="entity", scope_key=t,
                     direction=1, horizon_d=21, horizon_unit="trading_days",
                     timestamp_quality="CRAWL_BOUNDED", claim_family=REQ_A,
                     control=ctrl)
        for t, ctrl in (("MSFT", None), ("NVDA", None), ("AMD", None),
                        ("AAPL", "XLK"), ("JNJ", "XLV"))
    ]
    if one_by_one:
        return [q.register(c, root=root) for c in batch]
    return q.register_batch(batch, root=root)


@pytest.mark.parametrize("one_by_one", [False, True], ids=["register_batch", "register_loop"])
def test_fix8_a_batch_is_never_excluded_from_the_cohort_it_started(
        tmp_path, monotonic_now, one_by_one):
    """REVIEW FINDING 1 (BLOCKING), end to end. The clock is started BY a claim
    inside the batch, so the batch must be IN the cohort the clock opens.

    THE DEFECT: the clock was stamped `now()` at hook time — microseconds AFTER
    every row it was triggered by — and C3.2(d) compared INSTANTS, so the entire
    triggering batch fell below its own clock. The reviewer's repro registered
    five rows, started the clock, and the gate answered `n_cohort_rows=0`.
    Worse, it was ORDER-DEPENDENT: registering the controlled claims FIRST left
    the uncontrolled ones below the clock, silently deleting them from the
    coverage denominator — adversarial control #6 defeated by a sort order.

    Fixed at both ends: the clock records the TRIGGERING CLAIM'S OWN timestamp,
    and membership compares UTC DATES. Both registration shapes are exercised
    because they stamp differently (one `_prepare_claim` per row either way, but
    `register` runs the hook per row and `register_batch` once per batch).

    MUTATION CONTROL: revert C3.2(d) to the instant comparison
    (`if ts < clock_start_dt: continue`). The three uncontrolled rows drop out,
    `n_cohort_rows` falls to 2 and coverage jumps to 1.0 — this test fails on
    both.
    """
    stored = _register_mixed_batch(tmp_path, one_by_one=one_by_one)
    grades = [_grade_row(s, 21, subject_ret=0.06,
                         control_ret=0.01 if s.get("control") else None,
                         bench_ret=0.0, hit=True) for s in stored]
    gp = tmp_path / "data" / "qledger" / "grades.jsonl"
    gp.write_text("".join(json.dumps(g) + "\n" for g in grades), encoding="utf-8")

    rec = q.read_control_clock_start(REQ_A, tmp_path)
    trigger = next(s for s in stored if s.get("control"))
    assert rec["first_controlled_prospective_registration_utc"] == trigger["timestamp"], (
        "the clock must BE the triggering registration's stamp — the field is "
        "named after it")
    assert rec["control"] == "XLK"

    r = q.matched_control_check(REQ_A, 21, root=tmp_path)

    assert r.n_cohort_rows == 5, (
        f"every row of the triggering batch is a cohort member; got "
        f"{r.n_cohort_rows}. reason={r.reason}")
    assert r.n_controlled_rows == 2
    assert r.control_coverage == pytest.approx(0.4), (
        "the three uncontrolled rows must stay in the denominator")
    assert r.eligible is False


def test_fix8_registration_order_cannot_move_the_denominator(tmp_path, monotonic_now):
    """The same batch registered controlled-FIRST and uncontrolled-FIRST must
    produce the IDENTICAL coverage accounting. Order is not evidence."""
    today = date.today().isoformat()

    def _mk(t, ctrl):
        return q.make_claim(desk=REQ_A, asof=today, scope_type="entity",
                            scope_key=t, direction=1, horizon_d=21,
                            horizon_unit="trading_days",
                            timestamp_quality="CRAWL_BOUNDED",
                            claim_family=REQ_A, control=ctrl)

    unc = [("MSFT", None), ("NVDA", None), ("AMD", None)]
    con = [("AAPL", "XLK"), ("JNJ", "XLV")]
    seen = []
    for label, seq in (("u_first", unc + con), ("c_first", con + unc)):
        root = tmp_path / label
        stored = [q.register(_mk(t, c), root=root) for t, c in seq]
        gp = root / "data" / "qledger" / "grades.jsonl"
        gp.write_text("".join(
            json.dumps(_grade_row(s, 21, subject_ret=0.06,
                                  control_ret=0.01 if s.get("control") else None,
                                  bench_ret=0.0, hit=True)) + "\n"
            for s in stored), encoding="utf-8")
        r = q.matched_control_check(REQ_A, 21, root=root)
        seen.append((r.n_cohort_rows, r.n_controlled_rows, r.control_coverage))

    assert seen[0] == seen[1] == (5, 2, pytest.approx(0.4)), seen


def test_fix1_a_timezone_naive_stamp_is_excluded_and_counted(tmp_path):
    """A registration stamp with no zone cannot be placed against a UTC clock.
    It is EXCLUDED and COUNTED — never a TypeError escaping the gate, and never
    silently admitted."""
    claims, grades = [], []
    for i, asof in enumerate(_dates(4)):
        c = _claim(family=REQ_A, asof=asof,
                   timestamp=(f"{asof}T13:00:00" if i < 2 else f"{asof}T13:00:00+00:00"))
        claims.append(c)
        grades.append(_grade_row(c, subject_ret=0.06, control_ret=0.01,
                                 bench_ret=0.0, hit=True))
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.matched_control_check(REQ_A, 21, root=tmp_path)   # must not raise
    assert r.n_cohort_rows == 2
    assert "UNRESOLVABLE" in r.reason and "2 claim(s)" in r.reason


def test_fix1_retrospective_and_unresolvable_are_counted_separately(tmp_path):
    """(note 13) A retrospectively registered claim and a claim whose window
    will not resolve are different findings with different operator levers."""
    claims, grades = [], []
    for asof in _dates(3):                       # retrospective: registered late
        late = (date.fromisoformat(asof) + timedelta(days=90)).isoformat()
        c = _claim(family=REQ_A, asof=asof, claim_id=f"retro|{asof}",
                   timestamp=f"{late}T13:00:00+00:00")
        claims.append(c)
        grades.append(_grade_row(c, subject_ret=0.06, control_ret=0.01,
                                 bench_ret=0.0, hit=True))
    for asof in _dates(2, "2025-05-01"):         # unresolvable: no market
        c = _claim(family=REQ_A, asof=asof, subject="CN_CENSORSHIP_RISK",
                   bench="CN_CENSORSHIP_RISK", control="ALSO_NOT_A_TICKER",
                   claim_id=f"unres|{asof}")
        claims.append(c)
        grades.append({"claim_id": c["claim_id"], "horizon_d": 21,
                       "graded_at": "2025-12-01T00:00:00+00:00",
                       "subject_ret": 0.01, "bench_ret": 0.0, "control_ret": 0.0,
                       "excess": 0.01, "hit": True, "embargo_applied": False,
                       "horizon_unit": "trading_days",
                       "clock_version": q.CLOCK_V1, "clock_market": q.MARKET_US})
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.matched_control_check(REQ_A, 21, root=tmp_path)
    assert "3 claim(s) excluded as RETROSPECTIVE" in r.reason
    assert "2 claim(s) excluded as UNRESOLVABLE" in r.reason


def test_fix5_matched_control_refuses_the_legacy_clock(tmp_path):
    """REVIEW FINDING 5. A matched-control AUTHORITY verdict may never be
    computed on the legacy calendar approximation. Unreachable in production
    (a cohort member declares an explicit unit, so its rows are stamped) — which
    is exactly why it is asserted rather than assumed."""
    claims, grades = [], []
    for asof in _dates(30):
        c = _claim(family=REQ_A, asof=asof)
        claims.append(c)
        row = _grade_row(c, subject_ret=0.06, control_ret=0.01, bench_ret=0.0,
                         hit=True)
        for stamp in ("horizon_unit", "clock_version", "clock_exit_date",
                      "clock_coverage_date", "clock_market"):
            row.pop(stamp, None)                 # a LEGACY-basis row
        grades.append(row)
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.matched_control_check(REQ_A, 21, root=tmp_path)

    assert r.eligible is False
    assert r.clock_basis == q.CLOCK_LEGACY
    assert r.n_dates == 0
    assert "legacy calendar approximation" in r.reason


def test_fix1_a_corrupt_clock_record_refuses_loudly(tmp_path):
    """(note 11) An unreadable clock used to fall through to an empty-string
    comparison that admitted nobody — a corrupt artifact reading as "no evidence
    yet". It now refuses by name, so the operator is told which file to look at."""
    claims, grades = _cohort(REQ_A, 30, controlled=30)
    _write_store(tmp_path, claims, grades)
    d = _clock_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{REQ_A}.json").write_text(json.dumps({
        "claim_family": REQ_A,
        "first_controlled_prospective_registration_utc": "not-a-timestamp",
    }), encoding="utf-8")

    r = q.matched_control_check(REQ_A, 21, root=tmp_path)

    assert r.eligible is False
    assert "CORRUPT" in r.reason
    assert "control_evidence_clock_start" in r.reason
    assert r.evidence_basis == q.EVIDENCE_BASIS_MATCHED_CONTROL


def test_fix6_ladder_states_carries_the_required_families_from_day_one(tmp_path):
    """REVIEW FINDING 6. Both required families hold zero rows today, so a
    claims-derived enumeration omits them and `ladder_states` says nothing at
    all about the two families this contract is about. "Has not begun accruing"
    is a state a reader must be able to SEE."""
    claims, grades = _cohort(BENCH_FAM, 5, controlled=0)
    _write_store(tmp_path, claims, grades)

    out = q.emit_ladder_states(root=tmp_path)

    for fam in ("stock_desk", "demand_chain"):
        assert fam in out, f"{fam} missing from ladder_states"
        entry = out[fam]["21"]
        assert entry["evidence_basis"] == q.EVIDENCE_BASIS_MATCHED_CONTROL
        assert entry["eligible"] is False
        assert entry["control_clock_start"] is None
        assert "has not begun accruing" in entry["reason"]


def _na_coinflip_store(root: Path, n: int = 30) -> None:
    """A not_applicable family whose BENCH record clears the date floor at a
    coin-flip hit rate — i.e. one the bench gate would answer with demote=True
    and a pinned_reason."""
    claims, grades = [], []
    for i, asof in enumerate(_dates(n)):
        c = _claim(family=NA_FAM, asof=asof, claim_id=f"{NA_FAM}|{asof}")
        claims.append(c)
        hit = (i % 2 == 0)
        grades.append(_grade_row(c, subject_ret=0.06 if hit else -0.06,
                                 control_ret=None, bench_ret=0.0, hit=hit))
    _write_store(root, claims, grades)


def test_small_i_not_applicable_verdict_carries_no_demotion_instruction(tmp_path):
    """(note i) Forcing `eligible=False` while leaving the bench arm's
    "Auto-demote one rung" prose on `pinned_reason` published a demotion
    instruction for a family that has no rung to be demoted from."""
    _na_coinflip_store(tmp_path)
    bench = q.promotion_check(NA_FAM, 21, root=tmp_path, control_only=False)
    assert bench.demote is True and bench.pinned_reason, (
        "fixture must actually produce a demote verdict, else this asserts nothing")

    r = q.promotion_check_dispatch(NA_FAM, 21, root=tmp_path)
    assert r.evidence_basis == q.EVIDENCE_BASIS_NOT_APPLICABLE
    assert r.eligible is False and r.demote is False
    assert r.pinned_reason == ""
    assert r.as_dict()["pinned_reason"] == ""


def test_small_ii_a_not_applicable_family_is_never_approaching(tmp_path):
    """(note 14) A structurally unpromotable family cannot be "approaching" a
    gate it will never take — least of all in the payload the operator alert
    reads."""
    _na_coinflip_store(tmp_path)
    row = grader.compute_promotion_readiness(tmp_path, families=[NA_FAM])[NA_FAM]["21"]
    assert row["n_dates"] >= 20 and row["ready"] is False
    assert row["evidence_basis"] == q.EVIDENCE_BASIS_NOT_APPLICABLE
    assert row["approaching"] is False


def test_fix3_matched_verdict_never_publishes_bench_stats_unlabelled(tmp_path):
    """REVIEW FINDING 3. `_aggregate` measures the WHOLE family BENCH-relative:
    pre-clock rows, uncontrolled rows, everything. On a matched-control verdict
    those numbers used to sit in `hit_rate`/`excess_mean` beside `n_dates`,
    `wilson_ci_low` and `control_coverage` computed over the CONTROLLED COHORT
    ONLY — one row, two populations, no label (C6.1). They are still published,
    under `benchmark_baseline_*` names (C5.1's labelled baseline).

    MUTATION CONTROL: restore `"hit_rate": fam_stats.get("hit_rate")` on the
    matched branch — this test fails on `hit_rate is None`.
    """
    claims, grades = [], []
    for asof in _dates(40, "2025-02-03"):        # 40 PRE-CLOCK bench misses
        c = _claim(family=REQ_A, asof=asof, control=None, claim_id=f"pre|{asof}")
        claims.append(c)
        grades.append(_grade_row(c, subject_ret=-0.05, control_ret=None,
                                 bench_ret=0.0, hit=False))
    for asof in _dates(30, "2025-07-01"):        # 30 POST-CLOCK cohort hits
        c = _claim(family=REQ_A, asof=asof, control="XLK", claim_id=f"post|{asof}")
        claims.append(c)
        grades.append(_grade_row(c, subject_ret=0.06, control_ret=0.01,
                                 bench_ret=0.0, hit=True))
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A, when="2025-06-01T00:00:00+00:00")

    row = grader.compute_promotion_readiness(tmp_path, families=[REQ_A])[REQ_A]["21"]

    assert row["evidence_basis"] == q.EVIDENCE_BASIS_MATCHED_CONTROL
    assert row["n_dates"] == 30 and row["control_coverage"] == 1.0
    assert row["hit_rate"] is None, (
        "a whole-family BENCH hit rate may not ride in the headline slot of a "
        "matched-control verdict")
    assert row["excess_mean"] is None
    assert row["mean_abs_excess"] is None
    assert row["benchmark_baseline_hit_rate"] == pytest.approx(30 / 70, abs=1e-4)
    assert row["benchmark_baseline_excess_mean"] is not None
    assert row["benchmark_baseline_excess_basis"]


def test_fix3_a_benchmark_verdict_keeps_its_headline_stats(tmp_path):
    """The relabelling is scoped to matched-control verdicts: a benchmark family
    still reports its bench numbers where every existing consumer reads them."""
    claims, grades = _cohort(BENCH_FAM, 30, controlled=0)
    _write_store(tmp_path, claims, grades)

    row = grader.compute_promotion_readiness(tmp_path, families=[BENCH_FAM])[BENCH_FAM]["21"]
    assert row["evidence_basis"] == q.EVIDENCE_BASIS_BENCHMARK
    assert row["hit_rate"] is not None
    assert row["benchmark_baseline_hit_rate"] is None


def test_fix7_readiness_and_ladder_states_agree_on_a_bi_market_required_family(tmp_path):
    """REVIEW FINDING 7. `emit_ladder_states` minted per-basis matched verdicts
    for a bi-market required family while the READINESS payload — the one the
    admin tab and the first-cross alert read — emitted only the refused pooled
    one. Fixing it in the artifact and not in the payload that gates the alert
    is fixing it in the place nobody reads."""
    claims, grades = [], []
    for asof in _dates(30):
        for unit in ("trading_days", "calendar_days"):
            c = _claim(family=REQ_A, asof=asof, unit=unit,
                       claim_id=f"{unit}|{asof}")
            claims.append(c)
            grades.append(_grade_row(c, subject_ret=0.06, control_ret=0.01,
                                     bench_ret=0.0, hit=True))
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    ladder = q.emit_ladder_states(root=tmp_path, families=[REQ_A])[REQ_A]["21"]
    ready = grader.compute_promotion_readiness(tmp_path, families=[REQ_A])[REQ_A]["21"]

    assert set(ready["by_clock_basis"]) == set(ladder["by_clock_basis"])
    for basis, sub in ready["by_clock_basis"].items():
        assert sub["evidence_basis"] == q.EVIDENCE_BASIS_MATCHED_CONTROL
        assert sub["control_coverage"] == 1.0
        assert sub["ready"] is True
        assert sub["n_dates"] == ladder["by_clock_basis"][basis]["n_dates"] == 30
        assert sub["hit_rate"] is None and sub["benchmark_baseline_hit_rate"] is not None
        assert q.CLOCK_LEGACY not in ready["by_clock_basis"]


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


# =========================================================================== #
# P0d REVIEW FINDING 4 — MATURITY-AWARE COHORT ACCOUNTING
#
# THE PERVERSE INCENTIVE THIS SECTION KILLS. `grade_claim` rule 5 refuses the
# WHOLE grade row when a DECLARED control cannot be priced over the shared
# window. `matched_control_check` counted its cohort from GRADE ROWS, so such a
# claim left the coverage denominator entirely — while a claim declaring NO
# control left a row that counted as uncovered. Declaring an unpriceable control
# was therefore strictly BETTER for reported coverage than declaring none, and in
# its worst form (every control unpriceable) the gate reported "the cohort is
# EMPTY — accruing" forever. Rowless cohort claims are now CLASSIFIED and only
# the control-refused ones rejoin the denominator.
# =========================================================================== #
#: A ticker with NO price series anywhere in the fixture — a declared control
#: that `_leg_ret_in_window` can never measure, i.e. rule 5's refusal.
UNPRICEABLE_CONTROL = "XLZ"
#: Fixed evaluation date: after every 2025 window below closes, and inside the
#: fixture's price coverage. Deterministic regardless of the wall clock.
F4_TODAY = date(2025, 12, 31)


@pytest.fixture
def f4_prices(monkeypatch):
    """Subject/bench/control priceable across 2025; `UNPRICEABLE_CONTROL` absent.

    One patch covers BOTH halves of the classifier: `_matured_window` reads
    prices through `engine.desk_scorer.covers` -> `ai_desk._close_series`, and
    `_leg_ret_in_window` reads the same function directly."""
    store = {
        "AAPL": _session_series("2025-01-02", "2025-12-31", 100.0, 0.010),
        "SPY": _session_series("2025-01-02", "2025-12-31", 400.0, 0.002),
        "XLK": _session_series("2025-01-02", "2025-12-31", 100.0, 0.004),
    }
    monkeypatch.setattr("engine.ai_desk._close_series",
                        lambda ticker, root: store.get(ticker))
    return store


def _controlled_graded(n: int, start: str = "2025-02-03",
                       family: str = REQ_A) -> tuple[list[dict], list[dict]]:
    """`n` mature, validly-controlled, GRADED cohort claims — the covered book
    every finding-4 test measures its coverage against."""
    claims, grades = [], []
    for asof in _dates(n, start):
        c = _claim(family=family, asof=asof, control="XLK", claim_id=f"ctl|{asof}")
        claims.append(c)
        grades.append(_grade_row(c, subject_ret=0.06, control_ret=0.01,
                                 bench_ret=0.0, hit=True))
    return claims, grades


def _f4_store(root: Path, *, n_controlled: int, n_other: int,
              other_control: str | None, other_horizon: int = 21,
              other_start: str = "2025-05-01") -> None:
    """`n_controlled` covered+graded claims, plus `n_other` claims whose control
    is `other_control`.

    `other_control=None` -> a claim declaring NO control: `grade_claim` writes a
    row (bench legs only), so it stays in the cohort as an UNCOVERED row.
    `other_control=UNPRICEABLE_CONTROL` -> rule 5 refuses the row, so NO grade
    row is written — the state whose accounting this section repairs."""
    claims, grades = _controlled_graded(n_controlled)
    for asof in _dates(n_other, other_start):
        c = _claim(family=REQ_A, asof=asof, control=other_control,
                   horizon=other_horizon, claim_id=f"oth|{asof}")
        claims.append(c)
        if other_control is None:
            grades.append(_grade_row(c, other_horizon, subject_ret=0.06,
                                     control_ret=None, bench_ret=0.0, hit=True))
    _write_store(root, claims, grades)
    _start_clock(root, REQ_A)


def test_f4_declaring_an_unpriceable_control_cannot_beat_declaring_none(f4_prices, tmp_path):
    """THE HEART OF FINDING 4. Two cohorts identical but for one thing: in world A
    the uncovered half declares NO control (its rows exist, counted as uncovered);
    in world B the same half declares a control whose price series is absent, so
    rule 5 refuses every one of those rows. Coverage must be EQUAL and both must
    refuse — otherwise the cheapest route to a passing coverage number is to
    declare controls that cannot be measured.

    Under the old accounting world B reported coverage 1.0 over 30 controlled
    dates and returned ELIGIBLE — a matched-control promotion on a book that was
    half unmeasurable.

    MUTATION CONTROL: revert the denominator to `n_cohort_rows = len(rows)` (and
    drop `control_refused_dates` from `n_cohort_dates`). World B's coverage
    returns to 1.0 and `eligible` to True, and this test fails on
    `rb.control_coverage == ra.control_coverage` and on `rb.eligible is False`.
    """
    a, b = tmp_path / "declares_no_control", tmp_path / "declares_unpriceable"
    _f4_store(a, n_controlled=30, n_other=30, other_control=None)
    _f4_store(b, n_controlled=30, n_other=30, other_control=UNPRICEABLE_CONTROL)

    ra = q.matched_control_check(REQ_A, 21, root=a, today=F4_TODAY)
    rb = q.matched_control_check(REQ_A, 21, root=b, today=F4_TODAY)

    assert ra.control_coverage == pytest.approx(0.5)
    assert rb.control_coverage == ra.control_coverage
    assert ra.eligible is False and rb.eligible is False
    assert ra.n_cohort_rows == rb.n_cohort_rows == 60
    assert ra.n_cohort_dates == rb.n_cohort_dates == 60
    assert ra.n_controlled_rows == rb.n_controlled_rows == 30

    # ...and the two worlds are still TOLD APART in the disclosure: A's uncovered
    # rows are rows, B's are refused controls.
    assert ra.n_control_refused_rows == 0 and ra.cohort_rowless == {}
    assert rb.n_control_refused_rows == 30 and rb.n_control_refused_dates == 30
    assert rb.cohort_rowless == {q.COHORT_ROWLESS_CONTROL_REFUSED: 30}
    assert UNPRICEABLE_CONTROL in rb.reason
    assert "UNCOVERED" in rb.reason


def _immature_cohort(root: Path):
    """30 mature controlled+graded claims + 5 controlled claims whose windows do
    not close until 2026 — evaluated at 2025-12-22, the five are simply young."""
    claims, grades = _controlled_graded(30)
    for asof in _dates(5, "2025-12-15"):          # windows close in 2026
        claims.append(_claim(family=REQ_A, asof=asof, control="XLK",
                             claim_id=f"young|{asof}"))
    _write_store(root, claims, grades)
    _start_clock(root, REQ_A)
    return q.matched_control_check(REQ_A, 21, root=root, today=date(2025, 12, 22))


# SPLIT DELIBERATELY (review round 2, cosmetic finding): the census assertion and
# the gate-verdict assertion were one test, so the first to fail short-circuited
# and only HALF the stated mutation coverage was ever exercised. Two tests, two
# independently-earned claims, one shared store.
def test_f4_an_immature_controlled_claim_is_not_a_control_refusal(f4_prices, tmp_path):
    """`not_yet_matured` is a young claim, not a refusal — DISCLOSED under
    `cohort_rowless` so the cohort reads as young rather than as broken.

    MUTATION CONTROL: classify every rowless cohort claim as
    `COHORT_ROWLESS_CONTROL_REFUSED`. This test fails on the `cohort_rowless`
    census and on `n_control_refused_rows == 0`.
    """
    r = _immature_cohort(tmp_path)

    assert r.cohort_rowless == {q.COHORT_ROWLESS_NOT_YET_MATURED: 5}
    assert r.n_control_refused_rows == 0
    assert r.n_control_refused_dates == 0


def test_f4_an_immature_controlled_claim_leaves_the_gate_verdict_intact(f4_prices, tmp_path):
    """The other half, asserted on its own so it is genuinely exercised: young
    claims touch NO denominator, so coverage and eligibility are unmoved.

    MUTATION CONTROL: the same one — classify every rowless cohort claim as
    `COHORT_ROWLESS_CONTROL_REFUSED`. The five young claims enter the
    denominator, coverage falls to 30/35 = 0.857, and this test fails on
    `control_coverage == 1.0` and on `eligible is True`.
    """
    r = _immature_cohort(tmp_path)

    assert r.n_cohort_rows == 30 and r.n_cohort_dates == 30
    assert r.control_coverage == 1.0
    assert r.eligible is True, r.reason


def _holed_subject_cohort(prices: dict, root: Path):
    """30 mature controlled+graded claims + 5 whose SUBJECT series reaches the
    window's close (so maturity passes) but is missing the window's own entry bar
    — the real rule-5 shortened-window refusal, on the primary leg."""
    claims, grades = _controlled_graded(30)
    for i, asof in enumerate(_dates(5, "2025-06-02")):
        subject = f"HOLEY{i}"
        c = _claim(family=REQ_A, asof=asof, control="XLK", subject=subject,
                   claim_id=f"holey|{asof}")
        claims.append(c)
        window = q.claim_window(c, 21)
        series = _session_series("2025-01-02", "2025-12-31", 50.0, 0.001)
        prices[subject] = series.drop(pd.Timestamp(window.fill_date))
    _write_store(root, claims, grades)
    _start_clock(root, REQ_A)
    return q.matched_control_check(REQ_A, 21, root=root, today=F4_TODAY)


# Split for the same reason as the pair above: one assertion per claimed
# mutation consequence, so neither half can hide behind the other's failure.
def test_f4_a_refused_primary_leg_is_never_attributed_to_the_control(f4_prices, tmp_path):
    """A SUBJECT that cannot be measured over the shared window refuses the row
    too — but that is the subject's data gap, not a missing control.

    MUTATION CONTROL: attribute primary refusals to the control class (return
    `COHORT_ROWLESS_CONTROL_REFUSED` at step 6). This test fails on the
    `cohort_rowless` census and on `n_control_refused_rows == 0`.
    """
    r = _holed_subject_cohort(f4_prices, tmp_path)

    assert r.cohort_rowless == {q.COHORT_ROWLESS_PRIMARY_REFUSED: 5}
    assert r.n_control_refused_rows == 0
    assert r.n_control_refused_dates == 0


def test_f4_a_refused_primary_leg_never_moves_the_coverage_number(f4_prices, tmp_path):
    """The consequence that matters, asserted on its own: turning a delisted or
    holed SUBJECT into a control refusal would manufacture a coverage failure out
    of a price-store gap.

    MUTATION CONTROL: the same one. Coverage falls to 30/35 = 0.857 and this test
    fails on `control_coverage == 1.0` and on `eligible is True`.
    """
    r = _holed_subject_cohort(f4_prices, tmp_path)

    assert r.n_cohort_rows == 30 and r.n_cohort_dates == 30
    assert r.control_coverage == 1.0
    assert r.eligible is True, r.reason


def test_f4_a_horizon_that_can_never_grade_here_is_not_a_refusal(f4_prices, tmp_path):
    """A claim whose declared ruler never grades at the evaluated horizon has no
    row here and never will — it is refusing nothing, and it must never land in a
    denominator it can never leave.

    MUTATION CONTROL: drop the `in_scope_horizons` step from
    `_cohort_rowless_class`. The ten 5-day claims (which carry an UNPRICEABLE
    control, so they classify as control-refused once the horizon guard is gone)
    enter the denominator, coverage falls to 30/40 = 0.75, and this test fails on
    `eligible is True` and on the `cohort_rowless` census.
    """
    assert q.in_scope_horizons(5) == [5], "canary: a 5d claim grades only at 5d"

    claims, grades = _controlled_graded(30)
    for asof in _dates(10, "2025-06-02"):
        claims.append(_claim(family=REQ_A, asof=asof, horizon=5,
                             control=UNPRICEABLE_CONTROL, claim_id=f"h5|{asof}"))
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.matched_control_check(REQ_A, 21, root=tmp_path, today=F4_TODAY)

    assert r.cohort_rowless == {q.COHORT_ROWLESS_HORIZON_OUT_OF_SCOPE: 10}
    assert r.n_control_refused_rows == 0
    assert r.n_cohort_rows == 30
    assert r.control_coverage == 1.0
    assert r.eligible is True, r.reason


def test_f4_a_cohort_whose_controls_all_refuse_is_not_reported_as_empty(f4_prices, tmp_path):
    """FINDING 4 IN ITS WORST FORM. When EVERY control is unpriceable there are no
    grade rows at all, so the old path had no basis, no rows, and reported "the
    matched-control cohort is EMPTY — accruing" forever: a family whose control
    legs systematically cannot be measured reading as "no evidence yet". The
    evaluation basis is now derived from the refused claims' own windows and the
    verdict names the cause.

    MUTATION CONTROL: restore the plain `if n_cohort_dates == 0` empty-cohort
    early return ahead of the refusal accounting. `control_coverage` returns to
    None and the reason to "is EMPTY", failing this test twice over.
    """
    claims = [_claim(family=REQ_A, asof=asof, control=UNPRICEABLE_CONTROL,
                     claim_id=f"x|{asof}") for asof in _dates(30, "2025-02-03")]
    _write_store(tmp_path, claims, [])
    _start_clock(tmp_path, REQ_A)

    r = q.matched_control_check(REQ_A, 21, root=tmp_path, today=F4_TODAY)

    assert r.control_coverage == 0.0        # NOT None, and NOT "empty"
    assert r.n_cohort_rows == 30 and r.n_cohort_dates == 30
    assert r.n_controlled_rows == 0 and r.n_controlled_dates == 0
    assert r.n_control_refused_rows == 30 and r.n_control_refused_dates == 30
    assert r.clock_basis is not None, "the basis comes from the refused windows"
    assert r.eligible is False
    assert r.reason.startswith("accruing_with_missing_control")
    assert "EMPTY" not in r.reason
    assert UNPRICEABLE_CONTROL in r.reason


def test_f4_a_genuinely_empty_cohort_still_says_empty(tmp_path):
    """The EMPTY message is not retired — it is now reserved for the case it
    actually describes: no rows AND no control-refused claims."""
    _start_clock(tmp_path, REQ_A)
    _write_store(tmp_path, [], [])

    r = q.matched_control_check(REQ_A, 21, root=tmp_path, today=F4_TODAY)

    assert "is EMPTY" in r.reason
    assert r.control_coverage is None
    assert r.n_cohort_rows == 0 and r.n_control_refused_rows == 0
    assert r.cohort_rowless == {}


def test_f4_a_fully_graded_cohort_reports_byte_identical_numbers(tmp_path):
    """REGRESSION. With nothing refused, every number this gate reported before
    finding 4 is unchanged — the repair is strictly ADDITIVE (coverage can only
    fall, and only when a control actually refused)."""
    claims, grades = _cohort(REQ_A, 100, controlled=37)
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)

    assert (r.n_cohort_rows, r.n_cohort_dates) == (100, 100)
    assert (r.n_controlled_rows, r.n_controlled_dates) == (37, 37)
    assert r.control_coverage == pytest.approx(0.37)
    assert r.n_dates == 37
    assert r.eligible is False
    assert r.n_control_refused_rows == 0 and r.n_control_refused_dates == 0
    assert r.cohort_rowless == {}


def test_f4_a_closed_window_with_a_dead_subject_is_a_primary_leg_refusal(
        f4_prices, tmp_path):
    """REVIEW DEFECT 2 (ported from #5661). `not_yet_matured` means ONE thing —
    the window has not closed (contract C4.4's table). A subject whose price
    series simply ENDS (delisted, or never collected past a point) leaves a
    window that HAS closed and cannot be priced: that is `primary_leg_refused`,
    and it stays out of the coverage denominator like every other non-control
    refusal.

    Before the fix, `_matured_window` was asked first, and it answers False for
    BOTH "not closed yet" and "a leg's series does not reach the close" — so a
    permanently dead subject reported as YOUNG forever, which is exactly the
    young-vs-broken confusion the classification exists to prevent, and it left
    `primary_leg_refused` reachable only through the rarer rule-5 endpoint hole.

    MUTATION CONTROL: ask `_matured_window(root, window, today, [subject, bench])`
    BEFORE the `today < window.coverage_date` check (the shipped order before
    this fix). The five dead-subject claims classify as `not_yet_matured` and
    this test fails on the `cohort_rowless` equality.
    """
    claims, grades = _controlled_graded(30)
    for i, asof in enumerate(_dates(5, "2025-06-02")):
        subject = f"DEAD{i}"
        c = _claim(family=REQ_A, asof=asof, control="XLK", subject=subject,
                   claim_id=f"dead|{asof}")
        claims.append(c)
        window = q.claim_window(c, 21)
        # the series STOPS well before the window's close, and the window IS
        # closed as of F4_TODAY — a delisting, not a young claim.
        f4_prices[subject] = _session_series("2025-01-02", "2025-05-01", 50.0, 0.001)
        assert F4_TODAY >= window.coverage_date, "the fixture must be MATURE"
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.matched_control_check(REQ_A, 21, root=tmp_path, today=F4_TODAY)

    assert r.cohort_rowless == {q.COHORT_ROWLESS_PRIMARY_REFUSED: 5}, (
        "a CLOSED window that the subject cannot price is not a young claim")
    assert r.n_control_refused_rows == 0, "never the control's fault"
    assert r.n_cohort_rows == 30, "and never in the coverage denominator"
    assert r.control_coverage == 1.0
    assert r.eligible is True, r.reason


def test_f4_an_immature_claim_still_reads_as_immature_after_the_fix(
        f4_prices, tmp_path):
    """The other side of defect 2 (ported from #5661): moving the calendar test
    first must not reclassify a genuinely YOUNG claim. Same shape as the
    dead-subject case except the window has NOT closed — and the subject is
    perfectly priceable up to today, so only the calendar separates the two
    tests."""
    claims, grades = _controlled_graded(30)
    early = date(2025, 5, 15)
    for asof in _dates(5, "2025-05-01"):
        c = _claim(family=REQ_A, asof=asof, control="XLK", claim_id=f"young|{asof}")
        claims.append(c)
        assert early < q.claim_window(c, 21).coverage_date, "must be IMMATURE"
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.matched_control_check(REQ_A, 21, root=tmp_path, today=early)

    assert r.cohort_rowless == {q.COHORT_ROWLESS_NOT_YET_MATURED: 5}
    assert r.n_control_refused_rows == 0
    assert r.n_cohort_rows == 30


def test_f4_a_rowless_member_on_another_clock_basis_enters_no_count(
        f4_prices, tmp_path):
    """`other_basis` (C4.4's last table row; ported from #5661): a rowless cohort
    member whose own window resolves on a DIFFERENT grading clock is not this
    evaluation's business — it is counted under its own basis, never pooled into
    this one (P0a). Even when its control is unpriceable, it must NOT join THIS
    basis's coverage denominator.

    The claim below declares `calendar_days` while the graded book declares
    `trading_days`, so the two resolve to different basis keys at the same
    horizon.

    MUTATION CONTROL: drop the `row_basis != basis -> COHORT_ROWLESS_OTHER_BASIS`
    re-tag in `matched_control_check`. The calendar-clock claims are then counted
    as `control_leg_refused` on the trading-days basis, `n_cohort_rows` becomes
    33, coverage falls to 30/33, and this test fails on all three assertions.
    """
    claims, grades = _controlled_graded(30)
    for asof in _dates(3, "2025-06-02"):
        c = _claim(family=REQ_A, asof=asof, control=UNPRICEABLE_CONTROL,
                   unit="calendar_days", claim_id=f"cal|{asof}")
        claims.append(c)
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    r = q.matched_control_check(REQ_A, 21, root=tmp_path, today=F4_TODAY)

    # the graded book decides the basis; the calendar-clock members are elsewhere
    assert r.clock_basis == q.clock_basis_key(q.CLOCK_V1, "trading_days",
                                              q.MARKET_US)
    assert r.cohort_rowless == {q.COHORT_ROWLESS_OTHER_BASIS: 3}
    assert r.n_control_refused_rows == 0, (
        "an unpriceable control on ANOTHER basis is not this basis's uncovered claim")
    assert r.n_cohort_rows == 30
    assert r.control_coverage == 1.0


def test_f4_readiness_row_publishes_the_control_refusal_accounting(f4_prices, tmp_path):
    """C6.1 at the payload the admin tab and the first-cross alert actually read:
    a coverage number that MOVED because controls refused must be legible as
    that, not as an unexplained drop.

    (Asserted here rather than only in tests/test_grade_qledger.py: that suite is
    wired into no CI pack today, so an assertion living only there is invisible.)

    MUTATION CONTROL: drop the three keys from `_readiness_row` in
    scripts/grade_qledger.py — this test fails on the missing keys.
    """
    _f4_store(tmp_path, n_controlled=30, n_other=30,
              other_control=UNPRICEABLE_CONTROL)

    row = grader.compute_promotion_readiness(tmp_path, families=[REQ_A])[REQ_A]["21"]

    assert row["n_control_refused_rows"] == 30
    assert row["n_control_refused_dates"] == 30
    assert row["cohort_rowless"] == {q.COHORT_ROWLESS_CONTROL_REFUSED: 30}
    assert row["n_cohort_rows"] == 60
    assert row["control_coverage"] == pytest.approx(0.5)
    assert row["evidence_basis"] == q.EVIDENCE_BASIS_MATCHED_CONTROL
    assert row["ready"] is False


def test_f4_a_raising_classifier_gets_its_own_class_not_window_unresolvable(
        f4_prices, tmp_path, monkeypatch, caplog):
    """REVIEW ROUND 2, F4. `_cohort_rowless_class`'s catch-all returned
    `window_unresolvable` — a LEGITIMATE, expected outcome whose count carries no
    alarm, so a crash was hidden inside a normal number. And hidden in the
    coverage-FAVOURABLE direction: neither class enters a denominator, so every
    control refusal a crash swallowed silently RAISED coverage. Behaviour is
    unchanged (still no denominator, still non-fatal); the class is now its own
    and the log is a WARNING, so a non-zero count is visible on the readiness row.

    MUTATION CONTROL: return `COHORT_ROWLESS_WINDOW_UNRESOLVABLE` from the
    `except` again — this test fails on the `classifier_error` census key.
    """
    claims, grades = _controlled_graded(30)
    for asof in _dates(3, "2025-06-02"):
        claims.append(_claim(family=REQ_A, asof=asof, control="XLK",
                             claim_id=f"boom|{asof}"))
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    real_window = q.claim_window

    def _boom_on_the_rowless(claim, horizon_d, entry_anchor=None):
        if str(claim.get("claim_id", "")).startswith("boom|") and entry_anchor is not None:
            raise RuntimeError("calendar module exploded")
        return real_window(claim, horizon_d, entry_anchor=entry_anchor)

    monkeypatch.setattr(q, "claim_window", _boom_on_the_rowless)
    with caplog.at_level("WARNING", logger="qledger"):
        r = q.matched_control_check(REQ_A, 21, root=tmp_path, today=F4_TODAY)

    assert r.cohort_rowless.get(q.COHORT_ROWLESS_CLASSIFIER_ERROR) == 3
    assert q.COHORT_ROWLESS_WINDOW_UNRESOLVABLE not in r.cohort_rowless, (
        "a crash must not be filed under a legitimate expected outcome")
    # unchanged behaviour: it still enters NO denominator and never refuses
    assert r.n_control_refused_rows == 0
    assert r.n_cohort_rows == 30 and r.control_coverage == 1.0
    assert r.eligible is True, r.reason
    assert any("RAISED" in rec.getMessage() for rec in caplog.records), (
        "the catch-all must be a WARNING, not a DEBUG nobody reads")


def test_f4_classifier_error_is_disclosed_on_the_readiness_row(f4_prices, tmp_path, monkeypatch):
    """The point of giving the crash its own key is that an operator can SEE it:
    it has to survive into the nightly payload, not just the in-memory verdict."""
    claims, grades = _controlled_graded(30)
    claims.append(_claim(family=REQ_A, asof="2025-06-02", control="XLK",
                         claim_id="boom|one"))
    _write_store(tmp_path, claims, grades)
    _start_clock(tmp_path, REQ_A)

    real_window = q.claim_window
    monkeypatch.setattr(q, "claim_window", lambda claim, h, entry_anchor=None: (
        (_ for _ in ()).throw(RuntimeError("boom"))
        if str(claim.get("claim_id", "")) == "boom|one" and entry_anchor is not None
        else real_window(claim, h, entry_anchor=entry_anchor)))

    row = grader.compute_promotion_readiness(tmp_path, families=[REQ_A])[REQ_A]["21"]
    assert row["cohort_rowless"].get(q.COHORT_ROWLESS_CLASSIFIER_ERROR) == 1


def test_f4_promotion_result_as_dict_carries_the_new_accounting_keys(tmp_path):
    """The three fields travel on `as_dict()` — `ladder_states` and the readiness
    payload both serialise through it."""
    _start_clock(tmp_path, REQ_A)
    d = q.matched_control_check(REQ_A, 21, root=tmp_path, today=F4_TODAY).as_dict()
    for key in ("n_control_refused_rows", "n_control_refused_dates", "cohort_rowless"):
        assert key in d, key


# =========================================================================== #
# THE C2.3 CONTROL CONSTRUCTION — alias composition (census D0-2 / D0-1)
# =========================================================================== #
#: Census D0-2's alias set, pinned HERE rather than read from the module: a test
#: that iterates the table it is guarding goes vacuous the moment a row is
#: deleted (the deleted row is simply never visited).
D0_2_ALIASES = {
    "Technology": "Information Technology",
    "Healthcare": "Health Care",
    "Financial": "Financials",
    "Consumer Cyclical": "Consumer Discretionary",
    "Basic Materials": "Materials",
    "Consumer Defensive": "Consumer Staples",
}


def test_gics_sector_name_composes_to_the_direct_etf_map():
    """THE COMPOSITION INVARIANT that makes `membership_gics_sector_of` safe to
    hand to `make_claim`:

        control_for_sector(gics_sector_name(v)) == sector_gics_etf(v)

    for EVERY input. `make_claim` resolves the control itself from the `sector`
    it is given, so a resolver returning the canonical NAME must land on exactly
    the ETF the direct map would have chosen — and a resolver returning the ETF
    would be feeding an ETF ticker into a GICS-NAME map, census D0-1 in reverse.

    MUTATION CONTROL: delete any row from `qledger._SECTOR_ALIASES` (e.g.
    "Technology"). The pinned-table assertion and the per-alias name assertion
    both fail. (The composition equality alone would NOT catch it — both sides
    go None together — which is exactly why the alias set is pinned literally.)
    """
    assert q._SECTOR_ALIASES == D0_2_ALIASES

    for raw, canonical in D0_2_ALIASES.items():
        assert q.gics_sector_name(raw) == canonical, raw
        assert q.gics_sector_name(canonical) == canonical, canonical
        assert q.control_for_sector(q.gics_sector_name(raw)) == q.sector_gics_etf(raw)

    probes = (list(D0_2_ALIASES) + list(D0_2_ALIASES.values())
              + list(q._GICS_ETF) + list(q._GICS_ETF.values())
              + ["QQQ", "SMH", "Nonexistent Sector", "technology", "  ", "", None])
    for v in probes:
        assert q.control_for_sector(q.gics_sector_name(v)) == q.sector_gics_etf(v), v

    # the NAME, never the ETF
    assert q.gics_sector_name("Technology") == "Information Technology"
    assert q.gics_sector_name("Technology") not in set(q._GICS_ETF.values())
    assert q.gics_sector_name("  Healthcare  ") == "Health Care"
    assert q.gics_sector_name("QQQ") is None      # an ETF ticker is not a sector
    assert q.gics_sector_name(None) is None
    assert q.gics_sector_name("") is None
    assert q.gics_sector_name("Nonexistent Sector") is None


def test_membership_gics_sector_of_resolves_both_vocabularies_and_fails_open(tmp_path):
    """The C2.3 resolver end to end: membership.parquet -> canonical GICS NAME,
    across both of the file's vocabularies; None (never a raise) for an unknown
    value, an absent ticker, or an absent file.

    MUTATION CONTROL: return `sector_gics_etf(...)` instead of
    `gics_sector_name(...)` from the closure — every assertion below that names a
    sector fails, and the D0-1-in-reverse defect is caught at the boundary.
    """
    assert q.membership_gics_sector_of(tmp_path)("AAPL") is None   # no file at all

    root = tmp_path / "u"
    d = root / "data" / "universe"
    d.mkdir(parents=True)
    pd.DataFrame({"ticker": ["AAPL", "JNJ", "XOM", "WEIRD"],
                  "sector": ["Technology", "Health Care", "Consumer Defensive",
                             "Quantum Widgets"]}).to_parquet(d / "membership.parquet")
    q._MEMBERSHIP_SECTORS.clear()

    resolve = q.membership_gics_sector_of(root)
    assert resolve("AAPL") == "Information Technology"     # Yahoo -> canonical
    assert resolve("JNJ") == "Health Care"                 # already canonical
    assert resolve("XOM") == "Consumer Staples"            # Yahoo -> canonical
    assert resolve("weird") is None                        # unknown vocabulary
    assert resolve("OFFIDX") is None                       # absent from the file
    assert resolve(None) is None
    assert q.control_for_sector(resolve("AAPL")) == "XLK"


# =========================================================================== #
# P0d REVIEW ROUND 2, F5 — `today` REACHES THE MATCHED-CONTROL GATE
#
# `scripts/grade_qledger.py --today` exists for point-in-time replay and it
# reached `grade_claim`. It did NOT reach the readiness path:
# `run_readiness_post_step` -> `compute_promotion_readiness` ->
# `promotion_check_dispatch` -> `matched_control_check(root=root)` — no `today`.
# So a replay graded against date T while `_cohort_rowless_class` judged cohort
# MATURITY against the wall clock. The drift was conservative in direction (extra
# claims look matured and mostly land in `matured_awaiting_grading`), but two
# dates inside one run is exactly the point-in-time inconsistency C4.4's
# classification exists to rule out: the CLASS is the truth about why a row is
# missing, and a class computed on the wrong date is not that truth.
# =========================================================================== #
def _f5_replay_store(root: Path):
    """30 mature controlled+graded claims + 5 controlled claims registered in
    2025-06 whose 21-session windows close in JULY.

    AS OF 2025-06-16 (the replay date) those five have NOT matured; as of the
    wall clock — and as of F4_TODAY — they are long matured. That gap is the
    whole test: the five are `not_yet_matured` on a PIT replay and something else
    entirely if the gate silently re-reads `date.today()`."""
    claims, grades = _controlled_graded(30)
    for asof in _dates(5, "2025-06-09"):
        claims.append(_claim(family=REQ_A, asof=asof, control="XLK",
                             claim_id=f"replay|{asof}"))
    _write_store(root, claims, grades)
    _start_clock(root, REQ_A)


F5_REPLAY_TODAY = date(2025, 6, 16)


def test_f5_a_replay_judges_maturity_on_the_replay_date_not_the_wall_clock(
        f4_prices, tmp_path):
    """THE PIT INVARIANT, at the gate itself. Same store, two reference dates:
    at the replay date the five young claims are `not_yet_matured`; at a later
    date they are not. If `today` did not reach `_cohort_rowless_class` the two
    calls would be indistinguishable.

    MUTATION CONTROL: drop the `today=` kwarg from `matched_control_check`'s call
    inside `promotion_check_dispatch` — see the sibling test below, which is the
    one that exercises the production dispatch. THIS test pins the gate's own
    contract and fails if `matched_control_check` stops honouring `today`.
    """
    _f5_replay_store(tmp_path)

    replay = q.matched_control_check(REQ_A, 21, root=tmp_path,
                                     today=F5_REPLAY_TODAY)
    later = q.matched_control_check(REQ_A, 21, root=tmp_path, today=F4_TODAY)

    assert replay.cohort_rowless == {q.COHORT_ROWLESS_NOT_YET_MATURED: 5}
    assert later.cohort_rowless != replay.cohort_rowless, (
        "if the two dates agree, the reference date is not being honoured at all")
    assert q.COHORT_ROWLESS_NOT_YET_MATURED not in later.cohort_rowless


def test_f5_promotion_check_dispatch_threads_today_to_the_matched_gate(
        f4_prices, tmp_path):
    """THE PRODUCTION DISPATCH, which is where the date was actually dropped.

    MUTATION CONTROL: in `engine/qledger.py::promotion_check_dispatch`, drop the
    `today=today` kwarg from the `matched_control_check(...)` call so it falls
    back to `date.today()`. The five claims then read as matured (the wall clock
    is well past their July 2025 windows) and this test fails on
    `cohort_rowless == {not_yet_matured: 5}`.
    """
    _f5_replay_store(tmp_path)

    pr = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path,
                                    today=F5_REPLAY_TODAY)

    assert pr.evidence_basis == q.EVIDENCE_BASIS_MATCHED_CONTROL
    assert pr.cohort_rowless == {q.COHORT_ROWLESS_NOT_YET_MATURED: 5}


def test_f5_readiness_payload_is_point_in_time_consistent(f4_prices, tmp_path):
    """The payload the admin tab and the first-cross alert read must carry the
    REPLAY's classification, not a wall-clock one — a replayed nightly that
    publishes wall-clock maturity is publishing two dates in one record.

    MUTATION CONTROL: drop the `today=today` kwarg from the
    `q.promotion_check_dispatch(...)` call in
    `scripts/grade_qledger.py::compute_promotion_readiness` — this test fails on
    the `cohort_rowless` census in the emitted row.
    """
    _f5_replay_store(tmp_path)

    row = grader.compute_promotion_readiness(
        tmp_path, families=[REQ_A], today=F5_REPLAY_TODAY)[REQ_A]["21"]

    assert row["cohort_rowless"] == {q.COHORT_ROWLESS_NOT_YET_MATURED: 5}
    assert row["n_cohort_rows"] == 30
    assert row["evidence_basis"] == q.EVIDENCE_BASIS_MATCHED_CONTROL


def test_f5_ladder_states_is_point_in_time_consistent(f4_prices, tmp_path):
    """`emit_ladder_states` writes the OTHER production artifact
    (track_record.json). Review round 1 finding 7 established that these two
    payloads must agree; they cannot agree if only one of them knows the date.

    MUTATION CONTROL: drop the `today=today` kwarg from the
    `promotion_check_dispatch(...)` call in `engine/qledger.py::
    emit_ladder_states` — this test fails on the `cohort_rowless` census.
    """
    _f5_replay_store(tmp_path)

    entry = q.emit_ladder_states(root=tmp_path, families=[REQ_A],
                                 today=F5_REPLAY_TODAY)[REQ_A]["21"]

    assert entry["cohort_rowless"] == {q.COHORT_ROWLESS_NOT_YET_MATURED: 5}


def test_f5_omitting_today_is_unchanged_wall_clock_behaviour(f4_prices, tmp_path):
    """BACKWARD COMPATIBILITY, asserted rather than assumed: every signature
    keeps its default, and a caller that passes no `today` gets exactly the
    wall-clock answer it got before this change."""
    _f5_replay_store(tmp_path)

    default = q.promotion_check_dispatch(REQ_A, 21, root=tmp_path)
    explicit = q.matched_control_check(REQ_A, 21, root=tmp_path,
                                       today=date.today())

    assert default.cohort_rowless == explicit.cohort_rowless
    assert default.control_coverage == explicit.control_coverage
    assert default.n_cohort_rows == explicit.n_cohort_rows
    # and the readiness/ladder paths agree with it when `today` is omitted too
    row = grader.compute_promotion_readiness(tmp_path, families=[REQ_A])[REQ_A]["21"]
    assert row["cohort_rowless"] == default.cohort_rowless
