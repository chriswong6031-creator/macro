"""tests/test_prophet_stage_tilt.py — PSQ-TILT W1 hold-leash tests.

Implements the design test list in research/PROPHET_STAGE_TILT_W1_DESIGN.md §Tests:

  1. Leash matrix: (stage2, EC>=24, non-bear) -> 56; each single failing cond -> 45.
  2. Bear fail-safe: missing/corrupt data/regime/latest.json -> leash 1.0, no raise.
  3. Anti-veto/anti-rank pin: selected candidate ids + order identical tilt-on vs
     tilt-off (monkeypatch the tilt inputs to force eligibility).
  4. Degrade-to-1.0 on EC-table load failure and on stage-classify exception (no raise).
  5. Horizon propagation: tilted plan reaches management with tau on 56; ledger
     EXPIRED fires at >=56 not 45; option expiry min-date respects the scaled horizon.
  6. Ledger row schema unchanged (12 keys — existing pin must still pass; asserted here too).
  7. stage_tilt present in plan JSON + index.json projection; "validated" absent from plan JSONs.
  8. Auto-demote: synthetic summary.json with n>=30 & diff<=0 -> leash forced 1.0 +
     demoted: true; n<30 -> active.
  9. Shadow median_tilt emission: schema, nulls-when-unmatured, context-only pins intact.

Authority boundary (binding): the tilt is never an entry veto, never rank suppression,
never a win-rate gate. It only extends the intended HOLD horizon. Any input failure
degrades to leash 1.0 with a ::warning::; origination never raises because of the tilt.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

# ── repo path ─────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import engine.prophet_bridge as pb
import engine.prophet_stage_fusion as psf
import engine.prophet_stage_shadow as pss


# ---------------------------------------------------------------------------
# Fixtures — a tilt_inputs bundle the per-pick compute reads.
# ---------------------------------------------------------------------------
def _tilt_inputs(stage=2, ec_sent=30.0, ec_call_date="2026-06-01",
                 bear=False, demoted=False, ec_load_ok=True):
    """Build a fake tilt_inputs dict that _compute_stage_tilt consumes.

    We monkeypatch psf.stage_at_entry / psf.load_ticker_prices / psf.ec_sent_at_entry
    via a stub psf object so no real parquet is needed. The bench/root are inert.
    """
    ec_by_ticker: dict = {}
    if ec_sent is not None and ec_call_date is not None:
        ec_by_ticker = {
            "AAA": pd.DataFrame({
                "ticker": ["AAA"],
                "call_date": [pd.Timestamp(ec_call_date)],
                "earnings_call_sent": [ec_sent],
            })
        }

    class _StubPSF:
        EC_SENT_GATE = psf.EC_SENT_GATE

        @staticmethod
        def load_ticker_prices(ticker, root):
            # Non-empty close series so stage_at_entry runs.
            idx = pd.bdate_range("2020-01-01", periods=400)
            close = pd.Series(range(400), index=idx, dtype=float) + 100.0
            return close, None

        @staticmethod
        def stage_at_entry(close, vol, bench, entry_date):
            return int(stage), 5, 100

        @staticmethod
        def ec_sent_at_entry(ec_map, ticker, entry_date):
            return ec_sent

    return {
        "root": Path("/nonexistent"),
        "psf": _StubPSF,
        "ec_by_ticker": ec_by_ticker,
        "ec_load_ok": ec_load_ok,
        "bench": None,
        "bear": bear,
        "demoted": demoted,
    }


# ---------------------------------------------------------------------------
# 1. Leash matrix
# ---------------------------------------------------------------------------
def test_leash_matrix_all_conditions_met():
    """stage2 ∩ EC>=24 ∩ non-bear ∩ not-demoted -> leash 1.25 -> horizon 56."""
    hd, st = pb._compute_stage_tilt("AAA", "2026-07-01", _tilt_inputs())
    assert st["leash"] == pb.STAGE_TILT_LEASH == 1.25
    assert hd == 56
    assert st["eligible"] is True
    assert st["stage_at_entry"] == 2
    assert st["ec_sent"] == 30.0
    assert st["ec_call_date"] == "2026-06-01"
    assert st["bear_gate"] is False
    assert st["demoted"] is False
    assert st["provisional"] is True


@pytest.mark.parametrize("kwargs,reason", [
    ({"stage": 1}, "not-stage2"),
    ({"stage": 3}, "not-stage2"),
    ({"ec_sent": 23.0}, "ec-below-gate"),
    ({"ec_sent": None, "ec_call_date": None}, "no-ec"),
    ({"bear": True}, "bear-gate"),
])
def test_leash_matrix_single_failing_condition_gives_45(kwargs, reason):
    """Each single failing condition collapses the leash to 1.0 -> horizon 45."""
    hd, st = pb._compute_stage_tilt("AAA", "2026-07-01", _tilt_inputs(**kwargs))
    assert st["leash"] == 1.0, reason
    assert hd == 45, reason


def test_horizon_is_45_or_56_only():
    """The two lawful horizons: 45 (leash 1.0) and round(45*1.25)=56."""
    assert round(pb.HORIZON_DAYS_DEFAULT * 1.0) == 45
    assert round(pb.HORIZON_DAYS_DEFAULT * pb.STAGE_TILT_LEASH) == 56


# ---------------------------------------------------------------------------
# 2. Bear fail-safe — missing/corrupt regime artifact -> leash 1.0, no raise.
# ---------------------------------------------------------------------------
def test_bear_gate_missing_regime_file_is_bear(tmp_path):
    """No data/regime/latest.json -> bear=True (fail-safe), never raises."""
    assert pb._bear_from_regime(tmp_path) is True


def test_bear_gate_corrupt_regime_file_is_bear(tmp_path):
    (tmp_path / "regime").mkdir()
    (tmp_path / "regime" / "latest.json").write_text("{not json")
    assert pb._bear_from_regime(tmp_path) is True


def test_bear_gate_missing_keys_is_bear(tmp_path):
    (tmp_path / "regime").mkdir()
    (tmp_path / "regime" / "latest.json").write_text(json.dumps({"risk_radar": {}}))
    assert pb._bear_from_regime(tmp_path) is True


def test_bear_gate_reads_spy_below_200dma(tmp_path):
    (tmp_path / "regime").mkdir()
    (tmp_path / "regime" / "latest.json").write_text(json.dumps({
        "risk_radar": {"context_gate": {"spy_below_200dma": True}, "state": "caution"}
    }))
    assert pb._bear_from_regime(tmp_path) is True


def test_bear_gate_reads_risk_off_state(tmp_path):
    (tmp_path / "regime").mkdir()
    (tmp_path / "regime" / "latest.json").write_text(json.dumps({
        "risk_radar": {"context_gate": {"spy_below_200dma": False}, "state": "risk-off"}
    }))
    assert pb._bear_from_regime(tmp_path) is True


def test_bear_gate_none_sentinel_is_bear(tmp_path):
    """A present-but-None spy_below_200dma (SPY data gap) fails safe to bear."""
    (tmp_path / "regime").mkdir()
    (tmp_path / "regime" / "latest.json").write_text(json.dumps({
        "risk_radar": {"context_gate": {"spy_below_200dma": None}, "state": "watch"}
    }))
    assert pb._bear_from_regime(tmp_path) is True


def test_bear_gate_non_bear_when_healthy(tmp_path):
    (tmp_path / "regime").mkdir()
    (tmp_path / "regime" / "latest.json").write_text(json.dumps({
        "risk_radar": {"context_gate": {"spy_below_200dma": False}, "state": "caution"}
    }))
    assert pb._bear_from_regime(tmp_path) is False


def test_corrupt_regime_degrades_leash_to_1(tmp_path):
    """A corrupt regime artifact makes the whole tilt fail safe to leash 1.0."""
    (tmp_path / "regime").mkdir()
    (tmp_path / "regime" / "latest.json").write_text("garbage")
    ti = _tilt_inputs(bear=pb._bear_from_regime(tmp_path))  # bear=True
    hd, st = pb._compute_stage_tilt("AAA", "2026-07-01", ti)
    assert st["leash"] == 1.0
    assert hd == 45
    assert st["bear_gate"] is True


# ---------------------------------------------------------------------------
# 3. Anti-veto / anti-rank pin — selection identical tilt-on vs tilt-off.
# ---------------------------------------------------------------------------
def _standouts():
    return {
        "as_of": "2026-07-02",
        "gate_go": False,
        "buy": [
            {"ticker": "AAA", "dir": "up", "conviction": {"score": 80, "band": "high"},
             "entry_signal": {"act_level": 3, "spot": 100.0}},
            {"ticker": "BBB", "dir": "up", "conviction": {"score": 70, "band": "high"},
             "entry_signal": {"act_level": 2, "spot": 50.0}},
            {"ticker": "CCC", "dir": "up", "conviction": {"score": 65, "band": "neutral"},
             "entry_signal": {"act_level": 2, "spot": 25.0}},
        ],
    }


def test_selection_ids_and_order_unaffected_by_tilt():
    """select_candidates is a pure function of standouts — the tilt runs strictly
    after it and cannot change the selected id set or order (the anti-veto invariant).

    We prove it two ways: (a) select_candidates ignores any tilt state entirely;
    (b) originate_plans emits the SAME plan ids in the SAME order whether every pick
    is forced tilt-eligible (leash 1.25) or forced ineligible (leash 1.0)."""
    standouts = _standouts()
    sel = pb.select_candidates(standouts, n=pb.N_CANDIDATES)
    baseline_order = [b["ticker"] for b in sel]
    assert baseline_order == ["AAA", "BBB", "CCC"]  # score desc, act_level desc

    def _run(force_eligible: bool, monkeypatch_target):
        # Force the tilt path through one branch by stubbing _load_stage_tilt_inputs
        # and _compute_stage_tilt determinism.
        import unittest.mock as um
        ti = _tilt_inputs(stage=(2 if force_eligible else 1))
        with um.patch.object(pb, "_load_stage_tilt_inputs", return_value=ti), \
             um.patch.object(pb, "_load_price_history", return_value=None), \
             um.patch.object(pb, "compute_geometry", return_value={
                 "invalidation": 90.0, "t1": 110.0, "t2": 130.0, "r_unit": 10.0}), \
             um.patch.object(pb, "resolve_option", return_value=None):
            sp = _standouts_path(monkeypatch_target)
            return pb.originate_plans(sp, asof="2026-07-02", existing_ids=set(),
                                      thetadata_store=None)

    # write standouts to two temp files (fresh existing_ids each run)
    import tempfile
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        on = _run(True, d1)
        off = _run(False, d2)

    on_ids = [p["id"] for p in on]
    off_ids = [p["id"] for p in off]
    assert on_ids == off_ids, "tilt changed the selected id set/order (anti-veto violated)"
    # sanity: the two runs really did take different leash branches
    on_leash = {p["id"]: p["stage_tilt"]["leash"] for p in on}
    off_leash = {p["id"]: p["stage_tilt"]["leash"] for p in off}
    assert set(on_leash.values()) == {1.25}
    assert set(off_leash.values()) == {1.0}


def _standouts_path(dirpath) -> Path:
    p = Path(dirpath) / "us_standouts.json"
    p.write_text(json.dumps(_standouts()))
    return p


# ---------------------------------------------------------------------------
# 4. Degrade-to-1.0 on EC-table load failure and stage-classify exception.
# ---------------------------------------------------------------------------
def test_ec_table_load_failure_degrades_to_1():
    """ec_load_ok=False (EC table unreadable) -> not eligible -> leash 1.0, no raise."""
    hd, st = pb._compute_stage_tilt("AAA", "2026-07-01", _tilt_inputs(ec_load_ok=False))
    assert st["leash"] == 1.0
    assert hd == 45
    assert st["eligible"] is False


def test_stage_classify_exception_degrades_to_1():
    """A raising stage_at_entry -> leash 1.0, no raise out of _compute_stage_tilt."""
    ti = _tilt_inputs()

    def _boom(*a, **k):
        raise RuntimeError("classify blew up")

    ti["psf"].stage_at_entry = staticmethod(_boom)
    hd, st = pb._compute_stage_tilt("AAA", "2026-07-01", ti)
    assert st["leash"] == 1.0
    assert hd == 45
    assert st["stage_at_entry"] is None


def test_ticker_prices_missing_degrades_to_1():
    """No price series -> stage None -> not eligible -> leash 1.0."""
    ti = _tilt_inputs()
    ti["psf"].load_ticker_prices = staticmethod(lambda t, r: (None, None))
    hd, st = pb._compute_stage_tilt("AAA", "2026-07-01", ti)
    assert st["leash"] == 1.0
    assert st["stage_at_entry"] is None


# ---------------------------------------------------------------------------
# 5. Horizon propagation — management tau, ledger EXPIRED, option expiry.
# ---------------------------------------------------------------------------
def test_option_expiry_respects_scaled_horizon(tmp_path):
    """resolve_option's min_expiry = signal + horizon_days + 15d — a longer horizon
    pushes the min expiry date later. No store -> None, but the min-date arithmetic
    is what the design pins; assert via _next_monthly_expiry on both horizons."""
    sig = "2026-07-01"
    from datetime import date, timedelta
    base_min = date.fromisoformat(sig) + timedelta(days=45 + 15)
    tilt_min = date.fromisoformat(sig) + timedelta(days=56 + 15)
    assert tilt_min > base_min
    exp_base = pb._next_monthly_expiry(base_min)
    exp_tilt = pb._next_monthly_expiry(tilt_min)
    assert exp_tilt >= exp_base
    # the 11-day push crosses at least into a later-or-equal monthly expiry
    assert exp_tilt >= tilt_min and exp_base >= base_min


def test_ledger_expired_fires_at_scaled_horizon():
    """_determine_outcome reads plan.horizon_days: a plan with horizon 56 must NOT
    expire at day 45 but MUST expire by day 56 (a flat series that never hits a target)."""
    import scripts.build_prophet as bp

    idx = pd.bdate_range("2026-07-02", periods=80)
    # flat closes that never reach any target and never breach invalidation
    ph = pd.DataFrame({"close": [100.0] * len(idx)}, index=idx)

    def _plan(hd):
        return {
            "direction": "BULL", "entry": 100.0, "invalidation": 80.0,
            "targets": [200.0, 300.0], "horizon_days": hd,
            "signal_date": "2026-07-02",
        }

    asof = idx[-1].date().isoformat()
    # horizon 45: EXPIRED with days_held >= 45
    o45, _, _, d45 = bp._determine_outcome(_plan(45), ph, asof)
    assert o45 == "EXPIRED"
    assert d45 is not None and d45 >= 45
    # horizon 56: EXPIRED but strictly later than the 45-day close
    o56, _, _, d56 = bp._determine_outcome(_plan(56), ph, asof)
    assert o56 == "EXPIRED"
    assert d56 is not None and d56 >= 56
    assert d56 > d45, "the scaled horizon must delay the EXPIRED close vs the 45-day plan"


# ---------------------------------------------------------------------------
# 6. Ledger row schema unchanged (12 keys).
# ---------------------------------------------------------------------------
def test_ledger_row_schema_still_12_keys():
    """The tilt writes NOTHING to the prophet ledger — the 12-key row is untouched."""
    required = {
        "schema", "id", "asset", "direction", "signal_date", "close_date",
        "outcome", "stock_result_pct", "option_result_pct", "days_held",
        "plan_adherence", "asof",
    }
    assert len(required) == 12
    # A plan carrying stage_tilt must not leak that key into a ledger row: the row
    # builder in build_prophet.advance_ledger only projects the 12 fixed keys.
    import scripts.build_prophet as bp
    import inspect
    src = inspect.getsource(bp.advance_ledger)
    assert '"stage_tilt"' not in src, "stage_tilt must never appear in a ledger row"


# ---------------------------------------------------------------------------
# 7. stage_tilt present in plan JSON + index projection; no 'validated'.
# ---------------------------------------------------------------------------
def test_stage_tilt_present_in_plan_and_no_validated():
    """A plan dict from _compute_stage_tilt carries the full stage_tilt block with
    plain-word EN and no 'validated' token."""
    _hd, st = pb._compute_stage_tilt("AAA", "2026-07-01", _tilt_inputs())
    expected_keys = {
        "leash", "eligible", "stage_at_entry", "ec_sent", "ec_call_date",
        "bear_gate", "provisional", "demoted", "basis",
    }
    assert set(st.keys()) == expected_keys
    blob = json.dumps(st).lower()
    assert "validated" not in blob


def test_index_projection_includes_stage_tilt():
    """The driver's active_entries projection whitelists stage_tilt + horizon_days."""
    import scripts.build_prophet as bp
    import inspect
    src = inspect.getsource(bp.main)
    assert '"stage_tilt": plan.get("stage_tilt")' in src
    assert '"horizon_days": plan.get("horizon_days")' in src


# ---------------------------------------------------------------------------
# 8. Auto-demote — synthetic summary.json.
# ---------------------------------------------------------------------------
def _write_summary(tmp_path, n_stage2_ec, diff):
    d = tmp_path / "prophet_stage_shadow"
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.json").write_text(json.dumps({
        "schema": "prophet_stage_shadow.v1",
        "median_tilt": {
            "median_fwd_ret_126": {"stage2_ec": 1.0, "rest": 1.0},
            "diff": diff,
            "n_matured_126": {"stage2_ec": n_stage2_ec, "rest": 50},
        },
    }))


def test_auto_demote_fires_when_floor_met_and_diff_nonpositive(tmp_path):
    _write_summary(tmp_path, n_stage2_ec=30, diff=0.0)
    assert pb._stage_tilt_demoted(tmp_path) is True
    _write_summary(tmp_path, n_stage2_ec=40, diff=-5.0)
    assert pb._stage_tilt_demoted(tmp_path) is True


def test_auto_demote_not_fired_below_floor(tmp_path):
    _write_summary(tmp_path, n_stage2_ec=29, diff=-5.0)
    assert pb._stage_tilt_demoted(tmp_path) is False


def test_auto_demote_not_fired_when_diff_positive(tmp_path):
    _write_summary(tmp_path, n_stage2_ec=100, diff=3.2)
    assert pb._stage_tilt_demoted(tmp_path) is False


def test_auto_demote_absent_summary_is_active(tmp_path):
    assert pb._stage_tilt_demoted(tmp_path) is False


def test_demoted_forces_leash_1_in_compute():
    """When demoted, an otherwise-eligible pick is forced to leash 1.0 + demoted:true."""
    hd, st = pb._compute_stage_tilt("AAA", "2026-07-01", _tilt_inputs(demoted=True))
    assert st["leash"] == 1.0
    assert hd == 45
    assert st["demoted"] is True
    assert st["eligible"] is True  # eligibility is measured BEFORE the demote gate


# ---------------------------------------------------------------------------
# 9. Shadow median_tilt emission — schema, nulls, context-only pins intact.
# ---------------------------------------------------------------------------
def _shadow_row(pid, asset, stage, ec_sent, fwd126):
    return {
        "schema": pss.LEDGER_SCHEMA, "id": pid, "asset": asset,
        "direction": "BULL", "signal_date": "2021-02-24",
        "stage_at_entry": stage,
        "last_ec": ({"sent": ec_sent, "call_date": "2021-01-01"} if ec_sent is not None else None),
        "fwd": ({"fwd_ret_126": fwd126} if fwd126 is not None else {}),
    }


def test_median_tilt_schema_and_split(tmp_path):
    """median_tilt: matured-126 stage2∩EC vs rest medians + diff + per-side n."""
    rows = {
        # stage2 ∩ EC>=24, matured -> stage2_ec cohort (returns 10, 20 -> median 15)
        "A-BULL-1": _shadow_row("A-BULL-1", "A", pss.STAGE2, 30.0, 10.0),
        "B-BULL-1": _shadow_row("B-BULL-1", "B", pss.STAGE2, 40.0, 20.0),
        # stage2 but EC below gate -> rest (returns 4)
        "C-BULL-1": _shadow_row("C-BULL-1", "C", pss.STAGE2, 10.0, 4.0),
        # stage1 with EC>=24 -> rest (returns 6) -> rest median = (4,6) = 5
        "D-BULL-1": _shadow_row("D-BULL-1", "D", 1, 30.0, 6.0),
        # unmatured (no fwd_ret_126) -> excluded from both
        "E-BULL-1": _shadow_row("E-BULL-1", "E", pss.STAGE2, 30.0, None),
    }
    pss._write_ledger(tmp_path, rows)
    s = pss.summarize(root=tmp_path)

    mt = s["median_tilt"]
    assert mt["n_matured_126"]["stage2_ec"] == 2
    assert mt["n_matured_126"]["rest"] == 2
    assert mt["median_fwd_ret_126"]["stage2_ec"] == pytest.approx(15.0)
    assert mt["median_fwd_ret_126"]["rest"] == pytest.approx(5.0)
    assert mt["diff"] == pytest.approx(10.0)


def test_median_tilt_nulls_when_unmatured(tmp_path):
    """With nothing matured, medians + diff are null (nulls printed, not fabricated)."""
    rows = {
        "A-BULL-1": _shadow_row("A-BULL-1", "A", pss.STAGE2, 30.0, None),
        "B-BULL-1": _shadow_row("B-BULL-1", "B", 1, None, None),
    }
    pss._write_ledger(tmp_path, rows)
    s = pss.summarize(root=tmp_path)
    mt = s["median_tilt"]
    assert mt["n_matured_126"]["stage2_ec"] == 0
    assert mt["n_matured_126"]["rest"] == 0
    assert mt["median_fwd_ret_126"]["stage2_ec"] is None
    assert mt["median_fwd_ret_126"]["rest"] is None
    assert mt["diff"] is None


def test_median_tilt_keeps_context_only_pins(tmp_path):
    """Adding median_tilt must not break the is_context_only / display_only / no-verb /
    no-'validated' pins the shadow summary already carries."""
    rows = {"A-BULL-1": _shadow_row("A-BULL-1", "A", pss.STAGE2, 30.0, 10.0)}
    pss._write_ledger(tmp_path, rows)
    s = pss.summarize(root=tmp_path)
    assert s["is_context_only"] is True
    assert s["display_only"] is True
    assert s["authority_tier"] == "display"
    blob = json.dumps(s).lower()
    assert "validated" not in blob
    for verb in (" buy ", " sell ", " short "):
        assert verb not in blob
