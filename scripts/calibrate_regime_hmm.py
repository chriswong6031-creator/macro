"""Nightly calibration for the continuous-regime HMM (v1, L2).

Fits the 4-state informed Gaussian HMM (engine/regime_hmm.py) on the committed axis-score
history and writes data/regime/hmm_latest.json. This runs in the CALIBRATION lane (like the
ladder/business-cycle calibrations), NOT the render or engine.run path — engine/run.py only
READS the JSON as a display-only leaf (so a ~1s fit never lands in the fast render, per the
plan's compute-budget rule §S5).

DISPLAY-ONLY: the output does not drive any weight, size, or gross dial. It is gated behind
`engine.regime_fwd.enabled` when consumed, and scored promotion waits on validate_regime_fwd.py.

Run:  python -m scripts.calibrate_regime_hmm
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.regime_hmm import fit_regime_hmm  # noqa: E402
from lib import config  # noqa: E402


def main() -> int:
    p = config.data_dir() / "regime"
    hist = p / "regime_history.parquet"
    if not hist.exists():
        print(f"error: {hist} not found (run engine.run first)", file=sys.stderr)
        return 1
    df = pd.read_parquet(hist)
    out = fit_regime_hmm(df)
    if out is None:
        print("error: HMM fit returned None (insufficient history?)", file=sys.stderr)
        return 1
    dst = p / "hmm_latest.json"
    dst.write_text(json.dumps(out, indent=2, default=str))
    rp = out["regime_probs"]
    print(f"wrote {dst}: {out['asof']} modal={out['modal_quad']} "
          f"P={ {k: round(v, 2) for k, v in rp.items()} } "
          f"hazard={out['hazard']} dwell={out['expected_dwell_months']}mo", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
