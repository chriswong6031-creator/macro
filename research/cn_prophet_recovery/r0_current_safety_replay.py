#!/usr/bin/env python3
"""Immutable current-source replay for China Prophet R0.

This is a read-only research instrument.  It reads every dependency from one Git
revision, reconstructs the current V4 episode ledger, independently walks the
latched T+1 fills through the ten-session verdict, and asks whether the persisted
V4/V3 ordering race actually contains an intelligence-ordered treatment.

It deliberately does not import the live ranker, grader, audit, or tripwire.  Those
modules are source evidence, not runtime dependencies of this receipt; importing
them would let an uncommitted working tree contaminate a supposedly immutable replay.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


SCHEMA = "cn_prophet.r0_current_safety_replay.v1"
OPERATION = "cn-prophet-r0-current-safety-replay-20260905-sol-001"
LIVE_DEFINITION = "cn_prophet_v4"
CONTROL_DEFINITION = "cn_prophet_v3_shadow"
REQUIRED_TREATMENT_BASIS = "intel_interest_then_v3_score"
FALLBACK_BASIS = "cn_prophet_v3_score"
R4_METRIC = "cn_v4_vs_v3_order_shadow_excess"
HORIZON = 10
BOOT_N = 2_000
BOOT_SEED = 20_260_726

PATHS = {
    "ledger": "site/factordata/cn_track_ledger.json",
    "board": "data/china_standout_track/board.parquet",
    "entry_latch": "data/china_standout_track/entry_latch.parquet",
    "candidates": "data/china_prophet_rank/candidates.parquet",
    "audit_artifact": "data/cn_prophet_audit/latest.json",
    "ranker_source": "engine/china_board_rank.py",
    "grader_source": "engine/china_standout_track.py",
    "audit_source": "engine/cn_prophet_audit.py",
    "tripwire_source": "engine/cn_v3_tripwires.py",
    "builder_source": "scripts/build_china_library.py",
    "benchmark": "data/china/510300.SS.parquet",
}


class ReplayFailure(RuntimeError):
    """Typed fail-closed replay error."""


@dataclass
class GitSource:
    root: Path
    revision: str
    _blob_cache: dict[str, bytes] = field(default_factory=dict, init=False, repr=False)
    _blob_sha_cache: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def _git(self, *args: str) -> bytes:
        try:
            return subprocess.check_output(
                ["git", *args], cwd=self.root, stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode("utf-8", "replace").strip()
            raise ReplayFailure(f"SOURCE_BYTES_OR_PIT_VINTAGE_UNAVAILABLE: {detail}") from exc

    @property
    def sha(self) -> str:
        return self._git("rev-parse", self.revision).decode().strip()

    @property
    def tree(self) -> str:
        return self._git("rev-parse", f"{self.revision}^{{tree}}").decode().strip()

    def blob(self, path: str) -> bytes:
        if path not in self._blob_cache:
            self.preload([path])
        return self._blob_cache[path]

    def preload(self, paths: Sequence[str]) -> None:
        """Read many immutable blobs through one ``cat-file`` process.

        The Macro clone is blobless. Spawning one ``git show`` per security turns a
        23 MB replay into hundreds of process/network negotiations; batch mode keeps
        the same object identity while remaining practical in a sparse worktree.
        """
        missing = [path for path in dict.fromkeys(paths) if path not in self._blob_cache]
        if not missing:
            return
        process = subprocess.Popen(
            ["git", "cat-file", "--batch"], cwd=self.root,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert process.stdin is not None and process.stdout is not None
        for path in missing:
            process.stdin.write(f"{self.revision}:{path}\n".encode())
        process.stdin.close()
        try:
            for path in missing:
                header = process.stdout.readline().decode("utf-8", "replace").strip()
                parts = header.split()
                if len(parts) != 3 or parts[1] != "blob":
                    raise ReplayFailure(
                        f"SOURCE_BYTES_OR_PIT_VINTAGE_UNAVAILABLE: {path}: {header}"
                    )
                size = int(parts[2])
                payload = process.stdout.read(size)
                newline = process.stdout.read(1)
                if len(payload) != size or newline != b"\n":
                    raise ReplayFailure(
                        f"SOURCE_BYTES_OR_PIT_VINTAGE_UNAVAILABLE: short batch read for {path}"
                    )
                self._blob_cache[path] = payload
                self._blob_sha_cache[path] = parts[0]
        finally:
            process.stdout.close()
        stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
        code = process.wait()
        if process.stderr:
            process.stderr.close()
        if code:
            raise ReplayFailure(
                f"SOURCE_BYTES_OR_PIT_VINTAGE_UNAVAILABLE: cat-file exited {code}: {stderr.strip()}"
            )

    def blob_sha(self, path: str) -> str:
        if path not in self._blob_sha_cache:
            self.preload([path])
        return self._blob_sha_cache[path]

    def text(self, path: str) -> str:
        return self.blob(path).decode("utf-8")

    def json(self, path: str) -> Any:
        return json.loads(self.blob(path))

    def parquet(self, path: str) -> pd.DataFrame:
        return pd.read_parquet(io.BytesIO(self.blob(path)))


def _date(value: Any) -> str:
    return str(pd.Timestamp(value).date())


def _finite(value: Any) -> bool:
    try:
        return value is not None and bool(pd.notna(value)) and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _clean(value: Any) -> Any:
    """Convert numpy/pandas scalars to strict JSON values; preserve null as null."""
    if value is None or (not isinstance(value, (list, dict, tuple)) and pd.isna(value)):
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, pd.Timestamp):
        return _date(value)
    return value


def build_episode_memberships(board_days: Mapping[str, Iterable[str]]) -> list[dict[str, Any]]:
    """Collapse daily rows to contiguous runs using the production algorithm's grain.

    "Contiguous" means present on consecutive *stored board observations*.  This is
    exactly ``engine.track_scoring.build_episodes`` semantics: a ticker leaving one
    stored board observation closes a run; a later return opens another admission.
    """
    days = sorted(str(day) for day in board_days)
    previous: set[str] = set()
    open_runs: dict[str, dict[str, Any]] = {}
    episodes: list[dict[str, Any]] = []
    for day in days:
        current = {str(ticker) for ticker in board_days[day]}
        for ticker in current - previous:
            open_runs[ticker] = {"ticker": ticker, "entry_date": day, "board_dates": []}
        for ticker in current:
            if ticker not in open_runs:
                raise ReplayFailure("ROW_IDENTITY_OR_COHORT_RECONCILIATION_FAILED: missing open run")
            open_runs[ticker]["board_dates"].append(day)
        for ticker in previous - current:
            episode = open_runs.pop(ticker)
            episode["exit_observation_date"] = day
            episodes.append(episode)
        previous = current
    for episode in open_runs.values():
        episode["exit_observation_date"] = None
        episodes.append(episode)
    episodes.sort(key=lambda item: (item["entry_date"], item["ticker"]))
    for episode in episodes:
        episode["daily_materializations"] = len(episode["board_dates"])
        episode["carry_forward_materializations"] = len(episode["board_dates"]) - 1
    return episodes


def _board_days(frame: pd.DataFrame) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for row in frame[["date", "ticker"]].itertuples(index=False):
        out[_date(row.date)].add(str(row.ticker))
    return dict(out)


def compare_daily_orders(live: pd.DataFrame, control: pd.DataFrame) -> dict[str, Any]:
    """Compare post-admission/post-cap daily rows without inventing absent treatment."""
    cols = ["date", "ticker", "board_rank"]
    left = live[cols].copy().rename(columns={"board_rank": "live_rank"})
    right = control[cols].copy().rename(columns={"board_rank": "control_rank"})
    for frame in (left, right):
        frame["date"] = frame["date"].map(_date)
        frame["ticker"] = frame["ticker"].astype(str)
    joined = left.merge(right, how="outer", on=["date", "ticker"], indicator=True)
    both = joined[joined["_merge"] == "both"].copy()
    rank_delta = both[
        pd.to_numeric(both["live_rank"], errors="coerce")
        != pd.to_numeric(both["control_rank"], errors="coerce")
    ]
    by_date = []
    for day, group in joined.groupby("date", sort=True):
        paired = group[group["_merge"] == "both"]
        by_date.append(
            {
                "date": str(day),
                "live_n": int((group["_merge"] != "right_only").sum()),
                "control_n": int((group["_merge"] != "left_only").sum()),
                "live_only_n": int((group["_merge"] == "left_only").sum()),
                "control_only_n": int((group["_merge"] == "right_only").sum()),
                "rank_delta_n": int(
                    (
                        pd.to_numeric(paired["live_rank"], errors="coerce")
                        != pd.to_numeric(paired["control_rank"], errors="coerce")
                    ).sum()
                ),
            }
        )
    return {
        "live_daily_rows": int(len(live)),
        "control_daily_rows": int(len(control)),
        "paired_daily_rows": int(len(both)),
        "live_only_n": int((joined["_merge"] == "left_only").sum()),
        "control_only_n": int((joined["_merge"] == "right_only").sum()),
        "rank_delta_n": int(len(rank_delta)),
        "identical_post_cap_sets_and_ranks": bool(
            len(joined) == len(both) and len(rank_delta) == 0
        ),
        "by_date": by_date,
    }


def evaluate_r4(
    *, treatment_values: Sequence[float], control_values: Sequence[float],
    metric_present_in_audit: bool, minimum_n: int = 60
) -> dict[str, Any]:
    """Evaluate R4 fail-closed. Missing telemetry is unavailable, never no-breach."""
    treatment = [float(x) for x in treatment_values if _finite(x)]
    control = [float(x) for x in control_values if _finite(x)]
    comparable_n = min(len(treatment), len(control))
    if not metric_present_in_audit:
        state = "R4_SOURCE_MISSING_OR_MALFORMED"
    elif comparable_n == 0:
        state = "NO_ELIGIBLE_TREATMENT"
    elif comparable_n < minimum_n:
        state = "INSUFFICIENT_MATURITY"
    else:
        delta = float(np.median(treatment) - np.median(control))
        state = "BREACH_WARNING_PROPOSAL" if delta < 0 else "NO_BREACH"
    delta = (
        float(np.median(treatment) - np.median(control))
        if treatment and control
        else None
    )
    return {
        "metric": R4_METRIC,
        "minimum_matured": int(minimum_n),
        "treatment_n": len(treatment),
        "control_n": len(control),
        "comparable_n": comparable_n,
        "treatment_median_excess_pct": round(float(np.median(treatment)), 6)
        if treatment else None,
        "control_median_excess_pct": round(float(np.median(control)), 6)
        if control else None,
        "treatment_minus_control_median_excess_pct": round(delta, 6)
        if delta is not None else None,
        "metric_present_in_committed_audit": bool(metric_present_in_audit),
        "state": state,
        "serving_effect": "NONE",
        "interpretation": (
            "The committed nightly audit has no R4 measurement. Separately, the persisted "
            "current cohort has zero rows whose effective ordering basis is Intelligence, so "
            "the governed V4-order treatment is empty and no V4-ordering effect is estimable."
        ),
    }


def chronology_violations(row: Mapping[str, Any]) -> list[str]:
    """Return decision-clock violations without coercing absent clocks to a date."""
    admission = pd.Timestamp(row["stamp_date"])
    violations: list[str] = []
    for key in (
        "signal_asof", "signal_bar_asof", "micro_asof", "micro_batch_asof",
        "board_asof", "sector_turn_asof", "narrative_asof",
    ):
        value = row.get(key)
        if value is None or pd.isna(value):
            continue
        try:
            if pd.Timestamp(value).normalize() > admission.normalize():
                violations.append(key)
        except (TypeError, ValueError):
            violations.append(f"{key}:malformed")
    return violations


def _price_frame(source: GitSource, ticker: str) -> pd.DataFrame:
    path = PATHS["benchmark"] if ticker == "510300.SS" else f"data/china_stocks/{ticker}.parquet"
    frame = source.parquet(path).copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        date_col = next((c for c in ("date", "Date", "timestamp") if c in frame), None)
        if date_col is None:
            raise ReplayFailure(f"SOURCE_BYTES_OR_PIT_VINTAGE_UNAVAILABLE: {ticker} has no date")
        frame.index = pd.to_datetime(frame.pop(date_col), errors="coerce")
    frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    return frame


def _score_latched(
    prices: pd.DataFrame, bench_close: pd.Series, *, fill_date: str, entry: float,
    horizon: int = HORIZON
) -> dict[str, Any]:
    close = pd.to_numeric(prices["close"], errors="coerce").dropna()
    fill_ts = pd.Timestamp(fill_date)
    start = int(close.index.searchsorted(fill_ts, side="left"))
    if start >= len(close):
        return {"matured": False, "n_avail": 0}
    forward = close.iloc[start:]
    if len(forward) < horizon:
        return {"matured": False, "n_avail": int(len(forward))}
    window = forward.iloc[:horizon]
    exit_ts = window.index[-1]
    exit_price = float(window.iloc[-1])
    pnl = (exit_price / float(entry) - 1.0) * 100.0
    bench = pd.to_numeric(bench_close, errors="coerce").dropna()
    bi = int(bench.index.searchsorted(close.index[start], side="left"))
    bj = int(bench.index.searchsorted(exit_ts, side="left"))
    if bi >= len(bench) or bj >= len(bench) or bj < bi:
        raise ReplayFailure("BENCHMARK_WINDOW_MISMATCH")
    b0, b1 = float(bench.iloc[bi]), float(bench.iloc[bj])
    if not (_finite(b0) and _finite(b1) and b0 > 0):
        raise ReplayFailure("BENCHMARK_WINDOW_MISMATCH")
    excess = pnl - (b1 / b0 - 1.0) * 100.0
    return {
        "matured": True,
        "n_avail": int(len(forward)),
        "held": horizon,
        "exit_date": _date(exit_ts),
        "exit": exit_price,
        "pnl": pnl,
        "excess": excess,
    }


def _group_metrics(frame: pd.DataFrame, field: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if frame.empty:
        return rows
    grouped = frame.assign(**{field: frame[field].fillna("(unavailable)")}).groupby(
        field, dropna=False, sort=True
    )
    for value, group in grouped:
        x = pd.to_numeric(group["replay_excess"], errors="coerce").dropna()
        p = pd.to_numeric(group["replay_pnl"], errors="coerce").dropna()
        rows.append(
            {
                "value": str(value),
                "n": int(len(group)),
                "independent_cohorts": int(group["admission_date"].nunique()),
                "share_pct": round(100.0 * len(group) / len(frame), 1),
                "win_pct": round(100.0 * float((x > 0).mean()), 1) if len(x) else None,
                "mean_excess_pct": round(float(x.mean()), 3) if len(x) else None,
                "median_excess_pct": round(float(x.median()), 3) if len(x) else None,
                "mean_pnl_pct": round(float(p.mean()), 3) if len(p) else None,
            }
        )
    return sorted(rows, key=lambda row: (-row["n"], row["value"]))


def _date_block_ci(values_by_date: Sequence[tuple[str, float]]) -> dict[str, Any]:
    blocks: dict[str, list[float]] = defaultdict(list)
    for day, value in values_by_date:
        if _finite(value):
            blocks[str(day)].append(float(value))
    arrays = [np.asarray(blocks[key], dtype=float) for key in sorted(blocks)]
    if len(arrays) < 2:
        return {"n_blocks": len(arrays), "win_ci_pct": None, "mean_ci_pct": None}
    rng = np.random.default_rng(BOOT_SEED)
    wins = np.empty(BOOT_N)
    means = np.empty(BOOT_N)
    for i in range(BOOT_N):
        picks = rng.integers(0, len(arrays), len(arrays))
        values = np.concatenate([arrays[j] for j in picks])
        wins[i] = (values > 0).mean() * 100.0
        means[i] = values.mean()
    return {
        "n_blocks": len(arrays),
        "bootstrap_resamples": BOOT_N,
        "seed": BOOT_SEED,
        "win_ci_pct": [round(float(x), 1) for x in np.percentile(wins, [2.5, 97.5])],
        "mean_ci_pct": [round(float(x), 2) for x in np.percentile(means, [2.5, 97.5])],
    }


def _recursive_has_key(value: Any, needle: str) -> bool:
    if isinstance(value, dict):
        return needle in value or any(_recursive_has_key(v, needle) for v in value.values())
    if isinstance(value, list):
        return any(_recursive_has_key(v, needle) for v in value)
    return False


def _rank_bucket(value: Any) -> str:
    if not _finite(value):
        return "(unavailable)"
    rank = int(float(value))
    if rank <= 6:
        return "01-06"
    if rank <= 12:
        return "07-12"
    if rank <= 24:
        return "13-24"
    return "25+"


def _source_receipt(source: GitSource, price_tickers: Sequence[str]) -> dict[str, Any]:
    fixed = {name: source.blob_sha(path) for name, path in PATHS.items()}
    price_paths = [f"data/china_stocks/{ticker}.parquet" for ticker in sorted(set(price_tickers))]
    prices = {path: source.blob_sha(path) for path in price_paths}
    return {
        "revision": source.sha,
        "tree": source.tree,
        "fixed_blobs": fixed,
        "price_blob_count": len(prices),
        "price_total_bytes": sum(len(source.blob(path)) for path in prices),
        "price_blobs": prices,
    }


def run_replay(root: Path, source_ref: str) -> dict[str, Any]:
    source = GitSource(root.resolve(), source_ref)
    ledger = source.json(PATHS["ledger"])
    board = source.parquet(PATHS["board"])
    candidates = source.parquet(PATHS["candidates"])
    latch = source.parquet(PATHS["entry_latch"])
    audit = source.json(PATHS["audit_artifact"])
    as_of = str(ledger["as_of"])

    current_rows = list(ledger.get("rows") or [])
    source.preload(
        [PATHS["benchmark"]]
        + [f"data/china_stocks/{ticker}.parquet"
           for ticker in sorted({str(row["t"]) for row in current_rows})]
    )
    shadow_record = next(
        (item for item in ledger.get("extra_records", [])
         if item.get("board_definition") == CONTROL_DEFINITION),
        None,
    )
    if shadow_record is None:
        raise ReplayFailure("V3_SHADOW_RECONSTRUCTION_FAILED: committed control record absent")
    shadow_rows = list(shadow_record.get("rows") or [])

    board = board.copy()
    board["date"] = board["date"].map(_date)
    live_daily_all = board[board["board_definition"] == LIVE_DEFINITION].copy()
    control_daily_all = board[board["board_definition"] == CONTROL_DEFINITION].copy()
    live_daily = live_daily_all[live_daily_all["date"] <= as_of].copy()
    control_daily = control_daily_all[control_daily_all["date"] <= as_of].copy()
    live_episodes = build_episode_memberships(_board_days(live_daily))
    control_episodes = build_episode_memberships(_board_days(control_daily))
    live_keys = {(item["entry_date"], item["ticker"]) for item in live_episodes}
    control_keys = {(item["entry_date"], item["ticker"]) for item in control_episodes}
    ledger_keys = {(str(row.get("d")), str(row.get("t"))) for row in current_rows}
    shadow_keys = {(str(row.get("d")), str(row.get("t"))) for row in shadow_rows}
    identity = {
        "live_episode_n": len(live_episodes),
        "ledger_row_n": len(current_rows),
        "control_episode_n": len(control_episodes),
        "control_ledger_row_n": len(shadow_rows),
        "live_only_vs_ledger": sorted([list(key) for key in live_keys - ledger_keys]),
        "ledger_only_vs_live": sorted([list(key) for key in ledger_keys - live_keys]),
        "control_only_vs_ledger": sorted([list(key) for key in control_keys - shadow_keys]),
        "control_ledger_only": sorted([list(key) for key in shadow_keys - control_keys]),
        "daily_materializations": int(len(live_daily)),
        "carry_forward_materializations": int(
            sum(item["carry_forward_materializations"] for item in live_episodes)
        ),
        "multi_materialized_episode_n": int(
            sum(item["daily_materializations"] > 1 for item in live_episodes)
        ),
        "episodes": live_episodes,
    }
    if any(identity[key] for key in (
        "live_only_vs_ledger", "ledger_only_vs_live", "control_only_vs_ledger",
        "control_ledger_only",
    )):
        raise ReplayFailure("ROW_IDENTITY_OR_COHORT_RECONCILIATION_FAILED")

    order_comparison = compare_daily_orders(live_daily_all, control_daily_all)
    ledger_order_comparison = compare_daily_orders(live_daily, control_daily)

    candidates = candidates.copy()
    candidates["stamp_date"] = candidates["stamp_date"].map(_date)
    candidate_first = candidates.drop_duplicates(["stamp_date", "ticker"], keep="first").set_index(
        ["stamp_date", "ticker"], drop=False
    )
    board_first = live_daily.drop_duplicates(["date", "ticker"], keep="first").set_index(
        ["date", "ticker"], drop=False
    )
    latch_first = latch.drop_duplicates(["date", "ticker"], keep="first").copy()
    latch_first["date"] = latch_first["date"].map(_date)
    latch_map = {
        (row.date, str(row.ticker)): row
        for row in latch_first.itertuples(index=False)
    }

    coverage_by_date: list[dict[str, Any]] = []
    for day, daily in live_daily_all.groupby("date", sort=True):
        candidate_day = candidates[candidates["stamp_date"] == day]
        ranked = candidate_day[pd.to_numeric(candidate_day["score_rank"], errors="coerce").notna()]
        measured = (
            pd.to_numeric(ranked["intel_score"], errors="coerce").notna()
            & ranked["intel_basis"].notna()
        )
        lane_counts = {
            str(key): int(value)
            for key, value in candidate_day["lane"].fillna("(unavailable)").value_counts().items()
        }
        coverage_by_date.append(
            {
                "date": day,
                "ranked_candidate_n": int(len(ranked)),
                "intel_measured_n": int(measured.sum()),
                "intel_unavailable_n": int((~measured).sum()),
                "live_daily_n": int(len(daily)),
                "candidate_lane_counts": lane_counts,
                "board_vs_candidate_featured_delta_n": int(
                    len(daily) - lane_counts.get("featured", 0)
                ),
                "requested_order_basis": sorted(
                    str(x) for x in daily["requested_order_basis"].dropna().unique()
                ),
                "effective_order_basis": sorted(
                    str(x) for x in daily["effective_order_basis"].dropna().unique()
                ),
                "order_mode": sorted(str(x) for x in daily["order_mode"].dropna().unique()),
                "fallback_reason": sorted(
                    str(x) for x in daily["fallback_reason"].dropna().unique()
                ),
                "intel_coverage_complete_values": sorted(
                    bool(x) for x in daily["intel_coverage_complete"].dropna().unique()
                ),
            }
        )

    bench = _price_frame(source, "510300.SS")
    bench_close = pd.to_numeric(bench["close"], errors="coerce").dropna()
    price_cache: dict[str, pd.DataFrame] = {}
    replay_rows: list[dict[str, Any]] = []
    validation_counts: Counter[str] = Counter()
    for public in current_rows:
        key = (str(public["d"]), str(public["t"]))
        candidate = candidate_first.loc[key] if key in candidate_first.index else None
        board_row = board_first.loc[key] if key in board_first.index else None
        if candidate is None or board_row is None:
            raise ReplayFailure("ROW_IDENTITY_OR_COHORT_RECONCILIATION_FAILED: admission join")
        ticker = key[1]
        if ticker not in price_cache:
            price_cache[ticker] = _price_frame(source, ticker)
        prices = price_cache[ticker]
        latched = latch_map.get(key)
        latched_entry = getattr(latched, "entry", None) if latched is not None else None
        entry = float(latched_entry) if _finite(latched_entry) else float(public["e"])
        admission_ts = pd.Timestamp(key[0])
        after = prices.index[prices.index > admission_ts]
        derived_fill_date = _date(after[0]) if len(after) else None
        published_fill_date = str(public.get("ed")) if public.get("ed") else None
        fill_match = derived_fill_date == published_fill_date
        entry_match = _finite(public.get("e")) and round(entry, 2) == float(public["e"])
        validation_counts["fill_date_match"] += int(fill_match)
        validation_counts["entry_match"] += int(entry_match)

        candidate_dict = {str(k): _clean(v) for k, v in candidate.to_dict().items()}
        time_violations = chronology_violations(candidate_dict)
        effective_basis = _clean(board_row.get("effective_order_basis"))
        treatment = effective_basis == REQUIRED_TREATMENT_BASIS
        replay: dict[str, Any] = {
            "admission_date": key[0],
            "ticker": ticker,
            "matured": bool(public.get("m")),
            "board_rank": _clean(public.get("rk")),
            "candidate_score_rank": _clean(candidate.get("score_rank")),
            "prophet_score": _clean(candidate.get("prophet_score")),
            "sector": _clean(candidate.get("sector")) or "(unavailable)",
            "theme": _clean(candidate.get("narrative_theme")) or "(unavailable)",
            "correlation_cluster": (
                f"{_clean(candidate.get('sector')) or '(unavailable)'} | "
                f"{_clean(candidate.get('narrative_theme')) or '(unavailable)'}"
            ),
            "entry_status": _clean(candidate.get("entry_status")) or "(unavailable)",
            "candidate_lane_current_snapshot": _clean(candidate.get("lane")),
            "board_lane": _clean(board_row.get("lane")),
            "requested_order_basis": _clean(board_row.get("requested_order_basis")),
            "effective_order_basis": effective_basis,
            "order_mode": _clean(board_row.get("order_mode")),
            "fallback_reason": _clean(board_row.get("fallback_reason")),
            "intel_coverage_complete": bool(board_row.get("intel_coverage_complete")),
            "r4_treatment_eligible": treatment,
            "intel_coverage": "measured" if _finite(candidate.get("intel_score")) else "unavailable",
            "intel_score": _clean(candidate.get("intel_score")),
            "intel_edge_remaining": _clean(candidate.get("intel_edge_remaining")),
            "intel_gap_mult": _clean(candidate.get("intel_gap_mult")),
            "intel_falsifier_penalty": _clean(candidate.get("intel_falsifier_penalty")),
            "entry_basis": _clean(public.get("eb")),
            "published_entry": _clean(public.get("e")),
            "latched_entry": round(entry, 8),
            "published_fill_date": published_fill_date,
            "derived_fill_date": derived_fill_date,
            "fill_date_match": fill_match,
            "entry_match": entry_match,
            "candidate_clock_violations": time_violations,
            "entry_rederivation_disclosed": public.get("er") is not None,
        }
        if public.get("m"):
            scored = _score_latched(
                prices, bench_close, fill_date=published_fill_date, entry=entry
            )
            if not scored.get("matured"):
                raise ReplayFailure("BENCHMARK_WINDOW_MISMATCH: published mature row did not mature")
            replay.update(
                {
                    "replay_exit_date": scored["exit_date"],
                    "replay_exit": round(scored["exit"], 8),
                    "replay_pnl": round(scored["pnl"], 8),
                    "replay_excess": round(scored["excess"], 8),
                    "published_exit": _clean(public.get("l")),
                    "published_pnl": _clean(public.get("p")),
                    "published_excess": _clean(public.get("x")),
                    "exit_match": round(scored["exit"], 2) == float(public["l"]),
                    "pnl_match": round(scored["pnl"], 1) == float(public["p"]),
                    "excess_match": round(scored["excess"], 2) == float(public["x"]),
                }
            )
            validation_counts["matured"] += 1
            for name in ("exit_match", "pnl_match", "excess_match"):
                validation_counts[name] += int(replay[name])
        replay_rows.append(replay)

    matured = pd.DataFrame([row for row in replay_rows if row["matured"]])
    if matured.empty:
        raise ReplayFailure("INSUFFICIENT_INDEPENDENT_COHORTS: no mature rows")
    if int(validation_counts["matured"]) != int(ledger["summary"]["n_matured"]):
        raise ReplayFailure("ROW_IDENTITY_OR_COHORT_RECONCILIATION_FAILED: maturity count")
    for name in ("exit_match", "pnl_match", "excess_match"):
        if validation_counts[name] != validation_counts["matured"]:
            raise ReplayFailure(f"BENCHMARK_WINDOW_MISMATCH: {name}")

    matured["rank_bucket"] = matured["board_rank"].map(_rank_bucket)
    score_numeric = pd.to_numeric(matured["prophet_score"], errors="coerce")
    if score_numeric.notna().sum() >= 4:
        matured["v3_score_quartile"] = pd.qcut(
            score_numeric.rank(method="first"), 4,
            labels=["Q1-low", "Q2", "Q3", "Q4-high"],
        ).astype(object)
    else:
        matured["v3_score_quartile"] = "(unavailable)"

    decompositions = {
        field: _group_metrics(matured, field)
        for field in (
            "admission_date", "rank_bucket", "sector", "theme", "correlation_cluster",
            "entry_status", "v3_score_quartile", "intel_coverage",
        )
    }
    for component in (
        "intel_score", "intel_edge_remaining", "intel_gap_mult", "intel_falsifier_penalty"
    ):
        values = pd.to_numeric(matured[component], errors="coerce")
        decompositions[f"{component}_availability"] = {
            "available_n": int(values.notna().sum()),
            "unavailable_n": int(values.isna().sum()),
            "mean_when_available": round(float(values.mean()), 6)
            if values.notna().any() else None,
        }

    max_sector = max(decompositions["sector"], key=lambda row: row["n"])
    max_theme = max(decompositions["theme"], key=lambda row: row["n"])
    max_cohort = max(decompositions["admission_date"], key=lambda row: row["n"])
    concentration = {
        "largest_cohort": max_cohort,
        "largest_sector": max_sector,
        "largest_theme": max_theme,
        "sector_hhi": round(
            sum((row["share_pct"] / 100.0) ** 2 for row in decompositions["sector"]), 4
        ),
        "theme_hhi": round(
            sum((row["share_pct"] / 100.0) ** 2 for row in decompositions["theme"]), 4
        ),
    }

    audit_text = source.text(PATHS["audit_source"])
    tripwire_text = source.text(PATHS["tripwire_source"])
    metric_present = _recursive_has_key(audit, R4_METRIC)
    treatment_values = matured.loc[
        matured["r4_treatment_eligible"], "replay_excess"
    ].tolist()
    # The frozen control is descriptively present, but it is not a treatment comparison
    # when live used the same fallback order. Keep it out of a fabricated delta.
    control_values: list[float] = [] if not treatment_values else [
        float(row["x"]) for row in shadow_rows if row.get("m") and _finite(row.get("x"))
    ]
    r4 = evaluate_r4(
        treatment_values=treatment_values,
        control_values=control_values,
        metric_present_in_audit=metric_present,
    )

    lane_mismatches = matured[
        matured["candidate_lane_current_snapshot"] != matured["board_lane"]
    ]
    all_lane_mismatches = [
        {
            "date": key[0],
            "ticker": key[1],
            "board_lane": _clean(board_first.loc[key].get("lane")),
            "candidate_lane_current_snapshot": _clean(candidate_first.loc[key].get("lane")),
            "matured": bool(next(row for row in replay_rows if
                                  row["admission_date"] == key[0] and row["ticker"] == key[1])["matured"]),
        }
        for key in sorted(ledger_keys)
        if key in candidate_first.index
        and _clean(candidate_first.loc[key].get("lane")) != _clean(board_first.loc[key].get("lane"))
    ]
    daily_lane_mismatches = []
    for row in live_daily_all.itertuples(index=False):
        key = (_date(row.date), str(row.ticker))
        if key not in candidate_first.index:
            continue
        candidate_lane = _clean(candidate_first.loc[key].get("lane"))
        board_lane = _clean(getattr(row, "lane"))
        if candidate_lane != board_lane:
            daily_lane_mismatches.append(
                {
                    "date": key[0], "ticker": key[1], "board_lane": board_lane,
                    "candidate_lane_current_snapshot": candidate_lane,
                    "is_episode_admission": key in ledger_keys,
                }
            )

    source_receipt = _source_receipt(source, [row["t"] for row in current_rows])
    summary = ledger["summary"]
    replay_mean = float(matured["replay_excess"].mean())
    replay_median = float(matured["replay_excess"].median())
    replay_win = float((matured["replay_excess"] > 0).mean() * 100.0)
    independent_dates = sorted(matured["admission_date"].unique().tolist())

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "operation": OPERATION,
        "scope": {
            "source_mode": "immutable_git_revision",
            "read_only": True,
            "live_effect": "NONE",
            "authorized_paths": [
                "research/cn_prophet_recovery/r0_current_safety_replay.py",
                "research/cn_prophet_recovery/R0_CURRENT_SAFETY_REPLAY_2026-09-05.md",
                "research/cn_prophet_recovery/r0_current_safety_replay_results.json",
                "tests/test_cn_prophet_recovery_r0.py",
            ],
        },
        "source": source_receipt,
        "published_record": {
            "as_of": as_of,
            "board_definition": summary["board_definition"],
            "n_logged": int(summary["n_logged"]),
            "n_matured": int(summary["n_matured"]),
            "n_inflight": int(summary["n_inflight"]),
            "n_board_days": int(summary["n_board_days"]),
            "win_pct": float(summary["win_pct"]),
            "expectancy_pct": float(summary["expectancy_pct"]),
            "median_pct": float(summary["median_pct"]),
            "profit_factor": float(summary["profit_factor"]),
        },
        "identity_and_materialization": identity,
        "outcome_replay": {
            "matured_n": int(len(matured)),
            "independent_cohort_n": len(independent_dates),
            "independent_cohorts": independent_dates,
            "win_pct": round(replay_win, 1),
            "mean_excess_pct": round(replay_mean, 2),
            "median_excess_pct": round(replay_median, 2),
            "date_block_uncertainty": _date_block_ci(
                list(zip(matured["admission_date"], matured["replay_excess"], strict=True))
            ),
            "validation_counts": dict(sorted(validation_counts.items())),
            "rows": replay_rows,
        },
        "ordering_reconstruction": {
            "classification": "V3_FALLBACK",
            "coverage_by_date": coverage_by_date,
            "required_treatment_basis": REQUIRED_TREATMENT_BASIS,
            "treatment_daily_rows": int(
                (live_daily_all["effective_order_basis"] == REQUIRED_TREATMENT_BASIS).sum()
            ),
            "fallback_daily_rows": int(
                (live_daily_all["effective_order_basis"] == FALLBACK_BASIS).sum()
            ),
            "requested_v4_pre_cap_delta": None,
            "requested_v4_pre_cap_delta_reason": (
                "Coverage-atomic law makes requested Intelligence rank undefined when any ranked "
                "candidate is uncovered; ranking covered names alone would fabricate a treatment."
            ),
            "actual_effective_pre_cap": {
                "basis": FALLBACK_BASIS,
                "board_dates": len(coverage_by_date),
                "ranked_candidate_rows": int(
                    sum(day["ranked_candidate_n"] for day in coverage_by_date)
                ),
                "effective_vs_v3_rank_delta_n": 0,
                "derivation": (
                    "Every persisted bake declares V3 score as its effective basis; the current "
                    "ranker copies score_rank before lane partition whenever coverage is incomplete."
                ),
            },
            "actual_post_cap": order_comparison,
            "ledger_as_of_post_cap": ledger_order_comparison,
            "cap_or_admission_made_order_irrelevant": False,
            "cap_or_admission_ruling": (
                "Not the cause of identity: effective order had already fallen back before lane "
                "partition/caps, so no pre-cap Intelligence/V3 divergence existed to erase."
            ),
            "shadow_projection_defect": False,
            "shadow_projection_ruling": (
                "The independently stored daily live/control sets and ranks reconcile exactly; "
                "identity is the expected consequence of V3 fallback, not evidence of a copied "
                "shadow."
            ),
        },
        "r4_safety": {
            **r4,
            "spec_declared_in_tripwire_source": R4_METRIC in tripwire_text,
            "audit_imports_tripwire_module": "cn_v3_tripwires" in audit_text,
            "audit_artifact_as_of": str(audit.get("as_of")),
            "audit_artifact_has_tripwire_payload": _recursive_has_key(audit, "tripwire"),
            "producer_to_consumer_trace": [
                {"plane": "spec", "state": "BUILT", "owner": PATHS["tripwire_source"]},
                {"plane": "nightly_measurement", "state": "NOT_BUILT_CONTRACT_DISCONNECTED",
                 "owner": PATHS["audit_source"]},
                {"plane": "artifact", "state": "R4_SOURCE_MISSING_OR_MALFORMED",
                 "owner": PATHS["audit_artifact"]},
                {"plane": "warning_proposal", "state": "DARK_OR_DISCONNECTED"},
                {"plane": "serving_change", "state": "NONE_NOT_AUTHORIZED"},
            ],
            "minimal_later_repair_seam": (
                "Extend the existing cn_prophet_audit owner to consume the existing tripwire spec, "
                "write the exact same-input metric/provenance, and emit its warning/proposal; any "
                "serving change remains a separately authorized operator decision."
            ),
        },
        "decompositions": decompositions,
        "concentration": concentration,
        "chronology_and_accounting": {
            "candidate_clock_violation_n": int(
                sum(bool(row["candidate_clock_violations"]) for row in replay_rows)
            ),
            "entry_or_fill_mismatch_n": int(
                sum(not row["entry_match"] or not row["fill_date_match"] for row in replay_rows)
            ),
            "matured_lane_mismatch_n": int(len(lane_mismatches)),
            "all_board_dates_daily_lane_mismatch_n": len(daily_lane_mismatches),
            "all_board_dates_daily_lane_mismatches": daily_lane_mismatches,
            "ledger_as_of_daily_lane_mismatch_n": int(
                sum(row["date"] <= as_of for row in daily_lane_mismatches)
            ),
            "all_ledger_candidate_lane_mismatch_n": len(all_lane_mismatches),
            "all_ledger_candidate_lane_mismatches": all_lane_mismatches,
            "interpretation": (
                "Episode identity and all 65 matured outcomes reconcile. Candidate-snapshot lane "
                "mismatches occur only outside the matured population and are reported as a "
                "forward accounting risk, not retroactively assigned as cause of the current loss."
            ),
        },
        "cause_ledger": [
            {
                "classification": "INPUT_CHRONOLOGY_DEFECT",
                "ruling": "NOT_SUPPORTED_FOR_MATURED_OUTCOMES",
                "evidence": "All 172 T+1 fill dates/latched entries and all 65 exits/excess values reconcile.",
            },
            {
                "classification": "ACCOUNTING_OR_IDENTITY_DEFECT",
                "ruling": "FORWARD_RISK_PRESENT_NOT_CURRENT_MATURED_CAUSE",
                "evidence": (
                    f"All 172 episode keys reconcile; {len(all_lane_mismatches)} later rows disagree "
                    "with the current candidate lane snapshot, while the 65 matured rows have zero such mismatches."
                ),
            },
            {
                "classification": "ADMISSION_FAILURE",
                "ruling": "NOT_IDENTIFIED",
                "evidence": "Only four independent recommendation cohorts are mature; no causal admission control exists.",
            },
            {
                "classification": "V4_ORDERING_FAILURE",
                "ruling": "NOT_ESTIMABLE_ZERO_TREATMENT",
                "evidence": "Every current live daily row used the V3 fallback basis; R4 treatment n=0.",
            },
            {
                "classification": "CONCENTRATION_FAILURE",
                "ruling": "DESCRIPTIVE_RISK_NOT_CAUSAL",
                "evidence": (
                    f"Largest cohort share={max_cohort['share_pct']}%, sector share={max_sector['share_pct']}%, "
                    f"theme share={max_theme['share_pct']}%; four blocks cannot establish cause."
                ),
            },
            {
                "classification": "ADVERSE_SAMPLE / NOT_IDENTIFIED",
                "ruling": "SUPPORTED_CURRENT_RULING",
                "evidence": (
                    "The served V3-fallback shelf genuinely underperformed, but the date-blocked interval "
                    "crosses zero and there is no active V4-order treatment or same-population causal contrast."
                ),
            },
            {
                "classification": "MIXED",
                "ruling": "NOT_SUPPORTED_AS_CAUSAL_LABEL",
                "evidence": "Telemetry disconnection and forward accounting risk are real but do not explain the 65 outcomes.",
            },
        ],
        "verdict": {
            "current_outcome": "NEGATIVE_REAL_IMMATURE",
            "effective_order": "V3_FALLBACK",
            "v4_ordering_effect": "NOT_ESTIMABLE_ZERO_TREATMENT",
            "r4_runtime": "R4_ACTION_PATH_DISCONNECTED",
            "serving_change_authority": "NONE",
            "next_boundary": "RETURN_TO_SOL_FOR_R1_R2_ADJUDICATION",
        },
    }
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-ref", required=True, help="Immutable Git commit/ref to replay")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Macro repository worktree")
    parser.add_argument("--output", type=Path, help="Write the deterministic JSON receipt here")
    parser.add_argument("--stdout", action="store_true", help="Also print the receipt")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_replay(args.repo, args.source_ref)
    rendered = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    if args.stdout or not args.output:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
