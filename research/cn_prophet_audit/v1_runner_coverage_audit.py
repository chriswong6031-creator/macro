"""China Prophet V1 era missed-winner coverage — the CN mirror of
research/prophet_us_audit/runner_exclusion_audit.py.

MEASUREMENT INSTRUMENT, not a signal. Over the V1 board era (2026-06-30 →
2026-07-29): rank the full china_stocks universe by era return, then classify
every top runner's relationship to the board:

  caught          — had >=1 V1 board episode during the era
  eligible_missed — never boarded, but signal_gate.gate() (the production CN
                    cascade) printed an eligible T1-T3 verdict on >=1 era board
                    date (PIT close-truncated) — lost to the alignment
                    inclusion gate, the top-60 cut, or ranking
  never_eligible  — no eligible cascade day across the era board dates
                    (structural origination miss for this detector family)

Also freezes the admission-shape of each cohort (trailing 21/63d return and
drawdown-from-high at the run start) so the improvement plan can name which
DOOR (washout / continuation / rotation) each missed cohort needs.

Run from repo root:  python3 research/cn_prophet_audit/v1_runner_coverage_audit.py
Output: research/cn_prophet_audit/v1_runner_coverage_results.json (frozen)
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine import china_standout_track as cst  # noqa: E402
from engine import signal_gate  # noqa: E402
from engine import track_scoring as ts  # noqa: E402

ERA_START, ERA_END = "2026-06-30", "2026-07-29"
TOP_N = 150
OUT = Path(__file__).parent / "v1_runner_coverage_results.json"


def pct(a, nd=4):
    try:
        f = float(a)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if np.isfinite(f) else None


def main() -> None:
    board = pd.read_parquet(ROOT / "data/china_standout_track/board.parquet")
    board = board[board["board_definition"] == "legacy"]
    board_days: dict[str, set[str]] = defaultdict(set)
    for _, r in board.iterrows():
        board_days[str(r["date"])].add(str(r["ticker"]))
    era_dates = sorted(board_days)
    boarded = {e["ticker"] for e in ts.build_episodes(board_days)}

    led = json.loads((ROOT / "site/factordata/cn_track_ledger.json").read_text())
    sec_by = {r["t"]: r.get("sec") for r in led["prior_record"]["rows"]}
    nm_by = {r["t"]: r.get("nm") for r in led["prior_record"]["rows"]}

    t0, t1 = pd.Timestamp(ERA_START), pd.Timestamp(ERA_END)
    stocks_dir = ROOT / "data/china_stocks"
    runners = []
    for p in sorted(stocks_dir.glob("*.parquet")):
        tk = p.stem
        try:
            pdf = pd.read_parquet(p)
        except Exception:  # noqa: BLE001
            continue
        c = pd.to_numeric(pdf.get("close"), errors="coerce").dropna()
        if len(c) < 200:
            continue
        win = c[(c.index >= t0) & (c.index <= t1)]
        if len(win) < 15:
            continue
        era_ret = float(win.iloc[-1] / win.iloc[0] - 1.0)
        hist = c[c.index <= t0]
        start_char = {}
        if len(hist) > 64:
            s0 = float(hist.iloc[-1])
            start_char = {
                "trail_21_at_start": pct(s0 / float(hist.iloc[-22]) - 1.0),
                "trail_63_at_start": pct(s0 / float(hist.iloc[-64]) - 1.0),
                "dd_from_high_at_start": pct(
                    s0 / float(hist.iloc[-252:].max()) - 1.0),
            }
        runners.append({"ticker": tk, "era_ret": pct(era_ret), "close": c, **start_char})

    runners.sort(key=lambda r: -(r["era_ret"] or 0))
    top = runners[:TOP_N]
    print(f"universe evaluated={len(runners)}; top{TOP_N} era_ret "
          f"{top[-1]['era_ret']:.3f}..{top[0]['era_ret']:.3f}")

    results = []
    for i, r in enumerate(top):
        tk, c = r["ticker"], r.pop("close")
        status = "caught" if tk in boarded else None
        eligible_days = 0
        first_eligible = None
        last_verdict = None
        if status is None:
            for d in era_dates:
                cut = c[c.index <= pd.Timestamp(d)]
                if len(cut) < 200:
                    continue
                try:
                    v = signal_gate.gate(tk, cut)
                except Exception:  # noqa: BLE001
                    continue
                last_verdict = v
                if v.get("eligible") and v.get("tier_cascade") in ("T1", "T2", "T3"):
                    eligible_days += 1
                    if first_eligible is None:
                        first_eligible = d
            status = "eligible_missed" if eligible_days else "never_eligible"
        results.append({
            **{k: v for k, v in r.items()},
            "name": nm_by.get(tk),
            "sector": sec_by.get(tk),
            "status": status,
            "eligible_days": eligible_days if status != "caught" else None,
            "first_eligible": first_eligible,
            "last_reason": (last_verdict or {}).get("reason")
            if status == "never_eligible" else None,
        })
        if (i + 1) % 25 == 0:
            print(f"  …{i + 1}/{TOP_N}")

    by_status = Counter(r["status"] for r in results)

    def shape(rows):
        def med(key):
            vals = [r[key] for r in rows if r.get(key) is not None]
            return pct(float(np.median(vals))) if vals else None
        return {"n": len(rows),
                "median_trail_21_at_start": med("trail_21_at_start"),
                "median_trail_63_at_start": med("trail_63_at_start"),
                "median_dd_from_high_at_start": med("dd_from_high_at_start"),
                "median_era_ret": med("era_ret")}

    cohorts = {s: shape([r for r in results if r["status"] == s])
               for s in ("caught", "eligible_missed", "never_eligible")}
    reasons = Counter(r["last_reason"] for r in results
                      if r["status"] == "never_eligible")

    out = {
        "as_of": "2026-08-03",
        "era": [ERA_START, ERA_END],
        "universe_n": len(runners),
        "top_n": TOP_N,
        "by_status": dict(by_status),
        "cohort_shapes": cohorts,
        "never_eligible_last_reasons": dict(reasons),
        "runners": [{k: v for k, v in r.items()} for r in results],
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({k: out[k] for k in ("by_status", "cohort_shapes",
                                          "never_eligible_last_reasons")}, indent=1))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
