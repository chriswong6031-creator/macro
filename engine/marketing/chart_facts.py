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
   8: first reclaim/loss of key moving average since a named date
   7: 52-week high/low proximity (within 3%)
   6: 5+ session streak (green or red)
   5: volume surge (>=2.5× average)
   4: biggest single-day move in >=60 sessions
   3: tight range (NR7-style compression)
   2: percentage change (4w, 13w)
   1: percentage change (1w)
"""
from __future__ import annotations

import math
from datetime import datetime


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


def _fact_52w_high_low(
    ticker: str,
    dates: list[str],
    h: list[float],
    l: list[float],
    c: list[float],
) -> list[dict]:
    """Distance from 52-week high/low, and new 52-week high/low detection."""
    n = len(c)
    if n < 20:
        return []

    window = min(252, n)
    # Use only the look-back period (exclude today's bar so today can be a record)
    lookback_h = h[n - window: n - 1]
    lookback_l = l[n - window: n - 1]
    lookback_dates = dates[n - window: n - 1]

    if not lookback_h or not lookback_l:
        return []

    w52_high = max(lookback_h)
    w52_low = min(lookback_l)
    last_close = c[n - 1]
    last_high = h[n - 1]
    last_low = l[n - 1]

    facts: list[dict] = []

    # New 52-week high?
    if last_high > w52_high:
        # Find when the last 52w high was set
        prev_52w_idx = lookback_h.index(w52_high) if w52_high in lookback_h else -1
        if prev_52w_idx >= 0:
            since_str = _month_year(lookback_dates[prev_52w_idx])
            text = f"{ticker} hit a new 52-week high — first since {since_str}"
        else:
            text = f"{ticker} hit a new 52-week high"
        price_str = _fmt_price(last_high)
        facts.append({
            "id": "new_52w_high",
            "text": text,
            "salience": 10,
            "numbers": [price_str],
        })
    # New 52-week low?
    elif last_low < w52_low:
        prev_52w_idx = lookback_l.index(w52_low) if w52_low in lookback_l else -1
        if prev_52w_idx >= 0:
            since_str = _month_year(lookback_dates[prev_52w_idx])
            text = f"{ticker} hit a new 52-week low — first since {since_str}"
        else:
            text = f"{ticker} hit a new 52-week low"
        price_str = _fmt_price(last_low)
        facts.append({
            "id": "new_52w_low",
            "text": text,
            "salience": 10,
            "numbers": [price_str],
        })
    else:
        # Distance from 52-week high
        if w52_high > 0:
            dist_high_pct = (last_close - w52_high) / w52_high * 100
            if abs(dist_high_pct) <= 3.0:
                dist_str = _fmt_pct(dist_high_pct)
                text = f"{ticker} is {dist_str} off its 52-week high ({_fmt_price(w52_high)})"
                facts.append({
                    "id": "near_52w_high",
                    "text": text,
                    "salience": 7,
                    "numbers": [dist_str, _fmt_price(w52_high)],
                })
        # Distance from 52-week low
        if w52_low > 0:
            dist_low_pct = (last_close - w52_low) / w52_low * 100
            if abs(dist_low_pct) <= 5.0:
                dist_str = _fmt_pct(dist_low_pct)
                text = f"{ticker} is {dist_str} above its 52-week low ({_fmt_price(w52_low)})"
                facts.append({
                    "id": "near_52w_low",
                    "text": text,
                    "salience": 7,
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

    if currently_above and was_below:
        # Just crossed above — find last time it was above before this
        last_above_date = None
        for i in range(n - 2, -1, -1):
            if sma[i] is not None and c[i] > sma[i]:
                last_above_date = dates[i] if i < len(dates) else None
                break
        since_str = _month_year(last_above_date) if last_above_date else "a while"
        sma_val = _fmt_price(sma[-1])
        text = (
            f"{ticker} reclaimed its {label} ({sma_val}) — "
            f"first time since {since_str}"
        )
        return {
            "id": f"sma_{period}_reclaim",
            "text": text,
            "salience": 8,
            "numbers": [sma_val, since_str],
        }
    if not currently_above and was_above:
        # Just crossed below
        last_below_date = None
        for i in range(n - 2, -1, -1):
            if sma[i] is not None and c[i] < sma[i]:
                last_below_date = dates[i] if i < len(dates) else None
                break
        since_str = _month_year(last_below_date) if last_below_date else "a while"
        sma_val = _fmt_price(sma[-1])
        text = (
            f"{ticker} lost its {label} ({sma_val}) — "
            f"first time since {since_str}"
        )
        return {
            "id": f"sma_{period}_loss",
            "text": text,
            "salience": 8,
            "numbers": [sma_val, since_str],
        }
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
        f"{ticker} moved {pct_str} today — "
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
        f"{ticker} is in a tight range today — "
        f"narrowest of the last 7 sessions (range: {range_str})"
    )
    return {
        "id": "nr7",
        "text": text,
        "salience": 3,
        "numbers": [range_str],
    }


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
