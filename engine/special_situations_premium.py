"""M&A premium math for the Special Situations desk (B-F09-4 — display-only leaf).

Turns a classified Acquisition / Tender Offer / Going-Private event into ONE dated,
sourced premium number: the offer price (named filing + date) versus the unaffected
reference price (named date, taken from the trading-day close strictly before the
DEAL'S FIRST filing — never the filing being read). SCORED = False; this module
imports nothing from the scoring path and computes no rank, no expected return, no
trade authority. It reads only committed `data/` artifacts (no network) and never
guesses an issuer join — an unresolved or ambiguous CIK->ticker join is a typed
refusal, never a name match.

Precedent: engine/special_situations.py:34 (SCORED=False), :332 (lifecycle, source of
the announcement clock), engine/special_arb.py (deal-price extraction / plausibility
band), engine/capital_structure/document_terms.py (closed-enum, versioned schema
precedent for a bounded extraction scope).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SCORED = False
PREMIUM_SCHEMA = "special_situations.premium.v1"
PARSER_VERSION = "special-situations-premium/1.0.0"
DISCLAIMER_KEY = "disclaimer"

# Same categories as engine/special_arb.py:18 — only these have a fixed deal price.
PREMIUM_CATEGORIES = frozenset({"Acquisitions", "Tender Offers", "Going-Private"})

UNAFFECTED_LAG_TRADING_DAYS = 1
PLAUSIBLE_PREMIUM_PCT = (-50.0, 400.0)

_GROUP = "special_situations"
_RECEIPT_NAME = "premium_featured.json"

# CLOSED enum — precedent engine/capital_structure/document_terms.py:154 (TERM_NAMES).
REFUSALS: tuple[str, ...] = (
    "offer_terms_absent",
    "offer_price_implausible",
    "issuer_join_unresolved",
    "issuer_join_ambiguous",
    "announcement_date_unknown",
    "unaffected_price_unavailable",
    "currency_mismatch",
    "category_out_of_scope",
    "announcement_not_prior_to_filing",
    "computation_unavailable",
)

_NULL_COPY: dict[str, tuple[str, str]] = {
    "offer_terms_absent": (
        "Terms not disclosed in the filing — no price to compare.",
        "该文件未披露交易条款 — 无价格可比较。"),
    "offer_price_implausible": (
        "The price in this filing does not line up with the share price; not shown.",
        "该文件中的价格与股价明显不符，暂不显示。"),
    "issuer_join_unresolved": (
        "We could not confirm which listed company this filing belongs to.",
        "无法确认该文件对应哪家上市公司。"),
    "issuer_join_ambiguous": (
        "This company has more than one listed share class; we will not guess which one.",
        "该公司有多个上市股票类别，我们不做猜测。"),
    "announcement_date_unknown": (
        "We do not know the day this deal first reached the record, so there is no "
        "price to measure from.",
        "无法确定该交易首次进入记录的日期，因此没有可作为基准的股价。"),
    "unaffected_price_unavailable": (
        "We do not hold a share price from before this deal was announced.",
        "我们没有该交易公布之前的股价数据。"),
    "currency_mismatch": (
        "The offer and the share price are in different currencies; not compared.",
        "出价与股价币种不同，不作比较。"),
    "category_out_of_scope": (
        "This filing is not a takeover offer.",
        "该文件不属于收购要约。"),
    "announcement_not_prior_to_filing": (
        "We do not have a filing history showing this deal was announced before the "
        "one we are reading, so there is no earlier price to compare.",
        "我们没有显示该交易在本次文件之前已公布的历史记录，因此没有更早的股价可比较。"),
    "computation_unavailable": (
        "We could not compute a premium for this deal right now — check back later.",
        "我们暂时无法计算该交易的溢价，请稍后再试。"),
}


class PremiumRefusal(ValueError):
    """A premium cannot be computed for a stated, enumerated reason."""

    def __init__(self, reason: str):
        if reason not in REFUSALS:
            raise ValueError(f"unknown refusal reason: {reason!r}")
        self.reason = reason
        super().__init__(reason)


def _disclaimer() -> str:
    from engine import special_situations
    return special_situations.DISCLAIMER


def _refused(reason: str) -> dict:
    en, zh = _NULL_COPY[reason]
    return {
        "schema": PREMIUM_SCHEMA,
        "parser_version": PARSER_VERSION,
        "scored": SCORED,
        "is_context_only": True,
        "disclaimer": _disclaimer(),
        "status": "refused",
        "refusal": reason,
        "null_en": en,
        "null_zh": zh,
    }


def resolve_issuer(cik: object, *, ledger: Mapping[str, int]) -> tuple[str, str]:
    """(ticker, 'cik:<int>') for a CIK that maps to exactly ONE ticker in the canonical
    ledger (`data/edgar/ticker_cik_ledger.json` shape: {"tickers": {TICKER: CIK}}).
    CIK-keyed ONLY — this function never receives, reads, or matches an issuer's
    display name; the join key is the numeric filer identifier alone."""
    try:
        want = int(str(cik))
    except (TypeError, ValueError):
        raise PremiumRefusal("issuer_join_unresolved")
    matches = [tk for tk, c in ledger.items() if _as_int(c) == want]
    if not matches:
        raise PremiumRefusal("issuer_join_unresolved")
    if len(matches) > 1:
        raise PremiumRefusal("issuer_join_ambiguous")
    return matches[0], f"cik:{want}"


def _as_int(v: object) -> int | None:
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return None


def unaffected_reference(closes: "pd.Series", announcement_date: object, *,
                          lag_trading_days: int = UNAFFECTED_LAG_TRADING_DAYS,
                          ) -> tuple[float, str]:
    """(price, 'YYYY-MM-DD') of the close `lag_trading_days` trading rows BEFORE
    announcement_date. Raises PremiumRefusal('unaffected_price_unavailable') when the
    series does not cover it."""
    if closes is None:
        raise PremiumRefusal("unaffected_price_unavailable")
    s = closes.dropna()
    if s.empty or announcement_date is None:
        raise PremiumRefusal("unaffected_price_unavailable")
    try:
        d = pd.Timestamp(announcement_date)
    except (TypeError, ValueError):
        raise PremiumRefusal("unaffected_price_unavailable")
    pos = s.index.searchsorted(d)
    j = int(pos) - int(lag_trading_days)
    if not (0 <= j < len(s)):
        raise PremiumRefusal("unaffected_price_unavailable")
    idx = s.index[j]
    date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
    return float(s.iloc[j]), date_str


def compute_premium(offer_price: float, unaffected_price: float) -> float:
    """(offer/unaffected - 1) * 100, rounded to 1dp. Pure. Raises PremiumRefusal
    ('offer_price_implausible') outside PLAUSIBLE_PREMIUM_PCT or on non-positive inputs."""
    try:
        offer = float(offer_price)
        unaff = float(unaffected_price)
    except (TypeError, ValueError):
        raise PremiumRefusal("offer_price_implausible")
    if offer <= 0 or unaff <= 0:
        raise PremiumRefusal("offer_price_implausible")
    pct = round((offer / unaff - 1.0) * 100.0, 1)
    lo, hi = PLAUSIBLE_PREMIUM_PCT
    if not (lo <= pct <= hi):
        raise PremiumRefusal("offer_price_implausible")
    return pct


def _terms_dict(raw: object) -> dict:
    from engine import special_situations
    return special_situations._terms_dict(raw)


def premium_for_event(event: Mapping[str, object], *, closes: "pd.Series | None",
                       lifecycle_row: Mapping[str, object] | None,
                       ledger: Mapping[str, int], asof: str) -> dict:
    """ALWAYS returns a typed dict — never None, never raises. status is 'computed' or
    'refused'."""
    now = asof
    try:
        category = event.get("category")
        if category not in PREMIUM_CATEGORIES:
            return _refused("category_out_of_scope")

        from engine import special_arb as arb
        terms = arb.parse_terms(_terms_dict(event.get("llm_terms")))
        offer_price = terms.get("price_per_share")
        if not offer_price:
            return _refused("offer_terms_absent")
        currency = str(terms.get("currency")).upper() if terms.get("currency") else None

        cik = event.get("cik")
        ticker, issuer_key = resolve_issuer(cik, ledger=ledger)  # may raise

        if lifecycle_row is None:
            return _refused("announcement_date_unknown")
        announcement_filing_date = lifecycle_row.get("first_date")
        if announcement_filing_date is None or (
                isinstance(announcement_filing_date, float) and pd.isna(announcement_filing_date)):
            return _refused("announcement_date_unknown")

        # Blocker-1 fix: lifecycle()'s first_date is the earliest STORED filing for this
        # (cik, category) — for a deal we have only just started tracking, that IS the
        # filing we are reading, which is never a valid unaffected-price clock. Require at
        # least 2 stored filings AND a strictly-earlier announcement date before trusting
        # first_date as the announcement clock; otherwise this is a typed refusal, never a
        # silently-wrong premium.
        n_filings_val = _as_int(lifecycle_row.get("n_filings"))
        offer_filing_raw = event.get("date_filed")
        try:
            ann_ts = pd.Timestamp(announcement_filing_date)
        except (TypeError, ValueError):
            return _refused("announcement_date_unknown")
        try:
            offer_ts = pd.Timestamp(offer_filing_raw)
        except (TypeError, ValueError):
            offer_ts = None
        if n_filings_val is None or n_filings_val < 2 or (
                offer_ts is not None and ann_ts >= offer_ts):
            return _refused("announcement_not_prior_to_filing")

        if not currency:
            return _refused("currency_mismatch")
        market_currency = arb.market_currency(ticker)
        if not market_currency or currency != str(market_currency).upper():
            return _refused("currency_mismatch")

        unaffected_price, unaffected_price_date = unaffected_reference(
            closes, announcement_filing_date)  # may raise

        premium_pct = compute_premium(offer_price, unaffected_price)  # may raise

        offer_filing_date = event.get("date_filed")
        offer_form_type = str(event.get("form_type") or "")
        offer_accession = str(event.get("accession") or "")

        provenance = "filing_terms_extracted"
        try:
            cache = config.data_dir() / _GROUP / "doc_cache" / f"{offer_accession}.txt"
            if cache.exists():
                text = cache.read_text(encoding="utf-8", errors="ignore")
                parsed = arb.parse_terms_text(text) if hasattr(arb, "parse_terms_text") else {}
                pps = parsed.get("price_per_share") if isinstance(parsed, dict) else None
                if pps is not None and abs(float(pps) - float(offer_price)) <= 0.01:
                    provenance = "filing_text_confirmed"
        except Exception as e:  # noqa: BLE001 — best-effort confirmation only
            log.warning("special_situations_premium doc_cache confirm failed: %s", e)

        n_amend = lifecycle_row.get("n_amendments")
        n_filings = lifecycle_row.get("n_filings")
        amendment_vintage = {
            "form_type": offer_form_type,
            "is_amendment": offer_form_type.endswith("/A"),
            "n_amendments": int(n_amend) if n_amend is not None else None,
            "filings_in_deal": int(n_filings) if n_filings is not None else None,
        }

        def _dstr(v: object) -> str | None:
            if v is None:
                return None
            try:
                return pd.Timestamp(v).strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                return str(v)[:10]

        return {
            "schema": PREMIUM_SCHEMA,
            "parser_version": PARSER_VERSION,
            "scored": SCORED,
            "is_context_only": True,
            "disclaimer": _disclaimer(),
            "built": now,
            "status": "computed",
            "refusal": None,
            "ticker": ticker,
            "issuer_key": issuer_key,
            "company": str(event.get("company") or ""),
            "category": category,
            "currency": currency or "USD",
            "offer_price": float(offer_price),
            "offer_accession": offer_accession,
            "offer_filing_date": _dstr(offer_filing_date),
            "offer_form_type": offer_form_type,
            "offer_price_provenance": provenance,
            "announcement_filing_date": _dstr(announcement_filing_date),
            "unaffected_price": float(unaffected_price),
            "unaffected_price_date": unaffected_price_date,
            "premium_pct": premium_pct,
            "amendment_vintage": amendment_vintage,
            "source_url": str(event.get("source_url") or ""),
            "null_en": None,
            "null_zh": None,
        }
    except PremiumRefusal as r:
        return _refused(r.reason)
    except Exception as e:  # noqa: BLE001 — never raise out of a display-only leaf
        log.warning("special_situations_premium premium_for_event failed: %s", e)
        return _refused("computation_unavailable")


def _load_ledger() -> dict[str, int]:
    try:
        p = config.data_dir() / "edgar" / "ticker_cik_ledger.json"
        if not p.exists():
            return {}
        payload = json.loads(p.read_text(encoding="utf-8"))
        tickers = payload.get("tickers") if isinstance(payload, dict) else None
        return tickers if isinstance(tickers, dict) else {}
    except Exception as e:  # noqa: BLE001
        log.warning("special_situations_premium ledger load failed: %s", e)
        return {}


def premium_rows(limit: int | None = None, df: "pd.DataFrame | None" = None) -> list[dict]:
    """IO wrapper: build_situations() + lifecycle() + _closes_panel() + the CIK ledger,
    one premium_for_event() per in-scope row. Best-effort; never raises.

    `df` lets a caller that already built the situations frame (e.g. snapshot()) pass it
    in instead of paying for a second classification pass (Major-1 fix)."""
    from engine import special_situations as ss
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if df is None:
        try:
            df = ss.build_situations()
        except Exception as e:  # noqa: BLE001
            log.warning("special_situations_premium build_situations failed: %s", e)
            return []
    if df is None or df.empty:
        return []
    try:
        lc = ss.lifecycle(df)
    except Exception as e:  # noqa: BLE001
        log.warning("special_situations_premium lifecycle failed: %s", e)
        lc = {}
    try:
        panel = ss._closes_panel()
    except Exception as e:  # noqa: BLE001
        log.warning("special_situations_premium closes panel failed: %s", e)
        panel = pd.DataFrame()
    ledger = _load_ledger()

    rows: list[dict] = []
    scope = df[df.category.isin(PREMIUM_CATEGORIES)] if "category" in df.columns else df.iloc[0:0]
    for _, row in scope.iterrows():
        event = row.to_dict()
        cik = event.get("cik")
        key = (str(cik), event.get("category"))
        lifecycle_row = lc.get(key)
        closes = None
        try:
            ticker, _ik = resolve_issuer(cik, ledger=ledger)
            # Major-3 fix: exact ticker match only — a truncated fallback (dropping the
            # exchange/class suffix) can resolve to a DIFFERENT security's price column.
            if ticker in panel.columns:
                closes = panel[ticker]
        except PremiumRefusal:
            pass
        rows.append(premium_for_event(event, closes=closes, lifecycle_row=lifecycle_row,
                                       ledger=ledger, asof=now))
        if limit is not None and len(rows) >= limit:
            break
    return rows


def featured_premium(df: "pd.DataFrame | None" = None) -> dict:
    """Exactly ONE deal for the desk shell: the computed row with the most recent
    announcement_filing_date; tie-break lexicographically smallest offer_accession.
    Returns the newest REFUSED row if none computed, so the page still prints a true
    state instead of nothing. `df` — see premium_rows()."""
    try:
        rows = premium_rows(df=df)
    except Exception as e:  # noqa: BLE001
        log.warning("special_situations_premium featured_premium failed: %s", e)
        return _refused("computation_unavailable")
    if not rows:
        # Blocker-3 fix: no in-scope deals is a coverage fact, never a claim that a
        # specific filing omitted its terms — do not reuse offer_terms_absent here.
        return _refused("computation_unavailable")
    computed = [r for r in rows if r.get("status") == "computed"]
    if computed:
        computed.sort(key=lambda r: (r.get("announcement_filing_date") or "",
                                      "".join(reversed(r.get("offer_accession") or ""))),
                      reverse=True)
        # deterministic tie-break: smallest offer_accession among the max date
        best_date = computed[0].get("announcement_filing_date")
        tied = [r for r in computed if r.get("announcement_filing_date") == best_date]
        tied.sort(key=lambda r: r.get("offer_accession") or "")
        return tied[0]
    refused = sorted(rows, key=lambda r: str(r.get("built") or ""), reverse=True)
    return refused[0]


def write_receipt(path: "Path | None" = None) -> "Path | None":
    """Atomically write featured_premium() to data/special_situations/premium_featured.json
    (tmp + os.replace). Returns the path, or None on any failure (logged, never raised)."""
    try:
        target = path if path is not None else (config.data_dir() / _GROUP / _RECEIPT_NAME)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = featured_premium()
        fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".premium_featured_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, default=str)
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
        return target
    except Exception as e:  # noqa: BLE001
        log.warning("special_situations_premium write_receipt failed: %s", e)
        return None
