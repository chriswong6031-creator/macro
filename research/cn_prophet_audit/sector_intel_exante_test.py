"""Was the V1 loser concentration knowable ex-ante by OUR OWN sector/theme engines?

MEASUREMENT INSTRUMENT. Joins the PIT `data/china_sector_cycles/forward_log.parquet`
(accrued nightly since 2026-06-26 — covers the whole V1 era) and the PIT-dated
curated basket membership (`data/baskets_china/membership.json`, added/removed
dates) onto the 407 matured V1 episodes, at each episode's admission date.

Question: does the cycle engine's basket state at admission (phase, osc_slope,
rs_rank, above200d) separate losers from winners? If yes, the sector/theme
intelligence had ex-ante value the pick chain never consumed (wiring case).
If no, display-only was the right call (honest null).

Run from repo root: python3 research/cn_prophet_audit/sector_intel_exante_test.py
Output: research/cn_prophet_audit/sector_intel_exante_results.json (frozen)
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "sector_intel_exante_results.json"


def med(vals):
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    return round(float(np.median(vals)), 3) if vals else None


def main() -> None:
    eps = json.loads((Path(__file__).parent / "v1_loser_audit_results.json").read_text())["episodes"]
    flog = pd.read_parquet(ROOT / "data/china_sector_cycles/forward_log.parquet")
    flog = flog[flog["kind"] == "basket"].copy()
    flog["date"] = flog["date"].astype(str)

    mem = json.loads((ROOT / "data/baskets_china/membership.json").read_text())["baskets"]
    by_ticker: dict[str, list[tuple[str, str, str | None]]] = defaultdict(list)
    for bid, blk in mem.items():
        for m in blk.get("members") or []:
            by_ticker[str(m["ticker"])].append(
                (bid, str(m.get("added") or "1900-01-01"), m.get("removed")))

    flog_by = {(r["date"], str(r["id"])): r for _, r in flog.iterrows()}
    flog_dates = sorted(flog["date"].unique())

    def basket_state(ticker: str, d: str):
        """Best-RS basket state for the ticker at date d (PIT membership + PIT log)."""
        cands = []
        eff = max((x for x in flog_dates if x <= d), default=None)
        if eff is None:
            return None
        for bid, added, removed in by_ticker.get(ticker, []):
            if added <= d and (removed is None or removed > d):
                row = flog_by.get((eff, f"b-{bid}"))
                if row is not None:
                    cands.append(row)
        if not cands:
            return None
        best = min(cands, key=lambda r: r.get("rs_rank") or 99)
        return best

    rows = []
    for e in eps:
        st = basket_state(e["ticker"], e["date"])
        rec = {"ticker": e["ticker"], "date": e["date"], "excess": e["excess"],
               "covered": st is not None}
        if st is not None:
            rec.update({
                "phase": str(st.get("phase")),
                "osc_up": bool((st.get("osc_slope") or 0) > 0),
                "rs_rank": int(st.get("rs_rank")) if pd.notna(st.get("rs_rank")) else None,
                "above200d": bool(st.get("above200d")),
                "basket": str(st.get("name")),
            })
        rows.append(rec)

    cov = [r for r in rows if r["covered"]]
    print(f"episodes={len(rows)} basket-covered={len(cov)} "
          f"({100 * len(cov) / len(rows):.0f}%)")

    def table(rows_, key):
        g = defaultdict(list)
        for r in rows_:
            g[str(r.get(key))].append(r["excess"])
        out = {}
        for k, v in sorted(g.items()):
            out[k] = {"n": len(v),
                      "loser_rate": round(sum(1 for x in v if x <= 0) / len(v), 3),
                      "median_excess": med(v)}
        return out

    # phase × slope compound (the engine's own "first-tick-up" idiom generalized)
    for r in cov:
        r["phase_slope"] = f"{r['phase']}{'+' if r['osc_up'] else '-'}"
        rk = r.get("rs_rank")
        r["rs_tercile"] = None if rk is None else ("top" if rk <= 7 else "mid" if rk <= 15 else "bottom")

    uncovered = [r for r in rows if not r["covered"]]
    out = {
        "as_of": "2026-08-04",
        "coverage": {"episodes": len(rows), "covered": len(cov),
                     "uncovered_loser_rate": round(
                         sum(1 for r in uncovered if r["excess"] <= 0) / len(uncovered), 3)
                     if uncovered else None,
                     "covered_loser_rate": round(
                         sum(1 for r in cov if r["excess"] <= 0) / len(cov), 3) if cov else None},
        "by_phase": table(cov, "phase"),
        "by_phase_slope": table(cov, "phase_slope"),
        "by_rs_tercile": table(cov, "rs_tercile"),
        "by_above200d": table(cov, "above200d"),
        "by_basket": {k: v for k, v in sorted(
            table(cov, "basket").items(), key=lambda kv: kv[1]["median_excess"] or 0)
            if v["n"] >= 5},
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({k: out[k] for k in ("coverage", "by_phase", "by_phase_slope",
                                          "by_rs_tercile", "by_above200d")}, indent=1))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
