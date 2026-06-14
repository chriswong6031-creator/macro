"""Integration A/B lab — does adding a factor to the risk/allocation model survive
the house discipline (both-halves robustness + multi-regime, net of cost)?

This is the empirical gate every candidate factor must clear BEFORE it is wired
into the scoring path (per [[institutional-grade-roadmap]] and the macro-gate
rejection precedent). It exists for two reasons:
  1. a permanent "integration candidates" report (run each calibration) that
     re-checks shallow-history factors as their history deepens; and
  2. an importable / CLI instrument so an A/B can be specified declaratively.

A candidate is one of:
  {"type":"alloc_floor", "cond":"funding_z<-1|oi_price_divergence<-0.10", "to":0.5}
  {"type":"alloc_cap",   "cond":"etf_flow_state==distribution",            "to":0.5}
  {"type":"risk_reweight","weights":{"etf_outflow":1.0}}        # recompute risk_index
The condition mini-DSL: `col OP val` (OP in < > <= >= ==), joined by | (or) / & (and).
String equality uses ==, e.g. etf_flow_state==accumulation.

VERDICT logic encodes the discipline:
  REJECT            full-sample net Sharpe drops materially
  CONFIRMATION-ONLY helps but has NO pre-2021 footprint (shallow data — cannot
                    clear the both-halves bar by construction; keep as context)
  REGIME-CONCENTRATED helps full-sample but the gain sits in a single post-2021
                    regime (the overfit trap)
  ELIGIBLE          helps and is robust across >=2 distinct regimes incl. a
                    pre-2021 footprint that doesn't hurt
"""
from __future__ import annotations

import copy
import json
import re
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from lib import config
from scripts.calibrate_vector import backtest

SIG_PATH = "data/vector/signals.parquet"
SPLIT = "2021-01-01"
ETF_START = "2024-01-11"
COST_BPS = 10
# distinct post-2021 regimes for the concentration test (bear / recovery / chop)
REGIMES = [("2022_bear", "2022-01-01", "2023-01-01"),
           ("2023_24_recovery", "2023-01-01", "2025-01-01"),
           ("2025_26", "2025-01-01", None)]

_CMP = re.compile(r"^\s*([\w.]+)\s*(<=|>=|==|<|>)\s*(.+?)\s*$")
_FRAME = None
_INPUTS = None


def _frame() -> pd.DataFrame:
    global _FRAME
    if _FRAME is None:
        _FRAME = pd.read_parquet(SIG_PATH)
    return _FRAME


def _inputs():
    global _INPUTS
    if _INPUTS is None:
        from engine import btc_inputs
        _INPUTS = btc_inputs.load_all()
    return _INPUTS


def _cond(sig: pd.DataFrame, expr: str) -> pd.Series:
    """Parse `col<v|col>v&col==s` into a boolean mask aligned to sig.index."""
    out = None
    for orpart in expr.split("|"):
        andmask = None
        for andpart in orpart.split("&"):
            m = _CMP.match(andpart)
            if not m:
                raise ValueError(f"bad condition: {andpart!r}")
            col, op, val = m.group(1), m.group(2), m.group(3)
            if col not in sig.columns:
                raise KeyError(f"unknown column: {col}")
            s = sig[col]
            if op == "==":
                mask = (s == val)
            else:
                v = float(val)
                mask = {"<": s < v, ">": s > v, "<=": s <= v, ">=": s >= v}[op]
            mask = mask.fillna(False)
            andmask = mask if andmask is None else (andmask & mask)
        out = andmask if out is None else (out | andmask)
    return out


def _base_raw_valued(sig: pd.DataFrame, acfg: dict):
    """The current `optimal` allocation, pre-confirm, with the valuation overlay
    applied — the canonical base every overlay candidate forks from."""
    mom, risk = sig["momentum"], sig["risk_index"]
    v = acfg["variants"]["optimal"]
    full = (mom > v["mom_full"]) & (risk < v["risk_full"])
    half = (mom > v["mom_half"]) & (risk < v["risk_half"])
    raw = pd.Series(np.where(full, 1.0, np.where(half, 0.5, 0.0)), index=sig.index)
    dv = ((sig.get("mvrv_z", np.nan) < acfg["deep_value_z"])
          | (sig.get("nupl", np.nan) < acfg["deep_value_nupl"])).fillna(False)
    ov = ((sig.get("mayer", np.nan) > acfg["overvalued_mayer"])
          | (sig.get("reserve_risk", np.nan) > acfg["overvalued_rr"])).fillna(False)
    return raw.mask(dv, raw.clip(lower=0.5)).mask(ov, raw.clip(upper=0.5))


def _confirmed(raw: pd.Series, acfg: dict) -> pd.Series:
    from engine.btc_signals import _confirm
    return _confirm(raw, acfg["confirm_days"])


def base_alloc() -> pd.Series:
    cfg = config.load()["vector"]
    return _confirmed(_base_raw_valued(_frame(), cfg["allocation"]), cfg["allocation"])


def candidate_alloc(spec: dict) -> pd.Series:
    sig = _frame()
    cfg = config.load()["vector"]
    acfg = cfg["allocation"]
    t = spec["type"]
    if t in ("alloc_floor", "alloc_cap", "alloc_full"):
        raw = _base_raw_valued(sig, acfg).copy()
        mask = _cond(sig, spec["cond"])
        to = spec.get("to", 1.0 if t == "alloc_full" else 0.5)
        if t == "alloc_cap":
            raw = raw.mask(mask, raw.clip(upper=to))
        else:
            raw = raw.mask(mask, raw.clip(lower=to))
        return _confirmed(raw, acfg)
    if t == "risk_reweight":
        from engine.btc_signals import allocation, risk
        rcfg = copy.deepcopy(cfg["risk"])
        rcfg["weights"] = {**rcfg["weights"], **spec["weights"]}
        mom = sig["momentum"]
        rk = risk(_inputs(), mom, rcfg)["risk_index"].reindex(sig.index)
        valcols = [c for c in ("mvrv_z", "nupl", "mayer", "reserve_risk") if c in sig]
        al = allocation(mom, rk, acfg, sig[valcols])
        return al["alloc_optimal"]
    raise ValueError(f"unknown candidate type: {t}")


def _slice(close, alloc, lo, hi):
    m = pd.Series(True, index=close.index)
    if lo:
        m &= close.index >= lo
    if hi:
        m &= close.index < hi
    return close[m], alloc[m]


def _metrics(close, alloc, lo=None, hi=None) -> dict:
    c, a = _slice(close, alloc, lo, hi)
    if len(c) < 60:
        return {}
    r = backtest(c, a, COST_BPS)
    return {k: r[k] for k in ("cagr", "sharpe", "sortino", "maxdd",
                              "turnover_annual", "time_in_market")}


def evaluate(spec: dict) -> dict:
    """Backtest base vs candidate across full/halves/regimes; emit a verdict."""
    sig = _frame()
    close = sig["close"]
    base = base_alloc()
    alloc = candidate_alloc(spec)
    periods = [("full", None, None), ("pre2021", None, SPLIT),
               ("post2021", SPLIT, None), ("etf_era", ETF_START, None)]
    rows, deltas = {}, {}
    for name, lo, hi in periods + [(n, lo, hi) for n, lo, hi in REGIMES]:
        b, c = _metrics(close, base, lo, hi), _metrics(close, alloc, lo, hi)
        if b and c:
            rows[name] = {"base": b, "cand": c}
            deltas[name] = round(c["sharpe"] - b["sharpe"], 3)
    pre_footprint = bool(((alloc != base) & (sig.index < pd.Timestamp(SPLIT))).any())
    reg_deltas = [deltas.get(n) for n, _, _ in REGIMES if deltas.get(n) is not None]
    reg_pos = sum(1 for d in reg_deltas if d > 0.02)
    full_d = deltas.get("full", 0.0)
    pre_d = deltas.get("pre2021")
    if full_d < -0.02:
        verdict = "REJECT (hurts net Sharpe full-sample)"
    elif full_d <= 0.02 and reg_pos == 0:
        verdict = "NEUTRAL / no edge"
    elif not pre_footprint:
        verdict = "CONFIRMATION-ONLY (no pre-2021 footprint — keep as context/risk input)"
    elif reg_pos >= 2 and (pre_d is None or pre_d >= -0.02):
        verdict = "ELIGIBLE (multi-regime + both-halves)"
    else:
        verdict = "REGIME-CONCENTRATED (the overfit trap — do not hard-wire)"
    return {"spec": spec, "verdict": verdict, "sharpe_delta": deltas,
            "pre2021_footprint": pre_footprint, "regimes_positive": reg_pos,
            "detail": rows}


# default candidate panel — the standing "integration candidates" report
PANEL = [
    {"type": "alloc_floor", "cond": "funding_z<-1|oi_price_divergence<-0.10", "to": 0.5},
    {"type": "alloc_floor", "cond": "funding_z<-1", "to": 0.5},
    {"type": "alloc_floor", "cond": "vrp<-5", "to": 0.5},
    {"type": "alloc_floor", "cond": "coinbase_premium_ema<-0.3", "to": 0.5},
    {"type": "alloc_floor", "cond": "etf_flow_state==accumulation", "to": 0.5},
    {"type": "alloc_cap", "cond": "etf_flow_state==distribution", "to": 0.5},
    {"type": "alloc_cap", "cond": "cot_z>1.5", "to": 0.5},
    {"type": "alloc_cap", "cond": "leverage_stress>75", "to": 0.5},
    {"type": "risk_reweight", "weights": {"etf_outflow": 1.0}},
]


def _fmt(d: dict) -> str:
    return (f"CAGR {d['cagr']:6.1f}  Sh {d['sharpe']:5.2f}  Sort {d['sortino']:5.2f}  "
            f"MDD {d['maxdd']:6.1f}  turn {d['turnover_annual']:4.1f}")


def write_report(reports_dir: str = "reports") -> str:
    """Standing 'integration candidates' report — re-run each calibration so shallow
    factors get re-checked as their history deepens. A candidate graduates from
    CONFIRMATION-ONLY to ELIGIBLE only when it earns a pre-2021 footprint that
    survives the multi-regime A/B."""
    from pathlib import Path
    base, stored = base_alloc(), _frame()["alloc_optimal"]
    agree = (base.round(2) == stored.round(2)).mean()
    L = ["# Vector — Integration Candidates", "",
         f"_Empirical gate for wiring a factor into the risk/allocation **math**: it must "
         f"survive a both-halves + multi-regime A/B, net of {COST_BPS}bps. Display/context "
         f"use needs no such gate. Auto-generated by `scripts/integration_lab.py`._", "",
         f"Harness self-check — replicated base vs stored `alloc_optimal`: **{agree:.3f}** agreement.", "",
         "| candidate | verdict | ΔSharpe full | pre21 | post21 | etf-era | regimes+ |",
         "|---|---|---:|---:|---:|---:|:--:|"]
    for spec in PANEL:
        r = evaluate(spec)
        label = spec.get("cond") or json.dumps(spec.get("weights"))
        d = r["sharpe_delta"]
        L.append(f"| `{spec['type']}` {label} | {r['verdict']} | {d.get('full'):+.3f} | "
                 f"{d.get('pre2021')} | {d.get('post2021')} | {d.get('etf_era')} | "
                 f"{r['regimes_positive']}/3 |")
    L += ["", "**Reading.** ELIGIBLE → hard-wire it. CONFIRMATION-ONLY → keep as a context "
          "signal / risk-index input only (no pre-2021 footprint ⇒ cannot clear the both-halves "
          "bar by construction). REGIME-CONCENTRATED / REJECT → the overfit trap; do not blend."]
    out = Path(reports_dir) / "vector-integration-candidates.md"
    out.write_text("\n".join(L) + "\n")
    return str(out)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if argv:  # JSON candidate (object) or batch (array) -> JSON result(s)
        spec = json.loads(argv[0])
        if isinstance(spec, list):  # batch: one process, shared frame/inputs cache
            out = []
            for s in spec:
                try:
                    out.append(evaluate(s))
                except Exception as e:  # noqa: BLE001 — report, don't abort the batch
                    out.append({"spec": s, "verdict": f"ERROR: {e}"})
            print(json.dumps(out, default=str))
        else:
            print(json.dumps(evaluate(spec), default=str))
        return 0
    print(f"INTEGRATION CANDIDATES REPORT — base = optimal, net {COST_BPS}bps\n"
          f"(verdict gate: both-halves + multi-regime robustness)\n")
    base = base_alloc()
    stored = _frame()["alloc_optimal"]
    print(f"harness check — base vs stored alloc_optimal agreement: "
          f"{(base.round(2) == stored.round(2)).mean():.3f}\n")
    for spec in PANEL:
        r = evaluate(spec)
        label = spec.get("cond") or json.dumps(spec.get("weights"))
        print(f"• {spec['type']:13s} {label}")
        print(f"    VERDICT: {r['verdict']}")
        print(f"    Sharpe Δ: full {r['sharpe_delta'].get('full'):+.3f} | "
              f"pre21 {r['sharpe_delta'].get('pre2021')} | "
              f"post21 {r['sharpe_delta'].get('post2021'):+.3f} | "
              f"etf {r['sharpe_delta'].get('etf_era')} | "
              f"regimes+ {r['regimes_positive']}/3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
