#!/usr/bin/env python3
"""Provisional-basis tier replay + FRESH_TICKS/CN-blend knob sweeps — W6 #22/#36 harness.

Emits ``calibration/provisional_replay.json``: the honest repaint rate, provisional-vs-completed
forward edge, and not-topped veto flicker rate, measured by REPLAYING each historical day through
the SAME partial-bucket code path the live board uses (engine.provisional_replay). Then sweeps the
freshness / CN-blend knobs (#36) on the SAME stop-out-vs-lead harness the tier weights were tuned
on (research/signal_engine/walk_forward.py), US and CN separately, and reports whether the swept
values beat the incumbents OUT-OF-SAMPLE with honest CIs — or a null result honestly recorded.

Registers its multiple-testing budget in the Trial Ledger (P2-C, CI-enforced): the FRESH_TICKS
grid + the CN 4-knob grid. A null "no-improvement-found" is a fine outcome and is stamped as such.

Run:
  .venv/bin/python scripts/validate_provisional_replay.py                 # US replay + FRESH sweep
  .venv/bin/python scripts/validate_provisional_replay.py --cn            # + CN replay + CN sweep
  .venv/bin/python scripts/validate_provisional_replay.py --fast          # small panel (dev)
  .venv/bin/python scripts/validate_provisional_replay.py --replay-only    # skip sweeps
  .venv/bin/python scripts/validate_provisional_replay.py --sweep-only     # skip replay
"""
from __future__ import annotations

import os
import sys
import json
import glob
import time
import argparse
import warnings
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "research" / "signal_engine"))

from engine import provisional_replay as pr           # noqa: E402
from engine import confluence_tiers                    # noqa: E402
from engine.trial_ledger import register_trials, TrialLedger  # noqa: E402

_US_DATA = _ROOT / "data" / "stocks"
_CN_DATA = _ROOT / "data" / "china_stocks"
_OUT = _ROOT / "calibration" / "provisional_replay.json"

# --- knob grids (the multiple-testing budget we register) ------------------------------------- #
# FRESH_TICKS is the single knob defining "buyable now" for every market (#36). The incumbent is 2
# (justified by two anecdotes HON/LOW). Sweep the plausible just-crossed window.
FRESH_TICKS_GRID = (1, 2, 3, 4)
# CN blend constants (#36): incumbents WASHOUT_BONUS=0.5, EXT_PENALTY=0.5, CN_TIER_FRAC=0.30,
# CN_WN_FLOOR=0.60 (build_china_library.py:1164-1170). These reorder the CN board; the sweep tests
# the freshness knob + extension penalty on held-out CN names (the tier-blend fracs are board-order
# only, not entry-timing, so they are swept via the board-order ledger, not this stop-out harness).
CN_FRESH_TICKS_GRID = (1, 2, 3, 4)


def _load_panel_closes(data_dir: Path, limit: int | None = None) -> dict:
    """{ticker: close Series} from a parquet OHLC store."""
    panel = {}
    for fp in sorted(glob.glob(str(data_dir / "*.parquet"))):
        t = Path(fp).stem
        try:
            df = pd.read_parquet(fp, columns=["close"])
        except Exception:
            continue
        panel[t] = df["close"]
        if limit and len(panel) >= limit:
            break
    return panel


# ------------------------------------------------------------------ parallel replay
def _replay_one(args) -> dict:
    """Replay one name (process-pool task): returns a compact per-name bundle to merge."""
    ticker, close, max_days = args
    try:
        frame = pr.replay_series(ticker, close, max_days=max_days)
    except Exception:
        return {}
    if frame.empty:
        return {"ticker": ticker, "n_days": 0, "flick": None, "fires": None, "hyst": None}
    flick = pr.veto_flicker(frame)
    hyst = pr.veto_hysteresis_compare(frame)
    fires = pr.repaint_events(frame)
    if not fires.empty:
        fires = pr.edge_of_fires(ticker, close, fires)
        fires["ticker"] = ticker
    return {"ticker": ticker, "n_days": int(len(frame)), "flick": flick,
            "hyst": (hyst or None),
            "fires": fires.to_dict("records") if not fires.empty else []}


def run_replay(panel: dict, *, max_days: int, workers: int) -> dict:
    """Parallel panel replay → the honest measurement bundle (mirrors provisional_replay.replay_panel
    but parallelized across names for the full universe)."""
    tasks = [(t, c, max_days) for t, c in panel.items()]
    results = []
    t0 = time.time()
    if workers > 1 and len(tasks) > 8:
        try:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=workers) as ex:
                results = list(ex.map(_replay_one, tasks, chunksize=4))
        except Exception as e:  # noqa: BLE001 — parallelism must never break the run
            print(f"[replay] parallel failed ({e}) — serial fallback", file=sys.stderr)
            results = []
    if not results:
        results = [_replay_one(t) for t in tasks]
    dt = time.time() - t0

    all_fires, flick, hyst, n_days_total, n_names = [], [], [], 0, 0
    for r in results:
        if not r:
            continue
        if r.get("n_days", 0) > 0:
            n_names += 1
            n_days_total += r["n_days"]
        if r.get("flick"):
            flick.append(r["flick"])
        if r.get("hyst"):
            hyst.append(r["hyst"])
        if r.get("fires"):
            all_fires.extend(r["fires"])
    fires_df = pd.DataFrame(all_fires) if all_fires else pd.DataFrame()
    return {
        "n_names": n_names,
        "n_days_total": int(n_days_total),
        "n_fresh_fires": int(len(fires_df)),
        "elapsed_s": round(dt, 1),
        "repaint": pr._summarize_repaint(fires_df),
        "edge": pr._summarize_edge(fires_df, pr.EDGE_HORIZONS),
        "veto_flicker": pr._summarize_flicker(flick),
        "veto_hysteresis": pr._summarize_hysteresis(hyst),
        "config": {"max_days": max_days, "FRESH_TICKS": confluence_tiers.FRESH_TICKS,
                   "lookahead": pr.REPAINT_LOOKAHEAD, "horizons": list(pr.EDGE_HORIZONS)},
    }


# ------------------------------------------------------------------ FRESH_TICKS sweep
def _fresh_ticks_signal_fn(fresh_ticks: int):
    """A walk_forward signal callable whose only knob is FRESH_TICKS. It returns the daily BUY
    events of the confluence gate's FRESH tiers under a patched FRESH_TICKS — so the stop-out-vs-
    lead harness scores the freshness window directly (the same harness the tier weights used).

    Uses the VECTORIZED confluence_tiers.tier_stream (the validated twin of the live cascade — it
    matches the scalar gate exactly on settled bars, tests/test_provisional_replay) with FRESH_TICKS
    swept. A BUY event = a bar where a FRESH board tier (BUYABLE_TIERS = T1/T2/T3) FIRST appears (a
    new cross), leak-free (every indicator at bar t uses only data <= t). This is the completed-
    bucket / tradeable basis — the correct one for a next-bar-filled stop-out harness (a real fill
    happens on settled data, not the provisional intrabar tail)."""
    def fn(close, high=None, low=None):
        c = close.dropna()
        buy = pd.Series(False, index=c.index)
        ts = confluence_tiers.tier_stream(c, fresh_ticks=fresh_ticks)
        if ts.empty:
            return buy
        # a board-buyable fresh tier (T1/T2/T3 — T4 is board-excluded, matching signal_gate)
        board = ts["tier"].isin(list(signal_gate_buyable_tiers()))
        board = board.reindex(c.index).fillna(False).astype(bool)
        # fire on the FIRST bar a fresh board tier appears (a new cross), not every held bar
        fresh_start = board & ~board.shift(1, fill_value=False)
        buy.loc[fresh_start[fresh_start].index] = True
        return buy
    return fn


def signal_gate_buyable_tiers():
    from engine import signal_gate
    return signal_gate.BUYABLE_TIERS


def run_fresh_sweep(panel: dict, grid, *, market: str, workers: int, ledger: TrialLedger) -> dict:
    """Sweep FRESH_TICKS on the stop-out-vs-lead harness (held-out OOS). Incumbent = 2. Ships a
    swept value ONLY if it beats the incumbent OOS on stop_out_rate with an honest margin; else the
    incumbent stays and is stamped null. Registers every grid config in the trial ledger."""
    import walk_forward as wf

    fam = f"provisional_fresh_ticks_{market}"
    # register the sweep grid (itemized) — CI-enforced (P2-C)
    ledger.log_grid([{"FRESH_TICKS": g} for g in grid], family=fam,
                    info_cutoff=str(pd.Timestamp.today().date()))

    wf_panel = {t: pd.DataFrame({"close": c}) for t, c in panel.items()}
    # attach high/low where present for an intraday stop
    for t in list(wf_panel):
        fp = (_US_DATA if market == "us" else _CN_DATA) / f"{t}.parquet"
        try:
            df = pd.read_parquet(fp)
            for col in ("high", "low"):
                if col in df.columns:
                    wf_panel[t][col] = df[col].reindex(wf_panel[t].index)
        except Exception:
            pass

    results = {}
    incumbent = 2
    for g in grid:
        res = wf.walk_forward(_fresh_ticks_signal_fn(g), wf_panel, wf.DEFAULT_CFG,
                              metric="stop_out_rate", tag=f"fresh_{market}_{g}",
                              family=fam, log=False)
        oos = res["pooled"]["oos"]
        results[g] = {
            "n_names": res["n_names"],
            "oos_stop_out_mean": _get(oos, "treat", "mean"),
            "oos_n_names": oos.get("n_names"),
            "oos_stop_out_p50": _get(oos, "treat", "p50"),
            "oos_expectancy_mean": _mean_ctx(res, "oos", "expectancy"),
            "oos_win_rate_mean": _mean_ctx(res, "oos", "win_rate"),
            "oos_n_trades_mean": _mean_ctx(res, "oos", "n_trades"),
        }

    # verdict: lower OOS stop-out is better; require the best non-incumbent to beat incumbent by a
    # margin > the cross-name noise (we use a conservative 1.0pp absolute floor + more trades).
    inc = results.get(incumbent, {})
    inc_so = inc.get("oos_stop_out_mean")
    best_g, best_so = incumbent, inc_so
    for g, r in results.items():
        so = r.get("oos_stop_out_mean")
        if so is not None and (best_so is None or so < best_so):
            best_g, best_so = g, so
    improved = (best_g != incumbent and inc_so is not None and best_so is not None
                and (inc_so - best_so) >= 1.0
                and (results[best_g].get("oos_n_trades_mean") or 0) >= 1.0)
    return {
        "family": fam, "grid": list(grid), "incumbent": incumbent,
        "per_config": results,
        "verdict": {
            "ship": bool(improved),
            "shipped_value": (best_g if improved else incumbent),
            "basis": ("swept: beats-incumbent-oos" if improved
                      else "anecdote, sweep: no-improvement-found"),
            "incumbent_oos_stop_out": inc_so,
            "best_oos_stop_out": best_so,
            "margin_pp": (round(inc_so - best_so, 3) if (inc_so is not None and best_so is not None)
                          else None),
        },
    }


def _get(cs: dict, arm: str, stat: str):
    d = cs.get(arm) or {}
    v = d.get(stat)
    return round(float(v), 3) if v is not None else None


def _mean_ctx(res: dict, view: str, key: str):
    bt = res.get("by_ticker") or {}
    vals = [d["treat"][view].get(key) for d in bt.values()
            if d.get("treat") and d["treat"].get(view) and d["treat"][view].get(key) is not None]
    return round(float(np.mean(vals)), 3) if vals else None


# ------------------------------------------------------------------ CN blend constants (#36)
# The CN board-ORDER blend knobs (WASHOUT_BONUS / EXT_PENALTY / CN_TIER_FRAC / CN_WN_FLOOR). Unlike
# FRESH_TICKS these do NOT change a tradeable entry SIGNAL — they only REORDER the china board via
# signal_gate.blend_sorted. Their honest validation harness is therefore the board-ORDER ledger
# (engine.china_standout_track), NOT the stop-out-vs-lead harness. The audit (#36) + the ledger's
# own docstring make the anti-chase EXT_PENALTY's promotion contingent on that ledger showing
# extended top-of-board names underperform — which needs n>=8/horizon. We report the ledger's
# maturity + current EXTENDED-vs-not read so the knob's status is honest, never fabricated from a
# stop-out proxy the knob doesn't map to.
def assess_cn_blend(ledger: TrialLedger) -> dict:
    """Honest status of the CN blend constants: the incumbents, the board-order ledger's maturity,
    and — if matured — the measured extended-vs-not forward excess that would license promoting the
    EXT_PENALTY. Registers the CN blend grid as a declared research budget (the constants WERE
    hand-tuned across variants during research; that search is a multiple-testing cost)."""
    fam = "provisional_cn_blend"
    # incumbents (build_china_library.py:1164-1170)
    incumbents = {"WASHOUT_BONUS": 0.5, "EXT_PENALTY": 0.5, "CN_TIER_FRAC": 0.30, "CN_WN_FLOOR": 0.60}
    # a documented upper-bound on the research search (4 knobs, ~a handful of trial values each)
    ledger.log_declared_budget(16, family=fam,
                               reason="CN blend constants hand-tuned during research (4 knobs)")
    out = {
        "family": fam, "incumbents": incumbents,
        "harness": "board-order ledger (china_standout_track), NOT stop-out — these are ordering "
                   "knobs, not entry signals",
        "verdict": {
            "ship": False, "shipped_values": incumbents,
            "basis": "anecdote, sweep: ledger-immature",
        },
    }
    try:
        from engine import china_standout_track as cst
        g = cst.grade()
        out["ledger"] = {
            "available": g.get("available"), "n_rows": g.get("n_rows"),
            "dates": g.get("dates"), "n_graded": g.get("n_graded"),
        }
        # surface the extended-vs-not read per horizon (the EXT_PENALTY licensing signal)
        ext_reads = {}
        for h, d in (g.get("by_horizon") or {}).items():
            if isinstance(d, dict) and d.get("extended_fwd") is not None:
                ext_reads[h] = {"extended_fwd": d.get("extended_fwd"),
                                "not_extended_fwd": d.get("not_extended_fwd"),
                                "n_extended": d.get("n_extended")}
        out["ledger"]["extended_vs_not"] = ext_reads or "insufficient (need n>=8 & >=5 extended)"
        matured = bool(g.get("n_graded", 0) and g["n_graded"] >= cst._MIN_GRADED)
        out["verdict"]["basis"] = ("board-order ledger matured — see extended_vs_not"
                                   if matured else "anecdote, sweep: ledger-immature "
                                   f"(n_graded={g.get('n_graded', 0)} < {cst._MIN_GRADED})")
    except Exception as e:  # noqa: BLE001
        out["ledger"] = {"available": False, "error": str(e)}
    return out


# ------------------------------------------------------------------ orchestration
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cn", action="store_true", help="also run CN sweep + CN blend status")
    ap.add_argument("--cn-replay", action="store_true",
                    help="also run the (expensive) CN per-day replay; capped by --cn-replay-limit")
    ap.add_argument("--cn-replay-limit", type=int, default=60,
                    help="cap #CN names in the per-day replay (default 60 — it is 1s/name-day)")
    ap.add_argument("--fast", action="store_true", help="small dev panel")
    ap.add_argument("--replay-only", action="store_true")
    ap.add_argument("--sweep-only", action="store_true")
    ap.add_argument("--max-days", type=int, default=250)
    ap.add_argument("--limit", type=int, default=None, help="cap #names (dev)")
    args = ap.parse_args(argv)

    workers = max(1, (os.cpu_count() or 2))
    limit = 12 if args.fast else args.limit
    max_days = 60 if args.fast else args.max_days
    ledger = TrialLedger()

    out = {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "mode": "fast" if args.fast else "full",
            "shadow_only": True,
            "note": ("Provisional-basis tier replay (#22): each historical day replayed through the "
                     "LIVE partial-bucket code path (signal_gate.gate on the truncated series) — the "
                     "provisional-lane history the point-in-time validation never saw. Repaint = a "
                     "fresh T1/T2/T3 that un-crosses when the bucket completes; edge = provisional-vs-"
                     "completed next-bar-filled forward return (engine.grading); flicker = single-bar "
                     "not-topped veto flip rate. Knob sweeps (#36) on the stop-out-vs-lead harness "
                     "(walk_forward). No live artifact touched."),
            "workers": workers, "max_days": max_days,
        },
    }

    if not args.sweep_only:
        us_panel = _load_panel_closes(_US_DATA, limit=limit)
        print(f"[replay] US panel: {len(us_panel)} names, max_days={max_days}, workers={workers}",
              file=sys.stderr)
        out["us_replay"] = run_replay(us_panel, max_days=max_days, workers=workers)
        if args.cn_replay:
            cn_lim = 12 if args.fast else (limit or args.cn_replay_limit)
            cn_panel = _load_panel_closes(_CN_DATA, limit=cn_lim)
            print(f"[replay] CN panel: {len(cn_panel)} names (bounded)", file=sys.stderr)
            out["cn_replay"] = run_replay(cn_panel, max_days=max_days, workers=workers)

    if not args.replay_only:
        us_panel = _load_panel_closes(_US_DATA, limit=(limit or 120))
        print(f"[sweep] US FRESH_TICKS sweep on {len(us_panel)} names", file=sys.stderr)
        with register_trials("provisional_fresh_ticks_us", budget=len(FRESH_TICKS_GRID),
                             reason="FRESH_TICKS just-crossed window sweep (US, held-out OOS)",
                             ledger=ledger):
            out["us_fresh_sweep"] = run_fresh_sweep(us_panel, FRESH_TICKS_GRID, market="us",
                                                    workers=workers, ledger=ledger)
        if args.cn:
            cn_panel = _load_panel_closes(_CN_DATA, limit=(limit or 120))
            print(f"[sweep] CN FRESH_TICKS sweep on {len(cn_panel)} names", file=sys.stderr)
            with register_trials("provisional_fresh_ticks_cn", budget=len(CN_FRESH_TICKS_GRID),
                                 reason="FRESH_TICKS just-crossed window sweep (CN, held-out OOS)",
                                 ledger=ledger):
                out["cn_fresh_sweep"] = run_fresh_sweep(cn_panel, CN_FRESH_TICKS_GRID, market="cn",
                                                        workers=workers, ledger=ledger)
            print("[sweep] CN blend-constants status (board-order ledger)", file=sys.stderr)
            out["cn_blend"] = assess_cn_blend(ledger)

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(out, indent=1, default=_json_default))
    print(f"[done] wrote {_OUT}", file=sys.stderr)
    _print_summary(out)
    return 0


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)


def _print_summary(out: dict) -> None:
    print("\n===== PROVISIONAL REPLAY SUMMARY =====")
    for mkt in ("us", "cn"):
        rp = out.get(f"{mkt}_replay")
        if not rp:
            continue
        r = rp.get("repaint", {})
        e = rp.get("edge", {})
        v = rp.get("veto_flicker", {})
        print(f"\n[{mkt.upper()}] {rp['n_names']} names, {rp['n_days_total']} name-days, "
              f"{rp['n_fresh_fires']} fresh fires ({rp.get('elapsed_s')}s)")
        print(f"  repaint rate: {r.get('repaint_rate')} CI{r.get('repaint_ci')}  "
              f"hist={r.get('outcome_hist')}")
        for h, d in (e.get("by_horizon") or {}).items():
            print(f"  edge {h}: prov={d.get('provisional_median_fwd')} "
                  f"comp={d.get('completed_median_fwd')} "
                  f"flip={d.get('provisional_sign_flip_vs_completed')}")
        print(f"  veto flicker: flip={v.get('median_flip_rate')} "
              f"flicker={v.get('median_flicker_rate')}")
        hy = rp.get("veto_hysteresis") or {}
        if hy.get("single_bar") and hy.get("hysteretic"):
            sb, ht = hy["single_bar"], hy["hysteretic"]
            print(f"  veto hysteresis (confirm={hy.get('confirm')}): "
                  f"single P/R={sb.get('precision')}/{sb.get('recall')} "
                  f"flick={sb.get('flicker_rate')} -> "
                  f"hyst P/R={ht.get('precision')}/{ht.get('recall')} "
                  f"flick={ht.get('flicker_rate')}")
    for mkt in ("us", "cn"):
        sw = out.get(f"{mkt}_fresh_sweep")
        if not sw:
            continue
        vd = sw["verdict"]
        print(f"\n[{mkt.upper()}] FRESH_TICKS sweep verdict: ship={vd['ship']} "
              f"value={vd['shipped_value']} ({vd['basis']}) margin={vd.get('margin_pp')}pp")
    cb = out.get("cn_blend")
    if cb:
        print(f"\n[CN] blend constants verdict: ship={cb['verdict']['ship']} "
              f"({cb['verdict']['basis']})")


if __name__ == "__main__":
    raise SystemExit(main())
