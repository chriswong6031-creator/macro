"""Build the searchable International analysis library (site/intlstockdata/*.json)
+ the pooled cross-market standouts ranking.

Runs the shared cycle/ladder engine (engine.cycles.analyze) over the pooled
universe (collectors/intl_universe -> data/intl_search) and writes one small JSON
per instrument that intl_stock.html fetches client-side. Each record carries its
country `flag` + `market` so the Stock dashboard can show where a name is from.

Standouts are alpha-led (developed, momentum-persistent markets, like Canada/US):
sector-neutral residual momentum LEADS, computed STRICTLY WITHIN each market
(engine.intl_stocks.compute_intl_alpha), the cycle entry is the timing overlay.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cycles import analyze  # noqa: E402
from engine.intl_stocks import compute_intl_alpha, panel  # noqa: E402
from engine.setups import rank_setups, setup_score  # noqa: E402
from engine.technicals import season_line, seasonality, snapshot  # noqa: E402
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("intl_library")

INTL_ALPHA_WEIGHT = 0.55   # alpha-led (developed/momentum-persistent), like Canada

# Yahoo suffix -> TradingView exchange prefix (best-effort; embed degrades if off)
_TV_EXCH = {".T": "TSE", ".KS": "KRX", ".KQ": "KOSDAQ", ".TW": "TWSE", ".L": "LSE",
            ".DE": "XETR", ".PA": "EURONEXT", ".AS": "EURONEXT", ".BR": "EURONEXT",
            ".MI": "MIL", ".MC": "BME", ".SW": "SIX", ".ST": "OMXSTO", ".HE": "OMXHEX",
            ".CO": "OMXCOP", ".OL": "OSL", ".VI": "VIE", ".LS": "EURONEXT", ".IR": "EURONEXT"}


def tv_symbol(ticker: str) -> str:
    for sfx, exch in _TV_EXCH.items():
        if ticker.endswith(sfx):
            return f"{exch}:{ticker[:-len(sfx)].replace('-', '.')}"
    return ticker


def _one(ticker: str, close: pd.Series, name: str, sector: str,
         flag: str, market: str) -> dict | None:
    c = close.dropna()
    if len(c) < 300:
        return None
    res = analyze(c, None, kind="equity")
    if not res.get("ladder"):
        return None
    month = int(c.index.max().month)
    seas = seasonality(c)
    return {
        "ticker": ticker, "name": name, "sector": sector, "tv": tv_symbol(ticker),
        "flag": flag, "market": market,
        "asof": str(c.index.max().date()), "history_days": int(len(c)),
        "tech": snapshot(c),
        "season_this": season_line(seas, month),
        "season_next": season_line(seas, month % 12 + 1),
        "season_this_zh": season_line(seas, month, zh=True),
        "season_next_zh": season_line(seas, month % 12 + 1, zh=True),
        **res,
    }


def _spark_svg(vals: list[float], color: str = "var(--link)", w: int = 240, h: int = 42) -> str:
    vals = [float(v) for v in vals if v is not None and v == v]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n, pad = len(vals), h * 0.12

    def xy(i, v):
        return (i / (n - 1) * w, (h - pad) - ((v - lo) / rng) * (h - 2 * pad) + pad)

    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, v) for i, v in enumerate(vals)))
    lx, ly = xy(n - 1, vals[-1])
    return (f'<svg class="nch" viewBox="0 0 {w} {h}" preserveAspectRatio="none" width="100%" height="{h}">'
            f'<polyline points="0,{h} {pts} {w},{h}" fill="{color}" opacity="0.12" stroke="none"/>'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.7" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{color}"/></svg>')


def main(alpha: dict | None = None) -> dict | None:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    outdir = site / "intlstockdata"
    outdir.mkdir(parents=True, exist_ok=True)

    closes, members = panel()
    if closes.empty or members.empty:
        log.warning("intl library: no universe panel — skipped")
        return None
    if alpha is None:
        alpha = compute_intl_alpha(closes, members)
    alpha_pt = (alpha or {}).get("per_ticker", {})

    index, cand, built, failed = [], [], 0, 0
    for ticker in closes.columns:
        if ticker not in members.index:
            continue
        m = members.loc[ticker]
        try:
            rec = _one(ticker, closes[ticker], str(m["name"]), str(m["sector"]),
                       str(m["flag"]), str(m["market"]))
        except Exception as e:  # noqa: BLE001 — one bad ticker can't kill the library
            log.debug("intl library %s failed: %s", ticker, e)
            rec = None
        if rec is None:
            failed += 1
            continue
        if alpha_pt.get(ticker):
            rec["alpha"] = alpha_pt[ticker]
            sc = setup_score(rec, alpha_weight=INTL_ALPHA_WEIGHT)
            if sc:
                cand.append(sc)
        safe = ticker.replace("=", "_").replace("^", "_")
        (outdir / f"{safe}.json").write_text(json.dumps(rec, default=str))
        idx = {"t": ticker, "n": rec["name"], "s": rec["sector"], "st": rec["ladder"]["state"],
               "fl": rec["flag"], "mk": rec["market"]}
        if rec.get("alpha", {}).get("alpha") is not None:
            idx["a"] = rec["alpha"]["alpha"]
        index.append(idx)
        built += 1

    (outdir / "index.json").write_text(json.dumps(index))
    # Bespoke chart OHLC (close-only area series) read by intl_stock.html's chart.js —
    # pure serialisation of intl_search closes; never break the library over the garnish.
    try:
        from scripts.build_chart_data import emit_close_only
        nc = emit_close_only(outdir / "index.json", config.data_dir() / "intl_search" / "closes.parquet",
                             outdir.parent / "intlohlc", "intl")
        log.info("intl chart data: %d ohlc files", nc)
    except Exception as e:  # noqa: BLE001
        log.warning("intl chart data step failed (%s)", e)

    # pooled alpha-led "standout individual stocks" shortlist (flags attached)
    setups = None
    if cand:
        setups = rank_setups(cand, as_of=(alpha or {}).get("as_of"), rank_by="alpha", n_buy=60)
        for r in (setups.get("buy") or []):
            t = r["ticker"]
            if t in members.index:
                r["flag"] = str(members.loc[t, "flag"])
                r["market"] = str(members.loc[t, "market"])
            f = outdir / f"{t.replace('=', '_').replace('^', '_')}.json"
            if f.exists():
                try:
                    tech = json.loads(f.read_text()).get("tech", {})
                    r["price"] = tech.get("price")
                    r["off_high"] = tech.get("off_52w_high_pct")
                except Exception:  # noqa: BLE001
                    pass
            if t in closes.columns:
                s = closes[t].dropna().tail(64).tolist()
                col = ("var(--up)" if r.get("dir") == "up" else
                       "var(--down)" if r.get("dir") == "down" else "var(--muted)")
                r["spark_svg"] = _spark_svg(s, color=col)
        (site / "factordata").mkdir(parents=True, exist_ok=True)
        (site / "factordata" / "intl_setups.json").write_text(
            json.dumps(setups, separators=(",", ":"), default=str))
    log.info("intl library: %d analyzed, %d skipped, %d standouts",
             built, failed, len(cand))
    return setups


if __name__ == "__main__":
    main()
    sys.exit(0)
