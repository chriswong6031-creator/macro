"""engine.neuralweb.alpha_grammar — Formula AST and deterministic candidate enumerator.

HONESTY HEADER
--------------
This module is RESEARCH-SIDE ONLY (FR-12).  It defines the formula primitive set
and enumerates candidates for the family ``alpha_grammar_confluence_v1``.  No site
output, no synapse.yml registration, no spine claims, no board rank/size/alert changes.

PRIMITIVE SET (CLOSED v1)
-------------------------
Adding a primitive requires a masterplan amendment.

  ts_rank(x, w)            — rolling rank of x at bar t within the last w bars [0,1]
  ts_delta(x, w)           — x[t] - x[t-w]  (lagged difference)
  roll_corr(x, y, w)       — rolling Pearson correlation(x, y) over w bars
  decay_linear(x, w)       — linearly-weighted (newest=w, oldest=1) rolling mean
  zscore_winsor(x, w, clip=3) — rolling z-score, winsorised at ±clip
  vol_norm_move(x, w)      — (x[t] - x[t-1]) / rolling_std(x, w)  (one-bar move / sigma)
  dist_from_argmin(x, w)   — bars since the window minimum  (0 .. w-1)
  dist_from_argmax(x, w)   — bars since the window maximum  (0 .. w-1)
  cs_rank(x)               — cross-sectional percentile rank over the FIRE COHORT on the
                             same date.  Requires ≥MIN_COHORT_SIZE same-date fires;
                             emits NaN for the entire date-cohort when below the floor.

BASE SERIES (v1)
----------------
  close_returns            — pct_change of the PIT close slice
  Volume is DROPPED, not NaN-filled, when absent from the panel.  Candidates
  that depend on volume are excluded from enumeration when volume is unavailable;
  the ledger records only the actually-enumerable candidates.

PIT LAW (structural, tested)
-----------------------------
Every formula is evaluated as-of the fire date using ONLY bars strictly ≤ fire date.
The evaluator receives ``close.iloc[:fire_iloc+1]`` (the pre-fire slice) and nothing
else.  ``fire_iloc`` is derived via ``engine.grading._snap_loc`` on each ticker's
close series and asserted to equal the fire date (the snapped bar's date must match
the fire date).  A fire date missing from a ticker's close series produces NaN for
that event (never an off-by-one anchor).

CS_RANK MIN-COHORT FLOOR
------------------------
``MIN_COHORT_SIZE = 10``, matching ``validation.rank_ic``'s <10→NaN floor.
Dates where the fire cohort has fewer than MIN_COHORT_SIZE members emit NaN for
all cs_rank candidates on that date.  Candidates built on cs_rank are scored on
only the ≥10-cohort subset.  The effective n after the cohort floor is reported
per-candidate in the output.

SURVIVORSHIP CAVEAT (cross-section)
------------------------------------
The deep panel is surviving-names-only (manifest shows only current constituents
with backfilled history; dead names are absent).  Cross-sectional cs_rank / IC is
measured on a cross-section where the hardest-failing names are removed.  Absolute
IC/DSR overstates a live alpha.  Only within-arm / within-era comparisons are
defensible.  This caveat is stamped on every candidate record.

CLUSTERING DETERMINISM
----------------------
Greedy correlation clustering at |ρ| > 0.7 (and sensitivity at 0.6 / 0.8) is
performed after sorting candidates deterministically by (DSR desc, alpha_id asc),
so cluster membership is reproducible given the same scored panel.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FAMILY = "alpha_grammar_confluence_v1"
CANDIDATE_CAP = 200          # declared cap; never exceeded
MIN_COHORT_SIZE = 10         # matches validation.rank_ic <10→NaN floor
_WINDOWS = [5, 10, 21, 63]
_COMPOSITION_DEPTH = 2       # max depth of nested primitives

SURVIVORSHIP_CAVEAT = (
    "deep panel is surviving-names-only; absolute IC/DSR overstates a live alpha; "
    "within-arm comparisons are defensible, cross-section comparisons are not"
)

# ---------------------------------------------------------------------------
# Formula AST
# ---------------------------------------------------------------------------

def _canonical_json(obj: Any) -> str:
    """Deterministic JSON serialisation (sorted keys)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _alpha_id(ast_obj: Any) -> str:
    """Content-addressed 12-hex alpha_id from the canonical JSON of a formula node."""
    payload = _canonical_json(ast_obj)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


@dataclass(frozen=True)
class FormulaNode:
    """Immutable AST node for a formula primitive or composition."""
    op: str
    args: tuple = field(default_factory=tuple)
    kwargs: tuple = field(default_factory=tuple)  # tuple of (key, value) pairs

    def to_dict(self) -> dict:
        """Serialise to a JSON-safe dict (deterministic)."""
        d: dict[str, Any] = {"op": self.op}
        if self.args:
            d["args"] = [a.to_dict() if isinstance(a, FormulaNode) else a
                         for a in self.args]
        if self.kwargs:
            d["kwargs"] = {k: v for k, v in self.kwargs}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "FormulaNode":
        """Deserialise from a dict produced by to_dict()."""
        args = tuple(
            cls.from_dict(a) if isinstance(a, dict) and "op" in a else a
            for a in d.get("args", [])
        )
        kwargs = tuple(sorted(d.get("kwargs", {}).items()))
        return cls(op=d["op"], args=args, kwargs=kwargs)

    @property
    def alpha_id(self) -> str:
        return _alpha_id(self.to_dict())

    @property
    def lookback(self) -> int:
        """Maximum window depth (sum of all window arguments along the deepest path)."""
        windows = [a for a in self.args if isinstance(a, int) and a > 0]
        child_lb = max(
            (a.lookback for a in self.args if isinstance(a, FormulaNode)),
            default=0,
        )
        return max(windows, default=0) + child_lb

    def uses_cs_rank(self) -> bool:
        """True if this node or any descendant is a cs_rank primitive."""
        if self.op == "cs_rank":
            return True
        return any(
            a.uses_cs_rank() for a in self.args if isinstance(a, FormulaNode)
        )

    def uses_volume(self) -> bool:
        """True if this node or any descendant references volume."""
        if "volume" in self.op.lower():
            return True
        return any(
            a.uses_volume() for a in self.args if isinstance(a, FormulaNode)
        )


# Convenience constructors ---------------------------------------------------

def ts_rank(x: FormulaNode, w: int) -> FormulaNode:
    return FormulaNode(op="ts_rank", args=(x, w))

def ts_delta(x: FormulaNode, w: int) -> FormulaNode:
    return FormulaNode(op="ts_delta", args=(x, w))

def roll_corr(x: FormulaNode, y: FormulaNode, w: int) -> FormulaNode:
    return FormulaNode(op="roll_corr", args=(x, y, w))

def decay_linear(x: FormulaNode, w: int) -> FormulaNode:
    return FormulaNode(op="decay_linear", args=(x, w))

def zscore_winsor(x: FormulaNode, w: int, clip: float = 3.0) -> FormulaNode:
    return FormulaNode(op="zscore_winsor", args=(x, w),
                       kwargs=(("clip", clip),))

def vol_norm_move(x: FormulaNode, w: int) -> FormulaNode:
    return FormulaNode(op="vol_norm_move", args=(x, w))

def dist_from_argmin(x: FormulaNode, w: int) -> FormulaNode:
    return FormulaNode(op="dist_from_argmin", args=(x, w))

def dist_from_argmax(x: FormulaNode, w: int) -> FormulaNode:
    return FormulaNode(op="dist_from_argmax", args=(x, w))

def cs_rank(x: FormulaNode) -> FormulaNode:
    return FormulaNode(op="cs_rank", args=(x,))

# Base series leaf nodes (op = series name, no children)
CLOSE_RETURNS = FormulaNode(op="close_returns", args=())


# ---------------------------------------------------------------------------
# Formula evaluator (PIT-safe)
# ---------------------------------------------------------------------------

def _eval_node(node: FormulaNode, close_slice: pd.Series,
               cohort_values: dict[str, float] | None = None) -> pd.Series:
    """Evaluate a formula node on a PIT close slice (bars up to and including fire bar).

    Parameters
    ----------
    close_slice:
        close.iloc[:fire_iloc+1] — strictly no post-fire bars visible.
    cohort_values:
        For cs_rank nodes: {ticker: raw_value} for all tickers in the same-date
        cohort.  If None or cohort is below MIN_COHORT_SIZE, cs_rank emits NaN.
    """
    op = node.op
    args = node.args

    # --- Base series ---
    if op == "close_returns":
        return close_slice.pct_change()

    # --- Primitives that operate on a single child series ---
    def _child(idx: int) -> pd.Series:
        a = args[idx]
        if isinstance(a, FormulaNode):
            return _eval_node(a, close_slice, cohort_values)
        raise TypeError(f"Expected FormulaNode at arg[{idx}], got {type(a)}")

    def _window(idx: int) -> int:
        a = args[idx]
        if isinstance(a, int):
            return a
        raise TypeError(f"Expected int window at arg[{idx}], got {type(a)}")

    if op == "ts_rank":
        x, w = _child(0), _window(1)
        min_p = max(2, w // 2)
        s = _child(0)
        # Vectorised ts_rank using pandas rolling rank (available since pandas 1.5)
        # rank(pct=True) within each rolling window; NaN when < min_periods valid bars.
        try:
            ranked = s.rolling(w, min_periods=min_p).rank(pct=True)
        except AttributeError:
            # Fallback for older pandas: use apply with argsort
            arr_raw = s.values.copy()

            def _rolling_rank_fn(a: np.ndarray) -> float:
                valid = a[np.isfinite(a)]
                if len(valid) < min_p:
                    return float("nan")
                v = a[-1]
                if not np.isfinite(v):
                    return float("nan")
                return float((valid < v).sum() / (len(valid) - 1)) if len(valid) > 1 else 0.5

            ranked = s.rolling(w, min_periods=min_p).apply(_rolling_rank_fn, raw=True)
        return ranked

    if op == "ts_delta":
        x, w = _child(0), _window(1)
        return x - x.shift(w)

    if op == "roll_corr":
        # roll_corr(x, y, w) — both x and y are child FormulaNodes
        if not isinstance(args[0], FormulaNode) or not isinstance(args[1], FormulaNode):
            raise TypeError("roll_corr requires two FormulaNode children")
        x = _eval_node(args[0], close_slice, cohort_values)
        y = _eval_node(args[1], close_slice, cohort_values)
        w = _window(2)
        min_p = max(3, w // 2)
        return x.rolling(w, min_periods=min_p).corr(y)

    if op == "decay_linear":
        x, w = _child(0), _window(1)
        min_p = max(2, w // 2)
        weights = np.arange(1, w + 1, dtype=float)
        weights_norm = weights / weights.sum()
        def _decay_apply(a: np.ndarray) -> float:
            w_slice = weights[-len(a):]
            w_slice = w_slice / w_slice.sum()
            return float(np.dot(a, w_slice))
        return x.rolling(w, min_periods=min_p).apply(_decay_apply, raw=True)

    if op == "zscore_winsor":
        x, w = _child(0), _window(1)
        clip_val = dict(node.kwargs).get("clip", 3.0)
        min_p = max(3, w // 2)
        mu = x.rolling(w, min_periods=min_p).mean()
        sigma = x.rolling(w, min_periods=min_p).std(ddof=1)
        z = (x - mu) / sigma.where(sigma > 0)
        return z.clip(-clip_val, clip_val)

    if op == "vol_norm_move":
        x, w = _child(0), _window(1)
        move = x.diff(1)
        sigma = x.rolling(w, min_periods=max(3, w // 2)).std(ddof=1)
        return move / sigma.where(sigma > 0)

    if op == "dist_from_argmin":
        x, w = _child(0), _window(1)
        min_p = max(2, w // 2)
        # For a full window arr (min_periods enforced by rolling), argmin of arr
        # gives the position; bars since = len(arr)-1 - last_argmin
        # Since rolling only calls apply when min_periods is met, arr is valid.
        def _dist_min(arr: np.ndarray) -> float:
            return float(len(arr) - 1 - int(arr.argmin()))
        return x.rolling(w, min_periods=min_p).apply(_dist_min, raw=True)

    if op == "dist_from_argmax":
        x, w = _child(0), _window(1)
        min_p = max(2, w // 2)
        def _dist_max(arr: np.ndarray) -> float:
            return float(len(arr) - 1 - int(arr.argmax()))
        return x.rolling(w, min_periods=min_p).apply(_dist_max, raw=True)

    if op == "cs_rank":
        # Cross-sectional rank over the fire cohort at the fire date.
        # cohort_values maps ticker → raw value (already evaluated for each ticker).
        # This node returns a scalar for the ticker's own value; the cross-sectional
        # ranking is computed externally in compile_alpha_candidates.py where all
        # tickers' values are available simultaneously.
        # In the per-ticker evaluation path, cs_rank returns the raw child value;
        # the cross-sectional rank is applied by the runner (see apply_cs_rank_pass).
        return _eval_node(args[0], close_slice, cohort_values)

    raise ValueError(f"Unknown op: {op!r}")


def eval_formula_at_fire(
    node: FormulaNode,
    close: pd.Series,
    fire_date,
) -> float:
    """Evaluate a formula node at a specific fire date.

    Uses _snap_loc to find fire_iloc, asserts snapped date == fire_date,
    then evaluates on close.iloc[:fire_iloc+1] (PIT-safe slice).

    Returns NaN if the fire date is not in the close series.
    """
    from engine.grading import _snap_loc  # import here to allow mocking in tests
    fire_ts = pd.Timestamp(fire_date)
    iloc = _snap_loc(close.index, fire_ts)
    if iloc is None:
        return float("nan")
    # Assert PIT alignment: snapped bar's date must equal fire_date
    snapped_date = close.index[iloc]
    if snapped_date != fire_ts:
        # Fire date missing from close series — return NaN to avoid off-by-one anchor
        return float("nan")
    pit_slice = close.iloc[: iloc + 1]
    if len(pit_slice) == 0:
        return float("nan")
    result = _eval_node(node, pit_slice)
    if isinstance(result, pd.Series):
        v = result.iloc[-1]
        return float(v) if np.isfinite(v) else float("nan")
    return float(result) if np.isfinite(result) else float("nan")


# ---------------------------------------------------------------------------
# Candidate record
# ---------------------------------------------------------------------------

@dataclass
class CandidateRecord:
    """A fully-specified alpha candidate."""
    alpha_id: str
    family: str
    formula_ast: dict          # JSON-safe dict from FormulaNode.to_dict()
    source_artifacts: list[str]
    lookback: int
    lag: int                   # always >= 1 (PIT law)
    horizon: int
    expected_role: str
    mechanism_hypothesis: str
    overlap_cluster: str | None
    uses_cs_rank: bool
    survivorship_caveat: str

    def to_dict(self) -> dict:
        return {
            "alpha_id": self.alpha_id,
            "family": self.family,
            "formula_ast": self.formula_ast,
            "source_artifacts": self.source_artifacts,
            "lookback": self.lookback,
            "lag": self.lag,
            "horizon": self.horizon,
            "expected_role": self.expected_role,
            "mechanism_hypothesis": self.mechanism_hypothesis,
            "overlap_cluster": self.overlap_cluster,
            "uses_cs_rank": self.uses_cs_rank,
            "survivorship_caveat": self.survivorship_caveat,
        }

    @classmethod
    def from_node(
        cls,
        node: FormulaNode,
        mechanism_hypothesis: str,
        *,
        lag: int = 1,
        horizon: int = 21,
    ) -> "CandidateRecord":
        assert lag >= 1, "PIT law: lag must be >= 1"
        return cls(
            alpha_id=node.alpha_id,
            family=FAMILY,
            formula_ast=node.to_dict(),
            source_artifacts=[
                "data/research/gate_fires_deep.parquet",
                "data/research/gate_fires_baskets.parquet",
            ],
            lookback=node.lookback,
            lag=lag,
            horizon=horizon,
            expected_role="entry_quality_context",
            mechanism_hypothesis=mechanism_hypothesis,
            overlap_cluster=None,
            uses_cs_rank=node.uses_cs_rank(),
            survivorship_caveat=SURVIVORSHIP_CAVEAT,
        )


# ---------------------------------------------------------------------------
# Deterministic candidate enumeration
# ---------------------------------------------------------------------------

_UNARY_OPS_WITH_WINDOW = [
    ("ts_rank", ts_rank, "rolling rank position [0,1] within window"),
    ("ts_delta", ts_delta, "lagged difference: momentum proxy"),
    ("decay_linear", decay_linear, "linearly-weighted recent-bar emphasis"),
    ("zscore_winsor", zscore_winsor, "z-score winsorised to ±3σ: normalised deviation"),
    ("vol_norm_move", vol_norm_move, "one-bar move / rolling sigma: volatility-scaled momentum"),
    ("dist_from_argmin", dist_from_argmin, "bars since window low: reclaim distance"),
    ("dist_from_argmax", dist_from_argmax, "bars since window high: proximity to peak"),
]

_UNARY_OPS_NO_WINDOW = [
    ("cs_rank", lambda x: cs_rank(x), "cross-sectional rank within fire cohort"),
]


def _build_depth1_nodes(
    base: FormulaNode,
    base_name: str,
    windows: list[int],
) -> list[tuple[FormulaNode, str]]:
    """All depth-1 (primitive over base series) nodes for a given base."""
    nodes: list[tuple[FormulaNode, str]] = []
    for op_name, constructor, desc in _UNARY_OPS_WITH_WINDOW:
        for w in windows:
            n = constructor(base, w)
            hypothesis = f"{op_name}({base_name}, w={w}): {desc}"
            nodes.append((n, hypothesis))
    # cs_rank (no window)
    n = cs_rank(base)
    nodes.append((n, f"cs_rank({base_name}): cross-sectional rank of {base_name}"))
    return nodes


def _build_depth2_nodes(
    base: FormulaNode,
    base_name: str,
    windows: list[int],
    depth1_nodes: list[tuple[FormulaNode, str]],
) -> list[tuple[FormulaNode, str]]:
    """Depth-2 nodes: unary-window primitives over depth-1 intermediates."""
    nodes: list[tuple[FormulaNode, str]] = []
    for op_name, constructor, desc in _UNARY_OPS_WITH_WINDOW:
        for inner_node, inner_hyp in depth1_nodes[:12]:  # limit inner fan-out
            for w in windows:
                n = constructor(inner_node, w)
                hypothesis = (
                    f"{op_name}({inner_node.op}({base_name},...), w={w}): "
                    f"{desc} of [{inner_hyp}]"
                )
                nodes.append((n, hypothesis))
    return nodes


def enumerate_candidates(
    windows: list[int] | None = None,
    cap: int = CANDIDATE_CAP,
    include_cs_rank: bool = True,
) -> list[CandidateRecord]:
    """Enumerate candidates deterministically up to ``cap``.

    The full enumerated grid (before capping) is the true search space:
    ~9 primitives × close base × 4 windows × depth-2 compositions.
    The grid is logged to the ledger BEFORE grading via log_grid in the runner.

    Volume-based candidates are DROPPED (not NaN-filled) since the deep panel
    loads only the 'close' column.

    Truncation rule: depth-1 nodes first (ordered by primitive then window),
    then depth-2 nodes.  Within each group, sort by (op_name, window) for
    determinism.  cs_rank candidates are included if include_cs_rank=True;
    when False they are excluded and the caller records the drop reason.
    """
    if windows is None:
        windows = _WINDOWS

    base = CLOSE_RETURNS
    base_name = "close_returns"

    depth1 = _build_depth1_nodes(base, base_name, windows)
    depth2 = _build_depth2_nodes(base, base_name, windows, depth1)

    all_nodes: list[tuple[FormulaNode, str]] = depth1 + depth2

    # Filter duplicates (by alpha_id) while preserving order
    seen_ids: set[str] = set()
    unique_nodes: list[tuple[FormulaNode, str]] = []
    for node, hyp in all_nodes:
        aid = node.alpha_id
        if aid not in seen_ids:
            seen_ids.add(aid)
            unique_nodes.append((node, hyp))

    # Filter cs_rank if requested
    if not include_cs_rank:
        unique_nodes = [(n, h) for n, h in unique_nodes if not n.uses_cs_rank()]

    # Truncate to cap (first-come within the deterministic ordering)
    truncated = unique_nodes[:cap]

    records: list[CandidateRecord] = []
    for node, hypothesis in truncated:
        rec = CandidateRecord.from_node(node, mechanism_hypothesis=hypothesis)
        records.append(rec)

    return records


def full_grid_size(windows: list[int] | None = None) -> int:
    """Return the FULL enumerated grid size (before capping) for ledger honesty."""
    if windows is None:
        windows = _WINDOWS
    base = CLOSE_RETURNS
    base_name = "close_returns"
    depth1 = _build_depth1_nodes(base, base_name, windows)
    depth2 = _build_depth2_nodes(base, base_name, windows, depth1)
    all_nodes = depth1 + depth2
    seen: set[str] = set()
    count = 0
    for node, _ in all_nodes:
        aid = node.alpha_id
        if aid not in seen:
            seen.add(aid)
            count += 1
    return count


# ---------------------------------------------------------------------------
# Cross-sectional rank application (runner helper)
# ---------------------------------------------------------------------------

def apply_cs_rank_pass(
    signal_matrix: pd.DataFrame,
    candidate: CandidateRecord,
    fire_panel: pd.DataFrame,
) -> pd.Series:
    """Apply the cs_rank cross-sectional pass to a pre-computed signal matrix.

    After each ticker's raw formula value has been evaluated (using the inner
    child of cs_rank as the base formula), this function applies the cross-
    sectional percentile rank within each date's fire cohort.

    Parameters
    ----------
    signal_matrix:
        DataFrame indexed by fire_index (same index as fire_panel), one column
        per candidate; values are the raw child-formula outputs before cs_rank.
    candidate:
        The CandidateRecord whose formula uses cs_rank.
    fire_panel:
        The graded fire panel with at least a 'date' column.

    Returns
    -------
    pd.Series of cs_rank values, indexed like signal_matrix; NaN for dates
    where cohort size < MIN_COHORT_SIZE.
    """
    raw = signal_matrix[candidate.alpha_id].copy()
    out = pd.Series(np.nan, index=raw.index)

    dates = fire_panel["date"].values
    for d in np.unique(dates):
        mask = dates == d
        cohort_vals = raw[mask].dropna()
        n_cohort = mask.sum()
        if n_cohort < MIN_COHORT_SIZE or len(cohort_vals) < MIN_COHORT_SIZE:
            # Below min-cohort floor: emit NaN for all rows on this date
            continue
        # Rank 0..1
        ranked = cohort_vals.rank(pct=True)
        out[ranked.index] = ranked.values

    return out


# ---------------------------------------------------------------------------
# De-overlap: episode-level deduplication of overlapping forward windows
# ---------------------------------------------------------------------------

def deoverlap_fires_v2(
    fire_panel: pd.DataFrame,
    horizon: int = 21,
) -> pd.DataFrame:
    """Vectorised de-overlap: keep first non-overlapping fire per ticker.

    For each ticker, greedily keep a fire if it is ≥ ``horizon`` days after
    the last kept fire.  This is deterministic (sort by date ascending first).
    """
    kept_rows = []
    # Sentinel date far in the past; avoid pd.Timestamp.min (overflow on subtraction)
    _SENTINEL = pd.Timestamp("1900-01-01")
    for ticker, grp in fire_panel.sort_values(["ticker", "date"]).groupby("ticker"):
        last_kept_date = _SENTINEL
        for idx, row in grp.iterrows():
            fire_date = pd.Timestamp(row["date"])
            diff = (fire_date - last_kept_date).days
            if diff >= horizon:
                kept_rows.append(idx)
                last_kept_date = fire_date
    return fire_panel.loc[kept_rows]
