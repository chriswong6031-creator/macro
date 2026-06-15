"""Build the searchable Canada / TSX analysis library (site/canadastockdata/*.json).

Canada parallel of scripts/build_china_library.py. Runs the SAME cycle/ladder
engine over the Canada universe (curated large-cap constituents from the breadth
close cache + sector ETFs + indices in store group 'canada') and writes one small
JSON per instrument that canada_stock.html fetches client-side. Instant search, no
keys, no rate limits. site/canadastockdata/ is gitignored — regenerated nightly.

Alpha-led (not reversal-led like A-shares): Canada is a developed, momentum-
persistent market, so the standout ranking leads with sector-neutral residual
momentum (engine/residual_alpha.py) blended with cycle timing at CA_ALPHA_WEIGHT.
Each record carries a `tv` TradingView symbol (e.g. RY.TO -> TSX:RY) for the embed.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cycles import analyze  # noqa: E402
from engine.residual_alpha import compute_residual_alpha  # noqa: E402
from engine.setups import CA_ALPHA_WEIGHT, rank_setups, setup_score  # noqa: E402
from engine.technicals import season_line, seasonality, snapshot  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("canada_library")

TSX_INDEX = "^GSPTSE"   # cap-weighted TSX market proxy for the residual-alpha leg


def tv_symbol(ticker: str) -> str:
    """TradingView symbol for a TSX listing. RY.TO -> TSX:RY; GIB-A.TO -> TSX:GIB.A
    (dash class shares use a dot on TV); the Composite + ETFs map to a TSX ETF proxy."""
    if ticker == "^GSPTSE":
        return "TSX:XIC"
    if ticker.endswith(".TO"):
        return "TSX:" + ticker[:-3].replace("-", ".")
    return ticker


def _one(ticker: str, close: pd.Series, high: pd.Series | None,
         name: str, sector: str) -> dict | None:
    c = close.dropna()
    if len(c) < 300:
        return None
    res = analyze(c, high, kind="equity")
    if not res.get("ladder"):
        return None
    month = int(c.index.max().month)
    seas = seasonality(c)
    return {
        "ticker": ticker, "name": name, "sector": sector, "tv": tv_symbol(ticker),
        "asof": str(c.index.max().date()), "history_days": int(len(c)),
        "tech": snapshot(c),
        "season_this": season_line(seas, month),
        "season_next": season_line(seas, month % 12 + 1),
        "season_this_zh": season_line(seas, month, zh=True),
        "season_next_zh": season_line(seas, month % 12 + 1, zh=True),
        **res,
    }


def _breadth_panel() -> tuple[pd.DataFrame, dict[str, str], dict[str, str]]:
    """(closes, ticker->sector, ticker->name) for the residual-alpha cross-section +
    the search library. Prefers the BROAD search universe (canada_search = the full
    S&P/TSX Composite via iShares XIC, proper names + GICS sectors), falling back to
    the curated breadth cache (canada_breadth, ~74 names with ticker-as-name) when the
    broad panel isn't present. The regime engine itself stays on the breadth gauge."""
    dd = config.data_dir()
    sources = [
        (dd / "canada_search" / "closes.parquet", dd / "canada_search" / "members.parquet"),
        (dd / "canada_breadth" / "_closes_cache.parquet", dd / "canada_breadth" / "constituents.parquet"),
    ]
    for cp, mp in sources:
        if not (cp.exists() and mp.exists()):
            continue
        try:
            closes = pd.read_parquet(cp).sort_index()
            closes = closes.loc[:, ~closes.columns.duplicated()]
            members = pd.read_parquet(mp)
        except Exception as e:  # noqa: BLE001
            log.warning("canada panel unreadable (%s: %s)", cp.parent.name, e)
            continue
        if members.index.name != "symbol" and "symbol" in members.columns:
            members = members.set_index("symbol")
        tkr_sector = {t: str(s) for t, s in members["sector"].items()}
        tkr_name = {t: str(n) for t, n in members["name"].items()} if "name" in members.columns else {}
        log.info("canada library panel: %s (%d names)", cp.parent.name, closes.shape[1])
        return closes, tkr_sector, tkr_name
    return pd.DataFrame(), {}, {}


def compute_canada_alpha() -> dict | None:
    """Sector-neutral residual-momentum cross-section over the curated TSX large-cap
    panel (breadth close cache), with the S&P/TSX Composite as the market leg. Same
    engine as the US/China (engine/residual_alpha.py). Best-effort -> None on any gap."""
    closes, tkr_sector, names = _breadth_panel()
    if closes.empty:
        log.warning("canada alpha: breadth panel missing — skipped")
        return None
    mdf = store.read("canada", TSX_INDEX)
    if mdf is None or "close" not in mdf.columns:
        log.warning("canada alpha: no TSX (%s) market series — skipped", TSX_INDEX)
        return None
    market = mdf["close"].pct_change(fill_method=None)
    try:
        alpha = compute_residual_alpha(closes, market, tkr_sector)
    except Exception as e:  # noqa: BLE001 — additive leg, never fatal
        log.warning("canada alpha engine failed (%s) — skipped", e)
        return None
    if not alpha:
        return None

    def _fix(recs):
        for r in recs or []:
            r["name"] = names.get(r.get("ticker"), r.get("name"))
    _fix(alpha.get("top"))
    for sec in (alpha.get("by_sector") or {}).values():
        _fix(sec.get("leaders"))
        _fix(sec.get("laggards"))
    alpha["market"] = "S&P/TSX Composite"
    log.info("canada alpha: %d names, %d sectors", alpha.get("n"), len(alpha.get("by_sector", {})))
    return alpha


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
    return (f'<svg class="nch" viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
            f'width="100%" height="{h}">'
            f'<polyline points="0,{h} {pts} {w},{h}" fill="{color}" opacity="0.12" stroke="none"/>'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.7" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{color}"/></svg>')


def compute_canada_standouts(setups: dict | None) -> dict | None:
    """Enrich the alpha-led `setups.buy` shortlist into US-parity 'Standout
    individual stocks' cards — adds per-stock price + off-52w-high + a compact
    sparkline. Best-effort: returns setups with each buy row enriched."""
    if not setups or not setups.get("buy"):
        return setups
    site = config.ROOT / config.load()["storage"]["site_dir"]
    cd = site / "canadastockdata"
    closes, _, _ = _breadth_panel()
    for r in setups["buy"]:
        t = r["ticker"]
        f = cd / f"{t.replace('=', '_').replace('^', '_')}.json"
        if f.exists():
            try:
                rec = json.loads(f.read_text())
                tech = rec.get("tech", {})
                r["price"] = tech.get("price")
                r["off_high"] = tech.get("off_52w_high_pct")
            except Exception:  # noqa: BLE001
                pass
        if not closes.empty and t in closes.columns:
            s = closes[t].dropna().tail(64).tolist()
            col = ("var(--up)" if r.get("dir") == "up"
                   else "var(--down)" if r.get("dir") == "down" else "var(--muted)")
            r["spark_svg"] = _spark_svg(s, color=col)
    return setups


def universe() -> list[tuple[str, pd.Series, pd.Series | None, str, str]]:
    """(ticker, close, high|None, name, sector) for everything analyzable."""
    out: list[tuple] = []
    seen: set[str] = set()
    cy = config.load()["canada"]["yahoo"]

    # broad search universe (full S&P/TSX Composite via iShares XIC) when present,
    # else the curated breadth close cache — see _breadth_panel()
    closes, tkr_sector, tkr_name = _breadth_panel()
    for t in closes.columns:
        if t in seen:
            continue
        out.append((t, closes[t], None, tkr_name.get(t, t), tkr_sector.get(t, "—")))
        seen.add(t)
    if not out:
        log.warning("no canada search/breadth panel — library covers ETFs/indices only")

    # sector ETFs + broad indices from the canada store (deeper history than the cache)
    labels = {**{k: (v[0], "Sector ETF") for k, v in cy["sector_etfs"].items()},
              **{k: (v, "Index") for k, v in cy["indices"].items()}}
    for t, (nm, sec) in labels.items():
        if t in seen:
            continue
        df = store.read("canada", t)
        if df is None or "close" not in df.columns:
            continue
        out.append((t, df["close"], None, nm, sec))
        seen.add(t)
    return out


def _setup_score(rec: dict) -> tuple[float, dict] | None:
    """Alpha-led setup rank for a TSX name: residual momentum LEADS (CA_ALPHA_WEIGHT)
    with the cycle entry as the timing overlay, via the shared engine.setups."""
    return setup_score(rec, alpha_weight=CA_ALPHA_WEIGHT)


def main(alpha: dict | None = None) -> dict | None:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    outdir = site / "canadastockdata"
    outdir.mkdir(parents=True, exist_ok=True)

    if alpha is None:
        alpha = compute_canada_alpha()
    alpha_pt = (alpha or {}).get("per_ticker", {})
    if alpha:
        fdir = site / "factordata"
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / "canada_alpha.json").write_text(json.dumps(alpha, separators=(",", ":"), default=str))

    index, cand, built, failed = [], [], 0, 0
    sector_by: dict[str, str] = {}
    uni = universe()

    # refresh yfinance fundamentals up front (best-effort, capped) so pretty company
    # display names + the fundamentals panel are available for THIS run's records.
    from engine import canada_fundamentals
    try:
        canada_fundamentals.fetch_info([t for t, *_ in uni], max_new=40)
    except Exception as e:  # noqa: BLE001
        log.warning("canada fundamentals fetch failed (%s)", e)
    # earnings drip (get_earnings_dates for .TO names) — capped + freshness-cached, the
    # same up-front best-effort pattern; the per-stock 📅 panel reads what's been collected.
    try:
        canada_fundamentals.fetch_earnings([t for t, *_ in uni], max_new=40)
    except Exception as e:  # noqa: BLE001
        log.warning("canada earnings fetch failed (%s)", e)
    names_map = canada_fundamentals.display_names()

    for ticker, close, high, name, sector in uni:
        name = names_map.get(ticker) or name
        try:
            rec = _one(ticker, close, high, name, sector)
        except Exception as e:  # noqa: BLE001 — one bad ticker must not kill the library
            log.debug("canada library %s failed: %s", ticker, e)
            rec = None
        if rec is None:
            failed += 1
            continue
        if alpha_pt.get(ticker):
            rec["alpha"] = alpha_pt[ticker]
            sc = _setup_score(rec)
            if sc:
                cand.append(sc)
        safe = ticker.replace("=", "_").replace("^", "_")
        (outdir / f"{safe}.json").write_text(json.dumps(rec, default=str))
        idx = {"t": ticker, "n": name, "s": sector, "st": rec["ladder"]["state"]}
        if rec.get("alpha", {}).get("alpha") is not None:
            idx["a"] = rec["alpha"]["alpha"]
        index.append(idx)
        sector_by[ticker] = sector
        built += 1

    # descriptive FUNDAMENTALS (yfinance get_info: valuation + forward-val + sell-side
    # consensus + positioning) and EARNINGS (get_earnings_dates: next date + surprise
    # history) — context, not signals. Attached in ONE pass; each block degrades
    # independently (a missing field just hides its chip/panel).
    fmap: dict[str, dict] = {}
    earn: dict[str, dict] = {}
    try:
        fmap = canada_fundamentals.build_all(sector_by)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("canada fundamentals build failed (%s)", e)
    try:
        earn = canada_fundamentals.earnings_map()
    except Exception as e:  # noqa: BLE001
        log.warning("canada earnings unavailable (%s)", e)
    for ticker in set(fmap) | set(earn):
        patch: dict = {}
        if fmap.get(ticker):
            patch["fundamentals"] = fmap[ticker]
        if earn.get(ticker):
            patch["earnings"] = earn[ticker]
        if not patch:
            continue
        safe = ticker.replace("=", "_").replace("^", "_")
        fp = outdir / f"{safe}.json"
        if not fp.exists():
            continue
        try:
            rec = json.loads(fp.read_text())
            rec.update(patch)
            fp.write_text(json.dumps(rec, default=str))
        except Exception:  # noqa: BLE001
            continue
    fset = set(fmap)
    for idx in index:
        if idx["t"] in fset:
            idx["f"] = 1
    log.info("canada context attached: fund %d · earnings %d", len(fmap), len(earn))
    (outdir / "index.json").write_text(json.dumps(index))

    cal = config.data_dir() / "canada_regime" / "ladder_calibration.json"
    if cal.exists():
        (outdir / "calibration.json").write_text(cal.read_text())

    # cross-sectional alpha-led "Top setups" — selection (alpha) × timing (cycle)
    setups = None
    if cand:
        # alpha-led (rank_by="alpha"): like the US, Canada residual momentum is the
        # positive-IC selection leg; cycle timing is displayed context, not the sort key.
        setups = rank_setups(cand, as_of=(alpha or {}).get("as_of"), rank_by="alpha")
        (site / "factordata").mkdir(parents=True, exist_ok=True)
        (site / "factordata" / "canada_setups.json").write_text(
            json.dumps(setups, separators=(",", ":"), default=str))
    log.info("canada library: %d analyzed, %d skipped (thin history), %d setups",
             built, failed, len(cand))
    return setups


if __name__ == "__main__":
    main()
    sys.exit(0)
