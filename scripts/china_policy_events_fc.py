#!/usr/bin/env python3
"""F-C exploratory leg — MPC communiqué phrase-diff events × SHCOMP forward returns.

Pre-registration: research/CHINA_POLICY_EVENTS_PREREG.md (committed before any
outcome computation — the git timestamp is the proof).

UNBLOCKING HISTORY (per prereg §F-C row):
  F-C was BLOCKED-DATA at phase-0 run time: data/china_official/communiques.parquet
  was absent on main when scripts/china_policy_events_phase0.py ran on 2026-07-06.
  The W1.1 collector (scripts/backfill_china_communiques.py --family pboc_mpc) was
  run 2026-07-06 on the manual Mac lane (RUL-9: not in nightly collect). This script
  computes F-C as a pre-registered exploratory leg on the same day.

EPISTEMICS — F-C IS EXPLORATORY/UNSIGNED (per RUL-5):
  • Phrase polarity stays unsigned — events are salience-only.
  • NO verdicts (GO/ACCRUE/NO-GO/KILL words not applied to F-C).
  • NO t-stats, NO p-values, NO FDR.
  • NO signing by phrase polarity.
  • NO wiring into any engine, board, or score.
  • Descriptive tables only: n / mean / median (std permitted at top level).
  • The word "validated" is forbidden (CI-enforced).
  • Post-outcome threshold edits are void per the prereg void rule.

RUN HISTORY (data honesty; full detail in results-JSON run_history):
  Run 1 (2026-07-06, pre-fix parquet): the first collect returned 48 rows with
  publish_date AND meeting_date null for 47/48 (body-text date regex fails on MPC
  readout language; 2011–2015 listing page never fetched). Per the anchor spec
  (publish_date primary, meeting_date fallback, drop if both null) only the 2019-Q4
  event survived → n_usable=1, CAR@20 ≈ −7.58%, observed before any collector fix.
  Run 2 (2026-07-06, post-fix): the collector was repaired the same day — publish
  dates recovered from the PBoC listing-page CMS stamps (hui12 spans) and the
  missing 2011–2015 listing page fetched via page-range synthesis. 68 docs, all
  with publish_date. This was a data-completeness repair: no threshold, event
  definition, horizon, or gate changed (the prereg void rule is not triggered);
  the leg is descriptive/unsigned and carries no verdict in any case.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from typing import Any

import numpy as np
import pandas as pd

# ── Worktree root guard ───────────────────────────────────────────────────────
ROOT = pathlib.Path(".")
assert (ROOT / "data").exists(), (
    "Run from the worktree root (expected ./data/ to exist). "
    f"CWD is {pathlib.Path.cwd()}"
)

# Ensure the worktree root is on sys.path so that `engine` is importable
# when exec_module() runs phase-0 (which does `from engine.validation import …`).
_root_str = str(ROOT.resolve())
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

# ── Paths ─────────────────────────────────────────────────────────────────────
COMMUNIQUES_PATH = ROOT / "data" / "china_official" / "communiques.parquet"
SHCOMP_PATH      = ROOT / "data" / "china" / "000001.SS.parquet"
REGIME_PATH      = ROOT / "data" / "china_regime" / "regime_history.parquet"
SC_PATH          = ROOT / "data" / "china_sector_cycles" / "backfill.parquet"
RESULTS_PATH     = ROOT / "data" / "experiments" / "china_policy_events_results.json"

HORIZONS  = [5, 10, 20, 40, 60]
PRIMARY_H = 20
FAMILY    = "china_policy_events"


# ── Import phase-0 module (for CAR machinery only — not re-run) ───────────────
def _load_phase0() -> Any:
    """Import china_policy_events_phase0 as a module without executing main()."""
    p0_path = ROOT.resolve() / "scripts" / "china_policy_events_phase0.py"
    spec = importlib.util.spec_from_file_location(
        "china_policy_events_phase0", str(p0_path)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


_p0 = _load_phase0()

# Re-use constants and functions from phase-0 machinery
car_for_event             = _p0.car_for_event
compute_car_series        = _p0.compute_car_series
compute_conditioning_tables = _p0.compute_conditioning_tables
_conditioning_cell        = _p0._conditioning_cell
_load_close               = _p0._load_close

# Trial ledger — same family, same budget as phase-0 (budget covers F-C headroom)
_LED = _p0._LED


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — Load and filter communiqués
# ─────────────────────────────────────────────────────────────────────────────

def load_communiques() -> tuple[pd.DataFrame, int]:
    """Load pboc_mpc communiqués, filter explicit_gap rows, dedup, sort.

    Returns (df, n_explicit_gap_dropped).
    """
    df = pd.read_parquet(COMMUNIQUES_PATH)

    # Filter to pboc_mpc family only
    df = df[df["family"] == "pboc_mpc"].copy()

    # Drop explicit_gap sentinel rows
    gap_mask = df["source"] == "explicit_gap"
    n_explicit_gap_dropped = int(gap_mask.sum())
    df = df[~gap_mask].copy()

    # Dedup on doc_id (keep first occurrence)
    df = df.drop_duplicates(subset="doc_id", keep="first")

    # Sort chronologically by (meeting_year, meeting_quarter), NaNs last
    df = df.sort_values(
        ["meeting_year", "meeting_quarter"],
        na_position="last",
    ).reset_index(drop=True)

    return df, n_explicit_gap_dropped


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Event construction via consecutive phrase-set diff
# ─────────────────────────────────────────────────────────────────────────────

def build_phrase_sets(df: pd.DataFrame) -> list[set[str]]:
    """Compute phrase set for each doc in order (title + body, 46-formula book)."""
    from engine.communique_diff import load_phrase_book, phrases_in_text
    book = load_phrase_book(root=str(ROOT.resolve()))

    sets: list[set[str]] = []
    for _, row in df.iterrows():
        text = (str(row.get("title") or "") + " " + str(row.get("body") or ""))
        sets.append(phrases_in_text(text, book))
    return sets


def _parse_anchor(row: pd.Series) -> tuple[pd.Timestamp | None, str]:
    """Return (anchor_timestamp, which_field_used).

    Priority: publish_date -> meeting_date. Returns (None, 'dropped') if both null.
    """
    for field in ("publish_date", "meeting_date"):
        val = row.get(field)
        if val is not None and not (isinstance(val, float) and np.isnan(val)):
            try:
                ts = pd.Timestamp(val).normalize()
                if pd.notna(ts):
                    return ts, field
            except Exception:
                pass
    return None, "dropped"


def build_events(
    df: pd.DataFrame,
    phrase_sets: list[set[str]],
) -> tuple[list[dict], int, int, int]:
    """Construct events from consecutive communiqué pairs.

    Cold-start rule: the FIRST doc is baseline only; no event emitted for it.
    Event: len(appeared) + len(dropped) >= 1 for a consecutive pair.
    Anchor: publish_date of the CURRENT (newer) communiqué, per prereg; fallback
    meeting_date; drop if both null.
    Same-date merge: events sharing an anchor date merge to one episode.

    Returns (events_list, n_fallback, n_anchor_dropped, n_pairs_with_change).
    """
    n_docs = len(df)
    n_fallback = 0
    n_anchor_dropped = 0
    n_pairs_with_change = 0

    # Raw events before same-date merge
    raw: list[dict] = []

    for i in range(1, n_docs):  # i=0 is baseline (cold-start)
        prev_set = phrase_sets[i - 1]
        curr_set = phrase_sets[i]
        appeared = sorted(curr_set - prev_set)
        dropped  = sorted(prev_set - curr_set)

        if len(appeared) + len(dropped) < 1:
            continue  # no change — not an event

        n_pairs_with_change += 1
        curr_row = df.iloc[i]
        anchor, which = _parse_anchor(curr_row)

        if anchor is None:
            n_anchor_dropped += 1
            continue

        if which == "meeting_date":
            n_fallback += 1

        raw.append({
            "anchor":          anchor,
            "meeting_year":    int(curr_row.get("meeting_year") or 0),
            "meeting_quarter": (
                int(curr_row["meeting_quarter"])
                if pd.notna(curr_row.get("meeting_quarter"))
                else None
            ),
            "n_appeared":      len(appeared),
            "n_dropped":       len(dropped),
            "appeared":        appeared,
            "dropped":         dropped,
        })

    # Same-date merge: group by anchor, union phrase changes
    by_date: dict[pd.Timestamp, dict] = {}
    for ev in raw:
        d = ev["anchor"]
        if d not in by_date:
            by_date[d] = {
                "anchor":          d,
                "meeting_year":    ev["meeting_year"],
                "meeting_quarter": ev["meeting_quarter"],
                "appeared":        set(ev["appeared"]),
                "dropped":         set(ev["dropped"]),
            }
        else:
            by_date[d]["appeared"] |= set(ev["appeared"])
            by_date[d]["dropped"]  |= set(ev["dropped"])

    events: list[dict] = []
    for d, ep in sorted(by_date.items()):
        app = sorted(ep["appeared"])
        drp = sorted(ep["dropped"])
        events.append({
            "anchor":          d,
            "anchor_iso":      d.date().isoformat(),
            "meeting_year":    ep["meeting_year"],
            "meeting_quarter": ep["meeting_quarter"],
            "n_appeared":      len(app),
            "n_dropped":       len(drp),
            "appeared":        app,
            "dropped":         drp,
        })

    return events, n_fallback, n_anchor_dropped, n_pairs_with_change


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — CAR computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_fc_cars(
    event_dates: pd.DatetimeIndex,
    shcomp: pd.Series,
    cal: pd.DatetimeIndex,
) -> dict[str, dict]:
    """Compute per-horizon descriptive CAR statistics.

    Returns dict keyed by 'h5'..'h60' with:
      n_events, n_usable, n_dropped, mean_car, median_car, std_car.
    NO t-stats, NO p-values per RUL-5 (F-C exploratory/unsigned).
    """
    horizons_out: dict[str, dict] = {}
    for h in HORIZONS:
        cars, n_dropped = compute_car_series(
            event_dates, shcomp, None, h, cal, mode="absolute"
        )
        n_usable = len(cars)
        n_ev = len(event_dates)
        if n_usable > 0:
            mean_car   = round(float(cars.mean()), 6)
            median_car = round(float(cars.median()), 6)
            std_car    = round(float(cars.std(ddof=1)), 6) if n_usable > 1 else None
        else:
            mean_car = median_car = std_car = None

        horizons_out[f"h{h}"] = {
            "n_events":  n_ev,
            "n_usable":  n_usable,
            "n_dropped": n_dropped,
            "mean_car":  mean_car,
            "median_car": median_car,
            "std_car":   std_car,
        }
    return horizons_out


# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — Conditioning (descriptive only, sector_id=None)
# ─────────────────────────────────────────────────────────────────────────────

def compute_fc_conditioning(
    event_dates: pd.DatetimeIndex,
    primary_cars: pd.Series,
    regime: pd.DataFrame,
    sc: pd.DataFrame,
) -> dict:
    """Regime conditioning (quad/liquidity/cycle) with sector_id=None.

    Identical to phase-0's conditioning call but for F-C events.
    n<5 cells show n only. No t-stats, no verdicts per prereg.
    """
    return compute_conditioning_tables(event_dates, primary_cars, regime, sc, sector_id=None)


# ─────────────────────────────────────────────────────────────────────────────
# Section 5 — Print summary
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(
    n_docs: int,
    n_explicit_gap_dropped: int,
    n_pairs: int,
    n_pairs_with_change: int,
    n_events: int,
    n_fallback: int,
    n_anchor_dropped: int,
    horizons_out: dict[str, dict],
    conditioning: dict,
) -> None:
    print()
    print("=" * 60)
    print("F-C MPC Communiqué Phrase-Diff  (EXPLORATORY / UNSIGNED)")
    print("=" * 60)
    print(f"  Source: data/china_official/communiques.parquet (pboc_mpc)")
    print(f"  n_docs_pboc_mpc:            {n_docs}")
    print(f"  explicit_gap rows dropped:  {n_explicit_gap_dropped}")
    print(f"  n_consecutive_pairs:        {n_pairs}")
    print(f"  pairs with phrase change:   {n_pairs_with_change}  (≥1 formula appeared/dropped)")
    print(f"  anchor-null dropped:        {n_anchor_dropped}  (publish_date + meeting_date both null — no CAR anchor)")
    print(f"  n_anchor_fallback:          {n_fallback}  (event date from meeting_date fallback)")
    print(f"  final episodes (CAR-ready): {n_events}")
    if n_anchor_dropped > 0:
        print(f"NOTE: {n_anchor_dropped} pairs dropped — publish_date + meeting_date both null.")
        print("Per prereg anchor spec, pairs with both-null dates cannot produce CAR events.")
        print()
    print()
    print("--- Per-Horizon Descriptive CARs (SHCOMP absolute log, NO t-stat) ---")
    print(f"{'H':>4}  {'n_events':>8}  {'n_usable':>8}  {'n_dropped':>9}  {'mean':>9}  {'median':>9}")
    for hk in [f"h{h}" for h in HORIZONS]:
        h_data = horizons_out[hk]
        mean   = f"{h_data['mean_car']:.4%}" if h_data['mean_car'] is not None else "  n/a"
        med    = f"{h_data['median_car']:.4%}" if h_data['median_car'] is not None else "  n/a"
        print(
            f"{hk:>4}  {h_data['n_events']:>8}  {h_data['n_usable']:>8}  "
            f"{h_data['n_dropped']:>9}  {mean:>9}  {med:>9}"
        )
    print()
    print("--- Conditioning Tables (descriptive only, n<5 shows n only) ---")
    for dim in ["quad", "liquidity", "cycle"]:
        if dim not in conditioning:
            continue
        cells = conditioning[dim]
        print(f"  {dim}:")
        for label, cell in sorted(cells.items()):
            n = cell.get("n", 0)
            if n < 5:
                print(f"    {label}: n={n}")
            else:
                mean   = f"{cell.get('mean_car_h20', 0):.4%}"
                median = f"{cell.get('median_car_h20', 0):.4%}"
                print(f"    {label}: n={n}, mean={mean}, median={median}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Section 6 — Update results JSON (patch only F-C keys)
# ─────────────────────────────────────────────────────────────────────────────

def update_results_json(
    n_events: int,
    n_docs: int,
    n_pairs: int,
    n_pairs_with_change: int,
    n_fallback: int,
    n_anchor_dropped: int,
    n_explicit_gap_dropped: int,
    horizons_out: dict[str, dict],
    events: list[dict],
    conditioning: dict,
) -> None:
    """Patch F-C keys into results JSON in-place."""
    existing: dict = {}
    if RESULTS_PATH.exists():
        existing = json.loads(RESULTS_PATH.read_text())

    # Patch event_counts
    ec = existing.setdefault("event_counts", {})
    ec["FC_mpc_communiques"] = n_events

    # Patch fc_status
    existing["fc_status"] = (
        "RUN 2026-07-06 exploratory/descriptive/unsigned — "
        "communiques.parquet backfilled via scripts/backfill_china_communiques.py "
        "(W1.1 manual Mac lane) after phase-0 BLOCKED-DATA; "
        "see exploratory_trials.FC_communiques"
    )

    # Serialize events list (convert Timestamps to ISO strings)
    events_serial = []
    for ev in events:
        evs = dict(ev)
        evs["anchor"] = ev["anchor"].date().isoformat()
        events_serial.append(evs)

    # Build FC_communiques entry
    fc_entry: dict = {
        "label":              "FC->SHCOMP_phrase_diff_descriptive",
        "verdict":            "EXPLORATORY-DESCRIPTIVE",
        "unsigned":           True,
        "rul5":               "phrase polarity unsigned — events are salience-only",
        "anchor":             "publish_date (prereg) with meeting_date fallback",
        "n_docs_pboc_mpc":    n_docs,
        "n_pairs_diffed":     n_pairs,
        "n_pairs_with_phrase_change": n_pairs_with_change,
        "n_events":           n_events,
        "n_anchor_fallback":  n_fallback,
        "n_anchor_dropped":   n_anchor_dropped,
        "n_explicit_gap_rows_dropped": n_explicit_gap_dropped,
        "data_quality_note": (
            f"publish_date populated for all {n_docs} pboc_mpc rows from PBoC "
            "listing-page CMS stamps (hui12 spans) after collector fix 2026-07-06. "
            "meeting_date stays body-derived and is null for most readouts; "
            "publish_date is primary per prereg anchor spec, so "
            f"n_anchor_dropped={n_anchor_dropped}."
        ),
        "run_history": [
            {
                "run_date":    "2026-07-06 (pre-fix)",
                "n_docs":      48,
                "n_events":    1,
                "note": (
                    "First F-C computation ran on the pre-fix parquet: 47 of 48 rows "
                    "had null publish_date and null meeting_date (body-text date regex "
                    "fails on MPC readout language). Only the 2019-Q4 document carried "
                    "a parseable anchor (publish_date=2019-12-27 from body fallback), "
                    "yielding n_usable=1 and CAR@20 approx -7.58%. Observed before any "
                    "collector fix."
                ),
            },
            {
                "run_date":    "2026-07-06 (post-fix)",
                "n_docs":      n_docs,
                "n_events":    n_events,
                "note": (
                    "Collector fix recovered publish_date from PBoC listing-page CMS "
                    "stamps (hui12 spans adjacent to each article link) and fixed the "
                    "missing 2011-2015 listing pages via page-range synthesis (footer "
                    "linked pages 2 and 4 but not 3 — page 3 now synthesised). "
                    "This is a data-completeness repair: no threshold, event definition, "
                    "horizon, or gate was changed. The leg remains descriptive/unsigned "
                    "with no verdict in any case."
                ),
            },
        ],
        "horizons":           horizons_out,
        "events":             events_serial,
    }

    et = existing.setdefault("exploratory_trials", {})
    et["FC_communiques"] = fc_entry

    # Patch conditioning_tables
    ct = existing.setdefault("conditioning_tables", {})
    ct["FC_SHCOMP"] = conditioning

    RESULTS_PATH.write_text(json.dumps(existing, indent=2, default=str))
    print(f"Patched {RESULTS_PATH}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== China Policy Events — F-C Exploratory Leg ===")
    print("F-C: MPC communiqué phrase-diff × SHCOMP forward returns")
    print("EXPLORATORY / UNSIGNED per RUL-5 — no verdicts, no FDR")
    print()

    # ── Load data ─────────────────────────────────────────────────────────────
    assert COMMUNIQUES_PATH.exists(), f"BLOCKED: {COMMUNIQUES_PATH} not found"
    df, n_explicit_gap_dropped = load_communiques()
    n_docs = len(df)
    print(f"pboc_mpc docs (after gap-filter, dedup): {n_docs}")
    print(f"Explicit-gap rows dropped: {n_explicit_gap_dropped}")
    first, last = df.iloc[0], df.iloc[-1]
    print(f"Coverage: {int(first['meeting_year'])} Q{int(first['meeting_quarter'])} → "
          f"{int(last['meeting_year'])} Q{int(last['meeting_quarter'])}")

    # ── Build phrase sets ─────────────────────────────────────────────────────
    phrase_sets = build_phrase_sets(df)
    n_pairs = n_docs - 1  # first doc is baseline (cold-start rule)
    print(f"Consecutive pairs to diff (n_docs - 1): {n_pairs}")

    # ── Build events ──────────────────────────────────────────────────────────
    events, n_fallback, n_anchor_dropped, n_pairs_with_change = build_events(df, phrase_sets)
    n_events = len(events)
    print(f"Pairs with phrase change (≥1 formula appeared/dropped): {n_pairs_with_change}")
    print(f"Of those, anchor-null dropped (publish_date + meeting_date both null): {n_anchor_dropped}")
    print(f"Anchor fallback to meeting_date: {n_fallback}")
    print(f"Final episodes (same-date merged): {n_events}")

    if n_events == 0:
        print()
        print("WARNING: 0 episodes survived anchor filtering.")
        print("Per prereg, if no usable anchors exist, F-C cannot produce CAR results.")
        print("This reflects the data state: publish_date/meeting_date nearly all null.")
    elif n_events < 5:
        print()
        print(f"NOTE: Only {n_events} episode(s) with usable anchor dates.")
        print("CAR results are illustrative only at this n; far below meaningful statistical power.")

    # ── Log trial in ledger ───────────────────────────────────────────────────
    _LED.log_trial(
        {"trial": "FC_communiques_phrase_diff_h20", "kind": "exploratory_descriptive"},
        family=FAMILY,
        note=(
            "EXPLORATORY/UNSIGNED per RUL-5 — descriptive only, never enters FDR family"
        ),
    )

    # ── Load market data ──────────────────────────────────────────────────────
    shcomp = _load_close(SHCOMP_PATH)
    cal    = shcomp.index

    regime = pd.read_parquet(REGIME_PATH)
    regime.index = pd.to_datetime(regime.index).normalize()

    sc = pd.read_parquet(SC_PATH)
    sc["date"] = pd.to_datetime(sc["date"]).dt.normalize()

    # ── Build event DatetimeIndex ─────────────────────────────────────────────
    event_dates = pd.DatetimeIndex(
        [ev["anchor"] for ev in events]
    ).sort_values() if events else pd.DatetimeIndex([])

    # ── CAR computation ───────────────────────────────────────────────────────
    horizons_out = compute_fc_cars(event_dates, shcomp, cal)

    # ── Conditioning ─────────────────────────────────────────────────────────
    if len(event_dates) > 0:
        primary_cars, _ = compute_car_series(
            event_dates, shcomp, None, PRIMARY_H, cal, mode="absolute"
        )
    else:
        primary_cars = pd.Series(dtype=float)

    conditioning = compute_fc_conditioning(event_dates, primary_cars, regime, sc)

    # ── Print summary ─────────────────────────────────────────────────────────
    print_summary(
        n_docs=n_docs,
        n_explicit_gap_dropped=n_explicit_gap_dropped,
        n_pairs=n_pairs,
        n_pairs_with_change=n_pairs_with_change,
        n_events=n_events,
        n_fallback=n_fallback,
        n_anchor_dropped=n_anchor_dropped,
        horizons_out=horizons_out,
        conditioning=conditioning,
    )

    # ── Update results JSON ───────────────────────────────────────────────────
    update_results_json(
        n_events=n_events,
        n_docs=n_docs,
        n_pairs=n_pairs,
        n_pairs_with_change=n_pairs_with_change,
        n_fallback=n_fallback,
        n_anchor_dropped=n_anchor_dropped,
        n_explicit_gap_dropped=n_explicit_gap_dropped,
        horizons_out=horizons_out,
        events=events,
        conditioning=conditioning,
    )

    print("Done.")


if __name__ == "__main__":
    main()
