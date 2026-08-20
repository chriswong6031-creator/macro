#!/usr/bin/env python3
"""Temporary Turn-3 exact-price replay harness.

Research-only scratch code. It reads the repository's committed current-vintage
Yahoo parquets and writes compact text outputs under scratch_outputs/. It does
not alter any production artifact, model, score, gate, rank, or workflow.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch_outputs"
OUT.mkdir(parents=True, exist_ok=True)

HORIZONS = (5, 10, 20, 40, 60)
CONFIRM_WINDOWS = {"H2": 10, "H3": 20, "H4": 20}
CONFIRM_SEARCH_SESSIONS = 60

EVENTS: list[dict[str, Any]] = [
    {
        "event_id": "EXK-2016-01-28-GUIDANCE-CUT",
        "first_tradable_date": "2016-01-28",
        "family": "commodity_economics_control",
        "recoverable": False,
        "control": True,
        "structural": False,
        "public_state": "price_contingent_plan",
        "description": "Production reduction and El Cubo care-and-maintenance plan in low metal prices.",
    },
    {
        "event_id": "EXK-2018-08-29-AUSTERITY-SEQUENCE",
        "first_tradable_date": "2018-08-29",
        "family": "mixed_operational_and_sequencing",
        "recoverable": True,
        "control": False,
        "structural": False,
        "public_state": "adverse_with_known_positive_followup",
        "description": "Cost cuts and temporary El Compas halt; finalized Terronera PFS announced for next morning.",
        "mitigation_or_positive_date": "2018-08-30",
    },
    {
        "event_id": "EXK-2018-12-17-EL-CUBO-CUT",
        "first_tradable_date": "2018-12-17",
        "family": "operational_deterioration",
        "recoverable": False,
        "control": False,
        "structural": True,
        "public_state": "planned_capacity_cut_and_layoffs",
        "description": "El Cubo production planned at roughly half capacity with major layoffs.",
    },
    {
        "event_id": "EXK-2019-05-30-TURNAROUND",
        "first_tradable_date": "2019-05-30",
        "family": "corrective_kitchen_sink",
        "recoverable": True,
        "control": False,
        "structural": False,
        "public_state": "adverse_with_management_plan",
        "description": "Operational restructuring, cost cuts, workforce reduction, losses and H2 recovery objective.",
        "mitigation_or_positive_date": "2019-06-05",
    },
    {
        "event_id": "EXK-2019-07-02-FATALITY",
        "first_tradable_date": "2019-07-02",
        "family": "safety_control",
        "recoverable": False,
        "control": True,
        "structural": False,
        "public_state": "low_discretion_adverse_control",
        "description": "Fatal accident control.",
    },
    {
        "event_id": "EXK-2019-11-21-EL-CUBO-SUSPEND",
        "first_tradable_date": "2019-11-21",
        "family": "structural_impairment",
        "recoverable": False,
        "control": False,
        "structural": True,
        "public_state": "reserve_exhaustion",
        "description": "El Cubo suspension after economic reserves/resources were exhausted.",
    },
    {
        "event_id": "EXK-2020-04-02-COVID-SUSPEND",
        "first_tradable_date": "2020-04-02",
        "family": "macro_nondiscretionary_control",
        "recoverable": False,
        "control": True,
        "structural": False,
        "public_state": "government_mandated_shutdown",
        "description": "Mexico-mandated suspension of mines and guidance withdrawal.",
    },
    {
        "event_id": "EXK-2023-11-07-GUANACEVI-SHORTFALL",
        "first_tradable_date": "2023-11-07",
        "family": "recoverable_operational_shortfall",
        "recoverable": True,
        "control": False,
        "structural": False,
        "public_state": "adverse_with_claimed_remediation",
        "description": "Production shortfall, lower grades, repairs and high costs; management said sequencing was improving.",
        "mitigation_or_positive_date": "2024-01-09",
    },
    {
        "event_id": "EXK-2024-08-12-TRUNNION",
        "first_tradable_date": "2024-08-12",
        "family": "temporary_mechanical",
        "recoverable": True,
        "control": False,
        "structural": False,
        "public_state": "open_ended_repairable_failure",
        "description": "Primary ball-mill trunnion failure; processing suspended; replacement could take up to 12 weeks.",
        "mitigation_or_positive_date": "2024-08-19",
        "resolution_date": "2024-12-17",
    },
    {
        "event_id": "EXK-2025-01-08-TERRONERA-STEEL-DELAY",
        "first_tradable_date": "2025-01-08",
        "family": "construction_delay",
        "recoverable": True,
        "control": False,
        "structural": False,
        "public_state": "bounded_project_delay",
        "description": "Critical-path structural-steel delivery delays shifted wet commissioning.",
    },
    {
        "event_id": "EXK-2026-02-27-TERRONERA-SECURITY-PAUSE",
        "first_tradable_date": "2026-02-27",
        "family": "resolved_before_disclosure_control",
        "recoverable": True,
        "control": True,
        "structural": False,
        "public_state": "resolved_before_public_t0",
        "description": "Security/blockade pause disclosed after normal operations resumed.",
        "resolution_date": "2026-02-25",
    },
    {
        "event_id": "EXK-2026-08-17-TERRONERA-BLOCKADE",
        "first_tradable_date": "2026-08-17",
        "family": "community_blockade",
        "recoverable": True,
        "control": False,
        "structural": False,
        "public_state": "open_ended_potentially_reversible",
        "description": "Terronera suspended since August 12; blockade unresolved at public t0.",
        "live": True,
    },
]

EXCLUDED_CLOCK_PENDING = [
    "EXK-2017-GUANACEVI-CLUSTER",
    "EXK-2019-EL-COMPAS-BALL-MILL",
    "EXK-2021-EL-COMPAS-SUSPEND",
    "EXK-2025-Q3-RESISTOR-SHUTDOWN",
    "EXK-2026-Q1-TEMPORARY-PAUSES",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_price_path(symbol: str) -> Path:
    candidates = [
        ROOT / "data" / "yahoo" / f"{symbol}.parquet",
        ROOT / "data" / "stocks" / f"{symbol}.parquet",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"no price file for {symbol}: {candidates}")


def load_close(symbol: str) -> tuple[pd.Series, dict[str, Any]]:
    path = find_price_path(symbol)
    frame = pd.read_parquet(path)
    if "Date" in frame.columns:
        frame = frame.set_index("Date")
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    close_col = next(
        (name for name in ("close_price", "close", "Close", "adj_close", "Adj Close") if name in frame.columns),
        None,
    )
    if close_col is None:
        raise KeyError(f"{symbol}: no close column in {list(frame.columns)}")
    series = pd.to_numeric(frame[close_col], errors="coerce").dropna().astype(float)
    meta = {
        "symbol": symbol,
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "rows": int(len(series)),
        "first_date": series.index.min().date().isoformat(),
        "last_date": series.index.max().date().isoformat(),
        "close_column": close_col,
        "columns": [str(c) for c in frame.columns],
        "last_close": float(series.iloc[-1]),
    }
    return series.rename(symbol), meta


def session_on_or_after(index: pd.DatetimeIndex, date: str) -> int | None:
    pos = int(index.searchsorted(pd.Timestamp(date), side="left"))
    return pos if pos < len(index) else None


def metrics_for_entry(
    panel: pd.DataFrame,
    entry_pos: int | None,
    *,
    trigger_pos: int | None = None,
) -> dict[str, Any]:
    if entry_pos is None or entry_pos >= len(panel):
        return {"entry_available": False}
    entry = panel.iloc[entry_pos]
    result: dict[str, Any] = {
        "entry_available": True,
        "entry_date": panel.index[entry_pos].date().isoformat(),
        "entry_exk": float(entry["EXK"]),
        "entry_sil": float(entry["SIL"]),
        "entry_slv": float(entry["SLV"]),
        "entry_ratio_exk_sil": float(entry["ratio_exk_sil"]),
        "entry_basis": "first_public_tradable_close"
        if trigger_pos is None
        else "next_session_close_after_relative_confirmation",
        "trigger_date": None if trigger_pos is None else panel.index[trigger_pos].date().isoformat(),
    }
    for h in HORIZONS:
        end_pos = entry_pos + h
        if end_pos >= len(panel):
            result[f"ret_{h}d"] = None
            result[f"rel_sil_{h}d"] = None
            result[f"rel_slv_{h}d"] = None
            continue
        end = panel.iloc[end_pos]
        result[f"ret_{h}d"] = float(end["EXK"] / entry["EXK"] - 1.0)
        result[f"rel_sil_{h}d"] = float(
            (end["EXK"] / entry["EXK"]) / (end["SIL"] / entry["SIL"]) - 1.0
        )
        result[f"rel_slv_{h}d"] = float(
            (end["EXK"] / entry["EXK"]) / (end["SLV"] / entry["SLV"]) - 1.0
        )
    for h in (20, 40, 60):
        end_pos = min(entry_pos + h, len(panel) - 1)
        path = panel.iloc[entry_pos : end_pos + 1]["EXK"] / float(entry["EXK"]) - 1.0
        result[f"mfe_close_{h}d"] = float(path.max())
        result[f"mae_close_{h}d"] = float(path.min())
        result[f"path_sessions_{h}d"] = int(len(path) - 1)
        result[f"matured_{h}d"] = bool(entry_pos + h < len(panel))
    end_pos = min(entry_pos + 60, len(panel) - 1)
    path = panel.iloc[entry_pos + 1 : end_pos + 1]["EXK"] / float(entry["EXK"]) - 1.0
    positives = np.flatnonzero(path.to_numpy() > 0.0)
    result["time_to_positive_60d"] = None if len(positives) == 0 else int(positives[0] + 1)
    result["time_underwater_60d"] = int((path < 0.0).sum())
    result["target_before_invalidation"] = None
    result["failed_breakout"] = None
    result["unscored_metric_note"] = (
        "target/invalidation and failed-breakout remain null because no stop/target failure law "
        "was frozen before outcome reads"
    )
    return result


def confirmation_entry(
    panel: pd.DataFrame,
    armed_pos: int,
    window: int,
) -> tuple[int | None, int | None]:
    ratio = panel["ratio_exk_sil"]
    limit = min(armed_pos + CONFIRM_SEARCH_SESSIONS, len(panel) - 1)
    for pos in range(armed_pos + 1, limit + 1):
        if pos < window:
            continue
        prior = ratio.iloc[pos - window : pos]
        if len(prior) == window and float(ratio.iloc[pos]) > float(prior.max()):
            entry_pos = pos + 1 if pos + 1 < len(panel) else None
            return pos, entry_pos
    return None, None


def build_event_rows(panel: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in EVENTS:
        armed_pos = session_on_or_after(panel.index, event["first_tradable_date"])
        base = dict(event)
        base["armed_session"] = (
            None if armed_pos is None else panel.index[armed_pos].date().isoformat()
        )
        for arm in ("H0", "H1", "H2", "H3", "H4"):
            row = dict(base)
            row["arm"] = arm
            eligible = True
            if arm in ("H1", "H4") and not event["recoverable"]:
                eligible = False
            row["arm_eligible"] = eligible
            if not eligible or armed_pos is None:
                row.update({"entry_available": False, "eligibility_reason": "not_in_arm"})
                rows.append(row)
                continue
            if arm in ("H0", "H1"):
                row.update(metrics_for_entry(panel, armed_pos))
            else:
                window = CONFIRM_WINDOWS[arm]
                trigger_pos, entry_pos = confirmation_entry(panel, armed_pos, window)
                row["confirmation_window"] = window
                row["confirmation_search_sessions"] = CONFIRM_SEARCH_SESSIONS
                row["trigger_found"] = trigger_pos is not None
                row["sessions_to_trigger"] = (
                    None if trigger_pos is None else int(trigger_pos - armed_pos)
                )
                row.update(metrics_for_entry(panel, entry_pos, trigger_pos=trigger_pos))
            rows.append(row)
    return rows


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frame = pd.DataFrame(rows)
    out: list[dict[str, Any]] = []
    for arm, group in frame.groupby("arm", sort=True):
        eligible = group[group["arm_eligible"] == True]  # noqa: E712
        entered = eligible[eligible["entry_available"] == True]  # noqa: E712
        record: dict[str, Any] = {
            "arm": arm,
            "n_events_eligible": int(len(eligible)),
            "n_entries": int(len(entered)),
            "n_controls_entered": int(entered.get("control", pd.Series(dtype=bool)).fillna(False).sum()),
            "n_structural_entered": int(entered.get("structural", pd.Series(dtype=bool)).fillna(False).sum()),
            "n_recoverable_entered": int(entered.get("recoverable", pd.Series(dtype=bool)).fillna(False).sum()),
        }
        for h in HORIZONS:
            for field in (f"ret_{h}d", f"rel_sil_{h}d", f"rel_slv_{h}d"):
                values = pd.to_numeric(entered.get(field), errors="coerce").dropna()
                record[f"{field}_n"] = int(len(values))
                record[f"{field}_median"] = None if values.empty else float(values.median())
                record[f"{field}_mean"] = None if values.empty else float(values.mean())
                record[f"{field}_positive_share"] = (
                    None if values.empty else float((values > 0.0).mean())
                )
        out.append(record)
    return out


def current_case(panel: pd.DataFrame, rows: list[dict[str, Any]]) -> dict[str, Any]:
    event_id = "EXK-2026-08-17-TERRONERA-BLOCKADE"
    event_rows = [r for r in rows if r["event_id"] == event_id]
    armed_pos = session_on_or_after(panel.index, "2026-08-17")
    latest_pos = len(panel) - 1
    ratio = panel["ratio_exk_sil"]
    prior20 = ratio.iloc[max(0, armed_pos - 20) : armed_pos]
    pre_high = None if prior20.empty else float(prior20.max())
    pre_high_date = (
        None if prior20.empty else prior20.idxmax().date().isoformat()
    )
    current_ratio = float(ratio.iloc[latest_pos])
    h3 = next(row for row in event_rows if row["arm"] == "H3")
    return {
        "schema": "mastermind.opportunity_case.exk_turn3.v0",
        "authority": {
            "can_rank": False,
            "can_gate": False,
            "can_size": False,
            "can_originate_signal": False,
            "can_escalate": False,
        },
        "issuer_event": {
            "event_id": event_id,
            "issuer": "Endeavour Silver Corp.",
            "asset": "Terronera",
            "event_occurred_at": "2026-08-12",
            "source_available_at": "2026-08-16T21:00:00-04:00",
            "first_tradable_at": "2026-08-17",
            "event_family": "community_blockade",
            "duration_state": "open_ended_at_public_t0",
            "repairability": "potentially_reversible",
            "intent_orchestration": "UNKNOWN",
        },
        "listing_reaction": {
            "listing": "EXK",
            "venue": "NYSE",
            "primary_benchmark": "SIL",
            "armed_close": float(panel.iloc[armed_pos]["EXK"]),
            "latest_date": panel.index[latest_pos].date().isoformat(),
            "latest_close": float(panel.iloc[latest_pos]["EXK"]),
            "current_exk_sil_ratio": current_ratio,
            "pre_event_20_session_ratio_high": pre_high,
            "pre_event_ratio_high_date": pre_high_date,
            "gap_to_ratio_high": None if pre_high is None else current_ratio / pre_high - 1.0,
        },
        "recovery_formation": {
            "state": "CONFIRMED_20" if h3.get("trigger_found") else "STABILIZING_NOT_CONFIRMED",
            "h3_trigger_found": bool(h3.get("trigger_found")),
            "h3_trigger_date": h3.get("trigger_date"),
            "h3_entry_date": h3.get("entry_date"),
        },
        "historical_analogs": {
            "within_issuer_success": ["EXK-2024-08-12-TRUNNION"],
            "within_issuer_failure_or_early_false_start": ["EXK-2023-11-07-GUANACEVI-SHORTFALL"],
            "same_mechanism_resolved_before_disclosure": [
                "EXK-2026-02-27-TERRONERA-SECURITY-PAUSE"
            ],
            "structural_control": ["EXK-2019-11-21-EL-CUBO-SUSPEND"],
            "macro_control": ["EXK-2020-04-02-COVID-SUSPEND"],
        },
        "prophet_conviction": {"state": "NOT_JOINED_IN_THIS_REPLAY"},
        "entry_availability": {"state": "NOT_JOINED_IN_THIS_REPLAY"},
        "uncertainty": [
            "official-release body compiler not part of price replay",
            "current-vintage adjusted prices are not frozen point-in-time adjustments",
            "small event sample",
            "target/invalidation failure law not frozen",
        ],
    }


def md_pct(value: Any) -> str:
    return "—" if value is None or pd.isna(value) else f"{float(value) * 100:.2f}%"


def write_report(
    panel: pd.DataFrame,
    metas: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    aggregates: list[dict[str, Any]],
    case: dict[str, Any],
) -> None:
    event_frame = pd.DataFrame(rows)
    lines = [
        "# EXK Turn 3 — Exact Repository-Price Replay",
        "",
        f"**Repo commit:** `{os.getenv('GITHUB_SHA', 'local')}`",
        f"**Price span:** {panel.index.min().date()} → {panel.index.max().date()}",
        "**Adjustment:** vendor current-vintage adjusted closes; not a frozen PIT adjustment.",
        "**Authority:** research/display only. No ranking, gating, sizing or signal origination.",
        "",
        "## Input receipts",
        "",
        "| Symbol | Rows | Span | Last close | SHA-256 |",
        "|---|---:|---|---:|---|",
    ]
    for meta in metas:
        lines.append(
            f"| {meta['symbol']} | {meta['rows']} | {meta['first_date']} → {meta['last_date']} "
            f"| {meta['last_close']:.4f} | `{meta['sha256'][:16]}…` |"
        )
    lines += [
        "",
        "## Honest event population",
        "",
        f"- Confirmatory-clock events in replay: **{len(EVENTS)}** distinct events.",
        f"- Clock-pending events excluded before outcome reads: **{len(EXCLUDED_CLOCK_PENDING)}**.",
        "- Linked mitigation/resolution releases do not increase adverse-event N.",
        "- Controls and structural events remain visible and are not pooled invisibly with recoverable events.",
        "",
        "## Arm summary",
        "",
        "| Arm | Eligible | Entries | +20d median | +20d SIL-relative | +40d median | +40d SIL-relative |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for record in aggregates:
        lines.append(
            f"| {record['arm']} | {record['n_events_eligible']} | {record['n_entries']} "
            f"| {md_pct(record.get('ret_20d_median'))} "
            f"| {md_pct(record.get('rel_sil_20d_median'))} "
            f"| {md_pct(record.get('ret_40d_median'))} "
            f"| {md_pct(record.get('rel_sil_40d_median'))} |"
        )
    lines += [
        "",
        "## Event-level entries",
        "",
        "| Event | Family | Arm | Trigger | Entry | +20d | SIL-rel +20d | +40d | SIL-rel +40d | MAE 40d |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in event_frame[event_frame["arm"].isin(["H0", "H1", "H2", "H3", "H4"])].iterrows():
        if not bool(row.get("arm_eligible", False)):
            continue
        lines.append(
            f"| {row['event_id']} | {row['family']} | {row['arm']} "
            f"| {row.get('trigger_date') or '—'} | {row.get('entry_date') or '—'} "
            f"| {md_pct(row.get('ret_20d'))} | {md_pct(row.get('rel_sil_20d'))} "
            f"| {md_pct(row.get('ret_40d'))} | {md_pct(row.get('rel_sil_40d'))} "
            f"| {md_pct(row.get('mae_close_40d'))} |"
        )
    lines += [
        "",
        "## Current 2026 OpportunityCase",
        "",
        f"- State: **{case['recovery_formation']['state']}**",
        f"- H3 trigger: **{case['recovery_formation']['h3_trigger_found']}**",
        f"- Latest listing date: **{case['listing_reaction']['latest_date']}**",
        f"- Ratio gap to pre-event 20-session high: "
        f"**{md_pct(case['listing_reaction']['gap_to_ratio_high'])}**",
        "",
        "## Frozen limitations",
        "",
        "- H0/H1 use the first public tradable close.",
        "- H2/H3/H4 use the next session close after a 10/20-session relative-high confirmation.",
        "- Confirmation is searched for at most 60 sessions after the event.",
        "- Target-before-invalidation and failed-breakout remain null because no stop/failure law was frozen before outcomes.",
        "- This replay does not infer cause or orchestration from returns.",
    ]
    (OUT / "EXK_TURN3_EXACT_REPLAY_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    series: dict[str, pd.Series] = {}
    metas: list[dict[str, Any]] = []
    for symbol in ("EXK", "SIL", "SLV"):
        close, meta = load_close(symbol)
        series[symbol] = close
        metas.append(meta)
    panel = pd.concat(series.values(), axis=1, join="inner").dropna().sort_index()
    panel["ratio_exk_sil"] = panel["EXK"] / panel["SIL"]
    panel["ratio_exk_slv"] = panel["EXK"] / panel["SLV"]

    rows = build_event_rows(panel)
    aggregates = aggregate(rows)
    case = current_case(panel, rows)

    pd.DataFrame(rows).to_csv(OUT / "EXK_TURN3_EVENT_REPLAY.csv", index=False)
    panel.loc["2015-01-01":].reset_index(names="Date").to_csv(
        OUT / "EXK_SIL_SLV_DAILY_2015_2026.csv", index=False
    )
    (OUT / "EXK_TURN3_REPLAY_RESULTS.json").write_text(
        json.dumps(
            {
                "schema": "mastermind.exk_turn3_exact_replay.v0",
                "repo_commit": os.getenv("GITHUB_SHA", "local"),
                "authority": {
                    "can_rank": False,
                    "can_gate": False,
                    "can_size": False,
                    "can_originate_signal": False,
                    "can_escalate": False,
                },
                "design": {
                    "horizons": list(HORIZONS),
                    "confirmation_windows": CONFIRM_WINDOWS,
                    "confirmation_search_sessions": CONFIRM_SEARCH_SESSIONS,
                    "H0": "first public tradable close",
                    "H1": "H0 restricted to recoverable",
                    "H2": "next close after 10-session EXK/SIL relative high",
                    "H3": "next close after 20-session EXK/SIL relative high",
                    "H4": "recoverable plus H3",
                },
                "price_meta": metas,
                "excluded_clock_pending": EXCLUDED_CLOCK_PENDING,
                "events": EVENTS,
                "event_rows": rows,
                "aggregates": aggregates,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (OUT / "EXK_TURN3_OPPORTUNITY_CASE.json").write_text(
        json.dumps(case, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_report(panel, metas, rows, aggregates, case)

    print(json.dumps({
        "status": "ok",
        "outputs": sorted(p.name for p in OUT.iterdir()),
        "panel_rows": len(panel),
        "panel_first": panel.index.min().date().isoformat(),
        "panel_last": panel.index.max().date().isoformat(),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
