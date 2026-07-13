"""Cross-fund consolidated ownership FLOW + descriptive model boards (SM v3, S2.5).

The sibling engines answer "who holds this name" (engine.smart_money) and "did the
fund's trades work" (engine.manager_trades). This module asks the cross-sectional
question the desk cares about NEXT: **what is the tracked-fund cohort, as a group,
rotating into and out of — and which names combine breadth, conviction and room?**

Four surfaces, all DESCRIPTIVE (never a forecast, never wired into any score):

  * stock_flow       — per-name grade-weighted buy/sell breadth this filing cycle,
                       with an honest est. $-flow only where reported deltas make it
                       computable (never fabricated).
  * group_flow       — sector / theme rollup of per-fund rotation deltas
                       (Σ quarter-over-quarter weight changes, pp of book).
  * rotation_history — aggregate sector mix per quarter across funds (trend view).
  * models           — four ranked boards (most favored / conviction buys /
                       uncrowded conviction / rotating out), every row carrying its
                       transparent components and every board its method sentence.

PURITY CONTRACT: every function in this module is PURE given its inputs — no disk,
no network, no config reads, no clock. The build script (scripts/build_smart_money.py)
wires the inputs (sm, tracker, fund_intel, crowding, cls) and owns all I/O. This is
what makes the tests trivial (plain dict fixtures, no parquet, no monkeypatching).

CLOCK DISCIPLINE (SM2-R3): everything here lives on the 13F FILING clock — `asof`
stamps are filing dates (tracker.latest_filing / fund book_meta.filing_date), never
period_end, and no insider-lane (Quiver / SEC-panel) number is ever blended in.

NORMALIZATION: `norm()` is a percentile rank within the candidate set (0..1) —
never a z-score. The candidate sets are small (n≈20–300) and fat-tailed; a z-score
would let one outlier own the composite.
"""
from __future__ import annotations

import logging
import math
import statistics

log = logging.getLogger(__name__)

# Index / sector / commodity ETFs are excluded from the cross-stock flow and model
# boards (an SPY line is cash parking, not a stock pick, and it distorts breadth).
# mirror of scripts/build_smart_money.py — keep in sync
# (importing it from scripts.build_smart_money would be a circular import: the build
# script imports this module).
_INDEX_ETFS = frozenset({
    "SPY", "IVV", "VOO", "QQQ", "IWM", "DIA", "VTI", "RSP", "MDY", "IJR", "IJH",
    "EEM", "EFA", "VEA", "VWO", "FXI", "KWEB", "EWJ", "EWZ", "INDA",
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
    "SMH", "SOXX", "XBI", "IBB", "KRE", "XOP", "XME", "GDX", "GDXJ", "ARKK",
    "GLD", "SLV", "USO", "UNG", "TLT", "IEF", "SHY", "HYG", "LQD", "AGG", "BND",
})

# Grade weights for breadth (tracker A–D grades; anything else — D, 'n/a', missing —
# gets the ungraded default). Weights are display/rank context, never a score input.
GRADE_WEIGHTS: dict[str, float] = {"A": 2.0, "B": 1.5, "C": 1.0}
DEFAULT_GRADE_WEIGHT = 0.75

# Grades whose funds qualify as "top" buyers on the conviction / uncrowded boards.
_TOP_GRADES = ("A", "B")

_BUY_ACTIONS = {"new", "add"}
_SELL_ACTIONS = {"trim", "exit"}


# --------------------------------------------------------------------------- #
# Small pure helpers                                                            #
# --------------------------------------------------------------------------- #

def _f(v) -> float | None:
    """Finite float or None — guards NaN/inf/str leakage from upstream frames. PURE."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def grade_weight(grade: str | None) -> float:
    """Breadth weight for a tracker grade: A=2, B=1.5, C=1, else 0.75. PURE."""
    return GRADE_WEIGHTS.get(str(grade or "").strip().upper(), DEFAULT_GRADE_WEIGHT)


def norm(value: float | None, values: list[float]) -> float | None:
    """Percentile rank of `value` within the candidate set `values`, in 0..1. PURE.

    Mean-rank convention (ties share the average of their ranks):
      r = (#strictly-less) + 0.5 * (#equal - 1);   norm = r / (n - 1)
    so [1,2,3] -> 0.0 / 0.5 / 1.0 and a tied pair in [5,5,9] -> 0.25 each.
    n == 1 -> 0.5 (a lone candidate is median by definition); empty set or a
    None value -> None. NEVER a z-score — candidate sets here are small (n≈20–300)
    and fat-tailed, so a single outlier must not own the composite.
    """
    if value is None:
        return None
    vals = [v for v in (_f(x) for x in values) if v is not None]
    n = len(vals)
    if n == 0:
        return None
    if n == 1:
        return 0.5
    less = sum(1 for v in vals if v < value)
    equal = sum(1 for v in vals if v == value)
    r = less + 0.5 * max(0, equal - 1)
    return round(r / (n - 1), 3)


def _grade_map(tracker: dict | None) -> dict[str, str]:
    """{slug(lower): grade} from the tracker leaderboard ('n/a' kept as-is). PURE."""
    out: dict[str, str] = {}
    for row in (tracker or {}).get("leaderboard", []) or []:
        try:
            slug = str(row.get("slug", "")).strip().lower()
            if slug:
                out[slug] = str(row.get("grade", "n/a"))
        except Exception:  # noqa: BLE001
            continue
    return out


def _filing_asof(tracker: dict | None, sm: dict | None = None) -> str:
    """The 13F-lane as-of on the FILING clock: tracker.latest_filing first (the only
    look-ahead-free stamp), falling back to sm.as_of (a period_end — labeled by the
    caller as such only when no filing date exists at all). PURE."""
    t = str((tracker or {}).get("latest_filing") or "")
    if t:
        return t
    return str((sm or {}).get("as_of") or "")


def _dedup_by_ticker(by_ticker: dict) -> list[tuple[str, dict]]:
    """(ticker, record) pairs with share-class ALIAS copies removed. PURE.

    compute_smart_money writes alias entries (e.g. GOOG and GOOGL) pointing at the
    SAME dict object so both stock pages resolve; iterating by_ticker naively would
    double-count that issuer on every cross-stock board. Dedup is by object identity;
    keys are visited in sorted order so the surviving display ticker is deterministic
    (the record's other classes remain visible via its `share_classes` list).
    """
    seen: set[int] = set()
    out: list[tuple[str, dict]] = []
    for tk in sorted(by_ticker or {}):
        rec = by_ticker.get(tk)
        if not isinstance(rec, dict):
            continue
        if id(rec) in seen:
            continue
        seen.add(id(rec))
        out.append((str(tk), rec))
    return out


def _holder_flow_usd(holder: dict) -> float | None:
    """Estimated $ flow of ONE holder's move from its reported value/share deltas,
    or None when not computable — NEVER fabricated. PURE.

    * new  -> +value_usd (the whole reported position is inflow)
    * exit -> -value_usd (diff_snapshots stamps the PRIOR value on exit rows)
    * add/trim -> value_usd * (c/100) / (1 + c/100) where c = shares_change_pct —
      the share-driven value delta at the quarter-end mark (price held constant);
      requires BOTH shares_change_pct and value_usd, and c > -100.
    * hold / anything else -> None (not a move).
    """
    action = str(holder.get("action") or "")
    val = _f(holder.get("value_usd"))
    if action == "new":
        return val if val is not None and val > 0 else None
    if action == "exit":
        return -val if val is not None and val > 0 else None
    if action in ("add", "trim"):
        c = _f(holder.get("shares_change_pct"))
        if val is None or val <= 0 or c is None or c <= -100.0:
            return None
        frac = c / 100.0
        return val * frac / (1.0 + frac)
    return None


# --------------------------------------------------------------------------- #
# stock_flow — per-name grade-weighted breadth this filing cycle                #
# --------------------------------------------------------------------------- #

def stock_flow(sm: dict | None, tracker: dict | None, cap: int = 30) -> dict | None:
    """Cross-fund consolidated flow per name from the latest-cycle holder actions.

    Returns {'in': [row...], 'out': [row...], 'asof', 'method_en', 'method_zh'}
    or None when sm carries no by_ticker. Each row:
      {ticker, issuer, n_buying, n_selling,
       buy_funds:  [{slug, name, grade, action, pct_book}...],
       sell_funds: [{slug, name, grade, action, pct_book}...],
       gw_breadth, est_flow_usd, intensity, d_funds_qoq}

    * gw_breadth = Σ w(grade) over buying funds − Σ w(grade) over selling funds
      (w: A=2, B=1.5, C=1, else 0.75). The holder list on a by_ticker record is
      capped upstream at panel_top_n with buyers sorted first, so beyond-cap movers
      would silently be mostly SELLERS; to keep the sign consistent with the full
      n_buying/n_selling counts, unseen movers are weighted at the ungraded 0.75.
    * est_flow_usd = Σ per-holder value deltas over VISIBLE movers where computable
      (see _holder_flow_usd); None when no mover is computable — never fabricated.
    * intensity = mean |pct_book| across visible movers (exit rows carry 0 pct —
      that is the reported figure, kept as-is).
    * d_funds_qoq = latest QoQ change in tracked-holder count from the accumulation
      trend (None when <2 quarters of history).

    Index/sector/commodity ETFs excluded (_INDEX_ETFS); share-class aliases deduped.
    'in' = gw_breadth > 0 ranked descending, 'out' = gw_breadth < 0 ranked most
    negative first, each capped at `cap`. asof is on the FILING clock. PURE.
    """
    try:
        by_ticker = (sm or {}).get("by_ticker") or {}
        if not by_ticker:
            return None
        grades = _grade_map(tracker)

        rows_in: list[dict] = []
        rows_out: list[dict] = []
        for ticker, rec in _dedup_by_ticker(by_ticker):
            try:
                if ticker in _INDEX_ETFS:
                    continue
                holders = [h for h in rec.get("holders", []) or [] if isinstance(h, dict)]
                if not holders:
                    continue
                buy_funds, sell_funds = [], []
                gw = 0.0
                flows: list[float] = []
                movers_pct: list[float] = []
                for h in holders:
                    action = str(h.get("action") or "")
                    if action not in _BUY_ACTIONS and action not in _SELL_ACTIONS:
                        continue
                    slug = str(h.get("fund") or "").lower()
                    grade = grades.get(slug)
                    w = grade_weight(grade)
                    card = {
                        "slug": slug,
                        "name": str(h.get("fund_name") or slug),
                        "grade": grade,
                        "action": action,
                        "pct_book": _f(h.get("pct_portfolio")),
                    }
                    if action in _BUY_ACTIONS:
                        gw += w
                        buy_funds.append(card)
                    else:
                        gw -= w
                        sell_funds.append(card)
                    fl = _holder_flow_usd(h)
                    if fl is not None:
                        flows.append(fl)
                    p = _f(h.get("pct_portfolio"))
                    if p is not None:
                        movers_pct.append(abs(p))
                if not buy_funds and not sell_funds:
                    continue
                # full-record counts (computed upstream over the UNCAPPED holder set)
                n_buying = int(rec.get("n_buying") or len(buy_funds))
                n_selling = int(rec.get("n_selling") or len(sell_funds))
                # unseen (beyond-cap) movers carry no grade info -> ungraded weight
                gw += DEFAULT_GRADE_WEIGHT * max(0, n_buying - len(buy_funds))
                gw -= DEFAULT_GRADE_WEIGHT * max(0, n_selling - len(sell_funds))

                trend = rec.get("trend") or {}
                hs = trend.get("holders_series") or []
                d_qoq = (int(hs[-1]) - int(hs[-2])) if len(hs) >= 2 else None

                issuer = next((str(h.get("issuer") or "") for h in holders
                               if h.get("issuer")), "")
                row = {
                    "ticker": ticker,
                    "issuer": issuer,
                    "n_buying": n_buying,
                    "n_selling": n_selling,
                    "buy_funds": buy_funds,
                    "sell_funds": sell_funds,
                    "gw_breadth": round(gw, 2),
                    "est_flow_usd": round(sum(flows), 0) if flows else None,
                    "intensity": (round(sum(movers_pct) / len(movers_pct), 2)
                                  if movers_pct else None),
                    "d_funds_qoq": d_qoq,
                }
                if row["gw_breadth"] > 0:
                    rows_in.append(row)
                elif row["gw_breadth"] < 0:
                    rows_out.append(row)
            except Exception:  # noqa: BLE001 — one bad record must not break the board
                log.debug("stock_flow: skipped %s", ticker, exc_info=True)

        rows_in.sort(key=lambda r: (-r["gw_breadth"], -r["n_buying"], r["ticker"]))
        rows_out.sort(key=lambda r: (r["gw_breadth"], -r["n_selling"], r["ticker"]))
        return {
            "in": rows_in[:cap],
            "out": rows_out[:cap],
            "asof": _filing_asof(tracker, sm),
            "method_en": ("Grade-weighted holder breadth per name this filing cycle: "
                          "Σ w(grade) over buying funds minus selling funds "
                          "(w: A=2, B=1.5, C=1, else 0.75); est. flow $ only where "
                          "reported value/share deltas make it computable; "
                          "descriptive rank — not a forecast."),
            "method_zh": ("按基金评级加权的本申报周期持有人广度：买入基金 Σw(评级) 减 "
                          "卖出基金（w：A=2，B=1.5，C=1，其余 0.75）；预估资金流仅在申报的"
                          "市值/股数变化可计算时给出；描述性排名——非预测。"),
        }
    except Exception:  # noqa: BLE001
        log.warning("stock_flow failed", exc_info=True)
        return None


# --------------------------------------------------------------------------- #
# group_flow — sector / theme rollup of per-fund rotation deltas                #
# --------------------------------------------------------------------------- #

def _fund_group_deltas(fi: dict, level: str) -> dict[str, float]:
    """One fund's latest QoQ weight deltas keyed by group. PURE.

    level='sector': prefer the precomputed sector_rotation.deltas; fall back to the
    difference of the last two sector_series weight vectors.
    level='theme' : difference of the last two sector_series top_theme_weights
    vectors (basket-category granularity — the grain fund_intel carries QoQ).
    Missing keys count as 0 on either side. Empty dict when <2 quarters exist.
    """
    if level == "sector":
        deltas = ((fi.get("sector_rotation") or {}).get("deltas") or {})
        if isinstance(deltas, dict) and deltas:
            return {str(k): d for k, d in ((k, _f(v)) for k, v in deltas.items())
                    if d is not None}
        field = "weights"
    else:
        field = "top_theme_weights"
    series = fi.get("sector_series") or []
    if len(series) < 2:
        return {}
    prev = (series[-2] or {}).get(field) or {}
    cur = (series[-1] or {}).get(field) or {}
    out: dict[str, float] = {}
    for k in set(prev) | set(cur):
        d = (_f(cur.get(k)) or 0.0) - (_f(prev.get(k)) or 0.0)
        out[str(k)] = d
    return out


def _harvest_theme_labels(funds: dict) -> dict[str, tuple[str, str | None]]:
    """{group_key: (label, label_zh|None)} harvested from fund_intel metadata. PURE.

    label_zh is a PASSTHROUGH, never invented: basket-level keys pick up name_zh from
    theme_read leans / book theme entries (baskets carry name_zh); category-level keys
    only get a zh label when the metadata explicitly carries `category_zh`.
    """
    out: dict[str, tuple[str, str | None]] = {}

    def _note(key, label, zh) -> None:
        k = str(key or "")
        if not k:
            return
        prev = out.get(k)
        if prev is None or (prev[1] is None and zh):
            out[k] = (str(label or k), str(zh) if zh else None)

    for fi in (funds or {}).values():
        try:
            for lean in ((fi.get("theme_read") or {}).get("leans") or []):
                if not isinstance(lean, dict):
                    continue
                _note(lean.get("theme_key"), lean.get("label"), lean.get("label_zh"))
                _note(lean.get("category"), lean.get("category"),
                      lean.get("category_zh"))
            for pos in (fi.get("book") or []):
                for th in (pos.get("themes") or []):
                    if not isinstance(th, dict):
                        continue
                    _note(th.get("slug"), th.get("name"), th.get("name_zh"))
                    _note(th.get("category"), th.get("category"),
                          th.get("category_zh"))
        except Exception:  # noqa: BLE001
            continue
    return out


def _pos_in_group(pos: dict, key: str, level: str) -> bool:
    """Does a fund-book position belong to a rotation group? PURE."""
    if level == "sector":
        return str(pos.get("sector") or "") == key
    for th in (pos.get("themes") or []):
        if isinstance(th, dict):
            if str(th.get("category") or "") == key or str(th.get("slug") or "") == key:
                return True
        elif str(th) == key:
            return True
    return False


def group_flow(fund_intel: dict | None, tracker: dict | None,
               level: str = "sector", top_grades: list[str] | None = None,
               top_names_n: int = 5) -> dict | None:
    """Sector or theme (basket-category) rollup of per-fund rotation deltas.

    Σ of each included fund's latest quarter-over-quarter weight change per group
    (pp of that fund's book). `top_grades` (e.g. ["A","B"]) restricts to funds at
    those tracker grades — the "top funds only" variant; None = all funds.

    Returns {'groups': [row...], 'level', 'n_funds', 'asof', 'method_en',
    'method_zh'} or None when no fund contributes. Each row:
      {key, label, label_zh?, n_funds_in, n_funds_out, net_pp, avg_pp, intensity,
       top_names_in: [{ticker, pp}...], top_names_out: [{ticker, pp}...]}

    * net_pp = Σ delta_pp across funds; avg_pp = net_pp / n contributing funds;
      intensity = Σ |delta_pp| (how contested the rotation is, both directions).
    * top_names_in/out: this-cycle new/add (in) vs trim/exit (out) book positions
      of included funds in the group, ranked by Σ pct_book across funds. The book
      is the LATEST holdings so fully-exited names cannot appear on the out side —
      the pp deltas still carry their weight loss.
    * label_zh is a passthrough (baskets carry name_zh); never invented here.
    * Classification is today's map applied to history (survivorship-lite — the
      method note says so, per the honesty checklist).
    Groups ranked net_pp descending. asof on the FILING clock. PURE.
    """
    try:
        level = "theme" if str(level) == "theme" else "sector"
        funds = (fund_intel or {}).get("funds") or {}
        if not funds:
            return None
        grades = _grade_map(tracker)
        wanted = ({str(g).upper() for g in top_grades} if top_grades else None)

        included: dict[str, dict] = {}
        for slug, fi in funds.items():
            if not isinstance(fi, dict):
                continue
            if wanted is not None and str(grades.get(str(slug).lower(), "")).upper() not in wanted:
                continue
            included[str(slug)] = fi
        if not included:
            return None

        labels = _harvest_theme_labels(included) if level == "theme" else {}
        agg: dict[str, dict] = {}
        asof_dates: list[str] = []
        # pass 1: accumulate every fund's deltas so the group key-space is complete
        for slug, fi in included.items():
            try:
                fd = str((fi.get("book_meta") or {}).get("filing_date") or "")
                if fd:
                    asof_dates.append(fd)
                deltas = _fund_group_deltas(fi, level)
                for key, d in deltas.items():
                    g = agg.setdefault(key, {"net": 0.0, "absum": 0.0, "n": 0,
                                             "n_in": 0, "n_out": 0,
                                             "in_names": {}, "out_names": {}})
                    g["net"] += d
                    g["absum"] += abs(d)
                    g["n"] += 1
                    if d > 0:
                        g["n_in"] += 1
                    elif d < 0:
                        g["n_out"] += 1
            except Exception:  # noqa: BLE001 — one fund must not break the rollup
                log.debug("group_flow: skipped fund %s (deltas)", slug, exc_info=True)
        # pass 2: map this-cycle book positions onto the (now complete) group set
        for slug, fi in included.items():
            try:
                for pos in (fi.get("book") or []):
                    action = str(pos.get("action") or "")
                    if action not in _BUY_ACTIONS and action not in _SELL_ACTIONS:
                        continue
                    tk = str(pos.get("ticker") or "")
                    pp = _f(pos.get("pct_book")) or 0.0
                    for key, g in agg.items():
                        if _pos_in_group(pos, key, level):
                            side = "in_names" if action in _BUY_ACTIONS else "out_names"
                            g[side][tk] = g[side].get(tk, 0.0) + pp
            except Exception:  # noqa: BLE001 — one fund must not break the rollup
                log.debug("group_flow: skipped fund %s (names)", slug, exc_info=True)

        if not agg:
            return None

        def _top(names: dict[str, float]) -> list[dict]:
            ranked = sorted(names.items(), key=lambda kv: (-kv[1], kv[0]))
            return [{"ticker": t, "pp": round(p, 2)} for t, p in ranked[:top_names_n]]

        groups = []
        for key, g in agg.items():
            label, label_zh = labels.get(key, (key, None))
            row = {
                "key": key,
                "label": label,
                "n_funds_in": g["n_in"],
                "n_funds_out": g["n_out"],
                "net_pp": round(g["net"], 2),
                "avg_pp": round(g["net"] / g["n"], 2) if g["n"] else None,
                "intensity": round(g["absum"], 2),
                "top_names_in": _top(g["in_names"]),
                "top_names_out": _top(g["out_names"]),
            }
            if label_zh:
                row["label_zh"] = label_zh
            groups.append(row)
        groups.sort(key=lambda r: (-r["net_pp"], r["key"]))

        lvl_en = "sector" if level == "sector" else "theme"
        lvl_zh = "行业" if level == "sector" else "主题"
        return {
            "groups": groups,
            "level": level,
            "n_funds": len(included),
            "asof": max(asof_dates) if asof_dates else _filing_asof(tracker),
            "method_en": (f"Σ of per-fund quarter-over-quarter {lvl_en} weight changes "
                          "(pp of each fund's book) across tracked funds; positive = "
                          "rotation in; current sector/theme map applied to history; "
                          "descriptive — not a forecast."),
            "method_zh": (f"跟踪基金最新季度环比{lvl_zh}权重变化加总（占各基金组合的百分点）；"
                          "正值=轮入；历史采用当前行业/主题映射；描述性统计——非预测。"),
        }
    except Exception:  # noqa: BLE001
        log.warning("group_flow failed (level=%s)", level, exc_info=True)
        return None


# --------------------------------------------------------------------------- #
# rotation_history — aggregate sector mix per quarter                           #
# --------------------------------------------------------------------------- #

def rotation_history(fund_intel: dict | None,
                     top_slugs: list[str] | None = None) -> list[dict]:
    """Aggregate sector mix per quarter across tracked funds, ascending by quarter.

    Returns [{period_end, weights: {sector: pct}, n_funds, weighting}...] ([] when
    nothing contributes). `top_slugs` restricts to those funds (the top-funds
    variant — the build calls this twice).

    WEIGHTING HONESTY: fund_intel.sector_series carries within-fund value-weighted
    sector percentages but NO per-quarter book value, so a true cross-fund value
    weighting is only possible when a series row carries `book_value_usd` (used
    opportunistically when EVERY contributing row that quarter has it). Otherwise
    funds are EQUAL-weighted and the row says `weighting: "equal"` — stated, never
    silently approximated. Sectors missing from a fund's vector count as 0 so the
    aggregate still sums to ~100. Classification is today's map applied to history
    (survivorship-lite — surface the method note wherever this renders). PURE.
    """
    try:
        funds = (fund_intel or {}).get("funds") or {}
        if not funds:
            return []
        wanted = ({str(s).lower() for s in top_slugs} if top_slugs else None)

        # period_end -> list of (weights_vector, book_value|None)
        per_q: dict[str, list[tuple[dict, float | None]]] = {}
        for slug, fi in funds.items():
            if wanted is not None and str(slug).lower() not in wanted:
                continue
            if not isinstance(fi, dict):
                continue
            for entry in (fi.get("sector_series") or []):
                try:
                    pe = str((entry or {}).get("period_end") or "")
                    weights = (entry or {}).get("weights") or {}
                    if not pe or not isinstance(weights, dict) or not weights:
                        continue
                    bv = _f((entry or {}).get("book_value_usd"))
                    per_q.setdefault(pe, []).append((weights, bv))
                except Exception:  # noqa: BLE001
                    continue

        out: list[dict] = []
        for pe in sorted(per_q):
            rows = per_q[pe]
            values = [bv for _, bv in rows]
            value_weighted = all(v is not None and v > 0 for v in values) and len(rows) > 0
            total = sum(v for v in values if v) if value_weighted else float(len(rows))
            if total <= 0:
                continue
            acc: dict[str, float] = {}
            for weights, bv in rows:
                w_fund = (bv / total) if value_weighted else (1.0 / total)
                for sector, pct in weights.items():
                    p = _f(pct)
                    if p is None:
                        continue
                    acc[str(sector)] = acc.get(str(sector), 0.0) + p * w_fund
            out.append({
                "period_end": pe,
                "weights": {k: round(v, 2) for k, v in
                            sorted(acc.items(), key=lambda kv: -kv[1])},
                "n_funds": len(rows),
                "weighting": "value" if value_weighted else "equal",
            })
        return out
    except Exception:  # noqa: BLE001
        log.warning("rotation_history failed", exc_info=True)
        return []


# --------------------------------------------------------------------------- #
# models — four descriptive boards                                              #
# --------------------------------------------------------------------------- #

def _buyer_base_rate(quarter_history: list[dict] | None) -> dict:
    """A fund's historical new/add record from its tracker quarter_history — the
    LATEST cohort EXCLUDED (F8: current-cycle buys are unresolved; counting them
    would be soft leakage). PURE.

    Aggregates rows with period_end STRICTLY BEFORE the latest period_end:
      n             = Σ n_buys over prior quarters,
      hit_rate      = n_buys-weighted mean of per-quarter hit rates,
      median_excess = median of the per-quarter median excesses (trade-level
                      detail is not carried in quarter_history, so this is the
                      median-of-medians — robust, and honest about its grain).
    Returns {median_excess: None, hit_rate: None, n: 0} when no prior quarter
    exists — displayed as an empty record, never imputed.
    """
    empty = {"median_excess": None, "hit_rate": None, "n": 0}
    rows = [r for r in (quarter_history or []) if isinstance(r, dict)
            and r.get("period_end")]
    if len(rows) < 2:
        return empty
    latest = max(str(r["period_end"]) for r in rows)
    prior = [r for r in rows if str(r["period_end"]) < latest]
    if not prior:
        return empty
    n_total = 0
    hit_num = 0.0
    medians: list[float] = []
    for r in prior:
        n = int(r.get("n_buys") or 0)
        hr = _f(r.get("hit_rate"))
        me = _f(r.get("median_excess"))
        if n > 0 and hr is not None:
            n_total += n
            hit_num += hr * n
        if me is not None:
            medians.append(me)
    return {
        "median_excess": round(statistics.median(medians), 4) if medians else None,
        "hit_rate": round(hit_num / n_total, 3) if n_total else None,
        "n": n_total,
    }


def _sector_of(ticker: str, cls: dict | None) -> str | None:
    """Sector for a ticker from the merged classification map, or None. PURE."""
    rec = (cls or {}).get(ticker)
    if isinstance(rec, dict):
        s = rec.get("sector")
        return str(s) if s else None
    return None


def _board(rows: list[dict], title_en: str, title_zh: str,
           method_en: str, method_zh: str, asof: str) -> dict:
    """Uniform board envelope — every board states its method and its as-of."""
    return {"rows": rows, "title_en": title_en, "title_zh": title_zh,
            "method_en": method_en, "method_zh": method_zh, "asof": asof}


def models(sm: dict | None, tracker: dict | None, stock_flow_d: dict | None,
           crowding: list[dict] | None, fund_intel: dict | None,
           cls: dict | None, cap_favored: int = 20, cap_conviction: int = 20,
           cap_uncrowded: int = 15, cap_rotating: int = 20) -> dict | None:
    """Four DESCRIPTIVE model boards. Every board is {rows, title_en, title_zh,
    method_en, method_zh, asof}; every row carries transparent `components`.
    Composites are percentile-normalized within the candidate set via norm() —
    never z-scored (small n). All boards live on the 13F FILING clock; no
    insider-lane number is blended in (SM2-R3). Descriptive rank — not a forecast;
    the conviction_buys cohort is pre-registered as ledger L5 so the composite
    earns a forward record the honest way. Returns None only when sm is empty. PURE.

      most_favored   最受青睐  — 0.4·pct(n_funds) + 0.3·pct(gw_breadth) +
                                 0.2·pct(d_funds_qoq) + 0.1·pct(top-10 presence).
      conviction_buys 高信念买入 — this-cycle new/add at conviction tier 'high' from
                                 grade-A/B funds, ranked conviction × w(grade);
                                 buyer_base_rate EXCLUDES the latest cohort (F8).
      asymmetric     冷门高信念 — titled "Uncrowded conviction" (F9; the JSON key
                                 stays `asymmetric`): high/moderate conviction,
                                 ≤3 tracked holders, grade-A/B buyer, confirmed-
                                 elevated crowding excluded; conviction ÷ n_funds.
      rotating_out   轮出榜    — ≥2 tracked funds selling, most negative
                                 grade-weighted breadth first.
    """
    try:
        by_ticker = (sm or {}).get("by_ticker") or {}
        if not by_ticker:
            return None
        asof = _filing_asof(tracker, sm)
        grades = _grade_map(tracker)
        by_fund = (tracker or {}).get("by_fund") or {}
        funds_intel = (fund_intel or {}).get("funds") or {}

        # flow + crowding lookups (both 13F-lane inputs)
        flow_gw: dict[str, float] = {}
        for side in ("in", "out"):
            for r in ((stock_flow_d or {}).get(side) or []):
                g = _f(r.get("gw_breadth"))
                if r.get("ticker") and g is not None:
                    flow_gw[str(r["ticker"])] = g
        crowd_tier: dict[str, str] = {}
        for r in (crowding or []):
            if isinstance(r, dict) and r.get("ticker"):
                crowd_tier[str(r["ticker"])] = str(r.get("crowding_tier") or "unavailable")

        # ---------------- most_favored ---------------- #
        candidates: list[dict] = []
        for ticker, rec in _dedup_by_ticker(by_ticker):
            try:
                if ticker in _INDEX_ETFS:
                    continue
                n_funds = int(rec.get("vip") or 0)
                if n_funds <= 0:
                    continue
                holders = [h for h in rec.get("holders", []) or []
                           if isinstance(h, dict) and h.get("action") != "exit"]
                top10 = sum(1 for h in holders
                            if h.get("position_rank") is not None
                            and int(h["position_rank"]) <= 10)
                hs = (rec.get("trend") or {}).get("holders_series") or []
                d_qoq = (int(hs[-1]) - int(hs[-2])) if len(hs) >= 2 else None
                issuer = next((str(h.get("issuer") or "") for h in holders
                               if h.get("issuer")), "")
                candidates.append({
                    "ticker": ticker, "issuer": issuer,
                    "n_funds": n_funds,
                    "gw_breadth": flow_gw.get(ticker, 0.0),
                    "d_funds_qoq": d_qoq,
                    "top10": top10,
                })
            except Exception:  # noqa: BLE001
                log.debug("models/most_favored: skipped %s", ticker, exc_info=True)

        favored_rows: list[dict] = []
        if candidates:
            sets = {
                "n_funds": [float(c["n_funds"]) for c in candidates],
                "gw_breadth": [float(c["gw_breadth"]) for c in candidates],
                "d_funds_qoq": [float(c["d_funds_qoq"] or 0.0) for c in candidates],
                "top10": [float(c["top10"]) for c in candidates],
            }
            weights = (("n_funds", 0.4), ("gw_breadth", 0.3),
                       ("d_funds_qoq", 0.2), ("top10", 0.1))
            for c in candidates:
                comps: dict[str, dict] = {}
                composite = 0.0
                for key, w in weights:
                    raw = c[key]
                    nv = norm(float(raw if raw is not None else 0.0), sets[key])
                    nv = nv if nv is not None else 0.5
                    composite += w * nv
                    comps[key] = {"value": raw, "norm": nv}
                favored_rows.append({
                    "ticker": c["ticker"], "issuer": c["issuer"],
                    "sector": _sector_of(c["ticker"], cls),
                    "composite": round(composite, 3),
                    "components": comps,
                })
            favored_rows.sort(key=lambda r: (-r["composite"], r["ticker"]))
            favored_rows = favored_rows[:cap_favored]

        # ------------- conviction_buys / asymmetric ------------- #
        conv_agg: dict[str, dict] = {}   # high-conviction A/B buys (L5 cohort feed)
        unc_agg: dict[str, dict] = {}    # high/moderate conviction (uncrowded board)
        for slug, fi in funds_intel.items():
            try:
                slug_l = str(slug).lower()
                grade = str(grades.get(slug_l, "n/a")).upper()
                if grade not in _TOP_GRADES:
                    continue
                if not isinstance(fi, dict):
                    continue
                meta = fi.get("book_meta") or {}
                filing_date = str(meta.get("filing_date")
                                  or (by_fund.get(slug_l) or {}).get("filing_date")
                                  or "")
                qh = ((by_fund.get(slug_l) or {}).get("scorecard") or {}) \
                    .get("quarter_history")
                base_rate = _buyer_base_rate(qh)
                fund_name = str((by_fund.get(slug_l) or {}).get("name") or slug)
                for pos in (fi.get("book") or []):
                    action = str(pos.get("action") or "")
                    if action not in _BUY_ACTIONS:
                        continue
                    conv = pos.get("conviction") or {}
                    tier = str(conv.get("tier") or "")
                    score = _f(conv.get("score"))
                    tk = str(pos.get("ticker") or "")
                    if not tk or tk in _INDEX_ETFS or score is None:
                        continue
                    buyer = {
                        "slug": slug_l, "name": fund_name, "grade": grade,
                        "action": action, "conviction": round(score, 1),
                        "pct_book": _f(pos.get("pct_book")),
                        "base_rate": base_rate,
                    }
                    if tier in ("high", "moderate"):
                        u = unc_agg.setdefault(tk, {"issuer": str(pos.get("issuer") or ""),
                                                    "buyers": []})
                        u["buyers"].append(buyer)
                    if tier == "high":
                        c = conv_agg.setdefault(tk, {"issuer": str(pos.get("issuer") or ""),
                                                     "buyers": [], "filing_dates": []})
                        c["buyers"].append(buyer)
                        if filing_date:
                            c["filing_dates"].append(filing_date)
            except Exception:  # noqa: BLE001
                log.debug("models/conviction: skipped fund %s", slug, exc_info=True)

        conviction_rows: list[dict] = []
        for tk, c in conv_agg.items():
            buyers = sorted(c["buyers"],
                            key=lambda b: -(b["conviction"] * grade_weight(b["grade"])))
            top = buyers[0]
            rank_score = top["conviction"] * grade_weight(top["grade"])
            conviction_rows.append({
                "ticker": tk, "issuer": c["issuer"],
                "sector": _sector_of(tk, cls),
                "rank_score": round(rank_score, 1),
                # top-level convenience keys — the ranking buyer, flattened for the
                # template's conviction_buys columns (buyer / grade / conviction).
                "fund_name": top["name"],
                "slug": top["slug"],
                "grade": top["grade"],
                "conviction": top["conviction"],
                "buyers": buyers,
                "buyer_base_rate": top["base_rate"],   # the ranking buyer's PRIOR record
                # L5 anchor: the buy is fully public once the LAST buyer has filed
                "filing_date": max(c["filing_dates"]) if c["filing_dates"] else "",
                "components": {"conviction": top["conviction"],
                               "grade": top["grade"],
                               "grade_w": grade_weight(top["grade"]),
                               "n_buyers": len(buyers)},
            })
        conviction_rows.sort(key=lambda r: (-r["rank_score"], r["ticker"]))
        conviction_rows = conviction_rows[:cap_conviction]

        uncrowded_rows: list[dict] = []
        for tk, u in unc_agg.items():
            rec = by_ticker.get(tk) or {}
            n_funds = int(rec.get("vip") or 0)
            if n_funds <= 0:
                n_funds = sum(1 for h in rec.get("holders", []) or []
                              if isinstance(h, dict) and h.get("action") != "exit") or 1
            if n_funds > 3:
                continue
            tier = crowd_tier.get(tk)   # None = not on the crowding radar (most-held only)
            if tier == "elevated":
                continue
            buyers = sorted(u["buyers"], key=lambda b: -b["conviction"])
            conv = buyers[0]["conviction"]
            uncrowded_rows.append({
                "ticker": tk, "issuer": u["issuer"],
                "sector": _sector_of(tk, cls),
                "rank_score": round(conv / n_funds, 1),
                # top-level convenience keys for the asymmetric board columns.
                "conviction": conv,
                "n_funds": n_funds,
                "crowding_tier": tier,
                "grade": buyers[0]["grade"],
                "buyers": buyers,
                "components": {"conviction": conv, "n_funds": n_funds,
                               "crowding_tier": tier,   # None rendered as n/a — honest
                               "grade": buyers[0]["grade"]},
            })
        uncrowded_rows.sort(key=lambda r: (-r["rank_score"], r["ticker"]))
        uncrowded_rows = uncrowded_rows[:cap_uncrowded]

        # ---------------- rotating_out ---------------- #
        rotating_rows: list[dict] = []
        for r in ((stock_flow_d or {}).get("out") or []):
            try:
                if int(r.get("n_selling") or 0) < 2:
                    continue
                rotating_rows.append({
                    "ticker": r.get("ticker"), "issuer": r.get("issuer"),
                    "sector": _sector_of(str(r.get("ticker") or ""), cls),
                    "gw_breadth": r.get("gw_breadth"),
                    "n_buying": r.get("n_buying"),
                    "n_selling": r.get("n_selling"),
                    "intensity": r.get("intensity"),
                    "est_flow_usd": r.get("est_flow_usd"),
                    "sell_funds": r.get("sell_funds") or [],
                    "components": {"gw_breadth": r.get("gw_breadth"),
                                   "n_selling": r.get("n_selling"),
                                   "intensity": r.get("intensity")},
                })
            except Exception:  # noqa: BLE001
                log.debug("models/rotating_out: skipped row", exc_info=True)
        rotating_rows.sort(key=lambda r: (_f(r.get("gw_breadth")) or 0.0,
                                          -(int(r.get("n_selling") or 0)),
                                          str(r.get("ticker") or "")))
        rotating_rows = rotating_rows[:cap_rotating]

        return {
            "most_favored": _board(
                favored_rows, "Most favored", "最受青睐",
                ("Composite = 0.4·pct(n tracked holders) + 0.3·pct(grade-weighted "
                 "breadth) + 0.2·pct(QoQ holder change) + 0.1·pct(top-10 presence), "
                 "each a percentile within the candidate set; "
                 "descriptive rank — not a forecast."),
                ("综合分 = 0.4·pct(跟踪持有基金数) + 0.3·pct(评级加权广度) + "
                 "0.2·pct(季度环比持有人变化) + 0.1·pct(前十大持仓出现次数)，"
                 "均为候选集内百分位；描述性排名——非预测。"), asof),
            "conviction_buys": _board(
                conviction_rows, "Conviction buys", "高信念买入",
                ("This cycle's new/add positions at conviction tier 'high' from "
                 "grade-A/B funds, ranked by conviction × grade weight; buyer base "
                 "rate aggregates that fund's PRIOR filing cycles only (latest "
                 "cohort excluded — unresolved); descriptive rank — not a forecast."),
                ("本周期评级 A/B 基金的高信念新建/加仓，按 信念分×评级权重 排名；"
                 "买家历史记录仅汇总该基金以往申报周期（最新批次尚未了结，已剔除）；"
                 "描述性排名——非预测。"), asof),
            "asymmetric": _board(
                uncrowded_rows, "Uncrowded conviction", "冷门高信念",
                ("High/moderate-conviction buys by grade-A/B funds in names held by "
                 "≤3 tracked funds, confirmed-elevated crowding excluded (names off "
                 "the crowding radar pass with tier shown as n/a), ranked by "
                 "conviction ÷ holder count; descriptive rank — not a forecast."),
                ("评级 A/B 基金的高/中信念买入，标的仅 ≤3 家跟踪基金持有，剔除已确认的"
                 "高拥挤度（未覆盖拥挤度雷达的标的保留并标注 n/a），按 信念分÷持有基金数 "
                 "排名；描述性排名——非预测。"), asof),
            "rotating_out": _board(
                rotating_rows, "Rotating out", "轮出榜",
                ("Names with ≥2 tracked funds selling this cycle, ranked by the most "
                 "negative grade-weighted breadth; descriptive rank — not a forecast."),
                ("本周期 ≥2 家跟踪基金卖出的标的，按评级加权广度最负排序；"
                 "描述性排名——非预测。"), asof),
            "asof": asof,
        }
    except Exception:  # noqa: BLE001
        log.warning("models failed", exc_info=True)
        return None
