"""The R1A-M Intelligence Hub Market Pulse durable markup and roster law.

Three layers, each tested at the cheapest level that actually proves it:

1. ``compute_market_pulse_roster`` (scripts/build_intel_hub.py) is a pure
   function over a synthetic ``hub`` dict — the roster LAW (ordered unique
   union, US-routable only, capped, reading the right key) is proven without
   ever rendering HTML.
2. The ``ihmp`` Jinja macro (templates/intelligence_hub.html.j2) is rendered
   in isolation via `{% from "intelligence_hub.html.j2" import ihmp %}` —
   proves the per-row markup shape (selectors, US-only gating, duplicate
   multi-target) without paying for a full-page render.
3. Static source assertions over the full template text prove structural
   properties (generic `.nb-px` truly removed from the three roster loops,
   the page-level instrument selectors exist) and the rendered
   ``site/intelligence_hub.html`` (skipped if the sparse worktree omits
   ``site/``) proves the same at the byte level for real production output.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "templates" / "intelligence_hub.html.j2"
SITE_PATH = ROOT / "site" / "intelligence_hub.html"

from scripts.build_intel_hub import compute_market_pulse_roster, MARKET_PULSE_ROSTER_CAP  # noqa: E402


def _row(ticker: str, **overrides) -> dict:
    row = {
        "ticker": ticker, "opportunity_score": 50, "stage": "emerging", "price": None,
        # Full-page rendering (the Command ledger's `led-row`) also touches
        # these — safe/empty defaults so a full template render never trips
        # on an unrelated Undefined while proving the roster law.
        "name": None, "lean": 1, "edge_remaining": 0.5, "entry_gate": None,
        "trajectory": None, "flags": [], "edge_drivers": [], "falsifier": None,
        "leading_gap": 0, "directions": {}, "composite_conviction": None, "n_confirm": 0,
    }
    row.update(overrides)
    return row


def _hub(**overrides) -> dict:
    hub = {
        "command": [_row(f"C{i:02d}") for i in range(30)],
        "emerging": [_row(f"E{i:02d}") for i in range(14)],
        "discovery": [_row(f"D{i:02d}") for i in range(14)],
        "exhausted": [_row("EXH1")],
        "as_of": "2026-08-31",
    }
    hub.update(overrides)
    return hub


# ── compute_market_pulse_roster: the roster law ─────────────────────────────

def test_roster_is_the_exact_ordered_unique_union():
    hub = _hub()
    roster = compute_market_pulse_roster(hub)
    expected = [f"C{i:02d}" for i in range(30)] + [f"E{i:02d}" for i in range(14)] + [f"D{i:02d}" for i in range(14)]
    assert roster == expected


def test_roster_caps_at_30_14_14_slices_even_if_lists_are_longer():
    hub = _hub(
        command=[_row(f"C{i:02d}") for i in range(40)],
        emerging=[_row(f"E{i:02d}") for i in range(20)],
        discovery=[_row(f"D{i:02d}") for i in range(20)],
    )
    roster = compute_market_pulse_roster(hub)
    assert len(roster) <= MARKET_PULSE_ROSTER_CAP
    assert "C39" not in roster   # beyond command[:30]
    assert "E19" not in roster   # beyond emerging[:14]
    assert "D19" not in roster   # beyond discovery[:14]


def test_roster_dedupes_a_symbol_appearing_in_multiple_panels():
    hub = _hub(emerging=[_row("C00")] + [_row(f"E{i:02d}") for i in range(1, 14)])
    roster = compute_market_pulse_roster(hub)
    assert roster.count("C00") == 1


def test_hidden_discovery_symbol_never_leaks_in():
    """A symbol beyond hub.discovery's own 14 (i.e. not actually rendered on
    the page) must never enter the roster."""
    hub = _hub(discovery=[_row(f"D{i:02d}") for i in range(14)] + [_row("HIDDEN")])
    roster = compute_market_pulse_roster(hub)
    assert "HIDDEN" not in roster


def test_exhausted_only_symbol_is_excluded():
    hub = _hub()
    roster = compute_market_pulse_roster(hub)
    assert "EXH1" not in roster


def test_roster_reads_hub_discovery_never_discovery_shown():
    """`discovery_shown` is only intel_hub.py's internal local name; a hub
    dict never carries that key, and reading it instead of `discovery` would
    silently zero the Discovery contribution."""
    hub = _hub()
    assert hub.get("discovery_shown") is None
    assert len(hub["discovery"]) > 0

    broken = _hub(discovery=[])
    broken["discovery_shown"] = [_row(f"WRONG{i}") for i in range(14)]  # wrong key
    roster = compute_market_pulse_roster(broken)
    assert not any(t.startswith("WRONG") for t in roster)


def test_non_us_symbol_excluded_from_roster_and_denominator():
    hub = _hub(command=[_row("0700.HK")] + [_row(f"C{i:02d}") for i in range(1, 30)])
    roster = compute_market_pulse_roster(hub)
    assert "0700.HK" not in roster
    assert len(roster) == 29 + 14 + 14  # denominator excludes the non-US name


def test_roster_skips_rows_with_no_ticker():
    hub = _hub(command=[{"opportunity_score": 1}] + [_row(f"C{i:02d}") for i in range(1, 30)])
    roster = compute_market_pulse_roster(hub)
    assert len(roster) == 29 + 14 + 14


# ── the `ihmp` macro, rendered in isolation ─────────────────────────────────

@pytest.fixture(scope="module")
def env() -> Environment:
    e = Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                     autoescape=select_autoescape(["html", "xml"]))

    def region_for(sym: str) -> str:
        s = str(sym or "").upper()
        if s.endswith(".HK"):
            return "hk"
        return "us"

    e.globals["region_for"] = region_for
    return e


_STUB_HUB = {
    "command": [], "emerging": [], "discovery": [], "exhausted": [], "catalysts": [],
    "track_record": None, "desk_grader": {}, "sector_heat": [], "disclaimer": "",
    "n_universe": 0, "macro_context": {}, "desks": {}, "as_of": None,
}


def _render_macro(env: Environment, call: str, roster: list[str] | None = None) -> str:
    # `import` executes the WHOLE imported template's top-level code as a
    # module (Jinja semantics) — not just the macro body — so the snippet
    # must supply everything that top-level code touches. `with context`
    # shares this snippet's `hub`/`built`/etc with the imported module.
    tmpl = env.from_string(
        '{% from "intelligence_hub.html.j2" import ihmp with context %}' + call
    )
    return tmpl.render(
        hub=_STUB_HUB, built="2026-08-31T00:00:00+00:00", qledger_chips={}, china=None,
        market_pulse_roster=["AAPL"] if roster is None else roster,
    )


def test_ihmp_macro_renders_the_required_selectors(env):
    html = _render_macro(env, "{{ ihmp('AAPL', 227.98) }}")
    assert 'data-ihmp-symbol="AAPL"' in html
    assert "data-ihmp-price" in html
    assert "data-ihmp-abs" in html
    assert "data-ihmp-pct" in html
    assert "$227.98" in html


def test_ihmp_macro_omits_non_us_symbols_entirely(env):
    # roster includes the ticker so the ONLY reason it's omitted is region_for.
    html = _render_macro(env, "{{ ihmp('0700.HK', 300.0) }}", roster=["0700.HK"])
    assert "data-ihmp-symbol" not in html
    assert html.strip() == ""


def test_ihmp_macro_omits_a_us_symbol_not_in_the_roster(env):
    """BLOCKER d1: the roster law gates the shipped page, not merely the
    request set — a US-routable symbol absent from `market_pulse_roster`
    must render NOTHING, even though `region_for` alone would allow it."""
    html = _render_macro(env, "{{ ihmp('AAPL', 227.98) }}", roster=["MSFT"])
    assert "data-ihmp-symbol" not in html
    assert html.strip() == ""


def test_ihmp_macro_omitted_when_roster_kwarg_is_absent_entirely():
    """Fails CLOSED: a caller that never passes `market_pulse_roster` at all
    (context variable undefined) must gate to nothing, never to unfiltered."""
    e = Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                     autoescape=select_autoescape(["html", "xml"]))
    e.globals["region_for"] = lambda sym: "us"
    tmpl = e.from_string(
        '{% from "intelligence_hub.html.j2" import ihmp with context %}{{ ihmp("AAPL", 227.98) }}'
    )
    html = tmpl.render(hub=_STUB_HUB, built="2026-08-31T00:00:00+00:00", qledger_chips={}, china=None)
    assert "data-ihmp-symbol" not in html


def test_ihmp_macro_never_uses_the_generic_live_js_selectors(env):
    html = _render_macro(env, "{{ ihmp('AAPL', 227.98) }}")
    assert "nb-px" not in html
    assert "nb-chg" not in html
    assert 'data-sym=' not in html


def test_ihmp_macro_with_no_baseline_price_still_targets_the_symbol(env):
    """A roster member with no nightly close still gets a live target — the
    controller can paint it once a quote arrives."""
    html = _render_macro(env, "{{ ihmp('AAPL', None) }}")
    assert 'data-ihmp-symbol="AAPL"' in html
    assert "$" not in html.split("data-ihmp-price")[1].split("<")[0]


def test_duplicate_symbol_across_two_panel_occurrences_yields_two_targets(env):
    """The multi-target law: one symbol appearing in two panels is TWO DOM
    nodes sharing one data-ihmp-symbol; the roster (tested above) dedupes it
    to one request. This proves the DOM side of that split."""
    html = _render_macro(env, "{{ ihmp('AAPL', 227.98) }}{{ ihmp('AAPL', 227.98) }}")
    assert html.count('data-ihmp-symbol="AAPL"') == 2


# ── BLOCKER d1: the rendered page, through the REAL full template path ─────

def _full_hub(**overrides) -> dict:
    hub = {
        "schema": "intel-hub-v3", "n_universe": 0, "n_actionable": 0,
        "n_emerging": 0, "n_discovery": 0,
        "command": [_row(f"C{i:02d}") for i in range(30)],
        "emerging": [_row(f"E{i:02d}") for i in range(14)],
        "discovery": [_row(f"D{i:02d}") for i in range(14)],
        "exhausted": [], "catalysts": [],
        "desks": {k: {"live": False} for k in
                  ("news", "alt_data", "radar", "standout", "policy", "special")},
        "sector_heat": [], "macro_context": {}, "counts": {},
        "disclaimer": "Context only.", "as_of": "2026-08-31",
        "track_record": {"n_snapshots": 0}, "desk_grader": {},
    }
    hub.update(overrides)
    return hub


def test_rendered_page_ihmp_symbols_exactly_match_the_roster_law(env):
    """BLOCKER d1: every rendered `data-ihmp-symbol` must be a member of
    `compute_market_pulse_roster(hub)`, and the roster stays within its
    58-name cap — proven through the REAL page template (build_intel_hub.py's
    actual render call shape), not the isolated macro."""
    hub = _full_hub()
    for d in hub["command"]:
        d["price"] = 100.0
    roster = compute_market_pulse_roster(hub)
    assert roster  # sanity: the fixture actually produced a non-empty roster
    html = env.get_template("intelligence_hub.html.j2").render(
        hub=hub, built="2026-08-31T00:00:00+00:00", mode="intel_hub",
        qledger_chips={}, china=None, market_pulse_roster=roster,
    )
    rendered_syms = set(re.findall(r'data-ihmp-symbol="([^"]+)"', html))
    assert rendered_syms == set(roster)
    assert len(rendered_syms) <= MARKET_PULSE_ROSTER_CAP


def test_rendered_page_never_targets_a_symbol_beyond_the_roster(env):
    """A US-routable command-panel row beyond the roster's own 30-cap must
    never render a cluster, even though every OTHER gate (US-routable,
    non-empty ticker) would pass it."""
    hub = _full_hub(command=[_row(f"C{i:02d}") for i in range(40)])
    for d in hub["command"]:
        d["price"] = 100.0
    roster = compute_market_pulse_roster(hub)
    assert "C39" not in roster
    html = env.get_template("intelligence_hub.html.j2").render(
        hub=hub, built="2026-08-31T00:00:00+00:00", mode="intel_hub",
        qledger_chips={}, china=None, market_pulse_roster=roster,
    )
    assert 'data-ihmp-symbol="C39"' not in html


# ── static source assertions over the full template ─────────────────────────

@pytest.fixture(scope="module")
def template_text() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def template_code_only(template_text: str) -> str:
    """Template text with Jinja comments stripped — comments (including this
    file's own design-rationale prose, which mentions `.nb-px` by name) never
    reach the rendered page, so an assertion over raw source must not be
    fooled by them into a false failure OR a false pass."""
    return re.sub(r"\{#.*?#\}", "", template_text, flags=re.S)


def test_generic_nb_px_is_gone_from_the_three_roster_loops(template_code_only: str):
    assert "nb-px" not in template_code_only
    assert "nb-chg" not in template_code_only


def test_ihmp_macro_is_wired_into_all_three_roster_loops(template_code_only: str):
    assert template_code_only.count("{{ ihmp(d.ticker, d.price) }}") == 3


def test_page_level_instrument_selectors_are_present(template_code_only: str):
    for selector in (
        "data-ihmp-root", "data-ihmp-availability", "data-ihmp-freshness",
        "data-ihmp-session", "data-ihmp-coverage", "data-ihmp-baseline-at",
        "data-ihmp-asof",
    ):
        assert selector in template_code_only, selector
    assert 'aria-live="polite"' in template_code_only


def test_baseline_asof_time_element_is_baked_with_the_build_time(template_code_only: str):
    """d3: `.ihmp-bar time` was styled by CSS with nothing to select — this
    creates the element, baked with the nightly `built` timestamp."""
    assert "<time data-ihmp-asof datetime=\"{{ built or '' }}\">{{ built or '' }}</time>" in template_code_only


def test_theme_css_uses_semantic_ink_tokens_not_a_literal_palette(template_code_only: str):
    assert "--ink-up" in template_code_only
    assert "--ink-down" in template_code_only


def test_score_stage_and_entry_badge_macros_are_still_called_on_every_row(template_code_only: str):
    """Coarse invariance proof: the calls that render intelligence rank/
    stage/entry state were not touched by this change."""
    assert 'class="score">{{ d.opportunity_score' in template_code_only
    assert "{{ stage(d.stage) }}" in template_code_only
    assert "{{ entrybadge(d.entry_gate) }}" in template_code_only


def test_no_runtime_style_injection_was_introduced(template_code_only: str):
    """This page's material design lives in the static <style> block; no JS
    in this template may assemble or inject a stylesheet at runtime."""
    assert "style.textContent" not in template_code_only
    assert ".insertRule(" not in template_code_only


# ── the real rendered page (skipped if site/ is not checked out) ───────────

@pytest.fixture(scope="module")
def rendered_html() -> str:
    if not SITE_PATH.exists():
        pytest.skip("site/ is not checked out in this sparse worktree")
    return SITE_PATH.read_text(encoding="utf-8")


def test_rendered_hub_page_carries_zero_nb_px_quote_nodes(rendered_html: str):
    assert rendered_html.count("nb-px") == 0


def test_rendered_hub_page_carries_the_page_level_instrument(rendered_html: str):
    assert "data-ihmp-root" in rendered_html
    assert 'aria-live="polite"' in rendered_html
