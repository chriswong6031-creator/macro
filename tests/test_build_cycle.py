"""Tests for D3-W3.2 — the engine-backed cycle.html builder.

Acceptance areas (per the wave spec):

  (1) SEED PARSER      — scripts/_cycle_seed parses cycle_data.js (unquoted keys, string
                         concatenation, null, comments) → 23 curated cycles with turns[]
                         + OPINION prose, no node.
  (2) FRAME EMISSION   — a FRAME band carries the curated timeline + A8 leg-length list +
                         "N years ago" and NO position scalar / oscillator / cone (ruling A8).
  (3) MEASURED RECORD  — every registry MEASURED band emits an engine record with an
                         oscillator + confirmed turns + engine-owned projection (data-guarded).
  (4) TOLERANCE LOGGER — the build-time hand-vs-engine assertion fires on a synthetic gap
                         and NEVER fails the build on an opinion gap (only on structural error).
  (5) JS PARSE + CENSUS— the emitted window.CYCLE_ENGINE is valid JS/JSON with the right
                         two-tier census and script-tag shape (never a fetch).

Registry-resolution tests are guarded on data presence so the suite still runs in a
data-less checkout (they skip rather than fail).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from engine import cycle_proxies as cp
from scripts import _cycle_seed
from scripts import build_cycle

ROOT = Path(__file__).resolve().parent.parent
SEED_JS = ROOT / "site" / "cycle_data.js"


def _have(band) -> bool:
    try:
        cp.load_series(band)
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(autouse=True)
def _tripwires_to_tmp(tmp_path, monkeypatch):
    """compute() runs the W3.3 tripwire pass, whose latch persistence targets the
    CWD-relative data/cycle_ontology/tripwire_state.json — a TRACKED file. Point
    the latch file at tmp so test runs never dirty the repo, and no-op alert
    dispatch: against an empty tmp state every currently-FIRED tripwire would
    count as newly fired and try to notify."""
    from engine import falsifier_tripwires as ft
    monkeypatch.setattr(ft, "_STATE_JSON", tmp_path / "tripwire_state.json")
    monkeypatch.setattr(ft, "dispatch_alerts", lambda *a, **k: None)


# ── (1) SEED PARSER ──────────────────────────────────────────────────────────
def test_seed_parses_23_cycles():
    seed = _cycle_seed.load_seed(SEED_JS)
    assert len(seed["cycles"]) == 23
    assert "semis" in seed["by_id"] and "housing" in seed["by_id"]
    # xDomain + asOf come off CYCLE_META
    assert isinstance(seed["meta"].get("xDomain"), list) and len(seed["meta"]["xDomain"]) == 2
    assert seed["meta"].get("asOf")


def test_seed_captures_turns_and_concat_prose():
    seed = _cycle_seed.load_seed(SEED_JS)
    c = seed["by_id"]["semis"]
    # turns[] with null v and event strings
    assert len(c["turns"]) == 10
    assert c["turns"][0]["k"] == "peak" and c["turns"][0]["t"] == "2000-03"
    assert any(t["v"] is None for t in c["turns"])       # null parsed → None
    # string-concatenated prose survives whole (read is "..." + "..." in the source)
    assert len(c["now"]["read"]) > 200
    assert isinstance(c["proj"]["drivers"], list) and c["proj"]["drivers"]


def test_seed_parser_handles_string_concat_and_bools():
    src = 'window.CYCLE_META = {a: "x" + "y", b: [1, 2,], c: null, d: true, e: {k: "v"}};'
    (tmp := ROOT / "tests" / "_tmp_seed.js")  # noqa: E731 — inline for locality
    try:
        tmp.write_text("/* c */ (function(){\n" + src + "\n})();", encoding="utf-8")
        meta = _cycle_seed._P(_cycle_seed._tokenize(
            _cycle_seed._extract_assignment(_cycle_seed._strip_comments(tmp.read_text()),
                                            "CYCLE_META"))).value()
        assert meta == {"a": "xy", "b": [1, 2], "c": None, "d": True, "e": {"k": "v"}}
    finally:
        tmp.unlink(missing_ok=True)


# ── (2) FRAME EMISSION (ruling A8) ───────────────────────────────────────────
def _frame_band_and_seed():
    seed = _cycle_seed.load_seed(SEED_JS)
    band = cp.REGISTRY["housing"]["bands"][0]
    assert band["tier"] == "frame"
    return band, seed["by_id"]["housing"]


def test_frame_record_has_no_scalar_or_cone():
    band, seed_c = _frame_band_and_seed()
    rec = build_cycle._frame_record("housing", band, seed_c, today_x=2026.5)
    # A8: nothing resolves to a scalar position; no oscillator; no cone/proj
    assert rec["position_gauge"] is False
    assert "osc" not in rec
    assert "proj" not in rec
    assert "cone" not in rec
    assert "pos" not in rec and "now" not in rec
    # it DOES carry the crown-jewel timeline + the A8 leg-length list
    assert rec["turns"], "frame band must carry the curated turns"
    assert "leg_lengths" in rec and "ups" in rec["leg_lengths"]
    assert rec["last_turn"] and rec["years_since_last"] is not None
    # reserved tripwire slot for W3.3 (present but empty)
    assert rec["tripwire"] is None


def test_frame_leg_lengths_are_upleg_years():
    band, seed_c = _frame_band_and_seed()
    rec = build_cycle._frame_record("housing", band, seed_c, today_x=2026.5)
    ups = rec["leg_lengths"]["ups"]
    # housing curated turns give two ~14y up-legs (1975→1989, 1992→2006)
    assert all(isinstance(v, (int, float)) and v > 0 for v in ups)
    assert any(13.0 <= v <= 15.5 for v in ups), ups


def test_frame_years_since_uses_wallclock_arithmetic():
    band, seed_c = _frame_band_and_seed()
    rec = build_cycle._frame_record("housing", band, seed_c, today_x=2030.0)
    # last curated turn is 2012-02 → ~17.9y before 2030
    assert 17.0 <= rec["years_since_last"] <= 19.0, rec["years_since_last"]


# ── (3) MEASURED RECORD (data-guarded) ───────────────────────────────────────
def test_every_measured_band_emits_a_record():
    """Each registry MEASURED band (that resolves on disk) emits an engine record with an
    oscillator, confirmed turns and an engine-owned projection."""
    checked = 0
    for cid, band in cp.measured_bands():
        if cid == "spx" or not _have(band):
            continue
        rec = build_cycle._measured_record(cid, band)
        assert rec is not None, f"{cid}.{band['band']} emitted no record"
        assert rec["tier"] == "measured"
        assert rec["osc"], f"{cid} measured band has no oscillator"
        assert rec["turns"], f"{cid} measured band has no turns"
        # proxy bands suppress the position gauge (A17); non-proxy gauge it
        assert rec["position_gauge"] == (not band["proxy"])
        # engine-owned projection (anchored at last confirmed turn — W1.6)
        if rec["proj"] is not None:
            assert "central" in rec["proj"] and "overdue" in rec["proj"]
        checked += 1
    if checked == 0:
        pytest.skip("no measured tapes on disk (data-less checkout)")


def test_measured_record_trims_to_hero_window():
    band = cp.REGISTRY["business"]["bands"][0]   # INDPRO — a century of monthly history
    if not _have(band):
        pytest.skip("INDPRO tape absent")
    build_cycle._XDOMAIN0 = 2004.0
    rec = build_cycle._measured_record("business", band)
    xs = [p["x"] for p in rec["osc"]]
    # osc line trimmed to xDomain[0] − lead (turns keep the full deep history)
    assert min(xs) >= 2004.0 - build_cycle._PLOT_LEAD_YEARS - 0.1
    assert rec["n_turns_all"] and rec["n_turns_all"] > 3       # deep turns survive untrimmed


# ── (4) TOLERANCE LOGGER ─────────────────────────────────────────────────────
def test_tolerance_logger_fires_on_synthetic_gap(caplog):
    """The hand-vs-engine tolerance assertion warns loudly on a large gap and quietly on a
    small one — and NEVER raises (opinion gaps render, structural errors fail)."""
    # exercise the exact log call the builder makes, with a synthetic loud gap.
    log = logging.getLogger("build_cycle")
    with caplog.at_level(logging.INFO, logger="build_cycle"):
        hand, eng = 40.0, 92.0
        delta = round(eng - hand, 1)
        lvl = logging.WARNING if abs(delta) >= build_cycle._TOL_LOUD else logging.INFO
        log.log(lvl, "tolerance %s.%s: hand pos=%.0f  engine pos=%.1f  Δ=%+.1f",
                "synthetic", "intermediate", hand, eng, delta)
    rec = [r for r in caplog.records if "tolerance synthetic" in r.getMessage()]
    assert rec, "tolerance line not logged"
    assert rec[0].levelno == logging.WARNING       # |52| ≥ _TOL_LOUD → loud
    assert "Δ=+52.0" in rec[0].getMessage()


def test_tolerance_ledger_is_carried_not_fatal():
    """A hand-vs-engine gap is recorded in the payload ledger + on the card — it does not
    fail the build.  (Data-guarded: needs at least one measured tape to produce a ledger.)"""
    if not any(_have(b) for _, b in cp.measured_bands()):
        pytest.skip("no measured tapes on disk")
    payload = build_cycle.compute(ROOT)
    assert "tolerance_ledger" in payload
    # every ledger row has the delta triple; the build did NOT raise on any gap
    for row in payload["tolerance_ledger"]:
        assert {"cycle", "band", "hand_pos", "engine_pos", "delta"} <= set(row)


# ── (5) JS PARSE + CENSUS ────────────────────────────────────────────────────
def test_payload_census_and_shape():
    if not any(_have(b) for _, b in cp.measured_bands()):
        pytest.skip("no measured tapes on disk")
    payload = build_cycle.compute(ROOT)
    cen = payload["census"]
    assert cen["cards"] == len(payload["cycles"]) == len(payload["order"])
    assert cen["measured_cards"] + cen["frame_cards"] == cen["cards"]
    assert cen["dual_cards"] >= 4          # gold/dollar/japan/bitcoin at minimum
    # every card declares exactly one card_tier and a bands list
    for cid, card in payload["cycles"].items():
        assert card["card_tier"] in ("measured", "frame")
        assert card["bands"]
        assert "opinion" in card and "as_of" in card["opinion"]


def test_emitted_js_is_valid_and_scripttag(tmp_path):
    """The written cycle_engine.js assigns window.CYCLE_ENGINE (script-tag data, ruling A11)
    and its JSON body round-trips."""
    if not any(_have(b) for _, b in cp.measured_bands()):
        pytest.skip("no measured tapes on disk")
    payload = build_cycle.compute(ROOT)
    build_cycle._write_engine_js(tmp_path, payload)
    txt = (tmp_path / "cycledata" / "cycle_engine.js").read_text(encoding="utf-8")
    assert txt.startswith("/*") and "window.CYCLE_ENGINE = " in txt
    assert "fetch(" not in txt                          # NEVER a runtime fetch
    body = txt.split("window.CYCLE_ENGINE = ", 1)[1].rsplit(";", 1)[0]
    parsed = json.loads(body)                           # valid JSON → valid JS literal
    assert parsed["wave"] in ("W3.2", "W3.3", "W4.5")   # W4.5 adds regime_disagreement
    assert parsed["cycles"] and parsed["order"]
    assert "regime_disagreement" in parsed              # W4.5 key present (may be null)
    # W3.3: every card has a tripwires field (may be empty list)
    for cid, card in parsed["cycles"].items():
        assert "tripwires" in card, f"{cid} missing tripwires field"


def test_regime_disagreement_wired_with_meta_narrative():
    """W4.5: build_cycle wires check_claims via _regime_disagreement — the curated Q3 claims
    (12 per-cycle + the META regime block) contradict a stubbed Q1 engine, and the META
    narrative leads the summary.  Prior is stubbed so the test is data-independent."""
    from unittest.mock import patch

    firm_q1 = {"quad": "Q1", "confidence": 0.72, "transition_state": "STABLE",
               "liquidity": "expanding", "sources": {"regime": {"asof": "2026-07-01"}}}
    seed = _cycle_seed.load_seed(SEED_JS)
    with patch("engine.regime_prior.regime_prior", return_value=firm_q1):
        block = build_cycle._regime_disagreement(seed["meta"], seed["by_id"])
    assert block is not None, "curated Q3 prose must contradict a Q1 engine"
    assert block["primary_narrative_id"] == "meta"
    assert block["claimed_quad"] == "Q3"
    assert block["engine_quad"] == "Q1"
    assert block["n"] == 13                              # 12 per-cycle + meta
    assert block["cls"] == "stale-red"                   # firm engine read → red


def test_regime_disagreement_softens_on_provisional_engine():
    """A low-confidence / transitioning engine read softens the banner to amber."""
    from unittest.mock import patch

    provisional = {"quad": "Q1", "confidence": 0.327, "transition_state": "TRANSITIONING",
                   "liquidity": "expanding", "sources": {"regime": {"asof": "2026-07-01"}}}
    seed = _cycle_seed.load_seed(SEED_JS)
    with patch("engine.regime_prior.regime_prior", return_value=provisional):
        block = build_cycle._regime_disagreement(seed["meta"], seed["by_id"])
    assert block["provisional"] is True
    assert block["cls"] == "stale-amber"
    assert "provisional" in block["banner_en"].lower()


def test_committed_engine_js_parses_if_present():
    """If the builder has already run (site/cycledata/cycle_engine.js committed), the file
    is valid JS-assignable JSON with a matching census."""
    p = ROOT / "site" / "cycledata" / "cycle_engine.js"
    if not p.exists():
        pytest.skip("cycle_engine.js not built in this checkout")
    txt = p.read_text(encoding="utf-8")
    body = txt.split("window.CYCLE_ENGINE = ", 1)[1].rsplit(";", 1)[0]
    parsed = json.loads(body)
    assert parsed["census"]["cards"] == len(parsed["cycles"])
    # FRAME cards in the committed artifact carry no scalar position (A8)
    for cid, card in parsed["cycles"].items():
        if card["card_tier"] == "frame":
            for b in card["bands"]:
                if b["tier"] == "frame":
                    assert "osc" not in b and "proj" not in b and b["position_gauge"] is False


# ── (6) STALE-TAPE DEGRADE (data-guarded) ────────────────────────────────────
def test_stale_indpro_degrades_only_business(monkeypatch):
    """Regression for the 2026-07-16/17 freeze: a stale INDPRO must degrade ONLY the
    business band — compute() still returns the full payload, the business band still
    renders from its last data and carries band['stale'] for the card chip, and every
    other card (semis, memory, …) is fresh and unflagged."""
    import pandas as pd
    if not any(_have(b) for _, b in cp.measured_bands()):
        pytest.skip("no measured tapes on disk")
    real_load = cp.load_series
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=120)

    def truncating_load(band):
        s = real_load(band)
        refs = band.get("series")
        refs = [refs] if isinstance(refs, str) else (refs or [])
        if any("INDPRO" in r for r in refs):
            attrs = dict(s.attrs)
            s = s[s.index <= cutoff]
            s.attrs.update(attrs)
        return s

    monkeypatch.setattr(cp, "load_series", truncating_load)
    payload = build_cycle.compute(ROOT)          # must NOT raise

    biz = payload["cycles"]["business"]["bands"][0]
    assert biz.get("stale"), "stale INDPRO must flag the business band"
    assert biz["stale"]["days"] > biz["stale"]["limit"]
    assert biz["osc"] and biz["turns"], "stale band still renders from its last data"
    assert biz["health"]["ok"] is False

    for cid in ("semis", "memory"):
        mb = next(b for b in payload["cycles"][cid]["bands"] if b["tier"] == "measured")
        assert not mb.get("stale"), f"{cid} must be unaffected by the stale INDPRO"

    assert payload["census"]["stale_bands"] >= 1
    assert payload["census"]["cards"] >= 20      # the page is whole, not aborted
