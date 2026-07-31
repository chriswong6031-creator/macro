"""Data-base shim regression — every site page must carry the R2 fetch shim.

The bug (nearly shipped in #1045): standalone page builders (documented usage
``python -m scripts.build_baskets``) rendered pages WITHOUT the data-base shim —
it was only added by the separate post-render step scripts/inject_data_base.py.
Committing a standalone builder's output silently stripped
``<script data-dbase src="data_base.js">`` and regressed the R2 rerouting of the
heavy per-ticker fetches. Fix: all builders write through lib.pages.write_page,
which injects the depth-aware tag at write time; the post-render sweep stays as
the idempotent safety net.

Three layers here:
  1. unit tests for lib.pages (inject_text / dbase_prefix / write_page)
  2. a repo tripwire — every COMMITTED site/**/*.html carries the marker, so a
     future write path that bypasses write_page fails CI the moment its output
     is committed
  3. a source guard — no scripts/engine module writes a literal *.html target
     with raw write_text

Run: .venv/bin/python -m pytest tests/test_site_shim.py -q
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import DBASE_MARKER, dbase_prefix, inject_text, write_page  # noqa: E402

ROOT = config.ROOT


# ---------------------------------------------------------------------------
# 1. lib.pages units
# ---------------------------------------------------------------------------

def test_inject_text_top_of_head_and_idempotent():
    html = "<!doctype html><html><head><meta charset='utf-8'></head><body>x</body></html>"
    out = inject_text(html, "")
    assert out.index(DBASE_MARKER) < out.index("<meta"), "shim must load before anything in <head>"
    assert "window.DATA_BASE" in out, "shim body must be INLINE (see below)"
    assert "new URL(u, location.href)" in out, "absolute same-origin data URLs must route to R2"
    assert "a.origin === location.origin" in out, "external fetches must not be rewritten"
    assert inject_text(out, "") == out, "second injection must be a no-op"


def test_shim_is_inlined_not_linked():
    """The shim is inlined, and must stay that way.

    It has to block at the top of <head> (it patches window.fetch before any page
    fetch), which as an external ref made it the one resource that stalls the HTML
    parser for a full round-trip on EVERY page — ~460ms at the measured origin
    TTFB, to deliver under 1KB. Unversioned, it also carries max-age=300
    must-revalidate, so returning visitors paid a revalidation RTT in that same
    blocking position. Reverting to <script src> silently restores that stall."""
    out = inject_text("<html><head></head><body></body></html>", "")
    assert "data_base.js" not in out, "shim must not be an external ref"
    assert out.count(DBASE_MARKER) == 1
    # the real payload, not a stub
    assert "window.DATA_BASE" in out and "window.fetch" in out
    # nothing that would close the tag early
    assert "</script" not in out[out.index(DBASE_MARKER):out.index("</script>")]


def test_inject_text_upgrades_legacy_external_tag():
    """Pages rendered before inlining carry <script data-dbase src=...>. The sweep
    must swap it for the inline body IN PLACE (position = ordering guarantee)."""
    for prefix in ("", "../", "../../"):
        legacy = (
            f'<html><head><script {DBASE_MARKER} src="{prefix}data_base.js"></script>'
            "<title>t</title></head><body></body></html>"
        )
        out = inject_text(legacy, prefix)
        assert "data_base.js" not in out, f"external ref survived at prefix {prefix!r}"
        assert out.count(DBASE_MARKER) == 1, "upgrade must not duplicate the shim"
        assert "window.DATA_BASE" in out
        assert out.index(DBASE_MARKER) < out.index("<title>"), "must stay first in <head>"
        assert inject_text(out, prefix) == out, "upgrade must be idempotent"


def test_inject_text_refreshes_stale_inline_body():
    """Changing data_base.js must update already-inlined committed pages.

    Merely finding ``data-dbase`` is not enough: every page carries its own copy
    of the wrapper, so leaving a stale body in place makes a shim hotfix a no-op
    until that individual page happens to be rebuilt.
    """
    stale = (
        f"<html><head><script {DBASE_MARKER}>"
        "(function(){window.DATA_BASE='https://stale.invalid';})();"
        "</script><title>t</title></head><body></body></html>"
    )
    out = inject_text(stale, "")
    assert "stale.invalid" not in out
    assert "new URL(u, location.href)" in out
    assert out.count(DBASE_MARKER) == 1
    assert out.index(DBASE_MARKER) < out.index("<title>")
    assert inject_text(out, "") == out


def test_inject_text_prefix_and_headless_fallback():
    # inline: the depth prefix no longer appears anywhere, at any depth
    assert "data_base.js" not in inject_text("<head></head>", "../")
    # no <head> -> lands before </body>
    out = inject_text("<html><body>x</body></html>", "")
    assert out.index(DBASE_MARKER) < out.index("</body>")


def test_dbase_prefix_depth(tmp_path):
    site = tmp_path / "site"
    (site / "basket").mkdir(parents=True)
    assert dbase_prefix(site / "baskets.html") == ""
    assert dbase_prefix(site / "basket" / "ai.html") == "../"
    # real repo paths
    assert dbase_prefix(ROOT / "site" / "macro.html") == ""
    assert dbase_prefix(ROOT / "site" / "basket" / "x.html") == "../"


def test_write_page_injects_depth_aware(tmp_path):
    site = tmp_path / "site"
    sub = site / "basket"
    sub.mkdir(parents=True)
    write_page(site / "baskets.html", "<html><head></head><body></body></html>")
    write_page(sub / "ai.html", "<html><head></head><body></body></html>")
    # inlined -> identical payload at every depth, no src prefix to get wrong
    for page in (site / "baskets.html", sub / "ai.html"):
        text = page.read_text()
        assert f"<script {DBASE_MARKER}>" in text
        assert "window.DATA_BASE" in text and "data_base.js" not in text


def test_shim_body_cache_is_per_source_not_per_process(tmp_path, monkeypatch):
    """A failed read must not pin the REST of the process to the external ref.

    Builder tests patch lib.config.ROOT to a fixture tree that has no templates/
    (tests/test_build_leader_radar.py does). With one global cache slot, the first
    write_page under such a patch cached the failure forever, so every later page
    written in that pytest process came out with `<script data-dbase src=…>`
    instead of the inline shim — turning this file red only when it happened to
    run after that suite, with nothing in the failure pointing at the cause."""
    from lib import pages

    monkeypatch.setattr(pages.config, "ROOT", tmp_path)  # no templates/data_base.js
    fallback = inject_text("<html><head></head><body></body></html>", "")
    assert 'src="data_base.js"' in fallback, "unreadable shim must fall back, not vanish"

    monkeypatch.undo()  # back to the real repo root
    recovered = inject_text("<html><head></head><body></body></html>", "")
    assert "window.DATA_BASE" in recovered and "data_base.js" not in recovered


def test_write_page_keeps_existing_marker(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    pre = inject_text("<html><head></head><body></body></html>", "")
    write_page(site / "a.html", pre)
    assert (site / "a.html").read_text().count(DBASE_MARKER) == 1


# ---------------------------------------------------------------------------
# 2. repo tripwire — committed pages must all carry the shim
# ---------------------------------------------------------------------------

def test_every_committed_site_page_has_shim():
    site = ROOT / "site"
    missing = []
    for page in sorted(site.rglob("*.html")):
        try:
            head = page.read_text(errors="ignore")
        except OSError:
            continue
        if DBASE_MARKER not in head:
            missing.append(str(page.relative_to(site)))
    assert not missing, (
        f"{len(missing)} committed site page(s) lack the data-base shim "
        f"(R2 rerouting regression — write via lib.pages.write_page): {missing[:10]}"
    )


# ---------------------------------------------------------------------------
# 3. source guard — no raw write_text on an *.html target
#
# Two layers, because the cheap one has a structural blind spot:
#
#   3a. line regex — catches a LITERAL target written on the spot,
#       `(site / "x.html").write_text(...)`.
#   3b. AST pass  — catches the two-line form the regex can never see:
#           out = site_dir / "x.html"     # ← literal here
#           out.write_text(rendered)      # ← write here, nothing to match on
#       which is how build_leader_radar (#3635) and eight more builders shipped
#       shim-less pages under a green guard. The committed copies looked fine
#       only because the render lane's inject_data_base sweep heals them after
#       the fact, so the defect was visible ONLY in a standalone builder run.
#
# Neither layer can see a target whose ".html" never appears in the source at all
# (build_free_content's article write derives it from content frontmatter). Layer
# 2 above — the committed-page tripwire — is the only backstop for that shape,
# and tests/test_builder_shim_writes.py runs the builders to prove it.
# ---------------------------------------------------------------------------

_RAW_HTML_WRITE = re.compile(r"""\.html['")\] ]*\.write_text\(""")
# files that legitimately call write_text on page paths (the sweeps themselves).
# Page builders NEVER belong here — they belong on write_page.
_ALLOW = {"scripts/inject_data_base.py", "scripts/inject_wh_banner.py"}

# Throwaway-directory factories. A page written under one of these is a headless
# render wrapper or a selftest fixture, never a shipped site page — make_favicon,
# make_launch_card, engine/marketing/chart_render and check_ruling_conflicts all
# write a *.html into a TemporaryDirectory to feed Chrome or a selftest.
_TMP_FACTORIES = {"TemporaryDirectory", "NamedTemporaryFile", "mkdtemp", "mkstemp"}


def _guarded_sources():
    """scripts/ + engine/, recursively — a builder in a subpackage writes pages
    the same way one at the top level does."""
    for pkg in ("scripts", "engine"):
        yield from sorted((ROOT / pkg).rglob("*.py"))


def _mentions_html_literal(node: ast.AST) -> bool:
    """True if any string constant in this expression carries '.html' — covers
    `site / "x.html"` and f-strings like `d / f"{slug}.html"` alike."""
    return any(
        isinstance(n, ast.Constant) and isinstance(n.value, str) and ".html" in n.value
        for n in ast.walk(node)
    )


def _references_html_name(node: ast.AST, html_names: set[str]) -> bool:
    """True if this expression is built from a name already known to carry a page
    path — so html-ness propagates the way the temp-dir taint does.

    Without this the guard misses the module-constant idiom, which is common here:

        PAGE_OUT = "qa_bottom_sensors.html"   # ← the only literal in the file
        ...
        out = site / PAGE_OUT                 # no Constant → `out` unmarked
        out.write_text(html)                  # ← would slip through

    scripts/build_qa_bottom_sensors.py is exactly that shape, and the first
    version of this guard (#3652) returned [] for it.
    """
    return any(isinstance(n, ast.Name) and n.id in html_names for n in ast.walk(node))


def _is_tmp_expr(node: ast.AST, tmp_names: set[str]) -> bool:
    """True if this expression is rooted in a throwaway directory — either a
    tempfile factory call, or a name already known to hold one."""
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id in tmp_names:
            return True
        if isinstance(n, ast.Call):
            fn = n.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in _TMP_FACTORIES:
                return True
    return False


def _pairs(targets, value):
    """Zip tuple-unpacking targets with their values so `page, out = a/'w.html',
    b/'o.png'` taints only `page`. Falls back to (target, whole value)."""
    for t in targets:
        if isinstance(t, ast.Tuple) and isinstance(value, ast.Tuple) and len(t.elts) == len(value.elts):
            yield from zip(t.elts, value.elts)
        else:
            yield t, value


def _scan_scope(scope, html_names: set[str], tmp_names: set[str], out: list):
    """Bind names, flag writes, recurse — WITHOUT crossing into nested scopes.

    Scope discipline is the whole point: a plain ast.walk pairs an `out` assigned
    in one function with an unrelated `out.write_text` in another, which is how a
    naive version of this guard invents offenders (it reported build_darkpool_desk
    and build_options_screener, neither of which writes a page that way).
    Nested functions DO inherit their enclosing function's names (real closures);
    class bodies do not leak into their methods, matching Python's own rules.
    """
    html_names, tmp_names = set(html_names), set(tmp_names)
    nested = []

    def walk(node):
        # every def/lambda/class in this body opens its OWN scope — recurse later,
        # with this scope's names as the enclosing binding set
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            nested.append(node)
            return
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None and _is_tmp_expr(item.context_expr, tmp_names):
                    for n in ast.walk(item.optional_vars):
                        if isinstance(n, ast.Name):
                            tmp_names.add(n.id)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for tgt, val in _pairs(targets, node.value):
                names = {n.id for n in ast.walk(tgt) if isinstance(n, ast.Name)}
                if _is_tmp_expr(val, tmp_names):
                    tmp_names.update(names)     # taint propagates down the chain
                elif _mentions_html_literal(val) or _references_html_name(val, html_names):
                    html_names.update(names)    # ...and so does html-ness
        for child in ast.iter_child_nodes(node):
            walk(child)

    for stmt in scope.body:
        walk(stmt)

    def flag(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "write_text"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in html_names
            and node.func.value.id not in tmp_names
        ):
            out.append((node.lineno, node.func.value.id))
        for child in ast.iter_child_nodes(node):
            flag(child)

    for stmt in scope.body:
        flag(stmt)

    for n in nested:
        if isinstance(n, ast.ClassDef):
            _scan_scope(n, set(), set(), out)
        elif isinstance(n, ast.Lambda):
            _scan_scope(ast.Module(body=[ast.Expr(n.body)], type_ignores=[]), html_names, tmp_names, out)
        else:
            _scan_scope(n, html_names, tmp_names, out)


def _raw_html_writes(source: str) -> list:
    """[(line, varname)] for every `<name>.write_text(...)` on an *.html name."""
    out: list = []
    _scan_scope(ast.parse(source), set(), set(), out)
    return sorted(out)


def test_no_raw_write_text_on_html_targets():
    """Layer 3a — the literal, same-line form."""
    offenders = []
    for py in _guarded_sources():
        rel = str(py.relative_to(ROOT))
        if rel in _ALLOW:
            continue
        for i, line in enumerate(py.read_text(errors="ignore").splitlines(), 1):
            if _RAW_HTML_WRITE.search(line):
                offenders.append(f"{rel}:{i}")
    assert not offenders, (
        "site pages must be written via lib.pages.write_page (keeps the data-base "
        f"shim in standalone builder runs): {offenders}"
    )


def test_no_raw_write_text_on_html_variables():
    """Layer 3b — the variable form the regex is structurally blind to."""
    offenders = []
    for py in _guarded_sources():
        rel = str(py.relative_to(ROOT))
        if rel in _ALLOW:
            continue
        try:
            hits = _raw_html_writes(py.read_text(errors="ignore"))
        except SyntaxError:  # not ours to police here
            continue
        offenders += [f"{rel}:{line} ({name})" for line, name in hits]
    assert not offenders, (
        f"{len(offenders)} page write(s) bypass lib.pages.write_page via a variable "
        "target — the data-base shim is dropped in any standalone builder run "
        f"(the render lane's inject_data_base sweep hides this on committed pages): {offenders}"
    )


def test_source_guard_fires_on_synthetic_offenders():
    """Selftest: the gate must fire on the real shapes and stay quiet on the rest.

    Without this, layer 3b could silently stop matching (a refactor of the scope
    walker, a new AST node type) and read as green forever — the same failure mode
    that let the original regex pass while nine builders shipped shim-less pages.
    """
    # the two-line builder shape (build_leader_radar #3635, and eight more)
    assert _raw_html_writes(
        "def build(site_root, rendered):\n"
        "    html_out = site_root / 'leader_radar.html'\n"
        "    html_out.write_text(rendered)\n"
    ) == [(3, "html_out")]

    # an f-string target, and a target assigned many lines from its write
    assert _raw_html_writes(
        "def build(d, slug, html):\n"
        "    out = d / f'{slug}.html'\n"
        "    out.parent.mkdir(parents=True, exist_ok=True)\n"
        "    log('rendering')\n"
        "    out.write_text(html)\n"
    ) == [(5, "out")]

    # cross-function false pair: `out` here is two unrelated locals
    assert _raw_html_writes(
        "def a(site):\n"
        "    out = site / 'x.html'\n"
        "    return out\n"
        "def b(payload):\n"
        "    out = payload['dest']\n"
        "    out.write_text('data')\n"
    ) == []

    # headless-render / selftest wrapper in a throwaway dir — not a site page
    assert _raw_html_writes(
        "import tempfile\n"
        "from pathlib import Path\n"
        "def render(svg):\n"
        "    with tempfile.TemporaryDirectory() as td:\n"
        "        tdp = Path(td)\n"
        "        wrapper = tdp / 'w.html'\n"
        "        wrapper.write_text(svg)\n"
    ) == []

    # ...and the taint survives a rename chain (check_ruling_conflicts' shape)
    assert _raw_html_writes(
        "import tempfile\n"
        "from pathlib import Path\n"
        "def selftest():\n"
        "    with tempfile.TemporaryDirectory() as tmp_dir:\n"
        "        tmp_path = Path(tmp_dir)\n"
        "        site_dir = tmp_path / 'site'\n"
        "        fake = site_dir / 'test_h2.html'\n"
        "        fake.write_text('<div/>')\n"
    ) == []

    # the module-constant idiom — the literal is nowhere near the write
    # (scripts/build_qa_bottom_sensors.py's shape; #3652's guard returned [] here)
    assert _raw_html_writes(
        "PAGE_OUT = 'qa_bottom_sensors.html'\n"
        "def build(site, html):\n"
        "    out = site / PAGE_OUT\n"
        "    out.write_text(html)\n"
    ) == [(4, "out")]

    # ...and it must survive one more hop through a local
    assert _raw_html_writes(
        "PAGE_OUT = 'x.html'\n"
        "def build(site, html):\n"
        "    target = site / PAGE_OUT\n"
        "    final = target\n"
        "    final.write_text(html)\n"
    ) == [(5, "final")]

    # a constant with no .html must NOT arm the propagation
    assert _raw_html_writes(
        "DEST = 'feed.xml'\n"
        "def build(site, rss):\n"
        "    out = site / DEST\n"
        "    out.write_text(rss)\n"
    ) == []

    # write_page is the fix, and must not be flagged
    assert _raw_html_writes(
        "def build(site_root, rendered):\n"
        "    html_out = write_page(site_root / 'leader_radar.html', rendered)\n"
        "    log(html_out)\n"
    ) == []
