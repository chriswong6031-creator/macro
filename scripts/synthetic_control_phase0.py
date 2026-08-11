"""Phase-0: synthetic_control — donor-pool counterfactuals for event studies.

FROZEN PRE-REGISTRATION (written BEFORE any result was computed; every gap found
afterwards is recorded in AMENDMENTS below and repeated in the results file)
================================================================================
Family:  synthetic_control_phase0
Program: advanced-quant-methods-w2a
Charter: research/ADVANCED_QUANT_METHODS_ADJUDICATION_BY_FABLE.md §3#5, §4 wave-2a
Tier:    DIAGNOSTIC. This harness grades an ESTIMATOR, not a signal. Nothing here
         promotes anything, gates any surface, or enters a ranked path. No event
         family is being scored for tradability; two families with KNOWN answers are
         being used as instruments to measure whether the estimator tells the truth.

QUESTION
--------
Every event study in this repo scores an event by BENCHMARK-ADJUSTED CAR: the treated
name's return minus SPY's, or minus a sector ETF's. That is a one-donor counterfactual
whose weight was never fitted, and it is consistent only if the benchmark spans the
treated name's factor exposure. Goldsmith-Pinkham & Lyu (arXiv 2511.15123) show that
factor-model event-study estimates can be inconsistent under exactly this
misspecification, and that the repair is a fitted REPLICATING PORTFOLIO.

  Does a donor-pool synthetic control estimate event effects MORE HONESTLY than the
  incumbent benchmark-adjusted CAR on this panel — preserving an effect the house has
  already graded as real, refusing to manufacture one the house has already graded as
  null, and doing so with no more placebo dispersion than the incumbent?

An estimator is only worth adopting if it passes all three. A method that keeps the
real effect but also invents fake ones is biased; a method that kills both is
powerless; a method that is unbiased but noisier than what we already run has bought
nothing.

THE TWO INSTRUMENTS (both answers pre-exist; neither is being discovered here)
------------------------------------------------------------------------------
POSITIVE CONTROL — S&P index PURE ADDS.
  The house graded this family at +1.64% gross over the [-5, 0] trading-day window
  around the effective date, HAC t = 4.63 on n = 877 events / 86 months
  (scripts/validate_index_reconstitution.py; data/index_reconstitution/validation_gate.json,
  2026-08-01). A pure add is a name entering from OUTSIDE the S&P universe, so there is
  no offsetting forced index seller — the cohort that carries the announcement run-up.
  If synthetic control ERASES this effect, that is a failure of the estimator, not a
  discovery about index adds.

FALSIFIER — ClinicalTrials Phase-3 START.
  The house measured this family null TWICE: the 2026-07-19 event-prior screen
  (data/special_situations/event_priors/clinicaltrials.json, BH q = 0.6614, reject =
  false, is_context_only = true) and the 2026-08-03 event study
  (data/experiments/clinicaltrials_phase3_event_study_results.json): day-0 abnormal
  return -0.9 bp with t = -0.169, and the [0,20] read of +0.589% vs XLV carrying
  ticker-cluster t = 2.302 but empirical p = 0.186 against its own random-date placebo
  — i.e. the placebo reproduces ~70% of the apparent effect, and the [0,20] number
  vanishes entirely against SPY (+0.065%, t = 0.28). Verdict on record: "NULL —
  placebo-explained"; the scored catalyst leg is a KILL with a DNR row. If synthetic
  control MANUFACTURES a significant effect here, the estimator is biased.

ESTIMATORS (both pre-registered in engine/synthetic_control.py; no others run)
-----------------------------------------------------------------------------
  matched_k  top-k=20 eligible donors by pre-window return correlation, screened to a
             0.5x-2.0x vol-similarity band, EQUAL weight. Zero fitted parameters.
  sc_nnls    simplex-constrained least squares (w >= 0, sum w = 1) on pre-window
             returns over the top-M=50 by correlation, solved by exact-projection
             FISTA. The classic Abadie-Diamond-Hainmueller constraint set.
  INCUMBENT  benchmark-adjusted CAR vs SPY, and vs sector ETF where derivable. This is
             the arm the two above must beat; it is not itself under test.
The two SC estimators are reported side by side and are NEVER combined into a fused
composite (§3 fusion law).

DONOR POOL (engine/synthetic_control.eligible_donors; pre-registered)
  - not the treated name;
  - no event of the donor's OWN family within +/- 21 sessions of the event (a
    contaminated donor imports the treatment and biases tau toward zero);
  - >= 90% of the pre-window populated;
  - 20d median dollar volume >= $2M measured AT THE PRE-WINDOW END (causal);
  - house universe floor: split-adjusted close > $5 at the pre-window end (AM-3).

PIT LAW
  pre-window = 120 sessions ending at t-6 inclusive (a 5-session embargo before the
  event day). Nothing at or after t-5 enters any fit. For the index family the embargo
  is load-bearing: the announcement run-up IS the effect, and a pre-window running to
  t-1 would fit the donors to the leak and estimate it away. Pinned by
  tests/test_synthetic_control.py::test_pit_perturbation_does_not_move_weights.

EVENT DAY
  Index adds: t = 5 sessions BEFORE the first session on/after the effective date, so
    CAR[0,5] covers the incumbent's [-5, 0] announce window (see AM-7 — it carries ONE
    EXTRA session, and the incumbent's exact statistic is reconciled separately). S&P
    announces ~5 trading days ahead.
  Phase-3: t = first session on/after StudyFirstPostDate (first public availability;
    verified collectors/clinicaltrials.py studyFirstPostDateStruct), matching the prior
    study's date semantics exactly.

OUTCOMES
  tau_t = r_treated,t - r_counterfactual,t, and CAR over the windows [0], [0,5], [0,20]
  (trading days from the event day, inclusive). Simple returns on split-adjusted closes.

STATS LAW
  Primary inference is MONTHLY-CLUSTERED Newey-West on the per-event abnormal returns
  (group events by calendar month, take the mean, then engine.validation.newey_west_tstat
  with lags = min(4, max(1, n_months // 4))) — byte-identical to the stats law the
  incumbent index-reconstitution study used, so PC-1 is a like-for-like comparison.
  S&P reconstitutions batch quarterly and Phase-3 postings cluster within sponsor, so a
  naive iid t is invalid; a TICKER-clustered t is reported alongside as the secondary
  read (the statistic the Phase-3 prior study used, 19 sponsor clusters).

PLACEBO ARMS (both families, all arms)
  200 replications. Each replication re-dates EVERY event to a uniformly random
  eligible session for that same name, excluding sessions within +/- 42 of that name's
  real event (so a placebo cannot accidentally contain the real effect), and produces
  one aggregate CAAR. The 200 CAARs are the null distribution. Reported per arm:
  placebo MEAN (bias), placebo SD (dispersion — the power reading), and the two-sided
  EMPIRICAL p of the real CAAR against that distribution. The real events' donor
  contamination map is applied to placebo draws too, which is conservative.

GATES (pre-registered; each prints PASS/FAIL; a FAILED GATE IS A RESULT)
  PC-1  Positive control survives: S&P pure adds under sc_nnls at [0,5] give
        CAAR > 0 AND monthly-NW t > 2. (SC must not erase a graded effect.)
  PC-2  Neither SC estimator is biased: on BOTH families, |placebo mean| < 0.3% AND
        |placebo-mean t| < 2 at [0,5], where t = mean / (sd / sqrt(n_draws)).
  PC-3  SC buys something: sc_nnls placebo SD <= benchmark-CAR(SPY) placebo SD at
        [0,5], on the positive-control family. Otherwise SC is strictly noisier than
        what we already run.
  F-1   Falsifier holds: Phase-3 family under sc_nnls at [0,20] has |monthly-NW t| < 2
        AND empirical p > 0.05 against its own placebo. (SC must not manufacture an
        effect the placebo kills.)

VERDICTS
  ESTIMATOR_GO         all four gates pass
  ESTIMATOR_BIASED     PC-2 or F-1 fails (invents effects / is not centred)
  ESTIMATOR_POWERLESS  PC-1 or PC-3 fails (erases a real effect / is noisier)
  MIXED                failures on both sides
  The failing gate is always named.

DATA
  data/massive_stock_day/ — Polygon whole-market daily store, one parquet per
  instrument, open/high/low/close/volume/transactions, UNADJUSTED. Resolved by ladder:
    --data-root arg -> $MACRO_PRIMARY_DATA -> <repo>/data/massive_stock_day
    -> /Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day
  Read-only; this harness NEVER writes to the store. Splits repaired with the canonical
  scripts.replay_standout_pipeline.split_adjust (close only; the recovered factor is
  carried onto volume so dollar volume stays correct). Dividends are NOT adjusted
  (price return, not total return) — a whisker that applies identically to treated and
  donors and therefore very largely differences out of tau.

HONEST SCOPE
  The store begins 2021-07-06. A 120-session pre-window plus a 5-session embargo means
  the earliest usable event day is ~2022-01. Events are therefore restricted to
  2022-01-01 -> panel end, and the surviving n is PRINTED for both families. If pure
  adds in scope fall below 15, the pre-registered fallback is to DISCLOSE a widened
  variant with a shortened pre-window as a clearly-labelled second read — never to
  silently widen. (Measured before the run: 613 raw adds and 981 Phase-3 postings sit
  in scope, so the fallback is not expected to trigger.)

AMENDMENTS (gaps found while wiring; all recorded before the first result was read)
  AM-1  Announce dates. The charter names data/sp_index_changes/changes.parquet as the
        announce-date source. That store holds only 50 rows (25 adds, of which 4 are
        sp500) covering recent months — far too thin to carry the positive control, and
        NOT the store the +1.64%/t=4.63 house grade was computed from. The graded
        family is built entirely from data/breadth/sp1500_pit_membership.parquet via
        scripts/validate_index_reconstitution.py:load_events, with the announce window
        taken as [-5, 0] trading days around the EFFECTIVE date. This study reproduces
        THAT event list, because PC-1 is only a control if it is the same family the
        house already graded. changes.parquet is read only as a cross-check on the
        announce-lead assumption and its coverage is reported.
  AM-2  Sector-ETF arm. data/sector_holdings/XL*.parquet carry S&P 500 constituents
        only (236 unique tickers), so only 6.2% of in-scope index adds get a sector
        assignment — the adds are overwhelmingly sp400/sp600 names. The sector arm is
        therefore run for the Phase-3 family (XLV, exactly the benchmark the prior
        study used; all 19 sponsors are pharma) and REPORTED AS NOT DERIVABLE for the
        index family, where SPY is the incumbent comparator. Coverage is printed.
  AM-3  Universe floor. The charter's donor rules name coverage, liquidity and event
        exclusion but no price floor. The house universe floor (close > $5, e.g.
        engine/pick_forward_dist.py) is applied to donors so sub-$1 names whose returns
        are quantisation noise cannot enter a replicating portfolio. Removal-only.
  AM-4  Donor pre-screen. The fitted solver receives the top-50 donors by pre-window
        correlation rather than all ~4-5k eligible names. Curating the donor pool
        before fitting is standard synthetic-control practice, and at ~10^5 fits
        (events x 200 placebo replications x 2 families) the unscreened form does not
        finish. M=50 and k=20 are frozen here, before any result, and are not tuned.
  AM-5  Instrument-type. The store is instrument-level and this repo holds no
        whole-market security-type classifier, so ETFs/ADRs/preferreds that clear the
        liquidity floor are admissible DONORS. For a replicating portfolio this is a
        feature rather than a leak, but it is disclosed, not hidden.
  AM-6  Phase-3 events are collapsed to ticker-date CELLS (multiple NCTs posted by one
        sponsor on one day are ONE event), matching the prior study's
        "ticker_date_cells" construction. The prior study's own recorded biases —
        collector truncation at pageSize=100 and only 19 sponsor clusters — carry over
        unchanged and are restated in the results.

AMENDMENTS FOUND IN ADVERSARIAL REVIEW (recorded before the numbers below were read;
the run that produced them was discarded and re-run under these corrections)
  AM-7  CAR[0,5] is NOT byte-identical to the incumbent's announce window. The incumbent
        scores a PRICE RATIO close[e]/close[e-5]-1 = five daily returns; with the event
        day at e-5, CAR[0,5] sums SIX daily returns (closes e-6 -> e). The "spans
        exactly" claim above is withdrawn. The registered windows are kept as-is (all
        arms use identical windows, so the SC-vs-incumbent comparison this study exists
        to make is unaffected), and `incumbent_reconciliation` now computes the
        incumbent's exact statistic on this same sample and prints it beside the
        house's 2019→ grade.
  AM-8  The charter (§3#5) specifies matching on "pre-event path/vol/beta/sector/size/
        liquidity". This implementation matches on pre-window return CORRELATION (which
        subsumes path and, for a returns fit, beta), a vol-similarity band, liquidity and
        price. SECTOR and SIZE are NOT matched on: the repo holds no whole-market sector
        or share-count classifier for the 19k-name store (data/sector_holdings covers 236
        S&P 500 names — AM-2). A fitted replicating portfolio recovers sector exposure
        implicitly through correlation; that is a weaker claim than an explicit screen
        and is stated rather than skipped.
  AM-9  PC-1's "CAAR > 0" is evaluated on BOTH the event-weighted and month-weighted
        means. `monthly_nw` returns an event-weighted mean beside a month-weighted t;
        with quarterly-batched reconstitutions the two can disagree in sign. Requiring
        both to be positive is strictly stronger than the registered single-mean form.
  AM-10 The placebo exclusion band is ASYMMETRIC, [s-20, s+125], not the symmetric ±42
        first written. A placebo at s' fits its donors on [s'-125, s'-6], so s' in
        [s+42, s+125] passed the symmetric guard while FITTING on a window containing the
        real event — 9.6% of otherwise-eligible dates. That contaminates only the two SC
        arms (the benchmark arm fits nothing) and PC-3 is exactly an SC-vs-benchmark
        dispersion test, so the original guard biased the gate it was meant to support.
  AM-11 The $5 floor is applied to the close AS PRINTED, not the back-adjusted close.
        split_adjust back-multiplies prior bars by a factor detected later in the series,
        which is not PIT and inverts the selection: a raw $0.60 name that later
        reverse-splits 1:10 reads as $6.00 (admitted), a raw $8.00 name that later splits
        10:1 reads as $0.80 (excluded). Sub-$1 names are the dominant reverse-split case,
        i.e. exactly what AM-3 exists to remove.

EXECUTION: MANUAL, OFF THE RENDER PATH. This is not wired into daily.yml, render.yml or
config/dag.yml and must never be — a full run is ~95 minutes against the whole 20k-file
store, roughly 1.5x the entire nightly render budget (HOUSE-U6: heavy compute off the
render path). It is run by hand when the estimator or the event families change.

Run:    python -m scripts.synthetic_control_phase0
Writes: research/SYNTHETIC_CONTROL_PHASE0.md
        data/experiments/synthetic_control_phase0_results.json
        data/trial_ledger.jsonl  (family synthetic_control_phase0)
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import math
import os
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

if __name__ == "__main__":
    # Narrow on purpose: a numerics study wants numpy's invalid/divide RuntimeWarnings
    # VISIBLE. Only the noisy third-party import chatter is suppressed.
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    logging.disable(logging.INFO)

WT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT_ROOT))

from collectors.massive_stock_day import (          # noqa: E402
    StaleLocalMirrorError, check_local_mirror_freshness)
from engine import synthetic_control as sc          # noqa: E402
from engine import validation as V                  # noqa: E402
from engine.index_changes import classify_cohort, load_gate, pit_history   # noqa: E402
from engine.trial_ledger import TrialLedger         # noqa: E402
from scripts.replay_standout_pipeline import split_adjust       # noqa: E402

FAMILY = "synthetic_control_phase0"
LEDGER_PATH = WT_ROOT / "data" / "trial_ledger.jsonl"
RESULTS_JSON = WT_ROOT / "data" / "experiments" / "synthetic_control_phase0_results.json"
WRITEUP_MD = WT_ROOT / "research" / "SYNTHETIC_CONTROL_PHASE0.md"

# ---- frozen study constants (see pre-registration above) -------------------------
SCOPE_START = "2022-01-01"
ANNOUNCE_LEAD = 5          # index adds: event day = effective - 5 sessions
PLACEBO_DRAWS = 200
# NOTE: there is deliberately no PLACEBO_GUARD constant. The placebo exclusion band is
# ASYMMETRIC and derived from the windows themselves — [s-POST_WINDOW, s+PRE_WINDOW+EMBARGO]
# — in eligible_placebo_sessions(). A scalar guard existed here once, was superseded by
# AM-10, and survived as a dead constant that the results JSON kept publishing as if it
# were the live rule. Derive the band, never restate it.
PRICE_MIN = 5.0
POST_WINDOW = 20           # sessions after t that must exist
BENCH_SPY = "SPY"
BENCH_SECTOR_PHASE3 = "XLV"
MIN_EVENTS = 15            # below this the widened-variant fallback is disclosed
GATE_PLACEBO_BIAS = 0.003  # PC-2: |placebo mean| < 0.3%
SEED = 20260806


# ================================================================== data root + loading
# Ladder + loader shape copied from scripts/pick_forward_dist_phase0.py (wave-1 sibling);
# kept local rather than imported so the two PRs do not couple.
def resolve_data_root(arg: str | None) -> Path | None:
    """--data-root -> $MACRO_PRIMARY_DATA -> <repo>/data/massive_stock_day -> primary
    checkout. A root counts only if it actually holds parquets (the worktree carries the
    manifest but not the store)."""
    cands = []
    if arg:
        cands.append(Path(arg).expanduser())
    env = os.environ.get("MACRO_PRIMARY_DATA")
    if env:
        p = Path(env).expanduser()
        cands += [p, p / "massive_stock_day"]
    cands.append(WT_ROOT / "data" / "massive_stock_day")
    cands.append(Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day"))
    for c in cands:
        try:
            if c.is_dir() and any(c.glob("*.parquet")):
                return c
        except OSError:
            continue
    return None


@dataclass
class Panel:
    """Shared-calendar return panel. Sessions are integer indices into `dates`."""
    dates: pd.DatetimeIndex
    tickers: list[str]
    ret: np.ndarray            # (T, N) simple daily returns, NaN where absent
    dvol20: np.ndarray         # (T, N) 20d median dollar volume
    close: np.ndarray          # (T, N) split-ADJUSTED close (returns, presence checks)
    raw_close: np.ndarray | None = None   # (T, N) close AS PRINTED (the $5 floor)
    col: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if not self.col:
            self.col = {t: i for i, t in enumerate(self.tickers)}

    @property
    def n_sessions(self) -> int:
        return len(self.dates)


def build_panel(store: Path, *, max_names: int | None = None,
                extra: tuple[str, ...] = (BENCH_SPY, BENCH_SECTOR_PHASE3),
                verbose: bool = True) -> tuple[Panel, dict]:
    """Read the store, split-repair, and assemble a shared-calendar return panel.

    Prefilter is removal-only and strictly weaker than the donor rule it anticipates: a
    name is kept if it ever printed above the price floor and ever cleared the dollar
    volume floor on a single bar (a 20d median can never exceed the max). Benchmarks in
    `extra` are always kept.
    """
    paths = sorted(glob.glob(str(store / "*.parquet")))
    if max_names:
        keep_paths = [p for p in paths if Path(p).stem in extra]
        paths = keep_paths + [p for p in paths if Path(p).stem not in extra][:max_names]
    stats = {"files": len(paths), "read_ok": 0, "kept": 0, "split_repaired": 0}
    frames: dict[str, pd.DataFrame] = {}
    for i, p in enumerate(paths):
        if verbose and i and i % 5000 == 0:
            print(f"    {i:,}/{len(paths):,} read, {len(frames):,} kept", flush=True)
        stem = Path(p).stem
        try:
            df = pd.read_parquet(p, columns=["close", "volume"])
        except Exception:
            continue
        stats["read_ok"] += 1
        if len(df) < 60:
            continue
        close = df["close"]
        forced = stem in extra
        if not forced:
            if not (close > PRICE_MIN).any():
                continue
            if float((close * df["volume"]).max()) < sc.DVOL_FLOOR:
                continue
        adj = split_adjust(close)
        with np.errstate(invalid="ignore", divide="ignore"):
            factor = (close / adj).replace([np.inf, -np.inf], np.nan)
        if float(np.nanmax(factor) / max(float(np.nanmin(factor)), 1e-12)) > 1.0001:
            stats["split_repaired"] += 1
        vol = df["volume"] * factor          # shares scale inversely to price
        frames[stem] = pd.DataFrame({"close": adj, "dvol": adj * vol, "raw": close})
    stats["kept"] = len(frames)
    if not frames:
        return Panel(pd.DatetimeIndex([]), [], np.zeros((0, 0)), np.zeros((0, 0)),
                     np.zeros((0, 0))), stats

    dates = pd.DatetimeIndex(sorted({d for f in frames.values() for d in f.index}))
    tickers = sorted(frames)
    n_t, n_n = len(dates), len(tickers)
    close = np.full((n_t, n_n), np.nan)
    raw_close = np.full((n_t, n_n), np.nan)
    dvol = np.full((n_t, n_n), np.nan)
    for j, t in enumerate(tickers):
        f = frames[t].reindex(dates)
        close[:, j] = f["close"].to_numpy(dtype=float)
        raw_close[:, j] = f["raw"].to_numpy(dtype=float)
        dvol[:, j] = f["dvol"].to_numpy(dtype=float)

    ret = np.full((n_t, n_n), np.nan)
    ret[1:] = close[1:] / close[:-1] - 1.0
    # 20d MEDIAN dollar volume, causal (window ends at the bar, inclusive)
    dv20 = (pd.DataFrame(dvol).rolling(20, min_periods=10).median()).to_numpy(dtype=float)
    stats["sessions"] = n_t
    stats["names"] = n_n
    stats["calendar"] = (str(dates[0].date()), str(dates[-1].date()))
    return Panel(dates, tickers, ret, dv20, close, raw_close), stats


# ================================================================== event construction
def sp_pure_add_events(panel: Panel, data_dir: Path) -> tuple[pd.DataFrame, dict]:
    """Pure S&P adds — the family the house graded at +1.64% / t=4.63.

    Event list reproduces scripts/validate_index_reconstitution.py:load_events +
    engine.index_changes.classify_cohort (AM-1). Event day t = effective - 5 sessions.
    """
    pit = pd.read_parquet(data_dir / "breadth" / "sp1500_pit_membership.parquet")
    pit["start_date"] = pd.to_datetime(pit["start_date"], errors="coerce")
    adds = pit.dropna(subset=["start_date"])[["ticker", "start_date", "src"]].copy()
    adds.columns = ["ticker", "d", "index"]
    adds["ticker"] = adds["ticker"].astype(str).str.upper()
    adds = adds.dropna(subset=["d", "ticker"])
    diag = {"raw_adds_all_time": int(len(adds))}

    # pit_history() resolves its own path through engine.config.data_dir(). Assert it
    # agrees with the data_dir this study reads, so a study run against one checkout can
    # never classify cohorts from another's membership file.
    pit_by_t = pit_history()
    if pit_by_t:
        n_pit = sum(len(v) for v in pit_by_t.values())
        if n_pit != len(pit):
            print(f"[warn] pit_history() returned {n_pit} rows but {data_dir} holds "
                  f"{len(pit)} — engine.config.data_dir() resolves elsewhere; cohort "
                  f"labels may not match this study's event list", flush=True)
    adds["cohort"] = [classify_cohort(r.ticker, r.d, r.index, pit_by_t)
                      for r in adds.itertuples(index=False)]
    diag["cohort_counts"] = {k: int(v) for k, v in adds["cohort"].value_counts().items()}
    pure = adds[adds["cohort"] == "pure"].copy()
    diag["pure_all_time"] = int(len(pure))
    pure = pure[pure["d"] >= SCOPE_START]
    diag["pure_in_scope_date"] = int(len(pure))

    ev = _attach_sessions(panel, pure, lead=ANNOUNCE_LEAD)
    diag["events_usable"] = int(len(ev))
    diag["event_day_rule"] = "effective_date - 5 sessions (announce proxy)"
    return ev, diag


def phase3_events(panel: Panel, data_dir: Path) -> tuple[pd.DataFrame, dict]:
    """ClinicalTrials Phase-3 STARTs — the family the house graded NULL twice.

    Collapsed to ticker-date cells (AM-6); date semantics = StudyFirstPostDate.
    """
    p = data_dir / "clinicaltrials" / "trials.parquet"
    if not p.exists():
        return pd.DataFrame(columns=["ticker", "d"]), {"error": f"missing {p}"}
    tr = pd.read_parquet(p)
    diag = {"raw_rows": int(len(tr)), "uniq_nct": int(tr["nct"].nunique())}
    tr = tr[tr["phases"].astype(str).str.contains("PHASE3", na=False)]
    tr["d"] = pd.to_datetime(tr["first_post"], errors="coerce")
    tr["ticker"] = tr["ticker"].astype(str).str.upper()
    tr = tr.dropna(subset=["d", "ticker"])
    diag["phase3_rows"] = int(len(tr))
    cells = tr.groupby(["ticker", "d"], as_index=False).size()
    cells = cells.rename(columns={"size": "n_nct"})
    diag["ticker_date_cells_all_time"] = int(len(cells))
    cells = cells[cells["d"] >= SCOPE_START]
    diag["cells_in_scope_date"] = int(len(cells))
    diag["sponsors"] = int(cells["ticker"].nunique())

    ev = _attach_sessions(panel, cells, lead=0)
    diag["events_usable"] = int(len(ev))
    diag["event_day_rule"] = "StudyFirstPostDate (first public availability)"
    return ev, diag


def _attach_sessions(panel: Panel, ev: pd.DataFrame, *, lead: int) -> pd.DataFrame:
    """Map each event date onto the shared calendar and keep only events with a full
    pre-window, embargo and post-window inside the store."""
    if ev.empty or panel.n_sessions == 0:
        return pd.DataFrame(columns=["ticker", "col", "sess", "date"])
    out = ev.copy()
    pos = panel.dates.searchsorted(pd.to_datetime(out["d"]), side="left")
    out["sess"] = pos.astype(int) - int(lead)
    out["col"] = out["ticker"].map(panel.col)
    need_pre = sc.PRE_WINDOW + sc.EMBARGO
    ok = (out["col"].notna()
          & (pos < panel.n_sessions)
          & (out["sess"] >= need_pre)
          & (out["sess"] < panel.n_sessions - POST_WINDOW))
    out = out[ok].copy()
    out["col"] = out["col"].astype(int)
    out["date"] = panel.dates[out["sess"].to_numpy()]
    # one event per (ticker, session): a name cannot be treated twice on one day
    out = out.sort_values(["ticker", "sess"]).drop_duplicates(["ticker", "sess"])
    return out.reset_index(drop=True)[["ticker", "col", "sess", "date"]]


def contamination_map(panel: Panel, ev: pd.DataFrame, exclusion: int) -> np.ndarray:
    """(T, N) bool — True where a name has an event of its own within +/- `exclusion`
    sessions. A contaminated donor imports the treatment into the counterfactual."""
    n_t, n_n = panel.ret.shape
    flag = np.zeros((n_t, n_n), dtype=bool)
    if ev.empty:
        return flag
    flag[ev["sess"].to_numpy(), ev["col"].to_numpy()] = True
    # dilate +/- exclusion along the session axis via a windowed cumulative sum
    cs = np.zeros((n_t + 1, n_n), dtype=np.int32)
    cs[1:] = np.cumsum(flag, axis=0, dtype=np.int32)
    lo = np.clip(np.arange(n_t) - exclusion, 0, n_t)
    hi = np.clip(np.arange(n_t) + exclusion + 1, 0, n_t)
    return (cs[hi] - cs[lo]) > 0


# ================================================================== estimation core
def estimate_events(
    panel: Panel,
    cols: np.ndarray,
    sessions: np.ndarray,
    contaminated: np.ndarray,
    *,
    benchmarks: dict[str, np.ndarray] | None = None,
) -> dict[str, np.ndarray]:
    """Run every arm on one set of (name, event-session) pairs.

    Returns {arm: (E, n_windows) CARs} for arms 'matched_k', 'sc_nnls' and each supplied
    benchmark. One pass builds the donor pool and the correlation ranking ONCE and feeds
    both SC estimators from it — the ranking is shared, so this is exactly equivalent to
    running them separately and roughly halves the placebo cost.
    """
    e = len(cols)
    win = sc.CAR_WINDOWS
    keys = [f"{a}" if a == b else f"{a}_{b}" for a, b in win]
    arms = ["matched_k", "sc_nnls"] + sorted(benchmarks or {})
    out = {a: np.full((e, len(keys)), np.nan) for a in arms}
    if e == 0:
        return {"_keys": keys, **out}

    m = sc.PRESCREEN_M
    pre_t = np.zeros((e, sc.PRE_WINDOW))
    pre_d = np.zeros((e, sc.PRE_WINDOW, m))
    post_t = np.full((e, POST_WINDOW + 1), np.nan)
    post_d = np.zeros((e, POST_WINDOW + 1, m))
    n_sel = np.zeros(e, dtype=int)
    pool_sizes = np.zeros(e, dtype=int)
    # PANEL column index of each selected donor, in the pre-screen's rank order. Kept so
    # the harness's own donor selection is auditable from outside (weights alone live in
    # the m-wide selected space and cannot be checked against the panel).
    sel_cols = np.full((e, m), -1, dtype=int)

    drops = {"treated_pre_window_gap": 0, "thin_pool": 0, "thin_prescreen": 0}
    for i in range(e):
        c, s = int(cols[i]), int(sessions[i])
        sl = sc.pre_window_slice(s)
        pre = panel.ret[sl, :]
        y = pre[:, c]
        if not np.isfinite(y).all():
            # The treated name has a hole in its own fitting window. On this store the
            # dominant cause is SYMBOL DISCONTINUITY, not illiquidity: massive_stock_day
            # keys by CURRENT symbol, so a renamed/merged name (PARA, ELV, GEHC, WBD,
            # BALL, RVTY, WTW) carries its history only under whichever symbol it holds
            # today, and even a survivor like META shows a multi-month hole.
            drops["treated_pre_window_gap"] += 1
            continue
        end = sl.stop - 1                       # last session inside the pre-window
        mask = sc.eligible_donors(
            donor_pre=pre,
            donor_dvol=panel.dvol20[end, :],
            event_distance=np.where(contaminated[s, :], 0.0, np.inf),
            treated_col=c,
        )
        # $5 floor on the close AS PRINTED, not the back-adjusted one. split_adjust
        # back-multiplies every prior bar by a factor detected LATER in the series, so an
        # adjusted-price floor is not PIT and inverts the exact selection AM-3 wants: a
        # raw $0.60 name that later reverse-splits 1:10 reads as $6.00 and would be
        # ADMITTED, while a raw $8.00 name that later splits 10:1 reads as $0.80 and
        # would be EXCLUDED. The sub-$1 case is the dominant one for reverse splits.
        px = panel.raw_close if panel.raw_close is not None else panel.close
        mask &= np.isfinite(panel.close[end, :]) & (px[end, :] > PRICE_MIN)
        idx = np.flatnonzero(mask)
        pool_sizes[i] = idx.size
        if idx.size < m:
            drops["thin_pool"] += 1
            continue
        sub = pre[:, idx]
        sub = np.where(np.isfinite(sub), sub, 0.0)
        sel_local = sc.prescreen_donors(y, sub, m=m)
        if sel_local.size < m:
            drops["thin_prescreen"] += 1
            continue
        cols_sel = idx[sel_local]
        pre_t[i] = y
        pre_d[i] = pre[:, cols_sel]
        post_t[i] = panel.ret[s:s + POST_WINDOW + 1, c]
        post_d[i] = panel.ret[s:s + POST_WINDOW + 1, cols_sel]
        sel_cols[i] = cols_sel
        n_sel[i] = m

    live = n_sel > 0
    if not live.any():
        return {"_keys": keys, "_n_live": 0, "_pool_mean": 0.0, "_drops": drops,
                **{a: out[a] for a in arms}}

    # A missing donor print inside the fitting window is filled with a zero return: for a
    # buy-and-hold donor a non-trading day IS a zero return, and the >=90% coverage rule
    # caps this at 12 of 120 sessions. The solver requires finite input.
    pre_d = np.where(np.isfinite(pre_d), pre_d, 0.0)
    li = np.flatnonzero(live)

    # matched_k: equal weight over the top-k. prescreen_donors returns columns in
    # correlation rank order, so the first MATCHED_K columns of pre_d ARE the top-k the
    # equal-weight estimator selects. Pinned END-TO-END THROUGH THIS FUNCTION by
    # tests/test_synthetic_control.py::test_harness_recovers_a_known_mixture_end_to_end
    # (test_matched_k_is_top_k_of_the_prescreen pins the module in isolation and never
    # calls estimate_events, so it cannot see a defect introduced on this path).
    w_mk = np.zeros((li.size, m))
    w_mk[:, : sc.MATCHED_K] = 1.0 / sc.MATCHED_K
    # sc_nnls: simplex-constrained LS over all M
    w_sc = sc.solve_simplex_ls_batch(pre_t[li], pre_d[li])

    for arm, w in (("matched_k", w_mk), ("sc_nnls", w_sc)):
        cf = sc.counterfactual_path(w, post_d[li])
        res = sc.effect(post_t[li], cf)
        for j, k in enumerate(keys):
            out[arm][li, j] = res["car"][k]

    for bname, bret in (benchmarks or {}).items():
        for j, (a, b) in enumerate(win):
            seg_t = post_t[li][:, a:b + 1]
            bseg = np.stack([bret[int(sessions[i]) + a: int(sessions[i]) + b + 1]
                             for i in li])
            d = seg_t - bseg
            good = np.isfinite(d).all(axis=1)
            vals = np.where(good, np.nansum(d, axis=1), np.nan)
            out[bname][li, j] = vals

    return {"_keys": keys, "_n_live": int(li.size), "_drops": drops,
            "_pool_mean": float(pool_sizes[live].mean()) if live.any() else 0.0,
            "_weights": {"matched_k": w_mk, "sc_nnls": w_sc}, "_live_idx": li,
            "_sel_cols": sel_cols[li],
            **{a: out[a] for a in arms}}


# ================================================================== inference helpers
def monthly_nw(car: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    """Monthly-clustered Newey-West — byte-identical stats law to the incumbent
    index-reconstitution study (group by month, mean, NW lags=min(4, max(1, n//4)))."""
    good = np.isfinite(car)
    if good.sum() < 10:
        return {"n": int(good.sum()), "mean": None, "t": None, "p": None, "n_months": 0}
    df = pd.DataFrame({"car": car[good], "mo": pd.DatetimeIndex(dates[good]).to_period("M")})
    monthly = df.groupby("mo")["car"].mean()
    nw = V.newey_west_tstat(monthly.to_numpy(), lags=min(4, max(1, len(monthly) // 4)))
    # `mean` is EVENT-weighted (what the incumbent prints) but `t` is MONTH-weighted (the
    # clustering that makes it valid). S&P reconstitutions batch quarterly, so month
    # counts are very unequal and the two can disagree in SIGN. Both are printed, and
    # PC-1's ">0" reads mean_monthly — the estimand the t actually tests.
    return {"n": int(good.sum()), "n_months": int(len(monthly)),
            "mean": float(np.mean(car[good])), "mean_monthly": float(monthly.mean()),
            "t": nw.get("t"), "p": nw.get("p"),
            "hit_rate": float((car[good] > 0).mean())}


def ticker_cluster_t(car: np.ndarray, tickers: np.ndarray) -> float | None:
    """Cluster-robust t on the mean, clustering by ticker (the Phase-3 prior study's
    statistic — 19 sponsor clusters there)."""
    good = np.isfinite(car)
    if good.sum() < 10:
        return None
    x, g = car[good], np.asarray(tickers)[good]
    mean = float(x.mean())
    uniq = pd.unique(g)
    if len(uniq) < 2:
        return None
    n = x.size
    sums = np.array([float((x[g == u] - mean).sum()) for u in uniq])
    var = float((sums ** 2).sum()) / (n ** 2)
    se = float(np.sqrt(max(var, 1e-24)))
    corr = len(uniq) / max(len(uniq) - 1.0, 1.0)
    return float(mean / se * np.sqrt(1.0 / corr)) if se > 0 else None


def eligible_placebo_sessions(panel: Panel, col: int, real_sess: int) -> np.ndarray:
    """Sessions where this name could host a placebo event.

    Requires a full pre-window + embargo + post-window inside the store, price data
    present, and — the part that matters — a placebo date whose OWN windows are clear of
    the real event s.

    The exclusion is ASYMMETRIC because the two windows sit on opposite sides of the
    event day. For a placebo at s':
        outcome window [s', s'+POST_WINDOW]      contains s  <=>  s-POST_WINDOW <= s' <= s
        FIT window     [s'-125, s'-EMBARGO-1]    contains s  <=>  s+EMBARGO+1 <= s' <= s+125
    so the excluded band is [s-POST_WINDOW, s+PRE_WINDOW+EMBARGO].

    A symmetric +/-42 guard (the earlier form) covers the outcome window but leaves
    s' in [s+42, s+125] admissible — 9.6% of otherwise-eligible placebo dates FIT THE
    DONORS on a window containing the real treatment. That contaminates only the two SC
    arms (the benchmark arm has no fit), and PC-3 is precisely an SC-vs-benchmark
    dispersion comparison, so the earlier guard biased the gate it was meant to support.
    """
    lo = sc.PRE_WINDOW + sc.EMBARGO
    hi = panel.n_sessions - POST_WINDOW - 1
    if hi <= lo:
        return np.zeros(0, dtype=int)
    cand = np.arange(lo, hi + 1)
    contaminated = ((cand >= real_sess - POST_WINDOW)
                    & (cand <= real_sess + sc.PRE_WINDOW + sc.EMBARGO))
    cand = cand[~contaminated]
    if cand.size == 0:
        return cand
    ok = np.isfinite(panel.close[cand, col])
    return cand[ok]


# ================================================================== the study
def run_family(panel: Panel, ev: pd.DataFrame, label: str, *,
               benchmarks: dict[str, np.ndarray], draws: int, rng: np.random.Generator,
               verbose: bool = True) -> dict:
    """Real estimate + placebo null for one event family, every arm."""
    t0 = time.time()
    cols = ev["col"].to_numpy()
    sess = ev["sess"].to_numpy()
    contaminated = contamination_map(panel, ev, sc.EVENT_EXCLUSION)

    real = estimate_events(panel, cols, sess, contaminated, benchmarks=benchmarks)
    keys = real["_keys"]
    arms = ["matched_k", "sc_nnls"] + sorted(benchmarks)
    if verbose:
        print(f"  [{label}] real estimate: {real['_n_live']}/{len(ev)} events fitted, "
              f"mean eligible donor pool {real['_pool_mean']:.0f} "
              f"({time.time() - t0:.1f}s)", flush=True)

    stats: dict = {"n_events": int(len(ev)), "n_fitted": int(real["_n_live"]),
                   "n_dropped_unfitted": int(len(ev) - real["_n_live"]),
                   "drop_reasons": dict(real.get("_drops", {})),
                   "mean_donor_pool": round(float(real["_pool_mean"]), 1),
                   "windows": keys, "arms": {}}
    for arm in arms:
        per_win = {}
        # A ticker-clustered t is only a CLUSTERED statistic when tickers actually repeat.
        # Index adds are one-per-name, so every cluster is a singleton and the estimator
        # collapses to the plain iid t the pre-registration itself calls invalid here.
        # Suppressed rather than printed with a caveat nobody reads.
        n_ev_ = int(len(ev))
        n_tk_ = int(ev["ticker"].nunique()) if n_ev_ else 0
        clusters_meaningful = bool(n_ev_ and n_tk_ < 0.75 * n_ev_)
        for j, k in enumerate(keys):
            car = real[arm][:, j]
            s = monthly_nw(car, pd.DatetimeIndex(ev["date"]))
            s["ticker_cluster_t"] = (ticker_cluster_t(car, ev["ticker"].to_numpy())
                                     if clusters_meaningful else None)
            per_win[k] = s
        stats["arms"][arm] = {"real": per_win}
    stats["n_tickers"] = int(ev["ticker"].nunique()) if len(ev) else 0
    stats["ticker_cluster_t_reported"] = bool(
        len(ev) and stats["n_tickers"] < 0.75 * len(ev))

    # ---- placebo: re-date every event, `draws` times
    cand = [eligible_placebo_sessions(panel, int(c), int(s)) for c, s in zip(cols, sess)]
    usable = np.array([c.size > 0 for c in cand])
    # An event with NO eligible placebo date must be DROPPED from the null, not left at
    # its real session — keeping it injects the real effect into every one of the `draws`
    # replications and drags the placebo mean toward the real answer.
    keep = np.flatnonzero(usable)
    p_cols, p_sess_real = cols[keep], sess[keep]
    p_cand = [cand[i] for i in keep]
    stats["placebo_events"] = int(keep.size)
    stats["placebo_events_dropped"] = int(len(ev) - keep.size)
    if verbose:
        print(f"  [{label}] placebo: {draws} replications over "
              f"{int(usable.sum())}/{len(ev)} re-datable events "
              f"({len(ev) - keep.size} dropped as un-re-datable)", flush=True)
    null = {a: np.full((draws, len(keys)), np.nan) for a in arms}
    draw_fitted = np.zeros(draws, dtype=int)
    tp = time.time()
    for d in range(draws):
        psess = p_sess_real.copy()
        for i, c in enumerate(p_cand):
            psess[i] = c[rng.integers(c.size)]
        est = estimate_events(panel, p_cols, psess, contaminated, benchmarks=benchmarks)
        draw_fitted[d] = int(est["_n_live"])
        for arm in arms:
            for j in range(len(keys)):
                v = est[arm][:, j]
                null[arm][d, j] = float(np.nanmean(v)) if np.isfinite(v).any() else np.nan
        if verbose and (d + 1) % 25 == 0:
            el = time.time() - tp
            print(f"    {d + 1}/{draws} draws ({el:.0f}s, "
                  f"eta {el / (d + 1) * (draws - d - 1):.0f}s)", flush=True)

    for arm in arms:
        for j, k in enumerate(keys):
            dn = null[arm][:, j]
            dn = dn[np.isfinite(dn)]
            real_mean = float(np.nanmean(real[arm][:, j])) if np.isfinite(real[arm][:, j]).any() else np.nan
            blk = {"n_draws": int(dn.size),
                   "placebo_mean": float(dn.mean()) if dn.size else None,
                   "placebo_sd": float(dn.std(ddof=1)) if dn.size > 1 else None,
                   "real_caar": real_mean if np.isfinite(real_mean) else None}
            if dn.size > 1 and np.isfinite(real_mean):
                se = dn.std(ddof=1) / np.sqrt(dn.size)
                blk["placebo_bias_t"] = float(dn.mean() / se) if se > 0 else None
                # Two-sided empirical p of the real CAAR against the placebo null, with
                # the (1 + #)/(B + 1) permutation correction: without it the minimum
                # attainable value is 0.0, which reads as "impossible under the null"
                # when the honest statement is p < 1/(B+1). NOTE the null being tested is
                # "effect == placebo mean", not "effect == 0" — the distribution is
                # centred on its own mean before the comparison.
                centred = np.abs(dn - dn.mean())
                hits = int((centred >= abs(real_mean - dn.mean())).sum())
                blk["empirical_p"] = float((1 + hits) / (dn.size + 1))
                blk["empirical_p_floor"] = float(1.0 / (dn.size + 1))
            stats["arms"][arm].setdefault("placebo", {})[k] = blk

    # Per-draw placebo CAARs are PERSISTED so the PC-3 dispersion ratio can carry an
    # interval. The two arms are measured on the SAME draws (identical placebo dates), so
    # the comparison is paired and the paired form is the honest one — an unpaired SD
    # comparison throws away exactly the correlation that makes the test sharp.
    stats["placebo_draws_detail"] = {
        "windows": keys,
        "n_fitted_per_draw": {"mean": float(draw_fitted.mean()),
                              "min": int(draw_fitted.min()),
                              "max": int(draw_fitted.max())},
        "caar_by_arm": {a: [None if not np.isfinite(x) else round(float(x), 8)
                            for x in null[a][:, keys.index("0_5")]] for a in arms},
    }
    stats["pc3_dispersion"] = _pc3_dispersion(null, keys, arms)
    stats["runtime_s"] = round(time.time() - t0, 1)
    return stats


def _pc3_dispersion(null: dict, keys: list, arms: list) -> dict:
    """PC-3's SD ratio with an interval, computed on PAIRED draws at [0,5].

    PC-3 compares sc_nnls's placebo dispersion against the incumbent's. Both are measured
    on identical placebo dates, so the per-draw CAARs are paired and their difference is
    what carries the information. Reported: the raw ratio, a bootstrap CI on it, and the
    paired test on squared deviations (the variance-difference the ratio summarizes).
    """
    j = keys.index("0_5")
    if "sc_nnls" not in arms or BENCH_SPY not in arms:
        return {}
    a = null["sc_nnls"][:, j]
    b = null[BENCH_SPY][:, j]
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    if a.size < 20:
        return {"n_draws": int(a.size)}
    sd_a, sd_b = float(a.std(ddof=1)), float(b.std(ddof=1))
    da, db = a - a.mean(), b - b.mean()
    # paired difference of squared deviations: mean < 0 means SC is tighter
    diff = da ** 2 - db ** 2
    se = float(diff.std(ddof=1) / np.sqrt(diff.size))
    rng = np.random.default_rng(SEED + 1)
    boot = []
    for _ in range(2000):
        idx = rng.integers(0, a.size, a.size)          # paired resample
        boot.append(a[idx].std(ddof=1) / max(b[idx].std(ddof=1), 1e-18))
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return {"n_draws": int(a.size), "sd_sc_nnls": sd_a, "sd_benchmark": sd_b,
            "ratio": sd_a / sd_b if sd_b else None,
            "ratio_ci95_paired_bootstrap": [float(lo), float(hi)],
            "paired_var_diff_t": float(diff.mean() / se) if se > 0 else None,
            "note": "ratio < 1 means synthetic control is tighter under the null. The CI "
                    "is a paired bootstrap over draws; the t is a paired test on squared "
                    "deviations. PC-3 itself is registered as a bare point comparison, so "
                    "these quantify it rather than re-decide it."}


# ================================================================== gates
def evaluate_gates(pc: dict, fl: dict | None) -> dict:
    """PC-1/PC-2/PC-3/F-1 exactly as pre-registered. A failed gate is a result."""
    g: dict = {}
    reasons: dict[str, str] = {}

    def _get(fam, arm, kind, win, field):
        try:
            return fam["arms"][arm][kind][win][field]
        except (KeyError, TypeError):
            return None

    # PC-1 — positive control survives under sc_nnls at [0,5].
    # AM-9: the registered text says "CAAR > 0". Two CAARs exist — event-weighted (what
    # the incumbent prints) and month-weighted (the estimand the monthly-NW t tests) —
    # and with quarterly-batched reconstitutions they can disagree in sign. Both must be
    # positive. That is strictly STRONGER than the registered single-mean form, so it
    # cannot be a loosening after the fact.
    m = _get(pc, "sc_nnls", "real", "0_5", "mean")
    mm = _get(pc, "sc_nnls", "real", "0_5", "mean_monthly")
    t = _get(pc, "sc_nnls", "real", "0_5", "t")
    if None in (m, mm, t):
        # An absent positive-control family is a data-reach failure. Reporting it as FAIL
        # publishes ESTIMATOR_POWERLESS — "synthetic control erased a graded effect" —
        # when the truth is that the effect was never measured.
        g["PC1_positive_control_survives"] = None
        reasons["PC1"] = ("NOT EVALUABLE — the S&P pure-add family produced no estimate "
                          "(no events in scope, or the price store was unreachable)")
    else:
        g["PC1_positive_control_survives"] = bool(m > 0 and mm > 0 and t > 2.0)
        reasons["PC1"] = (f"sc_nnls S&P pure-add CAAR[0,5]={_pct(m)} event-weighted / "
                          f"{_pct(mm)} month-weighted, monthly-NW t={_r(t)} "
                          "(need both >0 and t>2)")

    # PC-2 — neither SC estimator is biased under the null, on BOTH families
    pc2, bits, pc2_skipped = True, [], []
    for fam, name in ((pc, "sp_pure_adds"), (fl, "phase3_start")):
        if not fam:
            # registered as "on BOTH families" — a skipped family must be SAID, not
            # quietly dropped from a conjunction that then reads as fully evaluated
            pc2_skipped.append(name)
            bits.append(f"{name} NOT EVALUATED")
            continue
        for arm in ("matched_k", "sc_nnls"):
            pm = _get(fam, arm, "placebo", "0_5", "placebo_mean")
            bt = _get(fam, arm, "placebo", "0_5", "placebo_bias_t")
            ok = (pm is not None and bt is not None
                  and abs(pm) < GATE_PLACEBO_BIAS and abs(bt) < 2.0)
            pc2 &= ok
            bits.append(f"{name}/{arm} mean={_pct(pm)} t={_r(bt)}{'' if ok else ' FAIL'}")
    g["PC2_estimators_unbiased"] = None if pc2_skipped else bool(pc2)
    reasons["PC2"] = "; ".join(bits) + f" (need |mean|<{GATE_PLACEBO_BIAS:.1%} and |t|<2 "
    reasons["PC2"] += f"on BOTH families; {len(pc2_skipped)} family not evaluated)" \
        if pc2_skipped else "on BOTH families)"

    # PC-3 — sc_nnls placebo dispersion <= benchmark-CAR(SPY) placebo dispersion at [0,5]
    sd_sc = _get(pc, "sc_nnls", "placebo", "0_5", "placebo_sd")
    sd_bm = _get(pc, BENCH_SPY, "placebo", "0_5", "placebo_sd")
    if sd_sc is None or sd_bm is None:
        # A missing comparator arm is a DATA-REACH failure, not a property of the
        # estimator. Publishing it as FAIL would print "ESTIMATOR_POWERLESS" because SPY
        # was absent from the store.
        g["PC3_sc_not_noisier"] = None
        reasons["PC3"] = (f"NOT EVALUABLE — sc_nnls placebo SD={_pct(sd_sc)}, "
                          f"{BENCH_SPY}-CAR placebo SD={_pct(sd_bm)}; the comparator arm "
                          "is missing, so there is nothing to compare against")
    else:
        g["PC3_sc_not_noisier"] = bool(sd_sc <= sd_bm)
        reasons["PC3"] = (f"sc_nnls placebo SD={_pct(sd_sc)} vs {BENCH_SPY}-CAR placebo "
                          f"SD={_pct(sd_bm)} (need SC <= incumbent)")

    # F-1 — falsifier: SC must not manufacture the Phase-3 effect
    if fl is None:
        g["F1_falsifier_holds"] = None
        reasons["F1"] = "NOT RUN — Phase-3 event store unavailable"
    else:
        ft = _get(fl, "sc_nnls", "real", "0_20", "t")
        fp = _get(fl, "sc_nnls", "placebo", "0_20", "empirical_p")
        g["F1_falsifier_holds"] = bool(
            ft is not None and fp is not None and abs(ft) < 2.0 and fp > 0.05)
        reasons["F1"] = (f"phase3 sc_nnls CAAR[0,20]={_pct(_get(fl, 'sc_nnls', 'real', '0_20', 'mean'))} "
                         f"monthly-NW t={_r(ft)} empirical p={_r(fp)} (need |t|<2 and p>0.05)")

    biased = (g["PC2_estimators_unbiased"] is False) or (g["F1_falsifier_holds"] is False)
    powerless = (g["PC1_positive_control_survives"] is False) or (g["PC3_sc_not_noisier"] is False)
    unevaluated = [k for k, v in g.items() if v is None]
    if biased and powerless:
        verdict = "MIXED"
    elif biased:
        verdict = "ESTIMATOR_BIASED"
    elif powerless:
        verdict = "ESTIMATOR_POWERLESS"
    elif unevaluated:
        # A gate that never ran is not a gate that passed. Without this branch a data
        # outage on the falsifier family promotes the headline to ESTIMATOR_GO with an
        # empty failing-gate list — the loudest possible way to publish an absence.
        verdict = "INCOMPLETE"
    else:
        verdict = "ESTIMATOR_GO"
    failing = [k for k, v in g.items() if v is False]
    return {"gates": g, "reasons": reasons, "verdict": verdict,
            "failing_gates": failing, "unevaluated_gates": unevaluated}


def _r(x, nd: int = 3):
    return None if x is None else round(float(x), nd)


def _pct(x, nd: int = 3) -> str:
    return "n/a" if x is None or not np.isfinite(float(x)) else f"{100 * float(x):.{nd}f}%"


# ================================================================== reporting
def write_report(res: dict) -> None:
    WRITEUP_MD.parent.mkdir(parents=True, exist_ok=True)
    g, rs = res["gate_eval"]["gates"], res["gate_eval"]["reasons"]

    def gs(v):
        return "**PASS**" if v is True else ("**FAIL**" if v is False else "N/A")

    L: list[str] = []
    L.append("# Synthetic control for event studies — Phase-0 (wave-2a)\n")
    L.append(f"*Run {res['run_date']} · charter "
             "`research/ADVANCED_QUANT_METHODS_ADJUDICATION_BY_FABLE.md` §3#5 · "
             "frozen pre-registration in `scripts/synthetic_control_phase0.py`*\n")
    L.append("**DIAGNOSTIC TIER.** This grades an *estimator*, not a signal. No event "
             "family here is being scored for tradability; two families whose answers "
             "the house already established are used as instruments to measure whether "
             "donor-pool synthetic control tells the truth on this panel. Nothing here "
             "promotes anything or gates any surface.\n")
    L.append(f"**Run MANUALLY, off the render path.** This study is not wired into "
             f"`daily.yml`, `render.yml` or `config/dag.yml` and must not be: a full run "
             f"is ~{res['runtime_s'] / 60:.0f} minutes against the whole 20k-file store, "
             f"comfortably more than the entire nightly render budget (HOUSE-U6). It is "
             f"re-run by hand when the estimator or the event families change.\n")

    L.append(f"## Verdict: `{res['gate_eval']['verdict']}`\n")
    if res["gate_eval"]["failing_gates"]:
        L.append(f"Failing gate(s): **{', '.join(res['gate_eval']['failing_gates'])}**\n")
    if res["gate_eval"].get("unevaluated_gates"):
        L.append(f"Gate(s) NOT EVALUATED (a gate that never ran is not a gate that "
                 f"passed): **{', '.join(res['gate_eval']['unevaluated_gates'])}**\n")
    L.append("| Gate | Result | Reading |")
    L.append("|---|---|---|")
    L.append(f"| PC-1 positive control survives | {gs(g['PC1_positive_control_survives'])} | {rs['PC1']} |")
    L.append(f"| PC-2 estimators unbiased | {gs(g['PC2_estimators_unbiased'])} | {rs['PC2']} |")
    L.append(f"| PC-3 SC not noisier | {gs(g['PC3_sc_not_noisier'])} | {rs['PC3']} |")
    L.append(f"| F-1 falsifier holds | {gs(g['F1_falsifier_holds'])} | {rs['F1']} |")
    L.append("")

    L.append("## Panel\n")
    p = res["panel"]
    L.append(f"- Store: `{res['store']}` — {p['files']:,} parquet files, "
             f"{p['kept']:,} names kept after the removal-only prefilter")
    L.append(f"- Calendar: {p['calendar'][0]} → {p['calendar'][1]} ({p['sessions']:,} sessions)")
    L.append(f"- Split repairs applied to {p['split_repaired']:,} names "
             "(`scripts.replay_standout_pipeline.split_adjust`, close-only, factor carried onto volume)")
    L.append(f"- Pre-window {sc.PRE_WINDOW} sessions ending t−{sc.EMBARGO + 1}; "
             f"donor exclusion ±{sc.EVENT_EXCLUSION} sessions; coverage ≥{sc.MIN_COVERAGE:.0%}; "
             f"20d median dollar volume ≥ ${sc.DVOL_FLOOR:,.0f}; close > ${PRICE_MIN:.0f}\n")

    for key, title in (("sp_pure_adds", "Positive control — S&P pure adds"),
                       ("phase3_start", "Falsifier — ClinicalTrials Phase-3 starts")):
        fam = res["families"].get(key)
        L.append(f"## {title}\n")
        if fam is None:
            L.append(f"NOT RUN — {res['family_diag'].get(key, {}).get('error', 'unavailable')}\n")
            continue
        d = res["family_diag"][key]
        L.append(f"- Event day rule: {d.get('event_day_rule')}")
        L.append(f"- {fam['n_fitted']:,} of {fam['n_events']:,} in-scope events fitted "
                 f"(mean eligible donor pool {fam['mean_donor_pool']:,.0f} names)")
        dr = fam.get("drop_reasons") or {}
        if fam.get("n_dropped_unfitted"):
            nd_, ne_ = fam["n_dropped_unfitted"], fam["n_events"]
            L.append(
                f"- **{nd_:,} of {ne_:,} events ({100 * nd_ / ne_:.1f}%) produced no "
                f"estimate** and are absent from every number in this table: "
                f"{dr.get('treated_pre_window_gap', 0):,} because the treated name has a "
                f"hole in its own 120-session fitting window, "
                f"{dr.get('thin_pool', 0):,} for a donor pool below the pre-screen width, "
                f"{dr.get('thin_prescreen', 0):,} for a short pre-screen. The dominant "
                f"cause is SYMBOL DISCONTINUITY, not illiquidity: `massive_stock_day` "
                f"keys by CURRENT symbol, so a renamed or merged company carries history "
                f"only under the symbol it holds today (PARA, ELV, GEHC, WBD, BALL, RVTY, "
                f"WTW in this window; even META shows a multi-month hole). The headline "
                f"is therefore computed on SURVIVORS. PC-1's verdict is robust to this — "
                f"it would take an implausible reversal among the dropped events to "
                f"overturn a t of this size — but the point estimate is a survivor "
                f"statistic and is not directly comparable to the incumbent's, which "
                f"fetches prices per-ticker and keeps them.")
        if key == "sp_pure_adds":
            L.append(
                "- **Cohort labelling inherits a house defect.** "
                "`engine.index_changes.classify_cohort` calls an add \"pure\" when it "
                "finds no prior PIT membership row, which also catches ticker RENAMES and "
                "SPIN-OFFS — entities that were already inside the S&P universe under "
                "another symbol and therefore DO have an offsetting forced seller (roughly "
                "seven such names in the 2022+ window). Reproducing the incumbent's "
                "construction faithfully was the point of this control, so the defect is "
                "disclosed here and deliberately NOT fixed in this PR; fixing it would "
                "change the family and break the comparison it exists to make.")
        if not fam.get("ticker_cluster_t_reported", True):
            L.append(
                f"- Ticker-clustered t is **not reported** for this family: "
                f"{fam.get('n_tickers', 0):,} tickers across {fam['n_events']:,} events "
                f"means clusters are effectively singletons, and the estimator collapses "
                f"to the plain iid t the pre-registration itself calls invalid here.")
        L.append(f"- Scope {SCOPE_START} → panel end; construction diagnostics: "
                 f"`{json.dumps({k: v for k, v in d.items() if k != 'event_day_rule'})}`\n")
        if fam.get("placebo_events_dropped"):
            L.append(f"- Placebo null runs on {fam['placebo_events']:,} events "
                     f"({fam['placebo_events_dropped']:,} had no eligible placebo date "
                     f"and were dropped rather than left at their real session)\n")
        L.append("| Arm | Window | CAAR (event-wtd) | CAAR (month-wtd) | monthly-NW t | "
                 "ticker-cluster t | hit rate | placebo mean | placebo SD | empirical p |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for arm in fam["arms"]:
            for w in fam["windows"]:
                r = fam["arms"][arm]["real"][w]
                pl = fam["arms"][arm].get("placebo", {}).get(w, {})
                L.append(
                    f"| `{arm}` | [{w.replace('_', ',')}] | {_pct(r.get('mean'))} | "
                    f"{_pct(r.get('mean_monthly'))} | "
                    f"{_r(r.get('t'))} | {_r(r.get('ticker_cluster_t'))} | "
                    f"{_r(r.get('hit_rate'), 3)} | {_pct(pl.get('placebo_mean'))} | "
                    f"{_pct(pl.get('placebo_sd'))} | {_r(pl.get('empirical_p'))} |")
        L.append("")
        if key == "sp_pure_adds" and res.get("incumbent_reconciliation"):
            rc = res["incumbent_reconciliation"]
            if rc.get("hac_t") is not None:
                hf, hr = rc.get("house_full_sample", {}), rc.get("house_recent_cut", {})
                gap = rc.get("unexplained_gap_vs_house_recent")
                L.append("**Reconciliation against the incumbent's exact statistic.** "
                         "`validate_index_reconstitution.py` scores a SPY-relative PRICE "
                         "RATIO over [-5,0] — five daily returns, where this study's "
                         "CAR[0,5] sums six (AM-7). Recomputing the incumbent's own "
                         f"construction on THIS study's event list gives "
                         f"{_pct(rc['mean_abn'])} (t={_r(rc['hac_t'])}, n={rc['n']}, "
                         f"{rc['n_months']} months). The house publishes "
                         f"{_pct(hf.get('mean_abn'))} (t={hf.get('hac_t')}, "
                         f"n={hf.get('n')}) on 2019→ and {_pct(hr.get('mean_abn'))} "
                         f"(t={hr.get('hac_t')}, n={hr.get('n')}) on its recent cut.\n")
                if gap is not None:
                    L.append(
                        f"The recent cut is the nearest published comparator to this "
                        f"window, and **{_pct(gap)} of the difference is not explained by "
                        f"the sample period**. Index mix is ruled out (both are pure adds "
                        f"across the same three indices) and the constructions agree, so "
                        f"the residual is a coverage/construction gap — most plausibly "
                        f"the event-list attrition disclosed above, which drops "
                        f"symbol-discontinuous names the incumbent's own price fetch "
                        f"keeps. It is stated here rather than absorbed into the word "
                        f"\"sample\".\n")

    L.append("## What the numbers mean\n")
    L.append(res["narrative"])
    if res.get("gate_honesty"):
        L.append("\n## Gate honesty — what these gates can and cannot discriminate\n")
        L.append("*Written after running them, deliberately kept out of the frozen "
                 "pre-registration so the gates were not retro-fitted to the answer.*\n")
        for n in res["gate_honesty"]:
            L.append(f"- {n}")
    L.append("\n## Amendments to the frozen pre-registration\n")
    L.append("*AM-1..AM-6 were recorded while wiring, before any compute. AM-7..AM-11 came "
             "out of an adversarial review of the first full run; that run was DISCARDED "
             "and re-run under these corrections, so no number below was produced under "
             "the defective forms.*\n")
    for a in AMENDMENTS:
        L.append(f"- {a}")
    L.append("\n## Caveats carried forward\n")
    for c in res["caveats"]:
        L.append(f"- {c}")
    L.append("\n---")
    L.append(f"*Results JSON: `{RESULTS_JSON.relative_to(WT_ROOT)}` · "
             f"trial ledger family `{FAMILY}` · runtime {res['runtime_s']:.0f}s · "
             f"seed {SEED} (placebo draws are the only stochastic element).*")
    WRITEUP_MD.write_text("\n".join(L) + "\n")
    print(f"[write] {WRITEUP_MD}")


def incumbent_reconciliation(panel: Panel, ev: pd.DataFrame) -> dict:
    """Recompute the INCUMBENT's own construction on this study's in-scope sample.

    scripts/validate_index_reconstitution.py scores an add as a SPY-relative PRICE RATIO
    close[e]/close[e-5] - 1 over its [-5, 0] window — five daily returns. This study's
    CAR[0,5] sums SIX daily returns (ret[e-5..e], i.e. closes e-6 -> e), because the
    event day is set to e-5 and window [0,5] is inclusive at both ends. The two are
    therefore NOT the same window, and the prereg's "spans exactly" was an overstatement
    (AM-7). This function prints the incumbent's exact statistic on the SAME EVENT LIST
    this study fits (not the incumbent's own 2019-> event list) so the gap is measured
    rather than argued about. House reference numbers are read from
    data/index_reconstitution/validation_gate.json via engine.index_changes.load_gate(),
    never transcribed — a hardcoded reference number silently goes stale the moment the
    incumbent re-runs.
    """
    if ev.empty or BENCH_SPY not in panel.col:
        return {"error": "no events or no SPY"}
    spy = panel.close[:, panel.col[BENCH_SPY]]
    recs = []
    for r in ev.itertuples(index=False):
        e = int(r.sess) + ANNOUNCE_LEAD          # back to the effective-date session
        i0, i1 = e - 5, e
        if i0 < 0 or i1 >= panel.n_sessions:
            continue
        c = panel.close[:, int(r.col)]
        if not (np.isfinite(c[i0]) and np.isfinite(c[i1])
                and np.isfinite(spy[i0]) and np.isfinite(spy[i1])):
            continue
        recs.append((panel.dates[i1], (c[i1] / c[i0] - 1.0) - (spy[i1] / spy[i0] - 1.0)))
    if len(recs) < 10:
        return {"n": len(recs)}
    d = pd.DataFrame(recs, columns=["d", "abn"])
    s = monthly_nw(d["abn"].to_numpy(), pd.DatetimeIndex(d["d"]))

    gate = load_gate() or {}
    ann = (gate.get("announce") or {}) if isinstance(gate.get("announce"), dict) else gate
    house_full = ann.get("pure_gross") or {}
    house_recent = ann.get("pure_gross_recent") or {}

    # The house's own RECENT cut (2023-01->) is the closest thing it publishes to this
    # study's window, so it is the right comparator — the full 2019-> number differs from
    # this run for two reasons at once and quoting only that one lets "the sample" absorb
    # everything.
    out = {"window": "[-5,0] price ratio vs SPY (incumbent construction), "
                     "recomputed on THIS study's event list",
           "n": s["n"], "n_months": s["n_months"], "mean_abn": s["mean"],
           "mean_abn_monthly": s.get("mean_monthly"), "hac_t": s["t"],
           "house_full_sample": {k: house_full.get(k) for k in ("n", "mean_abn", "hac_t")},
           "house_recent_cut": {k: house_recent.get(k) for k in ("n", "mean_abn", "hac_t")},
           "house_gate_source": "data/index_reconstitution/validation_gate.json"}
    hr = house_recent.get("mean_abn")
    if hr is not None and s["mean"] is not None:
        out["unexplained_gap_vs_house_recent"] = round(float(s["mean"]) - float(hr), 5)
        out["note"] = (
            "The house's own recent cut is the nearest published comparator to this "
            "window. The residual difference is NOT all 'sample': index-mix is ruled out "
            "(both are pure adds across the same three indices) and the constructions "
            "agree, so part of the gap is an unexplained construction/coverage "
            "difference — most likely the event-list attrition disclosed in "
            "drop_reasons, which removes symbol-discontinuous names the incumbent keeps.")
    else:
        out["note"] = ("House gate numbers unavailable — comparison is to this run only.")
    return out


def build_gate_honesty(res: dict) -> list[str]:
    """What each gate can and cannot discriminate AT THIS DESIGN.

    Written after running them, and kept separate from the frozen pre-registration so
    the gates themselves are not retro-fitted to the answer. A gate that a good
    estimator fails for reasons outside its control is still a failed gate — but a
    reader is owed the reason, and the wave-1 sibling set the precedent of printing it.
    """
    notes: list[str] = []
    pc = res.get("families", {}).get("sp_pure_adds")
    if not pc or BENCH_SPY not in pc.get("arms", {}):
        return notes

    def pm(arm, win="0_5"):
        return pc["arms"][arm]["placebo"][win].get("placebo_mean")

    # --- centring: is the offset the COHORT's or the ESTIMATOR's? Decided by MAGNITUDE
    # against the incumbent, not by sign. Every arm drifting the same DIRECTION says
    # nothing on its own — the incumbent drifts too. What matters is whether the fitted
    # counterfactual removes MORE of that drift than the benchmark does, and it is read
    # on BOTH families because they can disagree.
    fams = [("S&P pure adds", res.get("families", {}).get("sp_pure_adds")),
            ("Phase-3 starts", res.get("families", {}).get("phase3_start"))]
    rows, worse_on = [], []
    for fname, fam in fams:
        if not fam or BENCH_SPY not in fam.get("arms", {}):
            continue
        try:
            a_sc = fam["arms"]["sc_nnls"]["placebo"]["0_5"]
            a_mk = fam["arms"]["matched_k"]["placebo"]["0_5"]
            a_bm = fam["arms"][BENCH_SPY]["placebo"]["0_5"]
        except KeyError:
            continue
        s, k, b = a_sc.get("placebo_mean"), a_mk.get("placebo_mean"), a_bm.get("placebo_mean")
        ts, tb = a_sc.get("placebo_bias_t"), a_bm.get("placebo_bias_t")
        if None in (s, k, b):
            continue
        ratio = abs(s) / abs(b) if b else float("nan")
        rows.append(f"{fname}: fitted SC {_pct(s)} (t={_r(ts)}), equal-weight {_pct(k)}, "
                    f"incumbent SPY-CAR {_pct(b)} (t={_r(tb)}) — SC is {ratio:.2f}x the "
                    f"incumbent's offset")
        if abs(s) > abs(b):
            worse_on.append(fname)
    if rows:
        where = (" and ".join(worse_on) if len(worse_on) < 3
                 else ", ".join(worse_on[:-1]) + " and " + worse_on[-1])
        plural = "families" if len(worse_on) > 1 else "family"
        verdict = (
            f"On {where} the fitted SC is offset MORE than the incumbent it is supposed "
            f"to improve on, so on {'those' if len(worse_on) > 1 else 'that'} {plural} "
            "the offset is NOT merely the cohort's — the donor pool is not spanning "
            "these names and the weights are buying a systematic shortfall rather than "
            "removing one. "
            if worse_on else
            "On every family the fitted SC is the LEAST offset arm, so the residual "
            "offset is a property of the COHORT rather than of the estimator. ")
        notes.append(
            "**PC-2 mixes an estimator question with a cohort question, and the two "
            "families answer differently.** Every arm drifts in the same direction at "
            "random dates, including the incumbent SPY-CAR arm that is NOT under test — "
            "so direction alone settles nothing. The discriminating comparison is "
            "MAGNITUDE against the incumbent, on identical draws: "
            + "; ".join(rows) + ". " + verdict
            + "Note also that the incumbent arm is not uniformly worse: where it clears "
              "the t-arm that the SC arms fail, PC-2 is separating estimators rather "
              "than describing the cohort. Read the per-arm table, not the gate flag.")

    d20 = pc["arms"]["sc_nnls"]["placebo"].get("0_20", {}).get("placebo_mean")
    r20 = pc["arms"]["sc_nnls"]["real"].get("0_20", {}).get("mean")
    if d20 is not None and r20 is not None and abs(d20) > abs(r20):
        notes.append(
            f"**The [0,20] window carries no event signal at all for the index family.** "
            f"The random-date placebo mean ({_pct(d20)}) EXCEEDS the realized CAAR "
            f"({_pct(r20)}), so whatever the 21-day post-announcement window measures, a "
            f"date drawn at random on the same names reproduces more of it. Any "
            f"'post-announcement drift' read off that window would be cohort drift. This "
            f"is a statement about the window and the cohort, not about the estimator — "
            f"every arm shows it.")

    notes.append(
        "**PC-1 and PC-3 are the gates that can actually separate the arms**, because "
        "both are comparisons: PC-1 against a number the house already graded, PC-3 "
        "against the incumbent's own placebo dispersion on identical draws. PC-2 and F-1 "
        "are absolute thresholds and inherit whatever the cohort does.")
    nd = int(res.get("placebo_draws") or 0)
    ts = []
    for _, fam in fams:
        if not fam:
            continue
        for arm in ("matched_k", "sc_nnls"):
            try:
                v = fam["arms"][arm]["placebo"]["0_5"].get("placebo_bias_t")
            except KeyError:
                v = None
            if v is not None:
                ts.append(abs(float(v)))
    if ts and nd:
        # t scales as sqrt(B): t(B') = t(B) * sqrt(B'/B)
        def rng_at(b):
            lo = min(ts) * math.sqrt(b / nd)
            hi = max(ts) * math.sqrt(b / nd)
            return lo, hi
        tbl = " · ".join(f"B={b}: |t| {rng_at(b)[0]:.2f}–{rng_at(b)[1]:.2f} "
                         f"({'PASS' if rng_at(b)[1] < 2 else 'FAIL'})"
                         for b in (50, nd, 1000))
        b_pass = int(math.floor(nd * (2.0 / max(ts)) ** 2))
        notes.append(
            f"**PC-2's |t|<2 arm is controlled by the DRAW COUNT, not by the estimator.** "
            f"That t is the Monte-Carlo standard error of the placebo mean "
            f"(mean / (sd/sqrt(B))), so for any non-zero cohort drift it grows as "
            f"sqrt(B) without bound. Across the four arm x family cells: {tbl}. So the "
            f"arm does NOT flip at a plausible B — it would take B <= {b_pass} for every "
            f"cell to clear |t|<2, which is far too few draws to estimate a null "
            f"distribution at all. The honest statement is that this arm is guaranteed "
            f"to fail at ANY usable draw count once the cohort drift is non-zero, which "
            f"makes it a test of 'is the drift exactly zero', not a test of the "
            f"estimator. The economic content of PC-2 is carried entirely by its "
            f"|mean| < 0.3% arm, which IS B-invariant and which every cell passes.")
    pcf = pc.get("placebo_draws_detail", {}).get("n_fitted_per_draw", {})
    notes.append(
        "**Neither the donor pool nor the TREATED set is matched between the real and "
        "placebo arms.** Real index events batch on quarterly reconstitution dates, so "
        "many donors sit inside the ±21-session exclusion simultaneously and are dropped "
        "together; placebo dates are uniform and lose far fewer. On the treated side the "
        f"real statistic fits {pc.get('n_fitted', 0):,} events while each placebo draw "
        f"fits about {pcf.get('mean', 0):.0f} (range {pcf.get('min', 0):,}–"
        f"{pcf.get('max', 0):,}) out of {pc.get('placebo_events', 0):,} re-datable names "
        "— a placebo date is free to land where the name's window is clean, whereas the "
        "real date is not. So the null is estimated on a slightly LARGER and easier "
        "treated set than the statistic it is judging, which if anything understates the "
        "null's dispersion. A calendar-matched placebo drawn only from dates where the "
        "real event would also have fitted removes both asymmetries and is the sharper "
        "design for the next rung.")
    d3 = pc.get("pc3_dispersion") or {}
    if d3.get("ratio") is not None:
        ci = d3.get("ratio_ci95_paired_bootstrap") or [None, None]
        notes.append(
            f"**PC-3 is registered as a bare point comparison and passes by a margin "
            f"inside its own uncertainty.** The dispersion ratio is "
            f"{d3['ratio']:.3f} (SC {_pct(d3['sd_sc_nnls'])} vs incumbent "
            f"{_pct(d3['sd_benchmark'])}) with a paired-bootstrap 95% CI of "
            f"[{ci[0]:.3f}, {ci[1]:.3f}] over {d3['n_draws']} draws and a paired "
            f"variance-difference t of {_r(d3.get('paired_var_diff_t'))}. The gate's "
            f"PASS is real but should be read as 'SC is not noisier', not as 'SC is "
            f"materially tighter'.")
    try:
        mk_t = pc["arms"]["matched_k"]["real"]["0_5"]["t"]
        sc_t = pc["arms"]["sc_nnls"]["real"]["0_5"]["t"]
        if mk_t and sc_t and mk_t > sc_t:
            notes.append(
                f"**The unfitted estimator wins PC-1.** The equal-weight `matched_k` "
                f"basket carries t={_r(mk_t)} on the announce window against the fitted "
                f"`sc_nnls`'s t={_r(sc_t)}. PC-1 is registered on sc_nnls alone, so this "
                f"does not change the gate — but a zero-parameter basket matching or "
                f"beating the fitted counterfactual is the relevant signal about how much "
                f"the fitting is actually buying here.")
    except (KeyError, TypeError):
        pass
    if res.get("vol_band_fallbacks"):
        notes.append(
            f"**The pre-registered 0.5×–2.0× vol band disengaged "
            f"{res['vol_band_fallbacks']:,} times** (the band admitted no donor and the "
            f"screen fell back to the unbanded pool). Counted rather than silent, because "
            f"a screen that turns itself off is a screen the study cannot claim it applied.")
    notes.append(
        "The placebo null is drawn uniformly over the store's sessions while the real "
        "events cluster (S&P reconstitutions batch quarterly). Market drift differences "
        "out of every arm — each is a treated-minus-counterfactual difference — but the "
        "calendar composition of the null is not matched to the real events, and a "
        "calendar-matched placebo is the sharper design the next rung should use.")
    return notes


#: Reader-facing summary of every amendment in the frozen header. The header is the
#: authority; this exists so the WRITEUP carries them too — a correction recorded only in
#: a source docstring is a correction the reader of the results never sees.
AMENDMENTS = [
    "**AM-1 announce source.** `data/sp_index_changes/changes.parquet` holds 50 rows "
    "(4 sp500 adds) and is not the store the house's +1.64% grade came from; the family "
    "is rebuilt from `sp1500_pit_membership.parquet` exactly as "
    "`scripts/validate_index_reconstitution.py` does.",
    "**AM-2 sector arm.** Not derivable for index adds (`data/sector_holdings` covers 236 "
    "S&P 500 names = 6.2% of in-scope adds). Phase-3 keeps its XLV arm.",
    "**AM-3 universe floor.** The house $5 price floor is applied to donors; the charter's "
    "donor rules named coverage, liquidity and event exclusion but no price floor.",
    "**AM-4 donor pre-screen.** The fitted solver receives the top-50 by pre-window "
    "correlation, not all ~4,000 eligible names. M=50 and k=20 were frozen before any "
    "result and are not tuned.",
    "**AM-5 instrument type.** No whole-market security-type classifier exists here, so "
    "ETFs/ADRs/preferreds clearing the liquidity floor are admissible donors.",
    "**AM-6 Phase-3 cells.** Multiple NCTs posted by one sponsor on one day are ONE event, "
    "matching the prior study's `ticker_date_cells` construction.",
    "**AM-7 window.** `CAR[0,5]` is NOT byte-identical to the incumbent's announce window: "
    "the incumbent scores a five-return price ratio, this sums six. The prereg's \"spans "
    "exactly\" is withdrawn; `incumbent_reconciliation` computes the incumbent's exact "
    "statistic on this sample instead.",
    "**AM-8 charter matching.** The charter specifies matching on "
    "path/vol/beta/sector/size/liquidity. SECTOR and SIZE are NOT matched on — no "
    "whole-market classifier exists. Correlation matching subsumes path and, for a returns "
    "fit, beta; sector exposure is recovered only implicitly.",
    "**AM-9 PC-1 estimand.** PC-1 requires BOTH the event-weighted and month-weighted CAAR "
    "to be positive. `monthly_nw` pairs an event-weighted mean with a month-weighted t, and "
    "with quarterly-batched reconstitutions the two can disagree in sign. Strictly stronger "
    "than the registered single-mean form.",
    "**AM-10 placebo band.** ASYMMETRIC `[s−20, s+125]`, not the symmetric ±42 first "
    "written. A placebo at s' fits on `[s'−125, s'−6]`, so `s' ∈ [s+42, s+125]` passed the "
    "old guard while FITTING on a window containing the real treatment — 9.6% of eligible "
    "dates, contaminating only the SC arms and therefore biasing PC-3 specifically.",
    "**AM-11 price floor is PIT.** The $5 floor reads the close AS PRINTED, not the "
    "back-adjusted close. `split_adjust` back-multiplies prior bars by a factor detected "
    "later in the series, which is not PIT and inverts the selection: a raw $0.60 name that "
    "later reverse-splits 1:10 reads as $6.00 and would be admitted.",
]


def build_caveats() -> list[str]:
    """Everything a reader needs in order to not over-read the table above."""
    return [
        "DIAGNOSTIC tier — this grades an estimator, not a signal. No promotion, no "
        "surface, no ranked path, no fused composite of the two estimators anywhere.",
        f"Store starts 2021-07-06, so events are restricted to {SCOPE_START}→ and the "
        "sample is NOT the one the house's +1.64%/t=4.63 index grade was computed on "
        "(2019→, n=877). The positive control is directional, not a replication.",
        "AM-1: data/sp_index_changes/changes.parquet holds 50 rows (4 sp500 adds) and is "
        "too thin to carry the control; the graded family is rebuilt from "
        "sp1500_pit_membership.parquet exactly as scripts/validate_index_reconstitution.py "
        "does, with the announce day taken as effective − 5 sessions.",
        "AM-2: the sector-ETF arm is NOT derivable for index adds — data/sector_holdings "
        "covers S&P 500 constituents only (236 tickers, 6.2% of in-scope adds, which are "
        "mostly sp400/sp600). Phase-3 keeps its XLV arm.",
        "Donor contamination is screened against the IN-SCOPE events of the treated "
        "family only. Three classes of index event are therefore invisible to it and can "
        "sit inside a donor pool: S&P DELETIONS (negative drift, inflates tau), MIGRATION "
        "and RE-ADD cohorts (excluded from the treated set by classify_cohort but still "
        "index events), and PURE ADDS BEFORE 2022-01 (outside the study scope but inside "
        "some pre-windows). Each is a known, unremoved bias rather than an absent one; "
        "the top-50 correlation screen keeps the expected per-event contribution small.",
        "The contamination map is NOT point-in-time — it uses donors' future event dates "
        "to exclude them. That is correct for a retrospective diagnostic (it is donor "
        "hygiene, not a tradable rule) but it would not be available live.",
        "Phase-3 biases carry over from the prior study unchanged: collector truncation "
        "(pageSize=100, no pagination, sort by LastUpdatePostDate) and only 19 sponsor "
        "clusters, all mega-cap pharma and heavily time-overlapping.",
        "Prices are split-repaired but NOT dividend-adjusted (price return, not total "
        "return). The whisker applies to treated and donors alike and very largely "
        "differences out of tau.",
        "AM-5: no security-type classifier exists here, so ETFs/ADRs/preferreds clearing "
        "the liquidity floor are admissible donors.",
        "Missing donor prints inside the fitting window are filled with a zero return "
        "(for a buy-and-hold donor a non-trading day IS a zero return); the ≥90% coverage "
        "rule caps this at 12 of 120 sessions.",
        "Placebo dates are drawn per name outside the ASYMMETRIC exclusion band "
        "[s−20, s+125] sessions around the real event s — asymmetric because a placebo at "
        "s' scores forward over [s', s'+20] but FITS backward over [s'−125, s'−6], so the "
        "two windows sit on opposite sides of the event day (AM-10). An earlier symmetric "
        "±42 guard let 9.6% of eligible dates fit on a window containing the real "
        "treatment. The real events' donor-contamination map is applied to placebo draws "
        "too, which is conservative.",
        "Placebo draws are the only stochastic element and are seeded; every other number "
        "here is deterministic given the store.",
        "Cohort labelling inherits an incumbent defect: `classify_cohort` calls an add "
        "\"pure\" whenever it finds no prior PIT membership row, which also catches ticker "
        "RENAMES and SPIN-OFFS — entities already inside the S&P universe under another "
        "symbol, which therefore DO have an offsetting forced seller. Reproducing the "
        "incumbent's construction faithfully was the point of the positive control, so "
        "this is disclosed and deliberately not fixed here.",
        "Events whose treated name has a hole in its own fitting window produce no "
        "estimate and are absent from every reported number; the dominant cause is symbol "
        "discontinuity in a store keyed by CURRENT ticker, so the headline is a survivor "
        "statistic. Counts and reasons are in `drop_reasons`.",
        "Monthly clustering keys on the EVENT day (effective − 5 sessions) while the "
        "incumbent keys on the effective date, so a handful of events fall in a different "
        "month than they would there; the estimator is the same, the month partition is "
        "not identical.",
        "Empirical p carries the (1+k)/(B+1) permutation correction, so its floor is "
        "1/(B+1) and it can never print 0. The null it tests is 'effect equals the "
        "placebo mean', not 'effect equals zero'.",
    ]


def build_narrative(res: dict) -> str:
    ge = res["gate_eval"]
    pc = res["families"].get("sp_pure_adds")
    fl = res["families"].get("phase3_start")
    out = []
    if pc and BENCH_SPY in pc.get("arms", {}):
        sc5 = pc["arms"]["sc_nnls"]["real"]["0_5"]
        mk5 = pc["arms"]["matched_k"]["real"]["0_5"]
        bm5 = pc["arms"][BENCH_SPY]["real"]["0_5"]
        out.append(
            f"**Positive control.** Over the announce window the incumbent SPY-adjusted "
            f"CAR reads {_pct(bm5.get('mean'))} (t={_r(bm5.get('t'))}), the equal-weight "
            f"donor basket {_pct(mk5.get('mean'))} (t={_r(mk5.get('t'))}), and the fitted "
            f"synthetic control {_pct(sc5.get('mean'))} (t={_r(sc5.get('t'))}). The "
            f"house's graded number for this family is +1.64% at t=4.63 on the full "
            f"2019→ sample; this run is restricted to {SCOPE_START}→ by the store's "
            f"2021-07 start, so the samples differ — the comparison is directional, not "
            f"a replication.")

        sd_sc = pc["arms"]["sc_nnls"]["placebo"]["0_5"].get("placebo_sd")
        sd_mk = pc["arms"]["matched_k"]["placebo"]["0_5"].get("placebo_sd")
        sd_bm = pc["arms"][BENCH_SPY]["placebo"]["0_5"].get("placebo_sd")
        if sd_sc and sd_bm:
            out.append(
                f"**Power.** Under the null the fitted SC's aggregate estimate has "
                f"placebo dispersion {_pct(sd_sc)}, the equal-weight basket "
                f"{_pct(sd_mk)}, the incumbent {_pct(sd_bm)} "
                f"({sd_sc / sd_bm:.2f}× the incumbent). A counterfactual that is not "
                f"tighter than SPY under the null has bought nothing, whatever it does "
                f"to the point estimate — that is what PC-3 grades.")

        # Bias diagnosis: is a non-zero placebo mean the ESTIMATOR's or the COHORT's?
        pm_sc = pc["arms"]["sc_nnls"]["placebo"]["0_5"].get("placebo_mean")
        pm_mk = pc["arms"]["matched_k"]["placebo"]["0_5"].get("placebo_mean")
        pm_bm = pc["arms"][BENCH_SPY]["placebo"]["0_5"].get("placebo_mean")
        if pm_sc is not None and pm_bm is not None:
            bits = (f"**Centring.** At random dates on the same names the arms read "
                    f"{_pct(pm_sc)} (fitted SC), {_pct(pm_mk)} (equal-weight) and "
                    f"{_pct(pm_bm)} (incumbent SPY-CAR). ")
            if abs(pm_sc) < abs(pm_bm):
                bits += (
                    "Every arm is offset in the same direction and the fitted SC is the "
                    "LEAST offset, so the offset is a property of the COHORT rather than "
                    "of the estimator: names that were being added to an S&P index "
                    "drifted up against any counterfactual over this window, and SC "
                    "removes more of that drift than the incumbent does. This matters "
                    "for how the announce effect itself should be read — part of what a "
                    "benchmark-adjusted CAR attributes to the announcement is cohort "
                    "drift that a random date reproduces.")
            else:
                bits += (
                    "The fitted SC is offset MORE than the incumbent, so the offset is "
                    "the estimator's own and not merely the cohort's — the donor pool is "
                    "not spanning these names, and the weights are buying a systematic "
                    "shortfall rather than removing one.")
            bits += (" The harness itself manufactures nothing: on a synthetic no-effect "
                     "panel the same code path returns zero within sampling error "
                     "(tests/test_synthetic_control.py::"
                     "test_placebo_machinery_returns_zero_on_a_no_effect_panel), so this "
                     "offset is in the data, not in the estimator's arithmetic.")
            out.append(bits)

    if fl:
        f20 = fl["arms"]["sc_nnls"]["real"]["0_20"]
        fp = fl["arms"]["sc_nnls"]["placebo"]["0_20"]
        f0 = fl["arms"]["sc_nnls"]["real"]["0"]
        out.append(
            f"**Falsifier.** On Phase-3 starts the fitted SC reads "
            f"{_pct(f20.get('mean'))} over [0,20] with monthly-NW t={_r(f20.get('t'))} "
            f"and empirical p={_r(fp.get('empirical_p'))} against its own random-date "
            f"placebo; day 0 is {_pct(f0.get('mean'))} (t={_r(f0.get('t'))}). The house "
            f"verdict on record for this family is NULL — placebo-explained — and F-1 "
            f"asks only that SC not overturn it.")

    out.append(f"**Pre-registered verdict: `{ge['verdict']}`**"
               + (f" — failing {', '.join(ge['failing_gates'])}. A failed gate is a "
                  "result: it says where this estimator may and may not be trusted, and "
                  "nothing here promotes it into any scored path."
                  if ge["failing_gates"] else
                  ". All four pre-registered gates pass; adoption beyond diagnostic tier "
                  "is still a separate decision and is not taken here."))
    return "\n\n".join(out)


# ================================================================== main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-root", default=None, help="massive_stock_day store root")
    ap.add_argument("--draws", type=int, default=PLACEBO_DRAWS, help="placebo replications")
    ap.add_argument("--max-names", type=int, default=None, help="cap store reads (smoke)")
    ap.add_argument("--skip-ledger", action="store_true")
    ap.add_argument("--no-write", action="store_true", help="compute, print, write nothing")
    ap.add_argument("--allow-stale", action="store_true",
                    help="run against a local massive_stock_day mirror 20+ trading "
                         "sessions behind (refused by default — the mirror does not "
                         "self-update, so the numbers would be as of its frozen date)")
    args = ap.parse_args()

    t_start = time.time()
    print("=" * 72)
    print("synthetic_control — Phase-0 (wave-2a) · estimator honesty check")
    print("=" * 72)

    store = resolve_data_root(args.data_root)
    if store is None:
        print("ERROR: massive_stock_day store not reachable via the data-root ladder.")
        print("  Tried: --data-root, $MACRO_PRIMARY_DATA, <repo>/data/massive_stock_day,")
        print("  /Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day")
        print("  No numbers are produced. This is a data-reach failure, not a result.")
        return 2
    print(f"[data] store {store}")
    # The ladder proves the store is REACHABLE, never that it is CURRENT: a local tree
    # is a mirror of the R2-canonical store and nothing refreshes it in place.
    try:
        check_local_mirror_freshness(store, entrypoint="scripts/synthetic_control_phase0.py",
                                     allow_stale=args.allow_stale)
    except StaleLocalMirrorError:
        sys.exit(2)   # the banner already printed the lag and the fix command
    data_dir = WT_ROOT / "data"

    if not args.skip_ledger:
        led = TrialLedger(path=LEDGER_PATH, family=FAMILY)
        # Every arm x family x window cell that gets a t printed against it is a test and
        # is ledgered. The XLV sector arm runs on the Phase-3 family ONLY (AM-2), and it
        # is the cell carrying the one |t|>2 read in that family — leaving it unledgered
        # would understate the multiple-testing budget exactly where it matters.
        configs = [{"family": fam, "estimator": arm, "window": w}
                   for fam in ("sp_pure_adds", "phase3_start")
                   for arm in (("matched_k", "sc_nnls", BENCH_SPY)
                               + ((BENCH_SECTOR_PHASE3,) if fam == "phase3_start" else ()))
                   for w in ("0", "0_5", "0_20")]
        n_new = led.log_grid(configs, info_cutoff="2026-08-06",
                             note=f"frozen prereg; {len(configs)} arm x family x window "
                                  "cells (Phase-3 carries the extra XLV sector arm)")
        print(f"[ledger] logged {n_new} new trial configs "
              f"(family={FAMILY}, literal n={led.literal_n(FAMILY)})")

    print("[panel] reading store...", flush=True)
    panel, pstats = build_panel(store, max_names=args.max_names)
    print(f"[panel] {pstats['kept']:,} names x {pstats.get('sessions', 0):,} sessions "
          f"{pstats.get('calendar')} ({time.time() - t_start:.0f}s)", flush=True)
    if panel.n_sessions == 0:
        print("ERROR: empty panel."); return 2

    benchmarks = {}
    for b in (BENCH_SPY,):
        if b in panel.col:
            benchmarks[b] = panel.ret[:, panel.col[b]]
        else:
            print(f"[warn] benchmark {b} absent from the store — arm skipped")

    rng = np.random.default_rng(SEED)
    families, diag = {}, {}

    # ---- positive control
    ev_pc, d_pc = sp_pure_add_events(panel, data_dir)
    diag["sp_pure_adds"] = d_pc
    print(f"[events] S&P pure adds: {d_pc}", flush=True)
    if len(ev_pc) < MIN_EVENTS:
        print(f"[scope] only {len(ev_pc)} pure adds in scope (<{MIN_EVENTS}) — the "
              "pre-registered fallback is a DISCLOSED widened variant, not a silent one.")
    recon = None
    if len(ev_pc):
        families["sp_pure_adds"] = run_family(
            panel, ev_pc, "sp_pure_adds", benchmarks=benchmarks, draws=args.draws, rng=rng)
        recon = incumbent_reconciliation(panel, ev_pc)
        print(f"[recon] incumbent construction on this sample: {recon}", flush=True)

    # ---- falsifier (sector arm: XLV, exactly the prior study's benchmark)
    ev_f, d_f = phase3_events(panel, data_dir)
    diag["phase3_start"] = d_f
    print(f"[events] Phase-3 starts: {d_f}", flush=True)
    if len(ev_f):
        bmk = dict(benchmarks)
        if BENCH_SECTOR_PHASE3 in panel.col:
            bmk[BENCH_SECTOR_PHASE3] = panel.ret[:, panel.col[BENCH_SECTOR_PHASE3]]
        families["phase3_start"] = run_family(
            panel, ev_f, "phase3_start", benchmarks=bmk, draws=args.draws, rng=rng)

    gate_eval = evaluate_gates(families.get("sp_pure_adds", {}), families.get("phase3_start"))

    res = {
        "study": FAMILY,
        "tier": "DIAGNOSTIC",
        "run_date": pd.Timestamp.utcnow().strftime("%Y-%m-%d"),
        "charter": "research/ADVANCED_QUANT_METHODS_ADJUDICATION_BY_FABLE.md §3#5",
        "store": str(store),
        "panel": pstats,
        "scope_start": SCOPE_START,
        "placebo_draws": int(args.draws),
        "seed": SEED,
        "constants": {"pre_window": sc.PRE_WINDOW, "embargo": sc.EMBARGO,
                      "event_exclusion": sc.EVENT_EXCLUSION,
                      "min_coverage": sc.MIN_COVERAGE, "dvol_floor": sc.DVOL_FLOOR,
                      "prescreen_m": sc.PRESCREEN_M, "matched_k": sc.MATCHED_K,
                      "price_min": PRICE_MIN, "post_window": POST_WINDOW,
                      "placebo_exclusion_band": [-POST_WINDOW,
                                                 sc.PRE_WINDOW + sc.EMBARGO],
                      "placebo_exclusion_band_note":
                          "sessions relative to the real event s that a placebo date may "
                          "NOT take: [s-20, s+125]. Asymmetric because the outcome window "
                          "runs forward from s' and the FIT window runs backward from it "
                          "(AM-10)."},
        "family_diag": diag,
        "families": families,
        "incumbent_reconciliation": recon,
        "vol_band_fallbacks": int(sc.VOL_BAND_FALLBACKS[0]),
        "gate_eval": gate_eval,
        "runtime_s": round(time.time() - t_start, 1),
        "caveats": build_caveats(),
    }
    res["narrative"] = build_narrative(res)
    res["gate_honesty"] = build_gate_honesty(res)

    print("\n" + "=" * 72)
    print("GATES")
    print("=" * 72)
    for k, v in gate_eval["gates"].items():
        tag = "PASS" if v is True else ("FAIL" if v is False else "N/A ")
        print(f"  [{tag}] {k}")
        print(f"         {gate_eval['reasons'].get(k.split('_')[0], '')}")
    print(f"\nVERDICT: {gate_eval['verdict']}")
    if gate_eval["failing_gates"]:
        print(f"FAILING: {', '.join(gate_eval['failing_gates'])}")
    print(f"\nruntime {res['runtime_s']:.0f}s")

    if not args.no_write:
        RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_JSON.write_text(json.dumps(res, indent=2, default=str))
        print(f"[write] {RESULTS_JSON}")
        write_report(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
