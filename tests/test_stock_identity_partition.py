"""Stock Identity W1 — partition draws are disjoint and exactly reproducible.

The sealed calibration partition and the blind evaluation arm are only worth
anything if two properties hold mechanically: the three sets never overlap, and
re-running the draw from the committed universe snapshot plus the verbatim seed
strings reproduces the identical membership lists AND the identical hashes. If
either fails, "sealed" is a word rather than a fact.

These tests run offline against committed artifacts and small synthetic frames.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from engine.stock_identity import partition as part

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "stock_identity" / "partition" / "partition_manifest_v1.json"
SNAPSHOT = ROOT / "data" / "stock_identity" / "partition" / "universe_snapshot_v1.parquet"
REGISTRATION = ROOT / "research" / "stock_identity" / "W1_IDENTITY_ATLAS_V0_REGISTRATION.md"


def _manifest() -> dict:
    if not MANIFEST.exists():
        pytest.skip(f"{MANIFEST} not present in this checkout")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _snapshot() -> pd.DataFrame:
    if not SNAPSHOT.exists():
        pytest.skip(f"{SNAPSHOT} not present in this checkout")
    return pd.read_parquet(SNAPSHOT)


class TestSeeds:
    def test_seed_strings_are_verbatim_and_derive_the_recorded_seeds(self):
        # The registration writes the formula out; a drifted seed string would silently
        # produce a different, still-plausible-looking partition.
        assert part.SEED_STRING_BLIND == "stock-identity-blind-arm-v1"
        assert part.SEED_STRING_CALIBRATION == "stock-identity-sealed-calibration-partition-v1"
        assert part.SEED_STRING_DEAD == "stock-identity-pilot-dead-names-v1"
        for s, expected in (
            (part.SEED_STRING_BLIND, part.SEED_BLIND),
            (part.SEED_STRING_CALIBRATION, part.SEED_CALIBRATION),
            (part.SEED_STRING_DEAD, part.SEED_DEAD),
        ):
            assert expected == int(hashlib.sha256(s.encode()).hexdigest()[:16], 16)

    def test_manifest_records_the_same_seeds(self):
        m = _manifest()
        assert m["seeds"][part.SEED_STRING_BLIND] == part.SEED_BLIND
        assert m["seeds"][part.SEED_STRING_CALIBRATION] == part.SEED_CALIBRATION


class TestDisjointness:
    def test_pilot_blind_calibration_are_pairwise_disjoint(self):
        m = _manifest()
        pilot = set(m["pilot"]["members"])
        blind = set(m["blind_arm"]["members"])
        cal = set(m["calibration_partition"]["members"])
        assert pilot and blind and cal
        assert pilot & blind == set()
        assert pilot & cal == set()
        assert blind & cal == set()

    def test_check_disjoint_raises_on_overlap(self):
        with pytest.raises(ValueError):
            part.check_disjoint(["A", "B"], ["B", "C"], ["D"])
        part.check_disjoint(["A"], ["B"], ["C"])  # must not raise


class TestReproducibility:
    """Re-draw from the committed snapshot + seeds; demand identical lists and hashes."""

    def _redraw(self):
        snap = _snapshot()
        m = _manifest()
        sector_map = part.load_sector_map(ROOT)
        adv = pd.Series(snap["adv_252"].to_numpy(), index=snap["symbol"])
        vol = pd.Series(snap["realized_vol_252"].to_numpy(), index=snap["symbol"])
        strata = part.build_strata(
            snap, adv_252=adv, realized_vol_252=vol, sector_map=sector_map
        )
        pilot = list(m["pilot"]["members"])
        blind = part.draw_blind_arm(strata, pilot=pilot)
        cal = part.draw_calibration_partition(
            strata, pilot=pilot, blind=blind["members"]
        )
        return m, blind, cal

    def test_blind_arm_redraws_identically(self):
        m, blind, _ = self._redraw()
        assert blind["members"] == m["blind_arm"]["members"]
        assert blind["blind_sha256"] == m["blind_arm"]["blind_sha256"]

    def test_calibration_partition_redraws_identically(self):
        m, _, cal = self._redraw()
        assert cal["members"] == m["calibration_partition"]["members"]
        assert cal["calibration_sha256"] == m["calibration_partition"]["calibration_sha256"]

    def test_full_per_stratum_draw_order_is_persisted(self):
        # Provisionality (§3) only works if a later prefix-shrink can read the ORDER the
        # draw actually produced; storing just the chosen prefix would make the shrink
        # unauditable.
        m = _manifest()
        order = m["blind_arm"]["draw_order_by_stratum"]
        assert order
        chosen = set(m["blind_arm"]["members"])
        per = m["blind_arm"]["per_stratum"]
        recovered = {s for names in order.values() for s in names[:per]}
        assert recovered == chosen

    def test_universe_sha256_recomputes(self):
        m = _manifest()
        snap = _snapshot()
        assert part.universe_sha256(snap) == m["universe"]["universe_sha256"]

    def test_partition_procedure_sha256_recomputes_from_the_registration_text(self):
        m = _manifest()
        if not REGISTRATION.exists():
            pytest.skip("registration document not present")
        h, block = part.partition_procedure_sha256(REGISTRATION)
        assert block.startswith("## §4.")
        assert h == m["partition_procedure_sha256"]


class TestDrawOrder:
    def test_manifest_states_the_enforced_order(self):
        m = _manifest()
        assert m["draw_order_enforced"] == [
            "universe_snapshot",
            "pilot_cohort_fixed",
            "blind_arm_drawn",
            "calibration_partition_drawn",
            "manifest_hashes_written",
            "constants_calibrated",
        ]

    def test_calibration_history_cutoff_precedes_asof(self):
        m = _manifest()
        cutoff = pd.Timestamp(m["calibration_partition"]["calibration_history_cutoff"])
        asof = pd.Timestamp(m["asof"])
        assert cutoff < asof


class TestBlindEligibility:
    def test_blind_members_clear_the_declared_floors(self):
        m = _manifest()
        snap = _snapshot().set_index("symbol")
        floor = m["blind_arm"]["min_sessions"]
        for s in m["blind_arm"]["members"]:
            assert snap.loc[s, "n_rows"] >= floor
            assert bool(snap.loc[s, "blind_eligible"]) is True

    def test_sha256_of_symbols_is_order_independent(self):
        a = part.sha256_of_symbols(["B", "A", "C"])
        b = part.sha256_of_symbols(["A", "C", "B"])
        assert a == b
        assert a != part.sha256_of_symbols(["A", "C"])
