"""engine/subsector_confluence.py — the MACDRSI×StochRSI confluence ENTRY gate + the
validated rotation state machine, run on a SYNTHETIC equal-weight member-average index
for every Finviz S&P-500 sub-industry (and the 11 sectors), then funnelled into a
DOUBLE-GATED stock watch list (stock buyable AND its subsector buyable).

WHY. The existing subsector surfaces are orthogonal lenses: `subsector_rotation` is an
RRG/relative-strength read off Finviz's own % snapshot, and `subsector_scan` is an
EDGAR-scarcity × revision STAGE — neither runs the owner's price confluence. The Standout
board (`build_stock_library` → us_standouts.json) gates SINGLE names with the validated
T1-T4 cascade but has NO subsector-condition gate, so a great stock in a sector institutions
are distributing ranks identically to one with a tailwind. This module closes that gap by
COMPOSING existing, validated machinery — it adds no new signal math:

  • engine.subsector_scan._industry_map  → 503 S&P names → 11 sectors → 113 sub-industries
    (data/sp500_heatmap/industry_map.json, the Finviz heatmap clone)
  • engine.basket_index.consolidated_candle(mode="equal", pit=False) → the equal-weight
    member-average LEVEL series — the "combined members' weighted-average performance" chart
  • engine.signal_gate.gate → the owner's T1-T4 MACDRSI×StochRSI cascade (the ENTRY tier:
    T1 just-crossed master, T2 2D-MACD cross & 3D-Stoch crossed, T3 about-to-cross, T4 earliest)
  • engine.sector_signals.sector_signal → the validated BUY/SETUP/EXTENDED/TOPPING/SELL
    regime state machine (the rotation CONTEXT — the strong, era-robust edge is the AVOID side)

THE DOUBLE GATE (the user's spec, made context-aware rather than a sparse strict-AND):
  A subsector is ENTRY-NOW when its basket gate is a fresh buyable tier (T1/T2/T3) — i.e. it
  "just got a signal in the last 1-2 3D ticks, or has the 3D StochRSI and is about to get a
  2D MACDRSI". A member stock is a DOUBLE-CONFLUENCE buy when its OWN gate is buyable AND its
  subsector is a tailwind (entry-now, or a BUY/SETUP regime). A member whose own gate fires
  but whose subsector is TOPPING/SELL is surfaced as a HEADWIND warning, NOT a buy — that is
  the validated "don't chase the leadership institutions are distributing into" edge.

HONEST BY CONSTRUCTION. Equal-weight (the scored baseline — cap weights are partial and add
look-ahead). Membership is TODAY's S&P 500 with no point-in-time add/remove history, so the
index is a DESCRIPTIVE consolidated tape (survivorship-tinted), NOT an out-of-sample backtest.
EOD daily only. 3D buckets are calendar-business-day (not TradingView's session-from-IPO
anchor — the same known offset that already applies to single names). The SPDR-calibrated
STATE_BASE_RATES are OUT OF DOMAIN here and are deliberately NOT surfaced as validated numbers.
Every read is point-in-time / leak-free (the underlying gates project from PAST bars only).
DISPLAY-ONLY entry-QUALITY / RISK — one door; confirm before acting. None/empty on shortfall.
"""
from __future__ import annotations

import json
import logging
import re

import pandas as pd

from engine import basket_index, sector_signals, signal_gate, subsector_scan
from lib import config

log = logging.getLogger(__name__)

MIN_MEMBERS = 3                       # need a few priced names for a meaningful index (== subsector_scan)
_SEED_ADDED = "1990-01-01"            # synthetic membership start (unused under pit=False; member enters at its first bar)

# the fresh, actionable ENTRY tiers (== signal_gate.BUYABLE_TIERS): a just-crossed confirmed
# cross (T1/T2) or "3D StochRSI crossed & 2D MACD about to cross" (T3). T4 is the earliest /
# anti-falling-knife tier (off the 2D StochRSI) — surfaced as FORMING, not entry-now.
ENTRY_TIERS = signal_gate.BUYABLE_TIERS          # ("T1","T2","T3")
FORMING_TIER = "T4"

# ---- breadth reliability of a synthetic index --------------------------------------------------
# An equal-weight index on very few PRICED members is dominated by 1-2 names (on 3 names one stock
# is 33% of the tape), so its cascade tier + regime read is high-variance. We KEEP such groups
# (MIN_MEMBERS still gates the raw compute, and the member double-buy join is preserved) but tag
# them LOW confidence so a board can collapse them out of its headline lists rather than showing a
# 3-stock "index" with the same visual weight as a 25-name one. Heuristic DISPLAY thresholds, not
# statistically-derived cutoffs — an honest breadth flag, not a validated reliability number.
RELIABLE_MIN = 12                     # HIGH: broad, diversified index
RELIABLE_MED = 6                      # MED: usable but thin (<6 priced = LOW, collapsed by the board)


def reliability(n_priced: int | None) -> str:
    """HIGH/MED/LOW breadth-confidence tier from the count of PRICED members."""
    n = n_priced or 0
    if n >= RELIABLE_MIN:
        return "high"
    if n >= RELIABLE_MED:
        return "med"
    return "low"


def _breadth_coverage(groups: list[dict], base: dict | None = None) -> dict:
    """Coverage dict enriched with the HIGH/MED/LOW breadth-confidence split (+ thin share) so a
    board header can honestly report how much of it rests on thin, high-variance indices."""
    out = dict(base or {})
    n = len(groups)
    out["n_high"] = sum(1 for g in groups if g.get("reliability") == "high")
    out["n_med"] = sum(1 for g in groups if g.get("reliability") == "med")
    out["n_low_conf"] = sum(1 for g in groups if g.get("reliability") == "low")
    out["thin_share"] = round(out["n_low_conf"] / n, 3) if n else None
    return out

# regime sides that constitute a subsector TAILWIND vs a HEADWIND (sector_signals states).
# Tailwind = the buy family; headwind = the validated negative-edge avoid family (TOPPING/SELL).
# EXTENDED is "late, don't chase" (~market-neutral at 63d) — neither a tailwind nor a hard headwind.
_TAILWIND_STATES = {"BUY", "BUY_PARTIAL", "SETUP_BUY", "OVERSOLD_BOUNCE"}
_HEADWIND_STATES = {"TOPPING", "SELL"}


def _slug(s: str) -> str:
    """URL/file-safe key for a sub-industry name (globally unique in the Finviz taxonomy)."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-") or "x"


def _seed_members(tickers: list[str]) -> list[dict]:
    """Wrap a flat ticker list as basket-index membership entries (equal weight, no dates —
    pit=False makes each member live from its own first traded bar)."""
    seen, out = set(), []
    for t in tickers:
        if t and t not in seen:
            seen.add(t)
            out.append({"ticker": t, "added": _SEED_ADDED, "removed": None})
    return out


def _bench_close(ticker: str = "SPY") -> pd.Series | None:
    """Benchmark close for the regime engine's rs_60d. Resolves via the member loader (US: SPY in
    data/yahoo) and falls back to the China index store (data/china/<ticker>, e.g. 510300.SS = CSI
    300). A China desk MUST pass its own benchmark — SPY-vs-A-share rs_60d would be nonsensical."""
    df = basket_index._load_member_ohlcv(ticker)
    if df is None:
        p = config.data_dir() / "china" / f"{ticker}.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
            except Exception:  # noqa: BLE001
                df = None
    return df["close"].dropna() if df is not None and "close" in df else None


def _spy_close() -> pd.Series | None:
    return _bench_close("SPY")


def _ret20(close: pd.Series | None) -> float | None:
    """20-trading-day % return off a close series (needs >=21 bars); None on short/zero/NaN base.
    Callers pass series already on the SAME calendar so a member-vs-basket diff is a like window."""
    if close is None or len(close) < 21:
        return None
    base, last = close.iloc[-21], close.iloc[-1]
    if pd.isna(base) or pd.isna(last) or base == 0:
        return None
    return float(last / base - 1.0) * 100.0


def build_index(tickers: list[str]) -> tuple[pd.DataFrame | None, dict]:
    """Equal-weight member-average CANDLE (close = level from 1.0) for a group of tickers.
    (None, meta) if fewer than 3 members resolve OHLCV. pit=False = today's roster over its
    full available history (the deep technical read; no late-IPO dampening)."""
    members = _seed_members(tickers)
    idx = basket_index.deep_calendar(members)
    if len(idx) == 0:
        return None, {"n_total": len(set(tickers)), "n_with_ohlcv": 0, "coverage_pct": None}
    return basket_index.consolidated_candle(members, idx, mode="equal", pit=False)


def _member_gate(ticker: str, cache: dict) -> dict | None:
    """signal_gate.gate() on a member's own daily close (cached by ticker). None if no price."""
    if ticker in cache:
        return cache[ticker]
    df = basket_index._load_member_ohlcv(ticker)
    v = None
    if df is not None and "close" in df:
        c = df["close"].dropna()
        if len(c):
            try:
                v = signal_gate.gate(ticker, c)
            except Exception as e:  # noqa: BLE001 — never let one bad name kill the build
                log.warning("member gate failed %s: %s", ticker, e)
                v = None
    cache[ticker] = v
    return v


# regime contribution to the subsector "buyability factor" (0..1) used in the double-gate
# ranking — so a subsector with a tailwind REGIME but no fresh cascade tier still gets credit,
# and a topping/selling subsector contributes nothing (its members go to the headwind list).
_REGIME_W = {
    "BUY": 0.80, "BUY_PARTIAL": 0.60, "SETUP_BUY": 0.50, "OVERSOLD_BOUNCE": 0.40,
    "NEUTRAL": 0.25, "EXTENDED": 0.20, "BELOW_TREND": 0.15, "TOPPING": 0.0, "SELL": 0.0,
}


def _classify(buyable: bool, tier: str | None, state: str | None) -> str:
    """Coarse class for sorting/colour. A TOPPING/SELL regime is the validated AVOID edge and
    DOMINATES a coincident cascade tier (don't label a distributing subsector 'entry-now')."""
    if state in _HEADWIND_STATES:
        return "headwind"
    if buyable:
        return "entry_now"
    if tier == FORMING_TIER:
        return "forming"
    if state in _TAILWIND_STATES:
        return "tailwind"
    if state == "EXTENDED":
        return "late"
    return "neutral"


def _subsector_factor(entry_weight: float, state: str | None) -> float:
    """A subsector's 0..1 buyability factor for the double-gate combined score: the stronger of
    its fresh cascade ENTRY weight (T1 1.0 .. T4 0.4) and its REGIME tailwind weight. 0 for a
    headwind (TOPPING/SELL) regime — those never multiply a member into the double-buy list."""
    return max(entry_weight or 0.0, _REGIME_W.get(state or "", 0.0))


_CLASS_ORDER = {"entry_now": 0, "forming": 1, "tailwind": 2, "neutral": 3, "late": 4, "headwind": 5}


def score_group(key: str, label: str, sector: str, tickers: list[str],
                spy: pd.Series | None, member_cache: dict, *,
                kind: str = "subsector", with_members: bool = True,
                label_zh: str | None = None, sector_zh: str | None = None,
                member_names: dict | None = None) -> dict | None:
    """Build one group's synthetic index and run BOTH gates on it. Returns the structured
    verdict (entry tier + regime + per-member funnel + the index series for the chart), or
    None if the group is too thin / too short to gate. PURE w.r.t. files (reads the OHLCV store).
    """
    cand, meta = build_index(tickers)
    if cand is None or "close" not in cand:
        return None
    close = cand["close"].dropna()
    if len(close) < 220:                       # cascade needs >=200 daily bars; keep a small margin
        return None

    gv = signal_gate.gate(key, close)          # owner's T1-T4 MACDRSI×StochRSI cascade
    tier = gv.get("tier_cascade")
    buyable = signal_gate.is_buyable(gv)

    reg = sector_signals.sector_signal(close, name=label, spy_close=spy, ticker=key)
    reg.pop("base_rate", None)                 # SPDR-domain numbers are NOT valid for a subsector
    state = reg.get("state")

    cls = _classify(buyable, tier, state)
    px = float(close.iloc[-1])

    # per-member funnel: each member's OWN T1-T4 gate + its leadership within the basket
    members_detail, n_priced = [], 0
    bret20 = _ret20(close)                       # basket 20d return (close is the union-calendar level)
    if with_members:
        for t in tickers:
            mv = _member_gate(t, member_cache)
            mdf = basket_index._load_member_ohlcv(t)
            mc = mdf["close"].dropna() if mdf is not None and "close" in mdf else None
            if mc is None or len(mc) == 0:
                continue
            n_priced += 1
            # member 20d return ON THE BASKET CALENDAR, so vs_basket compares the SAME window
            mret20 = _ret20(mc.reindex(close.index).ffill())
            mtier = (mv or {}).get("tier_cascade")
            members_detail.append({
                "ticker": t,
                "name_zh": (member_names or {}).get(t),
                "price": round(float(mc.iloc[-1]), 2),
                "ret_20d": round(mret20, 1) if mret20 is not None else None,
                "vs_basket": (round(mret20 - bret20, 1)
                              if (mret20 is not None and bret20 is not None) else None),
                "stock_tier": mtier,
                "stock_weight": (mv or {}).get("weight") or 0.0,
                "stock_ticks": (mv or {}).get("ticks"),
                "stock_bars_to_cross": (mv or {}).get("bars_to_cross"),
                "stock_buyable": signal_gate.is_buyable(mv),
                "stock_state": (mv or {}).get("state"),
            })
        members_detail.sort(key=lambda m: (-(m["stock_weight"] or 0.0),
                                           -(m["vs_basket"] if m["vs_basket"] is not None else -999)))

    return {
        "key": key, "kind": kind, "label": label, "label_zh": label_zh,
        "sector": sector, "sector_zh": sector_zh,
        "n_members": len(set(tickers)), "n_priced": n_priced,
        "reliability": reliability(n_priced),
        "coverage_pct": meta.get("coverage_pct"), "n_live": meta.get("n_live"),
        "start": meta.get("start"), "as_of": str(close.index.max().date()),
        "price_level": round(px, 4),
        "class": cls,
        "entry": {
            "tier": tier, "weight": gv.get("weight") or 0.0, "tier_sub": gv.get("tier_sub"),
            "ticks": gv.get("ticks"), "bars_to_cross": gv.get("bars_to_cross"),
            "fresh_bars": gv.get("fresh_bars"), "eligible": bool(gv.get("eligible")),
            "buyable": buyable, "above200": gv.get("above200"),
            "reason": gv.get("reason"),
        },
        "regime": {
            "state": state, "side": reg.get("side"), "label": reg.get("label"),
            "label_zh": reg.get("label_zh"), "action": reg.get("action"),
            "action_zh": reg.get("action_zh"), "color": reg.get("color"),
            "conviction": reg.get("conviction"), "rsi_3d": reg.get("rsi_3d"),
            "stoch_3d": reg.get("stoch_3d"), "rsi_d": reg.get("rsi_d"),
            "stoch_d": reg.get("stoch_d"), "days_to_cross": reg.get("days_to_cross"),
            "rs_60d": reg.get("rs_60d"), "signal_line": sector_signals.signal_line(reg),
            "tailwind": state in _TAILWIND_STATES, "headwind": state in _HEADWIND_STATES,
            "ok": bool(reg.get("ok")),
        },
        "members": members_detail,
        # the index level series + §7 markers — consumed by the build script for the chart files
        "_candle": cand,
        "_markers": (gv.get("result") or {}),
    }


def _safe_score(label: str, *args, **kw) -> dict | None:
    """score_group, but one raising group never aborts the desk (additive-never-fatal; matches
    the basket entrypoint's per-item guard). signal_gate.gate never raises, but sector_signal
    makes no such promise — wrap the whole group so a single bad synthetic index just drops out."""
    try:
        return score_group(*args, **kw)
    except Exception as e:  # noqa: BLE001
        log.warning("subsector_confluence: group %s failed: %s", label, e)
        return None


def funnel(groups: list[dict]) -> dict:
    """From the scored groups, build the DOUBLE-GATED stock lists.

    double_buy    = a member whose OWN gate is buyable (T1/T2/T3) AND whose subsector is a
                    tailwind (entry-now, or a BUY/SETUP/oversold-bounce regime — never a
                    headwind) — the two-confluence picks. combined_score = stock cascade weight ×
                    subsector buyability factor, so T1-stock × T1-subsector (1.0) tops the board.
    headwind_warn = a member whose own gate is buyable BUT whose subsector is TOPPING/SELL —
                    surfaced as a warning ("good stock, sector distributing"), never as a buy.
    """
    double_buy, headwind_warn = [], []
    for g in groups:
        sub_state = g["regime"]["state"]
        sub_factor = _subsector_factor(g["entry"]["weight"], sub_state)
        headwind = g["regime"]["headwind"]
        tailwind = (not headwind) and (g["entry"]["buyable"] or g["regime"]["tailwind"])
        for m in g["members"]:
            if not m["stock_buyable"]:
                continue
            row = {
                "ticker": m["ticker"], "name_zh": m.get("name_zh"), "price": m["price"],
                "stock_tier": m["stock_tier"], "stock_weight": m["stock_weight"],
                "stock_ticks": m["stock_ticks"], "stock_bars_to_cross": m["stock_bars_to_cross"],
                "subsector_key": g["key"], "subsector": g["label"], "subsector_zh": g.get("label_zh"),
                "sector": g["sector"],
                "subsector_tier": g["entry"]["tier"], "subsector_state": sub_state,
                "subsector_side": g["regime"]["side"], "subsector_factor": round(sub_factor, 3),
                "subsector_reliability": g.get("reliability"),
                "subsector_n_priced": g.get("n_priced"),
                "combined_score": round((m["stock_weight"] or 0.0) * sub_factor, 4),
                "vs_subsector_20d": m["vs_basket"],
            }
            if tailwind:
                double_buy.append(row)
            elif headwind:
                headwind_warn.append(row)
    # breadth is an ADDITIVE tiebreaker only (not a multiplicative penalty): at equal conviction a
    # pick backed by a broader concept ranks above one backed by a 3-name index. The board still
    # collapses the LOW-confidence rows into their own section — this just orders within a section.
    double_buy.sort(key=lambda r: (-r["combined_score"], -(r.get("subsector_n_priced") or 0)))
    headwind_warn.sort(key=lambda r: (-(r["stock_weight"] or 0.0), -(r.get("subsector_n_priced") or 0)))
    return {"double_buy": double_buy, "headwind_warn": headwind_warn}


# ---------------------------------------------------------------- entrypoints ----

def compute_subsector_confluence() -> dict:
    """The S&P-500 sub-industry confluence desk. Builds an equal-weight index per Finviz
    sub-industry (and an 11-sector rollup), runs the entry gate + regime state machine on
    each, and funnels the double-gated members. Returns the full payload (the build script
    serialises it + the per-subsector chart files). Empty/degraded on missing inputs."""
    groups_map = subsector_scan._industry_map()
    if not groups_map:
        log.warning("subsector_confluence: industry_map missing")
        return {"ok": False, "reason": "industry_map missing", "subsectors": [], "sectors": []}

    spy = _spy_close()
    member_cache: dict = {}
    n_total = len(groups_map)

    subs: list[dict] = []
    for (sector, sub), tickers in sorted(groups_map.items()):
        if len(set(tickers)) < MIN_MEMBERS:
            continue
        g = _safe_score(sub, _slug(sub), sub, sector, tickers, spy, member_cache, kind="subsector")
        if g is not None:
            subs.append(g)

    # 11-sector rollup (all members of each Finviz sector) — context for "which subsectors
    # are propping up each sector". No member funnel (the subsector groups already carry it).
    sector_members: dict[str, list[str]] = {}
    for (sector, sub), tickers in groups_map.items():
        sector_members.setdefault(sector, []).extend(tickers)
    sectors: list[dict] = []
    for sector, tickers in sorted(sector_members.items()):
        g = _safe_score(sector, "sec-" + _slug(sector), sector, sector, tickers, spy, member_cache,
                        kind="sector", with_members=False)
        if g is not None:
            sectors.append(g)

    subs.sort(key=lambda g: (_CLASS_ORDER.get(g["class"], 9), -g["entry"]["weight"],
                             -(g["regime"]["rs_60d"] or 0)))
    ff = funnel(subs)

    return {
        "ok": True, "universe": "sp500_subsectors", "weighting": "equal",
        "as_of": max((g["as_of"] for g in subs), default=None),
        "coverage": _breadth_coverage(subs, {
            "n_subsectors": n_total, "n_gateable": len(subs),
            "n_thin": n_total - len(subs), "n_sectors": len(sectors),
        }),
        "entry_now": [g["key"] for g in subs if g["class"] == "entry_now"],
        "forming": [g["key"] for g in subs if g["class"] == "forming"],
        "headwind": [g["key"] for g in subs if g["class"] == "headwind"],
        "subsectors": subs,
        "sectors": sectors,
        "double_gated": ff,
        "notes": ("Equal-weight synthetic member-average index per sub-industry; "
                  "owner's T1-T4 MACDRSI×StochRSI cascade = the ENTRY gate, the validated "
                  "sector state machine = the rotation CONTEXT. Today's S&P-500 membership "
                  "(descriptive, not out-of-sample); EOD daily; calendar 3D buckets. A risk / "
                  "rotation-timing map — one door, confirm before acting; not alpha."),
    }


_US_BASKET_NOTE = ("Equal-weight curated thematic baskets; same T1-T4 entry gate + regime "
                   "context as the subsector desk. Curated membership (descriptive); EOD daily. "
                   "One door, confirm before acting; not alpha.")


def compute_basket_confluence(memberships: dict, *, benchmark: str = "SPY",
                              universe: str = "curated_baskets", kind: str = "basket",
                              notes: str | None = None) -> dict:
    """The same desk over a dict of equal-weight baskets {basket_id: {name, name_zh?, category,
    category_zh?, members:[{ticker, removed?, name_zh?}], ...}}. Region-agnostic: pass `benchmark`
    (SPY for US, 510300.SS=CSI 300 for China) for the regime rs_60d, and bilingual `name_zh`/
    `category_zh`/member `name_zh` flow straight through to the output for the CN pages."""
    spy = _bench_close(benchmark)
    member_cache: dict = {}
    items = memberships.items() if isinstance(memberships, dict) else [(b.get("id"), b) for b in memberships]

    baskets: list[dict] = []
    for bid, spec in items:
        members = spec.get("members") or []
        tickers = [m.get("ticker") for m in members if m.get("ticker") and not m.get("removed")]
        if len(set(tickers)) < MIN_MEMBERS:
            continue
        member_names = {m.get("ticker"): m.get("name_zh") for m in members if m.get("ticker")}
        g = _safe_score(bid, _slug(bid), spec.get("name") or bid, spec.get("category") or "theme",
                        tickers, spy, member_cache, kind=kind,
                        label_zh=spec.get("name_zh"), sector_zh=spec.get("category_zh"),
                        member_names=member_names)
        if g is not None:
            g["basket_id"] = bid
            baskets.append(g)

    # RC-R7: annotate dual-membership names (e.g. NVDA ∈ {mag7, ai_semiconductors}) with a
    # "behaves-as" read from trailing correlation vs each home's ex-name composite — so two
    # cards showing opposite reads for the same name are reconciled. Additive, never fatal.
    behaves_as = {}
    try:
        from engine import basket_behaves_as
        behaves_as = basket_behaves_as.annotate(baskets, memberships)
    except Exception as e:  # noqa: BLE001 — display-only, never blocks the desk
        log.warning("subsector_confluence: behaves_as annotation failed: %s", e)

    baskets.sort(key=lambda g: (_CLASS_ORDER.get(g["class"], 9), -g["entry"]["weight"],
                                -(g["regime"]["rs_60d"] or 0)))
    ff = funnel(baskets)
    return {
        "ok": True, "universe": universe, "weighting": "equal", "benchmark": benchmark,
        "behaves_as": behaves_as,
        "as_of": max((g["as_of"] for g in baskets), default=None),
        "coverage": _breadth_coverage(baskets, {"n_baskets": len(baskets)}),
        "entry_now": [g["key"] for g in baskets if g["class"] == "entry_now"],
        "forming": [g["key"] for g in baskets if g["class"] == "forming"],
        "headwind": [g["key"] for g in baskets if g["class"] == "headwind"],
        "baskets": baskets,
        "double_gated": ff,
        "notes": notes or _US_BASKET_NOTE,
    }


def compute_china_ths_confluence() -> dict:
    """The China 同花顺 (Tonghuashun) CONCEPT confluence desk. Same equal-weight index → T1-T4
    MACDRSI×StochRSI entry gate → regime state machine → double-gated funnel as the US desk, over
    the curated THS concept baskets (data/baskets_china_ths/membership.json), benchmarked to CSI
    300 (沪深300, 510300.SS). THS concepts are a FLAT, overlapping classification (a stock sits in
    many concepts) — NOT a sector→industry hierarchy — so this is the concept-basket analog of the
    US thematic-baskets desk, not a granular sub-industry partition. Regime base rates are
    US-SPDR-calibrated (NOT China-validated) and are not shown; the BUY/SETUP/TOPPING/SELL state
    logic is market-agnostic technical analysis. Degrades to ok=False if the membership is absent."""
    p = config.data_dir() / "baskets_china_ths" / "membership.json"
    if not p.exists():
        log.warning("china_ths_confluence: membership.json missing")
        return {"ok": False, "reason": "THS membership missing", "baskets": [], "double_gated": {"double_buy": [], "headwind_warn": []}}
    mem = json.loads(p.read_text())
    baskets = mem.get("baskets") or {}
    bench = mem.get("benchmark") or "510300.SS"
    blab, blab_zh = mem.get("benchmark_label") or "CSI 300", mem.get("benchmark_label_zh") or "沪深300"
    out = compute_basket_confluence(
        baskets, benchmark=bench, universe="ths_concepts", kind="concept",
        notes=(f"Equal-weight 同花顺 (Tonghuashun) CONCEPT baskets, benchmarked to {blab} ({blab_zh}, "
               f"{bench}). Same T1-T4 MACDRSI×StochRSI entry gate + regime context as the US desk. "
               "Curated, today's-membership (descriptive, hindsight-curated — NOT out-of-sample); EOD "
               "daily; calendar 3D buckets. Regime base rates are US-sector-calibrated and not shown "
               "for China. Display-only entry-quality / rotation-timing — one door, confirm before "
               "acting; not alpha."))
    out["region"] = "china"
    out["benchmark_label"], out["benchmark_label_zh"] = blab, blab_zh
    out["source"] = mem.get("source")
    return out


# --------------------------------------------- US index desks (Nasdaq-100 / Russell-2000) ----
# Same machinery as the S&P sub-industry desk, but over a CURATED index-membership file rather
# than the Finviz heatmap clone. Each desk partitions its index into Finviz sub-industry
# "subsectors" (the `subsectors` array, with the double-gated member funnel) PLUS a set of curated
# "amalgamations" (the `sectors` rollup — higher-level complexes whose internal rotation keeps the
# index grinding without leadership bleeding to ex-tech). Emits the compute_subsector_confluence
# shape so the board page renders these tabs through the exact S&P code path. Benchmark = the
# index's own ETF (QQQ / IWM) so rs_60d measures WITHIN-index relative strength (the rotation lens).

def _members_to_tickers(members: list) -> list[str]:
    """A membership 'members' list (dicts or bare strings) → a clean ticker list."""
    out: list[str] = []
    for m in members or []:
        t = (m.get("ticker") if isinstance(m, dict) else m)
        if t and not (isinstance(m, dict) and m.get("removed")):
            out.append(t)
    return out


def _member_names(members: list) -> dict:
    return {m["ticker"]: m.get("name_zh") for m in (members or [])
            if isinstance(m, dict) and m.get("ticker")}


def _compute_partition(subsectors: dict, amalgamations: dict, *, benchmark: str,
                       universe: str, region: str, notes: str) -> dict:
    """Score a curated {key: {name, name_zh?, sector, sector_zh?, members[]}} partition as the
    subsector board + an amalgamation rollup. `subsectors` carry the member funnel; `amalgamations`
    are the equal-weight complex indices (no funnel — the subsector groups already carry members)."""
    bench = _bench_close(benchmark)
    member_cache: dict = {}

    subs: list[dict] = []
    for key, spec in subsectors.items():
        tickers = _members_to_tickers(spec.get("members"))
        if len(set(tickers)) < MIN_MEMBERS:
            continue
        g = _safe_score(key, _slug(key), spec.get("name") or key, spec.get("sector") or "",
                        tickers, bench, member_cache, kind="subsector",
                        label_zh=spec.get("name_zh"), sector_zh=spec.get("sector_zh"),
                        member_names=_member_names(spec.get("members")))
        if g is not None:
            subs.append(g)

    sectors: list[dict] = []
    for key, spec in (amalgamations or {}).items():
        tickers = _members_to_tickers(spec.get("members"))
        if len(set(tickers)) < MIN_MEMBERS:
            continue
        # with_members=True so a complex's detail page lists its constituent names (gated), like
        # a subsector page — the amalgam is its own equal-weight index of those members.
        g = _safe_score(key, "amalg-" + _slug(key), spec.get("name") or key,
                        spec.get("name") or key, tickers, bench, member_cache, kind="sector",
                        with_members=True, label_zh=spec.get("name_zh"))
        if g is not None:
            sectors.append(g)

    subs.sort(key=lambda g: (_CLASS_ORDER.get(g["class"], 9), -g["entry"]["weight"],
                             -(g["regime"]["rs_60d"] or 0)))
    sectors.sort(key=lambda g: (_CLASS_ORDER.get(g["class"], 9), -g["entry"]["weight"],
                                -(g["regime"]["rs_60d"] or 0)))
    n_total = len(subsectors)
    return {
        "ok": True, "universe": universe, "weighting": "equal", "benchmark": benchmark,
        "region": region,
        "as_of": max((g["as_of"] for g in subs), default=None),
        "coverage": _breadth_coverage(subs, {"n_subsectors": n_total, "n_gateable": len(subs),
                     "n_thin": n_total - len(subs), "n_sectors": len(sectors)}),
        "entry_now": [g["key"] for g in subs if g["class"] == "entry_now"],
        "forming": [g["key"] for g in subs if g["class"] == "forming"],
        "headwind": [g["key"] for g in subs if g["class"] == "headwind"],
        "subsectors": subs,
        "sectors": sectors,
        "double_gated": funnel(subs),
        "notes": notes,
    }


def _compute_index_desk(ns: str, benchmark_default: str, universe: str,
                        index_label: str) -> dict:
    """Shared loader for the Nasdaq/Russell desks: read data/baskets_<ns>/membership.json
    ({subsectors, amalgamations, benchmark, benchmark_label}) and score the partition."""
    p = config.data_dir() / f"baskets_{ns}" / "membership.json"
    if not p.exists():
        log.warning("%s_confluence: membership.json missing (%s)", ns, p)
        return {"ok": False, "reason": f"{ns} membership missing", "subsectors": [], "sectors": [],
                "double_gated": {"double_buy": [], "headwind_warn": []}}
    mem = json.loads(p.read_text())
    bench = mem.get("benchmark") or benchmark_default
    blab = mem.get("benchmark_label") or index_label
    out = _compute_partition(
        mem.get("subsectors") or {}, mem.get("amalgamations") or {},
        benchmark=bench, universe=universe, region=ns,
        notes=(f"Equal-weight synthetic member-average index per sub-industry within the "
               f"{index_label}, plus curated amalgamation complexes (the rollup). Owner's T1-T4 "
               f"MACDRSI×StochRSI cascade = the ENTRY gate; the sector state machine = rotation "
               f"CONTEXT; benchmarked to {blab} so rs_60d reads WITHIN-index leadership. Today's "
               "membership (descriptive, not out-of-sample); EOD daily; calendar 3D buckets. "
               "Tracks how leadership rotates among the index's subsectors. Regime base rates are "
               "S&P-SPDR-calibrated (out-of-domain here) and not shown. DISPLAY-ONLY entry-quality "
               "/ rotation-timing — one door, confirm before acting; not alpha."))
    out["benchmark_label"] = blab
    out["source"] = mem.get("source")
    return out


def compute_nasdaq_confluence() -> dict:
    """Nasdaq-100 subsector confluence desk (benchmark QQQ)."""
    return _compute_index_desk("nasdaq", "QQQ", "nasdaq_subsectors", "Nasdaq-100 (QQQ)")


def compute_russell_confluence() -> dict:
    """Russell-2000 subsector confluence desk (benchmark IWM)."""
    return _compute_index_desk("russell", "IWM", "russell_subsectors", "Russell-2000 (IWM)")
