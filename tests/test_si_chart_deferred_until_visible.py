"""The basket overlay chart may not be created while its workspace view is hidden.

Both Sector Intelligence pages build the overlay chart from the basket payload, which
arrives by fetch — long before anybody opens the Explore view. Under the workspace
shell that container starts inside a `display:none` section, and lightweight-charts
binds `autoSize` at CREATION: a chart born zero-wide never recovers.

Measured on the shipped US page 2026-08-04, with Explore open and the container
951px wide: all seven canvases sat at `style.width: 0px`, and neither
`window.dispatchEvent(new Event('resize'))` nor nudging the container's width moved
them. The page looked fine — a 420px-tall empty panel under a full legend — which is
exactly why it survived: nothing throws, nothing logs, and the legend below it renders
from the same data.

The fix is a pair, and both halves are pinned here because either one alone is inert:

  * the page defers creation while `el.clientWidth` is 0 and records that it did;
  * the router announces every activation as `si:view`, and the page redraws when its
    own view arrives.

The router's announcement sits OUTSIDE the first-mount branch on purpose: the page's
organs are not in the lazy manifest, so a first-mount-only event would fire before the
payload had ever called renderChart and never fire again.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "templates"

# (page template, its router)
PAIRS = [
    ("sector_central.html.j2", "si_workspace.js"),
    ("sector_central_china.html.j2", "si_workspace_china.js"),
]


def _read(name: str) -> str:
    p = TPL / name
    assert p.exists(), f"{p} missing"
    return p.read_text(encoding="utf-8")


@pytest.mark.parametrize("page,router", PAIRS, ids=lambda v: str(v).split(".")[0])
def test_render_chart_defers_while_the_container_is_zero_wide(page: str, router: str) -> None:
    src = _read(page)
    body = src.split("function renderChart(", 1)
    assert len(body) == 2, f"{page}: renderChart() is gone"
    fn = body[1].split("\nfunction ", 1)[0]
    guard = re.search(r"if\s*\(\s*!chart\s*&&\s*!el\.clientWidth\s*\)\s*\{\s*_chartDeferred\s*=\s*true;\s*return;\s*\}", fn)
    assert guard, (
        f"{page}: renderChart() no longer defers on a zero-width container — the chart "
        f"would be created inside a display:none view and stay 0px wide forever"
    )
    create = fn.index("LightweightCharts.createChart")
    assert guard.start() < create, "the deferral guard must run BEFORE createChart"


@pytest.mark.parametrize("page,router", PAIRS, ids=lambda v: str(v).split(".")[0])
def test_page_redraws_the_chart_when_explore_arrives(page: str, router: str) -> None:
    src = _read(page)
    assert "_chartDeferred=false" in src.replace(" ", ""), \
        f"{page}: nothing ever clears the deferred flag — the chart would never be drawn"
    listener = re.search(
        r"addEventListener\('si:view'.{0,220}?_chartDeferred.{0,80}?renderChart\(\)", src, re.S)
    assert listener, (
        f"{page}: no si:view handler redraws the deferred chart. Without it the panel "
        f"stays empty for the whole session and nothing logs an error."
    )


@pytest.mark.parametrize("page,router", PAIRS, ids=lambda v: str(v).split(".")[0])
def test_router_announces_every_activation_not_only_first_mount(page: str, router: str) -> None:
    src = (TPL / router).read_text(encoding="utf-8")
    act = src.split("function activate(", 1)[1].split("\nfunction ", 1)[0]
    assert "new CustomEvent('si:view'" in act, f"{router}: activate() does not announce si:view"
    # …and it must sit outside the `if(!mounted[view])` block, or it fires once, before
    # the payload has ever asked for a chart, and never again.
    mount_block = re.search(r"if\(!mounted\[view\]\)\{(.*?)\n  \}", act, re.S)
    assert mount_block, f"{router}: could not locate the first-mount block"
    assert "si:view" not in mount_block.group(1), (
        f"{router}: si:view is dispatched inside the first-mount branch. The page's own "
        f"organs are not lazy-mounted, so that fires before the payload lands and never "
        f"again — the deferred chart would never be redrawn."
    )
