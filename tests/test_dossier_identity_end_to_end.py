"""End-to-end acceptance for the US stock dossier identity/truth boundary.

Drives the REAL context builder and the REAL Jinja template with the exact inputs
that produced the four published defects, then asserts on the rendered HTML and
runs the estate guard over it. The unit tests elsewhere pin each mechanism; this
file pins the OUTCOME a reader would see, which is what actually regressed:

  RWT  a mortgage REIT whose dossier described a restaurant in Portland, showed
       "—" for a sector the stock hub printed as Real Estate on the same day, and
       carried a peer rail of six unrelated companies, four of them "$nanM".
  RMD  an issuer named "ResMed|" in <title>, meta description, OpenGraph, the
       JSON-LD Corporation.name and the visible identity.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.build_ticker_pages import build_page_context  # noqa: E402
from scripts.check_stock_dossier_integrity import (  # noqa: E402
    check_identity,
    check_machine_sentinel,
    load_canonical_universe,
    prepare_checkable_text,
)


def _factors_row(ticker, name, sector, cap):
    return {"ticker": ticker, "name": name, "sector": sector, "mktcap_bn": cap}


def _agg(factors_map):
    """The aggregate maps build_page_context reads. Empty where irrelevant."""
    return {
        "factor_betas": {}, "factors_map": factors_map, "tech_screener": {},
        "member_ctx_map": {}, "member_ctx_as_of": "", "baskets_map": {},
        "intel_map": {}, "news_map": {}, "alt_map": {}, "spy_bars": [],
        "earnings_map": {}, "brief_map": {},
    }


# The real factor table shape that broke RWT: engine/factor_exposure writes
# ("<ticker>", "—") for any symbol missing from its name/sector map, and 30 symbols
# carried that sentinel together, most with a NaN market cap.
_FACTORS = {
    "RWT": _factors_row("RWT", "RWT", "—", float("nan")),
    "ARI": _factors_row("ARI", "ARI", "—", float("nan")),
    "AVB": _factors_row("AVB", "AVB", "—", 25.78),
    "AVNS": _factors_row("AVNS", "AVNS", "—", float("nan")),
    "BRBR": _factors_row("BRBR", "BRBR", "—", float("nan")),
    "CABO": _factors_row("CABO", "CABO", "—", 0.158),
    "CLB": _factors_row("CLB", "CLB", "—", float("nan")),
    # genuine Real Estate names, the peers a Real Estate target should get
    "CUZ": _factors_row("CUZ", "Cousins Properties", "Real Estate", 5.0),
    "EPR": _factors_row("EPR", "EPR Properties", "Real Estate", 5.1),
    "SKT": _factors_row("SKT", "Tanger Factory Outlet Centers, Inc.", "Real Estate", 4.4),
}


def _ctx(ticker, name, sector, profile, factors=None):
    per = {"blob": {"profile": dict(profile), "tech": {"price": 4.77}}}
    return build_page_context(
        ticker, name, sector, per, _agg(factors if factors is not None else _FACTORS),
        "2026-08-19T12:00:00Z",
    )


@pytest.fixture(scope="module")
def template():
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    return env.get_template("ticker.html.j2")


# --- RWT ---------------------------------------------------------------------

def test_rwt_keeps_the_sector_the_hub_knows():
    """The coverage universe knows Real Estate; the narrower profile plane carries
    the "—" sentinel. The known fact must survive."""
    ctx = _ctx("RWT", "Redwood Trust Inc", "Real Estate", {"sector": "—"})
    assert ctx["sector"] == "Real Estate"
    assert ctx["identity"]["sector"] == "Real Estate"
    assert ctx["identity"]["sector_conflict"] == ""


def test_rwt_peer_rail_is_same_sector_and_finite():
    ctx = _ctx("RWT", "Redwood Trust Inc", "Real Estate", {"sector": "—"})
    peers = ctx["peers"] or []
    assert peers, "a Real Estate target with real Real Estate peers must get a rail"
    got = {p["ticker"] for p in peers}
    assert got <= {"CUZ", "EPR", "SKT"}, f"non-Real-Estate peers leaked: {got}"
    for p in peers:
        assert "nan" not in p["mktcap"].lower()
        assert p["mktcap"], "a peer card claiming size must carry a finite one"


def test_rwt_publishes_no_description_when_none_survived_resolution():
    """A withheld description is the CORRECT fail-closed outcome — and the page
    must then assert no provenance rather than a naked string."""
    ctx = _ctx("RWT", "Redwood Trust Inc", "Real Estate",
               {"sector": "—", "description": None})
    assert ctx["identity"]["desc_provenance"] == ""
    assert not (ctx["meta"].get("desc_trunc") or "")


def test_rwt_renders_without_the_restaurant_or_nan(template):
    ctx = _ctx("RWT", "Redwood Trust Inc", "Real Estate",
               {"sector": "—", "description": None})
    html = template.render(**ctx)
    assert "restaurant" not in html.lower()
    assert "Portland" not in html
    assert "$nanM" not in html and "$nan" not in html
    assert 'content="Real Estate"' in html
    text = prepare_checkable_text(html)
    assert check_machine_sentinel(Path("RWT.html"), text, {}) == []


def test_rwt_agrees_with_the_hub_end_to_end(tmp_path, template):
    """The user journey the defect broke: /stocks/index.html -> /stocks/RWT.html
    must show the same company and the same sector."""
    hub = tmp_path / "index.html"
    hub.write_text(
        '<script>const R=[["RWT", "Redwood Trust Inc", "Real Estate", 4.77]];</script>',
        encoding="utf-8")
    ctx = _ctx("RWT", "Redwood Trust Inc", "Real Estate",
               {"sector": "—", "description": None})
    html = template.render(**ctx)
    guard_ctx = {"universe": load_canonical_universe(hub)}
    assert check_identity(Path("RWT.html"), prepare_checkable_text(html), guard_ctx) == []


def test_rwt_with_a_resolved_description_carries_provenance(template):
    """When a description IS independently resolvable it ships with its receipt:
    which article was accepted, how strongly, under which resolver version."""
    ctx = _ctx("RWT", "Redwood Trust Inc", "Real Estate", {
        "sector": "—",
        "description": "Redwood Trust, Inc. is a specialty finance company and REIT.",
        "wiki_title": "Redwood Trust",
        "desc_strength": "exact",
        "desc_resolver_version": 2,
        "desc_fetched_at": "2026-08-19T12:00:00+00:00",
    })
    prov = ctx["identity"]["desc_provenance"]
    assert prov.startswith("wikipedia:Redwood Trust:exact:v2:")
    html = template.render(**ctx)
    assert 'name="mm:desc-provenance"' in html
    assert "restaurant" not in html.lower()


def test_a_description_without_linkage_is_marked_incomplete_and_refused(template):
    """The provenance contract: a naked description string is not publishable."""
    ctx = _ctx("RWT", "Redwood Trust Inc", "Real Estate",
               {"sector": "—", "description": "Some blurb with no recorded source."})
    assert ctx["identity"]["desc_provenance"] == "incomplete"
    html = template.render(**ctx)
    found = check_identity(Path("RWT.html"), prepare_checkable_text(html),
                           {"universe": {}})
    assert "description-provenance-missing" in {v["pattern"] for v in found}


# --- RMD ---------------------------------------------------------------------

def test_rmd_issuer_name_is_clean_across_every_identity_surface(template):
    """The sanitised name reaches <title>, meta description, OpenGraph, JSON-LD
    Corporation.name and the visible identity with no trailing pipe."""
    ctx = _ctx("RMD", "ResMed", "Health Care",
               {"sector": "Health Care", "description": None},
               factors={"RMD": _factors_row("RMD", "ResMed", "Health Care", 33.1)})
    html = template.render(**ctx)
    assert "ResMed|" not in html
    assert "ResMed" in html
    title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
    # the ISSUER segment of the title — "RMD — <issuer>: …". The " | MastermindX"
    # suffix is the site-name separator and is part of the title format.
    issuer_seg = title.split("—", 1)[1].split(":", 1)[0]
    assert "|" not in issuer_seg, f"residue in title issuer segment: {issuer_seg!r}"
    for pat in (r'<meta name="description" content="([^"]*)"',
                r'<meta property="og:title" content="([^"]*)"',
                r'<meta property="og:description" content="([^"]*)"'):
        m = re.search(pat, html)
        assert m and "ResMed|" not in m.group(1), f"residue survived in {pat}"
    assert "ResMed|" not in (ctx["meta"].get("jsonld_str") or "")


def test_rmd_residue_would_be_caught_if_it_ever_returned(template):
    """The guard must FAIL a page carrying the residue — otherwise this whole
    class could regress silently again."""
    ctx = _ctx("RMD", "ResMed|", "Health Care", {"sector": "Health Care"},
               factors={"RMD": _factors_row("RMD", "ResMed|", "Health Care", 33.1)})
    html = template.render(**ctx)
    found = check_identity(Path("RMD.html"), prepare_checkable_text(html),
                           {"universe": {"RMD": {"name": "ResMed", "sector": "Health Care"}}})
    assert "issuer-name-residue" in {v["pattern"] for v in found}


# --- estate-wide invariants ---------------------------------------------------

def test_target_without_a_canonical_sector_gets_no_peer_rail(template):
    """Missing peers are acceptable; six unrelated companies labelled Peers are not."""
    ctx = _ctx("RWT", "Redwood Trust Inc", "", {"sector": "—"})
    assert ctx["peers"] is None
    html = template.render(**ctx)
    for wrong in ("AVNS", "BRBR", "CABO", "CLB"):
        assert f">{wrong}<" not in html
    assert "$nanM" not in html


def test_conflicting_sector_sources_are_recorded_not_silently_resolved():
    ctx = _ctx("RWT", "Redwood Trust Inc", "Real Estate", {"sector": "Energy"})
    assert ctx["identity"]["sector"] == "Real Estate"       # canonical plane wins
    assert ctx["identity"]["sector_conflict"] == "Real Estate vs Energy"
