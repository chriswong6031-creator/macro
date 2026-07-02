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


def test_intl_bridge_graveyard_is_published():
    """The intl graveyard is published like every other signal family. CONTEXT/INVERTED
    verdicts land in display, CONFIRMED-but-unwired legs (C3 breadth, C4a REER N=1) land in
    confirmer — each cited to its exact report, none wired into a score. W2 (C2): the
    macro-sleeve graded CONTEXT vs the US book (DSR 0.83 < the 0.90 door) → display. W3 (C4a):
    the REER N=1 resurrection graded CONFIRMED → moves pending→confirmer; W3 (C4c): the CNH
    basis graded INVERTED → display graveyard."""
    p = _payload()
    rows = [r for t in p["tiers"] for r in t["rows"]]
    intl = [r for r in rows if "intl_bridge/ledger.json" in r["source"]]
    assert len(intl) >= 5, "the intl bridge registry mirror should be published"
    blob = " ".join(r["name"] for r in intl).lower()
    for must in ("c2", "c4", "c3", "radar"):
        assert must in blob, f"expected an intl-bridge row mentioning {must!r}"
    # C2 now sits in DISPLAY (graveyard) — CONTEXT vs the US book, not scored
    display = next((t for t in p["tiers"] if t["key"] == "display"), None)
    assert display and any("C2" in r["name"] for r in display["rows"]), \
        "C2 macro-sleeve should be published in the display graveyard (CONTEXT verdict)"
    # W3-C4a: the REER N=1 resurrection graded CONFIRMED → it sits in CONFIRMER now, not pending
    confirmer = next((t for t in p["tiers"] if t["key"] == "confirmer"), None)
    assert confirmer and any("REER" in r["name"] for r in confirmer["rows"]), \
        "C4a REER N=1 should be published in the confirmer tier (CONFIRMED verdict)"
    # W3-C4c: the CNH basis graded INVERTED → it sits in the DISPLAY graveyard
    assert display and any("CNH" in r["name"] for r in display["rows"]), \
        "C4c CNH-basis should be published in the display graveyard (INVERTED verdict)"
    # nothing intl is wired into a score
    for r in intl:
        assert "not wired" in r["wired"] or "not shipped" in r["wired"] \
            or "display-only" in r["wired"]


def test_factor_cross_section_is_leak_free_and_data_driven():
    """The centerpiece: the leak-free PIT factor cross-section. Survivor count is
    read LIVE from ic_scorecard.json (so the page adapts to whichever branch's
    scorecard it sits on), and the survivors list is consistent with it."""
    p = _payload()
    fr = p["factor_rows"]
    assert len(fr) >= 9                                          # the factor panel is present
    assert p["summary"]["factor_total"] == len(fr)
    surv_rows = [r for r in fr if r["survives"]]
    assert p["summary"]["factor_survivors"] == len(surv_rows)
    assert {s["name"] for s in p["factor_survivors"]} == {r["name"] for r in surv_rows}
    # rows are sorted by IC descending (leaders on top)
    ics = [r["ic"] for r in fr if r["ic"] is not None]
    assert ics == sorted(ics, reverse=True)
    assert p["factor_meta"].get("leak_free") is True


def test_sue_demoted_after_deep_revalidation():
    """SUE survived FDR only on the shallow 2023-2025 window; a deep 2011-2026
    re-validation (survivorship-optimistic) collapsed the edge to ~zero (IC 0.0005,
    t 0.06), so it is DEMOTED out of the scored tier and shown as display with the
    deep-kill caveat (see reports/sue-deep-history-phase0.md)."""
    p = _payload()
    scored = next(t for t in p["tiers"] if t["key"] == "scored")
    assert not any("SUE" in r["name"] for r in scored["rows"]), "SUE should no longer be scored"
    disp = next(t for t in p["tiers"] if t["key"] == "display")
    sue = next((r for r in disp["rows"] if "SUE" in r["name"]), None)
    assert sue is not None, "SUE should remain shown as display (deep-killed), not deleted"
    blob = (sue["why"] + " " + " ".join(v for _, v in sue["extra"])).lower()
    assert "deep" in blob and "0.0005" in blob                 # the deep-kill caveat is present
    # SUE itself is not left pending (it is display-demoted). The pending tier, when present,
    # holds the intl-bridge validated-but-unwired entries (W1) — not SUE.
    pending = next((t for t in p["tiers"] if t["key"] == "pending"), None)
    if pending:
        assert not any("SUE" in r["name"] for r in pending["rows"])


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
