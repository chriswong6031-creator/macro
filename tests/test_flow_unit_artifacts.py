"""Flow-column unit-artifact detector/repair (collectors/edgar_flow_quality).

Synthetic panels only — no network, no committed-data reads.  Each fixture is a
minimal reconstruction of a defect class observed in the real panel (tickers in
comments), plus the confusable REAL patterns the detector must leave alone:
real COVID troughs (ABM, HOG), real subscription-transition troughs (ADSK cfo),
real breakeven years between losses (CWK), real sign-flip post-event (HOOD),
and broken-statements artefacts (BGC) where the panel is correct.

PIT honesty is pinned structurally: every repair value must equal the row's own
value × 10^k for k in {3, 6} — repairs never come from statements.parquet or
any other row.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from collectors.edgar_flow_quality import apply_flow_quality, detect, FLOW_COLS


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _panel(ticker: str, ni: list, fy0: int = 2018,
           revenue: list | None = None,
           assets: list | None = None,
           cfo: list | None = None,
           gross_profit: list | None = None,
           op_income: list | None = None,
           dividends: list | None = None,
           repurchases: list | None = None,
           ni_prior: list | None = None,
           col: str | None = None,
           col_vals: list | None = None) -> pd.DataFrame:
    """Build a minimal synthetic panel with the given ni series.

    Pass col/col_vals to set a non-ni column as the primary artifact.
    revenue defaults to ~$10B growing 5%/yr; assets ~$50B growing 5%/yr.
    """
    n = len(ni)
    rev = revenue if revenue is not None else [10e9 * 1.05 ** i for i in range(n)]
    ast = assets if assets is not None else [50e9 * 1.05 ** i for i in range(n)]
    rows = []
    for i in range(n):
        row: dict = {
            "ticker": ticker,
            "cik": 1,
            "fy": fy0 + i,
            "ni": float(ni[i]),
            "revenue": float(rev[i]) if (rev[i] is not None and not (isinstance(rev[i], float) and np.isnan(rev[i]))) else np.nan,
            "assets": float(ast[i]),
            "period_end": pd.Timestamp(f"{fy0 + i}-12-31"),
        }
        if cfo is not None:
            row["cfo"] = float(cfo[i])
        if gross_profit is not None:
            row["gross_profit"] = float(gross_profit[i])
        if op_income is not None:
            row["op_income"] = float(op_income[i])
        if dividends is not None:
            row["dividends"] = float(dividends[i])
        if repurchases is not None:
            row["repurchases"] = float(repurchases[i])
        if ni_prior is not None:
            row["ni_prior"] = float(ni_prior[i])
        if col is not None and col_vals is not None:
            row[col] = float(col_vals[i])
        rows.append(row)
    p = pd.DataFrame(rows)
    p["asof_date"] = p["period_end"] + pd.Timedelta(days=120)
    return p


def _statements(ticker: str, ni: list, fy0: int = 2018,
                revenue: list | None = None,
                cfo: list | None = None,
                op_income: list | None = None,
                gross_profit: list | None = None) -> pd.DataFrame:
    n = len(ni)
    rows = []
    for i in range(n):
        row: dict = {"ticker": ticker, "fy": fy0 + i,
                     "ni": float(ni[i]) if ni[i] is not None else np.nan}
        if revenue is not None:
            row["revenue"] = float(revenue[i])
        if cfo is not None:
            row["cfo"] = float(cfo[i])
        if op_income is not None:
            row["op_income"] = float(op_income[i])
        if gross_profit is not None:
            row["gross_profit"] = float(gross_profit[i])
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. ED class: ni ×1e3-low trailing rows, statements confirms → xsrc_scale
# ---------------------------------------------------------------------------
def test_ed_class_xsrc_repair_and_ni_prior_mirror():
    # ED fy2021-25: ni ~1.35-2.0e6 (thousands), real ~1.35-2.0e9
    # ni_prior of fy+1 row equals the raw ni → should be mirrored
    ni_panel = [1.003e9, 1.062e9, 1.141e9, 1.062e9, 1.193e9,
                1.346e6, 1.660e6, 2.519e6, 1.820e6, 2.023e6]
    ni_stmt  = [1.003e9, 1.062e9, 1.141e9, 1.062e9, 1.193e9,
                1.346e9, 1.660e9, 2.519e9, 1.820e9, 2.023e9]
    # ni_prior: fy2022 row contains prior=ni[fy2021]=1.346e6 (the raw artifact)
    ni_prior = [np.nan, 1.003e9, 1.062e9, 1.141e9, 1.062e9,
                1.193e9,   # fy2023: prior = fy2022 CLEAN → no mirror needed here
                1.346e6,   # fy2022 prior = fy2021 artifact → should be mirrored
                1.660e6,   # fy2023 prior = fy2022 artifact
                2.519e6,   # fy2024 prior = fy2023 artifact
                1.820e6]   # fy2025 prior = fy2024 artifact
    # Only fy2021's prior (in fy2022) matches the raw ni.  In this fixture we
    # set ni_prior for fy2022..2025 to the raw artifact values so mirroring fires.
    p = _panel("ED", ni_panel, fy0=2016, ni_prior=ni_prior,
               revenue=[12e9] * 10, assets=[60e9] * 10)
    st = _statements("ED", ni_stmt, fy0=2016,
                     revenue=[12e9] * 10)

    healed, audit = apply_flow_quality(p, statements=st)
    repaired_rows = healed[(healed.fy >= 2021) & (healed.fy <= 2025)]
    assert len(repaired_rows) == 5, "all 5 artifact rows should be repaired"
    # repairs must all be xsrc_scale
    assert all("xsrc_scale" in str(healed.at[i, "flow_flag"])
               for i in repaired_rows.index)
    # repaired values ≈ raw × 1e3
    for _, row in repaired_rows.iterrows():
        raw = healed.at[row.name, "ni_raw"]
        assert np.isfinite(raw), f"ni_raw missing for fy{row['fy']}"
        assert np.isclose(row["ni"], raw * 1e3, rtol=1e-6), \
            f"repair mismatch fy{row['fy']}: {row['ni']} vs {raw * 1e3}"

    # clean rows untouched
    clean_rows = healed[(healed.fy >= 2016) & (healed.fy <= 2020)]
    assert clean_rows["flow_flag"].isna().all() or \
           all(f is None for f in clean_rows["flow_flag"]), \
        "clean rows must not be flagged"

    # ni_prior mirror: fy2022's ni_prior was 1.346e6 (the artifact) → now 1.346e9
    fy2022_row = healed[healed.fy == 2022].iloc[0]
    assert np.isclose(fy2022_row["ni_prior"], 1.346e9, rtol=1e-4), \
        f"ni_prior not mirrored for fy2022: {fy2022_row['ni_prior']}"
    assert audit["mirrors"] > 0


# ---------------------------------------------------------------------------
# 2. ANET/GLPI class: ×1e6-low with statements → xsrc_scale x1e6
# ---------------------------------------------------------------------------
def test_anet_class_xsrc_x1e6_repair():
    # ANET fy2021-25: ni in 841..3511 (millions), real ~841M..3.5B
    ni_panel = [634.6e6, 841.0, 1352.0, 2087.0, 2852.0, 3511.0]
    ni_stmt  = [634.6e6, 841e6, 1352e6, 2087e6, 2852e6, 3511e6]
    p = _panel("ANET", ni_panel, fy0=2020, revenue=[3e9 * 1.3 ** i for i in range(6)],
               assets=[5e9 * 1.3 ** i for i in range(6)])
    st = _statements("ANET", ni_stmt, fy0=2020)

    healed, audit = apply_flow_quality(p, statements=st)
    art_rows = healed[healed.fy >= 2021]
    for _, row in art_rows.iterrows():
        assert np.isclose(row["ni"], row["ni_raw"] * 1e6, rtol=1e-6), \
            f"ANET fy{row['fy']}: expected x1e6 repair"
    assert audit["by_flag"].get("ni:xsrc_scale", 0) == 5


# ---------------------------------------------------------------------------
# 3. VC class: sign-waiver + fixed-point (flank_scale after round-1 xsrc repair)
# ---------------------------------------------------------------------------
def test_vc_class_fixed_point_and_sign_waiver():
    # VC-class: small raw value (|raw|<RAW_ABSURD) between a negative flank and a
    # positive repaired flank.  The sign-waiver must fire (negative left flank is
    # not a disqualifier when |raw|<RAW_ABSURD).  This also tests the fixed-point
    # loop: fy2022 is caught by xsrc in round 1, then fy2021=50 becomes flanked
    # by -56M (left) and 130M (right) and is caught by flank_scale in round 2.
    #
    # Synthetic values chosen so xsrc fires cleanly at k=6 (ratio ~1.000):
    ni_panel = [164e6, 70e6, -56e6,
                50.0,       # fy2021: artifact |raw|<RAW_ABSURD
                130.0]      # fy2022: artifact — xsrc catches this in round 1
    ni_stmt  = [np.nan, np.nan, np.nan,
                np.nan,     # fy2021: no statement coverage
                130e6]      # fy2022: ratio 130M/130=1000000 → k=6 band=1.0 ✓
    p = _panel("VC", ni_panel, fy0=2018,
               revenue=[2.8e9] * 5, assets=[2.2e9] * 5,
               cfo=[200e6, 180e6, 170e6, 60e6, 170e6])
    st = _statements("VC", ni_stmt, fy0=2018)

    healed, audit = apply_flow_quality(p, statements=st)
    # fy2022 must be repaired by xsrc in round 1
    fy2022 = healed[healed.fy == 2022].iloc[0]
    assert np.isclose(fy2022["ni_raw"], 130.0, rtol=1e-9), "fy2022 ni_raw should be 130"
    assert np.isclose(fy2022["ni"], 130e6, rtol=1e-6), "fy2022 ni should be 130M"

    # fy2021 must be repaired by flank_scale in round 2 (sign waiver: |raw|=50 < RAW_ABSURD)
    fy2021 = healed[healed.fy == 2021].iloc[0]
    assert np.isclose(fy2021["ni_raw"], 50.0, rtol=1e-9), "ni_raw should be 50"
    assert fy2021["ni"] > 1e6, f"fy2021 ni not repaired: {fy2021['ni']}"
    assert "flank_scale" in str(fy2021["flow_flag"]), \
        f"fy2021 should be flank_scale: {fy2021['flow_flag']}"

    # Clean rows untouched
    clean = healed[healed.fy <= 2020]
    assert all(f is None for f in clean["flow_flag"]), \
        "clean rows must not be flagged"


# ---------------------------------------------------------------------------
# 4. TECH/CRK/AIG class: interior single-row, no statements, flank_scale
#    Includes a negative-value case (AIG ni fy2018 = -6M between -6.084B/+3.348B)
# ---------------------------------------------------------------------------
def test_tech_class_interior_no_statements():
    # TECH op_income fy2013 = 158469 between ~163M and ~159M
    op_ok   = [150780000.0, 156328000.0, 163055000.0, 166209000.0]
    op_art  = [150780000.0, 156328000.0, 163055000.0, 166209000.0,
               158469.0,    159750000.0, 147023000.0]
    p = _panel("TECH", ni=[1e8] * 7, fy0=2009, op_income=op_art,
               revenue=[5e8 * 1.1 ** i for i in range(7)],
               assets=[1.2e8 * 1.1 ** i for i in range(7)])
    healed, audit = apply_flow_quality(p, statements=None)
    art_row = healed[healed.fy == 2013].iloc[0]
    assert np.isclose(art_row["op_income_raw"], 158469.0, rtol=1e-9), \
        "op_income_raw should preserve the artifact"
    assert np.isclose(art_row["op_income"], 158469.0 * 1e3, rtol=1e-4), \
        f"TECH op_income not x1e3 repaired: {art_row['op_income']}"
    assert "flank_scale" in str(art_row["flow_flag"])


def test_aig_class_negative_interior_flank():
    # AIG ni fy2018: panel = -6e6 between -6.084e9 (fy2017) and +3.348e9 (fy2019)
    # The ×1e3 scaled value = -6e9 ≈ -6.084e9 flank (ratio 1.014) → tight snap.
    # AIG is a large company; revenue covers the magnitude check.
    ni = [-8.362e9, 10.058e9, 20.622e9, 3.438e9, 9.085e9,
          7.529e9, 2.196e9, -0.849e9, -6.084e9,
          -6.0e6,      # fy2018: artifact
          3.348e9]
    p = _panel("AIG", ni, fy0=2009,
               revenue=[7e10] * 11, assets=[5e11] * 11,
               cfo=[1.5e10] * 11)
    healed, audit = apply_flow_quality(p, statements=None)
    art_row = healed[healed.fy == 2018].iloc[0]
    assert np.isclose(art_row["ni_raw"], -6.0e6, rtol=1e-9)
    # ×1e3 = -6e9; left flank -6.084e9 (ratio 1.014) → should repair
    assert np.isclose(art_row["ni"], -6.0e9, rtol=0.02), \
        f"AIG fy2018 not repaired: {art_row['ni']}"
    assert "flank_scale" in str(art_row["flow_flag"])


# ---------------------------------------------------------------------------
# 5. ABM class: real near-breakeven COVID year → UNFLAGGED
# ---------------------------------------------------------------------------
def test_abm_class_covid_trough_unflagged():
    # ABM ni fy2020 = 300000 between 127.4M (fy2019) and 126.3M (fy2021)
    # ×1e3 → 300M, ratio to 127.4M flank = 2.36x > TIGHT_ADJ=1.8 → unflagged
    ni = [75.6e6, 76.3e6, 57.2e6, 3.8e6, 97.8e6, 127.4e6,
          300000.0,      # fy2020 — REAL COVID year
          126.3e6, 230.4e6, 251.3e6, 81.4e6]
    p = _panel("ABM", ni, fy0=2014,
               revenue=[5.5e9 * 1.04 ** i for i in range(11)],
               assets=[3.8e9] * 11)
    _, audit = apply_flow_quality(p, statements=None)
    ni_flags = [r for r in audit["rows"] if r["col"] == "ni"
                and r["ticker"] == "ABM"]
    fy2020_flags = [r for r in ni_flags if r["fy"] == 2020]
    assert not fy2020_flags, f"ABM fy2020 must not be flagged: {fy2020_flags}"


# ---------------------------------------------------------------------------
# 6. CWK class: real breakeven between large negatives → UNFLAGGED (sign check)
# ---------------------------------------------------------------------------
def test_cwk_class_breakeven_between_losses_unflagged():
    # CWK ni fy2019 = 200000 between -185.8M (fy2018) and -220.5M (fy2020)
    # |raw| = 200000 >= RAW_ABSURD=1e4 → sign check required.
    # ×1e3 → 200M which is POSITIVE; adjacent clean flanks are NEGATIVE → sign mismatch.
    ni = [-221.3e6, -185.8e6,
          200000.0,     # fy2019 — REAL breakeven (filing note confirms)
          -220.5e6, 250e6, 196.4e6]
    p = _panel("CWK", ni, fy0=2017,
               revenue=[8e9] * 6, assets=[7e9] * 6)
    _, audit = apply_flow_quality(p, statements=None)
    fy2019_flags = [r for r in audit["rows"]
                    if r["ticker"] == "CWK" and r["fy"] == 2019 and r["col"] == "ni"]
    assert not fy2019_flags, f"CWK fy2019 must not be flagged: {fy2019_flags}"


# ---------------------------------------------------------------------------
# 7. HOG class: real trough, scaled lands 2.0x off flank → UNFLAGGED
# ---------------------------------------------------------------------------
def test_hog_class_tight_adj_blocks_flag():
    # HOG ni fy2020 = 1298000 (real $1.3M); flanks 423.6M (2019) and 650M (2021)
    # ×1e3 = 1.298B; ratio to 650M = 1.997x > TIGHT_ADJ=1.8 → unflagged
    ni = [733.993e6, 844.611e6, 752.207e6, 692.164e6, 521.759e6,
          531.451e6, 423.635e6,
          1298000.0,    # fy2020 — REAL COVID year
          650.024e6, 741.408e6, 706.586e6]
    p = _panel("HOG", ni, fy0=2013,
               revenue=[5.9e9] * 11, assets=[1.0e10] * 11)
    _, audit = apply_flow_quality(p, statements=None)
    fy2020_flags = [r for r in audit["rows"]
                    if r["ticker"] == "HOG" and r["fy"] == 2020 and r["col"] == "ni"]
    assert not fy2020_flags, f"HOG fy2020 must not be flagged: {fy2020_flags}"


# ---------------------------------------------------------------------------
# 8. ADSK cfo class: real trough 9e5, ×1e3 lands 2.4x off → UNFLAGGED
# ---------------------------------------------------------------------------
def test_adsk_cfo_real_trough_unflagged():
    # ADSK cfo fy2017 = 900000 (real subscription-transition trough)
    # ×1e3 = 900M; flanks: 169.7M (fy2016) and 377.1M (fy2018)
    # Ratio to 377.1M flank: 900/377.1 = 2.39 > TIGHT_ADJ=1.8 → unflagged
    cfo = [414e6, 169.7e6,
           900000.0,    # fy2017 — REAL trough
           377.1e6, 1415.1e6, 1437e6]
    ni = [-330.5e6, -582.1e6, -566.9e6, -80.8e6, 214.5e6, 1208e6]
    p = _panel("ADSK", ni, fy0=2015, cfo=cfo,
               revenue=[2e9 * 1.2 ** i for i in range(6)],
               assets=[5e9] * 6)
    _, audit = apply_flow_quality(p, statements=None)
    fy2017_flags = [r for r in audit["rows"]
                    if r["ticker"] == "ADSK" and r["fy"] == 2017 and r["col"] == "cfo"]
    assert not fy2017_flags, f"ADSK cfo fy2017 must not be flagged: {fy2017_flags}"


# ---------------------------------------------------------------------------
# 9. HOOD class: 7M profit next to -3.687B loss → UNFLAGGED (sign flip)
# ---------------------------------------------------------------------------
def test_hood_class_sign_flip_unflagged():
    # HOOD ni fy2020 = 7e6 (real profit); fy2021 = -3.687e9 (real loss)
    # |raw|=7M >= RAW_ABSURD → sign check: right flank is negative, ×1e3 would
    # give +7B (positive) → sign mismatch with -3.687B → unflagged
    ni = [7.0e6,       # fy2020 — REAL profit
          -3.687e9, -1.028e9, -541e6, 1.411e9]
    p = _panel("HOOD", ni, fy0=2020,
               revenue=[1e9, 1.8e9, 1.4e9, 1.9e9, 2.9e9],
               assets=[1.1e10, 2.0e10, 2.3e10, 1.8e10, 2.6e10])
    _, audit = apply_flow_quality(p, statements=None)
    fy2020_flags = [r for r in audit["rows"]
                    if r["ticker"] == "HOOD" and r["fy"] == 2020 and r["col"] == "ni"]
    assert not fy2020_flags, f"HOOD fy2020 must not be flagged: {fy2020_flags}"


# ---------------------------------------------------------------------------
# 10. BGC class: statements ×1e3 LOW of correct panel value → UNFLAGGED + disagree
# ---------------------------------------------------------------------------
def test_bgc_class_broken_statements_unflagged_and_in_disagreements():
    # BGC fy2023: panel ni = 38775000 (correct); statements ni = 38775 (broken ×1e3)
    # xsrc: |st|/|panel| = 38775/38775000 ≈ 0.001 → k would be -3 (negative) →
    # excluded by k>0 requirement → not xsrc_scale flagged.
    # Flank lane: ni = 38775000 which is similar to flanks ~40-160M → not absurd.
    ni_panel = [159.959e6, 185.022e6, 51.475e6, 202.196e6,
                43.901e6, 50.918e6, 153.488e6, 58.867e6,
                38775000.0,   # fy2023 — panel CORRECT; statements is broken
                123.228e6, 154.962e6]
    ni_stmt  = [np.nan] * 8 + [38775.0, 123228000.0, np.nan]
    p = _panel("BGC", ni_panel, fy0=2015,
               revenue=[2e9] * 11, assets=[3.5e9] * 11)
    st = _statements("BGC", ni_stmt, fy0=2015)

    _, audit = apply_flow_quality(p, statements=st)
    fy2023_flags = [r for r in audit["rows"]
                    if r["ticker"] == "BGC" and r["fy"] == 2023 and r["col"] == "ni"]
    assert not fy2023_flags, f"BGC fy2023 must not be flagged: {fy2023_flags}"

    # Should appear in xsrc_disagreements (significant ratio but no k>0 match)
    bgc_disagree = [d for d in audit["xsrc_disagreements"]
                    if d["ticker"] == "BGC" and d["fy"] == 2023 and d["col"] == "ni"]
    assert bgc_disagree, "BGC fy2023 should appear in xsrc_disagreements"


# ---------------------------------------------------------------------------
# 11. xsrc protection: row agreeing with statements → cannot be flank-flagged
# ---------------------------------------------------------------------------
def test_xsrc_protection_blocks_flank_flag():
    # Build a panel where a row would be flagged by the flank lane (share-absurd
    # between two large flanks) BUT the statements confirms the panel value
    # (within XSRC_CLEAN=1.5).  The protected row must stay unflagged.
    # ni: 1e9, 1.1e9, 5e6 (target), 1.2e9, 1.3e9
    # ×1e3 would land 5e9 vs 1.2e9 flank = 4.17x > TIGHT_ADJ → wouldn't snap
    # But let's make it such that the flank test would want to flag it, except
    # statements says 5e6 is correct.
    # Use ×1e6 scenario: ni=5 (tiny), flanks ~1B, statements ni=5 (same) → protected.
    ni_panel = [1.0e9, 1.1e9, 5.0, 1.2e9, 1.3e9]
    ni_stmt  = [np.nan, np.nan, 5.0, np.nan, np.nan]
    p = _panel("PROT", ni_panel, fy0=2018,
               revenue=[5e9] * 5, assets=[20e9] * 5,
               cfo=[8e8] * 5)
    st = _statements("PROT", ni_stmt, fy0=2018)

    _, audit = apply_flow_quality(p, statements=st)
    # ni=5 agrees with statements ni=5 within XSRC_CLEAN → PROTECTED
    fy2020_flags = [r for r in audit["rows"]
                    if r["ticker"] == "PROT" and r["fy"] == 2020 and r["col"] == "ni"]
    assert not fy2020_flags, \
        "xsrc-protected row must not be flagged by flank lane"


# ---------------------------------------------------------------------------
# 12. OLED dividends: interior ×1e3-low → flank_scale; GNRC/XHR: leading/trailing → UNFLAGGED
# ---------------------------------------------------------------------------
def test_oled_dividends_interior_flagged():
    # OLED fy2021: dividends = 37900 between 28.4M (2020) and 57M (2022)
    # ×1e3 = 37.9M ≈ midpoint of flanks; both flanks within TIGHT_ADJ
    div = [5.7e6, 11.3e6, 18.9e6, 28.4e6,
           37900.0,   # fy2021 artifact
           57e6, 66.7e6, 76.2e6, 85.5e6]
    ni = [103.885e6, 58.84e6, 138.304e6, 133.372e6,
          184e6, 210e6, 203e6, 222e6, 242e6]
    p = _panel("OLED", ni, fy0=2017,
               dividends=div,
               revenue=[3e8 * 1.1 ** i for i in range(9)],
               assets=[9e8 * 1.1 ** i for i in range(9)],
               cfo=[1e8 * 1.1 ** i for i in range(9)])
    healed, audit = apply_flow_quality(p, statements=None)
    art_row = healed[healed.fy == 2021].iloc[0]
    assert np.isclose(art_row["dividends_raw"], 37900.0, rtol=1e-9)
    assert np.isclose(art_row["dividends"], 37900.0 * 1e3, rtol=1e-4), \
        f"OLED dividends fy2021 not repaired: {art_row['dividends']}"
    assert "flank_scale" in str(art_row["flow_flag"])


def test_gnrc_xhk_leading_trailing_dividends_unflagged():
    # Class B leading segment (no left flank) → UNFLAGGED
    # GNRC: dividends started at $5M for 2 years then jumped to $100M
    div_lead = [5e6, 6e6,
                100e6, 110e6, 120e6]    # leading artifact-shaped segment; right flank absent
    p = _panel("GNRC", ni=[1e8] * 5, dividends=div_lead,
               revenue=[3e9] * 5, assets=[10e9] * 5, cfo=[2e8] * 5)
    _, audit = apply_flow_quality(p, statements=None)
    lead_flags = [r for r in audit["rows"]
                  if r["ticker"] == "GNRC" and r["col"] == "dividends"
                  and r["fy"] in (2018, 2019)]
    assert not lead_flags, f"leading Class B segment must not be flagged: {lead_flags}"

    # Class B trailing segment (no right flank) → UNFLAGGED
    div_trail = [100e6, 110e6, 120e6,
                 5e6, 6e6]    # trailing "artifact" — could be real wind-down
    p2 = _panel("XHR", ni=[1e8] * 5, dividends=div_trail,
                revenue=[3e9] * 5, assets=[10e9] * 5, cfo=[2e8] * 5)
    _, audit2 = apply_flow_quality(p2, statements=None)
    trail_flags = [r for r in audit2["rows"]
                   if r["ticker"] == "XHR" and r["col"] == "dividends"
                   and r["fy"] in (2022, 2023)]
    assert not trail_flags, f"trailing Class B segment must not be flagged: {trail_flags}"


# ---------------------------------------------------------------------------
# 13. CVX repurchases: real buyback suspension → UNFLAGGED (Class B both-flank requirement)
# ---------------------------------------------------------------------------
def test_cvx_repurchases_real_suspension_unflagged():
    # CVX repurchases fy2015-17 = 2M/2M/1M between 5.006B and 1.751B
    # Class B requires both flanks snap tightly.
    # Left: ×1e3 gives 2B; ratio to 5.006B = 2.5x > TIGHT_ADJ=1.8 → fails.
    rp = [7.75e8, 4.262e9, 5.004e9, 5.004e9, 5.006e9,
          2.0e6,     # fy2015
          2.0e6,     # fy2016
          1.0e6,     # fy2017 (real suspension)
          1.751e9, 4.039e9, 1.757e9]
    p = _panel("CVX", ni=[1e10] * 11, repurchases=rp,
               revenue=[2e11] * 11, assets=[2.5e11] * 11,
               cfo=[2e10] * 11, fy0=2010)
    _, audit = apply_flow_quality(p, statements=None)
    fy15_17_flags = [r for r in audit["rows"]
                     if r["ticker"] == "CVX" and r["col"] == "repurchases"
                     and r["fy"] in (2015, 2016, 2017)]
    assert not fy15_17_flags, \
        f"CVX repurchases fy2015-17 must not be flagged: {fy15_17_flags}"


# ---------------------------------------------------------------------------
# 14. Idempotency + raw preservation
# ---------------------------------------------------------------------------
def test_idempotent_and_raws_survive_second_pass():
    ni_panel = [1.0e9, 1.1e9, 1.346e6, 1.660e6, 2.519e6, 1.8e9]
    ni_stmt  = [1.0e9, 1.1e9, 1.346e9, 1.660e9, 2.519e9, 1.8e9]
    p = _panel("XX", ni_panel, fy0=2018, revenue=[1e10] * 6, assets=[6e10] * 6)
    st = _statements("XX", ni_stmt, fy0=2018)

    once, audit1 = apply_flow_quality(p, statements=st)
    twice, audit2 = apply_flow_quality(once, statements=st)

    assert audit2["rows_flagged"] == 0, \
        f"second pass must find nothing new; got {audit2['rows_flagged']} flags"

    # Raws preserved from first pass
    art_rows = twice[(twice.fy >= 2020) & (twice.fy <= 2022)]
    for _, row in art_rows.iterrows():
        assert np.isfinite(row["ni_raw"]), f"ni_raw missing after second pass fy{row['fy']}"
        assert row["flow_flag"] is not None, f"flow_flag cleared after second pass fy{row['fy']}"

    # Values unchanged between first and second pass
    pd.testing.assert_frame_equal(
        once.reset_index(drop=True),
        twice.reset_index(drop=True),
        check_like=True,
    )


# ---------------------------------------------------------------------------
# 15. PIT structure: every repair == raw × 10^3 or raw × 10^6 exactly
# ---------------------------------------------------------------------------
def test_all_repairs_are_own_value_times_power():
    # Mix of x1e3 and x1e6 artifacts via statements
    ni_panel = [5e8, 6e8, 1.5e3, 2.0e3, 500e3, 600e3, 7e8, 8e8]
    ni_stmt  = [5e8, 6e8, 1.5e9, 2.0e9, 500e6, 600e6, 7e8, 8e8]
    p = _panel("PIT", ni_panel, fy0=2015, revenue=[5e9] * 8, assets=[4e10] * 8)
    st = _statements("PIT", ni_stmt, fy0=2015)
    found = detect(p, statements=st)
    for _, row in found.iterrows():
        raw = row["value"]
        rep = row["repair"]
        assert np.isfinite(rep), "all repairs must be finite (no null class)"
        ok = any(np.isclose(rep, raw * 10 ** k, rtol=1e-6) for k in (3, 6))
        assert ok, f"repair {rep} is not raw ({raw}) × 10^3 or 10^6"


# ---------------------------------------------------------------------------
# 16. Zeros/NaNs: don't crash; ticker with <3 nonzero skipped
# ---------------------------------------------------------------------------
def test_zeros_and_nans_do_not_crash():
    # dividends with zeros interspersed
    div = [0.0, 10e6, 0.0, 12e6, 0.0, 11000.0, 14e6, 0.0]
    # fy2023: 11000 between 12M and 14M → could be artifact
    # But with zeros breaking adjacency, the nonzero sequence is: 10M, 12M, 11000, 14M
    # Segmentation on nonzero only: 10M→12M (ratio 1.2x), 12M→11000 (ratio 1091x = seg jump),
    # 11000→14M (ratio 1273x = seg jump) → 3 segments, middle = single-row
    p = _panel("ZRO", ni=[1e8] * 8, dividends=div,
               revenue=[1e9] * 8, assets=[5e9] * 8, cfo=[5e7] * 8, fy0=2016)
    # Should not raise
    _, audit = apply_flow_quality(p, statements=None)
    # The test simply verifies no exception; artifact detection outcome may vary.


def test_ticker_with_few_nonzero_values_skipped():
    # Only 2 nonzero values in ni → segmentation produces 1 segment → no flank → skip
    ni = [np.nan, np.nan, 1e6, np.nan, 2e6, np.nan]
    p = _panel("FEW", ni, revenue=[1e9] * 6, assets=[5e9] * 6, fy0=2015)
    _, audit = apply_flow_quality(p, statements=None)
    assert audit["rows_flagged"] == 0, "ticker with only 2 nonzero values should produce no flags"


# ---------------------------------------------------------------------------
# 17. detect() raises ValueError on missing ni; statements=None runs flank only
# ---------------------------------------------------------------------------
def test_detect_raises_on_missing_ni():
    p = pd.DataFrame({"ticker": ["A"], "fy": [2020], "period_end": [pd.Timestamp("2020-12-31")],
                      "revenue": [1e9], "assets": [5e9]})
    with pytest.raises(ValueError, match="ni"):
        detect(p)


def test_detect_raises_on_missing_required_cols():
    p = pd.DataFrame({"ticker": ["A"], "fy": [2020], "ni": [1e8]})
    with pytest.raises(ValueError):
        detect(p)


def test_statements_none_runs_flank_only():
    # When statements=None, xsrc lane must be skipped but flank lane runs normally
    # Use a clear flank artifact: 5 years of ~200M, one year of 200000 (×1e3 low),
    # then back to 200M.  200000 × 1e3 = 200M ≈ flanks.
    ni = [200e6, 210e6, 220e6, 200e3, 205e6, 215e6, 225e6]
    p = _panel("NOSTMT", ni, revenue=[2e9] * 7, assets=[1e10] * 7,
               cfo=[1.5e8] * 7, fy0=2015)
    found = detect(p, statements=None)
    # Should find the artifact via flank lane (no statements provided)
    art = found[(found.ticker == "NOSTMT") & (found.fy == 2018)]
    assert len(art) == 1, f"flank lane should catch the artifact: {found}"
    assert art.iloc[0]["flag"] == "flank_scale"
    assert art.iloc[0]["note"].startswith("x1e3")


# ---------------------------------------------------------------------------
# 18. xsrc_cohort: statements corroboration is REQUIRED (opus red-team M1)
# ---------------------------------------------------------------------------
def test_cohort_statements_absent_never_flagged():
    """M1 trap: a REAL near-breakeven year (e.g. a $3M large-writedown year on a
    $25B-revenue filer, 0.012% net margin) adjacent to a statements-confirmed
    artifact cohort, with NO statements coverage for that year, passes every
    magnitude gate (absurd share, scale regime, scaled plausibility) — the ONLY
    thing separating it from a mis-scaled fact is cross-source corroboration.
    Statements-absent rows must therefore never be cohort-flagged."""
    # fy2021 = 3e6 REAL (correct scale); fy2022-25 = ×1e3 artifacts (raw ~2e5)
    ni_panel = [3e6,             # fy2021: genuinely $3M — must stay untouched
                205e3, 231e3, 198e3, 226e3]     # fy2022-25: artifacts (×1e3 low)
    ni_stmt  = [np.nan,          # fy2021: no statement coverage
                205e6, 231e6, 198e6, 226e6]     # fy2022-25: confirms ×1e3
    p = _panel("TRAP1", ni_panel, fy0=2021,
               revenue=[25e9] * 5, assets=[60e9] * 5)
    st = _statements("TRAP1", ni_stmt, fy0=2021)

    healed, audit = apply_flow_quality(p, statements=st)

    # fy2022-25 must be xsrc_scale
    for fy in (2022, 2023, 2024, 2025):
        row = healed[healed.fy == fy].iloc[0]
        assert "xsrc_scale" in str(row["flow_flag"]), \
            f"fy{fy} should be xsrc_scale; got {row['flow_flag']}"

    # fy2021 must be UNTOUCHED — no statements value, no cohort flag
    fy2021 = healed[healed.fy == 2021].iloc[0]
    assert fy2021["flow_flag"] is None or "ni:" not in str(fy2021["flow_flag"]), \
        f"fy2021 (real $3M year) must not be flagged; got {fy2021['flow_flag']}"
    assert fy2021["ni"] == 3e6, \
        f"fy2021 real value must survive; got {fy2021['ni']}"


def test_pcg_vc_cohort_blocked_by_statements():
    """Negative control: same geometry but statements PRESENT and NOT scale-consistent
    (ratio ~4.9e6, outside [0.8e6, 1.25e6] band for k=6) → NOT xsrc_cohort.
    This tests the 'plain disagreement at >1.25× of 10^k' branch of condition 1."""
    ni_panel = [-102.0,
                430.0, 1100.0, 1500.0, 900.0]
    ni_stmt  = [-500e6,   # fy2021: |st|/|raw| = 500e6/102 ≈ 4.9e6 > 1.25×1e6 → NOT consistent
                430e6, 1100e6, 1500e6, 900e6]
    p = _panel("PCG3", ni_panel, fy0=2021,
               revenue=[20e9] * 5, assets=[60e9] * 5)
    st = _statements("PCG3", ni_stmt, fy0=2021)

    _, audit = apply_flow_quality(p, statements=st)
    fy2021_flags = [r for r in audit["rows"]
                    if r["ticker"] == "PCG3" and r["fy"] == 2021 and r["col"] == "ni"]
    cohort_flags = [r for r in fy2021_flags if r["flag"] == "xsrc_cohort"]
    assert not cohort_flags, \
        f"fy2021 must NOT be xsrc_cohort when statements is NOT scale-consistent: {cohort_flags}"


def test_pcg_vc_cohort_scale_consistent_statements():
    """PCG/VC variant-split archetype: statements PRESENT but scale-consistent
    (|st|/|raw| ≈ 0.86e6, within [0.5e6, 2e6] band for k=6) → xsrc_cohort FIRED.

    Models the real PCG fy2021 case where statements picked net-income-
    attributable-to-common (-88M) while the panel has total incl. preferred
    (-102M).  The ratio 88e6/102 ≈ 0.863e6 corroborates the ×1e6 scale even
    though it falls outside XSRC_TOL (1.10).
    """
    ni_panel = [-102.0,          # fy2021: artifact; statements picks -88M variant
                430.0, 1100.0, 1500.0, 900.0]
    # statements fy2021 = -88e6: ratio = 88e6/102 ≈ 0.863e6, within [0.8e6, 1.25e6]
    ni_stmt  = [-88e6,
                430e6, 1100e6, 1500e6, 900e6]
    p = _panel("PCG5", ni_panel, fy0=2021,
               revenue=[20e9] * 5, assets=[60e9] * 5)
    st = _statements("PCG5", ni_stmt, fy0=2021)

    healed, audit = apply_flow_quality(p, statements=st)

    # fy2022-25 must be xsrc_scale (ratio = 1e6 exactly, within XSRC_TOL)
    for fy in (2022, 2023, 2024, 2025):
        row = healed[healed.fy == fy].iloc[0]
        assert "xsrc_scale" in str(row["flow_flag"]), \
            f"fy{fy} should be xsrc_scale; got {row['flow_flag']}"

    # fy2021 must be xsrc_cohort: scale-consistent statements corroborates ×1e6
    fy2021 = healed[healed.fy == 2021].iloc[0]
    assert "xsrc_cohort" in str(fy2021["flow_flag"]), \
        f"fy2021 should be xsrc_cohort (scale-consistent statements); got {fy2021['flow_flag']}"
    assert np.isclose(fy2021["ni"], -102.0 * 1e6, rtol=1e-6), \
        f"fy2021 repair should be -102M; got {fy2021['ni']}"
    assert np.isclose(fy2021["ni_raw"], -102.0, rtol=1e-9), \
        f"fy2021 ni_raw should be -102; got {fy2021['ni_raw']}"


def test_cohort_scale_regime_control():
    """Adjacent row whose |raw| is >100x away from the confirmed rows' raws is
    NOT cohort-flagged even when its statements value is scale-consistent —
    the scale-regime gate (condition 3) holds independently of condition 1.
    """
    # Confirmed rows have raws ~430-1500 (×1e6 artifacts); adjacent row has
    # raw = 4.0 → regime ratio 430/4 = 107.5 > 100 → excluded, even though
    # statements = 3.6e6 is scale-consistent (ratio 0.9e6 within 1.25× of 1e6)
    # and the other gates pass (share 4/20e9 tiny; scaled 4e6/20e9 = 2e-4).
    ni_panel = [4.0,            # fy2021: out of the confirmed rows' raw regime
                430.0, 1100.0, 1500.0, 900.0]
    ni_stmt  = [3.6e6,          # scale-consistent — condition 1 alone would pass
                430e6, 1100e6, 1500e6, 900e6]
    p = _panel("PCG4", ni_panel, fy0=2021,
               revenue=[20e9] * 5, assets=[60e9] * 5)
    st = _statements("PCG4", ni_stmt, fy0=2021)

    _, audit = apply_flow_quality(p, statements=st)
    fy2021_flags = [r for r in audit["rows"]
                    if r["ticker"] == "PCG4" and r["fy"] == 2021 and r["col"] == "ni"]
    cohort_flags = [r for r in fy2021_flags if r["flag"] == "xsrc_cohort"]
    assert not cohort_flags, \
        f"fy2021 must NOT be cohort when raw is outside the confirmed regime: {cohort_flags}"


# ---------------------------------------------------------------------------
# 19. Class A anchor fallback: revenue=NaN, assets present → flank_scale
# ---------------------------------------------------------------------------
def test_tech_efc_anchor_fallback_assets():
    """TECH op_income fy2013 and EFC ni fy2023 archetypes: revenue is NaN for
    those years; assets are present.  After amendment 2 the flank lane must
    use assets as the anchor and flag the artifact.
    """
    # TECH-class: op_income = 158469 between ~160M values; revenue=NaN for that year
    op_art = [150780000.0, 156328000.0, 163055000.0,
              158469.0,       # fy2012: artifact; revenue is NaN → anchor = assets
              159750000.0, 147023000.0, 166209000.0]
    rev_vals = [5e8 * 1.1 ** i for i in range(7)]
    rev_vals[3] = np.nan      # revenue absent for the artifact year
    ast_vals = [1.2e9 * 1.1 ** i for i in range(7)]
    # assets ~$1.2B → op_income_artifact / assets = 158469/1.2e9 ≈ 1.3e-4 < ABSURD_SHARE ✓
    # ×1e3 = 158469000 ≈ 158M; flanks ~160M; ratio ≈ 1.01 → tight snap ✓
    p = _panel("TECH2", ni=[1e8] * 7, fy0=2009, op_income=op_art,
               revenue=rev_vals, assets=ast_vals)
    healed, audit = apply_flow_quality(p, statements=None)
    art_row = healed[healed.fy == 2012].iloc[0]
    assert np.isclose(art_row["op_income_raw"], 158469.0, rtol=1e-9), \
        "op_income_raw should preserve the artifact"
    assert np.isclose(art_row["op_income"], 158469.0 * 1e3, rtol=1e-4), \
        f"TECH2 op_income not x1e3 repaired: {art_row['op_income']}"
    assert "flank_scale" in str(art_row["flow_flag"])


def test_efc_class_revenue_nan_assets_anchor():
    """EFC ni class: REIT with revenue all-NaN; assets present → assets used as anchor."""
    # EFC-class: ni ~87898 (×1e3 artifact; real ~$87.9M) between 60M-120M values
    # revenue is NaN throughout; assets ~$15B
    # fy0=2016: index 3 → fy2019 is the artifact year
    ni = [60e6, 70e6, 80e6,
          87898.0,     # fy2019: artifact; revenue=NaN → anchor = assets
          100e6, 120e6]
    rev_vals = [np.nan] * 6
    ast_vals = [15e9] * 6
    # 87898 / 15e9 ≈ 5.9e-6 < ABSURD_SHARE ✓
    # ×1e3 = 87.9M; flanks 80M (left) and 100M (right)
    # ratio to 80M = 87.9/80 = 1.099 ≤ TIGHT_ADJ ✓
    p = _panel("EFC2", ni, fy0=2016,
               revenue=rev_vals, assets=ast_vals)
    healed, audit = apply_flow_quality(p, statements=None)
    art_row = healed[healed.fy == 2019].iloc[0]
    assert np.isclose(art_row["ni_raw"], 87898.0, rtol=1e-9), \
        "ni_raw should preserve the artifact"
    assert np.isclose(art_row["ni"], 87898.0 * 1e3, rtol=1e-4), \
        f"EFC2 ni not x1e3 repaired: {art_row['ni']}"
    assert "flank_scale" in str(art_row["flow_flag"])


# ---------------------------------------------------------------------------
# 20. HOG-class ×1e3 landing ~1.95-2.0× off flank with no statements → UNFLAGGED
# ---------------------------------------------------------------------------
def test_hog_class_tight_adj_1_95x_unflagged():
    """HOG-class: real trough year where ×1e3 lands ~1.95× off the clean flank —
    must stay UNFLAGGED at TIGHT_ADJ=1.8 (i.e., 1.95 > 1.8 → excluded)."""
    # Right flank = 650M; ×1e3 snap must land > 1.8× off it to be excluded.
    # raw = 1_267_000 → ×1e3 = 1.267B; ratio to 650M = 1.949 > 1.8 → unflagged
    # Left flank = 420M; ratio to 420M = 1.267B/420M = 3.017 > LOOSE_ALL? No, > TIGHT,
    # but LOOSE_ALL=4.0 so left passes LOOSE but not TIGHT.  Right doesn't snap tightly.
    ni = [500e6, 420e6,
          1_267_000.0,    # real trough: ×1e3 lands 1.949× off right flank
          650e6, 720e6]
    p = _panel("HOGB", ni, fy0=2017,
               revenue=[5.9e9] * 5, assets=[1.0e10] * 5)
    _, audit = apply_flow_quality(p, statements=None)
    trough_flags = [r for r in audit["rows"]
                    if r["ticker"] == "HOGB" and r["fy"] == 2019 and r["col"] == "ni"]
    assert not trough_flags, \
        f"HOG-class trough must not be flagged (1.95× > TIGHT_ADJ=1.8): {trough_flags}"
