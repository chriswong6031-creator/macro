"""Per-stock identity + business description for the analyzer's Profile panel
(Phase 2 of research/STOCK_FUNDAMENTALS_PLAN.md).

Two keyless, free, near-static sources — best-effort and cached (refreshed
slowly; descriptions barely move):

  SEC EDGAR submissions   data.sec.gov/submissions/CIK{10}.json
                          → SIC industry text, listing exchange, HQ city/state
  Wikipedia REST summary  en.wikipedia.org/api/rest_v1/page/summary/{title}
                          (resolved via the opensearch endpoint)
                          → a one-paragraph "what it does" business description

Writes data/profile/profiles.parquet (ticker-indexed: description, sic_description,
exchange, hq, name, source, as_of, wiki_title). engine/stock_fundamentals reads it into the
Profile block; a missing row just leaves those chips empty (the page already
guards for that). Resumable: only tickers absent from the cache (or older than
refresh_days) are fetched, capped at max_new per run, so a weekly job drips
through the universe without hammering either host. Nothing here can fail the
build — callers wrap it and per-ticker errors are skipped.

HONESTY (shown on the page): descriptions are Wikipedia extracts (community-
sourced, may lag); the SEC business address is the filing address, not
necessarily operational HQ; SIC is the SEC industry code, not a GICS sub-industry.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# Wikipedia asks for a descriptive UA with contact. SEC's data.sec.gov blocks
# (403) the email-laden form but accepts the simple edgar UA already in config —
# so SEC reuses config.edgar.user_agent, Wikipedia uses WIKI_UA.
WIKI_UA = "macro-dashboard research (chriswong6031-creator) macro-dashboard@users.noreply.github.com"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{:010d}.json"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
# limit=5 (not 1): opensearch's top hit is often a namesake (a lawsuit, a town,
# a chemical) rather than the company, so we pull a handful and validate.
WIKI_OPENSEARCH = ("https://en.wikipedia.org/w/api.php?action=opensearch"
                   "&search={}&limit=5&namespace=0&format=json")
REFRESH_DAYS = 120

# Trailing corporate-form words stripped to build a bare "core" search/match term
# ("Microsoft Corp" -> "Microsoft", "CVR Energy, Inc." -> "CVR Energy").
_CORE_SUFFIX = {"corp", "corporation", "inc", "incorporated", "co", "cos",
                "company", "companies", "ltd", "limited", "plc", "llc", "lp",
                "lllp", "sa", "nv", "ag", "se", "holdings", "holding"}
# Generic words ignored when checking a Wikipedia title actually names the company.
_NAME_STOP = _CORE_SUFFIX | {"the", "of", "and", "for", "group", "trust",
                             "international", "american", "global", "new",
                             "class", "cl"}
# Industry/descriptor words too generic to anchor a name match on their own — else
# "CVR Energy" matches "Cove Energy plc" on the shared "energy". A distinctive
# token (a brand) still anchors; an exact name still matches via core-substring.
_GENERIC_TOK = {
    "energy", "power", "electric", "electrical", "gas", "petroleum", "oil",
    "technologies", "technology", "systems", "system", "financial", "finance",
    "solutions", "services", "service", "industries", "industrial", "resources",
    "resource", "partners", "properties", "property", "realty", "brands",
    "networks", "communications", "pharmaceuticals", "pharmaceutical",
    "biosciences", "therapeutics", "motors", "materials", "products", "media",
    "entertainment", "foods", "retail", "stores", "bancshares", "bancorp",
    "insurance", "health", "healthcare", "digital", "national", "general",
    "united", "standard", "enterprises", "ventures", "laboratories", "pharma",
    "data", "first", "mortgage", "capital", "bank", "holdings",
}
# An organization-type keyword in a page's short description (or extract lead)
# is what separates the company from a same-named court case / place / chemical.
_ORG_KW = (
    "compan", "corporat", "incorporat", "holding", "conglomerate", "multinational",
    "manufactur", "retail", "bank", "insur", "brokerage", "broker", "reit",
    "real estate investment trust", "enterprise", "firm", "business", "airline",
    "utilit", "producer", "provider", "operator", "developer", "supplier", "maker",
    "distributor", "distribution", "fintech", "pharmaceutic", "biotechnolog",
    "biopharma", "technolog", "financ", "asset manage", "investment", "automaker",
    "automotive", "energy", "oil and gas", "mining", "semiconductor", "software",
    "restaurant", "hotel", "casino", "media", "telecommunication", "aerospace",
    "defense", "defence", "industrial", "chemical", "consumer", "service",
    "platform", " brand", "homebuilder", "winery", "brewer", "agricultur",
    "logistics", "transport", "railroad", "railway", "shipping", "apparel",
    "footwear", "cosmetic", "beverage", "bottler", "supermarket", "grocer",
    "commerce", "payment", "credit", "mortgage", "lender", "exchange",
    "marketplace", "networking", "bancorp", "bancshares", "realty", "properties",
    "reinsur", "staffing", "equipment", "products", "solutions", "stores",
    "health", "biolog", "medical", "devices", "fortune 500", "chain",
    "publicly traded", "publicly owned", "electronics", "refiner", "midstream",
    "educational", "institute", "carrier", "fund manage", "steakhouse",
)  # NB: bare "designer"/"producer" omitted — they also describe people
   # (a jewellery designer, a film producer); the company words above suffice.
# Wikidata short-description fragments that VETO a page outright: a place, a work,
# a person, a court case — never a company, even if an org word slips in (e.g.
# "unincorporated community" contains "incorporat"). Checked before _ORG_KW.
_NOT_COMPANY = (
    "unincorporated", "community in", "town in", "city in", "village in",
    "census-designated", "county", "river", "lake", "mountain", "island",
    "neighborhood", "borough", "hamlet", "municipality", "geological",
    "historic", "amino acid", "chemical compound", "chemical element",
    "documentary", "film", "novel", "book by", "album", "song", "single by",
    "band", "musician", "actor", "actress", "politician", "footballer",
    "writer", "poet", "given name", "surname", "species", "genus",
    # person professions — opensearch fuzz lands on a same-named individual
    # ("Jean Michel Schlumberger ... jewellery designer" for SLB)
    "designer", "architect", "painter", "novelist", "screenwriter",
    "composer", "journalist", "businessman", "businesswoman", "entrepreneur",
    "philanthropist", "economist", "physician", "aristocrat", "nobleman",
    "filmmaker", "rapper", "singer", "director", "cricketer",
    "court case", "legal case", "legal issue", "supreme court", "law case",
    "convention center", "country club", "concert hall", "university",
    "incident", "crisis", "battle", "treaty", "disease", "vaccine", "pandemic",
)
# Word-boundary matched (a substring veto would catch "contr-ACTOR", "un-INCORPORAT-ed").
_NOT_COMPANY_RE = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(v) for v in _NOT_COMPANY))


def _titlecase(s: str) -> str:
    """SEC entity names arrive ALL-CAPS ("MICROSOFT CORP"); lower the shouting so
    Wikipedia's (case-sensitive) opensearch ranking doesn't favour a lawsuit."""
    def fix(w: str) -> str:
        return w if (not w or "&" in w or "/" in w) else w[0].upper() + w[1:].lower()
    return " ".join(fix(w) for w in s.split())


def _clean_name(name: str) -> str:
    """A sane Wikipedia search string from a raw breadth/SEC name: fold "X (The)"
    to "The X", drop SEC registration tags (/DE/, /NEW/, trailing slash) and
    de-shout ALL-CAPS names."""
    n = " ".join(str(name or "").split())
    if not n:
        return ""
    m = re.match(r"^(.*?)[,\s]*\(the\)\s*$", n, re.I)
    if m:
        n = "The " + m.group(1).strip()
    n = re.sub(r"\s*/[A-Za-z .&]{1,8}/?\s*$", "", n).strip()  # " /DE/", " /NEW/"
    n = n.rstrip("/ ").strip()                                # "AMETEK INC/"
    letters = re.sub(r"[^A-Za-z]", "", n)
    if len(n) > 4 and letters and letters.isupper():
        n = _titlecase(n)
    return n


def _core_name(name: str) -> str:
    """`_clean_name` with trailing corporate-form words removed."""
    n = _clean_name(name)
    toks = re.sub(r"[.,]", " ", n).split()
    while toks and toks[-1].lower().strip(".,&") in _CORE_SUFFIX:
        toks.pop()
    return " ".join(toks).strip(" ,&")


def _search_terms(*names: str) -> list[str]:
    """Ordered, de-duplicated search candidates: the cleaned name then its bare
    core, for each supplied name (clean display name first, SEC name as backup).
    Kept deliberately tight — a bare brand token ("EPAM") tends to surface a
    same-named different entity, and every extra term is another way to go wrong."""
    out: list[str] = []
    for nm in names:
        for cand in (_clean_name(nm), _core_name(nm)):
            cand = cand.strip()
            if cand and cand not in out:
                out.append(cand)
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _lawsuit_title(title: str) -> bool:
    """"Microsoft Corp. v European Commission", "Altria Group v. Good" — a court
    case, not the company. Cheap pre-filter so we don't even fetch its summary."""
    return bool(re.search(r"\sv\.?\s", f" {title} "))


def _match_score(title: str, *names: str) -> int:
    """How well a Wikipedia title names the company: 3 = full core match, 2 = all
    distinctive tokens present (incl. a fused "Eagle"->"EagleBank"), 1 = only SOME
    of a multi-word name (the wrong-sibling smell: "Antero Resources" for "Antero
    Midstream"), 0 = none. Used to PREFER the closest page and reject partials."""
    t = _norm(title)
    if not t:
        return 0
    best = 0
    for nm in names:
        core = _norm(_core_name(nm))
        if core and (core in t or t in core):
            return 3
        ntoks = [w for w in re.sub(r"[^a-z0-9]", " ", str(nm).lower()).split()
                 if len(w) >= 4 and w not in _NAME_STOP and w not in _GENERIC_TOK]
        if not ntoks:
            continue
        present = sum(1 for w in set(ntoks) if w in t)   # substring → fused-aware
        if present and present == len(set(ntoks)):
            best = max(best, 2)
        elif present:
            best = max(best, 1)
    return best


def _name_relevant(title: str, *names: str) -> bool:
    """Does this Wikipedia title actually name the company? Guards against
    opensearch fuzz ("Arginine" for Argan, "Sugar Land" for CVR Energy)."""
    return _match_score(title, *names) >= 1


def _looks_company_guard(desc: str) -> bool:
    """False when the short description names a place/work/person/case."""
    return not _NOT_COMPANY_RE.search((desc or "").lower())


def _looks_company(desc: str, extract: str) -> bool:
    """An organization-type keyword in the Wikidata short description (preferred,
    it's terse and clean) — or, when there is none, in the extract's lead. A
    place/work/person/case short description vetoes regardless."""
    d = (desc or "").lower()
    if not _looks_company_guard(d):
        return False
    if d:
        return any(k in d for k in _ORG_KW)
    return any(k in (extract or "").lower()[:200] for k in _ORG_KW)


def _is_company_page(s: dict, *names: str) -> bool:
    """Accept a resolved Wikipedia page only if it both names the company and
    reads like an organization — fail-safe: an uncertain page yields no blurb
    (an empty chip) rather than a confidently-wrong one (a lawsuit, a town)."""
    if not isinstance(s, dict) or s.get("type") == "disambiguation":
        return False
    if not _name_relevant(s.get("title") or "", *names):
        return False
    return _looks_company(s.get("description") or "", s.get("extract") or "")


def _cache_path():
    p = config.data_dir() / "profile" / "profiles.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _get(url: str, headers: dict, retries: int = 3, timeout: int = 20):
    import requests
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001 — best-effort per source
            if attempt == retries - 1:
                log.debug("profile GET failed %s: %s", url.split("?")[0][-48:], e)
                return None
            time.sleep(1.2 * (attempt + 1))
    return None


def _universe() -> dict[str, str]:
    """{ticker: company name} from the breadth constituents (same set edgar uses)."""
    out: dict[str, str] = {}
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "constituents.parquet"
        if p.exists():
            meta = pd.read_parquet(p)
            for t, row in meta.iterrows():
                out.setdefault(str(t), str(row.get("name", t)))
    return out


def _cik_map() -> dict[str, int]:
    """ticker -> CIK. Primary: the CIKs edgar already resolved in
    data/edgar/fundamentals.parquet. Fallback: the SEC company_tickers.json cache."""
    out: dict[str, int] = {}
    fp = config.data_dir() / "edgar" / "fundamentals.parquet"
    if fp.exists():
        try:
            df = pd.read_parquet(fp, columns=["cik"])
            for t, row in df.iterrows():
                c = row.get("cik")
                if pd.notna(c):
                    out[str(t)] = int(c)
        except Exception:  # noqa: BLE001
            pass
    cache = config.data_dir() / "edgar" / "company_tickers.json"
    if len(out) < 100 and cache.exists():
        try:
            data = json.loads(cache.read_text())
            sec = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
            for t in _universe():
                u = t.upper()
                for cand in (u, u.replace("-", "."), u.replace(".", "-"),
                             u.split("-")[0], u.split(".")[0]):
                    if cand in sec:
                        out.setdefault(t, sec[cand])
                        break
        except Exception:  # noqa: BLE001
            pass
    return out


def _sec_submission(cik: int) -> dict:
    """SIC text, listing exchange, HQ city/state from the SEC submissions doc."""
    ua = config.load()["edgar"]["user_agent"]
    r = _get(SUBMISSIONS.format(cik), {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
    time.sleep(0.12)                       # SEC fair-access pacing (<10 req/s)
    if r is None:
        return {}
    try:
        d = r.json()
    except Exception:  # noqa: BLE001
        return {}
    exch = d.get("exchanges") or []
    addr = (d.get("addresses") or {}).get("business") or {}
    hq = ", ".join(p for p in (addr.get("city"), addr.get("stateOrCountry")) if p) or None
    return {"sic_description": (d.get("sicDescription") or None),
            "exchange": (exch[0] if exch else None), "hq": hq,
            "name": d.get("name") or None}


def _trim(extract: str, max_sentences: int = 2, max_chars: int = 320) -> str:
    """First couple of sentences of a Wikipedia extract, length-capped. A single
    capital initial ("W. W. Grainger", "W. P. Carey") is NOT a sentence break —
    without this the extract collapses to a useless stub ("W. W.")."""
    extract = " ".join((extract or "").split())
    if not extract:
        return ""
    # shield "X. " initials from the naive ". " split, restore after
    SEP = "\x00"
    guarded = re.sub(r"\b([A-Z])\.\s", lambda m: m.group(1) + "." + SEP, extract)
    parts, out = guarded.split(". "), ""
    for i, s in enumerate(parts):
        nxt = out + s + (". " if i < len(parts) - 1 else "")
        if i >= max_sentences or len(nxt.replace(SEP, " ")) > max_chars:
            break
        out = nxt
    out = out.replace(SEP, " ").strip()
    return out if out else extract.replace(SEP, " ")[:max_chars]


def _wiki_summary(title: str, headers: dict) -> dict | None:
    r = _get(WIKI_SUMMARY.format(quote(title.replace(" ", "_"))) + "?redirect=true", headers)
    time.sleep(0.05)
    if r is None:
        return None
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return None


def _wiki_page(*names: str, max_check: int = 6) -> tuple[str | None, str | None]:
    """Resolve the company's Wikipedia page → (one-paragraph description, page TITLE).
    opensearch ranks a namesake court case / town / chemical above the company for
    many tickers (especially ALL-CAPS SEC names), so we walk the top candidates of
    each search term, validate each as a company page, and keep the BEST name match —
    a full match short-circuits; a mere partial ("Antero Resources" for "Antero
    Midstream") is rejected so a wrong sibling never wins by ranking first.

    The TITLE is returned alongside the description so downstream consumers
    (collectors.wiki_pageviews) can request offshore pageviews for the SAME validated
    page without re-incurring the wrong-namesake resolution. Title is non-None exactly
    when a company page was accepted (score≥2); description may still be empty/None if
    the extract trimmed away."""
    headers = {"User-Agent": WIKI_UA, "Accept": "application/json"}
    seen: set[str] = set()
    checked = 0
    best_extract: str | None = None
    best_title: str | None = None
    best_score = 0
    for term in _search_terms(*names):
        r = _get(WIKI_OPENSEARCH.format(quote(term)), headers)
        time.sleep(0.05)
        cands: list[str] = []
        if r is not None:
            try:
                os_res = r.json()
                if isinstance(os_res, list) and len(os_res) >= 2:
                    cands = [c for c in os_res[1] if c]
            except Exception:  # noqa: BLE001
                cands = []
        for title in (cands or [term]):
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            if _lawsuit_title(title):           # cheap reject, skip the fetch
                continue
            if checked >= max_check:
                break
            checked += 1
            s = _wiki_summary(title, headers)
            if not s or not _is_company_page(s, *names):
                continue
            ttl = s.get("title") or title
            score = _match_score(ttl, *names)
            if score >= 3:                      # an unambiguous full-name match
                return (_trim(s.get("extract") or "") or None), ttl
            if score > best_score:              # keep the strongest partial seen
                best_score, best_extract, best_title = score, s.get("extract") or "", ttl
        if checked >= max_check:
            break
    # accept a held candidate only if it matched the WHOLE distinctive name (>=2);
    # a score-1 partial is the wrong-sibling smell → leave it blank.
    if best_score >= 2:
        return (_trim(best_extract or "") or None), best_title
    return None, None


def _wiki_description(*names: str, max_check: int = 6) -> str | None:
    """Back-compat shim: the description half of `_wiki_page` (title dropped)."""
    return _wiki_page(*names, max_check=max_check)[0]


def resolve_wiki_title(*names: str) -> str | None:
    """Public: the validated company Wikipedia page TITLE for these name(s), or None.
    Used by collectors.wiki_pageviews as the per-ticker fallback when the cached
    profiles.parquet `wiki_title` column has not yet been populated by a re-fetch."""
    return _wiki_page(*names)[1]


def fetch_profiles(force: bool = False, max_new: int = 250,
                   tickers: list[str] | None = None) -> pd.DataFrame:
    """Fetch (resumably) identity + descriptions for the universe; merge into the
    cache and return the wide ticker-indexed table. Best-effort: a host being down
    just leaves rows unfetched for the next run."""
    cache = _cache_path()
    existing = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
    cik = _cik_map()
    names = _universe()
    universe = tickers or list(names) or list(existing.index)

    def stale(t: str) -> bool:
        if force or existing.empty or t not in existing.index:
            return True
        ts = existing.loc[t].get("as_of")
        try:
            age = (datetime.now(timezone.utc) - pd.to_datetime(ts)).days
        except Exception:  # noqa: BLE001
            return True
        return age > REFRESH_DAYS

    todo = [t for t in universe if stale(t)][:max_new]
    log.info("equity_profile: %d universe, %d stale → fetching %d (cap %d)",
             len(universe), sum(stale(t) for t in universe), len(todo), max_new)

    rows = []
    now = datetime.now(timezone.utc).isoformat()
    for t in todo:
        display = names.get(t, t)                  # clean breadth name (mixed-case)
        rec: dict = {"ticker": t, "name": display, "as_of": now}
        if t in cik:
            rec.update(_sec_submission(cik[t]))    # may overwrite name with the SEC entity
        # Search the clean display name FIRST, the (ALL-CAPS) SEC name as backup:
        # "MICROSOFT CORP" ranks the EU antitrust case ahead of the company.
        # Persist the resolved page TITLE too (additive `wiki_title` column) so the
        # offshore-attention collector reuses this namesake-robust resolution.
        rec["description"], rec["wiki_title"] = _wiki_page(display, rec.get("name"))
        rec["source"] = "wikipedia+sec"
        rows.append(rec)

    fresh = pd.DataFrame(rows).set_index("ticker") if rows else pd.DataFrame()
    if not existing.empty and not fresh.empty:
        out = pd.concat([existing[~existing.index.isin(fresh.index)], fresh])
    else:
        out = fresh if not fresh.empty else existing
    if not out.empty:
        out.to_parquet(cache)
    log.info("equity_profile: cache now %d tickers (%d with a description)",
             len(out), int(out["description"].notna().sum()) if "description" in out else 0)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import sys
    ts = sys.argv[1:] or None
    df = fetch_profiles(force=bool(ts), max_new=10, tickers=ts)
    cols = [c for c in ("name", "sic_description", "exchange", "hq", "description") if c in df.columns]
    for t in (ts or list(df.index)[:5]):
        if t in df.index:
            r = df.loc[t]
            print(f"\n{t}: {r.get('name')}  [{r.get('exchange')} · {r.get('sic_description')} · {r.get('hq')}]")
            print(" ", (r.get("description") or "(no description)"))
