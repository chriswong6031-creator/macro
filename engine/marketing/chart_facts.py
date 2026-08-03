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
  may only claim what that series supports — "closed at a new 52-week CLOSING
  low" for close basis, "traded down to X intraday" for intraday basis. A fact
  detected on one basis and phrased on the other is the 2026-07-28 $TSLA defect
  (an intraday low, close-phrased, contradicted by the record's own last_close).
  The word "closing" is load-bearing in the close-basis wording: an unqualified
  "new 52-week high" names the intraday extreme a quote page prints, which a
  close-basis record has not measured and may be several percent away from.

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
import re
from datetime import date as _date, datetime, timedelta as _timedelta

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
    #
    # "CLOSING high", not "high". The close-basis branch compares last_close to
    # `w52_high_close` — the highest CLOSE of the look-back — and says nothing
    # whatever about `w52_high`, the intraday extreme every quote page prints as
    # "52-week high". Those two routinely differ by several percent: a name whose
    # true 52w high is 320 (an intraday spike) can set a new closing high at 305,
    # and "closed at a new 52-week high (305)" then reads as a claim the reader
    # can falsify in one glance at any quote page. Naming the basis IN THE
    # SENTENCE is the same rule the intraday branch already follows ("traded up
    # to X intraday"); the `basis` key was correct all along, it just never
    # reached the words. This is the $TSLA basis-mix defect wearing the other
    # sign — that one phrased an intraday record as a close, this one phrased a
    # close record as the intraday level.
    #
    # THE LADDER IS if/elif ALL THE WAY DOWN, and on an OUTSIDE-REVERSAL DAY that
    # is a real (unfixed) asymmetry: a bar that both closes above the prior
    # closing high AND trades below the 52-week low emits ONLY the bullish fact,
    # because the first arm matches and the low arms are never evaluated. Noted,
    # not restructured — splitting the ladder changes how many facts a post can
    # carry and which one leads, which is a copy-side decision, not a wording fix.
    if last_close > w52_high_close:
        close_str = _fmt_price(last_close)
        facts.append(_record_fact(
            "new_52w_high",
            f"{ticker} closed at a new 52-week closing high ({close_str})",
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
            f"{ticker} closed at a new 52-week closing low ({close_str})",
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


# ═════════════════════════════════════════════════════════════════════════════
# TrendSpider hardening PR-C — timeframe, stage and attention facts
# ═════════════════════════════════════════════════════════════════════════════
#
# THE FORMING-BAR LAW (PR-A handoff, masterplan §3 PR-C.2).
#
# ``chart_render.resample_bars`` deliberately KEEPS the forming weekly/monthly
# bucket: a chart that hid the current week would hide "you are here", which is
# the whole point of the annotation grammar. ``engine/weinstein_stage.py``
# deliberately DROPS it: a signal computed from a partial bar is a signal about
# a week that has not finished happening.
#
# Facts live on the weinstein side of that split, and nothing in the repo said
# so until now. On a Wednesday, a name's forming week is two days old; if the
# fact layer consumed it, a two-day dip would mint "worst week since 2022" and
# the caption would ship over a chart whose last bar is a stub. By Friday the
# same week can close green. So EVERY fact below is computed on
# ``resample_completed`` output — the resampled series MINUS the forming bucket
# — while the chart the director builds still plots the live bar. The two
# series differ by exactly one bar, on purpose, and the director maps fact
# anchors to chart bars BY DATE so the off-by-one can never silently shift a
# spotlight onto the wrong candle (chart_director._index_of_date).
#
# THE WINDOW CONTRACT (masterplan §0 gate 2, the claim-window law). Every fact
# emitted here carries:
#
#   window_start   ISO date of the OLDEST bar the claim depends on. "Four red
#                  weeks" depends on four weeks; "longest red run in 3 years"
#                  depends on everything back three years, and those are
#                  different windows for the same streak.
#   window_bars    how many bars of the fact's OWN timeframe that window spans.
#   timeframe      DAILY | WEEKLY | MONTHLY — the bars the fact was measured on.
#   claim_kind     which row of the director's doctrine table this fact selects.
#   anchor_dates   bars the chart should point at (touches, record bars, prior
#                  instances) as DATES, never indices.
#
# The director refuses to attach a fact whose ``window_start`` falls outside the
# plotted axis (widen the chart, rescope, or drop the fact). A fact with no
# ``window_start`` is treated as UNBOUNDED and refused outright for superlative
# claim kinds — absent metadata must never read as "the window is fine".

#: Claim kinds — the director's doctrine table is keyed on these.
CLAIM_KINDS: tuple[str, ...] = (
    "level_touch", "streak", "superlative", "analog", "volume_event",
    "breakout", "stage_read", "post_event_drift", "valuation", "context",
)

#: Minimum COMPLETED bars a timeframe fact needs before it may speak at all.
#: PIT law (§0 gate 3): a short history SUPPRESSES the fact — there is no
#: snapshot to fall back to, and 12 weekly bars are not "three years of weekly
#: bars with some missing".
_MIN_TF_BARS: dict[str, int] = {"WEEKLY": 60, "MONTHLY": 36}

#: Plain-word names for the PR-B pools. NO indicator vocabulary, no artifact
#: names, no internal slugs — these strings reach a reader (banned-vocab law).
_ATTENTION_WORDS: dict[str, str] = {
    "retail_attention": "most-talked-about",
    "options_volume": "busiest options tape",
    "dollar_volume": "most-traded",
}

#: Stage flag → (plain-word copy phrase, chart-label idiom). The asymmetry is
#: the law: the COPY says "marking up", the CHART LABEL may say "Stage 2".
_STAGE_WORDS: dict[int, tuple[str, str]] = {
    1: ("building a base", "Stage 1"),
    2: ("marking up", "Stage 2"),
    3: ("stalling out", "Stage 3"),
    4: ("under distribution", "Stage 4"),
}

_STAGE_WHY_RE = re.compile(r"stage\s+(\d)", re.I)

#: Per-process memo for the PR-B pools, keyed by (pool, root, as_of).
#:
#: WHY THIS IS NOT A NICETY. The pool functions are ticker-agnostic — each one
#: reads a whole artifact and ranks it — but the fact functions below are called
#: PER TICKER. ``data/options_flow`` is 383 separate parquet files; charting
#: thirty names a night without this memo re-reads that tree thirty times, three
#: pools deep, on a render budget that is law (~67 min, 4-core-bound). The
#: nightly builds one plan in one process, so the memo lives exactly as long as
#: the answer stays true, and the key carries ``as_of`` so a caller that walks
#: two dates gets two answers rather than the first one twice.
_POOL_CACHE: dict[tuple, list[dict]] = {}


def reset_pool_cache() -> None:
    """Drop the pool memo. For tests that mutate an artifact between calls."""
    _POOL_CACHE.clear()


def _cached_pool(name: str, fn, root: object, as_of: object) -> list[dict]:
    """One pool read per (pool, root, as_of) per process. [] on any failure."""
    key = (name, str(root), str(as_of))
    if key not in _POOL_CACHE:
        try:
            _POOL_CACHE[key] = list(fn(root, as_of=as_of) or [])
        except Exception:  # noqa: BLE001
            _POOL_CACHE[key] = []
    return _POOL_CACHE[key]


def _packet(facts: list[dict]) -> dict:
    """Sort, dedupe by id, and build the numbers whitelist. The packet shape."""
    facts = sorted(facts, key=lambda f: (-int(f.get("salience", 0)), str(f.get("id"))))
    seen: set[str] = set()
    kept: list[dict] = []
    for f in facts:
        fid = str(f.get("id"))
        if fid in seen:
            continue
        seen.add(fid)
        kept.append(f)
    whitelist: list[str] = []
    seen_nums: set[str] = set()
    for f in kept:
        for num in f.get("numbers", []):
            if num and num not in seen_nums:
                seen_nums.add(num)
                whitelist.append(num)
    return {"facts": kept, "numbers_whitelist": whitelist}


def merge_packets(*packets: dict) -> dict:
    """Merge fact packets, keeping the first fact for any repeated id."""
    facts: list[dict] = []
    for p in packets:
        if isinstance(p, dict):
            facts.extend(p.get("facts") or [])
    return _packet(facts)


def _tf_label(timeframe: str) -> tuple[str, str]:
    """('week', 'weeks') / ('month', 'months') for a normalised timeframe."""
    return ("month", "months") if timeframe == "MONTHLY" else ("week", "weeks")


def _years_phrase(bars: int, timeframe: str) -> str:
    """Plain-word span for a bar count on a resampled series.

    Years/months so the sentence reads cold. The only numeral it can produce is
    the year count, and every caller whitelists that token explicitly — a span
    phrase that reaches copy with an unlicensed number is the same defect as
    the "first time since a while" placeholder above.
    """
    per_year = 52 if timeframe == "WEEKLY" else 12
    years = bars / per_year
    if years >= 1.9:
        return f"{int(years)} years"
    if years >= 0.92:
        return "a year"
    months = max(1, round(bars / (per_year / 12.0)))
    return "a month" if months == 1 else f"{months} months"


def _span_numbers(span: str) -> list[str]:
    """The numeric tokens inside a ``_years_phrase`` result, for the whitelist."""
    return [tok for tok in span.split() if tok.isdigit()]


def _years_adj(bars: int, timeframe: str) -> str:
    """``_years_phrase`` in ADJECTIVE form — "12-year", "one-year", "6-month".

    "its 12 years high" is not a sentence a person writes, and the cold-read law
    says a line that only parses because you know what you meant gets rewritten.
    Same window, same whitelist tokens (the hyphenated form still tokenises to
    the bare digits), different grammar.
    """
    span = _years_phrase(bars, timeframe)
    if span == "a year":
        return "one-year"
    if span == "a month":
        return "one-month"
    return span.replace(" years", "-year").replace(" months", "-month")


def bucket_end(iso_date: str, timeframe: str) -> str:
    """The bucket LABEL a daily date resamples into ('' when unparseable).

    Mirrors ``chart_render._bucket_label`` exactly — W-FRI weeks are labelled by
    their Friday, months by their last calendar day — so a fact bucket and a
    chart bucket are the same object. Reimplemented rather than imported
    because this module has no other reason to import the renderer; the two are
    pinned together by tests/test_chart_director.py.
    """
    try:
        d = datetime.strptime(str(iso_date)[:10], "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001
        return ""
    tf = str(timeframe or "DAILY").upper()
    if tf == "WEEKLY":
        return (d + _timedelta(days=(4 - d.weekday()) % 7)).isoformat()
    if tf == "MONTHLY":
        nxt = _date(d.year + (d.month == 12), (d.month % 12) + 1, 1)
        return (nxt - _timedelta(days=1)).isoformat()
    return str(iso_date)[:10]


def resample_completed(
    dates: list[str],
    o: list[float],
    h: list[float],
    l: list[float],
    c: list[float],
    v: list[float],
    timeframe: str,
) -> tuple[list[str], list[float], list[float], list[float], list[float], list[float]]:
    """Daily OHLCV → COMPLETED weekly/monthly bars. The fact layer's series.

    ``chart_render.resample_bars`` with the forming bucket removed. The test is
    exact rather than calendar-guessed: the final bucket is complete only when
    the last DAILY bar in the input reaches that bucket's own end label (its
    Friday, or the month's last day). A Wednesday input therefore drops the week
    it is standing in, which is the point — a Friday-partial week must not mint
    a "worst week" fact.

    Holiday weeks: a week whose Friday is a market holiday ends on Thursday and
    its bucket label is still that Friday, so this drops it as forming. That is
    a one-bar lag on a handful of weeks a year, in the safe direction — a fact
    that arrives a week late is a far smaller defect than a fact minted from a
    bar that has not finished. DAILY passes through untouched.
    """
    from engine.marketing.chart_render import normalize_timeframe, resample_bars

    tf = normalize_timeframe(timeframe)
    res = resample_bars(dates, o, h, l, c, v, tf)
    if tf == "DAILY" or not res[0] or not dates:
        return res
    last_daily = str(dates[-1])[:10]
    last_bucket = str(res[0][-1])[:10]
    if last_daily < last_bucket:
        return tuple(col[:-1] for col in res)  # type: ignore[return-value]
    return res


def _ordinal(n: int) -> str:
    """'3rd' — plain ordinal for a touch count."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }".replace(" ", "")


def _fact_tf_streak(
    ticker: str,
    dates: list[str],
    o: list[float],
    c: list[float],
    timeframe: str,
) -> dict | None:
    """Consecutive same-direction COMPLETED bars, plus a scoped rarity clause.

    TWO WINDOWS, ONE STREAK, and keeping them apart is the whole §0.2 lesson.
    The bare count ("four red weeks in a row") is evidenced by the streak
    itself, so ``window_start`` is the streak's first bar. The rarity clause
    ("its longest run in 3 years") is evidenced by every bar the search covered,
    so when that clause fires ``window_start`` jumps back to the start of the
    search. Conflating them is exactly the failure mode the corpus study caught:
    a 3-year chart carrying a claim measured over 12.
    """
    n = len(c)
    if n < 8:
        return None
    _sing, plur = _tf_label(timeframe)

    up = 0
    for i in range(n - 1, -1, -1):
        if c[i] > o[i]:
            up += 1
        else:
            break
    dn = 0
    for i in range(n - 1, -1, -1):
        if c[i] < o[i]:
            dn += 1
        else:
            break
    streak, direction = (up, "up") if up >= dn else (dn, "down")
    if streak < 3:
        return None

    start_idx = n - streak
    count_str = str(streak)
    word = "green" if direction == "up" else "red"
    text = f"{ticker} has closed {word} {count_str} {plur} in a row"
    numbers = [count_str]
    window_start = str(dates[start_idx])[:10]
    window_bars = streak
    salience = 6
    claim_kind = "streak"

    # Rarity clause — was a run this long seen anywhere earlier in the series?
    prior_max = 0
    run = 0
    for i in range(0, start_idx):
        matched = (c[i] > o[i]) if direction == "up" else (c[i] < o[i])
        run = run + 1 if matched else 0
        prior_max = max(prior_max, run)
    if streak > prior_max and start_idx >= 8:
        span = _years_phrase(start_idx, timeframe)
        text = f"{text}, its longest run in {span}"
        numbers.extend(_span_numbers(span))
        window_start = str(dates[0])[:10]
        window_bars = n
        salience = 8
        claim_kind = "superlative"

    return {
        "id": f"tf_streak_{direction}",
        "text": text,
        "salience": salience,
        "basis": "close",
        "numbers": numbers,
        "timeframe": timeframe,
        "claim_kind": claim_kind,
        "window_start": window_start,
        "window_bars": window_bars,
        "anchor_dates": [str(d)[:10] for d in dates[start_idx:]],
        "streak_len": streak,
        "streak_direction": direction,
        "callout": f"{streak} {word} {plur} in a row",
    }


def _fact_tf_record(
    ticker: str,
    dates: list[str],
    h: list[float],
    l: list[float],
    c: list[float],
    timeframe: str,
) -> dict | None:
    """A COMPLETED bar that closed at the highest/lowest close of the series.

    CLOSE BASIS ONLY. The intraday ladder ``_fact_52w_high_low`` runs is right
    for daily bars a reader can check against a quote page; on a weekly bar the
    intraday extreme belongs to one unnamed session inside the week, and
    "traded up to X" would point at a bar the chart does not draw separately.
    """
    n = len(c)
    if n < 20:
        return None
    prior_c = c[: n - 1]
    if not prior_c:
        return None
    last = c[-1]
    sing, _plur = _tf_label(timeframe)
    span = _years_phrase(n, timeframe)
    numbers = [_fmt_price(last)] + _span_numbers(span)

    if last > max(prior_c):
        text = (f"{ticker} closed the {sing} at its highest level in {span} "
                f"({_fmt_price(last)})")
        fid = "tf_record_high"
        anchor = _last_set_at(prior_c, max(prior_c))
        callout = f"Highest {sing}ly close in {span}"
    elif last < min(prior_c):
        text = (f"{ticker} closed the {sing} at its lowest level in {span} "
                f"({_fmt_price(last)})")
        fid = "tf_record_low"
        anchor = _last_set_at(prior_c, min(prior_c))
        callout = f"Lowest {sing}ly close in {span}"
    else:
        return None

    anchors = [str(dates[-1])[:10]]
    # The PRIOR record only counts as a second disc when it is far enough back
    # to read as a separate event. A record broken two bars ago produces two
    # overlapping circles and says nothing (measured on the 2026-08 AMZN/KO/JPM
    # monthly proofs — same trap as the analog gap rule above).
    if anchor >= 0 and (len(prior_c) - anchor) >= _MIN_ANALOG_GAP_BARS:
        anchors.insert(0, str(dates[anchor])[:10])
    return {
        "id": fid,
        "text": text,
        "salience": 9,
        "basis": "close",
        "numbers": numbers,
        "timeframe": timeframe,
        "claim_kind": "superlative",
        "window_start": str(dates[0])[:10],
        "window_bars": n,
        "anchor_dates": anchors,
        "level": round(float(last), 4),
        "callout": callout,
    }


def _fact_tf_volume_record(
    ticker: str,
    dates: list[str],
    v: list[float],
    timeframe: str,
) -> dict | None:
    """Heaviest COMPLETED weekly/monthly volume of the series (volume event)."""
    n = len(v)
    if n < 20:
        return None
    prior = v[: n - 1]
    if not prior or max(prior) <= 0 or v[-1] <= max(prior):
        return None
    sing, _plur = _tf_label(timeframe)
    span = _years_phrase(n, timeframe)
    return {
        "id": "tf_volume_record",
        "text": f"{ticker} traded its heaviest {sing} of volume in {span}",
        "salience": 9,
        "numbers": _span_numbers(span),
        "timeframe": timeframe,
        "claim_kind": "volume_event",
        "window_start": str(dates[0])[:10],
        "window_bars": n,
        "anchor_dates": [str(dates[-1])[:10]],
        # SCOPED TO THE WINDOW THE FACT MEASURED — "in 3 years", never "ever"
        # (masterplan §1.3, the superlative-wider-than-the-axis failure).
        "callout": f"Heaviest {sing} of volume in {span}",
    }


#: How close a bar has to come to a moving average to count as a TOUCH — 1.5%
#: of the average's own value. Tight enough that a bar merely in the
#: neighbourhood is not counted, loose enough that a gap-and-reclaim is.
_MA_TOUCH_TOL = 0.012

#: Bars within which two tags of the average are ONE visit.
_MA_TOUCH_MERGE_BARS = 5

#: Bars a prior instance must sit BEHIND the last bar to count as a PRECEDENT
#: rather than as part of the event happening right now.
_MIN_ANALOG_GAP_BARS = 8

#: Most touches an "Nth touch" claim may carry — see the gate in
#: :func:`_fact_ma_touches` for why the ceiling matters more than the floor.
_MA_TOUCH_MAX = 6


def _fact_ma_touches(
    ticker: str,
    dates: list[str],
    h: list[float],
    l: list[float],
    c: list[float],
    period: int,
    label: str,
    timeframe: str,
    *,
    lookback: int,
) -> dict | None:
    """Count touches of ONE moving average inside an EXPLICIT window.

    THE WINDOW IS AN ARGUMENT, NOT A BY-PRODUCT. "Third touch of the 200-day"
    is only true relative to a stated stretch of tape, and the version of this
    claim that counts over "however many bars the caller happened to load" is
    the one the corpus study caught asserting a base rate its own chart could
    not show. ``lookback`` IS the window, ``window_start`` reports it, and the
    director refuses the fact when that start is off the plotted axis.

    Touch = the bar's LOW came within tolerance of the average while its close
    stayed above (support), or the mirror image for resistance. The discs the
    director draws sit on exactly those bars, so the count and the picture are
    the same object — an in-frame base rate the reader can recount.
    """
    n = len(c)
    if n < period + 10:
        return None
    sma = _sma(c, period)
    if sma[-1] is None or float(sma[-1]) <= 0:
        return None
    start = max(period - 1, n - lookback)
    if n - start < 10:
        return None

    above = c[-1] > float(sma[-1])
    touches: list[int] = []
    for i in range(start, n):
        avg = sma[i]
        if avg is None or avg <= 0:
            continue
        if above:
            if abs(l[i] - avg) / avg <= _MA_TOUCH_TOL and c[i] >= avg:
                touches.append(i)
        elif abs(h[i] - avg) / avg <= _MA_TOUCH_TOL and c[i] <= avg:
            touches.append(i)
    # Collapse NEARBY bars — a week spent sitting ON the average is ONE visit,
    # and counting it as five is how a "fifth touch" claim inflates itself into
    # a number the chart cannot show. The window is _MA_TOUCH_MERGE_BARS wide,
    # not "adjacent", because price rarely tags an average on consecutive bars:
    # it tags, pops, and comes back two days later, which is one visit to a
    # reader looking at the picture.
    merged: list[int] = []
    for i in touches:
        if merged and i - merged[-1] <= _MA_TOUCH_MERGE_BARS:
            merged[-1] = i
            continue
        merged.append(i)
    # The claim is about NOW: the newest touch has to be the current bar or
    # essentially it. An old cluster of touches is history, not a post.
    if len(merged) < 2 or merged[-1] < n - 3:
        return None
    # AND AN UPPER BOUND, which matters more than the lower one. Past ~6 the
    # "Nth touch" framing stops being a base rate and becomes a description of
    # a name that simply lives on its average: AAPL prints an 8th touch of the
    # 50-day, META a 14th, AMD a 13th, and a chart carrying fourteen discs is
    # the clutter the grammar exists to refuse (§1.1). The honest post for
    # those names is a different fact, not a weaker version of this one.
    if len(merged) > _MA_TOUCH_MAX:
        return None

    count_str = str(len(merged))
    avg_str = _fmt_price(float(sma[-1]))
    side = "found buyers at" if above else "was turned away at"
    span = (_years_adj(n - start, timeframe) + " stretch" if timeframe != "DAILY"
            else "past " + _window_label(n - start))
    text = (f"{ticker} {side} its {label} ({avg_str}) for the "
            f"{_ordinal(len(merged))} time in the {span}")
    return {
        "id": f"ma_touch_{period}",
        "text": text,
        "salience": 8,
        "basis": "intraday",
        "numbers": [count_str, avg_str] + _span_numbers(span),
        "timeframe": timeframe,
        "claim_kind": "level_touch",
        "window_start": str(dates[start])[:10],
        "window_bars": n - start,
        "anchor_dates": [str(dates[i])[:10] for i in merged],
        "ma": {"kind": "sma", "length": period},
        "level": round(float(sma[-1]), 4),
        # 2-6 words, in the disc's own colour (§1.1 callout budget). The
        # average itself is inline-labelled by the renderer, so the disc says
        # what is happening AT it, not what it is.
        "callout": f"{_ordinal(len(merged))} visit",
    }


def _fact_multi_year_level(
    ticker: str,
    dates: list[str],
    h: list[float],
    l: list[float],
    c: list[float],
    timeframe: str,
) -> dict | None:
    """Price within 4% of a multi-year high/low set on COMPLETED bars.

    The ANALOG row of the doctrine table: the reader is being shown "we have
    stood here before", and the prior instances are the anchors the director
    spotlights in blue-grey with a gold disc on now.
    """
    n = len(c)
    if n < 40:
        return None
    prior_h = h[: n - 1]
    prior_l = l[: n - 1]
    if not prior_h or not prior_l:
        return None
    last = c[-1]
    span = _years_phrase(n, timeframe)

    for level, kind in ((max(prior_h), "high"), (min(prior_l), "low")):
        if level <= 0:
            continue
        dist = abs(last - level) / level * 100.0
        if dist > 4.0:
            continue
        series = prior_h if kind == "high" else prior_l
        hits = [i for i in range(len(series))
                if series[i] > 0 and abs(series[i] - level) / level <= 0.02]
        # SEPARATE INSTANCES, not adjacent bars. A three-week stall at the high
        # is ONE prior visit; drawn as three discs it is one smudge and a count
        # the reader cannot recount, which is the opposite of what the discs are
        # for. Same merge rule as the moving-average touches above.
        spread: list[int] = []
        for i in hits:
            if spread and i - spread[-1] <= _MA_TOUCH_MERGE_BARS:
                spread[-1] = i
                continue
            spread.append(i)
        # AN ANALOG NEEDS A PRECEDENT, and a precedent has to be OLD enough to
        # read as history at the chart's own scale. AMZN's 12-year monthly high
        # was set three bars ago: "we have stood here before" is true of last
        # quarter, which is not the sentence the chart would be making, and the
        # two discs literally overlapped in the 2026-08 proof render. So the
        # claim kind is decided by whether separated PRIOR instances survive:
        # two or more and this is an analog with spotlights on each; fewer and
        # it is an ordinary level-proximity fact with one gold disc and a tag.
        prior = [i for i in spread if i <= len(series) - 1 - _MIN_ANALOG_GAP_BARS]
        anchors = [str(dates[i])[:10] for i in prior]
        # SPOTLIGHT BUDGET (§1.1): the two oldest instances plus the most
        # recent tell the story; nine discs are clutter.
        if len(anchors) > 3:
            anchors = anchors[:2] + anchors[-1:]
        claim_kind = "analog" if len(anchors) >= 2 else "level_touch"
        dist_str = f"{dist:.1f}%"
        lvl_str = _fmt_price(level)
        adj = _years_adj(n, timeframe)
        return {
            "id": f"multi_year_{kind}",
            "text": f"{ticker} is {dist_str} from {lvl_str}, its {adj} {kind}",
            "salience": 8,
            "basis": "intraday",
            "numbers": [dist_str, lvl_str] + _span_numbers(span),
            "timeframe": timeframe,
            "claim_kind": claim_kind,
            "window_start": str(dates[0])[:10],
            "window_bars": n,
            "anchor_dates": anchors + [str(dates[-1])[:10]],
            "level": round(float(level), 4),
            "callout": f"{adj} {kind}",
        }
    return None


def compute_timeframe_facts(
    ticker: str,
    dates: list[str],
    o: list[float],
    h: list[float],
    l: list[float],
    c: list[float],
    v: list[float],
    *,
    timeframe: str = "WEEKLY",
) -> dict:
    """Weekly/monthly facts from DAILY bars, computed on COMPLETED buckets only.

    Takes the same daily split-adjusted series the chart plots (§0 gate 3) and
    resamples it HERE rather than accepting pre-resampled input, so no caller
    can hand this function a series whose forming bar has already been baked in.

    Returns the standard packet with every fact carrying the window contract
    documented at the top of this section. Returns an EMPTY packet on short
    history: PIT law, no snapshot fallback.
    """
    from engine.marketing.chart_render import normalize_timeframe

    tf = normalize_timeframe(timeframe)
    if tf == "DAILY":
        return {"facts": [], "numbers_whitelist": []}
    rd, ro, rh, rl, rc, rv = resample_completed(dates, o, h, l, c, v, tf)
    if len(rc) < _MIN_TF_BARS[tf]:
        return {"facts": [], "numbers_whitelist": []}

    candidates = [
        _fact_tf_streak(ticker, rd, ro, rc, tf),
        _fact_tf_record(ticker, rd, rh, rl, rc, tf),
        _fact_tf_volume_record(ticker, rd, rv, tf),
        _fact_multi_year_level(ticker, rd, rh, rl, rc, tf),
    ]
    if tf == "WEEKLY":
        # The 30-week average is the stage classifier's own line, so a weekly
        # touch fact and a stage read draw the SAME curve (§3 stage read row).
        candidates.append(
            _fact_ma_touches(ticker, rd, rh, rl, rc, 30, "30-week average", tf,
                             lookback=min(len(rc), 156)))
    return _packet([f for f in candidates if f])


def compute_daily_level_facts(
    ticker: str,
    dates: list[str],
    o: list[float],
    h: list[float],
    l: list[float],
    c: list[float],
    v: list[float],
    *,
    lookback: int = 252,
) -> dict:
    """Daily MA-touch counts, window-scoped. The level-touch doctrine row.

    Returns AT MOST ONE fact. Two MA facts on one chart is the two-average
    chart the grammar forbids, arriving through the fact layer instead of
    through the renderer — so the tie is broken here rather than left for the
    director to notice.
    """
    out: list[dict] = []
    for period, label in ((50, "50-day average"), (200, "200-day average")):
        f = _fact_ma_touches(ticker, dates, h, l, c, period, label, "DAILY",
                             lookback=lookback)
        if f:
            out.append(f)
    out.sort(key=lambda f: (-int(f["salience"]), -int(f["ma"]["length"])))
    return _packet(out[:1])


# ─────────────────────────────────────────────────────────────────────────────
# Stage + attention context (PR-B pools ONLY)
# ─────────────────────────────────────────────────────────────────────────────
#
# STAGE READS COME FROM THE POOLS, NEVER FROM ``radar_internal._feed_stage``.
# Both read the same backfill parquet; only the pool has the freshness gate.
# The backfill is a WEEKLY artifact and was stuck at 2026-07-17 when this
# shipped, so ``stage2_leaders()`` legitimately returns [] most days and a
# separate collector fix is in flight. That empty list IS the gate working:
# this module then emits no stage fact and NEVER reconstructs one from the
# ungated read. A stage label is a claim about what a name is doing right now,
# and a month-old snapshot cannot make it.
#
# PLAIN WORDS IN THE COPY, the public idiom on the CHART: the fact text says
# "marking up" / "under distribution", while the director puts "Stage 2" in the
# chart callout, where indicator vocabulary is allowed (§0 gate 5).


def _stage_flag_from_why(why: str) -> int | None:
    """The stage number a pool row's ``why`` sentence states, or None.

    The pools are the contract, and their ``why`` is a sentence, so this reads
    that instead of reaching back into the parquet for a column the pool
    already summarised. ``stage2_leaders`` rows are stage 2 by construction;
    ``stage_transitions`` rows spell "stage 3 to 2", and the LAST match is the
    current one.
    """
    matches = _STAGE_WHY_RE.findall(str(why or ""))
    if not matches:
        return None
    try:
        flag = int(matches[-1])
    except (TypeError, ValueError):
        return None
    return flag if flag in _STAGE_WORDS else None


def compute_stage_facts(ticker: str, root: object, *, as_of: object = None) -> dict:
    """Weinstein stage context for ONE ticker, via the PR-B pools only.

    Returns an EMPTY packet — not a guess, not a stale read — when the pools are
    empty or the ticker is not in them. Never raises.
    """
    tkr = str(ticker or "").upper()
    if not tkr:
        return {"facts": [], "numbers_whitelist": []}
    try:
        from engine.marketing import attention_source as _asrc
    except Exception:  # noqa: BLE001
        return {"facts": [], "numbers_whitelist": []}

    row: dict | None = None
    transition = False
    try:
        for r in _cached_pool("stage_transitions", _asrc.stage_transitions, root, as_of):
            if str(r.get("ticker") or "").upper() == tkr:
                row, transition = r, True
                break
        if row is None:
            for r in _cached_pool("stage2_leaders", _asrc.stage2_leaders, root, as_of):
                if str(r.get("ticker") or "").upper() == tkr:
                    row = r
                    break
    except Exception:  # noqa: BLE001
        return {"facts": [], "numbers_whitelist": []}
    if row is None:
        return {"facts": [], "numbers_whitelist": []}

    flag = _stage_flag_from_why(row.get("why", ""))
    if flag is None and not transition:
        flag = 2  # stage2_leaders rows are stage 2 by construction
    if flag is None:
        return {"facts": [], "numbers_whitelist": []}
    plain, chart_label = _STAGE_WORDS[flag]
    verb = "has moved into" if transition else "has been"
    fact = {
        "id": "stage_read",
        "text": f"{tkr} {verb} {plain} on the weekly chart",
        "salience": 7,
        "numbers": [],
        "timeframe": "WEEKLY",
        "claim_kind": "stage_read",
        # A stage read is a claim about the last 30 WEEKS of tape (the
        # classifier's own average), so the chart has to show them. There is no
        # dated evidence bar to point at, so the window is expressed in bars and
        # the director widens the axis to cover them or drops the fact.
        "window_start": "",
        "window_bars": 30,
        "anchor_dates": [],
        "callout": chart_label,
        "ma": {"kind": "sma", "length": 30},
        "asof": str(row.get("asof") or "")[:10],
        "why": str(row.get("why") or ""),
        "source": str(row.get("source") or "stage_analysis"),
    }
    return _packet([fact])


def compute_attention_facts(ticker: str, root: object, *, as_of: object = None) -> dict:
    """Where a name sits in tonight's attention/options pools. Display tier.

    CONTEXT, never a claim about price. These facts exist so a caption can say
    why a name is on the desk tonight without the writer inventing a reason;
    they carry ``claim_kind="context"`` and the director never builds a chart
    AROUND one. Fail-soft and pool-gated: an empty pool yields no fact.
    """
    tkr = str(ticker or "").upper()
    if not tkr:
        return {"facts": [], "numbers_whitelist": []}
    try:
        from engine.marketing import attention_source as _asrc
    except Exception:  # noqa: BLE001
        return {"facts": [], "numbers_whitelist": []}

    out: list[dict] = []
    lanes = (
        ("retail_attention", _asrc.retail_attention, 4),
        ("options_volume", _asrc.top_by_options_volume, 3),
        ("dollar_volume", _asrc.top_by_dollar_volume, 2),
    )
    for fid, fn, salience in lanes:
        rows = _cached_pool(fid, fn, root, as_of)
        for r in rows:
            if str(r.get("ticker") or "").upper() != tkr:
                continue
            try:
                rank_i = int(r.get("rank"))
            except (TypeError, ValueError):
                break
            asof = str(r.get("asof") or "")[:10]
            out.append({
                "id": f"attention_{fid}",
                "text": f"{tkr} is #{rank_i} on our {_ATTENTION_WORDS[fid]} list today",
                "salience": salience,
                # Ranks under 100 are bare 1-2 digit integers, which the copy
                # validator already exempts; whitelisting only the wider ones
                # keeps the list free of tokens nothing needed licensing for.
                "numbers": [str(rank_i)] if rank_i >= 100 else [],
                "timeframe": "DAILY",
                "claim_kind": "context",
                "window_start": asof,
                "window_bars": 1,
                "anchor_dates": [],
                "asof": asof,
                "why": str(r.get("why") or ""),
                "source": str(r.get("source") or ""),
            })
            break
    return _packet(out)
