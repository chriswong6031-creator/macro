"""Contract tests for the shared light-mode odometer needle treatment.

The compact regime gauges are copied across five report templates.  Their dark
presentation attributes are intentionally neutral-white, while light mode must
derive its pointer from each report's existing semantic state token.  Keep the
twins synchronized so one country cannot silently fall back to the old black
blade again.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "templates" / "theme.css"
SITE_THEME = ROOT / "site" / "theme.css"
TEMPLATES = {
    "macro": ROOT / "templates" / "dashboard.html.j2",
    "canada": ROOT / "templates" / "canada.html.j2",
    "china": ROOT / "templates" / "china.html.j2",
    "hk": ROOT / "templates" / "hk.html.j2",
    "china_policy_watch": ROOT / "templates" / "china_policy_watch.html.j2",
}


def _compact_group(source: str) -> str:
    marker = "odo-needle--compact"
    marker_at = source.index(marker)
    group_at = source.rfind("<g", 0, marker_at)
    group_end = source.index("</g>", marker_at) + len("</g>")
    return source[group_at:group_end]


def test_theme_copy_and_light_only_pointer_contract():
    assert THEME.read_bytes() == SITE_THEME.read_bytes(), (
        "templates/theme.css and site/theme.css must remain byte-identical"
    )
    css = THEME.read_text(encoding="utf-8")
    block = css.split("/* ---- odo-needle:", 1)[1].split(
        "/* ---- Text-grade state INKS", 1
    )[0]

    assert "rgba(10,16,24,.82)" not in block
    assert "var(--odo-accent,var(--warn))" in block
    assert "color-mix(in srgb,var(--odo-accent" in block
    assert ".odo-needle-hub" in block
    assert all(
        line.startswith('html[data-theme="light"]')
        for line in block.splitlines()
        if ".odo-needle" in line and line.rstrip().endswith("{")
    ), "shared pointer rules must not alter the dark-mode rendering"


def test_all_five_compact_gauges_use_shared_semantic_needle():
    for name, path in TEMPLATES.items():
        source = path.read_text(encoding="utf-8")
        group = _compact_group(source)
        assert group.count("odo-needle--compact") == 1, name
        assert 'stroke="rgba(255,255,255,.30)"' in group, name
        assert 'fill="white" opacity=".94"' in group, name
        assert "odo-needle-hub" in group, name

    macro = TEMPLATES["macro"].read_text(encoding="utf-8")
    canada = TEMPLATES["canada"].read_text(encoding="utf-8")
    china = TEMPLATES["china"].read_text(encoding="utf-8")
    hk = TEMPLATES["hk"].read_text(encoding="utf-8")
    policy = TEMPLATES["china_policy_watch"].read_text(encoding="utf-8")

    assert "--odo-accent:var(--mx5-gauge,var(--warn))" in macro
    assert "--odo-accent:var(--mx5-gauge,var(--warn))" in hk
    assert "--odo-accent:var(--sh-accent)" in policy
    for source, prefix in ((canada, "cax"), (china, "cnx")):
        assert f".ms-green .{prefix}-gauge-needle{{--odo-accent:var(--up)}}" in source
        assert f".ms-red .{prefix}-gauge-needle{{--odo-accent:var(--down)}}" in source
        assert f".{prefix}-gauge-needle{{--odo-accent:var(--warn)}}" in source


def test_old_black_blade_overrides_are_gone():
    old_selectors = {
        "macro": "#mx5-gauge-needle polygon{fill:rgba(10,16,24,.82)}",
        "canada": ".cax-gauge-needle polygon{fill:rgba(10,16,24,.82)}",
        "china": ".cnx-gauge-needle polygon{fill:rgba(10,16,24,.82)}",
        "hk": "#mx5-gauge-needle polygon{fill:rgba(10,16,24,.82)}",
        "china_policy_watch": ".sh-needle polygon{fill:rgba(10,16,24,.82)}",
    }
    for name, path in TEMPLATES.items():
        source = path.read_text(encoding="utf-8")
        assert old_selectors[name] not in source, name
