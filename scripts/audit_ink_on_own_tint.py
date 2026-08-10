"""Audit: state-palette text printed on a tint of its OWN hue.

Report-only. Prints a table and always exits 0 unless --strict is passed, because
the estate currently has a large standing backlog (see
``research/INK_LAYER_ADOPTION_AUDIT_2026-08-10.md``) and a blocking gate here
would red main on legacy debt rather than on a regression.

THE DEFECT CLASS
----------------
``theme.css`` says the state palette is FILL-grade, not TEXT-grade, and ships an
``--ink-*`` layer as the text-safe form. A rule that writes

    background: color-mix(in srgb, var(--warn) 12%, var(--panel));
    color:      var(--warn);                    /* RAW, not var(--ink-warn) */

prints a fill-grade hue as text on a surface tinted with that same hue — a
strictly harder pair than the flat panel the palette was measured against,
because the tint pulls the background TOWARD the foreground. This is the shape
that put ``.pv-chip`` under AA twice in one day (PR #5226 zh-light ``near``
3.90:1, PR #5232 dark ``avoid`` 4.33:1). The fix in both cases was to route the
text through the ink layer, never to re-palette.

WHAT THIS DOES AND DOES NOT PROVE
---------------------------------
Static analysis of CSS text, so it is a CANDIDATE finder, not a verdict:

* Reachability is an OVER-APPROXIMATION. A rule is kept only when every class
  token in its selector is emitted as markup SOMEWHERE in the repo, which does
  not prove those tokens ever land on the same element. ``.cmd-hero .v-chip``
  was the motivating false positive: both halves look plausible and neither is
  ever emitted, so it measured 10/16 under AA while being unreachable CSS.
* Font size is read from the same rule body when present. AA is 3:1 for large
  text (>=24px, or >=18.66px at weight >=700) and 4.5:1 otherwise; a rule that
  inherits its size from elsewhere is assumed SMALL, which can over-report.
* Only the global palette tokens are resolved. Component-scoped hues
  (``--ic-col``, ``--m7-col``, ...) are skipped, so this UNDER-reports.
* Alpha, opacity, and stacked translucent ancestors are not composited.

Confirm anything this prints in a browser before acting on it.

    python3 scripts/audit_ink_on_own_tint.py            # full table
    python3 scripts/audit_ink_on_own_tint.py --top 20   # worst 20
    python3 scripts/audit_ink_on_own_tint.py --strict   # exit 1 if any fail
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

AA_SMALL = 4.5
AA_LARGE = 3.0

#: theme.css palettes, transcribed. zh swaps --up/--down (红涨绿跌); the status
#: tokens encode health, not direction, so they deliberately do NOT swap.
_DARK = dict(up="#45b873", down="#e06464", warn="#e0a030", ok="#3da564",
             act="#e05555", orange="#e08b45", info="#5b9bf0", link="#7aa7e0",
             panel="#181b21", panel2="#1e222a", bg="#0f1115", text="#d7dce3")
_LIGHT = dict(up="#1f9a55", down="#cf4040", warn="#b9791a", ok="#2f8a52",
              act="#c43d3d", orange="#c4781f", info="#285fff", link="#285fff",
              panel="#ffffff", panel2="#eef1f6", bg="#f7f8fa", text="#1c2430")

PALETTE = {("en", "dark"): _DARK, ("en", "light"): _LIGHT}
PALETTE[("zh", "dark")] = {**_DARK, "up": _DARK["down"], "down": _DARK["up"]}
PALETTE[("zh", "light")] = {**_LIGHT, "up": _LIGHT["down"], "down": _LIGHT["up"]}

#: --ink-mix-* from theme.css. Dark is a pass-through for the STATE inks; note
#: that the prophet verb inks no longer are (see theme.css's prophet block).
INK_MIX = {
    "dark": dict(up=100, down=100, warn=100, ok=100, act=100, orange=100,
                 link=100, info=100),
    "light": dict(up=62, down=84, warn=62, ok=70, act=88, orange=58,
                  link=88, info=88),
}
INK_MIX["light_zh"] = {**INK_MIX["light"], "up": 84, "down": 62}

_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_BG = re.compile(
    r"background(?:-color)?\s*:\s*color-mix\([^;]*?var\(--([a-z0-9-]+)\)\s*"
    r"([0-9.]+)%[^;]*?var\(--([a-z0-9-]+)\)")
_COLOR = re.compile(r"(?<!-)color\s*:\s*var\(--(ink-)?([a-z0-9-]+)")
_SIZE = re.compile(r"font-size\s*:\s*([0-9.]+)px")
_WEIGHT = re.compile(r"font-weight\s*:\s*([0-9]+)")
_CLASS_ATTR = re.compile(r'class\s*=\s*"([^"]*)"')
_CLASS_JS = re.compile(
    r"(?:classList\.(?:add|toggle)|className\s*=)\s*\(?\s*['\"]([^'\"]+)")
_SELECTOR_CLASS = re.compile(r"\.([A-Za-z0-9_-]+)")


def _rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _mix(top, pct, bottom):
    """color-mix(in srgb, top pct%, bottom) with both operands opaque."""
    f = pct / 100.0
    return tuple(f * a + (1 - f) * b for a, b in zip(top, bottom))


def _lum(c) -> float:
    def ch(v: float) -> float:
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def _ratio(fg, bg) -> float:
    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def emitted_class_tokens() -> set[str]:
    """Every class token that appears as MARKUP anywhere in the repo.

    Used only to drop rules whose selectors can never match. Deliberately
    generous — see the module docstring on over-approximation.
    """
    tokens: set[str] = set()
    globs = (ROOT.glob("templates/**/*"), ROOT.glob("scripts/**/*.py"),
             ROOT.glob("engine/**/*.py"), ROOT.glob("site/**/*.js"))
    for group in globs:
        for path in group:
            if not path.is_file() or path.suffix not in (
                    ".j2", ".html", ".js", ".py", ".css"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for blob in _CLASS_ATTR.findall(text):
                for tok in re.split(r"[\s{}%|'\"()]+", blob):
                    tok = tok.strip()
                    if tok and not tok.startswith(("{", "if", "else", "endif")):
                        tokens.add(tok)
            for blob in _CLASS_JS.findall(text):
                tokens.update(blob.split())
    return tokens


def _threshold(body: str) -> float:
    size = _SIZE.search(body)
    weight = _WEIGHT.search(body)
    if not size:
        return AA_SMALL                      # unknown size -> assume small
    px = float(size.group(1))
    bold = weight and int(weight.group(1)) >= 700
    if px >= 24 or (px >= 18.66 and bold):
        return AA_LARGE
    return AA_SMALL


def scan():
    emitted = emitted_class_tokens()
    findings = []
    for path in sorted(ROOT.glob("templates/**/*")):
        if not path.is_file() or path.suffix not in (".j2", ".css", ".html"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for selector, body in _RULE.findall(text):
            bg, color = _BG.search(body), _COLOR.search(body)
            if not (bg and color):
                continue
            hue, pct, under = bg.group(1), float(bg.group(2)), bg.group(3)
            is_ink, ctoken = bool(color.group(1)), color.group(2)
            if ctoken.replace("ink-", "") != hue:
                continue
            if hue not in _DARK or under not in ("panel", "panel2", "bg"):
                continue
            classes = _SELECTOR_CLASS.findall(selector)
            if not classes or not all(c in emitted for c in classes):
                continue                     # unreachable selector
            floor = _threshold(body)
            for lang in ("en", "zh"):
                for theme in ("light", "dark"):
                    pal = PALETTE[(lang, theme)]
                    base = _rgb(pal[under])
                    raw = _rgb(pal[hue])
                    bg_c = _mix(raw, pct, base)
                    if is_ink:
                        key = "light_zh" if (
                            theme == "light" and lang == "zh") else theme
                        fg_c = _mix(raw, INK_MIX[key].get(hue, 100),
                                    _rgb(pal["text"]))
                    else:
                        fg_c = raw
                    got = _ratio(fg_c, bg_c)
                    if got < floor:
                        findings.append(dict(
                            ratio=got, floor=floor,
                            file=str(path.relative_to(ROOT)),
                            selector=" ".join(selector.split())[:52],
                            hue=hue, pct=pct, ink=is_ink,
                            lang=lang, theme=theme))
    findings.sort(key=lambda f: f["ratio"])
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=0,
                    help="show only the N worst rows")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when anything is under its floor")
    args = ap.parse_args()

    findings = scan()
    rows = findings[:args.top] if args.top else findings
    print("\n  state-palette text on a tint of its OWN hue")
    print("  (report-only; confirm in a browser — see module docstring)\n")
    print(f"  {'ratio':>5} {'floor':>5}  {'combo':<9} {'token':<8} "
          f"{'grade':<4} selector")
    print("  " + "-" * 92)
    for f in rows:
        combo = f"{f['lang']}/{f['theme']}"
        grade = "ink" if f["ink"] else "RAW"
        print(f"  {f['ratio']:5.2f} {f['floor']:5.1f}  {combo:<9} "
              f"--{f['hue']:<6} {grade:<4} {f['selector']}")
        print(f"  {'':>25}{f['file']}  @ {f['pct']:g}% tint")
    raw = sum(1 for f in findings if not f["ink"])
    print(f"\n  {len(findings)} candidate pair(s) under floor; "
          f"{raw} print the RAW token where an --ink-* twin exists.")
    if args.top and len(findings) > args.top:
        print(f"  (showing {args.top} of {len(findings)} — "
              f"re-run without --top for the rest)")
    if findings and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
