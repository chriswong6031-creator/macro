"""
a2_oos_analysis.py — A2 OOS-analysis harness for the Long-Hold Thesis Layer.

Authority: AMENDMENT_A2_G1_RETEST.md, AMENDMENT_LH_R11_MULTI_FAMILY.md, and the
four family pre-registrations (OBJECTIVE.md §5, WASHOUT_TIMEFRAME_HYPOTHESIS.md,
EXPECT_DRIFT_FAMILY_PREREG.md, INSIDER_SPONSOR_LH_FAMILY_PREREG.md).

FREEZE ANCHOR (LH-R11.1): the commit of THIS file is the roster freeze anchor.
No family may be added to or removed from the roster after this commit without
a ratified amendment. The in-code ROSTER table below is the authoritative frozen
record.

NO-RUN GATE: the outcome-contact stage (feature-vs-label statistics on OOS-2)
REFUSES TO RUN unless BOTH conditions are met:
  1. honest compounder episode-cluster count (from W1 clustering) >= 25
  2. --operator-ack flag is explicitly passed

This refusal is unconditional and untunable. There is no environment variable
or config knob that bypasses it.

Usage (display / prep stage — always safe):
    python scripts/research/a2_oos_analysis.py --mode=prep

Usage (outcome-contact stage — gated):
    python scripts/research/a2_oos_analysis.py --mode=run --operator-ack \
        --cluster-count=<N>

The --cluster-count argument must be supplied for --mode=run; it must come from
the honest compounder episode-cluster count computed via the registered clustering
(name x macro-regime, ±10d) from W1. The operator is responsible for computing
this count honestly before invoking the flag.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional

# ---------------------------------------------------------------------------
# FROZEN ROSTER (LH-R11.1 freeze anchor)
#
# Transcribed from pre-registration documents. Do NOT edit without a ratified
# amendment. A reviewer must diff this table against the source documents.
#
# Source documents:
#   F1 — research/long_hold/OBJECTIVE.md §5
#   F2 — research/long_hold/WASHOUT_TIMEFRAME_HYPOTHESIS.md §4
#   F3 — research/long_hold/EXPECT_DRIFT_FAMILY_PREREG.md §2
#   F4 — research/long_hold/INSIDER_SPONSOR_LH_FAMILY_PREREG.md §2
# ---------------------------------------------------------------------------

ROSTER_VERSION = "2026-07-06"

# Each entry: (hypothesis_id, family_id, feature_name, feature_type, expected_sign,
#              test_statistic, restricted_range, feature_provenance)
#
# expected_sign: '+', '-', 'two-sided'
# test_statistic: 'MWU/RBC', 'Fisher', 'chi2'
# restricted_range: True if the feature carries LH-R11.3 restricted_range stamp
# feature_provenance: comma-separated data sources per LH-R11.3

ROSTER: list[dict] = [
    # -------------------------------------------------------------------
    # F1 — long_hold.fundamental (m=9)
    # Authority: OBJECTIVE.md §5 (frozen W1 list)
    # Notes: Coverage-restored per retest prep list. Dropped-for-coverage
    #        features remain in Σ denominator (LH-R11.2). op_income
    #        un-aliases quality_z ≡ profitability_z; interest_exp restores
    #        interest_coverage; insider_cmp restored via F4 data lane
    #        (remains an F1 hypothesis, m unchanged); archetype joined from
    #        history parquet.
    # -------------------------------------------------------------------
    {
        "hypothesis_id": "F1-01",
        "family": "long_hold.fundamental",
        "feature": "piotroski_f",
        "type": "cont",
        "direction": "+",
        "test": "MWU/RBC",
        "restricted_range": False,
        "feature_provenance": "fundamentals_panel(period_end+120d PIT)",
        "notes": "PIT via period_end + 120d; primary composit quality score",
    },
    {
        "hypothesis_id": "F1-02",
        "family": "long_hold.fundamental",
        "feature": "quality_z",
        "type": "cont",
        "direction": "+",
        "test": "MWU/RBC",
        "restricted_range": False,
        "feature_provenance": "fundamentals_panel(as_of cross-section)",
        "notes": "As-of cross-section; op_income lane un-aliases profitability_z",
    },
    {
        "hypothesis_id": "F1-03",
        "family": "long_hold.fundamental",
        "feature": "profitability_z",
        "type": "cont",
        "direction": "+",
        "test": "MWU/RBC",
        "restricted_range": False,
        "feature_provenance": "fundamentals_panel(as_of cross-section)",
        "notes": "As-of cross-section",
    },
    {
        "hypothesis_id": "F1-04",
        "family": "long_hold.fundamental",
        "feature": "sue",
        "type": "cont",
        "direction": "+",
        "test": "MWU/RBC",
        "restricted_range": False,
        "feature_provenance": "fundamentals_panel(most-recent quarter at fire_date PIT)",
        "notes": "Standardized unexpected earnings, most-recent quarter at fire date",
    },
    {
        "hypothesis_id": "F1-05",
        "family": "long_hold.fundamental",
        "feature": "insider_cmp",
        "type": "bin",
        "direction": "+",
        "test": "Fisher",
        "restricted_range": False,
        "feature_provenance": "sec_insider_panel(2006q1→, filing_date PIT)",
        "notes": "Cluster-matched purchase signal; data lane shared with F4; hypothesis stays F1",
    },
    {
        "hypothesis_id": "F1-06",
        "family": "long_hold.fundamental",
        "feature": "interest_coverage",
        "type": "cont",
        "direction": "+",
        "test": "MWU/RBC",
        "restricted_range": False,
        "feature_provenance": "fundamentals_panel(op_income/interest_exp PIT)",
        "notes": "op_income / interest_exp; available where interest_exp > 0; restored per retest prep",
    },
    {
        "hypothesis_id": "F1-07",
        "family": "long_hold.fundamental",
        "feature": "dilution_flag",
        "type": "bin",
        "direction": "-",
        "test": "Fisher",
        "restricted_range": False,
        "feature_provenance": "fundamentals_panel(shares YoY PIT)",
        "notes": "shares YoY > +3% threshold; negative expected sign (dilution = bad)",
    },
    {
        "hypothesis_id": "F1-08",
        "family": "long_hold.fundamental",
        "feature": "gross_margin_trend",
        "type": "cont",
        "direction": "+",
        "test": "MWU/RBC",
        "restricted_range": False,
        "feature_provenance": "fundamentals_panel(gross_profit/revenue 3yr slope PIT)",
        "notes": "3-year slope of gross_profit/revenue",
    },
    {
        "hypothesis_id": "F1-09",
        "family": "long_hold.fundamental",
        "feature": "archetype",
        "type": "cat",
        "direction": "+",
        "test": "Fisher",
        "restricted_range": False,
        "feature_provenance": "fundamentals_panel(history parquet join)",
        "notes": "Archetype class; joined from history parquet per retest prep",
    },
    # -------------------------------------------------------------------
    # F2 — long_hold.washout_tf (m=10)
    # Authority: WASHOUT_TIMEFRAME_HYPOTHESIS.md §4
    # Notes: Admitted per LH-R11 application §4. LH-R11.3 stamps apply:
    #        depth features (#5/#6) carry restricted_range; positive
    #        survivor-only depth results route to DEFERRED never SURVIVE.
    #        B1 data block acknowledged (monthly-bar maturity).
    #        Test statistic deviation from §6.4: binary features use
    #        Fisher/chi2, NOT MWU (degenerate on 0/1).
    #        Two-sided depth features spend two-sided alpha (N2).
    # -------------------------------------------------------------------
    {
        "hypothesis_id": "F2-01",
        "family": "long_hold.washout_tf",
        "feature": "stochrsi_m_k",
        "type": "cont",
        "direction": "-",
        "test": "MWU/RBC",
        "restricted_range": False,
        "feature_provenance": "price_series(monthly_resample,shift1)",
        "notes": "Monthly %K, prior fully-closed bar (.shift(1)); more oversold -> +missed_hold",
    },
    {
        "hypothesis_id": "F2-02",
        "family": "long_hold.washout_tf",
        "feature": "washout_m_active",
        "type": "bin",
        "direction": "+",
        "test": "Fisher",
        "restricted_range": False,
        "feature_provenance": "price_series(monthly_resample,shift1)",
        "notes": "Monthly %K<20 on >=2 of last 3 closed monthly bars; Fisher not MWU (M2 deviation)",
    },
    {
        "hypothesis_id": "F2-03",
        "family": "long_hold.washout_tf",
        "feature": "washout_w_active",
        "type": "bin",
        "direction": "+",
        "test": "Fisher",
        "restricted_range": False,
        "feature_provenance": "price_series(weekly_resample,shift1)",
        "notes": "Weekly %K<20 on >=2 of last 3 closed weekly bars; Fisher not MWU (M2 deviation)",
    },
    {
        "hypothesis_id": "F2-04",
        "family": "long_hold.washout_tf",
        "feature": "mtf_washout_count",
        "type": "ord",
        "direction": "+",
        "test": "MWU/RBC",
        "restricted_range": True,
        "feature_provenance": "price_series(2D/3D+weekly+monthly)",
        "notes": "# of {2D/3D, weekly, monthly} washed at fire (0-3); restricted_range: left-truncated at 15% washout presence",
    },
    {
        "hypothesis_id": "F2-05",
        "family": "long_hold.washout_tf",
        "feature": "pct_below_200dma",
        "type": "cont",
        "direction": "two-sided",
        "test": "MWU/RBC",
        "restricted_range": True,
        "feature_provenance": "price_series(SMA200)",
        "notes": "(close-SMA200)/SMA200; two-sided alpha (N2); restricted_range; positive survivor-only result -> DEFERRED never SURVIVE (M3)",
    },
    {
        "hypothesis_id": "F2-06",
        "family": "long_hold.washout_tf",
        "feature": "drawdown_from_52wk_high",
        "type": "cont",
        "direction": "two-sided",
        "test": "MWU/RBC",
        "restricted_range": True,
        "feature_provenance": "price_series(52wk_high)",
        "notes": "close/52wk-high - 1; two-sided alpha (N2); restricted_range; positive survivor-only result -> DEFERRED never SURVIVE (M3)",
    },
    {
        "hypothesis_id": "F2-07",
        "family": "long_hold.washout_tf",
        "feature": "ma200_slope_up",
        "type": "bin",
        "direction": "+",
        "test": "Fisher",
        "restricted_range": False,
        "feature_provenance": "price_series(SMA200,20bar_slope)",
        "notes": "SMA200 20-bar slope >= 0 (turning up); disambiguates F2-05/F2-06; Fisher not MWU (M2 deviation)",
    },
    {
        "hypothesis_id": "F2-08",
        "family": "long_hold.washout_tf",
        "feature": "vel_3m_turn",
        "type": "bin",
        "direction": "+",
        "test": "Fisher",
        "restricted_range": False,
        "feature_provenance": "price_series(3mo_return)",
        "notes": "3-mo return rising vs 1-mo-prior; Fisher not MWU (M2 deviation)",
    },
    {
        "hypothesis_id": "F2-09",
        "family": "long_hold.washout_tf",
        "feature": "base_length_days",
        "type": "cont",
        "direction": "+",
        "test": "MWU/RBC",
        "restricted_range": False,
        "feature_provenance": "price_series(52wk_high_date)",
        "notes": "Trading days since 52wk high; left-censoring stamp N4",
    },
    {
        "hypothesis_id": "F2-10",
        "family": "long_hold.washout_tf",
        "feature": "deep_and_turning",
        "type": "bin",
        "direction": "+",
        "test": "Fisher",
        "restricted_range": False,
        "feature_provenance": "price_series(derived:washout_m_active AND ma200_slope_up)",
        "notes": "washout_m_active AND ma200_slope_up; single logical AND, no fitted cutoff (N1); Fisher not MWU (M2 deviation)",
    },
    # -------------------------------------------------------------------
    # F3 — long_hold.expect_drift (m=7)
    # Authority: EXPECT_DRIFT_FAMILY_PREREG.md §2
    # Notes: New (LT-2). Coordinates with species S9 per LH-R10.
    #        feature_provenance per LH-R11.3 B2 firewall declaration.
    # -------------------------------------------------------------------
    {
        "hypothesis_id": "ED-1",
        "family": "long_hold.expect_drift",
        "feature": "sue_latest",
        "type": "cont",
        "direction": "+",
        "test": "MWU/RBC",
        "restricted_range": False,
        "feature_provenance": "edgar_eps_quarterly(PIT)",
        "notes": "Most recent SUE_q visible at fire_date",
    },
    {
        "hypothesis_id": "ED-2",
        "family": "long_hold.expect_drift",
        "feature": "sue_streak",
        "type": "int",
        "direction": "+",
        "test": "MWU/RBC",
        "restricted_range": False,
        "feature_provenance": "edgar_eps_quarterly(PIT)",
        "notes": "Consecutive quarters with d_q > 0 ending at most recent visible quarter (cap 8)",
    },
    {
        "hypothesis_id": "ED-3",
        "family": "long_hold.expect_drift",
        "feature": "pead_drift",
        "type": "cont",
        "direction": "+",
        "test": "MWU/RBC",
        "restricted_range": False,
        "feature_provenance": "edgar_8k_202,label_panel_price_stores",
        "notes": "Cumulative stock-minus-benchmark return E(f)+1...min(E(f)+20,fire_date-1); >=5 elapsed sessions required",
    },
    {
        "hypothesis_id": "ED-4",
        "family": "long_hold.expect_drift",
        "feature": "bad_news_absorption",
        "type": "bin",
        "direction": "+",
        "test": "Fisher",
        "restricted_range": False,
        "feature_provenance": "edgar_8k_202,edgar_eps_quarterly,label_panel_price_stores",
        "notes": "Most recent d_q<0 AND no close in 10 sessions post-E(f) below 63-session min AND stock-minus-bench E(f)+1..E(f)+5 >= 0",
    },
    {
        "hypothesis_id": "ED-5",
        "family": "long_hold.expect_drift",
        "feature": "good_news_hold",
        "type": "bin",
        "direction": "+",
        "test": "Fisher",
        "restricted_range": False,
        "feature_provenance": "edgar_8k_202,edgar_eps_quarterly,label_panel_price_stores",
        "notes": "Most recent d_q>0 AND close(E(f)+1)/close(E(f))-1 >= +2% AND close(E(f)+10) >= close(E(f)+1)",
    },
    {
        "hypothesis_id": "ED-6",
        "family": "long_hold.expect_drift",
        "feature": "sue_accel",
        "type": "cont",
        "direction": "+",
        "test": "MWU/RBC",
        "restricted_range": False,
        "feature_provenance": "edgar_eps_quarterly(PIT)",
        "notes": "SUE_latest - SUE_prev (two most recent visible quarters); else missing",
    },
    {
        "hypothesis_id": "ED-7",
        "family": "long_hold.expect_drift",
        "feature": "confirmed_absorption",
        "type": "bin",
        "direction": "+",
        "test": "Fisher",
        "restricted_range": False,
        "feature_provenance": "edgar_8k_202,edgar_eps_quarterly,label_panel_price_stores",
        "notes": "(ED-4 OR ED-5) AND ED-3 > 0",
    },
    # -------------------------------------------------------------------
    # F4 — long_hold.insider_sponsor_lh (m=3)
    # Authority: INSIDER_SPONSOR_LH_FAMILY_PREREG.md §2
    # Notes: New (LT-3). Entry-ruler insider tests remain with ESX Amendment
    #        2 RUL-26 (different program, different ruler, no shared claims).
    #        Data lane shared with F1 insider_cmp restoration; F1's hypothesis
    #        remains registered under F1's m=9.
    # -------------------------------------------------------------------
    {
        "hypothesis_id": "IS-1",
        "family": "long_hold.insider_sponsor_lh",
        "feature": "insider_net_usd_mcap_6m_pct",
        "type": "cont",
        "direction": "+",
        "test": "MWU/RBC",
        "restricted_range": False,
        "feature_provenance": "sec_insider_panel(2006q1→, filing_date PIT),fundamentals_panel(shares),label_panel_price_stores(mcap close)",
        "notes": "Trailing 126-session net open-market insider dollars (sum_P - sum_S) / mcap, sector-neutral cross-sectional percentile",
    },
    {
        "hypothesis_id": "IS-2",
        "family": "long_hold.insider_sponsor_lh",
        "feature": "cluster_buy_pre_fire",
        "type": "bin",
        "direction": "+",
        "test": "Fisher",
        "restricted_range": False,
        "feature_provenance": "sec_insider_panel(2006q1→, filing_date PIT)",
        "notes": ">=2 distinct insider CIKs each with >=$25,000 open-market P buys, filing_date within [fire_date-63, fire_date]",
    },
    {
        "hypothesis_id": "IS-3",
        "family": "long_hold.insider_sponsor_lh",
        "feature": "officer_buy_flag",
        "type": "bin",
        "direction": "+",
        "test": "Fisher",
        "restricted_range": False,
        "feature_provenance": "sec_insider_panel(2006q1→, filing_date PIT)",
        "notes": ">=1 is_officer open-market P buy >=$25,000 in window [fire_date-63, fire_date]",
    },
]

# ---------------------------------------------------------------------------
# Roster integrity checks
# ---------------------------------------------------------------------------

EXPECTED_FAMILY_COUNTS = {
    "long_hold.fundamental": 9,       # F1
    "long_hold.washout_tf": 10,       # F2
    "long_hold.expect_drift": 7,      # F3
    "long_hold.insider_sponsor_lh": 3, # F4
}
EXPECTED_TOTAL = 29  # Σ across all families


def _validate_roster() -> None:
    """Assert roster counts match the pre-registered values. Fails loudly on mismatch."""
    from collections import Counter
    counts = Counter(h["family"] for h in ROSTER)
    for fam, expected_m in EXPECTED_FAMILY_COUNTS.items():
        actual = counts.get(fam, 0)
        if actual != expected_m:
            raise AssertionError(
                f"Roster integrity failure: family '{fam}' has {actual} hypotheses, "
                f"expected {expected_m} (pre-registered m). "
                f"Check transcription against source pre-registration documents."
            )
    total = len(ROSTER)
    if total != EXPECTED_TOTAL:
        raise AssertionError(
            f"Roster integrity failure: total Σ={total}, expected Σ={EXPECTED_TOTAL}. "
            f"Check transcription against AMENDMENT_A2_G1_RETEST.md §2."
        )
    # All hypothesis IDs must be unique
    ids = [h["hypothesis_id"] for h in ROSTER]
    if len(ids) != len(set(ids)):
        from collections import Counter
        dupes = [k for k, v in Counter(ids).items() if v > 1]
        raise AssertionError(f"Duplicate hypothesis IDs in roster: {dupes}")


# Run at import time — the roster must be consistent
_validate_roster()


def roster_sha256() -> str:
    """Deterministic SHA-256 of the frozen roster.

    Serialized as a sorted JSON array (keys sorted, whitespace-normalized).
    This hash is the machine-verifiable freeze record.
    """
    canonical = json.dumps(
        sorted(ROSTER, key=lambda h: h["hypothesis_id"]),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Program-wide FDR machinery (LH-R11.2)
# ---------------------------------------------------------------------------

PROGRAM_FDR_Q = 0.10   # BH-FDR threshold (q)
PERMUTATION_SEED = 42  # within-regime reshuffle null seed (OBJECTIVE §6.4)
N_PERMUTATIONS = 1000  # per-feature reshuffle null (OBJECTIVE §6.4)


def _bh_fdr(p_values: list[float], q: float = PROGRAM_FDR_Q) -> list[bool]:
    """Benjamini-Hochberg FDR correction.

    Returns a boolean list: True = hypothesis survives at BH q.
    Input p_values list corresponds 1-1 to hypotheses passed.
    """
    m = len(p_values)
    if m == 0:
        return []
    # Sort by p-value, track original indices
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    threshold = [q * (rank + 1) / m for rank, (_, _) in enumerate(indexed)]
    # Find largest k where p_(k) <= q*k/m
    survive = [False] * m
    max_reject = -1
    for k, ((orig_idx, p), thr) in enumerate(zip(indexed, threshold)):
        if p <= thr:
            max_reject = k
    for k in range(max_reject + 1):
        orig_idx = indexed[k][0]
        survive[orig_idx] = True
    return survive


def run_program_wide_fdr(
    hypothesis_ids: list[str],
    p_values: list[float],
) -> dict[str, dict]:
    """Apply program-wide BH-FDR (LH-R11.2) and return adjudication table.

    Args:
        hypothesis_ids: list of hypothesis_id strings (must match ROSTER)
        p_values: list of p-values (same order as hypothesis_ids)

    Returns:
        dict keyed by hypothesis_id with:
          - p_value
          - survives_program_fdr (bool)
          - program_fdr_marginal (bool): True iff the hypothesis clears its
            within-family q=0.10 BH correction BUT fails the program-wide
            BH-FDR correction (AMENDMENT_LH_R11_MULTI_FAMILY.md §LH-R11.2).
            Hypotheses that fail BOTH corrections are NOT marginal.
    """
    assert len(hypothesis_ids) == len(p_values), "ids and p_values must have same length"

    # Program-wide BH-FDR over all Σ hypotheses
    survive_program = _bh_fdr(p_values)

    # Build a lookup from hypothesis_id -> index in the input list
    hid_to_idx = {hid: i for i, hid in enumerate(hypothesis_ids)}

    # Within-family BH-FDR (q=0.10) — descriptive only per LH-R11.2, but used
    # here to compute the program_fdr_marginal flag.
    # Group each family's p-values, run BH, record per-hid result.
    survive_within_family: dict[str, bool] = {}
    # Collect family membership from ROSTER for the submitted hypothesis_ids
    hid_set = set(hypothesis_ids)
    family_to_hids: dict[str, list[str]] = {}
    for h in ROSTER:
        hid = h["hypothesis_id"]
        if hid in hid_set:
            fam = h["family"]
            family_to_hids.setdefault(fam, []).append(hid)
    # Any submitted hid not in ROSTER gets a placeholder family of its own
    roster_hids = {h["hypothesis_id"] for h in ROSTER}
    for hid in hypothesis_ids:
        if hid not in roster_hids:
            family_to_hids.setdefault(f"__unknown_{hid}__", []).append(hid)

    for fam_hids in family_to_hids.values():
        fam_ps = [p_values[hid_to_idx[hid]] for hid in fam_hids]
        fam_survive = _bh_fdr(fam_ps, q=PROGRAM_FDR_Q)
        for hid, s in zip(fam_hids, fam_survive):
            survive_within_family[hid] = s

    result = {}
    for hid, p, s_prog in zip(hypothesis_ids, p_values, survive_program):
        s_within = survive_within_family.get(hid, False)
        # program_fdr_marginal: clears within-family q but fails program-wide
        marginal = s_within and (not s_prog)
        result[hid] = {
            "p_value": p,
            "survives_program_fdr": s_prog,
            "program_fdr_marginal": marginal,
        }
    return result


# ---------------------------------------------------------------------------
# Feature provenance and restricted_range stamp helpers (LH-R11.3)
# ---------------------------------------------------------------------------

def print_roster_stamps() -> None:
    """Print feature_provenance and restricted_range stamps for all hypotheses."""
    print(f"\n{'='*70}")
    print("FROZEN ROSTER — feature_provenance and restricted_range stamps")
    print(f"Σ={len(ROSTER)} hypotheses across {len(EXPECTED_FAMILY_COUNTS)} families")
    print(f"Roster SHA-256: {roster_sha256()}")
    print(f"{'='*70}\n")
    current_family = None
    for h in ROSTER:
        if h["family"] != current_family:
            current_family = h["family"]
            fam_m = EXPECTED_FAMILY_COUNTS[current_family]
            print(f"\n  Family: {current_family} (m={fam_m})")
            print(f"  {'id':<8} {'feature':<35} {'dir':<12} {'restricted_range':<17} {'test'}")
            print(f"  {'-'*8} {'-'*35} {'-'*12} {'-'*17} {'-'*12}")
        rr = "YES (LH-R11.3)" if h["restricted_range"] else "no"
        print(
            f"  {h['hypothesis_id']:<8} {h['feature']:<35} "
            f"{h['direction']:<12} {rr:<17} {h['test']}"
        )
        print(f"           provenance: {h['feature_provenance']}")
    print()


def print_within_family_descriptive(
    family: str,
    p_values: dict[str, float],
) -> None:
    """Print descriptive (non-ratifying) within-family BH-FDR table.

    Per LH-R11.2, within-family q is descriptive only — not a second gate.
    """
    fam_hyps = [h for h in ROSTER if h["family"] == family]
    fam_ids = [h["hypothesis_id"] for h in fam_hyps]
    fam_ps = [p_values.get(hid, float("nan")) for hid in fam_ids]
    survive = _bh_fdr([p for p in fam_ps if not _isnan(p)])
    print(f"\n  Within-family descriptive BH-FDR (q=0.10) for {family}:")
    print(f"  [NOTE: this is DESCRIPTIVE only; program-wide HLZ is the sole ratifying gate]")
    print(f"  {'id':<8} {'feature':<35} {'p_val':<12} {'within_fam_bh'}")
    print(f"  {'-'*8} {'-'*35} {'-'*12} {'-'*13}")
    valid_idx = 0
    for hid, p in zip(fam_ids, fam_ps):
        if _isnan(p):
            bh_str = "n/a"
        else:
            bh_str = "pass" if survive[valid_idx] else "fail"
            valid_idx += 1
        feat = next(h["feature"] for h in ROSTER if h["hypothesis_id"] == hid)
        print(f"  {hid:<8} {feat:<35} {p if not _isnan(p) else 'nan':<12} {bh_str}")


def _isnan(x: float) -> bool:
    import math
    try:
        return math.isnan(x)
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# No-run gate (the core safety mechanism)
# ---------------------------------------------------------------------------

CLUSTER_FLOOR = 25  # LH-R4 / AMENDMENT_A2_G1_RETEST.md §1


def check_no_run_gate(
    cluster_count: Optional[int],
    operator_ack: bool,
) -> None:
    """Enforce the hard no-run gate before any outcome-contact computation.

    REFUSES TO RUN unless BOTH conditions are satisfied:
      1. cluster_count >= CLUSTER_FLOOR (25)
      2. operator_ack is True

    The refusal is LOUD, UNCONDITIONAL, and UNTUNABLE.
    There is NO environment variable or config that overrides this gate.

    Args:
        cluster_count: honest compounder episode-cluster count from W1 clustering
        operator_ack: True only if --operator-ack was passed explicitly

    Raises:
        SystemExit with a non-zero code and a loud printed message if either
        condition is not met.
    """
    errors = []

    if cluster_count is None:
        errors.append(
            "CLUSTER COUNT NOT PROVIDED: --cluster-count=N is required for --mode=run. "
            f"The cluster count must be the honest compounder episode-cluster count "
            f"(name x macro-regime, ±10d) from W1 clustering. "
            f"Pre-registered floor: {CLUSTER_FLOOR}."
        )
    elif cluster_count < CLUSTER_FLOOR:
        errors.append(
            f"CLUSTER FLOOR NOT MET: cluster_count={cluster_count} < {CLUSTER_FLOOR} "
            f"(pre-registered LH-R4 floor). "
            f"The honest OOS-2 compounder episode-cluster count is insufficient to "
            f"run outcome-contact statistics. This is a DATA REALITY, not a tunable "
            f"parameter. Expected floor met ~2027-H2 at observed ~14 clusters/year accrual. "
            f"Contact stage is BLOCKED."
        )

    if not operator_ack:
        errors.append(
            "OPERATOR ACK NOT PROVIDED: --operator-ack flag is required to run the "
            "outcome-contact stage. This explicit acknowledgment is required in addition "
            "to the cluster floor. Pass --operator-ack only after confirming: "
            "(1) the cluster count is honest and computed via the registered clustering; "
            "(2) the A2 analysis script is already committed (freeze anchor satisfied); "
            "(3) no feature-outcome statistics have been computed on OOS-2 prior to "
            "this run (AMENDMENT_A2_G1_RETEST.md §4 contact rules)."
        )

    if errors:
        print("\n" + "!" * 70, file=sys.stderr)
        print("A2 OOS OUTCOME-CONTACT STAGE: HARD REFUSAL", file=sys.stderr)
        print("!" * 70, file=sys.stderr)
        print(
            "\nThe A2 outcome-contact stage has been blocked. The following condition(s) "
            "were not satisfied:\n",
            file=sys.stderr,
        )
        for i, err in enumerate(errors, 1):
            print(f"  [{i}] {err}", file=sys.stderr)
        print(
            "\nThis gate is unconditional and untunable. There is no environment "
            "variable, config file, or code path that bypasses it.\n",
            file=sys.stderr,
        )
        print(
            "Reference: AMENDMENT_A2_G1_RETEST.md §1 (cluster floor), "
            "AMENDMENT_LH_R11_MULTI_FAMILY.md §LH-R11.1 (freeze anchor), "
            "AMENDMENT_A2_G1_RETEST.md §4 (contact rules).",
            file=sys.stderr,
        )
        print("!" * 70 + "\n", file=sys.stderr)
        sys.exit(2)


# ---------------------------------------------------------------------------
# Prep mode (always safe — no outcome-contact)
# ---------------------------------------------------------------------------

def run_prep_mode() -> None:
    """Display the frozen roster and readiness information. No label data touched."""
    print("\n" + "=" * 70)
    print("A2 OOS ANALYSIS — PREP MODE (no outcome contact)")
    print("=" * 70)
    print(f"\nRoster version:  {ROSTER_VERSION}")
    print(f"Freeze anchor:   commit of THIS file is the LH-R11.1 freeze anchor")
    print(f"Roster SHA-256:  {roster_sha256()}")
    print(f"Total Sigma:     {len(ROSTER)} hypotheses (pre-registered Σ=29)")
    print(f"Program FDR:     Harvey-Liu-Zhu / BH q={PROGRAM_FDR_Q} (sole ratifying gate)")
    print(f"Cluster floor:   >= {CLUSTER_FLOOR} honest compounder episode-clusters (LH-R4)")
    print(f"Expected floor:  ~2027-H2 at ~14 clusters/year accrual")
    print()
    print("Family breakdown:")
    for fam, m in EXPECTED_FAMILY_COUNTS.items():
        print(f"  {fam:<40} m={m}")
    print()
    print_roster_stamps()
    print("\nPrep mode complete. To run outcome-contact stage:")
    print(
        "  python scripts/research/a2_oos_analysis.py --mode=run "
        "--operator-ack --cluster-count=<N>"
    )
    print(
        "\nGate requires: cluster_count >= 25 AND --operator-ack. "
        "Both conditions are mandatory. No bypass exists."
    )


# ---------------------------------------------------------------------------
# Synthetic run mode (for tests only — uses injected data, never real labels)
# ---------------------------------------------------------------------------

def _run_outcome_contact_on_data(
    fire_rows: list[dict],
    label_rows: list[dict],
    *,
    cluster_count: Optional[int] = None,
    operator_ack: bool = False,
) -> dict:
    """Execute the outcome-contact analysis on supplied data.

    Args:
        fire_rows: list of dicts with keys: ticker, fire_date, features...
        label_rows: list of dicts with keys: ticker, fire_date, label, ...
        cluster_count: honest compounder episode-cluster count; must be >= CLUSTER_FLOOR.
        operator_ack: must be True to proceed.

    Returns:
        Analysis result dict.

    NOTE: This function enforces the hard no-run gate as its FIRST statement.
    No caller can bypass the refusal — it is not only in main().
    """
    # Hard no-run gate — enforced here unconditionally so no future caller
    # can reach outcome-contact logic without satisfying both conditions.
    check_no_run_gate(cluster_count=cluster_count, operator_ack=operator_ack)

    # Join fire features to labels
    label_map = {(r["ticker"], r["fire_date"]): r for r in label_rows}
    joined = []
    for fire in fire_rows:
        key = (fire["ticker"], fire["fire_date"])
        if key in label_map:
            merged = {**fire, **label_map[key]}
            joined.append(merged)

    # Derive missed_hold flag
    for row in joined:
        row["missed_hold"] = row.get("label") == "compounder"

    # Compute per-hypothesis p-values (placeholder: requires scipy/statsmodels)
    # In a full run these would be Mann-Whitney U / Fisher exact / permutation nulls.
    # Here we return a structure showing what WOULD be computed.
    hypothesis_ids = [h["hypothesis_id"] for h in ROSTER]
    p_values_placeholder = {hid: float("nan") for hid in hypothesis_ids}

    result = {
        "roster_sha256": roster_sha256(),
        "n_joined": len(joined),
        "n_missed_hold": sum(1 for r in joined if r["missed_hold"]),
        "n_tactical_only": sum(1 for r in joined if r.get("label") == "tactical_only"),
        "p_values": p_values_placeholder,
        "program_fdr_result": {},
        "status": "outcome_contact_ran_on_synthetic_data",
    }
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "A2 OOS-analysis harness for the Long-Hold Thesis Layer. "
            "Outcome-contact stage is gated by cluster floor AND --operator-ack."
        )
    )
    parser.add_argument(
        "--mode",
        choices=["prep", "run"],
        default="prep",
        help=(
            "prep: display roster and readiness info (no label contact). "
            "run: execute outcome-contact analysis (requires both gate conditions)."
        ),
    )
    parser.add_argument(
        "--operator-ack",
        action="store_true",
        dest="operator_ack",
        default=False,
        help=(
            "Explicit operator acknowledgment that: (1) cluster floor is met "
            "and count is honest; (2) this is the freeze-anchor commit run; "
            "(3) no prior feature-outcome contact on OOS-2. "
            "Required for --mode=run. No bypass exists."
        ),
    )
    parser.add_argument(
        "--cluster-count",
        type=int,
        dest="cluster_count",
        default=None,
        help=(
            "Honest compounder episode-cluster count (name x macro-regime, ±10d) "
            "from W1 clustering. Required for --mode=run. "
            f"Must be >= {CLUSTER_FLOOR} (LH-R4 floor) to proceed."
        ),
    )
    parser.add_argument(
        "--print-hash",
        action="store_true",
        dest="print_hash",
        help="Print roster SHA-256 and exit.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)

    if args.print_hash:
        print(roster_sha256())
        return 0

    if args.mode == "prep":
        run_prep_mode()
        return 0

    # mode == "run": enforce the hard gate before any outcome contact
    check_no_run_gate(
        cluster_count=args.cluster_count,
        operator_ack=args.operator_ack,
    )

    # Gate cleared — outcome-contact stage
    # In production this would load real data and run the analysis.
    # For the freeze-anchor PR, the data-loading stubs are left explicit
    # so the next developer knows exactly what to wire in.
    print("\n" + "=" * 70)
    print("A2 OOS ANALYSIS — OUTCOME-CONTACT STAGE")
    print("=" * 70)
    print(f"\nGate cleared. cluster_count={args.cluster_count} >= {CLUSTER_FLOOR}. operator_ack=True.")
    print(f"Roster SHA-256: {roster_sha256()}")
    print(f"Σ={len(ROSTER)} hypotheses, program-wide BH-FDR q={PROGRAM_FDR_Q}")
    print(
        "\n[STUB] Data loading not wired in the freeze-anchor PR. "
        "Wire the following before the A2 analysis PR:\n"
        "  1. Load data/research/gate_fires_baskets.parquet (fire tape, 2024+ cohort)\n"
        "  2. Load data/research/long_hold_labels.parquet (OOS-2 labels)\n"
        "  3. Load feature panels per-family (see AMENDMENT_A2_G1_RETEST.md §3)\n"
        "  4. Call _run_outcome_contact_on_data(fire_rows, label_rows)\n"
        "  5. Apply run_program_wide_fdr() over all Σ=29 p-values\n"
        "  6. Emit results with all required stamps (survivorship_biased, "
        "coverage_frac, restricted_range, feature_provenance, program_fdr_marginal)\n"
    )
    print_roster_stamps()
    return 0


if __name__ == "__main__":
    sys.exit(main())
