"""engine/china_narrative_tags.py — W2-A: per-name narrative heat tags for the China board.

Answers: "which theme basket is a name part of, how hot is that basket, and does
the narrative radar have additional context?"

FUNCTIONS
  narrative_heat(closes, memberships_curated, memberships_ths, bench) -> dict
      Per-basket heat records. Call once per build and pass the result to name_tags().

  name_tags(heat, memberships_curated, memberships_ths, radar) -> dict
      Per-ticker strongest qualifying theme tag + radar join.

  build_narrative_tags() -> dict
      Convenience loader: reads all data sources, calls the two functions above,
      returns {"heat": ..., "tags": ..., "as_of": ...}. Safe to call from builders.

SPEC (W2 of the China Alpha Program — masterplan F4 / OWNER_RATIONALE §2/S3/S4)
  rel20   = basket EW 20d return vs CSI300 (from basket artifact perf["20d"]["rel"])
            OR computed directly from member closes + benchmark when the full basket
            artifact is not available (same math, vectorised).
  breadth = pct of active basket members whose last close is above their 20d MA.
  HOT     = rel20 >= +5pp AND breadth >= 60pct
  WARMING = rel20 >= 0    AND breadth >= 50pct
  else    = no tag (None level)

  Thresholds are documented display heuristics, logged to the ledger so W6 can
  calibrate them from forward grades.

PER-NAME TAG
  Strongest qualifying theme (by rel20) the name belongs to:
    {theme, level, rel20, breadth, source, n_members, n_covered}
  PLUS radar join (if the name appears in any china_narrative_radar basket):
    {basket_id, narr_rank, global_ai}

A/B TIER (display + ledger ONLY — rank influence NOT wired in W2)
  A = stage in {ENTRY, RIPENING} AND (theme HOT OR radar basket with global_ai
      honesty in {validated, partial})
  B = stage in {ENTRY, RIPENING} without that
  RAN_LATE rows get NO tier (tier=None).

HONESTY LAW (§754 / §773 — carried from china_narrative_radar)
  Narrative/theme momentum is a DESCRIPTIVE positioning lens, NOT validated alpha,
  NOT a buy list. Every user-visible element using these tags must carry this framing.

GRACEFUL DEGRADATION
  Any missing artifact -> empty tags, warning logged with counts. The board renders
  without narrative data — this module never raises, never crashes the build.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# ── Spec constants ────────────────────────────────────────────────────────────
HOT_REL20_THRESHOLD   = 5.0    # pp relative to CSI300
HOT_BREADTH_THRESHOLD = 0.60   # fraction of members above 20d MA

WARM_REL20_THRESHOLD   = 0.0   # pp
WARM_BREADTH_THRESHOLD = 0.50  # fraction

# Stages that qualify for A/B tiers
_TIERABLE_STAGES = {"ENTRY", "RIPENING"}

# radar global_ai honesty tags that qualify for A-tier
_A_TIER_HONESTY = {"validated", "partial"}

# Minimum active members to compute heat for a basket
_MIN_BASKET_MEMBERS = 3

# 20d window length (members above this rolling mean = breadth)
_BREADTH_WINDOW = 20

BENCHMARK_TICKER = "510300.SS"   # CSI 300 ETF


# ── Data loaders (kept separate so tests can monkeypatch) ─────────────────────

def _load_closes() -> pd.DataFrame | None:
    """Wide [Date x ticker] daily closes from data/china_search/closes.parquet."""
    p = config.ROOT / "data" / "china_search" / "closes.parquet"
    if not p.exists():
        log.warning("china_narrative_tags: closes.parquet not found at %s", p)
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df = df.loc[:, ~df.columns.duplicated()]
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("china_narrative_tags: closes.parquet unreadable: %s", exc)
        return None


def _load_benchmark() -> pd.Series | None:
    """CSI 300 benchmark close series aligned to the closes index."""
    try:
        bench_df = store.read("china", BENCHMARK_TICKER)
        if bench_df is None or "close" not in bench_df.columns:
            log.warning("china_narrative_tags: benchmark %s not found", BENCHMARK_TICKER)
            return None
        return bench_df["close"]
    except Exception as exc:  # noqa: BLE001
        log.warning("china_narrative_tags: benchmark load failed: %s", exc)
        return None


def _load_membership(path: Path) -> dict | None:
    """Load a membership.json; return None on any failure."""
    if not path.exists():
        log.warning("china_narrative_tags: membership not found at %s", path)
        return None
    try:
        raw = json.loads(path.read_text())
        return raw.get("baskets") or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("china_narrative_tags: membership unreadable at %s: %s", path, exc)
        return None


def _curated_membership() -> dict | None:
    return _load_membership(config.ROOT / "data" / "baskets_china" / "membership.json")


def _ths_membership() -> dict | None:
    return _load_membership(config.ROOT / "data" / "baskets_china_ths" / "membership.json")


# ── Active-members extractor (mirrors china_narrative_radar._basket_members) ──

def _active_members(basket_val: dict | list) -> list[dict]:
    """Return active (not removed) member records from a basket entry."""
    if isinstance(basket_val, list):
        rows = basket_val
    else:
        rows = basket_val.get("members") or basket_val.get("tickers") or []
    out = []
    for r in rows:
        if isinstance(r, dict):
            if r.get("removed") is None:
                out.append(r)
        else:
            out.append({"ticker": str(r), "name_zh": str(r)})
    return out


# ── Core compute ──────────────────────────────────────────────────────────────

def _basket_rel20_breadth(
    basket_id: str,
    basket_val: dict | list,
    closes: pd.DataFrame,
    bench_ret20: float | None,
) -> dict | None:
    """Compute rel20 and breadth for one basket.

    Returns None if fewer than _MIN_BASKET_MEMBERS have price data.
    """
    members = _active_members(basket_val)
    tickers = [m["ticker"] for m in members]
    covered = [t for t in tickers if t in closes.columns]
    n_members = len(members)
    n_covered  = len(covered)

    if n_covered < _MIN_BASKET_MEMBERS:
        return None

    # Equal-weight 20d return of the basket
    # Use the panel slice directly (vectorised) — same approach as baskets_region._perf
    sub = closes[covered]
    rets = sub.pct_change(fill_method=None)
    ew_ret = rets.mean(axis=1, skipna=True)  # cross-section mean daily return
    ew_level = (1.0 + ew_ret.fillna(0.0)).cumprod()

    if len(ew_level) < _BREADTH_WINDOW + 1:
        return None

    raw20 = float(ew_level.iloc[-1] / ew_level.iloc[-(_BREADTH_WINDOW + 1)] - 1.0) * 100.0
    rel20 = (raw20 - bench_ret20 * 100.0) if bench_ret20 is not None else raw20

    # Breadth: fraction of covered members above their own 20d MA at last date
    last_prices = sub.iloc[-1]
    ma20 = sub.iloc[-_BREADTH_WINDOW:].mean(axis=0)
    above = (last_prices > ma20).sum()
    valid = last_prices.notna().sum()
    breadth = float(above) / float(valid) if valid > 0 else 0.0

    # Grade the same precision we publish. Otherwise a tiny negative raw value
    # can be emitted as -0.0 while retaining a None level, making the record
    # contradict its documented threshold contract.
    rel20_display = round(rel20, 2)
    breadth_display = round(breadth, 4)

    # Heat level
    if rel20_display >= HOT_REL20_THRESHOLD and breadth_display >= HOT_BREADTH_THRESHOLD:
        level: str | None = "HOT"
    elif rel20_display >= WARM_REL20_THRESHOLD and breadth_display >= WARM_BREADTH_THRESHOLD:
        level = "WARMING"
    else:
        level = None

    # Name/meta from basket entry
    if isinstance(basket_val, dict):
        name    = basket_val.get("name", basket_id)
        name_zh = basket_val.get("name_zh", basket_id)
    else:
        name = name_zh = basket_id

    return {
        "basket_id": basket_id,
        "name":      name,
        "name_zh":   name_zh,
        "level":     level,
        "rel20":     rel20_display,
        "breadth":   breadth_display,
        "n_members": n_members,
        "n_covered": n_covered,
    }


def narrative_heat(
    closes: pd.DataFrame | None,
    memberships_curated: dict | None,
    memberships_ths: dict | None,
    bench_series: pd.Series | None,
) -> dict[str, dict]:
    """Compute per-basket heat records.

    Parameters
    ----------
    closes              Wide [Date x ticker] daily close matrix.
    memberships_curated Curated basket membership dict (id -> basket_val).
    memberships_ths     THS basket membership dict (id -> basket_val).
    bench_series        CSI 300 close series (used to compute bench_ret20).

    Returns
    -------
    dict mapping basket_id -> heat record:
      { basket_id, name, name_zh, level, rel20, breadth, source, n_members, n_covered }
    Level is "HOT", "WARMING", or None (unqualified).
    Empty dict on any critical failure.
    """
    if closes is None or closes.empty:
        log.warning("china_narrative_tags.narrative_heat: no closes — returning empty heat")
        return {}

    # Bench 20d return (as a fraction, not percentage)
    bench_ret20: float | None = None
    if bench_series is not None:
        bench_aligned = bench_series.reindex(closes.index).ffill()
        if len(bench_aligned.dropna()) > _BREADTH_WINDOW:
            bench_ret20 = float(
                bench_aligned.iloc[-1] / bench_aligned.iloc[-(_BREADTH_WINDOW + 1)] - 1.0
            )

    heat: dict[str, dict] = {}
    skipped = 0

    for source_label, mem_dict in [
        ("curated", memberships_curated),
        ("THS",     memberships_ths),
    ]:
        if not mem_dict:
            log.warning("china_narrative_tags.narrative_heat: no %s memberships", source_label)
            continue
        for bid, bval in mem_dict.items():
            if not isinstance(bval, (dict, list)):
                continue
            rec = _basket_rel20_breadth(bid, bval, closes, bench_ret20)
            if rec is None:
                skipped += 1
                continue
            rec["source"] = source_label
            heat[bid] = rec

    log.info(
        "china_narrative_tags.narrative_heat: %d baskets computed, %d skipped (coverage < %d)",
        len(heat), skipped, _MIN_BASKET_MEMBERS,
    )
    return heat


def _ticker_to_baskets(mem_dict: dict | None) -> dict[str, list[str]]:
    """Invert a membership dict: ticker -> [basket_id, ...]."""
    if not mem_dict:
        return {}
    out: dict[str, list[str]] = {}
    for bid, bval in mem_dict.items():
        for m in _active_members(bval):
            t = m.get("ticker") or m.get("symbol")
            if t:
                out.setdefault(t, []).append(bid)
    return out


def _build_radar_index(radar: dict | None) -> dict[str, dict]:
    """Index radar baskets by member ticker for O(1) lookup.

    Returns {ticker -> {basket_id, rank_63d, global_ai}} using the first (highest-ranked)
    basket the ticker appears in. Tolerates missing keys in the radar dict.
    """
    if not radar or not radar.get("baskets"):
        return {}
    index: dict[str, dict] = {}
    for basket in radar.get("baskets", []):
        bid   = basket.get("id", "")
        rank  = basket.get("rank_63d")
        gai   = basket.get("global_ai")   # may be None for non-AI baskets
        for m in basket.get("top_members", []):
            t = m.get("ticker")
            if t and t not in index:
                index[t] = {
                    "basket_id": bid,
                    "narr_rank": rank,
                    "global_ai": gai,   # {mom_4w_pct, direction, validated_tag, as_of} | None
                }
    return index


def name_tags(
    heat: dict[str, dict],
    memberships_curated: dict | None,
    memberships_ths: dict | None,
    radar: dict | None,
) -> dict[str, dict]:
    """Build per-ticker narrative tag dict.

    For each ticker, resolves:
      - strongest qualifying theme tag (by rel20) from heat + memberships
      - radar join if the ticker appears in any china_narrative_radar basket

    Parameters
    ----------
    heat                Output of narrative_heat().
    memberships_curated Curated basket membership dict.
    memberships_ths     THS basket membership dict.
    radar               Output of engine.china_narrative_radar.build_radar(). May be None.

    Returns
    -------
    dict mapping ticker -> tag dict:
    {
      theme:    str,           # basket display name
      theme_zh: str,
      basket_id: str,
      level:    "HOT" | "WARMING" | None,
      rel20:    float,         # basket rel20, pp
      breadth:  float,         # fraction 0..1
      source:   "curated" | "THS",
      n_members: int,
      n_covered: int,
      radar: {                 # None if not in any radar basket
        basket_id:  str,
        narr_rank:  int | None,
        global_ai:  dict | None,
      } | None,
    }
    Tickers with no qualifying theme and no radar join are absent from the dict.
    """
    # Invert memberships once
    curated_by_ticker = _ticker_to_baskets(memberships_curated)
    ths_by_ticker     = _ticker_to_baskets(memberships_ths)
    radar_index       = _build_radar_index(radar)

    # Collect all tickers that appear in at least one heat basket OR in the radar
    all_tickers: set[str] = set()
    all_tickers.update(curated_by_ticker.keys())
    all_tickers.update(ths_by_ticker.keys())
    all_tickers.update(radar_index.keys())

    tags: dict[str, dict] = {}

    for ticker in all_tickers:
        # Gather all basket ids this ticker belongs to (curated + THS)
        basket_ids = (
            curated_by_ticker.get(ticker, []) + ths_by_ticker.get(ticker, [])
        )

        # Find the strongest qualifying theme (by rel20, qualifying = level is not None)
        best_heat: dict | None = None
        for bid in basket_ids:
            rec = heat.get(bid)
            if rec is None:
                continue
            if rec["level"] is None:
                # Not qualifying on its own; still consider for best-rel20 even if unqualified
                # — spec says "strongest qualifying": skip non-qualifying
                continue
            if best_heat is None or rec["rel20"] > best_heat["rel20"]:
                best_heat = rec

        # Radar join
        radar_join = radar_index.get(ticker)

        # Only emit a tag if there is at least one signal (theme or radar)
        if best_heat is None and radar_join is None:
            continue

        tag: dict = {
            "theme":     best_heat["name"]     if best_heat else None,
            "theme_zh":  best_heat["name_zh"]  if best_heat else None,
            "basket_id": best_heat["basket_id"] if best_heat else None,
            "level":     best_heat["level"]    if best_heat else None,
            "rel20":     best_heat["rel20"]    if best_heat else None,
            "breadth":   best_heat["breadth"]  if best_heat else None,
            "source":    best_heat["source"]   if best_heat else None,
            "n_members": best_heat["n_members"] if best_heat else None,
            "n_covered": best_heat["n_covered"] if best_heat else None,
            "radar":     radar_join,
        }
        tags[ticker] = tag

    log.info("china_narrative_tags.name_tags: %d tickers tagged", len(tags))
    return tags


def ab_tier(stage: str | None, tag: dict | None) -> str | None:
    """Assign A/B tier from stage + tag.

    A = stage in {ENTRY, RIPENING} AND (theme HOT OR radar confirmer with
        honesty in {validated, partial})
    B = stage in {ENTRY, RIPENING} without A conditions
    None = RAN_LATE or no stage

    This is display + ledger only — rank influence NOT wired in W2.
    """
    if stage not in _TIERABLE_STAGES:
        return None
    if tag is None:
        return "B"
    theme_hot = tag.get("level") == "HOT"
    radar = tag.get("radar") or {}
    gai   = radar.get("global_ai") or {}
    radar_confirmed = gai.get("validated_tag") in _A_TIER_HONESTY
    if theme_hot or radar_confirmed:
        return "A"
    return "B"


# ── Convenience top-level loader ──────────────────────────────────────────────

def build_narrative_tags() -> dict:
    """Load all data sources and return {heat, tags, as_of, n_baskets, n_tagged}.

    Safe to call from builders — any missing artifact returns empty dicts with a
    warning log; never raises.
    """
    closes   = _load_closes()
    bench    = _load_benchmark()
    mem_cur  = _curated_membership()
    mem_ths  = _ths_membership()

    try:
        from engine.china_narrative_radar import build_radar
        radar = build_radar()
    except Exception as exc:  # noqa: BLE001
        log.warning("china_narrative_tags: radar unavailable: %s", exc)
        radar = None

    heat = narrative_heat(closes, mem_cur, mem_ths, bench)
    tags = name_tags(heat, mem_cur, mem_ths, radar)

    as_of = (
        str(closes.index[-1].date()) if closes is not None and not closes.empty
        else "unknown"
    )

    return {
        "as_of":    as_of,
        "heat":     heat,
        "tags":     tags,
        "n_baskets": len(heat),
        "n_tagged":  len(tags),
        "provenance": (
            "Narrative heat is a descriptive display heuristic — NOT validated alpha. "
            "Thresholds (rel20 >= +5pp / breadth >= 60pct for HOT) are pre-registered "
            "display heuristics; W6 will calibrate them from forward grades."
        ),
    }
