"""tests/test_fred_alias_collision.py — Config-lint: no FRED id maps to two different aliases.

House law (FRED alias-collision law): if the same FRED series id appears in
multiple fred.series groups, every occurrence MUST use the IDENTICAL alias.
A collision (same id, different alias across groups) silently dict-merges last-wins in
_all_series(), flipping the stored column alias out from under every consumer (and the
store upsert outlier guard then reads the wrong parquet — the 2026-07 8-run outage class)
at runtime — an 8-run outage class event.

The MIRROR direction is just as illegal and far quieter: two different FRED ids
claiming the SAME alias. Nothing crashes — engine/inputs.build_features flattens
every group into one sid->alias map and `_fred()` assigns out[alias] in dict order,
so the last group to register the alias simply wins and the other series vanishes
from the frame with no error, no log line, and a perfectly plausible number in its
place. That is exactly what happened to the 3m curve node: both DGS3MO (group
`curve`, constant-maturity, bond-equivalent basis) and DTB3 (group
`fx_rates_short`, secondary-market bill, DISCOUNT basis) were aliased `us3m`, and
`fx_rates_short` sorts later — so engine/yield_curve.NODES built its 0.25y point,
slope_3m10y, the NTFS recession read and the curve regime label off a discount-basis
bill running ~13bp below the CMT yield the rest of the curve was quoted on. The two
constructions disagree on whether 3m10y is inverted on 99 of the last 1260 sessions.
Fixed 2026-07-30: DTB3 -> us3m_bill.

Coverage:
  1. no_alias_collisions    — assert no FRED id has two different aliases
  2. no_alias_shared        — assert no alias is claimed by two different FRED ids
                               (the silent mirror of #1)
  3. series_section_present — config has a fred.series dict (sanity guard)
  4. new_groups_present     — IRD-W1 groups added (em_oas_ladder, swap_lines,
                               em_vol, corridor_rates) exist in config
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import defaultdict

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from engine.inputs import flatten_fred_aliases  # noqa: E402


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
# 2. no_alias_shared — the silent mirror of #1
# ---------------------------------------------------------------------------

class TestNoAliasSharedBetweenIds:
    def test_no_alias_claimed_by_two_ids(self):
        """Each alias must be owned by exactly ONE FRED series id across all groups.

        Unlike #1 this failure mode is silent — no KeyError, no stale adapter, just
        the wrong series quietly serving a named column in the feature frame.
        """
        alias_to_ids: dict[str, set[str]] = defaultdict(set)
        where: dict[str, set[str]] = defaultdict(set)

        for group_name, group in _fred_series.items():
            if not isinstance(group, dict):
                continue
            for fred_id, alias in group.items():
                alias_to_ids[str(alias)].add(str(fred_id))
                where[str(alias)].add(f"{fred_id} (group {group_name})")

        shared = {
            alias: ids for alias, ids in alias_to_ids.items() if len(ids) > 1
        }

        assert not shared, (
            "FRED alias claimed by more than one series id — engine/inputs flattens "
            "the groups and the last registration silently wins, so one of these "
            "series is simply not in the feature frame and the other is serving its "
            "name (the DGS3MO/DTB3 us3m case, fixed 2026-07-30):\n"
            + "\n".join(
                f"  {alias!r}: {sorted(where[alias])}"
                for alias in sorted(shared)
            )
        )

    def test_us3m_is_owned_by_dgs3mo(self):
        """Pin the specific regression: the 3m CURVE node is the constant-maturity
        yield (DGS3MO), not the discount-basis secondary-market bill (DTB3).

        engine/yield_curve.NODES quotes every other tenor from a DGS* constant-maturity
        series, and FRED's T10Y3M — which the engine prefers for spread_10y3m — is
        exactly DGS10 - DGS3MO. Sourcing the 0.25y node from DTB3 puts a discount-basis
        rate ~13bp light into a bond-equivalent curve.
        """
        curve = _fred_series.get("curve", {})
        assert curve.get("DGS3MO") == "us3m", (
            "curve.DGS3MO must be aliased 'us3m' — it is the bond-equivalent 3m node "
            "the rest of engine/yield_curve.NODES is quoted against"
        )
        for group_name, group in _fred_series.items():
            if not isinstance(group, dict):
                continue
            for fred_id, alias in group.items():
                assert not (alias == "us3m" and fred_id != "DGS3MO"), (
                    f"{fred_id} (group {group_name}) must not claim the 'us3m' alias — "
                    f"that is the DGS3MO constant-maturity curve node. A discount-basis "
                    f"bill belongs under a distinct alias (DTB3 -> us3m_bill)."
                )


class TestFlattenFredAliasesGuard:
    """engine.inputs.flatten_fred_aliases is the runtime half of the lint above."""

    def test_raises_on_alias_claimed_by_two_ids(self):
        cfg = {
            "curve": {"DGS3MO": "us3m"},
            "fx_rates_short": {"DTB3": "us3m"},
        }
        with pytest.raises(ValueError, match="us3m"):
            flatten_fred_aliases(cfg)

    def test_allows_same_id_in_several_groups_under_one_alias(self):
        """A series may feed several engines — that is legal and must not raise."""
        cfg = {
            "curve": {"DGS10": "us10y"},
            "bonds_extra": {"DGS10": "us10y", "DGS1": "us1y"},
        }
        assert flatten_fred_aliases(cfg) == {"DGS10": "us10y", "DGS1": "us1y"}

    def test_live_config_flattens_without_raising(self):
        """The committed config must survive the runtime guard."""
        flat = flatten_fred_aliases(_fred_series)
        assert flat["DGS3MO"] == "us3m"
        assert flat["DTB3"] == "us3m_bill"

    def test_tolerates_non_dict_group(self):
        assert flatten_fred_aliases({"curve": {"DGS10": "us10y"}, "junk": None}) == {
            "DGS10": "us10y"
        }


# ---------------------------------------------------------------------------
# 3. series_section_present
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
# 4. new_groups_present (IRD-W1 additions)
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
