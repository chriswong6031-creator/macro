"""Guard: an inline <svg> must never be taller than the wrapper that clips it.

THE BUG THIS EXISTS TO CATCH
----------------------------
An inline ``<svg>`` that carries a ``viewBox`` but no *resolved* height is sized
by its INTRINSIC aspect ratio, not by its parent's height:

    height = wrapperWidth * viewBoxH / viewBoxW

So this, which reads as if it obviously produces a 160px-tall chart::

    .chart-wrap{height:160px;overflow:hidden}
    .chart-wrap svg{display:block;width:100%}      /* <- no height */

    <div class="chart-wrap" style="height:160px">
      <svg viewBox="0 0 800 160" preserveAspectRatio="none"></svg>
    </div>

renders the SVG **220px** tall in a 1102px-wide panel, and ``overflow:hidden``
silently eats the bottom 27%.  Measured on market_structure.html before the fix:
gex-chart and sys-chart lost 60px each, cor-chart 49px, spx-flip-chart 42px.

Why it survives a build every time: *nothing fails*.  The template renders, the
chart JS runs, the SVG paths are valid and complete, the data has no nulls, and
every string-level test passes.  The only symptom is pixels that were never
painted — a line that "has gaps" wherever it dips into the clipped band, an
area chart with no baseline, bars chopped off below zero.  It reads as a data
problem, so the investigation starts in the engine and finds nothing wrong.

The tell is always the same: ``preserveAspectRatio="none"`` is on the element
*because* the author wanted the viewBox stretched to fill the wrapper — which it
can only do once the height resolves.

WHAT THIS CHECKS
----------------
For every ``<svg>`` inside a wrapper whose class sets both a height and
``overflow:hidden``, the SVG must resolve a height from one of:
  * an ``height="..."`` attribute,
  * an inline ``style="...height:..."``,
  * a CSS rule in the same template targeting its class/id (or a
    ``.wrapper svg`` descendant rule) that sets ``height``.

See also templates/market_structure.html.j2 (the comment on .chart-wrap).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TEMPLATES = REPO / "templates"

_CLASS_RULE = re.compile(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", re.S)
_SVG_TAG = re.compile(r"<svg\b([^>]*)>", re.S | re.I)
_HAS_HEIGHT = re.compile(r"(?<![\w-])height\s*:", re.I)
_HAS_CLIP = re.compile(r"overflow(-y)?\s*:\s*hidden", re.I)
_ATTR = re.compile(r'(\w[\w:-]*)\s*=\s*"([^"]*)"', re.S)


def _iter_templates():
    for path in sorted(TEMPLATES.rglob("*")):
        if path.is_file() and path.suffix in {".j2", ".html"}:
            yield path


def _class_props(css_text: str) -> tuple[set[str], set[str]]:
    """(classes that set a height, classes that clip overflow).

    Kept as two sets rather than one "clipping wrapper" set because the two
    halves routinely arrive from different places: market_structure.html.j2 puts
    overflow:hidden on the .chart-wrap RULE but the height in each element's
    INLINE style. Requiring both from the class rule made the scan blind to the
    very shape that shipped broken.
    """
    sized: set[str] = set()
    clips: set[str] = set()
    for name, body in _CLASS_RULE.findall(css_text):
        if _HAS_HEIGHT.search(body):
            sized.add(name)
        if _HAS_CLIP.search(body):
            clips.add(name)
    return sized, clips




def _selectors_with_height(css_text: str) -> set[str]:
    """Bare `.cls {` / `#id {` selectors that set a height."""
    out: set[str] = set()
    for m in re.finditer(r"([.#][A-Za-z0-9_-]+)\s*(?:,[^{]*)?\{([^}]*)\}", css_text, re.S):
        if _HAS_HEIGHT.search(m.group(2)):
            out.add(m.group(1))
    return out


def _attrs(tag_body: str) -> dict[str, str]:
    return {k.lower(): v for k, v in _ATTR.findall(tag_body)}


def _svg_resolves_height(tag_body: str, css_text: str) -> bool:
    attrs = _attrs(tag_body)
    if "height" in attrs and attrs["height"].strip():
        return True
    if _HAS_HEIGHT.search(attrs.get("style", "")):
        return True
    sized = _selectors_with_height(css_text)
    for cls in attrs.get("class", "").split():
        if f".{cls}" in sized:
            return True
    if attrs.get("id") and f"#{attrs['id']}" in sized:
        return True
    return False


_OPEN_DIV_AT_END = re.compile(r"<div\b([^>]*)>\s*$", re.S | re.I)


def _immediate_wrapper(html: str, svg_start: int) -> dict[str, str] | None:
    """Attributes of the SVG's IMMEDIATE parent div, or None if it has another.

    Deliberately narrow.  Walking every unclosed ancestor sweeps in page shells
    — a full-screen `.rv-modal` (height:95vh; overflow:hidden) is an ancestor of
    every 24px icon in research_vault.html.j2, and none of those are clipped.
    The defect this guard is for has one shape: a sized, clipping wrapper with
    the chart SVG sitting directly inside it.
    """
    m = _OPEN_DIV_AT_END.search(html[:svg_start])
    if not m:
        return None
    return _attrs(m.group(1) or "")


def _descendant_svg_sized(css_text: str) -> set[str]:
    """Any `<selector> svg { ... height ... }` rule — e.g. `.vh-tbtn svg`."""
    out: set[str] = set()
    for m in re.finditer(r"([.#][A-Za-z0-9_-]+)[^{},]*\ssvg\s*\{([^}]*)\}", css_text, re.S):
        if _HAS_HEIGHT.search(m.group(2)):
            out.add(m.group(1))
    return out


def _violations(path: Path) -> list[str]:
    html = path.read_text(encoding="utf-8", errors="replace")
    sized_cls, clip_cls = _class_props(html)
    svg_sized = _descendant_svg_sized(html)
    bad: list[str] = []
    for m in _SVG_TAG.finditer(html):
        body = m.group(1)
        if "viewbox" not in body.lower():
            continue
        parent = _immediate_wrapper(html, m.start())
        if parent is None:
            continue
        classes = parent.get("class", "").split()
        style = parent.get("style", "")
        # A wrapper only clips a chart when it is BOTH given a height and told
        # to hide the overflow — from its class rule or its inline style.
        has_height = _HAS_HEIGHT.search(style) or any(c in sized_cls for c in classes)
        clips = _HAS_CLIP.search(style) or any(c in clip_cls for c in classes)
        if not (has_height and clips):
            continue
        if any(f".{c}" in svg_sized for c in classes):
            continue
        if _svg_resolves_height(body, html):
            continue
        line = html[: m.start()].count("\n") + 1
        ident = _attrs(body).get("id") or _attrs(body).get("class") or "<svg>"
        rel = path.relative_to(REPO) if path.is_relative_to(REPO) else path.name
        wrapper = f".{classes[0]}" if classes else "<div>"
        bad.append(
            f"{rel}:{line}: svg '{ident}' inside clipping wrapper "
            f"'{wrapper}' has no resolved height — it will render "
            f"wrapperWidth*viewBoxH/viewBoxW tall and the excess is silently clipped"
        )
    return bad


def test_no_svg_taller_than_its_clipping_wrapper():
    """No template may clip a chart by leaving its SVG height to intrinsic sizing."""
    bad: list[str] = []
    for path in _iter_templates():
        bad.extend(_violations(path))
    assert not bad, "SVG intrinsic-height clipping (bottom of chart cut off):\n" + "\n".join(bad)


def test_market_structure_chart_wrap_pins_svg_height():
    """Pin the exact regression: .chart-wrap svg must keep an explicit height.

    Without this the four market_structure charts lose their bottom 27% and the
    page reads as a data outage.
    """
    css = (TEMPLATES / "market_structure.html.j2").read_text(encoding="utf-8")
    m = re.search(r"\.chart-wrap\s+svg\s*\{([^}]*)\}", css)
    assert m, ".chart-wrap svg rule vanished from market_structure.html.j2"
    assert _HAS_HEIGHT.search(m.group(1)), (
        ".chart-wrap svg must set a height — without it the SVG is sized by its "
        "viewBox aspect ratio and .chart-wrap's overflow:hidden clips the bottom"
    )


# --- the detector must be able to SEE the defect it claims to guard ----------

_BROKEN = """
<style>.chart-wrap{width:100%;height:160px;overflow:hidden}
.chart-wrap svg{display:block;width:100%}</style>
<div class="chart-wrap" style="height:160px">
  <svg id="demo" viewBox="0 0 800 160" preserveAspectRatio="none"></svg>
</div>
"""

_FIXED = _BROKEN.replace("svg{display:block;width:100%}", "svg{display:block;width:100%;height:100%}")


def test_detector_fires_on_the_original_defect(tmp_path):
    """A vacuous guard is worse than none — prove it flags the shipped bug."""
    p = tmp_path / "broken.html.j2"
    p.write_text(_BROKEN, encoding="utf-8")
    assert _violations(p), "detector missed the exact markup that shipped broken"


def test_detector_passes_the_fix(tmp_path):
    p = tmp_path / "fixed.html.j2"
    p.write_text(_FIXED, encoding="utf-8")
    assert not _violations(p), "detector false-positives on the corrected markup"


@pytest.mark.parametrize(
    "svg_tag",
    [
        '<svg id="d" viewBox="0 0 800 160" height="160"></svg>',
        '<svg id="d" viewBox="0 0 800 160" style="height:160px"></svg>',
    ],
)
def test_detector_accepts_other_ways_of_resolving_height(tmp_path, svg_tag):
    p = tmp_path / "ok.html.j2"
    p.write_text(_BROKEN.replace('<svg id="demo" viewBox="0 0 800 160" preserveAspectRatio="none"></svg>', svg_tag), encoding="utf-8")
    assert not _violations(p)
