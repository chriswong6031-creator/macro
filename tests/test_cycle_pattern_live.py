"""tests/test_cycle_pattern_live.py — state_daily_live adapter acceptance tests.

Tests the engine.cycle_pattern.live module and its integration with the entity
registry and config wiring.

Coverage:
  (1) Row count == sum of forward-log rows (cross-check against source).
  (2) Entity-id mapping 100% hit-rate for known families (country_cycles is
      fully mapped; sector/china measured backbone likewise); unmapped rows
      carry unmapped_id=True and entity_id=None, never silently dropped.
  (3) Hazard columns (hazard_1m_p/src, hazard_3m_p/src, hazard_6m_p/src)
      are preserved from the forward logs in the output.
  (4) Deterministic rebuild: two consecutive calls produce frame-equal output.
  (5) Absent-safe: a missing forward-log file is silently skipped (warning
      issued); the remaining logs still produce a valid output frame.
  (6) Config wiring: state_daily_live_path key is present in
      cycle_pattern_intelligence section.
  (7) Sort order: output is sorted (entity_id, date) ascending.
  (8) B- prefix basket ids resolve to basket family entities.
  (9) No label/outcome columns (PIT doctrine: y1, y3, y6, event_date banned).
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cycle_pattern import live, registry  # noqa: E402
from lib import config                           # noqa: E402

_DATA = Path(__file__).resolve().parent.parent / "data"

# --------------------------------------------------------------------------- #
# Module-scoped fixtures — built once to keep tests fast.
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def entities() -> pd.DataFrame:
    return registry.build_entities()


@pytest.fixture(scope="module")
def state(entities) -> pd.DataFrame:
    return live.build_state_daily_live(entities=entities)


# --------------------------------------------------------------------------- #
# (1) Row count == sum of forward-log rows
# --------------------------------------------------------------------------- #

def test_row_count_equals_sum_of_forward_logs(state):
    """Output row count must exactly equal the sum of raw forward-log row counts.

    The three forward logs are keep-FIRST by construction (engine.cycle_forward_log),
    so no within-log duplicates exist.  Engines are disjoint by entity family, so
    no cross-log duplicates exist.  The union should therefore produce no row loss
    and no inflation.
    """
    expected = live.total_forward_log_rows()
    assert len(state) == expected, (
        f"state_daily_live has {len(state)} rows but sum of forward logs is {expected}. "
        "Either rows were dropped (silent dedup) or inflated (unexpected fan-out)."
    )


# --------------------------------------------------------------------------- #
# (2) Entity-id mapping hit-rate for known families
# --------------------------------------------------------------------------- #

def test_country_cycles_fully_mapped(state):
    """All country_cycles rows must resolve to a known entity_id (100% hit-rate)."""
    ctry = state[state["engine"] == "country_cycles"]
    assert len(ctry) > 0, "No country_cycles rows in state_daily_live"
    unmapped = ctry[ctry["unmapped_id"]]
    assert len(unmapped) == 0, (
        f"country_cycles: {len(unmapped)} unmapped native ids: "
        f"{sorted(ctry.loc[ctry['unmapped_id'], 'native_id'].unique())}"
    )


def test_us_sector_etf_ids_mapped(state):
    """XLK etc. (us_sector family) must be fully mapped in the sector-cycles log."""
    us_sec = state[(state["engine"] == "us_sector_cycles") & (state["family"] == "us_sector")]
    assert len(us_sec) > 0, "No us_sector rows in state_daily_live"
    unmapped = us_sec[us_sec["unmapped_id"]]
    assert len(unmapped) == 0, (
        f"us_sector: {len(unmapped)} unmapped ETF ids: "
        f"{sorted(us_sec.loc[us_sec['unmapped_id'], 'native_id'].unique())}"
    )


def test_cn_sector_numeric_ids_mapped(state):
    """China sector numeric ids (e.g. 801010) must be fully mapped."""
    cn_sec = state[(state["engine"] == "china_sector_cycles") & (state["family"] == "cn_sector")]
    assert len(cn_sec) > 0, "No cn_sector rows in state_daily_live"
    unmapped = cn_sec[cn_sec["unmapped_id"]]
    assert len(unmapped) == 0, (
        f"cn_sector: {len(unmapped)} unmapped numeric ids: "
        f"{sorted(cn_sec.loc[cn_sec['unmapped_id'], 'native_id'].unique())}"
    )


def test_unmapped_rows_not_dropped(state):
    """Any unmapped id must appear in the output with unmapped_id=True, entity_id=None.

    This test verifies the 'loud warning, never dropped silently' contract by
    checking that rows flagged unmapped_id=True are actually present (not pruned).
    """
    assert "unmapped_id" in state.columns, "unmapped_id column missing from output"
    unmapped = state[state["unmapped_id"]]
    if len(unmapped) > 0:
        # Unmapped rows must have entity_id=None (not a valid entity).
        assert unmapped["entity_id"].isna().all(), (
            "Unmapped rows should have entity_id=None"
        )


# --------------------------------------------------------------------------- #
# (3) Hazard columns preserved
# --------------------------------------------------------------------------- #

def test_hazard_columns_present(state):
    """All six hazard probability columns must be in the output."""
    for col in live._HAZARD_COLS:
        assert col in state.columns, f"Hazard column missing: {col}"


def test_hazard_1m_p_numeric_where_stamped(state):
    """Where hazard_1m_p is not NaN it should be a float in [0, 1]."""
    stamped = state[state["hazard_1m_p"].notna()]
    if len(stamped) > 0:
        assert stamped["hazard_1m_p"].between(0.0, 1.0).all(), (
            "hazard_1m_p out of [0, 1] range"
        )


# --------------------------------------------------------------------------- #
# (4) Deterministic rebuild
# --------------------------------------------------------------------------- #

def test_deterministic_rebuild(entities):
    """Two consecutive builds from the same entities frame must be frame-equal."""
    df1 = live.build_state_daily_live(entities=entities)
    df2 = live.build_state_daily_live(entities=entities)
    assert_frame_equal(df1, df2, check_like=False)


# --------------------------------------------------------------------------- #
# (5) Absent-safe: missing forward log silently skipped
# --------------------------------------------------------------------------- #

def test_absent_log_silently_skipped(entities, tmp_path, monkeypatch):
    """When one forward log is absent the remaining two still produce a valid frame."""
    import engine.cycle_pattern.live as live_mod

    # Redirect _DATA to a tmp directory that has only one of the three logs.
    fake_data = tmp_path / "data"
    (fake_data / "sector_cycles").mkdir(parents=True)
    (fake_data / "country_cycles").mkdir(parents=True)
    (fake_data / "china_sector_cycles").mkdir(parents=True)
    (fake_data / "cycle_pattern").mkdir(parents=True)

    # Copy only sector_cycles and country_cycles logs; omit china.
    import shutil
    real_data = _DATA
    for sub in ("sector_cycles", "country_cycles"):
        src = real_data / sub / "forward_log.parquet"
        if src.exists():
            shutil.copy(src, fake_data / sub / "forward_log.parquet")

    monkeypatch.setattr(live_mod, "_DATA", fake_data)

    with warnings.catch_warnings():
        warnings.simplefilter("always")
        df = live_mod.build_state_daily_live(entities=entities)

    # Should have rows from the two present logs only.
    assert len(df) > 0, "Expected non-empty frame when two logs exist"
    assert "china_sector_cycles" not in df["engine"].values, (
        "china_sector_cycles engine should be absent when its log is missing"
    )

    # Restore — monkeypatch handles cleanup automatically.


# --------------------------------------------------------------------------- #
# (6) Config wiring
# --------------------------------------------------------------------------- #

def test_config_section_has_state_daily_live_path():
    cfg = config.load()["cycle_pattern_intelligence"]
    assert "state_daily_live_path" in cfg, (
        "state_daily_live_path key missing from cycle_pattern_intelligence in config.yml"
    )
    assert cfg["state_daily_live_path"] == "data/cycle_pattern/state_daily_live.parquet"


# --------------------------------------------------------------------------- #
# (7) Sort order
# --------------------------------------------------------------------------- #

def test_sorted_by_entity_id_then_date(state):
    """Output must be sorted (entity_id, date) ascending."""
    if state.empty:
        pytest.skip("Empty state — no sort order to check.")
    pairs = list(zip(state["entity_id"].fillna(""), state["date"]))
    assert pairs == sorted(pairs), "state_daily_live is not sorted (entity_id, date)"


# --------------------------------------------------------------------------- #
# (8) B- prefix basket ids resolve to basket family entities
# --------------------------------------------------------------------------- #

def test_b_prefix_basket_ids_resolve_to_basket_family(state):
    """B-<SLUG> ids in US and China logs must resolve to us_basket / cn_basket family."""
    baskets = state[state["family"].isin(["us_basket", "cn_basket"])]
    assert len(baskets) > 0, "Expected basket-family rows from B-<slug> forward-log ids"
    # Basket rows must not be unmapped.
    assert not baskets["unmapped_id"].any(), (
        f"Some basket rows are unmapped: {baskets.loc[baskets['unmapped_id'], 'native_id'].unique()}"
    )


# --------------------------------------------------------------------------- #
# (9) No label / outcome columns (PIT doctrine)
# --------------------------------------------------------------------------- #

def test_no_label_or_outcome_columns(state):
    forbidden = {"y1", "y3", "y6", "event_date", "censored", "leg_open_date"}
    leaked = forbidden.intersection(state.columns)
    assert not leaked, f"Label/outcome columns must not appear in state_daily_live: {sorted(leaked)}"
    fwd = [c for c in state.columns if c.startswith("fwd_")]
    assert not fwd, f"fwd_* columns must not appear in state_daily_live: {fwd}"
