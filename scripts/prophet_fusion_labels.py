#!/usr/bin/env python3
"""Frozen outcome frame for the Prophet US conditional-fusion arena (PR-1a skeleton).

Binding spec: ``research/PROPHET_CONDITIONAL_FUSION_MASTERPLAN_BY_FABLE.md`` §7
(frozen outcome definitions) and §9.4 (era-aware evaluation).  RESEARCH TIER, ZERO
AUTHORITY: this module reads committed stores, writes nothing under ``data/``, and
nothing it produces may move a rank, a size, or a gate.  It imports no ranker.

WHY THIS IS A SEPARATE MODULE FROM THE ARENA.  The outcome definitions are the part
of the arena that must be frozen BEFORE any challenger exists (§8.6 promotion gate:
"frozen now, before any result exists").  Keeping the label frame in its own leaf
module — imported by ``scripts/prophet_fusion_arena.py``, importing nothing from it —
means a diff that touches an outcome definition is visible as a diff to THIS file, and
cannot hide inside a modelling change.  The shared refusal base class lives here for
the same reason: the dependency arrow points arena -> labels, never back.

WHY EVERY FAILURE IS A TYPED REFUSAL, NEVER AN EMPTY FRAME.  The keystone store
(``data/us_prophet_rank/grades/``) does not exist yet (masterplan §4.0 — accrual is
BROKEN).  ``engine.us_prophet_grades.load_grades()`` answers an absent store with an
empty DataFrame, which is the correct contract for a nightly that must not crash and
the WRONG one for a research harness: a metric computed over zero rows is a number,
and a number is quotable.  Every load path here raises :class:`StoreEmptyRefusal`
naming the store instead.

WHAT IS DELIBERATELY NOT BUILT (nulls printed, never proxied)
-------------------------------------------------------------
* **O4 Entry quality** — owned by Live Entry Radar (#5578 §10).  This program defines
  NO rival entry outcome, so the Entry head is DEFERRED and reported as such.  The
  earlier ``fwd_mdd``-before-``fwd_mfe`` stand-in was itself a rival outcome and is
  withdrawn (masterplan §7 O4).
* **O6 Confidence calibration** — no printed-confidence band accrues yet, so the head
  has no ruler and is DEFERRED.  A head with no ruler is unfalsifiable and may not
  move rank (§7 O6).

Both appear in ``receipt["deferred_heads"]``.  A deferred head is never proxied.

UNITS.  ``excess_spy`` in both stores is a FRACTION of price (0.10 == +10pp), not a
percentage.  Every threshold below is therefore a fraction, and
:func:`_assert_fraction_units` refuses a frame that looks percent-scaled — a silent
100x unit error would make every tail and fragility read meaningless while producing
perfectly plausible-looking output.

Usage (report only; the arena is the CLI that consumes this)::

    python3 -m scripts.prophet_fusion_labels --frame board_ledger
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

import numpy as np
import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

SCHEMA = "prophet_fusion.labels.v1"

# --------------------------------------------------------------------------- #
# frames
# --------------------------------------------------------------------------- #

#: The graded-board frame (masterplan §8.5 frame 2): 2026-06-15 ->, the admitted
#: population, H in {5, 10, 21}.  Label: reconstructed curated universe, acceptable
#: with disclosure.
FRAME_BOARD_LEDGER = "board_ledger"

#: The keystone PIT frame (§8.5 frame 1) — ``data/us_prophet_rank/grades/`` via
#: :func:`engine.us_prophet_grades.load_grades`.  EMPTY TODAY (§4.0).
FRAME_PROPHET_RANK = "prophet_rank"

FRAMES = (FRAME_BOARD_LEDGER, FRAME_PROPHET_RANK)

BOARD_LEDGER_PARQUET = "us_board_ledger/retro_grades.parquet"
DISCLOSED_GAPS_JSON = "us_board_ledger/disclosed_gaps.json"

#: Every frame in §8.5 that cannot prove survivorship-cleanliness carries the flag
#: PRE-ASSIGNED (§9.6): its numbers may not be quoted without it and no §8.6 promotion
#: claim may rest on it.  Assigned here, in code, so an artifact cannot lose the label
#: by being copied out of the masterplan's prose.
SURVIVORSHIP_BIASED = {
    FRAME_BOARD_LEDGER: True,   # "reconstructed curated universe; acceptable with disclosure"
    FRAME_PROPHET_RANK: False,  # stamped PIT at admission time; nothing reconstructed
}

# --------------------------------------------------------------------------- #
# frozen outcome thresholds (§7) — FRACTIONS, not percentage points
# --------------------------------------------------------------------------- #

#: O3 asymmetry tails.  +10pp frozen before any challenger saw data as roughly the
#: top-decile magnitude of the measured H=21 excess distribution; the loser tail
#: mirrors it at -10pp.
TAIL_WIN = 0.10
TAIL_LOSS = -0.10

#: The horizons at which O3 is READ (§7 O3: "at H=21/63").  Computed at every horizon
#: the frame carries — the columns exist for all of them — but only these are the
#: registered read, and ``outcome_summary`` stamps the rest ``exploratory``.
TAIL_HORIZONS = (21, 63)

#: O5 fragility.  ``excess < -3pp @ H=10`` is the established loser rate (roadmap §5
#: frame, kept for cross-study comparability); ``excess < -10pp @ H=21`` is the severe
#: tail.  A horizon absent from this map has NO registered fragility read — it is
#: reported null, never given the neighbouring horizon's threshold.
FRAGILITY_BY_HORIZON: dict[int, float] = {10: -0.03, 21: -0.10}

#: O4 (Entry, owned by LER) and O6 (Confidence, no ruler yet).  Reported, never proxied.
DEFERRED_HEADS = ("entry", "confidence")
DEFERRED_REASON = {
    "entry": ("O4 is owned by Live Entry Radar (#5578 §10); this program defines no "
              "rival entry outcome and consumes LER grades when they exist. No proxy."),
    "confidence": ("O6 needs a printed-confidence band to grade conditional coverage "
                   "against; none accrues yet, so the head has no ruler and stays "
                   "display-only. No proxy."),
}

#: The disclosed null era, used ONLY when ``disclosed_gaps.json`` cannot be read.  The
#: file is the source of truth (a second gap will be added there, not here); this
#: constant exists so a missing file degrades to the KNOWN exclusion rather than to no
#: exclusion at all.  ``receipt["era_hygiene"]["source"]`` says which one was used.
FALLBACK_NULL_ERA = ("2026-08-03", "2026-08-06")

#: Units tripwire.  ``excess_spy`` is a fraction; a percent-scaled frame would put the
#: 99th percentile of |excess| in the tens.  3.0 (a +300% excess) is comfortably above
#: anything real and far below anything percent-scaled.
_UNITS_MAX_ABS = 3.0

# --------------------------------------------------------------------------- #
# column resolution — both stores, one label frame
# --------------------------------------------------------------------------- #

#: Date column, in preference order: the board ledger stamps ``as_of``, the grades
#: store stamps ``stamp_date``.  Resolved by presence, never assumed.
DATE_COLUMNS = ("as_of", "stamp_date")

#: MFE / MDD, in preference order.  The grades store writes unsuffixed ``fwd_mfe`` /
#: ``fwd_mdd`` per graded horizon (``engine.us_prophet_grades.grade_row``); the board
#: ledger writes per-horizon ``fwd_mfe_{H}`` and a close-based drawdown under a
#: different name entirely.  ``{h}`` is substituted with the row's horizon.
MFE_COLUMNS = ("fwd_mfe", "fwd_mfe_{h}")
MDD_COLUMNS = ("fwd_mdd", "fwd_mdd_{h}", "mae_close_excess_spy")

#: Strata, NOT features (§7 era hygiene): row-constant-per-night era stamps share F6's
#: cross-sectional degeneracy as features, so they are carried as strata and the
#: fragmentation is reported as the honest cost.  Carried when present; absence is
#: disclosed in the receipt, never filled.
STRATA_COLUMNS = ("board_definition", "rank_by", "price_basis", "price_source",
                  "universe_tier", "signal_class", "lane", "sector")

#: The label key.  ``lane`` is NOT in it: a name can sit in two lanes on one night
#: (measured: 2 such pairs in retro_grades on 2026-07-29) and that is one outcome, not
#: two.  Keep-first mirrors the candidates store's own dedupe law.
LABEL_KEY = ("date", "ticker", "horizon")

COHORT_CURATED = "curated"


# --------------------------------------------------------------------------- #
# refusals
# --------------------------------------------------------------------------- #

class FusionRefusal(RuntimeError):
    """Base for every refusal in the conditional-fusion harness.

    The arena imports this so a caller can catch the whole family with one except.
    """


class StoreEmptyRefusal(FusionRefusal):
    """A store the caller asked for is absent or has no rows.

    Never degraded to an empty frame: a metric over zero rows is still a number, and a
    number gets quoted.
    """

    def __init__(self, store: str, detail: str = "") -> None:
        self.store = store
        self.detail = detail
        super().__init__(f"store is empty or absent: {store}"
                         + (f" ({detail})" if detail else ""))


class LabelUnitsRefusal(FusionRefusal):
    """The outcome column does not look like a fraction (probable percent scaling)."""

    def __init__(self, column: str, observed: float) -> None:
        self.column = column
        self.observed = observed
        super().__init__(
            f"{column} fails the fraction-units check: |p99| = {observed:.4g} > "
            f"{_UNITS_MAX_ABS}. Every §7 threshold is a fraction (0.10 == +10pp); a "
            f"percent-scaled frame would silently make every tail read meaningless.")


class OutcomeColumnRefusal(FusionRefusal):
    """The frame carries no gradeable outcome column at all."""

    def __init__(self, missing: Sequence[str]) -> None:
        self.missing = tuple(missing)
        super().__init__("frame carries no outcome column; need one of: "
                         + ", ".join(self.missing))


class PriceBasisPoolRefusal(FusionRefusal):
    """Refusal to pool inference across the 2026-08-06 price-basis boundary (§9.4).

    Not raised by :func:`build_labels` — the label frame always CARRIES the stratum.
    Raised by :func:`assert_poolable`, at the point where a consumer treats the frame
    as one population, because that is where the era violation actually happens.
    """

    def __init__(self, bases: Sequence[str], counts: Mapping[str, int]) -> None:
        self.bases = tuple(bases)
        self.counts = dict(counts)
        super().__init__(
            "refusing to pool across price_basis eras "
            + ", ".join(f"{b}={counts.get(b, 0)}" for b in self.bases)
            + " — pass allow_price_basis_pool=True to proceed; the output is then "
              "tagged exploratory: true and is promotion-barred (§8.3, §9.4).")


# --------------------------------------------------------------------------- #
# era hygiene
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class NullEra:
    """One disclosed null era: a window that must be EXCLUDED, never imputed."""

    gap_id: str
    market: str | None
    board_definition: str | None
    window: tuple[str, str]
    missing_trading_days: tuple[str, ...]

    def covers(self, date: str) -> bool:
        """Window-inclusive, plus any explicitly listed day outside it.

        The window is used rather than only ``missing_trading_days`` because it is a
        SUPERSET (the 2026-08 gap declares 08-01..08-06 while listing 08-03..08-06 —
        the difference is a weekend, so excluding the window costs nothing and cannot
        under-exclude if a future gap lists its days incompletely).
        """
        lo, hi = self.window
        return (lo <= date <= hi) or (date in self.missing_trading_days)


def disclosed_null_eras(path: Path | str | None = None,
                        *, market: str = "US") -> tuple[list[NullEra], str]:
    """``(eras, source)`` from ``data/us_board_ledger/disclosed_gaps.json``.

    Only ``gradeable: false`` gaps are exclusions — a gradeable gap is a coverage fact,
    not a null era.  A missing/malformed file degrades to :data:`FALLBACK_NULL_ERA`
    with ``source="fallback_constant"``, so the known hole is never silently included.
    """
    target = Path(path) if path is not None else (_REPO_ROOT / "data" / DISCLOSED_GAPS_JSON)
    try:
        doc = json.loads(Path(target).read_text(encoding="utf-8"))
        gaps = doc.get("gaps") or []
    except Exception:  # noqa: BLE001 — an unreadable file must not disable the exclusion
        lo, hi = FALLBACK_NULL_ERA
        return ([NullEra("fallback", market, None, (lo, hi), (lo, hi))],
                "fallback_constant")
    out: list[NullEra] = []
    for gap in gaps:
        if not isinstance(gap, Mapping):
            continue
        if gap.get("gradeable") is not False:
            continue
        gap_market = gap.get("market")
        if gap_market is not None and str(gap_market).upper() != market.upper():
            continue
        window = gap.get("window") or {}
        days = tuple(str(d) for d in (gap.get("missing_trading_days") or ()))
        lo = str(window.get("from") or (days[0] if days else ""))
        hi = str(window.get("to") or (days[-1] if days else ""))
        if not lo or not hi:
            continue
        out.append(NullEra(str(gap.get("id") or "unnamed"), gap_market,
                           gap.get("board_definition"), (lo, hi), days))
    if not out:
        lo, hi = FALLBACK_NULL_ERA
        return ([NullEra("fallback", market, None, (lo, hi), (lo, hi))],
                "fallback_constant")
    return out, str(target)


# --------------------------------------------------------------------------- #
# store loaders
# --------------------------------------------------------------------------- #

def load_board_ledger_frame(root: Path | str | None = None,
                            path: Path | str | None = None) -> pd.DataFrame:
    """The graded-board frame (§8.5 frame 2).  Read-only.  Refuses an empty store."""
    if path is not None:
        target = Path(path)
    else:
        base = Path(root) / "data" if root is not None else _REPO_ROOT / "data"
        target = base / BOARD_LEDGER_PARQUET
    if not target.exists():
        raise StoreEmptyRefusal(str(target), "parquet does not exist")
    frame = pd.read_parquet(target)
    if frame.empty:
        raise StoreEmptyRefusal(str(target), "parquet has zero rows")
    return frame


def load_prophet_rank_frame(root: Path | str | None = None) -> pd.DataFrame:
    """The keystone PIT grades frame (§8.5 frame 1) — EMPTY TODAY (§4.0).

    ``engine.us_prophet_grades`` is imported LAZILY: it pulls the context-vector store,
    the grading ruler and ``lib.config``, and this module must stay importable (and
    fast) in a test process that never touches the live stores.
    """
    try:
        from engine import us_prophet_grades as upg  # noqa: PLC0415 — deliberate lazy import
    except Exception as exc:  # noqa: BLE001
        raise StoreEmptyRefusal("data/us_prophet_rank/grades",
                                f"engine.us_prophet_grades unimportable: {exc}") from exc
    frame = upg.load_grades(root)
    if frame is None or frame.empty:
        raise StoreEmptyRefusal(
            "data/us_prophet_rank/grades",
            "the keystone store is NOT ACCRUING (masterplan §4.0); load_grades() "
            "returned an empty frame and an empty frame is not a population")
    return frame


def load_frame(frame_name: str, *, root: Path | str | None = None,
               path: Path | str | None = None) -> pd.DataFrame:
    """Dispatch a frame name to its loader."""
    if frame_name == FRAME_BOARD_LEDGER:
        return load_board_ledger_frame(root=root, path=path)
    if frame_name == FRAME_PROPHET_RANK:
        return load_prophet_rank_frame(root=root)
    raise FusionRefusal(f"unknown frame {frame_name!r}; known frames: {list(FRAMES)}")


# --------------------------------------------------------------------------- #
# label frame
# --------------------------------------------------------------------------- #

@dataclass
class LabelFrame:
    """The frozen outcome frame plus the receipt that makes it auditable."""

    frame: pd.DataFrame
    receipt: dict[str, Any] = field(default_factory=dict)

    @property
    def dates(self) -> list[str]:
        if self.frame.empty:
            return []
        return sorted(self.frame["date"].astype(str).unique().tolist())

    @property
    def horizons(self) -> list[int]:
        if self.frame.empty:
            return []
        return sorted(int(h) for h in self.frame["horizon"].dropna().unique())


def _resolve(frame: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    for name in candidates:
        if "{h}" in name:
            continue
        if name in frame.columns:
            return name
    return None


def _per_horizon_column(frame: pd.DataFrame, patterns: Iterable[str],
                        horizons: Iterable[int]) -> pd.Series:
    """Pull a value that may live in one column or in one column PER horizon.

    Returns a float Series aligned to ``frame``; a row whose horizon has no column is
    NaN — unmeasured, never zero (#4485 null-never-false).
    """
    out = pd.Series(np.nan, index=frame.index, dtype="float64")
    flat = _resolve(frame, patterns)
    if flat is not None:
        out = pd.to_numeric(frame[flat], errors="coerce")
    for horizon in horizons:
        for pattern in patterns:
            if "{h}" not in pattern:
                continue
            name = pattern.format(h=int(horizon))
            if name not in frame.columns:
                continue
            mask = frame["horizon"] == horizon
            values = pd.to_numeric(frame.loc[mask, name], errors="coerce")
            out.loc[mask] = out.loc[mask].where(values.isna(), values)
            break
    return out


def _assert_fraction_units(values: pd.Series, column: str) -> float:
    finite = pd.to_numeric(values, errors="coerce").dropna().abs()
    if finite.empty:
        return 0.0
    observed = float(finite.quantile(0.99))
    if observed > _UNITS_MAX_ABS:
        raise LabelUnitsRefusal(column, observed)
    return observed


def _nullable_bool(mask: pd.Series, valid: pd.Series) -> pd.Series:
    """Boolean where measured, ``pd.NA`` where not — never False-by-default."""
    out = pd.Series(pd.array([pd.NA] * len(mask), dtype="boolean"), index=mask.index)
    out[valid] = mask[valid]
    return out


def build_labels(frame: pd.DataFrame | None = None, *,
                 frame_name: str = FRAME_BOARD_LEDGER,
                 root: Path | str | None = None,
                 path: Path | str | None = None,
                 disclosed_gaps_path: Path | str | None = None,
                 curated_only: bool = True) -> LabelFrame:
    """Build the §7 outcome frame from a graded store.

    Heads built: O1 (``excess_spy``), O2 (``hit``), O3 (``tail_win`` / ``tail_loss`` /
    ``mfe`` / ``mdd``), O5 (``fragile``).  O4 and O6 are DEFERRED and appear only in
    ``receipt["deferred_heads"]``.

    Era hygiene is applied here, once, so no consumer can forget it: the disclosed null
    era is EXCLUDED (not imputed) and the exclusion is counted in the receipt; era
    stamps ride as strata columns.  ``price_basis`` is carried, never pooled — see
    :func:`assert_poolable`.
    """
    if frame_name not in FRAMES:
        raise FusionRefusal(f"unknown frame {frame_name!r}; known frames: {list(FRAMES)}")
    raw = load_frame(frame_name, root=root, path=path) if frame is None else frame.copy()
    if raw is None or raw.empty:
        raise StoreEmptyRefusal(frame_name, "caller supplied an empty frame")

    date_col = _resolve(raw, DATE_COLUMNS)
    if date_col is None:
        raise OutcomeColumnRefusal(DATE_COLUMNS)
    if "excess_spy" not in raw.columns:
        raise OutcomeColumnRefusal(("excess_spy",))
    if "ticker" not in raw.columns or "horizon" not in raw.columns:
        raise OutcomeColumnRefusal(("ticker", "horizon"))

    work = raw.copy()
    work["date"] = work[date_col].astype(str).str.slice(0, 10)
    work["ticker"] = work["ticker"].astype(str)
    work["horizon"] = pd.to_numeric(work["horizon"], errors="coerce").astype("Int64")
    work = work[work["horizon"].notna()].copy()
    work["horizon"] = work["horizon"].astype(int)

    rows_in = int(len(work))

    # --- era hygiene: EXCLUDE the disclosed null era, count it, name its source ----
    eras, era_source = disclosed_null_eras(disclosed_gaps_path)
    in_era = pd.Series(False, index=work.index)
    for era in eras:
        in_era |= work["date"].map(era.covers)
    excluded_rows = int(in_era.sum())
    excluded_dates = sorted(work.loc[in_era, "date"].unique().tolist())
    work = work[~in_era].copy()

    # --- population: curated only; NEVER silently claim curated (store README) -----
    cohort_note = "column absent — frame is the admitted board population, unsplit"
    scan_excluded = 0
    if "universe_tier" in work.columns:
        tier = work["universe_tier"].astype("string")
        if tier.notna().any():
            if curated_only:
                keep = tier.str.lower() == COHORT_CURATED
                scan_excluded = int((~keep).sum())
                work = work[keep].copy()
                cohort_note = f"filtered to universe_tier == {COHORT_CURATED!r}"
            else:
                cohort_note = "curated_only=False — cohorts POOLED, exploratory"
        else:
            cohort_note = "column present but all-null — unsplit, not called curated"

    if work.empty:
        raise StoreEmptyRefusal(frame_name,
                                "every row was removed by era hygiene / population law")

    # --- dedupe on the label key (a name in two lanes is one outcome) --------------
    before = len(work)
    work = work.drop_duplicates(subset=list(LABEL_KEY), keep="first").copy()
    duplicates_dropped = before - len(work)

    excess = pd.to_numeric(work["excess_spy"], errors="coerce")
    units_p99 = _assert_fraction_units(excess, "excess_spy")
    measured = excess.notna()
    horizons = sorted(work["horizon"].unique().tolist())

    out = pd.DataFrame(index=work.index)
    out["date"] = work["date"]
    out["ticker"] = work["ticker"]
    out["horizon"] = work["horizon"]
    out["frame"] = frame_name
    out["survivorship_biased"] = bool(SURVIVORSHIP_BIASED.get(frame_name, True))

    # O1 — selection excess
    out["excess_spy"] = excess
    # O2 — directional hit
    out["hit"] = _nullable_bool(excess > 0, measured)
    # O3 — asymmetry tails + MFE / MDD
    out["tail_win"] = _nullable_bool(excess > TAIL_WIN, measured)
    out["tail_loss"] = _nullable_bool(excess < TAIL_LOSS, measured)
    out["tail_registered_read"] = out["horizon"].isin(TAIL_HORIZONS)
    out["mfe"] = _per_horizon_column(work, MFE_COLUMNS, horizons)
    out["mdd"] = _per_horizon_column(work, MDD_COLUMNS, horizons)
    # O5 — fragility, per-horizon threshold; a horizon with no registered threshold
    # gets pd.NA, never the neighbouring horizon's number
    thresholds = out["horizon"].map(FRAGILITY_BY_HORIZON)
    has_threshold = thresholds.notna() & measured
    out["fragility_threshold"] = thresholds
    out["fragile"] = _nullable_bool(excess < thresholds.fillna(-np.inf), has_threshold)

    strata_present, strata_absent = [], []
    for name in STRATA_COLUMNS:
        if name in work.columns:
            out[name] = work[name]
            strata_present.append(name)
        else:
            strata_absent.append(name)

    out = out.sort_values(["date", "horizon", "ticker"]).reset_index(drop=True)

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "frame": frame_name,
        "source": str(path) if path is not None else (
            str(_REPO_ROOT / "data" / BOARD_LEDGER_PARQUET)
            if frame_name == FRAME_BOARD_LEDGER and frame is None
            else ("caller-supplied frame" if frame is not None
                  else "data/us_prophet_rank/grades")),
        "survivorship_biased": bool(SURVIVORSHIP_BIASED.get(frame_name, True)),
        "rows_in": rows_in,
        "rows_out": int(len(out)),
        "duplicates_dropped": int(duplicates_dropped),
        "n_dates": int(out["date"].nunique()),
        "date_range": [out["date"].min(), out["date"].max()],
        "horizons": [int(h) for h in sorted(out["horizon"].unique())],
        "heads_built": ["O1", "O2", "O3", "O5"],
        "deferred_heads": list(DEFERRED_HEADS),
        "deferred_reason": dict(DEFERRED_REASON),
        "thresholds": {
            "tail_win": TAIL_WIN, "tail_loss": TAIL_LOSS,
            "tail_registered_horizons": list(TAIL_HORIZONS),
            "fragility_by_horizon": {str(k): v for k, v in FRAGILITY_BY_HORIZON.items()},
            "units": "fraction of price (0.10 == +10pp)",
            "units_p99_abs_excess": round(units_p99, 6),
        },
        "era_hygiene": {
            "source": era_source,
            "eras": [{"id": e.gap_id, "window": list(e.window)} for e in eras],
            "rows_excluded": excluded_rows,
            "dates_excluded": excluded_dates,
        },
        "population": {"curated_only": bool(curated_only),
                       "universe_tier": cohort_note,
                       "scan_rows_excluded": int(scan_excluded)},
        "strata": {"present": strata_present, "absent": strata_absent,
                   "counts": {name: {str(k): int(v) for k, v in
                                     out[name].astype("string").fillna("<null>")
                                     .value_counts().items()}
                              for name in strata_present
                              if out[name].nunique(dropna=False) <= 12}},
        "price_basis_pooled": False,
        "exploratory": bool(not curated_only),
    }
    return LabelFrame(frame=out, receipt=receipt)


# --------------------------------------------------------------------------- #
# pooling law (§9.4)
# --------------------------------------------------------------------------- #

def assert_poolable(labels: LabelFrame, *, allow_price_basis_pool: bool = False,
                    column: str = "price_basis") -> dict[str, Any]:
    """Refuse to treat a multi-era frame as ONE population without disclosure.

    WHY THIS IS NOT IN ``build_labels``.  The era violation is not "the frame contains
    two bases" — the frame SHOULD carry both, stratified.  It is "a statistic was
    computed across them as if they were one population".  So the check sits where the
    pooling happens: the arena calls this before it folds/scores, and the answer is
    either a refusal or an ``exploratory: true`` tag that is promotion-barred.
    """
    frame = labels.frame
    if column not in frame.columns:
        return {"column": column, "status": "absent", "pooled": False,
                "exploratory": False}
    counts = (frame[column].astype("string").fillna("<null>")
              .value_counts().to_dict())
    bases = sorted(counts)
    if len(bases) <= 1:
        return {"column": column, "status": "single_era", "bases": bases,
                "counts": {k: int(v) for k, v in counts.items()},
                "pooled": False, "exploratory": False}
    if not allow_price_basis_pool:
        raise PriceBasisPoolRefusal(bases, {k: int(v) for k, v in counts.items()})
    labels.receipt["price_basis_pooled"] = True
    labels.receipt["exploratory"] = True
    return {"column": column, "status": "pooled_by_explicit_flag", "bases": bases,
            "counts": {k: int(v) for k, v in counts.items()},
            "pooled": True, "exploratory": True,
            "note": "promotion-barred (§8.3 slices/exploratory, §9.4 era-aware)"}


# --------------------------------------------------------------------------- #
# summary (nulls printed)
# --------------------------------------------------------------------------- #

def _opt(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def outcome_summary(labels: LabelFrame) -> dict[str, Any]:
    """Per-horizon head readings.  A head with no data prints null, never a zero."""
    frame = labels.frame
    per_horizon: dict[str, Any] = {}
    for horizon in labels.horizons:
        slab = frame[frame["horizon"] == horizon]
        excess = pd.to_numeric(slab["excess_spy"], errors="coerce").dropna()
        wins, losses = excess[excess > 0], excess[excess < 0]
        threshold = FRAGILITY_BY_HORIZON.get(int(horizon))
        per_horizon[str(horizon)] = {
            "n": int(len(slab)),
            "n_measured": int(len(excess)),
            "n_dates": int(slab["date"].nunique()),
            "O1_excess": {"mean": _opt(excess.mean()), "median": _opt(excess.median())},
            "O2_hit": {"rate": _opt((excess > 0).mean()) if len(excess) else None},
            "O3_tails": {
                "registered_read": int(horizon) in TAIL_HORIZONS,
                "p_excess_gt_win": _opt((excess > TAIL_WIN).mean()) if len(excess) else None,
                "p_excess_lt_loss": _opt((excess < TAIL_LOSS).mean()) if len(excess) else None,
                "e_excess_given_win": _opt(wins.mean()) if len(wins) else None,
                "e_excess_given_loss": _opt(losses.mean()) if len(losses) else None,
                "mfe_median": _opt(pd.to_numeric(slab["mfe"], errors="coerce").median()),
                "mdd_median": _opt(pd.to_numeric(slab["mdd"], errors="coerce").median()),
                "mfe_coverage": _opt(pd.to_numeric(slab["mfe"], errors="coerce").notna().mean()),
                "mdd_coverage": _opt(pd.to_numeric(slab["mdd"], errors="coerce").notna().mean()),
            },
            "O5_fragility": {
                "threshold": threshold,
                "rate": (_opt((excess < threshold).mean())
                         if threshold is not None and len(excess) else None),
                "note": (None if threshold is not None
                         else "no registered fragility threshold at this horizon"),
            },
        }
    return {
        "schema": SCHEMA,
        "frame": labels.receipt.get("frame"),
        "survivorship_biased": labels.receipt.get("survivorship_biased"),
        "exploratory": labels.receipt.get("exploratory"),
        "deferred_heads": list(DEFERRED_HEADS),
        "by_horizon": per_horizon,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--frame", default=FRAME_BOARD_LEDGER, choices=list(FRAMES))
    parser.add_argument("--root", default=None)
    parser.add_argument("--json", action="store_true",
                        help="print the receipt + summary as JSON")
    args = parser.parse_args(argv)
    try:
        labels = build_labels(frame_name=args.frame, root=args.root)
    except FusionRefusal as exc:
        print(f"REFUSED: {type(exc).__name__}: {exc}", flush=True)
        return 2
    doc = {"receipt": labels.receipt, "summary": outcome_summary(labels)}
    if args.json:
        print(json.dumps(doc, indent=2, default=str), flush=True)
    else:
        r = labels.receipt
        print(f"labels frame={r['frame']} rows={r['rows_out']}/{r['rows_in']} "
              f"dates={r['n_dates']} horizons={r['horizons']} "
              f"era_excluded_rows={r['era_hygiene']['rows_excluded']} "
              f"deferred={','.join(r['deferred_heads'])} "
              f"survivorship_biased={r['survivorship_biased']}", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover — CLI entry
    raise SystemExit(main())
