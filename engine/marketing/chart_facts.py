"""engine.marketing.chart_facts — Deterministic "understand the chart" engine.

Turns raw OHLCV arrays into concrete, human-readable facts a writer can use.
All computation is deterministic (no RNG, no network). Every number that appears
in a fact text is also added to numbers_whitelist so the copy validator can confirm
no invented numbers sneak into posts.

Public API:
    compute_facts(ticker, dates, o, h, l, c, v) -> dict
      {
        "facts": [{"id": str, "text": str, "salience": int, "numbers": [str]}, ...],
        "numbers_whitelist": [str, ...],
      }

Salience scale (higher = more remarkable, harder to dismiss):
  10: new 52-week record (all-time-window high/low)
   9: volume record (highest in >=90 days)
   8: first reclaim/loss of key moving average since a named date; reclaim of
      the average price paid since the anchor (avwap_reclaim)
   7: 52-week high/low proximity (within 3%); retest & hold of the most-traded
      price (poc_retest_hold)
   6: 5+ session streak (green or red); holding the average price paid since the
      anchor — a passive "still above" state, streak-tier (avwap_hold)
   5: volume surge (>=2.5× average); most-traded-price level (poc_level)
   4: biggest single-day move in >=60 sessions
   3: tight range (NR7-style compression); sitting inside the band where most
      volume traded (in_value_area)
   2: percentage change (4w, 13w)
   1: percentage change (1w)

Polarity contract (M2 facts only):
  Every M2 fact dict carries a "polarity" key ∈ {+1, 0, -1} so directional
  posts can filter without brittle text-marker matching (a bull post must
  never lead with a bearish fact). +1 = bullish, -1 = bearish, 0 = neutral.
  Legacy (non-M2) facts have no polarity key and use the text-marker path.

Basis contract (extreme/level facts):
  Every fact whose detection compares a price to a level carries a "basis" key
  ∈ {"close", "intraday"} naming the series it was measured on, and its wording
  may only claim what that series supports — "closed at a new 52-week low" for
  close basis, "traded down to X intraday" for intraday basis. A fact detected
  on one basis and phrased on the other is the 2026-07-28 $TSLA defect (an
  intraday low, close-phrased, contradicted by the record's own last_close).

PLAIN-LANGUAGE CONTRACT (2026-07-26 $AAPL incident).
A fact is not raw material for the writer, it is the SENTENCE the reader ends up
holding: copywriter ships fact texts verbatim in the LLM prompt and renders
{top_fact} verbatim in the deterministic templates. So a fact that names a study
puts that study's name in a public post. The M2 detectors originally emitted
"Held the anchored VWAP from the Jun 26 volume-spike anchor for 20 straight
sessions" and the flagship account duly posted "That Jun 26 anchored VWAP has
held for 20 sessions. I'm watching a close below it" — jargon the reader cannot
decode, pointing at a line whose price the post never gave. Two rules follow:

  1. NAME THE THING IN PLAIN WORDS. No study names, no acronyms, no
     "anchored VWAP" / "point of control" / "value area". Say what the level IS
     ("the average price paid since the Jun 26 volume spike", "the price where
     the most shares changed hands"). copywriter.validate_copy now rejects the
     jargon outright, so a fact carrying it costs the post its voice lane.
  2. A FACT THAT REFERENCES A LEVEL MUST CARRY ITS PRICE, in the text AND in
     "numbers". avwap_hold used to whitelist only the streak count and the anchor
     day, so a writer obeying the whitelist literally could not name the line it
     was told to write about. "Watching a close below it" was the only sentence
     available to it.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Number formatters (produce strings that appear exactly in copy and whitelist)
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_pct(v: float, decimals: int = 1) -> str:
    """Format a signed percentage, e.g. '+12.3%' or '-5.5%'."""
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.{decimals}f}%"


def _fmt_price(v: float) -> str:
    """Format a price level with 2 decimal places, e.g. '226.50'."""
    return f"{v:.2f}"


def _fmt_mult(v: float) -> str:
    """Format a multiplier, e.g. '3x' or '2.5x'."""
    if v >= 10:
        return f"{round(v):.0f}x"
    return f"{v:.1f}x"


def _month_year(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' to 'Mon YYYY', e.g. 'Jul 2025'."""
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return dt.strftime("%b %Y")
    except Exception:
        return date_str[:7]


#: How old a prior extreme must be before "first since <date>" is INFORMATION.
#:
#: THE DEGENERATE-LOOKBACK DEFECT (2026-07-28 $ROST, 25 posts in one week).
#: The since-date is derived from the prior extreme found INSIDE the very same
#: 252-bar window the record is measured against. On a name printing new highs
#: day after day, the previous high is YESTERDAY, so the clause reads "$ROST hit
#: a new 52-week high, first since Jun 2026" on 07-28 and "first since Jul 2026"
#: on 07-29 — a sentence that says "the last time this happened was the last
#: time this happened". It is worse than filler: it wears the shape of a rarity
#: claim ("first since" implies a long absence) while asserting the opposite.
#: 60 sessions ≈ a quarter — below that the honest post is the record itself
#: with no rarity clause at all, so the clause is SUPPRESSED, never softened and
#: never replaced with a placeholder (see `_first_since`).
_MIN_SINCE_SESSIONS = 60


def _first_since(prior_date: object, age_sessions: int) -> str:
    """Month-year label for a "first since ..." clause, or "" to suppress it.

    "" means the caller must emit NO clause. Two callers used to render the
    literal string "a while" when the prior date could not be found
    (`_fact_sma_cross`), and that string went into the fact's `numbers` list as
    well — so "first time since a while" was both published copy and a licensed
    "number". A fact we cannot date does not get a date-shaped sentence.
    """
    if not prior_date or age_sessions < _MIN_SINCE_SESSIONS:
        return ""
    return _month_year(str(prior_date))


def _last_set_at(series: list[float], value: float) -> int:
    """Index of the LAST bar in *series* equal to *value* (-1 when absent).

    LAST, not first. The old code used ``list.index()``, which finds the
    EARLIEST bar at the extreme — on a series that touched 100.00 in January and
    again in July, a new high today was captioned "first since Jan", which is
    false: it was also at the high in July. The most recent touch is the only
    date that makes "first since" true, and it is also the one that exposes the
    degeneracy `_MIN_SINCE_SESSIONS` exists to suppress.
    """
    for i in range(len(series) - 1, -1, -1):
        if series[i] == value:
            return i
    return -1


def _window_label(sessions: int) -> str:
    """Plain-word span for a lookback in trading sessions ('six months').

    A fact that says "the most-traded price of the past six months" is readable
    cold; "the point of control over a 126-session volume profile" is not. Spelled
    out, never numeric, so the phrase adds no token to the numbers whitelist.
    """
    months = max(1, round(sessions / 21))
    words = {1: "month", 2: "two months", 3: "three months", 4: "four months",
             5: "five months", 6: "six months", 7: "seven months",
             8: "eight months", 9: "nine months", 10: "ten months",
             11: "eleven months", 12: "year"}
    return words.get(months, "year")


# ─────────────────────────────────────────────────────────────────────────────
# Simple moving average helper
# ─────────────────────────────────────────────────────────────────────────────

def _sma(prices: list[float], period: int) -> list[float | None]:
    """Return SMA of *period*; None where fewer than *period* data points exist."""
    result: list[float | None] = []
    for i in range(len(prices)):
        if i + 1 < period:
            result.append(None)
        else:
            result.append(sum(prices[i - period + 1: i + 1]) / period)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Fact detectors — each returns a fact dict or None
# ─────────────────────────────────────────────────────────────────────────────

def _fact_pct_change(
    ticker: str,
    dates: list[str],
    c: list[float],
    window: int,
    window_label: str,
    salience: int,
) -> dict | None:
    """Percentage change over *window* sessions."""
    n = len(c)
    if n < window + 1:
        return None
    prev = c[n - 1 - window]
    curr = c[n - 1]
    if prev <= 0:
        return None
    pct = (curr - prev) / prev * 100
    pct_str = _fmt_pct(pct)
    direction = "up" if pct >= 0 else "down"
    text = f"{ticker} is {direction} {pct_str} over the last {window_label}"
    return {
        "id": f"pct_{window}",
        "text": text,
        "salience": salience,
        "numbers": [pct_str],
    }


#: A "52-week" claim needs a year of bars. 240 (not 252) tolerates the handful
#: of holiday-shortened years and a store that is a few sessions short, while
#: still refusing a 90-bar window pretending to be a year.
_MIN_52W_BARS = 240


def _fact_52w_high_low(
    ticker: str,
    dates: list[str],
    h: list[float],
    l: list[float],
    c: list[float],
) -> list[dict]:
    """Distance from 52-week high/low, and new 52-week high/low detection.

    ONE BASIS PER FACT (2026-07-28 $TSLA incident). Every extreme fact carries a
    ``"basis"`` key ∈ {"close", "intraday"} naming the price series the record
    was DETECTED on, and its wording may only make a claim on that series. The
    TSLA post detected a new 52-week low on ``last_low < w52_low`` — an INTRADAY
    comparison — and the copy came out close-phrased ("down eight weeks in a
    row ... through 306.51"), while the record's own ``last_close`` was 313.03.
    The post asserted a close through a level the stock had not closed through,
    on a chart that showed it. So: a close-basis record says "closed at a new
    52-week high"; an intraday-basis record says "traded up to X intraday" and
    whitelists only the intraday price, so no close-shaped claim has a licensed
    number to stand on. Close basis is checked FIRST because a close record is
    the stronger, less arguable event; the intraday branch only fires when the
    high/low was made but not held into the bell.

    REQUIRES A YEAR OF BARS. This used to take ``window = min(252, n)`` and label
    whatever it found a "52-week" extreme regardless of how much history it was
    handed. The only production caller passed ``n=90``, so every one of these
    facts was a ~4-month extreme wearing a 52-week name — and on the live stores
    that is not a rounding error: MSFT's true 52-week high is 551.05 against a
    90-bar 466.32 (18.2% understated), CDW 18.6%, META 14.9%, TSLA 10.0%.

    The caller now loads 252. This floor is the second line: a fact that cannot
    be TRUE under its own name must not be emitted at all, whatever a future
    caller passes. Emitting nothing is honest; emitting a disprovable claim on
    an account whose product is being right about levels is not.
    """
    n = len(c)
    if n < 20:
        return []

    if n < _MIN_52W_BARS:
        return []

    window = min(252, n)
    # Use only the look-back period (exclude today's bar so today can be a record)
    lookback_h = h[n - window: n - 1]
    lookback_l = l[n - window: n - 1]
    lookback_c = c[n - window: n - 1]
    lookback_dates = dates[n - window: n - 1]

    if not lookback_h or not lookback_l or not lookback_c:
        return []

    # Two extremes per side, one per basis. The intraday pair is the level the
    # market quotes; the close pair is what a "closed at a new high" claim needs.
    w52_high = max(lookback_h)
    w52_low = min(lookback_l)
    w52_high_close = max(lookback_c)
    w52_low_close = min(lookback_c)
    last_close = c[n - 1]
    last_high = h[n - 1]
    last_low = l[n - 1]

    facts: list[dict] = []

    def _since_label(series: list[float], value: float) -> str:
        """"first since" label for the last bar of *series* that set *value*."""
        idx = _last_set_at(series, value)
        if idx < 0:
            return ""
        prior_date = lookback_dates[idx] if idx < len(lookback_dates) else ""
        # Sessions between that bar and today's (today sits one past the slice).
        return _first_since(prior_date, len(series) - idx)

    def _record_fact(fact_id: str, text: str, price_str: str,
                     basis: str, since: str) -> dict:
        if since:
            text = f"{text}, first since {since}"
        # `since` carries a year token ("Jun 2025") into the copy, so it is
        # whitelisted exactly like a price; suppressed clauses whitelist nothing.
        numbers = [price_str] + ([since] if since else [])
        return {"id": fact_id, "text": text, "salience": 10,
                "basis": basis, "numbers": numbers}

    # New 52-week high — CLOSE basis first (the stronger claim), then intraday.
    if last_close > w52_high_close:
        close_str = _fmt_price(last_close)
        facts.append(_record_fact(
            "new_52w_high",
            f"{ticker} closed at a new 52-week high ({close_str})",
            close_str, "close", _since_label(lookback_c, w52_high_close)))
    elif last_high > w52_high:
        high_str = _fmt_price(last_high)
        facts.append(_record_fact(
            "new_52w_high",
            f"{ticker} traded up to {high_str} intraday, a new 52-week high",
            high_str, "intraday", _since_label(lookback_h, w52_high)))
    # New 52-week low — same two-basis ladder.
    elif last_close < w52_low_close:
        close_str = _fmt_price(last_close)
        facts.append(_record_fact(
            "new_52w_low",
            f"{ticker} closed at a new 52-week low ({close_str})",
            close_str, "close", _since_label(lookback_c, w52_low_close)))
    elif last_low < w52_low:
        low_str = _fmt_price(last_low)
        facts.append(_record_fact(
            "new_52w_low",
            f"{ticker} traded down to {low_str} intraday, a new 52-week low",
            low_str, "intraday", _since_label(lookback_l, w52_low)))
    else:
        # Distance from 52-week high
        if w52_high > 0:
            dist_high_pct = (last_close - w52_high) / w52_high * 100
            if abs(dist_high_pct) <= 3.0:
                # Unsigned magnitude + an explicit direction word. "-0.6% off its
                # 52-week high" is a double negative the reader has to resolve
                # (0.6% below? 0.6% short of being 0.6% below?), and it went out
                # verbatim in the 2026-07-26 $AAPL post. Sign lives in the word.
                dist_str = f"{abs(dist_high_pct):.1f}%"
                side = "below" if dist_high_pct < 0 else "above"
                text = (f"{ticker} is {dist_str} {side} its 52-week high "
                        f"({_fmt_price(w52_high)})")
                facts.append({
                    "id": "near_52w_high",
                    "text": text,
                    "salience": 7,
                    # The CITED LEVEL is the intraday high — the number every
                    # quote page prints as "52-week high", and the one a reader
                    # can check. So the fact is intraday-basis and its wording
                    # stays a DISTANCE TO A LEVEL; it must never grow into a
                    # claim about where the stock closed relative to a close
                    # extreme it never measured (the $TSLA basis mix).
                    "basis": "intraday",
                    "numbers": [dist_str, _fmt_price(w52_high)],
                })
        # Distance from 52-week low
        if w52_low > 0:
            dist_low_pct = (last_close - w52_low) / w52_low * 100
            if abs(dist_low_pct) <= 5.0:
                # Same rule as near_52w_high: magnitude unsigned, direction in
                # the word. "+2.1% above" reads as two directions at once.
                dist_str = f"{abs(dist_low_pct):.1f}%"
                side = "above" if dist_low_pct >= 0 else "below"
                text = (f"{ticker} is {dist_str} {side} its 52-week low "
                        f"({_fmt_price(w52_low)})")
                facts.append({
                    "id": "near_52w_low",
                    "text": text,
                    "salience": 7,
                    # Same rule as near_52w_high: intraday level, distance-to-a-
                    # level wording, no close-shaped claim.
                    "basis": "intraday",
                    "numbers": [dist_str, _fmt_price(w52_low)],
                })

    return facts


def _fact_volume_record(
    ticker: str,
    dates: list[str],
    v: list[float],
    window: int = 180,
) -> dict | None:
    """Detect highest daily volume in the look-back window."""
    n = len(v)
    if n < 20:
        return None
    lookback = min(window, n)
    past_v = v[n - lookback: n - 1]  # exclude today
    if not past_v:
        return None
    today_vol = v[n - 1]
    max_past = max(past_v)
    if today_vol <= max_past:
        return None
    # How many months of history is that?
    months = round(lookback / 21)
    avg = sum(past_v) / len(past_v)
    mult = today_vol / avg if avg > 0 else 0
    mult_str = _fmt_mult(mult)
    months_str = f"{months}m" if months < 12 else f"{months // 12}y"
    text = (
        f"{ticker} had its highest daily volume in ~{months_str} today "
        f"({mult_str} its recent average)"
    )
    return {
        "id": "volume_record",
        "text": text,
        "salience": 9,
        "numbers": [mult_str],
    }


def _fact_volume_surge(
    ticker: str,
    dates: list[str],
    v: list[float],
    threshold: float = 2.5,
    avg_window: int = 20,
) -> dict | None:
    """Detect volume surge >= threshold × 20-day average."""
    n = len(v)
    if n < avg_window + 1:
        return None
    past_v = v[n - avg_window - 1: n - 1]
    if not past_v:
        return None
    avg = sum(past_v) / len(past_v)
    today_vol = v[n - 1]
    if avg <= 0 or today_vol / avg < threshold:
        return None
    mult = today_vol / avg
    mult_str = _fmt_mult(mult)
    text = f"{ticker} saw {mult_str} its average volume today"
    return {
        "id": "volume_surge",
        "text": text,
        "salience": 5,
        "numbers": [mult_str],
    }


def _fact_streak(
    ticker: str,
    dates: list[str],
    o: list[float],
    c: list[float],
) -> dict | None:
    """Detect green/red day streaks of 3 or more sessions."""
    n = len(c)
    if n < 3:
        return None

    # Count consecutive green days (close > open) ending at today
    streak_green = 0
    for i in range(n - 1, -1, -1):
        if c[i] > o[i]:
            streak_green += 1
        else:
            break

    # Count consecutive red days (close < open) ending at today
    streak_red = 0
    for i in range(n - 1, -1, -1):
        if c[i] < o[i]:
            streak_red += 1
        else:
            break

    if streak_green >= 3:
        count_str = str(streak_green)
        text = f"{ticker} has closed green {count_str} sessions in a row"
        return {
            "id": "streak_green",
            "text": text,
            "salience": 6,
            "numbers": [count_str],
        }
    if streak_red >= 3:
        count_str = str(streak_red)
        text = f"{ticker} has closed red {count_str} sessions in a row"
        return {
            "id": "streak_red",
            "text": text,
            "salience": 6,
            "numbers": [count_str],
        }
    return None


def _fact_weekly_streak(
    ticker: str,
    dates: list[str],
    c: list[float],
) -> dict | None:
    """Detect 4+ weekly gains or losses by grouping sessions into ISO weeks."""
    n = len(c)
    if n < 20 or not dates:
        return None

    # Group closes by week (ISO week key: YYYY-Www)
    weekly: list[tuple[str, float, float]] = []  # (week_key, open_of_week, close_of_week)
    current_week: str = ""
    week_open: float = 0.0
    week_close: float = 0.0

    for i, d in enumerate(dates):
        try:
            dt = datetime.strptime(d[:10], "%Y-%m-%d")
            iso = dt.isocalendar()
            wk = f"{iso[0]}-W{iso[1]:02d}"
        except Exception:
            continue
        if wk != current_week:
            if current_week:
                weekly.append((current_week, week_open, week_close))
            current_week = wk
            week_open = c[i]
        week_close = c[i]
    if current_week:
        weekly.append((current_week, week_open, week_close))

    if len(weekly) < 4:
        return None

    streak_up = 0
    for _, wo, wc in reversed(weekly):
        if wc > wo:
            streak_up += 1
        else:
            break
    streak_dn = 0
    for _, wo, wc in reversed(weekly):
        if wc < wo:
            streak_dn += 1
        else:
            break

    if streak_up >= 4:
        count_str = str(streak_up)
        text = f"{ticker} has been up {count_str} weeks in a row"
        return {
            "id": "weekly_streak_up",
            "text": text,
            "salience": 6,
            "numbers": [count_str],
        }
    if streak_dn >= 4:
        count_str = str(streak_dn)
        text = f"{ticker} has been down {count_str} weeks in a row"
        return {
            "id": "weekly_streak_dn",
            "text": text,
            "salience": 6,
            "numbers": [count_str],
        }
    return None


def _fact_sma_cross(
    ticker: str,
    dates: list[str],
    c: list[float],
    period: int,
    label: str,
) -> dict | None:
    """Detect first cross above/below a moving average since a named date."""
    n = len(c)
    if n < period + 2:
        return None
    sma = _sma(c, period)
    # Current bar above/below
    if sma[-1] is None or sma[-2] is None:
        return None
    currently_above = c[-1] > sma[-1]
    was_below = c[-2] < sma[-2]
    was_above = c[-2] > sma[-2]

    def _cross_fact(fact_id: str, verb: str, side_test) -> dict:
        """Assemble a cross fact, dating it only when the date is worth having.

        THE SAME DEGENERATE CLAUSE AS THE 52-WEEK FACTS, plus a placeholder.
        The prior-side bar is searched inside this very series, so a name that
        chops around its average produces "reclaimed its 50-day average, first
        time since Jul 2026" two sessions after it lost it — the live $TEL post
        of 2026-07-28. And when no prior bar was found at all, the two branches
        rendered the literal string "a while" INTO THE COPY and into `numbers`,
        so "first time since a while" shipped as a licensed fact. Suppressed
        under `_MIN_SINCE_SESSIONS`, never placeheld.
        """
        prior_date = None
        age = 0
        for i in range(n - 2, -1, -1):
            if sma[i] is not None and side_test(c[i], sma[i]):
                prior_date = dates[i] if i < len(dates) else None
                age = (n - 1) - i
                break
        since_str = _first_since(prior_date, age)
        sma_val = _fmt_price(sma[-1])
        text = f"{ticker} {verb} its {label} ({sma_val})"
        if since_str:
            text = f"{text}, first time since {since_str}"
        return {
            "id": fact_id,
            "text": text,
            "salience": 8,
            # Both the signal (close vs SMA-of-closes) and the wording are
            # close-basis; nothing here may speak about an intraday touch.
            "basis": "close",
            "numbers": [sma_val] + ([since_str] if since_str else []),
        }

    if currently_above and was_below:
        return _cross_fact(f"sma_{period}_reclaim", "reclaimed",
                           lambda close, avg: close > avg)
    if not currently_above and was_above:
        return _cross_fact(f"sma_{period}_loss", "lost",
                           lambda close, avg: close < avg)
    return None


def _fact_biggest_move(
    ticker: str,
    dates: list[str],
    o: list[float],
    c: list[float],
    window: int = 60,
) -> dict | None:
    """Detect biggest single-day percentage move (o→c) in the look-back window."""
    n = len(c)
    if n < 10:
        return None
    lookback = min(window, n - 1)
    # Compute day moves for the lookback window (excluding today)
    past_moves = []
    for i in range(n - lookback - 1, n - 1):
        if o[i] > 0:
            past_moves.append(abs((c[i] - o[i]) / o[i]) * 100)

    if not past_moves:
        return None

    # Today's move
    today_move = abs((c[-1] - o[-1]) / o[-1]) * 100 if o[-1] > 0 else 0
    if today_move <= max(past_moves):
        return None

    months = round(lookback / 21)
    months_str = f"{months}m" if months < 12 else f"{months // 12}y"
    direction = "up" if c[-1] >= o[-1] else "down"
    pct_str = _fmt_pct((c[-1] - o[-1]) / o[-1] * 100)
    text = (
        f"{ticker} moved {pct_str} today, "
        f"its biggest single-day {direction} in ~{months_str}"
    )
    return {
        "id": "biggest_move",
        "text": text,
        "salience": 4,
        "numbers": [pct_str],
    }


def _fact_nr7(
    ticker: str,
    dates: list[str],
    h: list[float],
    l: list[float],
) -> dict | None:
    """NR7: today's range is the narrowest of the last 7 sessions (including today)."""
    n = len(h)
    if n < 7:
        return None
    ranges = [h[i] - l[i] for i in range(n)]
    today_range = ranges[-1]
    # Prior 6 sessions (not including today)
    prior6 = ranges[n - 7: n - 1]
    if not prior6:
        return None
    # Today must be narrower than ALL of the prior 6
    if today_range >= min(prior6):
        return None
    range_str = _fmt_price(today_range)
    text = (
        f"{ticker} is in a tight range today, "
        f"narrowest of the last 7 sessions (range: {range_str})"
    )
    return {
        "id": "nr7",
        "text": text,
        "salience": 3,
        "numbers": [range_str],
    }


# ─────────────────────────────────────────────────────────────────────────────
# M2 detectors — AVWAP + Volume Profile
# ─────────────────────────────────────────────────────────────────────────────

def _fact_avwap_hold(
    ticker: str,
    dates: list[str],
    c: list[float],
    h: list[float],
    l: list[float],
    v: list[float],
) -> dict | None:
    """Detect anchored-VWAP hold streak or recent reclaim.

    Uses engine.indicators_m2 (lazy import). Returns None on any failure.
    Emits at most one of: avwap_hold (salience 6, polarity +1) or avwap_reclaim
    (salience 8, polarity +1).
    """
    try:
        import pandas as pd
        from engine import indicators_m2 as _m2  # lazy — guarded by importorskip in tests
    except Exception:
        return None

    n = len(c)
    if n < 5:
        return None

    try:
        df = pd.DataFrame(
            {"close": c, "high": h, "low": l, "volume": v},
            index=pd.to_datetime(dates),
        )
        lookback = min(63, n - 1)
        anchor_pos = _m2.earnings_proxy_anchor(df, lookback=lookback)
        if anchor_pos is None:
            return None
        anchor_age = n - 1 - anchor_pos
        if anchor_age < 1:
            return None

        anchor_date = df.index[anchor_pos]
        anchor_label = anchor_date.strftime("%b %d")
        # F6: the anchor day (e.g. "26" in "Jun 26", "06" in "May 06") is a numeric
        # token embedded verbatim in the fact text via {anchor_label}. Add the EXACT
        # token that appears (zero-padded strftime("%d"), matching anchor_label) to
        # the fact's numbers list so the copy contract holds exactly. (The validator
        # would otherwise pass it only via its bare 1-2-digit skip.)
        anchor_day_str = anchor_date.strftime("%d")

        avwap_series = _m2.anchored_vwap(df, anchor_pos)
        avwap_vals = list(avwap_series)

        # Warm-up guard: only look at bars where avwap is not NaN
        close_arr = c
        avwap_arr = avwap_vals

        # Check for reclaim: close was below avwap on bar n-2, above on bar n-1
        # Find last valid non-NaN avwap pair at n-1 and n-2
        def _is_valid(v_: object) -> bool:
            return v_ is not None and v_ == v_  # type: ignore[operator]

        cur_close = close_arr[-1]
        cur_avwap = avwap_arr[-1]
        if not _is_valid(cur_avwap):
            return None

        # Look for the bar just before current that has a valid avwap
        prev_close: float | None = None
        prev_avwap: float | None = None
        for i in range(n - 2, -1, -1):
            if _is_valid(avwap_arr[i]):
                prev_close = close_arr[i]
                prev_avwap = float(avwap_arr[i])  # type: ignore[arg-type]
                break

        cur_avwap_f = float(cur_avwap)
        cur_close_f = float(cur_close)

        # Reclaim: was below on prev valid bar, now above (within last 3 sessions)
        if prev_close is not None and prev_avwap is not None:
            was_below = prev_close < prev_avwap
            now_above = cur_close_f > cur_avwap_f
            # Count how many bars since the cross
            bars_since_cross = 0
            for i in range(n - 1, -1, -1):
                if _is_valid(avwap_arr[i]) and close_arr[i] > float(avwap_arr[i]):  # type: ignore[arg-type]
                    bars_since_cross += 1
                else:
                    break
            if was_below and now_above and bars_since_cross <= 3:
                avwap_price = _fmt_price(cur_avwap_f)
                return {
                    "id": "avwap_reclaim",
                    "text": (
                        f"{ticker} closed back above {avwap_price}, the average "
                        f"price paid since the {anchor_label} volume spike"
                    ),
                    "salience": 8,
                    "polarity": 1,
                    # F6: anchor_label (e.g. "Jun 26") embeds the day token "26"
                    # in the fact text; include it in numbers so the copy contract
                    # holds exactly. avwap_price is now IN the text (see the
                    # plain-language note on _fact_avwap_hold) as well as being
                    # the chart overlay label.
                    "numbers": [avwap_price, anchor_day_str],
                }

        # Hold streak: count consecutive sessions above avwap ending at last bar
        if anchor_age >= 10 and cur_close_f > cur_avwap_f:
            streak = 0
            for i in range(n - 1, -1, -1):
                av = avwap_arr[i]
                if not _is_valid(av):
                    break
                if close_arr[i] > float(av):  # type: ignore[arg-type]
                    streak += 1
                else:
                    break
            if streak >= 10:
                count_str = str(streak)
                avwap_price = _fmt_price(cur_avwap_f)
                return {
                    "id": "avwap_hold",
                    "text": (
                        f"{ticker} has held {avwap_price}, the average price paid "
                        f"since the {anchor_label} volume spike, for {count_str} "
                        f"straight sessions"
                    ),
                    # F4: passive "still above" state → streak-tier salience 6
                    # (avwap_reclaim, the ACTIVE cross event, stays at 8).
                    "salience": 6,
                    "polarity": 1,
                    # F6: anchor_label (e.g. "Jun 26") embeds the day token "26";
                    # include it so every numeric token in the text is whitelisted.
                    # avwap_price is whitelisted because it is now IN the text: the
                    # old wording named the LINE but never its PRICE, so a writer
                    # obeying the whitelist could only ever say "watching a close
                    # below it" — a level the reader cannot see (2026-07-26 $AAPL).
                    "numbers": [avwap_price, count_str, anchor_day_str],
                }

    except Exception as _e:
        # F5: fail-soft, but no longer silent — log with ticker context (mirrors
        # chart_render.build_m2_overlays). Behaviour unchanged: returns None.
        log.debug("_fact_avwap_hold: %s failed: %s", ticker, _e)
        return None

    return None


def _fact_poc(
    ticker: str,
    dates: list[str],
    c: list[float],
    h: list[float],
    l: list[float],
    v: list[float],
) -> list[dict]:
    """Detect volume point-of-control facts.

    Uses engine.indicators_m2 (lazy import). Returns [] on any failure.
    May emit: poc_level (salience 5), in_value_area (salience 3),
    poc_retest_hold (salience 7).
    """
    try:
        import pandas as pd
        from engine import indicators_m2 as _m2
    except Exception:
        return []

    n = len(c)
    if n < 5:
        return []

    try:
        df = pd.DataFrame(
            {"close": c, "high": h, "low": l, "volume": v},
            index=pd.to_datetime(dates),
        )
        window = min(126, n)
        profile = _m2.volume_profile(df, window=window)
        if profile is None:
            return []
        # Spelled-out span for the fact text ("six months"), so the reader knows
        # WHICH stretch of tape the level summarises without meeting the words
        # "volume profile". Spelled, never numeric — adds no whitelist token.
        win_label = _window_label(window)

        poc = float(profile["poc"])
        va_low = float(profile["va_low"])
        va_high = float(profile["va_high"])
        last_close = float(c[-1])

        facts: list[dict] = []

        if poc > 0:
            # POC level fact — F3: only emit when price is within ±15% of the POC.
            # A POC computed over a 126-day window can sit 150%+ away from a runaway
            # name's current price (real AMD: "price is 152.3% above it"), which is
            # a stale-reference artefact, not a tradeable level. Gate it out.
            pct_away = (last_close - poc) / poc * 100.0
            if abs(pct_away) <= 15.0:
                poc_str = _fmt_price(poc)
                direction = "above" if pct_away >= 0 else "below"
                # strip sign for clean "X% above" phrasing
                pct_abs_str = f"{abs(pct_away):.1f}%"
                text = (
                    f"{ticker} is {pct_abs_str} {direction} {poc_str}, the price "
                    f"where the most shares changed hands in the past {win_label}"
                )
                facts.append({
                    "id": "poc_level",
                    "text": text,
                    "salience": 5,
                    # F1: +1 if price sits above the POC, -1 if below.
                    "polarity": 1 if pct_away >= 0 else -1,
                    "numbers": [poc_str, pct_abs_str],
                })

            # In value area? (independent of the poc_level gate — price inside the
            # VA band is inherently near the POC, so no extra distance check needed)
            if va_low <= last_close <= va_high:
                va_low_str = _fmt_price(va_low)
                va_high_str = _fmt_price(va_high)
                facts.append({
                    "id": "in_value_area",
                    "text": (
                        f"{ticker} is sitting between {va_low_str} and "
                        f"{va_high_str}, where most of the past {win_label} of "
                        f"volume traded"
                    ),
                    "salience": 3,
                    # F1: neutral — inside the value band is not directional.
                    "polarity": 0,
                    "numbers": [va_low_str, va_high_str],
                })

            # POC retest and hold: low touched within 1% of POC in last 3 sessions
            # and closed back above
            for i in range(max(0, n - 3), n):
                low_i = float(l[i])
                close_i = float(c[i])
                if abs(low_i - poc) / poc <= 0.01 and close_i > poc:
                    poc_retest_str = _fmt_price(poc)
                    facts.append({
                        "id": "poc_retest_hold",
                        "text": (
                            f"{ticker} dipped back to {poc_retest_str}, the "
                            f"most-traded price of the past {win_label}, and held"
                        ),
                        "salience": 7,
                        # F1: a hold above the POC is a bullish structural event.
                        "polarity": 1,
                        "numbers": [poc_retest_str],
                    })
                    break  # emit at most once

        # F7: cap M2 POC facts at 2 per chart, priority
        # poc_retest_hold > poc_level > in_value_area.
        _poc_priority = {"poc_retest_hold": 0, "poc_level": 1, "in_value_area": 2}
        facts.sort(key=lambda f: _poc_priority.get(f["id"], 99))
        facts = facts[:2]

    except Exception as _e:
        # F5: fail-soft, but no longer silent — log with ticker context.
        log.debug("_fact_poc: %s failed: %s", ticker, _e)
        return []

    return facts


# ─────────────────────────────────────────────────────────────────────────────
# Main public function
# ─────────────────────────────────────────────────────────────────────────────

def compute_facts(
    ticker: str,
    dates: list[str],
    o: list[float],
    h: list[float],
    l: list[float],
    c: list[float],
    v: list[float],
) -> dict:
    """Compute chart facts for a ticker from OHLCV arrays.

    Returns:
        {
          "facts": [{"id": str, "text": str, "salience": int, "numbers": [str]}, ...],
          "numbers_whitelist": [str, ...],   # every number that may appear in copy
        }

    Facts are sorted salience-DESC (most remarkable first).
    """
    if not c or len(c) < 2:
        return {"facts": [], "numbers_whitelist": []}

    n = len(c)
    # Ensure all arrays are the same length (pad with last value if needed, fail-safe)
    def _safe(arr: list, default: float) -> list[float]:
        arr = list(arr) if arr else []
        while len(arr) < n:
            arr.append(arr[-1] if arr else default)
        return arr[:n]

    o = _safe(o, c[0])
    h = _safe(h, c[0])
    l = _safe(l, c[0])
    v = _safe(v, 0.0)
    dates_safe = list(dates) if dates else []
    while len(dates_safe) < n:
        dates_safe.append("")

    facts_raw: list[dict] = []

    # Percentage changes
    f = _fact_pct_change(ticker, dates_safe, c, window=5, window_label="week", salience=1)
    if f:
        facts_raw.append(f)
    f = _fact_pct_change(ticker, dates_safe, c, window=20, window_label="4 weeks", salience=2)
    if f:
        facts_raw.append(f)
    f = _fact_pct_change(ticker, dates_safe, c, window=65, window_label="quarter", salience=2)
    if f:
        facts_raw.append(f)

    # 52-week records and proximity
    for f in _fact_52w_high_low(ticker, dates_safe, h, l, c):
        facts_raw.append(f)

    # Volume record and surge (volume record supersedes surge)
    vol_record = _fact_volume_record(ticker, dates_safe, v)
    if vol_record:
        facts_raw.append(vol_record)
    else:
        vol_surge = _fact_volume_surge(ticker, dates_safe, v)
        if vol_surge:
            facts_raw.append(vol_surge)

    # Day and week streaks
    f = _fact_streak(ticker, dates_safe, o, c)
    if f:
        facts_raw.append(f)
    f = _fact_weekly_streak(ticker, dates_safe, c)
    if f:
        facts_raw.append(f)

    # SMA crosses (50-day and 200-day)
    for period, label in ((50, "50-day average"), (200, "200-day average")):
        f = _fact_sma_cross(ticker, dates_safe, c, period, label)
        if f:
            facts_raw.append(f)

    # Biggest single-day move
    f = _fact_biggest_move(ticker, dates_safe, o, c)
    if f:
        facts_raw.append(f)

    # Tight range (NR7)
    f = _fact_nr7(ticker, dates_safe, h, l)
    if f:
        facts_raw.append(f)

    # M2: Anchored VWAP hold / reclaim
    f = _fact_avwap_hold(ticker, dates_safe, c, h, l, v)
    if f:
        facts_raw.append(f)

    # M2: Volume point of control
    for f in _fact_poc(ticker, dates_safe, c, h, l, v):
        facts_raw.append(f)

    # Sort by salience DESC, then id ASC for determinism
    facts_raw.sort(key=lambda x: (-x["salience"], x["id"]))

    # Deduplicate by id (first occurrence wins)
    seen_ids: set[str] = set()
    facts: list[dict] = []
    for f in facts_raw:
        if f["id"] not in seen_ids:
            seen_ids.add(f["id"])
            facts.append(f)

    # Build numbers_whitelist: every number from every fact
    numbers_whitelist: list[str] = []
    seen_nums: set[str] = set()
    for f in facts:
        for num in f.get("numbers", []):
            if num and num not in seen_nums:
                seen_nums.add(num)
                numbers_whitelist.append(num)

    return {"facts": facts, "numbers_whitelist": numbers_whitelist}
