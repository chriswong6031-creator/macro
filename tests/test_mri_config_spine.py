"""Config sanity tests for MRI-PR-A data spine additions.

Verifies that:
  - The four new FRED series (GASREGW, JTSJOL, ADPMNUSNERSA, UNRATE, RSAFS) are
    present in the fred.series groups of config.yml.
  - UNRATE, RSAFS, JTSJOL, ADPMNUSNERSA appear in the vintage_series list.
  - The cleveland_nowcast config block exists with a month_url field.
  - The release_intel group is present and has the expected series ids.

No network. Reads config.yml from the repo root.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Fixture: load config once
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cfg() -> dict:
    cfg_path = Path(__file__).resolve().parent.parent / "config.yml"
    with cfg_path.open() as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_series_ids(cfg: dict) -> set[str]:
    """Collect every FRED series id across all groups."""
    ids: set[str] = set()
    for grp in cfg["fred"]["series"].values():
        ids.update(grp.keys())
    return ids


def _vintage_series(cfg: dict) -> list[str]:
    return cfg["fred"].get("vintage_series", [])


# ---------------------------------------------------------------------------
# Series presence in fred.series groups
# ---------------------------------------------------------------------------

MRI_FRED_SERIES = ["GASREGW", "JTSJOL", "ADPMNUSNERSA", "UNRATE", "RSAFS"]


@pytest.mark.parametrize("sid", MRI_FRED_SERIES)
def test_series_in_fred_groups(cfg, sid):
    """Each new MRI series is declared in at least one fred.series group."""
    all_ids = _all_series_ids(cfg)
    assert sid in all_ids, (
        f"{sid} not found in any fred.series group. "
        f"Available groups: {list(cfg['fred']['series'].keys())}"
    )


def test_release_intel_group_exists(cfg):
    """A 'release_intel' group exists in fred.series."""
    assert "release_intel" in cfg["fred"]["series"], (
        "release_intel group missing from fred.series"
    )


def test_release_intel_group_has_all_series(cfg):
    """The release_intel group contains all five MRI series ids."""
    grp = cfg["fred"]["series"].get("release_intel", {})
    for sid in MRI_FRED_SERIES:
        assert sid in grp, f"release_intel group missing series {sid}; found: {list(grp.keys())}"


# ---------------------------------------------------------------------------
# Vintage series list
# ---------------------------------------------------------------------------

MRI_VINTAGE_SERIES = ["UNRATE", "RSAFS", "JTSJOL", "ADPMNUSNERSA"]


@pytest.mark.parametrize("sid", MRI_VINTAGE_SERIES)
def test_series_in_vintage_list(cfg, sid):
    """Each MRI labor/release series is in vintage_series for ALFRED PIT fetching."""
    vintage = _vintage_series(cfg)
    assert sid in vintage, (
        f"{sid} not in fred.vintage_series. "
        f"It must be added so nightly fetches initial-release ALFRED vintages (MRI-R6)."
    )


# ---------------------------------------------------------------------------
# Cleveland nowcast config block
# ---------------------------------------------------------------------------

def test_cleveland_nowcast_block_exists(cfg):
    """cleveland_nowcast config block is present at the top level."""
    assert "cleveland_nowcast" in cfg, "cleveland_nowcast block missing from config.yml"


def test_cleveland_nowcast_has_month_url(cfg):
    """cleveland_nowcast block contains a month_url pointing to the Cleveland JSON."""
    block = cfg.get("cleveland_nowcast", {})
    assert "month_url" in block, "cleveland_nowcast.month_url missing"
    url = block["month_url"]
    assert "clevelandfed.org" in url, f"month_url does not point to clevelandfed.org: {url}"
    assert "nowcast_month.json" in url, f"month_url does not point to nowcast_month.json: {url}"


def test_cleveland_nowcast_has_retries(cfg):
    """cleveland_nowcast block contains a retries field."""
    block = cfg.get("cleveland_nowcast", {})
    assert "retries" in block, "cleveland_nowcast.retries missing"
    assert isinstance(block["retries"], int) and block["retries"] > 0
