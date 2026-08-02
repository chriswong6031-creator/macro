"""Thematic flow detector (engine/group_flow.py) — DISPLAY-ONLY characterization layer.

The load-bearing invariants: it is NEVER scored (nothing in axes/regime/conditions reads
it), every group is directional=false (the unbiased Phase-0 verdict is display_only), the
one-name HHI guard catches single-stock mirages, the universe-bias cap keeps hindsight
baskets below clean sectors, and the AI-handoff payload carries the do-not-conclude
guardrails + caveats so a downstream inference layer cannot over-trust it."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import group_flow as gf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
CFG = gf._cfg({})


# ---- staging (no wrong-signed 'exhausted'; 'cooling' carries no exit call) ----
def test_stage_lifecycle_uses_cooling_not_exhausted():
    assert gf._stage(0.6, 0.5, 0.3, CFG) == "emerging"
    assert gf._stage(0.0, 0.85, 0.0, CFG) == "confirmed"
    assert gf._stage(-0.6, 0.6, -0.3, CFG) == "cooling"
    assert gf._stage(0.0, 0.5, 0.0, CFG) == "quiet"
    for args in [(0.6, 0.5, 0.3), (0.0, 0.85, 0.0), (-0.6, 0.6, -0.3), (0.0, 0.5, 0.0)]:
        assert gf._stage(*args, CFG) != "exhausted"


# ---- read-quality: universe cap + HHI one-name penalty ----
def test_read_quality_universe_cap_and_hhi_penalty():
    fp = {"breadth": 0.7, "cohesion": 0.4}
    sec = gf._read_quality(fp, 15, 1.0, False)
    bas = gf._read_quality(fp, 15, 0.55, False)
    assert bas < sec                                   # hindsight baskets capped below clean sectors
    narrow = gf._read_quality(fp, 15, 1.0, True)       # one name dominates
    assert narrow < sec
    assert 0.0 <= bas <= 1.0 and 0.0 <= sec <= 1.0


# ---- cluster map: real co-movement structure ----
def test_cluster_map_detects_comoving_cluster():
    idx = pd.bdate_range("2024-01-01", periods=120)
    rng = np.random.default_rng(0)
    common = rng.normal(0, 0.01, 120)
    levels = {}
    for g in ("A", "B", "C"):                          # co-moving cluster
        levels[g] = pd.Series((1 + (common + rng.normal(0, 0.002, 120))).cumprod(), index=idx)
    for g in ("D", "E"):                               # independent
        levels[g] = pd.Series((1 + rng.normal(0, 0.01, 120)).cumprod(), index=idx)
    cl = gf._cluster_map(levels, CFG)
    assert cl is not None
    assert 0.0 < cl["absorption"] <= 1.0
    assert cl["regime"] in ("concentrated", "mixed", "broad")
    assert set(cl["top_pair"]) <= {"A", "B", "C"}      # the tightest pair is inside the cluster


# ---- leadership: HHI flags a one-name mirage ----
def test_leadership_hhi_guard_flags_one_name():
    idx = pd.bdate_range("2024-01-01", periods=30)
    flat = np.ones(30)
    df = pd.DataFrame({f"N{i}": flat * (1 + 0.0001 * i) for i in range(6)}, index=idx)
    moon = flat.copy(); moon[-1] = 2.0                 # one name doubles -> mirage
    df["MOON"] = moon
    lead = gf._leadership(df, {}, {"MOON": ("Moonshot", "")})
    assert lead["top"][0]["ticker"] == "MOON"
    assert lead["breadth"] == "narrow" and lead["hhi"] > 0.5


# ---- AI handoff: guardrails + caveats travel ----
def test_ai_handoff_carries_guardrails():
    meta = {"verdict": "display_only", "cohesion_caveats": ["c1", "c2"],
            "residual_risks": ["r1"], "cohesion_gate": {"tier": "low"},
            "survivorship_gap_20d": {"flow_score": 0.09}}
    h = gf._ai_handoff(meta, {"elevated": False})
    assert h["overall_verdict"] == "display_only"
    assert isinstance(h["do_not_conclude"], list) and len(h["do_not_conclude"]) >= 3
    assert "directional" in h["ai_directive"].lower()
    assert h["caveats"] == ["c1", "c2"] and h["residual_risks"] == ["r1"]


# ---- integration on the real cache (skips if data absent) ----
def test_compute_group_flows_is_display_only_and_structured():
    p = gf.compute_group_flows()
    if p is None:
        import pytest
        pytest.skip("no equity cache in this checkout")
    assert p["verdict"] == "display_only" and p["calibrated"] is False
    assert p["sectors"] and p["baskets"] and p["ai_handoff"]
    assert "groups" not in p                           # no combined cross-universe ranking ships
    assert isinstance(p["emerging"], dict) and set(p["emerging"]) == {"sectors", "baskets"}
    for g in p["sectors"] + p["baskets"]:
        assert g["directional"] is False              # never a forecast
        assert g["directional_confidence"] == "low"
        assert 0.0 <= g["read_quality"] <= 1.0
        assert g["type"] in ("sector", "basket")
        assert "cohesion_gate" in g and "leadership" in g
    # sector read-quality should not be capped below baskets by construction
    assert max(g["read_quality"] for g in p["sectors"]) >= max(g["read_quality"] for g in p["baskets"])


# ---- the validated-honest metadata (skips if not generated) ----
def test_validation_meta_is_honest():
    from lib import config
    mp = config.data_dir() / "group_flow" / "validation_meta.json"
    if not mp.exists():
        import pytest
        pytest.skip("validation_meta.json not generated")
    import json
    m = json.loads(mp.read_text())
    assert m["verdict"] == "display_only"
    assert all(w == 0.0 for w in m["forecast_weights"].values())   # NO leg earns a forecast weight
    assert m["cohesion_gate"]["use"] == "context_gate"
    assert m["calibrated"] is False and len(m["cohesion_caveats"]) >= 5


# ---- DISPLAY-ONLY invariant: the scoring path must not import the detector ----
def test_never_scored_invariant():
    for mod in ("engine/axes.py", "engine/regime.py", "engine/conditions.py"):
        assert "group_flow" not in (ROOT / mod).read_text(), f"{mod} must not import group_flow"


# ---- the baskets.html.j2 money-flow surface ----
#
# These render the REAL template end-to-end.  The previous version sliced a fragment
# out of the template SOURCE on literal `{% if flow %}` .. `<div id="content">`
# offsets; #3282 (Rotation Map revamp, 2026-07-24) rebuilt the standalone "Flow lens"
# card into the Money-flow tile under "Under the hood", `{% if flow %}` stopped
# existing, and the slice raised ValueError from that day on — unnoticed, because no
# CI job named this suite.  A full render cannot rot the same way: it has no literal
# offsets to miss, and a template that stops rendering fails here with the real Jinja
# error instead of a substring-not-found from the harness.
def _render_baskets(flow=None):
    from jinja2 import Environment, FileSystemLoader, Undefined
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True,
                      undefined=Undefined)
    ctx = {"basket_member_syms": []}
    if flow is not None:
        ctx["flow"] = flow
    return env.get_template("sector_central.html.j2").render(**ctx)


def _money_flow_card(html):
    """Slice the Money-flow tile out of the RENDERED page.

    Anchored on `mf-etf-chips`/`mf-vol-chip` — element ids the page's own JS calls
    getElementById() on — so renaming them breaks the visible card too, instead of
    silently rotting this guard the way the old source-offset slice did.
    """
    end = html.index('id="mf-vol-chip"')
    return html[html.rindex('<div class="rvx-gcard"', 0, end): end]


# The page reads only flow.cluster.regime today; the rest mirrors a real
# engine/group_flow.py payload so the fixture stays recognisable.
_SYNTH_FLOW = {
    "verdict": "display_only",
    "regime": {"vix": 16.0, "pctile": 0.32, "elevated": False},
    "cluster": {"absorption": 0.52, "regime": "concentrated",
                "dominant_cluster": ["Industrials", "Financials"],
                "top_pair": ["Industrials", "Financials"], "top_pair_corr": 0.81},
    "sectors": [{"name": "Industrials", "name_zh": "工业", "stage": "emerging",
                 "read_quality": 0.7, "leadership": {"breadth": "broad"},
                 "cohesion_gate": {"stress_conditional": False}}],
    "baskets": [{"name": "Retail", "name_zh": "零售", "stage": "emerging",
                 "read_quality": 0.35, "leadership": {"breadth": "narrow"},
                 "cohesion_gate": {"stress_conditional": False}}],
    "groups": [],
}


def test_money_flow_card_renders_bilingually():
    card = _money_flow_card(_render_baskets(_SYNTH_FLOW))
    assert "Money flow" in card and "资金流向" in card             # label, both languages
    assert "Crowding into a few" in card and "向少数板块集中" in card  # the regime verdict


@pytest.mark.parametrize("regime, en, zh", [
    ("concentrated", "Crowding into a few", "向少数板块集中"),
    ("broad",        "Spread across many",  "广泛分布"),
    ("mixed",        "No single group leads", "暂无单一板块主导"),
    ("bogus",        "No single group leads", "暂无单一板块主导"),  # unknown -> neutral default
])
def test_money_flow_verdict_is_plain_and_never_directional(regime, en, zh):
    """Display-only: the card says WHERE money is, never what to do about it."""
    flow = {**_SYNTH_FLOW, "cluster": {**_SYNTH_FLOW["cluster"], "regime": regime}}
    card = _money_flow_card(_render_baskets(flow))
    assert en in card and zh in card
    # Scan the visible copy, not the markup — `justify-content:center` is not a verb.
    text = re.sub(r"<[^>]+>", " ", card).lower()
    for verb in ("buy", "sell", "accumulate", "enter", "exit", "trim",
                 "forecast", "target", "will"):
        assert not re.search(rf"\b{verb}\b", text), \
            f"directional/forecast word {verb!r} in display-only card copy: {text.strip()!r}"


@pytest.mark.parametrize("flow", [
    None,                                   # key absent from the context entirely
    {},                                     # present but empty
    {"verdict": "display_only"},            # payload with no cluster leg
    {"verdict": "display_only", "cluster": None},
])
def test_money_flow_card_degrades_without_a_cluster(flow):
    card = _money_flow_card(_render_baskets(flow))
    assert "Money flow" in card and "—" in card        # placeholder, not a crash
    for en in ("Crowding into a few", "Spread across many", "No single group leads"):
        assert en not in card                          # and no invented verdict


@pytest.mark.parametrize("flow", [None, _SYNTH_FLOW])
def test_baskets_page_renders_with_no_unrendered_jinja(flow):
    html = _render_baskets(flow)
    assert "{{" not in html and "{%" not in html
