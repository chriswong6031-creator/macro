#!/usr/bin/env python3
"""Deterministic post-render estate guard for the public US stock dossier pages.

A render lane that writes 1900+ pages and only checks aggregate failure
counts cannot see a per-page formatting defect: 69 of 2066 generated pages
under site/stocks/ rendered the literal `$nanM` / `$nan` to the public,
because two independent formatters in scripts/build_ticker_pages.py treated a
float NaN as a present value (NaN is truthy in Python). The formatter bug is
fixed separately (scripts/build_ticker_pages.py + lib/numeric.py); THIS guard
is the release-gate half — it scans the estate the render lane just produced
and fails the build if the sentinel class reappears, from any code path,
present or future.

Checks are a registry of named functions (`CHECKS`), each taking the page, its
checkable text and a shared context, and returning a list of violations. Two
classes are implemented:

  machine_sentinel  raw NaN/Infinity leakage (the $nanM class).
  identity          the dossier must not confidently assert the WRONG company.
                    The ticker in the page, the issuer name, the sector and the
                    JSON-LD Corporation block must all agree with each other and
                    with the canonical rendered universe (the stock hub built by
                    the same run), and an issuer name must carry no transport
                    residue. A dossier may be incomplete; it may never be
                    confidently wrong.

Scope of "checkable text" — deliberately NOT full visible-text extraction:
  * `<style>...</style>` blocks are stripped (CSS keyword collisions, e.g. a
    font named "Infinity", are not a page value).
  * `<script>...</script>` blocks are stripped UNLESS
    `type="application/ld+json"` — JSON-LD is in-scope identity/value
    metadata (Python's `json.dumps` emits a bare, non-standard `NaN` token
    for a NaN float, which is exactly this leak class landing in structured
    data) and must be checked.
  * Everything else — visible markup text AND attribute values, including
    `<meta ... content="...">` — is left in place and scanned as one blob.
    A sentinel value renders inside ordinary tag text (`<small>$nanM</small>`)
    or an attribute (`content="$nanM"`), so there is no benefit to stripping
    tags first, and doing so would cost accuracy for no gain.

False-positive discipline: "nan" (bare, lowercase) is a real English word
(naan/nan bread) and appears in ordinary prose. This guard therefore never
matches bare lowercase "nan" — only the '$'-prefixed dollar-value sentinels
($nan, $nanM, $nanB, $nanK, $nanT) and the exact mixed-case `NaN` token that
Python's json module (and JavaScript) emit for a literal NaN, plus
`Infinity` / `-Infinity` and a bare `inf` token. All bare-word matches are
word-boundary anchored so they cannot fire on a substring inside an ordinary
word (e.g. "financial" contains "nan" as a substring but never as a word).

Run standalone:
    python3 scripts/check_stock_dossier_integrity.py [site_root]
    python3 scripts/check_stock_dossier_integrity.py --site-root site
Exit codes: 0 = clean · 1 = violation(s) found (or vacuous-sparse refusal).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.sparse_guard import refuse_if_vacuous, trees_for  # noqa: E402

DEFAULT_SITE_ROOT = _ROOT / "site"

# ---------------------------------------------------------------------------
# Text preparation
# ---------------------------------------------------------------------------

_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.IGNORECASE | re.DOTALL)
_LD_JSON_TYPE_RE = re.compile(r"""type\s*=\s*["']application/ld\+json["']""", re.IGNORECASE)


def _strip_script(match: re.Match) -> str:
    """Drop a <script> block's tags AND content, unless it is JSON-LD."""
    tag_attrs, content = match.group(1), match.group(2)
    if _LD_JSON_TYPE_RE.search(tag_attrs):
        return content
    return " "


def prepare_checkable_text(html: str) -> str:
    """Strip <style> entirely and <script> (except JSON-LD); keep everything else.

    The remaining blob covers visible markup text, tag attribute values
    (including `<meta content="...">`), and JSON-LD payloads in one pass.
    """
    html = _STYLE_RE.sub(" ", html)
    html = _SCRIPT_RE.sub(_strip_script, html)
    return html


# ---------------------------------------------------------------------------
# Sentinel patterns (machine_sentinel check)
# ---------------------------------------------------------------------------

# $nan / $nanM / $nanB / $nanK / $nanT — the exact shape both fixed formatters
# emitted. Not followed by another letter/digit so "$nanoseconds" (hypothetical
# future copy) would not match, though no such string exists in the estate today.
_DOLLAR_NAN_RE = re.compile(r"\$nan(?:[BMKT])?(?![A-Za-z0-9])")

# Bare NaN — exact mixed case only (Python json.dumps / JavaScript literal).
# Deliberately NOT case-insensitive: lowercase "nan" is the English word for a
# flatbread and appears in legitimate prose ("nan bread"); this guard must not
# flag it. \b anchors on both sides so this cannot match inside a longer word.
_BARE_NAN_RE = re.compile(r"\bNaN\b")

# Infinity / -Infinity — JS/JSON literal for a non-finite float.
_INFINITY_RE = re.compile(r"-?\bInfinity\b")

# Bare "inf" as a rendered value (Python's str(float('inf')) == 'inf').
# Word-boundary anchored; "inf" is not a standalone English word, so this is a
# low false-positive-risk pattern.
_INF_RE = re.compile(r"\binf\b")

_SENTINEL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (_DOLLAR_NAN_RE, "$nan"),
    (_BARE_NAN_RE, "NaN"),
    (_INFINITY_RE, "Infinity"),
    (_INF_RE, "inf"),
]

_SNIPPET_RADIUS = 40


def _snippet(text: str, start: int, end: int) -> str:
    lo = max(0, start - _SNIPPET_RADIUS)
    hi = min(len(text), end + _SNIPPET_RADIUS)
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(text) else ""
    return (prefix + text[lo:hi] + suffix).replace("\n", " ").strip()


def check_machine_sentinel(page: Path, text: str, ctx: dict) -> list[dict]:
    """Non-finite-number leakage: $nan*, bare NaN, Infinity, inf."""
    violations = []
    for pattern, label in _SENTINEL_PATTERNS:
        for match in pattern.finditer(text):
            violations.append({
                "page": page.name,
                "check": "machine_sentinel",
                "pattern": label,
                "snippet": _snippet(text, match.start(), match.end()),
            })
    return violations


# ---------------------------------------------------------------------------
# Identity class
# ---------------------------------------------------------------------------
# The canonical rendered universe is the stock hub that the SAME run produced:
# site/stocks/index.html embeds its rows as [ticker, name, sector, ...] arrays.
# Reading identity from there (rather than from a data plane) is deliberate — it
# asks the one question that matters to a reader: does the hub that linked me here
# and the dossier it linked to agree about who this company is? RWT was listed on
# the hub as "Redwood Trust Inc · Real Estate" while its own dossier printed the
# sector as "—" and described a restaurant in Portland.

_HUB_ROW_RE = re.compile(
    r"\[\s*\"([A-Z0-9][A-Z0-9.\-]{0,9})\"\s*,\s*\"((?:[^\"\\]|\\.)*)\"\s*,\s*\"((?:[^\"\\]|\\.)*)\"")
_JSONLD_BLOCK_RE = re.compile(
    r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
# Transport residue in a generated issuer name: a delimiter at either edge, or a
# pipe anywhere. RMD shipped as "ResMed|" into <title>, the meta description,
# OpenGraph and JSON-LD Corporation.name.
_NAME_RESIDUE_RE = re.compile(r"^[|;,/\s]|[|;,/]\s*$|\|")


def _unescape(s: str) -> str:
    return (s.replace("\\u0026", "&").replace("\\\"", "\"").replace("\\/", "/")
             .replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", "\"")
             .replace("\\\\", "\\").strip())


def load_canonical_universe(hub_path: Path) -> dict[str, dict]:
    """{ticker: {"name", "sector"}} from the rendered stock hub. Empty when the hub
    is missing — the identity class then only self-checks each page."""
    try:
        html = hub_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    out: dict[str, dict] = {}
    for m in _HUB_ROW_RE.finditer(html):
        ticker, name, sector = m.group(1), _unescape(m.group(2)), _unescape(m.group(3))
        if ticker and name:
            out.setdefault(ticker, {"name": name, "sector": sector})
    return out


def _jsonld_corporations(text: str) -> list[dict]:
    """Every Corporation-ish JSON-LD node on the page (flattened through @graph)."""
    import json as _json

    nodes: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("@type") in ("Corporation", "Organization"):
                nodes.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for m in _JSONLD_BLOCK_RE.finditer(text):
        try:
            walk(_json.loads(m.group(1)))
        except (ValueError, TypeError):
            continue
    return nodes


_META_RE = re.compile(
    r"""<meta\s+name=["']mm:([a-z-]+)["']\s+content=["']([^"']*)["']""", re.IGNORECASE)


def _asserted_identity(text: str) -> dict[str, str]:
    """The page's own mm:* identity assertion (see templates/ticker.html.j2)."""
    return {m.group(1).lower(): _unescape(m.group(2)) for m in _META_RE.finditer(text)}


def check_identity(page: Path, text: str, ctx: dict) -> list[dict]:
    """The dossier must not confidently assert the WRONG company.

    Every claim is checked against the canonical rendered universe — the stock hub
    the same run produced — and against the page's own structured data. A page that
    asserts nothing is not failed here (an un-migrated or minimal page is merely
    incomplete); a page that asserts something FALSE is."""
    violations: list[dict] = []
    if page.name == "index.html":
        return violations
    expected = page.stem                       # the filename IS the ticker contract
    universe: dict = ctx.get("universe") or {}
    canon = universe.get(expected) or {}
    asserted = _asserted_identity(text)

    def flag(pattern: str, snippet: str) -> None:
        violations.append({"page": page.name, "check": "identity",
                           "pattern": pattern, "snippet": snippet[:170]})

    # 1. the page's own <title> must name this ticker
    title_m = _TITLE_RE.search(text)
    title = _unescape(title_m.group(1)) if title_m else ""
    if title and not re.search(rf"(?<![A-Z0-9]){re.escape(expected)}(?![A-Z0-9])", title):
        flag("ticker-not-in-title", f"<title> {title!r} does not name {expected!r}")

    # 2. the asserted ticker must be this page's ticker
    if asserted.get("ticker") and asserted["ticker"].upper() != expected.upper():
        flag("ticker-mismatch",
             f"asserts mm:ticker {asserted['ticker']!r}, file is {expected!r}")

    # 3. issuer name: no transport residue, and it must be the canonical issuer
    issuer = asserted.get("issuer", "")
    for label, value in (("asserted", issuer), ("hub", canon.get("name", ""))):
        if value and _NAME_RESIDUE_RE.search(value):
            flag("issuer-name-residue", f"{label} issuer name carries residue: {value!r}")
    if issuer and canon.get("name") and _norm_name(issuer) != _norm_name(canon["name"]):
        flag("issuer-name-mismatch",
             f"page says {issuer!r}, canonical universe says {canon['name']!r}")

    # 4. sector: a fact the canonical universe KNOWS may not be dropped or changed
    canon_sector = _sector_key_for_guard(canon.get("sector", ""))
    page_sector = _sector_key_for_guard(asserted.get("sector", ""))
    if canon_sector and "sector" in asserted:
        if not page_sector:
            flag("sector-lost",
                 f"canonical universe knows {canon['sector']!r}; page asserts none")
        elif page_sector != canon_sector and not asserted.get("sector-conflict"):
            flag("sector-mismatch",
                 f"page says {asserted['sector']!r}, canonical universe says "
                 f"{canon['sector']!r} (and no conflict is recorded)")

    # 5. JSON-LD must agree with the page identity it sits on
    for node in _jsonld_corporations(text):
        sym = node.get("tickerSymbol")
        if isinstance(sym, str) and sym and sym.upper() != expected.upper():
            flag("jsonld-ticker-mismatch",
                 f"JSON-LD tickerSymbol {sym!r} != {expected!r}")
        nm = node.get("name")
        if isinstance(nm, str) and nm:
            if _NAME_RESIDUE_RE.search(nm):
                flag("jsonld-name-residue", f"JSON-LD name {nm!r}")
            ref = canon.get("name") or issuer
            if ref and _norm_name(nm) not in _norm_name(ref) and \
               _norm_name(ref) not in _norm_name(nm):
                flag("jsonld-name-mismatch",
                     f"JSON-LD name {nm!r} disagrees with {ref!r}")

    # 6. a published third-party description must carry auditable provenance
    prov = asserted.get("desc-provenance")
    if prov is not None and (prov == "incomplete" or prov.count(":") < 3):
        flag("description-provenance-missing",
             f"a description is published with no accepted-article linkage ({prov!r})")
    return violations


# The eleven GICS sectors as the dossier prints them, plus the vendor aliases the
# builder folds into them. Kept local and tiny on purpose: this guard must be
# readable as a contract, and must not import the builder it is auditing.
_SECTOR_ALIASES = {
    "information technology": "tech", "technology": "tech", "tech": "tech",
    "health care": "health care", "healthcare": "health care",
    "financials": "financials", "financial": "financials",
    "financial services": "financials",
    "consumer discretionary": "consumer disc.", "consumer cyclical": "consumer disc.",
    "consumer disc.": "consumer disc.",
    "communication services": "comm. services", "comm. services": "comm. services",
    "industrials": "industrials", "consumer staples": "staples", "staples": "staples",
    "energy": "energy", "materials": "materials", "basic materials": "materials",
    "real estate": "real estate", "utilities": "utilities",
}


def _sector_key_for_guard(raw: str) -> str:
    s = str(raw or "").strip().lower()
    if s in ("", "-", "--", "—", "–", "n/a", "na", "none", "nan", "null", "unknown"):
        return ""
    return _SECTOR_ALIASES.get(s, s)


# ONE compiled alternation, longest-first so "consumer discretionary" wins over
# "consumer". Twenty-five separate scans of a ~200 KB page across ~2,000 pages made
# the guard too slow to sit in the render lane, which is where it has to run.
_SECTOR_SCAN_RE = re.compile(
    r"(?<![A-Za-z])(?:%s)(?![A-Za-z])" % "|".join(
        re.escape(a) for a in sorted(_SECTOR_ALIASES, key=len, reverse=True)),
    re.IGNORECASE)


def _shown_sectors(text: str) -> set[str]:
    """Sector names the rendered page actually displays."""
    return {_SECTOR_ALIASES[m.group(0).lower()]
            for m in _SECTOR_SCAN_RE.finditer(text)
            if m.group(0).lower() in _SECTOR_ALIASES}


def _norm_name(s: str) -> str:
    """Company names compare after dropping corporate form, punctuation and case —
    "ResMed Inc." and "ResMed" are the same issuer; "ResMed|" is not a clean name
    but is caught by the residue check, not by this one."""
    s = re.sub(r"[^a-z0-9 ]", " ", str(s or "").lower())
    toks = [t for t in s.split()
            if t not in {"inc", "corp", "corporation", "incorporated", "co",
                         "company", "companies", "ltd", "limited", "plc", "llc",
                         "lp", "sa", "nv", "ag", "se", "holdings", "holding", "the",
                         "class", "cl", "a", "b", "c"}]
    return " ".join(toks)


# Registry of named check functions — each returns a list of violation dicts
# with at least {"page", "check", "snippet"}. Adding an identity-class check
# later means adding an entry here; the scan/report loop is unchanged.
CHECKS: dict[str, Callable[[Path, str, dict], list[dict]]] = {
    "machine_sentinel": check_machine_sentinel,
    "identity": check_identity,
}


# ---------------------------------------------------------------------------
# Scan + report
# ---------------------------------------------------------------------------

def scan(site_root: Path) -> tuple[int, list[dict]]:
    """Run every registered check over every site_root/stocks/*.html page.

    Returns (pages_scanned, violations).
    """
    stocks_dir = Path(site_root) / "stocks"
    pages = sorted(stocks_dir.glob("*.html")) if stocks_dir.is_dir() else []
    ctx = {"universe": load_canonical_universe(stocks_dir / "index.html")}
    violations: list[dict] = []
    for page in pages:
        try:
            html = page.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = prepare_checkable_text(html)
        for check in CHECKS.values():
            violations.extend(check(page, text, ctx))
    return len(pages), violations


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "site_root", nargs="?", default=None,
        help="Site root directory (default: site)",
    )
    parser.add_argument(
        "--site-root", dest="site_root_flag", default=None,
        help="Site root directory (overrides the positional argument)",
    )
    args = parser.parse_args(argv)

    site_root = Path(args.site_root_flag or args.site_root or DEFAULT_SITE_ROOT)

    pages_scanned, violations = scan(site_root)

    refusal = refuse_if_vacuous(
        pages_scanned, trees_for(site_root / "stocks"), "stock-dossier-integrity-vacuous",
    )
    if refusal:
        print(f"stock dossier integrity: REFUSED — {refusal}")
        return 1

    if violations:
        print("stock dossier integrity violations:")
        for v in violations:
            print(f"  {v['page']}  [{v['check']}:{v['pattern']}]  {v['snippet']}")
        pages_hit = len({v["page"] for v in violations})
        print(
            f"stock dossier integrity: FAIL — {len(violations)} violation(s) on "
            f"{pages_hit} page(s), {pages_scanned} page(s) scanned"
        )
        print(
            "::error title=stock-dossier-integrity::"
            f"{len(violations)} integrity violation(s) on {pages_hit} of "
            f"{pages_scanned} rendered ticker page(s): "
            + ", ".join(sorted({v["check"] for v in violations})),
            flush=True,
        )
        return 1

    print(f"stock dossier integrity: OK ({pages_scanned} page(s) scanned, 0 violations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
