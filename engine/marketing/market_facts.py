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

Voice law (MARKETING_VOICE_DOCTRINE_V2 §6): fact TEXT feeds post copy, so it must
translate metrics into plain observable words. NO regime labels ("Goldilocks"), NO
internal scores (growth score / inflation score), NO "(read: ...)" asides, NO em
dashes. Say what the data plainly shows, e.g. "growth data keeps coming in soft while
inflation readings are still warm". If the facts are thin, say less.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]

_EMPTY: dict = {"facts": [], "numbers_whitelist": []}


def _growth_words(g: float) -> str:
    """Plain observable phrase for a growth score (no label, no number)."""
    if g <= -0.30:
        return "growth data keeps coming in soft"
    if g < -0.05:
        return "growth data's been running a touch soft"
    if g <= 0.05:
        return "growth data's been roughly steady"
    if g < 0.30:
        return "growth data's firming up a little"
    return "growth data's been running hot"


def _inflation_words(i: float) -> str:
    """Plain observable phrase for an inflation score (no label, no number)."""
    if i <= -0.30:
        return "inflation's cooling off fast"
    if i < -0.05:
        return "inflation's easing a little"
    if i <= 0.05:
        return "inflation's holding roughly flat"
    if i < 0.30:
        return "inflation readings are still a bit warm"
    return "inflation readings are still warm"


# Liquidity overlay → plain observable phrase (no label vocab)
_LIQUIDITY_PLAIN: dict[str, str] = {
    "expanding": "loosening",
    "contracting": "tightening up",
    "neutral": "roughly steady",
    "tightening": "tightening up",
    "easing": "loosening",
}


def _sanitize_tape(text: str) -> str:
    """Strip banned punctuation/vocab from a pulled tape/direction string so it's
    safe to drop into copy. Replaces em/en dashes with a comma and swaps the banned
    word 'de-rating' for a plain synonym. This is translation, not invention."""
    out = str(text).strip().rstrip(".")
    for dash in ("—", " – ", "–"):  # em dash, spaced en dash, en dash
        out = out.replace(dash, ", ")
    # Banned vocab swaps (case-insensitive, plain synonyms)
    import re as _re
    out = _re.sub(r"de-?rating", "selloff", out, flags=_re.IGNORECASE)
    out = _re.sub(r"\bnarrative\b", "story", out, flags=_re.IGNORECASE)
    out = _re.sub(r"\s+,", ",", out)          # tidy " ," → ","
    out = _re.sub(r",\s*,", ",", out)         # collapse ", ,"
    out = _re.sub(r"\s{2,}", " ", out).strip().strip(",").strip()
    return out


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

    Example outputs (plain observable words, no labels or internal scores):
      "Growth data keeps coming in soft while inflation readings are still warm."
      "Liquidity's loosening a bit."
      "The picture's still shifting, not settled yet."
      "Today's tape: AI and semis unwinding, tech leading the selloff."
    """
    root = Path(root)
    regime_path = root / "data" / "regime" / "latest.json"
    brief_path = root / "site" / "neuralwebdata" / "daily_brief.json"

    regime = _load_json(regime_path)
    brief = _load_json(brief_path)

    if not regime and not brief:
        return dict(_EMPTY)

    facts: list[dict] = []

    # Observable count of groups on the move today (a real, honest number we can
    # fold into the headline read so a macro post carries a concrete digit).
    n_groups_str: str | None = None
    _count_folded = False  # True once the group count is folded into the top fact
    if isinstance(brief, dict):
        _tl = brief.get("thematic_line") or {}
        if isinstance(_tl, dict) and _tl.get("available"):
            _nt = _tl.get("n_themes")
            if _nt is not None:
                try:
                    n_groups_str = str(int(_nt))
                except (TypeError, ValueError):
                    n_groups_str = None

    # ── Growth + inflation, translated to plain observable words ──────────────
    # NO regime label, NO scores in the text. We read the underlying growth/
    # inflation scores and say what they plainly imply. The numbers stay internal.
    if isinstance(regime, dict):
        growth = regime.get("growth_score")
        inflation = regime.get("inflation_score")

        if growth is not None and inflation is not None:
            try:
                g = float(growth)
                infl = float(inflation)
                gw = _growth_words(g)
                iw = _inflation_words(infl)
                # Honest "not a comfortable mix" only when the two genuinely pull
                # opposite ways (soft growth + warm inflation, or vice versa).
                uncomfortable = (g < -0.05 and infl > 0.05) or (g > 0.05 and infl < -0.05)
                tail = " Not a comfortable mix." if uncomfortable else ""
                text = f"{gw[0].upper()}{gw[1:]} while {iw}.{tail}"
                nums: list[str] = []
                # Fold in the observable group count as a natural, checkable digit.
                if n_groups_str:
                    text += f" {n_groups_str} groups on the move today."
                    nums = [n_groups_str]
                    _count_folded = True
                facts.append({
                    "id": "growth_inflation",
                    "text": text,
                    "salience": 10,
                    "numbers": nums,
                })
            except (TypeError, ValueError):
                pass

        # ── Liquidity overlay ─────────────────────────────────────────────
        liq = regime.get("liquidity_overlay")
        if liq:
            liq_plain = _LIQUIDITY_PLAIN.get(str(liq).lower(), str(liq).lower())
            facts.append({
                "id": "liquidity_overlay",
                "text": f"Liquidity's {liq_plain} right now.",
                "salience": 7,
                "numbers": [],
            })

        # ── Transition state → plain words, no label ──────────────────────
        trans = str(regime.get("transition_state") or "").upper()
        if trans == "TRANSITIONING":
            facts.append({
                "id": "transition_state",
                "text": "The picture's still shifting, not settled yet.",
                "salience": 6,
                "numbers": [],
            })
        elif trans == "EARLY":
            facts.append({
                "id": "transition_state",
                "text": "Feels early in whatever this turns into.",
                "salience": 6,
                "numbers": [],
            })
        # STABLE (or anything else) → no separate fact; the growth/inflation line
        # already carries the read.

    # ── Daily brief narrative ─────────────────────────────────────────────────
    if isinstance(brief, dict):
        tape = brief.get("why_the_tape_moved") or {}
        if isinstance(tape, dict) and tape.get("available"):
            primary = tape.get("primary") or {}
            direction = primary.get("direction") or ""
            if direction:
                text_clean = _sanitize_tape(direction)
                if text_clean:
                    facts.append({
                        "id": "tape_direction",
                        "text": f"Today's tape: {text_clean}.",
                        "salience": 9,
                        "numbers": [],
                    })

        # Thematic line breadth number — only as a STANDALONE fact when it wasn't
        # already folded into the growth/inflation read (i.e. no regime data).
        if n_groups_str and not _count_folded:
            facts.append({
                "id": "theme_count",
                "text": f"{n_groups_str} different groups are on the move today.",
                "salience": 4,
                "numbers": [n_groups_str],
            })

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

    Example output (plain words, no "(read: ...)" asides, no em dashes):
      "What's driving today: AI and semis unwinding, tech leading the selloff. The
       cross-checks back it up."
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
            coherence = str(primary.get("coherence") or "").lower()
            if direction:
                text_clean = _sanitize_tape(direction)
                if text_clean:
                    # Translate the coherence flag into a plain aside (no "(read: ...)")
                    if coherence == "supported":
                        tail = " The cross-checks back it up."
                    elif coherence in ("conflicted", "mixed"):
                        tail = " Though the cross-checks are mixed on it."
                    elif coherence == "unsupported":
                        tail = " The rest of the data doesn't really back it up though."
                    else:
                        tail = ""
                    text = f"What's driving today: {text_clean}.{tail}"
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
