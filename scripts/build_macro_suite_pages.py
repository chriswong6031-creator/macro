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
from typing import Any, Mapping

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine.market_os.macro_workspaces import contract, registry  # noqa: E402
from lib import macro_suite_view  # noqa: E402

# Shared across every workspace page: copied once per build, never per page.
SHARED_ASSETS = ("macro_suite_boot.js", "macro_suite.css", "macro_suite.js")

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
)


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
        view = macro_suite_view.build_view(snapshot, page_built_at=page_built_at, artifact=artifact)
        ok = True
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
    return destination, ok


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
    for page in SUITE_PAGES:
        path, _ok = build_page(root, page, data_root=data, out_dir=site, env=env,
                               page_built_at=stamp)
        written.append(path)
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
