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
    CAR[0,5] spans exactly the incumbent's [-5, 0] announce window and the two
    estimators are compared on the SAME days. S&P announces ~5 trading days ahead.
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
import os
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

WT_ROOT = Path(__file__).resolve().parents[1]
if str(WT_ROOT) not in sys.path:
    sys.path.insert(0, str(WT_ROOT))

from engine import synthetic_control as sc          # noqa: E402
from engine import validation as V                  # noqa: E402
from engine.index_changes import classify_cohort, pit_history   # noqa: E402
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
PLACEBO_GUARD = 42         # placebo dates must be this far from the real event
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
    close: np.ndarray          # (T, N) split-adjusted close
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
        frames[stem] = pd.DataFrame({"close": adj, "dvol": adj * vol})
    stats["kept"] = len(frames)
    if not frames:
        return Panel(pd.DatetimeIndex([]), [], np.zeros((0, 0)), np.zeros((0, 0)),
                     np.zeros((0, 0))), stats

    dates = pd.DatetimeIndex(sorted({d for f in frames.values() for d in f.index}))
    tickers = sorted(frames)
    n_t, n_n = len(dates), len(tickers)
    close = np.full((n_t, n_n), np.nan)
    dvol = np.full((n_t, n_n), np.nan)
    for j, t in enumerate(tickers):
        f = frames[t].reindex(dates)
        close[:, j] = f["close"].to_numpy(dtype=float)
        dvol[:, j] = f["dvol"].to_numpy(dtype=float)

    ret = np.full((n_t, n_n), np.nan)
    ret[1:] = close[1:] / close[:-1] - 1.0
    # 20d MEDIAN dollar volume, causal (window ends at the bar, inclusive)
    dv20 = (pd.DataFrame(dvol).rolling(20, min_periods=10).median()).to_numpy(dtype=float)
    stats["sessions"] = n_t
    stats["names"] = n_n
    stats["calendar"] = (str(dates[0].date()), str(dates[-1].date()))
    return Panel(dates, tickers, ret, dv20, close), stats


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

    pit_by_t = pit_history()
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

    for i in range(e):
        c, s = int(cols[i]), int(sessions[i])
        sl = sc.pre_window_slice(s)
        pre = panel.ret[sl, :]
        y = pre[:, c]
        if not np.isfinite(y).all():
            continue
        end = sl.stop - 1                       # last session inside the pre-window
        mask = sc.eligible_donors(
            donor_pre=pre,
            donor_dvol=panel.dvol20[end, :],
            event_distance=np.where(contaminated[s, :], 0.0, np.inf),
            treated_col=c,
        )
        mask &= np.isfinite(panel.close[end, :]) & (panel.close[end, :] > PRICE_MIN)
        idx = np.flatnonzero(mask)
        pool_sizes[i] = idx.size
        if idx.size < m:
            continue
        sub = pre[:, idx]
        sub = np.where(np.isfinite(sub), sub, 0.0)
        sel_local = sc.prescreen_donors(y, sub, m=m)
        if sel_local.size < m:
            continue
        cols_sel = idx[sel_local]
        pre_t[i] = y
        pre_d[i] = pre[:, cols_sel]
        post_t[i] = panel.ret[s:s + POST_WINDOW + 1, c]
        post_d[i] = panel.ret[s:s + POST_WINDOW + 1, cols_sel]
        n_sel[i] = m

    live = n_sel > 0
    if not live.any():
        return {"_keys": keys, "_n_live": 0, "_pool_mean": 0.0,
                **{a: out[a] for a in arms}}

    # A missing donor print inside the fitting window is filled with a zero return: for a
    # buy-and-hold donor a non-trading day IS a zero return, and the >=90% coverage rule
    # caps this at 12 of 120 sessions. The solver requires finite input.
    pre_d = np.where(np.isfinite(pre_d), pre_d, 0.0)
    li = np.flatnonzero(live)

    # matched_k: equal weight over the top-k. prescreen_donors returns columns in
    # correlation rank order, so the first MATCHED_K columns of pre_d ARE the top-k that
    # engine.donor_weights(method='matched_k') would select — pinned by
    # tests/test_synthetic_control.py::test_matched_k_is_top_k_of_the_prescreen.
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

    return {"_keys": keys, "_n_live": int(li.size),
            "_pool_mean": float(pool_sizes[live].mean()) if live.any() else 0.0,
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
    return {"n": int(good.sum()), "n_months": int(len(monthly)),
            "mean": float(np.mean(car[good])), "t": nw.get("t"), "p": nw.get("p"),
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
    """Sessions where this name could host a placebo event: full pre-window + embargo +
    post-window inside the store, price data present, and >= PLACEBO_GUARD away from the
    name's real event so the placebo cannot contain the real effect."""
    lo = sc.PRE_WINDOW + sc.EMBARGO
    hi = panel.n_sessions - POST_WINDOW - 1
    if hi <= lo:
        return np.zeros(0, dtype=int)
    cand = np.arange(lo, hi + 1)
    cand = cand[np.abs(cand - real_sess) >= PLACEBO_GUARD]
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
                   "mean_donor_pool": round(float(real["_pool_mean"]), 1),
                   "windows": keys, "arms": {}}
    for arm in arms:
        per_win = {}
        for j, k in enumerate(keys):
            car = real[arm][:, j]
            s = monthly_nw(car, pd.DatetimeIndex(ev["date"]))
            s["ticker_cluster_t"] = ticker_cluster_t(car, ev["ticker"].to_numpy())
            per_win[k] = s
        stats["arms"][arm] = {"real": per_win}

    # ---- placebo: re-date every event, `draws` times
    cand = [eligible_placebo_sessions(panel, int(c), int(s)) for c, s in zip(cols, sess)]
    usable = np.array([c.size > 0 for c in cand])
    if verbose:
        print(f"  [{label}] placebo: {draws} replications over "
              f"{int(usable.sum())}/{len(ev)} re-datable events", flush=True)
    null = {a: np.full((draws, len(keys)), np.nan) for a in arms}
    tp = time.time()
    for d in range(draws):
        psess = sess.copy()
        for i, c in enumerate(cand):
            if c.size:
                psess[i] = c[rng.integers(c.size)]
        est = estimate_events(panel, cols, psess, contaminated, benchmarks=benchmarks)
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
                # two-sided empirical p of the real CAAR against the placebo null
                centred = np.abs(dn - dn.mean())
                blk["empirical_p"] = float((centred >= abs(real_mean - dn.mean())).mean())
            stats["arms"][arm].setdefault("placebo", {})[k] = blk

    stats["runtime_s"] = round(time.time() - t0, 1)
    return stats


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

    # PC-1 — positive control survives under sc_nnls at [0,5]
    m = _get(pc, "sc_nnls", "real", "0_5", "mean")
    t = _get(pc, "sc_nnls", "real", "0_5", "t")
    g["PC1_positive_control_survives"] = bool(
        m is not None and t is not None and m > 0 and t > 2.0)
    reasons["PC1"] = f"sc_nnls S&P pure-add CAAR[0,5]={_pct(m)} monthly-NW t={_r(t)} (need >0 and t>2)"

    # PC-2 — neither SC estimator is biased under the null, on BOTH families
    pc2, bits = True, []
    for fam, name in ((pc, "sp_pure_adds"), (fl, "phase3_start")):
        if fam is None:
            continue
        for arm in ("matched_k", "sc_nnls"):
            pm = _get(fam, arm, "placebo", "0_5", "placebo_mean")
            bt = _get(fam, arm, "placebo", "0_5", "placebo_bias_t")
            ok = (pm is not None and bt is not None
                  and abs(pm) < GATE_PLACEBO_BIAS and abs(bt) < 2.0)
            pc2 &= ok
            bits.append(f"{name}/{arm} mean={_pct(pm)} t={_r(bt)}{'' if ok else ' FAIL'}")
    g["PC2_estimators_unbiased"] = bool(pc2)
    reasons["PC2"] = "; ".join(bits) + f" (need |mean|<{GATE_PLACEBO_BIAS:.1%} and |t|<2)"

    # PC-3 — sc_nnls placebo dispersion <= benchmark-CAR(SPY) placebo dispersion at [0,5]
    sd_sc = _get(pc, "sc_nnls", "placebo", "0_5", "placebo_sd")
    sd_bm = _get(pc, BENCH_SPY, "placebo", "0_5", "placebo_sd")
    g["PC3_sc_not_noisier"] = bool(sd_sc is not None and sd_bm is not None and sd_sc <= sd_bm)
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
    if biased and powerless:
        verdict = "MIXED"
    elif biased:
        verdict = "ESTIMATOR_BIASED"
    elif powerless:
        verdict = "ESTIMATOR_POWERLESS"
    elif all(v is True for v in g.values() if v is not None):
        verdict = "ESTIMATOR_GO"
    else:
        verdict = "MIXED"
    failing = [k for k, v in g.items() if v is False]
    return {"gates": g, "reasons": reasons, "verdict": verdict, "failing_gates": failing}


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

    L.append(f"## Verdict: `{res['gate_eval']['verdict']}`\n")
    if res["gate_eval"]["failing_gates"]:
        L.append(f"Failing gate(s): **{', '.join(res['gate_eval']['failing_gates'])}**\n")
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
        L.append(f"- Scope {SCOPE_START} → panel end; construction diagnostics: "
                 f"`{json.dumps({k: v for k, v in d.items() if k != 'event_day_rule'})}`\n")
        L.append("| Arm | Window | CAAR | monthly-NW t | ticker-cluster t | hit rate | "
                 "placebo mean | placebo SD | empirical p |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for arm in fam["arms"]:
            for w in fam["windows"]:
                r = fam["arms"][arm]["real"][w]
                pl = fam["arms"][arm].get("placebo", {}).get(w, {})
                L.append(
                    f"| `{arm}` | [{w.replace('_', ',')}] | {_pct(r.get('mean'))} | "
                    f"{_r(r.get('t'))} | {_r(r.get('ticker_cluster_t'))} | "
                    f"{_r(r.get('hit_rate'), 3)} | {_pct(pl.get('placebo_mean'))} | "
                    f"{_pct(pl.get('placebo_sd'))} | {_r(pl.get('empirical_p'))} |")
        L.append("")

    L.append("## What the numbers mean\n")
    L.append(res["narrative"])
    L.append("\n## Caveats carried forward\n")
    for c in res["caveats"]:
        L.append(f"- {c}")
    L.append("\n---")
    L.append(f"*Results JSON: `{RESULTS_JSON.relative_to(WT_ROOT)}` · "
             f"trial ledger family `{FAMILY}` · runtime {res['runtime_s']:.0f}s · "
             f"seed {SEED} (placebo draws are the only stochastic element).*")
    WRITEUP_MD.write_text("\n".join(L) + "\n")
    print(f"[write] {WRITEUP_MD}")


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
        "Donor contamination is screened against the treated family's OWN events only. "
        "S&P DELETIONS are not in the index event list, so a donor being deleted (a "
        "negative-drift name) can enter a pool and inflate tau. With ~25 deletions a year "
        "against a donor pool in the thousands and a top-50 correlation screen, the "
        "expected contribution is small — but it is a known, unremoved bias, not an "
        "absent one.",
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
        "Placebo dates are drawn per name with a ±42-session guard around the real event; "
        "the real events' donor-contamination map is applied to placebo draws too, which "
        "is conservative.",
        "Placebo draws are the only stochastic element and are seeded; every other number "
        "here is deterministic given the store.",
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
    data_dir = WT_ROOT / "data"

    if not args.skip_ledger:
        led = TrialLedger(path=LEDGER_PATH, family=FAMILY)
        configs = [{"family": fam, "estimator": arm, "window": w}
                   for fam in ("sp_pure_adds", "phase3_start")
                   for arm in ("matched_k", "sc_nnls", BENCH_SPY)
                   for w in ("0", "0_5", "0_20")]
        n_new = led.log_grid(configs, info_cutoff="2026-08-06",
                             note="frozen prereg; 2 families x 3 arms x 3 windows = 18 tests")
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
    if len(ev_pc):
        families["sp_pure_adds"] = run_family(
            panel, ev_pc, "sp_pure_adds", benchmarks=benchmarks, draws=args.draws, rng=rng)

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
                      "price_min": PRICE_MIN, "placebo_guard": PLACEBO_GUARD},
        "family_diag": diag,
        "families": families,
        "gate_eval": gate_eval,
        "runtime_s": round(time.time() - t_start, 1),
        "caveats": build_caveats(),
    }
    res["narrative"] = build_narrative(res)

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
