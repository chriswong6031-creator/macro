"""Flow-column unit-artifact detector + PIT-honest repair for the EDGAR panel.

The frames-API scan in collectors/edgar.py occasionally lands on a fact stored in
the wrong unit for income-statement and cash-flow line items.  The two common
signatures are:

  ×1e3 low: the filer's net-income (or similar) fact is in thousands rather than
  units — ED fy2021-25 ni = 1.346e6/1.66e6/2.519e6/1.82e6/2.023e6 when the real
  values are ~$1.3-2.5 billion (ConEd).  Scale factor ×1e3 restores the row.

  ×1e6 low: the fact is in millions — ANET fy2021-25 ni = 841/1352/2087/2852/3511
  when the real values are ~$841M-$3.5B (Arista Networks).  Scale ×1e6 restores.

Both defects corrupt PIT earnings-yield and profitability factor legs on every
backtest rebalance that touches the artifact row.

Scope
-----
FLOW_COLS (7 columns).  Class A (5, scale-anchored — revenue/assets provide a
magnitude reference): ni, cfo, gross_profit, revenue, op_income.  Class B (2,
legitimately lumpy/near-zero; stricter interior-only rule): dividends, repurchases.

Out of scope (documented residual): interest_exp and capex.
  interest_exp has real near-zero-to-converts jumps (DDOG/GWRE) that are
  indistinguishable from unit artifacts without additional evidence.
  capex is a statements-lane provenance column and is already reconciled there.

Detection lanes
---------------
Lane 1 — cross-source (xsrc), Class A only
  For each panel row, compare the panel value to the same (ticker, fy) value in
  statements.parquet.  When both are finite, nonzero, same sign, and
  |st| / |panel| is within XSRC_TOL of 10^k for k ∈ XSRC_KS (k > 0 only — panel
  is always the small side, by construction of the artifact), AND the panel value's
  share of same-row revenue (or assets) is below PANEL_SHARE_MAX, the row is
  flagged xsrc_scale and repaired = panel_value × 10^k.

  BGC fy2023 anti-pattern: statements ni = 38775 while the panel is 38775000
  (the correct value).  Here |st|/|panel| ≈ 0.001, so k would be −3 (negative) —
  excluded by the k>0 requirement.  The row appears in xsrc_disagreements instead.

  Rows where |st|/|panel| is within [1/XSRC_CLEAN, XSRC_CLEAN] (same sign) are
  marked PROTECTED.  The flank lane cannot flag them regardless of segmentation.

Lane 1b — cohort (xsrc_cohort), Class A only
  Applied in the fixed-point loop after the xsrc pass, before the flank lane.
  For each (ticker, col) with >= 2 xsrc_scale flags all at the same power k,
  find unflagged nonzero rows that are CONTIGUOUS with the flagged rows in the
  nonzero-value sequence (transitively adjacent to a flagged row).  A row is
  flagged xsrc_cohort with repair = own value × 10^k only when ALL of:
    - statements HAS a value for that (ticker, fy, col) and it is
      scale-consistent: |st| / |raw| within [10^k / COHORT_ST_BAND,
      10^k × COHORT_ST_BAND].  When filers report net-income-attributable-to-
      common vs total incl. NCI/preferred the two variants diverge 5–30 %,
      never ~1000×; a statements value within 1.25× of 10^k corroborates the
      scale even when it picked a different fact variant (PCG/VC variant-split
      archetype: |st|/|raw| ≈ 0.83–0.90×10^6, within 1.25× of 10^6).
      Statements-absent rows are NEVER cohort-flagged: without cross-source
      corroboration the magnitude gates below cannot separate a mis-scaled
      fact from a genuine near-breakeven year in the artifact's regime (a
      real $3M impairment year on a $25B-revenue filer passes all of them).
    - |raw| / anchor < ABSURD_SHARE (anchor = revenue, else assets);
    - |raw| within 100x of the nearest confirmed row's raw (same scale regime);
    - |raw × 10^k| / anchor in [1e-4, 0.6] (scaled plausibility).
  Motivation: PCG ni fy2021 (real $−102M loss year between xsrc-confirmed ×1e6
  fy2022-25 rows) and VC ni fy2023/fy2024 (real $587M/$306M swing years between
  xsrc-confirmed ×1e6 fy2022 and fy2025 rows).

Lane 2 — segment/flank (flank), all 7 columns
  Per (ticker, column): segment the nonzero finite values at ≥ SEG_JUMP consecutive
  moves (zeros and NaNs break adjacency but are neither artifacts nor evidence).
  For each segment with at least one flanking clean segment, check two criteria:

  Share absurdity: the candidate segment's median |val|/|anchor| is below
  ABSURD_SHARE and ≥ SHARE_SEP× smaller than the clean flank's share.  Anchor =
  revenue (assets when c == revenue; Class B falls back to assets when revenue is
  absent; candidate is skipped if no anchor is present).

  Scale snap: try k ∈ FLANK_KS.  Scaled adjacent row vs adjacent clean-flank value
  within TIGHT_ADJ AND same sign for at least one present flank; EVERY present
  flank within LOOSE_ALL; raw break vs each present flank ≥ MIN_BREAK.  The same-
  sign requirement is waived when |raw| < RAW_ABSURD (e.g. VC ni fy2021 = 50 — a
  $50 annual net income on a $2.8B-revenue company is physically implausible and the
  sign of a tiny artifact depends on rounding).

  Anchor continuity at each boundary: among revenue/cfo/assets (excluding c) present
  on both sides, at least one within ANCHOR_CONT and none ≥ ANCHOR_BLOWUP.

  Margin coherence (Class A only): scaled |adjacent seg row|/|anchor| vs adjacent
  clean-flank row's |col|/|anchor| must be within MARGIN_COH.

  Class B (dividends, repurchases) — stricter: interior segments only (BOTH flanks
  present), tight same-sign snap on BOTH adjacent flanks, plus anchor continuity
  and share-absurdity.  No margin-coherence concept (Class B flows are lumpy).

  Segments that pass share-absurdity and anchor continuity with break ≥ 500× but
  find no confident k are recorded in flank_suspects (no mutation).

Repair discipline (PIT-honest)
-------------------------------
Every repair is the row's OWN filed value ×10^k for k ∈ {3, 6} — a deterministic
rescaling of the row's own fact.  This is PIT-legal: if the filer reported in
thousands, the "correct" billions value was implicitly knowable from the same
filing.  No repair ever uses a value from statements.parquet or from another row
— statements is EVIDENCE ONLY, not a repair source, because the statements lane
can itself carry a unit artifact (BGC fy2023 demonstrates this).

The nulled count in v1 audits is always 0.  Unlike the shares module (where some
artifacts have no confident PIT-legal repair and must be nulled), every detected
flow artifact has a confident own-value×10^k repair by construction: the xsrc lane
only fires when the statements ratio confirms the scale factor; the flank lane only
fires when the scaled value snaps tightly against both flanks.  A row that fails
the snap is left in flank_suspects with no mutation.

ni_prior mirroring
-------------------
Many panel rows carry ni_prior = prior fiscal year's ni.  When ni is repaired, the
following year's ni_prior (when present and equal to the raw ni within rel tol 1e-6)
is updated to the repaired value and recorded as ni_prior:mirror.  This prevents
the prior-year reference from remaining as a phantom artifact in the panel.

Known residuals (conservative by design)
-----------------------------------------
- Single-row interior artifacts without statements coverage AND whose flanks disagree
  in sign are left unflagged (CWK fy2019 class — real breakeven between losses).
- Leading/trailing single-segment artifacts without a clean opposite flank cannot be
  confidently distinguished from real level changes and stay in flank_suspects.
- interest_exp: real near-zero-to-converts jumps indistinguishable; out of scope.
- capex: statements-lane provenance; out of scope.
- The ABM fy2020 class (real COVID near-breakeven between normal years): the ×1e3
  snapped value lands >TIGHT_ADJ off both flanks — correctly left unflagged.
- The HOG fy2020 / ADSK cfo fy2017 class (real trough): scaled lands >TIGHT_ADJ
  off the clean flank — correctly left unflagged.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# columns and constants
# ---------------------------------------------------------------------------
FLOW_COLS = ["ni", "cfo", "gross_profit", "revenue", "op_income",
             "dividends", "repurchases"]

CLASS_A = ["ni", "cfo", "gross_profit", "revenue", "op_income"]
CLASS_B = ["dividends", "repurchases"]

XSRC_KS = (3, 6)           # panel value ×10^k should equal the statements value
XSRC_TOL = 1.10            # ...within this multiplicative band (ED lands ~1.000)
XSRC_CLEAN = 1.5           # panel≈statements within this = row PROTECTED from flank lane
PANEL_SHARE_MAX = 1e-2     # xsrc belt: panel raw must be tiny vs same-row revenue/assets

SEG_JUMP = 30.0            # consecutive-FY abs-ratio that starts a new level segment
                           # (flows are noisy; 30x is far above any real year-on-year move)
FLANK_KS = (3, 6)
TIGHT_ADJ = 1.8            # scaled segment row ADJACENT to a clean flank must land within
                           # this, SAME SIGN.  1.8 structurally excludes HOG-class real
                           # breakeven years (HOG ni fy2020=1298000; ×1e3=1.298B lands
                           # 1.997× off the 650M right flank — correctly unflagged at 1.8,
                           # would have been flagged at 2.0)
RAW_ABSURD = 1e4           # |raw| below this waives the same-sign requirement (a $50-$10k
                           # annual flow on a $100M+ company is physically implausible
                           # regardless of sign — VC ni fy2021 = 50)
LOOSE_ALL = 4.0            # every present flank must land within this (abs) after scaling
ANCHOR_CONT = 2.5          # ≥1 of revenue/cfo/assets continuous within this across each
                           # used boundary
ANCHOR_BLOWUP = 100.0      # ...and none of the present anchors breaks by this much
MARGIN_COH = 3.0           # scaled |col|/|anchor| vs adjacent-clean-year share, abs ratio
                           # (Class A only)
ABSURD_SHARE = 1e-3        # artifact-side |col|/|anchor| must be below this
SHARE_SEP = 50.0           # clean-side share / artifact-side share must be at least this
MIN_BREAK = 100.0          # belt: raw-vs-flank abs ratio floor
SUSPECTS_MIN_BREAK = 500.0 # flank_suspects trigger: high break but no confident snap

# Cohort lane: statements-present tolerance band.  When statements picks a
# DIFFERENT real fact variant (e.g. net-income-attributable-to-common vs total
# incl. NCI/preferred — PG&E's preferred dividends are exactly the −88 M vs
# −102 M gap), the two variants diverge 5–30 %, never ~1000×.  A statements
# value within 1.25× of 10^k corroborates the scale even when it picked a
# different variant (PCG/VC cases: ratios 0.83–0.90 × 10^k, well within 1.25×);
# only a statements value outside this band (e.g. 0.70× or 1.26×) is treated
# as a different-scale disagreement that blocks cohort flagging.
COHORT_ST_BAND = 1.25


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------
def _ratio(a, b) -> float:
    """Symmetric ratio max(a/b, b/a); NaN when either side is missing/zero/inf."""
    if a is None or b is None:
        return float("nan")
    a, b = float(a), float(b)
    if not (np.isfinite(a) and np.isfinite(b)) or a == 0.0 or b == 0.0:
        return float("nan")
    return max(abs(a) / abs(b), abs(b) / abs(a))


def _same_sign(a, b) -> bool:
    return (a > 0) == (b > 0)


def _segments_nonzero(vals: np.ndarray) -> list[list]:
    """Segment the POSITIONAL indices of nonzero-finite values at >=SEG_JUMP
    consecutive-pair moves.  Zeros and NaNs are excluded from segmentation (they
    break adjacency); each segment entry is [start_pos, end_pos, median_val] where
    positions index into `vals` directly.

    Returns list of [lo, hi, median] in position space within vals."""
    nz_idx = [i for i, v in enumerate(vals) if np.isfinite(v) and v != 0.0]
    if not nz_idx:
        return []
    segs: list[list] = []
    start = 0
    for j in range(1, len(nz_idx)):
        pi, ci = nz_idx[j - 1], nz_idx[j]
        r = _ratio(vals[pi], vals[ci])
        if np.isfinite(r) and r >= SEG_JUMP:
            seg_positions = nz_idx[start:j]
            seg_vals = [vals[p] for p in seg_positions]
            segs.append([seg_positions[0], seg_positions[-1],
                         float(np.median(seg_vals))])
            start = j
    seg_positions = nz_idx[start:]
    seg_vals = [vals[p] for p in seg_positions]
    segs.append([seg_positions[0], seg_positions[-1],
                 float(np.median(seg_vals))])
    return segs


def _seg_anchor(col: str, vals_col: np.ndarray, anchors: dict[str, np.ndarray],
                seg_lo: int, seg_hi: int) -> float | None:
    """Median absolute anchor value for a segment's positions.

    Anchor selection per position:
      col == "revenue" → assets
      Class B          → revenue, then assets fallback
      Class A (other)  → revenue, then assets fallback (amendment 2: TECH/EFC arch.)
    """
    col_anchors: list[float] = []
    rev_arr = anchors.get("revenue", np.array([]))
    ast_arr = anchors.get("assets", np.array([]))
    for pos in range(seg_lo, seg_hi + 1):
        if col == "revenue":
            av = ast_arr[pos] if pos < len(ast_arr) else np.nan
        else:
            # Class A or Class B: revenue primary, assets fallback
            av = rev_arr[pos] if pos < len(rev_arr) else np.nan
            if not (np.isfinite(av) and av != 0):
                av = ast_arr[pos] if pos < len(ast_arr) else np.nan
        if np.isfinite(av) and av != 0:
            col_anchors.append(abs(av))
    if not col_anchors:
        return None
    return float(np.median(col_anchors))


def _anchor_cont_ok(col: str, anchors: dict[str, np.ndarray], lo_pos: int,
                    hi_pos: int) -> bool:
    """Anchor continuity check across a boundary (lo_pos, hi_pos are adjacent
    position indices in the full ticker array).
    Among revenue/cfo/assets (excluding col itself) present on both sides:
      - at least one pair within ANCHOR_CONT
      - none of the present pairs >= ANCHOR_BLOWUP
    Returns True when the criteria are met; also returns True when NO anchor is
    present on either side (conservative: can't disprove continuity)."""
    checks: list[float] = []
    cands = [c for c in ("revenue", "cfo", "assets") if c != col]
    for ac in cands:
        arr = anchors.get(ac)
        if arr is None:
            continue
        if lo_pos < 0 or hi_pos >= len(arr):
            continue
        a, b = arr[lo_pos], arr[hi_pos]
        if not (np.isfinite(a) and np.isfinite(b) and a != 0 and b != 0):
            continue
        checks.append(_ratio(a, b))
    if not checks:
        return True   # no anchor available — conservative pass
    if any(r >= ANCHOR_BLOWUP for r in checks):
        return False
    return any(r <= ANCHOR_CONT for r in checks)


# ---------------------------------------------------------------------------
# core detector
# ---------------------------------------------------------------------------
def detect(panel: pd.DataFrame, statements: pd.DataFrame | None = None
           ) -> pd.DataFrame:
    """Scan the panel for flow-column unit artifacts.

    Returns a DataFrame with columns:
      [index, ticker, fy, col, flag, value, repair, note]
    where:
      index   = panel.index label of the flagged row
      flag    = "xsrc_scale", "xsrc_cohort", or "flank_scale"
      value   = original panel value
      repair  = value × 10^k (always finite; nulled count is always 0 in v1)
      note    = e.g. "x1e3 vs statements", "x1e6 cohort of 4 xsrc rows",
                or "x1e3 flank"

    Also emits (via audit) xsrc_disagreements and flank_suspects lists — these
    are returned only by apply_flow_quality, not by detect directly.

    Raises ValueError when the panel lacks required columns (ticker, fy,
    period_end, and at least ni).  Individual missing FLOW_COLS are tolerated by
    skipping those columns.

    statements=None → xsrc lane is skipped entirely.
    """
    need = {"ticker", "fy", "period_end"}
    missing_req = need - set(panel.columns)
    if missing_req:
        raise ValueError(f"panel missing required columns: {sorted(missing_req)}")
    if "ni" not in panel.columns:
        raise ValueError("panel missing required column: ni")

    active_cols = [c for c in FLOW_COLS if c in panel.columns]

    # Pre-join statements on (ticker, fy) for xsrc lane
    stmt_joined: dict[str, pd.Series] = {}   # col -> Series indexed by panel.index
    if statements is not None and not statements.empty:
        stmt_cols = [c for c in active_cols if c in CLASS_A and c in statements.columns]
        if stmt_cols:
            key_cols = ["ticker", "fy"] + stmt_cols
            stmt_sub = statements[key_cols].drop_duplicates(subset=["ticker", "fy"],
                                                            keep="last")
            merged = panel[["ticker", "fy"]].merge(
                stmt_sub, on=["ticker", "fy"], how="left", suffixes=("", "_s"))
            merged.index = panel.index
            for c in stmt_cols:
                stmt_joined[c] = pd.to_numeric(merged[c], errors="coerce")

    flags: list[dict] = []
    # xsrc_disagreements and flank_suspects accumulate internally; returned in
    # apply_flow_quality not here (detect is pure: flags only)
    _xsrc_disagree: list[dict] = []
    _flank_suspects: list[dict] = []

    # Protected set: (panel_index, col) → that row×col can't be flagged by flank lane.
    # Protection is column-scoped: a row whose ni agrees with statements is protected
    # only for the ni column; its dividends column remains eligible for flank flagging.
    protected: set[tuple] = set()   # (index, col) pairs

    # ---------------------------------------------------------------------------
    # Lane 1: cross-source (xsrc)
    # ---------------------------------------------------------------------------
    if stmt_joined:
        for col, st_series in stmt_joined.items():
            for idx in panel.index:
                pv = panel.at[idx, col]
                sv = st_series.at[idx]
                if not (np.isfinite(pv) and np.isfinite(sv)):
                    continue
                if pv == 0 or sv == 0:
                    continue
                if not _same_sign(pv, sv):
                    continue
                ratio_raw = abs(sv) / abs(pv)    # always > 0

                # Check if already in agreement (PROTECTED — skip xsrc, protect from flank)
                # Protection is column-scoped so other columns on the same row remain eligible.
                if 1.0 / XSRC_CLEAN <= ratio_raw <= XSRC_CLEAN:
                    protected.add((idx, col))
                    continue

                # Check for scale match: ratio_raw ≈ 10^k within XSRC_TOL, k > 0
                matched_k = None
                for k in XSRC_KS:
                    power = 10.0 ** k
                    band = ratio_raw / power
                    if 1.0 / XSRC_TOL <= band <= XSRC_TOL:
                        matched_k = k
                        break

                if matched_k is None:
                    # significant disagreement, neither clean nor artifact candidate
                    if ratio_raw > 2.0 or ratio_raw < 0.5:
                        _xsrc_disagree.append({
                            "ticker": panel.at[idx, "ticker"],
                            "fy": int(panel.at[idx, "fy"]),
                            "col": col,
                            "panel": float(pv),
                            "statements": float(sv),
                        })
                    continue

                # Belt: panel raw must be small relative to revenue/assets
                ticker_row = panel.loc[idx]
                rev = float(ticker_row.get("revenue", np.nan))
                ast = float(ticker_row.get("assets", np.nan))
                anchor = (ast if col == "revenue" or not np.isfinite(rev) or rev == 0
                          else rev)
                if np.isfinite(anchor) and anchor != 0:
                    if abs(pv) / abs(anchor) >= PANEL_SHARE_MAX:
                        # panel value is not tiny — not a unit artifact (or revenue
                        # itself is a small company; skip belt if no anchor available)
                        _xsrc_disagree.append({
                            "ticker": panel.at[idx, "ticker"],
                            "fy": int(panel.at[idx, "fy"]),
                            "col": col,
                            "panel": float(pv),
                            "statements": float(sv),
                        })
                        continue

                flags.append({
                    "index": idx,
                    "ticker": panel.at[idx, "ticker"],
                    "fy": int(panel.at[idx, "fy"]),
                    "col": col,
                    "flag": "xsrc_scale",
                    "value": float(pv),
                    "repair": float(pv) * (10.0 ** matched_k),
                    "note": f"x1e{matched_k} vs statements",
                })

    # Build set of xsrc-flagged indices per col for flank-lane protection
    xsrc_flagged: set[tuple] = {(f["index"], f["col"]) for f in flags}

    # ---------------------------------------------------------------------------
    # Lane 1b: xsrc_cohort
    # For each (ticker, col) that already has >= 2 xsrc_scale flags at the same k,
    # flag unflagged nonzero rows that are CONTIGUOUS (in the nonzero-value sequence)
    # with the flagged rows — provided statements is absent OR scale-consistent
    # (within COHORT_ST_BAND of 10^k) and plausibility conditions hold.
    # Motivation: PCG ni fy2021 (real loss year between xsrc-confirmed ×1e6 rows
    # fy2022-25) and VC ni fy2023-24 (real swing years between xsrc-confirmed
    # neighbours); in both cases statements picked a different real fact variant
    # (attributable-to-common vs total incl. NCI/preferred), so |st|/|raw| ≈ 0.86e6
    # — corroborating the scale while outside XSRC_TOL.
    # ---------------------------------------------------------------------------
    if stmt_joined:
        # Collect xsrc_scale flags grouped by (ticker, col) → list of (panel_idx, k, raw)
        xsrc_by_ticker_col: dict[tuple, list[tuple]] = defaultdict(list)
        for f in flags:
            if f["flag"] == "xsrc_scale":
                raw_v = f["value"]
                rep_v = f["repair"]
                if raw_v != 0:
                    k_f = round(np.log10(abs(rep_v) / abs(raw_v)))
                    if k_f in XSRC_KS:
                        xsrc_by_ticker_col[(f["ticker"], f["col"])].append(
                            (f["index"], k_f, raw_v)
                        )

        for (ticker_c, col_c), xsrc_entries in xsrc_by_ticker_col.items():
            if col_c not in CLASS_A:
                continue  # cohort only for Class A (same anchor logic)

            # Find the dominant k (must have >= 2 flags at same k)
            k_counts: dict[int, int] = {}
            for _, k_e, _ in xsrc_entries:
                k_counts[k_e] = k_counts.get(k_e, 0) + 1
            dominant_k = max(k_counts, key=lambda k: k_counts[k])
            if k_counts[dominant_k] < 2:
                continue

            power = 10.0 ** dominant_k

            # Get the xsrc-flagged panel indices at the dominant k
            flagged_indices = {idx_e for idx_e, k_e, _ in xsrc_entries
                               if k_e == dominant_k}
            # Get one representative raw to define "same scale regime"
            flagged_raws = [abs(raw_e)
                            for idx_e, k_e, raw_e in xsrc_entries
                            if k_e == dominant_k]

            # Build the nonzero-value sequence for this (ticker, col)
            g_t = panel[panel["ticker"] == ticker_c].sort_values("fy")
            if col_c not in g_t.columns:
                continue
            vals_c = pd.to_numeric(g_t[col_c], errors="coerce").to_numpy(dtype=float)
            idx_c = g_t.index.to_numpy()
            nz_positions = [i for i, v in enumerate(vals_c)
                            if np.isfinite(v) and v != 0.0]

            # Mark which positions in nz_positions are xsrc-flagged
            flagged_pos = {i for i, pi in enumerate(nz_positions)
                           if idx_c[pi] in flagged_indices}

            # Transitively expand: a position is "in the cohort block" if it is
            # reachable from a flagged position by stepping to adjacent positions
            # (in the nz sequence) that are xsrc-flagged.  Then the boundary
            # positions adjacent to the block (one step outside) are candidates.
            if not flagged_pos:
                continue
            # BFS/flood-fill the flagged-only interior
            interior: set[int] = set()
            queue = list(flagged_pos)
            while queue:
                p0 = queue.pop()
                if p0 in interior:
                    continue
                interior.add(p0)
                for nb in (p0 - 1, p0 + 1):
                    if 0 <= nb < len(nz_positions) and nb in flagged_pos \
                            and nb not in interior:
                        queue.append(nb)

            # Candidates: positions adjacent to the interior but not themselves flagged
            candidates: list[int] = []
            for p0 in interior:
                for nb in (p0 - 1, p0 + 1):
                    if (0 <= nb < len(nz_positions)
                            and nb not in interior
                            and nb not in flagged_pos):
                        candidates.append(nb)

            # Get statement values for this (ticker, col)
            st_series = stmt_joined.get(col_c)

            # Get anchor arrays for this ticker
            rev_c = pd.to_numeric(g_t.get("revenue", pd.Series(dtype=float)),
                                  errors="coerce").to_numpy(dtype=float)
            ast_c = pd.to_numeric(g_t.get("assets", pd.Series(dtype=float)),
                                  errors="coerce").to_numpy(dtype=float)

            for cpos in candidates:
                pi = nz_positions[cpos]
                panel_idx = idx_c[pi]
                raw = vals_c[pi]

                # Already protected or flagged by another class — skip
                if ((panel_idx, col_c) in protected
                        or (panel_idx, col_c) in xsrc_flagged):
                    continue

                # Condition 1: statements must be PRESENT and scale-consistent —
                # |st| / |raw| within [power / COHORT_ST_BAND, power * COHORT_ST_BAND],
                # i.e. the statements value is within 1.25× of 10^k of raw.
                # This covers fact-variant splits (attributable-to-common vs
                # total incl. NCI/preferred) where the two values diverge
                # 5–30 %, not ~1000×.  A statements value outside this band
                # (plain disagreement at ≥1.26× off, e.g. 50×) keeps the row
                # from being cohort-flagged.  A row with NO statements value is
                # never cohort-flagged: without cross-source corroboration the
                # remaining gates cannot distinguish a mis-scaled fact from a
                # genuine near-breakeven year in the artifact's magnitude
                # regime (a real $3M impairment year on a $25B-revenue filer
                # passes every magnitude gate) — opus red-team finding M1.
                sv = (st_series.at[panel_idx]
                      if st_series is not None and panel_idx in st_series.index
                      else np.nan)
                if not (np.isfinite(sv) and sv != 0):
                    continue
                st_ratio = abs(sv) / abs(raw)
                if not (power / COHORT_ST_BAND <= st_ratio <= power * COHORT_ST_BAND):
                    # statements has a value at a plainly different scale
                    # — not a cohort candidate
                    continue

                # Condition 2: |raw| / anchor < ABSURD_SHARE
                # Anchor: revenue if finite/nonzero, else assets
                rev_val = rev_c[pi] if pi < len(rev_c) else np.nan
                ast_val = ast_c[pi] if pi < len(ast_c) else np.nan
                if col_c == "revenue":
                    anchor_val = ast_val
                else:
                    anchor_val = (rev_val
                                  if np.isfinite(rev_val) and rev_val != 0
                                  else ast_val)
                if not (np.isfinite(anchor_val) and anchor_val != 0):
                    continue
                if abs(raw) / abs(anchor_val) >= ABSURD_SHARE:
                    continue

                # Condition 3: raw is in same scale regime as confirmed rows
                # (|raw| within 100x of the nearest flagged raw)
                min_ratio_to_flagged = min(
                    _ratio(abs(raw), fr) for fr in flagged_raws
                )
                if not np.isfinite(min_ratio_to_flagged) or min_ratio_to_flagged > 100.0:
                    continue

                # Condition 4: scaled plausibility [1e-4, 0.6]
                scaled_share = abs(raw) * power / abs(anchor_val)
                if not (1e-4 <= scaled_share <= 0.6):
                    continue

                # All conditions met — flag as xsrc_cohort
                n_confirmed = k_counts[dominant_k]
                flags.append({
                    "index": panel_idx,
                    "ticker": ticker_c,
                    "fy": int(panel.at[panel_idx, "fy"]),
                    "col": col_c,
                    "flag": "xsrc_cohort",
                    "value": float(raw),
                    "repair": float(raw) * power,
                    "note": (f"x1e{dominant_k} cohort of {n_confirmed} xsrc rows"),
                })
                xsrc_flagged.add((panel_idx, col_c))

    # ---------------------------------------------------------------------------
    # Lane 2: segment / flank
    # ---------------------------------------------------------------------------
    for ticker, g in panel.groupby("ticker"):
        g = g.sort_values("fy")
        idx_arr = g.index.to_numpy()
        fy_arr = g["fy"].to_numpy()

        # Build per-column value arrays and anchor arrays
        anchor_arrs: dict[str, np.ndarray] = {}
        for ac in ("revenue", "cfo", "assets"):
            if ac in g.columns:
                anchor_arrs[ac] = pd.to_numeric(g[ac], errors="coerce").to_numpy(dtype=float)
            else:
                anchor_arrs[ac] = np.full(len(g), np.nan)

        for col in active_cols:
            vals = pd.to_numeric(g[col], errors="coerce").to_numpy(dtype=float)
            segs = _segments_nonzero(vals)
            if len(segs) < 2:
                continue   # need at least two segments for a flank comparison

            # A segment is "clean" when none of its rows was xsrc-flagged in the
            # current round.  PROTECTED rows (agreeing with statements) count as
            # clean flanks — they are accurate values, just shielded from the
            # flank lane's own flagging.
            def _seg_clean(seg):
                return all((idx_arr[p], col) not in xsrc_flagged
                           for p in range(seg[0], seg[1] + 1))

            def _clean_left(si):
                return next((segs[j] for j in range(si - 1, -1, -1)
                             if _seg_clean(segs[j])), None)

            def _clean_right(si):
                return next((segs[j] for j in range(si + 1, len(segs))
                             if _seg_clean(segs[j])), None)

            is_class_b = col in CLASS_B

            for si, seg in enumerate(segs):
                lo, hi, med = seg
                seg_len = hi - lo + 1   # count of nonzero positions in segment

                # Skip if any row in this segment is already xsrc-flagged or
                # xsrc-protected for this specific column.
                if any((idx_arr[p], col) in xsrc_flagged
                       or (idx_arr[p], col) in protected
                       for p in range(lo, hi + 1)):
                    continue

                lg = _clean_left(si)
                rg = _clean_right(si)

                # Class B: interior only (both flanks required)
                if is_class_b and (lg is None or rg is None):
                    continue

                if lg is None and rg is None:
                    continue

                # --- share-absurdity check ---
                # Candidate segment median share = |med|/anchor
                anc_cand = _seg_anchor(col, vals, anchor_arrs, lo, hi)
                if anc_cand is None:
                    continue   # no anchor available — cannot assess
                cand_share = abs(med) / anc_cand

                if cand_share >= ABSURD_SHARE:
                    continue   # not absurdly small — not an artifact by this lane

                # Clean flank median share must be >> candidate
                flank_shares: list[float] = []
                for flk in (lg, rg):
                    if flk is None:
                        continue
                    anc_flk = _seg_anchor(col, vals, anchor_arrs, flk[0], flk[1])
                    if anc_flk is not None:
                        flank_shares.append(abs(flk[2]) / anc_flk)
                if not flank_shares:
                    continue
                max_flank_share = max(flank_shares)
                if max_flank_share < SHARE_SEP * cand_share:
                    continue   # flanks not clearly in a different league

                # --- raw break check ---
                # Compare segment adjacent row to adjacent clean-flank row
                flank_breaks: list[float] = []
                if lg is not None:
                    r = _ratio(vals[lo], vals[lg[1]])
                    if np.isfinite(r):
                        flank_breaks.append(r)
                if rg is not None:
                    r = _ratio(vals[hi], vals[rg[0]])
                    if np.isfinite(r):
                        flank_breaks.append(r)
                if not flank_breaks or min(flank_breaks) < MIN_BREAK:
                    continue   # not strongly enough broken

                # Suspect threshold: high break, will try snap below
                is_suspect = min(flank_breaks) >= SUSPECTS_MIN_BREAK

                # --- scale snap ---
                found_k: int | None = None
                for k in FLANK_KS:
                    power = 10.0 ** k

                    tight_ok = False
                    loose_ok = True
                    sign_ok_tight = True

                    # Check against left flank
                    if lg is not None:
                        adj_raw = vals[lo]
                        adj_scaled = adj_raw * power
                        adj_clean = vals[lg[1]]
                        r_tight = _ratio(adj_scaled, adj_clean)
                        if abs(adj_raw) >= RAW_ABSURD:
                            # sign must match
                            if not _same_sign(adj_scaled, adj_clean):
                                sign_ok_tight = False
                        else:
                            # waive sign check for absurdly small raw values
                            pass
                        if np.isfinite(r_tight) and r_tight <= TIGHT_ADJ and sign_ok_tight:
                            tight_ok = True
                        # All flank rows within LOOSE_ALL
                        for p in range(lo, hi + 1):
                            r_loose = _ratio(vals[p] * power, adj_clean)
                            if not (np.isfinite(r_loose) and r_loose <= LOOSE_ALL):
                                loose_ok = False
                                break
                    if not loose_ok:
                        continue

                    # Check against right flank
                    if rg is not None:
                        adj_raw = vals[hi]
                        adj_scaled = adj_raw * power
                        adj_clean = vals[rg[0]]
                        r_tight_r = _ratio(adj_scaled, adj_clean)
                        sign_ok_r = True
                        if abs(adj_raw) >= RAW_ABSURD:
                            if not _same_sign(adj_scaled, adj_clean):
                                sign_ok_r = False
                        else:
                            pass   # waive sign
                        if np.isfinite(r_tight_r) and r_tight_r <= TIGHT_ADJ and sign_ok_r:
                            tight_ok = True
                        # All flank rows within LOOSE_ALL
                        for p in range(lo, hi + 1):
                            r_loose = _ratio(vals[p] * power, adj_clean)
                            if not (np.isfinite(r_loose) and r_loose <= LOOSE_ALL):
                                loose_ok = False
                                break
                    if not loose_ok:
                        continue

                    if not tight_ok:
                        continue   # no flank snapped tightly

                    # Class B: BOTH flanks must snap tightly
                    if is_class_b:
                        tight_left = False
                        tight_right = False
                        if lg is not None:
                            adj_raw = vals[lo]
                            adj_scaled = adj_raw * power
                            adj_clean = vals[lg[1]]
                            r_tl = _ratio(adj_scaled, adj_clean)
                            if (abs(adj_raw) < RAW_ABSURD
                                    or _same_sign(adj_scaled, adj_clean)):
                                if np.isfinite(r_tl) and r_tl <= TIGHT_ADJ:
                                    tight_left = True
                        if rg is not None:
                            adj_raw = vals[hi]
                            adj_scaled = adj_raw * power
                            adj_clean = vals[rg[0]]
                            r_tr = _ratio(adj_scaled, adj_clean)
                            if (abs(adj_raw) < RAW_ABSURD
                                    or _same_sign(adj_scaled, adj_clean)):
                                if np.isfinite(r_tr) and r_tr <= TIGHT_ADJ:
                                    tight_right = True
                        if not (tight_left and tight_right):
                            continue

                    # --- anchor continuity ---
                    anc_ok = True
                    if lg is not None and lo > 0:
                        if not _anchor_cont_ok(col, anchor_arrs, lg[1], lo):
                            anc_ok = False
                    if rg is not None and hi < len(vals) - 1:
                        if not _anchor_cont_ok(col, anchor_arrs, hi, rg[0]):
                            anc_ok = False
                    if not anc_ok:
                        continue

                    # --- margin coherence (Class A only) ---
                    if not is_class_b:
                        margin_ok = True
                        for flk, adj_pos in ((lg, lo), (rg, hi)):
                            if flk is None:
                                continue
                            flk_adj_pos = flk[1] if flk is lg else flk[0]
                            # anchor at the clean flank's adjacent position
                            anc_fl = _seg_anchor(col, vals, anchor_arrs,
                                                 flk_adj_pos, flk_adj_pos)
                            # anchor at the segment adjacent position
                            anc_seg = _seg_anchor(col, vals, anchor_arrs,
                                                  adj_pos, adj_pos)
                            if anc_fl is None or anc_seg is None:
                                continue
                            clean_share = (abs(vals[flk_adj_pos]) / anc_fl
                                           if anc_fl > 0 else np.nan)
                            scaled_share = (abs(vals[adj_pos] * power) / anc_seg
                                            if anc_seg > 0 else np.nan)
                            if not (np.isfinite(clean_share) and np.isfinite(scaled_share)):
                                continue
                            r_margin = _ratio(scaled_share, clean_share)
                            if np.isfinite(r_margin) and r_margin > MARGIN_COH:
                                margin_ok = False
                                break
                        if not margin_ok:
                            continue

                    found_k = k
                    break

                if found_k is not None:
                    for p in range(lo, hi + 1):
                        v = vals[p]
                        if not (np.isfinite(v) and v != 0):
                            continue
                        flags.append({
                            "index": int(idx_arr[p]),
                            "ticker": str(ticker),
                            "fy": int(fy_arr[p]),
                            "col": col,
                            "flag": "flank_scale",
                            "value": float(v),
                            "repair": float(v) * (10.0 ** found_k),
                            "note": f"x1e{found_k} flank",
                        })
                elif is_suspect:
                    _flank_suspects.append({
                        "ticker": str(ticker),
                        "fy_lo": int(fy_arr[lo]),
                        "fy_hi": int(fy_arr[hi]),
                        "col": col,
                        "med": float(med),
                    })

    cols = ["index", "ticker", "fy", "col", "flag", "value", "repair", "note"]
    result = pd.DataFrame(flags, columns=cols)
    # Attach auxiliary lists as attributes for apply_flow_quality to harvest
    result.attrs["_xsrc_disagree"] = _xsrc_disagree
    result.attrs["_flank_suspects"] = _flank_suspects
    return result


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
def apply_flow_quality(
    panel: pd.DataFrame,
    statements: pd.DataFrame | None = None,
    max_rounds: int = 6,
) -> tuple[pd.DataFrame, dict]:
    """Return (panel copy with flow values repaired, audit dict).

    Adds sparse raw columns {col}_raw for each FLOW_COLS column present plus
    ni_prior_raw; values are NaN except on flagged/mirrored rows (sparse
    convention — differs from the dense shares_raw in edgar_share_quality for
    column-count economy: 7 flow columns × dense population = 22014 × 7 non-NaN
    cells vs. the 100-200 rows that are actually repaired).

    Adds string column `flow_flag` (None when no flag; ";"-joined tokens like
    "ni:xsrc_scale:x1e3", "dividends:flank_scale:x1e3", "ni_prior:mirror").

    Fixed-point loop: a repair changes what the flank lane sees on neighbouring
    rows (VC ni fy2021 = 50 only becomes flaggable after fy2022-25 are xsrc-
    repaired; ×1e6 snaps cleanly once the right flank is corrected).  Converges
    in 2-3 rounds; max_rounds is a runaway backstop.

    Idempotency: re-applying to a healed panel finds 0 new flags (repaired values
    are continuous; xsrc ratios become ~1 → protected; flank shares rise above
    ABSURD_SHARE).

    Audit dict keys: applied, rows_flagged, tickers_flagged, by_flag, repaired,
    nulled (always 0), mirrors, rows, xsrc_disagreements, flank_suspects.
    """
    out = panel.copy()

    # Initialise sparse raw columns and flow_flag
    for c in FLOW_COLS:
        raw_col = f"{c}_raw"
        if raw_col not in out.columns:
            out[raw_col] = float("nan")
    if "ni_prior_raw" not in out.columns:
        out["ni_prior_raw"] = float("nan")
    if "flow_flag" not in out.columns:
        out["flow_flag"] = None

    all_found: list[pd.DataFrame] = []
    all_xsrc_disagree: list[dict] = []
    all_flank_suspects: list[dict] = []

    for _round in range(max_rounds):
        found = detect(out, statements=statements)
        all_xsrc_disagree.extend(found.attrs.get("_xsrc_disagree", []))
        all_flank_suspects.extend(found.attrs.get("_flank_suspects", []))
        if found.empty:
            break
        for _, f in found.iterrows():
            i = f["index"]
            col = f["col"]
            raw_col = f"{col}_raw"
            # Preserve original only on first flag (idempotency: second run finds
            # nothing new, so this branch won't overwrite a prior raw)
            if pd.isna(out.at[i, raw_col]):
                out.at[i, raw_col] = out.at[i, col]
            out.at[i, col] = f["repair"]
            # Append token to flow_flag
            token = f"{col}:{f['flag']}:{f['note'].split()[0]}"
            existing = out.at[i, "flow_flag"]
            out.at[i, "flow_flag"] = token if (existing is None or existing != existing) \
                else f"{existing};{token}"
        all_found.append(found)
    else:
        log.warning("flow_quality: no fixed point after %d rounds", max_rounds)

    # Deduplicate across rounds (keep last = most-recent repair)
    found_all = (pd.concat(all_found, ignore_index=True)
                 .drop_duplicates(subset=["index", "col"], keep="last")
                 if all_found
                 else pd.DataFrame(columns=["index", "ticker", "fy", "col",
                                            "flag", "value", "repair", "note"]))

    # --- ni_prior mirroring ---
    mirrors = 0
    if "ni_prior" in out.columns and len(found_all):
        ni_repairs = found_all[found_all["col"] == "ni"][
            ["ticker", "fy", "value", "repair"]].copy()
        for _, row in ni_repairs.iterrows():
            t, fy_ni, raw_ni, rep_ni = row["ticker"], row["fy"], row["value"], row["repair"]
            # Find the (ticker, fy+1) row whose ni_prior == raw_ni (within 1e-6 rel tol)
            mask = (out["ticker"] == t) & (out["fy"] == fy_ni + 1)
            for idx2 in out.index[mask]:
                nip = out.at[idx2, "ni_prior"]
                if not np.isfinite(nip):
                    continue
                if abs(nip - raw_ni) <= 1e-6 * max(abs(raw_ni), 1.0):
                    if pd.isna(out.at[idx2, "ni_prior_raw"]):
                        out.at[idx2, "ni_prior_raw"] = nip
                    out.at[idx2, "ni_prior"] = rep_ni
                    token = "ni_prior:mirror"
                    existing = out.at[idx2, "flow_flag"]
                    out.at[idx2, "flow_flag"] = (
                        token if (existing is None or existing != existing)
                        else f"{existing};{token}")
                    mirrors += 1

    # Deduplicate auxiliary lists (across rounds)
    seen_disagree: set[tuple] = set()
    xsrc_disagree_dedup: list[dict] = []
    for d in all_xsrc_disagree:
        key = (d["ticker"], d["fy"], d["col"])
        if key not in seen_disagree:
            seen_disagree.add(key)
            xsrc_disagree_dedup.append(d)

    seen_suspects: set[tuple] = set()
    flank_suspects_dedup: list[dict] = []
    for d in all_flank_suspects:
        key = (d["ticker"], d["fy_lo"], d["fy_hi"], d["col"])
        if key not in seen_suspects:
            seen_suspects.add(key)
            flank_suspects_dedup.append(d)

    by_flag: dict[str, int] = {}
    if len(found_all):
        for _, row in found_all.iterrows():
            key = f"{row['col']}:{row['flag']}"
            by_flag[key] = by_flag.get(key, 0) + 1

    audit = {
        "applied": datetime.now(timezone.utc).isoformat(),
        "rows_flagged": int(len(found_all)),
        "tickers_flagged": int(found_all["ticker"].nunique()) if len(found_all) else 0,
        "by_flag": by_flag,
        "repaired": int(len(found_all)),   # all detections have a confident repair
        "nulled": 0,                        # v1: no null class (see module docstring)
        "mirrors": mirrors,
        "rows": [
            {"ticker": r["ticker"], "fy": r["fy"], "col": r["col"],
             "flag": r["flag"],
             "raw": float(r["value"]),
             "repair": float(r["repair"]),
             "note": r["note"]}
            for _, r in found_all.iterrows()
        ],
        "xsrc_disagreements": xsrc_disagree_dedup,
        "flank_suspects": flank_suspects_dedup,
    }

    if len(found_all):
        log.info(
            "flow_quality: %d rows on %d tickers (%s) — %d repaired, %d mirrors",
            audit["rows_flagged"], audit["tickers_flagged"],
            audit["by_flag"], audit["repaired"], mirrors,
        )
    return out, audit
