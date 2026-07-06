"""engine/rule_replay.py — R1 core: fire-tape × policy-grid replay engine.

Per §3.1–3.3 of NW_RAILS_AND_TIER1_LOBES_PROGRAM_BY_FABLE.md.

Architecture
------------
RuleSpec (frozen dataclass)
    • spec_id: human slug
    • cohort: CohortFilter — conjunction of predicates over replay_boarded columns
    • delay_n: int — fill-offset bars (default 1 = production next-bar fill)
    • exit: ExitPolicy — one of the frozen v1 exit policies
    • weight: "full" — constant weight only (sizing variants are v2)
    • horizons_ref: list[int] — reference horizon(s) for regret metrics (default [126])

ExitPolicy (frozen enum v1):
    hold(H)                 — time exit at H bars, H ∈ {5, 10, 21, 42, 63, 126}
    ema_trail(span, resamp)  — canonical EMA8 trail-flag (IMPORTS from signal_quality)
    trail_stop(pct)         — high-watermark trailing stop
    barrier(stop, target)   — close-only bracket

Per-fire path outputs (§3.2):
    exit_bar_offset, exit_ret, mae_to_exit, mfe_to_exit, holding_days,
    censored, foregone_mfe, avoided_mae

ERA LAW splits:
    verdict_grade_2021plus (massive, uncensored) → absolute rates allowed
    survivor_biased → within-cohort deltas only, stamped

Governor: all callers must provide a registry-validated spec list; results
refuse to serialize without a vintage stamp (engine.vintage_stamp.require_stamp).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable

import numpy as np
import pandas as pd

from engine.grading import fill_index
from engine.vintage_stamp import StampRefusal, require_stamp

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ERA LAW constants (mirrors replay_standout_pipeline.MASSIVE_ERA_START)
# ---------------------------------------------------------------------------
MASSIVE_ERA_START = pd.Timestamp("2021-07-06")

# Frozen v1 hold horizons (§3.1)
VALID_HOLD_HORIZONS: frozenset[int] = frozenset({5, 10, 21, 42, 63, 126})

# Frozen v1 trail_stop pcts (§3.1)
VALID_TRAIL_STOP_PCTS: frozenset[int] = frozenset({8, 12, 15, 20})


# ---------------------------------------------------------------------------
# ExitPolicy — frozen v1 enum
# ---------------------------------------------------------------------------
class ExitKind(Enum):
    HOLD = auto()
    EMA_TRAIL = auto()
    TRAIL_STOP = auto()
    BARRIER = auto()


@dataclass(frozen=True)
class ExitPolicy:
    """Frozen v1 exit policy.

    Construct via the class-method factories — never instantiate directly.
    """
    kind: ExitKind
    # HOLD
    hold_bars: int | None = None
    # EMA_TRAIL
    ema_span: int | None = None
    ema_resample: str | None = None
    # TRAIL_STOP
    trail_pct: float | None = None
    # BARRIER
    stop_pct: float | None = None
    target_pct: float | None = None

    # ---- factories ----
    @classmethod
    def hold(cls, H: int) -> "ExitPolicy":
        if H not in VALID_HOLD_HORIZONS:
            raise ValueError(
                f"hold(H): H={H!r} is not in the frozen v1 set {sorted(VALID_HOLD_HORIZONS)}. "
                "Extending the enum requires a program amendment."
            )
        return cls(kind=ExitKind.HOLD, hold_bars=H)

    @classmethod
    def ema_trail(cls, span: int = 8, resample: str = "3B") -> "ExitPolicy":
        """Canonical EMA8 trail-flag. MUST use signal_quality's resample grid — §3.1."""
        return cls(kind=ExitKind.EMA_TRAIL, ema_span=span, ema_resample=resample)

    @classmethod
    def trail_stop(cls, pct: float) -> "ExitPolicy":
        pct_int = int(pct)
        if pct_int not in VALID_TRAIL_STOP_PCTS:
            raise ValueError(
                f"trail_stop(pct): pct={pct!r} is not in frozen v1 set "
                f"{sorted(VALID_TRAIL_STOP_PCTS)}."
            )
        return cls(kind=ExitKind.TRAIL_STOP, trail_pct=float(pct))

    @classmethod
    def barrier(cls, stop_pct: float, target_pct: float) -> "ExitPolicy":
        if stop_pct >= 0:
            raise ValueError(
                f"barrier: stop_pct must be negative (e.g. -5 = 5% stop), got {stop_pct!r}"
            )
        if target_pct <= 0:
            raise ValueError(
                f"barrier: target_pct must be positive (e.g. 8 = 8% target), got {target_pct!r}"
            )
        return cls(kind=ExitKind.BARRIER, stop_pct=float(stop_pct), target_pct=float(target_pct))

    def to_dict(self) -> dict[str, Any]:
        """Stable, canonical serialization for hashing."""
        if self.kind == ExitKind.HOLD:
            return {"kind": "hold", "H": self.hold_bars}
        if self.kind == ExitKind.EMA_TRAIL:
            return {"kind": "ema_trail", "span": self.ema_span, "resample": self.ema_resample}
        if self.kind == ExitKind.TRAIL_STOP:
            return {"kind": "trail_stop", "pct": self.trail_pct}
        if self.kind == ExitKind.BARRIER:
            return {"kind": "barrier", "stop_pct": self.stop_pct, "target_pct": self.target_pct}
        raise ValueError(f"Unknown ExitKind: {self.kind}")  # pragma: no cover

    def slug(self) -> str:
        """Human-readable slug for spec_id construction."""
        d = self.to_dict()
        k = d["kind"]
        if k == "hold":
            return f"hold_{d['H']}"
        if k == "ema_trail":
            return f"ema_trail_s{d['span']}"
        if k == "trail_stop":
            return f"trail_stop_{int(d['pct'])}pct"
        if k == "barrier":
            sp = str(d['stop_pct']).replace('-', 'n').replace('.', 'p')
            tp = str(d['target_pct']).replace('.', 'p')
            return f"barrier_s{sp}_t{tp}"
        return k  # pragma: no cover


# ---------------------------------------------------------------------------
# CohortFilter — conjunction of equality/threshold predicates
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CohortFilter:
    """Conjunction of predicates over replay_boarded columns (v1: existing columns ONLY).

    Each predicate is one of:
        eq(col, val)       — exact equality
        ge(col, val)       — >=
        le(col, val)       — <=
        isin(col, vals)    — membership in a frozenset

    Stored as a tuple of (op, col, val) triples for hashability.
    """
    predicates: tuple = field(default_factory=tuple)

    def to_list(self) -> list[dict]:
        """Stable serialization for hashing."""
        return [{"op": op, "col": col, "val": val if not isinstance(val, frozenset) else sorted(val)}
                for op, col, val in self.predicates]

    def apply(self, df: pd.DataFrame) -> pd.Series:
        """Return a boolean mask for rows matching ALL predicates."""
        mask = pd.Series(True, index=df.index)
        for op, col, val in self.predicates:
            if col not in df.columns:
                log.warning("CohortFilter: column %r not in DataFrame — treating as no-match", col)
                mask &= False
                continue
            if op == "eq":
                mask &= df[col] == val
            elif op == "ge":
                mask &= df[col] >= val
            elif op == "le":
                mask &= df[col] <= val
            elif op == "isin":
                mask &= df[col].isin(val)
            else:
                raise ValueError(f"CohortFilter: unknown op {op!r}")
        return mask


def cohort_filter(*predicates: tuple) -> CohortFilter:
    """Build a CohortFilter from tuples of (op, col, val)."""
    return CohortFilter(predicates=tuple(predicates))


# ---------------------------------------------------------------------------
# RuleSpec — frozen dataclass with canonical content hash
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RuleSpec:
    """Frozen v1 rule specification.

    spec_id      — human slug (e.g. "exit_grid_v1/hold_21")
    cohort       — CohortFilter over replay_boarded columns
    delay_n      — fill offset bars (1 = standard next-bar fill)
    exit         — ExitPolicy instance
    weight       — "full" (v1 constant weight; sizing variants are v2)
    horizons_ref — reference horizons for regret metrics

    The content hash is sha256 of canonical JSON (sorted keys, no spec_id).
    spec_id is excluded from the hash so that a renamed spec with identical
    parameters is recognised as the same experiment cell.
    """
    spec_id: str
    cohort: CohortFilter
    delay_n: int = 1
    exit: ExitPolicy = field(default_factory=lambda: ExitPolicy.hold(21))
    weight: str = "full"
    horizons_ref: tuple[int, ...] = (126,)

    def __post_init__(self) -> None:
        if self.weight != "full":
            raise ValueError(
                f"RuleSpec.weight must be 'full' in v1; got {self.weight!r}. "
                "Sizing variants are planned for v2."
            )
        if self.delay_n < 0:
            raise ValueError(f"RuleSpec.delay_n must be >= 0, got {self.delay_n!r}")
        for h in self.horizons_ref:
            if h not in VALID_HOLD_HORIZONS:
                raise ValueError(
                    f"RuleSpec.horizons_ref contains {h!r}, which is not in "
                    f"the frozen v1 set {sorted(VALID_HOLD_HORIZONS)}."
                )

    def _canonical_dict(self) -> dict[str, Any]:
        """Stable canonical dict for hashing (spec_id excluded)."""
        return {
            "cohort": self.cohort.to_list(),
            "delay_n": self.delay_n,
            "exit": self.exit.to_dict(),
            "weight": self.weight,
            "horizons_ref": sorted(self.horizons_ref),
        }

    def content_hash(self) -> str:
        """sha256 of canonical JSON (sorted keys). Stable across runs."""
        canonical = json.dumps(self._canonical_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Full serialization including spec_id and content_hash."""
        d = self._canonical_dict()
        d["spec_id"] = self.spec_id
        d["content_hash"] = self.content_hash()
        return d


# ---------------------------------------------------------------------------
# EMA trail: import from signal_quality (§3.1 — NEVER re-implement)
# ---------------------------------------------------------------------------
def _compute_ema_trail_series(
    daily_close: pd.Series,
    span: int = 8,
    resample: str = "3B",
) -> tuple[pd.Series, pd.Series]:
    """Compute the EMA trail series and fresh-breach mask, using signal_quality's exact grid.

    IMPORTS engine.signal_quality.signal_frame for the '3B' resampled close, then
    applies the same ema_trail and fresh_breach logic from signal_quality.analyze().

    Returns
    -------
    ema_trail : pd.Series on the 3B index
    fresh_breach : pd.Series[bool] on the 3B index
    """
    from engine.signal_quality import signal_frame as _sf

    sig = _sf(daily_close)
    if sig.empty or "ema_trail" not in sig.columns:
        return pd.Series(dtype=float), pd.Series(dtype=bool)

    # Replicate the exact logic from signal_quality.analyze() (lines 203-207)
    c = sig["close"]
    trail = sig["ema_trail"]
    below = (c < trail)
    prev_below = below.shift(1, fill_value=False)
    rising_into = (trail.shift(1) > trail.shift(3))
    fresh_breach = (below & ~prev_below & rising_into).fillna(False)

    return trail, fresh_breach


# ---------------------------------------------------------------------------
# Per-fire path computation
# ---------------------------------------------------------------------------
def _compute_per_fire(
    close: pd.Series,
    fill_idx: int,
    exit_policy: ExitPolicy,
    horizons_ref: tuple[int, ...],
) -> dict[str, Any]:
    """Compute exit metrics for a single fire given the split-adjusted close.

    Parameters
    ----------
    close       : split-adjusted daily close Series (DatetimeIndex)
    fill_idx    : iloc of the fill bar (from grading.fill_index)
    exit_policy : ExitPolicy
    horizons_ref: reference horizons for regret (typically (126,))

    Returns
    -------
    dict with keys: exit_bar_offset, exit_ret, mae_to_exit, mfe_to_exit,
        holding_days, censored, foregone_mfe_{H}, avoided_mae_{H} for each H
    """
    entry_price = float(close.iloc[fill_idx])
    # Forward path: the bars AFTER the fill bar (strictly forward, §3.2 convention)
    max_H = max(horizons_ref)
    fwd_slice = close.iloc[fill_idx + 1 : fill_idx + 1 + max_H]

    result: dict[str, Any] = {
        "exit_bar_offset": None,
        "exit_ret": None,
        "mae_to_exit": None,
        "mfe_to_exit": None,
        "holding_days": None,
        "censored": False,
    }

    # Compute reference horizon metrics for regret calculation
    for H in horizons_ref:
        fwd_h = close.iloc[fill_idx + 1 : fill_idx + 1 + H]
        if len(fwd_h) < H:
            result[f"fwd_mfe_{H}"] = None
            result[f"fwd_mdd_{H}"] = None
        else:
            prices = fwd_h.values.astype(float)
            result[f"fwd_mfe_{H}"] = float(np.max(prices) / entry_price - 1)
            result[f"fwd_mdd_{H}"] = float(min(0.0, np.min(prices) / entry_price - 1))

    if len(fwd_slice) == 0:
        result["censored"] = True
        for H in horizons_ref:
            result[f"foregone_mfe_{H}"] = None
            result[f"avoided_mae_{H}"] = None
        return result

    prices = fwd_slice.values.astype(float)
    dates = fwd_slice.index

    # ----- determine exit bar offset -----
    exit_offset: int | None = None

    if exit_policy.kind == ExitKind.HOLD:
        H = exit_policy.hold_bars  # type: ignore[assignment]
        if len(fwd_slice) >= H:
            exit_offset = H - 1  # 0-indexed into fwd_slice
        else:
            result["censored"] = True
            exit_offset = len(fwd_slice) - 1

    elif exit_policy.kind == ExitKind.EMA_TRAIL:
        # Build a close series from fill_idx onward (including the fill bar as anchor)
        anchor_slice = close.iloc[fill_idx:]
        trail_series, fresh_breach = _compute_ema_trail_series(
            anchor_slice, span=exit_policy.ema_span or 8, resample=exit_policy.ema_resample or "3B"
        )
        # Map trail breach dates back to daily close dates
        exit_date: pd.Timestamp | None = None
        for breach_date in fresh_breach[fresh_breach].index:
            # Find the corresponding daily bar
            matching = anchor_slice.index[anchor_slice.index >= breach_date]
            if len(matching) > 0:
                exit_date = matching[0]
                break
        if exit_date is not None and exit_date > close.index[fill_idx]:
            # find offset in fwd_slice
            fwd_dates_arr = dates.to_numpy()
            exit_date_np = np.datetime64(exit_date)
            idxs = np.where(fwd_dates_arr >= exit_date_np)[0]
            if len(idxs) > 0:
                exit_offset = int(idxs[0])
            else:
                exit_offset = len(fwd_slice) - 1
                result["censored"] = True
        else:
            # No breach found in the forward path — censor at max_H
            exit_offset = len(fwd_slice) - 1
            result["censored"] = True

    elif exit_policy.kind == ExitKind.TRAIL_STOP:
        pct = exit_policy.trail_pct or 0.0
        trail_mult = 1.0 - pct / 100.0
        hwm = entry_price
        exit_offset = None
        for i, p in enumerate(prices):
            if p > hwm:
                hwm = p
            stop_level = hwm * trail_mult
            if p <= stop_level:
                exit_offset = i
                break
        if exit_offset is None:
            exit_offset = len(fwd_slice) - 1
            result["censored"] = True

    elif exit_policy.kind == ExitKind.BARRIER:
        stop_mult = 1.0 + (exit_policy.stop_pct or 0.0) / 100.0
        tgt_mult = 1.0 + (exit_policy.target_pct or 0.0) / 100.0
        exit_offset = None
        for i, p in enumerate(prices):
            rel = p / entry_price
            if rel <= stop_mult or rel >= tgt_mult:
                exit_offset = i
                break
        if exit_offset is None:
            exit_offset = len(fwd_slice) - 1
            result["censored"] = True

    else:
        raise ValueError(f"Unknown ExitKind: {exit_policy.kind}")  # pragma: no cover

    # ----- fill in exit metrics -----
    if exit_offset is not None and exit_offset < len(fwd_slice):
        exit_price = float(prices[exit_offset])
        result["exit_bar_offset"] = exit_offset + 1  # 1-indexed from fill bar
        result["exit_ret"] = exit_price / entry_price - 1
        # MAE / MFE up to exit
        path_to_exit = prices[:exit_offset + 1]
        result["mae_to_exit"] = float(min(0.0, np.min(path_to_exit) / entry_price - 1))
        result["mfe_to_exit"] = float(np.max(path_to_exit) / entry_price - 1)
        # holding_days: calendar days from fill bar to exit bar
        fill_date = close.index[fill_idx]
        exit_date_val = dates[exit_offset]
        result["holding_days"] = (exit_date_val - fill_date).days

    # ----- regret metrics -----
    for H in horizons_ref:
        fwd_mfe = result.get(f"fwd_mfe_{H}")
        mfe_to_exit = result.get("mfe_to_exit")
        fwd_mdd = result.get(f"fwd_mdd_{H}")
        mae_to_exit = result.get("mae_to_exit")

        if fwd_mfe is None or mfe_to_exit is None:
            result[f"foregone_mfe_{H}"] = None
        else:
            result[f"foregone_mfe_{H}"] = max(0.0, fwd_mfe - mfe_to_exit)

        if fwd_mdd is None or mae_to_exit is None:
            result[f"avoided_mae_{H}"] = None
        else:
            result[f"avoided_mae_{H}"] = max(0.0, abs(fwd_mdd) - abs(mae_to_exit))

    return result


# ---------------------------------------------------------------------------
# ERA LAW cohort splitter
# ---------------------------------------------------------------------------
def era_law_split(fires_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split fires into verdict-grade (2021+) and survivor-biased cohorts.

    Returns
    -------
    verdict_grade : rows where fire_date >= MASSIVE_ERA_START AND verdict_grade==True
    survivor_biased : all other rows

    Columns checked (by fallback):
        fire_date or signal_date — the signal/fire date column
        verdict_grade             — boolean flag
    """
    date_col = "fire_date" if "fire_date" in fires_df.columns else "signal_date"
    has_vg = "verdict_grade" in fires_df.columns

    if date_col not in fires_df.columns:
        log.warning("era_law_split: no date column found; treating all as survivor-biased")
        return fires_df.iloc[0:0].copy(), fires_df.copy()

    fire_dates = pd.to_datetime(fires_df[date_col], errors="coerce")
    in_era = fire_dates >= MASSIVE_ERA_START

    if has_vg:
        vg_flag = fires_df["verdict_grade"].fillna(False).astype(bool)
        verdict_mask = in_era & vg_flag
    else:
        verdict_mask = in_era

    verdict_grade = fires_df[verdict_mask].copy()
    survivor_biased = fires_df[~verdict_mask].copy()
    return verdict_grade, survivor_biased


# ---------------------------------------------------------------------------
# Main replay function
# ---------------------------------------------------------------------------
def replay_spec(
    spec: RuleSpec,
    fires_df: pd.DataFrame,
    closes: dict[str, pd.Series],
    *,
    registry_hashes: set[str] | None = None,
) -> pd.DataFrame:
    """Replay a single RuleSpec over the fire tape.

    Parameters
    ----------
    spec           : RuleSpec (must be registered; hash checked if registry_hashes given)
    fires_df       : replay_boarded DataFrame (columns include ticker, fire_date, etc.)
    closes         : {ticker: split-adjusted close Series}; callers are responsible for
                     calling split_adjust() before passing (§3.2 contract)
    registry_hashes: if provided, the spec's content_hash must be in this set or
                     GovernorRefusal is raised (enforces anti-fishing governor law)

    Returns
    -------
    pd.DataFrame with one row per fire, columns:
        fire_idx, ticker, fire_date, exit_bar_offset, exit_ret,
        mae_to_exit, mfe_to_exit, holding_days, censored,
        foregone_mfe_{H}, avoided_mae_{H} for each H in spec.horizons_ref,
        survivorship_biased, era_cohort
    """
    if registry_hashes is not None:
        h = spec.content_hash()
        if h not in registry_hashes:
            raise GovernorRefusal(
                f"RuleSpec {spec.spec_id!r} (hash {h}) is not registered in the "
                "rule-experiment registry. Register it via scripts/register_rule_experiment.py "
                "before running any replay. No --adhoc mode exists (house-law violation)."
            )

    # Apply cohort filter
    mask = spec.cohort.apply(fires_df)
    cohort_df = fires_df[mask].reset_index(drop=True)
    log.debug("replay_spec %s: %d/%d fires match cohort", spec.spec_id, len(cohort_df), len(fires_df))

    # ERA LAW split
    vg_df, sb_df = era_law_split(cohort_df)

    records: list[dict[str, Any]] = []
    date_col = "fire_date" if "fire_date" in cohort_df.columns else "signal_date"
    ticker_col = "ticker" if "ticker" in cohort_df.columns else cohort_df.columns[0]

    for era_label, sub_df, surv_biased in [
        ("verdict_grade_2021plus", vg_df, False),
        ("survivor_biased", sb_df, True),
    ]:
        for _, row in sub_df.iterrows():
            ticker = str(row[ticker_col])
            signal_date = pd.Timestamp(row[date_col])
            close = closes.get(ticker)
            if close is None or len(close) == 0:
                records.append({
                    "fire_idx": row.name,
                    "ticker": ticker,
                    "fire_date": signal_date,
                    "exit_bar_offset": None,
                    "exit_ret": None,
                    "mae_to_exit": None,
                    "mfe_to_exit": None,
                    "holding_days": None,
                    "censored": True,
                    "survivorship_biased": surv_biased,
                    "era_cohort": era_label,
                    "_missing_close": True,
                })
                continue

            # Apply delay_n to get fill index
            base_fill = fill_index(close, signal_date)
            if base_fill is None:
                records.append({
                    "fire_idx": row.name,
                    "ticker": ticker,
                    "fire_date": signal_date,
                    "exit_bar_offset": None,
                    "exit_ret": None,
                    "mae_to_exit": None,
                    "mfe_to_exit": None,
                    "holding_days": None,
                    "censored": True,
                    "survivorship_biased": surv_biased,
                    "era_cohort": era_label,
                    "_missing_fill": True,
                })
                continue

            # delay_n: shift fill bar further forward (default delay_n=1 means the
            # standard next-bar fill already computed by fill_index;
            # delay_n=2 means one additional bar delay)
            actual_fill = base_fill + max(0, spec.delay_n - 1)
            if actual_fill >= len(close):
                records.append({
                    "fire_idx": row.name,
                    "ticker": ticker,
                    "fire_date": signal_date,
                    "exit_bar_offset": None,
                    "exit_ret": None,
                    "mae_to_exit": None,
                    "mfe_to_exit": None,
                    "holding_days": None,
                    "censored": True,
                    "survivorship_biased": surv_biased,
                    "era_cohort": era_label,
                })
                continue

            try:
                metrics = _compute_per_fire(close, actual_fill, spec.exit, spec.horizons_ref)
            except Exception as exc:
                log.warning("replay_spec: error on %s %s: %s", ticker, signal_date, exc)
                metrics = {
                    "exit_bar_offset": None,
                    "exit_ret": None,
                    "mae_to_exit": None,
                    "mfe_to_exit": None,
                    "holding_days": None,
                    "censored": True,
                }

            rec: dict[str, Any] = {
                "fire_idx": row.name,
                "ticker": ticker,
                "fire_date": signal_date,
                "survivorship_biased": surv_biased,
                "era_cohort": era_label,
            }
            rec.update(metrics)
            records.append(rec)

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Governor enforcement
# ---------------------------------------------------------------------------
class GovernorRefusal(RuntimeError):
    """Raised when a spec is not registered or its hash is mismatched."""


# ---------------------------------------------------------------------------
# Serialization guard — requires vintage stamp
# ---------------------------------------------------------------------------
def serialize_results(
    results_df: pd.DataFrame,
    spec: RuleSpec,
    vintage: dict,
    *,
    extra_meta: dict | None = None,
) -> dict[str, Any]:
    """Serialize replay results to a JSON-safe dict.

    Raises StampRefusal if ``vintage`` is not a valid vintage_stamp() dict.
    Raises GovernorRefusal if the spec has no content hash (defensive).

    Returns a dict suitable for json.dumps — per-fire stats are included as
    a list of dicts; callers may split off the per-fire data to parquet separately.
    """
    require_stamp(vintage)  # hard refusal if missing or incomplete

    n_fires = len(results_df)
    n_censored = int(results_df.get("censored", pd.Series(dtype=bool)).sum()) if n_fires > 0 else 0
    n_vg = int((results_df.get("era_cohort", pd.Series()) == "verdict_grade_2021plus").sum()) if n_fires > 0 else 0
    n_sb = int((results_df.get("era_cohort", pd.Series()) == "survivor_biased").sum()) if n_fires > 0 else 0

    out: dict[str, Any] = {
        "spec": spec.to_dict(),
        "vintage_stamp": vintage,
        "n_fires": n_fires,
        "n_censored": n_censored,
        "n_verdict_grade": n_vg,
        "n_survivor_biased": n_sb,
    }
    if extra_meta:
        out.update(extra_meta)

    # Per-fire records (all None-safe)
    def _safe(v: Any) -> Any:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, pd.Timestamp):
            return str(v.date())
        if isinstance(v, bool):
            return bool(v)
        return v

    if not results_df.empty:
        out["per_fire"] = [
            {k: _safe(v) for k, v in row.items()}
            for row in results_df.to_dict(orient="records")
        ]
    else:
        out["per_fire"] = []

    return out
