"""Build the public bilingual Market Reference page -> site/reference.html.

MOR-1 (agentos/decisions/DEC-MARKET-ONTOLOGY-MARKET-ORIENTATION-PROJECTION-2026-08-30.md
§3.2/§3.3). Loads the closed registry `config/market_reference.yml`
(schema `mastermind.market_reference/v1`), validates it FAIL-CLOSED against
every §3.3 rule, then renders `templates/reference.html.j2` the same way
`scripts/build_methodology.py` renders its own static page: no live values,
Jinja `Environment(autoescape=True)`, `lib.pages.write_page` for the
data_base.js injection shim.

Deterministic — no network, no engine output, no as-of clock beyond the
build-time presentation stamp (DEC §4: `generated_at` is presentation-only;
the page carries no market values so no source-state chips are needed).

Usage: python -m scripts.build_market_reference
"""
from __future__ import annotations

import logging
import re
import string
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import yaml
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_market_reference")

SCHEMA = "mastermind.market_reference/v1"
REGISTRY_PATH = config.ROOT / "config" / "market_reference.yml"
TEMPLATE_NAME = "reference.html.j2"
OUT_NAME = "reference.html"

# Registry taxonomy (frozen — MOR1_CONTRACT.md "Registry taxonomy").
FAMILY_ORDER = [
    "regime", "liquidity", "volatility-stress", "rates-curve", "credit",
    "breadth-participation", "flows-positioning", "calendar-events",
    "doctrine", "cross-asset-basics",
]

# Plain-word rail labels for each family. Not specified by any of the three
# frozen inputs (the design spec left the family DISPLAY strings open — only
# the enum of family ids is frozen); smallest-scope builder choice, logged in
# the MOR-1 build packet DEVIATIONS.
FAMILY_LABELS: dict[str, tuple[str, str]] = {
    "regime": ("Regime", "宏观周期"),
    "liquidity": ("Liquidity", "流动性"),
    "volatility-stress": ("Volatility & Stress", "波动率与压力"),
    "rates-curve": ("Rates & Curve", "利率与曲线"),
    "credit": ("Credit", "信用"),
    "breadth-participation": ("Breadth & Participation", "广度与参与度"),
    "flows-positioning": ("Flows & Positioning", "资金流与持仓"),
    "calendar-events": ("Calendar & Events", "日历与事件"),
    "doctrine": ("Doctrine", "方法论词汇"),
    "cross-asset-basics": ("Cross-Asset Basics", "跨资产基础"),
}

# Owner pages this registry may cite, and the REAL id= anchors verified by
# hand against the live templates that render them (see the MOR-1 build
# packet DEVIATIONS table for the archaeology). A bare page (no fragment) is
# always legal. This is the allowlist "unknown owner page/anchor" fails
# closed against — extending it is the only way a future registry edit may
# cite a new owner surface.
#
# NAVIGABILITY (B1, 2026-09-02 review repair): `regime-radar`, `sx-events-v2`,
# `sx-markets-v2` and `sx-v5-sentiment` are the Market State command-center's
# always-visible container ids — verified, using BeautifulSoup against the
# committed site/macro.html, to sit outside any `display:none`/
# `visibility:hidden` rule under macro.html's actual rendered body class
# (`page-macro mx4-grid`, the server-rendered default). `ms-score` (inside
# `.mx2-hero`, which IS `display:none!important` under `mx4-grid`),
# `mx5PopFactors` (a `.mx5-popover`, at-rest `display:none` until a click),
# `dlg-risk`/`dlg-markets` (`.mx5-dlg` modals, at-rest `display:none`;
# macro.html does have a `_resolveAlertHash()` cold-load JS resolver that can
# open a `.mx5-dlg` named by the hash, but this registry does not rely on a
# JS mechanism for reachability — the design spec's own contract is that the
# page works with JS disabled), `release-radar` (`position:absolute;
# left:-10000px;visibility:hidden` under `mx4-grid` until its own tray is
# opened) and `cross-asset-macro` (only rendered when `mode=='stocks'`, i.e.
# on us_stocks.html — and even there `body.page-stocks
# #cross-asset-macro{display:none!important}`, so it is never visible on
# either page) are EXCLUDED from this allowlist for exactly that reason —
# see `check_anchor_liveness()` below and its red fixture in
# tests/test_market_reference.py.
KNOWN_OWNER_PAGES: dict[str, set[str]] = {
    "macro.html": {
        "regime-radar", "sx-events-v2", "sx-markets-v2", "sx-v5-sentiment",
        # A-MO-W2-1: verified live via check_anchor_liveness() against the
        # committed site/macro.html under its default rendered body class.
        "sx-evidence",
    },
    "aibrief.html": set(),
    "whitehouse.html": {"treasury-watch"},
    "bonds.html": {"curve", "real", "credit"},
    "committee.html": {"cm_rebalance_pulse_section"},
    # A-MO-W2-1: new owner surface, verified live via check_anchor_liveness()
    # against the committed site/us_stocks.html.
    "us_stocks.html": {"action-board", "equity-scoreboard", "advanced-breadth", "dash-mtf-section"},
}

# Display label for an owner_ref link. The registry stores only the raw
# `page.html#fragment`; the design spec's markup (§2, "Where you'll see
# this") needs a navigable label. Mechanical, not editorial — smallest-scope
# builder choice, logged in DEVIATIONS.
PAGE_LABELS: dict[str, tuple[str, str]] = {
    "macro.html": ("Macro Dashboard", "宏观看板"),
    "aibrief.html": ("AI Briefing", "AI 简报"),
    "whitehouse.html": ("Treasury Watch", "财政部观察"),
    "bonds.html": ("Bonds", "债券"),
    "committee.html": ("Committee", "委员会"),
    "us_stocks.html": ("US Stocks", "美股"),
}

# A-MO-W2-1: the fourth legal `coverage_exceptions[].state` value.
COVERAGE_STATES = {"not_an_indicator", "not_covered", "covered_by"}

# Public primary-source allowlist (MOR1_CONTRACT.md "Registry taxonomy").
SOURCE_HOST_LABELS: dict[str, str] = {
    "fred.stlouisfed.org": "FRED",
    "treasury.gov": "U.S. Treasury",
    "www.treasury.gov": "U.S. Treasury",
    "cboe.com": "CBOE",
    "www.cboe.com": "CBOE",
    "bls.gov": "U.S. BLS",
    "www.bls.gov": "U.S. BLS",
    "bea.gov": "U.S. BEA",
    "www.bea.gov": "U.S. BEA",
    "federalreserve.gov": "Federal Reserve",
    "www.federalreserve.gov": "Federal Reserve",
}

ALLOWED_KINDS = {"indicator", "glossary"}
ALLOWED_STATUS = {"active", "deprecated"}

_PUNCT_RE = re.compile(r"[\s　-〿＀-￯!-/:-@\[-`{-~]")


class RegistryError(Exception):
    """Registry validation failed. `.errors` carries every violated rule's message
    (fail-closed: the build reports every problem in one pass, not just the first)."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__(f"{len(self.errors)} registry validation error(s): " + "; ".join(self.errors))


def _norm_alias(s: str) -> str:
    """Casefold + strip normalization for duplicate-alias detection (contract rule)."""
    return unicodedata.normalize("NFKC", (s or "")).strip().casefold()


def search_key(entry: dict) -> str:
    """Build-time search key (design spec §2): label_en + label_zh + aliases_en +
    aliases_zh + id, lowercased, NFKC-normalized, whitespace/punctuation stripped.
    The only thing client JS searches — no DOM walking, no ZH segmentation."""
    parts = [entry.get("label_en", ""), entry.get("label_zh", ""), entry.get("id", "")]
    parts += list(entry.get("aliases_en") or [])
    parts += list(entry.get("aliases_zh") or [])
    raw = unicodedata.normalize("NFKC", "".join(parts)).casefold()
    return _PUNCT_RE.sub("", raw)


def initial_of(label_en: str) -> str:
    """Uppercased first Latin letter of label_en, or '#' when none (design spec §2)."""
    for ch in label_en or "":
        if ch.isascii() and ch.isalpha():
            return ch.upper()
    return "#"


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RegistryError([f"{path}: registry root must be a mapping"])
    return raw


# ---------------------------------------------------------------------------
# anchor liveness (B1, 2026-09-02 review repair)
# ---------------------------------------------------------------------------
#
# A durable, pragmatic (NOT a full CSS cascade engine) check against the
# committed site/<page>.html output AND the page's full local CSS corpus
# (inline <style> blocks plus every site-local <link rel=stylesheet> file,
# comments stripped — rendered pages here carry ZERO inline styles, so
# scanning the HTML alone finds nothing; verified on site/macro.html).
# Exact coverage, verified by EXECUTING the check against the six anchors
# removed in the B1 repair — do not overclaim beyond this list:
#   1. id ABSENT from the committed page — catches `cross-asset-macro`;
#   2. body-gated hide rules `body.<classes> #<id>{display:none|visibility:hidden}`
#      whose class set matches the rendered <body class="…"> — catches
#      `release-radar`;
#   3. host-element-own-class hide rules (`.cls…{display:none|…}` where the
#      id's element carries that class) — catches `mx5PopFactors`
#      (.mx5-popover) and `dlg-risk`/`dlg-markets` (.mx5-dlg).
# NOT covered: ANCESTOR-chain hiding (`ms-score` sits inside .mx2-hero,
# which is what hides it), descendant/sibling/attribute selectors, and
# !important cascade ordering — so KNOWN_OWNER_PAGES itself remains the
# hand-verified source of truth and this check is a 5-of-6 regression net,
# not a CSS verifier.
_BODY_HIDE_RULE_RE = re.compile(
    r"body((?:\.[A-Za-z0-9_-]+)+)\s*(?:>\s*)?#([A-Za-z0-9_-]+)\s*\{([^}]*)\}"
)
_BODY_CLASS_RE = re.compile(r'<body[^>]*\bclass="([^"]*)"')
_HIDDEN_DECL_RE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden")


def _page_css_texts(repo_root: Path, html_text: str) -> list[str]:
    """The page's CSS corpus: inline <style> blocks PLUS the contents of every
    LOCAL stylesheet it links (href resolved under site/, ?v= cache-busters
    stripped, external http(s) links skipped). Rendered pages here typically
    carry zero inline styles — their hide rules live in linked files — so
    scanning the HTML alone finds nothing (verified on site/macro.html)."""
    def _strip_comments(css: str) -> str:
        return re.sub(r"/\*.*?\*/", " ", css, flags=re.S)

    texts = [_strip_comments(m.group(1))
             for m in re.finditer(r"<style[^>]*>(.*?)</style>", html_text, re.S)]
    for lm in re.finditer(r'<link\s[^>]*rel="stylesheet"[^>]*href="([^"]+)"', html_text):
        href = lm.group(1).split("?", 1)[0]
        if href.startswith(("http://", "https://", "//")):
            continue
        css_path = (repo_root / "site" / href.lstrip("./")).resolve()
        try:
            css_path.relative_to((repo_root / "site").resolve())
        except ValueError:
            continue
        if css_path.exists():
            texts.append(_strip_comments(css_path.read_text(encoding="utf-8", errors="replace")))
    return texts


def _page_body_classes(html_text: str) -> frozenset[str]:
    m = _BODY_CLASS_RE.search(html_text)
    return frozenset(m.group(1).split()) if m else frozenset()


def _body_gated_hidden_ids(css_text: str) -> dict[str, list[frozenset[str]]]:
    """id -> list of body-class sets under which a `body.<classes> #<id>{…}`
    rule in this CSS hides it (display:none or visibility:hidden)."""
    hidden: dict[str, list[frozenset[str]]] = {}
    for m in _BODY_HIDE_RULE_RE.finditer(css_text):
        classes = frozenset(m.group(1).lstrip(".").split("."))
        frag, decl = m.group(2), m.group(3)
        if _HIDDEN_DECL_RE.search(decl):
            hidden.setdefault(frag, []).append(classes)
    return hidden


def _host_element_classes(html_text: str, frag: str) -> frozenset[str]:
    """Class set on the element carrying id=frag (empty when none/absent)."""
    m = re.search(r'<[A-Za-z][A-Za-z0-9]*\b[^>]*\bid="' + re.escape(frag) + r'"[^>]*>', html_text)
    if not m:
        return frozenset()
    cm = re.search(r'\bclass="([^"]*)"', m.group(0))
    return frozenset(cm.group(1).split()) if cm else frozenset()


def _pure_class_hidden_sets(css_text: str) -> list[frozenset[str]]:
    """Class sets hidden by PURE compound class rules (`.a.b{display:none}`).
    Only selectors that are exactly one class compound count — descendant,
    id-anchored, and attribute selectors are ignored (ancestor hiding is out
    of scope by design; see the coverage comment above KNOWN_OWNER_PAGES)."""
    out: list[frozenset[str]] = []
    for rm in re.finditer(r"([^{}]+)\{([^}]*)\}", css_text):
        sel_list, decl = rm.group(1), rm.group(2)
        if not _HIDDEN_DECL_RE.search(decl):
            continue
        for sel in sel_list.split(","):
            sel = sel.strip()
            if re.fullmatch(r"(?:\.[A-Za-z0-9_-]+)+", sel):
                out.append(frozenset(sel.lstrip(".").split(".")))
    return out


def check_anchor_liveness(repo_root: Path, page: str, frag: str) -> tuple[bool, str]:
    """(is_live, note) for `<page>#<frag>`. FAILS OPEN (is_live=True) when
    site/<page> is absent from this checkout — a sparse worktree, or a page
    this builder does not itself produce, may legitimately not have it built;
    this builder does not require every OTHER page's output to exist. When
    the page IS present, fails CLOSED: the id must exist in the page, and
    must not resolve to a body-class-gated display:none/visibility:hidden
    rule under the page's own actual rendered body class."""
    site_path = repo_root / "site" / page
    if not site_path.exists():
        return True, f"site/{page} not built in this checkout — liveness check skipped"
    text = site_path.read_text(encoding="utf-8", errors="replace")
    if f'id="{frag}"' not in text:
        return False, f'no id="{frag}" found in site/{page}'
    body_classes = _page_body_classes(text)
    host_classes = _host_element_classes(text, frag)
    for css_text in _page_css_texts(repo_root, text):
        for required in _body_gated_hidden_ids(css_text).get(frag, []):
            if required <= body_classes:
                return False, (
                    f"#{frag} is display:none/visibility:hidden on {page} under body class(es) "
                    f"{sorted(required)} (page's rendered body class: {sorted(body_classes)})"
                )
        if host_classes:
            for required in _pure_class_hidden_sets(css_text):
                if required <= host_classes:
                    return False, (
                        f"#{frag}'s own element is hidden on {page}: class rule "
                        f"{sorted(required)} carries display:none/visibility:hidden "
                        f"(element classes: {sorted(host_classes)})"
                    )
    return True, "live"


def validate(raw: dict, repo_root: Path = config.ROOT) -> list[dict]:
    """Validate the raw registry against every MOR1_CONTRACT.md §"Registry taxonomy"
    / DEC §3.3 rule, PLUS (B1) the anchor-liveness check against
    `<repo_root>/site/<page>.html`; return the ordered list of entry dicts on
    success. Raises RegistryError (fail-closed) with every violation found.
    `repo_root` defaults to this checkout's root; tests pass a temp dir with a
    synthetic site/<page>.html to exercise the liveness rule in isolation."""
    errors: list[str] = []
    if raw.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}, got {raw.get('schema')!r}")
    entries = raw.get("entries")
    if not isinstance(entries, list) or not entries:
        raise RegistryError(errors + ["entries must be a non-empty list"])

    seen_ids: dict[str, int] = {}
    seen_alias: dict[str, str] = {}
    for i, e in enumerate(entries):
        eid = e.get("id")
        where = f"entry[{i}] id={eid!r}"

        if not eid or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", str(eid)):
            errors.append(f"{where}: id must be a non-empty kebab-case slug")
        elif eid in seen_ids:
            errors.append(f"duplicate id: {eid!r} (entries[{seen_ids[eid]}] and [{i}])")
        else:
            seen_ids[eid] = i

        if e.get("kind") not in ALLOWED_KINDS:
            errors.append(f"{where}: kind must be one of {sorted(ALLOWED_KINDS)}, got {e.get('kind')!r}")
        if e.get("family") not in FAMILY_ORDER:
            errors.append(f"{where}: family must be one of {FAMILY_ORDER}, got {e.get('family')!r}")
        if e.get("authority_ceiling") != "reference_only":
            errors.append(f"{where}: authority_ceiling must be 'reference_only', got {e.get('authority_ceiling')!r}")
        if e.get("status") not in ALLOWED_STATUS:
            errors.append(f"{where}: status must be one of {sorted(ALLOWED_STATUS)}, got {e.get('status')!r}")

        # missing either language — the dual-authored prose fields
        for base in ("label", "short_definition", "why_it_matters"):
            en, zh = e.get(f"{base}_en"), e.get(f"{base}_zh")
            if not (en and str(en).strip()) or not (zh and str(zh).strip()):
                errors.append(f"{where}: {base}_en and {base}_zh must both be present and non-empty")
        if ("aliases_en" in e) != ("aliases_zh" in e):
            errors.append(f"{where}: aliases_en/aliases_zh must both be present when either is")

        # ZH-required parity for the single-field (non `_en`-suffixed) freeform
        # fields — MOR-1 shipped these English-only with a graceful t(en, zh='')
        # render fallback; the MOR-1 ZH supplement then supplied real translations
        # for every non-null value, so the fallback is now retired here in favour
        # of a fail-closed rule: whenever the field is present, its `_zh` sibling
        # must be present too. A null/absent value legitimately carries no `_zh`
        # sibling (the 8 entries with no up/down directional reading stay null on
        # both sides).
        for base in ("unit_or_basis", "interpretation_up", "interpretation_down", "interpretation_neutral"):
            en_val = e.get(base)
            if en_val is None or (isinstance(en_val, str) and not en_val.strip()):
                continue
            zh_val = e.get(f"{base}_zh")
            if not (zh_val and str(zh_val).strip()):
                errors.append(f"{where}: {base} is present but {base}_zh is missing")

        # missing caveats on kind: indicator
        if e.get("kind") == "indicator":
            cav_en, cav_zh = e.get("caveats_en") or [], e.get("caveats_zh") or []
            if not cav_en or not cav_zh:
                errors.append(f"{where}: kind:indicator requires a non-empty caveats_en and caveats_zh")
            elif len(cav_en) != len(cav_zh):
                errors.append(f"{where}: caveats_en and caveats_zh must have matching length")

        # unknown owner page/anchor, and (B1) anchor LIVENESS
        owner = e.get("owner_ref")
        if not owner or not isinstance(owner, str):
            errors.append(f"{where}: owner_ref is required")
        else:
            page, _, frag = owner.partition("#")
            if page not in KNOWN_OWNER_PAGES:
                errors.append(f"{where}: unknown owner page {page!r} in owner_ref {owner!r}")
            elif frag and frag not in KNOWN_OWNER_PAGES[page]:
                errors.append(f"{where}: unknown owner anchor '#{frag}' on page {page!r} in owner_ref {owner!r}")
            elif frag:
                is_live, note = check_anchor_liveness(repo_root, page, frag)
                if not is_live:
                    errors.append(f"{where}: owner_ref {owner!r} is not a live/visible anchor: {note}")

        # unsafe / non-allowlist public_source_refs
        for url in (e.get("public_source_refs") or []):
            parsed = urlparse(str(url))
            if parsed.scheme != "https" or parsed.netloc not in SOURCE_HOST_LABELS:
                errors.append(f"{where}: public_source_refs url {url!r} is not on the allowlist")

        # duplicate normalized aliases (casefold, strip) across EN+ZH, across the
        # whole registry — the same alias claimed by two different entry ids
        for alias in list(e.get("aliases_en") or []) + list(e.get("aliases_zh") or []):
            key = _norm_alias(alias)
            if not key:
                continue
            if key in seen_alias and seen_alias[key] != eid:
                errors.append(
                    f"{where}: alias {alias!r} duplicates an alias already used by entry {seen_alias[key]!r}"
                )
            else:
                seen_alias[key] = eid

    # related_ids must resolve to a real entry
    for i, e in enumerate(entries):
        for rid in (e.get("related_ids") or []):
            if rid not in seen_ids:
                errors.append(f"entry[{i}] id={e.get('id')!r}: related_ids references unknown id {rid!r}")

    # status:deprecated requires superseded_by; superseded_by must resolve to a real id
    for i, e in enumerate(entries):
        eid = e.get("id")
        sb = e.get("superseded_by")
        if e.get("status") == "deprecated" and not sb:
            errors.append(f"entry[{i}] id={eid!r}: status:deprecated requires a superseded_by")
        if sb and sb not in seen_ids:
            errors.append(f"entry[{i}] id={eid!r}: superseded_by references unknown id {sb!r}")

    # superseded_by cycle detection (status: deprecated entries only)
    graph = {e.get("id"): e.get("superseded_by") for e in entries if e.get("status") == "deprecated"}
    for start in graph:
        path_seen: set = set()
        cur = start
        while cur is not None:
            if cur in path_seen:
                errors.append(f"superseded_by cycle detected starting at {start!r}: {sorted(path_seen)}")
                break
            path_seen.add(cur)
            cur = graph.get(cur)

    if errors:
        raise RegistryError(errors)
    return entries


def _owner_refs_for(owner_ref: str) -> list[dict]:
    page, _, frag = owner_ref.partition("#")
    label_en, label_zh = PAGE_LABELS.get(page, (page, page))
    return [{"href": owner_ref, "label_en": label_en, "label_zh": label_zh}]


def _source_refs_for(urls: list[str]) -> list[dict]:
    out = []
    for url in urls or []:
        host = urlparse(str(url)).netloc
        out.append({"url": url, "label": SOURCE_HOST_LABELS.get(host, host)})
    return out


def build_view_model(entries: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """Turn validated registry entries into the view-model `templates/reference.html.j2`
    consumes (design spec §2). `unit_or_basis` / `interpretation_up/down/neutral` map
    straight from the registry's `<field>` / `<field>_zh` pair into the template's
    `<field>_en` / `<field>_zh` slots — real ZH copy from the MOR-1 ZH supplement,
    validated present by `validate()` whenever the English value is present (the
    original English-only build relied on the template's `t(en, zh='')` fallback for
    these fields; that fallback is now unreachable in practice since validate() no
    longer lets a non-null value through without its `_zh` sibling, but the template
    macro is left as-is since it is harmless dead-code-safety, not a live path)."""
    by_id = {e["id"]: e for e in entries}

    def rank(e: dict) -> tuple[int, str]:
        return (FAMILY_ORDER.index(e["family"]), (e.get("label_en") or "").casefold())

    ordered = sorted(entries, key=rank)

    vm: list[dict] = []
    for e in ordered:
        related = []
        for rid in (e.get("related_ids") or []):
            tgt = by_id.get(rid)
            if tgt:
                related.append({"id": rid, "label_en": tgt.get("label_en"), "label_zh": tgt.get("label_zh")})

        superseded_label_en = superseded_label_zh = None
        if e.get("status") == "deprecated" and e.get("superseded_by"):
            tgt = by_id.get(e["superseded_by"])
            if tgt:
                superseded_label_en, superseded_label_zh = tgt.get("label_en"), tgt.get("label_zh")

        row = dict(e)
        row["initial"] = initial_of(e.get("label_en", ""))
        row["search_key"] = search_key(e)
        row["owner_refs"] = _owner_refs_for(e["owner_ref"])
        row["owner_unlinked"] = "#" not in e["owner_ref"]
        row["public_source_refs"] = _source_refs_for(e.get("public_source_refs"))
        row["related"] = related
        row["unit_or_basis_en"] = e.get("unit_or_basis")
        row["unit_or_basis_zh"] = e.get("unit_or_basis_zh")
        row["interpretation_up_en"] = e.get("interpretation_up")
        row["interpretation_up_zh"] = e.get("interpretation_up_zh")
        row["interpretation_down_en"] = e.get("interpretation_down")
        row["interpretation_down_zh"] = e.get("interpretation_down_zh")
        row["interpretation_neutral_en"] = e.get("interpretation_neutral")
        row["interpretation_neutral_zh"] = e.get("interpretation_neutral_zh")
        row["superseded_by_label_en"] = superseded_label_en
        row["superseded_by_label_zh"] = superseded_label_zh
        vm.append(row)

    families = []
    for fid in FAMILY_ORDER:
        label_en, label_zh = FAMILY_LABELS[fid]
        count = sum(1 for e in vm if e["family"] == fid)
        families.append({"id": fid, "label_en": label_en, "label_zh": label_zh, "count": count})

    letters = list(string.ascii_uppercase)
    return vm, families, letters


def validate_coverage_exceptions(raw: dict, entries: list[dict]) -> list[dict]:
    """A-MO-W2-1: validate `coverage_exceptions` (optional). Fail-closed, same idiom
    as `validate()`. Returns the raw exception dicts on success; raises
    RegistryError with every violation found."""
    seen_ids = {e["id"] for e in entries}
    raw_list = raw.get("coverage_exceptions")
    if raw_list is None:
        return []
    errors: list[str] = []
    if not isinstance(raw_list, list):
        raise RegistryError(["coverage_exceptions must be a list when present"])
    for i, c in enumerate(raw_list):
        where = f"coverage_exceptions[{i}]"
        if not isinstance(c, dict):
            errors.append(f"{where}: must be a mapping")
            continue
        state = c.get("state")
        if state not in COVERAGE_STATES:
            errors.append(f"{where}: state must be one of {sorted(COVERAGE_STATES)}, got {state!r}")
        if not (c.get("element_en") or "").strip():
            errors.append(f"{where}: element_en must be non-empty")
        if not (c.get("element_zh") or "").strip():
            errors.append(f"{where}: element_zh must be non-empty")
        see_ids = c.get("see_ids") or []
        if state == "covered_by":
            if not see_ids:
                errors.append(f"{where}: state:covered_by requires non-empty see_ids")
        elif state in ("not_an_indicator", "not_covered"):
            if not (c.get("reason_en") or "").strip():
                errors.append(f"{where}: state:{state} requires non-empty reason_en")
            if not (c.get("reason_zh") or "").strip():
                errors.append(f"{where}: state:{state} requires non-empty reason_zh")
        for sid in see_ids:
            if sid not in seen_ids:
                errors.append(f"{where}: see_ids references unknown id {sid!r}")
        surface = c.get("surface")
        if surface not in KNOWN_OWNER_PAGES:
            errors.append(f"{where}: surface {surface!r} is not in KNOWN_OWNER_PAGES")
    if errors:
        raise RegistryError(errors)
    return raw_list


def build_coverage_view_model(coverage_raw: list[dict], entries: list[dict]) -> list[dict]:
    """A-MO-W2-1: turn validated coverage_exceptions into the view-model
    `templates/reference.html.j2`'s Coverage ledger consumes."""
    by_id = {e["id"]: e for e in entries}
    out: list[dict] = []
    for c in coverage_raw:
        surface = c.get("surface")
        label_en, label_zh = PAGE_LABELS.get(surface, (surface, surface))
        see = []
        for sid in c.get("see_ids") or []:
            tgt = by_id.get(sid)
            if tgt:
                see.append({"id": sid, "label_en": tgt.get("label_en"), "label_zh": tgt.get("label_zh")})
        out.append({
            "state": c.get("state"),
            "element_en": c.get("element_en"),
            "element_zh": c.get("element_zh"),
            "reason_en": c.get("reason_en"),
            "reason_zh": c.get("reason_zh"),
            "surface_label_en": label_en,
            "surface_label_zh": label_zh,
            "see": see,
        })
    return out


def main() -> int:
    site = config.ROOT / "site"
    try:
        raw = load_registry()
        entries = validate(raw)
        coverage_raw = validate_coverage_exceptions(raw, entries)
    except RegistryError as exc:
        for msg in exc.errors:
            log.error("market_reference registry: %s", msg)
        return 1
    except FileNotFoundError:
        log.error("market_reference registry not found at %s", REGISTRY_PATH)
        return 1

    entries_vm, families_vm, letters = build_view_model(entries)
    coverage = build_coverage_view_model(coverage_raw, entries)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template(TEMPLATE_NAME).render(
        entries=entries_vm, families=families_vm, letters=letters, generated_at=generated_at,
        coverage=coverage,
    )
    out = site / OUT_NAME
    write_page(out, html)
    log.info("wrote %s (%d entries, %.0f KB)", out, len(entries_vm), out.stat().st_size / 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
