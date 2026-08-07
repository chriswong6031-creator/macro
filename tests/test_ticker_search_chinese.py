"""The nav search must actually FIND a stock typed in Chinese.

The prior guard (tests/test_stock_library_manifests.py) asserted that
``_search_index_row`` copies a name_zh it is handed — it never asked whether any
market feeds one, and it never ran the matcher. So a US library carrying zero
Chinese names (0 of 2,930 rows) and a client that reports a failed library load
as "No ticker or company matches this search." both passed green.

These tests pin the two behaviours instead of their spelling:

  1. the SHIPPED theme.js matcher, evaluated in node, matches a Chinese query
     against a Chinese name, against a search-only alias, and does NOT promote
     an alias into the displayed name;
  2. the US builder emits a Chinese search key for the names the committed maps
     cover, and never lets the noisy alias shadow a curated name;
  3. a market whose library failed to load produces an honest notice rather than
     a "no matches" verdict — including the signed-out (401) case.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
THEME_SOURCES = {
    "templates": ROOT / "templates" / "theme.js",
    "site": ROOT / "site" / "theme.js",
}

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


# ---------------------------------------------------------------------------
# node harness — evaluate the SHIPPED function bodies, not a transcription
# ---------------------------------------------------------------------------

def _extract(source: str, name: str) -> str:
    """Slice `function <name>(...) { ... }` out of theme.js by brace balance."""
    start = source.index("function " + name + "(")
    depth, i = 0, source.index("{", start)
    for j in range(i, len(source)):
        if source[j] == "{":
            depth += 1
        elif source[j] == "}":
            depth -= 1
            if depth == 0:
                return source[start:j + 1]
    raise AssertionError(f"unbalanced braces extracting {name}()")


def _run_node(theme: Path, functions: list[str], preamble: str, script: str) -> dict:
    source = theme.read_text(encoding="utf-8")
    bodies = "\n".join(_extract(source, fn) for fn in functions)
    prog = f"{preamble}\n{bodies}\n{script}"
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


_MATCH_PREAMBLE = ""
_MATCH_FUNCTIONS = ["normalizeSearch", "nameEnglish", "nameChinese", "nameChineseAlias", "rank"]

# One row per shape the live manifests actually ship.
_ROWS = """
var ROWS = {
  cn:    {t: '002020.SZ', n: 'Zhejiang Jingxin Pharmaceutical Co., Ltd.', z: '京新药业'},
  hk:    {t: '0700.HK',   n: 'Tencent', z: '腾讯控股'},
  us_z:  {t: 'AAPL',      n: 'Apple Inc', z: '苹果公司'},
  us_za: {t: 'CBRE',      n: 'CBRE Group Inc', za: '世邦魏理仕'},
  us_en: {t: 'CRWD',      n: 'CrowdStrike Holdings'}
};
"""


@pytest.mark.parametrize("which", sorted(THEME_SOURCES))
def test_chinese_query_matches_chinese_name_and_alias(which: str) -> None:
    script = _ROWS + """
    var q = function (s) { return normalizeSearch(s); };
    var out = {};
    out.cn      = rank(ROWS.cn,    q('京新药业'));
    out.cn_part = rank(ROWS.cn,    q('京新'));
    out.hk      = rank(ROWS.hk,    q('腾讯'));
    out.us_z    = rank(ROWS.us_z,  q('苹果'));
    out.us_za   = rank(ROWS.us_za, q('世邦魏理仕'));
    out.us_en   = rank(ROWS.us_en, q('苹果'));
    out.ticker  = rank(ROWS.us_z,  q('aapl'));
    process.stdout.write(JSON.stringify(out));
    """
    got = _run_node(THEME_SOURCES[which], _MATCH_FUNCTIONS, _MATCH_PREAMBLE, script)
    # rank() returns 9 for "no match" — every Chinese-typed query must beat it.
    assert got["cn"] < 9, "a Chinese A-share name must match its Chinese query"
    assert got["cn_part"] < 9, "a Chinese prefix must match"
    assert got["hk"] < 9
    assert got["us_z"] < 9, "a US name with a curated Chinese name must match"
    assert got["us_za"] < 9, "a US name with a search-only alias must match"
    assert got["us_en"] == 9, "a name with no Chinese key must not match a Chinese query"
    assert got["ticker"] == 0, "ticker matching must be unaffected"


@pytest.mark.parametrize("which", sorted(THEME_SOURCES))
def test_search_alias_is_never_displayed(which: str) -> None:
    script = _ROWS + """
    process.stdout.write(JSON.stringify({
      curated: nameChinese(ROWS.us_z),
      alias:   nameChinese(ROWS.us_za),
      english: nameEnglish(ROWS.us_za)
    }));
    """
    got = _run_node(THEME_SOURCES[which], _MATCH_FUNCTIONS, _MATCH_PREAMBLE, script)
    assert got["curated"] == "苹果公司"
    assert got["alias"] == "", "a `za` alias must never become the shown Chinese name"
    assert got["english"] == "CBRE Group Inc"


# ---------------------------------------------------------------------------
# the honest empty state
# ---------------------------------------------------------------------------

_NOTICE_FUNCTIONS = ["searchCopy", "marketMeta", "loadFailureNotice"]
_NOTICE_PREAMBLE = """
var STOCK_MARKETS = [
  {key: 'us',   mkt: 'US',     mktZh: '美国'},
  {key: 'cn',   mkt: 'China',  mktZh: '中国A股'},
  {key: 'hk',   mkt: 'HK',     mktZh: '香港'},
  {key: 'ca',   mkt: 'Canada', mktZh: '加拿大'},
  {key: 'intl', mkt: 'Intl',   mktZh: '国际'}
];
var LANG = 'en';
function curLang() { return LANG; }
var libFailed = {};
"""


@pytest.mark.parametrize("which", sorted(THEME_SOURCES))
def test_failed_library_is_reported_not_reported_as_no_matches(which: str) -> None:
    script = """
    var out = {};
    out.clean = loadFailureNotice();
    libFailed = {us: 'auth', cn: 'auth', hk: 'auth', ca: 'auth', intl: 'auth'};
    out.all_auth = loadFailureNotice();
    libFailed = {cn: 'error'};
    out.one_error = loadFailureNotice();
    LANG = 'zh';
    out.one_error_zh = loadFailureNotice();
    process.stdout.write(JSON.stringify(out));
    """
    got = _run_node(THEME_SOURCES[which], _NOTICE_FUNCTIONS, _NOTICE_PREAMBLE, script)
    assert got["clean"] is None, "every market loaded → the real 'no matches' copy stands"
    assert got["all_auth"] and "Sign in" in got["all_auth"]["text"]
    assert got["all_auth"]["action"] is None, "a 401 does not heal on retry"
    assert got["one_error"] and "China" in got["one_error"]["text"]
    assert got["one_error"]["action"], "a transport failure offers the retry"
    assert re.search(r"[㐀-鿿]", got["one_error_zh"]["text"]), "zh mode speaks Chinese"


@pytest.mark.parametrize("which", sorted(THEME_SOURCES))
def test_library_load_failure_is_recorded_not_swallowed(which: str) -> None:
    source = THEME_SOURCES[which].read_text(encoding="utf-8")
    # The exact expression that turned every 401/404/5xx into an empty market.
    assert "r.ok ? r.json() : []" not in source
    assert "marketLoadFailed" in source
    assert "loadFailureNotice()" in source


# ---------------------------------------------------------------------------
# the US name maps + the builder seam that emits them
# ---------------------------------------------------------------------------

def test_us_name_maps_are_populated_and_disjoint() -> None:
    from collectors.us_names_zh import load_aliases_zh, load_names_zh, lookup

    names, aliases = load_names_zh(), load_aliases_zh()
    assert len(names) > 500, "the committed Chinese-name map must not be empty"
    assert len(aliases) > 100
    overlap = {t for t in aliases if lookup(names, t)}
    assert not overlap, f"aliases must never shadow a curated name: {sorted(overlap)[:5]}"
    for ticker, expected in (("AAPL", "苹果"), ("NVDA", "英伟达"), ("TSLA", "特斯拉")):
        assert expected in (lookup(names, ticker) or ""), ticker
    # class-share forms differ between our universe (BRK-B) and the source (BRK.B)
    assert lookup(names, "BRK-B") and lookup(names, "BRK.B")


def test_us_builder_emits_a_chinese_search_key() -> None:
    from scripts.build_stock_library import search_name_zh

    name, alias = search_name_zh("AAPL")
    assert name and not alias

    name, alias = search_name_zh("CBRE")
    assert alias and not name, "an alias-only name still gets a Chinese search key"

    assert search_name_zh("ZZZZ-NOT-A-TICKER") == (None, None)
