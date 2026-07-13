"""Build the searchable International analysis library (site/intlstockdata/*.json)
+ the pooled cross-market standouts ranking.

Runs the shared cycle/ladder engine (engine.cycles.analyze) over the pooled
universe (collectors/intl_universe -> data/intl_search) and writes one small JSON
per instrument that intl_stock.html fetches client-side. Each record carries its
country `flag` + `market` so the Stock dashboard can show where a name is from.

Standouts are alpha-led (developed, momentum-persistent markets, like Canada/US):
sector-neutral residual momentum LEADS, computed STRICTLY WITHIN each market
(engine.intl_stocks.compute_intl_alpha), the cycle entry is the timing overlay.
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

from engine import stock_technicals  # noqa: E402  — richer close-only technical snapshot
from engine import vol_squeeze  # noqa: E402  — single-stock volatility black hole (close-only)
from engine.cycles import analyze  # noqa: E402
from engine.intl_stocks import compute_intl_alpha, panel  # noqa: E402
from engine.setups import rank_setups, setup_score  # noqa: E402
from engine import stock_score  # noqa: E402
from engine import name_score  # noqa: E402  — per-name POTENTIAL (buy-readiness) score
from engine import name_score_grader  # noqa: E402
from engine import signal_gate  # noqa: E402 — owner's confluence T1->T4 cascade (layered ON main's inclusion gate)
from engine import stock_view  # noqa: E402
from engine.technicals import season_line, seasonality, snapshot  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("intl_library")

INTL_ALPHA_WEIGHT = 0.55   # alpha-led (developed/momentum-persistent), like Canada


# ── per-ticker analyze() fan-out (mirrors build_stock_library's process pool) ──
# Fan the GIL-bound engine.cycles.analyze across processes (knobs match the US/CN/HK/CA
# builds: STOCK_LIB_WORKERS env > stock_search.workers > cpu_count, capped 8). intl's
# _one needs no market-wide context, so each item carries everything → no initializer;
# per-name post-processing stays serial in main() → output order-identical.
def _library_workers() -> int:
    n = os.environ.get("STOCK_LIB_WORKERS") or None
    if n is None:
        n = config.load().get("stock_search", {}).get("workers")
    if n is None:
        n = os.cpu_count() or 1
    return max(1, min(int(n), 8))


def _intl_one_task(item):
    ticker, close, name, sector, flag, market = item
    try:
        return _one(ticker, close, name, sector, flag, market,
                    allow_limited=True)  # universe-wide opt-in mirroring the CN build
    except Exception as e:  # noqa: BLE001 — one bad ticker must not kill the library
        log.debug("intl library %s failed: %s", ticker, e)
        return None


def _analyze_universe(uni):
    """Run _one over the universe, parallel when worthwhile else serial; recs align
    1:1 with uni. Any pool error degrades to serial — parallelism never breaks the build."""
    workers = _library_workers()
    if workers > 1 and len(uni) > 50:
        try:
            from concurrent.futures import ProcessPoolExecutor
            t0 = time.time()
            with ProcessPoolExecutor(max_workers=workers) as ex:
                recs = list(ex.map(_intl_one_task, uni, chunksize=8))
            log.info("intl library: analysed %d names in %.0fs (%d processes)",
                     len(uni), time.time() - t0, workers)
            return recs
        except Exception as e:  # noqa: BLE001 — parallelism must never break the build
            log.warning("parallel intl library build failed (%s) — serial fallback", e)
    t0 = time.time()
    recs = [_intl_one_task(item) for item in uni]
    log.info("intl library: analysed %d names in %.0fs (serial)", len(uni), time.time() - t0)
    return recs

# Yahoo suffix -> TradingView exchange prefix (best-effort; embed degrades if off)
_TV_EXCH = {".T": "TSE", ".KS": "KRX", ".KQ": "KOSDAQ", ".TW": "TWSE", ".L": "LSE",
            ".DE": "XETR", ".PA": "EURONEXT", ".AS": "EURONEXT", ".BR": "EURONEXT",
            ".MI": "MIL", ".MC": "BME", ".SW": "SIX", ".ST": "OMXSTO", ".HE": "OMXHEX",
            ".CO": "OMXCOP", ".OL": "OSL", ".VI": "VIE", ".LS": "EURONEXT", ".IR": "EURONEXT"}


def _limited_rec(ticker: str, c: pd.Series, name: str, sector: str,
                 flag: str, market: str) -> dict:
    """A minimal, honest record for a name too new for the cycle model (a recent
    international listing under the 300-session floor). US/CN-parity port of
    build_stock_library._limited_rec / build_china_library._limited_rec: identity,
    listing date, session count, flag, market and the LIMITED sentinel state
    (intl_stock keys off `limited` before ever reading the ladder), so the
    click-through from search suggestions never 404s. Note: intl_stock.html charts
    from site/intlohlc/ which emit_close_only builds off the index — no `chart` key
    needed here; charts are free once indexed, exactly like China."""
    return {
        "ticker": ticker, "name": name, "sector": sector, "tv": tv_symbol(ticker),
        "flag": flag, "market": market,
        "asof": str(c.index.max().date()),
        "listed": str(c.index.min().date()),
        "history_days": int(len(c)),
        "limited": True,
        "ladder": {"state": "LIMITED"},
    }


def tv_symbol(ticker: str) -> str:
    for sfx, exch in _TV_EXCH.items():
        if ticker.endswith(sfx):
            return f"{exch}:{ticker[:-len(sfx)].replace('-', '.')}"
    return ticker


def _one(ticker: str, close: pd.Series, name: str, sector: str,
         flag: str, market: str,
         min_days: int = 300, allow_limited: bool = False) -> dict | None:
    c = close.dropna()
    if not len(c):
        return None
    # The search universe and this library share the same intl_search panel, so a
    # name the search suggestions return must never 404 on click-through: below the
    # 300-session cycle floor we emit an honest LIMITED record (searchable identity +
    # listing date + chart, "analysis pending") instead of dropping the name —
    # display-tier context ships freely; the full read unlocks as history accrues.
    # allow_limited covers the WHOLE universe (universe-wide, mirroring the CN build).
    if len(c) < min_days:
        return _limited_rec(ticker, c, name, sector, flag, market) if allow_limited else None
    res = analyze(c, None, kind="equity")
    if not res.get("ladder"):
        return _limited_rec(ticker, c, name, sector, flag, market) if allow_limited else None
    month = int(c.index.max().month)
    seas = seasonality(c)
    # RICH close-only technicals (engine.stock_technicals: momentum / 52w-high proximity / BBWP /
    # HVP / RSI / MA regime) supersede the thin close-only snapshot — best-effort so a thin/odd
    # series never breaks the build. The single-stock volatility black hole is added too.
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
        "flag": flag, "market": market,
        "asof": str(c.index.max().date()), "history_days": int(len(c)),
        "tech": _tech, "vol_squeeze": _sq,
        "season_this": season_line(seas, month),
        "season_next": season_line(seas, month % 12 + 1),
        "season_this_zh": season_line(seas, month, zh=True),
        "season_next_zh": season_line(seas, month % 12 + 1, zh=True),
        **res,
    }


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
    return (f'<svg class="nch" viewBox="0 0 {w} {h}" preserveAspectRatio="none" width="100%" height="{h}">'
            f'<polyline points="0,{h} {pts} {w},{h}" fill="{color}" opacity="0.12" stroke="none"/>'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.7" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{color}"/></svg>')


def _cone_note(anticipation: dict | None) -> list[dict] | None:
    """The favourable forward-risk-cone honesty note for a standout card. Mirrors the
    engine.stock_score 'anticipation' note (constructive risk SHAPE the factor axes don't
    price), surfaced here because the intl standouts board carries no full Conviction
    profile. Fires only when the medium-horizon cone is meaningfully favourable
    (anticipation_index ≥ 65, not thin, median upside ≥ 1.5× average drawdown). The
    percentile-RANK note is conviction-score-bound, so it never applies on this board.
    Best-effort — any odd shape yields None."""
    if not anticipation:
        return None
    try:
        ah = ((anticipation.get("horizons") or {}).get("medium") or {})
        aidx = anticipation.get("anticipation_index")
        mfe, dd = ah.get("mfe_med"), ah.get("dd_avg")
        if (aidx is not None and aidx >= 65 and not ah.get("thin")
                and mfe and dd and dd != 0 and (mfe / abs(dd)) >= 1.5):
            return [{
                "kind": "anticipation",
                "en": f"Forward risk cone is favourable (≈{mfe:.0f}% median upside vs "
                      f"≈{abs(dd):.0f}% average drawdown) — a constructive risk SHAPE the "
                      "factor axes don't price.",
                "zh": f"前瞻风险锥形态有利（中位上行约 {mfe:.0f}% 对平均回撤约 {abs(dd):.0f}%）——"
                      "因子维度未计入的有利风险形态。"}]
    except Exception:  # noqa: BLE001 — additive note, never fatal
        return None
    return None


def compute_intl_global_betas(closes, members) -> dict:
    """Per-stock GLOBAL-RISK beta for the Intl board — the country-slot card for ex-US
    names. Intl (like HK) has no idiosyncratic stock-selection edge, so the meaningful
    cross-market read is how much each name AMPLIFIES vs CUSHIONS global risk; oil/gold/
    CAD betas (the TSX card) don't apply off the Composite. Reuses engine/hk_global_beta
    with the S&P 500 (overnight) as the global-risk factor. Best-effort → {} on any
    failure, so the card simply stays absent (graceful). Returns {ticker: {beta, beta_pct,
    role, tilt}} consumed by stock_view._card_global_beta."""
    try:
        from engine import hk_global_beta
        spy = store.read("yahoo", "SPY")
        if spy is None or "close" not in spy.columns:
            log.warning("intl global-beta: no SPY factor series — skipped")
            return {}
        factor = spy["close"].pct_change(fill_method=None).shift(1)   # US -> intl overnight
        cols = [t for t in members.index if t in closes.columns]
        tkr_name = {t: str(members.loc[t, "name"]) for t in cols}
        tkr_sector = {t: str(members.loc[t, "sector"]) for t in cols}
        try:
            from engine import hk_global
            risk_state = hk_global.snapshot().get("state", "unknown")
        except Exception:  # noqa: BLE001 — risk state only colours the tilt; safe to omit
            risk_state = "unknown"
        out = hk_global_beta.compute_global_betas(closes, factor, risk_state, tkr_name, tkr_sector)
        pt = (out or {}).get("per_ticker", {})
        log.info("intl global-beta: %d names", len(pt))
        return pt
    except Exception as e:  # noqa: BLE001 — additive country card, never fatal
        log.warning("intl global-beta unavailable (%s)", e)
        return {}


def main(alpha: dict | None = None) -> dict | None:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    outdir = site / "intlstockdata"
    outdir.mkdir(parents=True, exist_ok=True)

    closes, members = panel()
    if closes.empty or members.empty:
        log.warning("intl library: no universe panel — skipped")
        return None
    if alpha is None:
        alpha = compute_intl_alpha(closes, members)
    alpha_pt = (alpha or {}).get("per_ticker", {})
    gbeta = compute_intl_global_betas(closes, members)   # global-risk-beta country-slot card

    # hoist the forward-anticipation engine + its gate ONCE (the cone is close-driven; the gate
    # read would otherwise repeat per name). None-safe: if the engine is unavailable, the cone is
    # simply skipped. The benchmark is per-COUNTRY (each market's own index, the same series the
    # within-market residual-alpha leg uses) — loaded once into a close map, picked per name. All
    # best-effort so a missing index just leaves the cone benchmark-less for that market.
    try:
        from engine.anticipation import anticipate as _anticipate, load_gate as _load_gate
        _ant_gate = _load_gate("US")
    except Exception:  # noqa: BLE001
        _anticipate = None
        _ant_gate = None
    tkr_country = {t: str(c) for t, c in members["country"].items()} if "country" in members.columns else {}
    bench_by_cc: dict[str, pd.Series] = {}
    try:
        _cc_idx = {cc: v.get("index") for cc, v in config.load()["intl"]["countries"].items()}
        for cc, idx_sym in _cc_idx.items():
            if not idx_sym:
                continue
            try:
                _bdf = store.read("intl", idx_sym)
                if _bdf is not None and "close" in _bdf.columns:
                    bench_by_cc[cc] = _bdf["close"]
            except Exception:  # noqa: BLE001 — one missing index can't break the build
                continue
    except Exception as e:  # noqa: BLE001 — additive cone, never fatal
        log.warning("intl anticipation benchmarks unavailable (%s)", e)

    index, cand, built, failed, limited = [], [], 0, 0, 0
    uni = []
    for ticker in closes.columns:
        if ticker not in members.index:
            continue
        m = members.loc[ticker]
        uni.append((ticker, closes[ticker], str(m["name"]), str(m["sector"]),
                    str(m["flag"]), str(m["market"])))
    recs = _analyze_universe(uni)           # parallel analyze() fan-out (order-preserving)
    profiles: dict[str, dict] = {}
    sig_verdict: dict[str, dict] = {}       # owner's confluence T1->T4 cascade verdict per name
    to_write: list[tuple[str, dict]] = []
    for (ticker, close, name, sector, flag, market), rec in zip(uni, recs):
        if rec is None:
            failed += 1
            continue
        if rec.get("limited"):
            # recent listing under the history floor — searchable identity + honest
            # "analysis pending" detail page (renderLimited), but it NEVER enters
            # scoring / standouts / profiles (accrual without authority).
            to_write.append((ticker.replace("=", "_").replace("^", "_"), rec))
            index.append({"t": ticker, "n": rec["name"], "s": rec["sector"], "st": "LIMITED",
                          "fl": rec["flag"], "mk": rec["market"]})
            limited += 1
            continue
        # COMBINE: confluence cascade computed alongside the residual-alpha selection — additive.
        # It NEVER changes eligibility (the rank_setups alpha floor stays the inclusion gate); it
        # only adds the per-card tier badge and re-ranks WITHIN setups["buy"] below.
        sig_verdict[ticker] = signal_gate.gate(ticker, close)
        if alpha_pt.get(ticker):
            rec["alpha"] = alpha_pt[ticker]
            sc = setup_score(rec, alpha_weight=INTL_ALPHA_WEIGHT)
            if sc:
                cand.append(sc)
        if gbeta.get(ticker):                  # global-risk-beta country-slot card (additive)
            rec["global_beta"] = gbeta[ticker]
        # forward anticipation cone (close-only) — feeds the risk-shape entry tilt + favourable-cone
        # note in the shared engine; benchmark = the name's own-market index. Best-effort.
        if _anticipate is not None:
            try:
                _ant = _anticipate(close.dropna(), bench=bench_by_cc.get(tkr_country.get(ticker)),
                                   asset_class="intl_equity", gate=_ant_gate)
                if _ant:
                    rec["anticipation"] = _ant
            except Exception:  # noqa: BLE001 — additive cone, never fatal
                pass
        # unified Conviction Profile (engine/stock_score, INTL market). Intl is
        # momentum-persistent like the TSX → residual-momentum selection prior, framed as
        # unvalidated context. The explicit INTL market avoids the HK no-alpha/never-Buy
        # fall-through that calling conviction_profile(rec, "INTL") used to hit.
        norm = stock_score.normalize_rec(rec, "INTL")
        rec["conviction"] = stock_score.conviction_profile(
            norm, "INTL", ctx={"as_of": (alpha or {}).get("as_of")})
        # ---- POTENTIAL score (engine/name_score, INTL) — front-running buy-readiness ----
        # Cycle-trigger timing blended with the residual-momentum prior. Overridden below.
        try:
            rec.setdefault("ticker", ticker)
            _sel_z = ((rec["conviction"].get("axes") or {}).get("selection") or {}).get("z")
            rec["conviction"]["potential"] = name_score.potential_score(
                rec, market="INTL", edge_z=_sel_z)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("INTL potential score for %s failed (%s)", ticker, e)
        profiles[ticker] = rec["conviction"]
        safe = ticker.replace("=", "_").replace("^", "_")
        to_write.append((safe, rec))
        idx = {"t": ticker, "n": rec["name"], "s": rec["sector"], "st": rec["ladder"]["state"],
               "fl": rec["flag"], "mk": rec["market"]}
        if rec.get("alpha", {}).get("alpha") is not None:
            idx["a"] = rec["alpha"]["alpha"]
        index.append(idx)
        built += 1

    # within-market percentile display score (mutates each conviction in place), then write
    stock_score.attach_panel_scores(profiles, "INTL")
    # INTL DISPLAYED score = the POTENTIAL (buy-readiness), not the comp-z percentile (kept
    # as rank_pctile). Front-running timing that still respects the momentum prior.
    _icalls = []
    for _safe, _rec in to_write:
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
            _icalls.append({**_pot["call"], "level": (_rec.get("tech") or {}).get("price")})
    try:
        if _icalls:
            name_score_grader.append_name_calls(_icalls, market="INTL",
                                                asof=str(pd.Timestamp.utcnow().date()))
    except Exception as e:  # noqa: BLE001 — grading is additive, never fatal
        log.warning("INTL name-score grader append failed (%s)", e)
    # ---- B2 accrual (research/LABEL_FALTERING_PHASE0.md §2) — archive per-basket member-
    # conviction stats (potential median/IQR/n + theme score/label) so the pre-registered
    # demotion study can run once ≥180 trading days accrue. Write-only ledger, never fatal.
    try:
        from engine import conviction_accrual
        _b2_asof = (alpha or {}).get("as_of")
        if conviction_accrual.archive_member_conviction("intl", profiles, asof=_b2_asof):
            log.info("B2 conviction accrual: archived conviction_intl for %s", _b2_asof)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("B2 conviction accrual (intl) failed (%s)", e)
    for safe, rec in to_write:
        rec["view"] = stock_view.build_view(rec, "INTL")
        (outdir / f"{safe}.json").write_text(json.dumps(rec, default=str))

    (outdir / "index.json").write_text(json.dumps(index))
    # Bespoke chart OHLC (close-only area series) read by intl_stock.html's chart.js —
    # pure serialisation of intl_search closes; never break the library over the garnish.
    try:
        from scripts.build_chart_data import emit_close_only
        nc = emit_close_only(outdir / "index.json", config.data_dir() / "intl_search" / "closes.parquet",
                             outdir.parent / "intlohlc", "intl")
        log.info("intl chart data: %d ohlc files", nc)
    except Exception as e:  # noqa: BLE001
        log.warning("intl chart data step failed (%s)", e)

    # pooled alpha-led "standout individual stocks" shortlist (flags attached)
    setups = None
    if cand:
        setups = rank_setups(cand, as_of=(alpha or {}).get("as_of"), rank_by="alpha", n_buy=60)
        for r in (setups.get("buy") or []):
            t = r["ticker"]
            r["signal"] = signal_gate.compact(sig_verdict.get(t))   # confluence T1->T4 tier badge
            if t in members.index:
                r["flag"] = str(members.loc[t, "flag"])
                r["market"] = str(members.loc[t, "market"])
            f = outdir / f"{t.replace('=', '_').replace('^', '_')}.json"
            if f.exists():
                try:
                    _rec = json.loads(f.read_text())
                    tech = _rec.get("tech", {})
                    r["price"] = tech.get("price")
                    r["off_high"] = tech.get("off_52w_high_pct")
                    # the new card chips (China-parity): the single-stock vol black hole +
                    # the favourable forward-cone honesty note (the intl board has no full
                    # Conviction profile, so these ride directly on the buy row).
                    if _rec.get("vol_squeeze"):
                        r["vol_squeeze"] = _rec["vol_squeeze"]
                    _notes = _cone_note(_rec.get("anticipation"))
                    if _notes:
                        r["notes"] = _notes
                except Exception:  # noqa: BLE001
                    pass
            if t in closes.columns:
                s = closes[t].dropna().tail(64).tolist()
                col = ("var(--up)" if r.get("dir") == "up" else
                       "var(--down)" if r.get("dir") == "down" else "var(--muted)")
                r["spark_svg"] = _spark_svg(s, color=col)
        # COMBINE re-rank: keep the SAME buy names (alpha floor unchanged), order by the owner's
        # weighted cascade blend — alpha base lifted by the T1->T4 weight. Weightless names sink to
        # their alpha rank. Intl has no alignment tiers, so blend_sorted (no tier split) is faithful.
        setups["buy"] = signal_gate.blend_sorted(
            setups.get("buy") or [], base_of=lambda r: r.get("alpha"),
            verdict_of=lambda r: sig_verdict.get(r.get("ticker")))
        (site / "factordata").mkdir(parents=True, exist_ok=True)
        (site / "factordata" / "intl_setups.json").write_text(
            json.dumps(setups, separators=(",", ":"), default=str))
    log.info("intl library: %d analyzed, %d limited (recent listings), %d skipped (empty/failed), %d standouts",
             built, limited, failed, len(cand))
    return setups


if __name__ == "__main__":
    main()
    sys.exit(0)
