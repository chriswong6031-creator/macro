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
from engine import stock_score  # noqa: E402
from engine import name_score  # noqa: E402  — per-name POTENTIAL (buy-readiness) score
from engine import name_score_grader  # noqa: E402
from engine import stock_technicals  # noqa: E402  — richer close-only technical snapshot
from engine import vol_squeeze  # noqa: E402  — single-stock volatility black hole (close-only)
from engine import stock_view  # noqa: E402
from engine.cycles import analyze  # noqa: E402
from engine.setups import ALIGN_MIN_KEEP  # noqa: E402
from engine import signal_gate  # noqa: E402 — owner's confluence T1->T4 cascade (layered ON main's gate)
from engine.technicals import season_line, seasonality, snapshot  # noqa: E402
from lib import config, store  # noqa: E402
from scripts.build_hk import tv_symbol  # noqa: E402
from collectors.hk_names_zh import load_names_zh as _load_names_zh  # noqa: E402

# Loaded once at module level — a small committed JSON, no I/O on re-import.
_HK_NAMES_ZH: dict[str, str] = _load_names_zh()

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


def _safe(ticker: str) -> str:
    return ticker.replace("=", "_").replace("^", "_")


def _write_verified_index(outdir: Path, index: list[dict]) -> list[dict]:
    """Write search manifest rows only when the matching detail JSON exists."""
    verified, missing = [], []
    for row in index:
        t = row.get("t")
        if t and (outdir / f"{_safe(t)}.json").exists():
            verified.append(row)
        elif t:
            missing.append(t)
    if missing:
        log.warning("hk library: dropped %d index rows without detail JSON (%s%s)",
                    len(missing), ", ".join(missing[:8]), "..." if len(missing) > 8 else "")
    (outdir / "index.json").write_text(json.dumps(verified))
    return verified


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
    # RICH close-only technicals (engine.stock_technicals: momentum / 52w-high proximity / BBWP /
    # HVP / RSI / MA regime), superseding the thin snapshot. The single-stock volatility black hole
    # is added too — all best-effort so a thin/odd series never breaks the build.
    try:
        _tech = stock_technicals.snapshot(c)
    except Exception:  # noqa: BLE001 — fall back to the thin snapshot
        _tech = snapshot(c)
    try:
        _sq = vol_squeeze.assess(c)
    except Exception:  # noqa: BLE001
        _sq = None
    return {
        "ticker": ticker, "name": name, "sector": sector, "tv": tv_symbol(ticker),
        "asof": str(c.index.max().date()), "history_days": int(len(c)),
        "tech": _tech, "vol_squeeze": _sq,
        "season_this": season_line(seas, month),
        "season_next": season_line(seas, month % 12 + 1),
        "season_this_zh": season_line(seas, month, zh=True),
        "season_next_zh": season_line(seas, month % 12 + 1, zh=True),
        "chart": chart_series(c),
        **res,
    }


def _overlay_deep_ohlc(out: list[tuple], group: str, min_rows: int = 300) -> int:
    """Upgrade names to the deep per-name OHLC store (data/<group>/<ticker>.parquet —
    real high/low + decades of history from collectors/hk_stock_prices.py) wherever the
    nightly collector has backfilled them, replacing the ~3y close-only breadth-cache
    series (which carry high=None). Mirrors how build_stock_library sources US names
    from data/stocks. Names not yet in the store keep their cache series, so this is a
    pure, NON-REGRESSING upgrade that fills in as the store grows (the seed ships ~12
    names; nightly backfills the rest). See research/signal_engine/MULTICOUNTRY_DATA.md."""
    n = 0
    for i, (t, _close, _high, name, sector) in enumerate(out):
        df = store.read(group, t)
        if df is None or "close" not in df.columns or len(df["close"].dropna()) < min_rows:
            continue
        out[i] = (t, df["close"], df.get("high"), name, sector)
        n += 1
    if n:
        log.info("hk library: upgraded %d names to the deep OHLC store (%s)", n, group)
    return n


def universe() -> list[tuple[str, pd.Series, pd.Series | None, str, str]]:
    """(ticker, close, high|None, name, sector) for everything analyzable."""
    out: list[tuple] = []
    seen: set[str] = set()
    hk = config.load()["hk"]
    hy = hk["yahoo"]
    names = hk.get("names", {})

    # Curated constituents + their sector. Prefer the deep HK search close panel when
    # available; the breadth cache can be shallow for newly added/late-refreshed names,
    # which made valid HK tickers show up as "not in library".
    cache = config.data_dir() / "hk_breadth" / "_closes_cache.parquet"
    cons = config.data_dir() / "hk_breadth" / "constituents.parquet"
    deep = config.data_dir() / "hk_search" / "closes_deep.parquet"
    if cons.exists() and (cache.exists() or deep.exists()):
        closes = pd.read_parquet(cache) if cache.exists() else pd.DataFrame()
        deep_closes = pd.read_parquet(deep) if deep.exists() else pd.DataFrame()
        meta = pd.read_parquet(cons)
        tickers = list(dict.fromkeys([*deep_closes.columns, *closes.columns]))
        for t in tickers:
            if t in seen or t not in meta.index:
                continue
            nm = str(meta.loc[t, "name"])
            if nm == t:  # parquet name is just the ticker — use the config display name
                nm = names.get(t, t)
            series = deep_closes[t] if t in deep_closes.columns else closes[t]
            out.append((t, series, None, nm, str(meta.loc[t, "sector"])))
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
    _overlay_deep_ohlc(out, "hk_stocks")   # prefer real-OHLC deep store where backfilled
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


# Hard freshness gate (masterplan §2 principle 6 / §5.2 / audit HKCA-3): the basket
# tailwind axis is fed by the hk_search deep close panel (closes_deep.parquet); the
# CARD price comes from the hk_breadth close cache. If the basket price source is more
# than this many TRADING days staler than the card panel, the tailwind axis is a lie
# and must be SUPPRESSED with a visible reason — enforced in code, never by cadence.
FRESHNESS_MAX_STALE_TD = 3


def _entry_window(e: dict) -> dict:
    """Derive the ripe-list CARD entry window (§5.0) from the existing entry-gauge
    fields — one of 'open-now' | 'pullback LO–HI' | 'wait-for-weekly'.

    Reads e['entry_signal'] (engine.entry_signal.assess) + e['group']:
      * open-now         — status buy_now/partial (window open)
      * pullback LO–HI   — a buy_zone exists below spot; wait to buy the dip
      * wait-for-weekly  — aligned/near but no open window / awaiting confluence
    Returns {kind, en, zh, lo, hi} — lo/hi are the buy-zone bounds when present.
    """
    es = e.get("entry_signal") or {}
    st = es.get("status")
    bz = es.get("buy_zone") or {}
    lo, hi = bz.get("low"), bz.get("high")
    if st in ("buy_now", "partial"):
        return {"kind": "open-now",
                "en": "entry: open now", "zh": "入场：当前开启", "lo": lo, "hi": hi}
    if hi is not None and st in ("buy_soon", "wait_pullback", "watch"):
        _lo = lo if lo is not None else hi
        if hi != _lo:
            span = f"{_lo:.2f}–{hi:.2f}"
        else:
            span = f"{hi:.2f}"
        return {"kind": "pullback",
                "en": f"entry: pullback {span}", "zh": f"入场：回调 {span}",
                "lo": _lo, "hi": hi}
    return {"kind": "wait-for-weekly",
            "en": "entry: wait for the weekly to turn", "zh": "入场：等待周线转向",
            "lo": lo, "hi": hi}


def _card_lead(e: dict, ewin: dict) -> dict:
    """One plain-English, mechanism-FIRST sentence per card (§7.1), assembled from
    already-computed fields — active language, en + zh, ending with the entry window.

    Fields used (all pre-stamped on the enriched row): southbound accum z, A/H value
    (percentile/cheap), bottoming-alignment state, and the derived entry window. The
    lead leads with the strongest FRESH mechanism, never the composite score.
    Example: "Mainland crowd adding (SB z +1.2) · H cheap vs A · weekly basing ·
              entry: pullback 41.20–42.80."
    """
    en_parts: list[str] = []
    zh_parts: list[str] = []
    sb = e.get("southbound") or {}
    sbz = sb.get("accum_z")
    if sbz is not None and sbz >= 0.6:
        en_parts.append(f"Mainland crowd adding (SB z {sbz:+.1f})")
        zh_parts.append(f"内地资金加仓（南向 z {sbz:+.1f}）")
    elif sbz is not None and sbz <= -0.6:
        en_parts.append(f"Mainland crowd trimming (SB z {sbz:+.1f})")
        zh_parts.append(f"内地资金减仓（南向 z {sbz:+.1f}）")
    ah = e.get("ah_value") or {}
    if ah.get("cheap"):
        pp = ah.get("premium_pct")
        en_parts.append("H cheap vs A" + (f" ({pp:.0f}% disc)" if pp is not None else ""))
        zh_parts.append("H 相对 A 便宜" + (f"（折价 {pp:.0f}%）" if pp is not None else ""))
    al = (e.get("conviction") or {}).get("alignment") or {}
    if e.get("group") == "entry_open":
        en_parts.append("cycle aligned")
        zh_parts.append("周期共振")
    elif al.get("aligned") or al.get("near"):
        en_parts.append("weekly basing")
        zh_parts.append("周线筑底")
    if e.get("washout_2w"):
        en_parts.append("2W washout reclaim")
        zh_parts.append("2周超卖反抽")
    if not en_parts:                       # never emit a hollow lead
        en_parts.append("Structural screen")
        zh_parts.append("结构性筛选")
    en = " · ".join(en_parts) + " · " + ewin["en"] + "."
    zh = " · ".join(zh_parts) + " · " + ewin["zh"] + "。"
    return {"en": en, "zh": zh}


def _float_or_zero(v) -> float:
    try:
        f = float(v)
        return f if f == f else 0.0   # NaN -> 0
    except (TypeError, ValueError):
        return 0.0


def _falling_knife_demote(buys: list[dict], enriched: list[dict]) -> tuple[list[dict], list[dict], float | None]:
    """FALLING-KNIFE DEMOTE (H4 phase-0 KILL — reports/h4-phase0.md).

    H4 refuted the within-universe REVERSAL hypothesis with WRONG-SIGN power on this exact
    expanded HK universe: the deepest trailing-3M losers do NOT rebound — they KEEP FALLING
    (deepest-quintile L/S −0.92%/mo, HAC-t −2.14, DSR 0.00, split-half sign-stable; it is
    short-horizon MOMENTUM, not reversal). So a name in the DEEPEST trailing-3M-return
    quintile of the board universe must NOT sit in the ripe-list entry_open/setting_up
    groups (that would sell a falling knife as a constructive entry). This is a HYGIENE
    GATE on the §5.0 ripe-list contract — it does not re-rank survivors, it only pushes the
    deepest-quintile losers OUT of the entry groups and onto the watch strip. Screen-tier
    gate cited to H4, NOT a validated scored seam.

    ``alpha`` == the trailing-3M-return z within the board universe (built upstream from
    _ret63 over ``enriched``). The quintile threshold is the 20th percentile of ``alpha``
    over the WHOLE board universe (``enriched``) — the honest cross-section, not just the
    entry survivors. Returns (kept_buys, demoted, quintile_cut); demoted entries are tagged
    ``knife_demoted``/``knife_z`` in place. No-op (nothing demoted) when the cross-section
    is too thin (<5) for a stable quintile."""
    import statistics as _stats
    alphas = [e.get("alpha") for e in enriched if e.get("alpha") is not None]
    if len(alphas) < 5:                        # need a meaningful cross-section for a quintile
        return buys, [], None
    cut = _stats.quantiles(alphas, n=5, method="inclusive")[0]   # 20th percentile (deepest Q)
    keep: list[dict] = []
    demoted: list[dict] = []
    for e in buys:
        a = e.get("alpha")
        if a is not None and a <= cut:
            e["knife_demoted"] = True          # deepest-quintile 3M loser -> watch, not entry
            e["knife_z"] = round(float(a), 2)
            demoted.append(e)
        else:
            keep.append(e)
    return keep, demoted, cut


# Render-lane freshness gate on the H-PLC store: placings print near-daily across
# SEHK, so a store whose newest announcement is a week behind the price panel means
# the collect lane is broken — degrade loudly, never silently fail open.
PLACEMENT_STORE_MAX_STALE_D = 7


def _placement_flags(tickers: list[str], as_of) -> tuple[dict, dict | None, bool]:
    """H-PLC dilution-flag lookup + freshness gate (masterplan §3 H-PLC, W1c).

    Reads the collect-lane store via ``collectors.hk_placements.flag_map`` — a pure
    parquet read, no network in the render lane. Fail-closed lives at the COLLECTOR
    (a zero-event fetch raises there, tripwire-named); here a missing or stale store
    degrades LOUDLY: no flags plus a visible health row (§2 principle 6), never a
    silent fail-open where freshly-diluted names sail into the entry groups
    unmarked. Returns ``(flag_map, health_row | None, available)`` — ``available``
    False also nulls the board-ledger stamp (None = 'not stamped', never a fake
    False)."""
    degraded = {
        "leg": "placement_gate",
        "en": "Placement/rights dilution gate unavailable this render — flags suppressed (see logs).",
        "zh": "配售/供股摊薄风险门本次不可用 —— 标记已抑制（见日志）。",
    }
    try:
        from collectors.hk_placements import flag_map, store_status
        st = store_status()
        if not st.get("available"):
            log.warning("hk placement gate: event store missing/empty — flags suppressed")
            return {}, degraded, False
        if st.get("latest") and as_of:
            gap = int((pd.Timestamp(str(as_of)) - pd.Timestamp(str(st["latest"]))).days)
            if gap > PLACEMENT_STORE_MAX_STALE_D:
                log.warning("hk placement gate: store %dd behind panel — flags suppressed", gap)
                return {}, {
                    "leg": "placement_gate",
                    "en": (f"Placement/rights dilution gate degraded — newest stored announcement "
                           f"is {gap} days behind the price panel; flags suppressed this render."),
                    "zh": f"配售/供股摊薄风险门已降级 —— 最新公告落后价格面板 {gap} 天；本次渲染未标记。",
                }, False
        return flag_map(tickers, asof=str(as_of) if as_of else None), None, True
    except Exception as ex:  # noqa: BLE001 — degrade loudly, never break the render
        log.warning("hk placement gate unavailable (%s) — flags suppressed, health flagged", ex)
        return {}, degraded, False


def _placement_demote(buys: list[dict], enriched: list[dict],
                      plc_map: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """PLACEMENT/RIGHTS DILUTION DEMOTE (H-PLC — masterplan §3, shipped W1c).

    HK's highest-frequency idiosyncratic run-killer: a discounted top-up placement /
    rights issue prints fresh dilution and hangs a block of below-market stock over
    the name. A name with a dilutive announcement inside the trailing 90d window
    (``collectors.hk_placements.FLAG_WINDOW_D``) must NOT sit in the ripe-list
    entry_open/setting_up groups — it is pushed onto the watch strip with a
    bilingual warning chip. This is the §5.0 hygiene predicate "not
    placement-flagged [HK]" delivered as a demote (the W4 falling-knife pattern),
    NOT a scored seam: risk gates ship validation-free; the post-placement drift
    event study accrues in the experiments registry for the honest read later.

    Tags EVERY flagged row in ``enriched`` in place (``placement_flag`` /
    ``placement_info`` with bilingual category + days_ago) so knife-demoted and
    watch names also carry the stamp for the board ledger and the chip, then splits
    ``buys`` into (kept, demoted)."""
    cats = {"placing": ("placing", "配售"),
            "rights_issue": ("rights issue", "供股"),
            "open_offer": ("open offer", "公开发售")}
    for e in enriched:
        info = plc_map.get(e.get("ticker"))
        if not info:
            continue
        cat_en, cat_zh = cats.get(info.get("category"),
                                  (str(info.get("category")), str(info.get("category"))))
        e["placement_flag"] = True
        e["placement_info"] = {"cat_en": cat_en, "cat_zh": cat_zh,
                               "date": info.get("date"),
                               "days_ago": info.get("days_ago"),
                               "n_events": info.get("n_events")}
    keep = [e for e in buys if not e.get("placement_flag")]
    demoted = [e for e in buys if e.get("placement_flag")]
    return keep, demoted


def _adv63_map(tickers: list[str]) -> dict[str, float]:
    """63-day average dollar TURNOVER (close × volume) per ticker, from the deep
    hk_stocks OHLCV store — the ripe-list TIEBREAK (§5.0). HK breadth names are
    close-ONLY, so ADV is available only for names backfilled into the deep store;
    absent => 0.0 and the contract sort falls back to the conviction composite for
    that name's tiebreak. Best-effort; a bad read yields no entry."""
    out: dict[str, float] = {}
    for t in tickers:
        try:
            df = store.read("hk_stocks", t)
            if df is None or "volume" not in df.columns or "close" not in df.columns:
                continue
            dv = (pd.to_numeric(df["close"], errors="coerce")
                  * pd.to_numeric(df["volume"], errors="coerce")).dropna()
            if len(dv) >= 20:
                out[t] = float(dv.tail(63).mean())
        except Exception:  # noqa: BLE001 — additive; a missing name just tiebreaks on conviction
            continue
    return out


def _volume_map(tickers: list[str]) -> dict[str, pd.Series]:
    """Daily SHARE-volume Series per ticker from the deep hk_stocks OHLCV store — the
    input the H2a SFC days-to-cover normalization needs (shorted_shares / 63d ADV-shares).
    Distinct from ``_adv63_map`` (which is dollar TURNOVER for the ripe-list tiebreak):
    here we return the raw share-volume series so engine.hk_stock_signals.sfc_short_pressure
    can build a trailing ADV asof each weekly SFC date. Best-effort; a missing name simply
    yields no SFC chip. Close-only breadth names have no volume => absent."""
    out: dict[str, pd.Series] = {}
    for t in tickers:
        try:
            df = store.read("hk_stocks", t)
            if df is None or "volume" not in df.columns:
                continue
            v = pd.to_numeric(df["volume"], errors="coerce").dropna()
            if len(v) >= 63:
                out[t] = v
        except Exception:  # noqa: BLE001 — additive; a missing name just drops the SFC chip
            continue
    return out


def _panel_max_date(path: Path) -> pd.Timestamp | None:
    """Max index date of a wide [Date × ticker] close parquet (None if unreadable)."""
    if not path.exists():
        return None
    try:
        idx = pd.DatetimeIndex(pd.read_parquet(path, columns=[]).index)
        return idx.max() if len(idx) else None
    except Exception:  # noqa: BLE001 — best-effort; a bad read never blocks the gate
        try:
            idx = pd.DatetimeIndex(pd.read_parquet(path).index)
            return idx.max() if len(idx) else None
        except Exception:  # noqa: BLE001
            return None


def _tailwind_staleness_td() -> int | None:
    """Trading-day gap between the CARD price panel (hk_breadth/_closes_cache) and the
    BASKET tailwind price source (hk_search/closes_deep). Positive => baskets are staler.

    Counts TRADING days (bars present in the fresher card panel that fall after the
    basket source's last bar), not calendar days — so a normal weekend never trips the
    gate. Returns None when either panel is unreadable (gate then no-ops open — logged
    by the caller). Masterplan §2.6 / HKCA-3.
    """
    d = config.data_dir()
    card = _panel_max_date(d / "hk_breadth" / "_closes_cache.parquet")
    basket = _panel_max_date(d / "hk_search" / "closes_deep.parquet")
    if card is None or basket is None:
        return None
    if basket >= card:
        return 0
    try:
        card_idx = pd.DatetimeIndex(pd.read_parquet(
            d / "hk_breadth" / "_closes_cache.parquet", columns=[]).index).sort_values()
    except Exception:  # noqa: BLE001
        # calendar-day fallback if the empty-column read path is unavailable
        return int((card - basket).days)
    return int((card_idx > basket).sum())


def _basket_tailwind_map() -> dict[str, dict]:
    """Per-ticker thematic-basket TAILWIND for the Conviction "upside" axis — the
    strongest HK theme a name belongs to, scored by that basket's 20d return vs the
    HSI benchmark (engine.baskets_hk). Mirrors build_stock_library._basket_tailwind_map.
    Best-effort — any failure yields {} and the axis is simply absent (the engine
    never reads a missing leg as neutral).

    HARD FRESHNESS GATE (§2.6, HKCA-3): if the basket price source (hk_search/
    closes_deep) is >FRESHNESS_MAX_STALE_TD trading days staler than the card price
    panel (hk_breadth cache), the whole axis is SUPPRESSED ({} returned) — the caller
    surfaces a visible "basket prices N days stale" health banner. Code, not cadence.
    """
    stale_td = _tailwind_staleness_td()
    if stale_td is not None and stale_td > FRESHNESS_MAX_STALE_TD:
        log.warning("hk basket tailwind SUPPRESSED — basket prices %d trading days "
                    "staler than card panel (> %d gate)", stale_td, FRESHNESS_MAX_STALE_TD)
        return {}
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
    split buy / watch (strong-but-blocked) / laggards. Returns a setups-shaped dict.

    THE RIPE-LIST CONTRACT (masterplan §5.0 — the deterministic pre-validation board
    order; quoted verbatim). Under the C7 zero-GO branch (all Canada momentum trials
    ACCRUE, §4.1 Branch B) this is ALSO the permanent product, so the order is made
    EXACT and deterministic here, not merely emergent:

        UNIVERSE = names passing hygiene (ADV floor · not suspended · price fresh · not
                   placement-flagged [HK])
        INCLUDE  = bottoming-alignment ∈ {PRIME, ARMED} (existing gate; near-aligned
                   backfill to min 10 when thin)
        GROUP    = entry-open (confluence T1-T3 buyable ∧ in/near buy-zone) > setting-up
                   (aligned, awaiting trigger)
        RANK     = within group, edge-stack z percentile (HK: hk_edge fused z as shipped)
        TIEBREAK = 63d ADV desc
        CARD     = mechanism lead (§7.1) + entry window (open-now | pullback lo–hi |
                   wait-for-weekly) + tier badge + why-now chips

    Timing GROUPS and GATES; the edge RANKS within groups — the house truth. Every
    ranked name is stamped with group + entry_window and logged to the standout-board
    forward ledger (engine.board_ledger, §5.4) at render time.
    """
    from collections import defaultdict
    from engine import dispersion, entry_signal, extension as ext_eng, risk_sizing
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
        _price = tech.get("price") if tech.get("price") is not None else r.get("price")
        _ma200 = tech.get("ma200")
        _dist_200dma: float | None = None
        try:
            if _price and _ma200 and float(_ma200) > 0:
                _dist_200dma = round(float(_price) / float(_ma200) - 1.0, 4)
        except Exception:  # noqa: BLE001
            pass
        _tk_name_zh = _HK_NAMES_ZH.get(t)
        enriched.append({
            "ticker": t,
            "name": r.get("name") or rec.get("name"),
            "name_zh": _tk_name_zh,
            "sector": r.get("sector") or rec.get("sector"),
            "sector_zh": r.get("sector_zh"),
            "price": _price,
            "off_high": tech.get("off_52w_high_pct"),
            "rsi": tech.get("rsi14"),
            "dist_200dma": _dist_200dma,  # pre-computed so washout engine reads top-level field
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
    adv63 = _adv63_map(tickers)          # ripe-list TIEBREAK (§5.0): 63d dollar turnover
    for e in enriched:
        e["_adv63"] = adv63.get(e["ticker"])
    closes = _closes_matrix()
    factor = _factor_ret()
    # cross-sectional DISPERSION regime — the dial for WHEN selection pays, computed ONCE over
    # the whole-universe HK return panel (mirrors build_stock_library). Feeds per-name
    # vol-managed sizing (engine/risk_sizing). Strictly additive; absence => gross x1.0.
    disp_regime, regime_gross = None, 1.0
    if closes is not None:
        try:
            disp_regime = dispersion.assess(closes.pct_change(fill_method=None).tail(280))
            if disp_regime:
                regime_gross = disp_regime["gross_mult"]
                log.info("hk dispersion regime: %s (pctile %s) -> gross x%.2f",
                         disp_regime["state"], disp_regime.get("dispersion_pctile"), regime_gross)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("hk dispersion regime failed (%s)", e)
    betas_pt = {r["ticker"]: {"role": r.get("role"), "tilt": r.get("tilt"), "beta": r.get("beta")}
                for r in rows}
    betas = {t: v["beta"] for t, v in betas_pt.items() if v.get("beta") is not None}
    southbound = hk_southbound_stocks.signal(tickers=list(closes.columns)) if closes is not None else {}
    ah_value = hk_stock_signals.ah_value_signal(hk_ah.ah_by_ticker())
    bnrs = (hk_stock_signals.beta_neutral_rs(closes, factor, betas)
            if (closes is not None and factor is not None) else {})
    ext_map = ext_eng.extension_signals(closes) if closes is not None else {}
    lottery = hk_stock_signals.lottery_map(closes) if closes is not None else {}
    # ---- H2a SFC reportable short-position CONTEXT (ACCRUE-labelled — reports/h2a-phase0.md).
    # Per covered name: current days-to-cover own-history percentile. Context chip only, NEVER
    # a rank input; freshness-guarded (suppressed when the latest SFC week is >12 trading days
    # old). shorted_shares from the git-committed weekly panel; ADV-shares from hk_stocks.
    sfc_short: dict[str, dict] = {}
    _as_of_seed = (scoreboard or {}).get("as_of")
    try:
        _pos = store.read("hk_shorts", "positions")
        if _pos is not None and not _pos.empty:
            sfc_short = hk_stock_signals.sfc_short_pressure(
                _pos, _volume_map(tickers), asof=_as_of_seed)
            log.info("hk SFC short-pressure: %d covered names with a days-to-cover percentile "
                     "(H2a ACCRUE context)", len(sfc_short))
    except Exception as ex:  # noqa: BLE001 — additive context; never fatal
        log.warning("hk SFC short-pressure skipped (%s)", ex)
    # ---- H5 peg-liquidity REGIME conditioner (ACCRUE — reports/h5-peg-liquidity-phase0.md).
    # agg_balance-driven EASY/TIGHT label for the deskhero + sizing context. Display + sizing
    # only; NO rank effect. Pure function over hkma/interbank_liquidity.
    liquidity_regime = None
    try:
        from engine import hk_liquidity_regime as _hklr
        liquidity_regime = _hklr.liquidity_regime(
            store.read("hkma", "interbank_liquidity"), asof=_as_of_seed)
        if liquidity_regime:
            log.info("hk peg-liquidity regime: %s (agg_balance pctile %s; H5 ACCRUE conditioner)",
                     liquidity_regime.get("regime"), liquidity_regime.get("pctile"))
    except Exception as ex:  # noqa: BLE001 — additive conditioner; never fatal
        log.warning("hk peg-liquidity regime skipped (%s)", ex)
    # ---- CN PORTS as LOG-AND-GRADE (masterplan §5.3) — computed here, stamped on the
    # card + ledger, but NEVER allowed to affect rank yet (grades mature first, W4/W7).
    #   washout_2w: the 2W-FRI StochRSI washout-reclaim pattern ported verbatim from
    #               build_china_library (_tf_state on the 2-week resample).
    #   extended:   the extension read (ext_map grade in {stretched, parabolic}).
    washout_2w: dict[str, bool] = {}
    if closes is not None:
        from engine.cycles import _tf_state as _tf_state_2w
        for t in list(closes.columns):
            try:
                s2w = closes[t].resample("2W-FRI").last().dropna()
                washout_2w[t] = bool(_tf_state_2w(s2w).get("stoch_cross_up"))
            except Exception:  # noqa: BLE001 — additive; thin history -> no flag
                continue
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
    sig_verdict: dict[str, dict] = {}       # owner's confluence T1->T4 cascade per name (COMBINE)
    for e in enriched:
        t = e["ticker"]
        rec = e["_rec"]
        ed = edge.get(t) or {}
        e["edge_z"] = ed.get("z")
        e["edge_basis"] = ed.get("basis")
        e["southbound"] = southbound.get(t)
        e["ah_value"] = ah_value.get(t)
        e["sfc_short"] = sfc_short.get(t)      # H2a days-to-cover pctile — context chip only
        # CN ports — LOG-AND-GRADE only, never a rank input yet (§5.3).
        e["washout_2w"] = bool(washout_2w.get(t))
        _xg = (ext_map.get(t) or {}).get("grade")
        e["extended"] = _xg in ("stretched", "parabolic")
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
        # ---- the two propagated engine gauges (US-parity), HK market ----------
        # close Series for the vol / entry engines: the curated close matrix (proper
        # date-indexed Series) preferred, else the per-stock chart closes. Both are
        # pure / point-in-time; every compute is try/except so a bad name never breaks
        # the build and an absent gauge just leaves the card unchanged.
        close_s = None
        try:
            if closes is not None and t in closes.columns:
                close_s = closes[t].dropna()
            if (close_s is None or len(close_s) < 60):
                ch = (rec.get("chart") or {}).get("c") or []
                if len(ch) >= 60:
                    close_s = pd.Series([float(x) for x in ch if x is not None])
        except Exception:  # noqa: BLE001 — additive, never fatal
            close_s = None
        if close_s is not None and len(close_s) >= 60:
            # COMBINE: owner's confluence T1->T4 cascade — additive badge only; never gates inclusion.
            try:
                sig_verdict[t] = signal_gate.gate(t, close_s)
            except Exception as ex:  # noqa: BLE001 — additive, never fatal
                log.debug("hk signal-gate for %s failed (%s)", t, ex)
            # ⚖ vol-managed inverse-vol sizing — HOW MUCH to own (risk), orthogonal to the
            # conviction score (WHAT) and the entry gauge (WHEN). Pure-vol, scaled by the
            # dispersion regime. Always computable when there's enough history.
            try:
                rs = risk_sizing.assess(close_s, regime_gross=regime_gross)
                if rs:
                    e["risk_sizing"] = rs
            except Exception as ex:  # noqa: BLE001 — additive, never fatal
                log.debug("hk risk-sizing for %s failed (%s)", t, ex)
            # entry-timing gauge — when & at what price to buy (reads rec['ladder']).
            # Gate on the SAME MACD-2D x StochRSI-3D confluence as the board (mirrors the
            # US pattern in build_stock_library): a "buy now / partial" with no fresh
            # confluence cross reads "awaiting confluence", never an open entry window.
            try:
                es = entry_signal.assess(close_s, None, rec,
                                         buyable=signal_gate.is_buyable(sig_verdict.get(t)))
                if es:
                    e["entry_signal"] = es
            except Exception as ex:  # noqa: BLE001 — additive, never fatal
                log.debug("hk entry-signal for %s failed (%s)", t, ex)
    stock_score.attach_panel_scores(profiles, "HK")  # within-market percentile display score (rank-framed)
    _hkcalls = []  # POTENTIAL-score forward-grading calls, flushed after the patch loop
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
        if e.get("risk_sizing"):
            rec["risk_sizing"] = e["risk_sizing"]    # vol-managed sizing for hk_lookup
        if e.get("entry_signal"):
            rec["entry_signal"] = e["entry_signal"]  # entry-timing gauge for hk_lookup
        # ---- POTENTIAL score (engine/name_score, HK) — front-running buy-readiness -------
        # HK has no validated cross-sectional name edge (RS is a SCREEN), so edge_mult=1:
        # the score is pure cycle-trigger timing × washout — front-running, not a buy claim.
        try:
            rec.setdefault("ticker", e["ticker"])
            _hkpot = name_score.potential_score(rec, market="HK")
            _hc = rec.get("conviction") or {}
            if _hc and _hkpot:
                _hc["potential"] = _hkpot
                _hc["rank_pctile"] = _hc.get("score")
                _hc["score"] = _hkpot["score"]
                _hc["band"], _hc["band_en"], _hc["band_zh"] = _hkpot["band"], _hkpot["band_en"], _hkpot["band_zh"]
                _hn = _hc.get("notes")
                if _hn:
                    _hc["notes"] = [n for n in _hn if n.get("kind") != "rank"] or None
                _hkcalls.append({**_hkpot["call"], "level": (rec.get("tech") or {}).get("price")})
        except Exception as ex:  # noqa: BLE001 — additive, never fatal
            log.debug("hk potential score for %s failed (%s)", e.get("ticker"), ex)
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

    try:
        if _hkcalls:
            name_score_grader.append_name_calls(_hkcalls, market="HK",
                                                asof=str(pd.Timestamp.utcnow().date()))
    except Exception as ex:  # noqa: BLE001 — grading is additive, never fatal
        log.debug("hk name-score grader append failed (%s)", ex)
    # ---- B2 accrual (research/LABEL_FALTERING_PHASE0.md §2) — archive per-basket member-
    # conviction stats (potential median/IQR/n + theme score/label) so the pre-registered
    # demotion study can run once ≥180 trading days accrue. Write-only ledger, never fatal.
    try:
        from engine import conviction_accrual
        if conviction_accrual.archive_member_conviction("hk", profiles, asof=as_of):
            log.info("B2 conviction accrual: archived conviction_hk for %s", as_of)
    except Exception as ex:  # noqa: BLE001 — additive, never fatal
        log.warning("B2 conviction accrual (hk) failed (%s)", ex)

    # ---- rank by the GATED conviction composite, split buy / watch / laggards ----
    def comp(e: dict) -> float:
        c = e.get("conviction") or {}
        z = c.get("composite_z")
        return z if z is not None else -9.0

    def _entry_ok(e: dict) -> bool:
        c = e.get("conviction") or {}
        if c.get("cycle_blocked"):
            return False
        ez = (c.get("axes") or {}).get("entry", {}).get("z")
        return ez is None or ez > -0.1

    def _atier(e: dict):
        a = (e.get("conviction") or {}).get("alignment") or {}
        return "aligned" if a.get("aligned") else ("near" if a.get("near") else None)

    def _ascore(e: dict):
        a = (e.get("conviction") or {}).get("alignment") or {}
        return ((a.get("score") or 0.0), comp(e))

    ranked = sorted(enriched, key=comp, reverse=True)
    # BOTTOMING-ALIGNMENT gate (the HK parallel of the US/CN fix): a name is BUYABLE only
    # when its weekly/3-day/daily are aligned to the upside (engine.cycles.mtf_alignment) —
    # weekly not-falling + 3-day nearing a bullish cross + daily just-crossed/about-to — so a
    # mid-weekly-bear name the southbound crowd is accumulating into a fall (or a cheaper-and-
    # cheaper A/H value leg) can no longer be sold as a buy. NEAR-aligned names backfill only
    # when too few are fully aligned; aligned names rank by alignment score then conviction.
    elig = [e for e in ranked if _entry_ok(e) and _atier(e)]
    aligned = sorted([e for e in elig if _atier(e) == "aligned"], key=_ascore, reverse=True)
    near = sorted([e for e in elig if _atier(e) == "near"], key=_ascore, reverse=True)
    buys = (aligned if len(aligned) >= ALIGN_MIN_KEEP
            else aligned + near[: ALIGN_MIN_KEEP - len(aligned)])[:n_buy]
    # COMBINE re-rank: keep the aligned-above-near inclusion, order WITHIN each tier by the owner's
    # weighted cascade blend (conviction composite percentile lifted by the T1->T4 weight). Names
    # with no verdict keep their conviction rank (weight 0 = no boost). Inclusion is UNCHANGED.
    import bisect as _bisect
    _czs = sorted(comp(e) for e in buys)
    _bn = len(_czs) or 1

    def _combine_key(e):
        w = (sig_verdict.get(e["ticker"]) or {}).get("weight") or 0.0
        pct = _bisect.bisect_right(_czs, comp(e)) / _bn
        return (0 if _atier(e) == "aligned" else 1, -(pct + 0.5 * w))
    buys = sorted(buys, key=_combine_key)
    for e in buys:
        e["align_tier"] = _atier(e)
        e["signal"] = signal_gate.compact(sig_verdict.get(e["ticker"]))   # confluence T1->T4 badge

    # ---- RIPE-LIST CONTRACT (§5.0): make the board order EXACTLY the contract -------------
    # INCLUSION is already the contract's UNIVERSE→INCLUDE (hygiene via compute_hk_scoreboard's
    # tradability screen + the bottoming-alignment {aligned≈PRIME, near≈ARMED} gate above,
    # near-aligned backfilling to ALIGN_MIN_KEEP). Here we impose the contract's GROUP → RANK →
    # TIEBREAK deterministically:
    #   GROUP    entry-open (confluence T1-T3 buyable ∧ in/near buy-zone)  >  setting-up
    #   RANK     within group, by the FUSED hk_edge z percentile (edge stacks; timing gates)
    #   TIEBREAK 63d ADV desc  (proxy: the per-name 63d dollar-turnover; falls back to conviction)
    _ez_vals = sorted(e.get("edge_z") for e in buys if e.get("edge_z") is not None)
    _ezn = len(_ez_vals) or 1

    def _edge_pctile(e: dict) -> float:
        z = e.get("edge_z")
        if z is None:
            return 0.0
        return _bisect.bisect_right(_ez_vals, z) / _ezn

    def _entry_open(e: dict) -> bool:
        # confluence T1-T3 buyable (owner's cascade) AND the entry gauge is at/near an
        # open window (buy_now / partial / in-buy-zone) — the contract's GROUP-1 predicate.
        buyable = signal_gate.is_buyable(sig_verdict.get(e["ticker"]))
        es = e.get("entry_signal") or {}
        st = es.get("status")
        near_zone = bool((es.get("buy_zone") or {}).get("high") is not None
                         and st in ("buy_now", "partial", "buy_soon"))
        return bool(buyable and (st in ("buy_now", "partial") or near_zone))

    def _adv63(e: dict) -> float:
        return _float_or_zero(e.get("_adv63"))

    def _contract_key(e: dict):
        # group first (0 = entry-open, 1 = setting-up), then edge-z percentile DESC, then
        # 63d ADV DESC, then conviction composite DESC (final deterministic settle).
        return (0 if _entry_open(e) else 1,
                -_edge_pctile(e), -_adv63(e), -comp(e))

    buys = sorted(buys, key=_contract_key)

    # ---- FALLING-KNIFE DEMOTE (H4 phase-0 KILL — reports/h4-phase0.md) — pure helper -------
    # deepest trailing-3M-return quintile -> pushed OUT of the entry groups onto the watch
    # strip (they keep falling, not rebound). Screen hygiene gate, not a scored seam.
    buys, demoted_knife, _knife_cut = _falling_knife_demote(buys, enriched)
    if _knife_cut is not None:
        log.info("hk falling-knife demote (H4 KILL): demoted %d of %d entry candidates "
                 "(3M-return z <= P20 %.2f)", len(demoted_knife),
                 len(demoted_knife) + len(buys), _knife_cut)

    # ---- PLACEMENT/RIGHTS DILUTION DEMOTE (H-PLC — masterplan §3, W1c risk gate) --------
    # dilutive announcement within 90d -> pushed OUT of the entry groups onto the watch
    # strip (fresh dilution + discounted-stock overhang). Hygiene gate, not a scored seam.
    plc_map, _plc_health, _plc_ok = _placement_flags(
        [e.get("ticker") for e in enriched], as_of)
    buys, demoted_plc = _placement_demote(buys, enriched, plc_map)
    if demoted_plc:
        log.info("hk placement demote (H-PLC): demoted %d of %d entry candidates "
                 "(dilutive placement/rights announcement in window)",
                 len(demoted_plc), len(demoted_plc) + len(buys))

    for e in buys:
        e["group"] = "entry_open" if _entry_open(e) else "setting_up"
        e["entry_window"] = _entry_window(e)     # open-now | pullback lo–hi | wait-for-weekly
        e["lead"] = _card_lead(e, e["entry_window"])  # §7.1 mechanism-first sentence
    buy_keys = {id(e) for e in buys}
    # strong-but-unaligned names (good edge, weekly still falling / unconfirmed) -> a WATCH
    # strip, not the buy list — the honest "wait for the weekly to turn" demotion. The
    # falling-knife demotes (deepest-3M losers, H4 KILL) join the strip FIRST, tagged with a
    # reason chip so the watcher sees WHY they were pushed out of the entry groups.
    for e in demoted_knife:
        e["watch_reason"] = "knife"
    for e in demoted_plc:
        e["watch_reason"] = "placement"
    _demoted = demoted_knife + demoted_plc
    _demoted_ids = {id(d) for d in _demoted}
    watch = _demoted + [e for e in ranked
                        if id(e) not in buy_keys and id(e) not in _demoted_ids
                        and comp(e) > 0.2][: max(0, 8 - len(_demoted))]
    laggards = sorted(enriched, key=comp)[:n_lag]

    for e in buys + watch:
        col = ("var(--up)" if e["dir"] == "up" else
               "var(--down)" if e["dir"] == "down" else "var(--muted)")
        e["spark_svg"] = _spark_svg(e["_chart"][-64:], color=col)
    # board-level fragility gauge over the top conviction cohort (display-only sizing context)
    cohort = ext_eng.cohort_stretch([ext_map[e["ticker"]] for e in ranked[:24]
                                     if e["ticker"] in ext_map])
    # ---- HEALTH SURFACE (§5.5 / §2 principle 6) — every degraded leg this render, so the
    # page never silently fails open. Each item: {leg, en, zh}. Rendered as a banner strip.
    health: list[dict] = []
    _stale_td = _tailwind_staleness_td()
    if _stale_td is not None and _stale_td > FRESHNESS_MAX_STALE_TD:
        health.append({
            "leg": "tailwind",
            "en": f"Theme tailwind suppressed — basket prices {_stale_td} trading days stale.",
            "zh": f"主题顺风已抑制 —— 篮子价格滞后 {_stale_td} 个交易日。",
        })
    if _plc_health:                       # H-PLC store missing/stale — flags suppressed
        health.append(_plc_health)
    # southbound store staleness: the smart-money summary's as_of vs the card panel date.
    try:
        out_sb = hk_southbound_stocks.market_summary()
    except Exception:  # noqa: BLE001
        out_sb = None
    _sb_asof = (out_sb or {}).get("as_of")
    if _sb_asof and as_of:
        try:
            _gap = int((pd.Timestamp(str(as_of)) - pd.Timestamp(str(_sb_asof))).days)
            if _gap > FRESHNESS_MAX_STALE_TD:
                health.append({
                    "leg": "southbound",
                    "en": f"Southbound smart-money store stale — {_gap} days behind the price panel.",
                    "zh": f"南向资金存储陈旧 —— 落后价格面板 {_gap} 天。",
                })
        except Exception:  # noqa: BLE001
            pass

    # ---- STANDOUT-BOARD FORWARD LEDGER (§5.4) — log the ranked board + grade incrementally.
    # Fail-OPEN (never breaks the render) but never SILENT: a write failure emits a loud log
    # AND a health row. The ledger consumes the fused hk_edge z, the confluence tier, the
    # alignment tier, the entry state, and today's close — plus the CN-port stamps.
    board_track = None
    try:
        from engine import board_ledger
        calls = []
        for e in (buys + watch):
            sig = e.get("signal") or {}
            ew = e.get("entry_window") or {}
            calls.append({
                "ticker": e.get("ticker"),
                "group": e.get("group") or ("watch" if e in watch else "setting_up"),
                "edge_z": e.get("edge_z"),                       # fused hk_edge z
                "gate_tier": sig.get("tier"),                    # signal_gate compact tier
                "align_tier": e.get("align_tier"),
                "entry_state": ew.get("kind"),                   # open-now|pullback|wait-for-weekly
                "close_asof": e.get("price"),
                # CN ports stamped for maturation study (never rank inputs yet, §5.3):
                "washout_2w": bool(e.get("washout_2w")),
                "extended": bool(e.get("extended")),
                # W4 phase-0 context fields (forward-compatible; harmless if the frozen
                # ledger schema drops them — matches the 1b precedent):
                #   knife_demoted: deepest-3M-loser demote fired (H4 KILL, reports/h4-phase0.md)
                #   sfc_short_pctile: SFC days-to-cover own-history pctile (H2a ACCRUE context)
                #   liq_regime: HK peg-liquidity regime at render (H5 ACCRUE conditioner)
                "knife_demoted": bool(e.get("knife_demoted")),
                # W0.2 Stage C: the knife magnitude + the CLOSED-taxonomy near-miss
                # reason. Before Stage C these were passed but silently DROPPED by
                # the ledger's _SCHEMA reindex; the schema now persists them.
                "knife_z": e.get("knife_z"),
                "primary_rejection_reason": ("knife_demote"
                                             if e.get("knife_demoted") else None),
                "sfc_short_pctile": (e.get("sfc_short") or {}).get("pctile"),
                "liq_regime": (liquidity_regime or {}).get("regime"),
                # W1c H-PLC risk-gate stamp (persisted — board_ledger schema column).
                # None when the placement store was degraded this render: 'not
                # stamped' must stay distinct from 'checked, clean'.
                "placement_flag": (bool(e.get("placement_flag")) if _plc_ok else None),
            })
        _n = board_ledger.append_board(calls, market="HK", asof=str(as_of) if as_of else None)
        if _n:
            _bt = board_ledger.grade("HK")            # cheap incremental — maturation accrues
            if _bt.get("available"):
                board_track = _bt
            log.info("hk standout board-ledger: logged %d rows (ledger=%d, graded=%s)",
                     len(calls), _n, (_bt or {}).get("n_graded"))
        else:
            log.warning("hk standout board-ledger: append_board returned 0 (no rows written)")
            health.append({
                "leg": "board_ledger",
                "en": "Board ledger write returned no rows — the scoreboard did not accrue this render.",
                "zh": "看板账本写入 0 行 —— 本次渲染未累积记分。",
            })
    except Exception as ex:  # noqa: BLE001 — fail-OPEN, never SILENT
        log.warning("hk standout board-ledger FAILED (%s) — render continues, health flagged", ex)
        health.append({
            "leg": "board_ledger",
            "en": "Board ledger write failed this render — scoreboard did not accrue (see logs).",
            "zh": "本次渲染看板账本写入失败 —— 记分未累积（见日志）。",
        })

    for e in enriched:                                          # drop bulky temp fields
        for k in ("_chart", "_ret63", "_rec", "_path", "_row", "_adv63"):
            e.pop(k, None)
    out = {"as_of": as_of, "risk_state": risk_state, "overlay": overlay,
           "calm": calm, "cohort": cohort or None,
           "buy": buys, "watch": watch, "laggards": laggards,
           "southbound_summary": out_sb,
           "liquidity_regime": liquidity_regime,   # H5 ACCRUE conditioner — deskhero chip
           "health": health or None,
           "board_track": board_track,
           "eligible": len(aligned),
           "universe": len(enriched)}
    if disp_regime:                                  # selection-regime gross dial (board context)
        out["dispersion_regime"] = disp_regime
    # ---- WASHOUT WATCH (additive, fail-open) — ignition organ for the stock-board revamp.
    # Operates on the FULL enriched list so cycle-blocked/DECLINE names (excluded by _entry_ok)
    # are visible.  Survives eligible:0 (risk-off blackout).  The existing board dict is
    # UNCHANGED when this block errors — the try/except is the only guard needed.
    try:
        from engine import hk_washout_watch as _ww
        # Collect organ snapshots fail-open; each missing organ → that signal absent.
        _ww_organs: dict = {"southbound": southbound}   # already computed above
        try:
            from engine import hk_adr_bridge as _adr
            _ww_organs["adr_bridge"] = _adr.snapshot()
        except Exception as _ex:  # noqa: BLE001
            log.debug("hk_washout_watch wiring: adr_bridge unavailable (%s)", _ex)
        try:
            from engine import hk_cbbc as _cbbc
            _cbbc_snap = _cbbc.run()
            _ww_organs["cbbc"] = _cbbc_snap
        except Exception as _ex:  # noqa: BLE001
            log.debug("hk_washout_watch wiring: cbbc unavailable (%s)", _ex)
        try:
            from engine import hk_filing_bus as _filing
            _ww_organs["filing_bus"] = _filing.run()
        except Exception as _ex:  # noqa: BLE001
            log.debug("hk_washout_watch wiring: filing_bus unavailable (%s)", _ex)
        try:
            from engine import hk_narrative as _narrative
            _ww_organs["narrative"] = _narrative.snapshot()
        except Exception as _ex:  # noqa: BLE001
            log.debug("hk_washout_watch wiring: narrative unavailable (%s)", _ex)
        try:
            from engine import hk_catalyst_calendar as _cat
            _ww_organs["catalyst_calendar"] = {"events": _cat.catalyst_events(asof=(
                __import__("datetime").date.fromisoformat(str(as_of)) if as_of else None))}
        except Exception as _ex:  # noqa: BLE001
            log.debug("hk_washout_watch wiring: catalyst_calendar unavailable (%s)", _ex)
        _ww_result = _ww.compute(
            enriched, _ww_organs,
            risk_state=risk_state, as_of=str(as_of) if as_of else None)
        out["washout_watch"] = _ww_result.get("washout_watch", [])
        log.info("hk washout_watch: %d candidates (eligible=%d, risk_state=%s)",
                 len(out["washout_watch"]), out["eligible"], risk_state)
    except Exception as _ww_ex:  # noqa: BLE001 — ADDITIVE: existing board is untouched on error
        log.warning("hk washout_watch compute failed (%s) — existing board intact", _ww_ex)
        out["washout_watch"] = []
    # persist the artifact so a transient build failure leaves a stale-but-present board.
    try:
        fdir = site / "factordata"
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / "hk_standouts.json").write_text(
            json.dumps(out, separators=(",", ":"), default=str))
        log.info("wrote hk_standouts.json (%d buy / %d watch of %d eligible / %d universe; %s)",
                 len(buys), len(watch), out["eligible"], out["universe"], risk_state)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("hk_standouts.json persist skipped (%s)", e)

    # ---- HK PICK LAB PRODUCER BLOCK (spec §5, HKPL-R7) --------------------------------
    # Writes the nightly HK snapshot parquet and the 1D Velocity Desk price-only first
    # pass.  Never-fatal: a failure here must not block the standout board persist above.
    # Organ columns are null at producer time (runner enriches via upsert after
    # build_hk_pick_lab's enrichment join).  See engine/pick_lab/hk_snapshot.py docstring
    # for the two-pass contract.
    #
    # Inputs in scope at this point:
    #   enriched        — per-ticker list with edge_z, washout_2w, extended, rsi, dist_200dma,
    #                     above_200, off_high, beta, role, price (close), sector, name, name_zh
    #   closes          — pd.DataFrame wide close panel (date × ticker) for signals_1d
    #   risk_state      — str: "Risk-on" / "Risk-off" / "neutral"
    #   liquidity_regime — from H5 ACCRUE organ (dict or None)
    #   vhsi_pct        — float or None (VHSI percentile computed above)
    #   as_of           — str or None (from scoreboard)
    #   site            — Path to site directory
    #   adv63           — dict[str, float]: 63d dollar turnover by ticker (from _adv63_map)
    try:
        import time as _time
        _t0_producer = _time.time()

        from engine.pick_lab.hk_snapshot import HK_SNAPSHOT_COLUMNS, build_hk_core_rows
        from engine.pick_lab.snapshot import write_snapshot
        from engine.pick_lab.velocity_desk import build_velocity_desk_artifact
        from engine.pick_lab.profile import HK_PROFILE
        from engine.pick_lab.signals_1d import compute_grids as _compute_grids

        _producer_asof = str(as_of) if as_of else str(pd.Timestamp.utcnow().date())

        # -- 1. Close panel: the breadth cache (already loaded as `closes` above)
        # Compute 1D/2D oscillators over the full close panel; also derive the 3D
        # MACD cross-up bars from a 3B-resampled panel.
        _osc_d12_map: dict[str, dict] = {}
        _osc_d3_map: dict[str, float | None] = {}
        if closes is not None and not closes.empty:
            try:
                _osc_df = _compute_grids(closes)
                # Rename kd_xup_bars → stoch_xup_bars for hk.py compatibility before storing
                for _t in _osc_df.index:
                    _od: dict = {}
                    for _g in ("d1", "d2"):
                        for _sfx in ("macd", "sig", "macd_xup_bars", "k", "d",
                                     "kd_xup_bars", "from_os", "ob"):
                            _od[f"{_g}_{_sfx}"] = _osc_df.at[_t, f"{_g}_{_sfx}"] \
                                if f"{_g}_{_sfx}" in _osc_df.columns else None
                    _osc_d12_map[_t] = _od
                # 3D MACD: resample to 3B bars and compute MACD cross
                try:
                    from engine.pick_lab.signals_1d import (
                        _rsi_macd as _rm, _xup as _xu, _since as _sn, XBAR_WIN as _XW
                    )
                    _p3 = closes.resample("3B").last()
                    for _t in closes.columns:
                        try:
                            _c3 = _p3[_t].dropna()
                            if len(_c3) < 90:
                                _osc_d3_map[_t] = None
                                continue
                            _m3, _s3 = _rm(_c3)
                            _x3 = _sn(_xu(_m3, _s3))
                            _v3 = float(_x3.iloc[-1]) if pd.notna(_x3.iloc[-1]) else None
                            _osc_d3_map[_t] = _v3 if (_v3 is None or _v3 <= _XW) else None
                        except Exception:  # noqa: BLE001
                            _osc_d3_map[_t] = None
                except Exception as _e3:  # noqa: BLE001 — 3D is additive
                    log.debug("hk producer: 3D MACD compute failed (%s) — d3_macd_xup_bars null", _e3)
                log.info("hk producer: oscillators computed for %d tickers", len(_osc_d12_map))
            except Exception as _eosc:  # noqa: BLE001 — oscillator block is additive
                log.warning("hk producer: signals_1d compute failed (%s) — osc columns null", _eosc)

        # Merge d3 into the osc map so build_hk_core_rows sees a unified dict
        for _t, _od in _osc_d12_map.items():
            _od["d3_macd_xup_bars"] = _osc_d3_map.get(_t)

        # -- 2. Stale-cross diagnostic: sessions_since_23d_cross / ret_since_23d_cross
        # Re-uses osc_d12_map: the 2D/3D cross is the older of d2_macd_xup_bars /
        # d3_macd_xup_bars.  A cross is "stale" when ≥5 sessions old with |ret| < 3%.
        _sessions_since_cross: dict[str, int | None] = {}
        _ret_since_cross: dict[str, float | None] = {}
        for _e in enriched:
            _t = _e.get("ticker")
            if not _t:
                continue
            _od = _osc_d12_map.get(_t) or {}
            # d2_macd_xup_bars is a 2B-bar count; d3_macd_xup_bars is a 3B-bar count.
            # Convert to approximate session counts before comparing (HKPL-R10a):
            #   2B bar × 2 ≈ daily sessions;  3B bar × 3 ≈ daily sessions.
            _d2x_bars = _od.get("d2_macd_xup_bars")
            _d3x_bars = _osc_d3_map.get(_t)
            _d2x_sess = int(_d2x_bars) * 2 if _d2x_bars is not None else None
            _d3x_sess = int(_d3x_bars) * 3 if _d3x_bars is not None else None
            # Pick the older cross in session units; None = never crossed in window
            _sessions_since: int | None = None
            if _d2x_sess is not None and _d3x_sess is not None:
                _sessions_since = max(_d2x_sess, _d3x_sess)
            elif _d2x_sess is not None:
                _sessions_since = _d2x_sess
            elif _d3x_sess is not None:
                _sessions_since = _d3x_sess
            _sessions_since_cross[_t] = _sessions_since
            # Return since cross: index back _sessions_since into the daily close panel
            _ret_s: float | None = None
            if _sessions_since is not None and closes is not None and _t in closes.columns:
                try:
                    _cs = closes[_t].dropna()
                    _sess_back = max(1, _sessions_since)
                    if len(_cs) > _sess_back:
                        _ret_s = round(float(_cs.iloc[-1]) / float(_cs.iloc[-1 - _sess_back]) - 1.0, 4)
                except Exception:  # noqa: BLE001
                    pass
            _ret_since_cross[_t] = _ret_s

        # -- 3. last_print_sessions_ago from the close panel (suspension guard)
        _last_print: dict[str, int | None] = {}
        if closes is not None and not closes.empty:
            _last_col = closes.apply(lambda s: s.dropna().shape[0])  # any bar = last print 0
            # More precisely: count trailing NaN sessions from the end of the panel
            _panel_len = len(closes)
            for _t in closes.columns:
                _s = closes[_t]
                # Find sessions since last valid bar by counting trailing NaN
                _rev = _s[::-1]
                _n_nan = 0
                for _v in _rev:
                    if pd.isna(_v):
                        _n_nan += 1
                    else:
                        break
                _last_print[_t] = _n_nan

        # -- 4. Build per-ticker dicts from the enriched list
        _close_by: dict[str, float | None] = {}
        _adv63_by: dict[str, float | None] = {}
        _name_by: dict[str, str | None] = {}
        _name_zh_by: dict[str, str | None] = {}
        _sector_by: dict[str, str | None] = {}
        _off_high_by: dict[str, float | None] = {}
        _rsi14_by: dict[str, float | None] = {}
        _dist_200dma_by: dict[str, float | None] = {}
        _above_200_by: dict[str, bool | None] = {}
        _edge_z_by: dict[str, float | None] = {}
        _edge_basis_by: dict[str, object] = {}
        _beta_by: dict[str, float | None] = {}
        _beta_role_by: dict[str, str | None] = {}
        _washout_2w_by: dict[str, bool | None] = {}
        _extended_by: dict[str, bool | None] = {}
        _tickers: list[str] = []

        for _e in enriched:
            _t = _e.get("ticker")
            if not _t:
                continue
            _tickers.append(_t)
            _close_by[_t] = _e.get("price")
            # adv63_hkd: try from the _adv63 field (was popped above but present in enriched scope)
            # Best-effort: read from adv63 dict computed earlier in the function
            _adv63_by[_t] = adv63.get(_t) if adv63 else None
            _name_by[_t] = _e.get("name")
            _name_zh_by[_t] = _e.get("name_zh")
            _sector_by[_t] = _e.get("sector")
            _off_high_by[_t] = _e.get("off_high")
            _rsi14_by[_t] = _e.get("rsi")
            _dist_200dma_by[_t] = _e.get("dist_200dma")
            _above_200_by[_t] = bool(_e.get("dist_200dma", 0) >= 0) if _e.get("dist_200dma") is not None else None
            _edge_z_by[_t] = _e.get("edge_z")
            _edge_basis_by[_t] = _e.get("edge_basis")
            _beta_by[_t] = _e.get("beta")
            _beta_role_by[_t] = _e.get("role")
            _washout_2w_by[_t] = bool(_e.get("washout_2w"))
            _extended_by[_t] = bool(_e.get("extended"))

        # HSI close (scalar)
        _hsi_close_scalar: float | None = None
        try:
            _hsi_df = store.read("hk", "^HSI")
            if _hsi_df is not None and "close" in _hsi_df.columns:
                _hsi_s = _hsi_df["close"].dropna()
                if not _hsi_s.empty:
                    _hsi_close_scalar = float(_hsi_s.iloc[-1])
        except Exception:  # noqa: BLE001
            pass

        # -- 5. Assemble snapshot rows
        _snap_rows = build_hk_core_rows(
            tickers=_tickers,
            asof=_producer_asof,
            close_by=_close_by,
            adv63_hkd_by=_adv63_by,
            name_by=_name_by,
            name_zh_by=_name_zh_by,
            sector_by=_sector_by,
            last_print_sessions_ago_by=_last_print,
            off_high_by=_off_high_by,
            rsi14_by=_rsi14_by,
            dist_200dma_by=_dist_200dma_by,
            above_200_by=_above_200_by,
            edge_z_by=_edge_z_by,
            edge_basis_by=_edge_basis_by,
            beta_by=_beta_by,
            beta_role_by=_beta_role_by,
            washout_2w_by=_washout_2w_by,
            extended_by=_extended_by,
            osc_d123_by=_osc_d12_map,
            sessions_since_23d_cross_by=_sessions_since_cross,
            ret_since_23d_cross_by=_ret_since_cross,
            risk_state=risk_state,
            peg_state=None,          # runner enriches from hk_regime/latest.json
            liquidity_regime=(liquidity_regime or {}).get("regime")
                              if isinstance(liquidity_regime, dict) else liquidity_regime,
            vhsi_pctile=vhsi_pct,
            hsi_close=_hsi_close_scalar,
        )
        log.info("hk producer: assembled %d snapshot rows (asof=%s)", len(_snap_rows), _producer_asof)

        # -- 6. Write snapshot parquet (keep-first; idempotent)
        # Gated on CN_LANE=asia (HKPL-R8): the US/render lanes must NOT win the keep_first
        # slot before asia-close runs, and render lanes must not overwrite the asia-enriched
        # velocity desk with the organ-null price-only first pass.
        import os as _os
        _is_asia_lane_lib = _os.environ.get("CN_LANE") == "asia"
        if _snap_rows:
            _snap_df = pd.DataFrame(_snap_rows).set_index("ticker")
            _snap_df.attrs["asof"] = _producer_asof
            if _is_asia_lane_lib:
                _n_written = write_snapshot(
                    _snap_df, _producer_asof, profile=HK_PROFILE, mode="keep_first"
                )
                log.info("hk producer: wrote %d new snapshot rows to parquet (HK_PROFILE)", _n_written)
            else:
                log.info(
                    "hk producer: CN_LANE!='asia' — snapshot parquet write skipped "
                    "(HKPL-R8; %d rows would have been written)", len(_snap_rows)
                )

        # -- 7. 1D Velocity Desk — price-only first pass (organ columns null)
        # Also gated on CN_LANE=asia so render/US lanes do not overwrite the asia-enriched
        # desk JSON with the null-organ first pass (HKPL-R8).
        try:
            if _snap_rows and _is_asia_lane_lib:
                _vd_artifact = build_velocity_desk_artifact(_snap_df, as_of=_producer_asof)
                _vd_fdir = site / "factordata"
                _vd_fdir.mkdir(parents=True, exist_ok=True)
                (_vd_fdir / "hk_1d_velocity_desk.json").write_text(
                    json.dumps(_vd_artifact, separators=(",", ":"), default=str))
                log.info("hk producer: wrote hk_1d_velocity_desk.json (%d rows, price-only first pass)",
                         _vd_artifact["n_rows"])
            elif _snap_rows:
                log.info("hk producer: CN_LANE!='asia' — velocity desk write skipped (HKPL-R8)")
        except Exception as _evd:  # noqa: BLE001 — velocity desk is additive
            log.warning("hk producer: velocity desk write failed (%s) — skipped", _evd)

        log.info("hk producer block done in %.1fs (%d rows, %d tickers)",
                 _time.time() - _t0_producer, len(_snap_rows), len(_tickers))

    except Exception as _ep:  # noqa: BLE001 — producer block must NEVER break the standout board
        log.warning("hk pick-lab producer block failed (%s) — standout board unaffected", _ep)

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

    # HSI benchmark close for the anticipation cone's relative leg (the HK market proxy).
    try:
        _hsi = store.read("hk", "^HSI")
        _hsi_close = _hsi["close"] if _hsi is not None and "close" in _hsi.columns else None
    except Exception:  # noqa: BLE001
        _hsi_close = None
    # hoist the anticipation engine + its gate ONCE (the cone is close-driven; the gate read would
    # otherwise repeat per name). None-safe: if the engine is unavailable, the cone is simply skipped.
    try:
        from engine.anticipation import anticipate as _anticipate, load_gate as _load_gate
        _ant_gate = _load_gate("US")
    except Exception:  # noqa: BLE001
        _anticipate = None
        _ant_gate = None

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
        # forward anticipation cone (close-only) — feeds the risk-shape entry tilt + favourable-cone
        # note in the shared engine; best-effort (skips quietly on thin history).
        if _anticipate is not None:
            try:
                _ant = _anticipate(close.dropna(), bench=_hsi_close, asset_class="hk_equity",
                                   gate=_ant_gate)
                if _ant:
                    rec["anticipation"] = _ant
            except Exception:  # noqa: BLE001 — additive cone, never fatal
                pass
        safe = _safe(ticker)
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
            safe = _safe(ticker)
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
            safe = _safe(ticker)
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
    # canonical render model (engine/stock_view) — ONE final pass over every per-stock JSON,
    # AFTER all patches (conviction + global_beta + fundamentals + A/H premium) have landed,
    # so the view's country_slot picks up global_beta + ah_premium. Additive + degrade-never.
    for fp in outdir.glob("*.json"):
        if fp.name in ("index.json", "calibration.json"):
            continue
        try:
            rec = json.loads(fp.read_text())
            if "ladder" not in rec:
                continue
            rec["view"] = stock_view.build_view(rec, "HK")
            fp.write_text(json.dumps(rec, default=str))
        except Exception:  # noqa: BLE001 — never fatal
            continue
    index = _write_verified_index(outdir, index)
    cal = config.data_dir() / "hk_regime" / "ladder_calibration.json"
    if cal.exists():
        (outdir / "calibration.json").write_text(cal.read_text())

    # reconstructed candlesticks for the bespoke chart: HK is close-only, so build a
    # conservative OHLC band (engine.ohlc_reconstruct) from each per-stock `chart`
    # series -> site/hkohlc/<T>.json. hk_lookup.html prefers these candles, falling
    # back to its inline close line if absent. Additive; never fatal to the build.
    try:
        from scripts.build_chart_data import build_hk
        log.info("hk chart data: %d reconstructed-candle files", build_hk(site))
    except Exception as e:  # noqa: BLE001 — chart garnish must never break the library
        log.warning("hk reconstructed candles skipped (%s)", e)

    log.info("hk library: %d analyzed, %d skipped (thin history)", built, failed)
    return betas


if __name__ == "__main__":
    main()
    sys.exit(0)
