"""Build the searchable China A-share analysis library (site/chinastockdata/*.json).

China parallel of scripts/build_stock_library.py. Runs the SAME cycle/ladder
engine over the China universe (curated constituents from the breadth close
cache + sector ETFs + indices in store group 'china') and writes one small JSON
per instrument that china_lookup.html fetches client-side. Instant search, no
keys, no rate limits. site/chinastockdata/ is gitignored — regenerated nightly.

Each record carries a `tv` field = the TradingView SSE:/SZSE: symbol so the
search page can embed an A-share chart (e.g. 600519.SS -> SSE:600519).
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
from engine.residual_alpha import compute_residual_alpha  # noqa: E402
from engine.setups import CN_ALPHA_WEIGHT, rank_setups, setup_score  # noqa: E402
from engine.technicals import season_line, seasonality, snapshot  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("china_library")

CSI300_ETF = "510300.SS"   # cap-weighted A-share market proxy for the residual-alpha leg
JUNK_SECTOR = "A-share"    # yfinance fallback bucket → route to the engine's skip sentinel


# ── per-ticker analyze() fan-out (mirrors build_stock_library's process pool) ──
# The ~795-name China universe runs the GIL-bound engine.cycles.analyze per name;
# fan it across processes so the daily build doesn't pay it serially. Knobs match
# the US build: STOCK_LIB_WORKERS env (1 = force serial) > stock_search.workers >
# cpu_count, capped at 8. The pool only carries the market-wide liquidity label
# (the sole macro modifier threaded into the CN ladder); everything else stays
# serial in main() after the analyses come back, so output is order-identical.
_CN_SHARED: dict = {}


def _library_workers() -> int:
    n = os.environ.get("STOCK_LIB_WORKERS") or None
    if n is None:
        n = config.load().get("stock_search", {}).get("workers")
    if n is None:
        n = os.cpu_count() or 1
    return max(1, min(int(n), 8))


def _cn_winit(liq=None) -> None:
    _CN_SHARED["liq"] = liq


def _cn_one_task(item):
    """Worker: one ticker's library record (or None). Mirrors the inline call +
    its one-bad-ticker-can't-kill-the-library guard."""
    ticker, close, high, name, sector = item
    try:
        return _one(ticker, close, high, name, sector, liquidity=_CN_SHARED.get("liq"))
    except Exception as e:  # noqa: BLE001 — one bad ticker must not kill the library
        log.debug("china library %s failed: %s", ticker, e)
        return None


def _analyze_universe(uni, liq):
    """Run _one over the universe, in parallel when the pool is worthwhile, else
    serial. Returns recs aligned 1:1 with uni (None for skips/failures). Any pool
    error degrades to the serial path — parallelism must never break the build."""
    _cn_winit(liq)  # also primes the serial path
    workers = _library_workers()
    if workers > 1 and len(uni) > 50:
        try:
            from concurrent.futures import ProcessPoolExecutor
            t0 = time.time()
            with ProcessPoolExecutor(max_workers=workers, initializer=_cn_winit,
                                     initargs=(liq,)) as ex:
                recs = list(ex.map(_cn_one_task, uni, chunksize=8))
            log.info("china library: analysed %d names in %.0fs (%d processes)",
                     len(uni), time.time() - t0, workers)
            return recs
        except Exception as e:  # noqa: BLE001 — parallelism must never break the build
            log.warning("parallel china library build failed (%s) — serial fallback", e)
    t0 = time.time()
    recs = [_cn_one_task(item) for item in uni]
    log.info("china library: analysed %d names in %.0fs (serial)", len(uni), time.time() - t0)
    return recs


def tv_symbol(ticker: str) -> str:
    code, _, suf = ticker.partition(".")
    if suf == "SS":
        return f"SSE:{code}"
    if suf == "SZ":
        return f"SZSE:{code}"
    return ticker


def current_liquidity() -> str | None:
    """The live China net-liquidity regime ("expanding"/"contracting"/"neutral")
    the engine last classified (china_regime/latest.json `liquidity_overlay`).
    Threaded into analyze() as the orthogonal macro conviction modifier on buy
    setups — the China parallel of build_stock_library.current_liquidity(). None
    when unavailable so the ladder simply omits the liquidity context. NOTE: the CN
    regime exposes only liquidity_overlay (no macro_risk/VIX leg), so unlike the US
    build this is the only macro modifier threaded in."""
    p = config.data_dir() / "china_regime" / "latest.json"
    if not p.exists():
        return None
    try:
        liq = json.loads(p.read_text()).get("liquidity_overlay")
    except Exception:  # noqa: BLE001 — additive context, never fatal
        return None
    return liq if liq in ("expanding", "contracting", "neutral") else None


def _one(ticker: str, close: pd.Series, high: pd.Series | None,
         name: str, sector: str, liquidity: str | None = None) -> dict | None:
    c = close.dropna()
    if len(c) < 300:
        return None
    # China net-liquidity is a single market-wide regime applying to every A-share
    # name (mirrors the US build); the CN regime carries no macro_risk/VIX leg, so
    # liquidity is the only macro conviction modifier threaded into the ladder.
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
        **res,
    }


def _add_cache(out: list[tuple], seen: set[str], closes_path, meta_path, label: str) -> int:
    """Append (ticker, close, None, name, sector) from a wide closes parquet + a
    meta table (index=ticker, columns name/sector). Robust: a missing OR CORRUPT
    parquet is logged and skipped, never fatal (one bad cache must not 404 the whole
    search library in CI)."""
    if not (closes_path.exists() and meta_path.exists()):
        log.warning("%s cache missing (%s) — skipped", label, closes_path.name)
        return 0
    try:
        closes = pd.read_parquet(closes_path)
        meta = pd.read_parquet(meta_path)
    except Exception as e:  # noqa: BLE001 — corrupt restored/committed parquet
        log.warning("%s cache unreadable (%s) — skipped", label, e)
        return 0
    added = 0
    for t in closes.columns:
        if t in seen or t not in meta.index:
            continue
        out.append((t, closes[t], None, str(meta.loc[t, "name"]), str(meta.loc[t, "sector"])))
        seen.add(t)
        added += 1
    log.info("china library universe: +%d from %s", added, label)
    return added


def _overlay_deep_ohlc(out: list[tuple], group: str, min_rows: int = 300) -> int:
    """Upgrade names to the deep per-name OHLC store (data/<group>/<ticker>.parquet —
    real high/low + decades of history from collectors/china_stock_prices.py) wherever
    the nightly collector has backfilled them, replacing the ~5y close-only search/
    breadth cache series (which carry high=None). Mirrors how build_stock_library
    sources US names from data/stocks. Names not yet in the store keep their cache
    series, so this is a pure, NON-REGRESSING upgrade that fills in as the store grows
    (the seed ships ~12 names; nightly backfills the rest). See
    research/signal_engine/MULTICOUNTRY_DATA.md."""
    n = 0
    for i, (t, _close, _high, name, sector) in enumerate(out):
        df = store.read(group, t)
        if df is None or "close" not in df.columns or len(df["close"].dropna()) < min_rows:
            continue
        out[i] = (t, df["close"], df.get("high"), name, sector)
        n += 1
    if n:
        log.info("china library: upgraded %d names to the deep OHLC store (%s)", n, group)
    return n


def compute_china_alpha() -> dict | None:
    """Sector-neutral residual-momentum cross-section over the A-share top-800 panel.

    Phase 0 (research/CHINA_HK_STOCK_SIGNALS.md) validated this as a GO ranking/context
    leg: same engine as the US (engine/residual_alpha.py), pointed at
    data/china_search/ with the CSI300 ETF as the market. Returns the JSON-able dict
    (top / by_sector / per_ticker) with company names enriched, or None if data is
    missing. Best-effort: every failure path degrades to None, never raises."""
    dd = config.data_dir()
    cp = dd / "china_search" / "closes.parquet"
    mp = dd / "china_search" / "members.parquet"
    if not (cp.exists() and mp.exists()):
        log.warning("china alpha: search panel missing — skipped")
        return None
    try:
        closes = pd.read_parquet(cp).sort_index()
        closes = closes.loc[:, ~closes.columns.duplicated()]
        members = pd.read_parquet(mp)
    except Exception as e:  # noqa: BLE001 — corrupt committed parquet must not break the build
        log.warning("china alpha: panel unreadable (%s) — skipped", e)
        return None
    # ticker→sector, routing the yfinance 'A-share' fallback bucket to the engine's
    # skip sentinel '—' so those ~10 unclassified names don't pollute the cross-section
    tkr_sector = {t: (s if s != JUNK_SECTOR else "—") for t, s in members["sector"].items()}
    names = {t: str(n) for t, n in members["name"].items()}
    mdf = store.read("china", CSI300_ETF)
    if mdf is None or "close" not in mdf.columns:
        log.warning("china alpha: no CSI300 (%s) market series — skipped", CSI300_ETF)
        return None
    market = mdf["close"].pct_change(fill_method=None)
    try:
        alpha = compute_residual_alpha(closes, market, tkr_sector)
    except Exception as e:  # noqa: BLE001 — additive leg, never fatal
        log.warning("china alpha engine failed (%s) — skipped", e)
        return None
    if not alpha:
        return None
    # the engine names default to the ticker when tkr_sector is injected — restore the
    # real EN/中文 company names from members for the leaders/laggards display records
    def _fix(recs):
        for r in recs or []:
            r["name"] = names.get(r.get("ticker"), r.get("name"))
    _fix(alpha.get("top"))
    for sec in (alpha.get("by_sector") or {}).values():
        _fix(sec.get("leaders"))
        _fix(sec.get("laggards"))
    alpha["market"] = "CSI 300"
    log.info("china alpha: %d names, %d sectors", alpha.get("n"), len(alpha.get("by_sector", {})))
    return alpha


def compute_china_reversal() -> dict | None:
    """The "Mean-reversion watch" — the VALIDATED A-share stock signal (3-month
    within-sector deepest dips, screened for ST/delisting + a market-cap floor).
    engine/china_reversal.py; reports/china-reversal-phase0.md. Best-effort: every
    failure path degrades to None, never raises."""
    from engine.china_reversal import reversal_watch
    dd = config.data_dir()
    cp = dd / "china_search" / "closes.parquet"
    mp = dd / "china_search" / "members.parquet"
    if not (cp.exists() and mp.exists()):
        log.warning("china reversal: search panel missing — skipped")
        return None
    try:
        closes = pd.read_parquet(cp).sort_index()
        closes = closes.loc[:, ~closes.columns.duplicated()]
        members = pd.read_parquet(mp)
    except Exception as e:  # noqa: BLE001 — corrupt committed parquet must not break the build
        log.warning("china reversal: panel unreadable (%s) — skipped", e)
        return None
    tkr_sector = {t: (s if s != JUNK_SECTOR else "—") for t, s in members["sector"].items()}
    tkr_name = {t: str(n) for t, n in members["name"].items()}
    tkr_name_zh = ({t: str(z) for t, z in members["name_zh"].items()}
                   if "name_zh" in members.columns else {})
    tkr_mktcap = ({t: float(v) for t, v in members["mktcap_yi"].items()}
                  if "mktcap_yi" in members.columns else {})
    try:
        out = reversal_watch(closes, tkr_sector, tkr_name, tkr_name_zh=tkr_name_zh,
                             tkr_mktcap=tkr_mktcap)
    except Exception as e:  # noqa: BLE001 — additive leg, never fatal
        log.warning("china reversal engine failed (%s) — skipped", e)
        return None
    if out:
        log.info("china reversal watch: %d names, %d on watch (screened %s)",
                 out.get("n"), len(out.get("watch", [])), out.get("screened"))
    return out


def compute_china_lowvol() -> dict | None:
    """The "Defensive (low-vol)" sleeve — the validated A-share defensive tilt (lowest
    trailing annualized volatility, screened for ST/delisting + a market-cap + vol floor).
    engine/china_lowvol.py; reports/china-lowvol-phase0.md. Best-effort: every failure
    path degrades to None, never raises."""
    from engine.china_lowvol import lowvol_sleeve
    dd = config.data_dir()
    cp = dd / "china_search" / "closes.parquet"
    mp = dd / "china_search" / "members.parquet"
    if not (cp.exists() and mp.exists()):
        log.warning("china lowvol: search panel missing — skipped")
        return None
    try:
        closes = pd.read_parquet(cp).sort_index()
        closes = closes.loc[:, ~closes.columns.duplicated()]
        members = pd.read_parquet(mp)
    except Exception as e:  # noqa: BLE001 — corrupt committed parquet must not break the build
        log.warning("china lowvol: panel unreadable (%s) — skipped", e)
        return None
    tkr_sector = {t: (s if s != JUNK_SECTOR else "—") for t, s in members["sector"].items()}
    tkr_name = {t: str(n) for t, n in members["name"].items()}
    tkr_name_zh = ({t: str(z) for t, z in members["name_zh"].items()}
                   if "name_zh" in members.columns else {})
    tkr_mktcap = ({t: float(v) for t, v in members["mktcap_yi"].items()}
                  if "mktcap_yi" in members.columns else {})
    try:
        out = lowvol_sleeve(closes, tkr_sector, tkr_name, tkr_name_zh=tkr_name_zh,
                            tkr_mktcap=tkr_mktcap)
    except Exception as e:  # noqa: BLE001 — additive leg, never fatal
        log.warning("china lowvol engine failed (%s) — skipped", e)
        return None
    if out:
        log.info("china lowvol: %d names, %d in sleeve (screened %s)",
                 out.get("n"), len(out.get("sleeve", [])), out.get("screened"))
    return out


def compute_china_scoreboard() -> dict | None:
    """Merge the per-stock screener JSONs (reversal / low-vol / alpha / setups, already
    written to site/factordata/) into ONE toggle-ready scoreboard — the consolidation of
    the scattered single-signal boards into a single switchable table. Each row is
    enriched with the per-stock price + cycle state (read only for the ~union of listed
    names, not all 800). Adds a CONFLUENCE mode = names appearing in BOTH the reversal and
    low-vol screens (beaten-down AND defensive — 'safer rebound'; legs validated, the
    intersection itself is honest context, not a backtested composite). Best-effort."""
    site = config.ROOT / config.load()["storage"]["site_dir"]
    fdir, cd = site / "factordata", site / "chinastockdata"

    def load(f):
        p = fdir / f
        try:
            return json.loads(p.read_text()) if p.exists() else {}
        except Exception:  # noqa: BLE001
            return {}
    rev, lv = load("china_reversal.json"), load("china_lowvol.json")
    al = load("china_alpha.json")
    # the three screener boards the page currently shows, consolidated into one toggle
    # (the momentum-reweight 'setups' feeds the separate Standout card strip, not here)
    raw = {"reversal": rev.get("watch", []), "lowvol": lv.get("sleeve", []),
           "alpha": (al.get("top", []) or [])[:16]}
    if not any(raw.values()):
        return None

    # per-stock price + cycle, only for the names actually listed (small read, not 800)
    look: dict[str, dict] = {}
    for t in {r["ticker"] for rows in raw.values() for r in rows}:
        p = cd / f"{t.replace('=', '_').replace('^', '_')}.json"
        if not p.exists():
            continue
        try:
            r = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        lad = r.get("ladder", {})
        cyc = lad.get("label") or lad.get("state")
        look[t] = {"price": r.get("tech", {}).get("price"),
                   "cycle": cyc,
                   "cycle_zh": lad.get("label_zh") or (i18n.tr(cyc) if cyc else None),
                   "cycle_dir": lad.get("dir")}

    def enrich(rows):
        return [{**rec, **look.get(rec["ticker"], {})} for rec in rows]
    modes = {k: enrich(v) for k, v in raw.items()}
    return {"as_of": rev.get("as_of") or lv.get("as_of") or al.get("as_of"), "modes": modes}


def _spark_svg(vals: list[float], color: str = "var(--link)",
               w: int = 240, h: int = 42) -> str:
    """Tiny theme-aware inline sparkline (area + line + last-point dot) — the same
    shape build_site._mini_svg draws for the US standout cards, replicated here to
    avoid importing the heavy build_site module. `vals` = a clean recent close list."""
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
    China parallel of build_stock_library._basket_tailwind_map(): the strongest
    A-share theme a name belongs to, scored by that basket's 20d return vs the
    benchmark (CSI 300). Best-effort — any failure yields {} and the tailwind axis
    is simply absent (the engine never reads a missing leg as neutral)."""
    out: dict[str, dict] = {}
    try:
        from engine import baskets_china
        data = baskets_china.compute_china_baskets() or {}
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
        log.warning("china basket tailwind map unavailable (%s)", e)
    return out


def compute_china_standouts(setups: dict | None, reversal: dict | None,
                            lowvol: dict | None) -> dict | None:
    """Enrich the reversal-led `setups.buy` shortlist into US-parity 'Standout
    individual stocks' CARDS — adds the unified Conviction profile (engine/
    stock_score, persisted on each per-stock JSON by main()) + per-stock price +
    off-52w-high + a compact price sparkline, plus a CHINA-UNIQUE 'confluence' flag =
    a name that sits in BOTH the validated screens (a deep-dip reversal candidate
    that is ALSO a low-vol defensive name → a structurally 'safer rebound'; both legs
    are validated, the intersection is honest context, not a backtested composite).
    Best-effort: returns the setups dict with each buy row enriched; missing fields
    just don't render."""
    if not setups or not setups.get("buy"):
        return setups
    site = config.ROOT / config.load()["storage"]["site_dir"]
    cd = site / "chinastockdata"
    rev_tk = {r["ticker"] for r in (reversal or {}).get("watch", [])}
    lv_tk = {r["ticker"] for r in (lowvol or {}).get("sleeve", [])}

    # recent closes for the sparklines — one small read for the ~12 listed names
    closes = None
    try:
        p = config.data_dir() / "china_search" / "closes.parquet"
        if p.exists():
            closes = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        closes = None

    for r in setups["buy"]:
        t = r["ticker"]
        # price + off-52w-high + the unified Conviction profile from the per-stock
        # library record (main() persisted rec['conviction'] before this runs)
        f = cd / f"{t.replace('=', '_').replace('^', '_')}.json"
        if f.exists():
            try:
                rec = json.loads(f.read_text())
                tech = rec.get("tech", {})
                r["price"] = tech.get("price")
                r["off_high"] = tech.get("off_52w_high_pct")
                if rec.get("conviction"):
                    r["conviction"] = rec["conviction"]
            except Exception:  # noqa: BLE001
                pass
        # confluence: in the reversal watch AND the low-vol sleeve (validated both)
        r["confluence"] = (t in rev_tk) and (t in lv_tk)
        # compact sparkline coloured by cycle direction
        if closes is not None and t in closes.columns:
            s = closes[t].dropna().tail(64).tolist()
            col = ("var(--up)" if r.get("dir") == "up"
                   else "var(--down)" if r.get("dir") == "down" else "var(--muted)")
            r["spark_svg"] = _spark_svg(s, color=col)
    return setups


def universe() -> list[tuple[str, pd.Series, pd.Series | None, str, str]]:
    """(ticker, close, high|None, name, sector) for everything analyzable."""
    out: list[tuple] = []
    seen: set[str] = set()
    cy = config.load()["china"]["yahoo"]
    dd = config.data_dir()

    # broad SEARCH universe FIRST (top-N A-shares by mcap, real EN/中文 names + sectors)
    # so its names win over the breadth cache's ticker-as-name fallback.
    _add_cache(out, seen, dd / "china_search" / "closes.parquet",
               dd / "china_search" / "members.parquet", "search_universe")

    # curated constituents from the breadth close cache (~3y window) + their sector
    if not _add_cache(out, seen, dd / "china_breadth" / "_closes_cache.parquet",
                      dd / "china_breadth" / "constituents.parquet", "breadth") and not out:
        log.warning("no china stock caches available — library covers ETFs/indices only")

    # sector ETFs + broad indices from the china store (deeper history than the cache)
    labels = {**{k: (v[0], "Sector ETF") for k, v in cy["sector_etfs"].items()},
              **{k: (v, "Index") for k, v in cy["indices"].items()}}
    for t, (nm, sec) in labels.items():
        if t in seen:
            continue
        df = store.read("china", t)
        if df is None or "close" not in df.columns:
            continue
        out.append((t, df["close"], None, nm, sec))
        seen.add(t)
    _overlay_deep_ohlc(out, "china_stocks")   # prefer real-OHLC deep store where backfilled
    return out


def _setup_score(rec: dict) -> tuple[float, dict] | None:
    """Actionable 'setup' rank for an A-share name, REVERSAL-led after the
    deep-history correction (research/CHINA_HK_STOCK_SIGNALS.md /
    reports/china-residual-alpha-deep.md): on ~35y of A-share data, cross-sectional
    momentum is NOT a validated edge — short-term REVERSAL is. So the residual is
    demoted to a light QUALITY tiebreaker (CN_ALPHA_WEIGHT=0.35×) and the score
    leads with the cycle-confirmed entry + the mean-reversion overlay. The blend is
    the shared engine.setups (engine/setups.py documents the US-vs-China weight)."""
    return setup_score(rec, alpha_weight=CN_ALPHA_WEIGHT)


def main(alpha: dict | None = None) -> dict | None:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    outdir = site / "chinastockdata"
    outdir.mkdir(parents=True, exist_ok=True)

    # Refresh the additive A-share CONTEXT caches that power the US-parity per-stock panels
    # (analyst consensus / earnings-disclosure calendar / own-history valuation percentile /
    # per-name margin financing). Keyless akshare/Eastmoney drips — best-effort, idempotent
    # within a day, capped where per-name. GFW-reachable from CI only; a blocked source just
    # leaves its cache (stale or absent) and the page hides that panel. Mirrors the US
    # build_stock_library equity_profile drip — keeps the fetch out of the workflow YAML.
    import importlib
    _val_cap = int((config.load().get("china") or {}).get("valuation_per_build", 60))
    for _mod, _kw in (("collectors.china_analyst", {}),
                      ("collectors.china_earnings", {}),
                      ("collectors.china_margin_detail", {}),
                      ("collectors.china_valuation", {"max_new": _val_cap})):
        try:
            importlib.import_module(_mod).refresh(**_kw)
        except Exception as e:  # noqa: BLE001 — additive context, never fatal
            log.warning("china context drip %s skipped (%s)", _mod, e)

    # sector-neutral residual-alpha leg — computed here if not passed in by build_china
    if alpha is None:
        alpha = compute_china_alpha()
    alpha_pt = (alpha or {}).get("per_ticker", {})
    if alpha:
        fdir = site / "factordata"
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / "china_alpha.json").write_text(
            json.dumps(alpha, separators=(",", ":"), default=str))

    # market caps (亿) for the fundamentals valuation pass — best-effort
    mktcap_by: dict[str, float] = {}
    try:
        mp = config.data_dir() / "china_search" / "members.parquet"
        if mp.exists():
            mdf = pd.read_parquet(mp)
            if mdf.index.name == "ticker" and "ticker" not in mdf.columns:
                mdf = mdf.reset_index()
            tcol = "ticker" if "ticker" in mdf.columns else mdf.columns[0]
            if "mktcap_yi" in mdf.columns:
                mktcap_by = {str(r[tcol]): float(r["mktcap_yi"])
                             for _, r in mdf.iterrows() if pd.notna(r.get("mktcap_yi"))}
    except Exception as e:  # noqa: BLE001
        log.debug("china mktcap load failed: %s", e)

    # live China net-liquidity regime — the single macro conviction modifier on the
    # ladder (CN has no macro_risk/VIX leg, unlike the US build)
    liq = current_liquidity()
    log.info("net-liquidity regime for china library: %s", liq or "unknown")

    # cross-sectional legs the unified Conviction Profile joins per name (engine/
    # stock_score): the VALIDATED A-share reversal z (the selection leg for CN) + the
    # strongest-theme basket tailwind. Both best-effort — a missing leg stays absent,
    # never read as neutral.
    rev_z_by: dict[str, float] = {}
    try:
        _rev = compute_china_reversal() or {}
        for _r in _rev.get("watch", []):
            if _r.get("ticker") and _r.get("rev_z") is not None:
                rev_z_by[_r["ticker"]] = _r["rev_z"]
    except Exception as e:  # noqa: BLE001 — additive leg, never fatal
        log.warning("china reversal-z map unavailable (%s)", e)
    basket_tw = _basket_tailwind_map()          # Conviction "upside / theme tailwind" axis

    index, cand, built, failed = [], [], 0, 0
    price_by: dict[str, float] = {}
    sector_by: dict[str, str] = {}
    # unified Conviction profiles per name + the DEFERRED per-stock JSON writes —
    # deferred (mirrors build_stock_library) so the display score can be the WITHIN-
    # MARKET percentile of the composite z (set once all names are profiled), not a
    # per-name logistic skin. disp_map carries the standout-card display fields.
    profiles: dict[str, dict] = {}
    disp_map: dict[str, dict] = {}
    to_write: list[tuple[str, dict]] = []
    # VALIDATED confluence buy gate (engine/signal_gate over engine/signal_quality): the
    # per-name {ticker: verdict} that becomes the PRIMARY buy-entry gate for the standout
    # board, REPLACING the unvalidated alpha-only floor (CHARTER §4/§7, GRID_GATE.md). Each
    # candidate also gets its §7 site/signals/<T>.json so china_lookup's chart shows the
    # SAME markers the board gated on. signal_quality is CLOSE-ONLY (it stochs the RSI of
    # close) so the close series is all it needs; thin names degrade to "insufficient
    # history" (excluded, never a crash).
    sig_verdict: dict[str, dict] = {}
    signals_dir = site / "signals"
    uni = universe()
    recs = _analyze_universe(uni, liq)      # parallel analyze() fan-out (order-preserving)
    for (ticker, close, high, name, sector), rec in zip(uni, recs):
        if rec is None:
            failed += 1
            continue
        if alpha_pt.get(ticker):            # additive: absent => no alpha panel for this name
            rec["alpha"] = alpha_pt[ticker]
            sc = _setup_score(rec)
            if sc:
                cand.append(sc)
                # VALIDATED confluence buy gate over the SAME close series the build uses
                # (close-only; never raises) + its §7 marker file so the chart and the
                # gated grid stay consistent. Computed only for ranked candidates (the
                # names that can reach the standout board).
                _g = signal_gate.gate(ticker, close)
                sig_verdict[ticker] = _g
                signal_gate.write_signal_file(
                    signals_dir, ticker.replace("=", "_").replace("^", "_"),
                    _g.get("result"))
        # ---- unified Conviction Profile (engine/stock_score, CN market) ----------
        # The single block both the china.html standout card AND china_lookup render,
        # so the two can never structurally disagree. The CN SELECTION leg is the
        # VALIDATED reversal z (residual alpha is a light tiebreaker); the cycle state
        # is a HARD verb modifier (a downtrend caps the entry axis and forbids a Buy
        # verb). Fund priors are OMITTED — the raw Piotroski/Altman scores are not
        # unit-variance cross-sectional z's, and a missing leg is honest (never neutral).
        norm = stock_score.normalize_rec(
            rec, "CN", rev_z=rev_z_by.get(ticker), basket=basket_tw.get(ticker))
        prof = stock_score.conviction_profile(norm, "CN", ctx={"as_of": (alpha or {}).get("as_of")})
        rec["conviction"] = prof
        profiles[ticker] = prof
        _tech = rec.get("tech") or {}
        _dir = (rec.get("ladder") or {}).get("dir")
        disp_map[ticker] = {
            "price": _tech.get("price"), "off_high": _tech.get("off_52w_high_pct"),
            "spark_svg": _spark_svg(
                list(close.dropna().tail(64).values),
                color=("var(--up)" if _dir == "up" else "var(--down)" if _dir == "down" else "var(--muted)"))}
        safe = ticker.replace("=", "_").replace("^", "_")
        to_write.append((safe, rec))            # deferred: write after percentile scoring
        idx = {"t": ticker, "n": name, "s": sector, "st": rec["ladder"]["state"]}
        if rec.get("alpha", {}).get("alpha") is not None:
            idx["a"] = rec["alpha"]["alpha"]          # alpha-z in the index for client ranking
        index.append(idx)
        price_by[ticker] = rec.get("tech", {}).get("price")
        sector_by[ticker] = sector
        built += 1
    # within-market percentile display score (mutates the conviction blocks in place;
    # rec['conviction'] is the SAME object, so the deferred per-stock JSONs below pick
    # it up — and the fundamentals re-read pass that follows preserves it).
    stock_score.attach_panel_scores(profiles)
    for safe, rec in to_write:
        (outdir / f"{safe}.json").write_text(json.dumps(rec, default=str))

    # descriptive FUNDAMENTALS + additive CONTEXT panels (analyst consensus / earnings
    # calendar / own-history valuation percentile / margin-financing positioning) — all
    # keyless akshare context, NOT signals. Each is computed for the cohort, then patched
    # onto the per-stock JSONs in ONE re-read pass. Every block degrades independently: a
    # missing cache just yields {} and the page hides that panel.
    fmap: dict[str, dict] = {}
    try:
        from engine import china_fundamentals
        fmap = china_fundamentals.build_all(price_by, sector_by, mktcap_by)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china fundamentals build failed (%s)", e)
    cons = earn = vpct = marg = {}
    try:
        from engine import china_extras
        cons = china_extras.analyst_consensus(price_by)
        earn = china_extras.earnings_calendar()
        vpct = china_extras.valuation_percentile()
        marg = china_extras.margin_positioning(mktcap_by)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china extras unavailable (%s)", e)
    for ticker in price_by:                       # every analyzed name has a JSON on disk
        patch: dict = {}
        if fmap.get(ticker):
            patch["fundamentals"] = fmap[ticker]
        if cons.get(ticker):
            patch["consensus"] = cons[ticker]
        if earn.get(ticker):
            patch["earnings"] = earn[ticker]
        if vpct.get(ticker):
            patch["val_pctile"] = vpct[ticker]
        if marg.get(ticker):
            patch["positioning"] = marg[ticker]
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
    for idx in index:                             # keep the existing fundamentals index flag
        if idx["t"] in fset:
            idx["f"] = 1
    log.info("china context attached: fund %d · consensus %d · earnings %d · val_pct %d · margin %d",
             len(fmap), len(cons), len(earn), len(vpct), len(marg))
    (outdir / "index.json").write_text(json.dumps(index))
    # Bespoke chart OHLC (close-only area series) read by china_lookup.html's chart.js —
    # pure serialisation of china_search closes; never break the library over the garnish.
    try:
        from scripts.build_chart_data import emit_close_only
        nc = emit_close_only(outdir / "index.json", config.data_dir() / "china_search" / "closes.parquet",
                             outdir.parent / "chinaohlc", "china")
        log.info("china chart data: %d ohlc files", nc)
    except Exception as e:  # noqa: BLE001
        log.warning("china chart data step failed (%s)", e)
    cal = config.data_dir() / "china_regime" / "ladder_calibration.json"
    if cal.exists():
        (outdir / "calibration.json").write_text(cal.read_text())

    # cross-sectional "Top setups" — selection (alpha) × timing (cycle), surfaced on
    # china.html. Buys = strong alpha with constructive timing; laggards = weak alpha.
    setups = None
    if cand:
        # n_buy generous so the standout strip's "show more" can reveal the full
        # ranked shortlist (the card grid shows 12, reveals the rest on demand). The
        # SHIPPED rank stays CN's VALIDATED leg (rank_by='setup', the reversal-led
        # construction); the Conviction composite rides as the displayed profile.
        setups = rank_setups(cand, as_of=(alpha or {}).get("as_of"), n_buy=110,
                             gate=sig_verdict)
        (site / "factordata" / "china_setups.json").write_text(
            json.dumps(setups, separators=(",", ":"), default=str))
        # WIDE "Standout individual stocks" board (the China parallel of
        # us_standouts.json). Ranked by the VALIDATED reversal-led setup leg; each row
        # carries the unified Conviction profile + price/off-high/sparkline so a
        # transient build failure leaves a stale-but-present artifact (the page falls
        # back to china_setups otherwise). eligible = names clearing the +0.5 alpha
        # quality floor; universe = the scored candidate count.
        wide = rank_setups(cand, as_of=(alpha or {}).get("as_of"), n_buy=110, n_lag=12,
                           gate=sig_verdict)
        for r in wide["buy"] + wide["laggards"]:
            t = r.get("ticker")
            r["conviction"] = profiles.get(t)
            r.update({k: v for k, v in (disp_map.get(t) or {}).items() if v is not None})
        # eligible/universe now come from the confluence gate's coverage (the alpha-only
        # +0.5 floor it replaced is no longer the buy gate); keep the keys for the page.
        _cov = wide.get("coverage") or {}
        wide["eligible"] = _cov.get("eligible", len(wide["buy"]))
        wide["universe"] = len(cand)
        (site / "factordata" / "china_standouts.json").write_text(
            json.dumps(wide, separators=(",", ":"), default=str))
        log.info("wrote china_standouts.json (%d buy [%d take · %d anticip] · gate_applied=%s · "
                 "%d eligible / %d scored / %d universe)",
                 len(wide["buy"]), _cov.get("take", 0), _cov.get("anticipation", 0),
                 wide.get("gate_applied"), _cov.get("eligible", 0),
                 _cov.get("scored", len(cand)), len(cand))
    log.info("china library: %d analyzed, %d skipped (thin history), %d setups",
             built, failed, len(cand))
    return setups


if __name__ == "__main__":
    main()
    sys.exit(0)
