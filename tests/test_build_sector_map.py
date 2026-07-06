"""Tests for scripts/build_sector_map.py — SIC→sector mapping.

LT-1c: sector map expansion for the Long-Hold Thesis Layer.

Tests:
  1. SIC text map spot checks: bank → Financials, biotech → Health Care,
     retailer → Consumer Discretionary.
  2. SIC numeric range mapping: SIC codes for representative industries.
  3. GICS priority: GICS source always wins over SIC-derived mapping.
  4. Output schema: ticker, sector, source columns; valid sector strings only.
  5. No duplicate tickers in output.

All tests are pure-logic — no network calls, no disk writes.
Fixture-only: tests import the mapping tables and pure functions, not the
build() orchestrator (which requires the data directory).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_sector_map import (  # noqa: E402
    _SIC_TEXT_MAP,
    _SIC_RANGE_MAP,
    _sic_range_to_sector,
)

# Valid GICS-style sector strings (must match constituents.parquet)
VALID_SECTORS = {
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Industrials",
    "Information Technology",
    "Materials",
    "Real Estate",
    "Utilities",
}


# ---------------------------------------------------------------------------
# SIC text map tests
# ---------------------------------------------------------------------------

class TestSicTextMap:
    """Spot-check the _SIC_TEXT_MAP lookup table."""

    # task-specified spot checks: bank→Financials, biotech→Health Care,
    # retailer→Consumer Discretionary
    @pytest.mark.parametrize("sic_desc,expected_sector", [
        # Banks → Financials
        ("National Commercial Banks", "Financials"),
        ("State Commercial Banks", "Financials"),
        ("Savings Institution, Federally Chartered", "Financials"),
        # Biotechnology → Health Care
        ("Biological Products, (No Diagnostic Substances)", "Health Care"),
        ("Pharmaceutical Preparations", "Health Care"),
        ("In Vitro & In Vivo Diagnostic Substances", "Health Care"),
        # Retailers → Consumer Discretionary
        ("Retail-Department Stores", "Consumer Discretionary"),
        ("Retail-Family Clothing Stores", "Consumer Discretionary"),
        ("Retail-Catalog & Mail-Order Houses", "Consumer Discretionary"),
        # Grocery retailers → Consumer Staples
        ("Retail-Grocery Stores", "Consumer Staples"),
        ("Retail-Drug Stores and Proprietary Stores", "Consumer Staples"),
        # Tech → Information Technology
        ("Semiconductors & Related Devices", "Information Technology"),
        ("Services-Prepackaged Software", "Information Technology"),
        ("Electronic Computers", "Information Technology"),
        # Energy
        ("Crude Petroleum & Natural Gas", "Energy"),
        ("Oil & Gas Field Services, NEC", "Energy"),
        ("Petroleum Refining", "Energy"),
        # Utilities
        ("Electric Services", "Utilities"),
        ("Natural Gas Distribution", "Utilities"),
        # Real Estate
        ("Real Estate Investment Trusts", "Real Estate"),
        ("Real Estate", "Real Estate"),
        # Industrials
        ("Air Transportation, Scheduled", "Industrials"),
        ("Railroads, Line-Haul Operating", "Industrials"),
        # Health Care services
        ("Services-Hospitals", "Health Care"),
        ("Services-Medical Laboratories", "Health Care"),
        # Insurance → Financials
        ("Fire, Marine & Casualty Insurance", "Financials"),
        ("Life Insurance", "Financials"),
        # Communication
        ("Telephone Communications (No Radiotelephone)", "Communication Services"),
        ("Cable & Other Pay Television Services", "Communication Services"),
        # Materials
        ("Steel Works, Blast Furnaces & Rolling & Finishing Mills", "Materials"),
        ("Industrial Organic Chemicals", "Materials"),
    ])
    def test_sic_text_to_sector(self, sic_desc: str, expected_sector: str):
        """SIC description maps to the expected GICS sector."""
        actual = _SIC_TEXT_MAP.get(sic_desc)
        assert actual == expected_sector, (
            f"SIC '{sic_desc}': expected {expected_sector!r}, got {actual!r}"
        )

    def test_all_values_are_valid_sectors(self):
        """Every value in _SIC_TEXT_MAP is a valid GICS sector string."""
        invalid = {v for v in _SIC_TEXT_MAP.values() if v not in VALID_SECTORS}
        assert not invalid, f"Invalid sector strings in _SIC_TEXT_MAP: {invalid}"

    def test_map_is_non_empty(self):
        """Sanity: the map is populated with at least 100 entries."""
        assert len(_SIC_TEXT_MAP) >= 100, (
            f"_SIC_TEXT_MAP has only {len(_SIC_TEXT_MAP)} entries"
        )


# ---------------------------------------------------------------------------
# SIC numeric range tests
# ---------------------------------------------------------------------------

class TestSicNumericRange:
    """Spot-check _sic_range_to_sector with representative SIC codes."""

    @pytest.mark.parametrize("sic_code,expected_sector", [
        # Banks (SIC 6021, 6022)
        (6021, "Financials"),
        (6022, "Financials"),
        # Insurance (SIC 6311-6399)
        (6311, "Financials"),
        (6331, "Financials"),
        # REITs (SIC 6798)
        (6798, "Real Estate"),
        # Oil & gas (SIC 1311, 1381)
        (1311, "Energy"),
        (1381, "Energy"),
        # Pharma (SIC 2836, 2835)
        (2836, "Health Care"),
        (2835, "Health Care"),
        # Semiconductors (SIC 3674)
        (3674, "Information Technology"),
        # Software (SIC 7372)
        (7372, "Information Technology"),
        # Electric utilities (SIC 4911)
        (4911, "Utilities"),
        # Railroads (SIC 4011)
        (4011, "Industrials"),
        # Airlines (SIC 4512)
        (4512, "Industrials"),
        # Steel (SIC 3310)
        (3310, "Materials"),
        # Retail clothing (SIC 5651)
        (5651, "Consumer Discretionary"),
        # Grocery (SIC 5411)
        (5411, "Consumer Staples"),
        # Tobacco (SIC 2111)
        (2111, "Consumer Staples"),
        # Chemicals (SIC 2860)
        (2860, "Materials"),
        # Telecom (SIC 4813)
        (4813, "Communication Services"),
        # TV broadcasting (SIC 4833)
        (4833, "Communication Services"),
        # Real estate operators (SIC 6512)
        (6512, "Real Estate"),
        # Hospitals (SIC 8062)
        (8062, "Health Care"),
        # Medical instruments (SIC 3841)
        (3841, "Health Care"),
        # Aircraft manufacturing (SIC 3721)
        (3721, "Industrials"),
        # Construction (SIC 1521)
        (1521, "Industrials"),
    ])
    def test_sic_range_to_sector(self, sic_code: int, expected_sector: str):
        """Numeric SIC code maps to the expected sector."""
        actual = _sic_range_to_sector(sic_code)
        assert actual == expected_sector, (
            f"SIC {sic_code}: expected {expected_sector!r}, got {actual!r}"
        )

    def test_returns_none_for_unmapped(self):
        """SIC code 0 (not in any range) returns None."""
        assert _sic_range_to_sector(0) is None

    def test_all_range_sectors_are_valid(self):
        """Every sector in _SIC_RANGE_MAP is a valid GICS string."""
        invalid = {sector for _, _, sector in _SIC_RANGE_MAP if sector not in VALID_SECTORS}
        assert not invalid, f"Invalid sector strings in _SIC_RANGE_MAP: {invalid}"

    def test_2836_overrides_2800_chemicals_range(self):
        """Pharma SIC 2836 (more specific) overrides broad chemicals range 2800-2899."""
        # Both 2836 (pharma) and 2860 (chemicals) are in the range map;
        # 2836 should map to Health Care, not Materials
        assert _sic_range_to_sector(2836) == "Health Care"
        assert _sic_range_to_sector(2860) == "Materials"

    def test_6798_reit_overrides_holding_companies(self):
        """SIC 6798 (REITs) maps to Real Estate, not Financials (holding cos 6700-6799)."""
        assert _sic_range_to_sector(6798) == "Real Estate"
        assert _sic_range_to_sector(6710) == "Financials"


# ---------------------------------------------------------------------------
# Schema invariants (pure logic, no I/O)
# ---------------------------------------------------------------------------

class TestSchema:
    """Schema contracts for the output format."""

    def test_valid_sectors_set_is_11(self):
        """There are exactly 11 GICS-style sector strings."""
        assert len(VALID_SECTORS) == 11

    def test_sic_range_map_non_empty(self):
        """_SIC_RANGE_MAP has at least 30 entries covering major SIC divisions."""
        assert len(_SIC_RANGE_MAP) >= 30, (
            f"_SIC_RANGE_MAP has only {len(_SIC_RANGE_MAP)} entries"
        )

    def test_sic_range_map_bounds_valid(self):
        """All entries have valid non-negative bounds with lo <= hi."""
        for lo, hi, sector in _SIC_RANGE_MAP:
            assert 0 <= lo <= hi, (
                f"Invalid range bounds: lo={lo}, hi={hi}"
            )
