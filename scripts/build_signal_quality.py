"""Build MTF confluence buy-filter signals.

Writes, per US deep-history ticker, the chart-marker file site/signals/<T>.json AND a
compact brain snapshot data/signal_archive/mtf_signals_latest.json (loaded by engine/run.py
into latest["mtf_signals"]). DISPLAY-ONLY entry-quality / risk signal — see the contract in
research/signal_engine/CHARTER.md (§7). Heavy compute lives here so engine/run.py just reads
the snapshot and can never be slowed by it.
"""
from __future__ import annotations

import sys
import glob
import json
import warnings
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if __name__ == "__main__":
    # CLI-only silencers.  logging.disable() is PROCESS-GLOBAL state: at module level it
    # leaks out of any import of this file and mutes every logger for the rest of the
    # process (order-dependent pytest flakes; bitten twice — see walk_forward.py and
    # tests/test_no_module_level_logging_disable.py).
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

import argparse  # noqa: E402

import pandas as pd  # noqa: E402
from engine.signal_quality import analyze  # noqa: E402
from engine.bar_derive import daily_close_for  # noqa: E402
from engine import marker_integrity  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Build MTF confluence buy-filter signals.")
    ap.add_argument("--intraday", action="store_true",
                    help="derive each ticker's daily close from the 15-min-DELAYED intraday "
                         "store (data/intraday/<T>.parquet) when present, else fall back to the "
                         "nightly adjusted daily store. Research hook — OFF by default; mind the "
                         "raw-vs-adjusted caveat in engine/bar_derive.py.")
    args = ap.parse_args()

    src = ROOT / "data" / "stocks"
    out_sig = ROOT / "site" / "signals"
    out_sig.mkdir(parents=True, exist_ok=True)
    arch = ROOT / "data" / "signal_archive"
    arch.mkdir(parents=True, exist_ok=True)

    snap, asof = [], None
    files = sorted(glob.glob(str(src / "*.parquet")))
    for fp in files:
        t = Path(fp).stem
        try:
            if args.intraday:
                # opt-in hook: intraday-derived daily close (engine/bar_derive). Per-ticker
                # fallback to the adjusted store when there is NO intraday file, it derives
                # empty, OR the intraday history is too short for the 3D warmup (a cold-started
                # store) — so a sparse intraday file never silently drops a ticker.
                close = daily_close_for(t, prefer_intraday=True, stocks_dir=src)
                if close is not None:
                    close = close.dropna()
                if close is None or len(close) < 130:
                    close = pd.read_parquet(fp)["close"].dropna()
                res = analyze(t, close)
            else:
                df = pd.read_parquet(fp)
                close = df["close"].dropna()
                # data/stocks carries TRUE intraday high/low — feed them so swing-high &
                # bearish-divergence read real extremes (close-only names omit them and
                # fall back to close; see engine.ohlc_reconstruct for the recon path).
                high = df["high"] if "high" in df.columns else None
                low = df["low"] if "low" in df.columns else None
                res = analyze(t, close, high, low)
        except Exception:
            continue
        if not res:
            continue
        # RC-R2 append-only marker law: a nightly recompute may never re-date or delete
        # a marker the site already rendered (engine/marker_integrity.py; drift counts
        # disclosed in res["pit"]). The brain snapshot below reads the MERGED stream.
        sig_path = out_sig / f"{t}.json"
        try:
            prev = json.loads(sig_path.read_text()) if sig_path.exists() else None
        except Exception:  # noqa: BLE001 — unreadable prior file → treat as new
            prev = None
        res = marker_integrity.merge_payload(prev, res)
        sig_path.write_text(json.dumps(res, separators=(",", ":")))
        asof = res["asof"]
        # `markers` is the validated trade stream only (risk_flag breaches live in their own
        # res["risk_flags"] list), so the brain's `last` is cleanly the last trade decision.
        snap.append({"ticker": t, "asof": res["asof"], "state": res["state"],
                     "above200": res["above200"], "weekly_bull": res["weekly_bull"],
                     "trail_breach": res["trail_breach"], "trail_stop": res["trail_stop"],
                     "early_now": res.get("early_now", False),
                     "last": res["markers"][-1] if res["markers"] else None})

    note = ("entry-quality RISK signal (display-only, NOT alpha); "
            "see research/signal_engine/CHARTER.md. "
            "Exits are the simple validated baseline (sell=SELL*, cut=fast-reversal). "
            "trail_breach/trail_stop = close-below-EMA8(3D) tail-risk flag (display-only, NOT a sell). "
            "early_now / res.early_markers = 2D-MACD pre-cross ADVANCE-WARNING (display-only context, "
            "NOT a buy and NOT scored; acting early is empirically worse entry quality — see CONFLUENCE_TUNING.md).")
    if args.intraday:
        note += " [intraday-derived close, ~15-min delayed — research hook]"
    (arch / "mtf_signals_latest.json").write_text(json.dumps({
        "asof": asof, "tf": "3D", "universe": "us_deep",
        "source": "intraday_delayed" if args.intraday else "daily_adjusted",
        "note": note,
        "signals": snap,
    }, indent=1))
    print(f"wrote {len(snap)} tickers -> site/signals/ + "
          f"data/signal_archive/mtf_signals_latest.json (asof {asof}"
          f"{', intraday' if args.intraday else ''})")


if __name__ == "__main__":
    main()
