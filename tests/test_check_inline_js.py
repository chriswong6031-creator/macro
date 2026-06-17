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
