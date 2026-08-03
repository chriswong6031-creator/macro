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

import copy
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
from engine import china_board_rank  # noqa: E402  — Prophet v2 score + execution/lifecycle lanes
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
from lib.ticker_popularity import attach_latest_volume, latest_volume_map  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("china_library")

CSI300_ETF = "510300.SS"   # cap-weighted A-share market proxy for the residual-alpha leg
JUNK_SECTOR = "A-share"    # yfinance fallback bucket → route to the engine's skip sentinel

# Prophet v2 keeps the first screen broad but makes the visible shelf selective:
# only execution-ready T1-T3 names can enter the featured lane.  Every other raw
# gate-eligible name is preserved in one of the explicit depth lanes.
BOARD_BUY_CAP = china_board_rank.FEATURED_CAP


def _prophet_ranking_contract() -> dict:
    """Public, versioned explanation of the live China Prophet priority."""
    return {
        "definition": china_board_rank.BOARD_DEFINITION,
        "score_kind": (
            "transparent priority heuristic; not a calibrated return forecast"
        ),
        "formula_points": dict(china_board_rank.SCORE_WEIGHTS),
        "featured_requirements": {
            "signal_tiers": list(signal_gate.BUYABLE_TIERS),
            "stage": "ENTRY",
            "entry_status": ["buy_now", "partial"],
            "adv_floor_yi": china_board_rank.ADV_FLOOR_YI,
            "same_day_signal": True,
            "same_day_microstructure": True,
            "fillable": True,
            "chase_veto": False,
            "extended": False,
            "sector_cap": china_board_rank.SECTOR_CAP,
            "board_cap": china_board_rank.FEATURED_CAP,
        },
        "zero_score_authority": [
            "residual_alpha", "setup", "sector_turn", "narrative",
            "quality", "low_vol", "risk_sizing",
        ],
    }


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
        return _one(ticker, close, high, name, sector, liquidity=_CN_SHARED.get("liq"),
                    allow_limited=True)
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


def _limited_rec(ticker: str, c: pd.Series, name: str, sector: str) -> dict:
    """A minimal, honest record for a name too new for the cycle model (a recent
    A-share listing under the 300-session floor). US-parity port of
    build_stock_library._limited_rec: identity, listing date, session count and
    the LIMITED sentinel state (china_lookup keys off `limited` before ever
    reading the ladder), plus the TV symbol so the page can chart it."""
    return {
        "ticker": ticker, "name": name, "sector": sector, "tv": tv_symbol(ticker),
        "asof": str(c.index.max().date()),
        "listed": str(c.index.min().date()),
        "history_days": int(len(c)),
        "limited": True,
        "ladder": {"state": "LIMITED"},
    }


def _search_index_row(
    ticker: str,
    name: str,
    sector: str,
    status: str,
    *,
    name_en: str | None = None,
    name_zh: str | None = None,
) -> dict:
    """Build a compact bilingual row for the global ticker-search manifest."""
    english = str(name_en or name or ticker).strip()
    row = {"t": ticker, "n": english, "s": sector, "st": status}
    chinese = str(name_zh or "").strip()
    if chinese and chinese.lower() != "nan":
        row["z"] = chinese
    return row


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
         name: str, sector: str, liquidity: str | None = None,
         min_days: int = 300, allow_limited: bool = False) -> dict | None:
    c = close.dropna()
    if not len(c):
        return None
    # The heatmap and this library read the SAME china_search panel, so a name the
    # tiles render must never 404 on click-through: below the 300-session cycle
    # floor we emit an honest LIMITED record (searchable identity + listing date +
    # chart, "analysis pending") instead of dropping the name — display-tier
    # context ships freely; the full read unlocks as history accrues. Unlike the
    # US build (curated extras only), allow_limited covers the WHOLE universe here
    # because the search universe IS the heatmap universe (the 46-tile dead-end
    # class, 2026-07-12).
    if len(c) < min_days:
        return _limited_rec(ticker, c, name, sector) if allow_limited else None
    # China net-liquidity is a single market-wide regime applying to every A-share
    # name (mirrors the US build); the CN regime carries no macro_risk/VIX leg, so
    # liquidity is the only macro conviction modifier threaded into the ladder.
    res = analyze(c, high, kind="equity", liquidity=liquidity)
    if not res.get("ladder"):
        return _limited_rec(ticker, c, name, sector) if allow_limited else None
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


_REVERSAL_MEMO: dict | None = None


def compute_china_reversal() -> dict | None:
    """The "Mean-reversion watch" — the VALIDATED A-share stock signal (3-month
    within-sector deepest dips, screened for ST/delisting + a market-cap floor).
    engine/china_reversal.py; reports/china-reversal-phase0.md. Best-effort: every
    failure path degrades to None, never raises.

    Memoized per process (asia-lane runtime diet): one build_china run reaches
    here THREE times — build_china.py's own reversal-watch block, main()'s
    reversal-z map, and the CN pick-lab snapshot producer — each a full
    closes.parquet (~1,537 col) read + reversal_watch() recompute over an
    unchanged panel. Cache hits return a deep copy so no caller can mutate the
    cached result. A None result is NOT cached (a missing/corrupt panel may be
    repaired later in the same process)."""
    global _REVERSAL_MEMO
    if _REVERSAL_MEMO is not None:
        return copy.deepcopy(_REVERSAL_MEMO)
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
        _REVERSAL_MEMO = copy.deepcopy(out)
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
               w: int = 240, h: int = 42,
               zone_lo: float | None = None, zone_hi: float | None = None,
               zone_state: str | None = None) -> str:
    """Tiny theme-aware inline sparkline (area + line + last-point dot) — the same
    shape build_site._mini_svg draws for the US standout cards, replicated here to
    avoid importing the heavy build_site module. `vals` = a clean recent close list.
    zone_lo/zone_hi/zone_state (all optional): the prophet-card buy-zone band —
    args absent -> output byte-identical to the band-less render."""
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
    band = ""
    if zone_hi is not None or zone_lo is not None:
        # Buy-zone band (prophet-card E1): a horizontal price band over the right
        # 40% of the plot on the SAME lo/hi/pad scale as the polyline — filled
        # low-opacity rect when the zone is ACTIVE, dashed edge lines only when
        # PENDING. Price-clamped into the plotted window; a zone wholly outside it
        # draws nothing. The edge lines carry no fill attribute and the rect keeps
        # fill-opacity, so the prophet-card hue override (stroke on *, fill on
        # [fill]:not([fill="none"])) recolors both without flattening the band.
        try:
            zh = float(zone_hi if zone_hi is not None else zone_lo)
            zl = float(zone_lo if zone_lo is not None else zone_hi)
            zl, zh = min(zl, zh), max(zl, zh)
            if zh > 0 and zh >= lo and zl <= hi:
                yt = (h - pad) - ((min(zh, hi) - lo) / rng) * (h - 2 * pad) + pad
                yb = (h - pad) - ((max(zl, lo) - lo) / rng) * (h - 2 * pad) + pad
                x0 = w * 0.60
                if zone_state == "active":
                    band = (f'<rect x="{x0:.1f}" y="{yt:.1f}" width="{w - x0:.1f}" '
                            f'height="{max(yb - yt, 0.0):.1f}" fill="{color}" '
                            f'fill-opacity="0.09" stroke="none"/>')
                band += (f'<line x1="{x0:.1f}" y1="{yt:.1f}" x2="{w}" y2="{yt:.1f}" '
                         f'stroke="{color}" stroke-width="1" stroke-dasharray="4 3" '
                         f'stroke-opacity="0.65"/>'
                         f'<line x1="{x0:.1f}" y1="{yb:.1f}" x2="{w}" y2="{yb:.1f}" '
                         f'stroke="{color}" stroke-width="1" stroke-dasharray="4 3" '
                         f'stroke-opacity="0.65"/>')
        except (TypeError, ValueError):
            band = ""  # malformed zone — never a broken spark
    return (f'<svg class="nch" viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
            f'width="100%" height="{h}">{band}'
            f'<polyline points="0,{h} {pts} {w},{h}" fill="{color}" opacity="0.12" stroke="none"/>'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.7" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6" fill="{color}"/></svg>')


# entry statuses whose card verb is buy/near — the boards render their priced zone
# as the ACTIVE (filled) spark band; any other status with a zone is PENDING (hollow).
_ZONE_ACTIVE_STATUSES = {"buy_now", "partial", "buy_soon", "await_confluence"}


def _spark_zone(es) -> dict:
    """Optional buy-zone band kwargs for _spark_svg, from the row's entry-timing
    gauge (engine.entry_signal.assess). Mirrors the prophet-card zone-footer gate:
    a band needs a priced zone (buy_zone.high), drawn filled while the entry window
    is open or imminent (buy/near verbs) and hollow-dashed otherwise (the zone
    exists but is not the live entry plan). Missing/odd gauge -> {}."""
    if not isinstance(es, dict):
        return {}
    bz = es.get("buy_zone")
    if not isinstance(bz, dict) or bz.get("high") is None:
        return {}
    return {"zone_lo": bz.get("low"), "zone_hi": bz.get("high"),
            "zone_state": "active" if es.get("status") in _ZONE_ACTIVE_STATUSES
            else "pending"}


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
            r["spark_svg"] = _spark_svg(s, color=col,
                                        **_spark_zone(r.get("entry_signal")))
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


def _detach_board_track_plumbing(bt) -> tuple[dict | None, dict | None]:
    """Pop grade()'s F7 ``fwd_excess_map_21d`` off the board-track dict before it is
    attached to the china_standouts artifact. The map is INTERNAL plumbing keyed by
    (ticker, date) TUPLES — json.dumps rejects tuple KEYS (``default=`` only covers
    values), so leaving it on ``bt`` crashes the final artifact write and the board
    goes stale on the persisted fallback (07-13→07-16 outage, 5×SLA). Returns
    (bt, fwd_map); ``bt`` is mutated in place. The tuple keys stay intact for the
    one legitimate consumer, china_standout_audit.run_attribution."""
    if not isinstance(bt, dict):
        return bt, None
    return bt, bt.pop("fwd_excess_map_21d", None)


# Forced-verdict horizon for the CN Track-record ledger, in sessions. Held equal to
# the US desk's LEDGER_HORIZON on purpose: the two desks' headline numbers are read
# side by side, and a horizon that differed per market would make them incomparable
# for no reason a reader could see. (The board's own 21d research grade in
# china_standout_track.grade() is a separate, longer-horizon question and is
# unaffected by this.)
_CN_HORIZON = 10

# Last ledger doc emit_cn_track_ledger built, so the render path can hand the SAME
# summary to the template that the popup's table will fetch. A one-slot dict rather
# than a return-signature change: the emitter's bool return is asserted by
# tests/test_track_ledger_emitters.py and by the nightly's log line.
_CN_LAST_LEDGER: dict = {"doc": None}

# --------------------------------------------------------------------------- #
# Board-definition ERAS (Prophet Learning Loop §3 / G5)
# --------------------------------------------------------------------------- #
# The CN board's definition changed on 2026-07-30 and the ledger filtered to the new
# `cn_prophet_v2` stamp, so a record built over ~1,082 graded rows collapsed to the 15
# rows carrying the new stamp and the desk's visible history went to zero overnight.
#
# The fix is NOT to drop the filter. Pooling a pre-change and a post-change board into
# one number is the era-pooling trap: the two samples were selected by different rules,
# so their union measures neither (memory `us-board-definition-change-2026-06-25`). The
# fix is to grade BOTH eras with the SAME scorer, the SAME three rules and the SAME exit
# rule, and publish them as two clearly labelled records that are never added together.
#
# The prior era is closed: no future row can carry a null stamp, so its numbers are
# frozen and only ever need re-grading if the price history is revised.
_CN_PRIOR_ERA_ID = "cn_standout_v1"

#: Stamp values that mean "written before the definition was versioned".
_CN_LEGACY_STAMPS = frozenset({"", "nan", "none", "null", "legacy", "<na>"})

#: Newest-first cap on the prior era's row list. Read from engine.track_ledger at use
#: time so the two records can never end up with different caps.


def _cn_is_legacy_stamp(value) -> bool:
    """True when a board_definition cell predates versioning (null / '' / 'legacy')."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() in _CN_LEGACY_STAMPS


def _cn_era_span(date_from: str | None,
                 date_to: str | None) -> tuple[str | None, str | None]:
    """Bilingual date-span suffix for an era label, or (None, None) with no dates."""
    def _parts(d):
        try:
            ts = pd.Timestamp(d)
        except (TypeError, ValueError):
            return None
        # pd.Timestamp(None) yields NaT rather than raising, and NaT.strftime raises.
        return None if pd.isna(ts) else ts
    a, b = _parts(date_from), _parts(date_to)
    if a is None or b is None:
        return (None, None)
    # Month names are built from a fixed table rather than strftime: `%-d` is a
    # platform-specific extension, and a locale-sensitive `%b` would make the emitted
    # artifact depend on the runner's environment.
    mon = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    # A span that crosses New Year needs BOTH years. Each language carries the year on
    # ONE end only — EN on the close, ZH on the open — which reads correctly inside a
    # single year and LIES across two: "Nov 3 – Feb 12 2026" dates the November to
    # 2026, and "2025年11月3日–2月12日" dates the February to 2025. This is the live
    # path, not the display: _track_record_dlg.html.j2 splits label_en/label_zh on
    # ' · ' and prints this span VERBATIM (its own cross-year branch is only the
    # no-label fallback), so the same-year form below stays byte-for-byte identical.
    cross = a.year != b.year
    en_from = f"{mon[a.month - 1]} {a.day}"
    if cross:
        en_from = f"{en_from} {a.year}"
    zh_to = f"{b.month}月{b.day}日"
    if cross:
        zh_to = f"{b.year}年{zh_to}"
    return (f"{en_from} – {mon[b.month - 1]} {b.day} {b.year}",
            f"{a.year}年{a.month}月{a.day}日–{zh_to}")


def _cn_era_label(date_from: str | None, date_to: str | None) -> tuple[str, str]:
    """Bilingual label for the PRIOR (pre-version) era, from the era's own date span.

    Derived rather than hard-coded so the label cannot drift away from the rows it
    describes if the store is ever backfilled.
    """
    en_span, zh_span = _cn_era_span(date_from, date_to)
    if en_span is None:
        return ("previous board definition", "上一版选股口径")
    return (f"previous board definition · {en_span}", f"上一版选股口径 · {zh_span}")


def _cn_unknown_era_label(stamp, date_from: str | None,
                          date_to: str | None) -> tuple[str, str]:
    """Bilingual label for a board_definition stamp the era split does not recognise.

    Keyed by the STAMP VALUE, never by a position in the version history: an
    unrecognised stamp is by definition one this build has no ordering for, so the
    only honest label names it and lets the reader decide what it was.
    """
    s = str(stamp)
    en_span, zh_span = _cn_era_span(date_from, date_to)
    if en_span is None:
        return (f"other board definition · {s}", f"其他选股口径 · {s}")
    return (f"other board definition · {s} · {en_span}",
            f"其他选股口径 · {s} · {zh_span}")


def _cn_grade_era(bdf, bench_ser, look, _cst) -> dict:
    """Grade ONE era's slice of the board store into rows + summary + survivorship.

    Extracted so the live record and the prior record run the identical path: same
    episode builder, same T+1 fill, same locked-limit exclusion, same forced horizon,
    same CSI300-excess metric, same date-blocked CI. If these two ever diverge the
    comparison the panel invites a reader to make becomes meaningless, so there is
    exactly one implementation and both eras call it.
    """
    from engine import track_scoring as _ts

    rows_out, n_locked, scored, n_inflight, n_skipped = \
        _cn_ledger_rows(bdf, bench_ser, look, _cst)
    summary = _ts.summarize(scored, metric="excess", n_inflight=n_inflight,
                            n_skipped=n_skipped, horizon=_CN_HORIZON)
    summary["n_logged"] = len(rows_out)
    summary["n_locked_excluded"] = n_locked
    return {
        "rows": rows_out,
        "summary": summary,
        "n_locked": n_locked,
        "n_inflight": n_inflight,
        "n_skipped": n_skipped,
        "state": _ts.publish_state(summary),
    }


def _cn_era_block(graded: dict, *, era_id: str, label_fn, closed: bool) -> dict:
    """Publish ONE non-live era: newest-first capped rows, its own summary, its own
    publish state, and a bilingual label derived from its own date span.

    Shared by `prior_record` and by every unrecognised-stamp record in
    `extra_records`, so the two can never drift into different shapes — a consumer
    that can read one can read all of them. `label_fn(date_from, date_to)` returns
    the (en, zh) pair; the span is computed here because the label describes the
    rows this function just sorted.
    """
    from engine import track_ledger as _tl

    rows = sorted(graded["rows"], key=lambda r: (r.get("d") or ""), reverse=True)
    dates = [r["d"] for r in rows if r.get("d")]
    d_from, d_to = (min(dates), max(dates)) if dates else (None, None)
    label_en, label_zh = label_fn(d_from, d_to)
    n_total = len(rows)
    capped = rows[:_tl.MAX_ROWS]
    summary = dict(graded["summary"])
    summary["board_definition"] = era_id
    return _tl.pyify({
        "label_en": label_en,
        "label_zh": label_zh,
        "board_definition": era_id,
        "date_from": d_from,
        "date_to": d_to,
        "state": graded["state"],
        "summary": summary,
        "rows": capped,
        "meta": {
            "n_total": n_total,
            "truncated": max(0, n_total - len(capped)),
            "grain": "episode",
            "closed": closed,
            "survivorship": {
                "n_locked_excluded": graded["n_locked"],
                "n_skipped_no_price": graded["n_skipped"],
                "note": ("locked-limit T+1 rows are unfillable — flagged, "
                         "excluded from stats"),
            },
            "exit_rule": (f"{_CN_HORIZON}-session forced verdict · T+1 open fill · "
                          "no oscillator target (3D thresholds not yet refit for "
                          "A-shares)"),
            "pooling_note_en": ("Graded with the same scorer, horizon and exit rule "
                                "as the current record, and reported separately. Each "
                                "era selected its board by a different rule, so these "
                                "records must never be added together."),
            "pooling_note_zh": ("与当前记录采用完全相同的评分方法、持有期与退出规则，"
                                "但单独统计。各时期的选股口径不同，"
                                "因此绝不可合并计算。"),
        },
    })


def _cn_track_state(bt: dict | None) -> str:
    """Mirror the template's 3-state selector for the CN track panel:
      • 'scored'   when the matured 21d horizon has n>=8 scored rows,
      • 'interim'  when the unrealized interim read has n>=8,
      • 'accruing' otherwise.
    bt = china_standout_track.grade() output (with 'interim' attached), i.e. the same
    dict the template consumes — keeps the ledger's `state` and the panel in lockstep."""
    if not isinstance(bt, dict) or not bt.get("available"):
        return "accruing"
    h21 = (bt.get("by_horizon") or {}).get("21d") or {}
    # scored 21d block carries hit_vs_csi300 (n>=_MIN_GRADED=8); the accruing block is
    # {"n": <8, "note": "accruing"} — so key presence discriminates scored vs accruing.
    if isinstance(h21, dict) and (h21.get("n") or 0) >= 8 and h21.get("hit_vs_csi300") is not None:
        return "scored"
    interim = bt.get("interim") or {}
    if isinstance(interim, dict) and interim.get("available") and (interim.get("n") or 0) >= 8 \
            and interim.get("hit_vs_csi300") is not None:
        return "interim"
    return "accruing"


def _cn_ledger_rows(bdf: pd.DataFrame, bench_ser, look: dict[str, dict],
                    _cst) -> tuple[list[dict], int, list[dict], int, int]:
    """Row loop for emit_cn_track_ledger — EPISODE grain, forced-horizon verdict.

    Returns (rows, n_locked, scored, n_inflight, n_skipped).

    Rewritten 2026-07-26 onto engine.track_scoring. Three changes from the
    board_day × ticker version this replaces:

      * EPISODE GRAIN. A name on the board for ten sessions used to emit ten rows that
        all measured overlapping windows of the same move. The summary counted them as
        ten independent observations, so `n` read 840 when the desk had made roughly
        400 distinct calls across 15 nights — and the Wilson interval built on that n
        was several times too narrow to be honest.
      * FORCED VERDICT AT H=10 sessions, replacing "21d if matured, else mark to the
        latest close". Marking unmatured rows to today pooled holding periods of 1 and
        17 sessions into one hit rate.
      * DATE-BLOCKED CI (in the caller's summarize()), replacing Wilson-on-raw-n.

    A-share specifics that must NOT be shared with the US desk and are preserved here:
    the T+1 OPEN (or (H+L)/2 proxy) fill via _t1_fill, and the locked-limit exclusion —
    a bar that printed high==low==close is unfillable at any price, so those episodes
    are flagged and kept OUT of the summary. No oscillator target exit: the 3D StochRSI
    thresholds the US desk exits on were fit on US volatility and have not been refit
    for A-share limit-board dynamics, so CN runs fixed-horizon until they are.
    """
    from engine import track_scoring as _ts

    # board_day → tickers, then contiguous runs. Ordered by date so the episode
    # builder sees the history in sequence.
    board_days: dict[str, set[str]] = {}
    meta_by_tk: dict[str, dict] = {}
    for _i, brow in bdf.iterrows():
        tk = str(brow.get("ticker") or "")
        d0s = str(brow.get("date") or "")
        if not tk or not d0s:
            continue
        board_days.setdefault(d0s, set()).add(tk)
        meta_by_tk[tk] = {
            "rank": brow.get("board_rank") if pd.notna(brow.get("board_rank")) else None,
            "tier": brow.get("tier") if pd.notna(brow.get("tier")) else None,
        }

    rows_out: list[dict] = []
    scored: list[dict] = []
    n_locked = n_inflight = n_skipped = 0

    for ep in _ts.build_episodes(board_days):
        tk, d0s = ep["ticker"], ep["entry_date"]
        try:
            d0 = pd.Timestamp(d0s)
        except Exception:  # noqa: BLE001
            continue

        pdf = _cst._price_frame(tk)  # noqa: SLF001 — memoized by caller
        if pdf is None or "close" not in pdf:
            n_skipped += 1
            continue
        fill, locked_flag, _pinned = _cst._t1_fill(pdf, d0)  # noqa: SLF001

        fl: list[str] = []
        if locked_flag:
            # Unfillable at any price. Flagged for the table, excluded from the stats —
            # counting a trade nobody could enter is the A-share version of the
            # unbuyable-entry bug this whole rewrite exists to remove.
            fl.append("locked")
            n_locked += 1

        closes = pd.to_numeric(pdf["close"], errors="coerce").dropna()
        after = closes.index[closes.index > d0]
        sc = None
        if fill is not None and len(after):
            # include_fill_bar: the fill is the T+1 OPEN, so that same session's close
            # is already a legitimate day-one exit. (The US desk fills AT a close and
            # must not treat that same bar as its own exit.)
            sc = _ts.score_from_fill(closes, after[0], float(fill), _CN_HORIZON,
                                     bench_close=bench_ser, include_fill_bar=True)
        if sc is None:
            n_skipped += 1
            continue

        matured = bool(sc["matured"]) and not locked_flag
        if matured:
            # CN grades on EXCESS vs CSI300: in A-shares beta dominates, so an absolute
            # win rate would mostly measure the index, not the desk.
            x = sc.get("excess")
            st = "beat" if (x or 0) > 0 else "lag"
            sc["board_date"] = d0s
            if x is not None:
                scored.append(sc)
            entry_px, latest_px, pct, dy = sc["entry"], sc["exit"], sc["pnl"], sc["held"]
        else:
            st = "early"
            if not sc.get("fill_pending"):
                n_inflight += 1
            entry_px = sc["entry"]
            latest_px = float(closes.iloc[-1]) if len(closes) else None
            pct, dy = sc["mark"], sc["held"]
            x = None

        disp = look.get(tk, {})
        rows_out.append({
            "t": tk,
            "nm": disp.get("nm"),
            "sec": disp.get("sec"),
            "grp": None,
            "d": d0s,
            "e": round(entry_px, 2) if entry_px is not None else None,
            "l": round(latest_px, 2) if latest_px is not None else None,
            "p": round(pct, 1) if pct is not None else None,
            "x": round(x, 2) if x is not None else None,
            "dy": dy,
            "st": st,
            "m": bool(matured),
            "rk": meta_by_tk.get(tk, {}).get("rank"),
            "tr": meta_by_tk.get(tk, {}).get("tier"),
            "fl": fl,
            "xr": sc.get("exit_reason") if matured else None,
        })
    return rows_out, n_locked, scored, n_inflight, n_skipped


def emit_cn_track_ledger(
    site: Path,
    bt: dict | None,
    buy_rows: list[dict] | None,
    *,
    board_definition: str | None = None,
    asof: str | None = None,
) -> bool:
    """Emit site/factordata/cn_track_ledger.json (track_ledger/v1).

    Grain: EPISODE (contiguous board run) from data/china_standout_track/board.parquet,
    scored on CSI300-relative excess at a forced 10-session verdict via
    engine.track_scoring — the same core the US desk uses. See _cn_ledger_rows for what
    changed from the board_day × ticker version and why, and engine/track_scoring.py
    for the three rules that make the number honest.

    TWO ERAS, TWO RECORDS, NEVER ONE NUMBER
    ---------------------------------------
    The store spans a board-definition change (2026-07-30). This function grades it in
    two disjoint cohorts and emits them side by side:

      * the LIVE record — rows stamped with `board_definition` — stays exactly where
        every existing consumer expects it (`summary`, `rows`, `meta.board_definition`);
      * `prior_record` carries the pre-version rows (null / '' / 'legacy' stamps) with
        its own summary, its own rows, its own publish state and a bilingual era label.
      * `extra_records` catches any OTHER stamp in the store — one labelled block per
        stamp value. Those rows used to match neither mask and disappear from the
        artifact without a trace; they are now graded, published under their own name
        and announced with a ``::warning`` in the Actions log.

    All of them go through `_cn_grade_era`, so the scorer, horizon, fill, locked-limit
    rule and CI method are identical and a reader may legitimately compare them. They
    are never summed. Filtering to the live stamp alone is what erased the desk's
    history on 2026-07-30 (348 matured episodes at 66.7% became n=0 `accruing`
    overnight); pooling the eras would have been the opposite error, since the boards
    selected their names by different rules and their union measures neither.

    A-share specifics preserved (these are real market differences, not style):
      • T+1 OPEN (or (H+L)/2 proxy) fill via _t1_fill — CN can trade the open; the US
        desk fills at the next close.
      • locked-limit T+1 rows: fl=['locked'], flagged in the table and EXCLUDED from
        the summary. A bar that printed high==low==close is unfillable at any price.
      • EXCESS vs CSI300 is the headline, not absolute P&L: in A-shares beta dominates,
        so an absolute win rate would mostly measure the index rather than the desk.
      • no oscillator target exit — the US desk's 3D StochRSI thresholds were fit on US
        volatility and have not been refit for A-share limit boards.

    `bt` is grade()'s output already in memory (kept for callers/back-compat; the
    publish state now derives from the sample itself via track_scoring.publish_state).
    `buy_rows` = today's ranked board (wide['buy']) used only as a name/sector display
    lookup. Render budget: lib.store reads are UNCACHED, so we install a per-ticker
    memo over _cst._price_frame for the duration of the loop (try/finally restored),
    collapsing O(rows) parquet reads to O(unique tickers).
    Returns True on a successful atomic write.
    """
    from engine import track_ledger as _tl
    from engine import track_scoring as _ts
    from engine import china_standout_track as _cst

    bench_dict = {"code": "510300.SS", "en": "CSI 300", "zh": "沪深300"}
    # The live record starts as a graded EMPTY era rather than as loose counters, so the
    # "store missing / era empty" path and the "era graded" path build their summary
    # through the same call and cannot drift apart.
    live: dict = {
        "rows": [], "n_locked": 0, "n_inflight": 0, "n_skipped": 0, "state": "accruing",
        "summary": _ts.summarize([], metric="excess", n_inflight=0, n_skipped=0,
                                 horizon=_CN_HORIZON),
    }
    if not board_definition:
        board_definition = next(
            (
                r.get("board_definition")
                or (r.get("prophet") or {}).get("version")
                for r in (buy_rows or [])
                if r.get("board_definition") or (r.get("prophet") or {}).get("version")
            ),
            (bt or {}).get("board_definition"),
        )

    # name/sector display lookup. Today's ranked board carries the freshest name +
    # sector, but the ledger spans EVERY episode back to first-write — most
    # of those tickers have long since rotated off the board, so a board-only lookup
    # left ~85% of rows with no name (the receipt read as bare tickers). Backfill from
    # the curated search universe (china_search/members.parquet, 'EN / 中文' names —
    # the same table the board's own names derive from) so historical rows resolve too.
    look: dict[str, dict] = {}
    try:
        mp = config.data_dir() / "china_search" / "members.parquet"
        if mp.exists():
            mem = pd.read_parquet(mp)
            name_col = mem["name"] if "name" in mem.columns else None
            sec_col = mem["sector"] if "sector" in mem.columns else None
            for tk in mem.index:
                tks = str(tk)
                nm_v = name_col.get(tk) if name_col is not None else None
                sec_v = sec_col.get(tk) if sec_col is not None else None
                look[tks] = {
                    "nm": str(nm_v) if pd.notna(nm_v) else None,
                    "sec": str(sec_v) if pd.notna(sec_v) else None,
                }
    except Exception as _e:  # noqa: BLE001 — display enrichment only, never fatal
        log.warning("cn track_ledger name backfill skipped (%s)", _e)
    # today's board wins on conflict (freshest name/sector).
    for r in (buy_rows or []):
        tk = r.get("ticker")
        if tk:
            look[str(tk)] = {"nm": r.get("name"), "sec": r.get("sector")}

    prior: dict | None = None
    unknown: dict[str, dict] = {}
    store_path = _cst._store_path()  # noqa: SLF001 — read-only path accessor
    if store_path.exists():
        try:
            bdf_all = pd.read_parquet(store_path)
        except Exception:  # noqa: BLE001
            bdf_all = pd.DataFrame()

        # ── split the store into eras BEFORE grading anything ──────────────────
        # `bdf` is the live record's slice (unchanged behaviour and unchanged output);
        # `bdf_prior` is everything written before the definition was versioned. The
        # two masks are disjoint by construction and neither row set ever enters the
        # other's summary — that separation IS the fix (see the era note above).
        bdf, bdf_prior = bdf_all, pd.DataFrame()
        unknown_slices: dict[str, pd.DataFrame] = {}
        if not bdf_all.empty:
            has_col = "board_definition" in bdf_all.columns
            legacy_current = _cn_is_legacy_stamp(board_definition)
            if board_definition and has_col:
                stamps = bdf_all["board_definition"]
                is_legacy = stamps.map(_cn_is_legacy_stamp)
                # With a pre-version LIVE definition every pre-version spelling IS the
                # live era — the same reading the no-stamp-column branch below takes —
                # and there is no prior era to publish beside it.
                live_mask = is_legacy if legacy_current else \
                    (stamps.astype(str) == str(board_definition))
                prior_mask = pd.Series(False, index=bdf_all.index) if legacy_current \
                    else is_legacy
                bdf = bdf_all[live_mask].copy()
                bdf_prior = bdf_all[prior_mask].copy()

                # ── rows NO era claimed ───────────────────────────────────────
                # A stamp this build has never heard of matched neither mask and fell
                # straight out of the artifact: the store kept the rows, the desk
                # simply stopped counting them, and nothing said so. Every unclaimed
                # stamp now gets its OWN labelled record — never pooled with either
                # known era, for exactly the reason the two known eras are never
                # pooled — plus a line-start Actions annotation naming it.
                orphan = bdf_all[~(live_mask | prior_mask)]
                if not orphan.empty:
                    for _stamp, _grp in orphan.groupby(
                            orphan["board_definition"].astype(str), sort=True):
                        _stamp = str(_stamp)
                        unknown_slices[_stamp] = _grp.copy()
                        # Bare print, NOT log.* — a logger prefixes the line and
                        # GitHub only parses '::' at column 0 (CLAUDE.md). The opening
                        # literal stays on the `print(` line on purpose: the repo guard
                        # (tests/test_gh_annotation_line_start.py) prefilters files on
                        # the bytes `("::`, so a call split before its first literal is
                        # invisible to it. flush because CI pipes stdout block-buffered.
                        print("::warning title=cn-track-unknown-board-definition::"
                              f"CN track ledger: {len(_grp)} board row(s) carry "
                              f"board_definition '{_stamp}' — neither the live stamp "
                              f"'{board_definition}' nor a pre-version stamp. Split "
                              "into its own labelled era (extra_records), never "
                              "pooled with either.", flush=True)
            elif board_definition and not legacy_current:
                # Never publish a pre-version ledger under a new board label. The rows
                # are not lost — with no stamp column at all, every row IS the prior era.
                bdf = pd.DataFrame()
                bdf_prior = bdf_all.copy()

        if not bdf.empty or not bdf_prior.empty or unknown_slices:
            bench_ser = _cst._bench_close()  # noqa: SLF001 — single read, reused below
            _pf_orig = _cst._price_frame
            _pf_memo: dict[str, pd.DataFrame | None] = {}

            def _pf_cached(tk: str) -> pd.DataFrame | None:
                if tk not in _pf_memo:
                    _pf_memo[tk] = _pf_orig(tk)
                return _pf_memo[tk]

            # One memo across EVERY era: the same names appear either side of the
            # definition change, and the store reads are uncached (render budget).
            _cst._price_frame = _pf_cached  # type: ignore[assignment]  # noqa: SLF001
            try:
                if not bdf.empty:
                    live = _cn_grade_era(bdf, bench_ser, look, _cst)
                if not bdf_prior.empty:
                    prior = _cn_grade_era(bdf_prior, bench_ser, look, _cst)
                for _stamp, _slice in unknown_slices.items():
                    unknown[_stamp] = _cn_grade_era(_slice, bench_ser, look, _cst)
            finally:
                _cst._price_frame = _pf_orig  # noqa: SLF001
                _pf_memo.clear()

    # Summary over MATURED, non-locked episodes only, scored on CSI300 excess. The CI
    # is date-blocked (engine.track_scoring) — episodes surfaced on the same board
    # night share the market's move and the ranker's state, so they are one bet. The
    # Wilson-on-raw-n this replaces reported 50.5–57.3% off 840 overlapping board-day
    # rows spanning 15 nights; that interval could not have been right.
    rows_out = live["rows"]
    n_locked, n_skipped = live["n_locked"], live["n_skipped"]
    summary = live["summary"]
    summary["board_definition"] = board_definition
    state = _ts.publish_state(summary)

    as_of = asof
    if rows_out:
        as_of = max((r["d"] for r in rows_out if r["d"]), default=None)

    doc = _tl.build_shell(
        "CN", as_of, state, bench_dict, summary, rows_out, grain="episode",
        survivorship={"n_locked_excluded": n_locked, "n_skipped_no_price": n_skipped,
                      "note": "locked-limit T+1 rows are unfillable — flagged, excluded from stats"},
        extra_meta={
            "board_definition": board_definition,
            "exit_rule": f"{_CN_HORIZON}-session forced verdict · T+1 open fill · "
                         "no oscillator target (3D thresholds not yet refit for A-shares)",
        },
    )

    # ── the prior-definition record, alongside and NEVER pooled ────────────────
    # `closed=True`: no future row can carry a null stamp, so this era's numbers are
    # frozen and only ever move if the price history is revised.
    if prior and prior["rows"]:
        doc["prior_record"] = _cn_era_block(
            prior, era_id=_CN_PRIOR_ERA_ID, label_fn=_cn_era_label, closed=True)

    # ── stamps this build does not recognise — labelled, never dropped ─────────
    # Same block shape as prior_record, keyed by the stamp itself, and NOT marked
    # closed: an unknown stamp is one this build has no version ordering for, so it
    # cannot honestly claim the era stopped accruing.
    extras = [
        _cn_era_block(graded, era_id=stamp, closed=False,
                      label_fn=lambda a, b, _s=stamp: _cn_unknown_era_label(_s, a, b))
        for stamp, graded in unknown.items() if graded["rows"]
    ]
    if extras:
        doc["extra_records"] = extras

    _CN_LAST_LEDGER["doc"] = doc
    return _tl.atomic_write(site / "factordata" / "cn_track_ledger.json", doc)


def _find_bad_json_keys(obj, path: str = "$") -> list[str]:
    """Locate dict keys json.dumps would reject (anything not str/int/float/bool/None),
    returning JSONPath-ish strings. Diagnostic for the artifact-write guard below —
    a bare TypeError from json.dumps never says WHICH key, so regressions were
    unlocatable from CI logs."""
    bad: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, (str, int, float, bool, type(None))):
                bad.append(f"{path}.{k!r} (key type {type(k).__name__})")
            bad.extend(_find_bad_json_keys(v, f"{path}.{k}"))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            bad.extend(_find_bad_json_keys(v, f"{path}[{i}]"))
    return bad


def _attach_eligible_coiled_fire(
    coiled_by: dict[str, dict],
    verdict_by: dict[str, dict],
    close_by: dict[str, pd.Series],
) -> int:
    """Attach the display-only COILED-FIRE receipt where it can be published.

    China Prophet serializes only raw-gate-eligible rows into its four board
    lanes.  Full-universe research stores persist ``coiled``/``star`` but do not
    consume the fire receipt, so evaluating the expensive multi-timeframe fire
    detector for ineligible names cannot affect any score, lane, or artifact.

    Returns the number of eligible COILED names evaluated. One malformed series
    is skipped without suppressing the otherwise valid cross-sectional verdicts.
    """
    evaluated = 0
    for ticker, payload in coiled_by.items():
        if (
            not isinstance(payload, dict)
            or not payload.get("coiled")
            or not (verdict_by.get(ticker) or {}).get("eligible")
        ):
            continue
        close = close_by.get(ticker)
        if close is None:
            continue
        evaluated += 1
        try:
            fire = coiled.fire_recent(close)
        except Exception:  # noqa: BLE001 — display receipt never suppresses rank state
            continue
        if isinstance(fire, dict) and fire.get("fire"):
            payload["fire"] = True
            payload["fire_ticks"] = fire.get("ticks")
            payload["fire_src"] = fire.get("src")
    return evaluated


def main(alpha: dict | None = None) -> dict | None:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    outdir = site / "chinastockdata"
    outdir.mkdir(parents=True, exist_ok=True)

    # Section wall-clock ticks (asia-lane runtime diet observability): this build
    # grew ~20 -> ~33+ min during 2026-07-02..10 with no per-section evidence of
    # where — the collect loop has "collect timing total"; this is the builder's
    # equivalent. Grep "[timing]" in the lane log to profile a run.
    _tick_t0 = time.monotonic()
    _tick_prev = [_tick_t0]

    def _tick(label: str) -> None:
        _now = time.monotonic()
        log.info("[timing] %-34s +%6.1fs (cum %7.1fs)",
                 label, _now - _tick_prev[0], _now - _tick_t0)
        _tick_prev[0] = _now

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
                      # china_inquiry has been FULLY RETIRED (W4 review fix): inquiry letters are
                      # now sourced exclusively from collectors/china_filings.py →
                      # data/china_filings/filings.parquet (category=='inquiry_letter').
                      # The engine's read-fallback to the frozen data/china_inquiry/inquiry.parquet
                      # stays in place to surface honest asof staleness if filings degrades.
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
                      ("collectors.tushare_history", {})):    # daily-grid flow/chips history → china_validation
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
    _tick("context drips + tushare health")

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
    name_en_by: dict[str, str] = {}
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
            if "name_en" in mdf.columns:
                name_en_by = {str(r[tcol]): str(r["name_en"])
                              for _, r in mdf.iterrows() if pd.notna(r.get("name_en"))}
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

    # Resolve the stock responsibility panel before any market context that can
    # influence live score. Context ETFs/indices remain in ``uni`` for library
    # pages, but neither their dates nor later context observations may advance
    # the Prophet decision clock.
    uni = universe()
    latest_volumes = latest_volume_map("cn")
    _close_map: dict[str, pd.Series] = {
        ticker: close
        for ticker, close, *_rest in uni
        if close is not None
    }
    _stock_universe_tickers = {
        _t for (_t, _c, _h, _n, _s) in uni
        if _s not in {"Sector ETF", "Index"}
    }
    _panel_asof = china_board_rank.stock_panel_asof(
        uni,
        _stock_universe_tickers,
    )

    # QVIX vol-regime overlay — the GEX-analog for A-shares (no single-stock options). A panic SPIKE
    # (qvix_z high) is the crash-risk regime → a CN macro risk_overlay that taxes a chase + vetoes a
    # high-conviction verb, mirroring the US VIX overlay. INVERTED interpretation (engine/china_signals).
    qvix_reg = None
    cn_risk_overlay: dict = {"stress": 0.0, "drivers": []}
    try:
        _qp = config.data_dir() / "china_qvix" / "qvix300.parquet"
        if _qp.exists() and _panel_asof is not None:
            _qvix_frame = pd.read_parquet(_qp)
            _qvix_frame.index = pd.to_datetime(
                _qvix_frame.index,
                errors="coerce",
            )
            _qvix_frame = _qvix_frame[
                _qvix_frame.index.notna()
                & (_qvix_frame.index <= pd.Timestamp(_panel_asof))
            ]
            if not _qvix_frame.empty and "close" in _qvix_frame:
                qvix_reg = china_signals.qvix_regime(
                    _qvix_frame["close"]
                )
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
        if _csi_close is not None and _panel_asof is not None:
            _csi_close = _csi_close.loc[:pd.Timestamp(_panel_asof)]
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
            if (
                not _flog.empty
                and "date" in _flog.columns
                and _panel_asof is not None
            ):
                _flog["_pit_date"] = pd.to_datetime(
                    _flog["date"],
                    errors="coerce",
                )
                _flog = _flog[
                    _flog["_pit_date"].notna()
                    & (_flog["_pit_date"] <= pd.Timestamp(_panel_asof))
                ]
                _latest_date = (
                    _flog["_pit_date"].max() if not _flog.empty else None
                )
                _flog_latest = (
                    _flog[_flog["_pit_date"] == _latest_date].copy()
                    if _latest_date is not None
                    else _flog.iloc[0:0].copy()
                )
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
                            "asof":      str(pd.Timestamp(_latest_date).date()),
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
    reversal_context_by: dict[str, dict] = {}
    _reversal_asof: str | None = None
    try:
        _rev = compute_china_reversal() or {}
        _reversal_asof = str(_rev.get("as_of") or "")[:10] or None
        # rev_z_all covers the WHOLE screened universe (the fix): the validated reversal selection
        # leg now populates conviction for every name, not just the top-16 display watch list.
        rev_z_by = dict(_rev.get("rev_z_all") or {})
        for _r in _rev.get("watch", []):            # back-compat: ensure the display names are in too
            if _r.get("ticker") and _r.get("rev_z") is not None:
                rev_z_by.setdefault(_r["ticker"], _r["rev_z"])
        reversal_context_by = dict(_rev.get("reversal_all") or {})
        log.info("china reversal-z: populated for %d names (was top-16 only)", len(rev_z_by))
    except Exception as e:  # noqa: BLE001 — additive leg, never fatal
        log.warning("china reversal-z map unavailable (%s)", e)
    _tick("alpha + reversal-z legs")
    basket_tw = _basket_tailwind_map()          # Conviction "upside / theme tailwind" axis

    index, cand, prophet_cand, built, failed, limited = [], [], [], 0, 0, 0
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
    screen_drop = {"st": 0, "mcap": 0, "adv": 0, "stale": 0, "non_stock": 0}
    MCAP_FLOOR_YI = 30.0            # matches china_reversal; 30.0 exactly is the placeholder => "unknown"
    STALE_DAYS = 15                 # a name whose last bar is >15 calendar days stale is likely
    #                                suspended/delisted (e.g. a frozen HK/A name) — never a live buy.
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

    _tick("universe assembly + screens")
    recs = _analyze_universe(uni, liq)      # parallel analyze() fan-out (order-preserving)
    _tick("cycles analyze fan-out")
    sig_verdict: dict[str, dict] = {}       # owner's confluence T1->T4 cascade verdict per name
    # COILED wave-3 CN ranking bonus: per-name inputs collected in the loop; cohort_fractions
    # computed AFTER the loop (cross-sectional). CN gate: clean15 +7.33pp, stop5 −6.21pp, n=10,784.
    # HK failed its gate — touch NOTHING in HK.
    _coil_d:      dict[str, float | None] = {}
    _coil_wash:   dict[str, bool | None]  = {}
    _coil_div:    dict[str, bool]         = {}
    _coil_sector: dict[str, str | None]   = {}
    _hold_state_cn: dict[str, dict]       = {}   # W0.1 HOLD tracker (display/ledger only; never in _cn_bonus)
    for (ticker, close, high, name, sector), rec in zip(uni, recs):
        if rec is None:
            failed += 1
            continue
        if rec.get("limited"):
            # recent listing under the history floor — searchable identity + honest
            # "analysis pending" detail page (renderLimited), but it NEVER enters
            # scoring / boards / profiles (accrual without authority).
            to_write.append((_safe(ticker), rec))
            index.append(_search_index_row(
                ticker, name, sector, "LIMITED",
                name_en=name_en_by.get(ticker), name_zh=name_zh_by.get(ticker),
            ))
            limited += 1
            continue
        # COMBINE: the confluence T1->T4 cascade is computed alongside main's bottoming-alignment
        # gate. It NEVER changes which names are eligible (alignment stays the inclusion gate) —
        # it only adds the per-card tier badge and re-ranks WITHIN the aligned buy list (below).
        sig_verdict[ticker] = signal_gate.gate(ticker, close)
        # signal_gate.asof is the label of its 3-business-day indicator bucket,
        # which can legitimately be one or two calendar sessions behind the
        # latest input. Preserve that analytical label, but add the actual daily
        # input receipt for same-session Prophet admission.
        _signal_input_last = close.last_valid_index()
        sig_verdict[ticker]["input_asof"] = (
            str(pd.Timestamp(_signal_input_last).date())
            if _signal_input_last is not None
            else None
        )
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
        except Exception:  # noqa: BLE001 — additive, never fatal
            pass
        # Residual alpha remains useful display context and powers the legacy
        # laggards strip, but it is no longer an admission dependency for Prophet
        # v2.  Build one board-shape row for every analyzed responsibility-screened
        # name; missing alpha/setup stays explicitly null.
        if alpha_pt.get(ticker):
            rec["alpha"] = alpha_pt[ticker]
        sc = _setup_score(rec) if rec.get("alpha") else None
        _lad = rec.get("ladder") or {}
        _lad_entry = _lad.get("entry") or {}
        _alpha_row = rec.get("alpha") or {}
        _prophet_row = {
            "ticker": ticker,
            "name": name,
            "sector": sector,
            "alpha": _alpha_row.get("alpha"),
            "alpha_entry": _alpha_row.get("entry"),
            "state": _lad.get("state"),
            "label": _lad.get("label"),
            "label_zh": _lad.get("label_zh"),
            "urgency": _lad_entry.get("urgency"),
            "dir": _lad.get("dir"),
            "eq_dir": _lad.get("eq_dir"),
            "sector_rank": _alpha_row.get("sector_rank"),
            "sector_n": _alpha_row.get("sector_n"),
            "setup": (sc[1].get("setup") if sc else None),
        }
        # 2W washout and extension are China-native score/admission inputs. They
        # must be computed independently of residual-alpha coverage.
        try:
            _tf2w = _tf_state(close.resample("2W-FRI").last().dropna())
            _washout_2w = _tf2w.get("stoch_cross_up")
            _prophet_row["washout_2w"] = (
                _washout_2w if isinstance(_washout_2w, bool) else None
            )
        except Exception:  # noqa: BLE001 — absent context earns no points
            _prophet_row["washout_2w"] = None
        try:
            _prophet_row["extension"] = china_signals.extension_read(
                close, rec.get("tech"), ticker,
                turn_ratio=(liq_by.get(ticker) or {}).get("turn_ratio"),
            )
        except Exception:  # noqa: BLE001 — unknown extension cannot be featured
            _prophet_row["extension"] = None

        # QUALITY / TRADABILITY screen — keep ST / illiquid / stale garbage off
        # both the v2 board and the legacy laggards context.
        _last = close.last_valid_index()
        if (
            _panel_asof is not None
            and _last is not None
            and (_panel_asof - _last).days > STALE_DAYS
        ):
            screen_drop["stale"] += 1
        elif ticker not in _stock_universe_tickers:
            screen_drop["non_stock"] += 1
        elif _tradability_ok(ticker):
            prophet_cand.append(_prophet_row)
            if sc:
                cand.append((sc[0], copy.deepcopy(_prophet_row)))
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
                color=("var(--up)" if _dir == "up" else "var(--down)" if _dir == "down" else "var(--muted)"),
                **_spark_zone(rec.get("entry_signal")))}
        # W0.1 HOLD: attach to per-stock JSON before the deferred write (mirrors US L1477-1479)
        if _hold_state_cn.get(ticker):
            rec["hold"] = _hold_state_cn[ticker]
        safe = _safe(ticker)
        to_write.append((safe, rec))            # deferred: write after percentile scoring
        idx = _search_index_row(
            ticker, name, sector, rec["ladder"]["state"],
            name_en=name_en_by.get(ticker), name_zh=name_zh_by.get(ticker),
        )
        attach_latest_volume(idx, ticker, latest_volumes)
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

    # Cross-sectional China Prophet board.  The broad raw gate remains useful discovery
    # telemetry, but it is not synonymous with "buy now": the explicit v2 lanes below
    # separate confirmed execution-ready entries, live-but-not-featured setups, blocked/
    # late names, and legacy early warnings.  Alignment remains display context.
    setups = None
    align_map = {t: (p or {}).get("alignment") for t, p in profiles.items()}
    def _atier(t: str) -> str | None:
        a = align_map.get(t) or {}
        return "aligned" if a.get("aligned") else ("near" if a.get("near") else None)

    # COILED is one bounded bottom-quality component in Prophet v2.  The old fixed
    # +0.4/+0.5 bonuses could swamp a 0..1 base score and have been removed.
    coiled_by: dict[str, dict] = {}
    try:
        _coil_frac = coiled.cohort_fractions(_coil_d, _coil_sector)
        coiled_by = {
            t: coiled.assess(_coil_wash.get(t), _coil_frac.get(t), bool(_coil_div.get(t)))
            for t in sig_verdict
        }
        # Wave-4 COILED-FIRE is a display/ledger receipt with zero score
        # authority. Evaluate it only for COILED names that can enter one of the
        # four serialized raw-eligible lanes.
        _n_fire_scanned = _attach_eligible_coiled_fire(
            coiled_by,
            sig_verdict,
            _close_map,
        )
        log.info(
            "china COILED-FIRE: evaluated %d raw-eligible COILED names "
            "(ineligible universe skipped)",
            _n_fire_scanned,
        )
    except Exception as _e:  # noqa: BLE001 — additive; board degrades gracefully without bonus
        log.warning("china coiled bonus skipped (%s)", _e)
        coiled_by = {}

    _candidate_rows = dedupe_dual_class(prophet_cand)
    for _row in _candidate_rows:
        _cb = coiled_by.get(_row.get("ticker"))
        if _cb is not None:
            _row["coiled"] = _cb

    # Join the same-day A-share execution packet.  Missing or stale packets never
    # manufacture a veto, but they cannot qualify a name for the featured shelf.
    _micro_doc: dict = {}
    try:
        _micro_path = site / "chinastatedata" / "microstructure.json"
        if _micro_path.exists():
            _micro_doc = json.loads(_micro_path.read_text())
    except Exception as _micro_e:  # noqa: BLE001 — admission degrades to non-featured
        log.warning("china Prophet microstructure join unavailable (%s)", _micro_e)
    _micro_by = {
        str(_packet.get("ticker")): dict(_packet)
        for _packet in (_micro_doc.get("name_packets") or [])
        if isinstance(_packet, dict) and _packet.get("ticker")
    }
    # The board is a point-in-time decision on the actual name-price panel.
    # Alpha can lag or advance independently; it has zero admission authority.
    _board_asof = (
        str(pd.Timestamp(_panel_asof).date()) if _panel_asof is not None else None
    )
    _alpha_asof = str((alpha or {}).get("as_of") or "")[:10] or None
    if _alpha_asof and _board_asof and _alpha_asof != _board_asof:
        log.warning(
            "china Prophet as-of mismatch: alpha=%s panel=%s; board anchored to panel",
            _alpha_asof, _board_asof,
        )
    _raw_gate_tickers = {
        str(_row.get("ticker"))
        for _row in _candidate_rows
        if (sig_verdict.get(_row.get("ticker")) or {}).get("eligible")
    }
    _need_live_micro = {
        _ticker for _ticker in _raw_gate_tickers
        if _ticker not in _micro_by
        or str((_micro_by.get(_ticker) or {}).get("as_of") or "")[:10] != _board_asof
    }
    if _need_live_micro:
        try:
            from engine.china_microstructure import (  # noqa: PLC0415
                _load_st_set as _micro_st_set,
                name_packet as _name_packet,
            )
            _st_set_for_micro = _micro_st_set(config.data_dir())
            _raw_dir = config.data_dir() / "china_stocks_raw"
            _micro_rebuilt = 0
            for _ticker in sorted(_need_live_micro):
                _raw_ticker = _ticker.replace(".SH", ".SS")
                _raw_path = _raw_dir / f"{_raw_ticker}.parquet"
                if not _raw_path.exists():
                    _raw_path = _raw_dir / f"{_ticker}.parquet"
                if not _raw_path.exists():
                    continue
                try:
                    _raw_frame = pd.read_parquet(_raw_path)
                    if _raw_frame.empty:
                        continue
                    _packet = _name_packet(
                        ticker=_ticker,
                        df=_raw_frame,
                        st_set=_st_set_for_micro,
                    )
                    _packet["as_of"] = str(pd.Timestamp(_raw_frame.index.max()).date())
                    _micro_by[_ticker] = _packet
                    _micro_rebuilt += 1
                except Exception:  # noqa: BLE001 — one bad name stays non-featured
                    continue
            log.info(
                "china Prophet live microstructure: refreshed %d/%d raw-eligible packets",
                _micro_rebuilt, len(_need_live_micro),
            )
        except Exception as _micro_live_e:  # noqa: BLE001 — conservative non-featured fallback
            log.warning(
                "china Prophet live microstructure refresh unavailable (%s)",
                _micro_live_e,
            )
    _score_reversal_by = (
        reversal_context_by
        if _reversal_asof and _reversal_asof == _board_asof
        else {}
    )
    _score_rev_z_by = (
        rev_z_by
        if _reversal_asof and _reversal_asof == _board_asof
        else {}
    )
    if reversal_context_by and not _score_reversal_by:
        log.warning(
            "china Prophet reversal context rejected for as-of mismatch: "
            "reversal=%s board=%s",
            _reversal_asof,
            _board_asof,
        )
    _sector_turn_by_ticker: dict[str, dict] = {}
    for _row in _candidate_rows:
        _sw_match = _YAHOO_TO_SW.get(_row.get("sector") or "")
        if _sw_match and _sw_match in _sector_turn_by_sw:
            _sector_turn_by_ticker[str(_row.get("ticker"))] = _sector_turn_by_sw[_sw_match]

    # Prophet v2 score authority is intentionally small and transparent:
    # confluence 35 + entry 25 + runway 20 + bottom quality 10 + membership
    # in the validated broad reversal sleeve 10.  Residual alpha, narratives,
    # sector turns, quality and low-vol context are recorded but have zero score
    # authority until their own forward evidence earns promotion.
    _scored_candidates = china_board_rank.enrich_and_score_rows(
        _candidate_rows,
        verdict_by=sig_verdict,
        profile_by=profiles,
        entry_by=entry_sig,
        risk_by=risk_sig,
        rev_z_by=_score_rev_z_by,
        reversal_by=_score_reversal_by,
        micro_by=_micro_by,
        liquidity_by=liq_by,
        sector_turn_by=_sector_turn_by_ticker,
        # Each packet carries its own as-of.  Passing the board date here lets
        # _micro_is_fresh require both the batch and per-name dates to match.
        micro_asof=_micro_doc.get("as_of"),
        board_asof=_board_asof,
    )
    eligible_rows = [
        r for r in _scored_candidates if (r.get("signal") or {}).get("eligible")
    ]
    _n_ext = sum(1 for r in eligible_rows if (r.get("extension") or {}).get("extended"))
    _n_buyable = sum(1 for r in eligible_rows if signal_gate.is_buyable(r.get("signal")))
    _reversal_coverage = china_board_rank.reversal_coverage(
        _scored_candidates,
        _score_reversal_by,
        source_asof=_reversal_asof,
        board_asof=_board_asof,
    )
    log.info("china Prophet v2 screen: %d raw eligible / %d actionable T1-T3 of %d scored; "
             "%d extended; quality-screen dropped ST=%d mcap=%d adv=%d stale=%d",
             len(eligible_rows), _n_buyable, len(_scored_candidates), _n_ext,
             screen_drop["st"], screen_drop["mcap"], screen_drop["adv"], screen_drop["stale"])

    # ── W1-B: W-tier setup layer wiring ───────────────────────────────────────────
    # (1) Compute w_setup for the FULL closes-panel universe (>=200 bars).
    #     Reuse the already-loaded closes from `uni`; do NOT re-read per name.
    #     Profile: ~6ms/name × 1478 names ≈ 9s — well inside the 2-min budget.
    #     Best-effort: failures degrade to None (no stage for that name), never fatal.
    from engine.setup_tier import w_setup as _w_setup_fn, assign_stage as _assign_stage_fn
    from engine.setup_tier import STAGE_ENTRY, STAGE_RAN_LATE, STAGE_RIPENING
    from engine.setup_tier import assign_ripening_zone as _assign_ripening_zone_fn
    from engine.setup_tier import ZONE_FALLING, ZONE_READY, ZONE_BASING
    from engine.cycles import macd_parts as _macd_parts
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
    _tick("per-name detail loop + signal gates")
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
        _narr_asof = str(_narr_result.get("as_of") or "")[:10] or None
        _narr_tags: dict = (
            _narr_result.get("tags") or {}
            if (
                _narr_asof
                and _board_asof
                and _narr_asof <= _board_asof
            )
            else {}
        )
        if (_narr_result.get("tags") or {}) and not _narr_tags:
            log.warning(
                "W2-B narrative tags rejected for PIT mismatch: narrative=%s board=%s",
                _narr_asof, _board_asof,
            )
        log.info("W2-B narrative tags: %d tickers tagged (%d baskets, as_of %s)",
                 _narr_result.get("n_tagged", 0), _narr_result.get("n_baskets", 0),
                 _narr_result.get("as_of", "?"))
    except Exception as _narr_exc:  # noqa: BLE001 — additive, never fatal
        log.warning("W2-B narrative tags failed (%s) — board renders without narrative data",
                    _narr_exc)
        _narr_tags = {}
        _narr_asof = None
        _narr_ab_tier = lambda stage, tag: None  # noqa: E731 — degraded stub

    # Preserve every shadow/challenger input on the full scored universe before
    # partition_board_rows copies it into display lanes. These are context-only:
    # enrich_and_score_rows has already frozen the live score.
    for _ranked_row in _scored_candidates:
        _ranked_ticker = str(_ranked_row.get("ticker") or "")
        if quality_badge.get(_ranked_ticker):
            _ranked_row["quality"] = copy.deepcopy(
                quality_badge[_ranked_ticker]
            )
        _ranked_row.update({
            _key: _value
            for _key, _value in (disp_map.get(_ranked_ticker) or {}).items()
            if _value is not None
        })
        if _narr_tags.get(_ranked_ticker):
            _ranked_row["narrative"] = copy.deepcopy(
                _narr_tags[_ranked_ticker]
            )

    # (2) Derive last_cross_info for rule-3 (NOT gate-eligible, recent cross <=15 sessions).
    #     Source: sig_verdict["last"] gives the last buy marker date; we compute sessions_since
    #     and pct_since from the close series in `uni`. Only compute for ineligible names.
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
        """Compact receipt of the actual Prophet v2 score — display only."""
        prophet = r.get("prophet") or {}
        points = prophet.get("points") or {}
        if not points:
            return ""
        labels = (
            ("signal", "signal"),
            ("entry", "entry"),
            ("runway", "runway"),
            ("bottom_quality", "bottom"),
            ("reversal_member", "reversal"),
        )
        receipt = [
            f"{label} {float(points.get(key) or 0):.1f}"
            for key, label in labels
        ]
        return f"Prophet {float(prophet.get('score') or 0):.1f}: " + " + ".join(receipt)

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
        # MACD D/2D/3D column feed (display-tier, no rank/stage change): the cascade's
        # 2D/3D RSI-MACD histograms off the gate verdict (sign → ▲/▼ glyph) + the daily
        # price-MACD hist last value (same construction as the ripening rows below).
        r["macd_d2"] = _sv.get("hist_d2")
        r["macd_d3"] = _sv.get("hist_d3")
        try:
            _c_b = _close_map.get(_t)
            _c_b = _c_b.dropna() if _c_b is not None else None
            if _c_b is not None and len(_c_b) >= 35:
                _mh_b = _macd_parts(_c_b)["hist"].dropna()
                if len(_mh_b):
                    r["macd_hist_d"] = round(float(_mh_b.iloc[-1]), 4)
        except Exception:  # noqa: BLE001 — display-only, never fatal
            pass

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
        # MACD D/2D/3D column feed (display-tier; only computed for rows that pass the
        # RAN filters above, so the _macd_parts cost stays on the small shelf set).
        _ran_macd_d: float | None = None
        try:
            _c_r = _close_w.dropna() if _close_w is not None else None
            if _c_r is not None and len(_c_r) >= 35:
                _mh_r = _macd_parts(_c_r)["hist"].dropna()
                if len(_mh_r):
                    _ran_macd_d = round(float(_mh_r.iloc[-1]), 4)
        except Exception:  # noqa: BLE001 — display-only, never fatal
            pass
        _ran_rows.append({
            "ticker": _t, "name": _name_w or _t, "sector": _sector_w or "",
            "cross_date": _lci["cross_date"],
            "sessions_since": _lci["sessions_since"],
            "pct_since": _lci.get("pct_since"),
            "macd_hist_d": _ran_macd_d,
            "macd_d2": _sv.get("hist_d2"),
            "macd_d3": _sv.get("hist_d3"),
            "sublabel": _stage_r.get("sublabel"),
            "basing_chip": (_stage_r.get("detail") or {}).get("basing_chip"),
            "launched_chip": (_stage_r.get("detail") or {}).get("launched_chip"),
            "hold_summary": _hold_summary,
        })
    _ran_rows.sort(key=lambda x: x.get("sessions_since") or 99)
    _ran_rows = _ran_rows[:15]

    # (5) Build the RIPENING arrays (W8-R1 three-zone lifecycle):
    #     - _ripening_rows   : READY + BASING (quota: READY up to 16, BASING fills to cap 32)
    #     - _ripening_falling: FALLING (cap 8, sorted ret_5d ascending — worst first)
    #
    #     Zone assignment: HARD precedence cascade per W8-R1.
    #     ORDERING LAW (Article-2 framing): within each zone, PRIMARY key = macd_bars_to_cross
    #     ascending (None→999); tiebreak = w1 cross bars_since asc (None→99); then stoch_2w asc.
    #     Zones are display grouping only — no ordering/attention authority.
    #
    #     Every row now carries: zone, evidence chips, ret_5d, macd_hist_d, macd_hist_slope sign,
    #     stoch_2w + reclaim arrow (+1/0/-1), days_in_washout, price, spark_svg.
    #
    #     W8-R1 constants (v1 frozen descriptively — amendment-logged, recalibrated at W6):
    #       - FALLING: ret_5d <= -8% OR (daily MACD hist < 0 AND falling)
    #       - READY:   fresh 1W cross (<=3 bars) AND hist>=0; OR hist>0 AND rising; OR 2W MACD <=10 AND hist>=0
    #       - BASING:  else
    #
    #     R3-minor bug fix: arrays are now built from `uni` (entire close universe) and
    #     attached to setups/wide unconditionally within the cand block (the arrays are
    #     always computed — the empty-cand case is a separate non-template fallback path).
    _t0_rip = time.time()
    _ripening_all: list[dict] = []    # all candidate rows before zone split
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
        _w1x = _ws.get("w1_cross") or {}

        # ── Per-name inputs for zone assignment ────────────────────────────────
        # 5d return (decimal): use the close series already in scope
        _ret5d: float | None = None
        _macd_hist_last: float | None = None
        _macd_hist_prev: float | None = None
        _price: float | None = None
        _spark_svg_rip: str = ""
        _days_in_washout: int | None = None
        try:
            _cv = _close_w.dropna() if _close_w is not None else None
            if _cv is not None and len(_cv) >= 6:
                _price = round(float(_cv.iloc[-1]), 3)
                _ret5d = round(float(_cv.iloc[-1] / _cv.iloc[-6] - 1.0), 4)
                # Daily MACD(12,26,9) last two hist values
                if len(_cv) >= 35:
                    _mdf = _macd_parts(_cv)
                    _mhist = _mdf["hist"].dropna()
                    if len(_mhist) >= 2:
                        _macd_hist_last = round(float(_mhist.iloc[-1]), 4)
                        _macd_hist_prev = round(float(_mhist.iloc[-2]), 4)
                # Spark SVG for the ripening card (same helper as buy rows)
                _spark_col = ("var(--up)" if _macd_hist_last is not None and _macd_hist_last >= 0
                              else "var(--down)" if _macd_hist_last is not None and _macd_hist_last < 0
                              else "var(--muted)")
                _spark_svg_rip = _spark_svg(list(_cv.tail(32).values), color=_spark_col)
                # Days in washout: sessions since 2W stoch entered <=35 in the current spell
                if _stoch is not None and _stoch <= 35:
                    _cv_tail = _cv.tail(80)
                    _cv2w = _cv_tail.resample("2W-FRI").last().dropna()
                    # count sessions in this continuous washout spell from the daily close
                    # (simple: count tail sessions while stoch would stay <=35 — use 2W stoch
                    # continuity proxy: count sessions from most recent washout entry)
                    # Approximate: look at recent 40 daily bars to find the entry session
                    try:
                        # compute rolling 14-period StochRSI on daily to find washout entry
                        from engine.confluence_tiers import _stoch_rsi_kd as _srsi_fn
                        _k14, _d14 = _srsi_fn(_cv.tail(60))
                        _in_wash = (_k14 <= 35)
                        _in_wash_vals = _in_wash.values.tolist()
                        _diw = 0
                        for _v in reversed(_in_wash_vals):
                            if _v:
                                _diw += 1
                            else:
                                break
                        _days_in_washout = _diw if _diw > 0 else None
                    except Exception:
                        _days_in_washout = None
        except Exception:
            pass

        # ── Reclaim arrow for 2W stoch ─────────────────────────────────────────
        # +1 = stoch_cross_up (reclaiming from <20), 0 = flat, -1 = declining
        _stoch_prev = None
        try:
            if _cv is not None and len(_cv) >= 4:
                _cv2w_all = _cv.resample("2W-FRI").last().dropna()
                if len(_cv2w_all) >= 2:
                    _tfs_prev = _tf_state(_cv2w_all.iloc[:-1])
                    _stoch_prev = _tfs_prev.get("stoch") if _tfs_prev else None
        except Exception:
            _stoch_prev = None
        _stoch_arrow: int
        if _w2.get("stoch_cross_up"):
            _stoch_arrow = 1
        elif _stoch_prev is not None and _stoch is not None and _stoch > _stoch_prev:
            _stoch_arrow = 1
        elif _stoch_prev is not None and _stoch is not None and _stoch < _stoch_prev:
            _stoch_arrow = -1
        else:
            _stoch_arrow = 0

        # ── Zone assignment (W8-R1 hard precedence) ────────────────────────────
        _zone_result = _assign_ripening_zone_fn(
            ret_5d=_ret5d,
            macd_hist_d=_macd_hist_last,
            macd_hist_prev_d=_macd_hist_prev,
            w1_cross_bars_since=_w1x.get("bars_since"),
            w1_from_washout=bool(_w1x.get("from_washout")),
            macd_bars_to_cross_2w=_btc,
            stoch_2w=_stoch,
            stoch_2w_prev=_stoch_prev,
        )
        _zone = _zone_result["zone"]
        _zone_evidence = _zone_result["evidence"]
        _zone_evidence_display = _zone_result.get("evidence_display") or []

        # ── Build the row ──────────────────────────────────────────────────────
        # Article-2 ORDERING keys (within zone): macd_bars_to_cross asc (None→999),
        # then w1 cross bars_since asc (None→99), then stoch_2w asc.
        _sort_btc = float(_btc) if _btc is not None else 999.0
        _sort_bars = float(_w1x.get("bars_since")) if _w1x.get("bars_since") is not None else 99.0
        _sort_stoch = float(_stoch) if _stoch is not None else 999.0

        _ripening_all.append({
            "ticker": _t,
            "name": _name_w or _t,
            "sector": _sector_w or "",
            "zone": _zone,
            "evidence": _zone_evidence,
            "evidence_display": _zone_evidence_display,
            "reasons": _ws.get("setup_reasons") or [],
            "imminence": _btc,
            "w2_stoch": _stoch,
            "w2_stoch_arrow": _stoch_arrow,    # +1/0/-1 reclaim arrow
            "w2_macd_approaching": bool(_w2.get("macd_approaching_up")),
            "w2_macd_cross_up": bool(_w2.get("macd_cross_up")),
            "w1_cross_date": _w1x.get("cross_date"),
            "w1_cross_bars_since": _w1x.get("bars_since"),
            "w1_d_at_cross": _w1x.get("d_at_cross"),
            "w1_from_washout": bool(_w1x.get("from_washout")),
            "spot_pct_in_range": (_ws.get("base") or {}).get("spot_pct_in_range"),
            "ret_5d": _ret5d,
            "macd_hist_d": _macd_hist_last,
            # 2D/3D RSI-MACD histogram off the gate verdict (display-tier glyph feed;
            # _sv may be None for names outside the verdict map → slots render ·).
            "macd_d2": (_sv or {}).get("hist_d2"),
            "macd_d3": (_sv or {}).get("hist_d3"),
            "macd_hist_slope": (
                1 if (_macd_hist_last is not None and _macd_hist_prev is not None
                      and _macd_hist_last > _macd_hist_prev)
                else -1 if (_macd_hist_last is not None and _macd_hist_prev is not None
                            and _macd_hist_last < _macd_hist_prev)
                else 0
            ),
            "days_in_washout": _days_in_washout,
            "price": _price,
            "spark_svg": _spark_svg_rip,
            "_sort_btc": _sort_btc,
            "_sort_bars": _sort_bars,
            "_sort_stoch": _sort_stoch,
        })

    # ── Zone split + ordering ──────────────────────────────────────────────────
    # Article-2 ordering within each zone: btc asc, then bars_since asc, then stoch asc
    _all_sorted = sorted(
        _ripening_all,
        key=lambda x: (x["_sort_btc"], x["_sort_bars"], x["_sort_stoch"])
    )

    # FALLING sink: sorted by ret_5d ascending (worst drawdown first), cap 8
    _ripening_falling: list[dict] = [r for r in _all_sorted if r["zone"] == ZONE_FALLING]
    _ripening_falling.sort(
        key=lambda x: float(x["ret_5d"]) if x.get("ret_5d") is not None else -999.0
    )
    _ripening_falling = _ripening_falling[:8]

    # READY + BASING: quota (READY up to 16, BASING fills remainder to cap 32)
    _ready_rows = [r for r in _all_sorted if r["zone"] == ZONE_READY]
    _basing_rows = [r for r in _all_sorted if r["zone"] == ZONE_BASING]
    _ready_capped = _ready_rows[:16]
    _basing_capped = _basing_rows[:(32 - len(_ready_capped))]
    _ripening_rows = _ready_capped + _basing_capped

    # Strip internal sort keys before serialisation
    for _rr in _ripening_rows + _ripening_falling:
        _rr.pop("_sort_btc", None)
        _rr.pop("_sort_bars", None)
        _rr.pop("_sort_stoch", None)

    _t1_rip = time.time()
    log.info("W8-R1 ripening zone loop: %.1fs over %d candidates → %d READY + %d BASING + %d FALLING",
             _t1_rip - _t0_rip, len(_ripening_all),
             len(_ready_capped), len(_basing_capped), len(_ripening_falling))

    # W2-B: attach narrative tags to RIPENING rows (display/ledger only — no rank change).
    # Stage is implicitly RIPENING for all rows in these arrays.
    for _rr in _ripening_rows + _ripening_falling:
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
    # W8-R1: updated caps (READY+BASING cap 32, FALLING sink cap 8)
    assert len(_ripening_rows) <= 32, (
        f"W8-R1 invariant FAILED: ripening (READY+BASING) cap 32 exceeded ({len(_ripening_rows)})")
    assert len(_ripening_falling) <= 8, (
        f"W8-R1 invariant FAILED: ripening FALLING sink cap 8 exceeded ({len(_ripening_falling)})")
    assert len(_ran_rows) <= 15, (
        f"W1-B invariant FAILED: ran cap 15 exceeded ({len(_ran_rows)})")
    _n_entry = sum(1 for r in eligible_rows if r.get("stage") == STAGE_ENTRY)
    _n_ran_late = sum(1 for r in eligible_rows if r.get("stage") == STAGE_RAN_LATE)
    log.info("W8-R1 zone partition: %d READY + %d BASING (ripening rows) + %d FALLING + %d RAN",
             len(_ready_capped), len(_basing_capped), len(_ripening_falling), len(_ran_rows))
    log.info("W1-B stage partition: %d ENTRY + %d RAN_LATE + %d no-shelf (buy rows); "
             "%d RIPENING + %d FALLING + %d RAN (non-buy universe)",
             _n_entry, _n_ran_late, len(eligible_rows) - _n_entry - _n_ran_late,
             len(_ripening_rows), len(_ripening_falling), len(_ran_rows))

    if _scored_candidates:
        as_of = _board_asof
        _execution_coverage = china_board_rank.execution_coverage(
            _scored_candidates
        )
        _board_lanes = china_board_rank.partition_board_rows(eligible_rows)
        _buy_rows = _board_lanes["featured"]
        _more_rows = _board_lanes["more_actionable"]
        _late_rows = _board_lanes["late_or_unfillable"]
        _forming_rows = _board_lanes["forming"]
        _watch_rows = list(_more_rows) + list(_late_rows) + list(_forming_rows)
        assert sum(_board_lanes["counts"].values()) == len(eligible_rows), (
            "China Prophet v2 invariant FAILED: lane partition lost or duplicated "
            f"raw-eligible rows ({_board_lanes['counts']} vs {len(eligible_rows)})."
        )
        assert all(signal_gate.is_buyable(r.get("signal")) for r in _buy_rows), (
            "China Prophet v2 invariant FAILED: featured shelf contains a non-T1-T3 row."
        )

        # laggards watch-strip: weakest residual-alpha names, independent of the buy gate.
        laggards = dedupe_dual_class(sorted(
            (r for _s, r in cand if r.get("alpha") is not None),
            key=lambda r: r["alpha"]))[:12]
        _ranking_contract = _prophet_ranking_contract()
        _ranking_contract["input_coverage"] = {
            "reversal": _reversal_coverage,
        }
        wide = {
            "schema_version": "2.0.0",
            "as_of": as_of,
            "rank_by": china_board_rank.BOARD_DEFINITION,
            "board_definition": china_board_rank.BOARD_DEFINITION,
            "ranking": _ranking_contract,
            "buy": _buy_rows,
            "more_actionable": _more_rows,
            "late_or_unfillable": _late_rows,
            "forming": _forming_rows,
            # Compatibility union for older consumers. New UI and contracts use
            # the three explicit depth lanes above.
            "watch": _watch_rows,
            "lane_counts": dict(_board_lanes["counts"]),
            "execution_coverage": _execution_coverage,
            "laggards": laggards,
        }
        # Required top-level contract keys get conservative defaults before any
        # fail-soft telemetry/enrichment work.
        wide["coverage"] = {
            "as_of": as_of,
            "data_through": _data_through(),
            "panel_collected_utc": None,
            "panel_collected_hour_utc": None,
            "partial_session": None,
            "session_note": "session coverage unavailable",
            "lane": os.environ.get("CN_LANE", "asia"),
        }
        wide["track_ledger"] = None
        wide["sleeve_chip"] = {}
        # The renderer and both JSON artifacts now share one lossless object; later
        # enrichments cannot drift between the live page and the machine contract.
        setups = wide
        log.info(
            "CN Prophet v2 lanes: %d raw eligible → %d featured + %d more + "
            "%d late/unfillable + %d forming — nothing dropped",
            len(eligible_rows), len(_buy_rows), len(_more_rows),
            len(_late_rows), len(_forming_rows),
        )
        _board_rows = _buy_rows + _more_rows + _late_rows + _forming_rows
        for r in _board_rows + wide["laggards"]:
            t = r.get("ticker")
            r["conviction"] = profiles.get(t)
            if not r.get("lane"):
                # Laggards are not in the Prophet contract and may retain the
                # richer display verdict. Board rows keep buy_signal(): slim,
                # strict-JSON-safe, and exactly what admission consumed.
                r["signal"] = signal_gate.compact(sig_verdict.get(t))
            else:
                r["align_tier"] = _atier(t)
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
            # DISPLAY/LEDGER ONLY — never changes Prophet v2 score or admission.
            # approx:true is propagated from the taxonomy map (Yahoo GICS ≠ Shenwan L1 exactly).
            _row_sector = r.get("sector") or ""
            _sw_match = _YAHOO_TO_SW.get(_row_sector)
            if _sw_match and _sw_match in _sector_turn_by_sw:
                r["sector_turn"] = _sector_turn_by_sw[_sw_match]
            # W2-B NARRATIVE TAGS: attach per-name theme heat + radar join + A/B tier.
            # DISPLAY/LEDGER ONLY — narrative NEVER affects Prophet v2 score or admission.
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
                    "asof":     _narr_asof,
                }
            _nb_stage = r.get("stage")
            r["ab_tier"] = _narr_ab_tier(_nb_stage, _nb_tag)
        # W2-B order-invariance assertion: buy order must be unchanged by narrative tagging.
        # Narrative is display/ledger only — it must never alter the ranked order.
        _buy_tickers_pre  = [r.get("ticker") for r in _buy_rows]
        _buy_tickers_post = [r.get("ticker") for r in wide["buy"]]
        assert _buy_tickers_pre == _buy_tickers_post, (
            "W2-B invariant FAILED: narrative tags altered the buy row order. "
            f"Pre: {_buy_tickers_pre[:5]} ... Post: {_buy_tickers_post[:5]}")
        wide["eligible"] = len(eligible_rows)
        wide["actionable"] = _n_buyable
        wide["universe"] = len(_scored_candidates)
        wide["quality_screen"] = {           # honest report of what the screen actually did
            "adv_floor_yi": china_liquidity.ADV_FLOOR_YI, "mcap_floor_yi": MCAP_FLOOR_YI,
            "dropped": dict(screen_drop), "n_extended_demoted": _n_ext,
            "note": ("ST/*ST/退 excluded; suspended/delisted (stale >15d) excluded; names below the "
                     "dollar-ADV tradability floor excluded (only when provably illiquid); already-"
                     "extended names are routed to the do-not-chase lane, not hidden. Market-cap is "
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
            # Full-universe, point-in-time feature/admission log for honest
            # incumbent/challenger research. It has no live score authority and
            # is write-gated to a settled Asia collection session.
            try:
                from engine import china_prophet_shadow as _cn_shadow  # noqa: PLC0415

                _shadow_n = _cn_shadow.append_candidates(
                    _scored_candidates,
                    as_of,
                    lane=_lane,
                    board_lanes=_board_lanes,
                )
                log.info("china Prophet shadow ledger: %d total candidate rows", _shadow_n)
            except Exception as _shadow_e:  # noqa: BLE001 — research log never suppresses board
                log.warning("china Prophet shadow ledger failed (%s)", _shadow_e)
            # SA-W2 F1 FIX: append today's CN regime row BEFORE append_board so that
            # append_board's get_regime_for_date(today) call finds the row.  The regime
            # store is keep-first, so calling append first is the only way the SAME-DAY
            # board row carries a non-null own_market_regime.  Depends on
            # regime_history.parquet already being written by china_run.py earlier in
            # this lane — that dependency is unchanged.
            try:
                from engine import china_regime_store as _cn_rs  # noqa: PLC0415
                _rstore_ok = _cn_rs.append(asof=str(as_of))
                log.info("[timing] cn_regime_store.append (%s)", "OK" if _rstore_ok else "skip/fail")
            except Exception as _rs_e:  # noqa: BLE001 — SA-R16: never suppress grade()
                log.warning("china_regime_store.append failed (%s) — board track continues", _rs_e)
            _bn = china_standout_track.append_board(wide["buy"], asof=as_of, lane=_lane)
            _bt = china_standout_track.grade()
            # Detach the tuple-keyed F7 map BEFORE _bt reaches wide/setups — it must
            # never ride into the JSON artifact (see _detach_board_track_plumbing).
            _bt, _fwd_map = _detach_board_track_plumbing(_bt)
            if (
                _bt.get("available")
                and _bt.get("board_definition") == wide["board_definition"]
            ):
                # Interim (unrealized) mark-to-latest-close read — shown while the forward ledger
                # is still pre-maturity so the panel isn't a black box until ~07-29. Labeled
                # INTERIM in the template; graduates to the 21d grade once maturities land.
                try:
                    _bt["interim"] = china_standout_track.interim_grade()
                except Exception as _ie:  # noqa: BLE001 — telemetry, never fatal
                    log.warning("china interim board-track read failed (%s)", _ie)
                wide["board_track"] = _bt
                setups["board_track"] = _bt
            elif _bt.get("available"):
                log.info(
                    "china board-track withheld: ledger definition %s != current %s",
                    _bt.get("board_definition"), wide["board_definition"],
                )
            setups["coverage"] = wide["coverage"]
            # TRD popup — EPISODE ledger (track_ledger/v1). Additive, never
            # fatal: reuses the board.parquet + closes the panel just read. Emitted even
            # when _bt is unavailable (accruing state) so the popup always has a feed.
            try:
                _cnok = emit_cn_track_ledger(
                    site,
                    _bt,
                    wide.get("buy"),
                    board_definition=wide["board_definition"],
                    asof=as_of,
                )
                # Hand the ledger's own summary to the template so the chip and the
                # popup table it heads report the SAME numbers. Before 2026-07-26 the
                # chip read setups.board_track (the 21d research grade) while the table
                # fetched this ledger — two methodologies, one component.
                setups["track_ledger"] = (
                    _CN_LAST_LEDGER.get("doc") if _cnok else None
                )
                log.info("cn track_ledger: %s", "wrote cn_track_ledger.json" if _cnok else "write skipped")
            except Exception as _cnle:  # noqa: BLE001 — ledger is additive; never fatal
                log.warning("cn track_ledger emit failed (%s) — render continues", _cnle)
            log.info("china standout board-track: logged top-%d (ledger=%d, graded=%s, lane=%s, partial=%s)",
                     min(60, len(wide["buy"])), _bn, _bt.get("n_graded"), _lane,
                     wide["coverage"]["partial_session"])
            # SA-W2: CN two-axis attribution + fitness card (fail-closed: asia lane only; SA-R16).
            # Reads the committed board.parquet + bench close; never raises; never suppresses grade().
            # F7: pass fwd_excess_map_21d from grade() to avoid re-opening per-ticker price stores.
            # [timing] tick after this block measures runtime impact on the asia lane.
            try:
                from engine import china_standout_audit as _cn_audit  # noqa: PLC0415
                from engine.china_standout_track import _bench_close as _cn_bench  # noqa: PLC0415,SLF001
                _bench = _cn_bench()
                # F7: thread the pre-computed map (grade() already opened these stores);
                # _fwd_map was detached from _bt right after grade() above.
                _audit_result = _cn_audit.run_attribution(
                    bench_close=_bench,
                    lane=_lane,
                    fwd_excess_map=_fwd_map,
                    board_definition=wide["board_definition"],
                )
                log.info("china standout attribution: %s", _audit_result)
            except Exception as _audit_e:  # noqa: BLE001 — SA-R16: attribution never fatal
                log.warning("china standout attribution failed (%s) — grade output unaffected", _audit_e)
        except Exception as e:  # noqa: BLE001 — telemetry, never fatal
            log.warning("china standout board-track failed (%s)", e)
        _tick("standout board-track + SA-W2 attribution")
        # Validated sleeve-size chip (W6-CN Fix 1) — thread the risk_radar_intl gross_factor
        # into the board header as a DISPLAY chip. Regime sizes sleeves, never vetoes names.
        # Passport: basis=measured, validation=cn_forward_log.jsonl (the repo's only closed loop).
        try:
            from engine.risk_radar_intl import cn_sleeve_chip
            wide["sleeve_chip"] = cn_sleeve_chip()
            setups["sleeve_chip"] = wide["sleeve_chip"]  # mirror onto rendered object (mirrors board_track/coverage pattern at L1823-1824)
            log.info("china stocks sleeve chip: %s", wide["sleeve_chip"].get("label_en"))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("china stocks sleeve chip failed (%s)", e)
        # W0.7 BOARD-WIDTH GUARD: read the previous artifact's buy-count; if the new count dropped
        # >40% day-over-day, stamp data_outage and log a WARNING — never publish a silently collapsed
        # board as if it were a normal render (git history shows n=110→42→11→110 across 06-25..06-30).
        # The banner is rendered by the template when data_outage.flag is true.
        _standouts_path = site / "factordata" / "china_standouts.json"
        _prev_buy_n: int | None = None
        _prev_definition: str | None = None
        _prev_execution_coverage: dict = {}
        try:
            if _standouts_path.exists():
                _prev = json.loads(_standouts_path.read_text())
                _prev_buy_n = len(_prev.get("buy") or [])
                _prev_definition = _prev.get("board_definition") or "legacy"
                _prev_execution_coverage = (
                    _prev.get("execution_coverage")
                    if isinstance(_prev.get("execution_coverage"), dict)
                    else {}
                )
        except Exception:  # noqa: BLE001 — guard must never block the write
            pass
        _new_buy_n = len(wide["buy"])
        _collapsed: dict[str, dict] = {}
        if (
            _prev_buy_n is not None
            and _prev_buy_n > 0
            and _prev_definition == wide["board_definition"]
        ):
            _coverage_pairs = {
                "featured": (_prev_buy_n, _new_buy_n),
                "raw_eligible": (
                    _prev_execution_coverage.get(
                        "raw_eligible", _prev.get("eligible")
                    ),
                    wide["execution_coverage"]["raw_eligible"],
                ),
                "actionable_t1_t3": (
                    _prev_execution_coverage.get(
                        "actionable_t1_t3", _prev.get("actionable")
                    ),
                    wide["execution_coverage"]["actionable_t1_t3"],
                ),
            }
            for _metric, (_old, _new) in _coverage_pairs.items():
                try:
                    _old_i, _new_i = int(_old), int(_new)
                except (TypeError, ValueError):
                    continue
                if _old_i <= 0:
                    continue
                _metric_drop = (_old_i - _new_i) / _old_i
                if _metric_drop > 0.40:
                    _collapsed[_metric] = {
                        "previous": _old_i,
                        "current": _new_i,
                        "drop_pct": round(_metric_drop * 100, 1),
                    }

            _micro_rate = float(
                wide["execution_coverage"]["fresh_same_day_micro_rate_pct"]
            )
            _actionable_n = int(
                wide["execution_coverage"]["actionable_t1_t3"]
            )
            _micro_incomplete = _actionable_n >= 5 and _micro_rate < 80.0
            if _collapsed or _micro_incomplete:
                _reason_parts = [
                    (
                        f"{_metric} {_vals['previous']}→{_vals['current']} "
                        f"({_vals['drop_pct']:.0f}% drop)"
                    )
                    for _metric, _vals in _collapsed.items()
                ]
                _metric_zh = {
                    "featured": "精选标的",
                    "raw_eligible": "原始合格标的",
                    "actionable_t1_t3": "可操作T1–T3标的",
                }
                _reason_parts_zh = [
                    (
                        f"{_metric_zh.get(_metric, _metric)} "
                        f"{_vals['previous']}→{_vals['current']} "
                        f"（下降{_vals['drop_pct']:.0f}%）"
                    )
                    for _metric, _vals in _collapsed.items()
                ]
                if _micro_incomplete:
                    _reason_parts.append(
                        f"same-day microstructure coverage {_micro_rate:.1f}% (<80%)"
                    )
                    _reason_parts_zh.append(
                        f"当日微观结构覆盖率{_micro_rate:.1f}%（低于80%）"
                    )
                wide["data_outage"] = {
                    "flag": True,
                    "metrics": _collapsed,
                    "micro_rate_pct": _micro_rate,
                    "reason": (
                        "; ".join(_reason_parts)
                        + ". Probable data/collector coverage gap. "
                        "The featured shelf is incomplete — treat with caution."
                    ),
                    "reason_zh": (
                        "；".join(_reason_parts_zh)
                        + "。可能存在数据或采集覆盖缺口，精选区并不完整，请谨慎参考。"
                    ),
                }
                log.warning(
                    "W0.7 Prophet coverage guard: %s — stamping data_outage",
                    "; ".join(_reason_parts),
                )
        elif _prev_buy_n is not None and _prev_definition != wide["board_definition"]:
            wide["definition_change"] = {
                "from": _prev_definition,
                "to": wide["board_definition"],
                "previous_featured_n": _prev_buy_n,
                "note": "Board-width comparison reset because the admission definition changed.",
            }
            log.info(
                "W0.7 board-width guard reset for definition change %s → %s",
                _prev_definition, wide["board_definition"],
            )
        # Input-health checks apply even on the first v2 run, when the prior
        # artifact has a different definition and width comparisons reset.
        _actionable_n = int(
            wide["execution_coverage"]["actionable_t1_t3"]
        )
        _micro_rate = float(
            wide["execution_coverage"]["fresh_same_day_micro_rate_pct"]
        )
        _signal_rate = float(
            wide["execution_coverage"]["fresh_same_day_signal_rate_pct"]
        )
        _micro_incomplete = _actionable_n >= 5 and _micro_rate < 80.0
        _signal_incomplete = _actionable_n >= 5 and _signal_rate < 80.0
        _reversal_incomplete = bool(_reversal_coverage["degraded"])
        if (
            _collapsed
            or _micro_incomplete
            or _signal_incomplete
            or _reversal_incomplete
        ):
            _reason_parts = [
                (
                    f"{_metric} {_vals['previous']}→{_vals['current']} "
                    f"({_vals['drop_pct']:.0f}% drop)"
                )
                for _metric, _vals in _collapsed.items()
            ]
            _metric_zh = {
                "featured": "精选标的",
                "raw_eligible": "原始合格标的",
                "actionable_t1_t3": "可操作T1–T3标的",
            }
            _reason_parts_zh = [
                (
                    f"{_metric_zh.get(_metric, _metric)} "
                    f"{_vals['previous']}→{_vals['current']} "
                    f"（下降{_vals['drop_pct']:.0f}%）"
                )
                for _metric, _vals in _collapsed.items()
            ]
            if _micro_incomplete:
                _reason_parts.append(
                    f"same-day microstructure coverage {_micro_rate:.1f}% (<80%)"
                )
                _reason_parts_zh.append(
                    f"当日微观结构覆盖率{_micro_rate:.1f}%（低于80%）"
                )
            if _signal_incomplete:
                _reason_parts.append(
                    f"same-day signal coverage {_signal_rate:.1f}% (<80%)"
                )
                _reason_parts_zh.append(
                    f"当日信号覆盖率{_signal_rate:.1f}%（低于80%）"
                )
            if _reversal_incomplete:
                _rev_rate = float(
                    _reversal_coverage["actionable_coverage_rate_pct"]
                )
                _reason_parts.append(
                    "same-day reversal input unavailable or incomplete "
                    f"({_rev_rate:.1f}% actionable coverage)"
                )
                _reason_parts_zh.append(
                    f"当日反转输入缺失或不完整（可操作标的覆盖率{_rev_rate:.1f}%）"
                )
            wide["data_outage"] = {
                "flag": True,
                "metrics": {
                    **_collapsed,
                    "reversal": _reversal_coverage,
                },
                "micro_rate_pct": _micro_rate,
                "signal_rate_pct": _signal_rate,
                "reason": (
                    "; ".join(_reason_parts)
                    + ". Probable data/collector coverage gap. "
                    "The featured shelf is incomplete — treat with caution."
                ),
                "reason_zh": (
                    "；".join(_reason_parts_zh)
                    + "。可能存在数据或采集覆盖缺口，精选区并不完整，请谨慎参考。"
                ),
            }
            log.warning(
                "W0.7 Prophet input guard: %s — stamping data_outage",
                "; ".join(_reason_parts),
            )
        # ── W8-E: table-view enrichment ───────────────────────────────────────
        # (a) NULL-SAFE real-mcap join: overlay Tushare total_mv_yi onto rows that
        #     currently carry the placeholder-30.0 sentinel or are missing a cap.
        #     cap_bucket: large>=500 / mid 100-500 / small<100 / null (unknown).
        # (b) days_since_signal: days since first appearance in board.parquet.
        #     Null-safe: if the store is absent the field is None ("—" in template).
        # DISPLAY ONLY — no ordering change; no rank effect.
        _MCAP_PLACEHOLDER = 30.0
        _w8e_cap_bucket_log: dict[str, int] = {"large": 0, "mid": 0, "small": 0, "unknown": 0}

        # Build a final real-cap lookup: prefer Tushare total_mv_yi (already in mktcap_by
        # with placeholder-dropped names filled) — the variable is already populated above.
        # For rows still at placeholder 30.0 sentinel, set mcap=None.
        def _w8e_mcap(ticker: str) -> float | None:
            v = mktcap_by.get(str(ticker))
            if v is None:
                return None
            try:
                fv = float(v)
                return None if fv == _MCAP_PLACEHOLDER else fv
            except (ValueError, TypeError):
                return None

        def _w8e_cap_bucket(mcap: float | None) -> str | None:
            if mcap is None:
                return None
            if mcap >= 500:
                return "large"
            if mcap >= 100:
                return "mid"
            return "small"

        # days_since_signal from board.parquet first-appearance date per ticker.
        _w8e_first_seen: dict[str, str] = {}
        try:
            _brd_path = config.data_dir() / "china_standout_track" / "board.parquet"
            if _brd_path.exists():
                _brd_df = pd.read_parquet(_brd_path)
                if "board_definition" in _brd_df.columns:
                    _brd_df = _brd_df[
                        _brd_df["board_definition"].astype(str)
                        == wide["board_definition"]
                    ]
                _w8e_first_seen = (
                    _brd_df.groupby("ticker")["date"].min()
                    .apply(str).to_dict()
                )
                log.info("W8-E days_since_signal: %d tickers in board ledger (range %s → %s)",
                         len(_w8e_first_seen),
                         min(_w8e_first_seen.values()) if _w8e_first_seen else "?",
                         max(_w8e_first_seen.values()) if _w8e_first_seen else "?")
        except Exception as _w8e_e:  # noqa: BLE001 — additive, never fatal
            log.warning("W8-E days_since_signal: board ledger unavailable (%s)", _w8e_e)

        _w8e_today_str = str(as_of) if as_of else None

        def _w8e_days_since(ticker: str) -> int | None:
            fs = _w8e_first_seen.get(str(ticker))
            if not fs or not _w8e_today_str:
                return None
            try:
                d0 = pd.Timestamp(fs).date()
                d1 = pd.Timestamp(_w8e_today_str).date()
                return max(0, (d1 - d0).days)
            except Exception:
                return None

        # Enrich all arrays: buy, watch (board-cap overflow), ran, ripening, ripening_falling
        _w8e_all_arrays = (
            list(wide["buy"]) +
            list(wide.get("watch") or []) +
            list(_ran_rows) +
            list(_ripening_rows) +
            list(_ripening_falling)
        )
        for _w8e_r in _w8e_all_arrays:
            _tk = _w8e_r.get("ticker")
            _mcap = _w8e_mcap(_tk) if _tk else None
            _w8e_r["mcap"] = _mcap
            _bucket = _w8e_cap_bucket(_mcap)
            _w8e_r["cap_bucket"] = _bucket
            _w8e_r["days_since_signal"] = _w8e_days_since(_tk) if _tk else None
            _w8e_cap_bucket_log[_bucket or "unknown"] = _w8e_cap_bucket_log.get(_bucket or "unknown", 0) + 1

        # Board header: honest cap-bucket composition (buy rows only)
        _w8e_buy_large  = sum(1 for r in wide["buy"] if r.get("cap_bucket") == "large")
        _w8e_buy_mid    = sum(1 for r in wide["buy"] if r.get("cap_bucket") == "mid")
        _w8e_buy_small  = sum(1 for r in wide["buy"] if r.get("cap_bucket") == "small")
        _w8e_buy_unk    = sum(1 for r in wide["buy"] if r.get("cap_bucket") is None)
        wide["cap_composition"] = {
            "large": _w8e_buy_large, "mid": _w8e_buy_mid,
            "small": _w8e_buy_small, "unknown": _w8e_buy_unk,
        }
        setups["cap_composition"] = wide["cap_composition"]
        log.info("W8-E enrichment: board cap composition large=%d mid=%d small=%d unknown=%d",
                 _w8e_buy_large, _w8e_buy_mid, _w8e_buy_small, _w8e_buy_unk)

        # ── W8-R1/W1-B: attach RIPENING + FALLING + RAN arrays to the artifact (new keys; buy unchanged).
        # Downstream consumers of `buy` keep working untouched — these are additive arrays.
        # ripening = READY + BASING (full scorecards); falling = FALLING sink (compact rows).
        wide["ripening"] = _ripening_rows
        wide["ripening_falling"] = _ripening_falling
        wide["ran"] = _ran_rows
        setups["ripening"] = _ripening_rows
        setups["ripening_falling"] = _ripening_falling
        setups["ran"] = _ran_rows
        # In-memory mirror of the board-cap overflow lane for the template (china_setups.json
        # on disk is written pre-enrichment above and stays unchanged — no watch key there).
        setups["watch"] = wide["watch"]
        # W1-B ledger: log ripening set to data/china_standout_track/ripening.parquet
        # (compact append: ticker, reasons, imminence, w2_stoch, zone — W6 conversion grading).
        # Schema-union tolerant: new columns (zone, evidence, sort keys) are written here;
        # the existing parquet reader in append_ripening tolerates the new columns via union.
        try:
            _rip_lane = os.environ.get("CN_LANE", "asia")
            _rn = china_standout_track.append_ripening(
                _ripening_rows + _ripening_falling, asof=as_of, lane=_rip_lane)
            log.info("W8-R1 ripening ledger: appended %d names this run (total ledger rows=%d)",
                     len(_ripening_rows) + len(_ripening_falling), _rn)
        except Exception as _re:  # noqa: BLE001 — ledger is additive, never fatal
            log.warning("W1-B ripening ledger failed (%s)", _re)
        # Serialize BEFORE opening the file; on TypeError name the offending key path
        # (a bare "keys must be str..." from json.dumps is unlocatable in CI logs —
        # that anonymity is what let the 07-13 tuple-key crash run for 3 sessions).
        try:
            _standouts_payload = json.dumps(
                wide,
                separators=(",", ":"),
                default=str,
                allow_nan=False,
            )
        except (TypeError, ValueError):
            _bad = _find_bad_json_keys(wide)
            log.error(
                "china_standouts.json NOT written — non-strict JSON payload; "
                "bad dict keys: %s",
                "; ".join(_bad[:20]) or "(none; inspect NaN/Infinity values)",
            )
            raise
        _standouts_path.write_text(_standouts_payload)
        (site / "factordata" / "china_setups.json").write_text(_standouts_payload)
        log.info("wrote China Prophet artifacts (%d featured / %d more / %d late-unfillable / "
                 "%d forming / %d RIPENING [%d READY+%d BASING] / %d FALLING / %d RAN / "
                 "%d raw eligible / %d actionable / %d universe)",
                 len(wide["buy"]), len(wide["more_actionable"]),
                 len(wide["late_or_unfillable"]), len(wide["forming"]),
                 len(_ripening_rows), len(_ready_capped), len(_basing_capped),
                 len(_ripening_falling), len(_ran_rows),
                 len(eligible_rows), _n_buyable, len(_scored_candidates))
    else:
        # A zero-name analysis collapse is the most severe coverage failure.
        # Never leave yesterday's apparently healthy board in place: publish an
        # explicit empty v2 artifact with a loud outage stamp.
        as_of = _board_asof or _data_through()
        try:
            _zero_session = (
                china_standout_track.session_status(as_of) if as_of else {}
            )
        except Exception:  # noqa: BLE001 — outage document must still publish
            _zero_session = {}
        _zero_coverage = {
            "as_of": as_of,
            "data_through": _data_through(),
            "panel_collected_utc": _zero_session.get("collected_utc"),
            "panel_collected_hour_utc": _zero_session.get(
                "collected_hour_utc"
            ),
            "partial_session": bool(_zero_session.get("partial_session")),
            "session_note": _zero_session.get("reason"),
            "lane": os.environ.get("CN_LANE", "asia"),
        }
        try:
            from engine.risk_radar_intl import cn_sleeve_chip  # noqa: PLC0415

            _zero_sleeve = cn_sleeve_chip()
        except Exception:  # noqa: BLE001 — optional context on an outage
            _zero_sleeve = {}
        wide = {
            "schema_version": "2.0.0",
            "as_of": as_of,
            "rank_by": china_board_rank.BOARD_DEFINITION,
            "board_definition": china_board_rank.BOARD_DEFINITION,
            "ranking": _prophet_ranking_contract(),
            "buy": [],
            "more_actionable": [],
            "late_or_unfillable": [],
            "forming": [],
            "watch": [],
            "lane_counts": {
                "featured": 0,
                "more_actionable": 0,
                "late_or_unfillable": 0,
                "forming": 0,
            },
            "execution_coverage": china_board_rank.execution_coverage([]),
            "laggards": [],
            "eligible": 0,
            "actionable": 0,
            "universe": 0,
            "quality_screen": {
                "adv_floor_yi": china_liquidity.ADV_FLOOR_YI,
                "mcap_floor_yi": MCAP_FLOOR_YI,
                "dropped": dict(screen_drop),
                "n_extended_demoted": 0,
                "note": "Analysis universe collapsed; no admission decision is available.",
            },
            "coverage": _zero_coverage,
            "sleeve_chip": _zero_sleeve,
            "cap_composition": {
                "large": 0, "mid": 0, "small": 0, "unknown": 0,
            },
            "ripening": [],
            "ripening_falling": [],
            "ran": [],
            "data_outage": {
                "flag": True,
                "metrics": {"scored_universe": {"current": 0}},
                "micro_rate_pct": 0.0,
                "reason": (
                    "Scored universe collapsed to zero. Probable data/analysis "
                    "pipeline failure; no China Prophet picks are published today."
                ),
                "reason_zh": (
                    "评分股票池降至零，可能存在数据或分析流水线故障；"
                    "今日不发布任何中国先知标的。"
                ),
            },
        }
        if disp_regime:
            wide["dispersion_regime"] = disp_regime
        if qvix_reg:
            wide["qvix_regime"] = qvix_reg
        try:
            _zero_ledger_ok = emit_cn_track_ledger(
                site,
                None,
                [],
                board_definition=china_board_rank.BOARD_DEFINITION,
                asof=as_of,
            )
            wide["track_ledger"] = (
                _CN_LAST_LEDGER.get("doc") if _zero_ledger_ok else None
            )
        except Exception as _zero_ledger_e:  # noqa: BLE001
            log.warning(
                "zero-universe China track shell failed (%s)",
                _zero_ledger_e,
            )
            wide["track_ledger"] = None
        setups = wide
        _standouts_path = site / "factordata" / "china_standouts.json"
        _standouts_payload = json.dumps(
            wide,
            separators=(",", ":"),
            default=str,
            allow_nan=False,
        )
        _standouts_path.write_text(_standouts_payload)
        (site / "factordata" / "china_setups.json").write_text(
            _standouts_payload
        )
        log.error(
            "China Prophet published explicit empty outage artifact: zero scored universe"
        )
    log.info("china library: %d analyzed, %d limited (recent listings), %d skipped (empty/failed), %d setups",
             built, limited, failed, len(_scored_candidates))
    _tick("boards + ledgers + manifest")

    # ── CN Pick Lab snapshot producer + Flagship-2 Reversion Desk ────────────
    # Spec §5 (snapshot) + §4 (reversion desk). Never-fatal: any failure logs a
    # warning and returns setups unchanged. Adds ≤30s to the library build.
    # Wires into the asia-lane commit via CN_LANE=asia (CNPL-R8).
    _cnpl_asof = _board_asof or (alpha or {}).get("as_of")
    if not _cnpl_asof:
        log.warning("china pick_lab snapshot: no settled panel as_of — skipped")
    else:
        try:
            import time as _cnpl_time
            _cnpl_t0 = _cnpl_time.time()
            from engine.pick_lab.cn_snapshot import build_cn_core_rows, CN_SNAPSHOT_COLUMNS
            from engine.pick_lab.snapshot import write_snapshot
            from engine.pick_lab.profile import CN_PROFILE
            from engine.pick_lab.reversion_desk import build_reversion_desk_artifact
            from engine.china_signals import board_type as _cn_board_type
            _cnpl_asof_date = str(pd.Timestamp(_cnpl_asof).date())

            # ── 1. Collect per-ticker raw vols (for low-vol tercile) ──────────
            _cnpl_vol_by: dict[str, float | None] = {}
            for (_cpl_t, _cpl_c, *_cpl_rest) in uni:
                try:
                    _cpl_ser = _cpl_c.dropna() if _cpl_c is not None else None
                    if _cpl_ser is None or len(_cpl_ser) < 63:
                        continue
                    _cpl_ret = _cpl_ser.pct_change(fill_method=None).dropna()
                    if len(_cpl_ret) >= 20:
                        _cnpl_vol_by[_cpl_t] = float(_cpl_ret.tail(60).std() * (252 ** 0.5))
                except Exception:  # noqa: BLE001 — additive, never fatal
                    pass

            # ── 2. Collect washout/extension from the full Prophet pool ───────
            _cnpl_washout_by: dict[str, bool | None] = {}
            _cnpl_extension_by: dict[str, dict | None] = {}
            for _cpl_r in _scored_candidates:
                _cpl_t = _cpl_r.get("ticker")
                if not _cpl_t:
                    continue
                _cnpl_washout_by[_cpl_t] = _cpl_r.get("washout_2w")
                _cnpl_extension_by[_cpl_t] = _cpl_r.get("extension")

            # ── 3. Collect 1D/2D oscillators on the closes panel ─────────────
            _cnpl_osc_by: dict[str, dict] = {}
            try:
                _cnpl_closes_path = config.data_dir() / "china_search" / "closes.parquet"
                if _cnpl_closes_path.exists():
                    from engine.pick_lab.signals_1d import compute_grids as _cnpl_grids
                    _cnpl_panel = pd.read_parquet(_cnpl_closes_path)
                    _cnpl_panel.index = pd.to_datetime(
                        _cnpl_panel.index,
                        errors="coerce",
                    )
                    _cnpl_panel = _cnpl_panel[
                        _cnpl_panel.index.notna()
                        & (
                            _cnpl_panel.index
                            <= pd.Timestamp(_cnpl_asof_date)
                        )
                    ]
                    _cnpl_osc_df = _cnpl_grids(_cnpl_panel)
                    for _cpl_t, _cpl_row in _cnpl_osc_df.iterrows():
                        _cnpl_osc_by[str(_cpl_t)] = _cpl_row.to_dict()
            except Exception as _cnpl_osc_e:  # noqa: BLE001 — additive, never fatal
                log.debug("china pick_lab: 1D/2D grid skipped (%s)", _cnpl_osc_e)

            # ── 4. Collect tech (rsi5/rsi10 etc) from per-stock JSON files ────
            _cnpl_tech_by: dict[str, dict] = {}
            _cnpl_outdir = site / "chinastockdata"
            for _cpl_t in list(sector_by.keys())[:]:
                _cpl_safe = _safe(_cpl_t)
                _cpl_fp = _cnpl_outdir / f"{_cpl_safe}.json"
                if not _cpl_fp.exists():
                    continue
                try:
                    _cpl_rec = json.loads(_cpl_fp.read_text())
                    _cpl_tech = _cpl_rec.get("tech") or {}
                    _cnpl_tech_by[_cpl_t] = {
                        "rsi5":       _cpl_tech.get("rsi5"),
                        "rsi10":      _cpl_tech.get("rsi10"),
                        "ret_5d":     _cpl_tech.get("ret_5d"),
                        "dist_ma20_z": _cpl_tech.get("dist_ma20_z"),
                        "above_ma120": _cpl_tech.get("above_ma120"),
                        "ma20_slope_up": _cpl_tech.get("ma20_slope_up"),
                        "limit_flag": _cpl_tech.get("limit_flag"),
                    }
                except Exception:  # noqa: BLE001
                    pass

            # ── 5. Board type + limit width per ticker ────────────────────────
            _cnpl_board_by: dict[str, str | None] = {}
            _cnpl_limit_width_by: dict[str, float | None] = {}
            for _cpl_t in sector_by:
                try:
                    _cpl_bd, _cpl_lw = _cn_board_type(_cpl_t)
                    _cnpl_board_by[_cpl_t] = _cpl_bd
                    _cnpl_limit_width_by[_cpl_t] = _cpl_lw
                except Exception:  # noqa: BLE001
                    _cnpl_board_by[_cpl_t] = None
                    _cnpl_limit_width_by[_cpl_t] = None

            # ── 6. Exact full-universe PIT reversal membership ────────────────
            _cnpl_rev_z_by: dict[str, float] = dict(_score_rev_z_by)
            _cnpl_rev_3m_by: dict[str, float | None] = {}
            _cnpl_rev_rank_by: dict[str, int | None] = {}
            _cnpl_rev_n_by: dict[str, int | None] = {}
            _cnpl_rev_deepest_by: dict[str, bool | None] = {}
            for _cpl_t, _cpl_ctx in _score_reversal_by.items():
                _cnpl_rev_3m_by[_cpl_t] = _cpl_ctx.get("ret_3m")
                _cnpl_rev_rank_by[_cpl_t] = _cpl_ctx.get("sector_rank")
                _cnpl_rev_n_by[_cpl_t] = _cpl_ctx.get("sector_n")
                _cnpl_rev_deepest_by[_cpl_t] = bool(
                    _cpl_ctx.get("deepest_quintile")
                )

            # ── 7. Draw-down (2y high %) from close series ────────────────────
            _cnpl_dd_by: dict[str, float | None] = {}
            for (_cpl_t, _cpl_c, *_cpl_rest) in uni:
                try:
                    _cpl_ser = _cpl_c.dropna() if _cpl_c is not None else None
                    if _cpl_ser is None or len(_cpl_ser) < 10:
                        continue
                    _cpl_look = _cpl_ser.tail(504)  # ~2y trading days
                    _cpl_high = float(_cpl_look.max())
                    _cpl_last = float(_cpl_ser.iloc[-1])
                    if _cpl_high > 0:
                        _cnpl_dd_by[_cpl_t] = round((1.0 - _cpl_last / _cpl_high) * 100, 1)
                except Exception:  # noqa: BLE001
                    pass

            # ── 8. Regime scalars ─────────────────────────────────────────────
            _cnpl_cycle_phase = None
            _cnpl_partic_regime = None
            _cnpl_partic_risk = None
            _cnpl_policy_impulse = None
            _cnpl_qvix_z = None
            _cnpl_csi300_close = None
            try:
                _cnpl_qp = (
                    config.data_dir() / "china_qvix" / "qvix300.parquet"
                )
                if _cnpl_qp.exists():
                    _cnpl_qdf = pd.read_parquet(_cnpl_qp)
                    _cnpl_qdf.index = pd.to_datetime(
                        _cnpl_qdf.index, errors="coerce"
                    )
                    _cnpl_qdf = _cnpl_qdf[
                        _cnpl_qdf.index <= pd.Timestamp(_cnpl_asof_date)
                    ]
                    if not _cnpl_qdf.empty and "close" in _cnpl_qdf:
                        _cnpl_qread = china_signals.qvix_regime(
                            _cnpl_qdf["close"]
                        )
                        _cnpl_qvix_z = (
                            (_cnpl_qread or {}).get("qvix_z")
                        )
            except Exception:  # noqa: BLE001 — PIT context stays null
                pass
            try:
                _cnpl_ms_path = (config.data_dir() / "china_regime" /
                                 "market_state.json")
                if _cnpl_ms_path.exists():
                    _cnpl_ms = json.loads(_cnpl_ms_path.read_text())
                    _cnpl_ms_asof = str(
                        _cnpl_ms.get("as_of")
                        or _cnpl_ms.get("asof")
                        or _cnpl_ms.get("date")
                        or ""
                    )[:10]
                    if (
                        _cnpl_ms_asof
                        and _cnpl_ms_asof <= _cnpl_asof_date
                    ):
                        _cnpl_cycle_phase = _cnpl_ms.get("cycle_phase")
                        _cnpl_partic_regime = _cnpl_ms.get(
                            "participation_regime"
                        )
                        _cnpl_partic_risk = _cnpl_ms.get(
                            "participation_risk"
                        )
                        _cnpl_policy_impulse = _cnpl_ms.get(
                            "policy_impulse"
                        )
            except Exception:  # noqa: BLE001 — additive, never fatal
                pass
            try:
                _csi_df = store.read("china", CSI300_ETF)
                if _csi_df is not None and "close" in _csi_df.columns:
                    _csi_close_pit = pd.to_numeric(
                        _csi_df["close"], errors="coerce"
                    ).dropna()
                    _csi_close_pit.index = pd.to_datetime(
                        _csi_close_pit.index, errors="coerce"
                    )
                    _csi_close_pit = _csi_close_pit[
                        _csi_close_pit.index
                        <= pd.Timestamp(_cnpl_asof_date)
                    ]
                    if not _csi_close_pit.empty:
                        _cnpl_csi300_close = float(
                            _csi_close_pit.iloc[-1]
                        )
            except Exception:  # noqa: BLE001
                pass

            # ── 9. Turnover by ticker (from liq_by) ──────────────────────────
            _cnpl_turnover_by: dict[str, float | None] = {
                _cpl_t: (_liq_v.get("adv_yi", None) * 1e8
                         if _liq_v and _liq_v.get("adv_yi") is not None else None)
                for _cpl_t, _liq_v in liq_by.items()
            }
            _cnpl_micro_by = {
                _cpl_t: _cpl_packet
                for _cpl_t, _cpl_packet in _micro_by.items()
                if isinstance(_cpl_packet, dict)
                and str(_cpl_packet.get("as_of") or "")[:10]
                == _cnpl_asof_date
            }
            _cnpl_limit_state_by = {
                _cpl_t: _cpl_packet.get("limit_state")
                for _cpl_t, _cpl_packet in _cnpl_micro_by.items()
            }
            _cnpl_chase_veto_by = {
                _cpl_t: (
                    (_cpl_packet.get("chase_veto") or {}).get("flag")
                    if isinstance(_cpl_packet.get("chase_veto"), dict)
                    else _cpl_packet.get("chase_veto")
                )
                for _cpl_t, _cpl_packet in _cnpl_micro_by.items()
            }
            _cnpl_t1_risk_by = {
                _cpl_t: _cpl_packet.get("t_plus_one_risk")
                for _cpl_t, _cpl_packet in _cnpl_micro_by.items()
            }

            # ── 10. Assemble rows ─────────────────────────────────────────────
            _scored_ticker_set = {
                str(_cpl_row.get("ticker"))
                for _cpl_row in _scored_candidates
                if _cpl_row.get("ticker")
            }
            _cnpl_tickers = sorted(
                _cpl_t
                for _cpl_t in _scored_ticker_set
                if _cpl_t in _close_map
                and not _close_map[_cpl_t].dropna().empty
                and str(
                    pd.Timestamp(
                        _close_map[_cpl_t].dropna().index.max()
                    ).date()
                )
                == _cnpl_asof_date
            )
            log.info(
                "china pick_lab PIT universe: %d exact-date responsibility-screened "
                "names (%d scored names excluded for lagged data)",
                len(_cnpl_tickers),
                len(_scored_ticker_set) - len(_cnpl_tickers),
            )
            _cnpl_rows = build_cn_core_rows(
                tickers=_cnpl_tickers,
                asof=_cnpl_asof,
                close_by=price_by,
                turnover_by=_cnpl_turnover_by,
                sector_by=sector_by,
                name_by={_cpl_t: _cpl_n for (_cpl_t, _, _, _cpl_n, _) in uni},
                name_zh_by=name_zh_by,
                board_by=_cnpl_board_by,
                is_st_by=st_flag_by,
                rev_3m_by=_cnpl_rev_3m_by,
                rev_z_by=_cnpl_rev_z_by,
                rev_sector_rank_by=_cnpl_rev_rank_by,
                rev_sector_n_by=_cnpl_rev_n_by,
                rev_deepest_quintile_by=_cnpl_rev_deepest_by,
                washout_2w_by=_cnpl_washout_by,
                coiled_by=coiled_by,
                extension_by=_cnpl_extension_by,
                vol_by=_cnpl_vol_by,
                osc_d12_by=_cnpl_osc_by,
                tech_by=_cnpl_tech_by,
                dd_pct_2y_by=_cnpl_dd_by,
                # Point-in-time execution data: only same-session packets.
                limit_state_by=_cnpl_limit_state_by,
                limit_width_by=_cnpl_limit_width_by,
                chase_veto_by=_cnpl_chase_veto_by,
                t_plus_one_risk_by=_cnpl_t1_risk_by,
                cycle_phase=_cnpl_cycle_phase,
                participation_regime=_cnpl_partic_regime,
                participation_risk=_cnpl_partic_risk,
                policy_impulse=_cnpl_policy_impulse,
                qvix_z=_cnpl_qvix_z,
                csi300_close=_cnpl_csi300_close,
                archetype_by={},
                above_20d_low_by={},
                theme_basket_by={},
                theme_breadth_pct_by={},
                theme_member_ret21_rank_by={},
                block_discount_recent_by={},
                lhb_inst_seats_5d_by={},
            )
            log.info("china pick_lab snapshot: %d rows assembled for %s (%.1fs)",
                     len(_cnpl_rows), _cnpl_asof, _cnpl_time.time() - _cnpl_t0)

            # ── 11. Write snapshot parquet (monthly partition) ────────────────
            if _cnpl_rows:
                _cnpl_df = pd.DataFrame(_cnpl_rows).set_index("ticker")
                _cnpl_df.attrs["asof"] = _cnpl_asof
                try:
                    # CNPL-R8: snapshot writes advance the forward ledger; only the
                    # asia-close nightly lane may do so.  Default is "" (no-op) so
                    # render/daily/weekly invocations that never set CN_LANE are
                    # honest no-ops — they cannot accidentally persist a snapshot
                    # with a render-clock asof.
                    _cnpl_lane = os.environ.get("CN_LANE", "")
                    if _cnpl_lane == "asia":
                        _cnpl_n_written = write_snapshot(
                            _cnpl_df, asof=_cnpl_asof, profile=CN_PROFILE)
                        log.info("china pick_lab snapshot: wrote %d rows to parquet (lane=asia)",
                                 _cnpl_n_written)
                    else:
                        log.debug("china pick_lab snapshot: skipped parquet write (lane=%s, not asia — CNPL-R8)",
                                  _cnpl_lane or "<unset>")
                except Exception as _cnpl_sw_e:  # noqa: BLE001 — never fatal
                    log.warning("china pick_lab snapshot: parquet write failed (%s)", _cnpl_sw_e)

                # ── 12. Flagship-2 Reversion Desk JSON ───────────────────────
                try:
                    _cnpl_fdir = site / "factordata"
                    _cnpl_fdir.mkdir(parents=True, exist_ok=True)
                    _cnpl_desk = build_reversion_desk_artifact(
                        _cnpl_df, as_of=_cnpl_asof)
                    (_cnpl_fdir / "china_reversion_desk.json").write_text(
                        json.dumps(
                            _cnpl_desk,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                    )
                    log.info("china reversion desk: %d rows written (schema=%s)",
                             _cnpl_desk.get("n_rows", 0), _cnpl_desk.get("schema"))
                except Exception as _cnpl_rd_e:  # noqa: BLE001 — never fatal
                    log.warning("china reversion desk write failed (%s)", _cnpl_rd_e)

        except Exception as _cnpl_e:  # noqa: BLE001 — never fatal (additive lane)
            log.warning("china pick_lab snapshot producer failed (%s)", _cnpl_e)
    # ── END CN Pick Lab snapshot producer ─────────────────────────────────────
    _tick("cn pick-lab snapshot producer")

    # ── W8-R7: CN per-stock MTF upturn organ ──────────────────────────────────
    # Runs AFTER the board arrays (buy/ripening) exist in wide/setups (required
    # for universe assembly). Never fatal — the dashboard degrades gracefully.
    # Asia-lane ledger write gated on CN_LANE=asia (mirrors CNPL-R8 pattern).
    try:
        import time as _mtf_time
        _mtf_t0 = _mtf_time.time()
        from engine.mtf_upturn import compute_cn as _mtf_cn_compute, write_cn_site_artifact as _mtf_cn_write
        _mtf_result = _mtf_cn_compute(data_root=config.data_dir(), as_of=as_of)
        _mtf_site_root = config.ROOT / config.load()["storage"]["site_dir"]
        _mtf_cn_write(_mtf_result, site_root=_mtf_site_root)
        log.info(
            "W8-R7 mtf_upturn_cn: universe=%d confirmed=%d watch=%d elapsed=%.1fs",
            _mtf_result.get("universe_n", 0),
            len(_mtf_result.get("cohort", {}).get("confirmed", [])),
            len(_mtf_result.get("cohort", {}).get("watch", [])),
            _mtf_result.get("elapsed_s", 0.0),
        )
        # Attach FULL result to setups so build_china.py can pass it to the template
        # directly (avoids re-reading the JSON file and eliminates the ordering hazard).
        if setups is not None:
            setups["mtf_upturn_cn"] = _mtf_result
    except Exception as _mtf_e:  # noqa: BLE001 — additive, never fatal
        log.warning("W8-R7 mtf_upturn_cn failed (%s) — dashboard degrades without MTF panel", _mtf_e)
    # ── END W8-R7 CN MTF upturn organ ─────────────────────────────────────────
    _tick("mtf_upturn organ")
    log.info("[timing] build_china_library main() TOTAL %.1fs",
             time.monotonic() - _tick_t0)

    return setups


if __name__ == "__main__":
    # CLI parity with build_china's in-process call: without alpha the CN pick-lab
    # snapshot block self-skips ("no as_of"), so the resilient-rebuild fallback lane
    # could never produce snapshots (2026-07-13..15 drought).
    try:
        _cli_alpha = compute_china_alpha()
    except Exception:  # noqa: BLE001 — never-fatal, mirrors build_china's alpha leg
        _cli_alpha = None
    main(alpha=_cli_alpha)
    sys.exit(0)
