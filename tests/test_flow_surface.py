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
  (g) date-keyed retention (M-XP a): every cycle ALSO emits date-keyed copies under
      live_flow/surface/{ROOT}/{YYYY-MM-DD}/ plus a dates.json sessions index, the LEGACY
      today-paths keep being written byte-identically (transition safety), and the R2
      retention prune keeps the newest N sessions while never touching the today-paths.
"""
from __future__ import annotations

import json

from scripts.build_flow_surface import (
    GREEK_METRICS,
    METRIC_GEX,
    METRIC_NETPREM,
    R2_SURFACE_PREFIX,
    SURFACE_RETAIN_SESSIONS,
    append_stamp,
    build_dates_index,
    build_index,
    build_and_stage_surfaces,
    cadence_label,
    check_index_files_contract,
    dated_surface_keys,
    dry_run,
    extract_cycle_quotes,
    frame_for_stamp,
    greek_columns_for_stamp,
    is_session_date,
    is_surface_dates,
    is_surface_frame,
    is_surface_index,
    list_surface_session_dates,
    merge_surface_dates,
    net_prem_by_strike,
    oi_by_contract,
    prune_surface_dates,
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


def _legacy_stamp_keys(keys, root: str = "SPY") -> list[str]:
    """The legacy today-path {HHMM}.json keys — live_flow/surface/{ROOT}/{HHMM}.json only.

    Discriminates by depth: a legacy key has exactly one segment after {ROOT}, a date-keyed
    key has two (…/{YYYY-MM-DD}/{HHMM}.json). idx.json and dates.json are excluded.
    """
    base = f"{R2_SURFACE_PREFIX}{root}/"
    return sorted(
        k for k in keys
        if k.startswith(base)
        and "/" not in k[len(base):]
        and not k.endswith(("idx.json", "dates.json"))
    )


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
    # flowSource.ts r2Key() resolves (live_flow/surface/{ROOT}/…). M-XP(a) adds date-keyed
    # copies + dates.json on top; the LEGACY today-keys below must stay exactly as they were.
    keys = {k for _, k in paths}
    assert any(k == "live_flow/surface/SPY/idx.json" for k in keys)
    snap_keys = _legacy_stamp_keys(keys)
    assert len(snap_keys) == 1
    assert snap_keys[0].startswith("live_flow/surface/SPY/") and snap_keys[0].endswith(".json")

    # The staged idx + snapshot are valid and mutually consistent.
    idx_local = next(p for p, k in paths if k == "live_flow/surface/SPY/idx.json")
    snap_local = next(p for p, k in paths if k == snap_keys[0])
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
    idx_local = next(p for p, k in paths2 if k == "live_flow/surface/SPY/idx.json")
    idx = json.loads(idx_local.read_text())
    assert idx["stamps"] == ["0931", "0941"]
    assert idx["latest"] == "0941"
    # The latest snapshot has 2 columns; strike 600 cumulative net = [1000, 3000].
    snap_local = next(p for p, k in paths2 if k == "live_flow/surface/SPY/0941.json")
    snap = json.loads(snap_local.read_text())
    assert snap["time_steps"] == ["09:31", "09:41"]
    assert snap["grids"]["netprem"][0] == [1000.0, 3000.0]
    # Both stamp files exist on disk → idx ↔ files contract holds. ("dates" is the M-XP(a)
    # sessions index, not a stamp file — the local staging dir stays flat, one dir per root.)
    surf_dir = tmp_path / "live_flow_out" / "surface" / "SPY"
    on_disk = sorted(p.stem for p in surf_dir.glob("*.json")
                     if p.stem not in ("idx", "_full", "dates"))
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
    # Lane G: the dry-run session builds real greek grids → the greek checks are present.
    assert rep["has_greeks"] is True
    assert rep["checks"]["greekMetricsPresent(gex,dex,vanna,charm)"] is True
    assert rep["checks"]["wallsPresent"] is True
    assert rep["checks"]["coveragePresent(0..1)"] is True


# ══════════════════════════════════════════════════════════════════════════════════════
# Lane G — intraday greek grids (gex/dex/vanna/charm) + walls + coverage
# ══════════════════════════════════════════════════════════════════════════════════════
#
# The netprem grid is unchanged (Wave 1); these assert the ADDITIVE greek machinery:
#   (g1) append_stamp carries gex/dex/vanna/charm as parallel levels×time grids, unioned
#        strike rows, one column per stamp — same orientation as netprem.
#   (g2) a netprem-only append (no greeks) is byte-identical to the Wave-1 frame (no
#        walls_path/coverage_path keys leak in).
#   (g3) frame_for_stamp truncates the greek grids AND surfaces per-stamp walls + coverage.
#   (g4) extract_cycle_quotes pulls the freshest NBBO mid per (exp,strike,right) from a tape.
#   (g5) oi_by_contract keys correctly; greek_columns_for_stamp joins quotes↔OI honestly.
#   (g6) POLLER FENCE: a greek failure must NOT break the netprem column write.
#   (g7) end-to-end build_and_stage_surfaces with quotes → frames carry greek grids + walls.

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine.intraday_greeks import bs_price  # noqa: E402


def _bs_chain_quotes(spot=600.0, iv=0.20, T=7 / 365.0, exp_str="2026-07-13",
                     strikes=(590.0, 595.0, 600.0, 605.0, 610.0)):
    """Synthetic {quotes, oi_map} for the greek path: BS-priced mids + call-above/put-below OI."""
    quotes, oi_map = [], {}
    for K in strikes:
        for right, isc in (("C", True), ("P", False)):
            mid = float(bs_price(spot, np.array([K]), np.array([T]), np.array([iv]),
                                 np.array([isc]), 0.043, 0.0)[0])
            if mid <= 0.02:
                continue
            quotes.append({"exp_str": exp_str, "exp_years": T, "strike": float(K),
                           "right": right, "mid": mid})
            oi = 800.0 + max(0.0, K - spot) * 60.0 if isc else 800.0 + max(0.0, spot - K) * 60.0
            oi_map[(exp_str, float(K), right)] = oi
    return quotes, oi_map


# ── (g1) append_stamp carries greek grids in netprem orientation ─────────────────────

def test_append_stamp_carries_greek_grids():
    greek = {
        METRIC_GEX: {600.0: 5e6, 605.0: 3e6},
        "dex": {600.0: 1e8, 605.0: 1.1e8},
        "vanna": {600.0: 2e5, 605.0: 3e5},
        "charm": {600.0: -4e5, 605.0: -5e5},
    }
    full = append_stamp(None, stamp="0931", time_step="09:31",
                        net_by_strike={600.0: 1000.0, 605.0: -500.0},
                        spot=602.0, asof="x", cadence_sec=120, session_date="d", root="SPY",
                        greek_by_strike=greek,
                        walls={"flip": 601.0, "callWall": 605.0, "putWall": 600.0},
                        coverage=1.0)
    # All five grids present, each levels×steps.
    assert set(full["metrics"]) == {METRIC_NETPREM, *GREEK_METRICS}
    validate_frame_dims(full)  # asserts EVERY grid is levels×steps
    assert full["grids"][METRIC_GEX][full["price_levels"].index(600.0)] == [5000000.0]
    # Second stamp appends a column to every grid.
    full = append_stamp(full, stamp="0941", time_step="09:41",
                        net_by_strike={600.0: 2000.0, 605.0: -900.0},
                        spot=603.0, asof="y", cadence_sec=120, session_date="d", root="SPY",
                        greek_by_strike={METRIC_GEX: {600.0: 6e6, 605.0: 3.5e6},
                                         "dex": {}, "vanna": {}, "charm": {}},
                        walls={"flip": 602.0, "callWall": 605.0, "putWall": 600.0},
                        coverage=0.8)
    validate_frame_dims(full)
    assert full["grids"][METRIC_GEX][full["price_levels"].index(600.0)] == [5000000.0, 6000000.0]
    # Strikes with no greek this stamp read 0.0 (honest), not forward-filled.
    assert full["grids"]["dex"][full["price_levels"].index(600.0)] == [100000000.0, 0.0]


# ── (g2) netprem-only frame unchanged (no greek bookkeeping leaks) ───────────────────

def test_greek_column_missing_this_cycle_keeps_prior_greeks():
    # Cross-cycle fence: a cycle whose greek path failed (greek_by_strike=None) must not
    # crash and must PRESERVE prior greek columns; the failed cycle's greek column reads
    # 0.0 (honest — no greek this cycle), while netprem still advances.
    full = append_stamp(None, stamp="0931", time_step="09:31", net_by_strike={600.0: 1000.0},
                        greek_by_strike={METRIC_GEX: {600.0: 5e6}, "dex": {}, "vanna": {}, "charm": {}},
                        walls={"flip": 601.0, "callWall": 605.0, "putWall": 595.0}, coverage=1.0,
                        spot=602.0, asof="x", cadence_sec=120, session_date="d", root="SPY")
    full = append_stamp(full, stamp="0941", time_step="09:41", net_by_strike={600.0: 2000.0},
                        greek_by_strike=None, walls=None, coverage=None,   # greek path failed
                        spot=603.0, asof="y", cadence_sec=120, session_date="d", root="SPY")
    validate_frame_dims(full)
    gi = full["price_levels"].index(600.0)
    assert full["grids"][METRIC_GEX][gi] == [5000000.0, 0.0]   # prior kept, new col 0.0
    assert full["grids"][METRIC_NETPREM][gi] == [1000.0, 2000.0]  # netprem advanced
    assert full["walls_path"][1] is None                        # failed cycle → no walls


def test_netprem_only_frame_has_no_greek_keys():
    full = append_stamp(None, stamp="0931", time_step="09:31",
                        net_by_strike={600.0: 1000.0}, spot=602.0, asof="x",
                        cadence_sec=120, session_date="d", root="SPY")
    assert set(full["grids"]) == {METRIC_NETPREM}
    assert full["metrics"] == [METRIC_NETPREM]
    # Wave-1 frames must NOT carry walls_path/coverage_path (byte-compat with the old store).
    assert "walls_path" not in full
    assert "coverage_path" not in full
    # frame_for_stamp on a netprem-only frame has no walls/coverage either.
    snap = frame_for_stamp(full, "0931")
    assert "walls" not in snap
    assert "coverage" not in snap


# ── (g3) frame_for_stamp truncates greeks + surfaces per-stamp walls/coverage ────────

def test_frame_for_stamp_surfaces_walls_and_coverage():
    full = None
    for stamp, tstep, gv, flip, cov in [
        ("0931", "09:31", 5e6, 601.0, 0.5),
        ("0941", "09:41", 6e6, 602.0, 0.75),
        ("0951", "09:51", 7e6, 603.0, 1.0),
    ]:
        full = append_stamp(full, stamp=stamp, time_step=tstep,
                            net_by_strike={600.0: 1.0},
                            greek_by_strike={METRIC_GEX: {600.0: gv}, "dex": {}, "vanna": {}, "charm": {}},
                            walls={"flip": flip, "callWall": 610.0, "putWall": 590.0},
                            coverage=cov, spot=602.0, asof="x", cadence_sec=120,
                            session_date="d", root="SPY")
    mid = frame_for_stamp(full, "0941")
    # greek grid truncated to the realized window.
    assert mid["grids"][METRIC_GEX][0] == [5000000.0, 6000000.0]
    # walls + coverage are the mid stamp's OWN snapshot (point-in-time, not forward-filled).
    assert mid["walls"] == {"flip": 602.0, "callWall": 610.0, "putWall": 590.0}
    assert mid["coverage"] == {"greeks": 0.75}
    latest = frame_for_stamp(full, "0951")
    assert latest["walls"]["flip"] == 603.0
    assert latest["coverage"] == {"greeks": 1.0}


# ── (g4) extract_cycle_quotes: freshest NBBO per contract from the tape ──────────────

def test_extract_cycle_quotes_takes_freshest_nbbo():
    # Two fills for the same (exp,strike,right); the LATER trade_timestamp's NBBO wins.
    calls = pd.DataFrame([
        {"expiration": "2026-07-13", "strike": 600.0, "right": "C",
         "trade_timestamp": "2026-07-06T10:00:00", "bid": 5.0, "ask": 5.2},
        {"expiration": "2026-07-13", "strike": 600.0, "right": "C",
         "trade_timestamp": "2026-07-06T10:05:00", "bid": 6.0, "ask": 6.4},  # fresher
        {"expiration": "2026-07-13", "strike": 605.0, "right": "C",
         "trade_timestamp": "2026-07-06T10:03:00", "bid": 3.0, "ask": 3.2},
    ])
    puts = pd.DataFrame([
        {"expiration": "2026-07-13", "strike": 595.0, "right": "P",
         "trade_timestamp": "2026-07-06T10:02:00", "bid": 2.0, "ask": 2.2},
    ])
    q = extract_cycle_quotes(calls, puts, session_date="2026-07-06", near_dte_cap_days=90)
    by_key = {(d["strike"], d["right"]): d for d in q}
    # 600C mid = (6.0+6.4)/2 = 6.2 (the fresher fill), NOT 5.1.
    assert abs(by_key[(600.0, "C")]["mid"] - 6.2) < 1e-9
    assert abs(by_key[(605.0, "C")]["mid"] - 3.1) < 1e-9
    assert abs(by_key[(595.0, "P")]["mid"] - 2.1) < 1e-9
    # exp_years > 0 for all (7 days out from session).
    assert all(d["exp_years"] > 0 for d in q)


def test_extract_cycle_quotes_drops_bad_quotes_and_expired():
    tape = pd.DataFrame([
        # zero bid → dropped
        {"expiration": "2026-07-13", "strike": 600.0, "right": "C",
         "trade_timestamp": "2026-07-06T10:00:00", "bid": 0.0, "ask": 5.0},
        # expired (before session) → dropped
        {"expiration": "2026-07-01", "strike": 600.0, "right": "C",
         "trade_timestamp": "2026-07-06T10:00:00", "bid": 5.0, "ask": 5.2},
        # beyond the DTE cap → dropped
        {"expiration": "2027-07-13", "strike": 600.0, "right": "P",
         "trade_timestamp": "2026-07-06T10:00:00", "bid": 5.0, "ask": 5.2},
        # good
        {"expiration": "2026-07-13", "strike": 605.0, "right": "P",
         "trade_timestamp": "2026-07-06T10:00:00", "bid": 4.0, "ask": 4.2},
    ])
    q = extract_cycle_quotes(tape, None, session_date="2026-07-06", near_dte_cap_days=90)
    assert len(q) == 1
    assert q[0]["strike"] == 605.0 and q[0]["right"] == "P"


def test_extract_cycle_quotes_empty_inputs():
    assert extract_cycle_quotes(None, None, session_date="2026-07-06") == []
    assert extract_cycle_quotes(pd.DataFrame(), pd.DataFrame(), session_date="2026-07-06") == []


# ── (g5) oi_by_contract + greek_columns_for_stamp join ───────────────────────────────

def test_oi_by_contract_keys():
    oi_df = pd.DataFrame([
        {"expiration": "2026-07-13", "strike": 600.0, "right": "C", "open_interest": 1500},
        {"expiration": "2026-07-13", "strike": 600.0, "right": "P", "open_interest": 2200},
    ])
    m = oi_by_contract(oi_df)
    assert m[("2026-07-13", 600.0, "C")] == 1500.0
    assert m[("2026-07-13", 600.0, "P")] == 2200.0
    assert oi_by_contract(None) == {}
    assert oi_by_contract(pd.DataFrame()) == {}


def test_greek_columns_for_stamp_joins_and_covers():
    quotes, oi_map = _bs_chain_quotes()
    out = greek_columns_for_stamp(quotes, oi_map=oi_map, spot=600.0)
    assert set(out["by_strike"]) == set(GREEK_METRICS)
    assert out["coverage"] == 1.0                       # every quoted strike had OI
    assert set(out["walls"]) == {"flip", "callWall", "putWall"}
    assert out["walls"]["callWall"] is not None and out["walls"]["callWall"] > 600.0
    assert out["walls"]["putWall"] is not None and out["walls"]["putWall"] < 600.0
    # A quote with no OI match contributes nothing → coverage drops below 1.
    quotes2 = quotes + [{"exp_str": "2026-07-13", "exp_years": 7 / 365.0,
                         "strike": 650.0, "right": "C", "mid": 0.5}]  # no OI for 650
    out2 = greek_columns_for_stamp(quotes2, oi_map=oi_map, spot=600.0)
    assert out2["coverage"] < 1.0
    assert 650.0 not in out2["by_strike"][METRIC_GEX] or out2["by_strike"][METRIC_GEX].get(650.0, 0.0) == 0.0


def test_greek_columns_empty_when_no_quotes():
    out = greek_columns_for_stamp([], oi_map={}, spot=600.0)
    assert out["coverage"] == 0.0
    assert all(out["by_strike"][m] == {} for m in GREEK_METRICS)
    assert out["walls"] == {"flip": None, "callWall": None, "putWall": None}


# ── (g6) POLLER FENCE — a greek failure must not break the netprem write ─────────────

def test_greek_failure_does_not_break_netprem(tmp_path, monkeypatch):
    import lib.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)

    # Force the greek path to raise by monkeypatching greek_columns_for_stamp to blow up.
    import scripts.build_flow_surface as bfs

    def _boom(*a, **k):
        raise RuntimeError("synthetic greek failure")

    monkeypatch.setattr(bfs, "greek_columns_for_stamp", _boom)

    rstk = {"SPY": _mk_strikes(s600=(1_000_000.0, 400_000.0))}
    quotes = {"SPY": [{"exp_str": "2026-07-13", "exp_years": 7 / 365.0,
                       "strike": 600.0, "right": "C", "mid": 5.0}]}
    paths = bfs.build_and_stage_surfaces(
        root_strikes_by_root=rstk, roots=["SPY"], session_date="2026-07-06",
        asof="2026-07-06T13:51:00Z", cadence_sec=120, spot_by_root={"SPY": 602.0},
        quotes_by_root=quotes, oi_by_root={"SPY": {("2026-07-13", 600.0, "C"): 1000.0}},
    )
    # Despite the greek explosion, the netprem frame is still written (fence held).
    snap_local = next(p for p, k in paths if k != "live_flow/surface/SPY/idx.json")
    snap = json.loads(snap_local.read_text())
    assert is_surface_frame(snap)
    assert snap["grids"]["netprem"][0] == [600000.0]     # netprem survived
    # No greek grids (they failed) — netprem-only frame.
    assert set(snap["grids"]) == {METRIC_NETPREM}


# ── (g7) end-to-end: build_and_stage_surfaces with quotes → greek grids on disk ──────

def test_build_and_stage_with_quotes_writes_greek_grids(tmp_path, monkeypatch):
    import lib.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)

    quotes, oi_map = _bs_chain_quotes(spot=600.0)
    rstk = {"SPY": _mk_strikes(s600=(1_000_000.0, 400_000.0), s605=(200_000.0, 900_000.0))}
    paths = build_and_stage_surfaces(
        root_strikes_by_root=rstk, roots=["SPY"], session_date="2026-07-06",
        asof="2026-07-06T13:51:00Z", cadence_sec=120, spot_by_root={"SPY": 600.0},
        quotes_by_root={"SPY": quotes}, oi_by_root={"SPY": oi_map},
    )
    legacy_snap_key = _legacy_stamp_keys({k for _, k in paths})[0]
    snap_local = next(p for p, k in paths if k == legacy_snap_key)
    snap = json.loads(snap_local.read_text())
    assert is_surface_frame(snap)
    # Greek grids present + validated dims (levels×steps), alongside netprem.
    assert set(GREEK_METRICS).issubset(set(snap["grids"]))
    validate_frame_dims(snap)
    # Walls + coverage surfaced on the per-stamp snapshot.
    assert set(snap.get("walls", {})) >= {"flip", "callWall", "putWall"}
    cov = (snap.get("coverage") or {}).get("greeks")
    assert isinstance(cov, (int, float)) and 0.0 <= cov <= 1.0


# ══ (g) date-keyed retention — M-XP(a) ══════════════════════════════════════════════
# The Terminal's multi-day replay (OEU lane T-B) reads:
#   live_flow/surface/{ROOT}/dates.json          → which sessions can be replayed
#   live_flow/surface/{ROOT}/{DATE}/idx.json     → that session's stamps
#   live_flow/surface/{ROOT}/{DATE}/{HHMM}.json  → that session's frames
# while the LIVE pane keeps reading the legacy today-paths. Both must hold every cycle.


class _FakeS3:
    """Minimal in-memory S3/R2 double: list_objects_v2 (Prefix + Delimiter) + delete_objects.

    Faithful to the two behaviors prune_surface_dates depends on: Delimiter="/" returns child
    prefixes in CommonPrefixes (not Contents), and delete_objects takes {"Objects":[{"Key"}]}.
    """

    def __init__(self, keys):
        self.keys = set(keys)
        self.deleted: list[str] = []
        self.list_calls = 0

    def list_objects_v2(self, **kw):
        self.list_calls += 1
        prefix = kw.get("Prefix", "")
        delim = kw.get("Delimiter")
        contents, common = [], set()
        for k in sorted(self.keys):
            if not k.startswith(prefix):
                continue
            rest = k[len(prefix):]
            if delim and delim in rest:
                common.add(prefix + rest.split(delim, 1)[0] + delim)
            else:
                contents.append({"Key": k})
        out = {"Contents": contents, "IsTruncated": False}
        if delim:
            out["CommonPrefixes"] = [{"Prefix": p} for p in sorted(common)]
        return out

    def delete_objects(self, Bucket=None, Delete=None):  # noqa: N803 — boto3 kwarg casing
        for o in (Delete or {}).get("Objects", []):
            self.keys.discard(o["Key"])
            self.deleted.append(o["Key"])
        return {"Deleted": [{"Key": o["Key"]} for o in (Delete or {}).get("Objects", [])]}


class _BoomS3:
    """An S3 double whose every call raises — the fail-soft contract's adversary."""

    def list_objects_v2(self, **kw):
        raise RuntimeError("R2 unreachable")

    def delete_objects(self, **kw):
        raise RuntimeError("R2 unreachable")


def _store_keys(root="SPY", dates=(), stamps=("0931", "0941"), legacy=True):
    """Build a realistic surface store key set: legacy today-paths + dated session prefixes."""
    base = f"{R2_SURFACE_PREFIX}{root}/"
    keys = set()
    if legacy:
        keys.add(base + "idx.json")
        keys.add(base + "dates.json")
        keys.update(base + f"{s}.json" for s in stamps)
    for d in dates:
        keys.add(f"{base}{d}/idx.json")
        keys.update(f"{base}{d}/{s}.json" for s in stamps)
    return keys


# ── (g1) dated copies are emitted ALONGSIDE the legacy today-paths ──────────────────

def test_dated_layout_written_alongside_legacy(tmp_path, monkeypatch):
    import lib.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)
    from datetime import datetime, timezone

    t = datetime(2026, 7, 6, 13, 31, tzinfo=timezone.utc)   # 09:31 ET
    paths = build_and_stage_surfaces(
        root_strikes_by_root={"SPY": _mk_strikes(s600=(1_000.0, 400.0))},
        roots=["SPY"], session_date="2026-07-06", asof="2026-07-06T13:31:00Z",
        cadence_sec=120, now=t,
    )
    keys = {k for _, k in paths}
    # Legacy today-paths — unchanged, still written (transition safety).
    assert "live_flow/surface/SPY/idx.json" in keys
    assert "live_flow/surface/SPY/0931.json" in keys
    # Date-keyed copies + the sessions index.
    assert "live_flow/surface/SPY/2026-07-06/idx.json" in keys
    assert "live_flow/surface/SPY/2026-07-06/0931.json" in keys
    assert "live_flow/surface/SPY/dates.json" in keys

    # The dated copies are the SAME local file as the legacy ones — one write, two keys, so
    # the live path and the replay path can never disagree byte-for-byte.
    by_key = {k: p for p, k in paths}
    assert by_key["live_flow/surface/SPY/idx.json"] == by_key["live_flow/surface/SPY/2026-07-06/idx.json"]
    assert by_key["live_flow/surface/SPY/0931.json"] == by_key["live_flow/surface/SPY/2026-07-06/0931.json"]
    # …and that shared file still validates as a SurfaceIndex / SurfaceFrame.
    assert is_surface_index(json.loads(by_key["live_flow/surface/SPY/idx.json"].read_text()))
    assert is_surface_frame(json.loads(by_key["live_flow/surface/SPY/0931.json"].read_text()))


# ── (g2) dates.json shape ───────────────────────────────────────────────────────────

def test_dates_json_shape_from_staging(tmp_path, monkeypatch):
    import lib.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)

    paths = build_and_stage_surfaces(
        root_strikes_by_root={"QQQ": _mk_strikes(s500=(9_000.0, 1_000.0))},
        roots=["QQQ"], session_date="2026-07-06", asof="2026-07-06T13:31:00Z",
        cadence_sec=300,
    )
    dates_local = next(p for p, k in paths if k.endswith("/dates.json"))
    doc = json.loads(dates_local.read_text())
    assert is_surface_dates(doc)
    assert doc["root"] == "QQQ"
    assert doc["dates"] == ["2026-07-06"]
    assert doc["latest"] == "2026-07-06"
    assert doc["count"] == 1
    assert doc["retain"] == SURFACE_RETAIN_SESSIONS
    # Cadence honesty: carried verbatim from the true write interval, same law as idx.json.
    assert doc["cadenceSec"] == 300 and doc["cadence"] == "5-min"
    assert doc["asof"] == "2026-07-06T13:31:00Z"
    assert doc["source"] == "poller"


def test_dates_index_newest_first_deduped_trimmed_and_junk_dropped():
    doc = build_dates_index(
        ["2026-07-01", "2026-07-03", "2026-07-02", "2026-07-03", "", None, "07/04/2026",
         "2026-07-0", "latest"],
        root="SPY", cadence_sec=120, asof="a", retain=2,
    )
    assert doc["dates"] == ["2026-07-03", "2026-07-02"]   # newest first, deduped, trimmed
    assert doc["latest"] == "2026-07-03"
    assert doc["count"] == 2
    assert is_surface_dates(doc)


def test_dates_index_empty_latest_is_null():
    doc = build_dates_index([], root="SPY", cadence_sec=120, asof="")
    assert doc["dates"] == [] and doc["latest"] is None and doc["count"] == 0
    assert is_surface_dates(doc)


def test_is_surface_dates_rejects_bad_docs():
    good = build_dates_index(["2026-07-02", "2026-07-01"], root="SPY", cadence_sec=120, asof="")
    assert is_surface_dates(good)
    assert not is_surface_dates({**good, "dates": ["2026-07-01", "2026-07-02"]})  # oldest first
    assert not is_surface_dates({**good, "latest": "2026-07-01"})                 # ≠ dates[0]
    assert not is_surface_dates({**good, "dates": ["not-a-date"]})
    assert not is_surface_dates({**good, "cadenceSec": "120"})
    assert not is_surface_dates({**good, "root": None})
    assert not is_surface_dates([])
    assert is_session_date("2026-07-06") and not is_session_date("2026-7-6")


def test_dated_surface_keys_rejects_malformed_date():
    idx_key, frame_key = dated_surface_keys("spy", "2026-07-06", "0931")
    assert idx_key == "live_flow/surface/SPY/2026-07-06/idx.json"
    assert frame_key == "live_flow/surface/SPY/2026-07-06/0931.json"
    # A junk date must never create a prefix the retention prune cannot recognize.
    for bad in ("2026-7-6", "20260706", "", "today"):
        try:
            dated_surface_keys("SPY", bad, "0931")
        except ValueError:
            continue
        raise AssertionError(f"dated_surface_keys accepted malformed date {bad!r}")


# ── (g3) sessions accumulate across a rollover; legacy always tracks TODAY ───────────

def test_second_session_accumulates_dates_and_rolls_legacy(tmp_path, monkeypatch):
    import lib.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)
    from datetime import datetime, timezone

    build_and_stage_surfaces(
        root_strikes_by_root={"SPY": _mk_strikes(s600=(1_000.0, 0.0))},
        roots=["SPY"], session_date="2026-07-06", asof="d1", cadence_sec=120,
        now=datetime(2026, 7, 6, 19, 55, tzinfo=timezone.utc),   # 15:55 ET
    )
    paths2 = build_and_stage_surfaces(
        root_strikes_by_root={"SPY": _mk_strikes(s600=(7_000.0, 0.0))},
        roots=["SPY"], session_date="2026-07-07", asof="d2", cadence_sec=120,
        now=datetime(2026, 7, 7, 13, 31, tzinfo=timezone.utc),   # 09:31 ET
    )
    keys = {k for _, k in paths2}
    # Day 2 writes ITS dated prefix; day 1's stays untouched on the store.
    assert "live_flow/surface/SPY/2026-07-07/0931.json" in keys
    assert "live_flow/surface/SPY/2026-07-06/1555.json" not in keys
    # dates.json now lists both sessions, newest first.
    dates_local = next(p for p, k in paths2 if k.endswith("/dates.json"))
    doc = json.loads(dates_local.read_text())
    assert doc["dates"] == ["2026-07-07", "2026-07-06"]
    assert doc["latest"] == "2026-07-07"
    assert is_surface_dates(doc)
    # Session-rollover guard still holds: the legacy idx is day 2's only (no carry-over of
    # day 1's stamps), so the live Terminal never replays yesterday as today.
    idx = json.loads(next(p for p, k in paths2 if k == "live_flow/surface/SPY/idx.json").read_text())
    assert idx["date"] == "2026-07-07" and idx["stamps"] == ["0931"]


# ── (g4) retention prune ────────────────────────────────────────────────────────────

def test_prune_keeps_newest_n_and_deletes_older():
    dates = [f"2026-07-{d:02d}" for d in range(1, 13)]      # 12 sessions
    s3 = _FakeS3(_store_keys(dates=dates))
    res = prune_surface_dates(s3, "bkt", "SPY", keep=10)
    assert res["ok"] is True
    assert res["retained"] == sorted(dates, reverse=True)[:10]
    assert sorted(res["deleted_dates"]) == ["2026-07-01", "2026-07-02"]
    assert res["deleted_objects"] == 6                       # 2 sessions × (idx + 2 stamps)
    # The two oldest prefixes are gone from the store; the newest 10 survive intact.
    assert not any("/2026-07-01/" in k or "/2026-07-02/" in k for k in s3.keys)
    assert f"{R2_SURFACE_PREFIX}SPY/2026-07-03/idx.json" in s3.keys
    assert f"{R2_SURFACE_PREFIX}SPY/2026-07-12/0941.json" in s3.keys


def test_prune_never_touches_legacy_today_paths():
    # The single most dangerous failure mode: a retention sweep blanking the live pane.
    dates = [f"2026-07-{d:02d}" for d in range(1, 13)]
    s3 = _FakeS3(_store_keys(dates=dates))
    res = prune_surface_dates(s3, "bkt", "SPY", keep=1)
    assert res["ok"] is True and len(res["deleted_dates"]) == 11
    for legacy in ("idx.json", "dates.json", "0931.json", "0941.json"):
        assert f"{R2_SURFACE_PREFIX}SPY/{legacy}" in s3.keys
    # Every deleted key sat under a {ROOT}/{YYYY-MM-DD}/ prefix — nothing at the root of
    # {ROOT}/ (where the live today-paths live) was ever a delete candidate.
    assert s3.deleted and all(
        is_session_date(k[len(f"{R2_SURFACE_PREFIX}SPY/"):].split("/")[0])
        for k in s3.deleted
    )


def test_prune_noop_when_nothing_to_delete():
    s3 = _FakeS3(_store_keys(dates=["2026-07-05", "2026-07-06"]))
    res = prune_surface_dates(s3, "bkt", "SPY", keep=10)
    assert res["ok"] is True
    assert res["deleted_dates"] == [] and res["deleted_objects"] == 0
    assert s3.deleted == []


def test_prune_is_fail_soft_on_r2_error():
    res = prune_surface_dates(_BoomS3(), "bkt", "SPY", keep=10)
    assert res["ok"] is False              # caller retries next session
    assert res["deleted_dates"] == [] and res["deleted_objects"] == 0


def test_prune_honors_per_key_delete_errors():
    """R2 reports a refused delete in the response BODY, never as an exception.

    Counting the batch length regardless fabricated the deleted count and left retention
    BELIEVED-enforced while the objects survived — retention has to be measured, not assumed.
    Twin of tests/test_flow_archive.py::test_prune_honors_per_key_delete_errors.
    """
    dates = [f"2026-07-{d:02d}" for d in range(1, 13)]      # 12 sessions, keep 10
    s3 = _FakeS3(_store_keys(dates=dates))
    refused = f"{R2_SURFACE_PREFIX}SPY/2026-07-01/0941.json"
    real_delete = s3.delete_objects

    def partial(Bucket=None, Delete=None):  # noqa: N803 — boto3 kwarg casing
        objs = (Delete or {}).get("Objects", [])
        kept = [o for o in objs if o["Key"] != refused]
        real_delete(Bucket=Bucket, Delete={"Objects": kept})
        errors = [{"Key": refused, "Code": "AccessDenied", "Message": "nope"}
                  for o in objs if o["Key"] == refused]
        return {"Deleted": [{"Key": o["Key"]} for o in kept], "Errors": errors}

    s3.delete_objects = partial
    res = prune_surface_dates(s3, "bkt", "SPY", keep=10)

    assert res["ok"] is False                 # retention is NOT verified this session
    # 2 stale sessions × 3 objects = 6, minus the one R2 refused.
    assert res["deleted_objects"] == 5
    # The date that did not fully delete is NOT claimed as deleted…
    assert res["deleted_dates"] == ["2026-07-02"]
    assert "2026-07-01" not in res["deleted_dates"]
    # …and the refused object really did survive, while its siblings went.
    assert refused in s3.keys
    assert f"{R2_SURFACE_PREFIX}SPY/2026-07-01/0931.json" not in s3.keys
    assert not any("/2026-07-02/" in k for k in s3.keys)
    # The live today-paths are untouched, as always.
    for legacy in ("idx.json", "dates.json", "0931.json"):
        assert f"{R2_SURFACE_PREFIX}SPY/{legacy}" in s3.keys


def test_list_session_dates_ignores_legacy_and_junk_prefixes():
    s3 = _FakeS3(
        _store_keys(dates=["2026-07-05", "2026-07-06"])
        | {f"{R2_SURFACE_PREFIX}SPY/notadate/idx.json",
           f"{R2_SURFACE_PREFIX}QQQ/2026-07-06/idx.json"}    # a different root
    )
    assert list_surface_session_dates(s3, "bkt", "SPY") == ["2026-07-06", "2026-07-05"]
    assert list_surface_session_dates(s3, "bkt", "QQQ") == ["2026-07-06"]
    assert list_surface_session_dates(_BoomS3(), "bkt", "SPY") == []


# ── (g5) ledger self-heal + fencing ─────────────────────────────────────────────────

def test_merge_surface_dates_heals_ledger_from_r2_truth(tmp_path, monkeypatch):
    # Staging-dir wipe (droplet redeploy): the local ledger knows only today, while R2 still
    # holds 3 sessions. Merging R2 truth back must republish the full list.
    import lib.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)

    build_and_stage_surfaces(
        root_strikes_by_root={"SPY": _mk_strikes(s600=(1_000.0, 0.0))},
        roots=["SPY"], session_date="2026-07-06", asof="a", cadence_sec=120,
    )
    dates_file = tmp_path / "live_flow_out" / "surface" / "SPY" / "dates.json"
    assert json.loads(dates_file.read_text())["dates"] == ["2026-07-06"]

    retained = merge_surface_dates(
        "SPY", ["2026-07-06", "2026-07-05", "2026-07-02"],
        cadence_sec=120, asof="a", retain=10)
    assert retained == ["2026-07-06", "2026-07-05", "2026-07-02"]
    doc = json.loads(dates_file.read_text())
    assert doc["dates"] == ["2026-07-06", "2026-07-05", "2026-07-02"]
    assert is_surface_dates(doc)


# ── (g6) OEU bug-wave F3-04 — the healed ledger must be PUT in the same cycle ────────
# live_flow_poller.py's retention sweep does exactly this sequence: prune_surface_dates
# (R2 truth) -> merge_surface_dates (heal the local ledger) -> upload the healed file.
# Before the fix, step 3 was deferred to "the next cycle's surface upload", which never
# arrives for a --once / --rth-only run (the plist's own documented cold-start recipe) —
# leaving the pre-heal, truncated dates.json as the live R2 object indefinitely.

def test_healed_ledger_lands_at_the_exact_path_the_poller_uploads(tmp_path, monkeypatch):
    """The path the poller's retention sweep now uploads (`_surface_out_dir(root) /
    SURFACE_DATES_NAME`) must be exactly the file merge_surface_dates just healed —
    not a stale copy, not a different root's file."""
    from scripts.build_flow_surface import _surface_out_dir, SURFACE_DATES_NAME
    import lib.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)

    # Cold staging dir: only today's session is known locally (a fresh worktree/droplet).
    build_and_stage_surfaces(
        root_strikes_by_root={"SPY": _mk_strikes(s600=(1_000.0, 0.0))},
        roots=["SPY"], session_date="2026-07-06", asof="a", cadence_sec=120,
    )

    # Simulate the poller's retention block: R2 truth has 3 retained sessions.
    s3 = _FakeS3(_store_keys(dates=["2026-07-02", "2026-07-05", "2026-07-06"]))
    res = prune_surface_dates(s3, "bkt", "SPY", keep=10)
    assert res["ok"] and res["retained"] == ["2026-07-06", "2026-07-05", "2026-07-02"]
    merge_surface_dates("SPY", res["retained"], cadence_sec=120, asof="a", retain=10)

    healed_path = _surface_out_dir("SPY") / SURFACE_DATES_NAME
    assert healed_path.exists()
    doc = json.loads(healed_path.read_text())
    # The exact defect: without the heal-and-upload, this file (and the one that would
    # have shipped to R2) would still read ["2026-07-06"] only.
    assert doc["dates"] == ["2026-07-06", "2026-07-05", "2026-07-02"]


def test_poller_retention_sweep_imports_the_heal_upload_dependencies():
    """Regression guard for the fix itself (#F3-04): live_flow_poller.py's retention
    block imports _surface_out_dir/SURFACE_DATES_NAME/R2_SURFACE_PREFIX from
    build_flow_surface and calls _upload_r2 on the healed path — verified against the
    module SOURCE (the block runs deep inside main()'s live loop, which needs a
    network-backed harness this repo does not have; the import + call-site check is the
    proportionate regression guard for a fix that is otherwise a one-line typo away from
    silently no-op'ing)."""
    import inspect
    import scripts.live_flow_poller as poller

    # The names themselves must be real, importable attributes of build_flow_surface —
    # a typo here would raise ImportError the moment the retention block executes.
    import scripts.build_flow_surface as bfs
    for name in ("_surface_out_dir", "SURFACE_DATES_NAME", "R2_SURFACE_PREFIX",
                 "merge_surface_dates", "prune_surface_dates"):
        assert hasattr(bfs, name), f"build_flow_surface has no {name} — poller import would fail"

    src = inspect.getsource(poller)
    start = src.index("M-XP(a): Flow-Surface retention sweep")
    end = src.index("FC-R8:", start)
    block = src[start:end]
    assert "_surface_out_dir" in block
    assert "SURFACE_DATES_NAME" in block
    assert "_upload_r2(s3, bucket, healed_path" in block


def test_dated_layout_failure_keeps_legacy_paths(tmp_path, monkeypatch):
    # Fencing contract: a blow-up anywhere in the dated layout degrades to today-only
    # (pre-M-XP behavior) and must never cost a root its legacy upload.
    import lib.config as cfg_mod
    import scripts.build_flow_surface as bfs
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)

    def _boom(*a, **kw):
        raise RuntimeError("dated layout exploded")

    monkeypatch.setattr(bfs, "dated_surface_keys", _boom)
    paths = bfs.build_and_stage_surfaces(
        root_strikes_by_root={"SPY": _mk_strikes(s600=(1_000.0, 400.0))},
        roots=["SPY"], session_date="2026-07-06", asof="a", cadence_sec=120,
    )
    keys = {k for _, k in paths}
    assert "live_flow/surface/SPY/idx.json" in keys
    assert len(_legacy_stamp_keys(keys)) == 1
    assert not any("2026-07-06/" in k for k in keys)   # no dated keys emitted
    # The legacy files are on disk and still valid.
    idx_local = next(p for p, k in paths if k == "live_flow/surface/SPY/idx.json")
    assert is_surface_index(json.loads(idx_local.read_text()))


def test_bad_session_date_degrades_to_legacy_only(tmp_path, monkeypatch):
    # A malformed session_date must not create an unprunable junk prefix — the dated layout
    # is simply skipped and the legacy paths still ship.
    import lib.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)

    paths = build_and_stage_surfaces(
        root_strikes_by_root={"SPY": _mk_strikes(s600=(1_000.0, 400.0))},
        roots=["SPY"], session_date="07/06/2026", asof="a", cadence_sec=120,
    )
    keys = {k for _, k in paths}
    assert "live_flow/surface/SPY/idx.json" in keys
    assert len(_legacy_stamp_keys(keys)) == 1
    assert not any(k.endswith("/dates.json") for k in keys)
    assert all(k.count("/") == 3 for k in keys)        # nothing nested under a junk prefix


def test_retain_sessions_override_trims_dates_index(tmp_path, monkeypatch):
    import lib.config as cfg_mod
    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)
    from datetime import datetime, timezone

    for day in (4, 5, 6):
        build_and_stage_surfaces(
            root_strikes_by_root={"SPY": _mk_strikes(s600=(1_000.0, 0.0))},
            roots=["SPY"], session_date=f"2026-07-{day:02d}", asof="a", cadence_sec=120,
            now=datetime(2026, 7, day, 13, 31, tzinfo=timezone.utc),
            retain_sessions=2,
        )
    doc = json.loads((tmp_path / "live_flow_out" / "surface" / "SPY" / "dates.json").read_text())
    assert doc["dates"] == ["2026-07-06", "2026-07-05"]   # oldest dropped at the cap
    assert doc["retain"] == 2 and doc["latest"] == "2026-07-06"
