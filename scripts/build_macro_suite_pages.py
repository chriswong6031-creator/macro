"""Render the Macro & Monetary workspace pages (F01 suite, R1B).

One builder for the whole twelve-workspace suite. For each REGISTERED page it:

1. reads the suite manifest and the workspace snapshot published by R1A
   (``site/macrodata/workspaces/manifest.json`` and
   ``site/macrodata/workspaces/<workspace>/<region>/latest.json``);
2. validates FAIL-CLOSED through the shared contract
   (``engine.market_os.macro_workspaces.contract``): closed schema, exact
   contract id and version, and a recomputed ``content_sha256``; then
   cross-checks the manifest's declared hash and byte size against the body it
   actually read, so a manifest can never describe a generation the page is not
   showing;
3. builds the pre-labelled view model (``lib.macro_suite_view``) and renders the
   shared shell to a flat page under ``site/``.

A validation failure does NOT produce an empty page and does NOT fall back to a
previous build. It renders the honest refusal page: workspace identity, the
typed reason, the exact artifact receipt, and no state whatsoever.

Adding workspace 2..12 is one :class:`SuitePage` entry plus a thin template.

Usage:
    python -m scripts.build_macro_suite_pages
    python -m scripts.build_macro_suite_pages --root /path/to/repo
    python -m scripts.build_macro_suite_pages --data-root /tmp/tampered/macrodata
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_REPO_ROOT = Path(__file__).resolve().parents[1]
# Unconditional insert at position 0 — the conditional shape is not a pin: a repo
# root already present LATER in sys.path leaves a decoy tree ahead of it, which is
# exactly what the import-pin guard's hostile-tree proof rejects.
sys.path.insert(0, str(_REPO_ROOT))

from engine.market_os.macro_workspaces import contract, registry  # noqa: E402
from lib import macro_suite_view  # noqa: E402

# Shared across every workspace page: copied once per build, never per page.
# macro_command.css / macro_command.js are Macro Command's page-level assets —
# non-.j2 plain-copy files, so they are paired here (F01 Macro Command P1,
# frozen spec §9 standing notes) and re-synced with
# `python -m scripts.check_template_site_sync --fix`.
SHARED_ASSETS = ("macro_suite_boot.js", "macro_suite.css", "macro_suite.js",
                  "macro_command.css", "macro_command.js")

MIN_CLIENT_CONTRACT = f"{contract.CONTRACT_ID}@{contract.CONTRACT_VERSION}"


@dataclass(frozen=True)
class SuitePage:
    """One published workspace page. This is the whole per-page contract."""

    workspace_id: str
    region: str
    template: str
    output: str
    seo_title: str
    seo_desc: str


# The suite registry. A workspace appears here only when its producer is BUILT
# in engine.market_os.macro_workspaces.registry — a page is never advertised
# ahead of its data (production navigation law, architecture section 6.2).
# R1B shipped liquidity_regime; the R2 pages wave (2026-09-04) added the six
# MCS/cycle workspaces the R2 producer wave made BUILT.
SUITE_PAGES: tuple[SuitePage, ...] = (
    SuitePage(
        workspace_id="liquidity_regime",
        region="US",
        template="macro_liquidity_regime.html.j2",
        output="macro_liquidity_regime.html",
        seo_title="US Liquidity Regime Monitor — Macro & Monetary | MastermindX",
        seo_desc=(
            "Funding pressure against balance-sheet support for the United States, "
            "with every source clock, method receipt and typed gap shown."
        ),
    ),
    SuitePage(
        workspace_id="growth_real_economy",
        region="US",
        template="macro_growth_real_economy.html.j2",
        output="macro_growth_real_economy.html",
        seo_title="US Growth & Real Economy — Macro & Monetary | MastermindX",
        seo_desc=(
            "Growth momentum against level and breadth for the United States, with "
            "nowcast-versus-hard-data disagreement, source clocks and typed gaps shown."
        ),
    ),
    SuitePage(
        workspace_id="business_activity",
        region="US",
        template="macro_business_activity.html.j2",
        output="macro_business_activity.html",
        seo_title="US Business Activity — Macro & Monetary | MastermindX",
        seo_desc=(
            "Leading, coincident and lagging cycle tiers for the United States — "
            "composites refuse honestly when their legs fall below floor, with every "
            "source clock shown."
        ),
    ),
    SuitePage(
        workspace_id="labor_markets",
        region="US",
        template="macro_labor_markets.html.j2",
        output="macro_labor_markets.html",
        seo_title="US Labor Markets — Macro & Monetary | MastermindX",
        seo_desc=(
            "Labor demand against supply tightness for the United States, with "
            "source clocks, method receipts and typed coverage gaps shown."
        ),
    ),
    SuitePage(
        workspace_id="inflation_system",
        region="US",
        template="macro_inflation_system.html.j2",
        output="macro_inflation_system.html",
        seo_title="US Inflation System — Macro & Monetary | MastermindX",
        seo_desc=(
            "Inflation impulse against persistence and breadth for the United "
            "States, with sticky-versus-headline contradictions surfaced and "
            "release-lag clocks shown."
        ),
    ),
    SuitePage(
        workspace_id="monetary_policy",
        region="US",
        template="macro_monetary_policy.html.j2",
        output="macro_monetary_policy.html",
        seo_title="US Monetary Policy — Macro & Monetary | MastermindX",
        seo_desc=(
            "Policy stance against the market-implied path for the United States, "
            "with two-sided splits surfaced and every source clock and typed gap shown."
        ),
    ),
    SuitePage(
        workspace_id="financial_conditions",
        region="US",
        template="macro_financial_conditions.html.j2",
        output="macro_financial_conditions.html",
        seo_title="US Financial Conditions — Macro & Monetary | MastermindX",
        seo_desc=(
            "Financial-conditions level against impulse for the United States, with "
            "uncovered legs typed honestly and every source clock shown."
        ),
    ),
    SuitePage(
        workspace_id="liquidity_central_banks",
        region="US",
        template="macro_liquidity_central_banks.html.j2",
        output="macro_liquidity_central_banks.html",
        seo_title="Liquidity & Central Banks — Macro & Monetary | MastermindX",
        seo_desc=(
            "Global monetary impulse against Fed, ECB and BoJ balance-sheet stance, "
            "with the weekly grid clock, warmup windows and typed gaps shown."
        ),
    ),
    SuitePage(
        workspace_id="capital_structure",
        region="US",
        template="macro_capital_structure.html.j2",
        output="macro_capital_structure.html",
        seo_title="US Capital Structure — Macro & Monetary | MastermindX",
        seo_desc=(
            "A read-only census of the US corporate capital-structure event "
            "projection — coverage, classification and review backlog, with "
            "everything the owner does not publish typed honestly."
        ),
    ),
    SuitePage(
        workspace_id="housing_real_estate",
        region="US",
        template="macro_housing_real_estate.html.j2",
        output="macro_housing_real_estate.html",
        seo_title="US Housing & Real Estate — Macro & Monetary | MastermindX",
        seo_desc=(
            "Mortgage rates, starts, permits and home prices for the United States, "
            "with rights-blocked and uncovered legs typed honestly and every "
            "release clock shown."
        ),
    ),
    SuitePage(
        workspace_id="consumer_payments",
        region="US",
        template="macro_consumer_payments.html.j2",
        output="macro_consumer_payments.html",
        seo_title="US Consumer & Payments — Macro & Monetary | MastermindX",
        seo_desc=(
            "Retail sales, consumer sentiment, household credit, saving and "
            "delinquencies for the United States — payments panels and sources "
            "still being collected are typed honestly, never imputed."
        ),
    ),
    SuitePage(
        workspace_id="national_debt_liabilities",
        region="US",
        template="macro_national_debt_liabilities.html.j2",
        output="macro_national_debt_liabilities.html",
        seo_title="US National Debt & Liabilities — Macro & Monetary | MastermindX",
        seo_desc=(
            "Treasury cash balance, net issuance, auction demand and BIS debt-service "
            "reads for the United States, with the missing debt-stock lanes disclosed "
            "rather than fabricated."
        ),
    ),
    SuitePage(
        workspace_id="rates_curves",
        region="US",
        template="macro_rates_curves.html.j2",
        output="macro_rates_curves.html",
        seo_title="US Rates & Curves — Macro & Monetary | MastermindX",
        seo_desc=(
            "The Treasury curve node by node — slopes, inversions, real yields, "
            "breakevens, term premium and the policy corridor — every read dated "
            "and same-day-disciplined."
        ),
    ),
    SuitePage(
        workspace_id="trade_flows",
        region="US",
        template="macro_trade_flows.html.j2",
        output="macro_trade_flows.html",
        seo_title="US Trade Flows — Macro & Monetary | MastermindX",
        seo_desc=(
            "The US trade balance, exports, imports and trade prices on a "
            "balance-of-payments basis — collection state shown honestly while "
            "the source lanes come online."
        ),
    ),
)


@dataclass(frozen=True)
class HubPage:
    """The one suite entry point. It owns no producer and publishes no state of
    its own — it composes what the fourteen workspace owners already published."""

    template: str
    output: str
    seo_title: str
    seo_desc: str


HUB_PAGE = HubPage(
    template="macro_monetary.html.j2",
    output="macro_monetary.html",
    seo_title="Macro & Monetary — the current read across fourteen workspaces | MastermindX",
    seo_desc=(
        "One entry point to the Macro & Monetary research suite: the current state of "
        "each of the fourteen workspaces, what changed, and which inputs need attention "
        "— every read dated and every gap typed."
    ),
)

#: Workspaces whose body renders decision-first rather than in the frozen §6.3
#: order. R1 sets the pattern on ONE page (Sol ruling 2026-09-05); extending it is
#: one entry here, and the amendment record
#: research/market_intelligence_productization/MARKET_ONTOLOGY_F01_R1_DECISION_FIRST_AMENDMENT_2026-09-05.md
#: is what authorizes the supersession.
DECISION_FIRST_WORKSPACES = frozenset({"liquidity_regime"})


@dataclass(frozen=True)
class SubTab:
    """One sub-tab inside a Macro Command section that covers two workspaces
    (frozen spec §1.1). `id` is a bare token — the template writes the
    `#<section>/<subtab>` hash and DOM ids, never this dataclass (R10)."""

    id: str
    label_en: str
    label_zh: str
    workspace_id: str
    deep_href: str


@dataclass(frozen=True)
class Section:
    """One Macro Command left-rail section (frozen spec §1.1 / §1.3).

    Named for the CUSTOMER's question, not the producer's workspace title —
    `label_en`/`label_zh` are the question, and `subtabs` (when present) are
    named for the answer. Either `workspace_id`+`deep_href` (single-workspace
    section) or `subtabs` (two-workspace section) is set, never both."""

    id: str
    label_en: str
    label_zh: str
    workspace_id: str | None = None
    deep_href: str | None = None
    subtabs: tuple[SubTab, ...] = ()


# Macro Command left-rail sections — twelve, in the FIXED reading order a
# first-time customer asks them (frozen spec §1.1), never the producer
# registry order above (SUITE_PAGES) and never re-sorted with the data (G3,
# DNR:KILL-REGIME-SCORECARD). The template adds the leading "#" to `id` for
# hrefs/DOM ids (R10) — this constant carries bare tokens only.
SECTIONS: tuple[Section, ...] = (
    Section(id="overview", label_en="Overview", label_zh="总览"),
    Section(id="money", label_en="Money & liquidity", label_zh="资金与流动性", subtabs=(
        SubTab(id="liquidity", label_en="How much money is around", label_zh="市场资金",
               workspace_id="liquidity_regime", deep_href="macro_liquidity_regime.html"),
        SubTab(id="central_banks", label_en="What central banks are holding", label_zh="央行资产负债表",
               workspace_id="liquidity_central_banks", deep_href="macro_liquidity_central_banks.html"),
    )),
    Section(id="policy", label_en="Policy rates", label_zh="政策利率",
            workspace_id="monetary_policy", deep_href="macro_monetary_policy.html"),
    Section(id="rates", label_en="Rates & the curve", label_zh="利率与收益率曲线",
            workspace_id="rates_curves", deep_href="macro_rates_curves.html"),
    Section(id="inflation", label_en="Inflation", label_zh="通胀",
            workspace_id="inflation_system", deep_href="macro_inflation_system.html"),
    Section(id="growth", label_en="Growth", label_zh="经济增长", subtabs=(
        SubTab(id="economy", label_en="The whole economy", label_zh="整体经济",
               workspace_id="growth_real_economy", deep_href="macro_growth_real_economy.html"),
        SubTab(id="business", label_en="What companies are doing", label_zh="企业活动",
               workspace_id="business_activity", deep_href="macro_business_activity.html"),
    )),
    Section(id="jobs", label_en="Jobs", label_zh="就业",
            workspace_id="labor_markets", deep_href="macro_labor_markets.html"),
    Section(id="housing", label_en="Housing", label_zh="房地产",
            workspace_id="housing_real_estate", deep_href="macro_housing_real_estate.html"),
    Section(id="consumer", label_en="Consumers", label_zh="消费者",
            workspace_id="consumer_payments", deep_href="macro_consumer_payments.html"),
    Section(id="credit", label_en="Borrowing costs", label_zh="融资环境", subtabs=(
        SubTab(id="borrowing", label_en="How hard it is to borrow", label_zh="融资难易",
               workspace_id="financial_conditions", deep_href="macro_financial_conditions.html"),
        SubTab(id="funding", label_en="How companies fund themselves", label_zh="企业融资结构",
               workspace_id="capital_structure", deep_href="macro_capital_structure.html"),
    )),
    Section(id="debt", label_en="Government debt", label_zh="政府债务",
            workspace_id="national_debt_liabilities", deep_href="macro_national_debt_liabilities.html"),
    Section(id="trade", label_en="Trade", label_zh="贸易往来",
            workspace_id="trade_flows", deep_href="macro_trade_flows.html"),
)


def _layout_for(workspace_id: str) -> str:
    return (macro_suite_view.LAYOUT_DECISION_FIRST
            if workspace_id in DECISION_FIRST_WORKSPACES
            else macro_suite_view.LAYOUT_GRAMMAR)


def suite_nav(current_output: str | None) -> dict[str, Any]:
    """The in-suite navigation context shared by the hub and all fourteen pages.

    Built from the closed registry in SUITE_PAGES order, so the switcher can
    never advertise a workspace the producer registry does not carry, and can
    never present a different order from the hub.
    """
    # `entries`, never `items`: `nav.items` in Jinja resolves to the dict method.
    entries = []
    for page in SUITE_PAGES:
        identity = _identity(page)
        entries.append({
            "workspace_id": page.workspace_id,
            "href": page.output,
            "title": identity["title"],
            "current": page.output == current_output,
        })
    return {
        "hub": {"href": HUB_PAGE.output, "current": HUB_PAGE.output == current_output},
        "entries": entries,
    }



class SnapshotRefused(Exception):
    """The published artifact did not clear the closed contract.

    ``kind`` is a token from the contract's closed null vocabulary (section
    7.7), so the refusal the reader sees is typed rather than free text.
    """

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


def _temp_sibling(path: Path) -> Path:
    return path.with_name(f".{path.name}.{os.getpid()}.tmp")


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = _temp_sibling(destination)
    try:
        shutil.copyfile(source, temp)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def _read_json(path: Path) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SnapshotRefused("SOURCE_FAILED", f"cannot read {path.name}: {exc.strerror or exc}") from exc
    try:
        return json.loads(raw.decode("utf-8")), len(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotRefused("SOURCE_FAILED", f"{path.name} is not valid JSON: {exc}") from exc


def read_workspace(data_root: Path, page: SuitePage) -> tuple[dict, dict]:
    """Load + validate one workspace artifact. Raises :class:`SnapshotRefused`.

    Order matters: the manifest is read FIRST (it is written LAST by the
    producer, so its presence implies the body is already on disk), then the
    body, then the body is checked against what the manifest declared. A reader
    that trusted either half alone could render one generation under another
    generation's header.
    """
    manifest_path = data_root / "workspaces" / "manifest.json"
    manifest, _ = _read_json(manifest_path)
    if not isinstance(manifest, Mapping):
        raise SnapshotRefused("SOURCE_FAILED", "manifest.json is not a JSON object")

    declared_contract = manifest.get("min_client_contract")
    if declared_contract != MIN_CLIENT_CONTRACT:
        raise SnapshotRefused(
            "COMPUTATION_REFUSED",
            f"manifest requires client contract {declared_contract!r}; this page implements "
            f"{MIN_CLIENT_CONTRACT!r}",
        )

    key = f"{page.workspace_id}/{page.region}"
    entry = (manifest.get("workspaces") or {}).get(key)
    if not isinstance(entry, Mapping):
        raise SnapshotRefused("NOT_COVERED", f"the suite manifest publishes no entry for {key!r}")

    relative = str(entry.get("path") or "")
    if not relative or relative.startswith("/") or ".." in Path(relative).parts:
        raise SnapshotRefused("SOURCE_FAILED", f"manifest path for {key!r} is not a safe relative path")

    body_path = data_root / relative
    snapshot, byte_size = _read_json(body_path)

    try:
        contract.validate(snapshot)
    except contract.ContractError as exc:
        raise SnapshotRefused("COMPUTATION_REFUSED", str(exc)) from exc

    published = (snapshot.get("generation") or {}).get("content_sha256")
    if entry.get("content_sha256") != published:
        raise SnapshotRefused(
            "DISAGREEMENT",
            f"manifest declares content_sha256 {entry.get('content_sha256')!r} but the body carries "
            f"{published!r}",
        )
    if isinstance(entry.get("bytes"), int) and entry["bytes"] != byte_size:
        raise SnapshotRefused(
            "DISAGREEMENT",
            f"manifest declares {entry['bytes']} bytes but the body on disk is {byte_size}",
        )
    if snapshot.get("workspace", {}).get("id") != page.workspace_id or \
            snapshot.get("region", {}).get("code") != page.region:
        raise SnapshotRefused(
            "DISAGREEMENT",
            "the artifact's own workspace/region identity does not match the manifest entry",
        )

    artifact = {
        "path": f"macrodata/{relative}",
        "manifest_path": "macrodata/workspaces/manifest.json",
        "sha256": published,
        "bytes": byte_size,
        "min_client_contract": MIN_CLIENT_CONTRACT,
    }
    return dict(snapshot), artifact


def _identity(page: SuitePage) -> dict[str, Any]:
    """Workspace identity for the refusal page, taken from the closed registry —
    never from the artifact we just refused to trust."""
    entry = registry.entry(page.workspace_id)
    return {
        "title": {"en": entry.get("title_en") or page.workspace_id,
                  "zh": entry.get("title_zh") or entry.get("title_en") or page.workspace_id},
        "subtitle": {"en": entry.get("subtitle_en") or "",
                     "zh": entry.get("subtitle_zh") or entry.get("subtitle_en") or ""},
    }


_REGION_NAMES = {"US": "United States"}


def _environment(root: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=True,
        undefined=StrictUndefined,
    )


def render_page(env: Environment, page: SuitePage, view: Mapping[str, Any]) -> str:
    html = env.get_template(page.template).render(
        view=view,
        workspace_id=page.workspace_id,
        region_code=page.region,
        page_title=view["workspace"]["title"]["en"],
        page_seo_title=page.seo_title,
        page_seo_desc=page.seo_desc,
        page_seo_path=page.output,
        active_section="research",
        active_page=Path(page.output).stem,
        suite_nav=suite_nav(page.output),
    )
    # The shared navigation partials indent around conditional blocks; normalise
    # generated-only trailing whitespace so the committed page stays diff-clean.
    return "\n".join(line.rstrip() for line in html.splitlines()) + "\n"


def build_page(root: Path, page: SuitePage, *, data_root: Path, out_dir: Path,
               env: Environment, page_built_at: str) -> tuple[Path, bool]:
    """Render one workspace page. Returns ``(path, ok)`` — ``ok`` is False when
    the page rendered the honest refusal instead of a state."""
    identity = _identity(page)
    fallback_artifact = {
        "path": f"macrodata/workspaces/{page.workspace_id}/{page.region}/latest.json",
        "manifest_path": "macrodata/workspaces/manifest.json",
        "sha256": None,
        "bytes": None,
        "min_client_contract": MIN_CLIENT_CONTRACT,
    }
    try:
        snapshot, artifact = read_workspace(data_root, page)
        view = macro_suite_view.build_view(snapshot, page_built_at=page_built_at,
                                           artifact=artifact, layout=_layout_for(page.workspace_id))
        ok = True
        hub_entry: dict[str, Any] = {"snapshot": snapshot, "failure": None}
    except SnapshotRefused as refusal:
        print(
            f"::warning title=macro_suite_page::{page.workspace_id}/{page.region} refused "
            f"({refusal.kind}: {refusal.detail}) — rendering the degraded page",
            flush=True,
        )
        view = macro_suite_view.degraded_view(
            workspace_id=page.workspace_id,
            title=identity["title"],
            subtitle=identity["subtitle"],
            region_code=page.region,
            region_display_name=_REGION_NAMES.get(page.region, page.region),
            page_built_at=page_built_at,
            artifact=fallback_artifact,
            failure_kind=refusal.kind,
            failure_detail=refusal.detail,
        )
        ok = False
        hub_entry = {"snapshot": None,
                     "failure": {"kind": refusal.kind, "detail": refusal.detail}}

    html = render_page(env, page, view)

    # write_page owns the depth-aware data-base shim. Route through a temporary
    # file so even an interrupted builder cannot leave a partial page served.
    from lib.pages import write_page  # noqa: PLC0415

    out_dir.mkdir(parents=True, exist_ok=True)
    destination = out_dir / page.output
    temp = _temp_sibling(destination)
    try:
        write_page(temp, html)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)

    hub_entry.update({
        "workspace_id": page.workspace_id,
        "region": page.region,
        "output": page.output,
        "title": identity["title"],
        "subtitle": identity["subtitle"],
    })
    return destination, ok, hub_entry


def _detail_link(title_by_workspace: Mapping[str, Mapping[str, str]], workspace_id: str,
                  deep_href: str) -> dict[str, Any]:
    title = title_by_workspace.get(workspace_id)
    return {"title": title or {"en": workspace_id, "zh": workspace_id}, "href": deep_href}


def _macro_command_sections(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Build the `sections` template context from the static SECTIONS constant.

    Every optional field a P1 panel does not populate (question / stance /
    primer / caption / watching / tone — R3) is set to an explicit falsy
    value rather than omitted: the render environment uses
    ``StrictUndefined``, so a bare ``{% if s.tone %}`` on a dict missing the
    key raises rather than evaluating falsy.
    """
    title_by_workspace = {entry["workspace_id"]: entry["title"] for entry in entries}
    all_links = [_detail_link(title_by_workspace, entry["workspace_id"], entry["output"])
                 for entry in entries]

    sections: list[dict[str, Any]] = []
    for section in SECTIONS:
        is_overview = section.id == "overview"
        subtabs: list[dict[str, Any]] | None = None
        detail_links: list[dict[str, Any]]
        if section.subtabs:
            subtabs = [{
                "id": tab.id,
                "label": {"en": tab.label_en, "zh": tab.label_zh},
                "first": index == 0,
                "deep_href": tab.deep_href,
            } for index, tab in enumerate(section.subtabs)]
            detail_links = [_detail_link(title_by_workspace, tab.workspace_id, tab.deep_href)
                            for tab in section.subtabs]
        elif is_overview:
            detail_links = all_links
        else:
            detail_links = [_detail_link(title_by_workspace, section.workspace_id, section.deep_href)]

        sections.append({
            "id": section.id,
            "label": {"en": section.label_en, "zh": section.label_zh},
            "first": is_overview,
            "tone": None,
            "question": None,
            "stance": None,
            "primer": None,
            "primer_open": False,
            "caption": None,
            "watching": None,
            "deep_href": section.deep_href,
            "subtabs": subtabs,
            "subtab_group_en": section.label_en if subtabs else None,
            "detail_links": detail_links,
        })
    return sections


def _macro_command_analyst(root: Path) -> dict[str, Any]:
    """`analyst.mountable` (§8, R8): true when the sitewide brain widget's
    launcher stub is baked into theme.js at build time. Degraded fallback
    (bare `<a href="chat.html">`, §8) only when it is genuinely absent."""
    try:
        theme_js = (root / "templates" / "theme.js").read_text(encoding="utf-8")
    except OSError:
        return {"mountable": False}
    return {"mountable": "mmb-boot" in theme_js}


def build_hub(entries: Sequence[Mapping[str, Any]], *, out_dir: Path,
              env: Environment, page_built_at: str, root: Path) -> Path:
    """Render the suite hub from what the fourteen pages just read.

    The hub reads NO artifact of its own. Every row is the snapshot (or the typed
    refusal) that the workspace page beside it was built from, so the hub and the
    page it links to cannot disagree about state, date or coverage. A workspace
    the builder could not read arrives here as a refusal, and the hub says so.

    Macro Command (F01 Macro Command P1) supersedes the hub's prior markup
    entirely (frozen spec §2.7): `sections`, `analyst`, `read` and `strip` are
    the new page's context. P1 ships no state computation (R3) — `read` and
    `strip` are honest-empty so the page's own built-in fallback copy
    ("Today's reading is incomplete...") renders rather than fabricated data.
    """
    html = env.get_template(HUB_PAGE.template).render(
        page_title="Macro & Monetary",
        page_seo_title=HUB_PAGE.seo_title,
        page_seo_desc=HUB_PAGE.seo_desc,
        page_seo_path=HUB_PAGE.output,
        active_section="research",
        active_page=Path(HUB_PAGE.output).stem,
        suite_nav=suite_nav(HUB_PAGE.output),
        sections=_macro_command_sections(entries),
        analyst=_macro_command_analyst(root),
        read={"as_of": None, "as_of_display": None, "clauses": [], "omitted": False},
        strip=[],
    )
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"

    from lib.pages import write_page  # noqa: PLC0415

    out_dir.mkdir(parents=True, exist_ok=True)
    destination = out_dir / HUB_PAGE.output
    temp = _temp_sibling(destination)
    try:
        write_page(temp, html)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
    return destination


def render(root: Path | str = _REPO_ROOT, *, data_root: Path | str | None = None,
           out_dir: Path | str | None = None, page_built_at: str | None = None) -> list[Path]:
    """Render every registered suite page plus the shared assets."""
    root = Path(root).resolve()
    site = Path(out_dir) if out_dir else root / "site"
    site.mkdir(parents=True, exist_ok=True)
    data = Path(data_root) if data_root else root / "site" / "macrodata"
    stamp = page_built_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    env = _environment(root)

    written: list[Path] = []
    entries: list[Mapping[str, Any]] = []
    for page in SUITE_PAGES:
        path, _ok, entry = build_page(root, page, data_root=data, out_dir=site, env=env,
                                      page_built_at=stamp)
        written.append(path)
        entries.append(entry)
    written.append(build_hub(entries, out_dir=site, env=env, page_built_at=stamp, root=root))
    for asset in SHARED_ASSETS:
        _atomic_copy(root / "templates" / asset, site / asset)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--data-root", type=Path, default=None,
                        help="macrodata root holding workspaces/ (default: <root>/site/macrodata)")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="output directory (default: <root>/site)")
    args = parser.parse_args(argv)
    try:
        pages = render(args.root, data_root=args.data_root, out_dir=args.out_dir)
    except Exception as exc:  # noqa: BLE001 — a precise non-zero helps the shared render lane
        print(f"::error title=macro_suite_pages::build failed ({type(exc).__name__}: {exc})", flush=True)
        return 1
    for page in pages:
        print(f"wrote {page}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
