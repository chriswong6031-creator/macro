"""engine.marketing.movers_source — Heatmap-backed data source for mover/theme posts.

Reads site/marketdata/sp500_heatmap.json and site/marketdata/themes_heatmap.json
to produce structured data for `mover` and `theme_list` content types.

Public API:
    load_movers(root) -> dict | None
    prefer_fresher_session(data) -> dict
    top_movers(data, *, tf, n, min_abs) -> {gainers, losers}
    theme_lists(data, *, tf, n, min_members, min_abs_theme) -> list[dict]
    mover_facts(mover, data) -> {facts, numbers_whitelist}
    theme_facts(theme_item) -> {facts, numbers_whitelist}

All functions are deterministic and fail-soft (return None / empty on errors).
No invented numbers — every number in the whitelist comes from real heatmap data.

UNIVERSE (widened 2026-08-02, masterplan §3 PR-B.3). The S&P heatmap is 503
names, which meant every "biggest mover" this desk has ever posted was the
biggest mover *of the S&P 500* — a Russell name down 22% on the day did not
exist. ``load_movers`` now also returns ``pack_tiles``: heatmap-shaped rows
built from ``data/marketing/hot_tape_pack.json`` for the ~800 liquid names the
heatmap does not carry, and ``top_movers`` considers them alongside the index
tiles. ``min_abs`` and the ``tier_map`` T3 exclusion are unchanged and apply to
the union, so the widening adds candidates and removes no gate.

Three things bound the extension, and all three are the pack's own honesty
guards rather than new inventions:

* **1D only.** The pack carries last/prev close, which is exactly one session.
  It has no 1W/1M change, so a ``tf`` other than ``"1D"`` sees the index tiles
  alone — the same board it has always seen — instead of a silently narrower
  version of a wider claim.
* **Split suspicion.** ``data/massive_stock_day`` is not split-adjusted, so a
  name the pack flags ``suspect`` (any adjacent close-to-close move beyond
  ±60% in its dense window) contributes no percentage. This is the same refusal
  ``hot_tape_pack`` documents for its own card rendering — a split-cliff candle
  is a lie-shaped picture, and a split-cliff percentage is a lie-shaped number.
  Residual exposure, stated: a clean 2-for-1 split reads as −50% and clears the
  ±60% guard. Every one of the 813 pack-only names measured on 2026-08-02 is
  also carried by a split-adjusted store (``data/baskets/ohlcv`` or
  ``data/stocks``), so the exposure is presently zero rather than merely small.
* **Tip-current records only.** A record whose own ``last_date`` lags the pack's
  ``trade_date`` has a "1-day" move from some other week.

Rows carry ``source`` (``"sp500_heatmap"`` | ``"hot_tape_pack"``) because the
claim a fact may make depends on it: only an index tile can be called one of
the biggest moves *in the index*.

SESSION PROVENANCE (2026-07-31). The two heatmaps date themselves DIFFERENTLY,
and they are systematically one calendar day apart:

  * sp500_heatmap.json  `asof` = the last date in the daily CLOSE matrix
    (engine/sp500_heatmap.build_heatmap, ``closes_sorted.index[-1]``). That cache
    lags the live session, so at 21:25Z on 2026-07-30 the field read 2026-07-29
    while the tile 1D it labels had already been overlaid with the 07-30 tape.
  * themes_heatmap.json `asof` = the finviz scrape's own capture date
    (scripts/fetch_finviz_themes: ``datetime.now(timezone.utc)``) — the session
    actually being read.

Measured over 14 consecutive commits (2026-07-30 13:34Z .. 2026-07-31 11:58Z)
the sp500 stamp was EXACTLY one day behind the themes stamp on every single one,
while the 1D numbers themselves agreed to 0.01pp across all 302 names the two
payloads share. A caller that dates BOTH row families by ``data["asof"]``
therefore mislabels the theme rows by a whole session (the mixed-asof failure),
and any freshness gate keyed on that field fails closed forever — which is
exactly what happened to the publish-time lane on 2026-07-31 (every in-window
sweep: pt_generated=0, pt_dropped=1, reason "tape stale").

So every ROW now carries the stamp of the artifact it actually came from, and the
payload keeps per-artifact stamps alongside the legacy ``asof`` (still the sp500
one, because scripts/build_movers_page and engine/press/desk_planner date their
S&P claims with it).
"""
from __future__ import annotations

import json
import zlib
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]

_EMPTY_FACTS: dict = {"facts": [], "numbers_whitelist": []}

# ─────────────────────────────────────────────────────────────────────────────
# Post tails, by direction.
#
# WHAT THIS REPLACES, AND WHY (operator voice law, 2026-07-31). These were four
# reply-bait questions per side — "Which one breaks out first?", "Dead-cat bounce
# or the real dip?", "Who's actually washed out here?" — and all four
# `publisher_live_movers` posts that have ever gone out ended on one. They are
# the exact shape the voice law bans: a question aimed at the reader that costs
# the author NOTHING. The desk names a move and then asks the timeline to do the
# thinking; there is no position, no watch-condition, and nothing that can later
# be shown to have been wrong.
#
# The replacements are stance-or-watch-condition tails that COST the author: each
# commits to doing nothing (or to waiting for a named condition) and then says
# the price of that choice out loud. Four constraints shape every line:
#
#   1. It must end with "?" — copywriter.validate_copy hard-requires a theme_list
#      body to end on a question mark, and that validator is not in this lane's
#      territory. A question can still cost the author when it is about the
#      AUTHOR ("Am I too slow here?") rather than the reader ("What's your
#      read?"). That distinction is the whole rule, and it is ENFORCED on the
#      rendered post by publish_time_content._tail_is_bait: a trailing question
#      carrying no first-person marker is bait, and the post is re-rolled onto
#      another template variant rather than shipped.
#   2. First person in the FINAL sentence, for the same reason.
#   3. NO numbers. copywriter._NUMBER_RE screens every numeric token against the
#      facts whitelist, so a tail inventing "two closes" or "3 days" is a copy
#      violation that drops the whole candidate.
#   4. Direction-keyed, and the key is the SIGN OF THE AGGREGATE (see
#      _direction_of) — never a `direction` string a caller may have set
#      independently of the number it labels.
#   5. **48 CHARACTERS MAX, EACH.** This is a supply constraint, not a style
#      preference, and it is the defect the 2026-07-31 rewrite introduced. The
#      bank it replaced was four ~32-char reply-bait questions; the stance tails
#      came back at up to 80 chars — 2.5× longer — and the tail is appended to a
#      theme body that already carries a member list ("$AAPL +2.1% $MSFT +1.4%
#      …"). copywriter.validate_copy caps headline+body at 275 chars, so the
#      longest banks pushed the 'dry, receipts-forward' theme render to 282 and
#      the candidate was DROPPED as a copy violation. A tail that costs the
#      author nothing to write but costs the desk the whole post is not a voice
#      improvement. The study's reaction-word form is a SHORT verdict — one
#      breath — not a paragraph, so the budget and the voice law agree here.
#      (publish_time_content._render_copy_unbaited now also re-rolls onto other
#      variants on a too-long violation, which is the second net; this is the
#      first, and a bank that fits should never need the net.)
# ─────────────────────────────────────────────────────────────────────────────
_TAIL_DOWN = [
    "Am I too slow waiting for one quiet close?",
    "Do I regret passing on the first bounce?",
    "Does patience cost me the snapback here?",
    "I'd rather be late. Am I paying for that?",
]
_TAIL_UP = [
    "Do I miss it if I refuse to pay up here?",
    "Am I too slow waiting for the pullback?",
    "Does not chasing keep costing me money?",
    "I want it to hold first. Too careful of me?",
]

#: Hard ceiling every tail must satisfy — pinned in tests so a future "better"
#: line cannot quietly reintroduce the 282-char drop. See constraint 5 above.
_TAIL_MAX_CHARS = 48


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


def _direction_of(pct: object, fallback: str = "down") -> str:
    """"up" / "down" derived from the NUMBER, never from a caller's label.

    Closes the direction-mismatch defect. :func:`theme_facts` used to read
    ``theme_item["direction"]`` with a ``"down"`` DEFAULT, so a theme item built
    without that key — every partially-constructed item in the wild, and any
    caller that simply forgot it — printed "+7.7% on average today (8 names
    lower)": a sentence contradicting the figure inside it, on a live account.
    The sign of the aggregate cannot disagree with itself, so it is the sole
    authority here; the string label survives only as the fallback for a
    genuinely absent or unparseable number.
    """
    try:
        v = float(pct)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "down" if str(fallback) == "down" else "up"
    return "down" if v < 0 else "up"


# ─────────────────────────────────────────────────────────────────────────────
# load_movers
# ─────────────────────────────────────────────────────────────────────────────

def load_movers(root: PathLike) -> dict | None:
    """Load both heatmap JSON files and return a combined data dict.

    Returns:
        {
          "sp500_tiles": [...],   # {t, name, sector, industry, perf, asof}
          "theme_tiles": [...],   # {t, name, sector, perf, members, asof}
          "asof": str | None,               # LEGACY alias of sp500_asof
          "sp500_asof": str | None,         # last daily-close date in that payload
          "themes_asof": str | None,        # finviz capture date in that payload
          "sp500_generated_utc": str | None,
          "themes_generated_utc": str | None,
          "sp500_source": str, "themes_source": str,
        }
    or None if both files are missing.

    Every tile (and every theme MEMBER) is stamped with an ``asof`` key naming
    the session ITS OWN artifact dates itself to — see the module docstring for
    why one payload-level stamp cannot honestly serve both families. The stamp is
    purely additive: no number is touched, so the existing consumers see
    byte-identical data plus one key.
    """
    root = Path(root)
    sp500_path = root / "site" / "marketdata" / "sp500_heatmap.json"
    themes_path = root / "site" / "marketdata" / "themes_heatmap.json"

    sp500_data = _load_json(sp500_path)
    themes_data = _load_json(themes_path)

    if sp500_data is None and themes_data is None:
        return None

    def _meta(payload: object, key: str) -> str | None:
        if not isinstance(payload, dict):
            return None
        v = payload.get(key)
        return str(v) if v else None

    sp500_asof = _meta(sp500_data, "asof") or _meta(sp500_data, "as_of")
    themes_asof = _meta(themes_data, "asof") or _meta(themes_data, "as_of")

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

    # Per-ROW session stamps, written in place on the just-parsed JSON objects
    # (nothing else holds a reference to them yet) — one attribute write per
    # tile, no copy. setdefault so a payload that ever grows its own per-tile
    # stamp wins over the file-level one.
    if sp500_asof:
        for _t in sp500_tiles:
            if isinstance(_t, dict):
                _t.setdefault("asof", sp500_asof)
    if themes_asof:
        for _t in theme_tiles:
            if not isinstance(_t, dict):
                continue
            _t.setdefault("asof", themes_asof)
            for _m in (_t.get("members") or []):
                if isinstance(_m, dict):
                    _m.setdefault("asof", themes_asof)

    for _t in sp500_tiles:
        if isinstance(_t, dict):
            _t.setdefault("source", "sp500_heatmap")

    # Liquid names the index board does not carry. Additive key: every existing
    # consumer reads sp500_tiles/theme_tiles and sees byte-identical data.
    pack_tiles = _pack_tiles(root, exclude={str(t.get("t", "")).upper()
                                            for t in sp500_tiles if isinstance(t, dict)})

    return {
        "sp500_tiles": sp500_tiles,
        "theme_tiles": theme_tiles,
        "pack_tiles": pack_tiles,
        # LEGACY key, deliberately unchanged in meaning: build_movers_page and
        # press.desk_planner both date their S&P claims with it.
        "asof": sp500_asof,
        "sp500_asof": sp500_asof,
        "themes_asof": themes_asof,
        "pack_asof": (pack_tiles[0].get("asof") if pack_tiles else None),
        "sp500_generated_utc": _meta(sp500_data, "generated_utc"),
        "themes_generated_utc": _meta(themes_data, "generated_utc"),
        "sp500_source": _meta(sp500_data, "source") or "",
        "themes_source": _meta(themes_data, "source") or "",
    }


def _pack_tiles(root: PathLike, exclude: set[str] | None = None) -> list[dict]:
    """Heatmap-shaped 1D rows for hot-tape-pack names outside *exclude*.

    Shaped exactly like an ``sp500_heatmap`` tile (``t``/``name``/``sector``/
    ``perf``/``asof``) so ``top_movers`` needs no second code path, plus
    ``source: "hot_tape_pack"`` so a downstream fact knows it may not claim the
    index. The pack has no company names and only carries ``sector`` for its
    S&P members, so both fall back the way the heatmap path already does.

    Fail-soft: an absent, malformed or unusable pack returns ``[]`` and the
    board is the 503-name index it has always been. No annotation here — the
    tier builder already prints exactly one for a missing/stale pack, and this
    module is called on the intraday path where a second copy of that warning
    would be noise, not news.
    """
    exclude = exclude or set()
    try:
        pack = _load_json(Path(root) / "data" / "marketing" / "hot_tape_pack.json")
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(pack, dict):
        return []
    records = pack.get("tickers")
    if not isinstance(records, dict):
        return []
    trade_date = str(pack.get("trade_date") or "")[:10]
    if not trade_date:
        return []

    tiles: list[dict] = []
    for ticker, rec in records.items():
        if not isinstance(rec, dict):
            continue
        t = str(ticker).upper()
        if not t or t in exclude:
            continue
        if rec.get("suspect"):
            continue
        if str(rec.get("last_date") or "")[:10] != trade_date:
            continue
        try:
            last_c = float(rec.get("last_close"))
            prev_c = float(rec.get("prev_close"))
        except (TypeError, ValueError):
            continue
        if not (prev_c > 0) or last_c != last_c or prev_c != prev_c:
            continue
        tiles.append({
            "t": t,
            "name": rec.get("ticker") or t,
            "sector": rec.get("sector") or "",
            "perf": {"1D": (last_c / prev_c - 1.0) * 100.0},
            "asof": trade_date,
            "source": "hot_tape_pack",
        })
    tiles.sort(key=lambda x: x["t"])
    return tiles


def prefer_fresher_session(data: dict | None) -> dict:
    """A COPY of *data* whose S&P rows carry the FRESHER of the two reads.

    When ``themes_asof`` is a strictly later session than ``sp500_asof`` (the
    standing case — see the module docstring), the themes payload holds the same
    1D change for every name it shares with the index board, one session newer.
    Preferring it re-dates those rows to the themes session, which is what lets a
    publish-time mover post claim the CURRENT session instead of being refused as
    stale on every heatmap-only sweep.

    OPT-IN, and it has to stay opt-in. ``engine/press/desk_planner`` writes
    "closed {pct}% on the session of {data['asof']}" from the payload-level
    stamp, so quietly freshening the rows underneath it would manufacture exactly
    the mixed-asof claim this whole change exists to prevent. The caller that
    tracks per-row sessions (engine/marketing/publish_time_content) opts in; the
    callers that do not, do not.

    Rows the themes payload does not carry come back untouched, still stamped
    with the older sp500 session — per row, never per payload.
    """
    d = dict(data or {})
    sp_asof = str(d.get("sp500_asof") or d.get("asof") or "")
    th_asof = str(d.get("themes_asof") or "")
    tiles = d.get("sp500_tiles") or []
    d["sp500_tiles"] = list(tiles)
    if not tiles or not th_asof or th_asof <= sp_asof:
        # Themes is not strictly fresher → nothing to prefer. A plain string
        # compare is right: both stamps are ISO "YYYY-MM-DD" by construction, and
        # an unparseable/absent stamp compares as "not fresher" (fail closed).
        return d

    fresher: dict[str, float] = {}
    for tile in d.get("theme_tiles") or []:
        if not isinstance(tile, dict):
            continue
        for m in tile.get("members") or []:
            if not isinstance(m, dict):
                continue
            tkr = str(m.get("t") or "")
            pct = (m.get("perf") or {}).get("1D")
            if not tkr or pct is None or tkr in fresher:
                continue
            try:
                fresher[tkr] = float(pct)
            except (TypeError, ValueError):
                continue

    out_tiles: list[dict] = []
    for tile in d["sp500_tiles"]:
        if not isinstance(tile, dict):
            continue
        tkr = str(tile.get("t") or "")
        if tkr not in fresher:
            out_tiles.append(tile)
            continue
        nt = dict(tile)
        perf = dict(nt.get("perf") or {})
        perf["1D"] = fresher[tkr]
        nt["perf"] = perf
        nt["asof"] = th_asof
        out_tiles.append(nt)
    d["sp500_tiles"] = out_tiles
    return d


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
          "gainers": [{ticker, name, pct, sector, asof, source}, ...],  # sorted pct DESC
          "losers":  [{ticker, name, pct, sector, asof, source}, ...],  # sorted pct ASC
        }

    The candidate board is the S&P heatmap tiles PLUS, for ``tf == "1D"`` only,
    the hot-tape-pack rows ``load_movers`` attached (see the module docstring).
    ``min_abs`` and the ``tier_map`` T3 exclusion are applied to the union
    unchanged: this widens what may be considered, never what may pass.
    """
    tiles = list((data or {}).get("sp500_tiles") or [])
    if str(tf) == "1D":
        tiles += list((data or {}).get("pack_tiles") or [])
    eligible = []
    seen: set[str] = set()
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
        # The index tile wins any collision: it is the split-adjusted, named,
        # sector-tagged read, and load_movers already excludes its names from
        # the pack rows — this is belt-and-braces for a hand-built payload.
        key = str(ticker).upper()
        if key in seen:
            continue
        seen.add(key)
        name = tile.get("name", ticker)
        sector = tile.get("sector", "")
        # `asof` rides the ROW, not the payload: after prefer_fresher_session a
        # tile refreshed from the themes read carries the themes session while
        # its index-only neighbours still carry the close-cache one, and a
        # publish-time post has to know which session ITS name belongs to.
        # `source` rides the row for the same reason — see mover_facts.
        eligible.append({"ticker": ticker, "name": name, "pct": pct,
                         "sector": sector, "asof": tile.get("asof"),
                         "source": tile.get("source") or "sp500_heatmap"})

    if tier_map:
        eligible = [m for m in eligible if tier_map.get(m.get("ticker"), "") != "T3"]

    gainers = sorted([e for e in eligible if e["pct"] > 0], key=lambda x: x["pct"], reverse=True)[:n]
    losers = sorted([e for e in eligible if e["pct"] < 0], key=lambda x: x["pct"])[:n]

    return {"gainers": gainers, "losers": losers}


# ─────────────────────────────────────────────────────────────────────────────
# theme_lists
# ─────────────────────────────────────────────────────────────────────────────

def _load_cashtag_tiers(root: PathLike | None) -> dict[str, str]:
    """Load data/marketing/cashtag_tiers.json and return a ticker→tier map.

    Returns {} on any error (file absent, malformed). Fail-soft.
    """
    if root is None:
        return {}
    try:
        path = Path(root) / "data" / "marketing" / "cashtag_tiers.json"
        raw = _load_json(path)
        if not isinstance(raw, dict):
            return {}
        tickers = raw.get("tickers") or {}
        if not isinstance(tickers, dict):
            return {}
        return {t: v.get("tier", "") for t, v in tickers.items() if isinstance(v, dict)}
    except Exception:  # noqa: BLE001
        return {}


def theme_lists(
    data: dict,
    *,
    tf: str = "1D",
    n: int = 8,
    min_members: int = 4,
    min_abs_theme: float = 1.0,
    cashtag_tiers: dict[str, str] | None = None,
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
          "question": str,         # the direction-keyed stance / watch tail
          "asof": str | None,      # the session ALL members share, else None
        }

    ``asof`` is None when the contributing members do NOT agree on a session: an
    aggregate that averages two sessions is the mixed-asof failure, so it gets no
    date at all and the consumer refuses it rather than guessing.
    """
    theme_tiles = (data or {}).get("theme_tiles") or []
    if not theme_tiles:
        return []

    # Step 1: collect all member tickers+pcts per THEME across all subsector tiles
    from collections import defaultdict
    theme_members: dict[str, dict[str, float]] = defaultdict(dict)  # theme -> {ticker: pct}
    theme_sessions: dict[str, set[str]] = defaultdict(set)          # theme -> {asof, ...}

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
                theme_sessions[theme_name].add(
                    str(m.get("asof") or tile.get("asof") or ""))

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

        # Through the ONE helper every direction word in this module now uses.
        direction: str = _direction_of(agg_pct)

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

        # Pick the tail deterministically (theme name hash for stability).
        # THE POOL IS KEYED ON THE RECOMPUTED SIGN, never on a stored label: an
        # "up" tail welded onto a negative aggregate is the direction-mismatch
        # defect, and routing the choice through _direction_of(agg_pct) makes it
        # unrepresentable rather than merely unlikely.
        q_pool = _TAIL_DOWN if _direction_of(agg_pct) == "down" else _TAIL_UP
        # crc32 (NOT builtin hash(), which is PYTHONHASHSEED-salted per process
        # → the tail would flip run-to-run, breaking artifact reproducibility).
        q_idx = zlib.crc32(theme_name.encode("utf-8")) % len(q_pool)
        question = q_pool[q_idx]

        tone = "selling off" if direction == "down" else "ripping"

        # Leading-theme score = mean |pct_change| of members, +boost when ≥2 members
        # are T1 in cashtag_tiers. Deterministic: boost is a fixed constant.
        member_pcts = [abs(pct) for _, pct in top_n_members]
        mean_abs = sum(member_pcts) / len(member_pcts) if member_pcts else 0.0
        t1_boost = 0.0
        if cashtag_tiers:
            t1_count = sum(
                1 for ticker, _ in top_n_members
                if cashtag_tiers.get(ticker, "") == "T1"
            )
            if t1_count >= 2:
                t1_boost = 1.5  # fixed boost for ≥2 T1 members

        raw_items.append({
            "theme": theme_name,
            "direction": direction,
            "tone": tone,
            "all_members": dict(top_n_members),   # before dedup
            "agg_pct": round(agg_pct, 2),
            "question": question,
            # One session or nothing: a set of size 1 dates the whole aggregate;
            # anything else averages two sessions and gets no date, so the
            # consumer refuses it instead of publishing a claim it cannot anchor.
            "asof": (next(iter(theme_sessions[theme_name]))
                     if len(theme_sessions[theme_name]) == 1 else None) or None,
            "_lead_score": mean_abs + t1_boost,
        })

    # Step 3: rank by leading-theme score descending (mean |pct| + T1 boost).
    # When cashtag_tiers is absent the T1 boost is 0 and this degrades to pure
    # mean-|member-pct| sort (NOT |agg_pct| — the member mean and the tile agg_pct
    # diverge whenever members are a strict subset of the tile universe).
    raw_items.sort(key=lambda x: x["_lead_score"], reverse=True)

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
            "asof": item["asof"],
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
        # SCOPE THE CLAIM TO THE BOARD THE ROW CAME FROM. This sentence used to
        # say "in the index" unconditionally, which was true while the only
        # board was the 503-name S&P heatmap. Once top_movers also draws from
        # the ~800-name hot-tape pack, that clause is a false statement about
        # membership for every non-index name — the same defect as a superlative
        # whose evidence window overruns its chart (masterplan §0.2). The wider
        # board gets the wider, still-true phrasing.
        scope = ("one of the biggest moves in the index"
                 if str(mover.get("source") or "sp500_heatmap") == "sp500_heatmap"
                 else "one of the biggest moves on the tape")
        facts.append({
            "id": "mover_magnitude",
            "text": f"{ticker} is {abs_pct_str} lower on the day, {scope}.",
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
    # THE NUMBER DECIDES. This was `theme_item.get("direction", "down")`, and the
    # default is what shipped the defect: a theme item built without an explicit
    # `direction` key printed "+7.7% on average today (8 names lower)" — a
    # sentence contradicting the figure it was quoting, welded on by a default
    # nobody could see. _direction_of recomputes from agg_pct and only falls back
    # to the stored label when the aggregate itself is missing or unparseable.
    direction = _direction_of(agg_pct, theme_item.get("direction", "down"))
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
