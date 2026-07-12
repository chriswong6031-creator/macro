"""tests/test_cb_calendar.py — Schema sanity tests for data/intl_risk/cb_calendar.yml.

Validates the static CB meeting calendar created for IRD-W1 (IRD-R7: descriptive
only, no intent prediction).

Coverage:
  1. file_parseable          — YAML loads without error
  2. all_seven_banks         — FOMC/ECB/BoJ/BoE/SNB/BoC/RBA all present
  3. dates_are_valid         — every date entry parses as a valid YYYY-MM-DD date
  4. dates_in_2026           — all dates are in 2026 (remaining-2026 calendar)
  5. at_least_four_per_bank  — each bank has ≥ 4 dates (sanity against truncation)
  6. required_fields         — each bank entry has name_en, name_zh, country, source, dates
  7. source_is_string        — source field is a non-empty string URL
  8. country_code_present    — country field is a 2-letter ISO code
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import date

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Load fixture once
# ---------------------------------------------------------------------------

_CALENDAR_PATH = (
    Path(__file__).resolve().parent.parent
    / "data" / "intl_risk" / "cb_calendar.yml"
)

_REQUIRED_BANKS = {"FOMC", "ECB", "BoJ", "BoE", "SNB", "BoC", "RBA"}
_REQUIRED_FIELDS = {"name_en", "name_zh", "country", "dates", "source"}


@pytest.fixture(scope="module")
def calendar_data() -> dict:
    assert _CALENDAR_PATH.exists(), (
        f"cb_calendar.yml not found at {_CALENDAR_PATH}; "
        "IRD-W1 Task-5 may not have been executed"
    )
    with open(_CALENDAR_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# 1. file_parseable
# ---------------------------------------------------------------------------

class TestFileParseable:
    def test_yaml_loads(self, calendar_data: dict):
        """YAML must load to a dict (not None or scalar)."""
        assert isinstance(calendar_data, dict), (
            "cb_calendar.yml did not parse to a top-level dict"
        )

    def test_has_banks_key(self, calendar_data: dict):
        """Top-level key must be 'banks'."""
        assert "banks" in calendar_data, (
            f"Expected top-level key 'banks', got: {list(calendar_data.keys())}"
        )


# ---------------------------------------------------------------------------
# 2. all_seven_banks
# ---------------------------------------------------------------------------

class TestAllSevenBanks:
    def test_all_required_banks_present(self, calendar_data: dict):
        """FOMC, ECB, BoJ, BoE, SNB, BoC, RBA must all be in banks."""
        banks = calendar_data.get("banks", {})
        missing = _REQUIRED_BANKS - set(banks.keys())
        assert not missing, (
            f"Missing required bank entries: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# 3. dates_are_valid (YYYY-MM-DD parseable)
# ---------------------------------------------------------------------------

class TestDatesAreValid:
    def test_all_dates_parse(self, calendar_data: dict):
        """Every date entry must parse as a valid calendar date."""
        banks = calendar_data.get("banks", {})
        bad: list[str] = []
        for bank, entry in banks.items():
            for d in entry.get("dates", []):
                try:
                    date.fromisoformat(str(d))
                except ValueError:
                    bad.append(f"{bank}: {d!r}")
        assert not bad, f"Invalid date strings found:\n" + "\n".join(bad)


# ---------------------------------------------------------------------------
# 4. dates_in_2026
# ---------------------------------------------------------------------------

class TestDatesIn2026:
    def test_all_dates_in_2026(self, calendar_data: dict):
        """All dates must be in 2026 (this is the remaining-2026 calendar)."""
        banks = calendar_data.get("banks", {})
        wrong_year: list[str] = []
        for bank, entry in banks.items():
            for d in entry.get("dates", []):
                try:
                    parsed = date.fromisoformat(str(d))
                    if parsed.year != 2026:
                        wrong_year.append(f"{bank}: {d}")
                except ValueError:
                    pass  # caught in test_all_dates_parse
        assert not wrong_year, (
            "Dates outside 2026 found in cb_calendar.yml:\n"
            + "\n".join(wrong_year)
        )


# ---------------------------------------------------------------------------
# 5. at_least_four_per_bank
# ---------------------------------------------------------------------------

class TestMinimumDatesPerBank:
    def test_at_least_four_dates_per_bank(self, calendar_data: dict):
        """Each bank must have at least 4 meeting dates (guards against truncation)."""
        banks = calendar_data.get("banks", {})
        too_few: list[str] = []
        for bank in _REQUIRED_BANKS:
            entry = banks.get(bank, {})
            n = len(entry.get("dates", []))
            if n < 4:
                too_few.append(f"{bank}: {n} dates")
        assert not too_few, (
            "Banks with fewer than 4 dates (possible truncation):\n"
            + "\n".join(too_few)
        )


# ---------------------------------------------------------------------------
# 6. required_fields per bank entry
# ---------------------------------------------------------------------------

class TestRequiredFields:
    def test_all_required_fields_present(self, calendar_data: dict):
        """Each bank entry must have name_en, name_zh, country, dates, source."""
        banks = calendar_data.get("banks", {})
        missing_fields: list[str] = []
        for bank, entry in banks.items():
            if not isinstance(entry, dict):
                missing_fields.append(f"{bank}: not a dict")
                continue
            for field in _REQUIRED_FIELDS:
                if field not in entry:
                    missing_fields.append(f"{bank}.{field}")
        assert not missing_fields, (
            f"Missing required fields in cb_calendar.yml:\n"
            + "\n".join(missing_fields)
        )


# ---------------------------------------------------------------------------
# 7. source_is_string
# ---------------------------------------------------------------------------

class TestSourceIsString:
    def test_source_non_empty_string(self, calendar_data: dict):
        """source field must be a non-empty string for each bank."""
        banks = calendar_data.get("banks", {})
        bad: list[str] = []
        for bank, entry in banks.items():
            src = entry.get("source")
            if not isinstance(src, str) or not src.strip():
                bad.append(f"{bank}: {src!r}")
        assert not bad, f"Banks with missing/empty source:\n" + "\n".join(bad)


# ---------------------------------------------------------------------------
# 8. country_code_present (2-letter ISO alpha-2)
# ---------------------------------------------------------------------------

class TestCountryCode:
    def test_country_is_two_letter_code(self, calendar_data: dict):
        """country field must be a 2-letter uppercase string."""
        banks = calendar_data.get("banks", {})
        bad: list[str] = []
        for bank, entry in banks.items():
            country = entry.get("country", "")
            if not (isinstance(country, str) and len(country) == 2 and country.isupper()):
                bad.append(f"{bank}: {country!r}")
        assert not bad, (
            "Banks with non-2-letter country codes:\n" + "\n".join(bad)
        )
