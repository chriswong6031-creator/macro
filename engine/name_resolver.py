"""Company-name -> ticker resolver (shared) — unblocks the newswire + intl lanes.

Verification showed those lanes yielded ~0 because they required an exchange-tagged ticker
('(NASDAQ: XYZ)') in the headline, which Google-News-aggregated headlines don't carry. This
resolves a ticker from the company NAME instead, against an index built from the SEC
company-ticker map (US, authoritative; cached by the collector in CI) + digest_db (US + the
intl universe, with exchange-suffixed tickers).

Precision over recall by design (the desk is ticker-keyed): normalize the name, take the
leading company span of a headline, and resolve ONLY on an exact, UNIQUE normalized match,
optionally scoped to a market (us / uk / canada). Ambiguous or partial names -> None.
"""
from __future__ import annotations

import json
import re

from lib import config

# legal-form / filler tokens stripped before matching (order-independent; word-boundaried)
_SUFFIX = (
    r"inc|incorporated|corp|corporation|co|company|companies|ltd|limited|plc|llc|l\.?l\.?c|"
    r"lp|l\.?p|sa|s\.?a|ag|nv|n\.?v|spa|s\.?p\.?a|ab|asa|oyj|oy|as|bv|gmbh|kk|kabushiki|"
    r"holdings?|holding|group|grp|bancorp|bankshares|enterprises|industries|international|"
    r"intl|the|and|class\s+[a-c]|series\s+[a-c]|adr|ads|reit|trust|fund|nv|plc"
)
_SUFFIX_RE = re.compile(rf"\b(?:{_SUFFIX})\b", re.I)
# split a headline at the first action verb to isolate the leading company name
_VERB_RE = re.compile(
    r"\s+(?:announces?|announced|to\s|agrees?|agreed|enters?|entered|completes?|completed|"
    r"launches?|reports?|reported|provides?|files?|filed|receives?|received|appoints?|"
    r"names?|names\b|sets?|declares?|commences?|will\s|plans?|explores?|begins?|says?|is\s|"
    r"has\s|posts?|signs?|signed|raises?|prices?|priced|terminates?|terminated)\b",
    re.I)
_STOP = {"us", "new", "first", "the", "global", "national", "american", "general"}
_CACHE: dict | None = None


def normalize_name(name: object) -> str:
    """Canonicalize a company name for matching: drop punctuation + legal-form tokens, lower,
    collapse whitespace. 'Acme Corporation, Inc.' and 'ACME corp' -> 'acme'."""
    if not name:
        return ""
    s = str(name).lower()
    s = re.sub(r"[.,]", "", s)            # join abbreviations first: 's.a.'->'sa', 'inc.'->'inc'
    s = re.sub(r"[/&'’\-]", " ", s)       # other punctuation -> space
    s = _SUFFIX_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def lead_company(text: object) -> str:
    """The leading company-name span of a headline (everything before the first action verb /
    open paren). 'Acme Corp announces strategic review' -> 'Acme Corp'."""
    if not text:
        return ""
    t = str(text).split("(")[0]
    return _VERB_RE.split(t, 1)[0].strip(" ,—-:")


def _add(idx: dict, name: object, ticker: object) -> None:
    nn = normalize_name(name)
    tk = str(ticker).strip().upper() if ticker else ""
    if not nn or not tk or len(nn) < 4 or nn in _STOP:
        return
    idx.setdefault(nn, set()).add(tk)


def build_index() -> dict[str, set]:
    """{normalized_name: {tickers}} from the SEC map (US) + digest_db (US + intl). Tickers
    keep their exchange suffix for intl (ARX.TO); US are bare (AIRI). Built once, cached."""
    idx: dict[str, set] = {}
    try:
        p = config.data_dir() / "edgar" / "company_tickers.json"
        if p.exists():
            for e in json.loads(p.read_text()).values():
                _add(idx, e.get("title"), e.get("ticker"))
    except Exception:  # noqa: BLE001
        pass
    try:
        import pandas as pd
        d = config.data_dir() / "special_situations" / "digest_db.parquet"
        if d.exists():
            df = pd.read_parquet(d, columns=["company", "ticker"])
            for _, r in df.dropna(subset=["ticker"]).iterrows():
                _add(idx, r["company"], r["ticker"])
    except Exception:  # noqa: BLE001
        pass
    return idx


def name_index() -> dict[str, set]:
    global _CACHE
    if _CACHE is None:
        _CACHE = build_index()
    return _CACHE


def clear_cache() -> None:
    global _CACHE
    _CACHE = None


def _market_ok(ticker: str, market: str | None) -> bool:
    if not market:
        return True
    m = market.lower()
    if m == "us":
        return "." not in ticker
    if m == "uk":
        return ticker.endswith(".L")
    if m == "canada":
        return ticker.endswith((".TO", ".V"))
    return True


def resolve(text: object, market: str | None = None, index: dict | None = None) -> str | None:
    """Resolve a ticker from a headline / company name via an exact, UNIQUE normalized match
    (optionally scoped to a market). None on no match, ambiguity, or a too-generic name."""
    idx = index if index is not None else name_index()
    nn = normalize_name(lead_company(text))
    if len(nn) < 4 or nn in _STOP:
        return None
    # walk LEADING prefixes longest-first ('barclays firm offer' -> 'barclays'), so a headline
    # that leads with the company resolves even when trailing words precede the verb. Only
    # leading prefixes are tried, so a company buried mid-headline never false-matches.
    toks = nn.split()
    for n in range(len(toks), 0, -1):
        key = " ".join(toks[:n])
        if len(key) < 4 or key in _STOP:
            continue
        cands = idx.get(key)
        if not cands:
            continue
        scoped = [t for t in cands if _market_ok(t, market)]
        if len(scoped) == 1:
            return scoped[0]
        if len(scoped) > 1:
            return None          # ambiguous at this prefix — stop (don't fall through to a shorter, looser one)
    return None
