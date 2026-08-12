"""scripts/build_product_page_registry.py — cross-repo user-visible page census.

One JSON row per user-visible route (or route FAMILY) across the three product
repos: `macro` (this static site), `terminal`
(/Users/chriswong/Documents/Cluade/charting-app, Next.js App Router) and
`mastermind` (/Users/chriswong/Documents/Cluade/Mastermind, FastAPI).

CONTRACT — every fact in a row is DERIVED from a file in one of those repos and
cites it in `source_evidence`, or is supplied by the hand-maintained overlay
`config/product_experience/page_registry_overrides.yml`, or is the literal
string "unknown".  Nothing is guessed.  "unknown" is a first-class value: a
census whose gaps are visible is worth more than one that fills them in.

Judgment fields (priority, archetype, primary_user_question, owner) are NEVER
derived — they come from the overrides file or keep their unclassified default.

Derivation sources
------------------
macro       git-tracked ``site/**/*.html`` (the shipped inventory — site/ is
            committed even though the working tree here is sparse), attributed
            to builders/templates by an AST scan of ``write_page()`` call sites
            in ``scripts/*.py``; nav membership from
            ``templates/_navlinks.html.j2`` + ``templates/_public_nav.html.j2``
            + ``templates/_public_footer.html.j2``;
            serving tiers from ``config/site_access.yml``; hand-authored pages
            from ``lib/pages.py``; sitemap exclusions from ``lib/seo.py``.
terminal    ``terminal/app/**/page.tsx`` read from a git REF (default
            origin/master — the disk checkout is routinely stale), nav from
            ``terminal/components/AppNav.tsx``, gates from per-page markers.
mastermind  ``@router.get(...)`` handlers in ``app/web.py`` that return an HTML
            ``FileResponse``.

A missing sister repo is never fatal: its `sources` entry records
``available: false`` and no rows are emitted for it.

Usage::

    python3 scripts/build_product_page_registry.py --as-of 2026-08-11T00:00:00Z
    python3 scripts/build_product_page_registry.py --check      # CI drift guard
    python3 scripts/build_product_page_registry.py --with-prs   # one gh call

Runtime is a few seconds without ``--with-prs``; stdlib + PyYAML only, no
network, no browser.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import yaml

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = "mastermind.page_registry.v1"
UNKNOWN = "unknown"

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "data" / "product_experience" / "page_registry.json"
DEFAULT_OVERRIDES = (
    REPO_ROOT / "config" / "product_experience" / "page_registry_overrides.yml"
)
DEFAULT_TERMINAL_ROOT = Path("/Users/chriswong/Documents/Cluade/charting-app")
DEFAULT_MASTERMIND_ROOT = Path("/Users/chriswong/Documents/Cluade/Mastermind")

# Field order is part of the artifact: rows are emitted with these keys, in this
# order, ALWAYS all of them.  A reader may therefore index a row without
# defaulting, and a diff of the JSON is a diff of facts rather than of layout.
FIELD_ORDER: tuple[str, ...] = (
    "page_id", "repo", "route", "route_kind", "source_template", "builder",
    "data_sources", "access_shell", "payload_tier", "nav_family", "archetype",
    "primary_user_question", "owner", "lifecycle", "priority", "generated",
    "bilingual", "themes", "locales", "known_contracts", "open_prs",
    "source_evidence", "notes",
)

REPOS = ("macro", "terminal", "mastermind")
ROUTE_KINDS = ("page", "family")
ACCESS_SHELLS = ("anonymous", "signed_in", "paid", "admin", "operator", UNKNOWN)
PAYLOAD_TIERS = ("public", "public_shell_premium_payload", "premium", "internal",
                 UNKNOWN)
LIFECYCLES = ("live", "lab", "internal", "parked", "dev_only", UNKNOWN)
PRIORITIES = ("P0", "P1", "P2", "P3", "unclassified")

# Fields the overrides overlay may set.  Judgment fields plus the access facts
# that no static reader can honestly derive (a gate enforced in middleware, a
# guest mode, an entitlement resolved at request time).  Everything else is
# derived-only, so an override can never quietly fabricate a builder or a route.
OVERRIDABLE: frozenset[str] = frozenset({
    "priority", "archetype", "primary_user_question", "owner", "lifecycle",
    "access_shell", "payload_tier", "nav_family", "bilingual", "themes",
    "locales", "known_contracts", "data_sources",
})
# Extra keys an override entry may carry that are not registry fields.
OVERRIDE_META: frozenset[str] = frozenset({"evidence", "note", "why"})

LIST_OR_UNKNOWN = ("themes", "locales")
ALWAYS_LIST = ("data_sources", "builder", "known_contracts", "open_prs",
               "source_evidence", "notes")


def blank_row(page_id: str, repo: str, route: str) -> dict[str, Any]:
    """A row with every field present at its honest default."""
    return {
        "page_id": page_id,
        "repo": repo,
        "route": route,
        "route_kind": "page",
        "source_template": UNKNOWN,
        "builder": [],
        "data_sources": [],
        "access_shell": UNKNOWN,
        "payload_tier": UNKNOWN,
        "nav_family": UNKNOWN,
        "archetype": "unclassified",
        "primary_user_question": "",
        "owner": "unowned",
        "lifecycle": UNKNOWN,
        "priority": "unclassified",
        "generated": UNKNOWN,
        "bilingual": UNKNOWN,
        "themes": UNKNOWN,
        "locales": UNKNOWN,
        "known_contracts": [],
        "open_prs": [],
        "source_evidence": [],
        "notes": [],
    }


def annotate(msg: str, *, title: str = "page-registry", level: str = "error") -> None:
    """Emit a GitHub Actions annotation.

    Bare ``print`` on purpose: a logger prefixes the line and GitHub silently
    drops any annotation that does not START the line (house law, CLAUDE.md).
    """
    print(f"::{level} title={title}::{msg}", flush=True)


# ---------------------------------------------------------------------------
# git plumbing (injectable so tests never touch a real repo)
# ---------------------------------------------------------------------------

GitRunner = Callable[[Path, list[str]], Optional[str]]


def run_git(root: Path, args: list[str]) -> Optional[str]:
    """Run ``git <args>`` in ``root``; return stdout, or None on any failure."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(root), capture_output=True, timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# macro — shared readers
# ---------------------------------------------------------------------------

def _literal_collection(path: Path, name: str) -> list[str]:
    """Read a module-level frozenset/set/list/tuple of string literals by name.

    Parsed, never imported: importing a builder module pulls jinja2/pandas and
    can execute config loading, neither of which a census may depend on.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return []
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        elif isinstance(node, ast.AnnAssign):
            target = node.target
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        value = node.value
        if isinstance(value, ast.Call) and value.args:  # frozenset({...})
            value = value.args[0]
        if isinstance(value, (ast.Set, ast.List, ast.Tuple)):
            return [e.value for e in value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []


def _load_site_access(path: Path) -> dict[str, Any]:
    """Parse config/site_access.yml into the buckets the census needs."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    out: dict[str, Any] = {}
    for bucket in ("public", "free_registered", "deny"):
        section = raw.get(bucket) or {}
        out[bucket] = {
            "exact": set(section.get("exact") or []),
            "prefixes": tuple(section.get("prefixes") or []),
        }
    premium = ((raw.get("premium") or {}).get("enforced_early") or {})
    out["premium_early"] = {
        "exact": set(premium.get("exact") or []),
        "prefixes": tuple(premium.get("prefixes") or []),
    }
    return out


def _in_bucket(route: str, bucket: dict[str, Any]) -> bool:
    if route in bucket["exact"]:
        return True
    return any(route.startswith(p) for p in bucket["prefixes"])


# --- nav ---------------------------------------------------------------------

_HREF_RE = re.compile(r'href="([^"]*)"')
_NAV_LINK_RE = re.compile(r'class="nav-link[^"]*"')
_NAV_GROUP_LABEL_RE = re.compile(r"t\(\s*'([^']+)'")
_TEMPLATE_VAR_RE = re.compile(r"\{\{[^}]*\}\}")
# A footer COLUMN heading is a bare ``<p>…</p>``; the brand tagline carries a
# class (``<p class="ft">``) and so is not one.
_FOOTER_HEADING_RE = re.compile(r"<p>\s*(.*?)\s*</p>")


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def _normalize_href(href: str) -> Optional[str]:
    """Site-root-relative route for a nav href, or None if it is not a page."""
    href = _TEMPLATE_VAR_RE.sub("", href).strip()
    if not href or href.startswith(("http", "//", "javascript:", "mailto:", "#")):
        return None
    href = href.split("#", 1)[0].split("?", 1)[0]
    if not href.endswith(".html"):
        return None
    return "/" + href.lstrip("./")


def parse_nav(text: str, *, group_prefix: str) -> dict[str, str]:
    """Map route -> ``<group_prefix>.<group_slug>`` for one nav template.

    The nav templates are written top-down: a top-level ``nav-link`` opens a
    group and every href after it belongs to that group until the next one.
    Reading the structure rather than a hand-kept list is the point — a nav
    edit moves the registry with it.
    """
    families: dict[str, str] = {}
    group = "brand"
    for line in text.splitlines():
        if _NAV_LINK_RE.search(line):
            label = _NAV_GROUP_LABEL_RE.search(line)
            if label:
                group = _slugify(label.group(1))
        for href in _HREF_RE.findall(line):
            route = _normalize_href(href)
            if route:
                families.setdefault(route, f"{group_prefix}.{group}")
    return families


def parse_public_nav(text: str, *, group_prefix: str) -> dict[str, str]:
    """Map route -> family for the anonymous/corporate nav.

    The public chrome is a flat link list with no per-group ``nav-link``
    trigger, so every route it names lands in one family.
    """
    families: dict[str, str] = {}
    for href in _HREF_RE.findall(text):
        route = _normalize_href(href)
        if route:
            families.setdefault(route, f"{group_prefix}.public")
    return families


def parse_footer(text: str, *, group_prefix: str) -> dict[str, str]:
    """Map route -> ``<group_prefix>.<column_slug>`` for the public footer.

    The footer is written per COLUMN: a ``<div class="f-col">`` opens with a
    bare heading paragraph (``<p>{{ t('Legal', '法律') }}</p>``) and every href
    after it belongs to that column until the next heading.  The ``f-bot`` strip
    repeats privacy/terms/disclaimer under no heading at all, so FIRST
    occurrence wins and those routes keep the Legal column that named them —
    the same ``setdefault`` rule the two nav parsers use.

    The footer is a real link inventory, not decoration: five live pages
    (about, about-research, privacy, terms, disclaimer) are reachable ONLY from
    here, and reading nothing but the two navs reported them as orphans.
    """
    families: dict[str, str] = {}
    group = "brand"
    for line in text.splitlines():
        heading = _FOOTER_HEADING_RE.search(line)
        if heading:
            label = _NAV_GROUP_LABEL_RE.search(heading.group(1))
            slug = _slugify(label.group(1) if label
                            else _TEMPLATE_VAR_RE.sub("", heading.group(1)))
            if slug:
                group = slug
        for href in _HREF_RE.findall(line):
            route = _normalize_href(href)
            if route:
                families.setdefault(route, f"{group_prefix}.{group}")
    return families


# --- builder / template attribution -----------------------------------------

class _WriteSite:
    """One resolved ``write_page()`` call: what route, from what template."""

    __slots__ = ("route", "is_family", "builder", "template", "line")

    def __init__(self, route: str, is_family: bool, builder: str,
                 template: Optional[str], line: int) -> None:
        self.route = route
        self.is_family = is_family
        self.builder = builder
        self.template = template
        self.line = line


# Base expressions that denote the site root.  Census-verified against every
# write_page() call in scripts/ — anything else stays UNRESOLVED rather than
# being assumed to be the site root (a wrong base invents a route).
_SITE_ROOT_BASES = frozenset({"site", "site_dir", "site_root", "_SITE", "SITE"})


def _is_site_root(expr: str) -> bool:
    """True when a path expression's base is the rendered site root."""
    return expr in _SITE_ROOT_BASES or "site_dir" in expr
_TEMPLATE_CALL_RE = re.compile(r"""get_template\(\s*['"]([\w.\-/]+\.html\.j2)['"]""")


def _assign_map(tree: ast.AST) -> dict[str, str]:
    """name -> unparsed value, only for names assigned exactly once.

    A name assigned twice (``outdir`` is ``site/"stockdata"`` in one function
    and ``site/"sectors"`` in another) is AMBIGUOUS and stays unresolved: the
    wrong branch would mint a route that does not exist.
    """
    seen: dict[str, set[str]] = defaultdict(set)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    seen[target.id].add(ast.unparse(node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.value is not None:
            seen[node.target.id].add(ast.unparse(node.value))
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def _placeholder(expr: str) -> str:
    """``f'{sub['key']}.html'`` -> ``<key>`` — a family's variable segment."""
    idents = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr)
    skip = {"f", "html", "str", "int", "Path", "slug_of"}
    for ident in reversed(idents):
        if ident not in skip:
            return f"<{ident}>"
    return "<id>"


def _resolve_path_expr(expr: str, names: dict[str, str]) -> Optional[tuple[str, bool]]:
    """Resolve a write_page() path expression to ``(route, is_family)``.

    Returns None when the expression cannot be anchored at the site root.
    Unresolved sites are counted, not guessed at.
    """
    for _ in range(5):
        base = expr.split(" / ")[0]
        if _is_site_root(base):
            break
        replacement = names.get(base)
        if not replacement or replacement == base:
            break
        expr = replacement + expr[len(base):]

    parts = [p.strip() for p in expr.split(" / ")]
    # Anchor on an explicit ``'site'`` segment (config.ROOT / 'site' / …,
    # _REPO_ROOT / 'site' / …, and the `X if args.x else …` ternary forms) or on
    # a known site-root base expression.
    anchor = None
    for i, part in enumerate(parts):
        if part in ("'site'", '"site"'):
            anchor = i + 1
            break
    if anchor is None:
        if not _is_site_root(parts[0]):
            return None
        anchor = 1

    segments: list[str] = []
    is_family = False
    tail = len(parts) - 1
    for i, part in enumerate(parts[anchor:], start=anchor):
        resolved = names.get(part, part) if re.fullmatch(r"\w+", part) else part
        literal = re.fullmatch(r"""['"]([^'"]*)['"]""", resolved)
        if literal:
            segments.append(literal.group(1))
            continue
        is_family = True
        # An f-string keeps its constant head: f'strategy_{k}.html' is the
        # family /strategy_<k>.html, not an opaque wildcard.
        fstr = re.fullmatch(r"""f['"](.*)['"]""", resolved, re.S)
        if fstr:
            body = fstr.group(1)
            rebuilt = ""
            for chunk in re.split(r"(\{[^{}]*\})", body):
                rebuilt += _placeholder(chunk[1:-1]) if chunk.startswith("{") \
                    else chunk
            segments.append(rebuilt)
        else:
            # Only the final segment is a page; a dynamic DIRECTORY segment
            # (build_theme_detail's per-region out_dir) keeps no .html suffix.
            segments.append(_placeholder(resolved) + (".html" if i == tail else ""))
    if not segments or not segments[-1].endswith(".html"):
        return None
    return "/" + "/".join(segments), is_family


def scan_write_sites(scripts_dir: Path) -> tuple[list[_WriteSite], list[tuple[str, str]]]:
    """AST-scan every builder for ``write_page()`` calls.

    Returns (resolved sites, unresolved ``(file, expression)`` pairs).  The
    unresolved list is reported as a coverage gap rather than swept away.
    """
    sites: list[_WriteSite] = []
    unresolved: list[tuple[str, str]] = []
    if not scripts_dir.is_dir():
        return sites, unresolved
    for path in sorted(scripts_dir.glob("*.py")):
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        names = _assign_map(tree)
        # name -> the template it renders, for `tmpl = env.get_template(...)`
        # followed by `write_page(out, tmpl.render(...))`.
        rendered: dict[str, str] = {}
        for name, expr in names.items():
            found = _TEMPLATE_CALL_RE.search(expr)
            if found:
                rendered[name] = found.group(1)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "write_page" and node.args):
                continue
            resolved = _resolve_path_expr(ast.unparse(node.args[0]), names)
            if resolved is None:
                unresolved.append((path.name, ast.unparse(node.args[0])))
                continue
            route, is_family = resolved
            template = None
            call_text = ast.unparse(node)
            found = _TEMPLATE_CALL_RE.search(call_text)
            if found:
                template = found.group(1)
            else:
                for name in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", call_text):
                    if name in rendered:
                        template = rendered[name]
                        break
                    hop = names.get(name)
                    if hop:
                        hop_names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", hop)
                        hit = next((h for h in hop_names if h in rendered), None)
                        if hit:
                            template = rendered[hit]
                            break
            sites.append(_WriteSite(route, is_family,
                                    f"scripts/{path.name}", template, node.lineno))
    return sites, unresolved


# --- bilingual / theme chrome ------------------------------------------------

_EXTENDS_RE = re.compile(r"""\{%-?\s*(?:extends|include|import|from)\s+['"]([^'"]+)['"]""")


def _template_chrome(templates_dir: Path, name: str, _depth: int = 0) -> str:
    """Concatenated text of a template and the partials it pulls in (depth 3)."""
    path = templates_dir / name
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if _depth >= 3:
        return text
    for ref in dict.fromkeys(_EXTENDS_RE.findall(text)):
        if ref != name:
            text += _template_chrome(templates_dir, ref, _depth + 1)
    return text


def _chrome_facts(text: str) -> tuple[Any, Any, Any]:
    """(bilingual, themes, locales) from a template's own bytes."""
    if not text:
        return UNKNOWN, UNKNOWN, UNKNOWN
    bilingual = bool(
        re.search(r"\bt\(\s*['\"]", text)
        or "data-lang" in text
        or "_navlinks.html.j2" in text
        or "_site_nav.html.j2" in text
        or "_public_nav.html.j2" in text
    )
    themed = "data-theme" in text or "theme.js" in text
    return (
        bilingual,
        ["light", "dark"] if themed else UNKNOWN,
        ["en", "zh"] if bilingual else ["en"],
    )


# ---------------------------------------------------------------------------
# macro — row assembly
# ---------------------------------------------------------------------------

# Sitemap-excluded names whose exclusion is a LIFECYCLE fact rather than an SEO
# one.  lib/seo.py's own comments are the evidence: "_lab"/"_v2" pages are
# labelled "internal lab variant" / "staging variant"; the rest of
# _EXCLUDE_NAMES (watchlist, unsubscribe, stock lookups …) are live pages kept
# out of the sitemap for indexing reasons, so they stay `live`.
_LAB_SUFFIXES = ("_lab", "_v2")
_INTERNAL_NAMES = frozenset({"status", "mastermind", "validation_timeline",
                             "qa_bottom_sensors"})


def _family_pattern(route: str) -> Optional["re.Pattern[str]"]:
    """Regex for a root-level family route, or None when it is too broad.

    ``/fund_<slug>.html`` legitimately attributes site/fund_berkshire.html to
    build_smart_money; ``/<name>.html`` (a builder that writes whatever page it
    is handed) matches the whole site and proves nothing about any of it, so a
    pattern carrying fewer than 4 constant characters is refused.
    """
    if route.count("/") != 1 or "<" not in route or not route.endswith(".html"):
        return None
    body = route[1: -len(".html")]
    if len(re.sub(r"<[^>]*>", "", body)) < 4:
        return None
    pattern = "".join(
        "[^/]*" if part.startswith("<") else re.escape(part)
        for part in re.split(r"(<[^>]*>)", body) if part
    )
    return re.compile(rf"^/{pattern}\.html$")


def _macro_page_id(route: str, *, family: bool = False) -> str:
    stem = route.lstrip("/")
    if stem.endswith(".html"):
        stem = stem[: -len(".html")]
    if family:
        stem = re.sub(r"<[^>]*>", "", stem).strip("_/")
        return "macro:" + (_slugify(stem) or "root") + "_family"
    return "macro:" + (_slugify(stem) or "index")


def derive_macro(root: Path, *, site_dir: Optional[Path] = None,
                 git: GitRunner = run_git) -> tuple[list[dict], dict]:
    """Rows + provenance for this repo's static site."""
    source: dict[str, Any] = {"available": True, "root": str(root)}
    head = git(root, ["rev-parse", "HEAD"])
    source["ref"] = "HEAD"
    source["sha"] = head.strip() if head else UNKNOWN

    listing = git(root, ["ls-files", "site/*.html"])
    tracked = [ln for ln in (listing or "").splitlines() if ln.endswith(".html")]
    if tracked:
        source["page_inventory"] = "git ls-files site/*.html"
    elif site_dir and site_dir.is_dir():
        tracked = sorted(
            "site/" + str(p.relative_to(site_dir)).replace("\\", "/")
            for p in site_dir.rglob("*.html")
        )
        source["page_inventory"] = f"--site-dir {site_dir}"
    else:
        source["page_inventory"] = "write_page() call sites only"
    source["tracked_html_pages"] = len(tracked)

    sites, unresolved = scan_write_sites(root / "scripts")
    source["write_page_sites"] = len(sites)
    source["write_page_unresolved"] = len(unresolved)

    by_route: dict[str, list[_WriteSite]] = defaultdict(list)
    for site in sites:
        by_route[site.route].append(site)

    templates_dir = root / "templates"
    nav = parse_nav(_read(templates_dir / "_navlinks.html.j2"),
                    group_prefix="product_nav")
    public_nav = parse_public_nav(_read(templates_dir / "_public_nav.html.j2"),
                                 group_prefix="public_nav")
    footer = parse_footer(_read(templates_dir / "_public_footer.html.j2"),
                          group_prefix="footer")
    access = _load_site_access(root / "config" / "site_access.yml")
    hand_authored = set(_literal_collection(root / "lib" / "pages.py",
                                            "HAND_AUTHORED_PAGES"))
    excluded = set(_literal_collection(root / "lib" / "seo.py", "_EXCLUDE_NAMES"))
    exclude_prefixes = tuple(_literal_collection(root / "lib" / "seo.py",
                                                 "_EXCLUDE_PREFIXES"))

    root_pages = sorted({p for p in tracked if p.count("/") == 1})
    # A sub-directory page gets its OWN row when it is a family hub
    # (<dir>/index.html) or a named hand-authored page; everything else folds
    # into one family row so the census stays readable at 4,500 pages.
    named_subpages: list[str] = []
    families: dict[str, list[str]] = defaultdict(list)
    for page in tracked:
        if page.count("/") == 1:
            continue
        rel = page.split("/", 1)[1]
        if rel in hand_authored or (page.count("/") == 2
                                    and page.endswith("/index.html")):
            named_subpages.append(page)
        else:
            families[page.split("/")[1]].append(page)
    # A route a builder writes but the committed tree does not hold is still a
    # route; keep it rather than losing the builder's own statement.
    for route, group in by_route.items():
        if not group[0].is_family and route.count("/") == 1:
            candidate = "site" + route
            if candidate not in root_pages:
                root_pages.append(candidate)
    root_pages = sorted(set(root_pages))

    family_patterns = [(pattern, site) for site in sites
                       if (pattern := _family_pattern(site.route)) is not None]

    rows: list[dict] = []
    tracked_set = set(tracked)
    for page in root_pages + sorted(named_subpages):
        name = page.split("/", 1)[1]
        stem = name[: -len(".html")]
        route = "/" if name == "index.html" else "/" + name
        row = blank_row(_macro_page_id(route), "macro", route)
        writes = by_route.get("/" + name, [])
        via_family = False
        if not writes:
            writes = [s for pattern, s in family_patterns if pattern.match("/" + name)]
            via_family = bool(writes)
        _fill_macro_common(row, site_dir, templates_dir, stem, name, route, writes,
                           access, nav, public_nav, footer, hand_authored, excluded,
                           exclude_prefixes, tracked_page=page in tracked_set,
                           via_family=via_family)
        rows.append(row)

    for directory, members in sorted(families.items()):
        if not members:  # every page in the directory already has its own row
            continue
        fam_writes = [s for s in sites
                      if s.is_family and s.route.startswith(f"/{directory}/")]
        param = "<id>"
        if fam_writes:
            tail = fam_writes[0].route.rsplit("/", 1)[-1]
            found = re.search(r"<[^>]*>", tail)
            if found:
                param = found.group(0)
        route = f"/{directory}/{param}.html"
        row = blank_row(_macro_page_id(route, family=True), "macro", route)
        templates = sorted({s.template for s in fam_writes if s.template})
        chrome = _template_chrome(templates_dir, templates[0]) if templates else ""
        row["route_kind"] = "family"
        row["access_shell"] = "anonymous"
        row["payload_tier"] = _macro_payload_tier(f"/{directory}/", access,
                                                  chrome=chrome)
        row["nav_family"] = nav.get(f"/{directory}/index.html") \
            or public_nav.get(f"/{directory}/index.html") \
            or footer.get(f"/{directory}/index.html") or "none"
        row["lifecycle"] = "live"
        row["builder"] = sorted({s.builder for s in fam_writes})
        row["generated"] = True if fam_writes else UNKNOWN
        if templates:
            row["source_template"] = f"templates/{templates[0]}"
            row["bilingual"], row["themes"], row["locales"] = _chrome_facts(chrome)
            row["source_evidence"].append(f"templates/{templates[0]}")
        if len(templates) > 1:
            row["notes"].append(
                "multiple templates render this family: "
                + ", ".join(f"templates/{t}" for t in templates))
        row["source_evidence"].append(f"site/{directory}/")
        row["source_evidence"].extend(f"{s.builder}:{s.line}" for s in fam_writes)
        row["notes"].append(f"{len(members)} committed pages under site/{directory}/")
        if not fam_writes:
            row["notes"].append(
                "no write_page() call site resolves to this directory; builder unknown")
        rows.append(row)

    # Ticker + basket families carry their gating rule in lib/pages.py; record it
    # where a reader of the row will see it.  lib/pages.py also NAMES the
    # generator for both, which is what makes `generated` knowable here.
    for row in rows:
        if row["page_id"] == "macro:stocks_family":
            row["known_contracts"].append(
                "lib/pages.py rendered_ticker_pages(): a stocks/<TICKER>.html "
                "page ships only for a membership ticker with a full stockdata blob")
            row["source_evidence"].append("lib/pages.py:129")
            row["generated"] = True
        if row["page_id"] == "macro:basket_family":
            row["known_contracts"].append(
                "lib/pages.py rendered_basket_pages(): a basket page ships only "
                "for a basket with >=3 members in the returns cache")
            row["source_evidence"].append("lib/pages.py:143")
            row["generated"] = True

    source["unresolved_write_sites"] = sorted(
        {f"scripts/{f}: {e}" for f, e in unresolved})[:40]
    return rows, source


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _macro_payload_tier(route: str, access: dict[str, Any], *, chrome: str) -> str:
    """Serving tier for a macro route.

    Every *.html SHELL has been anonymous since 2026-08-04 (config/site_access.yml
    header); what the policy still gates is the DATA payload.  So:
      deny            -> internal (404 even for an entitled user)
      public + premium payload referenced -> public_shell_premium_payload
      public          -> public
      anything else   -> public_shell_premium_payload (shell anonymous, payload
                         behind free_registered or the Insider+ default)
    """
    if not access:
        return UNKNOWN
    if _in_bucket(route, access["deny"]):
        return "internal"
    premium = access["premium_early"]
    references_premium = any(
        prefix in chrome for prefix in premium["prefixes"]
    ) or any(exact in chrome for exact in premium["exact"]) or "tier_preview" in chrome
    if _in_bucket(route, access["public"]):
        return "public_shell_premium_payload" if references_premium else "public"
    return "public_shell_premium_payload"


def _fill_macro_common(row: dict, site_dir: Optional[Path], templates_dir: Path, stem: str,
                       name: str, route: str, writes: list[_WriteSite],
                       access: dict[str, Any], nav: dict[str, str],
                       public_nav: dict[str, str], footer: dict[str, str],
                       hand_authored: set[str],
                       excluded: set[str], exclude_prefixes: Iterable[str],
                       *, tracked_page: bool, via_family: bool = False) -> None:
    lookup = "/" + name  # the access policy keys index.html by its file name
    templates = sorted({s.template for s in writes if s.template})
    if not templates and (templates_dir / f"{stem}.html.j2").is_file():
        templates = [f"{stem}.html.j2"]
        row["notes"].append(
            "template attributed by name match; no write_page() call site names it")
    chrome = _template_chrome(templates_dir, templates[0]) if templates else ""
    plain_copy = templates_dir / name  # a non-.j2 template/site byte-pair

    if name in hand_authored or (name == "index.html" and not writes):
        row["generated"] = False
        if name == "index.html" and (templates_dir / "index.html").is_file():
            row["source_template"] = "templates/index.html"
            chrome = _read(templates_dir / "index.html")
            row["source_evidence"].append("templates/index.html")
        else:
            row["source_template"] = f"site/{name}"
            row["notes"].append(
                "hand-authored page: the committed site file IS the source "
                "(lib/pages.py HAND_AUTHORED_PAGES)")
            row["source_evidence"].append("lib/pages.py:57")
            if site_dir and (site_dir / name).is_file():
                chrome = _read(site_dir / name)
    elif writes:
        row["generated"] = True
        row["builder"] = sorted({s.builder for s in writes})
        row["source_evidence"].extend(sorted(f"{s.builder}:{s.line}" for s in writes))
        if templates:
            row["source_template"] = f"templates/{templates[0]}"
        if len(templates) > 1:
            row["notes"].append(
                "multiple templates render this route: "
                + ", ".join(f"templates/{t}" for t in templates))
        if via_family:
            row["notes"].append(
                "attributed through the builder's family write "
                + ", ".join(sorted({s.route for s in writes})))
    elif plain_copy.is_file():
        row["generated"] = False
        row["source_template"] = f"templates/{name}"
        chrome = _read(plain_copy)
        row["source_evidence"].extend([f"templates/{name}",
                                       "scripts/check_template_site_sync.py"])
        row["notes"].append(
            "plain-copy page asset: templates/ and site/ ship byte-identical "
            "(scripts/check_template_site_sync.py)")
    else:
        row["notes"].append(
            "no write_page() call site resolves to this route; builder unknown")
        if templates:
            row["generated"] = True
            row["source_template"] = f"templates/{templates[0]}"

    if templates:
        row["source_evidence"].append(f"templates/{templates[0]}")
    if tracked_page:
        row["source_evidence"].append(f"site/{name}")
    else:
        row["notes"].append("written by a builder but not committed under site/")

    row["access_shell"] = "anonymous"
    row["source_evidence"].append("config/site_access.yml:1")
    row["payload_tier"] = _macro_payload_tier(lookup, access, chrome=chrome)
    if row["payload_tier"] == "internal":
        row["access_shell"] = UNKNOWN
        row["notes"].append(
            "config/site_access.yml deny: 404 even for an entitled user")
    if access:
        if _in_bucket(lookup, access["free_registered"]):
            row["known_contracts"].append("site_access.v1:free_registered")
        elif not _in_bucket(lookup, access["public"]) \
                and not _in_bucket(lookup, access["deny"]):
            row["known_contracts"].append("site_access.v1:default_insider")

    # The footer is the LOWEST-precedence inventory: a page the product nav or
    # the public nav names keeps that family, and only a page nothing else links
    # takes its footer column.
    row["nav_family"] = nav.get(lookup) or public_nav.get(lookup) \
        or footer.get(lookup) or (
            nav.get(route) or public_nav.get(route) or footer.get(route) or "none")
    if row["nav_family"] != "none":
        if lookup in nav or route in nav:
            row["source_evidence"].append("templates/_navlinks.html.j2")
        elif lookup in public_nav or route in public_nav:
            row["source_evidence"].append("templates/_public_nav.html.j2")
        else:
            row["source_evidence"].append("templates/_public_footer.html.j2")
    if lookup in nav and lookup in public_nav:
        row["notes"].append("linked from both the product nav and the public nav")

    lifecycle = "live"
    if row["payload_tier"] == "internal":
        lifecycle = "internal"
    elif any(stem.startswith(p) for p in exclude_prefixes):
        lifecycle = "internal"
        row["notes"].append("design mockup (lib/seo.py _EXCLUDE_PREFIXES)")
    elif stem.endswith(_LAB_SUFFIXES):
        lifecycle = "lab"
        row["source_evidence"].append("lib/seo.py:99")
    elif stem in _INTERNAL_NAMES:
        lifecycle = "internal"
        row["source_evidence"].append("lib/seo.py:99")
    elif writes and all(Path(s.builder).name.startswith(("_dev_", "render_"))
                        for s in writes):
        lifecycle = "dev_only"
    row["lifecycle"] = lifecycle
    if stem in excluded:
        row["notes"].append("excluded from the core sitemap (lib/seo.py _EXCLUDE_NAMES)")

    row["bilingual"], row["themes"], row["locales"] = _chrome_facts(chrome)


# ---------------------------------------------------------------------------
# terminal (charting-app, Next.js App Router)
# ---------------------------------------------------------------------------

_ROUTE_GROUP_RE = re.compile(r"^\(.*\)$")
_TOP_HREF_RE = re.compile(r'href:\s*"([^"]+)"')

# Gate markers, read off the page module itself.  Each is a server-side early
# return, so its presence in the file IS the gate — no runtime needed.
_TERMINAL_GATES: tuple[tuple[str, str, str], ...] = (
    ("isAdminRequest", "admin", "terminal/lib/adminGate.ts"),
    ("hasLiveOptions", "paid", "terminal/lib/entitlement.ts"),
    ("SignupGate", "signed_in", "terminal/components/gates/SignupGate.tsx"),
)


def derive_terminal(root: Path, ref: str, *, git: GitRunner = run_git
                    ) -> tuple[list[dict], dict]:
    """Rows + provenance for the Next.js terminal, read from a git REF.

    The disk checkout of charting-app is routinely stale (a feature branch, 100+
    commits behind), so nothing here reads the working tree.
    """
    source: dict[str, Any] = {"root": str(root), "ref": ref}
    if not root.is_dir():
        source.update({"available": False, "reason": f"{root} is not a directory"})
        return [], source
    listing = git(root, ["ls-tree", "-r", ref, "--name-only"])
    sha = git(root, ["rev-parse", ref])
    if listing is None:
        source.update({"available": False,
                       "reason": f"git ls-tree -r {ref} failed in {root}"})
        return [], source
    source["available"] = True
    source["sha"] = sha.strip() if sha else UNKNOWN

    pages = sorted(p for p in listing.splitlines()
                   if p.startswith("terminal/app/") and p.endswith("/page.tsx")
                   or p == "terminal/app/page.tsx")
    nav_text = git(root, ["show", f"{ref}:terminal/components/AppNav.tsx"]) or ""
    nav_hrefs = set(_TOP_HREF_RE.findall(nav_text.split("export const TOP")[-1]
                                         .split("]")[0])) if "export const TOP" \
        in nav_text else set()
    layout = git(root, ["show", f"{ref}:terminal/app/layout.tsx"]) or ""
    dark_only = 'data-theme="dark"' in layout
    i18n = git(root, ["show", f"{ref}:terminal/lib/i18n.tsx"]) or ""
    lang_match = re.search(r"type Lang\s*=\s*([^;]+);", i18n)
    locales = re.findall(r'"(\w+)"', lang_match.group(1)) if lang_match else []

    rows: list[dict] = []
    for page in pages:
        rel = page[len("terminal/app/"):-len("/page.tsx")] \
            if page != "terminal/app/page.tsx" else ""
        segments = [s for s in rel.split("/") if s and not _ROUTE_GROUP_RE.match(s)]
        is_family = any(s.startswith("[") for s in segments)
        route = "/" + "/".join(
            f"<{s.strip('[].')}>" if s.startswith("[") else s for s in segments)
        page_id = "terminal:" + (_slugify("_".join(
            re.sub(r"[\[\].]", "", s) for s in segments)) or "landing")
        row = blank_row(page_id, "terminal", route)
        row["route_kind"] = "family" if is_family else "page"
        row["generated"] = False
        row["source_template"] = page
        row["builder"] = []
        row["source_evidence"].append(page)
        row["notes"].append("Next.js App Router page module (the module IS the page)")

        body = git(root, ["show", f"{ref}:{page}"]) or ""
        for marker, shell, evidence in _TERMINAL_GATES:
            if marker in body:
                row["access_shell"] = shell
                row["source_evidence"].append(evidence)
                row["notes"].append(f"gate marker `{marker}` in the page module")
                break
        if row["access_shell"] == "paid":
            row["payload_tier"] = "premium"
            row["known_contracts"].append("entitlement feature terminal_live_options")

        if segments and segments[0] == "dev":
            row["lifecycle"] = "dev_only"
            row["notes"].append("under app/dev/ — developer surface, not customer content")
        else:
            row["lifecycle"] = "live"

        row["nav_family"] = "app_nav.rail" if route in nav_hrefs else "none"
        if row["nav_family"] != "none":
            row["source_evidence"].append("terminal/components/AppNav.tsx")

        if dark_only:
            row["themes"] = ["dark"]
            row["source_evidence"].append("terminal/app/layout.tsx")
        if locales:
            row["locales"] = sorted(locales)
            row["bilingual"] = len(locales) > 1
            row["source_evidence"].append("terminal/lib/i18n.tsx")
        rows.append(row)

    source["page_modules"] = len(rows)
    return rows, source


# ---------------------------------------------------------------------------
# mastermind (FastAPI portfolio app)
# ---------------------------------------------------------------------------

def derive_mastermind(root: Path, *, git: GitRunner = run_git,
                      read_text: Optional[Callable[[Path], str]] = None
                      ) -> tuple[list[dict], dict]:
    """Rows + provenance for the Mastermind FastAPI app.

    HTML routes are the ``@router.get(...)`` handlers in ``app/web.py`` that
    return a ``FileResponse`` of a ``.html`` static file.
    """
    read_text = read_text or _read
    source: dict[str, Any] = {"root": str(root)}
    web = root / "app" / "web.py"
    text = read_text(web)
    if not text:
        source.update({"available": False, "reason": f"{web} not readable"})
        return [], source
    branch = (git(root, ["rev-parse", "--abbrev-ref", "HEAD"]) or "").strip()
    sha = (git(root, ["rev-parse", "HEAD"]) or "").strip()
    dirty = git(root, ["status", "--porcelain", "--untracked-files=no"])
    source.update({
        "available": True,
        "ref": branch or UNKNOWN,
        "sha": sha or UNKNOWN,
        "tracked_worktree_clean": bool(dirty is not None and not dirty.strip()),
        "read_from": "worktree",
    })

    try:
        tree = ast.parse(text)
    except SyntaxError:
        source.update({"available": False, "reason": "app/web.py did not parse"})
        return [], source

    rows: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        route = None
        for deco in node.decorator_list:
            if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute) \
                    and deco.func.attr == "get" and deco.args \
                    and isinstance(deco.args[0], ast.Constant):
                route = deco.args[0].value
        if not isinstance(route, str):
            continue
        static = None
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) \
                    and inner.func.id == "FileResponse" and inner.args:
                served = ast.unparse(inner.args[0])
                found = re.search(r"""['"]([^'"]+\.html)['"]""", served)
                if found:
                    static = found.group(1)
        if not static:
            continue
        page_id = "mastermind:" + (_slugify(route) or "index")
        row = blank_row(page_id, "mastermind", route)
        row["generated"] = False
        row["source_template"] = f"app/static/{static}"
        row["source_evidence"].extend([f"app/web.py:{node.lineno}",
                                       f"app/static/{static}"])
        row["access_shell"] = "anonymous"
        row["payload_tier"] = "public"
        row["lifecycle"] = "live"
        row["nav_family"] = UNKNOWN
        row["notes"].append(
            "nav membership not derived: the dashboard nav is built client-side "
            "in the SPA, not from a server-side link inventory")
        row["source_evidence"].append("app/auth.py:13")
        row["notes"].append(
            "all GETs are unauthenticated: the browser password/cookie login was "
            "removed; only mutating/LLM POSTs need a bearer token (app/auth.py)")
        if static == "index.html" and route != "/":
            row["notes"].append(
                "same SPA shell as /: the client opens this view from the path")
        rows.append(row)

    source["html_routes"] = len(rows)
    return rows, source


# ---------------------------------------------------------------------------
# overrides
# ---------------------------------------------------------------------------

def load_overrides(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    pages = raw.get("pages") or {}
    if not isinstance(pages, dict):
        raise ValueError(f"{path}: `pages` must be a mapping of page_id -> fields")
    return pages


def apply_overrides(rows: list[dict], overrides: dict[str, dict],
                    *, source_name: str) -> list[str]:
    """Merge the overlay onto derived rows; return the list of hard errors.

    An override on a page_id that no longer exists is an ERROR, not a warning:
    a stale overlay is how a registry starts lying about a page that was
    deleted six months ago.
    """
    errors: list[str] = []
    index = {row["page_id"]: row for row in rows}
    for page_id, entry in sorted(overrides.items()):
        row = index.get(page_id)
        if row is None:
            errors.append(f"{source_name}: override for unknown page_id {page_id!r}")
            continue
        if not isinstance(entry, dict):
            errors.append(f"{source_name}: override {page_id!r} is not a mapping")
            continue
        for key, value in sorted(entry.items()):
            if key in OVERRIDE_META:
                continue
            if key not in OVERRIDABLE:
                errors.append(
                    f"{source_name}: override {page_id!r} sets non-overridable "
                    f"field {key!r} (derived-only)")
                continue
            row[key] = value
        evidence = entry.get("evidence") or []
        if isinstance(evidence, str):
            evidence = [evidence]
        row["source_evidence"].extend(str(e) for e in evidence)
        note = entry.get("note")
        if note:
            row["notes"].append(str(note))
    return errors


# ---------------------------------------------------------------------------
# open PRs (opt-in; ONE gh call — the REST pool is shared fleet-wide)
# ---------------------------------------------------------------------------

def attach_open_prs(rows: list[dict], repo_root: Path) -> dict[str, Any]:
    """Map open-PR changed files onto rows via builder/template/evidence paths."""
    try:
        proc = subprocess.run(
            ["gh", "pr", "list", "--state", "open", "--limit", "100",
             "--json", "number,title,files"],
            cwd=str(repo_root), capture_output=True, timeout=120, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "reason": str(exc)}
    if proc.returncode != 0:
        return {"available": False,
                "reason": proc.stderr.decode("utf-8", "replace").strip()[:200]}
    try:
        prs = json.loads(proc.stdout.decode("utf-8", "replace") or "[]")
    except json.JSONDecodeError:
        return {"available": False, "reason": "gh returned non-JSON"}
    touched: dict[str, set[int]] = defaultdict(set)
    titles: dict[int, str] = {}
    for pr in prs:
        number = pr.get("number")
        titles[number] = pr.get("title") or ""
        for entry in pr.get("files") or []:
            path = entry.get("path") if isinstance(entry, dict) else str(entry)
            if path:
                touched[path].add(number)
    for row in rows:
        if row["repo"] != "macro":
            continue
        paths = {p.split(":", 1)[0] for p in row["source_evidence"]}
        paths.update(row["builder"])
        if row["source_template"] != UNKNOWN:
            paths.add(row["source_template"])
        hits = sorted({n for p in paths for n in touched.get(p, ())})
        row["open_prs"] = [{"number": n, "title": titles.get(n, "")} for n in hits]
    return {"available": True, "open_prs": len(prs)}


# ---------------------------------------------------------------------------
# validation (--check)
# ---------------------------------------------------------------------------

def validate(doc: Any) -> list[str]:
    """Schema invariants of a built registry.  Returns a list of problems."""
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["registry is not a JSON object"]
    if doc.get("schema") != SCHEMA:
        problems.append(f"schema is {doc.get('schema')!r}, expected {SCHEMA!r}")
    if not isinstance(doc.get("generated_at"), str) or not doc.get("generated_at"):
        problems.append("generated_at missing or not a string")
    if not isinstance(doc.get("sources"), dict) or not doc["sources"]:
        problems.append("sources missing or empty")
    pages = doc.get("pages")
    if not isinstance(pages, list) or not pages:
        problems.append("pages missing or empty")
        return problems

    seen: set[str] = set()
    for i, row in enumerate(pages):
        where = f"pages[{i}]"
        if not isinstance(row, dict):
            problems.append(f"{where}: not an object")
            continue
        where = f"{row.get('page_id', where)}"
        missing = [f for f in FIELD_ORDER if f not in row]
        if missing:
            problems.append(f"{where}: missing fields {missing}")
            continue
        extra = [f for f in row if f not in FIELD_ORDER]
        if extra:
            problems.append(f"{where}: unexpected fields {extra}")
        for field, value in row.items():
            if value is None:
                problems.append(f"{where}: {field} is null (use \"unknown\")")
        page_id = row["page_id"]
        if page_id in seen:
            problems.append(f"{where}: duplicate page_id")
        seen.add(page_id)
        if row["repo"] not in REPOS:
            problems.append(f"{where}: repo {row['repo']!r} not in {REPOS}")
        if not str(page_id).startswith(f"{row['repo']}:"):
            problems.append(f"{where}: page_id is not prefixed with its repo")
        if row["route_kind"] not in ROUTE_KINDS:
            problems.append(f"{where}: route_kind {row['route_kind']!r} invalid")
        if not str(row["route"]).startswith("/"):
            problems.append(f"{where}: route must start with '/'")
        if row["access_shell"] not in ACCESS_SHELLS:
            problems.append(f"{where}: access_shell {row['access_shell']!r} invalid")
        if row["payload_tier"] not in PAYLOAD_TIERS:
            problems.append(f"{where}: payload_tier {row['payload_tier']!r} invalid")
        if row["lifecycle"] not in LIFECYCLES:
            problems.append(f"{where}: lifecycle {row['lifecycle']!r} invalid")
        if row["priority"] not in PRIORITIES:
            problems.append(f"{where}: priority {row['priority']!r} invalid")
        if not (isinstance(row["generated"], bool) or row["generated"] == UNKNOWN):
            problems.append(f"{where}: generated must be a bool or \"unknown\"")
        if not (isinstance(row["bilingual"], bool) or row["bilingual"] == UNKNOWN):
            problems.append(f"{where}: bilingual must be a bool or \"unknown\"")
        for field in LIST_OR_UNKNOWN:
            value = row[field]
            if not (value == UNKNOWN or (isinstance(value, list)
                                         and all(isinstance(v, str) for v in value))):
                problems.append(
                    f"{where}: {field} must be a list of strings or \"unknown\"")
        for field in ALWAYS_LIST:
            if not isinstance(row[field], list):
                problems.append(f"{where}: {field} must be a list")
        for field in ("source_template", "nav_family", "archetype", "owner",
                      "primary_user_question"):
            if not isinstance(row[field], str):
                problems.append(f"{where}: {field} must be a string")
        if not row["source_evidence"]:
            problems.append(f"{where}: no source_evidence")
    return problems


# ---------------------------------------------------------------------------
# build + CLI
# ---------------------------------------------------------------------------

def build_registry(*, repo_root: Path, terminal_root: Path, terminal_ref: str,
                   mastermind_root: Path, site_dir: Optional[Path],
                   as_of: Optional[str], overrides_path: Path,
                   git: GitRunner = run_git) -> tuple[dict, list[str]]:
    rows: list[dict] = []
    sources: dict[str, Any] = {}

    macro_rows, sources["macro"] = derive_macro(repo_root, site_dir=site_dir, git=git)
    rows.extend(macro_rows)
    terminal_rows, sources["terminal"] = derive_terminal(
        terminal_root, terminal_ref, git=git)
    rows.extend(terminal_rows)
    mastermind_rows, sources["mastermind"] = derive_mastermind(
        mastermind_root, git=git)
    rows.extend(mastermind_rows)

    errors = apply_overrides(rows, load_overrides(overrides_path),
                             source_name=str(overrides_path.name))

    for row in rows:
        row["source_evidence"] = sorted(dict.fromkeys(row["source_evidence"]))
        row["known_contracts"] = list(dict.fromkeys(row["known_contracts"]))
        row["notes"] = list(dict.fromkeys(row["notes"]))
    rows.sort(key=lambda r: (r["repo"], r["route"], r["page_id"]))

    doc = {
        "schema": SCHEMA,
        "generated_at": as_of or datetime.now(timezone.utc)
            .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "sources": sources,
        "pages": [{f: row[f] for f in FIELD_ORDER} for row in rows],
    }
    return doc, errors


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    ap.add_argument("--terminal-root", type=Path, default=DEFAULT_TERMINAL_ROOT)
    ap.add_argument("--terminal-ref", default="origin/master")
    ap.add_argument("--mastermind-root", type=Path, default=DEFAULT_MASTERMIND_ROOT)
    ap.add_argument("--site-dir", type=Path, default=None,
                    help="optional rendered site/ tree; enriches the inventory "
                         "when git is unavailable")
    ap.add_argument("--as-of", default=None,
                    help="pin generated_at (ISO8601) so diffs stay clean")
    ap.add_argument("--with-prs", action="store_true",
                    help="one `gh pr list` call to attach open PRs (OFF by "
                         "default: the GitHub REST pool is shared fleet-wide)")
    ap.add_argument("--check", action="store_true",
                    help="validate the committed JSON without deriving anything")
    args = ap.parse_args(argv)

    if args.check:
        try:
            doc = json.loads(args.output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            annotate(f"{args.output} is unreadable: {exc}")
            return 1
        problems = validate(doc)
        overrides = load_overrides(args.overrides)
        known = {row.get("page_id") for row in doc.get("pages", [])
                 if isinstance(row, dict)}
        problems.extend(
            f"{args.overrides.name}: override for unknown page_id {pid!r}"
            for pid in sorted(overrides) if pid not in known)
        if problems:
            for problem in problems[:40]:
                annotate(problem)
            annotate(f"{len(problems)} schema problem(s) in {args.output}")
            return 1
        print(f"page registry OK: {len(doc['pages'])} rows, schema {SCHEMA}")
        return 0

    doc, errors = build_registry(
        repo_root=REPO_ROOT, terminal_root=args.terminal_root,
        terminal_ref=args.terminal_ref, mastermind_root=args.mastermind_root,
        site_dir=args.site_dir, as_of=args.as_of, overrides_path=args.overrides,
    )
    if errors:
        for error in errors:
            annotate(error)
        return 1
    if args.with_prs:
        doc["sources"]["open_prs"] = attach_open_prs(doc["pages"], REPO_ROOT)

    problems = validate(doc)
    if problems:
        for problem in problems[:40]:
            annotate(problem)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, indent=2, ensure_ascii=False,
                                      sort_keys=False) + "\n", encoding="utf-8")
    counts: dict[str, int] = defaultdict(int)
    for row in doc["pages"]:
        counts[row["repo"]] += 1
    print(f"wrote {args.output} — " + ", ".join(
        f"{repo}: {counts[repo]}" for repo in REPOS) + f", total {len(doc['pages'])}")
    for repo in REPOS:
        entry = doc["sources"].get(repo, {})
        if not entry.get("available"):
            print(f"  {repo}: UNAVAILABLE — {entry.get('reason', 'unknown reason')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
