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
from engine import stock_score  # noqa: E402
from engine import china_name_score  # noqa: E402  — per-name POTENTIAL (buy-readiness) score
from engine import china_name_score_grader  # noqa: E402  — forward-grades the POTENTIAL score
from engine import stock_technicals  # noqa: E402  — richer close-only technical snapshot
from engine import vol_squeeze  # noqa: E402  — single-stock volatility black hole (close-only)
from engine import china_signals  # noqa: E402  — A-share reversal tech + QVIX regime + margin risk + extension
from engine import china_liquidity  # noqa: E402  — dollar-ADV liquidity floor + turnover-shape discriminator
from engine.china_reversal import is_st  # noqa: E402  — ST/*ST/退 delisting-risk exclusion
from engine import china_standout_track  # noqa: E402  — board-ORDER forward ledger (keystone)
from engine import stock_view  # noqa: E402
from engine import dispersion  # noqa: E402  — cross-sectional selection-regime gross dial
from engine import entry_signal  # noqa: E402  — WHEN/at-what-price entry-timing gauge (market-agnostic)
from engine import risk_sizing  # noqa: E402  — vol-managed inverse-vol sizing (validated Sharpe lever)
from engine.cycles import _tf_state, analyze  # noqa: E402 — _tf_state: 2W StochRSI washout flag
from engine.residual_alpha import compute_residual_alpha  # noqa: E402
from engine.setups import CN_ALPHA_WEIGHT, dedupe_dual_class, setup_score  # noqa: E402
from engine import signal_gate  # noqa: E402 — owner's confluence T1->T4 cascade (layered ON main's alignment gate)
from engine import coiled  # noqa: E402  — wave-3-validated COILED cohort-washout ranking bonus (CN gate: clean15 +7.33pp, stop5 −6.21pp better, n=10,784; display/ranking only; HK failed gate — CN only)
from engine import hold as hold_engine  # noqa: E402  — W6-C HOLD tracker (CN port, W0.1); close-only, additive display chip; NEVER fed into _cn_bonus / blend_sorted
from engine.technicals import season_line, seasonality, snapshot  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("china_library")

CSI300_ETF = "510300.SS"   # cap-weighted A-share market proxy for the residual-alpha leg
JUNK_SECTOR = "A-share"    # yfinance fallback bucket → route to the engine's skip sentinel


def _name_data_through(ticker: str | None) -> str | None:
    """The ACTUAL last data date for a board name (YYYY-MM-DD) — its china_stocks close store's
    newest bar, ETF store as fallback. Additive freshness field, distinct from the board as_of."""
    if not ticker:
        return None
    for g in ("china_stocks", "china"):
        try:
            d = store.last_date(g, str(ticker))
        except Exception:  # noqa: BLE001
            d = None
        if d is not None:
            return str(d)
    return None


def _data_through() -> str | None:
    """Board-level data_through: the CSI300 benchmark's last bar (the settled-session anchor every
    excess/relative read is measured against). Additive; never renames as_of."""
    return _name_data_through(CSI300_ETF)


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
        log.warning("china library: dropped %d index rows without detail JSON (%s%s)",
                    len(missing), ", ".join(missing[:8]), "..." if len(missing) > 8 else "")
    (outdir / "index.json").write_text(json.dumps(verified))
    return verified


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
    # RICH close-only technicals (engine.stock_technicals: momentum / 52w-high proximity / BBWP /
    # HVP / RSI / MA regime) merged with the A-SHARE-specific reversal reads (china_signals: RSI-5/10,
    # 5d return, distance-from-MA20, MA120 regime gate, price-limit + board type). Supersedes the
    # thin close-only snapshot. The single-stock volatility black hole + the forward cone are added
    # too — all best-effort so a thin/odd series never breaks the build.
    try:
        _tech = {**stock_technicals.snapshot(c), **china_signals.ashare_tech(c, ticker)}
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

    # Sector washout→turn context (owner request): a per-SECTOR map the board JS uses to
    # highlight + push up names whose sector washed out along with them and is now turning
    # (leg A: the sector composite's fresh 2D-MACD x 3D-StochRSI cross; leg B: washed peers
    # basing/perking — decline velocity collapsed, slight uptick). Re-orders the DEFAULT
    # view only: reports/china-reversal-gated.md falsified sector-state as a FILTER (its
    # info is a small per-name tilt), so this never adds/removes rows and feeds nothing
    # downstream. Best-effort — absent on any failure, never read as neutral.
    sector_turn = None
    try:
        from engine.china_sector_turn import sector_turn_map
        dd = config.data_dir()
        cp = dd / "china_search" / "closes.parquet"
        mp = dd / "china_search" / "members.parquet"
        if cp.exists() and mp.exists():
            closes = pd.read_parquet(cp)
            members = pd.read_parquet(mp)
            tkr_sector = {t: (s if s != JUNK_SECTOR else "—")
                          for t, s in members["sector"].items()}
            st = sector_turn_map(closes, tkr_sector)
            sector_turn = st.get("sectors") or None
            if sector_turn:
                n_boost = sum(1 for r in sector_turn.values() if r.get("boost"))
                log.info("china sector turn: %d sectors mapped, %d boosted",
                         len(sector_turn), n_boost)
    except Exception as e:  # noqa: BLE001 — additive display context, never fatal
        log.warning("china sector turn unavailable (%s)", e)

    return {"as_of": rev.get("as_of") or lv.get("as_of") or al.get("as_of"), "modes": modes,
            "sector_turn": sector_turn}


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
    benchmark (CSI 300).

    W0.5: extended to also consider THS concept baskets (compute_china_ths_baskets).
    Takes the strongest |rel20| across curated+THS; the winning entry is labeled with
    its source so the template can distinguish "theme: <name> (THS)" from a curated basket.
    A build-time log counts board names with zero membership after the merge so the
    603129-hole remains visible (both 300725 and 603129 live only in THS).

    Best-effort — any failure yields {} and the tailwind axis is simply absent (the
    engine never reads a missing leg as neutral)."""
    out: dict[str, dict] = {}

    def _ingest(data: dict | None, source: str) -> None:
        for b in (data or {}).get("baskets") or []:
            rel = ((b.get("perf") or {}).get("20d") or {}).get("rel")
            if rel is None:
                continue
            rel20 = float(rel) * 100.0          # fraction -> percent
            label = b.get("name") or ""
            if source == "ths":
                label = f"theme: {label} (THS)"
            for m in (b.get("members") or []):
                sym = m.get("symbol")
                if not sym:
                    continue
                prev = out.get(sym)
                if prev is None or abs(rel20) > abs(prev["rel20"]):
                    out[sym] = {"name": label, "rel20": rel20, "source": source}

    try:
        from engine import baskets_china
        _ingest(baskets_china.compute_china_baskets(), "curated")
        _ingest(baskets_china.compute_china_ths_baskets(), "ths")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china basket tailwind map unavailable (%s)", e)

    # W0.5 honesty log: count how many board names still have zero theme membership
    # after combining curated + THS (the 603129/300725 hole was the trigger).
    # This runs at build time only — the log line surfaces gaps without failing the build.
    _n_zero = sum(1 for sym in out if not out[sym].get("name"))
    log.info("china tailwind map: %d names covered (curated+THS); "
             "%d with zero membership", len(out), _n_zero)
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
                # the two market-agnostic gauges (persisted by main()): WHEN to buy
                # (entry-timing) + HOW MUCH to own (vol-managed sizing). US-parity chips.
                if rec.get("entry_signal"):
                    r["entry_signal"] = rec["entry_signal"]
                if rec.get("risk_sizing"):
                    r["risk_sizing"] = rec["risk_sizing"]
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
    # ORDER: keep the cascade-blend rank main() set via signal_gate.blend_sorted (cascade tier
    # × conviction, with the 2W-StochRSI washout bonus floated up). We deliberately do NOT
    # entry-open-first re-sort here — that flattened the tier/washout rank (it orders only on the
    # entry gauge + conviction score). Entry-open stays visible as the per-card chip.
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
                      ("collectors.china_valuation", {"max_new": _val_cap}),
                      # US-parity alt-data feeds (snapshot refreshers, idempotent within a UTC day)
                      ("collectors.china_comment", {}),       # 千股千评 attention / inst-participation / main-force cost
                      ("collectors.china_lhb", {}),           # 龙虎榜 Dragon-Tiger smart/hot-money + institutional seats
                      ("collectors.china_block_trades", {}),  # 大宗交易 block premium/discount
                      ("collectors.china_zt_pool", {}),       # 涨停板 limit-up momentum / sector breadth
                      ("collectors.china_buyback", {}),       # 回购 corporate buybacks
                      ("collectors.china_pledge", {}),        # 股权质押 forced-sell tail risk
                      ("collectors.china_unlocks", {}),       # 限售股 restricted-share unlock queue
                      ("collectors.china_preannounce", {}),   # 业绩预告 earnings pre-announcements
                      # china_inquiry DEPRECATED (W4): inquiry letters now from china_filings.
                      # Kept here for legacy data/china_inquiry/ backfill runs only.
                      ("collectors.china_inquiry", {}),       # 问询函 exchange inquiry letters (DEPRECATED → china_filings)
                      ("collectors.china_st", {}),            # ST board snapshot + history + goodwill
                      # PREMIUM Tushare feeds — GATED on TUSHARE_TOKEN (each refresh() self-no-ops
                      # without the token, so CI / keyless builds are unaffected). See
                      # research/TUSHARE_INTEGRATION.md.
                      ("collectors.tushare_valuation", {}),   # daily_basic per-name PE/PB/turnover/mv
                      ("collectors.tushare_margin", {}),      # margin_detail per-name 融资余额
                      ("collectors.tushare_moneyflow", {}),   # moneyflow_dc per-name + sector 主力资金 (push2 replacement)
                      ("collectors.tushare_chips", {}),       # cyq_perf 筹码胜率 holder cost-basis
                      ("collectors.tushare_broker", {}),      # broker_recommend 券商金股 pick tally
                      ("collectors.tushare_forecast", {}),    # forecast 业绩预告 + report_rc revision
                      ("collectors.tushare_history", {})):    # weekly-grid flow/chips history → china_validation
        try:
            importlib.import_module(_mod).refresh(**_kw)
        except Exception as e:  # noqa: BLE001 — additive context, never fatal
            log.warning("china context drip %s skipped (%s)", _mod, e)

    # Register the GATED Tushare drip plane in run_status/health (masterplan §W6-CN fix 4).
    # These drips run here (not in the collect.py adapter loop), so a frozen/token-less
    # Tushare plane was previously INVISIBLE to run_status — it silently no-ops and the last
    # committed parquet freezes. Record each table's data-through date + staleness state so a
    # freeze is loud, and consumers (via engine.tushare_freshness) already de-prefer stale rows.
    try:
        from engine.tushare_freshness import staleness_badge
        from lib import store as _store
        _t_tables = {"valuation": 1, "margin": 1, "moneyflow": 1, "chips": 1,
                     "broker": 30, "forecast": 30}   # table → expected cadence (days)
        _t_health = {tbl: staleness_badge(tbl, expected_cadence_days=cad)
                     for tbl, cad in _t_tables.items()}
        _st = _store.read_status()
        _st.setdefault("tushare", {})["health"] = _t_health
        _st["tushare"]["asof"] = str(pd.Timestamp.utcnow())
        _store.write_status(_st)
        _stale = [b["table"] for b in _t_health.values() if b["state"] in ("stale", "dead")]
        if _stale:
            log.warning("tushare plane STALE/DEAD (invisible-freeze guard): %s — free fallbacks "
                        "preferred at consume time; check TUSHARE_TOKEN", _stale)
    except Exception as e:  # noqa: BLE001 — health registration must never break a build
        log.warning("tushare health registration failed (%s)", e)

    # sector-neutral residual-alpha leg — computed here if not passed in by build_china
    if alpha is None:
        alpha = compute_china_alpha()
    alpha_pt = (alpha or {}).get("per_ticker", {})
    if alpha:
        fdir = site / "factordata"
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / "china_alpha.json").write_text(
            json.dumps(alpha, separators=(",", ":"), default=str))

    # market caps (亿) for the fundamentals valuation pass + Chinese names (for the ST screen) — best-effort
    mktcap_by: dict[str, float] = {}
    name_zh_by: dict[str, str] = {}
    _PLACEHOLDER_MCAP = 30.0     # china_universe seeds CSI/config extras with a 30.0亿 sentinel; 46% of
    #                              members carry it exactly. It is NOT a real cap — feeding it into
    #                              Altman-Z distress zones / P-S coloring fabricates readings from a
    #                              constant. Thread the sentinel to UNKNOWN (masterplan §W6-CN fix 5).
    try:
        mp = config.data_dir() / "china_search" / "members.parquet"
        if mp.exists():
            mdf = pd.read_parquet(mp)
            if mdf.index.name == "ticker" and "ticker" not in mdf.columns:
                mdf = mdf.reset_index()
            tcol = "ticker" if "ticker" in mdf.columns else mdf.columns[0]
            if "mktcap_yi" in mdf.columns:
                mktcap_by = {str(r[tcol]): float(r["mktcap_yi"])
                             for _, r in mdf.iterrows()
                             if pd.notna(r.get("mktcap_yi")) and float(r["mktcap_yi"]) != _PLACEHOLDER_MCAP}
            if "name_zh" in mdf.columns:
                name_zh_by = {str(r[tcol]): str(r["name_zh"])
                              for _, r in mdf.iterrows() if pd.notna(r.get("name_zh"))}
        # prefer real per-name caps from Tushare valuation total_mv_yi (asof-gated so a frozen
        # gated plane can't reintroduce stale caps) — fills exactly the placeholder-dropped names.
        try:
            from engine.tushare_freshness import prefer_tushare as _prefer_tv
            tv = pd.read_parquet(config.data_dir() / "tushare" / "valuation.parquet")
            chosen, _src = _prefer_tv(tv if "total_mv_yi" in tv.columns else None,
                                      pd.read_parquet(config.data_dir() / "china_a_val" / "pe.parquet")
                                      if (config.data_dir() / "china_a_val" / "pe.parquet").exists() else None)
            if _src == "tushare" and chosen is not None and "total_mv_yi" in chosen.columns:
                real = {str(r["ticker"]): float(r["total_mv_yi"])
                        for _, r in chosen.iterrows()
                        if pd.notna(r.get("ticker")) and pd.notna(r.get("total_mv_yi")) and float(r["total_mv_yi"]) > 0}
                mktcap_by = {**real, **mktcap_by}     # real caps fill the placeholder gaps; keep any Sina real caps
                log.info("china mktcap: filled %d names from Tushare total_mv_yi (placeholders dropped)", len(real))
        except Exception as _te:  # noqa: BLE001 — Tushare cap overlay is additive
            log.debug("china tushare mktcap overlay skipped (%s)", _te)
    except Exception as e:  # noqa: BLE001
        log.debug("china mktcap/name load failed: %s", e)

    # ST/*ST/退 delisting-risk flags from a field that ACTUALLY CARRIES the prefix.
    # ADVERSARIAL CHECK (masterplan §W6-CN fix 5): the Sina-sourced members.parquet name_zh
    # strips the ST prefix entirely (0/1494 matches), so the name_zh-keyed ST screen was
    # SILENTLY BLIND — a known-ST name in the universe (600777.SS) reads as "新潮能源" here while
    # Tushare moneyflow carries it as "*ST新潮". Source ST status from the Tushare moneyflow name
    # field (512 ST names on its latest snapshot) which preserves the prefix. Asof-gated so a
    # frozen gated plane cannot resurrect a name that has since been un-ST'd or delisted.
    st_flag_by: dict[str, bool] = {}
    try:
        from engine.tushare_freshness import frame_asof as _tf_asof
        mfp = config.data_dir() / "tushare" / "moneyflow.parquet"
        if mfp.exists():
            mf = pd.read_parquet(mfp)
            if "name" in mf.columns and "ticker" in mf.columns:
                # keep only the latest snapshot row per ticker (the current ST status)
                if "trade_date" in mf.columns:
                    mf = mf.sort_values("trade_date").drop_duplicates("ticker", keep="last")
                for _, r in mf.iterrows():
                    nm = str(r.get("name", ""))
                    if nm:
                        st_flag_by[str(r["ticker"])] = is_st(nm, None)
                _n_st = sum(1 for v in st_flag_by.values() if v)
                log.info("china ST screen: sourced %d ST/*ST/退 flags from Tushare moneyflow "
                         "(through %s); Sina name_zh dropped the prefix (0 matches)",
                         _n_st, _tf_asof(mf))
    except Exception as _se:  # noqa: BLE001 — additive; falls back to name_zh screen
        log.debug("china ST-flag source unavailable (%s)", _se)

    # live China net-liquidity regime — the single macro conviction modifier on the
    # ladder (CN has no macro_risk/VIX leg, unlike the US build)
    liq = current_liquidity()
    log.info("net-liquidity regime for china library: %s", liq or "unknown")

    # QVIX vol-regime overlay — the GEX-analog for A-shares (no single-stock options). A panic SPIKE
    # (qvix_z high) is the crash-risk regime → a CN macro risk_overlay that taxes a chase + vetoes a
    # high-conviction verb, mirroring the US VIX overlay. INVERTED interpretation (engine/china_signals).
    qvix_reg = None
    cn_risk_overlay: dict = {"stress": 0.0, "drivers": []}
    try:
        _qp = config.data_dir() / "china_qvix" / "qvix300.parquet"
        if _qp.exists():
            qvix_reg = china_signals.qvix_regime(pd.read_parquet(_qp)["close"])
        if qvix_reg and qvix_reg.get("stress", 0) > 0:
            cn_risk_overlay = {"stress": qvix_reg["stress"],
                               "drivers": [f"QVIX {qvix_reg['regime']}"], "qvix": qvix_reg}
            log.info("china QVIX regime: %s (z=%s) → stress %.2f",
                     qvix_reg["regime"], qvix_reg["qvix_z"], qvix_reg["stress"])
    except Exception as e:  # noqa: BLE001 — additive overlay, never fatal
        log.warning("china qvix regime unavailable (%s)", e)

    # per-stock margin-financing (融资余额) crowding — a surging balance is the 2015 fire-sale
    # mechanism (leverage crowding), a contrarian RISK. Reuses the fragility idio-risk slot + a caution.
    margin_crowd: dict[str, dict] = {}
    try:
        _mp = config.data_dir() / "china_margin_detail" / "detail.parquet"
        if _mp.exists():
            from collectors._drip import latest_snapshot
            _md = latest_snapshot(pd.read_parquet(_mp), "date")  # append-only PIT → latest session
            for _, _r in _md.iterrows():
                fb, fbp = china_signals._f(_r.get("fin_balance")), china_signals._f(_r.get("fin_balance_prior"))
                chg = ((fb / fbp - 1.0) * 100.0) if (fb and fbp and fbp > 0) else None
                mc = china_signals.margin_crowding(chg, None)
                if mc and mc["risk"] > 0:
                    margin_crowd[str(_r.get("ticker"))] = mc
            log.info("china margin crowding: %d names flagged", len(margin_crowd))
    except Exception as e:  # noqa: BLE001 — additive risk leg, never fatal
        log.warning("china margin crowding unavailable (%s)", e)
    try:
        _csi = store.read("china", CSI300_ETF)
        _csi_close = _csi["close"] if _csi is not None and "close" in _csi.columns else None
    except Exception:  # noqa: BLE001
        _csi_close = None
    # hoist the anticipation engine + its gate ONCE (the cone is close-driven; the gate read would
    # otherwise repeat ~800×). None-safe: if the engine is unavailable, the cone is simply skipped.
    try:
        from engine.anticipation import anticipate as _anticipate, load_gate as _load_gate
        _ant_gate = _load_gate("US")
    except Exception:  # noqa: BLE001
        _anticipate = None
        _ant_gate = None

    # W0.10 SECTOR FIRST-TICK-UP: load the latest forward_log rows; derive a
    # Shenwan-L1 first-tick-up dict (phase=="Trough" AND osc_slope>0, the earliest
    # non-lagged inflection per rotation-machinery.md §3.2). Joined to board names
    # via an explicit Yahoo-sector → Shenwan-L1 approximation dict (taxonomies differ;
    # marked approx:true). DISPLAY/LEDGER ONLY — never fed into _cn_bonus / blend_sorted.
    # W0.10 taxonomy map: Yahoo GICS-style sector labels (board rows) → Shenwan L1 name.
    # This is an approximation (the taxonomies diverge on edges); every join is marked
    # approx:true so the template and grader can label it correctly. Sectors not listed
    # here do not produce a sector_turn chip (the field is simply absent — no false read).
    _YAHOO_TO_SW: dict[str, str] = {
        "Healthcare":              "Pharma & Biotech",
        "Technology":              "Computers",
        "Basic Materials":         "Nonferrous Metals",    # broadest match; Steel is a sibling
        "Industrials":             "Defense & Military",   # approx; Manufacturing in SW too
        "Financial Services":      "Banks",
        "Consumer Cyclical":       "Automobiles",          # approx; Retail is also Consumer
        "Consumer Defensive":      "Food & Beverage",
        "Communication Services":  "Media",
        "Energy":                  "Oil & Petrochem",
        "Real Estate":             "Real Estate",
        "Utilities":               "Utilities",
    }
    _sector_turn_by_sw: dict[str, dict] = {}   # Shenwan L1 name → first-tick-up state dict
    try:
        _flog_p = config.data_dir() / "china_sector_cycles" / "forward_log.parquet"
        if _flog_p.exists():
            _flog = pd.read_parquet(_flog_p)
            if not _flog.empty and "date" in _flog.columns:
                _latest_date = _flog["date"].max()
                _flog_latest = _flog[_flog["date"] == _latest_date].copy()
                # first-tick-up: oscillator just turned positive from a Trough (no reversal required,
                # the earliest non-lagged inflection available in forward_log — rotation-machinery §3.2)
                _ftu = _flog_latest[
                    (_flog_latest.get("phase") == "Trough") &
                    (_flog_latest.get("osc_slope", 0.0) > 0) &
                    (_flog_latest["kind"] == "sector")   # Shenwan L1 sectors only (kind==sector)
                ]
                for _, _row in _ftu.iterrows():
                    _sw_name = str(_row.get("name") or "")
                    if _sw_name:
                        _sector_turn_by_sw[_sw_name] = {
                            "state":     "bottoming",
                            "osc_slope": float(_row.get("osc_slope") or 0.0),
                            "signature": float(_row.get("signature") or 0.0),
                            "asof":      str(_latest_date),
                            "approx":    True,  # Yahoo→SW taxonomy join is approximate
                        }
                log.info("W0.10 sector first-tick-up: %d Shenwan L1 sectors qualify (Trough + osc_slope>0) "
                         "as of %s: %s", len(_sector_turn_by_sw), _latest_date,
                         list(_sector_turn_by_sw.keys()))
    except Exception as _e10:  # noqa: BLE001 — additive, never fatal
        log.warning("W0.10 sector first-tick-up load failed (%s)", _e10)

    # cross-sectional legs the unified Conviction Profile joins per name (engine/
    # stock_score): the VALIDATED A-share reversal z (the selection leg for CN) + the
    # strongest-theme basket tailwind. Both best-effort — a missing leg stays absent,
    # never read as neutral.
    rev_z_by: dict[str, float] = {}
    try:
        _rev = compute_china_reversal() or {}
        # rev_z_all covers the WHOLE screened universe (the fix): the validated reversal selection
        # leg now populates conviction for every name, not just the top-16 display watch list.
        rev_z_by = dict(_rev.get("rev_z_all") or {})
        for _r in _rev.get("watch", []):            # back-compat: ensure the display names are in too
            if _r.get("ticker") and _r.get("rev_z") is not None:
                rev_z_by.setdefault(_r["ticker"], _r["rev_z"])
        log.info("china reversal-z: populated for %d names (was top-16 only)", len(rev_z_by))
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
    entry_sig: dict[str, dict] = {}             # entry-timing gauge per name (standout rows)
    risk_sig: dict[str, dict] = {}              # vol-managed sizing per name (standout rows)
    to_write: list[tuple[str, dict]] = []
    uni = universe()
    # cross-sectional DISPERSION regime — the dial for WHEN selection pays (high dispersion
    # => selection earns more => take more gross). Computed ONCE over the whole-universe
    # return panel; feeds per-name vol-managed sizing. Mirrors build_stock_library; the
    # gauge itself is market-agnostic (reads the return cross-section + each name's vol),
    # so it propagates to the mean-reversion-flavoured A-share book unchanged.
    disp_regime, regime_gross = None, 1.0
    try:
        _uni_closes = pd.concat({t: c for (t, c, *_rest) in uni}, axis=1).sort_index()
        disp_regime = dispersion.assess(_uni_closes.pct_change(fill_method=None).tail(280))
        if disp_regime:
            regime_gross = disp_regime["gross_mult"]
            log.info("china dispersion regime: %s (pctile %s, avg_corr %s) -> gross x%.2f",
                     disp_regime["state"], disp_regime.get("dispersion_pctile"),
                     disp_regime.get("avg_corr"), regime_gross)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china dispersion regime failed (%s)", e)
    # dollar-ADV liquidity + turnover-shape from the deep OHLCV store — the REAL tradability leg
    # (members.parquet mktcap is 46% a 30亿 placeholder; ADV is measured from close×volume). One
    # read per name (~3s over the ~1,500-name store). Missing/thin names simply have no ADV entry.
    liq_by: dict[str, dict] = {}
    try:
        liq_by = china_liquidity.liquidity_map([t for (t, *_r) in uni])
        _n_illq = sum(1 for v in liq_by.values()
                      if (v.get("adv_yi") or 0) < china_liquidity.ADV_FLOOR_YI)
        log.info("china liquidity: ADV for %d names; %d below the %.2f亿/day tradability floor",
                 len(liq_by), _n_illq, china_liquidity.ADV_FLOOR_YI)
    except Exception as e:  # noqa: BLE001 — additive screen, never fatal
        log.warning("china liquidity map unavailable (%s)", e)

    # QUALITY / TRADABILITY screen (P6) — keep garbage off the standout pool. Fail-CLOSED on ST;
    # the ADV floor only excludes names we can PROVE are illiquid (missing ADV passes through, logged).
    # market-cap is inert on the top-cap search universe (all real caps >30亿, 46% placeholder) so it
    # is kept as honest defense-in-depth and reported, not relied on. Counts surface the REAL bite.
    screen_drop = {"st": 0, "mcap": 0, "adv": 0, "stale": 0}
    MCAP_FLOOR_YI = 30.0            # matches china_reversal; 30.0 exactly is the placeholder => "unknown"
    STALE_DAYS = 15                 # a name whose last bar is >15 calendar days stale is likely
    #                                suspended/delisted (e.g. a frozen HK/A name) — never a live buy.
    # panel reference date = the freshest last-bar across the universe (suspended names lag it).
    _panel_asof = max((c.last_valid_index() for (_t, c, *_r) in uni
                       if c is not None and c.last_valid_index() is not None), default=None)

    def _tradability_ok(_t: str) -> bool:
        # ST from the Tushare name field (carries the prefix) OR the name_zh fallback (usually
        # blind — see the ST-flag sourcing above). Fail-CLOSED: either source flags → drop.
        if st_flag_by.get(_t, False) or is_st(name_zh_by.get(_t), None):
            screen_drop["st"] += 1
            return False
        _cap = mktcap_by.get(_t)
        if _cap is not None and _cap != MCAP_FLOOR_YI and _cap < MCAP_FLOOR_YI:  # real sub-floor cap only
            screen_drop["mcap"] += 1
            return False
        _adv = (liq_by.get(_t) or {}).get("adv_yi")
        if _adv is not None and _adv < china_liquidity.ADV_FLOOR_YI:  # proven illiquid
            screen_drop["adv"] += 1
            return False
        return True

    recs = _analyze_universe(uni, liq)      # parallel analyze() fan-out (order-preserving)
    sig_verdict: dict[str, dict] = {}       # owner's confluence T1->T4 cascade verdict per name
    # COILED wave-3 CN ranking bonus: per-name inputs collected in the loop; cohort_fractions
    # computed AFTER the loop (cross-sectional). CN gate: clean15 +7.33pp, stop5 −6.21pp, n=10,784.
    # HK failed its gate — touch NOTHING in HK.
    _coil_d:      dict[str, float | None] = {}
    _coil_wash:   dict[str, bool | None]  = {}
    _coil_div:    dict[str, bool]         = {}
    _coil_sector: dict[str, str | None]   = {}
    _coil_fire:   dict[str, dict]         = {}   # wave-4 COILED-FIRE display marker (CN, no rank change)
    _hold_state_cn: dict[str, dict]       = {}   # W0.1 HOLD tracker (display/ledger only; never in _cn_bonus)
    for (ticker, close, high, name, sector), rec in zip(uni, recs):
        if rec is None:
            failed += 1
            continue
        # COMBINE: the confluence T1->T4 cascade is computed alongside main's bottoming-alignment
        # gate. It NEVER changes which names are eligible (alignment stays the inclusion gate) —
        # it only adds the per-card tier badge and re-ranks WITHIN the aligned buy list (below).
        sig_verdict[ticker] = signal_gate.gate(ticker, close)
        # W0.1 HOLD tracker (CN port): compute basing state after the confluence anchor. Close-only;
        # anchor = the §7 take/pending buy-marker date when an open buy exists, else fall back to the
        # most-recent 3D RSI-MACD cross-up (≤ CROSS_MAX_AGE=45 trading days old). CN-specific caveat:
        # A-share names can be suspended >20 trading days — if the close series has a gap >20 bars
        # AFTER the last candidate anchor the fallback is skipped (see _cn_suspension_gap below).
        # DISPLAY/LEDGER ONLY — never fed into _cn_bonus() or blend_sorted. Stacks with washout/COILED.
        try:
            _sv_cn = sig_verdict[ticker]
            _last_m_cn = _sv_cn.get("last")
            _is_buy_cn = bool(_last_m_cn and _last_m_cn.get("type") in ("buy", "rebuy"))
            _anchor_cn = _last_m_cn.get("date") if _is_buy_cn else None
            # CN suspension guard: if the close series has a gap >20 trading days after the
            # last candidate anchor (or the tail of the series), skip the fallback to avoid a
            # stale cross anchoring a name that was simply suspended.
            _use_fallback = True
            if _anchor_cn is None:
                _clean = close.dropna()
                if len(_clean) >= 2:
                    _gaps = _clean.index.to_series().diff().dt.days.fillna(0)
                    _max_gap_td = int(_gaps.max())
                    if _max_gap_td > 28:   # >20 trading days ≈ >28 calendar days — suspension
                        _use_fallback = False
            _hs_cn = hold_engine.hold_state(close, anchor_date=_anchor_cn,
                                            last_cross_fallback=_use_fallback)
            if _hs_cn is not None:
                _hold_state_cn[ticker] = _hs_cn
        except Exception:  # noqa: BLE001 — additive, never fatal
            pass
        # COILED wave-3 CN ranking bonus: collect per-name inputs for cohort computation below.
        # Wave-4: also collect fire_recent for the COILED-FIRE display chip (CN included per wave-4
        # ship record; HK NOT touched; display chip + forward-ledger only, NO rank/bonus change).
        try:
            _coil_d[ticker]      = coiled.weekly_d_last(close)
            _coil_wash[ticker]   = coiled.washout_ctx(close)
            _coil_div[ticker]    = coiled.bull_div(close)
            _coil_sector[ticker] = sector or None
            _coil_fire[ticker]   = coiled.fire_recent(close)
        except Exception:  # noqa: BLE001 — additive, never fatal
            pass
        if alpha_pt.get(ticker):            # additive: absent => no alpha panel for this name
            rec["alpha"] = alpha_pt[ticker]
            sc = _setup_score(rec)
            if sc:
                # 2W StochRSI WASHOUT-RECLAIM (owner request): a bullish reclaim of the 20 line
                # from oversold on the 2-week bar (2W-FRI, the btc_mtf/commodity_mtf convention).
                # Such names have likely washed out on the higher 2W/1M timeframe, so the board
                # gives them a big rank lift (signal_gate.blend_sorted bonus_of) WHILE the cascade
                # tier still orders within. Best-effort; thin history -> no flag.
                try:
                    _tf2w = _tf_state(close.resample("2W-FRI").last().dropna())
                    sc[1]["washout_2w"] = bool(_tf2w.get("stoch_cross_up"))
                except Exception:  # noqa: BLE001 — additive, never fatal
                    pass
                # anti-chase EXTENSION read (close-only) — DEMOTES names that already ran (limit-up
                # pop / stretched above MA / near 52w high). Attached to the row; blend_sorted's
                # bonus_of subtracts a penalty proportional to score. Turnover-shape from the deep
                # store distinguishes accumulation (expansion off a base) from a distribution spike.
                try:
                    sc[1]["extension"] = china_signals.extension_read(
                        close, rec.get("tech"), ticker,
                        turn_ratio=(liq_by.get(ticker) or {}).get("turn_ratio"))
                except Exception:  # noqa: BLE001 — additive, never fatal
                    pass
                # QUALITY / TRADABILITY screen — keep ST / illiquid / stale garbage off the board
                _last = close.last_valid_index()
                if (_panel_asof is not None and _last is not None
                        and (_panel_asof - _last).days > STALE_DAYS):
                    screen_drop["stale"] += 1          # suspended / delisted — not a live pick
                elif _tradability_ok(ticker):
                    cand.append(sc)
        # ---- unified Conviction Profile (engine/stock_score, CN market) ----------
        # The single block both the china.html standout card AND china_lookup render,
        # so the two can never structurally disagree. The CN SELECTION leg is the
        # VALIDATED reversal z (residual alpha is a light tiebreaker); the cycle state
        # is a HARD verb modifier (a downtrend caps the entry axis and forbids a Buy
        # verb). Fund priors are OMITTED — the raw Piotroski/Altman scores are not
        # unit-variance cross-sectional z's, and a missing leg is honest (never neutral).
        # forward anticipation cone (close-only) — feeds the risk-shape entry tilt + favourable-cone
        # note in the shared engine; best-effort (skips quietly on thin history).
        if _anticipate is not None:
            try:
                _ant = _anticipate(close.dropna(), bench=_csi_close, asset_class="cn_equity",
                                   gate=_ant_gate)
                if _ant:
                    rec["anticipation"] = _ant
            except Exception:  # noqa: BLE001 — additive cone, never fatal
                pass
        # margin-financing crowding → the fragility idio-risk slot + a caution (contrarian leverage risk)
        _mc = margin_crowd.get(ticker)
        if _mc and _mc.get("crowded"):
            rec["fragility"] = {
                "flag": True,
                "risk": _mc.get("risk"),
                "band": _mc.get("band"),
                "chg_pct": _mc.get("chg_pct"),
                "pct_mcap": _mc.get("pct_mcap"),
            }
            rec["margin_crowd"] = _mc
        norm = stock_score.normalize_rec(
            rec, "CN", rev_z=rev_z_by.get(ticker), basket=basket_tw.get(ticker))
        prof = stock_score.conviction_profile(norm, "CN", ctx={
            "as_of": (alpha or {}).get("as_of"), "risk_overlay": cn_risk_overlay})
        rec["conviction"] = prof
        # ---- Vol-managed sizing (engine/risk_sizing) — the VALIDATED Sharpe lever -----
        # Inverse-vol size scaled by the dispersion regime: HOW MUCH to own (risk),
        # orthogonal to conviction (WHAT) and the entry gauge (WHEN). Pure price-vol, so
        # market-agnostic — propagates to the A-share book unchanged. Persisted on the rec
        # so it rides into the per-stock JSON + the standout card (re-read by the board).
        try:
            rs = risk_sizing.assess(close, regime_gross=regime_gross)
            if rs:
                rec["risk_sizing"] = rs
                if isinstance(prof, dict) and isinstance(prof.get("size"), dict):
                    prof["size"]["vol_mult"] = rs["size_mult"]      # additive, never overrides
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("china risk-sizing for %s failed (%s)", ticker, e)
        # ---- Entry-timing gauge (engine/entry_signal) — the SECOND gauge --------------
        # Conviction answers "own it?"; this answers "buy now / at what price / when?".
        # Reads the cycle/ladder (CN recs carry the same ladder) — market-agnostic. China
        # `high` is None (close-only caches); assess() tolerates that.
        # Gate the entry gauge on the SAME MACD-2D x StochRSI-3D confluence as the board
        # (mirrors the US pattern in build_stock_library): a daily-cycle "buy now / partial"
        # with no fresh confluence cross reads "awaiting confluence", never an open entry.
        try:
            es = entry_signal.assess(close, high, rec,
                                     buyable=signal_gate.is_buyable(sig_verdict.get(ticker)))
            if es:
                rec["entry_signal"] = es
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("china entry-signal for %s failed (%s)", ticker, e)
        # ---- Confluence cascade verdict (T1->T4) on the per-stock JSON ---------
        # Same MACD-2D x StochRSI-3D gate the China standout board ranks by, persisted per
        # name so the basket_china Holdings table can push a fresh confluence cross to the
        # top. Slim allow_nan-safe subset; mirrors rec["entry_signal"] (build_stock_library
        # parity). None-tolerant — unrated names get {eligible:false, tier_cascade:null}.
        rec["signal"] = signal_gate.buy_signal(sig_verdict.get(ticker))
        # ---- POTENTIAL score (engine/china_name_score) — the displayed CN buy-readiness ----
        # Replaces the old reversal-percentile (which ranked the most beaten-down name highest):
        # a trigger-gated washout confluence answering "set up to rise FROM HERE, actionable now?".
        # Computed AFTER entry_signal so the trigger can read the entry gauge. Attached here;
        # the displayed conviction.score/band are overridden from it after panel scoring below.
        try:
            rec["conviction"]["potential"] = china_name_score.potential_score(
                rec, regime_stress=float(cn_risk_overlay.get("stress") or 0.0))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("china potential score for %s failed (%s)", ticker, e)
        profiles[ticker] = prof
        if rec.get("entry_signal"):
            entry_sig[ticker] = rec["entry_signal"]    # attached to standout rows below
        if rec.get("risk_sizing"):
            risk_sig[ticker] = rec["risk_sizing"]      # attached to standout rows below
        _tech = rec.get("tech") or {}
        _dir = (rec.get("ladder") or {}).get("dir")
        disp_map[ticker] = {
            "price": _tech.get("price"), "off_high": _tech.get("off_52w_high_pct"),
            "spark_svg": _spark_svg(
                list(close.dropna().tail(64).values),
                color=("var(--up)" if _dir == "up" else "var(--down)" if _dir == "down" else "var(--muted)"))}
        # W0.1 HOLD: attach to per-stock JSON before the deferred write (mirrors US L1477-1479)
        if _hold_state_cn.get(ticker):
            rec["hold"] = _hold_state_cn[ticker]
        safe = _safe(ticker)
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
    stock_score.attach_panel_scores(profiles, "CN")
    # CN DISPLAYED score = the POTENTIAL (buy-readiness), not the comp-z reversal percentile.
    # Keep the percentile as `rank_pctile` (still a meaningful within-board rank) and drop the
    # now-inaccurate "within-board percentile RANK" honesty note. The verdict/entry gauges are
    # already cycle-anchored, so all three now agree (washed-out + turning = high, not "most fallen").
    for _, _rec in to_write:
        _c = _rec.get("conviction") or {}
        _pot = _c.get("potential")
        if not _pot:
            continue
        _c["rank_pctile"] = _c.get("score")               # preserve the old percentile rank
        _c["score"] = _pot["score"]
        _c["band"], _c["band_en"], _c["band_zh"] = _pot["band"], _pot["band_en"], _pot["band_zh"]
        _notes = _c.get("notes")
        if _notes:
            _c["notes"] = [n for n in _notes if n.get("kind") != "rank"] or None
    # forward-grading ledger — log today's POTENTIAL calls (keep-first per date,ticker) so the
    # score EARNS trust over time. The render lanes discard data/ writes, so only the nightly
    # `daily` (which commits data/) persists one entry per name per day. Best-effort.
    try:
        _asof = (alpha or {}).get("as_of") or str(pd.Timestamp.utcnow().date())
        _calls = []
        for _, _rec in to_write:
            _pot = (_rec.get("conviction") or {}).get("potential")
            if _pot and _pot.get("call"):
                _calls.append({**_pot["call"], "level": (_rec.get("tech") or {}).get("price")})
        if _calls:
            _n = china_name_score_grader.append_name_calls(_calls, asof=_asof)
            log.info("china name-score grader: logged %d calls for %s (ledger=%d)", len(_calls), _asof, _n)
    except Exception as e:  # noqa: BLE001 — grading is additive, never fatal
        log.warning("china name-score grader append failed (%s)", e)
    # ---- B2 accrual (research/LABEL_FALTERING_PHASE0.md §2) — archive per-basket member-
    # conviction stats (potential median/IQR/n + theme score/label) so the pre-registered
    # demotion study can run once ≥180 trading days accrue. Write-only ledger, never fatal.
    try:
        from engine import conviction_accrual
        _b2_asof = (alpha or {}).get("as_of")
        if conviction_accrual.archive_member_conviction("china", profiles, asof=_b2_asof):
            log.info("B2 conviction accrual: archived conviction_china for %s", _b2_asof)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("B2 conviction accrual (china) failed (%s)", e)
    for safe, rec in to_write:
        rec["view"] = stock_view.build_view(rec, "CN")   # canonical render model (rebuilt below once val/margin land)
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
        safe = _safe(ticker)
        fp = outdir / f"{safe}.json"
        if not fp.exists():
            continue
        try:
            rec = json.loads(fp.read_text())
            rec.update(patch)
            rec["view"] = stock_view.build_view(rec, "CN")   # rebuild so val_band + margin_fin cards appear
            fp.write_text(json.dumps(rec, default=str))
        except Exception:  # noqa: BLE001
            continue
    fset = set(fmap)
    for idx in index:                             # keep the existing fundamentals index flag
        if idx["t"] in fset:
            idx["f"] = 1
    log.info("china context attached: fund %d · consensus %d · earnings %d · val_pct %d · margin %d",
             len(fmap), len(cons), len(earn), len(vpct), len(marg))

    # per-name QUALITY composite (P9) — DISPLAY BADGE ONLY, deliberately NEVER in the board sort.
    # Sector-neutral z of value (earnings yield), quality (ROE) and profitability (net margin) via the
    # validated composite_score machinery (equal-weight, sector-neutral). Coverage is only ~half the
    # universe and value/quality are MUTED A-share edges, so a coverage-biased SORT would distort the
    # board — this is a chip (strong/avg/weak/—) to help weed obvious junk, nothing more.
    quality_badge: dict[str, dict] = {}
    if fmap:
        try:
            from engine import composite_score
            _legs = {t: {"value": (100.0 / v["pe"]) if (v.get("pe") and v["pe"] > 0) else None,
                         "quality": v.get("roe"), "profitability": v.get("net_margin")}
                     for t, f in fmap.items() for v in [f.get("valuation") or {}]}
            _lf = pd.DataFrame.from_dict(_legs, orient="index")
            _comp = composite_score.build(_lf, {t: sector_by.get(t) or "—" for t in _legs},
                                          use_legs=("value", "quality", "profitability"))
            for _t, _row in _comp.iterrows():
                _z = _row.get("composite")
                if _z is None or _z != _z:
                    continue
                _v = fmap[_t].get("valuation") or {}
                quality_badge[_t] = {
                    "z": round(float(_z), 2),
                    "band": "strong" if _z >= 0.75 else "weak" if _z <= -0.75 else "avg",
                    "n_legs": int(_row.get("n_legs") or 0), "roe": _v.get("roe"), "pe": _v.get("pe"),
                    "piotroski": (fmap[_t].get("piotroski") or {}).get("score")}
            log.info("china quality composite: %d names badged (of %d with fundamentals, ~%d%% of universe)",
                     len(quality_badge), len(fmap), int(100 * len(fmap) / max(1, len(price_by))))
        except Exception as e:  # noqa: BLE001 — additive badge, never fatal
            log.warning("china quality composite failed (%s)", e)
    index = _write_verified_index(outdir, index)
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

    # cross-sectional "Top setups" — now BOTTOMING-ALIGNED, not reversal/momentum-led.
    # The buy shortlist is gated on multi-timeframe alignment (weekly not-falling +
    # 3-day nearing a bullish cross + daily just-crossed/about-to), so a mid-weekly-bear
    # falling knife can no longer be surfaced as a buy card. The reversal-led setup score
    # survives only as the ranking tiebreaker within aligned names; the cycle alignment
    # is the gate. NEAR-aligned names backfill (clearly tagged) only when too few names
    # are fully aligned. align_map keys on the same alignment block the Conviction profile
    # carries (engine.cycles.mtf_alignment), available on every analyzed name's ladder.
    setups = None
    align_map = {t: (p or {}).get("alignment") for t, p in profiles.items()}
    # CONFLUENCE GATE (owner directive, 2026-06-29): the board's INCLUSION gate is now the
    # owner's T1->T4 MACD-RSI x StochRSI confluence cascade (engine/signal_gate, computed per
    # name above as sig_verdict), REPLACING the bottoming-alignment screen. A name is buyable
    # iff its cascade verdict is `eligible` — a held-fresh / forming T1 master, or a projected
    # T2/T3/T4 — all already freshness- and not-topped-guarded inside signal_gate.gate. Being
    # ABOVE or below the 200-day is irrelevant; the cascade alone decides (the prior screen's
    # below-200 "bottoming" bias was wrong for this system). Ranked by the weighted cascade
    # blend (signal_gate.blend_sorted): strongest tier first, lifted by the setup-score
    # percentile so conviction breaks ties within a tier. The bottoming-alignment line is kept
    # ONLY as per-card CONTEXT (align_tier, rendered when the name also happens to be aligned).
    def _atier(t: str) -> str | None:
        a = align_map.get(t) or {}
        return "aligned" if a.get("aligned") else ("near" if a.get("near") else None)
    WASHOUT_BONUS = 0.5   # 2W StochRSI washout-reclaim lift (~one tier; cascade tier still orders within)
    EXT_PENALTY = 0.5     # anti-chase: a fully-extended name is demoted ~one tier (symmetric w/ washout)
    # CN tier flatten (P4, revised): in A-shares a confirmed breakout is often already run and
    # medium-term momentum is dead, so we let a FRESH T2/T3 compete with a fresh T1 — a MILD
    # near-parity flatten (wn floored at 0.6, tier_frac 0.30 vs the US 0.45), NOT an inversion.
    # "Already ran" is handled ORTHOGONALLY by EXT_PENALTY below, not by demoting every T1.
    CN_TIER_FRAC, CN_WN_FLOOR = 0.30, 0.60

    # COILED wave-3 CN ranking bonus: cohort_fractions is cross-sectional (requires the full
    # universe), so it is computed here AFTER the loop. Both steps try/except guarded; failure
    # degrades gracefully to empty dict (board continues without the bonus, never fatal).
    coiled_by: dict[str, dict] = {}
    try:
        _coil_frac = coiled.cohort_fractions(_coil_d, _coil_sector)
        coiled_by = {
            t: coiled.assess(_coil_wash.get(t), _coil_frac.get(t), bool(_coil_div.get(t)))
            for t in sig_verdict
        }
        # Wave-4 COILED-FIRE CN: inject fire fields into assess dict for COILED names with a
        # recent fire. Display chip + forward-ledger only — NO rank/bonus change.
        for t, cb in coiled_by.items():
            if cb.get("coiled"):
                _fr = _coil_fire.get(t) or {}
                if _fr.get("fire"):
                    cb["fire"]       = True
                    cb["fire_ticks"] = _fr.get("ticks")
                    cb["fire_src"]   = _fr.get("src")
    except Exception as _e:  # noqa: BLE001 — additive; board degrades gracefully without bonus
        log.warning("china coiled bonus skipped (%s)", _e)
        coiled_by = {}

    def _cn_bonus(r):
        # wave-3 CN gate: clean15 +7.33pp, stop5 −6.21pp better, n=10,784. ADDITIVE beside:
        #   • WASHOUT_BONUS (own-name 2W StochRSI reclaim, orthogonal own-name signal)
        #   • EXT_PENALTY (anti-chase extension demote, orthogonal anti-chase)
        # A name with both washout_2w AND coiled legitimately stacks both bonuses.
        b = WASHOUT_BONUS if r.get("washout_2w") else 0.0
        b += ((coiled_by.get(r.get("ticker")) or {}).get("bonus") or 0.0)
        ext = float((r.get("extension") or {}).get("score") or 0.0)
        return b - EXT_PENALTY * ext                    # net additive lift/penalty on the 0..1 blend

    eligible_rows = signal_gate.blend_sorted(
        dedupe_dual_class([r for _s, r in cand
                           if (sig_verdict.get(r.get("ticker")) or {}).get("eligible")]),
        base_of=lambda r: r.get("setup") or 0.0,
        verdict_of=lambda r: sig_verdict.get(r.get("ticker")),
        bonus_of=_cn_bonus, tier_frac=CN_TIER_FRAC, wn_floor=CN_WN_FLOOR)
    _n_ext = sum(1 for r in eligible_rows if (r.get("extension") or {}).get("extended"))
    log.info("china confluence-gate: %d of %d scored names eligible (T1-T4); "
             "%d extended (demoted); quality-screen dropped ST=%d mcap=%d adv=%d stale=%d",
             len(eligible_rows), len(cand), _n_ext,
             screen_drop["st"], screen_drop["mcap"], screen_drop["adv"], screen_drop["stale"])

    # DIVERSIFY the head of the strip: cap per-sector representation so the top isn't ONE crowded
    # theme shown five ways (the flat, overlapping THS taxonomy makes single-theme crowding common).
    # A pure reorder — overflow rows keep their relative order and are appended after; nothing drops.
    def _diversify(rows: list, cap: int = 6) -> list:
        from collections import defaultdict
        seen: dict[str, int] = defaultdict(int)
        head, overflow = [], []
        for r in rows:
            s = r.get("sector") or "—"
            if seen[s] < cap:
                head.append(r); seen[s] += 1
            else:
                overflow.append(r)
        return head + overflow
    eligible_rows = _diversify(eligible_rows)

    # ── W1-B: W-tier setup layer wiring ───────────────────────────────────────────
    # (1) Compute w_setup for the FULL closes-panel universe (>=200 bars).
    #     Reuse the already-loaded closes from `uni`; do NOT re-read per name.
    #     Profile: ~6ms/name × 1478 names ≈ 9s — well inside the 2-min budget.
    #     Best-effort: failures degrade to None (no stage for that name), never fatal.
    from engine.setup_tier import w_setup as _w_setup_fn, assign_stage as _assign_stage_fn
    from engine.setup_tier import STAGE_ENTRY, STAGE_RAN_LATE, STAGE_RIPENING
    _wsetup_by: dict[str, dict | None] = {}
    _t0_wsetup = time.time()
    for (_t, _close_w, _high_w, _name_w, _sector_w) in uni:
        _c_w = _close_w.dropna() if _close_w is not None else None
        if _c_w is None or len(_c_w) < 200:
            continue
        try:
            _wsetup_by[_t] = _w_setup_fn(_c_w)
        except Exception:  # noqa: BLE001 — additive; never fatal
            _wsetup_by[_t] = None
    log.info("W1-B w_setup: %d names scanned in %.0fs (%d non-None)",
             len(_wsetup_by), time.time() - _t0_wsetup,
             sum(1 for v in _wsetup_by.values() if v is not None))

    # ── W2-B: Narrative tags (computed once per build, best-effort) ───────────
    # Calls build_narrative_tags() which loads closes + memberships + radar on
    # its own; returns empty dicts on any missing artifact (never raises).
    # Result is then joined per-name into buy and ripening rows below.
    # DISPLAY/LEDGER ONLY — rank influence NOT wired in W2 (F4 / F3 discipline).
    try:
        from engine.china_narrative_tags import (
            build_narrative_tags as _build_narr_tags,
            ab_tier as _narr_ab_tier,
        )
        _narr_result = _build_narr_tags()
        _narr_tags: dict = _narr_result.get("tags") or {}
        log.info("W2-B narrative tags: %d tickers tagged (%d baskets, as_of %s)",
                 _narr_result.get("n_tagged", 0), _narr_result.get("n_baskets", 0),
                 _narr_result.get("as_of", "?"))
    except Exception as _narr_exc:  # noqa: BLE001 — additive, never fatal
        log.warning("W2-B narrative tags failed (%s) — board renders without narrative data",
                    _narr_exc)
        _narr_tags = {}
        _narr_ab_tier = lambda stage, tag: None  # noqa: E731 — degraded stub

    # (2) Derive last_cross_info for rule-3 (NOT gate-eligible, recent cross <=15 sessions).
    #     Source: sig_verdict["last"] gives the last buy marker date; we compute sessions_since
    #     and pct_since from the close series in `uni`. Only compute for ineligible names.
    _close_map: dict[str, pd.Series] = {t: c for (t, c, *_) in uni if c is not None}
    _eligible_set = {r.get("ticker") for r in eligible_rows}

    def _last_cross_info(ticker: str, max_sessions: int | None = 15) -> dict | None:
        """Extract last-cross info: (cross_date, sessions_since, pct_since).
        Rule-3 callers keep the default 15-session window; buy rows pass
        max_sessions=None (rules 1a/2c need cross AGE with no cutoff)."""
        sv = sig_verdict.get(ticker)
        if not sv:
            return None
        last_m = sv.get("last") or {}
        if last_m.get("type") not in ("buy", "rebuy"):
            return None
        cross_date_str = last_m.get("date")
        if not cross_date_str:
            return None
        try:
            cross_dt = pd.Timestamp(cross_date_str)
            # NOT `_close_map.get(t) or Series()` — bool(Series) raises ValueError,
            # which the except below swallowed, silently disabling this function for
            # EVERY name (the rule-3 RAN shelf logged 0 rows every build).
            c = _close_map.get(ticker)
            c = pd.Series(dtype=float) if c is None else c.dropna()
            after = c[c.index > cross_dt]
            sessions_since = int(len(after))
            if max_sessions is not None and sessions_since > max_sessions:
                return None       # outside the caller's window — no point computing pct
            at_or_before = c[c.index <= cross_dt]
            if len(at_or_before) == 0:
                return None
            # sessions_since == 0 (cross fired on the latest bar) is a legitimate
            # fresh cross for buy rows; rule-3 callers never see it (they require
            # the gate to have LAPSED, which takes at least one session).
            price_at_cross = float(at_or_before.iloc[-1])
            spot = float(c.iloc[-1])
            pct_since = round((spot / price_at_cross - 1) * 100, 1) if price_at_cross > 0 else None
            return {"cross_date": cross_date_str, "sessions_since": sessions_since,
                    "pct_since": pct_since}
        except Exception:
            return None

    # (3) Assign lifecycle stage to each buy row (rules 1-2). ENTRY shelf preserves
    #     the existing blend_sorted order UNCHANGED (F3 discipline: no rank change here).
    #     Each buy row gains stage / sublabel / detail / why_ranked fields.
    def _why_ranked(r: dict) -> str:
        """Compact string of the actual blend inputs on this row — display only, no rank change."""
        sig = r.get("signal") or {}
        parts = []
        tier = sig.get("tier_cascade") or sig.get("tier")
        if tier:
            parts.append(str(tier))
        if r.get("washout_2w"):
            parts.append("2W-washout")
        cb = r.get("coiled") or {}
        if cb.get("coiled"):
            parts.append("coiled")
        ext = r.get("extension") or {}
        if ext.get("extended"):
            ext_sc = ext.get("score")
            parts.append(f"- ext {round(float(ext_sc), 2)}" if ext_sc is not None else "- ext")
        return " + ".join(p for p in parts if not p.startswith("-")) + (
            " " + " ".join(p for p in parts if p.startswith("-"))
        ).rstrip() if parts else ""

    for r in eligible_rows:
        _t = r.get("ticker")
        _sv = sig_verdict.get(_t) or {}
        _es = entry_sig.get(_t) or {}
        _es_status = _es.get("status")
        # overextended = the A-share PRICE-extension read only (extension_read: has it
        # already run?). The old `or _es_status in ("extended","topping")` term imported
        # the daily-cycle RSI>70 gate, which fires on the FIRST breakout thrust off a
        # base (limit-up mechanics) — it demoted exactly the freshest T1/T2 crosses to
        # RAN_LATE while names that crossed weeks ago sat on ENTRY. The daily gauge is
        # display context on the card; the stage may not be driven by it.
        _overext = bool((r.get("extension") or {}).get("extended"))
        _stage_res = _assign_stage_fn(
            gate_eligible=bool(_sv.get("eligible")),
            entry_status=_es_status,
            overextended=_overext,
            last_cross_info=_last_cross_info(_t, max_sessions=None),  # rule 1a: cross age
            hold_state=_hold_state_cn.get(_t),
            wsetup=_wsetup_by.get(_t),
        )
        r["stage"] = _stage_res["stage"]
        r["stage_sublabel"] = _stage_res.get("sublabel")
        r["stage_sublabel_zh"] = _stage_res.get("sublabel_zh")
        r["stage_detail"] = _stage_res.get("detail") or {}
        r["why_ranked"] = _why_ranked(r)

    # After stage assignment: propagate muted_entry from stage_detail to the row dict
    # so Jinja can suppress green banding without reading the nested detail dict.
    # Per adjudicated design F6: rule-2 rows with entry_status in {buy_now, partial}
    # are legitimate but must render muted (no green class, no Buy-now tooltip).
    for r in eligible_rows:
        _sd = r.get("stage_detail") or {}
        if _sd.get("muted_entry"):
            r["muted_entry"] = True

    # (4) Build the RAN array (rule 3): NOT gate-eligible, last cross within 15 sessions.
    #     Source: the full cand pool + sig_verdict; not the eligible_rows.
    #     Sorted by recency (sessions_since ascending), capped at 15.
    _ran_rows: list[dict] = []
    for (_t, _close_w, _high_w, _name_w, _sector_w) in uni:
        if _t in _eligible_set:
            continue           # gate-eligible -> already on buy shelf, not here
        _sv = sig_verdict.get(_t)
        if not _sv:
            continue
        if _sv.get("eligible"):
            continue           # only non-eligible names qualify for rule-3
        _lci = _last_cross_info(_t)
        if not _lci:
            continue
        _hold_s = _hold_state_cn.get(_t)
        _stage_r = _assign_stage_fn(
            gate_eligible=False, entry_status=None, overextended=False,
            last_cross_info=_lci, hold_state=_hold_s, wsetup=_wsetup_by.get(_t),
        )
        if _stage_r.get("stage") != STAGE_RAN_LATE:
            continue
        _hold_summary = None
        if _hold_s and _hold_s.get("state") in ("intact", "launched"):
            _hold_summary = {
                "state": _hold_s.get("state"),
                "anchor": _hold_s.get("anchor"),
                "maxup_pct": _hold_s.get("maxup_pct"),
                "invalidation": _hold_s.get("invalidation"),
            }
        _ran_rows.append({
            "ticker": _t, "name": _name_w or _t, "sector": _sector_w or "",
            "cross_date": _lci["cross_date"],
            "sessions_since": _lci["sessions_since"],
            "pct_since": _lci.get("pct_since"),
            "sublabel": _stage_r.get("sublabel"),
            "basing_chip": (_stage_r.get("detail") or {}).get("basing_chip"),
            "launched_chip": (_stage_r.get("detail") or {}).get("launched_chip"),
            "hold_summary": _hold_summary,
        })
    _ran_rows.sort(key=lambda x: x.get("sessions_since") or 99)
    _ran_rows = _ran_rows[:15]

    # (5) Build the RIPENING array (rule 4): NOT gate-eligible, no recent cross, setup_live.
    #     Screen the FULL closes panel universe (skip <200 bars). Sorted by imminence
    #     (macd_bars_to_cross ascending, then washout depth). Capped at 24.
    _ripening_rows: list[dict] = []
    for (_t, _close_w, _high_w, _name_w, _sector_w) in uni:
        if _t in _eligible_set:
            continue           # already on buy shelf
        _sv = sig_verdict.get(_t)
        if _sv and _sv.get("eligible"):
            continue           # gate-eligible -> not RIPENING
        _lci2 = _last_cross_info(_t)
        if _lci2:
            continue           # recent cross -> rule-3 RAN_LATE territory, not RIPENING
        _ws = _wsetup_by.get(_t)
        if not _ws or not _ws.get("setup_live"):
            continue
        _w2 = _ws.get("w2") or {}
        _btc = _w2.get("macd_bars_to_cross")
        _stoch = _w2.get("stoch")
        # imminence sort key: MACD bars to cross ascending (closer = more imminent),
        # fallback = 999 (washout-only names sort after MACD-imminent names).
        _imminence = float(_btc) if _btc is not None else (
            float(_stoch) / 10.0 if _stoch is not None else 999.0)
        _ripening_rows.append({
            "ticker": _t, "name": _name_w or _t, "sector": _sector_w or "",
            "reasons": _ws.get("setup_reasons") or [],
            "imminence": _btc,            # macd_bars_to_cross; None for washout-only
            "w2_stoch": _stoch,
            "w2_macd_approaching": bool(_w2.get("macd_approaching_up")),
            "w2_macd_cross_up": bool(_w2.get("macd_cross_up")),
            "w1_cross_date": (_ws.get("w1_cross") or {}).get("cross_date"),
            "w1_d_at_cross": (_ws.get("w1_cross") or {}).get("d_at_cross"),
            "spot_pct_in_range": (_ws.get("base") or {}).get("spot_pct_in_range"),
            "_sort_key": _imminence,
        })
    _ripening_rows.sort(key=lambda x: x.get("_sort_key") or 999)
    for _rr in _ripening_rows:
        _rr.pop("_sort_key", None)       # remove internal sort key before serialisation
    _ripening_rows = _ripening_rows[:24]

    # W2-B: attach narrative tags to RIPENING rows (display/ledger only — no rank change).
    # Stage is implicitly RIPENING for all rows in this array.
    for _rr in _ripening_rows:
        _rr_ticker = _rr.get("ticker")
        _rr_tag = _narr_tags.get(_rr_ticker) if _rr_ticker else None
        if _rr_tag:
            _rr["narrative"] = {
                "theme":    _rr_tag.get("theme"),
                "theme_zh": _rr_tag.get("theme_zh"),
                "basket_id": _rr_tag.get("basket_id"),
                "level":    _rr_tag.get("level"),
                "rel20":    _rr_tag.get("rel20"),
                "breadth":  _rr_tag.get("breadth"),
                "source":   _rr_tag.get("source"),
                "radar":    _rr_tag.get("radar"),
            }
        _rr["ab_tier"] = _narr_ab_tier("RIPENING", _rr_tag)

    # (6) Build-time INVARIANTS — fail loudly, stop the build so bugs are never silently shipped.
    _n_missing_stage = sum(1 for r in eligible_rows if "stage" not in r)
    assert _n_missing_stage == 0, (
        f"W1-B invariant FAILED: {_n_missing_stage} buy rows are missing the 'stage' field. "
        "Every buy row must have a stage (ENTRY, RAN_LATE, or None).")
    # RENDER-LEVEL invariants (replacing the old input-level assert that crashed on
    # buy_now+overextended — a LEGITIMATE combination per adjudicated design F6):
    #   (i)  Every rule-2 RAN_LATE row has a sublabel.
    #   (ii) Every rule-2 RAN_LATE row has stage=RAN_LATE.
    #  (iii) Rule-2 rows with buy_now/partial entry_status have muted_entry=True
    #        (so the template suppresses green banding — render-level guard, not input filter).
    _r2_rows = [r for r in eligible_rows if r.get("stage") == STAGE_RAN_LATE]
    _r2_no_sublabel = [r.get("ticker") for r in _r2_rows if not r.get("stage_sublabel")]
    assert not _r2_no_sublabel, (
        f"W1-B invariant FAILED: rule-2 RAN_LATE rows must have a sublabel. "
        f"Violation: {_r2_no_sublabel}")
    _r2_muted_missing = [
        r.get("ticker") for r in _r2_rows
        if (entry_sig.get(r.get("ticker")) or {}).get("status") in ("buy_now", "partial")
        and not r.get("muted_entry")
    ]
    assert not _r2_muted_missing, (
        f"W1-B invariant FAILED: rule-2 rows with buy_now/partial entry status must have "
        f"muted_entry=True (render-level guard). Violation: {_r2_muted_missing}")
    _elig_set_check = {r.get("ticker") for r in eligible_rows}
    _rip_bad = [r["ticker"] for r in _ripening_rows if r["ticker"] in _elig_set_check]
    assert not _rip_bad, (
        f"W1-B invariant FAILED: ripening rows must never be gate-eligible. "
        f"Violation: {_rip_bad}")
    assert len(_ripening_rows) <= 24, (
        f"W1-B invariant FAILED: ripening cap 24 exceeded ({len(_ripening_rows)})")
    assert len(_ran_rows) <= 15, (
        f"W1-B invariant FAILED: ran cap 15 exceeded ({len(_ran_rows)})")
    _n_entry = sum(1 for r in eligible_rows if r.get("stage") == STAGE_ENTRY)
    _n_ran_late = sum(1 for r in eligible_rows if r.get("stage") == STAGE_RAN_LATE)
    log.info("W1-B stage partition: %d ENTRY + %d RAN_LATE + %d no-shelf (buy rows); "
             "%d RIPENING + %d RAN (non-buy universe)",
             _n_entry, _n_ran_late, len(eligible_rows) - _n_entry - _n_ran_late,
             len(_ripening_rows), len(_ran_rows))

    if cand:
        as_of = (alpha or {}).get("as_of")
        # laggards watch-strip: weakest residual-alpha names, independent of the buy gate.
        laggards = dedupe_dual_class(sorted(
            (r for _s, r in cand if r.get("alpha") is not None),
            key=lambda r: r["alpha"]))[:12]
        for r in eligible_rows:
            r["align_tier"] = _atier(r.get("ticker"))        # context chip only (shown if aligned/near)
            r["signal"] = signal_gate.compact(sig_verdict.get(r.get("ticker")))
            # COILED wave-3 CN chip: attach assess() dict when the name qualifies as coiled or
            # at least has a washout_ctx signal (same pattern as US build_stock_library.py).
            _t = r.get("ticker")
            cb = coiled_by.get(_t)
            if cb and (cb.get("coiled") or cb.get("washout_ctx")):
                r["coiled"] = cb
        setups = {"as_of": as_of, "rank_by": "confluence",
                  "buy": eligible_rows[:110], "laggards": laggards}
        (site / "factordata" / "china_setups.json").write_text(
            json.dumps(setups, separators=(",", ":"), default=str))
        # WIDE "Standout individual stocks" board — same confluence gate; each row carries the
        # unified Conviction profile + entry/risk gauges so the card renders fully. eligible =
        # the confluence-eligible count; universe = the scored candidate count.
        wide = {"as_of": as_of, "rank_by": "confluence",
                "buy": list(eligible_rows[:110]), "laggards": laggards}
        for r in wide["buy"] + wide["laggards"]:
            t = r.get("ticker")
            r["conviction"] = profiles.get(t)
            r["signal"] = signal_gate.compact(sig_verdict.get(t))   # confluence T1->T4 tier badge
            if entry_sig.get(t):
                r["entry_signal"] = entry_sig[t]     # the entry-timing gauge for the card
            if risk_sig.get(t):
                r["risk_sizing"] = risk_sig[t]       # the vol-managed sizing for the card / bot
            if quality_badge.get(t):
                r["quality"] = quality_badge[t]      # fundamental-quality chip (DISPLAY only, not sort)
            r.update({k: v for k, v in (disp_map.get(t) or {}).items() if v is not None})
            # additive per-row data_through: the ACTUAL last data date for this name, distinct from
            # the board as_of (a name pulled a session behind the board reads as stale downstream).
            # ADDITIVE field only — never renames as_of; the Mastermind bot consumes this contract.
            _dt = _name_data_through(t)
            if _dt:
                r["data_through"] = _dt
            # W0.1 HOLD: attach basing-state to standout rows (display chip + ledger column)
            # (mirrors US build_stock_library.py:L1788-1791; display/ledger only, not a rank input)
            _hd_cn = _hold_state_cn.get(t)
            if _hd_cn is not None:
                r["hold"] = _hd_cn
            # W0.10 SECTOR FIRST-TICK-UP: attach sector_turn to the row when the name's
            # Yahoo-inferred Shenwan L1 sector is in first-tick-up state (Trough + osc_slope>0).
            # DISPLAY/LEDGER ONLY — never touches _cn_bonus or blend_sorted.
            # approx:true is propagated from the taxonomy map (Yahoo GICS ≠ Shenwan L1 exactly).
            _row_sector = r.get("sector") or ""
            _sw_match = _YAHOO_TO_SW.get(_row_sector)
            if _sw_match and _sw_match in _sector_turn_by_sw:
                r["sector_turn"] = _sector_turn_by_sw[_sw_match]
            # W2-B NARRATIVE TAGS: attach per-name theme heat + radar join + A/B tier.
            # DISPLAY/LEDGER ONLY — narrative NEVER affects _cn_bonus, blend_sorted, or admission.
            # ab_tier is None for RAN_LATE rows (spec law: ENTRY/RIPENING only).
            _nb_tag = _narr_tags.get(t) if t else None
            if _nb_tag:
                r["narrative"] = {
                    "theme":    _nb_tag.get("theme"),
                    "theme_zh": _nb_tag.get("theme_zh"),
                    "basket_id": _nb_tag.get("basket_id"),
                    "level":    _nb_tag.get("level"),
                    "rel20":    _nb_tag.get("rel20"),
                    "breadth":  _nb_tag.get("breadth"),
                    "source":   _nb_tag.get("source"),
                    "radar":    _nb_tag.get("radar"),
                }
            _nb_stage = r.get("stage")
            r["ab_tier"] = _narr_ab_tier(_nb_stage, _nb_tag)
        # W2-B order-invariance assertion: buy order must be unchanged by narrative tagging.
        # Narrative is display/ledger only — it must never alter the ranked order.
        _buy_tickers_pre  = [r.get("ticker") for r in eligible_rows[:110]]
        _buy_tickers_post = [r.get("ticker") for r in wide["buy"]]
        assert _buy_tickers_pre == _buy_tickers_post, (
            "W2-B invariant FAILED: narrative tags altered the buy row order. "
            f"Pre: {_buy_tickers_pre[:5]} ... Post: {_buy_tickers_post[:5]}")
        wide["eligible"] = len(eligible_rows)
        wide["universe"] = len(cand)
        wide["quality_screen"] = {           # honest report of what the screen actually did
            "adv_floor_yi": china_liquidity.ADV_FLOOR_YI, "mcap_floor_yi": MCAP_FLOOR_YI,
            "dropped": dict(screen_drop), "n_extended_demoted": _n_ext,
            "note": ("ST/*ST/退 excluded; suspended/delisted (stale >15d) excluded; names below the "
                     "dollar-ADV tradability floor excluded (only when provably illiquid); already-"
                     "extended names DEMOTED, not hidden (see the 'extended' badge). Market-cap is "
                     "defense-in-depth only — the source field is ~46% placeholder, so ADV + staleness "
                     "do the real weeding."),
        }
        if disp_regime:                      # selection-regime gross dial (board context)
            wide["dispersion_regime"] = disp_regime
        if qvix_reg:                         # the market vol-regime banner (GEX-analog for A-shares)
            wide["qvix_regime"] = qvix_reg
        # board-ORDER forward ledger (keystone): log today's ranked top-N so the BOARD earns trust
        # (the per-name grader does not observe blend_sorted order). grade() is "accruing" until
        # forward returns mature. This is the honest prerequisite for a hard extension veto.
        # LEDGER-INTEGRITY GATES (CN-1 §W6-CN), replacing the keep-first accident:
        #   • asia-lane gate: CN_LANE env selects the lane. Only the asia collection lane (which
        #     commits data/) persists; render lanes pass a non-asia lane and are refused. Default
        #     'asia' keeps the current call correct (the asia build is the only one that commits).
        #   • partial-session refusal: a board whose price panel was collected before the A-share
        #     close settled (<07:00 UTC on the board date) is refused — no mid-session partial board.
        #   • coverage metadata: stamp the panel collection UTC + partial_session onto the artifact.
        try:
            _lane = os.environ.get("CN_LANE", "asia")
            _sess = china_standout_track.session_status(as_of)
            wide["coverage"] = {
                "as_of": as_of, "data_through": _data_through(),
                "panel_collected_utc": _sess.get("collected_utc"),
                "panel_collected_hour_utc": _sess.get("collected_hour_utc"),
                "partial_session": bool(_sess.get("partial_session")),
                "session_note": _sess.get("reason"), "lane": _lane,
            }
            _bn = china_standout_track.append_board(wide["buy"], asof=as_of, lane=_lane)
            _bt = china_standout_track.grade()
            if _bt.get("available"):
                wide["board_track"] = _bt
                setups["board_track"] = _bt
            setups["coverage"] = wide["coverage"]
            log.info("china standout board-track: logged top-%d (ledger=%d, graded=%s, lane=%s, partial=%s)",
                     min(60, len(wide["buy"])), _bn, _bt.get("n_graded"), _lane,
                     wide["coverage"]["partial_session"])
        except Exception as e:  # noqa: BLE001 — telemetry, never fatal
            log.warning("china standout board-track failed (%s)", e)
        # Validated sleeve-size chip (W6-CN Fix 1) — thread the risk_radar_intl gross_factor
        # into the board header as a DISPLAY chip. Regime sizes sleeves, never vetoes names.
        # Passport: basis=measured, validation=cn_forward_log.jsonl (the repo's only closed loop).
        try:
            from engine.risk_radar_intl import cn_sleeve_chip
            wide["sleeve_chip"] = cn_sleeve_chip()
            log.info("china stocks sleeve chip: %s", wide["sleeve_chip"].get("label_en"))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("china stocks sleeve chip failed (%s)", e)
        # W0.7 BOARD-WIDTH GUARD: read the previous artifact's buy-count; if the new count dropped
        # >40% day-over-day, stamp data_outage and log a WARNING — never publish a silently collapsed
        # board as if it were a normal render (git history shows n=110→42→11→110 across 06-25..06-30).
        # The banner is rendered by the template when data_outage.flag is true.
        _standouts_path = site / "factordata" / "china_standouts.json"
        _prev_buy_n: int | None = None
        try:
            if _standouts_path.exists():
                _prev = json.loads(_standouts_path.read_text())
                _prev_buy_n = len(_prev.get("buy") or [])
        except Exception:  # noqa: BLE001 — guard must never block the write
            pass
        _new_buy_n = len(wide["buy"])
        if _prev_buy_n is not None and _prev_buy_n > 0:
            _drop_frac = (_prev_buy_n - _new_buy_n) / _prev_buy_n
            if _drop_frac > 0.40:
                wide["data_outage"] = {
                    "flag": True,
                    "prev_n": _prev_buy_n,
                    "new_n": _new_buy_n,
                    "drop_pct": round(_drop_frac * 100, 1),
                    "reason": (f"buy-count collapsed {_prev_buy_n}→{_new_buy_n} "
                               f"({_drop_frac*100:.0f}% drop, threshold 40%). "
                               "Probable cause: data gap / collector outage. "
                               "Board is INCOMPLETE — treat with caution."),
                }
                log.warning("W0.7 board-width guard: buy-count collapsed %d→%d (%.0f%% drop) — "
                            "stamping data_outage; banner will render",
                            _prev_buy_n, _new_buy_n, _drop_frac * 100)
        # W1-B: attach RIPENING + RAN arrays to the artifact (new keys; buy unchanged).
        # Downstream consumers of `buy` keep working untouched — these are additive arrays.
        wide["ripening"] = _ripening_rows
        wide["ran"] = _ran_rows
        setups["ripening"] = _ripening_rows
        setups["ran"] = _ran_rows
        # W1-B ledger: log ripening set to data/china_standout_track/ripening.parquet
        # (compact append: ticker, reasons, imminence, w2_stoch — W6 conversion grading).
        try:
            _rip_lane = os.environ.get("CN_LANE", "asia")
            _rn = china_standout_track.append_ripening(
                _ripening_rows, asof=as_of, lane=_rip_lane)
            log.info("W1-B ripening ledger: appended %d names this run (total ledger rows=%d)",
                     len(_ripening_rows), _rn)
        except Exception as _re:  # noqa: BLE001 — ledger is additive, never fatal
            log.warning("W1-B ripening ledger failed (%s)", _re)
        _standouts_path.write_text(
            json.dumps(wide, separators=(",", ":"), default=str))
        log.info("wrote china_standouts.json (%d buy [%d ENTRY/%d RAN_LATE] / %d RIPENING / %d RAN"
                 " / %d eligible / %d universe)",
                 len(wide["buy"]), _n_entry, _n_ran_late,
                 len(_ripening_rows), len(_ran_rows),
                 len(eligible_rows), len(cand))
    log.info("china library: %d analyzed, %d skipped (thin history), %d setups",
             built, failed, len(cand))
    return setups


if __name__ == "__main__":
    main()
    sys.exit(0)
