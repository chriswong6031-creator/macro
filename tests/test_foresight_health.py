"""Tests for engine.foresight_health — P0-D data-health surface.

Three canonical scenarios:
  (a) all-dark inputs  → mode CONFIRMER-ONLY, every leg DARK
  (b) synthetic cascade with one TIGHT band → t1_fred PARTIAL/LIVE and mode FULL
  (c) None inputs throughout → no raises, returns a valid dict
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from engine.foresight_health import compute_foresight_health


# ── helpers ──────────────────────────────────────────────────────────────────

def _theme(bottleneck_band=None, demand_band=None, guidance_band=None,
           revision_breadth=None, broadening_state=None, glut_band=None,
           altdata_summary=None):
    """Minimal theme row for testing."""
    return {
        "theme": "test_theme",
        "name": "Test Theme",
        "stage": "WATCH",
        "bottleneck_band": bottleneck_band,
        "demand_band": demand_band,
        "guidance_band": guidance_band,
        "revision_breadth": revision_breadth,
        "broadening_state": broadening_state,
        "glut_band": glut_band,
        "altdata_summary": altdata_summary,
    }


# ── (a) all-dark inputs ───────────────────────────────────────────────────────

def test_all_dark_cascade(tmp_path):
    """All AWAITING_DATA cascade → every leading leg DARK, mode CONFIRMER-ONLY."""
    themes = [
        _theme(bottleneck_band="AWAITING_DATA", demand_band=None,
               guidance_band=None, broadening_state="INSUFFICIENT_HISTORY",
               glut_band="AWAITING_DATA")
        for _ in range(3)
    ]
    cascade = {"themes": themes, "asof": "2026-07-02"}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    assert h["mode"] == "CONFIRMER-ONLY"
    assert h["n_leading_live"] == 0

    legs = h["legs"]
    assert legs["t1_fred"]["status"] == "DARK"
    assert legs["t1_text"]["status"] == "DARK"
    # demand_band=None → DARK
    assert legs["t2_demand"]["status"] == "DARK"
    # guidance_band=None → DARK
    assert legs["t3_guidance"]["status"] == "DARK"
    # power not passed → DARK
    assert legs["power"]["status"] == "DARK"
    # glut AWAITING → DARK
    assert legs["glut"]["status"] == "DARK"
    # broadening INSUFFICIENT_HISTORY → DARK
    assert legs["t4_accel"]["status"] == "DARK"


def test_all_dark_no_cascade(tmp_path):
    """cascade=None → graceful, all DARK."""
    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=None)
    assert h["mode"] == "CONFIRMER-ONLY"
    assert h["n_leading_live"] == 0
    assert all(v["status"] == "DARK" for v in h["legs"].values())


# ── (b) partial live cascade: one TIGHT band ─────────────────────────────────

def test_one_tight_band_partial(tmp_path):
    """One theme with TIGHT band + one still AWAITING → t1_fred PARTIAL, mode FULL."""
    themes = [
        _theme(bottleneck_band="TIGHT"),      # real band
        _theme(bottleneck_band="AWAITING_DATA"),  # still dark
    ]
    cascade = {"themes": themes, "asof": "2026-07-02"}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    assert h["legs"]["t1_fred"]["status"] == "PARTIAL"
    assert h["legs"]["t1_fred"]["detail"] == "1/2"
    # t1_fred is PARTIAL → mode FULL
    assert h["mode"] == "FULL"
    assert h["n_leading_live"] >= 1


def test_all_tight_bands_live(tmp_path):
    """All themes with real bands → t1_fred LIVE."""
    themes = [
        _theme(bottleneck_band="TIGHT"),
        _theme(bottleneck_band="SOLD_OUT"),
    ]
    cascade = {"themes": themes, "asof": "2026-07-02"}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    assert h["legs"]["t1_fred"]["status"] == "LIVE"
    assert h["mode"] == "FULL"


def test_demand_band_live(tmp_path):
    """Themes with real demand_band → t2_demand LIVE or PARTIAL."""
    themes = [
        _theme(demand_band="ACCELERATING"),
        _theme(demand_band="STEADY"),
    ]
    cascade = {"themes": themes, "asof": "2026-07-02"}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    assert h["legs"]["t2_demand"]["status"] == "LIVE"


def test_guidance_band_partial(tmp_path):
    """One theme with real guidance_band, one without → t3_guidance PARTIAL."""
    themes = [
        _theme(guidance_band="RAISING"),
        _theme(guidance_band=None),
    ]
    cascade = {"themes": themes}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    assert h["legs"]["t3_guidance"]["status"] == "PARTIAL"


def test_broadening_accel_live(tmp_path):
    """broadening_state with a real value → t4_accel LIVE."""
    themes = [_theme(broadening_state="BROADENING")]
    cascade = {"themes": themes}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    assert h["legs"]["t4_accel"]["status"] == "LIVE"


# ── (c) None inputs don't raise ──────────────────────────────────────────────

def test_none_inputs_no_raise(tmp_path):
    """Passing all None should return a valid dict and never raise."""
    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(
            cascade=None, emergence=None, subsectors=None, convergence=None,
            power=None, analyst=None, monitor=None, track=None,
        )
    assert isinstance(h, dict)
    assert "legs" in h
    assert "mode" in h
    assert "n_leading_live" in h


def test_garbage_inputs_no_raise(tmp_path):
    """Non-dict / unexpected type inputs should degrade gracefully."""
    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(
            cascade="not-a-dict",
            power=42,
            analyst=[1, 2, 3],
            monitor="broken",
            track="also-broken",
        )
    assert isinstance(h, dict)
    assert h["mode"] in ("FULL", "CONFIRMER-ONLY")


# ── health log dedup ──────────────────────────────────────────────────────────

def test_health_log_written(tmp_path):
    """Health log is created and contains a dated entry."""
    log_path = tmp_path / "health_log.jsonl"
    cascade = {"themes": [_theme()]}

    with mock.patch("engine.foresight_health._health_log_path", return_value=log_path):
        compute_foresight_health(cascade=cascade)

    assert log_path.exists()
    lines = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    assert "date" in lines[0]
    assert "mode" in lines[0]
    assert "legs" in lines[0]


def test_health_log_dedup(tmp_path):
    """Calling twice in the same day should write only one line."""
    log_path = tmp_path / "health_log.jsonl"
    cascade = {"themes": [_theme()]}

    with mock.patch("engine.foresight_health._health_log_path", return_value=log_path):
        compute_foresight_health(cascade=cascade)
        compute_foresight_health(cascade=cascade)

    lines = [l for l in log_path.read_text().splitlines() if l.strip()]
    assert len(lines) == 1


# ── power leg ────────────────────────────────────────────────────────────────

def test_power_leg_live(tmp_path):
    """Power payload with a real band → power LIVE."""
    power = {"band": "TIGHTENING", "tightness": 0.8, "regime": True}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade={"themes": []}, power=power)

    assert h["legs"]["power"]["status"] == "LIVE"


def test_power_leg_awaiting(tmp_path):
    """Power payload with AWAITING band → power DARK."""
    power = {"band": "AWAITING_DATA"}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade={"themes": []}, power=power)

    assert h["legs"]["power"]["status"] == "DARK"


# ── confirmers ───────────────────────────────────────────────────────────────

def test_confirmers_partial(tmp_path):
    """One theme with altdata_summary, one without → confirmers PARTIAL."""
    themes = [
        _theme(altdata_summary="1 patent cluster"),
        _theme(altdata_summary=None),
    ]
    cascade = {"themes": themes}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    assert h["legs"]["confirmers"]["status"] == "PARTIAL"


# ── analyst + monitor ────────────────────────────────────────────────────────

def test_analyst_live(tmp_path):
    analyst = {"regime_read": "hyperscaler capex powering semis", "theses": []}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade={"themes": []}, analyst=analyst)

    assert h["legs"]["analyst"]["status"] == "LIVE"


def test_monitor_partial(tmp_path):
    """Monitor present but 0 open theses → PARTIAL (real thesis_monitor payload shape)."""
    monitor = {"n_open": 0, "monitored": []}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade={"themes": []}, monitor=monitor)

    assert h["legs"]["monitor"]["status"] == "PARTIAL"


def test_monitor_live(tmp_path):
    """Monitor watching open theses → LIVE (pins the real payload contract: n_open/monitored)."""
    monitor = {"n_open": 2, "monitored": [{"theme": "a"}, {"theme": "b"}]}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade={"themes": []}, monitor=monitor)

    assert h["legs"]["monitor"]["status"] == "LIVE"
    assert "2" in (h["legs"]["monitor"]["detail"] or "")


def test_monitor_live_from_monitored_list_only(tmp_path):
    """n_open missing but monitored list present → still LIVE via the list-length fallback."""
    monitor = {"monitored": [{"theme": "a"}]}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade={"themes": []}, monitor=monitor)

    assert h["legs"]["monitor"]["status"] == "LIVE"


def test_grading_live(tmp_path):
    track = {"foresight": 5, "bottleneck": 3}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade={"themes": []}, track=track)

    assert h["legs"]["grading"]["status"] == "LIVE"


# ── W1a: t1_text health flip ──────────────────────────────────────────────────

def test_t1_text_live_when_text_bands_present(tmp_path):
    """W1a: t1_text LIVE/PARTIAL when at least one theme has bottleneck_text_only=True."""
    themes = [
        dict(_theme(bottleneck_band="TIGHT (text)"), bottleneck_text_only=True),
        dict(_theme(bottleneck_band="AWAITING_DATA"), bottleneck_text_only=False),
    ]
    cascade = {"themes": themes, "asof": "2026-07-02"}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    assert h["legs"]["t1_text"]["status"] in ("LIVE", "PARTIAL")
    # t1_text PARTIAL → mode FULL
    assert h["mode"] == "FULL"
    assert h["n_leading_live"] >= 1


def test_t1_text_dark_when_no_text_bands(tmp_path):
    """When cascade themes have no text-only bands, t1_text is DARK."""
    themes = [_theme(bottleneck_band="AWAITING_DATA") for _ in range(3)]
    cascade = {"themes": themes, "asof": "2026-07-02"}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    assert h["legs"]["t1_text"]["status"] == "DARK"


def test_t1_text_all_themes_have_text_band_returns_live(tmp_path):
    """All themes with TIGHT (text) band → t1_text LIVE."""
    themes = [
        dict(_theme(bottleneck_band="TIGHT (text)"), bottleneck_text_only=True),
        dict(_theme(bottleneck_band="TIGHTENING (text)"), bottleneck_text_only=True),
    ]
    cascade = {"themes": themes, "asof": "2026-07-02"}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    assert h["legs"]["t1_text"]["status"] == "LIVE"
    assert h["mode"] == "FULL"


# ── W5a: t1_fingerprint coherence (2026-08-04 regression) ────────────────────
# site/basketdata/foresight_cascade.json shipped themes staged
# "PRECIPICE (fingerprint)" / "BROADENING (fingerprint)" while the health block
# printed t1_fingerprint DARK 0/18: the assessor counted t["fingerprint"]["n_legs_live"],
# a bottleneck-payload key the cascade rows did not carry then. Invariant pinned here:
# a theme carrying fingerprint-variant evidence ⇒ the leg is never reported fully DARK.

def _fp_theme(stage="PRECIPICE (fingerprint)", band="TIGHTENING (fingerprint)",
              fingerprint_only=True, fingerprint=None):
    """Cascade row shaped like the shipped fingerprint-staged themes."""
    t = _theme(bottleneck_band=band)
    t["stage"] = stage
    t["bottleneck_fingerprint_only"] = fingerprint_only
    if fingerprint is not None:
        t["fingerprint"] = fingerprint
    return t


def test_fingerprint_stage_without_subobject_not_dark(tmp_path):
    """The shipped regression shape: fingerprint-variant stage + band but NO fingerprint
    sub-object on the row (older committed cascade vintage) → band/stage evidence floors
    the theme at 1 live leg; the leg must not read DARK."""
    themes = [_fp_theme(), _theme(bottleneck_band="TIGHT")]
    cascade = {"themes": themes, "asof": "2026-08-04"}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    leg = h["legs"]["t1_fingerprint"]
    assert leg["status"] == "PARTIAL"
    assert leg["detail"] == "1/2"


def test_fingerprint_subobject_counts_legs(tmp_path):
    """Sub-object passthrough drives the count: n_legs_live=2 → both-legs; =1 → one leg;
    rows without fingerprint evidence count as none."""
    themes = [
        _fp_theme(band="TIGHT (fingerprint)",
                  fingerprint={"n_legs_live": 2, "basis": "annual"}),
        _fp_theme(stage="BROADENING (fingerprint)",
                  fingerprint={"n_legs_live": 1, "basis": "annual"}),
        _theme(bottleneck_band="TIGHT"),
    ]
    cascade = {"themes": themes, "asof": "2026-08-04"}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    leg = h["legs"]["t1_fingerprint"]
    assert leg["status"] == "PARTIAL"
    assert leg["detail"] == "2/3 (1 both legs)"


def test_fingerprint_subobject_on_numeric_band_theme_counts(tmp_path):
    """A FRED-mapped theme (plain numeric band, fingerprint_only False) whose bottleneck
    payload still carried fingerprint data counts toward coverage — the leg measures data
    liveness, not band flavor."""
    themes = [dict(_theme(bottleneck_band="TIGHT"),
                   fingerprint={"n_legs_live": 1, "basis": "annual"})]
    cascade = {"themes": themes, "asof": "2026-08-04"}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    leg = h["legs"]["t1_fingerprint"]
    assert leg["status"] == "PARTIAL"
    assert leg["detail"] == "1/1"


def test_fingerprint_no_evidence_stays_dark(tmp_path):
    """No sub-object, no fingerprint band/flag/stage anywhere → the leg stays DARK
    (the evidence fallback must not make it vacuously alive)."""
    themes = [_theme(bottleneck_band="TIGHT"), _theme(bottleneck_band="AWAITING_DATA")]
    cascade = {"themes": themes, "asof": "2026-08-04"}

    with mock.patch("engine.foresight_health._health_log_path", return_value=tmp_path / "h.jsonl"):
        h = compute_foresight_health(cascade=cascade)

    leg = h["legs"]["t1_fingerprint"]
    assert leg["status"] == "DARK"
    assert leg["detail"] == "0/2"
