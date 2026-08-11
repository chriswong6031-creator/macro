"""Executable guards for the TOP ANATOMY W1 surface design freeze.

Authored (PR #5267) while the template was still INERT — no builder, no nav row,
no pipeline slot — so the guards below render it through a standalone Jinja
environment of the test's own making. That standalone render is still the freeze
and is kept verbatim: the design must survive on its own terms, independent of
whatever wires it.

The surface is no longer inert. `scripts/build_winner_health_page.py` renders it
from `data/top_maturation/latest.json`, `templates/_navlinks.html.j2` carries its
row, and `config/dag.yml` / `.github/workflows/daily.yml` schedule it (their
parity is `tests/test_dag_conformance.py`'s job, not this file's). A freeze that
only ever ran in a harness the production path does not use would be a freeze on
nobody's page, so the same two invariants are re-asserted through the real
builder below, and the wiring itself is pinned so the surface cannot silently go
dark again.
"""
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, Undefined


ROOT = Path(__file__).resolve().parent.parent


def _template():
    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=True,
        undefined=Undefined,
    )
    # Shared chrome calls these globals. The production builder wires the real
    # `engine.i18n` implementations; this standalone design harness needs only
    # parity, and deliberately keeps no dependency on the builder so the freeze
    # still fails loudly if the TEMPLATE regresses while the wiring is healthy.
    env.globals.update(td=lambda x, *a, **k: x, tr=lambda x, *a, **k: x)
    return env.get_template("winner_health.html.j2")


def _row(**overrides):
    row = {
        "ticker": "TEST", "name": "Test Corp", "r126": 0.62,
        "spark": [10.0, 11.0, 10.5], "episode_high": 12.0,
        "legs": [], "analog": None,
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize("wh", [
    None,
    {"null_state": True},
    {"null_state": False, "states": {}},
    {"null_state": False, "universe_n": 100, "states": {
        "extended_healthy": [_row()], "extended_watch": [],
        "thinning": [], "breaking": []}},
    {"null_state": False, "states": {"extended_watch": [
        _row(spark=[10.0, 11.0], analog={"n": 4, "track": "W"})]}},
])
def test_design_freeze_renders_board_and_honest_null_fixtures(wh):
    html = _template().render(wh=wh) if wh is not None else _template().render()
    assert "Winner Health" in html
    assert "winner_health.v1" not in html  # schema mechanics stay out of Tier 1


def test_optional_row_number_renders_an_honest_dash_not_fake_zero():
    wh = {"null_state": False, "states": {"extended_healthy": [{"ticker": "NULL"}]}}
    html = _template().render(wh=wh)
    assert "NULL" in html
    assert '<span class="fig">—</span>' in html
    assert '<span class="fig">+0%</span>' not in html


# ══════════════════════════════════════════════════════════════════════════════
# the freeze, re-asserted on the WIRED path
#
# The harness above builds its own environment. The production one is built by
# `scripts/build_winner_health_page.py` — different globals (real `engine.i18n`),
# different loader root, and a fail-open artifact loader in front of it. Both
# invariants have to survive THAT path too, or the freeze is guarding a render
# no reader ever gets.
# ══════════════════════════════════════════════════════════════════════════════
def _render_via_builder(tmp_path, wh):
    import json
    import sys

    sys.path.insert(0, str(ROOT))
    from scripts import build_winner_health_page as bwh  # noqa: PLC0415

    if wh is None:
        # No artifact at all — the builder's own honest-null path, which is the
        # production equivalent of rendering with `wh` undefined.
        return bwh.render(ROOT, fixture=tmp_path / "absent.json")
    p = tmp_path / "wh.json"
    p.write_text(json.dumps(wh, ensure_ascii=False), encoding="utf-8")
    return bwh.render(ROOT, fixture=p)


@pytest.mark.parametrize("wh", [
    None,
    {"null_state": True},
    {"null_state": False, "states": {}},
    {"null_state": False, "universe_n": 100, "states": {
        "extended_healthy": [_row()], "extended_watch": [],
        "thinning": [], "breaking": []}},
    {"null_state": False, "states": {"extended_watch": [
        _row(spark=[10.0, 11.0], analog={"n": 4, "track": "W"})]}},
])
def test_design_freeze_holds_through_the_production_builder(tmp_path, wh):
    html = _render_via_builder(tmp_path, wh)
    assert "Winner Health" in html
    assert "winner_health.v1" not in html  # schema mechanics stay out of Tier 1


def test_honest_dash_survives_the_production_builder(tmp_path):
    wh = {"null_state": False, "states": {"extended_healthy": [{"ticker": "NULL"}]}}
    html = _render_via_builder(tmp_path, wh)
    assert "NULL" in html
    assert '<span class="fig">—</span>' in html
    assert '<span class="fig">+0%</span>' not in html


def test_the_surface_is_wired_and_not_inert():
    """The template is referenced by a builder and reachable from the shared nav.

    Pins the transition out of the inert state this file was written against: an
    unreferenced template renders green here forever while shipping to nobody.
    """
    builder = ROOT / "scripts" / "build_winner_health_page.py"
    assert builder.exists(), "no page builder — the surface is inert again"
    assert "winner_health.html.j2" in builder.read_text(encoding="utf-8")

    # Product pages carry ONE global header family; the row lives in its shared
    # inventory, never in a page-local header (CLAUDE.md navigation law).
    navlinks = (ROOT / "templates" / "_navlinks.html.j2").read_text(encoding="utf-8")
    assert "winner_health.html" in navlinks, "surface is unreachable from the product nav"
