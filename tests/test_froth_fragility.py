"""Tests for engine.froth_fragility — the DISPLAY-ONLY retail-euphoria + hidden-
distribution top-risk gauge.

Load-bearing invariants:
  • DISPLAY-ONLY firewall: the gauge never appears in any scored output (regime.classify
    / axes.score_axis) and is referenced by build_site / run only — never by a scoring
    engine. Young / display-only legs are HARD-ZEROED (weight 0, cannot move the score).
  • Never-raises on empty / malformed input (degrade-never-raise).
  • points SUM to each face score (no black box).
  • Forward-log roundtrip (append idempotent -> resolve -> track_record).
  • Template card renders, is bilingual, and is absent when the gauge is None.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import froth_fragility as ff  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
_LATEST = ROOT / "data" / "regime" / "latest.json"

FROTH_KEYS = ("froth_fragility", "froth", "euphoria", "fragility", "ff_score", "leaddist")


def _real_latest() -> dict:
    if not _LATEST.exists():
        pytest.skip("data/regime/latest.json not present")
    return json.loads(_LATEST.read_text())


# --------------------------------------------------------------------------- #
# Never-raises contract
# --------------------------------------------------------------------------- #
def test_empty_and_none_inputs():
    assert ff.snapshot(None) is None
    assert ff.snapshot({}) is None
    assert ff.snapshot([]) is None  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [
    {"date": "x", "cross_asset": "not-a-dict"},
    {"date": "x", "cross_asset": {"absorption_pctile_5y": "oops"}},
    {"date": "x", "conditions": {"risk_appetite": None, "complacency": []}},
    {"date": "x", "conditions": "broken"},
])
def test_never_raises_on_malformed(bad):
    snap = ff.snapshot(bad)
    assert snap is None or isinstance(snap, dict)


# --------------------------------------------------------------------------- #
# Real-data snapshot: schema + points invariant + display-only hard-zero
# --------------------------------------------------------------------------- #
def test_real_snapshot_schema():
    snap = ff.snapshot(_real_latest())
    assert snap is not None
    for k in ("asof", "headline", "band", "quadrant", "face_a", "face_b", "stealth",
              "alert", "provisional", "disclaimer"):
        assert k in snap, k
    assert snap["quadrant"] in ff._QUAD_LABELS
    if snap["headline"] is not None:
        assert 0 <= snap["headline"] <= 100
        assert snap["band"] in ("calm", "watch", "elevated", "high", "extreme")


def test_points_sum_to_face_score():
    snap = ff.snapshot(_real_latest())
    for face in ("face_a", "face_b"):
        legs = snap[face]["legs"]
        score = snap[face]["score"]
        if score is None:
            continue
        total = sum(l["points"] for l in legs if l.get("available") and l.get("points"))
        assert abs(total - score) <= 0.6, (face, total, score)


def test_display_only_legs_are_hard_zeroed():
    """Every young / context leg contributes EXACTLY 0 — weight 0, not available, no points.
    And the registry's display-only keys must all actually be RENDERED (no vacuous pass)."""
    snap = ff.snapshot(_real_latest())
    rendered = {l["key"] for face in ("face_a", "face_b") for l in snap[face]["legs"]}
    display_keys = {k for k, scored in ff._SCORED_LEGS.items() if not scored}
    assert display_keys <= rendered, display_keys - rendered   # every registered chip is shown
    for face in ("face_a", "face_b"):
        for l in snap[face]["legs"]:
            if l["key"] in display_keys:
                assert l["weight"] == 0.0, l["key"]
                assert l["available"] is False, l["key"]
                assert l["scored"] is False, l["key"]
                assert l["points"] is None, l["key"]


def test_scored_legs_registry_matches_doctrine():
    # young / unvalidated legs must NOT be scored
    for k in ("A1_putcall", "A2_naaim", "A3_news", "A5_rr", "A6_crypto",
              "B3_med_dd", "B5_rsp_spy", "B7_complacency"):
        assert ff._SCORED_LEGS[k] is False, k
    # the deep, regime-specific legs may score
    for k in ("A4_parab", "B_stealth", "B_leaddist", "B1_ad_div", "B2_pct200_div", "B4_absorption"):
        assert ff._SCORED_LEGS[k] is True, k


def test_dropping_cross_asset_renormalizes():
    latest = _real_latest()
    latest.pop("cross_asset", None)          # removes the B4 absorption leg input
    snap = ff.snapshot(latest)
    assert snap is not None
    b4 = next((l for l in snap["face_b"]["legs"] if l["key"] == "B4_absorption"), None)
    assert b4 is not None and b4["available"] is False
    if snap["face_b"]["score"] is not None:
        total = sum(l["points"] for l in snap["face_b"]["legs"] if l.get("available") and l.get("points"))
        assert abs(total - snap["face_b"]["score"]) <= 0.6


# --------------------------------------------------------------------------- #
# Pure helpers (no disk)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("x,band", [
    (0, "calm"), (54.9, "calm"), (55, "watch"), (67.9, "watch"), (68, "elevated"),
    (77.9, "elevated"), (78, "high"), (87.9, "high"), (88, "extreme"), (100, "extreme"),
])
def test_band_cutoffs(x, band):
    assert ff._band(x)[0] == band


def test_band_none():
    assert ff._band(None) == (None, None)


def test_headline_soft_and_geometric_mean():
    st = {"stealth_fire": False, "gated": True}
    assert ff._headline_scalar(100.0, 0.0, st) == 0.0          # AND-logic: a zero face kills it
    assert abs(ff._headline_scalar(64.0, 64.0, st) - 64.0) <= 0.1
    # stealth floor recovers Face B when the stealth core fires
    st_fire = {"stealth_fire": True, "gated": True}
    assert ff._headline_scalar(40.0, 70.0, st_fire) == 70.0


def test_quadrant_logic():
    gate = {"gated": True, "stealth_fire": False}
    assert ff._quadrant(80, 80, gate) == "euphoric_fragile"
    assert ff._quadrant(80, 30, gate) == "euphoric_extended"
    assert ff._quadrant(80, 30, gate, leaders_dist=True) == "narrowing_top"
    # leadership distribution under a pinned index fires narrowing_top even when euphoria
    # has COOLED (low Face A) — the cooled-but-distributing regime must still register
    assert ff._quadrant(40, 30, gate, leaders_dist=True) == "narrowing_top"
    assert ff._quadrant(30, 80, gate) == "visible_stress"
    assert ff._quadrant(30, 30, gate) == "benign"
    # no gate (index already broken) + leaders_dist must NOT read as a stealth narrowing top
    assert ff._quadrant(40, 30, {"gated": False, "stealth_fire": False}, leaders_dist=True) == "benign"
    primed = {"gated": True, "stealth_fire": True}
    assert ff._quadrant(60, 40, primed) == "stealth_primed"


def test_renorm_stealth_skips_unavailable():
    legs = [
        {"available": True, "weight": 0.25, "lit": True},
        {"available": True, "weight": 0.25, "lit": False},
        {"available": False, "weight": 0.20, "lit": False},   # missing data -> drops out
        {"available": True, "weight": 0.20, "lit": False},
        {"available": True, "weight": 0.10, "lit": False},
    ]
    score, n_avail = ff._renorm_stealth(legs)
    assert n_avail == 4                                        # the unavailable leg is excluded
    # 0.25 lit / (0.25+0.25+0.20+0.10)=0.80 available weight -> 31.2, NOT 25 (which would
    # wrongly count the unavailable leg's weight in the denominator)
    assert abs(score - 31.2) < 0.5
    assert ff._renorm_stealth([{"available": False, "weight": 0.5, "lit": True}]) == (None, 0)


# --------------------------------------------------------------------------- #
# DISPLAY-ONLY firewall (load-bearing)
# --------------------------------------------------------------------------- #
def _code_only(p: Path) -> str:
    """Source minus comments and docstrings (ast round-trip). Prose may CITE the design
    lineage (basket_breadth_divergence is a within-basket RE-IMPLEMENTATION of the Face-B
    mechanics — macro#860, no import); any CODE reference — an import, an attribute, or
    even a dynamic-import string literal (non-docstring strings survive unparse) — trips."""
    import ast
    tree = ast.parse(p.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body[0].value.value = ""
    return ast.unparse(tree)


def test_firewall_not_referenced_by_scoring_engines():
    """froth_fragility may be referenced ONLY by engine/run.py (wiring) and itself —
    never by any scoring engine. The view-helper lives only in build_site."""
    allowed = {"froth_fragility.py", "run.py"}
    for p in (ROOT / "engine").glob("*.py"):
        if p.name in allowed:
            continue
        src = _code_only(p)
        assert "froth_fragility" not in src, p.name
        assert "_froth_fragility_view" not in src, p.name
    assert "froth_fragility" in (ROOT / "engine" / "run.py").read_text()   # actually wired


def test_firewall_absent_from_scoring_sources():
    axes_src = (ROOT / "engine" / "axes.py").read_text()
    regime_src = (ROOT / "engine" / "regime.py").read_text()
    cond_src = (ROOT / "engine" / "conditions.py").read_text()
    mrs_region = cond_src[cond_src.index("def _macro_risk_legs"):]
    for src in (axes_src, regime_src, mrs_region):
        for k in FROTH_KEYS:
            assert k not in src


@pytest.fixture(scope="module")
def real_f():
    from engine.inputs import build_features
    return build_features()


def test_not_scored_in_classify(real_f):
    from engine import regime
    cols = list(regime.classify(real_f).columns)
    for k in FROTH_KEYS:
        assert not any(k in c for c in cols), k


def test_not_in_axes_scoring(real_f):
    from engine import axes
    for ax in ("growth", "inflation"):
        cols = list(axes.score_axis(real_f, ax).columns)
        for k in FROTH_KEYS:
            assert not any(k in c for c in cols), (ax, k)


# --------------------------------------------------------------------------- #
# Forward-outcome log roundtrip
# --------------------------------------------------------------------------- #
def _snap_for_log() -> dict:
    return {"asof": "2026-06-01", "headline": 72.0, "band": "elevated",
            "quadrant": "euphoric_fragile",
            "face_a": {"score": 80.0}, "face_b": {"score": 70.0},
            "stealth": {"score": 64.0, "gated": True}, "stealth_fire": True,
            "unwind_risk": False, "alert": True}


def test_append_log_idempotent(tmp_path):
    p = tmp_path / "log.jsonl"
    snap = _snap_for_log()
    assert ff.append_log(snap, {}, path=p) is True
    assert ff.append_log(snap, {}, path=p) is False     # one line per asof
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    assert len(rows) == 1
    assert rows[0]["outcome_label_en"] and rows[0]["graded"] is None


def test_resolve_hit_and_track_record(tmp_path):
    p = tmp_path / "log.jsonl"
    ff.append_log(_snap_for_log(), {}, path=p)
    dates = ["2026-06-01"] + [f"2026-06-{d:02d}" for d in range(2, 2 + 50)]  # >= h42 ahead
    qqq = {d: 100.0 for d in dates}
    qqq["2026-06-20"] = 90.0                              # -10% drawdown => HIT (<= -8%)
    n = ff.resolve(qqq, {}, {}, path=p)
    assert n == 1
    tr = ff.track_record(path=p)
    assert tr["n"] == 1 and tr["hit_rate"] == 1.0
    assert tr["by_quadrant"].get("euphoric_fragile", {}).get("hits") == 1
    assert tr["by_hit_type"].get("drawdown") == 1


def test_resolve_not_matured_skipped(tmp_path):
    p = tmp_path / "log.jsonl"
    ff.append_log(_snap_for_log(), {}, path=p)
    qqq = {"2026-06-01": 100.0, "2026-06-02": 100.0, "2026-06-03": 100.0}  # < h42
    assert ff.resolve(qqq, {}, {}, path=p) == 0
    assert ff.track_record(path=p)["n"] == 0


def test_track_record_empty():
    tr = ff.track_record(path=Path("/nonexistent/froth_log.jsonl"))
    assert tr["n"] == 0 and tr["hit_rate"] is None and tr["provisional"] is True


# --------------------------------------------------------------------------- #
# Template render smoke + bilingual + absent-when-none
# --------------------------------------------------------------------------- #
def _render_card(froth_fragility, fear_euphoria=None):
    """Render the v2 MX2 sentiment block (inside the RISK tray) of dashboard.html.j2.
    Slices on {# MX2-SENTIMENT-START #} / {# MX2-SENTIMENT-END #} markers (Fix 6 — v2 transition).
    Previously sliced between SENTIMENT REGIME / CROSS-ASSET MACRO HTML comments (#757 merge);
    now points at the v2 tray region which carries the same content."""
    from jinja2 import Environment, FileSystemLoader
    from engine import i18n
    src = (TEMPLATES / "dashboard.html.j2").read_text()
    macros = src[: src.index("{# coloured")]
    start = src.index("{# MX2-SENTIMENT-START #}")
    end = src.index("{# MX2-SENTIMENT-END #}")
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    # market_state must be truthy to enter the RISK tray gate ({% if market_state %})
    _min_ms = {"radar": {}, "components": [], "color": "green", "score": 55,
               "label_en": "Risk-on", "label_zh": "偏好", "asof": "2026-07-11",
               "headline_en": "Markets lean risk-on.", "headline_zh": "市场偏向风险偏好。",
               "overrides": [], "flip_en": None, "flip_zh": None, "mtf": None}
    return env.from_string(macros + src[start:end]).render(
        froth_fragility=froth_fragility, fear_euphoria=fear_euphoria,
        mode="macro", latest={"risk_radar": None, "fed_stance": None, "turning_point": None},
        market_state=_min_ms, fear_greed=None)


_FF_MIN = {
    "headline": 51.6, "band": "watch", "band_zh": "关注", "provisional": True,
    "quadrant": "narrowing_top",
    "quadrant_en": "Euphoric, leaders distributing under a held index — narrowing-top risk",
    "quadrant_zh": "欣喜，但龙头在被托住的指数下派发——顶部收窄风险",
    "face_a": {"score": 68.9, "legs": [
        {"key": "A4_parab", "label": "Semis/AI parabolicity", "label_zh": "半导体/AI 抛物广度",
         "sub": 68.9, "weight": 1.0, "available": True, "scored": True, "points": 68.9,
         "color": "#e0a030", "pill": None, "note": "10% of the semis/AI cohort parabolic"},
        {"key": "A1_putcall", "label": "Equity put/call froth", "label_zh": "看跌看涨",
         "sub": None, "weight": 0.0, "available": False, "scored": False, "points": None,
         "color": "#888", "pill": "accruing", "note": "young series, scored 0"}]},
    "face_b": {"score": 38.6, "legs": [
        {"key": "B_leaddist", "label": "Leadership distribution", "label_zh": "龙头派发",
         "sub": 73.6, "weight": 0.24, "available": True, "scored": True, "points": 17.7,
         "color": "#d04545", "pill": None, "note": "7/7 mega-cap leaders below 50dma"}]},
    "stealth": {"score": 25.0, "n_lit": 1, "gate_state": "armed", "stealth_fire": False,
                "vix_decomp": "avg leader vol ≈37% × √0.34 ⇒ leadership-index vol ~22%"},
    "stealth_fire": False, "unwind_risk": False,
    "provisional_note": "Face-B led; forward record accruing.",
    "track_record": {"n": 0, "hit_rate": None},
    "disclaimer": "Display-only / validation-accruing.", "disclaimer_zh": "仅供展示。",
}


def test_render_smoke_bilingual():
    # #659 deliberately slimmed the card to a signal-only read (the Face A/B meters +
    # per-leg table were dropped from the render; the backend still computes them) and
    # #757 merged it into the "Sentiment regime" panel — assert THAT card's contract.
    html = _render_card(_FF_MIN)
    assert 'id="sentiment-regime"' in html
    assert 'id="froth-fragility"' in html                            # gauge keeps its own anchor
    assert "Froth & Fragility" in html and "狂热与脆弱" in html       # title both langs
    assert "narrowing-top risk" in html and "顶部收窄风险" in html     # quadrant both langs
    assert "Euphoria" in html and "欣喜" in html                      # face-A read both langs
    assert "Fragility / distribution" in html and "脆弱／派发" in html # face-B read both langs
    assert "Watch" in html and "关注" in html                         # headline band both langs
    assert "provisional" in html and "暂定" in html                   # accrual badge both langs
    assert "accruing" in html and "积累中" in html                    # forward-record line both langs
    assert "sizing, not selection" in html and "而非选股" in html      # display-only doctrine both langs
    assert 'class="pos"' not in html and 'class="neg"' not in html   # euphoria not "good"/"bad"


def test_render_absent_when_none():
    html = _render_card(None)
    assert 'id="sentiment-regime"' not in html
    assert 'id="froth-fragility"' not in html
    assert "狂热与脆弱" not in html      # whole merged panel absent too
    # the sibling Fear↔Euphoria lens alone must NOT resurrect the froth section
    html = _render_card(None, fear_euphoria={"fe_score": 50, "band": "Neutral", "roro": None})
    assert 'id="sentiment-regime"' in html
    assert 'id="froth-fragility"' not in html
