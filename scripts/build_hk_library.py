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
import os
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import i18n  # noqa: E402
from engine import signal_gate  # noqa: E402  — validated confluence buy gate (CHARTER §7)
from engine import stock_score  # noqa: E402
from engine.cycles import analyze  # noqa: E402
from engine.technicals import season_line, seasonality, snapshot  # noqa: E402
from lib import config, store  # noqa: E402
from scripts.build_hk import tv_symbol  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("hk_library")


# ── per-ticker analyze() fan-out (mirrors build_stock_library's process pool) ──
# The HK universe runs the GIL-bound engine.cycles.analyze per name; fan it across
# processes (knobs match the US/CN builds: STOCK_LIB_WORKERS env > stock_search.
# workers > cpu_count, capped 8). The pool carries only the market-wide liquidity
# label; per-name post-processing stays serial in main(), so output is order-identical.
_HK_SHARED: dict = {}


def _library_workers() -> int:
    n = os.environ.get("STOCK_LIB_WORKERS") or None
    if n is None:
        n = config.load().get("stock_search", {}).get("workers")
    if n is None:
        n = os.cpu_count() or 1
    return max(1, min(int(n), 8))


def _hk_winit(liq=None) -> None:
    _HK_SHARED["liq"] = liq


def _hk_one_task(item):
    ticker, close, high, name, sector = item
    try:
        return _one(ticker, close, high, name, sector, liquidity=_HK_SHARED.get("liq"))
    except Exception as e:  # noqa: BLE001 — one bad ticker must not kill the library
        log.debug("hk library %s failed: %s", ticker, e)
        return None


def _analyze_universe(uni, liq):
    """Run _one over the universe, parallel when worthwhile else serial; recs align
    1:1 with uni. Any pool error degrades to serial — parallelism never breaks the build."""
    _hk_winit(liq)  # also primes the serial path
    workers = _library_workers()
    if workers > 1 and len(uni) > 50:
        try:
            from concurrent.futures import ProcessPoolExecutor
            t0 = time.time()
            with ProcessPoolExecutor(max_workers=workers, initializer=_hk_winit,
                                     initargs=(liq,)) as ex:
                recs = list(ex.map(_hk_one_task, uni, chunksize=8))
            log.info("hk library: analysed %d names in %.0fs (%d processes)",
                     len(uni), time.time() - t0, workers)
            return recs
        except Exception as e:  # noqa: BLE001 — parallelism must never break the build
            log.warning("parallel hk library build failed (%s) — serial fallback", e)
    t0 = time.time()
    recs = [_hk_one_task(item) for item in uni]
    log.info("hk library: analysed %d names in %.0fs (serial)", len(uni), time.time() - t0)
    return recs


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


# ── HK-native signal feeds (the unique conviction system) ────────────────────
def _closes_matrix() -> pd.DataFrame | None:
    """The curated-constituent daily close matrix (date × ticker) the per-name legs run
    on — the same breadth cache the universe + global-beta engine use."""
    cache = config.data_dir() / "hk_breadth" / "_closes_cache.parquet"
    if not cache.exists():
        return None
    try:
        df = pd.read_parquet(cache).sort_index()
        return df.loc[:, ~df.columns.duplicated()]
    except Exception:  # noqa: BLE001
        return None


def _factor_ret() -> pd.Series | None:
    """The global-risk return factor (S&P 500, lagged one day for the overnight US->HK
    transmission) — the same factor the per-name global betas are measured against, so the
    beta-neutral residual is internally consistent."""
    spy = store.read("yahoo", "SPY")
    if spy is None or "close" not in spy.columns:
        return None
    return spy["close"].pct_change(fill_method=None).shift(1)


def _vhsi_pctile() -> float | None:
    """VHSI (HK implied-vol 'fear') percentile vs its own history — feeds the conviction
    risk overlay / calm. Best-effort: None when the series is missing."""
    try:
        v = store.read("hk", "_HSIL")
        if v is None or "close" not in v.columns:
            return None
        s = v["close"].dropna()
        if len(s) < 60:
            return None
        return round(float((s <= s.iloc[-1]).mean() * 100), 0)
    except Exception:  # noqa: BLE001
        return None


def _drawdown_band() -> str | None:
    """The HK drawdown-risk band (uncalibrated context) from the regime snapshot — escalates
    the conviction macro stress when HK is fragile."""
    p = config.data_dir() / "hk_regime" / "latest.json"
    if not p.exists():
        return None
    try:
        co = (json.loads(p.read_text()).get("conditions") or {}).get("drawdown_risk") or {}
        return co.get("band")
    except Exception:  # noqa: BLE001
        return None


def _consensus_z_map(records: dict[str, dict]) -> dict[str, float]:
    """Cross-sectional z of sell-side analyst UPSIDE (median target vs price) — the HK-unique
    quality leg A-shares lack (engine/hk_fundamentals already attaches the consensus block).
    Context only; fed to the conviction quality axis. {} when too few names carry coverage."""
    import statistics
    ups = {t: ((rec.get("fundamentals") or {}).get("consensus") or {}).get("upside_pct")
           for t, rec in records.items()}
    ups = {t: float(v) for t, v in ups.items() if v is not None}
    if len(ups) < 6:
        return {}
    vals = list(ups.values())
    mu = statistics.fmean(vals)
    sd = statistics.pstdev(vals) or 1.0
    return {t: float(max(-3.0, min(3.0, (v - mu) / sd))) for t, v in ups.items()}


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

    # HK-native enrichment legs — turns the one-number beta board into a real desk: the
    # mainland southbound smart-money flow per name + the A/H value dislocation. Cheap
    # (reads the cached snapshot / stored A+H closes); each degrades to absent.
    sb_sig: dict = {}
    ah_val: dict = {}
    try:
        from engine import hk_ah, hk_southbound_stocks, hk_stock_signals
        # z-score southbound over the SAME canonical universe the conviction edge uses (the
        # full analyzable close matrix, not just the beta'd subset), so a name's sb_z on the
        # board matches its sb_z inside the conviction edge. Falls back to the beta universe.
        cm = _closes_matrix()
        sb_universe = list(cm.columns) if cm is not None else list(pt.keys())
        sb_sig = hk_southbound_stocks.signal(tickers=sb_universe) or {}
        ah_val = hk_stock_signals.ah_value_signal(hk_ah.ah_by_ticker()) or {}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("hk scoreboard flow/value legs unavailable (%s)", e)

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
        sb = sb_sig.get(ticker) or {}
        av = ah_val.get(ticker) or {}
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
            "sb_z": sb.get("accum_z"),            # southbound accumulation z
            "sb_own": sb.get("own_pct"),          # mainland Connect % of issued shares
            "sb_label": sb.get("label"),
            "ah_z": av.get("z"),                  # A/H value z (dual-listed only)
            "ah_prem": av.get("premium_pct"),
            "conv": None,                         # conviction score (patched by standouts)
            "edge_z": None,                       # unified HK edge z (patched by standouts)
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


def compute_hk_standouts(scoreboard: dict | None, n_buy: int = 60, n_lag: int = 6) -> dict | None:
    """The HK Stock Desk — names ranked by a UNIFIED, regime-conditioned conviction that
    fuses HK's three honest structural edges (engine/hk_stock_signals): southbound
    smart-money FLOW, A/H VALUE dislocation, and BETA-NEUTRAL relative strength — NOT the
    dead residual-momentum / raw-RS sort the old board used (which just re-discovered
    global-risk beta and crowned an outlier). The live ``risk_state`` re-weights the blend
    (Risk-off → flow + value + cushions; Risk-on → RS + amplifiers).

    The fused edge z feeds the engine/stock_score selection axis; the entry brakes
    (parabolic / over-200dma / lottery) and the macro risk overlay are armed so the size /
    verb are meaningful. HK still has NO selection alpha, so trust_tier='HK'/'screen' and
    the verdict never says "Buy". Board is ranked by the gated conviction composite and
    split buy / watch (strong-but-blocked) / laggards. Returns a setups-shaped dict."""
    from collections import defaultdict
    from engine import extension as ext_eng
    from engine import hk_ah, hk_southbound_stocks, hk_stock_signals

    rows = ((scoreboard or {}).get("modes") or {}).get("all") or []
    if not rows:
        return None
    site = config.ROOT / config.load()["storage"]["site_dir"]
    hd = site / "hkstockdata"
    risk_state = (scoreboard or {}).get("risk_state") or "neutral"

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
            "beta": r.get("beta"), "role": r.get("role"), "tilt": r.get("tilt"),
            "_ret63": ret_63, "_chart": chart, "_rec": rec, "_path": f, "_row": r,
        })
    if len(enriched) < 4:
        return None

    # raw relative-strength z is kept as a DESCRIPTIVE chip (not the rank) so the card can
    # still show "how it ranks on 3m return" beside the honest beta-neutral leg.
    import statistics
    rets = [e["_ret63"] for e in enriched]
    mu = statistics.fmean(rets)
    sd = statistics.pstdev(rets) or 1.0
    for e in enriched:
        e["alpha"] = round((e["_ret63"] - mu) / sd, 2)
        rsi = e.get("rsi")
        if rsi is not None and rsi >= 70:
            e["alpha_entry"] = "extended"
        elif rsi is not None and rsi <= 55 and e["alpha"] > 0:
            e["alpha_entry"] = "pullback"
    by_sec: dict = defaultdict(list)
    for e in enriched:
        by_sec[e.get("sector")].append(e)
    for lst in by_sec.values():
        lst.sort(key=lambda x: x["alpha"], reverse=True)
        for i, e in enumerate(lst, 1):
            e["sector_rank"], e["sector_n"] = i, len(lst)

    # ---- HK-native conviction legs (the unique system) -----------------------
    tickers = [e["ticker"] for e in enriched]
    closes = _closes_matrix()
    factor = _factor_ret()
    betas_pt = {r["ticker"]: {"role": r.get("role"), "tilt": r.get("tilt"), "beta": r.get("beta")}
                for r in rows}
    betas = {t: v["beta"] for t, v in betas_pt.items() if v.get("beta") is not None}
    southbound = hk_southbound_stocks.signal(tickers=list(closes.columns)) if closes is not None else {}
    ah_value = hk_stock_signals.ah_value_signal(hk_ah.ah_by_ticker())
    bnrs = (hk_stock_signals.beta_neutral_rs(closes, factor, betas)
            if (closes is not None and factor is not None) else {})
    ext_map = ext_eng.extension_signals(closes) if closes is not None else {}
    lottery = hk_stock_signals.lottery_map(closes) if closes is not None else {}
    edge = hk_stock_signals.hk_edge(tickers, southbound=southbound, ah_value=ah_value,
                                    bnrs=bnrs, betas_pt=betas_pt, risk_state=risk_state)
    vhsi_pct = _vhsi_pctile()
    overlay = hk_stock_signals.hk_risk_overlay(risk_state, vhsi_pct, _drawdown_band())
    calm = hk_stock_signals.hk_calm(risk_state, vhsi_pct)
    consensus_z = _consensus_z_map({e["ticker"]: e["_rec"] for e in enriched})

    # ---- unified Conviction Profile (engine/stock_score), HK market ----------
    as_of = (scoreboard or {}).get("as_of")
    basket_tw = _basket_tailwind_map()
    fund_priors = _fund_priors_map()
    profiles: dict[str, dict] = {}
    for e in enriched:
        t = e["ticker"]
        rec = e["_rec"]
        ed = edge.get(t) or {}
        e["edge_z"] = ed.get("z")
        e["edge_basis"] = ed.get("basis")
        e["southbound"] = southbound.get(t)
        e["ah_value"] = ah_value.get(t)
        # the FUSED HK edge lands in the selection slot (rs_z); falls back to the raw RS z
        # only when no HK-native leg resolves. The pullback/extended tag rides on alpha_entry.
        sel_z = ed.get("z") if ed.get("z") is not None else e["alpha"]
        rec_for_norm = {**rec, "alpha": {"entry": e.get("alpha_entry")}}
        norm = stock_score.normalize_rec(
            rec_for_norm, "HK", rs_z=sel_z,
            fund_priors_z=fund_priors.get(t), quality_context_z=consensus_z.get(t),
            basket=basket_tw.get(t), ext=ext_map.get(t), lottery_max=lottery.get(t))
        # the dominant positive HK-native leg names the verdict ("mainland accumulating" /
        # "cheap H vs A twin" / "relative-strength standout") — so the screen says WHY.
        pos = [b for b in (ed.get("basis") or []) if b.get("z", 0) >= 0.6]
        if pos:
            norm["hk_edge_lead"] = max(pos, key=lambda b: b["z"])["leg"]
        prof = stock_score.conviction_profile(
            norm, "HK", ctx={"as_of": as_of, "risk_overlay": overlay,
                             "regime": {"calm": calm}})
        profiles[t] = prof
        e["conviction"] = prof
    stock_score.attach_panel_scores(profiles)        # within-market percentile display score
    # patch the (now percentile-scored) conviction + HK-native legs back into each per-stock
    # JSON so hk_lookup.html renders the identical hero + flow/value chips.
    for e in enriched:
        rec, fp = e["_rec"], e["_path"]
        rec["conviction"] = profiles.get(e["ticker"])
        if e.get("southbound"):
            rec["southbound"] = e["southbound"]
        if e.get("ah_value"):
            rec["ah_value"] = e["ah_value"]
        if e.get("edge_basis"):
            rec["edge"] = {"z": e.get("edge_z"), "basis": e["edge_basis"], "regime": risk_state}
        try:
            fp.write_text(json.dumps(rec, default=str))
        except Exception:  # noqa: BLE001 — additive, never fatal
            continue
        # write the conviction score + edge z back onto the scoreboard row (so the
        # screener can sort by conviction, not just beta).
        row = e.get("_row")
        if row is not None:
            row["conv"] = profiles[e["ticker"]].get("score")
            row["edge_z"] = e.get("edge_z")

    # ---- PRIMARY BUY GATE = the VALIDATED MACD-RSI × StochRSI confluence (engine/signal_gate
    # over engine/signal_quality), REPLACING the conviction-composite-alone buy screen this
    # board used to gate on (CHARTER §4 forbids standard MACD; GRID_GATE.md). signal_quality is
    # CLOSE-ONLY, so it runs on the SAME close series the chart draws (rec.chart t/c). A name is
    # BUYABLE only if the validated signal endorses it — a buy-filter `take`, or the
    # `anticipation` eligibility exception (a just-fired `pending` buy, or the `early`
    # advance-warning). Takes ALWAYS rank ABOVE anticipations; the conviction composite then
    # orders names WITHIN each tier. We also write the §7 site/signals/<T>.json marker file from
    # the SAME analyze() result so the bespoke chart renders the SAME markers the board gated on.
    # Thin/close-only names degrade to "insufficient history" (excluded, never a crash). The
    # hard-coded HK trust_tier=screen / size-cap / never-Buy honesty constraints are untouched —
    # this gate only decides INCLUSION + ORDER, never the verb.
    sig_verdict: dict[str, dict] = {}
    signals_dir = site / "signals"
    for e in enriched:
        t = e["ticker"]
        chart = (e.get("_rec") or {}).get("chart") or {}
        ts, cs = chart.get("t") or [], chart.get("c") or []
        close = pd.Series(dtype="float64")
        if ts and cs and len(ts) == len(cs):
            try:
                close = pd.Series(cs, index=pd.to_datetime(ts), dtype="float64").dropna()
            except Exception:  # noqa: BLE001 — never fatal; degrades to "insufficient history"
                close = pd.Series(dtype="float64")
        v = signal_gate.gate(t, close)   # never raises on thin/empty data
        sig_verdict[t] = v
        safe = t.replace("=", "_").replace("^", "_")
        signal_gate.write_signal_file(signals_dir, safe, v.get("result"))

    # ---- rank by tier (gate) then the conviction composite WITHIN tier ----
    def comp(e: dict) -> float:
        c = e.get("conviction") or {}
        z = c.get("composite_z")
        return z if z is not None else -9.0

    def buyable(e: dict) -> bool:
        c = e.get("conviction") or {}
        if c.get("cycle_blocked"):
            return False
        ez = (c.get("axes") or {}).get("entry", {}).get("z")
        return ez is None or ez > -0.1

    ranked = sorted(enriched, key=comp, reverse=True)
    eligible = [e for e in ranked if (sig_verdict.get(e["ticker"]) or {}).get("eligible")]
    gate_applied = bool(eligible)
    if gate_applied:
        # owner's WEIGHTED cascade blend: tier weight scales a conviction percentile so strong
        # earlier tiers surface alongside masters, not buried below them (TIERED_CASCADE.md).
        buys = signal_gate.blend_sorted(
            eligible, base_of=comp,
            verdict_of=lambda e: sig_verdict.get(e["ticker"]))[:n_buy]
    else:   # degenerate: no name cleared the confluence gate -> graceful un-gated fallback
        log.warning("hk_standouts: 0 names cleared the confluence gate — falling back to conviction board")
        buys = [e for e in ranked if buyable(e)][:n_buy]
    buy_keys = {id(e) for e in buys}
    # attach the compact verdict to every card row so the §7 badge renders on the grid.
    for e in enriched:
        e["signal"] = signal_gate.compact(sig_verdict.get(e["ticker"]))
    # strong-but-blocked names (good edge, no live buy signal) -> a WATCH strip, not the
    # buy list — the honest "wait for a base" demotion the old board lacked.
    watch = [e for e in ranked if id(e) not in buy_keys and comp(e) > 0.2][:8]
    laggards = sorted(enriched, key=comp)[:n_lag]
    n_take = sum(1 for e in buys if (sig_verdict.get(e["ticker"]) or {}).get("tier") == signal_gate.TAKE)
    n_antic = sum(1 for e in buys if (sig_verdict.get(e["ticker"]) or {}).get("tier") == signal_gate.ANTICIPATION)

    for e in buys + watch:
        col = ("var(--up)" if e["dir"] == "up" else
               "var(--down)" if e["dir"] == "down" else "var(--muted)")
        e["spark_svg"] = _spark_svg(e["_chart"][-64:], color=col)
    # board-level fragility gauge over the top conviction cohort (display-only sizing context)
    cohort = ext_eng.cohort_stretch([ext_map[e["ticker"]] for e in ranked[:24]
                                     if e["ticker"] in ext_map])
    for e in enriched:                                          # drop bulky temp fields
        for k in ("_chart", "_ret63", "_rec", "_path", "_row"):
            e.pop(k, None)
    out = {"as_of": as_of, "risk_state": risk_state, "overlay": overlay,
           "calm": calm, "cohort": cohort or None,
           "gate_applied": gate_applied,
           "buy": buys, "watch": watch, "laggards": laggards,
           "southbound_summary": hk_southbound_stocks.market_summary(),
           # eligible = names the VALIDATED confluence endorsed (the gate's coverage), so the
           # board header reads "<buy> of <eligible> passed the entry-quality gate". coverage
           # carries scored/eligible/take/anticipation for the build log (GRID_GATE.md).
           "eligible": len(eligible) if gate_applied else 0,
           "coverage": {"scored": len(enriched), "eligible": len(eligible),
                        "take": n_take, "anticipation": n_antic},
           "universe": len(enriched)}
    # persist the artifact so a transient build failure leaves a stale-but-present board.
    try:
        fdir = site / "factordata"
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / "hk_standouts.json").write_text(
            json.dumps(out, separators=(",", ":"), default=str))
        log.info("wrote hk_standouts.json (%d buy [%d take · %d anticip] / %d watch of "
                 "%d eligible / %d universe · gate_applied=%s · %s)",
                 len(buys), n_take, n_antic, len(watch), out["eligible"],
                 out["universe"], gate_applied, risk_state)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("hk_standouts.json persist skipped (%s)", e)
    return out


def main(betas: dict | None = None) -> dict | None:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    outdir = site / "hkstockdata"
    outdir.mkdir(parents=True, exist_ok=True)

    # warm the per-stock SOUTHBOUND smart-money store (collectors/hk_southbound_holdings
    # refreshes + COMMITS it in the daily collect step; this only cold-start-fetches when
    # the store is entirely absent, e.g. local dev before any collect). The conviction legs
    # below read it; a flaky Eastmoney degrades to the last committed snapshot.
    try:
        from engine import hk_southbound_stocks
        snap = hk_southbound_stocks.latest_holdings(allow_fetch=True)
        log.info("hk southbound: %s names in store",
                 "no" if snap is None else len(snap))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("hk southbound store warm-up skipped (%s)", e)

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
    uni = universe()
    recs = _analyze_universe(uni, liq)      # parallel analyze() fan-out (order-preserving)
    for (ticker, close, high, name, sector), rec in zip(uni, recs):
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
