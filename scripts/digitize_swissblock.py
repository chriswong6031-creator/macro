"""Digitize Swissblock's PUBLISHED signal panels and measure state agreement
with our reverse-engineered engine — the validation that justifies the whole
reverse-engineering premise.

Their lines are two-toned BY DESIGN (Risk Index: red >25 / blue <25; Momentum:
blue positive / red negative). So we don't fight anti-aliased value extraction —
we classify the dominant LINE COLOR per pixel-column, which IS their state
classification, then compare to ours on the same dates. State agreement is the
robust, low-error measurement (exact-value digitization is noted as future work).

Honest caveats baked in:
- x->date mapping is linear across the panel's stated window; a few days of
  registration error at the edges is expected and reported.
- panels are a fixed ~13-month window (Apr 2024–Apr 2025), one cycle slice.
- result is INDICATIVE: a sanity anchor, never a training target (we calibrate
  on our own forward-return history; this checks we'd have agreed with them).

Run: .venv/bin/python -m scripts.digitize_swissblock
Writes data/fixtures/swissblock/*.parquet + reports/vector-agreement.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store  # noqa: E402

PANELS = [
    {
        "file": "research/swissblock_panels/fe675282-eb18-4869-a745-410579af5099_1350x900.png",
        "name": "risk_index",
        "start": "2024-04-01", "end": "2025-04-29",
        "our_col": "risk_regime",
        "red_state": "high_risk", "blue_state": "low_risk",   # red>25, blue<25
        "crop_top": 0.20, "crop_bottom": 0.06, "crop_left": 0.04, "crop_right": 0.04,
    },
    {
        "file": "research/swissblock_panels/605ed6f3-cbb8-4b5d-8a31-4122757ab80f_1350x900.png",
        "name": "momentum",
        "start": "2024-04-01", "end": "2025-04-29",
        "our_col": "momentum_state",
        "red_state": "bear", "blue_state": "bull",            # blue>0, red<0
        "crop_top": 0.20, "crop_bottom": 0.06, "crop_left": 0.04, "crop_right": 0.04,
    },
]


def extract_color_states(path: str, crop: dict) -> pd.Series:
    """Per-column dominant line color -> 'red'/'blue'/NaN across the plot band."""
    im = np.asarray(Image.open(path).convert("RGB")).astype(int)
    h, w, _ = im.shape
    r0, r1 = int(h * crop["crop_top"]), int(h * (1 - crop["crop_bottom"]))
    c0, c1 = int(w * crop["crop_left"]), int(w * (1 - crop["crop_right"]))
    sub = im[r0:r1, c0:c1]
    r, g, b = sub[..., 0], sub[..., 1], sub[..., 2]
    red = (r > 140) & (r - g > 50) & (r - b > 40)
    blue = (b > 120) & (b - r > 40) & (b - g > 10)
    red_n, blue_n = red.sum(axis=0), blue.sum(axis=0)
    state = np.where((red_n + blue_n) < 2, np.nan,
                     np.where(red_n >= blue_n, 0.0, 1.0))  # 0=red, 1=blue
    return pd.Series(state)  # indexed by column offset


def to_daily(col_states: pd.Series, start: str, end: str,
             red_state: str, blue_state: str) -> pd.Series:
    valid = col_states.dropna()
    if valid.empty:
        return pd.Series(dtype=object)
    cmin, cmax = valid.index.min(), valid.index.max()
    dates = pd.date_range(start, end, freq="D")
    # map each date to the nearest populated column, majority-vote duplicates
    col_for_date = np.linspace(cmin, cmax, len(dates)).round().astype(int)
    vals = col_states.reindex(range(cmin, cmax + 1)).ffill().bfill()
    picked = vals.loc[col_for_date].values
    label = np.where(picked >= 0.5, blue_state, red_state)
    return pd.Series(label, index=dates, name="their_state")


def agreement(their: pd.Series, ours: pd.Series) -> dict:
    df = pd.concat([their.rename("their"), ours.rename("ours")], axis=1).dropna()
    if df.empty:
        return {"overlap_days": 0}
    match = (df["their"] == df["ours"]).mean()
    # flip-timing: median |days| between their state-change and our nearest one
    def changes(s):
        return s.index[s != s.shift()].tolist()
    tc, oc = changes(df["their"]), changes(df["ours"])
    deltas = []
    for t in tc:
        if oc:
            deltas.append(min(abs((t - o).days) for o in oc))
    return {
        "overlap_days": int(len(df)),
        "state_agreement_pct": round(100 * match, 1),
        "their_changes": len(tc), "our_changes": len(oc),
        "median_flip_delta_days": int(np.median(deltas)) if deltas else None,
    }


def main() -> int:
    sig = store.read("vector", "signals")
    if sig is None:
        print("run scripts.calibrate_vector first (needs data/vector/signals.parquet)")
        return 1
    sig.index = pd.to_datetime(sig.index)
    outdir = config.data_dir() / "fixtures" / "swissblock"
    outdir.mkdir(parents=True, exist_ok=True)

    lines = ["# Bitcoin Vector — agreement with Swissblock's published panels", "",
             "State-agreement between our engine and Swissblock's own two-toned signal "
             "lines, digitized by per-column color classification (their red/blue "
             "coding IS their state). Indicative sanity anchor over a ~13-month window, "
             "NOT a fit target. Exact-value digitization is future work.", ""]
    results = {}
    for p in PANELS:
        col_states = extract_color_states(p["file"], p)
        their = to_daily(col_states, p["start"], p["end"], p["red_state"], p["blue_state"])
        their.to_frame().to_parquet(outdir / f"{p['name']}_their_state.parquet")
        ours = sig[p["our_col"]].reindex(their.index).ffill()
        a = agreement(their, ours)
        results[p["name"]] = a
        lines.append(f"## {p['name']}  (vs our `{p['our_col']}`)\n")
        lines.append(f"- window: {p['start']} → {p['end']}, overlap {a.get('overlap_days')} days")
        lines.append(f"- **state agreement: {a.get('state_agreement_pct')}%**")
        lines.append(f"- their state-changes: {a.get('their_changes')}, "
                     f"ours: {a.get('our_changes')}, "
                     f"median flip delta: {a.get('median_flip_delta_days')} days\n")
        print(f"{p['name']:12s} agreement={a.get('state_agreement_pct')}%  "
              f"overlap={a.get('overlap_days')}d  flip_delta={a.get('median_flip_delta_days')}d")

    Path(config.load()["storage"]["reports_dir"], "vector-agreement.md").write_text("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
