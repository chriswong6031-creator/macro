"""Prophet-card verb inks must clear WCAG AA as TEXT, in both themes and both languages.

Two defects are pinned here, both found 2026-08-10, both invisible in source.

FIRST — ``--ink-pv-near`` under ``html[data-theme="light"][data-lang="zh"]`` was
keyed at 84% — the rung the estate uses for a plain red — but the zh ``--pv-near``
hue is not a plain red, it is ``color-mix(--up 82%, #fff)``, a red already pushed
most of the way to white. Mixing a nearly-white red only 84% of the way toward
``--text`` left the ink at 3.90:1 on the chip tint and 4.00:1 on ``--panel2``:
under AA on the Near card of every prophet board, in Chinese, in light mode. The
EN twin never had the bug because it compensates in the same direction
(buy 62% -> near 56%).

SECOND — in dark the verb-ink layer was a blanket pass-through (``--ink-pv-avoid``
resolved to the raw ``--pv-avoid`` #e06464), on the strength of theme.css's claim
that the raw dark inks clear 4.5:1 "on every estate surface". That measurement was
taken against ``--bg``/``--panel``/``--panel2`` and never against a surface tinted
with the hue's OWN colour — and ``.pv-chip`` is exactly that, a
``color-mix(--pvh 13%, --panel)`` that is DARKER than ``--panel``. #e06464 on its
own 13% tint measured 4.33:1. Fixed by mixing the dark avoid ink 88% toward
``--text``; the theme.css claim was narrowed to what it actually covered.

The lesson both share, and the reason the whole 5x4x4 plane is measured rather
than the pairs someone thought to check: a contrast claim is only as wide as the
SURFACES it was measured against, and this palette prints text on surfaces derived
from the text's own hue.

Why a test and not just the fix: nothing in the estate could SEE this. The inks
are computed by ``color-mix`` at paint time from tokens that a language switch
re-binds underneath them, so the failing value appears in no source file — the
percentage looks like every other percentage in ``theme.css``. That is exactly the
shape of defect that a palette edit re-introduces silently.

Method — this reads the shipping sources rather than mirroring them:

  · every ``--pv-*`` hue, ``--ink-pv-*`` mix and surface token is parsed out of
    ``templates/theme.css``, with the four theme × language cascades resolved by
    specificity (``:root`` < one-attribute < the two-attribute light+zh twin);
  · every consumer's SURFACE formula is parsed out of the real
    ``pv_css()`` block in ``templates/_prophet_card.html.j2`` — the chip's 13%
    tint, the target pill's thinner 9% tint, the zone footer's
    ``color-mix(--panel 55%, --bg)``, and the card's ``--panel2`` — so moving a
    rule cannot quietly narrow what is covered;
  · the ``--pvh``/``--pvh-ink`` per-verb bindings are parsed from the same file,
    so adding a sixth verb without an ink is caught rather than skipped.

Every parse is fail-closed: a pattern that stops matching raises, it does not
silently reduce the covered set.

The browser-side twin is ``mockups/refs/prophet_verb_ink/probe_pv_ink.py``, which
measures the same pairs through Chromium's own ``color-mix``; its numbers and
this file's agree to 0.01. This one is pure-python so it runs in a CI pack with
no browser.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
THEME_CSS = ROOT / "templates" / "theme.css"
CARD_J2 = ROOT / "templates" / "_prophet_card.html.j2"

#: WCAG 2.1 AA, small text. Every consumer below is 9.5-14px bold — the
#: large-text allowance (18.66px bold) does not apply to any of them.
AA_SMALL = 4.5

#: (lang, theme) — dark is theme.css's :root default, so it has no own block.
COMBOS = (("en", "light"), ("zh", "light"), ("en", "dark"), ("zh", "dark"))

#: Carve-outs: {(lang, theme, verb, consumer): measured_ratio}. EMPTY, and that is
#: the intended steady state — every pair on the plane clears AA today.
#:
#: The mechanism is kept rather than deleted with its last entry. It exists so a
#: defect can be pinned at its measured value (a CEILING, not an amnesty — the pair
#: still cannot drift further) when the fix is a separate visual change that should
#: not be folded silently into an unrelated PR. That is how
#: ``en/dark avoid .pv-chip`` (4.33:1) was held between the PR that found it and
#: the PR that re-keyed the dark avoid ink to 88%.
#:
#: ``test_known_gap_entries_are_still_failing`` below is what makes an entry
#: self-clearing: it fails the moment a carved-out pair starts passing, so a stale
#: entry cannot survive its own fix and quietly lower that pair's floor forever.
KNOWN_GAP: dict[tuple[str, str, str, str], float] = {}


# --------------------------------------------------------------------------- colour


def _lum(c) -> float:
    def ch(v: float) -> float:
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def _ratio(fg, bg) -> float:
    a, b = _lum(fg), _lum(bg)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)


def _hex(value: str):
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    n = int(value, 16)
    return ((n >> 16) & 255, (n >> 8) & 255, n & 255)


def _split_top(text: str):
    """Split on commas that are not inside parentheses."""
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [p.strip() for p in out]


def _resolve(expr: str, env: dict, depth: int = 0):
    """Resolve a colour expression to RGB. Handles hex, var(), and color-mix(in srgb …).

    ``color-mix(in srgb, A p%, B)`` interpolates in gamma-encoded sRGB, which is a
    plain component-wise lerp on the 0-255 values — the same thing Chromium does.
    """
    assert depth < 12, f"var() cycle resolving {expr!r}"
    expr = expr.strip()

    if expr.startswith("#"):
        return _hex(expr)

    if expr.startswith("var("):
        inner = expr[4:expr.rindex(")")]
        parts = _split_top(inner)
        name = parts[0].strip()
        if name in env:
            return _resolve(env[name], env, depth + 1)
        assert len(parts) > 1, f"unresolvable {expr!r} with no fallback"
        return _resolve(",".join(parts[1:]), env, depth + 1)

    if expr.startswith("color-mix("):
        inner = expr[10:expr.rindex(")")]
        parts = _split_top(inner)
        assert parts[0].strip() == "in srgb", f"unexpected color space in {expr!r}"
        m = re.match(r"^(.*?)\s+([\d.]+)%$", parts[1].strip())
        assert m, f"expected '<colour> N%' in {parts[1]!r}"
        a = _resolve(m.group(1), env, depth + 1)
        p = float(m.group(2)) / 100.0
        b = _resolve(parts[2], env, depth + 1)
        return tuple(a[i] * p + b[i] * (1 - p) for i in range(3))

    raise AssertionError(f"cannot resolve colour expression {expr!r}")


# --------------------------------------------------------------------------- parsing


def _blocks(css: str):
    """(selector, body) for every top-level rule, in document order."""
    return [(m.group(1).strip(), m.group(2))
            for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", _decomment(css))]


def _decomment(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _decls(body: str) -> dict:
    out = {}
    for decl in _split_decls(body):
        if ":" not in decl:
            continue
        name, _, value = decl.partition(":")
        name = name.strip()
        if name.startswith("--"):
            out[name] = value.strip()
    return out


def _split_decls(body: str):
    out, depth, cur = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == ";" and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [p.strip() for p in out if p.strip()]


def _env_for(css: str, lang: str, theme: str) -> dict:
    """Merge every custom property that applies to this theme × language.

    Ordered by specificity then document order, mirroring the cascade: ``:root``
    (0,1,0) < ``html[data-theme=…]`` / ``html[data-lang=…]`` (0,1,1) < the
    ``html[data-theme="light"][data-lang="zh"]`` twin (0,2,1). theme.css's own
    comment calls out that middle tie, which is why rank is computed rather than
    assumed from file order.
    """
    applicable = []
    for selector, body in _blocks(css):
        for sel in (s.strip() for s in selector.split(",")):
            if sel == ":root":
                rank = 0
            elif sel.startswith("html["):
                attrs = re.findall(r'\[([a-z-]+)="([a-z]+)"\]', sel)
                if len(attrs) != sel.count("["):
                    continue                       # not a plain attribute selector
                want = {"data-theme": theme, "data-lang": lang}
                if any(want.get(k) != v for k, v in attrs):
                    continue
                rank = len(attrs)
            else:
                continue
            applicable.append((rank, _decls(body)))
            break
    env = {}
    for _, decls in sorted(applicable, key=lambda r: r[0]):
        env.update(decls)
    return env


def _rule(css: str, selector: str) -> str:
    """Body of one rule from the card CSS. Fail-closed: no match is an error."""
    m = re.search(re.escape(selector) + r"\s*\{([^{}]*)\}", _decomment(css))
    assert m, f"{selector} not found in {CARD_J2.name} — the guard must be re-pointed"
    return m.group(1)


def _prop(body: str, prop: str) -> str:
    m = re.search(rf"(?:^|;)\s*{re.escape(prop)}\s*:([^;]*)", body)
    assert m, f"no {prop} in rule body {body[:80]!r}"
    return m.group(1).strip()


# --------------------------------------------------------------------------- fixtures


@pytest.fixture(scope="module")
def card_css() -> str:
    return CARD_J2.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def theme_css() -> str:
    return THEME_CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def verbs(card_css: str) -> dict:
    """{verb: (pvh_expr, pvh_ink_expr)} parsed from the .pv-<verb> binding rules."""
    found = {}
    for m in re.finditer(r"\.pv-([a-z]+)\s*\{\s*(--pvh\s*:[^}]*)\}", _decomment(card_css)):
        decls = _decls(m.group(2))
        if "--pvh" in decls and "--pvh-ink" in decls:
            found[m.group(1)] = (decls["--pvh"], decls["--pvh-ink"])
    assert len(found) >= 5, f"expected the 5 verb bindings, parsed {sorted(found)}"
    return found


@pytest.fixture(scope="module")
def surfaces(card_css: str) -> dict:
    """{consumer: (colour_expr, surface_expr)} — every rule that prints a verb hue."""
    chip, trg = _rule(card_css, ".pv-chip"), _rule(card_css, ".pv-trg")
    return {
        # 10px/800 uppercase verb, on its own 13% tint of the hue.
        "pv-chip": (_prop(chip, "color"), _prop(chip, "background")),
        # 14px/800 Edge number, on the card body.
        "pv-edn": (_prop(_rule(card_css, ".pv-edn"), "color"),
                   _prop(_rule(card_css, ".pvcard"), "background")),
        # 9.5px/800 zone label, on the footer's own third surface.
        "pv-znl": (_prop(_rule(card_css, ".pv-znl"), "color"),
                   _prop(_rule(card_css, ".pv-zn"), "background")),
        # 10px/800 target pill — a THINNER 9% tint, so strictly harder than the chip.
        "pv-trg": (_prop(trg, "color"), _prop(trg, "background")),
    }


def _measure(theme_css, verbs, surfaces, lang, theme, verb, consumer):
    env = _env_for(theme_css, lang, theme)
    pvh, pvh_ink = verbs[verb]
    env = {**env, "--pvh": pvh, "--pvh-ink": pvh_ink}
    fg_expr, bg_expr = surfaces[consumer]
    if verb == "buy" and consumer == "pv-chip":
        # .pv-buy .pv-chip inverts the chip: solid ink fill, --panel text. Measure
        # the pair a reader sees, not the one the base rule declares.
        body = _rule(CARD_J2.read_text(encoding="utf-8"), ".pv-buy .pv-chip")
        fg_expr, bg_expr = _prop(body, "color"), _prop(body, "background")
    return _ratio(_resolve(fg_expr, env), _resolve(bg_expr, env))


CASES = [
    pytest.param(lang, theme, verb, consumer,
                 id=f"{lang}-{theme}-{verb}-{consumer}")
    for lang, theme in COMBOS
    for verb in ("buy", "near", "wait", "hold", "avoid")
    for consumer in ("pv-chip", "pv-edn", "pv-znl", "pv-trg")
]


@pytest.mark.parametrize("lang,theme,verb,consumer", CASES)
def test_verb_ink_clears_aa(theme_css, verbs, surfaces, lang, theme, verb, consumer):
    got = _measure(theme_css, verbs, surfaces, lang, theme, verb, consumer)
    floor = KNOWN_GAP.get((lang, theme, verb, consumer), AA_SMALL)
    assert got >= floor - 0.005, (
        f"{lang}/{theme} .pv-{verb} .{consumer} = {got:.2f}:1, under {floor}:1. "
        f"Re-measure with mockups/refs/prophet_verb_ink/probe_pv_ink.py."
    )


def test_zh_light_near_stays_softer_than_buy(theme_css, verbs, surfaces):
    """Near must keep reading as the weaker call than Buy — the constraint that
    rules out the obvious "just copy EN's 56%" fix.

    ``--ink-pv-near`` has a floor (AA) and a ceiling (this): mixed past ~68%
    toward ``--text`` the Near ink becomes DARKER than the Buy ink, and on a board
    where colour is the only thing separating two adjacent verbs, the softer call
    would print heavier than the stronger one. EN honours the same ordering
    (near #2d7155 sits lighter than buy #1e6d47); this pins that zh does too.
    """
    env = _env_for(theme_css, "zh", "light")
    near = _resolve(env["--ink-pv-near"], env)
    buy = _resolve(env["--ink-pv-buy"], env)
    assert _lum(near) > _lum(buy), (
        f"zh light: Near ink {near} is not lighter than Buy ink {buy} — "
        "the verb ladder inverts. Lower the --ink-pv-near mix percentage."
    )


#: Minimum CIELAB separation between a stance token and the direction token it derives
#: from. Measured in dE76 rather than raw RGB distance because RGB distance lies about
#: greens: en/light sits 12.6 apart in summed channels and only 5.6 in dE, and it is dE
#: that answers "can a reader tell these two apart".
#:
#: 3.0 is a REVERSION guard, not the design target — it sits above the ~2.3 just-
#: noticeable threshold and well under every live margin. The four measured quadrants,
#: raw token / text ink: en-light 30.5/5.6 · zh-light 35.1/23.3 · en-dark 10.1/10.1 ·
#: zh-dark 12.5/12.5. All eight were 0.00 before C8-C.
#:
#: en/light's 5.6 is the thinnest and is INHERITED from the reference, not chosen here:
#: light's --ink-mix-up is 62% and the reference's stance mix is 54%, two points on one
#: axis, so the two inks are close by construction. It clears JND and the two never take
#: the same form (Buy is a solid pill; the change is small text), but it is the quadrant
#: to re-open first if the separation is ever judged too thin.
_STANCE_DIRECTION_MIN_DE = 3.0


def _resolve_ink(expr: str, env: dict):
    """--ink-up and friends carry the mix PERCENTAGE in a var(); inline it first."""
    for name in ("--ink-mix-up", "--ink-mix-down"):
        expr = expr.replace(f"var({name})", env.get(name, "100%"))
    return _resolve(expr, env)


def _lab(c):
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(x) for x in c)
    xyz = ((0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047,
           (0.2126 * r + 0.7152 * g + 0.0722 * b),
           (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883)
    fx, fy, fz = (t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in xyz)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _delta_e(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(_lab(a), _lab(b))) ** 0.5


@pytest.mark.parametrize("lang,theme", COMBOS, ids=[f"{l}-{t}" for l, t in COMBOS])
def test_stance_is_never_the_direction_ink(theme_css, lang, theme):
    """DA-002: a Buy call and a positive tape reading must not print the same colour.

    ``--pv-buy`` used to BE ``--up``: byte-identical on every one of the four
    theme x language quadrants (a literal on the two English planes, an explicit
    ``var(--up)`` alias on the two Chinese ones). So one ink on one card meant two
    different things — the stance we published and the direction the tape moved —
    and no reader could tell which they were looking at. Cured by C8-C, the
    Design-System PR chartered by the R4 composition verdict.

    Both layers are checked because both were collided and they fail independently:
    the raw token feeds fills, rings and glows, while ``--ink-pv-buy`` is what
    actually prints as TEXT. The light plane is the one that catches a lazy fix —
    at a 62%% mix ``--ink-pv-buy`` resolves byte-for-byte onto ``--ink-up``, because
    light's ``--ink-mix-up`` is also 62%%, so a stance token can clear the raw
    comparison and still land the chip and the change on one colour.
    """
    env = _env_for(theme_css, lang, theme)
    for stance_name, direction_name in (("--pv-buy", "--up"), ("--ink-pv-buy", "--ink-up")):
        stance = _resolve_ink(env[stance_name], env)
        direction = _resolve_ink(env[direction_name], env)
        gap = _delta_e(stance, direction)
        assert gap >= _STANCE_DIRECTION_MIN_DE, (
            f"{lang}/{theme}: {stance_name} sits dE {gap:.2f} from {direction_name} "
            f"(floor {_STANCE_DIRECTION_MIN_DE}) — stance has collapsed back onto direction. "
            f"They resolve to {'#%02x%02x%02x' % tuple(int(round(c)) for c in stance)} and "
            f"{'#%02x%02x%02x' % tuple(int(round(c)) for c in direction)}. Stance must derive "
            "FROM --up (so the zh flip stays structural) while staying visibly off it; see "
            "the stance block in templates/theme.css."
        )


def test_stance_still_derives_from_direction(theme_css):
    """The separation above must not be bought with a hand-picked hue.

    A literal would satisfy the distance check and quietly break 红涨绿跌: the zh
    blocks flip ``--up``/``--down`` and nothing else, so a stance token that does not
    reference ``--up`` stops flipping with it. This pins the mechanism, not the value.
    """
    for theme in ("dark", "light"):
        env = _env_for(theme_css, "en", theme)
        assert "var(--up)" in env["--pv-buy"], (
            f"{theme}: --pv-buy = {env['--pv-buy']!r} does not reference --up. "
            "Deriving is what makes the Chinese direction flip structural."
        )
    zh, en = _env_for(theme_css, "zh", "dark"), _env_for(theme_css, "en", "dark")
    assert _resolve(zh["--pv-buy"], zh) != _resolve(en["--pv-buy"], en), (
        "zh --pv-buy resolves to the English value — the direction flip did not carry."
    )


def test_known_gap_entries_are_still_failing(theme_css, verbs, surfaces):
    """A carve-out that has been fixed must be deleted, not left to rot.

    Vacuous while ``KNOWN_GAP`` is empty, which is the point: it only has work to
    do when someone carves a pair out, and then it is the thing that forces the
    entry to be removed by the PR that fixes the pair. Without it, fixing
    ``en/dark avoid`` would have left a stale entry behind that silently lowers
    the floor for that pair forever.
    """
    for (lang, theme, verb, consumer), pinned in KNOWN_GAP.items():
        got = _measure(theme_css, verbs, surfaces, lang, theme, verb, consumer)
        assert got < AA_SMALL, (
            f"{lang}/{theme} .pv-{verb} .{consumer} now measures {got:.2f}:1 and "
            f"clears AA — delete its KNOWN_GAP entry (pinned at {pinned})."
        )
