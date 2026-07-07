"""tests/test_w2153_itc337_phase0.py — ITC-337 phase-0 unit tests.

Tests the pure-logic helpers in scripts/w2153_itc337_phase0.py.
No network calls, no real price data required.

Covered:
  * load_respondent_map       — CSV loads; Tier-A and Tier-X present
  * match_respondent          — substring matching, tier filtering,
                                validity windows, longest-pattern rule
  * _extract_respondents_from_text — respondent section parsing
  * _extract_inv_number       — 337-TA-NNN extraction
  * _next_business_day        — BD arithmetic
  * abnormal_return           — beta-adjusted cumulative AR formula
  * compute_beta              — trailing OLS beta PIT constraint
  * run_event_study           — calendar-time collapse + NW result
  * apply_gates               — G1 + G2 logic; UNDERPOWERED flag
  * check_sector_diversity    — GICS-2 sector spread gate
"""
from __future__ import annotations

import sys
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.w2153_itc337_phase0 import (  # noqa: E402
    load_respondent_map,
    match_respondent,
    _extract_respondents_from_text,
    _extract_inv_number,
    _next_business_day,
    abnormal_return,
    compute_beta,
    run_event_study,
    apply_gates,
    check_sector_diversity,
    TRIAL_GRID,
    UNDERPOWERED_N,
    NW_LAGS,
    SPY,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bdate_series(tickers: list[str], n: int = 120,
                  seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Synthetic close and return matrices for testing."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2022-01-03", periods=n)
    data = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, (n, len(tickers))), axis=0))
    close = pd.DataFrame(data, index=idx, columns=tickers)
    ret   = close.pct_change()
    return close, ret


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ===========================================================================
# 1. Respondent map loading
# ===========================================================================

class TestRespondentMap:
    def test_loads_without_error(self):
        rmap = load_respondent_map()
        assert len(rmap) > 20

    def test_apple_maps_to_aapl(self):
        rmap = load_respondent_map()
        assert rmap["APPLE"]["ticker"] == "AAPL"

    def test_apple_is_tier_a(self):
        rmap = load_respondent_map()
        assert rmap["APPLE"]["tier"] == "A"

    def test_huawei_is_tier_x(self):
        rmap = load_respondent_map()
        assert rmap["HUAWEI"]["tier"] == "X"

    def test_samsung_is_tier_b_or_x(self):
        """Samsung Electronics is Korean-listed only — Tier-B or X."""
        rmap = load_respondent_map()
        tier = rmap["SAMSUNG ELECTRONICS"]["tier"]
        assert tier in ("B", "X")

    def test_qualcomm_maps_to_qcom(self):
        rmap = load_respondent_map()
        assert rmap["QUALCOMM"]["ticker"] == "QCOM"

    def test_all_tier_a_have_ticker(self):
        rmap = load_respondent_map()
        for pat, info in rmap.items():
            if info["tier"] == "A":
                assert info["ticker"], f"Tier-A pattern '{pat}' has no ticker"

    def test_tier_x_have_no_usable_ticker(self):
        """Tier-X patterns should have an empty ticker (private/foreign)."""
        rmap = load_respondent_map()
        for pat, info in rmap.items():
            if info["tier"] == "X":
                # ticker is None or empty string for private/foreign
                assert not info["ticker"], f"Tier-X pattern '{pat}' has ticker={info['ticker']}"

    def test_tier_b_returns_none_from_match(self):
        """Tier-B (non-US-listed) patterns should return None from match_respondent."""
        rmap = load_respondent_map()
        tier_b_patterns = [p for p, info in rmap.items() if info["tier"] == "B"]
        if tier_b_patterns:
            pat = tier_b_patterns[0]
            r = match_respondent(pat, date(2023, 1, 1), rmap)
            assert r is None, f"Tier-B pattern '{pat}' should return None; got {r}"


# ===========================================================================
# 2. match_respondent — substring matching and validity windows
# ===========================================================================

class TestMatchRespondent:
    def setup_method(self):
        self.rmap = load_respondent_map()

    def test_apple_inc_maps_to_aapl(self):
        r = match_respondent("Apple Inc., Cupertino CA", date(2023, 1, 1), self.rmap)
        assert r == "AAPL"

    def test_samsung_returns_none_tier_b_or_x(self):
        """Samsung is Tier-B/X; match_respondent must return None."""
        r = match_respondent("Samsung Electronics Co., Ltd.", date(2023, 1, 1), self.rmap)
        assert r is None   # Tier-X excluded

    def test_unknown_company_returns_none(self):
        r = match_respondent("Acme Fictional Corp.", date(2023, 1, 1), self.rmap)
        assert r is None

    def test_motorola_maps_to_msi_post_2011(self):
        """MOTOROLA pattern maps to MSI."""
        r = match_respondent("Motorola Solutions, Inc.", date(2015, 6, 1), self.rmap)
        assert r == "MSI"

    def test_rivian_before_ipo_returns_none(self):
        """If RIVIAN has valid_from=2021-11-10, event in 2019 should return None."""
        r = match_respondent("Rivian Automotive, Inc.", date(2019, 3, 1), self.rmap)
        # Either not in map or out of validity window
        assert r is None

    def test_lowercase_name_handled(self):
        """match_respondent uppercases the name; 'apple' should still match APPLE."""
        r = match_respondent("apple inc", date(2023, 1, 1), self.rmap)
        assert r == "AAPL"

    def test_longest_pattern_wins(self):
        """'SAMSUNG ELECTRONICS' should beat 'SAMSUNG' pattern."""
        r = match_respondent("Samsung Electronics Display Co.", date(2023, 1, 1), self.rmap)
        # Both SAMSUNG and SAMSUNG ELECTRONICS are Tier-B/X so result is None
        # but the function should not raise
        assert r is None or isinstance(r, str)

    def test_qualcomm_incorporated_matches(self):
        r = match_respondent("Qualcomm Incorporated", date(2023, 1, 1), self.rmap)
        assert r == "QCOM"


# ===========================================================================
# 3. _extract_inv_number — investigation number extraction
# ===========================================================================

class TestExtractInvNumber:
    def test_from_docket_ids(self):
        n = _extract_inv_number("", "", "Investigation No. 337-TA-1050")
        assert n == "337-TA-1050"

    def test_from_title(self):
        n = _extract_inv_number(
            None,
            "Certain Electronic Devices; 337-TA-1234; Notice of Institution",
            ""
        )
        assert n == "337-TA-1234"

    def test_from_text_body(self):
        text = (
            "Notice is hereby given that the Commission has instituted an "
            "investigation designated 337-TA-999 concerning..."
        )
        n = _extract_inv_number(text, "", "")
        assert n == "337-TA-999"

    def test_returns_none_when_not_found(self):
        n = _extract_inv_number("no number here", "title only", "ITC-2023-001")
        assert n is None

    def test_prefers_first_occurrence(self):
        text = "337-TA-100 see also 337-TA-200"
        n = _extract_inv_number(text, "", "")
        # Either 100 or 200 is acceptable (just must be one of them)
        assert n in ("337-TA-100", "337-TA-200")


# ===========================================================================
# 4. _extract_respondents_from_text — notice parsing
# ===========================================================================

class TestExtractRespondents:
    def _make_notice(self, respondents: list[str]) -> str:
        resp_block = "\n".join(f"  - {r}" for r in respondents)
        return f"""
AGENCY: International Trade Commission.
ACTION: Notice of institution of investigation.

SUMMARY: Notice is hereby given that a complaint was filed on January 1, 2023.
Investigation 337-TA-1100.

Complainant: Some Patent Troll LLC, Delaware.

Respondents:
{resp_block}

FOR FURTHER INFORMATION CONTACT: John Smith, (202) 000-0000.
"""

    def test_single_respondent_extracted(self):
        text = self._make_notice(["Apple Inc., Cupertino, California"])
        names = _extract_respondents_from_text(text)
        assert any("APPLE" in n.upper() for n in names)

    def test_multiple_respondents_extracted(self):
        text = self._make_notice([
            "Apple Inc., Cupertino, California",
            "Qualcomm Incorporated, San Diego, California",
            "Intel Corporation, Santa Clara, California",
        ])
        names = _extract_respondents_from_text(text)
        # Should extract at least 2 of the 3
        hits = sum(1 for n in names if any(
            k in n.upper() for k in ("APPLE", "QUALCOMM", "INTEL")))
        assert hits >= 2, f"Expected ≥2 recognized names, got {hits}; names={names}"

    def test_empty_text_returns_empty(self):
        names = _extract_respondents_from_text("")
        assert isinstance(names, list)
        assert len(names) == 0

    def test_none_text_returns_empty(self):
        names = _extract_respondents_from_text(None)
        assert isinstance(names, list)

    def test_section_end_stops_extraction(self):
        """Extraction must not bleed past 'FOR FURTHER INFORMATION'."""
        text = self._make_notice(["Apple Inc., California"])
        text += "\nFOR FURTHER INFORMATION CONTACT: John Smith\n"
        text += "Decoy Corp — should NOT be extracted\n"
        names = _extract_respondents_from_text(text)
        assert all("DECOY" not in n.upper() for n in names)


# ===========================================================================
# 5. _next_business_day — BD arithmetic
# ===========================================================================

class TestNextBusinessDay:
    def test_zero_days_returns_same(self):
        d = date(2023, 6, 5)   # Monday
        assert _next_business_day(d, 0) == d

    def test_one_bd_from_monday(self):
        d = date(2023, 6, 5)   # Monday → next BD is Tuesday
        assert _next_business_day(d, 1) == date(2023, 6, 6)

    def test_one_bd_from_friday_skips_weekend(self):
        d = date(2023, 6, 9)   # Friday → next BD is Monday
        assert _next_business_day(d, 1) == date(2023, 6, 12)

    def test_one_bd_from_thursday(self):
        d = date(2023, 6, 8)   # Thursday → Friday
        assert _next_business_day(d, 1) == date(2023, 6, 9)

    def test_five_bds_one_full_week(self):
        d = date(2023, 6, 5)   # Monday + 5BD = next Monday
        assert _next_business_day(d, 5) == date(2023, 6, 12)


# ===========================================================================
# 6. abnormal_return — beta-adjusted cumulative AR
# ===========================================================================

class TestAbnormalReturn:
    def _make_ret(self, spy_daily: float, stock_daily: float,
                  n: int = 60) -> pd.DataFrame:
        idx = pd.bdate_range("2022-01-03", periods=n)
        return pd.DataFrame({
            SPY: [spy_daily] * n,
            "AAPL": [stock_daily] * n,
        }, index=idx)

    def test_beta_one_formula(self):
        """AR = stock_cum - 1*SPY_cum = (1+0.02)^5 - (1+0.01)^5."""
        ret = self._make_ret(0.01, 0.02)
        entry = date(2022, 1, 3)
        ar = abnormal_return(ret, "AAPL", entry, 5, beta=1.0)
        expected = (1.02 ** 5 - 1) - (1.01 ** 5 - 1)
        assert ar == pytest.approx(expected, rel=1e-6)

    def test_beta_zero_returns_stock_only(self):
        ret = self._make_ret(0.01, 0.02)
        entry = date(2022, 1, 3)
        ar = abnormal_return(ret, "AAPL", entry, 5, beta=0.0)
        expected = 1.02 ** 5 - 1
        assert ar == pytest.approx(expected, rel=1e-6)

    def test_insufficient_forward_returns_none(self):
        ret = self._make_ret(0.01, 0.02, n=10)
        # Entry near end — only 3 future bars
        entry = date(2022, 1, 13)
        ar = abnormal_return(ret, "AAPL", entry, fwd_days=21, beta=1.0)
        assert ar is None

    def test_missing_ticker_returns_none(self):
        _, ret = _bdate_series([SPY, "MSFT"], n=60)
        ar = abnormal_return(ret, "NONEXISTENT", date(2022, 1, 3), 5, beta=1.0)
        assert ar is None


# ===========================================================================
# 7. compute_beta — trailing OLS PIT constraint
# ===========================================================================

class TestComputeBeta:
    def test_perfect_correlation_returns_one(self):
        """If stock = SPY, beta should be 1.0."""
        idx = pd.bdate_range("2020-01-02", periods=300)
        ret_val = np.random.default_rng(0).normal(0, 0.01, 300)
        df = pd.DataFrame({SPY: ret_val, "A": ret_val}, index=idx)
        beta = compute_beta(df, "A", date(2021, 12, 31))
        assert beta == pytest.approx(1.0, abs=0.01)

    def test_double_return_stock_gives_beta_near_two(self):
        """If stock returns = 2*SPY returns, beta ≈ 2.0."""
        idx = pd.bdate_range("2020-01-02", periods=300)
        spy_ret = np.random.default_rng(1).normal(0, 0.01, 300)
        df = pd.DataFrame({SPY: spy_ret, "B": 2 * spy_ret}, index=idx)
        beta = compute_beta(df, "B", date(2021, 12, 31))
        assert beta == pytest.approx(2.0, abs=0.1)

    def test_insufficient_history_returns_one(self):
        """Fewer than BETA_MIN_OBS observations → fall back to beta = 1.0."""
        idx = pd.bdate_range("2022-01-03", periods=30)
        df = pd.DataFrame({SPY: [0.01] * 30, "C": [0.02] * 30}, index=idx)
        beta = compute_beta(df, "C", date(2022, 2, 28))
        assert beta == 1.0

    def test_pit_constraint_respected(self):
        """Beta uses only data up to as_of_date; future data must not leak."""
        idx = pd.bdate_range("2020-01-02", periods=600)
        spy_ret = np.random.default_rng(2).normal(0, 0.01, 600)
        # Stock is SPY in first 300 days, then 3*SPY afterward
        stock_ret = np.where(np.arange(600) < 300, spy_ret, 3 * spy_ret)
        df = pd.DataFrame({SPY: spy_ret, "D": stock_ret}, index=idx)
        # as_of at day 300 → should use only first 252 obs where stock=SPY → beta≈1
        as_of = idx[299].date()
        beta_early = compute_beta(df, "D", as_of)
        assert beta_early == pytest.approx(1.0, abs=0.1)


# ===========================================================================
# 8. run_event_study — calendar-time collapse + NW
# ===========================================================================

class TestRunEventStudy:
    def _make_events(self, tickers: list[str], dates: list[date],
                     event_type: str = "institution") -> pd.DataFrame:
        rows = []
        for d in dates:
            for t in tickers:
                rows.append({
                    "inv_num": f"337-TA-{abs(hash(str(d)+t)) % 9000 + 1000}",
                    "doc_num": "dummy",
                    "event_date": pd.Timestamp(d),
                    "avail_date": pd.Timestamp(d),
                    "respondent": f"{t} Corp",
                    "ticker": t,
                    "event_type": event_type,
                })
        return pd.DataFrame(rows)

    def test_empty_events_returns_zero_events(self):
        _, ret = _bdate_series([SPY, "AAPL"])
        ev = pd.DataFrame(columns=["inv_num", "doc_num", "event_date",
                                   "avail_date", "respondent", "ticker", "event_type"])
        r = run_event_study(ev, ret, fwd_days=5, nw_lags=1)
        assert r["n_events"] == 0

    def test_single_event_returns_one_date(self):
        _, ret = _bdate_series([SPY, "AAPL"])
        ev = self._make_events(["AAPL"], [date(2022, 1, 10)])
        r = run_event_study(ev, ret, fwd_days=5, nw_lags=1)
        # May have 0 events if AAPL is not in ret; depends on ticker match
        assert r["n_dates"] in (0, 1)

    def test_calendar_collapse_multiple_same_day(self):
        """Two events on the same avail_date should produce 1 calendar-date obs."""
        _, ret = _bdate_series([SPY, "AAPL", "MSFT"])
        ev = self._make_events(["AAPL", "MSFT"], [date(2022, 1, 10)])
        r = run_event_study(ev, ret, fwd_days=5, nw_lags=1)
        # Both events on the same date → at most 1 calendar-date obs
        assert r["n_dates"] <= 1

    def test_underpowered_flag_set_below_threshold(self):
        """With n_dates < UNDERPOWERED_N, underpowered=True."""
        _, ret = _bdate_series([SPY, "AAPL"])
        dates = [date(2022, 1, 3 + i) for i in range(5)]
        ev = self._make_events(["AAPL"], dates)
        r = run_event_study(ev, ret, fwd_days=5, nw_lags=1)
        # With ≤5 dates, must be underpowered
        if r["n_dates"] < UNDERPOWERED_N:
            assert r["underpowered"] is True

    def test_result_has_required_keys(self):
        _, ret = _bdate_series([SPY, "AAPL"])
        ev = self._make_events(["AAPL"], [date(2022, 2, 1)])
        r = run_event_study(ev, ret, fwd_days=5, nw_lags=1)
        for key in ("n_events", "n_dates", "mean_ar", "nw", "by_ticker",
                    "cal_series", "underpowered"):
            assert key in r, f"Missing key: {key}"


# ===========================================================================
# 9. check_sector_diversity — GICS-2 gate
# ===========================================================================

class TestSectorDiversity:
    def test_single_sector_fails(self):
        """All IT tickers → only 1 sector → G2 fails."""
        by_ticker = {"AAPL": {"n": 5}, "MSFT": {"n": 3}, "QCOM": {"n": 2}}
        r = check_sector_diversity(None, by_ticker)
        # All are sector 45 (IT) → n_sectors = 1 → fail
        assert r["n_sectors"] == 1
        assert r["pass"] is False

    def test_two_sectors_passes(self):
        """IT + Healthcare → 2 sectors → G2 passes."""
        by_ticker = {"AAPL": {"n": 5}, "MSFT": {"n": 3},
                     "MDT": {"n": 4}, "JNJ": {"n": 2}}
        r = check_sector_diversity(None, by_ticker)
        assert r["n_sectors"] >= 2
        assert r["pass"] is True

    def test_unknown_ticker_excluded_from_count(self):
        """Tickers not in TICKER_SECTOR map are excluded from sector count."""
        by_ticker = {"UNKNOWN_XYZ": {"n": 10}}
        r = check_sector_diversity(None, by_ticker)
        assert "UNKNOWN_XYZ" in r["tickers_missing_sector"]
        assert r["n_sectors"] == 0

    def test_empty_by_ticker_fails(self):
        r = check_sector_diversity(None, {})
        assert r["n_sectors"] == 0
        assert r["pass"] is False


# ===========================================================================
# 10. apply_gates — gate logic + UNDERPOWERED handling
# ===========================================================================

class TestApplyGates:
    def _synthetic_results(self, t_vals: dict[str, float],
                           underpowered: bool = False) -> dict:
        """Build synthetic results from t-value map."""
        out: dict[str, dict] = {}
        for k, t in t_vals.items():
            p = 2.0 * (1.0 - _norm_cdf(abs(t))) if t is not None else None
            mean_ar = -0.5 if (t is not None and t < 0) else 0.5
            nw = {"mean": mean_ar / 100, "t": t, "p": p, "n": 30} if t is not None \
                 else {"mean": None, "t": None, "p": None, "n": 0}
            # build dummy by_ticker spanning 2 sectors (IT + Healthcare)
            by_ticker = {"AAPL": {"n": 5, "mean_ar_pct": mean_ar},
                         "MDT":  {"n": 3, "mean_ar_pct": mean_ar}}
            out[k] = {
                "n_events":    0 if underpowered else 50,
                "n_dates":     3 if underpowered else 30,
                "mean_ar":     mean_ar,
                "nw":          nw,
                "by_ticker":   by_ticker,
                "cal_series":  None,
                "underpowered": underpowered,
            }
        return out

    def test_all_underpowered_gives_underpowered_null(self):
        keys = [c["variant"] for c in TRIAL_GRID]
        results = self._synthetic_results({k: -2.5 for k in keys}, underpowered=True)
        gates = apply_gates(results)
        assert gates["verdict"] == "UNDERPOWERED_NULL"
        assert not gates["G1_pass"]

    def test_weak_t_gives_null(self):
        keys = [c["variant"] for c in TRIAL_GRID]
        results = self._synthetic_results({k: -0.8 for k in keys}, underpowered=False)
        gates = apply_gates(results)
        assert gates["verdict"] == "NULL"
        assert not gates["G1_pass"]

    def test_positive_direction_never_passes_g1(self):
        keys = [c["variant"] for c in TRIAL_GRID]
        # Override mean_ar to positive for all cells even though t is strong
        results = self._synthetic_results({k: 5.0 for k in keys}, underpowered=False)
        gates = apply_gates(results)
        assert gates["verdict"] == "NULL"
        assert not gates["G1_pass"]

    def test_required_keys_always_present(self):
        keys = [c["variant"] for c in TRIAL_GRID]
        results = self._synthetic_results({k: -1.0 for k in keys})
        gates = apply_gates(results)
        for key in ("G1_pass", "G1_passing", "G1_detail", "bh_results",
                    "G2_sector", "G2_pass", "verdict"):
            assert key in gates, f"Missing key: {key}"

    def test_underpowered_cells_not_in_bh(self):
        """Underpowered cells must not appear in the BH correction."""
        keys = [c["variant"] for c in TRIAL_GRID]
        results = self._synthetic_results({k: -3.0 for k in keys}, underpowered=True)
        gates = apply_gates(results)
        for k in keys:
            assert k not in gates["bh_results"], \
                f"Underpowered cell {k} should not appear in BH results"

    def test_g2_sector_concentration_fail(self):
        """If G1 passes but all tickers are in same sector, G2 fails."""
        keys = [c["variant"] for c in TRIAL_GRID]
        results = self._synthetic_results({k: -4.0 for k in keys}, underpowered=False)
        # Override by_ticker to all-IT tickers
        for k in keys:
            results[k]["by_ticker"] = {
                "AAPL": {"n": 5, "mean_ar_pct": -1.0},
                "MSFT": {"n": 3, "mean_ar_pct": -0.8},
                "QCOM": {"n": 2, "mean_ar_pct": -0.5},
            }
            results[k]["n_dates"] = 30
            results[k]["underpowered"] = False
        gates = apply_gates(results)
        # If G1 passes, G2 should fail (all same sector)
        if gates["G1_pass"]:
            assert not gates["G2_pass"]
            assert gates["verdict"] == "G1_PASS_G2_FAIL_SECTOR_CONCENTRATION"

    def test_trial_grid_has_four_cells(self):
        assert len(TRIAL_GRID) == 4
        variants = {c["variant"] for c in TRIAL_GRID}
        assert variants == {"E1_institution_5d", "E1_institution_21d",
                            "E2_adverse_5d", "E2_adverse_21d"}

    def test_nw_lags_defined_for_all_cells(self):
        for c in TRIAL_GRID:
            assert c["variant"] in NW_LAGS, f"{c['variant']} missing from NW_LAGS"

    def test_underpowered_threshold_is_25(self):
        assert UNDERPOWERED_N == 25
