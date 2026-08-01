"""Tests for the Research Vault page build (RV W3).

Covers the SSR shell that scripts/build_research_vault.py renders:
  - the page builds from an EMPTY catalog (honest empty state, no fake cards) and
    from a seeded catalog (SSR cards baked for SEO/no-JS fallback, but withheld from
    the interactive first paint until the live catalog resolves);
  - the flagship structure is present: hero + This-Week figs, the three lane tabs
    (Latest/Top Picks/Saved), the browse rail + facet filter, the PDF viewer modal
    (auth-overlay clone) with its quota/download states, and the app + catalog island;
  - bilingual EN/ZH dual-spans are balanced (equal l-en / l-zh counts) and the
    <title> carries NO i18n markup / CJK (check_title_i18n contract);
  - the not-investment-advice footer + the "highlighted research, never a trade call"
    framing + the watermark microcopy are present (compliance);
  - the SSR card projection is public-safe (never leaks a body-text field).

Pure render — jinja2 only (already a dep); no R2, no network.
"""
from __future__ import annotations

import hashlib
import json
import re

import pytest

from scripts import build_research_vault as bld


# --- fixtures ---------------------------------------------------------------

_SEED = {
    "schema": "research_vault.catalog.v1",
    "generated_at": "2026-07-22T18:00:00Z",
    "count": 2,
    "institutions": ["Bernstein", "Goldman Sachs"],
    "items": [
        {
            "id": "bernstein-2026-07-22-dc-pipeline",
            "title": "Data-center pipeline probabilities — credible developers vs PowerPoints",
            "institution": "Bernstein", "side": "sell", "desk": "Data Centers",
            "published_at": "2026-07-22T14:00:00Z",
            "summary_points": ["Only 33% of the announced pipeline looks credible.",
                               "Hyperscalers control 42% of that credible capacity."],
            "tags": ["AI", "Data centers"], "tickers": ["EQIX", "DLR"],
            "top_pick": True, "pages": 12, "needs_metadata": False,
            # a body field must NEVER survive into the SSR/catalog projection:
            "body": "SECRET FULL TEXT THAT MUST NOT LEAK",
        },
        {
            "id": "unknown-2026-07-20-korea", "title": "Korea equities — export cycle turns",
            "institution": "Unknown", "side": "independent", "desk": "",
            "published_at": "2026-07-20T10:00:00Z",
            "summary_points": [], "tags": ["Korea"], "tickers": ["EWY"],
            "top_pick": False, "pages": 0, "needs_metadata": True,
        },
    ],
}


def _render(monkeypatch, catalog):
    monkeypatch.setattr(bld, "load_catalog", lambda: catalog)
    return bld.render()


@pytest.fixture
def page_seeded(monkeypatch):
    return _render(monkeypatch, _SEED)


@pytest.fixture
def page_empty(monkeypatch):
    return _render(monkeypatch, dict(bld._EMPTY_CATALOG))


# --- build + structure ------------------------------------------------------

def test_builds_empty_and_seeded(page_empty, page_seeded):
    for html in (page_empty, page_seeded):
        assert "<!DOCTYPE html>" in html
        assert "research_vault_app.js" in html          # the client app is wired
        assert 'id="rv-catalog"' in html                 # the SSR catalog island


def test_page_canvas_tracks_shared_theme_tokens(page_seeded):
    body_rule = re.search(r"body\s*\{([^}]*)\}", page_seeded)
    assert body_rule, "Research Vault must define its page canvas"
    declarations = body_rule.group(1)
    assert "background:var(--bg)" in declarations
    assert "color:var(--text)" in declarations
    assert "min-height:100vh" in declarations


def test_committed_page_uses_hashed_themed_canvas_asset():
    html = (bld.ROOT / "site" / "research_vault.html").read_text(encoding="utf-8")
    match = re.search(r'href="(assets/css/([0-9a-f]{8})\.css)\?v=\2"', html)
    assert match, "Research Vault must load a content-hashed page stylesheet"
    css_path = bld.ROOT / "site" / match.group(1)
    css = css_path.read_bytes()
    assert hashlib.sha256(css).hexdigest()[:8] == match.group(2)
    text = css.decode("utf-8")
    assert "background:var(--bg)" in text
    assert "color:var(--text)" in text


def test_title_has_no_i18n(page_seeded):
    m = re.search(r"<title>(.*?)</title>", page_seeded, re.S)
    assert m, "no <title>"
    title = m.group(1)
    assert "l-en" not in title and "l-zh" not in title   # no dual-span in the title
    assert not re.search(r"[一-鿿]", title)       # no CJK in the title
    assert "Research Vault" in title


def test_hero_and_this_week_figs(page_seeded):
    assert 'id="fig-new"' in page_seeded                  # New this week
    assert 'id="fig-desks"' in page_seeded                # Desks publishing
    assert 'id="fig-theme"' in page_seeded                # Most-covered theme
    assert 'id="fig-total"' in page_seeded                # In the vault
    assert 'id="rvwNodes"' in page_seeded                 # the Desk Constellation signature (neural web)
    assert 'id="web-sname"' in page_seeded                # rotating spotlight name readout


def test_three_lane_tabs(page_seeded):
    for lane in ("latest", "picks", "saved"):
        assert f'data-lane="{lane}"' in page_seeded
    # bilingual lane labels
    assert "Latest" in page_seeded and "最新" in page_seeded
    assert "Top Picks" in page_seeded and "精选" in page_seeded
    assert "Saved" in page_seeded and "收藏" in page_seeded


def test_browse_and_filter(page_seeded):
    assert 'id="tree"' in page_seeded                     # browse rail tree host
    assert 'id="q"' in page_seeded                        # search box
    assert 'data-dim="inst"' in page_seeded               # institution facet group
    assert 'data-dim="side"' in page_seeded               # rating facet group
    assert 'data-dim="theme"' in page_seeded              # theme facet group


def test_pdf_viewer_modal(page_seeded):
    # the auth-overlay clone + its parts
    assert 'id="overlay"' in page_seeded and 'aria-modal="true"' in page_seeded
    assert 'id="vstage"' in page_seeded                   # pdf.js canvas host
    assert 'id="vthumbs"' in page_seeded                  # thumbnail rail
    assert 'id="pg-prev"' in page_seeded and 'id="pg-next"' in page_seeded  # page nav
    assert 'id="zoom-in"' in page_seeded and 'id="fit-w"' in page_seeded    # zoom / fit
    assert 'id="vh-invert"' in page_seeded and 'id="vh-fs"' in page_seeded  # invert + fullscreen
    # all quota/download states present
    for st in ("ok", "max", "free", "anon"):
        assert f'id="dl-state-{st}"' in page_seeded
        assert f'id="dl-btn-{st}"' in page_seeded


def test_pdf_gate_uses_latest_onboarding_sheet(page_seeded):
    assert 'href="onboard.css"' in page_seeded
    assert 'src="onboard.js"' in page_seeded
    js = (bld.ROOT / "site" / "research_vault_app.js").read_text(encoding="utf-8")
    assert "function openLatestSignin()" in js
    assert "window.MMOnboard.open('signin', {})" in js
    assert "MDXAuth.signIn" not in js


# --- SSR feed (SEO) ---------------------------------------------------------

def test_ssr_cards_baked_when_seeded(page_seeded):
    assert page_seeded.count('class="rep glass') == 2    # one per catalog item
    assert "Data-center pipeline probabilities" in page_seeded   # crawlable title
    assert "Bernstein" in page_seeded
    # top-pick + needs-metadata states render
    assert "rep glass pick" in page_seeded               # highlighted card
    assert "rep glass needs" in page_seeded              # needs-metadata card
    assert "Summary pending" in page_seeded              # empty-summary fallback
    assert 'class="rep-titlelink"' not in page_seeded


def test_public_ssr_preview_stops_at_three_and_shows_pro_gate(monkeypatch):
    catalog = dict(_SEED)
    catalog["items"] = [
        {
            **_SEED["items"][i % 2],
            "id": f"report-{i}",
            "title": f"Report {i}",
            "published_at": f"2026-07-{22 - i:02d}T14:00:00Z",
        }
        for i in range(5)
    ]
    catalog["count"] = 5
    html = _render(monkeypatch, catalog)
    assert html.count('class="rep glass') == 4  # three real cards + one generic ghost
    assert "Report 0" in html and "Report 2" in html and "Report 4" in html
    assert "Report 1" not in html and "Report 3" not in html
    island = re.search(r'<script id="rv-catalog" type="application/json">(.*?)</script>',
                       html, re.S)
    assert island
    payload = json.loads(island.group(1))
    assert len(payload["items"]) == 3
    assert payload["preview"] is True
    assert payload["summary"]["total"] == 5
    assert "2 more institutional reports" in html
    assert "Upgrade to Pro" in html


def test_client_preview_is_fixed_to_three_and_fails_closed():
    js = (bld.ROOT / "site" / "research_vault_app.js").read_text(encoding="utf-8")
    assert "var USER_TIER = 'anon'" in js
    assert "function feedUnlocked() { return USER_TIER === 'pro'; }" in js
    assert "function teaseCount() { return 3; }" in js
    assert "previewItems().filter(matchItem)" in js
    assert "x.slug && feedUnlocked()" in js
    assert "fetch(API + '/api/research/catalog', opts)" in js
    assert "var opts = { headers: h, credentials: 'include', cache: 'no-store' };" in js


# --- Pro unlock path (the MDXAuth boot race) --------------------------------
# USER_TIER fails CLOSED at 'anon' (#3939), and NOTHING but the MDXAuth auth-change
# listener ever calls resolveTier(). So the listener registering is the whole Pro
# unlock: if window.MDXAuth (defined by theme.js) has not been created by the time
# research_vault_app.js runs wire(), every visitor — Pro included — is pinned on the
# public 3-summary preview forever. Both tags ship `defer` (lib.pages
# .optimize_assets_text stamps it), so document order IS execution order.

def _script_order(html: str) -> list[str]:
    return re.findall(r'<script[^>]*\bsrc="([^"?]+)', html)


def test_theme_js_loads_before_the_vault_app(page_seeded):
    order = _script_order(page_seeded)
    assert "theme.js" in order, "theme.js must be loaded (it defines window.MDXAuth)"
    assert "research_vault_app.js" in order
    assert order.index("theme.js") < order.index("research_vault_app.js"), (
        "theme.js must execute before research_vault_app.js — otherwise wire() finds "
        "no window.MDXAuth, never registers the auth listener, and Pro accounts stay "
        "locked on the anonymous preview"
    )


# NOTE: no committed-page assertions here. site/research_vault.html is
# LANE-COMMITTED (render lanes re-bake it from the template with fresh ?v=
# stamps), so tests pinning its bytes turn every render into a red and every
# vault-JS edit into a hand-stamp chore — and a PR carrying the page conflicts
# with main within the hour (busy-main merge race, 2026-07-29). The rendered-
# output test above pins the order at the SOURCE (template); the render
# pipeline owns propagating it (with stamps) to the committed page.


def test_auth_listener_registration_has_a_load_fallback():
    js = (bld.ROOT / "site" / "research_vault_app.js").read_text(encoding="utf-8")
    # the callback is a named function so both registration paths share it
    assert "function onAuthResolved()" in js
    assert "window.MDXAuth.onChange(onAuthResolved)" in js
    on_auth = re.search(r"function onAuthResolved\(\) \{(.*?)\n    \}", js, re.S)
    assert on_auth and "refreshFromApi();" in on_auth.group(1)
    # ...and the fallback: register on 'load' when theme.js has not run yet
    # (same shape as site/mm_brain.js boot()), then redo the reads that went out
    # unauthenticated at boot.
    fallback = re.search(
        r"else window\.addEventListener\('load', function \(\) \{(.*?)\n    \}\);",
        js, re.S,
    )
    assert fallback, "missing the window 'load' fallback registration"
    body = fallback.group(1)
    assert "window.MDXAuth.onChange(onAuthResolved)" in body
    assert "resolveTier();" in body
    assert "refreshFromApi();" in body


def test_interactive_first_paint_masks_the_baked_snapshot(page_seeded):
    """The hourly data snapshot can be newer than the last page render.

    Apply the loading class in <head> (before a browser can paint), keep the baked
    cards available to crawlers/no-JS, and reveal interactive data only after the
    app settles a catalog source.
    """
    marker = "document.documentElement.classList.add('rv-awaiting-live')"
    assert marker in page_seeded
    assert page_seeded.index(marker) < page_seeded.index('id="rv-catalog"')
    assert "html.rv-awaiting-live .rv-feed{ display:none; }" in page_seeded
    assert "html.rv-awaiting-live .rv-feed-loading{ display:block; }" in page_seeded
    assert 'id="feed-shell" aria-busy="false"' in page_seeded
    assert 'class="rv-status-loading">Refreshing live research' in page_seeded
    assert 'class="rv-status-loading">正在刷新实时研报' in page_seeded


def test_no_js_default_is_an_honest_saved_snapshot(page_seeded):
    """With scripts disabled the SSR cards stay usable and never claim to be live."""
    assert 'class="rv-status-snapshot">Saved research snapshot' in page_seeded
    assert 'class="rv-status-snapshot">已保存研报快照' in page_seeded
    assert 'class="rv-lead-snapshot">Showing the latest saved institutional reports.' in page_seeded
    assert 'class="rv-lead-snapshot">正在显示最近保存的机构研报。' in page_seeded
    assert 'id="feed-shell" aria-busy="false"' in page_seeded


def test_boot_waits_for_authoritative_catalog_before_ingesting_bake():
    js = (bld.ROOT / "site" / "research_vault_app.js").read_text(encoding="utf-8")
    boot = re.search(r"function boot\(\) \{(.*?)\n  \}", js, re.S)
    assert boot, "missing Research Vault boot function"
    body = boot.group(1)
    assert "refreshFromApi();" in body
    assert "hydrateFromBake();" not in body, (
        "the render-time catalog must not be painted as current before the live API"
    )
    assert "CATALOG_SOURCE === 'loading') hydrateFromBake();" in js
    assert "ingest(j, j.stale ? 'snapshot' : 'live');" in js
    assert "Saved snapshot · live update unavailable" in js
    assert "shell.setAttribute('aria-busy', 'true')" in body


def test_catalog_refresh_is_no_store_and_newest_request_wins():
    js = (bld.ROOT / "site" / "research_vault_app.js").read_text(encoding="utf-8")
    assert "var CATALOG_REQ = 0" in js
    assert "var req = ++CATALOG_REQ;" in js
    assert "if (CATALOG_ABORT)" in js and "CATALOG_ABORT.abort()" in js
    assert "if (req !== CATALOG_REQ) return null;" in js
    assert "if (!j || !Array.isArray(j.items)) throw new Error('invalid catalog payload');" in js
    assert "cache: 'no-store'" in js
    assert "Promise.race([request, deadline])" in js
    assert "reject(new Error('catalog timeout'))" in js


def test_preview_hero_and_constellation_use_whole_vault_aggregates():
    js = (bld.ROOT / "site" / "research_vault_app.js").read_text(encoding="utf-8")
    assert "var CATALOG_SUMMARY = null" in js
    assert "var aggregateNewN = summaryNumber('new_this_week');" in js
    assert "var aggregateDeskN = summaryNumber('desks_this_week');" in js
    assert "var aggregatePicks = summaryNumber('highlighted');" in js
    assert "Array.isArray(CATALOG_SUMMARY.institutions)" in js
    assert "CATALOG_PREVIEW = !!(catalog && catalog.preview) || TOTAL_COUNT > ITEMS.length;" in js
    assert "Latest preview loaded. Whole-vault weekly totals are temporarily unavailable." in js


def test_empty_state_has_no_fake_cards(page_empty):
    assert 'class="rep glass' not in page_empty          # no baked cards at all
    # the client renders the honest bilingual empty state; the island is empty:
    assert '"items": []' in page_empty or '"items":[]' in page_empty


def test_ssr_projection_never_leaks_body(page_seeded):
    # the private full-text body must not appear anywhere in the baked page
    assert "SECRET FULL TEXT" not in page_seeded


# --- bilingual + compliance -------------------------------------------------

def test_bilingual_spans_balanced(page_seeded):
    en = page_seeded.count('class="l-en"')
    zh = page_seeded.count('class="l-zh"')
    assert en > 20                                        # substantial bilingual chrome
    assert en == zh, f"unbalanced dual-spans: {en} l-en vs {zh} l-zh"


def test_not_investment_advice_and_framing(page_seeded):
    assert "Not investment advice" in page_seeded
    assert "非投资建议" in page_seeded
    # Top Picks framed as highlighted research, never a trade call. (The hero's
    # own "not a trade recommendation" stance was retired — the not-advice guarantee
    # lives in the legal footer + the Top Picks framing, not a hero disclaimer.)
    assert "never a trade call" in page_seeded
    # watermark microcopy
    assert "not for redistribution" in page_seeded
    assert "Watermarked with your account" in page_seeded


def test_no_validated_word(page_seeded):
    # the 'validated' word is CI-banned in user-facing text
    assert not re.search(r"\bvalidated\b", page_seeded, re.I)
