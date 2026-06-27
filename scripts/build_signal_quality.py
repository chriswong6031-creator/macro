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
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

import pandas as pd  # noqa: E402
from engine.signal_quality import analyze  # noqa: E402


def main() -> None:
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
            close = pd.read_parquet(fp)["close"].dropna()
            res = analyze(t, close)
        except Exception:
            continue
        if not res:
            continue
        (out_sig / f"{t}.json").write_text(json.dumps(res, separators=(",", ":")))
        asof = res["asof"]
        # `markers` is the validated trade stream only (risk_flag breaches live in their own
        # res["risk_flags"] list), so the brain's `last` is cleanly the last trade decision.
        snap.append({"ticker": t, "asof": res["asof"], "state": res["state"],
                     "above200": res["above200"], "weekly_bull": res["weekly_bull"],
                     "trail_breach": res["trail_breach"], "trail_stop": res["trail_stop"],
                     "early_now": res.get("early_now", False),
                     "last": res["markers"][-1] if res["markers"] else None})

    (arch / "mtf_signals_latest.json").write_text(json.dumps({
        "asof": asof, "tf": "3D", "universe": "us_deep",
        "note": "entry-quality RISK signal (display-only, NOT alpha); see research/signal_engine/CHARTER.md. "
                "Exits are the simple validated baseline (sell=SELL*, cut=fast-reversal). "
                "trail_breach/trail_stop = close-below-EMA8(3D) tail-risk flag (display-only, NOT a sell). "
                "early_now / res.early_markers = 2D-MACD pre-cross ADVANCE-WARNING (display-only context, "
                "NOT a buy and NOT scored; acting early is empirically worse entry quality — see CONFLUENCE_TUNING.md).",
        "signals": snap,
    }, indent=1))
    print(f"wrote {len(snap)} tickers -> site/signals/ + "
          f"data/signal_archive/mtf_signals_latest.json (asof {asof})")


if __name__ == "__main__":
    main()
