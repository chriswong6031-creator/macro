"""CPI substrate v0 tests — entity registry + unified monthly PIT state lake.

Encodes the acceptance contract for engine.cycle_pattern.{registry,lake}:
row counts, entity family coverage, the 2026-06-30 join slice, the doctrine
label-exclusion, basket pit_membership, and deterministic rebuild.

Builds artifacts in-memory (no disk dependency on a prior driver run); a
separate test asserts the driver writes byte-deterministic parquet.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cycle_pattern import lake, registry  # noqa: E402
from lib import config  # noqa: E402

# Expected family cardinalities (the enumerated universe).
_EXPECTED_FAMILIES = {
    "us_sector": 11, "us_basket": 46, "nasdaq_group": 8, "russell_group": 11,
    "cn_sector": 31, "cn_basket": 22, "country": 24, "bloc": 7,
    "flagship_band": 20,
}
_BACKFILL_TOTAL = 1881 + 5738 + 4900  # 12_519
_BASKET_FAMILIES = ["us_basket", "nasdaq_group", "russell_group", "cn_basket", "bloc"]


@pytest.fixture(scope="module")
def entities() -> pd.DataFrame:
    return registry.build_entities()


@pytest.fixture(scope="module")
def state() -> pd.DataFrame:
    return lake.build_state_monthly()


# --------------------------------------------------------------------------- #
# entity registry
# --------------------------------------------------------------------------- #
def test_entity_count_and_families(entities):
    assert len(entities) >= 140
    counts = entities["family"].value_counts().to_dict()
    for fam, n in _EXPECTED_FAMILIES.items():
        assert counts.get(fam, 0) == n, f"{fam}: {counts.get(fam, 0)} != {n}"


def test_entity_id_stable_and_sorted(entities):
    assert entities["entity_id"].is_unique
    assert list(entities["entity_id"]) == sorted(entities["entity_id"])
    # slug shape '<family>:<native_id>', except flagship bands use the
    # spec-mandated 'flagship:<band_id>' prefix (family stays 'flagship_band').
    for eid, fam, nid in zip(entities["entity_id"], entities["family"],
                            entities["native_id"]):
        prefix = "flagship" if fam == "flagship_band" else fam
        assert eid == f"{prefix}:{nid}"


def test_baskets_and_amalgams_are_not_pit(entities):
    bf = entities[entities["family"].isin(_BASKET_FAMILIES)]
    assert len(bf) > 0
    assert (~bf["pit_membership"]).all()
    # conversely the measured backbone IS pit
    mb = entities[entities["family"].isin(
        ["us_sector", "cn_sector", "country", "flagship_band"])]
    assert mb["pit_membership"].all()


def test_flagship_bands_present(entities):
    fb = entities[entities["family"] == "flagship_band"]
    assert len(fb) == 20
    assert (fb["tier"] == "measured").all()
    assert fb["basis"].notna().all()


# --------------------------------------------------------------------------- #
# state lake
# --------------------------------------------------------------------------- #
def test_state_row_count(state):
    assert len(state) == _BACKFILL_TOTAL == 12519


def test_no_label_or_outcome_columns(state):
    for col in ("y1", "y3", "y6", "event_date", "censored", "leg_open_date"):
        assert col not in state.columns, f"{col} must not be in state lake"
    assert not [c for c in state.columns if c.startswith("fwd_")]


def test_2026_06_30_slice_fully_joined(state):
    d = state[state["date"] == "2026-06-30"]
    assert len(d) == 73
    # 100% hazard feature join hit-rate on the panel backbone this date
    assert d["age_m"].notna().all()
    assert (d["hazard_epoch"] == lake.HAZARD_EPOCH).all()
    assert d["engine"].value_counts().to_dict() == {
        "country_cycles": 31, "china_sector_cycles": 31, "us_sector_cycles": 11}


def test_china_schema_gap_flagged(state):
    cn = state[state["china_schema_v0"]]
    assert len(cn) == 4900
    for col in ("pos_v2", "phase_v2", "stance", "divergence", "overdue"):
        assert cn[col].isna().all(), f"china {col} should be NaN/None"
    # non-china rows are not flagged
    assert (~state.loc[~state["china_schema_v0"], "china_schema_v0"]).all()


def test_every_state_entity_is_registered(state, entities):
    assert set(state["entity_id"]).issubset(set(entities["entity_id"]))


def test_hazard_epoch_marker_matches_features(state):
    # hazard_epoch set iff features joined
    assert (state["hazard_epoch"].notna() == state["age_m"].notna()).all()


# --------------------------------------------------------------------------- #
# metadata sidecar
# --------------------------------------------------------------------------- #
def test_meta_covers_all_columns_with_pit_class(state, tmp_path):
    import json
    p = tmp_path / "meta.json"
    lake.write_meta(p)
    meta = json.loads(p.read_text())
    cols = meta["columns"]
    assert set(state.columns) == set(cols), "meta must document every state column"
    assert cols["quad"]["pit_class"] == "revision_optimistic"
    assert cols["liquidity"]["pit_class"] == "revision_optimistic"
    assert cols["age_m"]["pit_class"] == "pit_pure"
    assert cols["phase"]["pit_class"] == "engine_stamped"
    assert "2024-01-01" in meta["_note"]  # embargo note


# --------------------------------------------------------------------------- #
# determinism + config wiring
# --------------------------------------------------------------------------- #
def test_deterministic_rebuild(entities, state):
    assert_frame_equal(entities, registry.build_entities())
    assert_frame_equal(state, lake.build_state_monthly())
    # parquet bytes are identical across serialisations
    assert entities.to_parquet(index=False) == registry.build_entities().to_parquet(index=False)


def test_config_section_registered():
    cfg = config.load()["cycle_pattern_intelligence"]
    assert cfg["version"] == "v0"
    for k in ("entities_path", "state_monthly_path", "state_monthly_meta_path"):
        assert cfg[k].startswith("data/cycle_pattern/")
    assert cfg["hazard_epoch"] == "price_c4414dcb"
