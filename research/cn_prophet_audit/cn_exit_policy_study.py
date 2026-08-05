"""CN exit-policy horse race — early-review families vs the H=10 incumbent.

MEASUREMENT INSTRUMENT, not a signal, not a promotion, not a recommendation. The CN
edition of ``scripts/exit_policy_study.py`` (the US horse race, where NOTHING beat the
H=10 incumbent). Same P0 discipline, same reporting discipline, same descriptive
verdict language. Consumed by the CN loser-audit masterplan
(``research/CHINA_PROPHET_LOSER_INTELLIGENCE_MASTERPLAN_BY_FABLE.md``).

WHY A CN EDITION AT ALL
----------------------
The US study asked "does a holder-with-rules beat the fixed horizon?" and answered no.
The CN loser audit (``RESULTS_2026-08-04.md``) then measured something the US cohort did
NOT show: CN losers are FRONT-LOADED BLEEDS. 90 of 128 losers were slow bleeds, 72 of 128
took a >=7% single down day, and an early mark of <= -3% already carried a ~70% eventual
loser rate finishing at a median -14.6% absolute. That is the exact shape an early-review
exit is supposed to catch. So the question is re-asked on CN's own tape, on CN's own
episodes, with CN's own fill and benchmark conventions.

THE RECONCILIATION DOCTRINE (PROPHET_LEARNING_LOOP_MASTERPLAN_BY_FABLE.md §1)
----------------------------------------------------------------------------
Two different jobs, two instruments, never one blended number:

  1. THE TRACK RECORD measures SIGNAL QUALITY — comparable, forced-verdict, fixed-H
     episodes. It must stay policy-free so eras and desks compare. The incumbent's
     68.6% is a statement about the BOARD, not about a trading plan.
  2. THIS STUDY measures TRADE MANAGEMENT — on IDENTICAL entries, what does a
     holder-with-rules capture? "Cut losers short / let winners run" is tested here.

Nothing in this file changes the public track record, the board, or any weight.
``engine/track_scoring.py`` and ``engine/china_standout_track.py`` are imported
READ-ONLY. A policy that eventually displaces the incumbent must go through its own
pre-registration first; this file cannot promote anything.

THE COHORT — exactly the production frame, asserted before any policy number prints
-----------------------------------------------------------------------------------
``engine.track_scoring.build_episodes`` over ``data/china_standout_track/board.parquet``
rows with ``board_definition == 'legacy'`` ({date -> set(tickers)}); fills via
``engine.china_standout_track._t1_fill`` (T+1 open, else (H+L)/2 proxy) with locked-limit
bars EXCLUDED as unfillable; closes from ``_price_frame``; benchmark 510300.SS (CSI300)
via ``_bench_close``. P0 gate: the incumbent H=10 forced verdict with
``include_fill_bar=True`` must reproduce n_matured=407, win 0.6855, median excess 4.44,
128 losers. ``assert_p0`` runs BEFORE any policy is evaluated and raises on any drift.

BAR NUMBERING (a pin, not a convention you can infer)
-----------------------------------------------------
``include_fill_bar=True`` means forward BAR 1 IS THE FILL BAR'S OWN CLOSE. The fill is
the T+1 open/(H+L)/2, so that same session's close is a legitimate day-one exit, and
``score_from_fill``'s ``held`` counts bars on exactly this basis (``held == 10`` exits on
bar 10). Every rule here reads the same numbering: "close of forward session k" is
``prices[k-1]``.

This matters because the loser audit's own ``first3`` column is NOT bar 3 in this
numbering — it indexes position 3 of an 11-bar array whose position 0 is the fill bar, so
the audit's cited "day-3 mark" is BAR 4 here. The study therefore prints the conditional
loser rate at EVERY bar 1..10 (``tell_by_bar``) rather than inheriting one bar by
reference, and the review families are run at the bar they say they run at.

INEQUALITY CONVENTIONS (every boundary is a choice; a reader should see it, not infer it)
-----------------------------------------------------------------------------------------
* EVERY exit trigger is INCLUSIVE. A review fires on ``mark <= -X``, a hard stop on
  ``mark <= -Y``, the extension arms on ``mark >= +5``. These are levels a desk would
  PUBLISH, and trading AT a published level is trading through the thesis, so a touch
  counts. (The US study's synthetic ATR bands lean the other way — strict ``<`` — because
  a band nobody published is an artefact of the rule rather than a level. Nothing here is
  synthetic, so nothing here is strict.)
* Maturity stays the grader's: ``n_avail >= horizon`` — exactly ten forward bars IS
  matured (``track_scoring.score_from_fill``).
* A WIN is strict ``> 0`` with NO dead band, taken from ``track_scoring.summarize`` rather
  than re-implemented. A loser is therefore ``excess <= 0``, which is how the loser audit
  counts its 128.
* ``capture`` requires a strictly positive MFE; rows with MFE <= 0 are counted, not
  divided (see ``policy_metrics``).

TRIGGERS ARE ABSOLUTE; SCORING IS RELATIVE (the load-bearing asymmetry)
----------------------------------------------------------------------
Every exit rule fires on the ABSOLUTE mark from fill — a trader can execute it without
knowing what CSI300 did. Every outcome is scored in CSI300 EXCESS, because that is the CN
desk's headline metric (in A-shares beta dominates, so an absolute win rate mostly
measures the index). So a rule can cut an absolute loss that was NOT an excess loss, and
the excess column will show that cost. Both legs are reported.

EXITS ARE CLOSE-ONLY. T+1 SEMANTICS.
------------------------------------
A rule reads the close of session k and exits AT that close. No walker looks at an
intraday low or a next-open fill. This is legal for a close-based rule and it is
CONSERVATIVE in one direction (it never fires on a session that pierced the level and
recovered) and OPTIMISTIC in another (it assumes you can transact at the close).

In A-shares the second half is the sharp one: the exchange's daily price limit means a
close-based stop can execute WELL BELOW its own trigger level, and on a locked-limit bar
(high == low == close) it cannot execute AT ALL. Both are MEASURED per policy, never
asserted: ``slip_*`` is realized ``exit_mark - trigger_level`` in points of entry;
``n_exit_bar_locked`` counts exits landing on a bar that never traded away from its limit;
``n_trigger_bar_at_limit`` counts triggers on a session whose own move was at/through the
board's price limit.

CENSORING — the extension family only
-------------------------------------
The review/stop families all resolve inside the 10-bar forced-verdict window, so they are
uncensored by construction. The asymmetric-extension family holds to bar 21, and only 150
of 407 episodes have 21 forward bars in the committed caches. Those rows are NOT dropped
(dropping them would delete exactly the positions still running — the outcome-conditioned
denominator ``track_scoring``'s rule 1 forbids). They are MARKED at the last available
close and flagged ``extended_data_end``; the count and the marked-share print in the
report. A data_end row is a MARK, not a realized exit, and its hold is a LOWER BOUND.

STATISTICS
----------
Episodes surfaced on one board night are ONE BET. Every interval is
``track_scoring.date_block_ci`` (whole board days resampled, seeded) and ``n_board_days``
prints beside ``n_matured`` everywhere. Policy-vs-incumbent comparisons are PAIRED
per-episode deltas with a blocked CI on the mean delta. The blocks THEMSELVES overlap —
12 board days spanning 06-30..07-17 with 10-session windows share most of their tape — so
every interval here is TOO NARROW; ``window_overlap`` measures the sharing and the report
prints it. No correction is applied and no p-value is computed: with 12 heavily
overlapping blocks either would be a decoration.

MULTIPLICITY: 11 challenger policies in 5 pre-declared families (day3-review 3,
day5-review 2, hard-stop 3, combined 1, extension 2). NO correction is applied. The family
sizes are printed so the reader can price the search themselves.

IN-SAMPLE, ONE ERA, ONE REGIME. Every number here was fitted and evaluated on the same 12
graded entry dates of a FALLING tape (CSI300's 10-session forward window was negative on
10 of those 12 dates). An exit rule that cuts losses is flattered by a down tape almost by
construction. Nothing here is out-of-sample and nothing here is a promotion.

Run from repo root:  python3 research/cn_prophet_audit/cn_exit_policy_study.py
Outputs (both frozen, committed beside this file):
    research/cn_prophet_audit/cn_exit_policy_results.json
    research/cn_prophet_audit/CN_EXIT_POLICY_STUDY.md
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import china_standout_track as cst  # noqa: E402
from engine import track_scoring as ts  # noqa: E402

# The freeze date, PINNED rather than read from the clock: this artifact is committed,
# so a wall-clock ``as_of`` would rewrite the JSON on every re-run and churn the diff.
# Same convention as the sibling ``v1_loser_audit.py``.
AS_OF = "2026-08-04"

H = 10                      # the shipped CN horizon (forced verdict)
H_EXT = 21                  # the asymmetric-extension family's cap
EXT_TRIGGER_PCT = 5.0       # extend only when the bar-10 absolute mark is >= this
DEF = "legacy"              # board_definition of the cn_standout_v1 era

OUT_JSON = Path(__file__).parent / "cn_exit_policy_results.json"
OUT_MD = Path(__file__).parent / "CN_EXIT_POLICY_STUDY.md"

# ── P0 gate: the shipped cn_track_ledger prior_record, as frozen by the loser audit ──
P0_N_MATURED = 407
P0_N_LOSERS = 128
P0_WIN = 0.6855
P0_WIN_TOL = 0.002
P0_MEDIAN_EXCESS = 4.44
P0_MEDIAN_EXCESS_TOL = 0.05

# Exit reasons.
R_HORIZON = "horizon"
R_REVIEW = "review"
R_HARD_STOP = "hard_stop"
R_EXT_HORIZON = "extended_horizon"
R_EXT_DATA_END = "extended_data_end"

_MFE_FLOOR = 1e-9           # capture needs a STRICTLY positive favourable excursion


def limit_threshold(ticker: str) -> float:
    """A-share daily price-limit magnitude by listing board (approx, non-ST).

    688* (STAR) and 300* (ChiNext) run +-20%; main boards (60*/00*) run +-10%. Detected
    slightly inside the band so a rounding/adjustment artefact does not hide a limit day.
    Identical to ``v1_loser_audit.limit_threshold`` so the two studies count the same days.
    """
    code = ticker.split(".")[0]
    return 0.185 if code.startswith(("300", "688")) else 0.095


def _r(v: float | None, nd: int = 2) -> float | None:
    if v is None:
        return None
    v = float(v)
    return None if not math.isfinite(v) else round(v, nd)


def _median(vals: Sequence[float]) -> float | None:
    v = [float(x) for x in vals if x is not None and math.isfinite(float(x))]
    return float(np.median(v)) if v else None


# --------------------------------------------------------------------------- #
# cohort — exactly the production frame
# --------------------------------------------------------------------------- #
def load_board_days() -> tuple[dict[str, set[str]], int]:
    """{board_date: {tickers}} over the legacy (cn_standout_v1) rows only."""
    df = pd.read_parquet(ROOT / "data/china_standout_track/board.parquet")
    df = df[df["board_definition"] == DEF]
    days: dict[str, set[str]] = defaultdict(set)
    for d, tk in zip(df["date"].astype(str), df["ticker"].astype(str)):
        days[d].add(tk)
    return dict(days), len(df)


def build_cohort() -> tuple[list[dict], dict[str, Any]]:
    """Matured episodes with their full forward close path and per-bar execution context.

    Every exclusion is COUNTED, never silent, and every exclusion is by DATA COVERAGE,
    FILL LEGALITY, or AGE — none of which can know which way a trade went.
    """
    board_days, n_rows = load_board_days()
    bench = cst._bench_close()  # noqa: SLF001
    if bench is None or bench.empty:
        raise RuntimeError("CSI300 benchmark unavailable — excess is the CN headline metric")

    frames: dict[str, pd.DataFrame | None] = {}
    excl = Counter()
    cohort: list[dict] = []
    n_episodes = 0

    for ep in ts.build_episodes(board_days):
        n_episodes += 1
        tk, d0s = ep["ticker"], ep["entry_date"]
        d0 = pd.Timestamp(d0s)
        if tk not in frames:
            frames[tk] = cst._price_frame(tk)  # noqa: SLF001
        pdf = frames[tk]
        if pdf is None or "close" not in pdf:
            excl["no_price_frame"] += 1
            continue
        fill, locked, pinned = cst._t1_fill(pdf, d0)  # noqa: SLF001
        if locked:
            excl["locked_limit_fill"] += 1
            continue
        closes = pd.to_numeric(pdf["close"], errors="coerce").dropna()
        after = closes.index[closes.index > d0]
        if fill is None or not len(after) or not math.isfinite(float(fill)) or fill <= 0:
            excl["no_fill"] += 1
            continue
        sc = ts.score_from_fill(closes, after[0], float(fill), H,
                                bench_close=bench, include_fill_bar=True)
        if sc is None:
            excl["unscoreable"] += 1
            continue
        if not sc.get("matured"):
            excl["immature"] += 1
            continue

        i_fill = int(closes.index.searchsorted(after[0], side="left"))
        fwd = closes.iloc[i_fill:]                     # bar 1 = the fill bar's OWN close
        prices = np.asarray(fwd.values, dtype=float)
        entry = float(fill)
        marks = (prices / entry - 1.0) * 100.0

        # Per-bar execution context: the session's OWN move (bar 1 measured against the
        # board-date close, which is the bar the reader saw) and whether the bar was a
        # locked-limit print that could not have been transacted at all.
        prev = np.empty(len(prices), dtype=float)
        prev[0] = float(closes.iloc[i_fill - 1]) if i_fill > 0 else float("nan")
        prev[1:] = prices[:-1]
        with np.errstate(invalid="ignore", divide="ignore"):
            bar_ret = prices / prev - 1.0
        hi = pd.to_numeric(pdf.get("high"), errors="coerce").reindex(fwd.index)
        lo = pd.to_numeric(pdf.get("low"), errors="coerce").reindex(fwd.index)
        bar_locked = ((hi.notna() & lo.notna())
                      & (hi.to_numpy() == lo.to_numpy())
                      & (hi.to_numpy() == prices)).to_numpy()

        cohort.append({
            "ticker": tk,
            "board_date": d0s,
            "fill_date": str(fwd.index[0].date()),
            "entry": entry,
            "pinned_ref": bool(pinned),
            "prices": prices,
            "marks": marks,
            "index": fwd.index,
            "fill_ts": fwd.index[0],
            "bar_ret": bar_ret,
            "bar_locked": bar_locked,
            "limit_th": limit_threshold(tk),
            "n_avail": int(sc["n_avail"]),
            # The grader's own verdict on this episode, kept for the P0 gate.
            "p0_excess": sc.get("excess"),
            "p0_pnl": sc.get("pnl"),
            "p0_held": sc.get("held"),
        })

    cohort.sort(key=lambda e: (e["board_date"], e["ticker"]))
    prov = {
        "board_rows": n_rows,
        "board_days": len(board_days),
        "episodes": n_episodes,
        "matured": len(cohort),
        "exclusions": dict(sorted(excl.items())),
        "graded_board_days": len({e["board_date"] for e in cohort}),
        "price_data_last_session": str(max(e["index"][-1] for e in cohort).date()),
        "n_avail_min": min(e["n_avail"] for e in cohort),
        "n_avail_median": int(np.median([e["n_avail"] for e in cohort])),
        "n_avail_max": max(e["n_avail"] for e in cohort),
        "n_with_21_bars": sum(1 for e in cohort if e["n_avail"] >= H_EXT),
    }
    return cohort, prov


def assert_p0(cohort: Sequence[Mapping[str, Any]]) -> dict:
    """HARD GATE. Reproduce the shipped prior_record before any policy number exists.

    Runs on the grader's OWN verdicts (``score_from_fill``'s excess), not on this study's
    re-walk, so a drift in the study's walker cannot mask a drift in the cohort.
    """
    ex = [float(e["p0_excess"]) for e in cohort if e["p0_excess"] is not None]
    n = len(ex)
    losers = sum(1 for v in ex if v <= 0)
    win = (n - losers) / n if n else float("nan")
    med = float(np.median(ex)) if ex else float("nan")
    gate = {"n_matured": n, "win_rate": round(win, 4), "n_losers": losers,
            "median_excess_pct": round(med, 4),
            "expected": {"n_matured": P0_N_MATURED, "win_rate": P0_WIN,
                         "n_losers": P0_N_LOSERS, "median_excess_pct": P0_MEDIAN_EXCESS}}
    assert n == P0_N_MATURED, f"P0 GATE: n_matured {n} != {P0_N_MATURED}"
    assert losers == P0_N_LOSERS, f"P0 GATE: losers {losers} != {P0_N_LOSERS}"
    assert abs(win - P0_WIN) <= P0_WIN_TOL, f"P0 GATE: win {win:.4f} != {P0_WIN}"
    assert abs(med - P0_MEDIAN_EXCESS) <= P0_MEDIAN_EXCESS_TOL, (
        f"P0 GATE: median excess {med:.4f} != {P0_MEDIAN_EXCESS}")
    # Every matured episode must carry the full forced-verdict window, or the walkers
    # would silently run short and the "same 407 episodes" claim would be false.
    assert all(len(e["marks"]) >= H for e in cohort), "P0 GATE: an episode is short of H"
    assert all(int(e["p0_held"]) == H for e in cohort), (
        "P0 GATE: CN incumbent must be a pure fixed horizon (no early-exit leg)")
    gate["passed"] = True
    return gate


# --------------------------------------------------------------------------- #
# the policies
# --------------------------------------------------------------------------- #
class Policy:
    """One exit rule. Pure parameters — the walker below is the only behaviour."""

    def __init__(self, key: str, label: str, family: str, *, review_bar: int | None = None,
                 review_pct: float | None = None, hard_stop_pct: float | None = None,
                 extend: bool = False) -> None:
        self.key = key
        self.label = label
        self.family = family
        self.review_bar = review_bar
        self.review_pct = review_pct
        self.hard_stop_pct = hard_stop_pct
        self.extend = extend

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "family": self.family,
                "review_bar": self.review_bar, "review_pct": self.review_pct,
                "hard_stop_pct": self.hard_stop_pct,
                "extend_to_bar": H_EXT if self.extend else None,
                "extend_trigger_pct": EXT_TRIGGER_PCT if self.extend else None}


INCUMBENT = Policy("P0", "incumbent — fixed H=10 forced verdict", "incumbent")

POLICIES: tuple[Policy, ...] = (
    INCUMBENT,
    # 1. day-3 review
    Policy("R3x2", "day-3 review, exit if mark <= -2%", "day3_review",
           review_bar=3, review_pct=2.0),
    Policy("R3x3", "day-3 review, exit if mark <= -3%", "day3_review",
           review_bar=3, review_pct=3.0),
    Policy("R3x5", "day-3 review, exit if mark <= -5%", "day3_review",
           review_bar=3, review_pct=5.0),
    # 2. day-5 review
    Policy("R5x3", "day-5 review, exit if mark <= -3%", "day5_review",
           review_bar=5, review_pct=3.0),
    Policy("R5x5", "day-5 review, exit if mark <= -5%", "day5_review",
           review_bar=5, review_pct=5.0),
    # 3. hard stop on any forward close
    Policy("S6", "hard stop -6% (first close through)", "hard_stop", hard_stop_pct=6.0),
    Policy("S8", "hard stop -8% (first close through)", "hard_stop", hard_stop_pct=8.0),
    Policy("S10", "hard stop -10% (first close through)", "hard_stop", hard_stop_pct=10.0),
    # 4. combined
    Policy("R3x3_S8", "day-3 review -3% PLUS hard stop -8%", "combined",
           review_bar=3, review_pct=3.0, hard_stop_pct=8.0),
    # 5. asymmetric extension (winners-run half)
    Policy("EXT", f"extend to bar {H_EXT} if bar-{H} mark >= +{EXT_TRIGGER_PCT:.0f}%",
           "extension", extend=True),
    Policy("R3x3_EXT", f"day-3 review -3% PLUS extend to bar {H_EXT} "
                       f"if bar-{H} mark >= +{EXT_TRIGGER_PCT:.0f}%",
           "extension", review_bar=3, review_pct=3.0, extend=True),
)

FAMILY_SIZE = Counter(p.family for p in POLICIES if p.key != "P0")


def walk(marks: np.ndarray, policy: Policy) -> tuple[int, str, float | None]:
    """(exit_index_0based, reason, trigger_level_pct_or_None). Close-only, no lookahead.

    Within a bar the HARD STOP is tested before the scheduled review. On the one bar
    where both can fire the review level is the looser of the two, so both resolve at the
    same close and the ordering is immaterial to the P&L — it is pinned so the exit
    REASON is deterministic rather than dependent on dict ordering.
    """
    n = len(marks)
    limit = min(H, n)
    for i in range(limit):
        m = float(marks[i])
        if not math.isfinite(m):
            continue
        if policy.hard_stop_pct is not None and m <= -policy.hard_stop_pct:
            return i, R_HARD_STOP, -policy.hard_stop_pct
        if (policy.review_bar is not None and (i + 1) == policy.review_bar
                and m <= -policy.review_pct):
            return i, R_REVIEW, -policy.review_pct
    i10 = limit - 1
    if policy.extend and float(marks[i10]) >= EXT_TRIGGER_PCT:
        j = min(H_EXT, n) - 1
        return j, (R_EXT_HORIZON if n >= H_EXT else R_EXT_DATA_END), None
    return i10, R_HORIZON, None


def _excess(ep: Mapping[str, Any], exit_idx: int, pnl: float,
            bench: pd.Series) -> float | None:
    """Benchmark leg over the SAME fill bar -> exit bar window, matched by TIMESTAMP.

    Byte-identical in method to ``track_scoring.score_from_fill``: the name and the ETF
    can keep different holiday calendars, so offset arithmetic would drift.
    """
    b = bench.dropna()
    bi = int(b.index.searchsorted(ep["fill_ts"], side="left"))
    bj = int(b.index.searchsorted(ep["index"][exit_idx], side="left"))
    if bi >= len(b) or bj >= len(b) or bj < bi:
        return None
    b0, b1 = float(b.iloc[bi]), float(b.iloc[bj])
    if not (math.isfinite(b0) and b0 > 0 and math.isfinite(b1)):
        return None
    return pnl - (b1 / b0 - 1.0) * 100.0


def score_row(ep: Mapping[str, Any], policy: Policy, bench: pd.Series) -> dict:
    """One scored row, shaped for ``track_scoring.summarize``."""
    exit_idx, reason, trigger = walk(ep["marks"], policy)
    held = exit_idx + 1
    entry = float(ep["entry"])
    exit_px = float(ep["prices"][exit_idx])
    pnl = (exit_px / entry - 1.0) * 100.0
    window = ep["prices"][:held]
    mfe = (float(np.nanmax(window)) / entry - 1.0) * 100.0
    mae = (float(np.nanmin(window)) / entry - 1.0) * 100.0
    br = float(ep["bar_ret"][exit_idx])
    return {
        "ticker": ep["ticker"],
        "board_date": ep["board_date"],
        "entry_date": ep["fill_date"],
        "exit_date": str(ep["index"][exit_idx].date()),
        "matured": True,
        "entry": entry,
        "exit": exit_px,
        "held": held,
        "exit_reason": reason,
        "censored": reason == R_EXT_DATA_END,
        "pnl": pnl,
        "excess": _excess(ep, exit_idx, pnl, bench),
        "mfe": mfe,
        "mae": mae,
        "trigger_level_pct": trigger,
        # realized slippage: how far BELOW its own trigger the close-only fill landed.
        "slip_pp": (float(ep["marks"][exit_idx]) - trigger) if trigger is not None else None,
        # A resting stop is in the market on EVERY bar, including bar H — and a trigger
        # there exits at the same close the forced verdict would have. The rule fired,
        # but the trade is economically identical to the incumbent (delta exactly 0), so
        # the count is disclosed rather than allowed to inflate "n_triggered".
        "trigger_is_noop": bool(trigger is not None and held == H),
        "exit_bar_locked": bool(ep["bar_locked"][exit_idx]),
        "exit_bar_ret_pct": _r(br * 100.0) if math.isfinite(br) else None,
        "exit_bar_at_limit": bool(math.isfinite(br) and br <= -float(ep["limit_th"])),
    }


def evaluate(cohort: Sequence[Mapping[str, Any]],
             bench: pd.Series) -> dict[str, list[dict]]:
    """Run every policy over the SAME 407 matured episodes. {policy_key: [scored rows]}."""
    return {p.key: [score_row(ep, p, bench) for ep in cohort] for p in POLICIES}


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def policy_metrics(rows: Sequence[Mapping[str, Any]]) -> dict:
    """Headline block for one policy, computed through ``track_scoring.summarize``.

    ``summarize`` supplies the ledger's own definitions (win = strict > 0, no dead band,
    date-blocked CIs) so this study cannot invent a second convention for the headline.

    ONE deliberate departure: ``capture`` is recomputed with MFE <= 0 rows DROPPED rather
    than divided. ``summarize``'s filter is ``abs(mfe) > 1e-9``, which admits a NEGATIVE
    MFE — a position that never traded above its entry inside the window — and
    realised/MFE there is a ratio of two negatives that prints as a healthy positive. The
    dropped rows are counted, not hidden.
    """
    out = dict(ts.summarize(rows, metric="excess", horizon=H))

    # absolute-P&L legs beside the excess headline: the rules fire on absolute marks, so
    # a reader has to be able to see what they did to the absolute book as well.
    pnl = np.array([float(r["pnl"]) for r in rows if r.get("pnl") is not None], dtype=float)
    out["pnl_win_pct"] = _r(float((pnl > 0).mean() * 100.0), 1) if len(pnl) else None
    out["pnl_expectancy_pct"] = _r(float(pnl.mean())) if len(pnl) else None
    out["pnl_median_pct"] = _r(float(np.median(pnl))) if len(pnl) else None

    caps = [float(r["pnl"]) / float(r["mfe"]) for r in rows
            if r.get("mfe") is not None and math.isfinite(float(r["mfe"]))
            and float(r["mfe"]) > _MFE_FLOOR]
    out["capture"] = _r(float(np.median(caps))) if caps else None
    out["n_capture"] = len(caps)
    out["n_capture_undefined"] = len(rows) - len(caps)

    holds = [int(r["held"]) for r in rows]
    out["mean_hold"] = _r(float(np.mean(holds)), 1) if holds else None
    out["max_hold"] = max(holds) if holds else None
    out["exit_reasons"] = dict(sorted(Counter(str(r["exit_reason"]) for r in rows).items()))
    cens = [r for r in rows if r.get("censored")]
    out["n_censored"] = len(cens)
    out["censored_pct"] = _r(100.0 * len(cens) / len(rows), 1) if rows else None

    # ── A-share execution reality, measured on this policy's own exits ────────────
    #
    # ``exit_mark - trigger_level`` is the SAME arithmetic for both trigger kinds and it
    # does NOT mean the same thing, so it is reported split, never pooled:
    #
    #   RESTING STOP (`hard_stop`) — the level sits in the market on every bar. A real
    #       order fills near it intraday; this study fills at the close, which is by
    #       construction at or through it. The gap IS the close-only convention's
    #       execution cost, and it is a LOWER bound (no queue model, and a real stop
    #       would additionally fire on sessions this study holds through).
    #   SCHEDULED REVIEW (`review`) — the threshold is read ONCE, at a scheduled bar.
    #       Nothing was resting; the position is simply already deeper than the trigger
    #       when the calendar reaches the review. That is a property of the COHORT, not
    #       an execution cost, and reading it as slippage would roughly double the
    #       review families' apparent execution penalty.
    fired = [r for r in rows if r.get("trigger_level_pct") is not None]
    out["n_triggered"] = len(fired)
    kinds = {"resting_stop": [r for r in fired if r["exit_reason"] == R_HARD_STOP],
             "scheduled_review": [r for r in fired if r["exit_reason"] == R_REVIEW]}
    out["trigger_overshoot"] = {}
    for kind, rs in kinds.items():
        vals = [float(r["slip_pp"]) for r in rs if r.get("slip_pp") is not None]
        if not vals:
            continue
        out["trigger_overshoot"][kind] = {
            "n": len(rs),
            "n_noop_at_horizon_bar": sum(1 for r in rs if r.get("trigger_is_noop")),
            "mean_pp": _r(float(np.mean(vals))),
            "median_pp": _r(float(np.median(vals))),
            "p10_pp": _r(float(np.percentile(vals, 10))),
            "worst_pp": _r(float(np.min(vals))),
            "n_worse_than_2pp": sum(1 for v in vals if v <= -2.0),
            "n_bar_at_daily_limit": sum(1 for r in rs if r.get("exit_bar_at_limit")),
        }
    st = out["trigger_overshoot"].get("resting_stop") or {}
    out["stop_slip_mean_pp"] = st.get("mean_pp")
    out["stop_slip_worst_pp"] = st.get("worst_pp")
    out["n_trigger_bar_at_limit"] = sum(1 for r in fired if r.get("exit_bar_at_limit"))
    out["n_trigger_noop_at_horizon_bar"] = sum(1 for r in fired
                                               if r.get("trigger_is_noop"))
    out["n_exit_bar_locked"] = sum(1 for r in rows if r.get("exit_bar_locked"))
    return out


def paired_delta(rows: Sequence[Mapping[str, Any]], base: Sequence[Mapping[str, Any]],
                 field: str = "excess") -> dict:
    """Mean per-episode (policy - incumbent) with a date-blocked CI.

    PAIRED, not two-sample: the same entry on the same date appears in both legs, so the
    difference isolates the exit rule and removes the entry cohort's variance entirely.
    The CI still resamples whole board days — the pairs from one night are still one bet.
    """
    by_key = {(r["ticker"], r["board_date"]): r for r in base}
    deltas: list[tuple[str, float]] = []
    for r in rows:
        b = by_key.get((r["ticker"], r["board_date"]))
        if b is None or r.get(field) is None or b.get(field) is None:
            continue
        deltas.append((str(r["board_date"]), float(r[field]) - float(b[field])))
    if not deltas:
        return {"n": 0, "mean_delta_pp": None, "lo_pp": None, "hi_pp": None,
                "n_board_days": 0, "separates": False}
    vals = np.array([d for _, d in deltas], dtype=float)
    lo, hi = ts.date_block_ci(deltas, lambda a: float(a.mean()))
    return {
        "n": len(deltas),
        "n_board_days": len({d for d, _ in deltas}),
        "mean_delta_pp": _r(float(vals.mean()), 3),
        "median_delta_pp": _r(float(np.median(vals)), 3),
        "lo_pp": _r(lo, 3) if lo is not None else None,
        "hi_pp": _r(hi, 3) if hi is not None else None,
        "separates": bool(lo is not None and hi is not None and (lo > 0 or hi < 0)),
    }


def cut_vs_forfeit(rows: Sequence[Mapping[str, Any]], base: Sequence[Mapping[str, Any]],
                   field: str = "excess") -> dict:
    """The operator's criterion, made explicit: cut the losers, don't cut the winners.

    Partition on how the INCUMBENT called each episode (its 128 losers / 279 winners),
    then count how many rows the policy moved which way, and price both halves. The two
    net contributions sum to the overall mean delta exactly — asserted, because a
    decomposition whose halves do not add up to its own total is an advert, not a
    measurement.
    """
    by_key = {(r["ticker"], r["board_date"]): r for r in base}
    halves: dict[str, list[dict]] = {"losers": [], "winners": []}
    for r in rows:
        b = by_key.get((r["ticker"], r["board_date"]))
        if b is None or r.get(field) is None or b.get(field) is None:
            continue
        side = "losers" if float(b[field]) <= 0 else "winners"
        halves[side].append({"delta": float(r[field]) - float(b[field]),
                             "policy": float(r[field]), "base": float(b[field])})
    n_total = len(halves["losers"]) + len(halves["winners"])
    out: dict[str, Any] = {"n_total": n_total}
    for side, recs in halves.items():
        d = np.array([x["delta"] for x in recs], dtype=float) if recs else np.array([])
        out[side] = {
            "n": len(recs),
            "n_improved": int((d > 0).sum()) if len(d) else 0,
            "n_degraded": int((d < 0).sum()) if len(d) else 0,
            "n_unchanged": int((d == 0).sum()) if len(d) else 0,
            "n_flipped_sign": sum(1 for x in recs
                                  if (x["base"] <= 0) != (x["policy"] <= 0)),
            "mean_delta_in_half_pp": _r(float(d.mean()), 3) if len(d) else None,
            "median_delta_in_half_pp": _r(float(np.median(d)), 3) if len(d) else None,
            "net_contribution_pp": _r(float(d.sum()) / n_total, 3) if n_total else None,
        }
    out["losers_cut_net_pp"] = out["losers"]["net_contribution_pp"]
    out["winners_forfeited_net_pp"] = out["winners"]["net_contribution_pp"]
    # The operator's headline ratio: losers improved per winner degraded.
    wd = out["winners"]["n_degraded"]
    out["improved_per_winner_degraded"] = (
        _r(out["losers"]["n_improved"] / wd) if wd else None)
    return out


def tell_by_bar(cohort: Sequence[Mapping[str, Any]],
                base: Sequence[Mapping[str, Any]],
                thresholds: Iterable[float] = (-2.0, -3.0, -5.0)) -> dict:
    """P(eventual incumbent loser | mark at bar k <= threshold), for every bar 1..10.

    The review families pick a bar and a threshold; this is the evidence that grounds
    that pick, measured at every bar rather than inherited by reference from the loser
    audit (whose ``first3`` column indexes bar 4 in this study's numbering — see the
    module docstring's BAR NUMBERING pin).
    """
    by_key = {(r["ticker"], r["board_date"]): r for r in base}
    out: dict[str, Any] = {}
    for th in thresholds:
        rows = []
        for k in range(1, H + 1):
            hit = [ep for ep in cohort if math.isfinite(float(ep["marks"][k - 1]))
                   and float(ep["marks"][k - 1]) <= th]
            scored = [by_key[(e["ticker"], e["board_date"])] for e in hit
                      if (e["ticker"], e["board_date"]) in by_key]
            scored = [r for r in scored if r.get("excess") is not None]
            losers = [r for r in scored if float(r["excess"]) <= 0]
            rows.append({
                "bar": k,
                "n_hit": len(scored),
                "hit_pct_of_cohort": _r(100.0 * len(scored) / len(cohort), 1),
                "p_loser": _r(len(losers) / len(scored), 3) if scored else None,
                "median_final_excess_pct": _r(_median([r["excess"] for r in scored])),
                "median_final_pnl_pct": _r(_median([r["pnl"] for r in scored])),
            })
        out[f"mark_le_{abs(th):g}pct"] = rows
    return out


def window_overlap(cohort: Sequence[Mapping[str, Any]], bench: pd.Series,
                   horizon: int = H) -> dict:
    """How much of the tape neighbouring board days SHARE — the block-CI caveat, measured.

    ``date_block_ci`` resamples whole board days because episodes from one night are one
    bet. That fixes the WITHIN-day dependence and does nothing about the BETWEEN-day one.
    Measured rather than asserted: neighbour-pair overlap and the largest set of board
    days whose windows are pairwise DISJOINT — an honest floor on how many genuinely
    independent windows this sample contains. No correction is applied.
    """
    days = sorted({e["board_date"] for e in cohort})
    idx = bench.index
    spans: dict[str, tuple[int, int]] = {}
    for d in days:
        lo = int(idx.searchsorted(pd.Timestamp(d), side="right"))   # bar 1 = T+1
        spans[d] = (lo, min(lo + horizon, len(idx)))
    pairs = []
    for a, b in pairwise(days):
        (a0, a1), (b0, b1) = spans[a], spans[b]
        width = max(1, a1 - a0)
        pairs.append(round(100.0 * max(0, min(a1, b1) - max(a0, b0)) / width, 1))
    n_disjoint, end = 0, -1
    for d in sorted(days, key=lambda x: (spans[x][1], x)):
        s0, s1 = spans[d]
        if s0 >= end:
            n_disjoint += 1
            end = s1
    union: set[int] = set()
    for d in days:
        union |= set(range(*spans[d]))
    return {
        "n_board_days": len(days),
        "horizon": horizon,
        "overlap_min_pct": min(pairs) if pairs else None,
        "overlap_median_pct": _r(float(np.median(pairs)), 1) if pairs else None,
        "overlap_max_pct": max(pairs) if pairs else None,
        "n_neighbour_pairs_over_50": sum(1 for p in pairs if p >= 50.0),
        "max_disjoint_windows": n_disjoint,
        "union_sessions": len(union),
        "total_window_bars": sum(b - a for a, b in spans.values()),
    }


def regime(cohort: Sequence[Mapping[str, Any]], bench: pd.Series) -> dict:
    """The tape these rules were measured on. A stop family is flattered by a down tape."""
    days = sorted({e["board_date"] for e in cohort})
    rows = []
    for d in days:
        b = bench[bench.index > pd.Timestamp(d)]
        rows.append({"board_date": d,
                     "csi300_fwd10_pct": _r(float(b.iloc[H] / b.iloc[0] - 1.0) * 100.0)
                     if len(b) > H else None})
    vals = [r["csi300_fwd10_pct"] for r in rows if r["csi300_fwd10_pct"] is not None]
    return {"by_board_date": rows, "n_dates": len(vals),
            "n_negative": sum(1 for v in vals if v < 0),
            "median_pct": _r(_median(vals)),
            "min_pct": _r(min(vals)) if vals else None,
            "max_pct": _r(max(vals)) if vals else None}


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def _f(v: Any, nd: int = 2, suffix: str = "") -> str:
    if v is None:
        return "—"
    if isinstance(v, (int, np.integer)) and nd == 0:
        return f"{int(v)}{suffix}"
    return f"{float(v):.{nd}f}{suffix}"


def _sgn(v: Any, nd: int = 2) -> str:
    return "—" if v is None else f"{float(v):+.{nd}f}"


def render_md(res: Mapping[str, Any]) -> str:
    m = res["metrics"]
    d = res["deltas"]
    c = res["cut_vs_forfeit"]
    base = m["P0"]
    keys = [p["key"] for p in res["policies"]]
    chal = [k for k in keys if k != "P0"]
    lab = {p["key"]: p["label"] for p in res["policies"]}

    # Verdict arithmetic — computed, never asserted, so the summary cannot drift from
    # the table beneath it.
    fam = {p["key"]: p["family"] for p in res["policies"]}
    uncensored = [k for k in chal if not m[k]["n_censored"]]
    separating = [k for k in chal if d[k]["separates"] and (d[k]["mean_delta_pp"] or 0) > 0]
    sep_pnl = [k for k in chal if d[k]["paired_delta_pnl"]["separates"]
               and (d[k]["paired_delta_pnl"]["mean_delta_pp"] or 0) > 0]
    beats_win = [k for k in chal if (m[k]["win_pct"] or 0) > (base["win_pct"] or 0)]
    beats_median = [k for k in chal
                    if (m[k]["median_pct"] or 0) > (base["median_pct"] or 0)]
    beats_pf = [k for k in chal
                if (m[k]["profit_factor"] or 0) > (base["profit_factor"] or 0)]
    best_mean = max(uncensored, key=lambda k: d[k]["mean_delta_pp"] or -99)
    # "Best" MAE-p10 is the LEAST negative left tail, i.e. the maximum of a negative stat.
    best_mae = max(chal, key=lambda k: (m[k].get("mae_p10_pct") or -99))
    best_ratio = max(chal, key=lambda k: c[k]["improved_per_winner_degraded"] or -1)
    d3 = [k for k in chal if fam[k] == "day3_review"]
    d3_best = max(d3, key=lambda k: d[k]["mean_delta_pp"] or -99)
    tell3 = {r["bar"]: r for r in res["tell_by_bar"]["mark_le_3pct"]}
    stop_over = [m[k]["trigger_overshoot"]["resting_stop"] for k in chal
                 if "resting_stop" in m[k]["trigger_overshoot"]]
    stop_n = sum(x["n"] for x in stop_over)
    stop_noop = sum(x["n_noop_at_horizon_bar"] for x in stop_over)
    stop_lim = sum(x["n_bar_at_daily_limit"] for x in stop_over)
    stop_mean = (sum(x["mean_pp"] * x["n"] for x in stop_over) / stop_n) if stop_n else None
    stop_worst = min((x["worst_pp"] for x in stop_over), default=None)

    L: list[str] = []
    A = L.append
    A("# CN exit-policy horse race — early-review families vs the H=10 incumbent")
    A("")
    A(f"Frozen {res['as_of']} · era `cn_standout_v1` (`board_definition='legacy'`), "
      f"{res['provenance']['graded_board_days']} graded entry dates "
      f"{res['regime']['by_board_date'][0]['board_date']} → "
      f"{res['regime']['by_board_date'][-1]['board_date']} · "
      f"instrument `research/cn_prophet_audit/cn_exit_policy_study.py` · "
      "raw `cn_exit_policy_results.json`")
    A("")
    A("## DECISION-RELEVANT SUMMARY")
    A("")
    A(f"1. **No challenger beats the incumbent on the CN desk's own headline stats.** "
      f"{len(beats_win)}/{len(chal)} beat its {_f(base['win_pct'], 1)}% win rate and "
      f"{len(beats_median)}/{len(chal)} beat its {_f(base['median_pct'])}% median "
      f"excess — every single rule tested lowers both. What some of them buy instead is "
      f"MEAN excess, profit factor ({len(beats_pf)}/{len(chal)} beat "
      f"{_f(base['profit_factor'])}) and a thinner left tail.")
    A(f"2. **The day-3 review family — the rule this study was commissioned to test — "
      f"does not pay.** Its best member `{d3_best}` ({lab[d3_best]}) moves mean excess "
      f"{_sgn(d[d3_best]['mean_delta_pp'], 2)} pp "
      f"[{_f(d[d3_best]['lo_pp'])}, {_f(d[d3_best]['hi_pp'])}] — indistinguishable from "
      f"zero — while cutting win rate {_sgn(d[d3_best]['win_pct_delta'], 1)} pp and "
      f"median excess {_sgn(d[d3_best]['median_pct_delta'])} pp.")
    A(f"3. **Why: the day-3 tell is not sharper than the day-1 tell.** "
      f"P(eventual loser | mark ≤ −3%) is {_f(tell3[1]['p_loser'], 2)} at bar 1, "
      f"{_f(tell3[3]['p_loser'], 2)} at bar 3, and only reaches "
      f"{_f(tell3[10]['p_loser'], 2)} by bar 10. At bar 3 roughly one flagged name in "
      f"three still ends a winner ({tell3[3]['n_hit']} flagged, "
      f"{_f(100 * (1 - (tell3[3]['p_loser'] or 0)), 0)}% of them winners) — and every "
      "one of those is a winner the rule forfeits.")
    A("4. **What does separate from zero: the plain hard stop.** "
      + (f"On CSI300 excess, {', '.join(f'`{k}`' for k in separating)} "
         f"{'have' if len(separating) != 1 else 'has'} a date-blocked CI excluding 0"
         if separating else "NO policy has an excess CI excluding 0")
      + (f"; on absolute P&L so do {', '.join(f'`{k}`' for k in sep_pnl)}. "
         if sep_pnl else ". ")
      + f"Best uncensored challenger `{best_mean}` ({lab[best_mean]}): "
        f"{_sgn(d[best_mean]['mean_delta_pp'], 2)} pp mean excess "
        f"[{_f(d[best_mean]['lo_pp'], 3)}, {_f(d[best_mean]['hi_pp'], 3)}]. "
      + (f"`S8` clears zero by {_f(d['S8']['lo_pp'], 3)} pp — a hair, and the overlap "
         "caveat below is larger than that margin." if d["S8"]["separates"] else ""))
    A(f"5. **On the operator's cut-losers-not-winners criterion the STOP family wins and "
      f"the REVIEW family loses.** `{best_ratio}` improves "
      f"{c[best_ratio]['losers']['n_improved']} of the audit's {c['P0_n_losers']} losers "
      f"for {c[best_ratio]['winners']['n_degraded']} of its {c['P0_n_winners']} winners "
      f"degraded ({_f(c[best_ratio]['improved_per_winner_degraded'])}:1); "
      f"`{d3_best}` manages {c[d3_best]['losers']['n_improved']} for "
      f"{c[d3_best]['winners']['n_degraded']} "
      f"({_f(c[d3_best]['improved_per_winner_degraded'])}:1).")
    A(f"6. **Not one CUT rule improved a single incumbent WINNER** (0 of "
      f"{c['P0_n_winners']}, all nine review/stop rules; the extension family is the "
      "only one that ever helps a winner). A winner that was under water at the review "
      "or stop bar is by construction a recovery, and exiting into the hole always "
      "realized less than holding did. The winner column is pure cost — there is no "
      "upside leg to trade off against it.")
    A(f"7. **Tail damage is the one place the stops clearly earn.** Incumbent MAE-p10 "
      f"{_f(base['mae_p10_pct'])}%; `{best_mae}` cuts it to "
      f"{_f(m[best_mae]['mae_p10_pct'])}% ({_sgn(d[best_mae]['mae_p10_pct_delta'])} pp). "
      "If the objective is surviving the fat left tail rather than maximising the "
      "median, that is the trade on offer.")
    A(f"8. **A-share execution eats part of it, and part of it is unexecutable.** Pooling "
      f"the {len(stop_over)} stop-carrying rules ({stop_n} resting-stop exits in total, "
      f"the same episode counted once per rule, {stop_noop} of them no-ops on bar {H}), "
      f"a stop filled a weighted mean {_f(stop_mean)} pp BELOW its own trigger level "
      f"(worst single fill {_f(stop_worst)} pp), and {stop_lim} of those exits fired on "
      "a session already at the daily price limit — where a seller could not reliably "
      "transact at any price. Read every stop delta above as an UPPER bound on what the "
      "rule would have realized.")
    A(f"9. **The winners-run half is CENSORED, not measured.** Only "
      f"{res['provenance']['n_with_21_bars']}/{res['provenance']['matured']} episodes "
      f"have {H_EXT} forward bars in the committed caches, so "
      f"{m['EXT']['n_censored']} of `EXT`'s "
      f"{m['EXT']['exit_reasons'].get(R_EXT_HORIZON, 0) + m['EXT']['n_censored']} "
      f"extended rows are MARKED at {res['provenance']['price_data_last_session']}, not "
      "realized. `EXT` and `R3x3_EXT` are position reports, never returns, and they are "
      "excluded from the \"best challenger\" line above for exactly that reason.")
    A(f"10. **Epistemic status: hypothesis generator, nothing more.** In-sample, ONE era "
      f"of {res['provenance']['graded_board_days']} entry dates on a FALLING tape "
      f"(CSI300's forward window negative on {res['regime']['n_negative']}/"
      f"{res['regime']['n_dates']}), {len(chal)} rules in {len(FAMILY_SIZE)} families "
      f"with NO multiplicity correction, and only "
      f"{res['overlap']['max_disjoint_windows']} pairwise-disjoint windows behind "
      f"{res['overlap']['n_board_days']} nominal blocks — so every CI here is too "
      "narrow. It can motivate a pre-registration; it cannot change the track record, "
      "the board, or any weight, and no rule shipped from this file.")
    A("")

    A("## What this is / what it is not")
    A("")
    A("Two different jobs, two instruments, never one blended number "
      "(`research/PROPHET_LEARNING_LOOP_MASTERPLAN_BY_FABLE.md` §1):")
    A("")
    A("1. **The track record measures SIGNAL QUALITY** — comparable, forced-verdict, "
      "fixed-H episodes, policy-free so eras and desks compare. The incumbent's 68.6% "
      "is a statement about the BOARD, not about a trading plan, and it stays the "
      "public headline.")
    A("2. **This study measures TRADE MANAGEMENT** — on IDENTICAL entries, what a "
      "holder-with-rules captures. \"Cut losers short / let winners run\" is tested "
      "here and only here.")
    A("3. **Longer-term pick quality enters selection only through evidence** — the "
      "horizon ladder plus postmortem cohorts feed candidate features into the "
      "promotion pipeline, never directly into live weights.")
    A("")
    A("Conflating the two would be the single most misleading number this program could "
      "print: an exit policy's win rate is not the board's win rate, and improving the "
      "former says nothing about the latter. Every verdict below is DESCRIPTIVE — "
      "\"shows\", \"in this sample\". No promotion, no recommendation, no weight change.")
    A("")

    A("## P0 gate — the cohort reproduces the shipped prior record")
    A("")
    g = res["p0_gate"]
    A("Asserted BEFORE any policy number is computed; the study raises and writes "
      "nothing on drift.")
    A("")
    A("| Gate | Reproduced | Shipped |")
    A("|---|---|---|")
    A(f"| matured episodes | {g['n_matured']} | {g['expected']['n_matured']} |")
    A(f"| win rate (excess > 0) | {g['win_rate']} | {g['expected']['win_rate']} |")
    A(f"| losers | {g['n_losers']} | {g['expected']['n_losers']} |")
    A(f"| median excess | {_f(g['median_excess_pct'])}% | "
      f"{_f(g['expected']['median_excess_pct'])}% |")
    A("")
    p = res["provenance"]
    A(f"Frame: {p['board_rows']} `legacy` board rows over {p['board_days']} board days → "
      f"{p['episodes']} contiguous-run episodes → {p['matured']} matured on "
      f"{p['graded_board_days']} entry dates. Exclusions (all by data coverage, fill "
      f"legality, or age — none can know which way a trade went): "
      + ", ".join(f"`{k}` {v}" for k, v in p["exclusions"].items()) + ".")
    A("")

    A("## Method pins")
    A("")
    A(f"- **Bar numbering.** `include_fill_bar=True`, so forward **bar 1 IS the fill "
      f"bar's own close** (the fill is the T+1 open/(H+L)/2 proxy, so that session's "
      f"close is a legitimate day-one exit). `held == {H}` exits on bar {H}. "
      f"\"Close of forward session k\" means `prices[k-1]`.")
    A("- **The loser audit's `first3` is bar 4 here**, not bar 3 — it indexes position 3 "
      "of an 11-bar array whose position 0 is the fill bar. The review families are run "
      "at the bar they name, and the conditional-loser table below is printed for EVERY "
      "bar so the choice of review bar is grounded rather than inherited.")
    A("- **Triggers are ABSOLUTE marks from fill; outcomes are scored in CSI300 EXCESS.** "
      "A rule must be executable without knowing the index; the CN headline metric is "
      "relative because in A-shares beta dominates. A rule can therefore cut an absolute "
      "loss that was not an excess loss, and the excess column prices that.")
    A("- **Exits are CLOSE-ONLY.** A rule reads the close of session k and exits AT that "
      "close. No walker touches an intraday low. Conservative in one direction (never "
      "fires on a session that pierced and recovered), optimistic in another (assumes "
      "the close is transactable — see the A-share section).")
    A("- **Same-bar ordering.** The hard stop is tested before the scheduled review. On "
      "the one bar where both can fire the review level is the looser of the two, so "
      "both resolve at the same close; the pin makes the exit REASON deterministic.")
    A("- **Every trigger is INCLUSIVE** — a review fires on `mark <= −X`, a stop on "
      "`mark <= −Y`, the extension arms on `mark >= +5`. These are levels a desk would "
      "publish, and trading at a published level is trading through the thesis, so a "
      "touch counts. A WIN stays the ledger's strict `> 0` with no dead band, so a "
      "\"loser\" is `excess <= 0` — the same cut that produces the audit's 128.")
    A("- **MAE/MFE are measured over the policy's OWN held window** (`prices[:held]`), "
      "for every row including the incumbent's. The incumbent never exits early, so its "
      "window is the full 10 bars and its MAE equals the grader's.")
    A("- **MAE/MFE are CLOSE-PATH** (the caches carry no intraday path for the walk), so "
      "both UNDERSTATE the true excursion.")
    A("")

    A("## Headline — every policy on the same 407 episodes, scored in CSI300 excess")
    A("")
    A("| Policy | win% | median | mean | PF | avg win | avg loss | MAE p10 | med hold | "
      "mean hold | abs win% | abs median | censored |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for k in keys:
        r = m[k]
        A(f"| `{k}` {lab[k]} | {_f(r['win_pct'], 1)} | {_f(r['median_pct'])} | "
          f"{_f(r['expectancy_pct'])} | {_f(r['profit_factor'])} | "
          f"{_f(r['avg_win_pct'])} | {_f(r['avg_loss_pct'])} | "
          f"{_f(r.get('mae_p10_pct'))} | {_f(r['median_hold'], 0)} | "
          f"{_f(r['mean_hold'], 1)} | "
          f"{_f(r['pnl_win_pct'], 1)} | {_f(r['pnl_median_pct'])} | "
          + (f"**{r['n_censored']}**" if r["n_censored"] else "0") + " |")
    A("")
    A("All percentage columns are points. `win%`/`median`/`mean`/`PF`/`avg win`/`avg "
      "loss` are CSI300 excess; `abs win%`/`abs median` are absolute P&L. `MAE p10` is "
      "the 10th percentile of maximum adverse excursion over the policy's held window "
      "(more negative = fatter left tail). `censored` counts rows MARKED at the last "
      "available close rather than exited — any non-zero entry means that row is a "
      "position report, not a return.")
    A("")
    A("MEDIAN hold is 10 for every policy because no rule fires on more than half the "
      "cohort; the MEAN hold column is where the rules are visible. Read the median-hold "
      "column as \"the typical episode is untouched\", not as \"the rule does nothing\".")
    A("")

    A("## Delta vs the incumbent")
    A("")
    A("| Policy | Δ win% | Δ median | Δ PF | Δ avg loss | Δ MAE p10 | Δ mean hold | "
      "Δ mean excess, paired (95% blocked CI) |")
    A("|---|---|---|---|---|---|---|---|")
    for k in chal:
        dd = d[k]
        # Bounds print at 3dp: `S8`'s lower bound is +0.004, and a 2dp "[0.00, …]"
        # beside a bolded "excludes 0" reads as a contradiction instead of as the
        # hair's-breadth result it actually is.
        ci = (f"{_sgn(dd['mean_delta_pp'], 2)} pp "
              f"[{_f(dd['lo_pp'], 3)}, {_f(dd['hi_pp'], 3)}]"
              + ("  **excludes 0**" if dd["separates"] else ""))
        A(f"| `{k}` | {_sgn(dd['win_pct_delta'], 1)} | {_sgn(dd['median_pct_delta'])} | "
          f"{_sgn(dd['profit_factor_delta'])} | "
          f"{_sgn(dd['avg_loss_pct_delta'])} | {_sgn(dd['mae_p10_pct_delta'])} | "
          f"{_sgn(dd['mean_hold_delta'], 1)} | {ci} |")
    A("")
    A("The last column IS the mean-excess delta — mean of per-episode differences equals "
      "difference of means, and all 407 episodes carry an excess under every policy, so "
      "there is one number and it is printed once, unrounded until display. (A separate "
      "\"Δ mean\" column computed from the two 2-dp headline means would differ from it "
      "in the third decimal purely by double rounding; that column is deliberately not "
      "shown, and the identity is asserted in code.)")
    A("")
    A("Paired = the SAME entry on the SAME date in both legs, so the difference isolates "
      "the exit rule and removes the entry cohort's variance. The CI resamples whole "
      "board days. A bolded \"excludes 0\" is a WEAKER statement than it looks — see the "
      "overlap section.")
    A("")

    A("## Cut the losers, don't cut the winners (the operator's criterion, priced)")
    A("")
    A(f"Partitioned on how the INCUMBENT called each episode: {c['P0_n_losers']} losers, "
      f"{c['P0_n_winners']} winners. \"Improved\" = the policy's excess is strictly "
      "higher than the incumbent's on that episode; \"flipped\" = it crossed the 0 line.")
    A("")
    A("| Policy | losers improved | losers flipped to win | winners degraded | "
      "winners flipped to loss | improved / degraded | net on losers half | "
      "net on winners half |")
    A("|---|---|---|---|---|---|---|---|")
    for k in chal:
        cc = c[k]
        A(f"| `{k}` | {cc['losers']['n_improved']}/{cc['losers']['n']} | "
          f"{cc['losers']['n_flipped_sign']} | "
          f"{cc['winners']['n_degraded']}/{cc['winners']['n']} | "
          f"{cc['winners']['n_flipped_sign']} | "
          f"{_f(cc['improved_per_winner_degraded'])} | "
          f"{_sgn(cc['losers_cut_net_pp'])} pp | "
          f"{_sgn(cc['winners_forfeited_net_pp'])} pp |")
    A("")
    A("The two net columns sum to the paired mean delta by construction (asserted in "
      "code); each is `sum(delta over that half) / 407`, so they are contributions to "
      "the overall mean, not within-half averages. Signs are literal — a POSITIVE "
      "winners-half number means the policy helped winners on net (only the extension "
      "family does). A policy whose left column is large and whose right column is near "
      "zero is doing the job the operator asked for; a policy that buys its mean by "
      "hurting more winners than it saves losers is buying it in the wrong currency.")
    A("")
    cut_only = [k for k in chal
                if k not in ("EXT",) and not any(p["extend_to_bar"] for p in res["policies"]
                                                 if p["key"] == k)]
    n_cut_improved = sum(c[k]["winners"]["n_improved"] for k in cut_only)
    A(f"**The winners column has no upside leg.** Across all {len(cut_only)} CUT rules, "
      f"exactly {n_cut_improved} of "
      f"{c['P0_n_winners']} incumbent winners was improved by exiting early — every "
      "winner a cut rule touched, it hurt. The mechanism is visible in the pairing: an "
      "episode that ends an EXCESS winner despite being under water at the review bar is "
      "by construction a recovery, i.e. it out-ran CSI300 from the review bar to bar 10, "
      "so selling into the hole realized less than holding. This is a MEASURED property "
      "of this cohort, not an identity — but it means the winner-forfeiture column is "
      "pure cost with nothing to net it against.")
    A("")

    A("## When the tell actually appears (grounding the review bar)")
    A("")
    A("P(this episode ends an incumbent LOSER | its mark at bar k is at or below the "
      "threshold), over all 407 matured episodes.")
    A("")
    for th_key, rows in res["tell_by_bar"].items():
        A(f"**Threshold: mark ≤ −{th_key.split('_')[-1].replace('pct', '')}%**")
        A("")
        A("| bar | n hit | % of cohort | P(loser) | median final excess | "
          "median final abs P&L |")
        A("|---|---|---|---|---|---|")
        for r in rows:
            A(f"| {r['bar']} | {r['n_hit']} | {_f(r['hit_pct_of_cohort'], 1)} | "
              f"{_f(r['p_loser'], 3)} | {_f(r['median_final_excess_pct'])} | "
              f"{_f(r['median_final_pnl_pct'])} |")
        A("")
    A(f"Base rate for reference: {c['P0_n_losers']}/{res['provenance']['matured']} = "
      f"{_f(100.0 * c['P0_n_losers'] / res['provenance']['matured'], 1)}% of episodes "
      "end losers.")
    A("")
    A("**This is why the review families fail, and it is the study's most transferable "
      "finding.** The loser audit's early-mark tell is REAL — a name marked at ≤ −3% is "
      f"a {_f(tell3[3]['p_loser'], 2)} loser against a "
      f"{_f(100.0 * c['P0_n_losers'] / res['provenance']['matured'] / 100.0, 2)} base "
      "rate — but it does not SHARPEN at bar 3. It is already there at bar 1 "
      f"({_f(tell3[1]['p_loser'], 2)}) and only becomes decisive around bars 8–10 "
      f"({_f(tell3[8]['p_loser'], 2)}, {_f(tell3[9]['p_loser'], 2)}, "
      f"{_f(tell3[10]['p_loser'], 2)}) — by which point the forced verdict has already "
      "arrived and there is nothing left to cut. A conditional loser rate near 0.7 means "
      "~30% of everything the rule fires on is a winner, and the winners column above "
      "shows that all of those are forfeited outright. A DEPTH threshold does better "
      "than a DATE threshold precisely because it waits for a bigger move rather than a "
      "later calendar bar — which is exactly what the hard-stop family is.")
    A("")

    A("## A-share execution reality (the close-only convention, costed)")
    A("")
    A("`exit_mark − trigger_level` is the same arithmetic for both trigger kinds and it "
      "does NOT mean the same thing, so it is reported SPLIT, never pooled:")
    A("")
    A("- **resting stop** (`hard_stop`) — the level sits in the market on every bar. A "
      "real order fills near it intraday; this study fills at the close, which is by "
      "construction at or through it. **This gap is the execution cost of the close-only "
      "convention** and it is a LOWER bound (no queue model, and a real stop would "
      "additionally fire on sessions this study holds through).")
    A("- **scheduled review** (`review`) — the threshold is read ONCE, at a scheduled "
      "bar. Nothing was resting; the position is simply already deeper than the trigger "
      "when the calendar reaches the review. **That is a property of the cohort, not an "
      "execution cost** — reading it as slippage would roughly double the review "
      "families' apparent penalty.")
    A("")
    A("| Policy | trigger kind | n | of which no-op on bar 10 | mean | median | p10 | "
      "worst | ≤ −2pp | bar at daily limit |")
    A("|---|---|---|---|---|---|---|---|---|---|")
    for k in keys:
        for kind, o in (m[k].get("trigger_overshoot") or {}).items():
            A(f"| `{k}` | {kind} | {o['n']} | {o['n_noop_at_horizon_bar']} | "
              f"{_f(o['mean_pp'])} | "
              f"{_f(o['median_pp'])} | {_f(o['p10_pp'])} | {_f(o['worst_pp'])} | "
              f"{o['n_worse_than_2pp']} | {o['n_bar_at_daily_limit']} |")
    A("")
    A("All figures in points of entry; negative = past the trigger. A trigger bar \"at "
      "the daily limit\" is a session whose own move was at or through the board's price "
      "limit (±10% main board, ±20% STAR/ChiNext) — a seller could not reliably transact "
      "there at any price, so those exits are priced at a level nobody could have hit.")
    A("")
    A(f"**Not every trigger is a trade.** A resting stop is in the market on EVERY bar "
      f"including bar {H}, and a trigger there exits at the SAME close the forced verdict "
      f"would have — the rule fired, the position is identical to the incumbent's, and "
      f"the paired delta is exactly 0. The `no-op on bar {H}` column separates those out, "
      "so a stop's trigger count is never read as its trade count (e.g. `S10` fires "
      f"{m['S10']['n_triggered']} times but only "
      f"{m['S10']['n_triggered'] - m['S10']['n_trigger_noop_at_horizon_bar']} of those "
      "changed anything). Scheduled reviews sit at bars 3 and 5 and cannot be no-ops.")
    A("")
    A(f"Separately, exactly {base['n_exit_bar_locked']} exit in the cohort lands on a "
      "LOCKED bar (`high == low == close` — the session never traded away from its "
      f"limit), and it does so under EVERY policy including the incumbent, because it is "
      "a plain horizon exit. That is a property of the tape, not of any rule.")
    A("")

    A("## Censoring (the extension family only)")
    A("")
    A(f"The review and stop families resolve inside the 10-bar forced-verdict window, so "
      f"they are uncensored by construction. The extension family holds to bar {H_EXT}, "
      f"and only {p['n_with_21_bars']}/{p['matured']} episodes have {H_EXT} forward bars "
      f"in the committed caches (last session "
      f"{p['price_data_last_session']}; forward-bar availability "
      f"{p['n_avail_min']}…{p['n_avail_max']}, median {p['n_avail_median']}).")
    A("")
    A("| Policy | extended rows | of which MARKED at data end | censored % of cohort |")
    A("|---|---|---|---|")
    for k in chal:
        r = m[k]
        n_ext = (r["exit_reasons"].get(R_EXT_HORIZON, 0)
                 + r["exit_reasons"].get(R_EXT_DATA_END, 0))
        if not n_ext:
            continue
        A(f"| `{k}` | {n_ext} | {r['n_censored']} | {_f(r['censored_pct'], 1)} |")
    A("")
    A("Censored rows are NOT dropped — dropping them would delete exactly the positions "
      "still running, which is the outcome-conditioned denominator `track_scoring`'s "
      "rule 1 forbids. They are marked at the last available close and flagged. A "
      "data_end row is a MARK, not a realized exit, and its hold length is a LOWER "
      "BOUND. Read those rows as \"what the rule was holding on "
      f"{p['price_data_last_session']}\", never as \"what the rule returned\".")
    A("")

    A("## Regime — the tape this was measured on")
    A("")
    A(f"CSI300's own 10-session forward window from each graded entry date: negative on "
      f"**{res['regime']['n_negative']} of {res['regime']['n_dates']}** dates, median "
      f"{_f(res['regime']['median_pct'])}% (range {_f(res['regime']['min_pct'])}% … "
      f"{_f(res['regime']['max_pct'])}%).")
    A("")
    A("| board date | CSI300 fwd-10 |")
    A("|---|---|")
    for r in res["regime"]["by_board_date"]:
        A(f"| {r['board_date']} | {_f(r['csi300_fwd10_pct'])}% |")
    A("")
    A("An exit rule that cuts losses is FLATTERED by a falling tape almost by "
      "construction. This is the single largest reason to treat the deltas above as "
      "in-sample only.")
    A("")
    A("Convention note: this column is the loser audit's own `csi300_fwd10` "
      "(`bench[T+1 … T+11]`), kept byte-comparable so the two documents cross-reference. "
      "It spans ONE session more than the benchmark leg inside `excess`, which runs "
      "fill bar → exit bar (bars 1…10). Do not reconcile the two arithmetically.")
    A("")

    A("## Limitations (read before citing any number above)")
    A("")
    A(f"1. **In-sample, one era, one regime.** {p['graded_board_days']} graded entry "
      f"dates, {res['regime']['n_negative']}/{res['regime']['n_dates']} with a negative "
      "index window. No out-of-sample period exists for this closed book — the era ENDED "
      "when the board definition changed on 2026-07-30.")
    A(f"2. **No multiplicity correction.** {len(chal)} challengers across "
      + ", ".join(f"{fam} ({n})" for fam, n in sorted(FAMILY_SIZE.items()))
      + ". Thresholds were chosen from the loser audit's own descriptive statistics on "
        "THIS cohort, so the search is not independent of the sample either.")
    A(f"3. **The blocks overlap and the CI does not know it.** "
      f"{res['overlap']['n_board_days']} board days, neighbour-window overlap median "
      f"{_f(res['overlap']['overlap_median_pct'], 1)}% "
      f"(max {_f(res['overlap']['overlap_max_pct'], 1)}%), "
      f"{res['overlap']['n_neighbour_pairs_over_50']} of "
      f"{res['overlap']['n_board_days'] - 1} neighbour pairs sharing ≥50% of their "
      f"window, {res['overlap']['union_sessions']} distinct sessions covering "
      f"{res['overlap']['total_window_bars']} window bars, and only "
      f"**{res['overlap']['max_disjoint_windows']} pairwise-disjoint windows** in the "
      "whole sample. Every interval printed is too narrow and a bolded \"excludes 0\" is "
      "a weaker statement than it looks. No correction is applied — it would need a "
      "covariance model this sample cannot support.")
    A("4. **Close-only exits + A-share price limits.** The resting-stop overshoot is a "
      "LOWER bound on the convention's cost (no queue model), a real stop would also "
      "fire intraday on sessions this study holds through, and limit-day exits are "
      "priced at a level nobody could have transacted. The scheduled-review overshoot "
      "is NOT an execution cost and must not be added to it.")
    A("5. **The extension family is censored** — see above. Its rows are position "
      "reports, not returns.")
    A("6. **Absolute triggers, relative scoring.** The rules fire on absolute marks and "
      "are scored in CSI300 excess. In a falling tape an absolute stop cuts positions "
      "that were beating the index; that cost is IN the excess columns, but it means the "
      "same rule would behave differently under a flat or rising index.")
    A("7. **No promotion path is opened by this file.** Any rule that eventually "
      "displaces the incumbent needs its own pre-registration, shadow accrual, and "
      "out-of-sample window first. The track record's headline stays the fixed-horizon "
      "forced verdict.")
    A("")
    A("Instrument: `research/cn_prophet_audit/cn_exit_policy_study.py` · raw results "
      "`research/cn_prophet_audit/cn_exit_policy_results.json` · cohort forensics "
      "`research/cn_prophet_audit/RESULTS_2026-08-04.md` · doctrine "
      "`research/PROPHET_LEARNING_LOOP_MASTERPLAN_BY_FABLE.md` §1 · US sibling "
      "`scripts/exit_policy_study.py`.")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
DUMP_FIELDS = ("ticker", "board_date", "entry_date", "exit_date", "held",
               "exit_reason", "pnl", "excess", "mae", "mfe", "slip_pp",
               "exit_bar_locked", "exit_bar_at_limit", "censored")


def dump_rows(policies: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict:
    """Per-episode tables for downstream reuse, stored as incumbent + CHANGED-ONLY.

    Storing all twelve policies in full is 4,884 rows of which most are byte-identical
    copies of the incumbent — a rule that never fires on an episode leaves that episode
    exactly where the forced verdict left it. So the incumbent ships whole and each
    challenger ships only the episodes it TOUCHED, keyed by (ticker, board_date). An
    omitted episode is defined to equal the P0 row, and that definition is ASSERTED here
    rather than trusted: if a supposedly-untouched row ever differs from P0 in any dumped
    field, the study raises instead of silently shipping a lossy artifact.

    Floats round to 4dp ON DUMP ONLY — every statistic in the report is computed at full
    precision first. 4dp on a percent is 1e-4 pp, far finer than this sample resolves,
    and it keeps the committed artifact a readable diff.
    """
    def strip(r: Mapping[str, Any]) -> dict:
        return {k: (_r(r[k], 4) if isinstance(r[k], float) else r[k]) for k in DUMP_FIELDS}

    base = {(r["ticker"], r["board_date"]): r for r in policies["P0"]}
    out: dict[str, Any] = {"_note": ("P0 is complete; each challenger lists only the "
                                     "episodes whose exit differs from the incumbent's "
                                     "forced verdict. An omitted (ticker, board_date) "
                                     "equals the P0 row exactly — asserted at write "
                                     "time."),
                           "P0": [strip(r) for r in policies["P0"]]}
    for k, rows in policies.items():
        if k == "P0":
            continue
        changed, unchanged = [], 0
        for r in rows:
            b = base[(r["ticker"], r["board_date"])]
            if r["exit_reason"] == R_HORIZON and int(r["held"]) == H:
                assert strip(r) == strip(b), (
                    f"{k}: {r['ticker']} {r['board_date']} was treated as untouched but "
                    "differs from the incumbent row")
                unchanged += 1
            else:
                changed.append(strip(r))
        out[k] = {"n_total": len(rows), "n_unchanged_equal_to_P0": unchanged,
                  "changed": changed}
    return out


DELTA_FIELDS = ("win_pct", "median_pct", "expectancy_pct", "profit_factor",
                "avg_win_pct", "avg_loss_pct", "median_hold", "mean_hold",
                "mae_p10_pct", "mae_median_pct", "mfe_median_pct", "capture",
                "pnl_win_pct", "pnl_median_pct", "pnl_expectancy_pct")


def run_study() -> dict:
    cohort, prov = build_cohort()
    gate = assert_p0(cohort)                       # HARD GATE — before any policy number

    bench = cst._bench_close()  # noqa: SLF001
    policies = evaluate(cohort, bench)
    base_rows = policies["P0"]

    # The study's own incumbent walk must agree with the grader's verdict episode-for-
    # episode, or "same 407 episodes, same fills" is not true of the challenger rows.
    for a, b in zip(base_rows, cohort):
        assert a["held"] == H, "incumbent walk must exit on bar H"
        assert abs(float(a["pnl"]) - float(b["p0_pnl"])) < 1e-9, "incumbent pnl drift"
        assert abs(float(a["excess"]) - float(b["p0_excess"])) < 1e-9, (
            "incumbent excess drift vs track_scoring")

    metrics = {k: policy_metrics(rows) for k, rows in policies.items()}
    base_m = metrics["P0"]
    deltas: dict[str, dict] = {}
    cuts: dict[str, Any] = {"P0_n_losers": gate["n_losers"],
                            "P0_n_winners": gate["n_matured"] - gate["n_losers"]}
    for k, rows in policies.items():
        if k == "P0":
            continue
        dd = paired_delta(rows, base_rows, "excess")
        dd["paired_delta_pnl"] = paired_delta(rows, base_rows, "pnl")
        for f in DELTA_FIELDS:
            a, b = metrics[k].get(f), base_m.get(f)
            dd[f"{f}_delta"] = (_r(float(a) - float(b), 3)
                                if a is not None and b is not None else None)
        # ``expectancy_pct_delta`` and ``mean_delta_pp`` are THE SAME QUANTITY (mean of
        # differences == difference of means) and the report must never print two values
        # for it. They can only diverge if a row carries an excess in one leg and not the
        # other, so the pairing count is asserted against both summaries; the numeric
        # check then allows only the double-rounding gap (``summarize`` rounds expectancy
        # to 2dp before the subtraction). The REPORT prints the exact paired figure and
        # drops the rounded one — see ``render_md``.
        assert dd["n"] == metrics[k]["n_matured"] == base_m["n_matured"], (
            f"{k}: paired n {dd['n']} != summary n "
            f"{metrics[k]['n_matured']}/{base_m['n_matured']} — the mean-excess delta "
            "and the paired mean delta are no longer the same quantity")
        assert abs((dd["expectancy_pct_delta"] or 0.0)
                   - (dd["mean_delta_pp"] or 0.0)) <= 0.011, (
            f"{k}: rounded mean delta {dd['expectancy_pct_delta']} diverges from exact "
            f"paired mean {dd['mean_delta_pp']} by more than display rounding")
        deltas[k] = dd
        cc = cut_vs_forfeit(rows, base_rows, "excess")
        # The halves must add up to the paired mean, or the decomposition is an advert.
        halves = (cc["losers"]["net_contribution_pp"] or 0.0) + (
            cc["winners_forfeited_net_pp"] or 0.0)
        assert abs(halves - (dd["mean_delta_pp"] or 0.0)) < 5e-3, (
            f"{k}: decomposition halves {halves} != mean delta {dd['mean_delta_pp']}")
        # For a pure CUT rule the set of unchanged episodes must be exactly {never
        # triggered} U {triggered on bar H, where the exit IS the forced verdict's}. If
        # that identity ever breaks, either the walker moved an exit it should not have
        # or a "no-op" trigger is quietly changing the P&L.
        pol = next(p for p in POLICIES if p.key == k)
        if not pol.extend:
            unchanged = cc["losers"]["n_unchanged"] + cc["winners"]["n_unchanged"]
            expect = (len(rows) - metrics[k]["n_triggered"]
                      + metrics[k]["n_trigger_noop_at_horizon_bar"])
            assert unchanged == expect, (
                f"{k}: {unchanged} unchanged rows != {expect} "
                "(untriggered + bar-H no-ops)")
        cuts[k] = cc

    return {
        "as_of": AS_OF,
        "definition": f"cn_standout_v1 (board_definition='{DEF}')",
        "horizon": H,
        "extension_horizon": H_EXT,
        "family_sizes": dict(sorted(FAMILY_SIZE.items())),
        "p0_gate": gate,
        "provenance": prov,
        "policies": [p.as_dict() for p in POLICIES],
        "metrics": metrics,
        "deltas": deltas,
        "cut_vs_forfeit": cuts,
        "tell_by_bar": tell_by_bar(cohort, base_rows),
        "overlap": window_overlap(cohort, bench),
        "regime": regime(cohort, bench),
        "rows": dump_rows(policies),
    }


def main() -> None:
    res = run_study()
    OUT_JSON.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
    OUT_MD.write_text(render_md(res))
    g = res["p0_gate"]
    print(f"P0 GATE PASSED — matured={g['n_matured']} win={g['win_rate']} "
          f"losers={g['n_losers']} median_excess={g['median_excess_pct']}")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    base = res["metrics"]["P0"]
    print(f"{'policy':10s} {'win%':>6s} {'median':>7s} {'mean':>7s} {'PF':>5s} "
          f"{'MAEp10':>7s} {'Δmean':>7s} {'lo':>7s} {'hi':>7s}")
    for p in res["policies"]:
        k = p["key"]
        m = res["metrics"][k]
        d = res["deltas"].get(k, {})
        print(f"{k:10s} {m['win_pct']:6.1f} {m['median_pct']:7.2f} "
              f"{m['expectancy_pct']:7.2f} "
              f"{(m['profit_factor'] if m['profit_factor'] is not None else float('nan')):5.2f} "
              f"{m['mae_p10_pct']:7.2f} "
              f"{(d.get('mean_delta_pp') or 0.0):7.2f} "
              f"{(d.get('lo_pp') if d.get('lo_pp') is not None else 0.0):7.2f} "
              f"{(d.get('hi_pp') if d.get('hi_pp') is not None else 0.0):7.2f}"
              + ("" if k != "P0" else "   <- incumbent"))
    print(f"incumbent: win {base['win_pct']}% median {base['median_pct']} "
          f"mean {base['expectancy_pct']} over {base['n_board_days']} board days")


if __name__ == "__main__":
    main()
