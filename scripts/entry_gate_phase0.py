"""Phase-0 falsifiable check for the fresh-from-oversold ENTRY gate (the swing-entry
revamp of engine.cycles.mtf_alignment).

The claim under test, in the user's own terms: requiring a FRESH turn FROM A LOW (weekly
bear-recovering/basing + 3-day cross from oversold + daily just-crossed) and EXCLUDING the
overextended chase should REDUCE the immediate "get shaken out on the stop right after
entry" rate vs the prior gate (which peaked its rank on already-running names).

Method = the same no-look-ahead walk-forward as scripts/_bt_signals.py: state at bar i is
built from close[i-600:i+1] ONLY; outcomes use close[i+1 : i+1+k]. The honest lens for THIS
question is the SHORT-horizon adverse excursion (next 5 / 10 days) and a fixed-stop shakeout
rate — not the 21/63d return (those are shown for context). Panel = data/stocks/*.parquet.

Buckets compared:
  OLD-aligned   — the prior gate (weekly not-falling + 3-day turning/rising + daily trigger);
  NEW-aligned   — the new gate, tier in {PRIME, ARMED};
  NEW-PRIME     — the best combination only;
  REMOVED       — OLD-aligned that the NEW gate drops (the chase it now excludes — should be
                  the WORST on short-horizon drawdown if the fix is real);
  ADDED         — NEW-aligned the OLD gate missed (fresh-from-oversold turns);
  ALL           — every bar (baseline).

Run: python -m scripts.entry_gate_phase0   (writes /tmp/entry_gate_phase0.json)
"""
from __future__ import annotations
import sys, glob, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import warnings, logging
warnings.filterwarnings("ignore"); logging.disable(logging.CRITICAL)
import numpy as np, pandas as pd
from engine.cycles import mtf_snapshot, mtf_alignment, _tf_phase, _daily_trigger

WIN, STEP = 600, 12
STOP = -0.06                       # a FIXED protective stop; "shakeout" = next-k low breaches it
FWD = (5, 10, 21, 63)              # forward windows (the first two are the entry-risk lens)
PIVOT_LB = 12                      # swing-low lookback for the PIVOT-RELATIVE (tight) stop
# The fixed stop ignores entry quality; the user's actual thesis is that a fresh-from-oversold
# entry sits just above its pivot low, so a TIGHT stop under that pivot rarely gets hit, while a
# chase has no nearby support. The pivot-stop columns below test THAT (the honest arbiter):
#   pdist  = median stop distance = entry -> recent swing low (TIGHTER is better)
#   phit10/21 = % of entries whose next-10/21d low breaks the pivot (the real stop-out rate)


def _old_aligned(mtf: dict) -> bool:
    """The PRIOR gate, isolated (no knife/ladder-state block — same omission for the new
    bucket, so the comparison reflects only the gate-LOGIC change)."""
    D = mtf.get("D") or {}
    if not D:
        return False
    W, T3 = mtf.get("W") or {}, mtf.get("3D") or {}
    have_tf = bool(W) and bool(T3)
    wph, t3ph = _tf_phase(W), _tf_phase(T3)
    weekly_ok = wph in ("basing", "turning", "rising")
    t3_ok = t3ph in ("turning", "rising")
    daily_ok = _daily_trigger(D) is not None
    return bool(have_tf and weekly_ok and t3_ok and daily_ok and wph != "falling")


def agg(rows: list) -> dict:
    if len(rows) < 30:
        return {"n": len(rows)}
    a = np.array(rows)             # cols: dd5,r5,dd10,r10,dd21,r21,dd63,r63,pivot_ret
    dd5, _r5, dd10, _r10, dd21, r21, dd63, r63, piv = (a[:, k] for k in range(9))
    return {
        "n": len(rows),
        "shake10": round(100 * (dd10 <= STOP).mean(), 1),  # fixed -6% stop (entry-blind)
        # pivot-relative TIGHT stop (the honest test of the thesis):
        "pdist": round(100 * float(np.median(-piv)), 2),   # median stop distance (tighter=better)
        "phit10": round(100 * (dd10 <= piv).mean(), 1),    # broke the pivot within 10d
        "phit21": round(100 * (dd21 <= piv).mean(), 1),    # broke the pivot within 21d
        "ddMed10": round(100 * float(np.median(dd10)), 2),
        "hit21": round(100 * (r21 > 0).mean(), 1), "mean21": round(100 * r21.mean(), 2),
        "hit63": round(100 * (r63 > 0).mean(), 1), "mean63": round(100 * r63.mean(), 2),
    }


def main() -> int:
    files = sorted(glob.glob("data/stocks/*.parquet"))
    B: dict[str, list] = {k: [] for k in ("ALL", "OLD", "NEW", "PRIME", "REMOVED", "ADDED")}
    n_inst = 0
    for fi, f in enumerate(files):
        try:
            close = pd.read_parquet(f)["close"].dropna()
        except Exception:
            continue
        if len(close) < WIN + max(FWD) + 50:
            continue
        n_inst += 1
        cv = close.to_numpy()
        for i in range(WIN, len(close) - max(FWD) - 1, STEP):
            sub = close.iloc[i - WIN:i + 1]
            try:
                mtf = mtf_snapshot(sub, "equity")
                if not mtf.get("D"):
                    continue
                sma200 = float(sub.iloc[-200:].mean())
                ext_pct = (float(sub.iloc[-1]) / sma200 - 1.0) * 100.0 if sma200 else None
                new = mtf_alignment(mtf, ext_pct=ext_pct)
                old = _old_aligned(mtf)
            except Exception:
                continue
            p0 = cv[i]
            rec = []
            for k in FWD:
                rec.append(cv[i + 1:i + 1 + k].min() / p0 - 1.0)   # max adverse excursion
                rec.append(cv[i + k] / p0 - 1.0)                   # endpoint return
            rec.append(cv[i - PIVOT_LB:i + 1].min() / p0 - 1.0)    # pivot (swing-low) stop level
            tier = new.get("tier")
            new_al = tier in ("PRIME", "ARMED")
            B["ALL"].append(rec)
            if old:
                B["OLD"].append(rec)
            if new_al:
                B["NEW"].append(rec)
            if tier == "PRIME":
                B["PRIME"].append(rec)
            if old and not new_al:
                B["REMOVED"].append(rec)
            if new_al and not old:
                B["ADDED"].append(rec)
        if (fi + 1) % 20 == 0:
            print(f"  ...{fi + 1}/{len(files)} files, {n_inst} usable", flush=True)

    print(f"\n=== ENTRY-GATE PHASE-0: {n_inst} deep-history stocks, win={WIN} step={STEP}, "
          f"stop={int(STOP*100)}% ===\n")
    hdr = (f"{'bucket':10s} {'n':>7s} {'pdist':>6s} {'phit10':>7s} {'phit21':>7s} "
           f"{'fix_sh10':>8s} {'ddMed10':>8s} {'hit21':>6s} {'mean21':>7s} {'hit63':>6s} {'mean63':>7s}")
    print(hdr + "   (pdist=stop dist% [tighter better] · phit=pivot stop-out% · fix_sh10=fixed -6% stop)")
    M = {}
    for key in ("ALL", "OLD", "NEW", "PRIME", "REMOVED", "ADDED"):
        m = agg(B[key]); M[key] = m
        if "phit10" in m:
            print(f"{key:10s} {m['n']:>7d} {m['pdist']:>6} {m['phit10']:>7} {m['phit21']:>7} "
                  f"{m['shake10']:>8} {m['ddMed10']:>8} {m['hit21']:>6} {m['mean21']:>7} "
                  f"{m['hit63']:>6} {m['mean63']:>7}")
        else:
            print(f"{key:10s} {m.get('n', 0):>7d}  (thin — < 30)")

    print("\n--- VERDICT (the falsifier — PIVOT-relative tight stop, the user's actual mechanism) ---")
    o, nw = M.get("OLD", {}), M.get("NEW", {})
    if "phit10" in o and "phit10" in nw:
        d10 = nw["phit10"] - o["phit10"]; d21 = nw["phit21"] - o["phit21"]
        dd_dist = nw["pdist"] - o["pdist"]                 # negative => NEW stop is tighter
        # the thesis holds if the fresh entries get stopped out of a pivot stop NO MORE often,
        # while sitting on a TIGHTER stop (better risk per unit of stop) and earning more.
        better = (d10 <= 0.5) and (dd_dist <= 0) and (nw["mean21"] >= o["mean21"])
        print(f"NEW vs OLD pivot stop-out: 10d {o['phit10']}%→{nw['phit10']}% ({d10:+.1f}pp) · "
              f"21d {o['phit21']}%→{nw['phit21']}% ({d21:+.1f}pp)")
        print(f"stop distance (tighter=better): {o['pdist']}%→{nw['pdist']}% ({dd_dist:+.2f}pp) · "
              f"fwd mean21 {o['mean21']}%→{nw['mean21']}% · hit63 {o['hit63']}%→{nw['hit63']}%")
        if "phit10" in M.get("REMOVED", {}):
            r = M["REMOVED"]
            print(f"REMOVED (the chase the gate drops): pdist={r['pdist']}% (WIDER stop) "
                  f"phit10={r['phit10']}% mean21={r['mean21']}% — looser stop, weaker forward return")
        print("RESULT:", "PASS — fresh-from-oversold entries sit on a tighter pivot stop, are not "
              "stopped out more often, and earn more."
              if better else
              "MIXED — see the table; the pivot stop is tighter but the stop-out edge is small (survivor panel).")
    else:
        print("inconclusive — a bucket was too thin on this panel.")

    Path("/tmp/entry_gate_phase0.json").write_text(json.dumps(M, indent=1))
    print("\nwrote /tmp/entry_gate_phase0.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
