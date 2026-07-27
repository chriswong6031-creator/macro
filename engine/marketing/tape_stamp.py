"""engine.marketing.tape_stamp — deterministic "the tape moved" clause engine.

D05 Addendum 2 §7 (B2-COPY) tape-stamp law: the daemon runs on the VPS beside
``/var/lib/macro-live/public/live/quotes.json`` and the Sina/Webull feeds, so it
can attach ONE real number nobody relaying wires can — "WTI -1.8% on the headline".

The clause is threshold-gated and fabrication-proof:
  * map a wire item's tickers/entities -> live instruments (deterministic map);
  * read the live quote store (config path list, first existing wins);
  * a stamp is emitted ONLY when |move| >= threshold (default 0.4 %) AND the quote
    is fresh enough (staleness bound). A missing OR stale OR quiet quote yields
    NO stamp — we never fabricate a reaction, and a quiet tape is honestly silent.

Move basis (honest, from what the store actually carries):
  * the quote's own ``changePct`` (session move vs prior close) is the tape's
    reaction number. The store does not persist a price at ``detected_at``, so we
    do NOT claim a "since the headline" delta we cannot compute; the stamp phrases
    it as a session move ("today", or "vs prior close" overnight) — which is the
    number a reader can independently verify against the same feed.

IMPORT CLOSURE: stdlib only (json, re, time, pathlib, datetime). No pandas, no
yaml at module import — the thin marketing-engine CI lane must stay green. The
quote-store path list is passed in (the daemon reads config); this module never
reads yaml itself.

Public API:
    map_entities(item) -> list[str]                  # wire item -> instrument syms
    load_quotes(path_candidates) -> dict | None      # first existing store, parsed
    compute_stamp(item, quotes, *, now=None, cfg=None) -> dict
        {stamp: str, symbol: str|None, move_pct: float|None, reason: str}
        stamp == "" when no stamp is warranted (missing/stale/quiet/no-map).
    stamp_clause(item, quotes, *, now=None, cfg=None) -> str   # convenience: text only
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Config defaults (overridable via cfg dict passed from the daemon)
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_MIN_MOVE_PCT = 0.4          # |changePct| floor for a stamp to appear
_DEFAULT_STALENESS_MAX_S = 1800      # quote older than this -> NO stamp (30 min)

# Store path candidates (VPS first, repo fallback). The daemon overrides these
# via cfg["quote_store_paths"]; kept here so the module is usable standalone.
_DEFAULT_STORE_PATHS: tuple[str, ...] = (
    "/var/lib/macro-live/public/live/quotes.json",
    "site/live/quotes.json",
)

# ─────────────────────────────────────────────────────────────────────────────
# Entity/ticker -> live instrument symbol map (deterministic; keys of quotes.json)
#
# The quote store keys (2026-07-27 census): SPY QQQ ^RUT ^DJI ^HSI ^N225 ^KS11
#   ^TWII 000001.SS 510300.SS BTC-USD ES=F NQ=F CL=F BZ=F GC=F SI=F HG=F
#   DX-Y.NYB EURUSD=X GBPUSD=X USDJPY=X USDCNH=X USDCAD=X USDMXN=X USDCHF=X
#   USDBRL=X. A stamp names the instrument in plain words, so each symbol carries
#   a display label below.
# ─────────────────────────────────────────────────────────────────────────────

# entity keyword (lowercase, word-boundary matched) -> quote-store symbol.
# Ordered longest-first at match time so "crude oil" beats "oil" cleanly.
_ENTITY_TO_SYMBOL: dict[str, str] = {
    # energy
    "wti": "CL=F",
    "crude": "CL=F",
    "crude oil": "CL=F",
    "oil": "CL=F",
    "brent": "BZ=F",
    # metals
    "gold": "GC=F",
    "silver": "SI=F",
    "copper": "HG=F",
    # crypto
    "bitcoin": "BTC-USD",
    "btc": "BTC-USD",
    # dollar / fx
    "dollar": "DX-Y.NYB",
    "dxy": "DX-Y.NYB",
    "greenback": "DX-Y.NYB",
    "euro": "EURUSD=X",
    "yen": "USDJPY=X",
    "yuan": "USDCNH=X",
    "renminbi": "USDCNH=X",
    "sterling": "GBPUSD=X",
    "pound": "GBPUSD=X",
    "loonie": "USDCAD=X",
    "peso": "USDMXN=X",
    # equity index proxies
    "s&p": "ES=F",
    "s&p 500": "ES=F",
    "sp500": "ES=F",
    "nasdaq": "NQ=F",
    "russell": "^RUT",
    "dow": "^DJI",
    "nikkei": "^N225",
    "hang seng": "^HSI",
    "kospi": "^KS11",
    "shanghai": "000001.SS",
}

# Direct cashtag / index-ticker aliases from breaking_relevance's universe that a
# quote symbol exists for (equity ETFs live in the store as SPY/QQQ).
_TICKER_ALIAS: dict[str, str] = {
    "SPY": "SPY",
    "QQQ": "QQQ",
    "IWM": "^RUT",
    "DIA": "^DJI",
    "GLD": "GC=F",
    "SLV": "SI=F",
}

# Plain-word display label per store symbol (no raw slugs in front-facing copy).
_SYMBOL_LABEL: dict[str, str] = {
    "CL=F": "WTI", "BZ=F": "Brent", "GC=F": "Gold", "SI=F": "Silver",
    "HG=F": "Copper", "BTC-USD": "BTC", "DX-Y.NYB": "the dollar index",
    "EURUSD=X": "EUR/USD", "USDJPY=X": "USD/JPY", "USDCNH=X": "USD/CNH",
    "GBPUSD=X": "GBP/USD", "USDCAD=X": "USD/CAD", "USDMXN=X": "USD/MXN",
    "ES=F": "S&P futures", "NQ=F": "Nasdaq futures", "^RUT": "the Russell 2000",
    "^DJI": "the Dow", "^N225": "the Nikkei", "^HSI": "the Hang Seng",
    "^KS11": "the KOSPI", "000001.SS": "the Shanghai Composite",
    "SPY": "SPY", "QQQ": "QQQ",
}

# Compiled word-boundary patterns for entity matching, longest key first so a
# multi-word entity is preferred over a substring single word.
_ENTITY_PATTERNS: tuple[tuple[re.Pattern, str], ...] = tuple(
    (re.compile(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", re.IGNORECASE), sym)
    for kw, sym in sorted(_ENTITY_TO_SYMBOL.items(), key=lambda kv: -len(kv[0]))
)


# ─────────────────────────────────────────────────────────────────────────────
# Entity mapping
# ─────────────────────────────────────────────────────────────────────────────

def map_entities(item: dict) -> list[str]:
    """Map a (scored) wire item to live-quote instrument symbols, best-first.

    Precedence: matched tickers (from score_item) that alias to a store symbol,
    then entity keywords in headline + snippet. Deterministic order, deduped.
    """
    syms: list[str] = []

    matched = item.get("matched")
    if isinstance(matched, dict):
        for t in matched.get("tickers", []) or []:
            sym = _TICKER_ALIAS.get(str(t).upper())
            if sym and sym not in syms:
                syms.append(sym)

    text = f"{item.get('headline', '')} {item.get('body_snippet', '')}"
    for pat, sym in _ENTITY_PATTERNS:
        if sym in syms:
            continue
        if pat.search(text):
            syms.append(sym)
    return syms


# ─────────────────────────────────────────────────────────────────────────────
# Quote store loading (stdlib json; path list first-existing wins)
# ─────────────────────────────────────────────────────────────────────────────

def load_quotes(path_candidates: list[str] | tuple[str, ...] | None = None,
                *, root: Path | str | None = None) -> dict | None:
    """Load the first existing quote store from the candidate paths.

    Relative paths resolve against ``root`` (repo root) when supplied. Returns the
    parsed dict, or None when no store exists / parse fails (fail-soft: a missing
    store just means no stamps this tick).
    """
    candidates = list(path_candidates or _DEFAULT_STORE_PATHS)
    for cand in candidates:
        p = Path(cand)
        if not p.is_absolute() and root is not None:
            p = Path(root) / cand
        try:
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Freshness
# ─────────────────────────────────────────────────────────────────────────────

def _quote_epoch_ms(quote: dict, store: dict) -> int | None:
    """Best available quote timestamp in epoch ms (per-quote ts, else store ts)."""
    for src in (quote.get("ts"), store.get("ts")):
        try:
            v = int(src)
            if v > 0:
                return v
        except (TypeError, ValueError):
            continue
    return None


def _is_fresh(quote: dict, store: dict, now: datetime, staleness_max_s: int) -> bool:
    """True when the quote's timestamp is within staleness_max_s of `now`.

    No timestamp at all -> NOT fresh (fail-closed: an unstamped time is a stamp we
    refuse to make, never one we fabricate).
    """
    ms = _quote_epoch_ms(quote, store)
    if ms is None:
        return False
    age_s = now.timestamp() - (ms / 1000.0)
    # A future-dated quote (clock skew) is treated as fresh (age negative is fine);
    # only an OLD quote past the bound is stale.
    return age_s <= staleness_max_s


# ─────────────────────────────────────────────────────────────────────────────
# Stamp computation
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_pct(pct: float) -> str:
    """Signed one-decimal percent, e.g. +1.8% / -0.4%."""
    return f"{pct:+.1f}%"


def compute_stamp(
    item: dict,
    quotes: dict | None,
    *,
    now: datetime | None = None,
    cfg: dict | None = None,
) -> dict:
    """Compute the tape stamp for a scored wire item against the live quote store.

    Returns {stamp, symbol, move_pct, reason}. stamp == "" means NO stamp (the
    default outcome — the tape must actually have moved AND be fresh to earn one).
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)
    cfg = cfg or {}
    min_move = float(cfg.get("min_move_pct", _DEFAULT_MIN_MOVE_PCT))
    staleness_max_s = int(cfg.get("staleness_max_s", _DEFAULT_STALENESS_MAX_S))

    if not isinstance(quotes, dict):
        return {"stamp": "", "symbol": None, "move_pct": None, "reason": "no_store"}

    store_quotes = quotes.get("quotes")
    if not isinstance(store_quotes, dict) or not store_quotes:
        return {"stamp": "", "symbol": None, "move_pct": None, "reason": "empty_store"}

    syms = map_entities(item)
    if not syms:
        return {"stamp": "", "symbol": None, "move_pct": None, "reason": "no_mapping"}

    # Take the strongest mapped instrument that has a fresh, sufficient move. We
    # scan in precedence order and emit the FIRST that qualifies (deterministic).
    checked_any = False
    for sym in syms:
        q = store_quotes.get(sym)
        if not isinstance(q, dict):
            continue
        checked_any = True
        if not _is_fresh(q, quotes, now, staleness_max_s):
            continue
        try:
            pct = float(q.get("changePct"))
        except (TypeError, ValueError):
            continue
        if abs(pct) < min_move:
            continue
        label = _SYMBOL_LABEL.get(sym, sym)
        stamp = f"{label} {_fmt_pct(pct)}"
        return {"stamp": stamp, "symbol": sym, "move_pct": round(pct, 3),
                "reason": "moved"}

    if not checked_any:
        return {"stamp": "", "symbol": None, "move_pct": None,
                "reason": "symbol_absent"}
    return {"stamp": "", "symbol": None, "move_pct": None, "reason": "quiet_or_stale"}


def stamp_clause(
    item: dict,
    quotes: dict | None,
    *,
    now: datetime | None = None,
    cfg: dict | None = None,
) -> str:
    """Convenience: the stamp text only ("" when none warranted)."""
    return compute_stamp(item, quotes, now=now, cfg=cfg)["stamp"]
