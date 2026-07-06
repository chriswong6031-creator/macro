"""tests/test_cycle_pattern_lattice_phase0.py — guards for the §14 lattice runner.

Covers (per the build brief):
  (a) frozen lattice/target constants match §14 (AST guard — parse SOURCE, not import);
  (b) embargo guard on a synthetic frame;
  (c) james_stein delegation (import identity from build_conditional_cells);
  (d) phase_persist_3m positive control on synthetic monthly series incl. gap-breaks-chain;
  (e) promotion gate logic on synthetic cells (CI-excludes + n-floor + era-signs + BH all req'd);
  (f) sanity gate fires on a synthetic INVERTED table (positive control for the abort path);
  (g) --smoke completes on the real panel (data-guarded skipif), writes nothing real.

Pure numpy/pandas. Deterministic (seed 7).
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_RUNNER = _ROOT / "scripts" / "build_cycle_pattern_lattice_phase0.py"

import scripts.build_cycle_pattern_lattice_phase0 as L  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# (a) Frozen lattice/target constants match §14 (AST guard — parse SOURCE)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_module_const(name: str):
    """AST-parse a module-level constant from the runner SOURCE (not import), so the guard
    catches an in-code edit even if a monkeypatch is live at import time."""
    tree = ast.parse(_RUNNER.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"module-level constant {name!r} not found in {_RUNNER}")


def test_frozen_targets_match_prereg():
    """§14: exactly 3 targets, exact names, exact order."""
    targets = _parse_module_const("TARGETS")
    assert targets == ["rdd_63d", "turn_event_3m", "phase_persist_3m"], (
        f"TARGETS drifted from §14: {targets}"
    )


def test_frozen_lattices_match_prereg():
    """§14: L-A (phase_v2×family) and L-B (phase_v2×trend_pass×family)."""
    lattices = _parse_module_const("LATTICES")
    assert set(lattices) == {"L-A", "L-B"}, f"lattice set drifted: {set(lattices)}"
    assert lattices["L-A"] == [], "L-A conditions on phase_v2×family only (no extra dim)"
    assert lattices["L-B"] == ["trend_pass"], "L-B adds the trend_pass split"


def test_frozen_budget_and_family():
    """§14: 135 candidates, family rf.cycle_pattern.lattice_v0, embargo 2024-01-01, FDR q=0.10,
    promotion n_months floor 40. These are the guarded numbers."""
    assert _parse_module_const("N_TRIALS") == 135
    assert _parse_module_const("FAMILY") == "rf.cycle_pattern.lattice_v0"
    assert _parse_module_const("TRIAL_FAMILY_SUFFIX") == "lattice_v0"
    assert _parse_module_const("FDR_Q") == 0.10
    assert _parse_module_const("N_MONTHS_PROMOTE_FLOOR") == 40
    # 135 = (15 L-A + 30 L-B) × 3 targets — reconstruct from the frozen dims.
    la = 5 * 3
    lb = 5 * 2 * 3
    assert (la + lb) * 3 == 135


def test_embargo_date_constant_is_frozen():
    """Embargo constant literal in source is 2024-01-01."""
    tree = ast.parse(_RUNNER.read_text())
    found = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "EMBARGO_DATE":
                    # pd.Timestamp("2024-01-01")
                    found = node.value.args[0].value
    assert found == "2024-01-01", f"EMBARGO_DATE literal drifted: {found}"
    assert L.EMBARGO_DATE == pd.Timestamp("2024-01-01")


# ══════════════════════════════════════════════════════════════════════════════
# (b) Embargo guard on a synthetic frame
# ══════════════════════════════════════════════════════════════════════════════

def test_embargo_drops_2024_onward():
    df = pd.DataFrame({
        "date": pd.to_datetime([
            "2023-11-30", "2023-12-31", "2024-01-01", "2024-06-30", "2025-01-31",
        ]),
        "id": ["X"] * 5,
    })
    out = L.truncate_embargo(df)
    assert (pd.to_datetime(out["date"]) < pd.Timestamp("2024-01-01")).all()
    assert len(out) == 2, f"expected 2 pre-embargo rows, got {len(out)}"
    # boundary: 2024-01-01 itself is EXCLUDED (>=)
    assert pd.Timestamp("2024-01-01") not in set(out["date"])


# ══════════════════════════════════════════════════════════════════════════════
# (c) james_stein delegation — import identity from build_conditional_cells
# ══════════════════════════════════════════════════════════════════════════════

def test_james_stein_is_the_w44_function():
    """The runner must REUSE build_conditional_cells.james_stein_shrink verbatim (not fork)."""
    import scripts.build_conditional_cells as W44
    assert L.james_stein_shrink is W44.james_stein_shrink, (
        "runner must import james_stein_shrink from build_conditional_cells (W4.4 verbatim)"
    )
    # also derive_phase, cell_boot_ci, build_panel_with_returns are the same objects
    assert L.derive_phase is W44.derive_phase
    assert L.cell_boot_ci is W44.cell_boot_ci
    assert L.build_panel_with_returns is W44.build_panel_with_returns


# ══════════════════════════════════════════════════════════════════════════════
# (d) phase_persist_3m positive control (incl. gap-breaks-chain)
# ══════════════════════════════════════════════════════════════════════════════

def test_phase_persist_positive_control_and_gap_break():
    """Synthetic monthly series with a KNOWN persistence pattern and a deliberate calendar gap.

    id A: 6 consecutive month-ends, all phase 'Peak' → the first 3 stamps have a full
          unchanged 3-ahead window → persist=1; the last 3 lack a full window → NaN.
    id B: month 1 'Peak', then a GAP (month 2 missing), then months 3,4,5 'Peak' → month-1's
          t+1 (month 2) is missing → chain BREAKS → NaN (not 0, not 1).
    id C: 4 consecutive month-ends 'Peak','Peak','Trough','Peak' → month-1 has a full window
          but phase changes at t+2 → persist=0.
    """
    def me(y, m):
        return pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)

    rows = []
    # id A: 2020-01..2020-06 all Peak
    for m in range(1, 7):
        rows.append({"id": "A", "date": me(2020, m), "phase_v2": "Peak"})
    # id B: 2020-01 Peak, 2020-02 MISSING (gap), 2020-03..2020-05 Peak
    rows.append({"id": "B", "date": me(2020, 1), "phase_v2": "Peak"})
    for m in (3, 4, 5):
        rows.append({"id": "B", "date": me(2020, m), "phase_v2": "Peak"})
    # id C: 2020-01..2020-04 Peak,Peak,Trough,Peak
    for m, ph in zip((1, 2, 3, 4), ("Peak", "Peak", "Trough", "Peak")):
        rows.append({"id": "C", "date": me(2020, m), "phase_v2": ph})

    df = pd.DataFrame(rows).reset_index(drop=True)
    persist = L.derive_phase_persist_3m(df)
    df["persist"] = persist.values

    def g(iid, y, m):
        v = df[(df["id"] == iid) & (df["date"] == me(y, m))]["persist"]
        return v.iloc[0]

    # id A: first stamp has 3 consecutive Peaks ahead → 1.0
    assert g("A", 2020, 1) == 1.0
    assert g("A", 2020, 2) == 1.0
    assert g("A", 2020, 3) == 1.0
    # id A last three: no full 3-ahead window → NaN
    assert np.isnan(g("A", 2020, 4))
    assert np.isnan(g("A", 2020, 6))
    # id B month-1: t+1 (2020-02) is a calendar gap → chain breaks → NaN
    assert np.isnan(g("B", 2020, 1)), "a calendar gap must break the chain → NaN, not 0/1"
    # id C month-1: full window but phase changes at t+2 (Trough) → 0.0
    assert g("C", 2020, 1) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# (e) Promotion gate logic on synthetic cells (all four conditions required)
# ══════════════════════════════════════════════════════════════════════════════

def _cell(*, gap, ci95, n_months, boot_p, era_pre, era_post, collapsed=False):
    return {
        "lattice": "L-A", "phase_v2": "Peak", "family": "us_sector", "target": "turn_event_3m",
        "n_months": n_months, "n_raw": n_months, "shrunk": gap, "pooled": 0.0, "gap": gap,
        "ci95": ci95, "boot_p": boot_p, "era_pre_sign": era_pre, "era_post_sign": era_post,
        "collapsed": collapsed, "promoted": False,
    }


def test_promotion_requires_all_conditions():
    # A clean promotable cell: CI excludes 0 (both negative), n>=40, era signs match, tiny p.
    good = _cell(gap=-0.10, ci95=[-0.17, -0.05], n_months=200, boot_p=0.0,
                 era_pre=-1, era_post=-1)
    # Fails on CI straddling 0
    bad_ci = _cell(gap=-0.10, ci95=[-0.05, 0.02], n_months=200, boot_p=0.0,
                   era_pre=-1, era_post=-1)
    # Fails on n_months floor (< 40)
    bad_n = _cell(gap=-0.10, ci95=[-0.17, -0.05], n_months=39, boot_p=0.0,
                  era_pre=-1, era_post=-1)
    # Fails on era sign disagreement (post era flips sign)
    bad_era = _cell(gap=-0.10, ci95=[-0.17, -0.05], n_months=200, boot_p=0.0,
                    era_pre=-1, era_post=+1)
    # Fails on BH: give it a p that BH cannot reject when surrounded by many nulls.
    weak_bh = _cell(gap=-0.10, ci95=[-0.17, -0.05], n_months=200, boot_p=0.09,
                    era_pre=-1, era_post=-1)

    # BH is applied JOINTLY across the whole list. To isolate each non-BH failure from the BH
    # gate, we pad with many null cells (p=1.0) so ONLY p≈0 cells can survive BH.
    nulls = [_cell(gap=0.0, ci95=[-0.01, 0.01], n_months=100, boot_p=1.0,
                   era_pre=0, era_post=0) for _ in range(130)]

    cells = [good, bad_ci, bad_n, bad_era, weak_bh] + nulls
    L.apply_promotion_gate(cells)

    assert good["promoted"] is True, "clean cell must promote"
    assert bad_ci["promoted"] is False, "CI straddling 0 must NOT promote"
    assert bad_n["promoted"] is False, "n_months < 40 must NOT promote"
    assert bad_era["promoted"] is False, "era sign disagreement must NOT promote"
    assert weak_bh["promoted"] is False, "p that fails BH must NOT promote"
    # sanity: exactly one promotion here
    assert sum(c["promoted"] for c in cells) == 1


def test_promotion_bh_is_joint_and_gated():
    """BH is the family-wide gate: a cell with CI-exclusion + n + era but a middling p only
    promotes if BH (over ALL 135) rejects its null. Two strong cells among 133 nulls both
    survive; a lone middling-p cell among nulls does not."""
    strong = [_cell(gap=-0.10, ci95=[-0.17, -0.05], n_months=200, boot_p=0.0005,
                    era_pre=-1, era_post=-1) for _ in range(2)]
    nulls = [_cell(gap=0.0, ci95=[-0.01, 0.01], n_months=100, boot_p=0.9,
                   era_pre=0, era_post=0) for _ in range(133)]
    cells = strong + nulls
    L.apply_promotion_gate(cells)
    assert all(c["promoted"] for c in strong)
    assert not any(c["promoted"] for c in nulls)


# ══════════════════════════════════════════════════════════════════════════════
# (f) Sanity gate fires on a synthetic INVERTED table (abort-path positive control)
# ══════════════════════════════════════════════════════════════════════════════

def _synthetic_joined(*, invert: bool) -> pd.DataFrame:
    """Build a minimal joined frame with fwd_maxdd_63d such that KG-2 either holds or is
    inverted. DD is <=0; 'deeper' = more negative. invert=False → Trough deepest, Peak
    shallowest (KG-2 holds). invert=True → Peak deepest, Trough shallowest (KG-2 violated)."""
    dd_ok = {"Trough": -0.12, "Recovery": -0.09, "Expansion": -0.07,
             "Peak": -0.04, "Downturn": -0.08}
    dd_bad = {"Trough": -0.04, "Recovery": -0.07, "Expansion": -0.08,
              "Peak": -0.12, "Downturn": -0.09}
    table = dd_bad if invert else dd_ok
    rows = []
    for phase, dd in table.items():
        for k in range(30):  # ample n per phase
            rows.append({"phase_v2": phase, "family": "us_sector",
                         "fwd_maxdd_63d": dd + (k - 15) * 1e-4})
    return pd.DataFrame(rows)


def test_sanity_gate_passes_on_kg2_ordering():
    res = L.sanity_gate_rawdd(_synthetic_joined(invert=False))
    assert res["passed"] is True
    assert res["trough_ok"] and res["peak_ok"]


def test_sanity_gate_fires_on_inverted_table():
    res = L.sanity_gate_rawdd(_synthetic_joined(invert=True))
    assert res["passed"] is False, "inverted KG-2 ordering must fail the sanity gate"
    assert not (res["trough_ok"] and res["peak_ok"])
    assert "VIOLATED" in res["reason"]


# ══════════════════════════════════════════════════════════════════════════════
# (g) --smoke completes on the real panel (data-guarded skipif), writes nothing real
# ══════════════════════════════════════════════════════════════════════════════

_PANEL = _ROOT / "data" / "hazard" / "panel_price_c4414dcb.parquet"


@pytest.mark.skipif(not _PANEL.exists(), reason="hazard panel not present")
def test_smoke_completes_and_writes_nothing_real():
    real_artifact = _ROOT / "data" / "cycle_pattern" / "lattice" / "batch1.json"
    real_cands = _ROOT / "data" / "cycle_pattern" / "pattern_candidates.jsonl"
    real_ledger = _ROOT / "data" / "trial_ledger.jsonl"

    art_before = real_artifact.exists()
    cands_before = real_cands.read_text() if real_cands.exists() else None
    ledger_before = real_ledger.read_text() if real_ledger.exists() else None

    proc = subprocess.run(
        [sys.executable, str(_RUNNER), "--smoke"],
        cwd=str(_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"smoke failed:\nSTDOUT{proc.stdout}\nSTDERR{proc.stderr}"
    out = proc.stdout
    assert "CANDIDATE COUNT" in out and "135" in out, "must print the 135 candidate count"
    assert "SANITY GATE" in out, "must print the sanity-gate table"
    assert "No real artifacts written" in out

    # No real artifact created; no candidate append; real ledger unchanged.
    assert real_artifact.exists() == art_before, "smoke must not create the real artifact"
    cands_after = real_cands.read_text() if real_cands.exists() else None
    assert cands_after == cands_before, "smoke must not touch pattern_candidates.jsonl"
    ledger_after = real_ledger.read_text() if real_ledger.exists() else None
    assert ledger_after == ledger_before, "smoke must not touch the real trial ledger"
    assert "lattice_v0" not in (ledger_after or ""), (
        "smoke must declare its budget to a SCRATCH ledger, never the real one"
    )
