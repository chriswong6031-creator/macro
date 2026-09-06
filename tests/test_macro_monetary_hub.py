"""Macro & Monetary suite hub — `macro_monetary.html` (F01 / Macro Command).

The hub URL is unchanged from R1 (#6873): `site/macro_monetary.html`. Macro
Command P1 (#6930) retires the R1 card grid (`.mq-hub-card`,
`data-mq-hub-grid`, `view.changes`, `view.attention`) and supersedes it with
the command shell (left rail, hash routing, twelve panels). This file asserts
what is still true of that page under the new shell — not the retired markup.

Standing laws (same as R1, still binding):

1. NO INVENTED AUTHORITY. Fixed reading order only — never a cross-workspace
   score, fused composite, or "most important" claim
   (`DNR:KILL-FUSED-COMPOSITE`, `DNR:KILL-REGIME-SCORECARD`).
2. MISSING COVERAGE IS TYPED. Every em dash carries screen-reader text; honest
   null copy uses plain words ("Not available yet" / "No dated reading yet").
3. NO SLUGS, NO RECEIPTS, NO PLUMBING in the default reading path.
4. EN/ZH parity; no CJK inside `title=` attributes.
"""
from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

import pytest

from engine.market_os.macro_workspaces import registry as producer_registry
from scripts import build_macro_suite_pages as builder

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
DATA_ROOT = ROOT / "site" / "macrodata"
BUILT_AT = "2026-09-06T08:00:00Z"

# Fixed reading order — frozen Macro Command spec §1.1 (customer's question
# order), never the producer registry order and never re-sorted with data.
EXPECTED_SECTION_ORDER = (
    "overview", "money", "policy", "rates", "inflation", "growth",
    "jobs", "housing", "consumer", "credit", "debt", "trade",
)
SUBTABBED_SECTIONS = ("money", "growth", "credit")

_TEMPLATE_NAMES = (
    "macro_monetary.html.j2",
    "_macro_command_macros.html.j2",
    "_macro_suite_nav.html.j2",
    "macro_liquidity_regime.html.j2",
    "macro_growth_real_economy.html.j2",
    "macro_business_activity.html.j2",
    "macro_labor_markets.html.j2",
    "macro_inflation_system.html.j2",
    "macro_monetary_policy.html.j2",
    "macro_financial_conditions.html.j2",
    "macro_liquidity_central_banks.html.j2",
    "macro_capital_structure.html.j2",
    "macro_housing_real_estate.html.j2",
    "macro_consumer_payments.html.j2",
    "macro_national_debt_liabilities.html.j2",
    "macro_rates_curves.html.j2",
    "macro_trade_flows.html.j2",
    "_macro_suite_shell.html.j2",
    "_seo_head.html.j2",
    "_site_nav.html.j2",
    "_navlinks.html.j2",
    "macro_suite_boot.js",
    "macro_suite.css",
    "macro_suite.js",
    "macro_command.css",
    "macro_command.js",
    "theme.js",
)


def _isolated_root(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    templates = tmp_path / "templates"
    templates.mkdir(parents=True, exist_ok=True)
    for name in _TEMPLATE_NAMES:
        shutil.copyfile(TEMPLATES / name, templates / name)
    return tmp_path


def _data_copy(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    destination = tmp_path / "macrodata"
    shutil.copytree(DATA_ROOT / "workspaces", destination / "workspaces")
    return destination


def _render(tmp_path: Path, data_root: Path) -> dict[str, str]:
    root = _isolated_root(tmp_path)
    pages = builder.render(root, data_root=data_root, out_dir=tmp_path / "site",
                           page_built_at=BUILT_AT)
    return {p.name: p.read_text(encoding="utf-8") for p in pages}


@pytest.fixture(scope="module")
def rendered(tmp_path_factory) -> dict[str, str]:
    return _render(tmp_path_factory.mktemp("hub_live"), DATA_ROOT)


@pytest.fixture(scope="module")
def hub(rendered: dict[str, str]) -> str:
    return rendered[builder.HUB_PAGE.output]


def _authored(html: str) -> str:
    """The region the hub itself authors (excludes the shared global header)."""
    start = html.index('<main class="mc-shell"')
    return html[start:html.index("</main>", start)]


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------

def test_the_hub_is_published_at_the_ruled_route(rendered: dict[str, str]) -> None:
    """Same URL as R1; Macro Command supersedes the prior card-grid markup."""
    assert builder.HUB_PAGE.output == "macro_monetary.html"
    assert "macro_monetary.html" in rendered


def test_the_hub_does_not_displace_the_legacy_macro_routes() -> None:
    outputs = {page.output for page in builder.SUITE_PAGES} | {builder.HUB_PAGE.output}
    assert "macro.html" not in outputs
    assert "macro_context.html" not in outputs


def test_the_hub_renders_a_real_page_not_a_template(hub: str) -> None:
    assert "{{" not in hub and "{%" not in hub and "{#" not in hub


def test_the_hub_uses_the_macro_command_shell(hub: str) -> None:
    """R1's `.mq-hub` / `.mq-hub-card` grid is retired at this URL."""
    assert 'class="mc-shell"' in hub
    assert 'id="mc-rail"' in hub
    assert "mq-hub-card" not in hub
    assert "data-mq-hub-grid" not in hub


# --------------------------------------------------------------------------
# twelve rail sections — fixed order, EN + ZH, hash routing, sub-tabs
# --------------------------------------------------------------------------

def test_the_rail_has_exactly_twelve_sections_in_the_fixed_reading_order(hub: str) -> None:
    order = re.findall(r'data-mc-section="([a-z]+)"', hub)
    assert order == list(EXPECTED_SECTION_ORDER)


def test_every_rail_section_has_matching_en_and_zh_labels(hub: str) -> None:
    rail = hub[hub.index('id="mc-rail"'):hub.index('id="mc-content"')]
    for section in builder.SECTIONS:
        assert f'data-mc-section="{section.id}"' in rail
        # Jinja/autoescape turns `&` into `&amp;` in the served markup.
        assert f'<span class="l-en">{html.escape(section.label_en)}</span>' in rail
        assert f'<span class="l-zh">{html.escape(section.label_zh)}</span>' in rail


def test_every_hash_href_has_a_matching_bare_id(hub: str) -> None:
    targets = re.findall(r'href="#([^"]+)"', hub)
    assert targets, "expected at least the twelve rail links"
    ids = set(re.findall(r'\bid="([^"]+)"', hub))
    for target in targets:
        assert target in ids, f'href="#{target}" has no matching id="{target}"'


def test_the_twelve_panels_ship_unhidden_with_hash_routing_markup(hub: str) -> None:
    sections = re.findall(r'<section class="mc-panel" id="([a-z]+)"[^>]*>', hub)
    assert sections == list(EXPECTED_SECTION_ORDER)
    for block in re.finditer(r'<section class="mc-panel" id="[a-z]+"[^>]*>', hub):
        assert "hidden" not in block.group(0)
        assert 'data-mc-panel="' in block.group(0)


def test_the_three_subtabbed_sections_carry_money_growth_credit_tablists(hub: str) -> None:
    for section_id in SUBTABBED_SECTIONS:
        match = re.search(
            r'<section class="mc-panel" id="' + section_id + r'".*?(?=<section class="mc-panel"|</main>)',
            hub, re.S)
        assert match, section_id
        body = match.group(0)
        assert 'role="tablist"' in body, section_id
        assert len(re.findall(r'role="tab"', body)) == 2, section_id


def test_every_built_workspace_is_reachable_from_the_hub(hub: str) -> None:
    """Deep links live in panel offer lines and Details — not a card grid."""
    authored = _authored(hub)
    for page in builder.SUITE_PAGES:
        assert f'href="{page.output}"' in authored, page.workspace_id


def test_the_hub_uses_the_closed_registry_membership_and_never_reorders_by_magnitude(
        hub: str) -> None:
    """Sol 2026-09-05 Q2 / G3: fixed reading order. An importance ordering
    would be a cross-workspace ranker (`DNR:KILL-FUSED-COMPOSITE`)."""
    rail = hub[hub.index('id="mc-rail"'):hub.index('id="mc-content"')]
    positions = [rail.index(f'data-mc-section="{section_id}"')
                 for section_id in EXPECTED_SECTION_ORDER]
    assert positions == sorted(positions)

    # MEMBERSHIP is the closed producer registry's; ORDER is the Macro Command
    # reading order (SECTIONS), not the registry declaration order.
    assert {p.workspace_id for p in builder.SUITE_PAGES} == set(producer_registry.WORKSPACE_IDS)
    section_workspace_ids: list[str] = []
    for section in builder.SECTIONS:
        if section.subtabs:
            section_workspace_ids.extend(tab.workspace_id for tab in section.subtabs)
        elif section.workspace_id:
            section_workspace_ids.append(section.workspace_id)
    assert sorted(section_workspace_ids) == sorted(p.workspace_id for p in builder.SUITE_PAGES)
    assert len(section_workspace_ids) == len(set(section_workspace_ids)) == 14


def test_the_hub_order_does_not_move_when_the_data_moves(tmp_path: Path) -> None:
    """Anti-ranking as an experiment: break one workspace, blank another's
    deltas. The rail order must not move."""
    def rail_order(html: str) -> list[str]:
        return re.findall(r'data-mc-section="([a-z]+)"', html)

    baseline = rail_order(_render(tmp_path / "a", DATA_ROOT)[builder.HUB_PAGE.output])

    data_root = _data_copy(tmp_path / "b")
    (data_root / "workspaces" / "trade_flows" / "US" / "latest.json").write_text(
        "{ broken", encoding="utf-8")
    victim = data_root / "workspaces" / "inflation_system" / "US" / "latest.json"
    body = json.loads(victim.read_text(encoding="utf-8"))
    body["changes"]["deltas"] = []
    victim.write_text(json.dumps(body), encoding="utf-8")

    disturbed = rail_order(_render(tmp_path / "b", data_root)[builder.HUB_PAGE.output])

    assert disturbed == baseline == list(EXPECTED_SECTION_ORDER)


# --------------------------------------------------------------------------
# no invented authority / glance-tier vocabulary
# --------------------------------------------------------------------------

_RANKING_VOCABULARY = (
    "most important", "importance score", "composite score", "overall score",
    "macro score", "ranked", "ranking", "top 3 ", "top 5 ", "biggest mover",
)
_DENIALS = ("not ", "never ", "no ", "非", "不", "并非")
_BANNED_GLANCE = (
    "falsifier", "falsified", "refuted", "证伪",
    "coverage_ratio", "null_reason", "generation_id",
)


def test_the_hub_publishes_no_composite_score_rank_or_importance(hub: str) -> None:
    text = re.sub(r"<[^>]+>", " ", _authored(hub)).lower()
    for sentence in re.split(r"(?<=[.!?。！？])\s+|\n", text):
        for forbidden in _RANKING_VOCABULARY:
            if forbidden in sentence:
                assert any(d in sentence for d in _DENIALS), \
                    f"unnegated ranking claim: {forbidden!r} in {sentence.strip()[:160]!r}"


def test_no_banned_vocabulary_at_glance_tier(hub: str) -> None:
    """Glance path = authored main minus <details> (methods stay Tier-2)."""
    authored = _authored(hub)
    glance = re.sub(r"<details\b.*?</details>", " ", authored, flags=re.S | re.I)
    glance_text = re.sub(r"<[^>]+>", " ", glance).lower()
    for banned in _BANNED_GLANCE:
        assert banned.lower() not in glance_text, banned


# --------------------------------------------------------------------------
# honest / typed absence
# --------------------------------------------------------------------------

def test_coverage_absence_is_typed_and_has_screen_reader_text(hub: str) -> None:
    """Every `mq-dash` carries a sibling `.mq-sr` (G4); P1's empty Read shows
    plain-word absence, never a bare unlabelled dash."""
    authored = _authored(hub)
    assert "No dated reading yet" in authored or "Today's reading is incomplete" in authored
    assert "暂无带日期的读数" in authored or "今日读数不完整" in authored
    for match in re.finditer(r'<span class="mq-dash"[^>]*>—</span>(.{0,80})', authored, re.S):
        assert 'class="mq-sr"' in match.group(1), \
            "a mq-dash with no adjacent mq-sr is an unlabelled dash"


def test_a_broken_workspace_does_not_break_the_hub_or_reorder_the_rail(tmp_path: Path) -> None:
    """Operational failure is not investment importance — and under Macro
    Command the rail stays fixed even when a workspace artifact is unreadable."""
    data_root = _data_copy(tmp_path)
    victim = data_root / "workspaces" / "labor_markets" / "US" / "latest.json"
    victim.write_text("{ this is not json", encoding="utf-8")

    hub = _render(tmp_path, data_root)[builder.HUB_PAGE.output]
    assert re.findall(r'data-mc-section="([a-z]+)"', hub) == list(EXPECTED_SECTION_ORDER)
    for page in builder.SUITE_PAGES:
        assert f'href="{page.output}"' in hub


def test_a_missing_workspace_artifact_never_renders_as_zero_percent(tmp_path: Path) -> None:
    data_root = _data_copy(tmp_path)
    victim = data_root / "workspaces" / "housing_real_estate" / "US" / "latest.json"
    victim.unlink()

    hub = _render(tmp_path, data_root)[builder.HUB_PAGE.output]
    authored = _authored(hub)
    # Hub glance path must not invent a calm 0% for a missing source.
    assert "0%" not in authored
    assert re.findall(r'data-mc-section="([a-z]+)"', hub) == list(EXPECTED_SECTION_ORDER)


def test_a_manifest_that_omits_a_workspace_still_keeps_the_full_rail(tmp_path: Path) -> None:
    data_root = _data_copy(tmp_path)
    manifest_path = data_root / "workspaces" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["workspaces"].pop("trade_flows/US")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    hub = _render(tmp_path, data_root)[builder.HUB_PAGE.output]
    assert re.findall(r'data-mc-section="([a-z]+)"', hub) == list(EXPECTED_SECTION_ORDER)
    assert 'href="macro_trade_flows.html"' in hub


# --------------------------------------------------------------------------
# truthful first viewport / no machine text
# --------------------------------------------------------------------------

def test_the_hub_shows_a_dated_or_honestly_absent_as_of(hub: str) -> None:
    authored = _authored(hub)
    assert "<time" in authored or "No dated reading yet" in authored


def test_no_machine_receipt_reaches_the_hub_reading_path(hub: str) -> None:
    manifest = json.loads((DATA_ROOT / "workspaces" / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["workspaces"]["liquidity_regime/US"]
    assert entry["content_sha256"] not in hub
    assert entry["generation_id"] not in hub
    assert "workspaces/liquidity_regime/US/latest.json" not in hub
    assert "mastermind.macro_workspace_snapshot" not in hub


def test_no_python_none_token_reaches_the_page(hub: str) -> None:
    assert ">None<" not in hub
    assert ">none<" not in hub.lower()


def test_no_raw_workspace_slug_is_printed_as_prose(hub: str) -> None:
    """`liquidity_regime` is an id; it may only appear in machine attributes or hrefs."""
    for line in hub.splitlines():
        if "liquidity_regime" not in line:
            continue
        assert (
            'data-mc-' in line
            or 'href="macro_liquidity_regime.html"' in line
            or "macro_liquidity_regime.html" in line
            or "workspace_id" in line
        ), line.strip()[:160]


def test_the_hub_is_bilingual_through_the_shared_toggle(hub: str) -> None:
    authored = _authored(hub)
    assert authored.count('class="l-en"') == authored.count('class="l-zh"')
    assert authored.count('class="l-en"') > 0


def test_no_zh_text_inside_any_title_attribute(hub: str) -> None:
    zh = re.compile(r"[一-鿿]")
    for value in re.findall(r'\btitle="([^"]*)"', hub):
        assert not zh.search(value), f'title="{value}" carries ZH text'


def test_the_hub_carries_no_executable_inline_script(hub: str) -> None:
    """External deferred scripts are fine; inline executable bodies are not."""
    for match in re.finditer(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", hub, re.S):
        body = match.group("body").strip()
        attrs = match.group("attrs")
        assert not body or "data-dbase" in attrs, body[:120]


# --------------------------------------------------------------------------
# suite navigation shared with the fourteen workspace pages
# --------------------------------------------------------------------------

def test_every_workspace_page_can_return_to_the_hub(rendered: dict[str, str]) -> None:
    for page in builder.SUITE_PAGES:
        html = rendered[page.output]
        assert 'href="macro_monetary.html"' in html, page.output


def test_every_workspace_page_carries_the_full_suite_switcher(rendered: dict[str, str]) -> None:
    for page in builder.SUITE_PAGES:
        html = rendered[page.output]
        for sibling in builder.SUITE_PAGES:
            assert f'href="{sibling.output}"' in html, f"{page.output} -> {sibling.output}"


def test_the_suite_switcher_marks_the_current_workspace(rendered: dict[str, str]) -> None:
    for page in builder.SUITE_PAGES:
        html = rendered[page.output]
        assert 'aria-current="page"' in html, page.output
