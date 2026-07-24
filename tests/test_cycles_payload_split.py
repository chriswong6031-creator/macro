"""Tests for scripts/_cycles_payload.split_cycles_payload — the perf split that
peels the heavy per-entity arrays off the cycle-map payload into a lazy-hydrated
series chunk.

Invariants (per the cycles-perf masterplan §A):

  (a) lossless recombine: for every entity id, core_entity + series[id] == the
      original entity (the client does Object.assign(byId[id], series[id]));
  (b) sectors keep osc + turns in CORE (default sectors-osc first paint needs them);
      price is stripped from sectors too (price-mode only);
  (c) non-sectors families (baskets/nasdaq/russell) drop price + osc + turns to series;
  (d) fx + usd_record move from the sectors family into series (country currency card);
  (e) the input dict is NOT mutated (the full model still feeds the features json);
  (f) entities without heavy arrays pass through untouched (no empty series row);
  (g) meta / phases and non-family top-level keys are preserved verbatim in core.
"""
from __future__ import annotations

import copy

from scripts._cycles_payload import split_cycles_payload


# ── fixtures ─────────────────────────────────────────────────────────────────

def _price():
    return [{"x": 2020.0, "v": 100.0}, {"x": 2021.0, "v": 110.0}]


def _osc():
    return [{"x": 2020.0, "v": 40.0}, {"x": 2021.0, "v": 55.0}]


def _turns():
    return [{"x": 2020.5, "k": "trough", "osc": 20.0}]


def _fx():
    return {"pair": "USDJPY", "cycle_pos": 55.0}


def _usd_record():
    return {"now": {"pos_v2": 42.0}}


def _full_payload():
    """A compute()-shaped payload covering all four families + the country FX keys."""
    return {
        "meta": {"asOf": "2026-07-01", "today": 2026.5, "region": "us"},
        "phases": {"Peak": {}},
        "sectors": [
            {"id": "xlk", "name": "Tech", "now": {"pos": 60},
             "price": _price(), "osc": _osc(), "turns": _turns(),
             "fx": _fx(), "usd_record": _usd_record()},
            {"id": "xlv", "name": "Health", "now": {"pos": 30},
             "price": _price(), "osc": _osc(), "turns": _turns()},          # no fx/usd
        ],
        "baskets": [
            {"id": "b-ai", "name": "AI", "now": {"pos": 70},
             "price": _price(), "osc": _osc(), "turns": _turns()},
        ],
        "nasdaq": [
            {"id": "ndx-semis", "name": "Semis", "now": {"pos": 80},
             "price": _price(), "osc": _osc(), "turns": _turns()},
        ],
        "russell": [
            {"id": "rut-fin", "name": "Fin", "now": {"pos": 20},
             "price": _price(), "osc": _osc(), "turns": _turns()},
        ],
    }


# ── tests ────────────────────────────────────────────────────────────────────

def test_lossless_recombine_per_id():
    data = _full_payload()
    original = copy.deepcopy(data)
    core, series = split_cycles_payload(data)

    core_by_id = {}
    for fam in ("sectors", "baskets", "nasdaq", "russell"):
        for e in core[fam]:
            core_by_id[e["id"]] = e

    for fam in ("sectors", "baskets", "nasdaq", "russell"):
        for orig in original[fam]:
            eid = orig["id"]
            recombined = dict(core_by_id[eid])
            recombined.update(series.get(eid, {}))
            assert recombined == orig, f"recombine mismatch for {eid}"


def test_sectors_keep_osc_turns_in_core_but_not_price():
    core, series = split_cycles_payload(_full_payload())
    xlk_core = next(e for e in core["sectors"] if e["id"] == "xlk")
    assert "osc" in xlk_core and "turns" in xlk_core          # kept for default paint
    assert "price" not in xlk_core                            # price-mode only -> series
    assert "price" in series["xlk"]
    assert "osc" not in series["xlk"] and "turns" not in series["xlk"]


def test_non_sectors_drop_price_osc_turns_to_series():
    core, series = split_cycles_payload(_full_payload())
    for fam, eid in (("baskets", "b-ai"), ("nasdaq", "ndx-semis"), ("russell", "rut-fin")):
        ent = next(e for e in core[fam] if e["id"] == eid)
        assert "price" not in ent and "osc" not in ent and "turns" not in ent
        assert set(series[eid]) == {"price", "osc", "turns"}
        # non-heavy keys stay in core
        assert ent["name"] and ent["now"]


def test_fx_and_usd_record_move_from_sectors_to_series():
    core, series = split_cycles_payload(_full_payload())
    xlk_core = next(e for e in core["sectors"] if e["id"] == "xlk")
    assert "fx" not in xlk_core and "usd_record" not in xlk_core
    assert series["xlk"]["fx"] == _fx()
    assert series["xlk"]["usd_record"] == _usd_record()


def test_input_not_mutated():
    data = _full_payload()
    snapshot = copy.deepcopy(data)
    split_cycles_payload(data)
    assert data == snapshot, "split_cycles_payload mutated its input"


def test_entity_without_heavy_arrays_passes_through():
    core, series = split_cycles_payload(_full_payload())
    # xlv is a SECTOR with no fx/usd_record -> sectors keep osc+turns in core, so its
    # series row carries only price (fx/usd_record absent -> not added).
    assert set(series["xlv"]) == {"price"}
    assert "fx" not in series["xlv"] and "usd_record" not in series["xlv"]
    xlv_core = next(e for e in core["sectors"] if e["id"] == "xlv")
    assert "osc" in xlv_core and "turns" in xlv_core


def test_entity_with_no_heavy_keys_at_all_gets_no_series_row():
    data = {
        "meta": {}, "phases": {},
        "sectors": [{"id": "bare", "name": "Bare", "now": {"pos": 50}}],
    }
    core, series = split_cycles_payload(data)
    assert core["sectors"][0] == {"id": "bare", "name": "Bare", "now": {"pos": 50}}
    assert "bare" not in series


def test_meta_and_phases_preserved():
    data = _full_payload()
    core, _ = split_cycles_payload(data)
    assert core["meta"] == data["meta"]
    assert core["phases"] == data["phases"]


def test_absent_families_are_skipped():
    # a china-shaped payload has only sectors + baskets (no nasdaq/russell)
    data = {
        "meta": {}, "phases": {},
        "sectors": [{"id": "801010", "price": _price(), "osc": _osc(), "turns": _turns()}],
        "baskets": [{"id": "b-cn", "price": _price(), "osc": _osc(), "turns": _turns()}],
    }
    core, series = split_cycles_payload(data)
    assert "nasdaq" not in core and "russell" not in core
    assert "osc" in core["sectors"][0]              # sectors keep osc
    assert "osc" not in core["baskets"][0]          # basket osc -> series
    assert set(series) == {"801010", "b-cn"}
