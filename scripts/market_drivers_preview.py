"""Eyeball the deterministic market-driver attribution on recent sessions.

    python scripts/market_drivers_preview.py [n_days]

Prints a one-line-per-day driver tape plus a detailed breakdown of the latest
day (all nine driver scores, evidence, invalidation). No site build, no writes —
reads the existing parquet store via engine.inputs.build_features().
"""
from __future__ import annotations

import sys
import warnings

warnings.filterwarnings("ignore")  # silence pandas fragmentation/perf noise

from engine import market_drivers as md

VERDICT_MARK = {"clear": "●", "mixed": "◑", "quiet": "·", "unknown": "?"}


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    rows = md.history(n)
    cfg = md._cfg()

    print(f"\nMarket-driver attribution — last {len(rows)} sessions "
          f"(window={cfg['window_d']}d, z vs {cfg['z_window_d']}d)\n")
    print(f"{'date':<12}{'':2}{'driver':<18}{'conf':<8}{'proj':>6}{'dom':>6}  evidence")
    print("-" * 100)
    for r in rows:
        if r["verdict"] == "unknown":
            print(f"{r['asof']:<12}  {r['headline']}")
            continue
        mark = VERDICT_MARK.get(r["verdict"], " ")
        label = r["primary_label"] if r["verdict"] != "quiet" else "(quiet)"
        proj = r["strength"] * r.get("dir_sign", 1)         # signed: + = canonical "pos" reading
        print(f"{r['asof']:<12}{mark:2}{label:<18}{r['confidence']:<8}"
              f"{proj:>+6.2f}{r['dominance_ratio']:>6.2f}  "
              f"{', '.join(r['evidence'][:3])}")

    last = rows[-1]
    if last["verdict"] == "unknown":
        return
    print("\n" + "=" * 100)
    print(f"LATEST — {last['asof']}")
    print("=" * 100)
    print(f"  Primary driver : {last['primary_label']}  [{last['verdict'].upper()}]"
          f"  (confidence {last['confidence']})")
    print(f"  Direction      : {last['direction']}")
    print(f"  Strength       : {last['strength']}σ   dominance ×{last['dominance_ratio']}"
          f"   agreement {last['agreement']}"
          f"   absorption pctile {last['absorption_pctile']}")
    print(f"  Headline       : {last['headline']}")
    print(f"  Evidence       : {'; '.join(last['evidence'])}")
    print(f"  Invalidation   : {last['invalidation']}")
    print("\n  All drivers (by strength):")
    for s in last["scores"]:
        bar = "█" * int(min(abs(s["projection"]), 3) * 6)
        print(f"    {s['label']:<18}{s['projection']:>6.2f}  {bar}")
    print()


if __name__ == "__main__":
    main()
