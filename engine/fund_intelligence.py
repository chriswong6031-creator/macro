"""Per-fund 13F intelligence — full resolved books, conviction composites,
sector/theme rotation and the "core lean" synthesis for the Smart-Money desk
fund dossiers (Signal Desk v3).

engine.smart_money answers "who holds this name"; engine.manager_trades grades
each fund's trades. This module asks the per-fund portfolio questions the desk
could not answer before: what does the WHOLE latest book look like (not just
the top-8), which positions carry real conviction (a transparent 0-100
descriptive composite with every component shown), how has the fund's
sector/theme mix rotated across the retained quarters, and what is its current
thematic core lean.

Reuses the engine.smart_money primitives (``_read_all`` / ``diff_snapshots`` /
``resolve_tickers`` / ``position_rank_and_tilt`` / ``window_dressing_flag``)
so every number here shares the desk's resolution and diff semantics, and
prices everything through ONE shared ``engine.manager_trades.ClosePanel``
(never constructed per fund).

House rules honored here:
  * Look-ahead-free — every price anchor is the fund's PUBLIC ``filing_date``
    (never ``period_end``); add-streaks are derived from the snapshot store
    alone, so nothing here peeks past a filing.
  * Two clocks (SM2-R3) — everything in this module is 13F-lane.
    ``since_excess`` is a realized price read anchored on the filing date
    (the exact tracker convention), displayed side by side with the 13F
    numbers and never blended into another lane.
  * Descriptive, not predictive — the conviction score is a transparent
    weighted checklist (components carried on every row): a descriptive
    rank, not a forecast. Nothing here is imported by any scoring path.
  * NEVER-BREAK — disk readers degrade to []/{}/None with a logged warning;
    one classification source or one fund failing never takes down the build.
  * F12 honesty — historical quarters are classified with TODAY's
    sector/theme map (survivorship-lite); that caveat is stamped as
    ``method_note`` on the rotation payload and the build ``_meta``.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from engine.manager_trades import ClosePanel
from engine.smart_money import (_read_all, diff_snapshots, full_cusip_map,
                                name_ticker_map, position_rank_and_tilt,
                                resolve_tickers, window_dressing_flag)
from lib import config

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Tunables — config lives under smart_money.conviction (read with .get();      #
# defaults here are byte-identical to config.yml so absent config never breaks) #
# --------------------------------------------------------------------------- #

_DEFAULT_WEIGHTS: dict[str, float] = {
    "w_pct_book": 35.0,      # pct-of-book percentile within the fund
    "w_rank_top10": 15.0,    # position_rank <= 10
    "w_tilt": 10.0,          # tilt_pp > 0 (overweight vs the fund's mean slot)
    "w_add_streak": 20.0,    # consecutive new/add quarters (capped, see below)
    "w_new_at_size": 10.0,   # new position opened at >= _NEW_AT_SIZE_MIN_PCT of book
    "w_persisted": 10.0,     # window_dressing_flag == 'persisted'
}
# version tag for the weight set — embedded in build meta so the L5 ledger rule
# ("conviction x grade composite, weights v2026-07") stays legible if weights move.
CONVICTION_WEIGHTS_VERSION = "v2026-07"

_TIER_HIGH = 70.0            # score >= 70 -> 'high'
_TIER_MODERATE = 45.0        # score >= 45 -> 'moderate' (else 'low')
_STREAK_CAP_Q = 4            # a 4+ quarter add streak earns the full streak weight
_NEW_AT_SIZE_MIN_PCT = 2.0   # 'new_at_size' = new position at >= 2% of the book
_BUY_ACTIONS = {"new", "add"}
_MAX_LEANS = 6               # theme_read keeps the top-6 add clusters
_MAX_THEMES_PER_POSITION = 3
_MAX_NARRATIVE_TICKERS = 5
_UNCLASSIFIED = "Unclassified"

_MOVE_COLS = ["ticker", "issuer", "action", "pct_portfolio", "value_usd",
              "shares", "shares_change_pct"]

# F12: today's classification map applied to historical quarters. Stamped on the
# rotation payload + build _meta so the caveat travels with the numbers.
METHOD_NOTE_EN = ("Current sector/theme map applied to history — historical quarters "
                  "are classified with today's sector and theme membership "
                  "(survivorship-lite; past classification changes are not reconstructed).")
METHOD_NOTE_ZH = ("以当前行业/主题映射回溯历史——历史季度按今日的行业与主题成员分类"
                  "（轻度幸存者口径；不重建过去的分类变更）。")

CONVICTION_METHOD_EN = ("Conviction = pct-of-book percentile (35) + top-10 rank (15) + "
                        "overweight tilt (10) + add streak (20) + new-at-size (10) + "
                        "persistence (10) — a descriptive rank, not a forecast.")
CONVICTION_METHOD_ZH = ("信念分 = 组合占比分位（35）+ 前十大持仓（15）+ 超配倾斜（10）+ "
                        "连续加仓（20）+ 大额新建仓（10）+ 持仓延续（10）——描述性排序，"
                        "并非预测。")

# --------------------------------------------------------------------------- #
# Module caches (one-shot build process). _clear_caches() resets them for       #
# tests or long-lived processes that need fresh maps/snapshots.                 #
# --------------------------------------------------------------------------- #

_CLS_CACHE: dict | None = None
_HIST_CACHE: dict[str, list[tuple[str, str, pd.DataFrame]]] = {}


def _clear_caches() -> None:
    """Reset the module-level classification + snapshot caches (tests / reloads)."""
    global _CLS_CACHE
    _CLS_CACHE = None
    _HIST_CACHE.clear()


# --------------------------------------------------------------------------- #
# Classification merge (four sources, each optional)                            #
# --------------------------------------------------------------------------- #

def load_classifications() -> dict:
    """One merged ticker classification map from the four repo sources.

    Returns ``{TICKER: {sector, sub_industry, themes: [{slug, name, name_zh,
    category}], finviz: [{subsector_key, subsector_name, theme}]}}`` plus a
    ``"_meta"`` key with per-source coverage counts (coverage honesty — the
    caller can see exactly how much of each source landed).

    Sources (each read in its own try/except — one missing source must not
    kill the rest):
      1. data/sp500_heatmap/industry_map.json — primary sector + sub_industry.
      2. data/universe/membership.parquet    — sector FALLBACK for names the
         heatmap map misses (S&P 1500 ledger, active rows only).
      3. data/baskets/membership.json        — curated theme baskets, ACTIVE
         members only (``removed`` is null).
      4. data/themes_heatmap/themes_tree.json — Finviz theme tree, INVERTED to
         per-ticker subsector tags (theme fallback when no basket covers it).

    Sector fallback order: industry_map -> membership.parquet -> None.
    Theme fallback order:  baskets -> finviz tree (applied by ``_themes_for``).
    Cached module-level; ``_clear_caches()`` resets.
    """
    global _CLS_CACHE
    if _CLS_CACHE is not None:
        return _CLS_CACHE

    out: dict[str, dict] = {}
    meta = {"industry_map": 0, "membership_sector_fill": 0, "baskets": 0, "finviz": 0}

    def ent(ticker: str) -> dict:
        return out.setdefault(ticker, {"sector": None, "sub_industry": None,
                                       "themes": [], "finviz": []})

    # 1) S&P 500 heatmap industry map — the primary sector/sub-industry read
    try:
        p = config.data_dir() / "sp500_heatmap" / "industry_map.json"
        if p.exists():
            data = json.loads(p.read_text()) or {}
            for t, rec in data.items():
                tk = str(t).strip().upper()
                if not tk or not isinstance(rec, dict):
                    continue
                e = ent(tk)
                e["sector"] = rec.get("sector") or e["sector"]
                e["sub_industry"] = rec.get("sub_industry") or e["sub_industry"]
                meta["industry_map"] += 1
    except Exception:  # noqa: BLE001 — one source down must not kill the rest
        log.warning("load_classifications: industry_map.json unreadable — skipped",
                    exc_info=True)

    # 2) S&P 1500 membership ledger — sector fallback for names the map misses
    try:
        p = config.data_dir() / "universe" / "membership.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if "active" in df.columns:
                df = df[df["active"].astype(bool)]
            if "ticker" in df.columns and "sector" in df.columns:
                for rec in df[["ticker", "sector"]].dropna().to_dict("records"):
                    tk = str(rec["ticker"]).strip().upper()
                    sec = str(rec["sector"]).strip()
                    if not tk or not sec:
                        continue
                    e = ent(tk)
                    if not e["sector"]:
                        e["sector"] = sec
                        meta["membership_sector_fill"] += 1
    except Exception:  # noqa: BLE001
        log.warning("load_classifications: membership.parquet unreadable — skipped",
                    exc_info=True)

    # 3) Curated theme baskets — ACTIVE members only (removed is null)
    try:
        p = config.data_dir() / "baskets" / "membership.json"
        if p.exists():
            data = json.loads(p.read_text()) or {}
            for slug, b in (data.get("baskets") or {}).items():
                if not isinstance(b, dict):
                    continue
                tag = {"slug": str(slug), "name": b.get("name") or str(slug),
                       "name_zh": b.get("name_zh") or b.get("name") or str(slug),
                       "category": b.get("category")}
                for m in b.get("members") or []:
                    if not isinstance(m, dict) or m.get("removed") is not None:
                        continue
                    tk = str(m.get("ticker") or "").strip().upper()
                    if not tk:
                        continue
                    e = ent(tk)
                    if not any(th.get("slug") == tag["slug"] for th in e["themes"]):
                        e["themes"].append(dict(tag))
            meta["baskets"] = sum(1 for v in out.values() if v["themes"])
    except Exception:  # noqa: BLE001
        log.warning("load_classifications: baskets/membership.json unreadable — skipped",
                    exc_info=True)

    # 4) Finviz theme tree, inverted to per-ticker subsector tags
    try:
        p = config.data_dir() / "themes_heatmap" / "themes_tree.json"
        if p.exists():
            tree = json.loads(p.read_text()) or []
            for theme in tree:
                if not isinstance(theme, dict):
                    continue
                tname = theme.get("theme") or theme.get("key") or ""
                for sub in theme.get("subsectors") or []:
                    if not isinstance(sub, dict):
                        continue
                    skey = str(sub.get("key") or "")
                    sname = sub.get("name") or skey
                    for m in sub.get("members") or []:
                        tk = str(m or "").strip().upper()
                        if not tk or not skey:
                            continue
                        e = ent(tk)
                        if not any(f.get("subsector_key") == skey for f in e["finviz"]):
                            e["finviz"].append({"subsector_key": skey,
                                                "subsector_name": sname,
                                                "theme": tname})
            meta["finviz"] = sum(1 for v in out.values() if v["finviz"])
    except Exception:  # noqa: BLE001
        log.warning("load_classifications: themes_tree.json unreadable — skipped",
                    exc_info=True)

    meta["tickers"] = len(out)
    meta["with_sector"] = sum(1 for v in out.values() if v["sector"])
    meta["with_theme"] = sum(1 for v in out.values() if v["themes"] or v["finviz"])
    out["_meta"] = meta
    _CLS_CACHE = out
    return out


def _themes_for(ticker: str | None, cls: dict) -> list[dict]:
    """Theme tags for one ticker — curated baskets FIRST, Finviz subsector
    fallback only when no basket covers the name. PURE given the map.

    Returns ``[{key, label, label_zh, category, source}]`` (finviz keys are
    prefixed ``fv:`` so a basket slug and a Finviz subsector key can never
    collide into one cluster)."""
    if not ticker:
        return []
    info = cls.get(str(ticker).upper()) or {}
    tags: list[dict] = []
    for b in info.get("themes") or []:
        tags.append({"key": str(b.get("slug") or ""),
                     "label": str(b.get("name") or b.get("slug") or ""),
                     "label_zh": str(b.get("name_zh") or b.get("name") or ""),
                     "category": b.get("category"), "source": "basket"})
    if tags:
        return tags
    for f in info.get("finviz") or []:
        tags.append({"key": "fv:" + str(f.get("subsector_key") or ""),
                     "label": str(f.get("subsector_name") or ""),
                     "label_zh": str(f.get("subsector_name") or ""),
                     "category": f.get("theme"), "source": "finviz"})
    return tags


# --------------------------------------------------------------------------- #
# Conviction composite (pure)                                                   #
# --------------------------------------------------------------------------- #

def add_streak(actions: list | None) -> int:
    """Consecutive MOST-RECENT quarters with action in {new, add} for one name.

    ``actions`` is the fund's per-quarter action list for the ticker, ASCENDING
    by quarter (oldest first), with ``None`` for quarters where the name was not
    in the fund's diffable book. Counting starts at the latest quarter and stops
    at the first non-buy action (hold/trim/exit/None all break the streak).
    Derived look-ahead-free from the data/smart_money/<slug> snapshots only. PURE.
    """
    if not actions:
        return 0
    n = 0
    for a in reversed(list(actions)):
        if a in _BUY_ACTIONS:
            n += 1
        else:
            break
    return n


def conviction_score(pos: dict, book_positions: list[dict],
                     snap_history_actions: list | None = None,
                     weights: dict | None = None) -> dict:
    """Descriptive 0-100 conviction composite for one position. PURE.

    Components (each carried in the output with its raw ``value`` and earned
    ``points`` so the composite is fully transparent on the page):

      * ``pct_book``    — percentile of the position's pct-of-book within the
                          fund's resolved book (share of positions with
                          pct_book <= this one's); points = w * percentile.
      * ``rank_top10``  — position_rank <= 10 (binary).
      * ``tilt``        — tilt_pp > 0, i.e. overweight vs the fund's mean
                          allocation slot (binary).
      * ``add_streak``  — consecutive most-recent new/add quarters from
                          ``snap_history_actions`` (see :func:`add_streak`);
                          points scale linearly, capped at ``_STREAK_CAP_Q``.
      * ``new_at_size`` — a NEW position opened at >= 2% of the book (binary).
      * ``persisted``   — ``pos['persistence'] == 'persisted'`` (the
                          engine.smart_money window-dressing flag; binary).

    ``weights`` overrides the config-mirroring defaults (unknown keys ignored);
    callers wire config ``smart_money.conviction`` through here so this function
    stays pure. Tier: high >= 70, moderate >= 45, low below — thresholds assume
    weights summing to 100.

    Returns ``{score, tier, components: {name: {value, points}}}``.
    Missing/None fields simply earn 0 points — never raise.
    """
    w = dict(_DEFAULT_WEIGHTS)
    if weights:
        for k, v in weights.items():
            if k in _DEFAULT_WEIGHTS and v is not None:
                try:
                    w[k] = float(v)
                except (TypeError, ValueError):
                    continue

    # pct-of-book percentile within the fund (degenerate one-position book -> 1.0)
    x = pos.get("pct_book")
    vals = [float(p["pct_book"]) for p in (book_positions or [])
            if isinstance(p, dict) and p.get("pct_book") is not None]
    if x is None or not vals:
        pctile = 0.0
    else:
        pctile = sum(1 for v in vals if v <= float(x)) / len(vals)
    pts_pct = w["w_pct_book"] * pctile

    rank = pos.get("position_rank")
    rank_hit = rank is not None and not pd.isna(rank) and 1 <= float(rank) <= 10
    pts_rank = w["w_rank_top10"] if rank_hit else 0.0

    tilt = pos.get("tilt_pp")
    tilt_hit = tilt is not None and not pd.isna(tilt) and float(tilt) > 0
    pts_tilt = w["w_tilt"] if tilt_hit else 0.0

    streak = add_streak(snap_history_actions)
    pts_streak = w["w_add_streak"] * min(streak, _STREAK_CAP_Q) / float(_STREAK_CAP_Q)

    new_hit = (pos.get("action") == "new"
               and float(pos.get("pct_book") or 0.0) >= _NEW_AT_SIZE_MIN_PCT)
    pts_new = w["w_new_at_size"] if new_hit else 0.0

    persisted_hit = pos.get("persistence") == "persisted"
    pts_persist = w["w_persisted"] if persisted_hit else 0.0

    score = round(pts_pct + pts_rank + pts_tilt + pts_streak + pts_new + pts_persist, 1)
    tier = ("high" if score >= _TIER_HIGH
            else "moderate" if score >= _TIER_MODERATE else "low")
    return {
        "score": score,
        "tier": tier,
        "components": {
            "pct_book": {"value": round(pctile, 3), "points": round(pts_pct, 2)},
            "rank_top10": {"value": (int(rank) if rank_hit else
                                     (None if rank is None or pd.isna(rank) else int(rank))),
                           "points": round(pts_rank, 2)},
            "tilt": {"value": (None if tilt is None or pd.isna(tilt)
                               else round(float(tilt), 3)),
                     "points": round(pts_tilt, 2)},
            "add_streak": {"value": int(streak), "points": round(pts_streak, 2)},
            "new_at_size": {"value": bool(new_hit), "points": round(pts_new, 2)},
            "persisted": {"value": pos.get("persistence"), "points": round(pts_persist, 2)},
        },
    }


# --------------------------------------------------------------------------- #
# Snapshot history — resolved once per fund, shared by book + series            #
# --------------------------------------------------------------------------- #

def _resolved_history(slug: str, name_map: dict[str, str],
                      cusip_map: dict[str, str]) -> list[tuple[str, str, pd.DataFrame]]:
    """Every retained snapshot for a fund as a slim RESOLVED frame, ascending:
    ``[(period_end, filing_date, df[cusip, issuer, shares, value_usd, ticker,
    sh_type])]``. Equity (SH) lines only, grouped by cusip, ticker attached via
    ``resolve_tickers`` (None where unresolved — kept, so book totals and the
    'Unclassified' bucket stay honest).

    Cached per slug (the maps are stable within one build run); call
    ``_clear_caches()`` before re-resolving with different maps. A malformed
    quarter is skipped with a debug log, never raised."""
    if slug in _HIST_CACHE:
        return _HIST_CACHE[slug]
    out: list[tuple[str, str, pd.DataFrame]] = []
    for period_end, filing_date, df in _read_all(slug):
        try:
            eq = df[df.get("sh_type", "SH") == "SH"].copy()
            if eq.empty:
                continue
            g = (eq.groupby("cusip", as_index=False)
                   .agg(issuer=("issuer", "first"), shares=("shares", "sum"),
                        value_usd=("value_usd", "sum")))
            g = resolve_tickers(g, name_map, cusip_map)
            g["sh_type"] = "SH"                      # keep diff_snapshots happy on slims
            out.append((period_end, filing_date, g))
        except Exception:  # noqa: BLE001 — one bad quarter must not drop the fund
            log.debug("_resolved_history: %s quarter %s skipped", slug, period_end,
                      exc_info=True)
    _HIST_CACHE[slug] = out
    return out


def _cusip_ticker_map(hist: list[tuple[str, str, pd.DataFrame]]) -> dict[str, str]:
    """Union cusip -> ticker map across a fund's resolved snapshots (latest wins;
    resolution is quarter-independent so the union is self-consistent). PURE."""
    cmap: dict[str, str] = {}
    for _pe, _fd, sdf in hist:
        if "cusip" not in sdf.columns or "ticker" not in sdf.columns:
            continue
        for c, t in zip(sdf["cusip"], sdf["ticker"]):
            if t is None or (not isinstance(t, str) and pd.isna(t)):
                continue
            cmap[str(c)] = str(t)
    return cmap


def _ticker_moves(prev: pd.DataFrame | None, cur: pd.DataFrame,
                  cmap: dict[str, str]) -> pd.DataFrame:
    """Ticker-level position moves between two resolved slim snapshots. PURE
    given the frames. Diffs at cusip level via ``diff_snapshots``, attaches the
    already-resolved tickers, drops unresolved lines, then collapses dual-class
    / multi-lot lines onto one row per ticker (sum weight/value/shares, largest
    lot's action) — the exact compute_smart_money collapse so a fund is never
    double-counted across share classes."""
    diff = diff_snapshots(prev, cur)
    if diff.empty:
        return pd.DataFrame(columns=_MOVE_COLS)
    diff = diff.copy()
    diff["ticker"] = diff["cusip"].astype(str).map(cmap)
    diff = diff[diff["ticker"].notna()]
    if diff.empty:
        return pd.DataFrame(columns=_MOVE_COLS)
    return (diff.sort_values("value_usd", ascending=False)
            .groupby("ticker", as_index=False)
            .agg(issuer=("issuer", "first"), action=("action", "first"),
                 pct_portfolio=("pct_portfolio", "sum"),
                 value_usd=("value_usd", "sum"), shares=("shares", "sum"),
                 shares_change_pct=("shares_change_pct", "first")))


# --------------------------------------------------------------------------- #
# Full latest book                                                              #
# --------------------------------------------------------------------------- #

def fund_book(slug: str, name_map: dict[str, str], cusip_map: dict[str, str],
              cls: dict, panel: ClosePanel | None,
              weights: dict | None = None) -> list[dict]:
    """FULL resolved latest book for one fund (every position, not top-8).

    Each row: ``{ticker, issuer, shares, value_usd, pct_book, position_rank,
    tilt_pp, action, shares_change_pct, add_streak_q, persistence, conviction,
    sector, themes (<=3 {key, name, name_zh}), since_excess, period_end,
    filing_date}`` sorted by position_rank ascending.

    * ``pct_book`` is the share of the WHOLE reported equity book (unresolved
      lines included in the denominator — coverage-honest).
    * ``action`` / ``shares_change_pct`` come from the latest quarter's diff;
      full exits are NOT book rows (they are rotation, not holdings).
    * ``since_excess`` = SPY-excess from the fund's public filing date to the
      latest close via the SHARED ``panel`` (variable hold — the tracker's
      realized-P&L convention, not a fixed-horizon skill figure).
    * ``conviction`` = :func:`conviction_score` with the fund's whole book as
      the percentile reference and the look-ahead-free per-quarter action list.

    Degrades to [] (logged) on any fund-level failure; a single bad row is
    skipped, never raised.
    """
    try:
        hist = _resolved_history(slug, name_map, cusip_map)
        if not hist:
            return []
        period_end, filing_date, _latest = hist[-1]
        cmap = _cusip_ticker_map(hist)

        # per-quarter ticker-level moves for consecutive snapshot pairs (ascending).
        # The FIRST retained quarter has no prior -> excluded from the action
        # history (an all-"new" backfill artifact must not seed streaks).
        pair_moves: list[tuple[str, pd.DataFrame]] = []
        for i in range(1, len(hist)):
            pair_moves.append((hist[i][0], _ticker_moves(hist[i - 1][2], hist[i][2], cmap)))
        if pair_moves:
            latest_moves = pair_moves[-1][1]
            qmaps = [dict(zip(m["ticker"], m["action"])) for _pe, m in pair_moves]
        else:                                        # single retained snapshot
            latest_moves = _ticker_moves(None, hist[0][2], cmap)
            qmaps = []                               # no look-ahead-free history yet

        if latest_moves.empty:
            return []
        live = latest_moves[latest_moves["action"] != "exit"]
        if live.empty:
            return []
        ranked = position_rank_and_tilt(live)

        book: list[dict] = []
        acts_by_ticker: dict[str, list] = {}
        for rec in ranked.to_dict("records"):
            try:
                t = str(rec.get("ticker") or "")
                if not t:
                    continue
                actions = [q.get(t) for q in qmaps]
                acts_by_ticker[t] = actions

                since_val = None
                if panel is not None and filing_date:
                    try:
                        ex = panel.excess(t, filing_date)
                        since_val = ex["excess"] if ex else None
                    except Exception:  # noqa: BLE001 — price gap never kills the book
                        log.debug("fund_book: since_excess failed for %s/%s", slug, t,
                                  exc_info=True)

                rank = rec.get("rank")
                tilt = rec.get("tilt_pp")
                scp = rec.get("shares_change_pct")
                sh = rec.get("shares")
                book.append({
                    "ticker": t,
                    "issuer": str(rec.get("issuer") or ""),
                    "shares": (None if sh is None or pd.isna(sh) else float(sh)),
                    "value_usd": round(float(rec.get("value_usd") or 0.0), 0),
                    "pct_book": round(float(rec.get("pct_portfolio") or 0.0), 2),
                    "position_rank": (None if rank is None or pd.isna(rank) else int(rank)),
                    "tilt_pp": (None if tilt is None or pd.isna(tilt)
                                else round(float(tilt), 3)),
                    "action": rec.get("action"),
                    "shares_change_pct": (None if scp is None or pd.isna(scp)
                                          else round(float(scp), 1)),
                    "add_streak_q": add_streak(actions),
                    "persistence": window_dressing_flag(hist, t),
                    "sector": (cls.get(t) or {}).get("sector") if isinstance(cls, dict) else None,
                    "themes": [{"key": th["key"], "name": th["label"],
                                "name_zh": th["label_zh"]}
                               for th in _themes_for(t, cls)[:_MAX_THEMES_PER_POSITION]],
                    "since_excess": since_val,
                    "period_end": period_end,
                    "filing_date": filing_date,
                })
            except Exception:  # noqa: BLE001 — one bad row must not drop the book
                log.debug("fund_book: %s row skipped", slug, exc_info=True)

        # second pass: conviction needs the WHOLE book for the percentile leg
        for pos in book:
            pos["conviction"] = conviction_score(
                pos, book, acts_by_ticker.get(pos["ticker"]), weights=weights)

        book.sort(key=lambda p: (p["position_rank"] is None, p["position_rank"] or 0))
        return book
    except Exception:  # noqa: BLE001 — degrade, never break the desk build
        log.warning("fund_book: %s failed — returning empty book", slug, exc_info=True)
        return []


# --------------------------------------------------------------------------- #
# Sector / theme series + rotation                                              #
# --------------------------------------------------------------------------- #

def sector_series(slug: str, name_map: dict[str, str], cusip_map: dict[str, str],
                  cls: dict) -> list[dict]:
    """Value-weighted sector (and top theme-category) mix per retained quarter,
    ascending: ``[{period_end, filing_date, weights: {sector: pct},
    top_theme_weights: {category: pct}}]``.

    Unresolved lines and resolved-but-unmapped names are bucketed as
    ``"Unclassified"`` with their honest pct (the denominator is the whole
    reported book). Theme categories use each name's PRIMARY (first) curated
    basket; theme coverage is partial by design so category weights do not sum
    to 100. F12: today's map applied to history — see ``METHOD_NOTE_EN``.
    Degrades to [] on failure; a malformed quarter is skipped."""
    try:
        hist = _resolved_history(slug, name_map, cusip_map)
    except Exception:  # noqa: BLE001
        log.warning("sector_series: %s history unavailable", slug, exc_info=True)
        return []
    out: list[dict] = []
    for period_end, filing_date, sdf in hist:
        try:
            total = float(pd.to_numeric(sdf["value_usd"], errors="coerce").fillna(0.0).sum())
            if total <= 0:
                continue
            sec_v: dict[str, float] = {}
            cat_v: dict[str, float] = {}
            for rec in sdf.to_dict("records"):
                v = float(rec.get("value_usd") or 0.0)
                if v <= 0:
                    continue
                t = rec.get("ticker")
                tk = str(t) if isinstance(t, str) and t else None
                info = (cls.get(tk) if isinstance(cls, dict) and tk else None) or {}
                sec = info.get("sector") or _UNCLASSIFIED
                sec_v[sec] = sec_v.get(sec, 0.0) + v
                themes = info.get("themes") or []
                if themes:
                    cat = themes[0].get("category")
                    if cat:
                        cat_v[cat] = cat_v.get(cat, 0.0) + v
            weights = {k: round(100.0 * v / total, 2)
                       for k, v in sorted(sec_v.items(), key=lambda kv: -kv[1])}
            top_theme = {k: round(100.0 * v / total, 2)
                         for k, v in sorted(cat_v.items(), key=lambda kv: -kv[1])[:6]}
            out.append({"period_end": period_end, "filing_date": filing_date,
                        "weights": weights, "top_theme_weights": top_theme})
        except Exception:  # noqa: BLE001
            log.debug("sector_series: %s quarter %s skipped", slug, period_end,
                      exc_info=True)
    return out


def sector_rotation(series: list[dict]) -> dict:
    """Latest quarter-over-quarter sector rotation from a :func:`sector_series`
    list. PURE.

    Returns ``{into: [{sector, delta_pp}] top-3 desc, out_of: [...] top-3 most
    negative, deltas: {sector: delta_pp} (full union, sorted desc), period_end,
    prev_period_end, method_note}``. The ``"Unclassified"`` bucket stays in
    ``deltas`` (honesty) but is excluded from the into/out_of boards — a
    resolution-coverage shift is not a sector rotation. <2 quarters -> empty
    boards, never an error."""
    method_note = {"en": METHOD_NOTE_EN, "zh": METHOD_NOTE_ZH}
    if not series or len(series) < 2:
        return {"into": [], "out_of": [], "deltas": {},
                "period_end": ((series[-1] or {}).get("period_end") if series else None),
                "prev_period_end": None, "method_note": method_note}
    prev, cur = (series[-2] or {}), (series[-1] or {})
    pw, cw = (prev.get("weights") or {}), (cur.get("weights") or {})
    deltas = {k: round(float(cw.get(k, 0.0)) - float(pw.get(k, 0.0)), 2)
              for k in set(pw) | set(cw)}
    deltas = dict(sorted(deltas.items(), key=lambda kv: -kv[1]))
    movers = [(k, d) for k, d in deltas.items() if k != _UNCLASSIFIED]
    into = [{"sector": k, "delta_pp": d}
            for k, d in sorted(movers, key=lambda kv: -kv[1]) if d > 0][:3]
    out_of = [{"sector": k, "delta_pp": d}
              for k, d in sorted(movers, key=lambda kv: kv[1]) if d < 0][:3]
    return {"into": into, "out_of": out_of, "deltas": deltas,
            "period_end": cur.get("period_end"),
            "prev_period_end": prev.get("period_end"),
            "method_note": method_note}


# --------------------------------------------------------------------------- #
# Core-lean synthesis                                                           #
# --------------------------------------------------------------------------- #

def theme_read(book: list[dict], buys: list[dict], cls: dict) -> dict:
    """Cluster the latest quarter's new/add positions by theme — the fund's
    "core lean" synthesis. PURE given the classification map.

    ``buys`` = the book rows with action in {new, add}. Themes come from the
    curated baskets first, Finviz subsectors as fallback (per ticker). Returns
    ``{leans: [{theme_key, label, label_zh, category, source, tickers,
    added_pp, held_pp, n_names}] ranked by added_pp desc (cap 6),
    core: leans[0] | None, narrative_en, narrative_zh}``.

    * ``added_pp`` — sum of pct_book across this quarter's buys in the theme.
    * ``held_pp``  — sum of pct_book across ALL current holdings in the theme.
    * ``n_names``  — count of current holdings in the theme.

    The narratives are TEMPLATE strings (never an LLM call), e.g.
    "Core lean: AI Infrastructure — added SNDK, TSM, VST (+9.3pp of book this
    quarter)". Descriptive framing only."""
    clusters: dict[str, dict] = {}

    def slot(tag: dict) -> dict:
        return clusters.setdefault(tag["key"], {
            "theme_key": tag["key"], "label": tag["label"], "label_zh": tag["label_zh"],
            "category": tag.get("category"), "source": tag.get("source"),
            "tickers": [], "added_pp": 0.0, "held_pp": 0.0, "n_names": 0})

    ordered_buys = sorted((p for p in (buys or []) if isinstance(p, dict)),
                          key=lambda p: -(float(p.get("pct_book") or 0.0)))
    for p in ordered_buys:
        pct = float(p.get("pct_book") or 0.0)
        for tag in _themes_for(p.get("ticker"), cls):
            c = slot(tag)
            c["added_pp"] += pct
            if p.get("ticker") and p["ticker"] not in c["tickers"]:
                c["tickers"].append(p["ticker"])

    for p in (book or []):
        if not isinstance(p, dict):
            continue
        pct = float(p.get("pct_book") or 0.0)
        for tag in _themes_for(p.get("ticker"), cls):
            if tag["key"] in clusters:               # only buy-clusters are leans
                clusters[tag["key"]]["held_pp"] += pct
                clusters[tag["key"]]["n_names"] += 1

    leans = sorted((c for c in clusters.values() if c["added_pp"] > 0),
                   key=lambda c: -c["added_pp"])[:_MAX_LEANS]
    for c in leans:
        c["added_pp"] = round(c["added_pp"], 2)
        c["held_pp"] = round(c["held_pp"], 2)

    core = leans[0] if leans else None
    if core:
        head = core["tickers"][:_MAX_NARRATIVE_TICKERS]
        more = "…" if len(core["tickers"]) > _MAX_NARRATIVE_TICKERS else ""
        narrative_en = (f"Core lean: {core['label']} — added {', '.join(head)}{more} "
                        f"(+{core['added_pp']:.1f}pp of book this quarter)")
        narrative_zh = (f"核心倾向：{core['label_zh']} — 本季度加仓 {'、'.join(head)}{more}"
                        f"（占组合 +{core['added_pp']:.1f}pp）")
    else:
        narrative_en = ("No thematic add cluster this quarter — the latest buys "
                        "do not map to a tracked theme.")
        narrative_zh = "本季度无主题性加仓集群——最新买入未映射到任何跟踪主题。"

    return {"leans": leans, "core": core,
            "narrative_en": narrative_en, "narrative_zh": narrative_zh}


# --------------------------------------------------------------------------- #
# Orchestrator                                                                  #
# --------------------------------------------------------------------------- #

def _book_meta(slug: str, name_map: dict[str, str], cusip_map: dict[str, str]) -> dict:
    """Latest-book coverage meta for one fund: ``{n_positions, n_resolved,
    resolution_pct, book_value_usd, filing_date, period_end}`` (n_positions =
    distinct cusip lines in the latest equity snapshot). {} on failure."""
    try:
        hist = _resolved_history(slug, name_map, cusip_map)
        if not hist:
            return {}
        period_end, filing_date, sdf = hist[-1]
        n_pos = int(len(sdf))
        n_res = int(sdf["ticker"].notna().sum()) if "ticker" in sdf.columns else 0
        total = float(pd.to_numeric(sdf["value_usd"], errors="coerce").fillna(0.0).sum())
        return {"n_positions": n_pos, "n_resolved": n_res,
                "resolution_pct": (round(100.0 * n_res / n_pos, 1) if n_pos else None),
                "book_value_usd": round(total, 0),
                "filing_date": filing_date, "period_end": period_end}
    except Exception:  # noqa: BLE001
        log.debug("_book_meta: %s failed", slug, exc_info=True)
        return {}


def build_fund_intel(cfg: dict | None = None, tracker: dict | None = None) -> dict | None:
    """Build the per-fund intelligence payload for every tracked fund.

    ``cfg`` is the ``smart_money`` config block (defaults to config.yml's);
    ``tracker`` is the engine.manager_trades.compute_tracker() payload — used
    only to stamp each fund's A-D grade for display (None-tolerant).

    Returns ``{built, funds: {slug: {slug, name, style, grade, book, book_meta,
    sector_series (list, ascending), sector_rotation, theme_read}}, _meta}`` or
    None when no funds are configured. ONE shared ClosePanel prices every
    fund's since_excess; each fund is wrapped in its own try/except so a single
    bad fund degrades to absence, never a build failure."""
    cfg = cfg if cfg is not None else (config.load().get("smart_money", {}) or {})
    funds = cfg.get("funds", {}) or {}
    if not funds:
        return None

    conv_cfg = cfg.get("conviction", {}) or {}
    weights: dict[str, float] = {}
    for k, d in _DEFAULT_WEIGHTS.items():
        try:
            weights[k] = float(conv_cfg.get(k, d))
        except (TypeError, ValueError):              # malformed YAML -> default, log once
            log.warning("build_fund_intel: bad conviction weight %s=%r — using %s",
                        k, conv_cfg.get(k), d)
            weights[k] = d

    cls = load_classifications()
    name_map = name_ticker_map()
    cusip_map, _figi_meta = full_cusip_map()

    try:
        panel: ClosePanel | None = ClosePanel()      # ONE shared panel — never per-fund
    except Exception:  # noqa: BLE001 — priceless build still ships 13F analytics
        log.warning("build_fund_intel: ClosePanel unavailable — since_excess will be null")
        panel = None

    grades: dict[str, str] = {}
    try:
        for r in (tracker or {}).get("leaderboard") or []:
            g = r.get("grade")
            if r.get("slug") and g and g != "n/a":
                grades[r["slug"]] = g
    except Exception:  # noqa: BLE001 — malformed tracker just means ungraded display
        log.debug("build_fund_intel: tracker leaderboard unreadable", exc_info=True)

    funds_out: dict[str, dict] = {}
    failed: list[str] = []
    for slug, spec in funds.items():
        try:
            spec = spec or {}
            book = fund_book(slug, name_map, cusip_map, cls, panel, weights=weights)
            series = sector_series(slug, name_map, cusip_map, cls)
            rotation = sector_rotation(series)
            buys = [p for p in book if p.get("action") in _BUY_ACTIONS]
            funds_out[slug] = {
                "slug": slug,
                "name": spec.get("name", slug),
                "style": spec.get("style"),
                "grade": grades.get(slug),
                "book": book,
                "book_meta": _book_meta(slug, name_map, cusip_map),
                "sector_series": series,
                "sector_rotation": rotation,
                "theme_read": theme_read(book, buys, cls),
            }
        except Exception:  # noqa: BLE001 — one fund down, 49 still ship
            log.warning("build_fund_intel: %s failed — skipped", slug, exc_info=True)
            failed.append(slug)

    return {
        "built": datetime.now(timezone.utc).isoformat(),
        "funds": funds_out,
        "_meta": {
            "n_funds": len(funds),
            "n_ok": len(funds_out),
            "n_failed": len(failed),
            "failed": failed,
            "classification": (cls.get("_meta") if isinstance(cls, dict) else None),
            "price_thru": (panel.thru if panel is not None else None),
            "conviction_weights": weights,
            "conviction_weights_version": CONVICTION_WEIGHTS_VERSION,
            "conviction_method": {"en": CONVICTION_METHOD_EN, "zh": CONVICTION_METHOD_ZH},
            "method_note": {"en": METHOD_NOTE_EN, "zh": METHOD_NOTE_ZH},
        },
    }
