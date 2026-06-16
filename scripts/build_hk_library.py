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
from engine import stock_score  # noqa: E402
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


def current_liquidity() -> str | None:
    """The live HK DUAL-liquidity regime ("expanding"/"contracting"/"neutral") the HK
    engine last classified (hk_regime/latest.json `liquidity_overlay` — PBoC M2 +
    Fed-via-peg + southbound). Threaded into analyze() as the orthogonal macro
    conviction modifier on buy setups, mirroring the US library. None when
    unavailable so the ladder simply omits the liquidity context."""
    p = config.data_dir() / "hk_regime" / "latest.json"
    if not p.exists():
        return None
    try:
        liq = json.loads(p.read_text()).get("liquidity_overlay")
    except Exception:  # noqa: BLE001
        return None
    return liq if liq in ("expanding", "contracting", "neutral") else None


def _one(ticker: str, close: pd.Series, high: pd.Series | None,
         name: str, sector: str, liquidity: str | None = None) -> dict | None:
    c = close.dropna()
    if len(c) < 300:
        return None
    res = analyze(c, high, kind="equity", liquidity=liquidity)
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


def _spark_svg(vals: list[float], color: str = "var(--link)",
               w: int = 240, h: int = 42) -> str:
    """Tiny theme-aware inline sparkline (area + line + last-point dot) — same shape
    as the US/China standout cards, replicated locally to avoid a heavy import."""
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


def _basket_tailwind_map() -> dict[str, dict]:
    """Per-ticker thematic-basket TAILWIND for the Conviction "upside" axis — the
    strongest HK theme a name belongs to, scored by that basket's 20d return vs the
    HSI benchmark (engine.baskets_hk). Mirrors build_stock_library._basket_tailwind_map.
    Best-effort — any failure yields {} and the axis is simply absent (the engine
    never reads a missing leg as neutral)."""
    out: dict[str, dict] = {}
    try:
        from engine import baskets_hk
        data = baskets_hk.compute_hk_baskets() or {}
        for b in (data.get("baskets") or []):
            rel = ((b.get("perf") or {}).get("20d") or {}).get("rel")
            if rel is None:
                continue
            rel20 = float(rel) * 100.0          # fraction -> percent
            for m in (b.get("members") or []):
                sym = m.get("symbol")
                if not sym:
                    continue
                prev = out.get(sym)
                if prev is None or abs(rel20) > abs(prev["rel20"]):
                    out[sym] = {"name": b.get("name"), "rel20": rel20}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("hk basket tailwind map unavailable (%s)", e)
    return out


def _fund_priors_map() -> dict[str, float]:
    """Optional per-ticker fundamental-PRIORS z from the HK fundamentals cache — a
    cross-sectional z of the Piotroski F-score (fundamental health, the only
    health summary we have universe-wide). Clearly CONTEXT (HK has no validated
    selection edge); fed to the Conviction quality axis as an ex-US prior alongside
    the (absent) factor composite. Best-effort — {} when the cache is missing."""
    import statistics
    try:
        from engine import hk_fundamentals
        fmap = hk_fundamentals.build_all({}) or {}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("hk fund priors unavailable (%s)", e)
        return {}
    scores = {t: (f.get("piotroski") or {}).get("score")
              for t, f in fmap.items() if (f.get("piotroski") or {}).get("score") is not None}
    if len(scores) < 5:
        return {}
    vals = list(scores.values())
    mu = statistics.fmean(vals)
    sd = statistics.pstdev(vals) or 1.0
    return {t: (v - mu) / sd for t, v in scores.items()}


def compute_hk_standouts(scoreboard: dict | None, n_buy: int = 100, n_lag: int = 6) -> dict | None:
    """Standout HK names ranked by cross-sectional RELATIVE STRENGTH — each name's
    63-day (~3-month) return z-scored against the HK universe. HK has NO validated
    stock-picking alpha (residual momentum is dead on a 40y panel); this is a
    relative-strength / exposure READ surfaced as cards for parity with the US &
    China dashboards, NOT a backtested selection edge. Reuses the per-stock library
    JSON (price, off-52w-high, RSI, cycle, recent closes) and the global-beta
    scoreboard rows, so no new data is fetched. Returns a setups-shaped dict."""
    import statistics
    from collections import defaultdict

    rows = ((scoreboard or {}).get("modes") or {}).get("all") or []
    if not rows:
        return None
    site = config.ROOT / config.load()["storage"]["site_dir"]
    hd = site / "hkstockdata"

    enriched: list[dict] = []
    for r in rows:
        t = r.get("ticker")
        if not t:
            continue
        f = hd / f"{t.replace('=', '_').replace('^', '_')}.json"
        if not f.exists():
            continue
        try:
            rec = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        chart = (rec.get("chart") or {}).get("c") or []
        if len(chart) < 70:
            continue
        try:
            ret_63 = float(chart[-1]) / float(chart[-64]) - 1.0
        except Exception:  # noqa: BLE001
            continue
        tech = rec.get("tech") or {}
        enriched.append({
            "ticker": t,
            "name": r.get("name") or rec.get("name"),
            "sector": r.get("sector") or rec.get("sector"),
            "sector_zh": r.get("sector_zh"),
            "price": tech.get("price") if tech.get("price") is not None else r.get("price"),
            "off_high": tech.get("off_52w_high_pct"),
            "rsi": tech.get("rsi14"),
            "label": r.get("cycle"), "label_zh": r.get("cycle_zh"),
            "dir": r.get("cycle_dir") or "flat",
            "_ret63": ret_63, "_chart": chart, "_rec": rec, "_path": f,
        })
    if len(enriched) < 4:
        return None

    rets = [e["_ret63"] for e in enriched]
    mu = statistics.fmean(rets)
    sd = statistics.pstdev(rets) or 1.0
    for e in enriched:
        e["alpha"] = round((e["_ret63"] - mu) / sd, 2)        # relative-strength z
        rsi = e.get("rsi")
        if rsi is not None and rsi >= 70:
            e["alpha_entry"] = "extended"                      # stretched — reversal risk
        elif rsi is not None and rsi <= 55 and e["alpha"] > 0:
            e["alpha_entry"] = "pullback"                      # strong name, cooled off

    by_sec: dict = defaultdict(list)
    for e in enriched:
        by_sec[e.get("sector")].append(e)
    for lst in by_sec.values():
        lst.sort(key=lambda x: x["alpha"], reverse=True)
        for i, e in enumerate(lst, 1):
            e["sector_rank"], e["sector_n"] = i, len(lst)

    # ---- unified Conviction Profile (engine/stock_score), HK market ----------
    # Profile EVERY enriched name so the per-stock detail page and these standout
    # cards render the SAME block (they can never structurally disagree). HK has no
    # validated stock-selection edge, so the SELECTION axis is the relative-strength
    # z (framed as a screen) and trust_tier('HK')='screen' — the engine's verdict()
    # never says "Buy". The cycle state is a HARD verb modifier. The shipped board
    # rank STAYS the RS leg (below); the composite rides as the displayed profile.
    as_of = (scoreboard or {}).get("as_of")
    basket_tw = _basket_tailwind_map()
    fund_priors = _fund_priors_map()
    profiles: dict[str, dict] = {}
    for e in enriched:
        t = e["ticker"]
        rec = e["_rec"]
        # the standout's RS z lands in the engine's selection slot via rs_z; the
        # per-name pullback/extended tag rides on alpha_entry so the entry axis reads it.
        rec_for_norm = {**rec, "alpha": {"entry": e.get("alpha_entry")}}
        norm = stock_score.normalize_rec(
            rec_for_norm, "HK", rs_z=e["alpha"],
            fund_priors_z=fund_priors.get(t), basket=basket_tw.get(t))
        prof = stock_score.conviction_profile(norm, "HK", ctx={"as_of": as_of})
        profiles[t] = prof
        e["conviction"] = prof
    stock_score.attach_panel_scores(profiles)        # within-market percentile display score
    # patch the (now percentile-scored) conviction block back into each per-stock
    # JSON so hk_lookup.html renders the identical hero. The library wrote these
    # JSONs already; this mirrors the fundamentals / A-H premium patch pattern.
    for e in enriched:
        rec, fp = e["_rec"], e["_path"]
        rec["conviction"] = profiles.get(e["ticker"])
        try:
            fp.write_text(json.dumps(rec, default=str))
        except Exception:  # noqa: BLE001 — additive, never fatal
            continue

    buys = sorted(enriched, key=lambda x: x["alpha"], reverse=True)[:n_buy]
    laggards = sorted(enriched, key=lambda x: x["alpha"])[:n_lag]
    for e in buys:
        col = ("var(--up)" if e["dir"] == "up" else
               "var(--down)" if e["dir"] == "down" else "var(--muted)")
        e["spark_svg"] = _spark_svg(e["_chart"][-64:], color=col)
    for e in enriched:                                          # drop bulky temp fields
        e.pop("_chart", None); e.pop("_ret63", None)
        e.pop("_rec", None); e.pop("_path", None)
    out = {"as_of": as_of, "buy": buys, "laggards": laggards,
           "eligible": sum(1 for e in enriched if e["alpha"] >= 0.5),
           "universe": len(enriched)}
    # persist the artifact so a transient build failure leaves a stale-but-present
    # board (mirrors us_standouts.json — fixes the silent-vanish on a bad run).
    try:
        fdir = site / "factordata"
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / "hk_standouts.json").write_text(
            json.dumps(out, separators=(",", ":"), default=str))
        log.info("wrote hk_standouts.json (%d buy of %d eligible / %d universe)",
                 len(buys), out["eligible"], out["universe"])
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("hk_standouts.json persist skipped (%s)", e)
    return out


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

    liq = current_liquidity()
    log.info("hk dual-liquidity regime for library: %s", liq or "unknown")
    index, built, failed = [], 0, 0
    price_by: dict[str, float] = {}
    for ticker, close, high, name, sector in universe():
        try:
            rec = _one(ticker, close, high, name, sector, liquidity=liq)
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

    # A/H premium per dual-listed name — the signature HK cross-market arb context
    # (how much DEARER the mainland A-share trades vs its HK-listed H twin; a high
    # premium means the H/HK line is the cheaper way to own the same company). Pure
    # function of already-stored A + H closes (engine/hk_ah.py); attached to the ~12
    # dual-listed H tickers, absent => no panel.
    try:
        from engine import hk_ah
        ah = hk_ah.ah_by_ticker()
        for ticker, blk in ah.items():
            safe = ticker.replace("=", "_").replace("^", "_")
            fp = outdir / f"{safe}.json"
            if not fp.exists():
                continue
            try:
                rec = json.loads(fp.read_text())
                rec["ah_premium"] = blk
                fp.write_text(json.dumps(rec, default=str))
            except Exception:  # noqa: BLE001
                continue
        if ah:
            log.info("hk A/H premium: attached to %d dual-listed names", len(ah))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("hk A/H premium attach failed (%s); skipping", e)
    (outdir / "index.json").write_text(json.dumps(index))
    cal = config.data_dir() / "hk_regime" / "ladder_calibration.json"
    if cal.exists():
        (outdir / "calibration.json").write_text(cal.read_text())
    log.info("hk library: %d analyzed, %d skipped (thin history)", built, failed)
    return betas


if __name__ == "__main__":
    main()
    sys.exit(0)
