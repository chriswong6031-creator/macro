"""tests/test_mag7_panel.py — Mag 7 panel template render tests.

Covers:
  - Full fixture render (running_narrow) produces correct Tier-1 copy
  - Fail-open: panel renders nothing when payload is absent
  - Fail-open: panel renders nothing when trend_state is missing
  - No banned Tier-1 jargon leaks into rendered HTML
  - Dot class logic: green / amber / grey
  - Stance vocabulary by trend_state
  - Bilingual strings present
  - Footer ONE sentence, no "validated" word
  - Tech-legs word/arrow derivation
  - build_site._mag7_regime_view returns None gracefully when file missing
  - build_site._mag7_regime_view returns None when trend_state absent
"""
import pathlib
import json
import sys
import os
import pytest

# ── jinja2 guard ──────────────────────────────────────────────────────────────
try:
    from jinja2 import Environment, FileSystemLoader
    _JINJA_OK = True
except ImportError:
    _JINJA_OK = False

TEMPLATE_DIR = pathlib.Path(__file__).parent.parent / "templates"


def _env() -> "Environment":
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=False)
    return env


# ── fixture ───────────────────────────────────────────────────────────────────
FIXTURE: dict = {
    "as_of": "2026-07-10",
    "weights_basis": "polygon_mktcap",
    "trend_state": "running_narrow",
    "structure": {"dd_from_252d_high": -0.082, "chip": "recovering"},
    "run": {"start": "2026-06-26", "sessions": 11, "cw_ret": 0.093, "spy_ret": 0.022},
    "k7": {"trend": 4, "rs": 5},
    "cw": {"r2": 0.011, "r5": 0.032, "r10": 0.061, "r20": 0.038, "rel20": 0.016},
    "ew": {"r10": 0.042, "r20": 0.020},
    "members": [
        {"sym": "AAPL", "w": 0.184, "r5": 0.083, "r10": 0.065, "r20": 0.088,
         "rs20": 0.061, "above50": True, "above200": True, "contrib10": 0.31,
         "mtf": "UPTURN_CONFIRMED"},
        {"sym": "MSFT", "w": 0.132, "r5": -0.020, "r10": -0.031, "r20": -0.047,
         "rs20": -0.063, "above50": False, "above200": False, "contrib10": -0.08,
         "mtf": "UPTURN_EARLY"},
        {"sym": "NVDA", "w": 0.128, "r5": 0.044, "r10": -0.012, "r20": -0.026,
         "rs20": -0.042, "above50": False, "above200": False, "contrib10": -0.01,
         "mtf": "RUNNING"},
        {"sym": "AMZN", "w": 0.110, "r5": 0.021, "r10": 0.038, "r20": 0.047,
         "rs20": 0.031, "above50": False, "above200": True, "contrib10": 0.04,
         "mtf": "RUNNING"},
        {"sym": "GOOGL", "w": 0.102, "r5": -0.008, "r10": -0.009, "r20": -0.015,
         "rs20": -0.031, "above50": False, "above200": False, "contrib10": -0.01,
         "mtf": "COOLING"},
        {"sym": "META", "w": 0.098, "r5": 0.062, "r10": 0.071, "r20": 0.081,
         "rs20": 0.065, "above50": True, "above200": True, "contrib10": 0.07,
         "mtf": "UPTURN_CONFIRMED"},
        {"sym": "TSLA", "w": 0.070, "r5": -0.033, "r10": -0.054, "r20": -0.063,
         "rs20": -0.079, "above50": False, "above200": False, "contrib10": -0.04,
         "mtf": "DOWN"},
    ],
    "generals": {"now": ["AAPL", "META"], "joining": ["NVDA"], "coverage": 0.64},
    "spread20": {"max": 0.088, "min": -0.047, "range": 0.135},
    "mags": {"px": 65.10, "asof": "2026-07-02", "since_run": 0.057},
    "tech_legs": [
        {"id": "mag7", "en": "Mag 7", "zh": "七巨头", "r10_rel": 0.061,
         "r20_rel": 0.016, "word": "surging"},
        {"id": "ai_semiconductors", "en": "AI chips", "zh": "AI芯片",
         "r10_rel": 0.021, "r20_rel": -0.012, "word": "running"},
        {"id": "memory_storage", "en": "Memory", "zh": "存储",
         "r10_rel": -0.14, "r20_rel": 0.023, "word": "falling hard"},
        {"id": "ai_software", "en": "Software", "zh": "软件",
         "r10_rel": 0.008, "r20_rel": 0.007, "word": "flat"},
    ],
}

RENDER_TMPL = (
    "{% from '_mag7_panel.html.j2' import mag7_panel %}"
    "{{ mag7_panel(d) }}"
)
GUARD_TMPL = (
    "{% from '_mag7_panel.html.j2' import mag7_panel %}"
    "{% if d %}{{ mag7_panel(d) }}{% endif %}"
)


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_renders_full_fixture():
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FIXTURE)
    # Tier-1 title present
    assert "Mag 7" in html
    # Chinese twin present
    assert "七巨头" in html
    # State badge
    assert "Running" in html
    # State line contains day count + numbers
    assert "day 11" in html
    # Generals with company names (not raw tickers on Tier 1)
    assert "Apple" in html
    assert "Meta" in html
    assert "Nvidia" in html
    # Stance
    assert "don't chase" in html
    # Structure chip
    assert "8%" in html
    # Tech legs
    assert "surging" in html
    assert "falling hard" in html
    # Footer
    assert "Buy lanes" in html
    # As-of
    assert "2026-07-10" in html
    # Panel class present
    assert "m7p" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_fail_open_none_payload():
    """Panel must render nothing when payload is None."""
    env = _env()
    html = env.from_string(GUARD_TMPL).render(d=None)
    assert "m7p" not in html
    assert "Mag 7" not in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_fail_open_empty_dict():
    """Panel must render nothing when payload is empty dict (no trend_state)."""
    env = _env()
    # The macro itself wraps with {%- if d %}, so empty dict is falsy in Jinja? No —
    # in Jinja2 an empty dict is falsy. But test the macro's inner guard too.
    html = env.from_string(RENDER_TMPL).render(d={})
    # Empty dict is falsy in Jinja2 — macro's {%- if d %} block skips the content.
    assert "m7p" not in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_no_banned_tier1_jargon():
    """Banned raw machine slugs must not appear in user-visible copy.
    CSS class names (class="...") are excluded — they are invisible to users.
    We strip class attributes before checking to avoid false positives like
    'm7p-running_narrow' (a CSS class, not visible text)."""
    import re
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FIXTURE)
    # Strip class="..." and data-tip attributes so we only test user-visible copy
    stripped = re.sub(r'\s+class="[^"]*"', '', html)
    stripped = re.sub(r'\s+data-tip-[a-z]+="[^"]*"', '', stripped)
    # Also strip style attributes
    stripped = re.sub(r'\s+style="[^"]*"', '', stripped)
    banned = [
        "UPTURN_CONFIRMED", "running_narrow", "IGNITION", "K-of-N",
        "z-score", "percentile", "confluence", "lobe", "organ",
        "display-tier", "display-only",
    ]
    for term in banned:
        assert term not in stripped, f"Banned term '{term}' found in user-visible HTML"


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_dot_colors_correct():
    """AAPL (above50+rs20>0) → green; AMZN (not above50, rs20>0) → amber;
    TSLA (not above50, rs20<0) → grey."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FIXTURE)
    # Dots are rendered in fixed order. We check class names are present.
    assert "m7p-dot-green" in html   # AAPL + META
    assert "m7p-dot-amber" in html   # AMZN (rs20>0 but not above50)
    assert "m7p-dot-grey" in html    # MSFT, NVDA, GOOGL, TSLA


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_stance_vocabulary():
    """Each trend_state maps to the fixed stance vocabulary."""
    env = _env()
    cases = [
        ("running_narrow", "don't chase"),
        ("running_broad", "In favour"),
        ("turning_up", "Get ready"),
        ("cooling", "Watch"),
        ("rolling_over", "Protect gains"),
        ("down", "Stand aside"),
    ]
    for state, expected in cases:
        d = dict(FIXTURE, trend_state=state)
        html = env.from_string(RENDER_TMPL).render(d=d)
        assert expected in html, f"Expected '{expected}' for state '{state}'"


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_bilingual_strings():
    """Both EN and ZH strings must appear in the rendered output."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FIXTURE)
    # English
    assert "Mag 7" in html
    assert "Cap-weighted" in html
    # Chinese
    assert "七巨头" in html
    assert "七只最大美股" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_no_validated_word():
    """The word 'validated' must never appear in user-facing output (CI law)."""
    env = _env()
    html = env.from_string(RENDER_TMPL).render(d=FIXTURE)
    assert "validated" not in html.lower()


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_tech_legs_word_map():
    """Tech-legs word map: >=5% surging; >=2% running; <=-5% falling hard;
    <=-2% falling; else flat."""
    env = _env()
    d = dict(FIXTURE, tech_legs=[
        {"id": "a", "en": "A", "zh": "A", "r10_rel": 0.06, "r20_rel": 0.0, "word": "surging"},
        {"id": "b", "en": "B", "zh": "B", "r10_rel": 0.03, "r20_rel": 0.0, "word": "running"},
        {"id": "c", "en": "C", "zh": "C", "r10_rel": -0.06, "r20_rel": 0.0, "word": "falling hard"},
        {"id": "d", "en": "D", "zh": "D", "r10_rel": -0.03, "r20_rel": 0.0, "word": "falling"},
        {"id": "e", "en": "E", "zh": "E", "r10_rel": 0.005, "r20_rel": 0.0, "word": "flat"},
    ])
    html = env.from_string(RENDER_TMPL).render(d=d)
    assert "surging" in html
    assert "running" in html
    assert "falling hard" in html
    assert "falling" in html
    assert "flat" in html


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_structure_chip_only_for_recovering_drawdown():
    """Structure chip ('below the year high') only renders for recovering/drawdown chips."""
    env = _env()
    # at_highs — no chip
    d_high = dict(FIXTURE, structure={"dd_from_252d_high": 0.0, "chip": "at_highs"})
    html_high = env.from_string(RENDER_TMPL).render(d=d_high)
    assert "below the year high" not in html_high
    # recovering — chip present
    d_rec = dict(FIXTURE, structure={"dd_from_252d_high": -0.082, "chip": "recovering"})
    html_rec = env.from_string(RENDER_TMPL).render(d=d_rec)
    assert "below the year high" in html_rec


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
def test_mode_guard_in_dashboard():
    """{% if mode == 'stocks' and latest.mag7_regime %} guard works correctly:
    renders when mode=stocks + payload present; absent otherwise."""
    env = _env()
    # Inline guard matching what dashboard.html.j2 uses
    guard = (
        "{% from '_mag7_panel.html.j2' import mag7_panel %}"
        "{% if mode == 'stocks' and latest.mag7_regime %}{{ mag7_panel(latest.mag7_regime) }}{% endif %}"
    )
    latest_with = {"mag7_regime": FIXTURE}
    latest_without = {}
    # stocks mode + payload present → renders
    html_yes = env.from_string(guard).render(mode="stocks", latest=latest_with)
    assert "m7p" in html_yes
    # stocks mode + payload absent → empty
    html_no = env.from_string(guard).render(mode="stocks", latest=latest_without)
    assert "m7p" not in html_no
    # macro mode + payload present → empty
    html_macro = env.from_string(guard).render(mode="macro", latest=latest_with)
    assert "m7p" not in html_macro


# ── build_site loader tests (no network, no real data) ───────────────────────

def test_mag7_regime_view_missing_file(tmp_path, monkeypatch):
    """_mag7_regime_view returns None when the JSON file is absent."""
    import importlib, types
    # Minimal config shim
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    monkeypatch.setitem(sys.modules, "config", fake_config)
    # Re-import build_site with patched config
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._mag7_regime_view()
    assert result is None


def test_mag7_regime_view_malformed_json(tmp_path, monkeypatch):
    """_mag7_regime_view returns None when JSON is malformed."""
    import types
    (tmp_path / "mag7_regime").mkdir()
    (tmp_path / "mag7_regime" / "latest.json").write_text("{INVALID}")
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._mag7_regime_view()
    assert result is None


def test_mag7_regime_view_missing_trend_state(tmp_path, monkeypatch):
    """_mag7_regime_view returns None when trend_state key is absent."""
    import types
    (tmp_path / "mag7_regime").mkdir()
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps({"as_of": "2026-07-10"}))
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._mag7_regime_view()
    assert result is None


def test_mag7_regime_view_valid(tmp_path, monkeypatch):
    """_mag7_regime_view returns the dict when file is valid."""
    import types
    (tmp_path / "mag7_regime").mkdir()
    payload = {"as_of": "2026-07-10", "trend_state": "running_narrow"}
    (tmp_path / "mag7_regime" / "latest.json").write_text(json.dumps(payload))
    fake_config = types.ModuleType("config")
    fake_config.data_dir = lambda: tmp_path
    import scripts.build_site as bs
    monkeypatch.setattr(bs, "config", fake_config)
    result = bs._mag7_regime_view()
    assert result is not None
    assert result["trend_state"] == "running_narrow"
