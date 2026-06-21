"""China Alternative-Data desk — per-ticker smart-money convergence kernel.

LEAF · DISPLAY/CONTEXT-ONLY · KEYLESS · NO VALIDATED EDGE CLAIMED. The China analogue of
a US alt-data desk, but built from signals that survive a non-CN IP: it fuses the three
RELIABLE per-name A-share alt-data feeds already collected — sell-side consensus
(china_analyst), own-history valuation bands (china_valuation), and margin-financing trend
(china_margin_detail) — into a single cross-sectional "convergence" read per stock, plus
honest crowding flags. Reuses engine.china_extras parsers (one source of truth).

This is explicitly NOT scored into any allocation: A-share cross-sectional value Sharpe is
negative and sell-side ratings are opinion (see research/CHINA_HK_STOCK_SIGNALS.md). The
convergence is a display join + a Phase-0 candidate, never a sizer. It emits a compact
mastermind.json the intel bus reads as context. Never raises.
See research/CHINA_INTEL_POWERHOUSE.md §2.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "china_altdata.v1"

# convergence weights (display only). Value + margin carry it; analyst is a near-useless
# GATE in China (sell-side is ~universally "buy"), so it gets a low weight and mainly makes
# a name eligible for the all-three "triple" slice. The point is cross-sectional agreement.
_W = {"value": 0.45, "margin": 0.45, "analyst": 0.10}
_CROWD_CHG = 25.0   # financing 20d change % above which we flag leverage crowding


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _name_map() -> dict[str, str]:
    try:
        import pandas as pd
        p = config.data_dir() / "china_analyst" / "forecast.parquet"
        if not p.exists():
            return {}
        df = pd.read_parquet(p)
        if "ticker" in df.columns and "name" in df.columns:
            return {str(r.ticker): str(r.name) for r in df.itertuples()}
    except Exception:  # noqa: BLE001
        pass
    return {}


def _analyst_score(block: dict) -> float | None:
    buy, hold, sell = block.get("buy", 0), block.get("hold", 0), block.get("sell", 0)
    total = (buy or 0) + (hold or 0) + (sell or 0)
    if total <= 0:
        return None
    return _clip((buy - sell) / total)


def _value_score(payload: dict) -> float | None:
    pcts = []
    for k in ("pe", "pb", "ps"):
        d = payload.get(k) or {}
        pc = d.get("pctile")
        if pc is not None:
            pcts.append(float(pc))
    if not pcts:
        return None
    mean_pct = sum(pcts) / len(pcts)
    return _clip((50.0 - mean_pct) / 50.0)   # cheap vs own history -> positive


def _margin_score(block: dict) -> tuple[float | None, bool]:
    chg = block.get("chg_pct")
    if chg is None:
        return None, False
    return _clip(float(chg) / 20.0), float(chg) > _CROWD_CHG


def _rank_pct(vals: dict) -> dict:
    """Cross-sectional MID-RANK percentile (0..1) of each ticker's raw value among those that
    HAVE the feed. Centered later to [-1,1]. Tied values share one percentile — without this,
    the ~97%-unanimous-buy analyst feed would get spread across the whole band by sort order
    and flip stocks' accumulate/distribute side arbitrarily."""
    items = [(t, v) for t, v in vals.items() if v is not None]
    n = len(items)
    if n == 0:
        return {}
    if n == 1:
        return {items[0][0]: 0.5}
    order = sorted(items, key=lambda kv: kv[1])
    out: dict = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and order[j + 1][1] == order[i][1]:
            j += 1
        pct = ((i + j) / 2.0) / (n - 1)      # mean of the tied run's positional ranks
        for k in range(i, j + 1):
            out[order[k][0]] = pct
        i = j + 1
    return out


def _compute_rows(min_signals: int = 2) -> list[dict]:
    """Full per-ticker convergence rows (sorted desc). Rank-normalizes EACH feed cross-
    sectionally, then combines on a signed [-1,1] scale. Shared by by_ticker + convergence_map."""
    from engine import china_conviction as cv
    from engine import china_extras as ce
    analyst = ce.analyst_consensus() or {}
    valuation = ce.valuation_percentile() or {}
    margin = ce.margin_positioning() or {}
    if not (analyst or valuation or margin):
        return []
    names = _name_map()
    universe = set(analyst) | set(valuation) | set(margin)
    a_raw, v_raw, m_raw, crowd = {}, {}, {}, {}
    for t in universe:
        if t in analyst:
            a_raw[t] = _analyst_score(analyst[t])
        if t in valuation:
            v_raw[t] = _value_score(valuation[t])
        if t in margin:
            ms, c = _margin_score(margin[t])
            m_raw[t] = ms
            crowd[t] = c
    a_pct, v_pct, m_pct = _rank_pct(a_raw), _rank_pct(v_raw), _rank_pct(m_raw)
    rows: list[dict] = []
    for t in universe:
        present = {}
        if t in a_pct:
            present["analyst"] = a_pct[t] * 2 - 1
        if t in v_pct:
            present["value"] = v_pct[t] * 2 - 1
        if t in m_pct:
            present["margin"] = m_pct[t] * 2 - 1
        if len(present) < min_signals:
            continue
        wsum = sum(_W[k] for k in present)
        conv = sum(_W[k] * s for k, s in present.items()) / wsum if wsum else 0.0
        side = "accumulate" if conv > 0.05 else ("distribute" if conv < -0.05 else "neutral")
        sign = 1 if conv > 0 else (-1 if conv < 0 else 0)
        c100 = cv.to_100(abs(conv))
        _bk, ben, bzh = cv.signed_band(c100, sign)
        reasons = [k for k, s in present.items() if (s > 0) == (conv > 0) and abs(s) > 0.05]
        rows.append({
            "ticker": t, "name": names.get(t, t),
            "convergence": round(conv, 3), "n_signals": len(present),
            "conviction100": c100, "conviction_band_en": ben, "conviction_band_zh": bzh,
            "side": side,
            "analyst": None if "analyst" not in present else round(present["analyst"], 2),
            "value": None if "value" not in present else round(present["value"], 2),
            "margin": None if "margin" not in present else round(present["margin"], 2),
            "reasons": reasons,
            "flags": ["leverage_crowded"] if crowd.get(t) else [],
        })
    rows.sort(key=lambda r: (r["convergence"], r["n_signals"]), reverse=True)
    conv_pct = _rank_pct({r["ticker"]: r["convergence"] for r in rows})
    for r in rows:
        r["rank_pctile"] = round(conv_pct.get(r["ticker"], 0.5) * 100, 1)
    return rows


def convergence_map() -> dict[str, dict]:
    """{ticker: {convergence, side, name, conviction100}} over the FULL universe — the join the
    radar uses to surface per-divergence candidate names. {} on failure. Never raises."""
    try:
        return {r["ticker"]: {"convergence": r["convergence"], "side": r["side"],
                              "name": r["name"], "conviction100": r["conviction100"]}
                for r in _compute_rows()}
    except Exception as e:  # noqa: BLE001
        log.error("china_altdata.convergence_map failed (%s)", e)
        return {}


def by_ticker(min_signals: int = 2, top_n: int = 30) -> dict | None:
    """Per-ticker convergence desk view (top/bottom/triple slices). Never raises."""
    try:
        rows = _compute_rows(min_signals)
        if not rows:
            return None
        triple = [r for r in rows if r["n_signals"] >= 3]
        crowding = [r["ticker"] for r in rows if r["flags"]][:20]
        return {
            "schema": SCHEMA, "is_context_only": True, "asof": str(date.today()),
            "built": datetime.now(timezone.utc).isoformat(),
            "n_universe": len(rows), "n_triple": len(triple),
            "triple": triple[:top_n],
            "top": rows[:top_n], "bottom": rows[-top_n:][::-1],
            "crowding_flags": crowding,
            "weights": _W,
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_altdata.by_ticker failed (%s)", e)
        return None


def _slim(r: dict, side: str) -> dict:
    return {"ticker": r.get("ticker"), "name": r.get("name", r.get("ticker")),
            "convergence": r.get("convergence"), "conviction100": r.get("conviction100"),
            "n_signals": r.get("n_signals"), "reasons": r.get("reasons", []),
            "flags": r.get("flags", []), "side": side}


def mastermind(bt: dict | None = None) -> dict:
    """Rich context emit for the intel bus + future China Mastermind (never a size). Carries
    NAMES + conviction + reasons, not bare ticker strings."""
    bt = bt or by_ticker() or {}
    triple_ids = {r["ticker"] for r in bt.get("triple", [])}
    top = [_slim(r, "accumulate") for r in bt.get("triple", [])]
    for r in bt.get("top", []):
        if r["ticker"] not in triple_ids and len(top) < 10:
            top.append(_slim(r, r.get("side", "accumulate")))
    return {
        "schema": "china_altdata.mastermind.v2", "is_context_only": True,
        "asof": bt.get("asof", str(date.today())),
        "n_triple": bt.get("n_triple"), "n_universe": bt.get("n_universe"),
        "convergence_top": top[:10],
        "convergence_bottom": [_slim(r, "distribute") for r in bt.get("bottom", [])[:10]],
        "crowding_flags": bt.get("crowding_flags", []),
        "disclaimer_en": "Context only — a display join of three free feeds (consensus × valuation "
                         "× financing), no validated edge. A watchlist seed, never a size or trade.",
        "disclaimer_zh": "仅作背景——三个免费数据源（一致预期 × 估值 × 融资）的展示性合并，无已验证优势。"
                         "仅为自选股种子，绝非仓位或交易。",
    }
