"""Build the searchable Hong Kong / Hang Seng analysis library (site/hkstockdata/*.json).

HK parallel of scripts/build_china_library.py. Runs the SAME cycle/ladder engine
over the HK universe (curated constituents from the breadth close cache + HK
indices + ETF proxies in store group 'hk') and writes one small JSON per
instrument that hk_lookup.html fetches client-side. Instant search, no keys, no
rate limits. site/hkstockdata/ is gitignored — regenerated nightly.

Each record carries a `tv` field = the TradingView HKEX: symbol so the search
page can embed an HK chart (e.g. 0700.HK -> HKEX:700).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import i18n  # noqa: E402
from engine.cycles import analyze  # noqa: E402
from engine.technicals import season_line, seasonality, snapshot  # noqa: E402
from lib import config, store  # noqa: E402
from scripts.build_hk import tv_symbol  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("hk_library")


def compute_hk_global_betas() -> dict | None:
    """Per-stock global-risk beta cross-section — the honest per-name HK read (HK has
    no residual-alpha edge; engine/hk_global_beta.py). Beta of each constituent to the
    S&P 500 (overnight, US->HK transmission), conditioned on the live global risk_state.
    Best-effort: every failure path degrades to None, never raises."""
    from engine import hk_global, hk_global_beta
    dd = config.data_dir()
    cache = dd / "hk_breadth" / "_closes_cache.parquet"
    cons = dd / "hk_breadth" / "constituents.parquet"
    if not (cache.exists() and cons.exists()):
        log.warning("hk global-beta: breadth cache missing — skipped")
        return None
    try:
        closes = pd.read_parquet(cache).sort_index()
        closes = closes.loc[:, ~closes.columns.duplicated()]
        meta = pd.read_parquet(cons)
    except Exception as e:  # noqa: BLE001 — corrupt committed parquet must not break the build
        log.warning("hk global-beta: cache unreadable (%s) — skipped", e)
        return None
    names_cfg = config.load()["hk"].get("names", {})
    tkr_name = {t: (str(meta.loc[t, "name"]) if str(meta.loc[t, "name"]) != t
                    else names_cfg.get(t, t)) for t in meta.index}
    tkr_sector = meta["sector"].to_dict()
    spy = store.read("yahoo", "SPY")
    if spy is None or "close" not in spy.columns:
        log.warning("hk global-beta: no SPY factor series — skipped")
        return None
    factor = spy["close"].pct_change(fill_method=None).shift(1)   # overnight US->HK
    try:
        risk_state = hk_global.snapshot().get("state", "unknown")
    except Exception:  # noqa: BLE001
        risk_state = "unknown"
    try:
        out = hk_global_beta.compute_global_betas(closes, factor, risk_state, tkr_name, tkr_sector)
    except Exception as e:  # noqa: BLE001 — additive leg, never fatal
        log.warning("hk global-beta engine failed (%s) — skipped", e)
        return None
    if out:
        log.info("hk global-beta: %d names, risk_state=%s", out.get("n"), risk_state)
    return out


def chart_series(close: pd.Series, n: int = 504) -> dict:
    """Compact columnar close history for the client-side chart (the last ~2y of
    daily closes). TradingView's free embed gates HKEX data behind a login, so the
    HK pages draw the chart from OUR stored prices via TradingView Lightweight
    Charts (open-source) instead — same 'repo is the database' philosophy."""
    c = close.dropna().tail(n)
    return {"t": [str(d.date()) for d in c.index],
            "c": [round(float(v), 3) for v in c.values]}


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
        "chart": chart_series(c),
        **res,
    }


def universe() -> list[tuple[str, pd.Series, pd.Series | None, str, str]]:
    """(ticker, close, high|None, name, sector) for everything analyzable."""
    out: list[tuple] = []
    seen: set[str] = set()
    hk = config.load()["hk"]
    hy = hk["yahoo"]
    names = hk.get("names", {})

    # curated constituents from the breadth close cache (~3y window) + their sector
    cache = config.data_dir() / "hk_breadth" / "_closes_cache.parquet"
    cons = config.data_dir() / "hk_breadth" / "constituents.parquet"
    if cache.exists() and cons.exists():
        closes = pd.read_parquet(cache)
        meta = pd.read_parquet(cons)
        for t in closes.columns:
            if t in seen or t not in meta.index:
                continue
            nm = str(meta.loc[t, "name"])
            if nm == t:  # parquet name is just the ticker — use the config display name
                nm = names.get(t, t)
            out.append((t, closes[t], None, nm, str(meta.loc[t, "sector"])))
            seen.add(t)
    else:
        log.warning("hk breadth close cache missing — library covers indices/ETFs only")

    # HK indices + ETF proxies from the hk store (deeper history than the cache)
    labels = {**{k: (v, "Index") for k, v in hy["indices"].items()},
              **{k: (v, "ETF") for k, v in hy["etf_proxies"].items()}}
    for t, (nm, sec) in labels.items():
        if t in seen:
            continue
        df = store.read("hk", t)
        if df is None or "close" not in df.columns:
            continue
        out.append((t, df["close"], None, nm, sec))
        seen.add(t)
    return out


def compute_hk_scoreboard(betas: dict | None = None) -> dict | None:
    """Consolidate the HK per-name read into ONE toggle-ready scoreboard — the HK
    parallel of compute_china_scoreboard(). HK has no idiosyncratic stock-selection
    edge (residual momentum is dead on a 40y panel); the validated read is the
    GLOBAL-RISK beta overlay. So the three lenses are the same risk dimension sliced
    by exposure — Amplifiers (highest beta), Cushions (lowest beta), and the full
    sortable list (All) — every row enriched with the per-stock price + cycle state
    read back from hkstockdata/. Best-effort; never fatal."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    fdir, hd = site / "factordata", site / "hkstockdata"
    if betas is None:
        p = fdir / "hk_global_beta.json"
        try:
            betas = json.loads(p.read_text()) if p.exists() else None
        except Exception:  # noqa: BLE001
            betas = None
    pt = (betas or {}).get("per_ticker") or {}
    if not pt:
        return None

    rows = []
    for ticker, gb in pt.items():
        safe = ticker.replace("=", "_").replace("^", "_")
        f = hd / f"{safe}.json"
        rec = {}
        if f.exists():
            try:
                rec = json.loads(f.read_text())
            except Exception:  # noqa: BLE001
                rec = {}
        lad = rec.get("ladder", {})
        cyc = lad.get("label") or lad.get("state")
        sec = rec.get("sector")
        rows.append({
            "ticker": ticker,
            "name": rec.get("name"),
            "sector": sec,
            "sector_zh": i18n.tr(sec) if sec else None,
            "price": rec.get("tech", {}).get("price"),
            "beta": gb.get("beta"),
            "beta_pct": gb.get("beta_pct"),
            "role": gb.get("role"),
            "tilt": gb.get("tilt"),
            "cycle": cyc,
            "cycle_zh": lad.get("label_zh") or (i18n.tr(cyc) if cyc else None),
            "cycle_dir": lad.get("dir"),
        })
    if not rows:
        return None

    def b(r):  # sort key, missing beta to the bottom either way
        return r["beta"] if r["beta"] is not None else -1
    amp = sorted([r for r in rows if r["role"] == "amplifier"], key=b, reverse=True)
    cush = sorted([r for r in rows if r["role"] == "cushion"], key=b)
    allr = sorted(rows, key=b, reverse=True)
    return {"as_of": (betas or {}).get("as_of"),
            "risk_state": (betas or {}).get("risk_state"),
            "modes": {"amplifiers": amp, "cushions": cush, "all": allr}}


def main(betas: dict | None = None) -> dict | None:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    outdir = site / "hkstockdata"
    outdir.mkdir(parents=True, exist_ok=True)

    # per-stock global-risk beta leg — computed here if not passed in by build_hk
    if betas is None:
        betas = compute_hk_global_betas()
    beta_pt = (betas or {}).get("per_ticker", {})
    if betas:
        fdir = site / "factordata"
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / "hk_global_beta.json").write_text(
            json.dumps(betas, separators=(",", ":"), default=str))

    index, built, failed = [], 0, 0
    price_by: dict[str, float] = {}
    for ticker, close, high, name, sector in universe():
        try:
            rec = _one(ticker, close, high, name, sector)
        except Exception as e:  # noqa: BLE001 — one bad ticker must not kill the library
            log.debug("hk library %s failed: %s", ticker, e)
            rec = None
        if rec is None:
            failed += 1
            continue
        if beta_pt.get(ticker):             # additive: absent => no global-beta panel
            rec["global_beta"] = beta_pt[ticker]
        safe = ticker.replace("=", "_").replace("^", "_")
        (outdir / f"{safe}.json").write_text(json.dumps(rec, default=str))
        idx = {"t": ticker, "n": name, "s": sector, "st": rec["ladder"]["state"]}
        if rec.get("global_beta", {}).get("beta") is not None:
            idx["gb"] = rec["global_beta"]["beta"]
        index.append(idx)
        price_by[ticker] = rec.get("tech", {}).get("price")
        built += 1

    # descriptive FUNDAMENTALS (akshare) — context, not a signal; HK adds the
    # analyst-consensus read A-shares lack. Patched onto the per-stock JSONs.
    try:
        from engine import hk_fundamentals
        fmap = hk_fundamentals.build_all(price_by)
        for ticker, fund in fmap.items():
            safe = ticker.replace("=", "_").replace("^", "_")
            fp = outdir / f"{safe}.json"
            if not fp.exists():
                continue
            try:
                rec = json.loads(fp.read_text())
                rec["fundamentals"] = fund
                fp.write_text(json.dumps(rec, default=str))
            except Exception:  # noqa: BLE001
                continue
        if fmap:
            for idx in index:
                if idx["t"] in fmap:
                    idx["f"] = 1
            log.info("hk fundamentals: attached to %d names", len(fmap))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("hk fundamentals attach failed (%s); skipping", e)
    (outdir / "index.json").write_text(json.dumps(index))
    cal = config.data_dir() / "hk_regime" / "ladder_calibration.json"
    if cal.exists():
        (outdir / "calibration.json").write_text(cal.read_text())
    log.info("hk library: %d analyzed, %d skipped (thin history)", built, failed)
    return betas


if __name__ == "__main__":
    main()
    sys.exit(0)
