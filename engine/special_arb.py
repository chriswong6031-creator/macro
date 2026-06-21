"""Merger-arb spread math for the Special Situations desk (P1.2 — display-only).

For announced cash / cash+stock Acquisitions, Tender Offers and Going-Privates the
SPREAD (deal price vs the live price), its annualized return, and days-to-close is a
classic, directly observable event-driven datum — and the weekly digest does not
compute it. This module is PURE (no IO): it normalizes the deal terms the LLM lane
(P1.1) extracted, and turns (deal_price, live_price, expected_close) into spread /
annualized / downside-on-break numbers. The engine supplies the live + unaffected
prices; nothing here is scored or sized — it is context the desk and Mastermind read.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime

# only these categories have a fixed deal price to arb against
ARB_CATEGORIES = frozenset({"Acquisitions", "Tender Offers", "Going-Private"})
_DAYS_CAP = 1095          # clamp days-to-close to [1, 3y] so annualization can't explode
# a real pending cash deal trades within a sane band of its offer; an offer/price ratio far
# outside this is almost certainly a stale/mis-extracted deal price (e.g. a dividend grabbed
# instead of the offer) — reject it so a garbage spread can't sort to the TOP of the risk_arb
# book the Mastermind reads (which sorts by annualized_pct desc).
_PLAUS_LO, _PLAUS_HI = 0.6, 1.8
_CONSIDERATION = {"cash", "stock", "cash+stock", "other"}


def parse_terms(obj: object) -> dict:
    """Normalize an LLM `deal_terms` object into the canonical keys, dropping junk.
    Returns {} when there is nothing usable."""
    if not isinstance(obj, dict):
        return {}
    out: dict = {}
    pps = _num(obj.get("price_per_share"))
    if pps is not None and pps > 0:
        out["price_per_share"] = pps
    cur = obj.get("currency")
    if cur:
        out["currency"] = str(cur).strip().upper()[:3]
    con = str(obj.get("consideration") or "").strip().lower()
    if con in _CONSIDERATION:
        out["consideration"] = con
    prem = _num(obj.get("premium_pct"))
    if prem is not None:
        out["premium_pct"] = round(prem, 1)
    ec = _norm_close(obj.get("expected_close"))
    if ec:
        out["expected_close"] = ec
    bf = _num(obj.get("break_fee_musd"))
    if bf is not None and bf >= 0:
        out["break_fee_musd"] = bf
    return out


_PPS_RE = re.compile(
    r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(?:per\s+share|/\s?share|in\s+cash\s+per\s+share|cash\s+per\s+share)",
    re.I)
_CASH_RE = re.compile(r"\ball[- ]cash\b|\bin\s+cash\b|\bcash\s+consideration\b", re.I)
_STOCK_RE = re.compile(r"\ball[- ]stock\b|\bstock[- ]for[- ]stock\b|\bexchange\s+ratio\b", re.I)


def parse_terms_text(text: str | None) -> dict:
    """Regex fallback when the LLM lane is off / returned no terms: pull a price-per-share
    and the cash/stock nature from the filing body. Close date is left to the LLM lane."""
    if not text:
        return {}
    out: dict = {}
    m = _PPS_RE.search(text)
    if m:
        try:
            out["price_per_share"] = float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    cash, stock = bool(_CASH_RE.search(text)), bool(_STOCK_RE.search(text))
    if cash and stock:
        out["consideration"] = "cash+stock"
    elif cash:
        out["consideration"] = "cash"
    elif stock:
        out["consideration"] = "stock"
    return out


def days_to_close(expected_close: str | None, asof: date | None = None) -> int | None:
    """Calendar days from `asof` to the expected close (YYYY-MM[-DD]); None if unknown
    or already past. YYYY-MM resolves to month-end."""
    d = _to_date(expected_close)
    if d is None:
        return None
    asof = asof or _today()
    delta = (d - asof).days
    return delta if delta > 0 else None


def arb_metrics(deal_price: float | None, live_price: float | None, *,
                expected_close: str | None = None, asof: date | None = None,
                consideration: str | None = None, currency: str | None = None,
                unaffected_price: float | None = None) -> dict | None:
    """Spread economics for one announced deal. Returns None when not computable.

    gross_spread = deal/live - 1 (upside to the deal; negative = trading through it).
    annualized   = (deal/live)**(365/days) - 1, when a close date is known.
    downside     = unaffected/live - 1, the drop back toward the pre-announcement price
                   if the deal breaks (negative), when an unaffected price is supplied.
    Cross-currency deals (deal currency != USD price) are skipped to avoid a bogus spread.
    """
    dp, lp = _num(deal_price), _num(live_price)
    if dp is None or lp is None or dp <= 0 or lp <= 0:
        return None
    if currency and currency.upper() not in ("USD", "US$"):
        return None                                   # live close is USD; don't mix currencies
    if not (_PLAUS_LO <= dp / lp <= _PLAUS_HI):
        return None                                   # implausible offer/price → bad extraction;
        # keep a garbage spread out of the annualized-sorted risk_arb book
    gross = dp / lp - 1.0
    days = days_to_close(expected_close, asof)
    ann = None
    if days:
        d = max(1, min(int(days), _DAYS_CAP))
        ann = (dp / lp) ** (365.0 / d) - 1.0
    out = {
        "deal_price": round(dp, 4),
        "live_price": round(lp, 4),
        "gross_spread_pct": round(gross * 100, 2),
        "days_to_close": int(days) if days else None,
        "annualized_pct": round(ann * 100, 1) if ann is not None else None,
        "consideration": consideration,
    }
    up = _num(unaffected_price)
    if up is not None and up > 0:
        out["downside_on_break_pct"] = round((up / lp - 1.0) * 100, 1)
    return out


# ---------------------------------------------------------------- internals

def _num(v: object) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f      # drop NaN


def _norm_close(v: object) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    if re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", s):
        return s
    return None


def _to_date(v: object) -> date | None:
    s = _norm_close(v)
    if not s:
        return None
    try:
        if len(s) == 7:                               # YYYY-MM -> month end
            y, m = int(s[:4]), int(s[5:7])
            return date(y, m, calendar.monthrange(y, m)[1])
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, IndexError):
        return None


def _today() -> date:
    return datetime.now().date()
