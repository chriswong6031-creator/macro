"""Intraday LIVE risk-state -> site/live/risk_state.json.

The fast brain for the MARKET-LEVEL risk read (the sibling of build_live_overlay,
which is the fast brain for per-ticker technicals). It answers the question the
once-a-day nightly build can't: "given where the tape / vol / credit-proxy are
RIGHT NOW, what is the radar-aware Market State verdict?" — so the headline moves
as the fast signals move instead of being frozen between nightly builds.

DOCTRINE (research/LIVE_DATA_ARCHITECTURE.md):
  - The nightly build is the SLOW BRAIN. It owns the validated regime quad (7-day
    hysteresis), conviction, GTAA, and the SLOW radar legs (HY OAS / NFCI / macro).
  - This is the FAST LAYER. It recomputes ONLY the price-driven legs on live prices
    and CARRIES the slow legs forward, each STAMPED with its own as-of + basis so
    the page never claims freshness a leg doesn't have (e.g. HY OAS lags ~1 biz day
    even nightly; we say so).
  - Zero logic duplication: it splices live last-prices into the price store, then
    calls the SAME engine.risk_radar.compute() and engine.market_state.market_state_snapshot()
    the nightly build uses. The radar's context gate (SPY<200dma) therefore flips
    LIVE — the exact behaviour the slow build couldn't give.
  - HONEST MOTION: the continuous 0-100 score moves every tick (what you watch); the
    discrete band WORD (risk-on / mixed / risk-off) is DEBOUNCED (must persist N ticks)
    so live noise can't whipsaw the headline.

Fail-safe: any source down / market closed -> the live legs are marked stale and
the verdict simply equals the nightly baseline. risk_state.json always emits.
``--offline`` forces the no-network path (live == nightly) for local runs / tests.

risk_state.json is GITIGNORED, so the 3-min macro-update `git reset --hard` never
clobbers it (same contract as live/overlay.json).
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
from datetime import datetime, timezone

import pandas as pd

from engine import live_overlay, live_quotes, market_state, market_drivers, risk_radar
from lib import config
from lib import store as store_mod

log = logging.getLogger("risk_state_build")

# store-name (yahoo group) -> live-quote symbol. The radar + market-state tape read these
# off the price store; only the FAST, intraday-available ones are spliced. The SLOW radar
# legs (FRED HY OAS / DFII10, MOVE history) are NOT here -> they carry forward nightly.
SPLICE = {
    "SPY": "SPY", "QQQ": "QQQ", "IWM": "IWM", "SMH": "SMH",
    "XLU": "XLU", "XLP": "XLP", "XLY": "XLY",
    "HYG": "HYG", "TLT": "TLT",
    "_VIX": "^VIX", "_VIX3M": "^VIX3M", "_VIX9D": "^VIX9D", "_MOVE": "^MOVE",
}
# which market_state component legs become LIVE when we splice (the rest carry nightly)
_LIVE_LEGS = {"trend", "vol"}
# Volatility indices legitimately move far more than equities in a single session (VIX +40-80%
# on a real shock), so the equity limit-move guard would WRONGLY reject them — blinding the vol
# leg exactly when stress hits. Use a much looser cap (still catches a 10x glitch print).
_VOL_NAMES = {"_VIX", "_VIX3M", "_VIX9D", "_MOVE"}
_VOL_MAX_CHG = 200.0


def _usable(quote, base_close, max_chg, stale_after, now, session_open) -> float | None:
    """A fresh, real, non-outlier live trade -> its price; else None (carry nightly).
    max_chg=None disables the limit-move guard."""
    st = live_overlay.staleness(quote, stale_after, now, session_open=session_open)
    if st["stale"] or not quote or quote.get("price") is None:
        return None
    price = float(quote["price"])
    ref = quote.get("prev_close") or base_close
    if max_chg is not None and ref and abs(price / float(ref) - 1) > max_chg / 100.0:
        return None  # limit-move / glitch guard
    return price


def _spliced_frames(quotes, max_chg, stale_after, now, session_open):
    """Read nightly closes (BEFORE any store patch), splice a fresh live price onto today's
    bar. Returns (spliced_dfs{store_name: df[close]}, live_close{store_name: price},
    nightly_close{store_name: price}). Symbols without a usable quote are omitted -> they
    read nightly through the un-patched store."""
    spliced, live_close, nightly_close = {}, {}, {}
    for name, sym in SPLICE.items():
        close = live_overlay.read_close(name)
        if close is None or close.empty:
            continue
        nightly_close[name] = float(close.iloc[-1])
        cap = _VOL_MAX_CHG if name in _VOL_NAMES else max_chg
        price = _usable(quotes.get(sym), nightly_close[name], cap, stale_after, now, session_open)
        if price is None:
            continue
        s = live_overlay.splice(close, price, now)
        spliced[name] = pd.DataFrame({"close": s})
        live_close[name] = price
    return spliced, live_close, nightly_close


def _live_frame(spliced, indices=("SPY", "QQQ", "IWM")):
    """A minimal feature frame (index-tape columns) for market_state._build_tape, using the
    spliced close where we have a live price else the nightly close."""
    cols = {}
    for tkr in indices:
        if tkr in spliced:
            cols[tkr] = spliced[tkr]["close"]
        else:
            c = live_overlay.read_close(tkr)
            if c is not None and not c.empty:
                cols[tkr] = c
    return pd.DataFrame(cols) if cols else None


def _live_vix_term(live_close, nightly_close):
    """Live VIX term = VIX9D/VIX3M (the leading_signals definition), VIX/VIX3M fallback.
    Returns None if no fresh VIX leg (carry the nightly vix_term)."""
    def px(name):
        return live_close.get(name) if name in live_close else None
    v9d, v3m, vix = px("_VIX9D"), px("_VIX3M"), px("_VIX")
    if v9d and v3m:
        return round(v9d / v3m, 4)
    if vix and v3m:
        return round(vix / v3m, 4)
    return None


def _hy_oas_asof():
    """Last date of the FRED HY OAS series (the radar's heaviest credit leg) — carried, ~T+1."""
    try:
        df = store_mod.read("fred", "BAMLH0A0HYM2")
        if df is not None and len(df):
            return str(pd.to_datetime(df.index).max().date())
    except Exception:  # noqa: BLE001
        pass
    return None


def _verdict_block(ms: dict | None) -> dict:
    if not ms:
        return {}
    return {
        "verdict": ms.get("verdict"), "score": ms.get("score"), "raw_score": ms.get("raw_score"),
        "color": ms.get("color"), "label_en": ms.get("label_en"), "label_zh": ms.get("label_zh"),
        "headline_en": ms.get("headline_en"), "headline_zh": ms.get("headline_zh"),
        "radar": {k: (ms.get("radar") or {}).get(k)
                  for k in ("state", "state_ungated", "top_score", "label_en", "label_zh",
                            "context_gate", "amp", "ceiling")},
        "overrides": ms.get("overrides") or [],
    }


def _debounce(prev: dict, live_verdict: str | None, baseline_verdict: str | None,
              ticks_required: int) -> dict:
    """Move the continuous score every tick, but only flip the discrete band WORD after the
    new verdict has persisted >= ticks_required consecutive ticks. State carried in the JSON."""
    order = ["RISK_OFF", "MIXED", "RISK_ON"]
    shown = (prev.get("display") or {}).get("verdict") or baseline_verdict or live_verdict
    pend = (prev.get("display") or {}).get("pending") or {}
    if live_verdict is None or live_verdict == shown:
        return {"verdict": shown, "pending": None, "band_changed": False}
    # a different verdict is being proposed
    if pend.get("verdict") == live_verdict:
        n = int(pend.get("ticks", 1)) + 1
    else:
        n = 1
    if n >= max(1, ticks_required):
        return {"verdict": live_verdict, "pending": None, "band_changed": shown != live_verdict,
                "prev_verdict": shown}
    return {"verdict": shown, "pending": {"verdict": live_verdict, "ticks": n,
            "needs": ticks_required}, "band_changed": False,
            "in_order": (order.index(live_verdict) if live_verdict in order else None)}


def build(offline: bool = False) -> dict:
    cfg = config.load().get("live") or {}
    rs_cfg = cfg.get("risk_state") or {}
    now = datetime.now(timezone.utc)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    out_dir = site / "live"
    out_path = out_dir / "risk_state.json"

    stale_after = float(cfg.get("stale_after_min", 20))
    max_chg = float(cfg.get("max_chg_pct", live_overlay.DEFAULT_MAX_CHG_PCT))
    ticks_required = int(rs_cfg.get("debounce_ticks", 2))

    # nightly baseline (the SLOW-brain spine + the byte-identical macro.html verdict)
    try:
        latest = json.loads((config.data_dir() / "regime" / "latest.json").read_text())
    except Exception as e:  # noqa: BLE001
        log.error("risk_state: latest.json unreadable: %s", e)
        latest = {}
    nightly_ms = market_state.load_persisted() or {}
    nightly_asof = latest.get("date")
    session = live_overlay.market_session("us", now)
    prev = {}
    if out_path.exists():
        try:
            prev = json.loads(out_path.read_text())
        except Exception:  # noqa: BLE001
            prev = {}

    # live quotes for the fast symbols (graceful no-op offline / market closed)
    diag: dict = {}
    quotes = live_quotes.fetch_quotes(sorted(set(SPLICE.values())), offline=offline, diag=diag)
    spliced, live_close, nightly_close = _spliced_frames(
        quotes, max_chg, stale_after, now, session["open"])
    live_active = bool(spliced)

    # ---- recompute the engine on the spliced store (NO logic duplication) ----
    live_ms = None
    live_radar = None
    _orig_read = store_mod.read
    try:
        def _patched(group, name, *a, **k):
            if group == "yahoo" and name in spliced:
                return spliced[name]
            return _orig_read(group, name, *a, **k)
        store_mod.read = _patched  # risk_radar._s / context_gate_live now see live prices

        live_radar = risk_radar.compute()                 # live equity/vol/credit legs + live gate
        live_latest = copy.deepcopy(latest)
        live_latest["risk_radar"] = live_radar
        term = _live_vix_term(live_close, nightly_close)
        if term is not None:
            ra = (live_latest.setdefault("conditions", {})
                             .setdefault("risk_appetite", {}))
            ra["vix_term"] = term
        frame = _live_frame(spliced)
        live_ms = market_state.market_state_snapshot(live_latest, frame, latest.get("alerts") or [])
    except Exception as e:  # noqa: BLE001 — never abort the loop; fall back to nightly
        log.error("risk_state: live recompute failed: %s", e)
    finally:
        store_mod.read = _orig_read

    live_blk = _verdict_block(live_ms)
    # surface the radar's live gating detail (state_ungated + the SPY-200dma context gate) — this is
    # what flips the loud banner intraday the moment the broad tape breaks (the slow build couldn't).
    if live_radar and live_blk.get("radar") is not None:
        live_blk["radar"].update({
            "state_ungated": live_radar.get("state_ungated"),
            "context_gate": live_radar.get("context_gate"),
            "alert": live_radar.get("alert"),
            "conjunction": live_radar.get("conjunction"),
        })
    nightly_blk = _verdict_block(nightly_ms)

    # per-leg freshness ledger (honest as-of)
    legs = []
    for c in (live_ms or {}).get("components", []):
        key = c.get("key")
        is_live = live_active and key in _LIVE_LEGS
        legs.append({"key": key, "label_en": c.get("label_en"), "score": c.get("score"),
                     "basis": "live" if is_live else "carried",
                     "asof": "live" if is_live else nightly_asof})
    legs_asof = {
        "tape_trend": "live" if (live_active and "SPY" in spliced) else nightly_asof,
        "volatility": "live" if (live_active and ("_VIX3M" in spliced or "_VIX9D" in spliced)) else nightly_asof,
        "radar_fast": "live" if live_active else nightly_asof,   # equity/vol/credit-proxy radar legs
        "credit_hy_oas": _hy_oas_asof(),                          # FRED, carried, ~1 biz day lag
        "breadth": nightly_asof, "liquidity": nightly_asof,
        "macro_stress": nightly_asof, "cross_asset": nightly_asof,
    }

    # what moved the live read (vs nightly close)
    movers = []
    for name, label in (("SPY", "SPY"), ("QQQ", "QQQ"), ("_VIX", "VIX")):
        if name in live_close and name in nightly_close and nightly_close[name]:
            chg = round((live_close[name] / nightly_close[name] - 1) * 100, 2)
            if abs(chg) >= 0.05:
                movers.append({"sym": label, "chg_pct": chg})

    baseline_verdict = nightly_blk.get("verdict") or live_blk.get("verdict")
    live_verdict = live_blk.get("verdict")
    deb = _debounce(prev, live_verdict if live_active else baseline_verdict,
                    baseline_verdict, ticks_required)
    # the DISPLAY: continuous score is always the live read; the band word is debounced
    disp_verdict = deb["verdict"]
    disp_label = {"RISK_ON": ("Risk-on", "风险偏好", "green"),
                  "MIXED": ("Mixed", "混合", "yellow"),
                  "RISK_OFF": ("Risk-off", "避险", "red")}.get(disp_verdict, ("—", "—", "yellow"))
    display = {
        "verdict": disp_verdict,
        "label_en": disp_label[0], "label_zh": disp_label[1], "color": disp_label[2],
        "score": (live_blk.get("score") if live_active
                  else (nightly_blk.get("score") if nightly_blk.get("score") is not None
                        else live_blk.get("score"))),
        "band_changed": deb.get("band_changed", False),
        "pending": deb.get("pending"),
    }

    out = {
        "schema": "risk_state.v1",
        "built": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "session": session,
        "live_active": live_active,
        "stale": (not live_active),
        "stale_reason": (None if live_active else
                         ("market closed" if not session["open"] else "no fresh quotes")),
        # HONEST FRESHNESS: even "live" is vendor-delayed (Polygon Standard / Yahoo ~15 min).
        "delayed_min": int(cfg.get("delayed_min", 0)),
        "feed": str(cfg.get("feed_label", "") or ""),
        "realtime": int(cfg.get("delayed_min", 0)) == 0,
        "nightly_asof": nightly_asof,
        "polygon_status": diag.get("polygon_status", "unused"),
        "n_live_symbols": len(spliced),
        "movers": movers,
        "display": display,
        "live": live_blk,
        "nightly": nightly_blk,
        "legs": legs,
        "legs_asof": legs_asof,
        "note": ("Fast legs (tape, vol, radar equity/vol/credit-proxy + SPY-200dma context gate) "
                 "recomputed on live prices; slow legs (HY OAS, NFCI, breadth, macro) carried from "
                 "the nightly build and stamped with their own as-of. The score moves every tick; "
                 "the band word is debounced. De-risk = sizing, not selection."),
    }
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, indent=2, allow_nan=False))
    except Exception as e:  # noqa: BLE001
        log.error("risk_state write failed: %s", e)
        return {"status": "write_error", "error": str(e)}
    log.info("risk_state: live=%s n_live=%d display=%s score=%s (live=%s nightly=%s) movers=%s",
             live_active, len(spliced), display["verdict"], display["score"],
             live_blk.get("verdict"), nightly_blk.get("verdict"), movers)

    # ---- thin drivers pass (PS-R7: site/ only, NO data/ writes) ---------------
    # Recompute market_drivers snapshot (with repricing_coherence) and write it
    # alongside risk_state.json.  append_log(allow_write=False) enforces the law
    # that the parquet ledger is nightly-only.
    import time as _time
    _t0 = _time.perf_counter()
    try:
        drivers_snap = market_drivers.snapshot()
        market_drivers.append_log(drivers_snap, allow_write=False)  # PS-R7: no parquet write
        drivers_out = out_dir / "market_drivers.json"
        drivers_out.write_text(json.dumps(drivers_snap, indent=2, allow_nan=False,
                                          default=str))
        _elapsed = _time.perf_counter() - _t0
        log.info("drivers pass: state=%s score=%s elapsed=%.1fs",
                 (drivers_snap.get("repricing_coherence") or {}).get("state"),
                 (drivers_snap.get("repricing_coherence") or {}).get("score"),
                 _elapsed)
    except Exception as _e:  # noqa: BLE001 — best-effort; never abort the main path
        _elapsed = _time.perf_counter() - _t0
        log.warning("drivers pass failed (non-fatal, %.1fs): %s", _elapsed, _e)

    # ---- shock de-escalation intraday fast-path (PS-R7: site/ only) -----------
    # Reads the just-written site/live/market_drivers.json and refreshes
    # site/live/shock_state.json.  Committed firings ledger is read-only here.
    try:
        from engine import shock_deescalation as _sd
        _sd.build_intraday()
        log.info("shock_deescalation intraday pass complete")
    except Exception as _e2:  # noqa: BLE001 — best-effort; never abort the main path
        log.warning("shock_deescalation intraday pass failed (non-fatal): %s", _e2)

    return {"status": "ok", "live_active": live_active, "display": display["verdict"],
            "live": live_blk.get("verdict"), "nightly": nightly_blk.get("verdict")}


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
