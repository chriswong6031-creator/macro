"""Wave-2 A-share band-progress construction and substrate gate.

This module intentionally does *not* backtest against ``data/china_stocks_raw``.
That Yahoo plane is split-adjusted even when downloaded with ``auto_adjust=False``;
its historical prices therefore cannot reconstruct exact legal CNY 0.01 limits.

The executable has two jobs until the canonical TuShare full-A spine lands:

1. freeze/test the non-combinatorial signal taxonomy and exchange half-up tick
   arithmetic; and
2. emit a deterministic ``BLOCKED_SUBSTRATE`` receipt.  An explicit legacy audit
   may count off-tick rows and rounding-driven event-key deltas, but it never emits
   transition, return, fill, or strategy metrics.

The later measurement path must join TuShare unadjusted ``daily`` rows to vendor
``stk_limit`` upper/lower prices and an effective-dated security-session spine.
Vendor limit prices are authoritative; locally reconstructed prices are audits.

Run from repository root::

    TZ=UTC python3 scripts/research/cn_limit_band_progress_w2.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "cn_limit_band_progress_w2_substrate/v1"
RECEIPT_DATE = "2026-08-08"
AUTHORITY = "none_research_display_context_only"
TOLERANT_CUSHION = 0.002
# Float32-backed Parquet values such as 8.5299997 represent a legal 8.53 tick.
# Treat only a distance greater than CNY 0.00001 from the nearest cent as off tick.
TICK_ALIGNMENT_EPSILON_CNY = 1e-5

PROTOCOL_PATH = (
    ROOT
    / "research"
    / "cn_limit_alpha_sol"
    / "W2_BAND_PROGRESS_CONSTRUCTION_PROTOCOL_2026-08-08.md"
)
DEFAULT_JSON = (
    ROOT
    / "research"
    / "cn_limit_alpha_sol"
    / "W2_BAND_PROGRESS_SUBSTRATE_RECEIPT_2026-08-08.json"
)
DEFAULT_MARKDOWN = (
    ROOT
    / "research"
    / "cn_limit_alpha_sol"
    / "W2_BAND_PROGRESS_SUBSTRATE_RECEIPT_2026-08-08.md"
)

# These are integration seams, not assertions that the in-flight full-A builder
# must use these exact default locations.  CLI arguments override every path.
DEFAULT_DAILY = ROOT / "data" / "cn_a_share_spine" / "daily"
DEFAULT_LIMITS = ROOT / "data" / "cn_a_share_spine" / "stk_limit"
DEFAULT_CALENDAR = ROOT / "data" / "cn_a_share_spine" / "trade_calendar.parquet"
DEFAULT_SECURITY_SESSIONS = ROOT / "data" / "cn_a_share_spine" / "security_sessions"
DEFAULT_LEGACY_RAW = ROOT / "data" / "china_stocks_raw"
DEFAULT_ST_SNAPSHOT = ROOT / "data" / "china_st" / "st_snapshot.parquet"

DAILY_REQUIRED = frozenset(
    {"ts_code", "trade_date", "open", "high", "low", "close", "pre_close", "vol"}
)
LIMIT_REQUIRED = frozenset({"ts_code", "trade_date", "up_limit", "down_limit"})
CALENDAR_DATE_ALIASES = frozenset({"cal_date", "trade_date", "date", "Date"})
SECURITY_KEY_ALIASES = (
    frozenset({"ts_code", "ticker"}),
    frozenset({"trade_date", "date", "Date"}),
)
SECURITY_REQUIRED = frozenset(
    {
        "board",
        "rule_cohort",
        "session_eligible",
        "rule_known",
        "no_limit",
        "corporate_action_reference_known",
    }
)

TOUCH_RETREAT_IDS = (
    "TF_TOL_ONLY",
    "TF_CP_095_100",
    "TF_CP_080_095",
    "TF_CP_060_080",
    "TF_CP_LT060",
)
NO_TOUCH_HIGH_IDS = (
    "NT_H_095_100",
    "NT_H_080_095",
    "NT_H_060_080",
    "NT_H_040_060",
)
NO_TOUCH_CLOSE_IDS = (
    "NT_C_095_100",
    "NT_C_080_095",
    "NT_C_060_080",
    "NT_C_040_060",
)
ALL_CONSTRUCTION_IDS = (
    "S_STRICT",
    "S_TOL_ONLY",
    *TOUCH_RETREAT_IDS,
    *NO_TOUCH_HIGH_IDS,
    *NO_TOUCH_CLOSE_IDS,
)

UNTESTED_VARIANTS = (
    "first-touch, first-seal, last-seal, break/reseal, sealed duration, and path order",
    "wall growth, depletion, replenishment, cancellation, queue rank, partial fills, and signed flow",
    "opening-auction imbalance and post-09:25 decisions with true 09:30 execution",
    "early failed-seal absorption versus late demand exhaustion",
    "closing-auction-only seals and post-close fixed-price execution",
    "upper-then-lower versus lower-then-upper intraday traversal",
    "multi-step cadence words and flexible 3/5/10-session first-passage paths",
    "T+1 inventory vintages, volume-at-price, free float, unlocks, and queue elasticity",
    "PIT theme topology, spectator substitution, and failed-leader redistribution",
    "ladder topology, hysteresis, and regime interactions",
    "availability-safe LHB, block sponsorship, and catalyst classes",
    "full-universe delisted-name, historical ST, IPO, suspension, and corporate-action truth",
    "board-local nonlinear models, threshold/cash portfolios, and nested confirmation",
    "live fees, slippage, rejection, capacity, sector caps, and mark-to-market drawdown",
    "at least ten prospective graded sessions and every authority-promotion gauntlet",
)


@dataclass(frozen=True)
class SignalState:
    """Daily close/high state under one exact vendor upper limit."""

    strict_seal: bool
    tolerant_close: bool
    tolerant_only: bool
    exact_touch: bool
    exact_touch_failed: bool
    partial_no_touch: bool
    high_progress: float
    close_progress: float


def _finite_positive(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return bool(math.isfinite(number) and number > 0)


def half_up_yuan_tick(value: Any) -> float:
    """Round a positive price to CNY 0.01 with decimal ROUND_HALF_UP.

    The string conversion avoids importing the binary float's hidden tail into
    the decimal contract.  Vendor ``stk_limit`` remains authoritative; this is
    only an exchange-rule reconciliation helper.
    """

    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid tick value: {value!r}") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"tick value must be finite and positive: {value!r}")
    return float(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def half_up_limit_from_tick(pre_close: Any, width: Any, *, side: str = "up") -> float:
    """Reconstruct a limit from a tick-aligned prior close for audit only."""

    try:
        prior = Decimal(str(pre_close))
        band = Decimal(str(width))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("pre_close and width must be decimal-compatible") from exc
    if not prior.is_finite() or prior <= 0:
        raise ValueError("pre_close must be finite and positive")
    if not band.is_finite() or band <= 0 or band >= 1:
        raise ValueError("width must be between zero and one")
    if prior.quantize(Decimal("0.01")) != prior:
        raise ValueError("pre_close is not aligned to the CNY 0.01 tick")
    multiplier = Decimal(1) + band if side == "up" else Decimal(1) - band
    if side not in {"up", "down"}:
        raise ValueError("side must be 'up' or 'down'")
    return float((prior * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def classify_band_state(
    *, pre_close: Any, high: Any, close: Any, up_limit: Any
) -> SignalState:
    """Classify one daily bar without inventing intraday path order."""

    values = (pre_close, high, close, up_limit)
    if not all(_finite_positive(value) for value in values):
        raise ValueError("pre_close/high/close/up_limit must be finite and positive")
    prior, hi, finish, upper = map(float, values)
    span = upper - prior
    if not math.isfinite(span) or span <= 0:
        raise ValueError("up_limit must exceed pre_close")
    high_progress = (hi - prior) / span
    close_progress = (finish - prior) / span
    strict = finish >= upper
    tolerant = finish >= upper * (1.0 - TOLERANT_CUSHION)
    touch = hi >= upper
    return SignalState(
        strict_seal=bool(strict),
        tolerant_close=bool(tolerant),
        tolerant_only=bool(tolerant and not strict),
        exact_touch=bool(touch),
        exact_touch_failed=bool(touch and not strict),
        partial_no_touch=bool(not touch),
        high_progress=float(high_progress),
        close_progress=float(close_progress),
    )


def _progress_bucket(value: float, prefix: str) -> str | None:
    """Return one frozen [0.4, 1.0) progress bucket."""

    if not math.isfinite(value) or value < 0.40 or value >= 1.00:
        return None
    if value >= 0.95:
        suffix = "095_100"
    elif value >= 0.80:
        suffix = "080_095"
    elif value >= 0.60:
        suffix = "060_080"
    else:
        suffix = "040_060"
    return f"{prefix}_{suffix}"


def signal_memberships(state: SignalState) -> tuple[str, ...]:
    """Return frozen construction memberships for one valid state.

    Seal/touch morphology and the two no-touch marginals are deliberately
    separate panels.  A no-touch row can appear once in each marginal; callers
    must never sum the panels as one portfolio.
    """

    memberships: list[str] = []
    if state.strict_seal:
        memberships.append("S_STRICT")
    elif state.tolerant_only:
        memberships.append("S_TOL_ONLY")

    if state.exact_touch_failed:
        if state.tolerant_only:
            memberships.append("TF_TOL_ONLY")
        elif state.close_progress >= 0.95:
            memberships.append("TF_CP_095_100")
        elif state.close_progress >= 0.80:
            memberships.append("TF_CP_080_095")
        elif state.close_progress >= 0.60:
            memberships.append("TF_CP_060_080")
        else:
            memberships.append("TF_CP_LT060")
    elif state.partial_no_touch:
        high_id = _progress_bucket(state.high_progress, "NT_H")
        close_id = _progress_bucket(state.close_progress, "NT_C")
        if high_id:
            memberships.append(high_id)
        if close_id:
            memberships.append(close_id)
    return tuple(memberships)


def entry_proxy_state(
    *, open_price: Any, up_limit: Any, volume: Any, row_present: bool = True
) -> str:
    """Classify the D+1 official-open daily tradability proxy."""

    if not row_present:
        return "missing_bar_halt_or_data_missing_no_fill"
    if not _finite_positive(volume):
        return "zero_volume_halt_or_no_trade_no_fill"
    if not _finite_positive(open_price) or not _finite_positive(up_limit):
        return "price_or_limit_missing_no_fill"
    if float(open_price) >= float(up_limit) * (1.0 - TOLERANT_CUSHION):
        return "upper_queue_no_fill"
    return "daily_tradability_proxy"


def exact_exit_session(
    calendar: Sequence[Any], *, signal_date: Any, exit_id: str
) -> pd.Timestamp | None:
    """Return the frozen T+1-legal scheduled exit date.

    Signal information ends at D close, the candidate entry is D+1 open, and
    the earliest exit is therefore D+2.
    """

    sessions = pd.DatetimeIndex(
        pd.to_datetime(list(calendar), errors="coerce")
    ).normalize()
    sessions = sessions[~sessions.isna()].drop_duplicates().sort_values()
    positions = {date: i for i, date in enumerate(sessions)}
    date = pd.Timestamp(signal_date).normalize()
    start = positions.get(date)
    if start is None:
        return None
    offsets = {"E1_OPEN": 2, "E1_CLOSE": 2, "E3_CLOSE": 4}
    if exit_id not in offsets:
        raise ValueError(f"unknown exit_id: {exit_id}")
    target = start + offsets[exit_id]
    return sessions[target] if target < len(sessions) else None


def run_cluster_ids(
    frame: pd.DataFrame,
    *,
    calendar: Sequence[Any],
    ticker_col: str = "ticker",
    date_col: str = "signal_date",
    construction_col: str = "construction_id",
) -> pd.Series:
    """Assign immutable adjacent-session run IDs without hopping missing dates."""

    sessions = pd.DatetimeIndex(
        pd.to_datetime(list(calendar), errors="coerce")
    ).normalize()
    sessions = sessions[~sessions.isna()].drop_duplicates().sort_values()
    positions = {date: i for i, date in enumerate(sessions)}
    ordered = frame[[ticker_col, date_col, construction_col]].copy()
    ordered[date_col] = pd.to_datetime(
        ordered[date_col], errors="coerce"
    ).dt.normalize()
    ordered["_original"] = np.arange(len(ordered), dtype=np.int64)
    ordered["_position"] = ordered[date_col].map(positions)
    if ordered["_position"].isna().any():
        raise ValueError("signal date is absent from the official calendar")
    ordered = ordered.sort_values(
        [construction_col, ticker_col, date_col, "_original"], kind="mergesort"
    )
    group_cols = [construction_col, ticker_col]
    previous = ordered.groupby(group_cols, sort=False)["_position"].shift(1)
    new_run = previous.isna() | ordered["_position"].ne(previous + 1)
    ordered["_run_number"] = new_run.groupby(
        [ordered[construction_col], ordered[ticker_col]], sort=False
    ).cumsum()
    ordered["_run_id"] = (
        ordered[construction_col].astype(str)
        + ":"
        + ordered[ticker_col].astype(str)
        + ":"
        + ordered["_run_number"].astype(int).astype(str)
    )
    return ordered.set_index("_original")["_run_id"].reindex(range(len(frame)))


def apply_no_duplicate_state_machine(
    frame: pd.DataFrame,
    *,
    ticker_col: str = "ticker",
    signal_date_col: str = "signal_date",
    entry_date_col: str = "entry_date",
    exit_date_col: str = "exit_date",
    fill_state_col: str = "entry_state",
) -> pd.Series:
    """Accept first daily-proxy fill and reject overlap until its exit date.

    Nonfills never reserve capital.  Same-day exit proceeds cannot fund a same-day
    opening entry, so an entry date equal to the prior exit date remains rejected.
    """

    ordered = frame.copy()
    ordered["_original"] = np.arange(len(ordered), dtype=np.int64)
    for column in (signal_date_col, entry_date_col, exit_date_col):
        ordered[column] = pd.to_datetime(
            ordered[column], errors="coerce"
        ).dt.normalize()
    ordered = ordered.sort_values(
        [entry_date_col, signal_date_col, ticker_col, "_original"], kind="mergesort"
    )
    active_until: dict[str, pd.Timestamp] = {}
    states: dict[int, str] = {}
    for _, row in ordered.iterrows():
        original = int(row["_original"])
        if row[fill_state_col] != "daily_tradability_proxy":
            states[original] = "candidate_nonfill_cash"
            continue
        ticker = str(row[ticker_col])
        entry_date = row[entry_date_col]
        exit_date = row[exit_date_col]
        if pd.isna(entry_date):
            states[original] = "candidate_entry_date_missing_cash"
            continue
        prior_exit = active_until.get(ticker)
        if prior_exit is not None and pd.Timestamp(entry_date) <= prior_exit:
            states[original] = "overlap_rejected_cash"
            continue
        if pd.isna(exit_date):
            states[original] = "accepted_fill_exit_unresolved"
            active_until[ticker] = pd.Timestamp.max.normalize()
            continue
        states[original] = "accepted_fill"
        active_until[ticker] = pd.Timestamp(exit_date)
    return pd.Series(states).reindex(range(len(frame)))


def wilson_interval(
    successes: int, total: int, z: float = 1.959963984540054
) -> tuple[float | None, float | None]:
    """Wilson 95% interval for a binary rate."""

    if total <= 0:
        return None, None
    p = float(successes) / float(total)
    denominator = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denominator
    half = (
        z
        * math.sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return max(0.0, centre - half), min(1.0, centre + half)


def cluster_bootstrap_mean(
    values: Sequence[Any],
    clusters: Sequence[Any],
    *,
    reps: int = 1_000,
    seed: int = 20_260_808,
) -> tuple[float | None, float | None]:
    """Deterministic row-weighted one-way cluster-bootstrap interval."""

    frame = pd.DataFrame(
        {"value": pd.to_numeric(values, errors="coerce"), "cluster": clusters}
    )
    frame = frame.dropna(subset=["value", "cluster"])
    if frame.empty:
        return None, None
    grouped = frame.groupby("cluster", sort=True)["value"].agg(["sum", "count"])
    sums = grouped["sum"].to_numpy(dtype=float)
    counts = grouped["count"].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    draws = np.empty(reps, dtype=float)
    n_clusters = len(grouped)
    for i in range(reps):
        sampled = rng.integers(0, n_clusters, size=n_clusters)
        denominator = counts[sampled].sum()
        draws[i] = sums[sampled].sum() / denominator if denominator else np.nan
    finite = draws[np.isfinite(draws)]
    if not len(finite):
        return None, None
    low, high = np.quantile(finite, [0.025, 0.975])
    return float(low), float(high)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata_fingerprint(paths: Iterable[Path], *, root: Path) -> str:
    """Stable path/size fingerprint used only for blocked legacy diagnostics."""

    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(f"{relative}\0{path.stat().st_size}\n".encode())
    return digest.hexdigest()


def canonical_ticker(value: Any) -> str:
    ticker = str(value).strip().upper()
    return f"{ticker[:-3]}.SS" if ticker.endswith(".SH") else ticker


def _board_widths(ticker: str, dates: pd.DatetimeIndex) -> np.ndarray:
    code = canonical_ticker(ticker).split(".")[0]
    if code.startswith(("688", "689")):
        return np.full(len(dates), 0.20, dtype=float)
    if code.startswith(("300", "301", "302")):
        return np.where(dates >= pd.Timestamp("2020-08-24"), 0.20, 0.10)
    if code.startswith(("8", "4", "92")):
        return np.full(len(dates), 0.30, dtype=float)
    return np.full(len(dates), 0.10, dtype=float)


def _vector_half_up_positive(values: np.ndarray) -> np.ndarray:
    """Vector half-up for a legacy diagnostic, not an authority calculation."""

    scaled = values * 100.0
    return np.floor(np.nextafter(scaled, np.inf) + 0.5) / 100.0


def legacy_substrate_diagnostic(
    raw_dir: Path,
    *,
    st_snapshot_path: Path | None = DEFAULT_ST_SNAPSHOT,
    example_limit: int = 20,
) -> dict[str, Any]:
    """Audit the invalid Yahoo plane without producing any strategy metric."""

    files = sorted(raw_dir.glob("*.parquet")) if raw_dir.exists() else []
    if not files:
        return {
            "status": "legacy_raw_absent",
            "authority": "SUBSTRATE_INVALID_DIAGNOSTIC_ONLY",
            "files": 0,
        }

    st_names: set[str] = set()
    if st_snapshot_path is not None and st_snapshot_path.exists():
        st = pd.read_parquet(st_snapshot_path)
        column = (
            "ticker"
            if "ticker" in st.columns
            else "ts_code"
            if "ts_code" in st.columns
            else None
        )
        if column:
            st_names = {canonical_ticker(value) for value in st[column].dropna()}

    counts: dict[str, int] = {
        "rows": 0,
        "rows_with_prior_close": 0,
        "prior_close_not_exact_cent_at_1e_9_cny": 0,
        "prior_close_off_cny_0_01_tick": 0,
        "eligible_width_heuristic_rows": 0,
        "eligible_prior_close_not_exact_cent_at_1e_9_cny": 0,
        "eligible_prior_close_off_cny_0_01_tick": 0,
        "half_up_vs_legacy_upper_price_diff_rows": 0,
        "strict_seal_half_up": 0,
        "strict_seal_legacy": 0,
        "strict_seal_added_by_half_up": 0,
        "strict_seal_removed_by_half_up": 0,
        "exact_touch_half_up": 0,
        "exact_touch_legacy": 0,
        "exact_touch_added_by_half_up": 0,
        "exact_touch_removed_by_half_up": 0,
        "tolerant_close_half_up": 0,
        "tolerant_close_legacy": 0,
        "tolerant_close_symmetric_diff": 0,
        "files_read": 0,
        "files_failed": 0,
        "current_st_files_excluded": 0,
    }
    examples: list[dict[str, Any]] = []
    failed_files: list[str] = []

    for path in files:
        ticker = canonical_ticker(path.stem)
        if ticker in st_names:
            counts["current_st_files_excluded"] += 1
            continue
        try:
            frame = pd.read_parquet(path, columns=["open", "high", "close", "volume"])
        except Exception:  # noqa: BLE001 - diagnostic records the unreadable file
            counts["files_failed"] += 1
            failed_files.append(path.name)
            continue
        counts["files_read"] += 1
        counts["rows"] += len(frame)
        dates = pd.DatetimeIndex(
            pd.to_datetime(frame.index, errors="coerce")
        ).normalize()
        opens = pd.to_numeric(frame["open"], errors="coerce").to_numpy(dtype=float)
        highs = pd.to_numeric(frame["high"], errors="coerce").to_numpy(dtype=float)
        closes = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype=float)
        volumes = pd.to_numeric(frame["volume"], errors="coerce").to_numpy(dtype=float)
        previous = np.roll(closes, 1)
        if len(previous):
            previous[0] = np.nan
        widths = _board_widths(ticker, dates)
        finite_prior = np.isfinite(previous) & (previous > 0)
        counts["rows_with_prior_close"] += int(finite_prior.sum())
        tick_distance_cny = np.abs(previous - np.round(previous, 2))
        not_exact_cent = finite_prior & (tick_distance_cny > 1e-9)
        off_tick = finite_prior & (tick_distance_cny > TICK_ALIGNMENT_EPSILON_CNY)
        counts["prior_close_not_exact_cent_at_1e_9_cny"] += int(not_exact_cent.sum())
        counts["prior_close_off_cny_0_01_tick"] += int(off_tick.sum())

        valid = (
            finite_prior
            & np.isfinite(opens)
            & (opens > 0)
            & np.isfinite(highs)
            & (highs > 0)
            & np.isfinite(closes)
            & (closes > 0)
            & np.isfinite(volumes)
            & (volumes > 0)
        )
        corporate_action_proxy = valid & (
            np.abs(opens - previous) / previous > widths * 1.5
        )
        valid &= ~corporate_action_proxy
        counts["eligible_width_heuristic_rows"] += int(valid.sum())
        counts["eligible_prior_close_not_exact_cent_at_1e_9_cny"] += int(
            (valid & not_exact_cent).sum()
        )
        counts["eligible_prior_close_off_cny_0_01_tick"] += int(
            (valid & off_tick).sum()
        )
        raw_upper = previous * (1.0 + widths)
        half_up = _vector_half_up_positive(raw_upper)
        legacy = np.round(raw_upper, 2)
        price_diff = valid & ~np.isclose(half_up, legacy, rtol=0.0, atol=1e-12)
        counts["half_up_vs_legacy_upper_price_diff_rows"] += int(price_diff.sum())

        strict_half = valid & (closes >= half_up)
        strict_legacy = valid & (closes >= legacy)
        touch_half = valid & (highs >= half_up)
        touch_legacy = valid & (highs >= legacy)
        tolerant_half = valid & (closes >= half_up * (1.0 - TOLERANT_CUSHION))
        tolerant_legacy = valid & (closes >= legacy * (1.0 - TOLERANT_CUSHION))
        counts["strict_seal_half_up"] += int(strict_half.sum())
        counts["strict_seal_legacy"] += int(strict_legacy.sum())
        counts["strict_seal_added_by_half_up"] += int(
            (strict_half & ~strict_legacy).sum()
        )
        counts["strict_seal_removed_by_half_up"] += int(
            (strict_legacy & ~strict_half).sum()
        )
        counts["exact_touch_half_up"] += int(touch_half.sum())
        counts["exact_touch_legacy"] += int(touch_legacy.sum())
        counts["exact_touch_added_by_half_up"] += int(
            (touch_half & ~touch_legacy).sum()
        )
        counts["exact_touch_removed_by_half_up"] += int(
            (touch_legacy & ~touch_half).sum()
        )
        counts["tolerant_close_half_up"] += int(tolerant_half.sum())
        counts["tolerant_close_legacy"] += int(tolerant_legacy.sum())
        counts["tolerant_close_symmetric_diff"] += int(
            (tolerant_half ^ tolerant_legacy).sum()
        )

        changed = np.flatnonzero(
            price_diff & ((strict_half ^ strict_legacy) | (touch_half ^ touch_legacy))
        )
        for index in changed:
            if len(examples) >= example_limit:
                break
            examples.append(
                {
                    "ticker": ticker,
                    "date": str(dates[index].date()),
                    "previous_close": float(previous[index]),
                    "width": float(widths[index]),
                    "high": float(highs[index]),
                    "close": float(closes[index]),
                    "half_up_upper": float(half_up[index]),
                    "legacy_upper": float(legacy[index]),
                    "strict_half_up": bool(strict_half[index]),
                    "strict_legacy": bool(strict_legacy[index]),
                    "touch_half_up": bool(touch_half[index]),
                    "touch_legacy": bool(touch_legacy[index]),
                }
            )

    return {
        "status": "audited_invalid_plane",
        "authority": "SUBSTRATE_INVALID_DIAGNOSTIC_ONLY",
        "warning": (
            "Yahoo raw remains split-adjusted; these are detector-engineering counts only. "
            "No transition, return, fill, or strategy metric was computed."
        ),
        "scope_limitations": [
            "current ST-snapshot intersections excluded across all history",
            "board width inferred from ticker/date only",
            "historical ST, IPO no-limit, and exact corporate-action rules are not reconstructed",
            "vector half-up comparison is diagnostic; vendor stk_limit is the future authority",
        ],
        "tick_alignment_epsilon_cny": TICK_ALIGNMENT_EPSILON_CNY,
        "raw_metadata_fingerprint": _metadata_fingerprint(files, root=raw_dir),
        "files_discovered": len(files),
        "counts": counts,
        "changed_event_key_examples": examples,
        "failed_files": failed_files[:50],
    }


def _parquet_columns(path: Path) -> set[str]:
    """Return the union of Parquet columns for a file or partition directory."""

    try:
        import pyarrow.dataset as ds
    except ImportError as exc:  # pragma: no cover - repo runtime has pyarrow
        raise RuntimeError("pyarrow is required for the substrate gate") from exc
    dataset = ds.dataset(path, format="parquet")
    return set(dataset.schema.names)


def _schema_gate(path: Path, required: set[str] | frozenset[str]) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(
                path.relative_to(ROOT)
                if path.is_absolute() and ROOT in path.parents
                else path
            ),
            "exists": False,
            "columns": [],
            "missing_columns": sorted(required),
            "pass": False,
        }
    try:
        columns = _parquet_columns(path)
        error = None
    except Exception as exc:  # noqa: BLE001 - receipt must preserve gate failure
        columns = set()
        error = f"{type(exc).__name__}: {exc}"
    missing = sorted(set(required) - columns)
    payload: dict[str, Any] = {
        "path": str(
            path.relative_to(ROOT)
            if path.is_absolute() and ROOT in path.parents
            else path
        ),
        "exists": True,
        "columns": sorted(columns),
        "missing_columns": missing,
        "pass": not missing and error is None,
    }
    if error:
        payload["error"] = error
    return payload


def authoritative_substrate_gate(
    *, daily: Path, limits: Path, calendar: Path, security_sessions: Path
) -> dict[str, Any]:
    daily_gate = _schema_gate(daily, DAILY_REQUIRED)
    limits_gate = _schema_gate(limits, LIMIT_REQUIRED)
    calendar_gate = _schema_gate(calendar, set())
    calendar_columns = set(calendar_gate.get("columns") or [])
    if calendar_gate["exists"] and not (calendar_columns & CALENDAR_DATE_ALIASES):
        calendar_gate["missing_columns"] = ["one of: cal_date, trade_date, date, Date"]
        calendar_gate["pass"] = False
    security_gate = _schema_gate(security_sessions, SECURITY_REQUIRED)
    security_columns = set(security_gate.get("columns") or [])
    for aliases in SECURITY_KEY_ALIASES:
        if security_gate["exists"] and not (security_columns & aliases):
            security_gate.setdefault("missing_columns", []).append(
                "one of: " + ", ".join(sorted(aliases))
            )
            security_gate["pass"] = False
    gates = {
        "tushare_unadjusted_daily": daily_gate,
        "tushare_vendor_stk_limit": limits_gate,
        "official_trade_calendar": calendar_gate,
        "effective_dated_security_sessions": security_gate,
    }
    return {
        "gates": gates,
        "all_schema_gates_pass": all(bool(gate.get("pass")) for gate in gates.values()),
        "row_level_measurement_gates_run": False,
        "row_level_measurement_gates_pending": [
            "unique normalized ticker/date keys",
            "exact calendar and security-session join",
            "stk_limit missingness below 0.5 percent",
            "positive valid OHLCV and ordered vendor limits",
            "official tick alignment",
            "vendor reference-price and corporate-action consistency",
            "exact successor and exit horizon support",
        ],
    }


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def build_receipt(
    *,
    daily: Path,
    limits: Path,
    calendar: Path,
    security_sessions: Path,
    legacy_raw: Path | None,
    st_snapshot: Path | None,
) -> dict[str, Any]:
    gate = authoritative_substrate_gate(
        daily=daily,
        limits=limits,
        calendar=calendar,
        security_sessions=security_sessions,
    )
    if gate["all_schema_gates_pass"]:
        status = "CONSTRUCTION_ONLY_ROW_GATES_AND_MEASUREMENT_NOT_RUN"
        verdict = "BLOCKED_SUBSTRATE_NO_STRATEGY_MEASUREMENT"
        blocker = (
            "schema seams exist, but the row-level full-A identity/rule/limit gates and "
            "measurement implementation have not been adjudicated"
        )
    else:
        status = "BLOCKED_SUBSTRATE"
        verdict = "BLOCKED_SUBSTRATE_NO_STRATEGY_MEASUREMENT"
        blocker = "authoritative TuShare daily + stk_limit + calendar + security-session inputs are absent or incomplete"
    legacy = (
        legacy_substrate_diagnostic(legacy_raw, st_snapshot_path=st_snapshot)
        if legacy_raw is not None
        else {
            "status": "not_requested",
            "authority": "SUBSTRATE_INVALID_DIAGNOSTIC_ONLY",
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "receipt_date": RECEIPT_DATE,
        "authority": AUTHORITY,
        "status": status,
        "verdict": verdict,
        "blocker": blocker,
        "strategy_metrics_emitted": False,
        "transition_rates_emitted": False,
        "return_metrics_emitted": False,
        "fill_metrics_emitted": False,
        "instrument": {
            "path": str(Path(__file__).resolve().relative_to(ROOT)),
            "sha256": _sha256_file(Path(__file__).resolve()),
        },
        "construction_protocol": {
            "path": str(PROTOCOL_PATH.relative_to(ROOT)),
            "sha256": _sha256_file(PROTOCOL_PATH),
            "frozen_before_measurement": True,
            "construction_ids": list(ALL_CONSTRUCTION_IDS),
            "tolerant_close_is_legal_seal": False,
            "daily_bars_can_claim_path_order": False,
            "entry_clock": "D close information to D+1 official-open daily_tradability_proxy",
            "exits": ["E1_OPEN_D+2", "E1_CLOSE_D+2", "E3_CLOSE_D+4"],
            "cost_bps_round_trip": [0, 30, 60, 100],
            "bootstrap": {
                "date_clusters": True,
                "run_clusters": True,
                "repetitions": 1000,
                "seed": 20260808,
            },
        },
        "authoritative_substrate": gate,
        "legacy_substrate_diagnostic": legacy,
        "ore_ledger": {
            "law": (
                "A blocked or adverse exact construction cannot close the family; "
                "untested variants remain explicit and append-only."
            ),
            "untested_variants": list(UNTESTED_VARIANTS),
        },
        "next_action": (
            "bind this frozen taxonomy to the committed full-A TuShare daily/stk_limit/security-session "
            "spine, run every row-level gate, then implement and execute the deterministic measurement"
        ),
    }


def render_markdown(receipt: Mapping[str, Any]) -> str:
    gate = receipt["authoritative_substrate"]
    lines = [
        "# CN limit-move alpha — Wave-2 band-progress substrate receipt",
        "",
        f"**Date:** {receipt['receipt_date']}",
        f"**Authority:** {receipt['authority']}",
        f"**Status:** `{receipt['status']}`",
        f"**Verdict:** `{receipt['verdict']}`",
        "",
        "## Outcome",
        "",
        (
            "The construction grammar is frozen, but no strategy measurement is admissible yet. "
            "The historical Yahoo plane remains split-adjusted and cannot reconstruct legal CNY "
            "0.01 limit prices. No transition, return, fill, or strategy metric appears in this receipt."
        ),
        "",
        f"Exact blocker: {receipt['blocker']}.",
        "",
        "## Authoritative input gates",
        "",
        "| Plane | Exists | Schema pass | Missing columns / contract |",
        "|---|---:|---:|---|",
    ]
    for name, payload in gate["gates"].items():
        missing = ", ".join(payload.get("missing_columns") or []) or "—"
        lines.append(
            f"| `{name}` | {str(bool(payload.get('exists'))).lower()} | "
            f"{str(bool(payload.get('pass'))).lower()} | {missing} |"
        )
    lines.extend(
        [
            "",
            (
                "Row-level uniqueness, join, tick, limit-ordering, corporate-action, and exact-exit-clock "
                "gates remain pending even if the file schemas appear."
            ),
            "",
            "## Frozen definitions",
            "",
            "- Strict seal: close at or above vendor `stk_limit.up_limit`.",
            "- Tolerant-only close: inside the 0.2% cushion but below the legal ceiling; sensitivity only.",
            "- Exact-touch failure: daily high reaches the vendor ceiling and close finishes below it.",
            (
                "- Partial no-touch: high remains below the ceiling, with parallel fixed high-progress and "
                "close-progress buckets at 0.40/0.60/0.80/0.95."
            ),
            (
                "- Entry: D-close information to D+1 official-open `daily_tradability_proxy`; upper queue "
                "and missing rows remain cash zero."
            ),
            "- Earliest exit: D+2 under A-share T+1; daily bars cannot claim intraday sequence or fill.",
            "",
            "## Legacy-plane diagnostic",
            "",
        ]
    )
    legacy = receipt["legacy_substrate_diagnostic"]
    lines.append(
        f"Status: `{legacy.get('status')}`; authority: `{legacy.get('authority')}`."
    )
    counts = legacy.get("counts") or {}
    if counts:
        lines.extend(
            [
                "",
                f"- Files read / discovered: **{counts.get('files_read', 0):,} / {legacy.get('files_discovered', 0):,}**",
                f"- Stored rows: **{counts.get('rows', 0):,}**",
                f"- Prior closes checked: **{counts.get('rows_with_prior_close', 0):,}**",
                f"- Eligible prior closes not exactly cent-valued at CNY 1e-9: **{counts.get('eligible_prior_close_not_exact_cent_at_1e_9_cny', 0):,} / {counts.get('eligible_width_heuristic_rows', 0):,}**",
                f"- Eligible prior closes materially off tick by more than CNY {TICK_ALIGNMENT_EPSILON_CNY:g}: **{counts.get('eligible_prior_close_off_cny_0_01_tick', 0):,}**",
                f"- Half-up versus legacy upper-price differences: **{counts.get('half_up_vs_legacy_upper_price_diff_rows', 0):,}**",
                f"- Strict-seal key additions/removals under half-up: **{counts.get('strict_seal_added_by_half_up', 0):,} / {counts.get('strict_seal_removed_by_half_up', 0):,}**",
                f"- Exact-touch key additions/removals under half-up: **{counts.get('exact_touch_added_by_half_up', 0):,} / {counts.get('exact_touch_removed_by_half_up', 0):,}**",
                "",
                "These are detector-engineering counts on an invalid substrate, not market findings.",
            ]
        )
    lines.extend(["", "## UNTESTED VARIANTS", ""])
    lines.extend(f"- {item}" for item in receipt["ore_ledger"]["untested_variants"])
    lines.extend(
        [
            "",
            "## Next action",
            "",
            receipt["next_action"] + ".",
            "",
        ]
    )
    return "\n".join(lines)


def write_receipts(
    receipt: Mapping[str, Any], *, json_path: Path, markdown_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(_canonical_json(receipt), encoding="utf-8")
    markdown_path.write_text(render_markdown(receipt), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily", type=Path, default=DEFAULT_DAILY)
    parser.add_argument("--limits", type=Path, default=DEFAULT_LIMITS)
    parser.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR)
    parser.add_argument(
        "--security-sessions", type=Path, default=DEFAULT_SECURITY_SESSIONS
    )
    parser.add_argument("--legacy-raw-dir", type=Path, default=DEFAULT_LEGACY_RAW)
    parser.add_argument("--st-snapshot", type=Path, default=DEFAULT_ST_SNAPSHOT)
    parser.add_argument("--skip-legacy-audit", action="store_true")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    receipt = build_receipt(
        daily=args.daily,
        limits=args.limits,
        calendar=args.calendar,
        security_sessions=args.security_sessions,
        legacy_raw=None if args.skip_legacy_audit else args.legacy_raw_dir,
        st_snapshot=args.st_snapshot,
    )
    write_receipts(receipt, json_path=args.json, markdown_path=args.markdown)
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "verdict": receipt["verdict"],
                "strategy_metrics_emitted": receipt["strategy_metrics_emitted"],
                "json": str(args.json),
                "markdown": str(args.markdown),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
