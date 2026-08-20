#!/usr/bin/env python3
"""Turn-4 corrected EXK event-dislocation replay.

Research/display only. Primary benchmark SIL is required. Secondary benchmark SLV is
optional and remains a typed null when its canonical repository file is absent.
No ranking, gating, sizing, signal origination, external price fallback, or parameter search.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONS = (5, 10, 20, 40, 60)
ARMS = ("H0", "H1", "H2", "H3", "H4", "H1B", "H4B")
AUTH = {
    "can_rank": False,
    "can_gate": False,
    "can_size": False,
    "can_originate_signal": False,
    "can_escalate": False,
}
ADVERSE = {
    "adverse_plan",
    "adverse_operational",
    "adverse_plus_remediation",
    "adverse_plus_plan",
    "adverse_structural",
    "adverse_macro",
    "adverse_nondiscretionary",
    "adverse_project",
    "resolved_before_disclosure",
}
RECOVERABLE = {"recoverable", "resolved", "bounded", "price_contingent"}
OPEN_INFO = {"open", "partially_bounded", "open_unresolved", "open_ended"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _col(cols, names):
    norm = {str(c).lower().replace(" ", "_"): c for c in cols}
    for name in names:
        if name in norm:
            return norm[name]
    return None


def load_close(path: Path) -> pd.Series:
    if not path.exists():
        raise FileNotFoundError(path)
    d = pd.read_parquet(path)
    dc = _col(d.columns, ("date", "datetime", "timestamp", "time"))
    idx_raw = d.pop(dc) if dc is not None else d.index
    idx = pd.to_datetime(idx_raw, errors="coerce", utc=True).tz_convert(None).normalize()
    d.index = idx
    d = d.loc[~d.index.isna()]
    d = d[~d.index.duplicated(keep="last")].sort_index()
    cc = _col(d.columns, ("adj_close", "adjusted_close", "close_adjusted", "close"))
    if cc is None:
        raise ValueError(f"no close column in {path}: {list(d.columns)}")
    s = pd.to_numeric(d[cc], errors="coerce")
    return s.loc[np.isfinite(s) & (s > 0)]


def load_events(path: Path) -> list[dict]:
    p = json.loads(path.read_text(encoding="utf-8"))
    events = p.get("events") or p.get("event_ledger")
    if not isinstance(events, list):
        raise ValueError("events[] missing")
    return events


def align(root: Path) -> tuple[pd.DataFrame, dict]:
    paths = {symbol: root / f"data/yahoo/{symbol}.parquet" for symbol in ("EXK", "SIL", "SLV")}
    required = {symbol: load_close(paths[symbol]) for symbol in ("EXK", "SIL")}
    frame = pd.concat(required, axis=1, join="inner").dropna()
    if frame.empty:
        raise ValueError("no common EXK/SIL sessions")
    secondary = {"symbol": "SLV", "state": "UNAVAILABLE", "reason": "canonical_file_absent"}
    if paths["SLV"].exists():
        slv = load_close(paths["SLV"])
        frame = frame.join(slv.rename("SLV"), how="left")
        secondary = {
            "symbol": "SLV",
            "state": "MEASURED",
            "sha256": sha256_file(paths["SLV"]),
            "first_session": slv.index.min().date().isoformat(),
            "last_session": slv.index.max().date().isoformat(),
            "n_sessions": int(len(slv)),
        }
    else:
        frame["SLV"] = np.nan
    frame["EXK_SIL"] = frame.EXK / frame.SIL
    return frame, {
        "EXK": {"path": str(paths["EXK"]), "sha256": sha256_file(paths["EXK"])},
        "SIL": {"path": str(paths["SIL"]), "sha256": sha256_file(paths["SIL"])},
        "SLV": secondary,
    }


def adverse(event: dict) -> bool:
    return event.get("event_class") in ADVERSE and event.get("study_inclusion") != "exclude"


def recoverable(event: dict) -> bool:
    return event.get("recoverability_at_t0") in RECOVERABLE


def open_information(event: dict) -> bool:
    return bool(event.get("new_adverse_information_at_t0")) and event.get("adverse_uncertainty_at_t0") in OPEN_INFO


def session(index: pd.DatetimeIndex, date: str) -> int | None:
    pos = int(index.searchsorted(pd.Timestamp(date).normalize(), "left"))
    return pos if pos < len(index) else None


def breakout(frame: pd.DataFrame, start: int, lookback: int, max_wait: int):
    ratio = frame.EXK_SIL
    stop = min(len(frame), start + max_wait + 1)
    for pos in range(max(start, lookback), stop):
        prior = ratio.iloc[pos - lookback : pos]
        if len(prior) == lookback and np.isfinite(prior).all() and ratio.iloc[pos] > prior.max():
            return pos, {
                "signal_date": frame.index[pos].date().isoformat(),
                "signal_ratio": float(ratio.iloc[pos]),
                "prior_range_high": float(prior.max()),
                "prior_range_low": float(prior.min()),
            }
    return None, {"refusal": f"no_{lookback}d_breakout_within_{max_wait}_sessions"}


def entry_for(event: dict, arm: str, frame: pd.DataFrame, event_pos: int, max_wait: int):
    if arm == "H0":
        return event_pos, {"signal_date": frame.index[event_pos].date().isoformat()}
    if arm in ("H1", "H1B"):
        if not recoverable(event):
            return None, {"refusal": "not_recoverable_at_t0"}
        if arm == "H1B" and not open_information(event):
            return None, {"refusal": "no_open_adverse_information_at_t0"}
        return event_pos, {"signal_date": frame.index[event_pos].date().isoformat()}
    if arm in ("H4", "H4B") and not recoverable(event):
        return None, {"refusal": "not_recoverable_at_t0"}
    if arm == "H4B" and not open_information(event):
        return None, {"refusal": "no_open_adverse_information_at_t0"}
    lookback = 10 if arm == "H2" else 20
    signal_pos, meta = breakout(frame, event_pos, lookback, max_wait)
    if signal_pos is None:
        return None, meta
    entry_pos = signal_pos + 1
    if entry_pos >= len(frame):
        return None, {**meta, "refusal": "next_close_unavailable"}
    return entry_pos, meta


def metrics(frame: pd.DataFrame, entry_pos: int, meta: dict) -> dict:
    entry_exk = float(frame.EXK.iloc[entry_pos])
    entry_sil = float(frame.SIL.iloc[entry_pos])
    entry_ratio = float(frame.EXK_SIL.iloc[entry_pos])
    entry_slv = frame.SLV.iloc[entry_pos]
    out = {
        "entry_date": frame.index[entry_pos].date().isoformat(),
        "entry_exk": entry_exk,
        "entry_sil": entry_sil,
        "entry_slv": float(entry_slv) if np.isfinite(entry_slv) else None,
        "entry_exk_sil": entry_ratio,
    }
    for horizon in HORIZONS:
        end = entry_pos + horizon
        key = f"h{horizon}"
        if end >= len(frame):
            out[f"{key}_mature"] = False
            continue
        window = frame.iloc[entry_pos : end + 1]
        path = window.EXK / entry_exk - 1
        relative_path = window.EXK_SIL / entry_ratio - 1
        positive = np.flatnonzero(path.iloc[1:].to_numpy() > 0)
        slv_end = frame.SLV.iloc[end]
        out.update(
            {
                f"{key}_mature": True,
                f"{key}_end_date": frame.index[end].date().isoformat(),
                f"{key}_exk_return": float(frame.EXK.iloc[end] / entry_exk - 1),
                f"{key}_sil_return": float(frame.SIL.iloc[end] / entry_sil - 1),
                f"{key}_slv_return": (
                    float(slv_end / entry_slv - 1)
                    if np.isfinite(entry_slv) and np.isfinite(slv_end)
                    else None
                ),
                f"{key}_exk_sil_return": float(frame.EXK_SIL.iloc[end] / entry_ratio - 1),
                f"{key}_mfe_close": float(path.max()),
                f"{key}_mae_close": float(path.min()),
                f"{key}_time_to_positive": int(positive[0] + 1) if len(positive) else None,
                f"{key}_time_underwater": int((path.iloc[1:] < 0).sum()),
                f"{key}_min_relative_return": float(relative_path.min()),
                f"{key}_max_relative_return": float(relative_path.max()),
            }
        )
        out[f"{key}_breakout_failed"] = (
            None
            if meta.get("prior_range_low") is None
            else bool((window.EXK_SIL.iloc[1:] < meta["prior_range_low"]).any())
        )
    return out


def primary_episode_origins(events: list[dict]) -> dict[str, str]:
    earliest: dict[str, tuple[pd.Timestamp, str]] = {}
    for event in events:
        if not adverse(event):
            continue
        episode = str(event.get("episode_id") or event["event_id"])
        public_date = event.get("public_first_tradable_date")
        if not public_date:
            continue
        candidate = (pd.Timestamp(public_date), event["event_id"])
        if episode not in earliest or candidate < earliest[episode]:
            earliest[episode] = candidate
    return {episode: event_id for episode, (_, event_id) in earliest.items()}


def run(events: list[dict], frame: pd.DataFrame, max_wait: int = 60) -> list[dict]:
    rows: list[dict] = []
    origins = primary_episode_origins(events)
    for event in events:
        if not adverse(event):
            continue
        public_date = event.get("public_first_tradable_date")
        episode_id = str(event.get("episode_id") or event["event_id"])
        is_origin = origins.get(episode_id) == event["event_id"]
        if not public_date:
            rows.append(
                {
                    "event_id": event["event_id"],
                    "episode_id": episode_id,
                    "status": "REFUSED",
                    "refusal": "no_public_date",
                    "episode_origin_for_n": is_origin,
                }
            )
            continue
        event_pos = session(frame.index, public_date)
        if event_pos is None:
            rows.append(
                {
                    "event_id": event["event_id"],
                    "episode_id": episode_id,
                    "status": "REFUSED",
                    "refusal": "after_store_end",
                    "episode_origin_for_n": is_origin,
                }
            )
            continue
        for arm in ARMS:
            entry_pos, meta = entry_for(event, arm, frame, event_pos, max_wait)
            base = {
                "event_id": event["event_id"],
                "episode_id": episode_id,
                "study_role": event.get("study_role"),
                "arm": arm,
                "event_public_date": public_date,
                "event_session": frame.index[event_pos].date().isoformat(),
                "design_touched": bool(event.get("design_touched")),
                "episode_origin_for_n": is_origin,
            }
            if entry_pos is None:
                rows.append({**base, **meta, "status": "NO_ENTRY"})
            else:
                rows.append(
                    {
                        **base,
                        **meta,
                        **metrics(frame, entry_pos, meta),
                        "status": "ENTERED",
                        "fill_convention": (
                            "first_public_tradable_close"
                            if arm in ("H0", "H1", "H1B")
                            else "next_common_session_close_after_signal"
                        ),
                    }
                )
    return rows


def summarize(rows: list[dict]) -> dict:
    output = {
        "n_rows": len(rows),
        "n_entered": sum(row.get("status") == "ENTERED" for row in rows),
        "distinct_event_ids": len({row.get("event_id") for row in rows}),
        "distinct_episode_ids": len({row.get("episode_id") for row in rows}),
        "by_arm": {},
    }
    for arm in ARMS:
        entered = [row for row in rows if row.get("arm") == arm and row.get("status") == "ENTERED"]
        primary = [row for row in entered if row.get("episode_origin_for_n")]
        confirmatory = [row for row in primary if not row.get("design_touched")]
        cell = {
            "transition_n_entered": len(entered),
            "episode_origin_n_entered": len(primary),
            "confirmatory_episode_n": len(confirmatory),
            "design_touched_episode_n": len(primary) - len(confirmatory),
        }
        for horizon in HORIZONS:
            descriptive = [
                row.get(f"h{horizon}_exk_sil_return")
                for row in primary
                if row.get(f"h{horizon}_mature")
            ]
            values = [
                row.get(f"h{horizon}_exk_sil_return")
                for row in confirmatory
                if row.get(f"h{horizon}_mature")
            ]
            cell[f"h{horizon}_descriptive_episode_n"] = len(descriptive)
            cell[f"h{horizon}_descriptive_median_relative_return"] = (
                float(np.median(descriptive)) if descriptive else None
            )
            cell[f"h{horizon}_confirmatory_n"] = len(values)
            cell[f"h{horizon}_confirmatory_median_relative_return"] = (
                float(np.median(values)) if values else None
            )
        output["by_arm"][arm] = cell
    return output


def selftest() -> None:
    index = pd.bdate_range("2020-01-01", periods=180)
    sil = 100 * np.exp(np.linspace(0, 0.05, len(index)))
    exk = 10 * np.exp(np.linspace(0, 0.05, len(index)))
    event_pos = 60
    exk[event_pos : event_pos + 10] *= np.linspace(0.8, 0.75, 10)
    exk[event_pos + 10 :] *= np.linspace(0.78, 1.35, len(index) - (event_pos + 10))
    frame = pd.DataFrame({"EXK": exk, "SIL": sil, "SLV": np.nan}, index=index)
    frame["EXK_SIL"] = frame.EXK / frame.SIL
    event = {
        "event_id": "SYN",
        "episode_id": "SYN1",
        "public_first_tradable_date": index[event_pos].date().isoformat(),
        "event_class": "adverse_operational",
        "study_inclusion": "include",
        "recoverability_at_t0": "recoverable",
        "adverse_uncertainty_at_t0": "open",
        "new_adverse_information_at_t0": True,
        "design_touched": False,
    }
    first = run([event], frame)
    second = run([event], frame)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert all(
        row["entry_date"] > row["signal_date"]
        for row in first
        if row.get("status") == "ENTERED" and row.get("arm") in ("H2", "H3", "H4", "H4B")
    )
    touched = run([{**event, "design_touched": True}], frame)
    assert all(value["h5_confirmatory_n"] == 0 for value in summarize(touched)["by_arm"].values())
    duplicate = run(
        [
            event,
            {
                **event,
                "event_id": "SYN-PULSE",
                "public_first_tradable_date": index[event_pos + 5].date().isoformat(),
                "study_role": "adverse_pulse",
            },
        ],
        frame,
    )
    origins = {row["event_id"] for row in duplicate if row.get("episode_origin_for_n")}
    assert origins == {"SYN"}
    print("SELFTEST PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--events", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--max-wait", type=int, default=60)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return 0
    if not args.events or not args.out:
        parser.error("--events and --out required unless --selftest")
    root = args.root.resolve()
    frame, inputs = align(root)
    rows = run(load_events(args.events), frame, args.max_wait)
    payload = {
        "schema": "mastermind.exk_event_replay.v1_1",
        "authority": AUTH,
        "correction": {
            "from": "mastermind.exk_event_replay.v1",
            "reason": "SLV canonical file absent; secondary benchmark is typed UNAVAILABLE and never substituted",
            "primary_logic_changed": False,
            "episode_counting_correction": "all transitions retained; honest N uses first included transition per episode",
        },
        "design": {
            "horizons_sessions": list(HORIZONS),
            "max_confirmation_wait_sessions": args.max_wait,
            "primary_benchmark": "SIL",
            "secondary_benchmark": "SLV_if_canonical_available",
            "H0_H1_H1B_fill": "first_public_tradable_close",
            "H2_H3_H4_H4B_fill": "next_common_session_close_after_signal_close",
        },
        "inputs": inputs,
        "coverage": {
            "first_common_session": frame.index.min().date().isoformat(),
            "last_common_session": frame.index.max().date().isoformat(),
            "n_common_sessions": int(len(frame)),
        },
        "summary": summarize(rows),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {args.out} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
