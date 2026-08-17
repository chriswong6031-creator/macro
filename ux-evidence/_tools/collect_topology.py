#!/usr/bin/env python3
"""Phase 0.1 topology collection. Requires a clean git tree. Reuses Phase 0 screenshots."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from artifacts import write_manifest  # noqa: E402
from paths import evidence_root, relpath, repo_root  # noqa: E402
from pw_lib import goto, launch_browser, load_aionui_cookies, new_page  # noqa: E402
from run_meta import base_run_manifest, dump_json, finalize_run  # noqa: E402
from topology_lib import (  # noqa: E402
    ORIGIN,
    classify_dom_link,
    load_registry,
    match_family_for_url,
    normalize_href,
    parse_nav_tree,
    path_from_url,
    registry_families,
    reused_screenshot_name,
    scan_generated_site,
)

OUT = evidence_root() / "00-product-map"
PRIOR = "20260816T172029Z-e5431db1"
LINK_JS = """
({navSel}) => {
  const nav = document.querySelector(navSel || 'nav.site-nav');
  const out = [];
  document.querySelectorAll('a[href]').forEach((a, i) => {
    if (i > 500) return;
    const href = a.getAttribute('href') || '';
    if (!href || href.startsWith('javascript:') || href.startsWith('mailto:')) return;
    const inNav = !!(nav && nav.contains(a));
    const cls = (a.className || '').toString();
    let kind = 'OTHER';
    if (inNav) kind = 'GLOBAL_NAV';
    else if (cls.includes('pvcard')) kind = 'CARD_LINK';
    else if (a.closest('footer')) kind = 'FOOTER';
    else if (a.closest('.nb-grid-section, .action-board, #action-board, #us-standouts')) kind = 'CARD_LINK';
    else if (a.closest('main, #result, .page, .dash')) kind = 'CONTEXTUAL';
    else kind = 'CONTEXTUAL';
    out.push({
      href, kind, inNav,
      text: ((a.innerText || a.getAttribute('aria-label') || '').replace(/\\s+/g,' ').trim()).slice(0,80),
      cls: cls.slice(0,60)
    });
  });
  const headings = [];
  document.querySelectorAll('h1,h2,#us-standouts h2,.panel > h2, .sv-sec-h').forEach((h,i) => {
    if (i>30) return;
    headings.push({tag:h.tagName.toLowerCase(), id:h.id||null, text:(h.innerText||'').replace(/\\s+/g,' ').trim().slice(0,120)});
  });
  const panels = [];
  document.querySelectorAll('[id].panel, #us-standouts, #result, #sv-decision, #tvbox, details.sv-deep, details.sv-group, #regime-radar, #action-board, #stocks-header').forEach((el,i) => {
    if (i>20) return;
    const r = el.getBoundingClientRect();
    panels.push({
      id: el.id || null,
      tag: el.tagName.toLowerCase(),
      cls: (el.className||'').toString().slice(0,50),
      text: ((el.innerText||'').replace(/\\s+/g,' ').trim()).slice(0,100),
      h: Math.round(r.height),
      visible: r.height > 8 && r.width > 8
    });
  });
  return {
    title: document.title,
    heading: (document.querySelector('h1')||{}).innerText || null,
    lock_cta: !!document.querySelector('.lock-cta, .regwall, [data-gated]'),
    user_attr: document.documentElement.getAttribute('data-user'),
    links: out,
    headings,
    panels
  };
}
"""


def git_dirty() -> bool:
    out = subprocess.check_output(["git", "status", "--porcelain"], cwd=str(repo_root()), text=True)
    return bool(out.strip())


def route_id_for(url: str) -> str:
    p = path_from_url(url)
    return "R." + p.replace("/", ".").replace(".html", "").replace("#", ".")


def surface_id(family: str, slug: str) -> str:
    return "SUR." + family.replace("RF.", "") + "." + re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_")


def derive_capability(surface: dict) -> dict | None:
    label = (surface.get("label") or "").lower()
    sid = surface["surface_id"]
    text = ((surface.get("headings_text") or "") + " " + label).lower()
    rules = [
        ("prophet", "C.rank_actionable_stock_setups", "Rank actionable stock setups"),
        ("cycle & timing", "C.inspect_entry_timing", "Inspect entry timing"),
        ("sv-decision", "C.inspect_stock_verdict", "Inspect stock verdict / action"),
        ("winner", "C.inspect_winner_deterioration", "Inspect winner deterioration"),
        ("stage", "C.inspect_stock_cycle_stage", "Inspect stock cycle stage"),
        ("regime", "C.inspect_macro_regime", "Inspect macro regime"),
        ("what to do now", "C.inspect_macro_playbook", "Inspect current macro playbook"),
        ("intraday", "C.monitor_intraday_tape", "Monitor intraday tape"),
        ("dark pool", "C.inspect_darkpool", "Inspect dark-pool activity"),
        ("options", "C.inspect_options_positioning", "Inspect options positioning"),
        ("gex", "C.inspect_gex_structure", "Inspect GEX / market structure"),
        ("market structure", "C.inspect_gex_structure", "Inspect GEX / market structure"),
        ("sector", "C.inspect_sector_rotation", "Inspect sector rotation"),
        ("theme", "C.inspect_thematic_baskets", "Inspect thematic baskets"),
        ("confluence", "C.inspect_subsector_confluence", "Inspect subsector confluence"),
        ("flow velocity", "C.inspect_flow_acceleration", "Inspect flow acceleration"),
        ("smart money", "C.inspect_ownership_smart_money", "Inspect ownership / smart money"),
        ("etf", "C.inspect_etf_positioning", "Inspect ETF / fund positioning"),
        ("fund", "C.inspect_etf_positioning", "Inspect ETF / fund positioning"),
        ("policy", "C.inspect_policy_changes", "Inspect policy changes"),
        ("radar", "C.inspect_market_divergences", "Inspect market divergences"),
        ("special situation", "C.inspect_event_driven", "Inspect event-driven situations"),
        ("biocatalyst", "C.inspect_biocatalyst_events", "Inspect biopharma catalysts"),
        ("earnings", "C.inspect_earnings_records", "Inspect earnings records"),
        ("forensic", "C.inspect_filing_changes", "Inspect filing / accounting changes"),
        ("seasonality", "C.inspect_seasonality", "Inspect seasonality"),
        ("market memory", "C.inspect_market_memory", "Inspect market memory"),
        ("country cycle", "C.inspect_country_cycles", "Inspect country cycles"),
        ("watchlist", "C.inspect_portfolio_watchlist", "Inspect portfolio / watchlist"),
        ("vault", "C.browse_institutional_research", "Browse institutional research"),
        ("report", "C.browse_research_reports", "Browse research reports"),
        ("neural", "C.inspect_signal_votes", "Inspect how signals vote"),
        ("foresight", "C.inspect_themes_before_price", "Inspect themes before they are priced"),
        ("alert", "C.monitor_ranked_alerts", "Monitor ranked alerts"),
        ("news", "C.browse_news_catalysts", "Browse news / catalysts"),
        ("heatmap", "C.inspect_market_heatmap", "Inspect market heatmap"),
        ("leader", "C.inspect_leader_lifecycle", "Inspect leader lifecycle"),
        ("calibration", "C.inspect_state_trust", "Inspect historical state trust"),
        ("momentum", "C.inspect_multi_timeframe_momentum", "Inspect multi-timeframe momentum"),
        ("chart", "C.inspect_price_chart", "Inspect price chart"),
        ("identity", "C.identify_security", "Identify a security"),
        ("shell", "C.navigate_product", "Navigate the product shell"),
    ]
    for needle, cid, name in rules:
        if needle in text or needle in sid.lower() or needle in (surface.get("selector_hint") or "").lower():
            return {
                "capability_id": cid,
                "neutral_name": name,
                "concise_observed_description": f"Observed on surface {surface['label']}",
                "supporting_surface_ids": [sid],
                "supporting_route_family_ids": [surface["route_family_id"]],
                "evidence_status": surface.get("evidence_status") or "OBSERVED_BROWSER",
                "evidence_refs": [{"ref_type": "surface", "ref": sid, "note": surface.get("label")}],
                "confidence": "MEDIUM",
                "synonyms_labels_observed": [surface.get("label")],
                "market_contexts": surface.get("market_contexts") or [],
            }
    return None


def md_table(headers, rows) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(lines)


def main():
    if git_dirty():
        raise SystemExit("REFUSING canonical collection: git status --porcelain is not empty")
    reg = load_registry()
    families = registry_families(reg)
    source_rows = scan_generated_site(reg)
    nav_src = parse_nav_tree()

    run = base_run_manifest(schema_version="1.0")
    run["topology_schema_version"] = "1.1-candidate"
    run["canonical"] = True
    run["supersedes_run_id"] = PRIOR
    run["working_tree_dirty"] = False
    if git_dirty():
        raise SystemExit("became dirty before collection")

    cookies = load_aionui_cookies()
    run["authenticated_session_used"] = bool(cookies)
    run["cookie_count"] = len(cookies or [])
    run["cookies_injected"] = bool(cookies)

    # attach source counts to generation families
    by_fam_src = Counter(r["family"] for r in source_rows)
    for fid, n in by_fam_src.items():
        if fid in families:
            families[fid]["instance_count_source"] = n
        else:
            sample = next(x for x in source_rows if x["family"] == fid)
            families[fid] = {
                "route_family_id": fid,
                "canonical_pattern": sample["rel"],
                "route_class": sample["route_class"],
                "market_contexts": [],
                "product_domain": ["unknown"],
                "template_source_family": None,
                "instance_generation_rule": sample.get("reason"),
                "representative_instances": [],
                "canonical_target": sample.get("canonical_target"),
                "review_tier": "D",
                "discovery_sources": ["GENERATED_SITE"],
                "evidence_status": "OBSERVED_SOURCE",
                "evidence_refs": [{"ref_type": "source_file", "ref": sample["source_path"]}],
                "instance_count_source": n,
            }

    # representative instances: live families + param samples + one per generation rule
    sample_urls = []
    seen_u = set()

    def add_sample(url, role, sources):
        nu = normalize_href(url) if not url.startswith("http") else url
        if nu in seen_u:
            return
        seen_u.add(nu)
        sample_urls.append({"url": nu, "role": role, "sources": sources})

    for live in reg.get("live_families") or []:
        if live.get("path"):
            add_sample(live["path"], "canonical_sample", ["SOURCE_REGISTRY"])
        if live.get("external"):
            add_sample(live["external"], "external", ["NAV_TEMPLATE_SOURCE"])
    for p in reg.get("parameterized") or []:
        add_sample(p["sample"], "family_sample", ["SOURCE_REGISTRY", "MANUAL_SEED"])
    for rule in reg.get("generation_rules") or []:
        if rule.get("sample"):
            add_sample(rule["sample"], "family_sample", ["GENERATED_SITE"])
    for stub in reg.get("redirect_stubs") or []:
        add_sample(stub["path"], "stub", ["SOURCE_REGISTRY"])
    for twin in reg.get("seo_twins") or []:
        add_sample(twin["path"], "seo_twin", ["SOURCE_REGISTRY"])
    add_sample("stock.html#ONTO", "calibration_sample", ["MANUAL_SEED"])
    add_sample("sector_central.html#confluence", "rail_view", ["NAV_TEMPLATE_SOURCE"])

    # reuse prior screenshots / headings
    prior_inv = OUT / "prior-runs" / PRIOR / "product-route-inventory.json"
    prior_by_url = {}
    if prior_inv.exists():
        prev = json.loads(prior_inv.read_text())
        for inst in prev.get("route_instances") or []:
            prior_by_url[inst.get("requested_url")] = inst

    from playwright.sync_api import sync_playwright

    live_nav_edges = []
    page_facts = {}
    anon_facts = {}
    recaptured = []
    reused = []
    failures = []

    tier_a_urls = []
    for s in sample_urls:
        fid, _ = match_family_for_url(s["url"], families, reg)
        fam = families.get(fid) or {}
        if fam.get("review_tier") in {"A", "B"} and fam.get("route_class") == "LIVE_PRODUCT":
            tier_a_urls.append(s["url"])

    with sync_playwright() as p:
        browser = launch_browser(p)
        run["browser_name"] = "chrome"
        run["browser_version"] = getattr(browser, "version", "unknown")

        # live nav discovery
        ctx, page = new_page(browser, 1440, 1000, cookies or None)
        try:
            goto(page, ORIGIN + "/start.html", wait_ms=1000)
            try:
                page.locator("a.nav-link", has_text="United States").first.hover(timeout=4000)
                page.wait_for_timeout(250)
                page.locator("a.nav-link", has_text="Research").first.hover(timeout=4000)
                page.wait_for_timeout(250)
            except Exception as e:
                failures.append({"where": "desktop_nav_hover", "error": str(e).splitlines()[0][:160]})
            facts = page.evaluate(LINK_JS, {"navSel": "nav.site-nav"})
            for ln in facts.get("links") or []:
                if ln.get("kind") == "GLOBAL_NAV":
                    live_nav_edges.append(
                        {
                            "destination": ln["href"],
                            "nav_label": ln.get("text") or ln["href"],
                            "edge_type": "PRIMARY_NAV",
                            "evidence_status": "OBSERVED_BROWSER",
                            "channel": "desktop",
                            "discovery_source": "LIVE_BROWSER_DOM",
                            "nav_path": ["(live DOM)"],
                        }
                    )
            page_facts[ORIGIN + "/start.html"] = facts
        except Exception as e:
            failures.append({"where": "start_desktop", "error": str(e).splitlines()[0][:160]})
        ctx.close()

        ctx, page = new_page(browser, 390, 844, cookies or None)
        try:
            goto(page, ORIGIN + "/start.html", wait_ms=800)
            tog = page.locator(".nav-toggle, button[aria-label*='navigation' i]")
            if tog.count():
                tog.first.click(timeout=4000)
                page.wait_for_timeout(250)
            facts = page.evaluate(LINK_JS, {"navSel": "nav.site-nav"})
            page_facts["start.html#mobile"] = facts
        except Exception as e:
            failures.append({"where": "start_mobile", "error": str(e).splitlines()[0][:160]})
        ctx.close()

        # contextual links on tier A/B (no screenshots)
        for url in tier_a_urls:
            ctx, page = new_page(browser, 1440, 1000, cookies or None)
            try:
                goto(page, url, wait_ms=700)
                page_facts[url] = page.evaluate(LINK_JS, {"navSel": "nav.site-nav"})
            except Exception as e:
                failures.append({"where": url, "error": str(e).splitlines()[0][:160]})
            ctx.close()

        # anonymous probes
        for url in tier_a_urls:
            ctx, page = new_page(browser, 1440, 1000, None)
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(600)
                facts = page.evaluate(LINK_JS, {"navSel": "nav.site-nav"})
                anon_facts[url] = {
                    "http_status": resp.status if resp else 0,
                    "lock_cta": facts.get("lock_cta"),
                    "title": facts.get("title"),
                    "heading": facts.get("heading"),
                    "meaningful": bool((facts.get("heading") or facts.get("title")) and not facts.get("lock_cta")),
                }
            except Exception as e:
                anon_facts[url] = {"http_status": 0, "error": str(e).splitlines()[0][:160], "meaningful": False}
                failures.append({"where": "anon:" + url, "error": str(e).splitlines()[0][:160]})
            ctx.close()
        browser.close()

    # build instances
    instances = []
    for s in sample_urls:
        url = s["url"]
        fid, params = match_family_for_url(url, families, reg)
        fam = families.get(fid) or {}
        sources = list(s["sources"])
        if any(path_from_url(url).split("#")[0] == path_from_url(normalize_href(e["destination"])).split("#")[0] for e in nav_src):
            if "NAV_TEMPLATE_SOURCE" not in sources:
                sources.append("NAV_TEMPLATE_SOURCE")
        if url in page_facts:
            sources.append("LIVE_BROWSER_DOM")
        # prior screenshot reuse
        shots = {}
        for vp, path in reused_screenshot_name(url).items():
            shots[vp] = relpath(path)
            reused.append(str(path.name))
        prior = prior_by_url.get(url) or {}
        obs = []
        if cookies:
            obs.append(
                {
                    "session_kind": "authenticated_session",
                    "access_status": "ACCESSIBLE_CURRENT_SESSION",
                    "evidence_status": "OBSERVED_BROWSER" if url in page_facts else "UNKNOWN",
                    "note": "current-session cookies imported in memory only",
                }
            )
        if url in anon_facts:
            af = anon_facts[url]
            if af.get("error") or (af.get("http_status") or 0) >= 400:
                astatus = "BROKEN" if (af.get("http_status") or 0) >= 400 or af.get("http_status") == 0 else "UNKNOWN"
            elif af.get("lock_cta"):
                astatus = "SUBSCRIPTION_GATED"
            elif af.get("meaningful"):
                astatus = "ANONYMOUS_ACCESSIBLE"
            else:
                astatus = "UNKNOWN"
            obs.append(
                {
                    "session_kind": "anonymous_session",
                    "access_status": astatus,
                    "http_status": af.get("http_status"),
                    "lock_cta": af.get("lock_cta"),
                    "meaningful_content": af.get("meaningful"),
                    "evidence_status": "OBSERVED_BROWSER",
                }
            )
        # combined access
        anon = next((o for o in obs if o["session_kind"] == "anonymous_session"), None)
        if anon and anon["access_status"] == "ANONYMOUS_ACCESSIBLE":
            access = "ANONYMOUS_ACCESSIBLE"
        elif anon and anon["access_status"] in {"AUTH_REQUIRED", "SUBSCRIPTION_GATED", "BROKEN"}:
            access = anon["access_status"]
        elif any(o["session_kind"] == "authenticated_session" for o in obs):
            access = "ACCESSIBLE_CURRENT_SESSION"
        else:
            access = "UNKNOWN"
        inst = {
            "route_id": route_id_for(url),
            "route_family_id": fid,
            "requested_url": url,
            "normalized_url": url,
            "final_url": (prior.get("final_url") if prior else None) or url,
            "route_class": fam.get("route_class") or "UNKNOWN",
            "route_parameters": {k: v for k, v in params.items() if v},
            "route_instance_role": s["role"],
            "canonical_target": fam.get("canonical_target"),
            "discovery_sources": sorted(set(sources)),
            "access_status": access,
            "access_observations": obs,
            "screenshot_refs": shots,
            "evidence_status": "OBSERVED_BROWSER" if url in page_facts else "OBSERVED_SOURCE",
            "browser_title": (page_facts.get(url) or {}).get("title") or prior.get("browser_title"),
            "primary_visible_heading": (page_facts.get(url) or {}).get("heading") or prior.get("primary_visible_heading"),
            "reused_phase0_screenshot": bool(shots),
        }
        instances.append(inst)
        families.setdefault(fid, fam)
        families[fid].setdefault("representative_instances", [])
        if inst["route_id"] not in families[fid]["representative_instances"]:
            families[fid]["representative_instances"].append(inst["route_id"])
        for src in sources:
            if src not in (families[fid].get("discovery_sources") or []):
                families[fid].setdefault("discovery_sources", []).append(src)

    inst_by_id = {i["route_id"]: i for i in instances}

    # surfaces
    surfaces = [
        {
            "surface_id": "SUR.shell.global",
            "route_family_id": "RF.home.signed_in",
            "representative_route_id": "R.start",
            "label": "Global shell",
            "page_order": -1,
            "evidence_status": "OBSERVED_BOTH",
            "confidence": "HIGH",
            "visible": True,
            "is_global_shell": True,
            "primary_apparent_job": "Navigate markets, research, search, theme/language, Terminal",
            "major_controls": ["brand", "geo nav", "research mega", "search", "Terminal", "theme", "language"],
            "source_hints": ["templates/_site_nav.html.j2", "templates/_navlinks.html.j2"],
        }
    ]
    # decompose from live panels + prior coarse sections
    for inst in instances:
        fam = families.get(inst["route_family_id"]) or {}
        if fam.get("review_tier") not in {"A", "B"}:
            continue
        if fam.get("route_class") != "LIVE_PRODUCT":
            continue
        facts = page_facts.get(inst["requested_url"]) or {}
        prior = prior_by_url.get(inst["requested_url"]) or {}
        panels = facts.get("panels") or prior.get("major_sections") or []
        order = 0
        used = set()
        for pan in panels:
            pid = pan.get("id") or (pan.get("text") or "")[:24] or pan.get("cls")
            if not pid or pid in used:
                continue
            if pid in {"result"}:  # too large; split via children already listed
                continue
            used.add(pid)
            slug = pid if isinstance(pid, str) else "panel"
            sid = surface_id(inst["route_family_id"], slug)
            h = pan.get("h") or 0
            surfaces.append(
                {
                    "surface_id": sid,
                    "route_family_id": inst["route_family_id"],
                    "representative_route_id": inst["route_id"],
                    "label": (pan.get("text") or slug)[:80],
                    "page_order": order,
                    "evidence_status": "OBSERVED_BROWSER" if facts else "OBSERVED_SOURCE",
                    "confidence": "MEDIUM",
                    "visible": bool(pan.get("visible") if "visible" in pan else h > 8),
                    "is_global_shell": False,
                    "page_box": {"h": h} if h else None,
                    "primary_apparent_job": (pan.get("text") or "")[:120],
                    "selector_hint": ("#" + pid) if pan.get("id") else pan.get("cls"),
                    "headings_text": pan.get("text"),
                    "source_hints": [inst.get("requested_url")],
                }
            )
            order += 1
            if order >= 10:
                break
        if order == 0:
            surfaces.append(
                {
                    "surface_id": surface_id(inst["route_family_id"], "primary"),
                    "route_family_id": inst["route_family_id"],
                    "representative_route_id": inst["route_id"],
                    "label": inst.get("primary_visible_heading") or inst["route_id"],
                    "page_order": 0,
                    "evidence_status": inst.get("evidence_status") or "UNKNOWN",
                    "confidence": "LOW",
                    "visible": True,
                    "is_global_shell": False,
                    "primary_apparent_job": inst.get("browser_title"),
                    "source_hints": [inst["requested_url"]],
                }
            )

    # unique surface ids
    seen_s = set()
    uniq_s = []
    for s in surfaces:
        if s["surface_id"] in seen_s:
            s = dict(s)
            s["surface_id"] += "_" + (s.get("representative_route_id") or "x")
        seen_s.add(s["surface_id"])
        uniq_s.append(s)
    surfaces = uniq_s
    surf_by_id = {s["surface_id"]: s for s in surfaces}

    # capabilities
    caps = {}
    for s in surfaces:
        if s.get("is_global_shell"):
            c = derive_capability({**s, "label": "shell navigation"})
        else:
            c = derive_capability(s)
        if not c:
            continue
        if c["capability_id"] in caps:
            existing = caps[c["capability_id"]]
            if s["surface_id"] not in existing["supporting_surface_ids"]:
                existing["supporting_surface_ids"].append(s["surface_id"])
            if s["route_family_id"] not in existing["supporting_route_family_ids"]:
                existing["supporting_route_family_ids"].append(s["route_family_id"])
            existing.setdefault("possible_overlap", [])
        else:
            caps[c["capability_id"]] = c
    cap_list = list(caps.values())

    # workflow edges from contextual links
    wf_edges = []
    for url, facts in page_facts.items():
        if url.endswith("#mobile"):
            continue
        src_fid, _ = match_family_for_url(url, families, reg)
        for ln in facts.get("links") or []:
            kind = ln.get("kind")
            if kind in {"GLOBAL_NAV", "FOOTER", "EXTERNAL"}:
                continue
            dest = normalize_href(ln["href"]) if not str(ln["href"]).startswith("http") else ln["href"]
            if dest.startswith("/") or dest.endswith(".html") or "#" in dest or "mastermind" in dest:
                dst_fid, _ = match_family_for_url(dest if dest.startswith("http") else normalize_href(dest), families, reg)
            else:
                continue
            if dst_fid == src_fid and kind != "CARD_LINK":
                continue
            wf_edges.append(
                {
                    "edge_id": f"WE.{len(wf_edges)+1:04d}",
                    "from_ref": src_fid,
                    "to_ref": dst_fid,
                    "edge_type": "CARD_LINK" if kind == "CARD_LINK" else "CTA" if kind == "PRIMARY_CTA" else "DETAIL_LINK" if "stock.html" in dest else "CONTEXTUAL",
                    "link_class": kind if kind in {"CONTEXTUAL", "CARD_LINK", "PRIMARY_CTA", "LOCAL_NAV", "SEARCH"} else "CONTEXTUAL",
                    "evidence_status": "OBSERVED_BROWSER",
                    "href": dest,
                    "anchor_text": ln.get("text"),
                    "from_url": url,
                }
            )
    # cluster a few observed workflows from card links
    workflows = []
    if any(e["edge_type"] == "CARD_LINK" and "stock" in (e.get("href") or "") for e in wf_edges):
        workflows.append(
            {
                "workflow_id": "W.board_card_to_detail",
                "name": "Board card to security analyzer",
                "ordered_steps": [
                    {"route_family_id": "RF.equities.dashboard.us", "surface_id": next((s["surface_id"] for s in surfaces if "standouts" in s["surface_id"] or "prophet" in (s.get("label") or "").lower()), "SUR.equities.dashboard.us.primary")},
                    {"route_family_id": "RF.equities.detail.us"},
                ],
                "evidence_status": "OBSERVED_BROWSER",
                "confidence": "HIGH",
                "evidence_refs": ["a.pvcard href=stock.html#TICKER"],
                "observed_entry_points": ["RF.equities.dashboard.us"],
                "observed_exit_points": ["RF.equities.detail.us"],
            }
        )
    workflows.append(
        {
            "workflow_id": "W.search_to_analyzer",
            "name": "Global search to owning analyzer",
            "ordered_steps": [{"surface_id": "SUR.shell.global"}, {"route_family_id": "RF.equities.detail.us"}],
            "evidence_status": "OBSERVED_SOURCE",
            "confidence": "HIGH",
            "evidence_refs": ["templates/_site_nav.html.j2 search + theme.js routes picks"],
        }
    )
    workflows.append(
        {
            "workflow_id": "W.detail_to_watchlist",
            "name": "Security analyzer to watchlist / portfolio",
            "ordered_steps": [{"route_family_id": "RF.equities.detail.us"}, {"route_family_id": "RF.monitoring.watchlist"}],
            "evidence_status": "INFERRED",
            "confidence": "LOW",
            "inferred": True,
            "evidence_refs": ["No contextual control from stock.html to watchlist was observed in Phase 0.1."],
        }
    )

    # navigation tree from source + live
    nav_edges = []
    for i, e in enumerate(nav_src):
        nav_edges.append(
            {
                "edge_id": f"NAV.src.{i+1:03d}",
                "nav_path": e["nav_path"],
                "nav_label": e["nav_label"],
                "destination": e["destination"],
                "edge_type": e["edge_type"],
                "evidence_status": "OBSERVED_SOURCE",
                "channel": "desktop",
                "link_class": "GLOBAL_NAV",
            }
        )
    for i, e in enumerate(live_nav_edges):
        nav_edges.append(
            {
                "edge_id": f"NAV.live.{i+1:03d}",
                **{k: e[k] for k in ("nav_path", "nav_label", "destination", "edge_type", "evidence_status", "channel") if k in e},
                "link_class": "GLOBAL_NAV",
            }
        )

    fam_list = sorted(families.values(), key=lambda f: f["route_family_id"])
    class_counts = Counter(f.get("route_class") for f in fam_list)
    metrics = {
        "route_families": len(fam_list),
        "route_instances": len(instances),
        "surfaces": len(surfaces),
        "capabilities": len(cap_list),
        "workflow_edges": len(wf_edges),
        "workflows": len(workflows),
        **{f"class_{k}": v for k, v in class_counts.items()},
        "source_html_total": len(source_rows),
        "source_html_top_level": sum(1 for r in source_rows if "/" not in r["rel"]),
        "source_html_nested": sum(1 for r in source_rows if "/" in r["rel"]),
        "anonymous_probes": len(anon_facts),
        "access_unknown": sum(1 for i in instances if i.get("access_status") == "UNKNOWN"),
    }

    run = finalize_run(run, failures=failures, reused_screenshots=len(reused), recaptured_screenshots=len(recaptured))
    dump_json(OUT / "run-manifest.json", run)
    dump_json(OUT / "route-family-registry.json", {"schema_version": "1.1-candidate", "supersedes_run_id": PRIOR, "route_families": fam_list, "metrics": metrics})
    dump_json(OUT / "route-instance-inventory.json", {"schema_version": "1.1-candidate", "supersedes_run_id": PRIOR, "route_instances": instances, "metrics": metrics})
    dump_json(OUT / "surface-inventory.json", {"schema_version": "1.1-candidate", "supersedes_run_id": PRIOR, "surfaces": surfaces})
    dump_json(OUT / "capability-inventory.json", {"schema_version": "1.1-candidate", "capabilities": cap_list})
    dump_json(OUT / "workflow-edges.json", {"schema_version": "1.1-candidate", "edges": wf_edges, "workflows": workflows})
    dump_json(OUT / "navigation-tree.json", {"schema_version": "1.1-candidate", "edges": nav_edges})
    dump_json(OUT / "navigation-graph.json", {"schema_version": "1.1-candidate", "edges": nav_edges, "workflow_edges": wf_edges})
    dump_json(OUT / "raw" / "source-scan.json", {"count": len(source_rows), "by_class": dict(Counter(r["route_class"] for r in source_rows))})
    dump_json(OUT / "raw" / "failures.json", failures)
    dump_json(OUT / "raw" / "anon-probes.json", {k: {kk: vv for kk, vv in v.items() if kk != "error" or True} for k, v in anon_facts.items()})

    # terminology
    terms = [
        {"label": "Prophet", "surfaces": [s["surface_id"] for s in surfaces if "prophet" in (s.get("label") or "").lower() or "standouts" in s["surface_id"]], "possible_synonym": ["Stock Dashboard", "setups"], "possible_conflict": None},
        {"label": "Priority", "surfaces": [], "source_term": "cx.edge / us_board_rank", "possible_conflict": "conviction_score"},
        {"label": "conviction_score", "surfaces": [], "source_term": "#us-stocktable-data", "possible_conflict": "Priority"},
        {"label": "Stock Dashboard", "surfaces": [s["surface_id"] for s in surfaces if "dashboard" in s["route_family_id"]], "possible_synonym": ["Prophet"], "note": "Same nav label in US/China/HK/Canada/International with different destinations"},
        {"label": "Cycle", "surfaces": [s["surface_id"] for s in surfaces if "cycle" in (s.get("label") or "").lower()], "possible_synonym": ["Stage", "timing"]},
        {"label": "Verdict / Action", "surfaces": [s["surface_id"] for s in surfaces if "decision" in s["surface_id"] or "verdict" in (s.get("label") or "").lower()], "possible_conflict": "board verb vs detail WAIT"},
        {"label": "Smart Money", "surfaces": [s["surface_id"] for s in surfaces if "smart" in s["route_family_id"]], "possible_synonym": ["Ownership", "13F"]},
        {"label": "Flow", "surfaces": [s["surface_id"] for s in surfaces if "flow" in s["route_family_id"]], "possible_synonym": ["tape", "dark pool"]},
        {"label": "Theme / Narrative / Sector", "surfaces": [s["surface_id"] for s in surfaces if "theme" in s["route_family_id"] or "sector" in s["route_family_id"]], "possible_overlap": True},
        {"label": "Regime", "surfaces": [s["surface_id"] for s in surfaces if "regime" in (s.get("label") or "").lower() or "macro" in s["route_family_id"]], "possible_synonym": ["What To Do Now"]},
    ]
    dump_json(OUT / "terminology-map.json", {"terms": terms})

    # markdown renderings
    (OUT / "route-family-registry.md").write_text(
        "# Route family registry (topology 1.1-candidate)\n\n"
        + f"Supersedes `{PRIOR}`.\n\n"
        + md_table(
            ["family", "class", "pattern", "tier", "source n", "markets"],
            [
                [
                    f"`{f['route_family_id']}`",
                    f.get("route_class"),
                    f"`{f.get('canonical_pattern')}`",
                    f.get("review_tier"),
                    f.get("instance_count_source") or "",
                    ",".join(f.get("market_contexts") or []),
                ]
                for f in fam_list
            ],
        )
        + "\n"
    )
    (OUT / "surface-inventory.md").write_text(
        "# Surfaces\n\n"
        + md_table(
            ["surface", "family", "label", "shell?"],
            [[f"`{s['surface_id']}`", f"`{s['route_family_id']}`", (s.get("label") or "")[:60].replace("|", "/"), s.get("is_global_shell")] for s in surfaces],
        )
        + "\n"
    )
    (OUT / "capability-map-draft.md").write_text(
        "# Capability map (draft, granular)\n\nNot a redesign. Sol may merge later.\n\n"
        + "\n".join(
            f"- `{c['capability_id']}` **{c['neutral_name']}** — {c['evidence_status']} ({c.get('confidence')}). Surfaces: {', '.join('`'+x+'`' for x in c['supporting_surface_ids'])}."
            for c in cap_list
        )
        + "\n"
    )
    (OUT / "workflow-map-draft.md").write_text(
        "# Workflow map\n\nEdges come from contextual/card/CTA links, not the global menu.\n\n"
        + f"Atomic edges: {len(wf_edges)}\n\n"
        + "\n".join(
            f"- `{w['workflow_id']}` **{w['evidence_status']}** ({w.get('confidence')}): {w['name']}. {'; '.join(w.get('evidence_refs') or [])}"
            for w in workflows
        )
        + "\n"
    )
    (OUT / "navigation-tree.md").write_text(
        "# Navigation tree\n\nSource template hierarchy (desktop). Live DOM links are recorded separately in JSON.\n\n"
        + "\n".join(f"- `{' / '.join(e['nav_path'])}` → **{e['nav_label']}** (`{e['destination']}`)" for e in nav_src)
        + "\n"
    )
    (OUT / "navigation-graph.md").write_text(
        "# Navigation graph\n\nGlobal nav edges are GLOBAL_NAV. Workflow edges are separate.\n\n"
        f"- source nav edges: {len(nav_src)}\n- live DOM nav hrefs: {len(live_nav_edges)}\n- contextual workflow edges: {len(wf_edges)}\n"
    )
    (OUT / "terminology-map.md").write_text(
        "# Terminology map\n\nDo not collapse these.\n\n"
        + "\n".join(f"- **{t['label']}** — conflict/synonym: {t.get('possible_conflict') or t.get('possible_synonym')}" for t in terms)
        + "\n"
    )
    src_class = Counter(r["route_class"] for r in source_rows)
    (OUT / "source-route-reconciliation.md").write_text(
        "# Source route reconciliation\n\n"
        f"- total HTML discovered: {len(source_rows)}\n"
        f"- top-level: {metrics['source_html_top_level']}\n"
        f"- nested: {metrics['source_html_nested']}\n"
        + "".join(f"- {k}: {v}\n" for k, v in src_class.most_common())
        + "\nGeneration families (examples):\n\n"
        + "\n".join(
            f"- `{f['route_family_id']}` {f.get('route_class')} n={f.get('instance_count_source')} pattern `{f.get('canonical_pattern')}`"
            for f in fam_list
            if f.get("route_class") == "GENERATED_INSTANCE"
        )
        + "\n"
    )
    (OUT / "consolidation-history-observations.md").write_text(
        """# Consolidation history (observed, not endorsed)

These are source/nav comments describing past implementation decisions.

- Sector Intelligence consolidation (US): baskets + subsector rotation merged into `sector_central.html`; confluence remains a rail (`#confluence`). `subsectors.html` kept as an SEO twin.
- China Sector Intelligence: same pattern on `sector_central_china.html`; `subsectors_china.html` is an SEO twin.
- Options “One Door”: `gex.html`, `flow_desk.html`, `options_screener.html`, `flow_leaders.html` are redirect stubs into `options.html` modes.
- Intraday Flow Tracker was relocated out of the options flyout into the US group (`intraday_flow.html`).
- Brand home: signed-in destination is `start.html`; `index.html` is the marketing landing.
- Bitcoin Vector allocation page `vector_allocation.html` redirects to `crypto.html#allocation`.
- `btc_strategy.html` redirects to `vector.html#strategy-track-record`.

No judgment is made about whether these consolidations should remain.
"""
    )
    (OUT / "topology-observations.md").write_text(
        """# Topology observations (facts only)

- Prophet Stock Signals (`#us-standouts`) is a large surface inside `us_stocks.html`, not its own route.
- `stock.html#<ticker>`, `canada_stock.html#<ticker>`, and `intl_stock.html#<ticker>` are three families, not one U.S. pattern.
- `index.html`, `stocks/earnings/index.html`, and `bot.mastermind-x.com` are different families.
- China → Research → Market Mechanics is a real nav path; it is not a top-level Research item.
- Global navigation can reach most live routes; that is not a product workflow.
- Board “Priority” and table `conviction_score` are different producer fields (see Prophet decision-data-map).
- Thousands of `site/stocks/*.html` files are a generated instance family, not thousands of live product routes.
- Several former options/sector URLs are redirect stubs with meta-refresh + `location.replace`.
"""
    )
    (OUT / "REVIEW_START_HERE.md").write_text(
        f"""# REVIEW START HERE — Phase 0.1 topology

**Topology schema:** 1.1-candidate (not frozen)
**Page evidence schema:** 1.0 (unchanged)
**Run ID:** `{run['run_id']}`
**Repo SHA:** `{run['repo_head_sha']}`
**working_tree_dirty:** {run['working_tree_dirty']}
**Supersedes:** `{PRIOR}` (retained under `prior-runs/`)

## Machine status

See `VALIDATION.md` after the topology validator runs.

## Counts

Use the JSON metrics; do not treat families and instances as the same number.

## Index

- `route-family-registry.md`
- `navigation-tree.md`
- `surface-inventory.md`
- `capability-map-draft.md`
- `workflow-map-draft.md`
- `terminology-map.md`
- `consolidation-history-observations.md`
- `source-route-reconciliation.md`
- `screenshots/` (reused from Phase 0 unless noted)

No product decisions live here.
"""
    )
    (OUT / "VALIDATION.md").write_text(
        f"""# Phase 0.1 validation

Run: `python3 ux-evidence/_tools/validate_topology.py`

| Metric | Value |
|---|---|
| topology schema | 1.1-candidate |
| run ID | `{run['run_id']}` |
| repo SHA | `{run['repo_head_sha']}` |
| dirty | {run['working_tree_dirty']} |
| families | {metrics['route_families']} |
| sampled instances | {metrics['route_instances']} |
| surfaces | {metrics['surfaces']} |
| capabilities | {metrics['capabilities']} |
| workflow edges | {metrics['workflow_edges']} |
| workflows | {metrics['workflows']} |
| anonymous probes | {metrics['anonymous_probes']} |
| access unknown | {metrics['access_unknown']} |
"""
        + "".join(f"| class {k} | {v} |\n" for k, v in class_counts.most_common())
    )

    # compatibility alias
    dump_json(
        OUT / "product-route-inventory.json",
        {
            "schema_version": "1.1-candidate",
            "note": "Compatibility projection. Canonical families/instances are route-family-registry.json and route-instance-inventory.json.",
            "supersedes_run_id": PRIOR,
            "route_families": fam_list,
            "route_instances": instances,
            "metrics": metrics,
        },
    )

    write_manifest(OUT, generated_by=f"collect_topology:{run['run_id']}", associated_route="phase0.1", extra={"run_id": run["run_id"]})
    dump_json(evidence_root() / "run-manifest.json", {**run, "phase": "0.1"})
    print(json.dumps({"run_id": run["run_id"], "metrics": metrics, "failures": len(failures), "reused": len(reused)}, indent=2))


if __name__ == "__main__":
    main()
