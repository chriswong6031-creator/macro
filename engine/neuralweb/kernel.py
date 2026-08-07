"""engine.neuralweb.kernel — Reliability Kernel ESTIMATES (Neural Web W3 PR1).

HONESTY HEADER
--------------
The outputs of this module are ESTIMATES WITH UNCERTAINTY, never findings.

Only shrunken posteriors (shrunken_ic) are consumable by display surfaces; raw
means (mean_raw) are diagnostic only and must never drive allocation or alerting.

No behavior-changing consumer may read the artifact produced here
(data/neuralweb/kernel_estimates.parquet) until a cell passes the quarterly
pre-registered decision batch (PR2 FDR sweep). Display-first law is enforced
structurally: this module registers zero behavior-changing consumers.

Regime-conditioned cells are honest-but-thin: track_record regime stamps began
accruing 2026-07; qledger regime stamps are null pending backfill. The deep
1962-present signal-engine archive fills the marginal ('__all__') cells, which
carry the real statistical depth. Regime-conditioned cells will thicken as stamps
accrue — treat them as exploratory until then.

CELL DEFINITION
---------------
A kernel cell is the triple (engine, regime_bucket, horizon).

  regime_bucket: derived from quad_hard_label (primary regime dimension:
    Goldilocks / Reflation / Stagflation / Recession). Rows with null
    quad_hard_label → bucket '__unstamped__'.

  In ADDITION to regime-conditioned cells, the marginal bucket '__all__' is
  ALWAYS emitted per (engine, horizon). The marginal aggregates all rows
  regardless of regime stamp and is the depth-bearing cell for engines whose
  rows mostly pre-date the 2026-07 stamping campaign.

  horizon: integer trading-day horizon. Filtered to {5, 10, 21, 63, 126} as
    present in the spine index.

OUTCOME: signed excess via engine.spine._signed_outcome semantics (reused here
  by importing and mirroring exactly — see _signed_outcome). A positive signed
  outcome means the signal fired in the correct direction — BUT ONLY where the
  underlying outcome is genuinely signed; see OUTCOME BASIS below.

OUTCOME BASIS (per-cell label; gates wilson_ci_low)
---------------------------------------------------
Cells carry an ``outcome_basis`` column copied from the spine index rows
(query.OUTCOME_BASIS_FOR_LEDGER; a cell is single-engine so the mode is the
cell's basis). Vocabulary and the underlying trap are documented in
engine/neuralweb/query.py — the short version: four ledgers (track_record,
board_hk, board_ca, board_cn) fill outcome_excess from a forward MAXIMUM-
FAVORABLE-EXCURSION column that is non-negative BY CONSTRUCTION, with
direction pinned to 1.

  wilson_ci_low is DIRECTIONAL ACCURACY. Against an unsigned MFE proxy the
  quantity is undefined — "hits" degenerates to "MFE > 0 at least once",
  which is nearly always true — so this module emits wilson_ci_low=None for
  cells whose basis is not signed. Mirrors PR #4673's
  ``dst_outcome_unsigned_mfe_proxy``: direction agreement is undefined
  against an unsigned outcome, so the cohort is UNGRADEABLE for sign, not
  "graded 96% right".

  REPLACED VALUES (this is a correction, not an addition): pre-fix,
  track_record h=126 published wilson_ci_low=0.963. That number was
  "fraction of rows whose MFE exceeded zero at least once", never directional
  accuracy. Every unsigned cell's wilson_ci_low now reads None.

  synthetic_sign_stub cells (cortex_attention ±0.01) KEEP their Wilson CI:
  the sign there is a real hit/miss, only the magnitude is a placeholder.

  mean_raw, shrunken_ic, shrunken_ic_sd, reliability and the pooling family
  are UNCHANGED for every basis — they are magnitude statistics, now merely
  labelled by basis. half_life.py's documented rising-curve measurement reads
  those, so silently nulling them would delete a live measurement.

  A basis of None (unmapped ledger, or a legacy parquet with no column that
  somehow escaped the read-time backfill) is treated as NOT signed —
  fail-closed.

EVENT DEDUP: n_eff counts distinct (engine, symbol, as_of) triples within a
  horizon-specific cell — not raw row count. This is the co-firing collapse
  (#23): multiple rows for the same (engine, symbol, as_of) at a given horizon
  count as ONE observation. Because a cell is horizon-specific, a row at h=5
  and a row at h=21 for the same signal land in DIFFERENT cells and are
  counted once each in their respective cells. This is correct: one FIRE is
  one observation per (cell horizon) — a multi-horizon emission is one piece
  of evidence per horizon bucket, not per row.

SHRINKAGE: engine/pooling.py is reused DIRECTLY (imported, not reimplemented).
  One MemberStat per cell (key='engine:regime:horizon', n=n_eff, mean=raw mean
  signed excess, var=sample var). The pooling family = all cells sharing the
  same engine value. Two-tier shrinkage toward global 0: member → family →
  global (via pooled_edges). fill_basis=='asof_legacy' rows receive a
  noise=0.5 discount in MemberStat to reflect that legacy fills are noisier
  than next_bar fills.

  FAMILY MEMBERSHIP (audit fix): while an engine's regime stamps are 0%
  populated (regime_coverage == 0), its '__unstamped__' cells are byte-identical
  to the '__all__' marginals; keeping both as pooling members double-counts
  every horizon in the family denominator, inflating family precision. At 0%
  coverage, '__unstamped__' cells are EXCLUDED from family pooling membership —
  the rows are still emitted (display parity) and inherit the posterior of
  their identical '__all__' twin. Once real stamps accrue (coverage > 0),
  '__unstamped__' is a genuine sub-population and rejoins the family.

PER-CELL OUTPUTS
----------------
  n_raw           raw row count (before dedup)
  n_eff           distinct-(engine,symbol,as_of) count (event-collapsed)
  mean_raw        raw mean signed excess (diagnostic — do NOT consume directly)
  shrunken_ic     pooled_edges() output for this cell (the consumable posterior)
  shrunken_ic_sd  posterior sd of the shrunken cell mean (normal-normal model:
                  sqrt((var/n_eff)·(1-reliability)); at zero noise this equals
                  sqrt(var/(n_eff+K_POOL))). Displays render shrunken_ic ± sd.
  reliability     n_eff / (n_eff + K_POOL) as a single reliability metric
  outcome_basis   what outcome_excess measures for this cell (mode of the rows'
                  query.outcome_basis; None when the rows carry no label)
  wilson_ci_low   Wilson CI lower bound on directional accuracy (None when
                  n_eff < 12, OR when outcome_basis is not sign-safe — see
                  OUTCOME BASIS above)
  date_first      earliest as_of date in the cell (recency anchor)
  date_last       latest as_of date in the cell (recency anchor)
  fill_basis_mode most-common fill_basis value (provenance label)
  armed           bool — pooling.arming() result for the engine family
  armed_reason    str|None — pooling.arming() reason (family-level, broadcast;
                  previously computed but dropped before any artifact — the
                  arming reason now survives to kernel_families.json/site)
  regime_coverage fraction of graded deduped events for the engine carrying a
                  quad_hard_label stamp (family-level, broadcast to cells)

PER-FAMILY: pooling.arming() status (armed bool + heldout edges + reason) is
  computed and STORED for display; nothing acts on it in this PR. The family
  record in meta also carries regime_coverage (see above).

USAGE
-----
  from engine.neuralweb.kernel import build_estimates, write_estimates
  df, meta = build_estimates(root)          # full in-memory build
  write_estimates(root)                     # idempotent write to disk

CONSUMER CONTRACT (display-first law)
--------------------------------------
  Consumers reading kernel_estimates.parquet are display-only surfaces.
  DO NOT USE shrunken_ic to change allocation, alert severity, or board
  ordering until a cell passes the quarterly FDR batch (PR2). The armed
  flag is informational — it does NOT grant behavior-changing access in PR1.
"""
from __future__ import annotations

import logging
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine import pooling
from engine.pooling import MemberStat, K_POOL
from engine.qledger import wilson_ci_low as _wilson_ci_low

log = logging.getLogger(__name__)

__all__ = [
    "HORIZONS",
    "REGIME_COL",
    "UNSTAMPED_BUCKET",
    "MARGINAL_BUCKET",
    "NOISE_ASOF_LEGACY",
    "WILSON_MIN_N",
    "build_estimates",
    "write_estimates",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Horizons emitted in kernel cells (trading-day windows).
HORIZONS: tuple[int, ...] = (5, 10, 21, 63, 126)

#: Primary regime column — most populated across track_record/spine lanes.
REGIME_COL: str = "quad_hard_label"

#: Bucket label for rows with null quad_hard_label.
UNSTAMPED_BUCKET: str = "__unstamped__"

#: Marginal bucket — always emitted per (engine, horizon), aggregates all rows.
MARGINAL_BUCKET: str = "__all__"

#: Noise discount applied to fill_basis=='asof_legacy' rows (MemberStat.noise).
#: Legacy fills are noisier than next_bar fills; 0.5 ≈ halves effective reliability.
NOISE_ASOF_LEGACY: float = 0.5

#: Minimum n_eff to compute Wilson CI; below this, ci_low = None (accruing).
WILSON_MIN_N: int = 12

#: Outcome bases against which DIRECTIONAL ACCURACY is a defined quantity.
#: signed_excess — real signed return. synthetic_sign_stub — ±0.01 placeholder
#: whose SIGN is a real hit/miss (only the magnitude is fabricated), so a
#: directional hit rate over it is meaningful. Everything else — notably
#: unsigned_mfe_proxy, and None — yields wilson_ci_low=None (fail-closed).
SIGN_SAFE_BASES: frozenset[str] = frozenset({
    "signed_excess",
    "synthetic_sign_stub",
})


def _cell_outcome_basis(rows: pd.DataFrame) -> str | None:
    """Mode of the cell's outcome_basis, or None when unlabelled.

    A cell is single-engine and (in practice) single-ledger, so the mode IS
    the cell's basis; the mode form only guards against a mixed frame.
    Fail-open: a frame with no column, an all-null column, or an unreadable
    column returns None — which every caller must read as "not sign-safe".
    """
    if "outcome_basis" not in rows.columns:
        return None
    try:
        vals = rows["outcome_basis"].dropna().astype(str)
        vals = vals[~vals.isin(("", "nan", "None"))]
        if vals.empty:
            return None
        return str(Counter(vals.tolist()).most_common(1)[0][0])
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Internal: signed outcome (mirrors engine.spine._signed_outcome semantics)
# ---------------------------------------------------------------------------

def _signed_outcome_series(
    outcome_excess: pd.Series, direction: pd.Series
) -> pd.Series:
    """Direction-aware realized excess — cite: engine.spine._signed_outcome.

    A SHORT/veto (direction == -1) that avoided a loser earns POSITIVE credit
    (sign-inverted), matching audit #17 sign-convention. direction == 0 keeps
    the raw excess (no directional claim).

    This mirrors engine.spine._signed_outcome exactly; duplicated here to avoid
    a dependency on engine.spine (which reads local spine parquets and has
    side-effect paths); the kernel works on the pre-filtered neuralweb index.
    """
    d = pd.to_numeric(direction, errors="coerce").fillna(1)
    signed = outcome_excess.where(
        d == 0,
        outcome_excess * np.sign(d.replace(0, 1)),
    )
    return signed


# ---------------------------------------------------------------------------
# Internal: load the spine index
# ---------------------------------------------------------------------------

def _load_index(root: Path | str | None) -> pd.DataFrame:
    """Load data/neuralweb/spine_index.parquet via the W2 query layer.

    Returns an empty DataFrame if the parquet is absent or unreadable.
    The caller handles the empty case gracefully.
    """
    from engine.neuralweb.query import load_index  # noqa: PLC0415
    return load_index(root)


# ---------------------------------------------------------------------------
# Internal: cell row builder
# ---------------------------------------------------------------------------

def _cell_key(engine: str, regime: str, horizon: int) -> str:
    return f"{engine}:{regime}:{horizon}"


def _build_cell(
    engine: str,
    regime: str,
    horizon: int,
    rows: pd.DataFrame,
) -> dict[str, Any]:
    """Compute per-cell statistics from a filtered set of graded rows.

    Parameters
    ----------
    engine:     engine name (e.g. 'track_record', 'us_board').
    regime:     regime bucket string (MARGINAL_BUCKET, UNSTAMPED_BUCKET, or a
                quad_hard_label value like 'Goldilocks').
    horizon:    integer horizon.
    rows:       graded rows for this (engine, regime, horizon) cell — already
                filtered; must be non-empty.

    Returns
    -------
    dict with per-cell statistics (all defined in the module docstring).
    """
    # --- n_raw: raw row count before dedup ---
    n_raw = int(len(rows))

    # --- n_eff: distinct (symbol, as_of) pairs within this horizon cell ---
    # One FIRE = one observation per cell horizon (rows are already horizon-filtered).
    # Within the same cell, a symbol-date appearing multiple times is one event.
    # rows_deduped keeps the FIRST occurrence per (symbol, as_of) so that the
    # Wilson CI numerator (hits) and denominator (n_eff) come from the same
    # population — mixing pre-dedup numerator with deduped denominator would
    # give phat = hits/n_eff where hits > n_eff is possible under heavy co-firing.
    rows_deduped = rows.drop_duplicates(subset=["symbol", "as_of"])
    n_eff = int(len(rows_deduped))

    # --- signed outcomes (direction-aware) ---
    outcome_excess = pd.to_numeric(rows["outcome_excess"], errors="coerce")
    direction = rows["direction"]
    signed = _signed_outcome_series(outcome_excess, direction)
    finite_mask = np.isfinite(signed)
    signed_finite = signed[finite_mask]

    if len(signed_finite) == 0:
        mean_raw = 0.0
        var_raw = 1.0
    else:
        mean_raw = float(signed_finite.mean())
        var_raw = float(signed_finite.var()) if len(signed_finite) > 1 else 1.0
        var_raw = max(var_raw, 1e-9)

    # --- fill_basis mode and noise discount ---
    fill_bases = rows["fill_basis"].dropna().astype(str)
    fill_basis_mode: str
    if fill_bases.empty:
        fill_basis_mode = "unknown"
    else:
        fill_basis_mode = str(Counter(fill_bases.tolist()).most_common(1)[0][0])

    # asof_legacy rows are noisier — discount reliability
    n_asof_legacy = int((fill_bases == "asof_legacy").sum())
    frac_legacy = (n_asof_legacy / max(len(fill_bases), 1))
    noise = NOISE_ASOF_LEGACY * frac_legacy if frac_legacy > 0 else 0.0

    # --- outcome basis: what outcome_excess measures for this cell ---
    outcome_basis = _cell_outcome_basis(rows)

    # --- Wilson CI lower bound (directional accuracy) ---
    # Hits MUST be counted on the SAME deduped population used for n_eff.
    # Using pre-dedup signed_finite would give hits > n_eff under heavy same-day
    # co-firing, producing phat > 1 and sqrt(negative) inside the Wilson formula.
    #
    # BASIS GATE: directional accuracy is only defined where the sign of the
    # outcome carries information.  Against an unsigned MFE proxy (or an
    # unlabelled cell) "hits" degenerates to "MFE > 0 at least once" and the
    # CI reads as a near-1 accuracy that was never measured — so hits are not
    # counted at all and ci_low stays None.  Magnitude statistics above are
    # unaffected.  cf. PR #4673 edge_outcomes.py dst_outcome_unsigned_mfe_proxy.
    hits: int | None = None
    ci_low: float | None = None
    if outcome_basis in SIGN_SAFE_BASES:
        deduped_excess = pd.to_numeric(rows_deduped["outcome_excess"], errors="coerce")
        deduped_direction = rows_deduped["direction"]
        signed_deduped = _signed_outcome_series(deduped_excess, deduped_direction)
        hits = int((signed_deduped[np.isfinite(signed_deduped)] > 0).sum())
        if n_eff >= WILSON_MIN_N:
            ci_low = _wilson_ci_low(hits, n_eff)

    # --- date range ---
    asof_vals = rows["as_of"].dropna().astype(str)
    date_first = str(asof_vals.min()) if not asof_vals.empty else None
    date_last = str(asof_vals.max()) if not asof_vals.empty else None

    # --- shrunken_ic_sd: posterior sd of the shrunken cell mean ---
    # Normal-normal shrinkage posterior: with sampling variance var/n and
    # noise-discounted reliability r = MemberStat.reliability() (the SAME
    # machinery pooled_edges() consumes), posterior variance = (var/n)·(1-r).
    # At zero noise this is exactly var/(n_eff + K_POOL). Emitted so displays
    # can show an IC ± band per cell instead of a bare point estimate.
    shrunken_ic_sd: float | None = None
    if n_eff > 0:
        rel = MemberStat(
            key="_sd", n=float(n_eff), mean=mean_raw, var=var_raw, noise=noise,
        ).reliability()
        shrunken_ic_sd = round(
            math.sqrt(max(var_raw, 1e-9) / n_eff * max(1.0 - rel, 0.0)), 6,
        )

    return {
        "engine": engine,
        "regime": regime,
        "regime_col": REGIME_COL,
        "horizon": horizon,
        "n_raw": n_raw,
        "n_eff": n_eff,
        "mean_raw": round(mean_raw, 6),
        # shrunken_ic and reliability filled in after pooled_edges() call
        "shrunken_ic": None,
        "shrunken_ic_sd": shrunken_ic_sd,
        "reliability": round(n_eff / (n_eff + K_POOL), 4),
        "outcome_basis": outcome_basis,
        "wilson_ci_low": ci_low,
        # armed / armed_reason / regime_coverage filled in after arming() call
        "armed": None,
        "armed_reason": None,
        "regime_coverage": None,
        "fill_basis_mode": fill_basis_mode,
        "date_first": date_first,
        "date_last": date_last,
        # internal use only — consumed by pooled_edges(); stripped before output
        "_mean_raw": mean_raw,
        "_var_raw": var_raw,
        "_n_eff": n_eff,
        "_noise": noise,
        "_key": _cell_key(engine, regime, horizon),
    }


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def build_estimates(
    root: Path | str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Build kernel estimate cells from the spine index.

    Returns
    -------
    (df, meta)
        df: one row per (engine, regime_bucket, horizon) cell.
        meta: dict with build stats and per-family arming status.
    """
    index_df = _load_index(root)

    if index_df.empty:
        log.warning("kernel.build_estimates: spine index empty — returning empty estimates")
        meta = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "n_cells": 0,
            "n_engines": 0,
            "families": {},
            "gaps": ["spine index empty"],
        }
        return pd.DataFrame(), meta

    # Read-time backfill of outcome_basis.  load_index() already stamps via
    # _ensure_columns, but build_estimates is also called with hand-built
    # frames in tests and could be handed a pre-column parquet by a caller
    # that bypassed the query layer; the stamp is cheap and idempotent, and a
    # missing column here would silently null every Wilson CI.
    try:
        from engine.neuralweb.query import stamp_outcome_basis  # noqa: PLC0415
        index_df = stamp_outcome_basis(index_df)
    except Exception as e:  # noqa: BLE001
        log.warning("kernel.build_estimates: outcome_basis stamp failed (%s)", e)

    # Filter to graded rows only
    graded_mask = index_df["outcome_graded"].fillna(False)
    try:
        graded_mask = graded_mask.astype(bool)
    except (TypeError, ValueError):
        graded_mask = graded_mask.map(lambda x: bool(x) if x is not None else False)

    graded = index_df[graded_mask].copy().reset_index(drop=True)

    # Filter to finite outcome_excess
    graded["outcome_excess"] = pd.to_numeric(graded["outcome_excess"], errors="coerce")
    graded = graded[np.isfinite(graded["outcome_excess"])].reset_index(drop=True)

    # Filter to known horizons
    graded["horizon"] = pd.to_numeric(graded["horizon"], errors="coerce")
    graded = graded[graded["horizon"].isin(HORIZONS)].reset_index(drop=True)

    # Normalise engine column
    graded["engine"] = graded["engine"].fillna("unknown").astype(str)

    # Derive regime bucket from quad_hard_label
    graded["_regime_bucket"] = (
        graded[REGIME_COL]
        .fillna("")
        .astype(str)
        .apply(lambda v: UNSTAMPED_BUCKET if v.strip() in ("", "nan", "None") else v.strip())
    )

    # Regime coverage per engine: fraction of graded deduped events carrying a
    # quad_hard_label stamp. 0.0 → the '__unstamped__' bucket is byte-identical
    # to '__all__' (drives the pooling-membership exclusion below); reported on
    # both the family record and every cell so displays can label thin stamps.
    engines = graded["engine"].unique().tolist()
    regime_coverage: dict[str, float] = {}
    for engine in engines:
        eng_events = graded[graded["engine"] == engine].drop_duplicates(
            subset=["symbol", "as_of"],
        )
        if eng_events.empty:
            regime_coverage[engine] = 0.0
        else:
            n_stamped = int((eng_events["_regime_bucket"] != UNSTAMPED_BUCKET).sum())
            regime_coverage[engine] = round(n_stamped / len(eng_events), 4)

    # Collect cells
    cell_rows: list[dict[str, Any]] = []

    for engine in engines:
        eng_df = graded[graded["engine"] == engine]

        horizons_present = sorted(eng_df["horizon"].dropna().unique().tolist())
        for h_float in horizons_present:
            h = int(h_float)
            if h not in HORIZONS:
                continue
            h_df = eng_df[eng_df["horizon"] == h_float]

            # --- Regime-conditioned cells ---
            for regime, r_df in h_df.groupby("_regime_bucket"):
                if r_df.empty:
                    continue
                cell = _build_cell(engine, str(regime), h, r_df)
                cell_rows.append(cell)

            # --- Marginal cell ('__all__') — always emitted ---
            # NOTE: while the spine has zero regime stamps, __all__ and __unstamped__
            # are byte-identical cells for every engine. The __unstamped__ duplicate
            # is therefore EXCLUDED from the pooling family membership below
            # (regime_coverage == 0 guard) so it cannot double-count its horizon in
            # the family denominator; the row itself is still emitted for display
            # parity and inherits the posterior of its identical __all__ twin.
            if not h_df.empty:
                cell = _build_cell(engine, MARGINAL_BUCKET, h, h_df)
                cell_rows.append(cell)

    if not cell_rows:
        log.warning("kernel.build_estimates: no graded rows with valid horizons — empty estimates")
        meta = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "n_cells": 0,
            "n_engines": 0,
            "families": {},
            "gaps": ["no graded rows with valid horizons"],
        }
        return pd.DataFrame(), meta

    # ---------------------------------------------------------------------------
    # Apply shrinkage via engine/pooling.py (reused DIRECTLY — no reimplementation)
    # ---------------------------------------------------------------------------
    # Group cells into families by engine value; apply pooled_edges() per family.
    by_engine: dict[str, list[dict]] = {}
    for cell in cell_rows:
        by_engine.setdefault(cell["engine"], []).append(cell)

    for engine_name, cells in by_engine.items():
        coverage = regime_coverage.get(engine_name, 0.0)
        # AUDIT FIX: at 0% regime coverage every __unstamped__ cell is byte-
        # identical to its __all__ twin — keeping both as members double-counts
        # each horizon in the family denominator (rel_fam inflates). Exclude
        # __unstamped__ from MEMBERSHIP while coverage == 0; once any real
        # stamps accrue it is a genuine sub-population and rejoins the family.
        member_cells = [
            c for c in cells
            if not (coverage == 0.0 and c["regime"] == UNSTAMPED_BUCKET)
        ]
        members = [
            MemberStat(
                key=c["_key"],
                n=float(c["_n_eff"]),
                mean=c["_mean_raw"],
                var=c["_var_raw"],
                noise=c["_noise"],
            )
            for c in member_cells
        ]
        edges = pooling.pooled_edges(members)
        # Excluded __unstamped__ cells inherit their identical __all__ twin's
        # posterior (same rows → same posterior; emitted for display parity).
        marginal_key_by_h = {
            c["horizon"]: c["_key"] for c in member_cells
            if c["regime"] == MARGINAL_BUCKET
        }
        for cell in cells:
            key = cell["_key"]
            if key not in edges:
                key = marginal_key_by_h.get(cell["horizon"], key)
            cell["shrunken_ic"] = round(edges.get(key, 0.0), 6)

    # ---------------------------------------------------------------------------
    # Compute arming() per engine family (stored for display; nothing acts on it)
    # ---------------------------------------------------------------------------
    # arming() expects a time-ordered list of {key, event_key, outcome, as_of}.
    # We build this from all graded rows per engine, using signed outcome.
    family_arming: dict[str, dict] = {}
    for engine_name in engines:
        eng_df = graded[graded["engine"] == engine_name].copy()
        # Build event list — collapse per (symbol, as_of) key for arming.
        # signed outcomes reuse _signed_outcome_series (the same helper used in
        # _build_cell) to avoid a second reimplementation of the sign convention.
        eng_excess = pd.to_numeric(eng_df["outcome_excess"], errors="coerce")
        eng_signed = _signed_outcome_series(eng_excess, eng_df["direction"])
        finite_eng = np.isfinite(eng_signed)
        events: list[dict] = []
        for idx_i, is_finite in enumerate(finite_eng):
            if not is_finite:
                continue
            row = eng_df.iloc[idx_i]
            events.append({
                "key": str(row.get("family") or engine_name),
                "event_key": f"{row.get('symbol', '')}:{row.get('as_of', '')}",
                "outcome": float(eng_signed.iloc[idx_i]),
                "as_of": str(row.get("as_of") or ""),
            })
        arm_status = pooling.arming(events)
        family_record = arm_status.to_dict()
        # Family record carries regime_coverage (fraction of graded events
        # with a quad_hard_label stamp) alongside the arming status.
        family_record["regime_coverage"] = regime_coverage.get(engine_name, 0.0)
        family_arming[engine_name] = family_record

    # Propagate armed flag + arming reason + regime coverage to cells.
    # armed_reason was previously computed here and then dropped before any
    # artifact (only the bool survived to the parquet) — persisting it lets
    # decay.py carry the explicit reason into kernel_families.json/site.
    for cell in cell_rows:
        arm = family_arming.get(cell["engine"], {})
        cell["armed"] = bool(arm.get("armed", False))
        cell["armed_reason"] = str(arm.get("reason")) if arm.get("reason") else None
        cell["regime_coverage"] = regime_coverage.get(cell["engine"], 0.0)

    # ---------------------------------------------------------------------------
    # Build output DataFrame (strip internal helper columns)
    # ---------------------------------------------------------------------------
    output_cols = [
        "engine", "regime", "regime_col", "horizon",
        "n_raw", "n_eff", "mean_raw", "shrunken_ic", "shrunken_ic_sd",
        "reliability", "outcome_basis", "wilson_ci_low", "armed", "armed_reason",
        "regime_coverage",
        "fill_basis_mode", "date_first", "date_last",
    ]
    for cell in cell_rows:
        for k in list(cell.keys()):
            if k.startswith("_"):
                del cell[k]

    df = pd.DataFrame(cell_rows)[output_cols].copy()
    df["horizon"] = df["horizon"].astype(int)
    df = df.sort_values(
        ["engine", "horizon", "regime"],
        na_position="last",
    ).reset_index(drop=True)

    meta = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_cells": len(df),
        "n_engines": int(df["engine"].nunique()),
        "n_graded_rows_input": int(len(graded)),
        "families": family_arming,
        "gaps": [],
    }

    log.info(
        "kernel.build_estimates: %d cells across %d engines (%d graded input rows)",
        len(df), df["engine"].nunique(), len(graded),
    )
    return df, meta


# ---------------------------------------------------------------------------
# Write function (idempotent, full-rebuild)
# ---------------------------------------------------------------------------

def write_estimates(root: Path | str | None = None) -> dict:
    """Build kernel estimates and write to data/neuralweb/kernel_estimates.parquet.

    Also writes the envelope sidecar (artifact_id='kernel-estimates').

    IDEMPOTENT FULL REBUILD: the estimates parquet is a derived artifact,
    not a forward ledger. Overwriting on each nightly run is correct.

    NOTE on sidecar: do NOT call envelope.verify() on binary sidecars —
    byte_sha256 is the correct integrity check for parquet artifacts.
    write_sidecar() uses byte_sha256 internally; the verify() function
    checks the JSON inputs_hash which is not applicable to binary files.

    Returns a stats dict with cell counts and family arming status.
    """
    df, meta = build_estimates(root)

    if root is not None:
        out_dir = Path(root) / "data" / "neuralweb"
    else:
        from lib import config  # noqa: PLC0415
        out_dir = config.data_dir() / "neuralweb"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "kernel_estimates.parquet"

    if df.empty:
        # Write an empty but schema-valid parquet
        output_cols = [
            "engine", "regime", "regime_col", "horizon",
            "n_raw", "n_eff", "mean_raw", "shrunken_ic", "shrunken_ic_sd",
            "reliability", "outcome_basis", "wilson_ci_low", "armed", "armed_reason",
            "regime_coverage",
            "fill_basis_mode", "date_first", "date_last",
        ]
        df = pd.DataFrame(columns=output_cols)

    try:
        df.to_parquet(out_path, index=False)
    except Exception as e:  # noqa: BLE001
        log.error("kernel.write_estimates: to_parquet failed: %s", e)
        raise

    # Write the envelope sidecar
    try:
        from engine.neuralweb.envelope import write_sidecar  # noqa: PLC0415
        write_sidecar(out_path, artifact_id="kernel-estimates")
    except Exception as e:  # noqa: BLE001
        log.warning("kernel.write_estimates: sidecar write failed: %s", e)

    stats = {
        "output_path": str(out_path),
        "n_cells": meta.get("n_cells", 0),
        "n_engines": meta.get("n_engines", 0),
        "n_graded_rows_input": meta.get("n_graded_rows_input", 0),
        "generated_at": meta.get("generated_at"),
        "families": meta.get("families", {}),
    }
    log.info(
        "kernel.write_estimates: wrote %d cells to %s",
        stats["n_cells"], out_path,
    )
    return stats
