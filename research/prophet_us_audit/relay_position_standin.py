"""S-D: relay-position stand-in — the #4506 CN port, US curated baskets.

Event = a basket member printing a fresh 63-session closing high. For each event,
relay_position = fraction of the basket's cache-covered members whose OWN fresh-63d-high
came earlier within the trailing 21 sessions (0 = first mover, 1 = latest). Outcome =
forward 10-session return minus same-day universe median. Membership from
data/baskets/membership.json (added/removed dates honored PIT). Eval = every cache day
with full forward coverage (~12 months). Splits: early ≤0.33 / mid / late ≥0.67 +
first-mover exactly-0. Pooled + per-name-first + date-demeaned-by-construction (excess vs
day median). Exploratory stand-in; arms Door T promotion expectations, confers nothing.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "relay_position_standin_results.json")
os.chdir(REPO)
sys.path.insert(0, REPO)

H = 10
RELAY_WIN = 21
HIGH_WIN = 63


def main() -> None:
    px = pd.concat([pd.read_parquet(f"data/{g}/_closes_cache.parquet")
                    for g in ("breadth", "midcap_breadth", "smallcap_breadth")],
                   axis=1, sort=False)
    px = px.loc[:, ~px.columns.duplicated()]
    px = px.sort_index()
    di = px.index
    n = len(di)

    fresh_high = px.eq(px.rolling(HIGH_WIN).max()) & px.notna()
    # exclude the warmup where rolling max is undefined-ish
    fresh_high.iloc[:HIGH_WIN] = False
    fwd = px.shift(-H) / px - 1
    day_med = fwd.median(axis=1)

    baskets = json.load(open("data/baskets/membership.json"))["baskets"]
    events = []
    for bid, b in baskets.items():
        if str(bid).startswith("us_sector_"):
            continue
        members = [(m["ticker"], m.get("added"), m.get("removed"))
                   for m in b.get("members", [])]
        covered = [t for t, _, _ in members if t in px.columns]
        if len(covered) < 4:
            continue
        fh = fresh_high[covered]
        for i in range(HIGH_WIN + RELAY_WIN, n - H):
            d = di[i]
            active = []
            for t, added, removed in members:
                if t not in px.columns:
                    continue
                if added and str(d.date()) < added:
                    continue
                if removed and str(d.date()) >= removed:
                    continue
                active.append(t)
            if len(active) < 4:
                continue
            todays = [t for t in active if bool(fh.at[d, t])]
            if not todays:
                continue
            win = fh.loc[di[i - RELAY_WIN]:d, active]
            earlier_any = win.iloc[:-1].any()          # broke out before today, in window
            n_earlier = int(earlier_any.sum())
            for t in todays:
                f = fwd.at[d, t]
                if pd.isna(f):
                    continue
                pos = n_earlier / max(1, len(active) - 1)
                events.append({"basket": bid, "ticker": t, "date": str(d.date()),
                               "relay_position": round(float(pos), 3),
                               "n_active": len(active),
                               "excess_pp": round(float((f - day_med.at[d]) * 100), 3)})

    ev = pd.DataFrame(events)
    res: dict = {"n_events": int(len(ev)),
                 "n_names": int(ev["ticker"].nunique()) if len(ev) else 0,
                 "date_range": [ev["date"].min(), ev["date"].max()] if len(ev) else None,
                 "H": H, "relay_win": RELAY_WIN, "high_win": HIGH_WIN}

    def cell(m: pd.DataFrame) -> dict:
        byname = m.groupby("ticker")["excess_pp"].median()
        return {"n": int(len(m)), "names": int(byname.shape[0]),
                "median_excess_pp": round(float(m["excess_pp"].median()), 2),
                "mean_excess_pp": round(float(m["excess_pp"].mean()), 2),
                "win_pct": round(float((m["excess_pp"] > 0).mean() * 100), 1),
                "per_name_median_pp": round(float(byname.median()), 2)}

    if len(ev):
        res["first_mover_pos0"] = cell(ev[ev["relay_position"] == 0.0])
        res["early_le033"] = cell(ev[ev["relay_position"] <= 0.33])
        res["mid"] = cell(ev[(ev["relay_position"] > 0.33) & (ev["relay_position"] < 0.67)])
        res["late_ge067"] = cell(ev[ev["relay_position"] >= 0.67])
        # half-split robustness on the early-vs-late delta
        ev["date_dt"] = pd.to_datetime(ev["date"])
        mid_date = ev["date_dt"].median()
        for half, m in (("first_half", ev[ev["date_dt"] <= mid_date]),
                        ("second_half", ev[ev["date_dt"] > mid_date])):
            e = m[m["relay_position"] <= 0.33]["excess_pp"]
            l = m[m["relay_position"] >= 0.67]["excess_pp"]
            res[f"delta_early_minus_late_{half}"] = (
                round(float(e.median() - l.median()), 2)
                if len(e) >= 20 and len(l) >= 20 else f"thin (e={len(e)}, l={len(l)})")

    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
