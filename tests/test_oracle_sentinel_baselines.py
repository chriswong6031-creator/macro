"""PR-A1 conformance tests: onset-edge decay baselines + sentinel monitor_inert fix.

Two concerns this file guards:

A. every member of engine.oracle.contract._DISPLAY_WITH_EDGE_COMPOUNDS must
   have a published stat resolvable from the COMMITTED gauntlet artifacts
   (data/oracle/gauntlet/p3_results.json + p3b_routing_placebo.json).
   Future unpublished-edge-cell blindness becomes a CI failure.

B. the decay-monitor path for the two onset cells (ep_in_onset_21d /
   ep_out_onset_5d) no longer produces a monitor_inert trip when run against
   the committed files — the fix that motivated this PR.

NOTE: tests in group A use the REAL committed files (copied to a tmp dir so
the sentinel writer does not dirty the repo). Tests in group B do the same
and additionally plant synthetic live-episode rows to confirm the monitor
actually reads the published baselines and progresses past the monitor_inert
guard.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Paths to the real committed artifacts
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent
_GAUNTLET_DIR = _REPO_ROOT / "data" / "oracle" / "gauntlet"
_P3_RESULTS = _GAUNTLET_DIR / "p3_results.json"
_P3B_PLACEBO = _GAUNTLET_DIR / "p3b_routing_placebo.json"

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from engine.oracle.contract import _DISPLAY_WITH_EDGE_COMPOUNDS  # noqa: E402
from engine.oracle.sentinels import _load_published_stats, check_edge_decay  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _copy_gauntlet_to_tmp(tmp_path: Path) -> Path:
    """Copy the real gauntlet artifacts into a tmp oracle/gauntlet tree.

    Returns the tmp data_dir (parent of oracle/).
    """
    gauntlet_dst = tmp_path / "oracle" / "gauntlet"
    gauntlet_dst.mkdir(parents=True)
    shutil.copy2(_P3_RESULTS, gauntlet_dst / "p3_results.json")
    shutil.copy2(_P3B_PLACEBO, gauntlet_dst / "p3b_routing_placebo.json")
    return tmp_path


def _plant_live_episodes(
    data_dir: Path,
    *,
    n: int,
    mean: float,
    direction: str,
    horizon: int,
) -> None:
    """Write synthetic episodes_s.parquet with post-adjudication matured rows."""
    rows = []
    # onset_date must be after _ADJUDICATION_DATE = 2026-07-04
    base = pd.Timestamp("2026-07-10")
    for i in range(n):
        rows.append({
            "node": "XLE",
            "direction": direction,
            "onset_date": base + pd.Timedelta(days=i),
            f"outcome_rs_{horizon}d": mean,
            f"outcome_mature_{horizon}d": True,
        })
    df = pd.DataFrame(rows)
    oracle_dir = data_dir / "oracle"
    oracle_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(oracle_dir / "episodes_s.parquet")


# ---------------------------------------------------------------------------
# Group A — every display_with_edge compound resolves to a published stat
# ---------------------------------------------------------------------------

def test_all_display_edge_compounds_have_published_stat(tmp_path):
    """CI guard: every member of _DISPLAY_WITH_EDGE_COMPOUNDS must appear in
    the stats dict loaded from the committed gauntlet artifacts.

    If a future PR adds a new display_with_edge cell without committing its
    baseline, this test will fail — making the blindness visible at CI rather
    than silently tripping monitor_inert at runtime.
    """
    if not _P3_RESULTS.exists() or not _P3B_PLACEBO.exists():
        pytest.skip(
            "Gauntlet artifacts not present in this checkout "
            "(data/ is gitignored on CI without the artifact cache)"
        )

    data_dir = _copy_gauntlet_to_tmp(tmp_path)
    stats = _load_published_stats(data_dir)

    missing = sorted(c for c in _DISPLAY_WITH_EDGE_COMPOUNDS if c not in stats)
    assert not missing, (
        f"Published stat MISSING for {len(missing)} display_with_edge cell(s): "
        f"{missing}. "
        f"Either commit the baseline in data/oracle/gauntlet/p3_results.json "
        f"(episode cells) or p3b_routing_placebo.json (routing cells), "
        f"or remove the cell from _DISPLAY_WITH_EDGE_COMPOUNDS in contract.py."
    )


def test_onset_cell_baselines_correct_values(tmp_path):
    """The two onset edge cells carry the adjudicated DA means from
    ORACLE_GAUNTLET_P3_RESULTS.md (transcribed 2026-07-06).

    ep_out_onset_5d: DA +0.50%  (n=391)
    ep_in_onset_21d: DA +0.62%  (n=355)
    """
    if not _P3_RESULTS.exists():
        pytest.skip("p3_results.json not present in this checkout")

    data_dir = _copy_gauntlet_to_tmp(tmp_path)
    stats = _load_published_stats(data_dir)

    # ep_out_onset_5d
    assert "ep_out_onset_5d" in stats, "ep_out_onset_5d missing from published stats"
    assert abs(stats["ep_out_onset_5d"] - 0.005) < 1e-9, (
        f"ep_out_onset_5d: expected +0.005, got {stats['ep_out_onset_5d']}"
    )

    # ep_in_onset_21d
    assert "ep_in_onset_21d" in stats, "ep_in_onset_21d missing from published stats"
    assert abs(stats["ep_in_onset_21d"] - 0.0062) < 1e-9, (
        f"ep_in_onset_21d: expected +0.0062, got {stats['ep_in_onset_21d']}"
    )


# ---------------------------------------------------------------------------
# Group B — decay monitor no longer trips monitor_inert for onset cells
# ---------------------------------------------------------------------------

def test_ep_in_onset_21d_no_monitor_inert_with_committed_artifacts(tmp_path):
    """ep_in_onset_21d: with the committed p3_results.json in place, the
    decay monitor must NOT produce a monitor_inert trip (the pre-PR bug).

    We plant n=5 live rows (below the n>=10 reporting floor) so the monitor
    loads the stat, finds insufficient accrual, and exits silently — the key
    requirement is no monitor_inert trip.
    """
    if not _P3_RESULTS.exists():
        pytest.skip("p3_results.json not present in this checkout")

    data_dir = _copy_gauntlet_to_tmp(tmp_path)
    # plant minimal live rows so the parquet read succeeds (n<10 → silent skip)
    _plant_live_episodes(data_dir, n=5, mean=0.0062, direction="in", horizon=21)

    log_path = tmp_path / "oracle" / "sentinel_log.jsonl"
    trips = check_edge_decay(data_dir, log_path)

    monitor_inert_trips = [t for t in trips if "monitor_inert" in t]
    assert not monitor_inert_trips, (
        f"ep_in_onset_21d still producing monitor_inert despite committed "
        f"baselines: {monitor_inert_trips}"
    )


def test_ep_out_onset_5d_no_monitor_inert_with_committed_artifacts(tmp_path):
    """ep_out_onset_5d: same guard as above for the exit onset cell."""
    if not _P3_RESULTS.exists():
        pytest.skip("p3_results.json not present in this checkout")

    data_dir = _copy_gauntlet_to_tmp(tmp_path)
    _plant_live_episodes(data_dir, n=5, mean=0.005, direction="out", horizon=5)

    log_path = tmp_path / "oracle" / "sentinel_log.jsonl"
    trips = check_edge_decay(data_dir, log_path)

    monitor_inert_trips = [t for t in trips if "monitor_inert" in t]
    assert not monitor_inert_trips, (
        f"ep_out_onset_5d still producing monitor_inert despite committed "
        f"baselines: {monitor_inert_trips}"
    )


def test_decay_monitor_fires_sign_flip_once_baselines_loaded(tmp_path):
    """Confirm the monitor is ACTIVE (not inert) by planting a sign-flip with
    n>=30 post-adjudication rows for ep_in_onset_21d.

    Published: +0.62%. Live mean planted: -2.0%. With n=35 matured rows the
    monitor should trip decay_watch[sign_flip], not monitor_inert.
    """
    if not _P3_RESULTS.exists():
        pytest.skip("p3_results.json not present in this checkout")

    data_dir = _copy_gauntlet_to_tmp(tmp_path)
    _plant_live_episodes(data_dir, n=35, mean=-0.02, direction="in", horizon=21)

    log_path = tmp_path / "oracle" / "sentinel_log.jsonl"
    trips = check_edge_decay(data_dir, log_path)

    # Must have a sign_flip trip for ep_in_onset_21d
    sign_flip_trips = [
        t for t in trips if "sign_flip" in t and "ep_in_onset_21d" in t
    ]
    assert sign_flip_trips, (
        f"Expected decay_watch[sign_flip] for ep_in_onset_21d with published "
        f"+0.62% and live -2.0% at n=35, but got trips: {trips}"
    )

    # Must NOT also have a monitor_inert trip
    monitor_inert_trips = [t for t in trips if "monitor_inert" in t]
    assert not monitor_inert_trips, (
        f"monitor_inert tripped alongside sign_flip — baselines may not have "
        f"loaded correctly: {monitor_inert_trips}"
    )


# ---------------------------------------------------------------------------
# Group C — p3_results.json structural sanity checks
# ---------------------------------------------------------------------------

def test_p3_results_json_schema_sanity():
    """Structural checks on the committed p3_results.json:
    - top-level 'episodes' key present and is a dict
    - both onset-edge cell_ids present
    - direction_adjusted_mean field is a float for each
    - s3_error_rates present with expected sub-keys
    """
    if not _P3_RESULTS.exists():
        pytest.skip("p3_results.json not present in this checkout")

    data = json.loads(_P3_RESULTS.read_text())

    assert "episodes" in data, "episodes key missing from p3_results.json"
    assert isinstance(data["episodes"], dict), "episodes must be a dict"

    for cell_id in ("ep_in_onset_21d", "ep_out_onset_5d"):
        assert cell_id in data["episodes"], (
            f"{cell_id} missing from p3_results.json episodes"
        )
        row = data["episodes"][cell_id]
        assert "direction_adjusted_mean" in row, (
            f"{cell_id}: direction_adjusted_mean field missing"
        )
        assert isinstance(row["direction_adjusted_mean"], (int, float)), (
            f"{cell_id}: direction_adjusted_mean must be numeric, "
            f"got {type(row['direction_adjusted_mean'])}"
        )

    assert "s3_error_rates" in data, "s3_error_rates key missing from p3_results.json"
    er = data["s3_error_rates"]
    for key in (
        "false_start_rate_out_5d",
        "false_start_rate_in_5d",
        "onset_to_confirmed_rate_out",
        "onset_to_confirmed_rate_in",
    ):
        assert key in er, f"s3_error_rates missing sub-key: {key}"
