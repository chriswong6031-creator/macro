"""SEC EDGAR → per-ticker revenue-by-GEOGRAPHY from 10-K XBRL segment disclosures
(TXI W2 dollar-chain blast channels; the geo_revenue.* fields no site/stockdata/<T>.json
carried before this collector — PR #3431 dropped three blast channels for lack of them).

WHAT THIS PARSES, AND WHY IT CAN'T USE THE COMPANYFACTS/FRAMES API
-----------------------------------------------------------------
SEC's companyfacts + frames APIs (collectors/edgar.py, collectors/edgar_facts.py)
expose only NON-dimensional facts. Geographic segment revenue is DIMENSIONAL —
it hangs off ``srt:StatementGeographicalAxis`` (``us-gaap:...`` in legacy filings) —
so it is ABSENT from those APIs entirely. The only free source is the filing's
extracted XBRL INSTANCE document (the ``*_htm.xml`` in the filing's Archives dir),
which we fetch and parse for the geo-axis contexts directly.

NEVER-ESTIMATE (display-tier accrual law): a ticker emits a geo_revenue block ONLY
when a CLEAN decomposition parses off the instance (one of the three methods in
``_emit``). Everything else is a SKIP with a counted reason — no interpolation, no
sector averages, no LLM anything. Coverage is partial BY DESIGN: large caps mostly
tag the geographic note; many filers don't. Consumers bucket a missing field as
unevaluable. The skip histogram is the printed null (meta.skips).

SCOPE (v1): 10-K / 10-K/A only. Foreign filers that file 20-F/40-F instead of a
10-K are skipped ("no_10k") — their geo note lives in a different taxonomy and is
deferred to a later phase.

Percent convention: foreign_pct / em_pct / by_region[].pct are PERCENT 0-100 floats
(matching the substrate ``_pct`` fields, e.g. risk_sizing.vol_ann_pct = round(100*x, 1)).
em_pct is an explicit LOWER BOUND — only unambiguously-EM members are counted; mixed
regions (AsiaPacific, EMEA, ...) are listed in by_region but never summed into em_pct.

Pipeline per ticker (all keyless, UA only):
  a. CIK from edgar_facts._cik_map() (data/edgar/fundamentals.parquet).
  b. submissions/CIK{:010d}.json → latest 10-K by filingDate.
  c. {acc}/index.json → the instance item (``*_htm.xml``; legacy plain-instance fallback).
  d. GET the instance → parse_instance() → emit or skip.

Drip/state: annual data (cheap steady-state) → resumable capped drip, large-cap-first.
Sidecar data/edgar/_geo_revenue_state.json; merged store data/edgar/geo_revenue.json.
Registered in scripts/collect.py as host='sec', _SLOW member (bounded network drip).
CLI: python3 -m collectors.edgar_geo_revenue [TICKER ...] [--limit N] [--seed N].
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

from collectors.base import Adapter, is_connection_error
from collectors.edgar_facts import _cik_map, _get_json
from lib import config

log = logging.getLogger("edgar_geo_revenue")

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{:010d}.json"
INDEX = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"
DOC = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}"

GROUP = "edgar"
_STORE_FILE = "geo_revenue.json"
_STATE_FILE = "_geo_revenue_state.json"
SCHEMA = "edgar.geo_revenue.v1"

REFRESH_DAYS = 30            # re-hit submissions for checked tickers older than this
MAX_INSTANCE_BYTES = 60 * 1024 * 1024   # 60 MB guard (some instances are huge)
PACE = 0.12                 # SEC fair-access pacing: <10 req/s, after EVERY request
_TEN_K = {"10-K", "10-K/A"}

# ---- XBRL namespaces (namespace-agnostic where the taxonomy migrated) -----------
_XBRLI = "http://www.xbrl.org/2003/instance"
_XBRLDI = "http://xbrl.org/2006/xbrldi"

# Revenue concepts, PRIORITY ORDER (earlier wins on a tie in geo-fact count).
# us-gaap namespace only (ns URI contains "fasb.org/us-gaap").
REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenuesNetOfInterestExpense",
]

# --- member classification sets (normalized key = casefold; see _norm) -----------
# US member keys (revenue attributed to the United States).
US_MEMBERS = {"us", "unitedstates", "unitedstatesofamerica", "domestic"}
# Foreign-AGGREGATE members: a single line standing for "everything non-US".
FOREIGN_AGG_MEMBERS = {
    "nonus", "international", "foreign", "foreigncountries",
    "outsideunitedstates", "restofworld", "restoftheworld",
    "allothercountries", "otherforeigncountries",
}
# Excluded members: never summed; their PRESENCE forces a plain total to be required
# (a member_sum path that silently drops them would misstate the denominator).
EXCLUDED_MEMBERS = {"eliminations", "corporate", "corporateandother",
                    "intersegmenteliminations"}
_EXCLUDED_PREFIX = ("reconciling",)   # Reconciling* (prefix match on normalized key)

# EM ISO2 (MSCI EM 2025-ish + major frontier; conservative — em_pct is a lower bound).
EM_COUNTRIES = {
    "CN", "TW", "KR", "IN", "BR", "MX", "SA", "ZA", "TH", "ID", "MY", "PL", "TR",
    "PH", "CL", "PE", "GR", "HU", "CZ", "EG", "QA", "AE", "KW", "CO", "AR", "VN",
    "NG", "PK", "BD", "RO", "MA", "KE",
}
# DM ISO2 (developed markets; used only to classify by_region cls, not to sum).
DM_COUNTRIES = {
    "US", "CA", "GB", "DE", "FR", "IT", "ES", "NL", "CH", "SE", "DK", "NO", "FI",
    "BE", "AT", "IE", "PT", "IL", "JP", "AU", "NZ", "HK", "SG", "LU",
}
# Named regions → EM (counted into em_pct as a lower bound).
EM_REGIONS = {
    "greaterchina", "china", "latinamerica", "southamerica", "middleeast",
    "africa", "middleeastandafrica", "southeastasia", "emergingmarkets",
    "india", "brazil", "mexico", "southkorea", "korea",
}
# Named regions → DM (classified DM; NOT summed into em_pct).
DM_REGIONS = {
    "europe", "westerneurope", "japan", "canada", "australia", "unitedkingdom",
    "germany", "france", "switzerland", "netherlands",
}
# Everything else (AsiaPacific, APAC, Asia, EMEA, Americas, NorthAmerica,
# aggregates, unknown custom members) → cls "mixed"/"other" — NEVER into em_pct.


# ================================================================= helpers =======
def _store_path() -> Path:
    p = config.data_dir() / GROUP / _STORE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _state_path() -> Path:
    p = config.data_dir() / GROUP / _STATE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _archive_ua() -> str:
    """www.sec.gov/Archives enforces SEC fair-access strictly: the UA MUST carry a
    contact email (the data.sec.gov API is lenient and does not). Same idiom as
    collectors/edgar_headcount._archive_ua."""
    ua = config.load()["edgar"]["user_agent"]
    return ua if "@" in ua else ua + " macro-dashboard@users.noreply.github.com"


def _local(tag: str) -> str:
    """Local name of a possibly-namespaced ElementTree tag ('{ns}Local' → 'Local')."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _ns_uri(tag: str) -> str:
    """Namespace URI of a '{ns}Local' tag, '' if unqualified."""
    return tag[1:tag.rindex("}")] if tag.startswith("{") else ""


def _split_qname(qname: str, nsmap: dict[str, str]) -> tuple[str, str]:
    """A QName attribute value 'prefix:Local' → (namespace_uri, Local) using nsmap;
    unprefixed → ('', value). Used for explicit-member dimension + member values."""
    if ":" in qname:
        prefix, local = qname.split(":", 1)
        return nsmap.get(prefix, ""), local
    return "", qname


def _norm(key: str) -> str:
    """Normalized comparison key: casefold, drop non-alnum. 'Non-US' → 'nonus',
    'United States' → 'unitedstates'."""
    return "".join(ch for ch in key.casefold() if ch.isalnum())


def _member_key(member_local: str, member_ns: str) -> str:
    """Map an explicit-member QName to a member KEY per §4.

    country:XX  → the ISO2 code ('country:BR' → 'BR'). The country taxonomy uses
                  URI http://xbrl.sec.gov/country/... with two-letter local names.
    otherwise   → the localname with a trailing 'Member' stripped
                  ('GreaterChinaMember' → 'GreaterChina', 'US-GAAP:CountryUS' → 'US').
    """
    local = member_local
    # country:XX members: namespace is the SEC country taxonomy, local is the ISO2.
    if "xbrl.sec.gov/country" in member_ns or ("/country/" in member_ns):
        return local.upper()
    if local.endswith("Member"):
        local = local[: -len("Member")]
    # us-gaap CountryXX style (e.g. "CountryUS") → strip the "Country" prefix to ISO2.
    return local


def _label(key: str) -> str:
    """Human label for a member key: space a CamelCase key ('GreaterChina' →
    'Greater China'); ISO2 country codes are kept as-is."""
    if len(key) <= 3 and key.isupper():
        return key
    out = []
    for i, ch in enumerate(key):
        if i and ch.isupper() and (not key[i - 1].isupper()):
            out.append(" ")
        out.append(ch)
    return "".join(out).strip()


def _classify(key: str) -> str:
    """Classify a member key into us | dm | em | mixed for by_region.cls and em_pct.

    Only 'em' members are summed into em_pct (a lower bound). ISO2 codes route via
    the EM/DM country sets; named regions via the EM/DM region sets; everything else
    is 'mixed' (AsiaPacific, EMEA, Americas, unknown customs) — listed, never summed.
    """
    n = _norm(key)
    if n in US_MEMBERS:
        return "us"
    # ISO2 country code (2 letters, upper).
    if len(key) == 2 and key.isalpha() and key.isupper():
        if key in EM_COUNTRIES:
            return "em"
        if key in DM_COUNTRIES:
            return "dm"
        return "mixed"
    if n in EM_REGIONS:
        return "em"
    if n in DM_REGIONS:
        return "dm"
    return "mixed"


def _is_excluded(key: str) -> bool:
    n = _norm(key)
    return n in EXCLUDED_MEMBERS or n.startswith(_EXCLUDED_PREFIX)


def _is_us(key: str) -> bool:
    return _norm(key) in US_MEMBERS


def _is_foreign_agg(key: str) -> bool:
    return _norm(key) in FOREIGN_AGG_MEMBERS


# ============================================================ instance parse ======
def parse_instance(xml_bytes: bytes) -> dict:
    """Parse an extracted XBRL instance document for revenue-by-geography.

    PURE — raises nothing; returns either an emitted block
    ``{"ok": True, "foreign_pct": ..., ...}`` or ``{"ok": False, "reason": <skip>}``.
    Tests feed fixture bytes directly. See module docstring + §3/§4 of the spec.

    QName-valued attribute TEXT (dimension="srt:StatementGeographicalAxis",
    explicitMember="country:BR") is NOT expanded by ElementTree, so we register the
    doc's prefix→uri map here (self-sufficient for the direct test path) before parse.
    """
    _register_nsmap(xml_bytes)
    try:
        root = ET.fromstring(xml_bytes)
    except Exception as e:  # noqa: BLE001 — malformed instance → skip, never raise
        return {"ok": False, "reason": "parse_error", "detail": str(e)[:120]}

    # ---- contexts: id → {"end","start","instant","dims":[(dim_local,mem_key)],"tainted"}
    contexts: dict[str, dict] = {}
    # ---- units: id → is_usd
    usd_units: set[str] = set()
    # ---- facts: list of {"concept","context","unit","val"} (us-gaap revenue only)
    facts: list[dict] = []
    dei: dict[str, str] = {}

    for el in root:
        tag_local = _local(el.tag)
        ns = _ns_uri(el.tag)
        if ns == _XBRLI and tag_local == "context":
            contexts[el.get("id", "")] = _parse_context(el)
        elif ns == _XBRLI and tag_local == "unit":
            if _unit_is_usd(el):
                usd_units.add(el.get("id", ""))
        elif "fasb.org/us-gaap" in ns and tag_local in REVENUE_CONCEPTS:
            f = _parse_fact(el, tag_local)
            if f is not None:
                facts.append(f)
        elif "xbrl.sec.gov/dei" in ns and tag_local in (
            "DocumentPeriodEndDate", "DocumentFiscalYearFocus", "DocumentType",
        ):
            txt = (el.text or "").strip()
            if txt:
                dei[tag_local] = txt

    # ---- dedupe duplicate (concept, context) facts: keep first; log >0.5% disagreement
    seen: dict[tuple[str, str], float] = {}
    deduped: list[dict] = []
    for f in facts:
        k = (f["concept"], f["context"])
        if k in seen:
            prev = seen[k]
            if prev and abs(f["val"] - prev) / abs(prev) > 0.005:
                log.debug("geo_revenue dup disagree %s/%s: %s vs %s",
                          f["concept"], f["context"], prev, f["val"])
            continue
        seen[k] = f["val"]
        deduped.append(f)
    facts = deduped

    # ---- fiscal-year end + FY-duration context set ------------------------------
    doc_end = dei.get("DocumentPeriodEndDate")
    dur_ctx = {cid: c for cid, c in contexts.items()
               if c.get("start") and c.get("end") and _fy_duration(c)}
    if not doc_end:
        # fallback: max end among FY-duration contexts.
        ends = [c["end"] for c in dur_ctx.values()]
        doc_end = max(ends) if ends else None
    if not doc_end:
        return {"ok": False, "reason": "no_denominator"}

    fy_ctx = {cid: c for cid, c in dur_ctx.items() if c["end"] == doc_end}

    # geo contexts: FY-duration + end==doc_end + EXACTLY ONE dim on the geo axis + untainted.
    geo_ctx = {cid: c for cid, c in fy_ctx.items()
               if not c["tainted"] and len(c["dims"]) == 1
               and _norm_axis(c["dims"][0][0]) == "statementgeographicalaxis"}
    # plain contexts: FY-duration + end==doc_end + zero dims + untainted (the total).
    plain_ctx = {cid for cid, c in fy_ctx.items()
                 if not c["tainted"] and not c["dims"]}

    if not geo_ctx:
        return {"ok": False, "reason": "no_geo_axis"}

    # ---- choose the concept: most geo facts in USD units, priority-order on ties ---
    usd_ctx_ok = {cid for cid in geo_ctx}
    by_concept: dict[str, list[dict]] = {}
    for f in facts:
        if f["unit"] in usd_units and f["context"] in usd_ctx_ok:
            by_concept.setdefault(f["concept"], []).append(f)
    if not by_concept:
        return {"ok": False, "reason": "no_denominator"}

    def _concept_rank(c: str) -> tuple[int, int]:
        # more geo facts wins; ties → earlier in REVENUE_CONCEPTS (smaller index).
        return (len(by_concept[c]), -REVENUE_CONCEPTS.index(c))

    concept = max(by_concept, key=_concept_rank)
    geo_facts = by_concept[concept]

    # members: {member_key: value} summed across geo contexts of the chosen concept.
    members: dict[str, float] = {}
    for f in geo_facts:
        ctx = geo_ctx[f["context"]]
        key = ctx["dims"][0][1]
        members[key] = members.get(key, 0.0) + f["val"]

    # ---- total from a plain (zero-dim) context, same concept, USD ---------------
    total = None
    for f in facts:
        if (f["concept"] == concept and f["unit"] in usd_units
                and f["context"] in plain_ctx):
            total = f["val"]
            break

    return _emit(members, total, concept, doc_end, dei)


def _parse_context(ctx_el: ET.Element) -> dict:
    """One <context> → {"start","end","instant","dims":[(dim_local, member_key)],"tainted"}.

    Explicit dims are read from BOTH <segment> and <scenario>. A typedMember in
    either marks the context TAINTED (extra-dim, excluded from geo selection)."""
    start = end = instant = None
    dims: list[tuple[str, str]] = []
    tainted = False
    for period in ctx_el:
        if _local(period.tag) != "period":
            continue
        for p in period:
            pl = _local(p.tag)
            if pl == "startDate":
                start = (p.text or "").strip()
            elif pl == "endDate":
                end = (p.text or "").strip()
            elif pl == "instant":
                instant = (p.text or "").strip()
    # segment lives at <context><entity><segment>; scenario at <context><scenario>
    # (one level deeper vs a direct child). Walk the whole subtree for both so nesting
    # depth never matters. iter() includes ctx_el itself; that's fine (not a container).
    for container in ctx_el.iter():
        cl = _local(container.tag)
        if cl not in ("segment", "scenario"):
            continue
        for m in container:
            ml = _local(m.tag)
            if ml == "explicitMember":
                nsmap = _elem_nsmap(m)
                dim_ns, dim_local = _split_qname(m.get("dimension", ""), nsmap)
                mem_ns, mem_local = _split_qname((m.text or "").strip(), nsmap)
                dims.append((dim_local, _member_key(mem_local, mem_ns)))
            elif ml == "typedMember":
                tainted = True
    if instant and not end:
        end = instant
    return {"start": start, "end": end, "instant": instant,
            "dims": dims, "tainted": tainted}


def _elem_nsmap(el: ET.Element) -> dict[str, str]:
    """Prefix→URI map visible at *el*. ElementTree doesn't expose per-element nsmap,
    so we reconstruct it from the parser-registered global map plus this element's
    own declared namespaces (captured by the module-level _NS_REGISTRY on parse)."""
    # ElementTree stores xmlns declarations as attributes only when it can't resolve
    # them to a prefix; in practice the QName prefixes we need (srt, country, us-gaap)
    # are in the global registry populated during fromstring. Fall back to that.
    return dict(_NS_REGISTRY)


# ElementTree expands element/attr TAGS to {uri}local but does NOT expand QName-valued
# ATTRIBUTE TEXT (e.g. dimension="srt:StatementGeographicalAxis"), so we must resolve
# those prefixes ourselves. We capture the doc's prefix→uri map at parse time.
_NS_REGISTRY: dict[str, str] = {}


def _parse_fact(el: ET.Element, concept_local: str) -> dict | None:
    """A us-gaap revenue element → {"concept","context","unit","val"} or None (nil/
    non-numeric/no context)."""
    # xsi:nil="true" → skip.
    for k, v in el.attrib.items():
        if _local(k) == "nil" and str(v).lower() == "true":
            return None
    ctx = el.get("contextRef")
    unit = el.get("unitRef")
    if not ctx or not unit:
        return None
    txt = (el.text or "").strip()
    if not txt:
        return None
    try:
        val = float(txt)
    except (TypeError, ValueError):
        return None
    return {"concept": concept_local, "context": ctx, "unit": unit, "val": val}


def _unit_is_usd(unit_el: ET.Element) -> bool:
    """A <unit> is USD when its <measure> text ends with ':USD' or equals 'USD'."""
    for m in unit_el.iter():
        if _local(m.tag) == "measure":
            txt = (m.text or "").strip()
            if txt.endswith(":USD") or txt == "USD" or txt.rsplit(":", 1)[-1] == "USD":
                return True
    return False


def _norm_axis(dim_local: str) -> str:
    return dim_local.casefold()


def _fy_duration(ctx: dict) -> bool:
    """True when start→end spans a full fiscal year (300–400 days)."""
    try:
        days = (pd.to_datetime(ctx["end"]) - pd.to_datetime(ctx["start"])).days
    except Exception:  # noqa: BLE001
        return False
    return 300 <= days <= 400


def _emit(members: dict[str, float], total: float | None, concept: str,
          doc_end: str, dei: dict[str, str]) -> dict:
    """Apply the three emission methods (§4) to classified members + optional total.

    Returns an emitted block on success, or {"ok": False, "reason": <skip>}.
    """
    if not members:
        return {"ok": False, "reason": "no_geo_axis"}

    excluded_present = any(_is_excluded(k) for k in members)
    non_excl = {k: v for k, v in members.items() if not _is_excluded(k)}
    if not non_excl:
        return {"ok": False, "reason": "no_denominator"}

    us_val = sum(v for k, v in non_excl.items() if _is_us(k))
    has_us = any(_is_us(k) for k in non_excl)
    fa_val = sum(v for k, v in non_excl.items() if _is_foreign_agg(k))
    has_fa = any(_is_foreign_agg(k) for k in non_excl)

    method = denom = foreign_pct = None
    if total is not None and total > 0 and has_us:
        method, denom, foreign_pct = "us_member", total, 100.0 * (total - us_val) / total
    elif total is not None and total > 0 and has_fa:
        method, denom, foreign_pct = "foreign_agg", total, 100.0 * fa_val / total
    else:
        # member_sum: NO usable plain total. Require ≥2 non-excluded members incl ≥1
        # US; no negative members; no excluded members present at all.
        if total is None or total <= 0:
            if excluded_present:
                return {"ok": False, "reason": "eliminations_no_total"}
            if len(non_excl) < 2 or not has_us:
                return {"ok": False, "reason": "no_denominator"}
            if any(v < 0 for v in non_excl.values()):
                return {"ok": False, "reason": "no_denominator"}
            denom = sum(non_excl.values())
            if denom <= 0:
                return {"ok": False, "reason": "no_denominator"}
            method, foreign_pct = "member_sum", 100.0 * (denom - us_val) / denom
        else:
            # total present but no US and no foreign-agg member to anchor it.
            return {"ok": False, "reason": "no_denominator"}

    # sanity: land in [-0.5, 100.5]; clamp the ≤0.5pp overshoot, else skip.
    if foreign_pct < -0.5 or foreign_pct > 100.5:
        return {"ok": False, "reason": "out_of_range"}
    foreign_pct = min(100.0, max(0.0, foreign_pct))

    # em_pct (lower bound): only unambiguously-EM members, same denominator, ≥1 em.
    em_val = sum(v for k, v in non_excl.items() if _classify(k) == "em")
    has_em = any(_classify(k) == "em" for k in non_excl)
    em_pct = None
    if has_em and denom and denom > 0:
        em_pct = 100.0 * em_val / denom
        if em_pct > foreign_pct + 0.5:
            return {"ok": False, "reason": "em_gt_foreign"}
        em_pct = round(min(em_pct, foreign_pct), 1)

    # by_region: non-excluded members, cls, pct of denom; sorted desc, cap 12.
    by_region = []
    for k, v in non_excl.items():
        cls = "foreign_total" if _is_foreign_agg(k) else _classify(k)
        by_region.append({"key": k, "label": _label(k), "cls": cls,
                          "pct": round(100.0 * v / denom, 1) if denom else 0.0})
    by_region.sort(key=lambda r: r["pct"], reverse=True)
    by_region = by_region[:12]

    try:
        fy = int(dei.get("DocumentFiscalYearFocus") or doc_end[:4])
    except (TypeError, ValueError):
        fy = int(doc_end[:4])

    out = {
        "ok": True,
        "foreign_pct": round(foreign_pct, 1),
        "by_region": by_region,
        "asof": doc_end,
        "fy": fy,
        "method": method,
        "concept": concept,
    }
    if em_pct is not None:
        out["em_pct"] = em_pct
    return out


# ========================================================= fetch pipeline =========
def _register_nsmap(xml_bytes: bytes) -> None:
    """Populate _NS_REGISTRY (prefix→uri) from the instance root's declarations so
    QName-valued attribute TEXT (dimension/member) resolves. iterparse start-ns events
    surface every xmlns declaration in document order."""
    global _NS_REGISTRY
    reg: dict[str, str] = {}
    try:
        import io
        for event, node in ET.iterparse(io.BytesIO(xml_bytes), events=("start-ns",)):
            prefix, uri = node
            reg.setdefault(prefix, uri)
    except Exception:  # noqa: BLE001 — best effort; empty registry ⇒ unprefixed only
        pass
    _NS_REGISTRY = reg


def _latest_10k(cik: int) -> dict | None:
    """Latest 10-K/10-K/A for a filer from submissions. Returns
    {"accession","primaryDocument","filingDate","reportDate","form"} or None."""
    sub = _get_json(SUBMISSIONS.format(cik))
    time.sleep(PACE)
    if not sub:
        return None
    rec = (sub.get("filings") or {}).get("recent") or {}
    forms = rec.get("form") or []
    accs = rec.get("accessionNumber") or []
    prim = rec.get("primaryDocument") or []
    fdates = rec.get("filingDate") or []
    rdates = rec.get("reportDate") or []
    best = None
    for i, form in enumerate(forms):
        if form not in _TEN_K:
            continue
        try:
            fdate = fdates[i]
            acc = accs[i]
        except IndexError:
            continue
        cand = {
            "accession": acc,
            "primaryDocument": prim[i] if i < len(prim) else "",
            "filingDate": fdate,
            "reportDate": rdates[i] if i < len(rdates) else "",
            "form": form,
        }
        if best is None or (fdate or "") > (best["filingDate"] or ""):
            best = cand
    return best


def _instance_name(cik: int, acc_nodash: str) -> str | None:
    """The extracted XBRL instance filename in a filing's Archives dir.

    Primary: the item ending '_htm.xml'. Fallback (pre-2019 plain instances): a
    '.xml' item that is NOT a linkbase (_cal/_def/_lab/_pre.xml), NOT an R*.xml
    viewer file, NOT Financial_Report*. Returns None when neither is present.
    """
    idx = _get_json(INDEX.format(cik=cik, acc=acc_nodash))
    time.sleep(PACE)
    if not idx:
        return None
    items = ((idx.get("directory") or {}).get("item")) or []
    names = [it.get("name", "") for it in items if it.get("name")]
    for nm in names:
        if nm.endswith("_htm.xml"):
            return nm
    for nm in names:
        low = nm.lower()
        if not low.endswith(".xml"):
            continue
        if any(low.endswith(sfx) for sfx in ("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml")):
            continue
        base = nm.rsplit("/", 1)[-1]
        if base.startswith("R") and base[1:2].isdigit():
            continue
        if base.startswith("Financial_Report"):
            continue
        return nm
    return None


def _fetch_instance(cik: int, acc_nodash: str, name: str) -> bytes | None:
    """GET the instance document with the archive UA + a 60MB size guard.
    Returns the bytes, or None on a size/HTTP failure (skip). Raises only on a
    connection-level error (host unreachable) so the drip can fail fast."""
    import requests
    url = DOC.format(cik=cik, acc=acc_nodash, name=name)
    ua = _archive_ua()
    try:
        r = requests.get(url, headers={"User-Agent": ua,
                                       "Accept-Encoding": "gzip, deflate"}, timeout=60)
        time.sleep(PACE)
        if r.status_code != 200 or not r.content:
            return None
        cl = r.headers.get("Content-Length")
        if cl and cl.isdigit() and int(cl) > MAX_INSTANCE_BYTES:
            return b""   # sentinel: too large (caller maps to "instance_too_large")
        if len(r.content) > MAX_INSTANCE_BYTES:
            return b""
        return r.content
    except Exception as e:  # noqa: BLE001
        if is_connection_error(e):
            raise
        log.debug("geo_revenue: instance GET failed %s: %s", url[-40:], e)
        return None


def _geo_for(cik: int) -> dict:
    """Full per-ticker pipeline (b→d). Returns either an emitted block augmented with
    provenance (accession/source), or {"ok": False, "reason": <skip>, "accession": ...}.
    Never raises except on connection-level errors (propagated to fail the drip fast)."""
    filing = _latest_10k(cik)
    if not filing:
        return {"ok": False, "reason": "no_10k", "accession": None}
    acc = filing["accession"]
    acc_nodash = acc.replace("-", "")
    name = _instance_name(cik, acc_nodash)
    if not name:
        return {"ok": False, "reason": "no_instance", "accession": acc}
    xml_bytes = _fetch_instance(cik, acc_nodash, name)
    if xml_bytes is None:
        return {"ok": False, "reason": "fetch_error", "accession": acc}
    if xml_bytes == b"":
        return {"ok": False, "reason": "instance_too_large", "accession": acc}
    parsed = parse_instance(xml_bytes)
    parsed["accession"] = acc
    if parsed.get("ok"):
        parsed["source"] = f"10-K {filing.get('reportDate') or filing.get('filingDate')}"
    return parsed


# ================================================================ drip ============
def _load_state() -> dict:
    p = _state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()) or {}
    except Exception:  # noqa: BLE001
        return {}


def _size_ordered_universe(cik: dict[str, int]) -> list[str]:
    """Universe ordered LARGE-CAP FIRST by a size column in fundamentals.parquet
    (revenue desc, then assets desc); alphabetical fallback. Only tickers with a CIK."""
    fp = config.data_dir() / GROUP / "fundamentals.parquet"
    ordered: list[str] = []
    try:
        df = pd.read_parquet(fp, columns=["revenue", "assets"])
        size = df.get("revenue")
        if size is None or size.notna().sum() == 0:
            size = df.get("assets")
        df = df.assign(_size=size)
        ordered = [str(t) for t in df.sort_values("_size", ascending=False,
                                                   na_position="last").index]
    except Exception:  # noqa: BLE001
        ordered = []
    # keep only ticker with a CIK, then append any CIK-tickers not in the size frame.
    seen = set()
    out = []
    for t in ordered:
        if t in cik and t not in seen:
            out.append(t)
            seen.add(t)
    for t in sorted(cik):
        if t not in seen:
            out.append(t)
            seen.add(t)
    return out


def _emit_block(parsed: dict) -> dict:
    """Project a successful _geo_for result to the exact stored block shape (§5):
    optional keys absent when not derivable — never null-padded."""
    block = {
        "foreign_pct": parsed["foreign_pct"],
        "asof": parsed["asof"],
        "source": parsed["source"],
        "fy": parsed["fy"],
        "accession": parsed["accession"],
        "method": parsed["method"],
        "concept": parsed["concept"],
    }
    if parsed.get("em_pct") is not None:
        block["em_pct"] = parsed["em_pct"]
    if parsed.get("by_region"):
        block["by_region"] = parsed["by_region"]
    return block


def fetch_geo_revenue(force: bool = False, max_new: int = 60,
                      tickers: list[str] | None = None) -> dict:
    """Resumable capped drip. Merges results into data/edgar/geo_revenue.json and
    returns that document. Best-effort — connection errors abort early (caller-safe).

    Work order (large-cap-first): (1) never-checked tickers, full fetch capped at
    max_new; (2) checked tickers staler than REFRESH_DAYS → re-hit submissions ONLY,
    re-parse only when the latest 10-K accession differs (capped 3×max_new).
    """
    cik = _cik_map()
    state = _load_state()
    now_iso = datetime.now(timezone.utc).isoformat()

    if tickers:                       # explicit force-fetch list (CLI bare tickers)
        universe = [t for t in tickers if t in cik]
        never = universe if force else [t for t in universe if t not in state]
        recheck: list[str] = []
    else:
        universe = _size_ordered_universe(cik)
        never = [t for t in universe if t not in state][:max_new]
        recheck = [t for t in universe if t in state
                   and _stale(state[t].get("checked"))][: 3 * max_new]

    def _do_full(t: str) -> None:
        try:
            parsed = _geo_for(cik[t])
        except Exception as e:  # noqa: BLE001 — connection error → stop the drip
            if is_connection_error(e):
                raise
            log.debug("geo_revenue %s failed: %s", t, e)
            state[t] = {"checked": now_iso, "accession": None, "status": "fetch_error"}
            return
        state[t] = {
            "checked": now_iso,
            "accession": parsed.get("accession"),
            "status": "ok" if parsed.get("ok") else parsed.get("reason", "parse_error"),
        }
        if parsed.get("ok"):
            state[t]["block"] = _emit_block(parsed)

    for t in never:
        _do_full(t)

    for t in recheck:
        # re-hit submissions ONLY; re-parse only if the latest accession changed.
        try:
            filing = _latest_10k(cik[t])
        except Exception as e:  # noqa: BLE001
            if is_connection_error(e):
                raise
            continue
        prev_acc = state.get(t, {}).get("accession")
        if filing and filing["accession"] != prev_acc:
            _do_full(t)
        else:
            state[t]["checked"] = now_iso   # touch so it isn't re-hit next run

    _save_state(state)
    doc = _rebuild_store(state, cik, now_iso)
    _store_path().write_text(json.dumps(doc, indent=0, separators=(",", ":")))
    return doc


def _stale(checked_iso: str | None) -> bool:
    if not checked_iso:
        return True
    try:
        return (datetime.now(timezone.utc)
                - pd.to_datetime(checked_iso).to_pydatetime()).days > REFRESH_DAYS
    except Exception:  # noqa: BLE001
        return True


def _save_state(state: dict) -> None:
    _state_path().write_text(json.dumps(state, indent=0, separators=(",", ":")))


def _rebuild_store(state: dict, cik: dict[str, int], now_iso: str) -> dict:
    """Compose data/edgar/geo_revenue.json from state. meta.skips is recomputed from
    state each run (coverage honesty — the skip histogram is the printed null)."""
    by_ticker = {t: s["block"] for t, s in state.items()
                 if s.get("status") == "ok" and s.get("block")}
    skips: dict[str, int] = {}
    parsed = 0
    for s in state.values():
        st = s.get("status")
        if st == "ok":
            parsed += 1
        elif st:
            skips[st] = skips.get(st, 0) + 1
    return {
        "schema": SCHEMA,
        "updated": now_iso,
        "by_ticker": by_ticker,
        "meta": {
            "universe": len(cik),
            "attempted": len(state),
            "parsed": parsed,
            "skips": dict(sorted(skips.items(), key=lambda kv: -kv[1])),
        },
    }


# =============================================================== adapter ==========
class GeoRevenueAdapter(Adapter):
    """Bounded SEC drip: per-ticker revenue-by-geography from 10-K XBRL instances.
    Writes its own store (data/edgar/geo_revenue.json) and returns a heartbeat frame
    so the circuit-breaker runner (store.upsert) has a series to persist — same
    contract shape as EdgarDilutionAdapter. TXI W2 re-enable (PR #3431 blast channels).
    """

    name = "geo_revenue"
    group = GROUP
    stale_after_days = 40      # annual data; the drip touches ~60 new names/night

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        max_new = 200 if full_history else 60
        doc = fetch_geo_revenue(force=False, max_new=max_new)
        meta = doc.get("meta", {})
        hb = pd.DataFrame(
            {"parsed": [meta.get("parsed", 0)], "attempted": [meta.get("attempted", 0)]},
            index=[pd.Timestamp(datetime.now(timezone.utc).date())],
        )
        return {"geo_revenue__ingest": hb}


# =================================================================== CLI ==========
def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import sys
    args = sys.argv[1:]
    limit: int | None = None
    seed: int | None = None
    if "--limit" in args:
        i = args.index("--limit")
        limit = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    if "--seed" in args:
        i = args.index("--seed")
        seed = int(args[i + 1])
        args = args[:i] + args[i + 2:]

    if seed is not None:
        # force=False sweep over the first N of the large-cap-first universe.
        cik = _cik_map()
        uni = _size_ordered_universe(cik)[:seed]
        doc = fetch_geo_revenue(force=False, max_new=seed, tickers=uni)
        print(json.dumps(doc.get("meta", {}), indent=2))
        return 0

    tickers = [t.upper() for t in args] or ["AAPL"]
    max_new = limit if limit is not None else len(tickers)
    doc = fetch_geo_revenue(force=True, max_new=max_new, tickers=tickers)
    by_ticker = doc.get("by_ticker", {})
    state = _load_state()
    for t in tickers:
        print(f"\n=== {t} ===")
        if t in by_ticker:
            print(json.dumps(by_ticker[t], indent=2))
        else:
            reason = state.get(t, {}).get("status", "not_fetched")
            print(f"  SKIP: {reason}")
    print("\n--- meta ---")
    print(json.dumps(doc.get("meta", {}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
