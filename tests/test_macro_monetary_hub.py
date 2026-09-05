"""Macro & Monetary suite hub — `macro_monetary.html` (F01 / R1).

The hub is a Tier-1 surface under `docs/DESIGN_DOCTRINE.md`, so it is tested for
what a Tier-1 surface can get *wrong*, in the order that would hurt most:

1. NO INVENTED AUTHORITY. The hub composes what each workspace owner already
   published. It must never emit a cross-workspace importance score, a fused
   composite regime, a ranker, or the words "most important" — the constructions
   closed by `DNR:KILL-FUSED-COMPOSITE` and `DNR:KILL-REGIME-SCORECARD`, and
   re-closed for this lane by the Sol ruling of 2026-09-05.
2. OPERATIONAL FAILURE IS NOT INVESTMENT IMPORTANCE. Failed, stale, conflicted
   and correcting inputs get their own compact attention notice. They never
   reorder the suite, because "this source broke" is not "this matters most".
3. MISSING COVERAGE IS NOT CALM. A workspace the hub cannot read must be visibly
   unavailable. A workspace that is genuinely quiet must read as an answer, and
   the two must not look alike.
4. NO SLUGS, NO RECEIPTS, NO PLUMBING in the default reading path.
"""
from __future__ import annotations

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
BUILT_AT = "2026-09-05T08:00:00Z"

_TEMPLATE_NAMES = (
    "macro_monetary.html.j2",
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


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------

def test_the_hub_is_published_at_the_ruled_route(rendered: dict[str, str]) -> None:
    """Sol 2026-09-05: macro_monetary.html is the R1 candidate hub."""
    assert builder.HUB_PAGE.output == "macro_monetary.html"
    assert "macro_monetary.html" in rendered


def test_the_hub_does_not_displace_the_legacy_macro_routes() -> None:
    """`macro.html` (Macro Regime Dashboard) and `macro_context.html` (Macro
    Weather) are separate products with their own owners and their own builders."""
    outputs = {page.output for page in builder.SUITE_PAGES} | {builder.HUB_PAGE.output}
    assert "macro.html" not in outputs
    assert "macro_context.html" not in outputs


def test_the_hub_renders_a_real_page_not_a_template(hub: str) -> None:
    assert "{{" not in hub and "{%" not in hub and "{#" not in hub


# --------------------------------------------------------------------------
# all fourteen, in the owner's order — never a ranking
# --------------------------------------------------------------------------

def test_every_built_workspace_is_reachable_from_the_hub(hub: str) -> None:
    for page in builder.SUITE_PAGES:
        assert f'href="{page.output}"' in hub, page.workspace_id


def test_the_hub_uses_the_closed_registry_order_and_never_reorders_by_magnitude(hub: str) -> None:
    """Sol 2026-09-05 Q2: fixed existing workspace order. An importance ordering
    would be a cross-workspace ranker (`DNR:KILL-FUSED-COMPOSITE`)."""
    # Measured inside the workspace grid, not across the whole page: the bounded
    # changes list links to workspaces too, and it is a SUBSET, so a first-index
    # scan over the document would report a false reorder for any workspace that
    # published no change.
    grid = hub[hub.index("data-mq-hub-grid"):]
    positions = [grid.index(f'href="{page.output}"') for page in builder.SUITE_PAGES]
    assert positions == sorted(positions), "hub reordered the closed workspace order"

    # MEMBERSHIP is the closed producer registry's — the hub can never advertise a
    # workspace whose producer the registry does not carry. ORDER is the suite's
    # own existing published order, which is NOT the registry's declaration order
    # (`capital_structure` is a read-only census and the suite prints it after the
    # cycle workspaces). Asserting one against the other's source is the whole
    # point: the guarantee is "fixed and data-independent", not "alphabetised".
    assert {p.workspace_id for p in builder.SUITE_PAGES} == set(producer_registry.WORKSPACE_IDS)


def test_the_hub_order_does_not_move_when_the_data_moves(tmp_path: Path) -> None:
    """The anti-ranking property, stated as an experiment rather than an opinion.

    Break one workspace outright and blank another's deltas. If any ordering in
    the hub were magnitude-, recency- or severity-driven, this would move rows.
    """
    def grid_order(html: str) -> list[str]:
        grid = html[html.index("data-mq-hub-grid"):]
        return re.findall(r'data-mq-workspace="([a-z_]+)"', grid)

    baseline = grid_order(_render(tmp_path / "a", DATA_ROOT)[builder.HUB_PAGE.output])

    data_root = _data_copy(tmp_path / "b")
    (data_root / "workspaces" / "trade_flows" / "US" / "latest.json").write_text(
        "{ broken", encoding="utf-8")
    victim = data_root / "workspaces" / "inflation_system" / "US" / "latest.json"
    body = json.loads(victim.read_text(encoding="utf-8"))
    body["changes"]["deltas"] = []
    victim.write_text(json.dumps(body), encoding="utf-8")

    disturbed = grid_order(_render(tmp_path / "b", data_root)[builder.HUB_PAGE.output])

    assert disturbed == baseline
    assert len(baseline) == len(builder.SUITE_PAGES)


def _authored(html: str) -> str:
    """The region the hub itself authors.

    The shared global header (`_site_nav.html.j2`) is another product's surface
    and carries its own vocabulary — "ranked & triaged alerts" among it. Scanning
    the whole document would attribute that copy to this page and, worse, would
    make a hub-vocabulary guard fail whenever an unrelated menu item changed.
    """
    start = html.index('<main class="mq-shell mq-hub"')
    return html[start:html.index("</main>", start)]


_RANKING_VOCABULARY = (
    "most important", "importance score", "composite score", "overall score",
    "macro score", "ranked", "ranking", "top 3 ", "top 5 ", "biggest mover",
)
_DENIALS = ("not ", "never ", "no ", "非", "不", "并非")


def test_the_hub_publishes_no_composite_score_rank_or_importance(hub: str) -> None:
    """`DNR:KILL-FUSED-COMPOSITE` / `DNR:KILL-REGIME-SCORECARD`.

    The rule is that the hub must not CLAIM a ranking — saying plainly that it is
    not one is compliance, not a violation, so the check is per sentence and a
    denial clears it. A bare "the biggest mover this week" would still fail.
    """
    text = re.sub(r"<[^>]+>", " ", _authored(hub)).lower()
    for sentence in re.split(r"(?<=[.!?。！？])\s+|\n", text):
        for forbidden in _RANKING_VOCABULARY:
            if forbidden in sentence:
                assert any(d in sentence for d in _DENIALS), \
                    f"unnegated ranking claim: {forbidden!r} in {sentence.strip()[:160]!r}"


def test_recent_changes_is_bounded_and_states_what_it_did_not_show(hub: str) -> None:
    """Sol 2026-09-05 Q2: bounded 'Recent changes' with an explicit remaining
    count and a deeper path — not a curated 'most important' list."""
    assert "Recent changes" in hub
    assert 'data-mq-hub-changes' in hub
    assert 'data-mq-changes-remaining' in hub


# --------------------------------------------------------------------------
# operational failure is not investment importance
# --------------------------------------------------------------------------

def test_data_attention_is_a_separate_notice_not_an_ordering(hub: str) -> None:
    """Failed/stale/conflicted/correcting inputs are carried in their own compact
    notice. They must not be promoted into the changes list."""
    assert 'data-mq-hub-attention' in hub
    attention = hub.index('data-mq-hub-attention')
    changes = hub.index('data-mq-hub-changes')
    assert attention != changes


def test_a_workspace_the_hub_cannot_read_is_visibly_unavailable(tmp_path: Path) -> None:
    data_root = _data_copy(tmp_path)
    victim = data_root / "workspaces" / "labor_markets" / "US" / "latest.json"
    victim.write_text("{ this is not json", encoding="utf-8")

    hub = _render(tmp_path, data_root)[builder.HUB_PAGE.output]

    assert 'data-mq-hub-unavailable' in hub
    assert 'data-mq-workspace="labor_markets"' in hub
    # and the suite is still navigable — one broken workspace is not a broken hub
    for page in builder.SUITE_PAGES:
        assert f'href="{page.output}"' in hub


def test_an_unreadable_workspace_never_renders_as_calm_or_zero(tmp_path: Path) -> None:
    """Missing is never zero; missing coverage is not calm."""
    data_root = _data_copy(tmp_path)
    victim = data_root / "workspaces" / "housing_real_estate" / "US" / "latest.json"
    victim.unlink()

    hub = _render(tmp_path, data_root)[builder.HUB_PAGE.output]
    block = hub[hub.index('data-mq-workspace="housing_real_estate"'):][:1200]
    assert "mq-hub-absent" in block
    assert "0%" not in block


def test_a_manifest_that_omits_a_workspace_degrades_that_row_only(tmp_path: Path) -> None:
    data_root = _data_copy(tmp_path)
    manifest_path = data_root / "workspaces" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["workspaces"].pop("trade_flows/US")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    hub = _render(tmp_path, data_root)[builder.HUB_PAGE.output]
    assert 'data-mq-workspace="trade_flows"' in hub
    assert 'data-mq-hub-unavailable' in hub


# --------------------------------------------------------------------------
# truthful first viewport
# --------------------------------------------------------------------------

def test_the_hub_shows_an_effective_date_and_a_freshness_statement(hub: str) -> None:
    assert 'data-mq-hub-asof' in hub
    assert "<time" in hub


def test_no_machine_receipt_reaches_the_hub_reading_path(hub: str) -> None:
    """Hashes, generation ids, artifact paths and schema ids are Tier-2/3."""
    manifest = json.loads((DATA_ROOT / "workspaces" / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["workspaces"]["liquidity_regime/US"]
    assert entry["content_sha256"] not in hub
    assert entry["generation_id"] not in hub
    assert "workspaces/liquidity_regime/US/latest.json" not in hub
    assert "mastermind.macro_workspace_snapshot" not in hub


def test_a_metric_with_no_comparable_values_is_not_listed_as_a_change(hub: str) -> None:
    """`missing != zero`, and an uncomparable metric is not a change.

    Three shipped workspaces publish delta rows whose prior, current and delta are
    all null (`business_activity` leading/lagging tier momentum, and rows in
    `consumer_payments` and `trade_flows`). Rendered naively they reach the page as
    the literal Python ``None`` — which is what main's own what-changed tables do
    today. The hub must neither print that token nor spend one of its few change
    slots on a row that states no move.
    """
    assert ">None<" not in hub
    assert ">none<" not in hub.lower()

    body = _authored(hub)
    for entry in re.findall(r'<li class="mq-hub-change">.*?</li>', body, re.S):
        assert "None" not in entry, entry[:200]


def test_no_raw_workspace_slug_is_printed_as_prose(hub: str) -> None:
    """`liquidity_regime` is an id; "Liquidity Regime Monitor" is a name. The id
    may only appear inside a machine attribute or an href."""
    for line in hub.splitlines():
        if "liquidity_regime" not in line:
            continue
        assert ('data-mq-workspace="liquidity_regime"' in line
                or 'href="macro_liquidity_regime.html"' in line
                or "macro_liquidity_regime.html" in line), line.strip()[:160]


def test_the_hub_is_bilingual_through_the_shared_toggle(hub: str) -> None:
    assert hub.count('class="l-en"') == hub.count('class="l-zh"')
    assert hub.count('class="l-en"') > 0


def test_the_hub_carries_no_executable_inline_script(hub: str) -> None:
    """`macro_suite.js` is out of R1 scope: the hub is HTML + CSS only."""
    import re
    for match in re.finditer(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", hub, re.S):
        body = match.group("body").strip()
        attrs = match.group("attrs")
        assert not body or "data-dbase" in attrs, body[:120]


# --------------------------------------------------------------------------
# the suite navigation shared with the fourteen workspace pages
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
        assert f'aria-current="page"' in html, page.output
