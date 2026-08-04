"""The SECTOR_CENTRAL payload must execute BEFORE the inline bootstrap that reads it.

2026-08-04, measured in-browser on the shipped pages: `#board` rendered 0 bytes and
`#regime` 0 bytes on BOTH sector_central.html and sector_central_china.html, while
`window.SECTOR_CENTRAL` was present and complete (31 sectors, 22 baskets). Re-running
the page's own inline script by hand filled the board instantly — so nothing was wrong
with the data or the renderer, only with the ORDER.

Root cause: ``scripts/optimize_assets`` marks every ``<script src>`` ``defer`` unless
it opts out (``lib.pages.optimize_assets_text``). A deferred script runs after the
document is parsed — i.e. after every inline script — so the payload assigned
``window.SECTOR_CENTRAL`` a beat too late, and the bootstrap's first line

    var D = window.SECTOR_CENTRAL; if (!D) return;

took the early return. The whole gated layer (regime banner, conviction board,
self-grader, full sector table) went dark with no error in the console and no
symptom in any source-level test: the template was correct, the data file was
correct, and the defect only existed in the optimized output.

The opt-out is ``data-sync`` (the same marker government_revenue.html.j2 uses for its
dependency bundles). It keeps the ``?v=`` content hash — only the deferral is waived.

This guard is source-level on purpose: it fires in a PR, before a render, and it pins
the pair (attribute present on the tag + the bootstrap's early-return pattern that
depends on it) rather than a rendered artifact that only exists after a nightly.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "templates"

# (template, payload filename)
PAGES = [
    ("sector_central.html.j2", "sector_central_data.js"),
    ("sector_central_china.html.j2", "sector_central_china_data.js"),
]


def _read(name: str) -> str:
    p = TPL / name
    assert p.exists(), f"{p} missing"
    return p.read_text(encoding="utf-8")


@pytest.mark.parametrize("page,payload", PAGES, ids=lambda v: str(v).split(".")[0])
def test_payload_script_opts_out_of_defer(page: str, payload: str) -> None:
    src = _read(page)
    tags = re.findall(r"<script\b[^>]*\bsrc=\"%s\"[^>]*>" % re.escape(payload), src)
    assert len(tags) == 1, f"{page}: expected exactly one {payload} tag, found {len(tags)}"
    tag = tags[0]
    assert "data-sync" in tag, (
        f"{page}: {payload} must carry data-sync — optimize_assets would otherwise stamp it "
        f"`defer` and it would execute AFTER the inline bootstrap that reads "
        f"window.SECTOR_CENTRAL, leaving the board/regime/grader silently empty.\n  got: {tag}"
    )
    assert "defer" not in tag and "async" not in tag, (
        f"{page}: {payload} may not be deferred or async — the inline bootstrap below it "
        f"runs synchronously during parse and needs the payload already assigned."
    )


@pytest.mark.parametrize("page,payload", PAGES, ids=lambda v: str(v).split(".")[0])
def test_bootstrap_still_early_returns_on_a_missing_payload(page: str, payload: str) -> None:
    """The other half of the pair — and the reason the defect was silent.

    If the bootstrap ever stops early-returning, the ordering bug changes shape from
    "renders nothing" to "throws on every load", and this test's sibling above stops
    describing a real failure mode. Pin the pattern so the two stay in sync.
    """
    src = _read(page)
    assert re.search(r"var D\s*=\s*window\.SECTOR_CENTRAL;\s*if\s*\(\s*!D\s*\)\s*return;", src), (
        f"{page}: the SECTOR_CENTRAL bootstrap's early return moved or changed shape — "
        f"re-check that {payload} still executes before it"
    )


@pytest.mark.parametrize("page,payload", PAGES, ids=lambda v: str(v).split(".")[0])
def test_optimizer_preserves_the_opt_out(page: str, payload: str) -> None:
    """Run the real rewriter over the real tag: data-sync survives, defer is not added,
    and the content hash is still stamped. A guard on the template alone would pass even
    if the optimizer stopped honouring the marker."""
    from lib.pages import optimize_assets_text

    src = _read(page)
    tag = re.findall(r"<script\b[^>]*\bsrc=\"%s\"[^>]*>" % re.escape(payload), src)[0]
    out = optimize_assets_text(tag, lambda _u: "deadbeef")
    assert "data-sync" in out
    assert not re.search(r"\bdefer\b", out), (
        "optimize_assets_text added defer to a data-sync script — the opt-out is broken"
    )
    assert f'src="{payload}?v=deadbeef"' in out, (
        "a data-sync script must still be content-hash stamped; only the deferral is waived"
    )
