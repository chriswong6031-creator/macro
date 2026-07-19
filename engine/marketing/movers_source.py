"""engine.marketing.movers_source — Heatmap-backed data source for mover/theme posts.

Reads site/marketdata/sp500_heatmap.json and site/marketdata/themes_heatmap.json
to produce structured data for `mover` and `theme_list` content types.

Public API:
    load_movers(root) -> dict | None
    top_movers(data, *, tf, n, min_abs) -> {gainers, losers}
    theme_lists(data, *, tf, n, min_members, min_abs_theme) -> list[dict]
    mover_facts(mover, data) -> {facts, numbers_whitelist}
    theme_facts(theme_item) -> {facts, numbers_whitelist}

All functions are deterministic and fail-soft (return None / empty on errors).
No invented numbers — every number in the whitelist comes from real heatmap data.
"""
from __future__ import annotations

import json
import zlib
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]

_EMPTY_FACTS: dict = {"facts": [], "numbers_whitelist": []}

# Reply-bait questions by direction
_QUESTION_DOWN = [
    "Which one comes back first?",
    "Dead-cat bounce or real dip? Which do you buy?",
    "Who recovers fastest from here?",
    "Which one do you buy into this?",
]
_QUESTION_UP = [
    "Which one breaks out first?",
    "How long does this run last?",
    "Who leads this theme higher?",
    "Which one do you fade here?",
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(path: PathLike) -> dict | list | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def _fmt_pct(v: float) -> str:
    """Format a signed percentage: '+2.1%' or '-5.5%'."""
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


# ─────────────────────────────────────────────────────────────────────────────
# load_movers
# ─────────────────────────────────────────────────────────────────────────────

def load_movers(root: PathLike) -> dict | None:
    """Load both heatmap JSON files and return a combined data dict.

    Returns:
        {
          "sp500_tiles": [...],   # list of {t, name, sector, industry, perf}
          "theme_tiles": [...],   # list of {t, name, sector, perf, members}
          "asof": str | None,
        }
    or None if both files are missing.
    """
    root = Path(root)
    sp500_path = root / "site" / "marketdata" / "sp500_heatmap.json"
    themes_path = root / "site" / "marketdata" / "themes_heatmap.json"

    sp500_data = _load_json(sp500_path)
    themes_data = _load_json(themes_path)

    if sp500_data is None and themes_data is None:
        return None

    sp500_tiles: list[dict] = []
    if isinstance(sp500_data, dict):
        sp500_tiles = sp500_data.get("tiles") or []
        if not isinstance(sp500_tiles, list):
            sp500_tiles = []

    theme_tiles: list[dict] = []
    if isinstance(themes_data, dict):
        theme_tiles = themes_data.get("tiles") or []
        if not isinstance(theme_tiles, list):
            theme_tiles = []

    # asof: prefer sp500 metadata if present
    asof: str | None = None
    if isinstance(sp500_data, dict):
        asof = sp500_data.get("asof") or sp500_data.get("as_of")

    return {
        "sp500_tiles": sp500_tiles,
        "theme_tiles": theme_tiles,
        "asof": asof,
    }


# ─────────────────────────────────────────────────────────────────────────────
# top_movers
# ─────────────────────────────────────────────────────────────────────────────

def top_movers(
    data: dict,
    *,
    tf: str = "1D",
    n: int = 8,
    min_abs: float = 3.0,
    tier_map: dict | None = None,
) -> dict[str, list[dict]]:
    """Return top N gainers and losers from S&P 500 tiles.

    Args:
        data: result of load_movers()
        tf: timeframe key ("1D", "1W", etc.)
        n: max items per side
        min_abs: minimum absolute % to include

    Returns:
        {
          "gainers": [{ticker, name, pct, sector}, ...],  # sorted pct DESC
          "losers":  [{ticker, name, pct, sector}, ...],  # sorted pct ASC (most negative first)
        }
    """
    tiles = (data or {}).get("sp500_tiles") or []
    eligible = []
    for tile in tiles:
        if not isinstance(tile, dict):
            continue
        perf = tile.get("perf") or {}
        pct = perf.get(tf)
        if pct is None:
            continue
        try:
            pct = float(pct)
        except (TypeError, ValueError):
            continue
        if abs(pct) < min_abs:
            continue
        ticker = tile.get("t", "")
        name = tile.get("name", ticker)
        sector = tile.get("sector", "")
        eligible.append({"ticker": ticker, "name": name, "pct": pct, "sector": sector})

    if tier_map:
        eligible = [m for m in eligible if tier_map.get(m.get("ticker"), "") != "T3"]

    gainers = sorted([e for e in eligible if e["pct"] > 0], key=lambda x: x["pct"], reverse=True)[:n]
    losers = sorted([e for e in eligible if e["pct"] < 0], key=lambda x: x["pct"])[:n]

    return {"gainers": gainers, "losers": losers}


# ─────────────────────────────────────────────────────────────────────────────
# theme_lists
# ─────────────────────────────────────────────────────────────────────────────

def theme_lists(
    data: dict,
    *,
    tf: str = "1D",
    n: int = 8,
    min_members: int = 4,
    min_abs_theme: float = 1.0,
) -> list[dict]:
    """Build ranked theme list items from theme_tiles.

    Groups subsector tiles by their parent THEME (tile["sector"]).
    For each theme, aggregates member moves, picks direction, selects top N
    members by absolute move in that direction, ranks by |agg_pct| descending.
    Dedupes: a ticker appears in at most one theme_list.

    Returns list of:
        {
          "theme": str,            # e.g. "Artificial Intelligence"
          "direction": "down"|"up",
          "tone": str,             # plain-English tone
          "members": [{ticker, pct}, ...],  # top N by abs move in direction
          "agg_pct": float,        # average of member pcts
          "question": str,         # reply-bait question
        }
    """
    theme_tiles = (data or {}).get("theme_tiles") or []
    if not theme_tiles:
        return []

    # Step 1: collect all member tickers+pcts per THEME across all subsector tiles
    from collections import defaultdict
    theme_members: dict[str, dict[str, float]] = defaultdict(dict)  # theme -> {ticker: pct}

    for tile in theme_tiles:
        if not isinstance(tile, dict):
            continue
        theme_name = tile.get("sector", "")
        if not theme_name:
            continue
        members = tile.get("members") or []
        for m in members:
            if not isinstance(m, dict):
                continue
            ticker = m.get("t", "")
            perf = m.get("perf") or {}
            pct = perf.get(tf)
            if not ticker or pct is None:
                continue
            try:
                pct = float(pct)
            except (TypeError, ValueError):
                continue
            # First occurrence wins if ticker appears in multiple subsectors of same theme
            if ticker not in theme_members[theme_name]:
                theme_members[theme_name][ticker] = pct

    # Step 2: build theme items
    used_tickers: set[str] = set()
    raw_items = []

    for theme_name, member_map in theme_members.items():
        if len(member_map) < min_members:
            continue
        pcts = list(member_map.values())
        agg_pct = sum(pcts) / len(pcts)

        if abs(agg_pct) < min_abs_theme:
            continue

        direction: str = "down" if agg_pct < 0 else "up"

        # Select members that ACTUALLY moved in the theme's direction, then show
        # the most extreme first — a "who comes back?" (down) list must lead with
        # the biggest LOSERS, an "who's leading?" (up) list with the biggest
        # gainers. (The old sort double-negated and surfaced gainers in a down
        # list — e.g. "FinTech down" showing every member green.)
        if direction == "down":
            in_dir = [kv for kv in member_map.items() if kv[1] < 0]
            in_dir.sort(key=lambda kv: kv[1])              # most negative first
        else:
            in_dir = [kv for kv in member_map.items() if kv[1] > 0]
            in_dir.sort(key=lambda kv: kv[1], reverse=True)  # most positive first
        # Need enough names genuinely moving the theme's way to be a coherent list.
        if len(in_dir) < min_members:
            continue
        top_n_members = in_dir[:n]

        # Pick question deterministically (use theme name hash for stability)
        q_pool = _QUESTION_DOWN if direction == "down" else _QUESTION_UP
        # crc32 (NOT builtin hash(), which is PYTHONHASHSEED-salted per process
        # → the question would flip run-to-run, breaking artifact reproducibility).
        q_idx = zlib.crc32(theme_name.encode("utf-8")) % len(q_pool)
        question = q_pool[q_idx]

        tone = "selling off" if direction == "down" else "ripping"

        raw_items.append({
            "theme": theme_name,
            "direction": direction,
            "tone": tone,
            "all_members": dict(top_n_members),   # before dedup
            "agg_pct": round(agg_pct, 2),
            "question": question,
        })

    # Step 3: rank by |agg_pct| descending
    raw_items.sort(key=lambda x: abs(x["agg_pct"]), reverse=True)

    # Step 4: dedupe tickers across themes (first theme wins)
    result = []
    for item in raw_items:
        members_deduped = [
            {"ticker": ticker, "pct": pct}
            for ticker, pct in item["all_members"].items()
            if ticker not in used_tickers
        ]
        if len(members_deduped) < min_members:
            continue
        for m in members_deduped:
            used_tickers.add(m["ticker"])

        result.append({
            "theme": item["theme"],
            "direction": item["direction"],
            "tone": item["tone"],
            "members": members_deduped,
            "agg_pct": item["agg_pct"],
            "question": item["question"],
        })

    return result


# ─────────────────────────────────────────────────────────────────────────────
# mover_facts
# ─────────────────────────────────────────────────────────────────────────────

def mover_facts(mover: dict, data: dict | None = None) -> dict:
    """Build {facts, numbers_whitelist} for a single mover.

    mover: a dict with {ticker, name, pct, sector} (from top_movers output).
    data: unused currently (reserved for future enrichment), kept for API symmetry.

    Returns the standard facts shape; every number used in fact text is whitelisted.
    No invented numbers — only values from the mover dict itself.
    """
    ticker = mover.get("ticker", "")
    pct = mover.get("pct")
    name = mover.get("name", ticker)
    sector = mover.get("sector", "")

    if not ticker or pct is None:
        return dict(_EMPTY_FACTS)

    try:
        pct = float(pct)
    except (TypeError, ValueError):
        return dict(_EMPTY_FACTS)

    pct_str = _fmt_pct(pct)
    direction = "up" if pct >= 0 else "down"
    abs_str = _fmt_pct(abs(pct)).replace("+", "").replace("-", "")

    facts = []
    whitelist = [pct_str]

    # Primary fact: the day's move
    direction_verb = "surged" if pct >= 3 else ("gained" if pct > 0 else ("crashed" if pct <= -5 else "fell"))
    sector_note = f" ({sector})" if sector else ""
    text = f"{ticker} {direction_verb} {pct_str} today{sector_note}."
    facts.append({
        "id": "mover_pct",
        "text": text,
        "salience": 10,
        "numbers": [pct_str],
    })

    # Absolute magnitude note for bearish cases (bearish framing is good for reach)
    if pct < -3:
        abs_pct_str = f"{abs(pct):.1f}%"
        if abs_pct_str not in whitelist:
            whitelist.append(abs_pct_str)
        facts.append({
            "id": "mover_magnitude",
            "text": f"{ticker} is {abs_pct_str} lower on the day — one of today's biggest moves in the index.",
            "salience": 8,
            "numbers": [abs_pct_str],
        })

    facts.sort(key=lambda x: (-x["salience"], x["id"]))
    return {"facts": facts, "numbers_whitelist": list(dict.fromkeys(whitelist))}


# ─────────────────────────────────────────────────────────────────────────────
# theme_facts
# ─────────────────────────────────────────────────────────────────────────────

def theme_facts(theme_item: dict) -> dict:
    """Build {facts, numbers_whitelist} for a theme_list item.

    theme_item: a dict from theme_lists() output.
    The whitelist MUST cover every member % AND the aggregate pct.
    No invented numbers.
    """
    theme_name = theme_item.get("theme", "")
    members = theme_item.get("members") or []
    agg_pct = theme_item.get("agg_pct")
    direction = theme_item.get("direction", "down")
    question = theme_item.get("question", "")

    if not theme_name or not members:
        return dict(_EMPTY_FACTS)

    # Build whitelist: every member pct + agg
    whitelist: list[str] = []
    seen_wl: set[str] = set()

    def _add_wl(s: str) -> None:
        if s and s not in seen_wl:
            seen_wl.add(s)
            whitelist.append(s)

    member_pct_strs: list[str] = []
    for m in members:
        pct = m.get("pct")
        if pct is not None:
            try:
                s = _fmt_pct(float(pct))
                member_pct_strs.append(s)
                _add_wl(s)
            except (TypeError, ValueError):
                pass

    agg_pct_str: str | None = None
    if agg_pct is not None:
        try:
            agg_pct_str = _fmt_pct(float(agg_pct))
            _add_wl(agg_pct_str)
        except (TypeError, ValueError):
            pass

    facts = []

    # Primary fact: the theme's aggregate move
    direction_word = "lower" if direction == "down" else "higher"
    n_members_str = str(len(members))
    if agg_pct_str:
        text = (
            f"{theme_name} is {agg_pct_str} on average today "
            f"({n_members_str} names {direction_word})."
        )
        facts.append({
            "id": "theme_agg",
            "text": text,
            "salience": 10,
            "numbers": [agg_pct_str, n_members_str],
        })
        _add_wl(n_members_str)
    else:
        text = f"{theme_name}: {n_members_str} names are moving today."
        facts.append({
            "id": "theme_agg",
            "text": text,
            "salience": 8,
            "numbers": [n_members_str],
        })
        _add_wl(n_members_str)

    # Member listing fact
    if members:
        ticker_list = ", ".join(
            f"{m['ticker']} {_fmt_pct(m['pct'])}" if m.get("pct") is not None else m["ticker"]
            for m in members
        )
        facts.append({
            "id": "theme_members",
            "text": f"Moves in {theme_name}: {ticker_list}.",
            "salience": 9,
            "numbers": member_pct_strs,
        })

    # Question fact (for reply-bait context)
    if question:
        facts.append({
            "id": "theme_question",
            "text": question,
            "salience": 7,
            "numbers": [],
        })

    facts.sort(key=lambda x: (-x["salience"], x["id"]))
    return {"facts": facts, "numbers_whitelist": whitelist}
