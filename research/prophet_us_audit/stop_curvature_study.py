#!/usr/bin/env python3
"""Stop-curvature context study — the pre-registered §6.8(a) curvature audition.

CHARTER (BINDING): ``research/prophet_us_audit/STOP_CURVATURE_CHARTER_2026-08-11.md``.
PARENT:            ``research/prophet_us_audit/EARLY_ADMISSION_BAKEOFF_2026-08-11.md``
                   (§R4/R4b strict-form kill, §R9 controls, §RT red-team record).

WHAT THIS IS. R4b killed the §6.8(a) conditioning hypothesis *as pinned* — "1D MACD-RSI
histogram already rising (2-step) at stop confirm" — on rarity (110/12,786 = 0.9%), on
low-marking (23.6% vs 35.0%, month-cluster CI −11.4pp [−19.2,−2.8]) and on forward tape.
That kill closes the strict-rising CONSTRUCTION only. The operator's described form —
"arching up off the histogram low" — is a curvature/above-trailing-min construction the
strict lens cannot express. This script is that family's one pre-registered pass, forms
K1–K5 exactly as charter §2 enumerates them, on the pre-declared primary cells.

WHAT THIS REFUSES TO DO.
  * No form outside the enumerated five gets a classification rule or an outcome read.
    Any new form is a NEW charter (charter §2 last line). There is no search here.
  * No best-cell promotion. Grids are sensitivity-only and printed in full; every gate is
    judged on the pre-declared primary cell (charter §4.4).
  * No outcome column is readable before the G5 exemplar gate has concluded. That is not
    a convention here, it is enforced: the outcome columns live inside ``OutcomeVault``
    and every read before ``vault.unseal()`` raises. The ordering and its wall-clock
    timestamps are printed in RC.g5 so the sequence is auditable from the output alone.
  * No null is softened. A form that fails is a COMPLETED result: its row lands in the ore
    ledger, the construction closes, the family stays open ("not found yet" ≠ "does not
    exist", house epistemics law).

EXTRACTION (single path, no second lane). The frame is the R4 replay's frozen
``early_admission_bakeoff_stops.parquet`` (12,940 confirms). It carries point-in-time FLAGS
only — no per-bar histogram series — so K1–K3 need the 1D histogram path recomputed. The
recomputation reuses the parent's OWN loader (``early_admission_bakeoff.load_ohlc``) and
the same engine primitives ``NameData`` used (``engine.signal_quality._rsi_macd`` for the
1D MACD-RSI histogram, ``_tf_grid``+``_rsi_macd`` for the session-anchored 3D leg), and it
is GATED: RC.parity must reproduce the stored ``hist_rising`` column on every row of the
frame or the run aborts (exit 3). A study run on a series that disagrees with the replay's
own column measures nothing.

3D PHASE (charter §2 K4 dependency / §4.6). The defect the parent found in R4.hl_phase is
charting-app ``confluence_v2``'s first-timestamp-phased ``resample`` — MACRO-side the 3D
grid has been absolutely session-anchored since ``ANCHOR_ERA=sq-abs-session-2026-08-06``
(``engine/session_anchor.py``), so the stored ``m3_bull`` column already IS the
session-anchored recomputation. This script proves that rather than assuming it: it
rebuilds the session-anchored leg independently (RC.parity row 2) AND rebuilds a
first-timestamp-phased leg mimicking the defect, and prints the divergence (RC.parity
row 3) — a material phased-vs-anchored divergence is itself a finding (charter §4.6).

Usage (defaults are the parent run's own roots — the store is frozen at 2026-08-10):
    python3 research/prophet_us_audit/stop_curvature_study.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# The parent's OWN extraction + table machinery. Importing is safe: the module is
# ``__main__``-guarded and has no import-time side effects beyond constants.
from early_admission_bakeoff import (  # noqa: E402
    DEF_PRICE_ROOT, DEF_STOCKS_ROOT, Table, TABLES, load_ohlc, med, pct,
)
from engine.signal_quality import (  # noqa: E402
    ANCHOR_ERA, _rsi_macd, _tf_grid,
)
from engine.stock_technicals import atr as wilder_atr  # noqa: E402

# ---------------------------------------------------------------- frozen constants
# --- charter §2: the five forms and their PRE-DECLARED primary cells ---
K1_W_PRIMARY = 15                  # K1 off-the-trailing-min: primary w
K1_W_GRID = (10, 15, 21)           # ... sensitivity only
K2_M_PRIMARY = 3                   # K2 curvature proper: primary m
K2_M_GRID = (3, 5)
K3_PRIMARY = (0.30, 15)            # K3 normalized recovery: primary (theta, w)
K3_GRID = ((0.15, 15), (0.30, 15), (0.15, 10), (0.30, 10), (0.15, 21), (0.30, 21))
K2_MAX_NEG_FIRST_DIFF = 1          # "arch, not staircase": at most one negative first-diff
BUCKET_N = 3                       # the 3D grid (charter K4 / parent BUCKET_N)
SF_MIN_BUCKETS = 90                # signal_frame returns EMPTY below this many 3D bars

# --- charter §3: frame + outcome definitions (frozen; parent R4/R9f conventions) ---
NEAR_WIN_PRIMARY = 10              # +/-10-session local-low window
NEAR_TOL_PRIMARY = 2               # ... "at the low" = within +/-2 sessions of its argmin
NEAR_WIN_GRID = (5, 10, 15)        # R9f window-grid sensitivity
BASE_PUBLISHED = 0.349             # parent R4: 34.9% of confirms mark lows
NULL_PUBLISHED = 0.157             # parent R9f: 15.7% random-session null on the same frame

# --- charter §5: promotion gates ---
G1_COVERAGE_MIN = 0.05             # >=5% of confirms or rare-lens disclosure tier only
G2_LIFT_MIN_PP = 8.0               # >= +8pp over base
G2_CI_LOWER_MIN_PP = 2.0           # ... month-cluster CI lower bound > +2pp
G3_LIFT_RETAINED = 0.5             # >= half the raw lift retained, sign-stable, all 3 lenses
G4_FWD10_MIN = 0.02                # curvature-TRUE median fwd10 >= +2%

# --- charter §4.2 / parent §R9d: the risk-equalization battery ---
ALT_STOP_FIX = 0.08                # lens A: fixed -8% trigger (parent ALT_STOP_FIX)
ALT_STOP_ATR = 2.0                 # lens B: trailing anchor - 2 x ATR14 (parent ALT_STOP_ATR[0])
ALT_ANCHOR_WIN = 21                # ... both measured from the trailing 21-session max close
ALT_DEDUP = 10                     # ... deduped like the parent's DEDUP_SESSIONS
QUINTILES = 5                      # lens C: break-depth conditioning bins (parent QUINTILES)
MIN_CELL_N = 20                    # a cell thinner than this gets no verdict (parent)

# --- determinism ---
BOOT_B = 500                       # month-cluster bootstrap draws (parent BOOT_B)
CURV_SEED = 20260812               # this study's seed (parent used 20260811 for its own)
PIT_TOL = 1e-9                     # truncation-identity tolerance for the leak test

# --- charter §1: the motivating exemplars (outcomes already public; see the STLD-excluded row) ---
EXEMPLARS = (("STLD", "2026-05-19"), ("STLD", "2026-01-07"))
EXEMPLAR_NARRATIVE = ("STLD", "2026-06-18")   # illustration only; no lens is tuned to reject it
STLD = "STLD"

# --- charter §3 / parent §6: substrate bounds, restated verbatim, never silently re-windowed ---
SUBSTRATE = {
    "price_window": "the ohlcv store's ~2014+ coverage",
    "store_events_dropped_C0": 18137,
    "store_events_dropped_C2": 7202,
    "dropped_disposition": "dropped, NEVER relocated",
    "exposure_name_years": 2658.7,
    "survivorship": ("241-name deep-history store universe: names that delisted before the "
                     "store existed are absent, so outcome columns carry survivorship tint"),
    "breadth": "breadth features are NOT used here, so the post-2023 basket bound does not bind",
    "anchor_era": ANCHOR_ERA,
}

NOTES: list[str] = []
DEFERRED: list[str] = []


def note(msg: str) -> None:
    if msg not in NOTES:
        NOTES.append(msg)
        print(f"NOTE: {msg}", flush=True)


def defer(msg: str) -> None:
    if msg not in DEFERRED:
        DEFERRED.append(msg)
        print(f"DEFERRED: {msg}", flush=True)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------- outcome ordering (gate 1)
class OutcomeSealError(RuntimeError):
    """Raised when an outcome column is read before the G5 exemplar gate concludes."""


class OutcomeVault:
    """The frame's OUTCOME columns, physically unreadable until G5 has concluded.

    Charter §1: a lens that misses either motivating exemplar "is disqualified **ex ante**
    — before its outcome row is read". A comment cannot enforce that. This can: every
    outcome column lives in here, ``get`` raises ``OutcomeSealError`` while sealed, and the
    unseal timestamp is printed beside the G5 timestamps in RC.g5 so the ordering is
    auditable from the script's own output rather than from trust in the author.
    """

    #: the columns that describe WHAT HAPPENED (as opposed to what was knowable at T)
    OUTCOME_COLS = ("near_low_stop", "gap", "argmin_date", "fwd10", "fwd21")

    def __init__(self, frame: pd.DataFrame):
        self._hidden = {c: frame[c].copy() for c in self.OUTCOME_COLS if c in frame.columns}
        self._sealed = True
        self.sealed_at = _utc()
        self.unsealed_at: str | None = None
        self.reads = 0

    @classmethod
    def seal(cls, frame: pd.DataFrame) -> tuple[pd.DataFrame, "OutcomeVault"]:
        """Move the outcome columns OUT of the working frame and into the vault.

        The seal is structural, not stylistic: after this call the columns are simply not
        on the DataFrame, so an accidental ``frame["near_low_stop"]`` anywhere downstream
        raises ``KeyError`` rather than quietly leaking an outcome into a pre-G5 table.
        (It already caught one in this script: the frame-reconciliation base rate.)
        """
        vault = cls(frame)
        return frame.drop(columns=[c for c in cls.OUTCOME_COLS if c in frame.columns]), vault

    def get(self, col: str, pos: np.ndarray | None = None) -> np.ndarray:
        """Return an outcome column, optionally restricted to ``pos`` (positions in the
        ORIGINAL stops frame). Raises while sealed — including for the frame's own base
        rate, which is as much an outcome as any cohort's."""
        if self._sealed:
            raise OutcomeSealError(
                f"outcome column {col!r} read while SEALED — the G5 exemplar gate has not "
                "concluded. Charter §1: forms are disqualified ex ante, before outcomes.")
        if col not in self._hidden:
            raise KeyError(col)
        self.reads += 1
        v = self._hidden[col].to_numpy()
        return v if pos is None else v[pos]

    def unseal(self) -> None:
        self._sealed = False
        self.unsealed_at = _utc()


# ---------------------------------------------------------------- per-name recomputation
class NameCurv:
    """One ticker's curvature substrate, rebuilt on the parent's OWN extraction.

    Everything here is a function of bars at-or-before its own index position; nothing in
    this class reads a bar after the row it describes (proved, not asserted, in RC.pit).
    """

    def __init__(self, ticker: str, df: pd.DataFrame, source: str):
        self.ticker, self.source = ticker, source
        self.idx = df.index
        self.pos = {d: i for i, d in enumerate(self.idx)}
        self.close = df["close"]
        self.c = self.close.to_numpy(dtype="float64")
        self.h = df["high"].to_numpy(dtype="float64")
        self.l = df["low"].to_numpy(dtype="float64")
        self.atr14 = wilder_atr(df["high"], df["low"], df["close"], 14).to_numpy(dtype="float64")

        # -- 1D MACD-RSI histogram: the EXACT NameData construction (hist1 = macd - signal) --
        m1, s1 = _rsi_macd(self.close)
        self.hist = (m1 - s1).to_numpy(dtype="float64")

        # -- 3D leg, session-anchored (engine/session_anchor via _tf_grid) --
        self.m3_sa, self.m3_src = self._m3_session_anchored()
        # -- 3D leg, first-timestamp phased: the confluence_v2 defect class, for RC.parity --
        self.m3_ph = self._m3_phased()

    # ---- 3D legs ----
    def _m3_session_anchored(self) -> tuple[np.ndarray, np.ndarray]:
        """``signal_frame``'s own 3D macd>=sig leg, mapped to daily at bucket-LAST knowability.

        Reproduces ``NameData.m3_ge_daily`` exactly: ``_tf_grid`` buckets absolutely on the
        session calendar, ``_rsi_macd`` runs on the bucket closes, and the state is carried
        to daily bars from the bucket's LAST session — never its open label — so a bar mid
        bucket reads the PREVIOUS completed bucket. ``m3_src`` records which session each
        daily value became knowable on; RC.pit asserts that date never exceeds the bar.
        """
        false_arr = np.zeros(len(self.idx), dtype=bool)
        nat = np.full(len(self.idx), np.datetime64("NaT"), dtype="datetime64[ns]")
        grid = _tf_grid(self.close, BUCKET_N, "US")
        s3 = grid.close
        if len(s3) < SF_MIN_BUCKETS:      # signal_frame returns an EMPTY frame -> all False
            return false_arr, nat
        macd, sig = _rsi_macd(s3)
        state = (macd >= sig).astype(float)
        ls = pd.DatetimeIndex(grid.last_session.reindex(s3.index).to_numpy())
        kd = pd.Series(state.to_numpy(), index=ls)
        kd = kd[~kd.index.isna()]
        kd = kd[~kd.index.duplicated(keep="last")].sort_index()
        daily = kd.reindex(self.idx, method="ffill")
        src = pd.Series(kd.index.to_numpy(), index=kd.index).reindex(self.idx, method="ffill")
        return (daily >= 0.5).to_numpy(), src.to_numpy(dtype="datetime64[ns]")

    def _m3_phased(self) -> np.ndarray:
        """The SAME leg on a first-timestamp-phased grid — the R4.hl_phase defect class.

        ``confluence_v2`` cuts its 3D grid with a pandas resample whose bin edges anchor to
        the SERIES' first timestamp, so the bucket a date lands in depends on how much
        leading history the caller handed in. Reproduced here as positional bucketing
        (``position_in_THIS_series // 3``) — the same leading-history dependence — so the
        divergence against the absolute anchor can be measured instead of assumed.
        """
        false_arr = np.zeros(len(self.idx), dtype=bool)
        b = np.arange(len(self.idx)) // BUCKET_N
        agg = (pd.DataFrame({"v": self.c, "d": self.idx.to_numpy()})
               .groupby(b, sort=True).agg(close=("v", "last"), last_session=("d", "last")))
        s3 = pd.Series(agg["close"].to_numpy(), index=pd.DatetimeIndex(agg["last_session"]))
        if len(s3) < SF_MIN_BUCKETS:
            return false_arr
        macd, sig = _rsi_macd(s3)
        kd = (macd >= sig).astype(float)
        kd = kd[~kd.index.duplicated(keep="last")].sort_index()
        return (kd.reindex(self.idx, method="ffill") >= 0.5).to_numpy()

    # ---- the charter's five forms; each is (value | None-if-unavailable) ----
    def tmin(self, T: int, w: int) -> float | None:
        """Trailing minimum of ``hist`` over the prior ``w`` sessions, EXCLUDING bar T.

        Charter §2: the confirm bar is excluded from the minimum "so 'off the low' is
        knowable" — with T included, ``hist > tmin`` would be unfalsifiable at a new low.
        """
        if T - w < 0:
            return None
        seg = self.hist[T - w: T]
        if not np.isfinite(seg).any():
            return None
        return float(np.nanmin(seg))

    def k1(self, T: int, w: int = K1_W_PRIMARY) -> bool | None:
        h = self.hist[T]
        tm = self.tmin(T, w)
        if tm is None or not np.isfinite(h):
            return None
        return bool(h > tm and h < 0.0 and tm < 0.0)

    def k2(self, T: int, m: int = K2_M_PRIMARY, tight: bool = False) -> bool | None:
        """Charter K2: mean 2nd difference over the last ``m`` bars >= 0, <=1 negative 1st diff.

        DISCLOSED AMBIGUITY: "over the last m bars" admits two readings — m DIFFERENCES
        (bars T-m..T, the default here, the more generous window) or m BARS (T-m+1..T).
        The charter does not disambiguate, so rather than resolve it silently this study
        implements both and prints both in RC.grid. Both readings return FALSE at both
        motivating exemplars, so the G5 verdict does not turn on the choice.
        """
        lo = T - m + 1 if tight else T - m
        if lo < 0:
            return None
        seg = self.hist[lo: T + 1]
        if not np.isfinite(seg).all() or seg.size < 3:
            return None
        d1 = np.diff(seg)
        d2 = np.diff(d1)
        if d2.size == 0:
            return None
        return bool(float(np.mean(d2)) >= 0.0
                    and int((d1 < 0).sum()) <= K2_MAX_NEG_FIRST_DIFF)

    def k3(self, T: int, theta: float = K3_PRIMARY[0], w: int = K3_PRIMARY[1]) -> bool | None:
        h = self.hist[T]
        tm = self.tmin(T, w)
        if tm is None or not np.isfinite(h):
            return None
        if tm >= 0.0:
            return False
        return bool((h - tm) / abs(tm) >= theta)

    def k4(self, T: int) -> bool | None:
        return bool(self.m3_sa[T])

    def k5(self, T: int) -> bool | None:
        a, b = self.k1(T, K1_W_PRIMARY), self.k4(T)
        if a is None and b is None:
            return None
        return bool(bool(a) or bool(b))

    def hist_rising(self, T: int) -> bool | None:
        """The parent's OWN killed strict form (R4b), recomputed at an arbitrary bar.

        Not a charter form and not a candidate: it exists so the R9d battery can be
        exercised on an already-published lens when no new form survives G5.
        """
        h = self.hist
        if T < 2:
            return None
        if not (np.isfinite(h[T]) and np.isfinite(h[T - 1]) and np.isfinite(h[T - 2])):
            return False
        return bool(h[T] > h[T - 1] > h[T - 2])

    def form(self, name: str, T: int) -> bool | None:
        return {"K1": self.k1, "K2": self.k2, "K3": self.k3, "K4": self.k4, "K5": self.k5,
                CONTROL_FORM: self.hist_rising}[name](T)

    # ---- outcome primitive (charter §3): near-low on ANY window, from bars only ----
    def near_low(self, T: int, win: int, tol: int) -> bool | None:
        a, b = T - win, T + win
        if a < 0 or b > len(self.idx) - 1:
            return None
        arg = a + int(np.nanargmin(self.l[a: b + 1]))
        return bool(abs(T - arg) <= tol)


FORMS = ("K1", "K2", "K3", "K4", "K5")
#: NOT a charter form — the parent's already-published R4b strict split, used only to
#: exercise the R9d battery when no enumerated form survives G5 (auditions nothing).
CONTROL_FORM = "R4b(hist_rising)"
FORM_LABEL = {
    "K1": f"K1 off-the-trailing-min (hist>tmin_w, hist<0, tmin_w<0) — primary w={K1_W_PRIMARY}",
    "K2": f"K2 curvature proper (mean 2nd diff >=0, <=1 negative 1st diff) — primary m={K2_M_PRIMARY}",
    "K3": f"K3 normalized recovery ((hist-tmin_w)/|tmin_w| >= θ) — primary θ={K3_PRIMARY[0]}, w={K3_PRIMARY[1]}",
    "K4": "K4 multi-timeframe carry (3D MACD-RSI >= signal at confirm, session-anchored)",
    "K5": f"K5 composite K1(w={K1_W_PRIMARY}) OR K4 — the single pre-declared union",
}


# ---------------------------------------------------------------- statistics
def rate(flags) -> float | None:
    v = [bool(x) for x in flags if x is not None]
    return float(np.mean(v)) if v else None


def iqr(vals) -> tuple[float | None, float | None]:
    v = [float(x) for x in vals if x is not None and np.isfinite(x)]
    if not v:
        return None, None
    return float(np.percentile(v, 25)), float(np.percentile(v, 75))


def month_cluster_ci(months: np.ndarray, cohort: np.ndarray,
                     hit: np.ndarray) -> tuple[float | None, float | None]:
    """Month-cluster bootstrap CI on the TRUE-minus-FALSE near-low spread (R4b style).

    The parent reported the killed strict form as −11.4pp [−19.2,−2.8] on exactly this
    estimand (23.6% TRUE vs 35.0% FALSE), so G2's "+8pp with a CI lower bound > +2pp" is
    read against the same quantity. Clustering by calendar month is the parent's own answer
    to the frame's clear serial dependence — stops arrive in washout clusters.
    """
    ok = ~pd.isna(cohort)
    months, cohort, hit = months[ok], cohort[ok].astype(bool), hit[ok].astype(bool)
    if cohort.size == 0:
        return None, None
    order = np.argsort(months, kind="stable")
    months, cohort, hit = months[order], cohort[order], hit[order]
    bounds = np.flatnonzero(np.r_[True, months[1:] != months[:-1]])
    groups = np.split(np.arange(months.size), bounds[1:])
    if len(groups) < 4:
        return None, None
    rng = np.random.default_rng(CURV_SEED)
    draws = []
    for _ in range(BOOT_B):
        pick = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        co, hi = cohort[pick], hit[pick]
        if co.sum() == 0 or (~co).sum() == 0:
            continue
        draws.append(hi[co].mean() - hi[~co].mean())
    if len(draws) < BOOT_B // 4:
        return None, None
    return float(np.percentile(draws, 2.5) * 100), float(np.percentile(draws, 97.5) * 100)


def per_name_first(tickers: np.ndarray, cohort: np.ndarray,
                   hit: np.ndarray) -> tuple[float | None, int]:
    """Per-name-first aggregation (R2 style): each NAME's rate, then the mean over names."""
    ok = (~pd.isna(cohort)) & cohort.astype(bool)
    if ok.sum() == 0:
        return None, 0
    d = pd.DataFrame({"t": tickers[ok], "h": hit[ok].astype(bool)})
    per = d.groupby("t")["h"].mean()
    return float(per.mean()), int(per.size)


# ---------------------------------------------------------------- build
def build_names(tickers: list[str], price_root: Path,
                stocks_root: Path) -> tuple[dict[str, NameCurv], list[str]]:
    out, missing = {}, []
    for i, t in enumerate(tickers, 1):
        df, src = load_ohlc(t, price_root, stocks_root)
        if df is None or df.empty:
            missing.append(t)
            continue
        out[t] = NameCurv(t, df, src)
        if i % 40 == 0:
            print(f"  ... built {i}/{len(tickers)} names", flush=True)
    return out, missing


# ---------------------------------------------------------------- RC.parity (blocking gate)
def parity_gate(stops: pd.DataFrame, nds: dict[str, NameCurv]) -> tuple[bool, dict]:
    """BLOCKING: the recomputed histogram must reproduce ``hist_rising`` on ALL rows.

    ``hist_rising`` is the parent's own column, defined at ``early_admission_bakeoff.py``
    ``stop_row``: T>=2, all three of hist[T],hist[T-1],hist[T-2] finite, and strictly
    hist[T] > hist[T-1] > hist[T-2]. If a single row disagrees, the recomputed series is
    not the replay's series and NOTHING downstream measures what it claims to.
    """
    n = len(stops)
    hr_match = hr_seen = 0
    m3sa_match = m3ph_match = m3_seen = 0
    unresolved = []
    hr_bad, m3_bad = [], []
    for r in stops.itertuples(index=False):
        nd = nds.get(r.ticker)
        if nd is None:
            unresolved.append((r.ticker, str(pd.Timestamp(r.date).date()), "no price frame"))
            continue
        T = nd.pos.get(pd.Timestamp(r.date))
        if T is None:
            unresolved.append((r.ticker, str(pd.Timestamp(r.date).date()), "date not in frame"))
            continue
        h = nd.hist
        recomputed = bool(T >= 2 and np.isfinite(h[T]) and np.isfinite(h[T - 1])
                          and np.isfinite(h[T - 2]) and h[T] > h[T - 1] > h[T - 2])
        hr_seen += 1
        if recomputed == bool(r.hist_rising):
            hr_match += 1
        elif len(hr_bad) < 12:
            hr_bad.append((r.ticker, str(pd.Timestamp(r.date).date()),
                           bool(r.hist_rising), recomputed,
                           [None if not np.isfinite(x) else round(float(x), 6)
                            for x in h[max(0, T - 2): T + 1]]))
        m3_seen += 1
        if bool(nd.m3_sa[T]) == bool(r.m3_bull):
            m3sa_match += 1
        elif len(m3_bad) < 12:
            m3_bad.append((r.ticker, str(pd.Timestamp(r.date).date()),
                           bool(r.m3_bull), bool(nd.m3_sa[T])))
        if bool(nd.m3_ph[T]) == bool(r.m3_bull):
            m3ph_match += 1

    tb = Table("RC.parity",
               "PARITY GATE — recomputed series vs the R4 replay's own stored columns",
               ["leg", "rows compared", "matches", "mismatches", "match%", "verdict"],
               "BLOCKING on hist_rising: a divergent series measures nothing, so the run "
               "aborts (exit 3) rather than proceeding on it. The 3D rows are diagnostic: "
               "they establish which grid phase the stored m3_bull column actually holds.")
    tb.add("1D MACD-RSI histogram -> hist_rising (2-step strict)", hr_seen, hr_match,
           hr_seen - hr_match, pct(hr_match / hr_seen if hr_seen else None),
           "PASS" if hr_seen == n and hr_match == hr_seen else "FAIL")
    tb.add("3D macd>=sig, SESSION-ANCHORED -> m3_bull", m3_seen, m3sa_match,
           m3_seen - m3sa_match, pct(m3sa_match / m3_seen if m3_seen else None),
           "matches stored" if m3sa_match == m3_seen else "diverges from stored")
    tb.add("3D macd>=sig, FIRST-TIMESTAMP PHASED -> m3_bull", m3_seen, m3ph_match,
           m3_seen - m3ph_match, pct(m3ph_match / m3_seen if m3_seen else None),
           "phase-defect mimic (charter §4.6 reconciliation row)")
    tb.emit()

    if unresolved:
        ub = Table("RC.parity.unresolved", "Rows the recomputation could not resolve",
                   ["ticker", "date", "reason"])
        for u in unresolved[:40]:
            ub.add(*u)
        ub.emit()
    if hr_bad:
        bb = Table("RC.parity.hist_mismatch", "hist_rising DIVERGENCES (first 12)",
                   ["ticker", "date", "stored", "recomputed", "hist[T-2:T]"])
        for b in hr_bad:
            bb.add(*b)
        bb.emit()
    if m3_bad:
        mb = Table("RC.parity.m3_mismatch",
                   "m3_bull vs session-anchored recomputation — divergences (first 12)",
                   ["ticker", "date", "stored m3_bull", "session-anchored"])
        for b in m3_bad:
            mb.add(*b)
        mb.emit()

    ok = (not unresolved) and hr_seen == n and hr_match == hr_seen
    return ok, {"rows": n, "hist_seen": hr_seen, "hist_match": hr_match,
                "m3_session_anchored_match": m3sa_match, "m3_phased_match": m3ph_match,
                "m3_seen": m3_seen, "unresolved": len(unresolved),
                "hist_mismatch_examples": hr_bad, "m3_mismatch_examples": m3_bad}


# ---------------------------------------------------------------- RC.pit (gate 2)
def pit_leak_test(stops: pd.DataFrame, nds: dict[str, NameCurv], sample: int) -> tuple[bool, dict]:
    """A leak test that CAN FAIL — not a comment (charter §4.1; parent §RT retraction class).

    Two independent legs, because the two substrates leak differently:

      (a) 1D TRUNCATION IDENTITY. Recompute the histogram on ``close[:T+1]`` only and
          require every value in the deepest window any form reads — [T-21, T] — to match
          the full-series value to 1e-9. Any centred/backward-filled/forward-reaching step
          anywhere in ``_rsi_macd`` moves these numbers and the test reds. (This is the
          exact defect class the parent had to retract on: a label window resolving past T.)
      (b) 3D KNOWABILITY. Every daily 3D value carries the session it became knowable on
          (bucket LAST, never the open label). Assert that date <= the confirm bar, on
          EVERY row — a bucket that has not finished by T cannot be read at T.

    Both legs run BEFORE any table freezes. A failure aborts the run (exit 4).
    """
    rows = stops.reset_index(drop=True)
    rng = np.random.default_rng(CURV_SEED)
    if sample and sample < len(rows):
        pick = sorted(rng.choice(len(rows), size=sample, replace=False).tolist())
        scope = f"seeded random sample of {sample}/{len(rows)} rows (seed {CURV_SEED})"
    else:
        pick = list(range(len(rows)))
        scope = f"ALL {len(rows)} rows"

    deepest = max(max(K1_W_GRID), max(K3_GRID, key=lambda x: x[1])[1], max(K2_M_GRID)) + 2
    t0 = time.time()
    trunc_checked = trunc_bad = 0
    worst = 0.0
    bad_examples = []
    for i in pick:
        r = rows.iloc[i]
        nd = nds.get(r["ticker"])
        if nd is None:
            continue
        T = nd.pos.get(pd.Timestamp(r["date"]))
        if T is None or T < deepest:
            continue
        m1, s1 = _rsi_macd(nd.close.iloc[:T + 1])
        trunc = (m1 - s1).to_numpy(dtype="float64")
        a = T - deepest
        full_seg, tr_seg = nd.hist[a: T + 1], trunc[a: T + 1]
        both = np.isfinite(full_seg) & np.isfinite(tr_seg)
        if (np.isfinite(full_seg) != np.isfinite(tr_seg)).any():
            trunc_bad += 1
            if len(bad_examples) < 8:
                bad_examples.append((r["ticker"], str(pd.Timestamp(r["date"]).date()),
                                     "finite-mask differs"))
        elif both.any():
            d = float(np.max(np.abs(full_seg[both] - tr_seg[both])))
            worst = max(worst, d)
            if d > PIT_TOL:
                trunc_bad += 1
                if len(bad_examples) < 8:
                    bad_examples.append((r["ticker"], str(pd.Timestamp(r["date"]).date()),
                                         f"max|Δ|={d:.3e}"))
        trunc_checked += 1
    elapsed = time.time() - t0

    know_checked = know_bad = 0
    know_examples = []
    for r in rows.itertuples(index=False):
        nd = nds.get(r.ticker)
        if nd is None:
            continue
        T = nd.pos.get(pd.Timestamp(r.date))
        if T is None:
            continue
        src = nd.m3_src[T]
        know_checked += 1
        if np.isnat(src):
            continue                      # no 3D state yet -> the leg reads False, no leak
        if pd.Timestamp(src) > pd.Timestamp(r.date):
            know_bad += 1
            if len(know_examples) < 8:
                know_examples.append((r.ticker, str(pd.Timestamp(r.date).date()),
                                      str(pd.Timestamp(src).date())))

    tb = Table("RC.pit", "PIT LEAK TEST — every feature input <= the confirm-bar close",
               ["leg", "scope", "checked", "violations", "worst deviation", "verdict"],
               "A test that can FAIL, not a comment (charter §4.1). Leg (a) recomputes the "
               "histogram on a series TRUNCATED at T and demands bit-comparable values over "
               f"[T-{deepest}, T]; leg (b) demands every 3D value's knowability session <= T.")
    tb.add("(a) 1D histogram truncation identity", scope, trunc_checked, trunc_bad,
           f"{worst:.3e}", "PASS" if trunc_bad == 0 else "FAIL")
    tb.add("(b) 3D bucket-last knowability <= confirm bar", f"ALL {len(rows)} rows",
           know_checked, know_bad, "-", "PASS" if know_bad == 0 else "FAIL")
    tb.emit()
    if bad_examples or know_examples:
        eb = Table("RC.pit.violations", "PIT violations (first 8 per leg)",
                   ["leg", "ticker", "date", "detail"])
        for e in bad_examples:
            eb.add("(a) truncation", e[0], e[1], e[2])
        for e in know_examples:
            eb.add("(b) knowability", e[0], e[1], f"knowable {e[2]} > confirm")
        eb.emit()

    ok = trunc_bad == 0 and know_bad == 0
    return ok, {"truncation_scope": scope, "truncation_checked": trunc_checked,
                "truncation_violations": trunc_bad, "worst_abs_dev": worst,
                "truncation_seconds": round(elapsed, 1),
                "knowability_checked": know_checked, "knowability_violations": know_bad,
                "deepest_window": deepest}


# ---------------------------------------------------------------- RC.g5 (gate 1, runs FIRST)
def g5_exemplar_gate(nds: dict[str, NameCurv], vault: OutcomeVault) -> tuple[dict, dict]:
    """Charter §1 exemplar-coverage gate — DEFINITION VALIDITY, checked before outcomes.

    "A candidate lens must classify May-19 AND Jan-07 curvature-TRUE at their confirm-bar
    closes using only information available then. A lens that misses either does not
    formalize the operator's visual form and is disqualified **ex ante** — before its
    outcome row is read." A form that fails here gets NO outcome row: not a weak row, not
    a caveated row, none.
    """
    started = _utc()
    t_start = time.perf_counter()
    verdicts: dict[str, dict] = {}

    def _cell(v: bool | None) -> str:
        return "-" if v is None else ("TRUE" if v else "FALSE")

    tb = Table("RC.g5", "G5 EXEMPLAR-COVERAGE GATE (charter §1) — ex ante, before any outcome",
               ["form"] + [f"{t} {d}" for t, d in EXEMPLARS] + ["G5", "consequence"],
               "Checked at the exemplars' own confirm-bar closes on information available "
               "then. FAIL = DISQUALIFIED ex ante; the form gets no outcome row at all.")
    for f in FORMS:
        cells = {}
        for tkr, d in EXEMPLARS:
            nd = nds.get(tkr)
            T = None if nd is None else nd.pos.get(pd.Timestamp(d))
            cells[d] = None if T is None else nd.form(f, T)
        passed = bool(cells) and all(v is True for v in cells.values())
        verdicts[f] = {"cells": dict(cells), "pass": passed}
        tb.add(FORM_LABEL[f].split(" —")[0], *[_cell(cells[d]) for _, d in EXEMPLARS],
               "PASS" if passed else "FAIL",
               "outcome row read" if passed else "DISQUALIFIED ex ante — no outcome row")
    tb.emit()

    # The receipts behind the verdict: the raw histogram path and 3D state at each exemplar,
    # printed so the gate is auditable rather than asserted. No cohort, no outcome.
    rb = Table("RC.g5.receipt",
               "Exemplar receipts — the substrate the gate read (confirm-bar close, PIT)",
               ["ticker", "confirm", "hist[T]", "hist[T-1]", "hist[T-2]",
                f"tmin_w={K1_W_PRIMARY} (excl T)", "hist vs tmin", "3D bull (anchored)",
                "3D bull (phased)"],
               "hist = 1D MACD-RSI histogram, the R4 replay's own series (RC.parity-locked).")
    for tkr, d in list(EXEMPLARS) + [EXEMPLAR_NARRATIVE]:
        nd = nds.get(tkr)
        T = None if nd is None else nd.pos.get(pd.Timestamp(d))
        if T is None:
            rb.add(tkr, d, "-", "-", "-", "-", "-", "-", "-")
            continue
        tm = nd.tmin(T, K1_W_PRIMARY)
        rb.add(tkr, d + ("  (narrative only)" if (tkr, d) == EXEMPLAR_NARRATIVE else ""),
               round(float(nd.hist[T]), 4), round(float(nd.hist[T - 1]), 4),
               round(float(nd.hist[T - 2]), 4), None if tm is None else round(tm, 4),
               "-" if tm is None else ("ABOVE (off the low)" if nd.hist[T] > tm
                                       else "AT/BELOW (fresh low)"),
               bool(nd.m3_sa[T]), bool(nd.m3_ph[T]))
    rb.emit()

    # ---- cross-check receipt: is the G5 failure about the SERIES, or about the bar? ----
    # Strictly a receipt on the three already-public exemplars: it defines no form,
    # classifies no cohort, reads no outcome column and licenses nothing. It exists for one
    # reason — if every enumerated form misses the exemplars, the successor charter needs to
    # know whether that is specific to the house MACD-RSI series or true of the daily
    # histogram generally. Textbook MACD(12,26,9) on close is the obvious rival serialization
    # of "the histogram" the operator would be looking at.
    cb = Table("RC.g5.crosscheck",
               "CROSS-CHECK RECEIPT — textbook MACD(12,26,9) histogram at the same exemplars",
               ["ticker", "confirm", "hist[T-2]", "hist[T-1]", "hist[T]",
                f"tmin_w={K1_W_PRIMARY} (excl T)", "reading"],
               "RECEIPT ONLY, on the 3 exemplars whose outcomes are already public. Defines "
               "no form, classifies no cohort, reads no outcome, licenses nothing. Its only "
               "job is to tell a successor charter whether a G5 miss is a property of the "
               "house MACD-RSI series or of the daily bar itself.")
    for tkr, d in list(EXEMPLARS) + [EXEMPLAR_NARRATIVE]:
        nd = nds.get(tkr)
        T = None if nd is None else nd.pos.get(pd.Timestamp(d))
        if T is None:
            cb.add(tkr, d, "-", "-", "-", "-", "-")
            continue
        e12 = nd.close.ewm(span=12, adjust=False).mean()
        e26 = nd.close.ewm(span=26, adjust=False).mean()
        macd = e12 - e26
        hp = (macd - macd.ewm(span=9, adjust=False).mean()).to_numpy(dtype="float64")
        tm = float(np.nanmin(hp[T - K1_W_PRIMARY: T])) if T >= K1_W_PRIMARY else None
        cb.add(tkr, d + ("  (narrative only)" if (tkr, d) == EXEMPLAR_NARRATIVE else ""),
               round(float(hp[T - 2]), 4), round(float(hp[T - 1]), 4), round(float(hp[T]), 4),
               None if tm is None else round(tm, 4),
               "-" if tm is None else ("ABOVE (off the low)" if hp[T] > tm
                                       else "AT/BELOW (fresh low)"))
    cb.emit()

    concluded = _utc()
    vault.unseal()
    ob = Table("RC.g5.ordering", "ORDERING PROOF — G5 concluded before outcomes were readable",
               ["event", "wall clock (UTC)", "monotonic offset (s)"],
               "The outcome columns are physically sealed inside OutcomeVault until the "
               "unseal below; any earlier read raises OutcomeSealError. This table is the "
               "receipt that the sequence in the code is the sequence that ran.")
    ob.add("outcome columns SEALED at load", vault.sealed_at, 0.0)
    ob.add("G5 exemplar gate started", started, round(t_start - t_start, 4))
    ob.add("G5 exemplar gate concluded", concluded, round(time.perf_counter() - t_start, 4))
    ob.add("outcome columns UNSEALED", vault.unsealed_at,
           round(time.perf_counter() - t_start, 4))
    ob.add("outcome reads before unseal", "0 (enforced — OutcomeSealError)", "-")
    ob.emit()
    return verdicts, {"started": started, "concluded": concluded,
                      "unsealed": vault.unsealed_at,
                      "reads_before_unseal": 0}


# ---------------------------------------------------------------- coverage (lens geometry)
def coverage_table(frame: pd.DataFrame, nds: dict[str, NameCurv],
                   flags: dict[str, np.ndarray]) -> dict:
    """Coverage is LENS GEOMETRY, not tape — it is what the form sees, not what happened.

    Printed for every form including the G5-disqualified ones: it reads no outcome column,
    and G1's floor (>=5%) is the named R4b trap (the killed strict form fired at 0.9%).
    """
    tb = Table("RC.coverage", "COVERAGE per form on its PRE-DECLARED primary cell (charter G1)",
               ["form", "TRUE n", "frame n", "coverage%", "unavailable", "names w/ a fire",
                "G1 (>=5%)"],
               f"Frame = the R4b frame (full_window & non-addon). Floor {G1_COVERAGE_MIN:.0%}; "
               "below it a form is disclosure-tier only, whatever its point estimate.")
    out = {}
    n = len(frame)
    for f in FORMS:
        v = flags[f]
        avail = ~pd.isna(v)
        tr = np.array([bool(x) for x in np.where(avail, v, False)], dtype=bool)
        cov = tr.sum() / n if n else None
        names = int(pd.Series(frame["ticker"].to_numpy()[tr]).nunique()) if tr.any() else 0
        tb.add(f, int(tr.sum()), n, pct(cov), int((~avail).sum()), names,
               "PASS" if (cov or 0) >= G1_COVERAGE_MIN else "FAIL (rare-lens tier)")
        out[f] = {"true_n": int(tr.sum()), "frame_n": n, "coverage": cov,
                  "unavailable": int((~avail).sum()), "names": names,
                  "g1_pass": bool((cov or 0) >= G1_COVERAGE_MIN)}
    tb.emit()
    return out


# ---------------------------------------------------------------- primary outcome (G5 survivors)
def primary_table(frame: pd.DataFrame, fpos: np.ndarray, flags: dict[str, np.ndarray],
                  vault: OutcomeVault, eligible: list[str]) -> dict:
    """Charter §3 primary: low-marking rate of curvature-TRUE confirms, with every control.

    Rows are emitted ONLY for forms that cleared G5. A disqualified form's row is its G5
    verdict; printing an outcome row for it would be exactly the ex-ante violation the
    charter's §1 exists to prevent.
    """
    near = vault.get("near_low_stop", fpos)
    tick = frame["ticker"].to_numpy()
    months = frame["date"].dt.to_period("M").astype(str).to_numpy()
    is_stld = (tick == STLD)
    half = frame["date"].median()
    first_half = (frame["date"] <= half).to_numpy()

    tb = Table("RC.primary",
               "PRIMARY — low-marking rate (+/-2 sessions of the +/-10-session local low)",
               ["form", "cohort", "n", "near-low%", "spread vs FALSE (pp)",
                "month-cluster CI 95%", "per-name-first%", "names",
                "1st half spread (pp)", "2nd half spread (pp)", "STLD-excluded spread (pp)"],
               f"Base {BASE_PUBLISHED:.1%} / random-session null {NULL_PUBLISHED:.1%} (parent "
               "R4/R9f). The estimand is TRUE minus FALSE — the same quantity the killed "
               "strict form scored −11.4pp [−19.2,−2.8] on. STLD-excluded column is "
               "disclosure (3 events in 12,940 whose outcomes are already public), not "
               "protection.")
    out = {}
    for f in eligible:
        v = flags[f]
        avail = ~pd.isna(v)
        tr = np.where(avail, v, False).astype(bool)
        fa = avail & ~tr
        r_t, r_f = rate(near[tr]), rate(near[fa])
        spread = None if (r_t is None or r_f is None) else (r_t - r_f) * 100
        lo, hi = month_cluster_ci(months, np.where(avail, tr, np.nan), near)
        pnf, nnames = per_name_first(tick, np.where(avail, tr, np.nan), near)

        def _sp(mask):
            a, b = rate(near[tr & mask]), rate(near[fa & mask])
            return None if (a is None or b is None) else (a - b) * 100

        sp_ex = _sp(~is_stld)
        tb.add(f, "TRUE", int(tr.sum()), pct(r_t), None if spread is None else round(spread, 2),
               "-" if lo is None else f"[{lo:+.1f}, {hi:+.1f}]",
               pct(pnf), nnames,
               None if _sp(first_half) is None else round(_sp(first_half), 2),
               None if _sp(~first_half) is None else round(_sp(~first_half), 2),
               None if sp_ex is None else round(sp_ex, 2))
        tb.add(f, "FALSE", int(fa.sum()), pct(r_f), "-", "-",
               pct(per_name_first(tick, np.where(avail, fa, np.nan), near)[0]),
               per_name_first(tick, np.where(avail, fa, np.nan), near)[1], "-", "-", "-")
        out[f] = {"true_n": int(tr.sum()), "false_n": int(fa.sum()),
                  "near_true": r_t, "near_false": r_f, "spread_pp": spread,
                  "ci_lo_pp": lo, "ci_hi_pp": hi, "per_name_first_true": pnf,
                  "half1_spread_pp": _sp(first_half), "half2_spread_pp": _sp(~first_half),
                  "stld_excluded_spread_pp": sp_ex}
    if not eligible:
        tb.add("(none)", "-", 0, "-", "-", "-", "-", 0, "-", "-", "-")
    tb.emit()
    return out


def window_grid_table(frame: pd.DataFrame, nds: dict[str, NameCurv],
                      flags: dict[str, np.ndarray], eligible: list[str]) -> dict:
    """R9f-style window-grid sensitivity: +/-5 / +/-10 / +/-15, recomputed from bars."""
    tb = Table("RC.windowgrid", "WINDOW-GRID sensitivity on the primary metric (R9f style)",
               ["form", "window", "TRUE near-low%", "FALSE near-low%", "spread (pp)", "n TRUE"],
               "Recomputed from the price frames, not read off a stored column, so the "
               "+/-5 and +/-15 windows are real re-measurements.")
    out = {}
    positions = []
    for r in frame.itertuples(index=False):
        nd = nds.get(r.ticker)
        positions.append(None if nd is None else nd.pos.get(pd.Timestamp(r.date)))
    for f in eligible:
        v = flags[f]
        out[f] = {}
        for win in NEAR_WIN_GRID:
            hits_t, hits_f = [], []
            for i, (r, T) in enumerate(zip(frame.itertuples(index=False), positions)):
                if T is None or v[i] is None:
                    continue
                nl = nds[r.ticker].near_low(T, win, NEAR_TOL_PRIMARY)
                if nl is None:
                    continue
                (hits_t if bool(v[i]) else hits_f).append(nl)
            rt, rf = rate(hits_t), rate(hits_f)
            sp = None if (rt is None or rf is None) else (rt - rf) * 100
            tb.add(f, f"+/-{win}", pct(rt), pct(rf), None if sp is None else round(sp, 2),
                   len(hits_t))
            out[f][f"win{win}"] = {"true": rt, "false": rf, "spread_pp": sp,
                                   "n_true": len(hits_t)}
    if not eligible:
        tb.add("(none)", "-", "-", "-", "-", 0)
    tb.emit()
    return out


def forward_table(fpos: np.ndarray, flags: dict[str, np.ndarray], vault: OutcomeVault,
                  eligible: list[str]) -> dict:
    """Charter §3 secondary — forward tape as MOVE CAPTURED, never as 'safety' (R8b framing).

    R8b already proved that waiting changes stop-out rates by ZERO under the fire's own
    risk contract, so nothing here may be phrased as a safety claim; these are move medians.
    """
    f10 = vault.get("fwd10", fpos)
    f21 = vault.get("fwd21", fpos)
    tb = Table("RC.forward", "SECONDARY — forward tape after confirm (MOVE captured, not safety)",
               ["form", "cohort", "n", "median fwd10", "IQR fwd10", "median fwd21",
                "IQR fwd21", "G4 (median fwd10 >= +2%)"],
               "Framed per R8b: these are MOVE medians. Waiting was already shown to change "
               "stop-out rates by zero under the fire's own risk contract — no safety claim "
               "is available from this table.")
    out = {}
    for f in eligible:
        v = flags[f]
        avail = ~pd.isna(v)
        tr = np.where(avail, v, False).astype(bool)
        fa = avail & ~tr
        for label, m in (("TRUE", tr), ("FALSE", fa)):
            q1, q3 = iqr(f10[m])
            q1b, q3b = iqr(f21[m])
            g4 = (med(f10[m]) or -1) >= G4_FWD10_MIN
            tb.add(f, label, int(m.sum()), med(f10[m]),
                   "-" if q1 is None else f"[{q1:+.3f}, {q3:+.3f}]", med(f21[m]),
                   "-" if q1b is None else f"[{q1b:+.3f}, {q3b:+.3f}]",
                   ("PASS" if g4 else "FAIL") if label == "TRUE" else "-")
            if label == "TRUE":
                out[f] = {"median_fwd10": med(f10[m]), "median_fwd21": med(f21[m]),
                          "iqr10": [q1, q3], "iqr21": [q1b, q3b], "g4_pass": bool(g4),
                          "n": int(m.sum())}
    if not eligible:
        tb.add("(none)", "-", 0, "-", "-", "-", "-", "-")
    tb.emit()
    return out


# ---------------------------------------------------------------- RC.r9d (gate 3)
def synth_triggers(nd: NameCurv, kind: str) -> list[int]:
    """Risk-equalized synthetic stop triggers whose WIDTH does not depend on swing structure.

    The structure stop's distance is set by wherever the last confirmed swing low happens to
    sit, so a curvature cohort with systematically different stop distance would post a
    different low-marking rate for pure geometry reasons. These triggers hold the width
    fixed instead — in percent (lens A) or in volatility units (lens B) — off the trailing
    ``ALT_ANCHOR_WIN``-session max close. The anchor is this study's translation of the
    parent's entry-anchored ALT_STOP_FIX / ALT_STOP_ATR onto an entry-free frame; it is a
    disclosed choice, not a charter term.
    """
    c = nd.c
    n = len(c)
    if n < ALT_ANCHOR_WIN + 2:
        return []
    anchor = pd.Series(c).rolling(ALT_ANCHOR_WIN).max().to_numpy()
    if kind == "fix8":
        level = anchor * (1.0 - ALT_STOP_FIX)
    else:
        level = anchor - ALT_STOP_ATR * nd.atr14
    fires, last = [], -10 ** 9
    for t in range(ALT_ANCHOR_WIN, n):
        if not np.isfinite(level[t]) or not np.isfinite(c[t]):
            continue
        if c[t] < level[t] and (t - last) >= ALT_DEDUP:
            fires.append(t)
            last = t
    return fires


def r9d_battery(frame: pd.DataFrame, fpos: np.ndarray, nds: dict[str, NameCurv],
                flags: dict[str, np.ndarray], vault: OutcomeVault,
                forms_to_test: list[str], label: str) -> dict:
    """Charter §4.2 — "the verdict lives here". All three lenses, always.

    A lift that dies under risk-equalization is stop-width arithmetic and is PRINTED as
    such. Lenses A and B replace the structure trigger with a fixed-width one and re-read
    the same primary metric; lens C keeps the real events and holds break depth fixed
    within quintiles (the parent's ``within_quintile_spread``, re-pointed at this metric).
    """
    near = vault.get("near_low_stop", fpos)
    tb = Table(f"RC.r9d{label}",
               f"RISK-EQUALIZATION BATTERY ({'G5 survivors' if label == '' else label.strip('.')}) "
               "— charter §4.2 / parent R9d",
               ["form", "lens", "TRUE near-low%", "FALSE near-low%", "spread (pp)",
                "n TRUE", "vs raw spread", "reads as"],
               f"Lens A = fixed −{ALT_STOP_FIX:.0%} off the trailing {ALT_ANCHOR_WIN}-session "
               f"max close; lens B = same anchor − {ALT_STOP_ATR}×ATR14; lens C = the real "
               "structure stops, split within break-depth quintiles. A sign flip or a "
               "collapse to under half the raw lift is stop-width arithmetic, named as such.")
    out: dict[str, dict] = {}

    # ---- raw spread on the structure frame, for the retention comparison ----
    raw: dict[str, float | None] = {}
    for f in forms_to_test:
        v = flags[f]
        avail = ~pd.isna(v)
        tr = np.where(avail, v, False).astype(bool)
        fa = avail & ~tr
        a, b = rate(near[tr]), rate(near[fa])
        raw[f] = None if (a is None or b is None) else (a - b) * 100

    for f in forms_to_test:
        v = flags[f]
        avail = ~pd.isna(v)
        tr = np.where(avail, v, False).astype(bool)
        tb.add(f, "RAW (the real structure stops — the retention denominator)",
               pct(rate(near[tr])), pct(rate(near[avail & ~tr])),
               None if raw[f] is None else round(raw[f], 2), int(tr.sum()), "1.00x",
               "baseline")

    # ---- lenses A/B: synthetic fixed-width triggers, curvature evaluated at the trigger ----
    panel = sorted(set(frame["ticker"].tolist()))
    for kind, lens in (("fix8", f"A fixed −{ALT_STOP_FIX:.0%}"),
                       ("atr2", f"B {ALT_STOP_ATR}×ATR")):
        cohorts: dict[str, tuple[list, list]] = {f: ([], []) for f in forms_to_test}
        n_events = 0
        for t in panel:
            nd = nds.get(t)
            if nd is None:
                continue
            for T in synth_triggers(nd, kind):
                nl = nd.near_low(T, NEAR_WIN_PRIMARY, NEAR_TOL_PRIMARY)
                if nl is None:
                    continue
                n_events += 1
                for f in forms_to_test:
                    val = nd.form(f, T)
                    if val is None:
                        continue
                    cohorts[f][0 if val else 1].append(nl)
        for f in forms_to_test:
            tl, fl = cohorts[f]
            rt, rf = rate(tl), rate(fl)
            sp = None if (rt is None or rf is None) else (rt - rf) * 100
            out.setdefault(f, {})[kind] = {"true": rt, "false": rf, "spread_pp": sp,
                                           "n_true": len(tl), "n_events": n_events}
            tb.add(f, f"{lens}  (n={n_events} synthetic)", pct(rt), pct(rf),
                   None if sp is None else round(sp, 2), len(tl),
                   _retention(raw[f], sp), _reads_as(raw[f], sp))

    # ---- lens C: real events, break depth held fixed within quintiles ----
    depth = (frame["close"].to_numpy() / frame["stop_level"].to_numpy()) - 1.0
    try:
        qs = pd.qcut(pd.Series(depth), QUINTILES, labels=False, duplicates="drop").to_numpy()
    except Exception:
        qs = np.full(len(depth), np.nan)
    for f in forms_to_test:
        v = flags[f]
        avail = ~pd.isna(v)
        tr = np.where(avail, v, False).astype(bool)
        fa = avail & ~tr
        sps, used = [], 0
        for qi in sorted(set(x for x in qs if not pd.isna(x))):
            m = (qs == qi)
            a, b = rate(near[tr & m]), rate(near[fa & m])
            if a is None or b is None:
                continue
            if int((tr & m).sum()) < MIN_CELL_N // 2 or int((fa & m).sum()) < MIN_CELL_N // 2:
                continue
            sps.append((a - b) * 100)
            used += 1
        sp = float(np.mean(sps)) if sps else None
        out.setdefault(f, {})["quintile"] = {"spread_pp": sp, "quintiles_used": used}
        tb.add(f, f"C break-depth quintiles ({used}/{QUINTILES} usable)", "-", "-",
               None if sp is None else round(sp, 2), int(tr.sum()),
               _retention(raw[f], sp), _reads_as(raw[f], sp))
    if not forms_to_test:
        tb.add("(none)", "-", "-", "-", "-", 0, "-", "-")
    tb.emit()
    for f in forms_to_test:
        out.setdefault(f, {})["raw_spread_pp"] = raw[f]
    return out


def _retention(raw: float | None, alt: float | None) -> str:
    if raw is None or alt is None or raw == 0:
        return "-"
    return f"{alt / raw:+.2f}x"


def _reads_as(raw: float | None, alt: float | None) -> str:
    if raw is None or alt is None:
        return "-"
    if raw == 0:
        return "no raw lift to retain"
    if np.sign(alt) != np.sign(raw):
        return "SIGN FLIP — stop-width arithmetic"
    if abs(alt) < abs(raw) * G3_LIFT_RETAINED:
        return "COLLAPSES (<half retained) — stop-width arithmetic"
    return "survives this lens"


# ---------------------------------------------------------------- gates
def gates_table(cov: dict, prim: dict, fwd: dict, r9d: dict, g5: dict) -> dict:
    tb = Table("RC.gates", "PROMOTION GATES per form (charter §5) — judged on the "
                           "PRE-DECLARED primary cell, never a scanned max",
               ["form", "G5 exemplar", "G1 coverage", "G2 lift+CI", "G3 risk-equalization",
                "G4 fwd tape", "VERDICT"],
               "G5 is evaluated FIRST and gates the rest: a form disqualified ex ante gets "
               "no outcome row, so G2/G3/G4 are NOT EVALUATED for it — that is the charter's "
               "design, not missing work.")
    out = {}
    for f in FORMS:
        g5p = g5[f]["pass"]
        c = cov[f]
        g1 = ("PASS" if c["g1_pass"]
              else f"FAIL ({(c['coverage'] or 0):.1%} < {G1_COVERAGE_MIN:.0%})")
        if not g5p:
            tb.add(f, "FAIL", g1, "not evaluated", "not evaluated", "not evaluated",
                   "DISQUALIFIED ex ante (G5)")
            out[f] = {"g5": False, "g1": c["g1_pass"], "g2": None, "g3": None, "g4": None,
                      "verdict": "DISQUALIFIED_EX_ANTE_G5"}
            continue
        p = prim.get(f, {})
        sp, lo = p.get("spread_pp"), p.get("ci_lo_pp")
        g2 = bool(sp is not None and sp >= G2_LIFT_MIN_PP
                  and lo is not None and lo > G2_CI_LOWER_MIN_PP)
        rr = r9d.get(f, {})
        raw = rr.get("raw_spread_pp")
        lens_ok = []
        for k in ("fix8", "atr2", "quintile"):
            a = (rr.get(k) or {}).get("spread_pp")
            lens_ok.append(bool(raw and a is not None and np.sign(a) == np.sign(raw)
                                and abs(a) >= abs(raw) * G3_LIFT_RETAINED))
        g3 = all(lens_ok)
        g4 = bool(fwd.get(f, {}).get("g4_pass"))
        verdict = "PROMOTION-ELIGIBLE (gauntlet only)" if (g5p and c["g1_pass"] and g2 and g3
                                                           and g4) else "FAIL — ore ledger row"
        tb.add(f, "PASS", g1,
               f"{'PASS' if g2 else 'FAIL'} ({sp:+.1f}pp, CI lo {lo:+.1f}pp)"
               if sp is not None and lo is not None else "FAIL (no estimate)",
               f"{'PASS' if g3 else 'FAIL'} ({sum(lens_ok)}/3 lenses)",
               "PASS" if g4 else "FAIL", verdict)
        out[f] = {"g5": True, "g1": c["g1_pass"], "g2": g2, "g3": g3, "g4": g4,
                  "lens_ok": lens_ok, "verdict": verdict}
    tb.emit()
    return out


def substrate_table() -> None:
    tb = Table("RC.substrate", "SUBSTRATE BOUNDS restated (parent N4–N6) — no silent re-windowing",
               ["bound", "value"],
               "Restated verbatim from the parent artifact. This study re-windows nothing.")
    tb.add("price window", SUBSTRATE["price_window"])
    tb.add("pre-store events dropped (C0)", f"{SUBSTRATE['store_events_dropped_C0']:,}")
    tb.add("pre-store events dropped (C2)", f"{SUBSTRATE['store_events_dropped_C2']:,}")
    tb.add("disposition of dropped events", SUBSTRATE["dropped_disposition"])
    tb.add("exposure (name-years)", f"{SUBSTRATE['exposure_name_years']:.1f}")
    tb.add("survivorship", SUBSTRATE["survivorship"])
    tb.add("breadth bound", SUBSTRATE["breadth"])
    tb.add("3D anchor era", SUBSTRATE["anchor_era"])
    tb.emit()


def sensitivity_grids(frame: pd.DataFrame, nds: dict[str, NameCurv],
                      positions: list[int | None]) -> dict:
    """Charter §2/§4.4: the full parameter grid, COVERAGE ONLY for disqualified forms.

    Grids are sensitivity-only and are printed in full so the primary cell cannot be
    mistaken for a chosen one. For forms disqualified at G5 this prints lens geometry
    (how often each cell fires, and whether it covers the exemplars) and no outcome.
    """
    tb = Table("RC.grid", "PARAMETER GRIDS (sensitivity only — no cell is promotable)",
               ["form", "cell", "primary?", "TRUE n", "coverage%"]
               + [f"covers {d}" for _, d in EXEMPLARS]
               + [f"fires {EXEMPLAR_NARRATIVE[1]} (narrative)"],
               "Printed in full per charter §4.4. Promotion is judged on the pre-declared "
               "primary cell; no scanned maximum is eligible for anything. The narrative "
               "column is disclosure: charter §1 tunes NO lens to reject Jun-18, so a cell "
               "firing there decides nothing — it is printed because a reviewer will look "
               "for it and it should not have to be recomputed by hand.")
    out: dict[str, dict] = {}
    cells: list[tuple[str, str, bool, object]] = []
    for w in K1_W_GRID:
        cells.append(("K1", f"w={w}", w == K1_W_PRIMARY, ("k1", {"w": w})))
    for m in K2_M_GRID:
        cells.append(("K2", f"m={m}", m == K2_M_PRIMARY, ("k2", {"m": m})))
    for m in K2_M_GRID:                 # the disclosed wording ambiguity, both ways
        cells.append(("K2", f"m={m} (tight reading: m BARS, not m diffs)", False,
                      ("k2", {"m": m, "tight": True})))
    for th, w in K3_GRID:
        cells.append(("K3", f"θ={th}, w={w}", (th, w) == K3_PRIMARY, ("k3", {"theta": th, "w": w})))
    cells.append(("K4", "session-anchored", True, ("k4", {})))
    cells.append(("K4", "first-timestamp phased (defect mimic)", False, ("k4ph", {})))
    cells.append(("K5", f"K1(w={K1_W_PRIMARY}) OR K4", True, ("k5", {})))

    for fam, cell, is_primary, (fn, kw) in cells:
        n_true = 0
        n_avail = 0
        for r, T in zip(frame.itertuples(index=False), positions):
            nd = nds.get(r.ticker)
            if nd is None or T is None:
                continue
            val = (bool(nd.m3_ph[T]) if fn == "k4ph" else getattr(nd, fn)(T, **kw))
            if val is None:
                continue
            n_avail += 1
            n_true += int(bool(val))
        ex = []
        for tkr, d in list(EXEMPLARS) + [EXEMPLAR_NARRATIVE]:
            nd = nds.get(tkr)
            T = None if nd is None else nd.pos.get(pd.Timestamp(d))
            ex.append(None if T is None else
                      (bool(nd.m3_ph[T]) if fn == "k4ph" else getattr(nd, fn)(T, **kw)))
        cov = n_true / len(frame) if len(frame) else None
        tb.add(fam, cell, "PRIMARY" if is_primary else "", n_true, pct(cov),
               *["-" if v is None else ("TRUE" if v else "FALSE") for v in ex])
        out.setdefault(fam, {})[cell] = {
            "true_n": n_true, "avail_n": n_avail, "coverage": cov, "primary": is_primary,
            "exemplars": {d: ex[i] for i, (_, d) in enumerate(EXEMPLARS)},
            "narrative_exemplar": {EXEMPLAR_NARRATIVE[1]: ex[-1]}}
    tb.emit()
    return out


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stops", default=str(Path(__file__).resolve().parent
                                           / "early_admission_bakeoff_stops.parquet"))
    ap.add_argument("--price-root", default=DEF_PRICE_ROOT)
    ap.add_argument("--stocks-root", default=DEF_STOCKS_ROOT)
    ap.add_argument("--pit-sample", type=int, default=0,
                    help="rows in the PIT truncation leg; 0 = ALL rows (default)")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent
                                         / "stop_curvature_study_results.json"))
    args = ap.parse_args()

    started = _utc()
    print("=" * 100)
    print("STOP-CURVATURE CONTEXT STUDY — charter STOP_CURVATURE_CHARTER_2026-08-11.md")
    print(f"started {started}   seed {CURV_SEED}   anchor era {ANCHOR_ERA}")
    print("=" * 100, flush=True)

    stops = pd.read_parquet(args.stops)
    stops["date"] = pd.to_datetime(stops["date"])
    print(f"stops frame: {len(stops):,} confirms, {stops['ticker'].nunique()} names, "
          f"{stops['date'].min().date()} -> {stops['date'].max().date()}", flush=True)

    # The outcome columns are REMOVED from the frame and put behind the seal before
    # anything else touches it — see OutcomeVault.seal for why this is structural.
    stops, vault = OutcomeVault.seal(stops)

    tickers = sorted(set(stops["ticker"].tolist()))
    print(f"building {len(tickers)} name frames from {args.price_root} ...", flush=True)
    nds, missing = build_names(tickers, Path(args.price_root), Path(args.stocks_root))
    if missing:
        note(f"{len(missing)} ticker(s) had no price frame and are unresolved: {missing[:10]}")

    # ---- RC.parity: BLOCKING ----
    ok, parity = parity_gate(stops, nds)
    if not ok:
        print("\n::error title=stop-curvature-parity::PARITY GATE FAILED — recomputed "
              "histogram does not reproduce the stored hist_rising column. Study ABORTED; "
              "no table is trustworthy on a divergent series.", flush=True)
        Path(args.out).write_text(json.dumps(
            {"aborted": "parity", "parity": parity, "tables": TABLES}, indent=1, default=str))
        return 3
    print("\nPARITY GATE: PASS — recomputed histogram reproduces hist_rising on all "
          f"{parity['hist_match']:,}/{parity['rows']:,} rows.", flush=True)

    # ---- RC.pit: BLOCKING ----
    ok, pit = pit_leak_test(stops, nds, args.pit_sample)
    if not ok:
        print("\n::error title=stop-curvature-pit::PIT LEAK TEST FAILED — a feature input "
              "resolves past the confirm-bar close. Study ABORTED.", flush=True)
        Path(args.out).write_text(json.dumps(
            {"aborted": "pit", "parity": parity, "pit": pit, "tables": TABLES},
            indent=1, default=str))
        return 4

    # ---- frame selection (STRUCTURAL — full_window/addon are not outcome columns) ----
    keep = (stops["full_window"] & ~stops["addon"]).to_numpy()
    fpos = np.flatnonzero(keep)
    frame = stops[keep].reset_index(drop=True)

    positions = []
    for r in frame.itertuples(index=False):
        nd = nds.get(r.ticker)
        positions.append(None if nd is None else nd.pos.get(pd.Timestamp(r.date)))

    # ---- the five forms, on their pre-declared primary cells ----
    flags: dict[str, np.ndarray] = {}
    for f in FORMS:
        vals = []
        for r, T in zip(frame.itertuples(index=False), positions):
            nd = nds.get(r.ticker)
            vals.append(None if (nd is None or T is None) else nd.form(f, T))
        flags[f] = np.array(vals, dtype=object)

    # ---- G5 FIRST. Outcomes are sealed until this returns. ----
    g5, ordering = g5_exemplar_gate(nds, vault)
    eligible = [f for f in FORMS if g5[f]["pass"]]
    if not eligible:
        note("NO enumerated form cleared G5. Per charter §1 every form is disqualified ex "
             "ante and no outcome row is read for any of them — the family's row in the ore "
             "ledger is a DEFINITION-VALIDITY null, not a tape null.")

    # ---- frame reconciliation: the base rate IS an outcome, so it prints only now ----
    fb = Table("RC.frame", "FRAME reconciliation (charter §3) — nothing silently re-windowed",
               ["frame", "n", "names", "near-low% (base)", "used for"],
               "The R4b frame (full_window & non-addon) is the frame the parent's 34.9% base, "
               "its month-cluster CIs and its 110/12,786 strict-form coverage were all read "
               "on. The wider 12,940 row set is printed beside it so the choice is visible. "
               "This table emits AFTER G5 because a base rate is an outcome read like any "
               "other — it is served through the same seal.")
    fb.add("all replayed confirms", len(stops), int(stops["ticker"].nunique()),
           pct(float(np.mean(vault.get("near_low_stop")))), "disclosure")
    fb.add("R4b frame: full_window & non-addon", len(frame), int(frame["ticker"].nunique()),
           pct(float(np.mean(vault.get("near_low_stop", fpos)))),
           "PRIMARY — every gate is read here")
    fb.emit()

    substrate_table()
    cov = coverage_table(frame, nds, flags)
    grids = sensitivity_grids(frame, nds, positions)

    prim = primary_table(frame, fpos, flags, vault, eligible)
    wgrid = window_grid_table(frame, nds, flags, eligible)
    fwd = forward_table(fpos, flags, vault, eligible)
    r9d = r9d_battery(frame, fpos, nds, flags, vault, eligible, "")

    # The battery is charter §4.2's "the verdict lives here" — it must be shown to WORK even
    # when no new form survives to be tested by it. Run it on the parent's ALREADY-PUBLISHED
    # strict split (R4b hist_rising), which is not a new form and auditions nothing.
    ctrl = {}
    if not eligible:
        note("Running the R9d battery on the parent's already-published R4b strict split "
             "(hist_rising) as machinery validation. That lens' outcome is already public "
             "(23.6% vs 35.0%, −11.4pp) — re-reading it auditions no new construction.")
        ctrl_flags = {CONTROL_FORM: np.array(
            [bool(x) for x in frame["hist_rising"].to_numpy()], dtype=object)}
        ctrl = r9d_battery(frame, fpos, nds, ctrl_flags, vault, [CONTROL_FORM], ".control")

    gates = gates_table(cov, prim, fwd, r9d, g5)

    payload = {
        "study": "stop-curvature context study",
        "charter": "research/prophet_us_audit/STOP_CURVATURE_CHARTER_2026-08-11.md",
        "parent": "research/prophet_us_audit/EARLY_ADMISSION_BAKEOFF_2026-08-11.md",
        "started": started, "finished": _utc(), "seed": CURV_SEED,
        "anchor_era": ANCHOR_ERA,
        "price_root": args.price_root, "stocks_root": args.stocks_root,
        "frame": {"all_confirms": len(stops), "r4b_frame": len(frame),
                  "names": int(frame["ticker"].nunique()),
                  "base_near_low": float(np.mean(vault.get("near_low_stop", fpos))),
                  "base_published": BASE_PUBLISHED, "null_published": NULL_PUBLISHED},
        "substrate": SUBSTRATE,
        "parity": parity, "pit": pit, "g5": g5, "g5_ordering": ordering,
        "coverage": cov, "grids": grids, "primary": prim, "window_grid": wgrid,
        "forward": fwd, "r9d": r9d, "r9d_control": ctrl, "gates": gates,
        "eligible_forms": eligible, "notes": NOTES, "deferred": DEFERRED,
        "outcome_reads_after_unseal": vault.reads,
        "tables": TABLES,
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, default=str))
    print(f"\nfrozen tables -> {args.out}", flush=True)
    print(f"outcome column reads: {vault.reads} (all after unseal; 0 possible before)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
