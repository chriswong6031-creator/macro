"""Build the searchable stock-analysis library (site/stockdata/*.json).

Architecture note: this is a static site — no server, so search cannot hit a
live API. Instead, everything the breadth collector already downloads nightly
(all S&P 500 constituents) plus every stored ETF/stock/commodity/crypto gets
run through the SAME cycle/ladder engine as the sector pages, and each result
is written as a small JSON the search page fetches client-side. Instant
results, no keys, no rate limits; coverage = the library universe, refreshed
nightly. site/stockdata/ is gitignored — regenerated at build time and shipped
only inside the Pages artifact.

Usage: python -m scripts.build_stock_library
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

from engine import ticker_alerts  # noqa: E402
from engine.conditions import sector_macro_beta  # noqa: E402
from engine.cycles import analyze, market_vix_context  # noqa: E402
from engine.extension import extension_signals  # noqa: E402
from engine.playbook import SECTOR_NAMES  # noqa: E402
from engine.setups import US_ALPHA_WEIGHT, rank_setups, setup_score, sue_confirmer  # noqa: E402
from engine import stock_score  # noqa: E402
from engine import stock_macro_sensitivity as macro_sens  # noqa: E402
from engine import dannytrades_chip as dt_chip  # noqa: E402
from engine.stock_fundamentals import panels as fundamental_panels  # noqa: E402
from engine.technicals import season_line, seasonality, snapshot  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("stock_library")

ETF_LABELS = {**SECTOR_NAMES,
              "SPY": "S&P 500 ETF", "QQQ": "Nasdaq-100 ETF", "IWM": "Russell 2000 ETF",
              "SMH": "Semiconductors ETF", "RSP": "Equal-Weight S&P ETF",
              "HYG": "High-Yield Bond ETF", "LQD": "IG Corporate Bond ETF",
              "GC=F": "Gold", "CL=F": "Crude Oil (WTI)", "HG=F": "Copper",
              "SI=F": "Silver", "BZ=F": "Brent Crude", "DX-Y.NYB": "US Dollar Index",
              "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "SOL-USD": "Solana"}


def current_liquidity() -> str | None:
    """The live US net-liquidity regime ("expanding"/"contracting"/"neutral")
    the engine last classified (regime/latest.json `liquidity_overlay`). Threaded
    into analyze() as the orthogonal macro conviction modifier on buy setups;
    None when unavailable so the ladder simply omits the liquidity context."""
    p = config.data_dir() / "regime" / "latest.json"
    if not p.exists():
        return None
    try:
        liq = json.loads(p.read_text()).get("liquidity_overlay")
    except Exception:  # noqa: BLE001
        return None
    return liq if liq in ("expanding", "contracting", "neutral") else None


def current_macro() -> float | None:
    """The live aggregate macro-risk score (MRS, 0..1) the engine last computed
    (regime/latest.json `macro_risk.score`). Threaded into analyze() as the
    risk-OFF conviction modifier on buy setups (scaled per name by its sector
    sensitivity); None when unavailable so the ladder omits the macro context."""
    p = config.data_dir() / "regime" / "latest.json"
    if not p.exists():
        return None
    try:
        v = (json.loads(p.read_text()).get("macro_risk") or {}).get("score")
    except Exception:  # noqa: BLE001
        return None
    return float(v) if isinstance(v, (int, float)) else None


OPTIONABLE_GEX = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD",
                  "NFLX", "AVGO", "CRM", "ORCL", "ADBE", "QCOM", "MU", "INTC",
                  "PLTR", "COIN", "SMCI", "MRVL", "JPM", "BAC", "XOM", "WMT", "LLY"]


def _optionable_gex() -> dict:
    """Per-stock dealer-gamma summary for the liquid optionable subset (DISPLAY-ONLY,
    never in the score -- gated by scripts/validate_gex.py). Best-effort; failures skip.
    A vol-regime + levels map, not directional (see LIMITATIONS.md)."""
    try:
        from collectors.cboe import GexAdapter
        from engine.gex_engine import compute_gex
    except Exception:  # noqa: BLE001
        return {}
    adapter = GexAdapter(); gcfg = adapter.cfg.get("gex", {})
    ecfg = {k: gcfg[k] for k in ("contract_multiplier", "pct_move",
                                 "strike_window_pct", "max_expiry_days") if k in gcfg}
    out: dict = {}
    for t in OPTIONABLE_GEX:
        try:
            chain, spot = adapter._chain(t)
            summ = compute_gex(chain, spot, cfg={**ecfg, "r": gcfg.get("r", 0.043), "q": 0.0})
            if summ.get("tier") not in (None, "no_options"):
                out[t] = summ
        except Exception as e:  # noqa: BLE001
            log.debug("per-stock gex %s skipped: %s", t, e)
    log.info("per-stock GEX: %d/%d optionable names", len(out), len(OPTIONABLE_GEX))
    return out


def current_vix_context() -> dict | None:
    """Live market panic/washout context from VIX (percentile, panic, fading),
    computed once and threaded into analyze() for the Phase-2 washout knife-risk
    temper on Bottom Confidence. None when VIX is unavailable."""
    p = config.data_dir() / "yahoo" / "_VIX.parquet"
    if not p.exists():
        return None
    try:
        vctx = market_vix_context(pd.read_parquet(p)["close"])
    except Exception:  # noqa: BLE001
        return None
    return vctx or None


def current_risk_overlay() -> dict:
    """Macro/event STRESS read for the standout board's risk overlay (engine.stock_score's
    subtract-only tax + verb veto on a CHASE into a stressed tape). Blends the live VIX
    percentile + regime/latest.json risk leaves (drawdown_risk, systemic_stress, turning
    point). Each component is ELEVATED-ONLY (0 until it crosses a genuinely-stressed
    threshold), so a calm week (this one: VIX ~16/29th pct) returns stress ~0 and the overlay
    is silent. Returns {stress in [0,1], drivers, vix_pct}."""
    out = {"stress": 0.0, "drivers": []}

    def _elev(x, lo, hi):
        return None if x is None else max(0.0, min(1.0, (float(x) - lo) / (hi - lo)))
    try:
        d = json.loads((config.data_dir() / "regime" / "latest.json").read_text())
        cond = d.get("conditions") or {}
        tp = d.get("turning_point") or {}
        comps = {}
        vp = config.data_dir() / "yahoo" / "_VIX.parquet"
        vix_pct = None
        if vp.exists():
            v = pd.read_parquet(vp)["close"]
            vix_pct = float((v <= v.iloc[-1]).tail(252).mean())
            comps["vix"] = _elev(vix_pct, 0.55, 0.90)             # only above the 55th pct
        comps["drawdown"] = _elev((cond.get("drawdown_risk") or {}).get("score"), 25, 60)
        comps["systemic"] = _elev((cond.get("systemic_stress") or {}).get("ofr_fsi_pctile"), 0.60, 0.95)
        # imminent KNOWN MACRO event (FOMC) — a board-wide binary risk window. Within ~1d -> 0.7,
        # ~3d -> 0.5, so T3's macro tax + verb veto fire into a Fed week even if VIX is still calm.
        try:
            import datetime as _dt
            from engine.catalyst_tone import _FOMC_MEETINGS
            today = _dt.date.today()
            fut = sorted(d for d in (_dt.date.fromisoformat(x) for x in _FOMC_MEETINGS) if d >= today)
            if fut:
                dd_ev = (fut[0] - today).days
                comps["fomc"] = 0.7 if dd_ev <= 1 else 0.5 if dd_ev <= 3 else 0.0
        except Exception:  # noqa: BLE001
            pass
        present = {k: c for k, c in comps.items() if c is not None}
        tp_force = 1.0 if tp.get("active") else (0.6 if tp.get("raw_fire") else 0.0)
        # any single GENUINELY-elevated risk signal (each already elevated-only) lifts stress;
        # an active turning point dominates. Calm tape => all components 0 => stress 0.
        stress = max([tp_force] + list(present.values())) if (present or tp_force) else 0.0
        drivers = [k for k, c in present.items() if c > 0.3]
        if tp_force >= 0.6:
            drivers.append("turning point")
        out = {"stress": round(float(stress), 3), "drivers": drivers, "vix_pct": vix_pct}
    except Exception as e:  # noqa: BLE001 — additive; absence => no tax
        log.warning("risk overlay read failed (%s) — standouts run without the macro tax", e)
    return out


def current_calm(bench: pd.Series | None) -> float | None:
    """The live `calm` regime score in [0,1] the Conviction EDGE axis uses to scale the
    residual-momentum leg (engine.stock_score._edge_weights). This is the SAME causal
    price-tape regime validated in scripts.conviction_v2_regime — trend (SPY vs its 200dma)
    AND realized-vol (trailing 63d vs its 1y median) — so the live tilt matches the backtest.
    Returns {0, 0.5, 1.0}: both calm -> 1 (momentum up-weighted), one -> 0.5, both stress ->
    0 (momentum pulled back, the SUE event edge leads). None when SPY history is too short."""
    if bench is None or len(bench) < 220:
        return None
    c = pd.to_numeric(bench, errors="coerce").dropna()
    if len(c) < 220:
        return None
    sma200 = c.rolling(200).mean()
    trend_up = bool(c.iloc[-1] >= sma200.iloc[-1])
    rvol = c.pct_change().rolling(63).std()
    rvol_med = rvol.rolling(252, min_periods=120).median()
    lo_vol = bool(rvol.iloc[-1] <= rvol_med.iloc[-1]) if pd.notna(rvol_med.iloc[-1]) else trend_up
    return 0.5 * float(trend_up) + 0.5 * float(lo_vol)


def sue_freshness_days(asof: pd.Timestamp | None = None) -> dict[str, float]:
    """Per-ticker days since its most recent EDGAR EPS filing became visible — feeds the
    Conviction EDGE axis's PEAD freshness decay (engine.stock_score._pead_decay), so a fresh
    earnings surprise outranks a stale one and the score reacts the moment earnings land.
    Empty dict when the panel is unavailable (decay then no-ops to 1.0). Best-effort.

    CAVEAT: the EPS panel's `asof_date` is a SYNTHETIC period_end + 60d (collectors.edgar_eps
    does not carry the real filing date), so freshness here is really 'days since fiscal-
    quarter-end + 60'. It still spreads names across the drift window over the calendar (the
    backtest validated it on the same field over 213 monthly rebalances), but right after an
    earnings wave most names cluster at one value. A real EDGAR submissions-API filing date
    would sharpen this — tracked as a follow-up."""
    try:
        from engine import sue as _sue
        panel = _sue.load_panel()
    except Exception:  # noqa: BLE001
        return {}
    if panel is None or panel.empty:
        return {}
    now = pd.Timestamp(asof) if asof is not None else pd.Timestamp.now().normalize()
    sub = panel[panel["asof_date"] <= now]
    if sub.empty:
        return {}
    latest = sub.groupby("ticker")["asof_date"].max()
    return {t: float((now - d).days) for t, d in latest.items() if pd.notna(d)}


def _limited_rec(ticker: str, c: pd.Series, name: str, sector: str) -> dict:
    """A minimal, honest record for a curated extra too new for the cycle model
    (a days-old IPO). Carries enough for search + the page's renderLimited
    branch: identity, listing date, session count, and the LIMITED sentinel
    state (the page keys off `limited` before ever reading the ladder)."""
    return {
        "ticker": ticker, "name": name, "sector": sector,
        "asof": str(c.index.max().date()),
        "listed": str(c.index.min().date()),
        "history_days": int(len(c)),
        "limited": True,
        "ladder": {"state": "LIMITED"},
    }


def _one(ticker: str, close: pd.Series, high: pd.Series | None,
         name: str, sector: str, liquidity: str | None = None,
         macro_drag: float | None = None, macro_beta: float = 0.0,
         bench: pd.Series | None = None, alert_days: int = 120,
         alert_max: int = 50, vix_ctx: dict | None = None,
         min_days: int = 300, allow_limited: bool = False,
         macro_frame=None, ant_gate: dict | None = None,
         breadth: pd.Series | None = None,
         name_dir_inputs: dict | None = None) -> dict | None:
    c = close.dropna()
    # The cycle ladder itself needs ~260 sessions (engine/cycles), so 300 is a
    # conservative margin for the broad library. Curated single-stock extras
    # (recent IPOs / ADRs) pass a lower floor so a fresh listing becomes
    # searchable the moment its ladder is computable, not ~2 months later — the
    # empty-ladder guard below still gates anything the engine can't yet read.
    # A brand-new listing (e.g. a days-old IPO like SPCX) has no computable
    # ladder at all; for curated extras we still emit a LIMITED record so the
    # name is searchable now (header + honest banner + live chart) rather than
    # invisible for ~a year — see _limited_rec / the page's renderLimited.
    if len(c) < min_days:
        return _limited_rec(ticker, c, name, sector) if allow_limited else None
    # crypto trades 7 days/week — its cycle clock runs longer in calendar days
    # than an equity's, so it gets the crypto cycle preset (Yahoo crypto tickers
    # carry the -USD suffix: BTC-USD, ETH-USD, SOL-USD …).
    kind = "crypto" if ticker.endswith("-USD") else "equity"
    # US net-liquidity is a single macro regime that applies to every US-listed
    # name — and to crypto (BTC tracks it) — so the same live label conditions all.
    res = analyze(c, high, kind=kind, liquidity=liquidity,
                  macro_drag=macro_drag, macro_beta=macro_beta, vix_ctx=vix_ctx)
    if not res.get("ladder"):
        return _limited_rec(ticker, c, name, sector) if allow_limited else None
    month = int(c.index.max().month)
    seas = seasonality(c)
    asof = str(c.index.max().date())
    rec = {
        "ticker": ticker, "name": name, "sector": sector,
        "asof": asof,
        "history_days": int(len(c)),
        "tech": snapshot(c),
        "season_this": season_line(seas, month),
        "season_next": season_line(seas, month % 12 + 1),
        "season_this_zh": season_line(seas, month, zh=True),
        "season_next_zh": season_line(seas, month % 12 + 1, zh=True),
        **res,
    }
    # per-ticker alert feed: a backfilled technical signal-change timeline with
    # the ladder's standing read pinned on top (embedded so the client page,
    # which fetches this JSON, renders it with no extra request). The ladder log
    # is flushed once in main(), not per ticker.
    rec["alerts"] = ticker_alerts.compact_feed(ticker_alerts.build_feed(
        ticker, c, high, bench, res.get("ladder"), asof,
        days=alert_days, max_events=alert_max))
    # multi-horizon anticipation cone (DISPLAY-ONLY risk read; only GO legs score, and
    # only for us_equity — crypto gets no scored gate until its own per-class Phase-0).
    try:
        from engine import anticipation as _antic
        a = _antic.anticipate(c, high, bench=bench, breadth=breadth, asset=ticker,
                              asset_class=("crypto" if kind == "crypto" else "us_equity"),
                              macro_frame=macro_frame, gate=(ant_gate if kind == "equity" else {}),
                              name_dir_inputs=(name_dir_inputs if kind == "equity" else None))
        if a:
            rec["anticipation"] = a
    except Exception:  # noqa: BLE001 — additive; one cone error must not drop the name
        pass
    return rec


def universe() -> list[tuple[str, pd.Series, pd.Series | None, str, str]]:
    """(ticker, close, high|None, name, sector) for everything analyzable."""
    out: list[tuple] = []
    seen: set[str] = set()

    # deep-history holdings stocks (preferred over breadth's 3y window)
    d = config.data_dir() / "stocks"
    names: dict[str, tuple[str, str]] = {}
    hd = config.data_dir() / "sector_holdings"
    if hd.exists():
        for p in hd.glob("*.parquet"):
            fund = p.stem
            try:
                df = pd.read_parquet(p)
            except Exception as e:  # noqa: BLE001 — one corrupt parquet must not 404 the library
                log.warning("sector_holdings %s unreadable (%s) — skipped", p.name, e)
                continue
            if "ticker" not in df.columns:  # e.g. the holdings_runs summary
                continue
            for _, r in df.iterrows():
                names[str(r["ticker"]).replace(".", "-")] = (
                    str(r.get("name", "")).title(), SECTOR_NAMES.get(fund, fund))
    if d.exists():
        for p in sorted(d.glob("*.parquet")):
            t = p.stem
            try:
                df = pd.read_parquet(p)
            except Exception as e:  # noqa: BLE001
                log.warning("stocks %s unreadable (%s) — skipped", p.name, e)
                continue
            nm, sec = names.get(t, (t, ""))
            out.append((t, df["close"], df.get("high"), nm, sec))
            seen.add(t)

    # Index constituents from the breadth close caches (~3y window each). The
    # S&P 500 + 400 + 600 together form the S&P Composite 1500 — ~1500 unique
    # liquid US names, the practical "all US equities" search set (S&P 600 also
    # serves as the free Russell 2000 small-cap proxy). Order is priority: a
    # ticker is taken from the first cache that carries it, and data/stocks deep
    # history above already won the ~110 holdings names.
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        cache = config.data_dir() / grp / "_closes_cache.parquet"
        cons = config.data_dir() / grp / "constituents.parquet"
        if not (cache.exists() and cons.exists()):
            log.warning("%s close cache missing — those constituents skipped", grp)
            continue
        try:
            closes = pd.read_parquet(cache)
            meta = pd.read_parquet(cons)
        except Exception as e:  # noqa: BLE001 — corrupt restored cache must not crash build_site
            log.warning("%s cache unreadable (%s) — those constituents skipped", grp, e)
            continue
        added = 0
        for t in closes.columns:
            if t in seen or t not in meta.index:
                continue
            out.append((t, closes[t], None,
                        str(meta.loc[t, "name"]), str(meta.loc[t, "sector"])))
            seen.add(t)
            added += 1
        log.info("stock library universe: +%d from %s", added, grp)

    # ETFs / commodities / crypto from the yahoo store, then the searchable
    # single-stock extras (foreign ADRs + recent IPOs outside the S&P 1500).
    ycfg = config.load()["yahoo"]["tickers"]
    etfs = (ycfg["sectors"] + ycfg["extras"] + ycfg.get("factors", [])
            + ycfg.get("credit", []) + ycfg.get("fx_commod", [])
            + ycfg.get("crypto", []))
    scfg = config.load().get("stock_search", {})
    extra_names = scfg.get("extra_names", {}) or {}
    for t in etfs + (scfg.get("extra_tickers", []) or []):
        if t in seen or t.startswith("^"):
            continue
        df = store.read("yahoo", t)
        if df is None:
            continue
        lbl = extra_names.get(t)
        if lbl:  # a real single stock: show the company name + its GICS sector
            out.append((t, df["close"], df.get("high"),
                        str(lbl.get("name", t)), str(lbl.get("sector", ""))))
        else:    # an ETF / macro proxy
            out.append((t, df["close"], None, ETF_LABELS.get(t, t), "ETF / macro"))
        seen.add(t)
    return out


# ---- parallel per-ticker analysis (the build's single heaviest stretch) ------
# _one() is dominated by engine.cycles.analyze and is GIL-bound, but every ticker
# is independent (its JSON is written serially in main()), so the universe is
# fanned across processes. These helpers are module-level so spawned workers can
# import them; the shared read-only context is installed once per worker via the
# pool initializer.
_SHARED: dict = {}


def _library_workers() -> int:
    """Process-pool size for the per-ticker fan-out. Precedence: STOCK_LIB_WORKERS
    env var (ops knob; set 1 to force the serial path) > config stock_search.workers
    > the runner's CPU count. Capped at 8 so we don't oversubscribe pandas' BLAS
    threads."""
    n = os.environ.get("STOCK_LIB_WORKERS") or None
    if n is None:
        n = config.load().get("stock_search", {}).get("workers")
    if n is None:
        n = os.cpu_count() or 1
    return max(1, min(int(n), 8))


# Lower history floor for curated extras (recent IPOs / ADRs) — one trading
# year. The empty-ladder guard in _one still governs, so this just trims the
# conservative 300-session margin for the names we hand-pick to be searchable.
EXTRAS_MIN_DAYS = 252


def _winit(liq, drag, bench, a_days, a_max, vctx, extras=frozenset(),
           macro_frame=None, ant_gate=None, breadth=None, name_dir_inputs=None) -> None:
    _SHARED.update(liquidity=liq, macro_drag=drag, bench=bench,
                   alert_days=a_days, alert_max=a_max, vix_ctx=vctx, extras=extras,
                   macro_frame=macro_frame, ant_gate=ant_gate, breadth=breadth,
                   name_dir_inputs=name_dir_inputs)


def _one_task(item):
    """Worker: one ticker's library record (or None). Reads the shared context
    installed by _winit; mirrors the original inline call and its
    one-bad-ticker-can't-kill-the-library guard."""
    ticker, close, high, name, sector = item
    try:
        extras = _SHARED.get("extras") or frozenset()
        is_extra = ticker in extras
        min_days = EXTRAS_MIN_DAYS if is_extra else 300
        return _one(ticker, close, high, name, sector,
                    liquidity=_SHARED.get("liquidity"), macro_drag=_SHARED.get("macro_drag"),
                    macro_beta=sector_macro_beta(sector), bench=_SHARED.get("bench"),
                    alert_days=_SHARED.get("alert_days", 120),
                    alert_max=_SHARED.get("alert_max", 50), vix_ctx=_SHARED.get("vix_ctx"),
                    min_days=min_days, allow_limited=is_extra,
                    macro_frame=_SHARED.get("macro_frame"), ant_gate=_SHARED.get("ant_gate"),
                    breadth=_SHARED.get("breadth"), name_dir_inputs=_SHARED.get("name_dir_inputs"))
    except Exception as e:  # noqa: BLE001 — one bad ticker must not kill the library
        log.debug("library %s failed: %s", ticker, e)
        return None


def _spark_svg(vals, color: str = "var(--link)", w: int = 240, h: int = 42) -> str:
    """Tiny theme-aware inline sparkline (area + line + last dot) for the standout
    cards — same shape as build_china_library._spark_svg / build_site._mini_svg."""
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


_SPARK_COLOR = {"up": "var(--up)", "down": "var(--down)", "caution": "var(--warn)"}


def _basket_tailwind_map() -> dict[str, dict]:
    """Per-ticker thematic-basket TAILWIND for the Conviction "upside" axis (§2 Axis
    C): the strongest theme a name belongs to, scored by that basket's 20d return
    vs the benchmark. Best-effort — any failure yields {} and the axis is simply
    absent (the engine never reads a missing leg as neutral)."""
    out: dict[str, dict] = {}
    try:
        from engine import baskets
        data = baskets.compute_baskets() or {}
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
        log.warning("basket tailwind map unavailable (%s)", e)
    return out


def _basket_membership_map() -> dict[str, list[dict]]:
    """All active thematic basket memberships per ticker — for the detail page.
    Reads membership.json (no live performance data needed). Returns
    {ticker: [{"slug", "name", "name_zh", "category", "theme", "rationale"}]}.
    Display-only — never touches any score."""
    out: dict[str, list[dict]] = {}
    try:
        mf = config.data_dir() / "baskets" / "membership.json"
        if not mf.exists():
            return out
        data = json.loads(mf.read_text())
        for slug, b in (data.get("baskets") or {}).items():
            for m in (b.get("members") or []):
                tick = m.get("ticker")
                if not tick or m.get("removed"):
                    continue
                out.setdefault(tick, []).append({
                    "slug": slug,
                    "name": b.get("name", ""),
                    "name_zh": b.get("name_zh", ""),
                    "category": b.get("category", ""),
                    "theme": b.get("theme", ""),
                    "rationale": m.get("rationale", ""),
                })
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("basket membership map unavailable (%s)", e)
    return out


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    outdir = site / "stockdata"
    outdir.mkdir(parents=True, exist_ok=True)

    liq = current_liquidity()
    drag = current_macro()
    vctx = current_vix_context()
    log.info("net-liquidity regime for library: %s · macro-risk: %s · VIX: %s",
             liq or "unknown", "—" if drag is None else f"{drag:.2f}", vctx or "n/a")
    # benchmark for per-ticker relative-strength alerts + the feed window/caps
    spy = store.read("yahoo", "SPY")
    bench = spy["close"] if spy is not None else None
    # live calm/risk-on regime score (validated price tape) — scales the Conviction EDGE
    # axis's residual-momentum leg up in calm tape, back toward zero in stress.
    calm = current_calm(bench)
    asof_now = bench.index.max() if bench is not None and len(bench) else None
    sue_fresh = sue_freshness_days(asof_now)   # PEAD freshness per name (days since filing)
    risk_overlay = current_risk_overlay()      # macro/event stress tax on a chase (T3)
    # forward EARNINGS calendar (T7): days-until-next-report per name -> binary-event size-down.
    import datetime as _dt
    _earn_cal, _today = {}, _dt.date.today()
    try:
        from engine.stock_fundamentals import _load_earnings
        _earn_cal = _load_earnings()
    except Exception as e:  # noqa: BLE001 — additive; absence => no earnings gate
        log.warning("earnings calendar unavailable (%s)", e)

    def _edays(t):
        nd = (_earn_cal.get(t) or {}).get("next_date")
        if not nd:
            return None
        try:
            dlt = (_dt.date.fromisoformat(str(nd)[:10]) - _today).days
            return float(dlt) if 0 <= dlt <= 60 else None
        except Exception:  # noqa: BLE001
            return None
    log.info("conviction regime: calm=%s · SUE freshness %d · macro stress=%.2f %s · earnings cal %d names",
             "n/a" if calm is None else f"{calm:.2f}", len(sue_fresh),
             risk_overlay.get("stress", 0.0), risk_overlay.get("drivers") or "",
             sum(1 for t in _earn_cal if _edays(t) is not None))
    acfg = config.load().get("alerts", {})
    a_days = int(acfg.get("ticker_timeline_days", 120))
    a_max = int(acfg.get("ticker_max_events", 50))
    ladder_rows: list[dict] = []
    # Phase-2 (research/STOCK_FUNDAMENTALS_PLAN.md): drip a capped batch of
    # per-stock profiles (SEC identity + Wikipedia descriptions) into
    # data/profile/ each build — resumable + capped so it never hammers SEC/
    # Wikipedia or stalls the build, and quiet once the universe is covered.
    try:
        from collectors.equity_profile import fetch_profiles
        cap = config.load().get("equity_profile", {}).get("per_build", 80)
        fetch_profiles(max_new=cap)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("equity_profile drip skipped (%s)", e)
    # Fundamental panels (factor fingerprint, trailing valuation, financials,
    # positioning) assembled once from already-collected data and merged per name.
    # Best-effort: a failure here must never 404 the technical library.
    try:
        fpanels = fundamental_panels()
    except Exception as e:  # noqa: BLE001
        log.warning("fundamental panels unavailable (%s) — library ships technicals only", e)
        fpanels = {}
    # institutional flow per stock: which thematic/active funds are accumulating
    # or trimming each name (written by build_site.build_etf_page just before this
    # runs, so the per-stock page can show it). Additive — absent => no panel.
    flows: dict[str, list] = {}
    ff = outdir / "fund_flows.json"
    if ff.exists():
        try:
            flows = json.loads(ff.read_text())
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("fund_flows.json unreadable (%s)", e)
    # sector-neutral residual-alpha per-ticker scores (written by build_site.
    # build_alpha_data just before this runs). Additive — absent => no panel.
    alpha_pt: dict[str, dict] = {}
    alpha_asof = None
    ap = site / "factordata" / "alpha.json"
    if ap.exists():
        try:
            _aj = json.loads(ap.read_text()) or {}
            alpha_pt = _aj.get("per_ticker", {})
            alpha_asof = _aj.get("as_of")
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("alpha.json unreadable (%s)", e)
    # confirmer legs for the Top-setups board: the factor composite (factors.json
    # table) as a LIGHT tiebreaker + insider BUY clusters (insider_signals.json) + the
    # validated SUE earnings-momentum z (factors.json table 'sue') — all written by
    # build_site just before this runs. Additive — absent => no chip. DISPLAY context
    # only; the factor breaks ties in rank_setups, insider/SUE never touch the order.
    factor_z: dict[str, float] = {}
    sue_z: dict[str, float] = {}
    insider_map: dict[str, dict] = {}
    fp = site / "factordata" / "factors.json"
    if fp.exists():
        try:
            for _r in (json.loads(fp.read_text()) or {}).get("table", []):
                if not _r.get("ticker"):
                    continue
                if _r.get("composite") is not None:
                    factor_z[_r["ticker"]] = _r["composite"]
                if _r.get("sue") is not None:
                    sue_z[_r["ticker"]] = _r["sue"]
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("factors.json unreadable (%s)", e)
    isp = site / "factordata" / "insider_signals.json"
    if isp.exists():
        try:
            insider_map = json.loads(isp.read_text()) or {}
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("insider_signals.json unreadable (%s)", e)
    # curated super-investor 13F holdings per stock (written by build_site.
    # build_smartmoney_data just before this runs). Additive — absent => no panel.
    smart_money: dict[str, dict] = {}
    smp = site / "factordata" / "smartmoney.json"
    if smp.exists():
        try:
            smart_money = (json.loads(smp.read_text()) or {}).get("by_ticker", {})
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("smartmoney.json unreadable (%s)", e)
    # per-stock dealer-gamma (DISPLAY-ONLY, gated from the score by validate_gex)
    gex_by_ticker = _optionable_gex()
    # contrarian crowding/fragility flags (DISPLAY-ONLY, gated OUT of the score by
    # scripts/fund_crowding_phase0.py — short interest has no PIT history to validate).
    # Computed once over the whole panel; graceful (absent feed => {} => no chip).
    from engine.crowding import compute_fragility
    fragility_map = compute_fragility()
    basket_tw = _basket_tailwind_map()          # Conviction "upside / theme tailwind" axis
    bsk_mem = _basket_membership_map()          # all active basket memberships (display-only)
    # per-stock Macro-sensitivity context (rate-beta tier + duration + live-regime
    # head/tailwind + inflation label) — reads factor_betas.json (written by build_site
    # just before this) + data/transmission/latest.json (the Rate & Inflation Transmission
    # foundation). DISPLAY-ONLY, never scored; absent files => no chip. (engine/
    # stock_macro_sensitivity.py)
    try:
        macro_sens_ctx = macro_sens.load_context(site)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("macro-sensitivity context unavailable (%s)", e)
        macro_sens_ctx = None
    # Phase-0 gate: the board rank stays the VALIDATED leg unless a deep-CI run proved
    # the composite beats it (scripts/stock_conviction_phase0.py). Absent / shallow =>
    # NEUTRAL => gate_go False => Conviction ships as display-only context.
    gate_go = False
    _gate = config.data_dir() / "regime" / "stock_conviction_gate.json"
    if _gate.exists():
        try:
            gate_go = (json.loads(_gate.read_text()) or {}).get("US") == "GO"
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("stock_conviction_gate.json unreadable (%s)", e)
    # analyst estimate-REVISION momentum — the fast/early EDGE leg. Drip a capped batch each
    # build (resumable, never fatal), then read the latest readings into a cross-sectional z.
    try:
        from collectors.equity_revisions import fetch_revisions
        fetch_revisions(max_new=int(config.load().get("equity_profile", {}).get("per_build", 200)))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("revision drip skipped (%s)", e)
    revision_z: dict[str, float] = {}
    _rp = config.data_dir() / "revisions" / "latest.parquet"
    if _rp.exists():
        try:
            _rv = pd.read_parquet(_rp)
            raw = {}
            for t, r in _rv.iterrows():
                b = r.get("breadth"); e = r.get("est_chg_30d")
                xs = [x for x in (b, (max(-15, min(15, e)) / 10.0 if e is not None and e == e else None))
                      if x is not None and x == x]
                if xs:
                    raw[t] = float(sum(xs) / len(xs))
            if len(raw) >= 5:
                s = pd.Series(raw); mu, sd = s.mean(), s.std(ddof=0) or 1.0
                revision_z = ((s - mu) / sd).clip(-3, 3).round(3).to_dict()
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("revisions latest.parquet unreadable (%s)", e)
    log.info("revision-momentum: %d names with a cross-sectional z%s", len(revision_z),
             " · GATE GO → board ranks by EDGE" if gate_go else "")
    index, cand, built, failed = [], [], 0, 0
    # Conviction profiles (engine/stock_score) per name + the deferred per-stock JSON
    # writes — deferred so the display score can be the WITHIN-MARKET percentile of the
    # composite z (set once all names are profiled), not a per-name logistic skin.
    profiles: dict[str, dict] = {}
    disp_map: dict[str, dict] = {}              # price / off-high / sparkline per name
    to_write: list[tuple[str, dict]] = []
    uni = universe()
    # extension / exhaustion read over the WHOLE library universe (own-history ext_z +
    # grade), wired in EXACTLY as build_discovery does — this is what re-arms the validated
    # parabolic/stretched penalty in stock_score._axis_entry that was dead on this board
    # (every standout previously carried ext=None, so a +35%-over-200dma chase got no brake).
    ext_map, lottery_map = {}, {}
    try:
        _ext_closes = pd.concat({t: c for (t, c, *_rest) in uni}, axis=1).sort_index()
        ext_map = extension_signals(_ext_closes)
        # recent single-day MAX return % over the last 21d — the lottery/spike penalty (T5):
        # a top name with a radioactive one-day pop (>~18%) has a NEGATIVE fwd median + ~2x DD.
        lottery_map = (_ext_closes.pct_change().tail(21).max() * 100.0).round(2).to_dict()
        log.info("extension read on %d names (%d parabolic, %d stretched) · lottery on %d",
                 len(ext_map), sum(1 for v in ext_map.values() if v.get("grade") == "parabolic"),
                 sum(1 for v in ext_map.values() if v.get("grade") == "stretched"), len(lottery_map))
    except Exception as e:  # noqa: BLE001 — additive; absence just means no extension brake
        log.warning("extension/lottery read failed (%s) — standouts run without the brakes", e)
    # Heaviest stretch of the whole site build: ~1500 independent _one() calls.
    # Fan them across processes (CI runner = 4 vCPU); the cheap post-processing
    # below (shared-map merges, setup scoring, JSON writes) stays serial and in
    # universe() order, so the output is byte-identical to the serial build.
    # Graceful: any pool error — or workers<=1 — drops back to the serial path.
    extra_set = frozenset(
        config.load().get("stock_search", {}).get("extra_tickers", []) or [])
    # anticipation cone inputs (shared, read-only): the validated macro overlay frame +
    # Phase-0 gate + market breadth — built ONCE and installed into every worker (pickled
    # at pool init, not per task). The cone rides this heavy parallel stretch for ~free.
    try:
        from engine import anticipation as _antic
        _amf = _antic.macro_legs_frame()
        ant_macro = None if (_amf is None or _amf.empty) else _amf
        ant_gate = _antic.load_gate("US")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("anticipation overlay unavailable (%s)", e)
        ant_macro, ant_gate = None, None
    try:
        ant_breadth = pd.read_parquet(config.data_dir() / "breadth" / "breadth.parquet")["pct_above_200"]
    except Exception:  # noqa: BLE001
        ant_breadth = None
    # single-name macro-transmission lean (NAME_DIRECTION): build the shared rate inputs ONCE
    # — but ONLY when the Phase-0 gate has a scored horizon. Single-name real-rate transmission
    # is currently a validated NULL (research/NAME_DIRECTION_PHASE0.md), so this stays None and
    # the per-name beta pass is skipped entirely → ZERO added cost on the daily critical path.
    name_dir_inputs = None
    try:
        from engine import anticipation as _antic2, name_direction as _nd
        nd_gate = _antic2.name_direction_gate()
        if _antic2.name_direction_scored(nd_gate):
            ri = _nd.rate_inputs(bench)
            if ri is not None:
                # cross-sectional mean duration prior (latest) for the live Vasicek shrink
                dur_prior = 0.0  # conservative default; refined when the channel ever scores
                name_dir_inputs = {"inputs": ri, "gate": nd_gate, "dur_prior": dur_prior}
                log.info("NAME_DIRECTION active — single-name macro lean enabled")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("name-direction inputs unavailable (%s)", e)
    _winit(liq, drag, bench, a_days, a_max, vctx, extra_set,
           ant_macro, ant_gate, ant_breadth, name_dir_inputs)  # also primes the serial path
    workers = _library_workers()
    recs: list[dict | None] | None = None
    if workers > 1 and len(uni) > 50:
        try:
            from concurrent.futures import ProcessPoolExecutor
            t0 = time.time()
            with ProcessPoolExecutor(max_workers=workers, initializer=_winit,
                                     initargs=(liq, drag, bench, a_days, a_max, vctx, extra_set,
                                               ant_macro, ant_gate, ant_breadth)) as ex:
                recs = list(ex.map(_one_task, uni, chunksize=8))
            log.info("stock library: analysed %d names in %.0fs (%d processes)",
                     len(uni), time.time() - t0, workers)
        except Exception as e:  # noqa: BLE001 — parallelism must never break the build
            log.warning("parallel library build failed (%s) — serial fallback", e)
            recs = None
    if recs is None:
        t0 = time.time()
        recs = [_one_task(item) for item in uni]
        log.info("stock library: analysed %d names in %.0fs (serial)", len(uni), time.time() - t0)

    for (ticker, close, high, name, sector), rec in zip(uni, recs):
        if rec is None:
            failed += 1
            continue
        if fpanels.get(ticker):
            rec.update(fpanels[ticker])
        if flows.get(ticker):
            rec["fund_flows"] = flows[ticker]
        if alpha_pt.get(ticker):            # additive: absent => no alpha/setup for this name
            rec["alpha"] = alpha_pt[ticker]
            sc = setup_score(rec, alpha_weight=US_ALPHA_WEIGHT)
            if sc:
                row = sc[1]
                row["factor_z"] = factor_z.get(ticker)      # tiebreaker in rank_setups + display
                ins = insider_map.get(ticker) or {}
                if ins.get("buyers", 0) >= 2 and (ins.get("net_mn") or 0) > 0:
                    row["insider_buyers"] = ins.get("buyers")
                    row["insider_bps"] = ins.get("bps")
                    row["insider_net_mn"] = ins.get("net_mn")
                sconf = sue_confirmer(sue_z.get(ticker))    # earnings-momentum confirmer (display only)
                if sconf is not None:
                    row["sue_z"] = sconf
                cand.append(sc)
        if smart_money.get(ticker):
            rec["smart_money"] = smart_money[ticker]
        if gex_by_ticker.get(ticker):
            rec["gex"] = gex_by_ticker[ticker]
        if fragility_map.get(ticker):
            rec["fragility"] = fragility_map[ticker]
        if bsk_mem.get(ticker):
            rec["baskets_membership"] = bsk_mem[ticker]
        # ---- unified Conviction Profile (engine/stock_score) -----------------
        # The single block both the dashboard standout card AND this name's detail page
        # render, so the two can never structurally disagree. v2: the EDGE = the VALIDATED
        # event core (SUE + insider + analyst-revisions), residual momentum a light context;
        # the cycle state is a HARD verb modifier (a downtrend caps entry + forbids a Buy verb).
        ins = insider_map.get(ticker) or {}
        ins_bps = ins.get("bps") if (ins.get("buyers", 0) >= 2 and (ins.get("net_mn") or 0) > 0) else None
        if ext_map.get(ticker):
            rec["ext"] = ext_map[ticker]            # re-arms the parabolic/stretched entry brake
        norm = stock_score.normalize_rec(
            rec, "US", sue=sue_z.get(ticker), sue_fresh_days=sue_fresh.get(ticker),
            insider_bps=ins_bps, revision_z=revision_z.get(ticker), basket=basket_tw.get(ticker),
            lottery_max=lottery_map.get(ticker), earnings_days=_edays(ticker))
        prof = stock_score.conviction_profile(
            norm, "US", ctx={"as_of": alpha_asof, "gate_go": gate_go,
                             "regime": {"calm": calm}, "risk_overlay": risk_overlay})
        rec["conviction"] = prof
        # 4H intraday available? (Polygon hourly store -> site/intraday/<T>.json). stock.html
        # passes this to the chart so the 4H button only appears where data actually exists.
        rec["has_intraday"] = 1 if (config.data_dir() / "intraday" / f"{ticker}.parquet").exists() else 0
        profiles[ticker] = prof
        # ---- Macro sensitivity (display-only, never scored) -------------------
        # rate-beta tier + duration bucket + live-regime head/tailwind + inflation
        # label. Uses the archetype merged from fpanels above + the shared context.
        if macro_sens_ctx is not None:
            try:
                arche_key = ((rec.get("profile") or {}).get("archetype") or {}).get("key")
                ms = macro_sens.assess(ticker, sector, arche_key, macro_sens_ctx,
                                       sector_macro_beta_val=sector_macro_beta(sector))
                if ms:
                    rec["macro_sensitivity"] = ms
            except Exception as e:  # noqa: BLE001 — additive, never fatal
                log.warning("macro-sensitivity for %s failed (%s)", ticker, e)
        # ---- DannyTrades CONTRARIAN read (display-only) -----------------------
        # extension flag (decile Spearman −0.88) + whale-fade; needs full OHLCV+volume
        # (data/stocks names only — others silently skip). See research/DANNYTRADES_PHASE0.md.
        try:
            _ohlcv = store.read("stocks", ticker)
            if _ohlcv is not None and {"low", "volume"} <= set(_ohlcv.columns):
                dtc = dt_chip.assess(_ohlcv["close"], _ohlcv.get("high"),
                                     _ohlcv.get("low"), _ohlcv.get("volume"))
                if dtc:
                    rec["dt_contra"] = dtc
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("dt-contra for %s failed (%s)", ticker, e)
        _tech = rec.get("tech") or {}
        disp_map[ticker] = {
            "price": _tech.get("price"), "off_high": _tech.get("off_52w_high_pct"),
            "spark_svg": _spark_svg(list(close.tail(64).values),
                                    color=_SPARK_COLOR.get((rec.get("ladder") or {}).get("dir"), "var(--link)"))}
        ladder_rows.append(ticker_alerts.ladder_row(ticker, rec.get("ladder"), rec.get("asof")))
        safe = ticker.replace("=", "_").replace("^", "_")
        to_write.append((safe, rec))            # deferred: write after percentile scoring
        idx = {"t": ticker, "n": name, "s": sector, "st": rec["ladder"]["state"]}
        if rec.get("alpha", {}).get("alpha") is not None:
            idx["a"] = rec["alpha"]["alpha"]          # alpha-z in the index for client ranking
        index.append(idx)
        built += 1
    # within-market percentile display score (mutates the conviction blocks in place;
    # rec['conviction'] is the SAME object, so the per-stock JSONs pick it up below).
    stock_score.attach_panel_scores(profiles)
    for safe, rec in to_write:
        (outdir / f"{safe}.json").write_text(json.dumps(rec, default=str))
    # flush the accruing ladder-transition log in one idempotent, atomic write
    try:
        added = ticker_alerts.write_ladder_log_batch(ladder_rows)
        log.info("ladder log: +%d new transitions", added)
    except Exception as e:  # noqa: BLE001 — the log is additive, never fatal
        log.warning("ladder log flush skipped (%s)", e)
    (outdir / "index.json").write_text(json.dumps(index))
    cal = config.data_dir() / "regime" / "ladder_calibration.json"
    if cal.exists():
        (outdir / "calibration.json").write_text(cal.read_text())
    # cross-sectional "Top setups" — selection (sector-neutral residual alpha) ×
    # timing (cycle entry + reversal overlay), surfaced on the macro dashboard's
    # "Standout individual stocks" board (read by build_site one build later, since
    # build_library runs at the END of build_site). Buys = strong-alpha leaders on a
    # constructive entry; laggards = weak alpha. Mirrors build_china_library.
    if cand:
        # rank by the validated alpha leg, NOT the blended setup score: Phase-0
        # (reports/setup-score-phase0.md) found the cycle-timing/reversal blend does
        # not improve forward-return ranking on the US panel — it dilutes alpha — so
        # the board rides the positive-IC leg and shows the timing as entry context.
        setups = rank_setups(cand, as_of=alpha_asof, rank_by="alpha")
        (site / "factordata").mkdir(parents=True, exist_ok=True)
        (site / "factordata" / "setups.json").write_text(
            json.dumps(setups, separators=(",", ":"), default=str))
        log.info("wrote setups.json (%d buy, %d laggards, %d candidates)",
                 len(setups["buy"]), len(setups["laggards"]), len(cand))
        # WIDE "Standout individual stocks" board (the bench the user sees, ~80-120).
        # v2: when the deep-PIT gate is GO (the validated EVENT edge beats the momentum
        # baseline), rank the board by the holistic Conviction composite (EDGE-dominant);
        # otherwise keep the validated residual-alpha rank. Either way each card carries
        # the full Conviction profile/verdict + per-leg basis.
        # Rank the board by the holistic multi-factor Conviction composite (a DISPLAY
        # ordering that integrates the validated event EDGE + entry timing + quality +
        # tailwind — surfacing the event-edge names the alpha-only rank would bury). This
        # is NOT claimed as a validated standalone alpha: the deep-PIT gate found nothing
        # cleanly beats noise at this horizon (residual momentum ALSO fails DSR), so the
        # per-card trust tier + α chip + per-leg basis show exactly what is validated vs
        # context. `gate_go` (currently NEUTRAL) would flip the trust tier to 'validated'.
        row_by_t = {r.get("ticker"): r for _, r in cand}
        scored = [(t, p) for t, p in profiles.items()
                  if p.get("composite_z") is not None and t in row_by_t]
        scored.sort(key=lambda kv: -(kv[1]["composite_z"]))
        # ENTRY-QUALITY GATE (China's discipline, T4-validated: poor-entry top-momentum names
        # realize -0.7pp/mo and a -58% vs -41% worst drawdown). A name is BUYABLE only if its
        # cycle/extension does NOT block (downtrend / parabolic / over-extended chase like CASY)
        # AND its entry is constructive (entry_z > 0; an ABSENT entry is not "poor", so it
        # stays). Strong-but-not-buyable names go to a WATCH list ("leaders — wait for a
        # pullback") so they are surfaced honestly, never sold as buys.
        def _buyable(p):
            if p.get("cycle_blocked"):
                return False
            ez = ((p.get("axes") or {}).get("entry") or {}).get("z")
            return ez is None or ez > 0
        buyable = [(t, p) for t, p in scored if _buyable(p)]
        watch = [(t, p) for t, p in scored
                 if not _buyable(p) and (p.get("composite_z") or 0) > 0]
        wide = {"as_of": alpha_asof, "rank_by": ("edge-validated" if gate_go else "conviction"),
                "gate_go": gate_go,
                "buy": [row_by_t[t] for t, _ in buyable[:120]],
                "watch": [row_by_t[t] for t, _ in watch[:24]],
                "laggards": [row_by_t[t] for t, _ in scored[-12:][::-1]] if len(scored) > 24 else []}
        eligible = sum(1 for _, p in buyable if (p.get("composite_z") or 0) > 0)
        for r in wide["buy"] + wide["watch"] + wide["laggards"]:
            t = r.get("ticker")
            r["conviction"] = profiles.get(t)
            r.update({k: v for k, v in (disp_map.get(t) or {}).items() if v is not None})
        wide["eligible"] = eligible
        wide["universe"] = len(cand)
        (site / "factordata" / "us_standouts.json").write_text(
            json.dumps(wide, separators=(",", ":"), default=str))
        log.info("wrote us_standouts.json (%d buy · rank_by=%s · %d eligible / %d universe)",
                 len(wide["buy"]), wide["rank_by"], eligible, len(cand))
    # multi-timeframe Bottom-Confidence per-band held-rate (stock.html shows the
    # measured "this band held the low ~N%" line; see research/BOTTOM_CONFIDENCE.md)
    bccal = config.data_dir() / "regime" / "bottom_confidence_calibration.json"
    if bccal.exists():
        (outdir / "bc_calibration.json").write_text(bccal.read_text())
    log.info("stock library: %d analyzed, %d skipped (thin history)", built, failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
