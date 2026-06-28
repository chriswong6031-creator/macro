"""International special-situations classifier (Phase 4 core — pure, display-only).

The recon showed the digest's moat is non-US coverage (55%). EDGAR can't see it; each
market routes to its own regulator (SEDAR+, RNS, TDnet/EDINET, HKEX, DART, ASX, BSE/NSE,
EU ad-hoc). This module is the DETERMINISTIC, offline-tested core that maps an
international filing-type / announcement headline to our mature taxonomy — distilled from
recon §D3. Any international feed wired later (now: gated UK/CA RSS collectors) routes
through `classify_intl`; nothing here fetches or scores. International situations are
cross-border by definition.
"""
from __future__ import annotations

import re

from engine.special_situations import (
    ACQ, ACT, CAP, DELIST, DIV, GP, ITEND, REV, RIGHTS, RESTR, SPIN, TERM, TO,
)

# regulator/exchange code -> ISO-2 country (for the cross-border / country tag)
REGULATOR_COUNTRY: dict[str, str] = {
    "sedar": "CA", "tsx": "CA", "rns": "GB", "lse": "GB", "tdnet": "JP", "edinet": "JP",
    "hkex": "HK", "dart": "KR", "kind": "KR", "asx": "AU", "bse": "IN", "nse": "IN",
    "sebi": "IN", "eu": "EU", "bafin": "DE", "amf": "FR", "cninfo": "CN", "csrc": "CN",
}

# exchange suffix -> ISO-2 (resolve a ticker like ARX.TO / BARC.L / 2551.HK)
SUFFIX_COUNTRY: dict[str, str] = {
    "TO": "CA", "V": "CA", "L": "GB", "T": "JP", "HK": "HK", "KS": "KR", "KQ": "KR",
    "AX": "AU", "NS": "IN", "BO": "IN", "DE": "DE", "PA": "FR", "SS": "CN", "SZ": "CN",
    "ST": "SE", "OL": "NO", "HE": "FI", "SI": "SG", "SW": "CH", "MI": "IT", "AS": "NL",
}


def country_for(regulator: str | None = None, ticker: str | None = None) -> str | None:
    """ISO-2 country from a regulator code and/or an exchange-suffixed ticker."""
    if regulator:
        c = REGULATOR_COUNTRY.get(str(regulator).strip().lower())
        if c:
            return c
    if ticker and "." in str(ticker):
        suf = str(ticker).rsplit(".", 1)[-1].upper()
        return SUFFIX_COUNTRY.get(suf)
    return None


# Ordered intl rules (category, stage, phrases); FIRST match wins. Going-private-specific
# language is checked before a generic offer so a scheme that cancels the listing is GP, not
# a plain tender. Phrases cover EN + the common CJK / EU regulator terms (recon §D3/§B1).
_INTL_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    (TERM, "terminated", (
        "offer has lapsed", "offer withdrawn", "rule 2.8", "no intention to make an offer",
        "scheme has lapsed", "lapsing of the offer", "termination of the offer", "deal terminated")),
    (GP, "live", (
        "cancellation of listing", "cancellation of admission to trading", "privatisation",
        "privatization", "take private", "taking private", "going private", "squeeze-out",
        "squeeze out", "compulsory acquisition", "delisting offer", "rule 3.5")),
    (TO, "live", (
        "rule 2.7", "firm intention to make an offer", "recommended cash offer",
        "recommended offer", "cash acquisition", "tender offer", "take-over bid", "takeover bid",
        "bidder's statement", "open offer", "mandatory offer", "voluntary general offer",
        "mandatory general offer", "offre publique", "übernahmeangebot", "公開買付", "公开买付",
        "공개매수")),
    (ACQ, "announced", (
        "plan of arrangement", "arrangement agreement", "merger agreement", "to be acquired",
        "agreed to acquire", "business combination agreement", "吸収合併", "합병")),
    (ACT, "initiated", (
        "early warning report", "substantial shareholder", "substantial holder",
        "major shareholding", "form 8.3", "tr-1", "form 604", "form 603", "form 605",
        "large shareholding", "大量保有", "주식대량보유", "requisition", "requisitions a",
        "board representation", "activist")),
    (REV, "initiated", (
        "rule 2.4", "possible offer", "strategic review", "strategic alternatives",
        "review of strategic", "formal sale process", "strategic options")),
    (SPIN, "announced", (
        "demerger", "spin-off", "spinoff", "spin off", "会社分割")),
    (DIV, "announced", (
        "disposal of", "agreement to sell", "sale of business", "divestment", "divestiture",
        "sale of its")),
    (CAP, "announced", (
        "special dividend", "share buyback", "share buy-back", "share repurchase",
        "return of capital", "normal course issuer bid", "tender buyback")),
    (RIGHTS, "live", (
        "rights issue", "renounceable", "entitlement offer", "rights offering")),
    (RESTR, "announced", (
        "administration", "administrators appointed", "creditors", "liability management",
        "restructuring", "insolvency", "judicial management", "winding-up")),
    (DELIST, "notice", (
        "delisting", "delisted", "removal from trading", "suspension of trading")),
]


def classify_intl(text: str | None) -> tuple[str | None, str | None]:
    """Map an international filing-type / headline to a mature category + stage. Falls back to
    the US text rules (shared house keywords) when no intl phrase matches. (None, None) if
    nothing fits."""
    if not text:
        return None, None
    t = " ".join(str(text).lower().split())
    for cat, stage, phrases in _INTL_RULES:
        if any(p in t for p in phrases):
            return cat, stage
    from engine import special_situations as sse
    return sse.classify_text(text)
