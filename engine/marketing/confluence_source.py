"""engine.marketing.confluence_source — Confluence-fired signal sourcing for Content Studio.

Reads site/factordata/tech_confluence.json and surfaces currently-firing high-win-rate
signal combos as postable signal candidates for the Marketing Content Studio (§3 of the
MARKETING_TRENDSPIDER_PLAYBOOK_AND_CHART_ENGINE_BY_FABLE.md).

Public API:
    load_confluence(root) -> dict | None
    fired_combo_signals(conf, *, side, top_n, min_edge, max_age_days, today) -> list[dict]
    win_rate_hook(sig) -> (headline, body)
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Words that must NEVER appear in public-facing copy (the hook model rule from §1).
# We keep indicator names out of the public post body — "signal stack" is the public term.
_FORBIDDEN_INDICATOR_WORDS = frozenset({
    "macd", "rsi", "stochastic", "ema", "sma", "bollinger", "atr",
    "adx", "dmi", "obv", "cmf", "vwap", "ichimoku", "keltner",
    "donchian", "connors", "ttm", "squeeze", "choppiness", "bbwp",
})

# Path inside the repo root
_CONFLUENCE_REL = Path("site") / "factordata" / "tech_confluence.json"


def load_confluence(root: Path | str | None = None) -> dict | None:
    """Load tech_confluence.json fail-soft.

    Returns the parsed dict, or None if the file is missing, empty, or unparseable.
    """
    try:
        r = Path(root) if root is not None else Path(".")
        path = r / _CONFLUENCE_REL
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return None
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return None


def _parse_date(s: Any) -> date | None:
    """Parse a YYYY-MM-DD string to a date. Returns None on any failure."""
    try:
        parts = str(s)[:10].split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:  # noqa: BLE001
        return None


def _score(combo: dict) -> float:
    """Ranking score: geometric blend of edge_wr_test and h21.wr_mc_test.

    edge_wr_test is the out-of-sample edge over a naive 50% baseline (already
    positive-only for quality combos). h21.wr_mc_test is the month-1 win rate
    on the test split. We blend them as sqrt(edge * wr_mc_test) — both must be
    positive to earn a score. Deterministic.
    """
    edge = combo.get("edge_wr_test") or 0.0
    h21 = combo.get("h21") or {}
    wr = h21.get("wr_mc_test") or 0.0
    if edge <= 0 or wr <= 0:
        return 0.0
    return math.sqrt(edge * wr)


def fired_combo_signals(
    conf: dict,
    *,
    side: str = "long",
    top_n: int = 8,
    min_edge: float = 0.05,
    max_age_days: int = 10,
    today: str | None = None,
) -> list[dict]:
    """Return currently-firing combos ranked by edge×win-rate blend.

    Filters:
    - active_now must be non-empty (combo firing right now)
    - edge_wr_test >= min_edge
    - last_fire within max_age_days of today (freshness gate — same spirit as
      is_postable_signal in content_studio.py)

    Deduplication: one combo per ticker (the highest-scoring combo wins).
    Ordering: stable sort by score DESC then combo id ASC (deterministic).

    Returns up to top_n dicts, each:
    {
        ticker, combo_id, combo_name, win_rate (h21 wr_mc_test as %),
        edge (pp = edge_wr_test * 100), n_fires, fires_last3y, last_fire,
        legs_plain: [display_en of each leg], side,
    }
    """
    if not isinstance(conf, dict):
        return []

    legs_catalog = conf.get("legs") or []
    combos = (conf.get("combos") or {}).get(side, []) or []

    # Resolve today
    if today:
        today_date = _parse_date(today)
    else:
        today_date = datetime.now(timezone.utc).date()
    if today_date is None:
        return []

    # Collect candidates: all combos with active_now and passing filters
    candidates: list[tuple[float, str, str, dict]] = []
    # (score, combo_id, ticker, combo)
    for combo in combos:
        active = combo.get("active_now") or []
        if not active:
            continue

        edge = combo.get("edge_wr_test") or 0.0
        if edge < min_edge:
            continue

        last_fire_date = _parse_date(combo.get("last_fire"))
        if last_fire_date is None:
            continue
        age = (today_date - last_fire_date).days
        if age < 0 or age > max_age_days:
            continue

        sc = _score(combo)
        combo_id = combo.get("id", "")

        for ticker in active:
            candidates.append((sc, combo_id, ticker, combo))

    # Stable sort: score DESC, then combo_id ASC (deterministic tiebreak)
    candidates.sort(key=lambda x: (-x[0], x[1]))

    # Dedupe: one combo per ticker (first = best score for that ticker)
    seen_tickers: set[str] = set()
    results: list[dict] = []

    for sc, combo_id, ticker, combo in candidates:
        if ticker in seen_tickers:
            continue
        if len(results) >= top_n:
            break
        seen_tickers.add(ticker)

        h21 = combo.get("h21") or {}
        wr_mc_test = h21.get("wr_mc_test") or 0.0
        n_test = h21.get("n_test") or 0
        months_test = h21.get("months_test") or 0
        # Recompute edge from THIS combo (outer-loop `edge` variable is the last
        # filtered combo, not the current dedupe combo — avoid the closure bug).
        combo_edge = combo.get("edge_wr_test") or 0.0

        # Map leg indices to display_en names (plain words — no raw signal ids)
        leg_indices = combo.get("legs") or []
        legs_plain: list[str] = []
        for idx in leg_indices:
            if 0 <= idx < len(legs_catalog):
                legs_plain.append(legs_catalog[idx].get("display_en", ""))

        results.append({
            "ticker": ticker,
            "combo_id": combo_id,
            "combo_name": combo.get("name_en", combo_id),
            "win_rate": round(wr_mc_test * 100, 1),
            "edge": round(combo_edge * 100, 1),
            "n_fires": combo.get("n_fires") or 0,
            "fires_last3y": combo.get("fires_last3y") or 0,
            "last_fire": str(combo.get("last_fire", ""))[:10],
            "first_fire": str(combo.get("first_fire", ""))[:10],
            "legs_plain": legs_plain,
            "side": side,
            "n_test": n_test,
            "months_test": months_test,
            "_score": sc,
        })

    return results


def win_rate_hook(sig: dict) -> tuple[str, str]:
    """Build a reach-optimized, HONEST, plain-word (headline, body) for a fired combo.

    Rules (from playbook §1 + §3):
    - WIN-RATE number is the hook.
    - No raw indicator names in PUBLIC copy ("signal stack", never "MACD"/"RSI"/etc).
    - Carry a cashtag ($TICKER).
    - Include honest disclosure ("historical, not a guarantee").
    - We'll grade this one publicly (receipts culture).
    """
    ticker = sig.get("ticker", "")
    cashtag = f"${ticker}" if ticker else ""
    win_rate = sig.get("win_rate", 0.0)
    n_fires = sig.get("n_fires", 0)
    fires_last3y = sig.get("fires_last3y", 0)
    last_fire = sig.get("last_fire", "")
    side = sig.get("side", "long")
    months_test = sig.get("months_test", 0)
    n_test = sig.get("n_test", 0)

    # Observation span for plain-word copy: full history from first_fire to last_fire
    # (the honest window the combo has actually been observed over — NOT the test-half
    # months, which understates it and produced "over the last 1 years").
    first_fire = sig.get("first_fire", "")
    span_years = 0
    fd, ld = _parse_date(first_fire), _parse_date(last_fire)
    if fd and ld and ld >= fd:
        span_years = int(round((ld - fd).days / 365.25))
    if span_years >= 2:
        span_phrase = f"over the past {span_years} years"
    elif span_years == 1:
        span_phrase = "over the past year"
    else:
        span_phrase = "across its history"

    direction_word = "higher" if side == "long" else "lower"
    win_rate_str = f"{win_rate:.0f}%"

    headline = (
        f"{cashtag} just triggered a setup that's historically worked "
        f"{win_rate_str} of the time"
    )

    # Body: win-rate stat named, historical framing, disclosure, cashtag, grade pledge
    body = (
        f"This signal stack has resolved {direction_word} {win_rate_str} of the time at "
        f"the ~1-month mark {span_phrase} "
        f"({n_fires} historical fires"
        + (f", {fires_last3y} in the last 3 years" if fires_last3y else "")
        + "). "
        f"Historical, not a guarantee — we'll grade this one publicly. {cashtag}"
    )

    return headline, body
