"""Acceptance suite for scripts/build_cycle_pattern_ft_phase0.py (PREREGISTRATION.md §12).

Guards (task step 3):
  (a) frozen-block guard — the feature-block lists in the runner match §12 EXACTLY.
  (b) embargo guard — panel truncation to date<2024-01-01 on a synthetic frame.
  (c) sync formula — matches append_sync_gauge._compute_sync to 1e-9 on synthetic positions.
  (d) breadth positive-control — known SMA relationships on a tiny synthetic tape universe.
  (e) gate math delegates to fit_cycle_hazard functions (import identity + behavioral).
  (f) --smoke completes on the real panel if present (data-guarded) WITHOUT writing artifacts.
  (g) fit_cycle_hazard's own tests still pass (asserted via the refactor being behavior-safe;
      the suite is run in CI — this test asserts the refactored signature is backward-compatible).

Pure numpy/pandas. Tests write only to tmp paths (house rule: nothing under
data/cycle_pattern/ft_trials/ in this phase).
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(_REPO))

import scripts.build_cycle_pattern_ft_phase0 as ft  # noqa: E402
import scripts.fit_cycle_hazard as hz  # noqa: E402
from scripts.append_sync_gauge import _compute_sync  # noqa: E402

_RUNNER = _REPO / "scripts/build_cycle_pattern_ft_phase0.py"
_PANEL = _REPO / "data/hazard/panel_price_c4414dcb.parquet"


# ─────────────────────────────────────────────────────────────────────────────
# (a) Frozen-block guard — feature lists match §12 verbatim
# ─────────────────────────────────────────────────────────────────────────────

# The EXACT lists as written in PREREGISTRATION.md §12 (independently transcribed here so a
# silent edit to the runner constants trips this test).
PREREG_FT1 = ["fam_pct_above_200d", "fam_pct_above_50d", "breadth_div_own", "breadth_thrust_3m"]
PREREG_FT4 = ["sync_family", "phase_breadth_late", "phase_breadth_early", "pos_dispersion"]


def _parse_module_list(name: str) -> list[str]:
    """Parse a module-level list constant from the runner SOURCE via AST (not import), so
    the guard reads the frozen literal even if a future import-time mutation drifted it."""
    tree = ast.parse(_RUNNER.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return [ast.literal_eval(e) for e in node.value.elts]
    raise AssertionError(f"module constant {name} not found")


def test_frozen_ft1_block_matches_prereg():
    src_list = _parse_module_list("FT1_BREADTH_BLOCK")
    assert src_list == PREREG_FT1, f"FT1 block drifted from §12: {src_list}"
    assert ft.FT1_BREADTH_BLOCK == PREREG_FT1, "imported FT1 constant drifted"


def test_frozen_ft4_block_matches_prereg():
    src_list = _parse_module_list("FT4_STRUCTURE_BLOCK")
    assert src_list == PREREG_FT4, f"FT4 block drifted from §12: {src_list}"
    assert ft.FT4_STRUCTURE_BLOCK == PREREG_FT4, "imported FT4 constant drifted"


def test_trial_budget_is_twelve():
    """§12: 12 cells (2 blocks × 2 directions × 3 horizons), family rf.cycle_pattern.ft_v0."""
    assert ft.N_TRIALS == 12
    assert ft.FAMILY == "rf.cycle_pattern.ft_v0"
    assert len(ft.FT1_BREADTH_BLOCK) == 4 and len(ft.FT4_STRUCTURE_BLOCK) == 4
    assert 2 * 2 * len(hz.HORIZONS) == ft.N_TRIALS


# ─────────────────────────────────────────────────────────────────────────────
# (b) Embargo guard — truncation to date<2024-01-01
# ─────────────────────────────────────────────────────────────────────────────

def test_embargo_truncation_excludes_2024_onward():
    dates = pd.to_datetime(
        ["2009-06-30", "2023-12-31", "2024-01-01", "2024-06-30", "2025-01-31"]
    )
    frame = pd.DataFrame({"date": dates, "family": "us_sector", "id": "XLB", "x": 1.0})
    out = ft.truncate_embargo(frame)
    assert out["date"].max() < ft.EMBARGO_DATE, "row on/after 2024-01-01 survived embargo"
    assert (out["date"] < pd.Timestamp("2024-01-01")).all()
    # 2023-12-31 kept; 2024-01-01 (boundary) and later dropped
    assert pd.Timestamp("2023-12-31") in set(out["date"])
    assert pd.Timestamp("2024-01-01") not in set(out["date"])
    assert len(out) == 2


def test_embargo_date_constant_is_frozen():
    assert ft.EMBARGO_DATE == pd.Timestamp("2024-01-01")


# ─────────────────────────────────────────────────────────────────────────────
# (c) sync_family formula matches append_sync_gauge reference to 1e-9
# ─────────────────────────────────────────────────────────────────────────────

def test_sync_matches_append_sync_gauge_reference():
    rng = np.random.default_rng(11)
    for _ in range(50):
        n = rng.integers(3, 40)
        pos = rng.uniform(0, 100, size=n)
        assert abs(ft._sync_R(pos) - _compute_sync(pos)) < 1e-9, "sync formula drifted from reference"


def test_sync_edge_cases():
    # All identical positions → perfectly synced → R == 1.
    assert abs(ft._sync_R(np.full(8, 42.0)) - 1.0) < 1e-9
    assert abs(_compute_sync(np.full(8, 42.0)) - 1.0) < 1e-9
    # Antipodal pair (0 and 50 → angles 0 and π) → cancels → R == 0.
    assert ft._sync_R(np.array([0.0, 50.0])) < 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# (d) breadth positive-control on a tiny synthetic tape universe
# ─────────────────────────────────────────────────────────────────────────────

def _write_tape(path: Path, dates, closes, price_col="close_price"):
    df = pd.DataFrame({price_col: closes}, index=pd.to_datetime(dates))
    df.index.name = "Date"
    df.to_parquet(path)


def test_breadth_positive_control(tmp_path, monkeypatch):
    """Two synthetic yahoo members with KNOWN SMA relationships at a chosen month-end:
    one strictly rising (close > SMA → above), one strictly falling (close < SMA → below).
    fam_pct_above should therefore be exactly 0.5."""
    yahoo = tmp_path / "yahoo"
    yahoo.mkdir()
    # 400 trading-ish days so both 50d and 200d SMAs are defined.
    days = pd.bdate_range("2018-01-01", periods=400)
    # Member A: monotonically rising → last close is above both SMAs (SMA lags a rising series).
    rising = np.linspace(10.0, 50.0, len(days))
    # Member B: monotonically falling → last close is below both SMAs.
    falling = np.linspace(50.0, 10.0, len(days))
    _write_tape(yahoo / "XLB.parquet", days, rising)
    _write_tape(yahoo / "XLC.parquet", days, falling)

    # Restrict the universe to these two members for us_sector.
    monkeypatch.setattr(ft, "FAMILY_MEMBERS", {"us_sector": ["XLB", "XLC"]})

    t = days[-1]
    bf = ft.compute_family_breadth("us_sector", [t], yahoo, tmp_path / "cn_absent")
    row = bf.iloc[0]
    assert row["n_members_200d"] == 2, "both members should have a defined 200d SMA at t"
    assert row["n_members_50d"] == 2
    assert abs(row["fam_pct_above_200d"] - 0.5) < 1e-9, "one up, one down → 0.5 above-200d"
    assert abs(row["fam_pct_above_50d"] - 0.5) < 1e-9

    # PIT guard: at an EARLY month-end (before 200d of history) the 200d SMA is undefined,
    # so those members drop out of the 200d denominator (never counted as 'below').
    t_early = days[60]   # only ~60 bars of history
    bf_early = ft.compute_family_breadth("us_sector", [t_early], yahoo, tmp_path / "cn_absent")
    assert bf_early.iloc[0]["n_members_200d"] == 0, "200d SMA must be undefined at 60 bars"


def test_breadth_all_above(tmp_path, monkeypatch):
    yahoo = tmp_path / "yahoo"
    yahoo.mkdir()
    days = pd.bdate_range("2018-01-01", periods=400)
    for tkr in ["XLB", "XLC", "XLE"]:
        _write_tape(yahoo / f"{tkr}.parquet", days, np.linspace(10.0, 80.0, len(days)))
    monkeypatch.setattr(ft, "FAMILY_MEMBERS", {"us_sector": ["XLB", "XLC", "XLE"]})
    t = days[-1]
    bf = ft.compute_family_breadth("us_sector", [t], yahoo, tmp_path / "none")
    assert abs(bf.iloc[0]["fam_pct_above_200d"] - 1.0) < 1e-9, "all rising → 100% above"


# ─────────────────────────────────────────────────────────────────────────────
# (e) gate math delegates to fit_cycle_hazard (import identity + behavioral)
# ─────────────────────────────────────────────────────────────────────────────

def test_gate_delegates_to_fit_cycle_hazard():
    # Import identity: the runner reuses the harness objects, does not redefine them.
    assert ft.month_block_brier_gap_ci is hz.month_block_brier_gap_ci
    assert ft.bh_fdr is hz.bh_fdr
    assert ft._boot_pvalue is hz._boot_pvalue
    assert ft._brier is hz._brier
    assert ft.walk_forward is hz.walk_forward
    assert ft.build_design is hz.build_design
    assert ft.compound_model is hz.compound_model


def test_cell_gate_positive_when_block_strictly_better():
    """Behavioral: a base+block that predicts y perfectly must beat a base at the base rate —
    ΔBrier(base − block) CI must be entirely above 0 (block adds skill)."""
    rng = np.random.default_rng(4)
    months = pd.date_range("2010-01", "2023-12", freq="ME")
    dates, y, base, block = [], [], [], []
    br = 0.3
    for m in months:
        for _ in range(20):
            yi = int(rng.uniform() < br)
            dates.append(m); y.append(float(yi))
            base.append(br)                       # base = base rate (uninformative)
            block.append(0.98 if yi else 0.02)    # block near-perfect
    years = pd.to_datetime(pd.Series(dates)).dt.year.to_numpy()
    cell = ft._cell_gate(np.array(dates, dtype="datetime64[ns]"),
                         np.array(y), np.array(base), np.array(block), years)
    assert cell["ci_excludes_zero"], f"strong block must clear CI: {cell['ci90']}"
    assert cell["delta_brier"] > 0
    assert cell["sign_stable"], "perfect block must be sign-stable across years"


def test_cell_gate_fails_when_block_no_better():
    rng = np.random.default_rng(5)
    months = pd.date_range("2010-01", "2023-12", freq="ME")
    dates, y, base, block = [], [], [], []
    br = 0.3
    for m in months:
        for _ in range(20):
            yi = int(rng.uniform() < br)
            dates.append(m); y.append(float(yi))
            base.append(br)
            block.append(br + rng.normal() * 1e-6)   # identical to base (noise)
    years = pd.to_datetime(pd.Series(dates)).dt.year.to_numpy()
    cell = ft._cell_gate(np.array(dates, dtype="datetime64[ns]"),
                         np.array(y), np.array(base), np.array(block), years)
    assert not cell["ci_excludes_zero"], f"null block must NOT clear CI: {cell['ci90']}"


def test_joint_bh_fdr_across_twelve_cells():
    """The runner applies BH-FDR JOINTLY across all 12 cells (both blocks = one family).
    A synthetic p-vector of 3 tiny + 9 large must reject only the tiny ones under q=0.10."""
    pvals = [0.001, 0.005, 0.02] + [0.5] * 9
    rej = ft.bh_fdr(pvals, q=0.10)
    assert rej[0] and rej[1], "smallest p-values must survive BH"
    assert not any(rej[3:]), "large p-values must not survive"


# ─────────────────────────────────────────────────────────────────────────────
# (f) --smoke completes on the real panel WITHOUT writing real artifacts
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _PANEL.exists(), reason="real panel not present in this checkout")
def test_smoke_completes_without_writing_artifacts(tmp_path):
    ft_trials = _REPO / "data/cycle_pattern/ft_trials"
    before = set(ft_trials.glob("*.json")) if ft_trials.exists() else set()
    prod_ledger = _REPO / "data/trial_ledger.jsonl"
    prod_before = prod_ledger.read_bytes() if prod_ledger.exists() else b""

    proc = subprocess.run(
        [sys.executable, str(_RUNNER), "--smoke"],
        cwd=str(_REPO), capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, f"smoke failed:\n{proc.stdout}\n{proc.stderr}"
    assert "CANDIDATE COUNT" in proc.stdout, "anti-mining candidate count not printed"
    # candidate count printed BEFORE the first per-cell verdict line in the log
    ci = proc.stdout.index("CANDIDATE COUNT")
    verdict_pos = proc.stdout.find("verdict=")
    if verdict_pos != -1:
        assert ci < verdict_pos, "candidate count must print BEFORE any evaluation"

    # No real artifact written
    after = set(ft_trials.glob("*.json")) if ft_trials.exists() else set()
    assert after == before, "smoke must NOT write ft_trials artifacts"
    # Production ledger untouched (smoke routes the declaration to a scratch temp path)
    prod_after = prod_ledger.read_bytes() if prod_ledger.exists() else b""
    assert prod_after == prod_before, "smoke must NOT append to the production trial ledger"
    # (byte-equality above is the leak check; the family MAY legitimately exist in the
    # ledger once the real run has declared it — do not assert absence)


# ─────────────────────────────────────────────────────────────────────────────
# (g) fit_cycle_hazard's own tests still pass after the walk_forward refactor
# ─────────────────────────────────────────────────────────────────────────────

def test_walk_forward_default_signature_unchanged():
    """The refactor added keyword-only design/cont_features/l2_exempt with global defaults.
    The W4.2 call walk_forward(panel, 'up') must still work identically (2 positional args)."""
    import inspect
    sig = inspect.signature(hz.walk_forward)
    params = list(sig.parameters)
    assert params[:2] == ["panel_d", "direction"], "positional prefix changed"
    # new params are keyword-only with default None (global fallback → identical behavior)
    for p in ("design", "cont_features", "l2_exempt"):
        assert sig.parameters[p].default is None
        assert sig.parameters[p].kind == inspect.Parameter.KEYWORD_ONLY


def test_fit_cycle_hazard_suite_still_green():
    """Run the harness's own acceptance suite — the refactor must keep it byte-clean."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_cycle_hazard_fit.py", "-q"],
        cwd=str(_REPO), capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, f"fit_cycle_hazard suite broke:\n{proc.stdout}\n{proc.stderr}"
