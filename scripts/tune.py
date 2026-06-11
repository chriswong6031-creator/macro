"""Hysteresis/threshold tuning sweep (Phase 2e).

Grid-searches the config knobs the spec sanctions tuning (z_threshold,
hysteresis_days, shock_override_z, us2y growth weight) and scores each combo
against the validation criteria:
  - whipsaw % (< 15 target, lower better)
  - 2008-crisis Q4 share (higher better)
  - 2022 Q3 share (higher better)
  - 2021 H1 Q2 share (higher better)
  - covid flip lag in days from 2020-02-19 (lower better)

Writes the grid to reports/tuning_grid.csv and prints the Pareto-ish leaders.
Run AFTER changing component definitions; copy the winner into config.yml.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.inputs import build_features  # noqa: E402
from engine.regime import classify  # noqa: E402
from lib import config  # noqa: E402
from scripts.validate import regime_segments, whipsaw_stats  # noqa: E402

GRID = {
    "z_threshold": [0.25, 0.35, 0.45],
    "hysteresis_days": [5, 7, 9],
    "shock_override_z": [0.7, 0.85],
    "us2y_weight": [1.0, 0.5],
}


def score_combo(regime: pd.DataFrame) -> dict:
    seg = regime_segments(regime["quad"])
    ws = whipsaw_stats(seg, config.load()["validation"]["whipsaw_max_days"])
    q = regime["quad"]

    def share(a: str, b: str, quad: str) -> float:
        s = q.loc[a:b].dropna()
        return float((s == quad).mean()) if len(s) else float("nan")

    covid = regime.loc["2020-02-19":"2020-04-30"]
    q4_days = covid.index[covid["quad"] == "Q4"]
    covid_lag = (q4_days[0] - pd.Timestamp("2020-02-19")).days if len(q4_days) else 99

    return {
        "whipsaw_pct": ws["pct"], "changes": ws["changes"],
        "q4_2008": round(share("2008-09-01", "2009-03-31", "Q4"), 2),
        "q3_2022": round(share("2022-01-01", "2022-12-31", "Q3"), 2),
        "q2_2021h1": round(share("2021-01-01", "2021-06-30", "Q2"), 2),
        "covid_lag_d": covid_lag,
    }


def main() -> None:
    f = build_features()
    cfg = config.load()
    rows = []
    for zt, hd, sz, w2 in itertools.product(*GRID.values()):
        cfg["engine"]["scoring"]["z_threshold"] = zt
        cfg["engine"]["quad"]["hysteresis_days"] = hd
        cfg["engine"]["quad"]["shock_override_z"] = sz
        cfg["engine"]["growth_axis"]["components"]["us2y_direction"]["weight"] = w2
        regime = classify(f).loc["2007-01-01":]
        res = {"z_threshold": zt, "hysteresis_days": hd,
               "shock_override_z": sz, "us2y_weight": w2, **score_combo(regime)}
        rows.append(res)
        print(res)
    df = pd.DataFrame(rows)
    df["meets_whipsaw"] = df["whipsaw_pct"] < cfg["validation"]["whipsaw_target_pct"]
    # composite: prioritize episode fidelity among combos meeting the whipsaw bar
    df["fidelity"] = df["q4_2008"] + df["q3_2022"] + df["q2_2021h1"] - df["covid_lag_d"] / 60
    out = config.ROOT / cfg["storage"]["reports_dir"] / "tuning_grid.csv"
    df.sort_values(["meets_whipsaw", "fidelity"], ascending=False).to_csv(out, index=False)
    print("\n=== leaders (meeting whipsaw target) ===")
    print(df[df["meets_whipsaw"]].sort_values("fidelity", ascending=False)
          .head(8).to_string(index=False))


if __name__ == "__main__":
    main()
