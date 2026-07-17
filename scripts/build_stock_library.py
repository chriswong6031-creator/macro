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
import math
import logging
import os
import sys
import time
from datetime import date, timedelta
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
    US_ALPHA_WEIGHT, entry_open_first, rank_setups, setup_score,
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
from engine import coiled  # noqa: E402  — wave-2-validated COILED ranking bonus (display/ranking only)
from engine import donor  # noqa: E402  — G6a donor-sector context chip (display-only)
from engine import hold as hold_engine  # noqa: E402  — W6-C HOLD tracker (basing state / invalidation)
from engine import earnings_blackout as _eb  # noqa: E402  — W1.5 earnings-blackout hygiene veto
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

# Single-stock rows carry ONE sector vocabulary: the 11 GICS names. The breadth
# constituents and stock_search.extra_names paths already emit it; the deep-history
# holdings path uses SPDR display names (SECTOR_NAMES), which differ from GICS for
# exactly two funds — bridged here so every consumer (SECZH map, donor.GICS_SECTORS,
# cohort grouping) sees one vocabulary. Anything else non-empty is a data-quality
# leak — e.g. a stray non-fund parquet stem from data/sector_holdings/ riding in as
# a fake sector (QCOM sector="history", PR #2113 issue 4).
GICS_SECTORS = {
    "Energy", "Materials", "Industrials", "Consumer Discretionary",
    "Consumer Staples", "Health Care", "Financials", "Information Technology",
    "Communication Services", "Utilities", "Real Estate",
}
_SPDR_TO_GICS = {"Technology": "Information Technology",
                 "Communications": "Communication Services"}


def _drop_spurious_sector_rows(wide: dict) -> dict[str, list[tuple]]:
    """Drop buy/watch/laggards rows whose sector label is corrupt.

    A row is kept when its sector is empty/None (unknown — missing metadata is
    not a reason to drop a scored setup) or one of the 11 GICS names. Mutates
    *wide* in place; returns {lane: [(ticker, sector), ...]} for what was
    dropped so the caller can log it.
    """
    dropped: dict[str, list[tuple]] = {}
    for lane in ("buy", "watch", "laggards"):
        rows = wide.get(lane) or []
        bad = [(r.get("ticker"), r.get("sector")) for r in rows
               if (r.get("sector") or "") and r.get("sector") not in GICS_SECTORS]
        if bad:
            wide[lane] = [r for r in rows
                          if not r.get("sector") or r.get("sector") in GICS_SECTORS]
            dropped[lane] = bad
    return dropped


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
            summ = compute_gex(chain, spot, cfg={**ecfg, "r": gcfg.get("r", 0.043), "q": 0.0}, symbol=t)
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
            if fund not in SECTOR_NAMES:
                # cross-fund log files also live here (history.parquet PIT archiver,
                # holdings_runs.parquet) — their stems would leak in as fake sector
                # labels (QCOM sector="history", PR #2113 issue 4)
                continue
            sec = SECTOR_NAMES[fund]
            sec = _SPDR_TO_GICS.get(sec, sec)
            try:
                df = pd.read_parquet(p)
            except Exception as e:  # noqa: BLE001 — one corrupt parquet must not 404 the library
                log.warning("sector_holdings %s unreadable (%s) — skipped", p.name, e)
                continue
            if "ticker" not in df.columns:  # e.g. the holdings_runs summary
                continue
            for _, r in df.iterrows():
                names[str(r["ticker"]).replace(".", "-")] = (
                    str(r.get("name", "")).title(), sec)
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


# Urgency values that read as actionable on the board. A blocked signal must never
# carry any of these (check_board_contradictions.py invariant (b) asserts the
# artifact side; this is the builder side).
_ACTIONABLE_URGENCIES = ("now", "imminent")


def _board_alpha_sort_key(ticker: str, row_by_t: dict, profile: dict | None = None) -> tuple:
    """W8 alpha-desc sort key for wide-board buy rows (forward ledger #1062:
    P@1 board-order 28.6% vs alpha-order 71.4%).

    The scalar residual-alpha z lives on the BOARD ROW (``row_by_t[t]["alpha"]``,
    set by engine.setups.setup_score) — NOT on the conviction profile, which never
    carries an ``"alpha"`` key. The original in-closure key read the profile, so
    the primary key was a constant -0.0 for every row and the #1494 determinism
    tiebreaker silently became the whole sort — shipping a ticker-alphabetical
    board that trips check_board_contradictions invariant (d) (negative-alpha
    slot-1 above positive-alpha rows in the same lane). Falls back to the
    profile's composite_z when the row carries no alpha (recovery-lane contract).
    """
    row = row_by_t.get(ticker) or {}
    alpha = row.get("alpha")
    if alpha is None and profile is not None:
        alpha = profile.get("composite_z")
    return (-(alpha or 0.0), ticker)


def _atier(p: dict | None) -> str | None:
    """Board-level alignment tier off a conviction profile. Under the cascade
    inclusion gate this is per-card CONTEXT only (align_tier badge + lane
    derivation) — never an inclusion predicate."""
    a = (p or {}).get("alignment") or {}
    return "aligned" if a.get("aligned") else ("near" if a.get("near") else None)


def _cascade_elig(scored: list[tuple], sig_verdict: dict) -> list[tuple]:
    """CONFLUENCE CASCADE INCLUSION GATE for the wide standout board (owner
    directive 2026-07-16, parity with CN build_china_library.py:1433 and HK
    owner-ratified 2026-07-16): a name is buy-shelf eligible iff its signal_gate
    T1->T4 cascade verdict is `eligible` (freshness- and not-topped-guarded
    inside signal_gate.gate). Returns [(ticker, profile, align_tier), ...]
    preserving `scored` order (composite desc, ticker) — the board ORDERING is
    applied by the caller via signal_gate.blend_sorted."""
    return [(t, p, _atier(p)) for t, p in scored
            if (sig_verdict.get(t) or {}).get("eligible")]


# ── P2.4 Board Contract v2 lane taxonomy ─────────────────────────────────────
# Spec: research/entry_intel/P2_4_BOARD_CONTRACT_V2_DESIGN.md
# Vocabulary sets — verified 2026-07-05 against live us_standouts.json.
# Live board: align_tier in {"aligned", "near", None}.
# Replay/conviction layer: alignment.tier in {"PRIME", "ARMED", ...}.
# Both vocabularies are handled explicitly; unknown values log a warning.
_PRIME_EQUIV = {"PRIME", "aligned"}         # bottoming-type tiers
_ARMED_EQUIV = {"ARMED"}                    # continuation-type (requires rising weekly)
_NEAR_EQUIV = {"APPROACHING", "near", "bear_recovering", "turning"}  # near-aligned


def _lane_for(align_tier_val, weekly_phase_val):
    """Derive the v2 lane label from align_tier + weekly_phase.

    Handles both the live production vocabulary (aligned/near/None) and
    the replay/conviction vocabulary (PRIME/ARMED/APPROACHING).
    Logs a warning on any unknown tier and defaults to 'bottoming'.

    Under the cascade inclusion gate, align_tier may be None for healthy
    uptrending leaders that are cascade-eligible but never bottoming-aligned
    (they bypassed the alignment screen). A rising-weekly cascade-eligible
    name is a continuation entry, not bottoming — so tier=None with
    weekly_phase='rising' → 'continuation'. Non-rising None → 'bottoming'
    (conservative; JS already maps both lanes).
    """
    tier = None if align_tier_val in (None, "None", "") else align_tier_val
    if tier in _PRIME_EQUIV:
        return "bottoming"
    if tier in _ARMED_EQUIV and weekly_phase_val == "rising":
        return "continuation"
    if tier in _NEAR_EQUIV and weekly_phase_val == "rising":
        return "continuation"  # near/APPROACHING with rising phase → continuation
    if tier in _ARMED_EQUIV or tier in _NEAR_EQUIV:
        return "bottoming"     # non-rising ARMED or near → bottoming group
    if tier is None:
        # Cascade-eligible with no alignment tier: rising weekly → continuation
        # (uptrending leader); all other → bottoming (conservative default).
        return "continuation" if weekly_phase_val == "rising" else "bottoming"
    # UNKNOWN vocabulary: log loudly, default gracefully
    log.warning(
        "P2.4 _lane_for: UNKNOWN align_tier value %r (weekly_phase=%r) — "
        "defaulting to 'bottoming'. Update _PRIME_EQUIV/_ARMED_EQUIV/_NEAR_EQUIV "
        "if the builder vocabulary has changed.", align_tier_val, weekly_phase_val
    )
    return "bottoming"


def _enforce_blocked_buy_invariant(buy_rows: list[dict]) -> int:
    """W6-US invariant (b): a BUY row whose signal.last.quality == 'block' must not
    carry actionable urgency, and its label must carry the '(blocked)' marker.

    Downgrades urgency in _ACTIONABLE_URGENCIES → 'caution'. The original pass only
    downgraded 'now'; 'imminent' slipped through and shipped rows with
    label='BOTTOMING (blocked)' + urgency='imminent' (REZI/NGVT/ATMU/PCG, 2026-07),
    tripping the pages.yml deploy gate. Mutates rows in place; returns rows touched.
    """
    touched = 0
    for _r in buy_rows:
        _last = (_r.get("signal") or {}).get("last") or {}
        if _last.get("quality") != "block":
            continue
        touched += 1
        if _r.get("urgency") in _ACTIONABLE_URGENCIES:
            _r["urgency"] = "caution"
        _lbl = _r.get("label")
        if _lbl and "(blocked)" not in str(_lbl):
            _r["label"] = f"{_lbl} (blocked)"
        _lbl_zh = _r.get("label_zh")
        if _lbl_zh and "（受阻）" not in str(_lbl_zh):
            _r["label_zh"] = f"{_lbl_zh}（受阻）"
    return touched


def _compute_board_staleness(ohlcv_dir: "Path | None" = None, now: "datetime | None" = None) -> dict:
    """CSP-W5: compute staleness metadata for the US standout board.

    Scans data/baskets/ohlcv/*.parquet to find the maximum (most recent) date
    present in any per-ticker close store — this is the date the board is priced
    from, the same store the cascade gate reads.

    Returns:
        {
          "price_through": "2026-07-15",  # ISO date of most recent close in the store
          "age_days":      0,             # calendar days since price_through (int)
          "delayed":       False,         # True when >= 2 trading sessions behind expected
        }

    Fail-soft: if the store is absent or unreadable, returns
        {"price_through": None, "age_days": None, "delayed": False}
    so the badge is silently suppressed — never crashes a build.

    Calendar: uses lib.nyse_calendar.expected_last_session and is_session — the
    same pure-rule calendar used across the freshness infrastructure.
    """
    from datetime import datetime as _dt, timezone as _tz
    from lib import nyse_calendar as _nyse

    _sentinel = {"price_through": None, "age_days": None, "delayed": False}
    try:
        _root = ohlcv_dir or (config.data_dir() / "baskets" / "ohlcv")
        _root = _root if isinstance(_root, Path) else Path(_root)
        if not _root.is_dir():
            return _sentinel
        _max_date: "date | None" = None
        for _fname in os.listdir(str(_root)):
            if not _fname.endswith(".parquet"):
                continue
            try:
                _df = pd.read_parquet(str(_root / _fname), columns=["close"])
                if _df.empty:
                    continue
                _idx = pd.to_datetime(_df.index)
                _last = _idx.max().date()
                if _max_date is None or _last > _max_date:
                    _max_date = _last
            except Exception:  # noqa: BLE001 — per-file failure is non-fatal
                continue
        if _max_date is None:
            return _sentinel

        _now = now or _dt.now(_tz.utc)
        _expected = _nyse.expected_last_session(_now)

        # age_days: calendar days between price_through and expected session
        _age_days = (_expected - _max_date).days

        # delayed: count trading sessions between price_through and expected session
        # (strictly after price_through, up to and including expected)
        _d = _max_date
        _sessions_behind = 0
        while _d < _expected:
            _d = _d + timedelta(days=1)
            if _nyse.is_session(_d):
                _sessions_behind += 1

        _delayed = _sessions_behind >= 2

        log.debug(
            "board staleness: price_through=%s expected=%s age_days=%d "
            "sessions_behind=%d delayed=%s",
            _max_date, _expected, _age_days, _sessions_behind, _delayed,
        )
        return {
            "price_through": str(_max_date),
            "age_days": _age_days,
            "delayed": _delayed,
        }
    except Exception as _e:  # noqa: BLE001 — never crashes a build
        log.warning("_compute_board_staleness: failed (%s) — suppressing badge", _e)
        return _sentinel


def _count_trading_sessions_between(start_date: "date", end_date: "date") -> int:
    """Count NYSE trading sessions strictly after start_date up through end_date.

    Used by the pending-buy expiry rule: a pending buy that fired on start_date
    is 'unconfirmed for N sessions' where N = _count_trading_sessions_between(
    fire_date, board_asof).

    Reuses lib.nyse_calendar.is_session — the same pure-rule calendar used
    everywhere in the freshness infrastructure.
    """
    from lib import nyse_calendar as _nyse
    _d = start_date
    _n = 0
    while _d < end_date:
        _d = _d + timedelta(days=1)
        if _nyse.is_session(_d):
            _n += 1
    return _n


def _expire_pending_buys(buy_rows: list[dict], watch_rows: list[dict],
                         board_asof: "str | None") -> tuple[list[dict], list[dict], int]:
    """CSP-W5 pending-buy expiry: move stale unconfirmed pending rows from buy to watch.

    Rule: a buy-lane row whose signal has tier='anticipation', sub='pending',
    and whose buy fired > 3 trading sessions before board_asof AND is still
    unconfirmed (quality still 'pending') is demoted to the watch shelf with
    a bilingual reason string.

    Demotion-only: adds nothing to the buy side.  Never touches confirmed (take)
    signals.  Deterministic: always produces the same result for the same inputs.

    Returns:
        (new_buy_rows, new_watch_rows, n_expired)
        where n_expired is the count of rows moved from buy to watch.

    Fail-soft: if board_asof is None or unparseable, no rows are expired (the rule
    requires a known current date to count sessions).
    """
    if not board_asof:
        return buy_rows, watch_rows, 0
    try:
        _asof = pd.Timestamp(board_asof).date()
    except Exception:  # noqa: BLE001
        return buy_rows, watch_rows, 0

    _EXPIRY_SESSIONS = 3  # > 3 trading sessions = expired

    new_buy: list[dict] = []
    expired: list[dict] = []
    for _r in buy_rows:
        _sig = _r.get("signal") or {}
        # Only target anticipation/pending rows that are still unconfirmed
        if _sig.get("tier") != "anticipation" or _sig.get("sub") != "pending":
            new_buy.append(_r)
            continue
        _last = _sig.get("last") or {}
        if _last.get("quality") != "pending":
            new_buy.append(_r)
            continue
        _fire_date_str = _last.get("date")
        if not _fire_date_str:
            new_buy.append(_r)
            continue
        try:
            _fire_date = pd.Timestamp(_fire_date_str).date()
        except Exception:  # noqa: BLE001
            new_buy.append(_r)
            continue

        _sessions = _count_trading_sessions_between(_fire_date, _asof)
        if _sessions > _EXPIRY_SESSIONS:
            # Demote: mark the row with the expiry reason and move it to watch
            _r = dict(_r)  # shallow copy — don't mutate the original list item
            _r["pending_expired"] = True
            _r["pending_expiry_reason"] = (
                f"confirmation expired — signal fired {_fire_date_str}, "
                f"no confirming data since"
            )
            _r["pending_expiry_reason_zh"] = (
                f"确认超时 — 信号于 {_fire_date_str} 触发，此后无确认数据"
            )
            _r["lane"] = "watch"    # re-tag lane so the watch grid shows it correctly
            expired.append(_r)
        else:
            new_buy.append(_r)

    new_watch = expired + watch_rows  # expired rows go to the top of watch
    n_expired = len(expired)
    if n_expired:
        log.info(
            "CSP-W5 pending expiry: %d row(s) moved buy→watch "
            "(pending > %d sessions unconfirmed): %s",
            n_expired, _EXPIRY_SESSIONS,
            [_r.get("ticker") for _r in expired],
        )
    return new_buy, new_watch, n_expired


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
    # Oracle dark-tilt channel — {} unless config oracle.tilt_enabled (R4: default off).
    try:
        from engine.oracle.tilt import oracle_tilt_by_etf
        oracle_by_etf = oracle_tilt_by_etf()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("oracle tilt channel unavailable (%s)", e)
        oracle_by_etf = {}
    if oracle_by_etf:
        log.info("spotlight context: oracle tilt ENABLED for %d sector ETFs", len(oracle_by_etf))
    return {"theme_by_id": theme_by_id, "sector_by_etf": sector_by_etf,
            "alloc_by_id": alloc_by_id, "oracle_tilt_by_etf": oracle_by_etf, "unmapped": set()}


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
    oracle_t = ((ctx.get("oracle_tilt_by_etf") or {}).get(etf)) if etf else None
    return _sp.compute(memberships, ctx.get("theme_by_id") or {},
                       sector_etf=etf, sector_row=sector_row, oracle_t=oracle_t)


def _personality_inputs(
    ticker: str,
    rec: dict,
    ohlcv_df: "pd.DataFrame | None",
    as_of: str,
    dna_class_entry: "dict | None",
    bsk_mem_entry: "list[dict] | None",
    etf_wt: "float | None",
    oracle_active: "bool | None",
    days_to_earnings: "float | None" = None,
) -> dict:
    """Map a build_stock_library rec to engine.stock_personality.assess() kwargs.

    Pure function (no I/O) — all inputs are pre-computed by the caller.
    This is the W2b sourcing contract (see assess() docstring §W2b caller sourcing contract).

    Sourcing decisions
    ------------------
    vol_squeeze_state  ← rec["vol_squeeze"]["state"]
    ret_21d            ← close.pct_change(21) as a fraction (NOT percent) from ohlcv_df or
                         rec["tech"]["price"] path fallback → None when neither available
    months_underwater  ← engine.entry_primitives.time_underwater_series(close) tail / 21.0
                         Requires ohlcv_df close column ≥300 bars; else None.
    hv_pctile          ← rec["tech"]["hv_pctile"] (0-100 scale, from stock_technicals)
    rel_volume         ← rec["tech"]["rel_volume"]
    obv_slope_up       ← rec["tech"]["obv_slope_up"]
    off_52w_high_pct   ← rec["tech"]["off_52w_high_pct"] — SIGNED NEGATIVE pct below high
    gex.gamma_regime   ← rec["gex"]["gamma_regime"] (renamed from "regime" in older payloads)
    gex.dist_to_flip   ← rec["gex"]["dist_to_flip_pct"]
    short_pct_float    ← rec["positioning"]["short"]["pct_float"] (PERCENT 0-100)
    days_to_cover      ← rec["positioning"]["short"]["days_to_cover"]
    insider_*          ← rec["positioning"]["insider"] fields
    market_cap         ← rec["profile"]["mktcap_bn"] * 1e9 (factors.json field, bn → USD)
    attention_z        ← None (wiki attention z not yet wired per R-SP6; forward-ledger only)
    bo_regime          ← rec["beneficial_ownership"]["regime"]
    basket_membership  ← list of slug strings from bsk_mem_entry
    etf_weight_max     ← etf_wt (pre-loaded max weight_pct across all ETFs)
    oracle_episode     ← oracle_active (pre-mapped from oracle_state.json)
    events             ← {"days_to_earnings": days_to_earnings} when days_to_earnings is not
                         None; otherwise None.  Caller passes _edays(ticker) from the
                         earnings-calendar closure (engine.stock_fundamentals._load_earnings).
    archetype          ← rec["profile"]["archetype"]
    dna_class          ← dna_class_entry (T-1 by design)
    """
    _tech = rec.get("tech") or {}
    _pos = rec.get("positioning") or {}
    _pos_short = _pos.get("short") or {} if isinstance(_pos, dict) else {}
    _pos_insider = _pos.get("insider") or {} if isinstance(_pos, dict) else {}
    _profile = rec.get("profile") or {}
    _gex = rec.get("gex") or {}
    _sm = rec.get("smart_money") or {}
    _bo = rec.get("beneficial_ownership") or {}

    # ---- ret_21d: FRACTION from OHLCV close; fallback to None ----
    ret_21d: "float | None" = None
    if ohlcv_df is not None and "close" in ohlcv_df.columns and len(ohlcv_df) >= 22:
        try:
            _c = ohlcv_df["close"].dropna()
            if len(_c) >= 22:
                ret_21d = float(_c.iloc[-1] / _c.iloc[-22] - 1.0)
        except Exception:  # noqa: BLE001
            pass

    # ---- months_underwater: bars/21 from entry_primitives.time_underwater_series ----
    months_underwater: "float | None" = None
    if ohlcv_df is not None and "close" in ohlcv_df.columns and len(ohlcv_df) >= 300:
        try:
            from engine.entry_primitives import time_underwater_series  # noqa: PLC0415
            _c_all = ohlcv_df["close"].dropna()
            _tu = time_underwater_series(_c_all)
            if _tu is not None and len(_tu) > 0:
                _last = _tu.iloc[-1]
                if _last is not None and not (isinstance(_last, float) and __import__("math").isnan(_last)):
                    months_underwater = float(_last) / 21.0
        except Exception:  # noqa: BLE001
            pass

    # ---- Positioning map per assess() contract ----
    _positioning = {
        "short_pct_float": _pos_short.get("pct_float"),
        "days_to_cover": _pos_short.get("days_to_cover"),
        "insider_net_usd_mn": _pos_insider.get("net_mn"),
        "insider_cluster": _pos_insider.get("cluster"),
        "insider_n_buyers": _pos_insider.get("n_buyers"),
    }

    # ---- smart_money map (ownership_hhi, n_holders from 13F) ----
    _sm_holders = _sm.get("holders") or []
    _smart_money = {
        "ownership_hhi": _sm.get("ownership_hhi"),
        "n_holders": len(_sm_holders) if _sm_holders else None,
    }

    # ---- GEX map ----
    _gex_map: "dict | None" = None
    if _gex:
        _gex_regime = _gex.get("gamma_regime") or _gex.get("regime")
        _gex_dist = _gex.get("dist_to_flip_pct")
        _gex_map = {"gamma_regime": _gex_regime, "dist_to_flip_pct": _gex_dist}

    # ---- tech map per assess() contract ----
    _tech_map = {
        "hv_pctile": _tech.get("hv_pctile"),
        "rel_volume": _tech.get("rel_volume"),
        "obv_slope_up": _tech.get("obv_slope_up"),
        "off_52w_high_pct": _tech.get("off_52w_high_pct"),
        "ret_21d": ret_21d,
        "months_underwater": months_underwater,
        "vol_squeeze_state": (rec.get("vol_squeeze") or {}).get("state"),
        "ladder_state": (rec.get("ladder") or {}).get("state"),
    }

    # ---- basket_membership: list of slug strings ----
    _bsk = [m["slug"] for m in (bsk_mem_entry or []) if m.get("slug")]

    # ---- events: days_to_earnings from caller-provided parameter ----
    # Caller passes _edays(ticker) from the earnings-calendar closure.
    # rec["tech"] never carries days_to_earnings; rec["profile"]["earnings"]["days_to_next"]
    # is also never populated — both were dead sourcing paths (W2b fix finding 2).
    _events: "dict | None" = None
    if days_to_earnings is not None:
        try:
            _events = {"days_to_earnings": int(days_to_earnings)}
        except (TypeError, ValueError):
            pass

    # ---- market_cap ----
    _mktcap: "float | None" = None
    _mktcap_bn = _profile.get("mktcap_bn")
    if _mktcap_bn is not None:
        try:
            _mktcap = float(_mktcap_bn) * 1e9
        except (TypeError, ValueError):
            pass

    # ---- archetype ----
    _arch = _profile.get("archetype")

    # ---- bo_regime ----
    _bo_regime = _bo.get("regime") if _bo else None

    # ---- dna_class dict for assess() ----
    _dna: "dict | None" = None
    if dna_class_entry and dna_class_entry.get("dna_class"):
        _dna = {
            "key": dna_class_entry["dna_class"],
            "style_regime": dna_class_entry.get("style_regime"),
            "as_of": dna_class_entry.get("as_of", "T-1"),
        }

    return {
        "as_of": as_of,
        "path_features": None,  # filled by caller after path_personality.features()
        "archetype": _arch,
        "dna_class": _dna,
        "positioning": _positioning,
        "smart_money": _smart_money,
        "basket_membership": _bsk if _bsk else None,
        "etf_weight_max": etf_wt,
        "attention_z": None,      # wiki attention not yet wired; forward-ledger only
        "bo_regime": _bo_regime,
        "gex": _gex_map,
        "events": _events,
        "tech": _tech_map,
        "oracle_episode_active": oracle_active,
        "market_cap": _mktcap,
    }


def _stamp_personality_forward_ledger(
    sp_by_ticker: "dict[str, dict]",
    build_date: "str | None",
    cfg,
) -> None:
    """Append per-fire personality stamps to data/stock_personality/forward_ledger.parquet.

    Reads data/signal_archive/track_record.parquet for recent buy/rebuy fires.
    For each fire with a personality object, appends one row.
    Deduped on (ticker, date, type); single-writer (nightly engine job is sole advancer).
    Fail-open: any error is logged at warning and the ledger is left unchanged.

    CONSTRAINT the filter must honor: track_record appends entry rows RETROACTIVELY —
    buy/rebuy markers are skipped while quality == "pending" (engine/track_record.py
    anti-repaint gate), so a fire dated D typically lands in the parquet only ~3-4
    sessions later. A same-day `date == build_date` filter therefore matches nothing,
    ever (2026-07-12 audit: TTD 07-06 fire appeared in the 07-10 commit, SBUX 07-07 in
    the 07-12 commit). We scan a bounded lookback window and rely on the dedup key for
    exactly-once appends; `stamped_on` records the actual write date so the personality
    lag vs the fire date stays visible (personality read is CURRENT at stamp time, a few
    sessions after the fire — base personality is slow-moving).

    Nightly engine job is the SOLE ADVANCER of this ledger.
    Intraday lanes DISCARD data/ writes per house law.
    """
    if not sp_by_ticker or not build_date:
        return
    try:
        _tr_path = cfg.data_dir() / "signal_archive" / "track_record.parquet"
        if not _tr_path.exists():
            return
        _tr = pd.read_parquet(_tr_path, columns=["ticker", "date", "type"])
        # Lookback floor: 30 days covers the pending-quality lag with wide margin;
        # 2026-07-06 = ledger wire-in date (never backfill pre-wiring history).
        try:
            _lb = (date.fromisoformat(str(build_date)[:10]) - timedelta(days=30)).isoformat()
        except Exception:  # noqa: BLE001 — unparseable build_date → wire-in floor only
            _lb = "2026-07-06"
        _floor = max(_lb, "2026-07-06")
        _dates = _tr["date"].astype(str)
        _today_fires = _tr[
            (_dates >= _floor) &
            (_dates <= str(build_date)) &
            (_tr["type"].isin(["buy", "rebuy"]))
        ]
        if _today_fires.empty:
            return
        _rows = []
        for _, _fire in _today_fires.iterrows():
            _ftk = str(_fire["ticker"])
            _sp = sp_by_ticker.get(_ftk)
            if _sp is None:
                continue
            _base = _sp.get("base") or {}
            _cm = _sp.get("current_mode") or {}
            _chart = (_base.get("chart_personality") or {}).get("labels")
            _own = (_base.get("ownership_habitat") or {}).get("labels")
            _micro = (_base.get("microstructure") or {}).get("labels")
            _rows.append({
                "ticker": _ftk,
                "date": str(_fire["date"]),
                "type": str(_fire["type"]),
                "archetype": (_base.get("archetype") or {}).get("key"),
                "dna_class": (_base.get("dna_class") or {}).get("key"),
                "chart": json.dumps(_chart) if _chart is not None else None,
                "ownership": json.dumps(_own) if _own is not None else None,
                "micro": json.dumps(_micro) if _micro is not None else None,
                "modes": json.dumps(_cm.get("modes")) if _cm.get("modes") is not None else None,
                "lineage": "stock_personality.v1",
                "stamped_on": str(build_date),
            })
        if not _rows:
            return
        _new_df = pd.DataFrame(_rows)
        _fl_path = cfg.data_dir() / "stock_personality" / "forward_ledger.parquet"
        _fl_path.parent.mkdir(parents=True, exist_ok=True)
        _appended = len(_new_df)  # tracks post-dedup rows actually written (default: all)
        if _fl_path.exists():
            try:
                _exist = pd.read_parquet(_fl_path)
                # Dedup on (ticker, date, type)
                _exist_keys = set(zip(_exist["ticker"], _exist["date"], _exist["type"]))
                _new_df = _new_df[
                    ~_new_df.apply(
                        lambda r: (r["ticker"], r["date"], r["type"]) in _exist_keys, axis=1
                    )
                ]
                _appended = len(_new_df)  # post-dedup: rows actually being appended
                if not _new_df.empty:
                    _new_df = pd.concat([_exist, _new_df], ignore_index=True)
                else:
                    _new_df = _exist
            except Exception:  # noqa: BLE001 — corrupt existing → overwrite
                pass
        _new_df.to_parquet(_fl_path, compression="snappy", index=False)
        log.info("personality forward ledger: +%d new rows (total=%d)", _appended, len(_new_df))
    except Exception as _fl_e:  # noqa: BLE001 — additive, never fatal
        log.warning("personality forward ledger stamp failed (%s)", _fl_e)


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    outdir = site / "stockdata"
    outdir.mkdir(parents=True, exist_ok=True)

    # W8b: load provenance sidecar context once (shared across all tickers).
    # Fail-open: missing neuralweb artifacts → empty context → no provenance rows.
    try:
        from engine.provenance_sidecar import load_context as _load_prov_ctx
        _prov_ctx = _load_prov_ctx(config.ROOT)
        log.info("provenance sidecar context loaded (kernel_engines=%d spine_tickers=%d)",
                 len(_prov_ctx.kernel), len(_prov_ctx.spine_latest))
    except Exception as _pe:  # noqa: BLE001 — additive, never fatal
        _prov_ctx = None
        log.warning("provenance sidecar context load failed (%s); provenance rows skipped", _pe)

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
                # audit #25: the board TIEBREAK must use the scorecard-passing IC-weighted
                # composite (composite_rank), NOT the blind equal-weight composite (ic_ir -0.049,
                # anti-predictive). Fall back to composite only if the rank composite is absent.
                _cz = _r.get("composite_rank")
                if _cz is None:
                    _cz = _r.get("composite")
                if _cz is not None:
                    factor_z[_r["ticker"]] = _cz
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
    # ---- stock_personality.v1 pre-loop loads -----------------------------------
    # All hoisted outside the loop; never re-read per ticker.
    _sp_dna_class: "dict[str, dict]" = {}      # ticker -> {key, style_regime, as_of} from dna_class.json (T-1)
    _sp_dna_as_of: "str | None" = None
    try:
        _dna_p = site / "factordata" / "dna_class.json"
        if _dna_p.exists():
            _dna_doc = json.loads(_dna_p.read_text())
            _sp_dna_class = _dna_doc.get("per_ticker") or {}
            _sp_dna_as_of = _dna_doc.get("as_of")
            log.info("dna_class.json loaded: %d tickers (as_of=%s)", len(_sp_dna_class), _sp_dna_as_of)
    except Exception as _sp_dna_e:  # noqa: BLE001 — additive, never fatal
        log.debug("dna_class.json load skipped (%s)", _sp_dna_e)
    # ETF weight max per ticker from newest data/etf_holdings/<ETF>/*.parquet snapshots.
    _sp_etf_wt: "dict[str, float]" = {}         # ticker -> max weight_pct across all ETFs
    try:
        _etf_dir = config.data_dir() / "etf_holdings"
        if _etf_dir.exists():
            _etf_frames: list["pd.DataFrame"] = []
            for _etf_sub in _etf_dir.iterdir():
                if not _etf_sub.is_dir():
                    continue
                _snaps = sorted(_etf_sub.glob("*.parquet"))
                if not _snaps:
                    continue
                try:
                    _df = pd.read_parquet(_snaps[-1])
                    if "ticker" in _df.columns and "weight_pct" in _df.columns:
                        _etf_frames.append(_df[["ticker", "weight_pct"]])
                except Exception:  # noqa: BLE001
                    pass
            if _etf_frames:
                _etf_all = pd.concat(_etf_frames, ignore_index=True)
                _sp_etf_wt = _etf_all.groupby("ticker")["weight_pct"].max().to_dict()
                log.info("ETF weight max: %d tickers from etf_holdings snapshots", len(_sp_etf_wt))
    except Exception as _sp_etf_e:  # noqa: BLE001 — additive, never fatal
        log.debug("ETF weight max load skipped (%s)", _sp_etf_e)
    # Oracle episode-active map: sector -> bool (is any complex for this sector in active episode)
    # Reads site/basketdata/oracle_state.json once. Sector mapping mirrors engine.spotlight.GICS_TO_ETF
    # (ETF-based proxy). A complex is "active" when state not in {quiet, None}.
    # Cheaply importable: direct JSON read (no engine module).
    # Semantics: dict contains only sectors that ARE in GICS_TO_ETF; .get(sector) returns
    # None (unknown) for sectors outside the mapped key set — not False (mapped-and-quiet).
    _sp_oracle_active: "dict[str, bool]" = {}   # GICS sector string -> bool; absent = unknown
    try:
        _oracle_st_p = site / "basketdata" / "oracle_state.json"
        if _oracle_st_p.exists():
            _oracle_doc = json.loads(_oracle_st_p.read_text())
            # Map ETF -> bool (any complex with that ETF code has active episode)
            from engine.spotlight import GICS_TO_ETF as _GICS_TO_ETF  # noqa: PLC0415
            # oracle complex ids approximate sector ETFs; use a hard mapping table for
            # the closed complex set (frozen in oracle state):
            _ORACLE_COMPLEX_TO_ETF: dict[str, str] = {
                "ai_compute": "XLK", "software": "XLK", "long_duration_growth": "XLK",
                "healthcare_defensive": "XLV",
                "consumer_staples_defensive": "XLP",
                "energy_commodities": "XLE",
                "financials_rates": "XLF",
                "short_duration_value": "XLF",
            }
            _etf_active: set[str] = set()
            for _cx in (_oracle_doc.get("complexes") or []):
                _cstate = _cx.get("state")
                _cx_id = _cx.get("id", "")
                if _cstate and _cstate not in ("quiet",):
                    _cxetf = _ORACLE_COMPLEX_TO_ETF.get(_cx_id)
                    if _cxetf:
                        _etf_active.add(_cxetf)
                    else:
                        log.debug("oracle complex '%s' not in _ORACLE_COMPLEX_TO_ETF — update map if this is a new complex", _cx_id)
            # Invert GICS_TO_ETF: sector -> bool (only mapped sectors; absent = sector unknown)
            for _gs, _ge in _GICS_TO_ETF.items():
                _sp_oracle_active[_gs] = _ge in _etf_active
    except Exception as _sp_orc_e:  # noqa: BLE001 — additive, never fatal
        log.debug("oracle episode active map skipped (%s)", _sp_orc_e)
    # Species registry for setup_compatibility — loaded once.
    _sp_species_entries: "list[dict]" = []
    try:
        _sp_reg_p = config.data_dir() / "species" / "registry.json"
        if _sp_reg_p.exists():
            _sp_reg_doc = json.loads(_sp_reg_p.read_text())
            _sp_species_entries = _sp_reg_doc.get("species") or []
            log.info("species registry: %d entries loaded for setup_compatibility", len(_sp_species_entries))
    except Exception as _sp_reg_e:  # noqa: BLE001 — additive, never fatal
        log.debug("species registry load skipped (%s)", _sp_reg_e)
    # Personality pass timing accumulator (sum of per-ticker personality try-block elapsed)
    _sp_elapsed_acc: float = 0.0
    _sp_n_tickers = 0
    _sp_n_skipped = 0
    # Container for personality objects (ticker -> personality dict) for post-loop passes
    _sp_by_ticker: "dict[str, dict]" = {}
    # -------------------------------------------------------------------
    spotlight_ctx = _spotlight_context()        # theme intel + sector stage for the spotlight tilt
    # Sector Pulse — per-ticker theme-heat context for the stockdata JSON and standout cards.
    # Computed ONCE here: build_pulse + ticker_themes, then looked up per name.
    # DISPLAY-ONLY; additive + never-fatal (pulse failure cannot break the stockdata build).
    _sector_pulse_map: "dict[str, dict]" = {}   # ticker → compact pulse block (or absent)
    _sector_pulse_as_of: "str | None" = None
    try:
        from engine.sector_pulse import build_pulse as _sp_build, ticker_themes as _sp_themes
        _sp_payload = _sp_build("us")
        if _sp_payload:
            _sector_pulse_as_of = _sp_payload.get("as_of")
            _sp_n_themes = _sp_payload.get("n_themes")
            # Index pulse rows by theme id for O(1) lookup below
            _sp_by_id: "dict[str, dict]" = {r["id"]: r for r in (_sp_payload.get("themes") or [])}
            # Map each ticker → list of theme ids it belongs to (point-in-time)
            _sp_tk_map = _sp_themes("us")
            for _sp_tick, _sp_ids in _sp_tk_map.items():
                if not _sp_ids:
                    continue
                # Best = lowest rank number (highest position) among all of the ticker's themes
                _sp_cands = [_sp_by_id[tid] for tid in _sp_ids if tid in _sp_by_id]
                if not _sp_cands:
                    continue
                _sp_best = min(_sp_cands, key=lambda r: (r["rank"] is None, r["rank"] or 9999))
                _sector_pulse_map[_sp_tick] = {
                    "as_of": _sector_pulse_as_of,
                    "theme_id": _sp_best.get("id"),
                    "theme_name": _sp_best.get("name"),
                    "theme_name_zh": _sp_best.get("name_zh"),
                    "heat": _sp_best.get("heat"),
                    "label": _sp_best.get("label"),
                    "reco": _sp_best.get("reco"),
                    "rank": _sp_best.get("rank"),
                    "n_themes": _sp_n_themes,
                    "rank_delta_5d": _sp_best.get("rank_delta_5d"),
                    "theme_ids": list(_sp_ids),
                }
        log.info("sector_pulse: %d tickers mapped to themes", len(_sector_pulse_map))
    except Exception as _spe:  # noqa: BLE001 — additive; pulse failure must not break the build
        log.warning("sector_pulse precompute skipped (%s)", _spe)
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
    # W0c — Government-funding exposure chip (engine/gov_exposure.py).
    # DISPLAY-ONLY; evidence_tier=fingerprint (annual XBRL + monthly awards lag);
    # score_cap=60.  Absent data or ticker not in USAspending coverage → no chip.
    # R9a caveat (curated-alias matching) + R9e caveat (price-live mktcap vs lagged
    # awards) are rendered on-page in stock.html.j2.
    _gov_obs:  "pd.DataFrame | None" = None
    _gov_gl:   "pd.DataFrame | None" = None
    _gov_mktcap: dict[str, float] = {}
    try:
        from engine import gov_exposure as _gov_exp
        _obs_p = config.data_dir() / "usaspending" / "obligations.parquet"
        _gl_p  = config.data_dir() / "usaspending" / "grants_loans.parquet"
        if _obs_p.exists():
            _gov_obs = pd.read_parquet(_obs_p)
        if _gl_p.exists():
            _gov_gl = pd.read_parquet(_gl_p)
        _fj_p = site / "factordata" / "factors.json"
        if _fj_p.exists():
            for _fr in (json.loads(_fj_p.read_text()) or {}).get("table", []):
                _t = _fr.get("ticker")
                _mc = _fr.get("mktcap_bn")
                if _t and _mc:
                    _gov_mktcap[_t] = float(_mc) * 1e9  # factors.json is in $B
    except Exception as _gve:  # noqa: BLE001 — additive, never fatal
        log.warning("gov_exposure preload skipped (%s)", _gve)
    # W3 evidence-stack: news burst (DISPLAY-ONLY; 17-ticker coverage today).
    # site/news/by_ticker.json schema: {schema, is_context_only, asof, tickers}.
    # Absent file or missing ticker => chip absent.
    _news_p = site / "news" / "by_ticker.json"
    news_map: dict[str, dict] = {}
    if _news_p.exists():
        try:
            news_map = json.loads(_news_p.read_text()).get("tickers", {})
        except Exception as _ne:  # noqa: BLE001 — additive, never fatal
            log.warning("news/by_ticker.json unreadable (%s)", _ne)
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
        if _no_drip():
            log.info("revision drip skipped (render lane — data/ write discarded)")
        else:
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
        # sorted: set iteration is hash-seed-dependent per run; row order feeds
        # float summation in the sector z-scores, so pin it for reproducibility
        for _t in sorted(set(_factor_legs) | set(alpha_pt) | set(revision_z)):
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
    _liq_map: dict[str, dict] = {}              # P0.3 liquidity/capacity hygiene (display-only, R10)
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

    # ---- flow_score pre-loop load (FS-4 Lane C, schema flow_score.stock/v1) --------
    # Loads ledger + scores once; looked up per-ticker inside the main rec loop below.
    # OMITTED entirely (block never written) when:
    #   (a) flow_signals ledger absent, OR
    #   (b) config/flow_score.yml scoring.enabled is False (kill-switch), OR
    #   (c) any exception during load — additive block must never break the stockdata build.
    # PRE-GATE LAW (FS-R3 / amendment §9): score stays null until FS-5 — the block
    # deliberately does NOT read scores.parquet, so no calibrated number can leak
    # onto a user surface before the gauntlet passes.
    _fs_ledger_by_root: "dict[str, dict]" = {}   # root → {n_events, since}
    _fs_scoring_enabled: bool = False             # kill-switch default = off until file exists
    try:
        import yaml as _yaml  # noqa: PLC0415
        _fs_cfg_path = Path(__file__).resolve().parent.parent / "config" / "flow_score.yml"
        if _fs_cfg_path.exists():
            _fs_yml = _yaml.safe_load(_fs_cfg_path.read_text()) or {}
            _fs_scoring_enabled = bool((_fs_yml.get("scoring") or {}).get("enabled", False))
        _fs_ledger_path = config.data_dir() / "flow_signals" / "ledger.parquet"
        if _fs_ledger_path.exists():
            _fs_ldf = pd.read_parquet(_fs_ledger_path, columns=["root", "session_date"])
            _fs_ldf = _fs_ldf.dropna(subset=["root"])
            for _fs_root, _fs_grp in _fs_ldf.groupby("root"):
                _fs_ledger_by_root[str(_fs_root)] = {
                    "n_events": int(len(_fs_grp)),
                    "since": str(_fs_grp["session_date"].min()),
                }
            log.info("flow_score: ledger loaded — %d roots, %d events",
                     len(_fs_ledger_by_root), len(_fs_ldf))
    except Exception as _fs_load_e:  # noqa: BLE001 — additive; must not break the stockdata build
        log.warning("flow_score pre-load skipped (%s)", _fs_load_e)
        _fs_ledger_by_root = {}
        _fs_scoring_enabled = False

    sig_verdict: dict[str, dict] = {}   # owner's confluence cascade verdict per name (T1->T4)
    _coil_d: dict[str, float | None] = {}       # weekly StochRSI D per name (for cohort fractions)
    _coil_wash: dict[str, bool | None] = {}     # washout context per name
    _coil_div: dict[str, bool] = {}             # bullish divergence per name
    _coil_sector: dict[str, str | None] = {}    # sector per name (for cohort grouping)
    _coil_fire: dict[str, dict] = {}            # wave-4 COILED-FIRE marker per name (display only)
    # G6a donor-sector: collect per-name close series (same sector map as _coil_sector)
    _donor_closes: dict[str, "pd.Series"] = {}  # close series for donor composite
    # W6-C HOLD tracker: per-name basing state (INTACT/LAUNCHED/BROKEN) + invalidation
    _hold_state: dict[str, dict] = {}           # hold dict per name (None when no anchor)
    # W3 evidence-stack: per-ticker evidence fields collected during the rec loop.
    # These are joined to ALL board rows (buy + watch) after cand assembly.
    # Keys: gex_confirm, altdata, sue_fresh_days, news_burst, smartmoney_chip, stop_guidance.
    # Insider fields (insider_buyers/bps/net_mn) are already attached to the cand row at L1248.
    # evidence_health carries staleness markers: {source: 'stale-Nd'} when the artifact is stale.
    _w3_evidence: dict[str, dict] = {}   # ticker -> evidence payload for board-row propagation
    for (ticker, close, high, name, sector), rec in zip(uni, recs):
        if rec is None:
            failed += 1
            continue
        # COMBINE: the confluence T1->T4 cascade is computed alongside main's bottoming-alignment
        # gate. It NEVER changes which names are eligible (alignment stays the inclusion gate) —
        # it only adds the per-card tier badge and re-ranks WITHIN the aligned set (below).
        sig_verdict[ticker] = signal_gate.gate(ticker, close)
        # W6-C HOLD tracker: derive anchor from the §7 take/pending marker (open buy only),
        # fall back to the last 3D cross. Additive + graceful: failure -> None entry.
        try:
            _sv = sig_verdict[ticker]
            _last_m = _sv.get("last")
            _is_buy = bool(_last_m and _last_m.get("type") in ("buy", "rebuy"))
            _anchor = _last_m.get("date") if _is_buy else None
            _hs = hold_engine.hold_state(close, anchor_date=_anchor, last_cross_fallback=True)
            if _hs is not None:
                _hold_state[ticker] = _hs
        except Exception:
            pass
        # COILED wave-2 ranking bonus: collect per-name inputs for cohort computation below.
        # All four lines are guarded as one block; failure leaves dicts empty for this name.
        # Wave-4: also collect fire_recent for the COILED-FIRE display chip (display only,
        # NO rank/bonus change — the ledger grades this live before it earns weight).
        try:
            _coil_d[ticker]      = coiled.weekly_d_last(close)
            _coil_wash[ticker]   = coiled.washout_ctx(close)
            _coil_div[ticker]    = coiled.bull_div(close)
            _coil_sector[ticker] = sector or None
            _coil_fire[ticker]   = coiled.fire_recent(close)
            # G6a donor: retain close series for sector-mapped names (reuse _coil_sector)
            if sector:
                _donor_closes[ticker] = close
        except Exception:
            pass
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
        # ---- W5b liquidity chip (DISPLAY-ONLY, zero rank/gate power) ---------------
        # engine.liquidity_chip: 20-session MEDIAN dollar volume (close x volume),
        # liquidity tier (deep/ok/thin/illiquid), and days-to-build at $100k and $1M
        # clips assuming the investor consumes at most 10 % of ADV per day.
        # Also retains the legacy adv_dollar_21d MEAN + days_to_exit for backward compat
        # (stock.html and the detail page may still read these fields).
        # Available only when _ohlcv has a volume column (data/stocks names); breadth-
        # cache-only names (close-only) silently skip — field absent is the honest answer.
        try:
            if _ohlcv is not None and "volume" in _ohlcv.columns:
                from engine import liquidity_chip as _lc
                _lchip = _lc.compute(_ohlcv["close"], _ohlcv["volume"])
                if _lchip is not None:
                    # W5b primary fields
                    _liq_map[ticker] = _lchip
                    # Legacy mean-based fields (backward compat — kept alongside the new median)
                    _vol21 = _ohlcv["volume"].tail(21).dropna()
                    _close21 = _ohlcv["close"].tail(21).dropna()
                    _n21 = min(len(_vol21), len(_close21))
                    if _n21 >= 5:
                        _adv_dv21 = float(
                            (_vol21.iloc[-_n21:].values * _close21.iloc[-_n21:].values).mean()
                        )
                        _adv_10pct21 = _adv_dv21 * 0.10
                        _dte21 = (100_000 / _adv_10pct21) if _adv_10pct21 > 0 else None
                        _liq_map[ticker]["adv_dollar_21d"] = round(_adv_dv21, 0)
                        if _dte21 is not None:
                            _liq_map[ticker]["days_to_exit_at_10pct_adv"] = round(_dte21, 1)
        except Exception as _liqe:  # noqa: BLE001 — hygiene fields; never fatal
            log.debug("liquidity chip for %s skipped (%s)", ticker, _liqe)
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
        # basket_alloc: the allocation/trend-gate state used for the VALIDATED size de-risk
        # caution (engine.stock_score._basket_risk) and Mastermind display.
        #
        # SELECTION RULE: always use the BEST-RANKED basket (lowest rotation rank = most
        # in-favor) from the name's memberships, regardless of which basket drives the
        # spotlight tilt. This keeps the caution anchored to the name's PRIMARY narrative.
        #
        # Why NOT the spotlight max-|tilt| basket: when a name belongs to a minor basket
        # that is currently fading (e.g. NVDA tagged into quantum_computing alongside its
        # primary ai_semiconductors membership), the spotlight engine may pick that minor
        # basket because its negative tilt is the largest |z| — but attributing the
        # de-risk caution to that minor basket is a credibility misattribution. The
        # spotlight tilt (used for scoring) is UNCHANGED; only the caution anchor differs.
        _alloc_by_id = spotlight_ctx.get("alloc_by_id") or {}
        _bslug = None
        if bsk_mem.get(ticker):
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
        # ---- Confluence cascade verdict (T1->T4) on the per-stock JSON ---------
        # The owner's MACD-2D x StochRSI-3D gate (already computed above as sig_verdict),
        # persisted per name so the theme/basket-detail Holdings table can surface a fresh
        # confluence cross to the top — the same tier the standout board ranks by. Slim,
        # allow_nan-safe subset (buy_signal); mirrors rec["entry_signal"]. None-tolerant.
        rec["signal"] = signal_gate.buy_signal(sig_verdict.get(ticker))
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
        # ---- Government-funding exposure chip (W0c, display-only) -----------
        # Fingerprint-class (annual XBRL lag + monthly awards lag); score_cap=60.
        # R9a/R9e caveats rendered in template via data-tip-en/data-tip-zh.
        if _gov_obs is not None and _gov_mktcap:
            try:
                _ge = _gov_exp.funding_to_mktcap(
                    ticker, _gov_obs, _gov_gl, _gov_mktcap)
                if _ge:
                    rec["gov_exposure"] = _ge
            except Exception as _gee:  # noqa: BLE001 — additive, never fatal
                log.warning("gov_exposure chip for %s failed (%s)", ticker, _gee)
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
        # ---- stock_personality.v1 pass (display-only; fail-open; never fatal) ----
        # Runs after dt_contra so all prior blocks (tech, vol_squeeze, gex, positioning,
        # smart_money, basket_membership) are already on rec. OHLCV frame reuses _ohlcv
        # (loaded above for the tech/squeeze pass). path_personality.features() computes
        # only trailing windows (cheap snapshot API — no full-history series).
        _sp_tick_t0 = time.time()
        try:
            import engine.path_personality as _ppath  # noqa: PLC0415
            import engine.stock_personality as _spers  # noqa: PLC0415
            # Build OHLCV frame for path_personality: prefer _ohlcv (full OHLCV);
            # fallback to a close-only DataFrame from the universe's close series.
            _sp_ohlcv = _ohlcv
            if _sp_ohlcv is None:
                _sp_ohlcv = pd.DataFrame({"close": close})
            # Compute path features (cheap snapshot — only trailing windows)
            _pfeats = _ppath.features(_sp_ohlcv)
            # Build inputs map from rec
            _sp_asof = str(rec.get("asof") or alpha_asof or "")
            _sp_inputs = _personality_inputs(
                ticker, rec, _sp_ohlcv, _sp_asof,
                dna_class_entry=_sp_dna_class.get(ticker),
                bsk_mem_entry=bsk_mem.get(ticker),
                etf_wt=_sp_etf_wt.get(ticker),
                oracle_active=_sp_oracle_active.get(sector),
                days_to_earnings=_edays(ticker),
            )
            _sp_inputs["path_features"] = _pfeats
            _personality = _spers.assess(ticker, **_sp_inputs)
            _personality["setup_compatibility"] = _spers.setup_compatibility(
                _personality, _sp_species_entries
            )
            rec["personality"] = _personality
            _sp_by_ticker[ticker] = _personality
            _sp_n_tickers += 1
            _sp_elapsed_acc += time.time() - _sp_tick_t0
        except Exception as _sp_e:  # noqa: BLE001 — display chip; NEVER fatal
            _sp_n_skipped += 1
            # WARNING (not debug) so a systemic failure surfaces in nightly logs,
            # which run at INFO. First skip carries the full traceback for diagnosis;
            # skips beyond 10 drop to debug so a full-universe failure can't flood
            # the log — the end-of-loop summary always prints the skip count.
            if _sp_n_skipped == 1:
                log.warning("personality pass for %s skipped (%s: %s)",
                            ticker, type(_sp_e).__name__, _sp_e, exc_info=True)
            elif _sp_n_skipped <= 10:
                log.warning("personality pass for %s skipped (%s: %s)",
                            ticker, type(_sp_e).__name__, _sp_e)
            else:
                log.debug("personality pass for %s skipped (%s: %s)",
                          ticker, type(_sp_e).__name__, _sp_e)
        _tech = rec.get("tech") or {}
        disp_map[ticker] = {
            "price": _tech.get("price"), "off_high": _tech.get("off_52w_high_pct"),
            "spark_svg": _spark_svg(list(close.tail(64).values),
                                    color=_SPARK_COLOR.get((rec.get("ladder") or {}).get("dir"), "var(--link)"))}
        ladder_rows.append(ticker_alerts.ladder_row(ticker, rec.get("ladder"), rec.get("asof")))
        # W6-C HOLD: attach per-name basing state to the stockdata JSON (BLOCKED names get it too)
        if _hold_state.get(ticker):
            rec["hold"] = _hold_state[ticker]
        # W2 PR-J — Long-Hold Thesis Layer: entry_clock annotation (display-only).
        # Days since the most recent tactical buy/rebuy marker fire (signal_gate).
        # horizon_role=hold_thesis; must NOT feed entry-stack scored surfaces (LH-R1).
        try:
            from engine.long_hold_clocks import entry_clock as _ec  # noqa: PLC0415
            _eck = _ec(sig_verdict.get(ticker))
            if _eck is not None:
                rec["entry_clock"] = _eck
        except Exception:  # noqa: BLE001 — additive display chip; never fatal
            pass
        # Sector Pulse — top-level block in each stockdata JSON (DISPLAY-ONLY, never scored).
        # Null/absent when the ticker maps to no live theme. Never fatal.
        try:
            _sp_row = _sector_pulse_map.get(ticker) or _sector_pulse_map.get(ticker.upper())
            if _sp_row:
                rec["sector_pulse"] = _sp_row
        except Exception as _spe2:  # noqa: BLE001 — additive; must not break the stockdata build
            pass
        # ---- confluence block (frozen Terminal contract, 2026-07-06) ---------------
        # Top-level block in each stockdata JSON consumed by the charting-app Terminal.
        # Shape: {tier, weight, sub, ticks, bars_to_cross, provisional, not_topped,
        #         htf_s1, htf_s2, asof} (null-safe; all keys always present).
        # Source: signal_gate verdict already computed above. Keep cheap — no new loads.
        try:
            _sv = sig_verdict.get(ticker) or {}
            rec["confluence"] = {
                "tier": _sv.get("tier_cascade"),
                "weight": _sv.get("weight"),
                "sub": _sv.get("tier_sub"),
                "ticks": _sv.get("ticks"),
                "bars_to_cross": _sv.get("bars_to_cross"),
                "provisional": bool(_sv.get("provisional")),
                "not_topped": bool(_sv.get("not_topped", True)),
                "htf_s1": bool(_sv.get("htf_s1", False)),
                "htf_s2": bool(_sv.get("htf_s2", False)),
                "asof": _sv.get("asof"),
            }
        except Exception:  # noqa: BLE001 — additive; never fatal
            rec["confluence"] = {"tier": None, "weight": None, "sub": None, "ticks": None,
                                 "bars_to_cross": None, "provisional": False,
                                 "not_topped": True, "htf_s1": False, "htf_s2": False,
                                 "asof": None}
        # ---- sniper pre-compute (frozen Terminal contract, 2026-07-06) -----------
        # Compute w2_washout/w2_stoch_d + days_since_63d_low here (close is in scope).
        # coiled is deferred to after coiled_by is built (after the main loop) and injected
        # in the final to_write loop. Store partial sniper block now; complete later.
        try:
            from engine import setup_tier as _st  # lazy import; module cached after first use
            _ws = _st.w_setup(close)
            _w2_washout = False
            _w2_stoch_d: float | None = None
            if _ws:
                _w2d = (_ws.get("w2") or {})
                _stoch_val = _w2d.get("stoch")
                if _stoch_val is not None:
                    _w2_washout = bool(_stoch_val <= _st.W2_STOCH_WASHOUT)
                    _w2_stoch_d = float(_stoch_val)
            # days_since_63d_low: trading sessions since close hit its 63-session low
            _ds63: int | None = None
            _c63 = close.dropna()
            if len(_c63) >= 63:
                _w63 = _c63.iloc[-63:]
                _low63_pos = int(_w63.argmin())
                _ds63 = int(len(_w63) - 1 - _low63_pos)
            _asof_snap = str(close.index[-1].date()) if len(close) else None
            rec["sniper"] = {
                "w2_washout": _w2_washout,
                "w2_stoch_d": _w2_stoch_d,
                "days_since_63d_low": _ds63,
                "coiled": None,          # filled after coiled_by is computed below
                "asof": _asof_snap,
            }
        except Exception:  # noqa: BLE001 — additive; never fatal
            rec["sniper"] = {"w2_washout": False, "w2_stoch_d": None,
                             "days_since_63d_low": None, "coiled": None, "asof": None}
        # ---- flow_score block (FS-4 Lane C, schema flow_score.stock/v1) ---------------
        # Additive: OMITTED (key absent) when ledger absent OR config/flow_score.yml
        # scoring.enabled is False (kill-switch) OR any exception.
        # Never writes a fake-neutral value — absent ledger => key simply not present.
        # PRE-GATE LAW (FS-R3): score is display-only; must not feed any ranker/sizer/gate.
        if _fs_ledger_by_root and _fs_scoring_enabled:
            try:
                _fs_entry = _fs_ledger_by_root.get(ticker) or _fs_ledger_by_root.get(ticker.upper())
                if _fs_entry is not None:
                    # PRE-GATE LAW (FS-R3 / amendment §9): the flow_score.stock/v1
                    # block is a "building_history" receipt only until FS-5 gauntlet
                    # passes.  score and n_similar must remain null (frozen contract).
                    # Wiring a live calibrated score here while status='building_history'
                    # would produce an internally inconsistent block and surface a
                    # pre-gate number on a user-facing page.  gate.json.scored stays
                    # false; do not populate score until the interface contract is
                    # amended at FS-5.
                    _fs_block: dict = {
                        "schema": "flow_score.stock/v1",
                        "status": "building_history",
                        "n_events": _fs_entry["n_events"],
                        "since": _fs_entry["since"],
                        "score": None,
                        "n_similar": None,
                        "asof": str(pd.Timestamp.now(tz="UTC").date()),
                    }
                    rec["flow_score"] = _fs_block
            except Exception as _fs_e:  # noqa: BLE001 — additive; never fatal
                log.debug("flow_score block skipped for %s (%s)", ticker, _fs_e)
        safe = ticker.replace("=", "_").replace("^", "_")
        to_write.append((safe, rec))            # deferred: write after percentile scoring
        idx = {"t": ticker, "n": name, "s": sector, "st": rec["ladder"]["state"]}
        if rec.get("alpha", {}).get("alpha") is not None:
            idx["a"] = rec["alpha"]["alpha"]          # alpha-z in the index for client ranking
        index.append(idx)
        # W3 evidence-stack: collect board-row fields from rec for propagation after assembly.
        # ZERO ordering/admission impact — display chips + grader strata only.
        # Stale/absent artifact => field absent + health marker; never a neutral default.
        try:
            _ev: dict = {}
            _ev_health: dict = {}
            # GEX confirmer (Source 2): propagate from rec (already computed above).
            # Scope: magnet-distance >= 5% OR regime == 'short' via gex_confirm.assess().
            _gc = rec.get("gex_confirm")
            if _gc:
                _ev["gex_confirm"] = _gc
            # Alt-data convergence (Source 3): convergence_score >= 2 across independent channels.
            # Reuse altdata_ctx (same as site/altdata/by_ticker.json tickers).
            _adv = altdata_ctx.get(ticker)
            if _adv and (_adv.get("convergence_score") or 0) >= 2:
                _ev["altdata"] = {
                    "convergence_score": _adv.get("convergence_score"),
                    "channels": _adv.get("channels"),
                    "weighted_score": _adv.get("weighted_score"),
                    "trump_linked": _adv.get("trump_linked"),
                }
            # SUE freshness (Source 4): attach sue_fresh_days alongside sue_z.
            # Both already available (sue_z dict + sue_fresh dict loaded above).
            _sz = sue_z.get(ticker)
            _sf = sue_fresh.get(ticker)
            if _sz is not None and _sf is not None and _sf <= 60:
                _ev["sue_fresh_days"] = _sf
            # News burst (Source 5): n_recent >= 3 fires chip.
            # Coverage is 17 tickers only (context chip; is_context_only=true).
            _nv = news_map.get(ticker)
            if _nv and (_nv.get("n_recent") or 0) >= 3:
                _ev["news_burst"] = {
                    "n_recent": _nv.get("n_recent"),
                    "sentiment_lean": _nv.get("sentiment_lean"),
                    "n_pos": _nv.get("n_pos"),
                    "n_neg": _nv.get("n_neg"),
                }
            # Anticipation stop-budget (Source 6): derive stop_guidance from GO horizons.
            # rec["anticipation"] is computed inside rec_for(). Propagate the stop-width
            # guidance (dd_avg / dd_tail) from the best direction_scored horizon.
            _ant = rec.get("anticipation")
            if _ant:
                try:
                    _horizons = (_ant.get("horizons") or {}).values()
                    _scored_h = [h for h in _horizons
                                 if h.get("direction_scored") and h.get("dd_avg") is not None]
                    if not _scored_h:
                        _scored_h = [h for h in _horizons if h.get("dd_avg") is not None]
                    if _scored_h:
                        # shortest validated horizon (fewest window days)
                        _best_h = min(_scored_h, key=lambda h: h.get("window_td") or 999)
                        _dda = _best_h.get("dd_avg")
                        _ddt = _best_h.get("dd_tail")
                        if _dda is not None:
                            _ev["stop_guidance"] = {
                                "pct": round(abs(float(_dda)) * 100, 1),
                                "tail_pct": round(abs(float(_ddt)) * 100, 1) if _ddt is not None else None,
                                "horizon": _best_h.get("window_td"),
                                "scored": bool(_best_h.get("direction_scored")),
                            }
                except Exception:  # noqa: BLE001 — display-only, never fatal
                    pass
            # Smartmoney 13F (Source 7): A/B-grade fund new/add action.
            # Already in rec["smart_money"] (joined above). Q1-2026 data — staleness caveat on chip.
            _sm = rec.get("smart_money")
            if _sm:
                _holders = _sm.get("holders") or []
                _ab_add = [h for h in _holders
                           if h.get("action") in ("new", "add")
                           and h.get("fund_grade") in ("A", "B")]
                if _ab_add:
                    _best_ab = min(_ab_add, key=lambda h: {"A": 0, "B": 1}.get(h.get("fund_grade"), 2))
                    _ev["smartmoney_chip"] = {
                        "action": _best_ab.get("action"),
                        "n_funds_adding": len(_ab_add),
                        "best_fund": _best_ab.get("fund_name"),
                        "best_grade": _best_ab.get("fund_grade"),
                        "period_end": _best_ab.get("period_end", "2026-03-31"),
                        "staleness_caveat": "Q1-2026 13F",
                    }
            if _ev_health:
                _ev["evidence_health"] = _ev_health
            if _ev:
                _w3_evidence[ticker] = _ev
        except Exception as _w3e:  # noqa: BLE001 — W3 evidence is additive, never fatal
            log.warning("W3 evidence collection for %s failed (%s)", ticker, _w3e)
        built += 1
    # ---- stock_personality.v1 benchmark gate ----------------------------------------
    # Skip-count summary at WARNING whenever any ticker skipped: a partial or
    # full-universe personality failure must be visible in nightly logs (INFO level),
    # never only at per-ticker debug (the 2026-07 "0 of 1,626" scare was undiagnosable
    # because every skip logged at debug).
    if _sp_n_skipped:
        log.warning("personality pass: %.1fs — %d ok, %d skipped of %d total",
                    _sp_elapsed_acc, _sp_n_tickers, _sp_n_skipped,
                    _sp_n_tickers + _sp_n_skipped)
    else:
        log.info("personality pass: %.1fs over %d tickers (0 skipped)",
                 _sp_elapsed_acc, _sp_n_tickers)
    # ---- stock_personality.v1 panel append ------------------------------------------
    # Append today's per-ticker label rows to data/stock_personality/panel/YYYY-MM/panel.parquet
    # (gitignored-local; R2-published via publish_r2). Fail-open: any write error is logged.
    if _sp_by_ticker:
        try:
            # PIT stamp: use alpha_asof (the trading-date source) so the (ticker, date) join
            # is correct.  The 02:00-UTC cron makes utcnow().date() = trading date + 1.
            if alpha_asof is None:
                log.warning("personality panel: alpha_asof is None — falling back to wall-clock date (PIT may be off by 1 day)")
                _today_str = str(pd.Timestamp.utcnow().date())
            else:
                _today_str = str(alpha_asof)[:10]
            _panel_month = _today_str[:7]   # "YYYY-MM"
            _panel_root = config.data_dir() / "stock_personality" / "panel" / _panel_month
            _panel_root.mkdir(parents=True, exist_ok=True)
            _panel_path = _panel_root / "panel.parquet"
            _panel_rows = []
            for _sp_tk, _sp_p in _sp_by_ticker.items():
                _base = _sp_p.get("base") or {}
                _cm = _sp_p.get("current_mode") or {}
                _chart_labels = (_base.get("chart_personality") or {}).get("labels")
                _own_labels = (_base.get("ownership_habitat") or {}).get("labels")
                _micro_labels = (_base.get("microstructure") or {}).get("labels")
                _modes = _cm.get("modes")
                _cov = (_sp_p.get("evidence") or {}).get("coverage") or {}
                _panel_rows.append({
                    "ticker": _sp_tk,
                    "date": _today_str,
                    "archetype_key": ((_base.get("archetype") or {}).get("key")),
                    "dna_class_key": ((_base.get("dna_class") or {}).get("key")),
                    "chart_labels": json.dumps(_chart_labels) if _chart_labels is not None else None,
                    "ownership_labels": json.dumps(_own_labels) if _own_labels is not None else None,
                    "micro_labels": json.dumps(_micro_labels) if _micro_labels is not None else None,
                    "modes": json.dumps(_modes) if _modes is not None else None,
                    "cov_archetype": _cov.get("archetype"),
                    "cov_dna": _cov.get("dna_class"),
                    "cov_ownership": _cov.get("ownership"),
                    "cov_micro": _cov.get("micro"),
                    "cov_chart": _cov.get("chart"),
                })
            _new_df = pd.DataFrame(_panel_rows)
            if _panel_path.exists():
                try:
                    _exist_df = pd.read_parquet(_panel_path)
                    # Drop same (ticker, date) rows before appending (dedup idempotent)
                    _exist_df = _exist_df[
                        ~(_exist_df["ticker"].isin(_new_df["ticker"]) &
                          (_exist_df["date"] == _today_str))
                    ]
                    _new_df = pd.concat([_exist_df, _new_df], ignore_index=True)
                except Exception:  # noqa: BLE001 — corrupt existing → overwrite
                    pass
            _new_df.to_parquet(_panel_path, compression="snappy", index=False)
            log.info("personality panel: wrote %d rows to %s", len(_new_df), _panel_path)
        except Exception as _sp_panel_e:  # noqa: BLE001 — additive, never fatal
            log.warning("personality panel write failed (%s)", _sp_panel_e)
    # ---- stock_personality.v1 site aggregate ----------------------------------------
    # Write site/factordata/stock_personality.json (slim, git-committed).
    try:
        if _sp_by_ticker:
            # PIT stamp: use alpha_asof (trading date) to match the panel row date.
            if alpha_asof is None:
                log.warning("stock_personality.json: alpha_asof is None — falling back to wall-clock date")
                _sp_today = str(pd.Timestamp.utcnow().date())
            else:
                _sp_today = str(alpha_asof)[:10]
            # Coverage fractions across universe
            _all_cov: dict[str, list[float]] = {}
            _all_arch: dict[str, int] = {}
            _all_dna: dict[str, int] = {}
            _all_chart: dict[str, int] = {}
            _all_own: dict[str, int] = {}
            _all_micro: dict[str, int] = {}
            _all_mode: dict[str, int] = {}
            _per_ticker: dict[str, dict] = {}
            for _sp_tk, _sp_p in _sp_by_ticker.items():
                _base = _sp_p.get("base") or {}
                _cm = _sp_p.get("current_mode") or {}
                _cov = (_sp_p.get("evidence") or {}).get("coverage") or {}
                for _axis, _val in _cov.items():
                    if _val is not None:
                        _all_cov.setdefault(_axis, []).append(float(_val))
                _ak = (_base.get("archetype") or {}).get("key")
                _dk = (_base.get("dna_class") or {}).get("key")
                _cl = (_base.get("chart_personality") or {}).get("labels") or []
                _ol = (_base.get("ownership_habitat") or {}).get("labels") or []
                _ml = (_base.get("microstructure") or {}).get("labels") or []
                _md = _cm.get("modes") or []
                if _ak:
                    _all_arch[_ak] = _all_arch.get(_ak, 0) + 1
                if _dk:
                    _all_dna[_dk] = _all_dna.get(_dk, 0) + 1
                for _lbl in _cl:
                    _all_chart[_lbl] = _all_chart.get(_lbl, 0) + 1
                for _lbl in _ol:
                    _all_own[_lbl] = _all_own.get(_lbl, 0) + 1
                for _lbl in _ml:
                    _all_micro[_lbl] = _all_micro.get(_lbl, 0) + 1
                for _m in _md:
                    _all_mode[_m] = _all_mode.get(_m, 0) + 1
                _per_ticker[_sp_tk] = {
                    "arch": _ak, "dna": _dk,
                    "chart": _cl, "own": _ol,
                    "micro": _ml, "modes": _md,
                }
            _sp_agg = {
                "schema": "stock_personality.v1",
                "as_of": _sp_today,
                "n_tickers": len(_sp_by_ticker),
                "coverage": {ax: round(sum(vals)/len(vals), 3)
                             for ax, vals in _all_cov.items() if vals},
                "label_distributions": {
                    "archetype": _all_arch,
                    "dna_class": _all_dna,
                    "chart_personality": _all_chart,
                    "ownership_habitat": _all_own,
                    "microstructure": _all_micro,
                    "current_mode": _all_mode,
                },
                "per_ticker": _per_ticker,
            }
            _sp_agg_path = site / "factordata" / "stock_personality.json"
            _sp_agg_path.write_text(json.dumps(_sp_agg, default=str))
            log.info("stock_personality.json: %d tickers written", len(_per_ticker))
    except Exception as _sp_agg_e:  # noqa: BLE001 — additive, never fatal
        log.warning("stock_personality site aggregate write failed (%s)", _sp_agg_e)
    # ---- stock_personality.v1 forward-ledger stamp ---------------------------------
    # Append one row per new buy/rebuy fire TODAY that has a personality object.
    # Single-writer: only the nightly engine job advances this ledger.
    _stamp_personality_forward_ledger(_sp_by_ticker, alpha_asof, config)
    # ---------------------------------------------------------------------------
    # ---- W0.2 Stage C: US signal_gate NEAR-MISS capture (masterplan §5.2 move 2) ----
    # signal_gate.gate() annotates verdicts that failed EXACTLY ONE Appendix-A
    # condition (freshness_expired / not_topped_veto — the two signal_gate-emitted
    # taxonomy reasons). Log them to the track-record ledger where they mature under
    # the same one-grader as fires ("grade rejections as predictions", §5.2 move 3).
    # Fail-open LOUD: capture failure never breaks the render but always logs.
    try:
        from engine import track_record as _tr
        _near = []
        for _t, _v in sig_verdict.items():
            _r = (_v or {}).get("near_miss_reason")
            if _r:
                _near.append({
                    "ticker": _t,
                    "date": str(_v.get("asof") or alpha_asof or ""),
                    "primary_rejection_reason": _r,
                    "reason_detail": _v.get("reason"),
                })
        if _near:
            _nm_out = _tr.log_near_misses(_near)
            log.info("near-miss capture: %s", _nm_out)
    except Exception as _nme:  # noqa: BLE001
        log.warning("near-miss capture failed (%s) — fires unaffected", _nme)
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
    # ---- B2 accrual (research/LABEL_FALTERING_PHASE0.md §2) — archive per-basket member-
    # conviction stats (potential median/IQR/n + theme score/label) so the pre-registered
    # demotion study can run once ≥180 trading days accrue. Write-only ledger, never fatal.
    try:
        from engine import conviction_accrual
        if conviction_accrual.archive_member_conviction("us", profiles, asof=alpha_asof):
            log.info("B2 conviction accrual: archived conviction_us for %s", alpha_asof)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("B2 conviction accrual (us) failed (%s)", e)
    for safe, rec in to_write:
        # canonical render model (engine/stock_view) — built AFTER attach_panel_scores so
        # the view's score/band match the final within-market percentile. Additive: the
        # shared stockview.js renders rec["view"]; legacy panels still read rec.* directly.
        rec["view"] = stock_view.build_view(rec, "US")
        # W8b: attach provenance sidecar to view (Committee View flagship data contract).
        # Fail-open: any per-ticker error → provenance key absent, page degrades gracefully.
        if _prov_ctx is not None:
            try:
                from engine.provenance_sidecar import build_provenance as _build_prov
                _ticker = rec.get("ticker", safe.replace("_", "="))
                rec["view"]["provenance"] = _build_prov(_ticker, rec, _prov_ctx)
            except Exception as _prov_e:  # noqa: BLE001 — additive, never fatal
                log.debug("provenance sidecar failed for %s: %s", safe, _prov_e)
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
    # COILED wave-2 ranking bonus: compute cohort fractions once (cross-sectional, after loop),
    # then build per-ticker assess() dict. Both steps try/except guarded; failure -> empty dict.
    # Wave-4: merge COILED-FIRE fields into the assess dict (display chip only, NO rank change).
    coiled_by: dict[str, dict] = {}
    try:
        _coil_frac = coiled.cohort_fractions(_coil_d, _coil_sector)
        coiled_by = {
            t: coiled.assess(_coil_wash.get(t), _coil_frac.get(t), bool(_coil_div.get(t)))
            for t in sig_verdict
        }
        # Wave-4 COILED-FIRE: for names that are COILED and have a recent fire, inject the fire
        # fields directly into the assess dict (JSON-safe; mutates in-place for row flow-through).
        # NO bonus change, NO rank input — display chip + forward-ledger only.
        for t, cb in coiled_by.items():
            if cb.get("coiled"):
                _fr = _coil_fire.get(t) or {}
                if _fr.get("fire"):
                    cb["fire"]       = True
                    cb["fire_ticks"] = _fr.get("ticks")
                    cb["fire_src"]   = _fr.get("src")
    except Exception as _e:  # noqa: BLE001 — additive; board degrades gracefully without bonus
        log.warning("coiled bonus skipped (%s)", _e)
        coiled_by = {}
    # Inject coiled into sniper blocks now that coiled_by is available.
    # sniper["coiled"] was left as None during the main loop because coiled_by
    # is a cross-sectional compute (needs the full cohort to set fractions).
    for _safe, _rec in to_write:
        try:
            _t = _rec.get("ticker", _safe.replace("_", "="))
            _sniper = _rec.get("sniper")
            if _sniper is not None:
                _sniper["coiled"] = bool((coiled_by.get(_t) or {}).get("coiled")) or None
        except Exception:  # noqa: BLE001 — additive; never fatal
            pass
    # G6a donor-sector context chip: compute once cross-sectionally after the loop.
    # Uses the same sector map as the COILED bonus (_coil_sector).  DISPLAY-ONLY —
    # never a gate, never changes ranking.  Additive + graceful: failure -> None.
    _donor_ctx = None
    try:
        _donor_ctx = donor.donor_state(_donor_closes, _coil_sector)
        if _donor_ctx:
            log.info("donor context: sector=%s state=%s legs=%s",
                     _donor_ctx.get("donor_sector"), _donor_ctx.get("state"),
                     _donor_ctx.get("legs"))
    except Exception as _de:  # noqa: BLE001
        log.debug("donor_state skipped (%s)", _de)
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
        # ticker tiebreaker: identical composite_z must never leave board order to
        # dict insertion order (reproducibility — same inputs, same board)
        scored.sort(key=lambda kv: (-(kv[1]["composite_z"]), kv[0]))
        # CONFLUENCE CASCADE INCLUSION GATE (owner directive, 2026-07-16 — mirroring CN
        # build_china_library.py:1433 and HK owner-ratified 2026-07-16): a name is
        # BUYABLE iff its signal_gate T1->T4 cascade verdict is `eligible` (freshness-
        # and not-topped-guarded inside signal_gate.gate). This REPLACES the prior
        # bottoming-alignment screen as the PRIMARY inclusion gate, exactly as the
        # signal_gate charter (engine/signal_gate.py docstring) prescribes for ALL
        # country standout grids. Cascade-eligible names include healthy uptrending
        # leaders (T1/T2 take) and forming continuations (T3/T4) — the old aligned/near
        # conjunction structurally excluded them (2026-07-15 live board: 30 aligned of
        # 1464, only 7 of 28 buys cascade-eligible; cascade-eligible pool was 82).
        # The bottoming-alignment data is RETAINED as per-card CONTEXT: _atier(p) is
        # still the third tuple element; it drives the align_tier badge and lane
        # derivation below, exactly as in CN. It is NOT an inclusion predicate anymore.
        # Parity with CN/HK: if sig_verdict is empty the builder logs a loud warning —
        # no fallback gate (breakage is a data-pipeline issue, not a gate-design
        # issue; the signal_sanity coverage floor catches a broken/empty board).
        if not sig_verdict:
            log.warning(
                "us_standouts wide board: sig_verdict is EMPTY — "
                "cascade gate will admit zero names (data-pipeline issue).")

        elig = _cascade_elig(scored, sig_verdict)

        # BOARD ORDERING: the owner's WEIGHTED cascade blend (signal_gate.blend_sorted,
        # US defaults) — conviction percentile scaled by the cascade weight, plus the
        # wave-2-validated COILED cohort-washout bonus (framework ledger 2026-07-01;
        # lifts a coiled name ~half a tier, star ~0.8). Strict tier-first was explicitly
        # rejected by the owner (blend_sorted docstring) — a strong-conviction T2/T3
        # must outrank a weak master. This pre-cap order decides which names survive
        # the per-sector soft cap below; the terminal DISPLAY sort within the trend
        # lane stays W8 alpha-desc (_board_alpha_sort_key, forward ledger #1062).
        buyable = signal_gate.blend_sorted(
            elig,
            base_of=lambda x: x[1].get("composite_z") or 0.0,
            verdict_of=lambda x: sig_verdict.get(x[0]),
            bonus_of=lambda x: ((coiled_by.get(x[0]) or {}).get("bonus") or 0.0),
        )

        # ── W8-C Lane R (cascade-gate supersedes) ────────────────────────────
        # Under the cascade inclusion gate, is_buyable (T1/T2/T3) is a strict
        # subset of eligible (T1/T2/T3/T4). Every name that would have qualified
        # for Lane R via is_buyable is already admitted on the trend lane above.
        # The W8-C scan is structurally empty: recovery candidates live on the
        # trend lane already. Retain the variable names so all downstream
        # references (buy_ids union, earnings-blackout recovery pass) compile.
        _recovery_cands: list[tuple] = []
        _recovery_tickers: set[str] = set()
        log.info("W8-C Lane R: cascade gate supersedes — recovery scan skipped "
                 "(is_buyable is a strict subset of cascade-eligible; "
                 "%d eligible on trend lane)", len(buyable))

        # W6-US fix 6: soft per-sector cap + dual-class dedup on the wide board.
        # The same PER_SECTOR=5 cap that guards action_board.notable in build_site.py
        # is now applied here so the cascade gate can't over-concentrate in one sector
        # (live pre-migration: 10 Industrials + 9 Utilities = 19/34 = 56% of buys).
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

        # ── W1.5 Earnings-blackout hygiene veto (adjudicated 2026-07-05) ──────
        # HYGIENE GATE — fresh-entry suppression only (RUL-4-legal).
        # HOLD/LAUNCHED names are never touched; only fresh-fire buy candidates.
        # Fail-open law: missing store / stale store => never suppresses.
        #
        # Injection: pass the already-built close-series index as the trading-day
        # calendar so earnings_blackout skips the redundant data/stocks/*.parquet
        # re-read (_build_td_calendar cold cost ~5s on 224+ files).
        try:
            _td_dates: "pd.DatetimeIndex | None" = None
            try:
                import pandas as _pd_eb
                _td_dates = _pd_eb.DatetimeIndex(sorted(set(
                    idx
                    for (_, cl, *_) in uni
                    for idx in cl.index
                )))
                _eb.set_td_calendar(_td_dates)
            except Exception:  # noqa: BLE001 — graceful: fall through to internal glob
                pass
            _eb_store_info = _eb.store_staleness()
            _eb_store_stale = _eb_store_info.get("stale", True)
            _eb_suppressed: list[tuple] = []   # (t, p, tier) suppressed from buy
            _eb_suppressed_r: list[tuple] = [] # (t, p) suppressed from Lane R
            _eb_blackout_map: dict[str, dict] = {}  # t -> assess() result
            if _eb_store_stale:
                log.warning(
                    "W1.5 earnings_blackout: store stale (as_of_age_td=%s) — "
                    "suppressing NOTHING (fail-open)",
                    _eb_store_info.get("as_of_age_td"))
            else:
                # Assess trend-lane buyable candidates
                _buyable_after_eb: list[tuple] = []
                for _item_eb in buyable:
                    _t_eb, _p_eb, _tier_eb = _item_eb
                    # Skip HOLD (any active state) — launched/intact/broken are all
                    # treated as open position; earnings gate does not re-suppress them.
                    # NOTE: hold state lives on row_by_t (rec["hold"]), NOT on prof (_p_eb).
                    _hd_eb = (row_by_t[_t_eb].get("hold") or {}) if _t_eb in row_by_t else {}
                    if _hd_eb.get("state") in {"launched", "intact", "broken"}:
                        _buyable_after_eb.append(_item_eb)
                        continue
                    _ev = _eb.assess(_t_eb)
                    _eb_blackout_map[_t_eb] = _ev
                    if _ev.get("in_blackout"):
                        _eb_suppressed.append(_item_eb)
                        # Attach rejection tag to the row (REJECTION_TAXONOMY slot)
                        row_by_t[_t_eb]["primary_rejection_reason"] = "event_blackout"
                    else:
                        _buyable_after_eb.append(_item_eb)
                buyable = _buyable_after_eb

                # Assess Lane-R recovery candidates
                _recovery_after_eb: list[tuple] = []
                for _t_eb, _p_eb in _recovery_cands:
                    # NOTE: hold state lives on row_by_t (rec["hold"]), NOT on prof (_p_eb).
                    _hd_eb = (row_by_t[_t_eb].get("hold") or {}) if _t_eb in row_by_t else {}
                    if _hd_eb.get("state") in {"launched", "intact", "broken"}:
                        _recovery_after_eb.append((_t_eb, _p_eb))
                        continue
                    _ev = _eb_blackout_map.get(_t_eb) or _eb.assess(_t_eb)
                    _eb_blackout_map[_t_eb] = _ev
                    if _ev.get("in_blackout"):
                        _eb_suppressed_r.append((_t_eb, _p_eb))
                        row_by_t[_t_eb]["primary_rejection_reason"] = "event_blackout"
                    else:
                        _recovery_after_eb.append((_t_eb, _p_eb))
                _recovery_cands = _recovery_after_eb
                _recovery_tickers = {t for t, _ in _recovery_cands}

                _n_eb_suppressed = len(_eb_suppressed) + len(_eb_suppressed_r)
                if _n_eb_suppressed:
                    log.info(
                        "W1.5 earnings_blackout: suppressed %d fresh-buy candidate(s) "
                        "— %s (event_blackout; HOLD/LAUNCHED untouched)",
                        _n_eb_suppressed,
                        ", ".join(t for t, _, _ti in _eb_suppressed)
                        + (", " + ", ".join(t for t, _ in _eb_suppressed_r)
                           if _eb_suppressed_r else ""),
                    )
                else:
                    log.info("W1.5 earnings_blackout: no fresh-buy candidates in blackout today")

            # Build suppressed-today summary for the board surface
            _eb_suppressed_count = len(_eb_suppressed) + len(_eb_suppressed_r)
            _eb_suppressed_note: dict | None = (
                {"count": _eb_suppressed_count,
                 "tickers": [t for t, _, _ti in _eb_suppressed]
                             + [t for t, _ in _eb_suppressed_r],
                 "store_stale": _eb_store_stale}
                if _eb_suppressed_count or _eb_store_stale else None
            )
        except Exception as _eb_exc:  # noqa: BLE001 — hygiene gate must never crash a build
            log.warning("W1.5 earnings_blackout: gate error (%s) — fail-open", _eb_exc)
            _eb_suppressed_count = 0
            _eb_suppressed_note = None
            _eb_blackout_map = {}
            _eb_store_stale = True

        buy_ids = {t for t, _, _ in buyable} | _recovery_tickers
        # overflow names join watch (only if positive conviction, no duplication)
        _overflow_tickers = {t for t, _, _ in _buyable_overflow}
        watch = [(t, p) for t, p in scored
                 if t not in buy_ids and (p.get("composite_z") or 0) > 0
                 and t not in _overflow_tickers]
        # prepend capped-overflow to watch in order (they are aligned — keep them visible)
        _overflow_watch = [(t, row_by_t[t]) for t, _, _ in _buyable_overflow
                           if (profiles.get(t) or {}).get("composite_z", 0) > 0]
        watch = _overflow_watch + watch

        # ── P2.4 Board Contract v2: lane taxonomy + weekly_phase capture ─────
        # Spec: research/entry_intel/P2_4_BOARD_CONTRACT_V2_DESIGN.md
        # Step A: populate weekly_phase on every cand row from
        #         profiles[t]["alignment"]["weekly"] BEFORE _tag() is called.
        # Step B: _lane_for() (module level, unit-tested in
        #         tests/test_us_standouts_cascade_gate.py) derives the lane from
        #         align_tier + weekly_phase, handling both live vocab (aligned/near)
        #         and replay vocab (PRIME/ARMED/APPROACHING) with an UNKNOWN guard.

        # Step A: capture weekly_phase + above_trend from profiles onto cand rows.
        # weekly_phase comes from profiles[t]["alignment"]["weekly"] (the _tf_phase()
        # value: "rising"/"rolling"/"falling"/"turning"/"unknown"). This is the primary
        # discriminator for ARMED-continuation vs PRIME-bottoming lane detection.
        # above_trend: sourced from sig_verdict[t].get("above200") — the signal_gate
        # already computes this boolean (price > 200d SMA) in gate() and emits it as a
        # top-level verdict key.  Board rows in row_by_t do NOT carry a "tech" sub-dict
        # at Step A time (tech snapshot is absent from the buy-loop dict), so the
        # previous primary path (r_dict.get("tech").get("above200")) always returned
        # None — hence 0% fill in the P2.4 real-build (VERIFY_P2_4_REALBUILD.md F1).
        # Fix (AC-5): use sig_verdict[ticker].get("above200") as the primary source.
        # sig_verdict is built at L1344 (same closure scope) from signal_gate.gate()
        # which populates above200 for every analysed name.
        def _get_above_trend(ticker_str):
            """Extract above_trend bool; primary = sig_verdict[t].above200."""
            # Primary: signal_gate verdict (above200 populated for all analysed names)
            _sv_ab = (sig_verdict.get(ticker_str) or {}).get("above200")
            if _sv_ab is not None:
                return bool(_sv_ab)
            # Fallback: already set on the row (e.g. from a prior propagation pass)
            _r_fb = row_by_t.get(ticker_str)
            if _r_fb is not None:
                _existing = _r_fb.get("above_trend")
                if _existing is not None:
                    return bool(_existing)
            return None

        # buyable = (t, p, tier) triples; _recovery_cands = (t, p) pairs — iterate separately
        for _t_a, _p_a, _tier_a in buyable:
            _r_a = row_by_t.get(_t_a)
            if _r_a is None:
                continue
            _align_a = (_p_a.get("alignment") or {})
            _wph_a = _align_a.get("weekly")
            if _wph_a is not None:
                _r_a["weekly_phase"] = _wph_a
            _atrd_a = _get_above_trend(_t_a)
            if _atrd_a is not None:
                _r_a["above_trend"] = _atrd_a
        for _t_a, _p_a in _recovery_cands:
            _r_a = row_by_t.get(_t_a)
            if _r_a is None:
                continue
            _prof_a = profiles.get(_t_a) or {}
            _align_a = (_prof_a.get("alignment") or {})
            _wph_a = _align_a.get("weekly")
            if _wph_a is not None:
                _r_a["weekly_phase"] = _wph_a
            _atrd_a = _get_above_trend(_t_a)
            if _atrd_a is not None:
                _r_a["above_trend"] = _atrd_a
        # Also propagate weekly_phase + above_trend for watch rows.
        # watch is a mixed list [(t, p_or_row)]; ignore the second element and always
        # look up from profiles for alignment (consistent source for both list variants).
        for _t_a, _ in watch:
            _r_a = row_by_t.get(_t_a)
            if _r_a is None:
                continue
            _prof_a = profiles.get(_t_a) or {}
            _align_a = (_prof_a.get("alignment") or {})
            _wph_a = _align_a.get("weekly")
            if _wph_a is not None:
                _r_a["weekly_phase"] = _wph_a
            _atrd_a = _get_above_trend(_t_a)
            if _atrd_a is not None:
                _r_a["above_trend"] = _atrd_a

        def _tag(t, tier, lane=None):
            """Tag a board row with align_tier and derive the v2 lane label.

            tier: the alignment tier string (from conviction.alignment.tier:
                  PRIME/ARMED/APPROACHING, or from _atier(): aligned/near).
                  Stored as r["align_tier"] for display/downstream consumers.
            lane: if explicitly supplied (e.g. "recovery") the lane is set
                  directly; otherwise derived by _lane_for(tier, weekly_phase).
            """
            r = row_by_t[t]
            # Use the richer conviction.alignment.tier (PRIME/ARMED) when available,
            # falling back to the _atier() board-level tier (aligned/near).
            _conv_tier = (profiles.get(t) or {}).get("alignment", {}).get("tier")
            _eff_tier = _conv_tier if _conv_tier else tier
            r["align_tier"] = _eff_tier
            weekly_ph = r.get("weekly_phase")
            r["lane"] = lane if lane is not None else _lane_for(_eff_tier, weekly_ph)
            return r

        # ── W8 alpha-within-lane ordering ─────────────────────────────────────
        # Forward ledger (#1062): P@1 board-order 28.6% vs alpha-order 71.4%.
        # Replace entry_open_first as the terminal sort for the wide board:
        # within lane='trend' order by alpha desc; then lane='recovery' block
        # ordered by alpha desc. The entry status BADGE is kept (not removed).
        # Alpha is read from the board ROW, not the conviction profile — the
        # profile has no "alpha" key, and reading it turned this sort into a
        # ticker-alphabetical board (invariant (d) regression; see
        # _board_alpha_sort_key).
        buyable_trend = sorted(
            buyable,
            key=lambda x: _board_alpha_sort_key(x[0], row_by_t))  # alpha desc within trend
        # Recovery rows: tag and order by alpha desc
        _recovery_rows_ordered = [
            _tag(t, "recovery", lane="recovery")
            for t, p in _recovery_cands
        ]

        # Trend rows: P2.4 v2 — lane is derived by _lane_for(tier, weekly_phase)
        # (no explicit lane= override so the continuation branch fires).
        _trend_rows_ordered = [_tag(t, tier) for t, _, tier in buyable_trend[:120]]

        _all_buy_rows = _trend_rows_ordered + _recovery_rows_ordered

        # P2.4 spec §3.1: watch rows must carry lane="watch" so lane_counts has a
        # "watch" key (not None).  Previously _tag() was only called for buy rows;
        # watch rows were assembled raw from row_by_t with lane=None — producing the
        # "null:24" key in lane_counts (VERIFY_P2_4_REALBUILD.md AC-2 gap / F2).
        def _tag_watch(t):
            r = row_by_t[t]
            r.setdefault("lane", "watch")   # don't overwrite if already set
            if r.get("lane") != "watch":
                r["lane"] = "watch"
            return r

        wide = {"as_of": alpha_asof, "rank_by": "confluence", "gate_go": gate_go,
                "buy": _all_buy_rows,
                "watch": [_tag_watch(t) for t, _ in watch[:24]],
                "laggards": [row_by_t[t] for t, _ in scored[-12:][::-1]] if len(scored) > 24 else [],
                "concentration": _concentration_stat,
                # G6a donor-sector: page-level context chip (not per-row; None when insufficient data)
                "donor": _donor_ctx,
                # W1.5 earnings-blackout: compact suppressed-today note (None when nothing suppressed
                # and store is fresh). Rendered as a board-level notice by the template.
                "earnings_blackout_note": _eb_suppressed_note}
        # Sector-integrity backstop (PR #2113 issue 4): universe() is now hardened
        # against non-fund sector_holdings parquets, but any future path that leaks a
        # junk sector label must not ship — drop the row here, before every downstream
        # consumer (lane_counts, conviction delta, shadow book, the artifact write).
        _spurious_sec = _drop_spurious_sector_rows(wide)
        for _lane_s, _rows_s in _spurious_sec.items():
            log.warning("sector-integrity guard: dropped %d %s row(s) with spurious "
                        "sector label: %s", len(_rows_s), _lane_s, _rows_s)
        eligible = len(elig)
        for r in wide["buy"] + wide["watch"] + wide["laggards"]:
            t = r.get("ticker")
            r["conviction"] = profiles.get(t)
            # P2.4 Step D: ext_z top-level field — extension z-score for the anti-chase
            # context chip (display-only per R10; F3 gate promotion is P3's jurisdiction).
            # Source: ext_map[t]["ext_z"] — the pre-computed per-name extension z-score
            # built at L1238 via extension_signals(_ext_closes).  The previous path read
            # profiles[t]["axes"]["extension"]["z"] which is NOT populated at profiles
            # level — hence 0% fill in the P2.4 real-build (VERIFY_P2_4_REALBUILD.md F3).
            # Fix: source directly from ext_map which is available in the same scope.
            _extz_v = (ext_map.get(t) or {}).get("ext_z")
            if _extz_v is not None:
                try:
                    r["ext_z"] = round(float(_extz_v), 2)
                except (TypeError, ValueError):
                    pass
            # P2.1a Step G: antichase_shadow_blocked — F3 anti-chase shadow gate field.
            # Reads ext_z from the same ext_map source used in Step D above.
            # Threshold = PARABOLIC_Z = 2.0 (engine/extension.py L36; pre-registered in
            # P2_1A_ANTICHASE_GATE_PREREG.md §1.3). SHADOW period: label only, ZERO
            # enforcement — name stays on board at same rank. The blocked field drives:
            #   (1) Anti-Chase Watch chip in the template (display only),
            #   (2) the shadow ledger writer below (forward-grading accrual),
            #   (3) species registry chip rung (F3_ANTICHASE, deployment_status=chip).
            # It is intentionally present on ALL rows (buy + watch + laggards) so the
            # shadow ledger can grade non-blocked rows as the control group.
            _ANTICHASE_Z_THRESH = 2.0   # mirrors PARABOLIC_Z — do not tune here
            _extz_float = r.get("ext_z")
            if _extz_float is not None:
                r["antichase_shadow_blocked"] = bool(_extz_float > _ANTICHASE_Z_THRESH)
            else:
                r["antichase_shadow_blocked"] = False
            # P2.4 Step C: above_trend propagation — final catch-all for rows that
            # weren't captured in Step A (e.g. laggard rows not in buy/watch lists).
            # Source: sig_verdict[t].above200 (consistent with Step A fix above).
            if r.get("above_trend") is None:
                _atrd_e = (sig_verdict.get(t) or {}).get("above200")
                if _atrd_e is not None:
                    r["above_trend"] = bool(_atrd_e)
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
            # Sector Pulse heat chip (DISPLAY-ONLY, never scores/ranks). Propagated from the
            # per-ticker pulse map built above; absent when the ticker is not in any live theme.
            _sp_r = _sector_pulse_map.get(t) or _sector_pulse_map.get((t or "").upper())
            if _sp_r:
                r["sector_pulse"] = _sp_r
            cb = coiled_by.get(t)                  # COILED wave-2 ranking bonus chip (display only)
            if cb and (cb.get("coiled") or cb.get("washout_ctx")):
                r["coiled"] = cb
            # W6-C HOLD: attach basing-state chip to standout rows (display-only, display after coiled)
            _hd = _hold_state.get(t)
            if _hd is not None:
                r["hold"] = _hd
            # W1.5 / MLC-W5 earnings-proximity chip — display-only context on ALL board rows.
            # For rows that are still on the board (HOLD/LAUNCHED or outside blackout),
            # attach the upcoming earnings date chip when days_to_earnings <= 14d (MLC-W5
            # extended from the original 7d; disclosure only per MLC-R10 — never gates).
            # For suppressed names: they are not on the board, so no chip needed here.
            _eb_row = _eb_blackout_map.get(t)
            if _eb_row is None and not _eb_store_stale:
                # Name was not assessed yet (e.g. watch/laggard rows not in the buy pipeline)
                try:
                    _eb_row = _eb.assess(t)
                    _eb_blackout_map[t] = _eb_row
                except Exception:  # noqa: BLE001
                    _eb_row = None
            if _eb_row and not _eb_row.get("stale") and _eb_row.get("days_to_earnings") is not None:
                _eb_days = _eb_row["days_to_earnings"]
                if _eb_days is not None and _eb_days <= 14:
                    # Map Nasdaq raw time tokens to display-friendly labels.
                    _raw_nt = _eb_row.get("next_time")
                    _nt_labels = {
                        "time-after-hours": "after close",
                        "time-pre-market": "pre-market",
                        "time-not-supplied": None,
                    }
                    _disp_nt = _nt_labels.get(_raw_nt, _raw_nt) if _raw_nt else None
                    # EN/ZH bilingual chip text (MLC-R6; glance-tier plain words).
                    # Display proximity in CALENDAR days from next_date so "today/
                    # tomorrow/in N d" read the way a human means them. _eb_days is a
                    # TRADING-day count (used for the ≤14 gate + W1.5 blackout), so a
                    # single trading day across a weekend is NOT calendar-"tomorrow"
                    # (Fri→Mon = 1 td / 3 cal). Fall back to _eb_days if next_date is
                    # unparseable.
                    _cal_days = _eb_days
                    _nd_raw = _eb_row.get("next_date")
                    if _nd_raw:
                        try:
                            _cal_days = (date.fromisoformat(str(_nd_raw)[:10])
                                         - date.today()).days
                        except Exception:  # noqa: BLE001
                            _cal_days = _eb_days
                    if _cal_days <= 0:
                        _chip_en = "Reports today"
                        _chip_zh = "今日公布业绩"
                    elif _cal_days == 1:
                        _chip_en = "Reports tomorrow"
                        _chip_zh = "明日公布业绩"
                    else:
                        _chip_en = f"Reports in {_cal_days} d"
                        _chip_zh = f"{_cal_days}日后公布业绩"
                    r["earnings_soon"] = {
                        "days_to": _cal_days,
                        "next_date": _eb_row.get("next_date"),
                        "next_time": _disp_nt,
                        "in_blackout": bool(_eb_row.get("in_blackout")),
                        "chip_en": _chip_en,
                        "chip_zh": _chip_zh,
                    }
            # W6-US fix 8: emit cand_depth_pct from the ladder onto every board row so
            # it is a first-class field available for the US-2 ledger study (depth vs
            # forward returns for FRESH-BUY rows). NOT a gate — we do NOT filter on it
            # (F2 caution: min-depth would kill the best trend-continuation entries).
            _lad8 = r.get("ladder") or {}
            _cdp8 = _lad8.get("cand_depth_pct")
            if _cdp8 is not None:
                r["cand_depth_pct"] = _cdp8
            # W5b liquidity chip fields — DISPLAY-ONLY (zero rank/gate power).
            # adv_dollar_20d_median: 20-session median dollar volume (W5b primary).
            # tier: deep/ok/thin/illiquid.
            # days_to_build_100k / days_to_build_1m: buildability at 10 % ADV.
            # Also the legacy adv_dollar_21d/days_to_exit_at_10pct_adv (backward compat).
            _lhyg = _liq_map.get(t)
            if _lhyg:
                # W5b new fields
                if _lhyg.get("adv_dollar_20d_median") is not None:
                    r["adv_dollar_20d_median"] = _lhyg["adv_dollar_20d_median"]
                if _lhyg.get("tier") is not None:
                    r["liquidity_tier"] = _lhyg["tier"]
                if _lhyg.get("days_to_build_100k") is not None:
                    r["days_to_build_100k"] = _lhyg["days_to_build_100k"]
                if _lhyg.get("days_to_build_1m") is not None:
                    r["days_to_build_1m"] = _lhyg["days_to_build_1m"]
                # Legacy fields (backward compat)
                if _lhyg.get("adv_dollar_21d") is not None:
                    r["adv_dollar_21d"] = _lhyg["adv_dollar_21d"]
                if _lhyg.get("days_to_exit_at_10pct_adv") is not None:
                    r["days_to_exit_at_10pct_adv"] = _lhyg["days_to_exit_at_10pct_adv"]
            # W8-B postcross lifecycle chip (BASED/ARMED/SHAKEN) — DISPLAY-ONLY.
            # W8-A verdict: NO rank power; ships as eligibility+display only; safety:
            # stop5 -4/-5pp vs stale complement, NI vs FRESH. Additive + never fatal.
            try:
                from engine import postcross as _pc
                _close_pc = (_ext_closes[t].dropna()
                             if "_ext_closes" in dir() and t in _ext_closes.columns
                             else None)
                if _close_pc is not None and len(_close_pc) >= 100:
                    _pc_state = _pc.postcross(_close_pc)
                    if _pc_state.get("based"):
                        r["postcross"] = _pc_state
            except Exception as _pce:  # noqa: BLE001 — display-only; never fatal
                pass
            # W9-A SAFETY_ONLY annotation (2026-07-03, #1143): when a BASED or Lane-R row
            # sits inside a sector-wide capitulation (cohort washout fraction >= 0.40 at
            # build time), attach a "sector_capitulating" marker for the safety chip.
            # NO rank/admission effect — display-only context, sign-stable stop-reduction
            # signal (−2.7pp stocks / −3.5pp baskets) but clean15 sub-threshold (+0.54pp).
            # Cohort fraction = fraction of GICS-sector peers with weekly StochRSI D < 30;
            # uses the same _coil_frac computed above (H6 cohort washout, leak-free).
            try:
                _is_based_row = bool(r.get("postcross", {}).get("based"))
                _is_recovery_row = r.get("lane") == "recovery"
                if _is_based_row or _is_recovery_row:
                    _w9a_frac = _coil_frac.get(t)
                    if _w9a_frac is not None and _w9a_frac >= 0.40:
                        r["sector_capitulating"] = {"cohort_frac": round(float(_w9a_frac), 3)}
            except Exception as _w9ae:  # noqa: BLE001 — display-only; never fatal
                pass
            # W3 evidence-stack: propagate evidence fields to ALL board rows (buy + watch).
            # ZERO ordering/admission impact — display chips + grader strata only.
            # Missing artifact => field absent, chip absent; never a neutral default.
            _w3ev = _w3_evidence.get(t)
            if _w3ev:
                # GEX confirmer (Source 2)
                if _w3ev.get("gex_confirm") is not None:
                    r["gex_confirm"] = _w3ev["gex_confirm"]
                # Alt-data convergence (Source 3)
                if _w3ev.get("altdata") is not None:
                    r["altdata"] = _w3ev["altdata"]
                # SUE freshness (Source 4) — also attach sue_fresh_days alongside the existing sue_z
                if _w3ev.get("sue_fresh_days") is not None:
                    r["sue_fresh_days"] = _w3ev["sue_fresh_days"]
                # News burst (Source 5)
                if _w3ev.get("news_burst") is not None:
                    r["news_burst"] = _w3ev["news_burst"]
                # Anticipation stop-budget (Source 6)
                if _w3ev.get("stop_guidance") is not None:
                    r["stop_guidance"] = _w3ev["stop_guidance"]
                # Smartmoney 13F (Source 7)
                if _w3ev.get("smartmoney_chip") is not None:
                    r["smartmoney_chip"] = _w3ev["smartmoney_chip"]
                # Propagate evidence_health if any sources had staleness markers
                if _w3ev.get("evidence_health"):
                    r["evidence_health"] = _w3ev["evidence_health"]
            # W3 Confluence+ badge: k-of-n independent group votes.
            # Groups: INSIDER, POLITICAL/GOV, GEX-OPTIONS, ALTDATA-ALT, SUE, NEWS, SMARTMONEY.
            # Same-group signals (e.g. insider_cluster + altdata insider_buy) never double-count.
            # Badge fires at k >= 2 independent group votes. ZERO admission/ordering power.
            try:
                _c_votes = 0
                _c_groups: list[str] = []
                # INSIDER group (Source 1): insider_buyers >= 2 (from cand row; also altdata insider)
                if (r.get("insider_buyers") or 0) >= 2:
                    _c_votes += 1
                    _c_groups.append("INSIDER")
                # POLITICAL/GOV group: altdata channels containing political signals
                _ad_r = r.get("altdata") or {}
                _ad_chans = set(_ad_r.get("channels") or [])
                _POL_CHANS = frozenset({"congress_buy", "trump", "gov_contract",
                                        "gov_contract_accel", "gov_grant", "lobbying"})
                if _ad_chans & _POL_CHANS:
                    _c_votes += 1
                    _c_groups.append("POLITICAL/GOV")
                # GEX-OPTIONS group: gex_confirm verdict == "confirm" only
                if (r.get("gex_confirm") or {}).get("verdict") == "confirm":
                    _c_votes += 1
                    _c_groups.append("GEX-OPTIONS")
                # ALTDATA-ALT group: altdata convergence >= 2 from NON-insider, NON-political channels
                _EXCL_CHANS = frozenset({"insider_buy", "insider_cluster",
                                         "congress_buy", "trump", "gov_contract",
                                         "gov_contract_accel", "gov_grant", "lobbying"})
                _alt_chans = _ad_chans - _EXCL_CHANS
                if _ad_r.get("convergence_score", 0) and _alt_chans:
                    # at least 1 non-insider/non-political channel present
                    _c_votes += 1
                    _c_groups.append("ALTDATA-ALT")
                # SUE group: sue_z >= 1 AND sue_fresh_days <= 60 (both must be present on row)
                if r.get("sue_z") and r.get("sue_fresh_days") is not None and r["sue_fresh_days"] <= 60:
                    _c_votes += 1
                    _c_groups.append("SUE")
                # NEWS group: news_burst present (n_recent >= 3 already checked at collection)
                if r.get("news_burst"):
                    _c_votes += 1
                    _c_groups.append("NEWS")
                # SMARTMONEY group: smartmoney_chip present (A/B-grade new/add already checked)
                if r.get("smartmoney_chip"):
                    _c_votes += 1
                    _c_groups.append("SMARTMONEY")
                if _c_votes >= 2:
                    r["confluence_plus"] = {"k": _c_votes, "groups": _c_groups}
            except Exception as _cpe:  # noqa: BLE001 — display-only; never fatal
                pass
            # B2+B3 Buy Decision Packet dossier — compact per-row join (display-only).
            # Built LAST in the loop so all chips (conviction, signal, hold, earnings_soon,
            # near_miss_reason) are already attached.  Fail-open: error → dossier absent.
            # ext_grade sourced from ext_map (available in this scope) — NOT on the row.
            try:
                from engine import stock_dossier as _sd
                _ds_ext_grade = (ext_map.get(t) or {}).get("grade")
                _ds = _sd.build_dossier(r, ext_grade=_ds_ext_grade)
                if _ds:
                    r["dossier"] = _ds
            except Exception as _dse:  # noqa: BLE001 — display-only; never fatal
                pass
        # W6-US fix 8 (cont): log FRESH-BUY rows with shallow depth for US-2 ledger study.
        # Shallow = cand_depth_pct < 5.0% (less than 5% pullback from the pre-cycle high).
        # The live ETN case: off_high=-2.2%, cand_depth_pct likely ~2-3%.
        # We DO NOT gate on depth (F2 caution: min-depth kills best trend-continuation entries).
        _FB_SHALLOW_THRESHOLD = 5.0
        _fb_shallow = [(r.get("ticker"), r.get("cand_depth_pct"), r.get("off_high"))
                       for r in wide["buy"]
                       if r.get("state") in ("FRESH BUY", "TURN SIGNALED")
                       and r.get("cand_depth_pct") is not None
                       and r["cand_depth_pct"] < _FB_SHALLOW_THRESHOLD]
        if _fb_shallow:
            log.info("W6-US fix 8: %d FRESH-BUY/TURN-SIGNALED rows with shallow depth "
                     "(cand_depth_pct < %.1f%%) — logged for US-2 ledger study (NOT gated): %s",
                     len(_fb_shallow), _FB_SHALLOW_THRESHOLD,
                     [(t, f"{d:.1f}%", f"off_high={o:.1f}%" if o else None)
                      for t, d, o in _fb_shallow])
        # W8 ordering: entry_open_first removed as the terminal sort for the wide board
        # (forward ledger P@1: board-order 28.6% vs alpha-order 71.4% — entry_open_first
        # is harmful as the terminal sort). The entry status BADGE is kept for display;
        # the ordering above (alpha desc within lane) is the final order. entry_open_first
        # is still used by the narrow "Top setups" / other consumers; it is NOT removed
        # from engine/setups.py — only no longer applied here.
        wide["eligible"] = eligible
        wide["universe"] = len(cand)
        if disp_regime:                            # selection-regime gross dial (board + bot)
            wide["dispersion_regime"] = disp_regime

        # P2.4 Step E: lane_counts top-level field — nightly monitoring primitive.
        # Counts rows per lane (bottoming/continuation/watch/recovery) across buy+watch.
        # Logged so the build log carries the distribution for AC-2 verification.
        from collections import Counter as _Counter
        _lane_ct = _Counter(r.get("lane") for r in wide["buy"] + wide["watch"])
        wide["lane_counts"] = dict(_lane_ct)
        log.info("P2.4 lane_counts: %s", wide["lane_counts"])

        # P2.1a Step H: anti-chase shadow ledger writer.
        # Appends per-ticker rows to data/signal_archive/antichase_shadow_ledger.parquet.
        # The ledger records EVERY board row (blocked and unblocked) so the control group
        # (antichase_shadow_blocked=False) is tracked for the Wilson-bound comparison in
        # the flip criterion C2 (P2_1A_ANTICHASE_GATE_PREREG.md §2.2).
        # Pattern: append-only parquet; keep-FIRST per (asof, ticker); never fatal.
        # Rollback fields per R-P2.1: flip_eligible=False + flip_criteria_met={'C1':False,
        #   'C2':False,'C3':False} mark this as a shadow row (no flip authority yet).
        # These fields are set to False throughout the shadow period; only a Fable ruling
        # + criteria check can set them to True (that logic is in the monthly review, not here).
        try:
            import pandas as _pd
            _shadow_path = config.data_dir() / "signal_archive" / "antichase_shadow_ledger.parquet"
            _shadow_path.parent.mkdir(parents=True, exist_ok=True)
            _asof_s = wide.get("as_of")
            if _asof_s:
                _asof_str = str(_pd.Timestamp(_asof_s).date())
                # Load existing to deduplicate by (asof, ticker)
                _old_shadow = _pd.read_parquet(_shadow_path) if _shadow_path.exists() else None
                _seen_shadow = set()
                if _old_shadow is not None and "asof" in _old_shadow.columns and "ticker" in _old_shadow.columns:
                    _seen_shadow = set(zip(_old_shadow["asof"].astype(str), _old_shadow["ticker"].astype(str)))
                _new_rows = []
                for _sr_h in wide["buy"] + wide["watch"]:
                    _t_h = _sr_h.get("ticker")
                    if _t_h is None or (_asof_str, _t_h) in _seen_shadow:
                        continue
                    _new_rows.append({
                        "asof": _asof_str,
                        "ticker": _t_h,
                        "lane": _sr_h.get("lane"),
                        "ext_z": _sr_h.get("ext_z"),
                        "antichase_shadow_blocked": bool(_sr_h.get("antichase_shadow_blocked")),
                        # Rollback/flip fields (R-P2.1): always False during shadow period.
                        # Set to True only after Fable ruling + C1+C2+C3 criteria confirmed.
                        "flip_eligible": False,
                        "flip_criteria_met": False,   # simplified bool; C1+C2+C3 detail in monthly review
                        "gate_state": "shadow",        # shadow | enforcing | rolledback
                        "logged_at": str(_pd.Timestamp.now(tz="UTC").isoformat()),
                    })
                if _new_rows:
                    _new_df = _pd.DataFrame(_new_rows)
                    _merged_shadow = _pd.concat([_old_shadow, _new_df], ignore_index=True) \
                        if _old_shadow is not None else _new_df
                    _merged_shadow.to_parquet(_shadow_path, index=False)
                    _n_blocked = sum(r["antichase_shadow_blocked"] for r in _new_rows)
                    log.info("P2.1a antichase shadow ledger: %d rows appended (%d blocked, %d unblocked) for %s",
                             len(_new_rows), _n_blocked, len(_new_rows) - _n_blocked, _asof_str)
                else:
                    log.debug("P2.1a antichase shadow ledger: no new rows for %s (all already logged)", _asof_str)
        except Exception as _ac_e:  # noqa: BLE001 — shadow ledger is never fatal
            log.debug("P2.1a antichase shadow ledger write skipped: %s", _ac_e)

        # P2.5 Step I: EI-F1D-RW shadow ledger writer.
        # Appends per-ticker rows to data/signal_archive/f1d_shadow_ledger.parquet.
        # Records EVERY board row (qualified and not-qualified) so the control group
        # (f1d_shadow_bonus=0) is tracked for the forward flip criterion.
        #
        # Spec: research/entry_intel/P2_5_INTERACTION_PREREG.md
        # Study: research/entry_intel/p1_runs/P2_5_STUDY/RESULTS.md
        # Registry: data/species/registry.json (entry: EI-F1D-RW)
        #
        # SIX ship configs (from study): C1, C3, C5, C6, C7, C8.
        # Primary = C6 (deep_trio: dd_pct>25% AND ac_pass AND rs_fav).
        # Dead configs C2/C4 are NOT tracked — they are listed for reference only.
        #
        # dd_pct computation: byte-faithful to washout_depth_pit in run_P2_5_study.py.
        #   _WASH_CTX_B=91, _WASH_CTX_A=217; window=close[-91:]; capit_pos=argmin(window);
        #   prior_max=nanmax(close[capit_pos-126:capit_pos]); dd_pos=-dd (positive fraction).
        # PIT discipline: only price index <= as_of is used.
        #
        # rs_sector_quartile: within-sector ext_z rank; Q1 (lowest ext_z) = most washed-out
        #   relative to peers = RS-favorable for a reversal context. Quartiles 1,2 = rs_fav.
        #   Computed from ext_map (same source as Step D/G) and _coil_sector (sector map).
        #
        # blend_sorted: min-max normalized composite_z across all board rows this day.
        # f1d_shadow_bonus: +0.10 if C6 qualifies, else 0.0.
        # f1d_shadow_rank: percentile of (blend_sorted + bonus) within-day (0..1).
        #
        # Pattern: append-only parquet; keep-FIRST per (asof, ticker); never fatal.
        try:
            import pandas as _f1d_pd
            import numpy as _f1d_np
            _F1D_LEDGER_PATH = config.data_dir() / "signal_archive" / "f1d_shadow_ledger.parquet"
            _F1D_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
            _f1d_asof_s = wide.get("as_of")
            if _f1d_asof_s:
                _f1d_asof_str = str(_f1d_pd.Timestamp(_f1d_asof_s).date())
                _f1d_asof_ts = _f1d_pd.Timestamp(_f1d_asof_s)

                # ── 1. Compute per-ticker dd_pct (byte-faithful to washout_depth_pit) ──
                # _WASH_CTX_B / _WASH_CTX_A match run_P2_5_study.py constants exactly.
                _F1D_WASH_B = 91
                _F1D_WASH_A = 217

                def _f1d_dd_pct(ticker_close: "_f1d_pd.Series") -> "float | None":
                    """PIT depth computation — mirrors washout_depth_pit in study script."""
                    try:
                        _c = ticker_close.dropna()
                        if not isinstance(_c.index, _f1d_pd.DatetimeIndex):
                            _c = _c.copy()
                            _c.index = _f1d_pd.to_datetime(_c.index)
                        _arr = _c.to_numpy()
                        _n = len(_arr)
                        if _n < _F1D_WASH_A + _F1D_WASH_B:
                            return None
                        _window = _arr[_n - _F1D_WASH_B:]
                        _local_min = int(_f1d_np.argmin(_window))
                        _capit_pos = (_n - _F1D_WASH_B) + _local_min
                        if _capit_pos < 126:
                            return None
                        _prior_max = float(_f1d_np.nanmax(_arr[_capit_pos - 126: _capit_pos]))
                        if _prior_max <= 0:
                            return None
                        _dd = _arr[_capit_pos] / _prior_max - 1.0
                        return float(-_dd)   # positive fraction (e.g. 0.31 = 31% down)
                    except Exception:
                        return None

                # ── 2. Compute sector-level rs_sector_quartile from ext_map ──
                # Group tickers by sector (from _coil_sector); rank each ticker's ext_z
                # within sector; quartile 1 = bottom ext_z (most washed-out = rs_fav).
                # Mirrors replay_standout_pipeline.py lines 573-586 (F5 fix).
                _f1d_sector_ext: "dict[str, list[float]]" = {}
                for _f1d_t, _f1d_sec in (_coil_sector or {}).items():
                    if _f1d_sec is None:
                        continue
                    _f1d_ez = (ext_map.get(_f1d_t) or {}).get("ext_z")
                    if _f1d_ez is not None:
                        _f1d_sector_ext.setdefault(str(_f1d_sec), []).append(float(_f1d_ez))

                def _f1d_rs_quartile(ticker: "str") -> "int | None":
                    """Return sector-relative ext_z quartile (1=lowest=rs_fav, 4=highest)."""
                    _sec = (_coil_sector or {}).get(ticker)
                    if _sec is None:
                        return None
                    _my_ez = (ext_map.get(ticker) or {}).get("ext_z")
                    if _my_ez is None:
                        return None
                    _peers = _f1d_sector_ext.get(str(_sec), [])
                    if len(_peers) < 4:
                        return None
                    _below = sum(1 for _v in _peers if _v < _my_ez)
                    _pctile = _below / len(_peers)
                    return int(min(4, max(1, _f1d_np.floor(_pctile * 4) + 1)))

                # ── 3. Compute blend_sorted (min-max normalized composite_z) for all rows ──
                _f1d_all_rows = wide["buy"] + wide["watch"]
                _f1d_czs = [
                    float((profiles.get(_r.get("ticker")) or {}).get("composite_z") or 0.0)
                    for _r in _f1d_all_rows
                ]
                _f1d_cz_min = min(_f1d_czs) if _f1d_czs else 0.0
                _f1d_cz_max = max(_f1d_czs) if _f1d_czs else 1.0
                _f1d_cz_range = _f1d_cz_max - _f1d_cz_min if _f1d_cz_max != _f1d_cz_min else 1.0

                def _f1d_blend_sorted(ticker: "str") -> "float":
                    _cz = float((profiles.get(ticker) or {}).get("composite_z") or 0.0)
                    return (_cz - _f1d_cz_min) / _f1d_cz_range

                # ── 4. Deduplicate against existing ledger ──
                _f1d_old = _f1d_pd.read_parquet(_F1D_LEDGER_PATH) if _F1D_LEDGER_PATH.exists() else None
                _f1d_seen: "set[tuple[str, str]]" = set()
                if _f1d_old is not None and "asof" in _f1d_old.columns and "ticker" in _f1d_old.columns:
                    _f1d_seen = set(zip(_f1d_old["asof"].astype(str), _f1d_old["ticker"].astype(str)))

                # ── 5. Build shadow rows with per-config booleans ──
                _f1d_new_rows = []
                for _f1d_bname, _f1d_section_rows in [("us_buy", wide["buy"]), ("us_watch", wide["watch"])]:
                    for _f1d_r in _f1d_section_rows:
                        _f1d_t = _f1d_r.get("ticker")
                        if _f1d_t is None or (_f1d_asof_str, _f1d_t) in _f1d_seen:
                            continue
                        # washout state (from _coil_wash, already computed in per-ticker loop)
                        _f1d_wash_active = bool(_coil_wash.get(_f1d_t) is True)
                        # dd_pct: PIT-sliced computation on massive_stock_day close
                        _f1d_dd: "float | None" = None
                        try:
                            _f1d_close_raw = _f1d_pd.read_parquet(
                                config.data_dir() / "massive_stock_day" / f"{_f1d_t}.parquet"
                            )["close"]
                            _f1d_pit_close = _f1d_close_raw[_f1d_close_raw.index <= _f1d_asof_ts]
                            _f1d_dd = _f1d_dd_pct(_f1d_pit_close)
                        except Exception:
                            pass
                        # above_200 from signal verdict (same source as Step D above)
                        _f1d_above200 = bool((sig_verdict.get(_f1d_t) or {}).get("above200"))
                        # ext_z from ext_map (same source as Step D/G)
                        _f1d_extz = _f1d_r.get("ext_z")  # already populated by Step D
                        _f1d_ac_pass = (_f1d_extz is not None) and (float(_f1d_extz) <= 2.0)
                        # rs_sector_quartile
                        _f1d_rs_q = _f1d_rs_quartile(_f1d_t)
                        _f1d_rs_fav = (_f1d_rs_q is not None) and (_f1d_rs_q in (1, 2))
                        # blend_sorted
                        _f1d_bs = _f1d_blend_sorted(_f1d_t)
                        # Per-config booleans (six ship-qualifying configs only; C2/C4 DEAD)
                        _f1d_c1 = _f1d_wash_active and (_f1d_dd is not None) and (_f1d_dd > 0.25)
                        _f1d_c3 = _f1d_wash_active and (not _f1d_above200)
                        _f1d_c5 = _f1d_wash_active and _f1d_ac_pass and _f1d_rs_fav
                        _f1d_c6 = _f1d_c1 and _f1d_ac_pass and _f1d_rs_fav   # deep_trio (primary)
                        _f1d_c7 = _f1d_wash_active and (_f1d_dd is not None) and (_f1d_dd > 0.40) and _f1d_ac_pass and _f1d_rs_fav
                        _f1d_c8 = _f1d_wash_active and (not _f1d_above200) and (_f1d_dd is not None) and (_f1d_dd > 0.25)
                        # Bonus: +0.10 if primary C6 qualifies
                        _f1d_bonus = 0.10 if _f1d_c6 else 0.0
                        _f1d_new_rows.append({
                            "asof": _f1d_asof_str,
                            "ticker": _f1d_t,
                            "board_name": _f1d_bname,
                            "washout_active": _f1d_wash_active,
                            "dd_pct": _f1d_dd,
                            "ext_z": _f1d_extz,
                            "rs_sector_quartile": float(_f1d_rs_q) if _f1d_rs_q is not None else None,
                            "above_200": _f1d_above200,
                            "blend_sorted": round(_f1d_bs, 6),
                            "f1d_shadow_bonus": _f1d_bonus,
                            # f1d_shadow_rank filled below after all rows assembled
                            "c1_qual": _f1d_c1,
                            "c3_qual": _f1d_c3,
                            "c5_qual": _f1d_c5,
                            "c6_qual": _f1d_c6,
                            "c7_qual": _f1d_c7,
                            "c8_qual": _f1d_c8,
                            "gate_state": "shadow",
                            "logged_at": str(_f1d_pd.Timestamp.now(tz="UTC").isoformat()),
                        })

                # ── 6. Compute f1d_shadow_rank (within-day re-percentile) ──
                if _f1d_new_rows:
                    _f1d_scores = [r["blend_sorted"] + r["f1d_shadow_bonus"] for r in _f1d_new_rows]
                    _f1d_n = len(_f1d_scores)
                    for _f1d_i, _f1d_row in enumerate(_f1d_new_rows):
                        _below_n = sum(1 for _s in _f1d_scores if _s < _f1d_scores[_f1d_i])
                        _f1d_row["f1d_shadow_rank"] = round(_below_n / _f1d_n, 6) if _f1d_n > 1 else 0.5

                    # ── 7. Write ledger (append-only; keep-first dedup) ──
                    _f1d_new_df = _f1d_pd.DataFrame(_f1d_new_rows)
                    _f1d_merged = _f1d_pd.concat([_f1d_old, _f1d_new_df], ignore_index=True) \
                        if _f1d_old is not None else _f1d_new_df
                    _f1d_merged.to_parquet(_F1D_LEDGER_PATH, index=False)
                    _f1d_n_c6 = sum(1 for _r in _f1d_new_rows if _r["c6_qual"])
                    _f1d_n_c1 = sum(1 for _r in _f1d_new_rows if _r["c1_qual"])
                    log.info(
                        "P2.5 F1D shadow ledger: %d rows appended (C6=%d C1=%d C3=%d C5=%d C7=%d C8=%d) for %s",
                        len(_f1d_new_rows), _f1d_n_c6, _f1d_n_c1,
                        sum(1 for _r in _f1d_new_rows if _r["c3_qual"]),
                        sum(1 for _r in _f1d_new_rows if _r["c5_qual"]),
                        sum(1 for _r in _f1d_new_rows if _r["c7_qual"]),
                        sum(1 for _r in _f1d_new_rows if _r["c8_qual"]),
                        _f1d_asof_str,
                    )
                    # ── 8. Attach shadow fields to board rows (ADDITIVE; production order UNTOUCHED) ──
                    # Per spec: shadow columns on JSON rows only; no template ordering change.
                    # Display chip: f1d_shadow_c6=True row gets data-tip chip in template.
                    _f1d_row_by_t = {_r["ticker"]: _r for _r in _f1d_new_rows}
                    for _f1d_brd in wide["buy"] + wide["watch"]:
                        _f1d_lr = _f1d_row_by_t.get(_f1d_brd.get("ticker"))
                        if _f1d_lr is not None:
                            _f1d_brd["washout_active"] = _f1d_lr["washout_active"]
                            _f1d_brd["dd_pct"] = _f1d_lr["dd_pct"]
                            _f1d_brd["f1d_shadow_bonus"] = _f1d_lr["f1d_shadow_bonus"]
                            _f1d_brd["f1d_shadow_rank"] = _f1d_lr["f1d_shadow_rank"]
                            _f1d_brd["f1d_shadow_c6"] = _f1d_lr["c6_qual"]
                else:
                    log.debug("P2.5 F1D shadow ledger: no new rows for %s (all already logged)", _f1d_asof_str)
        except Exception as _f1d_e:  # noqa: BLE001 — shadow ledger is never fatal
            log.debug("P2.5 F1D shadow ledger write skipped: %s", _f1d_e)

        # P2.4 Step F: setups.json lane backfill — same taxonomy, shared lane labels.
        # The setups object is still in memory (written initially at L1948). Update it
        # with lane values from the standout board and re-write to ensure shared taxonomy.
        # rank_by backfill: AC-6 requires non-null "alpha" value.
        _standout_lane_map = {r["ticker"]: r.get("lane") for r in wide.get("buy", [])}
        _setups_updated = False
        for _sr in setups.get("buy", []):
            _st = _sr.get("ticker")
            _sl = _standout_lane_map.get(_st, "bottoming")  # default: bottoming if not on board
            _sr["lane"] = _sl
            _setups_updated = True
        if "rank_by" not in setups or setups.get("rank_by") is None:
            setups["rank_by"] = "alpha"
            _setups_updated = True
        if _setups_updated:
            (site / "factordata" / "setups.json").write_text(
                json.dumps(setups, separators=(",", ":"), default=str))
            log.info("P2.4 setups.json lane backfill: %d buy rows updated, rank_by=%s",
                     len(setups.get("buy", [])), setups.get("rank_by"))

        # --- W6-US fix 7: urgency must respect the gated entry status ---
        # Row-level urgency="now" is derived from the cycle-state dict, but the
        # entry_signal.status is confluence-gated (entry_signal.py:167). When the gate
        # says "await_confluence" the cycle has not confirmed, so urgency="now" is
        # dishonest. We enforce: urgency="now" is only allowed when entry_signal.status
        # is in {buy_now, partial}. Otherwise urgency is downgraded to the entry status.
        _URGENCY_STATUS_MAP = {
            "buy_now": "now", "partial": "now",
            "await_confluence": "caution", "extended": "caution",
            "bounce_wait": "caution",
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

        # --- W8 HEADLINE ARBITER (masterplan P5) ---
        # A pure post-assembly pass that enforces honesty. Three rules:
        #   (1) FRESH-BUY-ish state/label with a stale cross (> FRESH_TICKS+1 ticks old) OR
        #       extension_read.extended=True → downgrade state/label to the hold equivalent.
        #   (2) urgency='imminent' while the entry/label indicates a blocked/BOTTOMING state
        #       → downgrade urgency to 'caution'.
        #   (3) W2 NEW: band in {high, constructive} while conviction verdict is Lagging or
        #       no-clear-edge → demote band one step + record arbiter_note. This fires BEFORE
        #       the W6-US fix-3(a) invariant check so that invariant never fires in production
        #       for this class (the arbiter closes the gap at build time).
        # Additive + never raises (nightly must not fail). Logs downgrade counts.
        _BAND_DEMOTE = {"high": "constructive", "constructive": "neutral"}
        try:
            from engine.confluence_tiers import FRESH_TICKS as _FRESH_TICKS
            _FRESH_BUY_STATES = {"FRESH BUY", "TURN SIGNALED"}
            _BOTM_STATES = {"BOTTOMING", "BASING", "ACCUMULATION"}
            _arbiter_downgrade_count = 0
            for _ra in wide["buy"] + wide["watch"]:
                _sig_a = _ra.get("signal") or {}
                _ticks_a = _sig_a.get("ticks")
                # Check extension for this row (reuse ext_map pre-computed for the universe)
                _ext_a = ext_map.get(_ra.get("ticker")) or {}
                _ext_extended_a = bool(_ext_a.get("grade") in ("parabolic", "stretched"))
                _state_a = _ra.get("state") or ""
                _stale_a = (_ticks_a is not None and _ticks_a > _FRESH_TICKS + 1)
                if _state_a in _FRESH_BUY_STATES and (_stale_a or _ext_extended_a):
                    # Rule 1: Downgrade to HOLD / extended hold equivalent
                    _why_a = "stale cross" if _stale_a else "extended"
                    _ra["arbiter_note"] = f"downgraded from {_state_a} ({_why_a})"
                    _ra["state"] = "HOLD — EXTENDED" if _ext_extended_a else "HOLD"
                    _label_a = _ra.get("label") or ""
                    if "FRESH" in _label_a.upper() or "TURN" in _label_a.upper():
                        _ra["label"] = "Hold — entry aged" if not _ext_extended_a else "Hold — extended"
                        _ra["label_zh"] = "持有—入场信号陈旧" if not _ext_extended_a else "持有—已过热"
                    _arbiter_downgrade_count += 1
                # Rule 2: urgency=imminent with blocked signal or BOTTOMING state.
                # The blocked-quality leg was missing until 2026-07 (rule text said
                # "blocked" but the code only checked _BOTM_STATES): HOLD/TURN-SIGNALED
                # rows with quality=block kept urgency=imminent, then invariant (b)
                # suffixed their label '(blocked)' → deploy-gate contradiction.
                _blocked_a = (_sig_a.get("last") or {}).get("quality") == "block"
                if _ra.get("urgency") == "imminent" and (_state_a in _BOTM_STATES or _blocked_a):
                    _ra["urgency"] = "caution"
                    if not _ra.get("arbiter_note"):
                        _why2 = (f"state={_state_a}" if _state_a in _BOTM_STATES
                                 else "blocked signal")
                        _ra["arbiter_note"] = f"urgency imminent downgraded ({_why2})"
                    _arbiter_downgrade_count += 1
                # Rule 3 (W2): band high/constructive while verdict is lagging/no-clear-edge
                # → demote band one step so the visual band reflects the conviction read.
                _c_arb = _ra.get("conviction") or {}
                _v_arb = (_c_arb.get("verdict") or "").lower()
                _b_arb = _c_arb.get("band") or ""
                if _b_arb in _BAND_DEMOTE and any(k in _v_arb for k in ("lagging", "no clear edge")):
                    _new_band = _BAND_DEMOTE[_b_arb]
                    _c_arb["band"] = _new_band
                    _note_arb = f"band demoted {_b_arb}→{_new_band} (verdict={_c_arb.get('verdict')})"
                    if _ra.get("arbiter_note"):
                        _ra["arbiter_note"] += "; " + _note_arb
                    else:
                        _ra["arbiter_note"] = _note_arb
                    _arbiter_downgrade_count += 1
                    log.debug("W2 arbiter rule3: %s %s", _ra.get("ticker"), _note_arb)
            if _arbiter_downgrade_count:
                log.info("W8 arbiter: %d rows downgraded (state/urgency/band honesty pass)",
                         _arbiter_downgrade_count)
        except Exception as _ae:  # noqa: BLE001 — arbiter is additive; never fatal
            log.warning("W8 arbiter skipped (%s)", _ae)

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
        #     BUY/FRESH never shows actionable urgency (now/imminent) when
        #     signal.last.quality=='block'. We mutate the row (not just log) so the
        #     invariant enforces itself in the artifact (see _enforce_blocked_buy_invariant).
        _blocked_buy_count = _enforce_blocked_buy_invariant(wide["buy"])
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

        # CSP-W5 — Board staleness block + pending-buy expiry (display-tier, demotion-only)
        # ────────────────────────────────────────────────────────────────────────────────
        # (1) Staleness: compute price_through / age_days / delayed from the max-date in
        #     data/baskets/ohlcv — the same store the cascade gate reads.  Emit into
        #     wide["staleness"] so the template can render the BOARD DELAYED badge.
        # (2) Expiry: move any pending buy that is > 3 trading sessions old and still
        #     unconfirmed from buy to watch.  Demotion-only: adds nothing to the buy side.
        # Both are fail-soft: any exception leaves the artifact unchanged.
        try:
            _staleness = _compute_board_staleness()
            wide["staleness"] = _staleness
            log.info(
                "CSP-W5 staleness: price_through=%s age_days=%s delayed=%s",
                _staleness.get("price_through"),
                _staleness.get("age_days"),
                _staleness.get("delayed"),
            )
        except Exception as _stale_e:  # noqa: BLE001
            log.warning("CSP-W5 staleness: failed (%s) — block absent from artifact", _stale_e)

        try:
            _buy_after, _watch_after, _n_expired = _expire_pending_buys(
                wide.get("buy", []), wide.get("watch", []), wide.get("as_of"))
            if _n_expired:
                wide["buy"] = _buy_after
                wide["watch"] = _watch_after
                wide["pending_expired_count"] = _n_expired
        except Exception as _exp_e:  # noqa: BLE001
            log.warning("CSP-W5 pending expiry: failed (%s) — no rows demoted", _exp_e)

        # B4 Conviction Delta — load prev artifact BEFORE overwriting, diff dossier keys,
        # embed compact delta block into wide.  Fail-open: any error leaves delta absent.
        # Idempotence: if prev_as_of == cur_as_of (same-day re-render or preview), carry
        # the existing delta forward unchanged rather than diffing the file against itself.
        try:
            from engine.conviction_delta import diff_standouts, load_prev_standouts
            _delta_path = site / "factordata" / "us_standouts.json"
            _prev_doc   = load_prev_standouts(_delta_path)
            _prev_as_of = (_prev_doc or {}).get("as_of")
            _cur_as_of  = wide.get("as_of")
            if _prev_as_of and _cur_as_of and _prev_as_of == _cur_as_of:
                # Same-day re-render: carry forward the existing delta block unchanged.
                _existing_delta = (_prev_doc or {}).get("delta")
                if _existing_delta:
                    wide["delta"] = _existing_delta
                    log.info("conviction_delta: same-day re-render (as_of=%s) — delta carried forward "
                             "(%d entries)", _cur_as_of, len(_existing_delta.get("entries", [])))
                else:
                    log.debug("conviction_delta: same-day re-render but prev has no delta — computing fresh")
                    wide["delta"] = diff_standouts(_prev_doc, wide)
            else:
                _delta = diff_standouts(_prev_doc, wide)
                wide["delta"] = _delta
                log.info("conviction_delta: %d entries (prev_as_of=%s → cur_as_of=%s)",
                         len(_delta.get("entries", [])), _prev_as_of, _cur_as_of)
        except Exception as _dlt_e:  # noqa: BLE001 — display-only; never fatal
            log.debug("conviction_delta: skipped (%s)", _dlt_e)

        (site / "factordata" / "us_standouts.json").write_text(
            json.dumps(_json_safe(wide), separators=(",", ":"), default=str, allow_nan=False))
        log.info("wrote us_standouts.json (%d buy · rank_by=%s · %d eligible / %d universe)",
                 len(wide["buy"]), wide["rank_by"], eligible, len(cand))
        # Render-lane self-check: the board-invariants CI job only fires on PRs that
        # touch the artifact, and the pages.yml deploy-gate twin is manual-dispatch
        # only — a nightly render that regresses an invariant ships silently (the
        # 2026-07 invariant-(d) latent red). Grade the fresh artifact here, warn-only:
        # a display-tier guard must never fail the render.
        try:
            from scripts.check_board_contradictions import _check as _board_invariants
            _bc_viol = _board_invariants(str(site / "factordata" / "us_standouts.json"))
            if _bc_viol:
                log.warning("board-contradictions self-check: %d violation(s) in fresh "
                            "us_standouts.json: %s", len(_bc_viol), "; ".join(_bc_viol))
        except Exception as _bc_e:  # noqa: BLE001 — guard must never break the render
            log.debug("board-contradictions self-check skipped (%s)", _bc_e)
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
        # ── Pick Lab snapshot producer (spec §5, PL-R7) ────────────────────────────────
        # Additive block: assembles the PIT universe snapshot for the pick-lab runner.
        # Wrapped try/except — never fatal. Log success/skip only (no exception re-raise).
        # Sector/regime enrichment (sector_phase/stage/bucket) stays NULL here; the runner
        # fills them from that night's committed sector artifacts (PL-R7b).
        # Budget: 1D/2D grids are vectorized over _ext_closes (already in memory). The 3D
        # grid values are extracted from signal_frame (one call per ticker, close-only,
        # no I/O) — adds <30s across the full universe.
        try:
            import time as _plab_time
            _plab_t0 = _plab_time.time()
            from engine.pick_lab import snapshot as _plab_snap
            from engine.pick_lab import signals_1d as _plab_s1d
            from engine.signal_quality import signal_frame as _plab_sf

            _plab_asof = wide.get("as_of")
            if _plab_asof and "_ext_closes" in dir() and _ext_closes is not None:

                # ── 1. Load personality JSON (small JSON; load once) ──────────────────
                _plab_personality: dict[str, dict] = {}
                try:
                    import json as _plab_json
                    _plab_sp_path = site / "factordata" / "stock_personality.json"
                    if _plab_sp_path.exists():
                        _plab_sp_raw = _plab_json.loads(_plab_sp_path.read_text())
                        _plab_personality = _plab_sp_raw.get("per_ticker") or {}
                except Exception as _plab_sp_e:
                    log.debug("pick_lab: personality load skipped (%s)", _plab_sp_e)

                # ── 2. Compute 1D/2D oscillator grid (vectorized) ────────────────────
                import pandas as _plab_pd
                _plab_d12_df = _plab_pd.DataFrame()  # empty fallback
                try:
                    _plab_d12_df = _plab_s1d.compute_grids(_ext_closes)
                except Exception as _plab_d12_e:
                    log.warning("pick_lab: 1D/2D grid skipped (%s)", _plab_d12_e)

                # ── 3. Compute 3D oscillator scalars per ticker ───────────────────────
                # signal_frame already ran inside sig_verdict but does not expose raw
                # macd/k/d scalars in its return; re-run close-only (no I/O).
                _plab_d3: dict[str, dict] = {}
                _OS3, _OB3, _CONF_W3 = 20, 80, 8
                for _plab_t3, _plab_c3 in _ext_closes.items():
                    try:
                        _sf3 = _plab_sf(_plab_c3.dropna())
                        if _sf3.empty or len(_sf3) < 2:
                            continue
                        _last3 = _sf3.iloc[-1]
                        _m3 = float(_last3["macd"]) if _plab_pd.notna(_last3["macd"]) else None
                        _s3 = float(_last3["sig"])  if _plab_pd.notna(_last3["sig"])  else None
                        _k3 = float(_last3["k"])    if _plab_pd.notna(_last3["k"])    else None
                        _d3 = float(_last3["d"])    if _plab_pd.notna(_last3["d"])    else None
                        # macd cross-up bars (window=15 bars on the 3D frame)
                        _mx3 = None
                        _kx3 = None
                        if _m3 is not None and _s3 is not None:
                            _macd_col = _sf3["macd"]
                            _sig_col  = _sf3["sig"]
                            _k_col    = _sf3["k"]
                            _d_col    = _sf3["d"]
                            _mxup = (_macd_col > _sig_col) & (_macd_col.shift(1) <= _sig_col.shift(1))
                            _kxup = (_k_col > _d_col)     & (_k_col.shift(1) <= _d_col.shift(1))
                            import numpy as _plab_np
                            _pos = _plab_np.arange(len(_sf3))

                            def _since3(cond_s):
                                _last_arr = _plab_pd.Series(
                                    _plab_np.where(cond_s.to_numpy(), _pos, _plab_np.nan),
                                    index=cond_s.index).ffill()
                                return _plab_pd.Series(_pos, index=cond_s.index) - _last_arr

                            _mxbar3 = _since3(_mxup).iloc[-1]
                            _kxbar3 = _since3(_kxup).iloc[-1]
                            _XBAR3  = 15  # same window as signals_1d.XBAR_WIN
                            _mx3 = float(_mxbar3) if _plab_pd.notna(_mxbar3) and _mxbar3 <= _XBAR3 else None
                            _kx3 = float(_kxbar3) if _plab_pd.notna(_kxbar3) and _kxbar3 <= _XBAR3 else None
                        # from_os: d < 20 within last 8 3D bars
                        _from_os3 = None
                        if len(_sf3) >= _CONF_W3:
                            _d_tail = _sf3["d"].iloc[-_CONF_W3:]
                            _from_os3 = bool(_d_tail.min() < _OS3) if _d_tail.notna().any() else None
                        # ob: k or d >= 80 on latest bar
                        _ob3 = None
                        if _k3 is not None and _d3 is not None:
                            _ob3 = bool(_k3 >= _OB3 or _d3 >= _OB3)
                        # weekly_bull from signal_frame
                        _wbull3 = bool(_last3["w_bull"]) if "w_bull" in _sf3.columns else None
                        _plab_d3[_plab_t3] = {
                            "d3_macd": _m3, "d3_sig": _s3,
                            "d3_macd_xup_bars": _mx3, "d3_k": _k3, "d3_d": _d3,
                            "d3_kd_xup_bars": _kx3, "d3_from_os": _from_os3, "d3_ob": _ob3,
                            "weekly_bull": _wbull3,
                        }
                    except Exception:
                        pass  # null-honest: leave d3 absent for this ticker

                # ── 3b. T0 beta indicator artifact (display-only; reuses the grids above) ──
                try:
                    from engine import t0_indicator as _t0i
                    _t0_art = _t0i.build_artifact(d1_grid=_plab_d12_df, d3_map=_plab_d3, closes=_ext_closes, asof=_plab_asof, sector_map=_coil_sector, liq_map=_liq_map)
                    _t0i.write_artifact(_t0_art, site)
                    log.info("t0_indicator: %d matches / %d scanned for %s", len(_t0_art["matches"]), _t0_art["universe_n"], _plab_asof)
                except Exception as _t0_e:  # noqa: BLE001 — never fatal
                    log.warning("t0_indicator artifact skipped (%s)", _t0_e)

                # ── 4. Build rec lookup for tech/alpha/context fields ─────────────────
                # to_write is list of (safe_ticker, rec); rec["ticker"] is the canonical key.
                _plab_rec_by_t: dict[str, dict] = {}
                for _plab_sf_t, _plab_rec in to_write:
                    _tk = _plab_rec.get("ticker") or _plab_sf_t
                    _plab_rec_by_t[_tk] = _plab_rec

                # ── 5. Assemble profile_dicts for the full scored universe ────────────
                # Use `profiles` (all tickers with a conviction profile) as the universe.
                # Fields null-honest: if a source dict is missing the key, leave as None.
                _plab_calm  = calm if calm is not None else None
                _plab_stress = (risk_overlay or {}).get("stress")
                _plab_liq_ov = (wide.get("dispersion_regime") or {}).get("state") if wide.get("dispersion_regime") else None

                # SPY close: last close of SPY from _ext_closes if present
                _plab_spy_close = None
                try:
                    if "SPY" in _ext_closes.columns:
                        _plab_spy_close = float(_ext_closes["SPY"].dropna().iloc[-1])
                except Exception:
                    pass

                _plab_profiles: list[dict] = []
                _plab_board_recs: dict[str, dict] = {}
                _plab_tech_dicts: dict[str, dict] = {}
                _plab_osc_dicts: dict[str, dict] = {}

                for _plab_tk, _plab_prof in profiles.items():
                    # ── identity / scores ──
                    _plab_rec2 = _plab_rec_by_t.get(_plab_tk) or {}
                    _plab_tech = _plab_rec2.get("tech") or {}
                    _plab_alpha = _plab_rec2.get("alpha") or {}
                    _plab_lad = _plab_rec2.get("ladder") or {}
                    _plab_vs  = _plab_rec2.get("vol_squeeze") or {}
                    _plab_liq_chip = _liq_map.get(_plab_tk) or {}
                    _plab_axes = _plab_prof.get("axes") or {}
                    _plab_coil_cb = coiled_by.get(_plab_tk) or {}

                    # personality
                    _plab_pers = _plab_personality.get(_plab_tk) or {}
                    _plab_arch = _plab_pers.get("arch")
                    _plab_modes = _plab_pers.get("modes") or []
                    _plab_cur_mode = _plab_modes[0] if _plab_modes else None

                    # is_20d_high: close == 20d high (derived from off_52w_high_pct proxy is
                    # unavailable; compute from _ext_closes if possible)
                    _plab_is_20d = None
                    try:
                        _plab_cs = _ext_closes.get(_plab_tk)
                        if _plab_cs is not None and len(_plab_cs.dropna()) >= 20:
                            _plab_px = _plab_cs.dropna().iloc[-1]
                            _plab_h20 = _plab_cs.dropna().iloc[-20:].max()
                            _plab_is_20d = bool(_plab_px >= _plab_h20)
                    except Exception:
                        pass

                    # dollar_adv_20d: prefer liquidity_chip median; fallback to tech mean
                    _plab_adv20 = (_plab_liq_chip.get("adv_dollar_20d_median")
                                   or _plab_tech.get("dollar_vol_20d"))

                    _plab_profiles.append({
                        "ticker": _plab_tk,
                        "sector": _plab_rec2.get("sector") or _coil_sector.get(_plab_tk),
                        "close": _plab_tech.get("price"),
                        "dollar_adv_20d": _plab_adv20,
                        "vol_ratio_20d": _plab_tech.get("rel_volume"),
                        "is_20d_high": _plab_is_20d,
                        "pct_vs_20dma": _plab_tech.get("pct_vs_20dma"),
                        "above_200": _plab_tech.get("above200"),
                        "off_52w_high_pct": _plab_tech.get("off_52w_high_pct"),
                        "rsi14": _plab_tech.get("rsi14"),
                        "ext_grade": (_plab_rec2.get("ext") or {}).get("grade") or (ext_map.get(_plab_tk) or {}).get("grade"),
                        # scores
                        "composite_z": _plab_prof.get("composite_z"),
                        "score": _plab_prof.get("score"),
                        "axis_selection": (_plab_axes.get("selection") or {}).get("z"),
                        "axis_entry":     (_plab_axes.get("entry")     or {}).get("z"),
                        "axis_quality":   (_plab_axes.get("quality")   or {}).get("z"),
                        "edge_insider":   _plab_alpha.get("insider_bps"),
                        "edge_sue":       _plab_alpha.get("sue"),
                        "edge_revision":  _plab_alpha.get("revision") or _plab_alpha.get("rev_pctile"),
                        "edge_alpha":     _plab_alpha.get("alpha"),
                        # context
                        "cycle_state": (_plab_lad.get("entry") or {}).get("tag") or _plab_lad.get("state"),
                        "urgency": (_plab_lad.get("entry") or {}).get("urgency"),
                        "coiled": bool(_plab_coil_cb.get("coiled")) if _plab_coil_cb.get("coiled") is not None else None,
                        "star":   bool(_plab_coil_cb.get("star"))   if _plab_coil_cb.get("star")   is not None else None,
                        "washout_active": bool(_coil_wash.get(_plab_tk) is True),
                        "vol_squeeze_state": _plab_vs.get("state"),
                        "archetype": _plab_arch,
                        "current_mode": _plab_cur_mode,
                        "implied_upside_pct": (_plab_rec2.get("fundamental") or {}).get("implied_upside_pct"),
                        "is_blackout": bool((_plab_rec2.get("entry_signal") or {}).get("is_blackout")) if (_plab_rec2.get("entry_signal") or {}).get("is_blackout") is not None else None,
                        "dilution_events_365d": (_plab_rec2.get("fundamental") or {}).get("dilution_events_365d"),
                        "days_since_shelf": (_plab_rec2.get("fundamental") or {}).get("days_since_shelf"),
                        "interest_coverage": (_plab_rec2.get("fundamental") or {}).get("interest_coverage"),
                        # dd_pct: compute from _ext_closes (already in memory, no disk I/O)
                        # mirrors washout_depth_pit constants from F1D block above
                        "dd_pct": None,  # computed below into _plab_tech_dicts
                        # regime scalars (repeated on every row — display-only)
                        "calm":              _plab_calm,
                        "stress":            _plab_stress,
                        "liquidity_overlay": _plab_liq_ov,
                        "spy_close":         _plab_spy_close,
                        # enrichment nulls (PL-R7b runner fills these)
                        "sector_phase": None, "sector_stage": None,
                        "sector_rs_mom20": None, "sector_bucket": None,
                    })

                    # ── gate fields ──
                    _plab_sv = sig_verdict.get(_plab_tk) or {}
                    _plab_board_recs[_plab_tk] = {
                        "tier": _plab_sv.get("tier_cascade"),
                        "t_ticks": _plab_sv.get("ticks"),
                        "gate_state": ("eligible" if _plab_sv.get("eligible") else "ineligible"),
                    }

                    # ── oscillator merge: d1/d2 from compute_grids, d3 from signal_frame ──
                    _plab_osc_row: dict = {}
                    if not _plab_d12_df.empty and _plab_tk in _plab_d12_df.index:
                        _plab_osc_row.update(
                            {k: v for k, v in _plab_d12_df.loc[_plab_tk].to_dict().items()
                             if v is not None and not (_plab_pd.isna(v) if not isinstance(v, (bool, str)) else False)}
                        )
                    _plab_osc_row.update(_plab_d3.get(_plab_tk) or {})
                    if _plab_osc_row:
                        _plab_osc_dicts[_plab_tk] = _plab_osc_row

                # ── 6. Compute dd_pct from _ext_closes (mirrors F1D block) ────────────
                _F1D_WASH_B2, _F1D_WASH_A2 = 91, 217
                for _plab_dd_t in profiles:
                    try:
                        _plab_c_dd = _ext_closes.get(_plab_dd_t)
                        if _plab_c_dd is None:
                            continue
                        _plab_c_dd = _plab_c_dd.dropna()
                        _arr_dd = _plab_c_dd.to_numpy()
                        _n_dd = len(_arr_dd)
                        if _n_dd < _F1D_WASH_A2 + _F1D_WASH_B2:
                            continue
                        import numpy as _np_dd
                        _window_dd = _arr_dd[_n_dd - _F1D_WASH_B2:]
                        _local_min_dd = int(_np_dd.argmin(_window_dd))
                        _capit_pos_dd = (_n_dd - _F1D_WASH_B2) + _local_min_dd
                        if _capit_pos_dd < 126:
                            continue
                        _prior_max_dd = float(_np_dd.nanmax(_arr_dd[_capit_pos_dd - 126: _capit_pos_dd]))
                        if _prior_max_dd <= 0:
                            continue
                        _dd_frac = float(-(_arr_dd[_capit_pos_dd] / _prior_max_dd - 1.0))
                        _plab_tech_dicts[_plab_dd_t] = {"dd_pct": _dd_frac}
                    except Exception:
                        pass  # null-honest; leave dd_pct absent for this ticker

                # ── 7. Build rows and write ───────────────────────────────────────────
                _plab_rows = _plab_snap.build_core_rows(
                    profile_dicts=_plab_profiles,
                    board_rec_dicts=_plab_board_recs,
                    technicals_dicts=_plab_tech_dicts,
                    oscillator_dicts=_plab_osc_dicts,
                    asof=_plab_asof,
                )
                if _plab_rows:
                    _plab_df = _plab_pd.DataFrame(_plab_rows)
                    _plab_snap.write_snapshot(_plab_df, _plab_asof)
                    log.info("pick_lab snapshot: %d rows for %s (%.1fs)",
                             len(_plab_rows), _plab_asof, _plab_time.time() - _plab_t0)
                else:
                    log.warning("pick_lab snapshot: 0 rows assembled for %s", _plab_asof)
            else:
                log.warning("pick_lab snapshot skipped: no as_of or no close panel")
        except Exception as _plab_e:  # noqa: BLE001 — snapshot producer is never fatal
            log.warning("pick_lab snapshot skipped (%s)", _plab_e)
    # multi-timeframe Bottom-Confidence per-band held-rate (stock.html shows the
    # measured "this band held the low ~N%" line; see research/BOTTOM_CONFIDENCE.md)
    bccal = config.data_dir() / "regime" / "bottom_confidence_calibration.json"
    if bccal.exists():
        (outdir / "bc_calibration.json").write_text(bccal.read_text())
    log.info("stock library: %d analyzed, %d skipped (thin history)", built, failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
