"""Historical + unit regression for the brain's entry-quality BREADTH consumer.

What it confirms (honoring CHARTER §2–4, §6f — microscope, not verdict machine):

1. The REGIME-tracking dimension is the 200-day TREND breadth (above200%), and it moves
   monotonically with the equity regime: broad-up in a bull, split in a chop, broad-down
   in a bear. The 3D-confluence long/short STATE mix is a mean-reversion-oscillator read
   (CHARTER §5) — short-horizon ENTRY-timing colour, NOT a regime read (at a local low
   inside an uptrend the whole universe reads short-bias). So the consumer anchors the
   regime CONFLICT on trend breadth and reports entry quality separately. This test does
   NOT claim the state mix tracks the regime — only above200% does.
2. The calibration conflict fires ONLY when breadth DISAGREES with the macro posture
   (rolled-over / narrow tape under risk-on; still-broad tape under risk-off), and the
   payload is internally consistent (a broad-up trend never carries a "rolled over"
   message — entry-narrowness is flagged as entry-narrowness).

Historical breadth is rebuilt AS-OF each date by truncating every US deep-history close
series and running engine.signal_quality.analyze — the same code path the live snapshot
uses (scripts/build_signal_quality.py). Display/diagnostic only. Run:

    python research/signal_engine/test_breadth_consume.py
"""
from __future__ import annotations

import sys
import glob
import json
import warnings
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

import pandas as pd  # noqa: E402

from engine.signal_quality import analyze  # noqa: E402
from engine import master_brain as mb       # noqa: E402

# Historically-labelled equity regimes, chosen by their TREND breadth (above-200):
#   bull  — broad 2024 uptrend                 (~77% above 200)
#   mixed — early-2016 correction/recovery chop (~44% above 200, the split band)
#   bear  — deep in the 2022 drawdown          (~8% above 200)
REGIMES = [("bull", "2024-07-01"), ("mixed", "2016-02-29"), ("bear", "2022-09-30")]

# Two macro postures to probe the conflict branches against (fixtures, NOT real reads).
RISK_ON = {"macro_risk": {"label": "low"}, "growth_score": 0.6, "liquidity_overlay": "expanding"}
RISK_OFF = {"macro_risk": {"label": "severe"}, "growth_score": -0.6, "liquidity_overlay": "contracting"}


def leaf_asof(asof: str) -> dict:
    """Rebuild the mtf_signals leaf (§7B shape) as-of `asof` over the US deep universe."""
    snap = []
    for fp in sorted(glob.glob(str(ROOT / "data" / "stocks" / "*.parquet"))):
        t = Path(fp).stem
        try:
            close = pd.read_parquet(fp)["close"].dropna().loc[:asof]   # leak-free as-of read
            res = analyze(t, close)
        except Exception:
            continue
        if not res:
            continue
        snap.append({"ticker": t, "asof": res["asof"], "state": res["state"],
                     "above200": res["above200"], "weekly_bull": res["weekly_bull"],
                     "last": res["markers"][-1] if res["markers"] else None})
    return {"asof": asof, "tf": "3D", "universe": "us_deep", "signals": snap}


def make_leaf(n=30, long=0, short=0, above=0, take=0, block=0, pending=0) -> dict:
    """Hand-built leaf for the unit regressions (controlled state / trend / entry mix)."""
    states = ["long-bias"] * long + ["short-bias"] * short + ["mixed"] * (n - long - short)
    sigs = [{"ticker": f"T{i}", "state": states[i], "above200": i < above, "last": None}
            for i in range(n)]
    for i, q in enumerate(["take"] * take + ["block"] * block + ["pending"] * pending):
        sigs[i]["last"] = {"date": "2020-01-01", "type": "buy", "quality": q, "reason": "x"}
    return {"asof": "synthetic", "tf": "3D", "universe": "test", "signals": sigs}


def historical() -> dict[str, dict]:
    print("=" * 80)
    print("entry-quality BREADTH — historical regression (risk/entry-quality read, NOT alpha)")
    print("=" * 80)
    out = {}
    for label, asof in REGIMES:
        leaf = leaf_asof(asof)
        base = mb.breadth_from_leaf(leaf, macro=None)
        out[label] = base
        print(f"\n### {label.upper()}  (as-of {asof})  n={base['n']}, {base['n_at_entry']} at entry")
        print(f"    {base['summary']}")
        print(f"    TREND breadth = {base['trend_breadth']:<10} (above200 {base['above200_pct']}%) "
              f"<- the regime-tracking dimension")
        print(f"    ENTRY breadth = {base['entry_breadth']:<10} (take-share {base['take_share_resolved_pct']}%, "
              f"take {base['take_pct']}% / block {base['block_pct']}% / pending {base['pending_pct']}%) "
              f"<- short-horizon colour")
        print(f"    state mix: long {base['long_bias_pct']}% / short {base['short_bias_pct']}% / "
              f"mixed {base['mixed_pct']}%  (oscillator — not a regime read)")
        for pname, macro in (("risk-on", RISK_ON), ("risk-off", RISK_OFF)):
            cc = mb.breadth_from_leaf(leaf, macro)["calibration_check"]
            print(f"    macro={pname:<8} -> {'CONFLICT: ' + cc if cc else 'no conflict (breadth agrees)'}")
    return out


def assert_historical(reads: dict[str, dict]) -> None:
    a = {k: reads[k]["above200_pct"] for k in reads}
    assert a["bull"] > a["mixed"] > a["bear"], f"above200% not monotone with regime: {a}"
    assert reads["bull"]["trend_breadth"] == "broad-up"
    assert reads["mixed"]["trend_breadth"] == "split"
    assert reads["bear"]["trend_breadth"] == "broad-down"
    print("\n[assert] above200% monotone bull>mixed>bear, trend bands map correctly — OK")


def unit_regressions() -> None:
    print("\n" + "=" * 80)
    print("unit regressions — conflict logic & internal consistency")
    print("=" * 80)

    # (1) broad-up trend + few endorsed entries + risk-on: fire ENTRY-narrow, NOT a
    #     "trend rolled over" claim. Payload must stay internally consistent
    #     (the finding #1 self-contradiction regression).
    up_narrow = make_leaf(n=30, long=21, short=3, above=26, take=0, block=15)
    r = mb.breadth_from_leaf(up_narrow, RISK_ON)
    assert r["trend_breadth"] == "broad-up" and r["entry_breadth"] == "narrow"
    cc = r["calibration_check"]
    assert cc and "narrow leadership" in cc and "rolled over" not in cc, cc
    print(f"[1] broad-up + narrow entries + risk-on -> consistent: trend={r['trend_breadth']}, "
          f"entry={r['entry_breadth']}\n    {cc}")

    # (2) broad-up trend + broadly endorsed entries + risk-on: AGREEMENT -> silent.
    up_broad = make_leaf(n=30, long=21, short=3, above=26, take=14, block=2)
    r2 = mb.breadth_from_leaf(up_broad, RISK_ON)
    assert r2["entry_breadth"] == "endorsed" and r2["calibration_check"] is None
    print(f"[2] broad-up + endorsed entries + risk-on -> no conflict (agreement): OK")

    # (3) same broad-up tape under risk-off: CONFLICT (de-risk may be lagging).
    r3 = mb.breadth_from_leaf(up_broad, RISK_OFF)
    assert r3["calibration_check"] and "lagging" in r3["calibration_check"]
    print(f"[3] broad-up + risk-off -> conflict: {r3['calibration_check']}")

    # (4) broad-down tape under risk-off: AGREEMENT -> silent.
    down = make_leaf(n=30, long=2, short=22, above=3, take=1, block=6)
    r4 = mb.breadth_from_leaf(down, RISK_OFF)
    assert r4["trend_breadth"] == "broad-down" and r4["calibration_check"] is None
    print(f"[4] broad-down + risk-off -> no conflict (agreement): OK")

    # (5) pending entries must NOT masquerade as low conviction (take_share excludes them).
    pend = make_leaf(n=30, long=21, above=26, take=10, block=2, pending=12)
    r5 = mb.breadth_from_leaf(pend, RISK_ON)
    assert r5["take_share_resolved_pct"] == round(100 * 10 / 12) and r5["entry_breadth"] == "endorsed"
    assert r5["calibration_check"] is None, "pending wave wrongly tripped narrow"
    print(f"[5] pending entries excluded from take-share ({r5['take_share_resolved_pct']}% resolved) "
          f"-> no spurious narrow: OK")

    # (6) degrade-never-raise on malformed input (non-dict `last`, thin leaf).
    bad = {"signals": [{"ticker": "X", "state": "long-bias", "above200": True, "last": "oops"}] * 25}
    assert mb.breadth_from_leaf(bad, RISK_ON) is not None     # coerces, doesn't raise
    assert mb.breadth_from_leaf({"signals": []}, RISK_ON) is None   # too thin -> None
    assert mb.breadth_from_leaf(None, RISK_ON) is None
    print(f"[6] malformed `last` coerced, thin/None leaf -> None (no raise): OK")


def live_case() -> None:
    print("\n" + "=" * 80)
    live_macro = json.loads((ROOT / "data" / "regime" / "latest.json").read_text())
    live = mb.entry_quality_breadth(live_macro)
    if not live:
        print("LIVE: no leaf on disk — skipped")
        return
    print(f"LIVE  (as-of {live['asof']})  macro_posture={live['macro_posture']}")
    print(f"    {live['summary']}")
    print(f"    trend={live['trend_breadth']}, entry={live['entry_breadth']}")
    cc = live["calibration_check"]
    print(f"    conflict: {'YES — ' + cc if cc else 'none (regime & breadth agree — not surfaced)'}")


def main() -> None:
    reads = historical()
    assert_historical(reads)
    unit_regressions()
    live_case()
    print("\nAll assertions passed.")


if __name__ == "__main__":
    main()
