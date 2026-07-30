"""Tests for engine/neuralweb/brain_curve.py — the Mastermind curve-detail tool.

All offline: stdlib only, no network, no LLM, no API key, no gateway import.

THREE DELIBERATE ISOLATIONS
---------------------------
  1. THE IN-PROCESS CACHE IS CLEARED between tests. It is keyed on (root, source
     mtimes) with a 60 s ceiling, so two tests writing different fixtures to the
     same tmp_path inside one mtime tick could otherwise read each other's
     payload — a green suite over a stale answer.

  2. THE LIVE PACKET IS NEUTRALISED by default. `live_tenors` calls
     market_packet.build_packet, which walks its own live-dir ladder and can
     reach /var/lib/macro-live on a deployed host or a self-hosted runner. A test
     that let it through would read PRODUCTION quotes and pass or fail depending
     on which machine ran it, and on whether the tape was open. One test opts
     back in with an explicit stub.

  3. NO WALL CLOCK. get_curve_detail takes no `now` — nothing in the payload is
     clock-derived (the asof comes off the artifact), so there is no fixture to
     age. That is why this suite has no frozen NOW where its sibling does.

Coverage:
   1-4   happy path off a transmission-shaped fixture: shape, spreads, PCA,
         momentum, recession, forwards, freshness
   5-7   parent ladder: transmission wins, regime fallback, decomposition falls
         through to world_state on that rung (both nestings)
   8-10  degraded: no parent, corrupt JSON, an all-null block
  11-13  EPISTEMICS: favored/pressured and the sector IC table never survive
         projection; the display-only disclosure is carried; the FRED seam appended
  14-15  budget: <=8 KB serialised, on the fixture and on the real artifact
  16-17  zh label passthrough; prose stays EN
  18-19  live_tenors merged when the packet has a curve; null when it does not
  20-21  no mutation of the source dicts; the caller's dict is not the cache's
  22-23  tool schema
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine.neuralweb import brain_curve as bc  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Clear the cache and stub the live packet off (see this module's docstring)."""
    bc._CACHE.clear()
    monkeypatch.setattr(bc, "_live_tenors", lambda root: None)
    yield
    bc._CACHE.clear()


# --------------------------------------------------------------------------- #
# Fixture builders — shaped like the REAL data/transmission/latest.json block
# --------------------------------------------------------------------------- #
def _slope(value, pctile, chg_bp, *, inverted=False, en="2s10s (cycle slope)"):
    """One `slopes` entry, with the bilingual label the real artifact carries."""
    return {
        "label": {"en": en, "zh": "标签"},
        "value": value, "pctile": pctile, "chg_63d_bp": chg_bp,
        "inverted": inverted,
    }


def _yield_curve_block() -> dict:
    """A full yield_curve block, including the fields that must NOT be emitted.

    `regime.favored` / `regime.pressured` and the `signals.sector` IC table are
    present ON PURPOSE: they exist in the real artifact, and the fence tests below
    prove the projection drops them.
    """
    return {
        "asof": "2026-07-29",
        "shape": {
            "level": {"value": 4.34, "pctile": 0.68, "chg_63d": 29.0},
            "slope_2s10s": {"value": 0.45, "pctile": 0.69, "chg_63d": -6.0},
            # NOTE the shape block spells it `chg_63d`, not `chg_63d_bp`.
            "fly_2s5s10s": {"value": -0.17, "pctile": 0.67, "chg_63d": 6.0},
            "fly_5s10s30s": {"value": -0.22, "pctile": 0.30, "chg_63d": -1.0},
            "pca": {
                "factors": [
                    {"key": "level", "label": {"en": "Level", "zh": "水平"},
                     "var_explained": 0.825, "loadings": {"us3m": 0.085}},
                    {"key": "slope", "label": {"en": "Slope", "zh": "斜率"},
                     "var_explained": 0.0943, "loadings": {"us3m": -0.275}},
                    {"key": "curvature", "label": {"en": "Curvature", "zh": "曲率"},
                     "var_explained": 0.0439, "loadings": {"us3m": -0.744}},
                ],
                "first3_var": 0.9632,
                "window_d": 1260,
                "tenors": ["us3m", "us2y", "us10y"],
                "pca_health": {"curvature_stability_tag": "stable"},
            },
        },
        "slopes": {
            "2s10s": _slope(0.45, 0.69, -6.0),
            "3m10y": _slope(0.84, 0.83, 13.0, en="3m10y (recession slope)"),
            "5s30s": _slope(0.74, 0.72, -21.0, en="5s30s (long-end)"),
            "2s5s": _slope(0.09, 0.61, -5.0, en="2s5s (front belly)"),
            "real_5s10s": _slope(0.22, 0.53, -36.0, en="Real 5s10s (TIPS curve)"),
            "be_5s10s": _slope(0.02, 0.76, 23.0, en="Breakeven 5s10s"),
            "tp_adj": _slope(1.29, 0.98, 7.0, en="TP-adjusted 2s10s"),
        },
        "momentum": {
            "real10y_speed_bp": 50.0, "nom10y_speed_bp": 22.0,
            "front2y_speed_bp": 38.0, "slope_chg_bp": -6.0,
            "real_speed_pctile": 0.81, "trend_spread": 0.12,
            "trend_spread_dir": "rising", "trend_spread_chg_1y_bp": 80.0,
            "window_d": 63,
        },
        "regime": {
            "key": "bear_steepener",
            "label": {"en": "Bear steepener", "zh": "熊市陡峭"},
            "desc": {"en": "long rates rising faster than short", "zh": "长端快于短端"},
            "fed_phase": {"en": "Reflation / fiscal supply", "zh": "再通胀"},
            "note": {"en": "Historically the best equity regime overall.", "zh": "历史最佳"},
            # FORBIDDEN — a shock -> beneficiary/casualty map (TI-R5).
            "favored": ["XLE", "XLF", "XLB"],
            "pressured": ["QQQ", "XLK", "XLU", "XLRE", "TLT", "GC=F"],
            "term_premium_dir": "rising",
            "term_premium_chg_bp": 13.0,
            "window_d": 21,
        },
        "recession": {
            "ntfs": 0.70,
            "ntfs_signal": "positive — no near-term break priced",
            "nyfed_prob": 14.0,
            "uninversion": False,
            "tp_adj_curve": 1.29,
            "flags": [], "n_flags": 0,
            "risk": "low",
            "policy_stance": {
                "fed_funds": 3.63, "neutral_anchor": 2.5, "gap_pp": 1.13,
                "stance": "restrictive",
                "note": {"en": "Wright (2006) exposition " + "x" * 400, "zh": "注"},
            },
            "lead_time_note": {"en": "y" * 900, "zh": "注"},
        },
        "forwards": {
            "f_1y1y": 4.43, "f_2y1y": 4.41, "f_5y5y": 4.87,
            "carry_10y_pct": 4.61, "rolldown_10y_pct": 0.37,
            "carry_roll_10y_pct": 4.98,
            "note": {"en": "z" * 400, "zh": "注"},
        },
        # FORBIDDEN — per-ETF tilts with forward ICs and CONFIRMED verdicts.
        "signals": {
            "core_macro": {"en": "Curve: Bear steepener.", "zh": "曲线"},
            "sector": [
                {"etf": "XLF", "tilt": "tailwind", "ic": -0.204,
                 "verdict": "CONFIRMED", "duration": "short"},
                {"etf": "XLK", "tilt": "headwind", "ic": -0.221,
                 "verdict": "CONFIRMED", "duration": "long"},
            ],
        },
        "scored_status": {
            "en": "Display-only. No yield-curve leg passed the scored-leg gate.",
            "zh": "仅供展示。",
        },
        "caveats": [
            {"en": "Display / context only — never scored.", "zh": "仅供展示"},
            {"en": "Rate-of-change beats level.", "zh": "速度胜过水平"},
        ],
    }


_STATE = {
    "rates": {
        "real_10y": 2.41, "real_10y_pctile": 0.99, "real_10y_chg_63d_bp": 50.0,
        "nominal_10y": 4.61, "curve_2s10s": 0.45, "curve_tp_adj": 1.29,
        "policy_gap": 0.63, "regime": "restrictive", "direction": "rising",
        "label": {"en": "Real 10y 2.41%", "zh": "实际10年期"},
    },
    "expectations": {
        "breakeven_10y": 2.26, "breakeven_5y5y": 2.28, "model_5y": 2.42,
        "survey_1y": 4.8, "market_minus_model_bp": -14.0, "anchoring": "anchored",
        "label": {"en": "5y5y breakeven 2.28%", "zh": "5年5年"},
    },
}


def _write(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _transmission(root: pathlib.Path, *, block=None, state=None) -> None:
    """data/transmission/latest.json — the display-tier parent (66 KB in prod)."""
    _write(root / "data" / "transmission" / "latest.json", {
        "asof": "2026-07-29",
        "state": _STATE if state is None else state,
        "yield_curve": _yield_curve_block() if block is None else block,
    })


def _regime(root: pathlib.Path, *, block=None) -> None:
    """data/regime/latest.json — the infra-tier parent, which carries NO `state`."""
    _write(root / "data" / "regime" / "latest.json", {
        "asof": "2026-07-29",
        "yield_curve": _yield_curve_block() if block is None else block,
    })


def _world_state(root: pathlib.Path, *, nested: bool = True) -> None:
    """data/neuralweb/world_state.json. `nested` is the REAL 2026-07 location
    (rates_transmission.state); the flat form is the shape a later flattening
    would produce, and both rungs are read."""
    payload = ({"rates_transmission": {"asof": "2026-07-29", "state": _STATE}}
               if nested else {"state": _STATE})
    _write(root / "data" / "neuralweb" / "world_state.json", payload)


# --------------------------------------------------------------------------- #
# 1-4  Happy path
# --------------------------------------------------------------------------- #
def test_happy_path_carries_the_documented_envelope(tmp_path):
    _transmission(tmp_path)
    out = bc.get_curve_detail(tmp_path)

    assert out["schema"] == "brain.curve_detail.v1"
    assert out["asof"] == "2026-07-29"
    assert out["tier"] == "display"
    assert "error" not in out
    assert set(out) == {
        "schema", "asof", "tier", "regime", "spreads", "decomposition", "shape",
        "momentum", "recession", "forwards", "live_tenors", "freshness", "caveats",
    }
    assert out["freshness"]["source_asof"] == "2026-07-29"


def test_spreads_carry_value_pctile_change_and_inversion(tmp_path):
    """The four headline spreads, each with the percentile that makes it readable."""
    _transmission(tmp_path)
    spreads = bc.get_curve_detail(tmp_path)["spreads"]
    assert set(spreads) == {"2s10s", "3m10y", "5s30s", "2s5s"}
    assert spreads["2s10s"] == {
        "value": 0.45, "pctile": 0.69, "chg_63d_bp": -6.0, "inverted": False,
    }
    assert spreads["5s30s"]["chg_63d_bp"] == -21.0
    # The bilingual label is NOT carried: it is UI furniture, and the model gets
    # the key ("5s30s") plus the schema description instead.
    assert "label" not in spreads["5s30s"]


def test_shape_pca_names_its_numbers_as_variance_shares(tmp_path):
    """A bare `"level": 0.825` beside `"nominal_10y": 4.61` invites reading a
    variance share as a rate — the yield-direction misread the eval rubric tracks.
    The key has to say what the number is."""
    _transmission(tmp_path)
    shape = bc.get_curve_detail(tmp_path)["shape"]
    assert shape["level"] == 4.34 and shape["level_pctile"] == 0.68
    assert shape["pca"] == {
        "level_var_explained": 0.825,
        "slope_var_explained": 0.0943,
        "curvature_var_explained": 0.0439,
        "first3_var_explained": 0.9632,
        "window_d": 1260.0,
    }
    # The `shape` block spells the change `chg_63d`; the output normalises every
    # change key to `_bp` so a caller does not have to know which block it came from.
    assert shape["fly_2s5s10s"] == {"value": -0.17, "pctile": 0.67, "chg_63d_bp": 6.0}
    assert shape["fly_5s10s30s"]["chg_63d_bp"] == -1.0
    # PCA loadings and pca_health are a 9x3 matrix of no use to a chat turn.
    assert "loadings" not in json.dumps(shape)
    assert "pca_health" not in shape["pca"]


def test_decomposition_momentum_recession_and_forwards(tmp_path):
    _transmission(tmp_path)
    out = bc.get_curve_detail(tmp_path)

    decomp = out["decomposition"]
    assert decomp["nominal_10y"] == 4.61 and decomp["real_10y"] == 2.41
    assert decomp["breakeven_10y"] == 2.26 and decomp["breakeven_5y5y"] == 2.28
    assert decomp["anchoring"] == "anchored"
    assert decomp["real_5s10s"]["chg_63d_bp"] == -36.0
    assert decomp["be_5s10s"]["value"] == 0.02
    assert decomp["tp_adj_2s10s"]["pctile"] == 0.98
    # The two upstream "policy gap" quantities are DIFFERENT (2y−funds market
    # pricing vs funds−neutral stance) and read 0.63 / 1.13 on 2026-07-29. Both
    # ship, under keys that state their own arithmetic, so neither can be quoted
    # as the other.
    assert decomp["policy_pricing_2y_minus_funds_pp"] == 0.63
    assert out["recession"]["policy_stance"]["gap_pp"] == 1.13
    assert "policy_gap_pp" not in decomp

    assert out["momentum"]["real10y_speed_bp"] == 50.0
    assert out["momentum"]["trend_spread_dir"] == "rising"

    rec = out["recession"]
    assert rec["ntfs"] == 0.70
    # The stance word rides WITH the number: 0.70 alone carries no sign convention.
    assert rec["ntfs_signal"] == "positive — no near-term break priced"
    assert rec["nyfed_prob_pct"] == 14.0
    assert rec["uninversion"] is False and rec["risk"] == "low"
    assert rec["policy_stance"]["stance"] == "restrictive"
    # The Wright-2006 paragraph is textbook context, not a fact about today.
    assert "note" not in rec["policy_stance"]
    assert "lead_time_note" not in rec

    fwd = out["forwards"]
    assert fwd["f_5y5y"] == 4.87
    # carry_roll_10y_pct upstream -> carry_rolldown_10y_pct out (carry + rolldown).
    assert fwd["carry_rolldown_10y_pct"] == 4.98
    assert "note" not in fwd


# --------------------------------------------------------------------------- #
# 5-7  Parent ladder + decomposition fallback
# --------------------------------------------------------------------------- #
def test_transmission_parent_wins_over_regime(tmp_path):
    """The display-tier parent leads: it is 66 KB against 770 KB and carries the
    decomposition in its own `state`, so the happy path is one file open."""
    _transmission(tmp_path)
    other = _yield_curve_block()
    other["asof"] = "2026-07-01"
    _regime(tmp_path, block=other)
    assert bc.get_curve_detail(tmp_path)["asof"] == "2026-07-29"


def test_regime_parent_is_the_fallback(tmp_path):
    """With no transmission artifact the regime parent answers, in full."""
    _regime(tmp_path)
    out = bc.get_curve_detail(tmp_path)
    assert out["asof"] == "2026-07-29"
    assert out["spreads"]["2s10s"]["value"] == 0.45
    assert out["regime"]["key"] == "bear_steepener"


@pytest.mark.parametrize("nested", [True, False])
def test_decomposition_falls_through_to_world_state_on_the_regime_rung(tmp_path, nested):
    """data/regime/latest.json carries NO `state` block (verified against the real
    770 KB artifact), so on that rung the real/breakeven levels must come from the
    Neural Web world state — otherwise the fallback silently ships a curve with no
    real-rate or breakeven read at all."""
    _regime(tmp_path)
    _world_state(tmp_path, nested=nested)
    decomp = bc.get_curve_detail(tmp_path)["decomposition"]
    assert decomp["nominal_10y"] == 4.61
    assert decomp["real_10y"] == 2.41
    assert decomp["breakeven_5y5y"] == 2.28
    assert decomp["anchoring"] == "anchored"


def test_regime_rung_without_world_state_still_serves_the_curve(tmp_path):
    """A missing world state costs the LEVELS, never the whole read: the spreads,
    regime and recession suite all live in the block itself."""
    _regime(tmp_path)
    out = bc.get_curve_detail(tmp_path)
    decomp = out["decomposition"]
    assert "nominal_10y" not in decomp and "breakeven_10y" not in decomp
    # The curve legs survive — they come from `slopes`, not from `state`.
    assert decomp["real_5s10s"]["value"] == 0.22
    assert out["spreads"]["3m10y"]["value"] == 0.84


# --------------------------------------------------------------------------- #
# 8-10  Degraded paths
# --------------------------------------------------------------------------- #
def test_no_parent_artifact_returns_the_documented_error(tmp_path):
    out = bc.get_curve_detail(tmp_path)
    assert out["schema"] == "brain.curve_detail.v1"
    assert out["error"] == "curve_detail_unavailable"
    assert "spreads" not in out and "regime" not in out
    # An honest instruction, so the model says "unavailable" instead of
    # describing a curve it never read.
    assert "unavailable" in out["note"]


def test_corrupt_parent_json_falls_through_to_the_next_rung(tmp_path):
    """Corrupt is treated as absent — and must not take the turn down."""
    path = tmp_path / "data" / "transmission" / "latest.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    _regime(tmp_path)
    assert bc.get_curve_detail(tmp_path)["asof"] == "2026-07-29"


def test_both_parents_corrupt_reports_unavailable(tmp_path):
    for rel in (("data", "transmission", "latest.json"), ("data", "regime", "latest.json")):
        path = tmp_path.joinpath(*rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
    assert bc.get_curve_detail(tmp_path)["error"] == "curve_detail_unavailable"


def test_a_parent_present_but_missing_the_block_is_skipped(tmp_path):
    """`yield_curve` absent (or not a dict) is not a usable parent."""
    _write(tmp_path / "data" / "transmission" / "latest.json",
           {"asof": "2026-07-29", "state": _STATE, "yield_curve": None})
    _regime(tmp_path)
    assert bc.get_curve_detail(tmp_path)["asof"] == "2026-07-29"

    bc._CACHE.clear()
    _write(tmp_path / "data" / "regime" / "latest.json", {"asof": "x"})
    assert bc.get_curve_detail(tmp_path)["error"] == "curve_detail_unavailable"


def test_an_all_null_block_drops_rather_than_shipping_hollow_sections(tmp_path):
    """A section of nothing but nulls reads as "the desk measured this and got
    nothing"; absent reads as "not published in this vintage". Only the second is
    true, so empty sections are dropped."""
    block = {
        "asof": "2026-07-29",
        "shape": {"level": {"value": None, "pctile": None}},
        "slopes": {"2s10s": {"value": None, "pctile": None, "chg_63d_bp": None}},
        "momentum": {}, "regime": {}, "recession": {}, "forwards": {},
    }
    _transmission(tmp_path, block=block, state={})
    out = bc.get_curve_detail(tmp_path)
    assert out["asof"] == "2026-07-29"
    for absent in ("spreads", "shape", "momentum", "regime", "recession",
                   "forwards", "decomposition"):
        assert absent not in out, f"{absent} shipped as an all-null block"
    # The disclosure still ships: the seam applies to a thin vintage too.
    assert out["caveats"] == [bc._FRED_SEAM_CAVEAT]
    assert out["live_tenors"] is None


def test_inverted_is_only_emitted_when_it_is_a_real_boolean(tmp_path):
    """A string "false" or a missing key must not become an inversion claim."""
    block = _yield_curve_block()
    block["slopes"]["2s10s"]["inverted"] = "false"
    block["slopes"]["3m10y"].pop("inverted")
    block["slopes"]["5s30s"]["inverted"] = True
    _transmission(tmp_path, block=block)
    spreads = bc.get_curve_detail(tmp_path)["spreads"]
    assert "inverted" not in spreads["2s10s"]
    assert "inverted" not in spreads["3m10y"]
    assert spreads["5s30s"]["inverted"] is True


# --------------------------------------------------------------------------- #
# 11-13  EPISTEMICS — TI-R5 / A7, pinned mechanically
# --------------------------------------------------------------------------- #
def test_favored_and_pressured_lists_never_reach_the_output(tmp_path):
    """The block carries `regime.favored` / `regime.pressured` — a shock ->
    beneficiary/casualty map, a standing house KILL (TI-R5,
    research/DO_NOT_REBUILD.md §1). The curve tool must not become the
    beneficiary map by another name.

    Asserted on the whole serialised payload, not just on the `regime` key, so a
    future source that MOVES or renames the lists still cannot leak them.
    """
    _transmission(tmp_path)
    out = bc.get_curve_detail(tmp_path)
    assert "favored" not in out["regime"] and "pressured" not in out["regime"]
    blob = json.dumps(out, ensure_ascii=False)
    for ticker in ("XLE", "XLF", "XLB", "QQQ", "XLK", "XLU", "XLRE", "TLT", "GC=F"):
        assert ticker not in blob, f"{ticker} leaked out of the beneficiary map"


def test_the_sector_ic_table_and_its_verdicts_never_reach_the_output(tmp_path):
    """`signals.sector` is per-ETF tilts with forward ICs and CONFIRMED /
    DIRECTIONAL verdicts — laundered directional escalation if relayed by an LLM
    (A7: the model may not originate or relay a signal or escalation)."""
    _transmission(tmp_path)
    blob = json.dumps(bc.get_curve_detail(tmp_path), ensure_ascii=False)
    for banned in ("signals", "CONFIRMED", "DIRECTIONAL", "tailwind", "headwind",
                   "-0.204", "-0.221", "ic_driver"):
        assert banned not in blob, f"{banned!r} survived projection"


def test_the_display_only_disclosure_and_the_fred_seam_both_ship(tmp_path):
    """Nulls printed, not hidden: the calibrator found NO yield-curve leg robust
    enough to move an allocation, and that has to travel with the numbers. The
    weekly-FRED seam is appended on top — a leg can be days older than the asof.
    """
    _transmission(tmp_path)
    caveats = bc.get_curve_detail(tmp_path)["caveats"]
    assert any("scored-leg gate" in c for c in caveats), "scored_status was dropped"
    assert any("never scored" in c for c in caveats), "source caveats were dropped"
    assert caveats[-1] == bc._FRED_SEAM_CAVEAT
    assert "multi-day official lag" in caveats[-1]


def test_the_seam_caveat_survives_a_source_that_floods_the_caveat_list(tmp_path):
    """OUR disclosure is not the source's to crowd out — the bound drops source
    entries, never the seam."""
    block = _yield_curve_block()
    block["caveats"] = [{"en": f"source caveat {n}", "zh": "x"} for n in range(30)]
    _transmission(tmp_path, block=block)
    caveats = bc.get_curve_detail(tmp_path)["caveats"]
    assert len(caveats) <= bc._MAX_CAVEATS + 1
    assert caveats[-1] == bc._FRED_SEAM_CAVEAT


def test_no_numeric_confidence_key_is_emitted(tmp_path):
    """Percentiles and variance shares are measurements the engine published; a
    `confidence`/`score`/`probability` key would be an authority claim this
    display-tier tool has no gauntlet for."""
    _transmission(tmp_path)
    blob = json.dumps(bc.get_curve_detail(tmp_path)).lower()
    for banned in ("confidence", "\"score\"", "conviction", "validated"):
        assert banned not in blob, f"{banned} appeared in a display-tier payload"


# --------------------------------------------------------------------------- #
# 14-15  Payload budget
# --------------------------------------------------------------------------- #
_BUDGET_BYTES = 8 * 1024


def test_payload_stays_inside_the_eight_kb_budget(tmp_path):
    """The fixture deliberately carries oversized prose (a 900-char lead-time
    note, a 400-char stance note) so this measures the CLAMPS, not a thin
    fixture."""
    _transmission(tmp_path)
    size = len(json.dumps(bc.get_curve_detail(tmp_path), ensure_ascii=False))
    assert size <= _BUDGET_BYTES, f"{size} bytes exceeds the 8 KB budget"


def test_a_source_with_runaway_prose_is_still_inside_budget(tmp_path):
    """Every prose field clamped, so one verbose vintage cannot blow the budget."""
    block = _yield_curve_block()
    block["regime"]["note"]["en"] = "N" * 5000
    block["regime"]["fed_phase"]["en"] = "P" * 5000
    block["regime"]["desc"]["en"] = "D" * 5000
    block["scored_status"]["en"] = "S" * 5000
    block["caveats"] = [{"en": "C" * 5000, "zh": "x"} for _ in range(6)]
    _transmission(tmp_path, block=block)
    out = bc.get_curve_detail(tmp_path)
    size = len(json.dumps(out, ensure_ascii=False))
    assert size <= _BUDGET_BYTES, f"{size} bytes exceeds the 8 KB budget"
    assert out["regime"]["note"].endswith("…"), "the clamp marks the truncation"


@pytest.mark.skipif(
    not (ROOT / "data" / "transmission" / "latest.json").exists(),
    reason="data/transmission/latest.json not present in this checkout",
)
def test_real_artifact_read_is_well_formed_and_inside_budget():
    """The committed artifact, read at the wall clock on purpose: the one test
    that proves the tool works against real data as it ages."""
    out = bc.get_curve_detail(ROOT)
    assert out["schema"] == "brain.curve_detail.v1"
    assert "error" not in out, "the real artifact failed to project"
    assert out["asof"], "the real read carries no asof"
    size = len(json.dumps(out, ensure_ascii=False))
    assert size <= _BUDGET_BYTES, f"real payload is {size} bytes"
    assert out["spreads"]["2s10s"]["value"] is not None
    assert out["caveats"][-1] == bc._FRED_SEAM_CAVEAT
    blob = json.dumps(out, ensure_ascii=False)
    for ticker in ("XLE", "XLF", "QQQ", "XLK", "TLT"):
        assert ticker not in blob, f"{ticker} leaked from the real artifact"


# --------------------------------------------------------------------------- #
# 16-17  Language
# --------------------------------------------------------------------------- #
def test_the_regime_label_passes_zh_through(tmp_path):
    """The desk PRECOMPUTES both label languages (curve_regime_label_zh is the
    packet's precedent), so both ship — never a machine translation, and never an
    English string presented as Chinese."""
    _transmission(tmp_path)
    regime = bc.get_curve_detail(tmp_path)["regime"]
    assert regime["label_en"] == "Bear steepener"
    assert regime["label_zh"] == "熊市陡峭"


def test_an_untranslated_label_ships_no_zh_key(tmp_path):
    block = _yield_curve_block()
    block["regime"]["label"] = {"en": "Bear steepener"}
    _transmission(tmp_path, block=block)
    regime = bc.get_curve_detail(tmp_path)["regime"]
    assert regime["label_en"] == "Bear steepener"
    assert "label_zh" not in regime


def test_prose_fields_ship_en_only_to_hold_the_budget(tmp_path):
    """Carrying both languages for every paragraph would roughly double a payload
    with an 8 KB ceiling; the reply's language is the LANGUAGE directive's job."""
    _transmission(tmp_path)
    regime = bc.get_curve_detail(tmp_path)["regime"]
    assert regime["note"] == "Historically the best equity regime overall."
    assert regime["fed_phase"] == "Reflation / fiscal supply"
    assert "历史最佳" not in json.dumps(regime, ensure_ascii=False)


def test_a_bare_string_label_is_accepted_as_english(tmp_path):
    """Defensive shape handling: not every desk field is an {en, zh} pair."""
    block = _yield_curve_block()
    block["regime"]["label"] = "Bear steepener"
    block["scored_status"] = "Display-only, scored-leg gate found nothing."
    _transmission(tmp_path, block=block)
    out = bc.get_curve_detail(tmp_path)
    assert out["regime"]["label_en"] == "Bear steepener"
    assert any("scored-leg gate" in c for c in out["caveats"])


# --------------------------------------------------------------------------- #
# 18-19  Live tenor overlay
# --------------------------------------------------------------------------- #
def test_live_tenors_are_merged_when_the_packet_has_a_curve(tmp_path, monkeypatch):
    """The overlay comes from market_packet, NOT from a second quotes.json read:
    the packet already does PAIR-LEVEL yield-scale detection, and yield-index
    units are feed-dependent here (spark = percent-direct, relay = x10). Re-reading
    quotes would fork that law."""
    monkeypatch.undo()  # restore the real _live_tenors, then stub the packet
    bc._CACHE.clear()
    from engine.neuralweb import market_packet

    monkeypatch.setattr(market_packet, "build_packet", lambda root: {
        "version": "x",
        "curve": {
            "tenors": {
                "3M": {"level_pct": 3.66, "change_bp": -1.2},
                "10Y": {"level_pct": 4.61, "change_bp": 3.4},
                "30Y": {"level_pct": 5.02, "change_bp": None},
            },
            "asof": "2026-07-29T18:30:00Z",
            "front_tenor": "3M", "long_tenor": "30Y",
        },
    })
    _transmission(tmp_path)
    out = bc.get_curve_detail(tmp_path)

    live = out["live_tenors"]
    assert live["asof"] == "2026-07-29T18:30:00Z"
    assert live["tenors"]["10Y"] == {"level_pct": 4.61, "change_bp": 3.4}
    assert live["tenors"]["3M"]["level_pct"] == 3.66
    # A tenor with a level but no change keeps the level rather than vanishing.
    assert live["tenors"]["30Y"] == {"level_pct": 5.02}
    # Both stamps are reported, so a nightly asof is never read as a live one.
    assert out["freshness"] == {"source_asof": "2026-07-29",
                               "live_asof": "2026-07-29T18:30:00Z"}
    # front_tenor/long_tenor are packet-internal plumbing, not a curve fact.
    assert set(live) == {"tenors", "asof"}


def test_live_tenors_is_an_explicit_null_when_the_tape_is_dark(tmp_path, monkeypatch):
    """Explicit null, not a missing key: null says "the overlay is absent"
    (closed, stale, unresolved), a missing key says "not part of this tool".

    This is the real state of a fresh checkout — the committed quotes.json
    snapshot predates ^TNX entering DISPLAY_SYMBOLS (#3963), so it carries no
    yield symbols at all.
    """
    monkeypatch.undo()
    bc._CACHE.clear()
    from engine.neuralweb import market_packet

    monkeypatch.setattr(market_packet, "build_packet",
                        lambda root: {"version": "x", "gaps": ["quotes: absent"]})
    _transmission(tmp_path)
    out = bc.get_curve_detail(tmp_path)
    assert "live_tenors" in out and out["live_tenors"] is None
    assert out["freshness"] == {"source_asof": "2026-07-29"}


def test_a_packet_explosion_costs_the_overlay_not_the_curve(tmp_path, monkeypatch):
    """The nightly read is the deliverable; the overlay is a bonus."""
    monkeypatch.undo()
    bc._CACHE.clear()
    from engine.neuralweb import market_packet

    def _boom(root):
        raise RuntimeError("live dir exploded")

    monkeypatch.setattr(market_packet, "build_packet", _boom)
    _transmission(tmp_path)
    out = bc.get_curve_detail(tmp_path)
    assert out["live_tenors"] is None
    assert out["spreads"]["2s10s"]["value"] == 0.45


# --------------------------------------------------------------------------- #
# 20-21  Isolation: sources and cache
# --------------------------------------------------------------------------- #
def test_the_source_dicts_are_never_mutated(tmp_path):
    """Pure slicing. Read the parents, project, then re-read and compare byte for
    byte — an artifact-strip that mutated a reused dict has burned this house
    before (memory: artifact-strip-must-not-mutate-reused-dict)."""
    _transmission(tmp_path)
    _world_state(tmp_path)
    paths = [tmp_path / "data" / "transmission" / "latest.json",
             tmp_path / "data" / "neuralweb" / "world_state.json"]
    before = [p.read_text(encoding="utf-8") for p in paths]

    out = bc.get_curve_detail(tmp_path)
    out["spreads"]["2s10s"]["value"] = 99.0      # caller scribbles on the result
    out["caveats"].append("caller junk")
    del out["regime"]

    assert [p.read_text(encoding="utf-8") for p in paths] == before
    bc._CACHE.clear()
    fresh = bc.get_curve_detail(tmp_path)
    assert fresh["spreads"]["2s10s"]["value"] == 0.45
    assert "regime" in fresh


def test_a_caller_cannot_poison_the_cache(tmp_path):
    """The cache holds a STRING and every hit is re-parsed, so a caller mutating
    what it got back cannot corrupt the next caller's answer."""
    _transmission(tmp_path)
    first = bc.get_curve_detail(tmp_path)
    first["spreads"]["2s10s"]["value"] = 99.0
    first["caveats"].clear()

    second = bc.get_curve_detail(tmp_path)          # served from cache
    assert second["spreads"]["2s10s"]["value"] == 0.45
    assert second["caveats"][-1] == bc._FRED_SEAM_CAVEAT
    assert second is not first


def test_the_cache_key_moves_when_a_source_appears(tmp_path):
    """A source that APPEARS changes the key as surely as an edited one — a
    missing file is keyed as None, not skipped. Otherwise the regime rung's
    decomposition would stay dark until the 60 s ceiling expired."""
    _regime(tmp_path)
    assert "nominal_10y" not in bc.get_curve_detail(tmp_path)["decomposition"]
    _world_state(tmp_path)
    assert bc.get_curve_detail(tmp_path)["decomposition"]["nominal_10y"] == 4.61


def test_get_curve_detail_never_raises_on_junk_input():
    """Not even for a root that cannot be stat'd."""
    for root in (pathlib.Path("/nonexistent/macro/root"),
                 pathlib.Path("/dev/null")):
        bc._CACHE.clear()
        out = bc.get_curve_detail(root)
        assert out["schema"] == "brain.curve_detail.v1"
        assert out["error"] == "curve_detail_unavailable"


def test_the_block_is_sliced_not_the_parent_returned(tmp_path):
    """The regime parent is 770 KB of unrelated infrastructure; only the
    ~18 KB yield_curve block may be read out of it."""
    block = _yield_curve_block()
    _write(tmp_path / "data" / "regime" / "latest.json", {
        "asof": "2026-07-29",
        "yield_curve": block,
        "risk_radar_raw": {"secret": "x" * 5000},
        "foresight_cascade": ["do not ship me"],
    })
    blob = json.dumps(bc.get_curve_detail(tmp_path), ensure_ascii=False)
    assert "do not ship me" not in blob
    assert "risk_radar_raw" not in blob and "foresight_cascade" not in blob


# --------------------------------------------------------------------------- #
# 22-23  Tool schema
# --------------------------------------------------------------------------- #
def test_curve_tool_schema_shape_and_epistemics_fence():
    schema = bc.CURVE_TOOL_SCHEMA
    assert schema["name"] == "get_curve_detail"
    assert schema["input_schema"] == {"type": "object", "properties": {},
                                      "required": []}, "no arguments — root is injected"
    description = schema["description"]
    # WHEN to call it.
    for cue in ("yield curve", "steepening", "inversion", "breakeven",
                "term premium", "duration"):
        assert cue in description, f"the model is never told to call it for {cue!r}"
    # The tier fence and the honest seam, stated to the model too.
    assert "DISPLAY TIER" in description
    assert "never an allocation signal" in description
    assert "no sector beneficiary or casualty list" in description
    assert "multi-day official lag" in description
    # CI-guarded house word: never claim a display-tier read is validated.
    assert "validated" not in description.lower()


def test_curve_schema_is_json_serialisable():
    """It is handed to the Anthropic SDK verbatim."""
    assert json.loads(json.dumps(bc.CURVE_TOOL_SCHEMA)) == bc.CURVE_TOOL_SCHEMA


def test_module_constants_match_the_documented_contract():
    """The names the gateway and the tests both key off."""
    assert bc.SCHEMA == "brain.curve_detail.v1"
    assert bc.ERROR_UNAVAILABLE == "curve_detail_unavailable"
    assert bc._PARENT_RELS[0] == ("data", "transmission", "latest.json")
    assert bc._PARENT_RELS[1] == ("data", "regime", "latest.json")
    assert copy.deepcopy(bc._SPREAD_KEYS) == ("2s10s", "3m10y", "5s30s", "2s5s")
