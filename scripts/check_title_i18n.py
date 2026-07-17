#!/usr/bin/env python3
"""Static guard: no translated text in title= attributes, no markup in <title> RCDATA.

The i18n rule is that translated text NEVER goes in HTML attributes: the dual-span
l-en/l-zh mechanism cannot operate inside an attribute, so a bilingual native tooltip
shows BOTH languages mashed together, whatever the toggle says. The same goes for a
`{{ t(...) }}` interpolation in an attribute — t() renders dual-span markup, which
inside an attribute becomes literal `<span ...>` garbage text.

The failure this guard catches: a `title="..."` whose value contains CJK characters
or a t()/td() interpolation. Both were live violations found in the #1095 review (e.g.
the W6-C HOLD chip's long bilingual title). The fix pattern (shipped with this guard)
is either:

  • data-tip-en= / data-tip-zh= on the same element — theme.js shows ONE body-appended
    popover whose dual-span body follows [data-lang] (hover on desktop, tap on mobile;
    the generalisation of the #1061 .nb-cau icon+popover pattern), or
  • a static ENGLISH-ONLY title (the same allowance as static English aria-labels) on
    pages that ship no JS (us_stocks_v2, foresight), or
  • dropping a title that merely repeats the visible dual-span chip text.

The <title> ELEMENT is the same class through a different door (#2705): <title> is
RCDATA, so markup inside it is never parsed — a `{{ t(...) }}` / `{{ td(...) }}` in a
template <title> (or its {% block title %}) ships literal '<span class="l-en">…' as
the browser-tab text. The #2705 sweep fixed 52 templates plus their rendered site
copies; the element rules keep the class closed:

  • templates/*.j2 — any LINE where a <title> element or {% block title %} co-occurs
    with a t()/td() interpolation fails. Line-scoped ON PURPOSE: committee.html.j2
    builds SVG tooltip strings in JavaScript ('<title>' + esc(tip) + '</title>'),
    and JS concatenation never carries a Jinja t()/td() on the same line, so it
    cannot trip. A {% block title %} body is additionally region-scanned so a
    wrapped block cannot hide the call on its own line (the block tag never appears
    in JS, so a region scan is safe where it is not for bare <title>).
  • site/**/*.html — the page <title> (the FIRST title element in the file; inline
    SVG <title> tooltips and JS strings all come later) must not contain '<span',
    scanned multi-line-safe.

Plain CJK inside a <title> ELEMENT is ALLOWED (baskets_china's '· 同花顺',
flow_desk's hardcoded bilingual title): page titles are plain English with optional
literal CJK — the element rule is about markup-in-RCDATA, not language. The fix for
an element hit is to pass plain strings (never t()/td()) and let the H1 carry the
dual-span bilingual heading.

This guard turns the whole class of drift into a pre-merge failure instead of a review
find. It runs in the same ci.yml / pages.yml gates as check_nav_gap.py and
check_nav_mega.py, sweeping TEMPLATE SOURCE (templates/) and rendered pages (site/).

Usage:
    python -m scripts.check_title_i18n [DIR_OR_FILE ...]   # default: templates/ site/
    python -m scripts.check_title_i18n --self-test
Exit codes: 0 = all clean / self-test passed · 1 = violation(s) / self-test failed.
"""
from __future__ import annotations

import os
import re
import sys

# CJK unified ideographs + extension A, CJK punctuation, fullwidth forms.
_CJK = re.compile(r"[一-鿿㐀-䶿　-〿＀-￯]")

# A title attribute and its quoted value (either quote style). [^"']* deliberately
# spans newlines so a wrapped attribute is still caught.
_TITLE = re.compile(r"title\s*=\s*(\"[^\"]*\"|'[^']*')")

# t()/td() interpolation markers (dual-span renderers — must never run inside an
# attribute or a <title> element).
_T_CALL = re.compile(r"\{\{-?\s*td?\(")

# A zh-named variable interpolated into the title — the DATA-DRIVEN channel: no literal
# CJK in the template, but the rendered title carries Chinese (e.g. the old
# `title="{{ al.line }} · {{ al.line_zh }}"` join, or the qmark() macro's `{{ zh }}`).
_ZH_VAR = re.compile(r"\{\{[^}]*(?:\bzh\b|_zh\b|\.zh\b)")

# ---- <title> element (RCDATA) rules — #2705 -------------------------------------
# A <title> element open or a {% block title %} open, and a t()/td() call anywhere
# inside one {{ ... }} interpolation ([^{}] keeps the match within a single pair of
# braces; \b keeps 'format(' / 'sort(' from matching the t/td token).
_TITLE_OPEN = re.compile(r"<title[\s>]", re.IGNORECASE)
_BLOCK_TITLE_OPEN = re.compile(r"\{%-?\s*block\s+title\b")
_T_TD_INTERP = re.compile(r"\{\{[^{}]*?\btd?\(")

# A whole {% block title %}…{% endblock %} body (may wrap across lines).
_BLOCK_TITLE_REGION = re.compile(r"\{%-?\s*block\s+title\b.*?\{%-?\s*endblock", re.S)

# The page <title> of a rendered file: first title element, body up to the close
# (<\\?/ also stops at a JS-escaped '<\/title>' so a script string stays a short span).
_FIRST_TITLE = re.compile(r"<title[^>]*>(.*?)<\\?/title", re.S | re.I)

_EXTS = (".j2", ".html", ".htm")


def find_violations(paths: list[str]):
    """Return [(path, line, reason, excerpt)] for every title= attribute carrying CJK
    or t()/td(), and every <title> element carrying dual-span markup (RCDATA rule)."""
    files: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, names in os.walk(p):
                files.extend(os.path.join(root, n) for n in names if n.endswith(_EXTS))
        else:
            files.append(p)

    out = []
    for path in sorted(set(files)):
        try:
            src = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue

        # -- title= ATTRIBUTE rules (all scanned files) --
        for m in _TITLE.finditer(src):
            val = m.group(1)[1:-1]
            reasons = []
            if _CJK.search(val):
                reasons.append("CJK in title")
            if _T_CALL.search(val):
                reasons.append("t() in title")
            if path.endswith(".j2") and _ZH_VAR.search(val):
                reasons.append("zh variable in title")
            if reasons:
                line = src.count("\n", 0, m.start()) + 1
                out.append((path, line, " + ".join(reasons), val[:90]))

        # -- <title> ELEMENT rules (RCDATA) --
        if path.endswith(".j2"):
            flagged: set[int] = set()
            for i, text in enumerate(src.splitlines(), 1):
                if (_TITLE_OPEN.search(text) or _BLOCK_TITLE_OPEN.search(text)) \
                        and _T_TD_INTERP.search(text):
                    flagged.add(i)
                    out.append((path, i, "t()/td() in <title> RCDATA", text.strip()[:90]))
            for m in _BLOCK_TITLE_REGION.finditer(src):
                call = _T_TD_INTERP.search(m.group(0))
                if call:
                    line = src.count("\n", 0, m.start() + call.start()) + 1
                    if line not in flagged:
                        excerpt = " ".join(m.group(0).split())[:90]
                        out.append((path, line, "t()/td() in <title> RCDATA", excerpt))
        else:
            m = _FIRST_TITLE.search(src)
            if m and "<span" in m.group(1).lower():
                pos = m.start(1) + m.group(1).lower().index("<span")
                line = src.count("\n", 0, pos) + 1
                excerpt = " ".join(m.group(1).split())[:90]
                out.append((path, line, "'<span' in <title> RCDATA", excerpt))
    return out


def _self_test() -> int:
    """Prove the guard flags known-bad fixtures and passes known-good ones."""
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="check_title_i18n_selftest_")
    try:
        def w(name: str, text: str) -> str:
            p = os.path.join(tmp, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            return p

        bad = {
            "attr CJK": w("bad_attr_cjk.j2", '<span title="中文提示">x</span>\n'),
            "attr t()": w("bad_attr_t.j2", "<a title=\"{{ t('a','b') }}\">x</a>\n"),
            "attr zh var": w("bad_attr_zh.j2", '<a title="{{ al.line_zh }}">x</a>\n'),
            "t() in <title>": w("bad_title_t.j2", "<title>{{ t('Macro','宏观') }} — X</title>\n"),
            "td() in block title": w(
                "bad_block_td.j2", "{% block title %}{{ td('nav.macro') }}{% endblock %}\n"
            ),
            "t() in wrapped block title": w(
                "bad_block_ml.j2", "{% block title %}\n  {{ t('a','b') }}\n{% endblock %}\n"
            ),
            "span in rendered <title>": w(
                "bad_site_span.html",
                '<head>\n<title>\nBoard — <span class="l-en">X</span>'
                '<span class="l-zh">宏观</span></title>\n</head>\n',
            ),
        }
        good = {
            "plain CJK <title>": w(
                "good_cjk_title.j2", "<title>China thematic baskets · 同花顺 — vs CSI 300</title>\n"
            ),
            "JS-built SVG title string": w(
                "good_js_title.j2", "var s = '<title>' + esc(tip) + '</title></circle>';\n"
            ),
            "plain block title": w(
                "good_block.j2", "{% block title %}Odds Desk — Macro Dashboard{% endblock %}\n"
            ),
            "rendered CJK title + body span": w(
                "good_site.html",
                "<head><title>Flow Desk · 盘中资金流</title></head>\n"
                '<body><span class="l-en">x</span></body>\n',
            ),
            "data-tip attributes": w(
                "good_tip.j2", '<span data-tip-en="hint" data-tip-zh="提示">x</span>\n'
            ),
        }

        failures = []
        for label, p in bad.items():
            if not find_violations([p]):
                failures.append(f"known-bad NOT flagged: {label}")
        for label, p in good.items():
            hits = find_violations([p])
            if hits:
                failures.append(f"known-good flagged: {label} -> {hits}")
        if failures:
            for f in failures:
                print(f"check_title_i18n: self-test FAIL — {f}", file=sys.stderr)
            return 1
        print("check_title_i18n: self-test OK — bad fixtures flagged, good fixtures clean.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] == "--self-test":
        return _self_test()
    paths = argv if argv else ["templates", "site"]

    violations = find_violations(paths)
    if violations:
        print(
            f"check_title_i18n: FAIL — {len(violations)} violation(s): translated text in a "
            f"title= attribute, or dual-span markup in <title> RCDATA. Translated text NEVER "
            f"goes in attributes, and t()/td() markup NEVER goes in a <title> element — "
            f"the dual-span l-en/l-zh mechanism cannot operate in either place:\n",
            file=sys.stderr,
        )
        for path, line, reason, excerpt in violations:
            print(f"  {path}:{line} [{reason}] {excerpt!r}", file=sys.stderr)
        print(
            "\nFix attributes by moving the text out: use data-tip-en=/data-tip-zh= (theme.js "
            "renders the language-aware popover), or keep a static ENGLISH-ONLY title, or drop "
            "a title that repeats the visible dual-span chip. Fix <title> elements by passing "
            "plain strings (English + optional literal CJK — never t()/td()); the H1 carries "
            "the dual-span bilingual heading.",
            file=sys.stderr,
        )
        return 1

    scanned = ", ".join(paths)
    print(
        f"check_title_i18n: OK — no bilingual/CJK title attributes, no markup in "
        f"<title> RCDATA ({scanned})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
