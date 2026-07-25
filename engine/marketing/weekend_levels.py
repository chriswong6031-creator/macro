"""engine.marketing.weekend_levels — popular-ticker "levels into the week" posts.

WHY THIS EXISTS
The signal lane (content_studio) sources posts from the Prophet plan pool, which
(a) ages out — most plans exceed the 21-day postable window, so on a quiet week
`postable_signals` can return almost nothing — and (b) skews to mid-caps. On a
weekend, markets are closed and there are no fresh signals or same-day movers to
post at all. That is exactly when the account most needs reach content: people
search the cashtags of the stocks THEY hold ($NVDA, $TSLA, $AAPL…) over the
weekend to see what the tape is saying, and there is far less competition on
those hashtags than on a weekday.

This module fills that gap with an evergreen, drought-proof lane: for a curated
set of the most-searched tickers it reads Friday's close (EOD OHLCV) and writes a
short, honest "here's where it sits into the week" WATCHLIST post — levels and
observations, never a buy/sell call. It needs no Prophet plan and no live tape,
so it works every weekend regardless of signal supply.

COMPLIANCE
Emitted as kind="watchlist", which the Sentinel does NOT require a disclosure on
(disclosure law is signal-only, sentinel.py §disclosure). Copy is generated from
level facts with no financial-advice lexicon and exactly one cashtag per post, so
it clears the plan-level gate. `_assert_clean` enforces this at build time.

DISPLAY-TIER, NO AUTHORITY. This never scores, ranks, or escalates anything; it
is a presentation of public price levels. The publisher's live tape gate still
re-verifies every item before it posts (and post-#3466 posts level kinds against
the last close on weekends).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")

_STOCKS_REL = "data/stocks"

# The most-searched, always-liquid tickers — the reach list. Mirrors
# config/marketing.yml radar.t1_always; the caller may override.
_DEFAULT_REACH_TICKERS: tuple[str, ...] = (
    "NVDA", "TSLA", "AAPL", "AMD", "PLTR", "MSFT", "AMZN", "META",
    "GOOGL", "AVGO", "COIN", "NFLX", "MSTR", "HOOD", "SMCI",
)

# Financial-advice phrasing we must never emit (defense-in-depth mirror of the
# sentinel lexicon; the sentinel is the real authority).
_BANNED_SUBSTRINGS: tuple[str, ...] = (
    "you should buy", "you should sell", "get in now", "get in before",
    "guaranteed", "can't lose", "cannot lose", "sure thing", "easy money",
    "risk-free", "risk free", "free money", "no-brainer", "back up the truck",
    "load up", "all-in", "to the moon", "buy now", "must buy", "table pounding",
)


# ─────────────────────────────────────────────────────────────────────────────
# Level math (pure)
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(px: float) -> str:
    """Human price: 2dp under 100, else whole dollars (keeps copy terse)."""
    return f"{px:.2f}" if px < 100 else f"{px:,.0f}"


def compute_levels(closes: list[float]) -> dict[str, Any] | None:
    """Derive weekend levels from a close series (oldest→newest).

    Returns None when there is not enough history to say anything honest
    (need at least ~50 sessions for a 50-day line).
    """
    if not closes or len(closes) < 50:
        return None
    last = float(closes[-1])
    if last <= 0:
        return None
    wk_ref = closes[-6] if len(closes) >= 6 else closes[0]
    wk_pct = (last / wk_ref - 1.0) * 100.0 if wk_ref else 0.0
    sma20 = sum(closes[-20:]) / 20.0
    sma50 = sum(closes[-50:]) / 50.0
    window = closes[-252:] if len(closes) >= 252 else closes
    hi52 = max(window)
    lo52 = min(window)
    return {
        "last": last,
        "wk_pct": wk_pct,
        "sma20": sma20,
        "sma50": sma50,
        "hi52": hi52,
        "lo52": lo52,
        "above20": last >= sma20,
        "above50": last >= sma50,
        "pct_from_hi": (last / hi52 - 1.0) * 100.0 if hi52 else 0.0,
        "pct_from_lo": (last / lo52 - 1.0) * 100.0 if lo52 else 0.0,
    }


def classify_state(lv: dict[str, Any]) -> str:
    """One-word structural state used to pick copy and a direction lean."""
    near_hi = lv["pct_from_hi"] >= -2.5
    near_lo = lv["pct_from_lo"] <= 8.0
    if lv["above20"] and lv["above50"]:
        return "leading" if near_hi else "uptrend"
    if lv["above50"] and not lv["above20"]:
        return "cooling"          # above the 50, lost the 20
    if lv["above20"] and not lv["above50"]:
        return "reclaiming"       # back over the 20, still under the 50
    return "basing" if near_lo else "downtrend"


_LEAN = {
    "leading": "BULL", "uptrend": "BULL", "reclaiming": "BULL",
    "cooling": "NEUTRAL", "basing": "NEUTRAL", "downtrend": "BEAR",
}


# ─────────────────────────────────────────────────────────────────────────────
# Copy (honest, terse, watchlist voice — no calls)
# ─────────────────────────────────────────────────────────────────────────────

def _week_clause(wk: float) -> str:
    if abs(wk) < 0.5:
        return "roughly flat on the week"
    return f"{'up' if wk > 0 else 'down'} {abs(wk):.0f}% on the week"


def _trend_clause(lv: dict[str, Any]) -> str:
    s20, s50 = _fmt(lv["sma20"]), _fmt(lv["sma50"])
    if lv["above20"] and lv["above50"]:
        return f"holding above both the 20- ({s20}) and 50-day ({s50})"
    if lv["above50"] and not lv["above20"]:
        return f"back under the 20-day ({s20}) but still over the 50-day ({s50})"
    if lv["above20"] and not lv["above50"]:
        return f"back above the 20-day ({s20}), still under the 50-day ({s50})"
    return f"under both the 20- ({s20}) and 50-day ({s50})"


def _position_clause(lv: dict[str, Any]) -> str:
    fh = lv["pct_from_hi"]
    if fh >= -2.5:
        return "sitting right up at its 52-week high"
    if fh >= -8:
        return "near the top of its 52-week range"
    if lv["pct_from_lo"] <= 8:
        return "down near the low end of its 52-week range"
    span = lv["hi52"] - lv["lo52"]
    pos = (lv["last"] - lv["lo52"]) / span if span > 0 else 0.5
    if pos < 0.34:
        return f"about {abs(fh):.0f}% off the highs, in the lower third of its range"
    if pos > 0.66:
        return f"about {abs(fh):.0f}% off the highs, still upper-half of its range"
    return f"about {abs(fh):.0f}% off the highs, mid-range for the year"


def _watch_level(lv: dict[str, Any]) -> str:
    """The single level worth naming: the line it's testing right now."""
    if lv["above20"] and lv["above50"]:
        return f"the 20-day at {_fmt(lv['sma20'])} is the first line to hold"
    if lv["above50"] and not lv["above20"]:
        return f"getting back over {_fmt(lv['sma20'])} is what flips it back constructive"
    if lv["above20"] and not lv["above50"]:
        return f"the 50-day at {_fmt(lv['sma50'])} is the level I want reclaimed"
    # Under both MAs. Near the low → the low is the line that matters; otherwise
    # the nearest overhead line (20-day) is the first hurdle back.
    if lv["pct_from_lo"] <= 8:
        return f"watching whether {_fmt(lv['lo52'])} holds or gives way"
    return f"the 20-day at {_fmt(lv['sma20'])} is the first hurdle back"


# Rotated honest tails — all say the same true thing (watching, not advising).
_TAILS: tuple[str, ...] = (
    "On the watch list, not a call.",
    "Watching, no position.",
    "On the radar — tracking it, not touching it.",
    "Levels, not advice.",
)

# X hard limit. A post over this is never emitted (caller skips it).
_MAX_LEN: int = 280


def render_post(ticker: str, lv: dict[str, Any], *, variant: int = 0) -> tuple[str, str]:
    """(headline, body) for one ticker. Deterministic given (ticker, variant).

    The cashtag appears once (headline); the body carries the substance so the
    post never reads like a cashtag-stuffed bot. Adaptive length: the 52-week
    position sentence is context, so it is dropped first if the full post would
    exceed the X limit — the essentials (trend, the level to watch, the honest
    tail) always stay."""
    headline = f"${ticker} into the week"
    tail = _TAILS[variant % len(_TAILS)]

    def _body(with_position: bool) -> str:
        pos = f" {_position_clause(lv).capitalize()}." if with_position else ""
        return (
            f"Closed {_fmt(lv['last'])}, {_week_clause(lv['wk_pct'])}, "
            f"{_trend_clause(lv)}.{pos} Into next week, {_watch_level(lv)}. {tail}"
        )

    body = _body(True)
    if len(headline) + 2 + len(body) > _MAX_LEN:
        body = _body(False)
    return headline, body


# ─────────────────────────────────────────────────────────────────────────────
# Scheduling (weekend gating + ladder slot assignment)
# ─────────────────────────────────────────────────────────────────────────────

_LADDER = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")


def should_run(as_of: str) -> bool:
    """True when *as_of* (the content's target day) is a weekend (Sat/Sun).

    This lane exists to fill the low-signal, market-closed window; on trading
    days the normal signal lane carries the queue. Gated on the target DATE, not
    wall-clock — the nightly runs in the small hours UTC, so the run's local
    weekday is unreliable; the as_of it is generating for is what matters."""
    try:
        d = datetime.strptime(str(as_of)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return False
    return d.weekday() >= 5  # Saturday=5, Sunday=6


def weekend_schedule(as_of: str, n: int) -> list[tuple[str, str]]:
    """Assign up to *n* items to the D1 (=as_of) ladder slots, each resolved to
    its advisory scheduled_at (UTC via outbox.slot_datetime). The publisher's
    10-min floor paces whatever is already due; future slots post at their time."""
    from engine.marketing.outbox import slot_datetime  # noqa: PLC0415
    out: list[tuple[str, str]] = []
    for i in range(min(n, len(_LADDER))):
        slot = f"D1-{_LADDER[i]}"
        out.append((slot, slot_datetime(as_of, slot) or "immediate"))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Data loading + item construction
# ─────────────────────────────────────────────────────────────────────────────

def load_closes(root: Path | str | None, ticker: str) -> list[float] | None:
    """Read the EOD close series for *ticker* from data/stocks/<T>.parquet.

    Fail-soft: returns None on any missing file / unreadable frame / missing
    column so a single bad ticker never breaks the batch.
    """
    r = Path(root) if root is not None else Path(".")
    path = r / _STOCKS_REL / f"{ticker}.parquet"
    try:
        if not path.exists():
            return None
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path, columns=["close"])
        if "close" not in df.columns or df.empty:
            return None
        return [float(x) for x in df["close"].tolist() if x == x]  # drop NaN
    except Exception as exc:  # noqa: BLE001
        log.warning("weekend_levels: unreadable closes for %s: %s", ticker, exc)
        return None


def _assert_clean(text: str, ticker: str) -> None:
    """Guard: no advice lexicon, exactly one cashtag. Raises on violation so a
    non-compliant post can never be emitted (caller skips it)."""
    if len(text) > _MAX_LEN:
        raise ValueError(f"{ticker} copy is {len(text)} chars (max {_MAX_LEN})")
    low = text.lower()
    for bad in _BANNED_SUBSTRINGS:
        if bad in low:
            raise ValueError(f"banned phrase {bad!r} in {ticker} copy")
    distinct = set(_CASHTAG_RE.findall(text))
    if distinct != {ticker.upper()}:
        raise ValueError(f"{ticker} copy cashtags {distinct or '∅'}, want exactly {{{ticker.upper()}}}")


def build_items(
    root: Path | str | None,
    *,
    tickers: list[str] | None = None,
    as_of: str,
    account: str = "flagship",
    provenance: str = "weekend_levels",
    now: datetime | None = None,
    schedule: list[tuple[str, str]] | None = None,
    max_items: int = 8,
) -> list[dict[str, Any]]:
    """Build outbox item dicts (via outbox.make_item) for the reach tickers.

    schedule: optional list of (slot_label, scheduled_at_iso) assigned in order;
    when omitted, items are scheduled "immediate" with no slot (caller schedules).
    Returns at most *max_items* items, one per ticker that has usable data and
    compliant copy. Never raises — a bad ticker is skipped with a warning.
    """
    from engine.marketing.outbox import make_item  # noqa: PLC0415

    ts_now = now if now is not None else datetime.now(timezone.utc)
    picks = [t.upper() for t in (tickers or _DEFAULT_REACH_TICKERS)]
    out: list[dict[str, Any]] = []

    for idx, ticker in enumerate(picks):
        if len(out) >= max_items:
            break
        closes = load_closes(root, ticker)
        lv = compute_levels(closes) if closes else None
        if lv is None:
            log.info("weekend_levels: skip %s (insufficient data)", ticker)
            continue
        headline, body = render_post(ticker, lv, variant=idx)
        text = f"{headline}\n\n{body}"
        try:
            _assert_clean(text, ticker)
        except ValueError as exc:
            log.warning("weekend_levels: %s", exc)
            continue

        slot_label: str | None = None
        scheduled_at = "immediate"
        if schedule and len(out) < len(schedule):
            slot_label, scheduled_at = schedule[len(out)]

        source = {
            "ticker": ticker,
            "direction": _LEAN.get(classify_state(lv), "NEUTRAL"),
            "state": classify_state(lv),
            "last_close": round(lv["last"], 2),
            "wk_pct": round(lv["wk_pct"], 1),
            "lane": "weekend_levels",
        }
        try:
            item = make_item(
                account=account, kind="watchlist", text=text, as_of=as_of,
                scheduled_at=scheduled_at, slot=slot_label, priority=5,
                provenance=provenance, source=source, now=ts_now,
            )
        except ValueError as exc:
            log.warning("weekend_levels: make_item failed for %s: %s", ticker, exc)
            continue
        out.append(item)

    return out
