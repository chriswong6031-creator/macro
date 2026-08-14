"""Tests for scripts/grade_cortex_attention.py — the cortex attention grader.

Pins the two W3 adversarial-review defects (PR #5679) and the null/miss split
they exposed:

  1. DIRECTION COERCION.  `int(claim.get("direction") or 1)` mapped direction=0
     onto +1, so every salience flag was graded as a long call on signed
     excess-vs-SPY.  24 of the 25 live firings are direction=0.
  2. FALSIFIER ROUTING.  Naked substring matching put 12 of 24 real rows in
     'unknown' and — worse — produced four realized_move classifications that
     were pure substring accidents: "move" inside "REmove attention if ..."
     (3 rows) and "return" inside "if the radar RETURNS below caution" (1 row).
  3. NULL vs MISS.  Every criterion the grader could not evaluate was written as
     outcome_hit=False, a fabricated miss that both understated the hit rate and
     inflated n — a one-way ratchet against ever clearing the Article-3 gate.

Every test is hermetic (tmp_path roots, synthetic prices), so the file runs in a
sparse worktree without data/ checked out.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from scripts import grade_cortex_attention as g


# ---------------------------------------------------------------------------
# Live falsifier strings, verbatim from data/reflexes/cortex_attention/firings.jsonl.
# These are the exact strings the substring router mis-classified.  They are
# inlined rather than read from data/ so the test is hermetic and so the strings
# that actually broke are pinned even if the ledger is later compacted.
# ---------------------------------------------------------------------------

# Matched "move" inside "Remove" → graded as a long price bet on a macro scope.
LIVE_REMOVE_FALSIFIERS = [
    "Remove attention if China exits Q3 into Q1/Q2 with non-contracting liquidity "
    "and participation no longer reads forced_deleveraging for three consecutive "
    "sessions; otherwise review the thesis by its 2026-08-06 check date.",
    "Remove attention if the 10-year real yield falls at least 20bp from 2.41% and "
    "the curve ceases bear-steepening; retain if real yield reaches or exceeds "
    "2.50% while bear-steepening persists.",
    "Remove attention if HY OAS widens above 3.25% or rises at least 40bp over 20 "
    "sessions with credit stress confirmation; retain for thesis review if OAS "
    "remains below 3.00% and rates-credit health remains above 75 through the "
    "2026-08-14 check date.",
]

# Matched "return" inside "returns below caution" — a state transition, not a price return.
LIVE_RADAR_RETURNS_FALSIFIER = (
    "Close the flag if the radar's matured caution-state 21-day pullback rate rises "
    "above its unconditional base rate with at least 25 graded caution observations, "
    "or if the radar returns below caution for five consecutive sessions."
)

LIVE_STATE_FALSIFIER = (
    "Clear the attention item if cross-asset confirmation rises above 70% agreement "
    "for three consecutive sessions while the equity regime remains Q1; retain it if "
    "agreement stays at or below 50% or the equity regime exits Q1."
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BARS = 400
H = 5


def _mkroot(tmp_path):
    root = tmp_path / "repo"
    (root / "data" / "yahoo").mkdir(parents=True)
    (root / "data" / "reflexes" / "cortex_attention").mkdir(parents=True)
    return root


def _index(n=BARS):
    return pd.bdate_range("2023-01-02", periods=n)


def _write_prices(root, symbol, series):
    pd.DataFrame({"close": series}).to_parquet(root / "data" / "yahoo" / f"{symbol}.parquet")


def _flat_spy(n=BARS):
    """SPY held constant so that excess-vs-SPY equals the symbol's own return exactly."""
    return pd.Series(100.0, index=_index(n))


def _noisy(seed=0, n=BARS, sigma=0.005, jumps=None):
    """A stationary price series with optional controlled single-bar log-returns."""
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0, sigma, n)
    r[0] = 0.0
    for pos, val in (jumps or {}).items():
        r[pos] = val
    return pd.Series(100 * np.exp(np.cumsum(r)), index=_index(n))


def _controlled(seed, asof_pos=300, simple_ret=0.15, horizon=H, n=BARS, sigma=0.005):
    """Series whose graded window realises EXACTLY `simple_ret` against a flat SPY.

    forward_metrics fills at bar asof_pos+1 and exits at asof_pos+1+horizon, so the
    window return is the product of log-returns on bars (asof_pos+2 .. asof_pos+1+H).
    Those bars are zeroed and one carries log1p(simple_ret) — giving an exact simple
    return, which is what lets the sign-symmetry test compare +x against -x honestly.
    """
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0, sigma, n)
    r[0] = 0.0
    lo, hi = asof_pos + 2, asof_pos + 1 + horizon
    r[lo:hi + 1] = 0.0
    r[lo] = np.log1p(simple_ret)
    return pd.Series(100 * np.exp(np.cumsum(r)), index=_index(n))


def _write_claims(root, claims):
    p = root / "data" / "reflexes" / "cortex_attention" / "firings.jsonl"
    p.write_text("\n".join(json.dumps(c) for c in claims) + "\n", encoding="utf-8")


def _grade(root, today=date(2026, 8, 14)):
    return g.grade_attention(
        root=root, today=today, now=datetime(2026, 8, 14, tzinfo=timezone.utc)
    )


def _rows(root):
    p = root / "data" / "reflexes" / "cortex_attention" / "grades.jsonl"
    return {
        json.loads(line)["claim_id"]: json.loads(line)
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _claim(cid, asof, direction=0, symbol="XYZ", horizon=H, falsifier="XYZ moves >2% within the window"):
    return {
        "claim_id": cid,
        "asof": asof,
        "horizon_d": horizon,
        "direction": direction,
        "scope_key": symbol,
        "falsifier": falsifier,
    }


def _asof(pos):
    return _index()[pos].date().isoformat()


# ---------------------------------------------------------------------------
# Defect 1 — direction coercion
# ---------------------------------------------------------------------------

def test_the_old_coercion_expression_really_did_map_zero_to_long():
    """Anti-vacuity control: document the exact defect this file guards against.

    If this ever stops holding, the tests below are pinning nothing.
    """
    assert int(0 or 1) == 1          # the pre-W3 expression, on a direction=0 claim
    assert g._claim_direction({"direction": 0}) == 0


@pytest.mark.parametrize("raw,expected", [
    (0, 0), (1, 1), (-1, -1), (None, 0), ("", 0), ("2", 2), ("junk", 0),
])
def test_claim_direction_never_invents_a_direction(raw, expected):
    assert g._claim_direction({"direction": raw}) == expected


def test_missing_direction_field_is_zero_not_long():
    assert g._claim_direction({}) == 0


def test_direction_zero_is_graded_on_magnitude_not_sign(tmp_path):
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", _flat_spy())
    _write_prices(root, "XYZ", _noisy(seed=1, jumps={302: 0.15}))
    _write_claims(root, [_claim("c", _asof(300))])
    _grade(root)

    row = _rows(root)["c"]
    assert row["direction"] == 0, "the claim's own direction must survive into the ledger"
    assert row["outcome_detail"]["criterion"] == "abs_excess_vs_placebo"
    assert row["base_rate"] == g._MAGNITUDE_BASE_RATE
    assert "abs_excess" in row["outcome_detail"]


def test_direction_zero_hits_on_a_large_DOWN_move(tmp_path):
    """THE regression. A big adverse move is attention WELL SPENT on a salience flag.

    Under the coerced-to-long grader this scored a miss: excess < 0 with an
    assumed direction of +1.
    """
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", _flat_spy())
    _write_prices(root, "XYZ", _noisy(seed=2, jumps={302: -0.15}))
    _write_claims(root, [_claim("down", _asof(300))])
    _grade(root)

    row = _rows(root)["down"]
    detail = row["outcome_detail"]
    assert detail["excess"] < 0, "fixture must actually produce a negative excess"
    assert row["outcome_hit"] is True, "a large DOWN move must hit a direction-0 claim"
    # And the old rule would have said otherwise, which is the whole point:
    assert (detail["excess"] > 0) is False


def test_direction_zero_is_sign_symmetric(tmp_path):
    """Equal-magnitude up and down moves must grade identically."""
    out = {}
    for name, ret in (("up", 0.15), ("down", -0.15)):
        root = _mkroot(tmp_path / name)
        _write_prices(root, "SPY", _flat_spy())
        _write_prices(root, "XYZ", _controlled(seed=3, simple_ret=ret))
        _write_claims(root, [_claim(name, _asof(300))])
        _grade(root)
        out[name] = _rows(root)[name]

    assert out["up"]["outcome_hit"] == out["down"]["outcome_hit"] is True
    assert out["up"]["outcome_detail"]["excess"] == pytest.approx(0.15, abs=1e-4)
    assert out["down"]["outcome_detail"]["excess"] == pytest.approx(-0.15, abs=1e-4)
    assert out["up"]["outcome_detail"]["abs_excess"] == pytest.approx(
        out["down"]["outcome_detail"]["abs_excess"], abs=1e-9
    ), "an up move and an equal-sized down move must grade identically"


def test_direction_zero_quiet_window_is_a_real_miss_not_a_null(tmp_path):
    """A small move is an evaluated MISS — the grader must not null out to avoid scoring."""
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", _flat_spy())
    # No jump: the window is ordinary, so |excess| sits below the 70th pctile.
    _write_prices(root, "XYZ", _noisy(seed=4, jumps={301: 0.0, 302: 0.0, 303: 0.0,
                                                     304: 0.0, 305: 0.0, 306: 0.0}))
    _write_claims(root, [_claim("quiet", _asof(300))])
    _grade(root)

    row = _rows(root)["quiet"]
    assert row["outcome_hit"] is False
    assert row["gradeable"] is True
    assert row["outcome_detail"]["abs_excess"] < row["outcome_detail"]["threshold"]


def test_directional_claims_still_grade_on_signed_excess(tmp_path):
    """direction != 0 keeps the signed criterion and the 0.5 binary prior."""
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", _flat_spy())
    _write_prices(root, "XYZ", _noisy(seed=5, jumps={302: 0.15}))
    _write_claims(root, [
        _claim("long", _asof(300), direction=1),
        _claim("short", _asof(300), direction=-1),
    ])
    _grade(root)

    rows = _rows(root)
    for cid in ("long", "short"):
        assert rows[cid]["outcome_detail"]["criterion"] == "signed_excess_vs_spy"
        assert rows[cid]["base_rate"] == g._BASE_RATE_DEFAULT
    assert rows["long"]["outcome_hit"] is True     # up move, long call
    assert rows["short"]["outcome_hit"] is False   # up move, short call


# ---------------------------------------------------------------------------
# The placebo / base rate
# ---------------------------------------------------------------------------

def test_magnitude_base_rate_is_one_minus_q_by_construction():
    assert g._MAGNITUDE_BASE_RATE == pytest.approx(1.0 - g._MAGNITUDE_Q)


def test_placebo_threshold_is_calibrated_to_its_declared_base_rate(tmp_path):
    """On a no-signal series the hit rate must land near 1 - _MAGNITUDE_Q.

    This is what makes the reported base_rate honest: the A2 lift test divides by
    it, so a threshold that fires at a different rate than it claims would corrupt
    the gate in whichever direction the mismatch ran.
    """
    n = 1200
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", pd.Series(100.0, index=_index(n)))
    _write_prices(root, "XYZ", _noisy(seed=11, n=n))

    # Non-overlapping asofs so the samples are close to independent.
    positions = list(range(300, n - (H + 2), H + 1))
    _write_claims(root, [_claim(f"c{p}", _index(n)[p].date().isoformat()) for p in positions])
    _grade(root)

    rows = [r for r in _rows(root).values() if r["gradeable"]]
    assert len(rows) >= 100, "need a real sample to say anything about calibration"
    rate = sum(1 for r in rows if r["outcome_hit"]) / len(rows)
    assert rate == pytest.approx(g._MAGNITUDE_BASE_RATE, abs=0.10), (
        f"hit rate {rate:.3f} strays from the declared base rate "
        f"{g._MAGNITUDE_BASE_RATE} — the reported base_rate would be a lie"
    )


def test_placebo_never_looks_ahead(tmp_path):
    """Prices after the claim's own window must not move the threshold."""
    asof_pos = 300
    thresholds = []
    for name, tail_jump in (("base", 0.0), ("mutated", 0.25)):
        root = _mkroot(tmp_path / name)
        _write_prices(root, "SPY", _flat_spy())
        # Mutate strictly AFTER the realized window closes (entry 301, exit 306).
        jumps = {302: 0.15}
        if tail_jump:
            jumps.update({p: tail_jump for p in range(310, 340)})
        _write_prices(root, "XYZ", _noisy(seed=6, jumps=jumps))
        _write_claims(root, [_claim("c", _asof(asof_pos))])
        _grade(root)
        thresholds.append(_rows(root)["c"]["outcome_detail"]["threshold"])

    assert thresholds[0] == pytest.approx(thresholds[1], rel=1e-12), (
        "threshold moved when only post-window prices changed — the placebo is "
        "peeking at data the claim could not have seen"
    )


def test_placebo_window_count_grows_with_available_history(tmp_path):
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", _flat_spy())
    _write_prices(root, "XYZ", _noisy(seed=7))
    _write_claims(root, [_claim("early", _asof(150)), _claim("late", _asof(350))])
    _grade(root)

    rows = _rows(root)
    assert rows["early"]["outcome_detail"]["placebo_n"] < rows["late"]["outcome_detail"]["placebo_n"]


def test_thin_history_is_a_null_not_a_guessed_threshold(tmp_path):
    """Fewer than _MIN_PLACEBO_N closed windows must refuse to mint a threshold."""
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", _flat_spy())
    _write_prices(root, "XYZ", _noisy(seed=8))
    _write_claims(root, [_claim("thin", _asof(20))])
    _grade(root)

    row = _rows(root)["thin"]
    assert row["outcome_hit"] is None
    assert row["gradeable"] is False
    assert "magnitude threshold" in row["outcome_detail"]["ungradeable_reason"]


# ---------------------------------------------------------------------------
# Defect 2 — falsifier routing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("falsifier", LIVE_REMOVE_FALSIFIERS)
def test_remove_attention_is_not_a_realized_move_claim(falsifier):
    """'REmove' must not match 'move'. Three live rows were graded as price bets."""
    cls = g._classify({"falsifier": falsifier, "direction": 0}, None)
    assert cls["class"] != "realized_move"
    assert "realized_move" not in cls["families"]


def test_radar_returns_is_not_a_realized_move_claim():
    """'returns below caution' is a state transition, not a price return."""
    cls = g._classify({"falsifier": LIVE_RADAR_RETURNS_FALSIFIER, "direction": 0}, None)
    assert "verdict_change" in cls["families"]
    # It also names a 'pullback rate', so it is compound — and compound is a null.
    assert cls["compound"] is True


@pytest.mark.parametrize("word", ["removed", "removes", "removal", "unmoved"])
def test_no_substring_of_a_longer_word_routes_to_realized_move(word):
    cls = g._classify({"falsifier": f"The item is {word} when the criterion clears.",
                       "direction": 0}, None)
    assert "realized_move" not in cls["families"]


@pytest.mark.parametrize("falsifier", [
    "SYNTHETIC moves >2% within 5 days",
    "Clear if the name outperforms SPY by at least 5% over 20 trading days",
    "Retain if the name underperforms its sector by 3%",
    "Close if a 10% drawdown occurs within the horizon",
    "Close if the excess return exceeds 4%",
])
def test_genuine_price_language_still_routes_to_realized_move(falsifier):
    cls = g._classify({"falsifier": falsifier, "direction": 0}, None)
    assert "realized_move" in cls["families"]


def test_state_language_routes_to_verdict_change():
    cls = g._classify({"falsifier": LIVE_STATE_FALSIFIER, "direction": 0}, None)
    assert cls["class"] == "verdict_change"
    assert cls["compound"] is False


def test_regime_quadrant_without_the_word_regime_is_still_state():
    cls = g._classify(
        {"falsifier": "Remove attention if China exits Q3 into Q1/Q2.", "direction": 0}, None
    )
    assert cls["class"] == "verdict_change"


def test_compound_falsifier_is_flagged(tmp_path):
    cls = g._classify({
        "falsifier": "Treat the conflict as resolved only if China exits Q3 and FXI "
                     "outperforms SPY by at least 5% over a fresh 20-day window.",
        "direction": 0,
    }, None)
    assert cls["compound"] is True
    assert set(cls["families"]) == {"realized_move", "verdict_change"}


def test_compound_falsifier_grades_as_a_disclosed_null(tmp_path):
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", _flat_spy())
    _write_prices(root, "XYZ", _noisy(seed=9, jumps={302: 0.15}))
    _write_claims(root, [_claim(
        "compound", _asof(300),
        falsifier="Clear the flag only if the regime exits Q3 and XYZ outperforms SPY by 5%.",
    )])
    _grade(root)

    row = _rows(root)["compound"]
    assert row["outcome_hit"] is None
    assert "compound falsifier" in row["outcome_detail"]["ungradeable_reason"]


def test_unrecognised_falsifier_is_a_null_with_a_reason(tmp_path):
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", _flat_spy())
    _write_claims(root, [_claim(
        "meta", _asof(300), symbol="cortex_attention_calibration",
        falsifier="Do not infer attention skill until at least 25 graded firings exist.",
    )])
    _grade(root)

    row = _rows(root)["meta"]
    assert row["falsifier_class"] == "unknown"
    assert row["outcome_hit"] is None
    assert row["outcome_detail"]["ungradeable_reason"]


def test_scope_that_is_not_a_ticker_is_never_handed_to_the_price_grader(tmp_path):
    """The live corpus is all scope_type='macro'; those names are not symbols."""
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", _flat_spy())
    assert g._price_symbol({"scope_key": "Open Long-Treasuries overweight theses"}, root) is None
    assert g._price_symbol({"scope_key": "SPY"}, root) == "SPY"


def test_detect_falsifier_class_wrapper_agrees_with_classify():
    claim = {"falsifier": LIVE_STATE_FALSIFIER, "direction": 0}
    assert g._detect_falsifier_class(claim) == g._classify(claim, None)["class"]


# ---------------------------------------------------------------------------
# Defect 3 — nulls are not misses
# ---------------------------------------------------------------------------

def test_macro_scope_direction_zero_is_null_not_miss(tmp_path):
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", _flat_spy())
    _write_claims(root, [_claim(
        "macro", _asof(300), symbol="Open Long-Treasuries overweight theses",
        falsifier=LIVE_STATE_FALSIFIER,
    )])
    summary = _grade(root)

    row = _rows(root)["macro"]
    assert row["outcome_hit"] is None
    assert row["gradeable"] is False
    assert summary["new_nulls"] == 1


def test_verdict_change_with_direction_zero_is_null(tmp_path):
    root = _mkroot(tmp_path)
    hit, detail = g._grade_verdict_change(
        {"scope_key": "x", "direction": 0, "asof": "2026-08-01", "horizon_d": 5},
        root, date(2026, 8, 14),
    )
    assert hit is None
    assert "world_state history" in detail["ungradeable_reason"]


def test_escalation_with_no_dated_artifacts_is_null(tmp_path):
    root = _mkroot(tmp_path)
    alerts = root / "data" / "alerts"
    alerts.mkdir(parents=True)
    # Undated store files — exactly what data/alerts/ holds today.
    (alerts / "rule_scorecard.json").write_text("{}", encoding="utf-8")
    (alerts / "watchlist_sentinel_states.json").write_text("{}", encoding="utf-8")

    hit, detail = g._grade_escalation(
        {"scope_key": "XYZ", "direction": 0, "asof": "2026-08-01", "horizon_d": 5},
        root, date(2026, 8, 14),
    )
    assert hit is None
    assert detail["dated_alert_files"] == 0


def test_escalation_absence_in_a_live_store_is_a_real_miss(tmp_path):
    root = _mkroot(tmp_path)
    alerts = root / "data" / "alerts"
    alerts.mkdir(parents=True)
    (alerts / "2026-08-03.json").write_text(
        json.dumps({"date": "2026-08-03", "symbols": ["OTHER"]}), encoding="utf-8"
    )

    hit, detail = g._grade_escalation(
        {"scope_key": "XYZ", "direction": 0, "asof": "2026-08-01", "horizon_d": 5},
        root, date(2026, 8, 14),
    )
    assert hit is False, "a dated store that simply lacks the symbol is a genuine miss"
    assert detail["dated_alert_files"] == 1


def test_escalation_finds_a_matching_alert_in_window(tmp_path):
    root = _mkroot(tmp_path)
    alerts = root / "data" / "alerts"
    alerts.mkdir(parents=True)
    (alerts / "2026-08-03.json").write_text(
        json.dumps({"date": "2026-08-03", "symbols": ["XYZ"]}), encoding="utf-8"
    )

    hit, _ = g._grade_escalation(
        {"scope_key": "XYZ", "direction": 0, "asof": "2026-08-01", "horizon_d": 5},
        root, date(2026, 8, 14),
    )
    assert hit is True


# ---------------------------------------------------------------------------
# A2 earn-in
# ---------------------------------------------------------------------------

def _grades(*specs):
    """specs: (outcome_hit, base_rate) tuples."""
    return [
        {"claim_id": f"c{i}", "graded_at": "2026-08-14", "outcome_hit": hit, "base_rate": br}
        for i, (hit, br) in enumerate(specs)
    ]


def test_nulls_are_excluded_from_the_earn_in_denominator(tmp_path):
    root = _mkroot(tmp_path)
    probation = g.evaluate_a2_earn_in(
        _grades((True, 0.3), (False, 0.3), (None, 0.5), (None, 0.5)),
        root, dry_run=True, now=datetime(2026, 8, 14, tzinfo=timezone.utc),
    )
    rec = probation["attention_track_record"]
    assert rec["n"] == 2, "only gradeable rows may enter n"
    assert rec["hits"] == 1
    assert rec["ungradeable"] == 2
    assert rec["total_rows"] == 4


def test_earn_in_base_rate_is_the_mean_of_the_criteria_actually_applied(tmp_path):
    root = _mkroot(tmp_path)
    probation = g.evaluate_a2_earn_in(
        _grades((True, 0.3), (False, 0.3), (True, 0.5)),
        root, dry_run=True, now=datetime(2026, 8, 14, tzinfo=timezone.utc),
    )
    assert probation["attention_track_record"]["base_rate"] == pytest.approx(
        (0.3 + 0.3 + 0.5) / 3
    )


def test_an_all_null_record_does_not_manufacture_a_zero_hit_rate(tmp_path):
    """Before W3 this read n=4, hits=0 — evidence of failure that was never measured."""
    root = _mkroot(tmp_path)
    probation = g.evaluate_a2_earn_in(
        _grades((None, 0.5), (None, 0.5), (None, 0.5), (None, 0.5)),
        root, dry_run=True, now=datetime(2026, 8, 14, tzinfo=timezone.utc),
    )
    rec = probation["attention_track_record"]
    assert rec["n"] == 0 and rec["hits"] == 0 and rec["ungradeable"] == 4
    assert probation["granted"] is False
    assert "insufficient-n" in probation["reason"]


def test_probation_discloses_the_null_count(tmp_path):
    root = _mkroot(tmp_path)
    probation = g.evaluate_a2_earn_in(
        _grades((True, 0.3), (None, 0.5)),
        root, dry_run=True, now=datetime(2026, 8, 14, tzinfo=timezone.utc),
    )
    assert "ungradeable" in probation["attention_track_record"], (
        "nulls must be printed, not hidden"
    )


# ---------------------------------------------------------------------------
# Ledger shape
# ---------------------------------------------------------------------------

def test_grade_rows_carry_the_gradeable_flag_and_applied_base_rate(tmp_path):
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", _flat_spy())
    _write_prices(root, "XYZ", _noisy(seed=10, jumps={302: 0.15}))
    _write_claims(root, [
        _claim("mag", _asof(300)),
        _claim("macro", _asof(300), symbol="a macro thesis name",
               falsifier=LIVE_STATE_FALSIFIER),
    ])
    _grade(root)

    rows = _rows(root)
    assert rows["mag"]["gradeable"] is True
    assert rows["mag"]["base_rate"] == g._MAGNITUDE_BASE_RATE
    assert rows["macro"]["gradeable"] is False
    for row in rows.values():
        assert row["gradeable"] == (row["outcome_hit"] is not None)


def test_synthetic_rows_are_still_excluded(tmp_path):
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", _flat_spy())
    _write_claims(root, [{
        "claim_id": "syn", "asof": _asof(300), "horizon_d": H, "direction": 1,
        "scope_key": "SYNTHETIC_TICKER", "trigger_key": "SYNTHETIC_TICKER",
        "falsifier": "SYNTHETIC_TICKER moves >2% within 5 days (dry-run synthetic item)",
    }])
    summary = _grade(root)
    assert summary["total_firings"] == 0
    assert summary["new_grades"] == 0


def test_grader_version_was_bumped_past_the_defective_build():
    assert g._GRADER_VERSION != "W7b-PR2", (
        "rows graded by the fixed grader must be distinguishable from the "
        "direction-coerced ones already in the ledger"
    )
