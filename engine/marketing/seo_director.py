"""engine.marketing.seo_director — Beacon SEO audit engine (weekly, fully offline).

Audits the rendered site (site/*.html, site/stocks/ sampled, site/sitemap.xml,
site/robots.txt, site/llms.txt, site/brand-facts.json) without any network calls.

Health score 0-100, weighted:
  technical       30%  canonical correctness + sitemap validity + robots ok
  on_page         30%  title/desc coverage and quality (core pages)
  structured_data 15%  JSON-LD parseable + og coverage
  ai_readiness    10%  llms.txt + brand-facts present and fresh (<90d)
  links           10%  broken internal links + orphans
  perf             5%  page weight >2.5MB flags

Canonical host: https://www.mastermind-x.com/
NOTE: The live site currently uses https://mastermind-x.com/ (no www) in
sitemap.xml, robots.txt, and page canonical tags.  The spec's "www" host is
the target canonical; issues are flagged accordingly so operators can migrate.
TODO: unify via lib.seo.SITE_BASE once lib/seo.py is available.

Page families (by filename):
  stocks    — site/stocks/**
  fund      — fund_*.html
  strategy  — strategy_*.html
  report    — report_*.html
  utility   — _mockup*.html, chat.html, calibration.html
  core      — everything else

Public API (all fail-soft — no public function raises):
  classify_page(stem: str) -> str
  audit_site(site_dir: Path, *, as_of=None) -> dict
  run(root: Path, *, as_of=None, write=True) -> dict

CLI:
  python -m engine.marketing.seo_director --root . [--dry-run]
  Prints a compact summary table.  Emits ::warning:: lines for critical issues.
  Always exits 0 on findings; exits 1 only on crash.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# NOTE: parallel lane lib/seo.py will define SITE_BASE; import it when ready.
# R1: the canonical host is the www form. The apex (non-www) form is our CURRENT deployed
# host and a KNOWN in-flight migration target — it is tracked as a DISTINCT, counted
# HIGH-severity issue class (apex_host / canonical_non_www), never silently accepted as
# canonical. A genuinely foreign host stays CRITICAL. See _is_www_host / _is_apex_host /
# _is_own_host — host CORRECTNESS is judged there, not by treating apex as "valid".
try:  # single source of truth (lib/seo.py, PR A / D12A R1)
    from lib.seo import SITE_BASE
except Exception:  # pragma: no cover — lib layout changes must not kill the Director
    SITE_BASE = "https://www.mastermind-x.com/"
# Current deployed apex host (no www). Used only to distinguish OUR apex from a foreign
# host (file-existence / path extraction). Does NOT certify the host as canonical.
_SITE_BASE_ALT = "https://mastermind-x.com/"

_STOCKS_SAMPLE_N = 25          # evenly-spaced sample from site/stocks/
_MAX_ISSUES = 200              # cap issues list
_MAX_PAGES_IN_ORDER = 10       # cap page lists in work orders
_MAX_WORK_ORDERS = 20

_TITLE_MIN = 15
_TITLE_MAX = 70
_DESC_MIN = 50
_DESC_MAX = 170
_PAGE_WEIGHT_WARN_MB = 2.5
_BRAND_FACTS_STALE_DAYS = 90

_UTILITY_NAMES = frozenset({"chat.html", "calibration.html"})

_ARTIFACTS_REL = Path("data") / "marketing" / "seo"
_AUDIT_FILE = "seo_audit.json"
_WORK_ORDERS_FILE = "seo_work_orders.json"
_SCORECARD_FILE = "seo_scorecard.json"
_HISTORY_FILE = "seo_history.jsonl"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json_atomic(path: Path, obj: Any) -> None:
    """Atomic write via temp file in same directory (mirrors radar_internal pattern)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=".tmp_", suffix=".json"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


def _append_jsonl(path: Path, obj: Any) -> None:
    """Append one JSON line to a JSONL file atomically (temp-and-replace-whole-file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[str] = []
    if path.exists():
        try:
            existing = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        except Exception:  # noqa: BLE001
            pass
    existing.append(json.dumps(obj, ensure_ascii=False))
    tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".jsonl")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(existing) + "\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


def _is_www_host(url: str) -> bool:
    """Return True if URL starts with SITE_BASE (www form = the R1 canonical host)."""
    return url.startswith(SITE_BASE)


def _is_apex_host(url: str) -> bool:
    """Return True if URL is on the current deployed apex (non-www) host.

    Apex is a KNOWN in-flight migration target (apex -> www), so it is tracked as a
    distinct, counted HIGH-severity class — never silently accepted as canonical.
    """
    return url.startswith(_SITE_BASE_ALT) and not url.startswith(SITE_BASE)


def _is_own_host(url: str) -> bool:
    """Return True if URL is on either of OUR hosts (www or apex).

    Used only to distinguish our own hosts from a genuinely FOREIGN host (which is a
    critical wrong-host defect).  It does NOT certify the host as canonical — apex is
    our host but is still flagged per R1.
    """
    return url.startswith(SITE_BASE) or url.startswith(_SITE_BASE_ALT)


# Back-compat alias: for structural "is this one of our hosts / resolvable to a file"
# checks (file existence, path extraction).  Host-CORRECTNESS is judged via _is_www_host
# / _is_apex_host, NOT this function.
_is_valid_host = _is_own_host


def _url_path(url: str) -> str:
    """Strip host prefix; return the path portion."""
    for base in (SITE_BASE, _SITE_BASE_ALT):
        if url.startswith(base):
            return url[len(base):]
    return url


def _issue_id(cls: str, page: str) -> str:
    """Stable slug for an issue (class + page)."""
    slug = re.sub(r"[^a-z0-9]+", "_", (cls + "_" + page).lower()).strip("_")
    return slug[:120]


# ---------------------------------------------------------------------------
# Page family classifier
# ---------------------------------------------------------------------------


def classify_page(stem: str) -> str:
    """Return the page family for a filename stem or relative path string.

    Examples:
      "stocks/AAPL"   -> "stocks"
      "fund_ako"      -> "fund"
      "strategy_btc"  -> "strategy"
      "report_haven"  -> "report"
      "_mockup_foo"   -> "utility"
      "chat"          -> "utility"
      "calibration"   -> "utility"
      "macro"         -> "core"
    """
    name = Path(stem).name  # drop any leading path component
    if name.startswith("stocks/") or str(stem).startswith("stocks/"):
        return "stocks"
    if name.startswith("fund_"):
        return "fund"
    if name.startswith("strategy_"):
        return "strategy"
    if name.startswith("report_"):
        return "report"
    if name.startswith("_mockup") or name in {"chat", "calibration"}:
        return "utility"
    return "core"


def _classify_html(path: Path, site_dir: Path) -> str:
    """Classify an HTML file by its path relative to site_dir."""
    try:
        rel = path.relative_to(site_dir)
    except ValueError:
        rel = Path(path.name)
    parts = rel.parts
    if len(parts) > 1 and parts[0] == "stocks":
        return "stocks"
    return classify_page(rel.stem)


# ---------------------------------------------------------------------------
# HTML meta-data extraction
# ---------------------------------------------------------------------------

_RE_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_RE_META_DESC = re.compile(
    r'<meta\s[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_RE_META_DESC_ALT = re.compile(
    r'<meta\s[^>]*content=["\']([^"\']*)["\'][^>]*name=["\']description["\']',
    re.IGNORECASE,
)
_RE_CANONICAL = re.compile(
    r'<link\s[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_RE_OG_TITLE = re.compile(
    r'<meta\s[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_RE_OG_DESC = re.compile(
    r'<meta\s[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_RE_OG_IMAGE = re.compile(
    r'<meta\s[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']*)["\']',
    re.IGNORECASE,
)
_RE_JSONLD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_RE_LANG = re.compile(r'<html[^>]+lang=["\']([^"\']+)["\']', re.IGNORECASE)
_RE_A_HREF = re.compile(r'<a\s[^>]*href=["\']([^"\'#?]+)["\']', re.IGNORECASE)


def _extract_meta(html: str) -> dict:
    """Extract SEO-relevant meta from raw HTML string. Returns a dict of found fields."""
    m_title = _RE_TITLE.search(html)
    title = re.sub(r"<[^>]+>", "", m_title.group(1)).strip() if m_title else None

    m_desc = _RE_META_DESC.search(html) or _RE_META_DESC_ALT.search(html)
    description = m_desc.group(1).strip() if m_desc else None

    m_can = _RE_CANONICAL.search(html)
    canonical = m_can.group(1).strip() if m_can else None

    og_title = ((_RE_OG_TITLE.search(html) or None) and _RE_OG_TITLE.search(html).group(1))
    og_desc = ((_RE_OG_DESC.search(html) or None) and _RE_OG_DESC.search(html).group(1))
    og_image = ((_RE_OG_IMAGE.search(html) or None) and _RE_OG_IMAGE.search(html).group(1))

    jsonld_blocks = _RE_JSONLD.findall(html)
    lang_m = _RE_LANG.search(html)
    lang = lang_m.group(1) if lang_m else None

    # Extract internal relative .html hrefs
    hrefs = _RE_A_HREF.findall(html)

    return {
        "title": title,
        "description": description,
        "canonical": canonical,
        "og_title": og_title,
        "og_desc": og_desc,
        "og_image": og_image,
        "jsonld_blocks": jsonld_blocks,
        "lang": lang,
        "hrefs": hrefs,
    }


def _html_size_bytes(path: Path) -> int:
    try:
        return path.stat().st_size
    except Exception:  # noqa: BLE001
        return 0


# ---------------------------------------------------------------------------
# Sitemap reader
# ---------------------------------------------------------------------------


def _parse_sitemap(sitemap_path: Path) -> dict:
    """Parse sitemap.xml and return {urls: [...], parse_ok: bool, error: str|None}."""
    result = {"urls": [], "parse_ok": False, "error": None}
    try:
        tree = ElementTree.parse(sitemap_path)
        root = tree.getroot()
        # Handle namespace
        ns = ""
        m = re.match(r"\{([^}]+)\}", root.tag)
        if m:
            ns = m.group(1)
        ns_prefix = f"{{{ns}}}" if ns else ""

        urls = []
        for url_el in root.iter(f"{ns_prefix}url"):
            loc_el = url_el.find(f"{ns_prefix}loc")
            if loc_el is not None and loc_el.text:
                urls.append(loc_el.text.strip())
        result["urls"] = urls
        result["parse_ok"] = True
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


# ---------------------------------------------------------------------------
# robots.txt reader
# ---------------------------------------------------------------------------


def _parse_robots(robots_path: Path) -> dict:
    """Return {ok: bool, disallows_all: bool, has_sitemap_line: bool, sitemap_urls: [...]}."""
    out = {
        "ok": False,
        "disallows_all": False,
        "has_sitemap_line": False,
        "sitemap_urls": [],
        "sitemap_host_ok": False,   # True ONLY if a Sitemap line uses the www canonical host (R1)
        "sitemap_host_apex": False,  # True if a Sitemap line uses the apex (non-www) host
        "sitemap_host_foreign": False,  # True if a Sitemap line uses a genuinely foreign host
    }
    try:
        text = robots_path.read_text(encoding="utf-8")
        out["ok"] = True
        lines = [l.strip() for l in text.splitlines()]
        user_agent_star = False
        for i, line in enumerate(lines):
            low = line.lower()
            if low.startswith("user-agent:") and line.split(":", 1)[1].strip() == "*":
                user_agent_star = True
            if user_agent_star and low.startswith("disallow:"):
                val = line.split(":", 1)[1].strip()
                if val in ("/", "/*"):
                    out["disallows_all"] = True
            if low.startswith("sitemap:"):
                sm_url = line.split(":", 1)[1].strip()
                # fix: split on "sitemap:" but URL includes "https:" so rebuild
                sm_full = line[len("sitemap:"):].strip()
                out["sitemap_urls"].append(sm_full)
                out["has_sitemap_line"] = True
        # Classify each Sitemap host per R1: www = ok, apex = migration-flag, else foreign.
        for sm in out["sitemap_urls"]:
            if _is_www_host(sm):
                out["sitemap_host_ok"] = True
            elif _is_apex_host(sm):
                out["sitemap_host_apex"] = True
            else:
                out["sitemap_host_foreign"] = True
    except Exception:  # noqa: BLE001
        pass
    return out


# ---------------------------------------------------------------------------
# brand-facts reader
# ---------------------------------------------------------------------------


def _parse_brand_facts(path: Path, as_of: datetime) -> dict:
    """Return {present, parses, effective_at, age_days}."""
    out = {"present": path.exists(), "parses": False, "effective_at": None, "age_days": None}
    if not out["present"]:
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        out["parses"] = True
        ea = data.get("effective_at") or data.get("as_of")
        if ea:
            out["effective_at"] = str(ea)[:10]
            try:
                ea_dt = datetime.fromisoformat(out["effective_at"])
                out["age_days"] = max(0, (as_of.date() - ea_dt.date()).days)
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    return out


# ---------------------------------------------------------------------------
# Core audit logic
# ---------------------------------------------------------------------------


def audit_site(site_dir: Path, *, as_of: datetime | None = None) -> dict:
    """Audit the rendered site directory.  Pure-ish: reads files, returns dict, no writes.

    Args:
        site_dir: Path to the site/ directory.
        as_of:    Timestamp for the audit (default: now UTC).

    Returns:
        A dict matching the seo_audit.v1 schema.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)
    as_of_iso = as_of.strftime("%Y-%m-%dT%H:%M:%SZ")

    issues: list[dict] = []
    _total_issues = [0]  # total attempted (including truncated)
    # True per-class / per-severity tallies (NOT subject to the _MAX_ISSUES display cap).
    # The health score MUST use these — computing it off the capped `issues` list would
    # silently suppress penalties on large sites (>_MAX_ISSUES issues) and let the score
    # stop decreasing once the cap is hit.
    class_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    # One representative issue per class, retained REGARDLESS of the _MAX_ISSUES display cap.
    # Work orders are built from these + the true class_counts, so a class that overflows
    # the display list (e.g. missing_from_sitemap, sitemap_apex_host — emitted late) still
    # produces an actionable order with example pages instead of being silently dropped.
    class_exemplars: dict[str, list[dict]] = {}
    _EXEMPLARS_PER_CLASS = _MAX_PAGES_IN_ORDER

    def _add_issue(severity: str, cls: str, page: str, detail: str) -> None:
        _total_issues[0] += 1
        class_counts[cls] = class_counts.get(cls, 0) + 1
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        rec = {
            "id": _issue_id(cls, page),
            "severity": severity,
            "class": cls,
            "page": page,
            "detail": detail,
        }
        ex = class_exemplars.setdefault(cls, [])
        if len(ex) < _EXEMPLARS_PER_CLASS:
            ex.append(rec)
        if len(issues) >= _MAX_ISSUES:
            return
        issues.append(rec)

    # ---- discover HTML pages ----
    core_pages: list[Path] = []
    fund_pages: list[Path] = []
    strategy_pages: list[Path] = []
    report_pages: list[Path] = []
    utility_pages: list[Path] = []
    stocks_pages: list[Path] = []

    for html in sorted(site_dir.glob("*.html")):
        fam = _classify_html(html, site_dir)
        if fam == "utility":
            utility_pages.append(html)
        elif fam == "fund":
            fund_pages.append(html)
        elif fam == "strategy":
            strategy_pages.append(html)
        elif fam == "report":
            report_pages.append(html)
        else:
            core_pages.append(html)

    stocks_dir = site_dir / "stocks"
    if stocks_dir.is_dir():
        stocks_pages = sorted(stocks_dir.glob("*.html"))

    non_stocks_pages = core_pages + fund_pages + strategy_pages + report_pages + utility_pages
    all_public_pages = non_stocks_pages  # stocks handled separately

    # ---- build set of filenames present in site/ for internal link checks ----
    site_files: set[str] = set()
    for f in site_dir.rglob("*.html"):
        try:
            site_files.add(str(f.relative_to(site_dir)))
        except ValueError:
            pass

    # ---- parse all non-stocks pages ----
    metas: dict[Path, dict] = {}
    for page in non_stocks_pages:
        try:
            html = page.read_text(encoding="utf-8", errors="replace")
            metas[page] = _extract_meta(html)
            metas[page]["_size"] = _html_size_bytes(page)
            metas[page]["_family"] = _classify_html(page, site_dir)
        except Exception:  # noqa: BLE001
            metas[page] = {
                "title": None, "description": None, "canonical": None,
                "og_title": None, "og_desc": None, "og_image": None,
                "jsonld_blocks": [], "lang": None, "hrefs": [],
                "_size": 0, "_family": _classify_html(page, site_dir),
            }

    # ---- per-page checks ----
    title_values: dict[str, list[str]] = {}   # title text -> [page stems]
    desc_values: dict[str, list[str]] = {}    # desc text -> [page stems]

    for page, meta in metas.items():
        try:
            rel = str(page.relative_to(site_dir))
        except ValueError:
            rel = page.name
        fam = meta["_family"]

        # HTML lang
        if not meta.get("lang"):
            _add_issue("medium", "missing_lang", rel, "No <html lang> attribute")

        # Title
        title = meta.get("title")
        if not title:
            sev = "high" if fam in ("core", "fund", "strategy") else "medium"
            _add_issue(sev, "missing_title", rel, "No <title> element")
        else:
            tlen = len(title)
            if tlen < _TITLE_MIN or tlen > _TITLE_MAX:
                _add_issue(
                    "medium", "title_length", rel,
                    f"Title length {tlen} chars (expected {_TITLE_MIN}-{_TITLE_MAX}): {title[:80]}"
                )
            if title not in title_values:
                title_values[title] = []
            title_values[title].append(rel)

        # Meta description
        desc = meta.get("description")
        if not desc:
            sev = "high" if fam in ("core",) else "medium"
            _add_issue(sev, "missing_description", rel, "No meta description")
        else:
            dlen = len(desc)
            if dlen < _DESC_MIN or dlen > _DESC_MAX:
                _add_issue(
                    "medium", "desc_length", rel,
                    f"Description length {dlen} chars (expected {_DESC_MIN}-{_DESC_MAX})"
                )
            if desc not in desc_values:
                desc_values[desc] = []
            desc_values[desc].append(rel)

        # Canonical
        canonical = meta.get("canonical")
        if not canonical:
            sev = "high" if fam in ("core", "fund", "strategy", "report") else "medium"
            _add_issue(sev, "missing_canonical", rel, "No rel=canonical link")
        else:
            # Host check — flag wrong host as critical
            if not _is_valid_host(canonical):
                _add_issue(
                    "critical", "canonical_wrong_host", rel,
                    f"Canonical host invalid: {canonical}"
                )
            else:
                # Check www vs non-www (flag as high — migration issue)
                if not _is_www_host(canonical):
                    _add_issue(
                        "high", "canonical_non_www", rel,
                        f"Canonical uses non-www host (migration target = www): {canonical}"
                    )
                # Self-referential check: canonical path should match page's own rel path
                can_path = _url_path(canonical)
                # For index.html the canonical may be bare root
                if can_path not in (rel, rel.rstrip("/"), ""):
                    # Allow stocks/X.html -> stocks/X.html
                    if can_path != rel and can_path != rel.replace("\\", "/"):
                        # Only flag if they're clearly different pages
                        can_stem = Path(can_path).stem
                        page_stem = page.stem
                        if can_stem != page_stem and can_path != "":
                            _add_issue(
                                "high", "canonical_not_self", rel,
                                f"Canonical points to different page: {canonical}"
                            )

        # OG tags
        if not meta.get("og_title") or not meta.get("og_desc") or not meta.get("og_image"):
            missing_og = [k for k in ("og_title", "og_desc", "og_image") if not meta.get(k)]
            _add_issue(
                "medium", "missing_og", rel,
                f"Missing OG tags: {', '.join(missing_og)}"
            )

        # JSON-LD
        for block in meta.get("jsonld_blocks", []):
            try:
                json.loads(block)
            except Exception:
                _add_issue("medium", "jsonld_parse_error", rel, "JSON-LD block failed to parse")

        # Page weight
        size_mb = meta.get("_size", 0) / (1024 * 1024)
        if size_mb > _PAGE_WEIGHT_WARN_MB:
            _add_issue(
                "low", "page_weight", rel,
                f"HTML size {size_mb:.1f} MB exceeds {_PAGE_WEIGHT_WARN_MB} MB"
            )

        # Internal links check
        seen_hrefs: set[str] = set()
        for href in meta.get("hrefs", []):
            # Only check relative .html links (not external, not anchors, not absolute)
            if href.startswith("http") or href.startswith("//") or href.startswith("#"):
                continue
            if not href.endswith(".html"):
                continue
            # Skip JS/template-literal hrefs — these are runtime-built strings scraped out
            # of <a> tags inside scripts (e.g. basket/${t.id}.html, ${_bbase()}${esc(x.id)}.html)
            # and are NOT static links. Flagging them is a weekly false positive.
            if any(tok in href for tok in ("${", "{{", "<%", "{%")):
                continue
            # De-dupe within a page: one report per distinct broken target, not per occurrence.
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)
            # Normalize relative to page location
            page_dir = page.parent
            try:
                target = (page_dir / href).resolve().relative_to(site_dir.resolve())
                target_str = str(target)
                if target_str not in site_files:
                    _add_issue(
                        "high", "broken_internal_link", rel,
                        f"Broken internal link: {href} (resolved: {target_str})"
                    )
            except (ValueError, Exception):  # noqa: BLE001
                # Absolute href on this host or unresolvable
                pass

    # ---- duplicate titles ----
    for title, pages in title_values.items():
        if len(pages) > 1:
            _add_issue(
                "high", "duplicate_title",
                pages[0],
                f"Duplicate title across {len(pages)} pages: {title[:60]!r}. Others: {pages[1:4]}"
            )

    # ---- duplicate descriptions ----
    for desc, pages in desc_values.items():
        if len(pages) > 1:
            _add_issue(
                "medium", "duplicate_description",
                pages[0],
                f"Duplicate description across {len(pages)} pages. Others: {pages[1:4]}"
            )

    # ---- sitemap ----
    sitemap_path = site_dir / "sitemap.xml"
    sitemap_data = {"total_urls": 0, "core": 0, "stocks": 0,
                    "host_ok": False, "bad_host_count": 0, "apex_host_count": 0,
                    "orphans_in_sitemap": [], "missing_from_sitemap": [],
                    "duplicates": [], "parse_ok": False}

    if sitemap_path.exists():
        sm = _parse_sitemap(sitemap_path)
        sitemap_data["parse_ok"] = sm["parse_ok"]
        if not sm["parse_ok"]:
            _add_issue("critical", "sitemap_parse_error", "sitemap.xml",
                       f"Sitemap XML parse error: {sm.get('error', 'unknown')}")
        else:
            urls = sm["urls"]
            sitemap_data["total_urls"] = len(urls)
            seen_urls: set[str] = set()
            dups: list[str] = []
            bad_host: list[str] = []   # genuinely foreign hosts (critical)
            apex_host: list[str] = []  # our apex (non-www) host — R1 migration flag (high)
            orphans: list[str] = []
            for url in urls:
                if url in seen_urls:
                    dups.append(url)
                seen_urls.add(url)
                if not _is_own_host(url):
                    bad_host.append(url)
                    _add_issue("critical", "sitemap_bad_host", "sitemap.xml",
                               f"Sitemap URL with invalid host: {url}")
                else:
                    if _is_apex_host(url):
                        apex_host.append(url)
                    # Check if the file exists in site/
                    path_part = _url_path(url)
                    file_path = site_dir / path_part
                    if not file_path.exists():
                        orphans.append(url)
                        _add_issue("critical", "sitemap_orphan", "sitemap.xml",
                                   f"Sitemap entry points to missing file: {url}")
                    # Classify url
                    if path_part.startswith("stocks/"):
                        sitemap_data["stocks"] += 1
                    else:
                        sitemap_data["core"] += 1

            sitemap_data["bad_host_count"] = len(bad_host)
            sitemap_data["apex_host_count"] = len(apex_host)
            sitemap_data["orphans_in_sitemap"] = orphans[:50]
            sitemap_data["duplicates"] = dups[:50]
            # host_ok is strict per R1: FALSE if ANY entry is off the www canonical host
            # (foreign OR apex). Apex is our host but not canonical, so it must not read ok.
            sitemap_data["host_ok"] = (len(bad_host) == 0 and len(apex_host) == 0)

            # One aggregate apex issue (HIGH) — apex->www is a known in-flight migration,
            # so it is distinct + counted, never masked as "ok". Aggregate to avoid a
            # per-URL flood that would starve the issues cap.
            if apex_host:
                _add_issue("high", "sitemap_apex_host", "sitemap.xml",
                           f"{len(apex_host)} sitemap <loc> entries use apex (non-www) host; "
                           f"canonical is www (R1). Example: {apex_host[0]}")

            if dups:
                _add_issue("high", "sitemap_duplicates", "sitemap.xml",
                           f"{len(dups)} duplicate <loc> entries in sitemap")

            # Pages missing from sitemap: core/fund/strategy/report pages not in utility
            in_sitemap_paths = {_url_path(u) for u in urls if _is_valid_host(u)}
            missing_from_sm = []
            for page in non_stocks_pages:
                fam = _classify_html(page, site_dir)
                if fam == "utility":
                    continue
                try:
                    rel = str(page.relative_to(site_dir))
                except ValueError:
                    rel = page.name
                if rel not in in_sitemap_paths and rel.replace("\\", "/") not in in_sitemap_paths:
                    missing_from_sm.append(rel)
                    _add_issue("medium", "missing_from_sitemap", rel,
                               f"Public page not in sitemap: {rel}")
            # Full truthful total — the list field below is a capped SAMPLE (50), and the
            # per-page issues above can be starved by the _MAX_ISSUES cap on large sites,
            # so the honest count must live in its own field.
            sitemap_data["missing_from_sitemap_count"] = len(missing_from_sm)
            sitemap_data["missing_from_sitemap"] = missing_from_sm[:50]
    else:
        _add_issue("critical", "missing_sitemap", "sitemap.xml", "sitemap.xml not found")

    # ---- robots.txt ----
    robots_path = site_dir / "robots.txt"
    robots_data: dict = {"robots_ok": False, "robots_sitemap_host_ok": False}
    if robots_path.exists():
        rb = _parse_robots(robots_path)
        robots_data["robots_ok"] = rb["ok"]
        robots_data["robots_sitemap_host_ok"] = rb["sitemap_host_ok"]
        if rb["disallows_all"]:
            _add_issue("critical", "robots_blocks_all", "robots.txt",
                       "robots.txt Disallow: / blocks all crawlers")
        if not rb["has_sitemap_line"]:
            _add_issue("high", "robots_no_sitemap", "robots.txt",
                       "robots.txt has no Sitemap: directive")
        # Host of the Sitemap: directive per R1 (canonical host = www).
        if rb.get("sitemap_host_foreign"):
            _add_issue("critical", "robots_sitemap_wrong_host", "robots.txt",
                       f"robots.txt Sitemap uses a foreign host: {rb['sitemap_urls']}")
        elif rb.get("sitemap_host_apex") and not rb["sitemap_host_ok"]:
            _add_issue("high", "robots_sitemap_apex_host", "robots.txt",
                       f"robots.txt Sitemap uses apex (non-www) host; canonical is www: {rb['sitemap_urls']}")
    else:
        _add_issue("high", "missing_robots", "robots.txt", "robots.txt not found")

    # ---- llms.txt ----
    llms_path = site_dir / "llms.txt"
    llms_present = llms_path.exists()
    if not llms_present:
        _add_issue("low", "missing_llms_txt", "llms.txt", "llms.txt not present")

    # ---- brand-facts.json ----
    brand_facts_path = site_dir / "brand-facts.json"
    bf = _parse_brand_facts(brand_facts_path, as_of)
    if not bf["present"]:
        _add_issue("low", "missing_brand_facts", "brand-facts.json", "brand-facts.json not present")
    elif not bf["parses"]:
        _add_issue("medium", "brand_facts_parse_error", "brand-facts.json",
                   "brand-facts.json failed to parse as JSON")
    elif bf["age_days"] is not None and bf["age_days"] > _BRAND_FACTS_STALE_DAYS:
        _add_issue("low", "brand_facts_stale", "brand-facts.json",
                   f"brand-facts.json effective_at is {bf['age_days']}d ago (warn >{_BRAND_FACTS_STALE_DAYS}d)")

    # ---- stocks sample ----
    stocks_sample_results: dict = {
        "sampled": 0, "with_canonical": 0, "with_title": 0, "with_desc": 0,
        "bad_host_canonical": 0,
    }
    if stocks_pages:
        n = len(stocks_pages)
        step = max(1, n // _STOCKS_SAMPLE_N)
        sample = stocks_pages[::step][:_STOCKS_SAMPLE_N]
        stocks_sample_results["sampled"] = len(sample)
        for sp in sample:
            try:
                html = sp.read_text(encoding="utf-8", errors="replace")
                sm = _extract_meta(html)
                if sm.get("title"):
                    stocks_sample_results["with_title"] += 1
                if sm.get("description"):
                    stocks_sample_results["with_desc"] += 1
                can = sm.get("canonical")
                if can:
                    stocks_sample_results["with_canonical"] += 1
                    if not _is_valid_host(can):
                        stocks_sample_results["bad_host_canonical"] += 1
                        _add_issue(
                            "critical", "canonical_wrong_host",
                            f"stocks/{sp.name}",
                            f"Stock page canonical wrong host: {can}"
                        )
            except Exception:  # noqa: BLE001
                pass

    # ---- census ----
    families = ("core", "fund", "strategy", "report", "utility", "stocks")
    family_pages = {
        "core": core_pages, "fund": fund_pages, "strategy": strategy_pages,
        "report": report_pages, "utility": utility_pages, "stocks": stocks_pages,
    }
    in_sitemap_paths_set: set[str] = set()
    if sitemap_path.exists() and sitemap_data["parse_ok"]:
        sm_urls = _parse_sitemap(sitemap_path)["urls"]
        in_sitemap_paths_set = {_url_path(u) for u in sm_urls if _is_valid_host(u)}

    census_by_family: dict[str, dict] = {}
    for fam in families:
        pages_list = family_pages[fam]
        total = len(pages_list)
        if fam == "stocks":
            # Don't audit individually; use sample data
            census_by_family[fam] = {
                "pages": total,
                "sampled": stocks_sample_results["sampled"],
                "with_canonical": stocks_sample_results["with_canonical"],
                "with_title": stocks_sample_results["with_title"],
                "with_desc": stocks_sample_results["with_desc"],
                "with_og": None,
                "with_jsonld": None,
                "in_sitemap": None,
            }
            continue
        with_canonical = 0
        with_desc = 0
        with_og = 0
        with_jsonld = 0
        in_sitemap_count = 0
        for p in pages_list:
            m = metas.get(p, {})
            if m.get("canonical"):
                with_canonical += 1
            if m.get("description"):
                with_desc += 1
            if m.get("og_title") and m.get("og_desc") and m.get("og_image"):
                with_og += 1
            if m.get("jsonld_blocks"):
                with_jsonld += 1
            try:
                rel = str(p.relative_to(site_dir))
            except ValueError:
                rel = p.name
            if rel in in_sitemap_paths_set or rel.replace("\\", "/") in in_sitemap_paths_set:
                in_sitemap_count += 1
        census_by_family[fam] = {
            "pages": total,
            "with_canonical": with_canonical,
            "with_desc": with_desc,
            "with_og": with_og,
            "with_jsonld": with_jsonld,
            "in_sitemap": in_sitemap_count,
        }

    total_pages = sum(len(v) for v in family_pages.values())

    # ---- health score ----
    # Use the TRUE (uncapped) per-class counts so the score reflects every issue,
    # not just the first _MAX_ISSUES that fit in the display list.
    health_score = _compute_health_score(
        class_counts=class_counts,
        metas=metas,
        census_by_family=census_by_family,
        sitemap_data=sitemap_data,
        robots_data=robots_data,
        llms_present=llms_present,
        brand_facts=bf,
        non_stocks_pages=non_stocks_pages,
        core_pages=core_pages,
        site_dir=site_dir,
    )

    # ---- cap issues list ----
    issues_out = issues[:_MAX_ISSUES]
    truncated_count = max(0, _total_issues[0] - len(issues_out))

    crawl_infra = {
        "robots_ok": robots_data.get("robots_ok", False),
        "robots_sitemap_host_ok": robots_data.get("robots_sitemap_host_ok", False),
        "llms_txt_present": llms_present,
        "brand_facts_present": bf["present"],
        "brand_facts_age_days": bf.get("age_days"),
    }

    return {
        "schema": "seo_audit.v1",
        "as_of": as_of_iso,
        "health_score": health_score,
        "census": {
            "total_pages": total_pages,
            "by_family": census_by_family,
        },
        "sitemap": {
            "total_urls": sitemap_data["total_urls"],
            "core": sitemap_data.get("core", 0),
            "stocks": sitemap_data.get("stocks", 0),
            "host_ok": sitemap_data.get("host_ok", False),
            "bad_host_count": sitemap_data.get("bad_host_count", 0),
            "apex_host_count": sitemap_data.get("apex_host_count", 0),
            "orphans_in_sitemap": sitemap_data.get("orphans_in_sitemap", []),
            "missing_from_sitemap": sitemap_data.get("missing_from_sitemap", []),
            "missing_from_sitemap_count": sitemap_data.get("missing_from_sitemap_count", 0),
            "duplicates": sitemap_data.get("duplicates", []),
        },
        "crawl_infra": crawl_infra,
        "issues": issues_out,
        "issue_counts_by_class": dict(class_counts),
        "issue_counts_by_severity": dict(severity_counts),
        "_class_exemplars": {k: list(v) for k, v in class_exemplars.items()},
        "_issues_truncated_count": truncated_count,
    }


# ---------------------------------------------------------------------------
# Health score computation
# ---------------------------------------------------------------------------


def _compute_health_score(
    class_counts: dict,
    metas: dict,
    census_by_family: dict,
    sitemap_data: dict,
    robots_data: dict,
    llms_present: bool,
    brand_facts: dict,
    non_stocks_pages: list,
    core_pages: list,
    site_dir: Path,
) -> int:
    """Compute 0-100 health score per documented weights.

    technical       30%  canonical+sitemap+robots correctness
    on_page         30%  title/desc coverage+quality (core pages)
    structured_data 15%  JSON-LD + og coverage (core pages)
    ai_readiness    10%  llms.txt + brand-facts present+fresh
    links           10%  broken internal links + orphans
    perf             5%  page weight flags

    `class_counts` are the TRUE per-class issue tallies (uncapped) — using the
    capped display list here would let the score plateau once _MAX_ISSUES is hit.
    """

    def _count(*classes: str) -> int:
        return sum(class_counts.get(c, 0) for c in classes)

    # --- technical (30%) ---
    technical = 100.0
    # sitemap parse + host
    if not sitemap_data.get("parse_ok"):
        technical -= 40
    else:
        bad_host = sitemap_data.get("bad_host_count", 0)
        apex_host = sitemap_data.get("apex_host_count", 0)
        orphans = len(sitemap_data.get("orphans_in_sitemap", []))
        if bad_host > 0:
            technical -= min(40, bad_host * 5)
        # Apex (non-www) host is a real but bounded technical debt (in-flight migration).
        if apex_host > 0:
            technical -= 10
        if orphans > 0:
            technical -= min(20, orphans * 2)
    # robots
    if not robots_data.get("robots_ok"):
        technical -= 10
    if _count("robots_blocks_all") > 0:
        technical -= 30
    if not robots_data.get("robots_sitemap_host_ok"):
        technical -= 5
    # canonical wrong-host critical issues
    critical_canonical = _count("canonical_wrong_host")
    if critical_canonical > 0:
        # Proportion-based penalty
        total_non_stocks = max(1, len(non_stocks_pages))
        pct_bad = critical_canonical / total_non_stocks
        technical -= pct_bad * 30
    technical = max(0.0, min(100.0, technical))

    # --- on_page (30%) ---
    on_page = 100.0
    core_n = max(1, len(core_pages))
    missing_title_core = _count("missing_title")
    missing_desc_core = _count("missing_description")
    dup_titles = _count("duplicate_title")
    title_len_issues = _count("title_length")
    desc_len_issues = _count("desc_length")

    on_page -= (missing_title_core / core_n) * 40
    on_page -= (missing_desc_core / core_n) * 40
    on_page -= min(10, dup_titles * 2)
    on_page -= min(10, (title_len_issues + desc_len_issues))
    on_page = max(0.0, min(100.0, on_page))

    # --- structured_data (15%) ---
    structured_data = 100.0
    core_census = census_by_family.get("core", {})
    core_total = max(1, core_census.get("pages", 1))
    with_og = core_census.get("with_og", 0) or 0
    with_jsonld = core_census.get("with_jsonld", 0) or 0
    og_coverage = with_og / core_total
    jsonld_coverage = with_jsonld / core_total
    # OG coverage weight 60%, JSON-LD 40%
    structured_data = (og_coverage * 60 + jsonld_coverage * 40)
    jsonld_errors = _count("jsonld_parse_error")
    structured_data -= min(20, jsonld_errors * 5)
    structured_data = max(0.0, min(100.0, structured_data))

    # --- ai_readiness (10%) ---
    ai_readiness = 0.0
    if llms_present:
        ai_readiness += 50.0
    if brand_facts.get("present") and brand_facts.get("parses"):
        age = brand_facts.get("age_days")
        if age is None or age <= _BRAND_FACTS_STALE_DAYS:
            ai_readiness += 50.0
        else:
            ai_readiness += 25.0  # present but stale

    # --- links (10%) ---
    links_score = 100.0
    broken_links = _count("broken_internal_link")
    orphans_count = len(sitemap_data.get("orphans_in_sitemap", []))
    links_score -= min(60, broken_links * 5)
    links_score -= min(30, orphans_count * 3)
    links_score = max(0.0, min(100.0, links_score))

    # --- perf (5%) ---
    perf = 100.0
    weight_flags = _count("page_weight")
    perf -= min(100, weight_flags * 10)
    perf = max(0.0, min(100.0, perf))

    # --- weighted sum ---
    score = (
        technical * 0.30 +
        on_page * 0.30 +
        structured_data * 0.15 +
        ai_readiness * 0.10 +
        links_score * 0.10 +
        perf * 0.05
    )
    return max(0, min(100, round(score)))


# ---------------------------------------------------------------------------
# Work orders builder
# ---------------------------------------------------------------------------


def _build_work_orders(audit: dict, as_of: str) -> dict:
    """Group issues into actionable work orders (max 20).

    Orders are grouped by class, sorted by severity then count.
    """
    from collections import defaultdict

    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    # Prefer the uncapped exemplars (one representative set per class, retained past the
    # display cap) so late-emitted classes (missing_from_sitemap, sitemap_apex_host) still
    # get orders. Fall back to the display issues list for older audits without exemplars.
    exemplars = audit.get("_class_exemplars")
    true_counts = audit.get("issue_counts_by_class", {})
    by_class: dict[str, list[dict]] = defaultdict(list)
    if exemplars:
        for cls, iss_list in exemplars.items():
            by_class[cls] = list(iss_list)
    else:
        for iss in audit.get("issues", []):
            by_class[iss["class"]].append(iss)

    # Class metadata for suggested fixes
    _FIX_MAP: dict[str, tuple[str, str]] = {
        "canonical_wrong_host": (
            "Fix canonical host to match SITE_BASE",
            "grep canonical in template; assert href starts with SITE_BASE"
        ),
        "canonical_non_www": (
            "Migrate canonical tags from non-www to www host",
            "After migration: grep canonical in site/ — zero non-www hits"
        ),
        "canonical_not_self": (
            "Ensure canonical href matches the page's own URL",
            "Load page; canonical URL in <head> should match page URL"
        ),
        "missing_canonical": (
            "Add rel=canonical to all public pages",
            "Check page in browser: view-source should show rel=canonical in <head>"
        ),
        "missing_title": (
            "Add <title> element to pages",
            "grep '<title' on each affected page — should return a non-empty match"
        ),
        "title_length": (
            "Adjust title length to 15-70 chars",
            "Measure len(title) for each page; assert 15 <= len <= 70"
        ),
        "duplicate_title": (
            "Make titles unique across pages",
            "Run duplicate-title check: zero duplicates expected"
        ),
        "missing_description": (
            "Add meta description to all core pages",
            "grep 'name=.description' in page source — should be present"
        ),
        "desc_length": (
            "Adjust description length to 50-170 chars",
            "Measure len(desc) for each page; assert 50 <= len <= 170"
        ),
        "duplicate_description": (
            "Make meta descriptions unique across pages",
            "Run duplicate-desc check: zero duplicates expected"
        ),
        "missing_og": (
            "Add og:title, og:description, og:image to all pages",
            "Open Graph debugger or grep meta property=og: — all three present"
        ),
        "jsonld_parse_error": (
            "Fix malformed JSON-LD blocks",
            "json.loads() on each JSON-LD block must succeed"
        ),
        "missing_lang": (
            "Add lang attribute to <html> element",
            "grep '<html' in page — should include lang= attribute"
        ),
        "broken_internal_link": (
            "Fix broken internal .html links",
            "Crawl internal links: zero 404s expected"
        ),
        "sitemap_orphan": (
            "Remove sitemap entries pointing to missing files",
            "Every sitemap <loc> URL must resolve to an existing file"
        ),
        "sitemap_bad_host": (
            "Fix sitemap entries with invalid host",
            "All sitemap <loc> entries must use the canonical host"
        ),
        "sitemap_apex_host": (
            "Migrate sitemap <loc> entries from apex to www canonical host",
            "grep <loc> in sitemap.xml — every URL starts with https://www.mastermind-x.com/"
        ),
        "robots_sitemap_apex_host": (
            "Migrate robots.txt Sitemap: directive to www canonical host",
            "robots.txt Sitemap line starts with https://www.mastermind-x.com/"
        ),
        "robots_sitemap_wrong_host": (
            "Fix robots.txt Sitemap: directive host (foreign host)",
            "robots.txt Sitemap line uses the canonical https://www.mastermind-x.com/ host"
        ),
        "sitemap_duplicates": (
            "Remove duplicate <loc> entries from sitemap",
            "sitemap.xml: each URL appears exactly once"
        ),
        "missing_from_sitemap": (
            "Add public pages to sitemap",
            "Run sitemap audit: zero public pages missing"
        ),
        "robots_blocks_all": (
            "Fix robots.txt — remove Disallow: /",
            "robots.txt: no Disallow: / for User-agent: *"
        ),
        "robots_no_sitemap": (
            "Add Sitemap: directive to robots.txt",
            "robots.txt: contains Sitemap: https://... line"
        ),
        "missing_llms_txt": (
            "Create llms.txt for AI search readiness",
            "site/llms.txt exists and is accessible"
        ),
        "missing_brand_facts": (
            "Create brand-facts.json with effective_at timestamp",
            "site/brand-facts.json present and effective_at within 90 days"
        ),
        "brand_facts_stale": (
            "Refresh brand-facts.json (>90 days stale)",
            "effective_at in brand-facts.json is within 90 days"
        ),
        "page_weight": (
            "Reduce HTML page weight to <2.5 MB",
            "wc -c site/<page>.html < 2621440 bytes"
        ),
    }

    def _true_count(cls: str, iss_list: list[dict]) -> int:
        # Prefer the uncapped tally; fall back to the exemplar/display list length.
        return true_counts.get(cls, len(iss_list))

    orders: list[dict] = []
    for cls, iss_list in sorted(
        by_class.items(),
        key=lambda kv: (
            sev_rank.get(min((i["severity"] for i in kv[1]), key=lambda s: sev_rank.get(s, 99)), 99),
            -_true_count(kv[0], kv[1]),
            kv[0],  # stable, deterministic tiebreak on class name
        ),
    ):
        top_sev = min((i["severity"] for i in iss_list), key=lambda s: sev_rank.get(s, 99))
        pages_sample = [i["page"] for i in iss_list[:_MAX_PAGES_IN_ORDER]]
        total_count = _true_count(cls, iss_list)
        fix_title, falsifiable = _FIX_MAP.get(cls, (f"Fix {cls} issues", f"Zero {cls} issues in next audit"))
        orders.append({
            "id": cls,
            "priority": len(orders) + 1,
            "title": fix_title,
            "class": cls,
            "severity": top_sev,
            "pages": pages_sample,
            "pages_count": total_count,
            "suggested_fix": fix_title,
            "falsifiable_check": falsifiable,
        })
        if len(orders) >= _MAX_WORK_ORDERS:
            break

    return {
        "schema": "seo_work_orders.v1",
        "as_of": as_of,
        "orders": orders,
    }


# ---------------------------------------------------------------------------
# Scorecard + history
# ---------------------------------------------------------------------------


def _count_by_severity(issues: list[dict]) -> dict:
    counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for iss in issues:
        sev = iss.get("severity", "low")
        counts[sev] = counts.get(sev, 0) + 1
    return counts


def _load_prior_scorecard(seo_dir: Path) -> dict | None:
    p = seo_dir / _SCORECARD_FILE
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _build_scorecard(audit: dict, prior: dict | None) -> dict:
    as_of = audit["as_of"]
    health = audit["health_score"]
    # Prefer the TRUE (uncapped) severity tallies; fall back to counting the display
    # list only for audits produced before the honest-count field existed.
    sev_counts = audit.get("issue_counts_by_severity") or _count_by_severity(audit.get("issues", []))

    deltas = None
    if prior:
        prior_health = prior.get("health_score")
        prior_counts = prior.get("issue_counts_by_severity", {})
        deltas = {
            "health_score": (health - prior_health) if prior_health is not None else None,
            "critical": sev_counts["critical"] - prior_counts.get("critical", 0),
            "high": sev_counts["high"] - prior_counts.get("high", 0),
            "medium": sev_counts["medium"] - prior_counts.get("medium", 0),
            "low": sev_counts["low"] - prior_counts.get("low", 0),
        }

    return {
        "schema": "seo_scorecard.v1",
        "as_of": as_of,
        "health_score": health,
        "issue_counts_by_severity": sev_counts,
        "deltas_vs_prior": deltas,
        "families_summary": audit["census"]["by_family"],
    }


def _build_history_line(audit: dict) -> dict:
    sev_counts = audit.get("issue_counts_by_severity") or _count_by_severity(audit.get("issues", []))
    return {
        "as_of": audit["as_of"],
        "health_score": audit["health_score"],
        "issues": sev_counts,
        "total_pages": audit["census"]["total_pages"],
    }


# ---------------------------------------------------------------------------
# Top-level run()
# ---------------------------------------------------------------------------


def run(root: Path, *, as_of: datetime | None = None, write: bool = True) -> dict:
    """Full audit cycle: read root/site, optionally write artifacts under root/data/marketing/seo/.

    Args:
        root:   Repo root path.
        as_of:  Audit timestamp (default: now UTC).
        write:  If True, write all four artifact files.

    Returns:
        seo_audit dict.
    """
    site_dir = root / "site"
    seo_dir = root / _ARTIFACTS_REL

    audit = audit_site(site_dir, as_of=as_of)
    work_orders = _build_work_orders(audit, audit["as_of"])

    prior_scorecard = _load_prior_scorecard(seo_dir) if write else None
    scorecard = _build_scorecard(audit, prior_scorecard)
    history_line = _build_history_line(audit)

    if write:
        try:
            # Persist only the public v1 contract — underscore keys (e.g.
            # _class_exemplars) are in-memory working state, not artifact schema.
            persisted = {k: v for k, v in audit.items() if not k.startswith("_")}
            _write_json_atomic(seo_dir / _AUDIT_FILE, persisted)
            _write_json_atomic(seo_dir / _WORK_ORDERS_FILE, work_orders)
            _write_json_atomic(seo_dir / _SCORECARD_FILE, scorecard)
            _append_jsonl(seo_dir / _HISTORY_FILE, history_line)
        except Exception as exc:  # noqa: BLE001
            log.error("seo_director: artifact write failed: %s", exc)

    return audit


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_summary(audit: dict) -> None:
    health = audit["health_score"]
    sev = _count_by_severity(audit.get("issues", []))
    census = audit["census"]
    print(f"\n=== SEO Director Audit ===")
    print(f"as_of      : {audit['as_of']}")
    print(f"health     : {health}/100")
    print(f"total pages: {census['total_pages']}")
    print(f"issues     : critical={sev['critical']} high={sev['high']} "
          f"medium={sev['medium']} low={sev['low']}")
    print()
    print(f"{'Family':<12} {'pages':>6} {'canonical':>9} {'desc':>6} {'og':>6} {'jsonld':>7} {'in_sm':>7}")
    print("-" * 60)
    for fam, data in census["by_family"].items():
        if not isinstance(data, dict):
            continue
        pages = data.get("pages", "?")
        can = data.get("with_canonical", "-")
        desc = data.get("with_desc", "-")
        og = data.get("with_og", "-")
        jld = data.get("with_jsonld", "-")
        insm = data.get("in_sitemap", "-")
        print(f"{fam:<12} {str(pages):>6} {str(can):>9} {str(desc):>6} {str(og):>6} {str(jld):>7} {str(insm):>7}")
    print()
    sm_block = audit["sitemap"]
    print("Sitemap :", sm_block["total_urls"], "URLs,",
          "host_ok:", sm_block.get("host_ok"),
          "apex_host:", sm_block.get("apex_host_count", 0),
          "orphans:", len(sm_block["orphans_in_sitemap"]),
          "missing_from_sm:", sm_block.get("missing_from_sitemap_count",
                                           len(sm_block["missing_from_sitemap"])),
          f"(showing {len(sm_block['missing_from_sitemap'])})")
    if audit.get("_issues_truncated_count"):
        print(f"NOTE: {audit['_issues_truncated_count']} issues truncated from display "
              f"(health score + counts use TRUE totals)")
    ci = audit["crawl_infra"]
    print("Infra   :", "robots_ok=" + str(ci["robots_ok"]),
          "llms.txt=" + str(ci["llms_txt_present"]),
          "brand-facts=" + str(ci["brand_facts_present"]),
          "bf_age=" + str(ci.get("brand_facts_age_days", "n/a")) + "d")

    # Emit ::warning:: for critical issues
    for iss in audit.get("issues", []):
        if iss["severity"] == "critical":
            print(f"::warning:: [SEO critical] {iss['class']} on {iss['page']}: {iss['detail']}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="SEO Director — weekly offline site audit")
    parser.add_argument("--root", default=".", help="Repo root (default: .)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Audit without writing artifacts")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        audit = run(root, write=not args.dry_run)
        _print_summary(audit)
    except Exception as exc:  # noqa: BLE001
        print(f"::error:: seo_director crashed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
