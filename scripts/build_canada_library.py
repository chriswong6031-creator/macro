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
import os
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import stock_score  # noqa: E402
from engine import name_score  # noqa: E402  — per-name POTENTIAL (buy-readiness) score
from engine import name_score_grader  # noqa: E402
from engine import stock_technicals  # noqa: E402  — richer close-only technical snapshot
from engine import vol_squeeze  # noqa: E402  — single-stock volatility black hole (close-only)
from engine import stock_view  # noqa: E402
from engine import entry_signal  # noqa: E402 — entry-timing gauge (WHEN to buy)
from engine import risk_sizing  # noqa: E402 — vol-managed inverse-vol sizing (the validated Sharpe lever)
from engine import dispersion  # noqa: E402 — cross-sectional dispersion regime (selection-gross dial)
from engine.cycles import analyze  # noqa: E402
from engine.residual_alpha import compute_residual_alpha  # noqa: E402
from engine.setups import CA_ALPHA_WEIGHT, entry_open_first, rank_setups, setup_score  # noqa: E402
from engine import signal_gate  # noqa: E402 — owner's confluence T1->T4 cascade (layered ON main's alpha/alignment gate)
from engine.technicals import season_line, seasonality, snapshot  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("canada_library")

TSX_INDEX = "^GSPTSE"   # cap-weighted TSX market proxy for the residual-alpha leg


# ── per-ticker analyze() fan-out (mirrors build_stock_library's process pool) ──
# Fan the GIL-bound engine.cycles.analyze across processes (knobs match the US/CN/HK
# builds: STOCK_LIB_WORKERS env > stock_search.workers > cpu_count, capped 8). The
# pool carries only the market-wide liquidity overlay; per-name post-processing
# (alpha, conviction, deferred writes) stays serial in main() → output order-identical.
_CA_SHARED: dict = {}


def _library_workers() -> int:
    n = os.environ.get("STOCK_LIB_WORKERS") or None
    if n is None:
        n = config.load().get("stock_search", {}).get("workers")
    if n is None:
        n = os.cpu_count() or 1
    return max(1, min(int(n), 8))


def _ca_winit(liq=None) -> None:
    _CA_SHARED["liq"] = liq


def _ca_one_task(item):
    ticker, close, high, name, sector = item
    try:
        # universe-wide opt-in: the search universe IS the heatmap universe (mirrors CN build)
        return _one(ticker, close, high, name, sector, liquidity=_CA_SHARED.get("liq"),
                    allow_limited=True)
    except Exception as e:  # noqa: BLE001 — one bad ticker must not kill the library
        log.debug("canada library %s failed: %s", ticker, e)
        return None


def _analyze_universe(uni, liq):
    """Run _one over the universe, parallel when worthwhile else serial; recs align
    1:1 with uni. Any pool error degrades to serial — parallelism never breaks the build."""
    _ca_winit(liq)  # also primes the serial path
    workers = _library_workers()
    if workers > 1 and len(uni) > 50:
        try:
            from concurrent.futures import ProcessPoolExecutor
            t0 = time.time()
            with ProcessPoolExecutor(max_workers=workers, initializer=_ca_winit,
                                     initargs=(liq,)) as ex:
                recs = list(ex.map(_ca_one_task, uni, chunksize=8))
            log.info("canada library: analysed %d names in %.0fs (%d processes)",
                     len(uni), time.time() - t0, workers)
            return recs
        except Exception as e:  # noqa: BLE001 — parallelism must never break the build
            log.warning("parallel canada library build failed (%s) — serial fallback", e)
    t0 = time.time()
    recs = [_ca_one_task(item) for item in uni]
    log.info("canada library: analysed %d names in %.0fs (serial)", len(uni), time.time() - t0)
    return recs


def current_liquidity() -> str | None:
    """The live Canada net-liquidity / regime overlay the engine last classified
    (canada_regime/latest.json `liquidity_overlay`). Threaded into analyze() as the
    orthogonal macro conviction modifier on buy setups (mirrors the US library);
    None when unavailable so the ladder simply omits the liquidity context."""
    p = config.data_dir() / "canada_regime" / "latest.json"
    if not p.exists():
        return None
    try:
        liq = json.loads(p.read_text()).get("liquidity_overlay")
    except Exception:  # noqa: BLE001
        return None
    return liq if liq in ("expanding", "contracting", "neutral") else None


def _basket_tailwind_map() -> dict[str, dict]:
    """Per-ticker thematic-basket TAILWIND for the Conviction "upside" axis (the
    sector/theme leg): the strongest Canada theme a name belongs to, scored by that
    basket's 20d return vs the S&P/TSX benchmark. Best-effort — any failure yields {}
    and the axis is simply absent (the engine never reads a missing leg as neutral).
    Mirrors build_stock_library._basket_tailwind_map for the US."""
    out: dict[str, dict] = {}
    try:
        from engine import baskets_canada
        data = baskets_canada.compute_canada_baskets() or {}
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
        log.warning("canada basket tailwind map unavailable (%s)", e)
    return out


def tv_symbol(ticker: str) -> str:
    """TradingView symbol for a TSX listing. RY.TO -> TSX:RY; GIB-A.TO -> TSX:GIB.A
    (dash class shares use a dot on TV); the Composite + ETFs map to a TSX ETF proxy."""
    if ticker == "^GSPTSE":
        return "TSX:XIC"
    if ticker.endswith(".TO"):
        return "TSX:" + ticker[:-3].replace("-", ".")
    return ticker


def _limited_rec(ticker: str, c: pd.Series, name: str, sector: str) -> dict:
    """A minimal, honest record for a name too new for the cycle model (a recent TSX
    listing under the 300-session floor). Port of build_china_library._limited_rec:
    identity, listing date, session count and the LIMITED sentinel state
    (canada_stock.html keys off `limited` before ever reading the ladder), plus the
    TV symbol so the page can chart it.

    Note: no `chart` key here — canada_stock.html charts from site/canadaohlc/ which
    emit_close_only builds off index.json (limited names are indexed with st=LIMITED
    and get canadaohlc charts for free once they appear in the index)."""
    return {
        "ticker": ticker, "name": name, "sector": sector, "tv": tv_symbol(ticker),
        "asof": str(c.index.max().date()),
        "listed": str(c.index.min().date()),
        "history_days": int(len(c)),
        "limited": True,
        "ladder": {"state": "LIMITED"},
    }


def _one(ticker: str, close: pd.Series, high: pd.Series | None,
         name: str, sector: str, liquidity: str | None = None,
         min_days: int = 300, allow_limited: bool = False) -> dict | None:
    c = close.dropna()
    if not len(c):
        return None
    # The heatmap and this library read the SAME canada_search panel, so a name the
    # tiles render must never 404 on click-through: below the 300-session cycle
    # floor we emit an honest LIMITED record (searchable identity + listing date +
    # chart, "analysis pending") instead of dropping the name — display-tier
    # context ships freely; the full read unlocks as history accrues. Unlike the
    # US build (curated extras only), allow_limited covers the WHOLE universe here
    # because the search universe IS the heatmap universe.
    if len(c) < min_days:
        return _limited_rec(ticker, c, name, sector) if allow_limited else None
    # Canada net-liquidity / regime overlay is a single macro label that conditions
    # every TSX-listed name's buy-setup conviction (mirrors the US library; macro_drag
    # / VIX legs are US-only and intentionally dropped here).
    res = analyze(c, high, kind="equity", liquidity=liquidity)
    if not res.get("ladder"):
        return _limited_rec(ticker, c, name, sector) if allow_limited else None
    month = int(c.index.max().month)
    seas = seasonality(c)
    # RICH close-only technicals (engine.stock_technicals: momentum / 52w-high proximity / BBWP /
    # HVP / RSI / MA regime) supersede the thin close-only snapshot; the single-stock volatility
    # black hole is added too — both best-effort so a thin/odd series never breaks the build.
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


# ---------------------------------------------------------------------------
# Branch B — the ripe-list contract (masterplan §5.0), CA-permanent.
#
# C7 phase-0 verdict (reports/c7-canada-momentum-phase0.md): ALL four momentum
# trials → ACCRUE (mom_res is FDR-stable q=0.0002 on the names panel but DSR-short
# 0.37<0.90; mom_tot fails both). No C-leg GO'd, so masterplan §4.1 BRANCH B fires:
# the CA board runs this exact order permanently and the 0-100 composite is
# SUPPRESSED (replaced by a rank pill + an honest "screen — accruing" tier badge).
#
#   UNIVERSE = names passing hygiene + bottoming-alignment {PRIME, ARMED}(+backfill)
#              — ALREADY applied upstream by rank_setups(align_map=...).
#   GROUP    = entry_open (confluence-buyable ∧ in/near buy-zone) > setting_up
#   RANK     = within group, residual-momentum z (the alpha leg) desc — labeled
#              "screen — momentum prior ACCRUING", NEVER a validated composite.
#   TIEBREAK = 63d ADV desc (proxy: off-high magnitude when ADV absent) — kept
#              stable so a thin field never churns.
# ---------------------------------------------------------------------------

# entry_signal.status values that mean "entry window is open NOW" (green on the card).
# Everything else on an aligned board row is "setting up" (awaiting the trigger).
_ENTRY_OPEN_STATUS = {"buy_now", "partial"}
# map status -> the ledger's compact entry_state vocabulary ('open'|'pullback'|'wait').
_ENTRY_STATE = {
    "buy_now": "open", "partial": "open",
    "wait_pullback": "pullback", "hold": "pullback",
    "buy_soon": "wait", "watch": "wait", "await_confluence": "wait",
    "extended": "wait", "topping": "wait", "exit": "wait", "avoid": "wait",
    "blocked": "wait", "bounce_wait": "wait",
}


def _row_group(r: dict) -> str:
    """'entry_open' when the entry gauge reads an OPEN window (buy_now/partial),
    else 'setting_up' (aligned, awaiting the trigger). The board is already
    alignment-gated upstream, so no 'watch' bucket appears here."""
    st = (r.get("entry_signal") or {}).get("status")
    return "entry_open" if st in _ENTRY_OPEN_STATUS else "setting_up"


def _oil_regime_on(overlay: dict | None) -> bool:
    """C1 phase-0: oil→XEG is the ONE ACCRUE (HAC t +2.75, FDR-pass, DSR-short);
    gold/copper are NO-GO. The oil context chip fires only when the overlay's oil
    factor is positive/rising (risk-on contribution). Gold/copper: never."""
    for f in (overlay or {}).get("factors") or []:
        if f.get("key") == "oil":
            return f.get("risk") == "on" or (f.get("z") or 0) > 0
    return False


def _lead_sentence(r: dict, oil_on: bool, zh: bool = False) -> str:
    """Plain-English card lead — 'what moves this stock, and when to buy it'.

    Deliberately short and jargon-free: the raw factor beta, the momentum-screen z
    and the insider cluster each already have their own chip/row on the card, so the
    lead is a one-glance summary, not a data dump. The main driver is named in plain
    words (Gold / Oil / CAD) with the beta number left to the per-stock detail page."""
    parts: list[str] = []
    fb = r.get("factor_beta") or {}
    prim = fb.get("primary")
    sec = r.get("sector")
    # 1) main driver — plain words, no beta number
    if prim:
        lbl = (fb.get("primary_label_zh") if zh else fb.get("primary_label")) or prim
        parts.append((f"主要驱动：{lbl}" if zh else f"Main driver: {lbl}"))
    elif sec:
        parts.append((f"主要驱动：{sec} 板块" if zh else f"Main driver: {sec} sector"))
    # 2) entry cue — plain words + the buy-zone price
    es = r.get("entry_signal") or {}
    st = es.get("status")
    bz = es.get("buy_zone") or {}
    if st in _ENTRY_OPEN_STATUS:
        parts.append(("现在可买" if zh else "buy now"))
    elif bz.get("low") is not None and bz.get("high") is not None:
        parts.append((f"回撤至 ${bz['low']:.2f}–${bz['high']:.2f} 买入" if zh
                      else f"buy on a pullback to ${bz['low']:.2f}–${bz['high']:.2f}"))
    else:
        parts.append(("等待周线转向" if zh else "wait for the weekly turn"))
    return " · ".join(parts)


def _branch_b_order(rows: list[dict], overlay: dict | None) -> list[dict]:
    """Apply the ripe-list contract order (§5.0) and stamp per-row Branch-B fields:
    group, board_pos (rank pill), oil_tailwind (C1 chip), lead_en/lead_zh.

    Group entry_open before setting_up; within each group order by the momentum
    SCREEN z (alpha) desc, tiebreak off-high magnitude (a pullback proxy for ADV,
    stable). board_pos is a single 1-based rank across the whole ordered board so the
    pill reads #1, #2, … top-to-bottom."""
    oil_on = _oil_regime_on(overlay)

    def _key(r):
        grp = 0 if _row_group(r) == "entry_open" else 1
        az = r.get("alpha")
        # -az so higher momentum-screen z ranks first; None sorts last within group
        return (grp, -(az if az is not None else -9.9), -abs(r.get("off_high") or 0.0))

    ordered = sorted(rows, key=_key)
    for pos, r in enumerate(ordered, start=1):
        r["group"] = _row_group(r)
        r["board_pos"] = pos
        r["oil_tailwind"] = bool(oil_on and (r.get("factor_beta") or {}).get("primary") == "oil")
        r["lead_en"] = _lead_sentence(r, oil_on, zh=False)
        r["lead_zh"] = _lead_sentence(r, oil_on, zh=True)
    return ordered


# weekly states that mean the higher timeframe is still FALLING — a name blocked here
# with a strong momentum screen is a falling-knife-style demote (edge, but no base yet).
_KNIFE_WEEKLY = {"bear", "bear_falling", "falling", "down", "bear_down"}


def _build_watch(cand: list, buys: list[dict], align_map: dict | None,
                 profiles: dict | None, n: int = 8) -> list[dict]:
    """Strong-but-blocked WATCH strip (W6 parity with HK's watch-strip).

    A name reaches the watch strip when its residual-momentum SCREEN z clears the buy
    floor (BUY_MIN) but the multi-timeframe bottoming-alignment gate held it OUT of the
    buy list (weekly not turned / no fresh entry) — a real edge awaiting a base, NOT a
    scored pick. Rows whose weekly is still falling are tagged watch_reason='knife' so
    the card states why they were pushed off the entry groups. Ranked by screen z desc.

    Pure re-selection over the already-scored candidate pool — no new network / IO."""
    from engine.setups import BUY_MIN
    am = align_map or {}
    pf = profiles or {}
    buy_ids = {r.get("ticker") for r in (buys or [])}
    watch: list[dict] = []
    for item in (cand or []):
        r = item[1] if isinstance(item, (tuple, list)) else item
        t = r.get("ticker")
        if not t or t in buy_ids:
            continue
        a = r.get("alpha")
        if a is None or a < BUY_MIN:          # strong momentum SCREEN only
            continue
        al = am.get(t) or {}
        if al.get("aligned") or al.get("near"):
            continue                          # not blocked → it is (near-)buyable, skip
        wk = str(al.get("weekly") or "").lower()
        knife = wk in _KNIFE_WEEKLY or ((al.get("knife") or 0.0) >= 0.66)
        row = {
            "ticker": t,
            "name": r.get("name"),
            "alpha": a,
            "watch_reason": "knife" if knife else "blocked",
            "block_reason": al.get("reason"),
            "block_reason_zh": al.get("reason_zh"),
        }
        if pf.get(t):
            _c = pf[t]
            row["conviction"] = {
                "score": _c.get("score"),
                "verdict": _c.get("verdict"),
                "verdict_zh": _c.get("verdict_zh"),
            }
        watch.append(row)
    # knives first (they earned the loudest explanation), then by screen z descending.
    watch.sort(key=lambda w: (0 if w["watch_reason"] == "knife" else 1, -(w["alpha"] or 0)))
    return watch[:n]


def compute_canada_standouts(setups: dict | None, overlay: dict | None = None) -> dict | None:
    """Enrich the alpha-led `setups.buy` shortlist into the CA standout board and
    apply the BRANCH-B ripe-list contract order (masterplan §5.0 + C7 verdict).

    Adds per-stock price + off-52w-high + sparkline + the unified Conviction Profile
    (kept for the honest desaturated context, NOT the sort key) + the commodity
    factor-beta + insider context + the extension log-and-grade chip; then GROUPS
    entry_open vs setting_up and RANKS within group by the residual-momentum SCREEN
    z (the alpha leg, honestly labeled accruing). Best-effort per row."""
    if not setups or not setups.get("buy"):
        return setups
    site = config.ROOT / config.load()["storage"]["site_dir"]
    cd = site / "canadastockdata"
    closes, _, _ = _breadth_panel()
    # extension log-and-grade signals (engine/extension) — a PER-NAME risk-placement
    # read, NOT rank-affecting: it only stamps an 'extended' chip + a ledger column.
    try:
        from engine import extension
        ext_map = extension.extension_signals(closes) if not closes.empty else {}
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("canada extension signals unavailable (%s)", e)
        ext_map = {}
    # ---- CA2 port: close-only entry-QUALITY engines (log-and-grade, NO rank effect) ----
    # pullback_zone (price-range enriching the entry window) + hold (basing-state note) +
    # dannytrades (vol-compression / contrarian). Mirrors the extension-demote idiom (#1072):
    # each is a per-name CONTEXT chip stamped onto the row, never an eligibility/rank input.
    # dannytrades needs OHLCV+volume, which the CA board universe (close-only canada_search
    # panel) lacks — so assess() self-gates to None; the leg lights up only if CA ever gains
    # a per-name OHLCV store (mirrors the US has_intraday presence-guard idiom).
    try:
        from engine import pullback_zone as _pullback_zone
    except Exception:  # noqa: BLE001 — additive, never fatal
        _pullback_zone = None
    try:
        from engine import hold as _hold_engine
    except Exception:  # noqa: BLE001
        _hold_engine = None
    try:
        from engine import dannytrades_chip as _dt_chip
    except Exception:  # noqa: BLE001
        _dt_chip = None
    for r in setups["buy"]:
        t = r["ticker"]
        f = cd / f"{t.replace('=', '_').replace('^', '_')}.json"
        if f.exists():
            try:
                rec = json.loads(f.read_text())
                tech = rec.get("tech", {})
                r["price"] = tech.get("price")
                r["off_high"] = tech.get("off_52w_high_pct")
                if r.get("conviction") is None and rec.get("conviction"):
                    r["conviction"] = rec["conviction"]
                # the entry-timing gauge (WHEN to buy) so the card renders it AND the
                # board can group by open entries — main() attaches it only to the
                # separate standouts artifact, not this page-facing setups list.
                if rec.get("entry_signal"):
                    r.setdefault("entry_signal", rec["entry_signal"])
                # confluence T1->T4 tier verdict — the card tier badge + the board ledger's
                # gate_tier both read this. Written per-name in main(); read here so the
                # page-facing board carries the REAL tier (not a shared-object side effect).
                if rec.get("signal"):
                    r["signal"] = rec["signal"]
                # commodity/FX factor beta (the TSX signature) + insider context —
                # patched onto the per-stock JSON in main(); the board row needs them
                # for the mechanism lead + the C1 oil context chip.
                if rec.get("factor_beta"):
                    r["factor_beta"] = rec["factor_beta"]
                if rec.get("insider"):
                    r["insider"] = rec["insider"]
                # earnings catalyst — next report date drives the "reports in Nd" why-now
                # chip (W6 §7.4). Presence-guarded on the card; context, never a rank input.
                if rec.get("earnings"):
                    r["earnings"] = rec["earnings"]
                    nd = rec["earnings"].get("next_date")
                    if nd:
                        try:
                            _dt = (pd.Timestamp(nd).normalize()
                                   - pd.Timestamp.utcnow().normalize()).days
                            r["earnings"]["days_to"] = int(_dt) if _dt >= 0 else None
                        except Exception:  # noqa: BLE001 — chip is optional
                            pass
            except Exception:  # noqa: BLE001
                pass
        # extension demote as LOG-AND-GRADE: an 'extended' chip when the name is
        # stretched/parabolic vs its 200d, never a rank change (Phase-0 showed
        # freshness does NOT cut drawdown; extension.py docstring).
        ex = ext_map.get(t)
        if ex and ex.get("grade") in ("parabolic", "stretched"):
            r["extended"] = {"grade": ex["grade"], "ext_z": ex.get("ext_z"),
                             "near_52wh": ex.get("near_52wh")}
        # CA2 port — pullback zone (enriches the entry window with a concrete price range for
        # a don't-chase leader) + hold (basing-state note vs its anchor) + dannytrades
        # (vol-compression / contrarian). All close-only where possible, all log-and-grade:
        # per-name context chips, NEVER a rank/eligibility input. Best-effort per row.
        _series = closes[t].dropna() if (not closes.empty and t in closes.columns) else None
        if _pullback_zone is not None and (r.get("price") is not None):
            try:
                _tk = {"price": r.get("price"), "off_52w_high_pct": r.get("off_high")}
                # enrich with the 200/50d context from the per-stock JSON tech when present
                _jf = cd / f"{t.replace('=', '_').replace('^', '_')}.json"
                if _jf.exists():
                    _jtech = (json.loads(_jf.read_text()) or {}).get("tech") or {}
                    for _k in ("pct_vs_200dma", "pct_vs_50dma", "above50"):
                        if _jtech.get(_k) is not None:
                            _tk[_k] = _jtech[_k]
                pz = _pullback_zone.compute(
                    _tk, (r.get("extended") or {}).get("grade"),
                    downtrend=(r.get("dir") == "down"))
                if pz:
                    r["pullback_zone"] = pz
            except Exception as e:  # noqa: BLE001 — additive, never fatal
                log.debug("CA pullback-zone for %s failed (%s)", t, e)
        if _hold_engine is not None and _series is not None:
            try:
                _hs = _hold_engine.hold_state(_series, last_cross_fallback=True)
                if _hs:
                    r["hold"] = _hs
            except Exception as e:  # noqa: BLE001 — additive, never fatal
                log.debug("CA hold-state for %s failed (%s)", t, e)
        if _dt_chip is not None and _series is not None:
            try:
                # close-only panel → high/low/volume absent → assess() self-gates to None.
                # Lights up automatically the day CA gains a per-name OHLCV store.
                dtc = _dt_chip.assess(_series, None, None, None)
                if dtc:
                    r["dt_contra"] = dtc
            except Exception as e:  # noqa: BLE001 — additive, never fatal
                log.debug("CA dt-contra for %s failed (%s)", t, e)
        if not closes.empty and t in closes.columns:
            s = closes[t].dropna().tail(64).tolist()
            col = ("var(--up)" if r.get("dir") == "up"
                   else "var(--down)" if r.get("dir") == "down" else "var(--muted)")
            r["spark_svg"] = _spark_svg(s, color=col)
    # ── W8-G: days_since_signal enrichment ───────────────────────────────────
    # Days since first appearance in the CA board ledger (data/board_ledger/ca_board.parquet).
    # Null-safe: if the store is absent the field is None ("—" in template / table).
    # DISPLAY ONLY — no ordering change; no rank effect (mirrors build_china_library:2067).
    _w8g_first_seen: dict[str, str] = {}
    try:
        from lib import config as _w8g_cfg  # noqa: PLC0415
        _brd_path = _w8g_cfg.data_dir() / "board_ledger" / "ca_board.parquet"
        if _brd_path.exists():
            _brd_df = pd.read_parquet(_brd_path, columns=["date", "ticker"])
            _w8g_first_seen = (
                _brd_df.groupby("ticker")["date"].min()
                .apply(str).to_dict()
            )
            log.info("W8-G days_since_signal: %d tickers in CA board ledger (range %s → %s)",
                     len(_w8g_first_seen),
                     min(_w8g_first_seen.values()) if _w8g_first_seen else "?",
                     max(_w8g_first_seen.values()) if _w8g_first_seen else "?")
    except Exception as _w8g_e:  # noqa: BLE001 — additive, never fatal
        log.warning("W8-G days_since_signal: CA board ledger unavailable (%s)", _w8g_e)

    _w8g_today_str = str(setups.get("as_of")) if setups.get("as_of") else None

    def _w8g_days_since(ticker: str) -> int | None:
        fs = _w8g_first_seen.get(str(ticker))
        if not fs or not _w8g_today_str:
            return None
        try:
            d0 = pd.Timestamp(fs).date()
            d1 = pd.Timestamp(_w8g_today_str).date()
            return max(0, (d1 - d0).days)
        except Exception:  # noqa: BLE001
            return None

    for _w8g_r in setups["buy"]:
        _tk = _w8g_r.get("ticker")
        _w8g_r["days_since_signal"] = _w8g_days_since(_tk) if _tk else None

    # BRANCH B: group (entry_open > setting_up) then rank within group by the momentum
    # SCREEN z. Replaces the entry_open_first composite sort — the composite is NOT the
    # order under the zero-GO branch (masterplan §4.1 / §5.0).
    setups["buy"] = _branch_b_order(setups["buy"], overlay)
    setups["branch"] = "B"          # honest marker: ripe-list contract, composite suppressed
    setups["rank_basis"] = "momentum_screen_accruing"
    # ---- CA2: CONFLUENCE stat + SECTOR-CONCENTRATION banner (both make the tape HONEST) ----
    setups["confluence"] = _confluence_stat(setups["buy"])
    _sc = _sector_concentration(setups["buy"])
    if _sc:
        setups["sector_concentration"] = _sc
    return setups


def _confluence_stat(rows: list[dict]) -> dict:
    """Count board names with an OPEN confluence buy today (a FRESH MACD-2D x StochRSI-3D
    cross → signal_gate.is_buyable). The desk header prints "N buyable crosses today of M
    board names" so an all-None (zero-cross) tape reads honestly as "0 of M" — VISIBLE, not
    a silent blank. r['signal'] is the per-name compact verdict stamped in main()."""
    return {"crosses": sum(1 for r in rows if signal_gate.is_buyable(r.get("signal"))),
            "board": len(rows)}


def _sector_concentration(rows: list[dict], threshold: float = 0.60) -> dict | None:
    """When MORE than `threshold` of the board shares one sector, return the banner payload
    (sector, n, total, per-sector counts) — honesty, NOT forced diversification: the basing
    cohort clustering in (e.g.) the gold complex is a fact the reader should SEE. No re-rank.
    None when the board is empty, unlabeled ('—') dominates, or no sector clears threshold."""
    if not rows:
        return None
    counts: dict[str, int] = {}
    for r in rows:
        s = r.get("sector") or "—"
        counts[s] = counts.get(s, 0) + 1
    top_sec, top_n = max(counts.items(), key=lambda kv: kv[1])
    if top_sec == "—" or (top_n / len(rows)) <= threshold:
        return None
    return {"sector": top_sec, "n": top_n, "total": len(rows),
            "counts": dict(sorted(counts.items(), key=lambda kv: -kv[1]))}


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

    index, cand, built, failed, limited = [], [], 0, 0, 0
    sector_by: dict[str, str] = {}
    uni = universe()

    liq = current_liquidity()                  # macro overlay threaded into analyze()
    basket_tw = _basket_tailwind_map()         # Conviction "theme tailwind" axis
    # Phase-0 gate (display framing only; the board rank always stays the validated α leg).
    gate_go = False
    _gate = config.data_dir() / "regime" / "stock_conviction_gate.json"
    if _gate.exists():
        try:
            gate_go = (json.loads(_gate.read_text()) or {}).get("CA") == "GO"
        except Exception:  # noqa: BLE001 — additive, never fatal
            pass
    log.info("canada library: net-liquidity overlay %s · basket-tailwind names %d",
             liq or "unknown", len(basket_tw))

    # forward anticipation cone — hoist the engine + its gate ONCE (the cone is close-driven and the
    # S&P/TSX benchmark close is read once for the residual-alpha leg; both reads would otherwise repeat
    # per name). None-safe: if the engine is unavailable, the cone is simply skipped for every name.
    try:
        from engine.anticipation import anticipate as _anticipate, load_gate as _load_gate
        _ant_gate = _load_gate("US")
    except Exception:  # noqa: BLE001
        _anticipate = None
        _ant_gate = None
    try:
        _tsx = store.read("canada", TSX_INDEX)
        _tsx_close = _tsx["close"] if (_tsx is not None and "close" in _tsx.columns) else None
    except Exception:  # noqa: BLE001
        _tsx_close = None

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
    # insider transactions drip (SEDI via yfinance get_insider_transactions for .TO
    # names) — same up-front, capped, freshness-cached best-effort pattern. The per-
    # stock 👤 panel reads what's been collected. CONTEXT, not a signal.
    from engine import canada_insider
    try:
        canada_insider.fetch_insider([t for t, *_ in uni], max_new=40)
    except Exception as e:  # noqa: BLE001
        log.warning("canada insider fetch failed (%s)", e)
    names_map = canada_fundamentals.display_names()
    # fold the pretty display-name remap into the universe up front so the parallel
    # analyze() fan-out (and the serial post-loop) carry the final name unchanged.
    uni = [(t, c, h, names_map.get(t) or n, s) for (t, c, h, n, s) in uni]

    # Conviction profiles (engine/stock_score) per name + the deferred per-stock JSON
    # writes — deferred so the display score can be the WITHIN-MARKET percentile of the
    # composite z (set once all names are profiled), not a per-name logistic skin.
    # Mirrors build_stock_library (US).
    profiles: dict[str, dict] = {}
    to_write: dict[str, tuple[str, dict]] = {}   # ticker -> (safe, rec)
    entry_sig: dict[str, dict] = {}              # entry-timing gauge per name (board rows)
    risk_sig: dict[str, dict] = {}               # vol-managed sizing per name (board rows)
    # cross-sectional DISPERSION regime — the dial for WHEN selection pays (high
    # dispersion => take more gross on the cross-sectional book). Computed ONCE over the
    # whole-universe return panel; feeds per-name vol-managed sizing as `regime_gross`.
    # Mirrors build_stock_library (US). Best-effort: a thin panel just leaves gross=1.0.
    disp_regime, regime_gross = None, 1.0
    try:
        _ext_closes = pd.concat({t: c for (t, c, *_rest) in uni}, axis=1).sort_index()
        disp_regime = dispersion.assess(_ext_closes.pct_change(fill_method=None).tail(280))
        if disp_regime:
            regime_gross = disp_regime["gross_mult"]
            log.info("canada dispersion regime: %s (pctile %s, avg_corr %s) -> gross x%.2f",
                     disp_regime["state"], disp_regime.get("dispersion_pctile"),
                     disp_regime.get("avg_corr"), regime_gross)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("canada dispersion regime failed (%s)", e)
    recs = _analyze_universe(uni, liq)      # parallel analyze() fan-out (order-preserving)
    sig_verdict: dict[str, dict] = {}       # owner's confluence T1->T4 cascade verdict per name
    for (ticker, close, high, name, sector), rec in zip(uni, recs):
        if rec is None:
            failed += 1
            continue
        if rec.get("limited"):
            # recent listing under the history floor — searchable identity + honest
            # "analysis pending" detail page (renderLimited), but it NEVER enters
            # scoring / boards / profiles (accrual without authority).
            to_write[ticker] = (ticker.replace("=", "_").replace("^", "_"), rec)
            index.append({"t": ticker, "n": name, "s": sector, "st": "LIMITED"})
            limited += 1
            continue
        # COMBINE: confluence cascade computed alongside the alpha/alignment gate — additive.
        # It NEVER changes eligibility (alpha floor + alignment stay the inclusion gate); it only
        # adds the per-card tier badge and re-ranks WITHIN the existing buy list (below).
        sig_verdict[ticker] = signal_gate.gate(ticker, close)
        # Persist the display-safe confluence verdict onto the per-stock JSON so the page-
        # facing standout board (compute_canada_standouts, run again in build_canada.py) can
        # read the real T1->T4 tier per row — not rely on a shared-object side effect. The
        # board's forward ledger (gate_tier) and the card tier badge both source from here.
        rec["signal"] = signal_gate.compact(sig_verdict[ticker])
        if alpha_pt.get(ticker):
            rec["alpha"] = alpha_pt[ticker]
            sc = _setup_score(rec)
            if sc:
                cand.append(sc)
        # ---- unified Conviction Profile (engine/stock_score) -----------------
        # The single block both the dashboard standout card AND this name's detail page
        # render, so the two can never structurally disagree. CA selection = residual
        # alpha (weak positive-IC context — the trust tier says so); the cycle state is a
        # HARD verb modifier (a downtrend caps the entry axis and forbids a Buy verb).
        # Canada carries no validated cross-sectional quality leg (no SUE/insider/factor
        # composite), so the quality axis is simply absent — never read as neutral.
        # forward anticipation cone (close-only) — feeds the risk-shape entry tilt + favourable-cone
        # note in the shared engine; best-effort (skips quietly on thin history).
        if _anticipate is not None:
            try:
                _ant = _anticipate(close.dropna(), bench=_tsx_close, asset_class="ca_equity",
                                   gate=_ant_gate)
                if _ant:
                    rec["anticipation"] = _ant
            except Exception:  # noqa: BLE001 — additive cone, never fatal
                pass
        norm = stock_score.normalize_rec(rec, "CA", basket=basket_tw.get(ticker))
        prof = stock_score.conviction_profile(norm, "CA", ctx={"as_of": (alpha or {}).get("as_of"), "gate_go": gate_go})
        rec["conviction"] = prof
        # ---- Risk-based sizing (engine/risk_sizing) — the VALIDATED Sharpe lever ----
        # Vol-managed inverse-vol size: bet LESS on high-vol names, MORE on calm ones,
        # scaled by the dispersion regime. HOW MUCH to own (risk), orthogonal to the
        # conviction score (WHAT) and the entry gauge (WHEN). Pure-vol; high is None on CA.
        try:
            rs = risk_sizing.assess(close, regime_gross=regime_gross)
            if rs:
                rec["risk_sizing"] = rs
                risk_sig[ticker] = rs                            # attached to board rows below
                if isinstance(prof, dict) and isinstance(prof.get("size"), dict):
                    prof["size"]["vol_mult"] = rs["size_mult"]   # additive, never overrides
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("risk-sizing for %s failed (%s)", ticker, e)
        # ---- Entry-timing gauge (engine/entry_signal) — the SECOND gauge ------------
        # Conviction answers "own it?"; this answers "buy now / at what price / when?".
        # Reads the already-calibrated rec['ladder']/cycle; high is None on CA (close-only).
        # Gate on the SAME MACD-2D x StochRSI-3D confluence as the board (mirrors the
        # US pattern in build_stock_library): a "buy now / partial" with no fresh
        # confluence cross reads "awaiting confluence", never an open entry window.
        try:
            es = entry_signal.assess(close, high, rec,
                                     buyable=signal_gate.is_buyable(sig_verdict.get(ticker)))
            if es:
                rec["entry_signal"] = es
                entry_sig[ticker] = es                           # attached to board rows below
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("entry-signal for %s failed (%s)", ticker, e)
        # ---- POTENTIAL score (engine/name_score, CA) — front-running buy-readiness ----
        # Cycle-trigger timing blended with CA's residual-momentum prior (its best-available
        # selection leg). Overrides the displayed score after panel scoring below.
        try:
            rec.setdefault("ticker", ticker)
            _sel_z = ((prof.get("axes") or {}).get("selection") or {}).get("z")
            rec["conviction"]["potential"] = name_score.potential_score(
                rec, market="CA", edge_z=_sel_z,
                regime_stress=float((prof.get("risk") or {}).get("macro_stress") or 0.0))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("CA potential score for %s failed (%s)", ticker, e)
        profiles[ticker] = prof
        safe = ticker.replace("=", "_").replace("^", "_")
        to_write[ticker] = (safe, rec)           # deferred: write after percentile scoring
        idx = {"t": ticker, "n": name, "s": sector, "st": rec["ladder"]["state"]}
        if rec.get("alpha", {}).get("alpha") is not None:
            idx["a"] = rec["alpha"]["alpha"]
        index.append(idx)
        sector_by[ticker] = sector
        built += 1

    # within-market percentile display score (mutates each conviction block in place;
    # rec['conviction'] is the SAME object, so the per-stock JSONs pick it up below).
    stock_score.attach_panel_scores(profiles, "CA")
    # CA DISPLAYED score = the POTENTIAL (buy-readiness), not the comp-z percentile (kept as
    # rank_pctile). Front-running timing that still respects the residual-momentum prior.
    _cacalls = []
    for _safe, _rec in to_write.values():
        _c = _rec.get("conviction") or {}
        _pot = _c.get("potential")
        if not _pot:
            continue
        _c["rank_pctile"] = _c.get("score")
        _c["score"] = _pot["score"]
        _c["band"], _c["band_en"], _c["band_zh"] = _pot["band"], _pot["band_en"], _pot["band_zh"]
        _notes = _c.get("notes")
        if _notes:
            _c["notes"] = [n for n in _notes if n.get("kind") != "rank"] or None
        if _pot.get("call"):
            _cacalls.append({**_pot["call"], "level": (_rec.get("tech") or {}).get("price")})
    try:
        if _cacalls:
            name_score_grader.append_name_calls(_cacalls, market="CA",
                                                asof=str(pd.Timestamp.utcnow().date()))
    except Exception as e:  # noqa: BLE001 — grading is additive, never fatal
        log.warning("CA name-score grader append failed (%s)", e)
    # ---- B2 accrual (research/LABEL_FALTERING_PHASE0.md §2) — archive per-basket member-
    # conviction stats (potential median/IQR/n + theme score/label) so the pre-registered
    # demotion study can run once ≥180 trading days accrue. Write-only ledger, never fatal.
    try:
        from engine import conviction_accrual
        _b2_asof = (alpha or {}).get("as_of")
        if conviction_accrual.archive_member_conviction("canada", profiles, asof=_b2_asof):
            log.info("B2 conviction accrual: archived conviction_canada for %s", _b2_asof)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("B2 conviction accrual (canada) failed (%s)", e)
    for safe, rec in to_write.values():
        rec["view"] = stock_view.build_view(rec, "CA")   # canonical render model (rebuilt below once factor_beta lands)
        (outdir / f"{safe}.json").write_text(json.dumps(rec, default=str))

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
    insiders: dict[str, dict] = {}
    try:
        insiders = canada_insider.insider_map()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("canada insider unavailable (%s)", e)
    # commodity / FX factor betas — the TSX-differentiated exposure read (oil / gold / CAD,
    # market-controlled). Pure function of the close panel + the macro factor levels.
    betas: dict[str, dict] = {}
    try:
        from engine import canada_factor_beta, canada_overlay
        closes_fb, _, _ = _breadth_panel()
        mdf = store.read("canada", TSX_INDEX)
        market_fb = mdf["close"] if (mdf is not None and "close" in mdf.columns) else None
        betas = canada_factor_beta.compute_betas(
            closes_fb, canada_overlay.factor_series(), market=market_fb)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("canada factor beta unavailable (%s)", e)
    for ticker in set(fmap) | set(earn) | set(betas) | set(insiders):
        patch: dict = {}
        if fmap.get(ticker):
            patch["fundamentals"] = fmap[ticker]
        if earn.get(ticker):
            patch["earnings"] = earn[ticker]
        if betas.get(ticker):
            patch["factor_beta"] = betas[ticker]
        if insiders.get(ticker):
            patch["insider"] = insiders[ticker]
        if not patch:
            continue
        safe = ticker.replace("=", "_").replace("^", "_")
        fp = outdir / f"{safe}.json"
        if not fp.exists():
            continue
        try:
            rec = json.loads(fp.read_text())
            rec.update(patch)
            rec["view"] = stock_view.build_view(rec, "CA")   # rebuild so the commodity_beta card appears
            fp.write_text(json.dumps(rec, default=str))
        except Exception:  # noqa: BLE001
            continue
    fset = set(fmap)
    for idx in index:
        if idx["t"] in fset:
            idx["f"] = 1
    log.info("canada context attached: fund %d · earnings %d · factor-beta %d · insider %d",
             len(fmap), len(earn), len(betas), len(insiders))
    (outdir / "index.json").write_text(json.dumps(index))
    # Bespoke chart OHLC (close-only area series) read by canada_stock.html's chart.js —
    # pure serialisation of canada_search closes; never break the library over the garnish.
    try:
        from scripts.build_chart_data import emit_close_only
        nc = emit_close_only(outdir / "index.json", config.data_dir() / "canada_search" / "closes.parquet",
                             outdir.parent / "canadaohlc", "canada")
        log.info("canada chart data: %d ohlc files", nc)
    except Exception as e:  # noqa: BLE001
        log.warning("canada chart data step failed (%s)", e)

    cal = config.data_dir() / "canada_regime" / "ladder_calibration.json"
    if cal.exists():
        (outdir / "calibration.json").write_text(cal.read_text())

    # cross-sectional alpha-led "Top setups" — selection (alpha) × timing (cycle)
    setups = None
    # BOTTOMING-ALIGNMENT gate (mirrors the US/CN/HK fix): the buy shortlist is gated on
    # multi-timeframe alignment (weekly not-falling + 3-day nearing a bullish cross + daily
    # just-crossed/about-to) so a mid-weekly-bear falling knife is kept off the strip;
    # within aligned names the validated alpha leg is the ranking tiebreaker.
    align_map = {t: (p or {}).get("alignment") for t, p in profiles.items()}
    if cand:
        # n_buy generous (100) so the Stock Dashboard's "show more" can reveal the full
        # bench. The Conviction composite rides as the displayed profile/verdict per card.
        as_of = (alpha or {}).get("as_of")
        eligible = sum(1 for _s, r in cand
                       if (align_map.get(r.get("ticker")) or {}).get("aligned"))
        setups = rank_setups(cand, as_of=as_of, rank_by="alpha", n_buy=100,
                             align_map=align_map)
        # attach the unified Conviction Profile to every shipped row (the dashboard card
        # and the name's own page then render the SAME block — never disagree).
        for r in setups["buy"] + setups.get("laggards", []):
            t = r.get("ticker")
            if profiles.get(t):
                r["conviction"] = profiles[t]
        setups["eligible"] = eligible        # how many passed the alignment gate
        setups["universe"] = len(cand)
        # WATCH strip (W6 parity with HK) — strong momentum-SCREEN z that the bottoming-
        # alignment gate BLOCKED from the buy list (weekly still falling / no fresh turn):
        # a real edge with no entry window yet. Names whose weekly is a falling knife are
        # tagged so the watcher sees WHY they were held out of the entry groups. This is a
        # SCREEN-hygiene surface, not a scored seam — the momentum leg is accruing (C7).
        setups["watch"] = _build_watch(cand, setups["buy"], align_map, profiles)
        (site / "factordata").mkdir(parents=True, exist_ok=True)
        (site / "factordata" / "canada_setups.json").write_text(
            json.dumps(setups, separators=(",", ":"), default=str))
        # WIDE "Standout individual stocks" board persisted as its own artifact, so a
        # transient build failure leaves a stale-but-present file (mirrors us_standouts.json).
        # Ranked by the validated alpha leg; enriched with price/off-high/sparkline + the
        # Conviction profile; eligible = how many cleared the +0.5 alpha floor.
        wide = compute_canada_standouts(
            rank_setups(cand, as_of=as_of, rank_by="alpha", n_buy=100, n_lag=12,
                        align_map=align_map))
        # COMBINE re-rank: keep the alpha/alignment inclusion, order WITHIN each alignment tier by
        # the owner's weighted cascade blend (setup-score percentile lifted by the T1->T4 weight).
        # Weightless names keep their rank. Eligibility/membership UNCHANGED.
        import bisect as _bisect
        _scores = sorted((r.get("setup") or 0.0) for r in wide["buy"])
        _bn = len(_scores) or 1

        def _combine_key(r):
            w = (sig_verdict.get(r.get("ticker")) or {}).get("weight") or 0.0
            pct = _bisect.bisect_right(_scores, r.get("setup") or 0.0) / _bn
            return (0 if r.get("align_tier") == "aligned" else 1, -(pct + 0.5 * w))
        wide["buy"] = sorted(wide["buy"], key=_combine_key)
        for r in wide["buy"] + wide.get("laggards", []):
            t = r.get("ticker")
            r["signal"] = signal_gate.compact(sig_verdict.get(t))   # confluence T1->T4 tier badge
            if r.get("conviction") is None and profiles.get(t):
                r["conviction"] = profiles[t]
            if entry_sig.get(t):
                r["entry_signal"] = entry_sig[t]     # the entry-timing gauge for the card
            if risk_sig.get(t):
                r["risk_sizing"] = risk_sig[t]       # the vol-managed sizing for the card / bot
        wide["buy"] = entry_open_first(wide["buy"])   # entry-open-first, then score (stable)
        wide["eligible"] = eligible          # how many passed the alignment gate
        wide["universe"] = len(cand)
        if disp_regime:                      # selection-regime gross dial (board + bot)
            wide["dispersion_regime"] = disp_regime
        (site / "factordata" / "canada_standouts.json").write_text(
            json.dumps(wide, separators=(",", ":"), default=str))
        log.info("wrote canada_standouts.json (%d buy of %d eligible / %d universe)",
                 len(wide["buy"]), eligible, len(cand))
    log.info("canada library: %d analyzed, %d limited (recent listings), %d skipped (empty/failed), %d setups",
             built, limited, failed, len(cand))
    return setups


if __name__ == "__main__":
    main()
    sys.exit(0)
