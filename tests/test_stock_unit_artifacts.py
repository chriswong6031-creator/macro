"""Stock-column unit-artifact detector/repair (collectors/edgar_stock_quality).

Synthetic panels only — no network, no committed-data reads.  Each fixture is a
minimal reconstruction of a defect class observed in the real panel (tickers in
comments), plus the confusable REAL patterns the detector must leave alone:
real negative equity (CHTR-class sign flip, RNG-class leading tiny equity),
leading-edge junk facts (MDT/FTI/MIR), leading-edge genuine small debt_lt
(OTIS/OGS/IDCC), near-zero genuine mid-series equity, and idempotency.

PIT honesty is pinned structurally: every repair value must equal the row's own
value × 10^k for k in {3, 6} — repairs never come from statements.parquet or
any other row.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from collectors.edgar_stock_quality import apply_stock_quality, detect, STOCK_COLS


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _panel(ticker: str,
           assets: list,
           fy0: int = 2008,
           equity: list | None = None,
           debt_lt: list | None = None,
           revenue: list | None = None,
           ni: list | None = None,
           cfo: list | None = None,
           shares: list | None = None,
           assets_prior: list | None = None) -> pd.DataFrame:
    """Build a minimal synthetic panel for stock-column tests.

    revenue defaults to ~$2.5B growing 5%/yr; ni to ~$200M; assets provided
    explicitly so the test controls the exact artifact shape.
    """
    n = len(assets)
    rev_def = [2.5e9 * 1.05 ** i for i in range(n)]
    ni_def  = [200e6 * 1.05 ** i for i in range(n)]
    rev = revenue if revenue is not None else rev_def
    ni_vals = ni if ni is not None else ni_def
    rows = []
    for i in range(n):
        row: dict = {
            "ticker": ticker,
            "cik": 1,
            "fy": fy0 + i,
            "assets": float(assets[i]) if (assets[i] is not None and not
                            (isinstance(assets[i], float) and np.isnan(assets[i])))
                      else np.nan,
            "period_end": pd.Timestamp(f"{fy0 + i}-12-31"),
        }
        row["revenue"] = (float(rev[i]) if (rev[i] is not None and not
                          (isinstance(rev[i], float) and np.isnan(rev[i])))
                          else np.nan)
        row["ni"] = (float(ni_vals[i]) if (ni_vals[i] is not None and not
                     (isinstance(ni_vals[i], float) and np.isnan(ni_vals[i])))
                     else np.nan)
        if equity is not None:
            row["equity"] = float(equity[i])
        if debt_lt is not None:
            row["debt_lt"] = float(debt_lt[i])
        if cfo is not None:
            row["cfo"] = float(cfo[i])
        if shares is not None:
            row["shares"] = float(shares[i])
        if assets_prior is not None:
            row["assets_prior"] = float(assets_prior[i]) if (
                assets_prior[i] is not None and not
                (isinstance(assets_prior[i], float) and np.isnan(assets_prior[i]))
            ) else np.nan
        rows.append(row)
    p = pd.DataFrame(rows)
    p["asof_date"] = p["period_end"] + pd.Timedelta(days=120)
    return p


def _statements(ticker: str, assets: list, fy0: int = 2008,
                equity: list | None = None,
                debt_lt: list | None = None) -> pd.DataFrame:
    n = len(assets)
    rows = []
    for i in range(n):
        row: dict = {
            "ticker": ticker,
            "fy": fy0 + i,
            "assets": float(assets[i]) if assets[i] is not None else np.nan,
        }
        if equity is not None:
            row["equity"] = float(equity[i]) if equity[i] is not None else np.nan
        if debt_lt is not None:
            row["debt_lt"] = float(debt_lt[i]) if debt_lt[i] is not None else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# a. ATO-class: all three stock cols ×1e3 low, interior, revenue NaN,
#    ni+shares continuous, assets_prior mirror on next fy
# ---------------------------------------------------------------------------
def test_ato_class_all_three_cols_x1e3_interior():
    """ATO fy2010: assets=7.2216e6/equity=2.2749e6/debt_lt=1.8073e6 (all ×1e3 low)
    between proper-scale flanks.  revenue=NaN that year; ni and shares continuous.
    All three repaired ×1e3.  Next fy's assets_prior mirrored."""
    # fy2008, fy2009, fy2010(artifact), fy2011, fy2012
    assets  = [5.5e9, 6.367e9, 7.2216e6, 7.6356e9, 7.964e9]
    equity  = [1.8e9, 2.177e9, 2.2749e6, 2.2678e9, 2.424e9]
    debt_lt = [1.9e9, 2.169e9, 1.8073e6, 2.206e9,  1.956e9]
    rev     = [np.nan, np.nan, np.nan, np.nan, np.nan]  # revenue absent throughout
    ni_vals = [190e6, 191e6, 205.839e6, 207.601e6, 216.717e6]
    shares_vals = [np.nan, np.nan, 90648911.0, 90016074.0, 90517509.0]
    # assets_prior for fy2011 should equal raw artifact assets from fy2010
    ap = [np.nan, np.nan, 6.367e9, 7.2216e6, 7.6356e9]

    p = _panel("ATO", assets, fy0=2008,
               equity=equity, debt_lt=debt_lt, revenue=rev,
               ni=ni_vals, shares=shares_vals, assets_prior=ap)

    healed, audit = apply_stock_quality(p, statements=None)

    # All three artifact columns must be repaired
    art = healed[healed.fy == 2010].iloc[0]
    assert np.isclose(art["assets"],  7.2216e9,  rtol=1e-4), \
        f"assets not repaired: {art['assets']}"
    assert np.isclose(art["equity"],  2.2749e9,  rtol=1e-4), \
        f"equity not repaired: {art['equity']}"
    assert np.isclose(art["debt_lt"], 1.8073e9,  rtol=1e-4), \
        f"debt_lt not repaired: {art['debt_lt']}"

    # raw columns preserve originals
    assert np.isclose(art["assets_raw"],  7.2216e6, rtol=1e-4)
    assert np.isclose(art["equity_raw"],  2.2749e6, rtol=1e-4)
    assert np.isclose(art["debt_lt_raw"], 1.8073e6, rtol=1e-4)

    # flags contain x1e3 flank tokens
    assert "assets:flank_scale:x1e3" in str(art["stock_flag"])
    assert "equity:flank_scale:x1e3" in str(art["stock_flag"])
    assert "debt_lt:flank_scale:x1e3" in str(art["stock_flag"])

    # assets_prior in fy2011 mirrors the repaired assets value
    fy2011 = healed[healed.fy == 2011].iloc[0]
    assert np.isclose(fy2011["assets_prior"], 7.2216e9, rtol=1e-4), \
        f"assets_prior not mirrored in fy2011: {fy2011['assets_prior']}"
    assert np.isclose(fy2011["assets_prior_raw"], 7.2216e6, rtol=1e-4)
    assert "assets_prior:mirror" in str(fy2011["stock_flag"])
    assert audit["mirrors"] == 1

    # clean rows untouched
    for fy in (2008, 2009, 2011, 2012):
        row = healed[healed.fy == fy].iloc[0]
        flag = row["stock_flag"]
        if fy == 2011:
            # fy2011 has assets_prior:mirror but no col repair
            continue
        assert flag is None or "flank_scale" not in str(flag), \
            f"clean fy{fy} should not be flank-flagged: {flag}"


# ---------------------------------------------------------------------------
# b. GNRC-class: single interior debt_lt ×1e3, other columns clean
# ---------------------------------------------------------------------------
def test_gnrc_class_interior_debt_lt_x1e3():
    """GNRC fy2016: debt_lt=1.0484e6 between 1.0677e9 (2015) and 9.3506e8 (2017).
    assets and equity are continuous; only debt_lt repaired."""
    # fy2014..fy2018
    assets  = [1.864e9, 1.779e9, 1.866e9, 2.026e9, 2.426e9]
    equity  = [489e6,   466e6,   401e6,   554e6,   760e6]
    debt_lt = [1.1065e9, 1.0677e9, 1.0484e6, 9.3506e8, 9.0081e8]
    rev     = [np.nan, np.nan, 1.4477e9, 1.6794e9, 2.0235e9]
    ni_vals = [174e6, 77e6, 97e6, 158e6, 238e6]

    p = _panel("GNRC", assets, fy0=2014,
               equity=equity, debt_lt=debt_lt, revenue=rev, ni=ni_vals)

    healed, audit = apply_stock_quality(p, statements=None)

    art = healed[healed.fy == 2016].iloc[0]
    assert np.isclose(art["debt_lt"], 1.0484e9, rtol=1e-4), \
        f"debt_lt not repaired: {art['debt_lt']}"
    assert np.isclose(art["debt_lt_raw"], 1.0484e6, rtol=1e-4)
    assert "debt_lt:flank_scale:x1e3" in str(art["stock_flag"])

    # assets and equity on fy2016 must NOT be flagged
    assert "assets:flank_scale" not in str(art.get("stock_flag", ""))
    assert "equity:flank_scale" not in str(art.get("stock_flag", ""))

    # other years untouched
    for fy in (2014, 2015, 2017, 2018):
        row = healed[healed.fy == fy].iloc[0]
        assert row.get("debt_lt_raw") is None or np.isnan(row.get("debt_lt_raw", np.nan)), \
            f"GNRC fy{fy} debt_lt_raw should be NaN (not a repair): {row.get('debt_lt_raw')}"

    assert audit["repaired"] == 1
    assert audit["nulled"] == 0


# ---------------------------------------------------------------------------
# c. SNEX-class: single interior assets ×1e6, assets_prior mirror on next fy
# ---------------------------------------------------------------------------
def test_snex_class_interior_assets_x1e6():
    """SNEX fy2018: assets=8710.5 between 6.8089e9 (2017) and 1.0129e10 (2019).
    Scaled value 8.7105e9 lands 1.28× off left flank (6.8089e9) — within
    TIGHT_ADJ=1.5.  assets_prior in fy2019 (= raw artifact) must be mirrored."""
    # fy2016..fy2020
    assets      = [6.2907e9, 6.8089e9, 8710.5, 1.0129e10, 1.3975e10]
    assets_prior_vals = [np.nan, 6.2907e9, 6.8089e9, 8710.5, 1.0129e10]
    rev         = [1.4755e10, 2.9424e10, 2.7623e10, 3.2897e10, 5.4140e10]
    ni_vals     = [np.nan, np.nan, 55.5e6, 85.1e6, 169.6e6]

    p = _panel("SNEX", assets, fy0=2016,
               revenue=rev, ni=ni_vals, assets_prior=assets_prior_vals)

    healed, audit = apply_stock_quality(p, statements=None)

    art = healed[healed.fy == 2018].iloc[0]
    assert np.isclose(art["assets"], 8.7105e9, rtol=1e-4), \
        f"assets not repaired: {art['assets']}"
    assert np.isclose(art["assets_raw"], 8710.5, rtol=1e-4)
    assert "assets:flank_scale:x1e6" in str(art["stock_flag"])

    # fy2019 assets_prior mirror
    fy2019 = healed[healed.fy == 2019].iloc[0]
    assert np.isclose(fy2019["assets_prior"], 8.7105e9, rtol=1e-4), \
        f"assets_prior not mirrored in fy2019: {fy2019['assets_prior']}"
    assert np.isclose(fy2019["assets_prior_raw"], 8710.5, rtol=1e-4)
    assert "assets_prior:mirror" in str(fy2019["stock_flag"])

    assert audit["repaired"] == 1
    assert audit["mirrors"] == 1


# ---------------------------------------------------------------------------
# d. xsrc lane: panel assets ×1e3 low, statements confirms → xsrc_scale
# ---------------------------------------------------------------------------
def test_xsrc_lane_assets_x1e3():
    """A row whose panel assets is ×1e3 low and statements confirms the
    correction (|st|/|panel| ≈ 1000, within XSRC_TOL=1.10)."""
    # fy2019(artifact), fy2020, fy2021 — no flanks needed for xsrc lane
    assets_p = [5.0e6,    12e9,  13e9]   # fy2019: artifact
    assets_s = [5.0e9,    12e9,  13e9]   # statements: correct scale
    rev       = [2e9, 2.1e9, 2.2e9]
    ni_vals   = [200e6, 210e6, 220e6]

    p = _panel("XSTO", assets_p, fy0=2019, revenue=rev, ni=ni_vals)
    st = _statements("XSTO", assets_s, fy0=2019)

    healed, audit = apply_stock_quality(p, statements=st)

    art = healed[healed.fy == 2019].iloc[0]
    assert np.isclose(art["assets"], 5.0e9, rtol=1e-6), \
        f"xsrc repair wrong: {art['assets']}"
    assert np.isclose(art["assets_raw"], 5.0e6, rtol=1e-6)
    assert "xsrc_scale" in str(art["stock_flag"])
    xsrc_flags = [r for r in audit["rows"] if r["flag"] == "xsrc_scale"]
    assert len(xsrc_flags) >= 1


# ---------------------------------------------------------------------------
# e. CHTR-class: equity sign flip −4.6e7 → +4.014e10 → UNFLAGGED
# ---------------------------------------------------------------------------
def test_chtr_class_equity_sign_flip_unflagged():
    """CHTR equity fy2015=-4.6e7 (real); fy2016=+4.014e10 (Time Warner Cable
    acquisition).  Abs ratio ≈ 873 × (inside ×1e3 artifact band), but signs
    differ → same_sign check rejects it.  Must stay unflagged."""
    assets  = [2.44e10, 3.93e10, 1.49e11, 1.47e11, 1.46e11]
    equity  = [1.46e8,  -4.6e7,  4.014e10, 3.908e10, 3.628e10]
    debt_lt = [2.09e10, 3.57e10, 5.97e10, 6.82e10, 6.95e10]
    rev     = [9.1e9, 9.7e9, 4.12e10, 4.14e10, 4.15e10]

    p = _panel("CHTR", assets, fy0=2013,
               equity=equity, debt_lt=debt_lt, revenue=rev)

    _, audit = apply_stock_quality(p, statements=None)

    # equity fy2015 (negative) to fy2016 (positive): must not be flagged
    chtr_flags = [r for r in audit["rows"] if r["ticker"] == "CHTR"]
    equity_flags = [r for r in chtr_flags if r["col"] == "equity"]
    assert not equity_flags, \
        f"CHTR equity sign-flip must not be flagged: {equity_flags}"


# ---------------------------------------------------------------------------
# f. OTIS/OGS/IDCC-class: leading-edge tiny debt_lt → UNFLAGGED (interior-only rule)
# ---------------------------------------------------------------------------
def test_otis_class_leading_edge_debt_lt_unflagged():
    """OTIS fy2019: debt_lt=5e6 before IPO-era jump to 5.262B.  Interior-only
    rule leaves leading segments entirely unflagged (flank_suspects at most)."""
    assets  = [np.nan, np.nan, np.nan, np.nan, 1.85e10, 1.89e10, 1.90e10]
    debt_lt = [np.nan, np.nan, np.nan, np.nan, 5.0e6,  5.262e9, 5.262e9]
    rev     = [np.nan, np.nan, np.nan, np.nan, 1.43e10, 1.39e10, 1.42e10]

    p = _panel("OTIS", assets, fy0=2015,
               debt_lt=debt_lt, revenue=rev)

    _, audit = apply_stock_quality(p, statements=None)
    otis_flagged = [r for r in audit["rows"]
                    if r["ticker"] == "OTIS" and r["col"] == "debt_lt"
                    and r["fy"] in (2019,)]
    assert not otis_flagged, \
        f"OTIS leading-edge debt_lt must not be flagged: {otis_flagged}"


# ---------------------------------------------------------------------------
# g. RNG-class: leading-edge tiny equity → UNFLAGGED (interior-only rule)
# ---------------------------------------------------------------------------
def test_rng_class_leading_equity_unflagged():
    """RNG equity: tiny positive pre-IPO values before growth.  The leading
    segment has no left flank — interior-only rule leaves it unflagged."""
    assets  = [50e6,  80e6,  1.0e9, 1.2e9, 1.5e9, 2.0e9]
    equity  = [71e3,  80e3,  1.2e9, 1.3e9, 1.4e9, 1.8e9]
    rev     = [50e6,  80e6,  3.5e8, 5.0e8, 7.0e8, 9.0e8]

    p = _panel("RNG", assets, fy0=2012,
               equity=equity, revenue=rev)

    _, audit = apply_stock_quality(p, statements=None)
    rng_flagged = [r for r in audit["rows"]
                   if r["ticker"] == "RNG" and r["col"] == "equity"]
    assert not rng_flagged, \
        f"RNG leading-edge equity must not be flagged: {rng_flagged}"


# ---------------------------------------------------------------------------
# h. MDT/FTI-class: leading-edge junk assets → UNFLAGGED + suspect
# ---------------------------------------------------------------------------
def test_mdt_class_junk_assets_unflagged():
    """MDT fy2014 assets=46000 before ~$100B balance sheet.  No ×10^k restores
    a plausible value (46000 × 1e6 = 4.6e10, which is at least plausible size
    but 46000 × 1e3 = 4.6e7 which is not, and 4.6e10 might not snap tightly).
    Interior-only rule means this LEADING segment is never flagged (flank_suspects
    only if break ≥ 500×)."""
    # Leading artifact, then normal scale
    assets = [46000.0, 1.0274e11, 1.0356e11, 1.1211e11, 1.2189e11]
    equity = [-3.7e7,   4.9e10,   5.2e10,   5.9e10,   6.2e10]
    rev    = [np.nan,   2.82e10,  2.91e10,  3.02e10,  3.0e10]
    ni_vals= [np.nan,   3.8e9,    4.5e9,    4.6e9,    4.4e9]

    p = _panel("MDT", assets, fy0=2014,
               equity=equity, revenue=rev, ni=ni_vals)

    healed, audit = apply_stock_quality(p, statements=None)
    mdt_flagged = [r for r in audit["rows"]
                   if r["ticker"] == "MDT" and r["col"] == "assets"]
    assert not mdt_flagged, \
        f"MDT junk leading assets must not be flagged: {mdt_flagged}"

    # The fy2014 junk row must go to flank_suspects (leading break ≥ 500×)
    mdt_suspects = [s for s in audit["flank_suspects"]
                    if s["ticker"] == "MDT" and s["col"] == "assets"]
    assert mdt_suspects, "MDT junk assets should appear in flank_suspects"

    # fy2015 assets_prior = 46000 (mirror of junk) must be untouched since
    # the original fy2014 assets was never repaired — no mirror should fire
    fy2015 = healed[healed.fy == 2015].iloc[0]
    ap_raw = fy2015.get("assets_prior_raw", np.nan)
    assert not np.isfinite(ap_raw) or np.isnan(float(ap_raw)), \
        f"MDT fy2015 assets_prior_raw should be NaN (no repair happened): {ap_raw}"
    # assets values on non-junk rows must be untouched
    for fy in (2015, 2016, 2017, 2018):
        row = healed[healed.fy == fy].iloc[0]
        flag = row.get("stock_flag", None)
        assert flag is None or "flank_scale" not in str(flag), \
            f"MDT fy{fy} should not have flank_scale: {flag}"


# ---------------------------------------------------------------------------
# i. Real near-zero equity mid-series that does NOT snap to 10^k → UNFLAGGED
# ---------------------------------------------------------------------------
def test_real_near_zero_equity_mid_series_unflagged():
    """A genuine near-breakeven book year in the middle of a series.
    The equity value is tiny but doesn't scale to match either flank:
    left=2B, right=2.1B, raw=5e6 → ×1e3 would give 5B (2.5× off flanks > TIGHT_ADJ).
    Must stay unflagged."""
    assets  = [1.5e10, 1.6e10, 1.7e10, 1.8e10, 1.9e10]
    equity  = [1.8e9, 2.0e9, 5.0e6, 2.1e9, 2.2e9]
    rev     = [3e9, 3.1e9, 3.2e9, 3.3e9, 3.4e9]

    p = _panel("NZEQ", assets, fy0=2018,
               equity=equity, revenue=rev)

    _, audit = apply_stock_quality(p, statements=None)
    flags = [r for r in audit["rows"]
             if r["ticker"] == "NZEQ" and r["col"] == "equity" and r["fy"] == 2020]
    assert not flags, \
        f"Real near-zero equity mid-series must not be flagged: {flags}"


# ---------------------------------------------------------------------------
# j. xsrc reverse/BGC-class: statements is the SMALL side (k negative) → disagree
# ---------------------------------------------------------------------------
def test_xsrc_reverse_statements_small_side():
    """Panel assets = 5.0e9 (correct), statements assets = 5.0e6 (broken ×1e3 low).
    |st|/|panel| ≈ 0.001 → k would be -3 (negative) — excluded by k>0 requirement.
    Row appears in xsrc_disagreements, panel is NOT mutated."""
    assets_p = [4.5e9, 5.0e9, 5.5e9]
    assets_s = [4.5e9, 5.0e6, 5.5e9]  # fy2019 statements is broken

    p = _panel("BGCS", assets_p, fy0=2018)
    st = _statements("BGCS", assets_s, fy0=2018)

    _, audit = apply_stock_quality(p, statements=st)

    fy2019_flags = [r for r in audit["rows"]
                    if r["ticker"] == "BGCS" and r["fy"] == 2019]
    assert not fy2019_flags, \
        f"Reverse-xsrc (panel correct, stmt broken) must not be flagged: {fy2019_flags}"

    bgcs_disagree = [d for d in audit["xsrc_disagreements"]
                     if d["ticker"] == "BGCS" and d["fy"] == 2019]
    assert bgcs_disagree, "Reverse-xsrc case should appear in xsrc_disagreements"


# ---------------------------------------------------------------------------
# k. PROTECTED: statements ≈ panel within 1.5 same sign → flank lane cannot flag
# ---------------------------------------------------------------------------
def test_xsrc_protection_blocks_flank_flag():
    """A row that looks like a flank artifact but statements confirms the panel
    value is correct (within XSRC_CLEAN=1.5) → PROTECTED from flank lane."""
    # assets = 1e9, 1.1e9, 5e6, 1.2e9, 1.3e9 (middle looks tiny)
    # statements for middle fy = 5e6 (confirms it's a real tiny balance)
    assets_p = [1.0e9, 1.1e9, 5.0e6, 1.2e9, 1.3e9]
    assets_s = [np.nan, np.nan, 5.0e6, np.nan, np.nan]

    p = _panel("PROT", assets_p, fy0=2017)
    st = _statements("PROT", assets_s, fy0=2017)

    _, audit = apply_stock_quality(p, statements=st)

    fy2019_flags = [r for r in audit["rows"]
                    if r["ticker"] == "PROT" and r["fy"] == 2019
                    and r["col"] == "assets"]
    assert not fy2019_flags, \
        "xsrc-protected row must not be flagged by flank lane"


# ---------------------------------------------------------------------------
# l. Idempotency: second pass on healed panel finds nothing new
# ---------------------------------------------------------------------------
def test_idempotent_and_raws_survive_second_pass():
    """Running apply_stock_quality on an already-healed panel must find 0 new
    flags.  The raw columns and stock_flag from the first pass survive."""
    assets  = [5.5e9, 6.367e9, 7.2216e6, 7.6356e9, 7.964e9]
    equity  = [1.8e9, 2.177e9, 2.2749e6, 2.2678e9, 2.424e9]
    debt_lt = [1.9e9, 2.169e9, 1.8073e6, 2.206e9,  1.956e9]
    rev     = [np.nan, np.nan, np.nan, np.nan, np.nan]
    ni_vals = [190e6, 191e6, 205e6, 207e6, 216e6]
    shares_vals = [np.nan, np.nan, 90e6, 90e6, 90e6]
    ap = [np.nan, np.nan, 6.367e9, 7.2216e6, 7.6356e9]

    p = _panel("IDEM", assets, fy0=2008,
               equity=equity, debt_lt=debt_lt, revenue=rev,
               ni=ni_vals, shares=shares_vals, assets_prior=ap)

    once,  audit1 = apply_stock_quality(p, statements=None)
    twice, audit2 = apply_stock_quality(once, statements=None)

    assert audit2["rows_flagged"] == 0, \
        f"second pass must find nothing new; got {audit2['rows_flagged']} flags"

    # raws preserved from first pass
    art_once  = once[once.fy == 2010].iloc[0]
    art_twice = twice[twice.fy == 2010].iloc[0]
    assert np.isfinite(art_twice["assets_raw"]),  "assets_raw missing after second pass"
    assert np.isfinite(art_twice["equity_raw"]),  "equity_raw missing after second pass"
    assert np.isfinite(art_twice["debt_lt_raw"]), "debt_lt_raw missing after second pass"
    assert art_twice["stock_flag"] is not None, "stock_flag cleared after second pass"

    # Values unchanged between first and second pass
    pd.testing.assert_frame_equal(
        once.reset_index(drop=True),
        twice.reset_index(drop=True),
        check_like=True,
    )


# ---------------------------------------------------------------------------
# PIT discipline: every repair == raw × 10^3 or raw × 10^6
# ---------------------------------------------------------------------------
def test_all_repairs_are_own_value_times_power():
    """All detections in the xsrc lane must be raw × 10^k for k ∈ {3,6}."""
    assets_p = [5e8, 6e8, 1.5e3, 2.0e3, 500e3, 600e3, 7e8, 8e8]
    assets_s = [5e8, 6e8, 1.5e9, 2.0e9, 500e6, 600e6, 7e8, 8e8]
    p = _panel("PIT2", assets_p, fy0=2014)
    st = _statements("PIT2", assets_s, fy0=2014)
    found = detect(p, statements=st)
    for _, row in found.iterrows():
        raw = row["value"]
        rep = row["repair"]
        assert np.isfinite(rep), "all repairs must be finite"
        ok = any(np.isclose(rep, raw * 10 ** k, rtol=1e-6) for k in (3, 6))
        assert ok, f"repair {rep} is not raw ({raw}) × 10^3 or 10^6"


# ---------------------------------------------------------------------------
# detect() raises ValueError on missing assets or required cols
# ---------------------------------------------------------------------------
def test_detect_raises_on_missing_assets():
    p = pd.DataFrame({"ticker": ["A"], "fy": [2020],
                      "period_end": [pd.Timestamp("2020-12-31")],
                      "equity": [1e9]})
    with pytest.raises(ValueError, match="assets"):
        detect(p)


def test_detect_raises_on_missing_required_cols():
    p = pd.DataFrame({"ticker": ["A"], "fy": [2020], "assets": [5e9]})
    with pytest.raises(ValueError):
        detect(p)


# ---------------------------------------------------------------------------
# statements=None runs flank only
# ---------------------------------------------------------------------------
def test_statements_none_runs_flank_only():
    """When statements=None, xsrc lane is skipped but flank lane runs normally.
    Use ×1e3 artifact: 5.3e6 between ~5.3e9 flanks → ratio ≈ 1000."""
    assets = [5.0e9, 5.2e9, 5.3e9, 5.3e6, 6.0e9, 6.1e9, 6.2e9]
    ni_vals = [200e6, 210e6, 220e6, 215e6, 240e6, 250e6, 260e6]
    shares_v = [1e7] * 7

    p = _panel("NSTMT", assets, fy0=2015,
               ni=ni_vals, shares=shares_v)
    found = detect(p, statements=None)
    art = found[(found.ticker == "NSTMT") & (found.fy == 2018)]
    assert len(art) == 1, f"flank lane should catch the interior artifact: {found}"
    assert art.iloc[0]["flag"] == "flank_scale"
    assert art.iloc[0]["note"].startswith("x1e3")


# ---------------------------------------------------------------------------
# Audit shape matches contract (same keys as flow audit)
# ---------------------------------------------------------------------------
def test_audit_shape():
    """Audit dict must have all expected keys with correct types."""
    p = _panel("AUD", [5e9, 5.1e9, 5.2e9])
    _, audit = apply_stock_quality(p, statements=None)

    required = {"applied", "rows_flagged", "tickers_flagged", "by_flag",
                "repaired", "nulled", "mirrors", "rows",
                "xsrc_disagreements", "flank_suspects"}
    assert required <= set(audit.keys()), \
        f"missing audit keys: {required - set(audit.keys())}"
    assert audit["nulled"] == 0, "nulled must always be 0 in v1"
    assert isinstance(audit["by_flag"], dict)
    assert isinstance(audit["rows"], list)


# ---------------------------------------------------------------------------
# NEW TESTS: Three-gate Class B design (FIX 1) and anchor-all-absent (FIX 2)
# ---------------------------------------------------------------------------

# Test 1: recap contrast — statements-absent perfect snap vs statements-present
# ---------------------------------------------------------------------------
def test_classb_recap_contrast_stmt_absent_vs_present():
    """Pin the documented behavior for the statements-absent perfect-snap recap.

    Variant A (statements absent): equity 2e9 → 2e6 → 2e9, perfect snap ratios
    1.00/1.00, good NI anchors → Gate 2(a) passes, Gate 2(b) absent → REPAIRED.
    This is the documented residual; *_raw preserves the original.

    Variant B (statements present confirming raw): statements equity=2e6 at the
    artifact year → xsrc lane marks it PROTECTED (st≈panel within 1.5) → NOT
    repaired by the flank lane.
    """
    # --- Variant A: no statements ---
    assets_a = [1.5e10, 1.5e10, 1.5e10, 1.5e10, 1.5e10]
    equity_a = [2.0e9,  2.0e9,  2.0e6,  2.0e9,  2.0e9 ]
    ni_a     = [200e6,  205e6,  210e6,  215e6,  220e6 ]

    pA = _panel("RCPA", assets_a, fy0=2016,
                equity=equity_a, ni=ni_a)
    healedA, auditA = apply_stock_quality(pA, statements=None)

    art_a = healedA[healedA.fy == 2018].iloc[0]
    assert np.isclose(art_a["equity"], 2.0e9, rtol=1e-4), \
        f"stmt-absent perfect-snap recap should be repaired: {art_a['equity']}"
    assert np.isclose(art_a["equity_raw"], 2.0e6, rtol=1e-4), \
        "equity_raw should preserve the original raw value"
    eq_flags_a = [r for r in auditA["rows"]
                  if r["ticker"] == "RCPA" and r["col"] == "equity"]
    assert eq_flags_a, "Variant A should produce an equity repair"

    # --- Variant B: statements present confirming raw (st=2e6 = raw) ---
    assets_b = [1.5e10, 1.5e10, 1.5e10, 1.5e10, 1.5e10]
    equity_b = [2.0e9,  2.0e9,  2.0e6,  2.0e9,  2.0e9 ]
    ni_b     = [200e6,  205e6,  210e6,  215e6,  220e6 ]
    # statements confirms the raw value — ratio st/panel ≈ 1.0 → PROTECTED
    stmt_equity_b = [np.nan, np.nan, 2.0e6, np.nan, np.nan]

    pB = _panel("RCPB", assets_b, fy0=2016, equity=equity_b, ni=ni_b)
    stB = _statements("RCPB", [np.nan]*5, fy0=2016, equity=stmt_equity_b)
    healedB, auditB = apply_stock_quality(pB, statements=stB)

    art_b = healedB[healedB.fy == 2018].iloc[0]
    assert np.isclose(art_b["equity"], 2.0e6, rtol=1e-4), \
        f"Variant B (stmt present=raw) must NOT be repaired: {art_b['equity']}"
    eq_flags_b = [r for r in auditB["rows"]
                  if r["ticker"] == "RCPB" and r["col"] == "equity"]
    assert not eq_flags_b, \
        f"Variant B must produce no equity repair: {eq_flags_b}"


# Test 2: statements-disagreement blocks standalone Class-B repair
# ---------------------------------------------------------------------------
def test_classb_standalone_stmt_disagreement_blocks():
    """Standalone debt_lt interior snap where statements has a value at neither
    ≈raw nor ≈raw×10^k (st = raw×40) → no repair, row goes to flank_suspects."""
    assets_vals = [2.0e9, 2.0e9, 2.0e9, 2.0e9, 2.0e9]
    equity_vals = [800e6, 820e6, 840e6, 860e6, 880e6]
    # debt_lt: 1.1e9, 1.1e9, 1.1e6 (artifact), 1.1e9, 1.1e9
    # assets and equity are clean → no same-row assets corroboration
    debt_lt_vals = [1.1e9, 1.1e9, 1.1e6, 1.1e9, 1.1e9]
    ni_vals_t   = [100e6, 102e6, 105e6, 108e6, 111e6]

    p = _panel("SDIS", assets_vals, fy0=2017,
               equity=equity_vals, debt_lt=debt_lt_vals, ni=ni_vals_t)

    # Statements says debt_lt = 1.1e6 * 40 = 44e6 — neither raw(1.1e6) nor scaled(1.1e9)
    stmt_dlt = [np.nan, np.nan, 44.0e6, np.nan, np.nan]
    st = _statements("SDIS", [np.nan]*5, fy0=2017, debt_lt=stmt_dlt)

    healed, audit = apply_stock_quality(p, statements=st)

    art = healed[healed.fy == 2019].iloc[0]
    # Must NOT be repaired
    assert np.isclose(art["debt_lt"], 1.1e6, rtol=1e-4), \
        f"stmt-disagree should block repair: debt_lt={art['debt_lt']}"
    dlt_flags = [r for r in audit["rows"]
                 if r["ticker"] == "SDIS" and r["col"] == "debt_lt"]
    assert not dlt_flags, f"no debt_lt repair should fire: {dlt_flags}"

    # Must appear in flank_suspects
    dlt_suspects = [s for s in audit["flank_suspects"]
                    if s["ticker"] == "SDIS" and s["col"] == "debt_lt"]
    assert dlt_suspects, "stmt-disagreement debt_lt must appear in flank_suspects"


# Test 3: strict-band boundary (standalone vs corroborated)
# ---------------------------------------------------------------------------
def test_classb_strict_band_boundary():
    """CLASSB_SOLO_TIGHT=1.25 boundary behaviour, and that Gate 1 (same-row
    corroboration) still uses the looser TIGHT_ADJ=1.5 band.

    Case A: standalone debt_lt, both-flank ratio 1.24 → repaired.
    Case B: standalone debt_lt, both-flank ratio 1.26 → NOT repaired (suspects).
    Case C: debt_lt with same-row assets corroboration (Gate 1), ratio 1.45 → repaired.
    """
    ni_v = [100e6] * 5

    # Case A: ratio 1.24 — passes CLASSB_SOLO_TIGHT=1.25
    # Left flank adjacent = 1.24e9 = artifact×1e3×1.24 → ratio=1.24
    # Right flank adjacent = 1.24e9 same
    assets_a = [2.0e9, 2.0e9, 2.0e9, 2.0e9, 2.0e9]
    equity_a = [800e6, 820e6, 840e6, 860e6, 880e6]
    debt_lt_a = [1.24e9, 1.24e9, 1.0e6, 1.24e9, 1.24e9]

    pA = _panel("BDA", assets_a, fy0=2017,
                equity=equity_a, debt_lt=debt_lt_a, ni=ni_v)
    healedA, auditA = apply_stock_quality(pA, statements=None)
    art_a = healedA[healedA.fy == 2019].iloc[0]
    # Artifact=1.0e6; repaired = 1.0e6×1e3 = 1.0e9; flank=1.24e9; snap ratio=1.24 ≤ 1.25
    assert np.isclose(art_a["debt_lt"], 1.0e9, rtol=1e-4), \
        f"Case A (ratio 1.24): should be repaired to 1.0e9, got {art_a['debt_lt']}"

    # Case B: ratio 1.26 — fails CLASSB_SOLO_TIGHT=1.25
    debt_lt_b = [1.26e9, 1.26e9, 1.0e6, 1.26e9, 1.26e9]
    pB = _panel("BDB", assets_a, fy0=2017,
                equity=equity_a, debt_lt=debt_lt_b, ni=ni_v)
    healedB, auditB = apply_stock_quality(pB, statements=None)
    art_b = healedB[healedB.fy == 2019].iloc[0]
    assert np.isclose(art_b["debt_lt"], 1.0e6, rtol=1e-4), \
        f"Case B (ratio 1.26): must NOT be repaired, got {art_b['debt_lt']}"
    b_flags = [r for r in auditB["rows"]
               if r["ticker"] == "BDB" and r["col"] == "debt_lt"]
    assert not b_flags, f"Case B should produce no repair: {b_flags}"

    # Case C: same-row assets corroboration (Gate 1) → uses TIGHT_ADJ=1.5
    # Assets also ×1e3 low → repaired first, then equity uses Gate 1 at ratio 1.45
    assets_c  = [2.0e9, 2.0e9, 2.0e6, 2.0e9, 2.0e9]   # assets artifact
    equity_c  = [1.45e9, 1.45e9, 1.0e6, 1.45e9, 1.45e9]  # equity artifact at ratio 1.45
    debt_lt_c = [500e6] * 5  # clean
    pC = _panel("BDC", assets_c, fy0=2017,
                equity=equity_c, debt_lt=debt_lt_c, ni=ni_v)
    healedC, auditC = apply_stock_quality(pC, statements=None)
    art_c = healedC[healedC.fy == 2019].iloc[0]
    # assets must be repaired first
    assert np.isclose(art_c["assets"], 2.0e9, rtol=1e-4), \
        f"Case C: assets should be repaired, got {art_c['assets']}"
    # equity artifact=1.0e6, repaired=1.0e6×1e3=1.0e9; flank=1.45e9; snap ratio=1.45 ≤ TIGHT_ADJ=1.5
    assert np.isclose(art_c["equity"], 1.0e9, rtol=1e-4), \
        f"Case C (Gate 1, ratio 1.45): equity should be repaired to 1.0e9, got {art_c['equity']}"


# Test 4: AMD-class real de-lever — never repaired under any gate
# ---------------------------------------------------------------------------
def test_amd_class_real_delever_not_repaired():
    """debt_lt 3.3e8 → 1e6 → 2.467e9 (scaled ratios 3.0/2.5 > CLASSB_SOLO_TIGHT).
    Not corroborated (assets and equity are clean, no same-row assets artifact).
    Must never be repaired under any gate."""
    assets_vals = [2.0e9, 2.1e9, 2.2e9, 2.3e9, 2.4e9]
    equity_vals = [800e6, 820e6, 840e6, 860e6, 880e6]
    # Flanks: 3.3e8 (left) and 2.467e9 (right)
    # Scaled at 1e3: 1e6×1e3=1e9; ratio vs left = max(1e9/3.3e8, 3.3e8/1e9) = 3.03
    #               ratio vs right = max(1e9/2.467e9, 2.467e9/1e9) = 2.47
    # Both > CLASSB_SOLO_TIGHT=1.25 AND > TIGHT_ADJ=1.5 → not repaired
    debt_lt_vals = [3.3e8, 3.3e8, 1.0e6, 2.467e9, 2.467e9]
    ni_vals_t   = [50e6, 55e6, 60e6, 65e6, 70e6]

    p = _panel("AMDC", assets_vals, fy0=2019,
               equity=equity_vals, debt_lt=debt_lt_vals, ni=ni_vals_t)

    _, audit = apply_stock_quality(p, statements=None)
    amd_flags = [r for r in audit["rows"]
                 if r["ticker"] == "AMDC" and r["col"] == "debt_lt"]
    assert not amd_flags, \
        f"AMD-class real de-lever must not be repaired: {amd_flags}"


# Test 5: all-anchors-absent → NOT repaired (FIX 2)
# ---------------------------------------------------------------------------
def test_all_anchors_absent_rejects():
    """assets 5e9 → 5e3 → 5e9 with revenue/ni/cfo/shares all NaN.
    FIX 2: _anchor_cont_ok now returns False when no anchors are present on
    either side → repair is rejected to flank_suspects."""
    assets_vals = [5.0e9, 5.0e9, 5.0e3, 5.0e9, 5.0e9]
    # All anchors absent — pass explicit NaN revenue and ni
    rev_nan  = [np.nan] * 5
    ni_nan   = [np.nan] * 5

    p = _panel("NOAN", assets_vals, fy0=2017,
               revenue=rev_nan, ni=ni_nan)
    # Also clear the default ni by using the override; cfo/shares absent by default

    _, audit = apply_stock_quality(p, statements=None)
    noan_flags = [r for r in audit["rows"]
                  if r["ticker"] == "NOAN" and r["col"] == "assets"]
    assert not noan_flags, \
        f"All-anchors-absent: repair must be rejected: {noan_flags}"

    # Should appear in flank_suspects (ratio ≈ 1e6 >> SUSPECTS_MIN_BREAK=500)
    noan_suspects = [s for s in audit["flank_suspects"]
                     if s["ticker"] == "NOAN" and s["col"] == "assets"]
    assert noan_suspects, \
        "All-anchors-absent artifact should appear in flank_suspects"


# Test 6: ATO-class regression — assets via Class A, equity+debt_lt via Gate 1
# ---------------------------------------------------------------------------
def test_ato_class_gate1_corroboration():
    """ATO fy2010 triple artifact: assets×1e3 low, equity×1e3 low, debt_lt×1e3 low.
    After FIX 1, equity and debt_lt must be repaired via Gate 1 (same-row assets
    corroboration), evidenced by 'corr:same_row_assets' in the note string.
    All three repairs must still fire; audit shows 3 repaired rows + 1 mirror."""
    assets  = [5.5e9, 6.367e9, 7.2216e6, 7.6356e9, 7.964e9]
    equity  = [1.8e9, 2.177e9, 2.2749e6, 2.2678e9, 2.424e9]
    debt_lt = [1.9e9, 2.169e9, 1.8073e6, 2.206e9,  1.956e9]
    rev     = [np.nan, np.nan, np.nan, np.nan, np.nan]
    ni_vals = [190e6, 191e6, 205.839e6, 207.601e6, 216.717e6]
    shares_vals = [np.nan, np.nan, 90648911.0, 90016074.0, 90517509.0]
    ap = [np.nan, np.nan, 6.367e9, 7.2216e6, 7.6356e9]

    p = _panel("ATOG", assets, fy0=2008,
               equity=equity, debt_lt=debt_lt, revenue=rev,
               ni=ni_vals, shares=shares_vals, assets_prior=ap)

    healed, audit = apply_stock_quality(p, statements=None)

    art = healed[healed.fy == 2010].iloc[0]
    assert np.isclose(art["assets"],  7.2216e9, rtol=1e-4), \
        f"ATO-class assets not repaired: {art['assets']}"
    assert np.isclose(art["equity"],  2.2749e9, rtol=1e-4), \
        f"ATO-class equity not repaired: {art['equity']}"
    assert np.isclose(art["debt_lt"], 1.8073e9, rtol=1e-4), \
        f"ATO-class debt_lt not repaired: {art['debt_lt']}"

    # equity and debt_lt notes should indicate Gate 1 corroboration
    rows_2010 = [r for r in audit["rows"] if r["ticker"] == "ATOG" and r["fy"] == 2010]
    eq_rows  = [r for r in rows_2010 if r["col"] == "equity"]
    dlt_rows = [r for r in rows_2010 if r["col"] == "debt_lt"]
    assert eq_rows and "corr:same_row_assets" in eq_rows[0]["note"], \
        f"equity repair should carry Gate-1 corroboration note: {eq_rows}"
    assert dlt_rows and "corr:same_row_assets" in dlt_rows[0]["note"], \
        f"debt_lt repair should carry Gate-1 corroboration note: {dlt_rows}"

    assert audit["repaired"] == 3, f"expected 3 repairs, got {audit['repaired']}"
    assert audit["mirrors"] == 1, f"expected 1 mirror, got {audit['mirrors']}"


# ---------------------------------------------------------------------------
# Gate 1 corroboration must also fire from an XSRC-sourced assets repair
# (not only a flank-lane one): same filing, same mis-scaled unit, regardless
# of which lane confirmed the assets mis-scale.
# ---------------------------------------------------------------------------
def test_classb_gate1_corroboration_from_xsrc_assets():
    """Assets artifact repaired by the xsrc lane (statements confirms ×1e3);
    same-row equity artifact snaps at ratio 1.4 — inside Gate 1's TIGHT_ADJ=1.5
    but outside the standalone CLASSB_SOLO_TIGHT=1.25.  Equity must be repaired
    with the corr:same_row_assets note.  Statements carries no equity value
    (absent), so neither PROTECTED nor the Gate 2b statements check interferes."""
    assets_p = [2.0e9, 2.0e9, 2.0e6, 2.0e9, 2.0e9]     # fy2019 artifact
    assets_s = [2.0e9, 2.0e9, 2.0e9, 2.0e9, 2.0e9]     # statements: correct scale
    equity_p = [1.4e9, 1.4e9, 1.0e6, 1.4e9, 1.4e9]     # same-row artifact, ratio 1.4
    ni_v = [150e6] * 5

    p = _panel("XCOR", assets_p, fy0=2017, equity=equity_p, ni=ni_v)
    st = _statements("XCOR", assets_s, fy0=2017,
                     equity=[None] * 5)                 # equity absent in statements

    healed, audit = apply_stock_quality(p, statements=st)

    art = healed[healed.fy == 2019].iloc[0]
    assert np.isclose(art["assets"], 2.0e9, rtol=1e-6), \
        f"assets should be xsrc-repaired: {art['assets']}"
    assert "xsrc_scale" in str(art["stock_flag"]), \
        f"assets repair should come from the xsrc lane: {art['stock_flag']}"
    assert np.isclose(art["equity"], 1.0e9, rtol=1e-4), \
        f"equity (ratio 1.4) should be Gate-1 repaired via xsrc corroboration: {art['equity']}"
    eq_rows = [r for r in audit["rows"]
               if r["ticker"] == "XCOR" and r["fy"] == 2019 and r["col"] == "equity"]
    assert eq_rows and "corr:same_row_assets" in eq_rows[0]["note"], \
        f"equity repair should carry Gate-1 corroboration note: {eq_rows}"
