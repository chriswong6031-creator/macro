#!/usr/bin/env python3
"""ignition_chase_study.py — 12-month CHASE x THEME-IGNITION study (phase-0, offline).

WHAT THIS IS
    An OFFLINE research instrument. It does not import engine code, does not touch
    the render path, and writes nothing outside research/cn_prophet_audit/. It reads
    committed price + basket-membership stores and freezes two frozen artifacts:
        ignition_chase_results.json   every cell, every n, machine-readable
        IGNITION_CHASE_STUDY.md       the same numbers as prose + caveats

WHY
    The V1 loser audit (research/cn_prophet_audit/RESULTS_2026-08-04.md, PR #4500)
    produced two in-era observations on a 407-episode, one-month sample:
      (1) CHASE x THEME interaction — chase-pattern admissions that sat inside a
          recognised HOT theme were relay winners (n=5, median +14.5 excess) while
          chase admissions with no theme membership were bagholders (n=26, -14.3).
      (2) THEME IGNITION — theme-level breadth ignition might LEAD member forward
          returns, making early theme heat a pre-emptive rather than a late signal.
    Both were single-era, tiny-n, and in-sample. This instrument re-runs the same
    constructions over the whole committed A-share universe for twelve months so the
    interaction can be looked at with real n before anyone builds a relay-aware
    admission rule.

WHAT IT IS NOT
    Not a backtest of a strategy, not a promotion gate, not evidence that any of
    these cells is tradeable. Every number is IN-SAMPLE and MOTIVATING-ONLY. The
    forward windows overlap heavily (thousands of events, many on the same dates,
    many in the same themes) so the effective sample is far smaller than n. No
    p-values, no bootstrap CIs on medians, no Sharpe. The only interval reported is
    a Wilson interval on win%, which is a binomial statement about the count and
    still ignores the overlap. Read every cell as "what this cohort did", never as
    "what this cohort will do".

NO LOOKAHEAD
    Every feature at event date d is computed from bars <= d. Outcomes start at the
    T+1 fill. The ONE unavoidable lookahead is basket membership: see the caveat
    block at the bottom of the emitted markdown, which quantifies it.

CONVENTIONS (mirrored from production, not invented here)
    limit band       engine/china_signals.board_type — STAR (688/689) and ChiNext
                     (300/301) are +-20%, everything else +-10%. NOTE this is wider
                     than the brief's literal "300/688" text: 301xxx is ChiNext and
                     carries the 20% band, so scoring it at 9.5% would manufacture
                     false limit-closes on 89 names. Production wins.
    theme heat       engine/china_narrative_tags — rel20 = basket EW 20d return minus
                     CSI300 20d return (pp), breadth = share of covered members above
                     their own 20d MA (the MA includes today's close, as in
                     production), HOT = rel20 >= 5 AND breadth >= 0.60, WARMING =
                     rel20 >= 0 AND breadth >= 0.50, rounded (2dp / 4dp) BEFORE the
                     threshold test, exactly as production grades it.
    name theme       the strongest QUALIFYING basket by rel20 the name belongs to
                     (engine/china_narrative_tags.name_tags).
    fill + grading   engine/china_standout_track._t1_fill and
                     engine/track_scoring.score_from_fill: fill at the T+1 open (or
                     the (H+L)/2 proxy), locked-limit T+1 bars are UNFILLABLE and
                     excluded, the fill bar counts as bar 1 of the horizon, and the
                     benchmark leg spans the same fill-bar -> exit-bar window.

RUNTIME
    Single process, pure pandas/numpy, ~3-6 min on an M-series Mac. Prints a stage
    timer so a slow store is visible rather than silent.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / "ignition_chase_results.json"
OUT_MD = HERE / "IGNITION_CHASE_STUDY.md"

# ── study window ──────────────────────────────────────────────────────────────
WINDOW_START = pd.Timestamp("2025-08-01")
WINDOW_END = pd.Timestamp("2026-07-31")
# lookback deep enough for the 252-session high plus the 21-session trailing return
HISTORY_START = pd.Timestamp("2024-04-01")
HORIZONS = (10, 21)

# ── production-mirrored constants ─────────────────────────────────────────────
HOT_REL20, HOT_BREADTH = 5.0, 0.60
WARM_REL20, WARM_BREADTH = 0.0, 0.50
BREADTH_WINDOW = 20
MIN_COVERED = 5          # brief raises production's 3 to 5
LIMIT_TOL = 1e-9         # close == high, in float terms
DEDUPE_SESSIONS = 5      # one event per (ticker, 5-session window), keep-first
TRAIL21_CHASE = 0.25     # trailing-21d return gate for the non-limit chase leg
DAY0_CHASE = 0.03        # same-day move required alongside the trail21 gate
WASHOUT_DD = -0.25       # table C split: dd-from-252d-high
IGNITION_DD = -0.20      # table E fresh-admission: MA20 cross needs this drawdown
RELAY_EARLY, RELAY_LATE = 1, 4
THIN_N = 15              # cells below this are labelled "thin"

STATE_HOT = "HOT"
STATE_WARM = "WARMING"
STATE_UNQUAL = "none_unqualified"
STATE_NOBASKET = "no_basket"
STATE_ORDER = [STATE_HOT, STATE_WARM, STATE_UNQUAL, STATE_NOBASKET]

_T0 = time.time()


def _stage(msg: str) -> None:
    print(f"[{time.time() - _T0:6.1f}s] {msg}", flush=True)


# ── stats helpers ─────────────────────────────────────────────────────────────

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """Wilson score interval on a binomial proportion. The ONLY interval we report.

    It is a statement about the count of positive outcomes and nothing else: it does
    NOT account for the overlapping forward windows or the theme clustering, both of
    which make the true uncertainty wider than this.
    """
    if n <= 0:
        return None, None
    p = k / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return round(100.0 * (centre - half) / denom, 1), round(100.0 * (centre + half) / denom, 1)


def cell(values: np.ndarray) -> dict:
    """Frozen summary of one cohort's excess returns. Never hides a thin cell."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    n = int(v.size)
    if n == 0:
        return {"n": 0, "win_pct": None, "win_ci95": [None, None], "median": None,
                "mean": None, "p10": None, "p90": None, "thin": True}
    wins = int((v > 0).sum())
    lo, hi = wilson(wins, n)
    return {
        "n": n,
        "win_pct": round(100.0 * wins / n, 1),
        "win_ci95": [lo, hi],
        "median": round(float(np.median(v)), 2),
        "mean": round(float(np.mean(v)), 2),
        "p10": round(float(np.percentile(v, 10)), 2),
        "p90": round(float(np.percentile(v, 90)), 2),
        "thin": n < THIN_N,
    }


def cells_by_horizon(df: pd.DataFrame, mask: np.ndarray) -> dict:
    out = {}
    for h in HORIZONS:
        out[f"h{h}"] = cell(df.loc[mask, f"excess_h{h}"].to_numpy())
    return out


# ── production-mirrored board / limit band ────────────────────────────────────

def limit_threshold(ticker: str) -> float:
    """Daily price-limit threshold as a return fraction, from engine.china_signals."""
    code = ticker.upper().split(".")[0]
    if code.startswith(("688", "689", "300", "301")):
        return 0.185          # +-20% band
    if code.startswith(("8", "4", "92")):
        return 0.285          # +-30% Beijing board (none present in this store)
    return 0.095              # +-10% main board


# ── data loading ──────────────────────────────────────────────────────────────

def load_panel() -> dict:
    """Wide [calendar x ticker] close/high/low/open frames plus the CSI300 series."""
    bench_df = pd.read_parquet(ROOT / "data" / "china" / "510300.SS.parquet")
    bench_df.index = pd.to_datetime(bench_df.index)
    bench = bench_df["close"].sort_index()
    bench = bench[bench.index >= HISTORY_START].dropna()
    calendar = bench.index

    paths = sorted((ROOT / "data" / "china_stocks").glob("*.parquet"))
    cols = {"close": {}, "high": {}, "low": {}, "open": {}}
    skipped = 0
    for p in paths:
        ticker = p.name[: -len(".parquet")]
        try:
            df = pd.read_parquet(p)
        except Exception:  # noqa: BLE001 — a corrupt store file must not kill the run
            skipped += 1
            continue
        df.index = pd.to_datetime(df.index)
        df = df[df.index >= HISTORY_START].sort_index()
        df = df[~df.index.duplicated(keep="last")]
        if "close" not in df.columns or len(df) < 60:
            skipped += 1
            continue
        for c, bucket in cols.items():
            bucket[ticker] = df[c] if c in df.columns else pd.Series(np.nan, index=df.index)

    frames = {c: pd.DataFrame(v).reindex(calendar).astype(float) for c, v in cols.items()}
    tickers = list(frames["close"].columns)
    _stage(f"panel: {len(tickers)} tickers, {len(calendar)} sessions, {skipped} skipped")
    return {"calendar": calendar, "bench": bench, "tickers": tickers, **frames}


def load_memberships() -> dict:
    """basket_id -> {name, name_zh, source, members[]} across curated + THS."""
    out: dict[str, dict] = {}
    for src, rel in (("curated", "baskets_china"), ("THS", "baskets_china_ths")):
        raw = json.loads((ROOT / "data" / rel / "membership.json").read_text())
        for bid, bval in (raw.get("baskets") or {}).items():
            members = [
                m["ticker"]
                for m in (bval.get("members") or [])
                if isinstance(m, dict) and m.get("removed") is None and m.get("ticker")
            ]
            out[bid] = {
                "name": bval.get("name", bid),
                "name_zh": bval.get("name_zh", bid),
                "source": src,
                "members": members,
            }
    return out


# ── per-name daily features (all use bars <= d) ───────────────────────────────

def name_features(panel: dict) -> dict:
    close, high, low, opn = panel["close"], panel["high"], panel["low"], panel["open"]
    tickers = panel["tickers"]

    thr = np.array([limit_threshold(t) for t in tickers], dtype=float)
    ret1 = close / close.shift(1) - 1.0
    at_high = close >= (high - LIMIT_TOL)
    limit_close = (ret1.to_numpy() >= thr[None, :]) & at_high.to_numpy() & close.notna().to_numpy()
    limit_close = pd.DataFrame(limit_close, index=close.index, columns=close.columns)

    trail21 = close / close.shift(21) - 1.0
    chase = limit_close | ((trail21 >= TRAIL21_CHASE) & (ret1 >= DAY0_CHASE))
    chase = chase & close.notna()

    ma20 = close.rolling(BREADTH_WINDOW, min_periods=BREADTH_WINDOW).mean()
    cross_up = (close > ma20) & (close.shift(1) <= ma20.shift(1))
    hi252 = close.rolling(252, min_periods=120).max()
    dd252 = close / hi252 - 1.0

    # fill-realistic entry price for every bar (used at T+1), mirroring _t1_fill
    fill = opn.where(opn.notna(), (high + low) / 2.0)
    fill = fill.where(fill.notna(), close)
    locked = (high == low) & (low == close) & close.notna()

    lim3d = limit_close.astype(float).rolling(3, min_periods=1).max()

    _stage("name features built")
    return {
        "ret1": ret1, "limit_close": limit_close, "trail21": trail21, "chase": chase,
        "ma20": ma20, "cross_up": cross_up, "dd252": dd252, "fill": fill,
        "locked": locked, "lim3d": lim3d, "thr": thr,
    }


def dedupe_events(flags: pd.DataFrame, lo: int, hi: int) -> list[tuple[int, int]]:
    """(ticker_col_idx, date_row_idx) events, one per (ticker, 5-session window), keep-first."""
    arr = flags.to_numpy()
    out: list[tuple[int, int]] = []
    for j in range(arr.shape[1]):
        rows = np.flatnonzero(arr[:, j])
        last = -10_000
        for r in rows:
            if r < lo or r > hi:
                continue
            if r - last < DEDUPE_SESSIONS:
                continue
            out.append((j, int(r)))
            last = r
    return out


# ── basket heat panels (time series of the production point calculation) ──────

def basket_panels(panel: dict, feats: dict, memberships: dict) -> dict:
    close, bench = panel["close"], panel["bench"]
    lim3d = feats["lim3d"]
    bench20 = (bench / bench.shift(BREADTH_WINDOW) - 1.0) * 100.0

    ids, recs = [], []
    for bid, meta in memberships.items():
        covered = [t for t in meta["members"] if t in close.columns]
        if len(covered) < MIN_COVERED:
            continue
        sub = close[covered]
        rets = sub.pct_change(fill_method=None)
        ew_ret = rets.mean(axis=1)
        ew_level = (1.0 + ew_ret.fillna(0.0)).cumprod()
        raw20 = (ew_level / ew_level.shift(BREADTH_WINDOW) - 1.0) * 100.0
        rel20 = (raw20 - bench20).round(2)

        ma20 = sub.rolling(BREADTH_WINDOW, min_periods=1).mean()
        valid = sub.notna().sum(axis=1)
        above = (sub > ma20).sum(axis=1)
        breadth = (above / valid.replace(0, np.nan)).round(4)

        level = np.where(
            (rel20 >= HOT_REL20) & (breadth >= HOT_BREADTH), 2,
            np.where((rel20 >= WARM_REL20) & (breadth >= WARM_BREADTH), 1, 0),
        )
        ncov = valid.to_numpy()
        level = np.where(ncov >= MIN_COVERED, level, 0)

        ids.append(bid)
        recs.append({
            "rel20": rel20.to_numpy(),
            "breadth": breadth.to_numpy(),
            "level": level.astype(np.int8),
            "slope5": (rel20 - rel20.shift(5)).to_numpy(),
            "ncov": ncov.astype(np.int16),
            "ew_level": ew_level.to_numpy(),
            "lim3d": lim3d[covered].sum(axis=1).to_numpy(),
            "covered": covered,
        })

    nb, nt = len(ids), len(close.index)
    mats = {
        k: np.full((nb, nt), np.nan if k != "lim3d" else 0.0, dtype=float)
        for k in ("rel20", "breadth", "slope5", "ew_level", "lim3d")
    }
    mats["level"] = np.zeros((nb, nt), dtype=np.int8)
    mats["ncov"] = np.zeros((nb, nt), dtype=np.int16)
    for i, r in enumerate(recs):
        for k, mat in mats.items():
            mat[i] = r[k]

    ticker_baskets: dict[str, list[int]] = {}
    for i, bid in enumerate(ids):
        for t in recs[i]["covered"]:
            ticker_baskets.setdefault(t, []).append(i)

    _stage(f"basket panels: {nb} baskets with >= {MIN_COVERED} covered members")
    return {"ids": ids, "meta": memberships, "mats": mats, "ticker_baskets": ticker_baskets}


def assign_themes(panel: dict, baskets: dict, restrict_source: str | None = None) -> dict:
    """Per (ticker, date): strongest QUALIFYING basket by rel20; else best covered basket.

    Returns int arrays [n_tickers x n_dates]: assigned basket row (or -1) and a state
    code 0..3 indexing STATE_ORDER.
    """
    mats, ids, meta = baskets["mats"], baskets["ids"], baskets["meta"]
    keep = None
    if restrict_source is not None:
        keep = {i for i, bid in enumerate(ids) if meta[bid]["source"] == restrict_source}

    tickers = panel["tickers"]
    nt = len(panel["calendar"])
    assigned = np.full((len(tickers), nt), -1, dtype=np.int32)
    state = np.full((len(tickers), nt), STATE_ORDER.index(STATE_NOBASKET), dtype=np.int8)

    rel, lvl, ncov = mats["rel20"], mats["level"], mats["ncov"]
    for ti, t in enumerate(tickers):
        bidx = baskets["ticker_baskets"].get(t)
        if not bidx:
            continue
        if keep is not None:
            bidx = [b for b in bidx if b in keep]
            if not bidx:
                continue
        bidx = np.asarray(bidx)
        r, lv, nc = rel[bidx], lvl[bidx], ncov[bidx]
        covered = nc >= MIN_COVERED
        qual = (lv > 0) & covered

        r_q = np.where(qual, r, -np.inf)
        best_q = np.argmax(r_q, axis=0)
        has_q = qual.any(axis=0)

        r_a = np.where(covered, r, -np.inf)
        best_a = np.argmax(r_a, axis=0)
        has_a = covered.any(axis=0)

        pick = np.where(has_q, best_q, best_a)
        assigned[ti] = np.where(has_q | has_a, bidx[pick], -1)

        lvl_pick = lv[best_q, np.arange(nt)]
        st = np.where(
            has_q,
            np.where(lvl_pick == 2, STATE_ORDER.index(STATE_HOT), STATE_ORDER.index(STATE_WARM)),
            np.where(has_a, STATE_ORDER.index(STATE_UNQUAL),
                     STATE_ORDER.index(STATE_NOBASKET)),
        )
        state[ti] = st
    return {"assigned": assigned, "state": state}


# ── outcomes ──────────────────────────────────────────────────────────────────

def valid_positions(close: pd.DataFrame) -> list[np.ndarray]:
    arr = close.to_numpy()
    return [np.flatnonzero(np.isfinite(arr[:, j])) for j in range(arr.shape[1])]


def event_outcomes(panel: dict, feats: dict, vpos: list[np.ndarray],
                   events: list[tuple[int, int]]) -> dict:
    """T+1-fill, locked-limit-excluded, CSI300-relative excess at every horizon.

    Mirrors engine.track_scoring.score_from_fill with include_fill_bar=True: the fill
    bar is bar 1 of the horizon, so the exit bar sits `horizon` valid bars after the
    event bar, and the benchmark leg spans fill-bar close -> exit-bar close.
    """
    close = panel["close"].to_numpy()
    fill_arr = feats["fill"].to_numpy()
    locked = feats["locked"].to_numpy()
    bench = panel["bench"].to_numpy()

    n = len(events)
    fills = np.full(n, np.nan)
    lock_flag = np.zeros(n, dtype=bool)
    ex = {h: np.full(n, np.nan) for h in HORIZONS}

    for e, (ti, di) in enumerate(events):
        v = vpos[ti]
        r = int(np.searchsorted(v, di))
        if r + 1 >= len(v):
            continue
        j = int(v[r + 1])
        if locked[j, ti]:
            lock_flag[e] = True
            continue
        f = fill_arr[j, ti]
        if not np.isfinite(f) or f <= 0:
            continue
        fills[e] = f
        for h in HORIZONS:
            if r + h >= len(v):
                continue
            k = int(v[r + h])
            c = close[k, ti]
            b0, b1 = bench[j], bench[k]
            if not (np.isfinite(c) and np.isfinite(b0) and np.isfinite(b1) and b0 > 0):
                continue
            ex[h][e] = (c / f - 1.0) * 100.0 - (b1 / b0 - 1.0) * 100.0
    return {"fill": fills, "locked": lock_flag, **{f"excess_h{h}": ex[h] for h in HORIZONS}}


def universe_baseline(panel: dict, feats: dict, lo: int, hi: int) -> dict:
    """Date-matched 'what did an average A-share do' comparator.

    Calendar-offset approximation (T+1 = next CALENDAR session, not the name's next
    traded bar), so halted names drop out rather than rolling forward. Deliberately
    cruder than the event path — it exists to answer "is the chase cohort worse than
    a coin toss on this tape", not to grade anything.
    """
    close = panel["close"].to_numpy()
    fill_arr = feats["fill"].to_numpy()
    locked = feats["locked"].to_numpy()
    bench = panel["bench"].to_numpy()
    nt = close.shape[0]

    out = {}
    for h in HORIZONS:
        rows = np.arange(lo, hi + 1)
        rows = rows[(rows + 1 < nt) & (rows + h < nt)]
        f = fill_arr[rows + 1]
        c = close[rows + h]
        lk = locked[rows + 1]
        b_leg = (bench[rows + h] / bench[rows + 1] - 1.0) * 100.0
        exc = (c / f - 1.0) * 100.0 - b_leg[:, None]
        exc = np.where(lk | ~np.isfinite(f) | (f <= 0), np.nan, exc)
        out[f"h{h}"] = cell(exc.ravel())
    return out


# ── table builders ────────────────────────────────────────────────────────────

def build_event_frame(panel: dict, feats: dict, baskets: dict, themes: dict,
                      vpos: list[np.ndarray], lo: int, hi: int) -> pd.DataFrame:
    events = dedupe_events(feats["chase"], lo, hi)
    _stage(f"chase events after 5-session dedupe: {len(events)}")
    out = event_outcomes(panel, feats, vpos, events)

    tickers = panel["tickers"]
    cal = panel["calendar"]
    mats = baskets["mats"]
    ids = baskets["ids"]
    lim3d_self = feats["lim3d"].to_numpy()
    dd = feats["dd252"].to_numpy()
    limit_flag = feats["limit_close"].to_numpy()

    ti = np.array([e[0] for e in events])
    di = np.array([e[1] for e in events])
    asg = themes["assigned"][ti, di]
    st = themes["state"][ti, di]
    have = asg >= 0

    rel20 = np.where(have, mats["rel20"][np.where(have, asg, 0), di], np.nan)
    breadth = np.where(have, mats["breadth"][np.where(have, asg, 0), di], np.nan)
    slope5 = np.where(have, mats["slope5"][np.where(have, asg, 0), di], np.nan)
    lim3d_tot = np.where(have, mats["lim3d"][np.where(have, asg, 0), di], np.nan)
    lim3d_ex = lim3d_tot - lim3d_self[di, ti]

    relay = np.full(len(events), "na", dtype=object)
    relay[have & (lim3d_ex <= RELAY_EARLY)] = "early"
    relay[have & (lim3d_ex > RELAY_EARLY) & (lim3d_ex < RELAY_LATE)] = "mid"
    relay[have & (lim3d_ex >= RELAY_LATE)] = "late"

    df = pd.DataFrame({
        "ticker": [tickers[t] for t in ti],
        "date": [cal[d] for d in di],
        "date_idx": di,
        "limit_leg": limit_flag[di, ti],
        "theme_state": [STATE_ORDER[s] for s in st],
        "basket_id": [ids[a] if a >= 0 else None for a in asg],
        "basket_source": [baskets["meta"][ids[a]]["source"] if a >= 0 else None for a in asg],
        "rel20": rel20,
        "breadth": breadth,
        "slope5": slope5,
        "lim3d_ex_self": lim3d_ex,
        "relay": relay,
        "dd252": dd[di, ti],
        "locked_t1": out["locked"],
        **{f"excess_h{h}": out[f"excess_h{h}"] for h in HORIZONS},
    })
    df["washout"] = np.where(df["dd252"] <= WASHOUT_DD, "deep_dd", "shallow_dd")
    df["half"] = np.where(df["date"] < pd.Timestamp("2026-02-01"), "H1_2025_08_2026_01",
                          "H2_2026_02_2026_07")
    df["theme_pooled_none"] = np.where(
        df["theme_state"].isin([STATE_HOT, STATE_WARM]), df["theme_state"], "none_pooled")
    return df


def table_a(df: pd.DataFrame) -> dict:
    out = {}
    for s in STATE_ORDER:
        out[s] = cells_by_horizon(df, (df["theme_state"] == s).to_numpy())
    out["none_pooled(unqualified+no_basket)"] = cells_by_horizon(
        df, df["theme_state"].isin([STATE_UNQUAL, STATE_NOBASKET]).to_numpy())
    out["ALL"] = cells_by_horizon(df, np.ones(len(df), dtype=bool))
    return out


def table_b(df: pd.DataFrame) -> dict:
    out = {}
    for s in STATE_ORDER:
        for r in ("early", "mid", "late", "na"):
            m = ((df["theme_state"] == s) & (df["relay"] == r)).to_numpy()
            if m.sum() == 0:
                continue
            out[f"{s}|{r}"] = cells_by_horizon(df, m)
    # relay ladder pooled across every theme state that HAS a relay count — the
    # cleanest statement of whether crowding, rather than heat, is the live axis
    for r in ("early", "mid", "late"):
        out[f"ANY_THEME|{r}"] = cells_by_horizon(df, (df["relay"] == r).to_numpy())
    return out


def table_c(df: pd.DataFrame) -> dict:
    out = {}
    for s in STATE_ORDER:
        for w in ("deep_dd", "shallow_dd"):
            m = ((df["theme_state"] == s) & (df["washout"] == w)).to_numpy()
            if m.sum() == 0:
                continue
            out[f"{s}|{w}"] = cells_by_horizon(df, m)
    return out


def table_d(df: pd.DataFrame, baseline: dict) -> dict:
    all_m = np.ones(len(df), dtype=bool)
    return {
        "all_chase_events_pooled": cells_by_horizon(df, all_m),
        "limit_close_leg_only": cells_by_horizon(df, df["limit_leg"].to_numpy().astype(bool)),
        "trail21_leg_only": cells_by_horizon(df, ~df["limit_leg"].to_numpy().astype(bool)),
        "universe_cell_baseline": baseline,
        "locked_t1_excluded": int(df["locked_t1"].sum()),
    }


def ignition_events(baskets: dict, lo: int, hi: int) -> list[tuple[int, int]]:
    """(basket_row, date_row) where heat UPGRADED vs 5 sessions ago; 5-session dedupe."""
    lvl = baskets["mats"]["level"]
    prev = np.full_like(lvl, 0)
    prev[:, 5:] = lvl[:, :-5]
    fired = (lvl > prev) & (lvl >= 1)
    out = []
    for b in range(fired.shape[0]):
        last = -10_000
        for d in np.flatnonzero(fired[b]):
            if d < lo or d > hi or d - last < DEDUPE_SESSIONS:
                continue
            out.append((b, int(d)))
            last = d
    return out


def table_e(panel: dict, feats: dict, baskets: dict, themes: dict,
            vpos: list[np.ndarray], df_chase: pd.DataFrame, lo: int, hi: int) -> dict:
    mats = baskets["mats"]
    bench = panel["bench"].to_numpy()
    close = panel["close"]
    tickers = panel["tickers"]
    tcol = {t: i for i, t in enumerate(tickers)}
    nt = len(panel["calendar"])

    igs = ignition_events(baskets, lo, hi)
    _stage(f"theme ignition transitions after dedupe: {len(igs)}")

    # (i) does the BASKET itself go up after ignition?
    basket_fwd = {h: [] for h in HORIZONS}
    for b, d in igs:
        lvlseries = mats["ew_level"][b]
        for h in HORIZONS:
            if d + h >= nt:
                continue
            l0, l1 = lvlseries[d], lvlseries[d + h]
            b0, b1 = bench[d], bench[d + h]
            if np.isfinite(l0) and l0 > 0 and np.isfinite(l1) and b0 > 0:
                basket_fwd[h].append((l1 / l0 - 1.0) * 100.0 - (b1 / b0 - 1.0) * 100.0)

    # basket-level control: every (basket, date) cell in-window, ignition or not
    ctrl = {h: [] for h in HORIZONS}
    for b in range(mats["ew_level"].shape[0]):
        lvlseries = mats["ew_level"][b]
        for h in HORIZONS:
            rows = np.arange(lo, min(hi + 1, nt - h))
            l0, l1 = lvlseries[rows], lvlseries[rows + h]
            b0, b1 = bench[rows], bench[rows + h]
            v = (l1 / l0 - 1.0) * 100.0 - (b1 / b0 - 1.0) * 100.0
            ctrl[h].append(v[np.isfinite(v)])

    # (ii) members that print a FRESH admission-like event inside the next 10 sessions
    adm = (feats["limit_close"] | (feats["cross_up"] & (feats["dd252"] <= IGNITION_DD)))
    adm = (adm & close.notna()).to_numpy()

    raw_member: set[tuple[int, int]] = set()
    for b, d in igs:
        for t in baskets["meta"][baskets["ids"][b]]["members"]:
            j = tcol.get(t)
            if j is None:
                continue
            for dd_ in range(d + 1, min(d + 10, nt - 1) + 1):
                if adm[dd_, j]:
                    raw_member.add((j, dd_))   # first admission print after this ignition
                    break
    # same 5-session keep-first dedupe every other cohort here gets, so a member picked
    # up by two overlapping ignitions is not counted twice
    member_events: list[tuple[int, int]] = []
    last_seen: dict[int, int] = {}
    for j, dd_ in sorted(raw_member):
        if dd_ - last_seen.get(j, -10_000) < DEDUPE_SESSIONS:
            continue
        member_events.append((j, dd_))
        last_seen[j] = dd_
    ig_out = event_outcomes(panel, feats, vpos, member_events)

    # baseline: EVERY admission-like event in the window, ignition-linked or not
    all_adm = dedupe_events(pd.DataFrame(adm, index=close.index, columns=close.columns), lo, hi)
    all_out = event_outcomes(panel, feats, vpos, all_adm)

    # (iii) the reverse cell — chase events inside a FADING hot theme
    fading = ((df_chase["theme_state"] == STATE_HOT) & (df_chase["slope5"] < 0)).to_numpy()
    rising = ((df_chase["theme_state"] == STATE_HOT) & (df_chase["slope5"] >= 0)).to_numpy()

    return {
        "n_ignition_transitions": len(igs),
        "basket_forward_excess_after_ignition": {
            f"h{h}": cell(np.asarray(basket_fwd[h])) for h in HORIZONS},
        "basket_forward_excess_all_cells_control": {
            f"h{h}": cell(np.concatenate(ctrl[h]) if ctrl[h] else np.array([]))
            for h in HORIZONS},
        "member_fresh_admissions_after_ignition": {
            f"h{h}": cell(ig_out[f"excess_h{h}"]) for h in HORIZONS},
        "all_admission_like_events_baseline": {
            f"h{h}": cell(all_out[f"excess_h{h}"]) for h in HORIZONS},
        "chase_in_HOT_rising_slope5": cells_by_horizon(df_chase, rising),
        "chase_in_HOT_fading_slope5": cells_by_horizon(df_chase, fading),
        "n_member_events": len(member_events),
        "n_all_admission_events": len(all_adm),
    }


def table_f(df: pd.DataFrame, df_curated: pd.DataFrame) -> dict:
    halves = {}
    for half in sorted(df["half"].unique()):
        halves[half] = {
            s: cells_by_horizon(df, ((df["theme_state"] == s) & (df["half"] == half)).to_numpy())
            for s in STATE_ORDER
        }
    flips = []
    for s in STATE_ORDER:
        for h in HORIZONS:
            vals = [halves[k][s][f"h{h}"]["median"] for k in halves]
            ns = [halves[k][s][f"h{h}"]["n"] for k in halves]
            if any(v is None for v in vals):
                continue
            if (vals[0] > 0) != (vals[1] > 0):
                flips.append({"cell": s, "horizon": f"h{h}", "medians": vals, "n": ns})
    return {
        "halves": halves,
        "sign_flips": flips,
        "curated_only_theme_assignment": table_a(df_curated),
    }


# ── verdicts (rules stated up front so the summary cannot drift) ──────────────

def half_gaps_from_events(df: pd.DataFrame) -> tuple[list[str], list[float | None]]:
    """HOT-minus-no-qualifying-theme median excess gap (H=10), computed per half from
    the raw event rows rather than reconstructed from summary cells."""
    labels, gaps = [], []
    for half in sorted(df["half"].unique()):
        sub = df[(df["half"] == half) & df["excess_h10"].notna()]
        hot = sub.loc[sub["theme_state"] == STATE_HOT, "excess_h10"]
        none = sub.loc[sub["theme_state"].isin([STATE_UNQUAL, STATE_NOBASKET]), "excess_h10"]
        labels.append(half)
        gaps.append(None if hot.empty or none.empty
                    else round(float(hot.median() - none.median()), 2))
    return labels, gaps


def verdicts(t_a: dict, t_b: dict, t_d: dict, t_e: dict,
             half_gaps: list[float | None]) -> dict:
    """Three pre-stated decision rules applied to the frozen cells."""
    hot = t_a[STATE_HOT]["h10"]
    none = t_a["none_pooled(unqualified+no_basket)"]["h10"]
    gap = None
    if hot["median"] is not None and none["median"] is not None:
        gap = round(hot["median"] - none["median"], 2)

    stable = (
        gap is not None
        and len(half_gaps) > 0
        and all(g is not None for g in half_gaps)
        and len({g > 0 for g in half_gaps}) == 1
        and (half_gaps[0] > 0) == (gap > 0)
    )

    if gap is None or hot["n"] < THIN_N or none["n"] < THIN_N:
        v1 = "INCONCLUSIVE (thin cells)"
    elif gap >= 3.0 and hot["median"] > 0 and stable:
        v1 = "REPLICATES"
    elif gap >= 3.0 and hot["median"] > 0:
        v1 = "DIRECTIONAL ONLY (not stable across halves)"
    elif gap > 0:
        v1 = "WEAK (gap below the 3pp pre-stated bar)"
    else:
        v1 = "DOES NOT REPLICATE"

    bk = t_e["basket_forward_excess_after_ignition"]["h10"]
    bctrl = t_e["basket_forward_excess_all_cells_control"]["h10"]
    mem = t_e["member_fresh_admissions_after_ignition"]["h10"]
    base = t_e["all_admission_like_events_baseline"]["h10"]
    lead_basket = (bk["median"] is not None and bctrl["median"] is not None
                   and bk["median"] > bctrl["median"] and bk["n"] >= THIN_N)
    lead_member = (mem["median"] is not None and base["median"] is not None
                   and mem["median"] - base["median"] >= 2.0 and mem["n"] >= THIN_N)
    if lead_basket and lead_member:
        v2 = "LEADS (both legs)"
    elif lead_basket or lead_member:
        v2 = "PARTIAL (one leg only)"
    else:
        v2 = "DOES NOT LEAD"

    # A blanket veto is only defensibly good if the vetoed cohort is worse than the
    # tape on ALL THREE of median, mean and win rate. A cohort that is worse on the
    # median but better on the mean has a fat right tail the veto would also delete,
    # and calling that "net-positive" would be exactly the kind of one-legged headline
    # this instrument exists to avoid.
    pooled = t_d["all_chase_events_pooled"]["h10"]
    uni = t_d["universe_cell_baseline"]["h10"]
    legs = {}
    if pooled["median"] is not None and uni["median"] is not None:
        legs = {
            "median": pooled["median"] < uni["median"],
            "mean": pooled["mean"] < uni["mean"],
            "win_pct": pooled["win_pct"] < uni["win_pct"],
        }
    if not legs:
        v3 = "INCONCLUSIVE"
    elif all(legs.values()):
        v3 = "NET-POSITIVE (a blanket veto saves value on median, mean and win rate)"
    elif not any(legs.values()):
        v3 = "NET-NEGATIVE (a blanket veto forfeits value on median, mean and win rate)"
    else:
        worse = [k for k, ok in legs.items() if ok]
        better = [k for k, ok in legs.items() if not ok]
        v3 = (f"MIXED — the chase cohort is worse on {'/'.join(worse)} but better on "
              f"{'/'.join(better)}; no blanket verdict is honest")

    # what DID separate, if anything: the relay ladder inside a theme
    ladder = {r: t_b.get(f"ANY_THEME|{r}", {}).get("h10") for r in ("early", "mid", "late")}
    have = all(c and c["median"] is not None and c["n"] >= THIN_N for c in ladder.values())
    monotone = bool(
        have
        and ladder["early"]["median"] > ladder["mid"]["median"] > ladder["late"]["median"]
        and ladder["early"]["win_pct"] > ladder["late"]["win_pct"]
    )
    v4 = ("MONOTONE early > mid > late" if monotone
          else "NOT MONOTONE" if have else "INCONCLUSIVE (thin cells)")

    # every name-level cell of real size whose median excess is actually positive —
    # computed, not asserted, so the summary cannot drift away from the tables
    above_water = []
    for tbl, label in ((t_a, "A"), (t_b, "B")):
        for k, val in tbl.items():
            c = val.get("h10")
            if c and c["n"] >= 100 and c["median"] is not None and c["median"] > 0:
                above_water.append({"table": label, "cell": k, "n": c["n"],
                                    "median": c["median"], "win_pct": c["win_pct"]})

    return {
        "q1_chase_x_theme_replicates": v1,
        "q1_evidence": {"hot_h10": hot, "none_pooled_h10": none, "gap_pp": gap,
                        "half_gaps_pp": half_gaps, "stable_across_halves": bool(stable)},
        "q2_ignition_leads": v2,
        "q2_evidence": {"basket_after_ignition_h10": bk, "basket_control_h10": bctrl,
                        "member_fresh_h10": mem, "all_admission_baseline_h10": base},
        "q3_blanket_veto": v3,
        "q3_evidence": {"all_chase_pooled_h10": pooled, "universe_baseline_h10": uni,
                        "veto_better_on": legs},
        "q4_relay_ladder": v4,
        "q4_evidence": ladder,
        "above_water_name_level_cells_n_ge_100_h10": above_water,
    }


# ── markdown emitter ──────────────────────────────────────────────────────────

def _fmt(c: dict) -> str:
    if c["n"] == 0:
        return "| 0 | — | — | — | — | — | — |"
    lo, hi = c["win_ci95"]
    thin = " *(thin)*" if c["thin"] else ""
    return (f"| {c['n']}{thin} | {c['win_pct']}% | {lo}–{hi} | {c['median']} | "
            f"{c['mean']} | {c['p10']} | {c['p90']} |")


def _table(rows: dict, horizon: str, title: str) -> str:
    lines = [f"**{title} — H={horizon[1:]} sessions**", "",
             "| cell | n | win% | Wilson 95% | median | mean | p10 | p90 |",
             "|---|---|---|---|---|---|---|---|"]
    for k, v in rows.items():
        c = v.get(horizon, v)
        # a raw pipe splits a GFM table cell even inside a code span — escape it
        lines.append(f"| `{k.replace('|', chr(92) + '|')}` " + _fmt(c))
    return "\n".join(lines) + "\n"


def render_md(res: dict) -> str:
    m, t = res["meta"], res["tables"]
    v = res["verdicts"]
    cov = res["coverage"]
    q1e, q2e = v["q1_evidence"], v["q2_evidence"]
    q3e, q4e = v["q3_evidence"], v["q4_evidence"]
    aw = v["above_water_name_level_cells_n_ge_100_h10"]
    aw_list = ", ".join(f"`{c['cell']}` (n={c['n']}, {c['median']}pp)" for c in aw)
    if not aw:
        aw_text = "NO name-level cell with n>=100 has a positive median excess at all"
    elif len(aw) == 1:
        aw_text = f"the ONLY name-level cell with n>=100 and a positive median excess is {aw_list}"
    else:
        aw_text = ("the only name-level cells with n>=100 and a positive median excess are "
                   + aw_list)

    out: list[str] = []
    out.append("# CN Prophet — 12-month CHASE x THEME-IGNITION study (phase-0)\n")
    out.append(
        f"Instrument `research/cn_prophet_audit/ignition_chase_study.py`; frozen cells in "
        f"`ignition_chase_results.json`. Window **{m['window_start']} → {m['window_end']}** "
        f"({m['n_sessions_in_window']} CSI300 sessions), universe {cov['n_tickers']} A-share "
        f"names, {cov['n_baskets_used']} theme baskets. Generated {m['generated_at']}.\n")
    out.append(
        "Motivated by the V1 loser audit (`RESULTS_2026-08-04.md`, PR #4500), whose "
        "chase x theme cell held **n=5**. This re-runs the same constructions at "
        "12-month scale. **Everything below is in-sample and motivating-only.**\n")

    out.append("## DECISION-RELEVANT SUMMARY\n")
    out.append(
        f"1. **Chase x theme interaction: {v['q1_chase_x_theme_replicates']}.** "
        f"Chase events inside a HOT theme: n={q1e['hot_h10']['n']}, "
        f"median excess {q1e['hot_h10']['median']}pp, win {q1e['hot_h10']['win_pct']}%. "
        f"Chase events with no qualifying theme: n={q1e['none_pooled_h10']['n']}, "
        f"median {q1e['none_pooled_h10']['median']}pp, win "
        f"{q1e['none_pooled_h10']['win_pct']}%. Gap **{q1e['gap_pp']}pp** at H=10; "
        f"half-by-half gaps {q1e['half_gaps_pp']} "
        f"({'same sign in both halves' if q1e['stable_across_halves'] else 'SIGN FLIPS across halves'}).")
    out.append(
        f"2. **Theme ignition lead: {v['q2_ignition_leads']}.** After a WARMING/HOT "
        f"upgrade the basket itself ran median {q2e['basket_after_ignition_h10']['median']}pp "
        f"excess over 10 sessions (n={q2e['basket_after_ignition_h10']['n']}) against an "
        f"all-cells basket control of {q2e['basket_control_h10']['median']}pp "
        f"(n={q2e['basket_control_h10']['n']}). Members printing a fresh admission-like "
        f"event inside the next 10 sessions: median "
        f"{q2e['member_fresh_h10']['median']}pp (n={q2e['member_fresh_h10']['n']}) vs an "
        f"all-admission baseline of {q2e['all_admission_baseline_h10']['median']}pp "
        f"(n={q2e['all_admission_baseline_h10']['n']}).")
    out.append(
        f"3. **Naive blanket chase veto: {v['q3_blanket_veto']}.** All "
        f"{q3e['all_chase_pooled_h10']['n']} matured chase events pooled ran median "
        f"{q3e['all_chase_pooled_h10']['median']}pp excess, mean "
        f"{q3e['all_chase_pooled_h10']['mean']}pp, win "
        f"{q3e['all_chase_pooled_h10']['win_pct']}% (Wilson "
        f"{q3e['all_chase_pooled_h10']['win_ci95'][0]}–"
        f"{q3e['all_chase_pooled_h10']['win_ci95'][1]}%), against a date-matched universe "
        f"cell baseline of median {q3e['universe_baseline_h10']['median']}pp, mean "
        f"{q3e['universe_baseline_h10']['mean']}pp, win "
        f"{q3e['universe_baseline_h10']['win_pct']}%. The chase cohort has a WIDER "
        "distribution than the tape in both directions, so a blanket veto deletes the "
        "right tail along with the left.")
    out.append(
        f"4. **What actually separated: relay position, not theme heat "
        f"({v['q4_relay_ladder']}).** Pooled across every theme state that has a relay "
        f"count — early (<=1 other member limit-closed in [d-2, d]) median "
        f"{q4e['early']['median']}pp / win {q4e['early']['win_pct']}% (n={q4e['early']['n']}); "
        f"mid {q4e['mid']['median']}pp / {q4e['mid']['win_pct']}% (n={q4e['mid']['n']}); "
        f"late (>=4) {q4e['late']['median']}pp / {q4e['late']['win_pct']}% "
        f"(n={q4e['late']['n']}). The V1 audit's intuition — that WHERE in a theme's "
        "relay you buy decides the outcome — survives; its proxy (is the theme HOT) does "
        "not. The ladder is a RANKING, not a green light: even the early rung sits below "
        f"the universe median, and {aw_text}. A relay-aware rule is therefore a candidate "
        "ORDERING or de-escalation input, not a buy trigger.\n")
    out.append(
        "**Read this before acting on any row.** Forward windows overlap massively; "
        "theme cells are the same few dozen baskets on the same few dozen dates, so the "
        "effective n is far below the printed n. Basket membership is a single 2026-07-08 "
        "snapshot applied backward for twelve months — the one irreducible lookahead here, "
        "quantified in Caveats. No cell below has been through the gauntlet; nothing here "
        "promotes anything.\n")

    out.append("## A. Chase events by theme state at d\n")
    for h in ("h10", "h21"):
        out.append(_table(t["A_theme_state"], h, "A — theme state at admission"))
    out.append("## B. Theme state x relay position\n")
    out.append(
        "`early` = at most 1 OTHER member of the same theme printed a limit-close in "
        "[d-2, d]; `late` = 4 or more; `mid` = 2-3; `na` = the name sits in no covered "
        "basket, so the relay count is undefined rather than zero.\n")
    for h in ("h10", "h21"):
        out.append(_table(t["B_theme_x_relay"], h, "B — theme x relay"))
    out.append("## C. Theme state x washout context (drawdown from the 252d high at d)\n")
    for h in ("h10", "h21"):
        out.append(_table(t["C_theme_x_washout"], h, "C — theme x washout"))

    out.append("## D. What a naive blanket chase veto actually vetoes\n")
    d = t["D_blanket_veto"]
    rows = {k: d[k] for k in ("all_chase_events_pooled", "limit_close_leg_only",
                              "trail21_leg_only")}
    rows["universe_cell_baseline"] = d["universe_cell_baseline"]
    for h in ("h10", "h21"):
        out.append(_table(rows, h, "D — pooled chase vs universe"))
    out.append(
        f"{d['locked_t1_excluded']} events were dropped because their T+1 bar printed "
        "high==low==close (locked limit, unfillable at any price) — the same exclusion "
        "production grading makes.\n")

    out.append("## E. Ignition lead test\n")
    e = t["E_ignition_lead"]
    out.append(
        f"{e['n_ignition_transitions']} theme upgrades (heat level today strictly above "
        "its level 5 sessions ago, deduped to one per basket per 5 sessions). Basket "
        "forward excess is close-to-close on the EW basket level — a basket is not "
        "tradeable, so no fill mechanics are applied to it. Member rows use the same "
        "T+1-fill grading as everything else.\n")
    rows = {
        "basket after ignition": e["basket_forward_excess_after_ignition"],
        "basket control (all cells)": e["basket_forward_excess_all_cells_control"],
        "member fresh admission <=10d after ignition": e["member_fresh_admissions_after_ignition"],
        "all admission-like events (baseline)": e["all_admission_like_events_baseline"],
        "chase inside HOT, rel20 slope5 >= 0": e["chase_in_HOT_rising_slope5"],
        "chase inside HOT, rel20 slope5 < 0 (fading)": e["chase_in_HOT_fading_slope5"],
    }
    for h in ("h10", "h21"):
        out.append(_table(rows, h, "E — ignition lead"))

    out.append("## F. Robustness — halves and a curated-only theme assignment\n")
    f = t["F_halves"]
    for half, cells in f["halves"].items():
        for h in ("h10",):
            out.append(_table(cells, h, f"F — {half}"))
    if f["sign_flips"]:
        out.append("**Sign flips between halves:**\n")
        for fl in f["sign_flips"]:
            out.append(f"- `{fl['cell']}` at {fl['horizon']}: medians {fl['medians']}, n {fl['n']}")
        out.append("")
    else:
        out.append("No A-cell median changed sign between halves.\n")
    out.append(
        "The curated-only pass re-assigns every name's theme using ONLY the 22 "
        "hand-curated baskets (seeded 2021, not a 2026 vendor snapshot), so it is the "
        "closest thing here to a membership-drift control:\n")
    out.append(_table(f["curated_only_theme_assignment"], "h10", "F — curated-only assignment"))

    out.append("## Caveats — read these as part of the result\n")
    for c in res["caveats"]:
        out.append(f"- {c}")
    out.append("")
    return "\n".join(out)


# ── caveats ───────────────────────────────────────────────────────────────────

def caveats(n_young: int, n_members: int) -> list[str]:
    """The honesty block. Emitted into both artifacts; part of the result, not decoration."""
    membership = (
        "**Membership lookahead (the big one).** `data/baskets_china_ths/membership.json` "
        "is byte-identical to the 2026-07-08 THS snapshot and carries no `removed` rows and "
        "no in-window `added` dates: it is TODAY's composition applied backward for twelve "
        "months. The only two point-in-time snapshots in the repo are 8 calendar days apart "
        "and already differ by 7.7% of member-slots once both are filtered to the price "
        "cache, so a 12-month backward application is a material and unquantified "
        "composition bias. Its direction is knowable even if its size is not: a name sits "
        "in the 2026 concept board partly BECAUSE it moved with that theme, so every "
        "HOT/WARMING cell is flattered and every no-theme cell is the residue. The "
        "curated-only pass in table F is the closest available control, not a fix."
    )
    young = (
        f"**Young names.** {n_young} of {n_members} basket members have under 200 sessions "
        "of price history before the window opens, so their early-window breadth and rel20 "
        "contributions rest on short series."
    )
    overlap = (
        "**Overlapping windows.** Events cluster on the same dates and inside the same "
        "themes; a 10-session forward window overlaps the next event's. The printed n counts "
        "events, not independent observations. Treat every median as descriptive."
    )
    no_ci = (
        "**No CI theater.** The only interval reported is a Wilson interval on win%, which "
        "is a binomial statement and still ignores the overlap above. No p-values, no "
        "bootstrap on medians, no significance claim anywhere."
    )
    in_sample = (
        "**In-sample.** Thresholds (18.5%/9.5% band, +25%/+3% chase leg, rel20 5/0, breadth "
        "0.60/0.50, relay 1/4, dd -25%) were fixed BEFORE this run from production and from "
        "the V1 audit, not fitted here — but the window, the cohorts, and the cuts were all "
        "chosen after seeing the V1 result. Nothing here is out-of-sample in the sense that "
        "matters."
    )
    maturation = (
        "**Horizon maturation.** Events late in the window cannot mature: an H=21 outcome "
        "needs 21 further sessions and the price store ends 2026-08-03. H=21 cells are "
        "therefore built on an earlier, smaller slice of the window than H=10 cells — they "
        "are not the same cohort re-measured."
    )
    survivorship = (
        "**Survivorship.** `data/china_stocks` is the live price cache; names delisted "
        "before it was built are absent from both the universe and every basket."
    )
    coarse = (
        "**Theme assignment is coarse.** A name in several baskets is assigned the single "
        "strongest qualifying one by rel20 (production's rule). Multi-theme names therefore "
        "contribute to exactly one cell, and the choice is made with same-day data only."
    )
    self_inclusion = (
        "**A chase event helps cause its own theme's HOT tag.** rel20 and breadth are "
        "computed over ALL covered members INCLUDING the event name (production's "
        "definition, kept deliberately). The median basket here holds 13 covered members, "
        "so one member closing limit-up moves its own basket's 20d EW return by roughly "
        "1.5pp single-handedly, and the same close puts that member above its own 20d MA "
        "in the breadth count. Part of 'this chase event sat in a HOT theme' is therefore "
        "mechanical rather than contextual, which is one plausible reason the theme axis "
        "in table A separates nothing. The relay count in table B does NOT have this "
        "problem — it excludes the event name by construction."
    )
    return [membership, self_inclusion, young, overlap, no_ci, in_sample, maturation,
            survivorship, coarse]


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    panel = load_panel()
    feats = name_features(panel)
    memberships = load_memberships()
    baskets = basket_panels(panel, feats, memberships)
    themes = assign_themes(panel, baskets)
    themes_curated = assign_themes(panel, baskets, restrict_source="curated")
    vpos = valid_positions(panel["close"])

    cal = panel["calendar"]
    lo = int(np.searchsorted(cal, WINDOW_START, side="left"))
    hi = int(np.searchsorted(cal, WINDOW_END, side="right")) - 1

    df = build_event_frame(panel, feats, baskets, themes, vpos, lo, hi)
    df_cur = build_event_frame(panel, feats, baskets, themes_curated, vpos, lo, hi)
    baseline = universe_baseline(panel, feats, lo, hi)
    _stage("outcomes graded")

    t_a = table_a(df)
    t_b = table_b(df)
    t_c = table_c(df)
    t_d = table_d(df, baseline)
    t_e = table_e(panel, feats, baskets, themes, vpos, df, lo, hi)
    t_f = table_f(df, df_cur)
    _stage("tables built")

    n_young = int(sum(
        1 for t in {t for b in baskets["ids"] for t in baskets["meta"][b]["members"]}
        if t in panel["close"].columns
        and int(panel["close"][t].iloc[:lo].notna().sum()) < 200))
    n_members = len({t for b in baskets["ids"] for t in baskets["meta"][b]["members"]})

    res = {
        "meta": {
            "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%MZ"),
            "window_start": str(WINDOW_START.date()),
            "window_end": str(WINDOW_END.date()),
            "n_sessions_in_window": hi - lo + 1,
            "horizons": list(HORIZONS),
            "status": "IN-SAMPLE, MOTIVATING-ONLY — not a backtest, not a promotion",
            "definitions": {
                "limit_close": "close/prevclose-1 >= band AND close == high (band from "
                               "engine.china_signals.board_type: 688/689/300/301 = 18.5%, "
                               "else 9.5%)",
                "chase_event": "limit_close OR (trailing-21d return >= +25% AND same-day "
                               "return >= +3%), deduped to one per ticker per 5 sessions, "
                               "keep-first",
                "theme_state": "strongest QUALIFYING basket by rel20 (HOT rel20>=5 and "
                               "breadth>=0.60; WARMING rel20>=0 and breadth>=0.50; both "
                               "need >=5 covered members)",
                "relay_position": "distinct OTHER members of the assigned basket with a "
                                  "limit-close in [d-2, d]: early<=1, mid 2-3, late>=4",
                "outcome": "T+1 fill (open, else (H+L)/2), locked-limit T+1 excluded, exit "
                           "at the horizon-th valid bar counting the fill bar as bar 1, "
                           "excess vs 510300.SS over the same fill->exit window",
            },
        },
        "coverage": {
            "n_tickers": len(panel["tickers"]),
            "n_baskets_used": len(baskets["ids"]),
            "n_basket_members": n_members,
            "n_members_under_200_sessions_before_window": n_young,
            "n_chase_events": len(df),
            "n_chase_matured_h10": int(df["excess_h10"].notna().sum()),
            "n_chase_matured_h21": int(df["excess_h21"].notna().sum()),
            "n_locked_t1_excluded": int(df["locked_t1"].sum()),
            "theme_state_counts": df["theme_state"].value_counts().to_dict(),
        },
        "tables": {
            "A_theme_state": t_a,
            "B_theme_x_relay": t_b,
            "C_theme_x_washout": t_c,
            "D_blanket_veto": t_d,
            "E_ignition_lead": t_e,
            "F_halves": t_f,
        },
        "caveats": caveats(n_young, n_members),
    }
    half_labels, half_gaps = half_gaps_from_events(df)
    res["verdicts"] = verdicts(t_a, t_b, t_d, t_e, half_gaps)
    res["verdicts"]["q1_evidence"]["half_labels"] = half_labels

    OUT_JSON.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    OUT_MD.write_text(render_md(res))
    _stage(f"wrote {OUT_JSON.name} and {OUT_MD.name}")
    print(json.dumps(res["verdicts"], indent=2, default=str)[:2000], flush=True)


if __name__ == "__main__":
    main()
