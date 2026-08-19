"""Public dashboard preview-tier contracts."""
from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_public_dashboard_shells_and_controller_are_allowlisted():
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
    public = set(policy["public"]["exact"])
    assert {"/macro.html", "/start.html", "/us_stocks.html", "/tier_preview.css", "/tier_preview.js"} <= public
    assert "/macro.html" not in set(policy["free_registered"]["exact"])


def test_public_hub_globe_topology_is_allowlisted():
    """The public shell must not fetch its map geometry through the regwall."""
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
    public = set(policy["public"]["exact"])
    html = (ROOT / "site" / "start.html").read_text()

    assert 'data-topo="world-110m.json"' in html
    assert "/world-110m.json" in public


def test_stock_preview_controller_enforces_one_three_full():
    js = (ROOT / "templates" / "tier_preview.js").read_text()
    assert 'state = { tier: "anon", cap: 1 }' in js
    assert 'tier === "free" ? 3 : 1' in js
    assert "isPaid(tier) ? Infinity" in js
    assert "Create free account" in js
    assert "Preview 1 signal before signup" not in js
    assert js.count('action: "Create free account"') == 1
    assert js.count('secondary: "Already a member? Sign in"') == 1
    assert (ROOT / "site" / "tier_preview.js").read_text() == js
    assert (ROOT / "site" / "tier_preview.css").read_text() == (
        ROOT / "templates" / "tier_preview.css"
    ).read_text()


def test_stock_preview_uses_one_surface_cta_per_primary_decision_system():
    js = (ROOT / "templates" / "tier_preview.js").read_text()
    assert '{ key: "action", selector: "#action-board" }' in js
    assert '{ key: "prophet", selector: "#us-standouts" }' in js
    assert 'panel.appendChild(makeGate(surface.key))' in js
    assert 'group.root.insertAdjacentElement("afterend", makeGate())' not in js
    assert "Open more of today’s action board" in js
    assert "Expand the Prophet shortlist" in js


def test_dashboard_wires_preview_and_macro_detail_gate():
    template = (ROOT / "templates" / "dashboard.html.j2").read_text()
    theme = (ROOT / "templates" / "theme.js").read_text()
    assert '<script src="tier_preview.js"></script>' in template
    assert '<link rel="stylesheet" href="tier_preview.css">' in template
    assert '<script src="onboard.js"></script>' not in template
    assert '<link rel="stylesheet" href="onboard.css">' not in template
    assert "onboard.js is lazy-loaded" in theme
    assert "s.src = pfx + 'onboard.js'" in theme
    assert "window.MMXAccessPreview.isAnon()" in template
    assert "window.MMXAccessPreview.openSignin()" in template
    for selector in (
        "#action-board .actbody",
        "#us-standouts .nbgrid",
        "body.page-stocks .panel table tbody",
    ):
        assert selector in (ROOT / "templates" / "tier_preview.js").read_text()


# --------------------------------------------------------------------------- #
# Two surfaces inside #us-standouts that rendered REAL board data outside the gate
# --------------------------------------------------------------------------- #
# Both leaks had the same shape: the gate was wired to the CARD markup, and a second
# surface rendering the same board in different markup was never added to it.  Each
# test therefore pins BOTH sides — the controller's selector AND the template that
# emits it — because a rename on either side alone would re-open the leak with every
# assertion still green.

def test_prophet_ran_rows_go_through_the_same_cap_as_the_cards():
    """The `ran` list carries ticker + name + move, one row per name: the same board
    the blurred cards carry, in quieter markup, and it sat ungated directly beneath
    them — an anonymous visitor could read the roster in plain text."""
    js = (ROOT / "templates" / "tier_preview.js").read_text()
    dash = (ROOT / "templates" / "dashboard.html.j2").read_text()
    # The ROW markup moved to templates/_us_ran_rows.html.j2 when the panel gained a
    # server-side split (the client cap below is now the second of two gates, not
    # the only one), so the emitter assertion follows it there. The CONTAINER is
    # still emitted by dashboard.html.j2 and is what tier_preview.js selects on.
    rows = (ROOT / "templates" / "_us_ran_rows.html.j2").read_text()

    # emitter side
    assert '<div class="pbr-l">' in dash
    assert '{% include "_us_ran_rows.html.j2" %}' in dash
    assert '<a class="pbr-r' in rows
    # gate side — inside groups(), so it inherits applyGroup()'s cap/blur/hide path
    # rather than getting a second, drifting rule of its own.
    gfn = js[js.index("function groups()"):js.index("function surfaceFor(")]
    assert 'add("#us-standouts .pbr-l");' in gfn
    # and inside directRows(), or the container yields zero items and gates nothing.
    assert ".dash-tw-row,.pbr-r" in js


def test_retired_prophet_theme_strip_has_no_preview_adapter_left_behind():
    """Prophet no longer repeats the full Theme Heat panel in a mini-strip, so the
    preview script must not keep a dead, separately drifting membership adapter."""
    js = (ROOT / "templates" / "tier_preview.js").read_text()
    dash = (ROOT / "templates" / "dashboard.html.j2").read_text()
    for retired in ("pbt-tk", "pbt-more", "applyThemeTickers", "themeNameCount"):
        assert retired not in dash
        assert retired not in js
    assert "applyTapeMembers();" in js  # the real Theme Heat preview contract remains


def test_pricing_copy_matches_preview_limits_and_drops_china_pitch():
    plans = (ROOT / "templates" / "plans.html.j2").read_text()
    index = (ROOT / "templates" / "index.html").read_text()
    onboard = (ROOT / "templates" / "onboard.js").read_text()
    theme = (ROOT / "templates" / "theme.js").read_text()
    combined = "\n".join((plans, index, onboard, theme))
    assert "3 signals per daily list" in combined
    assert "preview 1 before signup" in combined
    assert "6 buy signals a day" not in combined
    assert "6 signals a day" not in combined
    assert "China special situations" not in plans
    assert "The China event desk" not in plans
