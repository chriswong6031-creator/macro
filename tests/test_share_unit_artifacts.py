"""Share-count unit-artifact detector/repair (collectors/edgar_share_quality).

Synthetic panels only — no network, no committed-data reads. Each fixture is a
minimal reconstruction of a defect class observed in the real panel (tickers in
comments), plus the confusable REAL patterns the detector must leave alone:
genuine splits, genuine dilutions, reverse-split-then-issuance valleys (HTZ),
real sub-15M share counts held for years (Skyline). PIT honesty is pinned
structurally: every repair value must equal the row's own value x 10^k, the
same-FY DEI count, or a PRIOR year's clean count — never a later year's value.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from collectors.edgar_share_quality import (
    apply_share_quality, detect, suspicious_tickers)


def _panel(ticker: str, shares: list, equity: list | None = None,
           assets: list | None = None, fy0: int = 2010,
           shares_dei: list | None = None) -> pd.DataFrame:
    n = len(shares)
    eq = equity if equity is not None else [1e9 * 1.05 ** i for i in range(n)]
    at = assets if assets is not None else [3e9 * 1.05 ** i for i in range(n)]
    rows = []
    for i in range(n):
        rows.append({"ticker": ticker, "cik": 1, "fy": fy0 + i,
                     "shares": shares[i], "equity": eq[i], "assets": at[i],
                     "period_end": pd.Timestamp(f"{fy0 + i}-12-31")})
        if shares_dei is not None:
            rows[-1]["shares_dei"] = shares_dei[i]
    p = pd.DataFrame(rows)
    p["asof_date"] = p["period_end"] + pd.Timedelta(days=120)
    return p


def _flags(p, reference=None):
    f = detect(p, reference=reference)
    return {(r["ticker"], r["fy"]): r for _, r in f.iterrows()}


# --------------------------------------------------------------------------- #
# unit_level — the ED class
# --------------------------------------------------------------------------- #
def test_ed_valley_repaired_by_carry_forward():
    # ED fy2010-15: shares ~13x low for six years, equity seamless
    sh = [281e6] + [22e6] * 6 + [305e6, 310e6, 320e6]
    p = _panel("ED", sh)
    healed, audit = apply_share_quality(p)
    mid = healed[(healed.fy >= 2011) & (healed.fy <= 2016)]
    assert (mid["share_flag"] == "unit_level").all()
    assert (mid["shares"] == 281e6).all()          # last clean PRIOR value only
    assert (mid["shares_raw"] == 22e6).all()
    clean = healed[(healed.fy == 2010) | (healed.fy >= 2017)]
    assert clean["share_flag"].isna().all() and (clean["shares"] == clean["shares_raw"]).all()
    assert audit["by_flag"] == {"unit_level": 6}


def test_unit_level_prefers_same_fy_dei_count():
    sh = [281e6] + [22e6] * 3 + [305e6]
    dei = [np.nan, 285e6, 288e6, 291e6, np.nan]
    p = _panel("ED", sh, shares_dei=dei)
    healed, _ = apply_share_quality(p)
    mid = healed[(healed.fy >= 2011) & (healed.fy <= 2013)]
    assert list(mid["shares"]) == [285e6, 288e6, 291e6]   # contemporaneous DEI


def test_unit_level_blocked_by_matching_real_split():
    # same valley shape but a real 1:13 reverse split near the entry boundary
    # (and matching forward near exit) — basis change, not an artifact
    sh = [281e6] + [22e6] * 2 + [285e6]
    ref = {"tickers": {"XX": {"first_trade": "1990-01-01",
                              "splits": {"2011-02-01": 1 / 13.0,
                                         "2013-03-01": 13.0}}}}
    p = _panel("XX", sh)
    assert _flags(p, ref) == {}


def test_htz_reverse_split_then_issuance_valley_not_flagged():
    # HTZ 2016-20: real 1-for-5 reorg then bankruptcy-exit issuance; equity
    # explodes at the exit boundary -> no unit_level (equity not continuous)
    eq = [4e9, 4.1e9, 2e9, 1.5e9, 1e9, 0.1e9, 5.3e9, 5.5e9]
    sh = [423e6, 440e6, 84e6, 85e6, 86e6, 84e6, 311e6, 320e6]
    p = _panel("HTZ", sh, equity=eq)
    assert not any(r["flag"] == "unit_level" for r in _flags(p).values())


# --------------------------------------------------------------------------- #
# unit_scale — power-of-ten typos
# --------------------------------------------------------------------------- #
def test_interior_thousands_typo_scale_repaired():
    # GRMN class: five years reported in thousands
    sh = [195.4e6, 195.2e6, 195.15e3, 191.8e3, 189.7e3, 188.2e3, 189.0e6]
    p = _panel("GRMN", sh)
    healed, _ = apply_share_quality(p)
    mid = healed[(healed.fy >= 2012) & (healed.fy <= 2015)]
    assert (mid["share_flag"] == "unit_scale").all()
    assert list(mid["shares"]) == [195.15e6, 191.8e6, 189.7e6, 188.2e6]


def test_alternating_scale_artifacts_flag_only_wrong_rows():
    # SXI class: 1e10-scale islands around a correct row
    sh = [12.6e6, 12.59e6, 12.70e9, 12.66e6, 12.71e9, 12.04e6, 12.0e6]
    p = _panel("SXI", sh)
    healed, _ = apply_share_quality(p)
    bad = healed[healed.fy.isin([2012, 2014])]
    good = healed[~healed.fy.isin([2012, 2014])]
    assert (bad["share_flag"] == "unit_scale").all()
    assert np.allclose(bad["shares"], [12.70e6, 12.71e6])
    assert good["share_flag"].isna().all()


def test_leading_and_trailing_scale_typos_repaired():
    # QCOM fy2009 (x1e6 low lead) / CPK fy2023+ (x1e3 high tail)
    lead = _panel("QCOM", [1674.0, 1.634e9, 1.687e9, 1.716e9])
    healed, _ = apply_share_quality(lead)
    assert healed.loc[healed.fy == 2010, "shares"].iloc[0] == pytest.approx(1.674e9)
    tail = _panel("CPK", [16.3e6, 16.4e6, 17.4e6, 17.7e6, 17.8e9, 22.8e9])
    healed2, _ = apply_share_quality(tail)
    t = healed2[healed2.fy >= 2014]
    assert (t["share_flag"] == "unit_scale").all()
    assert np.allclose(t["shares"], [17.8e6, 22.8e6])
    assert healed2[healed2.fy < 2014]["share_flag"].isna().all()


def test_unit_extreme_nulls_when_snap_not_confident():
    # RTX fy2009: junk 1.38e6 whose x1e3 lands 1.5x from the flank — null, not
    # a guessed repair
    p = _panel("RTX", [1.3817e6, 920e6, 907e6, 916e6])
    healed, _ = apply_share_quality(p)
    row = healed[healed.fy == 2010].iloc[0]
    assert row["share_flag"] == "unit_extreme" and pd.isna(row["shares"])


def test_genuine_forward_split_untouched():
    # single 4:1 boundary, equity continuous — the split lane's territory
    p = _panel("SPLT", [50e6, 51e6, 52e6, 208e6, 209e6])
    assert _flags(p) == {}


def test_genuine_large_dilution_untouched():
    # 3.5x issuance with equity jump — real capital raise
    eq = [1e9, 1.05e9, 3.6e9, 3.7e9]
    p = _panel("DIL", [50e6, 52e6, 180e6, 182e6], equity=eq)
    assert _flags(p) == {}


# --------------------------------------------------------------------------- #
# placeholder — registration-statement counts
# --------------------------------------------------------------------------- #
def test_placeholder_rows_nulled_or_snapped():
    # OGS class: "100 shares" against $4B assets -> null; AAP class: thousands
    # count that snaps onto the flank -> repaired
    p1 = _panel("OGS", [100.0, 52.1e6, 52.3e6], assets=[4e9, 4.1e9, 4.2e9])
    healed1, _ = apply_share_quality(p1)
    r = healed1[healed1.fy == 2010].iloc[0]
    assert r["share_flag"] == "placeholder" and pd.isna(r["shares"])
    p2 = _panel("AAP", [93.6e3, 82.0e3, 72.8e6, 73.4e6], assets=[3e9] * 4)
    healed2, _ = apply_share_quality(p2)
    fixed = healed2[healed2.fy <= 2011]
    assert (fixed["share_flag"] == "placeholder").all()
    assert np.allclose(fixed["shares"], [93.6e6, 82.0e6])


def test_small_company_small_counts_not_placeholder():
    # a real 90k-share row on a $50M filer is not our business
    p = _panel("TINY", [90e3, 92e3, 94e3], assets=[5e7, 5.2e7, 5.4e7])
    assert _flags(p) == {}


# --------------------------------------------------------------------------- #
# pre_public — first-trade reference
# --------------------------------------------------------------------------- #
def test_pre_public_rows_nulled_by_first_trade():
    # ROKU class: fy2016 filed by a company that first traded 2017-09
    ref = {"tickers": {"ROKU": {"first_trade": "2017-09-28", "splits": {}}}}
    p = _panel("ROKU", [4.8e6, 99e6, 110e6, 120e6], fy0=2016)
    healed, _ = apply_share_quality(p, ref)
    r = healed[healed.fy == 2016].iloc[0]
    assert r["share_flag"] == "pre_public" and pd.isna(r["shares"])
    assert healed[healed.fy >= 2017]["share_flag"].isna().all()


def test_no_reference_entry_means_no_pre_public_flag():
    p = _panel("ROKU", [4.8e6, 99e6, 110e6, 120e6], fy0=2016)
    f = _flags(p, {"tickers": {}})
    assert not any(r["flag"] == "pre_public" for r in f.values())


def test_long_listed_name_exempt_from_pre_public():
    ref = {"tickers": {"ED": {"first_trade": "1985-01-01", "splits": {}}}}
    p = _panel("ED", [280e6, 285e6, 290e6])
    assert _flags(p, ref) == {}


# --------------------------------------------------------------------------- #
# pre_public_tiny — founder/SPAC counts that outlive the IPO
# --------------------------------------------------------------------------- #
def _ahco_panel():
    # AHCO: three ~7.2M founder rows (equity sign flip at exit), a NaN year,
    # then the real ~134M basis. yfinance carries the SPAC price era, so
    # first_trade predates the later rows — only the tiny rule catches them.
    eq = [2.4e4, 5.0e6, -38.8e6, 354.9e6, 2.06e9, 2.15e9]
    sh = [7.19e6, 7.20e6, 7.19e6, np.nan, 133.8e6, 134.4e6]
    return _panel("AHCO", sh, equity=eq, fy0=2017)


def test_spac_founder_counts_nulled_across_nan_gap():
    ref = {"tickers": {"AHCO": {"first_trade": "2018-05-01", "splits": {}}}}
    healed, _ = apply_share_quality(_ahco_panel(), ref)
    tiny = healed[healed.fy <= 2019]
    assert tiny["share_flag"].isin(["pre_public", "pre_public_tiny"]).all()
    assert tiny["shares"].isna().all()
    assert healed[healed.fy >= 2021]["share_flag"].isna().all()


def test_reverse_split_makes_tiny_count_legitimate():
    # CPF: 1:20 reverse split right before the tiny fy row — count is real
    eq = [65e6, 400e6, 420e6, 440e6]
    p = _panel("CPF", [1.527e6, 28.9e6, 29.0e6, 29.1e6], equity=eq)
    ref = {"tickers": {"CPF": {"first_trade": "1987-08-01",
                               "splits": {"2011-02-03": 0.05}}}}
    assert _flags(p, ref) == {}


def test_stable_tiny_count_held_for_years_not_flagged():
    # Skyline: 8.39M real shares for 7 filings, then a real merger 6.7x-es it
    eq = [65e6, 51e6, 42e6, 27e6, 20e6, 15e6, 60e6, 450e6, 460e6]
    sh = [8.39e6] * 7 + [56.6e6, 56.7e6]
    p = _panel("SKY", sh, equity=eq)
    assert not any(r["flag"] == "pre_public_tiny" for r in _flags(p).values())


def test_rop_straddle_converges_to_full_repair():
    # ROP class: an in-thousands segment straddles the 1e5 placeholder cutoff.
    # Round 1 repairs the sub-1e5 row as placeholder; only then do the ~100k
    # rows become a visible interior scale segment (reviewer finding B1).
    sh = [96.0e6, 98.0e6, 99.312e3, 100.126e3, 100.870e3, 101.672e6, 103.0e6]
    p = _panel("ROP", sh, assets=[9e9] * 7)
    healed, _ = apply_share_quality(p)
    fixed = healed[(healed.fy >= 2012) & (healed.fy <= 2014)]
    assert fixed["share_flag"].notna().all()
    assert np.allclose(fixed["shares"], [99.312e6, 100.126e6, 100.870e6])


def test_noisy_history_carry_forward_uses_adjacent_clean_row():
    # ASTH class (reviewer finding B3): many candidate segments; the artifact
    # row's carry-forward must come from the ADJACENT unflagged prior row, not
    # from a distant segment that survived the candidate filter.
    #   2010-12: ~34.8M | 2013: 4.86M (real reverse-split era, ambiguous,
    #   protected by equity discontinuity) ... 2016-22: ~46.6M (real basis)
    #   2023: 500k artifact | 2024-25: ~47.9M
    sh = [34.8e6, 34.8e6, 34.9e6, 4.86e6, 40.0e6, 42.0e6, 44.0e6, 46.0e6,
          46.3e6, 46.58e6, 0.5e6, 47.9e6, 48.0e6]
    eq = [80e6, 82e6, 84e6, 20e6, 300e6, 320e6, 340e6, 360e6,
          380e6, 400e6, 420e6, 440e6, 460e6]
    p = _panel("ASTH", sh, equity=eq)
    healed, _ = apply_share_quality(p)
    row = healed[healed.fy == 2020].iloc[0]
    assert row["share_flag"] == "unit_level"
    assert row["shares"] == 46.58e6                # adjacent prior, not 34.8M


def test_long_public_tiny_count_exposed_by_earlier_null_not_flagged():
    # ADAM class: after a leading 1000x row is nulled, the next row (a real
    # tiny count of a company public since 2004) becomes the leading segment;
    # the long-public exemption must keep pre_public_tiny off it.
    sh = [9.43e9, 13.9e6, 49.6e6, 64.1e6, 105.1e6]
    eq = [68e6, 85e6, 322e6, 481e6, 818e6]
    ref = {"tickers": {"ADAM": {"first_trade": "2004-07-01", "splits": {}}}}
    p = _panel("ADAM", sh, equity=eq)
    healed, _ = apply_share_quality(p, ref)
    lead = healed[healed.fy == 2010].iloc[0]
    assert lead["share_flag"] == "unit_extreme" and pd.isna(lead["shares"])
    assert healed[healed.fy >= 2011]["share_flag"].isna().all()


# --------------------------------------------------------------------------- #
# apply semantics
# --------------------------------------------------------------------------- #
def test_apply_is_idempotent_and_preserves_raw():
    p = _panel("ED", [281e6] + [22e6] * 6 + [305e6, 310e6, 320e6])
    once, audit1 = apply_share_quality(p)
    twice, audit2 = apply_share_quality(once)
    pd.testing.assert_frame_equal(once, twice)
    assert audit2["rows_flagged"] == 0             # nothing new on a healed panel
    assert (twice["shares_raw"][twice["share_flag"] == "unit_level"] == 22e6).all()


def test_repairs_never_use_future_values():
    # structural PIT pin: every repaired value equals the row's own value x10^k
    # or a value knowable at or before the row's asof (prior clean count / DEI)
    sh = [281e6] + [22e6] * 6 + [305e6, 310e6, 320e6]
    p = _panel("ED", sh)
    f = detect(p)
    for _, r in f.iterrows():
        if pd.isna(r["repair"]):
            continue
        own_scaled = any(np.isclose(r["repair"], r["shares"] * 10.0 ** k)
                         for k in (3, 6, 9, -3, -6, -9))
        prior_fy = p[(p.fy < r["fy"]) & (p.shares == r["repair"])]
        assert own_scaled or len(prior_fy), \
            f"repair for fy{r['fy']} is not PIT-knowable"


def test_other_columns_untouched_and_only_shares_mutated():
    p = _panel("ED", [281e6] + [22e6] * 3 + [305e6])
    healed, _ = apply_share_quality(p)
    for col in ("equity", "assets", "ni", "period_end", "asof_date"):
        if col in p.columns:
            pd.testing.assert_series_equal(p[col], healed[col], check_names=False)


def test_suspicious_tickers_selects_lookup_candidates():
    jumpy = _panel("JMP", [5e6, 60e6, 61e6])       # >=3x jump
    calm = _panel("CLM", [50e6, 51e6, 52e6])
    late = _panel("NEW", [30e6, 31e6], fy0=2024)   # recent history start
    p = pd.concat([jumpy, calm, late], ignore_index=True)
    sus = suspicious_tickers(p)
    assert "JMP" in sus and "NEW" in sus and "CLM" not in sus


def test_detect_requires_panel_columns():
    with pytest.raises(ValueError):
        detect(pd.DataFrame({"ticker": ["A"], "fy": [2020]}))
