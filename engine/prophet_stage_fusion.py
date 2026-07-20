"""Prophet × Stage-Analysis fusion backtest harness (PSF).

Binding pre-registration: ``research/PROPHET_STAGE_FUSION_PREREG.md`` (committed
2026-07-20 BEFORE any graded result). This module implements arms A / B / B-fresh /
C, the one-grader ruler, the §4 metrics (Wilson 95% CI, n_dates independence,
regime split, block-bootstrap by month), the §5 falsifiers, and the §7 look-ahead
controls EXACTLY as written. It reinvents nothing:

  * base timing signal  ->  ``engine.confluence_tiers.tier_stream`` (the validated
      T1-T4 close-only cascade). A "fresh fire" = a per-day transition INTO T1 or T2.
  * stage_at_entry      ->  ``engine.weinstein_stage.stage_series`` / ``classify``
      (PIT weekly stage + weeks_in_stage, close[:entry] truncation).
  * grading             ->  ``engine.grading.terminal_state`` (clean15_126 & clean8_21),
      ``forward_metrics`` (21/63/126), ``grading.resolve_series`` dead-name imputation
      (a delisted name carries its graded loss instead of vanishing).
  * EC join             ->  ``data/stage_analysis/backfill/earnings_calls.parquet`` on
      ``document_ticker`` with ``call_date < entry_date``, most-recent row.

§ SURVIVORSHIP (FIX-2 — honest universe, not the false ``as_of_panel`` claim). The universe
is the union of the live price globs (``baskets/ohlcv`` ∪ ``data/stocks``) WITH the delisted
tickers from the dead-name store (``data/edgar/dead_name_prices.parquet``) that are ABSENT
from the live globs — those (mostly losing) delisted fires are graded via
``grading.resolve_series`` (which returns the dead series when there is no live cache) and
ARE counted. This is NOT a full point-in-time (PIT) reconstruction: S&P-1500 PIT members
(``data/breadth/sp1500_pit_membership.parquet``) that traded 2022–26 but have NO price source
in either the live globs OR the dead-name store are still absent and CANNOT be graded (no
series exists); their count is disclosed in the ``universe`` block. The universe therefore
remains survivor-LEAN for those price-source-less names — absolute win-rates are upward-biased
(surviving names win more), but the falsifier verdicts are DELTA-based (A→B→C win-rate
differences), and survivorship inflates all arms' absolute win-rates ~symmetrically, so the
null on the delta is robust to the residual lean. This is disclosed in §0 of the report.

§0 PROXY DISCLOSURE (printed on every surfaced result): Prophet has no backtestable
history (5 live entries post-2026-07-10). PSF tests the FUSION MECHANISM on the repo's
validated T1-T4 confluence cascade as a PIT-replayable Prophet-family timing entry. A
positive result is strong evidence the mechanism helps Prophet's own entries — confirmed
forward on live Prophet from go-live. It is NOT a Prophet replay. Results are display-tier
until an operator-ratified promotion.

Efficiency (per §EFFICIENCY): for each ticker we precompute ONCE the daily tier_stream
and the weekly stage_series, then detect fresh-fire events and look up stage/weeks/EC at
each fire's date — never re-classifying per fire.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from engine import confluence_tiers, grading, weinstein_stage

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Frozen constants (mirror the pre-registration §2-§4; do not change without an  #
# amendment row in research/PROPHET_STAGE_FUSION_PREREG.md).                     #
# --------------------------------------------------------------------------- #
FRESH_FIRE_TIERS = ("T1", "T2")           # §2 base event = a T1/T2 fresh fire
STAGE2 = 2                                 # Weinstein Stage-2 (advancing)
FRESH_WEEKS_MAX = 10                       # §2 B-fresh: weeks_in_stage <= 10
EC_SENT_GATE = 24                          # §2 arm C: earnings_call_sent >= 24 (published gate)
MIN_COMPLETED_WEEKS = 45                   # §7 late-IPO exclusion (< 45 completed weeks -> counted, excluded)
BENCH_TICKER = "SPY"                       # §2 bench

# §3 two ruler parameterizations.
PARAM_CLEAN15_126 = dict(liftoff_mult=grading.LIFTOFF_15, liftoff_horizon=grading.LIFTOFF_HORIZON_126)
PARAM_CLEAN8_21 = dict(liftoff_mult=grading.LIFTOFF_8, liftoff_horizon=grading.LIFTOFF_HORIZON_21)

# §4 forward-metric horizons.
FWD_HORIZONS = (21, 63, 126)

# §4 regime split (bear / bull / recent). Inclusive start, exclusive end.
REGIMES = {
    "2022_bear":  ("2022-01-01", "2023-01-01"),
    "2023_24_bull": ("2023-01-01", "2025-01-01"),
    "2025_26":    ("2025-01-01", "2026-07-18"),
}

# §1 window bound: entries over 2022-01-01 … 2026-07-17 (the US universe window).
WINDOW_START = pd.Timestamp("2022-01-01")
WINDOW_END = pd.Timestamp("2026-07-17")

PROXY_DISCLOSURE = (
    "PROXY (PSF §0): Prophet has NO backtestable history (5 live entries post-2026-07-10). "
    "This is a FUSION-MECHANISM test on the repo's backing-artifact-backed T1-T4 confluence "
    "cascade as a PIT-replayable Prophet-family timing entry — NOT a Prophet replay. A positive "
    "result is evidence the mechanism helps Prophet's own entries, to be confirmed forward on "
    "live Prophet from go-live (~Dec 2026). Results are display-tier until operator-ratified "
    "promotion."
)


# --------------------------------------------------------------------------- #
# Wilson score interval (§4 — the CI on every win-rate and every arm delta).    #
# --------------------------------------------------------------------------- #
def wilson_ci(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float | None, float | None, float | None]:
    """Wilson score 95% CI for a binomial proportion. Returns (point, lo, hi) in [0,1].

    z default = the two-sided 95% normal quantile. Returns (None, None, None) for n == 0.
    Pure-closed-form (no scipy) — matches the thin data-bot env.
    """
    if n <= 0:
        return None, None, None
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / denom
    lo = max(0.0, centre - margin)
    hi = min(1.0, centre + margin)
    return p, lo, hi


def wilson_diff_ci(succ_a: int, n_a: int, succ_b: int, n_b: int,
                   z: float = 1.959963984540054) -> tuple[float | None, float | None, float | None]:
    """Approximate 95% CI for the DIFFERENCE of two independent Wilson-scored proportions
    (win-rate_B − win-rate_A). The falsifiers (§5) test whether this lower bound is > 0.

    Uses the Newcombe (1998) method-10 hybrid-score interval for the difference of two
    proportions — each proportion's own Wilson interval propagated into the difference,
    which behaves well at the small/skewed n the arms hit. Returns (diff_point, lo, hi).
    Sign convention: positive = B beats A. Returns (None, None, None) if either n == 0.
    """
    if n_a <= 0 or n_b <= 0:
        return None, None, None
    p_a, l_a, u_a = wilson_ci(succ_a, n_a, z)
    p_b, l_b, u_b = wilson_ci(succ_b, n_b, z)
    diff = p_b - p_a
    # Newcombe method 10: lower = diff - sqrt((p_b-l_b)^2 + (u_a-p_a)^2);
    #                     upper = diff + sqrt((u_b-p_b)^2 + (p_a-l_a)^2)
    lo = diff - math.sqrt((p_b - l_b) ** 2 + (u_a - p_a) ** 2)
    hi = diff + math.sqrt((u_b - p_b) ** 2 + (p_a - l_a) ** 2)
    return diff, lo, hi


# --------------------------------------------------------------------------- #
# Event detection — a "fresh fire" = a per-day transition INTO T1 or T2.        #
# --------------------------------------------------------------------------- #
def fresh_fire_dates(close: pd.Series) -> pd.DatetimeIndex:
    """Daily dates on which the T1-T4 cascade transitions INTO T1 or T2 (a fresh fire).

    Computed ONCE per ticker off ``confluence_tiers.tier_stream`` (the vectorized,
    completed-bucket / point-in-time daily cascade). A fire day is a day whose tier is in
    {T1,T2} and whose PREVIOUS day's tier is NOT in {T1,T2} — the per-day transition INTO
    the taken tiers (the fresh-tick semantics of the module: a just-crossed entry, not a
    name that has been rising for many ticks). Never raises → empty index.
    """
    try:
        stream = confluence_tiers.tier_stream(close)
        if stream is None or stream.empty or "tier" not in stream.columns:
            return pd.DatetimeIndex([])
        tier = stream["tier"]
        in_taken = tier.isin(FRESH_FIRE_TIERS).to_numpy()
        prev = np.concatenate(([False], in_taken[:-1]))
        fire = in_taken & (~prev)
        return stream.index[fire]
    except Exception as e:  # noqa: BLE001 — one bad name never breaks the fan-out
        log.warning("psf: fresh_fire_dates failed (%s)", e)
        return pd.DatetimeIndex([])


# --------------------------------------------------------------------------- #
# PIT stage lookup at an entry date (look-ahead-safe).                          #
# --------------------------------------------------------------------------- #
def stage_at_entry(close: pd.Series, volume: pd.Series | None,
                   bench_close: pd.Series, entry_date) -> tuple[int, int, int]:
    """PIT (stage, weeks_in_stage, n_completed_weeks) at ``entry_date``.

    LOOK-AHEAD GUARD (§7): inputs are TRUNCATED to the entry bar — the close (and bench,
    and volume) are sliced to ``<= entry_date`` before classification, so the weekly stage
    can only see completed weeks on-or-before the entry. Returns (0, 0, n_weeks) for a
    too-young name (< 45 completed weeks). Never raises.
    """
    try:
        ed = pd.Timestamp(entry_date)
        c = close[close.index <= ed]
        v = volume[volume.index <= ed] if volume is not None and len(volume) else None
        b = bench_close[bench_close.index <= ed] if bench_close is not None and len(bench_close) else bench_close
        res = weinstein_stage.classify(c, v, b)
        return int(res.get("stage", 0) or 0), int(res.get("weeks_in_stage", 0) or 0), int(res.get("n_weeks", 0) or 0)
    except Exception as e:  # noqa: BLE001
        log.warning("psf: stage_at_entry failed (%s)", e)
        return 0, 0, 0


def _stage_lookup_from_series(stage_ser: pd.Series, entry_date) -> tuple[int, int]:
    """Fast (stage, weeks_in_stage) at ``entry_date`` from a precomputed per-week
    ``stage_series`` (PIT-equivalent: stage_series only uses completed weeks, so the label
    at-or-before the entry never depends on future weeks). weeks_in_stage is derived by
    counting the run of the current stage back through the weekly index up to the entry.

    This is the efficient per-fire path (no re-classify). The truncating ``stage_at_entry``
    is the audited guard the tests pin against.
    """
    if stage_ser is None or stage_ser.empty:
        return 0, 0
    ed = pd.Timestamp(entry_date)
    prior = stage_ser[stage_ser.index <= ed]
    if prior.empty:
        return 0, 0
    st = int(prior.iloc[-1])
    if st == 0:
        return 0, 0
    # weeks_in_stage = length of the trailing run equal to st (matches _run_machine's counter,
    # which resets on any stage change and increments while the stage holds).
    vals = prior.to_numpy()
    wis = 0
    for v in vals[::-1]:
        if int(v) == st:
            wis += 1
        else:
            break
    return st, wis


# --------------------------------------------------------------------------- #
# EC join — most-recent earnings-call sentiment with call_date < entry_date.    #
# --------------------------------------------------------------------------- #
def load_ec_table(ec_path: str | Path | None = None) -> pd.DataFrame:
    """Load the earnings-call backfill table, or an EMPTY frame if absent (fail-open, §5).

    Columns kept: ticker (from ``document_ticker``), call_date (datetime), earnings_call_sent.
    When the local gitignored parquet is missing, returns an empty frame so arm C simply
    yields n=0 (the harness must degrade, never crash — the fail-open-on-absent-EC test).
    """
    from lib import config
    p = Path(ec_path) if ec_path is not None else (
        config.data_dir() / "stage_analysis" / "backfill" / "earnings_calls.parquet")
    cols = ["ticker", "call_date", "earnings_call_sent"]
    if not p.exists():
        log.warning("psf: earnings_calls parquet absent (%s) — arm C degrades to n=0", p)
        return pd.DataFrame(columns=cols)
    try:
        df = pd.read_parquet(p, columns=["document_ticker", "call_date", "earnings_call_sent"])
    except Exception as e:  # noqa: BLE001
        log.warning("psf: earnings_calls unreadable (%s) — arm C degrades to n=0", e)
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame({
        "ticker": df["document_ticker"].astype(str),
        "call_date": pd.to_datetime(df["call_date"], errors="coerce"),
        "earnings_call_sent": pd.to_numeric(df["earnings_call_sent"], errors="coerce"),
    }).dropna(subset=["call_date"])
    return out.sort_values("call_date").reset_index(drop=True)


def ec_sent_at_entry(ec_by_ticker: dict[str, pd.DataFrame], ticker: str, entry_date) -> float | None:
    """Most-recent ``earnings_call_sent`` with ``call_date < entry_date`` for ``ticker``.

    STRICTLY-BEFORE (call_date < entry_date, §7 look-ahead control): a call printed on the
    entry day itself is NOT usable (its sentiment would not be known pre-fill). Returns None
    when the ticker has no prior call (arm C then excludes the fire). Never raises.
    """
    g = ec_by_ticker.get(str(ticker))
    if g is None or g.empty:
        return None
    ed = pd.Timestamp(entry_date)
    prior = g[g["call_date"] < ed]
    if prior.empty:
        return None
    v = prior["earnings_call_sent"].iloc[-1]  # g is call_date-sorted → last is most-recent
    return float(v) if pd.notna(v) else None


def ec_index(ec_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """{ticker -> call_date-sorted frame} for fast per-fire most-recent lookup."""
    if ec_df is None or ec_df.empty:
        return {}
    out: dict[str, pd.DataFrame] = {}
    for tk, g in ec_df.groupby("ticker"):
        out[str(tk)] = g.sort_values("call_date").reset_index(drop=True)
    return out


# --------------------------------------------------------------------------- #
# Per-fire record + arm membership.                                            #
# --------------------------------------------------------------------------- #
@dataclass
class Fire:
    ticker: str
    date: pd.Timestamp
    tier: str
    stage: int
    weeks_in_stage: int
    ec_sent: float | None
    # grading outputs (filled by grade_fire)
    state_15_126: str | None = None
    state_8_21: str | None = None
    fwd: dict[str, float | None] = field(default_factory=dict)
    matured_15_126: bool = False
    matured_8_21: bool = False
    _liftoff_bar_clean15_126: int | None = None
    _liftoff_bar_clean8_21: int | None = None
    # FIX-3: unconditional hold/excursion metric — bars from fill to the max-favorable-
    # excursion peak within the 126-bar forward window, computed over ALL matured fires
    # (NOT conditional-on-winning like _liftoff_bar_*). None until forward_metrics runs.
    bars_to_mfe_peak_126: int | None = None

    def in_arm(self, arm: str, ec_gate: float = EC_SENT_GATE) -> bool:
        """Membership test for arm ∈ {A, B, B_fresh, C}. §2 filters (identical universe/
        events/ruler; only the filter differs)."""
        if arm == "A":
            return True
        if arm == "B":
            return self.stage == STAGE2
        if arm == "B_fresh":
            return self.stage == STAGE2 and self.weeks_in_stage <= FRESH_WEEKS_MAX
        if arm == "C":
            return (self.stage == STAGE2 and self.ec_sent is not None
                    and self.ec_sent >= ec_gate)
        raise ValueError(f"unknown arm {arm!r}")


ARMS = ("A", "B", "B_fresh", "C")


def grade_fire(close: pd.Series, fire: Fire) -> Fire:
    """Grade one fire through the §3 ruler (both parameterizations + fwd metrics).

    ``close`` is the survivorship-resolved (dead-name-imputed) series used to grade. Sets
    ``state_15_126`` (clean15_126), ``state_8_21`` (clean8_21), the 21/63/126 forward
    metrics, and per-parameterization maturity flags. Fail-open (a bad series leaves the
    fire ungraded, matured=False → dropped from denominators)."""
    try:
        ts15 = grading.terminal_state(close, fire.date, **PARAM_CLEAN15_126)
        fire.state_15_126 = ts15.get("state")
        fire.matured_15_126 = fire.state_15_126 is not None
        fire._liftoff_bar_clean15_126 = ts15.get("liftoff_at_bar")
    except Exception as e:  # noqa: BLE001
        log.warning("psf: grade clean15_126 %s@%s failed (%s)", fire.ticker, fire.date, e)
    try:
        ts8 = grading.terminal_state(close, fire.date, **PARAM_CLEAN8_21)
        fire.state_8_21 = ts8.get("state")
        fire.matured_8_21 = fire.state_8_21 is not None
        fire._liftoff_bar_clean8_21 = ts8.get("liftoff_at_bar")
    except Exception as e:  # noqa: BLE001
        log.warning("psf: grade clean8_21 %s@%s failed (%s)", fire.ticker, fire.date, e)
    try:
        fire.fwd = grading.forward_metrics(close, fire.date, horizons=FWD_HORIZONS)
    except Exception as e:  # noqa: BLE001
        log.warning("psf: forward_metrics %s@%s failed (%s)", fire.ticker, fire.date, e)
        fire.fwd = {}
    # FIX-3: bars-to-MFE-peak over the 126-bar strictly-forward window (next-bar fill), for
    # ALL matured fires (unconditional). Mirrors grading.forward_metrics' fill convention.
    try:
        fill = grading.fill_index(close, fire.date)
        if fill is not None:
            fwd = close.iloc[fill + 1:fill + 1 + 126]
            if len(fwd) >= 126:
                arr = fwd.to_numpy(dtype=float)
                if np.isfinite(arr).any():
                    fire.bars_to_mfe_peak_126 = int(np.nanargmax(arr)) + 1  # 1-based bar
    except Exception as e:  # noqa: BLE001
        log.warning("psf: mfe-peak %s@%s failed (%s)", fire.ticker, fire.date, e)
    return fire


# --------------------------------------------------------------------------- #
# Per-ticker event pass (the efficient precompute).                            #
# --------------------------------------------------------------------------- #
def fires_for_ticker(ticker: str, close: pd.Series, volume: pd.Series | None,
                     bench_close: pd.Series, ec_by_ticker: dict[str, pd.DataFrame],
                     grade_close: pd.Series | None = None,
                     window_start: pd.Timestamp = WINDOW_START,
                     window_end: pd.Timestamp = WINDOW_END) -> tuple[list[Fire], bool]:
    """All graded fires for one ticker + a late-IPO flag (True = EXCLUDED, counted).

    ONE tier_stream + ONE stage_series precompute per ticker (§EFFICIENCY); each fresh-fire
    date then does an O(log n) stage/EC lookup. Late-IPO gate (§7): a name with < 45
    completed weekly bars at the LAST fire in-window is flagged excluded-and-counted (its
    fires that fall before the name has 45 weeks get stage=0 and are dropped from the
    stageable arms B/B-fresh/C but still counted in A). Returns ([] , True) for a name too
    young to stage at ALL of its in-window fires.
    """
    fires: list[Fire] = []
    try:
        dates = fresh_fire_dates(close)
    except Exception:  # noqa: BLE001
        return [], False
    if len(dates) == 0:
        return [], False

    # window filter (entries over 2022-01-01…2026-07-17)
    dates = dates[(dates >= window_start) & (dates <= window_end)]
    if len(dates) == 0:
        return [], False

    # precompute the weekly stage series ONCE (vectorized).
    try:
        stage_ser = weinstein_stage.stage_series(close, volume, bench_close)
    except Exception:  # noqa: BLE001
        stage_ser = pd.Series([], dtype="int64")

    gclose = grade_close if grade_close is not None else close
    any_stageable = False
    for d in dates:
        st, wis = _stage_lookup_from_series(stage_ser, d)
        # late-IPO / too-young: fewer than MIN_COMPLETED_WEEKS completed weeks at entry ->
        # stage unavailable for this fire (stage_series returns 0 there or no prior weeks).
        n_weeks_prior = int((stage_ser.index <= pd.Timestamp(d)).sum()) if not stage_ser.empty else 0
        if n_weeks_prior < MIN_COMPLETED_WEEKS:
            st, wis = 0, 0  # not stageable at this fire (counted in A, excluded from B/C)
        else:
            any_stageable = True
        ec = ec_sent_at_entry(ec_by_ticker, ticker, d)
        # tier at the fire day (T1 or T2 by construction of fresh_fire_dates)
        fire = Fire(ticker=ticker, date=pd.Timestamp(d), tier="T1/T2",
                    stage=st, weeks_in_stage=wis, ec_sent=ec)
        grade_fire(gclose, fire)
        fires.append(fire)

    late_ipo_excluded = (not any_stageable) and len(fires) > 0
    return fires, late_ipo_excluded


# --------------------------------------------------------------------------- #
# Arm aggregation — win-rate (Wilson CI), STOPPED, holds, n_dates, regimes.     #
# --------------------------------------------------------------------------- #
def _regime_of(date: pd.Timestamp) -> str | None:
    for name, (a, b) in REGIMES.items():
        if pd.Timestamp(a) <= date < pd.Timestamp(b):
            return name
    return None


def _median(vals: list[float]) -> float | None:
    v = [x for x in vals if x is not None and np.isfinite(x)]
    return float(np.median(v)) if v else None


def _mean(vals: list[float]) -> float | None:
    v = [x for x in vals if x is not None and np.isfinite(x)]
    return float(np.mean(v)) if v else None


def aggregate_arm(fires: list[Fire], arm: str, param: str = "clean15_126",
                  ec_gate: float = EC_SENT_GATE) -> dict[str, Any]:
    """§4 metrics for one arm at one ruler parameterization.

    param ∈ {"clean15_126","clean8_21"} selects the terminal-state field graded.
    Metrics: n_entries, n_dates (independent signal dates), CLEAN_LIFTOFF win-rate + Wilson
    95% CI, STOPPED rate, mean/median fwd_ret_63 & fwd_ret_126, median fwd_mdd_126, median
    bars-to-liftoff (via the ruler's liftoff bar), all over the MATURED subset for that
    parameterization.
    """
    if param == "clean15_126":
        state_attr, matured_attr, horizon = "state_15_126", "matured_15_126", 126
    elif param == "clean8_21":
        state_attr, matured_attr, horizon = "state_8_21", "matured_8_21", 21
    else:
        raise ValueError(f"unknown param {param!r}")

    members = [f for f in fires if f.in_arm(arm, ec_gate)]
    matured = [f for f in members if getattr(f, matured_attr)]

    n_entries = len(matured)
    # n_dates = independent signal dates (not overlapping observations): unique calendar
    # entry dates across DISTINCT names is over-counting; the spec's "independent signal
    # dates" = the count of unique (calendar) fire dates in the arm — overlapping same-day
    # fires across names are correlated by the market factor, so one date = one independent
    # observation for the CI's effective-n honesty check.
    dates = sorted({f.date.normalize() for f in matured})
    n_dates = len(dates)

    wins = sum(1 for f in matured if getattr(f, state_attr) == grading.TerminalState.CLEAN_LIFTOFF)
    stopped = sum(1 for f in matured if getattr(f, state_attr) == grading.TerminalState.STOPPED)

    win_pt, win_lo, win_hi = wilson_ci(wins, n_entries)
    stop_pt, stop_lo, stop_hi = wilson_ci(stopped, n_entries)

    fwd63 = [f.fwd.get("fwd_ret_63") for f in matured]
    fwd126 = [f.fwd.get("fwd_ret_126") for f in matured]
    mdd126 = [f.fwd.get("fwd_mdd_126") for f in matured]
    mfe126 = [f.fwd.get("fwd_mfe_126") for f in matured]

    # bars-to-liftoff: use the ruler's liftoff bar for CLEAN_LIFTOFF fires only.
    # CONDITIONAL-ON-WINNING (confounded) — kept for continuity but NOT the H3 primary.
    bars_to_liftoff: list[float] = []
    for f in matured:
        if getattr(f, state_attr) == grading.TerminalState.CLEAN_LIFTOFF:
            # re-derive the liftoff bar from the stored terminal_state note is heavy; instead
            # store it during grading. We recompute cheaply below via _liftoff_bar cache.
            b = getattr(f, f"_liftoff_bar_{param}", None)
            if b is not None:
                bars_to_liftoff.append(float(b))

    # FIX-3 unconditional hold/excursion metric — bars-to-MFE-peak over ALL matured fires
    # (not just winners), plus the median MFE magnitude. This is the honest H3 hold metric.
    bars_to_mfe = [f.bars_to_mfe_peak_126 for f in matured if f.bars_to_mfe_peak_126 is not None]

    return {
        "arm": arm,
        "param": param,
        "n_entries": n_entries,
        "n_dates": n_dates,
        "win_rate": win_pt,
        "win_ci95": [win_lo, win_hi],
        "wins": wins,
        "stopped": stopped,
        "stopped_rate": stop_pt,
        "stopped_ci95": [stop_lo, stop_hi],
        "mean_fwd_ret_63": _mean(fwd63),
        "median_fwd_ret_63": _median(fwd63),
        "mean_fwd_ret_126": _mean(fwd126),
        "median_fwd_ret_126": _median(fwd126),
        "median_fwd_mdd_126": _median(mdd126),
        "median_fwd_mfe_126": _median(mfe126),
        "median_bars_to_liftoff": _median(bars_to_liftoff),         # conditional-on-winning
        "median_bars_to_mfe_peak_126": _median([float(b) for b in bars_to_mfe]),  # UNCONDITIONAL (FIX-3)
    }


def aggregate_by_regime(fires: list[Fire], arm: str, param: str = "clean15_126",
                        ec_gate: float = EC_SENT_GATE) -> dict[str, dict[str, Any]]:
    """§4 per-regime metrics for one arm/param (2022 bear / 2023-24 bull / 2025-26)."""
    out: dict[str, dict[str, Any]] = {}
    for name in REGIMES:
        sub = [f for f in fires if _regime_of(f.date) == name]
        out[name] = aggregate_arm(sub, arm, param, ec_gate)
    return out


# --------------------------------------------------------------------------- #
# Block bootstrap by month (§4) — resample entry-MONTHS with replacement,       #
# recompute the win-rate, and report the bootstrap SE / percentile CI.          #
# --------------------------------------------------------------------------- #
def block_bootstrap_winrate(fires: list[Fire], arm: str, param: str = "clean15_126",
                            ec_gate: float = EC_SENT_GATE, n_boot: int = 2000,
                            seed: int = 20260720) -> dict[str, Any]:
    """Month-block bootstrap of the CLEAN_LIFTOFF win-rate (§4).

    Blocks = calendar months of the fire date (autocorrelated same-month fires travel
    together). Resample the set of months with replacement; recompute the pooled win-rate;
    report the bootstrap mean, SE, and 2.5/97.5 percentile CI. Degrades to nulls for < 2
    months of data.
    """
    if param == "clean15_126":
        state_attr, matured_attr = "state_15_126", "matured_15_126"
    else:
        state_attr, matured_attr = "state_8_21", "matured_8_21"

    members = [f for f in fires if f.in_arm(arm, ec_gate) and getattr(f, matured_attr)]
    if not members:
        return {"n_boot": 0, "mean": None, "se": None, "ci95": [None, None], "n_months": 0}

    by_month: dict[str, list[int]] = {}
    for f in members:
        key = f"{f.date.year}-{f.date.month:02d}"
        outcome = 1 if getattr(f, state_attr) == grading.TerminalState.CLEAN_LIFTOFF else 0
        by_month.setdefault(key, []).append(outcome)

    months = list(by_month.keys())
    n_months = len(months)
    if n_months < 2:
        return {"n_boot": 0, "mean": None, "se": None, "ci95": [None, None], "n_months": n_months}

    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    month_arr = np.array(months, dtype=object)
    for i in range(n_boot):
        pick = rng.integers(0, n_months, size=n_months)
        num = 0
        den = 0
        for j in pick:
            outs = by_month[month_arr[j]]
            num += sum(outs)
            den += len(outs)
        boots[i] = (num / den) if den else np.nan
    boots = boots[np.isfinite(boots)]
    if boots.size == 0:
        return {"n_boot": 0, "mean": None, "se": None, "ci95": [None, None], "n_months": n_months}
    return {
        "n_boot": int(boots.size),
        "mean": float(np.mean(boots)),
        "se": float(np.std(boots, ddof=1)) if boots.size > 1 else None,
        "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
        "n_months": n_months,
    }


def _month_outcomes(fires: list[Fire], arm: str, param: str,
                    ec_gate: float) -> dict[str, list[int]]:
    """{ "YYYY-MM" -> [1/0 CLEAN_LIFTOFF outcomes] } for the matured members of one arm.

    The month blocks are the resampling unit of the difference bootstrap (§4 independence:
    autocorrelated same-month fires travel together; the effective n is the count of
    independent monthly blocks, NOT the ~47k overlapping intra-month observations)."""
    if param == "clean15_126":
        state_attr, matured_attr = "state_15_126", "matured_15_126"
    else:
        state_attr, matured_attr = "state_8_21", "matured_8_21"
    members = [f for f in fires if f.in_arm(arm, ec_gate) and getattr(f, matured_attr)]
    by_month: dict[str, list[int]] = {}
    for f in members:
        key = f"{f.date.year}-{f.date.month:02d}"
        by_month.setdefault(key, []).append(
            1 if getattr(f, state_attr) == grading.TerminalState.CLEAN_LIFTOFF else 0)
    return by_month


def block_bootstrap_diff_ci(fires: list[Fire], arm_hi: str, arm_lo: str,
                            param: str = "clean15_126", ec_gate: float = EC_SENT_GATE,
                            n_boot: int = 2000, seed: int = 20260720) -> dict[str, Any]:
    """§4/§5 PRIMARY falsifier statistic: month-block bootstrap of the win-rate DIFFERENCE
    (win_hi − win_lo) — e.g. B−A for PSF-H1, C−B for PSF-H2.

    Effective-n honesty (the FIX-1 blocker): the Wilson diff CI is computed on n_entries
    (~15k–47k OVERLAPPING intra-month observations) and is therefore anti-conservative. The
    honest CI resamples the ~49–54 monthly blocks WITH REPLACEMENT, and on each resample
    recomputes BOTH arms' pooled win-rates on the SAME resampled set of months, takes the
    (hi − lo) difference, and reports the 2.5/97.5 percentile of those differences. Because
    both arms are recomputed on the identical resampled months, within-month cross-arm
    correlation is preserved (a paired-by-block bootstrap), so the difference CI is not
    inflated by the common market factor.

    Verdict semantics (mirror §5): the hypothesis FAILS iff the 2.5% percentile lower bound
    of the difference is <= 0 (the CI straddles or sits below 0). Degrades to nulls for < 2
    shared months. Returns the point difference, the bootstrap-diff mean/SE, the percentile
    CI, and the shared-month count.
    """
    by_month_hi = _month_outcomes(fires, arm_hi, param, ec_gate)
    by_month_lo = _month_outcomes(fires, arm_lo, param, ec_gate)
    # Months present in EITHER arm (a resampled month contributes each arm's fires for that
    # month; a month absent in one arm contributes 0/0 there and is simply skipped in that
    # arm's numerator/denominator — the point estimate below uses each arm's own pooled rate).
    months = sorted(set(by_month_hi) | set(by_month_lo))
    n_months = len(months)

    def _pooled(by_month: dict[str, list[int]], picked: np.ndarray, month_arr) -> float | None:
        num = den = 0
        for j in picked:
            outs = by_month.get(month_arr[j])
            if outs:
                num += sum(outs)
                den += len(outs)
        return (num / den) if den else None

    # point difference (over ALL months, no resampling)
    def _pooled_all(by_month: dict[str, list[int]]) -> float | None:
        num = sum(sum(v) for v in by_month.values())
        den = sum(len(v) for v in by_month.values())
        return (num / den) if den else None

    p_hi = _pooled_all(by_month_hi)
    p_lo = _pooled_all(by_month_lo)
    point = (p_hi - p_lo) if (p_hi is not None and p_lo is not None) else None

    if n_months < 2:
        return {"n_boot": 0, "diff_point": point, "diff_mean": None, "diff_se": None,
                "ci95": [None, None], "n_months": n_months,
                "lower_gt_0": False, "straddles_0": True}

    rng = np.random.default_rng(seed)
    month_arr = np.array(months, dtype=object)
    boots = np.empty(n_boot)
    boots[:] = np.nan
    for i in range(n_boot):
        pick = rng.integers(0, n_months, size=n_months)   # resample months WITH replacement
        rate_hi = _pooled(by_month_hi, pick, month_arr)     # BOTH arms on the SAME months
        rate_lo = _pooled(by_month_lo, pick, month_arr)     # (paired-by-block)
        if rate_hi is not None and rate_lo is not None:
            boots[i] = rate_hi - rate_lo
    boots = boots[np.isfinite(boots)]
    if boots.size == 0:
        return {"n_boot": 0, "diff_point": point, "diff_mean": None, "diff_se": None,
                "ci95": [None, None], "n_months": n_months,
                "lower_gt_0": False, "straddles_0": True}
    lo = float(np.percentile(boots, 2.5))
    hi = float(np.percentile(boots, 97.5))
    return {
        "n_boot": int(boots.size),
        "diff_point": point,
        "diff_mean": float(np.mean(boots)),
        "diff_se": float(np.std(boots, ddof=1)) if boots.size > 1 else None,
        "ci95": [lo, hi],
        "n_months": n_months,
        "lower_gt_0": bool(lo > 0.0),
        "straddles_0": bool(lo <= 0.0 <= hi),
    }


# --------------------------------------------------------------------------- #
# Falsifier verdicts (§5) — PSF-H1 / PSF-H2 / PSF-H3.                           #
# --------------------------------------------------------------------------- #
def falsifier_verdicts(fires: list[Fire], param: str = "clean15_126",
                       ec_gate: float = EC_SENT_GATE) -> dict[str, Any]:
    """The §5 pre-registered falsifier tests, returning pass|fail + the actual CI numbers.

    FIX-1 (effective-n honesty). The PRIMARY falsifier statistic is now the month-block
    bootstrap of the win-rate DIFFERENCE (``block_bootstrap_diff_ci``): the verdicts are
    re-derived off the bootstrap-diff 2.5% lower bound (> 0 to PASS), because the Wilson
    diff CI is computed on n_entries (~15k–47k OVERLAPPING intra-month observations) and is
    anti-conservative — its effective n is ~49–54 monthly blocks, not the raw fire count.
    The Wilson diff CIs are still reported, clearly labelled anti-conservative.

      * PSF-H1 FAILS iff the bootstrap-diff lower bound of (win_B − win_A) <= 0 at
        n_dates_B >= 25 (n_dates still gates power; the CI is the bootstrap one).
      * PSF-H1 hold-leg (H3, FIX-3) uses the UNCONDITIONAL bars-to-MFE-peak over ALL matured
        fires (not the conditional-on-winning bars-to-liftoff) + the STOPPED rate.
      * PSF-H2 FAILS iff the bootstrap-diff lower bound of (win_C − win_B) <= 0 at
        n_dates_C >= 25.
      * KILL iff a negative (win_B − win_A) point estimate persists at n_dates >= 50 across
        >= 2 regimes.
    """
    def _matured(arm: str) -> list[Fire]:
        mat = "matured_15_126" if param == "clean15_126" else "matured_8_21"
        return [f for f in fires if f.in_arm(arm, ec_gate) and getattr(f, mat)]

    def _win_counts(arm: str) -> tuple[int, int, int]:
        state = "state_15_126" if param == "clean15_126" else "state_8_21"
        mat = _matured(arm)
        wins = sum(1 for f in mat if getattr(f, state) == grading.TerminalState.CLEAN_LIFTOFF)
        n = len(mat)
        n_dates = len({f.date.normalize() for f in mat})
        return wins, n, n_dates

    aA = aggregate_arm(fires, "A", param, ec_gate)
    aB = aggregate_arm(fires, "B", param, ec_gate)
    aC = aggregate_arm(fires, "C", param, ec_gate)

    wA, nA, dA = _win_counts("A")
    wB, nB, dB = _win_counts("B")
    wC, nC, dC = _win_counts("C")

    # --- PSF-H1: stage quality lifts win-rate (B vs A) ---
    # PRIMARY = month-block bootstrap difference CI (FIX-1). Anti-conservative Wilson kept.
    boot1 = block_bootstrap_diff_ci(fires, "B", "A", param, ec_gate)
    dpt1, dlo1, dhi1 = wilson_diff_ci(wA, nA, wB, nB)       # anti-conservative (overlapping obs)
    h1_gate_met = dB >= 25
    b1_lo = boot1["ci95"][0]
    h1_fail = (b1_lo is None) or (b1_lo <= 0)   # PRIMARY: bootstrap-diff lower bound <= 0
    h1_verdict = "fail" if h1_fail else "pass"
    h1_note = ("PRIMARY = month-block bootstrap-diff CI (n_months≈%d); Wilson diff CI is "
               "ANTI-CONSERVATIVE (overlapping obs, effective n ≈ %d monthly blocks, not %d). "
               % (boot1["n_months"], boot1["n_months"], nB)) + (
               "n_dates gate met (>= 25)." if h1_gate_met
               else f"n_dates_B={dB} < 25 (underpowered — verdict provisional).")

    # --- PSF-H3: longer holds + lower STOPPED (B vs A) — FIX-3 unconditional metric ---
    # Conditional-on-winning bars-to-liftoff is confounded; the honest hold metric is the
    # UNCONDITIONAL median bars-to-MFE-peak over ALL matured fires.
    hold_B_uncond = aB.get("median_bars_to_mfe_peak_126")
    hold_A_uncond = aA.get("median_bars_to_mfe_peak_126")
    hold_B_cond = aB.get("median_bars_to_liftoff")     # kept for continuity (confounded)
    hold_A_cond = aA.get("median_bars_to_liftoff")
    stop_B = aB.get("stopped_rate")
    stop_A = aA.get("stopped_rate")
    # H3 FAILS if unconditional hold_B <= hold_A AND STOPPED_B >= STOPPED_A (both legs against).
    hold_worse = (hold_B_uncond is not None and hold_A_uncond is not None
                  and hold_B_uncond <= hold_A_uncond)
    stop_worse = (stop_B is not None and stop_A is not None and stop_B >= stop_A)
    h3_fail = bool(hold_worse and stop_worse)
    h3_verdict = "fail" if h3_fail else "pass"

    # --- PSF-H2: EC adds on top (C vs B) ---
    boot2 = block_bootstrap_diff_ci(fires, "C", "B", param, ec_gate)
    dpt2, dlo2, dhi2 = wilson_diff_ci(wB, nB, wC, nC)       # anti-conservative
    h2_gate_met = dC >= 25
    b2_lo = boot2["ci95"][0]
    h2_fail = (b2_lo is None) or (b2_lo <= 0)   # PRIMARY: bootstrap-diff lower bound <= 0
    h2_verdict = "fail" if h2_fail else "pass"
    h2_note = ("PRIMARY = month-block bootstrap-diff CI (n_months≈%d); Wilson diff CI is "
               "ANTI-CONSERVATIVE (overlapping obs, effective n ≈ %d monthly blocks, not %d). "
               % (boot2["n_months"], boot2["n_months"], nC)) + (
               "n_dates gate met (>= 25)." if h2_gate_met
               else f"n_dates_C={dC} < 25 (underpowered — verdict provisional).")

    # --- KILL rule: negative point estimate at n_dates >= 50 across >= 2 regimes ---
    kill_regimes: list[str] = []
    for name in REGIMES:
        sub = [f for f in fires if _regime_of(f.date) == name]
        rA = aggregate_arm(sub, "A", param, ec_gate)
        rB = aggregate_arm(sub, "B", param, ec_gate)
        if rB["n_dates"] >= 50 and rA["win_rate"] is not None and rB["win_rate"] is not None:
            if (rB["win_rate"] - rA["win_rate"]) < 0:
                kill_regimes.append(name)
    kill = len(kill_regimes) >= 2

    return {
        "param": param,
        "PSF_H1": {
            "verdict": h1_verdict,
            "primary_stat": "block_bootstrap_diff_ci (B−A)",
            "bootstrap_diff": boot1,
            "delta_win_B_minus_A": dpt1,
            "wilson_diff_ci95_ANTICONSERVATIVE": [dlo1, dhi1],
            "n_dates_B": dB, "n_dates_A": dA,
            "wins_B": wB, "n_B": nB, "wins_A": wA, "n_A": nA,
            "gate_met_n_dates_ge_25": h1_gate_met,
            "note": h1_note,
        },
        "PSF_H3": {
            "verdict": h3_verdict,
            "metric": "UNCONDITIONAL bars-to-MFE-peak over ALL matured fires (FIX-3)",
            "median_bars_to_mfe_peak_B": hold_B_uncond,
            "median_bars_to_mfe_peak_A": hold_A_uncond,
            "median_bars_to_liftoff_B_conditional": hold_B_cond,
            "median_bars_to_liftoff_A_conditional": hold_A_cond,
            "stopped_rate_B": stop_B,
            "stopped_rate_A": stop_A,
            "hold_worse": hold_worse, "stop_worse": stop_worse,
            "note": ("H3 fails only if BOTH unconditional-hold_B<=hold_A AND STOPPED_B>=STOPPED_A. "
                     "Caveat: the PASS rests on a conditional/asymmetric AND-both-legs falsifier — "
                     "NOT a clean win. Do NOT overstate 'longer holds'; it is a right-shift + a "
                     "lower stop rate, one leg at a time."),
        },
        "PSF_H2": {
            "verdict": h2_verdict,
            "primary_stat": "block_bootstrap_diff_ci (C−B)",
            "bootstrap_diff": boot2,
            "delta_win_C_minus_B": dpt2,
            "wilson_diff_ci95_ANTICONSERVATIVE": [dlo2, dhi2],
            "n_dates_C": dC, "n_dates_B": dB,
            "wins_C": wC, "n_C": nC, "wins_B": wB, "n_B": nB,
            "gate_met_n_dates_ge_25": h2_gate_met,
            "note": h2_note,
        },
        "KILL": {
            "triggered": kill,
            "negative_regimes_n_dates_ge_50": kill_regimes,
            "note": "KILL iff negative (win_B-win_A) point estimate at n_dates>=50 across >=2 regimes",
        },
    }


# --------------------------------------------------------------------------- #
# FIX-4 — dependence disclosure + de-overlapped robustness arm.                 #
# --------------------------------------------------------------------------- #
DEOVERLAP_WINDOW_BARS = 126  # one fire per name per non-overlapping 126-bar window


def fire_multiplicity(fires: list[Fire]) -> dict[str, Any]:
    """§FIX-4 dependence disclosure: per-name fire multiplicity (fires share the same name's
    overlapping forward windows → the ~47k fires are FAR from independent). Reports the mean
    and median fires-per-name and the total distinct names."""
    by_name: dict[str, int] = {}
    for f in fires:
        by_name[f.ticker] = by_name.get(f.ticker, 0) + 1
    counts = list(by_name.values())
    return {
        "n_names": len(by_name),
        "n_fires": len(fires),
        "mean_fires_per_name": float(np.mean(counts)) if counts else None,
        "median_fires_per_name": float(np.median(counts)) if counts else None,
        "max_fires_per_name": int(max(counts)) if counts else 0,
        "note": ("Per-name fire multiplicity: each name fires ~N times over the window and "
                 "each fire opens an OVERLAPPING 126-bar forward window, so same-name fires are "
                 "strongly dependent. The Wilson CIs (on n_entries) ignore this; the month-block "
                 "bootstrap and the de-overlapped robustness arm address it."),
    }


def de_overlap_fires(fires: list[Fire], window_bars: int = DEOVERLAP_WINDOW_BARS) -> list[Fire]:
    """§FIX-4: keep ONE fire per name per non-overlapping ``window_bars``-day window.

    Greedy left-to-right per name: sort a name's fires by date, keep the first, then skip
    every subsequent fire within ``window_bars`` calendar days of the last kept one; keep the
    next fire outside that window; repeat. This removes the overlapping-forward-window
    dependence WITHIN a name (cross-name same-day dependence is separately handled by the
    month-block bootstrap). Returns the de-overlapped fire list (a subset)."""
    by_name: dict[str, list[Fire]] = {}
    for f in fires:
        by_name.setdefault(f.ticker, []).append(f)
    kept: list[Fire] = []
    span = pd.Timedelta(days=window_bars)  # calendar-day proxy for the 126-BAR window (~26wk)
    for _tk, group in by_name.items():
        group.sort(key=lambda x: x.date)
        last_kept: pd.Timestamp | None = None
        for f in group:
            if last_kept is None or (f.date - last_kept) >= span:
                kept.append(f)
                last_kept = f.date
    return kept


def deoverlap_robustness(fires: list[Fire], param: str = "clean15_126",
                         ec_gate: float = EC_SENT_GATE) -> dict[str, Any]:
    """§FIX-4 robustness arm: re-run the §5 falsifiers on the de-overlapped fire set (one
    fire per name per non-overlapping 126-bar window) and report whether the null holds."""
    deov = de_overlap_fires(fires)
    fals = falsifier_verdicts(deov, param, ec_gate)
    return {
        "window_bars": DEOVERLAP_WINDOW_BARS,
        "n_fires_deoverlapped": len(deov),
        "n_fires_full": len(fires),
        "falsifiers": fals,
        "note": ("One fire per name per non-overlapping 126-bar window (removes within-name "
                 "overlapping-forward-window dependence). If the null holds here, it is robust "
                 "to the ~20-fires/name multiplicity."),
    }


# --------------------------------------------------------------------------- #
# Universe construction (§2 — baskets/ohlcv ∪ data/stocks) + price loaders.     #
# --------------------------------------------------------------------------- #
def _read_ohlcv(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_parquet(path)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty or "close" not in df.columns:
        return None
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:  # noqa: BLE001
            return None
    return df


def load_ticker_prices(ticker: str, data_root: Path) -> tuple[pd.Series | None, pd.Series | None]:
    """(close, volume) daily series for a ticker, preferring baskets/ohlcv then data/stocks
    (the §2 union; the deep stocks store extends late-IPO history). Fail-open → (None, None)."""
    for sub in ("baskets/ohlcv", "stocks"):
        p = data_root / sub / f"{ticker}.parquet"
        if not p.exists():
            continue
        df = _read_ohlcv(p)
        if df is None:
            continue
        close = df["close"].dropna()
        vol = df["volume"].dropna() if "volume" in df.columns else None
        if len(close):
            return close, vol
    return None, None


def _live_globbed_tickers(data_root: Path) -> set[str]:
    """Tickers present in the live price globs (baskets/ohlcv ∪ data/stocks), minus bench."""
    tickers: set[str] = set()
    for sub in ("baskets/ohlcv", "stocks"):
        d = data_root / sub
        if not d.exists():
            continue
        for p in d.glob("*.parquet"):
            tickers.add(p.stem)
    tickers.discard(BENCH_TICKER)
    return tickers


def build_universe(data_root: Path, dead_prices: dict[str, pd.Series] | None = None) -> list[str]:
    """The FIX-2 honest universe = the live globs (baskets/ohlcv ∪ data/stocks) UNION the
    delisted dead-name tickers ABSENT from those globs (so delisted, mostly-losing fires are
    counted, not survivorship-dropped). SPY (bench) excluded.

    Dead-name-absent tickers are graded via ``grading.resolve_series`` (which returns the
    dead series when there is no live cache). This is NOT full PIT: S&P-1500 PIT members
    with no price source anywhere are still absent — see ``survivorship_disclosure``.
    """
    live = _live_globbed_tickers(data_root)
    dead = dead_prices if dead_prices is not None else (grading.load_dead_prices() or {})
    dead_absent = {str(t) for t in dead.keys()} - live
    dead_absent.discard(BENCH_TICKER)
    return sorted(live | dead_absent)


def survivorship_disclosure(data_root: Path, dead_prices: dict[str, pd.Series] | None = None,
                            window_start: pd.Timestamp = WINDOW_START,
                            window_end: pd.Timestamp = WINDOW_END) -> dict[str, Any]:
    """Quantify the FIX-2 survivorship posture for the report §0/Universe block.

    Returns counts for: live-globbed names, dead-name tickers added (delisted, now counted),
    and the RESIDUAL PIT members that traded in-window but have NO price source anywhere
    (still absent, cannot be graded) — the honest remaining survivor-lean.
    """
    live = _live_globbed_tickers(data_root)
    dead = dead_prices if dead_prices is not None else (grading.load_dead_prices() or {})
    dead_tks = {str(t) for t in dead.keys()}
    dead_added = sorted(dead_tks - live - {BENCH_TICKER})

    pit_traded: set[str] = set()
    pit_absent_no_source: list[str] = []
    try:
        p = data_root / "breadth" / "sp1500_pit_membership.parquet"
        if p.exists():
            pit = pd.read_parquet(p)
            pit["start_date"] = pd.to_datetime(pit["start_date"], errors="coerce")
            pit["end_date"] = pd.to_datetime(pit["end_date"], errors="coerce")
            traded = pit[(pit["start_date"] <= window_end)
                         & (pit["end_date"].isna() | (pit["end_date"] >= window_start))]
            pit_traded = {str(t) for t in traded["ticker"].astype(str).unique()}
            have_source = live | dead_tks
            pit_absent_no_source = sorted(pit_traded - have_source)
    except Exception as e:  # noqa: BLE001
        log.warning("psf: survivorship_disclosure PIT read failed (%s)", e)

    return {
        "n_live_globbed": len(live),
        "n_dead_name_added_counted": len(dead_added),
        "n_pit_members_traded_in_window": len(pit_traded),
        "n_pit_absent_no_price_source": len(pit_absent_no_source),
        "posture": (
            "survivor-LEAN, not full PIT: live globs UNION delisted dead-name tickers "
            f"(+{len(dead_added)} counted); {len(pit_absent_no_source)} S&P-1500 PIT members "
            "that traded 2022-26 have NO price source anywhere and remain absent. Falsifier "
            "verdicts are DELTA-based (A→B→C); survivorship inflates all arms' ABSOLUTE "
            "win-rates ~symmetrically, so the null on the delta is robust to the residual "
            "lean, while absolute win-rates are upward-biased."),
    }


def load_bench_close(data_root: Path) -> pd.Series | None:
    """SPY daily close (data/yahoo/SPY.parquet) — the single §2 benchmark. Fail-open → None."""
    p = data_root / "yahoo" / "SPY.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    if df is None or df.empty:
        return None
    col = "close" if "close" in df.columns else ("close_price" if "close_price" in df.columns else None)
    if col is None:
        return None
    s = df[col].dropna()
    return s if len(s) else None


# --------------------------------------------------------------------------- #
# Full run driver — fan-out per ticker (capped 4 workers), aggregate, assemble. #
# --------------------------------------------------------------------------- #
_RUN_SHARED: dict[str, Any] = {}


def _run_init(data_root_str: str, ec_path_str: str | None) -> None:
    _RUN_SHARED["data_root"] = Path(data_root_str)
    _RUN_SHARED["bench"] = load_bench_close(Path(data_root_str))
    ec_df = load_ec_table(ec_path_str)
    _RUN_SHARED["ec"] = ec_index(ec_df)
    # dead-name price store for survivorship-imputed grading (grading.resolve_series).
    try:
        _RUN_SHARED["dead"] = grading.load_dead_prices()
    except Exception:  # noqa: BLE001
        _RUN_SHARED["dead"] = {}


def _run_one(ticker: str) -> tuple[list[Fire], bool, bool]:
    """Worker: (fires, late_ipo_excluded, had_prices) for one ticker."""
    dr: Path = _RUN_SHARED["data_root"]
    bench = _RUN_SHARED.get("bench")
    ec = _RUN_SHARED.get("ec", {})
    dead = _RUN_SHARED.get("dead", {})
    close, vol = load_ticker_prices(ticker, dr)
    if close is None:
        # FIX-2: a dead-name-absent (delisted) ticker has no live glob — resolve its close
        # from the dead-name store so its (mostly losing) fires are DETECTED, STAGED, and
        # GRADED, not survivorship-dropped. No volume series for these → stage classify
        # falls back to price-only (weinstein_stage handles vol=None).
        try:
            close = grading.resolve_series(ticker, None, dead_prices=dead)
        except Exception:  # noqa: BLE001
            close = None
        if close is None or close.empty:
            return [], False, False
        vol = None
    # survivorship-resolved grading series (dead-name terminal appended if delisted).
    try:
        gclose = grading.resolve_series(ticker, close, dead_prices=dead)
    except Exception:  # noqa: BLE001
        gclose = close
    if gclose is None:
        gclose = close
    fires, late = fires_for_ticker(ticker, close, vol, bench, ec, grade_close=gclose)
    return fires, late, True


def run_backtest(data_root: Path, tickers: list[str] | None = None,
                 ec_path: str | Path | None = None, max_workers: int = 4,
                 sample_n: int | None = None, sample_seed: int = 20260720) -> dict[str, Any]:
    """Run the full PSF backtest and return the results dict (also serialized by the CLI).

    Fans fire-detection+grading across processes (capped at 4). ``sample_n`` (if set and
    smaller than the universe) draws a representative random sample and DISCLOSES it —
    never a silent truncation (§EFFICIENCY). ``tickers`` overrides the universe (tests).
    """
    data_root = Path(data_root)
    dead_prices = grading.load_dead_prices() or {}
    if tickers is None:
        tickers = build_universe(data_root, dead_prices=dead_prices)
    n_universe = len(tickers)
    surv = survivorship_disclosure(data_root, dead_prices=dead_prices)

    sampled = False
    sample_note = None
    if sample_n is not None and sample_n < n_universe:
        rng = np.random.default_rng(sample_seed)
        idx = rng.choice(n_universe, size=sample_n, replace=False)
        tickers = [tickers[i] for i in sorted(idx)]
        sampled = True
        sample_note = (f"Representative random sample of {sample_n}/{n_universe} names "
                       f"(seed={sample_seed}, uniform over the union universe) — DISCLOSED, "
                       "not a silent truncation.")

    workers = max(1, min(int(max_workers), 4))
    all_fires: list[Fire] = []
    n_late_ipo = 0
    n_with_prices = 0

    if workers > 1 and len(tickers) > 20:
        try:
            from concurrent.futures import ProcessPoolExecutor
            ec_str = str(ec_path) if ec_path is not None else None
            with ProcessPoolExecutor(max_workers=workers, initializer=_run_init,
                                     initargs=(str(data_root), ec_str)) as ex:
                for fires, late, had in ex.map(_run_one, tickers, chunksize=16):
                    all_fires.extend(fires)
                    n_late_ipo += int(late)
                    n_with_prices += int(had)
        except Exception as e:  # noqa: BLE001 — parallelism must never break the run
            log.warning("psf: parallel run failed (%s) — serial fallback", e)
            all_fires, n_late_ipo, n_with_prices = [], 0, 0
            _run_init(str(data_root), str(ec_path) if ec_path is not None else None)
            for tk in tickers:
                fires, late, had = _run_one(tk)
                all_fires.extend(fires)
                n_late_ipo += int(late)
                n_with_prices += int(had)
    else:
        _run_init(str(data_root), str(ec_path) if ec_path is not None else None)
        for tk in tickers:
            fires, late, had = _run_one(tk)
            all_fires.extend(fires)
            n_late_ipo += int(late)
            n_with_prices += int(had)

    return assemble_results(all_fires, n_universe=n_universe, n_with_prices=n_with_prices,
                            n_late_ipo=n_late_ipo, sampled=sampled, sample_note=sample_note,
                            sample_n=(len(tickers) if sampled else n_universe),
                            survivorship=surv)


def assemble_results(fires: list[Fire], *, n_universe: int, n_with_prices: int,
                     n_late_ipo: int, sampled: bool = False, sample_note: str | None = None,
                     sample_n: int | None = None, ec_gate: float = EC_SENT_GATE,
                     survivorship: dict[str, Any] | None = None) -> dict[str, Any]:
    """Assemble the full §4 results dict (all arms × both params + regimes + bootstrap +
    §5 falsifiers), with the §0 proxy disclosure printed prominently at the top."""
    universe: dict[str, Any] = {
        "n_union_universe": n_universe,
        "n_with_prices": n_with_prices,
        "n_late_ipo_excluded_counted": n_late_ipo,
        "min_completed_weeks_gate": MIN_COMPLETED_WEEKS,
        "bench": BENCH_TICKER,
        "window": [str(WINDOW_START.date()), str(WINDOW_END.date())],
        "sampled": sampled,
        "sample_n": sample_n,
        "sample_note": sample_note,
    }
    if survivorship is not None:
        universe["survivorship"] = survivorship
    out: dict[str, Any] = {
        "proxy_disclosure": PROXY_DISCLOSURE,
        "spec": "research/PROPHET_STAGE_FUSION_PREREG.md",
        "generated_utc": pd.Timestamp.now("UTC").isoformat(),
        "universe": universe,
        "n_fires_total": len(fires),
        "ec_gate": ec_gate,
        "fire_multiplicity": fire_multiplicity(fires),   # FIX-4 dependence disclosure
        "params": {},
    }
    for param in ("clean15_126", "clean8_21"):
        arms_out: dict[str, Any] = {}
        for arm in ARMS:
            arms_out[arm] = {
                "overall": aggregate_arm(fires, arm, param, ec_gate),
                "by_regime": aggregate_by_regime(fires, arm, param, ec_gate),
                "bootstrap_winrate": block_bootstrap_winrate(fires, arm, param, ec_gate),
            }
        out["params"][param] = {
            "arms": arms_out,
            "falsifiers": falsifier_verdicts(fires, param, ec_gate),
            "deoverlap_robustness": deoverlap_robustness(fires, param, ec_gate),  # FIX-4
        }
    return out
