"""Tests for scripts/build_flow_surface — the intraday Flow-Surface snapshot store.

Shape conformance is asserted against a VENDORED copy of the Terminal contract
(charting-app terminal/lib/surfaceContract.ts + the public/data/surface fixtures),
so this suite is self-contained and does not depend on the sibling repo being present.

Invariants (RECON §2, MASTERPLAN §3 Lane T item 5; surfaceContract.ts):

  (a) idx ↔ snapshot stamp consistency: index.stamps match the written per-stamp files,
      and index.latest === stamps[-1] (checkIndexFilesContract law).
  (b) grid dimensions == len(price_levels) × len(time_steps) for every metric grid, and
      the orientation is grids[metric][levelIdx][timeIdx].
  (c) cadence honesty: cadenceSec (int) + cadence (label) are present and reflect the
      passed write interval — never a finer cadence than the caller supplied.
  (d) idempotent stamp append: re-appending an existing stamp overwrites that column in
      place; it does not duplicate the stamp or grow the time axis.
  (e) empty-session behavior: an empty strike rollup yields no column (skipped), and an
      empty index has latest === null and passes the files contract with no files.
  (f) the produced idx + frame validate against the ported surfaceContract.ts validators
      AND carry exactly the keys the Terminal fixtures carry (diff-of-keys is empty for
      the required set).
"""
from __future__ import annotations

import json

from scripts.build_flow_surface import (
    append_stamp,
    build_index,
    build_and_stage_surfaces,
    cadence_label,
    check_index_files_contract,
    dry_run,
    frame_for_stamp,
    is_surface_frame,
    is_surface_index,
    net_prem_by_strike,
    resolve_surface_roots,
    validate_frame_dims,
)


# ── vendored ground truth: the Terminal fixture shapes (surfaceContract.ts) ──────────
# Required top-level keys the Terminal validators / fixture path read. Extra keys are
# tolerated by the validators (isSurfaceIndex/isSurfaceFrame check a subset), but our
# materializer must at minimum emit these.
IDX_REQUIRED_KEYS = {"date", "stamps", "latest", "cadenceSec"}
FRAME_REQUIRED_KEYS = {"spot", "price_levels", "time_steps", "grids", "asof", "cadence"}

# A verbatim slice of surface_idx_fixture.json (SPY) — the canonical index shape.
VENDORED_IDX_FIXTURE = {
    "date": "2026-07-06",
    "stamps": ["0931", "0936", "0941"],
    "latest": "0941",
    "cadenceSec": 300,
    "cadence": "5-min",
    "root": "SPY",
    "source": "fixture",
}

# A verbatim-shaped SurfaceFrame (surface_fixture.json / surfaceContract.test.ts FRAME):
# grids[metric][levelIdx][timeIdx], price_levels ascending, time_steps "HH:MM".
VENDORED_FRAME_FIXTURE = {
    "spot": 100,
    "price_levels": [90, 95, 100, 105, 110],
    "time_steps": ["09:31", "09:41", "09:51"],
    "grids": {"netprem": [[1, 2, 3], [-1, -2, -3], [0, 5, 10], [4, 4, 4], [0, 0, -8]]},
    "asof": "2026-07-06T13:51:00Z",
    "cadence": "10-min",
}


def _mk_strikes(**pairs) -> dict:
    """Build a root_strikes rollup {strike_str: {call_prem, put_prem, vol}} from
    {strike: (call_prem, put_prem)} kwargs (strike passed as e.g. s600=(...))."""
    out = {}
    for k, (call, put) in pairs.items():
        strike = k[1:] if k.startswith("s") else k
        out[str(float(strike))] = {"call_prem": call, "put_prem": put, "vol": 10}
    return out


# ── vendored-fixture sanity: the ground truth itself validates ──────────────────────

def test_vendored_fixtures_validate():
    assert is_surface_index(VENDORED_IDX_FIXTURE)
    assert is_surface_frame(VENDORED_FRAME_FIXTURE)
    # The fixture idx obeys the files contract against its own stamps, latest is last.
    r = check_index_files_contract(VENDORED_IDX_FIXTURE, VENDORED_IDX_FIXTURE["stamps"])
    assert r["ok"] and r["latestOk"]
    # Vendored frame grid is levels × steps.
    validate_frame_dims(VENDORED_FRAME_FIXTURE)


# ── (f) our output carries the required Terminal keys + validates ───────────────────

def test_output_keys_match_terminal_fixture():
    rep = dry_run(root="SPY", n_stamps=5, cadence_sec=120)
    idx, frame = rep["index"], rep["latest_frame"]

    # Diff-of-keys against the required set must be empty (we emit every required key).
    assert IDX_REQUIRED_KEYS - set(idx) == set(), f"idx missing {IDX_REQUIRED_KEYS - set(idx)}"
    assert FRAME_REQUIRED_KEYS - set(frame) == set(), f"frame missing {FRAME_REQUIRED_KEYS - set(frame)}"

    # And they validate against the ported contract.
    assert is_surface_index(idx)
    assert is_surface_frame(frame)


# ── (a) idx ↔ snapshot stamp consistency ────────────────────────────────────────────

def test_idx_snapshot_stamp_consistency():
    # Build a 3-stamp session by hand; the idx stamps must equal the per-stamp frames' union.
    full = None
    stamps_written = []
    for stamp, tstep, net in [
        ("0931", "09:31", {600.0: 1_000.0}),
        ("0941", "09:41", {600.0: 2_500.0, 605.0: -400.0}),
        ("0951", "09:51", {600.0: 3_000.0, 605.0: -900.0}),
    ]:
        full = append_stamp(full, stamp=stamp, time_step=tstep, net_by_strike=net,
                            spot=602.0, asof="x", cadence_sec=120,
                            session_date="2026-07-06", root="SPY")
        stamps_written.append(stamp)

    idx = build_index(full, session_date="2026-07-06", cadence_sec=120, root="SPY")
    assert idx["stamps"] == stamps_written
    assert idx["latest"] == "0951"
    # checkIndexFilesContract: idx.stamps must match the files we'd write (one per stamp).
    r = check_index_files_contract(idx, stamps_written)
    assert r["ok"] is True
    assert r["missing"] == [] and r["extra"] == []
    # A missing file is flagged.
    assert check_index_files_contract(idx, ["0931", "0951"])["missing"] == ["0941"]
    # An extra file is flagged.
    assert check_index_files_contract(idx, stamps_written + ["1001"])["extra"] == ["1001"]
    # latest must be the last stamp.
    bad = dict(idx, latest="0941")
    assert check_index_files_contract(bad, stamps_written)["latestOk"] is False


# ── (b) grid dimensions == levels × steps, orientation [level][time] ─────────────────

def test_grid_dims_levels_by_steps():
    full = None
    # Two strikes appear at t0; a third strike enters at t1 (union grows the level axis,
    # and the earlier column reads 0.0 for the late-arriving strike).
    full = append_stamp(full, stamp="0931", time_step="09:31",
                        net_by_strike={600.0: 5.0, 605.0: -3.0},
                        spot=602.0, asof="x", cadence_sec=120,
                        session_date="d", root="SPY")
    full = append_stamp(full, stamp="0941", time_step="09:41",
                        net_by_strike={600.0: 9.0, 605.0: -7.0, 610.0: 2.0},
                        spot=603.0, asof="x", cadence_sec=120,
                        session_date="d", root="SPY")

    assert full["price_levels"] == [600.0, 605.0, 610.0]  # ascending union
    assert full["time_steps"] == ["09:31", "09:41"]
    grid = full["grids"]["netprem"]
    # dims: 3 levels × 2 steps
    assert len(grid) == 3
    assert all(len(row) == 2 for row in grid)
    validate_frame_dims(full)
    # orientation grid[levelIdx][timeIdx]: strike 600 (idx 0) over time = [5, 9]
    assert grid[0] == [5.0, 9.0]
    # strike 605 (idx 1) = [-3, -7]
    assert grid[1] == [-3.0, -7.0]
    # strike 610 (idx 2) entered at t1 → column 0 is 0.0 (honest, no premium yet), t1 = 2
    assert grid[2] == [0.0, 2.0]


def test_validate_frame_dims_raises_on_mismatch():
    import pytest
    bad = {
        "price_levels": [1, 2, 3],
        "time_steps": ["09:31", "09:41"],
        "grids": {"netprem": [[1, 2], [3, 4]]},  # only 2 rows, need 3
    }
    with pytest.raises(ValueError):
        validate_frame_dims(bad)


# ── net premium column semantics: call_prem - put_prem per strike ───────────────────

def test_net_prem_by_strike():
    rstk = _mk_strikes(s600=(1_000.0, 400.0), s605=(200.0, 900.0))
    net = net_prem_by_strike(rstk)
    assert net[600.0] == 600.0    # 1000 - 400
    assert net[605.0] == -700.0   # 200 - 900
    # Non-numeric / malformed entries are skipped, never fabricated.
    assert net_prem_by_strike({"NaN-strike": {"call_prem": 1}}) == {}
    assert net_prem_by_strike({}) == {}


# ── (c) cadence honesty ─────────────────────────────────────────────────────────────

def test_cadence_honesty():
    idx = build_index(
        append_stamp(None, stamp="0931", time_step="09:31", net_by_strike={600.0: 1.0},
                     spot=1.0, asof="x", cadence_sec=120, session_date="d", root="SPY"),
        session_date="d", cadence_sec=120, root="SPY",
    )
    assert idx["cadenceSec"] == 120
    assert isinstance(idx["cadenceSec"], int) and not isinstance(idx["cadenceSec"], bool)
    assert idx["cadence"] == "2-min"
    # Label table + fallbacks (never claims finer than the true interval).
    assert cadence_label(60) == "1-min"
    assert cadence_label(300) == "5-min"
    assert cadence_label(600) == "10-min"
    assert cadence_label(45) == "45s"       # sub-minute honest label
    assert cadence_label(180) == "3-min"    # uncommon interval rounds to minutes
    assert cadence_label(0) == "" and cadence_label(-5) == ""


# ── (d) idempotent stamp append ─────────────────────────────────────────────────────

def test_idempotent_stamp_append():
    full = append_stamp(None, stamp="0931", time_step="09:31",
                        net_by_strike={600.0: 5.0}, spot=1.0, asof="x",
                        cadence_sec=120, session_date="d", root="SPY")
    full = append_stamp(full, stamp="0941", time_step="09:41",
                        net_by_strike={600.0: 9.0}, spot=1.0, asof="x",
                        cadence_sec=120, session_date="d", root="SPY")
    assert full["stamps"] == ["0931", "0941"]
    assert full["grids"]["netprem"][0] == [5.0, 9.0]

    # Re-append 0941 with a CORRECTED value — must overwrite that column, not duplicate.
    full2 = append_stamp(full, stamp="0941", time_step="09:41",
                         net_by_strike={600.0: 12.0}, spot=1.0, asof="x",
                         cadence_sec=120, session_date="d", root="SPY")
    assert full2["stamps"] == ["0931", "0941"]                # no duplicate stamp
    assert full2["time_steps"] == ["09:31", "09:41"]          # time axis unchanged
    assert len(full2["grids"]["netprem"][0]) == 2             # still 2 columns
    assert full2["grids"]["netprem"][0] == [5.0, 12.0]        # column overwritten
    # idx built from the re-appended frame stays contract-consistent.
    idx = build_index(full2, session_date="d", cadence_sec=120, root="SPY")
    assert check_index_files_contract(idx, full2["stamps"])["ok"] is True


# ── frame_for_stamp: replay truncation matches flowSource.ts surface: logic ──────────

def test_frame_for_stamp_truncates_to_realized_window():
    full = None
    for stamp, tstep, val in [("0931", "09:31", 1.0), ("0941", "09:41", 2.0), ("0951", "09:51", 3.0)]:
        full = append_stamp(full, stamp=stamp, time_step=tstep, net_by_strike={600.0: val},
                            spot=val, asof="x", cadence_sec=120, session_date="d", root="SPY")
    # Mid stamp → only the first two columns realized.
    mid = frame_for_stamp(full, "0941")
    assert mid["time_steps"] == ["09:31", "09:41"]
    assert mid["grids"]["netprem"][0] == [1.0, 2.0]
    assert mid["spot"] == 2.0  # spot resolved from spot_path at that column
    validate_frame_dims(mid)
    # Latest stamp → full day.
    latest = frame_for_stamp(full, "0951")
    assert latest["time_steps"] == ["09:31", "09:41", "09:51"]
    assert latest["grids"]["netprem"][0] == [1.0, 2.0, 3.0]
    # Unknown stamp → full day (never fabricated).
    unk = frame_for_stamp(full, "9999")
    assert unk["time_steps"] == ["09:31", "09:41", "09:51"]


# ── (e) empty-session behavior ──────────────────────────────────────────────────────

def test_empty_index_latest_is_null():
    empty = {"stamps": []}
    idx = build_index(empty, session_date="2026-07-06", cadence_sec=120, root="SPY")
    assert idx["latest"] is None
    assert idx["stamps"] == []
    assert is_surface_index(idx)
    # Empty index passes the files contract with no files; a non-null latest fails latestOk.
    assert check_index_files_contract(idx, [])["ok"] is True
    assert check_index_files_contract(dict(idx, latest="0931"), [])["latestOk"] is False


def test_empty_rollup_writes_no_column(tmp_path, monkeypatch):
    # build_and_stage_surfaces must skip a root whose strike rollup is empty this cycle
    # (never blanks a good prior frame). Redirect the staging dir to tmp_path.
    import lib.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)

    paths = build_and_stage_surfaces(
        root_strikes_by_root={"SPY": {}},   # empty rollup
        roots=["SPY"],
        session_date="2026-07-06",
        asof="2026-07-06T13:51:00Z",
        cadence_sec=120,
    )
    assert paths == []                       # nothing staged
    assert not (tmp_path / "live_flow_out" / "surface" / "SPY").exists() or \
        list((tmp_path / "live_flow_out" / "surface" / "SPY").glob("*.json")) == []


# ── build_and_stage_surfaces: end-to-end staging + R2 key shape ─────────────────────

def test_build_and_stage_surfaces_writes_files_and_keys(tmp_path, monkeypatch):
    import lib.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)

    rstk = {"SPY": _mk_strikes(s600=(1_000_000.0, 400_000.0), s605=(200_000.0, 900_000.0))}
    paths = build_and_stage_surfaces(
        root_strikes_by_root=rstk,
        roots=["SPY"],
        session_date="2026-07-06",
        asof="2026-07-06T13:51:00Z",
        cadence_sec=120,
        spot_by_root={"SPY": 602.5},
    )
    # Two files staged: idx.json + one {HHMM}.json, with the exact R2 keys the Terminal
    # flowSource.ts r2Key() resolves (live_flow/surface/{ROOT}/…).
    keys = {k for _, k in paths}
    assert any(k == "live_flow/surface/SPY/idx.json" for k in keys)
    snap_keys = [k for k in keys if k != "live_flow/surface/SPY/idx.json"]
    assert len(snap_keys) == 1
    assert snap_keys[0].startswith("live_flow/surface/SPY/") and snap_keys[0].endswith(".json")

    # The staged idx + snapshot are valid and mutually consistent.
    idx_local = next(p for p, k in paths if k.endswith("idx.json"))
    snap_local = next(p for p, k in paths if k != "live_flow/surface/SPY/idx.json")
    idx = json.loads(idx_local.read_text())
    snap = json.loads(snap_local.read_text())
    assert is_surface_index(idx)
    assert is_surface_frame(snap)
    # idx stamp == the one snapshot file's stamp.
    stamp_from_key = snap_local.stem
    assert idx["stamps"] == [stamp_from_key]
    assert idx["latest"] == stamp_from_key
    # snapshot content: 2 strikes, 1 time step, net = call - put.
    assert snap["price_levels"] == [600.0, 605.0]
    assert snap["grids"]["netprem"][0] == [600000.0]   # 1_000_000 - 400_000
    assert snap["grids"]["netprem"][1] == [-700000.0]  # 200_000 - 900_000
    validate_frame_dims(snap)


def test_second_cycle_appends_column(tmp_path, monkeypatch):
    # Two consecutive cycles for the same root must produce a 2-column grid (append, not
    # replace) with two distinct stamp files listed in idx.
    import lib.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)
    from datetime import datetime, timezone

    t1 = datetime(2026, 7, 6, 13, 31, tzinfo=timezone.utc)  # 09:31 ET
    t2 = datetime(2026, 7, 6, 13, 41, tzinfo=timezone.utc)  # 09:41 ET

    build_and_stage_surfaces(
        root_strikes_by_root={"SPY": _mk_strikes(s600=(1_000.0, 0.0))},
        roots=["SPY"], session_date="2026-07-06", asof="a", cadence_sec=600, now=t1,
    )
    paths2 = build_and_stage_surfaces(
        root_strikes_by_root={"SPY": _mk_strikes(s600=(3_000.0, 0.0))},
        roots=["SPY"], session_date="2026-07-06", asof="b", cadence_sec=600, now=t2,
    )
    idx_local = next(p for p, k in paths2 if k.endswith("idx.json"))
    idx = json.loads(idx_local.read_text())
    assert idx["stamps"] == ["0931", "0941"]
    assert idx["latest"] == "0941"
    # The latest snapshot has 2 columns; strike 600 cumulative net = [1000, 3000].
    snap_local = next(p for p, k in paths2 if k.endswith("0941.json"))
    snap = json.loads(snap_local.read_text())
    assert snap["time_steps"] == ["09:31", "09:41"]
    assert snap["grids"]["netprem"][0] == [1000.0, 3000.0]
    # Both stamp files exist on disk → idx ↔ files contract holds.
    surf_dir = tmp_path / "live_flow_out" / "surface" / "SPY"
    on_disk = sorted(p.stem for p in surf_dir.glob("*.json") if p.stem not in ("idx", "_full"))
    assert on_disk == ["0931", "0941"]
    assert check_index_files_contract(idx, on_disk)["ok"] is True


# ── root resolution lever ───────────────────────────────────────────────────────────

def test_resolve_surface_roots():
    assert resolve_surface_roots({}) == ["SPY", "QQQ", "IWM"]
    assert resolve_surface_roots({"surface_roots": ["SPY", "TSLA"]}) == ["SPY", "TSLA"]
    # top_n appends the highest-gross actives, deduped, capped at base + top_n.
    got = resolve_surface_roots(
        {"surface_top_n": 2},
        root_gross_today={"NVDA": 9e9, "SPY": 8e9, "AAPL": 7e9, "META": 6e9},
    )
    assert got[:3] == ["SPY", "QQQ", "IWM"]      # base preserved, order-stable
    assert len(got) == 5                          # 3 base + 2 extra
    assert "NVDA" in got and "AAPL" in got        # SPY already in base, so next two by gross


# ── dry-run self-check gate ─────────────────────────────────────────────────────────

def test_dry_run_all_checks_pass():
    rep = dry_run(root="QQQ", n_stamps=8, cadence_sec=120)
    assert all(rep["checks"].values()), rep["checks"]
    # Mid frame is strictly shorter than the latest (replay truncation is real).
    assert len(rep["mid_frame"]["time_steps"]) < len(rep["latest_frame"]["time_steps"])
    assert rep["index"]["cadenceSec"] == 120
    assert rep["index"]["cadence"] == "2-min"
