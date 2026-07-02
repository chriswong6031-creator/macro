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

# convergence weights — DEFAULT prior (used until china_signal_lab.leg_weights_for('altdata')
# returns earned, forward-return-validated weights). Two-sided signed legs only: value/margin
# (own-history valuation cheapness + financing trend), flow (主力资金 net inflow — Tushare-GATED,
# the push2 replacement, absent without a token), comment (千股千评 inst-vs-retail + main-force),
# lhb (龙虎榜 hot-money net buy — SIGN-FLIPPED NEGATIVE per research/CHINA_ENGINE_REASSESSMENT.md:
#   raw hot-money LHB flag on dip names measured −1.43%/21d fill-realistic excess, cluster-t≈−2.2
#   (931 obs). The apparent positive is all in survivorship-inflated up-day flags. The raw hotmoney
#   score as designed DRAINS alpha → DEMOTION weight. See §W6-CN Fix 2.),
# block (大宗交易 premium/discount — SIGN-FLIPPED NEGATIVE per research/CHINA_ENGINE_REASSESSMENT.md:
#   block-trade PREMIUM leg as designed measured −0.60%/5d, t≈−2.8. Premium = institutional unload
#   on dip names, not accumulation. DEMOTION weight. See §W6-CN Fix 2.),
# analyst is a near-useless GATE (China sell-side ~universally "buy"). The point is cross-sectional
# agreement.
_W_DEFAULT = {"value": 0.24, "margin": 0.20, "flow": 0.18, "comment": 0.15,
              "lhb": -0.10,   # DEMOTION: measured −1.43%/21d on dip names (§W6-CN Fix 2)
              "block": -0.05, # DEMOTION: measured −0.60%/5d premium-block drag (§W6-CN Fix 2)
              "analyst": 0.08}
# _W_DEFAULT is the live fallback returned by _leg_weights() when china_signal_lab has no
# earned weights yet. Nothing should reference _W_DEFAULT directly; always go through
# _leg_weights() so the earned-weights path is used when available.
_CROWD_CHG = 25.0   # financing 20d change % above which we flag leverage crowding

# PROBATIONARY confirmers — emit as chips and log to the forward ledger for accrual.
# ZERO score weight until the ledger matures (~2 months after store-group fix in CN-1).
# Passport: basis=probationary (research/ENGINE_FIX_MASTERPLAN.md §W6-CN).
# deep-discount blocks (≤−15%): +3.45%/21d fill-realistic (t≈3.4, 669 obs) — best
#   northbound replacement found (§8 Q4 answer, CHINA_ENGINE_REASSESSMENT.md).
# inst-seat LHB (≥2 institutional seats, net buy): +1.57%/21d (t≈0.8, 140 obs) — weak-positive,
#   never negative, forward-ledger candidate (see also china_discovery.lhb_inst).
_PROBATIONARY_DISCOUNT_PCT = -15.0   # block discount threshold for the deep-discount confirmer


def _leg_weights() -> dict:
    """Earned, forward-return-validated leg weights from china_signal_lab; default prior on miss."""
    try:
        from engine import china_signal_lab
        w = china_signal_lab.leg_weights_for("altdata")
        if w:
            return w
    except Exception:  # noqa: BLE001
        pass
    return dict(_W_DEFAULT)


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
    # new US-parity per-name legs (all two-sided signed). Degrade to {} when a cache is absent.
    comment = ce.comment() or {}
    lhb = ce.lhb() or {}
    block = ce.block_trades() or {}
    flow = ce.fundflow() or {}        # 主力资金 net inflow — Tushare-GATED ({} without a token)
    try:
        from engine import china_crowding
        crowd_map = china_crowding.compute_crowding_map() or {}
    except Exception:  # noqa: BLE001
        crowd_map = {}
    names = _name_map()
    for d in (comment, lhb, block, flow):     # backfill names from the new feeds too
        for t, v in d.items():
            names.setdefault(t, v.get("name", t) if isinstance(v, dict) else t)
    universe = (set(analyst) | set(valuation) | set(margin) | set(comment) | set(lhb)
                | set(block) | set(flow))
    raw = {"analyst": {}, "value": {}, "margin": {}, "comment": {}, "lhb": {}, "block": {}, "flow": {}}
    crowd_legacy = {}
    for t in universe:
        if t in analyst:
            raw["analyst"][t] = _analyst_score(analyst[t])
        if t in valuation:
            raw["value"][t] = _value_score(valuation[t])
        if t in margin:
            ms, c = _margin_score(margin[t])
            raw["margin"][t] = ms
            crowd_legacy[t] = c
        if t in comment and comment[t].get("comment_score") is not None:
            raw["comment"][t] = comment[t]["comment_score"]
        if t in lhb and lhb[t].get("hotmoney_score") is not None:
            raw["lhb"][t] = lhb[t]["hotmoney_score"]
        if t in block and block[t].get("block_score") is not None:
            raw["block"][t] = block[t]["block_score"]
        if t in flow and flow[t].get("flow_score") is not None:
            raw["flow"][t] = flow[t]["flow_score"]
    pct = {leg: _rank_pct(vals) for leg, vals in raw.items()}
    W = _leg_weights()
    rows: list[dict] = []
    for t in universe:
        present = {leg: pct[leg][t] * 2 - 1 for leg in pct if t in pct[leg]}
        if len(present) < min_signals:
            continue
        wsum = sum(W.get(k, 0.0) for k in present) or 1.0
        conv = sum(W.get(k, 0.0) * s for k, s in present.items()) / wsum
        side = "accumulate" if conv > 0.05 else ("distribute" if conv < -0.05 else "neutral")
        sign = 1 if conv > 0 else (-1 if conv < 0 else 0)
        # n_signals corroboration discount: a single-leg name cannot top the board at 97.
        # Scale linearly from 0→1/3 signals, capped at 1.0 for ≥3 legs. Matches the
        # brief's requirement that conv=0.5 with n=1 scores below conv=0.5 with n=3.
        n_present = len(present)
        c100 = cv.to_100(abs(conv) * min(1.0, n_present / 3.0))
        _bk, ben, bzh = cv.signed_band(c100, sign)
        reasons = [k for k, s in present.items() if (s > 0) == (conv > 0) and abs(s) > 0.05]
        flags = list((crowd_map.get(t) or {}).get("flags") or [])
        if not flags and crowd_legacy.get(t):
            flags = ["leverage_crowded"]
        row = {
            "ticker": t, "name": names.get(t, t),
            "convergence": round(conv, 3), "n_signals": len(present),
            "conviction100": c100, "conviction_band_en": ben, "conviction_band_zh": bzh,
            "side": side, "reasons": reasons, "flags": flags,
        }
        for leg in raw:
            row[leg] = None if leg not in present else round(present[leg], 2)
        rows.append(row)
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


def _probationary_chips() -> dict[str, dict]:
    """Probationary confirmers — emitted as chips + logged for the forward ledger.
    ZERO score weight until the ledger matures (~2 months post CN-1 store-group fix).
    Passport: basis=probationary (research/ENGINE_FIX_MASTERPLAN.md §W6-CN Fix 2).

    Returns {ticker: {deep_discount: bool, inst_lhb: bool, ...}} for names that fire at
    least one probationary leg. These chips render on the detail page but DO NOT enter
    any ranking path.
    """
    try:
        from engine import china_extras as ce
        out: dict[str, dict] = {}
        # (1) deep-discount blocks (≤−15% discount): +3.45%/21d fill-realistic (t≈3.4, 669 obs).
        #     Best northbound replacement found. Inverted from the raw block leg.
        #     Measured: research/CHINA_ENGINE_REASSESSMENT.md §Measurements / Sign tests.
        block = ce.block_trades() or {}
        for t, bv in block.items():
            prem = bv.get("avg_premium_pct") or 0.0
            amt = bv.get("block_amt_yi") or 0.0
            if prem <= _PROBATIONARY_DISCOUNT_PCT and amt > 0:
                out.setdefault(t, {})["deep_discount_block"] = {
                    "avg_premium_pct": round(prem, 2),
                    "block_amt_yi": round(amt, 2),
                    "passport": {
                        "basis": "probationary",
                        "measured": "+3.45%/21d fill-realistic t≈3.4 (669 obs, single regime)",
                        "source": "research/CHINA_ENGINE_REASSESSMENT.md §Q4/Sign tests",
                        "weight": 0.0,
                        "note": "Zero score weight until forward ledger matures.",
                    },
                }
        # (2) institutional-seat LHB net-buy (≥2 inst seats, net buy): +1.57%/21d (t≈0.8, 140 obs).
        #     Weak-positive, never negative — accrual candidate.
        lhb = ce.lhb() or {}
        for t, lv in lhb.items():
            if lv.get("leading") and lv.get("n_inst_buy", 0) >= 2 and lv.get("inst_net_buy_yi", 0.0) > 0:
                out.setdefault(t, {})["inst_seat_lhb"] = {
                    "n_inst_buy": lv.get("n_inst_buy"),
                    "inst_net_buy_yi": lv.get("inst_net_buy_yi"),
                    "inst_accum_score": lv.get("inst_accum_score"),
                    "passport": {
                        "basis": "probationary",
                        "measured": "+1.57%/21d t≈0.8 (140 obs, weak-positive, never negative)",
                        "source": "research/CHINA_ENGINE_REASSESSMENT.md §Q4/Sign tests",
                        "weight": 0.0,
                        "note": "Zero score weight until forward ledger matures.",
                    },
                }
        return out
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.debug("china_altdata probationary chips failed (%s)", e)
        return {}


def by_ticker(min_signals: int = 2, top_n: int = 30) -> dict | None:
    """Per-ticker convergence desk view (top/bottom/triple slices). Never raises."""
    try:
        rows = _compute_rows(min_signals)
        if not rows:
            return None
        triple = [r for r in rows if r["n_signals"] >= 3]
        crowding = [r["ticker"] for r in rows if r["flags"]][:20]
        # Probationary chips: deep-discount blocks + inst-seat LHB (ZERO weight, display only).
        # Emitted separately so they never contaminate the convergence score ranking.
        prob = _probationary_chips()
        # Annotate rows that carry a probationary chip
        for r in rows:
            pc = prob.get(r.get("ticker"))
            if pc:
                r["probationary_chips"] = pc
        return {
            "schema": SCHEMA, "is_context_only": True, "asof": str(date.today()),
            "built": datetime.now(timezone.utc).isoformat(),
            "n_universe": len(rows), "n_triple": len(triple),
            "triple": triple[:top_n],
            "top": rows[:top_n], "bottom": rows[-top_n:][::-1],
            "crowding_flags": crowding,
            "weights": _leg_weights(),
            # Probationary chip index: {ticker: {deep_discount_block?, inst_seat_lhb?}}
            # ZERO scoring weight; display chips + forward ledger seed only.
            "probationary": {t: c for t, c in prob.items()},
            "probationary_passport": {
                "basis": "probationary",
                "source": "research/CHINA_ENGINE_REASSESSMENT.md §Q4 / §W6-CN Fix 2",
                "weight": 0.0,
                "note": ("Zero score weight until ledger matures. deep_discount_block: "
                         "+3.45%/21d t≈3.4 (669 obs). inst_seat_lhb: +1.57%/21d t≈0.8 (140 obs)."),
            },
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
