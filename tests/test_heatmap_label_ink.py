"""The heatmap's blanket-white label rule has no floor of its own — this is it.

#4608 (operator directive, 2026-08-05) replaced the per-tile WCAG ink chooser
with an unconditional white label: ``inkDark()`` returns false, ``fgFor()``
returns ``#ffffff``. The old chooser was self-correcting — a fill too bright for
white simply got black text — so the palette could drift and the labels stayed
legible. Under a blanket rule that safety net is gone: brightening a ramp now
degrades every label on that side of the map silently, and nothing in the
renderer or the suite notices.

So the legibility moved into the PALETTE, and the palette is what has to be
pinned. This walks the nine fills ``binPalette()`` builds in each theme, from
the ``--hm-up-v`` / ``--hm-dn-v`` values parsed out of the shipping renderer, and
asserts white clears AA-large on all of them — the bar #4608 measured itself
against (3.46:1 on the strongest dark green, ~4:1 on the red extremes, 4.1:1 on
the deepened no-data grey).

The pre-#4608 light palette (``--hm-up-v:#1aa869``) put its top green at 3.07:1
and is what this rejects.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("templates/heatmap.js", "site/heatmap.js")

# binPalette()'s own ladder, mirrored rather than imported (it lives in JS).
# theme -> (neutral, heavy-mix weight, no-data grey). The mid weights (0.46 /
# 0.26) are shared; only the ±2 bin differs between the boards.
LADDER = {
    "light": {"neutral": (104, 111, 124), "heavy": 0.74, "na": (120, 126, 137)},
    "dark": {"neutral": (41, 46, 57), "heavy": 0.82, "na": None},
}
INK = (255, 255, 255)
AA_LARGE = 3.0          # the bar #4608 set for the label
NA_FLOOR = 3.0


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    n = int(value, 16)
    return ((n >> 16) & 255, (n >> 8) & 255, n & 255)


def _relative_luminance(c) -> float:
    def channel(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(c[0]) + 0.7152 * channel(c[1]) + 0.0722 * channel(c[2])


def _contrast(a, b) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _mix(a, b, t):
    return tuple(round(a[i] * t + b[i] * (1 - t)) for i in range(3))


def _source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _palette_vars(source: str, selector: str) -> dict[str, str]:
    rule = re.search(re.escape(selector) + r"\{([^}]*)\}", source)
    assert rule, f"heatmap.js no longer carries the {selector} palette rule"
    found = dict(re.findall(r"(--hm-(?:up|dn)-v):\s*(#[0-9a-fA-F]{3,6})", rule.group(1)))
    assert set(found) == {"--hm-up-v", "--hm-dn-v"}, (selector, found)
    return found


def _bins(up, dn, theme: str):
    """The nine fills binPalette() produces, hottest first."""
    spec = LADDER[theme]
    nu, heavy = spec["neutral"], spec["heavy"]
    return [
        ("+3", up),
        ("+2", _mix(up, nu, heavy)),
        ("+1", _mix(up, nu, 0.46)),
        ("+0.5", _mix(up, nu, 0.26)),
        ("0", nu),
        ("-0.5", _mix(dn, nu, 0.26)),
        ("-1", _mix(dn, nu, 0.46)),
        ("-2", _mix(dn, nu, heavy)),
        ("-3", dn),
    ]


@pytest.mark.parametrize("rel", SOURCES)
def test_label_ink_is_unconditionally_white(rel: str) -> None:
    """If the chooser ever comes back, the palette floors below stop applying."""
    source = _source(rel)
    assert "function inkDark() { return false; }" in source
    assert "function fgFor() { return '#ffffff'; }" in source
    assert "function inkCls() { return ''; }" in source


@pytest.mark.parametrize("rel", SOURCES)
@pytest.mark.parametrize(
    "theme,selector",
    [("dark", ":root"), ("light", 'html[data-theme="light"]')],
)
def test_every_bin_carries_a_legible_white_label(rel: str, theme: str, selector: str) -> None:
    palette = _palette_vars(_source(rel), selector)
    up = _hex_to_rgb(palette["--hm-up-v"])
    dn = _hex_to_rgb(palette["--hm-dn-v"])

    thin = [
        f"{name} rgb{fill} = {_contrast(fill, INK):.2f}:1"
        for name, fill in _bins(up, dn, theme)
        if _contrast(fill, INK) < AA_LARGE
    ]
    assert not thin, (
        f"{theme} board: these fills are too bright for the white label every tile "
        f"now carries — deepen the ramp, do not re-introduce the ink chooser: "
        + "; ".join(thin)
    )


@pytest.mark.parametrize("rel", SOURCES)
def test_light_no_data_grey_stays_deep_enough_for_white(rel: str) -> None:
    """P.na is a literal, not a ramp — it drifts independently of --hm-up-v."""
    source = _source(rel)
    literal = re.search(r"P\.na\s*=\s*\[(\d+),\s*(\d+),\s*(\d+)\]", source)
    assert literal, "the light board's no-data grey is no longer a literal triple"
    grey = tuple(int(g) for g in literal.groups())
    assert grey == LADDER["light"]["na"], (
        "the light no-data grey moved; re-measure before changing this pin", grey
    )
    assert _contrast(grey, INK) >= NA_FLOOR, _contrast(grey, INK)


@pytest.mark.parametrize("rel", SOURCES)
def test_zh_swap_reuses_the_same_two_colours(rel: str) -> None:
    """红涨绿跌 swaps which ramp is which; it must not introduce a third colour.

    Both zh overrides re-point the two vars at each other, so a palette fix
    applied to the base rule alone would leave Chinese readers on the old value —
    the same defect, surviving in half the audience.
    """
    source = _source(rel)
    for base_sel, zh_sel in (
        (":root", 'html[data-lang="zh"]'),
        ('html[data-theme="light"]', 'html[data-theme="light"][data-lang="zh"]'),
    ):
        base = _palette_vars(source, base_sel)
        swapped = _palette_vars(source, zh_sel)
        assert swapped["--hm-up-v"].lower() == base["--hm-dn-v"].lower(), zh_sel
        assert swapped["--hm-dn-v"].lower() == base["--hm-up-v"].lower(), zh_sel
