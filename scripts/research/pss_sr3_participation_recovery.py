#!/usr/bin/env python3
"""PSS-SR3 — synchronized participation recovery.

The construction and decision law were committed before outcomes in
``research/PSS_SR3_PARTICIPATION_RECOVERY_PREREG.md``.  The outcome-blind path
builder lives in ``pss_sr3_participation_feasibility`` and is reused verbatim.

Run:
    python -m scripts.research.pss_sr3_participation_recovery

Outputs:
    reports/pss_sr3_participation_recovery.md
    data/research/pss_sr3_participation_recovery_events.parquet
    data/research/pss_sr3_participation_recovery_panel.parquet
    data/research/pss_sr3_participation_recovery_census.parquet
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.research import pss_f4_semivar as f4
from scripts.research import pss_sr2_peer_diffusion as sr2
from scripts.research import pss_sr3_participation_feasibility as feasibility


ROOT = Path(__file__).resolve().parents[2]
PANEL_PQ = ROOT / "data/research/ptt_w1_panel.parquet"
OUT_EVENTS = ROOT / "data/research/pss_sr3_participation_recovery_events.parquet"
OUT_PANEL = ROOT / "data/research/pss_sr3_participation_recovery_panel.parquet"
OUT_CENSUS = ROOT / "data/research/pss_sr3_participation_recovery_census.parquet"
OUT_REPORT = ROOT / "reports/pss_sr3_participation_recovery.md"

LEVEL_COLUMN = "peer_recovery_min_level_0.50"
ACTIVE_COLUMN = "peer_recovery_min_joint_5"
LEVEL_FLOOR = 0.50
ACTIVE_FLOOR = 0.50
OUTCOME_HORIZON = 63
REBOUND_TARGET = 0.08

PERMUTATIONS = 2_000
PERM_SEED = 20260806
BOOTSTRAPS = 1_000
BOOT_SEED = 20260807
MOVING_BLOCK_MONTHS = 3

INFER_METRICS = ("mae", "tail10", "w5", "called", "rebound8_first")
PRIMARY_GROUPS = ("sr3", "level_control")
GROUPS = ("sr3", "level_control", "weak_level")

EVENT_COLUMNS = (
    "sym",
    "sector",
    "anchor_date",
    "formation_confirm",
    "date",
    "month",
    "era",
    "group",
    "is_sr3",
    "is_level_control",
    "is_weak_level",
    "atr_anchor",
    "reference_low",
    "anchor_breadth",
    "peer_peak",
    "level_min",
    "active_min",
    "delay",
    "close_depth_atr",
    "next_open_gap",
    "severity_band",
    "delay_band",
    "mae",
    "prox",
    "w5",
    "called",
    "tail10",
    "tdt",
    "rebound8_first",
    "breach_first",
    "unresolved",
    "resolution_day",
)


def classify_path(level_min: float, active_min: float) -> str:
    if level_min < LEVEL_FLOOR:
        return "weak_level"
    if active_min >= ACTIVE_FLOOR:
        return "sr3"
    return "level_control"


def event_row(
    row: pd.Series,
    ohlcv: pd.DataFrame,
    metrics: dict[str, np.ndarray],
) -> dict[str, object] | None:
    """Append outcomes only after the frozen action date is known."""

    date = pd.Timestamp(row["date"])
    if date not in ohlcv.index:
        return None
    location = ohlcv.index.get_loc(date)
    if not isinstance(location, (int, np.integer)):
        return None
    action = int(location)
    if action + OUTCOME_HORIZON >= len(ohlcv):
        return None
    if not np.isfinite(metrics["mae63"][action]) or not np.isfinite(
        metrics["prox"][action]
    ):
        return None

    close = ohlcv["close"].to_numpy(dtype=float)
    low = ohlcv["low"].to_numpy(dtype=float)
    open_ = ohlcv["open"].to_numpy(dtype=float)
    reference_low = float(row["reference_low"])
    atr_anchor = float(row["atr_anchor"])
    risk = sr2.competing_risk(
        close,
        low,
        action,
        reference_low - feasibility.SUBJECT_BREACH_ATR * atr_anchor,
        horizon=OUTCOME_HORIZON,
    )
    mae = float(metrics["mae63"][action])
    prox = float(metrics["prox"][action])
    tdt = float(metrics["tdt"][action])
    group = classify_path(float(row[LEVEL_COLUMN]), float(row[ACTIVE_COLUMN]))
    next_open_gap = (
        float((open_[action + 1] / close[action] - 1.0) * 100.0)
        if np.isfinite(open_[action + 1]) and np.isfinite(close[action])
        else np.nan
    )
    return {
        "sym": str(row["sym"]),
        "sector": str(row["sector"]),
        "anchor_date": pd.Timestamp(row["anchor_date"]),
        "formation_confirm": pd.Timestamp(row["formation_confirm"]),
        "date": date,
        "month": str(row["month"]),
        "era": str(row["era"]),
        "group": group,
        "is_sr3": group == "sr3",
        "is_level_control": group == "level_control",
        "is_weak_level": group == "weak_level",
        "atr_anchor": atr_anchor,
        "reference_low": reference_low,
        "anchor_breadth": float(row["anchor_breadth"]),
        "peer_peak": float(row["peer_peak"]),
        "level_min": float(row[LEVEL_COLUMN]),
        "active_min": float(row[ACTIVE_COLUMN]),
        "delay": int(row["delay"]),
        "close_depth_atr": float(row["close_depth_atr"]),
        "next_open_gap": next_open_gap,
        "severity_band": str(row["severity_band"]),
        "delay_band": str(row["delay_band"]),
        "mae": mae,
        "prox": prox,
        "w5": bool(prox <= 5.0),
        "called": bool(-2 <= tdt <= 5),
        "tail10": bool(mae <= -10.0),
        "tdt": tdt,
        **risk,
    }


def append_outcomes(
    paths: pd.DataFrame,
    census: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    complete_by_name: dict[str, int] = {}
    dropped_by_name: dict[str, int] = {}
    for number, (sym, group) in enumerate(
        paths.groupby("sym", sort=True),
        start=1,
    ):
        ohlcv = feasibility.load_ohlcv(str(sym))
        metrics = f4.metric_arrays(ohlcv["close"].to_numpy(dtype=float))
        completed = 0
        dropped = 0
        for _, path_row in group.iterrows():
            outcome = event_row(path_row, ohlcv, metrics)
            if outcome is None:
                dropped += 1
                continue
            rows.append(outcome)
            completed += 1
        complete_by_name[str(sym)] = completed
        dropped_by_name[str(sym)] = dropped
        if number % 100 == 0:
            print(
                f"outcomes {number}/{paths['sym'].nunique()} names; "
                f"events={len(rows):,}",
                flush=True,
            )
    events = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    if len(events):
        events = events.sort_values(
            ["date", "sector", "sym", "anchor_date"]
        ).reset_index(drop=True)
    census = census.copy()
    census["outcome_complete"] = (
        census["sym"].astype(str).map(complete_by_name).fillna(0).astype(int)
    )
    census["outcome_dropped"] = (
        census["sym"].astype(str).map(dropped_by_name).fillna(0).astype(int)
    )
    return events, census


def add_unmapped_census(census: pd.DataFrame, mapped: set[str]) -> pd.DataFrame:
    panel = pd.read_parquet(PANEL_PQ, columns=["sym", "eligible"])
    eligible = set(
        panel.loc[panel["eligible"].astype(bool), "sym"].dropna().astype(str)
    )
    unmapped = sorted(eligible - mapped)
    if not unmapped:
        return census
    extra = pd.DataFrame(
        {"sym": unmapped, "sector": "", "status": "missing_sector_map"}
    )
    out = pd.concat([census, extra], ignore_index=True).fillna(0)
    return out.sort_values(["sector", "sym"]).reset_index(drop=True)


def inference_tape(events: pd.DataFrame) -> pd.DataFrame:
    """Frozen keep-first name-month tape with informative exact strata."""

    if not len(events):
        empty = events.copy()
        empty["stratum"] = pd.Series(index=empty.index, dtype="string")
        return empty
    data = (
        events[events["group"].isin(PRIMARY_GROUPS)]
        .sort_values(["date", "anchor_date", "sym"])
        .drop_duplicates(["sym", "month"], keep="first")
        .copy()
    )
    keys = ["sector", "month", "severity_band", "delay_band"]
    counts = data.groupby(keys, observed=True)["is_sr3"].agg(["size", "sum"])
    good = counts[(counts["sum"] >= 2) & ((counts["size"] - counts["sum"]) >= 2)]
    if not len(good):
        empty = data.iloc[0:0].copy()
        empty["stratum"] = pd.Series(index=empty.index, dtype="string")
        return empty
    good_index = set(good.index.tolist())
    mask = [
        (row.sector, row.month, row.severity_band, row.delay_band)
        in good_index
        for row in data.itertuples()
    ]
    data = data.loc[mask].copy()
    data["stratum"] = (
        data["sector"].astype(str)
        + "|"
        + data["month"].astype(str)
        + "|"
        + data["severity_band"].astype(str)
        + "|"
        + data["delay_band"].astype(str)
    )
    return data


def metric_values(data: pd.DataFrame, metric: str) -> np.ndarray:
    values = data[metric].to_numpy(dtype=float)
    if metric in ("tail10", "breach_first"):
        return -100.0 * values
    if metric in ("w5", "called", "rebound8_first"):
        return 100.0 * values
    return values


def stratum_effects(events: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Equal-weight effects; positive always means SR3 is better."""

    data = inference_tape(events)
    binary = metric in (
        "tail10",
        "breach_first",
        "w5",
        "called",
        "rebound8_first",
    )
    rows: list[dict[str, object]] = []
    for stratum, group in data.groupby("stratum", sort=True):
        treatment = group["is_sr3"].to_numpy(dtype=bool)
        if treatment.sum() < 2 or (~treatment).sum() < 2:
            continue
        values = metric_values(group, metric)
        reducer = np.mean if binary else np.median
        rows.append(
            {
                "stratum": stratum,
                "month": str(group["month"].iloc[0]),
                "sector": str(group["sector"].iloc[0]),
                "effect": float(
                    reducer(values[treatment]) - reducer(values[~treatment])
                ),
                "n_treatment": int(treatment.sum()),
                "n_control": int((~treatment).sum()),
            }
        )
    return pd.DataFrame(rows)


def permuted_effects(
    events: pd.DataFrame,
    metric: str,
    n_perm: int,
    seed: int,
) -> tuple[float, np.ndarray, list[tuple[int, int]]]:
    data = inference_tape(events)
    binary = metric in (
        "tail10",
        "breach_first",
        "w5",
        "called",
        "rebound8_first",
    )
    prepared: list[tuple[np.ndarray, int]] = []
    observed_parts: list[float] = []
    counts: list[tuple[int, int]] = []
    for _, group in data.groupby("stratum", sort=True):
        treatment = group["is_sr3"].to_numpy(dtype=bool)
        nt = int(treatment.sum())
        nc = int((~treatment).sum())
        if nt < 2 or nc < 2:
            continue
        values = metric_values(group, metric)
        reducer = np.mean if binary else np.median
        observed_parts.append(
            float(reducer(values[treatment]) - reducer(values[~treatment]))
        )
        prepared.append((values, nt))
        counts.append((nt, nc))
    if not prepared:
        return np.nan, np.full(n_perm, np.nan), counts
    observed = float(np.mean(observed_parts))
    rng = np.random.default_rng(seed)
    null = np.empty(n_perm)
    reducer = np.mean if binary else np.median
    for draw in range(n_perm):
        parts = []
        for values, nt in prepared:
            order = rng.permutation(len(values))
            parts.append(
                float(
                    reducer(values[order[:nt]])
                    - reducer(values[order[nt:]])
                )
            )
        null[draw] = float(np.mean(parts))
    return observed, null, counts


def moving_block_ci(
    effects: pd.DataFrame,
    n_boot: int,
    seed: int,
    block_months: int = MOVING_BLOCK_MONTHS,
) -> tuple[float, float]:
    if not len(effects):
        return np.nan, np.nan
    observed_months = pd.PeriodIndex(effects["month"], freq="M")
    months = pd.period_range(
        observed_months.min(),
        observed_months.max(),
        freq="M",
    )
    pieces = {
        month: effects.loc[
            observed_months == month, "effect"
        ].to_numpy(dtype=float)
        for month in months
    }
    rng = np.random.default_rng(seed)
    boot = np.empty(n_boot)
    n_months = len(months)
    for draw in range(n_boot):
        sampled: list[pd.Period] = []
        while len(sampled) < n_months:
            start = int(rng.integers(0, n_months))
            sampled.extend(
                months[(start + offset) % n_months]
                for offset in range(block_months)
            )
        arrays = [pieces[month] for month in sampled[:n_months] if len(pieces[month])]
        boot[draw] = (
            float(np.mean(np.concatenate(arrays))) if arrays else np.nan
        )
    finite = boot[np.isfinite(boot)]
    if not len(finite):
        return np.nan, np.nan
    return float(np.percentile(finite, 2.5)), float(np.percentile(finite, 97.5))


def inference(
    events: pd.DataFrame,
    metric: str,
    n_perm: int,
    n_boot: int,
) -> dict[str, float]:
    effects = stratum_effects(events, metric)
    observed, null, _ = permuted_effects(
        events,
        metric,
        n_perm,
        PERM_SEED,
    )
    if not np.isfinite(observed):
        return {
            "effect": np.nan,
            "p": np.nan,
            "ci_low": np.nan,
            "ci_high": np.nan,
            "strata": 0,
            "events": 0,
        }
    p = float((1 + np.sum(null >= observed)) / (n_perm + 1))
    ci_low, ci_high = moving_block_ci(
        effects,
        n_boot,
        BOOT_SEED,
    )
    return {
        "effect": observed,
        "p": p,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "strata": len(effects),
        "events": int((effects["n_treatment"] + effects["n_control"]).sum()),
    }


def group_subset(events: pd.DataFrame, group: str) -> pd.DataFrame:
    return events[events["group"].eq(group)]


def absolute_summary(events: pd.DataFrame, group: str) -> dict[str, float]:
    data = group_subset(events, group)
    if not len(data):
        return {
            "events": 0,
            "names": 0,
            "names3": 0,
            **{
                key: np.nan
                for key in (
                    "mae",
                    "prox",
                    "w5",
                    "called",
                    "tail10",
                    "tdt",
                    "rebound8_first",
                    "breach_first",
                    "unresolved",
                    "delay",
                    "close_depth",
                    "anchor_breadth",
                    "peer_peak",
                    "level_min",
                    "active_min",
                    "next_open_gap",
                )
            },
        }
    per_name = (
        data.groupby("sym", observed=True)
        .agg(
            n=("date", "size"),
            mae=("mae", "median"),
            prox=("prox", "median"),
            w5=("w5", "mean"),
            called=("called", "mean"),
            tail10=("tail10", "mean"),
            tdt=("tdt", "median"),
            rebound8_first=("rebound8_first", "mean"),
            breach_first=("breach_first", "mean"),
            unresolved=("unresolved", "mean"),
            delay=("delay", "median"),
            close_depth=("close_depth_atr", "median"),
            anchor_breadth=("anchor_breadth", "median"),
            peer_peak=("peer_peak", "median"),
            level_min=("level_min", "median"),
            active_min=("active_min", "median"),
            next_open_gap=("next_open_gap", "median"),
        )
        .reset_index()
    )
    return {
        "events": len(data),
        "names": len(per_name),
        "names3": int((per_name["n"] >= 3).sum()),
        "mae": float(per_name["mae"].median()),
        "prox": float(per_name["prox"].median()),
        "w5": float(per_name["w5"].mean() * 100.0),
        "called": float(per_name["called"].mean() * 100.0),
        "tail10": float(per_name["tail10"].mean() * 100.0),
        "tdt": float(per_name["tdt"].median()),
        "rebound8_first": float(per_name["rebound8_first"].mean() * 100.0),
        "breach_first": float(per_name["breach_first"].mean() * 100.0),
        "unresolved": float(per_name["unresolved"].mean() * 100.0),
        "delay": float(per_name["delay"].median()),
        "close_depth": float(per_name["close_depth"].median()),
        "anchor_breadth": float(per_name["anchor_breadth"].median()),
        "peer_peak": float(per_name["peer_peak"].median()),
        "level_min": float(per_name["level_min"].median()),
        "active_min": float(per_name["active_min"].median()),
        "next_open_gap": float(per_name["next_open_gap"].median()),
    }


def per_name_summary(
    events: pd.DataFrame,
    group: str,
    era: str,
) -> pd.DataFrame:
    data = group_subset(events[events["era"].eq(era)], group)
    if not len(data):
        return pd.DataFrame()
    out = (
        data.groupby("sym", observed=True)
        .agg(
            n=("date", "size"),
            mae=("mae", "median"),
            prox=("prox", "median"),
            w5=("w5", "mean"),
            called=("called", "mean"),
            tail10=("tail10", "mean"),
            tdt=("tdt", "median"),
            rebound8_first=("rebound8_first", "mean"),
            breach_first=("breach_first", "mean"),
            unresolved=("unresolved", "mean"),
            delay=("delay", "median"),
            close_depth_atr=("close_depth_atr", "median"),
            level_min=("level_min", "median"),
            active_min=("active_min", "median"),
        )
        .reset_index()
    )
    out["era"] = era
    out["group"] = group
    return out


def build_panel(events: pd.DataFrame) -> pd.DataFrame:
    pieces = [
        per_name_summary(events, group, era)
        for era in ("DEV", "VAL", "FWD")
        for group in GROUPS
    ]
    pieces = [piece for piece in pieces if len(piece)]
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def containment(events: pd.DataFrame) -> dict[str, float]:
    primary = events[events["group"].isin(PRIMARY_GROUPS)]
    h1 = primary[primary["date"].between("2022-01-01", "2022-06-30")]
    autumn = primary[
        primary["date"].between("2022-09-01", "2022-11-30")
    ]
    return {
        "h1_opportunity_density": len(h1) / 6.0,
        "autumn_opportunity_density": len(autumn) / 3.0,
        "h1_treatment_density": float(h1["is_sr3"].sum()) / 6.0,
        "autumn_treatment_density": float(autumn["is_sr3"].sum()) / 3.0,
        "h1_share": float(h1["is_sr3"].mean()) if len(h1) else np.nan,
        "autumn_share": (
            float(autumn["is_sr3"].mean()) if len(autumn) else np.nan
        ),
    }


def leave_one_sector_effects(
    events: pd.DataFrame,
    metric: str,
) -> dict[str, float]:
    out: dict[str, float] = {}
    for sector in feasibility.SECTORS:
        effects = stratum_effects(events[events["sector"].ne(sector)], metric)
        out[sector] = (
            float(effects["effect"].mean()) if len(effects) else np.nan
        )
    return out


def fmt(value: float, digits: int = 2) -> str:
    if not np.isfinite(value):
        return "—"
    return f"{value:+.{digits}f}"


def qualification(
    events: pd.DataFrame,
    results: dict[tuple[str, str], dict[str, float]],
) -> tuple[bool, list[tuple[str, bool, str]]]:
    checks: list[tuple[str, bool, str]] = []
    for era in ("DEV", "VAL"):
        for metric in ("mae", "tail10"):
            result = results[(era, metric)]
            passed = bool(
                np.isfinite(result["ci_low"])
                and result["effect"] > 0
                and result["ci_low"] > 0
                and result["p"] <= 0.05
            )
            detail = (
                f"effect={fmt(result['effect'])}, "
                f"CI=[{fmt(result['ci_low'])},{fmt(result['ci_high'])}], "
                f"p={result['p']:.4f}"
                if np.isfinite(result["p"])
                else "not estimable"
            )
            checks.append((f"{era} {metric} clears", passed, detail))
        timing = any(
            results[(era, metric)]["effect"] > 0
            for metric in ("w5", "called")
        )
        rebound = results[(era, "rebound8_first")]["effect"] > 0
        checks.append(
            (
                f"{era} timing and rebound-first improve",
                bool(timing and rebound),
                f"W5={fmt(results[(era, 'w5')]['effect'])}, "
                f"called={fmt(results[(era, 'called')]['effect'])}, "
                f"rebound8={fmt(results[(era, 'rebound8_first')]['effect'])}",
            )
        )

    treatment = events[events["is_sr3"]]
    n_names = int(treatment["sym"].nunique())
    n_names3 = int((treatment.groupby("sym").size() >= 3).sum())
    strata = {
        era: results[(era, "mae")]["strata"] for era in ("DEV", "VAL")
    }
    coverage = (
        n_names >= 500
        and n_names3 >= 100
        and all(value >= 40 for value in strata.values())
    )
    checks.append(
        (
            "Coverage and informative-strata floor",
            bool(coverage),
            f"names={n_names}, names≥3={n_names3}, strata={strata}",
        )
    )

    contained = containment(events)
    share_gap = contained["autumn_share"] - contained["h1_share"]
    checks.append(
        (
            "H1 active share at least 15pp below Sep-Nov",
            bool(np.isfinite(share_gap) and share_gap >= 0.15),
            f"H1={contained['h1_share']*100:.1f}%, "
            f"Sep-Nov={contained['autumn_share']*100:.1f}%, "
            f"gap={share_gap*100:.1f}pp",
        )
    )

    for era in ("DEV", "VAL"):
        effects = stratum_effects(
            events[events["era"].eq(era)],
            "close_depth_atr",
        )
        difference = (
            float(effects["effect"].mean()) if len(effects) else np.nan
        )
        checks.append(
            (
                f"{era} no safe-late distance confound",
                bool(np.isfinite(difference) and difference <= 0.25),
                f"stratified treatment-control={fmt(difference)} ATR",
            )
        )

    concentration = (
        treatment.groupby("sector").size().max() / len(treatment)
        if len(treatment)
        else np.nan
    )
    leave_one_ok = True
    leave_one_detail: list[str] = []
    for era in ("DEV", "VAL"):
        era_events = events[events["era"].eq(era)]
        for metric in ("mae", "tail10"):
            effects = leave_one_sector_effects(era_events, metric)
            minimum = min(effects.values()) if effects else np.nan
            leave_one_ok = leave_one_ok and bool(
                np.isfinite(minimum) and minimum > 0
            )
            leave_one_detail.append(f"{era}-{metric} min={fmt(minimum)}")
    checks.append(
        (
            "Sector robustness and ≤25% concentration",
            bool(
                leave_one_ok
                and np.isfinite(concentration)
                and concentration <= 0.25
            ),
            ", ".join(leave_one_detail)
            + f", max share={concentration*100:.1f}%",
        )
    )

    fwd = all(
        results[("FWD", metric)]["effect"] >= 0
        for metric in ("mae", "tail10")
    )
    checks.append(
        (
            "No FWD primary reversal",
            bool(fwd),
            f"MAE={fmt(results[('FWD', 'mae')]['effect'])}, "
            f"tail={fmt(results[('FWD', 'tail10')]['effect'])}",
        )
    )
    return all(passed for _, passed, _ in checks), checks


def report_group_table(events: pd.DataFrame) -> list[str]:
    lines = [
        "| group | paths | names | names >=3 | MAE63 | prox | W5 | called | "
        "tail<=-10 | tdt | rebound8 first | breach first | unresolved |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group in GROUPS:
        summary = absolute_summary(events, group)
        lines.append(
            f"| {group} | {int(summary['events'])} | "
            f"{int(summary['names'])} | {int(summary['names3'])} | "
            f"{fmt(summary['mae'])}% | {fmt(summary['prox'])}% | "
            f"{fmt(summary['w5'], 1)}% | "
            f"{fmt(summary['called'], 1)}% | "
            f"{fmt(summary['tail10'], 1)}% | "
            f"{fmt(summary['tdt'], 1)}td | "
            f"{fmt(summary['rebound8_first'], 1)}% | "
            f"{fmt(summary['breach_first'], 1)}% | "
            f"{fmt(summary['unresolved'], 1)}% |"
        )
    return lines


def report_confound_table(events: pd.DataFrame) -> list[str]:
    lines = [
        "| group | delay | close/ref | anchor breadth | formation peer peak | "
        "passive breadth | active breadth | next-open gap |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group in GROUPS:
        summary = absolute_summary(events, group)
        lines.append(
            f"| {group} | {fmt(summary['delay'], 1)}td | "
            f"{fmt(summary['close_depth'])} ATR | "
            f"{fmt(summary['anchor_breadth'], 3)} | "
            f"{fmt(summary['peer_peak'], 3)} | "
            f"{fmt(summary['level_min'], 3)} | "
            f"{fmt(summary['active_min'], 3)} | "
            f"{fmt(summary['next_open_gap'], 3)}% |"
        )
    return lines


def primary_tape_audit(events: pd.DataFrame, era: str) -> dict[str, int]:
    primary = (
        events[
            events["era"].eq(era) & events["group"].isin(PRIMARY_GROUPS)
        ]
        .sort_values(["date", "anchor_date", "sym"])
        .copy()
    )
    deduplicated = primary.drop_duplicates(["sym", "month"], keep="first")
    retained = inference_tape(primary)
    return {
        "raw": len(primary),
        "repeat_dropped": len(primary) - len(deduplicated),
        "deduplicated": len(deduplicated),
        "noninformative_dropped": len(deduplicated) - len(retained),
        "retained": len(retained),
        "strata": int(retained["stratum"].nunique()) if len(retained) else 0,
    }


def marginal_count_table(
    events: pd.DataFrame,
    index_column: str,
) -> list[str]:
    primary = events[events["group"].isin(PRIMARY_GROUPS)]
    counts = (
        primary.groupby([index_column, "group"], observed=True)
        .size()
        .unstack(fill_value=0)
        .reindex(columns=PRIMARY_GROUPS, fill_value=0)
        .sort_index()
    )
    lines = [
        f"| {index_column} | SR3 | level control | total |",
        "|---|---:|---:|---:|",
    ]
    for label, row in counts.iterrows():
        treatment = int(row["sr3"])
        control = int(row["level_control"])
        lines.append(
            f"| {label} | {treatment} | {control} | "
            f"{treatment + control} |"
        )
    return lines


def diagnostic_partition_table(events: pd.DataFrame) -> list[str]:
    """Post-verdict mechanism partitions; descriptive and never rescuing."""

    lines = [
        "| era | partition | cell | strata | MAE | tail | W5 | "
        "rebound8 first |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    dimensions = (
        ("delay", "delay_band", ("d1", "d2", "d3")),
        ("anchor severity", "severity_band", ("p1", "p2", "p3")),
    )
    for era in ("DEV", "VAL", "FWD"):
        era_events = events[events["era"].eq(era)]
        for label, column, cells in dimensions:
            for cell in cells:
                subset = era_events[era_events[column].eq(cell)]
                effects = {
                    metric: stratum_effects(subset, metric)
                    for metric in (
                        "mae",
                        "tail10",
                        "w5",
                        "rebound8_first",
                    )
                }
                n_strata = len(effects["mae"])
                values = {
                    metric: (
                        float(frame["effect"].mean()) if len(frame) else np.nan
                    )
                    for metric, frame in effects.items()
                }
                lines.append(
                    f"| {era} | {label} | {cell} | {n_strata} | "
                    f"{fmt(values['mae'])} | {fmt(values['tail10'])} | "
                    f"{fmt(values['w5'])} | "
                    f"{fmt(values['rebound8_first'])} |"
                )
    return lines


def render_report(
    events: pd.DataFrame,
    census: pd.DataFrame,
    n_perm: int,
    n_boot: int,
) -> tuple[str, bool]:
    results: dict[tuple[str, str], dict[str, float]] = {}
    for era in ("DEV", "VAL", "FWD"):
        era_events = events[events["era"].eq(era)]
        for metric in INFER_METRICS:
            results[(era, metric)] = inference(
                era_events,
                metric,
                n_perm,
                n_boot,
            )
    qualified, checks = qualification(events, results)

    lines = [
        "# PSS-SR3 — synchronized participation recovery",
        "",
        "The construction and decision law were committed before forward "
        "outcomes in `research/PSS_SR3_PARTICIPATION_RECOVERY_PREREG.md`. "
        "Positive effects always mean SR3 is better than the nested "
        "level-recovered control.",
        "",
        "SR3 is research/display-only. Historical qualification could authorize "
        "only a prospective frozen shadow, never entry, rank, size, gate, or "
        "alert authority.",
        "",
        "## Construction audit",
        "",
        "- Anchor: subject fresh prior-60 close low during a shifted-q80 "
        "ex-self sector new-low breadth extreme.",
        "- Subject action: first three-session recovery hold; each close >= "
        "+0.50 frozen ATR, each low >= -0.50 ATR, final close in "
        "[+1.00,+1.75] ATR.",
        "- Passive peer qualification: on all three action-window closes, at "
        "least half of peers are >=+0.50 own frozen ATR above their own "
        "formation lows.",
        "- Treatment: on all three closes, at least half of those same peers "
        "also close above their own five-session-prior close.",
        "- Primary control: identical subject path and passive majority peer "
        "recovery, but active breadth remains below half.",
        "- Inference: keep-first name-month; exact sector x month x anchor "
        "severity x delay strata; within-stratum permutation primary.",
        "",
    ]
    for era in ("DEV", "VAL", "FWD"):
        era_events = events[events["era"].eq(era)]
        lines.extend([f"## {era}", "", *report_group_table(era_events), ""])
        lines.extend(
            [
                "### Frozen-geometry and execution audit",
                "",
                *report_confound_table(era_events),
                "",
            ]
        )
        lines.extend(
            [
                "### SR3 minus level-recovered control",
                "",
                "| metric | effect | 95% 3-month-block CI | permutation p | "
                "informative strata | retained events |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for metric in INFER_METRICS:
            result = results[(era, metric)]
            lines.append(
                f"| {metric} | {fmt(result['effect'])} | "
                f"[{fmt(result['ci_low'])}, {fmt(result['ci_high'])}] | "
                f"{result['p']:.4f} | {int(result['strata'])} | "
                f"{int(result['events'])} |"
                if np.isfinite(result["p"])
                else f"| {metric} | — | — | — | 0 | 0 |"
            )
        lines.append("")
        tape = primary_tape_audit(events, era)
        lines.extend(
            [
                "Inference-tape accounting: "
                f"{tape['raw']:,} raw primary paths; "
                f"{tape['repeat_dropped']:,} repeated name-month paths "
                "dropped; "
                f"{tape['deduplicated']:,} de-duplicated; "
                f"{tape['noninformative_dropped']:,} outside informative "
                "strata; "
                f"{tape['retained']:,} retained across "
                f"{tape['strata']:,} strata.",
                "",
            ]
        )

    lines.extend(
        [
            "## Frozen decision law",
            "",
            "| check | pass | evidence |",
            "|---|:---:|---|",
        ]
    )
    for label, passed, detail in checks:
        lines.append(f"| {label} | {'YES' if passed else 'NO'} | {detail} |")
    lines.extend(
        [
            "",
            f"**Verdict: {'QUALIFIES FOR PROSPECTIVE SHADOW ONLY' if qualified else 'KILLED'}**.",
            "",
            "## Containment and topology",
            "",
        ]
    )
    contained = containment(events)
    lines.extend(
        [
            "- H1-2022 primary opportunity / treatment density: "
            f"{contained['h1_opportunity_density']:.1f} / "
            f"{contained['h1_treatment_density']:.1f} per month.",
            "- Sep-Nov 2022 primary opportunity / treatment density: "
            f"{contained['autumn_opportunity_density']:.1f} / "
            f"{contained['autumn_treatment_density']:.1f} per month.",
            "- Conditional treatment share: "
            f"H1 {contained['h1_share']*100:.1f}% vs "
            f"Sep-Nov {contained['autumn_share']*100:.1f}%.",
            "",
            "Treatment paths by sector:",
            "",
        ]
    )
    sector_counts = (
        events[events["is_sr3"]]
        .groupby("sector", observed=True)
        .size()
        .sort_values(ascending=False)
    )
    lines.extend(f"- {sector}: {int(count)}" for sector, count in sector_counts.items())
    lines.extend(
        [
            "",
            "### Primary path counts by era",
            "",
            *marginal_count_table(events, "era"),
            "",
            "### Primary path counts by sector",
            "",
            *marginal_count_table(events, "sector"),
            "",
            "### Primary path counts by action month",
            "",
            *marginal_count_table(events, "month"),
            "",
            "### Primary path counts by name",
            "",
            *marginal_count_table(events, "sym"),
            "",
            "### Leave-one-sector-out primary effects",
            "",
            "| era | omitted sector | MAE effect | tail effect |",
            "|---|---|---:|---:|",
        ]
    )
    for era in ("DEV", "VAL"):
        era_events = events[events["era"].eq(era)]
        mae_effects = leave_one_sector_effects(era_events, "mae")
        tail_effects = leave_one_sector_effects(era_events, "tail10")
        for sector in feasibility.SECTORS:
            lines.append(
                f"| {era} | {sector} | {fmt(mae_effects[sector])} | "
                f"{fmt(tail_effects[sector])} |"
            )

    status_counts = census["status"].value_counts().sort_index()
    lines.extend(["", "## Exclusion and path census", ""])
    lines.extend(f"- `{status}`: {int(count)} names" for status, count in status_counts.items())
    lines.extend(
        [
            "",
            "Aggregate primary groups:",
            "",
            f"- treatment: {int(events['is_sr3'].sum()):,}",
            f"- level-recovered control: {int(events['is_level_control'].sum()):,}",
            f"- weak-level diagnostic: {int(events['is_weak_level'].sum()):,}",
            f"- complete outcome paths: {int(census['outcome_complete'].sum()):,}",
            f"- incomplete outcome paths dropped: "
            f"{int(census['outcome_dropped'].sum()):,}",
            "",
            "## Post-kill diagnostic partition",
            "",
            "These slices were read only after the frozen verdict. They diagnose "
            "the failure mechanism and cannot rescue, reverse, or retune SR3. "
            "Each value remains an equal-weight effect across the same exact "
            "primary strata; sparse one-stratum cells are printed, not promoted.",
            "",
            *diagnostic_partition_table(events),
            "",
            "## Interpretation",
            "",
        ]
    )
    if qualified:
        lines.append(
            "Every frozen historical requirement passed. This authorizes only "
            "a separately reviewed, deterministic prospective display shadow; "
            "it does not authorize an entry, rank, size, gate, or alert."
        )
    else:
        lines.append(
            "At least one frozen requirement failed. This exact SR3 construction "
            "is not usable and cannot be rescued by threshold retiming, removing "
            "the nested control, or replacing active participation with another "
            "absence-of-weakness label after outcomes."
        )
    lines.extend(
        [
            "",
            f"Inference: {n_perm:,} within-stratum permutations "
            f"(base seed {PERM_SEED}); {n_boot:,} circular three-month "
            f"moving-block bootstraps (base seed {BOOT_SEED}).",
            "",
        ]
    )
    return "\n".join(lines), qualified


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--permutations", type=int, default=PERMUTATIONS)
    parser.add_argument("--bootstraps", type=int, default=BOOTSTRAPS)
    parser.add_argument(
        "--reuse-events",
        action="store_true",
        help="Reuse existing events/census and regenerate panel/report.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.reuse_events and OUT_EVENTS.exists() and OUT_CENSUS.exists():
        events = pd.read_parquet(OUT_EVENTS)
        census = pd.read_parquet(OUT_CENSUS)
    else:
        ticker_sector = feasibility.load_universe()
        paths, census = feasibility.build_paths(ticker_sector)
        events, census = append_outcomes(paths, census)
        census = add_unmapped_census(census, set(ticker_sector))
        OUT_EVENTS.parent.mkdir(parents=True, exist_ok=True)
        events.to_parquet(OUT_EVENTS, index=False)
        census.to_parquet(OUT_CENSUS, index=False)

    panel = build_panel(events)
    panel.to_parquet(OUT_PANEL, index=False)
    report, qualified = render_report(
        events,
        census,
        max(1, args.permutations),
        max(1, args.bootstraps),
    )
    OUT_REPORT.write_text(report, encoding="utf-8")
    print(f"wrote {OUT_EVENTS.relative_to(ROOT)} ({len(events):,} rows)")
    print(f"wrote {OUT_PANEL.relative_to(ROOT)} ({len(panel):,} rows)")
    print(f"wrote {OUT_CENSUS.relative_to(ROOT)} ({len(census):,} rows)")
    print(f"wrote {OUT_REPORT.relative_to(ROOT)}")
    print(
        "verdict: "
        + (
            "QUALIFIES FOR PROSPECTIVE SHADOW ONLY"
            if qualified
            else "KILLED"
        )
    )


if __name__ == "__main__":
    main()
