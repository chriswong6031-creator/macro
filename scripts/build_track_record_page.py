#!/usr/bin/env python3
"""build_track_record_page.py — Prophet W1: US Track Record sub-page builder.

Read-only over data inputs (NO ledger writes, NO network, NO data/ mutations).
Runs standalone (nightly CI) and locally for initial bake.

Writes:
  site/factordata/us_track_history.json  — cohort rollup artifact
  site/us_track_record.html              — Tier-3 depth page

Spec: research/PROPHET_MASTERPLAN_BY_FABLE.md §PR-R9.

Never-raise contract (SA-R16): every input read is wrapped; missing input renders
the page with honest plain-word accrual placeholders.

Ends with lib.procutil.hard_exit() — Arrow shutdown-hang law for parquet-reading
one-shots.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap sys.path so this script works as both `python scripts/build_track_record_page.py`
# and `python -m scripts.build_track_record_page`.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

# ---------------------------------------------------------------------------
# Paths (all read-only except the two output paths).
# ---------------------------------------------------------------------------
RETRO_GRADES = _ROOT / "data" / "us_board_ledger" / "retro_grades.parquet"
SNAPSHOTS_JSONL = _ROOT / "data" / "us_board_ledger" / "snapshots.jsonl"
US_BOARD_TRACK = _ROOT / "site" / "factordata" / "us_board_track.json"
US_BOARD_OUTCOMES = _ROOT / "site" / "factordata" / "us_board_outcomes.json"
US_AUDIT_SCOREBOARD = _ROOT / "site" / "factordata" / "us_audit_scoreboard.json"
US_ATTRIBUTION = _ROOT / "data" / "standout_audit" / "us_attribution.parquet"

OUT_JSON = _ROOT / "site" / "factordata" / "us_track_history.json"
OUT_HTML = _ROOT / "site" / "us_track_record.html"
TEMPLATE = _ROOT / "templates" / "us_track_record.html.j2"

# ---------------------------------------------------------------------------
# Effective-n helper — mirrors engine/standout_audit._effective_n (SA-R14).
# We import it directly; if that fails we reimplement the same algorithm.
# ---------------------------------------------------------------------------
try:
    from engine.standout_audit import _effective_n, _wilson_ci  # type: ignore
    log.info("Using _effective_n/_wilson_ci from engine.standout_audit")
except Exception:  # noqa: BLE001
    import math

    def _effective_n(  # type: ignore[override]
        dates: list,
        horizon_days: int = 21,
        session_dates: list | None = None,
    ) -> int:
        """Non-overlapping window count — mirrors engine/standout_audit._effective_n."""
        if not dates:
            return 0
        try:
            import pandas as pd  # local import, not always needed

            unique_dates = sorted(
                set(
                    pd.Timestamp(d).normalize()
                    for d in dates
                    if pd.notna(d) and str(d).strip()
                )
            )
            if not unique_dates:
                return 0
            if session_dates is not None:
                all_sessions = sorted(
                    set(
                        pd.Timestamp(d).normalize()
                        for d in session_dates
                        if pd.notna(d) and str(d).strip()
                    )
                )
                session_idx = {d: i for i, d in enumerate(all_sessions)}

                def _to_ord(ts):
                    if ts in session_idx:
                        return session_idx[ts]
                    return sum(1 for s in all_sessions if s <= ts) - 1

                count = 1
                last_ord = _to_ord(unique_dates[0])
                for d in unique_dates[1:]:
                    ord_ = _to_ord(d)
                    if ord_ - last_ord >= horizon_days:
                        count += 1
                        last_ord = ord_
            else:
                count = 1
                last_start = unique_dates[0]
                for d in unique_dates[1:]:
                    if (d - last_start).days >= horizon_days:
                        count += 1
                        last_start = d
            return count
        except Exception as exc:  # noqa: BLE001
            log.warning("_effective_n fallback: %s", exc)
            return 0

    def _wilson_ci(hits: int, n: int, z: float = 1.645) -> tuple[float, float]:  # type: ignore[override]
        """Wilson CI. Returns (lo, hi)."""
        if n <= 0:
            return 0.0, 0.0
        p_hat = hits / n
        denom = 1.0 + z**2 / n
        center = (p_hat + z**2 / (2 * n)) / denom
        spread = (
            z * ((p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) ** 0.5) / denom
        )
        lo = max(0.0, center - spread)
        hi = min(1.0, center + spread)
        return round(lo, 4), round(hi, 4)

    log.warning("engine.standout_audit not importable — using local _effective_n/_wilson_ci")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_json_load(path: Path) -> dict | None:
    """Load JSON file; return None on any error."""
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not load %s: %s", path, exc)
        return None


def _safe_parquet_load(path: Path):
    """Load parquet; return None on any error."""
    try:
        import pandas as pd  # local, only when needed
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not load %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Cohort rollup computation
# ---------------------------------------------------------------------------

def _compute_cohort_rollup(df) -> dict:
    """Compute weekly cohort win-rate series and return distribution bins.

    Matured rows only (non-null excess_spy). Per horizon.
    Returns dict with per-horizon cells + return distribution.

    Never raises — returns accruing placeholders on any error.
    """
    try:
        import pandas as pd

        if df is None or df.empty:
            return {"accruing": True, "reason": "no retro_grades data", "horizons": {}}

        # Session dates: all unique entry_dates in the ledger (for session-ordinal eff_n)
        session_dates = sorted(df["entry_date"].dropna().unique().tolist())

        results: dict[str, object] = {"horizons": {}, "accruing": False}

        for h in [5, 10, 21, 63]:
            sub = df[df["horizon"] == h].copy()
            matured = sub[sub["excess_spy"].notna()].copy()
            raw_n = len(matured)

            if raw_n == 0:
                results["horizons"][f"h{h}"] = {
                    "accruing": True,
                    "raw_n": 0,
                    "effective_n": 0,
                    "reason": f"no matured rows for {h}d horizon yet",
                    "cohort_series": [],
                }
                continue

            # Entry dates for effective_n
            entry_dates = matured["entry_date"].dropna().tolist()
            eff_n = _effective_n(entry_dates, horizon_days=21, session_dates=session_dates)

            # Overall stats
            n_wins = (matured["excess_spy"] > 0).sum()
            win_rate = float(n_wins / raw_n)
            avg_excess = float(matured["excess_spy"].mean())
            med_excess = float(matured["excess_spy"].median())

            # Wilson CI on cluster units (eff_n)
            n_cluster_wins = 0
            if eff_n > 0:
                # Approximate: scale hits proportionally to eff_n
                n_cluster_wins = round(win_rate * eff_n)
            w_lo, w_hi = _wilson_ci(n_cluster_wins, eff_n) if eff_n > 0 else (0.0, 0.0)

            accruing = eff_n < 3

            # Weekly cohort series: group by ISO week of entry_date
            matured["_entry_week"] = pd.to_datetime(
                matured["entry_date"], errors="coerce"
            ).dt.to_period("W").astype(str)
            weekly = matured.groupby("_entry_week").agg(
                n=("excess_spy", "count"),
                win_rate=("excess_spy", lambda x: float((x > 0).sum() / len(x))),
                avg_excess=("excess_spy", "mean"),
                med_excess=("excess_spy", "median"),
                entry_dates=("entry_date", list),
            )
            cohort_series = []
            for week_label, row in weekly.iterrows():
                dates_in_week = [str(d) for d in (row["entry_dates"] or [])]
                e_n = _effective_n(dates_in_week, horizon_days=21, session_dates=session_dates)
                cohort_series.append(
                    {
                        "week": str(week_label),
                        "raw_n": int(row["n"]),
                        "effective_n": int(e_n),
                        "win_rate": round(float(row["win_rate"]), 4),
                        "avg_excess": round(float(row["avg_excess"]), 4),
                        "med_excess": round(float(row["med_excess"]), 4),
                    }
                )

            results["horizons"][f"h{h}"] = {
                "accruing": accruing,
                "raw_n": raw_n,
                "effective_n": eff_n,
                "win_rate": round(win_rate, 4),
                "avg_excess": round(avg_excess, 4),
                "med_excess": round(med_excess, 4),
                "wilson_lo": w_lo,
                "wilson_hi": w_hi,
                "cohort_series": cohort_series,
            }

        # Return distribution (21d excess, matured rows only)
        dist_df = df[(df["horizon"] == 21) & df["excess_spy"].notna()]
        if not dist_df.empty:
            vals = dist_df["excess_spy"].tolist()
            # 10 bins, rounded to 3 decimal places
            import numpy as np  # local; acceptable for one-shot

            counts, edges = np.histogram(vals, bins=10)
            results["return_distribution_21d"] = {
                "raw_n": len(vals),
                "bins": [
                    {
                        "lo": round(float(edges[i]), 4),
                        "hi": round(float(edges[i + 1]), 4),
                        "count": int(counts[i]),
                    }
                    for i in range(len(counts))
                ],
                "accruing": True,  # 21d matured = 0 at launch; will fill post-launch
            }
        else:
            results["return_distribution_21d"] = {
                "accruing": True,
                "reason": "no matured 21d rows yet",
                "bins": [],
                "raw_n": 0,
            }

        return results

    except Exception as exc:  # noqa: BLE001
        log.warning("_compute_cohort_rollup failed: %s", exc, exc_info=True)
        return {"accruing": True, "reason": str(exc), "horizons": {}}


def _compute_board_series(snapshots_path: Path) -> dict:
    """Board-size + lane-mix series from snapshots.jsonl."""
    try:
        series = []
        if not snapshots_path.exists():
            return {"accruing": True, "reason": "snapshots.jsonl absent", "series": []}
        with open(snapshots_path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                snap = json.loads(line)
                as_of = snap.get("as_of", "")
                board = snap.get("board", [])
                by_lane: dict[str, int] = {}
                for entry in board:
                    lane = entry.get("lane", "unknown")
                    by_lane[lane] = by_lane.get(lane, 0) + 1
                series.append(
                    {
                        "as_of": as_of,
                        "total": len(board),
                        "by_lane": by_lane,
                    }
                )
        return {"series": series, "accruing": len(series) < 3}
    except Exception as exc:  # noqa: BLE001
        log.warning("_compute_board_series failed: %s", exc)
        return {"accruing": True, "reason": str(exc), "series": []}


def _compute_failure_mix(attr_path: Path) -> dict:
    """Failure-mode mix over time from us_attribution.parquet."""
    try:
        if not attr_path.exists():
            return {
                "data_gap": True,
                "reason": "us_attribution.parquet absent — SA-R15 data_gap sentinel",
                "mix": [],
            }
        df = _safe_parquet_load(attr_path)
        if df is None or df.empty:
            return {
                "data_gap": True,
                "reason": "us_attribution.parquet empty",
                "mix": [],
            }
        # Count outcome_cause and process_fault columns if present
        outcome_cols = [c for c in df.columns if "cause" in c.lower() or "fault" in c.lower()]
        if not outcome_cols:
            return {
                "data_gap": True,
                "reason": "attribution columns absent (accruing)",
                "mix": [],
            }
        mix = {}
        for col in outcome_cols[:4]:
            vc = df[col].value_counts(dropna=True).to_dict()
            mix[col] = {str(k): int(v) for k, v in vc.items()}
        return {"data_gap": False, "mix": mix, "raw_n": len(df)}
    except Exception as exc:  # noqa: BLE001
        log.warning("_compute_failure_mix failed: %s", exc)
        return {"data_gap": True, "reason": str(exc), "mix": []}


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build() -> int:
    """Build us_track_history.json and us_track_record.html.

    Returns 0 on success (page always rendered; failures become placeholders).
    """
    as_of = date.today().isoformat()

    # ── 1. Load inputs ──────────────────────────────────────────────────────
    df_grades = _safe_parquet_load(RETRO_GRADES)
    board_track_json = _safe_json_load(US_BOARD_TRACK)
    outcomes_json = _safe_json_load(US_BOARD_OUTCOMES)
    scoreboard_json = _safe_json_load(US_AUDIT_SCOREBOARD)

    # ── 2. Compute ──────────────────────────────────────────────────────────
    cohort_rollup = _compute_cohort_rollup(df_grades)
    board_series = _compute_board_series(SNAPSHOTS_JSONL)
    failure_mix = _compute_failure_mix(US_ATTRIBUTION)

    # ── 3. Assemble us_track_history.json ────────────────────────────────────
    track_history: dict = {
        "schema": "us_track_history/v1",
        "as_of": as_of,
        "generated": datetime.utcnow().isoformat() + "+00:00",
        "cohort_rollup": cohort_rollup,
        "board_series": board_series,
        "failure_mix": failure_mix,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(track_history, indent=2, default=str))
    log.info("Wrote %s", OUT_JSON)

    # ── 4. Assemble template view-model ─────────────────────────────────────
    # Glance hero stats from outcomes_json summary
    outcomes_summary = (outcomes_json or {}).get("summary", {})
    win_rate_pct = None
    avg_pct = None
    n_outcomes = None
    n_running = outcomes_summary.get("n_running")
    n_stopped = outcomes_summary.get("n_stopped")
    n_total = outcomes_summary.get("n_total")
    n_skipped = outcomes_summary.get("n_skipped_no_price", 0)
    outcomes_as_of = (outcomes_json or {}).get("as_of", as_of)

    if outcomes_summary.get("win_rate") is not None:
        win_rate_pct = round(float(outcomes_summary["win_rate"]) * 100)
    if outcomes_summary.get("avg_pct") is not None:
        avg_pct = round(float(outcomes_summary["avg_pct"]), 1)
    if n_total is not None:
        n_outcomes = n_total

    # Board track horizon ladder from us_board_track.json
    horizon_ladder = []
    if board_track_json:
        per_h = board_track_json.get("per_horizon", {})
        for h_key in ["h5", "h10", "h21", "h63"]:
            cell = per_h.get(h_key, {})
            ovs = cell.get("overall_vs_spy", {})
            raw_n = ovs.get("n", 0)
            # Also get effective_n from cohort_rollup
            cr_cell = cohort_rollup.get("horizons", {}).get(h_key, {})
            eff_n = cr_cell.get("effective_n", 0)
            accruing = cr_cell.get("accruing", raw_n == 0)
            h_num = int(h_key[1:])
            horizon_ladder.append(
                {
                    "horizon": h_num,
                    "raw_n": raw_n,
                    "effective_n": eff_n,
                    "hit_rate": ovs.get("hit_rate"),
                    "wilson_lo": ovs.get("wilson_lo"),
                    "wilson_hi": ovs.get("wilson_hi"),
                    "median_excess": ovs.get("median_excess"),
                    "mean_excess": ovs.get("mean_excess"),
                    "accruing": accruing,
                }
            )

    # Cohort series for chart (use h5 as most populated)
    chart_series_h5 = []
    chart_series_h10 = []
    for h_key, target in [("h5", chart_series_h5), ("h10", chart_series_h10)]:
        cell = cohort_rollup.get("horizons", {}).get(h_key, {})
        target.extend(cell.get("cohort_series", []))

    # Scoreboard coverage monitor
    coverage_monitor = (scoreboard_json or {}).get("coverage_monitor", {})
    gate_suppressed = (scoreboard_json or {}).get("gate_suppressed", {})
    sb_as_of = (scoreboard_json or {}).get("as_of", as_of)
    buy_lane_rows = (scoreboard_json or {}).get("buy_lane_rows", 0)
    all_lanes_rows = (scoreboard_json or {}).get("all_lanes_rows", 0)

    # Outcomes table rows (top 60 shown)
    outcomes_rows = (outcomes_json or {}).get("rows", [])

    # Survivorship note
    survivorship = (board_track_json or {}).get("survivorship", {})

    vm = {
        "as_of": as_of,
        "outcomes_as_of": outcomes_as_of,
        "sb_as_of": sb_as_of,
        # Glance hero
        "win_rate_pct": win_rate_pct,
        "avg_pct": avg_pct,
        "n_outcomes": n_outcomes,
        "n_running": n_running,
        "n_stopped": n_stopped,
        "n_skipped": n_skipped,
        # Horizon ladder
        "horizon_ladder": horizon_ladder,
        # Chart series (inline JSON for JS)
        "chart_series_h5_json": json.dumps(chart_series_h5),
        "chart_series_h10_json": json.dumps(chart_series_h10),
        # Board series
        "board_series": board_series.get("series", []),
        "board_series_accruing": board_series.get("accruing", True),
        # Outcomes table
        "outcomes_rows": outcomes_rows,
        # Failure mix
        "failure_mix_data_gap": failure_mix.get("data_gap", True),
        "failure_mix": failure_mix.get("mix", {}),
        # Coverage monitor
        "coverage_monitor": coverage_monitor,
        "gate_suppressed": gate_suppressed,
        "buy_lane_rows": buy_lane_rows,
        "all_lanes_rows": all_lanes_rows,
        # Survivorship
        "survivorship": survivorship,
        # Overall accrual
        "cohort_accruing": cohort_rollup.get("accruing", False),
        "track_history": track_history,
    }

    # ── 5. Render HTML ───────────────────────────────────────────────────────
    from jinja2 import Environment, FileSystemLoader  # noqa: E402

    env = Environment(
        loader=FileSystemLoader(str(_ROOT / "templates")),
        autoescape=True,
    )
    html = env.get_template("us_track_record.html.j2").render(**vm)
    write_page(OUT_HTML, html)
    log.info("Wrote %s", OUT_HTML)

    return 0


if __name__ == "__main__":
    rc = build()
    from lib.procutil import hard_exit  # noqa: E402  # Arrow shutdown-hang law

    hard_exit(rc)
