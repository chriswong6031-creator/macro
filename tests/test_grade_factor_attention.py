"""Tests for scripts/grade_factor_attention.py — the factor attention grader.

Pins the latent direction-coercion defect (sibling of cortex PR #5693):

  1. DIRECTION COERCION.  ``int(claim.get("direction") or -1)`` mapped 0 / None
     / "" / absent onto -1, so a missing or direction-free claim would be
     graded as a SHORT on signed excess-vs-SPY.  The live producer always
     writes direction=-1; the ledger is empty (n=0), so this is latent.
  2. NULL vs MISS.  Unevaluable paths returned False, a fabricated miss that
     would inflate A2 n and understate the hit rate the first time the
     reflex fires.
  3. BASE RATE.  A flat 0.5 was written onto every grade row, including
     rows that were never graded on that criterion.

This reflex is a signed underperform-SPY bet.  It does NOT grow a magnitude
/ placebo path — that would invent a contract the producer never asked.
direction=0 / missing → disclosed null, excluded from the A2 denominator.

Every test is hermetic (tmp_path roots, synthetic prices), so the file runs
in a sparse worktree without data/ checked out.
"""
from __future__ import annotations

import ast
import inspect
import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts import grade_factor_attention as g


BARS = 400
H = 5
TODAY = date(2026, 8, 14)
NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mkroot(tmp_path):
    root = tmp_path / "repo"
    (root / "data" / "yahoo").mkdir(parents=True)
    (root / "data" / "reflexes" / "factor_attention").mkdir(parents=True)
    return root


def _index(n=BARS):
    return pd.bdate_range("2023-01-02", periods=n)


def _write_prices(root, symbol, series):
    pd.DataFrame({"close": series}).to_parquet(
        root / "data" / "yahoo" / f"{symbol}.parquet"
    )


def _flat_spy(n=BARS):
    """SPY held constant so excess-vs-SPY equals the symbol's own return."""
    return pd.Series(100.0, index=_index(n))


def _controlled(seed, asof_pos=300, simple_ret=0.15, horizon=H, n=BARS, sigma=0.005):
    """Series whose graded window realises EXACTLY `simple_ret` against a flat SPY.

    forward_metrics fills at bar asof_pos+1 and exits at asof_pos+1+horizon, so
    the window return is the product of log-returns on bars
    (asof_pos+2 .. asof_pos+1+H).  Those bars are zeroed and one carries
    log1p(simple_ret).
    """
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0, sigma, n)
    r[0] = 0.0
    lo, hi = asof_pos + 2, asof_pos + 1 + horizon
    r[lo:hi + 1] = 0.0
    r[lo] = np.log1p(simple_ret)
    return pd.Series(100 * np.exp(np.cumsum(r)), index=_index(n))


def _write_claims(root, claims):
    p = root / "data" / "reflexes" / "factor_attention" / "firings.jsonl"
    p.write_text("\n".join(json.dumps(c) for c in claims) + "\n", encoding="utf-8")


def _grade(root, today=TODAY):
    return g.grade_factor_attention(root=root, today=today, now=NOW)


def _rows(root):
    p = root / "data" / "reflexes" / "factor_attention" / "grades.jsonl"
    return {
        json.loads(line)["claim_id"]: json.loads(line)
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _claim(cid, asof, direction=-1, symbol="XYZ", horizon=H):
    return {
        "claim_id": cid,
        "asof": asof,
        "horizon_d": horizon,
        "direction": direction,
        "scope_key": symbol,
    }


def _asof(pos):
    return _index()[pos].date().isoformat()


def _priced_root(tmp_path, simple_ret=-0.10):
    root = _mkroot(tmp_path)
    _write_prices(root, "SPY", _flat_spy())
    _write_prices(root, "XYZ", _controlled(seed=1, simple_ret=simple_ret))
    return root


# ---------------------------------------------------------------------------
# Defect 1 — the old coercion, and that the new parser refuses it
# ---------------------------------------------------------------------------

def test_the_old_coercion_expression_really_did_map_zero_to_short():
    """Anti-vacuity control: document the exact defect this file guards against.

    If this ever stops holding, the tests below are pinning nothing.
    """
    assert int(0 or -1) == -1
    assert int(None or -1) == -1
    assert int("" or -1) == -1
    assert g._claim_direction({"direction": 0}) is None
    assert g._claim_direction({"direction": None}) is None
    assert g._claim_direction({"direction": ""}) is None
    assert g._claim_direction({}) is None


@pytest.mark.parametrize("raw,expected", [
    (-1, -1),
    (1, 1),
    ("-1", -1),
    ("1", 1),
    (0, None),
    (None, None),
    ("", None),
    ("junk", None),
    (2, None),
    (-2, None),
])
def test_claim_direction_never_invents_a_signed_bet(raw, expected):
    assert g._claim_direction({"direction": raw}) == expected


def test_missing_direction_field_is_null_not_short():
    assert g._claim_direction({}) is None


def test_source_has_no_executable_or_minus_one_coercion():
    """The docstring may name the defect; executable code must not recreate it."""
    src = Path(g.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "int"):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if not (isinstance(arg, ast.BoolOp) and isinstance(arg.op, ast.Or)):
            continue
        for term in arg.values:
            if isinstance(term, ast.UnaryOp) and isinstance(term.op, ast.USub):
                if isinstance(term.operand, ast.Constant) and term.operand.value == 1:
                    pytest.fail("executable int(... or -1) coercion reintroduced")
            if isinstance(term, ast.Constant) and term.value in (-1, 1):
                pytest.fail(
                    f"executable int(... or {term.value}) coercion reintroduced"
                )


def test_no_magnitude_path_was_imported_from_the_cortex_sibling():
    src = Path(g.__file__).read_text(encoding="utf-8")
    assert "_abs_excess_placebo" not in src
    assert "_MAGNITUDE" not in src
    assert "abs_excess" not in src


# ---------------------------------------------------------------------------
# Signed excess vs SPY — the live contract
# ---------------------------------------------------------------------------

def test_direction_minus_one_hits_when_name_underperforms_spy(tmp_path):
    root = _priced_root(tmp_path, simple_ret=-0.10)
    _write_claims(root, [_claim("short_hit", _asof(300), direction=-1)])
    _grade(root)

    row = _rows(root)["short_hit"]
    assert row["direction"] == -1
    assert row["outcome_detail"]["excess"] == pytest.approx(-0.10, abs=1e-4)
    assert row["outcome_hit"] is True
    assert row["base_rate"] == g._BASE_RATE_DEFAULT
    assert row["outcome_detail"]["criterion"] == "signed_excess_vs_spy"


def test_direction_minus_one_misses_when_name_outperforms_spy(tmp_path):
    root = _priced_root(tmp_path, simple_ret=0.10)
    _write_claims(root, [_claim("short_miss", _asof(300), direction=-1)])
    _grade(root)

    row = _rows(root)["short_miss"]
    assert row["outcome_detail"]["excess"] == pytest.approx(0.10, abs=1e-4)
    assert row["outcome_hit"] is False
    assert row["base_rate"] == g._BASE_RATE_DEFAULT


def test_direction_plus_one_hits_when_name_outperforms_spy(tmp_path):
    root = _priced_root(tmp_path, simple_ret=0.10)
    _write_claims(root, [_claim("long_hit", _asof(300), direction=1)])
    _grade(root)

    row = _rows(root)["long_hit"]
    assert row["direction"] == 1
    assert row["outcome_hit"] is True
    assert row["base_rate"] == g._BASE_RATE_DEFAULT


def test_direction_plus_one_misses_when_name_underperforms_spy(tmp_path):
    root = _priced_root(tmp_path, simple_ret=-0.10)
    _write_claims(root, [_claim("long_miss", _asof(300), direction=1)])
    _grade(root)

    assert _rows(root)["long_miss"]["outcome_hit"] is False


# ---------------------------------------------------------------------------
# Defect 1b — direction=0 / missing / blank are nulls, not SHORTs
# ---------------------------------------------------------------------------

def test_direction_zero_underperform_is_null_not_a_short_hit(tmp_path):
    """THE regression.  Name underperforms SPY, claim says direction=0.

    The old ``int(0 or -1)`` grader would score this a SHORT hit.  The new
    grader must disclose a null — 0 is not a signed bet, and this reflex
    does not have a magnitude path.
    """
    root = _priced_root(tmp_path, simple_ret=-0.10)
    _write_claims(root, [_claim("zero", _asof(300), direction=0)])
    _grade(root)

    row = _rows(root)["zero"]
    assert row["outcome_hit"] is None
    assert row["direction"] is None
    assert row["base_rate"] is None
    assert "ungradeable_reason" in row["outcome_detail"]
    assert "excess" not in row["outcome_detail"], (
        "a direction=0 row must not be run through signed-excess at all"
    )
    # The old expression would have treated this as a SHORT.  The underperform
    # fixture is load-bearing: restoring int(x or -1) turns this into a hit.
    assert int(0 or -1) == -1


@pytest.mark.parametrize("raw", [None, "", "junk"])
def test_unparseable_direction_is_null_even_when_excess_is_negative(tmp_path, raw):
    root = _priced_root(tmp_path, simple_ret=-0.10)
    claim = _claim("bad", _asof(300), direction=raw)
    _write_claims(root, [claim])
    _grade(root)

    row = _rows(root)["bad"]
    assert row["outcome_hit"] is None
    assert row["direction"] is None
    assert row["base_rate"] is None


def test_missing_direction_key_is_null(tmp_path):
    root = _priced_root(tmp_path, simple_ret=-0.10)
    claim = _claim("omit", _asof(300), direction=-1)
    del claim["direction"]
    _write_claims(root, [claim])
    _grade(root)

    row = _rows(root)["omit"]
    assert row["outcome_hit"] is None
    assert row["direction"] is None
    assert row["base_rate"] is None


# ---------------------------------------------------------------------------
# Defect 2 — unevaluable paths are nulls, not fabricated misses
# ---------------------------------------------------------------------------

def test_missing_symbol_is_null_not_false(tmp_path):
    root = _mkroot(tmp_path)
    hit, detail = g._grade_realized_move(
        {"direction": -1, "asof": "2023-01-02", "horizon_d": H, "scope_key": ""},
        root, TODAY,
    )
    assert hit is None
    assert "symbol" in detail["ungradeable_reason"] or "asof" in detail["ungradeable_reason"]


def test_no_price_data_is_null_not_false(tmp_path):
    root = _mkroot(tmp_path)
    hit, detail = g._grade_realized_move(
        {"direction": -1, "asof": _asof(300), "horizon_d": H, "scope_key": "XYZ"},
        root, TODAY,
    )
    assert hit is None
    assert "no price data" in detail["ungradeable_reason"]


def test_horizon_not_elapsed_is_null_not_false(tmp_path):
    """Calendar-matured claim whose trading-day window has not closed."""
    root = _mkroot(tmp_path)
    n = 320
    _write_prices(root, "SPY", _flat_spy(n))
    _write_prices(root, "XYZ", _controlled(seed=2, n=n, asof_pos=300, simple_ret=-0.10))
    # asof at 300, horizon 21 trading days, only 19 bars after fill → None
    hit, detail = g._grade_realized_move(
        {"direction": -1, "asof": _asof(300), "horizon_d": 21, "scope_key": "XYZ"},
        root, TODAY,
    )
    assert hit is None
    assert "not yet elapsed" in detail["ungradeable_reason"]


# ---------------------------------------------------------------------------
# Defect 3 — A2 n excludes nulls; 0.5 is not written onto null rows
# ---------------------------------------------------------------------------

def _grade_specs(*specs):
    """specs: (outcome_hit, base_rate) tuples."""
    return [
        {"claim_id": f"c{i}", "graded_at": "2026-08-14",
         "outcome_hit": hit, "base_rate": br}
        for i, (hit, br) in enumerate(specs)
    ]


def test_nulls_are_excluded_from_the_earn_in_denominator(tmp_path):
    root = _mkroot(tmp_path)
    probation = g._evaluate_a2_earn_in(
        _grade_specs((True, 0.5), (False, 0.5), (None, None), (None, None)),
        root, dry_run=True, now=NOW,
    )
    rec = probation["attention_track_record"]
    assert rec["n"] == 2, "only gradeable rows may enter n"
    assert rec["hits"] == 1
    assert rec["ungradeable"] == 2
    assert rec["base_rate"] == g._BASE_RATE_DEFAULT


def test_an_all_null_record_does_not_manufacture_a_zero_hit_rate(tmp_path):
    """Before the fix this read n=4, hits=0 — evidence of failure never measured."""
    root = _mkroot(tmp_path)
    probation = g._evaluate_a2_earn_in(
        _grade_specs((None, None), (None, None), (None, None), (None, None)),
        root, dry_run=True, now=NOW,
    )
    rec = probation["attention_track_record"]
    assert rec["n"] == 0 and rec["hits"] == 0 and rec["ungradeable"] == 4
    assert rec["base_rate"] is None
    assert probation["granted"] is False
    assert "insufficient-n" in probation["reason"]


def test_end_to_end_a2_n_excludes_direction_zero_and_unevaluable(tmp_path):
    root = _priced_root(tmp_path, simple_ret=-0.10)
    _write_prices(root, "ABC", _controlled(seed=3, asof_pos=280, simple_ret=0.10))
    _write_claims(root, [
        _claim("signed_hit", _asof(300), direction=-1),
        _claim("signed_miss", _asof(280), direction=-1, symbol="ABC"),
        _claim("zero", _asof(300), direction=0),
        _claim("missing_px", _asof(300), direction=-1, symbol="NOPE"),
    ])
    summary = _grade(root)

    rows = _rows(root)
    assert rows["signed_hit"]["outcome_hit"] is True
    assert rows["signed_miss"]["outcome_hit"] is False
    assert rows["zero"]["outcome_hit"] is None
    assert rows["missing_px"]["outcome_hit"] is None
    assert rows["zero"]["base_rate"] is None
    assert rows["missing_px"]["base_rate"] is None
    assert rows["signed_hit"]["base_rate"] == g._BASE_RATE_DEFAULT

    assert summary["a2_earn_in"]["n"] == 2
    assert summary["a2_earn_in"]["hits"] == 1


def test_grader_version_was_bumped_past_the_defective_build():
    assert g._GRADER_VERSION != "P1D-v1"


def test_claim_direction_is_the_only_parser():
    """A single Optional[int] helper is the whole direction contract."""
    src = inspect.getsource(g._grade_realized_move)
    assert "_claim_direction" in src
    assert "or -1" not in src
    src_loop = inspect.getsource(g.grade_factor_attention)
    assert "int(claim.get(\"direction\") or -1)" not in src_loop
    assert "int(claim.get('direction') or -1)" not in src_loop
