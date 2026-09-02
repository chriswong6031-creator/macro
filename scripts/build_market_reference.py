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
KNOWN_OWNER_PAGES: dict[str, set[str]] = {
    "macro.html": {"ms-score", "regime-radar", "dlg-risk", "mx5PopFactors", "release-radar"},
    "aibrief.html": set(),
    "whitehouse.html": {"treasury-watch"},
    "bonds.html": {"curve", "real", "credit"},
    "committee.html": {"cm_rebalance_pulse_section"},
    "us_stocks.html": {"cross-asset-macro"},
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


def validate(raw: dict) -> list[dict]:
    """Validate the raw registry against every MOR1_CONTRACT.md §"Registry taxonomy"
    / DEC §3.3 rule; return the ordered list of entry dicts on success. Raises
    RegistryError (fail-closed) with every violation found."""
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

        # unknown owner page/anchor
        owner = e.get("owner_ref")
        if not owner or not isinstance(owner, str):
            errors.append(f"{where}: owner_ref is required")
        else:
            page, _, frag = owner.partition("#")
            if page not in KNOWN_OWNER_PAGES:
                errors.append(f"{where}: unknown owner page {page!r} in owner_ref {owner!r}")
            elif frag and frag not in KNOWN_OWNER_PAGES[page]:
                errors.append(f"{where}: unknown owner anchor '#{frag}' on page {page!r} in owner_ref {owner!r}")

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


def main() -> int:
    site = config.ROOT / "site"
    try:
        raw = load_registry()
        entries = validate(raw)
    except RegistryError as exc:
        for msg in exc.errors:
            log.error("market_reference registry: %s", msg)
        return 1
    except FileNotFoundError:
        log.error("market_reference registry not found at %s", REGISTRY_PATH)
        return 1

    entries_vm, families_vm, letters = build_view_model(entries)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template(TEMPLATE_NAME).render(
        entries=entries_vm, families=families_vm, letters=letters, generated_at=generated_at,
    )
    out = site / OUT_NAME
    write_page(out, html)
    log.info("wrote %s (%d entries, %.0f KB)", out, len(entries_vm), out.stat().st_size / 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
