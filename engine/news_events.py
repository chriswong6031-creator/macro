"""Event-identity layer for news headlines.

LEAF · CONTEXT-ONLY · DISPLAY-ONLY. Pure functions — no network, no file I/O.
Imports nothing from the mechanical scoring core (conditions/regime/run/inputs/
equity_alloc) and nothing in the scoring path imports it. Every public function
returns plain data and NEVER raises into the build.

This module answers one question: WHAT HAPPENED? Keyword-theme tagging (NFP
tagged 'stocks', Nuveen tagged 'capital_return') is NOT event identity. This is.

PUBLIC API
----------
classify_event(title, body='') -> dict | None
    Deterministic event-type classification. Returns None when no class matches —
    most headlines are NOT typed events. Never force-fits.

extract_numbers(text) -> dict
    Dollar amounts (B/M/K scaling), percentages, EPS-style figures,
    guidance-range frames, payroll counts.

theme_centrality(title, theme, matched_keyword) -> 'primary'|'secondary'|'incidental'
    V1 heuristic: how central is the matched keyword to the headline's main action?

enrich_with_qbus(h, qbus_df) -> dict
    Attach event, centrality, novelty_z, echo to a headline dict (fail-open).

is_context_only = True  (schema contract)
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

is_context_only: bool = True


# --------------------------------------------------------------------------- #
# EVENT TAXONOMY
# ~20 deterministic classes; each entry:
#   name, patterns (list[re.Pattern]), direction, optional numeric requirement
#
# Precedence is the list ORDER — first match wins. Most-specific classes lead.
# --------------------------------------------------------------------------- #

# helper — compile once at import
def _re(*pats: str, flags=re.I | re.X) -> list[re.Pattern]:
    return [re.compile(p, flags) for p in pats]


# Event class definitions — list of dicts; precedence = list index (ascending).
# Each dict keys:
#   name       str
#   pats       list[re.Pattern]  — matched against title (+ body when provided)
#   direction  'bullish'|'bearish'|'mixed'|'informational'
#   need_num   bool  — True requires at least one number in the matched text
_EVENT_CLASSES: list[dict] = [

    # ---- guidance & pre-announcement ----------------------------------------
    {
        "name": "guidance_cut",
        "pats": _re(
            r"\b(?:cut[s]?|lower[s]?|reduce[s]?|trim[s]?|slash[es]*|pare[s]?)"
            r"\b[^.]{0,50}\b(?:guidance|outlook|forecast|revenue\s+(?:guidance|forecast)"
            r"|eps\s+(?:guidance|forecast)|annual\s+(?:forecast|guidance|revenue))\b",

            r"\b(?:guidance|outlook|forecast|revenue\s+forecast|annual\s+forecast)\b"
            r"[^.]{0,60}"
            r"\b(?:cut[s]?|lower[s]?|below|misses?|disappoint|reduce[s]?|slash[es]*|trim[s]?)\b",

            r"\bwarn[s]?\b[^.]{0,50}\b(?:below|miss|short(?:fall)?|disappoint|weak)\b",

            r"\b(?:issues?|issues)\s+(?:profit|revenue|earnings)\s+warning\b",
            r"\bprofit\s+warning\b",
        ),
        "direction": "bearish",
        "need_num": False,
    },
    {
        "name": "guidance_raise",
        "pats": _re(
            r"\b(?:raise[s]?|boost[s]?|lift[s]?|increas[es]+|hike[s]?|up(?:grade)?s?\s+)"
            r"\b[^.]{0,50}\b(?:guidance|outlook|forecast|revenue\s+forecast|"
            r"eps\s+(?:guidance|forecast)|annual\s+(?:forecast|guidance|revenue))\b",

            r"\b(?:guidance|outlook|forecast)\b[^.]{0,60}"
            r"\b(?:raise[s]?|boost[s]?|lift[s]?|above|beat[s]?|top[s]?|exceed[s]?)\b",

            r"\braise[s]?\s+(?:full.year|fy|q[1-4])\s+(?:guidance|forecast|outlook)\b",
            r"\braise[s]?\s+(?:revenue|earnings|eps|profit)\s+(?:guidance|forecast|outlook)\b",
        ),
        "direction": "bullish",
        "need_num": False,
    },
    {
        "name": "preannouncement",
        "pats": _re(
            r"\bpre.?announ(?:ces?|cing)\b",
            r"\bpreliminary\s+(?:results?|revenue|earnings|profit)\b",
            r"\bpre.?warning\b",
        ),
        "direction": "mixed",
        "need_num": False,
    },

    # ---- earnings -------------------------------------------------------
    {
        "name": "earnings_result",
        "pats": _re(
            r"\b(?:reports?|posts?|delivers?|records?)\s+(?:quarterly\s+)?"
            r"(?:earnings|results?|profit[s]?|revenue[s]?|eps)\b",

            r"\b(?:earnings|results?)\s+(?:beat|top[s]?|exceed|miss|disappoint|below)\b",
            r"\bq[1-4]\s+(?:earnings|results?|profit|revenue|eps)\b",
            r"\b(?:beats?|misses?)\s+(?:earnings|revenue|eps|profit)\s+(?:estimate|forecast|expectation)\b",
            r"\b(?:earnings|revenue)\s+(?:beat|miss)\b",
            r"\bfull.year\s+(?:earnings|profit|revenue)\b",
        ),
        "direction": "mixed",
        "need_num": False,
    },

    # ---- analyst actions ------------------------------------------------
    {
        "name": "analyst_estimate_revision",
        "pats": _re(
            r"\b(?:analyst[s]?|wall\s+street)\s+(?:cut[s]?|lower[s]?|raise[s]?|boost[s]?|hike[s]?)\s+(?:estimate|eps|target|forecast)\b",
            r"\b(?:estimate[s]?|forecast[s]?|eps\s+estimate[s]?)\s+(?:cut|lower|raise|boost|trimmed?|elevated?)\b",
            r"\bconsensus\s+(?:estimate|eps)\s+(?:cut|raise|lower|boost)\b",
        ),
        "direction": "mixed",
        "need_num": False,
    },
    {
        "name": "rating_change",
        "pats": _re(
            # "upgrades Apple to Overweight" — company name may appear between verb and rating
            r"\b(?:upgrade[sd]?|downgrade[sd]?)\b[^.]{0,40}?\b(?:to\s+)?(?:buy|sell|hold|neutral|outperform|underperform|overweight|underweight|strong\s+buy|market\s+perform)\b",
            r"\b(?:upgrade[sd]?|downgrade[sd]?)\s+(?:to\s+)?(?:buy|sell|hold|neutral|outperform|underperform|overweight|underweight|strong\s+buy|market\s+perform)\b",
            r"\b(?:initiates?|starts?|resumes?|reinstates?)\b[^.]{0,50}?\b(?:buy|sell|hold|neutral|outperform|underperform|overweight|underweight)\b",
            r"\b(?:cuts?|raise[s]?|boost[s]?|lower[s]?)\s+(?:price\s+target|pt)\b",
            r"\bprice\s+target\s+(?:cut|lowered?|raised?|boosted?|increased?)\b",
        ),
        "direction": "mixed",
        "need_num": False,
    },

    # ---- corporate actions -----------------------------------------------
    {
        "name": "contract_award",
        "pats": _re(
            r"\bwins?\s+\$?[\d.,]+\s*(?:billion|million|thousand|[BMK])\b[^.]{0,50}\b(?:contract|award|deal|order)\b",
            r"\b(?:award[ed]?|wins?|secures?|land[s]?)\s+(?:a\s+)?(?:\$[^\s]+\s+)?(?:[\d.,]+\s*(?:billion|million|thousand|[BMK])[^.]{0,30})?\b(?:contract|deal|order|award|agreement)\b",
            r"\b(?:contract|award|order)\s+(?:worth|valued\s+at|of)\s+\$?[\d.,]+\s*(?:billion|million|[BMK])\b",
        ),
        "direction": "bullish",
        "need_num": True,
    },
    {
        "name": "customer_win",
        "pats": _re(
            r"\b(?:wins?|secures?|land[s]?|sign[s]?|close[s]?)\s+(?:a\s+)?(?:major\s+|new\s+)?(?:customer|client|partnership|collaboration|agreement|deal)\b",
            r"\b(?:customer|client|partnership)\s+(?:win|agreement|sign)\b",
            r"\bsign[s]?\s+(?:multi.year|long.term|strategic)\s+(?:agreement|deal|partnership|contract)\b",
        ),
        "direction": "bullish",
        "need_num": False,
    },
    {
        "name": "customer_loss",
        "pats": _re(
            r"\b(?:lose[s]?|lost)\s+(?:a\s+)?(?:major\s+|key\s+)?(?:customer|client|contract|account)\b",
            r"\b(?:customer|client|contract)\s+(?:terminat|cancel|loss|lost|walk|exit)\b",
            r"\b(?:terminat[es]+|cancel[s]?)\s+(?:its\s+)?(?:contract|partnership|agreement|deal)\b",
        ),
        "direction": "bearish",
        "need_num": False,
    },
    {
        "name": "product_launch",
        "pats": _re(
            r"\b(?:launch[es]+|introduc[es]+|unveil[s]?|release[s]?|debut[s]?|roll[s]?\s+out)"
            r"\b[^.]{0,40}?\b(?:product[s]?|service[s]?|platform|model|device|app|feature|drug|treatment|vaccine|chip|processor|software)\b",
            r"\b(?:new\s+)?(?:product[s]?|service|platform|model|device|app|drug|treatment|vaccine|chip|processor)\s+(?:launch|debut|release|unveil)\b",
        ),
        "direction": "bullish",
        "need_num": False,
    },
    {
        "name": "product_delay",
        "pats": _re(
            r"\b(?:delay[s]?|postpone[s]?|push[es]?\s+back|defer[s]?)\b"
            r"[^.]{0,40}?\b(?:launch|release|debut|introduction|rollout)\b",
            r"\b(?:launch|release|debut|rollout)\s+(?:delayed?|postponed?|pushed?\s+back|defer)\b",
            r"\bsetback\b[^.]{0,40}\b(?:product|launch|release|drug|approval)\b",
        ),
        "direction": "bearish",
        "need_num": False,
    },

    # ---- management -------------------------------------------------------
    {
        "name": "management_change",
        "pats": _re(
            r"\b(?:names?|appoints?|hires?|elect[s]?)\b[^.]{0,50}?\b(?:ceo|cfo|coo|cto|president|chairman|cro|chief|executive)\b",
            # role + person name + verb (e.g. "CEO Pat Gelsinger steps down")
            r"\b(?:ceo|cfo|coo|cto|president|chief\s+executive)\b[^.]{0,40}?"
            r"\b(?:resign|step[s]?\s+down|retire|depart|leave[s]?|exit|quit)\b",
            r"\b(?:resign[s]?|step[s]?\s+down|depart[s]?|exit[s]?)\s+as\s+(?:ceo|cfo|coo|cto|chief|president)\b",
        ),
        "direction": "mixed",
        "need_num": False,
    },

    # ---- legal / regulatory -----------------------------------------------
    {
        "name": "regulatory_probe",
        "pats": _re(
            # regulator + action verb (within ~50 chars)
            # Note: many verb stems (investigat-, scrutin-) don't end on word boundary,
            # so we use word-boundary only on the full regulator token, not the stem.
            r"\b(?:sec|ftc|doj|fda|cfpb|epa|nlrb|eu\s+(?:commission|regulator))\b"
            r"[^.]{0,50}?"
            r"(?:investigat|probe[s]?|inquir|scrutin|review|fine[s]?|charge[s]?|sanction|enforc)",

            # action verb then regulator
            r"\b(?:investigat|probe[s]?|inquir|antitrust|scrutin|regulatory\s+action)"
            r"[^.]{0,50}?"
            r"\b(?:sec|ftc|doj|fda|cfpb|epa|nlrb|justice\s+department|regulator)\b",

            r"\b(?:antitrust\s+(?:probe|investigation|suit|lawsuit|scrutiny)|ftc\s+(?:probe|sues?|investigation|blocks?))\b",
            r"\b(?:fda\s+(?:rejects?|approves?|clears?|denies?|holds?|delays?))\b",
        ),
        "direction": "bearish",
        "need_num": False,
    },
    {
        "name": "litigation",
        "pats": _re(
            r"\b(?:sue[s]?|sues|lawsuit[s]?|files?\s+suit|legal\s+action|litigation)\b",
            r"\b(?:settle[s]?|settlement)\s+(?:lawsuit|suit|case|charges?|claims?)\b",
            r"\b(?:court|jury)\s+(?:rules?|finds?|order[s]?|award[s]?)\b[^.]{0,40}\b(?:against|in\s+favor)\b",
        ),
        "direction": "bearish",
        "need_num": False,
    },

    # ---- capital actions --------------------------------------------------
    {
        "name": "equity_offering",
        "pats": _re(
            r"\b(?:prices?|launch[es]+|files?|announces?|completes?|plans?)\s+(?:an?\s+)?"
            r"(?:public\s+)?(?:equity\s+)?(?:offering|share\s+issuance|secondary\s+offering|ipo|spo|follow.on)\b",

            r"\b(?:follow.on\s+offering|public\s+offering|share\s+sale|stock\s+offering|new\s+shares)\b",
            r"\bprices?\s+(?:its\s+)?ipo\b",
        ),
        "direction": "bearish",
        "need_num": False,
    },
    {
        "name": "buyback",
        "pats": _re(
            r"\b(?:announces?|authorizes?|approves?|launch[es]+|boost[s]?|expand[s]?)\s+(?:a\s+)?(?:new\s+)?"
            r"\$?[\d.,]*\s*(?:billion|million|[BMK])?\s*(?:share\s+)?(?:buyback|repurchase|buy.back)\b",

            r"\b(?:share\s+)?(?:buyback|repurchase)\s+(?:program|plan|authoriz|announc)\b",
            r"\brepurchas[es]+\s+(?:up\s+to\s+)?\$?[\d.,]+\s*(?:billion|million|[BMK])\b",
        ),
        "direction": "bullish",
        "need_num": False,
    },
    {
        "name": "dividend_change",
        "pats": _re(
            r"\b(?:raise[s]?|boost[s]?|hike[s]?|increas[es]+|cut[s]?|reduce[s]?|suspend[s]?|eliminate[s]?)\s+(?:its\s+)?(?:quarterly\s+|annual\s+)?dividend\b",
            r"\bdividend\s+(?:raise|hike|boost|increase|cut|reduction|suspension|elimination)\b",
            r"\b(?:initiates?|declares?|announces?)\s+(?:its\s+)?(?:first\s+)?dividend\b",
            r"\bspecial\s+dividend\b",
        ),
        "direction": "mixed",
        "need_num": False,
    },

    # ---- M&A --------------------------------------------------------------
    {
        "name": "mna_confirmed",
        "pats": _re(
            r"\b(?:agrees?\s+to|confirms?\s+|announces?\s+)(?:acquire|merge|buy)\b",
            r"\b(?:acquires?|merges?\s+with|to\s+be\s+acquired|takeover\s+(?:bid|offer|deal))\b",
            r"\b(?:agreed|confirmed)\s+(?:acquisition|merger|takeover|deal|transaction)\b",
            # dollar-anchored acquisition — "in a $Xb deal" or "$Xb acquisition of"
            r"\b\$[\d.,]+\s*(?:billion|million|[BMK])\b[^.]{0,40}\b(?:acquisition|merger|deal)\b",
            r"\b(?:acquisition|merger)\s+(?:in\s+a\s+)?\$[\d.,]+\s*(?:billion|million|[BMK])\b",
            # close / complete language
            r"\b(?:complet[es]+|closed?|clos[es]+)\s+(?:its\s+)?(?:acquisition|merger|deal|transaction)\b",
        ),
        "direction": "bullish",
        "need_num": False,
    },
    {
        "name": "mna_rumor",
        "pats": _re(
            r"\b(?:reports?|sources?)\s+(?:say|suggest|indicate)\b[^.]{0,50}"
            r"\b(?:acquisition|merger|buyout|takeover|deal)\b",

            r"\b(?:explore[s]?|consider[s]?|eye[s]?|in\s+talks?|mulling?)\s+"
            r"(?:a\s+)?(?:sale|acquisition|merger|buyout|strategic\s+(?:option|alternative|review))\b",

            r"\bstrategic\s+(?:review|alternative[s]?)\b",
            r"\bbidding\s+war\b",
        ),
        "direction": "bullish",
        "need_num": False,
    },

    # ---- activist --------------------------------------------------------
    {
        "name": "activist_campaign",
        "pats": _re(
            r"\b(?:activist|hedge\s+fund|carl\s+icahn|nelson\s+peltz|elliott|starboard|jana|third\s+point)\b"
            r"[^.]{0,60}\b(?:stake|position|target[s]?|push[es]+|pressure[s]?|demand[s]?|call[s]?\s+for|campaign)\b",

            r"\btakes?\s+(?:a\s+)?(?:significant\s+)?stake\b[^.]{0,30}\bactivist\b",
            r"\bactivist\s+(?:investor|pressure|campaign|push|stake|position)\b",
        ),
        "direction": "bullish",
        "need_num": False,
    },

    # ---- macro data release -----------------------------------------------
    {
        "name": "macro_release",
        "pats": _re(
            # payrolls / labor
            r"\b(?:nonfarm\s+payroll|payrolls?\s+(?:add|rise|fall|gain|report|grew?|drop|surpass|beat|miss))\b",
            r"\b(?:jobs?\s+report|employment\s+(?:situation|report|data)|labor\s+market\s+report)\b",
            r"\b(?:initial\s+(?:jobless\s+)?claims?|continuing\s+claims?|jolts?|job\s+openings)\s+(?:rise|fall|drop|climb|jump|decline|hit|tick)\b",
            r"\b(?:unemployment\s+rate)\s+(?:rise[s]?|fall[s]?|held?|drop[s]?|tick[s]?|unchanged)\b",
            # inflation
            r"\b(?:cpi|pce|ppi|consumer\s+price\s+index|personal\s+consumption\s+expenditure[s]?)\s+"
            r"(?:rose?|fell?|rose?|climb[s]?|drop[s]?|tick[s]?|show[s]?|came?\s+in|beat|miss|rose?\s+by)\b",
            r"\bcore\s+(?:cpi|pce|ppi|inflation)\s+(?:rose?|fell?|tick[s]?|held?)\b",
            # growth / gdp
            r"\bgdp\s+(?:grew?|grew|fell?|rose?|declined?|contracted?|expanded?|came?\s+in|beat|miss)\b",
            r"\b(?:advance|preliminary|final)\s+gdp\b",
            r"\b(?:ism|pmi)\s+(?:manufacturing|services?|composite)\s+(?:rose?|fell?|tick[s]?|came?\s+in|hit[s]?)\b",
            # Fed / FOMC
            r"\bfomc\s+(?:minutes?|statement|meeting|decision|raises?|cuts?|holds?|keeps?)\b",
            r"\bfed\s+(?:raises?|cuts?|holds?|keeps?)\s+(?:rates?|interest\s+rates?|federal\s+funds)\b",
            r"\bfederal\s+reserve\s+(?:raises?|cuts?|holds?|keeps?)\b",
            r"\b(?:rate\s+(?:hike|cut|pause|skip|hold))\b",
            # treasury / credit
            r"\b(?:treasury\s+yields?|10.year\s+yield)\s+(?:rose?|fell?|hit[s]?|touch[es]+|climb[s]?)\b",
            r"\b(?:retail\s+sales?|durable\s+goods|housing\s+starts?|building\s+permits?)\s+"
            r"(?:rose?|fell?|grew?|dropped?|declined?|came?\s+in|beat|miss|tick[s]?)\b",
        ),
        "direction": "informational",
        "need_num": False,
    },

    # ---- policy / trade / geopolitical -----------------------------------
    {
        "name": "policy_trade_control",
        "pats": _re(
            r"\b(?:tariff[s]?|trade\s+war|trade\s+deal|trade\s+agreement|sanction[s]?|export\s+control[s]?|import\s+ban|embargo)\b",
            r"\b(?:white\s+house|congress|senate|administration|executive\s+order)\b[^.]{0,50}"
            r"\b(?:tariff|trade|sanction|tax|regulation|policy|spending|budget|deficit)\b",

            r"\b(?:bans?|restrict[s]?|block[s]?|limit[s]?)\s+(?:export[s]?|import[s]?|sale[s]?|chip[s]?|technology|ai)\b",
            r"\b(?:section\s+232|section\s+301|ipa[s]?\s+(?:act|review|subsidy)|chips\s+act|ira\s+(?:act|subsidy|credit))\b",
        ),
        "direction": "mixed",
        "need_num": False,
    },

    # ---- distress --------------------------------------------------------
    {
        "name": "bankruptcy_restructuring",
        "pats": _re(
            r"\b(?:files?\s+(?:for\s+)?(?:chapter\s+(?:11|7|15))|bankruptcy|bankrupt)\b",
            r"\b(?:restructuring|debt\s+restructuring|out.of.court\s+(?:restructuring|deal)|creditor\s+agreement)\b",
            r"\b(?:liquidat|wind[s]?\s+down|shutter[s]?|close[s]?\s+doors?)\b[^.]{0,30}\bcompany\b",
        ),
        "direction": "bearish",
        "need_num": False,
    },
]

# Build a fast name→entry dict for reference
_CLASS_MAP: dict[str, dict] = {e["name"]: e for e in _EVENT_CLASSES}


# --------------------------------------------------------------------------- #
# 1. classify_event
# --------------------------------------------------------------------------- #
def classify_event(title: str, body: str = "") -> dict | None:
    """Classify a headline into a deterministic event type.

    Returns a dict or None (None = no confident match — do NOT force-fit):
      {
        event_type: str,       # one of the ~23 class names
        direction:  str,       # 'bullish'|'bearish'|'mixed'|'informational'
        numbers:    dict,      # extract_numbers() result over title+body
        confidence: str,       # 'high'|'medium'|'low'
        matched:    str,       # which pattern (repr) fired first
      }

    Precedence: list order — most-specific first. Runs title first, then appends
    body (when provided) for a second-pass on the same pattern set. Body is only
    used as a confirming signal; title alone decides for efficiency. PURE."""
    title = (title or "").strip()
    if not title:
        return None
    combined = title + " " + (body or "")
    # try title alone first, then combined
    for search_text in (title, combined):
        low = search_text
        for cls in _EVENT_CLASSES:
            for pat in cls["pats"]:
                m = pat.search(low)
                if m:
                    nums = extract_numbers(combined)
                    if cls.get("need_num") and not _has_num(nums):
                        continue
                    # confidence heuristic: title-only match = high; body-assist = medium
                    conf = "high" if search_text is title else "medium"
                    # weak signals (mna_rumor, customer_win without a number) = medium
                    if cls["name"] in ("mna_rumor", "customer_win", "customer_loss",
                                       "analyst_estimate_revision"):
                        conf = "medium" if conf == "high" else "low"
                    return {
                        "event_type": cls["name"],
                        "direction": cls["direction"],
                        "numbers": nums,
                        "confidence": conf,
                        "matched": pat.pattern[:80],
                    }
    return None


def _has_num(nums: dict) -> bool:
    """True if extract_numbers found at least one value."""
    return bool(
        nums.get("usd") is not None
        or nums.get("percentages")
        or nums.get("eps")
        or nums.get("guidance_range")
        or nums.get("count")
    )


# --------------------------------------------------------------------------- #
# 2. extract_numbers
# --------------------------------------------------------------------------- #
# Patterns — compiled once at module load.
_USD_RE = re.compile(
    r"\$\s*(?P<val>[\d,]+(?:\.\d+)?)\s*(?P<unit>[BbMmKk](?:illion|illion)?\b|billion|million|thousand)?",
    re.I)
_PCT_RE = re.compile(r"(?P<pct>-?[\d,]+(?:\.\d+)?)\s*%")
_EPS_RE = re.compile(
    r"\b(?:eps|earnings?\s+per\s+share|loss\s+per\s+share|diluted\s+eps)\s+"
    r"(?:of\s+)?\$?\s*(?P<val>-?[\d.]+)\b",
    re.I)
_GUID_RANGE_RE = re.compile(
    r"(?:sees?|expects?|guides?\s+(?:for|to)?|targets?|raises?\s+(?:guidance|forecast)\s+to)\s+"
    r"(?:fy|full.year|annual|quarterly|q[1-4])?\s*"
    r"(?:revenue|sales|eps|profit|net\s+income)?\s*"
    r"\$?\s*(?P<lo>[\d.]+)\s*(?:[-–—to]+)\s*\$?\s*(?P<hi>[\d.]+)\s*"
    r"(?P<unit>[BbMmKk](?:illion)?\b|billion|million)?",
    re.I)
_COUNT_RE = re.compile(
    r"\b(?P<cnt>[\d,]+)\s+(?:jobs?|workers?|employees?|positions?|payrolls?|cuts?|layoffs?|people)\b",
    re.I)

_UNIT_MAP = {
    "b": 1_000_000_000, "billion": 1_000_000_000,
    "m": 1_000_000,     "million": 1_000_000,
    "k": 1_000,         "thousand": 1_000,
}


def _parse_float(s: str) -> float:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return float("nan")


def extract_numbers(text: str) -> dict:
    """Extract structured numeric values from news text.

    Returns:
      {
        usd:           float | None  — first dollar amount in raw dollars
        usd_all:       list[float]   — all dollar amounts found (raw dollars)
        percentages:   list[float]
        eps:           float | None
        guidance_range:{lo, hi, unit_str} | None
        count:         int | None    — payroll/job counts
      }
    All extraction is text-only — never raises."""
    text = (text or "")

    # --- USD ---------------------------------------------------------------
    usd_all: list[float] = []
    for m in _USD_RE.finditer(text):
        val = _parse_float(m.group("val"))
        unit_raw = (m.group("unit") or "").lower().strip()
        mult = _UNIT_MAP.get(unit_raw[:1] if unit_raw else "", 1)
        # special-case full word units
        for kw, mv in (("billion", 1_000_000_000), ("million", 1_000_000), ("thousand", 1_000)):
            if kw in unit_raw:
                mult = mv
                break
        if not (val != val):  # skip NaN
            usd_all.append(val * mult)

    # --- percentages -------------------------------------------------------
    pcts: list[float] = []
    for m in _PCT_RE.finditer(text):
        v = _parse_float(m.group("pct"))
        if not (v != v):
            pcts.append(v)

    # --- EPS ---------------------------------------------------------------
    eps: float | None = None
    m = _EPS_RE.search(text)
    if m:
        v = _parse_float(m.group("val"))
        if not (v != v):
            eps = v

    # --- guidance range ---------------------------------------------------
    guide: dict | None = None
    m = _GUID_RANGE_RE.search(text)
    if m:
        lo = _parse_float(m.group("lo"))
        hi = _parse_float(m.group("hi"))
        unit_raw = (m.group("unit") or "").lower().strip()
        mult = _UNIT_MAP.get(unit_raw[:1] if unit_raw else "", 1)
        for kw, mv in (("billion", 1_000_000_000), ("million", 1_000_000), ("thousand", 1_000)):
            if kw in unit_raw:
                mult = mv
                break
        if not (lo != lo or hi != hi):
            guide = {"lo": lo * mult, "hi": hi * mult, "unit_str": unit_raw or ""}

    # --- job/payroll counts -----------------------------------------------
    count: int | None = None
    m = _COUNT_RE.search(text)
    if m:
        v = _parse_float(m.group("cnt"))
        if not (v != v):
            count = int(v)

    return {
        "usd": usd_all[0] if usd_all else None,
        "usd_all": usd_all,
        "percentages": pcts,
        "eps": eps,
        "guidance_range": guide,
        "count": count,
    }


# --------------------------------------------------------------------------- #
# 3. theme_centrality
# --------------------------------------------------------------------------- #

# Action-frame verbs: these signal that the keyword is in an active role.
_ACTION_VERBS = re.compile(
    r"\b(?:cut[s]?|raise[s]?|boost[s]?|lower[s]?|slash[es]*|hike[s]?|trim[s]?|"
    r"reduce[s]?|increas[es]+|declare[s]?|announce[s]?|approve[s]?|"
    r"suspend[s]?|eliminat[es]+|initiat[es]+|launch[es]+|award[s]?|"
    r"win[s]?|loses?|invest[s]?|acquir[es]+|bid[s]?|explore[s]?|"
    r"reports?|posts?|delivers?|beats?|misses?|tops?|exceeds?|"
    r"probe[s]?|investigat[es]+|sue[s]?|file[s]?|settle[s]?|"
    r"names?|appoints?|resign[s]?|retire[s]?|steps?\s+down|"
    r"price[s]?|offer[s]?|acquires?|merges?|buys?|sells?|"
    r"upgrade[s]?|downgrade[s]?|initiat[es]+|reiterat[es]+|"
    r"warns?|guide[s]?|sees?|forecast[s]?|targets?)\b",
    re.I)

# Leading-clause boundary: first ~60 chars of the title tend to hold the subject.
_LEADING_CHARS = 65


def theme_centrality(title: str, theme: str, matched_keyword: str) -> str:
    """Heuristic: how central is the matched keyword to the headline's main action?

    primary    — keyword in the leading clause (~first 65 chars) OR adjacent to an
                 action-frame verb (within 50 chars).
    secondary  — keyword present but not in the leading clause; or present with no
                 adjacent action verb.
    incidental — keyword not found in the title at all.

    PURE — no side-effects, no network. Never raises."""
    title = (title or "").strip()
    kw = (matched_keyword or "").strip().lower()
    if not title or not kw:
        return "incidental"
    low = title.lower()
    pos = low.find(kw)
    if pos < 0:
        return "incidental"

    # In leading clause?
    if pos < _LEADING_CHARS:
        return "primary"

    # Adjacent to an action verb (within 50 chars either side)?
    window_start = max(0, pos - 50)
    window_end = min(len(low), pos + len(kw) + 50)
    window = low[window_start:window_end]
    if _ACTION_VERBS.search(window):
        return "primary"

    return "secondary"


# --------------------------------------------------------------------------- #
# 4. QBUS READ-BACK: enrich_with_qbus
# --------------------------------------------------------------------------- #
def _load_qbus_df():
    """Load the qbus items parquet exactly once per call. Returns df or None."""
    try:
        from engine import qbus
        return qbus.read_items()
    except Exception as e:  # noqa: BLE001
        log.debug("qbus load failed (%s)", e)
        return None


def enrich_with_qbus(h: dict, qbus_df=None) -> dict:
    """Attach event-identity + qbus intelligence to a KEPT headline dict.

    Adds:
      event        — classify_event result (or None)
      centrality   — theme_centrality result ('primary'|'secondary'|'incidental')
      novelty_z    — float | None  (qbus novelty z-score for the first ticker/theme)
      echo         — {n_sources, n_desks} | None  (qbus cross-desk corroboration)

    STRICTLY FAIL-OPEN: empty/missing qbus store → None fields.
    DISPLAY-ONLY: never mutates keep/drop decision, never raises. PURE."""
    out = dict(h)
    title = h.get("title", "")
    theme = h.get("theme") or ""
    # best matched_keyword: use the theme token itself as the cheapest proxy
    matched_kw = theme.replace("_", " ")

    # event classification
    event = None
    try:
        event = classify_event(title, h.get("summary", "") or "")
    except Exception as e:  # noqa: BLE001
        log.debug("classify_event failed (%s)", e)

    # centrality
    centrality = "incidental"
    try:
        centrality = theme_centrality(title, theme, matched_kw)
    except Exception as e:  # noqa: BLE001
        log.debug("theme_centrality failed (%s)", e)

    # qbus read-back — one load per call, shared across headlines by passing df in
    novelty = None
    echo = None
    try:
        df = qbus_df  # caller may pass a pre-loaded df to avoid re-reading per item
        if df is None:
            df = _load_qbus_df()

        if df is not None and len(df) > 0:
            from datetime import date, timezone, datetime as dt_cls
            from engine import qbus as qbus_mod

            # pick subject: first ticker, else theme
            tickers = h.get("tickers") or []
            subject = tickers[0] if tickers else theme

            # get a date for asof — from seendate or now
            asof_str = h.get("seendate") or h.get("fetched_at", "")
            try:
                asof = dt_cls.fromisoformat(
                    asof_str[:10] if asof_str else ""
                ).date()
            except (ValueError, TypeError):
                asof = date.today()

            if subject:
                novelty = qbus_mod.novelty_z(subject, asof, df=df)

            # echo: exact item_id join first (a story ingested under the wire
            # desks' norm_title|host id basis matches directly) …
            event_key = ""
            item_id = h.get("_id", "")
            if item_id and "item_id" in df.columns:
                sub = df[df["item_id"] == item_id]
                if len(sub) > 0:
                    event_key = str(sub.iloc[0].get("event_key") or "")
            if not event_key:
                # … falling back to the shingled-title cluster match for
                # headlines never ingested under that exact id (another desk's
                # crawl of the same story carries a different host/title).
                # `asof` above already keys off the headline's own seendate
                # day when parseable.
                event_key = qbus_mod.event_key_for_title(title, asof, df=df) or ""
            if event_key:
                raw_echo = qbus_mod.echo_stats(event_key, df=df, asof=asof)
                if raw_echo:
                    echo = {
                        "n_sources": raw_echo.get("n_sources"),
                        "n_desks": raw_echo.get("n_desks"),
                    }
    except Exception as e:  # noqa: BLE001
        log.debug("qbus read-back failed (%s)", e)

    out["event"] = event
    out["centrality"] = centrality
    out["novelty_z"] = novelty
    out["echo"] = echo
    return out
