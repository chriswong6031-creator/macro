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
exchange, hq, name, source, as_of). engine/stock_fundamentals reads it into the
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
import unicodedata
from datetime import datetime, timezone
from urllib.parse import quote

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# Wikipedia asks for a descriptive UA with contact. SEC's data.sec.gov blocks
# (403) the email-laden form but accepts the simple edgar UA already in config —
# so SEC reuses config.edgar.user_agent, Wikipedia uses WIKI_UA.
WIKI_UA = "macro-dashboard research (mastermindx-market-intelligence) macro-dashboard@users.noreply.github.com"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{:010d}.json"
WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
# limit=5 (not 1): opensearch's top hit is often a namesake (a lawsuit, a town,
# a chemical) rather than the company, so we pull a handful and validate.
WIKI_OPENSEARCH = ("https://en.wikipedia.org/w/api.php?action=opensearch"
                   "&search={}&limit=5&namespace=0&format=json")
REFRESH_DAYS = 120
# Bumped whenever the entity-acceptance rule changes. A cached row resolved under an
# older version is re-adjudicated by scripts/revalidate_profile_descriptions.py (and
# re-fetched by the next collector pass) instead of sitting out the REFRESH_DAYS
# window — a wrong-entity blurb must never wait 120 days for its own correction.
#   v1: name-relevance + organization-type gates only. Published "Redwood is a
#       restaurant in Portland, Oregon" as the profile for RWT / Redwood Trust Inc,
#       because "Trust" is a stop word, leaving the single distinctive token
#       "redwood", which the restaurant page carries.
#   v2: graded resolution strength + first-party (SEC SIC) industry corroboration;
#       a single-distinctive-token match must now be corroborated to be published.
#   v3: child-entity rejection. v2 still published a page whose title appends a
#       word the issuer's name lacks AND which declares itself a subsidiary, brand
#       or product line of a DIFFERENT company: PSMT carried "PriceSmart Foods" (a
#       BC supermarket chain owned by the Jim Pattison Group), LNC "Lincoln
#       Financial Media" (a defunct broadcaster), DMC "Del Monte Foods" (a
#       NutriAsia subsidiary), TXN "Texas Instruments Power" (a transistor series).
RESOLVER_VERSION = 3
# A row whose SEC identity resolved but whose Wikipedia description came back empty
# was usually a TRANSIENT miss (Wikipedia throttled/down for that one fetch), not a
# name Wikipedia genuinely lacks — the matcher resolves the vast majority on a retry.
# So don't freeze that gap for the full REFRESH_DAYS: retry description-less rows on a
# short cadence, bounded by an attempt counter so a truly-undescribable name backs off
# to the normal refresh cycle instead of burning the per-build budget forever.
DESC_RETRY_DAYS = 4
MAX_DESC_TRIES = 6

# Trailing corporate-form words stripped to build a bare "core" search/match term
# ("Microsoft Corp" -> "Microsoft", "CVR Energy, Inc." -> "CVR Energy").
_CORE_SUFFIX = {"corp", "corporation", "inc", "incorporated", "co", "cos",
                "company", "companies", "ltd", "limited", "plc", "llc", "lp",
                "lllp", "sa", "nv", "ag", "se", "holdings", "holding"}
# Generic words ignored when checking a Wikipedia title actually names the company.
_NAME_STOP = _CORE_SUFFIX | {"the", "of", "and", "for", "group", "trust",
                             "international", "american", "global", "new",
                             "class", "cl"}
# NB: directional words ("northern", "western", "pacific") are deliberately NOT
# stop words. Demoting them looks right — "Northern Oil & Gas" should not read as
# "Northern Trust" — but measured on the live cache it TRADES one collision for a
# worse one: with both demoted, "Western Union" and "Union Pacific" reduce to the
# same single token "union" and grade EXACT, which is the one strength nothing can
# veto. Issuers whose distinctive name is a single common word (Northern, Union,
# Universal, First Bancorp of PR vs of NC) are a genuine name-collision class that
# name evidence alone cannot settle; see the wave note rather than widening this set.
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
    # "research" is an industry descriptor, not a brand — exactly like the
    # "laboratories"/"technologies" already above. Left out, "ACM Research" reduced
    # to the single token "research" and matched the unrelated "AST Research".
    "research",
    # same family: words a legal name carries and an article title drops
    # ("Shift4 Payments, Inc." is titled "Shift4")
    "payment", "payments", "semiconductor", "semiconductors", "software",
    "automotive", "aerospace", "logistics", "packaging", "chemicals", "chemical",
    "metals", "mining", "restaurants", "hotels", "resorts", "airlines",
    "devices", "instruments", "diagnostics",
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

# --- first-party industry corroboration -------------------------------------
# Coarse industry FAMILIES, deliberately few and deliberately overlapping. Used to
# ask one narrow, deterministic question of two independent sources — the SEC's SIC
# text for the ticker (first-party: it is the issuer's own filing classification)
# and the candidate Wikipedia page's own words:
#
#     do these two describe the same KIND of organisation?
#
# This is corroboration, never classification: we never publish the family, never
# rank on it, and never let it override a full-name match. It exists only to break
# the tie on a marginal single-token name match, where the alternative is guessing.
# A term may belong to several families — that makes agreement EASIER to reach,
# which is the safe direction (a false "contradiction" would withhold a correct
# blurb; a missed contradiction merely leaves the older, weaker gate in charge).
_INDUSTRY_FAMILIES: dict[str, tuple[str, ...]] = {
    "finance": (
        "bank", "banks", "banking", "bancorp", "bancshares", "savings institution",
        "thrift", "credit union", "broker", "brokers", "brokerage", "securities",
        "asset management", "asset manager", "investment advice", "investment adviser",
        "investment advisor", "investment management", "investment manager",
        "financial services", "financial institution", "fintech", "mortgage",
        "lender", "lending", "consumer credit", "clearing", "payment", "payments",
        "credit card", "private equity", "hedge fund", "capital markets",
    ),
    "insurance": (
        "insurance", "insurer", "insurers", "reinsurance", "reinsurer",
        "underwriter", "casualty", "annuity", "annuities",
    ),
    "real_estate": (
        "real estate", "reit", "real estate investment trust", "realty",
        "property", "properties", "apartment", "apartments", "shopping center",
        "shopping centre", "office building", "self storage", "self-storage",
    ),
    "food_service": (
        "restaurant", "restaurants", "eating place", "eating places", "steakhouse",
        "fast food", "fast-food", "coffeehouse", "coffee shop", "cafe", "café",
        "diner", "pizzeria", "catering", "caterer", "bar and grill", "brewpub",
    ),
    "food_products": (
        "food", "foods", "beverage", "beverages", "brewer", "brewery", "brewing",
        "winery", "wine", "distiller", "distillery", "bottler", "bottling",
        "confectionery", "dairy", "snack", "kindred products",
    ),
    "retail": (
        "retail", "retailer", "retailers", "stores", "store", "supermarket",
        "grocer", "grocery", "e-commerce", "ecommerce", "marketplace",
        "department store", "mail order", "catalog",
    ),
    "technology": (
        "software", "internet", "technology", "information technology",
        "computer programming", "data processing", "computer services",
        "cloud", "saas", "platform", "prepackaged software", "computer integrated",
        "cybersecurity", "artificial intelligence", "video game", "video games",
    ),
    "hardware": (
        "semiconductor", "semiconductors", "electronics", "electronic", "computer hardware",
        "printed circuit", "circuit boards", "instruments", "measurement",
        "peripheral", "peripherals", "networking equipment", "telecommunications equipment",
    ),
    "health": (
        "pharmaceutical", "pharmaceuticals", "pharma", "biotechnology", "biotech",
        "biological products", "medical", "medicine", "medicines", "surgical",
        "orthopedic", "prosthetic", "diagnostic", "diagnostics", "hospital",
        "hospitals", "health care", "healthcare", "clinic", "clinics", "therapeutics",
        "electromedical", "drug", "drugs", "laboratory", "laboratories", "dental",
    ),
    "energy": (
        "oil", "gas", "petroleum", "crude", "refiner", "refining", "refinery",
        "midstream", "pipeline", "pipelines", "drilling", "oilfield", "coal",
        "natural gas", "energy", "renewable", "solar", "wind power",
    ),
    "utilities": (
        "utility", "utilities", "electric services", "electric power", "electric utility",
        "water supply", "water utility", "gas distribution", "power generation",
    ),
    "mining": (
        "mining", "miner", "miners", "metals", "metal", "gold", "silver", "copper",
        "steel", "aluminum", "aluminium", "smelting", "ore", "quarry",
    ),
    "chemicals": (
        "chemical", "chemicals", "plastics", "resins", "elastomers", "fertilizer",
        "industrial gases", "coatings", "adhesives",
    ),
    "industrial": (
        "machinery", "equipment", "manufacturer", "manufacturing", "conglomerate",
        "industrial", "engineering", "tools", "bearings", "valves", "pumps",
    ),
    "aerospace": (
        "aerospace", "defense", "defence", "aircraft", "missile", "satellite",
        "space", "avionics", "armament",
    ),
    "auto": (
        "automaker", "automotive", "motor vehicle", "automobile", "car maker",
        "vehicle", "vehicles", "auto parts", "tires", "tyres",
    ),
    "transport": (
        "airline", "airlines", "air transportation", "railroad", "railway", "rail",
        "shipping", "maritime", "trucking", "logistics", "freight", "courier",
        "transportation", "delivery",
    ),
    "telecom": (
        "telecommunication", "telecommunications", "wireless", "cellular", "broadband",
        "cable television", "telephone", "telecom", "communications services",
    ),
    "media": (
        "media", "broadcasting", "broadcaster", "entertainment", "film", "television",
        "publishing", "publisher", "newspaper", "magazine", "music", "studio",
        "advertising", "streaming",
    ),
    "apparel": (
        "apparel", "clothing", "footwear", "shoes", "luxury", "cosmetic", "cosmetics",
        "fashion", "textile", "textiles", "jewelry", "jewellery", "accessories",
    ),
    "hospitality": (
        "hotel", "hotels", "motel", "motels", "resort", "resorts", "casino", "casinos",
        "gaming", "cruise", "lodging", "travel", "leisure",
    ),
    "construction": (
        "homebuilder", "home builder", "construction", "builders", "operative builders",
        "building products", "cement", "concrete", "roofing", "infrastructure",
    ),
    "paper": (
        "paper", "packaging", "containers", "corrugated", "pulp", "cardboard",
    ),
    "agriculture": (
        "agriculture", "agricultural", "farming", "farm", "crop", "crops",
        "livestock", "seed", "seeds", "forestry", "timber", "lumber",
    ),
    "education": (
        "education", "educational", "university", "college", "school", "schools",
        "tutoring", "e-learning",
    ),
    "services": (
        "staffing", "consulting", "consultant", "outsourcing", "business services",
        "professional services", "accounting", "legal services", "security services",
        "waste management", "facilities",
    ),
}
# Pre-compiled word-boundary matcher per family. Substring matching would map
# "riverbank" to finance and "carbon" to auto.
_FAMILY_RE: dict[str, re.Pattern] = {
    fam: re.compile(r"\b(?:%s)\b" % "|".join(sorted((re.escape(k) for k in kws),
                                                    key=len, reverse=True)))
    for fam, kws in _INDUSTRY_FAMILIES.items()
}


# SEC buckets that assert nothing. "NEC" is the taxonomy's own "not elsewhere
# classified" — reading an industry out of it manufactures evidence where the
# filing explicitly declines to give any, and that produced a false contradiction
# against Shift4 ("Services-Business Services, NEC" vs "payment processing company").
_UNINFORMATIVE_SIC_RE = re.compile(
    r"\bnec\b|\bn\.e\.c\.|not elsewhere classified|^blank checks?$", re.I)


_US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}
_STATE_NAME_RE = re.compile(r"\b(?:%s)\b" % "|".join(
    sorted((re.escape(s) for s in _US_STATES), key=len, reverse=True)), re.I)


def _page_states(text: str) -> frozenset[str]:
    """US state codes explicitly named in a page's lead."""
    return frozenset(_US_STATES[m.group(0).lower()]
                     for m in _STATE_NAME_RE.finditer(str(text or "")))


def _location_contradicts(hq: str | None, page_desc: str | None,
                          page_extract: str | None) -> bool:
    """True when the SEC's own business address for THIS ticker and the candidate
    page put the company in different US states.

    The last discriminator for a true name collision, where the issuer and a
    same-named other company are both real firms in adjacent industries and no
    amount of name or industry evidence separates them. Measured on TRMK: the SEC
    files Trustmark Corp at JACKSON, MS; the page Wikipedia offers under that name
    is a privately held benefits company in Chicago, IL.

    Conservative on purpose — a contradiction requires the page to name at least one
    state, none of them to be the SEC's, and the page not to name the SEC's city
    either. A page that names no location says nothing and vetoes nothing."""
    hq_text = str(_cell(hq) or "").strip()
    if not hq_text:
        return False
    parts = [p.strip() for p in hq_text.split(",")]
    hq_state = parts[-1].strip().upper() if len(parts) > 1 else ""
    if hq_state not in set(_US_STATES.values()):
        return False                       # non-US or unparseable — no opinion
    lead = f"{page_desc or ''} {str(page_extract or '')[:400]}"
    states = _page_states(lead)
    if not states or hq_state in states:
        return False
    hq_city = parts[0].strip().lower()
    if hq_city and re.search(r"\b%s\b" % re.escape(hq_city), lead, re.I):
        return False                       # right city, unmentioned state
    return True


def _industry_families(*texts: str) -> frozenset[str]:
    """The coarse industry families named anywhere in `texts` (lower-cased,
    word-boundary matched). Empty when nothing recognisable is said — which is
    always treated as "no evidence", never as "contradiction"."""
    blob = " ".join(str(t or "") for t in texts).lower()
    if not blob.strip():
        return frozenset()
    return frozenset(fam for fam, rx in _FAMILY_RE.items() if rx.search(blob))


# Families that routinely describe ONE issuer through two vocabularies. SEC SIC text
# is a 1970s manufacturing taxonomy; Wikipedia writes modern prose — Apple is
# "Electronic Computers" to the SEC (hardware) and "a technology company" to
# Wikipedia (technology). Without this, agreement would be under-detected and correct
# blurbs withheld. Adjacency is symmetric and NOT transitive: it is applied one hop
# only, so retail~food_service and food_service~hospitality never chain real_estate
# to food_service — the pair the RWT defect turned on.
_FAMILY_ADJACENT: tuple[frozenset[str], ...] = tuple(frozenset(p) for p in (
    ("technology", "hardware"), ("technology", "telecom"), ("technology", "media"),
    ("technology", "services"), ("finance", "insurance"), ("finance", "real_estate"),
    ("energy", "utilities"), ("energy", "mining"), ("energy", "industrial"),
    ("mining", "industrial"), ("mining", "chemicals"), ("industrial", "aerospace"),
    ("industrial", "auto"), ("industrial", "construction"), ("industrial", "chemicals"),
    # a vehicle dealership is filed as retail and describes itself as automotive
    # (measured on RUSHA: SIC "Retail-Auto Dealers & Gasoline Stations")
    ("retail", "auto"),
    # automotive suppliers describe themselves as electronics/technology firms
    # (measured on GNTX: SIC "Motor Vehicle Parts", page "electronics and
    # technology company") — both are true of the same issuer
    ("auto", "hardware"), ("auto", "technology"),
    ("industrial", "transport"), ("industrial", "paper"), ("industrial", "hardware"),
    # offshore support / oilfield marine: the SEC files them as Water Transportation
    # while their own prose says "petroleum service company" (measured on TDW)
    ("energy", "transport"),
    ("health", "hardware"), ("health", "chemicals"), ("retail", "food_products"),
    ("retail", "food_service"), ("retail", "apparel"), ("food_service", "hospitality"),
    ("hospitality", "media"), ("agriculture", "food_products"), ("media", "telecom"),
))


def _families_compatible(a: frozenset[str], b: frozenset[str]) -> bool:
    """True when the two family sets overlap, or name an adjacent pair (one hop)."""
    if a & b:
        return True
    return any({x, y} in _FAMILY_ADJACENT for x in a for y in b if x != y)


def _industry_agrees(sic_description: str | None,
                     page_desc: str | None, page_extract: str | None) -> bool | None:
    """Do the SEC's own industry text and the candidate page describe the same kind
    of organisation?  True = corroborated, False = contradicted, None = no evidence
    on at least one side (the only honest answer when SEC has no SIC for the ticker
    or the page says nothing an industry word can be read out of)."""
    sic_text = str(sic_description or "")
    if _UNINFORMATIVE_SIC_RE.search(sic_text):
        return None                      # the filing itself declines to classify
    sic_fams = _industry_families(sic_text)
    if not sic_fams:
        return None
    # Prefer the terse Wikidata short description; fall back to the extract's LEAD
    # only when there is none. Reading the WHOLE extract is what makes this test
    # unusable: a full paragraph name-drops incidental industries, so Visa's
    # "payment card services corporation ... " picks up families its SIC
    # ("Services-Business Services, NEC") never names, and a correct page reads as a
    # contradiction. Measured: whole-extract matching wrongly contradicted 67 rows
    # including Visa, Mastercard, Berkshire Hathaway, eBay and HP.
    page_fams = _industry_families(page_desc)
    if not page_fams:
        page_fams = _industry_families(str(page_extract or "")[:200])
    if not page_fams:
        return None
    return _families_compatible(sic_fams, page_fams)


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
    # " /DE/", " /NEW/" and the backslash form " \\TX\\" (RUSH ENTERPRISES INC \\TX\\)
    n = re.sub(r"\s*[/\\][A-Za-z .&]{1,8}[/\\]?\s*$", "", n).strip()
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
    """Comparison form: accents folded, then everything but [a-z0-9] dropped.

    Folding matters — without it "Estée" loses its "é" entirely and becomes "este",
    so "Estée Lauder" and "Estee Lauder" stop being the same string and a correctly
    resolved issuer is demoted to a marginal match."""
    folded = unicodedata.normalize("NFKD", str(s).lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", folded)


def _cell(v):
    """A parquet cell coerced to None when missing — round-tripped object columns
    come back as float NaN, which is truthy as a string ("nan") and breaks int()."""
    try:
        return None if pd.isna(v) else v
    except (TypeError, ValueError):       # arrays/odd types: leave as-is
        return v


def _int0(v) -> int:
    """A count cell as a non-negative int (NaN/None/garbage → 0)."""
    try:
        return int(v) if pd.notna(v) else 0
    except (TypeError, ValueError):
        return 0


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
    opensearch fuzz ("Arginine" for Argan, "Sugar Land" for CVR Energy) AND against
    the wrong SIBLING ("Antero Resources" offered for Antero Midstream), which is a
    score-1 partial. Only a whole-name match (>=2) is relevant; a partial is exactly
    the shape that publishes a real company's blurb under another company's ticker."""
    return _match_score(title, *names) >= 2


# --- graded resolution strength ---------------------------------------------
# How strongly a candidate page is tied to the issuer. Recorded on the cached row
# (desc_strength) so a published blurb is always traceable to WHY it was accepted.
STRENGTH_EXACT = "exact"      # issuer core == candidate core, or fully contained
STRENGTH_TOKENS = "tokens"    # every distinctive issuer token present, >= 2 of them
STRENGTH_WEAK = "weak"        # every distinctive token present, but there is only ONE
STRENGTH_NONE = "none"        # partial or no match — never publishable

# A Wikipedia parenthetical exists precisely BECAUSE the bare title is ambiguous.
# These qualifiers say "the company one"; anything else ("(restaurant)", "(band)",
# "(film)") says the opposite and caps the candidate at WEAK.
_CORPORATE_PAREN = {"company", "corporation", "business", "brand", "conglomerate",
                    "bank", "retailer", "manufacturer", "firm", "airline", "automaker"}
_PAREN_RE = re.compile(r"\s*\(([^)]*)\)\s*$")


def _title_core(title: str) -> str:
    """The candidate title with any trailing disambiguation parenthetical removed,
    then reduced like an issuer name ("Redwood (restaurant)" -> "Redwood")."""
    return _core_name(_PAREN_RE.sub("", str(title or "")).strip())


def _foreign_parenthetical(title: str, *names: str) -> bool:
    """True when the title carries a trailing "(...)" whose content neither says
    "company" nor appears in the issuer's own name — Wikipedia's own marker that
    this title is a NAMESAKE of something else."""
    m = _PAREN_RE.search(str(title or ""))
    if not m:
        return False
    inner = m.group(1).strip().lower()
    if not inner:
        return False
    words = re.sub(r"[^a-z ]", " ", inner).split()
    # EVERY word must be a bare corporate form. "(company)" says "the company one";
    # "(benefits company)" says "the BENEFITS one" — a qualifier, i.e. Wikipedia
    # distinguishing this namesake from others, which is the opposite of
    # corroboration. Accepting any-word made "Trustmark (benefits company)", a
    # private Chicago insurer, an EXACT match for Trustmark Corp, a Mississippi bank.
    if words and all(w in _CORPORATE_PAREN for w in words):
        return False
    joined = _norm(" ".join(str(n or "") for n in names))
    return not (_norm(inner) and _norm(inner) in joined)


def _toks(s: str) -> list[str]:
    """Word tokens, Unicode-aware and accent-folded — "Estée Lauder" is two tokens
    ("estee", "lauder"), not four, and compares equal to an unaccented spelling.
    Folding must happen at the TOKEN level too, not only in `_norm`: Wikipedia and
    the SEC disagree about accents constantly, and a token-level mismatch reads as
    "the title added a distinctive word", which is the wrong-entity signal."""
    folded = unicodedata.normalize("NFKD", str(s or "").lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return re.findall(r"\w+", folded, re.UNICODE)


def _core_equivalent(title: str, *names: str) -> bool:
    """Is the candidate's core name the SAME name as the issuer's, rather than
    merely containing it as a substring?

    `_match_score`'s full-match test is bare substring containment, so a short
    issuer core sits happily inside a longer unrelated title: "Cactus, Inc." (an
    oilfield equipment maker) scored a full match against "Cactus Club Cafe", a
    Canadian restaurant chain, and — with no word boundary at all — "ATI INC"
    matched inside "Americ-ati-onal"... i.e. "American International Group".

    So the comparison is by TOKEN, and it is DIRECTIONAL, which is the part that
    matters. Which side carries the extra word decides what the extra word means:

      the ISSUER carries it, the title drops it  -> the article simply uses the
          common short name. "Shift4 Payments, Inc." is titled "Shift4"; an
          industry descriptor here is not a different company.
      the TITLE carries it, the issuer lacks it  -> the article is about something
          NARROWER than the issuer: a subsidiary, a brand, or a product line.
          "PriceSmart" vs "PriceSmart Foods" (a BC supermarket chain owned by the
          Jim Pattison Group), "Lincoln Financial" vs "Lincoln Financial Media" (a
          defunct broadcaster), "Texas Instruments" vs "Texas Instruments Power" (a
          transistor series). Only a bare corporate form may be added.

    Getting this backwards is expensive: EXACT is the one strength that no
    industry, geographic or offline check may veto, so anything wrongly graded
    EXACT is published with no further test at all."""
    tcore = _title_core(title)
    t_toks = _toks(tcore)
    if not t_toks:
        return False
    t_set = set(t_toks)
    for nm in names:
        ncore = _core_name(nm or "")
        n_toks = _toks(ncore)
        if not n_toks:
            continue
        # fused/punctuation-only difference: "Exxon Mobil" == "ExxonMobil"
        if _norm(tcore) == _norm(ncore):
            return True
        n_set = set(n_toks)
        shared = t_set & n_set
        # the agreement must rest on a BRAND, never on shared filler
        if not any(w not in _NAME_STOP and w not in _GENERIC_TOK for w in shared):
            continue
        issuer_only = n_set - t_set
        title_only = t_set - n_set
        if not all(w in _NAME_STOP or w in _GENERIC_TOK for w in issuer_only):
            continue
        if not all(w in _NAME_STOP for w in title_only):
            continue
        return True
    return False


def _resolution_strength(title: str, *names: str) -> str:
    """Grade a candidate title against the issuer's names.

    The published RWT blurb is why this exists. "Redwood Trust Inc" loses "Trust"
    to the stop list and "Inc" to the length floor, leaving the single distinctive
    token "redwood" — which "Redwood (restaurant)" carries in full. Under the old
    all-distinctive-tokens rule that was indistinguishable from a real match, so the
    restaurant was published. A one-token agreement is now graded WEAK and must be
    corroborated by first-party industry evidence before it may be published."""
    score = _match_score(title, *names)
    if score < 2:
        return STRENGTH_NONE
    # `_core_equivalent` — not the raw substring score — is the authority on
    # "same name". _match_score's core test has no word boundary and no direction,
    # so it both over-grants (ATI inside "AmericATIonal") and under-grants (a
    # leading "The" defeats the containment for "Estée Lauder Companies (The)").
    if (not _foreign_parenthetical(title, *names)
            and _core_equivalent(title, *names)):
        return STRENGTH_EXACT
    # how many distinctive tokens actually carried the match?
    t = _norm(title)
    distinct = 0
    for nm in names:
        toks = {w for w in re.sub(r"[^a-z0-9]", " ", str(nm or "").lower()).split()
                if len(w) >= 4 and w not in _NAME_STOP and w not in _GENERIC_TOK}
        if toks and all(w in t for w in toks):
            distinct = max(distinct, len(toks))
    if _foreign_parenthetical(title, *names):
        return STRENGTH_WEAK
    return STRENGTH_TOKENS if distinct >= 2 else STRENGTH_WEAK


# A page that declares itself a subsidiary, division, brand or product line is
# describing something NARROWER than the listed issuer. Paired with a title that
# adds a word the issuer's own name does not carry, that is the signature of the
# wrong entity — measured on the live cache, it is what PSMT ("PriceSmart Foods",
# a BC supermarket chain owned by the Jim Pattison Group), LNC ("Lincoln Financial
# Media", a defunct broadcaster), DMC ("Del Monte Foods", a NutriAsia subsidiary)
# and TXN ("Texas Instruments Power", a transistor series) all have in common.
# Each signal alone is too blunt: plenty of correct pages mention a subsidiary, and
# a fused title ("Eagle Bancorp" -> "EagleBank") adds a token without adding a WORD.
_CHILD_ENTITY_RE = re.compile(
    r"\b(?:wholly[- ]owned\s+)?"
    r"(?:subsidiary|division|unit|marque|trade\s+name|product\s+line|brand)\s+of\b"
    r"|\b(?:is|was)\s+(?:a|an|the)\s+series\s+of\b"
    r"|\bowned\s+by\b|\bmanufactured\s+by\b|\boperated\s+by\b",
    re.IGNORECASE)


# A product line is never a company, so there is no parent to compare — reject.
_PRODUCT_RE = re.compile(
    r"\b(?:is|was)\s+(?:a|an|the)\s+(?:series|line|range|family|model)\s+of\b",
    re.IGNORECASE)
# "... subsidiary of X", "... owned by X" — X is the declared parent.
_PARENT_RE = re.compile(
    r"\b(?:(?:wholly[- ]owned\s+)?"
    r"(?:subsidiary|division|unit|marque|trade\s+name|product\s+line|brand)\s+of"
    r"|owned\s+by|manufactured\s+by|operated\s+by)\s+"
    r"(?:the\s+)?([A-Z][\w&.'-]*(?:\s+(?:and\s+)?[A-Z][\w&.'-]*){0,4})",
    re.IGNORECASE)


def _declares_foreign_parent(page_desc: str | None, page_extract: str | None,
                             *names: str) -> bool:
    """Does the page declare itself a child of something that is NOT this issuer?

    A page saying "X is a subsidiary of Y" is about X, not Y — so if Y is not the
    issuer we are resolving, the blurb belongs to a different company. But if Y IS
    the issuer, the page is the issuer's own operating bank or property and the
    blurb is legitimate: measured on the live cache, comparing the declared parent
    is what separates "Old National Bank, operated by Old National Bancorp" (ONB,
    correct) from "PriceSmart Foods, a subsidiary of the Overwaitea Food Group"
    (PSMT, a different company entirely)."""
    lead = f"{page_desc or ''} {str(page_extract or '')[:400]}"
    if _PRODUCT_RE.search(lead):
        return True                      # a product line has no parent to match
    m = _PARENT_RE.search(lead)
    if not m:
        return False
    parent = _norm(_core_name(m.group(1)))
    if not parent:
        return False
    for nm in names:
        core = _norm(_core_name(nm or ""))
        if core and (core in parent or parent in core):
            return False                 # the declared parent IS this issuer
    return True


def _title_adds_a_word(title: str, *names: str) -> bool:
    """Does the candidate title carry a WORD the issuer's own name does not?

    Word-level on purpose. A fused rendering ("Eagle Bancorp" titled "EagleBank")
    adds no word — its single token simply spells the issuer differently — while
    "PriceSmart" -> "PriceSmart Foods" genuinely appends one."""
    t_words = set(_toks(_title_core(title)))
    if not t_words:
        return False
    for nm in names:
        if not nm:
            continue
        n_words = set(_toks(_core_name(nm))) | set(_toks(nm))
        extra = {w for w in (t_words - n_words)
                 if w not in _NAME_STOP and len(w) >= 3}
        # a fused spelling is not an addition: the whole issuer core sits inside it
        fused = _norm(_core_name(nm))
        if extra and fused and any(fused in _norm(w) or _norm(w) in fused for w in extra):
            continue
        if not extra:
            return False
    return True


def _accept_page(s: dict, sic_description: str | None, *names: str,
                 hq: str | None = None) -> tuple[bool, str]:
    """The publication decision for one candidate page: (accepted, strength).

    Fail-closed by construction — an uncertain candidate yields NO blurb, because an
    empty Company Profile is merely incomplete while another company's blurb is a
    distribution-scale falsehood. No LLM is consulted; every input is deterministic.

      EXACT   the issuer's whole core name is the page's name  -> publish
      TOKENS  every distinctive token, at least two of them,    -> publish unless the
              and no namesake parenthetical                        SEC's own industry
                                                                   text contradicts it
      WEAK    only ONE distinctive token agreed, or a namesake  -> publish ONLY when
              parenthetical is present                             first-party industry
                                                                   evidence corroborates
      NONE    a partial / unrelated name                        -> never
    """
    if not isinstance(s, dict) or s.get("type") == "disambiguation":
        return False, STRENGTH_NONE
    title = s.get("title") or ""
    desc, extract = s.get("description") or "", s.get("extract") or ""
    if not _looks_company(desc, extract):
        return False, STRENGTH_NONE
    strength = _resolution_strength(title, *names)
    if strength == STRENGTH_NONE:
        return False, STRENGTH_NONE
    agrees = _industry_agrees(sic_description, desc, extract)
    if strength == STRENGTH_EXACT:
        return True, strength                      # a full-name match is never vetoed
    # A true NAME COLLISION — two real companies, same name, neighbouring
    # industries — is the one case name and industry evidence both fail on. Only
    # there is the SEC's filing address brought in as the tie-breaker, and only
    # when Wikipedia has ITSELF flagged the name as ambiguous by disambiguating the
    # title. That restriction is measured, not stylistic: applied to every cached
    # row, an unrestricted geographic veto fired on 5 rows of which 3 were correct
    # companies (Molson Coors, Perdoceo, Valley National) — the SEC address is the
    # FILING address, not the operational HQ, so it disagrees routinely and
    # harmlessly. Restricted to disambiguated titles it fires on the collision it
    # was added for (Trustmark Corp of Jackson, MS vs the Chicago benefits company
    # Wikipedia offers under that name) and on none of those three.
    if (_foreign_parenthetical(title, *names)
            and _location_contradicts(hq, desc, extract)):
        return False, strength
    # A title that appends a word the issuer's own name lacks, on a page that
    # declares itself a child of some OTHER company, is describing a subsidiary,
    # brand or product line — not the listed issuer. Both halves are required:
    # correct pages mention subsidiaries all the time, and a fused spelling adds a
    # token without adding a word.
    if (_title_adds_a_word(title, *names)
            and _declares_foreign_parent(desc, extract, *names)):
        return False, strength
    if strength == STRENGTH_TOKENS:
        return agrees is not False, strength       # only a CONTRADICTION blocks
    return agrees is True, strength                # WEAK needs positive corroboration


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


def adjudicate_cached_row(name: str | None, wiki_title: str | None,
                          description: str | None,
                          sic_description: str | None) -> tuple[bool, str]:
    """Should an ALREADY-CACHED blurb be WITHDRAWN right now, offline?
    Returns (withdraw, reason).

    Deliberately much narrower than `_accept_page`, because the cache retains less
    evidence than the fetch had. At fetch time the matcher saw BOTH the clean
    display name and the SEC entity name, plus the page's Wikidata short
    description; the cache keeps one name and the extract. Condemning a row on that
    thinner record produces false accusations — measured against the live cache, an
    "absence of corroboration" rule wrongly convicted A. O. Smith, Eli Lilly,
    Estée Lauder and Old National Bank, all correctly resolved.

    So the offline pass withdraws ONLY on a positive CONTRADICTION: the SEC's own
    industry text for the ticker and the stored blurb both say what kind of
    organisation this is, and they are incompatible. That is the RWT class (a
    mortgage REIT described as a Portland restaurant) and it is decidable now.

    Everything else is not exonerated — it is merely not convictable on this
    evidence. `RESOLVER_VERSION` marks every cached row for re-adjudication by the
    collector, which re-runs the full rule with the complete evidence set.
    Absence of evidence is not evidence of a wrong entity."""
    # _cell first: a parquet round-trip returns missing object cells as float NaN,
    # which is TRUTHY and stringifies to "nan" — the same trap that put "$nanM" on
    # the public dossiers. `str(x or "")` is not a null check.
    text = str(_cell(description) or "").strip()
    if not text:
        return False, "no-description"
    title = str(_cell(wiki_title) or "").strip()
    if not title:
        # No recorded article title: nothing to test the name against, so a
        # contradiction here would be an accusation with no named accused. Measured,
        # this alone wrongly convicted Quaker Chemical and Instacart. Publication of
        # an unlinked blurb is the provenance guard's job, not this one's.
        return False, "no-recorded-title"
    nm = _cell(name)
    # A full-name match is the strongest evidence the cache holds; it is never
    # overturned by the coarse industry taxonomy (Visa is EXACT and stays).
    if _resolution_strength(title, *([str(nm)] if nm else [])) == STRENGTH_EXACT:
        return False, "exact-name-match"
    if _industry_agrees(sic_description, None, text) is False:
        return True, "industry-contradiction"
    # decidable offline from the stored extract alone: the page says it belongs to
    # a different company, and its title carries a word this issuer's name does not
    if (_title_adds_a_word(title, str(nm) if nm else "")
            and _declares_foreign_parent(None, text, str(nm) if nm else "")):
        return True, "declares-a-different-parent"
    return False, "retained-pending-refetch"


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


_STRENGTH_RANK = {STRENGTH_NONE: 0, STRENGTH_WEAK: 1,
                  STRENGTH_TOKENS: 2, STRENGTH_EXACT: 3}


def _wiki_description(*names: str, sic_description: str | None = None,
                      hq: str | None = None,
                      max_check: int = 6) -> tuple[str | None, str | None, str | None]:
    """One-paragraph business description AND the validated article title via
    Wikipedia REST. opensearch ranks a namesake court case / town / chemical above
    the company for many tickers (especially ALL-CAPS SEC names), so we walk the top
    candidates of each search term, validate each as a company page, and keep the
    BEST name match — a full match short-circuits; a mere partial ("Antero
    Resources" for "Antero Midstream") is rejected so a wrong sibling never wins by
    ranking first. Returns (extract, title); title is reused by the offshore-
    attention collector (collectors/wiki_pageviews.py) so it never re-resolves the
    page (and re-incurs the wrong-namesake risk)."""
    headers = {"User-Agent": WIKI_UA, "Accept": "application/json"}
    seen: set[str] = set()
    checked = 0
    best_extract: str | None = None
    best_title: str | None = None
    best_strength = STRENGTH_NONE
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
            if not s:
                continue
            accepted, strength = _accept_page(s, sic_description, *names, hq=hq)
            if not accepted:
                continue
            matched = s.get("title") or title
            if strength == STRENGTH_EXACT:      # an unambiguous full-name match
                return _trim(s.get("extract") or "") or None, matched, strength
            if _STRENGTH_RANK[strength] > _STRENGTH_RANK[best_strength]:
                best_strength = strength
                best_extract, best_title = s.get("extract") or "", matched
        if checked >= max_check:
            break
    if best_strength != STRENGTH_NONE:
        return (_trim(best_extract or "") or None), best_title, best_strength
    return None, None, None


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

    def _age(t: str):
        if existing.empty or t not in existing.index:
            return None
        try:
            return (datetime.now(timezone.utc) - pd.to_datetime(existing.loc[t].get("as_of"))).days
        except Exception:  # noqa: BLE001
            return None

    def _has_desc(t: str) -> bool:
        if existing.empty or t not in existing.index:
            return False
        d = _cell(existing.loc[t].get("description"))
        return d is not None and bool(str(d).strip())

    def stale_resolver(t: str) -> bool:
        """A row whose blurb was accepted by an OLDER acceptance rule has not been
        adjudicated by the current one. It is re-fetched on the next pass rather
        than waiting out REFRESH_DAYS — a wrong-entity description must not get a
        120-day grace period just because it was cached before the fix."""
        if existing.empty or t not in existing.index:
            return False
        if not _has_desc(t):
            return False
        return _int0(existing.loc[t].get("desc_resolver_version")) != RESOLVER_VERSION

    def new_or_stale(t: str) -> bool:
        if force or existing.empty or t not in existing.index:
            return True
        if stale_resolver(t):
            return True
        age = _age(t)
        return age is None or age > REFRESH_DAYS

    def desc_retry(t: str) -> bool:
        """Re-attempt a row that has an identity but no description, on the short
        DESC_RETRY_DAYS cadence and only until MAX_DESC_TRIES — so a transient
        Wikipedia miss self-heals without a undescribable name looping forever."""
        if new_or_stale(t) or _has_desc(t):
            return False
        age = _age(t)
        tries = _int0(existing.loc[t].get("desc_tries"))
        return age is not None and age >= DESC_RETRY_DAYS and tries < MAX_DESC_TRIES

    def title_backfill(t: str) -> bool:
        """Backfill the wiki_title column (added for the offshore-attention chip)
        into already-cached rows that have a description but no resolved title — so
        the normal max_new-capped pass repopulates it incrementally without forcing
        a full re-fetch. Gated on the DESC_RETRY_DAYS cadence so a just-fetched row
        is never disturbed (a re-fetch could regress a good blurb). Rows still
        missing a description are already covered by the new/stale + desc_retry
        budgets above."""
        if new_or_stale(t) or desc_retry(t):
            return False
        if existing.empty or t not in existing.index:
            return False
        if not _has_desc(t):
            return False
        wt = _cell(existing.loc[t].get("wiki_title")) if "wiki_title" in existing.columns else None
        if wt is not None and str(wt).strip():
            return False
        age = _age(t)
        return age is not None and age >= DESC_RETRY_DAYS

    # new/stale names take the budget first; leftover budget retries empty
    # descriptions, then backfills any still-missing wiki_title for the attention chip
    primary = [t for t in universe if new_or_stale(t)]
    pset = set(primary)
    retries = [t for t in universe if t not in pset and desc_retry(t)]
    rset = pset | set(retries)
    backfill = [t for t in universe if t not in rset and title_backfill(t)]
    todo = (primary + retries + backfill)[:max_new]
    log.info("equity_profile: %d universe, %d new/stale + %d desc-retry + %d title-backfill → "
             "fetching %d (cap %d)",
             len(universe), len(primary), len(retries), len(backfill), len(todo), max_new)

    rows = []
    now = datetime.now(timezone.utc).isoformat()
    for t in todo:
        prior = {k: _cell(v) for k, v in
                 (existing.loc[t].to_dict() if (not existing.empty and t in existing.index) else {}).items()}
        display = names.get(t) or prior.get("name") or t   # clean breadth name (mixed-case)
        rec: dict = {"ticker": t, "name": display, "as_of": now}
        # carry forward previously-resolved identity so a transient SEC hiccup on a
        # retry can't blank out good chips
        for k in ("sic_description", "exchange", "hq"):
            if prior.get(k) is not None:
                rec[k] = prior[k]
        if t in cik:
            sec = _sec_submission(cik[t])          # may overwrite name with the SEC entity
            rec.update({k: v for k, v in sec.items() if v is not None})
        # Search the clean display name FIRST, the (ALL-CAPS) SEC name as backup:
        # "MICROSOFT CORP" ranks the EU antitrust case ahead of the company.
        desc, wtitle, strength = _wiki_description(
            display, rec.get("name"), sic_description=rec.get("sic_description"),
            hq=rec.get("hq"))
        # Carry a prior blurb forward ONLY when it was accepted by the CURRENT
        # resolver. The old carry-forward was unconditional, which would have
        # resurrected exactly the wrong-entity blurbs this version exists to
        # withhold: the collector would correctly refuse the restaurant page, then
        # immediately restore the restaurant text from the cache it was fixing.
        prior_desc = prior.get("description")
        prior_ok = _int0(prior.get("desc_resolver_version")) == RESOLVER_VERSION
        if not desc and prior_ok and isinstance(prior_desc, str) and prior_desc.strip():
            desc = prior_desc                       # transient Wikipedia miss, not a rejection
            strength = _cell(prior.get("desc_strength")) or strength
            wtitle = wtitle or _cell(prior.get("wiki_title"))
        rec["description"] = desc or None
        # persist the validated article title (reused by the offshore-attention
        # collector so it never re-resolves the page); never regress a good title.
        prior_title = prior.get("wiki_title")
        if not wtitle and prior_ok and isinstance(prior_title, str) and prior_title.strip():
            wtitle = prior_title
        rec["wiki_title"] = wtitle or None
        # bound the retry loop: reset on success, increment on a still-empty fetch
        rec["desc_tries"] = 0 if rec["description"] else _int0(prior.get("desc_tries")) + 1
        rec["source"] = "wikipedia+sec"
        # --- correction receipts: enough to audit any published blurb ----------
        rec["desc_strength"] = strength if rec["description"] else None
        rec["desc_resolver_version"] = RESOLVER_VERSION if rec["description"] else 0
        rec["desc_fetched_at"] = now if rec["description"] else None
        unchanged = (rec["description"] is not None
                     and isinstance(prior_desc, str)
                     and prior_desc.strip() == str(rec["description"]).strip())
        prior_first = _cell(prior.get("desc_first_seen"))
        rec["desc_first_seen"] = (prior_first if (unchanged and prior_first) else
                                  (now if rec["description"] else None))
        # when a previously-published blurb is withdrawn or replaced, stamp WHEN —
        # a correction without a clock cannot be reasoned about afterwards
        had_desc = isinstance(prior_desc, str) and bool(prior_desc.strip())
        rec["desc_superseded_at"] = (now if (had_desc and not unchanged)
                                     else _cell(prior.get("desc_superseded_at")))
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
