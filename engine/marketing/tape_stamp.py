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

THE MACRO PRINT HAD NO PATH TO A STAMP AT ALL (2026-08-05)
----------------------------------------------------------
Measured over the 83 ``kind=breaking`` rows in ``data/marketing/outbox/items.jsonl``
since 2026-08-03T14:39Z: 83 of 83 carry ``source.tape_stamp == ""``. Replaying
this module over them, 79 return ``no_mapping`` and 4 return ``quiet_or_stale``
— and 3 of those 4 mapped to WTI off the bare word "oil" inside a Cramer/Chevron
headline, which is an entity MENTION, not a reaction instrument.

The cause is structural, not a bug: :func:`map_entities` requires the headline or
snippet to literally NAME an instrument, and a macro print names a STATISTIC.
"US ISM Manufacturing PMI for July 55.6 versus 54.0 estimate", "JOLTs job
openings 7.359M vs 7.400M estimate", "US June factory orders -0.3% vs +0.2%
expected" — none of them contains a ticker, a metal or a currency, so none of
them could ever earn a stamp. Keyword mapping is a COMPANY/COMMODITY-news idiom
that was applied to a MACRO class, and the class it silently excluded is the one
whose place on the brand account ``config/marketing.yml wire_routing.classes``
justifies in exactly these words: "a CPI/NFP/GDP print is only half the post; the
half our readers come for is what it does to the path". We were keeping the class
on the brand desk for a read the code could not attach.

Second structural gap: "the path" had no instrument here even in principle. The
live plane serves 34 symbols including ``^TNX``/``^IRX``/``^FVX``/``^TYX``, and
this module's maps knew none of them.

The fix is :func:`reaction_basket` — for a US macro print the reaction
instruments are known A PRIORI and do not need to be named in the headline: the
risk tape, the front of the path and the dollar. Every number is still measured,
still threshold-gated, still freshness-gated, and the clause makes NO causal
claim ("S&P futures +0.6% · the 10-year +5bp" is a co-timed reading, never
"because of the print"). The LLM never touches it (constitution A7).

IMPORT CLOSURE: stdlib only (json, re, time, pathlib, datetime). No pandas, no
yaml at module import — the thin marketing-engine CI lane must stay green. The
quote-store path list is passed in (the daemon reads config); this module never
reads yaml itself.

Public API:
    map_entities(item) -> list[str]                  # wire item -> instrument syms
    load_quotes(path_candidates) -> dict | None      # first existing store, parsed
    reaction_basket(item, quotes, *, now=None, cfg=None) -> dict
        {stamp, legs, reason} — the US-macro-print path (see below).
    compute_stamp(item, quotes, *, now=None, cfg=None) -> dict
        {stamp: str, symbol: str|None, move_pct: float|None, reason: str, legs: list}
        stamp == "" when no stamp is warranted (missing/stale/quiet/no-map).
    stamp_clause(item, quotes, *, now=None, cfg=None) -> str   # convenience: text only
    shorten_stamp(stamp, max_legs) -> str            # budget ladder: shed legs, keep the read
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
# m3: a quote whose timestamp is MORE than this many seconds in the FUTURE is a
# clock-skew / corrupt-feed signal, NOT a fresh quote -> NO stamp (fail-closed). A
# small tolerance absorbs benign sub-2-minute skew between the feed clock and ours.
_DEFAULT_FUTURE_SKEW_TOLERANCE_S = 120

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
    # Curve tenors. Named the way `copywriter._NAMED_PRINT_TERMS` whitelists them
    # ("10-year", "Treasury yield") so a stamp reads as a NAMED PRINT the reader
    # can look up, not as desk jargon.
    "^IRX": "the 3-month", "^FVX": "the 5-year",
    "^TNX": "the 10-year", "^TYX": "the 30-year",
}

# ─────────────────────────────────────────────────────────────────────────────
# YIELD UNITS — a yield index is quoted in PERCENT, so its `changePct` is a
# percent OF a percent and printing it is simply wrong.
#
# Live store, 2026-08-05: ^TNX price 4.627, prevClose 4.686, changePct -1.26.
# The yield fell 5.9 BASIS POINTS. Rendering that leg with `_fmt_pct(changePct)`
# would ship "the 10-year -1.3%", which a reader parses either as a 1.3% yield or
# as a bond-price move — neither is what happened. The honest number is the
# arithmetic difference in bp: (price - prevClose) * 100.
#
# So a yield leg carries its OWN units, its OWN formatter and its OWN threshold,
# and the price path is left exactly as it was.
# ─────────────────────────────────────────────────────────────────────────────
_YIELD_SYMBOLS: frozenset[str] = frozenset({"^IRX", "^FVX", "^TNX", "^TYX"})

# ─────────────────────────────────────────────────────────────────────────────
# THE US MACRO REACTION BASKET — the class-driven path
#
# A macro print names a statistic, never an instrument, so its reaction
# instruments cannot come from the headline. They come from the CLASS: what a
# CPI/NFP/ISM print moves is the risk tape, the front of the path, and the
# dollar. Three legs, fixed, in that order — the order a macro desk reads them.
#
# PER-LEG FLOORS ARE MEASURED, NOT PICKED. Each floor is that instrument's
# MEDIAN absolute daily move over the trailing ~3y (2023-08-01 -> 2026-08-05,
# n≈750 sessions), so the three legs mean the SAME THING as each other — "this
# leg moved at least as much as it does on a typical whole day" — instead of
# sharing one number that means a shrug on one instrument and a shock on another.
# The single inherited 0.4% floor was exactly that: ≈p43 of SPY's distribution
# but ≈p85 of the dollar's, so a dollar leg would have shown on 1 day in 7.
#
#   ES=F      0.5 %   SPY close-to-close |move|, p50 = 0.497 %  (data/yahoo/SPY)
#   ^TNX      4 bp    DGS10 |diff|,             p50 = 4.0 bp    (data/fred/DGS10)
#   DX-Y.NYB  0.17 %  DTWEXBGS |pct_change|,    p50 = 0.168 %   (data/fred/DTWEXBGS)
#
# TWO HONEST CAVEATS, both making the basket MORE permissive than p50 rather
# than less, which is the safe direction for a display-tier clause:
#   * the floors are full-session distributions but the reading is a PARTIAL
#     session (most US prints land 08:30 ET). A partial-session move that already
#     equals a typical WHOLE day is unambiguously notable — that is the point of
#     anchoring here rather than higher.
#   * DTWEXBGS is the BROAD dollar index; DX-Y.NYB spot runs a little hotter, so
#     0.17 % sits slightly under its own p50.
# Every floor is config-overridable under `wire.tape.reaction` in press_sources.yml.
_US_MACRO_BASKET: tuple[tuple[str, float], ...] = (
    ("ES=F", 0.5),          # percent
    ("^TNX", 4.0),          # BASIS POINTS (yield index — see _YIELD_SYMBOLS)
    ("DX-Y.NYB", 0.17),     # percent
)

#: How many legs a stamp may carry. Three is the whole basket; the caller's
#: length-budget ladder sheds legs from the tail via :func:`shorten_stamp`.
_DEFAULT_MAX_LEGS = 3

#: The separator between legs. The same mid-dot the composed post already uses
#: to hang the stamp off the body, so the whole tail reads as one clause family
#: and `wire_format._line_two_residue` still strips it as our own furniture.
_LEG_SEP = " · "

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


def _is_fresh(
    quote: dict,
    store: dict,
    now: datetime,
    staleness_max_s: int,
    future_skew_tolerance_s: int = _DEFAULT_FUTURE_SKEW_TOLERANCE_S,
) -> bool:
    """True when the quote's timestamp is within staleness_max_s of `now`.

    No timestamp at all -> NOT fresh (fail-closed: an unstamped time is a stamp we
    refuse to make, never one we fabricate).

    m3: a quote timestamped MORE than future_skew_tolerance_s in the future is a
    clock-skew / corrupt-feed signal, not a fresh quote -> NOT fresh (fail-closed).
    Previously any future-dated quote passed as fresh, so a garbage-future ts could
    mint a stamp off a stale or wrong number. A small tolerance still admits benign
    sub-tolerance skew between the feed clock and ours.
    """
    ms = _quote_epoch_ms(quote, store)
    if ms is None:
        return False
    age_s = now.timestamp() - (ms / 1000.0)
    # Future-skew clamp (fail-closed): age below -tolerance means the quote is dated
    # meaningfully after `now` -> reject. Benign skew (age >= -tolerance) is fine.
    if age_s < -abs(future_skew_tolerance_s):
        return False
    # An OLD quote past the staleness bound is likewise not fresh.
    return age_s <= staleness_max_s


# ─────────────────────────────────────────────────────────────────────────────
# Stamp computation
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_pct(pct: float) -> str:
    """Signed one-decimal percent, e.g. +1.8% / -0.4%."""
    return f"{pct:+.1f}%"


def _fmt_bp(bp: float) -> str:
    """Signed whole basis points, e.g. +5bp / -12bp.

    Whole bp on purpose: the feed carries the 10-year to three decimals of a
    percent (4.627), which is tenths of a bp — precision the reader cannot use
    and the feed does not really have. "bp" is house units vocabulary
    (`copywriter._ANCHOR_NUMBER_RE` admits it as a print's number).
    """
    return f"{bp:+.0f}bp"


def _leg_reading(sym: str, quote: dict, min_move: float) -> tuple[str, float] | None:
    """One basket leg's plain-word reading, or None when it does not qualify.

    Returns ``(text, move)`` where `move` is percent for a price and BASIS POINTS
    for a yield index — the units the leg's own floor is expressed in.

    Freshness is the CALLER's check; this decides units, threshold and wording.
    """
    label = _SYMBOL_LABEL.get(sym, sym)

    if sym in _YIELD_SYMBOLS:
        # bp, from the arithmetic difference — never from changePct (see the
        # _YIELD_SYMBOLS note). A missing/zero prevClose is not a zero move, it
        # is an unknown one: fail closed rather than mint a bp number off it.
        try:
            price = float(quote.get("price"))
            prev = float(quote.get("prevClose"))
        except (TypeError, ValueError):
            return None
        if prev <= 0:
            return None
        bp = (price - prev) * 100.0
        if abs(bp) < min_move:
            return None
        return f"{label} {_fmt_bp(bp)}", round(bp, 2)

    try:
        pct = float(quote.get("changePct"))
    except (TypeError, ValueError):
        return None
    if abs(pct) < min_move:
        return None
    return f"{label} {_fmt_pct(pct)}", round(pct, 3)


def _basket_for(item: dict, cfg: dict) -> tuple[tuple[str, float], ...]:
    """The reaction basket this item qualifies for, or () for no basket.

    ONE GATE, TWO HALVES, both required:

      * ``event_class == "macro_print"`` — the class whose product IS the read.
        `policy` (Fed/White House/tariffs) is the other flagship class and wants
        the same treatment, but `macro_print_tier` is deliberately scoped to one
        class ("a function scoped to one class must have NO opinion about the
        others"), so extending it needs its own economy test rather than a
        second, quietly-disagreeing copy of this one. Left for a follow-up.

      * ``macro_economy == "us"`` — stamped onto the item by
        `breaking_relevance.score_item`. THIS IS THE HONESTY GATE. Every number
        in the basket is a US instrument, so hanging it off "Canada June trade
        balance +3.86B" would present an unrelated US session move as that
        print's reading. Real numbers, fabricated link — the exact failure the
        module's "we never fabricate a reaction" law exists to prevent.

    FAIL-CLOSED ON AN ABSENT FIELD. An item scored before `macro_economy`
    existed carries "", which is not "us", so it gets NO basket and the caller
    falls through to the entity map — i.e. today's behaviour exactly. The basket
    can only ever ADD a stamp where there was none; it can never change or
    remove one.
    """
    if str(item.get("event_class") or "") != "macro_print":
        return ()
    if str(item.get("macro_economy") or "") != "us":
        return ()

    raw = cfg.get("basket")
    if not isinstance(raw, list) or not raw:
        return _US_MACRO_BASKET
    legs: list[tuple[str, float]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        sym = str(entry.get("symbol") or "").strip()
        try:
            floor = float(entry.get("min_move"))
        except (TypeError, ValueError):
            continue
        if sym:
            legs.append((sym, floor))
    return tuple(legs) or _US_MACRO_BASKET


def reaction_basket(
    item: dict,
    quotes: dict | None,
    *,
    now: datetime | None = None,
    cfg: dict | None = None,
) -> dict:
    """The measured US-tape reading for a US macro print.

    Returns ``{stamp, legs, reason}``. ``stamp == ""`` means no leg qualified —
    the same honest silence a quiet tape has always produced, never a placeholder.

    Each leg is gated INDEPENDENTLY on freshness and on its own floor, so a
    silent leg drops out and the rest still ship. That matters overnight: the
    yield indexes only tick in the US session (``^TNX`` carried delayMin 826 at
    04:46 ET on 2026-08-05), so a pre-open print reads on futures and the dollar
    and simply does not claim a rates move it cannot see.

    NO CAUSAL CLAIM IS MADE. The clause is a co-timed session reading vs prior
    close — the same basis the single-instrument stamp has always used, and a
    number the reader can verify against the same public feed. It says what the
    tape DID, never that the print is why.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)
    cfg = cfg or {}
    reaction_cfg = cfg.get("reaction") if isinstance(cfg.get("reaction"), dict) else {}

    basket = _basket_for(item, reaction_cfg)
    if not basket:
        return {"stamp": "", "legs": [], "reason": "no_basket"}

    if not isinstance(quotes, dict):
        return {"stamp": "", "legs": [], "reason": "no_store"}
    store_quotes = quotes.get("quotes")
    if not isinstance(store_quotes, dict) or not store_quotes:
        return {"stamp": "", "legs": [], "reason": "empty_store"}

    staleness_max_s = int(cfg.get("staleness_max_s", _DEFAULT_STALENESS_MAX_S))
    future_skew_tolerance_s = int(
        cfg.get("future_skew_tolerance_s", _DEFAULT_FUTURE_SKEW_TOLERANCE_S)
    )
    max_legs = int(reaction_cfg.get("max_legs", _DEFAULT_MAX_LEGS))

    texts: list[str] = []
    legs: list[dict] = []
    for sym, floor in basket:
        if len(texts) >= max_legs:
            break
        q = store_quotes.get(sym)
        if not isinstance(q, dict):
            continue
        if not _is_fresh(q, quotes, now, staleness_max_s, future_skew_tolerance_s):
            continue
        reading = _leg_reading(sym, q, floor)
        if reading is None:
            continue
        text, move = reading
        texts.append(text)
        legs.append({"symbol": sym, "text": text, "move": move,
                     "units": "bp" if sym in _YIELD_SYMBOLS else "pct"})

    if not texts:
        return {"stamp": "", "legs": [], "reason": "basket_quiet_or_stale"}
    return {"stamp": _LEG_SEP.join(texts), "legs": legs, "reason": "basket"}


def shorten_stamp(stamp: str, max_legs: int) -> str:
    """The first ``max_legs`` legs of a multi-leg stamp (<=0 legs -> "").

    The length-budget ladder in `press_lane._apply_wire_voice` used to shed the
    OPENER and then decline the whole voice pass, which threw the tape reading
    away to save characters the reading was the point of. Shedding a leg is the
    cheaper trade: a two-leg read is still a read.

    Parsing our own separator, not guessing at a model's — `_LEG_SEP` is written
    by :func:`reaction_basket` a few lines above.
    """
    stamp = str(stamp or "").strip()
    if not stamp or max_legs <= 0:
        return ""
    return _LEG_SEP.join(stamp.split(_LEG_SEP)[:max_legs])


def compute_stamp(
    item: dict,
    quotes: dict | None,
    *,
    now: datetime | None = None,
    cfg: dict | None = None,
) -> dict:
    """Compute the tape stamp for a scored wire item against the live quote store.

    Returns {stamp, symbol, move_pct, reason, legs}. stamp == "" means NO stamp
    (the default outcome — the tape must actually have moved AND be fresh to
    earn one).

    TWO PATHS, BASKET FIRST. A US macro print takes the class-driven
    :func:`reaction_basket`; everything else takes the entity map exactly as
    before. The order is what makes this additive: the basket only fires on a
    population that measured 100 % empty (see the module note), and when it
    stays silent the entity map still runs, so no item that earns a stamp today
    loses or changes one.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)
    cfg = cfg or {}

    if bool((cfg.get("reaction") or {}).get("enabled", True)):
        basket = reaction_basket(item, quotes, now=now, cfg=cfg)
        if basket["stamp"]:
            return {"stamp": basket["stamp"], "symbol": None, "move_pct": None,
                    "reason": basket["reason"], "legs": basket["legs"]}

    min_move = float(cfg.get("min_move_pct", _DEFAULT_MIN_MOVE_PCT))
    staleness_max_s = int(cfg.get("staleness_max_s", _DEFAULT_STALENESS_MAX_S))
    future_skew_tolerance_s = int(
        cfg.get("future_skew_tolerance_s", _DEFAULT_FUTURE_SKEW_TOLERANCE_S)
    )

    if not isinstance(quotes, dict):
        return {"stamp": "", "symbol": None, "move_pct": None, "reason": "no_store",
                "legs": []}

    store_quotes = quotes.get("quotes")
    if not isinstance(store_quotes, dict) or not store_quotes:
        return {"stamp": "", "symbol": None, "move_pct": None, "reason": "empty_store",
                "legs": []}

    syms = map_entities(item)
    if not syms:
        return {"stamp": "", "symbol": None, "move_pct": None, "reason": "no_mapping",
                "legs": []}

    # Take the strongest mapped instrument that has a fresh, sufficient move. We
    # scan in precedence order and emit the FIRST that qualifies (deterministic).
    checked_any = False
    for sym in syms:
        q = store_quotes.get(sym)
        if not isinstance(q, dict):
            continue
        checked_any = True
        if not _is_fresh(q, quotes, now, staleness_max_s, future_skew_tolerance_s):
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
                "reason": "moved", "legs": []}

    if not checked_any:
        return {"stamp": "", "symbol": None, "move_pct": None,
                "reason": "symbol_absent", "legs": []}
    return {"stamp": "", "symbol": None, "move_pct": None,
            "reason": "quiet_or_stale", "legs": []}


def stamp_clause(
    item: dict,
    quotes: dict | None,
    *,
    now: datetime | None = None,
    cfg: dict | None = None,
) -> str:
    """Convenience: the stamp text only ("" when none warranted)."""
    return compute_stamp(item, quotes, now=now, cfg=cfg)["stamp"]
