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

# convergence weights (display only — equal-ish, value tilted down given the negative
# A-share value Sharpe; the point is agreement across independent feeds, not a backtest)
_W = {"analyst": 0.40, "value": 0.30, "margin": 0.30}
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


def by_ticker(min_signals: int = 2, top_n: int = 30) -> dict | None:
    """Per-ticker convergence over analyst + valuation + margin. None if no data. Never raises."""
    try:
        from engine import china_extras as ce
        analyst = ce.analyst_consensus() or {}
        valuation = ce.valuation_percentile() or {}
        margin = ce.margin_positioning() or {}
        if not (analyst or valuation or margin):
            return None
        names = _name_map()
        universe = set(analyst) | set(valuation) | set(margin)
        rows: list[dict] = []
        for t in universe:
            a = _analyst_score(analyst.get(t, {})) if t in analyst else None
            v = _value_score(valuation.get(t, {})) if t in valuation else None
            m, crowded = _margin_score(margin.get(t, {})) if t in margin else (None, False)
            present = {"analyst": a, "value": v, "margin": m}
            avail = {k: s for k, s in present.items() if s is not None}
            if len(avail) < min_signals:
                continue
            wsum = sum(_W[k] for k in avail)
            conv = sum(_W[k] * s for k, s in avail.items()) / wsum if wsum else 0.0
            flags = []
            if crowded:
                flags.append("leverage_crowded")
            rows.append({
                "ticker": t, "name": names.get(t, t),
                "convergence": round(conv, 3), "n_signals": len(avail),
                "analyst": None if a is None else round(a, 2),
                "value": None if v is None else round(v, 2),
                "margin": None if m is None else round(m, 2),
                "flags": flags,
            })
        if not rows:
            return None
        # primary: convergence; tie-break: more independent feeds agreeing ranks higher
        rows.sort(key=lambda r: (r["convergence"], r["n_signals"]), reverse=True)
        # the meaningful slice — ALL THREE independent feeds present (analyst+value+margin)
        triple = [r for r in rows if r["n_signals"] >= 3]
        triple.sort(key=lambda r: r["convergence"], reverse=True)
        crowding = [r["ticker"] for r in rows if "leverage_crowded" in r["flags"]][:20]
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


def mastermind(bt: dict | None = None) -> dict:
    """Compact context emit for the intel bus + future China Mastermind (never a size)."""
    bt = bt or by_ticker() or {}
    # prefer the all-three-agree slice; fall back to the broad list to fill 10
    triple = [r["ticker"] for r in bt.get("triple", [])]
    top = triple + [r["ticker"] for r in bt.get("top", []) if r["ticker"] not in triple]
    return {
        "schema": "china_altdata.mastermind.v1", "is_context_only": True,
        "asof": bt.get("asof", str(date.today())),
        "n_triple": bt.get("n_triple"), "n_universe": bt.get("n_universe"),
        "convergence_top": top[:10],
        "convergence_bottom": [r["ticker"] for r in bt.get("bottom", [])[:10]],
        "crowding_flags": bt.get("crowding_flags", []),
    }
