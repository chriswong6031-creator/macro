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

import bisect
import json
import math
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import ticker_alerts  # noqa: E402
from engine import signal_gate  # noqa: E402 — owner's confluence T1->T4 cascade (layered ON main's gate)
from engine.conditions import sector_macro_beta  # noqa: E402
from engine.cycles import analyze, market_vix_context  # noqa: E402
from engine.extension import extension_signals  # noqa: E402
from engine.playbook import SECTOR_NAMES  # noqa: E402
from engine.setups import (  # noqa: E402
    ALIGN_MIN_KEEP, US_ALPHA_WEIGHT, entry_open_first, rank_setups, setup_score,
    sue_confirmer)
from engine import stock_score  # noqa: E402
from engine import name_score  # noqa: E402  — per-name POTENTIAL (buy-readiness) score, edge-blended
from engine import name_score_grader  # noqa: E402  — forward-grades the POTENTIAL score
from engine import entry_signal  # noqa: E402
from engine import risk_sizing  # noqa: E402 — vol-managed inverse-vol sizing (the validated Sharpe lever)
from engine import dispersion  # noqa: E402 — cross-sectional dispersion regime (selection-gross dial)
from engine import stock_view  # noqa: E402
from engine import stock_macro_sensitivity as macro_sens  # noqa: E402
from engine import pullback_zone  # noqa: E402
from engine import dannytrades_chip as dt_chip  # noqa: E402
from engine import stock_technicals  # noqa: E402  — richer OHLCV-aware technical snapshot
from engine import vol_squeeze  # noqa: E402  — single-stock volatility black hole
from engine import gex_confirm  # noqa: E402  — dealer-gamma verifier/confirmer
from engine import options_ivspread  # noqa: E402  — Cremers-Weinbaum call−put IV-spread confirmer
from engine import demand_chain as dchain  # noqa: E402
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


def current_vol_regime() -> dict | None:
    """The live INDEX vol-regime snapshot (engine.vol_regime -> site/vol/regime.json, mirrored
    to regime/latest.json['vol_regime']). Threaded into analyze() as a UNIFORM, subtract-only
    sizing caution on buy setups when the regime is a risk-off kill-switch state. None when
    unavailable so the ladder simply omits the vol-regime context (behaviour unchanged)."""
    try:
        from engine import vol_regime
        snap = vol_regime.published_snapshot()
        return snap or None
    except Exception:  # noqa: BLE001 — additive context, never fatal
        return None


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


def _load_gex_board(site: Path) -> dict:
    """The pre-built per-symbol dealer-gamma payloads (site/gex/<SYM>.json) — RICHER than the
    live compute_gex path: they carry call/put walls + the vol_hole state + consistent units,
    for the curated optionable universe. Read once; graceful (absent dir => {}). These feed the
    GEX verifier/confirmer (engine.gex_confirm) and enrich the per-stock gex chip."""
    out: dict = {}
    gdir = site / "gex"
    if not gdir.exists():
        return out
    for fp in gdir.glob("*.json"):
        sym = fp.stem
        if sym == "index":
            continue
        try:
            payload = json.loads(fp.read_text())
            if (payload.get("summary") or {}).get("tier") not in (None, "no_options"):
                out[sym] = payload
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.debug("gex board %s unreadable: %s", sym, e)
    log.info("GEX board: %d per-symbol payloads loaded for the confirmer", len(out))
    return out


def _flat_gex_from_board(payload: dict) -> dict:
    """A stock.html-compatible flat gex dict from the rich board payload. CRUCIAL: stock.html
    multiplies iv30 by 100 (expects a DECIMAL), but the board stores iv30 as a PERCENT — so we
    convert it back to decimal here (the iv30 unit-mismatch fix), and ADD the walls + vol_hole
    that the lighter compute_gex path never produced (never touching the keys stock.html reads)."""
    s = payload.get("summary") or {}
    iv = s.get("iv30")
    return {
        "gamma_regime": s.get("regime"), "regime": s.get("regime"),
        "net_gex_bn": s.get("net_gex_bn"),
        "gamma_flip": s.get("gamma_flip"), "dist_to_flip_pct": s.get("dist_to_flip_pct"),
        "iv30": (round(iv / 100.0, 4) if iv is not None else None),   # PERCENT -> DECIMAL
        "call_wall": s.get("call_wall"), "put_wall": s.get("put_wall"),
        # magnets + spot feed the Phase-3a posture/levels/pin narrative in stock.html.j2
        "magnet_up": s.get("magnet_up"), "magnet_down": s.get("magnet_down"),
        "spot": s.get("spot"),
        "tier": s.get("tier"), "n_strikes": s.get("n_strikes"),
        "rr_25d": s.get("rr_25d"),
        "vol_hole": payload.get("vol_hole"),
    }


def _next_monthly_opex_days() -> int | None:
    """Calendar days to the next monthly options expiry (3rd Friday) — feeds the GEX confirmer's
    pre-OPEX suppression (charm/vanna flows dominate the last 2 sessions)."""
    import datetime as _dt

    def third_friday(y: int, m: int) -> "_dt.date":
        d = _dt.date(y, m, 1)
        return d + _dt.timedelta(days=(4 - d.weekday()) % 7 + 14)
    today = _dt.date.today()
    tf = third_friday(today.year, today.month)
    if tf < today:
        ny, nm = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        tf = third_friday(ny, nm)
    return (tf - today).days


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
         name_dir_inputs: dict | None = None,
         vol_regime: dict | None = None) -> dict | None:
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
                  macro_drag=macro_drag, macro_beta=macro_beta, vix_ctx=vix_ctx,
                  vol_regime=vol_regime)
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


def _no_drip() -> bool:
    """True when RENDER_NO_DRIP=1 — set by the render-only lanes (render.yml /
    engine-render.yml). Those lanes commit site/ ONLY and DISCARD every data/ write,
    so the per-build SEC/Wikipedia drip fetches (equity_profile, edgar_rpo,
    edgar_headcount) below are pure wasted network there: the parquet/JSON they
    persist is thrown away, and the page still renders from the COMMITTED caches the
    nightly already advanced. Skipping them restores the lanes' "no network" invariant
    and removes ~3-4 min of rate-limited SEC fetching from every render. The nightly
    `daily` (which commits data/) leaves this unset, so the drip still advances there."""
    return os.environ.get("RENDER_NO_DRIP") == "1"


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
           macro_frame=None, ant_gate=None, breadth=None, name_dir_inputs=None,
           vol_regime=None) -> None:
    _SHARED.update(liquidity=liq, macro_drag=drag, bench=bench,
                   alert_days=a_days, alert_max=a_max, vix_ctx=vctx, extras=extras,
                   macro_frame=macro_frame, ant_gate=ant_gate, breadth=breadth,
                   name_dir_inputs=name_dir_inputs, vol_regime=vol_regime)


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
                    breadth=_SHARED.get("breadth"), name_dir_inputs=_SHARED.get("name_dir_inputs"),
                    vol_regime=_SHARED.get("vol_regime"))
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


def _json_safe(o):
    """Recursively replace non-finite floats (NaN/Inf) with None so the emitted JSON is
    RFC-compliant. Python's json writes a bare ``NaN`` token otherwise, which strict /
    JS (JSON.parse) consumers reject; here a stray NaN (e.g. a name's factor_z) used to
    leak into us_standouts.json. Pairs with allow_nan=False to also fail loudly if a
    non-finite slips through a non-float path."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    return o


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


def _spotlight_context() -> dict:
    """Heavy, once-per-build prep for the per-name SPOTLIGHT tilt: the live thematic-basket
    intel (engine.theme_scoring — score/label/reco per basket, keyed by slug) + the live
    sector playbook stage table (engine.playbook — stage/extended/RS-pctile per SPDR ETF).
    Recomputed in-process here (same pattern as _basket_tailwind_map) because build_baskets /
    build_allocation run AFTER this in the daily pipeline, so their JSON isn't on disk yet
    (~3s total — measured). Best-effort: either channel can be empty; the per-name blend
    simply skips a missing one (the engine never reads a missing leg as neutral)."""
    theme_by_id: dict[str, dict] = {}
    try:
        from engine import theme_scoring
        ti = theme_scoring.compute_theme_intel("us") or {}
        for t in (ti.get("themes") or []):
            if t.get("id"):
                theme_by_id[t["id"]] = t
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("spotlight theme intel unavailable (%s)", e)
    sector_by_etf: dict[str, dict] = {}
    try:
        from engine import playbook
        from engine.inputs import yahoo_closes
        st = playbook.stage_table(yahoo_closes())
        for etf, row in st.iterrows():
            pc = row.get("pctile_252d")
            sector_by_etf[etf] = {
                "stage": row.get("stage"), "extended": bool(row.get("extended")),
                "pctile_252d": float(pc) if pc is not None and pd.notna(pc) else None,
                "name": row.get("name")}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("spotlight sector stage table unavailable (%s)", e)
    alloc_by_id = _basket_alloc_map(theme_by_id)
    log.info("spotlight context: %d scored themes · %d sector stages · %d basket alloc states",
             len(theme_by_id), len(sector_by_etf), len(alloc_by_id))
    return {"theme_by_id": theme_by_id, "sector_by_etf": sector_by_etf,
            "alloc_by_id": alloc_by_id, "unmapped": set()}


def _basket_alloc_map(theme_by_id: dict) -> dict:
    """Per-basket ALLOCATION / absolute-trend-gate state, keyed by slug, for the VALIDATED
    scored de-risk (engine.stock_score._basket_risk). Recomputed in-process via
    engine.narrative_rotation so it never depends on allocation.json being on disk (the
    rotation/allocation build runs AFTER this in the pipeline). Merges the theme-scoring
    label/reco for context. Best-effort: {} if the rotation can't be built."""
    out: dict[str, dict] = {}
    try:
        from engine import narrative_rotation as nr
        rot = nr.compute_narrative_rotation("us") or {}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("basket alloc map unavailable (%s)", e)
        return out
    book = {w.get("id"): w
            for w in ((rot.get("allocation") or {}).get("weights") or [])}
    for r in (rot.get("ranks") or []):
        sid = r.get("id")
        if not sid:
            continue
        gate = r.get("gate") or {}
        dur = r.get("durability") or {}
        cr = r.get("crowding") or {}
        w = book.get(sid) or {}
        th = theme_by_id.get(sid) or {}
        out[sid] = {
            "rank": r.get("rank"), "score": r.get("score"),
            "eligible": bool(r.get("eligible")),
            "above_trend": bool(gate.get("above_200dma")),
            "ret_12m": gate.get("ret_12m"),
            "durability_bar": dur.get("bar"),
            "crowded": bool(w.get("crowded") if w else cr.get("crowded")),
            "book_wt": w.get("weight"),
            "label": th.get("label"), "reco": th.get("reco"),
            "name": th.get("name") or r.get("name"), "name_zh": th.get("name_zh"),
            "signal_grade": (th.get("signal_strength") or {}).get("grade"),
        }
    return out


def _spotlight_for(sector: str | None, memberships: list[dict] | None,
                   ctx: dict | None) -> dict | None:
    """Per-name spotlight tilt: the strongest theme (by |tilt|) the name belongs to, blended
    with its sector's playbook stage (GICS->ETF bridged). None when neither channel fires."""
    if not ctx:
        return None
    from engine import spotlight as _sp
    sec = (sector or "").strip()
    etf = _sp.GICS_TO_ETF.get(sec) if sec else None
    if sec and etf is None:
        ctx.setdefault("unmapped", set()).add(sec)
    sector_row = (ctx.get("sector_by_etf") or {}).get(etf) if etf else None
    return _sp.compute(memberships, ctx.get("theme_by_id") or {},
                       sector_etf=etf, sector_row=sector_row)


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    outdir = site / "stockdata"
    outdir.mkdir(parents=True, exist_ok=True)

    liq = current_liquidity()
    drag = current_macro()
    vctx = current_vix_context()
    vreg = current_vol_regime()
    log.info("net-liquidity regime for library: %s · macro-risk: %s · VIX: %s · vol-regime: %s",
             liq or "unknown", "—" if drag is None else f"{drag:.2f}", vctx or "n/a",
             (vreg or {}).get("regime") or "n/a")
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
        if _no_drip():
            log.info("equity_profile drip skipped (render lane — data/ write discarded)")
        else:
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
    _factor_legs: dict[str, dict] = {}          # per-ticker value/quality/profitability (composite)
    _sectors: dict[str, str] = {}               # for sector-neutral combination
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
                _factor_legs[_r["ticker"]] = {k: _r.get(k) for k in
                                              ("value", "quality", "profitability")}
                if _r.get("sector"):
                    _sectors[_r["ticker"]] = _r["sector"]
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
    # per-stock 13D/G beneficial-ownership regime (activist 13D + 13G→13D flip = signal;
    # custodian/index 13G = aggregation NOISE). Reads the sweep cache directly. CONTEXT.
    beneficial_ownership: dict[str, dict] = {}
    try:
        from engine.beneficial_ownership import load_regime
        beneficial_ownership = load_regime()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("beneficial_ownership regime unreadable (%s)", e)
    # per-stock dealer-gamma (DISPLAY-ONLY, gated from the score by validate_gex). PRIMARY =
    # the pre-built site/gex board payloads (rich: walls + vol_hole + consistent units), which
    # already cover the curated optionable universe. The live compute_gex path is only used as a
    # cold-start fallback when the board dir is entirely absent (a fresh checkout before the first
    # gex build) — it is skipped whenever the board has any payload, to avoid the slow Cboe fetch.
    gex_board = _load_gex_board(site)
    gex_by_ticker = _optionable_gex() if not gex_board else {}
    opex_days = _next_monthly_opex_days()
    # Cremers-Weinbaum call−put IV spread per optionable name (the one DIRECTIONAL options
    # confirmer we can build for $0 — no trade tape / NBBO signing needed). Computed once over
    # the freshest per-strike chain snapshot; graceful {} when the GEX chain store is absent.
    # DISPLAY-ONLY context until scripts/validate_options_ivspread earns a verdict.
    try:
        _ivs_chain = options_ivspread._latest_chain()
        ivspread_map = options_ivspread.ivspread_map(_ivs_chain) if _ivs_chain is not None else {}
        ivspread_prior = options_ivspread.prior_spread_map() if ivspread_map else {}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.debug("ivspread map skipped: %s", e)
        ivspread_map, ivspread_prior = {}, {}
    if ivspread_map:
        log.info("IV-spread confirmer: %d optionable names", len(ivspread_map))
    # contrarian crowding/fragility flags (DISPLAY-ONLY, gated OUT of the score by
    # scripts/fund_crowding_phase0.py — short interest has no PIT history to validate).
    # Computed once over the whole panel; graceful (absent feed => {} => no chip).
    from engine.crowding import compute_fragility
    fragility_map = compute_fragility()
    basket_tw = _basket_tailwind_map()          # Conviction "upside / theme tailwind" axis
    bsk_mem = _basket_membership_map()          # all active basket memberships (display-only)
    spotlight_ctx = _spotlight_context()        # theme intel + sector stage for the spotlight tilt
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
    # Alt-data per-stock chip (engine/altdata.py suite -> engine/altdata_signals.by_ticker).
    # DISPLAY-ONLY: politician/insider/contract/Trump flow convergence per name. Absent
    # file => no chip. Built by build_alt_data, which runs before build_site.
    try:
        from engine import altdata_signals as _altdata
        altdata_ctx = _altdata.load().get("tickers", {})
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("alt-data context unavailable (%s)", e)
        altdata_ctx = {}
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
    # raw analyst-revision fields, surfaced per-stock for the Demand Context panel (L1
    # "consensus"): these are collected but were previously distilled only into the
    # cross-sectional z below — the panel needs the unblended numbers to LABEL them as
    # already-priced. See memory demand-desk-divergence (Phase 0).
    revision_raw: dict[str, dict] = {}
    _rp = config.data_dir() / "revisions" / "latest.parquet"
    if _rp.exists():
        try:
            _rv = pd.read_parquet(_rp)

            def _rf(x):  # NaN/inf-safe float for the JSON payload, else None
                try:
                    x = float(x)
                except (TypeError, ValueError):
                    return None
                return x if x == x and x not in (float("inf"), float("-inf")) else None

            raw = {}
            for t, r in _rv.iterrows():
                b = r.get("breadth"); e = r.get("est_chg_30d")
                xs = [x for x in (b, (max(-15, min(15, e)) / 10.0 if e is not None and e == e else None))
                      if x is not None and x == x]
                if xs:
                    raw[t] = float(sum(xs) / len(xs))
                rr = {"breadth": _rf(b), "est_chg_30d": _rf(e), "est_chg_90d": _rf(r.get("est_chg_90d")),
                      "net_up_30d": _rf(r.get("net_up_30d")), "n_analysts": _rf(r.get("n_analysts"))}
                if any(v is not None for v in rr.values()):
                    revision_raw[str(t)] = rr
            if len(raw) >= 5:
                s = pd.Series(raw); mu, sd = s.mean(), s.std(ddof=0) or 1.0
                revision_z = ((s - mu) / sd).clip(-3, 3).round(3).to_dict()
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("revisions latest.parquet unreadable (%s)", e)
    log.info("revision-momentum: %d names with a cross-sectional z%s", len(revision_z),
             " · GATE GO → board ranks by EDGE" if gate_go else "")
    # ---- Decorrelated cross-sectional COMPOSITE (engine/composite_score) ----------
    # The Fundamental-Law lever: a sector-neutral, equal-weight blend of the DECORRELATED
    # return-predictive legs (momentum + value + quality + profitability + revisions). Our
    # probe measured these legs are near-uncorrelated (so they stack, ~1.42x single-leg IC).
    # A transparent CONTEXT score beside conviction — never a per-name verdict (cross-sectional
    # edge only). Reversal (net-of-cost mirage) + low-vol (a sizing lever) deliberately excluded.
    composite_pt: dict[str, dict] = {}
    try:
        from engine import composite_score
        _legrows = {}
        for _t in set(_factor_legs) | set(alpha_pt) | set(revision_z):
            _fl = _factor_legs.get(_t) or {}
            _legrows[_t] = {"momentum": (alpha_pt.get(_t) or {}).get("alpha"),
                            "value": _fl.get("value"), "quality": _fl.get("quality"),
                            "profitability": _fl.get("profitability"),
                            "revisions": revision_z.get(_t)}
        if _legrows:
            _comp = composite_score.build(pd.DataFrame(_legrows).T, _sectors)
            if not _comp.empty:
                for _t, _row in _comp.iterrows():
                    composite_pt[_t] = {"z": _row["composite"], "n_legs": int(_row["n_legs"]),
                                        "legs": {c[:-2]: round(float(_row[c]), 2)
                                                 for c in _comp.columns
                                                 if c.endswith("_z") and pd.notna(_row[c])}}
                log.info("decorrelated composite: %d names (mean %.1f legs)",
                         len(composite_pt), _comp["n_legs"].mean())
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("composite score failed (%s)", e)
    # Customer-demand chains (engine/demand_chain) — the L2 "independent observable"
    # leg of the Demand Context panel: aggregate spender capex/revenue from OTHER
    # companies' SEC filings is the forward-demand pool for each beneficiary cohort
    # (AI capex → semis/infra; homebuilder revenue → building products). Computed
    # ONCE here; attached per beneficiary name in the loop below. Display-only.
    demand_signals: dict[str, dict] = {}
    _sp = config.data_dir() / "edgar" / "statements.parquet"
    if _sp.exists():
        try:
            demand_signals = dchain.compute_signals(pd.read_parquet(_sp))
            for ck, sg in demand_signals.items():
                log.info("demand-chain[%s]: %s %+.0f%% YoY to ~$%.0fB (FY%d, n=%d)", ck,
                         sg["trend"], sg["yoy_pct"] or 0.0, sg["total_latest_bn"],
                         sg["fy_latest"], sg["n_spenders"])
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("demand-chain signals skipped (%s)", e)
    # RPO / contracted forward bookings (engine/demand_chain.rpo_read) — the per-name
    # L2 read for the software complex the capex chains don't reach. Used as a
    # fallback when a name is not on any customer-capex chain.
    rpo_by_ticker: dict[str, list[dict]] = {}
    try:                                        # drip RPO for the software universe (cached 25d; like revisions)
        from collectors.edgar_rpo import fetch_rpo
        if _no_drip():
            log.info("rpo drip skipped (render lane — data/ write discarded)")
        else:
            fetch_rpo()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("rpo drip skipped (%s)", e)
    _rpop = config.data_dir() / "edgar" / "rpo.parquet"
    if _rpop.exists():
        try:
            _rpo = pd.read_parquet(_rpop)
            for t, g in _rpo.groupby("ticker"):
                rpo_by_ticker[str(t)] = [{"fy": int(r.fy), "rpo": float(r.rpo),
                                          "revenue": (float(r.revenue) if r.revenue == r.revenue else None)}
                                         for r in g.itertuples()]
            log.info("demand-chain: RPO bookings for %d names", len(rpo_by_ticker))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("rpo.parquet unreadable (%s)", e)
    # Headcount / hiring (engine/demand_chain.hiring_read) — the per-name COINCIDENT
    # hiring-confidence read (10-K employee growth), the honest free stand-in for live
    # job postings. Last display fallback when a name is not on a chain and has no RPO.
    headcount_by_ticker: dict[str, list[dict]] = {}
    try:                                        # drip headcount (cached 90d; gentle SEC doc fetch)
        from collectors.edgar_headcount import fetch_headcount
        if _no_drip():
            log.info("headcount drip skipped (render lane — data/ write discarded)")
        else:
            fetch_headcount(max_new=10)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("headcount drip skipped (%s)", e)
    _hcp = config.data_dir() / "edgar" / "headcount.parquet"
    if _hcp.exists():
        try:
            _hc = pd.read_parquet(_hcp)
            for t, g in _hc.groupby("ticker"):
                headcount_by_ticker[str(t)] = [{"fy": int(r.fy), "employees": int(r.employees)}
                                               for r in g.itertuples()]
            log.info("demand-chain: headcount for %d names", len(headcount_by_ticker))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("headcount.parquet unreadable (%s)", e)
    # scored-ledger track record (engine/demand_ledger, prior build) for the panel's
    # accountability line; absent on first run — degrade silently.
    demand_track = None
    _dtr = config.data_dir() / "demand_chain" / "track_record.json"
    if _dtr.exists():
        try:
            demand_track = json.loads(_dtr.read_text())
        except Exception:  # noqa: BLE001
            demand_track = None
    demand_chip: dict[str, dict] = {}      # per-ticker actionable demand divergence → standout board chip
    index, cand, built, failed = [], [], 0, 0
    # Conviction profiles (engine/stock_score) per name + the deferred per-stock JSON
    # writes — deferred so the display score can be the WITHIN-MARKET percentile of the
    # composite z (set once all names are profiled), not a per-name logistic skin.
    profiles: dict[str, dict] = {}
    entry_sig: dict[str, dict] = {}             # entry-timing gauge per name (board rows)
    risk_sig: dict[str, dict] = {}              # vol-managed sizing per name (board rows)
    disp_map: dict[str, dict] = {}              # price / off-high / sparkline per name
    to_write: list[tuple[str, dict]] = []
    uni = universe()
    # extension / exhaustion read over the WHOLE library universe (own-history ext_z +
    # grade), wired in EXACTLY as build_discovery does — this is what re-arms the validated
    # parabolic/stretched penalty in stock_score._axis_entry that was dead on this board
    # (every standout previously carried ext=None, so a +35%-over-200dma chase got no brake).
    ext_map, lottery_map = {}, {}
    disp_regime, regime_gross = None, 1.0
    try:
        _ext_closes = pd.concat({t: c for (t, c, *_rest) in uni}, axis=1).sort_index()
        ext_map = extension_signals(_ext_closes)
        # cross-sectional DISPERSION regime — the dial for WHEN selection pays (high
        # dispersion => selection earns more => take more gross on the cross-sectional book).
        # Computed ONCE over the whole-universe return panel; feeds per-name vol-managed sizing.
        try:
            disp_regime = dispersion.assess(_ext_closes.pct_change(fill_method=None).tail(280))
            if disp_regime:
                regime_gross = disp_regime["gross_mult"]
                log.info("dispersion regime: %s (pctile %s, avg_corr %s) -> gross x%.2f",
                         disp_regime["state"], disp_regime.get("dispersion_pctile"),
                         disp_regime.get("avg_corr"), regime_gross)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("dispersion regime failed (%s)", e)
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
           ant_macro, ant_gate, ant_breadth, name_dir_inputs, vreg)  # also primes the serial path
    workers = _library_workers()
    recs: list[dict | None] | None = None
    if workers > 1 and len(uni) > 50:
        try:
            from concurrent.futures import ProcessPoolExecutor
            t0 = time.time()
            with ProcessPoolExecutor(max_workers=workers, initializer=_winit,
                                     initargs=(liq, drag, bench, a_days, a_max, vctx, extra_set,
                                               ant_macro, ant_gate, ant_breadth,
                                               name_dir_inputs, vreg)) as ex:
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

    sig_verdict: dict[str, dict] = {}   # owner's confluence cascade verdict per name (T1->T4)
    for (ticker, close, high, name, sector), rec in zip(uni, recs):
        if rec is None:
            failed += 1
            continue
        # COMBINE: the confluence T1->T4 cascade is computed alongside main's bottoming-alignment
        # gate. It NEVER changes which names are eligible (alignment stays the inclusion gate) —
        # it only adds the per-card tier badge and re-ranks WITHIN the aligned set (below).
        sig_verdict[ticker] = signal_gate.gate(ticker, close)
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
        if beneficial_ownership.get(ticker):
            rec["beneficial_ownership"] = beneficial_ownership[ticker]
        # ---- richer OHLCV technical snapshot + single-stock volatility black hole ------
        # Supersede the thin close-only snapshot with the research-vetted read (ATR/ADX/
        # squeeze/volume where full OHLCV exists; momentum / 52w-proximity / realized-vol
        # percentile everywhere). The OHLCV names also get the price-based vol-squeeze state.
        # Read store("stocks") ONCE here and reuse it for the DannyTrades chip below.
        # Graceful: any failure leaves the thin snapshot in place.
        _ohlcv = None
        try:
            _ohlcv = store.read("stocks", ticker)
            if _ohlcv is not None and {"high", "low", "volume"} <= set(_ohlcv.columns):
                rich = stock_technicals.snapshot(_ohlcv["close"], _ohlcv["high"],
                                                 _ohlcv["low"], _ohlcv["volume"], bench=bench)
                sq = vol_squeeze.assess(_ohlcv["close"], _ohlcv["high"],
                                        _ohlcv["low"], _ohlcv["volume"])
            else:
                rich = stock_technicals.snapshot(close, bench=bench)
                sq = vol_squeeze.assess(close)
            rec["tech"] = {**(rec.get("tech") or {}), **rich}
            if sq:
                rec["vol_squeeze"] = sq
        except Exception as e:  # noqa: BLE001 — additive; the thin snapshot is already on rec
            log.warning("tech/squeeze enrich for %s failed (%s)", ticker, e)
        # ---- dealer-gamma join (RICH board payload) + the GEX verifier/confirmer -------
        # Prefer the pre-built site/gex payload (call/put walls + vol_hole + correct units);
        # fall back to the live compute_gex summary. _flat_gex_from_board keeps stock.html's
        # gex chip working (and fixes the iv30 decimal/percent mismatch).
        _gp = gex_board.get(ticker)
        if _gp:
            rec["gex"] = _flat_gex_from_board(_gp)
            _gc = gex_confirm.assess(_gp, opex_days=opex_days)
            if _gc:
                rec["gex_confirm"] = _gc
        elif gex_by_ticker.get(ticker):
            rec["gex"] = gex_by_ticker[ticker]
            _gc = gex_confirm.assess(gex_by_ticker[ticker], opex_days=opex_days)
            if _gc:
                rec["gex_confirm"] = _gc
        # OPEX-pin caution chip in stock.html.j2 reads g.opex_days (calendar days to the
        # next monthly expiry — no feed). DISPLAY-ONLY, never in the score.
        if rec.get("gex") is not None and opex_days is not None:
            rec["gex"]["opex_days"] = opex_days
        # ---- IV-spread confirmer (Cremers-Weinbaum) — DIRECTIONAL options lean ----------
        # The directional companion to the gex confirmer: gex says HOW the next move behaves;
        # the IV spread says which way the options market is LEANING (calls richer = informed
        # bullish). Long confirmer (direction='up') matching how gex_confirm is wired here; it
        # can amplify or caution but never manufacture a buy, and stays display-only until the
        # forward-IC gate validates. None when the name has no/thin options.
        _ivs = ivspread_map.get(ticker)
        if _ivs:
            rec["iv_spread"] = _ivs
            _prior = ivspread_prior.get(ticker.upper())
            _cur = _ivs.get("ivspread")
            _chg = (round(float(_cur) - _prior, 5)
                    if _prior is not None and _cur is not None else None)
            _ic = options_ivspread.assess(_ivs, chg=_chg)
            if _ic:
                rec["iv_spread_confirm"] = _ic
        if fragility_map.get(ticker):
            rec["fragility"] = fragility_map[ticker]
        if bsk_mem.get(ticker):
            rec["baskets_membership"] = bsk_mem[ticker]
        if revision_raw.get(ticker):           # raw analyst-revision fields → Demand Context (L1 consensus)
            rec["revisions"] = revision_raw[ticker]
        if demand_signals or rpo_by_ticker or headcount_by_ticker:   # demand chains / RPO / hiring → L2
            dchread = (dchain.chain_read(demand_signals, rec.get("baskets_membership"),
                                         rec.get("revisions"), ticker=ticker) if demand_signals else None)
            if dchread is None and rpo_by_ticker.get(ticker):   # software complex: own forward bookings
                dchread = dchain.rpo_read(rpo_by_ticker[ticker], rec.get("revisions"))
            if dchread is None and headcount_by_ticker.get(ticker):   # last fallback: hiring/headcount
                dchread = dchain.hiring_read(headcount_by_ticker[ticker], rec.get("revisions"))
            if dchread:
                # attach the scored-ledger summary (leading chains only) for the
                # panel's accountability line — global, same for every name
                if dchread.get("leading") and demand_track:
                    o = demand_track.get("overall") or {}
                    dchread["ledger"] = {"scored": o.get("n"), "hits": o.get("hits"),
                                         "hit_rate": o.get("hit_rate"), "open": demand_track.get("open"),
                                         "since": demand_track.get("as_of")}
                rec["demand_chain"] = dchread
                # board chip flags the LEADING variant only (capex / RPO) — coincident
                # cross-reads (housing, hiring) stay on the panel + Demand Desk page.
                if dchread.get("leading") and dchread["divergence"] in ("ahead_of_consensus", "consensus_at_risk"):
                    demand_chip[ticker] = {"div": dchread["divergence"], "chain": dchread["chain_key"],
                                           "tier": dchread["tier"], "yoy": dchread.get("yoy_pct")}
        # ---- unified Conviction Profile (engine/stock_score) -----------------
        # The single block both the dashboard standout card AND this name's detail page
        # render, so the two can never structurally disagree. v2: the EDGE = the VALIDATED
        # event core (SUE + insider + analyst-revisions), residual momentum a light context;
        # the cycle state is a HARD verb modifier (a downtrend caps entry + forbids a Buy verb).
        ins = insider_map.get(ticker) or {}
        ins_bps = ins.get("bps") if (ins.get("buyers", 0) >= 2 and (ins.get("net_mn") or 0) > 0) else None
        if ext_map.get(ticker):
            rec["ext"] = ext_map[ticker]            # re-arms the parabolic/stretched entry brake
        spot = _spotlight_for(sector, bsk_mem.get(ticker), spotlight_ctx)
        # primary narrative basket = the spotlight theme (strongest tilt the name belongs to);
        # attach its allocation/trend-gate state for the validated size de-risk + Mastermind.
        _alloc_by_id = spotlight_ctx.get("alloc_by_id") or {}
        _bslug = ((spot or {}).get("theme") or {}).get("slug")
        if not _bslug and bsk_mem.get(ticker):
            # spotlight neutral but the name IS in basket(s): attach its best-ranked (most
            # in-favor) narrative so Mastermind + the de-blur still see it (de-risk stays inert
            # unless that basket is itself below-trend / deteriorating).
            _cands = [m.get("slug") for m in bsk_mem[ticker] if m.get("slug") in _alloc_by_id]
            if _cands:
                _bslug = min(_cands, key=lambda s: (_alloc_by_id[s].get("rank") or 999))
        _balloc = _alloc_by_id.get(_bslug) if _bslug else None
        if _balloc:
            rec["basket_alloc"] = {**_balloc, "slug": _bslug}
        norm = stock_score.normalize_rec(
            rec, "US", sue=sue_z.get(ticker), sue_fresh_days=sue_fresh.get(ticker),
            insider_bps=ins_bps, revision_z=revision_z.get(ticker), basket=basket_tw.get(ticker),
            spotlight=spot, basket_alloc=rec.get("basket_alloc"),
            lottery_max=lottery_map.get(ticker), earnings_days=_edays(ticker))
        prof = stock_score.conviction_profile(
            norm, "US", ctx={"as_of": alpha_asof, "gate_go": gate_go,
                             "regime": {"calm": calm}, "risk_overlay": risk_overlay})
        rec["conviction"] = prof
        # ---- Risk-based sizing (engine/risk_sizing) — the VALIDATED Sharpe lever ----
        # Vol-managed inverse-vol size: bet LESS on high-vol names, MORE on calm ones,
        # scaled by the dispersion regime. This is HOW MUCH to own (risk), orthogonal to
        # the conviction score (WHAT to own) and the entry gauge (WHEN). Mastermind + the
        # board multiply the conviction-base size by `size_mult`.
        try:
            rs = risk_sizing.assess(close, regime_gross=regime_gross)
            if rs:
                rec["risk_sizing"] = rs
                if isinstance(prof, dict) and isinstance(prof.get("size"), dict):
                    prof["size"]["vol_mult"] = rs["size_mult"]      # additive, never overrides
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("risk-sizing for %s failed (%s)", ticker, e)
        if composite_pt.get(ticker):                # decorrelated cross-sectional composite (context)
            rec["composite"] = composite_pt[ticker]
        # ---- Entry-timing gauge (engine/entry_signal) — the SECOND gauge ------
        # Conviction answers "own it?"; this answers "buy now / at what price / when?".
        # A structured plan (status, buy zone $, don't-chase line, stop, horizon read)
        # so an extended leader reads "wait — accumulate ~$X", never "99 · Buy Now".
        try:
            # gate the entry gauge on the SAME MACD-2D x StochRSI-3D confluence as the boards:
            # a daily-cycle "buy now / partial" with no fresh confluence cross reads
            # "awaiting confluence", never an open entry window.
            es = entry_signal.assess(close, high, rec,
                                     buyable=signal_gate.is_buyable(sig_verdict.get(ticker)))
            if es:
                rec["entry_signal"] = es
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("entry-signal for %s failed (%s)", ticker, e)
        # ---- Pullback buy-zone (display-only) ---------------------------------
        # turn an "Extended — don't chase" verdict into a concrete level: the rising 50d /
        # the out-of-chase line for a timeable leader, or a "this is a chase, the reset is X%
        # lower" read for a parabolic blow-off. Pure price math off rec['tech'] + the grade;
        # self-gates (returns None) for anything not in don't-chase territory.
        try:
            pz = pullback_zone.compute(
                rec.get("tech"), (rec.get("ext") or {}).get("grade"),
                downtrend=((rec.get("ladder") or {}).get("dir") == "down"))
            if pz:
                rec["pullback_zone"] = pz
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("pullback-zone for %s failed (%s)", ticker, e)
        # 4H intraday available? (Polygon hourly store -> site/intraday/<T>.json). stock.html
        # passes this to the chart so the 4H button only appears where data actually exists.
        rec["has_intraday"] = 1 if (config.data_dir() / "intraday" / f"{ticker}.parquet").exists() else 0
        # ---- POTENTIAL score (engine/name_score, US) — the displayed buy-readiness ----
        # Front-running / trend-following timing (cycle trigger × washout) BLENDED with the
        # US validated EVENT edge (insider / SUE / revisions = the selection-axis z), so a
        # washed-out turning name WITH insider buying outranks an identical one without —
        # timing AND alpha, neither at the other's cost. Overrides the displayed score below.
        try:
            _sel_z = ((prof.get("axes") or {}).get("selection") or {}).get("z")
            rec["conviction"]["potential"] = name_score.potential_score(
                rec, market="US", edge_z=_sel_z,
                regime_stress=float((prof.get("risk") or {}).get("macro_stress") or 0.0))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("US potential score for %s failed (%s)", ticker, e)
        profiles[ticker] = prof
        if rec.get("entry_signal"):
            entry_sig[ticker] = rec["entry_signal"]    # attached to standout rows below
        if rec.get("risk_sizing"):
            risk_sig[ticker] = rec["risk_sizing"]      # attached to standout rows below
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
        # ---- Alt-data convergence chip (display-only) -------------------------
        if altdata_ctx:
            try:
                ad = _altdata.chip(altdata_ctx.get(ticker))
                if ad:
                    rec["altdata"] = ad
            except Exception as e:  # noqa: BLE001 — additive, never fatal
                log.warning("alt-data chip for %s failed (%s)", ticker, e)
        # ---- DannyTrades CONTRARIAN read (display-only) -----------------------
        # extension flag (decile Spearman −0.88) + whale-fade; needs full OHLCV+volume
        # (data/stocks names only — others silently skip). See research/DANNYTRADES_PHASE0.md.
        try:
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
    # surface any GICS sector strings the spotlight sector-channel couldn't bridge to an SPDR
    # ETF (the theme channel still fires for these names) so the alias map can be widened.
    _unmapped = spotlight_ctx.get("unmapped") if spotlight_ctx else None
    if _unmapped:
        log.warning("spotlight: %d unmapped sector(s) -> add to engine.spotlight.GICS_TO_ETF: %s",
                    len(_unmapped), sorted(_unmapped))
    # within-market percentile display score (mutates the conviction blocks in place;
    # rec['conviction'] is the SAME object, so the per-stock JSONs pick it up below).
    stock_score.attach_panel_scores(profiles)
    # W6-US fix 2: emit BOTH scores as first-class fields so nothing is hidden.
    #   score_edge   = the within-market composite_z percentile (monotone with edge; the
    #                  "how good is this name" read). This is what attach_panel_scores wrote
    #                  into c["score"] before we overwrite it.
    #   score_timing = the potential_score (buy-readiness blend: washout × trigger × survive
    #                  × edge_mult). This is what the card historically displayed as "score".
    # The PRIMARY displayed number stays score_timing (= legacy c["score"]) for continuity,
    # but score_edge is emitted and the template can render it as a separate "edge percentile"
    # meter. The band/color is now forced to agree with the verdict so a Lagging name with a
    # high washout score can never wear a green/high band (build-time invariant enforced below).
    # Backward-compat: the old "score" field = score_timing so downstream code reading
    # c["score"] still gets the timing number; nothing outside us_stocks.html reads score_edge.
    for _safe, _rec in to_write:
        _c = _rec.get("conviction") or {}
        _pot = _c.get("potential")
        if not _pot:
            continue
        # score_edge = the honest edge-percentile (overwritten by potential below)
        _c["score_edge"] = _c.get("score")
        # score_timing = the buy-readiness blend (legacy "score" for continuity)
        _c["score_timing"] = _pot["score"]
        # The PRIMARY displayed number is score_timing (buy-readiness), kept in "score"
        # for backward-compat. The band is forced to the verdict-derived cap so the
        # band color never contradicts the absolute edge verdict.
        _c["rank_pctile"] = _c.get("score")
        _c["score"] = _pot["score"]
        # Verdict-anchored band: never green/constructive/high on a Lagging or no-edge name.
        # The potential band is used as-is for names with a positive verdict;
        # for Lagging / no-clear-edge verdicts we cap at "neutral".
        _verdict = (_c.get("verdict") or "").lower()
        _lagging = any(k in _verdict for k in ("lagging", "no clear edge"))
        if _lagging:
            # cap to neutral regardless of washout depth
            _c["band"] = "neutral"
            _c["band_en"] = "neutral"
            _c["band_zh"] = "中性"
        else:
            _c["band"], _c["band_en"], _c["band_zh"] = _pot["band"], _pot["band_en"], _pot["band_zh"]
        _notes = _c.get("notes")
        if _notes:
            _c["notes"] = [n for n in _notes if n.get("kind") != "rank"] or None
    try:
        _asof = str(pd.Timestamp.utcnow().date())
        _calls = []
        for _safe, _rec in to_write:
            _pot = (_rec.get("conviction") or {}).get("potential")
            if _pot and _pot.get("call"):
                _calls.append({**_pot["call"], "level": (_rec.get("tech") or {}).get("price")})
        if _calls:
            _n = name_score_grader.append_name_calls(_calls, market="US", asof=_asof)
            log.info("US name-score grader: logged %d calls for %s (ledger=%d)", len(_calls), _asof, _n)
    except Exception as e:  # noqa: BLE001 — grading is additive, never fatal
        log.warning("US name-score grader append failed (%s)", e)
    for safe, rec in to_write:
        # canonical render model (engine/stock_view) — built AFTER attach_panel_scores so
        # the view's score/band match the final within-market percentile. Additive: the
        # shared stockview.js renders rec["view"]; legacy panels still read rec.* directly.
        rec["view"] = stock_view.build_view(rec, "US")
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
    # Publish the per-name confluence-cascade verdict (the owner's MACD-2D x StochRSI-3D
    # T1->T4 gate, already computed above for every universe name) so the discovery "Top
    # Picks" board (scripts/build_discovery, which runs AFTER build_site in the daily
    # pipeline) can gate its "Buy-zone" picks on the SAME signal the Top-setups strip uses —
    # one source of truth, no recompute, T1 (the validated §7 master) included. Additive.
    (site / "factordata").mkdir(parents=True, exist_ok=True)
    if sig_verdict:
        try:
            sig_out = {t: signal_gate.buy_signal(v) for t, v in sig_verdict.items()}
            (site / "factordata" / "signal_gate.json").write_text(
                json.dumps({"as_of": alpha_asof, "verdicts": sig_out},
                           separators=(",", ":"), default=str, allow_nan=False))
            log.info("wrote signal_gate.json (%d verdicts, %d buyable)", len(sig_out),
                     sum(1 for v in sig_verdict.values() if signal_gate.is_buyable(v)))
        except Exception as e:  # noqa: BLE001 — additive; discovery falls back to recompute
            log.warning("signal_gate.json write skipped (%s)", e)
    # cross-sectional "Top setups" — selection (sector-neutral residual alpha) ×
    # timing (cycle entry + reversal overlay), surfaced on the macro dashboard's
    # "Standout individual stocks" board (read by build_site one build later, since
    # build_library runs at the END of build_site). Mirrors build_china_library.
    if cand:
        # The buy list is HARD-GATED on the owner's MACD-2D x StochRSI-3D confluence
        # (signal_gate.is_buyable: T1/T2 just-crossed or T3 about-to-cross) — so the board
        # only ever recommends a name that has actually triggered (or is imminently
        # triggering) the entry, never a high-alpha leader that is downtrending on the 3D
        # MACD/StochRSI. The gate REPLACES the alpha>=0.5 floor; the alpha leg now only
        # RANKS the survivors (Phase-0 found the cycle/reversal blend dilutes forward-return
        # ranking, so we keep the validated alpha leg as the sort and show timing as context).
        setups = rank_setups(cand, as_of=alpha_asof, rank_by="alpha",
                             buy_gate=lambda t: signal_gate.is_buyable(sig_verdict.get(t)))
        for r in setups.get("buy", []):
            r["signal"] = signal_gate.buy_signal(sig_verdict.get(r.get("ticker")))
        (site / "factordata" / "setups.json").write_text(
            json.dumps(setups, separators=(",", ":"), default=str))
        log.info("wrote setups.json (%d buy [confluence-gated], %d laggards, %d candidates)",
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
        # realize -0.7pp/mo and a -58% vs -41% worst drawdown) AND the new BOTTOMING-ALIGNMENT
        # gate. A name is BUYABLE only if its cycle/extension does NOT block (downtrend /
        # parabolic / over-extended chase) AND its entry is constructive (entry_z > 0) AND its
        # weekly/3-day/daily are ALIGNED to the upside (engine.cycles.mtf_alignment: weekly
        # not-falling + 3-day nearing a bullish cross + daily just-crossed/about-to) — so a
        # mid-weekly-bear falling knife with a strong event EDGE can no longer top the board.
        # NEAR-aligned names backfill (tagged) only when too few are fully aligned; the buy
        # list is ranked by alignment score first, then the Conviction composite. Strong-but-
        # unaligned names (wrong tape / weekly still falling) drop to the WATCH strip.
        def _entry_ok(p):
            if p.get("cycle_blocked"):
                return False
            ez = ((p.get("axes") or {}).get("entry") or {}).get("z")
            return ez is None or ez > 0

        def _atier(p):
            a = p.get("alignment") or {}
            return "aligned" if a.get("aligned") else ("near" if a.get("near") else None)

        def _asort(tp):
            _t, p, _tier = tp
            a = p.get("alignment") or {}
            return ((a.get("score") or 0.0), (p.get("composite_z") or 0.0))

        elig = [(t, p, _atier(p)) for t, p in scored if _entry_ok(p) and _atier(p)]
        aligned = sorted([x for x in elig if x[2] == "aligned"], key=_asort, reverse=True)
        near = sorted([x for x in elig if x[2] == "near"], key=_asort, reverse=True)
        buyable = (aligned if len(aligned) >= ALIGN_MIN_KEEP
                   else aligned + near[: ALIGN_MIN_KEEP - len(aligned)])
        # COMBINE re-rank: keep main's aligned-above-near inclusion, but order WITHIN each
        # alignment tier by the owner's confluence weighted blend (conviction percentile +
        # 0.5 * cascade weight) so the strongest confluence entries (T1>T2>T3>T4) rise. Names
        # with no confluence verdict keep their conviction rank (weight 0 = no boost, not buried).
        _czs = sorted((p.get("composite_z") or 0.0) for _t, p, _ti in buyable)
        _bn = len(_czs) or 1

        def _combine_key(x):
            t, p, tier = x
            w = (sig_verdict.get(t) or {}).get("weight") or 0.0
            pct = bisect.bisect_right(_czs, p.get("composite_z") or 0.0) / _bn
            return (0 if tier == "aligned" else 1, -(pct + 0.5 * w))
        buyable = sorted(buyable, key=_combine_key)

        # W6-US fix 6: soft per-sector cap + dual-class dedup on the wide board.
        # The same PER_SECTOR=5 cap that guards action_board.notable in build_site.py
        # is now applied here so bottoming-alignment can't select all of one sector
        # (live: 10 Industrials + 9 Utilities = 19/34 = 56% of buys).
        # Soft: names that exceed the cap overflow into the watch strip instead of
        # being discarded — the board is transparent about them.
        # Dual-class dedup: names sharing a normalised company name (GOOG+GOOGL) keep
        # only the first-ranked variant. Uses engine.setups.norm_company.
        from engine.setups import norm_company as _norm_co
        _WIDE_PER_SECTOR = 5
        _by_sec_w: dict[str | None, int] = {}
        _seen_name_w: set[str] = set()
        _buyable_capped: list[tuple] = []
        _buyable_overflow: list[tuple] = []
        for _item in buyable:
            _t6, _p6, _tier6 = _item
            _r6 = row_by_t[_t6]
            _nm6 = _norm_co(_r6.get("name"))
            if _nm6 and _nm6 in _seen_name_w:
                # dual-class dupe — drop silently
                continue
            if _nm6:
                _seen_name_w.add(_nm6)
            _sec6 = _r6.get("sector")
            if _by_sec_w.get(_sec6, 0) < _WIDE_PER_SECTOR:
                _by_sec_w[_sec6] = _by_sec_w.get(_sec6, 0) + 1
                _buyable_capped.append(_item)
            else:
                _buyable_overflow.append(_item)
        # overflow goes to watch (they are aligned, just over the soft cap)
        buyable = _buyable_capped

        # concentration stat for the banner
        _sec_counts6 = {}
        for _t6, _p6, _ti6 in buyable:
            _s6 = row_by_t[_t6].get("sector")
            _sec_counts6[_s6] = _sec_counts6.get(_s6, 0) + 1
        _top2_share6 = sum(sorted(_sec_counts6.values(), reverse=True)[:2]) / max(len(buyable), 1)
        _n_sectors6 = len(_sec_counts6)
        _concentration_stat = {
            "top2_sector_share": round(_top2_share6, 2),
            "n_sectors": _n_sectors6,
            "n_names": len(buyable),
            "effective_bets": _n_sectors6,  # rough lower bound
            "overflow_count": len(_buyable_overflow),
        }
        log.info("W6-US fix 6: sector cap applied — %d buy names, %d sectors, "
                 "top-2 share %.0f%%, %d overflow to watch",
                 len(buyable), _n_sectors6, 100 * _top2_share6, len(_buyable_overflow))

        buy_ids = {t for t, _, _ in buyable}
        # overflow names join watch (only if positive conviction, no duplication)
        _overflow_tickers = {t for t, _, _ in _buyable_overflow}
        watch = [(t, p) for t, p in scored
                 if t not in buy_ids and (p.get("composite_z") or 0) > 0
                 and t not in _overflow_tickers]
        # prepend capped-overflow to watch in order (they are aligned — keep them visible)
        _overflow_watch = [(t, row_by_t[t]) for t, _, _ in _buyable_overflow
                           if (profiles.get(t) or {}).get("composite_z", 0) > 0]
        watch = _overflow_watch + watch

        def _tag(t, tier):
            r = row_by_t[t]
            r["align_tier"] = tier
            return r
        wide = {"as_of": alpha_asof, "rank_by": "bottoming-alignment", "gate_go": gate_go,
                "buy": [_tag(t, tier) for t, _, tier in buyable[:120]],
                "watch": [row_by_t[t] for t, _ in watch[:24]],
                "laggards": [row_by_t[t] for t, _ in scored[-12:][::-1]] if len(scored) > 24 else [],
                "concentration": _concentration_stat}
        eligible = len(aligned)
        for r in wide["buy"] + wide["watch"] + wide["laggards"]:
            t = r.get("ticker")
            r["conviction"] = profiles.get(t)
            r["signal"] = signal_gate.compact(sig_verdict.get(t))   # confluence T1->T4 tier badge
            if entry_sig.get(t):
                r["entry_signal"] = entry_sig[t]     # the entry-timing gauge for the card
            if risk_sig.get(t):
                r["risk_sizing"] = risk_sig[t]       # the vol-managed sizing for the card / bot
            if composite_pt.get(t):
                r["composite"] = composite_pt[t]     # the decorrelated cross-sectional composite
            r.update({k: v for k, v in (disp_map.get(t) or {}).items() if v is not None})
            if demand_chip.get(t):                 # L2 demand-divergence flag for the board chip
                r["demand"] = demand_chip[t]
        # ENTRY-OPEN-FIRST board order: names whose entry gauge reads "Buy zone — entry
        # open now" lead the strip, then by the displayed conviction score. Stable, so
        # the bottoming-alignment + confluence rank above only settles ties. Applied
        # after enrichment so entry_signal + conviction are attached to every row.
        wide["buy"] = entry_open_first(wide["buy"])
        wide["eligible"] = eligible
        wide["universe"] = len(cand)
        if disp_regime:                            # selection-regime gross dial (board + bot)
            wide["dispersion_regime"] = disp_regime

        # --- W6-US fix 7: urgency must respect the gated entry status ---
        # Row-level urgency="now" is derived from the cycle-state dict, but the
        # entry_signal.status is confluence-gated (entry_signal.py:167). When the gate
        # says "await_confluence" the cycle has not confirmed, so urgency="now" is
        # dishonest. We enforce: urgency="now" is only allowed when entry_signal.status
        # is in {buy_now, partial}. Otherwise urgency is downgraded to the entry status.
        _URGENCY_STATUS_MAP = {
            "buy_now": "now", "partial": "now",
            "await_confluence": "caution", "extended": "caution",
        }
        _urgency_downgrade_count = 0
        for _r in wide["buy"] + wide["watch"]:
            if _r.get("urgency") != "now":
                continue
            _es7 = (_r.get("entry_signal") or {}).get("status")
            if _es7 not in ("buy_now", "partial", None):
                _r["urgency"] = _URGENCY_STATUS_MAP.get(_es7, "caution")
                _urgency_downgrade_count += 1
        if _urgency_downgrade_count:
            log.info("W6-US fix 7: %d rows had urgency=now with non-open entry status "
                     "— downgraded to match entry_signal.status", _urgency_downgrade_count)

        # --- W6-US fix 3: build-time honesty invariants ---
        # (a) Band/verdict contradiction: band high/constructive while verdict is Lagging
        #     or no-clear-edge is a regression guard for fix 2. After fix 2 this MUST be
        #     empty; the invariant raises so future regressions don't silently slip through.
        _band_verdict_violations: list[str] = []
        for _r in wide["buy"]:
            _c3 = _r.get("conviction") or {}
            _v3 = (_c3.get("verdict") or "").lower()
            _b3 = _c3.get("band") or ""
            if _b3 in ("high", "constructive") and any(
                    k in _v3 for k in ("lagging", "no clear edge")):
                _band_verdict_violations.append(
                    f"{_r.get('ticker')}: band={_b3}, verdict={_c3.get('verdict')}")
        if _band_verdict_violations:
            raise RuntimeError(
                "W6-US invariant (a) FAILED — green band on lagging/no-edge name(s): "
                + "; ".join(_band_verdict_violations))

        # (b) BUY label with blocked signal: downgrade label+urgency so a row labeled
        #     BUY/FRESH never shows urgency='now' when signal.last.quality=='block'.
        #     We mutate the row (not just log) so the invariant enforces itself in the artifact.
        _blocked_buy_count = 0
        for _r in wide["buy"]:
            _sig3 = _r.get("signal") or {}
            _last3 = _sig3.get("last") or {}
            if _last3.get("quality") == "block":
                _blocked_buy_count += 1
                # downgrade urgency from "now" to "caution" if present
                if _r.get("urgency") == "now":
                    _r["urgency"] = "caution"
                # downgrade label: prefix with "(blocked)" marker
                _lbl3 = _r.get("label")
                if _lbl3 and "(blocked)" not in str(_lbl3):
                    _r["label"] = f"{_lbl3} (blocked)"
                _lbl3_zh = _r.get("label_zh")
                if _lbl3_zh:
                    _r["label_zh"] = f"{_lbl3_zh}（受阻）"
        if _blocked_buy_count:
            log.warning("W6-US invariant (b): %d BUY rows have signal.last.quality=block — "
                        "urgency downgraded to caution, label suffixed (blocked)",
                        _blocked_buy_count)

        # (c) Confirmer chip renders for a scored:false gate.
        # For GEX: verify the gate file agrees with _gex_gate_scored() at build time.
        # This is a warning (not a raise) since the chip render is fixed in fix 4.
        try:
            from engine.stock_score import _gex_gate_scored
            _gex_scored = _gex_gate_scored()
            if not _gex_scored:
                _gex_chip_rows = [_r.get("ticker") for _r in wide["buy"]
                                  if ((_r.get("conviction") or {}).get("gex_confirm") or {}).get("verdict")]
                if _gex_chip_rows:
                    log.warning("W6-US invariant (c): GEX gate scored=False but %d buy rows have "
                                "gex_confirm chip (fix 4 hides them in template): %s",
                                len(_gex_chip_rows), _gex_chip_rows[:5])
        except Exception as _e3:  # noqa: BLE001
            log.debug("W6-US invariant (c) GEX check skipped: %s", _e3)

        (site / "factordata" / "us_standouts.json").write_text(
            json.dumps(_json_safe(wide), separators=(",", ":"), default=str, allow_nan=False))
        log.info("wrote us_standouts.json (%d buy · rank_by=%s · %d eligible / %d universe)",
                 len(wide["buy"]), wide["rank_by"], eligible, len(cand))
        # forward shadow book — freeze the live score at build time so it can be graded on
        # REALIZED forward returns later (engine/shadow_book; research/MEASUREMENT_FLOOR.md).
        # Additive + display-only + append-only; never fatal.
        try:
            from engine import shadow_book as _sb
            _asof = wide.get("as_of")
            if _asof:
                def _reg(c):
                    rg = (c or {}).get("regime")
                    return rg.get("state") if isinstance(rg, dict) else None
                _recs = [{"ticker": r.get("ticker"), "score": (r.get("conviction") or {}).get("score"),
                          "percentile": (r.get("conviction") or {}).get("score"),
                          "regime": _reg(r.get("conviction"))}
                         for b in ("buy", "watch", "laggards") for r in wide.get(b, [])]
                _n = _sb.snapshot(_asof, [r for r in _recs if r["score"] is not None])
                log.info("shadow book: snapshotted %d frozen scores for %s", _n, _asof)
        except Exception as e:  # noqa: BLE001
            log.debug("shadow snapshot skipped (%s)", e)
    # multi-timeframe Bottom-Confidence per-band held-rate (stock.html shows the
    # measured "this band held the low ~N%" line; see research/BOTTOM_CONFIDENCE.md)
    bccal = config.data_dir() / "regime" / "bottom_confidence_calibration.json"
    if bccal.exists():
        (outdir / "bc_calibration.json").write_text(bccal.read_text())
    log.info("stock library: %d analyzed, %d skipped (thin history)", built, failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
