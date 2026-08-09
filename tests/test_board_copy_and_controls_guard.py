from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

CONTROL_ASSET_PAIRS = (
    (ROOT / "templates" / "sector_cycles.js", ROOT / "site" / "sector_cycles.js"),
    (
        ROOT / "templates" / "subsectors_china.js",
        ROOT / "site" / "subsectors_china.js",
    ),
)

SOURCE_RENDER_PAIRS = CONTROL_ASSET_PAIRS + (
    (ROOT / "templates" / "subsectors.js", ROOT / "site" / "subsectors.js"),
    (ROOT / "templates" / "nav_market.js", ROOT / "site" / "nav_market.js"),
)

# These are the approved public surfaces whose job is to explain implementation.
# Product boards may name T1-T4, but must send readers here for the mechanics.
METHODOLOGY_ALLOWLIST = {
    Path("templates/discovery.html.j2"),
    Path("templates/methodology.html.j2"),
    Path("templates/factors.html.j2"),
    Path("templates/signal_lab.html.j2"),
}

_COMMENT_BLOCKS = re.compile(
    r"{#.*?#}|<!--.*?-->|/\*.*?\*/|^[ \t]*//[^\n]*(?:\n|$)",
    re.DOTALL | re.MULTILINE,
)

_MECHANICS_PATTERNS = (
    (
        "tier_indicator_explanation",
        re.compile(
            r"(?:\b(?-i:T[1-4])\b[^\n]{0,180}\b(?:MACD|Stoch-?RSI|RSI-MACD|"
            r"bars?\s+to\s+(?:the\s+)?cross|about\s+to\s+cross|cross(?:ed|ing))\b|"
            r"\b(?:MACD|Stoch-?RSI|RSI-MACD)\b[^\n]{0,180}\b(?-i:T[1-4])\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "tier_formula",
        re.compile(r"\bT[1-4]\s*[x×*]\s*T[1-4]\s*="),
    ),
    (
        "tier_numeric_mechanics",
        re.compile(
            r"\b(?-i:T[1-4])(?:\s*/\s*(?-i:T[1-4]))*\b[^\n]{0,120}"
            r"(?:(?<!font-)\b(?:weight|bars?|threshold|flip|un-?cross)\b|"
            r"[x×*]\s*(?-i:T[1-4]))",
            re.IGNORECASE,
        ),
    ),
    (
        "ranking_formula",
        re.compile(
            r"(?:combined\s+conviction|conviction\s+rank)\s*=|"
            r"stock\s+weight\s*[x×*]\s*concept\s+buyability",
            re.IGNORECASE,
        ),
    ),
    (
        "internal_mechanics_vocabulary",
        re.compile(
            r"\b(?:double[- ]gat(?:e|ed|ing)|confluence\s+cascade|"
            r"regime\s+state\s+machine)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "internal_implementation_reference",
        re.compile(
            r"(?:engine/signal_gate|calibration/provisional_replay\.json|"
            r"reports/top-picks-phase0\.md|Oracle\s+P8|"
            r"DO_NOT_REBUILD\s*§?\s*2|CN\s+analog\s+of\s+TS-R3/TS-R4|"
            r"promotion\s+question\s+earliest\s+2027|W6\s+#22)",
            re.IGNORECASE,
        ),
    ),
    (
        "chart_construction_details",
        re.compile(
            r"(?:0\s*[–-]\s*100\s+oscillator|rebased\s*,\s*log|"
            r"equal[- ]weight\s+synthetic)",
            re.IGNORECASE,
        ),
    ),
    (
        "cross_projection_details",
        re.compile(
            r"\bbars?[-\s]+to[-\s]+(?:the[-\s]+)?cross\b",
            re.IGNORECASE,
        ),
    ),
    (
        "six_leg_receipt",
        re.compile(r"(?:\bof\s+6\s+(?:legs|signs)\b|6\s*(?:条腿|项迹象))", re.IGNORECASE),
    ),
    (
        "chinese_internal_mechanics",
        re.compile(
            r"(?:双重(?:闸门|门控)|汇聚级联|"
            r"层级\s*(?:T[1-4]|\{\{)[^。\n]{0,40}权重|0\s*[–-]\s*100\s*振荡器)"
        ),
    ),
)


def _blank_comments(text: str) -> str:
    """Remove implementation comments without changing line numbers."""

    return _COMMENT_BLOCKS.sub(
        lambda match: "".join("\n" if char == "\n" else " " for char in match.group()),
        text,
    )


def _mechanics_hits(text: str) -> list[tuple[str, int, str]]:
    public_copy = _blank_comments(text)
    hits: list[tuple[str, int, str]] = []
    for label, pattern in _MECHANICS_PATTERNS:
        for match in pattern.finditer(public_copy):
            line = public_copy.count("\n", 0, match.start()) + 1
            excerpt = " ".join(match.group().split())
            hits.append((label, line, excerpt[:180]))
    return hits


def _public_template_sources() -> list[Path]:
    paths = []
    for path in sorted((ROOT / "templates").rglob("*")):
        if not path.is_file() or path.suffix not in {".html", ".j2", ".js"}:
            continue
        relative = path.relative_to(ROOT)
        if relative in METHODOLOGY_ALLOWLIST:
            continue
        paths.append(path)
    return paths


def _button_tag(source: str, marker: str) -> str:
    matches = [tag for tag in re.findall(r"<button\b[^>]*>", source) if marker in tag]
    assert len(matches) == 1, f"expected one {marker} button, found {len(matches)}"
    return matches[0]


def _assert_accessible_button(source: str, marker: str) -> None:
    tag = _button_tag(source, marker)
    assert re.search(r'\btype="button"', tag), tag
    assert re.search(r'\baria-expanded="false"', tag), tag
    assert re.search(r'\baria-controls="[^"]+"', tag), tag


@pytest.mark.parametrize("label", ("T1", "T2", "T3", "T4", "T1–T4", "T1/T2"))
def test_tier_names_are_allowed_without_an_internal_explanation(label: str) -> None:
    assert _mechanics_hits(f"Entry quality: {label}.") == []


@pytest.mark.parametrize(
    "copy",
    (
        "T3 means 3D StochRSI crossed while 2D MACD is about to cross.",
        "Ranked by combined conviction = stock weight × concept buyability factor.",
        "T1×T1 = 1.0.",
        "The double-gated confluence cascade uses a regime state machine.",
        "See engine/signal_gate and calibration/provisional_replay.json, W6 #22.",
        "Every board uses a 0–100 oscillator (rebased, log).",
    ),
)
def test_internal_tier_mechanics_examples_are_rejected(copy: str) -> None:
    assert _mechanics_hits(copy), copy


def test_public_board_copy_names_tiers_without_explaining_the_engine() -> None:
    violations = []
    for path in _public_template_sources():
        for label, line, excerpt in _mechanics_hits(path.read_text(encoding="utf-8")):
            violations.append(f"{path.relative_to(ROOT)}:{line}: {label}: {excerpt}")

    assert not violations, (
        "Board copy may name T1-T4, but implementation mechanics and formulas belong "
        "only on an explicitly allowlisted methodology surface:\n"
        + "\n".join(violations[:80])
    )


def test_control_sources_match_the_shipped_assets_byte_for_byte() -> None:
    for source, shipped in SOURCE_RENDER_PAIRS:
        assert source.read_bytes() == shipped.read_bytes(), (
            f"{source.relative_to(ROOT)} and {shipped.relative_to(ROOT)} diverged; "
            "the source/render pair must ship together"
        )


def test_map_see_all_control_is_accessible_and_wired() -> None:
    source = CONTROL_ASSET_PAIRS[0][0].read_text(encoding="utf-8")
    _assert_accessible_button(source, 'id="sc-xc-more"')
    assert 'id="sc-xc-map"' in source
    assert 'xcMore.addEventListener("click"' in source
    assert 'xcMap.classList.toggle("xc-map-open")' in source
    assert 'xcMore.setAttribute("aria-expanded", open ? "true" : "false")' in source


def test_leadership_see_all_control_is_accessible_and_wired() -> None:
    source = CONTROL_ASSET_PAIRS[0][0].read_text(encoding="utf-8")
    _assert_accessible_button(source, 'id="sc-lead-more"')
    assert 'id="sc-lead"' in source
    assert 'ldMore.addEventListener("click"' in source
    assert 'r.classList.toggle("sc-lead-hidden", !open && i >= leadCap)' in source
    assert 'ldMore.setAttribute("aria-expanded", open ? "true" : "false")' in source
    assert '<div class="sc-lead-more">' not in source


def test_card_see_more_control_is_accessible_and_wired() -> None:
    source = CONTROL_ASSET_PAIRS[1][0].read_text(encoding="utf-8")
    _assert_accessible_button(source, "sc-card-more")
    assert "var regionId = 'sc-card-region-' + (++collapseSeq)" in source
    assert 'id="\' + regionId + \'"' in source
    assert "e.target.closest('.sc-card-more')" in source
    assert "box.classList.toggle('sc-card-collapsed')" in source
    assert "card.classList.toggle('sc-card-hidden', !open && i >= limit)" in source
    assert "btn.setAttribute('aria-expanded', open ? 'true' : 'false')" in source
    assert "See more (" in source and "展开更多 (" in source


def test_row_see_all_control_is_accessible_and_wired() -> None:
    source = CONTROL_ASSET_PAIRS[1][0].read_text(encoding="utf-8")
    _assert_accessible_button(source, "sc-row-more")
    assert "var regionId = 'sc-row-region-' + (++collapseSeq)" in source
    assert "tableHTML.replace('<table ', '<table id=\"' + regionId + '\" ')" in source
    assert "e.target.closest('.sc-row-more')" in source
    assert "rbox.classList.toggle('sc-rows-collapsed')" in source
    assert "tr.classList.toggle('sc-card-hidden', hide)" in source
    assert "btn.setAttribute('aria-expanded', open ? 'true' : 'false')" in source
    assert "See all ' + total" in source and "展开全部 ' + total" in source
