"""The wide nav panels must stay anchored to the header, not to their trigger.

`.nav-dd-menu.nav-mega` and `.nav-dd-menu.nav-market-menu` are ~1276px panels
positioned with `right: 0`. navigation-refresh.css makes that resolve against
the whole header by clearing the trigger's own positioning
(`.site-nav .nav-mega-dd`/`.nav-market-dd { position: static }`) — both at
specificity (0,2,0).

Any stylesheet loaded AFTER navigation-refresh.css that re-declares
`.site-nav .nav-dd { position: relative }` matches at the same (0,2,0) and wins
on source order. The trigger becomes the offset parent again, `right: 0` pins
the panel's right edge to the ~140px pill, and the remaining ~950px hangs off
the left of the viewport as two disjoint boxes. `_vector_polish.html.j2` — a
theme.css copy that ships at the end of <body> on 59 vector-family pages
(special_situations, commodities, bonds, strategies, …) — did exactly this.

Restoring `static` has a second half: on a static parent the trigger's own
`.nav-dd::after` hover bridge (`left: 0; right: 0; top: 100%`) stops being a
9px strip under the pill and becomes one spanning the entire header, holding
panels open on any downward exit. navigation-refresh.css therefore pairs the
static anchor with `content: none` and moves the bridge onto
`a.nav-link::after`. A late copy must re-assert both halves or neither.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

# The two files that OWN this cascade. theme.css is the base (always linked
# before navigation-refresh.css); navigation-refresh.css is the source of the
# static anchors themselves. Everything else is a downstream copy.
CASCADE_OWNERS = {"theme.css", "navigation-refresh.css"}

WIDE_DD_CLASSES = ("nav-mega-dd", "nav-market-dd")

# `.site-nav .nav-dd { … position: relative … }` — specificity (0,2,0), i.e.
# enough to tie the static anchors. A bare `.nav-dd` (0,1,0) loses outright and
# is not a hazard, so it is deliberately not matched.
_RELATIVE_DD = re.compile(
    r"\.(?:site-nav|topbar)\s+\.nav-dd\s*\{[^}]*position\s*:\s*relative",
    re.DOTALL,
)


def _wide_dd_rule(text: str, cls: str, prop: str, value: str) -> bool:
    """True when `text` declares `prop: value` for `.<cls>` at >= (0,2,0)."""
    pattern = re.compile(
        r"\.(?:site-nav|topbar)\s+\." + cls + r"(?:::after)?[^{}]*\{[^}]*"
        + prop + r"\s*:\s*" + value,
        re.DOTALL,
    )
    return bool(pattern.search(text))


def _candidate_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(TEMPLATES.rglob("*")):
        if not path.is_file() or path.name in CASCADE_OWNERS:
            continue
        if path.suffix not in {".css", ".j2", ".html"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _RELATIVE_DD.search(text):
            files.append(path)
    return files


def test_late_nav_css_copies_keep_the_wide_menu_anchors_static() -> None:
    offenders: list[str] = []
    for path in _candidate_files():
        text = path.read_text(encoding="utf-8")
        for cls in WIDE_DD_CLASSES:
            if not _wide_dd_rule(text, cls, "position", "static"):
                offenders.append(f"{path.relative_to(ROOT)}: .{cls} left positioned")
            if not _wide_dd_rule(text, cls, "content", "none"):
                offenders.append(
                    f"{path.relative_to(ROOT)}: .{cls}::after bridge not cleared"
                )
    assert not offenders, (
        "A stylesheet outside navigation-refresh.css re-declares "
        "`.site-nav .nav-dd { position: relative }` at (0,2,0) without "
        "re-asserting the wide-menu anchors. If it loads after "
        "navigation-refresh.css the mega/market panels re-anchor to their "
        "trigger pill and hang ~950px off the left of the viewport:\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_can_see_the_defect() -> None:
    # _vector_polish.html.j2 is the real-world instance; it must still be a
    # candidate (i.e. it still carries the (0,2,0) relative declaration this
    # guard exists to police), otherwise the assertion above is vacuous.
    candidates = {p.name for p in _candidate_files()}
    assert "_vector_polish.html.j2" in candidates

    polish = (TEMPLATES / "_vector_polish.html.j2").read_text(encoding="utf-8")
    without_fix = polish.replace("position:static", "position:relative")
    for cls in WIDE_DD_CLASSES:
        assert _wide_dd_rule(polish, cls, "position", "static")
        assert not _wide_dd_rule(without_fix, cls, "position", "static")


def test_navigation_refresh_still_owns_the_static_anchors() -> None:
    css = (TEMPLATES / "navigation-refresh.css").read_text(encoding="utf-8")
    for cls in WIDE_DD_CLASSES:
        assert _wide_dd_rule(css, cls, "position", "static"), cls
        assert _wide_dd_rule(css, cls, "content", "none"), cls
