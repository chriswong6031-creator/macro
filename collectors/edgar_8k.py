"""SEC EDGAR 8-K MATERIAL-EVENT collector — the filing-time latency channel.

8-K current reports are filed within ~4 business days of a material corporate event, so
they lead the news narrative AND the tape. This collector reads the structured SEC
submissions feed (data.sec.gov/submissions/CIK##########.json — keyless, the `items` field
is machine-readable, not text-parsed) for every narrative-basket member, keeps only MATERIAL
item codes (new material agreements, acquisitions, financings, leadership changes, Reg-FD /
other material events — NOT routine earnings 2.02 / voting 5.07 / exhibits 9.01), and writes:

  * data/edgar/material_8k_events.parquet  — append-only, key-deduped per accession (PIT +
      _first_seen). Per-TICKER convergence channel (engine.altdata `material_events`).
  * data/edgar/material_8k_velocity.parquet — derived per-BASKET count, recent-60d vs
      prior-60d (the 'theme_event' Divergence-Radar leg in engine.theme_activity).

The ONLY new source that touches all 31 themes — including the healthcare blind spot, where
FDA actions land as 8-K item 8.01. Keyless; reuses edgar.py's cached CIK map + fair-access UA.
Display / context only.
"""
from __future__ import annotations

import html as _html
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from lib import config

log = logging.getLogger(__name__)

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{:010d}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
# SEC fair-access requires a descriptive name + contact email; www.sec.gov 403s a UA without
# one (data.sec.gov is more lenient). RFC2606 placeholder — same pattern as edgar_trumpflow.
_SEC_UA = "macro-dashboard admin@macro-dashboard.example.com"


def _sec_get_json(url: str, retries: int = 3, timeout: int = 30) -> dict | None:
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": _SEC_UA, "Accept-Encoding": "gzip, deflate"}, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    if last is not None and is_connection_error(last):
        raise last
    return None


def _company_tickers() -> dict | None:
    """SEC ticker->CIK file, cached locally (shared with collectors/edgar.py). Fetched with a
    fair-access UA so www.sec.gov doesn't 403; falls back to the cache on any fetch failure."""
    cache = config.data_dir() / "edgar" / "company_tickers.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except Exception:  # noqa: BLE001
            pass
    data = _sec_get_json(TICKERS_URL)
    if data:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data))
    return data


def _cik_map(universe: list[str]) -> dict[str, int]:
    """ticker -> CIK from SEC company_tickers.json (exact + dash/dot variants)."""
    data = _company_tickers()
    if not data:
        return {}
    sec = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
    out: dict[str, int] = {}
    for t in universe:
        u = t.upper()
        for cand in (u, u.replace("-", "."), u.replace(".", "-"), u.split("-")[0], u.split(".")[0]):
            if cand in sec:
                out[t] = sec[cand]
                break
    return out
# material item codes worth a signal (activity, not routine housekeeping):
#   1.01 material definitive agreement · 1.02 termination of material agreement ·
#   1.03 bankruptcy/receivership · 2.01 completion of acquisition ·
#   2.03 creation of a direct financial obligation ·
#   2.04 triggering of direct financial obligation (default/acceleration) ·
#   3.01 delisting notice / listing-standard failure ·
#   3.02 unregistered equity sales · 4.02 non-reliance on prior financials
#   (restatement/material weakness) · 5.02 director/officer change ·
#   7.01 Reg-FD disclosure · 8.01 other material event (where FDA/major news lands)
# LHB-R7 expansion for long-hold A6 hard-stop routing + B1 hardening ladder
# (research/LONG_HOLD_LOBE_BRAINSTORM_ADJUDICATION_BY_FABLE.md)
MATERIAL_ITEMS = {
    "1.01", "1.02", "1.03",
    "2.01", "2.03", "2.04",
    "3.01", "3.02",
    "4.02",
    "5.02",
    "7.01", "8.01",
}

# Velocity radar leg pinned to the original six codes — the per-basket velocity feeds
# the live theme Divergence-Radar leg (engine.theme_activity); the LHB-R7 expansion
# must not silently shift that signal, so velocity stays pinned to the original six
# codes.  Expanded codes are for downstream long-hold consumers of
# material_8k_events.parquet only.
LEGACY_VELOCITY_ITEMS = frozenset({"1.01", "2.01", "2.03", "5.02", "7.01", "8.01"})
_ITEM_RE = re.compile(r"\d\.\d{2}")
RECENT_D = 60
PRIOR_D = 60
PACE_S = 0.12  # SEC fair-access: <=10 req/s

# Optional per-filing extraction columns written by enrich_contract_amounts().  Kept in
# one place because BOTH the enrichment writer and the accession-dedup merge in
# _merge_events must agree on the list — a field added to one and not the other is blanked
# the next time an already-enriched accession is re-scanned.
_ENRICH_COLS = (
    "amount_usd", "counterparty", "extraction_ok",
    "counterparty_ok", "amount_src", "counterparty_src", "enrich_rev",
)


def _membership() -> dict:
    try:
        return json.loads((config.data_dir() / "baskets" / "membership.json").read_text()).get("baskets", {})
    except Exception:  # noqa: BLE001
        return {}


def _universe(mem: dict) -> list[str]:
    seen, out = set(), []
    for b in mem.values():
        for m in b.get("members", []):
            t = m.get("ticker")
            if t and not m.get("removed") and t not in seen:
                seen.add(t)
                out.append(t)
    return out


class Edgar8KAdapter(Adapter):
    name = "edgar_8k"
    group = "edgar"
    stale_after_days = 5

    def _events_path(self):
        p = config.data_dir() / "edgar" / "material_8k_events.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _velocity_path(self):
        return config.data_dir() / "edgar" / "material_8k_velocity.parquet"

    def _pull_ticker(self, ticker: str, cik: int) -> list[dict]:
        """Material-8K rows for one CIK from the structured submissions feed."""
        data = _sec_get_json(SUBMISSIONS_URL.format(int(cik)), retries=3)
        if not data:
            return []
        rec = (data.get("filings") or {}).get("recent") or {}
        forms = rec.get("form") or []
        out = []
        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            raw = (rec.get("items") or [None] * len(forms))[i] or ""
            codes = set(_ITEM_RE.findall(raw))
            mat = sorted(codes & MATERIAL_ITEMS)
            if not mat:
                continue
            out.append({
                "ticker": ticker, "cik": int(cik), "form": form,
                "filing_date": (rec.get("filingDate") or [None] * len(forms))[i],
                "items": ",".join(mat),
                "accession": (rec.get("accessionNumber") or [None] * len(forms))[i],
            })
        return out

    def _merge_events(self, new: pd.DataFrame) -> pd.DataFrame:
        new = new.copy()
        now_ts = datetime.now(timezone.utc).isoformat()
        # Only stamp rows that are genuinely new (will not exist in the stored file yet).
        new["_first_seen"] = now_ts
        path = self._events_path()
        if path.exists():
            old = pd.read_parquet(path)
            combined = pd.concat([old, new], ignore_index=True)
        else:
            combined = new

        # Groupby-accession merge: for each accession that appears more than once
        # (e.g. an accession already stored with truncated items before the LHB-R7
        # expansion, or a re-scan after back-fill), produce exactly one output row:
        #   items        — comma-joined sorted union of all codes seen across all rows
        #   _first_seen  — earliest (minimum) _first_seen stamp (preserves PIT)
        #   other cols   — values from the earliest-_first_seen row; for the optional
        #                  extraction fields (_ENRICH_COLS) take the first non-null across
        #                  duplicates so enrichment results survive the merge
        def _agg_accession(grp: pd.DataFrame) -> pd.Series:
            # Sort so the earliest _first_seen row comes first
            grp = grp.sort_values("_first_seen")
            base = grp.iloc[0].copy()
            # Union of items codes
            all_codes: set[str] = set()
            for raw in grp["items"].dropna():
                for code in str(raw).split(","):
                    code = code.strip()
                    if code:
                        all_codes.add(code)
            base["items"] = ",".join(sorted(all_codes))
            # First non-null for optional enrichment columns (_ENRICH_COLS — a new
            # extraction field added there must survive the accession merge too, or a
            # re-scan of an already-enriched accession silently blanks it)
            for col in _ENRICH_COLS:
                if col in grp.columns:
                    non_null = grp[col].dropna()
                    base[col] = non_null.iloc[0] if not non_null.empty else None
            return base

        if combined.duplicated(subset=["accession"]).any():
            # groupby(as_index=False) keeps the key column in the result so we never
            # lose the accession column after apply() consumes it as the group key.
            combined = (
                combined.groupby("accession", sort=False, as_index=False)
                .apply(_agg_accession, include_groups=False)
                .reset_index(drop=True)
            )
            # Restore column order: mandatory cols first, then any extras
            mandatory = ["ticker", "cik", "form", "filing_date", "items", "accession", "_first_seen"]
            extras = [c for c in combined.columns if c not in mandatory]
            combined = combined[mandatory + extras]
        else:
            combined = combined.reset_index(drop=True)

        combined.to_parquet(path)
        return combined

    def _velocity(self, events: pd.DataFrame, mem: dict) -> pd.DataFrame:
        """Per-basket material-8K counts: recent RECENT_D days vs the prior PRIOR_D.

        Only events whose items field intersects LEGACY_VELOCITY_ITEMS are counted here.
        The LHB-R7 expansion added six new codes to MATERIAL_ITEMS; those codes must not
        silently shift the Divergence-Radar signal — velocity is pinned to the original
        six codes that the live theme_activity engine was calibrated against.
        """
        ev = events.copy()
        # Filter to LEGACY_VELOCITY_ITEMS: keep rows where at least one code in the
        # comma-joined items string is a member of the original six-code set.
        def _intersects_legacy(items_str: str) -> bool:
            if not items_str:
                return False
            return bool({c.strip() for c in str(items_str).split(",")} & LEGACY_VELOCITY_ITEMS)

        ev = ev[ev["items"].fillna("").apply(_intersects_legacy)]
        ev["d"] = pd.to_datetime(ev["filing_date"], errors="coerce")
        ev = ev[ev["d"].notna()]
        t0 = ev["d"].max() if not ev.empty else pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))
        rec_lo = t0 - pd.Timedelta(days=RECENT_D)
        pri_lo = t0 - pd.Timedelta(days=RECENT_D + PRIOR_D)
        rows = []
        for bid, b in mem.items():
            members = {m.get("ticker") for m in b.get("members", []) if m.get("ticker") and not m.get("removed")}
            if not members:
                continue
            sub = ev[ev["ticker"].isin(members)]
            rec = sub[(sub["d"] > rec_lo) & (sub["d"] <= t0)]
            pri = sub[(sub["d"] > pri_lo) & (sub["d"] <= rec_lo)]
            if rec.empty and pri.empty:
                continue
            covered = sorted(rec["ticker"].unique())
            rows.append({"basket_id": bid, "recent_count": int(len(rec)), "prior_count": int(len(pri)),
                         "n_members": int(len(covered)), "covered": ",".join(covered)})
        return pd.DataFrame(rows).set_index("basket_id") if rows else pd.DataFrame()

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        mem = _membership()
        universe = _universe(mem)
        if not universe:
            raise ValueError("edgar_8k: no basket members to scan")
        cikmap = _cik_map(universe)
        if not cikmap:
            raise ValueError("edgar_8k: could not map any ticker -> CIK (company_tickers.json unavailable)")

        events, errors = [], 0
        for ticker, cik in cikmap.items():
            try:
                events.extend(self._pull_ticker(ticker, cik))
                time.sleep(PACE_S)
            except Exception as e:  # noqa: BLE001
                errors += 1
                if is_connection_error(e):
                    raise  # host down -> fail fast, don't grind 345x
                log.debug("edgar_8k %s (CIK %s) failed: %s", ticker, cik, e)
                continue

        if not events:
            raise ValueError(f"edgar_8k: no material 8-K rows returned (errors={errors})")
        df = pd.DataFrame(events)
        merged = self._merge_events(df)
        velocity = self._velocity(merged, mem)
        if not velocity.empty:
            velocity.to_parquet(self._velocity_path())
        log.info("edgar_8k: %d/%d tickers mapped, +%d events scanned, %d total, %d baskets, %d errors",
                 len(cikmap), len(universe), len(df), len(merged), len(velocity), errors)
        ingest = pd.DataFrame(
            {"new_scanned": [len(df)], "total_rows": [len(merged)], "baskets": [len(velocity)]},
            index=[pd.Timestamp(datetime.now(timezone.utc).date())],
        )
        return {"edgar_8k__ingest": ingest}


# ---------------------------------------------------------------------------
# W1c — contract-dollar magnitude extraction for Item 1.01 / 2.03 filings
# ---------------------------------------------------------------------------
# EDGAR Archives primary-doc URL: https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}
# Fetching is bounded to filings <= 45 days old on the incremental path (see enrich_contract_amounts).

_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
_ENRICH_WINDOW_DAYS = 45   # only fetch primary doc for recent filings on incremental runs

# GR3b — enrichment schema revision.  Stamped on every row this module writes, and the
# BACKFILL path (incremental=False) re-attempts any row whose stamp is missing or older
# than this.  That is what makes a previously-failed row retryable WITHOUT overloading
# extraction_ok, whose False is a real coverage fact the graded ledger reads
# (engine/eightk_magnitude.py: n_extraction_ok / extraction_ok_pct / the amount gate).
# Bump this when the extraction rules change enough that old rows deserve another pass.
_ENRICH_REV = 2

# GR3b — exhibit fetch bounds.  Material-agreement 8-Ks carry the contract itself as an
# EX-10 (or EX-2 for a separation/merger), and the parties + dollars live there rather
# than in the four-paragraph primary doc.  Bounded hard: a credit agreement can run to
# several MB and there is no budget to read all of one, let alone all of three.
_EXHIBIT_CAP = 3               # exhibits fetched per filing
_EXHIBIT_MAX_BYTES = 1_000_000  # per exhibit; read is truncated at the cap, never skipped
_DOC_CACHE_DIR = "_8k_doc_cache"  # data/edgar/_8k_doc_cache/<cik>/<acc>/<file>.txt

# Exhibit TYPE codes worth reading.  Matched EXACTLY, not by prefix: every filing also
# carries the inline-XBRL taxonomy as EX-101.SCH / EX-101.LAB / EX-101.PRE / EX-101.DEF,
# and a `startswith("EX-10")` test burns all three exhibit slots on taxonomy stubs that
# strip to ~110 characters of link:presentationLink boilerplate (measured on the live
# filings 2026-08-08).  EX-2.x is read only for merger/separation filings (item 2.01).
_EX_CONTRACT_RE = re.compile(r"^EX-10(\.\d+)?$", re.IGNORECASE)
_EX_MERGER_RE = re.compile(r"^EX-2(\.\d+)?$", re.IGNORECASE)
_MERGER_ITEM = "2.01"

# HTML -> text.  The primary doc and every exhibit are HTML; the amount and name regexes
# are prose regexes and cannot see across a tag boundary ('$' in one <td>, '1,234' in the
# next).  Same idiom as collectors/issuer_evidence._clean_cell: drop markup, THEN unescape
# character references, then normalise invisible layout artifacts and whitespace.
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_INVISIBLE_RE = re.compile("[\\xad\\u200b-\\u200f\\u2028\\u2029\\u2060\\ufeff]")
_WS_RE = re.compile(r"\s+")

# Dollar-amount regex: captures 'approximately $1.2 billion', '$450 million', '$3,200,000',
# '$12.5M', numbers with decimal/comma thousands separators.
# EVERY multiplier alternative is word-bounded (\b): without it '$5 mmBtu' reads as $5M,
# '$10 millionaire' as $10M, '$4 bnb tokens' as $4B — and since the parser keeps the
# LARGEST match, one spurious suffix hit would corrupt amount_usd → contract_dollar_z →
# a false pre_drift flag on the graded ledger. '$X mmBtu' is common in energy 1.01 filings.
_DOLLAR_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(billion\b|million\b|bn\b|mm\b|m\b)?",
    re.IGNORECASE,
)
# ── Counterparty extraction (GR3b) ─────────────────────────────────────────
# Two stages, both deterministic and both regex/set-driven — no LLM, no fuzzy scoring.
#
#   STAGE 1 candidates: find a parties lead-in ('by and among', 'between', 'with', …),
#     then read the clause that follows and split it into party fragments on commas and
#     'and'.  A single clause routinely names four parties ("by and among X, the lenders
#     party thereto, and Y, as Agent"), so the old .search()-returns-first-match shape
#     could only ever see the FIRST one — which on a credit agreement is the registrant.
#   STAGE 2 validation: _counterparty_is_valid() rejects role words, defined terms,
#     all-generic phrases, prose fragments, and the registrant's own name.
_CP_LEADIN_RE = re.compile(
    r"\b(?:by\s+and\s+among|by\s+and\s+between|by,?\s+between|among|between|with|from)\s+",
    re.IGNORECASE,
)
_CP_CLAUSE_CHARS = 320   # chars of clause read after a lead-in (parties sit at the front)
_CP_FRAGMENT_RE = re.compile(r"\s*(?:,|;|\band\b)\s*", re.IGNORECASE)
_CP_LEAD_ARTICLE_RE = re.compile(r"^(?:the|a|an|each\s+of\s+the|certain\s+of\s+the)\s+", re.IGNORECASE)
_CP_PAREN_RE = re.compile(r"\s*\([^)]*\)?\s*$")

# A legal-form suffix is the strongest single signal that a fragment is an entity name;
# it also licenses a ONE-token name ("Alphabet Inc." survives, bare "Alphabet" does not).
_CP_LEGAL_SUFFIXES = frozenset({
    "llc", "l.l.c.", "inc", "inc.", "incorporated", "corp", "corp.", "corporation",
    "company", "co", "co.", "ltd", "ltd.", "limited", "lp", "l.p.", "llp", "l.l.p.",
    "plc", "ag", "sa", "s.a.", "nv", "n.v.", "bv", "b.v.", "gmbh", "ab", "as", "oyj",
    "n.a.", "na", "association", "bank", "trust", "holdings", "partners", "group",
    "sàrl", "s.à", "kgaa", "spa", "s.p.a.", "pte", "pty", "kk", "k.k.",
})

# Words that are pure role / boilerplate / document furniture.  A fragment whose tokens
# are ALL drawn from this set is not a name — that rule generalises where an exact-phrase
# blocklist does not ("a Material Definitive", "the Financial Institutions", "Certain
# Lenders" all die on it, and none of them needed their own entry).
_CP_GENERIC_WORDS = frozenset({
    "a", "an", "the", "such", "certain", "various", "other", "others", "new", "additional",
    "material", "definitive", "agreement", "agreements", "amendment", "amended", "restated",
    "credit", "loan", "note", "notes", "indenture", "facility", "security", "guaranty",
    "company", "companies", "registrant", "issuer", "parent", "subsidiary", "subsidiaries",
    "borrower", "borrowers", "lender", "lenders", "guarantor", "guarantors", "holder",
    "holders", "party", "parties", "purchaser", "purchasers", "seller", "sellers",
    "buyer", "buyers", "obligor", "obligors", "counterparty", "counterparties",
    "agent", "agents", "administrative", "collateral", "syndication", "documentation",
    "trustee", "trustees", "custodian", "depositary", "escrow", "underwriter",
    "underwriters", "initial", "several", "representative", "representatives",
    "financial", "institutions", "institution", "banks", "investors", "investor",
    "exhibit", "exhibits", "item", "section", "annex", "schedule", "article", "page",
    "date", "dated", "thereto", "hereto", "hereof", "thereof", "herein", "therein",
    "corporation", "corp", "inc", "llc", "ltd", "limited", "plc", "lp", "llp", "co",
    "group", "holdings", "partners", "trust", "bank", "association", "national",
    # Document titles and role nouns that survive the clause split as a bare fragment —
    # "Agreement and Plan of Merger" leaves "Plan of Merger", a signature block leaves
    # "General Partner", a securities 8-K leaves "Private Placement".  All measured on
    # the live filings 2026-08-08, none of them an entity.
    "plan", "plans", "merger", "reorganization", "acquisition", "purchase", "sale",
    "separation", "distribution", "transition", "services", "service", "underwriting",
    "placement", "private", "public", "offering", "commitment", "letter", "form",
    "general", "partner", "managing", "member", "members", "manager", "managers",
    "revolving", "term", "senior", "subordinated", "secured", "unsecured", "receivables",
    "exchange", "registration", "rights", "employment", "incentive", "equity", "capital",
    "stock", "share", "shares", "common", "preferred", "indemnification", "license",
    "first", "second", "third", "fourth", "fifth", "securities", "commission",
    "washington", "united", "states", "delaware", "nevada", "corporate", "board",
    "class", "series", "title", "name", "description", "number", "amount", "value",
})

# Exact-phrase rejects for boilerplate that survives the all-generic test only because it
# carries one distinctive token ('York', 'Nasdaq').  Listing venues and the Commission
# appear on the cover page of every 8-K ever filed and are never a transaction party.
_CP_PHRASE_BLOCKLIST = frozenset({
    "new york stock exchange", "nyse american", "nasdaq stock market",
    "nasdaq global select market", "nasdaq global market", "nasdaq capital market",
    "securities and exchange commission", "cboe bqx exchange", "cboe bzx exchange",
    "us securities", "secretary of state",
    "secretary of state of the state of delaware", "internal revenue service",
})
# Entries above are matched against a punctuation-free normal form, so 'U.S. Securities'
# and 'US Securities' are one key rather than two spellings to remember.
_CP_PUNCT_RE = re.compile(r"[^a-z0-9 ]")

# A candidate whose LAST word is document furniture is a document title that survived the
# clause split, not a party: 'Seventh Supplemental Indenture', 'Floating Rate Notes',
# 'Houston Electric Amendment', "ICANN's Base Registry Agreement".  Measured at ~7% of
# extracted names on the trailing-24m backfill before this rule (2026-08-08).  Keyed on
# the TAIL specifically, so 'Agreement Corp' or 'Indenture Trustee Bank Ltd' would still
# be considered on their own merits.
_CP_TAIL_FURNITURE = frozenset({
    "agreement", "agreements", "amendment", "amendments", "indenture", "indentures",
    "supplement", "supplemental", "note", "notes", "certificate", "certificates",
    "letter", "plan", "schedule", "annex", "exhibit", "waiver", "consent",
    "guaranty", "guarantee", "deed", "lease", "loan", "facility", "commitment",
})

# Lower-case tokens allowed INSIDE a name without breaking its "looks like a proper
# name" test — real entity names carry them ("Bank of America", "Ares Capital de Mexico").
_CP_NAME_CONNECTORS = frozenset({"of", "and", "the", "de", "del", "la", "le", "van", "von", "für", "und", "&"})

_CP_TOKEN_STRIP = ".,;:'\"()"


def _parse_dollar_amounts(text: str) -> tuple[float | None, bool]:
    """Extract the largest contract USD amount from filing text.

    Returns (amount_usd, extraction_ok).  extraction_ok=True iff at least one
    parseable $ figure was found; amount_usd is the largest such figure in USD.
    Many 8-K/Item-1.01 filings bury the $ in exhibits or omit it entirely — those
    return (None, False) and degrade to count-only.
    """
    best: float | None = None
    for m in _DOLLAR_RE.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        suffix = (m.group(2) or "").lower()
        if suffix in ("billion", "bn"):
            val *= 1_000_000_000
        elif suffix in ("million", "mm", "m"):
            val *= 1_000_000
        # skip noise values under $10k (page numbers, percentages formatted as $0.XX)
        if val < 10_000:
            continue
        if best is None or val > best:
            best = val
    return best, best is not None


def _norm_name_tokens(name: str) -> list[str]:
    """Lower-cased significant tokens of a name, legal-form suffixes dropped.

    Used for self-name comparison only: 'REALTY INCOME CORPORATION' and 'Realty Income
    Corp' must both reduce to ['realty', 'income'] so a filing that names its own
    registrant as the first party is recognised as such.
    """
    out: list[str] = []
    for tok in re.split(r"[\s,]+", str(name or "")):
        t = tok.strip(_CP_TOKEN_STRIP).lower()
        # Connectors go too: without that, 'Bank of America' and 'Bank of New York
        # Mellon' both reduce to a leading 'of' and read as the same entity.
        if not t or t in _CP_LEGAL_SUFFIXES or t in _CP_NAME_CONNECTORS:
            continue
        out.append(t)
    return out


def _is_self_name(candidate: str, registrant: str | None) -> bool:
    """True when `candidate` names the filer itself rather than a counterparty.

    A credit agreement opens 'by and among <the registrant>, the lenders party thereto,
    and <the bank>' — the first party is almost always the filer or one of its financing
    subsidiaries, and a column of registrant self-names carries no information for any
    downstream counterparty consumer.  Prefix match in BOTH directions so
    'Public Storage' catches 'Public Storage Operating Company' and vice versa.
    """
    if not registrant:
        return False
    c, r = _norm_name_tokens(candidate), _norm_name_tokens(registrant)
    if not c or not r:
        return False
    n = min(len(c), len(r))
    if c[:n] == r[:n]:
        return True

    # Spacing variants: 'Go Daddy Operating Company' is the filer 'GoDaddy Inc.'.
    # Compared as joined TOKEN PREFIXES rather than raw string prefixes, so the match
    # has to land on a token boundary — 'America' must not read as a self-name for
    # 'American Airlines' just because one spells the other's first eight letters.
    def _prefixes(toks: list[str]) -> set[str]:
        acc, out = "", set()
        for t in toks:
            acc += t
            out.add(acc)
        return out

    if "".join(r) in _prefixes(c) or "".join(c) in _prefixes(r):
        return True
    # A shared DISTINCTIVE first token is the same tell one level looser: 'Cognizant
    # Worldwide Limited' is a financing subsidiary of 'Cognizant Technology Solutions
    # Corp', not its counterparty.  Restricted to a non-generic head word so that
    # 'Bank of America' is not read as a self-name for 'Bank of New York Mellon'.
    return c[0] == r[0] and c[0] not in _CP_GENERIC_WORDS and c[0] not in _CP_NAME_CONNECTORS


def _counterparty_is_valid(name: str, registrant: str | None = None) -> bool:
    """Deterministic quality gate for a candidate counterparty name.

    Rejects, in order: length outliers · fragments with no proper-name token · prose
    (any lower-case token that is not a name connector) · all-generic phrases
    ('Material Definitive', 'the Financial Institutions') · bare one-token names with no
    legal-form suffix ('Alphabet' alone) · the registrant's own name.
    """
    if not name or not (3 <= len(name) <= 80):
        return False
    raw_tokens = [t for t in re.split(r"[\s,]+", name) if t.strip(_CP_TOKEN_STRIP)]
    if not raw_tokens:
        return False

    lowered = [t.strip(_CP_TOKEN_STRIP).lower() for t in raw_tokens]
    if _WS_RE.sub(" ", _CP_PUNCT_RE.sub("", " ".join(lowered))).strip() in _CP_PHRASE_BLOCKLIST:
        return False
    if lowered[-1] in _CP_TAIL_FURNITURE:
        return False
    has_suffix = any(t in _CP_LEGAL_SUFFIXES for t in lowered)

    # Prose test: a real name is Title Case or ALL CAPS throughout, apart from the small
    # set of connectors.  'lenders party thereto' and 'financial institutions party
    # hereto' die here without needing to be enumerated.
    name_like = 0
    for raw, low in zip(raw_tokens, lowered):
        head = raw.strip(_CP_TOKEN_STRIP)
        if not head:
            continue
        if head[0].isupper():
            name_like += 1
        elif low not in _CP_NAME_CONNECTORS:
            return False

    if name_like == 0:
        return False
    if name_like < 2 and not has_suffix:
        return False
    if all(t in _CP_GENERIC_WORDS or t in _CP_NAME_CONNECTORS for t in lowered):
        return False
    return not _is_self_name(name, registrant)


def _counterparty_candidates(text: str) -> list[str]:
    """Ordered party-name candidates from every parties clause in `text`."""
    out: list[str] = []
    for m in _CP_LEADIN_RE.finditer(text):
        end = m.end() + _CP_CLAUSE_CHARS
        clause = text[m.end():end]
        # A sentence end closes the parties clause; anything after it is unrelated prose.
        parts = re.split(r"(?<=[a-z0-9\)])\.\s+[A-Z]", clause)
        clause = parts[0]
        frags = _CP_FRAGMENT_RE.split(clause)
        # The window can cut mid-word ('...Securities and Exchange Commis|'), and a
        # half-word reads as a plausible proper noun to every rule below it.  When the
        # clause really was cut at the window edge, its trailing fragment is discarded.
        if len(parts) == 1 and end < len(text) and frags:
            frags = frags[:-1]
        for frag in frags:
            frag = _CP_PAREN_RE.sub("", frag).strip().strip(_CP_TOKEN_STRIP + " ")
            frag = _CP_LEAD_ARTICLE_RE.sub("", frag).strip()
            if not frag:
                continue
            # 'as Agent' / 'as Initial Borrower' annotate the PREVIOUS party; they are
            # never a party themselves.
            if re.match(r"^as\b", frag, re.IGNORECASE):
                continue
            out.append(frag)
    return out


def _parse_counterparty(text: str, registrant: str | None = None) -> str | None:
    """Best-effort counterparty from filing text. None when unextractable.

    Walks the candidates in document order and returns the FIRST that passes
    `_counterparty_is_valid`; `registrant` (the filer's own legal name, when known)
    suppresses self-names so the first party of a credit agreement does not win.
    Best-effort by construction: no candidate passing the gate is a legitimate null,
    not an error.

    Returned names are normalised at the edges — trailing commas and periods are dropped,
    so 'Fabrinet Technologies Inc.' stores as 'Fabrinet Technologies Inc'.  A trailing
    period is ambiguous between an abbreviation and the end of the sentence the name was
    read from, and a consistently-stripped form is the better join key for either.
    """
    for cand in _counterparty_candidates(text):
        if _counterparty_is_valid(cand, registrant):
            return cand
    return None


def _registrant_name(cik: int | None) -> str | None:
    """Filer legal name for a CIK from the already-cached SEC company_tickers.json.

    Keyless and local — the file is fetched once by `_company_tickers()` and shared with
    collectors/edgar.py.  Returns None when the map is unavailable, which simply disables
    the self-name rule rather than failing the extraction.
    """
    if cik is None:
        return None
    cache = _registrant_name._cache  # type: ignore[attr-defined]
    if cache is None:
        data = _company_tickers() or {}
        cache = {}
        for row in data.values():
            try:
                cache[int(row["cik_str"])] = str(row.get("title") or "")
            except Exception:  # noqa: BLE001
                continue
        _registrant_name._cache = cache  # type: ignore[attr-defined]
    return cache.get(int(cik)) or None


_registrant_name._cache = None  # type: ignore[attr-defined]


def _strip_doc_text(raw: str) -> str:
    """HTML/SGML filing body -> flat prose."""
    t = _SCRIPT_STYLE_RE.sub(" ", raw or "")
    t = _TAG_RE.sub(" ", t)
    t = _html.unescape(t)
    t = _INVISIBLE_RE.sub("", t).replace("\xa0", " ")
    return _WS_RE.sub(" ", t).strip()


# Fair-access pacing is now enforced PER REQUEST rather than per filing.  Before GR3b a
# filing cost exactly two requests and the enrich loop slept once per filing; a filing
# now costs up to 1 manifest + 1 primary + _EXHIBIT_CAP exhibits, and a per-filing sleep
# would let a multi-exhibit filing burst well past the <=10 req/s ceiling.
_LAST_ARCHIVES_REQ = [0.0]


def _archives_get(url: str, pace_s: float = PACE_S, timeout: int = 30, stream: bool = False):
    """GET an EDGAR Archives URL, holding the module's minimum inter-request interval."""
    wait = pace_s - (time.monotonic() - _LAST_ARCHIVES_REQ[0])
    if wait > 0:
        time.sleep(wait)
    _LAST_ARCHIVES_REQ[0] = time.monotonic()
    return requests.get(url, headers={"User-Agent": _SEC_UA}, timeout=timeout, stream=stream)


def _doc_cache_path(cik: int, acc_nodash: str, filename: str) -> Path | None:
    """Local cache path for one fetched filing document, or None if the name is unsafe.

    The filename comes off a remote index, so it is treated as untrusted: anything with a
    path separator or a parent reference is refused rather than sanitised.
    """
    safe = str(filename or "").strip()
    if not safe or "/" in safe or "\\" in safe or ".." in safe:
        return None
    return config.data_dir() / "edgar" / _DOC_CACHE_DIR / str(int(cik)) / acc_nodash / f"{safe}.txt"


def _fetch_doc_text(cik: int, acc_nodash: str, filename: str, pace_s: float = PACE_S,
                    strip: bool = True, max_bytes: int | None = None,
                    stats: dict | None = None) -> str | None:
    """Fetch one filing document as text, through the on-disk cache.

    The cache holds the STRIPPED text (a 2.7MB credit agreement caches as ~1MB of prose),
    which is what makes the backfill interrupt-safe: a resumed run re-reads from disk and
    re-issues no request for anything already seen.  Only successes are cached — a 404 or
    a timeout stays retryable.

    `max_bytes` bounds the transfer itself (streamed, not downloaded-then-measured).  A
    document longer than the bound is TRUNCATED rather than skipped: the parties clause
    and the headline dollar figure both sit in the opening page of a contract, so the
    first megabyte carries the signal.  Truncations are counted, never silent.
    """
    path = _doc_cache_path(cik, acc_nodash, filename)
    if path is not None and path.exists():
        try:
            if stats is not None:
                stats["cache_hits"] = stats.get("cache_hits", 0) + 1
            return path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass   # unreadable cache entry -> refetch

    url = f"{_ARCHIVES}/{int(cik)}/{acc_nodash}/{filename}"
    try:
        r = _archives_get(url, pace_s=pace_s, stream=max_bytes is not None)
        if r.status_code != 200:
            if stats is not None:
                stats["fetch_http_err"] = stats.get("fetch_http_err", 0) + 1
            return None
        if max_bytes is None:
            raw = r.text
        else:
            buf = bytearray()
            for chunk in r.iter_content(chunk_size=65536):
                buf.extend(chunk)
                if len(buf) >= max_bytes:
                    if stats is not None:
                        stats["exhibit_truncated"] = stats.get("exhibit_truncated", 0) + 1
                    break
            r.close()
            raw = bytes(buf[:max_bytes]).decode(r.encoding or "utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        if stats is not None:
            stats["fetch_exc"] = stats.get("fetch_exc", 0) + 1
        return None

    text = _strip_doc_text(raw) if strip else raw
    if path is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass   # cache is an optimisation, never a correctness requirement
    if stats is not None:
        stats["fetch_ok"] = stats.get("fetch_ok", 0) + 1
    return text


def _parse_sgml_manifest(text: str) -> list[tuple[str, str]]:
    """[(TYPE, FILENAME)] from a filing's SGML `-index-headers.html` page.

    This is the authoritative document map for a filing.  index.json is NOT: its `type`
    field is the directory-listing ICON name — every row reads 'text.gif' — so the
    pre-GR3b primary-doc selector ("type in 8-K/8-K/A") never matched anything, fell
    through to "first .htm in the listing", and picked `<acc>-index-headers.html` itself:
    the EDGAR submission header, which contains no agreement text at all.  That is why
    all 207 enriched filings recorded a null amount AND a null counterparty.
    """
    out: list[tuple[str, str]] = []
    for block in _html.unescape(text or "").split("<DOCUMENT>")[1:]:
        t = re.search(r"<TYPE>([^<\r\n]+)", block)
        f = re.search(r"<FILENAME>([^<\r\n]+)", block)
        if t and f:
            out.append((t.group(1).strip().upper(), f.group(1).strip()))
    return out


def _fetch_filing_manifest(cik: int, accession: str, pace_s: float = PACE_S,
                           stats: dict | None = None) -> list[tuple[str, str]]:
    """Document map for one filing (cached, one request)."""
    acc_nodash = accession.replace("-", "")
    raw = _fetch_doc_text(int(cik), acc_nodash, f"{accession}-index-headers.html",
                          pace_s=pace_s, strip=False, stats=stats)
    return _parse_sgml_manifest(raw) if raw else []


def _select_exhibits(manifest: list[tuple[str, str]], items: str) -> tuple[list[tuple[str, str]], int]:
    """((TYPE, FILENAME) to read, n_eligible_before_cap) for a material-agreement filing.

    EX-10.x always (the material contract); EX-2.x only when the filing also reports item
    2.01, which is what makes it a merger/separation.  Manifest order is the filer's own
    exhibit sequence, so the cap keeps the first `_EXHIBIT_CAP` — 10.1 before 10.7.
    """
    merger = _MERGER_ITEM in {c.strip() for c in str(items or "").split(",")}
    eligible = [
        (t, f) for t, f in manifest
        if _EX_CONTRACT_RE.match(t) or (merger and _EX_MERGER_RE.match(t))
    ]
    return eligible[:_EXHIBIT_CAP], len(eligible)


def _primary_doc_name(manifest: list[tuple[str, str]]) -> str | None:
    """Filename of the 8-K body itself within a filing's document map."""
    name = next((f for t, f in manifest if t in ("8-K", "8-K/A")), None)
    if name is None:
        # Filer used a non-standard TYPE: fall back to the first non-XBRL .htm document.
        name = next(
            (f for t, f in manifest
             if f.lower().endswith((".htm", ".html")) and not t.upper().startswith("EX-101")),
            None,
        )
    return name


def _fetch_primary_doc_text(cik: int, accession: str, pace_s: float = PACE_S,
                            stats: dict | None = None) -> str | None:
    """Primary 8-K document as flat text.

    Returns STRIPPED prose since GR3b, not raw HTML: the amount and name regexes are
    prose regexes and cannot match across a tag boundary ('$' in one <td>, '1,234' in
    the next).
    """
    manifest = _fetch_filing_manifest(int(cik), str(accession), pace_s=pace_s, stats=stats)
    if not manifest:
        return None
    name = _primary_doc_name(manifest)
    if not name:
        return None
    return _fetch_doc_text(int(cik), str(accession).replace("-", ""), name,
                           pace_s=pace_s, stats=stats)


def _extract_filing(cik: int, accession: str, items: str, pace_s: float = PACE_S,
                    stats: dict | None = None) -> dict | None:
    """Run both extraction legs over one filing's primary doc + exhibits.

    PRECEDENCE (both legs, stated once and applied identically): the primary document
    wins; exhibits fill gaps only.  The primary 8-K is the registrant's own description
    of the transaction, so a name or a headline figure found there is the one the filer
    considered material.  Exhibits are the raw contract — read only when the primary is
    silent, because a 400-page credit agreement mentions dozens of incidental dollar
    figures and taking the maximum across all of them would bias `amount_usd` upward
    against the pre-GR3b measurement basis.

    The two legs are INDEPENDENT: a filing with no parseable dollar figure still yields a
    counterparty, which is exactly the coupling GR3 proved was pinning the column at null.

    Exhibits are fetched LAZILY — only once the primary document has left a leg unfilled,
    and only until both legs are filled.  That keeps the nightly increment at roughly two
    requests per filing (manifest + primary) in the common case where the primary answers
    both, instead of paying for up to three multi-megabyte contracts every time.

    Returns None when the filing could not be read (retry-eligible), else a dict of the
    enrichment columns.
    """
    acc_nodash = str(accession).replace("-", "")
    manifest = _fetch_filing_manifest(int(cik), str(accession), pace_s=pace_s, stats=stats)
    if not manifest:
        return None

    registrant = _registrant_name(int(cik))
    amount: float | None = None
    amount_src: str | None = None
    counterparty: str | None = None
    counterparty_src: str | None = None
    read_any = False

    def _consume(text: str, src: str) -> None:
        nonlocal amount, amount_src, counterparty, counterparty_src
        if amount is None:
            got, ok = _parse_dollar_amounts(text)
            if ok:
                amount, amount_src = got, src
        if counterparty is None:
            got_cp = _parse_counterparty(text, registrant)
            if got_cp:
                counterparty, counterparty_src = got_cp, src

    primary_name = _primary_doc_name(manifest)
    if primary_name:
        primary = _fetch_doc_text(int(cik), acc_nodash, primary_name, pace_s=pace_s, stats=stats)
        if primary:
            read_any = True
            _consume(primary, "primary")

    if amount is None or counterparty is None:
        picked, n_eligible = _select_exhibits(manifest, items)
        if stats is not None and picked:
            stats["filings_consulting_exhibits"] = stats.get("filings_consulting_exhibits", 0) + 1
            stats["exhibits_eligible"] = stats.get("exhibits_eligible", 0) + n_eligible
            if n_eligible > _EXHIBIT_CAP:
                stats["exhibit_cap_binds"] = stats.get("exhibit_cap_binds", 0) + 1
                stats["exhibits_skipped"] = stats.get("exhibits_skipped", 0) + (n_eligible - _EXHIBIT_CAP)
        for _ex_type, ex_name in picked:
            txt = _fetch_doc_text(int(cik), acc_nodash, ex_name, pace_s=pace_s,
                                  max_bytes=_EXHIBIT_MAX_BYTES, stats=stats)
            if stats is not None:
                stats["exhibits_read"] = stats.get("exhibits_read", 0) + 1
            if not txt:
                continue
            read_any = True
            _consume(txt, "exhibit")
            if amount is not None and counterparty is not None:
                break

    if not read_any:
        return None

    return {
        "amount_usd": amount,
        # extraction_ok keeps its pre-GR3b meaning — "a dollar amount parsed" — because
        # engine/eightk_magnitude.py reads it as exactly that (n_extraction_ok,
        # extraction_ok_pct, and the gate on the amount_usd read).  Name-extraction
        # success is reported separately in counterparty_ok rather than overloaded here.
        "extraction_ok": amount is not None,
        "amount_src": amount_src,
        "counterparty": counterparty,
        "counterparty_ok": counterparty is not None,
        "counterparty_src": counterparty_src,
        "enrich_rev": _ENRICH_REV,
    }


def enrich_contract_amounts(
    events: pd.DataFrame,
    incremental: bool = True,
    pace_s: float = PACE_S,
    *,
    window_days: int | None = None,
    limit: int | None = None,
    skip_accessions: set[str] | None = None,
    stats: dict | None = None,
) -> pd.DataFrame:
    """Add the contract-extraction columns to material_8k_events.

    For rows whose items contain '1.01' or '2.03', read the primary filing document and
    (GR3b) its material-contract exhibits, then regex-extract the contract dollar amount
    and the counterparty name INDEPENDENTLY of one another.

    Args:
        events:      The full material_8k_events DataFrame (must have cik/accession/
                     filing_date/items columns).
        incremental: NIGHTLY path when True — only filings <= _ENRICH_WINDOW_DAYS old that
                     have never been read (extraction_ok absent or NaN).  Deliberately
                     unchanged by GR3b so the nightly increment stays at the handful of
                     newly-filed 1.01/2.03 reports per run.
                     BACKFILL path when False — every 1.01/2.03 row inside `window_days`
                     whose `enrich_rev` stamp is missing or older than `_ENRICH_REV`.
                     That re-attempts rows a previous revision already marked
                     extraction_ok=False, which a plain isna() mask can never revisit.
        pace_s:      Minimum seconds between EDGAR Archives requests (per REQUEST).
        window_days: Backfill horizon; None means all history.  Ignored when incremental.
        limit:       Stop after this many rows (chunked / bounded runs).
        skip_accessions: Accessions already attempted by the caller this run.  A chunked
                     backfill passes the running set so a filing that could not be READ
                     (and therefore stays deliberately unstamped, to keep it retryable on
                     the next run) does not re-fill the head of every later chunk.
        stats:       Optional dict, updated in place with fetch + yield counters.

    Returns:
        Updated DataFrame.  Rows not in scope are returned unchanged.
    """
    df = events.copy()
    for col in _ENRICH_COLS:
        if col not in df.columns:
            df[col] = None
        elif df[col].dtype != object:
            # pandas 3.x refuses to write a str/bool into a float64 cell — and an
            # all-null enrichment column round-trips out of parquet as float64, so the
            # first successful extraction would raise TypeError mid-loop and take the
            # whole lane down.  Coerce to the object dtype the committed schema uses.
            df[col] = df[col].astype(object)

    mask_items = df["items"].str.contains(r"1\.01|2\.03", na=False)
    dates = pd.to_datetime(df["filing_date"], errors="coerce", utc=True)

    if incremental:
        cutoff = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=_ENRICH_WINDOW_DAYS)
        target_mask = mask_items & (dates >= cutoff) & df["extraction_ok"].isna()
    else:
        rev = pd.to_numeric(df["enrich_rev"], errors="coerce")
        target_mask = mask_items & (rev.isna() | (rev < _ENRICH_REV))
        if window_days is not None:
            cutoff = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=window_days)
            target_mask &= dates >= cutoff

    if skip_accessions:
        target_mask &= ~df["accession"].astype("string").isin(skip_accessions)

    targets = df[target_mask]
    if limit is not None:
        targets = targets.head(limit)
    log.info("edgar_8k enrich: %d rows to process (incremental=%s, window_days=%s, limit=%s)",
             len(targets), incremental, window_days, limit)
    if stats is not None:
        stats["targeted"] = stats.get("targeted", 0) + len(targets)
        # Attempted set, for a chunked caller: see `skip_accessions` above.
        stats.setdefault("attempted_accessions", []).extend(
            targets["accession"].astype("string").dropna().tolist()
        )

    for idx_pos, row in targets.iterrows():
        cik = row.get("cik")
        acc = row.get("accession")
        # pd.isna first: a null in an int64 cik column reads back as NaN, and NaN is
        # TRUTHY, so a bare `not cik` would send it to int(nan) and route a permanently
        # broken row down the retry-forever path instead of stamping it.
        if pd.isna(cik) or pd.isna(acc) or not cik or not acc:
            # Permanently unenrichable — no ids to fetch with.  Stamped so the backfill
            # does not keep rediscovering it.
            df.at[idx_pos, "extraction_ok"] = False
            df.at[idx_pos, "counterparty_ok"] = False
            df.at[idx_pos, "enrich_rev"] = _ENRICH_REV
            if stats is not None:
                stats["no_ids"] = stats.get("no_ids", 0) + 1
            continue
        try:
            got = _extract_filing(int(cik), str(acc), str(row.get("items") or ""),
                                  pace_s=pace_s, stats=stats)
        except Exception as e:  # noqa: BLE001
            # TRANSIENT fetch failure (network/503/timeout): leave the row unstamped so
            # both masks retry it next run.  False is reserved for filings we actually
            # READ and found nothing in (a real coverage fact the ledger grades on; a
            # sticky False here would silently shrink coverage forever).
            log.debug("edgar_8k enrich fetch failed (retry-eligible) %s %s: %s",
                      row.get("ticker"), acc, e)
            if stats is not None:
                stats["unread"] = stats.get("unread", 0) + 1
            continue

        if got is None:
            if stats is not None:
                stats["unread"] = stats.get("unread", 0) + 1
            continue   # nothing readable — retry-eligible, not a coverage fact

        for col, val in got.items():
            df.at[idx_pos, col] = val
        if stats is not None:
            stats["read"] = stats.get("read", 0) + 1
            if got["extraction_ok"]:
                stats[f"amount_{got['amount_src']}"] = stats.get(f"amount_{got['amount_src']}", 0) + 1
            if got["counterparty_ok"]:
                stats[f"name_{got['counterparty_src']}"] = stats.get(f"name_{got['counterparty_src']}", 0) + 1

    if stats is not None and stats.get("exhibit_cap_binds"):
        # House law: no silent truncation.  The cap is a real information loss and says so
        # in the Actions summary.  Bare print at column 0 — a logger would prefix the line
        # and GitHub would drop the annotation.
        print(f"::warning title=edgar-8k-exhibit-cap::exhibit cap ({_EXHIBIT_CAP}/filing) bound on "
              f"{stats['exhibit_cap_binds']} filings, {stats.get('exhibits_skipped', 0)} exhibits unread; "
              f"{stats.get('exhibit_truncated', 0)} exhibits truncated at {_EXHIBIT_MAX_BYTES} bytes",
              flush=True)
    return df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    Edgar8KAdapter().fetch()
