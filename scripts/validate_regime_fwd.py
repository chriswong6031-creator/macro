"""Forward-regime grading gate — audit #16, masterplan W2.

The base-effect + causal-HMM forward suite (engine/base_effect.py, engine/regime_one.py)
was shipped DISPLAY-ONLY "until scripts/validate_regime_fwd.py clears it" — and that
validator was never written (the whole point of #16). This is it.

It does four things, all SHADOW (touches no live decision path):

  1. MATURE — walk the forward-grading ledgers and fill each row's realized_* fields
     once the horizon has elapsed, reading the realized axis outcome from the committed
     regime history (data/regime/regime_history.parquet) + the base_effect YoY paths.
       * base_effect_fwd.jsonl : predicted base-forced accel sign (q1) vs the realized
         sign of the axis-score change over +63 bdays (the 2nd-derivative call).
       * regime_fwd_hmm.jsonl  : predicted causal-filtered modal quad vs the realized
         legacy quad at +21 bdays.
  2. GRADE — hit-rate of the matured calls, with WILSON confidence intervals so the
     interim (small-n) uncertainty is honest, not a point estimate on n=3.
  3. GO/NO-GO — a call is GRADEABLE only once n_matured >= MIN_GRADE_N AND the Wilson
     lower bound clears 0.5 (better than a coin flip on the axis sign). Until then the
     verdict is ACCRUING with a distance-to-decision. Nothing promotes on this run;
     the summary is written to calibration/regime_fwd_grade.json.
  4. revised=False on the SHADOW base_effect path — with the #809 vintage backfill,
     base_effect.compute(as_of, vintages) can now read CPI (1997+), PCE (2000+),
     PPI (2014+) leak-free. This script verifies the PIT path resolves and reports the
     revised flag it achieves, threading as_of + vintages properly (run.py currently
     passes neither, so its base_effect silently falls back to revised=True — #16).

Run:  python -m scripts.validate_regime_fwd            # mature + grade + summary
      python -m scripts.validate_regime_fwd --accrue   # also append today's HMM call
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

BE_HORIZON_BD = 63     # base_effect 2nd-derivative call horizon (one quarter)
HMM_HORIZON_BD = 21    # causal-HMM quad call horizon (one month)
MIN_GRADE_N = 20       # matured rows before a go/no-go verdict is even attempted


# --------------------------------------------------------------------------- #
# Wilson interval (accrual-aware, honest small-n uncertainty)
# --------------------------------------------------------------------------- #
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Wilson score interval for a binomial proportion. Returns (lo, phat, hi).
    Degrades gracefully at n=0 -> (0, 0, 1)."""
    if n <= 0:
        return 0.0, 0.0, 1.0
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return round(max(0.0, centre - half), 4), round(phat, 4), round(min(1.0, centre + half), 4)


# --------------------------------------------------------------------------- #
# Realized axis outcomes from the committed history
# --------------------------------------------------------------------------- #
def _axis_scores() -> pd.DataFrame | None:
    p = config.data_dir() / "regime" / "regime_history.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def _realized_accel_sign(hist: pd.DataFrame, axis: str, asof: pd.Timestamp,
                         horizon_bd: int) -> int | None:
    """Realized sign of the axis-score CHANGE over the horizon — the 2nd-derivative
    call base_effect makes (is the rate accelerating or decelerating). None if the
    horizon hasn't elapsed in the committed history."""
    col = f"{axis}_score"
    if col not in hist.columns:
        return None
    idx = hist.index
    if asof not in idx:
        pos = idx.searchsorted(asof)
        if pos >= len(idx):
            return None
        asof = idx[pos]
    start = idx.get_loc(asof)
    end = start + horizon_bd
    if end >= len(idx):
        return None
    a, b = hist[col].iloc[start], hist[col].iloc[end]
    if pd.isna(a) or pd.isna(b):
        return None
    d = float(b) - float(a)
    return int((d > 0) - (d < 0))


def _realized_quad(hist: pd.DataFrame, asof: pd.Timestamp, horizon_bd: int) -> str | None:
    if "quad" not in hist.columns:
        return None
    idx = hist.index
    if asof not in idx:
        pos = idx.searchsorted(asof)
        if pos >= len(idx):
            return None
        asof = idx[pos]
    end = idx.get_loc(asof) + horizon_bd
    if end >= len(idx):
        return None
    q = hist["quad"].iloc[end]
    return None if pd.isna(q) else str(q)


# --------------------------------------------------------------------------- #
# Mature the ledgers
# --------------------------------------------------------------------------- #
def _load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
    return rows


def _write_jsonl(p: Path, rows: list[dict]) -> None:
    p.write_text("\n".join(json.dumps(r, default=str) for r in rows) + ("\n" if rows else ""))


def mature_base_effect(hist: pd.DataFrame) -> tuple[int, int]:
    p = config.data_dir() / "regime" / "base_effect_fwd.jsonl"
    rows = _load_jsonl(p)
    filled = 0
    for r in rows:
        asof = pd.Timestamp(r["asof"])
        for axis, key in (("growth", "realized_growth_2d_at_63d"),
                          ("inflation", "realized_infl_2d_at_63d")):
            if r.get(key) is None:
                rv = _realized_accel_sign(hist, axis, asof, BE_HORIZON_BD)
                if rv is not None:
                    r[key] = rv
                    filled += 1
    if filled:
        _write_jsonl(p, rows)
    n_matured = sum(1 for r in rows if r.get("realized_growth_2d_at_63d") is not None
                    and r.get("realized_infl_2d_at_63d") is not None)
    return len(rows), n_matured


def mature_hmm(hist: pd.DataFrame) -> tuple[int, int]:
    p = config.data_dir() / "regime" / "regime_fwd_hmm.jsonl"
    rows = _load_jsonl(p)
    filled = 0
    for r in rows:
        if r.get("realized_quad_at_21d") is None:
            rv = _realized_quad(hist, pd.Timestamp(r["asof"]), HMM_HORIZON_BD)
            if rv is not None:
                r["realized_quad_at_21d"] = rv
                filled += 1
    if filled:
        _write_jsonl(p, rows)
    n_matured = sum(1 for r in rows if r.get("realized_quad_at_21d") is not None)
    return len(rows), n_matured


def accrue_hmm_row() -> bool:
    """Append today's causal-filtered modal-quad call to regime_fwd_hmm.jsonl (idempotent
    per session). Delegates to engine.regime_one.accrue_hmm_row (the engine owns the
    ledger convention; this script only wires it into the grading run)."""
    from engine.regime_one import accrue_hmm_row as _engine_accrue
    return _engine_accrue()


# --------------------------------------------------------------------------- #
# Grade
# --------------------------------------------------------------------------- #
def grade_base_effect() -> dict:
    p = config.data_dir() / "regime" / "base_effect_fwd.jsonl"
    rows = _load_jsonl(p)
    out = {}
    for axis, pred_key, real_key in (("growth", "be_growth_2d_q1", "realized_growth_2d_at_63d"),
                                     ("inflation", "be_infl_2d_q1", "realized_infl_2d_at_63d")):
        matured = [r for r in rows if r.get(real_key) is not None and r.get(pred_key) is not None]
        # a call is a HIT if the predicted accel sign matches the realized sign
        # (ignore the pred==0 flat calls — no directional claim to grade).
        directional = [r for r in matured if r[pred_key] != 0]
        hits = sum(1 for r in directional if r[pred_key] == r[real_key])
        n = len(directional)
        lo, phat, hi = wilson(hits, n)
        out[axis] = {"n_total_rows": len(rows), "n_matured": len(matured),
                     "n_directional": n, "hits": hits,
                     "hit_rate": phat, "wilson_lo": lo, "wilson_hi": hi,
                     "horizon_bd": BE_HORIZON_BD}
    return out


def grade_hmm() -> dict:
    p = config.data_dir() / "regime" / "regime_fwd_hmm.jsonl"
    rows = _load_jsonl(p)
    matured = [r for r in rows if r.get("realized_quad_at_21d") is not None]
    hits = sum(1 for r in matured if r.get("pred_modal_quad") == r["realized_quad_at_21d"])
    n = len(matured)
    lo, phat, hi = wilson(hits, n)
    return {"n_total_rows": len(rows), "n_matured": n, "hits": hits,
            "hit_rate": phat, "wilson_lo": lo, "wilson_hi": hi,
            "horizon_bd": HMM_HORIZON_BD,
            "note": "causal-filtered modal quad vs realized quad at +21bd"}


def _verdict(n_matured: int, wilson_lo: float, baseline: float = 0.5) -> dict:
    if n_matured < MIN_GRADE_N:
        return {"status": "accruing", "gradeable": False,
                "distance_to_decision": MIN_GRADE_N - n_matured,
                "reason": f"only {n_matured}/{MIN_GRADE_N} matured rows; "
                          f"~{MIN_GRADE_N - n_matured} more sessions to a first verdict"}
    if wilson_lo > baseline:
        return {"status": "go", "gradeable": True,
                "reason": f"Wilson lower bound {wilson_lo:.2f} > {baseline} baseline"}
    return {"status": "no-go", "gradeable": True,
            "reason": f"Wilson lower bound {wilson_lo:.2f} does not clear {baseline} — "
                      f"cannot reject coin-flip; stays display-only"}


# --------------------------------------------------------------------------- #
# revised=False PIT verification for base_effect (the #16/#809 unblock)
# --------------------------------------------------------------------------- #
def check_base_effect_pit() -> dict:
    """Verify base_effect can now run leak-free on the inflation legs (CPI/PCE/PPI) via
    the #809 vintage backfill: build with as_of + loaded vintages and report the revised
    flag it achieves. run.py's live call passes NEITHER (silent revised=True fallback);
    this is the SHADOW proof the PIT path resolves so run.py can thread it."""
    try:
        from collectors.fred import load_vintages
        from engine import base_effect as be
        vints = load_vintages()
        as_of = pd.Timestamp.today().normalize()
        pit = be.compute(as_of=as_of, vintages=vints)
        latest = be.compute()  # run.py's current call (no as_of/vintages)
        return {
            "vintages_loaded": vints is not None and not getattr(vints, "empty", True),
            "n_vintage_series": (int(vints["series"].nunique())
                                 if vints is not None and not vints.empty else 0),
            "pit_revised_flag": (pit or {}).get("revised"),
            "latest_call_revised_flag": (latest or {}).get("revised"),
            "growth_series_revised": {k: v.get("revised")
                                      for k, v in ((pit or {}).get("growth") or {})
                                      .get("series", {}).items()},
            "inflation_series_revised": {k: v.get("revised")
                                         for k, v in ((pit or {}).get("inflation") or {})
                                         .get("series", {}).items()},
            "note": "run.py should thread as_of + load_vintages() into base_effect.compute "
                    "on the SHADOW regime_one path so CPI/PCE/PPI read leak-free (revised=False "
                    "where vintage coverage exists: CPI 1997+, PCE 2000+, PPI 2014+).",
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--accrue", action="store_true",
                    help="append today's causal-HMM forward call before grading")
    args = ap.parse_args()

    hist = _axis_scores()
    if hist is None:
        print("error: regime_history.parquet not found (run engine.run first)", file=sys.stderr)
        return 1

    if args.accrue:
        appended = accrue_hmm_row()
        print(f"accrue: {'appended' if appended else 'no-op (already have today)'}", file=sys.stderr)

    be_total, be_mat = mature_base_effect(hist)
    hmm_total, hmm_mat = mature_hmm(hist)

    be_grade = grade_base_effect()
    hmm_grade = grade_hmm()

    summary = {
        "schema": "regime_fwd_grade.v1",
        "as_of": str(hist.index[-1].date()),
        "min_grade_n": MIN_GRADE_N,
        "base_effect": {
            "growth": {**be_grade["growth"],
                       "verdict": _verdict(be_grade["growth"]["n_directional"],
                                           be_grade["growth"]["wilson_lo"])},
            "inflation": {**be_grade["inflation"],
                          "verdict": _verdict(be_grade["inflation"]["n_directional"],
                                              be_grade["inflation"]["wilson_lo"])},
        },
        "causal_hmm": {**hmm_grade,
                       "verdict": _verdict(hmm_grade["n_matured"], hmm_grade["wilson_lo"],
                                           baseline=0.25)},   # 4-quad baseline = 0.25
        "base_effect_pit": check_base_effect_pit(),
        "note": "SHADOW gate (#16). No promotion happens here — this measures accrual and "
                "issues an accrual-aware go/no-go. Forward calls are 1 row/session; mature "
                "at +63bd (base_effect) / +21bd (HMM).",
    }

    dst = config.ROOT / "calibration" / "regime_fwd_grade.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(summary, indent=2, default=str))

    beg, bei = summary["base_effect"]["growth"], summary["base_effect"]["inflation"]
    print(f"base_effect: {be_mat}/{be_total} matured | "
          f"growth {beg['verdict']['status']} (n={beg['n_directional']}) | "
          f"inflation {bei['verdict']['status']} (n={bei['n_directional']})", file=sys.stderr)
    print(f"causal_hmm: {hmm_mat}/{hmm_total} matured | "
          f"{summary['causal_hmm']['verdict']['status']} (n={hmm_mat})", file=sys.stderr)
    pit = summary["base_effect_pit"]
    print(f"base_effect PIT: revised(pit)={pit.get('pit_revised_flag')} "
          f"revised(run.py-call)={pit.get('latest_call_revised_flag')}", file=sys.stderr)
    print(f"wrote {dst}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
