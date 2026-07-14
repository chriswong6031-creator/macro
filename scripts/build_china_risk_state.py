"""Intraday LIVE China risk-state -> site/live/china_risk_state.json.

The China analogue of scripts/build_risk_state.py: the fast brain for the China
Market State board on china.html. It answers the same question the nightly build
can't: "given where the Shanghai Composite / CSI 300 / Shenzhen tape and the
external capital-flow legs are RIGHT NOW, what is the radar-aware China Market
State verdict?" — so the board headline moves as the fast signals move instead of
being frozen between nightly builds.

DOCTRINE (mirrors research/LIVE_DATA_ARCHITECTURE.md for the CN market):
  - The nightly build (scripts/build_china.py) is the SLOW BRAIN. It owns the
    calibrated RORO composite (9-leg causal z-scores), the PBoC liquidity overlay,
    the QVIX+margin vol proxy, and the breadth percentile (which requires the full
    china_breadth store to compute). ALL of those remain nightly here too.
  - This is the FAST LAYER for the PRICE-DRIVEN legs only: the 3-index CN tape
    (F1/trend), the external capital-flow leg that leads A-share drawdowns
    (USD/CNH + DX-Y.NYB via risk_radar_intl), and the GTAA ETFs that let any
    engine read of those names go live. Everything else carries forward.
  - Zero logic duplication: we splice live last-prices into the price store via a
    store.read monkeypatch, then call the SAME engine.risk_radar_intl.snapshot and
    engine.market_state.market_state_snapshot the nightly build uses. The breadth
    percentile + RORO conditions that were injected in-memory by build_china are
    replicated in-memory here on a deep copy of latest.json.
  - NIGHTLY BASELINE: there is no persisted CN market_state snapshot (persist() is
    US-only in engine.market_state), so we reproduce the nightly read by running
    the identical pipeline WITHOUT the store patch. The fresh-checkout stores equal
    the Asia-close state, which is exactly what the rendered board reflects.
  - HONEST MOTION: the continuous 0-100 score moves every tick (tape leg updated on
    live prices); the discrete band WORD is debounced (must persist N ticks) so a
    noisy open can't whipsaw the headline.

LIVE LEGS (price-driven, update every tick during HKEX RTH):
  tape_trend       — 3-index CN tape (000001.SS / 510300.SS / 399001.SZ), live via splice
  radar_capital_flow — risk_radar_intl.CN: USD/CNH + DX-Y.NYB legs become live when
                     either is spliced; US rate shock legs (DGS2/DGS10/DFII10) are
                     carried (FRED, ~T+1) just as in the US build

CARRIED LEGS (nightly stores, stamped with their own as-of):
  radar_rate_shock — last date of FRED DGS10 store (~T+1 lag)
  breadth          — china_breadth/breadth last date (nightly-only, requires full store)
  vol_qvix         — china_qvix/qvix300 last date (nightly)
  risk_roro        — nightly_asof (RORO composite is nightly)
  liquidity_pboc   — nightly_asof (PBoC overlay is nightly)
  stress_guards    — nightly_asof (slowdown / drawdown gauges are nightly)

Fail-safe: any error in the live recompute logs and falls back to nightly; the JSON
always emits. --offline forces the no-network path (live == nightly). NO writes
anywhere except site/live/china_risk_state.json.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
from datetime import datetime, timezone

import pandas as pd

from engine import live_overlay, live_quotes, market_state, risk_radar_intl
from engine.market_state_cn import CN_PROFILE
from lib import config
from lib import store as store_mod

log = logging.getLogger("china_risk_state_build")

# Store (group, name) -> live-quote symbol. The radar + market-state tape read
# these off the price store; only the FAST, intraday-available A-share and
# FX/capital-flow symbols are here. The SLOW legs (FRED rates, PBoC, breadth)
# are NOT here — they carry forward nightly.
#
# 000001.SS / 510300.SS / 399001.SZ  — the 3-index CN tape (_CN_INDICES in
#   engine/market_state_cn.py); these are the tape/trend leg
# 510300.SS is also the price-side of the breadth divergence check
#   (F4 in build_china): live splice makes the divergence flag reactive intraday
# 159915.SZ / 510880.SS / 511010.SS / 512400.SS / 518880.SS — the GTAA ETFs;
#   any engine read of those store names now goes live (feeds movers)
# ("yahoo","CNH_F") -> "CNH=F"  — USD/CNH: the primary capital-flow leg for the
#   CN radar; live splice makes radar_capital_flow reactive intraday
# ("yahoo","DX-Y.NYB") -> "DX-Y.NYB" — DXY: secondary FX leg (fills CNH gap
#   pre-2013, combined in risk_radar_intl._sub_legs)
# ("hk","_HSI") -> "^HSI" — Hang Seng index; NO CN state leg reads it today
#   (it has no role in CN_PROFILE or CN_RADAR), but it feeds the movers block
#   and provides HK context on the China board
SPLICE: dict[tuple[str, str], str] = {
    ("china",   "000001.SS"): "000001.SS",
    ("china",   "399001.SZ"): "399001.SZ",    # completes the 3-index CN tape
    ("china",   "510300.SS"): "510300.SS",
    ("china",   "159915.SZ"): "159915.SZ",
    ("china",   "510880.SS"): "510880.SS",
    ("china",   "511010.SS"): "511010.SS",
    ("china",   "512400.SS"): "512400.SS",
    ("china",   "518880.SS"): "518880.SS",
    ("yahoo",   "CNH_F"):     "CNH=F",         # radar's primary capital-flow leg
    ("yahoo",   "DX-Y.NYB"): "DX-Y.NYB",      # DXY: secondary FX, fills pre-2013 CNH gap
    ("hk",      "_HSI"):      "^HSI",           # movers / HK context only; no CN state leg
}

# Which components of market_state_snapshot become LIVE when we splice. The rest
# carry the nightly read. "trend" = the 3-index tape; "vol" stays nightly (QVIX
# is a nightly store, no live splice).
_LIVE_LEGS = {"trend"}

# Limit-move guard: the config default (35%) is a GLITCH guard (10x prints), not an
# A-share limit-board validator — main boards halt at ±10% (ChiNext/STAR ±20%), so a
# wrong-but-plausible 15% print on a main-board name would pass. Accepted: the guard
# mirrors the US build's contract, and the tape indices/ETFs spliced here move far
# less than single names. CNH/DXY/HSI are subject to the same default guard.

# Import the usable-quote helper and debounce function from scripts.build_risk_state
# rather than copying them. They are PURE (no network, no disk) so the import is
# zero-drift: if the US build changes the guard logic, the CN build automatically
# inherits the fix. The verdict_block helper is also reused for the same reason.
from scripts.build_risk_state import _usable, _debounce, _verdict_block  # noqa: E402


def _read_cn_close(group: str, name: str) -> pd.Series | None:
    """Read the daily close Series for a CN/HK store (group, name) pair.
    Unlike live_overlay.read_close() which is yahoo/stocks-only, this handles
    the china/hk group prefix that our SPLICE map uses."""
    df = store_mod.read(group, name)
    if df is None or df.empty:
        return None
    col = "close" if "close" in df.columns else (df.columns[0] if len(df.columns) else None)
    if col is None:
        return None
    s = df[col].astype(float).dropna()
    return s if not s.empty else None


def _spliced_frames_cn(quotes: dict, max_chg: float, stale_after: float,
                       now: datetime, session_open: bool):
    """Read nightly closes (BEFORE any store patch) for every SPLICE symbol, splice
    a fresh live price onto today's bar where usable. Returns:
      spliced_dfs  {(group,name): DataFrame(close)}  — for the store monkeypatch
      live_close   {(group,name): float}              — usable live prices
      nightly_close {(group,name): float}             — last nightly bar price
    Symbols without a usable quote are omitted from spliced/live_close; they read
    nightly through the un-patched store."""
    spliced: dict = {}
    live_close: dict = {}
    nightly_close: dict = {}
    for (group, name), sym in SPLICE.items():
        close = _read_cn_close(group, name)
        if close is None or close.empty:
            continue
        nightly_close[(group, name)] = float(close.iloc[-1])
        price = _usable(quotes.get(sym), nightly_close[(group, name)],
                        max_chg, stale_after, now, session_open)
        if price is None:
            continue
        s = live_overlay.splice(close, price, now)
        spliced[(group, name)] = pd.DataFrame({"close": s})
        live_close[(group, name)] = price
    return spliced, live_close, nightly_close


def _precompute_breadth(features_frame: pd.DataFrame | None) -> dict | None:
    """Replicate the F4 breadth precompute from build_china.py lines 808-816 exactly:
    both the percentile AND the divergence price side read the FEATURE-FRAME columns
    (bdate-reindexed + ffill-limited), never the raw store — so the iloc[-22] lookback
    lands on the same calendar dates as the nightly board's computation. When the frame
    is built under the store patch, the 510300.SS column already carries the spliced
    live price; the breadth column stays nightly (derived store, no live splice).
    Returns a conditions["breadth"] dict {above200_pctile, div} or None."""
    if features_frame is None:
        return None
    _b = (features_frame["pct_above_200"].dropna()
          if "pct_above_200" in getattr(features_frame, "columns", []) else None)
    if _b is None or len(_b) < 60:
        return None
    _win = _b.tail(252 * 5)
    _pctile = float((_win <= _win.iloc[-1]).mean())
    _px = (features_frame["510300.SS"].dropna()
           if "510300.SS" in features_frame.columns else None)
    _div = bool(_px is not None and len(_px) > 21 and len(_b) > 21
                and _b.iloc[-1] < _b.iloc[-22] and _px.iloc[-1] > _px.iloc[-22])
    return {"above200_pctile": _pctile, "div": _div}


def _readonly_can_force() -> bool:
    """The board applies the radar hard-force only once the CN forward-grade ledger
    matures (Article-3 Wilson gate; build_china attaches scorecard()["can_force"]).
    Reproduce that authority READ-ONLY: scorecard(log_governance=False) reads the
    graded ledger without the governance append — the nightly snapshot_and_grade
    remains the sole ledger/governance writer. Degrades to False (never-force)."""
    try:
        from engine import risk_radar_intl_audit as _rra
        return bool(_rra.scorecard(risk_radar_intl.CN_PROFILE.key,
                                   log_governance=False).get("can_force"))
    except Exception as e:  # noqa: BLE001
        log.warning("china_risk_state: read-only can_force failed (%s); never-force", e)
        return False


def _fred_dgs10_asof() -> str | None:
    """Last date of the FRED DGS10 series (US 10y rate — the main CN radar rate leg).
    This store is FRED-sourced (~T+1 lag), always carried, never live-spliced."""
    try:
        df = store_mod.read("fred", "DGS10")
        if df is not None and len(df):
            return str(pd.to_datetime(df.index).max().date())
    except Exception:  # noqa: BLE001
        pass
    return None


def _store_last_date(group: str, name: str, col: str = "close") -> str | None:
    """Return the last non-null index date of a store series as an ISO string."""
    try:
        df = store_mod.read(group, name)
        if df is None or df.empty:
            return None
        c = col if col in df.columns else df.columns[0]
        s = df[c].dropna()
        if s.empty:
            return None
        return str(pd.to_datetime(s.index).max().date())
    except Exception:  # noqa: BLE001
        return None


def build(offline: bool = False) -> dict:
    cfg = config.load().get("live") or {}
    crs_cfg = cfg.get("china_risk_state") or {}
    now = datetime.now(timezone.utc)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    out_dir = site / "live"
    out_path = out_dir / "china_risk_state.json"

    stale_after = float(cfg.get("stale_after_min", 20))
    max_chg = float(cfg.get("max_chg_pct", live_overlay.DEFAULT_MAX_CHG_PCT))
    ticks_required = int(crs_cfg.get("debounce_ticks", 2))

    # Load the nightly latest.json (the spine of the China board)
    try:
        latest = json.loads(
            (config.data_dir() / "china_regime" / "latest.json").read_text()
        )
    except Exception as e:  # noqa: BLE001
        log.error("china_risk_state: china_regime/latest.json unreadable: %s", e)
        latest = {}
    nightly_asof = latest.get("date")

    # Session checks: usability requires EITHER the CN or HK session to be open
    # (CN 09:30-11:30 / 13:00-15:00 Shanghai, HK 09:30-12:00 / 13:00-16:00 HKT).
    cn_session = live_overlay.market_session("cn", now)
    hk_session = live_overlay.market_session("hk", now)
    session_open = cn_session["open"] or hk_session["open"]

    # Load previous output for debounce state
    prev: dict = {}
    if out_path.exists():
        try:
            prev = json.loads(out_path.read_text())
        except Exception:  # noqa: BLE001
            prev = {}

    # Live quotes for the fast symbols (graceful no-op offline / market closed)
    diag: dict = {}
    # All CN/HK symbols go to Yahoo spark (keyless), same as live_overlay intl_source
    quotes = live_quotes.fetch_quotes(
        sorted({sym for sym in SPLICE.values()}),
        offline=offline, diag=diag
    )
    spliced, live_close, nightly_close = _spliced_frames_cn(
        quotes, max_chg, stale_after, now, session_open
    )
    live_active = bool(spliced)

    # ---- nightly baseline (run WITHOUT store patch to reproduce rendered board) ----
    # There is no persisted CN market_state snapshot (persist() is US-only), so we
    # reproduce the nightly read by running the same pipeline on the fresh-checkout
    # stores, which equal the Asia-close state the rendered board reflects.
    nightly_ms: dict | None = None
    can_force = _readonly_can_force()   # same authority read for both passes
    try:
        from engine.china_inputs import build_features as _build_features
        _f_nightly = _build_features()
        _latest_nightly = copy.deepcopy(latest)
        # F4 breadth precompute for nightly (feature-frame columns, as build_china does)
        _br_nightly = _precompute_breadth(_f_nightly)
        if _br_nightly is not None:
            _latest_nightly.setdefault("conditions", {})["breadth"] = _br_nightly
        _latest_nightly["risk_radar"] = risk_radar_intl.compute(risk_radar_intl.CN_PROFILE)
        _latest_nightly["risk_radar"]["can_force"] = can_force
        # build_china passes the full feature frame; _build_tape reads the 3 index columns
        nightly_ms = market_state.market_state_snapshot(
            _latest_nightly, _f_nightly,
            latest.get("alerts") or [], profile=CN_PROFILE
        )
    except Exception as e:  # noqa: BLE001
        log.warning("china_risk_state: nightly baseline failed (%s); nightly block will be empty", e)

    # ---- recompute the engine on the spliced store (NO logic duplication) ----
    live_ms: dict | None = None
    _orig_read = store_mod.read
    try:
        def _patched(group, name, *a, **k):
            key = (group, name)
            if key in spliced:
                return spliced[key]
            return _orig_read(group, name, *a, **k)
        store_mod.read = _patched  # risk_radar_intl + market_state now see live prices

        # Build features from the patched store (china_inputs.build_features reads
        # the china price store, which the monkeypatch now redirects for our spliced
        # tickers — so the frame's 510300.SS / index columns carry the live price)
        from engine.china_inputs import build_features as _build_features_live
        _f_live = _build_features_live()

        latest_live = copy.deepcopy(latest)

        # (a) Replicate the F4 breadth precompute verbatim (build_china lines 808-816):
        # feature-frame columns for both sides; the breadth column is nightly-only
        # (derived store, no live splice) while the price side is live via the splice.
        _br_live = _precompute_breadth(_f_live)
        if _br_live is not None:
            latest_live.setdefault("conditions", {})["breadth"] = _br_live

        # (b) External-driver Risk Radar — the patched store makes the USD/CNH and
        # DX-Y.NYB legs reactive to live prices. can_force parity via the read-only
        # scorecard (see _readonly_can_force). NEVER call:
        # risk_radar_intl_audit.snapshot_and_grade, _intl_tune.tune,
        # risk_radar_scorecard.write — those advance nightly ledgers.
        latest_live["risk_radar"] = risk_radar_intl.compute(risk_radar_intl.CN_PROFILE)
        latest_live["risk_radar"]["can_force"] = can_force

        # (c) Same market_state_snapshot the nightly build calls, on the same full
        # feature frame (build_china passes _f; _build_tape reads the 3 index columns)
        live_ms = market_state.market_state_snapshot(
            latest_live, _f_live,
            latest.get("alerts") or [], profile=CN_PROFILE
        )
    except Exception as e:  # noqa: BLE001 — never abort; fall back to nightly
        log.error("china_risk_state: live recompute failed: %s", e)
    finally:
        store_mod.read = _orig_read   # ALWAYS restore, even on exception

    live_blk = _verdict_block(live_ms)
    nightly_blk = _verdict_block(nightly_ms)

    # Per-leg freshness ledger (honest as-of stamps per-leg)
    legs = []
    for c in (live_ms or nightly_ms or {}).get("components", []):
        key = c.get("key")
        is_live = live_active and key in _LIVE_LEGS
        legs.append({
            "key": key, "label_en": c.get("label_en"), "score": c.get("score"),
            "basis": "live" if is_live else "carried",
            "asof": "live" if is_live else nightly_asof,
        })

    # capital-flow leg (radar) goes live when CNH_F or DX-Y.NYB is spliced
    _cf_live = (live_active and (
        ("yahoo", "CNH_F") in spliced or ("yahoo", "DX-Y.NYB") in spliced
    ))
    legs_asof = {
        # tape uses 000001.SS (SHCOMP) as the primary indicator
        "tape_trend": "live" if (live_active and ("china", "000001.SS") in spliced) else nightly_asof,
        # radar capital-flow = USD/CNH + DXY — live when either is spliced
        "radar_capital_flow": "live" if _cf_live else nightly_asof,
        # US rate-shock legs come from FRED stores (~T+1 lag); always carried
        "radar_rate_shock": _fred_dgs10_asof(),
        # breadth = china_breadth store (nightly-only, derived store)
        "breadth": _store_last_date("china_breadth", "breadth", "pct_above_200") or nightly_asof,
        # vol proxy = QVIX300 from china_qvix store (nightly)
        "vol_qvix": _store_last_date("china_qvix", "qvix300") or nightly_asof,
        # remaining conditions legs — all nightly
        "risk_roro": nightly_asof,
        "liquidity_pboc": nightly_asof,
        "stress_guards": nightly_asof,
    }

    # Movers: SHCOMP / CSI300 / HSI / CNH vs nightly close (threshold 0.05%)
    movers = []
    _mover_map = [
        (("china", "000001.SS"), "SHCOMP"),
        (("china", "510300.SS"), "CSI300"),
        (("hk",    "_HSI"),      "HSI"),
        (("yahoo", "CNH_F"),     "CNH"),
    ]
    for key, label in _mover_map:
        if key in live_close and key in nightly_close and nightly_close[key]:
            chg = round((live_close[key] / nightly_close[key] - 1) * 100, 2)
            if abs(chg) >= 0.05:
                movers.append({"sym": label, "chg_pct": chg})

    # Debounce: score moves every tick; band WORD debounced >= ticks_required
    baseline_verdict = nightly_blk.get("verdict") or live_blk.get("verdict")
    live_verdict = live_blk.get("verdict")
    deb = _debounce(prev, live_verdict if live_active else baseline_verdict,
                    baseline_verdict, ticks_required)
    disp_verdict = deb["verdict"]
    # The label map mirrors the US build — same three bands, same Chinese labels
    disp_label = {
        "RISK_ON":  ("Risk-on",  "风险偏好", "green"),
        "MIXED":    ("Mixed",    "混合",     "yellow"),
        "RISK_OFF": ("Risk-off", "避险",     "red"),
    }.get(disp_verdict, ("—", "—", "yellow"))
    display = {
        "verdict":  disp_verdict,
        "label_en": disp_label[0], "label_zh": disp_label[1], "color": disp_label[2],
        "score": (live_blk.get("score") if live_active
                  else (nightly_blk.get("score") if nightly_blk.get("score") is not None
                        else live_blk.get("score"))),
        "band_changed": deb.get("band_changed", False),
        "pending": deb.get("pending"),
    }

    out = {
        "schema": "china_risk_state.v1",
        "built": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        # Both sessions emitted: the china board covers A-shares AND HK context
        "session": {"cn": cn_session, "hk": hk_session},
        "live_active": live_active,
        "stale": (not live_active),
        "stale_reason": (None if live_active else
                         ("market closed" if not session_open else "no fresh quotes")),
        # HONEST FRESHNESS: Yahoo spark is ~15-min delayed (same as the US build)
        "delayed_min": int(cfg.get("delayed_min", 15)),
        "feed": str(cfg.get("feed_label", "") or ""),
        "realtime": int(cfg.get("delayed_min", 15)) == 0,
        "nightly_asof": nightly_asof,
        "n_live_symbols": len(spliced),
        "movers": movers,
        "display": display,
        "live": live_blk,
        "nightly": nightly_blk,
        "legs": legs,
        "legs_asof": legs_asof,
        "note": (
            "SAME display-only construction as the nightly China Market State board "
            "(engine.market_state CN_PROFILE). Fast legs (tape/trend, USD/CNH + DXY "
            "radar capital-flow) recomputed on ~15-min-delayed Yahoo prices during "
            "HKEX RTH; slow legs (RORO composite, QVIX, breadth percentile, PBoC "
            "liquidity, drawdown guards) carried from the nightly build and stamped "
            "with their own as-of. The continuous score moves every tick; the band "
            "word is debounced. De-risk = sizing, not selection."
        ),
    }

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, indent=2, allow_nan=False))
    except Exception as e:  # noqa: BLE001
        log.error("china_risk_state write failed: %s", e)
        return {"status": "write_error", "error": str(e)}

    log.info(
        "china_risk_state: live=%s n_live=%d display=%s score=%s "
        "(live=%s nightly=%s) movers=%s",
        live_active, len(spliced), display["verdict"], display["score"],
        live_blk.get("verdict"), nightly_blk.get("verdict"), movers
    )
    return {
        "status": "ok", "live_active": live_active,
        "display": display["verdict"],
        "live": live_blk.get("verdict"), "nightly": nightly_blk.get("verdict"),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="skip network; live == nightly (local test / closed-market path)")
    args = ap.parse_args()
    print(build(offline=args.offline))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
