#!/usr/bin/env python3
"""onset_fillability_restatement_v1.py — CN LIMIT-MOVE ALPHA, Wave 3 / lane W3-C.

THE ONE QUESTION
    Wave 1 shipped two halves of one arithmetic and never joined them.

    Lane L3 (onset calibration) proved that the onset probabilities are REAL and ORDERED:
    AUC 0.775 against the ladder's 0.592, and a top-K daily book whose head realizes ~17%
    against a 1.2% base — a 14x lift.  Every one of those numbers is a probability of a
    limit-up CLOSE at T+1.

    Lane L1 (continuation rider) then proved that a close is not a fill: 46.7% of realized
    main-board next-day boards open UNBUYABLE (一字 / locked at the open), rising to 75.0%
    at N>=3; locked exits roll at up to 9.98% frequency costing -2.14% mean and -20.96%
    worst; and every naive open-anchored rider loses.

    L1 paid that tax on the CONTINUATION side only.  The onset book never got the treatment.
    So the program's most impressive published table — L3's top-K daily book — is still
    quoted at paper prices.  This file states it at fillable ones.

    PRIMARY: for each of L3's selection objects and each per-date top-K book, what fraction
    of the paper edge survives open-anchored implementability?  Every paper number is
    printed BESIDE its implementable twin.  The pairing is the product.

HONEST PRIOR, WRITTEN BEFORE THE FIRST NUMBER
    This is a measurement COMPLETION, not an edge hunt.  The expected outcome is that the
    edge concentrates in the picks you cannot buy — that the model's best names are exactly
    the 一字 opens the auction already took.  That null, cleanly measured, IS the deliverable:
    it is the honest "what could you actually buy" curve the product needs in place of a
    paper hit rate.  Nothing here is expected to be net-positive, and nothing here is
    reframed if it is not.

TIER
    Display / audit.  MEASUREMENT ONLY.  Nothing here promotes, ranks for size, gates,
    admits, or reaches a live surface.  No LLM is involved at any point.  Under the ORE LAW
    the null is printed, never buried, and the ORE LEDGER states what was NOT tested.

BINDING CONVENTIONS — INHERITED BY IMPORT, NOT RE-DECIDED
    The panel, the exclusions, the PRIMARY limit-up definition, the tolerant cushion, the
    no-board-pooling rule, the ChiNext 2020-08-24 era restriction, the fit/calib/holdout
    boundaries, the THIN gates, the five selection objects and the top-K tie rule all come
    from onset_calibration_v1.py BY IMPORT.  The fillability censor, the 一字 test, the three
    exit families, the locked-exit roll and the round-trip cost come from
    continuation_rider_v1.py BY IMPORT.  This file adds exactly four things: the join between
    them, a second (ex-ante) pick universe, the censoring taxonomy, and the corruption control.

    The exit walker cannot be imported — L1 defines it inside a closure — so it is restated
    here and PINNED: STAGE 9's L1 parity gate re-runs continuation_rider_v1.process_ticker on
    a deterministic 1-in-8 ticker sample and requires trade-for-trade agreement.  A
    reimplementation that drifted would fail that gate rather than quietly disagree.

PRE-REGISTRATION (frozen before the first number was read; see PREREG below and the receipt)

  POPULATION.  L3's panel and L3's frozen splits, verbatim.  Boards admitted exactly where
  L3 admits them (fit-core positives >= 150).  ChiNext is never pooled across 2020-08-24.

  TWO PICK UNIVERSES, both pre-registered, answering different questions:
    U1_y_ok    — L3's own rows (live & complete-case & USABLE NEXT BAR).  The paper column
                 here reproduces L3's published top-K table cell for cell; that reproduction
                 is a gate (STAGE 9).  This is the PRIMARY universe for the pairing.
    U2_ex_ante — live & complete-case, WITHOUT the y_ok filter.  L3's own JSON flags that
                 conditioning on next-bar usability is a filter a desk at T's close cannot
                 apply.  U2 is that filter removed, and it is the only universe in which the
                 SUSPENDED / no-bar censoring category can exist at all.  Picks with no
                 usable next bar are reported as censored, never scored 0 and never scored 1.

  BOOKS.  Per (universe, board, window, ranker, K), per feature-date: rank by P-hat
  descending, ties by ticker ascending (L3's rule, load-bearing for B0's four distinct
  values), take the top K.
    rankers  B0, B1, B2, P1, P2   (L3's five; the brief named B0/B1/B2/P2 and L3 published
                                   B1/B0/P1/B2 — carrying all five costs nothing and makes
                                   both lists a subset)
    K        1, 3, 5, 10, 20, 50  (10/20/50 are L3's published set, so the paper column is
                                   checkable; 1/3/5 are desk-realistic book sizes, and the
                                   fillability question bites hardest at the head of a book)
    windows  fit (in-sample, labelled as such) and holdout (out-of-sample).  L3 published
             the holdout only; a survivor claim needs both, so both are run.

  FILLABILITY CENSOR — L1's, unchanged.  A pick is FILLABLE iff its T+1 bar is usable
  (L1's pair rule) and open[T+1] < limit_price[T+1] * (1 - 0.002).  Unfillable opens are
  REFUSED, never modelled as fills.

  EXITS — L1's E1 / E2 / E3 with the locked-exit roll, unchanged.  ONE disclosed change to
  the STEP rule, pre-registered: the exit walk is CLOSURE-TOLERANT.  W3-A measured that
  reusing v0's 10-calendar-day pair rule as a forward-chain step rule truncates every open
  window market-wide at a CNY / National-Day closure and force-closes it at a
  mark-to-market close (+11.03% on the truncated ChiNext tail — an illusion).  The ENTRY
  pair rule stays v0's 10 days, because it defines the population L3 and L1 both measured;
  only the walk past an entry tolerates a closure.  Both step rules are run and printed
  (the strict one is what the L1 parity gate compares against).

  COMPLETE-WINDOW BOOKS.  A trade whose exit was still forced (store edge, 30-session hold
  cap, roll cap exhausted) is counted in its own block and EXCLUDED from every headline.

  THE PAIRING.  For every cell:
    paper_rate  = P(limit-up close at T+1 | picked)                     <- L3's number
    impl_rate   = P(limit-up close at T+1 | picked AND fillable open)   <- L1's censor
    paper_book  = every pick filled at the T+1 open REGARDLESS of fillability (the fiction a
                  naive backtest of L3's book would print; a 一字 pick is "bought" at the
                  limit), exits as above
    impl_book   = fillable picks only, exits as above
  Survival is reported as a RATIO only where the paper number is positive; where the paper
  number is negative or straddles zero the difference in percentage points is the statement.
  Paper and implementable are never blended.

  SECONDARY (a) — does model confidence correlate with unfillability?  Fillable share by
  P-hat decile and by top-K bucket, per board, Wilson on every rate, against the date-wide
  market baseline.  Hypothesis under test: the model's best picks are exactly the 一字 opens.

  SECONDARY (b) — the survivor book.  Fillable-only top-K: net mean/median, per-trade AND
  date-clustered t, era (yearly) table.  Is ANY implementable onset book net-positive in
  BOTH fit and holdout?

  SECONDARY (c) — censoring composition among non-fillable picks: 一字 / limit-at-open (not
  一字) / suspended (name missed sessions) / exchange closure / excluded bar / store edge,
  per era, per board.

  CORRUPTION CONTROL.  Fillability flags are permuted WITHIN (universe, board, window, date)
  across every candidate row, frozen seed, then every book is re-derived.  This preserves
  each session's market-wide fillable share and destroys only the association between P-hat
  rank and fillability.  PRE-REGISTERED EXPECTATION: the paper-vs-implementable gap collapses
  to ~0 and the survivor book degrades toward the unconditional book.  If it does not, the
  gap is a coding artifact and the finding is void.

  STATISTICS.  Wilson 95% on every rate.  Date-clustered t beside per-trade stats on every
  return cell — never the per-trade t alone.  Yearly era tables.  THIN at n < 20.  Boards
  never pooled.

Run from repo root:  TZ=UTC python3 research/cn_prophet_audit/onset_fillability_restatement_v1.py
Outputs (frozen, committed):
    research/cn_prophet_audit/ONSET_FILLABILITY_RESTATEMENT_V1_2026-08-09.json
    research/cn_prophet_audit/ONSET_FILLABILITY_RESTATEMENT_V1_2026-08-09.md  (mirrors JSON)
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ["TZ"] = "UTC"
try:
    time.tzset()
except AttributeError:  # pragma: no cover - non-POSIX
    pass

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DATA = REPO / "data"
OUT_DIR = REPO / "research" / "cn_prophet_audit"
OUT_JSON = OUT_DIR / "ONSET_FILLABILITY_RESTATEMENT_V1_2026-08-09.json"

ONSET_PY = OUT_DIR / "onset_calibration_v1.py"
RIDER_PY = OUT_DIR / "continuation_rider_v1.py"

_MISSING = (
    "MISSING WAVE-1 DEPENDENCY: {path}\n"
    "This lane JOINS two Wave-1 artifacts and deliberately does not vendor copies of them.\n"
    "Fetch them from their authoring branches:\n"
    "  git fetch origin claude/cn-limit-w1-onset claude/cn-limit-w1-rider "
    "claude/cn-limit-w1-dataheal\n"
    "  git show origin/claude/cn-limit-w1-onset:"
    "research/cn_prophet_audit/onset_calibration_v1.py"
    " > research/cn_prophet_audit/onset_calibration_v1.py\n"
    "  git show origin/claude/cn-limit-w1-rider:"
    "research/cn_prophet_audit/continuation_rider_v1.py"
    " > research/cn_prophet_audit/continuation_rider_v1.py\n"
    "  git show origin/claude/cn-limit-w1-dataheal:"
    "data/china_microstructure/limit_events.parquet"
    " > data/china_microstructure/limit_events.parquet\n"
    "  git show origin/claude/cn-limit-w1-dataheal:"
    "data/china_microstructure/limit_tape.parquet"
    " > data/china_microstructure/limit_tape.parquet\n"
    "  git show origin/claude/cn-limit-w1-dataheal:data/china_zt_pool/pool.parquet"
    " > data/china_zt_pool/pool.parquet\n"
    "(or simply run this after those Wave-1 PRs have merged to main)."
)

for _p in (ONSET_PY, RIDER_PY):
    if not _p.exists():
        raise SystemExit(_MISSING.format(path=_p))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # safe: both siblings guard main() on __main__
    return mod


onset = _load("onset_calibration_v1", ONSET_PY)
rider = _load("continuation_rider_v1", RIDER_PY)

from engine.china_microstructure import _board_from_ticker  # noqa: E402

# ── inherited constants (never redefined locally) ─────────────────────────────

LIMIT_CLOSE_TOL = onset.LIMIT_CLOSE_TOL          # 0.002 — v0's adjudicated cushion
MAX_PAIR_GAP_DAYS = onset.MAX_PAIR_GAP_DAYS      # 10 calendar days, ENTRY pair rule
THIN_CELL_N = onset.THIN_CELL_N                  # 20
MIN_FIT_CORE_POS = onset.MIN_FIT_CORE_POS        # 150 — L3's board-admission floor
MIN_CALIB_POS = onset.MIN_CALIB_POS              # 50
MIN_HOLDOUT_POS = onset.MIN_HOLDOUT_POS          # 100
DESIGN_COLS = onset.DESIGN_COLS
N_DUMMIES = onset.N_DUMMIES

TIME_STOP_SESSIONS = rider.TIME_STOP_SESSIONS    # 3  -> E3 exits at the open of T+4
MAX_HOLD_SESSIONS = rider.MAX_HOLD_SESSIONS      # 30
ROLL_CAP_SESSIONS = rider.ROLL_CAP_SESSIONS      # 10
ROUND_TRIP_COST = rider.ROUND_TRIP_COST          # 0.0015 (15 bp)
EXIT_RULES = tuple(sorted(rider.EXIT_RULES))     # E1_board_fail, E2_first_down_close, E3_...

# ── frozen parameters (this file's, pre-registered before the first run) ──────

RANKERS = ("B0", "B1", "B2", "P1", "P2")
TOP_K = (1, 3, 5, 10, 20, 50)
WINDOWS = ("fit", "holdout")
UNIVERSES = ("U1_y_ok", "U2_ex_ante")
PRIMARY_UNIVERSE = "U1_y_ok"
HEADLINE_RANKERS = ("B1", "B2")        # era tables are cut for these two only
HEADLINE_K = 10                        # L3's smallest published K
P_DECILES = 10
CORRUPTION_SEED = 20260809
CLOSURE_TOLERANT_PRIMARY = True
PARITY_TICKER_STRIDE = 8               # L1 trade-parity gate: deterministic 1-in-8 sample

# Store vintage — stamped so a post-expansion re-run is comparable (masterplan §9).
VINTAGE = {
    "curated_universe_names": 1842,
    "healed_limit_events": 71463,
    "raw_store": "data/china_stocks_raw (BACK-ADJUSTED, per L1's price-basis audit)",
    "heal_branch": "claude/cn-limit-w1-dataheal",
    "note": ("Every number here is calibrated ON and FOR the curated 1,842-name era.  The "
             "Codex lane's expansion to the full ~5,400-name universe (ST + delisted) will "
             "move the denominators; falsifier F3 hangs over this receipt as it does over "
             "every Wave-1/2 artifact."),
}

# The censoring taxonomy.  Order IS the integer code stored in `censor_cat`.
#
# "Suspended" needed care.  This store does NOT drop a 停牌 session — it carries a
# ZERO-VOLUME PLACEHOLDER bar (133,781 of them in window), which v0's exclusion cascade then
# marks not-live.  A taxonomy that only looked for MISSING bars would therefore have printed
# "suspensions: 0" while a hundred thousand suspension bars sat in the store under another
# name.  Codes 3-7 unpick v0's cascade so each non-fillable pick names its own cause.
CENSOR_CATS = (
    "fillable",
    "unfillable_yizi_strict",
    "unfillable_limit_open_not_yizi",
    "no_entry_suspended_zero_volume",
    "no_entry_exdiv_suspect",
    "no_entry_ipo_window",
    "no_entry_bad_prev_close",
    "no_entry_exchange_closure",
    "no_entry_long_gap_with_missed_sessions",
    "no_entry_store_edge",
)
CENSOR_CODE = {c: i for i, c in enumerate(CENSOR_CATS)}

PREREG = {
    "decided_before_the_first_number": [
        "the honest prior is a NULL: the edge is expected to concentrate in unfillable "
        "picks, and that null cleanly measured is the deliverable",
        "L3's panel, splits, board-admission gate and five selection objects are IMPORTED, "
        "never re-derived or re-tuned",
        "L1's fillability censor, 一字 test, three exit families, locked-exit roll and 15 bp "
        "round trip are IMPORTED, never re-specified",
        f"rankers {list(RANKERS)}; K {list(TOP_K)}; windows {list(WINDOWS)}; "
        f"universes {list(UNIVERSES)} — all fixed before the first book was built",
        "every paper number is printed beside its implementable twin; the two are never "
        "blended and no cell is reported alone",
        "survival is a RATIO only where the paper number is positive; otherwise the pp "
        "difference is the statement (a ratio across zero is meaningless)",
        "the exit walk is closure-tolerant and the ENTRY pair rule is not; both step rules "
        "are run and printed",
        "complete-window books only in every headline; forced/truncated trades are counted "
        "in their own block",
        "date-clustered t beside per-trade stats on every return cell",
        f"THIN at n < {THIN_CELL_N}; L3's {MIN_FIT_CORE_POS} fit-core-positive board floor "
        "inherited and never lowered",
        "the corruption control and its expected outcome were written before it was run",
    ],
    "what_would_falsify_the_finding": (
        "The paper-vs-implementable gap is claimed to be the fillability censor doing real "
        "work.  The corruption control is its falsifier: permuting fillability within a "
        "session must collapse the gap toward zero.  A gap that survives the permutation is "
        "a coding artifact and the finding is void."
    ),
}


# ── small helpers (Wilson / rounding / JSON are L1's, imported) ───────────────

wilson = rider.wilson
jsonable = rider.jsonable
_r = rider._r


def rate_block(k: int, n: int) -> dict:
    """Binomial rate with Wilson 95% and a THIN flag.  L1's, restated for local clarity."""
    ci = wilson(int(k), int(n))
    return {
        "n": int(n), "k": int(k),
        "rate_pct": _r(100.0 * k / n, 4) if n else None,
        "wilson95_pct": [_r(100.0 * ci[0], 4), _r(100.0 * ci[1], 4)] if ci else None,
        "thin": bool(n < THIN_CELL_N),
    }


def ret_block(rets: np.ndarray, dates: np.ndarray | None = None,
              names: np.ndarray | None = None) -> dict:
    """Per-trade distribution.  NOT an inference block — see date_clustered()."""
    x = np.asarray(rets, dtype="float64")
    fin = np.isfinite(x)
    x = x[fin]
    n = int(x.size)
    if n == 0:
        return {"n": 0, "thin": True}
    net = (1.0 + x) * (1.0 - ROUND_TRIP_COST) - 1.0
    wins = int((x > 0).sum())
    ci = wilson(wins, n)
    out = {
        "n": n,
        "win_rate_pct": _r(100.0 * wins / n),
        "win_wilson95_pct": [_r(100.0 * ci[0]), _r(100.0 * ci[1])] if ci else None,
        "mean_gross_pct": _r(100.0 * float(x.mean()), 3),
        "mean_net_pct": _r(100.0 * float(net.mean()), 3),
        "median_net_pct": _r(100.0 * float(np.median(net)), 3),
        "p10_net_pct": _r(100.0 * float(np.percentile(net, 10)), 3),
        "p90_net_pct": _r(100.0 * float(np.percentile(net, 90)), 3),
        "worst_net_pct": _r(100.0 * float(net.min()), 3),
        "best_net_pct": _r(100.0 * float(net.max()), 3),
        "per_trade_t": None,
        "thin": bool(n < THIN_CELL_N),
    }
    if n > 1:
        sd = float(net.std(ddof=1))
        out["per_trade_t"] = _r(float(net.mean()) / (sd / np.sqrt(n)), 2) if sd > 0 else None
    if names is not None and len(names) == len(fin):
        vc = pd.Series(np.asarray(names)[fin]).value_counts()
        out["n_names"] = int(vc.size)
        out["top5_name_share_pct"] = _r(100.0 * float(vc.head(5).sum()) / n)
    if dates is not None and len(dates) == len(fin):
        out["n_dates"] = int(pd.Series(np.asarray(dates)[fin]).nunique())
    return out


def date_clustered(rets: np.ndarray, dates: np.ndarray) -> dict:
    """Date-clustered net expectancy — W2-B's / W3-A's function, copied.

    Trades are not independent: a theme wave puts dozens of names on one session behind one
    market-wide open.  Collapsing each date to its own mean net return first makes the
    reported t count SESSIONS.  The point estimate changes meaning deliberately:
    date-equal weighting is what a book that cannot take unlimited same-day positions earns.
    """
    x = np.asarray(rets, dtype="float64")
    fin = np.isfinite(x)
    x = x[fin]
    if x.size == 0:
        return {"n_dates": 0}
    net = (1.0 + x) * (1.0 - ROUND_TRIP_COST) - 1.0
    dm = pd.Series(net).groupby(np.asarray(dates)[fin]).mean().to_numpy()
    k = int(dm.size)
    out = {"n_dates": k, "date_eq_weight_net_pct": _r(100.0 * float(dm.mean()), 3),
           "trades_per_date": _r(float(x.size) / k, 2)}
    if k > 1:
        se = float(dm.std(ddof=1)) / np.sqrt(k)
        out["date_clustered_se_pct"] = _r(100.0 * se, 3)
        out["date_clustered_t"] = _r(float(dm.mean()) / se, 2) if se > 0 else None
    return out


def book_block(rets: np.ndarray, dates: np.ndarray,
               names: np.ndarray | None = None) -> dict:
    """The only return block this file emits: per-trade stats AND the clustered t together."""
    b = ret_block(rets, dates=dates, names=names)
    b.update(date_clustered(rets, dates))
    return b


def survival(paper: float | None, impl: float | None) -> dict:
    """Paper -> implementable survival.  Ratio ONLY where paper is positive."""
    if paper is None or impl is None:
        return {"delta_pp": None, "survival_ratio": None,
                "ratio_suppressed": "a paper or implementable value is missing"}
    d = {"delta_pp": _r(impl - paper, 3), "survival_ratio": None}
    if paper > 0:
        d["survival_ratio"] = _r(impl / paper, 3)
    else:
        d["ratio_suppressed"] = ("paper value is <= 0 — a survival ratio across zero is "
                                 "meaningless; read delta_pp")
    return d


# ── STAGE 1 — fillability of EVERY panel row (vectorised, one store pass) ─────

def _shift_next(a, fill):
    return np.r_[a[1:], fill]


def exclusion_causes(df: pd.DataFrame, A: dict, board: str) -> dict:
    """Re-derive v0's exclusion CASCADE per bar so a censored pick can name its cause.

    _ticker_arrays returns only the union (`live`) and aggregate counts, so a pick whose T+1
    bar is not live can otherwise be reported no more precisely than "excluded".  The cascade
    below is v0's, in v0's order, and the per-ticker counts it produces are pinned against
    _ticker_arrays' own excl_stats — a drift here would silently mislabel suspensions.
    """
    idx = pd.to_datetime(df.sort_index().index)
    vol = df.sort_index()["volume"].to_numpy(dtype=np.float64)
    o, pc, width, n = A["o"], A["pc"], A["width"], A["n"]

    excl = np.zeros(n, dtype=bool)
    ipo_window = 0
    if board in ("star", "chinext"):
        ipo_window = rider.CHINEXT_STAR_IPO_WINDOW
    elif idx.min() < rider.IPO_PRE2014_DATE:
        ipo_window = rider.PRE2014_IPO_WINDOW
    ipo = np.zeros(n, dtype=bool)
    if ipo_window:
        ipo[:ipo_window] = True
        excl |= ipo
    bad_pc = (~np.isfinite(pc) | (pc <= 0)) & ~excl
    excl |= bad_pc
    with np.errstate(invalid="ignore", divide="ignore"):
        open_move = np.abs(o - pc) / pc
    exdiv = np.isfinite(open_move) & (open_move > width * 1.5) & ~excl
    excl |= exdiv
    zero_vol = np.isfinite(vol) & (vol <= 0) & ~excl
    return {"ipo": ipo, "bad_pc": bad_pc, "exdiv": exdiv, "zero_vol": zero_vol}


def store_pass(panel: pd.DataFrame,
               market_days: np.ndarray) -> tuple[pd.DataFrame, dict, dict]:
    """One pass over data/china_stocks_raw: per-bar fillability + a cached walk kernel.

    Returns (fill_frame, cache, meta).  fill_frame is keyed (ticker, date) over every bar
    and carries L1's censor verbatim.  cache holds only the six arrays the exit walk needs,
    so the walk never re-reads a parquet.

    The suspension/closure split is the reason the market calendar is threaded through here:
    a >10-day gap with ZERO market sessions in between is an exchange closure (CNY /
    National Day), while a gap that skipped real sessions is the NAME being suspended.  L1
    could not make that distinction because its population was already conditioned on a
    usable next bar; U2 can, and it is the only place the word "suspended" is earned.
    """
    st_set, st_note = onset.load_st_cohort()
    files = sorted((DATA / "china_stocks_raw").glob("*.parquet"))
    want = set(panel["ticker"].unique())

    frames, cache, bridged, unclassified = [], {}, 0, 0
    cause_tally = {"ipo": 0, "exdiv": 0, "zero_vol": 0}
    excl_stats_tally = {"ipo": 0, "exdiv": 0, "zero_vol": 0}
    counts = {"tickers_read": 0, "tickers_skipped_st": 0, "tickers_unreadable": 0}
    for p in files:
        ticker = p.stem
        if ticker in st_set:
            counts["tickers_skipped_st"] += 1
            continue
        if ticker not in want:
            continue
        try:
            df = pd.read_parquet(p)
        except Exception:  # noqa: BLE001
            counts["tickers_unreadable"] += 1
            continue
        board = _board_from_ticker(ticker)
        A = rider._ticker_arrays(df, board)
        if A is None:
            counts["tickers_unreadable"] += 1
            continue
        counts["tickers_read"] += 1

        n = A["n"]
        o, h, lo, c = A["o"], A["h"], A["lo"], A["c"]
        live, lu, days = A["live"], A["lu"], A["days"]
        lim_up, lim_dn = A["lim_up"], A["lim_dn"]

        nxt_o = _shift_next(o, np.nan)
        nxt_h = _shift_next(h, np.nan)
        nxt_lo = _shift_next(lo, np.nan)
        nxt_c = _shift_next(c, np.nan)
        nxt_live = _shift_next(live, False)
        nxt_lu = _shift_next(lu, False)
        nxt_lim_up = _shift_next(lim_up, np.nan)
        nxt_days = _shift_next(days, np.iinfo(np.int64).max)

        has_next = np.r_[np.ones(n - 1, dtype=bool), False] if n else np.zeros(0, dtype=bool)
        gap_days = np.where(has_next, nxt_days - days, np.iinfo(np.int64).max)
        pair_ok = has_next & (gap_days <= MAX_PAIR_GAP_DAYS)
        y_ok = pair_ok & nxt_live

        # sessions the MARKET held strictly between this bar and the ticker's next bar
        left = np.searchsorted(market_days, days, side="right")
        right = np.searchsorted(market_days, np.where(has_next, nxt_days, days), side="left")
        missed_sessions = np.where(has_next, np.maximum(right - left, 0), 0)

        with np.errstate(invalid="ignore"):
            unfill = y_ok & np.isfinite(nxt_o) & np.isfinite(nxt_lim_up) & (
                nxt_o >= nxt_lim_up * (1.0 - LIMIT_CLOSE_TOL))
            yizi = unfill & nxt_lu & np.isfinite(nxt_lo) & (nxt_o == nxt_h) \
                & (nxt_o == nxt_lo) & (nxt_o == nxt_c)
        fillable = y_ok & ~unfill

        cause = exclusion_causes(df, A, board)
        for k, sk in (("ipo", "ipo_excluded"), ("exdiv", "exdiv_excluded"),
                      ("zero_vol", "zero_volume_excluded")):
            cause_tally[k] += int((cause[k] & A["in_win"]).sum())
            excl_stats_tally[k] += int(A["excl_stats"][sk])
        # v0's four exclusion masks are disjoint by construction (each is computed against
        # the running union), so `blocked` matches exactly one and the np.where order below
        # carries no hidden precedence.
        C = CENSOR_CODE
        blocked = has_next & pair_ok & ~nxt_live
        cat = np.full(n, C["no_entry_store_edge"], dtype=np.int8)
        cat = np.where(has_next & ~pair_ok & (missed_sessions == 0),
                       C["no_entry_exchange_closure"], cat)
        cat = np.where(has_next & ~pair_ok & (missed_sessions > 0),
                       C["no_entry_long_gap_with_missed_sessions"], cat)
        cat = np.where(blocked & _shift_next(cause["bad_pc"], False),
                       C["no_entry_bad_prev_close"], cat)
        cat = np.where(blocked & _shift_next(cause["zero_vol"], False),
                       C["no_entry_suspended_zero_volume"], cat)
        cat = np.where(blocked & _shift_next(cause["exdiv"], False),
                       C["no_entry_exdiv_suspect"], cat)
        cat = np.where(blocked & _shift_next(cause["ipo"], False),
                       C["no_entry_ipo_window"], cat)
        cat = np.where(unfill & ~yizi, C["unfillable_limit_open_not_yizi"], cat)
        cat = np.where(yizi, C["unfillable_yizi_strict"], cat)
        cat = np.where(fillable, C["fillable"], cat)
        # In-window only: every pre-window bar's successor is non-live by definition, so an
        # unmasked count here would read 1.6M and mean nothing.
        unclassified += int((blocked & (cat == C["no_entry_store_edge"])
                             & A["in_win"]).sum())

        keep = A["in_win"]
        bridged += int((y_ok & (missed_sessions > 0) & keep).sum())
        frames.append(pd.DataFrame({
            "ticker": ticker,
            "date": pd.DatetimeIndex(A["idx"][keep]).astype("datetime64[ns]"),
            "y_ok_chk": y_ok[keep],
            "fillable": fillable[keep],
            "unfillable": unfill[keep],
            "yizi_strict": yizi[keep],
            "censor_cat": cat[keep],
        }))
        cache[ticker] = {
            "days": days.astype(np.int64),
            "o": o, "c": c, "lim_dn": lim_dn,
            "lu": lu.astype(bool), "live": live.astype(bool), "n": n,
        }

    fill = pd.concat(frames, ignore_index=True)
    counts["st_cohort"] = st_note
    counts["rows"] = len(fill)
    counts["short_suspensions_bridged_by_the_10d_pair_rule"] = bridged
    counts["bridged_note"] = (
        "v0's pair rule accepts a successor bar up to 10 calendar days out, so a SHORT "
        "suspension is silently bridged and the 'next bar' can be days later.  Counted here "
        "because it is a real property of every number L1, L3 and this file publish.")
    counts["exclusion_cause_pin"] = {
        "rederived": cause_tally,
        "ticker_arrays_excl_stats": excl_stats_tally,
        "pass": bool(cause_tally == excl_stats_tally),
        "what_it_pins": ("the re-derived exclusion cascade against _ticker_arrays' own "
                         "counts — a drift here would mislabel suspensions as something else"),
    }
    counts["blocked_bars_unclassified"] = unclassified
    return fill, cache, {"store_pass": counts, "cache_tickers": len(cache)}


# ── STAGE 2 — the exit walker (L1's, restated; pinned by STAGE 9's parity gate) ─

def _usable_next(i: int, K: dict, closure_tolerant: bool) -> int:
    j = i + 1
    if j >= K["n"]:
        return -1
    if not bool(K["live"][j]):
        return -1
    if not closure_tolerant and K["days"][j] - K["days"][i] > MAX_PAIR_GAP_DAYS:
        return -1
    return j


def _resolve_exit(b_sched: int, fallback_bar: int, K: dict, closure_tolerant: bool):
    """L1's locked-exit roll: a scheduled open at/below limit-down cannot be sold."""
    o, c, lim_dn = K["o"], K["c"], K["lim_dn"]
    if b_sched < 0:
        return float(c[fallback_bar]), fallback_bar, 0, True, np.nan
    sched_open = float(o[b_sched])
    rolls = 0
    b = b_sched
    while bool(np.isfinite(lim_dn[b])) and o[b] <= lim_dn[b] * (1.0 + LIMIT_CLOSE_TOL):
        if rolls >= ROLL_CAP_SESSIONS:
            return float(c[b]), b, rolls, True, sched_open
        nb = _usable_next(b, K, closure_tolerant)
        rolls += 1
        if nb < 0:
            return float(c[b]), b, rolls, True, sched_open
        b = nb
    return float(o[b]), b, rolls, False, sched_open


def walk_trades(K: dict, t: int, closure_tolerant: bool) -> dict:
    """Every exit family for ONE entry: buy at the open of bar t+1.  L1's arithmetic."""
    o, c, lu = K["o"], K["c"], K["lu"]
    e = t + 1
    entry_px = float(o[e])
    out = {}
    if not np.isfinite(entry_px) or entry_px <= 0:
        return out
    for rule in EXIT_RULES:
        forced_walk = False
        if rule == "E3_time_stop_T4":
            cur, ok_walk = e, True
            for _ in range(TIME_STOP_SESSIONS):
                nb = _usable_next(cur, K, closure_tolerant)
                if nb < 0:
                    ok_walk = False
                    break
                cur = nb
            b_sched = cur if ok_walk else -1
            fallback = cur
        else:
            cur, steps = e, 0
            while True:
                cont = bool(lu[cur]) if rule == "E1_board_fail" else bool(c[cur] >= o[cur])
                if not cont:
                    break
                nb = _usable_next(cur, K, closure_tolerant)
                if nb < 0 or steps >= MAX_HOLD_SESSIONS:
                    forced_walk = True
                    break
                cur = nb
                steps += 1
            b_sched = -1 if forced_walk else _usable_next(cur, K, closure_tolerant)
            fallback = cur
        px, b_exit, rolls, forced, sched_open = _resolve_exit(
            b_sched, fallback, K, closure_tolerant)
        extra = (px / sched_open - 1.0) if (rolls > 0 and np.isfinite(sched_open)
                                            and sched_open > 0) else np.nan
        out[rule] = {
            "ret": px / entry_px - 1.0,
            "hold": int(b_exit - e),
            "rolls": int(rolls),
            "complete": not (forced or forced_walk),
            "roll_cost": extra,
        }
    return out


def price_picks(pairs: pd.DataFrame, cache: dict, closure_tolerant: bool) -> pd.DataFrame:
    """Price every unique (ticker, date) entry once.  Returns one row per (pair, rule)."""
    cols = ["ticker", "date", "rule", "ret", "hold", "rolls", "complete", "roll_cost"]
    rows = []
    for ticker, g in pairs.groupby("ticker", sort=True):
        K = cache.get(ticker)
        if K is None:
            continue
        dts = np.sort(g["date"].unique())
        dnum = dts.astype("datetime64[D]").astype(np.int64)
        pos = np.searchsorted(K["days"], dnum)
        for d, dn, i in zip(dts, dnum, pos):
            i = int(i)
            if i >= K["n"] or int(K["days"][i]) != int(dn) or i + 1 >= K["n"]:
                continue
            for rule, v in walk_trades(K, i, closure_tolerant).items():
                rows.append((ticker, d, rule, v["ret"], v["hold"], v["rolls"],
                             v["complete"], v["roll_cost"]))
    if not rows:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(rows, columns=cols)
    out["date"] = out["date"].astype("datetime64[ns]")
    return out


# ── STAGE 3 — books ───────────────────────────────────────────────────────────

def topk_frame(df: pd.DataFrame, preds: dict, kmax: int) -> pd.DataFrame:
    """Top-kmax picks per (ranker, feature-date) with a rank column.

    Nested by construction — top-1 is inside top-3 is inside top-50 — so one frame with a
    rank column serves every K and the pick set is built once.  Ties broken by ticker
    ascending: L3's rule, load-bearing for B0, which has four distinct values and therefore
    selects an essentially arbitrary K names from inside its top tie group.
    """
    dates = df["date"].to_numpy()
    tick = df["ticker"].to_numpy()
    order_date = np.argsort(dates, kind="stable")
    uniq, starts = np.unique(dates[order_date], return_index=True)
    bounds = list(starts) + [len(order_date)]

    parts = []
    for name in RANKERS:
        p = preds[name]
        rows, ranks = [], []
        for i in range(len(uniq)):
            idx = order_date[bounds[i]:bounds[i + 1]]
            if idx.size == 0:
                continue
            take = min(kmax, idx.size)
            ordr = np.lexsort((tick[idx], -p[idx]))[:take]
            pick = idx[ordr]
            rows.append(pick)
            ranks.append(np.arange(take, dtype=np.int16))
        if not rows:
            continue
        sel = np.concatenate(rows)
        part = pd.DataFrame({
            "ranker": name,
            "rank": np.concatenate(ranks),
            "row": sel.astype(np.int64),
            "p_hat": p[sel],
        })
        parts.append(part)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def attach(picks: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    src = df.reset_index(drop=True)
    take = src.iloc[picks["row"].to_numpy()]
    out = picks.copy()
    for col in ("date", "ticker", "year", "y_limit_up", "y_ok", "fillable", "unfillable",
                "yizi_strict", "censor_cat", "N_bucket"):
        out[col] = take[col].to_numpy()
    return out


def _cell_pairing(sub: pd.DataFrame, trades: dict, base_rate: float,
                  pos_per_date: pd.Series, fill_col: str = "fillable") -> dict:
    """The product: one book cell stated at paper prices AND at fillable ones."""
    n_pick = len(sub)
    graded = sub[sub["y_ok"]]
    n_graded = len(graded)
    fill_flag = sub[fill_col].to_numpy()
    n_fill = int(fill_flag.sum())

    paper_hits = int(graded["y_limit_up"].sum())
    fsub = sub[sub[fill_col]]
    impl_hits = int(fsub["y_limit_up"].sum())

    dates_used = int(sub["date"].nunique())
    pos_total = int(pos_per_date.reindex(sub["date"].unique()).fillna(0).sum())

    cell = {
        "picks": n_pick,
        "dates": dates_used,
        "picks_graded": n_graded,
        "picks_ungraded_censored": n_pick - n_graded,
        "entry_available_pct": _r(100.0 * n_fill / n_pick, 3) if n_pick else None,
        "paper": {
            "rate": rate_block(paper_hits, n_graded),
            "capture_share_pct": _r(100.0 * paper_hits / pos_total, 3) if pos_total else None,
            "lift_vs_base": _r((paper_hits / n_graded) / base_rate, 3)
            if (n_graded and base_rate > 0) else None,
            "mean_p_hat_pct": _r(100.0 * float(graded["p_hat"].mean()), 4) if n_graded
            else None,
        },
        "implementable": {
            "rate": rate_block(impl_hits, n_fill),
            "capture_share_pct": _r(100.0 * impl_hits / pos_total, 3) if pos_total else None,
            "lift_vs_base": _r((impl_hits / n_fill) / base_rate, 3)
            if (n_fill and base_rate > 0) else None,
            "mean_p_hat_pct": _r(100.0 * float(fsub["p_hat"].mean()), 4) if n_fill else None,
        },
        "positives_available": pos_total,
    }
    cell["survival_rate"] = survival(cell["paper"]["rate"]["rate_pct"],
                                     cell["implementable"]["rate"]["rate_pct"])
    cell["survival_capture"] = survival(cell["paper"]["capture_share_pct"],
                                        cell["implementable"]["capture_share_pct"])

    # ── the return axis, per exit family ──────────────────────────────────────
    books = {}
    key = pd.MultiIndex.from_arrays([sub["ticker"].to_numpy(), sub["date"].to_numpy()])
    for rule in EXIT_RULES:
        tr = trades[rule]
        hit = tr.reindex(key)
        ret = hit["ret"].to_numpy()
        complete = hit["complete"].to_numpy()
        complete = np.where(pd.isna(complete), False, complete).astype(bool)
        priced = np.isfinite(ret)
        dts = sub["date"].to_numpy()
        nms = sub["ticker"].to_numpy()

        m_paper = priced & complete
        m_impl = m_paper & fill_flag
        blk = {
            "paper": book_block(ret[m_paper], dts[m_paper], nms[m_paper]),
            "implementable": book_block(ret[m_impl], dts[m_impl], nms[m_impl]),
            "excluded_incomplete_windows": int((priced & ~complete).sum()),
            "unpriced_picks": int((~priced).sum()),
            "rolls_implementable": int(np.nansum(
                np.where(m_impl, hit["rolls"].to_numpy(), 0))),
        }
        blk["survival_mean_net"] = survival(blk["paper"].get("mean_net_pct"),
                                            blk["implementable"].get("mean_net_pct"))
        blk["survival_date_eq_net"] = survival(
            blk["paper"].get("date_eq_weight_net_pct"),
            blk["implementable"].get("date_eq_weight_net_pct"))
        books[rule] = blk
    cell["books"] = books
    return cell


# ── STAGE 4 — secondary (a): confidence vs unfillability ──────────────────────

def fillable_by_decile(df: pd.DataFrame, preds: dict) -> dict:
    """Fillable share by P-hat decile, per ranker.  The hypothesis test of secondary (a).

    Deciles are cut on the VALUES of P-hat so ties share a bucket (v0's correction): B0 has
    four distinct values and rank-binning it would manufacture ten 'deciles' out of four
    numbers.  Realised bucket counts are printed rather than assumed to be ten.

    AND, for a model with fewer distinct values than requested bins, its DISTINCT VALUES are
    the bins (L3's reliability() rule, reused).  Plain qcut collapses B0's ladder to a single
    bucket — 99% of its mass sits at the N=0 rate — which would report the benchmark as
    having no structure at all rather than reporting the four rungs it actually has.
    """
    out = {}
    fillable = df["fillable"].to_numpy()
    yok = df["y_ok"].to_numpy()
    yizi = df["yizi_strict"].to_numpy()
    for name in RANKERS:
        p = pd.Series(preds[name])
        if int(p.nunique()) <= P_DECILES:
            b = (p.rank(method="dense").astype(int) - 1)
        else:
            b = rider.value_quantile_bins(p, P_DECILES)
        if b is None:
            out[name] = {"status": "no bins — P-hat is constant"}
            continue
        b = b.reindex(range(len(df))).to_numpy()
        rows = []
        for q in sorted(set(x for x in b if pd.notna(x))):
            m = (b == q)
            rows.append({
                "decile": int(q),
                "n": int(m.sum()),
                "mean_p_hat_pct": _r(100.0 * float(p[m].mean()), 4),
                "fillable": rate_block(int(fillable[m].sum()), int(m.sum())),
                "yizi_strict_pct": _r(100.0 * float(yizi[m].mean()), 3),
                "usable_next_bar_pct": _r(100.0 * float(yok[m].mean()), 3),
            })
        rows.sort(key=lambda r: r["decile"])
        top, bot = (rows[-1], rows[0]) if len(rows) >= 2 else (None, None)
        out[name] = {
            "realised_bins": len(rows),
            "bins": rows,
            "top_vs_bottom_fillable_pp": (
                _r(top["fillable"]["rate_pct"] - bot["fillable"]["rate_pct"], 3)
                if top and bot else None),
            "reading": ("A NEGATIVE top-vs-bottom value is the hypothesis confirmed: the "
                        "model's most confident rows are the least buyable."),
        }
    return out


def fillable_by_k(picks: pd.DataFrame, market_fillable_pct: float | None) -> list[dict]:
    """Fillable share by top-K bucket per ranker, against the market-wide baseline."""
    rows = []
    for name in RANKERS:
        sel = picks[picks["ranker"] == name]
        for k in TOP_K:
            s = sel[sel["rank"] < k]
            if s.empty:
                continue
            rb = rate_block(int(s["fillable"].sum()), len(s))
            rows.append({
                "ranker": name, "K": k,
                "fillable": rb,
                "yizi_strict_pct": _r(100.0 * float(s["yizi_strict"].mean()), 3),
                "vs_market_pp": (_r(rb["rate_pct"] - market_fillable_pct, 3)
                                 if (rb["rate_pct"] is not None
                                     and market_fillable_pct is not None) else None),
            })
    return rows


# ── STAGE 5 — secondary (c): censoring composition per era ────────────────────

def censoring_composition(picks: pd.DataFrame) -> dict:
    """Among NON-fillable picks: why, per year.  The taxonomy is CENSOR_CATS."""
    bad = picks[~picks["fillable"]]
    per_year = []
    for yr, g in bad.groupby("year", observed=True):
        tot = len(g)
        row = {"year": int(yr), "unfillable_picks": tot}
        for i, cat in enumerate(CENSOR_CATS):
            if i == 0:
                continue
            row[cat + "_pct"] = _r(100.0 * float((g["censor_cat"] == i).mean()), 2)
        per_year.append(row)
    per_year.sort(key=lambda r: r["year"])
    overall = {}
    for i, cat in enumerate(CENSOR_CATS):
        n = int((picks["censor_cat"] == i).sum())
        overall[cat] = {"n": n, "pct_of_all_picks": _r(100.0 * n / max(1, len(picks)), 3)}
    return {"overall": overall, "by_year": per_year,
            "denominator": "picks whose T+1 open was NOT fillable"}


# ── STAGE 6 — era tables ──────────────────────────────────────────────────────

def era_table(sub: pd.DataFrame, trades: dict, rule: str) -> list[dict]:
    """Yearly paper-vs-implementable, on ONE exit family.  Mandatory under §0 gate 2."""
    rows = []
    tr = trades[rule]
    key = pd.MultiIndex.from_arrays([sub["ticker"].to_numpy(), sub["date"].to_numpy()])
    hit = tr.reindex(key)
    ret = hit["ret"].to_numpy()
    complete = np.where(pd.isna(hit["complete"].to_numpy()), False,
                        hit["complete"].to_numpy()).astype(bool)
    priced = np.isfinite(ret) & complete
    yrs = sub["year"].to_numpy()
    fl = sub["fillable"].to_numpy()
    yok = sub["y_ok"].to_numpy()
    yy = sub["y_limit_up"].to_numpy()
    dts = sub["date"].to_numpy()
    for yr in sorted(set(int(x) for x in yrs)):
        m = (yrs == yr)
        mg, mf = m & yok, m & fl
        pb, ib = m & priced, m & priced & fl
        rows.append({
            "year": yr,
            "picks": int(m.sum()),
            "fillable_pct": _r(100.0 * float(fl[m].mean()), 2) if m.sum() else None,
            "paper_rate": rate_block(int(yy[mg].sum()), int(mg.sum())),
            "implementable_rate": rate_block(int(yy[mf].sum()), int(mf.sum())),
            "paper_book": book_block(ret[pb], dts[pb]),
            "implementable_book": book_block(ret[ib], dts[ib]),
        })
    return rows


# ── STAGE 7 — the corruption control ──────────────────────────────────────────

def corrupt_fillability(df: pd.DataFrame, seed: int) -> np.ndarray:
    """Permute the fillability flag WITHIN each feature-date, frozen seed.

    Permuting within a session preserves that session's market-wide fillable share exactly
    (the 一字 intensity of the day is a real market fact and must survive) and destroys ONLY
    the association between P-hat rank and buyability.  Under the null that the censor is a
    coding artifact, every paired number must come back together.
    """
    rng = np.random.default_rng(seed)
    flag = df["fillable"].to_numpy().copy()
    out = flag.copy()
    dates = df["date"].to_numpy()
    order = np.argsort(dates, kind="stable")
    uniq, starts = np.unique(dates[order], return_index=True)
    bounds = list(starts) + [len(order)]
    for i in range(len(uniq)):
        idx = order[bounds[i]:bounds[i + 1]]
        if idx.size <= 1:
            continue
        out[idx] = flag[idx][rng.permutation(idx.size)]
    return out


# ── STAGE 8 — verification gates ──────────────────────────────────────────────

def l1_trade_parity(cache: dict) -> dict:
    """Re-run L1's own process_ticker on a 1-in-8 ticker sample and demand agreement.

    This is what makes the restated walker safe to use.  L1 defines its entry book inside a
    closure, so it cannot be imported; the alternative to a parity gate is a silent
    divergence in the one arithmetic this lane exists to apply.  Compared under L1's STRICT
    step rule (closure_tolerant=False), because that is the rule L1 published.
    """
    st_set, _ = onset.load_st_cohort()
    files = sorted((DATA / "china_stocks_raw").glob("*.parquet"))
    sample = [p for i, p in enumerate(files) if i % PARITY_TICKER_STRIDE == 0
              and p.stem not in st_set and p.stem in cache]
    n_cmp = 0
    max_abs = 0.0
    mismatched = 0
    missing = 0
    for p in sample:
        ticker = p.stem
        board = _board_from_ticker(ticker)
        A = rider._ticker_arrays(pd.read_parquet(p), board)
        if A is None:
            continue
        _, trades = rider.process_ticker(ticker, A, board)
        if not trades:
            continue
        K = cache[ticker]
        mine = {}
        for dt, _t, _b, _N, _bnd, rule, _epx, _px, ret, *_rest in trades:
            dn = int(pd.Timestamp(dt).to_datetime64().astype("datetime64[D]")
                     .astype(np.int64))
            i = int(np.searchsorted(K["days"], dn))
            if i >= K["n"] or int(K["days"][i]) != dn or i + 1 >= K["n"]:
                missing += 1
                continue
            if (ticker, dt) not in mine:
                mine[(ticker, dt)] = walk_trades(K, i, closure_tolerant=False)
            got = mine[(ticker, dt)].get(rule)
            if got is None:
                missing += 1
                continue
            n_cmp += 1
            d = abs(float(got["ret"]) - float(ret))
            max_abs = max(max_abs, d)
            if d > 1e-12:
                mismatched += 1
    return {
        "tickers_sampled": len(sample),
        "stride": PARITY_TICKER_STRIDE,
        "trades_compared": n_cmp,
        "trades_missing": missing,
        "trades_mismatched": mismatched,
        "max_abs_return_diff": float(max_abs),
        "pass": bool(n_cmp > 0 and mismatched == 0 and missing == 0),
        "what_it_pins": ("the restated exit walker against continuation_rider_v1's own "
                         "entry book, trade for trade, under L1's strict step rule"),
    }


L3_PUBLISHED_TOPK = {
    # board -> (ranker, K) -> (rows, hits, realized_pct)   [ONSET_CALIBRATION_V1 receipt]
    "main": {
        ("B1", 10): (11350, 1882, 16.581), ("B0", 10): (11350, 1912, 16.846),
        ("B2", 10): (11350, 2025, 17.841), ("P1", 10): (11350, 1491, 13.137),
        ("B1", 20): (22700, 2796, 12.317), ("B0", 20): (22700, 2532, 11.154),
        ("B2", 20): (22700, 2846, 12.537), ("P1", 20): (22700, 2319, 10.216),
        ("B1", 50): (56750, 4201, 7.403), ("B0", 50): (56750, 3118, 5.494),
        ("B2", 50): (56750, 4041, 7.121), ("P1", 50): (56750, 3822, 6.735),
    },
    "chinext": {
        ("B1", 10): (4330, 102, 2.356), ("B0", 10): (4330, 46, 1.062),
        ("B2", 10): (4330, 91, 2.102), ("P1", 10): (4330, 90, 2.079),
    },
}


def l3_topk_parity(board: str, cells: dict) -> dict:
    """The paper column must BE L3's published column, or this lane is reading another book."""
    want = L3_PUBLISHED_TOPK.get(board, {})
    checked, bad = [], 0
    for (ranker, K), (rows, hits, pct) in sorted(want.items()):
        got = cells.get(f"{ranker}|K{K}")
        if got is None:
            bad += 1
            checked.append({"ranker": ranker, "K": K, "status": "CELL ABSENT"})
            continue
        g_rows = got["paper"]["rate"]["n"]
        g_hits = got["paper"]["rate"]["k"]
        g_pct = got["paper"]["rate"]["rate_pct"]
        ok = (g_rows == rows and g_hits == hits and abs((g_pct or 0) - pct) <= 0.001)
        bad += 0 if ok else 1
        checked.append({"ranker": ranker, "K": K, "published": [rows, hits, pct],
                        "rederived": [g_rows, g_hits, g_pct], "match": bool(ok)})
    return {"cells_checked": len(checked), "mismatches": bad, "pass": bool(want and bad == 0),
            "detail": checked,
            "what_it_pins": ("the paper column against ONSET_CALIBRATION_V1's published "
                             "holdout top-K table, row for row")}


# ── ORE LEDGER ────────────────────────────────────────────────────────────────

ORE_LEDGER = {
    "law": ("A null on one construction NEVER closes a hypothesis.  What follows is what "
            "this lane did NOT test.  Nothing below is claimed dead."),
    "entry_constructions_untested": [
        "LIMIT-ORDER-AT-OPEN fills — this book takes the printed open or refuses.  A resting "
        "buy limit below the 一字 price is a different (worse-filled, sometimes filled) object.",
        "PARTIAL FILLS — every fill here is all-or-nothing at one price.  A 一字 board with a "
        "thin seal fills a fraction of a desk's size; that fraction is unmeasured and needs "
        "the auction-matched-volume feed (集合竞价成交, purchased 2026-08-09).",
        "AUCTION-PARTICIPATION entries — queueing INTO the 9:25 call auction rather than "
        "reading its result.  No history exists anywhere; collector P5 must start before "
        "this is answerable.",
        "INTRADAY FIRST-TOUCH entries — buying a name as it approaches the board rather than "
        "at the open.  Blocked on minute bars (purchased; not yet wired by the Codex lane).",
        "SEAL-BREAK (开板) re-entries on a pick whose T+1 opened locked and then unsealed — "
        "the fillable moment that daily bars cannot see but 首次封板时间 partly can.",
        "VWAP or first-N-minutes entries as a fill proxy for the unbuyable open.",
        "NEXT-DAY DEFERRAL — skipping an unfillable pick to T+2 rather than refusing it.",
    ],
    "exit_constructions_untested": [
        "L1's three exit families are the whole exit space here.  Trailing stops, "
        "limit-target exits, seal-stability exits and intraday stops are untested.",
        "The locked-exit roll cap is L1's 10 sessions; longer and shorter caps are untested.",
        "H > 1 onset horizons — this lane grades the SAME one-bar outcome L3 modelled.",
    ],
    "selection_constructions_untested": [
        "Regime conditioning of the BOOK (W2-A's R0/R2/R3 objects) — this lane restates L3's "
        "five objects only.  A regime-conditioned book may censor differently.",
        "FILLABILITY-AWARE RANKING — a ranker trained to predict P(board AND fillable) rather "
        "than P(board).  This lane measures the tax; it does not try to dodge it.",
        "Size-weighted or P-weighted books — every book here is equal-weight within a date.",
        "Books that spend the refused slot on the next-ranked fillable name (a REPLACEMENT "
        "book) rather than leaving it empty.",
    ],
    "population_untested": [
        "F3 — the full ~5,400-name universe including ST and delisted names.  Every number "
        "here is the curated 1,842-name slice; the censoring rate itself may be a curation "
        "artifact, since the omitted small-caps are where 一字 lives.",
        "STAR is THIN-SKIPPED by L3's board gate and is therefore unmeasured here, not null.",
        "The U2 ex-ante universe is measured for censoring but its books are secondary; a "
        "full ex-ante restatement of every L3 table is untested.",
    ],
}


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:  # noqa: C901 - one linear instrument, deliberately readable top-to-bottom
    t0 = time.time()
    stamped = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("[0] dependencies resolved: onset_calibration_v1, continuation_rider_v1",
          flush=True)

    panel, panel_meta = onset.build_panel()
    # One date dtype everywhere.  The raw store's index is datetime64[ms]; every join,
    # reindex and MultiIndex lookup below would silently miss on a ms/ns mismatch.
    panel["date"] = panel["date"].astype("datetime64[ns]")
    splits, _global_split = onset.make_splits(panel)
    print(f"[1] panel {len(panel):,} rows, split {splits['global']['split_date']} "
          f"({time.time() - t0:.0f}s)", flush=True)

    market_days = np.sort(
        panel.loc[panel["live"], "date"].unique()
    ).astype("datetime64[D]").astype(np.int64)

    fill, cache, store_meta = store_pass(panel, market_days)
    rows_before = len(panel)
    panel = panel.merge(fill, on=["ticker", "date"], how="left")
    unjoined = int(panel["censor_cat"].isna().sum())
    if len(panel) != rows_before or unjoined:
        raise SystemExit(
            f"FILLABILITY JOIN IS NOT 1:1 — {rows_before} panel rows -> {len(panel)} joined, "
            f"{unjoined} without a censor category.  A silently unjoined row would be scored "
            "as if it were unbuyable, which is the exact fiction this lane exists to remove.")
    panel["fillable"] = panel["fillable"].astype(bool)
    panel["unfillable"] = panel["unfillable"].astype(bool)
    panel["yizi_strict"] = panel["yizi_strict"].astype(bool)
    panel["censor_cat"] = panel["censor_cat"].astype(np.int8)
    yok_agree = bool((panel["y_ok"].to_numpy() == panel["y_ok_chk"].to_numpy()).all())
    print(f"[2] fillability joined ({time.time() - t0:.0f}s); y_ok agreement with L1's "
          f"arrays: {yok_agree}", flush=True)

    zt = DATA / "china_zt_pool" / "pool.parquet"
    coverage = {
        "curated_universe": panel_meta["tickers_kept"],
        "raw_store_files": panel_meta["files_found"],
        "st_cohort": panel_meta["st_cohort"],
        "sector_coverage_pct": panel_meta["sector_coverage_pct"],
        "complete_case_coverage": panel_meta["complete_case_coverage"],
        "caveat": (
            "THE BINDING COVERAGE FACT, inherited unchanged from v0: ~1,842 curated names "
            "against a listed A-share market of roughly 5,400, survivors-only, 1 ST name in "
            "100.  The 打板 game lives disproportionately in the small-caps this store omits, "
            "and 一字 lives disproportionately in exactly those names — so the censoring rates "
            "below are, if anything, the OPTIMISTIC end of the market's true tax."),
    }
    if zt.exists():
        ztn = set(pd.read_parquet(zt)["ticker"].astype(str))
        raw = {p.stem for p in sorted((DATA / "china_stocks_raw").glob("*.parquet"))}
        coverage["zt_pool_names"] = len(ztn)
        coverage["zt_pool_names_present_in_raw_pct"] = _r(
            100.0 * len(ztn & raw) / max(1, len(ztn)), 1)

    market_fillable = {}
    for b, g in panel[panel["live"]].groupby("board", observed=True):
        m = g[g["y_ok"]]
        market_fillable[str(b)] = _r(100.0 * float(m["fillable"].mean()), 3) if len(m) else None

    # ── models, books, pairing, per board ─────────────────────────────────────
    by_board, pick_store = {}, []
    for board in sorted(panel["board"].unique()):
        if board not in splits:
            continue
        sl = onset.slice_board(panel, board, splits)
        gate = {
            "fit_core_positives": int(sl["fit_core"]["y_limit_up"].sum()),
            "fit_calib_positives": int(sl["fit_calib"]["y_limit_up"].sum()),
            "holdout_positives": int(sl["holdout"]["y_limit_up"].sum()),
            "floors": {"fit_core_positives": MIN_FIT_CORE_POS,
                       "fit_calib_positives": MIN_CALIB_POS,
                       "holdout_positives": MIN_HOLDOUT_POS},
        }
        gate["passes"] = bool(gate["fit_core_positives"] >= MIN_FIT_CORE_POS
                              and gate["fit_calib_positives"] >= MIN_CALIB_POS
                              and gate["holdout_positives"] >= MIN_HOLDOUT_POS)
        if not gate["passes"]:
            by_board[board] = {
                "status": "THIN-SKIP — not modelled",
                "thin_gate": gate,
                "reason": ("L3's pre-registered events-per-variable floor is not met, so L3 "
                           "never built a book here.  A fillability re-statement of a book "
                           "that does not exist would be an invention.  Printed as a "
                           "measured null."),
            }
            print(f"    {board}: THIN-SKIP ({gate['fit_core_positives']} fit-core positives "
                  f"< {MIN_FIT_CORE_POS})", flush=True)
            continue

        b0 = onset.fit_b0(sl["fit_all"])
        b1 = onset.fit_b1(sl, DESIGN_COLS, "B1 six features + N dummies")
        b2 = onset.fit_b2(sl)
        p1 = onset.fit_b1(sl, ["f3_runup_5"], "P1 f3 alone")
        p2 = onset.fit_b1(sl, ["f3_runup_5"] + N_DUMMIES, "P2 f3 + N dummies")

        def score(df: pd.DataFrame) -> dict:
            return {"B0": onset.apply_b0(df, b0), "B1": onset.apply_b1(df, b1),
                    "B2": onset.apply_b2(df, b2), "P1": onset.apply_b1(df, p1),
                    "P2": onset.apply_b1(df, p2)}

        era_start = pd.Timestamp(splits[board]["era_start"])
        sd = pd.Timestamp(splits[board]["split_date"])
        base_mask = ((panel["board"] == board) & (panel["date"] >= era_start)
                     & panel["live"] & panel["complete_case"])
        u2_all = panel[base_mask]

        entry = {"status": "modelled", "split": splits[board], "thin_gate": gate,
                 "market_fillable_pct_all_usable_rows": market_fillable.get(board),
                 "universes": {}}

        for uni in UNIVERSES:
            src_all = u2_all[u2_all["y_ok"]] if uni == "U1_y_ok" else u2_all
            uni_out = {}
            for window in WINDOWS:
                df = (src_all[src_all["date"] < sd] if window == "fit"
                      else src_all[src_all["date"] >= sd]).reset_index(drop=True)
                if df.empty:
                    continue
                preds = score(df)
                graded = df[df["y_ok"]]
                base_rate = float(graded["y_limit_up"].mean()) if len(graded) else 0.0
                pos_per_date = graded.groupby("date", observed=True)["y_limit_up"].sum()

                picks = attach(topk_frame(df, preds, max(TOP_K)), df)
                picks["universe"], picks["window"], picks["board"] = uni, window, board
                pick_store.append(picks[["ticker", "date"]])

                corrupted = corrupt_fillability(df, CORRUPTION_SEED)
                picks["fillable_corrupt"] = corrupted[picks["row"].to_numpy()]

                uni_out[window] = {
                    "rows": len(df), "dates": int(df["date"].nunique()),
                    "graded_rows": len(graded),
                    "base_rate_pct": _r(100.0 * base_rate, 4),
                    "fillable_pct_all_rows": _r(100.0 * float(df["fillable"].mean()), 3),
                    "_picks": picks, "_preds": preds, "_df": df,
                    "_base": base_rate, "_pos": pos_per_date,
                }
            entry["universes"][uni] = uni_out
        by_board[board] = entry
        print(f"    {board}: modelled — books built for "
              f"{sum(len(v) for v in entry['universes'].values())} (universe, window) pairs "
              f"({time.time() - t0:.0f}s)", flush=True)

    # ── price every unique pick ONCE ──────────────────────────────────────────
    pairs = (pd.concat(pick_store, ignore_index=True)
             .drop_duplicates()
             .sort_values(["ticker", "date"])
             .reset_index(drop=True)) if pick_store else pd.DataFrame()
    print(f"[3] pricing {len(pairs):,} unique (ticker, feature-date) entries "
          f"({time.time() - t0:.0f}s)", flush=True)

    priced_primary = price_picks(pairs, cache, CLOSURE_TOLERANT_PRIMARY)
    priced_strict = price_picks(pairs, cache, False)
    trades_primary = {r: g.set_index(["ticker", "date"])
                      for r, g in priced_primary.groupby("rule", sort=True)}
    trades_strict = {r: g.set_index(["ticker", "date"])
                     for r, g in priced_strict.groupby("rule", sort=True)}
    for d in (trades_primary, trades_strict):
        for r in EXIT_RULES:
            d.setdefault(r, pd.DataFrame(
                columns=["ret", "hold", "rolls", "complete", "roll_cost"],
                index=pd.MultiIndex.from_arrays([[], []], names=["ticker", "date"])))

    step_rule_effect = {}
    for rule in EXIT_RULES:
        a, b = trades_primary[rule], trades_strict[rule]
        step_rule_effect[rule] = {
            "closure_tolerant_complete_windows": int(a["complete"].sum()) if len(a) else 0,
            "strict_10d_complete_windows": int(b["complete"].sum()) if len(b) else 0,
            "windows_recovered_by_closure_tolerance": (
                int(a["complete"].sum()) - int(b["complete"].sum())) if len(a) and len(b)
            else None,
        }
    print(f"[4] priced {len(priced_primary):,} trades (closure-tolerant) and "
          f"{len(priced_strict):,} (strict) ({time.time() - t0:.0f}s)", flush=True)

    # ── assemble every cell ───────────────────────────────────────────────────
    headline = []
    for board, entry in by_board.items():
        if entry.get("status") != "modelled":
            continue
        for uni, uni_out in entry["universes"].items():
            for window, blob in uni_out.items():
                picks, df = blob.pop("_picks"), blob.pop("_df")
                preds, base, pos = blob.pop("_preds"), blob.pop("_base"), blob.pop("_pos")

                cells, cells_corrupt = {}, {}
                for ranker in RANKERS:
                    sel = picks[picks["ranker"] == ranker]
                    for k in TOP_K:
                        sub = sel[sel["rank"] < k]
                        if sub.empty:
                            continue
                        key = f"{ranker}|K{k}"
                        cells[key] = _cell_pairing(sub, trades_primary, base, pos)
                        # The control is a gate, not a product: only the paired numbers the
                        # gate reads are kept, so the frozen JSON stays reviewable.
                        cc = _cell_pairing(sub, trades_primary, base, pos,
                                           fill_col="fillable_corrupt")
                        cells_corrupt[key] = {
                            "entry_available_pct": cc["entry_available_pct"],
                            "paper_rate_pct": cc["paper"]["rate"]["rate_pct"],
                            "implementable_rate_pct":
                                cc["implementable"]["rate"]["rate_pct"],
                            "survival_rate": cc["survival_rate"],
                            "books": {
                                r: {"paper_mean_net_pct": v["paper"].get("mean_net_pct"),
                                    "implementable_mean_net_pct":
                                        v["implementable"].get("mean_net_pct"),
                                    "implementable_date_eq_net_pct":
                                        v["implementable"].get("date_eq_weight_net_pct"),
                                    "implementable_dc_t":
                                        v["implementable"].get("date_clustered_t"),
                                    "survival_mean_net": v["survival_mean_net"]}
                                for r, v in cc["books"].items()},
                        }
                blob["cells"] = cells
                blob["corruption_control"] = {
                    "seed": CORRUPTION_SEED,
                    "design": ("fillability permuted within each feature-date across every "
                               "candidate row; the session's market-wide fillable share is "
                               "preserved exactly and only the rank-fillability association "
                               "is destroyed"),
                    "expectation_written_first": ("the paper-vs-implementable gap collapses "
                                                  "to ~0 and the survivor book degrades "
                                                  "toward the unconditional book"),
                    "cells": cells_corrupt,
                }
                blob["fillable_by_top_k"] = fillable_by_k(
                    picks, blob.get("fillable_pct_all_rows"))
                blob["censoring_composition"] = censoring_composition(picks)
                # Diagnostics that would only restate U1 are cut for U2, which exists to
                # measure the censoring U1 cannot see — not to duplicate its tables.
                if uni == PRIMARY_UNIVERSE:
                    blob["fillable_by_p_decile"] = fillable_by_decile(df, preds)
                    blob["strict_step_rule_cells"] = {
                        f"{r}|K{HEADLINE_K}": _cell_pairing(
                            picks[(picks["ranker"] == r) & (picks["rank"] < HEADLINE_K)],
                            trades_strict, base, pos)["books"]
                        for r in HEADLINE_RANKERS
                    }
                    blob["era_tables"] = {
                        f"{r}|K{HEADLINE_K}|{rule}": era_table(
                            picks[(picks["ranker"] == r) & (picks["rank"] < HEADLINE_K)],
                            trades_primary, rule)
                        for r in HEADLINE_RANKERS for rule in ("E1_board_fail",
                                                               "E3_time_stop_T4")
                    }
                    for key, cell in cells.items():
                        for rule, bk in cell["books"].items():
                            headline.append({
                                "board": board, "window": window, "cell": key, "exit": rule,
                                "paper_rate_pct": cell["paper"]["rate"]["rate_pct"],
                                "impl_rate_pct": cell["implementable"]["rate"]["rate_pct"],
                                "entry_available_pct": cell["entry_available_pct"],
                                "paper_net_pct": bk["paper"].get("mean_net_pct"),
                                "impl_net_pct": bk["implementable"].get("mean_net_pct"),
                                "impl_date_eq_net_pct":
                                    bk["implementable"].get("date_eq_weight_net_pct"),
                                "impl_dc_t": bk["implementable"].get("date_clustered_t"),
                                "impl_n": bk["implementable"].get("n"),
                            })

        # L3 parity is a HOLDOUT / U1 statement — that is the table L3 published.
        u1 = entry["universes"].get(PRIMARY_UNIVERSE, {}).get("holdout")
        entry["l3_topk_parity"] = (l3_topk_parity(board, u1["cells"]) if u1
                                   else {"pass": False, "reason": "no U1 holdout book"})

    # ── secondary (b): the survivor census, fit AND holdout ───────────────────
    hf = pd.DataFrame(headline)
    survivors = []
    if not hf.empty:
        for (board, cell, ex), g in hf.groupby(["board", "cell", "exit"], sort=True):
            got = {r["window"]: r for _, r in g.iterrows()}
            if set(got) != set(WINDOWS):
                continue
            f, h = got["fit"], got["holdout"]
            if (f["impl_net_pct"] or -9) > 0 and (h["impl_net_pct"] or -9) > 0:
                survivors.append({
                    "board": board, "cell": cell, "exit": ex,
                    "fit_net_pct": f["impl_net_pct"], "fit_dc_t": f["impl_dc_t"],
                    "fit_n": f["impl_n"],
                    "holdout_net_pct": h["impl_net_pct"], "holdout_dc_t": h["impl_dc_t"],
                    "holdout_n": h["impl_n"],
                    "clears_t2_both": bool((f["impl_dc_t"] or -9) >= 2.0
                                           and (h["impl_dc_t"] or -9) >= 2.0),
                })
    survivor_census = {
        "bar": ("net of a 15 bp round trip, positive in BOTH windows, on complete windows "
                "only; the decision bar additionally requires date-clustered t >= 2.0 in "
                "both"),
        "cells_evaluated": int(hf.groupby(["board", "cell", "exit"]).ngroups) if not hf.empty
        else 0,
        "positive_both_windows": len(survivors),
        "clearing_t2_both_windows": sum(1 for s in survivors if s["clears_t2_both"]),
        "detail": sorted(survivors, key=lambda s: (-(s["holdout_dc_t"] or -99), s["cell"])),
        "max_holdout_dc_t_over_all_implementable_cells": (
            _r(float(hf.loc[hf["window"] == "holdout", "impl_dc_t"].max()), 2)
            if not hf.empty and hf["impl_dc_t"].notna().any() else None),
    }

    # ── verification gates ────────────────────────────────────────────────────
    gates = {
        "y_ok_agreement_L3_vs_L1_arrays": {
            "pass": yok_agree,
            "what_it_pins": ("L3's panel y_ok and L1's independently derived pair rule agree "
                             "row for row — the two lanes are reading the same population"),
        },
        "exclusion_cause_pin": store_meta["store_pass"]["exclusion_cause_pin"],
        "l1_trade_parity": l1_trade_parity(cache),
        "l3_topk_parity": {b: e.get("l3_topk_parity") for b, e in by_board.items()
                           if e.get("status") == "modelled"},
        "corruption_control": None,   # filled below
    }
    print(f"[5] gates: L1 trade parity "
          f"{gates['l1_trade_parity']['pass']} "
          f"(max diff {gates['l1_trade_parity']['max_abs_return_diff']:.2e}) "
          f"({time.time() - t0:.0f}s)", flush=True)

    # corruption summary — the falsifier, read across the primary universe/holdout
    corr_rows = []
    for board, entry in by_board.items():
        if entry.get("status") != "modelled":
            continue
        for window in WINDOWS:
            blob = entry["universes"].get(PRIMARY_UNIVERSE, {}).get(window)
            if not blob:
                continue
            for key, real in blob["cells"].items():
                fake = blob["corruption_control"]["cells"].get(key)
                if fake is None:
                    continue
                corr_rows.append({
                    "board": board, "window": window, "cell": key,
                    "real_rate_gap_pp": real["survival_rate"]["delta_pp"],
                    "corrupt_rate_gap_pp": fake["survival_rate"]["delta_pp"],
                    "real_net_gap_pp_E1":
                        real["books"]["E1_board_fail"]["survival_mean_net"]["delta_pp"],
                    "corrupt_net_gap_pp_E1":
                        fake["books"]["E1_board_fail"]["survival_mean_net"]["delta_pp"],
                })
    cdf = pd.DataFrame(corr_rows).dropna(
        subset=["real_rate_gap_pp", "corrupt_rate_gap_pp",
                "real_net_gap_pp_E1", "corrupt_net_gap_pp_E1"])
    gates["corruption_control"] = {
        "cells": len(cdf),
        "mean_abs_real_rate_gap_pp": _r(float(cdf["real_rate_gap_pp"].abs().mean()), 3)
        if len(cdf) else None,
        "mean_abs_corrupt_rate_gap_pp": _r(float(cdf["corrupt_rate_gap_pp"].abs().mean()), 3)
        if len(cdf) else None,
        "mean_abs_real_net_gap_pp_E1": _r(float(cdf["real_net_gap_pp_E1"].abs().mean()), 3)
        if len(cdf) else None,
        "mean_abs_corrupt_net_gap_pp_E1":
            _r(float(cdf["corrupt_net_gap_pp_E1"].abs().mean()), 3) if len(cdf) else None,
        "collapse_ratio_rate": None,
        "pass": None,
        "reading": ("PASS requires the corrupted gap to collapse toward zero relative to the "
                    "real one.  A corrupted gap of the same size would mean the censor is a "
                    "coding artifact and the whole finding is void."),
        "detail": corr_rows,
    }
    if len(cdf) and float(cdf["real_rate_gap_pp"].abs().mean()) > 0:
        ratio = (float(cdf["corrupt_rate_gap_pp"].abs().mean())
                 / float(cdf["real_rate_gap_pp"].abs().mean()))
        gates["corruption_control"]["collapse_ratio_rate"] = _r(ratio, 4)
        gates["corruption_control"]["pass"] = bool(ratio < 0.10)

    # strip the working frames the JSON must not carry
    for entry in by_board.values():
        for uni_out in entry.get("universes", {}).values():
            for blob in uni_out.values():
                for k in [k for k in blob if k.startswith("_")]:
                    blob.pop(k)

    payload = {
        "instrument": "research/cn_prophet_audit/onset_fillability_restatement_v1.py",
        "program": ("CN LIMIT-MOVE ALPHA — Wave 3 / lane W3-C (onset fillability "
                    "re-statement; masterplan §8 W2 item 3)"),
        "predecessors": {
            "L3_onset": "research/cn_prophet_audit/onset_calibration_v1.py (PR #5055)",
            "L1_rider": "research/cn_prophet_audit/continuation_rider_v1.py (PR #5061)",
            "L0_heals": "data/china_microstructure + data/china_zt_pool (PR #5059)",
            "W3A_windows": ("research/cn_prophet_audit/WINDOW_TARGET_BATTERY_V1_2026-08-09.md "
                            "(PR #5099) — the truncation defect this lane does not re-pay"),
        },
        "tier": ("display/audit — MEASUREMENT ONLY.  Nothing here promotes, ranks for size, "
                 "gates, admits, or reaches a live surface.  No LLM is involved."),
        "honest_prior": (
            "This is a measurement COMPLETION, not an edge hunt.  The expected outcome is "
            "that the edge concentrates in the picks you cannot buy.  That null, cleanly "
            "measured, IS the deliverable."),
        "generated_utc": stamped,
        "store_vintage": VINTAGE,
        "preregistration": PREREG,
        "definitions": {
            "paper": ("the number a naive backtest of L3's top-K book prints: every pick "
                      "graded, and on the return axis every pick FILLED at the T+1 open "
                      "regardless of whether that open was buyable"),
            "implementable": ("the same book with L1's censor: a pick is taken only where "
                              "open[T+1] < limit_price[T+1] * (1 - 0.002)"),
            "fillable": "open[T+1] < limit_price[T+1] * (1 - 0.002), on a usable T+1 bar",
            "yizi_strict": ("the whole T+1 bar printed at the limit: open == high == low == "
                            "close, and the close is a limit-up close"),
            "entry_pair_rule": (f"T and its next bar <= {MAX_PAIR_GAP_DAYS} calendar days "
                                "apart and that bar not excluded — v0's rule, UNCHANGED"),
            "exit_step_rule": ("CLOSURE-TOLERANT: the exit walk steps to the immediately "
                               "following LIVE bar with no calendar cap.  W3-A measured that "
                               "reusing the 10-day pair rule as a walk rule truncates every "
                               "open window market-wide at a CNY / National-Day closure and "
                               "force-closes it at a mark-to-market close.  The strict "
                               "variant is run and printed beside it."),
            "complete_window": ("the exit was realised at a scheduled open (possibly after a "
                                "locked-exit roll).  Store-edge, 30-session-cap and "
                                "roll-cap-exhausted trades are counted separately and "
                                "excluded from every headline."),
            "date_clustered_t": ("each feature-date collapsed to its own mean net return "
                                 "first, so the t counts SESSIONS, not trades"),
            "capture_share": ("share of a date's realized limit-ups the selection contained, "
                              "pooled over the window's dates"),
            "survival_ratio": ("implementable / paper, reported ONLY where the paper value is "
                               "positive; elsewhere read delta_pp"),
            "U1_y_ok": "L3's own rows — live, complete-case, usable next bar",
            "U2_ex_ante": ("live and complete-case WITHOUT the next-bar-usability filter — "
                           "the set a desk can rank at T's close, and the only universe in "
                           "which suspension censoring is visible"),
            "exit_rules": rider.EXIT_RULES,
            "locked_exit": rider.LOCKED_EXIT_NOTE,
            "round_trip_cost": f"{ROUND_TRIP_COST * 1e4:.0f} bp, applied to every net number",
        },
        "coverage_receipt": coverage,
        "panel": {k: panel_meta[k] for k in
                  ("panel_rows", "live_rows", "tickers_kept", "limit_up_events_by_board",
                   "window", "excluded_bars")},
        "store_pass": store_meta,
        "market_fillable_pct_by_board": market_fillable,
        "step_rule_effect": step_rule_effect,
        "verification_gates": gates,
        "survivor_census": survivor_census,
        "headline_grid": headline,
        "by_board": by_board,
        "ore_ledger": ORE_LEDGER,
        "reproduce": ("TZ=UTC python3 research/cn_prophet_audit/"
                      "onset_fillability_restatement_v1.py  (from repo root; deterministic "
                      "apart from generated_utc)"),
    }
    payload["runtime_sec"] = round(time.time() - t0, 1)

    OUT_JSON.write_text(json.dumps(jsonable(payload), indent=2, ensure_ascii=False) + "\n")
    print(f"[6] -> {OUT_JSON.name}  ({payload['runtime_sec']:.0f}s, "
          f"{OUT_JSON.stat().st_size / 1e6:.2f} MB)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
