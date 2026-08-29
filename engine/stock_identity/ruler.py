"""Stock Identity W3A — the episode localization ruler (freeze §4.1, plan Tasks 1-3).

Expert-independent, path-anchored measurement over the W1 episode catalog and W2
expert events/attribution. **This module never opens Q1, never ranks an expert
against another on a name's own outcomes, and never writes a best/rank/route
column anywhere** (``DNR:KILL-OUTCOME-AUDITION``) — that guard is test-enforced
both on this module's own source (no ranking vocabulary as an identifier) and on
every DataFrame it returns.

Two layers of measurement
--------------------------
1. **Per-fire metrics** (:func:`compute_fire_metrics`) — one row per attributed
   ``(event, episode)`` hit: ``lead_lag``, ``price_dist``, ``atr_dist``,
   ``mae_after``, ``capture``, ``false_start``. A censored episode has no anchor,
   so its fires carry ``NaN`` anchor metrics (LER convention, masterplan §9.5) —
   they are never dropped, because dropping them would turn every downstream
   recall figure into a survivorship filter.
2. **Cell aggregates** (:func:`aggregate_cell_metrics`) — per ``(family_key,
   episode_type, grain)`` cell: ``false_start_rate``, ``flooding``,
   ``recall_at_tier``, ``zone_precision``, ``relative_order``, ``consistency``.

The unconditional block (:func:`compute_unconditional_block`) is the other half
of "no fit claim exists without attribution rate" (freeze §4.1): fires/name/year
and episode-attribution-rate, counted over EVERY event — attributed or not.

The two graded composites
--------------------------
``C-LOC-R = recall_at_tier * zone_precision - lambda_fs * false_start_rate``

``C-LOC-D = rank-normalized median ATR distance to anchor of in-zone fires``,
gated by the recall floor and penalized by ``false_start_rate`` at the same
``lambda_fs``.

``lambda_fs``/``recall_floor`` are the PR-3 constant family: they do not exist
before Task 3C's one-time sealed-calibration constant-setting act runs against
``SI-SEALED-CAL-P1``. Until then the shipped ``ruler_spec_v1.json`` carries the
explicit sentinel ``{"status": "pending_sealed_calibration"}`` and
:func:`compute_composites` REFUSES to run — it never substitutes a guessed or
fixture value for a production read. Tasks 2-3 test the metric/composite MATH by
constructing a :class:`RulerSpec` directly in test code with clearly-labeled
FIXTURE-ONLY constants; those constants are chosen for arithmetic legibility and
carry no prior on the value Task 3C later computes, and they are never
serialized to the shipped spec file.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "PR3_PENDING_SENTINEL",
    "FIRE_METRIC_COLUMNS",
    "UNCONDITIONAL_BLOCK_COLUMNS",
    "CELL_METRIC_COLUMNS",
    "FORBIDDEN_OUTPUT_TOKENS",
    "GRAIN_CLASSES",
    "SUPPORT_COVERAGE_COLUMNS",
    "AVAILABILITY_TAXONOMY_TOKENS",
    "FAMILY_EPISODE_AVAILABILITY_COLUMNS",
    "FAMILY_ELIGIBLE_STATE",
    "PendingSealedCalibrationError",
    "MissingRankStratumColumnsError",
    "UnconditionalBlockUniverseError",
    "RulerSpec",
    "grain_class",
    "episode_identifier",
    "validate_ruler_inputs",
    "compute_fire_metrics",
    "compute_unconditional_block",
    "build_family_episode_availability",
    "aggregate_cell_metrics",
    "compute_composites",
    "build_support_coverage",
]

#: The explicit sentinel status a shipped spec carries before Task 3C runs.
PR3_PENDING_SENTINEL = "pending_sealed_calibration"

#: Cadence classes the grain-cadence null groups by (freeze §4.2 "grain is always
#: stratified"). Any observed W2 ``grain`` string classifies into exactly one.
GRAIN_CLASSES: tuple[str, ...] = ("daily", "weekly")

#: Ranking/outcome-audition vocabulary that may never appear as a column name or as
#: an identifier in this module's own source (``DNR:KILL-OUTCOME-AUDITION``).
FORBIDDEN_OUTPUT_TOKENS: tuple[str, ...] = (
    "best_expert", "expert_rank", "winner", "route", "prophet_score",
)

#: Closed per-fire metric column names (plan Task 1 interface). ``mae_basis``
#: records whether the strictly-forward adverse-excursion window used ``low``
#: (long-side convention) or fell back to ``close`` (freeze review finding M6).
FIRE_METRIC_COLUMNS: tuple[str, ...] = (
    "event_id", "family_key", "symbol", "episode_id", "episode_type",
    "episode_tier", "grain", "signal_known_ts",
    "lead_lag", "price_dist", "atr_dist", "mae_after", "mae_basis", "capture",
    "false_start",
)

#: Closed unconditional-block column names (plan Task 1 interface). ``no_coverage``
#: flags an explicit zero-total (family, symbol) row emitted for every member of
#: the roster/family universe with no events at all (freeze review finding M10) —
#: distinct from a real, measured zero-fire outcome.
UNCONDITIONAL_BLOCK_COLUMNS: tuple[str, ...] = (
    "family_key", "symbol", "total_fires", "attributed_fires",
    "fires_per_name_year", "episode_attribution_rate", "no_coverage",
)

#: The closed availability-state taxonomy (freeze §7 "Failure / correction
#: semantics"). ``build_support_coverage`` draws every absence/coverage-problem
#: value in its ``availability_state`` column from exactly this set; ``"resolved"``
#: is the one non-problem state (a fire genuinely attributed to a resolved,
#: non-censored episode) and is deliberately NOT drawn from this taxonomy, since
#: the taxonomy enumerates failure/absence semantics, not successful outcomes.
AVAILABILITY_TAXONOMY_TOKENS: tuple[str, ...] = (
    "MEASURED_ZERO", "STRUCTURAL_ABSENCE", "NO_COVERAGE", "NOT_YET_AVAILABLE",
    "STALE", "SOURCE_FAILED", "IDENTITY_UNRESOLVED", "UNESTIMABLE",
    "EPOCH_UNSTABLE", "CENSORED", "ABSTAIN",
)

#: Closed cell-aggregate column names — the "aggregations" owned by
#: ``compute_fire_metrics`` per the plan's Global Constraints closed-column list.
CELL_METRIC_COLUMNS: tuple[str, ...] = (
    "family_key", "episode_type", "grain", "n_fires", "n_episodes",
    "false_start_rate", "flooding", "recall_at_tier", "zone_precision",
    "relative_order", "consistency", "atr_dist_median_in_zone",
)

#: The one non-problem eligibility state (Ruling 2, SI-W3A-RULER-V1 PR-3 seal
#: law) -- deliberately NOT drawn from :data:`AVAILABILITY_TAXONOMY_TOKENS`,
#: symmetric with ``build_support_coverage``'s ``"resolved"`` (that constant's
#: docstring: the taxonomy enumerates failure/absence semantics only).
FAMILY_ELIGIBLE_STATE = "ELIGIBLE"

#: Row shape of :func:`build_family_episode_availability` — one row per
#: ``(family_key, tier-eligible episode)`` pair, outcome-independent (never
#: reads fires/events), carrying a typed ``availability_state`` drawn from
#: :data:`FAMILY_ELIGIBLE_STATE` or the closed
#: :data:`AVAILABILITY_TAXONOMY_TOKENS` exclusion set.
FAMILY_EPISODE_AVAILABILITY_COLUMNS: tuple[str, ...] = (
    "family_key", "episode_type", "symbol", "episode_id", "availability_state",
)

_REQUIRED_EVENT_COLUMNS: tuple[str, ...] = (
    "event_id", "family_key", "symbol", "signal_known_ts", "grain",
)
_REQUIRED_ATTRIBUTION_COLUMNS: tuple[str, ...] = (
    "event_id", "family_key", "symbol", "signal_known_ts", "episode_index",
    "episode_type", "episode_tier", "episode_start_date", "episode_end_date",
    "episode_resolution", "episode_censored", "attributed",
)
_REQUIRED_EPISODE_COLUMNS: tuple[str, ...] = (
    "symbol", "episode_type", "tier", "start_date", "anchor_date", "end_date",
    "resolution", "censored", "reference_price", "anchor_price", "a0_anchor", "a0_leg",
)

#: The typed outcome-independent support/coverage frame Task 2 emits for W3B — the
#: ONLY ruler-side artifact Task 4's census may consume (plan Task 2 Step 7 / Task 4
#: Interfaces). Deliberately carries NO realized metric or composite column.
SUPPORT_COVERAGE_COLUMNS: tuple[str, ...] = (
    "episode_id", "event_id", "ticker", "known_ts", "calendar_block",
    "calendar_block_basis", "family", "grain", "attributed", "price_coverage",
    "feature_coverage", "price_plane_id", "availability_state",
)


class PendingSealedCalibrationError(RuntimeError):
    """Raised when a composite/constant read is attempted while the PR-3 ruler
    constants still carry the ``pending_sealed_calibration`` sentinel."""


class MissingRankStratumColumnsError(RuntimeError):
    """Raised by :func:`compute_composites` when ``spec.c_loc_d_rank_population``
    requires stratum columns (``episode_type``/``grain``) that the cell-metrics
    frame does not carry (M5-residual). The prior implementation silently fell
    back to a GLOBAL rank across the whole cell population in this case, which
    lets a cell's ``c_loc_d`` move whenever cells from an unrelated stratum are
    added or removed — exactly the invariant the stratified rank exists to
    guarantee. This function never substitutes that weaker computation; it
    refuses instead."""


class UnconditionalBlockUniverseError(ValueError):
    """Raised by :func:`compute_unconditional_block` when the caller-supplied
    ``universe`` omits an observed ``(family_key, symbol)`` pair (M10-minor).
    The prior implementation's ``universe_df.merge(total, how="left")`` silently
    DROPPED any such pair from the output — an incomplete universe declaration
    must surface as an error, never a quiet omission."""


# ---------------------------------------------------------------------------
# RulerSpec
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RulerSpec:
    """Immutable, hashable ruler spec — receipted constants only (plan Task 1 Step 3).

    Two families of fields:

    * **Previously-frozen W1 geometry** (``atr_basis``, ``p_pre_sessions``,
      ``useful_zone_window_sessions``, ``useful_zone_delta_atr``,
      ``false_start_atr_threshold``, ``episode_type_anchor``, ``grain_classes``) —
      sourced from ``si_constants_v1.json`` / ``episodes.py`` and never re-derived
      here.
    * **A non-PR-3 structural field** (``c_loc_d_rank_population``) — frozen
      alongside the geometry above (M5-residual), never part of the pending PR-3
      constant family. Read by :func:`compute_composites` to decide the stratum
      C-LOC-D's rank normalization is computed WITHIN; the only currently-defined
      value is ``"episode_type_x_grain"``. Because it is carried in
      :meth:`to_canonical_dict`, it is covered by :meth:`spec_hash` — changing it
      changes the spec hash, exactly like any other frozen structural field.
    * **The PR-3 ruler-composite constant family** (``recall_floor``,
      ``lambda_fs``) — ``None`` with ``pr3_status == PR3_PENDING_SENTINEL`` until
      Task 3C's one-time sealed-calibration act sets them exactly once.
    """

    schema: str
    version: str
    atr_basis: str
    p_pre_sessions: int
    useful_zone_window_sessions: int
    useful_zone_delta_atr: float
    false_start_atr_threshold: float
    episode_type_anchor: Mapping[str, str]
    grain_classes: tuple[str, ...]
    graded_composites: tuple[str, ...]
    c_loc_d_rank_population: str
    recall_floor: float | None
    lambda_fs: float | None
    pr3_status: str
    pr3_receipt: Mapping[str, Any] | None
    authority: Mapping[str, bool]

    @property
    def pr3_pending(self) -> bool:
        return self.pr3_status == PR3_PENDING_SENTINEL

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "version": self.version,
            "atr_basis": self.atr_basis,
            "p_pre_sessions": self.p_pre_sessions,
            "useful_zone_window_sessions": self.useful_zone_window_sessions,
            "useful_zone_delta_atr": self.useful_zone_delta_atr,
            "false_start_atr_threshold": self.false_start_atr_threshold,
            "episode_type_anchor": dict(self.episode_type_anchor),
            "grain_classes": list(self.grain_classes),
            "graded_composites": list(self.graded_composites),
            "c_loc_d_rank_population": self.c_loc_d_rank_population,
            "recall_floor": self.recall_floor,
            "lambda_fs": self.lambda_fs,
            "pr3_status": self.pr3_status,
            "pr3_receipt": dict(self.pr3_receipt) if self.pr3_receipt else None,
            "authority": dict(self.authority),
        }

    def spec_hash(self) -> str:
        payload = json.dumps(
            self.to_canonical_dict(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def from_json(cls, path: str | Path) -> "RulerSpec":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        pr3 = payload.get("pr3") or {}
        geometry = payload.get("geometry") or {}
        return cls(
            schema=payload["schema"],
            version=payload["version"],
            atr_basis=geometry["atr_basis"],
            p_pre_sessions=int(geometry["p_pre_sessions"]),
            useful_zone_window_sessions=int(geometry["useful_zone_window_sessions"]),
            useful_zone_delta_atr=float(geometry["useful_zone_delta_atr"]),
            false_start_atr_threshold=float(geometry["false_start_atr_threshold"]),
            episode_type_anchor=dict(geometry["episode_type_anchor"]),
            grain_classes=tuple(geometry["grain_classes"]),
            graded_composites=tuple(payload["graded_composites"]),
            c_loc_d_rank_population=payload["c_loc_d_rank_population"],
            recall_floor=pr3.get("recall_floor"),
            lambda_fs=pr3.get("lambda_fs"),
            pr3_status=pr3["status"],
            pr3_receipt=pr3.get("receipt"),
            authority=dict(payload["authority"]),
        )


def grain_class(grain: Any) -> str:
    """Classify an observed W2 ``grain`` string into exactly one cadence class.

    ``"W"`` and anything ending in ``"W"`` (e.g. ``"2W"``) is weekly cadence;
    everything else (``"1D"``, ``"3D"``, ``"1D-state-over-2D/3D-buckets"``, ...)
    is daily cadence. Frozen mechanical rule, not a per-family lookup table, so a
    new W2 family never needs this module edited.
    """
    g = str(grain or "").strip().upper()
    if g == "W" or g.endswith("W"):
        return "weekly"
    return "daily"


def validate_ruler_inputs(
    events: pd.DataFrame, attribution: pd.DataFrame, episodes: pd.DataFrame
) -> None:
    """Raise ``ValueError`` if any input is missing a required column.

    Fail-closed at the boundary: a silently-absent column would show up
    downstream as a coverage null rather than the schema defect it is.
    """
    for name, df, required in (
        ("events", events, _REQUIRED_EVENT_COLUMNS),
        ("attribution", attribution, _REQUIRED_ATTRIBUTION_COLUMNS),
        ("episodes", episodes, _REQUIRED_EPISODE_COLUMNS),
    ):
        if df is None:
            raise ValueError(f"{name}: input is None")
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"{name}: missing required column(s) {missing}")


# ---------------------------------------------------------------------------
# episode id + lookup
# ---------------------------------------------------------------------------
def episode_identifier(symbol: Any, episode_type: Any, start_date: Any) -> str:
    """Deterministic episode id: the catalog carries none, so downstream joins
    (support frame, census) mint one identically here and nowhere else."""
    ts = pd.Timestamp(start_date)
    return f"{str(symbol).upper()}::{episode_type}::{ts.date().isoformat()}"


#: Internal alias kept for brevity inside this module.
_episode_id = episode_identifier


def _episode_lookup(episodes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if episodes is None or episodes.empty:
        return {}
    return {
        str(s): sub.reset_index(drop=True) for s, sub in episodes.groupby("symbol")
    }


def _empty_fire_metrics() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in FIRE_METRIC_COLUMNS})


def _empty_unconditional_block() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in UNCONDITIONAL_BLOCK_COLUMNS})


def _asof_close(bars: pd.DataFrame, ts: pd.Timestamp) -> float | None:
    idx = bars.index
    pos = idx.searchsorted(ts, side="right") - 1
    if pos < 0:
        return None
    return float(bars["close"].iloc[pos])


def _session_pos(idx: pd.DatetimeIndex, ts: pd.Timestamp) -> int:
    pos = idx.searchsorted(ts, side="left")
    return int(min(pos, len(idx) - 1)) if len(idx) else 0


# ---------------------------------------------------------------------------
# Task 2: per-fire metrics
# ---------------------------------------------------------------------------
def compute_fire_metrics(
    events: pd.DataFrame,
    attribution: pd.DataFrame,
    episodes: pd.DataFrame,
    bars_by_symbol: Mapping[str, pd.DataFrame],
    spec: RulerSpec,
) -> pd.DataFrame:
    """One measurement row per attributed ``(event, episode)`` hit.

    Episode anchor selection is a pure mapping from episode type (already fixed
    by ``engine.stock_identity.episodes`` — this function never re-derives it).
    No ranking step exists: a symbol/episode with several attributed events
    yields several rows, never a single "best" pick. Censored episodes carry
    ``NaN`` for every anchor-relative metric (no anchor exists yet), but their
    fires still appear here — the unconditional block downstream needs them.
    """
    validate_ruler_inputs(events, attribution, episodes)
    if attribution is None or attribution.empty:
        return _empty_fire_metrics()

    ev_grain: dict[Any, Any] = {}
    if events is not None and not events.empty:
        ev_grain = dict(zip(events["event_id"], events["grain"]))

    eps_lookup = _episode_lookup(episodes)
    rows: list[dict[str, Any]] = []

    attributed = attribution[attribution["attributed"] == True]  # noqa: E712
    for r in attributed.itertuples(index=False):
        symbol = str(r.symbol)
        eps = eps_lookup.get(symbol)
        if eps is None or r.episode_index is None:
            continue
        idx = int(r.episode_index)
        if idx < 0 or idx >= len(eps):
            continue
        erow = eps.iloc[idx]
        known_ts = pd.Timestamp(r.signal_known_ts)
        eid = _episode_id(symbol, erow["episode_type"], erow["start_date"])
        grain = ev_grain.get(r.event_id)

        censored = bool(erow.get("censored"))
        anchor_date = erow.get("anchor_date")
        anchor_price = erow.get("anchor_price")
        a0_anchor = erow.get("a0_anchor")
        reference_price = erow.get("reference_price")

        lead_lag = np.nan
        price_dist = np.nan
        atr_dist = np.nan
        mae_after = np.nan
        mae_basis: str | None = None
        capture = np.nan
        false_start: bool | None = None

        has_anchor = (
            not censored
            and anchor_date is not None
            and pd.notna(anchor_date)
            and anchor_price is not None
            and pd.notna(anchor_price)
        )
        if has_anchor:
            bars = bars_by_symbol.get(symbol) if bars_by_symbol else None
            anchor_ts = pd.Timestamp(anchor_date)
            if bars is not None and not bars.empty and "close" in bars.columns:
                bidx = bars.index
                lead_lag = float(_session_pos(bidx, known_ts) - _session_pos(bidx, anchor_ts))
                price_at_fire = _asof_close(bars, known_ts)
                if price_at_fire is not None:
                    price_dist = float(price_at_fire - float(anchor_price))
                    a0_ok = a0_anchor is not None and pd.notna(a0_anchor) and float(a0_anchor) > 0
                    if a0_ok:
                        atr_dist = float(price_dist / float(a0_anchor))
                        false_start = bool(abs(atr_dist) > spec.false_start_atr_threshold)
                    if reference_price is not None and pd.notna(reference_price):
                        denom = float(reference_price) - float(anchor_price)
                        if denom != 0:
                            capture = float((float(reference_price) - price_at_fire) / denom)
                    if a0_ok:
                        # Strictly-forward-from-fire window (freeze review finding M6):
                        # (known_ts, known_ts + useful_zone_window_sessions] in trading
                        # sessions of THIS symbol's own bars — never a pre-fire bar, and
                        # never anchored off anchor_ts (a lagging fire's anchor can sit
                        # BEFORE known_ts, which previously leaked pre-fire bars in).
                        pos_known = _session_pos(bidx, known_ts)
                        start_pos = pos_known + 1
                        end_pos = min(start_pos + spec.useful_zone_window_sessions, len(bidx))
                        if start_pos < len(bidx) and start_pos < end_pos:
                            fwd = bars.iloc[start_pos:end_pos]
                            if "low" in fwd.columns and fwd["low"].notna().any():
                                worst = float(fwd["low"].min())
                                mae_basis = "low"
                            else:
                                worst = float(fwd["close"].min())
                                mae_basis = "close"
                            mae_after = float(max(0.0, (price_at_fire - worst) / float(a0_anchor)))

        rows.append({
            "event_id": r.event_id,
            "family_key": r.family_key,
            "symbol": symbol,
            "episode_id": eid,
            "episode_type": erow["episode_type"],
            "episode_tier": int(erow["tier"]) if pd.notna(erow["tier"]) else None,
            "grain": grain,
            "signal_known_ts": known_ts,
            "lead_lag": lead_lag,
            "price_dist": price_dist,
            "atr_dist": atr_dist,
            "mae_after": mae_after,
            "mae_basis": mae_basis,
            "capture": capture,
            "false_start": false_start,
        })

    if not rows:
        return _empty_fire_metrics()
    out = pd.DataFrame(rows)
    return out[list(FIRE_METRIC_COLUMNS)].reset_index(drop=True)


# ---------------------------------------------------------------------------
# unconditional block
# ---------------------------------------------------------------------------
def _symbol_span_years(episode_rows: pd.DataFrame) -> dict[str, float]:
    if episode_rows is None or episode_rows.empty or "start_date" not in episode_rows.columns:
        return {}
    out: dict[str, float] = {}
    for sym, sub in episode_rows.groupby("symbol"):
        starts = pd.to_datetime(sub["start_date"])
        ends_col = sub["end_date"] if "end_date" in sub.columns else sub["start_date"]
        ends = pd.to_datetime(ends_col)
        ends = ends.fillna(starts)
        if starts.empty:
            continue
        span_days = (ends.max() - starts.min()).days
        out[str(sym)] = max(span_days, 1) / 365.25
    return out


def compute_unconditional_block(
    events: pd.DataFrame,
    attribution: pd.DataFrame,
    episode_rows: pd.DataFrame,
    universe: Sequence[tuple[Any, Any]] | None = None,
) -> pd.DataFrame:
    """Every expert/ticker row: total fires, attributed fires, fires/name/year and
    ``episode_attribution_rate`` — preserving zero-total as explicit no-coverage
    (``NaN`` rate, ``no_coverage=True``) rather than division to zero or a silently
    absent row (plan Task 2 Step 4; freeze review finding M10).

    ``universe`` is the full roster/family universe to report over — every
    ``(family_key, symbol)`` pair the caller expects coverage for (families from
    the W2 family registry; symbols from the caller's cohort). A pair present in
    ``universe`` but absent from ``events`` gets an explicit
    ``total_fires=0, fires_per_name_year=0.0, episode_attribution_rate=NaN,
    no_coverage=True`` row instead of being silently omitted. When ``universe`` is
    ``None`` the function falls back to reporting only pairs observed in ``events``
    (legacy behavior, still with ``no_coverage=False`` on every emitted row). The
    reverse direction (M10-minor) is also enforced: an observed
    ``(family_key, symbol)`` pair present in ``events`` but absent from a
    caller-supplied ``universe`` raises :class:`UnconditionalBlockUniverseError`
    rather than being silently dropped from the output.
    """
    required = ("event_id", "family_key", "symbol")
    if events is None:
        raise ValueError("events: input is None")
    missing = [c for c in required if c not in events.columns]
    if missing:
        raise ValueError(f"events: missing required column(s) {missing}")

    if events.empty:
        total = pd.DataFrame(columns=["family_key", "symbol", "total_fires"])
    else:
        total = (
            events.groupby(["family_key", "symbol"], as_index=False)["event_id"]
            .nunique()
            .rename(columns={"event_id": "total_fires"})
        )

    if attribution is not None and not attribution.empty:
        per_event = attribution.groupby(
            ["family_key", "symbol", "event_id"], as_index=False
        )["attributed"].max()
        attributed = (
            per_event.groupby(["family_key", "symbol"], as_index=False)["attributed"]
            .sum()
            .rename(columns={"attributed": "attributed_fires"})
        )
    else:
        attributed = pd.DataFrame(columns=["family_key", "symbol", "attributed_fires"])

    if universe is not None:
        universe_df = pd.DataFrame(list(universe), columns=["family_key", "symbol"]).drop_duplicates()
        # M10-minor: a `universe_df.merge(total, how="left")` keys off universe_df,
        # so any observed (family_key, symbol) pair in `total` that the caller's
        # universe omits is silently DROPPED from the output rather than surfaced —
        # refuse before merging instead.
        if not total.empty:
            observed_pairs = set(
                map(tuple, total[["family_key", "symbol"]].itertuples(index=False, name=None))
            )
            universe_pairs = set(
                map(tuple, universe_df.itertuples(index=False, name=None))
            )
            missing = observed_pairs - universe_pairs
            if missing:
                preview = sorted(missing)[:10]
                raise UnconditionalBlockUniverseError(
                    f"{len(missing)} observed (family_key, symbol) pair(s) are absent "
                    f"from the supplied universe and would be silently dropped: "
                    f"{preview}{'...' if len(missing) > 10 else ''} — the caller's "
                    "universe declaration is incomplete"
                )
        out = universe_df.merge(total, on=["family_key", "symbol"], how="left")
    else:
        out = total.copy()

    if out.empty:
        return _empty_unconditional_block()

    out = out.merge(attributed, on=["family_key", "symbol"], how="left")
    out["no_coverage"] = out["total_fires"].isna()
    out["attributed_fires"] = out["attributed_fires"].fillna(0).astype(int)
    out["total_fires"] = out["total_fires"].fillna(0).astype(int)

    span_years = _symbol_span_years(episode_rows)
    out["fires_per_name_year"] = out.apply(
        lambda r: (
            0.0 if r["no_coverage"] else (
                r["total_fires"] / span_years[r["symbol"]]
                if span_years.get(r["symbol"]) else np.nan
            )
        ),
        axis=1,
    )
    out["episode_attribution_rate"] = out.apply(
        lambda r: (r["attributed_fires"] / r["total_fires"]) if r["total_fires"] > 0 else np.nan,
        axis=1,
    )
    return out[list(UNCONDITIONAL_BLOCK_COLUMNS)].sort_values(
        ["family_key", "symbol"]
    ).reset_index(drop=True)


def _family_registry_index(
    family_registry: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Mapping[str, Any]]:
    """Normalize either the raw ``family_registry.json``'s ``families`` list or an
    already-keyed ``{family_key: entry}`` mapping. ``None`` yields an empty index
    (every family then reads as registry-absent -- Ruling 2 (c): never a silent
    fired-on fallback)."""
    if family_registry is None:
        return {}
    if isinstance(family_registry, Mapping):
        return dict(family_registry)
    return {str(entry["family_key"]): entry for entry in family_registry if "family_key" in entry}


def _family_first_available_bound(entry: Mapping[str, Any] | None) -> tuple[pd.Timestamp | None, bool]:
    """``(bound, field_present)``. ``field_present=False`` means the registry
    entry does not carry a ``family_first_available`` key AT ALL (Ruling 2
    design note: a genuinely-missing provenance field types the family
    unestimable, never a guessed value). A PRESENT field whose value is
    ``None``/falsy means "no known start boundary" -- the SAME convention
    already used throughout ``data/stock_identity/expert_events/
    family_registry.json`` (21 of 24 committed entries carry ``null``),
    ``engine/stock_identity/replay/registry.py``, and
    ``scripts/stock_identity_replay_pilot.py`` (``fa.get(...)``)."""
    if entry is None or "family_first_available" not in entry:
        return None, False
    val = entry.get("family_first_available")
    return (pd.Timestamp(val) if val else None), True


def _episode_family_availability_state(
    erow: Any,
    family_entry: Mapping[str, Any] | None,
    family_entry_present: bool,
    bars_by_symbol: Mapping[str, pd.DataFrame] | None,
    bars_supplied: bool,
) -> str:
    """One typed availability state for a ``(family, tier-eligible episode)``
    pair — outcome-independent, never reads ``events``/fires (Ruling 2). Returns
    :data:`FAMILY_ELIGIBLE_STATE` or one of the closed
    :data:`AVAILABILITY_TAXONOMY_TOKENS` exclusion states:

    * ``"UNESTIMABLE"`` — no family registry was supplied at all, this
      ``family_key`` is absent from it, or the registry entry genuinely lacks
      the ``family_first_available`` field (three distinct "cannot establish
      lawful availability" causes, all typed the same way per Ruling 2 (c) —
      NEVER a silent fall-through to fired-on coverage), OR no
      ``bars_by_symbol`` was supplied to check instrument/date coverage.
    * ``"NOT_YET_AVAILABLE"`` — the registry's ``family_first_available``
      postdates the episode's ENTIRE window (start through end/anchor-absent
      fallback to start) — a resolved, typed exclusion.
    * ``"NO_COVERAGE"`` — bars were supplied but do not cover the episode's
      instrument/window.
    """
    if not family_entry_present:
        return "UNESTIMABLE"
    bound, field_present = _family_first_available_bound(family_entry)
    if not field_present:
        return "UNESTIMABLE"
    start = pd.Timestamp(erow.start_date)
    end_raw = getattr(erow, "end_date", None)
    end = pd.Timestamp(end_raw) if end_raw is not None and pd.notna(end_raw) else start
    if bound is not None and bound > end:
        return "NOT_YET_AVAILABLE"
    if not bars_supplied:
        return "UNESTIMABLE"
    symbol = str(erow.symbol)
    bars = bars_by_symbol.get(symbol) if bars_by_symbol else None
    if bars is None or bars.empty:
        return "NO_COVERAGE"
    lo, hi = bars.index.min(), bars.index.max()
    covers = (lo <= start <= hi) or (lo <= end <= hi) or (start <= lo and end >= hi)
    if not covers:
        return "NO_COVERAGE"
    return FAMILY_ELIGIBLE_STATE


def build_family_episode_availability(
    episodes: pd.DataFrame,
    family_keys: Sequence[str],
    *,
    family_registry: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] | None = None,
    bars_by_symbol: Mapping[str, pd.DataFrame] | None = None,
    tier_ceiling: int = 2,
) -> pd.DataFrame:
    """The outcome-independent ``(family_key, tier-eligible episode)``
    availability frame Ruling 2 (SI-W3A-RULER-V1 PR-3 seal law) requires
    :func:`aggregate_cell_metrics`'s ``recall_at_tier`` denominator be built
    from — REPLACING the prior events-derived ("fired-on") family/symbol
    coverage universe. One row per ``(family_key, tier-eligible episode)``
    pair — REGARDLESS of whether that family ever fired an event on that
    episode's symbol — carrying a typed, closed ``availability_state``
    (:data:`FAMILY_ELIGIBLE_STATE` / :data:`AVAILABILITY_TAXONOMY_TOKENS`; see
    :func:`_episode_family_availability_state`).

    Availability is established from OUTCOME-INDEPENDENT provenance/coverage
    only: (i) the W2 family registry's own ``family_first_available``
    boundary (never postdating the episode's window), and (ii)
    instrument/date input availability (``bars_by_symbol`` coverage of the
    episode's window). Grain carries no separate availability axis in the
    committed provenance — one symbol's OHLCV underlies every grain a family
    might read it at — so instrument/date/grain availability collapses to (ii)
    by design, not by omission.

    Class-P families (zero committed rows,
    ``engine/stock_identity/replay/registry.py``'s ``CLASS_P_FAMILIES``) and
    any family absent from ``family_keys`` never appear here at all — they
    carry no ``fire_metrics`` rows upstream, so :func:`aggregate_cell_metrics`
    never forms a cell for them regardless of this frame's content.
    """
    registry_index = _family_registry_index(family_registry)
    family_registry_supplied = family_registry is not None
    bars_supplied = bars_by_symbol is not None

    eps = episodes if episodes is not None else pd.DataFrame()
    if eps.empty or not {"symbol", "episode_type", "tier", "start_date"} <= set(eps.columns) or not family_keys:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in FAMILY_EPISODE_AVAILABILITY_COLUMNS})

    tier_eligible = eps.loc[eps["tier"].fillna(3) <= tier_ceiling].copy()
    if tier_eligible.empty:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in FAMILY_EPISODE_AVAILABILITY_COLUMNS})

    tier_eligible["eligible_episode_id"] = tier_eligible.apply(
        lambda r: episode_identifier(r["symbol"], r["episode_type"], r["start_date"]), axis=1
    )

    rows: list[dict[str, Any]] = []
    for family_key in sorted(set(family_keys)):
        entry = registry_index.get(family_key)
        entry_present = family_registry_supplied and (family_key in registry_index)
        for erow in tier_eligible.itertuples(index=False):
            state = _episode_family_availability_state(
                erow, entry, entry_present, bars_by_symbol, bars_supplied,
            )
            rows.append({
                "family_key": family_key,
                "episode_type": erow.episode_type,
                "symbol": str(erow.symbol),
                "episode_id": erow.eligible_episode_id,
                "availability_state": state,
            })
    return pd.DataFrame(rows, columns=list(FAMILY_EPISODE_AVAILABILITY_COLUMNS))


# ---------------------------------------------------------------------------
# Task 3: cell aggregation + composites
# ---------------------------------------------------------------------------
def aggregate_cell_metrics(
    fire_metrics: pd.DataFrame,
    episodes: pd.DataFrame,
    spec: RulerSpec,
    events: pd.DataFrame,
    *,
    group_cols: Sequence[str] = ("family_key", "episode_type", "grain"),
    family_registry: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]] | None = None,
    bars_by_symbol: Mapping[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Per-cell aggregates consumed by :func:`compute_composites`.

    ``recall_at_tier`` — of EVERY tier-eligible episode (tier <= 2, the "useful"
    episodes per ``episodes.py`` tier floors) in the ``episodes`` catalog that
    belongs to the cell's ``episode_type`` and that the cell's family was
    LAWFULLY AVAILABLE to fire on (Ruling 2, SI-W3A-RULER-V1 PR-3 seal law —
    see :func:`build_family_episode_availability`) — REGARDLESS of whether
    that episode ever received a fire — the fraction that received at least
    one in-zone fire (``|atr_dist| <= useful_zone_delta_atr``) from this cell.
    A cell whose eligible episodes never fired at all still reports a defined
    ``0.0``, never ``NaN`` (freeze review finding B2). The eligibility
    universe is now built from OUTCOME-INDEPENDENT provenance/coverage (the
    ``family_registry``'s ``family_first_available`` boundary plus
    ``bars_by_symbol`` instrument/date coverage) — Ruling 2 REPLACES the prior
    events-derived ("fired-on") family/symbol coverage universe: adding an
    available symbol with eligible episodes and zero fires now GROWS the
    denominator (and can only hold or lower recall, never improve it), a
    genuinely not-yet-available symbol never enters the denominator, and
    missing eligibility evidence (``family_registry``/``bars_by_symbol`` not
    supplied, or a family/field absent from the registry) types the excluded
    episodes ``UNESTIMABLE`` rather than silently falling through to the OLD
    fired-on read. ``zone_precision`` — of the cell's fires with a defined
    ``atr_dist``, the fraction that landed in-zone. ``false_start_rate`` —
    mean of the per-fire ``false_start`` flag over resolved (non-``None``)
    fires. ``flooding`` — fires per eligible-episode useful-zone session
    (``n_fires / (n_eligible * useful_zone_window_sessions)``), a size-invariant
    density read on noise (freeze review finding M7 — previously not normalized
    by the eligible-episode population, so cells with more coverage always read
    "noisier" at equal density). ``relative_order`` — over same-episode fire
    pairs, the fraction where the temporally later fire sits closer to anchor.
    ``consistency`` — ``1 - CV(|atr_dist|)`` within the cell, clipped to ``[0, 1]``.

    ``events`` is retained as a required positional parameter for call-site
    compatibility only — Ruling 2 removes its prior use (deriving the
    recall-denominator coverage universe from fired-on events); it is no
    longer read by this function's own logic.
    """
    if fire_metrics is None or fire_metrics.empty:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in CELL_METRIC_COLUMNS})

    fm = fire_metrics.copy()
    fm["_in_zone"] = fm["atr_dist"].abs() <= spec.useful_zone_delta_atr

    # Ruling 2 (SI-W3A-RULER-V1 PR-3 seal law): the recall-denominator
    # eligibility universe is now the outcome-independent
    # build_family_episode_availability() frame — never events-derived
    # ("fired-on") coverage (DNR:KILL-OUTCOME-AUDITION also applies: this
    # never reads any expert's own outcome rank). Computed ONCE, keyed by
    # (family_key, episode_type), for every family_key that appears among
    # fm's own groups (a family with zero fires anywhere never forms a cell
    # at all, so its eligibility is never needed).
    family_keys_present = sorted({str(f) for f in fm["family_key"].dropna().unique()})
    availability = build_family_episode_availability(
        episodes, family_keys_present,
        family_registry=family_registry, bars_by_symbol=bars_by_symbol,
    )
    eligible_by_cell: dict[tuple[Any, Any], set[str]] = {}
    if not availability.empty:
        elig_only = availability.loc[availability["availability_state"] == FAMILY_ELIGIBLE_STATE]
        for (fam, etype), sub_a in elig_only.groupby(["family_key", "episode_type"]):
            eligible_by_cell[(fam, etype)] = set(sub_a["episode_id"])

    rows: list[dict[str, Any]] = []
    for key, sub in fm.groupby(list(group_cols), dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        family_key = key[0] if len(key) > 0 else None
        episode_type = key[1] if len(key) > 1 else None
        n_fires = int(len(sub))
        n_episodes = int(sub["episode_id"].nunique())

        defined_atr = sub.dropna(subset=["atr_dist"])
        zone_precision = (
            float(defined_atr["_in_zone"].mean()) if not defined_atr.empty else np.nan
        )

        fs = sub["false_start"].dropna()
        false_start_rate = float(fs.mean()) if len(fs) else np.nan

        family_key_str = str(family_key) if family_key is not None else None
        eligible_ids = eligible_by_cell.get((family_key_str, episode_type), set())
        n_eligible = len(eligible_ids)

        recalled_ids = set(
            sub.loc[sub["_in_zone"] == True, "episode_id"]  # noqa: E712
        )
        n_recalled = len(eligible_ids & recalled_ids)
        recall_at_tier = (n_recalled / n_eligible) if n_eligible > 0 else np.nan

        flooding = (
            (n_fires / (n_eligible * spec.useful_zone_window_sessions))
            if (n_eligible > 0 and spec.useful_zone_window_sessions)
            else np.nan
        )

        rel_hits = 0
        rel_total = 0
        for _, esub in sub.groupby("episode_id"):
            esub = esub.dropna(subset=["atr_dist"]).sort_values("signal_known_ts")
            if len(esub) < 2:
                continue
            dvals = esub["atr_dist"].abs().to_numpy()
            for i in range(len(dvals) - 1):
                rel_total += 1
                if dvals[i + 1] < dvals[i]:
                    rel_hits += 1
        relative_order = (rel_hits / rel_total) if rel_total > 0 else np.nan

        in_zone_dists = defined_atr.loc[defined_atr["_in_zone"] == True, "atr_dist"].abs()  # noqa: E712
        atr_dist_median_in_zone = float(in_zone_dists.median()) if len(in_zone_dists) else np.nan

        abs_dists = defined_atr["atr_dist"].abs()
        if len(abs_dists) >= 2 and float(abs_dists.mean()) > 0:
            consistency = float(max(0.0, min(1.0, 1.0 - (abs_dists.std() / abs_dists.mean()))))
        else:
            consistency = np.nan

        rows.append({
            "family_key": key[0] if len(key) > 0 else None,
            "episode_type": key[1] if len(key) > 1 else None,
            "grain": key[2] if len(key) > 2 else None,
            "n_fires": n_fires,
            "n_episodes": n_episodes,
            "false_start_rate": false_start_rate,
            "flooding": flooding,
            "recall_at_tier": recall_at_tier,
            "zone_precision": zone_precision,
            "relative_order": relative_order,
            "consistency": consistency,
            "atr_dist_median_in_zone": atr_dist_median_in_zone,
        })

    return pd.DataFrame(rows)[list(CELL_METRIC_COLUMNS)]


def compute_composites(metrics: pd.DataFrame, spec: RulerSpec) -> pd.DataFrame:
    """The two and only two graded composites, over already-aggregated cell metrics.

    ``C-LOC-R = recall_at_tier * zone_precision - lambda_fs * false_start_rate``.
    ``C-LOC-D`` is the rank-normalized median in-zone ATR distance to anchor
    (closer = higher score), gated to ``NaN`` below ``recall_floor`` and
    penalized by ``false_start_rate`` at the same ``lambda_fs``.

    REFUSES while ``spec.pr3_pending`` — the shipped spec's PR-3 fields carry the
    ``pending_sealed_calibration`` sentinel until Task 3C runs, and this function
    never substitutes a guessed or fixture value for a production constant.
    """
    if spec.pr3_pending:
        raise PendingSealedCalibrationError(
            "ruler spec PR-3 constants (lambda_fs/recall_floor) are still "
            f"{PR3_PENDING_SENTINEL!r} — Task 3C has not run. compute_composites "
            "never substitutes a guessed or fixture value for a production constant."
        )
    if metrics is None:
        raise ValueError("metrics: input is None")

    out = metrics.copy()
    out["c_loc_r"] = out["recall_at_tier"] * out["zone_precision"] - spec.lambda_fs * out["false_start_rate"]

    # M5/M5-residual: rank-normalize WITHIN the stratum spec.c_loc_d_rank_population
    # declares — a cell's C-LOC-D must never move because unrelated strata's cells
    # were added/removed (frozen population choice, read from the spec itself —
    # ruler_spec_v1.json.c_loc_d_rank_population == "episode_type_x_grain"; see
    # W3_RULER_REGISTRATION.md). A missing stratum column REFUSES rather than
    # silently falling back to a GLOBAL rank across the whole population (the
    # prior implementation's `elif` branch) — that fallback is exactly the
    # invariant-breaking computation the stratified rank exists to prevent.
    if "atr_dist_median_in_zone" in out.columns:
        closer_is_better = -out["atr_dist_median_in_zone"]
        if spec.c_loc_d_rank_population == "episode_type_x_grain":
            if not {"episode_type", "grain"} <= set(out.columns):
                raise MissingRankStratumColumnsError(
                    "compute_composites: c_loc_d_rank_population="
                    f"{spec.c_loc_d_rank_population!r} requires 'episode_type' and "
                    "'grain' columns in the cell-metrics frame to rank WITHIN each "
                    "stratum (freeze review finding M5) — refusing rather than "
                    "silently falling back to a GLOBAL rank across the whole "
                    "population, which would let a cell's c_loc_d move whenever "
                    "cells from an unrelated stratum are added or removed."
                )
            ranked = closer_is_better.groupby(
                [out["episode_type"], out["grain"]]
            ).rank(pct=True, na_option="keep")
        else:
            raise ValueError(
                "compute_composites: unsupported c_loc_d_rank_population "
                f"{spec.c_loc_d_rank_population!r} (only 'episode_type_x_grain' is "
                "currently defined)"
            )
    else:
        ranked = pd.Series(np.nan, index=out.index)
    c_loc_d = ranked - spec.lambda_fs * out["false_start_rate"]

    # M1: a NaN recall_at_tier must FAIL the recall-floor gate (fail-closed) — the
    # prior `.fillna(False)` treated an undefined recall as "not below floor" and
    # let a cell with no measurable recall still receive a graded c_loc_d.
    recall_is_nan = out["recall_at_tier"].isna()
    below_floor = out["recall_at_tier"] < spec.recall_floor
    gated = below_floor.fillna(False) | recall_is_nan
    c_loc_d = c_loc_d.mask(gated)
    out["c_loc_d"] = c_loc_d

    gate_reason = pd.Series(None, index=out.index, dtype="object")
    gate_reason = gate_reason.mask(recall_is_nan, "recall_at_tier_nan")
    gate_reason = gate_reason.mask(below_floor.fillna(False) & ~recall_is_nan, "below_recall_floor")
    out["c_loc_d_gate_reason"] = gate_reason
    return out


# ---------------------------------------------------------------------------
# support/coverage frame (Task 2 Step 7 — the ONLY ruler-side artifact Task 4 may
# consume; NO realized metric or composite column)
# ---------------------------------------------------------------------------
def _empty_support_frame() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in SUPPORT_COVERAGE_COLUMNS})


def build_support_coverage(
    events: pd.DataFrame,
    attribution: pd.DataFrame,
    episodes: pd.DataFrame,
    bars_by_symbol: Mapping[str, pd.DataFrame],
    feature_symbols: Any = (),
) -> pd.DataFrame:
    """The typed outcome-independent support/coverage frame for W3B.

    One row per attribution row (attributed or not) — identifiers, clocks/blocks,
    family/grain, attribution presence, feature/price coverage and
    censored/availability state. ``calendar_block`` here is a simple, honestly
    provisional calendar-quarter bucket over ``known_ts``; Task 4 owns the real
    P90-episode-duration block-length law (freeze §4.2) and may recompute this
    column from ``known_ts`` — this frame never claims to already implement it.
    """
    validate_ruler_inputs(events, attribution, episodes)
    if attribution is None or attribution.empty:
        return _empty_support_frame()

    ev_lookup: pd.DataFrame = pd.DataFrame()
    if events is not None and not events.empty:
        cols = [c for c in ("grain", "price_plane_id") if c in events.columns]
        ev_lookup = events.set_index("event_id")[cols]

    feature_syms = set(feature_symbols) if feature_symbols is not None else set()
    eps_lookup = _episode_lookup(episodes)

    rows: list[dict[str, Any]] = []
    for r in attribution.itertuples(index=False):
        symbol = str(r.symbol)
        known_ts = pd.Timestamp(r.signal_known_ts)
        grain = None
        plane_id = None
        if r.event_id in ev_lookup.index:
            row = ev_lookup.loc[r.event_id]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            grain = row.get("grain")
            plane_id = row.get("price_plane_id")

        attributed = bool(r.attributed)
        eid = None
        # MEASURED_ZERO: a real, measured fire that simply did not attribute to any
        # episode window — bars/data were available, the outcome is a genuine zero,
        # never a missing-data state (freeze §7 taxonomy; MINORS finding).
        availability_state = "MEASURED_ZERO"
        if attributed:
            eps = eps_lookup.get(symbol)
            idx = int(r.episode_index) if r.episode_index is not None and pd.notna(r.episode_index) else None
            if eps is not None and idx is not None and 0 <= idx < len(eps):
                erow = eps.iloc[idx]
                eid = _episode_id(symbol, erow["episode_type"], erow["start_date"])
                # "resolved" is the one non-problem state and is deliberately NOT
                # drawn from AVAILABILITY_TAXONOMY_TOKENS (see that constant's
                # docstring); CENSORED is a real taxonomy token.
                availability_state = "CENSORED" if bool(erow.get("censored")) else "resolved"

        bars = bars_by_symbol.get(symbol) if bars_by_symbol else None
        has_bars = bars is not None and not bars.empty
        price_coverage = 0.0
        if has_bars:
            price_coverage = 1.0 if (bars.index.min() <= known_ts <= bars.index.max()) else 0.0
        if not has_bars and availability_state == "MEASURED_ZERO":
            # missing-bars -> NO_COVERAGE (freeze §7 taxonomy; MINORS finding).
            availability_state = "NO_COVERAGE"

        feature_coverage = 1.0 if symbol in feature_syms else 0.0
        calendar_block = f"{known_ts.year}Q{((known_ts.month - 1) // 3) + 1}"
        # Provisional: Task 4 owns the real P90-episode-duration block-length law
        # (freeze §4.2) and may recompute calendar_block from known_ts. This basis
        # tag makes that provisionality machine-readable rather than only prose.
        calendar_block_basis = "calendar_quarter_provisional"

        rows.append({
            "episode_id": eid,
            "event_id": r.event_id,
            "ticker": symbol,
            "known_ts": known_ts,
            "calendar_block": calendar_block,
            "calendar_block_basis": calendar_block_basis,
            "family": r.family_key,
            "grain": grain,
            "attributed": attributed,
            "price_coverage": price_coverage,
            "feature_coverage": feature_coverage,
            "price_plane_id": plane_id,
            "availability_state": availability_state,
        })

    if not rows:
        return _empty_support_frame()
    return pd.DataFrame(rows)[list(SUPPORT_COVERAGE_COLUMNS)]
