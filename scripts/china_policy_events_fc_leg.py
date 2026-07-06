#!/usr/bin/env python3
"""F-C leg: PBoC MPC communiqué phrase-diff events × SHCOMP forward returns.

Pre-registration: research/CHINA_POLICY_EVENTS_PREREG.md
Family: F-C, EXPLORATORY / UNSIGNED (RUL-5 of CHINA_INTEL_CYCLES_MASTERPLAN_BY_FABLE.md)

This leg was BLOCKED-DATA in the original phase-0 run because
data/china_official/communiques.parquet was absent.  The backfill script
(scripts/backfill_china_communiques.py, PR #1724) has since run; this script
runs the pre-registered F-C analysis.

LAWS:
  - Phrase polarity is UNSIGNED — no directional claim is made or permitted.
    Events are APPEARED or DROPPED; the study produces descriptive CARs only.
  - No verdicts, no FDR membership, no wiring.
  - Post-outcome threshold edits are void per the prereg void rule.
  - HAC NW t-stat MAY be shown but is LABELED exploratory (matching F-X precedent
    in the original report).

EVENT DEFINITION (pre-registered F-C row):
  Source: family=='pboc_mpc' rows from communiques.parquet, ordered by meeting
  sequence (meeting_year, meeting_quarter).  Compare each readout's body against
  the PREVIOUS readout's body using phrase_book.yml formulas + variants.  Event =
  a meeting whose readout has ≥1 formula APPEARED or DROPPED vs prior.

ANCHOR (pre-registered):
  publish_date where available; fall back to meeting_date where publish_date is null.
  Fallback count and bias direction are reported honestly (MPC readouts publish within
  days of the meeting — no directional bias on fallback is expected).

PIT:
  Entry = first close STRICTLY AFTER anchor date (same convention as F-A/F-B).
"""
from __future__ import annotations

import json
import pathlib
import sys
import textwrap
from datetime import datetime

import numpy as np
import pandas as pd

# ── Shared functions from the original phase-0 study ─────────────────────────
_HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from scripts.china_policy_events_phase0 import (
    FAMILY,
    HORIZONS,
    MIN_K,
    PRIMARY_H,
    N_TRIALS_DECLARED,
    SHCOMP_PATH,
    REGIME_PATH,
    RESULTS_PATH,
    _load_close,
    car_for_event,
    compute_car_series,
    compute_conditioning_tables,
    next_trading_day,
)
from engine.communique_diff import load_phrase_book, phrases_in_text
from engine.trial_ledger import TrialLedger

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = _HERE
DATA = ROOT / "data"
COMMUNIQUES_PATH = DATA / "china_official" / "communiques.parquet"
REPORT_PATH = ROOT / "reports" / "china-policy-events-phase0.md"

# ── Trial ledger (same family, same budget — already declared) ─────────────────
_LED = TrialLedger.with_declared_budget(N_TRIALS_DECLARED, FAMILY)


# ─────────────────────────────────────────────────────────────────────────────
# Phrase-diff event extraction
# ─────────────────────────────────────────────────────────────────────────────

def _body_text(row: dict | pd.Series) -> str:
    """Combine title + body for phrase matching (same convention as communique_diff)."""
    title = str(row.get("title") or "")
    body = str(row.get("body") or "")
    return f"{title} {body}"


def extract_phrase_diff_events(
    df: pd.DataFrame,
    book: list[dict],
) -> list[dict]:
    """Compare each MPC readout against the PRIOR readout in sequence.

    Returns a list of event dicts — one per meeting that had ≥1 formula change.
    Rows are expected sorted by (meeting_year, meeting_quarter).

    Cold-start rule: the very first readout in the sequence has no prior, so
    no event is emitted for it (matching communique_diff cold-start logic).

    Each event dict:
      {meeting_id, meeting_year, meeting_quarter, anchor_date, anchor_source,
       appeared[], dropped[]}
    """
    events: list[dict] = []
    rows = df.to_dict("records")

    for i, row in enumerate(rows):
        if i == 0:
            # Cold start — no prior readout to diff against.
            continue

        prior = rows[i - 1]
        today_phrases = phrases_in_text(_body_text(row), book)
        prior_phrases = phrases_in_text(_body_text(prior), book)

        appeared = sorted(today_phrases - prior_phrases)
        dropped = sorted(prior_phrases - today_phrases)

        if not appeared and not dropped:
            continue  # no formula change — not an event

        # Anchor: publish_date preferred; fall back to meeting_date
        anchor_date: str | None = None
        anchor_source: str = "publish_date"
        pub = str(row.get("publish_date") or "").strip()
        if pub and pub != "None" and pub != "nan":
            anchor_date = pub[:10]
        else:
            mt = str(row.get("meeting_date") or "").strip()
            if mt and mt != "None" and mt != "nan":
                anchor_date = mt[:10]
                anchor_source = "meeting_date_fallback"

        if not anchor_date:
            # No usable date — skip (cannot anchor PIT entry)
            continue

        yr = row.get("meeting_year")
        qt = row.get("meeting_quarter")
        meeting_id = f"pboc_mpc_{yr}_Q{qt}" if qt else f"pboc_mpc_{yr}"

        events.append({
            "meeting_id": meeting_id,
            "meeting_year": int(yr) if yr is not None else None,
            "meeting_quarter": int(qt) if qt is not None else None,
            "anchor_date": anchor_date,
            "anchor_source": anchor_source,
            "appeared": appeared,
            "dropped": dropped,
        })

    return events


# ─────────────────────────────────────────────────────────────────────────────
# Descriptive statistics (no verdict — EXPLORATORY)
# ─────────────────────────────────────────────────────────────────────────────

def _newey_west_tstat_safe(x: np.ndarray, lags: int = 4) -> dict | None:
    """HAC NW t-stat — labeled exploratory, returned for reporting only."""
    try:
        from engine.validation import newey_west_tstat
        return newey_west_tstat(x, lags=lags)
    except Exception:
        return None


def _descriptive_stats(cars: pd.Series, label: str = "") -> dict:
    """N/mean/median plus HAC-t labeled exploratory. No verdict field."""
    x = cars.dropna().to_numpy(float)
    n = len(x)
    if n == 0:
        return {"label": label, "n": 0, "mean_car": None, "median_car": None,
                "hac_t_exploratory": None, "hac_p_exploratory": None}
    mean_ = float(np.mean(x))
    median_ = float(np.median(x))
    nw = _newey_west_tstat_safe(x) if n >= MIN_K else None
    return {
        "label": label,
        "n": n,
        "mean_car": round(mean_, 6),
        "median_car": round(median_, 6),
        "hac_t_exploratory": round(nw["t"], 3) if nw else None,
        "hac_p_exploratory": round(nw["p"], 4) if nw else None,
        "hac_note": ("LABELED EXPLORATORY — not a gate, no verdict" if nw else
                     f"HAC not computed (n={n} < {MIN_K})"),
    }


def _conditioning_cell_fc(cars: pd.Series) -> dict:
    """n/mean/median only (no t-stats per prereg RUL-2). n<5 → n only."""
    n = int(len(cars.dropna()))
    if n < 5:
        return {"n": n}
    return {
        "n": n,
        "mean_car_h20": round(float(cars.dropna().mean()), 6),
        "median_car_h20": round(float(cars.dropna().median()), 6),
    }


def compute_fc_conditioning(
    event_dates: pd.DatetimeIndex,
    primary_cars: pd.Series,
    regime: pd.DataFrame,
) -> dict:
    """Regime-conditioning tables: quad / liquidity / cycle at anchor date."""
    results: dict = {}
    for col in ["quad", "liquidity", "cycle"]:
        if col not in regime.columns:
            continue
        tbl: dict = {}
        for ev_date in event_dates:
            if ev_date not in primary_cars.index:
                continue
            car_val = primary_cars.loc[ev_date]
            sub = regime[col]
            sub = sub[sub.index <= ev_date]
            label_val = str(sub.iloc[-1]) if not sub.empty else "unknown"
            tbl.setdefault(label_val, []).append(car_val)
        results[col] = {k: _conditioning_cell_fc(pd.Series(v)) for k, v in tbl.items()}
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Slice tables: APPEARED-only / DROPPED-only / BOTH
# ─────────────────────────────────────────────────────────────────────────────

def compute_slice_tables(
    events: list[dict],
    event_date_to_cars: dict,  # anchor_date_str → {h_label: car}
) -> dict:
    """Break APPEARED-only / DROPPED-only / BOTH at H=20 (n/mean/median only)."""
    slices: dict[str, list[float]] = {
        "appeared_only": [],
        "dropped_only": [],
        "both": [],
    }
    for ev in events:
        anchor = ev["anchor_date"]
        if anchor not in event_date_to_cars:
            continue
        car_h20 = event_date_to_cars[anchor].get(f"h{PRIMARY_H}")
        if car_h20 is None:
            continue
        has_app = len(ev["appeared"]) > 0
        has_drp = len(ev["dropped"]) > 0
        if has_app and has_drp:
            slices["both"].append(car_h20)
        elif has_app:
            slices["appeared_only"].append(car_h20)
        elif has_drp:
            slices["dropped_only"].append(car_h20)

    out: dict = {}
    for key, vals in slices.items():
        n = len(vals)
        if n == 0:
            out[key] = {"n": 0}
        elif n < 5:
            out[key] = {"n": n}
        else:
            out[key] = {
                "n": n,
                "mean_car_h20": round(float(np.mean(vals)), 6),
                "median_car_h20": round(float(np.median(vals)), 6),
            }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_fc_leg(
    root: pathlib.Path | None = None,
    communiques_path: pathlib.Path | None = None,
) -> dict:
    """Run the F-C MPC communiqué phrase-diff leg. Returns results dict.

    Args:
        root: repo root; defaults to the repo root of this script. phrase_book.yml,
              SHCOMP, and regime_history are always loaded from the REAL repo root
              (these are read-only data files the study depends on).
        communiques_path: override path to communiques.parquet (for tests). When None,
              falls back to root/data/china_official/communiques.parquet, then to
              the real REPO ROOT path.
    """
    # phrase_book, SHCOMP, and regime always come from the real repo root.
    data_root = ROOT

    # communiques path: explicit override > local root > real repo root
    if communiques_path is not None:
        comm_path = communiques_path
    elif root is not None:
        comm_path = root / "data" / "china_official" / "communiques.parquet"
    else:
        comm_path = data_root / "data" / "china_official" / "communiques.parquet"

    if not comm_path.exists():
        raise FileNotFoundError(
            f"communiques.parquet not found at {comm_path}. "
            "Run scripts/backfill_china_communiques.py first."
        )

    df_all = pd.read_parquet(comm_path)
    df_mpc = (
        df_all[df_all["family"] == "pboc_mpc"]
        .copy()
        .sort_values(["meeting_year", "meeting_quarter"], na_position="last")
        .reset_index(drop=True)
    )
    n_mpc_total = len(df_mpc)

    book = load_phrase_book(data_root)
    if not book:
        raise RuntimeError(
            "phrase_book.yml not found or empty. "
            f"Expected at {data_root}/data/china_official/phrase_book.yml"
        )

    shcomp_path = data_root / "data" / "china" / "000001.SS.parquet"
    shcomp = _load_close(shcomp_path)
    cal = shcomp.index

    regime_path = data_root / "data" / "china_regime" / "regime_history.parquet"
    regime = pd.read_parquet(regime_path)
    regime.index = pd.to_datetime(regime.index).normalize()

    # ── Extract phrase-diff events ─────────────────────────────────────────────
    events = extract_phrase_diff_events(df_mpc, book)
    n_diffable = max(0, n_mpc_total - 1)  # first row has no prior = cold start
    n_events = len(events)

    # Count fallback anchors
    n_fallback = sum(1 for e in events if e["anchor_source"] == "meeting_date_fallback")

    print(f"F-C: {n_mpc_total} MPC readouts loaded, {n_diffable} diffable pairs")
    print(f"     {n_events} event meetings (≥1 formula change)")
    print(f"     Anchor: publish_date used={n_events - n_fallback}, "
          f"meeting_date fallback={n_fallback}")
    if n_fallback > 0:
        print(f"     Fallback bias: MPC readouts publish within days of meeting; "
              f"fallback expected to have minimal bias (~0-3 day shift at most)")

    # Convert event anchors to DatetimeIndex
    anchor_dates_raw = pd.to_datetime(
        [e["anchor_date"] for e in events], errors="coerce"
    ).normalize()
    valid_mask = ~anchor_dates_raw.isna()
    events_valid = [e for e, ok in zip(events, valid_mask) if ok]
    anchor_dates = anchor_dates_raw[valid_mask]

    # Deduplicate same-date events (same-date same-family merge per prereg)
    dedup_map: dict = {}
    for ev, dt in zip(events_valid, anchor_dates):
        if dt not in dedup_map:
            dedup_map[dt] = ev
        else:
            # merge: union appeared/dropped
            dedup_map[dt]["appeared"] = sorted(
                set(dedup_map[dt]["appeared"]) | set(ev["appeared"])
            )
            dedup_map[dt]["dropped"] = sorted(
                set(dedup_map[dt]["dropped"]) | set(ev["dropped"])
            )

    events_deduped = list(dedup_map.values())
    event_dates_deduped = pd.DatetimeIndex(sorted(dedup_map.keys()))
    n_same_date_merges = n_events - len(events_deduped)
    if n_same_date_merges:
        print(f"     Same-date merge: {n_same_date_merges} collapsed")

    # ── Log trial in ledger ───────────────────────────────────────────────────
    _LED.log_trial(
        {"trial": "FC_mpc_communiques", "kind": "exploratory",
         "n_events": len(events_deduped), "n_fallback_anchor": n_fallback},
        family=FAMILY,
        note="EXPLORATORY/UNSIGNED per RUL-5 — phrase polarity unsigned, no verdict, no FDR",
    )

    # ── Compute CARs at all horizons ──────────────────────────────────────────
    # Build per-anchor-date lookup for slice tables
    event_date_to_cars: dict = {}

    horizon_rows: dict = {}
    for h in HORIZONS:
        cars_h, n_dropped = compute_car_series(
            event_dates_deduped, shcomp, None, h, cal, "absolute"
        )
        stats = _descriptive_stats(cars_h, label=f"FC->SHCOMP_h{h}")
        entry = {
            "h": h,
            "n_events_total": len(event_dates_deduped),
            "n_usable": len(cars_h),
            "n_dropped": n_dropped,
            **{k: v for k, v in stats.items() if k != "label"},
        }
        horizon_rows[f"h{h}"] = entry

        # Collect per-date CARs for slice tables
        for dt, car_val in cars_h.items():
            dt_str = str(dt)[:10]
            event_date_to_cars.setdefault(dt_str, {})[f"h{h}"] = car_val

    # Primary-H cars series for conditioning
    primary_cars_h, _ = compute_car_series(
        event_dates_deduped, shcomp, None, PRIMARY_H, cal, "absolute"
    )

    # ── Slice tables: APPEARED-only / DROPPED-only / BOTH ─────────────────────
    # Map deduped event anchor dates to events for slice logic
    events_by_anchor: dict = {}
    for ev, dt in zip(events_valid, anchor_dates):
        dt_str = str(dt)[:10]
        events_by_anchor.setdefault(dt_str, ev)

    slice_tables = compute_slice_tables(events_deduped, event_date_to_cars)

    # ── Conditioning tables ────────────────────────────────────────────────────
    conditioning = compute_fc_conditioning(
        event_dates_deduped, primary_cars_h, regime
    )

    # ── Notable appeared / dropped formulas ───────────────────────────────────
    # Count formula frequencies across all events
    appeared_counts: dict[str, int] = {}
    dropped_counts: dict[str, int] = {}
    for ev in events_deduped:
        for ph in ev.get("appeared", []):
            appeared_counts[ph] = appeared_counts.get(ph, 0) + 1
        for ph in ev.get("dropped", []):
            dropped_counts[ph] = dropped_counts.get(ph, 0) + 1

    top_appeared = sorted(appeared_counts.items(), key=lambda x: -x[1])[:5]
    top_dropped = sorted(dropped_counts.items(), key=lambda x: -x[1])[:5]

    print(f"\n  Top appeared formulas: {top_appeared[:3]}")
    print(f"  Top dropped formulas:  {top_dropped[:3]}")

    # ── Print main descriptive table ──────────────────────────────────────────
    print(f"\n=== F-C MPC Phrase-Diff — Descriptive (UNSIGNED / EXPLORATORY) ===")
    print(f"  All-change events: n={len(event_dates_deduped)}")
    print(f"  {'H':>4}  {'K':>5}  {'Mean':>8}  {'Median':>8}  {'HAC-t*':>8}  {'HAC-p*':>8}")
    for h in HORIZONS:
        row = horizon_rows[f"h{h}"]
        t = row.get("hac_t_exploratory") or "--"
        p = row.get("hac_p_exploratory") or "--"
        print(f"  {h:>4}  {row['n_usable']:>5}  "
              f"{(row['mean_car'] or 0)*100:>+7.2f}%  "
              f"{(row['median_car'] or 0)*100:>+7.2f}%  "
              f"{str(t):>8}  {str(p):>8}")
    print(f"  * HAC-t/p labeled EXPLORATORY — no verdict, not a gate")

    # Primary stats
    primary_stats = _descriptive_stats(primary_cars_h, label=f"FC->SHCOMP_h{PRIMARY_H}_ALL")

    # ── Build results dict ─────────────────────────────────────────────────────
    fc_result = {
        "label": "FC->SHCOMP_exploratory",
        "family": "F-C",
        "exploratory": True,
        "unsigned": True,
        "verdict": "EXPLORATORY",
        "no_verdict_note": (
            "F-C is EXPLORATORY/UNSIGNED per prereg RUL-5 — phrase polarity stays "
            "unsigned; no directional claim is made or permitted. "
            "No FDR membership. No wiring."
        ),
        "n_mpc_readouts": n_mpc_total,
        "n_diffable_pairs": n_diffable,
        "n_events_with_change": n_events,
        "n_same_date_merges": n_same_date_merges,
        "n_events_after_dedup": len(event_dates_deduped),
        "anchor_source": "publish_date primary; meeting_date fallback",
        "n_fallback_anchor": n_fallback,
        "fallback_bias_note": (
            "MPC readouts publish within days of meeting. Fallback expected "
            "~0-3 day shift; no systematic directional bias."
            if n_fallback > 0 else "No fallback anchors used."
        ),
        "top_appeared_formulas": [{"phrase": k, "count": v} for k, v in top_appeared],
        "top_dropped_formulas": [{"phrase": k, "count": v} for k, v in top_dropped],
        "horizons": horizon_rows,
        "primary_h": PRIMARY_H,
        "primary_stats": primary_stats,
        "slice_tables": slice_tables,
        "conditioning_tables": conditioning,
    }

    return fc_result


# ─────────────────────────────────────────────────────────────────────────────
# Update results JSON
# ─────────────────────────────────────────────────────────────────────────────

def update_results_json(fc_result: dict, results_path: pathlib.Path | None = None) -> None:
    """Replace the BLOCKED-DATA F-C stanza with actual results (schema-consistent)."""
    path = results_path or RESULTS_PATH
    with open(path) as f:
        results = json.load(f)

    # Replace both locations that held the BLOCKED-DATA status
    results["event_counts"]["FC_mpc_communiques"] = fc_result["n_events_after_dedup"]
    results["fc_status"] = (
        f"COMPLETED: {fc_result['n_events_after_dedup']} events from "
        f"{fc_result['n_mpc_readouts']} MPC readouts; EXPLORATORY/UNSIGNED"
    )

    # Replace the BLOCKED-DATA stanza in exploratory_trials
    results["exploratory_trials"]["FC_communiques"] = fc_result

    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Updated {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Append F-C section to the report
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:+.2f}%"


def _fmt_t(v: float | None) -> str:
    return str(v) if v is not None else "—"


def append_fc_report(fc_result: dict, report_path: pathlib.Path | None = None) -> None:
    """Append an F-C section to reports/china-policy-events-phase0.md."""
    path = report_path or REPORT_PATH

    # Build the phrase tables
    top_app = fc_result.get("top_appeared_formulas", [])
    top_drp = fc_result.get("top_dropped_formulas", [])

    def _phrase_rows(items: list[dict], n: int = 5) -> str:
        if not items:
            return "| — | — |\n"
        return "\n".join(
            f"| {it['phrase']} | {it['count']} |" for it in items[:n]
        ) + "\n"

    # Main horizon table
    horizons = fc_result.get("horizons", {})
    horizon_md_rows = ""
    for h in HORIZONS:
        row = horizons.get(f"h{h}", {})
        k = row.get("n_usable", "—")
        mean_ = _fmt_pct(row.get("mean_car"))
        median_ = _fmt_pct(row.get("median_car"))
        hac_t = _fmt_t(row.get("hac_t_exploratory"))
        bold = "**" if h == PRIMARY_H else ""
        horizon_md_rows += (
            f"| {bold}H={h}{bold} | {bold}{k}{bold} | "
            f"{bold}{mean_}{bold} | {bold}{median_}{bold} | "
            f"{bold}{hac_t} [exp.]{bold} |\n"
        )

    # Slice table
    slices = fc_result.get("slice_tables", {})
    def _slice_row(key: str, label: str) -> str:
        cell = slices.get(key, {})
        n = cell.get("n", 0)
        if n < 5:
            return f"| {label} | {n} | n<5 | n<5 |\n"
        return (f"| {label} | {n} | "
                f"{_fmt_pct(cell.get('mean_car_h20'))} | "
                f"{_fmt_pct(cell.get('median_car_h20'))} |\n")

    # Conditioning tables
    cond = fc_result.get("conditioning_tables", {})
    def _cond_table(col: str, title: str) -> str:
        tbl = cond.get(col, {})
        if not tbl:
            return f"*{title}: no data*\n\n"
        header = f"| {title.capitalize()} | n | Mean CAR@H20 | Median CAR@H20 |\n|---|---|---|---|\n"
        rows = ""
        for label_val, cell in sorted(tbl.items()):
            n = cell.get("n", 0)
            if n < 5:
                rows += f"| {label_val} | {n} | n<5 | n<5 |\n"
            else:
                rows += (f"| {label_val} | {n} | "
                         f"{_fmt_pct(cell.get('mean_car_h20'))} | "
                         f"{_fmt_pct(cell.get('median_car_h20'))} |\n")
        return header + rows + "\n"

    fallback_note = (
        f"publish_date used for {fc_result['n_events_after_dedup'] - fc_result['n_fallback_anchor']} "
        f"events; meeting_date fallback for {fc_result['n_fallback_anchor']}. "
        + (fc_result.get("fallback_bias_note", ""))
    )
    if fc_result["n_fallback_anchor"] == 0:
        fallback_note = "publish_date available for all events; no fallback used."

    section = f"""

---

## F-C MPC Communiqué Phrase-Diff Leg

**Status:** EXPLORATORY / UNSIGNED — no verdict, no FDR membership, no wiring.
This leg was BLOCKED-DATA in the original run. Data became available after
`scripts/backfill_china_communiques.py` ran (PR #1724).

**What this section contains:** Descriptive forward CAR tables for SHCOMP
following MPC readouts that contained ≥1 formula change vs the prior readout.
Phrase polarity is unsigned — no directional claim is made or permitted.
HAC t-statistics are shown but **labeled EXPLORATORY** — they are not gates,
they carry no verdict weight, and they do not enter any FDR family.

### Events

| Metric | Value |
|---|---|
| MPC readouts loaded | {fc_result['n_mpc_readouts']} |
| Diffable pairs | {fc_result['n_diffable_pairs']} |
| Events (≥1 formula change) | {fc_result['n_events_with_change']} |
| After same-date merge | {fc_result['n_events_after_dedup']} |
| Anchor fallback (meeting_date) | {fc_result['n_fallback_anchor']} |

Anchor note: {fallback_note}

> **In plain English:** Each PBoC Monetary Policy Committee quarterly readout is
> compared against the preceding one. If any phrase from the canonical phrase book
> appears for the first time (APPEARED) or disappears (DROPPED), the meeting is
> an "event". We then ask: how did the Shanghai Composite perform over the following
> 5 / 10 / 20 / 40 / 60 trading sessions? Because the phrase book's polarity is
> provisional and unsigned, we make no claim about *direction* — we simply measure
> what happened. This is a fact-finding exercise, not a signal.

### Main Table — All-Change Events → SHCOMP Absolute Log CAR

| Horizon | K usable | Mean CAR | Median CAR | HAC-t [exploratory] |
|---|---|---|---|---|
{horizon_md_rows}
*HAC NW t (lags=4) labeled EXPLORATORY — shown for reference, not a gate, no verdict.*

### Slice Tables (H=20 only — n/mean/median, no t-stats)

| Slice | n | Mean CAR@H20 | Median CAR@H20 |
|---|---|---|---|
{_slice_row('appeared_only', 'APPEARED-only events')}{_slice_row('dropped_only', 'DROPPED-only events')}{_slice_row('both', 'Both (appeared AND dropped)')}
*Cells n<5 show n only.*

### Top Appeared / Dropped Formulas (frequency across all events)

**Appeared (new formula in readout vs prior):**

| Formula | Times appeared |
|---|---|
{_phrase_rows(top_app)}
**Dropped (formula present in prior, absent in this readout):**

| Formula | Times dropped |
|---|---|
{_phrase_rows(top_drp)}

### Conditioning Tables (Descriptive — No t-stats, No Verdict Language)

Regime at anchor date (last known as-of). Cells n<5 print n only.

{_cond_table('quad', 'quad')}
{_cond_table('liquidity', 'liquidity')}
{_cond_table('cycle', 'cycle')}

> **In plain English:** We are looking at whether the market regime at the time of
> a phrase-change event seems to moderate the forward drift. These are counts and
> averages only — no claim about edge, no verdict. Any pattern here would need its
> own pre-registered test before it could be acted on.

### What This Leg Cannot Tell You

Because phrase polarity is UNSIGNED and this leg is EXPLORATORY:
- No claim is made about *which direction* a formula change predicts.
- No claim survives to FDR gating.
- Nothing here wires into any engine, board, or score.
- "APPEARED" does not mean bullish; "DROPPED" does not mean bearish.
- Any numeric observation is descriptive only — it requires a new pre-registered
  test (with its own budget) before it can be used as an investment input.
"""

    existing = path.read_text(encoding="utf-8") if path.exists() else ""

    # Remove any existing F-C section (idempotent)
    fc_marker = "\n---\n\n## F-C MPC Communiqué Phrase-Diff Leg"
    if fc_marker in existing:
        existing = existing[:existing.index(fc_marker)]

    updated = existing.rstrip() + "\n" + section
    path.write_text(updated, encoding="utf-8")
    print(f"Appended F-C section to {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def main() -> dict:
    print("=== F-C MPC Communiqué Phrase-Diff Leg ===")
    print(f"  Pre-registration: research/CHINA_POLICY_EVENTS_PREREG.md")
    print(f"  Status: EXPLORATORY / UNSIGNED per RUL-5")
    print()

    fc_result = run_fc_leg()
    update_results_json(fc_result)
    append_fc_report(fc_result)

    print("\n=== F-C Complete ===")
    print(f"  n events: {fc_result['n_events_after_dedup']}")
    print(f"  anchor fallback: {fc_result['n_fallback_anchor']}")
    print(f"  verdict: {fc_result['verdict']} (no further verdict possible — UNSIGNED)")
    return fc_result


if __name__ == "__main__":
    main()
