"""S-D: relay-position stand-in — the #4506 CN port, US curated baskets.

Event = a basket member printing a fresh 63-session closing high. For each event,
relay_position = fraction of the basket's covered members whose OWN fresh-63d-high came
earlier within the trailing 21 sessions (0 = first mover, 1 = latest). Outcome = forward
10-session return minus same-day universe median. Membership from
data/baskets/membership.json (added/removed dates honored PIT). Splits: early ≤0.33 / mid /
late ≥0.67 + first-mover exactly-0. Pooled + per-name-first + date-demeaned-by-construction
(excess vs day median). Exploratory stand-in; arms Door T promotion expectations, confers
nothing.

PRICE BASIS — MIGRATED TO A PINNED FROZEN PANEL (reference migration)
=====================================================================
This is the worked reference for ``research/RESEARCH_PRICE_PANEL_ADOPTION.md``. It used to
price itself by concatenating the three breadth close caches at run time::

    px = pd.concat([pd.read_parquet(f"data/{g}/_closes_cache.parquet") for g in ...])

Those caches are re-based at an infrequent full rebuild and accrue RAW closes after it, so
that line returns different numbers on different days. Measured on THIS instrument, running
the pre-migration code unchanged against the same repo on 2026-08-06: **6 of its 31 numeric
statistics moved** versus the committed
``relay_position_standin_results.json`` — two events re-partitioned between the `mid` and
`late` buckets and four cell statistics moved by 0.01pp. Small here (the outcome is
day-demeaned, which cancels most of a common re-base), but it is drift with no upper bound
and nothing recorded that it had happened.

It now reads ``data/research_panels/prices_v<PANEL_VERSION>.parquet`` — adjusted-first,
write-once, sha256-verified. Re-running it a year from now reads the same bytes.

THE FROZEN JSON IS NOT OVERWRITTEN. ``relay_position_standin_results.json`` is retained
exactly as it shipped; this module writes a mode-suffixed file and never that path.

The pinned run is NOT a correction of the frozen one and the two are not decomposed. The
panel changes the price BASIS *and* the observed population in one step: the adjusted
sources carry the large-cap sleeve ~2 years deeper than ``data/breadth``'s cache, so names
that had no history before 2025-03-18 now have it (#4698 trap 1 — coverage masquerading as
basis). ``population`` in the results block reports the observed cells and date range so
that change is visible rather than inferred. Decomposing basis from coverage needs a
mask-pinned re-run, which is the instrument lane's work, not this migration's.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(REPO)
sys.path.insert(0, REPO)

H = 10
RELAY_WIN = 21
HIGH_WIN = 63

#: The pinned evidence base. Bumping this is a deliberate act that mints a NEW results
#: file — it never rewrites an existing one. There is no "latest": see the adoption note.
PANEL_VERSION = os.environ.get("RELAY_PRICE_PANEL", "2026-08-06")

#: ``cache_legacy`` reproduces the pre-migration price path for provenance comparison. It
#: is irreproducible BY CONSTRUCTION — that is the point of keeping it nameable — and it
#: writes its own file, never the frozen one.
BASIS = os.environ.get("RELAY_PRICE_BASIS", "panel")


def _load_panel_module():
    path = Path(REPO) / "research/research_panels/price_panel.py"
    spec = importlib.util.spec_from_file_location("price_panel", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_prices() -> tuple[pd.DataFrame, dict, str]:
    """Close panel + a provenance block + the output path for this basis."""
    if BASIS == "cache_legacy":
        px = pd.concat([pd.read_parquet(f"data/{g}/_closes_cache.parquet")
                        for g in ("breadth", "midcap_breadth", "smallcap_breadth")],
                       axis=1, sort=False)
        px = px.loc[:, ~px.columns.duplicated()].sort_index()
        prov = {
            "basis": "cache_legacy",
            "reproducible": False,
            "why_not": ("the breadth close caches are re-based at a full rebuild and accrue "
                        "raw closes after it; this frame differs between run dates"),
            "names": int(px.shape[1]), "sessions": int(px.shape[0]),
        }
        return px, prov, os.path.join(HERE, "relay_position_standin_cache_rerun.json")

    pp = _load_panel_module()
    px, m = pp.load_panel(PANEL_VERSION)
    # Benchmarks share the file so an excess return has both legs on one basis; they are
    # not members of the cross-section and must not enter the day median or the highs.
    px = px.drop(columns=[b for b in m["benchmarks"] if b in px.columns])
    prov = {
        "basis": "frozen_panel",
        "reproducible": True,
        "panel_version": m["version"],
        "panel_sha256": m["sha256"],
        "panel_asof": m["asof"],
        "coverage": pp.coverage_line(m),
        "n_covered_adjusted": m["n_covered"],
        "n_requested": m["n_requested"],
        "coverage_pct": m["coverage_pct"],
        "n_on_unadjusted_cache": len(m["uncovered"]["unadjusted_basis"]),
        "n_unresolved": len(m["uncovered"]["unresolved"]),
        "names": int(px.shape[1]), "sessions": int(px.shape[0]),
    }
    return px, prov, os.path.join(
        HERE, f"relay_position_standin_panel_v{PANEL_VERSION}.json")


def main() -> None:
    px, price_prov, out = load_prices()
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
    res: dict = {"price_basis": price_prov,
                 # The population the price basis admitted. Reported so a delta against the
                 # frozen JSON is never read as pure basis: the panel changes coverage too.
                 "population": {
                     "panel_names": int(px.shape[1]),
                     "panel_sessions": int(px.shape[0]),
                     "panel_range": [str(di.min().date()), str(di.max().date())],
                     "cells_observed": int(px.notna().to_numpy().sum()),
                 },
                 "n_events": int(len(ev)),
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

    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))
    if price_prov["basis"] == "frozen_panel":
        # The coverage receipt belongs beside the n, not in a file nobody opens.
        print(f"\ncoverage: n={res['n_events']} events over {price_prov['coverage']}")


if __name__ == "__main__":
    main()
