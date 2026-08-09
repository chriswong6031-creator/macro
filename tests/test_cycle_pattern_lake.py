"""CPI substrate v0 tests — entity registry + unified monthly PIT state lake.

Encodes the acceptance contract for engine.cycle_pattern.{registry,lake}:
row counts, entity family coverage, the 2026-06-30 join slice, the doctrine
label-exclusion, basket pit_membership, and deterministic rebuild.

Builds artifacts in-memory (no disk dependency on a prior driver run); a
separate test asserts the driver writes byte-deterministic parquet.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cycle_pattern import lake, registry  # noqa: E402
from lib import config  # noqa: E402

# Families the registry reads out of a data artifact, and the artifact each one is
# read from. The contract is FAITHFULNESS — one entity per member of the source, no
# drops and no duplicates — not a frozen universe size.
#
# It used to be a dict of literals ({"us_basket": 47, ...}), and that rotted exactly
# the way a literal over a growing store must: the code comment still said 46, the
# literal said 47, and data/baskets/membership.json had reached 48, so the suite was
# red on main. Nothing caught it because the suite is named by no CI job. Bumping the
# number would only buy time until the next basket lands; measuring the registry
# against its own source is the assertion that was meant all along, and it FAILS on
# the thing worth failing on (a family silently losing or doubling members).
_ARTIFACT_FAMILIES = {
    "us_basket": ("baskets/membership.json", "baskets"),
    "cn_basket": ("baskets_china/membership.json", "baskets"),
    "nasdaq_group": ("baskets_nasdaq/membership.json", "amalgamations"),
    "russell_group": ("baskets_russell/membership.json", "amalgamations"),
}

# Blocs are the curated split of the country-cycles universe (registry._COUNTRY_BLOC_IDS);
# country is its complement. Both are pinned against that split, not against a literal.
_MIN_TOTAL_ENTITIES = 140
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
def _artifact_members(rel: str, key: str) -> set[str]:
    payload = json.loads((Path(config.data_dir()) / rel).read_text(encoding="utf-8"))
    return set(payload[key])


def test_entity_count_and_families(entities):
    assert len(entities) >= _MIN_TOTAL_ENTITIES
    counts = entities["family"].value_counts().to_dict()

    # Every family the registry enumerates is present and non-empty.
    for fam in (*_ARTIFACT_FAMILIES, "us_sector", "cn_sector",
                "country", "bloc", "flagship_band"):
        assert counts.get(fam, 0) > 0, f"family {fam} vanished from the registry"

    # Artifact-backed families: exactly one entity per member, by NATIVE ID —
    # a count alone would pass if one member were dropped and another doubled.
    for fam, (rel, key) in _ARTIFACT_FAMILIES.items():
        got = set(entities.loc[entities["family"] == fam, "native_id"])
        assert got == _artifact_members(rel, key), (
            f"{fam} does not mirror data/{rel}: "
            f"missing={sorted(_artifact_members(rel, key) - got)} "
            f"extra={sorted(got - _artifact_members(rel, key))}"
        )

    # country/bloc are one universe split on a curated bloc list; the split must be
    # exact and exhaustive, which is the part a per-family literal never checked.
    blocs = set(entities.loc[entities["family"] == "bloc", "native_id"])
    countries = set(entities.loc[entities["family"] == "country", "native_id"])
    assert blocs == set(registry._COUNTRY_BLOC_IDS)
    assert not (blocs & countries)


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
# monthly oscillator columns (Wave 0 substrate)
# --------------------------------------------------------------------------- #
def test_osc_columns_present(state):
    """All six oscillator columns must be present in the state lake."""
    for col in ("mmacd_hist", "mmacd_sign", "mmacd_slope", "mstoch_k", "mstoch_d", "osc_missing"):
        assert col in state.columns, f"oscillator column {col!r} missing from state lake"


def test_osc_missing_china_always_true(state):
    """All China sector rows must carry osc_missing=True (no yahoo daily tape)."""
    cn = state[state["engine"] == "china_sector_cycles"]
    assert len(cn) == 4900
    assert cn["osc_missing"].all(), "China sectors must be osc_missing=True (no yahoo tape)"
    for col in ("mmacd_hist", "mmacd_sign", "mmacd_slope", "mstoch_k", "mstoch_d"):
        assert cn[col].isna().all(), f"China {col} must be NaN when osc_missing=True"


def test_osc_nonnull_for_liquid_entities(state):
    """US sector and country entities with enough history must have non-null oscillators."""
    # XLK and XLY have backfill from 2010-12-31 — well above the 40-bar threshold.
    xlk = state[(state["native_id"] == "XLK") & (~state["osc_missing"])]
    assert len(xlk) > 0, "XLK must have at least one non-missing oscillator row"
    assert xlk["mmacd_hist"].notna().all()
    assert xlk["mstoch_k"].between(0, 100).all(), "mstoch_k must be in [0, 100]"
    assert xlk["mstoch_d"].between(0, 100).all(), "mstoch_d must be in [0, 100]"
    assert xlk["mmacd_sign"].isin([-1.0, 1.0, 0.0]).all(), "mmacd_sign must be -1/0/+1"


def test_yahoo_tape_is_resolved_with_the_case_the_store_actually_uses(entities):
    """The oscillator read must name its file in the store's OWN case.

    `_compute_monthly_oscs_for_entity` used to `.lower()` the native_id before
    `store.read("yahoo", ...)`. Every file in that side-store is UPPERCASE, so the lowered
    name resolves on a case-INSENSITIVE checkout (macOS/APFS — every dev machine here, and
    the self-hosted mac lanes) and returns None on `ubuntu-latest`, where the ci-pack jobs
    run. A None read is indistinguishable from "this entity has no tape", so the whole US
    sector/country cross-section silently fell through to osc_missing=True and
    test_osc_nonnull_for_liquid_entities above failed on an empty frame — a red that
    CANNOT be reproduced on the machine most of us verify on.

    So this compares against `os.listdir`, which reports the name as STORED even on a
    case-insensitive filesystem. `Path.exists()` would not: it is the very check that
    lies here, and a guard that cannot see the failure it names is decoration.
    """
    import os

    ydir = Path(config.data_dir()) / "yahoo"
    if not ydir.is_dir():
        pytest.skip("yahoo side-store is not present in this checkout")
    on_disk = set(os.listdir(ydir))

    backed = entities[entities["engine"].isin(["us_sector_cycles", "country_cycles"])]
    native_ids = sorted({str(n) for n in backed["native_id"]})
    assert native_ids, "no yahoo-backed entities — this guard would be vacuous"

    # THE READER'S OWN function, not a re-implementation of it. A copy of the rule here
    # would pass while the reader lowered its key, which is exactly the defect.
    def _resolve(nid: str) -> str:
        return f"{lake.yahoo_key(nid)}.parquet"

    present = [n for n in native_ids if _resolve(n) in on_disk]
    assert present, (
        "not ONE yahoo-backed entity resolves to a file whose case matches the store. "
        f"tried e.g. {[_resolve(n) for n in native_ids[:4]]}; the store holds "
        f"{sorted(on_disk)[:4]}")

    # And the lowered spelling — the defect — must NOT be what the store holds, or this
    # guard is pinning a convention that does not exist.
    lowered = [n for n in present if _resolve(n).lower() in on_disk
               and _resolve(n).lower() != _resolve(n)]
    assert not lowered, (
        f"the store holds lowercase names for {lowered[:4]} — the convention this guard "
        "pins has changed; update the reader and this test together")


def test_osc_missing_early_periods_us(state):
    """Rows with fewer than 40 completed monthly bars at stamp date must be osc_missing."""
    # XLC launched 2018; backfill goes back to ~2019; early rows have <40 monthly bars.
    xlc = state[state["native_id"] == "XLC"]
    missing_xlc = xlc[xlc["osc_missing"]]
    assert len(missing_xlc) > 0, "XLC early rows must be osc_missing (new ETF)"
    # All missing rows should be NaN for float oscillator columns.
    for col in ("mmacd_hist", "mstoch_k"):
        assert missing_xlc[col].isna().all()


def test_osc_row_count_unchanged(state):
    """Adding oscillator columns must not change the row count (12519)."""
    assert len(state) == 12519, f"row count changed: {len(state)} != 12519"


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
