"""tests/test_fred_alias_collision.py — Config-lint: no FRED id maps to two different aliases.

House law (FRED alias-collision law): if the same FRED series id appears in
multiple fred.series groups, every occurrence MUST use the IDENTICAL alias.
A collision (same id, different alias across groups) kills the entire FredAdapter
at runtime — an 8-run outage class event.

Coverage:
  1. no_alias_collisions    — assert no FRED id has two different aliases
  2. series_section_present — config has a fred.series dict (sanity guard)
  3. new_groups_present     — IRD-W1 groups added (em_oas_ladder, swap_lines,
                               em_vol, corridor_rates) exist in config
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import defaultdict

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402


# ---------------------------------------------------------------------------
# Load once at module level (no network, reads config.yml)
# ---------------------------------------------------------------------------

_cfg = config.load()
_fred_series: dict = _cfg.get("fred", {}).get("series", {})


# ---------------------------------------------------------------------------
# 1. no_alias_collisions
# ---------------------------------------------------------------------------

class TestNoAliasCollisions:
    def test_no_duplicate_id_different_aliases(self):
        """Each FRED series id must map to exactly ONE alias across all groups.

        Collision = same id, two or more distinct alias strings.
        """
        id_to_aliases: dict[str, set[str]] = defaultdict(set)

        for group_name, group in _fred_series.items():
            if not isinstance(group, dict):
                continue
            for fred_id, alias in group.items():
                id_to_aliases[fred_id].add(str(alias))

        collisions = {
            fred_id: aliases
            for fred_id, aliases in id_to_aliases.items()
            if len(aliases) > 1
        }

        assert not collisions, (
            "FRED alias collision detected — same id mapped to multiple aliases "
            "(this is an 8-run outage class event at runtime):\n"
            + "\n".join(
                f"  {fid!r}: {sorted(als)}"
                for fid, als in sorted(collisions.items())
            )
        )

    def test_all_aliases_are_strings(self):
        """Every alias value in fred.series must be a non-empty string."""
        bad: list[str] = []
        for group_name, group in _fred_series.items():
            if not isinstance(group, dict):
                continue
            for fred_id, alias in group.items():
                if not isinstance(alias, str) or not alias.strip():
                    bad.append(f"{group_name}.{fred_id}: {alias!r}")
        assert not bad, f"Non-string or empty aliases found:\n" + "\n".join(bad)


# ---------------------------------------------------------------------------
# 2. series_section_present
# ---------------------------------------------------------------------------

class TestSeriesSectionPresent:
    def test_fred_series_is_dict(self):
        """config must have a non-empty fred.series dict."""
        assert isinstance(_fred_series, dict) and len(_fred_series) > 0, (
            "fred.series is empty or missing from config.yml"
        )

    def test_minimum_group_count(self):
        """fred.series must have at least 10 groups (sanity guard against truncated config)."""
        assert len(_fred_series) >= 10, (
            f"fred.series only has {len(_fred_series)} groups — config may be truncated"
        )


# ---------------------------------------------------------------------------
# 3. new_groups_present (IRD-W1 additions)
# ---------------------------------------------------------------------------

class TestIrdW1GroupsPresent:
    _REQUIRED_GROUPS = [
        "em_oas_ladder",
        "swap_lines",
        "em_vol",
        "corridor_rates",
    ]

    def test_ird_w1_groups_exist(self):
        """IRD-W1 fred.series groups must be present in config.yml."""
        missing = [g for g in self._REQUIRED_GROUPS if g not in _fred_series]
        assert not missing, (
            f"IRD-W1 FRED groups missing from config.yml: {missing}"
        )

    def test_em_oas_ladder_key_ids(self):
        """em_oas_ladder must contain expected BAML EM series ids."""
        group = _fred_series.get("em_oas_ladder", {})
        expected_ids = [
            "BAMLEMHBHYCRPIOAS",
            "BAMLEMRACRPIASIAOAS",
            "BAMLEMRLCRPILAOAS",
            "BAMLEMRECRPIEMEAOAS",
        ]
        for sid in expected_ids:
            assert sid in group, (
                f"Expected FRED id {sid!r} missing from em_oas_ladder"
            )

    def test_swap_lines_contains_swpt_wlcfll(self):
        """swap_lines group must contain SWPT and WLCFLL."""
        group = _fred_series.get("swap_lines", {})
        assert "SWPT" in group, "SWPT missing from swap_lines group"
        assert "WLCFLL" in group, "WLCFLL missing from swap_lines group"

    def test_corridor_rates_has_effr(self):
        """corridor_rates group must contain EFFR."""
        group = _fred_series.get("corridor_rates", {})
        assert "EFFR" in group, "EFFR missing from corridor_rates group"

    def test_em_vol_has_vxeem(self):
        """em_vol group must contain VXEEMCLS."""
        group = _fred_series.get("em_vol", {})
        assert "VXEEMCLS" in group, "VXEEMCLS missing from em_vol group"
