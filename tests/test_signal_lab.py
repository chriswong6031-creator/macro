"""Signal Lab — the consolidated honest validation scorecard (engine/signal_lab.py)
+ the signal_lab.html.j2 page render. The page's whole value is honesty, so these
tests guard the structure, the source-citation discipline, and the load-bearing
honest negatives (no cross-sectional factor survives FDR; the graveyard is shown).
"""
from __future__ import annotations

from jinja2 import Environment, FileSystemLoader

from engine import i18n, signal_lab
from lib import config

TIER_KEYS = {"scored", "confirmer", "display", "killed", "pending"}


def _payload():
    return signal_lab.build_scorecard()


def test_scorecard_shape_and_summary_consistency():
    p = _payload()
    assert set(t["key"] for t in p["tiers"]) <= TIER_KEYS
    s = p["summary"]
    # summary per-tier counts add up to the registry total
    assert sum(s[k] for k in ("scored", "confirmer", "display", "killed", "pending")) == s["total"]
    # and they match the grouped rows the template renders
    for tier in p["tiers"]:
        assert tier["count"] == len(tier["rows"]) == s[tier["key"]]


def test_every_row_is_cited_and_well_formed():
    p = _payload()
    for tier in p["tiers"]:
        for r in tier["rows"]:
            assert r["name"] and r["name_zh"], "row needs bilingual name"
            assert r["why"] and r["why_zh"], "row needs a bilingual rationale"
            assert r["source"], f"{r['name']} has no source citation"
            assert r["tier"] in TIER_KEYS
            assert r["market"]


def test_the_graveyard_is_shown():
    """The differentiator: we publish the signals we measured and refused to ship."""
    p = _payload()
    killed = next((t for t in p["tiers"] if t["key"] == "killed"), None)
    assert killed and killed["count"] >= 5
    names = " ".join(r["name"] for r in killed["rows"]).lower()
    for must in ("rvol", "base", "gbt", "carry"):
        assert must in names, f"expected a killed signal mentioning {must!r}"


def test_factor_cross_section_is_leak_free_and_honest():
    """The centerpiece: the 11-factor PIT cross-section, with NONE surviving FDR."""
    p = _payload()
    fr = p["factor_rows"]
    assert len(fr) == 11
    assert p["summary"]["factor_total"] == 11
    # honest negative — the cost of refusing to look ahead
    assert p["summary"]["factor_survivors"] == 0
    assert all(not r["survives"] for r in fr)
    # rows are sorted by IC descending (failing "leaders" on top)
    ics = [r["ic"] for r in fr if r["ic"] is not None]
    assert ics == sorted(ics, reverse=True)
    assert p["factor_meta"].get("leak_free") is True


def test_insider_is_the_lone_fdr_survivor_but_only_a_confirmer():
    """The one cross-sectional stock factor that survives FDR is gated as a
    confirmer (DSR borderline), never a standalone sizer."""
    p = _payload()
    conf = next(t for t in p["tiers"] if t["key"] == "confirmer")
    ins = next((r for r in conf["rows"] if "insider" in r["name"].lower()), None)
    assert ins is not None
    assert ins["fdr_survivor"] is True
    assert ins["q_fdr"] is not None and ins["q_fdr"] < 0.10     # survives FDR
    assert ins["dsr"] is not None and ins["dsr"] < 0.90         # but DSR-borderline


def test_scored_tier_leads_with_the_spvector():
    p = _payload()
    scored = next(t for t in p["tiers"] if t["key"] == "scored")
    assert scored["count"] >= 1
    assert any(r["dsr"] is not None and r["dsr"] >= 0.90 for r in scored["rows"]), \
        "the scored tier should contain at least one DSR-passing object (the SP/Macro Vector)"


def test_page_renders_without_template_errors():
    env = Environment(loader=FileSystemLoader(config.ROOT / "templates"))
    env.filters["min"] = lambda seq: min(seq)
    env.globals.update(td=i18n.td, tr=i18n.tr, zip=zip)
    html = env.get_template("signal_lab.html.j2").render(**_payload())
    assert "Signal Lab" in html
    assert "{{" not in html and "{%" not in html        # no unrendered jinja
    assert "survive FDR" in html
    for pill in ("v-scored", "v-killed", "v-confirmer"):
        assert pill in html
    # the methodology + PIT data stamps are present (ChatGPT proposal #2)
    assert "Deflated Sharpe" in html
    assert "data span" in html
