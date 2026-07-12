"""Inline-JS deploy guard — unit tests for scripts/check_inline_js.

Verifies the guard catches a blank-page-causing syntax error (the `var DISP = ;`
class of bug) and passes clean/non-JS/external blocks. Skips when `node` is not
on PATH (the guard degrades to exit code 2 there, asserted separately)."""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import check_inline_js as guard

HAS_NODE = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not HAS_NODE, reason="node not on PATH")

CLEAN = '<!doctype html><script>\n  var DISP = {"A": 1};\n  (function(){ return DISP.A; })();\n</script>'
BROKEN = '<!doctype html><script>\n  var DISP = ;\n  (function(){ return 1; })();\n</script>'
EXTERNAL = '<script src="theme.js"></script>'
JSON_ISLAND = '<script type="application/json" id="d">{"not": "js" "missing": "comma"}</script>'


def _write(tmp_path, name, html):
    (tmp_path / name).write_text(html, encoding="utf-8")


@needs_node
def test_clean_site_passes(tmp_path):
    _write(tmp_path, "ok.html", CLEAN)
    assert guard.find_bad_scripts(str(tmp_path)) == []
    assert guard.main([str(tmp_path)]) == 0


@needs_node
def test_broken_inline_js_is_caught(tmp_path):
    _write(tmp_path, "bad.html", BROKEN)
    bad = guard.find_bad_scripts(str(tmp_path))
    assert len(bad) == 1
    path, line, err = bad[0]
    assert path.endswith("bad.html")
    assert line == 2  # the `var DISP = ;` line within the file
    assert "Error" in err
    assert guard.main([str(tmp_path)]) == 1


@needs_node
def test_external_and_json_blocks_are_skipped(tmp_path):
    # src= scripts aren't our content; application/json islands aren't executed
    # as JS and would false-positive on node --check — both must be ignored.
    _write(tmp_path, "ext.html", EXTERNAL + JSON_ISLAND)
    assert guard.find_bad_scripts(str(tmp_path)) == []


@needs_node
def test_real_site_is_clean():
    """The shipped site/ must always parse — this is the regression that bit twice."""
    site = Path(__file__).resolve().parent.parent / "site"
    if not site.is_dir():
        pytest.skip("site/ not built")
    assert guard.find_bad_scripts(str(site)) == []


def test_missing_node_fails_loudly(monkeypatch):
    # A guard that cannot run must FAIL (exit 2), never silently pass.
    monkeypatch.setattr(guard.shutil, "which", lambda _name: None)
    assert guard.main(["site"]) == 2


# ---- on*= handler attributes (the PR #2321 gap) --------------------------------

CURLY_ONCLICK = '<button onclick="showTab(‘overview’)">x</button>'


def test_curly_onclick_flagged_without_node(tmp_path):
    # The contamination scan is pure python — it must go red even where node
    # is unavailable (and in .j2 files node can never parse).
    _write(tmp_path, "curly.html", CURLY_ONCLICK)
    bad = guard.find_curly_contamination([str(tmp_path)])
    assert len(bad) == 1
    path, line, msg = bad[0]
    assert path.endswith("curly.html") and line == 1
    assert "U+2018" in msg and "on*=" in msg


@needs_node
def test_curly_onclick_fails_node_check_too(tmp_path):
    _write(tmp_path, "curly.html", CURLY_ONCLICK)
    assert any(p.endswith("curly.html") for p, _l, _m in guard.find_bad_handlers([str(tmp_path)]))
    assert guard.main([str(tmp_path)]) == 1


@needs_node
def test_broken_handler_js_is_caught(tmp_path):
    # the china_stocks.html shape: attribute truncated at an unescaped inner
    # double quote leaves an unterminated string — SyntaxError on every click.
    _write(tmp_path, "bh.html", '<a href="#" onclick="f(\'<span class="x">\')">x</a>')
    bad = guard.find_bad_handlers([str(tmp_path)])
    assert len(bad) == 1 and "on*= handler" in bad[0][2]


@needs_node
def test_entity_escaped_handler_quotes_parse(tmp_path):
    # &quot;/&rsquo; entities decode before the browser's JS parse — the guard
    # must unescape the same way, so properly-escaped handlers stay green.
    _write(tmp_path, "ok.html",
           '<button onclick="this.innerHTML=\'<i class=&quot;a&quot;>don&rsquo;t</i>\'">x</button>')
    assert guard.find_bad_handlers([str(tmp_path)]) == []
    assert guard.find_curly_contamination([str(tmp_path)]) == []


def test_handler_inside_script_body_or_comment_is_ignored(tmp_path):
    # onclick= strings inside JS-built HTML (script bodies) carry JS escaping
    # that is not standalone-parseable; commented-out markup never executes.
    _write(tmp_path, "js.html",
           "<script>var h = '<a onclick=\"broken(‘x’)\">';</script>\n"
           '<!-- <button onclick="dead(‘x’)">gone</button> -->')
    assert guard.find_curly_contamination([str(tmp_path)]) == []


# ---- smart-quote contamination in <script> blocks ------------------------------

def test_script_code_position_curly_flagged(tmp_path):
    _write(tmp_path, "cs.html", "<script>\nvar x = ‘oops’;\n</script>")
    bad = guard.find_curly_contamination([str(tmp_path)])
    assert bad and bad[0][1] == 2 and "CODE position" in bad[0][2]


def test_curly_inside_js_string_literal_is_legal(tmp_path):
    # 500+ shipped script blocks carry curly quotes INSIDE string literals as
    # bilingual display copy (e.g. “买入”, don’t) — those must never be flagged.
    _write(tmp_path, "disp.html",
           '<script>var a = "don’t “chase”"; var b = \'周期状态“买入”\'; // note: don’t\n</script>')
    assert guard.find_curly_contamination([str(tmp_path)]) == []


# ---- .j2 templates (curly scan only — node cannot parse Jinja) ------------------

def test_j2_curly_onclick_flagged_without_render(tmp_path):
    _write(tmp_path, "page.html.j2",
           '{% if p %}<button onclick="pick(‘a’)">x</button>{% endif %}')
    bad = guard.find_curly_contamination([str(tmp_path)])
    assert len(bad) == 1 and bad[0][0].endswith("page.html.j2")


def test_j2_jinja_syntax_is_not_flagged(tmp_path):
    _write(tmp_path, "ok.html.j2",
           '<button onclick="go(\'{{ slug }}\')">x</button>\n'
           "<script>var lbl = '{{ t('show','展开') }}'; {# don’t flag jinja comments #}</script>")
    assert guard.find_curly_contamination([str(tmp_path)]) == []


# ---- selftest + real tree -------------------------------------------------------

@needs_node
def test_selftest_is_green():
    assert guard.main(["--selftest"]) == 0


@needs_node
def test_real_tree_handlers_and_curly_clean():
    """site/ and templates/ must stay clean under the new checks (the guard's
    first tree-run caught the china_stocks.html truncated onclick, fixed in
    the PR that introduced this check)."""
    root = Path(__file__).resolve().parent.parent
    dirs = [str(root / d) for d in ("site", "templates") if (root / d).is_dir()]
    if not dirs:
        pytest.skip("site/templates not present")
    assert guard.find_bad_handlers(dirs) == []
    assert guard.find_curly_contamination(dirs) == []
