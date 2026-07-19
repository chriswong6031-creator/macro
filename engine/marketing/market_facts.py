"""engine.marketing.market_facts — Deterministic fact sources for non-ticker content types.

Turns regime/daily_brief/heatmap/confluence artifacts into concrete, checkable
facts that macro/event/watchlist posts can weave in — same shape as chart_facts.py.

Public API:
    macro_facts(root)   -> {facts, numbers_whitelist}
    sector_facts(root)  -> {facts, numbers_whitelist}
    breadth_facts(root) -> {facts, numbers_whitelist}
    event_facts(root)   -> {facts, numbers_whitelist}

All functions:
- Return {"facts": [], "numbers_whitelist": []} on missing files (fail-soft)
- Are deterministic (no RNG, no network)
- Put every number that appears in a fact text into numbers_whitelist
- Never invent numbers — only values actually present in the source artifacts
- Use plain-word language, no indicator vocabulary (MACD/RSI/Stochastic/etc.)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]

_EMPTY: dict = {"facts": [], "numbers_whitelist": []}

# Plain-English label map for quad names (no raw slug leaks)
_QUAD_PLAIN: dict[str, str] = {
    "Q1": "Goldilocks",
    "Q2": "Reflation",
    "Q3": "Stagflation",
    "Q4": "Deflation",
}

# Liquidity overlay → plain English
_LIQUIDITY_PLAIN: dict[str, str] = {
    "expanding": "expanding",
    "contracting": "contracting",
    "neutral": "neutral",
    "tightening": "tightening",
    "easing": "easing",
}

# Transition state → plain English (keep the word but clarify)
_TRANSITION_PLAIN: dict[str, str] = {
    "TRANSITIONING": "transitioning",
    "STABLE": "stable",
    "EARLY": "early-stage",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(path: PathLike) -> dict | list | None:
    """Load JSON file; return None on any error."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def _fmt_score(v: float) -> str:
    """Format a score as a signed float with 2 decimal places."""
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}"


def _fmt_pct(v: float, decimals: int = 1) -> str:
    """Format a signed percentage, e.g. '+2.1%'."""
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.{decimals}f}%"


def _build(facts: list[dict]) -> dict:
    """Build the return shape from a list of fact dicts."""
    seen_ids: set[str] = set()
    deduped: list[dict] = []
    for f in facts:
        fid = f.get("id", "")
        if fid not in seen_ids:
            seen_ids.add(fid)
            deduped.append(f)

    seen_nums: set[str] = set()
    whitelist: list[str] = []
    for f in deduped:
        for num in f.get("numbers", []):
            if num and num not in seen_nums:
                seen_nums.add(num)
                whitelist.append(num)

    return {"facts": deduped, "numbers_whitelist": whitelist}


# ─────────────────────────────────────────────────────────────────────────────
# macro_facts
# ─────────────────────────────────────────────────────────────────────────────

def macro_facts(root: PathLike) -> dict:
    """Compute macro facts from regime/latest.json, site/neuralwebdata/daily_brief.json,
    and data/neuralweb/world_state.json.

    Example outputs:
      "The macro regime is Goldilocks — growth score -0.07, inflation score +0.40."
      "Liquidity is expanding."
      "The regime is transitioning — not yet stable."
      "Today's tape: AI/semis unwind — tech-led de-rating."
    """
    root = Path(root)
    regime_path = root / "data" / "regime" / "latest.json"
    brief_path = root / "site" / "neuralwebdata" / "daily_brief.json"

    regime = _load_json(regime_path)
    brief = _load_json(brief_path)

    if not regime and not brief:
        return dict(_EMPTY)

    facts: list[dict] = []

    # ── Regime quad ──────────────────────────────────────────────────────────
    if isinstance(regime, dict):
        quad_name = regime.get("quad_name") or regime.get("label") or ""
        quad_id = regime.get("quad") or ""
        # Use human-readable name; fallback to raw quad_name
        plain_name = _QUAD_PLAIN.get(quad_id, quad_name) or quad_name
        growth = regime.get("growth_score")
        inflation = regime.get("inflation_score")

        if plain_name and growth is not None and inflation is not None:
            try:
                g = float(growth)
                infl = float(inflation)
                g_str = _fmt_score(g)
                i_str = _fmt_score(infl)
                text = (
                    f"The macro regime is {plain_name} — "
                    f"growth score {g_str}, inflation score {i_str}."
                )
                facts.append({
                    "id": "regime_quad",
                    "text": text,
                    "salience": 10,
                    "numbers": [g_str, i_str],
                })
            except (TypeError, ValueError):
                pass
        elif plain_name:
            facts.append({
                "id": "regime_quad",
                "text": f"The macro regime is {plain_name}.",
                "salience": 8,
                "numbers": [],
            })

        # ── Liquidity overlay ─────────────────────────────────────────────
        liq = regime.get("liquidity_overlay")
        if liq:
            liq_plain = _LIQUIDITY_PLAIN.get(str(liq).lower(), str(liq).lower())
            facts.append({
                "id": "liquidity_overlay",
                "text": f"Liquidity is {liq_plain}.",
                "salience": 7,
                "numbers": [],
            })

        # ── Transition state ──────────────────────────────────────────────
        trans = regime.get("transition_state")
        if trans:
            trans_plain = _TRANSITION_PLAIN.get(str(trans).upper(), str(trans).lower())
            facts.append({
                "id": "transition_state",
                "text": f"The regime is {trans_plain}.",
                "salience": 6,
                "numbers": [],
            })

    # ── Daily brief narrative ─────────────────────────────────────────────────
    if isinstance(brief, dict):
        tape = brief.get("why_the_tape_moved") or {}
        if isinstance(tape, dict) and tape.get("available"):
            primary = tape.get("primary") or {}
            direction = primary.get("direction") or ""
            if direction:
                # Strip internal tag noise — take first sentence-like chunk
                text_clean = str(direction).strip().rstrip(".")
                facts.append({
                    "id": "tape_direction",
                    "text": f"Today's tape: {text_clean}.",
                    "salience": 9,
                    "numbers": [],
                })

        # Thematic line breadth numbers
        tl = brief.get("thematic_line") or {}
        if isinstance(tl, dict) and tl.get("available"):
            n_themes = tl.get("n_themes")
            if n_themes is not None:
                try:
                    n = int(n_themes)
                    n_str = str(n)
                    facts.append({
                        "id": "theme_count",
                        "text": f"{n_str} themes are active on the dashboard right now.",
                        "salience": 4,
                        "numbers": [n_str],
                    })
                except (TypeError, ValueError):
                    pass

    # Sort salience-DESC, id-ASC for determinism
    facts.sort(key=lambda x: (-x["salience"], x["id"]))
    return _build(facts)


# ─────────────────────────────────────────────────────────────────────────────
# sector_facts
# ─────────────────────────────────────────────────────────────────────────────

def sector_facts(root: PathLike) -> dict:
    """Compute sector facts from site/marketdata/sp500_heatmap.json.

    Example outputs:
      "Energy led today +1.1%; only 1 of 11 sectors closed in the green."
      "Communication Services lagged today -1.3%."
      "ISRG fell -14.2% today, the biggest single-stock move in the index."
    """
    root = Path(root)
    hm_path = root / "site" / "marketdata" / "sp500_heatmap.json"
    hm = _load_json(hm_path)

    if not isinstance(hm, dict):
        return dict(_EMPTY)

    tiles = hm.get("tiles") or []
    if not isinstance(tiles, list) or not tiles:
        return dict(_EMPTY)

    # Aggregate sector performance (mean of 1D tile returns)
    from collections import defaultdict
    sector_vals: dict[str, list[float]] = defaultdict(list)
    best_stock_name = ""
    best_stock_pct = 0.0
    best_stock_abs = 0.0
    best_stock_ticker = ""

    for tile in tiles:
        if not isinstance(tile, dict):
            continue
        sector = tile.get("sector") or ""
        perf = tile.get("perf") or {}
        p1d = perf.get("1D")
        if sector and p1d is not None:
            try:
                sector_vals[sector].append(float(p1d))
            except (TypeError, ValueError):
                pass
        # Track biggest single-stock absolute mover
        if p1d is not None:
            try:
                abs_p = abs(float(p1d))
                if abs_p > best_stock_abs:
                    best_stock_abs = abs_p
                    best_stock_pct = float(p1d)
                    best_stock_ticker = tile.get("t") or ""
                    best_stock_name = tile.get("name") or best_stock_ticker
            except (TypeError, ValueError):
                pass

    if not sector_vals:
        return dict(_EMPTY)

    sector_avg = {
        s: sum(v) / len(v)
        for s, v in sector_vals.items()
    }
    sorted_sectors = sorted(sector_avg.items(), key=lambda x: x[1], reverse=True)

    facts: list[dict] = []

    # Best and worst sector
    if sorted_sectors:
        best_name, best_pct = sorted_sectors[0]
        worst_name, worst_pct = sorted_sectors[-1]

        # Count green sectors (positive mean return)
        n_green = sum(1 for _, v in sorted_sectors if v > 0)
        n_total = len(sorted_sectors)
        n_green_str = str(n_green)
        n_total_str = str(n_total)
        best_pct_str = _fmt_pct(best_pct)
        worst_pct_str = _fmt_pct(worst_pct)

        if best_pct > 0:
            text = (
                f"{best_name} led today {best_pct_str}; "
                f"{n_green_str} of {n_total_str} sectors closed in the green."
            )
            facts.append({
                "id": "sector_leader",
                "text": text,
                "salience": 8,
                "numbers": [best_pct_str, n_green_str, n_total_str],
            })
        else:
            # Broad red day
            text = (
                f"All {n_total_str} sectors closed lower today; "
                f"{best_name} held up best at {best_pct_str}."
            )
            facts.append({
                "id": "sector_leader",
                "text": text,
                "salience": 8,
                "numbers": [n_total_str, best_pct_str],
            })

        if worst_name != best_name:
            text_worst = f"{worst_name} lagged today {worst_pct_str}."
            facts.append({
                "id": "sector_laggard",
                "text": text_worst,
                "salience": 7,
                "numbers": [worst_pct_str],
            })

    # Biggest single-stock mover
    if best_stock_ticker and best_stock_abs >= 3.0:
        direction = "rose" if best_stock_pct > 0 else "fell"
        pct_str = _fmt_pct(best_stock_pct)
        display = best_stock_name or best_stock_ticker
        text_stock = (
            f"{display} {direction} {pct_str} today, "
            f"the biggest single-stock move in the index."
        )
        facts.append({
            "id": "biggest_stock_mover",
            "text": text_stock,
            "salience": 6,
            "numbers": [pct_str],
        })

    facts.sort(key=lambda x: (-x["salience"], x["id"]))
    return _build(facts)


# ─────────────────────────────────────────────────────────────────────────────
# breadth_facts
# ─────────────────────────────────────────────────────────────────────────────

def breadth_facts(root: PathLike) -> dict:
    """Compute market-breadth/temperature facts from site/factordata/tech_confluence.json.

    Example outputs:
      "226 names in the S&P 500 universe are showing bullish momentum setups right now."
      "The most widely active setup across the index is a momentum-trend cluster."
    """
    root = Path(root)
    tc_path = root / "site" / "factordata" / "tech_confluence.json"
    tc = _load_json(tc_path)

    if not isinstance(tc, dict):
        return dict(_EMPTY)

    facts: list[dict] = []

    # ── Count tickers with any long combo firing ──────────────────────────────
    now = tc.get("now") or {}
    universe_n = tc.get("universe_n")

    if isinstance(now, dict):
        n_active = len([t for t, v in now.items() if isinstance(v, list) and len(v) > 0])
        if n_active > 0:
            n_str = str(n_active)
            if universe_n:
                try:
                    u_str = str(int(universe_n))
                    text = (
                        f"{n_str} of {u_str} names in the S&P universe are showing "
                        f"bullish momentum setups right now."
                    )
                    facts.append({
                        "id": "breadth_active",
                        "text": text,
                        "salience": 8,
                        "numbers": [n_str, u_str],
                    })
                except (TypeError, ValueError):
                    text = (
                        f"{n_str} names in the index are showing "
                        f"bullish momentum setups right now."
                    )
                    facts.append({
                        "id": "breadth_active",
                        "text": text,
                        "salience": 8,
                        "numbers": [n_str],
                    })
            else:
                text = (
                    f"{n_str} names are showing bullish momentum setups right now."
                )
                facts.append({
                    "id": "breadth_active",
                    "text": text,
                    "salience": 8,
                    "numbers": [n_str],
                })

    # ── Most common setup — plain language, no indicator vocab ───────────────
    combos_block = tc.get("combos") or {}
    if isinstance(combos_block, dict):
        long_combos = combos_block.get("long") or []
    elif isinstance(combos_block, list):
        long_combos = combos_block
    else:
        long_combos = []

    if isinstance(now, dict) and long_combos:
        from collections import Counter
        combo_fires: Counter = Counter()
        for t, indices in now.items():
            if isinstance(indices, list):
                for i in indices:
                    if isinstance(i, int) and i < len(long_combos):
                        combo_fires[i] += 1

        if combo_fires:
            top_idx, top_count = combo_fires.most_common(1)[0]
            top_count_str = str(top_count)
            # Plain description — no indicator vocab
            # We use a generic momentum/trend description
            facts.append({
                "id": "top_setup_breadth",
                "text": (
                    f"The most active bullish setup is firing on {top_count_str} names today."
                ),
                "salience": 6,
                "numbers": [top_count_str],
            })

    facts.sort(key=lambda x: (-x["salience"], x["id"]))
    return _build(facts)


# ─────────────────────────────────────────────────────────────────────────────
# event_facts
# ─────────────────────────────────────────────────────────────────────────────

def event_facts(root: PathLike) -> dict:
    """Best-available event/catalyst fact for the day.

    Tries daily_brief first (why_the_tape_moved). Falls back to macro_facts.

    Example output:
      "Today's catalyst: AI/semis unwind — tech-led de-rating (coherence: supported)."
    """
    root = Path(root)
    brief_path = root / "site" / "neuralwebdata" / "daily_brief.json"
    brief = _load_json(brief_path)

    facts: list[dict] = []

    if isinstance(brief, dict):
        tape = brief.get("why_the_tape_moved") or {}
        if isinstance(tape, dict) and tape.get("available"):
            primary = tape.get("primary") or {}
            direction = primary.get("direction") or ""
            coherence = primary.get("coherence") or ""
            if direction:
                text_clean = str(direction).strip().rstrip(".")
                if coherence and coherence != "unknown":
                    text = f"Today's catalyst: {text_clean} (read: {coherence})."
                else:
                    text = f"Today's catalyst: {text_clean}."
                facts.append({
                    "id": "event_catalyst",
                    "text": text,
                    "salience": 10,
                    "numbers": [],
                })

    if not facts:
        # Fall back to macro facts as best available context
        return macro_facts(root)

    facts.sort(key=lambda x: (-x["salience"], x["id"]))
    return _build(facts)


# ─────────────────────────────────────────────────────────────────────────────
# merge helper (for watchlist: combine breadth + sector)
# ─────────────────────────────────────────────────────────────────────────────

def merge_facts(*fact_dicts: dict) -> dict:
    """Merge multiple facts dicts, deduplicating by id, preserving order by salience."""
    combined: list[dict] = []
    seen_ids: set[str] = set()
    for fd in fact_dicts:
        if not isinstance(fd, dict):
            continue
        for f in fd.get("facts") or []:
            fid = f.get("id", "")
            if fid not in seen_ids:
                seen_ids.add(fid)
                combined.append(f)

    combined.sort(key=lambda x: (-x.get("salience", 0), x.get("id", "")))

    seen_nums: set[str] = set()
    whitelist: list[str] = []
    for f in combined:
        for num in f.get("numbers", []):
            if num and num not in seen_nums:
                seen_nums.add(num)
                whitelist.append(num)

    return {"facts": combined, "numbers_whitelist": whitelist}
