"""Stock-column unit-artifact detector + PIT-honest repair for the EDGAR panel.

The frames-API scan in collectors/edgar.py occasionally lands on a fact stored in
the wrong unit for balance-sheet stock line items.  The two common signatures are:

  ×1e3 low: the filer's assets (or similar) fact is in thousands rather than
  units — ATO fy2010 assets = 7.221623e6 when the real value is ~$7.2B
  (Atmos Energy).  Scale factor ×1e3 restores the row.

  ×1e6 low: the fact is in millions — SNEX fy2018 assets = 8710.5 when the
  real value is ~$8.71B (StoneX).  Scale ×1e6 restores.

Both defects corrupt PIT equity factors (book value, leverage, etc.) on every
backtest rebalance that touches the artifact row.

Scope
-----
STOCK_COLS (3 columns).  Class A (1, assets only — never legitimately near-zero
or negative for a real operating filer): assets.  Class B (2, legitimately
lumpy/near-zero): equity (CAN go negative or near-zero — pre-IPO deficits,
buyback-driven negative book), debt_lt (legitimately near-zero — un-levered
periods, converts).

Out of scope: interest_exp, capex (flow/statements-lane provenance columns).

Detection lanes
---------------
Lane 1 — cross-source (xsrc), all three columns
  For each panel row, compare the panel value to the same (ticker, fy) value in
  statements.parquet.  When both are finite, nonzero, SAME SIGN, and
  |st| / |panel| is within XSRC_TOL of 10^k for k ∈ XSRC_KS (k > 0 only — panel
  is always the small side, by construction of the artifact), AND the panel raw
  is small vs the small-side belt anchor (for assets: revenue; for equity/debt_lt:
  same-row assets, falling back to revenue), the row is flagged xsrc_scale and
  repaired = panel_value × 10^k.

  NOTE: as of the current panel (2026-07-10), statements coverage for stock cols
  is fy2015+ only, and the three known artifacts (ATO fy2010, GNRC fy2016,
  SNEX fy2018) all predate or are outside that coverage.  The xsrc lane yields
  ZERO hits today but ships for future nightly re-collections and marks PROTECTED
  rows (statements ≈ panel within XSRC_CLEAN same sign).

  BGC-class anti-pattern: statements is the SMALL side (k would be negative) →
  excluded by the k>0 requirement → appears in xsrc_disagreements, no mutation.

  PROTECTED: |st|/|panel| within [1/XSRC_CLEAN, XSRC_CLEAN] same sign → the
  flank lane cannot flag this row×col regardless of segmentation.

Lane 1b — cohort (xsrc_cohort), all columns
  Applied after the xsrc pass.  For each (ticker, col) with >= 2 xsrc_scale
  flags at the same k, flag unflagged nonzero rows that are CONTIGUOUS (in the
  nonzero-value sequence) with the flagged rows — provided statements is present
  AND scale-consistent within COHORT_ST_BAND=1.25 of 10^k.  Statements-absent
  rows are NEVER cohort-flagged.  See edgar_flow_quality.py for full rationale.

Lane 2 — segment/flank (flank), all 3 columns
  Per (ticker, col): segment the nonzero finite values at ≥ SEG_JUMP consecutive-
  move ratio.

  DESIGN DECISION — interior-only for ALL THREE columns (differs from the flow
  module, where only Class B is interior-only):
    Stock balance-sheet items are far smoother than flow items; legitimate
    leading or trailing level changes DO occur and are indistinguishable from
    unit artifacts without additional evidence.  Census findings that led to
    this rule:
      OTIS fy2019 debt_lt: leading small segment (5e6) before an IPO-era
        step-up to 5.262B onward — perfectly interior-shaped but the leading
        context is an IPO capital restructuring, not an artifact.
      OGS fy2012 debt_lt: leading small segment before an M&A step-up.
      IDCC fy2011 debt_lt: leading small segment before converts issuance.
      RNG fy2014-15 equity: leading tiny negative equity from pre-IPO
        deficit — the company grew into positive book later.
      MDT fy2014 assets: leading-edge junk fact (assets=46000 before a
        ~$100B balance sheet) — NULLED by Lane 3; no ×10^k restores a
        plausible value.
      FTI fy2015 assets=equity=74100: same junk class, NULLED by Lane 3.
      MIR fy2019 assets=5000: same class, NULLED by Lane 3.
    Every confirmed repaired artifact (ATO fy2010, GNRC fy2016, SNEX fy2018)
    is an INTERIOR segment — both flanking clean segments are present.
    Leading/trailing segments that pass a break ≥ SUSPECTS_MIN_BREAK=500×
    go to flank_suspects (no mutation).

  Snap test for BOTH flanks present (interior): try k ∈ FLANK_KS.
    For Class A (assets): tight same-sign snap (TIGHT_ADJ) on at least one
      present flank AND every present flank within LOOSE_ALL same sign.
    For Class B (equity, debt_lt): THREE-GATE test (see below).
    NO sign-waiver for any stock column (no RAW_ABSURD class): a tiny negative
    equity is a real deficit, a tiny positive debt_lt is a real un-levered period.
    TIGHT_ADJ=1.5 (tighter than the flow module's 1.8) — confirmed cases land
    within 1.28× of clean flanks (ATO ×1e3: 1.20/1.22; SNEX ×1e6: 1.28/1.16).

  CLASS-B THREE-GATE design (equity, debt_lt):
  -----------------------------------------------
  The motivation is the recap/de-lever false-positive class: a real transient
  near-zero equity (recap / full de-lever) whose value coincidentally lands on a
  10^k multiple of both flanks (e.g. equity 2e9 → 2e6 → 2e9, ratio 1.00/1.00)
  would be falsely ×1e3'd under the old TIGHT_ADJ=1.5 single-gate rule.  The
  AMD fy2021 debt_lt=1e6 case (scaled ratios ~3.0/2.5) is rejected by the break
  belt today but landed within only ~2× of TIGHT_ADJ, motivating tighter defense.

  Gates checked in order for every Class-B interior snap candidate (after the
  Class A snap has already passed the standard tight test for assets in this pass):

    Gate 0 — PROTECTED (unchanged, supremely conservative):
      If statements ≈ panel within XSRC_CLEAN=1.5 same sign (xsrc lane), the row
      is in the `protected` set and is never reached here.

    Gate 1 — Same-row Class-A corroboration:
      If the SAME (ticker, fy) row's assets was repaired at the SAME k in the
      current flank pass (assets is always processed before equity/debt_lt in
      active_cols order), the Class-B snap is corroborated — same filing, same
      mis-scaled unit → repair at the existing TIGHT_ADJ=1.5 band.
      This covers ATO fy2010: assets ×1e3 is confirmed first, then equity and
      debt_lt use Gate 1 with TIGHT_ADJ.
      Audit note: "corr": "same_row_assets" is recorded in the flag.

    Gate 2 — Standalone Class B (no same-row corroboration):
      Covers GNRC fy2016 debt_lt (assets and equity are clean, only debt_lt is
      off-scale).  Requires ALL of:
        (a) STRICT both-flank snap: scaled vs BOTH adjacent flanks within
            CLASSB_SOLO_TIGHT=1.25, same sign.  GNRC lands 1.018/1.122 — passes.
            A real recap trough must coincidentally land within ±25% of flank×10^-k
            on BOTH sides, a ~3× smaller accident window than the old 1.5.
        (b) Statements evidence, when present:
            - absent (row missing or NaN — the entire pre-2015 region, and
              GNRC fy2016 debt_lt which statements does not carry): geometric
              path allowed; proceed.
            - |st|/|raw| within [10^k/1.25, 10^k×1.25]: corroborates → repair.
            - |st|/|raw| within [1/1.5, 1.5]: PROTECTED territory (Gate 0 safety
              net) → no repair.
            - any other ratio: disagreement → no repair; route to flank_suspects
              with the statements value recorded.
        (c) Anchor presence: each used boundary must have at least one anchor
            (per FIX 2, see _anchor_cont_ok description below) — all-absent → reject.

  Known residual under Gate 2:
    A statements-absent interior segment with a perfect both-flank strict snap
    (ratio ≤ 1.25 on both sides) and good anchors WILL be repaired even if the
    true underlying event is a real recap/de-lever.  The accident window is small
    (±25% both sides simultaneously) and *_raw preservation makes any false repair
    reversible and auditable from the committed panel.

  Break belt: candidate segment's median must be ≥ MIN_BREAK=100× below BOTH
  flank medians (raw-vs-flank abs ratio).

  ABSURD_SHARE anchor: for assets, use revenue as anchor; for equity/debt_lt,
  use assets as anchor (same-row).  Candidate is skipped if no anchor is present.
  No ABSURD_SHARE/SHARE_SEP filter is applied (the break belt and snap together
  are sufficient; the ABSURD_SHARE anchor-share test is NOT ported from the flow
  module — for stock cols the natural anchor is often NaN in artifact years:
  ATO fy2010 has revenue=NaN, and even |assets_artifact|/|ni| ≈ 3.5e-2 would
  fail a 1e-3 belt while being a genuine artifact).

  Anchor continuity at each used boundary: among {revenue, ni, cfo, shares} ∪
  (STOCK_COLS minus col-under-test) present on both sides, at least one within
  ANCHOR_CONT=2.5 and none ≥ ANCHOR_BLOWUP=100.0.
    WHY include ni and shares: ATO fy2010 has revenue=NaN; ni and shares are
    present and continuous across the boundary — the anchor set MUST include
    them or ATO fails continuity.
    CRITICAL: when ALL anchors are absent on either side, the check REJECTS
    (returns False) — this prevents spurious repairs on entirely context-free rows.

  No ABSURD_SHARE / SHARE_SEP requirement (see above).
  No margin-coherence concept for stock columns.

Lane 3 — leading-edge junk-fact NULL (junk_null)
  Applied inside the per-ticker flank loop, BEFORE the flank_suspects append,
  for LEADING segments only (lg is None, si == 0, rg is not None).  Trailing
  and interior segments are never nulled by this lane.

  The junk class (MDT fy2014, FTI fy2015, MIR fy2019) is characterised by
  balance-sheet facts from a SHELL or PREDECESSOR ENTITY embedded in a filing
  that also carries REAL FLOW facts for the operating entity.  The junk assets
  value is minuscule compared to the same-row revenue/ni/cfo, but no ×10^k snap
  can restore a plausible balance-sheet number — the artifact is not a unit error,
  it is a wrong fact.  The discipline mirrors collectors/edgar_share_quality.py:
  "NaN, never wrong."

  Detection (assets — Class A):
    1. Row break: _ratio(v, vals[rg[0]]) ≥ SUSPECTS_MIN_BREAK (500×).
    2. Same-row incoherence: anchor_max = max(|revenue|, |ni|, |cfo|) for
       finite nonzero values on the row; require at least one anchor present
       AND anchor_max / |assets| ≥ JUNK_ANCHOR_MULT (1000×).
       Calibration (census over all 51 flank_suspects, 2026-07-11): junk class
       ratios are 9,451× (FTI), 106,565× (MDT), 88,020× (MIR).  Largest REAL
       coherent tiny-asset row: CLSK fy2010 at 471× — the honest headroom to
       the 1000× threshold is only 2.1×, but the population gap between the
       largest real row (471×) and the smallest junk row (9,451×) is a clean
       ~20× with nothing in between.
       Anchors all-absent → NOT nulled (AHCO-class — no evidence; stays suspect).
    3. If both pass → append flag {flag:"junk_null", repair:nan} and record fy
       in _junk_null_fy (a per-ticker-per-col-pass set).

  Detection (equity, debt_lt — Class B):
    Require int(fy) in _junk_null_fy (same-row assets junk-nulled this pass).
    NO own-incoherence test for Class B — doing so would falsely kill real rows:
      AMCR fy2018 equity=130 with revenue=9.3B → incoherence 71.5M× (REAL equity;
        company had negative book before the spin-off, then a massive recapitalisation
        assigned this stub equity figure).
      DEA-class: similarly tiny equity vs revenue (REAL).
      OTIS fy2019 debt_lt=5e6 with revenue=13.1B → 2.62M× incoherence (REAL;
        IPO-era minimal debt before the capital structure was established).
      OGS, J, KNF debt_lt: same class.
    Class B is nulled ONLY when the same-row assets was already junk-nulled —
    that corroboration signal is the only safe trigger.

  Note on sign flips: _ratio is abs-based.  A sign flip (e.g. MIR fy2019
  equity=+4364 breaking against fy2020 equity=-9.795e7) does NOT block the null
  — the ratio is still ≥ 500×, so the per-row break check fires normally.

  Fully-nulled segments: when every nonzero row in a leading segment was junk-
  nulled, that segment is NOT appended to flank_suspects (a fully-nulled segment
  is no longer "suspect — no mutation").

Repair discipline (PIT-honest)
-------------------------------
Every repair is the row's OWN filed value ×10^k for k ∈ {3, 6}.  Statements is
EVIDENCE ONLY, never a repair source.  The null class (junk_null, see Lane 3
above) sets repair = NaN — cells where no confident PIT-legal repair exists are
nulled so downstream factors go NaN instead of wrong.  This mirrors the
edgar_share_quality.py discipline: "NaN, never wrong."
Originals preserved in assets_raw / equity_raw / debt_lt_raw (sparse: NaN except
on flagged/mirrored rows).  A string column `stock_flag` mirrors flow_flag format.

assets_prior mirroring
-----------------------
Many panel rows carry assets_prior = prior fiscal year's assets.  When assets is
repaired OR nulled at (ticker, fy), the (ticker, fy+1) row's assets_prior — when
present and equal to the raw assets within rel tol 1e-6 — is updated to the
repaired value (or NaN for junk_null) and recorded as "assets_prior:mirror" (for
repairs) or "assets_prior:null_mirror" (for junk_null nulls).  This prevents the
phantom artifact from persisting in the panel as a prior-year reference.

Handled by Lane 3 (formerly residuals)
---------------------------------------
- MDT fy2014 assets=46000 / equity=-3.6954e7: NULLED (junk_null).
  The fy2015 assets_prior=46000 is null-mirrored to NaN.
- FTI fy2015 assets=equity=74100: NULLED.
  The fy2016 assets_prior=74100 is null-mirrored to NaN.
- MIR fy2019 assets=5000 / equity=4364: NULLED.
  The fy2020 assets_prior=5000 is null-mirrored to NaN.

Known residuals (conservative by design)
-----------------------------------------
- Anchor-absent leading junk (AHCO-class, assets=310616 with all-NaN flow
  anchors): NOT nulled — no incoherence evidence; stays in flank_suspects.
- Interior junk and trailing junk: NOT nulled — the lane is leading-edge only.
  Within a leading segment every row is evaluated INDEPENDENTLY (per-row break
  + per-row incoherence), so a multi-row leading junk segment CAN null more
  than one fy — but each nulled row must carry its own evidence.
- OTIS/OGS/IDCC leading-edge debt_lt and RNG leading-edge equity: interior-only
  rule leaves them entirely unflagged (flank_suspects at most if break ≥ 500×).
  OTIS debt_lt=5e6 has large same-row assets/revenue but assets is clean (never
  nulled) → no corroboration → equity/debt_lt survive.
- CHTR equity sign flip (−4.6e7 → +4.014e10, abs ratio ~873): same-sign
  requirement rejects it — a negative equity flipping to a positive value is
  a real corporate event (debt paydown / earnings recovery), not a unit artifact.
- Statements-absent perfect-snap recap (equity 2e9 → 2e6 → 2e9, ratio 1.00/1.00):
  repaired under Gate 2 because the accident window is small and the repair is
  reversible via *_raw preservation.  See CLASS-B THREE-GATE design above.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# columns and constants
# ---------------------------------------------------------------------------
STOCK_COLS = ["assets", "equity", "debt_lt"]

CLASS_A = ["assets"]
CLASS_B = ["equity", "debt_lt"]

XSRC_KS = (3, 6)           # panel value ×10^k should equal the statements value
XSRC_TOL = 1.10            # ...within this multiplicative band
XSRC_CLEAN = 1.5           # panel≈statements within this = row PROTECTED from flank lane
# No PANEL_SHARE_MAX belt for stock xsrc (anchors vary; break + snap covers it)

SEG_JUMP = 30.0            # consecutive-FY abs-ratio that starts a new level segment
                           # (stocks are smoother than flows; 30x covers real restructurings)
FLANK_KS = (3, 6)
TIGHT_ADJ = 1.5            # scaled segment row ADJACENT to a clean flank must land within
                           # this, SAME SIGN.  Tighter than flow's 1.8 — confirmed cases
                           # land ≤1.28× (ATO ×1e3: 1.20/1.22; SNEX ×1e6: 1.28/1.16).
                           # No sign-waiver (RAW_ABSURD class absent for stock cols)
CLASSB_SOLO_TIGHT = 1.25  # stricter snap band for standalone Class-B (equity/debt_lt)
                           # with no same-row assets corroboration (Gate 2 of 3-gate design).
LOOSE_ALL = 4.0            # every present flank must land within this (abs) after scaling
ANCHOR_CONT = 2.5          # ≥1 of {revenue,ni,cfo,shares}∪(STOCK_COLS−col) continuous
                           # within this across each used boundary
ANCHOR_BLOWUP = 100.0      # ...and none of the present anchors breaks by this much
MIN_BREAK = 100.0          # belt: raw-vs-flank abs ratio floor (BOTH flanks)
SUSPECTS_MIN_BREAK = 500.0 # flank_suspects trigger: high break but no confident snap

JUNK_ANCHOR_MULT = 1000.0  # same-row flow anchor must exceed |assets| by this to call the
                           # assets fact junk.  Calibrated: junk class ≥ 9,451x (FTI; MDT
                           # 106,565x, MIR 88,020x); real tiny-asset shells ≤ 471x (CLSK
                           # fy2010).  Headroom real→threshold is 2.1x; the real→junk
                           # population gap is ~20x, empty.  Applies to ASSETS ONLY: equity/debt_lt
                           # are legitimately tiny against large anchors (AMCR fy2018
                           # equity=130 vs revenue 9.3B is REAL; OTIS fy2019 debt_lt=5e6 vs
                           # revenue 13.1B is REAL) — they null only via same-row-assets
                           # corroboration.
_JUNK_FLOW_ANCHORS = ("revenue", "ni", "cfo")   # dollar-flow anchors for the junk test

# Cohort lane tolerance band (same as flow module — see edgar_flow_quality.py)
COHORT_ST_BAND = 1.25

# Anchor set for continuity check.
# Base: {revenue, ni, cfo, shares}.  WHY not STOCK_COLS companions: when all
# three stock cols are simultaneously corrupted (ATO fy2010 has assets, equity,
# AND debt_lt all ×1e3 low), companion equity/debt_lt both show ~1000× blowup
# across the boundary and would falsely trigger ANCHOR_BLOWUP, rejecting a
# genuine artifact.  The base set is sufficient: ni (~$205M) and shares (~90M)
# are both present and continuous for ATO, confirming no real structural event.
_CONT_ANCHORS_BASE = ("revenue", "ni", "cfo", "shares")


# ---------------------------------------------------------------------------
# internal helpers (mirror edgar_flow_quality.py naming exactly)
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
    consecutive-pair moves.  Returns list of [lo, hi, median] in position space."""
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


def _anchor_cont_ok(col: str, anchors: dict[str, np.ndarray], lo_pos: int,
                    hi_pos: int) -> bool:
    """Anchor continuity check across a boundary (lo_pos, hi_pos are adjacent
    position indices in the full ticker array).

    Anchor set: {revenue, ni, cfo, shares} — see _CONT_ANCHORS_BASE comment for
    why STOCK_COLS companions are excluded.

    Returns True when the criteria are met (at least one anchor within ANCHOR_CONT
    and none at ANCHOR_BLOWUP).  Returns False when ALL anchors are absent on at
    least one side — all-absent means we have no evidence that the surrounding
    context is stable, so repair is rejected.  This is deliberately anti-conservative:
    a legitimate repair must have at least one observable anchor signal present."""
    checks: list[float] = []
    cands = list(_CONT_ANCHORS_BASE)
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
        return False   # no anchor on both sides — reject to avoid context-free repairs
    if any(r >= ANCHOR_BLOWUP for r in checks):
        return False
    return any(r <= ANCHOR_CONT for r in checks)


# ---------------------------------------------------------------------------
# core detector
# ---------------------------------------------------------------------------
def detect(panel: pd.DataFrame, statements: pd.DataFrame | None = None
           ) -> pd.DataFrame:
    """Scan the panel for stock-column unit artifacts.

    Returns a DataFrame with columns:
      [index, ticker, fy, col, flag, value, repair, note]

    statements=None → xsrc lane is skipped entirely.
    """
    need = {"ticker", "fy", "period_end"}
    missing_req = need - set(panel.columns)
    if missing_req:
        raise ValueError(f"panel missing required columns: {sorted(missing_req)}")
    if "assets" not in panel.columns:
        raise ValueError("panel missing required column: assets")

    active_cols = [c for c in STOCK_COLS if c in panel.columns]

    # Pre-join statements on (ticker, fy) for xsrc lane
    stmt_joined: dict[str, pd.Series] = {}   # col -> Series indexed by panel.index
    if statements is not None and not statements.empty:
        stmt_cols = [c for c in active_cols if c in statements.columns]
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
    _xsrc_disagree: list[dict] = []
    _flank_suspects: list[dict] = []

    # Protected set: (panel_index, col) → flank lane cannot flag this row×col
    protected: set[tuple] = set()

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

                # Already in agreement (PROTECTED — protect from flank)
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
                    # Significant disagreement at neither clean nor artifact scale
                    if ratio_raw > 2.0 or ratio_raw < 0.5:
                        _xsrc_disagree.append({
                            "ticker": panel.at[idx, "ticker"],
                            "fy": int(panel.at[idx, "fy"]),
                            "col": col,
                            "panel": float(pv),
                            "statements": float(sv),
                        })
                    continue

                # Small-side belt: panel raw must be small vs same-row anchor.
                # assets → anchor = revenue; equity/debt_lt → anchor = assets
                # (fallback to revenue when assets absent or zero).
                ticker_row = panel.loc[idx]
                if col == "assets":
                    rev = float(ticker_row.get("revenue", np.nan))
                    anchor = rev if (np.isfinite(rev) and rev != 0) else np.nan
                else:
                    ast = float(ticker_row.get("assets", np.nan))
                    rev = float(ticker_row.get("revenue", np.nan))
                    anchor = (ast if (np.isfinite(ast) and ast != 0)
                              else rev if (np.isfinite(rev) and rev != 0)
                              else np.nan)

                if np.isfinite(anchor) and anchor != 0:
                    # Panel must be at least XSRC_TOL×10^k smaller than anchor
                    # (i.e. scaled value is in plausible range)
                    scaled = abs(pv) * (10.0 ** matched_k)
                    if scaled <= abs(anchor) * 0.01:
                        # implausibly small even after scaling → disagree
                        _xsrc_disagree.append({
                            "ticker": panel.at[idx, "ticker"],
                            "fy": int(panel.at[idx, "fy"]),
                            "col": col,
                            "panel": float(pv),
                            "statements": float(sv),
                        })
                        continue
                    # Raw panel must be clearly tiny vs anchor
                    if abs(pv) / abs(anchor) >= 0.5:
                        # not tiny — likely not an artifact
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

    # Build set of xsrc-flagged indices per col
    xsrc_flagged: set[tuple] = {(f["index"], f["col"]) for f in flags}

    # ---------------------------------------------------------------------------
    # Lane 1b: xsrc_cohort
    # ---------------------------------------------------------------------------
    if stmt_joined:
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
            k_counts: dict[int, int] = {}
            for _, k_e, _ in xsrc_entries:
                k_counts[k_e] = k_counts.get(k_e, 0) + 1
            dominant_k = max(k_counts, key=lambda k: k_counts[k])
            if k_counts[dominant_k] < 2:
                continue

            power = 10.0 ** dominant_k
            flagged_indices = {idx_e for idx_e, k_e, _ in xsrc_entries
                               if k_e == dominant_k}
            flagged_raws = [abs(raw_e)
                            for idx_e, k_e, raw_e in xsrc_entries
                            if k_e == dominant_k]

            g_t = panel[panel["ticker"] == ticker_c].sort_values("fy")
            if col_c not in g_t.columns:
                continue
            vals_c = pd.to_numeric(g_t[col_c], errors="coerce").to_numpy(dtype=float)
            idx_c = g_t.index.to_numpy()
            nz_positions = [i for i, v in enumerate(vals_c)
                            if np.isfinite(v) and v != 0.0]

            flagged_pos = {i for i, pi in enumerate(nz_positions)
                           if idx_c[pi] in flagged_indices}
            if not flagged_pos:
                continue

            # BFS flood-fill interior
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

            candidates: list[int] = []
            for p0 in interior:
                for nb in (p0 - 1, p0 + 1):
                    if (0 <= nb < len(nz_positions)
                            and nb not in interior
                            and nb not in flagged_pos):
                        candidates.append(nb)

            st_series = stmt_joined.get(col_c)
            ast_c = pd.to_numeric(g_t.get("assets", pd.Series(dtype=float)),
                                  errors="coerce").to_numpy(dtype=float)
            rev_c = pd.to_numeric(g_t.get("revenue", pd.Series(dtype=float)),
                                  errors="coerce").to_numpy(dtype=float)

            for cpos in candidates:
                pi = nz_positions[cpos]
                panel_idx = idx_c[pi]
                raw = vals_c[pi]

                if ((panel_idx, col_c) in protected
                        or (panel_idx, col_c) in xsrc_flagged):
                    continue

                # Condition 1: statements PRESENT and scale-consistent
                sv = (st_series.at[panel_idx]
                      if st_series is not None and panel_idx in st_series.index
                      else np.nan)
                if not (np.isfinite(sv) and sv != 0):
                    continue
                st_ratio = abs(sv) / abs(raw)
                if not (power / COHORT_ST_BAND <= st_ratio <= power * COHORT_ST_BAND):
                    continue

                # Condition 2: |raw| must be tiny vs anchor
                # assets → anchor = revenue; equity/debt_lt → anchor = assets
                if col_c == "assets":
                    rev_val = rev_c[pi] if pi < len(rev_c) else np.nan
                    anchor_val = rev_val if (np.isfinite(rev_val) and rev_val != 0) else np.nan
                else:
                    ast_val = ast_c[pi] if pi < len(ast_c) else np.nan
                    rev_val = rev_c[pi] if pi < len(rev_c) else np.nan
                    anchor_val = (ast_val if (np.isfinite(ast_val) and ast_val != 0)
                                  else rev_val if (np.isfinite(rev_val) and rev_val != 0)
                                  else np.nan)
                if not (np.isfinite(anchor_val) and anchor_val != 0):
                    continue
                if abs(raw) / abs(anchor_val) >= 0.5:
                    continue

                # Condition 3: raw in same scale regime (within 100x of confirmed raws)
                min_ratio_to_flagged = min(
                    _ratio(abs(raw), fr) for fr in flagged_raws
                )
                if not np.isfinite(min_ratio_to_flagged) or min_ratio_to_flagged > 100.0:
                    continue

                # Condition 4: scaled plausibility [1e-4, 1.5]
                scaled_share = abs(raw) * power / abs(anchor_val)
                if not (1e-4 <= scaled_share <= 1.5):
                    continue

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
    # Lane 2: segment / flank — interior only for ALL stock columns
    # ---------------------------------------------------------------------------
    for ticker, g in panel.groupby("ticker"):
        g = g.sort_values("fy")
        idx_arr = g.index.to_numpy()
        fy_arr = g["fy"].to_numpy()

        # Build anchor arrays (superset: all STOCK_COLS + flow anchors + ni + shares)
        anchor_arrs: dict[str, np.ndarray] = {}
        for ac in ("revenue", "ni", "cfo", "shares", "assets", "equity", "debt_lt"):
            if ac in g.columns:
                anchor_arrs[ac] = pd.to_numeric(g[ac], errors="coerce").to_numpy(dtype=float)
            else:
                anchor_arrs[ac] = np.full(len(g), np.nan)

        # Track assets repairs so Class-B Gate 1 can detect same-row
        # corroboration.  Key: (ticker, fy), value: k.  Seeded with this
        # ticker's xsrc/cohort assets repairs (same-filing evidence regardless
        # of which lane confirmed the mis-scale); flank-lane assets repairs are
        # added as they fire — assets is always first in active_cols
        # (["assets", "equity", "debt_lt"]).
        # CRASH GUARD: junk_null flags carry repair=NaN; np.log10(nan) raises
        # ValueError in round().  Guard: only seed from rows with finite repair.
        _flank_assets_k: dict[tuple[str, int], int] = {}
        for f in flags:
            if (f["col"] == "assets" and f["ticker"] == ticker
                    and f["value"] != 0 and np.isfinite(f["repair"])):
                k_f = round(np.log10(abs(f["repair"]) / abs(f["value"])))
                if k_f in XSRC_KS:
                    _flank_assets_k[(str(ticker), int(f["fy"]))] = k_f

        # Per-col, per-ticker registry of fiscal years whose ASSETS was junk-nulled
        # in this pass.  Reset for each (ticker, col) iteration below — but because
        # assets is always processed first (active_cols order preserves STOCK_COLS),
        # _junk_null_fy is populated by the assets pass and readable by equity/
        # debt_lt.  SAME-CALL requirement: corroboration only works within one
        # detect() call — active_cols order guarantees assets runs before the
        # Class-B cols for each ticker, so all co-row nulls resolve in the same
        # round.  Once assets is NaN, later rounds can no longer corroborate;
        # a Class-B junk value whose own segment only becomes eligible in a
        # LATER round would stay un-nulled (narrow window, none observed).
        _junk_null_fy: set[int] = set()

        for col in active_cols:
            vals = pd.to_numeric(g[col], errors="coerce").to_numpy(dtype=float)
            segs = _segments_nonzero(vals)
            if len(segs) < 2:
                continue

            is_class_b = col in CLASS_B

            def _seg_clean(seg):
                return all((idx_arr[p], col) not in xsrc_flagged
                           for p in range(seg[0], seg[1] + 1))

            def _clean_left(si):
                return next((segs[j] for j in range(si - 1, -1, -1)
                             if _seg_clean(segs[j])), None)

            def _clean_right(si):
                return next((segs[j] for j in range(si + 1, len(segs))
                             if _seg_clean(segs[j])), None)

            for si, seg in enumerate(segs):
                lo, hi, med = seg

                # Skip if any row is xsrc-flagged or xsrc-protected for this col
                if any((idx_arr[p], col) in xsrc_flagged
                       or (idx_arr[p], col) in protected
                       for p in range(lo, hi + 1)):
                    continue

                lg = _clean_left(si)
                rg = _clean_right(si)

                # INTERIOR-ONLY for all stock columns: both flanks required.
                # Leading segments also evaluated by Lane 3 (junk_null) below.
                if lg is None or rg is None:
                    # Check if it qualifies for flank_suspects
                    if lg is None and rg is None:
                        continue
                    flk = rg if lg is None else lg
                    adj_seg = vals[lo] if rg is not None else vals[hi]
                    adj_flk = flk[0] if rg is not None else flk[1]
                    brk = _ratio(adj_seg, vals[adj_flk])

                    # -----------------------------------------------------------
                    # Lane 3 — leading-edge junk-fact NULL (flag "junk_null")
                    # Applies ONLY to leading segments: lg is None, si == 0,
                    # rg is not None.  Trailing segments are never nulled.
                    # -----------------------------------------------------------
                    junk_nulled_rows: set[int] = set()   # positions nulled this seg
                    if lg is None and si == 0 and rg is not None:
                        for p in range(lo, hi + 1):
                            v = vals[p]
                            if not (np.isfinite(v) and v != 0):
                                continue

                            # Gate 1: per-row break ≥ SUSPECTS_MIN_BREAK
                            row_brk = _ratio(v, vals[rg[0]])
                            if not (np.isfinite(row_brk) and row_brk >= SUSPECTS_MIN_BREAK):
                                continue

                            if col == "assets":
                                # Gate 2 (assets only): same-row flow incoherence
                                anchor_max = 0.0
                                any_anchor = False
                                for ac in _JUNK_FLOW_ANCHORS:
                                    av = anchor_arrs.get(ac)
                                    if av is None:
                                        continue
                                    a_val = av[p]
                                    if np.isfinite(a_val) and a_val != 0:
                                        anchor_max = max(anchor_max, abs(a_val))
                                        any_anchor = True
                                if not any_anchor:
                                    # No flow anchor evidence — cannot call junk; stays suspect
                                    continue
                                if anchor_max / abs(v) < JUNK_ANCHOR_MULT:
                                    continue
                                # Junk assets confirmed
                                flags.append({
                                    "index": int(idx_arr[p]),
                                    "ticker": str(ticker),
                                    "fy": int(fy_arr[p]),
                                    "col": col,
                                    "flag": "junk_null",
                                    "value": float(v),
                                    "repair": float("nan"),
                                    "note": (f"null junk-fact leading-edge "
                                             f"(anchor {anchor_max / abs(v):.0f}x)"),
                                })
                                _junk_null_fy.add(int(fy_arr[p]))
                                junk_nulled_rows.add(p)

                            elif col in CLASS_B:
                                # Class B: only null if same-row assets was
                                # junk-nulled this pass (no own-incoherence test —
                                # see AMCR/DEA/OTIS counterexamples in docstring).
                                if int(fy_arr[p]) not in _junk_null_fy:
                                    continue
                                flags.append({
                                    "index": int(idx_arr[p]),
                                    "ticker": str(ticker),
                                    "fy": int(fy_arr[p]),
                                    "col": col,
                                    "flag": "junk_null",
                                    "value": float(v),
                                    "repair": float("nan"),
                                    "note": "null junk-fact leading-edge corr:same_row_assets",
                                })
                                junk_nulled_rows.add(p)

                    # Append to flank_suspects only if the segment has at least
                    # one nonzero row that was NOT junk-nulled (a fully-nulled
                    # segment is no longer "no mutation").
                    if np.isfinite(brk) and brk >= SUSPECTS_MIN_BREAK:
                        nz_in_seg = [p for p in range(lo, hi + 1)
                                     if np.isfinite(vals[p]) and vals[p] != 0]
                        if any(p not in junk_nulled_rows for p in nz_in_seg):
                            _flank_suspects.append({
                                "ticker": str(ticker),
                                "fy_lo": int(fy_arr[lo]),
                                "fy_hi": int(fy_arr[hi]),
                                "col": col,
                                "med": float(med),
                            })
                    continue

                # --- raw break check vs BOTH flanks ---
                r_left = _ratio(vals[lo], vals[lg[1]])
                r_right = _ratio(vals[hi], vals[rg[0]])
                if not (np.isfinite(r_left) and np.isfinite(r_right)):
                    continue
                if r_left < MIN_BREAK or r_right < MIN_BREAK:
                    continue   # must break from BOTH flanks by at least MIN_BREAK

                is_suspect = (r_left >= SUSPECTS_MIN_BREAK and r_right >= SUSPECTS_MIN_BREAK)

                # --- scale snap ---
                found_k: int | None = None
                corr_note: str = ""
                for k in FLANK_KS:
                    power = 10.0 ** k

                    # Compute both-flank snap ratios (needed for all classes)
                    adj_raw_l = vals[lo]
                    adj_scaled_l = adj_raw_l * power
                    adj_clean_l = vals[lg[1]]
                    if not (np.isfinite(adj_scaled_l) and np.isfinite(adj_clean_l)):
                        continue
                    if not _same_sign(adj_scaled_l, adj_clean_l):
                        continue   # no sign-waiver for stock columns
                    r_tight_l = _ratio(adj_scaled_l, adj_clean_l)

                    adj_raw_r = vals[hi]
                    adj_scaled_r = adj_raw_r * power
                    adj_clean_r = vals[rg[0]]
                    if not (np.isfinite(adj_scaled_r) and np.isfinite(adj_clean_r)):
                        continue
                    if not _same_sign(adj_scaled_r, adj_clean_r):
                        continue
                    r_tight_r = _ratio(adj_scaled_r, adj_clean_r)

                    if is_class_b:
                        # --------------------------------------------------
                        # CLASS-B three-gate logic (equity, debt_lt)
                        # --------------------------------------------------
                        # Gate 0: PROTECTED rows are already excluded above via
                        # the `protected` set — nothing to do here.

                        # Determine which tight band applies for this candidate.
                        # Gate 1: same-row Class-A corroboration (assets repaired
                        # at same k for any fy in this segment during this pass)?
                        corroborated = any(
                            _flank_assets_k.get((str(ticker), int(fy_arr[p]))) == k
                            for p in range(lo, hi + 1)
                        )
                        if corroborated:
                            # Gate 1: use the normal TIGHT_ADJ band (1.5)
                            tight_band = TIGHT_ADJ
                            _corr_note = "corr:same_row_assets"
                        else:
                            # Gate 2: standalone Class B — stricter band
                            tight_band = CLASSB_SOLO_TIGHT

                        # Both flanks must pass the applicable tight band
                        if not (np.isfinite(r_tight_l) and r_tight_l <= tight_band):
                            continue
                        if not (np.isfinite(r_tight_r) and r_tight_r <= tight_band):
                            continue

                        if not corroborated:
                            # Gate 2(b): statements evidence check (per segment row)
                            # For each row in the segment that has a finite nonzero
                            # statement value, classify the ratio.
                            st_series = stmt_joined.get(col)
                            stmt_gate_ok = True
                            for p in range(lo, hi + 1):
                                v = vals[p]
                                if not (np.isfinite(v) and v != 0):
                                    continue
                                panel_idx_p = int(idx_arr[p])
                                if st_series is None or panel_idx_p not in st_series.index:
                                    continue
                                sv = st_series.at[panel_idx_p]
                                if not (np.isfinite(sv) and sv != 0):
                                    continue
                                # statements present — classify the ratio
                                st_ratio = abs(sv) / abs(v)
                                if power / CLASSB_SOLO_TIGHT <= st_ratio <= power * CLASSB_SOLO_TIGHT:
                                    # Corroborates the scale correction — proceed
                                    pass
                                elif 1.0 / XSRC_CLEAN <= st_ratio <= XSRC_CLEAN:
                                    # PROTECTED territory: statements ≈ raw
                                    # (Gate 0 safety net)
                                    stmt_gate_ok = False
                                    break
                                else:
                                    # Disagreement — record to suspects and skip
                                    _flank_suspects.append({
                                        "ticker": str(ticker),
                                        "fy_lo": int(fy_arr[lo]),
                                        "fy_hi": int(fy_arr[hi]),
                                        "col": col,
                                        "med": float(med),
                                        "stmt_disagree": float(sv),
                                    })
                                    stmt_gate_ok = False
                                    break
                            if not stmt_gate_ok:
                                continue
                            _corr_note = ""

                        # LOOSE_ALL check (all rows in segment vs both flanks)
                        loose_ok = True
                        for p in range(lo, hi + 1):
                            vp = vals[p]
                            if not (np.isfinite(vp) and vp != 0):
                                continue
                            r_ll = _ratio(vp * power, adj_clean_l)
                            r_rl = _ratio(vp * power, adj_clean_r)
                            if not ((np.isfinite(r_ll) and r_ll <= LOOSE_ALL) and
                                    (np.isfinite(r_rl) and r_rl <= LOOSE_ALL)):
                                loose_ok = False
                                break
                        if not loose_ok:
                            continue

                        # Anchor continuity (FIX 2: all-absent now rejects)
                        if lo > 0:
                            if not _anchor_cont_ok(col, anchor_arrs, lg[1], lo):
                                continue
                        if hi < len(vals) - 1:
                            if not _anchor_cont_ok(col, anchor_arrs, hi, rg[0]):
                                continue

                        corr_note = _corr_note

                    else:
                        # --------------------------------------------------
                        # CLASS A (assets) — original logic unchanged
                        # --------------------------------------------------
                        if not (np.isfinite(r_tight_l) and r_tight_l <= TIGHT_ADJ):
                            continue
                        if not (np.isfinite(r_tight_r) and r_tight_r <= TIGHT_ADJ):
                            continue

                        # LOOSE_ALL on all rows vs both flanks
                        loose_ok = True
                        for p in range(lo, hi + 1):
                            vp = vals[p]
                            if not (np.isfinite(vp) and vp != 0):
                                continue
                            r_ll = _ratio(vp * power, adj_clean_l)
                            r_rl = _ratio(vp * power, adj_clean_r)
                            if not ((np.isfinite(r_ll) and r_ll <= LOOSE_ALL) and
                                    (np.isfinite(r_rl) and r_rl <= LOOSE_ALL)):
                                loose_ok = False
                                break
                        if not loose_ok:
                            continue

                        # Anchor continuity (FIX 2: all-absent now rejects)
                        if lo > 0:
                            if not _anchor_cont_ok(col, anchor_arrs, lg[1], lo):
                                continue
                        if hi < len(vals) - 1:
                            if not _anchor_cont_ok(col, anchor_arrs, hi, rg[0]):
                                continue

                    found_k = k
                    break

                if found_k is not None:
                    for p in range(lo, hi + 1):
                        v = vals[p]
                        if not (np.isfinite(v) and v != 0):
                            continue
                        note = f"x1e{found_k} flank"
                        if corr_note:
                            note = f"{note} {corr_note}"
                        flags.append({
                            "index": int(idx_arr[p]),
                            "ticker": str(ticker),
                            "fy": int(fy_arr[p]),
                            "col": col,
                            "flag": "flank_scale",
                            "value": float(v),
                            "repair": float(v) * (10.0 ** found_k),
                            "note": note,
                        })
                    # Record assets repairs for same-ticker Gate 1 corroboration
                    if col == "assets":
                        for p in range(lo, hi + 1):
                            v = vals[p]
                            if np.isfinite(v) and v != 0:
                                fy_val = int(fy_arr[p])
                                _flank_assets_k[(str(ticker), fy_val)] = found_k
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
    result.attrs["_xsrc_disagree"] = _xsrc_disagree
    result.attrs["_flank_suspects"] = _flank_suspects
    return result


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
def apply_stock_quality(
    panel: pd.DataFrame,
    statements: pd.DataFrame | None = None,
    max_rounds: int = 6,
) -> tuple[pd.DataFrame, dict]:
    """Return (panel copy with stock values repaired or nulled, audit dict).

    Adds sparse raw columns {col}_raw for each STOCK_COLS column present plus
    assets_prior_raw; values are NaN except on flagged/mirrored rows.

    Adds string column `stock_flag` (None when no flag; ";"-joined tokens like
    "assets:flank_scale:x1e3", "assets:junk_null:null", "assets_prior:mirror",
    "assets_prior:null_mirror").

    Fixed-point loop: mirrors edgar_flow_quality.apply_flow_quality exactly.
    Converges in ≤2 rounds for stock columns (smoother series).

    Idempotency: re-applying to a healed panel finds 0 new flags.

    Null class (junk_null): Lane 3 sets repair=NaN for junk leading-edge facts
    (MDT/FTI/MIR class).  These cells become NaN in the panel so downstream
    factors go NaN instead of wrong.  Originals preserved in *_raw columns.

    Audit dict keys: applied, rows_flagged, tickers_flagged, by_flag, repaired,
    nulled (count of NaN-repair flags), mirrors, rows, xsrc_disagreements,
    flank_suspects.
    """
    out = panel.copy()

    # Initialise sparse raw columns and stock_flag
    for c in STOCK_COLS:
        raw_col = f"{c}_raw"
        if raw_col not in out.columns:
            out[raw_col] = float("nan")
    if "assets_prior_raw" not in out.columns:
        out["assets_prior_raw"] = float("nan")
    if "stock_flag" not in out.columns:
        out["stock_flag"] = None

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
            if pd.isna(out.at[i, raw_col]):
                out.at[i, raw_col] = out.at[i, col]
            out.at[i, col] = f["repair"]
            token = f"{col}:{f['flag']}:{f['note'].split()[0]}"
            existing = out.at[i, "stock_flag"]
            out.at[i, "stock_flag"] = token if (existing is None or existing != existing) \
                else f"{existing};{token}"
        all_found.append(found)
    else:
        log.warning("stock_quality: no fixed point after %d rounds", max_rounds)

    # Deduplicate across rounds
    found_all = (pd.concat(all_found, ignore_index=True)
                 .drop_duplicates(subset=["index", "col"], keep="last")
                 if all_found
                 else pd.DataFrame(columns=["index", "ticker", "fy", "col",
                                            "flag", "value", "repair", "note"]))

    # --- assets_prior mirroring ---
    # Mirror the ni_prior pattern from edgar_flow_quality.py exactly.
    # Nulled assets rows (repair=NaN) flow through the same matching logic;
    # when rep_a is NaN, assets_prior is set to NaN and token is "null_mirror".
    mirrors = 0
    if "assets_prior" in out.columns and len(found_all):
        assets_repairs = found_all[found_all["col"] == "assets"][
            ["ticker", "fy", "value", "repair"]].copy()
        for _, row in assets_repairs.iterrows():
            t = row["ticker"]
            fy_a = row["fy"]
            raw_a = row["value"]
            rep_a = row["repair"]
            # Find (ticker, fy+1) row whose assets_prior == raw_a within 1e-6 rel tol
            mask = (out["ticker"] == t) & (out["fy"] == fy_a + 1)
            for idx2 in out.index[mask]:
                ap = out.at[idx2, "assets_prior"]
                if not np.isfinite(ap):
                    continue
                if abs(ap - raw_a) <= 1e-6 * max(abs(raw_a), 1.0):
                    if pd.isna(out.at[idx2, "assets_prior_raw"]):
                        out.at[idx2, "assets_prior_raw"] = ap
                    out.at[idx2, "assets_prior"] = rep_a  # NaN for junk_null
                    token = ("assets_prior:null_mirror"
                             if not np.isfinite(rep_a)
                             else "assets_prior:mirror")
                    existing = out.at[idx2, "stock_flag"]
                    out.at[idx2, "stock_flag"] = (
                        token if (existing is None or existing != existing)
                        else f"{existing};{token}")
                    mirrors += 1

    # Deduplicate auxiliary lists
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
        # repaired: flags with a finite repair (×10^k); nulled: flags with NaN repair
        # (junk_null lane — cells where no PIT-honest repair exists, NaN is correct).
        "repaired": int(found_all["repair"].notna().sum()) if len(found_all) else 0,
        "nulled": int(found_all["repair"].isna().sum()) if len(found_all) else 0,
        "mirrors": mirrors,
        "rows": [
            {"ticker": r["ticker"], "fy": r["fy"], "col": r["col"],
             "flag": r["flag"],
             "raw": float(r["value"]),
             # Never emit NaN into JSON — null is the JSON encoding for "no repair value"
             "repair": (float(r["repair"]) if np.isfinite(r["repair"]) else None),
             "note": r["note"]}
            for _, r in found_all.iterrows()
        ],
        "xsrc_disagreements": xsrc_disagree_dedup,
        "flank_suspects": flank_suspects_dedup,
    }

    if len(found_all):
        log.info(
            "stock_quality: %d rows on %d tickers (%s) — %d repaired, %d nulled, %d mirrors",
            audit["rows_flagged"], audit["tickers_flagged"],
            audit["by_flag"], audit["repaired"], audit["nulled"], mirrors,
        )
    return out, audit
