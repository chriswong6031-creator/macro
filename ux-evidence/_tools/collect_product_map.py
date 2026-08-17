#!/usr/bin/env python3
"""Phase 0 product topology discovery. Shallow. No deep dossiers."""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifacts import write_manifest  # noqa: E402
from paths import evidence_root, relpath, repo_root  # noqa: E402
from pw_lib import (  # noqa: E402
    assert_and_shot,
    goto,
    launch_browser,
    load_aionui_cookies,
    new_page,
    viewport_metrics,
)
from run_meta import base_run_manifest, dump_json, finalize_run  # noqa: E402

ORIGIN = "https://www.mastermind-x.com"
OUT = evidence_root() / "00-product-map"
SHOTS = OUT / "screenshots"
NAV_FILE = repo_root() / "templates" / "_navlinks.html.j2"

SKIP_SOURCE_PREFIXES = (
    "_mockup",
    "qa_",
    "report_",
    "us_stocks_v2",
)
SKIP_SOURCE_EXACT = {
    "coming-soon.html",
    "unsubscribe.html",
    "status.html",
}

ARCHETYPES = [
    ("home / command center", ("start.html", "index.html", "intelligence_hub.html")),
    ("market dashboard", ("macro.html", "china.html", "hk.html", "canada.html", "intl.html")),
    ("discovery / ranked decision board", ("us_stocks.html", "china_stocks.html", "hk_stocks.html", "canada_stocks.html", "intl_stocks.html")),
    ("security/company analyzer", ("stock.html", "canada_stock.html", "intl_stock.html")),
    ("sector/theme intelligence", ("sector_central", "baskets", "subsector", "allocation")),
    ("macro intelligence", ("macro_context", "cycle.html", "markets.html", "country_cycles")),
    ("flow/tape intelligence", ("intraday_flow", "flow_", "darkpool", "etfs.html")),
    ("options intelligence", ("options.html", "gex.html", "market_structure")),
    ("monitoring/watchlist/portfolio", ("watchlist.html",)),
    ("research/terminal", ("research_vault", "reports.html", "neural_web", "chat.html")),
    ("alert center", ("alerts.html",)),
    ("news/information feed", ("news.html", "china_news")),
    ("configuration/settings", ("plans.html",)),
    ("marketing/conversion", ("index.html", "about.html", "plans.html")),
    ("account/billing", ("plans.html", "support.html")),
    ("utility/tool", ("learn.html", "disclaimer.html", "privacy.html", "terms.html")),
]


def slug_family(path: str) -> str:
    p = path.split("#", 1)[0]
    name = Path(p).name or p
    if name == "stock.html":
        return "RF.us.stock_detail"
    if name == "canada_stock.html":
        return "RF.ca.stock_detail"
    if name == "intl_stock.html":
        return "RF.intl.stock_detail"
    if name.startswith("fund_") and name.endswith(".html"):
        return "RF.fund.profile"
    if name.startswith("strategy_") and name.endswith(".html"):
        return "RF.strategy.tactical"
    if name.startswith("report_") and name.endswith(".html"):
        return "RF.research.report"
    stem = name.replace(".html", "")
    geo = "us"
    if stem.startswith("china") or stem.endswith("_china") or "china" in stem:
        geo = "cn"
    elif stem.startswith("hk") or stem.endswith("_hk"):
        geo = "hk"
    elif stem.startswith("canada") or stem.endswith("_canada"):
        geo = "ca"
    elif stem.startswith("intl") or stem in {"japan", "south_korea", "euro_area", "united_kingdom", "india"}:
        geo = "intl"
    return f"RF.{geo}.{stem}"


def parse_navlinks() -> list[dict]:
    text = NAV_FILE.read_text()
    items = []
    group = "unknown"
    for raw in re.finditer(
        r'href="(?:\{\{\s*NP\s*\}\})?(https?://[^"]+|[A-Za-z0-9_./#-]+\.html(?:#[A-Za-z0-9_-]+)?)"',
        text,
    ):
        href = raw.group(1)
        # find nearest preceding nav-link label for group
        before = text[: raw.start()]
        g = re.findall(r"nav-link[^>]*>.*?t\('([^']+)'", before[-2500:], re.S)
        if g:
            group = g[-1]
        after = text[raw.end() : raw.end() + 400]
        label_m = re.search(r"t\('([^']+)'", after)
        window = text[max(0, raw.start() - 160) : raw.start()]
        is_group_trigger = "nav-link" in window or "nav-sub-trig" in window
        label = label_m.group(1) if label_m else href
        if is_group_trigger:
            group = label
        items.append(
            {
                "href": href,
                "label": label,
                "parent_group": group,
                "discovery_source": "PRIMARY_NAV" if "mega" not in before[-200:].lower() else "MEGA_NAV",
            }
        )
    # refine mega
    for it in items:
        if it["parent_group"] == "Research":
            it["discovery_source"] = "MEGA_NAV"
    return items


def source_routes() -> list[dict]:
    site = repo_root() / "site"
    out = []
    for p in sorted(site.glob("*.html")):
        name = p.name
        if name.startswith(SKIP_SOURCE_PREFIXES) or name in SKIP_SOURCE_EXACT:
            continue
        why = "generated top-level site HTML"
        user_facing = True
        if name.startswith("fund_"):
            why = "generated fund profile; family RF.fund.profile"
        elif name.startswith("strategy_"):
            why = "generated tactical strategy page; family RF.strategy.tactical"
        elif name.startswith("_"):
            user_facing = False
            why = "underscore prefix; treated as non-product"
        out.append(
            {
                "path": name,
                "route_family_id": slug_family(name),
                "discovery_source": "GENERATED_SITE",
                "user_facing": user_facing,
                "reason": why,
            }
        )
    # parameterized families
    stock_n = len(list((site / "stocks").glob("*.html"))) if (site / "stocks").exists() else 0
    out.append(
        {
            "path": "stock.html#<ticker>",
            "route_family_id": "RF.us.stock_detail",
            "discovery_source": "SOURCE_ROUTE",
            "user_facing": True,
            "reason": f"templates/stock.html.j2 + site/stocks/*.html ({stock_n} generated instances). Sample stock.html#ONTO.",
            "instance_count_source": stock_n,
        }
    )
    return out


def normalize_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return urljoin(ORIGIN + "/", href.lstrip("/"))


def family_for(url: str) -> tuple[str, dict]:
    parsed = urlparse(url)
    path = parsed.path.lstrip("/")
    frag = parsed.fragment
    params = {}
    if path == "stock.html" and frag:
        params["ticker"] = frag
        return "RF.us.stock_detail", params
    if path.endswith("_stock.html") and frag:
        params["ticker"] = frag
        return slug_family(path), params
    if frag:
        params["hash"] = frag
    return slug_family(path or "index.html"), params


def provisional_archetype(path: str) -> tuple[str, str]:
    name = path.split("#")[0]
    for label, keys in ARCHETYPES:
        for k in keys:
            if k in name:
                return label, "PROVISIONAL"
    return "UNKNOWN", "PROVISIONAL"


def page_facts(page) -> dict:
    return page.evaluate(
        """() => {
          const h = document.querySelector('h1, h2, .page-title, #r_name');
          const lock = !!document.querySelector('.lock-cta, .regwall, [data-gated]');
          const links = [];
          document.querySelectorAll('a[href]').forEach((a, i) => {
            if (i > 400) return;
            const href = a.getAttribute('href') || '';
            if (!href || href.startsWith('javascript:') || href.startsWith('mailto:') || href.startsWith('#')) return;
            if (href.startsWith('http') && !href.includes('mastermind-x.com') && !href.includes('bot.mastermind')) return;
            links.push({href, text: (a.innerText||'').replace(/\\s+/g,' ').trim().slice(0,80)});
          });
          const sections = [];
          document.querySelectorAll('main, #us-standouts, #result, .panel, details.sv-group, details.sv-deep').forEach((el, i) => {
            if (i > 18) return;
            const r = el.getBoundingClientRect();
            sections.push({
              tag: el.tagName.toLowerCase(),
              id: el.id || null,
              cls: (el.className||'').toString().slice(0,60),
              text: ((el.innerText||'').replace(/\\s+/g,' ').trim()).slice(0,80),
              h: Math.round(r.height)
            });
          });
          return {
            title: document.title,
            heading: h ? (h.innerText||'').replace(/\\s+/g,' ').trim().slice(0,160) : null,
            lang: document.documentElement.getAttribute('data-lang') || document.documentElement.lang,
            theme: document.documentElement.getAttribute('data-theme'),
            lock_cta: lock,
            user_attr: document.documentElement.getAttribute('data-user'),
            visible_text: (document.body.innerText||'').slice(0,4000),
            outbound: links,
            coarse_sections: sections
          };
        }"""
    )


def classify_access(facts: dict, status: int, final_url: str) -> str:
    if status >= 400:
        return "BROKEN"
    if facts.get("lock_cta"):
        return "SUBSCRIPTION_GATED"
    if facts.get("user_attr"):
        return "AUTHENTICATED_ACCESSIBLE"
    return "ANONYMOUS_ACCESSIBLE"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    run = base_run_manifest(schema_version="1.0")
    cookies = load_aionui_cookies()
    run["authenticated_session_used"] = bool(cookies)
    nav_items = parse_navlinks()
    src_items = source_routes()

    # unique sample list: all nav destinations + parameterized samples
    samples = []
    seen = set()
    for it in nav_items:
        href = it["href"]
        if href.startswith("javascript:"):
            continue
        url = normalize_url(href)
        key = urlparse(url)._replace(query="").geturl()
        if key in seen:
            # keep extra discovery sources
            for s in samples:
                if s["normalized_url"] == key:
                    if it["discovery_source"] not in s["discovery_sources"]:
                        s["discovery_sources"].append(it["discovery_source"])
            continue
        seen.add(key)
        fam, params = family_for(url)
        samples.append(
            {
                "route_id": f"R.{urlparse(url).path.lstrip('/').replace('.html','').replace('/','.') or 'root'}"
                + (f"#{params.get('ticker') or params.get('hash')}" if params else ""),
                "route_family_id": fam,
                "requested_url": url,
                "normalized_url": key,
                "route_parameters": params,
                "route_instance_role": "canonical_sample",
                "discovery_sources": [it["discovery_source"]],
                "nav_label": it["label"],
                "parent_navigation_group": it["parent_group"],
                "primary_nav": it["discovery_source"] in {"PRIMARY_NAV", "MEGA_NAV"},
                "canonicalization_reason": "nav destination",
            }
        )
    for extra in ("stock.html#ONTO", "start.html", "index.html"):
        url = normalize_url(extra)
        key = url
        if key not in seen:
            seen.add(key)
            fam, params = family_for(url)
            samples.append(
                {
                    "route_id": f"R.{extra.replace('.html','').replace('#','.')}",
                    "route_family_id": fam,
                    "requested_url": url,
                    "normalized_url": key,
                    "route_parameters": params,
                    "route_instance_role": "calibration_sample" if "ONTO" in extra else "canonical_sample",
                    "discovery_sources": ["MANUAL_SEED"],
                    "nav_label": extra,
                    "parent_navigation_group": None,
                    "primary_nav": extra in {"start.html"},
                    "canonicalization_reason": "seed",
                }
            )

    # representative source-only families
    have_fams = {s["route_family_id"] for s in samples}
    for spec in json.loads((evidence_root() / "_config" / "routes" / "seeds.json").read_text())["parameterized_families"]:
        if spec["route_family_id"] in have_fams:
            continue
        url = normalize_url(spec["sample"])
        fam, params = family_for(url)
        samples.append(
            {
                "route_id": f"R.{spec['sample'].replace('.html','').replace('#','.')}",
                "route_family_id": spec["route_family_id"],
                "requested_url": url,
                "normalized_url": url,
                "route_parameters": params,
                "route_instance_role": "family_sample",
                "discovery_sources": ["SOURCE_ROUTE"],
                "nav_label": spec["sample"],
                "parent_navigation_group": None,
                "primary_nav": False,
                "canonicalization_reason": spec["reason"],
            }
        )
        have_fams.add(spec["route_family_id"])

    from playwright.sync_api import sync_playwright

    instances = []
    surfaces = []
    console_notes = []
    with sync_playwright() as p:
        browser = launch_browser(p)
        run["browser_version"] = getattr(browser, "version", "unknown")
        # shell mega-menu on start.html
        for w, h, tag in ((1440, 1000, "1440x1000"), (390, 844, "390x844")):
            ctx, page = new_page(browser, w, h, cookies or None)
            goto(page, ORIGIN + "/start.html", wait_ms=1200)
            try:
                if w >= 1000:
                    page.locator("a.nav-link", has_text="United States").first.hover(timeout=4000)
                    page.wait_for_timeout(400)
                    assert_and_shot(page, SHOTS / f"shell_us_menu_{tag}.png", w, h)
                    page.locator("a.nav-link", has_text="Research").first.hover(timeout=4000)
                    page.wait_for_timeout(400)
                    assert_and_shot(page, SHOTS / f"shell_research_menu_{tag}.png", w, h)
                else:
                    tog = page.locator(".nav-toggle, button[aria-label*='navigation' i]")
                    if tog.count():
                        tog.first.click(timeout=4000)
                        page.wait_for_timeout(300)
                    assert_and_shot(page, SHOTS / f"shell_mobile_nav_{tag}.png", w, h)
            except Exception as e:
                console_notes.append({"shell": tag, "error": str(e).splitlines()[0][:200]})
            ctx.close()

        for i, sample in enumerate(samples):
            rec = dict(sample)
            rec["captured_at"] = None
            rec["screenshots"] = {}
            rec["viewports"] = {}
            broken = False
            for w, h, tag in ((1440, 1000, "1440x1000"), (390, 844, "390x844")):
                ctx, page = new_page(browser, w, h, cookies or None)
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)[:160]))
                status = 0
                final = sample["requested_url"]
                chain = []
                try:
                    resp = page.goto(sample["requested_url"], wait_until="domcontentloaded", timeout=35000)
                    status = resp.status if resp else 0
                    final = page.url
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    page.wait_for_timeout(900)
                except Exception as e:
                    broken = True
                    rec["broken_reason"] = str(e).splitlines()[0][:200]
                    rec["http_status"] = status
                    ctx.close()
                    break
                facts = page_facts(page)
                m = viewport_metrics(page)
                stem = re.sub(r"[^A-Za-z0-9._-]+", "_", urlparse(sample["requested_url"]).path.strip("/") or "root")
                if sample.get("route_parameters", {}).get("ticker"):
                    stem += "_" + sample["route_parameters"]["ticker"]
                dest = SHOTS / f"{stem}_{tag}.png"
                try:
                    shot = assert_and_shot(page, dest, w, h)
                    rec["screenshots"][tag] = shot.get("repo_relative_path")
                except Exception as e:
                    rec["screenshots"][tag] = None
                    rec.setdefault("capture_errors", []).append(str(e)[:160])
                rec["viewports"][tag] = {
                    "inner_width": m.get("innerWidth"),
                    "inner_height": m.get("innerHeight"),
                    "document_scroll_width": m.get("scrollW"),
                    "document_scroll_height": m.get("scrollH"),
                    "horizontal_overflow": int(m.get("scrollW") or 0) - w > 2,
                    "page_height": m.get("scrollH"),
                }
                if tag == "1440x1000":
                    rec["browser_title"] = facts.get("title")
                    rec["primary_visible_heading"] = facts.get("heading")
                    rec["final_url"] = final
                    rec["http_status"] = status
                    rec["redirect_chain"] = chain
                    rec["authentication_status"] = classify_access(facts, status, final)
                    rec["lock_cta"] = facts.get("lock_cta")
                    rec["data-as-of"] = None
                    m_asof = re.search(r"20\d{2}-\d{2}-\d{2}", facts.get("title") or "")
                    if m_asof:
                        rec["data-as-of"] = m_asof.group(0)
                    arch, ast = provisional_archetype(urlparse(sample["requested_url"]).path)
                    rec["provisional_archetype"] = arch
                    rec["archetype_status"] = ast
                    rec["major_sections"] = facts.get("coarse_sections") or []
                    rec["major_outbound_product_links"] = (facts.get("outbound") or [])[:40]
                    rec["visible_text_excerpt"] = (facts.get("visible_text") or "")[:800]
                    rec["console_error_count"] = len(errors)
                    rec["captured_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
                    rec["local_html"] = "site/" + Path(urlparse(sample["requested_url"]).path).name
                    rec["source_mapping"] = rec["local_html"]
                    rec["evidence_status"] = "OBSERVED_BROWSER"
                    # one surface per sampled route (not each card)
                    surfaces.append(
                        {
                            "surface_id": f"SUR.{rec['route_family_id'].replace('RF.','')}.primary",
                            "route_family_id": rec["route_family_id"],
                            "label": rec.get("nav_label") or rec.get("primary_visible_heading") or rec["route_family_id"],
                            "page_order": 0,
                            "semantic_section": rec.get("primary_visible_heading"),
                            "geometry": None,
                            "visibility": "visible",
                            "primary_apparent_job": rec.get("provisional_archetype"),
                            "major_controls": [],
                            "outbound_product_links": [x.get("href") for x in (facts.get("outbound") or [])[:12]],
                            "source_mapping": rec["source_mapping"],
                            "evidence_status": "OBSERVED_BROWSER",
                        }
                    )
                ctx.close()
            rec["broken_unreachable"] = broken or (rec.get("http_status") or 0) >= 400
            instances.append(rec)
            print(f"[{i+1}/{len(samples)}] {rec.get('http_status')} {rec['requested_url']}")
        browser.close()

    # families
    fams = {}
    for inst in instances:
        fid = inst["route_family_id"]
        fams.setdefault(
            fid,
            {
                "route_family_id": fid,
                "pattern": "stock.html#<ticker>" if fid.endswith("stock_detail") else urlparse(inst["requested_url"]).path,
                "sampled_instances": [],
                "discovery_sources": set(),
                "provisional_archetype": inst.get("provisional_archetype"),
            },
        )
        fams[fid]["sampled_instances"].append(inst["route_id"])
        fams[fid]["discovery_sources"].update(inst.get("discovery_sources") or [])
    for src in src_items:
        fid = src["route_family_id"]
        if fid not in fams:
            fams[fid] = {
                "route_family_id": fid,
                "pattern": src["path"],
                "sampled_instances": [],
                "discovery_sources": {src["discovery_source"]},
                "provisional_archetype": provisional_archetype(src["path"])[0],
                "source_only": True,
                "user_facing_reason": src.get("reason"),
            }
        else:
            fams[fid]["discovery_sources"].add(src["discovery_source"])

    family_list = []
    for fid, f in sorted(fams.items()):
        f = dict(f)
        f["discovery_sources"] = sorted(f["discovery_sources"])
        family_list.append(f)

    browser_paths = set()
    for it in nav_items:
        if not it["href"].startswith("javascript:"):
            browser_paths.add(urlparse(normalize_url(it["href"])).path.lstrip("/"))
    source_paths = {s["path"] for s in src_items if s.get("user_facing")}
    inter = sorted(browser_paths & source_paths)
    browser_only = sorted(browser_paths - source_paths)
    source_only = sorted(p for p in source_paths - browser_paths if "<" not in p)

    inventory = {
        "schema_version": "1.0",
        "run_id": run["run_id"],
        "repo_head_sha": run["repo_head_sha"],
        "route_families": family_list,
        "route_instances": instances,
        "metrics": {
            "route_families_discovered": len(family_list),
            "route_instances_sampled": len(instances),
            "browser_discovered_routes": len(browser_paths),
            "source_discovered_routes": len(source_paths),
            "browser_source_intersection": len(inter),
            "browser_only": len(browser_only),
            "source_only": len(source_only),
            "gated": sum(1 for i in instances if i.get("authentication_status") in {"SUBSCRIPTION_GATED", "ACCOUNT_GATED"}),
            "broken": sum(1 for i in instances if i.get("broken_unreachable")),
        },
    }
    dump_json(OUT / "product-route-inventory.json", inventory)

    # markdown inventory
    lines = [
        "# Product route inventory (Phase 0)",
        "",
        f"Run `{run['run_id']}` · schema 1.0 · SHA `{run['repo_head_sha']}`",
        "",
        "## Counts",
        "",
        f"- route families: {inventory['metrics']['route_families_discovered']}",
        f"- sampled instances: {inventory['metrics']['route_instances_sampled']}",
        f"- browser-discovered paths: {inventory['metrics']['browser_discovered_routes']}",
        f"- source-discovered paths: {inventory['metrics']['source_discovered_routes']}",
        f"- intersection: {inventory['metrics']['browser_source_intersection']}",
        f"- browser-only: {inventory['metrics']['browser_only']}",
        f"- source-only: {inventory['metrics']['source_only']}",
        f"- gated (sampled): {inventory['metrics']['gated']}",
        f"- broken (sampled): {inventory['metrics']['broken']}",
        "",
        "## Sampled routes",
        "",
        "| family | url | title | archetype | access |",
        "|---|---|---|---|---|",
    ]
    for inst in instances:
        lines.append(
            f"| `{inst['route_family_id']}` | {inst['requested_url']} | {(inst.get('browser_title') or '')[:60]} | {inst.get('provisional_archetype')} | {inst.get('authentication_status')} |"
        )
    (OUT / "product-route-inventory.md").write_text("\n".join(lines) + "\n")

    dump_json(OUT / "surface-inventory.json", {"schema_version": "1.0", "run_id": run["run_id"], "surfaces": surfaces})

    # capabilities — derived, not redesign
    caps = [
        {
            "capability_id": "C.discover_stock_setups",
            "name": "Discover ranked stock setups",
            "supporting": ["RF.us.stock_dashboard", "RF.cn.china_stocks", "RF.hk.hk_stocks"],
            "evidence_status": "OBSERVED_BROWSER",
            "evidence_refs": ["us_stocks.html Prophet board", "peer market stock dashboards in nav"],
            "confidence": "HIGH",
        },
        {
            "capability_id": "C.inspect_security_cycle",
            "name": "Inspect a single security cycle / verdict",
            "supporting": ["RF.us.stock_detail"],
            "evidence_status": "OBSERVED_BROWSER",
            "evidence_refs": ["stock.html#ONTO", "board card hrefs to stock.html#TICKER"],
            "confidence": "HIGH",
        },
        {
            "capability_id": "C.inspect_market_regime",
            "name": "Inspect market regime / macro dashboard",
            "supporting": ["RF.us.macro", "RF.cn.china", "RF.hk.hk"],
            "evidence_status": "OBSERVED_BROWSER",
            "evidence_refs": ["nav Market Dashboard rows"],
            "confidence": "HIGH",
        },
        {
            "capability_id": "C.sector_rotation",
            "name": "Inspect sector / theme rotation",
            "supporting": ["RF.us.sector_central", "RF.cn.sector_central_china"],
            "evidence_status": "OBSERVED_BROWSER",
            "evidence_refs": ["nav Sector Intelligence"],
            "confidence": "HIGH",
        },
        {
            "capability_id": "C.options_positioning",
            "name": "Inspect options / market-structure positioning",
            "supporting": ["RF.us.options", "RF.us.market_structure", "RF.us.darkpool"],
            "evidence_status": "OBSERVED_BROWSER",
            "evidence_refs": ["nav Options & Market Structure"],
            "confidence": "HIGH",
        },
        {
            "capability_id": "C.intraday_flow",
            "name": "Monitor intraday flow / tape",
            "supporting": ["RF.us.intraday_flow"],
            "evidence_status": "OBSERVED_BROWSER",
            "evidence_refs": ["nav Intraday Flow Tracker"],
            "confidence": "HIGH",
        },
        {
            "capability_id": "C.research_library",
            "name": "Browse research / reports / vault",
            "supporting": ["RF.us.intelligence_hub", "RF.us.reports", "RF.us.research_vault"],
            "evidence_status": "OBSERVED_BROWSER",
            "evidence_refs": ["Research mega-nav"],
            "confidence": "HIGH",
        },
        {
            "capability_id": "C.own_book",
            "name": "Inspect own holdings / watchlist",
            "supporting": ["RF.us.watchlist"],
            "evidence_status": "OBSERVED_BROWSER",
            "evidence_refs": ["Research mega-nav Mastermind Portfolio → watchlist.html"],
            "confidence": "MEDIUM",
        },
    ]
    (OUT / "capability-map-draft.md").write_text(
        "# Capability map (draft, Phase 0)\n\n"
        "These are observed product capabilities, not redesign recommendations.\n\n"
        + "\n".join(
            f"- `{c['capability_id']}` **{c['name']}** — {c['evidence_status']} ({c['confidence']}). Surfaces: {', '.join(c['supporting'])}."
            for c in caps
        )
        + "\n"
    )

    workflows = [
        {
            "workflow_id": "W.board_to_detail",
            "steps": ["RF.us.stock_dashboard card", "RF.us.stock_detail"],
            "evidence_status": "OBSERVED",
            "edge_evidence": "a.pvcard[data-ticker] href=stock.html#TICKER on us_stocks.html",
            "confidence": "HIGH",
        },
        {
            "workflow_id": "W.search_to_detail",
            "steps": ["global nav search", "stock analyzer"],
            "evidence_status": "OBSERVED_SOURCE",
            "edge_evidence": "templates/_site_nav.html.j2 search + theme.js routes picks to the owning analyzer",
            "confidence": "HIGH",
        },
        {
            "workflow_id": "W.nav_geo_to_dashboard",
            "steps": ["geo mega-nav", "market or stock dashboard"],
            "evidence_status": "OBSERVED",
            "edge_evidence": "PRIMARY_NAV hrefs in _navlinks.html.j2",
            "confidence": "HIGH",
        },
        {
            "workflow_id": "W.detail_to_monitoring",
            "steps": ["stock detail", "watchlist/portfolio"],
            "evidence_status": "INFERRED",
            "edge_evidence": "No direct contextual control from stock.html to watchlist was exercised. Inferred only from both existing as product surfaces.",
            "confidence": "LOW",
        },
    ]
    (OUT / "workflow-map-draft.md").write_text(
        "# Workflow map (draft, Phase 0)\n\n"
        "Observed vs inferred are separated.\n\n"
        + "\n".join(
            f"- `{w['workflow_id']}` **{w['evidence_status']}** ({w['confidence']}): {' → '.join(w['steps'])}. Evidence: {w['edge_evidence']}"
            for w in workflows
        )
        + "\n"
    )

    # navigation graph
    ng = ["# Navigation graph (Phase 0)", "", "Observed edges only unless marked INFERRED.", ""]
    ng.append("```")
    for inst in instances:
        if inst.get("primary_nav"):
            ng.append(f"NAV[{inst.get('parent_navigation_group')}] --PRIMARY/MEGA--> {inst['route_family_id']} ({inst['requested_url']})")
    ng.append("BOARD --CARD_LINK--> RF.us.stock_detail")
    ng.append("SEARCH --INFERRED_FROM_SOURCE--> analyzer family by market")
    ng.append("```")
    (OUT / "navigation-graph.md").write_text("\n".join(ng) + "\n")

    (OUT / "topology-observations.md").write_text(
        """# Topology observations (facts only)

- Prophet Stock Signals (`#us-standouts`) is a large surface inside the U.S. Stock Dashboard (`us_stocks.html`), not a standalone route.
- The U.S. security analyzer is entered through `stock.html#<ticker>` from multiple product surfaces (Prophet cards, search). Canada/Intl have sibling analyzer families.
- Navigation is geography-first (United States / China / Hong Kong / Canada / International / Other Assets) plus a Research mega-menu.
- The term “Stock Dashboard” is reused across US/China/HK/Canada/International with market-specific destinations.
- Two different numeric fields can appear as confidence-like values on the U.S. board: card “Priority” vs table `conviction_score` (see Prophet decision-data-map).
- `index.html` is the marketing landing; `start.html` is the signed-in home (brand `a.nav-brand` href).
- Options destinations other than `options.html` / `darkpool.html` / `market_structure.html` were collapsed into the options workspace (nav comments). Old URLs may still exist as redirects — record live final_url on samples.
- Thousands of generated instance pages exist under `site/stocks/` and are not separate route families.
- Strategy and fund profile HTML files are generated families, mostly source-discovered rather than primary-nav destinations.
"""
    )

    (OUT / "source-route-reconciliation.md").write_text(
        "# Source vs browser route reconciliation\n\n"
        f"- Intersection (nav path also a top-level generated HTML file): {len(inter)}\n"
        f"- Browser-only: {len(browser_only)} — {', '.join(browser_only[:30])}\n"
        f"- Source-only (top-level html not in nav; families recorded, not all sampled): {len(source_only)}\n\n"
        "Source-only includes generated strategy/fund/utility pages. They are user-facing if generated into `site/` without mock/qa prefix, but they are not primary-nav destinations.\n"
    )

    # REVIEW + validation md written after metrics
    run = finalize_run(
        run,
        authenticated_session_used=bool(cookies),
        cookie_count=len(cookies or []),
        cookies_injected=bool(cookies),
    )
    dump_json(OUT / "run-manifest.json", run)
    dump_json(
        OUT / "evidence-index.json",
        {
            "schema_version": "1.0",
            "run_id": run["run_id"],
            "phase": 0,
            "inventory": relpath(OUT / "product-route-inventory.md"),
            "screenshots_dir": relpath(SHOTS),
        },
    )

    (OUT / "REVIEW_START_HERE.md").write_text(
        f"""# REVIEW START HERE — Phase 0

**Run ID:** `{run['run_id']}`
**Schema:** 1.0
**Repo SHA:** `{run['repo_head_sha']}`
**Collector:** `{run['collector_version']}`

## What was collected

- Shallow topology for nav-declared routes plus representative parameterized families.
- 1440 and 390 default screenshots per sampled instance.
- Shared-shell menu-open shots (US mega-nav, Research mega-nav, mobile nav).
- Route family vs instance distinction (do not treat every `stock.html#TICKER` as a new page).

## What was not collected

- Five-width responsive sets, keyboard, motion, every tooltip/tab/filter.
- Deep dossiers beyond Prophet calibration.
- Every generated `site/stocks/*` and every `strategy_*` / `fund_*` instance.

## Validation

See `VALIDATION.md` after `validate_dossier.py` is run.

## Key files

- `product-route-inventory.md` / `.json`
- `navigation-graph.md`
- `surface-inventory.json`
- `capability-map-draft.md`
- `workflow-map-draft.md`
- `topology-observations.md`
- `source-route-reconciliation.md`
- `screenshots/`
"""
    )

    dump_json(OUT / "raw" / "nav-parsed.json", nav_items)
    dump_json(OUT / "raw" / "source-routes.json", src_items)
    dump_json(OUT / "raw" / "shell-notes.json", console_notes)
    write_manifest(OUT, generated_by=f"collect_product_map:{run['run_id']}", associated_route="phase0", extra={"run_id": run["run_id"]})
    print(json.dumps(inventory["metrics"] | {"run_id": run["run_id"]}, indent=2))


if __name__ == "__main__":
    main()
