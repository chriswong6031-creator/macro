"""tests/test_watchlist_sector_i18n.py — sector names on the watchlist workspace.

The defect this pins is the quiet kind. Every label on the Portfolio Intelligence
workspace switches with `html[data-lang="zh"]`, because every label is written in
the source as a bilingual pair. Sector names are the exception: they arrive as ONE
raw English string per record on `stockdata/index.json`, painted client-side, with
no Jinja left to reach the `td()`/`tr()` glossary a baked page uses. So they sat in
English inside an otherwise Chinese row — and nothing raised, because an
untranslated name renders perfectly, just in the wrong language.

The remedy (mirroring the Options desk's shipped `OEW_SECTOR_ZH`) is a literal map
baked into the page: `engine.i18n.sector_lexicon()` -> `window.WL_SECTOR_ZH` ->
`secZh()`/`secCell()` in templates/watchlist.js. Four things can each break it
silently, so each gets its own section below:

  1. The GLOSSARY can go blind to a taxonomy. Two are live — the 11 GICS names the
     US library emits and yfinance's names the CN/HK/CA/Intl libraries emit — plus
     the discovery basket names behind the "Sector / theme" label. A name missing
     from `SECTOR_KEYS` is not an error at runtime; it is English on the page.
  2. The WIRING can be absent. A page baked without the global degrades to English,
     which is the correct fallback and therefore indistinguishable from the bug.
  3. The HELPER can be wrong (returning English for a name the map covers).
  4. A PRINT SITE can bypass a perfectly correct helper. `esc(r.s)` and
     `secCell(r.s)` differ by one identifier and render identically in English.

Sections 3-4 shell `node` over the module the way its sibling suites do
(tests/test_watchlist_workspace_js.py): the file is a browser IIFE, driven behind
minimal window/document stubs with readyState 'loading' so init() never runs.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import jinja2
import pytest
import yaml

# jinja2/yaml are imported HARD, not via importorskip: the job that runs this file
# installs both (.github/ci/legacy-jobs.yml `wri-risk-core`, pinned against drift by
# test_watchlist_workspace_js.test_the_pack_dep_list_matches_the_job_that_runs_this_file).
# An importorskip here would turn a dropped dependency into a green SKIP — the house
# trap where a suite reports success while proving nothing.

ROOT = Path(__file__).resolve().parents[1]
WATCHLIST_JS = ROOT / "templates" / "watchlist.js"
SITE_WATCHLIST_JS = ROOT / "site" / "watchlist.js"
WATCHLIST_J2 = ROOT / "templates" / "watchlist.html.j2"
BUILD_SITE = ROOT / "scripts" / "build_site.py"
STOCK_LIBRARY = ROOT / "scripts" / "build_stock_library.py"
CHINA_J2 = ROOT / "templates" / "china.html.j2"
CONFIG_YML = ROOT / "config.yml"

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")


@pytest.fixture(scope="module")
def js_source() -> str:
    return WATCHLIST_JS.read_text()


@pytest.fixture(scope="module")
def template_source() -> str:
    return WATCHLIST_J2.read_text()


# ===========================================================================
# 1. the glossary — every taxonomy that can reach the page has a zh twin
# ===========================================================================

def test_the_lexicon_answers_every_key_it_declares():
    """`sector_lexicon()` OMITS a name the glossary cannot answer, so the caller's
    English fallback stays the single fallback path. That makes a dropped key
    invisible at runtime by design — this is the assertion that makes it loud."""
    from engine.i18n import SECTOR_KEYS, sector_lexicon

    lex = sector_lexicon()
    dropped = [k for k in SECTOR_KEYS if k not in lex]
    assert not dropped, (
        f"SECTOR_KEYS entries the glossary cannot translate: {dropped}. "
        "Either add them to engine.i18n.LEX or drop them from SECTOR_KEYS — "
        "a key that silently falls out ships English to a zh reader."
    )
    # and nothing maps to itself: an identity entry is an English answer wearing a
    # translation's clothes, which is worse than an absent key (the JS can no
    # longer tell "unmapped" from "mapped").
    identity = sorted(k for k, v in lex.items() if k == v)
    assert not identity, identity


def test_the_us_library_sector_taxonomy_is_covered():
    """The 11 GICS names every US row carries (build_stock_library.GICS_SECTORS).

    Read out of the source with `ast` rather than imported: importing that module
    pulls the whole engine graph, and this assertion only needs the literal.
    """
    from engine.i18n import SECTOR_KEYS

    src = STOCK_LIBRARY.read_text()
    m = re.search(r"^GICS_SECTORS = (\{.*?\n\})", src, re.M | re.S)
    assert m, "GICS_SECTORS literal not found in scripts/build_stock_library.py"
    gics = ast.literal_eval(m.group(1))
    assert gics, "parsed an empty GICS_SECTORS — the regex matched the wrong thing"
    missing = sorted(set(gics) - set(SECTOR_KEYS))
    assert not missing, (
        f"US sector names with no entry in engine.i18n.SECTOR_KEYS: {missing}"
    )


def test_the_non_us_library_sector_taxonomy_is_covered():
    """yfinance's names — what the CN/HK/CA/Intl libraries put in `s`.

    Sourced from the SECZH literal the China page already ships, so this reds when
    that taxonomy grows and the watchlist would otherwise start leaking English for
    the new name.
    """
    from engine.i18n import SECTOR_KEYS

    src = CHINA_J2.read_text()
    m = re.search(r"\{%\s*set SECZH = (\{[^%]*?\})\s*%\}", src, re.S)
    assert m, "SECZH literal not found in templates/china.html.j2"
    seczh = ast.literal_eval(m.group(1))
    assert len(seczh) >= 11, f"parsed a suspiciously small SECZH: {seczh}"
    missing = sorted(set(seczh) - set(SECTOR_KEYS))
    assert not missing, (
        f"non-US sector names with no entry in engine.i18n.SECTOR_KEYS: {missing}"
    )


def test_the_discovery_theme_names_are_covered():
    """The "theme" half of the drawer's "Sector / theme" label — config.yml
    `themes.*.name`, which is where a new basket lands."""
    from engine.i18n import SECTOR_KEYS

    themes = yaml.safe_load(CONFIG_YML.read_text()).get("themes") or {}
    names = {
        (spec or {}).get("name")
        for spec in themes.values()
        if isinstance(spec, dict) and (spec or {}).get("name")
    }
    assert names, "config.yml declares no themes — fixture assumption broke"
    missing = sorted(names - set(SECTOR_KEYS))
    assert not missing, (
        f"theme names with no entry in engine.i18n.SECTOR_KEYS: {missing}"
    )


# ===========================================================================
# 2. the wiring — builder hands the map over, template publishes it
# ===========================================================================

def test_the_builder_hands_the_map_to_the_watchlist_render():
    """scripts/build_site.py must pass `sector_zh_json` into THIS render call.

    Scoped to the watchlist render's own argument list rather than the whole file,
    so passing it to some other page cannot satisfy this.
    """
    src = BUILD_SITE.read_text()
    m = re.search(
        r'env\.get_template\("watchlist\.html\.j2"\)\.render\((.*?)\)\)', src, re.S
    )
    assert m, "watchlist.html.j2 render call not found in scripts/build_site.py"
    call = m.group(1)
    assert "sector_zh_json=" in call, (
        "the watchlist render does not pass sector_zh_json; the page would publish "
        f"an empty map and every sector would render English. Call args:\n{call}"
    )
    assert "sector_lexicon()" in call, (
        "sector_zh_json is passed but not from engine.i18n.sector_lexicon() — a "
        "second, driftable source of the same vocabulary"
    )


def test_the_template_publishes_the_map_as_a_page_global(template_source):
    """The global the JS reads, fed by the context the builder passes."""
    m = re.search(r"window\.WL_SECTOR_ZH\s*=\s*([^;]+);", template_source)
    assert m, "templates/watchlist.html.j2 publishes no window.WL_SECTOR_ZH"
    assert "sector_zh_json" in m.group(1), m.group(1)


@pytest.mark.parametrize(
    ("ctx", "expected"),
    [
        ({}, "{}"),                                       # crop/preview shooters
        ({"sector_zh_json": ""}, "{}"),                    # builder handed nothing
        ({"sector_zh_json": '{"Energy": "能源"}'}, '{"Energy": "能源"}'),
    ],
)
def test_the_global_is_valid_javascript_under_every_context(ctx, expected):
    """Undefined `sector_zh_json` must not emit a bare `=`.

    watchlist.html.j2 is rendered by the crop and preview shooters
    (mockups/refs/psi/workspace/crops/impl/) with their OWN context, not the
    builder's. Without the `default` filter those renders emit `window.WL_SECTOR_ZH
    = ;` — one SyntaxError that takes down the whole inline block, and with it
    STATE_DISPLAY, SUPABASE_CFG, WL_STARTERS and WRI_REGIME. Renders the line as
    SHIPPED (extracted from the template) rather than a re-typed copy.
    """
    line = next(
        ln for ln in WATCHLIST_J2.read_text().splitlines()
        if "window.WL_SECTOR_ZH" in ln and "=" in ln
    )
    out = jinja2.Template(line).render(**ctx)
    assert out.strip().endswith(";"), out
    assert out.split("=", 1)[1].strip().rstrip(";").strip() == expected, out


# ===========================================================================
# 3. the helper — node-shelled, the real module
# ===========================================================================
SHIM = """
global.CustomEvent = function (t, o) { this.type = t; this.detail = o && o.detail; };
var __store = {};
global.localStorage = {
  getItem: function (k) {
    return Object.prototype.hasOwnProperty.call(__store, k) ? __store[k] : null;
  },
  setItem: function (k, v) { __store[k] = String(v); },
  removeItem: function (k) { delete __store[k]; }
};
global.document = {
  readyState: 'loading',
  documentElement: {
    getAttribute: function () { return LANG; },
    setAttribute: function () {},
    classList: { add: function () {}, remove: function () {} }
  },
  getElementById: function () { return null; },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  addEventListener: function () {},
  removeEventListener: function () {},
  dispatchEvent: function () { return true; },
  createElement: function () { return { style: {}, classList: { add: function () {} } }; }
};
global.window = global;
global.window.addEventListener = function () {};
global.location = { hash: '', pathname: '/watchlist.html', search: '', origin: 'https://x' };
function OUT(o) { process.stdout.write(JSON.stringify(o)); }
"""

# the shape the builder actually bakes — two English names sharing one Chinese
# label, which is what makes the sort key load-bearing (see the sort test)
MAP = {
    "Information Technology": "信息技术",
    "Materials": "原材料",
    "Basic Materials": "原材料",
    "Energy": "能源",
}


def _wl(js_body: str, lang: str = "zh", sector_map: dict | None = MAP) -> dict:
    """Run `js_body` with watchlist.js required as WL, under the given page lang."""
    head = "var LANG = %s;\n" % json.dumps(lang)
    head += SHIM + "\n"
    if sector_map is not None:
        head += "global.window.WL_SECTOR_ZH = %s;\n" % json.dumps(sector_map)
    script = head + "var WL = require(%s);\n" % json.dumps(str(WATCHLIST_JS))
    script += textwrap.dedent(js_body)
    res = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert res.returncode == 0, f"node failed:\nSTDERR:\n{res.stderr}"
    assert res.stdout.strip(), f"no stdout; stderr:\n{res.stderr}"
    return json.loads(res.stdout)


@needs_node
def test_a_mapped_sector_renders_its_chinese_in_the_zh_span():
    """THE regression. A sector the map covers must not reach the zh span in English."""
    got = _wl("OUT({ cell: WL.secCell('Information Technology') });")["cell"]
    zh = re.search(r'<span class="l-zh">(.*?)</span>', got, re.S)
    en = re.search(r'<span class="l-en">(.*?)</span>', got, re.S)
    assert zh and en, got
    assert zh.group(1) == "信息技术", (
        f"zh span carries {zh.group(1)!r}, not the glossary's answer — this is the "
        "English leak the map exists to close"
    )
    assert en.group(1) == "Information Technology", got


@needs_node
def test_an_unmapped_sector_keeps_its_english_in_both_spans():
    """Honest fallback: a name the glossary does not carry is shown as-is, never
    blanked and never guessed at."""
    got = _wl("OUT({ cell: WL.secCell('Widget Fabrication') });")["cell"]
    assert got.count("Widget Fabrication") == 2, got
    assert "undefined" not in got and "null" not in got, got


@needs_node
def test_english_survives_the_window_between_a_js_deploy_and_the_next_bake():
    """templates/watchlist.js is a paired plain-copy asset (live on the VPS's 3-min
    pull); watchlist.html only carries the map after the next render bake. In
    between, the new JS runs against a page with NO global — which must read as
    English, not as `undefined` in the zh column."""
    got = _wl("OUT({ cell: WL.secCell('Energy'), raw: WL.secZh('Energy') });",
              sector_map=None)
    assert got["raw"] == "Energy"
    assert got["cell"].count("Energy") == 2, got["cell"]


@needs_node
def test_a_sector_name_is_escaped_before_it_reaches_the_markup():
    """`s` is store-derived data on a page that builds HTML by concatenation."""
    got = _wl("""OUT({ cell: WL.secCell('<img src=x onerror=1>') });""")["cell"]
    assert "<img" not in got, got
    assert "&lt;img" in got, got


@needs_node
def test_the_sort_key_follows_the_label_the_reader_can_see():
    """The glossary is many-to-one across the two live taxonomies: `Materials` and
    `Basic Materials` are both 原材料. Sorting on the English behind them splits one
    visible sector into two non-adjacent runs, so under zh the column reads
    unsorted. Under `en` the key must stay the English, unchanged."""
    got = _wl("""
        OUT({
          zh_a: WL.secSortKey('Materials'),
          zh_b: WL.secSortKey('Basic Materials'),
          none: WL.secSortKey('')
        });
    """, lang="zh")
    assert got["zh_a"] == got["zh_b"] == "原材料", got
    assert got["none"] == "~", got  # no-sector sentinel, unchanged by this wave

    en = _wl("OUT({ a: WL.secSortKey('Materials'), b: WL.secSortKey('Basic Materials') });",
             lang="en")
    assert en["a"] == "Materials" and en["b"] == "Basic Materials", en


@needs_node
def test_a_chinese_query_matches_the_sector_the_reader_can_see():
    """Both filter boxes match on `secZh`, so a reader who can SEE 能源 can type it.
    Matching only the English behind the label makes the box look broken to them."""
    got = _wl("""
        OUT({ hit: WL.secZh('Energy').indexOf('能源') >= 0,
              miss: WL.secZh('Energy').indexOf('医疗') >= 0 });
    """)
    assert got["hit"] is True and got["miss"] is False, got


# ===========================================================================
# 4. the print sites — a correct helper is worth nothing if a row bypasses it
# ===========================================================================

# (anchor that identifies the line, what the site is)
PRINT_SITES = [
    ('class="wl-sector muted"', "pre-W2 list card"),
    ("var sect = r.s ?", "dense table, Sector column"),
    # not the bare 'Sector / theme' pair — that also matches the table's column
    # HEADER, which is a label and already bilingual. This is the VALUE line.
    ("if (r.s) cells.push(", "row drawer, 390px demotion"),
    ("'<small>' + esc(x.n", "search-to-add suggestion"),
]


@pytest.mark.parametrize(("anchor", "what"), PRINT_SITES)
def test_every_sector_print_site_goes_through_the_bilingual_helper(
    anchor, what, js_source
):
    lines = [ln for ln in js_source.splitlines() if anchor in ln]
    assert len(lines) == 1, f"{what}: anchor {anchor!r} matched {len(lines)} lines"
    assert "secCell(" in lines[0], (
        f"{what} prints a sector without secCell(), so it renders English under zh "
        f"however correct the helper is:\n{lines[0].strip()}"
    )


def test_no_sector_value_reaches_the_markup_unpaired(js_source):
    """The exact shape of the original defect: the raw `s` handed straight to esc().

    `secCell` escapes both halves itself, so a surviving `esc(r.s)` is always a
    print site that was missed or reverted.
    """
    leaks = re.findall(r"esc\(\s*[rx]\.s\s*(?:\|\||\))", js_source)
    assert not leaks, (
        f"sector value passed to esc() directly ({leaks}) — that is an English-only "
        "span; use secCell(), which emits the .l-en/.l-zh pair"
    )


def test_the_helpers_are_shared_rather_than_re_implemented(js_source):
    """portfolio.js and watchlist_risk.js paint into the same page. When either
    grows a sector name it must reach THIS lookup — a second copy is a second
    vocabulary that drifts."""
    ws = re.search(r"window\.WS = \{(.*?)\n  \};", js_source, re.S)
    assert ws, "window.WS export block not found in templates/watchlist.js"
    assert "secZh: secZh" in ws.group(1) and "secCell: secCell" in ws.group(1)

    for sibling in ("portfolio.js", "watchlist_risk.js"):
        src = (ROOT / "templates" / sibling).read_text()
        assert "WL_SECTOR_ZH" not in src, (
            f"templates/{sibling} reads the raw map directly; go through "
            "WS().secCell() so the fallback and escaping stay in one place"
        )


def test_the_paired_site_copy_ships_the_same_bytes():
    """Plain-copy law: templates/watchlist.js and site/watchlist.js are one asset.
    The VPS serves the site/ copy, so a template-only edit ships nothing at all."""
    assert SITE_WATCHLIST_JS.read_bytes() == WATCHLIST_JS.read_bytes(), (
        "site/watchlist.js is out of sync — run "
        "`python -m scripts.check_template_site_sync --fix`"
    )
