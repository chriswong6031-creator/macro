"""W3-A · ABNORMAL-TURNOVER cross-sectional signal — Phase-0 validation (the flagship of the
volume program, F7). NOTHING here is wired to any page/board/rank regardless of outcome — pure
research + measurement.

Mechanism (ashare-signal-research §A). In a retail tape a spike in turnover marks the peak of an
attention / overreaction cycle: names with *abnormally high* recent turnover subsequently
UNDERPERFORM (the demand shock unwinds), and *low/stable* abnormal turnover OUTPERFORMS. It is the
microstructure sibling of the (validated) short-term reversal edge, on the VOLUME plane instead of
the price plane. External evidence: "Anomalies in the China A-share market" (2000-2019) — abnormal
turnover NEGATIVELY predicts returns; the LOW-abnormal-turnover long leg earns +1.24%/mo, t=3.35 (EW).

PROXY LIMITATION (pre-registered, honest). The paper's abnormal turnover uses the TURNOVER RATIO
(shares traded / free-float shares). We have no historical per-name float-share series, so we
pre-register a VOLUME-based proxy:

    abn_turn = ln( mean(volume, last 21d) / mean(volume, trailing 252d skip the last 21d) )

i.e. recent volume relative to its own trailing-year baseline, per name. This differs from the true
turnover ratio in that (a) it omits the float normalisation — but abn_turn is a WITHIN-NAME ratio so a
constant float cancels; float only matters if it CHANGED materially inside the 252d window (equity
issuance / large unlock), which biases a minority of names; (b) it is a share-VOLUME z, not a
turnover-ratio z. For the cross-sectional RANK the paper relies on, a within-name volume ratio is the
closest float-free proxy and is exactly what the signal-research doc pre-registered ("volume-z is a
clean fallback that needs nothing else"). Numbers here therefore test the MECHANISM on our substrate,
they do not reproduce the paper's point estimate.

MEASUREMENT CONSTITUTION (binding — research/china_alpha/CHINA_ALPHA_MASTERPLAN_BY_FABLE.md §4):
  * Substrate      = data/china_stocks_raw/ (append-only, survivorship-CLEAN, real per-name volume to
                     2008; has open/high/low so a T+1 fill is buildable). NEVER the trimmed
                     china_search close-only panel.
  * Benchmark      = CSI300-relative excess, always (510300.SS via lib.store; history starts
                     2012-05-04, which bounds the excess-return backtest window).
  * Fill realism   = T+1 (H+L)/2 entry; EXCLUDE locked-limit rows (high==low==close) at the entry bar.
                     Report close-to-close ALONGSIDE the fill-realistic number (the T+1 grading tax).
  * Split hygiene  = the raw plane is UNADJUSTED (splits / ex-div appear as single-day jumps). Daily
                     returns with |ret| > 0.25 (beyond the physical A-share ±20% limit envelope) are
                     corporate-action artifacts, not returns; they are zeroed before compounding the
                     forward return. (Contamination measured ~0.19% of 21d windows.)
  * Splits         = time-HALF (early/late) and pre/post-2024.
  * Placebo        = 2000-permutation label shuffle (seed-fixed) on the primary L/S spread.
  * Positive ctrl  = the VALIDATED 3-month within-sector reversal signal through the SAME harness must
                     reproduce a positive low-minus-high spread (proves the instrument is live).

UNIVERSE FILTERS (pre-registered):
  * >= 400 trading days of history (stable trailing-252d baseline + rebalance grid room).
  * ADV floor for fill realism: trailing-60d median (close*volume) >= 1e8 yuan (~US$14M) at the
    rebalance bar (a monthly-rebalance basket can transact this).
  * EXCLUDE names whose locked-limit days exceed 20% of their history (structurally unfillable tape).

DESIGN (pre-registered):
  * Monthly rebalance (calendar month-end -> last trading day on/before).
  * DECILES on abn_turn (cross-sectional, and a sector-neutral robustness variant).
  * PRIMARY metric = LOW-minus-HIGH decile L/S, CSI300-relative 21d-forward, HAC (Newey-West) t.
    "Low-minus-high" because the paper's edge is the LOW-abnormal-turnover long leg outperforming.
  * T1 decile spread full + splits; T2 orthogonality vs within-sector 3M reversal (residualize
    abn_turn on rev3 each rebalance -> residual spread; if residual |t| < 2 the signal is
    REDUNDANT-WITH-REVERSAL and the verdict says so regardless of raw t); T3 monotonicity across
    deciles; T4 2000-perm placebo; T5 positive control (reversal through same harness); T6 fill vs
    close-to-close gap.

PRE-REGISTERED VERDICT (fixed BEFORE running):
  GO     : primary L/S (fill-realistic) HAC |t| >= 3 on the FULL window AND spread sign-stable across
           BOTH era splits (early/late AND pre/post-2024 same sign), AND the T2 RESIDUAL spread |t| >= 2
           (adds information beyond reversal), AND T5 positive control fires (reversal spread > 0).
  ACCRUE : 2 <= |t| < 3 full-sample, OR |t| >= 3 but only in one era (era-only / not split-stable),
           OR residual |t| in [2,3) while raw is strong — a forward ledger opens, nothing wired.
  NO-GO  : |t| < 2 full-sample; OR sign-unstable across BOTH splits; OR T2 residual |t| < 2
           (REDUNDANT-WITH-REVERSAL) regardless of raw t; OR T5 positive control fails (instrument dead
           -> the whole run is void).

Run: PYTHONPATH=$PWD python3 -m scripts.china_turnover_phase0
Deterministic (seeded rng); no network; read-only on data/ (writes only reports/).
"""
from __future__ import annotations

import glob
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from lib import config, store  # noqa: E402

RAW_DIR = "data/china_stocks_raw"
MEMBERS = "data/china_search/members.parquet"
CSI300 = ("china", "510300.SS")
JUNK = "A-share"

MIN_HISTORY = 400          # trading days
ADV_FLOOR = 1e8            # yuan, trailing-60d median close*volume
LOCKED_MAX_FRAC = 0.20     # exclude names with >20% locked-limit days
SPLIT_CAP = 0.25           # |daily ret| beyond this = corporate-action artifact -> zeroed
FWD = 21                   # forward holding horizon (trading days)
BASE_LOOK = 252            # trailing baseline window for abn_turn
REC_LOOK = 21              # recent window for abn_turn
PERM = 2000                # placebo permutations
SEED = 3                   # deterministic (nod to W3 / F7)
N_DECILES = 10


# ----------------------------------------------------------------------------- signal math
def abn_turn(volume: pd.Series, rec: int = REC_LOOK, base: int = BASE_LOOK) -> pd.Series:
    """abn_turn = ln( mean(vol, last `rec` d) / mean(vol, trailing `base` d skipping last `rec`) ).

    Pure function of a single name's volume series; the unit tests pin this on synthetic series
    with known abnormal windows. NaN until `base` observations exist; +inf/-inf (a zero-mean
    baseline or recent window) mapped to NaN so it never enters a rank.
    """
    v = volume.astype(float)
    recent = v.rolling(rec, min_periods=rec).mean()
    # trailing baseline that EXCLUDES the recent window: mean over the `base` days ending `rec` ago
    baseline = v.shift(rec).rolling(base, min_periods=max(base // 2, 60)).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.log(recent / baseline)
    return out.replace([np.inf, -np.inf], np.nan)


def clean_daily_ret(close: pd.Series, cap: float = SPLIT_CAP) -> pd.Series:
    """Daily simple return with split/ex-div artifacts (|ret|>cap) zeroed (treated as non-events).

    Genuine NaNs (the leading return, gaps) are PRESERVED as NaN — only real |ret|>cap moves are
    zeroed — so downstream rolling products keep their NaN alignment.
    """
    r = close.pct_change()
    return r.mask(r.abs() > cap, 0.0)


# ----------------------------------------------------------------------------- HAC t
def hac_t(x: np.ndarray, lags: int = 4) -> float:
    """Newey-West HAC t-stat of the mean of a series (H0: mean == 0). Same estimator family as the
    sibling probes (c_hc_readthrough / china_global_theme), specialised to a mean."""
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 12:
        return float("nan")
    mu = x.mean()
    e = x - mu
    s = float(e @ e)
    for l in range(1, lags + 1):
        w = 1 - l / (lags + 1)
        s += 2 * w * float(e[l:] @ e[:-l])
    var_mean = s / (n * n)
    return float(mu / np.sqrt(var_mean)) if var_mean > 0 else float("nan")


def _ann_sharpe(x: pd.Series) -> float:
    return float(x.mean() / x.std() * np.sqrt(12)) if len(x) > 1 and x.std() else 0.0


def _maxdd(x: pd.Series) -> float:
    cum = (1 + x).cumprod()
    return float((cum / cum.cummax() - 1).min())


# ----------------------------------------------------------------------------- panel build
def _read_universe(root: Path):
    """Load the raw plane into aligned frames, apply the pre-registered universe filters, and
    compute clean forward returns + fill-realistic entries. Returns dict of frames."""
    members = pd.read_parquet(root / MEMBERS)
    sector_all = pd.Series({t: (s if s != JUNK else "—") for t, s in members["sector"].items()})

    closes, fwd_c2c_parts, fwd_fill_parts, vols = {}, {}, {}, {}
    excluded = {"history": 0, "locked": 0, "adv": 0, "no_sector": 0}
    for f in sorted(glob.glob(str(root / RAW_DIR / "*.parquet"))):
        tkr = Path(f).stem
        sec = sector_all.get(tkr, "—")
        if sec == "—":
            excluded["no_sector"] += 1
            continue
        df = pd.read_parquet(f)
        if len(df) < MIN_HISTORY:
            excluded["history"] += 1
            continue
        c, hi, lo, vol = df["close"], df["high"], df["low"], df["volume"]
        locked = (hi == lo) & (lo == c)
        if float(locked.mean()) > LOCKED_MAX_FRAC:
            excluded["locked"] += 1
            continue
        adv = (c * vol).tail(60).median()
        if not (pd.notna(adv) and adv >= ADV_FLOOR):
            excluded["adv"] += 1
            continue
        # clean daily return -> compounded forward FWD-day return (close-to-close), split-safe
        r = clean_daily_ret(c)
        fwd_c2c = (1 + r).shift(-1).rolling(FWD).apply(np.prod, raw=True).shift(-(FWD - 1)) - 1
        # fill-realistic: enter at T+1 (H+L)/2, exit at close of T+FWD; locked-limit entry rows unfillable
        entry_px = ((hi + lo) / 2).shift(-1)                     # next bar's (H+L)/2
        t1_locked = locked.shift(-1).reindex(c.index).fillna(True).astype(bool)  # T+1 locked => unfillable
        entry_px = entry_px.where(~t1_locked)                    # drop rows whose T+1 is locked
        # split-safe exit level: compound clean returns FWD days forward from the signal close
        exit_lvl = c * (1 + r).shift(-1).rolling(FWD).apply(np.prod, raw=True).shift(-(FWD - 1))
        fwd_fill = exit_lvl / entry_px - 1
        closes[tkr] = c
        vols[tkr] = vol
        fwd_c2c_parts[tkr] = fwd_c2c
        fwd_fill_parts[tkr] = fwd_fill

    px = pd.DataFrame(closes).sort_index()
    vol = pd.DataFrame(vols).reindex(px.index)
    fwd_c2c = pd.DataFrame(fwd_c2c_parts).reindex(px.index)
    fwd_fill = pd.DataFrame(fwd_fill_parts).reindex(px.index)
    sector = sector_all.reindex(px.columns)
    return {"px": px, "vol": vol, "fwd_c2c": fwd_c2c, "fwd_fill": fwd_fill,
            "sector": sector, "excluded": excluded}


def _benchmark_fwd(root: Path, idx: pd.DatetimeIndex) -> pd.Series:
    """CSI300 clean FWD-day forward return aligned to the panel index (the excess benchmark)."""
    b = store.read(*CSI300)
    if b is None or "close" not in b.columns:
        raise SystemExit("CSI300 benchmark (510300.SS) missing — cannot compute excess.")
    bc = b["close"].copy()
    bc.index = pd.to_datetime(bc.index)
    bc = bc.reindex(idx).ffill()
    br = clean_daily_ret(bc)
    return (1 + br).shift(-1).rolling(FWD).apply(np.prod, raw=True).shift(-(FWD - 1)) - 1


# ----------------------------------------------------------------------------- backtest core
def _grid(idx: pd.DatetimeIndex) -> list:
    g = [idx[idx <= me][-1] for me in pd.date_range(idx.min(), idx.max(), freq="ME") if len(idx[idx <= me])]
    return [d for d in g if idx.get_loc(d) >= BASE_LOOK + REC_LOOK and idx.get_loc(d) + FWD < len(idx)]


def _rebalance_spreads(grid, sig_frame, fwd_frame, bench_fwd, sector, *,
                       sector_neutral=False, residual_on=None, low_minus_high=True):
    """For each rebalance: rank the (optionally sector-neutralised / residualised) signal into
    deciles, take EW CSI300-relative forward return of the LOW and HIGH deciles, return the
    per-rebalance low-minus-high spread series and per-decile excess series.

    residual_on: a signal frame (e.g. rev3) to cross-sectionally residualise `sig` against each
    rebalance (OLS of sig on residual_on within the cross-section) — the T2 orthogonality test.
    """
    spread, decile_exc = [], {q: [] for q in range(N_DECILES)}
    for d in grid:
        if d not in fwd_frame.index:
            continue
        fr = fwd_frame.loc[d]
        bx = float(bench_fwd.get(d, np.nan))
        if not np.isfinite(bx):
            continue
        s = sig_frame.loc[d].copy()
        common = s.dropna().index.intersection(fr.dropna().index)
        if residual_on is not None:
            rv = residual_on.loc[d]
            common = common.intersection(rv.dropna().index)
        if sector_neutral:
            common = common.intersection(sector.dropna().index)
        if len(common) < 100:                        # need enough names for 10 deciles
            continue
        s = s.reindex(common)
        exc = fr.reindex(common) - bx                # CSI300-relative excess
        if sector_neutral:
            s = s - s.groupby(sector.reindex(common)).transform("mean")
        if residual_on is not None:
            rv = residual_on.loc[d].reindex(common)      # the reversal signal row for THIS rebalance
            m = (s.notna() & rv.notna()).values
            if int(m.sum()) < 100:
                continue
            X = np.column_stack([np.ones(int(m.sum())), rv.values[m]])
            beta = np.linalg.lstsq(X, s.values[m], rcond=None)[0]
            resid_arr = np.full(len(s), np.nan)
            resid_arr[m] = s.values[m] - X @ beta
            s = pd.Series(resid_arr, index=s.index)
        s = s.dropna()
        exc = exc.reindex(s.index).dropna()
        s = s.reindex(exc.index)
        if len(s) < 100:
            continue
        ranks = s.rank(method="first")
        q = ((ranks - 1) / len(s) * N_DECILES).astype(int).clip(0, N_DECILES - 1)
        means = exc.groupby(q).mean()
        for dq in range(N_DECILES):
            if dq in means.index:
                decile_exc[dq].append(float(means[dq]))
        if 0 in means.index and (N_DECILES - 1) in means.index:
            lo, hi = float(means[0]), float(means[N_DECILES - 1])
            spread.append(lo - hi if low_minus_high else hi - lo)
    return pd.Series(spread, dtype=float), {q: pd.Series(v, dtype=float) for q, v in decile_exc.items()}


def _spread_stats(s: pd.Series) -> dict:
    if len(s) < 12:
        return {"n": len(s), "error": "thin"}
    return {"n": len(s), "mean_pct": round(float(s.mean()) * 100, 3),
            "t_hac": round(hac_t(s.values), 2), "sharpe": round(_ann_sharpe(s), 2),
            "maxdd_pct": round(_maxdd(s) * 100, 1), "hit": round(float((s > 0).mean()), 3)}


def _era_masks(grid):
    """Boolean grid masks for the pre-registered era splits (time-half + pre/post-2024)."""
    g = pd.DatetimeIndex(grid)
    mid = g[len(g) // 2]
    return {
        "full": np.ones(len(g), bool),
        "early": (g <= mid),
        "late": (g > mid),
        "pre-2024": (g <= pd.Timestamp("2023-12-31")),
        "2024+": (g >= pd.Timestamp("2024-01-01")),
    }, g


# ----------------------------------------------------------------------------- main
def main() -> int:
    root = config.ROOT
    U = _read_universe(root)
    px, vol = U["px"], U["vol"]
    fwd_c2c, fwd_fill, sector = U["fwd_c2c"], U["fwd_fill"], U["sector"]
    bench_fwd = _benchmark_fwd(root, px.index)

    # restrict to the CSI300 window (excess is only defined where the benchmark exists)
    first_bench = bench_fwd.dropna().index.min()

    # signals ----------------------------------------------------------------
    at = pd.DataFrame({t: abn_turn(vol[t]) for t in vol.columns}).reindex(px.index)
    r63 = px.apply(lambda c: (1 + clean_daily_ret(c)).rolling(63).apply(np.prod, raw=True) - 1)
    rev3 = -r63                                     # within-sector demeaning handled at rebalance

    grid = [d for d in _grid(px.index) if d >= first_bench]
    masks, g = _era_masks(grid)

    # The spread series drops empty rebalances, so eras are split by masking the GRID up front
    # (position-safe): run the backtest on each era's grid slice.
    def bt_grid(sub_grid, sig, fwd, *, sn=False, resid=None, lmh=True):
        return _rebalance_spreads(sub_grid, sig, fwd, bench_fwd, sector,
                                  sector_neutral=sn, residual_on=resid, low_minus_high=lmh)

    era_grids = {e: [d for i, d in enumerate(g) if masks[e][i]] for e in masks}

    out_lines: list[str] = []

    def log(s=""):
        print(s)
        out_lines.append(s)

    log(f"W3-A abnormal-turnover phase-0 · substrate china_stocks_raw · CSI300-relative excess")
    log(f"universe {px.shape[1]} names after filters (excluded {U['excluded']}) · "
        f"benchmark {first_bench.date()}->{px.index.max().date()} · {len(grid)} monthly rebalances\n")

    # ===== T1: primary L/S decile spread, fill-realistic, full + splits =====
    log("== T1 · PRIMARY low-minus-high decile L/S (CSI300-relative, fill-realistic) ==")
    log(f"{'era':10}{'n':>5}{'mean%':>9}{'t_HAC':>8}{'Sharpe':>8}{'maxDD%':>9}{'hit':>7}")
    t1 = {}
    for e in ["full", "early", "late", "pre-2024", "2024+"]:
        sp, _ = bt_grid(era_grids[e], at, fwd_fill)
        st = _spread_stats(sp)
        t1[e] = st
        if st.get("error"):
            log(f"{e:10}{st['n']:>5}   (thin)")
        else:
            log(f"{e:10}{st['n']:>5}{st['mean_pct']:>9}{st['t_hac']:>8}{st['sharpe']:>8}"
                f"{st['maxdd_pct']:>9}{st['hit']:>7}")
    # sector-neutral robustness (full only)
    sp_sn, _ = bt_grid(era_grids["full"], at, fwd_fill, sn=True)
    t1["full_sn"] = _spread_stats(sp_sn)
    log(f"{'full·SN':10}{t1['full_sn'].get('n',0):>5}{t1['full_sn'].get('mean_pct',''):>9}"
        f"{t1['full_sn'].get('t_hac',''):>8}{t1['full_sn'].get('sharpe',''):>8}"
        f"{t1['full_sn'].get('maxdd_pct',''):>9}{t1['full_sn'].get('hit',''):>7}")
    log("")

    # ===== T6: fill-realistic vs close-to-close gap (full) =====
    sp_c2c, _ = bt_grid(era_grids["full"], at, fwd_c2c)
    t6 = _spread_stats(sp_c2c)
    log("== T6 · fill-realistic vs close-to-close (full) ==")
    log(f"fill-realistic mean {t1['full'].get('mean_pct')}%/reb (t {t1['full'].get('t_hac')}); "
        f"close-to-close mean {t6.get('mean_pct')}%/reb (t {t6.get('t_hac')}); "
        f"grading tax = {round((t6.get('mean_pct',0) or 0) - (t1['full'].get('mean_pct',0) or 0),3)}pp/reb\n")

    # ===== T3: monotonicity across deciles (full, fill-realistic) =====
    _, dec = bt_grid(era_grids["full"], at, fwd_fill)
    dec_means = {q: (round(float(dec[q].mean()) * 100, 3) if len(dec[q]) else None) for q in range(N_DECILES)}
    log("== T3 · decile monotonicity (mean CSI300-relative excess %/reb, D0=lowest abn_turn) ==")
    log("  ".join(f"D{q}:{dec_means[q]}" for q in range(N_DECILES)))
    valid = [dec_means[q] for q in range(N_DECILES) if dec_means[q] is not None]
    spear = float(pd.Series(valid).corr(pd.Series(range(len(valid))), method="spearman")) if len(valid) > 3 else float("nan")
    log(f"  Spearman(decile#, excess) = {round(spear,3)}  (negative = low-abn-turn wins, monotone)\n")

    # ===== T2: ORTHOGONALITY — residualize abn_turn on within-sector 3M reversal =====
    # rev3 must be within-sector demeaned to mirror engine/china_reversal; residualise abn_turn on it.
    log("== T2 · ORTHOGONALITY vs within-sector 3M reversal (residual spread) ==")
    # build within-sector demeaned rev3 per rebalance by using sector_neutral machinery indirectly:
    # residual_on expects a raw signal; we demean rev3 within sector here so the OLS strips the
    # reversal component the picker actually uses.
    rev3_sn = rev3.copy()
    for d in era_grids["full"]:
        row = rev3.loc[d]
        rev3_sn.loc[d] = row - row.groupby(sector.reindex(row.index)).transform("mean")
    sp_raw, _ = bt_grid(era_grids["full"], at, fwd_fill)                    # raw (reference)
    sp_res, _ = bt_grid(era_grids["full"], at, fwd_fill, resid=rev3_sn)     # residualised
    t2_raw, t2_res = _spread_stats(sp_raw), _spread_stats(sp_res)
    log(f"raw abn_turn spread   t_HAC {t2_raw.get('t_hac')}  mean {t2_raw.get('mean_pct')}%  n {t2_raw.get('n')}")
    log(f"residual (⊥reversal)  t_HAC {t2_res.get('t_hac')}  mean {t2_res.get('mean_pct')}%  n {t2_res.get('n')}")
    redundant = abs(t2_res.get("t_hac", 0) or 0) < 2
    log(f"=> {'REDUNDANT-WITH-REVERSAL (residual |t|<2)' if redundant else 'ADDS INFO beyond reversal (residual |t|>=2)'}\n")

    # ===== T5: POSITIVE CONTROL — reversal through the SAME harness must be positive =====
    # The validated edge is DEEP-dip (buy low reversal-fuel = most-beaten names). rev3 high = most
    # beaten. The picker LONGS high rev3, so a HIGH-minus-LOW spread on rev3_sn must be positive.
    log("== T5 · POSITIVE CONTROL: within-sector 3M reversal through same harness (must be > 0) ==")
    sp_pc, _ = bt_grid(era_grids["full"], rev3_sn, fwd_fill, sn=False, lmh=False)  # high-minus-low
    t5 = _spread_stats(sp_pc)
    pc_ok = (t5.get("mean_pct", 0) or 0) > 0 and (t5.get("t_hac", 0) or 0) > 0
    log(f"reversal high-minus-low spread  mean {t5.get('mean_pct')}%  t_HAC {t5.get('t_hac')}  "
        f"Sharpe {t5.get('sharpe')}  n {t5.get('n')}  => instrument {'LIVE' if pc_ok else 'DEAD (run void)'}\n")

    # ===== T4: 2000-permutation placebo on the primary fill-realistic spread =====
    log(f"== T4 · {PERM}-permutation placebo (seed={SEED}) on primary L/S spread ==")
    real_t = t1["full"].get("t_hac", float("nan"))
    perm_p, null_mean, null_sd = _placebo(era_grids["full"], at, fwd_fill, bench_fwd, sector, real_t)
    log(f"real t_HAC {real_t}  |  null mean {round(null_mean,3)} sd {round(null_sd,3)} "
        f"perm_p {round(perm_p,4)}\n")

    # ---- machine verdict on the pre-registered gate --------------------------
    ft = abs(t1["full"].get("t_hac", 0) or 0)
    early_m = t1["early"].get("mean_pct", 0) or 0
    late_m = t1["late"].get("mean_pct", 0) or 0
    pre_m = t1["pre-2024"].get("mean_pct", 0) or 0
    post_m = t1["2024+"].get("mean_pct", 0) or 0
    sign_stable = (np.sign(early_m) == np.sign(late_m)) and (np.sign(pre_m) == np.sign(post_m)) \
        and np.sign(early_m) != 0
    res_t = abs(t2_res.get("t_hac", 0) or 0)

    if not pc_ok:
        verdict = "NO-GO"; why = "positive control FAILED (instrument dead) — run void"
    elif ft < 2:
        # the raw signal is itself null — the honest headline, not the (moot) redundancy clause
        verdict = "NO-GO"
        why = (f"primary |t|={ft:.2f}<2 (null; placebo perm_p={perm_p:.3f}); "
               f"also sign_stable={sign_stable}, residual |t|={res_t:.2f}<2 — redundant with reversal")
    elif not sign_stable:
        verdict = "NO-GO"; why = f"primary |t|={ft:.2f} but sign-UNSTABLE across era splits (era artifact)"
    elif redundant:
        # raw signal strong but the reversal-orthogonal residual collapses — the binding redundancy clause
        verdict = "NO-GO"; why = f"REDUNDANT-WITH-REVERSAL (residual |t|={res_t:.2f}<2) regardless of raw |t|={ft:.2f}"
    elif ft >= 3 and sign_stable and res_t >= 2:
        verdict = "GO"; why = f"|t|={ft:.2f}>=3, sign-stable both splits, residual |t|={res_t:.2f}>=2"
    else:
        verdict = "ACCRUE"
        why = (f"|t|={ft:.2f}, sign_stable={sign_stable}, residual |t|={res_t:.2f} "
               "-> 2<=t<3 or era-only or residual borderline")
    log("== PRE-REGISTERED MACHINE VERDICT ==")
    log(f"VERDICT: {verdict}  ({why})")

    _write_report(root, out_lines, U, first_bench, grid, t1, t2_raw, t2_res, redundant,
                  dec_means, spear, t5, pc_ok, t6, perm_p, null_mean, null_sd, real_t, verdict, why)
    print(f"\nMACHINE VERDICT: {verdict}")
    return 0


def _placebo(sub_grid, sig, fwd, bench_fwd, sector, real_t):
    """2000-permutation null: shuffle the abn_turn cross-section labels within each rebalance
    (seed-fixed), recompute the low-minus-high spread t. A real edge sits in the null's tail."""
    rng = np.random.default_rng(SEED)
    # cache per-rebalance (excess, signal) so each permutation is cheap
    cache = []
    for d in sub_grid:
        if d not in fwd.index:
            continue
        fr = fwd.loc[d]
        bx = float(bench_fwd.get(d, np.nan))
        if not np.isfinite(bx):
            continue
        s = sig.loc[d]
        common = s.dropna().index.intersection(fr.dropna().index)
        if len(common) < 100:
            continue
        cache.append((s.reindex(common).values.copy(), (fr.reindex(common) - bx).values.copy()))
    if not cache:
        return float("nan"), float("nan"), float("nan")

    def spread_from(perm=False):
        vals = []
        for sv, ev in cache:
            sx = rng.permutation(sv) if perm else sv
            ranks = pd.Series(sx).rank(method="first")
            q = ((ranks - 1) / len(sx) * N_DECILES).astype(int).clip(0, N_DECILES - 1).values
            lo = ev[q == 0].mean() if (q == 0).any() else np.nan
            hi = ev[q == (N_DECILES - 1)].mean() if (q == (N_DECILES - 1)).any() else np.nan
            if np.isfinite(lo) and np.isfinite(hi):
                vals.append(lo - hi)
        return hac_t(np.array(vals))

    null = np.array([spread_from(perm=True) for _ in range(PERM)])
    null = null[np.isfinite(null)]
    perm_p = float(np.mean(np.abs(null) >= abs(real_t))) if np.isfinite(real_t) else float("nan")
    return perm_p, float(null.mean()), float(null.std())


def _write_report(root, out_lines, U, first_bench, grid, t1, t2_raw, t2_res, redundant,
                  dec_means, spear, t5, pc_ok, t6, perm_p, null_mean, null_sd, real_t, verdict, why):
    rpt = root / "reports" / "china-turnover-phase0.md"
    rpt.parent.mkdir(exist_ok=True)
    body = [
        "# W3-A — Abnormal-turnover cross-sectional signal — Phase-0 Report",
        "",
        "Flagship of the volume program (F7). Tests whether ABNORMAL TURNOVER (volume-based proxy) "
        "predicts A-share returns — external evidence: low-abnormal-turnover long leg +1.24%/mo t=3.35 "
        "(2000-2019). Substrate `data/china_stocks_raw` (append-only, survivorship-clean, real volume). "
        "CSI300-relative excess, fill-realistic T+1 (H+L)/2 entries, locked-limit rows excluded, "
        "split/ex-div artifacts zeroed. **NOTHING wired to any page/board/rank regardless of outcome.**",
        "",
        "PROXY: `abn_turn = ln(mean(vol,21d) / mean(vol,252d skip 21))`. Volume-z fallback for the "
        "float-normalised turnover ratio the paper uses (we lack historical float shares) — a "
        "within-name ratio so a constant float cancels; tests the MECHANISM, not the paper's point "
        "estimate.",
        "",
        f"PRE-REGISTERED GATE — GO: primary fill-realistic L/S |t|>=3 full AND sign-stable across BOTH "
        f"era splits AND T2 residual |t|>=2 AND positive control fires. ACCRUE: 2<=|t|<3, or era-only, "
        f"or residual borderline. NO-GO: |t|<2, or sign-unstable, or T2 residual |t|<2 "
        f"(REDUNDANT-WITH-REVERSAL) regardless of raw t, or positive control fails.",
        "",
        f"**MACHINE VERDICT: {verdict}** — {why}",
        "",
        "```",
        *out_lines,
        "```",
        "",
        "## Reading",
        f"- **T1 primary**: low-minus-high decile L/S full-sample t_HAC = {t1['full'].get('t_hac')} "
        f"(mean {t1['full'].get('mean_pct')}%/reb). Positive = low-abnormal-turnover names outperform.",
        f"- **T2 orthogonality**: residual-vs-reversal t_HAC = {t2_res.get('t_hac')} "
        f"({'REDUNDANT — the edge is the reversal factor on the volume plane' if redundant else 'adds information beyond reversal'}).",
        f"- **T3 monotonicity**: Spearman(decile, excess) = {round(spear,3)}.",
        f"- **T4 placebo**: perm_p = {round(perm_p,4)} (null mean {round(null_mean,3)}, sd {round(null_sd,3)}).",
        f"- **T5 positive control**: reversal high-minus-low spread mean {t5.get('mean_pct')}% "
        f"t {t5.get('t_hac')} => instrument {'LIVE' if pc_ok else 'DEAD (run void)'}.",
        f"- **T6 fill tax**: close-to-close {t6.get('mean_pct')}%/reb vs fill-realistic "
        f"{t1['full'].get('mean_pct')}%/reb.",
        "",
        "Honest caveats: volume-z proxy (not the float-normalised ratio); raw plane is unadjusted so "
        "corporate-action days are zeroed in the return metric (not the signal); excess is gross of "
        "cost and abnormal-turnover is a high-turnover family (~254% in the source), so a positive "
        "gross spread still needs a net-of-cost pass before any wiring. CSI300-relative window starts "
        f"{first_bench.date()} (benchmark availability).",
        "",
    ]
    rpt.write_text("\n".join(body))
    print(f"wrote {rpt}")


if __name__ == "__main__":
    raise SystemExit(main())
