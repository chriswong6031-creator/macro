"""Tests for engine.cycle_forward_log — the W0.2 shared forward-log writer.

Four acceptance criteria (per masterplan W0.2 spec):

  (a) keep-FIRST invariant: two consecutive appends for the same (date, series_id)
      preserve the FIRST row — the second write is silently dropped.
  (b) cone-edge ordering: proj_lo <= proj_central <= proj_hi when all three are
      present (for months that have a projection band).
  (c) writer is never-raise on empty / missing proj: degenerate inputs (no proj,
      empty data, missing asOf) all return 0 without raising.
  (d) proj_lo / proj_hi are populated when _project_next produces low/high keys
      (i.e. the cone-edge data hole N-D2-1 is closed).

Note: I/O-bound tests (a) patch `lib.config.data_dir` via pytest monkeypatch so
the module registry is never permanently polluted (avoids cross-test contamination).
"""
from __future__ import annotations

import pandas as pd
import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _fake_data(asof="2026-07-01", with_proj=True, proj_lo=None, proj_hi=None,
               proj_central=None) -> dict:
    """Minimal compute()-shaped dict with one sector + one basket."""
    def _sector(sid, proj=True):
        pr: dict = {}
        if proj:
            pr = {
                "nextTurn": "peak",
                "central": proj_central or "2027-03",
                "low": proj_lo or "2026-11",
                "high": proj_hi or "2027-07",
            }
        return {
            "id": sid, "kind": "sector", "name": sid.upper(),
            "now": {
                "phase": "Expansion", "pos": 55.0, "osc_slope": 1.2,
                "signal": None, "timing_state": "TRENDING",
                "above200d": True, "rs_63d": 3.5,
            },
            "proj": pr,
        }

    return {
        "meta": {"asOf": asof, "region": "us"},
        "sectors": [_sector("xlk", proj=with_proj), _sector("xlf", proj=False)],
        "baskets": [_sector("b-mag7", proj=with_proj)],
    }


# ── (a) keep-FIRST invariant ─────────────────────────────────────────────────

def test_keep_first_invariant(tmp_path, monkeypatch):
    """Two appends on the same date must leave only the FIRST row per (date, id)."""
    import engine.cycle_forward_log as clf
    import lib.config as config_mod

    # Patch only the data_dir function — does not inject fake modules into sys.modules
    monkeypatch.setattr(config_mod, "data_dir", lambda: tmp_path)

    # first append
    data1 = _fake_data(asof="2026-07-01", proj_central="2027-03")
    n1 = clf._append(data1, "sector_cycles")
    assert n1 == 3, f"expected 3 rows (2 sectors + 1 basket), got {n1}"

    # second append — same date, different proj_central value
    data2 = _fake_data(asof="2026-07-01", proj_central="2028-01")
    n2 = clf._append(data2, "sector_cycles")
    assert n2 == 3

    # read back and check keep-first
    p = tmp_path / "sector_cycles" / "forward_log.parquet"
    assert p.exists()
    df = pd.read_parquet(p)
    xlk_rows = df[df["id"] == "xlk"]
    assert len(xlk_rows) == 1, "keep-FIRST violated: duplicate (date, id) found"
    assert xlk_rows.iloc[0]["proj_central"] == "2027-03", (
        "keep-FIRST violated: second write's value replaced the first"
    )


# ── (b) cone-edge ordering ───────────────────────────────────────────────────

def test_cone_edge_ordering():
    """proj_lo <= proj_central <= proj_hi (as YYYY-MM strings they sort lexicographically)."""
    import engine.cycle_forward_log as clf

    data = _fake_data(asof="2026-07-01", proj_lo="2026-11", proj_central="2027-03",
                      proj_hi="2027-07")
    rows = clf._extract_rows(data)

    for r in rows:
        if r["proj_central"] is None:
            # xlf has no proj — skip
            continue
        lo = r["proj_lo"]
        cen = r["proj_central"]
        hi = r["proj_hi"]
        assert lo is not None and cen is not None and hi is not None, (
            f"cone edges missing on {r['id']}: lo={lo}, cen={cen}, hi={hi}"
        )
        assert lo <= cen, f"{r['id']}: proj_lo ({lo}) > proj_central ({cen})"
        assert cen <= hi, f"{r['id']}: proj_central ({cen}) > proj_hi ({hi})"


# ── (c) never-raise on empty / missing proj ──────────────────────────────────

def test_never_raise_on_empty_data():
    """append_forward_log returns 0 without raising on degenerate inputs.
    Tests the pure extraction + internal logic, not the parquet I/O path."""
    import engine.cycle_forward_log as clf

    # None data — _append guards against None at top
    assert clf._append(None, "sector_cycles") == 0

    # empty dict — no asOf → return 0
    assert clf._append({}, "sector_cycles") == 0

    # meta present but asOf missing
    assert clf._append({"meta": {}, "sectors": [], "baskets": []}, "sector_cycles") == 0

    # unknown engine — the public wrapper catches this before _append
    assert clf.append_forward_log(_fake_data(), "unknown_engine") == 0

    # data with sectors that have no proj at all — _extract_rows should still produce
    # rows, but with null proj cols.  Test via _extract_rows directly (no I/O).
    data_no_proj = _fake_data(with_proj=False)
    rows = clf._extract_rows(data_no_proj)
    assert len(rows) == 3, f"expected 3 rows, got {len(rows)}"
    # all proj cols should be None when no proj
    for r in rows:
        assert r["proj_lo"] is None, f"{r['id']}: proj_lo should be None"
        assert r["proj_hi"] is None, f"{r['id']}: proj_hi should be None"
        assert r["proj_central"] is None, f"{r['id']}: proj_central should be None"


# ── (d) proj_lo / proj_hi populated from _project_next output ────────────────

def test_proj_lo_hi_populated():
    """When the engine supplies low/high keys, they land in the log schema."""
    import engine.cycle_forward_log as clf

    data = _fake_data(asof="2026-07-01", proj_lo="2026-10", proj_central="2027-02",
                      proj_hi="2027-06")
    rows = clf._extract_rows(data)
    # xlk and b-mag7 have proj; xlf does not
    with_proj = [r for r in rows if r["proj_central"] is not None]
    assert len(with_proj) == 2, "expected 2 rows with projection (xlk + b-mag7)"
    for r in with_proj:
        assert r["proj_lo"] == "2026-10", f"{r['id']}: proj_lo wrong"
        assert r["proj_hi"] == "2027-06", f"{r['id']}: proj_hi wrong"

    no_proj = [r for r in rows if r["proj_central"] is None]
    assert len(no_proj) == 1
    assert no_proj[0]["proj_lo"] is None
    assert no_proj[0]["proj_hi"] is None


# ── China writer cone-edge columns ───────────────────────────────────────────

def test_china_writer_has_proj_lo_hi_keys():
    """The china_sector_cycles.append_forward_log dict building now includes proj_lo/proj_hi."""
    import pathlib

    src = pathlib.Path("/tmp/wave-w023/engine/china_sector_cycles.py").read_text()
    # parse and look for proj_lo and proj_hi in the rows.append(…) dict
    assert '"proj_lo"' in src or "'proj_lo'" in src, (
        "china_sector_cycles.py: proj_lo key missing from append_forward_log rows"
    )
    assert '"proj_hi"' in src or "'proj_hi'" in src, (
        "china_sector_cycles.py: proj_hi key missing from append_forward_log rows"
    )
