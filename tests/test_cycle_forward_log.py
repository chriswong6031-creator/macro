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


# ── flagship cycle payload (engine "cycle_ontology") ─────────────────────────

def _fake_cycle_payload(asof="2026-07-01") -> dict:
    """Minimal scripts.build_cycle.compute()-shaped payload: one MEASURED card
    (with proj + hazard + tripwires) and one FRAME-only card."""
    measured_band = {
        "band": "intermediate", "tier": "measured",
        "now": {
            "phase": "Peak", "pos": 74.0,
            "hazard": {
                "1m": {"p": 0.11, "source": "MODEL", "cell_verdict": "PASS"},
                "3m": {"p": 0.29, "source": "PRIOR", "cell_verdict": "PRIOR"},
                "6m": {"p": 0.48, "source": "PRIOR", "cell_verdict": "PRIOR"},
            },
        },
        "proj": {"nextTurn": "trough", "central": "2027-06", "low": "2026-12",
                 "high": "2028-06", "overdue": False, "overdue_frac": 0.62},
    }
    frame_band = {"band": "secular", "tier": "frame", "turns": [], "period": {}}
    return {
        "version": 1, "as_of": asof,
        "order": ["business", "gold"],
        "cycles": {
            "business": {
                "id": "business", "name": "US Business Cycle", "card_tier": "measured",
                "bands": [measured_band],
                "tripwires": [
                    {"id": "business.a.v1", "state": "ARMED", "claim": "ISM > 54"},
                    {"id": "business.b.v1", "state": "ARMED", "claim": "payrolls positive"},
                    {"id": "business.c.v1", "state": "FIRED", "claim": "UE > 4.5%"},
                    {"id": "business.d.v1", "state": "DATA_MISSING", "claim": "n/a"},
                ],
            },
            "gold": {
                "id": "gold", "name": "Gold", "card_tier": "frame",
                "bands": [frame_band], "tripwires": [],
            },
        },
    }


def test_cycle_rows_shape_and_counts():
    """One row per CARD; MEASURED carries the window + hazard, FRAME nulls them,
    and the ARMED/FIRED counts are stamped so the window is gradeable later."""
    import engine.cycle_forward_log as clf

    rows = clf._extract_cycle_rows(_fake_cycle_payload())
    assert [r["id"] for r in rows] == ["business", "gold"], "one row per card, in payload order"

    biz = rows[0]
    assert biz["date"] == "2026-07-01"
    assert biz["card_tier"] == "measured"
    assert biz["phase"] == "Peak" and biz["pos"] == 74.0
    assert biz["proj_next"] == "trough"
    assert (biz["proj_lo"], biz["proj_central"], biz["proj_hi"]) == ("2026-12", "2027-06", "2028-06")
    assert biz["proj_lo"] <= biz["proj_central"] <= biz["proj_hi"]
    assert biz["overdue"] is False and biz["overdue_frac"] == 0.62
    assert biz["hazard_1m_p"] == 0.11 and biz["hazard_1m_src"] == "MODEL"
    assert biz["hazard_3m_src"] == "PRIOR" and biz["hazard_6m_p"] == 0.48
    # counts ignore DATA_MISSING (and anything that is not ARMED / FIRED)
    assert biz["n_watching"] == 2, "two ARMED conditions"
    assert biz["n_crossed"] == 1, "one FIRED condition"

    # a FRAME-only card still stamps a row — a null never blocks accrual
    gold = rows[1]
    assert gold["card_tier"] == "frame"
    for k in ("phase", "pos", "proj_next", "proj_central", "proj_lo", "proj_hi",
              "hazard_1m_p", "hazard_1m_src"):
        assert gold[k] is None, f"FRAME card should null {k}"
    assert gold["n_watching"] == 0 and gold["n_crossed"] == 0


def test_cycle_engine_keep_first_and_path(tmp_path, monkeypatch):
    """The flagship stamp lands at data/cycle_ontology/forward_log.parquet and is
    keep-FIRST per (date, id) — a past day's published window is never rewritten."""
    import engine.cycle_forward_log as clf
    import lib.config as config_mod

    monkeypatch.setattr(config_mod, "data_dir", lambda: tmp_path)

    n1 = clf.append_forward_log(_fake_cycle_payload(asof="2026-07-01"), "cycle_ontology")
    assert n1 == 2, f"expected 2 card rows, got {n1}"

    # a second run the same day with a MOVED window must not overwrite the first stamp
    moved = _fake_cycle_payload(asof="2026-07-01")
    moved["cycles"]["business"]["bands"][0]["proj"]["central"] = "2029-01"
    assert clf.append_forward_log(moved, "cycle_ontology") == 2

    p = tmp_path / "cycle_ontology" / "forward_log.parquet"
    assert p.exists(), "ledger did not land at data/cycle_ontology/forward_log.parquet"
    df = pd.read_parquet(p)
    biz = df[df["id"] == "business"]
    assert len(biz) == 1, "keep-FIRST violated: duplicate (date, id)"
    assert biz.iloc[0]["proj_central"] == "2027-06", "keep-FIRST violated: window was rewritten"


def test_cycle_engine_never_raises_on_degenerate_payloads():
    """Empty / meta-less / order-less payloads return 0 rather than raising."""
    import engine.cycle_forward_log as clf

    assert clf._append(None, "cycle_ontology") == 0
    assert clf._append({}, "cycle_ontology") == 0                       # no as_of
    assert clf._append({"as_of": "2026-07-01", "cycles": {}}, "cycle_ontology") == 0
    # as_of missing but cards present → no stamp (the PIT key would be null)
    assert clf._append({"cycles": _fake_cycle_payload()["cycles"],
                        "order": ["business"]}, "cycle_ontology") == 0
    # order listing a card that is not in cycles must be skipped, not crash
    rows = clf._extract_cycle_rows({"as_of": "2026-07-01", "order": ["ghost"], "cycles": {}})
    assert rows == []


def test_build_cycle_wires_the_forward_log():
    """scripts/build_cycle.py must actually call the writer — a forward ledger that
    is never appended is the classic dead-wire defect."""
    import pathlib

    src = (pathlib.Path(__file__).resolve().parent.parent
           / "scripts" / "build_cycle.py").read_text(encoding="utf-8")
    assert "from engine.cycle_forward_log import append_forward_log" in src, (
        "build_cycle.py does not import append_forward_log"
    )
    assert 'append_forward_log(payload, "cycle_ontology")' in src, (
        "build_cycle.py does not stamp the flagship forward log"
    )


# ── China writer cone-edge columns ───────────────────────────────────────────

def test_china_writer_has_proj_lo_hi_keys():
    """The china_sector_cycles.append_forward_log dict building now includes proj_lo/proj_hi."""
    import pathlib

    src = (pathlib.Path(__file__).resolve().parent.parent / "engine" / "china_sector_cycles.py").read_text()
    # parse and look for proj_lo and proj_hi in the rows.append(…) dict
    assert '"proj_lo"' in src or "'proj_lo'" in src, (
        "china_sector_cycles.py: proj_lo key missing from append_forward_log rows"
    )
    assert '"proj_hi"' in src or "'proj_hi'" in src, (
        "china_sector_cycles.py: proj_hi key missing from append_forward_log rows"
    )
