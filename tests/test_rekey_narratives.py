"""Tests for the turn-epoch re-key migrator + epoch-aware narrative loading (W2.1).

Covers the wave's acceptance gates:

  A. turn_epoch primitive — determinism, basis prefix, float/dict equivalence, distinctness.
  B. rekey_series_legs — exact (same month), shifted (±months within tol), orphaned
     (no match), new (turn with no prior narrative); prev_key chain; collision → orphan.
  C. half-cycle-scaled tolerance — slow series widens, fast series stays near base.
  D. rekey_engine — refuses new_epoch == old_epoch; --dry-run writes nothing; writes the
     narratives.<epoch>.json + orphans file otherwise; idempotent (same inputs → identical).
  E. Epoch-aware loader — resolves legacy file with byte-identity to the pre-W2.1 flatten;
     resolves a written epoch file; the REKEY GUARD path (required epoch missing →
     stale_quarantined + empty map, never fatal).
  F. Byte-identity of CURRENT built narrative bindings across all three engines (the
     zero-behaviour-change proof).

No network; pure fixtures + the repo's committed data files (read-only).
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.cycle_ontology import turn_epoch, LEGACY_TR_EPOCH, DETECTOR_VERSION  # noqa: E402
from scripts import rekey_narratives as rk  # noqa: E402
from scripts import _narrative_epoch as ne  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# fixtures
# ─────────────────────────────────────────────────────────────────────────────
def _turns(specs):
    """specs: list of (kind, date, [provisional]) -> ontology-shaped turn dicts (xlk)."""
    out = []
    for spec in specs:
        kind, date = spec[0], spec[1]
        prov = spec[2] if len(spec) > 2 else False
        ym = date[:7]
        yr = int(date[:4]) + (int(date[5:7]) - 1) / 12.0
        out.append({"turn_id": f"xlk:{kind}:{ym}", "k": kind, "date": date, "t": ym,
                    "x": round(yr, 3), "provisional": prov})
    return out


# ─────────────────────────────────────────────────────────────────────────────
# A. turn_epoch
# ─────────────────────────────────────────────────────────────────────────────
def test_turn_epoch_deterministic():
    assert turn_epoch("close_tr", 14.0) == turn_epoch("close_tr", 14.0)


def test_turn_epoch_float_dict_equivalence():
    assert turn_epoch("close_tr", 14.0) == turn_epoch("close_tr", {"pct": 14.0})


def test_turn_epoch_basis_prefix():
    assert turn_epoch("close_tr", 14.0).startswith("tr_")
    assert turn_epoch("close_price", 14.0).startswith("price_")


def test_turn_epoch_distinct_on_change():
    tags = {
        turn_epoch("close_tr", 14.0),
        turn_epoch("close_price", 14.0),      # basis change
        turn_epoch("close_tr", 16.0),         # threshold change
        turn_epoch("close_tr", 14.0, detector_version=DETECTOR_VERSION + 1),  # detector change
    }
    assert len(tags) == 4


def test_turn_epoch_rejects_bad_params():
    with pytest.raises(TypeError):
        turn_epoch("close_tr", "not-a-number")  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────────────────
# B. rekey_series_legs — exact / shifted / orphaned / new
# ─────────────────────────────────────────────────────────────────────────────
def test_rekey_exact_same_month():
    old = {"2020-03-23": {"title": "COVID trough"}}
    new = _turns([("trough", "2020-03-30")])   # same YYYY-MM
    nl, orph, rep = rk.rekey_series_legs(old, new, series_id="xlk", tol_days=90)
    assert nl["2020-03-30"]["status"] == "exact"
    assert nl["2020-03-30"]["prev_key"] == "2020-03-23"
    assert not orph


def test_rekey_shifted_within_tolerance():
    old = {"2021-12-27": {"title": "Peak"}}
    new = _turns([("peak", "2022-01-04")])     # +8d, different month → shifted
    nl, orph, rep = rk.rekey_series_legs(old, new, series_id="xlk", tol_days=90)
    leg = nl["2022-01-04"]
    assert leg["status"] == "shifted"
    assert leg["rekey_shift_days"] == 8
    assert leg["prev_key"] == "2021-12-27"


def test_rekey_orphaned_no_match():
    old = {"2018-12-24": {"title": "Xmas low"}}
    new = _turns([("trough", "2020-03-23")])   # ~15 months away → orphaned
    nl, orph, rep = rk.rekey_series_legs(old, new, series_id="xlk", tol_days=60)
    assert "2018-12-24" in orph
    assert orph["2018-12-24"]["status"] == "orphaned"
    assert orph["2018-12-24"]["title"] == "Xmas low"     # retained verbatim
    # orphan is NEVER in the plotted legs map
    assert "2018-12-24" not in nl
    # ... except the new turn shows up as a fresh 'new' slot
    assert nl["2020-03-23"]["status"] == "new"


def test_rekey_new_turn_no_prior():
    old = {}
    new = _turns([("peak", "2023-10-27")])
    nl, orph, rep = rk.rekey_series_legs(old, new, series_id="xlk", tol_days=60)
    assert nl["2023-10-27"]["status"] == "new"
    assert nl["2023-10-27"]["prev_key"] is None


def test_rekey_provisional_turn_ignored():
    old = {"2024-06-01": {"title": "should orphan — matches only a provisional turn"}}
    new = _turns([("peak", "2024-06-01", True)])   # provisional → not a match target
    nl, orph, rep = rk.rekey_series_legs(old, new, series_id="xlk", tol_days=60)
    assert "2024-06-01" in orph
    assert not nl   # provisional turn is not emitted as a 'new' slot either


def test_rekey_collision_second_binding_orphaned():
    # two old legs both nearest to one new turn → first wins, second orphaned
    old = {"2020-03-10": {"title": "A"}, "2020-03-25": {"title": "B"}}
    new = _turns([("trough", "2020-03-18")])
    nl, orph, rep = rk.rekey_series_legs(old, new, series_id="xlk", tol_days=90)
    assert len(nl) == 1
    assert len(orph) == 1
    assert "collided" in list(orph.values())[0]["reason"]


def test_rekey_prev_key_chain_grows():
    old = {"2020-03-23": {"title": "t", "prev_key_chain": ["ancient-key"]}}
    new = _turns([("trough", "2020-03-30")])
    nl, orph, rep = rk.rekey_series_legs(old, new, series_id="xlk", tol_days=90)
    assert nl["2020-03-30"]["prev_key_chain"] == ["ancient-key", "2020-03-23"]


# ─────────────────────────────────────────────────────────────────────────────
# C. half-cycle-scaled tolerance
# ─────────────────────────────────────────────────────────────────────────────
def test_tolerance_fast_series_near_base():
    # ~6-month half-cycles → base tolerance
    fast = _turns([("trough", "2020-01-01"), ("peak", "2020-07-01"),
                   ("trough", "2021-01-01"), ("peak", "2021-07-01")])
    assert rk.half_cycle_tol_days(fast) == rk._BASE_TOL_DAYS


def test_tolerance_slow_series_widens():
    # multi-year half-cycles → widened tolerance, clamped to MAX
    slow = _turns([("trough", "2000-01-01"), ("peak", "2005-01-01"),
                   ("trough", "2010-01-01"), ("peak", "2015-01-01")])
    tol = rk.half_cycle_tol_days(slow)
    assert tol > rk._BASE_TOL_DAYS
    assert tol <= rk._MAX_TOL_DAYS


def test_tolerance_too_few_turns_falls_back():
    assert rk.half_cycle_tol_days(_turns([("trough", "2020-01-01")])) == rk._BASE_TOL_DAYS


# ─────────────────────────────────────────────────────────────────────────────
# D. rekey_engine — refusal, dry-run, write, idempotence
# ─────────────────────────────────────────────────────────────────────────────
def _fixture_engine(tmp_path, engine="sector_cycles"):
    """Stand up a minimal data/<dir>/ with a narratives.json + cycle_dna.json."""
    ddir = tmp_path / "data" / rk.ENGINES[engine]["dir"]
    ddir.mkdir(parents=True)
    doc = {"version": "fixture", "note": "test",
           "sectors": {"xlk": {"now": "x", "legs": {
               "2020-03-23": {"title": "COVID trough", "body": "low"},
               "2021-12-27": {"title": "Peak", "body": "top"},
               "2018-12-24": {"title": "ghost", "body": "vanishes"}}}},
           "baskets": {}}
    (ddir / "narratives.json").write_text(json.dumps(doc), encoding="utf-8")
    (ddir / "cycle_dna.json").write_text(json.dumps(doc), encoding="utf-8")
    return ddir


def _new_turns_map():
    return {"xlk": _turns([("trough", "2020-03-30"),   # exact
                           ("peak", "2022-01-04"),      # shifted from 2021-12-27
                           ("trough", "2023-10-27")])}  # new; 2018-12-24 orphans


def test_rekey_engine_refuses_same_epoch(tmp_path):
    _fixture_engine(tmp_path)
    with pytest.raises(ValueError, match="new_epoch == old_epoch"):
        rk.rekey_engine("sector_cycles", _new_turns_map(),
                        old_epoch="tr_v0", new_epoch="tr_v0", root=tmp_path)


def test_rekey_engine_dry_run_writes_nothing(tmp_path):
    ddir = _fixture_engine(tmp_path)
    res = rk.rekey_engine("sector_cycles", _new_turns_map(),
                          old_epoch="tr_v0", new_epoch="price_x1",
                          root=tmp_path, dry_run=True)
    assert res["wrote"] is False
    assert not (ddir / "narratives.price_x1.json").exists()
    # stats still computed
    assert res["narr_stats"]["exact"] == 1
    assert res["narr_stats"]["shifted"] == 1
    assert res["narr_stats"]["orphaned"] == 1
    assert res["narr_stats"]["new"] == 1


def test_rekey_engine_writes_epoch_and_orphans(tmp_path):
    ddir = _fixture_engine(tmp_path)
    res = rk.rekey_engine("sector_cycles", _new_turns_map(),
                          old_epoch="tr_v0", new_epoch="price_x1", root=tmp_path)
    assert res["wrote"] is True
    out = ddir / "narratives.price_x1.json"
    orph = ddir / "narratives.price_x1.orphans.json"
    assert out.exists() and orph.exists()
    doc = json.loads(out.read_text())
    assert doc["epoch"] == "price_x1"
    assert doc["prev_epoch"] == "tr_v0"
    legs = doc["sectors"]["xlk"]["legs"]
    assert legs["2020-03-30"]["status"] == "exact"
    assert legs["2022-01-04"]["status"] == "shifted"
    assert legs["2023-10-27"]["status"] == "new"
    # orphan retained, detached, never in plotted legs
    odoc = json.loads(orph.read_text())
    assert "2018-12-24" in odoc["sectors"]["xlk"]["legs"]
    assert "2018-12-24" not in legs


def test_rekey_dna_epoch_invariant_carried_verbatim(tmp_path):
    """cycle_dna.json is a per-series PROFILE (no turn legs) → carried verbatim, only the
    epoch stamp changes; no fabricated 'new' slots."""
    ddir = tmp_path / "data" / "sector_cycles"
    ddir.mkdir(parents=True)
    (ddir / "narratives.json").write_text(json.dumps(
        {"sectors": {"xlk": {"legs": {"2020-03-23": {"title": "t"}}}}, "baskets": {}}),
        encoding="utf-8")
    dna = {"sectors": {"xlk": {"summary": "Tech cycles on rates+capex",
                               "drivers": ["duration"], "median_cycle_months": 42}},
           "baskets": {}}
    (ddir / "cycle_dna.json").write_text(json.dumps(dna), encoding="utf-8")
    res = rk.rekey_engine("sector_cycles", _new_turns_map(),
                          old_epoch="tr_v0", new_epoch="price_x1", root=tmp_path)
    dna_out = json.loads((ddir / "cycle_dna.price_x1.json").read_text())
    assert dna_out["_rekey_stats"]["turn_keyed"] is False
    assert dna_out["sectors"]["xlk"]["summary"] == "Tech cycles on rates+capex"
    assert dna_out["sectors"]["xlk"]["median_cycle_months"] == 42
    assert res["dna_stats"]["new"] == 0   # nothing fabricated


def test_rekey_engine_idempotent(tmp_path):
    _fixture_engine(tmp_path)
    a = rk.rekey_engine("sector_cycles", _new_turns_map(),
                        old_epoch="tr_v0", new_epoch="price_x1", root=tmp_path)
    b = rk.rekey_engine("sector_cycles", _new_turns_map(),
                        old_epoch="tr_v0", new_epoch="price_x1", root=tmp_path)
    pa = Path(a["narratives_path"]).read_text()
    pb = Path(b["narratives_path"]).read_text()
    assert pa == pb   # byte-identical


# ─────────────────────────────────────────────────────────────────────────────
# E. Epoch-aware loader + REKEY GUARD
# ─────────────────────────────────────────────────────────────────────────────
def test_loader_falls_back_to_legacy(tmp_path):
    ddir = _fixture_engine(tmp_path)
    res = ne.resolve_narratives("sector_cycles", ddir, "narratives")
    assert res["epoch"] == LEGACY_TR_EPOCH        # legacy tagged tr_v0
    assert res["stale_quarantined"] is False
    assert "xlk" in res["map"]


def test_loader_resolves_written_epoch_file(tmp_path):
    ddir = _fixture_engine(tmp_path)
    # write the epoch file the loader will compute for sector_cycles
    epoch = ne.current_epoch("sector_cycles")
    (ddir / f"narratives.{epoch}.json").write_text(json.dumps(
        {"epoch": epoch, "sectors": {"xlk": {"legs": {"2020-03-30": {"status": "exact"}}}},
         "baskets": {}}), encoding="utf-8")
    res = ne.resolve_narratives("sector_cycles", ddir, "narratives")
    assert res["epoch"] == epoch
    assert res["source"].name == f"narratives.{epoch}.json"
    assert "xlk" in res["map"]


def test_rekey_guard_required_epoch_missing_quarantines(tmp_path):
    ddir = _fixture_engine(tmp_path)
    # demand an epoch whose file does NOT exist → guard fires, never fatal
    res = ne.resolve_narratives_required_epoch(
        "sector_cycles", ddir, "price_MISSING", "narratives")
    assert res["stale_quarantined"] is True
    assert res["map"] == {}
    assert res["source"] is None


def test_rekey_guard_required_epoch_present_loads(tmp_path):
    ddir = _fixture_engine(tmp_path)
    (ddir / "narratives.price_OK.json").write_text(json.dumps(
        {"epoch": "price_OK", "sectors": {"xlk": {"legs": {}}}, "baskets": {}}),
        encoding="utf-8")
    res = ne.resolve_narratives_required_epoch(
        "sector_cycles", ddir, "price_OK", "narratives")
    assert res["stale_quarantined"] is False
    assert "xlk" in res["map"]


def test_country_basket_prefix_preserved(tmp_path):
    ddir = tmp_path / "data" / "country_cycles"
    ddir.mkdir(parents=True)
    (ddir / "narratives.json").write_text(json.dumps(
        {"sectors": {"ewj": {"legs": {}}}, "baskets": {"efa": {"legs": {}}}}),
        encoding="utf-8")
    res = ne.resolve_narratives("country_cycles", ddir, "narratives")
    # country keeps baskets UN-prefixed (no "b-")
    assert "efa" in res["map"]
    assert "b-efa" not in res["map"]


# ─────────────────────────────────────────────────────────────────────────────
# F. Byte-identity of the CURRENT built narrative bindings (zero-behaviour-change)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("engine,ddir,prefix", [
    ("sector_cycles", "sector_cycles", "b-"),
    ("country_cycles", "country_cycles", ""),
    ("china_sector_cycles", "china_sector_cycles", "b-"),
])
@pytest.mark.parametrize("kind", ["narratives", "cycle_dna"])
def test_builds_byte_identical_to_legacy_flatten(engine, ddir, prefix, kind):
    """The epoch-aware loader returns EXACTLY what the pre-W2.1 loaders returned, on the
    committed data files (no flip has happened, so the legacy file resolves)."""
    f = ROOT / "data" / ddir / f"{kind}.json"
    if not f.exists():
        pytest.skip(f"{f} absent")
    doc = json.loads(f.read_text(encoding="utf-8"))
    # reproduce the exact pre-W2.1 flatten
    legacy = dict(doc.get("sectors", {}))
    for k, v in (doc.get("baskets", {}) or {}).items():
        legacy[prefix + k] = v
    got = ne.resolve_narratives(engine, ROOT / "data" / ddir, kind)["map"]
    assert json.dumps(got, sort_keys=True, ensure_ascii=False) == \
           json.dumps(legacy, sort_keys=True, ensure_ascii=False)
