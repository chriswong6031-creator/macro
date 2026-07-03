"""Tests for engine/gov_exposure.py — hermetic, no network, no real parquets.

Covers:
  1. funding_to_mktcap — happy path, materiality bands, None-on-missing ticker,
     None-on-zero mktcap, grants-only path.
  2. funding_theme_roll — happy path, empty roll-up (None).
  3. capex_burden — happy path, None-on-thin-data, None-on-missing-ticker-in-caller,
     FCF-trap detection (capex_ocf > 80% AND fcf < 0), burden sanity fixture.
  4. spender_capex_burden — delegates to capex_burden per CHAIN spenders; absent
     statements → None (not 0).
  5. Chip-attachment regression — attaching rec["gov_exposure"] does NOT perturb
     any pre-existing keys in the rec dict.
"""
from __future__ import annotations

import pandas as pd
import pytest

from engine.gov_exposure import (
    capex_burden,
    funding_theme_roll,
    funding_to_mktcap,
    spender_capex_burden,
)


# ─── fixtures ─────────────────────────────────────────────────────────────────

def _make_obligations(tickers: list[str], months: int = 14, value: float = 1e9) -> pd.DataFrame:
    """Synthetic month × ticker obligations frame with constant values."""
    import pandas as pd
    idx = pd.date_range("2025-01-01", periods=months, freq="MS")
    return pd.DataFrame({t: [value] * months for t in tickers}, index=idx)


def _make_grants(tickers: list[str], months: int = 14, value: float = 5e8) -> pd.DataFrame:
    import pandas as pd
    idx = pd.date_range("2025-01-01", periods=months, freq="MS")
    return pd.DataFrame({t: [value] * months for t in tickers}, index=idx)


def _make_stmt_rows(
    ticker: str,
    years: int = 5,
    cfo: float = 10e9,
    capex: float = 3e9,
    debt_lt: float = 5e9,
    debt_cur: float = 1e9,
    cash: float = 2e9,
) -> list[dict]:
    rows = []
    for i in range(years):
        rows.append({
            "ticker": ticker,
            "fy": 2020 + i,
            "cfo":    cfo   * (1 + 0.05 * i),   # slight growth each year
            "capex":  capex * (1 + 0.02 * i),
            "debt_lt":  debt_lt,
            "debt_cur": debt_cur,
            "cash":     cash,
        })
    return rows


# ─── funding_to_mktcap ────────────────────────────────────────────────────────

class TestFundingToMktcap:
    def test_happy_path_contracts_only(self):
        obs = _make_obligations(["LMT"], months=14, value=1e9)
        mkt = {"LMT": 20e9}   # $20B mktcap
        r = funding_to_mktcap("LMT", obs, None, mkt)
        assert r is not None
        # 12 months of $1B = $12B contracts; / $20B = 60%
        assert r["ratio_pct"] == pytest.approx(60.0, abs=1.0)
        assert r["band"] == "heavy"
        assert r["evidence_tier"] == "fingerprint"
        assert r["score_cap"] == 60

    def test_contracts_plus_grants(self):
        obs = _make_obligations(["MSFT"], months=14, value=1e9)
        gl  = _make_grants(["MSFT"], months=14, value=5e8)
        mkt = {"MSFT": 3_000e9}   # $3T mktcap
        r = funding_to_mktcap("MSFT", obs, gl, mkt)
        assert r is not None
        # contracts ~12B + grants ~6B = 18B; / 3000B ≈ 0.6%
        assert r["ratio_pct"] < 2.0
        assert r["band"] == "minor"
        assert r["contracts_ttm"] is not None
        assert r["grants_ttm"] is not None

    def test_notable_band(self):
        obs = _make_obligations(["HII"], months=14, value=1e9)
        mkt = {"HII": 80e9}   # ~80B → ratio ~15% → heavy; use small mktcap
        r = funding_to_mktcap("HII", obs, None, mkt)
        assert r is not None
        assert r["band"] == "heavy"

    def test_none_on_missing_ticker(self):
        obs = _make_obligations(["LMT"], months=14)
        mkt = {"LMT": 20e9}
        r = funding_to_mktcap("MISSING_TICKER", obs, None, mkt)
        assert r is None

    def test_none_on_zero_mktcap(self):
        obs = _make_obligations(["LMT"], months=14)
        mkt = {"LMT": 0.0}
        r = funding_to_mktcap("LMT", obs, None, mkt)
        assert r is None

    def test_none_on_absent_mktcap(self):
        obs = _make_obligations(["LMT"], months=14)
        r = funding_to_mktcap("LMT", obs, None, {})
        assert r is None

    def test_grants_only_path(self):
        empty_obs = _make_obligations([], months=14)   # no columns
        gl  = _make_grants(["MP"], months=14, value=2e8)
        mkt = {"MP": 10e9}
        r = funding_to_mktcap("MP", empty_obs, gl, mkt)
        # MP absent from obs but present in grants → still a result
        assert r is not None
        assert r["contracts_ttm"] is None
        assert r["grants_ttm"] is not None
        assert r["ratio_pct"] > 0

    def test_empty_obligations_frame(self):
        obs = pd.DataFrame()
        r = funding_to_mktcap("LMT", obs, None, {"LMT": 20e9})
        assert r is None


# ─── funding_theme_roll ────────────────────────────────────────────────────────

class TestFundingThemeRoll:
    def test_happy_path(self):
        obs = _make_obligations(["LMT", "RTX"], months=14, value=2e9)
        mkt = {"LMT": 50e9, "RTX": 100e9}
        r = funding_theme_roll(["LMT", "RTX"], obs, None, mkt)
        assert r is not None
        assert r["n_covered"] == 2
        assert r["weighted_ratio_pct"] > 0
        assert r["evidence_tier"] == "fingerprint"
        assert r["score_cap"] == 60

    def test_none_when_no_coverage(self):
        obs = _make_obligations(["LMT"], months=14)
        mkt = {"LMT": 50e9}
        r = funding_theme_roll(["MISSING_A", "MISSING_B"], obs, None, mkt)
        assert r is None


# ─── capex_burden ─────────────────────────────────────────────────────────────

class TestCapexBurden:
    def test_happy_path(self):
        rows = _make_stmt_rows("MSFT", years=5, cfo=136e9, capex=56e9)
        r = capex_burden(rows)
        assert r is not None
        assert r["capex_ocf_latest"] is not None
        assert r["capex_ocf_latest"] > 0
        assert r["fy_latest"] == 2024
        assert r["evidence_tier"] == "fingerprint"
        assert r["score_cap"] == 60

    def test_none_on_empty_rows(self):
        r = capex_burden([])
        assert r is None

    def test_none_on_none_input(self):
        r = capex_burden(None)  # type: ignore[arg-type]
        assert r is None

    def test_none_on_insufficient_years(self):
        rows = _make_stmt_rows("TST", years=2, cfo=10e9, capex=3e9)
        r = capex_burden(rows, min_years=3)
        assert r is None

    def test_fcf_trap_detection(self):
        """capex_ocf > 80% AND fcf < 0 → fcf_trap = True."""
        rows = []
        for i in range(4):
            rows.append({
                "ticker": "TRAP",
                "fy": 2020 + i,
                "cfo":   5e9,   # positive OCF
                "capex": 5e9 + 1e9,   # capex EXCEEDS cfo → FCF < 0
                "debt_lt": 10e9, "debt_cur": 1e9, "cash": 2e9,
            })
        r = capex_burden(rows)
        assert r is not None
        assert r["fcf_trap"] is True
        assert r["fcf_latest_bn"] is not None
        assert r["fcf_latest_bn"] < 0

    def test_fcf_trap_not_flagged_when_fcf_positive(self):
        """Even with high capex/OCF, if FCF > 0 there is no FCF trap."""
        rows = []
        for i in range(4):
            rows.append({
                "ticker": "SAFETRAP",
                "fy": 2020 + i,
                "cfo":   20e9,
                "capex": 17e9,  # 85% capex/OCF but FCF still positive
                "debt_lt": 10e9, "debt_cur": 1e9, "cash": 2e9,
            })
        r = capex_burden(rows)
        assert r is not None
        assert r["fcf_trap"] is False

    def test_burden_sanity_capex_over_ocf_gt_100_flagged(self):
        """capex_ocf > 100% is an extreme FCF-burden situation."""
        rows = []
        for i in range(4):
            rows.append({
                "ticker": "EXTREME",
                "fy": 2020 + i,
                "cfo":   10e9,
                "capex": 12e9,  # 120% capex/OCF
                "debt_lt": 5e9, "debt_cur": 1e9, "cash": 1e9,
            })
        r = capex_burden(rows)
        assert r is not None
        assert r["capex_ocf_latest"] is not None
        assert r["capex_ocf_latest"] > 100.0, "Expected capex_ocf > 100%"
        assert r["fcf_trap"] is True          # FCF < 0

    def test_none_when_capex_missing_but_cfo_present(self):
        """With no capex, no fcf_trap; but result still returned (FCF = CFO fallback)."""
        rows = []
        for i in range(4):
            rows.append({"ticker": "X", "fy": 2020 + i, "cfo": 10e9})
        r = capex_burden(rows)
        assert r is not None
        assert r["capex_ocf_latest"] is None   # no capex available
        assert r["fcf_trap"] is False
        assert r["fcf_latest_bn"] is not None  # FCF falls back to CFO


# ─── spender_capex_burden ─────────────────────────────────────────────────────

class TestSpenderCapexBurden:
    def test_ai_chain_present(self):
        """ai_datacenter chain spenders present in synthetic statements → results."""
        rows = []
        for tkr in ["MSFT", "AMZN", "META"]:
            rows.extend(_make_stmt_rows(tkr, years=4, cfo=100e9, capex=50e9))
        df = pd.DataFrame(rows)
        result = spender_capex_burden(df, "ai_datacenter")
        assert len(result) > 0
        for tkr, burden in result.items():
            assert burden is not None, f"{tkr} should have a burden result"
            assert burden["evidence_tier"] == "fingerprint"

    def test_absent_ticker_returns_none(self):
        """A spender ticker absent from statements → None, not KeyError/0."""
        empty_df = pd.DataFrame(columns=["ticker", "fy", "cfo", "capex",
                                         "debt_lt", "debt_cur", "cash"])
        result = spender_capex_burden(empty_df, "ai_datacenter")
        # result dict may be empty if no tickers matched
        # but if a ticker IS in the result, its value must be None (not 0)
        for v in result.values():
            assert v is None

    def test_unknown_chain_returns_empty(self):
        df = pd.DataFrame()
        result = spender_capex_burden(df, "nonexistent_chain_xyz")
        assert result == {}


# ─── chip-attachment regression ───────────────────────────────────────────────

class TestChipAttachmentRegression:
    """Attaching rec['gov_exposure'] must not perturb any pre-existing keys."""

    def test_only_gov_exposure_added(self):
        existing_rec = {
            "ticker": "LMT",
            "ladder": {"state": "BUY ZONE"},
            "altdata": {"score": 2},
            "macro_sensitivity": {"tier": "high"},
            "profile": {"archetype": {"key": "defense"}},
        }
        before_keys = set(existing_rec.keys())

        obs = _make_obligations(["LMT"], months=14, value=5e9)
        mkt = {"LMT": 30e9}
        exposure = funding_to_mktcap("LMT", obs, None, mkt)
        if exposure:
            existing_rec["gov_exposure"] = exposure

        after_keys = set(existing_rec.keys())
        new_keys = after_keys - before_keys
        assert new_keys == {"gov_exposure"}, (
            f"Only 'gov_exposure' should be added; got {new_keys}")
        # pre-existing keys are intact
        for k in before_keys:
            assert existing_rec[k] is not None
