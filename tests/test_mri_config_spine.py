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
# vintage_series must stay a SUPERSET of DEFAULT_VINTAGE_SERIES
#
# collectors/fred.py::_vintage_series() is
#     self.cfg.get("vintage_series", DEFAULT_VINTAGE_SERIES)
# — an OVERRIDE, not a merge — and fetch_vintages() concats what it fetched and
# writes data/fred_vintage/vintages.parquet WHOLESALE. So a series that is in
# DEFAULT_VINTAGE_SERIES but missing from this config list is DELETED from the
# store on the next keyed collect, and nothing says so: the collector warns on
# fetch errors, never on omissions.
#
# This has now happened twice. IC4WSA/CCSA went from 891/876 rows to zero and
# took the claims point forecast and NFP's claims_survey_week_ccsa leg with them
# (restored in #3710). PPIFES/ECIALLCIV/ECIWAG went from 148/51/118 rows to zero (#3735)
# and left the CPI bridge's core_goods_pipeline block running on PPIFIS alone
# under a spec that declares an equal-weight PPIFIS+PPIFES average.
#
# config.yml's own comment has always asserted the superset invariant in prose.
# This is the executable form of it.
# ---------------------------------------------------------------------------

def test_vintage_series_superset_of_default(cfg):
    """config.yml's fred.vintage_series must cover every DEFAULT_VINTAGE_SERIES member.

    The config value REPLACES the default rather than extending it, and the store is
    rewritten wholesale from whatever was fetched — so anything dropped here is deleted
    from data/fred_vintage/vintages.parquet on the next keyed collect, silently.
    """
    from collectors.fred import DEFAULT_VINTAGE_SERIES

    configured = set(_vintage_series(cfg))
    missing = sorted(set(DEFAULT_VINTAGE_SERIES) - configured)
    assert not missing, (
        f"fred.vintage_series is missing {len(missing)} DEFAULT_VINTAGE_SERIES "
        f"member(s): {missing}. The config list OVERRIDES the default (it does not "
        f"extend it) and fetch_vintages() rewrites vintages.parquet wholesale, so "
        f"these would be DELETED from the point-in-time store on the next keyed "
        f"collect — with no warning, since the collector only reports fetch errors. "
        f"Either add them back, or remove them from DEFAULT_VINTAGE_SERIES with a "
        f"reason, but do not let the two lists drift apart."
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
