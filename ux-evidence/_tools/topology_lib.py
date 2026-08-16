#!/usr/bin/env python3
"""Phase 0.1 topology helpers: registry matching, source scan, nav hierarchy."""
from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from paths import evidence_root, repo_root

ORIGIN = "https://www.mastermind-x.com"
ROUTE_CLASSES = {
    "LIVE_PRODUCT",
    "REDIRECT_STUB",
    "SEO_TWIN",
    "GENERATED_INSTANCE",
    "UTILITY",
    "LEGACY_ORPHAN",
    "MARKETING",
    "UNKNOWN",
}


def load_registry() -> dict:
    return json.loads((evidence_root() / "_config" / "topology-registry.json").read_text())


def normalize_href(href: str) -> str:
    if not href:
        return href
    if href.startswith("javascript:"):
        return href
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(ORIGIN + "/", href.lstrip("/"))


def path_from_url(url: str) -> str:
    if url.startswith("http"):
        p = urlparse(url)
        path = p.path.lstrip("/")
        if p.fragment:
            return f"{path}#{p.fragment}"
        return path
    return url.lstrip("/")


def _family_record(fid, pattern, rclass, domain, markets, **extra) -> dict:
    rec = {
        "route_family_id": fid,
        "canonical_pattern": pattern,
        "route_class": rclass,
        "market_contexts": markets or [],
        "product_domain": domain if isinstance(domain, list) else [domain],
        "template_source_family": extra.get("template"),
        "instance_generation_rule": extra.get("rule"),
        "representative_instances": extra.get("reps") or [],
        "canonical_target": extra.get("canonical_target"),
        "review_tier": extra.get("tier", "D"),
        "discovery_sources": extra.get("discovery_sources") or [],
        "evidence_status": extra.get("evidence_status", "OBSERVED_SOURCE"),
        "evidence_refs": extra.get("evidence_refs") or [],
        "instance_count_source": extra.get("instance_count_source"),
        "label": extra.get("label"),
    }
    return rec


def registry_families(reg: dict) -> dict[str, dict]:
    out = {}
    for item in reg.get("live_families") or []:
        path = item.get("path") or item.get("external")
        out[item["family"]] = _family_record(
            item["family"],
            path,
            item["class"],
            item["domain"],
            item.get("markets"),
            tier=item.get("tier", "B"),
            label=item.get("label"),
            template=f"site/{item['path']}" if item.get("path") else None,
            evidence_refs=[{"ref_type": "registry", "ref": path}],
        )
    for item in reg.get("redirect_stubs") or []:
        out[item["family"]] = _family_record(
            item["family"],
            item["path"],
            "REDIRECT_STUB",
            ["utility"],
            [],
            tier="D",
            canonical_target=item.get("canonical_target"),
            evidence_refs=[{"ref_type": "registry", "ref": item["path"]}],
        )
    for item in reg.get("seo_twins") or []:
        out[item["family"]] = _family_record(
            item["family"],
            item["path"],
            "SEO_TWIN",
            ["sectors_themes"],
            [],
            tier="D",
            canonical_target=item.get("canonical_live"),
            evidence_refs=[{"ref_type": "nav_comment", "ref": item.get("note") or item["path"]}],
        )
    for item in reg.get("parameterized") or []:
        out[item["family"]] = _family_record(
            item["family"],
            item["pattern"],
            item["class"],
            item["domain"],
            item.get("markets"),
            tier=item.get("tier", "B"),
            template=item.get("template"),
            rule=item["pattern"],
            evidence_refs=[{"ref_type": "template", "ref": item.get("template") or item["pattern"]}],
        )
    for item in reg.get("generation_rules") or []:
        out[item["family"]] = _family_record(
            item["family"],
            item["pattern"],
            item["class"],
            item["domain"],
            item.get("markets"),
            tier="C" if item["class"] == "GENERATED_INSTANCE" else "D",
            rule=item.get("glob") or item.get("prefix"),
            evidence_refs=[{"ref_type": "generation_rule", "ref": item.get("glob") or item.get("prefix")}],
        )
    for path in reg.get("utility_paths") or []:
        fid = "RF.utility." + Path(path).stem
        out[fid] = _family_record(fid, path, "UTILITY", ["utility"], [], tier="D")
    for path in reg.get("marketing_paths") or []:
        fid = "RF.marketing." + Path(path).stem
        out[fid] = _family_record(fid, path, "MARKETING", ["marketing"], [], tier="D")
    out["RF.bot.external"] = out.get("RF.bot.external") or _family_record(
        "RF.bot.external",
        "https://bot.mastermind-x.com",
        "LIVE_PRODUCT",
        ["monitoring"],
        [],
        tier="B",
        label="Mastermind Bot",
    )
    return out


def classify_source_file(rel: str, text_head: str, reg: dict) -> dict:
    name = Path(rel).name
    if name.startswith(tuple(reg.get("debris_name_prefixes") or ())) or name in set(reg.get("debris_exact") or []):
        return {"route_class": "UNKNOWN", "family": "RF.debris." + Path(rel).stem, "reason": "excluded debris rule"}
    for stub in reg.get("redirect_stubs") or []:
        if rel == stub["path"] or name == stub["path"]:
            return {
                "route_class": "REDIRECT_STUB",
                "family": stub["family"],
                "canonical_target": stub["canonical_target"],
                "reason": "registry redirect stub",
            }
    for twin in reg.get("seo_twins") or []:
        if rel == twin["path"] or name == twin["path"]:
            return {
                "route_class": "SEO_TWIN",
                "family": twin["family"],
                "canonical_target": twin.get("canonical_live"),
                "reason": twin.get("note") or "registry SEO twin",
            }
    for live in reg.get("live_families") or []:
        if live.get("path") == rel or live.get("path") == name:
            return {"route_class": live["class"], "family": live["family"], "reason": "registry live family"}
    if name in (reg.get("utility_paths") or []):
        return {"route_class": "UTILITY", "family": "RF.utility." + Path(name).stem, "reason": "registry utility"}
    if name in (reg.get("marketing_paths") or []):
        return {"route_class": "MARKETING", "family": "RF.marketing." + Path(name).stem, "reason": "registry marketing"}
    for rule in reg.get("generation_rules") or []:
        if rule.get("glob") and fnmatch.fnmatch(rel, rule["glob"]):
            if rel in (rule.get("exclude") or []):
                continue
            return {
                "route_class": rule["class"],
                "family": rule["family"],
                "reason": f"generation rule {rule['glob']}",
            }
        if rule.get("prefix") and name.startswith(rule["prefix"]) and name.endswith(".html"):
            if name in (rule.get("exclude") or []):
                continue
            return {
                "route_class": rule["class"],
                "family": rule["family"],
                "reason": f"generation prefix {rule['prefix']}",
            }
    # heuristic stub: tiny file with meta refresh to another html
    if "http-equiv=\"refresh\"" in text_head.lower() or "http-equiv='refresh'" in text_head.lower():
        m = re.search(r"url=([^\"']+)", text_head, re.I)
        if m and ".html" in m.group(1) and len(text_head) < 20000:
            return {
                "route_class": "REDIRECT_STUB",
                "family": "RF.stub." + Path(rel).stem,
                "canonical_target": m.group(1),
                "reason": "heuristic meta-refresh stub",
            }
    return {
        "route_class": "LEGACY_ORPHAN" if "/" not in rel else "UNKNOWN",
        "family": "RF.unregistered." + rel.replace("/", ".").replace(".html", ""),
        "reason": "no registry match",
    }


def scan_generated_site(reg: dict | None = None) -> list[dict]:
    reg = reg or load_registry()
    site = repo_root() / "site"
    rows = []
    for p in sorted(site.rglob("*.html")):
        rel = p.relative_to(site).as_posix()
        try:
            head = p.read_text(errors="ignore")[:12000]
        except Exception:
            head = ""
        cls = classify_source_file(rel, head, reg)
        rows.append(
            {
                "source_path": "site/" + rel,
                "rel": rel,
                "bytes": p.stat().st_size,
                **cls,
            }
        )
    return rows


def parse_nav_tree() -> list[dict]:
    """Parse _navlinks.html.j2 into hierarchical nav edges with a real div stack."""
    text = (repo_root() / "templates" / "_navlinks.html.j2").read_text()
    edges: list[dict] = []
    # frames: {depth, label}
    frames: list[dict] = []
    depth = 0
    i = 0
    n = len(text)

    def current_path() -> list[str]:
        return [f["label"] for f in frames if f.get("label")]

    def emit(href: str, label: str, cls: str):
        if not href or href.startswith("javascript:"):
            return
        path = current_path()
        if "nav-brand" in cls:
            path = ["Brand"]
            label = "Home"
        elif not path:
            path = ["Ungrouped"]
        mega = "Research" in path or "mega" in cls or "rail" in cls
        edges.append(
            {
                "nav_path": path[:],
                "nav_label": label,
                "destination": href,
                "edge_type": "MEGA_NAV" if mega else "PRIMARY_NAV",
                "evidence_status": "OBSERVED_SOURCE",
                "channel": "desktop",
                "discovery_source": "NAV_TEMPLATE_SOURCE",
            }
        )

    while i < n:
        if text.startswith("<div", i):
            depth += 1
            chunk = text[i : i + 80]
            if re.match(r'<div class="nav-dd', chunk):
                frames.append({"depth": depth, "label": ""})
            i += 4
            continue
        if text.startswith("</div>", i):
            if frames and frames[-1]["depth"] == depth:
                frames.pop()
            depth = max(0, depth - 1)
            i += 6
            continue
        if text.startswith("<a ", i) or text.startswith("<a\n", i):
            end = text.find(">", i)
            if end < 0:
                i += 1
                continue
            tag = text[i : end + 1]
            hm = re.search(r'href="(?:\{\{\s*NP\s*\}\})?([^"]+)"', tag)
            cm = re.search(r'class="([^"]*)"', tag)
            href = hm.group(1) if hm else ""
            cls = cm.group(1) if cm else ""
            after = text[end + 1 : end + 800]
            tm = re.search(r"t\('([^']+)'", after)
            if not tm:
                tm = re.search(r'aria-label="([^"]+)"', tag)
            label = tm.group(1) if tm else href
            if cls.startswith("nav-link") or "nav-sub-trig" in cls:
                if frames and frames[-1]["label"] == "":
                    frames[-1]["label"] = label
            if href:
                emit(href, label, cls)
            i = end + 1
            continue
        i += 1

    seen = set()
    uniq = []
    for e in edges:
        key = (tuple(e["nav_path"]), e["destination"], e["nav_label"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)
    return uniq


def classify_dom_link(href: str, in_nav: bool, extra: str = "") -> str:
    if not href:
        return "UNKNOWN"
    if href.startswith("http") and "mastermind-x.com" not in href and "bot.mastermind" not in href:
        return "EXTERNAL"
    if in_nav:
        return "GLOBAL_NAV"
    if extra == "card" or "pvcard" in extra:
        return "CARD_LINK"
    if extra == "cta":
        return "PRIMARY_CTA"
    if extra == "local":
        return "LOCAL_NAV"
    if extra == "search":
        return "SEARCH"
    if extra == "footer":
        return "FOOTER"
    return "CONTEXTUAL"


def match_family_for_url(url: str, families: dict, reg: dict) -> tuple[str, dict]:
    path = path_from_url(url)
    base, frag = (path.split("#", 1) + [""])[:2]
    if url.startswith("https://bot.mastermind"):
        return "RF.bot.external", {"external": True}
    rail = reg.get("hash_rails") or {}
    if path in rail:
        return rail[path]["family"], {"hash": frag, "rail": True}
    for item in reg.get("parameterized") or []:
        prefix = item["pattern"].split("#")[0]
        if base == prefix:
            return item["family"], {"ticker": frag or None}
    for item in reg.get("live_families") or []:
        if item.get("path") == base or item.get("path") == path:
            return item["family"], {"hash": frag or None}
    for item in reg.get("redirect_stubs") or []:
        if item["path"] == base:
            return item["family"], {"canonical_target": item.get("canonical_target")}
    for item in reg.get("seo_twins") or []:
        if item["path"] == base:
            return item["family"], {}
    cls = classify_source_file(base, "", reg)
    return cls["family"], {"hash": frag or None}


def reused_screenshot_name(url: str) -> dict:
    """Map a URL to existing Phase 0 screenshot stems."""
    p = path_from_url(url)
    base, frag = (p.split("#", 1) + [""])[:2]
    if base == "stock.html" and frag:
        stem = f"stock.html_{frag}"
    else:
        stem = base.replace("/", "_") or "root"
    shots = evidence_root() / "00-product-map" / "screenshots"
    out = {}
    for vp in ("1440x1000", "390x844"):
        cand = shots / f"{stem}_{vp}.png"
        if cand.exists():
            out[vp] = cand
    return out
