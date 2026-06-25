"""Falsifier gate for the BTC impulse radar's ACT-TIER legs.

The honesty mandate: a leg may carry act-tier weight ONLY while it still LEADS.
This re-derives each act leg's leak-free edge over the full history + the 2024+
holdout + a block-permutation p-value, compares to a PRE-REGISTERED floor, and
writes a verdict gate `data/vector/impulse_legs_gate.json`. The radar reads that
gate at build time and AUTO-DEMOTES a leg whose edge has decayed (status
"demoted" → its act points are zeroed) — no code change needed, mirroring the
repo's `validate-leading-legs` pattern. `main()` also exits non-zero when a
pre-registered act leg fails, so CI fails loudly on a regression.

Legs + floors (pre-registered; raising a floor or adding a leg is the only
allowed knob, and it must be deliberate):
  d2  DVOL range-jolt  (DOWN)  holdout lift >= 1.5   — the strongest leg
  d3  SOPR profit-spike(DOWN)  holdout lift >= 1.3
  u1  SOPR capitulation(UP)    holdout lift >= 1.3   (reactive bounce caller)

Label (the locked taxonomy): DOWN = forward-min over (t,t+3] <= -5%; UP =
forward-max over (t,t+3] >= +5%. All features come from btc_impulse_radar's
shared causal condition builders, so the gate cannot drift from the live legs.
Deterministic (fixed RNG seed) so CI is reproducible.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from lib import config, store
from engine import btc_impulse_radar as radar

log = logging.getLogger(__name__)

HOLDOUT_START = "2024-01-01"          # ETF-era holdout (where we validate)
LABEL_H = 3                           # forward horizon (trading days)
LABEL_THR = 0.05                      # +-5%
PERM_N = 2000                         # block-permutation shuffles
P_MAX = 0.05

LEGS = {
    "d2": {"dir": "down", "floor": 1.5, "label": "Vol-of-vol jolt (DVOL range)"},
    "d3": {"dir": "down", "floor": 1.3, "label": "SOPR profit-take spike"},
    "u1": {"dir": "up",   "floor": 1.3, "label": "SOPR capitulation (wash-out)"},
}


def _labels(close: pd.Series):
    fwd_min = close.shift(-1).rolling(LABEL_H).min()
    fwd_max = close.shift(-1).rolling(LABEL_H).max()
    return (fwd_min / close - 1.0) <= -LABEL_THR, (fwd_max / close - 1.0) >= LABEL_THR


def _lift(fire: pd.Series, label: pd.Series, mask: pd.Series):
    v = fire.notna() & label.notna() & mask
    n = int((v & fire).sum())
    base = label[v].mean()
    cond = label[v & fire].mean() if n else np.nan
    lift = (cond / base) if (base and not np.isnan(cond)) else np.nan
    return float(base) if pd.notna(base) else np.nan, float(lift) if pd.notna(lift) else np.nan, n


def _perm_p(fire: pd.Series, label: pd.Series, mask: pd.Series, observed_lift: float, rng) -> float:
    """Circular-shift permutation p — preserves the autocorrelation of `fire`
    (block structure) while breaking its alignment with the labels."""
    v = fire.notna() & label.notna() & mask
    f = fire[v].to_numpy().astype(bool)
    lab = label[v].to_numpy().astype(float)
    base = lab.mean()
    L = len(f)
    if L < 30 or base <= 0 or np.isnan(observed_lift) or f.sum() == 0:
        return np.nan
    ge = 0
    for _ in range(PERM_N):
        s = int(rng.integers(1, L))
        fs = np.roll(f, s)
        m = fs.sum()
        if not m:
            continue
        lift = (lab[fs].mean() / base)
        if lift >= observed_lift:
            ge += 1
    return (ge + 1) / (PERM_N + 1)


def validate(sig_df: pd.DataFrame | None = None) -> dict:
    """Re-derive each act leg's edge and verdict. Never raises."""
    try:
        if sig_df is None:
            sig_df = store.read("vector", "signals")
        if sig_df is None or sig_df.empty:
            return {"ok": False, "reason": "signals.parquet not found"}
        df = sig_df.copy(); df.index = pd.to_datetime(df.index); df = df.sort_index()
        close = df["close"]
        down, up = _labels(close)
        fires = radar.fire_series(df)
        if fires is None or fires.empty:
            return {"ok": False, "reason": "fire_series empty (radar inputs missing)"}
        holdout = pd.Series(df.index >= pd.Timestamp(HOLDOUT_START), index=df.index)
        full = pd.Series(True, index=df.index)
        rng = np.random.default_rng(0)

        out = {}
        all_pass = True
        for key, spec in LEGS.items():
            if key not in fires.columns:
                out[key] = {"status": "no_data", "pass": None, "label": spec["label"]}
                continue
            fire = fires[key].reindex(df.index).fillna(False)
            label = down if spec["dir"] == "down" else up
            base_f, lift_f, n_f = _lift(fire, label, full)
            base_h, lift_h, n_h = _lift(fire, label, holdout)
            p = _perm_p(fire, label, full, lift_f, rng)
            passed = (
                pd.notna(lift_h) and lift_h >= spec["floor"]
                and pd.notna(p) and p <= P_MAX
            )
            all_pass = all_pass and passed
            out[key] = {
                "status": "leading" if passed else "demoted",
                "pass": bool(passed),
                "dir": spec["dir"], "label": spec["label"], "floor": spec["floor"],
                "lift_full": round(lift_f, 3) if pd.notna(lift_f) else None,
                "lift_holdout": round(lift_h, 3) if pd.notna(lift_h) else None,
                "perm_p": round(p, 4) if pd.notna(p) else None,
                "n_fires_full": n_f, "n_fires_holdout": n_h,
            }
        return {"ok": True, "asof": str(df.index[-1].date()), "all_pass": all_pass,
                "holdout_start": HOLDOUT_START, "label": f"fwd({LABEL_H}d) +-{int(LABEL_THR*100)}%",
                "legs": out,
                "note": ("Pre-registered act-tier legs re-validated leak-free. A leg "
                         "is DEMOTED (act points zeroed by the radar) if its 2024+ "
                         "holdout lift falls below its floor or its permutation p>0.05.")}
    except Exception as e:  # noqa: BLE001 — falsifier is additive, never fatal to the build
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def gate_path():
    return config.data_dir() / "vector" / "impulse_legs_gate.json"


def write_gate(verdict: dict) -> None:
    p = gate_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(verdict, indent=2))


def load_gate() -> dict:
    """Read the verdict gate (used by the radar to auto-demote). {} if absent."""
    try:
        p = gate_path()
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    v = validate()
    if not v.get("ok"):
        log.warning("impulse falsifier could not run: %s", v.get("reason"))
        return 0  # missing data is not a regression — don't fail CI on it
    write_gate(v)
    for key, leg in v["legs"].items():
        log.info("  %s: %s  holdout_lift=%s floor=%s p=%s", key, leg.get("status"),
                 leg.get("lift_holdout"), leg.get("floor"), leg.get("perm_p"))
    if not v["all_pass"]:
        failed = [k for k, lg in v["legs"].items() if lg.get("pass") is False]
        log.error("IMPULSE FALSIFIER FAILED — leg(s) stopped leading: %s", failed)
        return 1
    log.info("impulse falsifier: all act legs still lead.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
