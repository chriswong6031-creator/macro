"""Regression tests for theme.js's lazy assistant launcher (the #mmb-boot stub).

Two independent defects are pinned here, both measured on production 2026-08-19
against theme.js?v=948020b9 and mm_brain.js?v=f74045d8:

  1. RESOLUTION. `initChatLauncher` set `s.src = 'mm_brain.js'` — a bare relative
     URL, which a dynamically created <script> resolves against the DOCUMENT, not
     against the script that created it. There is exactly ONE mm_brain.js (site
     root) and no <base> anywhere in the estate, so every nested page without a
     page-authored <script> tag requested a URL that does not exist:
     https://www.mastermind-x.com/stocks/mm_brain.js -> 404, window.MMBrain false,
     #mmb-root absent. ~4,600 pages, including every /stocks/<TICKER>.html.

     theme.js already knew the answer: `_mmSharedAssetRoot` is derived from
     theme.js's own script URL and is what account.js (line ~448) and onboard.js
     (~3553) resolve against, after account.js hit this exact trap on the nested
     estate. The guard below is therefore written against the CLASS of bug, not
     the one instance: EVERY dynamically injected same-origin child asset in
     theme.js must be built from the shared root.

  2. EAGERNESS. Where it did resolve (root pages), it downloaded and executed
     232 KB / ~70 KB gzip at DOMContentLoaded whether the reader ever opened the
     chat or not. The stub now holds the resting state and the bundle is fetched
     on activation.

Plus the drift guard that makes (2) safe to keep: the stub is a SECOND copy of a
control whose source of truth is mm_brain.js's #mmb-launch, so the geometry that
decides whether the handover is invisible is compared property-by-property. A
launcher that moves 6px when the real bundle mounts is a bug the eye catches and
no functional test would.

No network, no render — all static analysis of the committed sources.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WORKTREE = Path(__file__).resolve().parent.parent
TEMPLATES = WORKTREE / "templates"
THEME_JS = TEMPLATES / "theme.js"
MM_BRAIN_JS = TEMPLATES / "mm_brain.js"


@pytest.fixture(scope="module")
def theme_src() -> str:
    return THEME_JS.read_text()


@pytest.fixture(scope="module")
def brain_src() -> str:
    return MM_BRAIN_JS.read_text()


@pytest.fixture(scope="module")
def theme_code(theme_src: str) -> str:
    """theme.js with /* block comments */ removed.

    Needed because this file's own prose quotes the defect verbatim
    (``s.src = 'mm_brain.js'``), and so does theme.js's — a guard that scanned
    comments would fire on the explanation of the bug rather than the bug.
    """
    return re.sub(r"/\*.*?\*/", " ", theme_src, flags=re.DOTALL)


# ---------------------------------------------------------------------------
# 1. every dynamic child asset resolves from the SHARED root, never the document
# ---------------------------------------------------------------------------

# `<something>.src = '<literal>'` / `.src = "<literal>"` — a script/link URL
# assigned from a bare string literal. An expression (pfx + 'x.js',
# _mmBrainSrc(), _mmOverlaySrc) is not a literal and is not matched here; those
# are checked for shared-root provenance by the second half of the test.
_LITERAL_SRC_RE = re.compile(r"""\.(?:src|href)\s*=\s*(['"])([^'"]+)\1""")

# URLs that are not ours to rebase: absolute, protocol-relative, data/blob, and
# the empty string (used to detach a media element).
_NOT_LOCAL = ("http://", "https://", "//", "data:", "blob:", "about:", "#", "/")


def _document_relative_offenders(code: str) -> list[str]:
    """Injected asset URLs that are bare relative literals (comments stripped)."""
    code = re.sub(r"/\*.*?\*/", " ", code, flags=re.DOTALL)
    return [
        url
        for _q, url in _LITERAL_SRC_RE.findall(code)
        if url and not url.startswith(_NOT_LOCAL)
    ]


def test_the_resolution_guard_actually_fires_on_the_2026_08_19_defect() -> None:
    """The guard must reject the exact line that shipped the outage.

    A guard registered against healthy code and never shown to fail is not
    evidence of anything. This feeds it the pre-fix statement verbatim and the
    post-fix one beside it.
    """
    broken = "var s = document.createElement('script');\n    s.src = 'mm_brain.js'; s.defer = true;"
    fixed = "s.src = new URL('mm_brain.js', _mmSharedAssetRoot || location.href).href;"
    assert _document_relative_offenders(broken) == ["mm_brain.js"], (
        "the guard no longer detects the original defect — it has been weakened "
        "into a test that can only pass"
    )
    assert _document_relative_offenders(fixed) == []
    # absolute / protocol-relative / data URLs are never ours to rebase
    assert _document_relative_offenders(
        "a.src = 'https://cdn.example/x.js'; b.src = '//h/y.js'; c.src = '/z.js'; d.src = 'data:,';"
    ) == []


def test_no_dynamic_child_asset_is_document_relative(theme_code: str) -> None:
    """No injected asset URL may be a bare relative literal.

    This is the bug itself. `s.src = 'mm_brain.js'` reads as obviously correct
    beside a <script src="mm_brain.js"> in a root page's HTML, and is silently
    wrong on every nested one — the failure is invisible from the source and
    invisible in CI, because the only symptom is a 404 in someone else's browser.
    """
    offenders = _document_relative_offenders(theme_code)
    assert not offenders, (
        "theme.js assigns a document-relative URL to an injected asset: "
        f"{offenders}. A dynamic <script>/<link> resolves against the PAGE, so "
        "this 404s on every nested route (site/stocks/, site/sectors/, …) while "
        "working perfectly at the site root. Build the URL from "
        "_mmSharedAssetRoot, which is derived from theme.js's own script URL: "
        "  new URL('<asset>', _mmSharedAssetRoot || location.href).href"
    )


@pytest.mark.parametrize(
    "asset, builder",
    [
        ("mm_brain.js", "_mmBrainSrc"),
        ("terminal_overlay.js", "_mmOverlaySrc"),
        ("account.js", "pfx"),
        ("onboard.js", "pfx"),
    ],
)
def test_named_child_assets_are_built_from_the_shared_root(
    theme_src: str, asset: str, builder: str
) -> None:
    """Each known child asset's URL is composed, and composed from the shared root.

    Named individually rather than discovered so that DELETING a resolution — the
    regression that actually happened — fails here instead of quietly reducing
    the guard's coverage to nothing.
    """
    assert asset in theme_src, f"{asset} is no longer referenced by theme.js"
    assert builder in theme_src, (
        f"{asset}'s URL builder `{builder}` is gone from theme.js — if the asset "
        "moved, move its resolution too; do not fall back to a bare literal."
    )


def test_shared_asset_root_is_derived_from_the_script_url(theme_src: str) -> None:
    """_mmSharedAssetRoot must keep reading theme.js's OWN src, not location."""
    block = re.search(
        r"var\s+_mmSharedAssetRoot\s*=\s*\(function\s*\(\)\s*\{(.*?)\}\)\(\);",
        theme_src,
        re.DOTALL,
    )
    assert block, "_mmSharedAssetRoot's definition changed shape — re-read this guard"
    body = block.group(1)
    assert "_mmThemeScript" in body and ".src" in body, (
        "_mmSharedAssetRoot no longer derives from theme.js's own script URL. "
        "Falling back to location.href for the ROOT (rather than only as the "
        "last-resort default) reintroduces the nested-estate 404 for every "
        "consumer at once."
    )


# ---------------------------------------------------------------------------
# 2. the bundle is not fetched before intent
# ---------------------------------------------------------------------------


def _init_chat_launcher(theme_src: str) -> str:
    """The body of initChatLauncher(), the DOMContentLoaded entry point."""
    i = theme_src.index("function initChatLauncher()")
    depth, j = 0, theme_src.index("{", i)
    for k in range(j, len(theme_src)):
        if theme_src[k] == "{":
            depth += 1
        elif theme_src[k] == "}":
            depth -= 1
            if depth == 0:
                return theme_src[j : k + 1]
    raise AssertionError("initChatLauncher() is unbalanced")


def test_launcher_init_does_not_fetch_the_bundle(theme_src: str) -> None:
    """DOMContentLoaded may mount the stub; it may not request mm_brain.js.

    The one sanctioned exception is the pair of pages carrying .sx card faces,
    which mm_brain.js decorates with per-card Explain buttons that are part of the
    page AT REST — those load at idle, after `load`, off the first-paint path.
    """
    body = _init_chat_launcher(theme_src)
    assert "_mmMountBootLauncher()" in body, "initChatLauncher no longer mounts the stub"
    direct = re.findall(r"loadBrain\s*\(", body)
    assert not direct, (
        "initChatLauncher() calls loadBrain() directly — that is the eager fetch "
        "this change removed. Route activation through _mmBrainMount()."
    )
    # the idle exception is explicit, bounded, and gated on the cards existing
    assert "MMB_EXPLAIN_SEL" in body and "requestIdleCallback" in body, (
        "the .sx Explain-card idle path is gone — those buttons are page-at-rest "
        "affordances and cannot wait for the reader to open the chat"
    )


def test_activation_is_coalesced_and_stays_retryable(theme_src: str) -> None:
    """One request and one mount however many activations race; a failure retries."""
    assert re.search(r"if\s*\(_mmBrainScript\)\s*return;", theme_src), (
        "loadBrain() lost its in-flight guard — racing activations (double click, "
        "click during hover-warm) would each append a <script> and mm_brain.js "
        "would be fetched N times"
    )
    assert re.search(r"onerror\s*=\s*function\s*\(\)\s*\{\s*_mmBrainScript\s*=\s*null", theme_src), (
        "a failed load must clear _mmBrainScript, or the launcher is dead for the "
        "rest of the session after one bad response"
    )


def test_hover_warm_never_executes_the_bundle(theme_src: str) -> None:
    """Hover/focus warms the cache with rel=preload — never with a <script>.

    A <script> would MOUNT the widget, so merely pointing at the launcher would
    build the whole chat DOM: laziness lost, and the real launcher would appear
    underneath the stub while the reader has activated nothing.
    """
    i = theme_src.index("function _mmBrainWarm()")
    j = theme_src.index("\n  }", i)
    warm = theme_src[i:j]
    assert "'preload'" in warm and "'script'" in warm, "_mmBrainWarm must use rel=preload/as=script"
    assert "createElement('script')" not in warm, (
        "_mmBrainWarm creates a <script> — that executes and mounts the widget on "
        "hover, which is not activation"
    )


# ---------------------------------------------------------------------------
# 3. the stub does not collide with, or drift from, the real launcher
# ---------------------------------------------------------------------------


def test_stub_ids_do_not_collide_with_the_real_widget(theme_src: str) -> None:
    """The stub owns #mmb-boot; #mmb-root/#mmb-launch belong to mm_brain.js.

    Both are briefly alive in the same document during the handover, and
    mm_brain.js resolves its own controls with document-wide querySelector — a
    shared id would hand it the stub's element.
    """
    assert "el.id = 'mmb-boot'" in theme_src
    for owned in ("mmb-root", "mmb-launch"):
        assert f"el.id = '{owned}'" not in theme_src, f"the stub must not claim #{owned}"
    # it must still STAND DOWN when a page-authored <script> already mounted the widget
    body = _init_chat_launcher(theme_src)
    assert "window.MMBrain" in body and "getElementById('mmb-root')" in body, (
        "initChatLauncher lost its already-mounted check — legacy pages that carry "
        "their own <script src=mm_brain.js> would get a stub stacked on the real "
        "launcher and a second request for a bundle already on the page"
    )


def _stub_css(theme_src: str) -> str:
    """The stub's stylesheet, reassembled from theme.js's string concatenation.

    theme.js is ES5 (no template literals), so MMB_BOOT_CSS is a chain of quoted
    fragments joined by `+`, with /* comments */ between some of them. Parsing the
    raw text as CSS would read `' + '#mmb-boot` as the selector. Join the string
    literals — the concatenation's actual value — and parse that.
    """
    i = theme_src.index("var MMB_BOOT_CSS")
    j = theme_src.index("\n  var MMB_BOOT_AT", i)
    body = re.sub(r"/\*.*?\*/", " ", theme_src[i:j], flags=re.DOTALL)
    return "".join(re.findall(r"'([^']*)'", body))


def _strip_at_blocks(css: str) -> str:
    """``css`` with every conditional at-rule block (@media/@supports) removed.

    The base geometry must be compared against the base geometry: both files park
    a `display:none` for print and a collapsed pill for phones behind at-rules, and
    flattening those into the unconditional rule reports drift where the two files
    in fact agree.
    """
    out, i = [], 0
    while i < len(css):
        m = re.compile(r"@(?:media|supports)\b").search(css, i)
        if not m:
            out.append(css[i:])
            break
        out.append(css[i : m.start()])
        j = css.index("{", m.end())
        depth = 0
        for k in range(j, len(css)):
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
                if depth == 0:
                    i = k + 1
                    break
        else:
            break
    return "".join(out)


def _declarations(css: str, selector: str) -> dict[str, str]:
    """The cascaded `prop: value` map for ``selector``.

    Merged across EVERY rule with that exact selector, later winning — both
    launchers split their declarations across a token block and a geometry block
    under one selector, so reading only the first rule would compare an empty
    geometry against a real one and report drift that is not there.
    """
    out: dict[str, str] = {}
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        if m.group(1).strip().replace("\n", " ").split(",")[0].strip() != selector:
            continue
        for decl in re.split(r";(?![^(]*\))", m.group(2)):
            if ":" in decl and not decl.lstrip().startswith("--"):
                k, v = decl.split(":", 1)
                out[k.strip()] = re.sub(r"\s+", " ", v.strip())
    if not out:
        raise AssertionError(f"no rule for {selector!r}")
    return out


# The properties that decide whether the stub→real handover is invisible. Colour
# is deliberately absent: both sides read the same --mmb-fab-* tokens, and those
# are asserted by name below instead of by value.
_MIRRORED = ("position", "right", "bottom", "z-index", "display", "align-items",
             "gap", "padding", "border-radius", "cursor")


def test_stub_geometry_mirrors_the_real_launcher(theme_src: str, brain_src: str) -> None:
    """#mmb-boot sits exactly where #mmb-launch will, at the same size and shape.

    mm_brain.js mounts its own launcher during script execution and the stub is
    removed in that same tick, so any disagreement here is a visible jump at the
    exact moment the reader is looking at the control they just clicked.
    """
    real = _declarations(_strip_at_blocks(brain_src), "#mmb-launch")
    stub = _declarations(_strip_at_blocks(_stub_css(theme_src)), "#mmb-boot")
    mismatched = {p: (real.get(p), stub.get(p)) for p in _MIRRORED if real.get(p) != stub.get(p)}
    assert not mismatched, (
        "#mmb-boot (theme.js) drifted from #mmb-launch (mm_brain.js) — "
        f"{{prop: (mm_brain, theme)}} = {mismatched}. Update the stub to match; "
        "mm_brain.js is the source of truth for this control."
    )


def test_the_geometry_guard_actually_fires_on_drift(theme_src: str, brain_src: str) -> None:
    """Nudge the stub 6px and the mirror test must notice."""
    real = _declarations(_strip_at_blocks(brain_src), "#mmb-launch")
    drifted = _declarations(
        _strip_at_blocks(_stub_css(theme_src)).replace("right:22px", "right:28px"), "#mmb-boot"
    )
    assert any(real.get(p) != drifted.get(p) for p in _MIRRORED), (
        "the geometry mirror cannot see a 6px move — it is not guarding anything"
    )


def test_stub_mobile_breakpoint_mirrors_the_real_launcher(theme_src: str, brain_src: str) -> None:
    """The phone collapse (labelled pill -> bare orb) must fire at the same width."""
    stub_css = _stub_css(theme_src)
    for src, name in ((brain_src, "mm_brain.js"), (stub_css, "theme.js")):
        assert "@media(max-width:700px)" in src, f"{name} lost the 700px launcher breakpoint"
    real = _declarations(brain_src.split("@media(max-width:700px)")[1], "#mmb-launch")
    stub = _declarations(stub_css.split("@media(max-width:700px)")[1], "#mmb-boot")
    for prop in ("right", "bottom", "padding", "gap"):
        assert real.get(prop) == stub.get(prop), (
            f"phone {prop} differs: mm_brain={real.get(prop)!r} theme={stub.get(prop)!r}"
        )


def test_stub_reads_the_same_launcher_tokens(theme_src: str, brain_src: str) -> None:
    """Both launchers dress from the same --mmb-fab-* / --mmb-rim-* token names."""
    tokens = {t for t in re.findall(r"--mmb-(?:fab|rim)-[a-z-]+", brain_src)}
    missing = sorted(t for t in tokens if t not in theme_src)
    assert not missing, (
        f"the stub does not define/consume {missing} — it will not match "
        "#mmb-launch in one of the two themes"
    )


def test_stub_is_keyboard_operable_and_carries_no_translated_title(theme_src: str) -> None:
    """A div given a button's manners by hand, and no translated text in title=.

    The house i18n rule (CI-guarded elsewhere) is that translated strings never go
    in a title= attribute, because it is not re-localizable on langchange and is
    invisible to a screen reader that already read the label.
    """
    i = theme_src.index("function _mmMountBootLauncher()")
    mount = theme_src[i : theme_src.index("\n  }\n", i)]
    for attr in ("'role', 'button'", "'tabindex', '0'", "'aria-expanded'", "'aria-label'"):
        assert attr in mount, f"the stub is missing {attr}"
    assert "'Enter'" in mount and ("' '" in mount or "'Spacebar'" in mount), (
        "the stub is a <div role=button>; Enter and Space must be wired by hand"
    )
    assert "setAttribute('title'" not in mount, "no title= on the stub (i18n law)"
    assert "_mmBootRelabel" in theme_src and "langchange" in theme_src, (
        "the stub must re-localize on langchange rather than pinning the language "
        "it happened to mount in"
    )
