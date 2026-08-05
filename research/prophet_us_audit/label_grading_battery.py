"""US label-grading battery — grade the system's OWN internal labels as signals.

Charter: research/CN_TO_US_PROPHET_HANDOFF_2026-08-04.md §1 (operator-requested
CN->US transfer). The CN breakthrough was not a new indicator: it came from
stratifying matured outcomes by labels the system ALREADY stamps, and finding the
entry gauge's ladder inverted on that tape. This instrument runs the same three
measurements on the US tape.

DIRECTION FENCE (handoff §5). CN's tape mean-reverts; the US tape measured
confirmation-POSITIVE (roadmap §5 S-B). Nothing here assumes either sign. Every
cohort is reported raw + demeaned + per-name-first with its n, and the verdict
lines are written from the printed numbers only.

Three sections, one frame family:

  (1) by_entry_status  — the entry_signal.assess gauge (engine/entry_signal.py,
      wired at scripts/build_stock_library.py:2657-2659) stamps a status on US
      rows; data/us_board_ledger/retro_grades.parquet carries it. Stratify
      matured BUY-lane episodes by that status. Question: is the gauge's ladder
      correctly ordered FOR this tape?

  (2) veto/exclusion labels graded FROM THE VETO DAY — full-universe PIT
      construction off the three closes caches. Each veto is a timing label that
      may be mispriced. Legs are replicated inline (source lines cited at each
      leg) and spot-checked for equality against engine.confluence_tiers.

  (3) the ran lane from its OWN anchor — the US analogue of CN's RAN_LATE shelf.

MEASUREMENT ONLY. No gate, board, engine or config change follows from this file;
any flip is a later operator adjudication (DNR row 49; the US plan's G0.2/G0.4
sequencing stands).

Stats guards, binding on every section: date-demeaned beside raw; per-name-first
beside pooled; loser := excess_spy < -3pp (stated, with medians reported so no
verdict hangs on the threshold); thin cells print n and say thin; half-split
robustness on headline deltas; winner-forfeiture costing on implied filters (the
v1_loser_audit G0.7 idiom); per-sector concentration disclosure.

FROZEN-REPLAY PIN: every price series is truncated at REPRO_ASOF and the ledger
frame at REPRO_ASOF, so this instrument reproduces after tonight's nightly
(handoff §2; the CN #4522 trap).

NUMPY-BOOL TRAP: ``x is True`` on a numpy bool is ALWAYS False (memory:
numpy-bool-is-true-deadens-a-feature-leg). Every truth test below goes through
bool() or ==, and every leg carries a fire count so a dead leg is visible.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "label_grading_battery_results.json")
os.chdir(REPO)
sys.path.insert(0, REPO)

from engine import confluence_tiers as ct                      # noqa: E402
from engine import us_board_rank as ubr                        # noqa: E402
from engine.confluence_tiers import (                          # noqa: E402
    BUY_RSI_MAX, FRESH_TICKS, OB, RSI_LEN,
    _last_true_pos, _rsi_macd, _stoch_rsi_kd, _tf_bars, _ticks_since_vec,
    _to_daily, _xup,
)
from engine.technicals import rsi                              # noqa: E402
from lib import store                                          # noqa: E402

# ---------------------------------------------------------------- constants --
REPRO_ASOF = "2026-07-31"     # frozen-replay pin: names-cache last session on the
                              # frame this battery was authored against. Every price
                              # series and the ledger are truncated here so a re-run
                              # after any later nightly reproduces these numbers.
LOSER_PP = -3.0               # loser := excess vs SPY < -3pp at the horizon (STATED)
H_PRIMARY = 10                # primary horizon (sessions)
H_SUPPORT = 21                # supporting horizon (sessions)
THIN_N = 20                   # below this an n is called thin in its own row
LOOK = 126                    # section-2/3 evaluation window (leader_reset_study idiom)
MIN_HIST = 260                # names with less history than this are out of the universe
BENCH = "SPY"

_GROUPS = ("breadth", "midcap_breadth", "smallcap_breadth")


# ------------------------------------------------------------------ helpers --
def _r(x, nd: int = 2):
    """Round, but never crash on a NaN/None/inf."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if np.isfinite(f) else None


def stats_block(ex_spy_pp, ex_dm_pp, tickers, *, thin_n: int = THIN_N) -> dict:
    """The house stat row: pooled raw + demeaned + per-name-first, with n and a
    thin flag. ``ex_spy_pp`` is excess vs SPY in percentage points (the loser
    basis); ``ex_dm_pp`` is the demeaned/market-neutral column beside it."""
    n = len(ex_spy_pp)
    if n == 0:
        return {"n": 0, "thin": True, "note": "no observations in this cell"}
    s = pd.Series(np.asarray(ex_spy_pp, dtype=float))
    d = pd.Series(np.asarray(ex_dm_pp, dtype=float))
    byname = pd.DataFrame({"t": list(tickers), "ex": s.to_numpy()}).groupby("t")["ex"].median()
    out = {
        "n": int(n),
        "names": int(byname.shape[0]),
        "loser_rate_pct": _r((s < LOSER_PP).mean() * 100, 1),
        "win_rate_pct": _r((s > 0).mean() * 100, 1),
        "median_excess_spy_pp": _r(s.median()),
        "median_excess_dm_pp": _r(d.median()),
        "per_name_first_median_pp": _r(byname.median()),
        "mean_excess_spy_pp": _r(s.mean()),
        "p25_pp": _r(s.quantile(0.25), 1),
        "p75_pp": _r(s.quantile(0.75), 1),
    }
    if n < thin_n:
        out["thin"] = True
        out["thin_note"] = f"THIN CELL — n={n} < {thin_n}; directional read only"
    return out


def half_split(dates, ex_spy_pp, ex_dm_pp, tickers) -> dict:
    """Robustness: split the cohort at its median event date and re-stat each half.
    A headline delta that only exists in one half is not a stable delta."""
    if len(dates) < 4:
        return {"note": "too few observations to half-split", "n": int(len(dates))}
    dser = pd.Series(pd.to_datetime(list(dates)))
    n_dates = int(dser.nunique())
    if n_dates < 2:
        # A cohort drawn from ONE session cannot be split in time. Saying "stable"
        # here would be a vacuous pass, so the guard reports itself as unrunnable.
        return {"note": "UNRUNNABLE — all observations share a single date; a time "
                        "half-split cannot test this cohort",
                "n": int(len(dates)), "distinct_dates": n_dates}
    cut = dser.median()
    first = (dser <= cut).to_numpy()
    if first.all() or (~first).all():
        # median date == max date (a heavily back-loaded cohort): fall back to splitting
        # strictly BEFORE the median so both halves are non-empty.
        first = (dser < cut).to_numpy()
    if first.sum() == 0 or (~first).sum() == 0:
        return {"note": "UNRUNNABLE — dates too concentrated to form two non-empty halves",
                "n": int(len(dates)), "distinct_dates": n_dates}
    ex_spy_pp = np.asarray(ex_spy_pp, dtype=float)
    ex_dm_pp = np.asarray(ex_dm_pp, dtype=float)
    tk = np.asarray(list(tickers), dtype=object)
    a = stats_block(ex_spy_pp[first], ex_dm_pp[first], tk[first])
    b = stats_block(ex_spy_pp[~first], ex_dm_pp[~first], tk[~first])
    out = {"split_at": str(pd.Timestamp(cut).date()), "distinct_dates": n_dates,
           "first_half": a, "second_half": b}
    pa, pb = a.get("per_name_first_median_pp"), b.get("per_name_first_median_pp")
    if pa is not None and pb is not None:
        out["sign_flip_across_halves"] = bool((pa > 0) != (pb > 0))
        out["per_name_median_gap_pp"] = _r(abs(pa - pb))
    return out


def forfeiture_cost(name: str, base_ex_pp: np.ndarray, hit: np.ndarray) -> dict:
    """G0.7 winner-forfeiture costing (v1_loser_audit idiom): a candidate filter is
    priced by BOTH the losers it removes and the winners it forfeits, never by the
    losers alone. ``hit`` = the rows the filter would REMOVE from ``base_ex_pp``."""
    base_ex_pp = np.asarray(base_ex_pp, dtype=float)
    hit = np.asarray(hit, dtype=bool)
    kept = ~hit
    n_hit, n_kept = int(hit.sum()), int(kept.sum())
    return {
        "filter": name,
        "n_removed": n_hit,
        "losers_removed": int((base_ex_pp[hit] < LOSER_PP).sum()) if n_hit else 0,
        "winners_removed_gt0": int((base_ex_pp[hit] > 0).sum()) if n_hit else 0,
        "removed_median_excess_pp": _r(np.median(base_ex_pp[hit])) if n_hit else None,
        "kept_n": n_kept,
        "kept_win_rate_pct": _r((base_ex_pp[kept] > 0).mean() * 100, 1) if n_kept else None,
        "kept_loser_rate_pct": _r((base_ex_pp[kept] < LOSER_PP).mean() * 100, 1) if n_kept else None,
        "kept_median_excess_pp": _r(np.median(base_ex_pp[kept])) if n_kept else None,
        "base_median_excess_pp": _r(np.median(base_ex_pp)) if len(base_ex_pp) else None,
        "base_win_rate_pct": _r((base_ex_pp > 0).mean() * 100, 1) if len(base_ex_pp) else None,
    }


def sector_concentration(tickers, sector_of: dict, top: int = 4) -> dict:
    """Per-sector concentration disclosure: a cohort verdict carried by one sector
    is a sector call wearing a label's clothes."""
    secs = pd.Series([sector_of.get(str(t), "unknown") for t in tickers])
    if secs.empty:
        return {"coverage_pct": 0.0}
    vc = secs.value_counts(normalize=True) * 100
    known = float((secs != "unknown").mean() * 100)
    return {
        "coverage_pct": _r(known, 1),
        "top_sectors_pct": {str(k): _r(v, 1) for k, v in vc.head(top).items()},
        "max_single_sector_pct": _r(vc.max(), 1),
    }


def _sector_map() -> dict:
    """ticker -> GICS sector, read off the board ledger (the only PIT-ish map that
    covers the graded names). Coverage is disclosed wherever it is used."""
    df = pd.read_parquet("data/us_board_ledger/retro_grades.parquet")
    m = (df.dropna(subset=["ticker", "sector"])
           .drop_duplicates("ticker").set_index("ticker")["sector"].to_dict())
    return {str(k): str(v) for k, v in m.items()}


# ------------------------------------------------------- section 1: ladder --
def load_ledger(horizon: int) -> pd.DataFrame:
    """Matured BUY-lane episodes at one horizon, frozen at REPRO_ASOF."""
    df = pd.read_parquet("data/us_board_ledger/retro_grades.parquet")
    df = df[(df["lane"] == "buy") & (df["horizon"] == horizon)].copy()
    df = df.dropna(subset=["excess_spy", "entry_date", "ticker"])
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df = df[df["entry_date"] <= pd.Timestamp(REPRO_ASOF)]        # frozen-replay pin
    df["excess_pp"] = df["excess_spy"].astype(float) * 100.0
    # date-demeaned outcome (within the admission-date cohort) — the standins idiom
    df["excess_dm"] = df["excess_pp"] - df.groupby("entry_date")["excess_pp"].transform("mean")
    return df


def section_entry_status(sector_of: dict) -> dict:
    """(1) Is the entry gauge's ladder correctly ordered for the US tape?

    Census first — the status vocabulary is read off the frame, never assumed from
    the CN side."""
    res: dict = {
        "question": "is the entry_signal.assess ladder correctly ordered FOR this tape?",
        "gauge_source": "engine/entry_signal.py (_STATUS_BY_URGENCY, l.24-33); wired for US "
                        "rows at scripts/build_stock_library.py:2657-2659",
        "frame": "data/us_board_ledger/retro_grades.parquet, lane=='buy'",
        "loser_def": f"excess_spy < {LOSER_PP}pp at the horizon",
    }
    for h, tag in ((H_PRIMARY, "H10_primary"), (H_SUPPORT, "H21_supporting")):
        df = load_ledger(h)
        if df.empty:
            res[tag] = {"n": 0, "note": "no matured buy-lane rows at this horizon"}
            continue
        # ---- census: the ACTUAL vocabulary on US rows, with nulls counted ----
        vocab = df["entry_status"].fillna("<NULL>").value_counts().to_dict()
        n_dates = int(df["entry_date"].nunique())
        block: dict = {
            "rows": int(len(df)), "names": int(df["ticker"].nunique()),
            "admission_dates": n_dates,
            "date_range": [str(df["entry_date"].min().date()), str(df["entry_date"].max().date())],
            "status_census": {str(k): int(v) for k, v in vocab.items()},
            "base": stats_block(df["excess_pp"].to_numpy(), df["excess_dm"].to_numpy(),
                                df["ticker"].tolist()),
        }
        if n_dates <= 1:
            block["demean_degenerate"] = (
                "ALL rows share ONE admission date — the date-demeaned column is a "
                "within-single-cohort deviation, not a cross-date control. Read raw.")
        # ---- the ladder ----
        ladder = {}
        for status, g in df.groupby(df["entry_status"].fillna("<NULL>")):
            blk = stats_block(g["excess_pp"].to_numpy(), g["excess_dm"].to_numpy(),
                              g["ticker"].tolist())
            blk["sector_mix"] = sector_concentration(g["ticker"].tolist(), sector_of)
            ladder[str(status)] = blk
        block["by_entry_status"] = ladder
        # ---- headline: best vs worst by per-name-first median among non-thin cells --
        ranked = [(k, v) for k, v in ladder.items()
                  if k != "<NULL>" and v.get("n", 0) >= THIN_N
                  and v.get("per_name_first_median_pp") is not None]
        ranked.sort(key=lambda kv: kv[1]["per_name_first_median_pp"], reverse=True)
        block["ranked_non_thin_by_per_name_median"] = [
            {"status": k, "n": v["n"], "per_name_first_median_pp": v["per_name_first_median_pp"],
             "median_excess_spy_pp": v["median_excess_spy_pp"],
             "loser_rate_pct": v["loser_rate_pct"]} for k, v in ranked]
        if len(ranked) >= 2:
            best, worst = ranked[0], ranked[-1]
            block["headline"] = {
                "best_status": best[0], "worst_status": worst[0],
                "delta_per_name_median_pp": _r(best[1]["per_name_first_median_pp"]
                                               - worst[1]["per_name_first_median_pp"]),
                "half_split_best": half_split(
                    df[df["entry_status"] == best[0]]["entry_date"],
                    df[df["entry_status"] == best[0]]["excess_pp"],
                    df[df["entry_status"] == best[0]]["excess_dm"],
                    df[df["entry_status"] == best[0]]["ticker"]),
                "half_split_worst": half_split(
                    df[df["entry_status"] == worst[0]]["entry_date"],
                    df[df["entry_status"] == worst[0]]["excess_pp"],
                    df[df["entry_status"] == worst[0]]["excess_dm"],
                    df[df["entry_status"] == worst[0]]["ticker"]),
            }
            # implied filter, costed BOTH ways (G0.7)
            block["implied_filter_cost"] = forfeiture_cost(
                f"drop_status_{worst[0]}", df["excess_pp"].to_numpy(),
                (df["entry_status"] == worst[0]).to_numpy())
        # ---- the buy_now / confirmed cell called out by name (handoff §1) ----
        block["confirmation_cells"] = {
            s: ladder.get(s, {"n": 0}) for s in ("buy_now", "partial", "buy_soon",
                                                 "await_confluence")}
        res[tag] = block

    # ---- H=5 MATURITY CROSS-CHECK (not a deliverable horizon) --------------------
    # The horizons are NOT nested samples of one population: a board row matures at H=5
    # ten sessions before it matures at H=10, so the H=10 frame is only the EARLIER
    # boards and its per-status cells are much thinner. Any status whose H=10 cell is
    # thin must be read against the same status at H=5, where the sample is several
    # times larger, before it is read at all. This block exists so a thin negative cell
    # cannot be quoted without its own counter-evidence sitting beside it.
    df5 = load_ledger(5)
    if not df5.empty:
        cc = {}
        for status, g in df5.groupby(df5["entry_status"].fillna("<NULL>")):
            cc[str(status)] = stats_block(g["excess_pp"].to_numpy(),
                                          g["excess_dm"].to_numpy(), g["ticker"].tolist())
        h10 = res.get("H10_primary", {}).get("by_entry_status", {})
        flips = []
        for s, v5 in cc.items():
            v10 = h10.get(s)
            if not v10 or v10.get("per_name_first_median_pp") is None:
                continue
            if (v5["per_name_first_median_pp"] > 0) != (v10["per_name_first_median_pp"] > 0):
                flips.append({"status": s,
                              "H5": {"n": v5["n"],
                                     "per_name_first_median_pp": v5["per_name_first_median_pp"],
                                     "loser_rate_pct": v5["loser_rate_pct"]},
                              "H10": {"n": v10["n"],
                                      "per_name_first_median_pp": v10["per_name_first_median_pp"],
                                      "loser_rate_pct": v10["loser_rate_pct"]}})
        res["H5_maturity_crosscheck"] = {
            "why": "H=5 and H=10 are NOT nested samples — a row matures at H=5 ten sessions "
                   "earlier, so the H=10 frame carries only the earlier boards and its "
                   "per-status cells are thinner. Reported so a thin H=10 cell is never "
                   "quoted without the larger-sample read of the same label beside it. "
                   "H=5 is NOT a deliverable horizon of this battery.",
            "rows": int(len(df5)),
            "by_entry_status": cc,
            "statuses_whose_sign_differs_vs_H10": flips,
        }
    return res


# --------------------------------------------- section 2: veto-day labels --
def load_universe() -> tuple[pd.DataFrame, dict[str, pd.Series], dict]:
    """Two price views, deliberately kept apart.

    ``px`` — the three US closes caches EXACTLY as production reads them, truncated at
    REPRO_ASOF. Every oscillator leg in section 2 is computed from this and nothing
    else, because ``_tf_bars`` resamples on ``3B``/``2B`` buckets whose PHASE is
    anchored on the series' first index date (memory:
    resample-bin-phase-is-anchored-on-the-first-index-date). Prepending history would
    shift every 3D bucket boundary and quietly de-align the labels from the gate they
    are supposed to be grading.

    ``deep`` — the same names spliced under with data/yahoo/<T>.parquet, used for the
    WEEKLY leg only. That leg has no phase sensitivity worth protecting (W-FRI anchors
    on the calendar, not on the first row) and it has a hard depth requirement the
    caches cannot meet: ``_rsi_macd`` needs RSI_LEN(14)+BASE_LEN(60)=74 W-FRI bars
    before its first non-NaN, and the `breadth` cache (the large-cap sleeve — AAPL,
    ABBV, …) starts 2025-03-18 with only 345 sessions ≈ 72 weekly bars. On the raw
    caches ``weekly_bull`` is therefore IDENTICALLY FALSE for 549 of 1540 names — a
    silently dead leg that would have deleted the large-cap sleeve from section 3
    without ever raising an error. The two sources agree where they overlap (checked:
    median max relative difference 0.000000 over a 40-name sample) and the cache always
    wins on any shared date, so the splice only ever fills history that is missing.
    """
    frames = [pd.read_parquet(f"data/{g}/_closes_cache.parquet") for g in _GROUPS]
    idx = sorted(set().union(*[set(f.index) for f in frames]))
    wide = pd.concat([f.reindex(idx) for f in frames], axis=1)
    wide = wide.loc[:, ~wide.columns.duplicated()]
    wide = wide.loc[wide.index <= pd.Timestamp(REPRO_ASOF)]      # frozen-replay pin
    px = wide.loc[:, wide.notna().sum() >= MIN_HIST]

    deep: dict[str, pd.Series] = {}
    deepened = 0
    ydir = Path("data/yahoo")
    for t in px.columns:
        base = px[t].dropna()
        p = ydir / f"{t}.parquet"
        if not p.exists():
            deep[t] = base
            continue
        try:
            y = pd.read_parquet(p)
        except (OSError, ValueError):
            deep[t] = base
            continue
        col = "close" if "close" in y.columns else "close_price"
        if col not in y.columns:
            deep[t] = base
            continue
        ys = y[col].dropna()
        ys.index = pd.to_datetime(ys.index)
        ys = ys[ys.index <= pd.Timestamp(REPRO_ASOF)]            # frozen-replay pin
        merged = base.combine_first(ys)          # cache wins on overlap
        if merged.notna().sum() > base.notna().sum():
            deepened += 1
        deep[t] = merged.dropna()
    prov = {
        "cache_names": int(wide.shape[1]),
        "universe_after_min_history": int(px.shape[1]),
        "names_deepened_from_yahoo_for_weekly_leg": int(deepened),
        "splice_scope": "WEEKLY leg only — the 3D/2D oscillator legs are computed on the "
                        "unspliced production cache series so their resample phase matches "
                        "the gate they grade",
        "splice_rule": "cache value wins on any overlapping date; data/yahoo/<T>.parquet "
                       "fills earlier history only",
    }
    return px, deep, prov


def build_label_panels(px: pd.DataFrame,
                       deep: dict[str, pd.Series] | None = None) -> tuple[dict, dict]:
    """Per-day, per-name veto/exclusion labels for the whole universe.

    Every leg is replicated INLINE from engine/confluence_tiers.py so the label is
    self-describing, with the production source line cited beside it. An equality
    spot-check against ``confluence_tiers.tier_stream`` runs afterwards and is
    reported — the replication is pinned, not asserted.

    NaN semantics match the production scalar path: a NaN comparison is False, so a
    warm-up bar never fires a veto leg.
    """
    idx = px.index
    n = len(idx)
    cols: list[str] = []
    weekly_ok: list[str] = []       # names whose weekly leg produces ANY non-NaN value
    acc: dict[str, list[np.ndarray]] = {k: [] for k in (
        "stoch_ob", "stoch_bear", "macd_bear", "rsi_ge_cap",
        "cross_ticks", "has_cross", "not_topped_stream", "eligible",
        "above200", "weekly_bull", "has_px")}

    for t in px.columns:
        c = px[t].dropna()
        if len(c) < MIN_HIST:
            continue
        di = c.index
        ss3, sk3 = _tf_bars(c, 3)                    # 3D buckets (confluence_tiers l.386)
        k3, d3 = _stoch_rsi_kd(ss3)
        m3, s3 = _rsi_macd(ss3)
        r14_3 = rsi(ss3, RSI_LEN)

        def td(s, kn=sk3, how="ffill", _di=di):
            # _di bound at definition, not captured: these closures live inside the
            # per-name loop, and a late-bound `di` would silently re-map every leg onto
            # the LAST name's index if one ever escaped the iteration.
            return _to_daily(s, kn, _di, how)

        k3_d, d3_d = td(k3), td(d3)
        m3_d, s3_d = td(m3), td(s3)
        r14_d = td(r14_3)

        # ---- the three not_topped legs, verbatim from confluence_tiers l.231-234 ----
        #   stoch_ob   = (k3n >= OB) or (d3n >= OB)   -> overbought zone
        #   stoch_bear = k3n < d3n                    -> rolled over / not crossed up
        #   macd_bear  = m3n < s3n                    -> 3D RSI-MACD below signal
        # (vectorized twin at l.424-427). `.fillna(False)` reproduces the scalar
        # float-NaN path, where every comparison against NaN is False.
        ob = ((k3_d >= OB) | (d3_d >= OB)).fillna(False).to_numpy()
        sb = (k3_d < d3_d).fillna(False).to_numpy()
        mb = (m3_d < s3_d).fillna(False).to_numpy()
        # ---- the RSI cap (confluence_tiers l.38 BUY_RSI_MAX=65; used l.223/l.420) ----
        # NOTE the deliberate asymmetry: production computes rsi_ok = (r14 < 65) and
        # THEN .fillna(False), so a warm-up NaN is "not ok". A warm-up bar is not a CAP
        # BREACH, so this label tests r14 >= 65 directly — the genuine veto print.
        rc = (r14_d >= BUY_RSI_MAX).fillna(False).to_numpy()

        # ---- freshness: per-day tick age of the last raw 3D RSI-MACD cross ----------
        # confluence_tiers l.430-432 computes exactly this as t1_ticks. It CANNOT be
        # read off tier_stream's `ticks` column: that column is populated only when a
        # tier is assigned (l.467-484), i.e. only when the name is ELIGIBLE — which is
        # never true for the freshness-expired cohort we are grading.
        mb3_d = _to_daily(_xup(m3, s3).fillna(False), sk3, di, "event")
        mb3_np = mb3_d.fillna(False).to_numpy().astype(bool)
        last_cross3 = _last_true_pos(mb3_np)
        ticks = _ticks_since_vec(sk3, last_cross3, di, FRESH_TICKS).astype(float)
        has_cross = last_cross3 >= 0
        ticks[~has_cross] = np.nan

        # ---- trend legs for section 3 (confluence_tiers l.404-406, and the identical
        # weekly formula in engine/signal_quality.py l.95-99 that feeds the live
        # verdict's weekly_bull/above200) --------------------------------------------
        ma200 = c.rolling(200).mean()
        above200 = (c > ma200).fillna(False).to_numpy()
        # WEEKLY leg off the DEEP series (see load_universe): the caches are too shallow
        # for _rsi_macd's 74-bar weekly warm-up on the large-cap sleeve.
        cw = (deep or {}).get(t)
        if cw is None or len(cw) < len(c):
            cw = c
        wk = cw.resample("W-FRI").last().dropna()
        wm, ws = _rsi_macd(wk)
        # COMPUTABILITY, tracked not assumed: _rsi_macd needs RSI_LEN(14)+BASE_LEN(60)
        # weekly bars before its first non-NaN. A name with a short series yields an
        # ALL-NaN weekly leg, which .fillna(False) would quietly turn into "not bullish"
        # — indistinguishable from a real bearish read. Names where the leg cannot be
        # computed are recorded and excluded from any cohort that depends on it.
        if bool(wm.notna().any()) and bool(ws.notna().any()):
            weekly_ok.append(t)
        wbull = ((wm >= ws).shift(1).reindex(di, method="ffill")
                 .fillna(False).astype(bool).to_numpy())

        st = ct.tier_stream(c)
        if st.empty:
            nt_stream = np.zeros(len(di), dtype=bool)
            elig = np.zeros(len(di), dtype=bool)
        else:
            nt_stream = st["not_topped"].reindex(di).fillna(False).to_numpy().astype(bool)
            elig = st["eligible"].reindex(di).fillna(False).to_numpy().astype(bool)

        def onto(arr, fill=False, _di=di):
            """Lift a per-name daily array onto the universe index (_di bound, see td)."""
            s = pd.Series(arr, index=_di).reindex(idx)
            return s.fillna(fill).to_numpy() if fill is not None else s.to_numpy()

        cols.append(t)
        acc["stoch_ob"].append(onto(ob))
        acc["stoch_bear"].append(onto(sb))
        acc["macd_bear"].append(onto(mb))
        acc["rsi_ge_cap"].append(onto(rc))
        acc["cross_ticks"].append(onto(ticks, fill=None))
        acc["has_cross"].append(onto(has_cross))
        acc["not_topped_stream"].append(onto(nt_stream))
        acc["eligible"].append(onto(elig))
        acc["above200"].append(onto(above200))
        acc["weekly_bull"].append(onto(wbull))
        acc["has_px"].append(onto(np.ones(len(di), dtype=bool)))

    panels = {k: pd.DataFrame(np.column_stack(v) if v else np.empty((n, 0)),
                              index=idx, columns=cols)
              for k, v in acc.items()}
    for k in ("stoch_ob", "stoch_bear", "macd_bear", "rsi_ge_cap", "has_cross",
              "not_topped_stream", "eligible", "above200", "weekly_bull", "has_px"):
        panels[k] = panels[k].astype(bool)
    panels["weekly_computable"] = pd.Series(
        [t in set(weekly_ok) for t in cols], index=cols)

    # ---- PER-LEG FIRE COUNTS: the dead-leg diagnostic (handoff §2 / numpy-bool trap).
    # A leg that never fires here is a defect in THIS instrument, and it is visible.
    legs = ("stoch_ob", "stoch_bear", "macd_bear", "rsi_ge_cap", "has_cross",
            "eligible", "above200", "weekly_bull")
    inrange = panels["has_px"].to_numpy()
    diag = {
        "universe_names": len(cols), "sessions": n,
        "in_range_name_days": int(inrange.sum()),
        "fire_counts_name_days": {k: int(panels[k].to_numpy().sum()) for k in legs},
        "fire_rate_pct_of_in_range": {
            k: _r(100.0 * panels[k].to_numpy().sum() / max(int(inrange.sum()), 1), 1)
            for k in legs},
        "names_firing_at_least_once": {
            k: int((panels[k].to_numpy().sum(axis=0) > 0).sum()) for k in legs},
    }
    # DEAD-LEG ALARM: a leg that never fires, or fires for no name, is a defect in THIS
    # instrument — never a finding about the tape. It is reported, not inferred.
    diag["dead_legs"] = [k for k in legs if diag["fire_counts_name_days"][k] == 0]
    wk_ok = int(panels["weekly_computable"].sum())
    diag["weekly_leg_computability"] = {
        "names_computable": wk_ok,
        "names_not_computable": int(len(cols) - wk_ok),
        "why": "_rsi_macd needs RSI_LEN(14)+BASE_LEN(60)=74 W-FRI bars before its first "
               "non-NaN; a shorter series yields an all-NaN weekly leg that .fillna(False) "
               "would render as a real bearish read. Cohorts depending on this leg are "
               "restricted to the computable names and say so.",
    }

    # ---- equality spot-check: inline legs vs the production stream ----------------
    # Scoped to IN-RANGE cells only: off a name's own history both sides are padded, so
    # comparing there would measure the padding, not the replication.
    inline_nt = ~(panels["stoch_ob"] | panels["stoch_bear"] | panels["macd_bear"])
    diff = (inline_nt.to_numpy() != panels["not_topped_stream"].to_numpy()) & inrange
    total = int(inrange.sum())
    mism = int(diff.sum())
    diag["equality_spot_check"] = {
        "basis": "inline ~(stoch_ob|stoch_bear|macd_bear) vs "
                 "confluence_tiers.tier_stream not_topped, IN-RANGE cells only",
        "cells": total, "mismatches": mism,
        "mismatch_pct": _r(100.0 * mism / total, 3) if total else None,
        "residual_note": "a small residual is expected on each name's warm-up head, where "
                         "tier_stream returns an empty frame (series shorter than "
                         f"MIN_HISTORY={ct.MIN_HISTORY}) and the inline legs still evaluate",
    }
    return panels, diag


def _bench_forward(idx: pd.DatetimeIndex, h: int) -> pd.Series:
    """SPY forward return over h sessions on the universe index."""
    sp = store.read("yahoo", BENCH)
    col = "close" if (sp is not None and "close" in sp.columns) else "close_price"
    s = sp[col].dropna()
    s.index = pd.to_datetime(s.index)
    s = s[s.index <= pd.Timestamp(REPRO_ASOF)]
    s = s.reindex(idx).ffill()
    return s.shift(-h) / s - 1.0


def gather(mask: np.ndarray, ex_spy: np.ndarray, ex_dm: np.ndarray,
           tickers: np.ndarray, dates: np.ndarray) -> tuple:
    """Pull (ticker, date, excess_spy_pp, excess_dm_pp) for every True cell that has
    a finite forward outcome."""
    ok = mask & np.isfinite(ex_spy) & np.isfinite(ex_dm)
    r, c = np.nonzero(ok)
    return (tickers[c], dates[r], ex_spy[ok] * 100.0, ex_dm[ok] * 100.0)


def section_veto_labels(px: pd.DataFrame, panels: dict, diag: dict,
                        sector_of: dict) -> dict:
    """(2) Every veto/exclusion reason as a label, graded FROM ITS VETO DAY."""
    idx = px.index
    n = len(idx)
    eval_hi = n - H_PRIMARY
    eval_lo = max(0, eval_hi - LOOK)
    tickers = np.asarray(px.columns, dtype=object)
    dates = np.asarray(idx)

    res: dict = {
        "question": "is any veto/exclusion label mispriced as a TIMING label?",
        "construction": "full universe from the three closes caches; each label graded "
                        "forward from the session on which it fired (the veto day)",
        "eval_window": [str(pd.Timestamp(idx[eval_lo]).date()),
                        str(pd.Timestamp(idx[eval_hi - 1]).date())],
        "window_note": f"last {LOOK} sessions with full H={H_PRIMARY} forward coverage; "
                       f"H={H_SUPPORT} stats use the subset of those days that also carry "
                       f"{H_SUPPORT} forward sessions (n reported separately per horizon)",
        "leg_diagnostics": diag,
        "w52_boundary": (
            "FRESHNESS SCOPE — this section grades ALL freshness-expiry prints as a "
            "label, regardless of whether the other legs passed. The "
            "expired-with-ALL-OTHER-LEGS-PASSING counterfactual is a DIFFERENT "
            "construction and is owned by the in-flight W5.2 instrument "
            "(fresh_ticks_extension_replay.py, sibling lane). Nothing here duplicates, "
            "replaces or pre-empts that measurement."),
    }

    labels = {
        "not_topped:stoch_ob": panels["stoch_ob"].to_numpy(),
        "not_topped:stoch_bear": panels["stoch_bear"].to_numpy(),
        "not_topped:macd_bear": panels["macd_bear"].to_numpy(),
        "not_topped:any_leg": (panels["stoch_ob"] | panels["stoch_bear"]
                               | panels["macd_bear"]).to_numpy(),
        "freshness_expired:all_prints": (
            panels["has_cross"].to_numpy()
            & (panels["cross_ticks"].to_numpy() > FRESH_TICKS)),
        "rsi_cap_ge65": panels["rsi_ge_cap"].to_numpy(),
        # control cohort: the names the gate ADMITTED that day
        "CONTROL:eligible_admitted": panels["eligible"].to_numpy(),
    }
    # exclusive attribution — the leg firing ALONE (so a verdict is not carried by
    # a co-firing sibling leg)
    ob, sb, mb = (panels["stoch_ob"].to_numpy(), panels["stoch_bear"].to_numpy(),
                  panels["macd_bear"].to_numpy())
    labels["not_topped:stoch_ob_ONLY"] = ob & ~sb & ~mb
    labels["not_topped:stoch_bear_ONLY"] = sb & ~ob & ~mb
    labels["not_topped:macd_bear_ONLY"] = mb & ~ob & ~sb

    per_h: dict = {}
    for h, tag in ((H_PRIMARY, f"H{H_PRIMARY}"), (H_SUPPORT, f"H{H_SUPPORT}")):
        fwd = (px.shift(-h) / px - 1.0)
        uni_med = fwd.median(axis=1)
        spy_fwd = _bench_forward(idx, h)
        ex_spy = fwd.sub(spy_fwd, axis=0).to_numpy()[eval_lo:eval_hi]
        ex_dm = fwd.sub(uni_med, axis=0).to_numpy()[eval_lo:eval_hi]
        d_slice = dates[eval_lo:eval_hi]
        out: dict = {}
        for lname, m in labels.items():
            mm = m[eval_lo:eval_hi]
            tk, dt, es, ed = gather(mm, ex_spy, ex_dm, tickers, d_slice)
            blk = stats_block(es, ed, tk)
            blk["fire_cells_in_window"] = int(mm.sum())
            if blk.get("n", 0) > 0:
                blk["sector_mix"] = sector_concentration(tk, sector_of)
            # onset-only robustness: the FIRST day of each contiguous run. The pooled
            # all-days cell double-counts a name that sits in a label for weeks; the
            # onset cut is the low-overlap read of the same label.
            prev = np.vstack([np.zeros((1, mm.shape[1]), dtype=bool), mm[:-1]])
            onset = mm & ~prev
            tko, _dto, eso, edo = gather(onset, ex_spy, ex_dm, tickers, d_slice)
            blk["onset_only"] = stats_block(eso, edo, tko)
            out[lname] = blk
        per_h[tag] = out

    res["by_horizon"] = per_h

    # ---- headline + half-split + admission costing on the PRIMARY horizon ---------
    prim = per_h[f"H{H_PRIMARY}"]
    ctrl = prim.get("CONTROL:eligible_admitted", {})
    ranked = [(k, v) for k, v in prim.items()
              if not k.startswith("CONTROL") and v.get("n", 0) >= THIN_N
              and v.get("per_name_first_median_pp") is not None]
    ranked.sort(key=lambda kv: kv[1]["per_name_first_median_pp"], reverse=True)
    res["ranked_labels_H10_by_per_name_median"] = [
        {"label": k, "n": v["n"], "per_name_first_median_pp": v["per_name_first_median_pp"],
         "median_excess_spy_pp": v["median_excess_spy_pp"],
         "median_excess_dm_pp": v["median_excess_dm_pp"],
         "loser_rate_pct": v["loser_rate_pct"]} for k, v in ranked]
    res["control_admitted_H10"] = {
        "n": ctrl.get("n"), "per_name_first_median_pp": ctrl.get("per_name_first_median_pp"),
        "median_excess_spy_pp": ctrl.get("median_excess_spy_pp"),
        "median_excess_dm_pp": ctrl.get("median_excess_dm_pp"),
        "loser_rate_pct": ctrl.get("loser_rate_pct"),
        "note": "the cohort the gate ADMITTED — the bar any veto label must clear before "
                "'this veto is mispriced' means anything",
    }

    # half-split on each label that beats the admitted control on per-name median
    fwd = (px.shift(-H_PRIMARY) / px - 1.0)
    uni_med = fwd.median(axis=1)
    spy_fwd = _bench_forward(idx, H_PRIMARY)
    ex_spy = fwd.sub(spy_fwd, axis=0).to_numpy()[eval_lo:eval_hi]
    ex_dm = fwd.sub(uni_med, axis=0).to_numpy()[eval_lo:eval_hi]
    d_slice = dates[eval_lo:eval_hi]
    hs: dict = {}
    ctrl_med = ctrl.get("per_name_first_median_pp")
    for lname, blk in ranked:
        if ctrl_med is None or blk["per_name_first_median_pp"] <= ctrl_med:
            continue
        tk, dt, es, ed = gather(labels[lname][eval_lo:eval_hi], ex_spy, ex_dm,
                                tickers, d_slice)
        hs[lname] = half_split(dt, es, ed, tk)
    res["half_split_labels_beating_control"] = hs or {
        "note": "no veto label beat the admitted control on per-name-first median at "
                "H=10 — nothing to stress-test"}

    # ---- widening cost, both directions (G0.7 framing for an ADMISSION label) -----
    # A veto label's implied action is to WIDEN (stop vetoing). The honest price is what
    # the cohort brings with it: its own winners AND its own losers, against the control.
    widen: dict = {}
    for lname, blk in prim.items():
        if lname.startswith("CONTROL") or blk.get("n", 0) == 0:
            continue
        widen[lname] = {
            "n_admitted_if_widened": blk["n"],
            "loser_rate_pct": blk.get("loser_rate_pct"),
            "win_rate_pct": blk.get("win_rate_pct"),
            "median_excess_spy_pp": blk.get("median_excess_spy_pp"),
            "vs_control_per_name_median_pp": (
                _r(blk["per_name_first_median_pp"] - ctrl_med)
                if (ctrl_med is not None
                    and blk.get("per_name_first_median_pp") is not None) else None),
        }
    res["widening_cost_vs_control_H10"] = widen
    return res


# ------------------------------------------------- section 3: the ran lane --
def section_ran_lane(px: pd.DataFrame, panels: dict, sector_of: dict) -> dict:
    """(3) The ran/leaders lane, forward-graded from its OWN lane-entry anchor.

    Census first. The US board carries TWO distinct 'ran' objects and they have
    very different evidence status — the distinction is the finding:

      3a  STAGE-ran — a BUY-lane row whose entry_status lands in
          engine/us_board_rank._RAN_STATUSES (l.136). These rows ARE in the ledger
          and ARE gradeable today.
      3b  the ran ARRAY — engine/us_board_rank.build_ran_rows / ran_admits (l.1055),
          a separate lane of names the gate no longer admits. It was added
          2026-08-02 (scripts/grade_us_board.py:164-168) and the snapshot store
          ends 2026-07-31, so it has ZERO point-in-time history. It is
          RECONSTRUCTED here from its own published rules and labelled a proxy.
    """
    res: dict = {"question": "how does the US ran cohort grade from its own anchor?"}

    # ---------- census of what actually exists -----------------------------------
    led = pd.read_parquet("data/us_board_ledger/retro_grades.parquet")
    lane_census = led["lane"].value_counts().to_dict()
    snap_lanes: dict = {}
    try:
        import collections
        cnt: dict = collections.defaultdict(int)
        d_by_lane: dict = collections.defaultdict(set)
        with open("data/us_board_ledger/snapshots.jsonl") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                for lane in ("buy", "watch", "leaders", "ran", "laggards", "laggard"):
                    v = d.get(lane)
                    if isinstance(v, list) and v:
                        cnt[lane] += len(v)
                        d_by_lane[lane].add(d.get("as_of"))
        snap_lanes = {k: {"name_rows": int(v), "dates": len(d_by_lane[k]),
                          "range": [min(d_by_lane[k]), max(d_by_lane[k])]}
                      for k, v in cnt.items()}
    except OSError as e:
        snap_lanes = {"error": str(e)}

    res["census"] = {
        "ledger_lanes": {str(k): int(v) for k, v in lane_census.items()},
        "snapshot_lanes": snap_lanes,
        "COVERAGE_DEBT": (
            "The production 'ran' ARRAY has NO point-in-time history at all: it is "
            "absent from every row of retro_grades.parquet and from every snapshot in "
            "snapshots.jsonl. scripts/grade_us_board.py:164-168 records why — the lane "
            "was added 2026-08-02 as a NEW forward cohort, and the snapshot store ends "
            f"{REPRO_ASOF}. 'leaders' is in the same position for a shorter reason: 4 "
            "board dates (2026-07-28..07-31), none of them matured at H=10 as of this "
            "run. WHAT MUST ACCRUE: ~10 further board sessions carrying the `ran` key, "
            "plus H=10 maturity on the earliest of them — roughly 4 trading weeks from "
            "2026-08-02 — before 3b can be graded on PRODUCTION rows rather than the "
            "reconstruction below."),
    }

    # ---------- 3a: STAGE-ran inside the buy lane (real ledger rows) --------------
    ran_statuses = sorted(ubr._RAN_STATUSES)
    res["ran_statuses_source"] = {
        "value": ran_statuses,
        "source": "engine/us_board_rank.py:136 _RAN_STATUSES (bucketed by stage_of, l.419)",
    }
    a: dict = {"basis": "BUY-lane ledger rows whose entry_status buckets to STAGE_RAN; "
                        "anchor = the board admission date on the row (its own entry)"}
    for h, tag in ((H_PRIMARY, f"H{H_PRIMARY}"), (H_SUPPORT, f"H{H_SUPPORT}")):
        df = load_ledger(h)
        if df.empty:
            a[tag] = {"n": 0}
            continue
        m = df["entry_status"].isin(ran_statuses)
        blk = stats_block(df.loc[m, "excess_pp"].to_numpy(), df.loc[m, "excess_dm"].to_numpy(),
                          df.loc[m, "ticker"].tolist())
        blk["per_status"] = {
            s: stats_block(df.loc[df["entry_status"] == s, "excess_pp"].to_numpy(),
                           df.loc[df["entry_status"] == s, "excess_dm"].to_numpy(),
                           df.loc[df["entry_status"] == s, "ticker"].tolist())
            for s in ran_statuses if int((df["entry_status"] == s).sum()) > 0}
        blk["rest_of_buy_lane"] = stats_block(
            df.loc[~m, "excess_pp"].to_numpy(), df.loc[~m, "excess_dm"].to_numpy(),
            df.loc[~m, "ticker"].tolist())
        if int(m.sum()) >= 4:
            blk["half_split"] = half_split(df.loc[m, "entry_date"], df.loc[m, "excess_pp"],
                                           df.loc[m, "excess_dm"], df.loc[m, "ticker"])
            blk["sector_mix"] = sector_concentration(df.loc[m, "ticker"].tolist(), sector_of)
        a[tag] = blk
    res["a_stage_ran_from_ledger"] = a

    # ---------- 3b: PIT reconstruction of the ran ARRAY ---------------------------
    idx = px.index
    n = len(idx)
    eval_hi = n - H_PRIMARY
    eval_lo = max(0, eval_hi - LOOK)
    tickers = np.asarray(px.columns, dtype=object)
    dates = np.asarray(idx)

    ticks = panels["cross_ticks"].to_numpy()
    with np.errstate(invalid="ignore"):
        in_window = (ticks >= ubr.RAN_TICKS_MIN) & (ticks <= ubr.RAN_TICKS_MAX)
    in_window = np.nan_to_num(in_window, nan=False).astype(bool)
    # ran_admits (engine/us_board_rank.py:1078-1089): eligible is False AND ticks in
    # [RAN_TICKS_MIN, RAN_TICKS_MAX] AND above200 AND weekly_bull AND not marked down.
    # The 'dir == down' leg has no close-only twin and is NOT applied — stated below.
    # Restrict to names whose WEEKLY leg is computable at all: on a name with too little
    # history the leg is all-NaN, which .fillna(False) renders as "weekly not bullish" —
    # indistinguishable from a genuine bearish read, and it would silently delete that
    # whole sleeve from the lane rather than report it. Excluded names are counted below.
    wk_ok = panels["weekly_computable"].reindex(px.columns).fillna(False).to_numpy()
    ran_mask = (~panels["eligible"].to_numpy()
                & in_window
                & panels["above200"].to_numpy()
                & panels["weekly_bull"].to_numpy()
                & wk_ok[None, :])
    # lane-ENTRY anchor: the first day of each contiguous run in the lane
    prev = np.vstack([np.zeros((1, ran_mask.shape[1]), dtype=bool), ran_mask[:-1]])
    onset = ran_mask & ~prev

    b: dict = {
        "basis": "close-only PIT reconstruction of engine/us_board_rank.ran_admits "
                 "(l.1055) from its published rules; graded from the LANE-ENTRY day "
                 "(first session of each contiguous run), which is the lane's own anchor",
        "rules_applied": {
            "eligible_is_False": "engine.confluence_tiers.tier_stream eligible column",
            "ticks_window": [int(ubr.RAN_TICKS_MIN), int(ubr.RAN_TICKS_MAX)],
            "above200": "close > 200d MA (daily grid)",
            "weekly_bull": "W-FRI RSI-MACD m>=s, shifted 1 — the identical formula the "
                           "live verdict uses at engine/signal_quality.py:95-97",
        },
        # Each caveat is ONE parenthesised string: implicit concatenation inside a list
        # is how a missing comma silently fuses two entries into one.
        "PROXY_CAVEATS": [
            ("tier_stream's `eligible` is the close-only twin of the production verdict; "
             "the live board's T1 comes from the §7 held master, of which the raw-3D-cross "
             "fallback used here is a superset (confluence_tiers.tier_stream docstring)."),
            ("the production array also EXCLUDES names already on buy/watch/leaders/"
             "laggards (scripts/build_stock_library.py:4138-4141) and caps at RAN_CAP="
             f"{ubr.RAN_CAP}; neither is applied here, so this cohort is a SUPERSET."),
            ("the `dir == 'down'` leg of ran_admits reads a board row field with no "
             "close-only twin and is not applied."),
            ("above200/weekly_bull are computed on the DAILY grid; production samples the "
             "same formulas onto the 3B grid (signal_quality l.95-99)."),
        ],
        "weekly_leg_universe_bound": {
            "names_in_scope": int(wk_ok.sum()),
            "names_excluded_leg_uncomputable": int(len(px.columns) - wk_ok.sum()),
            "note": "the ran gate REQUIRES weekly_bull, so names whose weekly leg cannot "
                    "be computed are out of scope for 3b rather than counted as bearish",
        },
    }
    for h, tag in ((H_PRIMARY, f"H{H_PRIMARY}"), (H_SUPPORT, f"H{H_SUPPORT}")):
        fwd = (px.shift(-h) / px - 1.0)
        uni_med = fwd.median(axis=1)
        spy_fwd = _bench_forward(idx, h)
        ex_spy = fwd.sub(spy_fwd, axis=0).to_numpy()[eval_lo:eval_hi]
        ex_dm = fwd.sub(uni_med, axis=0).to_numpy()[eval_lo:eval_hi]
        d_slice = dates[eval_lo:eval_hi]
        tk, dt, es, ed = gather(onset[eval_lo:eval_hi], ex_spy, ex_dm, tickers, d_slice)
        blk = stats_block(es, ed, tk)
        blk["lane_entry_events_in_window"] = int(onset[eval_lo:eval_hi].sum())
        blk["lane_days_in_window"] = int(ran_mask[eval_lo:eval_hi].sum())
        if blk.get("n", 0) > 0:
            blk["sector_mix"] = sector_concentration(tk, sector_of)
            blk["half_split"] = half_split(dt, es, ed, tk)
        # the admitted control on the same window/horizon
        tkc, _dtc, esc, edc = gather(panels["eligible"].to_numpy()[eval_lo:eval_hi],
                                    ex_spy, ex_dm, tickers, d_slice)
        blk["control_admitted"] = stats_block(esc, edc, tkc)
        b[tag] = blk
    b["eval_window"] = [str(pd.Timestamp(idx[eval_lo]).date()),
                        str(pd.Timestamp(idx[eval_hi - 1]).date())]

    # fidelity spot-check: the vectorized mask vs the REAL gate function ------------
    rng = np.random.default_rng(11)
    rows = rng.integers(eval_lo, eval_hi, size=4000)
    colsi = rng.integers(0, len(tickers), size=4000)
    agree = disagree = 0
    for r_i, c_i in zip(rows, colsi):
        tv = ticks[r_i, c_i]
        verdict = {
            "eligible": bool(panels["eligible"].to_numpy()[r_i, c_i]),
            # bool()/int() on purpose: `ran_admits` uses `is True`, which a numpy bool
            # would silently fail (memory: numpy-bool-is-true-deadens-a-feature-leg).
            # Production is safe because engine/signal_quality.py:287 wraps both flags
            # in bool() before they reach the verdict.
            "ticks": None if not np.isfinite(tv) else int(tv),
            "above200": bool(panels["above200"].to_numpy()[r_i, c_i]),
            "weekly_bull": bool(panels["weekly_bull"].to_numpy()[r_i, c_i]),
        }
        if bool(ubr.ran_admits(verdict, {})) == bool(ran_mask[r_i, c_i]):
            agree += 1
        else:
            disagree += 1
    b["gate_equality_spot_check"] = {
        "sampled_cells": int(agree + disagree), "agree": agree, "disagree": disagree,
        "basis": "vectorized mask vs engine.us_board_rank.ran_admits called on a "
                 "reconstructed verdict for the same cell",
    }
    res["b_ran_array_reconstructed"] = b
    return res


# ------------------------------------------------------------------ readout --
def build_readout(res: dict) -> dict:
    """A compact, MACHINE-DERIVED headline per section: the numbers a reader needs
    plus the stability flag that says whether the number survived its own guard.
    Nothing here is authored — every value is lifted from the tables above."""
    out: dict = {"note": "derived from the tables above; no value is hand-entered"}

    # ---- 1: is the ladder ordered? -------------------------------------------
    s1 = res["section_1_by_entry_status"].get("H10_primary", {})
    ranked = s1.get("ranked_non_thin_by_per_name_median", [])
    ladder = s1.get("by_entry_status", {})
    out["section_1"] = {
        "n": s1.get("rows"), "names": s1.get("names"), "dates": s1.get("admission_dates"),
        "base_per_name_median_pp": (s1.get("base") or {}).get("per_name_first_median_pp"),
        "base_loser_rate_pct": (s1.get("base") or {}).get("loser_rate_pct"),
        "non_thin_order_best_to_worst": [r["status"] for r in ranked],
        "buy_now_cell": {k: (ladder.get("buy_now") or {}).get(k)
                         for k in ("n", "loser_rate_pct", "median_excess_spy_pp",
                                   "per_name_first_median_pp", "thin")},
        "thin_cells_whose_sign_differs_at_H5": [
            f["status"] for f in (res["section_1_by_entry_status"]
                                  .get("H5_maturity_crosscheck", {})
                                  .get("statuses_whose_sign_differs_vs_H10", []))],
        "null_status_rows": (s1.get("status_census") or {}).get("<NULL>"),
        "null_status_share_pct": _r(
            100.0 * ((s1.get("status_census") or {}).get("<NULL>", 0)
                     / max(s1.get("rows") or 1, 1)), 1),
        "headline_delta_pp": (s1.get("headline") or {}).get("delta_per_name_median_pp"),
    }

    # ---- 2: is any veto label mispriced? -------------------------------------
    s2 = res["section_2_veto_labels"]
    ctrl = s2.get("control_admitted_H10", {})
    hs = s2.get("half_split_labels_beating_control", {})
    beat = [k for k in hs if isinstance(hs[k], dict) and "first_half" in hs[k]]
    flipped = [k for k in beat if hs[k].get("sign_flip_across_halves") is True]
    out["section_2"] = {
        "eval_window": s2.get("eval_window"),
        "control_admitted_per_name_median_pp": ctrl.get("per_name_first_median_pp"),
        "control_admitted_loser_rate_pct": ctrl.get("loser_rate_pct"),
        "labels_beating_control_H10": beat,
        "of_which_sign_flip_across_halves": flipped,
        "max_edge_over_control_pp": max(
            [v.get("vs_control_per_name_median_pp") or -99
             for v in (s2.get("widening_cost_vs_control_H10") or {}).values()] or [None]),
        "dead_legs": (s2.get("leg_diagnostics") or {}).get("dead_legs"),
        "leg_replication_mismatches": (
            (s2.get("leg_diagnostics") or {}).get("equality_spot_check") or {}
        ).get("mismatches"),
    }

    # ---- 3: how does the ran cohort grade? -----------------------------------
    s3 = res["section_3_ran_lane"]
    a10 = (s3.get("a_stage_ran_from_ledger") or {}).get("H10", {})
    rest = a10.get("rest_of_buy_lane", {})
    b10 = (s3.get("b_ran_array_reconstructed") or {}).get("H10", {})
    ahs = a10.get("half_split", {})
    bhs = b10.get("half_split", {})
    out["section_3"] = {
        "a_stage_ran": {
            "n": a10.get("n"), "names": a10.get("names"),
            "loser_rate_pct": a10.get("loser_rate_pct"),
            "per_name_first_median_pp": a10.get("per_name_first_median_pp"),
            "vs_rest_of_buy_lane": {
                "rest_n": rest.get("n"), "rest_loser_rate_pct": rest.get("loser_rate_pct"),
                "rest_per_name_median_pp": rest.get("per_name_first_median_pp"),
                "delta_per_name_median_pp": _r(
                    (a10.get("per_name_first_median_pp") or 0)
                    - (rest.get("per_name_first_median_pp") or 0)),
            },
            "half_split_sign_flip": ahs.get("sign_flip_across_halves"),
        },
        "b_reconstructed_ran_array": {
            "lane_entry_events": b10.get("lane_entry_events_in_window"),
            "names": b10.get("names"),
            "per_name_first_median_pp": b10.get("per_name_first_median_pp"),
            "control_per_name_median_pp": (b10.get("control_admitted") or {}
                                           ).get("per_name_first_median_pp"),
            "half_split_sign_flip": bhs.get("sign_flip_across_halves"),
            "gate_spot_check_disagree": (
                (s3.get("b_ran_array_reconstructed") or {}).get(
                    "gate_equality_spot_check") or {}).get("disagree"),
        },
        "production_ran_array_pit_rows": 0,
    }
    return out


# --------------------------------------------------------------------- main --
def main() -> None:
    sector_of = _sector_map()
    res: dict = {
        "instrument": "US label-grading battery (CN->US handoff §1)",
        "repro_asof": REPRO_ASOF,
        "loser_def_pp": LOSER_PP,
        "horizons": {"primary": H_PRIMARY, "supporting": H_SUPPORT},
        "direction_fence": (
            "CN's tape mean-reverts; the US tape measured confirmation-positive. No "
            "direction is assumed anywhere in this instrument — the numbers below "
            "decide, and thin cells are called thin rather than read."),
        "scope": "MEASUREMENT ONLY — no gate/board/engine change follows from this file",
    }
    res["section_1_by_entry_status"] = section_entry_status(sector_of)

    px, deep, prov = load_universe()
    panels, diag = build_label_panels(px, deep)
    res["universe"] = {
        "names": int(px.shape[1]), "sessions": int(px.shape[0]),
        "range": [str(px.index.min().date()), str(px.index.max().date())],
        "min_history_sessions": MIN_HIST,
        "provenance": prov,
        "sector_map_coverage_pct": _r(
            100.0 * np.mean([str(t) in sector_of for t in px.columns]), 1),
    }
    res["section_2_veto_labels"] = section_veto_labels(px, panels, diag, sector_of)
    res["section_3_ran_lane"] = section_ran_lane(px, panels, sector_of)
    res["readout"] = build_readout(res)

    with open(OUT, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")   # CLI-only: never at import time (repo guard)
    main()
