#!/usr/bin/env python3
"""Static guard: no translated text inside title= attributes.

The i18n rule is that translated text NEVER goes in HTML attributes: the dual-span
l-en/l-zh mechanism cannot operate inside an attribute, so a bilingual native tooltip
shows BOTH languages mashed together, whatever the toggle says. The same goes for a
`{{ t(...) }}` interpolation in an attribute — t() renders dual-span markup, which
inside an attribute becomes literal `<span ...>` garbage text.

The failure this guard catches: a `title="..."` whose value contains CJK characters
or a t() interpolation. Both were live violations found in the #1095 review (e.g. the
W6-C HOLD chip's long bilingual title). The fix pattern (shipped with this guard) is
either:

  • data-tip-en= / data-tip-zh= on the same element — theme.js shows ONE body-appended
    popover whose dual-span body follows [data-lang] (hover on desktop, tap on mobile;
    the generalisation of the #1061 .nb-cau icon+popover pattern), or
  • a static ENGLISH-ONLY title (the same allowance as static English aria-labels) on
    pages that ship no JS (us_stocks_v2, foresight), or
  • dropping a title that merely repeats the visible dual-span chip text.

This guard turns the whole class of drift into a pre-merge failure instead of a review
find. It is meant to run in the same ci.yml / pages.yml gates as check_nav_gap.py and
check_nav_mega.py. It scans TEMPLATE SOURCE by default (templates/); it also accepts
`site` to sweep rendered pages once the render pipeline has flushed pre-fix output
(python-side builders emit no CJK titles today, so templates are the only channel).

Usage:
    python -m scripts.check_title_i18n [DIR_OR_FILE ...]   # default: templates/
Exit codes: 0 = all clean · 1 = violation(s) found.
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

# t() interpolation markers (dual-span renderer — must never run inside an attribute).
_T_CALL = re.compile(r"\{\{\s*t\(")

# A zh-named variable interpolated into the title — the DATA-DRIVEN channel: no literal
# CJK in the template, but the rendered title carries Chinese (e.g. the old
# `title="{{ al.line }} · {{ al.line_zh }}"` join, or the qmark() macro's `{{ zh }}`).
_ZH_VAR = re.compile(r"\{\{[^}]*(?:\bzh\b|_zh\b|\.zh\b)")

_EXTS = (".j2", ".html", ".htm")


def find_violations(paths: list[str]):
    """Return [(path, line, reason, excerpt)] for every title= carrying CJK or t()."""
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
    return out


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    paths = argv if argv else ["templates"]

    violations = find_violations(paths)
    if violations:
        print(
            f"check_title_i18n: FAIL — {len(violations)} title attribute(s) carry translated "
            f"text (CJK or a t() interpolation). Translated text NEVER goes in attributes — "
            f"the dual-span l-en/l-zh mechanism cannot operate there:\n",
            file=sys.stderr,
        )
        for path, line, reason, excerpt in violations:
            print(f"  {path}:{line} [{reason}] {excerpt!r}", file=sys.stderr)
        print(
            "\nFix by moving the text out of the attribute: use data-tip-en=/data-tip-zh= "
            "(theme.js renders the language-aware popover), or keep a static ENGLISH-ONLY "
            "title, or drop a title that repeats the visible dual-span chip.",
            file=sys.stderr,
        )
        return 1

    scanned = ", ".join(paths)
    print(f"check_title_i18n: OK — no bilingual/CJK title attributes ({scanned}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
