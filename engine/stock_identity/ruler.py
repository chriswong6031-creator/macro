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
    "PendingSealedCalibrationError",
    "RulerSpec",
    "grain_class",
    "episode_identifier",
    "validate_ruler_inputs",
    "compute_fire_metrics",
    "compute_unconditional_block",
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

#: Closed per-fire metric column names (plan Task 1 interface).
FIRE_METRIC_COLUMNS: tuple[str, ...] = (
    "event_id", "family_key", "symbol", "episode_id", "episode_type",
    "episode_tier", "grain", "signal_known_ts",
    "lead_lag", "price_dist", "atr_dist", "mae_after", "capture", "false_start",
)

#: Closed unconditional-block column names (plan Task 1 interface).
UNCONDITIONAL_BLOCK_COLUMNS: tuple[str, ...] = (
    "family_key", "symbol", "total_fires", "attributed_fires",
    "fires_per_name_year", "episode_attribution_rate",
)

#: Closed cell-aggregate column names — the "aggregations" owned by
#: ``compute_fire_metrics`` per the plan's Global Constraints closed-column list.
CELL_METRIC_COLUMNS: tuple[str, ...] = (
    "family_key", "episode_type", "grain", "n_fires", "n_episodes",
    "false_start_rate", "flooding", "recall_at_tier", "zone_precision",
    "relative_order", "consistency", "atr_dist_median_in_zone",
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
    "episode_id", "event_id", "ticker", "known_ts", "calendar_block", "family",
    "grain", "attributed", "price_coverage", "feature_coverage", "price_plane_id",
    "availability_state",
)


class PendingSealedCalibrationError(RuntimeError):
    """Raised when a composite/constant read is attempted while the PR-3 ruler
    constants still carry the ``pending_sealed_calibration`` sentinel."""


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
                    if a0_ok and pd.notna(atr_dist):
                        lo, hi = (known_ts, anchor_ts) if known_ts <= anchor_ts else (anchor_ts, known_ts)
                        window = bars.loc[(bidx >= lo) & (bidx <= hi), "close"]
                        if not window.empty:
                            dists = (window.astype(float) - float(anchor_price)).abs() / float(a0_anchor)
                            mae_after = float(max(0.0, float(dists.max()) - abs(atr_dist)))

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
    events: pd.DataFrame, attribution: pd.DataFrame, episode_rows: pd.DataFrame
) -> pd.DataFrame:
    """Every expert/ticker row: total fires, attributed fires, fires/name/year and
    ``episode_attribution_rate`` — preserving zero-total as explicit no-coverage
    (``NaN``) rather than division to zero (plan Task 2 Step 4)."""
    required = ("event_id", "family_key", "symbol")
    if events is None:
        raise ValueError("events: input is None")
    missing = [c for c in required if c not in events.columns]
    if missing:
        raise ValueError(f"events: missing required column(s) {missing}")
    if events.empty:
        return _empty_unconditional_block()

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

    out = total.merge(attributed, on=["family_key", "symbol"], how="left")
    out["attributed_fires"] = out["attributed_fires"].fillna(0).astype(int)
    out["total_fires"] = out["total_fires"].astype(int)

    span_years = _symbol_span_years(episode_rows)
    out["fires_per_name_year"] = out.apply(
        lambda r: (
            r["total_fires"] / span_years[r["symbol"]]
            if span_years.get(r["symbol"]) else np.nan
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


# ---------------------------------------------------------------------------
# Task 3: cell aggregation + composites
# ---------------------------------------------------------------------------
def aggregate_cell_metrics(
    fire_metrics: pd.DataFrame,
    episodes: pd.DataFrame,
    spec: RulerSpec,
    *,
    group_cols: Sequence[str] = ("family_key", "episode_type", "grain"),
) -> pd.DataFrame:
    """Per-cell aggregates consumed by :func:`compute_composites`.

    ``recall_at_tier`` — of the cell's tier-eligible episodes (tier <= 2, the
    "useful" episodes per ``episodes.py`` tier floors), the fraction that
    received at least one in-zone fire (``|atr_dist| <= useful_zone_delta_atr``).
    ``zone_precision`` — of the cell's fires with a defined ``atr_dist``, the
    fraction that landed in-zone. ``false_start_rate`` — mean of the per-fire
    ``false_start`` flag over resolved (non-``None``) fires. ``flooding`` — fires
    per useful-zone session, a density read on noise. ``relative_order`` — over
    same-episode fire pairs, the fraction where the temporally later fire sits
    closer to anchor. ``consistency`` — ``1 - CV(|atr_dist|)`` within the cell,
    clipped to ``[0, 1]``.
    """
    if fire_metrics is None or fire_metrics.empty:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in CELL_METRIC_COLUMNS})

    fm = fire_metrics.copy()
    fm["_in_zone"] = fm["atr_dist"].abs() <= spec.useful_zone_delta_atr

    rows: list[dict[str, Any]] = []
    for key, sub in fm.groupby(list(group_cols), dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        n_fires = int(len(sub))
        n_episodes = int(sub["episode_id"].nunique())

        defined_atr = sub.dropna(subset=["atr_dist"])
        zone_precision = (
            float(defined_atr["_in_zone"].mean()) if not defined_atr.empty else np.nan
        )

        fs = sub["false_start"].dropna()
        false_start_rate = float(fs.mean()) if len(fs) else np.nan

        eligible_eps = sub[sub["episode_tier"].fillna(3) <= 2]
        n_eligible = int(eligible_eps["episode_id"].nunique())
        n_recalled = int(
            eligible_eps.loc[eligible_eps["_in_zone"] == True, "episode_id"].nunique()  # noqa: E712
        )
        recall_at_tier = (n_recalled / n_eligible) if n_eligible > 0 else np.nan

        flooding = (n_fires / spec.useful_zone_window_sessions) if spec.useful_zone_window_sessions else np.nan

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

    if "atr_dist_median_in_zone" in out.columns:
        closer_is_better = -out["atr_dist_median_in_zone"]
        ranked = closer_is_better.rank(pct=True, na_option="keep")
    else:
        ranked = pd.Series(np.nan, index=out.index)
    c_loc_d = ranked - spec.lambda_fs * out["false_start_rate"]
    below_floor = out["recall_at_tier"] < spec.recall_floor
    c_loc_d = c_loc_d.mask(below_floor.fillna(False))
    out["c_loc_d"] = c_loc_d
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
        availability_state = "unattributed"
        if attributed:
            eps = eps_lookup.get(symbol)
            idx = int(r.episode_index) if r.episode_index is not None and pd.notna(r.episode_index) else None
            if eps is not None and idx is not None and 0 <= idx < len(eps):
                erow = eps.iloc[idx]
                eid = _episode_id(symbol, erow["episode_type"], erow["start_date"])
                availability_state = "censored" if bool(erow.get("censored")) else "resolved"

        bars = bars_by_symbol.get(symbol) if bars_by_symbol else None
        has_bars = bars is not None and not bars.empty
        price_coverage = 0.0
        if has_bars:
            price_coverage = 1.0 if (bars.index.min() <= known_ts <= bars.index.max()) else 0.0
        if not has_bars and availability_state == "unattributed":
            availability_state = "structural_absence"

        feature_coverage = 1.0 if symbol in feature_syms else 0.0
        calendar_block = f"{known_ts.year}Q{((known_ts.month - 1) // 3) + 1}"

        rows.append({
            "episode_id": eid,
            "event_id": r.event_id,
            "ticker": symbol,
            "known_ts": known_ts,
            "calendar_block": calendar_block,
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
