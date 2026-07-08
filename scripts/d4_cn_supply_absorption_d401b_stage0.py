"""D4-01b Stage 0 — deep-discount block reversion falsifier (family cn_supply_absorption).

PREREG SOURCE (frozen at dispatch): research/SIGNAL_LAB_FRONTIER_DAY4_FABLE_ADJUDICATION_2026-07-08.md
§"D4-01 reassessment" → "Registered re-entry design (D4-01b, staged)". The family verdict
of PR #1932 was VACATED at family level (estimand contamination + rank-not-path matching +
false E2 data gap); the construct kill (price-only absorption = momentum, unidentifiable)
STANDS. This lane is the registered staged re-entry. Stage 0 asks the cheapest decisive
question: does deep-discount block reversion exist AT ALL net of the [t,t+10] price path?
If dead in both regimes, the family CLOSES for real.

FROZEN DESIGN — GATES REGISTERED BEFORE ANY OUTCOME CONTACT
===========================================================

Events (Stage 0):
  Source: data/china_block_tape mrtj partitions (canonical host store; the lane sets
    CHINA_BLOCK_TAPE_STORE because the store is runner-local/untracked and worktrees do
    not carry it — the original lane's false "data gap" came exactly from this).
  Filter: block-day rows 2013-01-01+ with premium_ratio <= -0.15 (RAW RATIO units; unit
    assertions + F5-01 pass-rate print + variant-count divergence at -0.10/-0.15/-0.20
    are hard-asserted before any event is accepted).
  Coverage: .SH -> .SS normalization into data/china_stocks_raw (close+volume);
    known-ticker load check asserted.

Anchoring (AM-S0-1, merged-lane convention preserved):
  t = first trading session strictly AFTER the block date d.
  path  = close[t+10]/close[t] - 1                       ([t,t+10], 10 sessions)
  entry = t+10+1 = t+11 (registered family entry; forward window does NOT overlap path)
  fwd   = close[t+32]/close[t+11] - 1                    (21 sessions from entry)

Contrast (strictly within signal-date; continuous caliper, not rank bins):
  Control pool per date d: covered price-store tickers with valid (path, vol, size, fwd),
    EXCLUDING any ticker with ANY block-tape row (any premium sign) in calendar window
    [d-45, d+50] (AM-S0-4: lookback = partially-treated supply overhang; lookahead covers
    the measurement window, which ends ~t+32 sessions ≈ 46-48 calendar days — a control
    that becomes treated mid-window is not a control. The lookahead leg is estimand
    definition for the falsifier, not a tradable filter, and is flagged as such).
  Covariates: (path raw-return, ln trailing vol, ln trailing size).
    AM-S0-3: trailing stats are vectorized on 60 TRADING BARS (min 20) through the block
    date d: vol = std of daily log returns; size = median(close x volume) with
    zero-volume bars set NaN (upgrade over the merged price-only size proxy — volume
    exists in the store; registered here, before results; fallback ln median close if a
    ticker lacks volume).
  Calipers (AM-S0-5): a candidate control must lie within 0.5 x per-date cross-sectional
    SD (pool ∪ events, ddof=1) of the event on ALL THREE covariates. Up to 3 nearest
    controls by summed SD-normalized |delta| (deterministic; ties by ticker sort order —
    no random sampling). NO caliper relaxation; zero-candidate events are EXCLUDED and
    the exclusion rate printed. Dates with pool < 100 valid controls are dropped
    (printed). Achieved match quality (mean |Δpath| etc.) is printed — "matched on the
    path" must be verifiable, not asserted.
  Episode dedup (AM-S0-2): an event is kept only if the same ticker had no deep-discount
    row in the prior 31 calendar days (refractory window = the [t,t+10]+entry span);
    clustered prints are one episode, not N events. Dedup count printed.

Series and estimands:
  diff_e = fwd_event - mean(fwd of matched controls);  m_d = mean over events at date d,
  n_d = matched-event count. Two estimands per cell, printed SEPARATELY (never conflated;
  the merged run's undisclosed estimand switch is the named failure mode here):
    EW  (DECISIVE): equal-weighted mean of the per-date series {m_d}.
    NW-w (printed, non-decisive): n_d-weighted mean, t via influence-function series
      psi_d = n_d (m_d - mu_w) / mean(n); newey_west_tstat(psi_d + mu_w) gives the exact
      HAC t for the weighted mean.
  Inference: Newey-West with lag = 31 observations (AM-S0-6: horizon-matched — entry lag
  11 + horizon 21 - 1; the per-date series is near-daily so observation-space lag ≈
  trading-day lag).

Regimes (mandatory split; pooled is NON-decisive per the 减持新规 law):
  Split at 2023-08-27 by BLOCK DATE d: pre = [2013-01-01, 2023-08-26], post = 2023-08-27+.

FROZEN GATE (Stage 0):
  Minimum-N floor per regime cell, pre-registered before looking at returns:
    n_matched_events >= 300 AND n_distinct_signal_dates >= 100. A cell below floor is
    UNPOWERED: it carries NO verdict either way and is labeled as such.
  Cell ALIVE iff: floor met AND mean_EW > 0 AND |t_NW(EW)| >= 2.0 AND BH q <= 0.10,
    with BH computed across the POWERED regime cells' two-sided HAC p-values (alpha .10).
  Stage-0 outcome:
    >= 1 powered cell ALIVE  -> Stage 0 ALIVE -> Stage 1 (flow-intensity DiD) proceeds.
    no powered cell ALIVE    -> FAMILY CLOSES (per the registered design: the base
      reversion is dead/crowded-out in both regimes and the absorption interaction has
      no room). Unpowered cells are reported, not adjudicated.
    both cells unpowered     -> NO VERDICT; lane returns to the bench (not expected:
      pre-regime has ~8.4k deep rows / 1,565 dates, post ~5.4k / 685).
  The EW estimand is decisive by freeze. If EW and NW-w disagree, EW rules and the
  disagreement is REPORTED (that pattern is exactly the event-heavy-cluster signature).
  No other outcome-bearing cells exist in Stage 0; all other prints are descriptive
  context with zero gate weight.

Stage 1 (pre-declared; RUN ONLY IF STAGE 0 ALIVE): flow-intensity DiD per the registered
  design — treatment intensity = amt_wan / event-date free-float recomputed from the
  price store (not the tape's precomputed amt_pct_mktcap); "absorbed" = price holds/
  rises over [t,t+10]; the not-absorbed counterfactual is PRINTED blocks that gave back
  the print (never absence-of-print — endogenous observability); decisive term = the
  within-date interaction (absorbed - gave-back | heavy supply) minus (same path split |
  no supply). E1 holder-sale windows ride only as a labeled non-decisive ITT leg.

Trial accounting: the full Stage-0 cell grid is logged to the TrialLedger (family
  cn_supply_absorption) AT GENERATION, before outcomes are computed. The lane does not
  commit data/trial_ledger.jsonl (intraday data/-discard law); the delta is reported in
  the PR body.

Run:
    CHINA_BLOCK_TAPE_STORE=<canonical>/data/china_block_tape \
        python -m scripts.d4_cn_supply_absorption_d401b_stage0
Writes reports/d4-cn-supply-absorption-d401b-stage0.md (frozen prereg printed BEFORE
results). Display-tier study output; not a production signal; no signal keys are
originated by this lane.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.validation import benjamini_hochberg, newey_west_tstat   # noqa: E402
from engine.trial_ledger import TrialLedger                          # noqa: E402
from scripts.d4_cn_supply_absorption_phase0 import _norm_ticker      # noqa: E402
from scripts.d4_cn_supply_absorption_e2_rerun import (               # noqa: E402
    TAPE_STORE,
    _anchored_returns,
    load_tape,
)

FAMILY = "cn_supply_absorption"
LANE = "D4-01b_stage0"
REPORT_PATH = ROOT / "reports" / "d4-cn-supply-absorption-d401b-stage0.md"
PRICE_STORE = ROOT / "data" / "china_stocks_raw"

# ---- frozen constants (see docstring; do not edit after results exist) ----
USABLE_FROM = pd.Timestamp("2013-01-01")
DEEP_RATIO = -0.15                 # premium_ratio threshold, RAW RATIO units
VARIANT_THRESHOLDS = (-0.10, -0.15, -0.20)   # F5-01 variant-count divergence check
PATH_WINDOW = 10                   # sessions, [t, t+10]
ENTRY_LAG = PATH_WINDOW + 1        # t+10+1 registered entry
HORIZON = 21                       # forward sessions from entry
NW_LAG = ENTRY_LAG + HORIZON - 1   # = 31, horizon-matched HAC lag
REGIME_SPLIT = pd.Timestamp("2023-08-27")    # 减持新规
EPISODE_DEDUP_DAYS = 31            # AM-S0-2 refractory window (calendar days)
POOL_EXCL_BACK = 45                # AM-S0-4 lookback (calendar days)
POOL_EXCL_FWD = 50                 # AM-S0-4 lookahead (calendar days)
CALIPER_SD = 0.5                   # AM-S0-5, per covariate, per-date SD units
MAX_CONTROLS = 3                   # nearest-3, deterministic
MIN_POOL = 100                     # valid controls per date, else date dropped
TRAIL_BARS = 60                    # AM-S0-3 trailing window (trading bars)
TRAIL_MIN_OBS = 20
FLOOR_EVENTS = 300                 # frozen minimum-N floor per regime cell
FLOOR_DATES = 100
T_THRESHOLD = 2.0
BH_ALPHA = 0.10
KNOWN_TICKER = "000001.SZ"         # known-ticker load check (symlink/store resolution)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_price_frames() -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
    """Close + daily amount (close x volume; zero-volume bars -> NaN) per ticker.
    Same close conventions as the merged load_price_store; volume added per AM-S0-3."""
    files = sorted(PRICE_STORE.glob("*.parquet"))
    closes: dict[str, pd.Series] = {}
    amounts: dict[str, pd.Series] = {}
    n_no_vol = 0
    for f in files:
        df = pd.read_parquet(f)
        col = "close" if "close" in df.columns else "close_price"
        s = df[col].sort_index().dropna()
        s.index = pd.to_datetime(s.index)
        closes[f.stem] = s
        if "volume" in df.columns:
            v = df["volume"].sort_index()
            v.index = pd.to_datetime(v.index)
            amt = (s * v.reindex(s.index)).replace(0.0, np.nan)
        else:
            n_no_vol += 1
            amt = s.copy()  # AM-S0-3 fallback: price-only size proxy
        amounts[f.stem] = amt
    print(f"\n[price_store] {len(closes)} tickers from {PRICE_STORE} "
          f"({n_no_vol} without volume -> price-only size fallback)")
    assert KNOWN_TICKER in closes, f"known-ticker load check FAILED: {KNOWN_TICKER} absent"
    s0 = closes[KNOWN_TICKER]
    print(f"  [verify] {KNOWN_TICKER}: {len(s0)} rows, "
          f"{s0.index.min().date()}..{s0.index.max().date()} (known-ticker load check OK)")
    assert len(s0) > 5000, "known-ticker history implausibly short — wrong store?"
    return closes, amounts


# ---------------------------------------------------------------------------
# Event construction (verification-law prints + episode dedup)
# ---------------------------------------------------------------------------

def build_stage0_events(tape: pd.DataFrame, closes: dict[str, pd.Series]) -> pd.DataFrame:
    usable = tape[tape["date"] >= USABLE_FROM].copy()
    pr = usable["premium_ratio"].astype(float)
    print(f"\n[events] usable rows (>= {USABLE_FROM.date()}): {len(usable):,}")

    # F5-01 law: variant counts must diverge as thresholds imply
    counts = {}
    for th in VARIANT_THRESHOLDS:
        counts[th] = int(pr.le(th).sum())
        print(f"  variant threshold premium_ratio <= {th:+.2f}: {counts[th]:,} rows "
              f"= {100.0*counts[th]/len(usable):.2f}%")
    assert counts[-0.10] > counts[-0.15] > counts[-0.20] > 0, \
        "variant counts do not diverge monotonically — event filter is broken"
    assert counts[-0.10] > 1.5 * counts[-0.15] > 1.5 * counts[-0.20], \
        "variant counts diverge too weakly for a right-tail threshold family"

    deep = usable[pr.le(DEEP_RATIO).values].copy()
    rate = 100.0 * len(deep) / len(usable)
    print(f"  frozen filter <= {DEEP_RATIO}: {len(deep):,}/{len(usable):,} = {rate:.2f}% "
          f"pass rate (F5-01 audit expectation ~8%)")
    assert 4.0 <= rate <= 14.0, "pass rate far from the F5-01 audit expectation"

    # AM-S0-2 episode dedup (refractory 31 calendar days per ticker)
    deep = deep.sort_values(["ticker", "date"])
    keep = np.ones(len(deep), dtype=bool)
    last_kept: dict[str, pd.Timestamp] = {}
    dts = deep["date"].tolist()
    tks = deep["ticker"].tolist()
    for i in range(len(deep)):
        lk = last_kept.get(tks[i])
        if lk is not None and (dts[i] - lk).days <= EPISODE_DEDUP_DAYS:
            keep[i] = False
        else:
            last_kept[tks[i]] = dts[i]
    n_before = len(deep)
    deep = deep[keep]
    print(f"  episode dedup (AM-S0-2, {EPISODE_DEDUP_DAYS}d refractory): "
          f"{n_before:,} -> {len(deep):,} episode-start events "
          f"({n_before - len(deep):,} clustered prints collapsed)")

    deep["store_ticker"] = deep["ticker"].map(_norm_ticker)
    deep["covered"] = deep["store_ticker"].isin(closes.keys())
    n_cov = int(deep["covered"].sum())
    print(f"  coverage after .SH->.SS normalization: {n_cov:,}/{len(deep):,} "
          f"= {100.0*n_cov/len(deep):.1f}% of episode events (expected ~30%)")
    ev = deep[deep["covered"]].copy().sort_values(["date", "store_ticker"])
    pre = ev[ev["date"] < REGIME_SPLIT]
    post = ev[ev["date"] >= REGIME_SPLIT]
    print(f"  covered episode events: pre-规 {len(pre):,} ({pre['date'].nunique():,} dates), "
          f"post-规 {len(post):,} ({post['date'].nunique():,} dates)")
    return ev


# ---------------------------------------------------------------------------
# Vectorized covariate / return matrices over (event dates x tickers)
# ---------------------------------------------------------------------------

def build_matrices(event_dates: list[pd.Timestamp],
                   closes: dict[str, pd.Series],
                   amounts: dict[str, pd.Series]):
    tickers = sorted(closes.keys())
    date_arr = np.array(pd.DatetimeIndex(event_dates).values)
    nD, nT = len(event_dates), len(tickers)
    PATH = np.full((nD, nT), np.nan)
    FWD = np.full((nD, nT), np.nan)
    LV = np.full((nD, nT), np.nan)
    LS = np.full((nD, nT), np.nan)
    print(f"\n[matrices] {nD} event dates x {nT} tickers "
          f"(path [t,t+{PATH_WINDOW}], fwd [t+{ENTRY_LAG}, t+{ENTRY_LAG+HORIZON}], "
          f"trailing {TRAIL_BARS}-bar vol/size)")
    for j, tk in enumerate(tickers):
        s = closes[tk]
        PATH[:, j] = _anchored_returns(s, date_arr, 0, PATH_WINDOW)
        FWD[:, j] = _anchored_returns(s, date_arr, ENTRY_LAG, ENTRY_LAG + HORIZON)
        # trailing stats THROUGH the block date d (PIT: block print is known EOD at d)
        lr = np.log(s / s.shift(1))
        vol = lr.rolling(TRAIL_BARS, min_periods=TRAIL_MIN_OBS).std()
        amt = amounts[tk].reindex(s.index)
        size = amt.rolling(TRAIL_BARS, min_periods=TRAIL_MIN_OBS).median()
        pos = np.searchsorted(s.index.values, date_arr, side="right") - 1
        ok = pos >= 0
        v = np.full(nD, np.nan)
        z = np.full(nD, np.nan)
        v[ok] = vol.values[pos[ok]]
        z[ok] = size.values[pos[ok]]
        with np.errstate(divide="ignore", invalid="ignore"):
            LV[:, j] = np.where(v > 0, np.log(v), np.nan)
            LS[:, j] = np.where(z > 0, np.log(z), np.nan)
    return tickers, PATH, FWD, LV, LS


def build_blocked_sets(tape: pd.DataFrame, event_dates: list[pd.Timestamp]) -> list[set[str]]:
    """AM-S0-4: per event date, the set of store tickers with ANY tape row (any premium)
    in [d - POOL_EXCL_BACK, d + POOL_EXCL_FWD] calendar days."""
    t = tape.sort_values("date")
    dates = t["date"].values
    tick = t["ticker"].map(_norm_ticker).values
    out = []
    for d in event_dates:
        lo = np.searchsorted(dates, np.datetime64(d - pd.Timedelta(days=POOL_EXCL_BACK)), side="left")
        hi = np.searchsorted(dates, np.datetime64(d + pd.Timedelta(days=POOL_EXCL_FWD)), side="right")
        out.append(set(tick[lo:hi]))
    sizes = [len(s) for s in out]
    print(f"[blocked_sets] any-block exclusion window [-{POOL_EXCL_BACK}d, +{POOL_EXCL_FWD}d]: "
          f"mean {np.mean(sizes):.0f} / max {np.max(sizes)} tickers excluded per date")
    return out


# ---------------------------------------------------------------------------
# Within-date continuous-caliper matching
# ---------------------------------------------------------------------------

def run_matching(ev: pd.DataFrame, event_dates: list[pd.Timestamp], tickers: list[str],
                 PATH, FWD, LV, LS, blocked: list[set[str]]):
    tk_ix = {tk: j for j, tk in enumerate(tickers)}
    date_ix = {d: i for i, d in enumerate(event_dates)}
    ev = ev.copy()
    ev["di"] = ev["date"].map(date_ix)
    ev["j"] = ev["store_ticker"].map(tk_ix)

    daily = []          # (date, m_d, n_d)
    n_ev_invalid = 0    # event lacks valid covariates/fwd
    n_ev_nocand = 0     # zero controls inside calipers
    n_dates_thin = 0    # pool < MIN_POOL
    n_dates_degenerate = 0
    mq_dpath, mq_dlv, mq_dls, ev_path_list, pool_path_means = [], [], [], [], []

    blocked_mask = np.zeros((len(event_dates), len(tickers)), dtype=bool)
    for i in range(len(event_dates)):
        cols = [tk_ix[t] for t in blocked[i] if t in tk_ix]
        blocked_mask[i, cols] = True

    for di, grp in ev.groupby("di"):
        valid = (np.isfinite(PATH[di]) & np.isfinite(FWD[di])
                 & np.isfinite(LV[di]) & np.isfinite(LS[di]))
        pool_mask = valid & ~blocked_mask[di]
        pool_idx = np.where(pool_mask)[0]

        ev_js, ev_paths, ev_lvs, ev_lss, ev_fwds = [], [], [], [], []
        for _, row in grp.iterrows():
            j = row["j"]
            if not (np.isfinite(PATH[di, j]) and np.isfinite(FWD[di, j])
                    and np.isfinite(LV[di, j]) and np.isfinite(LS[di, j])):
                n_ev_invalid += 1
                continue
            ev_js.append(j)
            ev_paths.append(PATH[di, j]); ev_lvs.append(LV[di, j])
            ev_lss.append(LS[di, j]); ev_fwds.append(FWD[di, j])
        if not ev_js:
            continue
        if len(pool_idx) < MIN_POOL:
            n_dates_thin += 1
            continue

        allp = np.concatenate([PATH[di, pool_idx], np.array(ev_paths)])
        alv = np.concatenate([LV[di, pool_idx], np.array(ev_lvs)])
        als = np.concatenate([LS[di, pool_idx], np.array(ev_lss)])
        sd_p, sd_v, sd_s = allp.std(ddof=1), alv.std(ddof=1), als.std(ddof=1)
        if not (sd_p > 0 and sd_v > 0 and sd_s > 0):
            n_dates_degenerate += 1
            continue

        pool_p = PATH[di, pool_idx]; pool_v = LV[di, pool_idx]
        pool_s = LS[di, pool_idx]; pool_f = FWD[di, pool_idx]
        pool_path_means.append(float(pool_p.mean()))

        diffs = []
        for k in range(len(ev_js)):
            dp = np.abs(pool_p - ev_paths[k])
            dv = np.abs(pool_v - ev_lvs[k])
            ds = np.abs(pool_s - ev_lss[k])
            cand = (dp <= CALIPER_SD * sd_p) & (dv <= CALIPER_SD * sd_v) & (ds <= CALIPER_SD * sd_s)
            if not cand.any():
                n_ev_nocand += 1
                continue
            dist = dp / sd_p + dv / sd_v + ds / sd_s
            dist = np.where(cand, dist, np.inf)
            take = np.argsort(dist, kind="stable")[:MAX_CONTROLS]
            take = take[np.isfinite(dist[take])]
            diffs.append(float(ev_fwds[k] - pool_f[take].mean()))
            ev_path_list.append(ev_paths[k])
            mq_dpath.extend(dp[take].tolist())
            mq_dlv.extend(dv[take].tolist())
            mq_dls.extend(ds[take].tolist())
        if diffs:
            daily.append((event_dates[di], float(np.mean(diffs)), len(diffs)))

    daily_df = pd.DataFrame(daily, columns=["date", "m_d", "n_d"]).sort_values("date")
    stats = {
        "n_ev_invalid": n_ev_invalid, "n_ev_nocand": n_ev_nocand,
        "n_dates_thin": n_dates_thin, "n_dates_degenerate": n_dates_degenerate,
        "match_dpath_mean": float(np.mean(mq_dpath)) if mq_dpath else None,
        "match_dpath_median": float(np.median(mq_dpath)) if mq_dpath else None,
        "match_dlv_mean": float(np.mean(mq_dlv)) if mq_dlv else None,
        "match_dls_mean": float(np.mean(mq_dls)) if mq_dls else None,
        "ev_path_mean": float(np.mean(ev_path_list)) if ev_path_list else None,
        "pool_path_mean": float(np.mean(pool_path_means)) if pool_path_means else None,
        "n_matched_events": int(daily_df["n_d"].sum()) if len(daily_df) else 0,
    }
    print(f"\n[matching] matched events: {stats['n_matched_events']:,} over "
          f"{len(daily_df):,} dates; excluded — invalid covariates/fwd: {n_ev_invalid}, "
          f"zero in-caliper candidates: {n_ev_nocand}; dates dropped — thin pool: "
          f"{n_dates_thin}, degenerate SD: {n_dates_degenerate}")
    if stats["match_dpath_mean"] is not None:
        print(f"[match_quality] |Δpath| mean={stats['match_dpath_mean']*100:.2f}pp "
              f"median={stats['match_dpath_median']*100:.2f}pp; "
              f"|Δln vol| mean={stats['match_dlv_mean']:.3f}; "
              f"|Δln size| mean={stats['match_dls_mean']:.3f}")
        print(f"[context] event [t,t+10] path mean={stats['ev_path_mean']*100:+.2f}pp vs "
              f"pool mean={stats['pool_path_mean']*100:+.2f}pp (descriptive)")
    return daily_df, stats


# ---------------------------------------------------------------------------
# Estimands + gate
# ---------------------------------------------------------------------------

def cell_estimands(daily: pd.DataFrame, label: str) -> dict:
    md = daily["m_d"].to_numpy(float)
    nd = daily["n_d"].to_numpy(float)
    n_events = int(nd.sum())
    n_dates = len(daily)
    out = {"label": label, "n_events": n_events, "n_dates": n_dates,
           "floor_met": (n_events >= FLOOR_EVENTS and n_dates >= FLOOR_DATES)}
    if n_dates >= 8:
        ew = newey_west_tstat(pd.Series(md), lags=NW_LAG)
        out["ew"] = ew
        mu_w = float((nd * md).sum() / nd.sum())
        psi = nd * (md - mu_w) / nd.mean()
        nww = newey_west_tstat(pd.Series(psi + mu_w), lags=NW_LAG)
        out["nww"] = nww
        # pooled-pair iid t, reference only (per-date means weighted by n as proxy)
        out["mean_ew"] = ew["mean"]
        out["mean_nww"] = nww["mean"]
    else:
        out["ew"] = {"mean": None, "t": None, "p": None, "n": n_dates}
        out["nww"] = {"mean": None, "t": None, "p": None, "n": n_dates}
        out["mean_ew"] = out["mean_nww"] = None
    e = out["ew"]
    w = out["nww"]
    print(f"\n[cell {label}] n_events={n_events:,} n_dates={n_dates:,} "
          f"floor_met={out['floor_met']}")
    print(f"  EW  (DECISIVE): mean={_pp(e['mean'])} t_NW(lag{NW_LAG})={e['t']} p={e['p']}")
    print(f"  NW-w (printed): mean={_pp(w['mean'])} t_NW(lag{NW_LAG})={w['t']} p={w['p']}")
    return out


def _pp(v):
    return "N/A" if v is None else f"{v*100:+.3f}pp"


def evaluate_gate(cells: dict[str, dict]) -> dict:
    powered = {k: c for k, c in cells.items() if c["floor_met"] and c["ew"]["p"] is not None}
    bh = benjamini_hochberg({k: c["ew"]["p"] for k, c in powered.items()}, alpha=BH_ALPHA)
    for k, c in cells.items():
        c["bh_q"] = bh.get(k, {}).get("q")
        c["bh_reject"] = bool(bh.get(k, {}).get("reject", False))
        c["alive"] = bool(
            c["floor_met"] and c["ew"]["mean"] is not None and c["ew"]["mean"] > 0
            and c["ew"]["t"] is not None and abs(c["ew"]["t"]) >= T_THRESHOLD
            and c["bh_reject"]
        )
    n_powered = len(powered)
    any_alive = any(c["alive"] for c in cells.values())
    if n_powered == 0:
        outcome = "NO_VERDICT"
    elif any_alive:
        outcome = "STAGE0_ALIVE"
    else:
        outcome = "FAMILY_CLOSES"
    print(f"\n[gate] powered cells: {n_powered}/{len(cells)}; "
          f"alive: {[k for k, c in cells.items() if c['alive']]}; outcome: {outcome}")
    return {"outcome": outcome, "n_powered": n_powered}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def render_report(ctx: dict) -> str:
    L: list[str] = []
    W = L.append
    W("# D4-01b Stage 0 — deep-discount block reversion falsifier")
    W("## Family: `cn_supply_absorption` (REVIVE-AMENDED re-entry; staged)")
    W("")
    W("*Lane: D4-01b Stage 0. Prereg source (frozen at dispatch):*")
    W("*`research/SIGNAL_LAB_FRONTIER_DAY4_FABLE_ADJUDICATION_2026-07-08.md` §\"D4-01")
    W("reassessment\" → \"Registered re-entry design (D4-01b, staged)\". Display-tier study")
    W("output — not a production signal; this lane originates no signal keys.*")
    W("")
    W("---")
    W("")
    W("## 0. Frozen pre-registration (gates BEFORE results)")
    W("")
    W("All of the following was frozen in the harness docstring and committed BEFORE any")
    W("outcome was computed (see the two-commit receipt in the PR: commit 1 = harness +")
    W("this section with results pending; commit 2 = results).")
    W("")
    W(f"- **Events**: mrtj block-tape rows {USABLE_FROM.date()}+, `premium_ratio <= {DEEP_RATIO}`")
    W("  (RAW RATIO units, hard-asserted; F5-01 pass-rate + variant-count divergence at")
    W(f"  {', '.join(str(t) for t in VARIANT_THRESHOLDS)} asserted before any event is accepted);")
    W(f"  episode dedup: {EPISODE_DEDUP_DAYS}-calendar-day refractory per ticker (AM-S0-2);")
    W("  coverage via `.SH -> .SS` into `data/china_stocks_raw`.")
    W(f"- **Anchoring (AM-S0-1)**: t = first session strictly after block date; path =")
    W(f"  [t, t+{PATH_WINDOW}] close-to-close; entry = t+{ENTRY_LAG} (registered family entry);")
    W(f"  forward = {HORIZON} sessions from entry (no overlap with the path window).")
    W(f"- **Contrast**: strictly within signal-date. Control pool excludes any ticker with")
    W(f"  ANY tape row in [d-{POOL_EXCL_BACK}, d+{POOL_EXCL_FWD}] calendar days (AM-S0-4; lookahead leg")
    W("  = estimand definition covering the measurement window, flagged as non-tradable).")
    W(f"  Covariates (path, ln 60-bar vol, ln 60-bar median close×volume) (AM-S0-3);")
    W(f"  continuous calipers at {CALIPER_SD} × per-date cross-sectional SD on ALL THREE")
    W(f"  (AM-S0-5), nearest-{MAX_CONTROLS} deterministic, NO relaxation, zero-candidate events")
    W(f"  excluded (rate printed), dates with pool < {MIN_POOL} dropped.")
    W(f"- **Estimands**: per-date long-short m_d; EW mean over dates = DECISIVE; n_d-weighted")
    W("  mean printed separately, never conflated (the merged run's undisclosed estimand")
    W(f"  switch is the named failure mode). Newey-West lag {NW_LAG} (horizon-matched, AM-S0-6).")
    W(f"- **Regimes**: mandatory split at {REGIME_SPLIT.date()} (减持新规) by block date;")
    W("  pooled full-sample printed NON-decisive only.")
    W(f"- **Minimum-N floor (pre-registered)**: >= {FLOOR_EVENTS} matched events AND")
    W(f"  >= {FLOOR_DATES} distinct signal dates per regime cell; below floor = UNPOWERED,")
    W("  no verdict either way.")
    W(f"- **Gate**: cell ALIVE iff floor met AND mean_EW > 0 AND |t_NW| >= {T_THRESHOLD} AND")
    W(f"  BH q <= {BH_ALPHA} across the powered regime cells. >= 1 powered cell alive ->")
    W("  Stage 1 proceeds. No powered cell alive -> **FAMILY CLOSES**. Both cells")
    W("  unpowered -> no verdict, lane returns to bench.")
    W("- **Stage 1 (pre-declared, runs ONLY if Stage 0 alive)**: flow-intensity DiD;")
    W("  treatment intensity = `amt_wan` / event-date free-float recomputed from the price")
    W("  store; not-absorbed counterfactual = printed blocks that gave back the print")
    W("  (never absence-of-print); decisive term = within-date interaction vs the same")
    W("  path split among no-supply names; E1 windows = labeled non-decisive ITT leg only.")
    W("")
    if not ctx.get("results_ready"):
        W("---")
        W("")
        W("## RESULTS PENDING")
        W("")
        W("This freeze commit intentionally contains no results. The harness runs next;")
        W("results land in the following commit.")
        W("")
        return "\n".join(L)
    W("---")
    W("")
    W("## 1. Store verification (canonical host data plane)")
    W("")
    W("| Check | Value |")
    W("|---|---|")
    W(f"| Tape store | `{ctx['store']}` (env `CHINA_BLOCK_TAPE_STORE`; worktrees do not carry the untracked store) |")
    W(f"| mrtj partitions / rows | {ctx['tape_files']} files / {ctx['tape_rows']:,} rows ({ctx['tape_min']}..{ctx['tape_max']}) |")
    W(f"| Duplicate (date,ticker) rows | {ctx['tape_dup']} (asserted 0) |")
    W(f"| Unit assertion | `premium_ratio` RAW ratio: identity vs `cross_price/close - 1` verified; 0 rows <= -15 in raw units; median {ctx['pr_median']:+.4f} |")
    W(f"| Known-ticker load check | `{KNOWN_TICKER}` present, {ctx['known_rows']:,} rows (store resolution proven) |")
    W(f"| Price store | `data/china_stocks_raw`, {ctx['n_price_tickers']:,} tickers, close+volume |")
    W("")
    W("## 2. Event set (verification-law prints)")
    W("")
    W("| Check | Value |")
    W("|---|---|")
    W(f"| Usable rows (2013+) | {ctx['usable_rows']:,} |")
    for th in VARIANT_THRESHOLDS:
        n = ctx['variant_counts'][th]
        W(f"| Variant `premium_ratio <= {th:+.2f}` | {n:,} rows = {100.0*n/ctx['usable_rows']:.2f}% |")
    W(f"| Frozen filter (<= {DEEP_RATIO}) pass rate | {ctx['n_deep']:,}/{ctx['usable_rows']:,} = {ctx['pass_rate']:.2f}% (F5-01 expectation ~8% — consistent) |")
    W(f"| Variant divergence | monotone {ctx['variant_counts'][-0.10]:,} > {ctx['variant_counts'][-0.15]:,} > {ctx['variant_counts'][-0.20]:,} — asserted |")
    W(f"| Episode dedup (AM-S0-2) | {ctx['n_deep']:,} -> {ctx['n_episodes']:,} episode-start events |")
    W(f"| Covered after .SH->.SS | {ctx['n_covered']:,}/{ctx['n_episodes']:,} = {ctx['cov_rate']:.1f}% |")
    W(f"| Matched events (post caliper) | {ctx['n_matched']:,} over {ctx['n_match_dates']:,} dates |")
    W(f"| Exclusions | invalid covariates/fwd: {ctx['mstats']['n_ev_invalid']}; zero in-caliper candidates: {ctx['mstats']['n_ev_nocand']}; thin-pool dates: {ctx['mstats']['n_dates_thin']} |")
    W("")
    W(f"**Match quality (achieved, not asserted):** |Δpath| mean "
      f"{ctx['mstats']['match_dpath_mean']*100:.2f}pp / median {ctx['mstats']['match_dpath_median']*100:.2f}pp; "
      f"|Δln vol| mean {ctx['mstats']['match_dlv_mean']:.3f}; |Δln size| mean {ctx['mstats']['match_dls_mean']:.3f}. "
      f"Event [t,t+10] path mean {ctx['mstats']['ev_path_mean']*100:+.2f}pp vs pool mean "
      f"{ctx['mstats']['pool_path_mean']*100:+.2f}pp (descriptive).")
    W("")
    W("## 3. Stage-0 results (gated cells + non-decisive prints)")
    W("")
    W("| Cell | n events | n dates | floor | EW mean | t_NW (EW) | p | BH q | NW-w mean | t_NW (NW-w) | verdict |")
    W("|---|---|---|---|---|---|---|---|---|---|---|")
    for k, c in ctx["cells"].items():
        floor = "met" if c["floor_met"] else "**UNPOWERED**"
        q = f"{c['bh_q']:.3f}" if c.get("bh_q") is not None else "—"
        verdict = ("**ALIVE**" if c["alive"] else
                   ("no verdict" if not c["floor_met"] else "dead"))
        W(f"| {k} | {c['n_events']:,} | {c['n_dates']:,} | {floor} | {_pp(c['ew']['mean'])} | "
          f"{c['ew']['t']} | {c['ew']['p']} | {q} | {_pp(c['nww']['mean'])} | {c['nww']['t']} | {verdict} |")
    pc = ctx["pooled"]
    W(f"| pooled (NON-decisive) | {pc['n_events']:,} | {pc['n_dates']:,} | — | {_pp(pc['ew']['mean'])} | "
      f"{pc['ew']['t']} | {pc['ew']['p']} | — | {_pp(pc['nww']['mean'])} | {pc['nww']['t']} | — |")
    W("")
    W(f"Decisive estimand: EW per-date series, NW lag {NW_LAG}. The pooled row exists only")
    W("because the prereg mandates printing it as non-decisive (减持新规 changed window-")
    W("selection meaning; pooled-regime estimates are not interpretable).")
    if ctx["ew_nww_disagree"]:
        W("")
        W("**EW vs NW-w disagreement flag:** the two estimands disagree in sign or")
        W("significance in at least one cell — the event-heavy-cluster signature. EW rules")
        W("by freeze; the disagreement is reported here, not adjudicated away.")
    W("")
    W("## 4. Gate outcome")
    W("")
    outcome = ctx["gate"]["outcome"]
    if outcome == "FAMILY_CLOSES":
        W("**No powered regime cell is ALIVE. Per the frozen rule, family")
        W(f"`{FAMILY}` CLOSES.** The deep-discount block reversion premium, net of a")
        W("continuous [t,t+10] path + vol + size match evaluated strictly within date, is")
        W("statistically indistinguishable from zero (or negative) in both the pre- and")
        W("post-减持新规 regimes. The known local-quant reversion trade shows no residual")
        W("room in the covered universe, so the Stage-1 absorption interaction has no room")
        W("either; Stage 1 is NOT run, per the staged design.")
    elif outcome == "STAGE0_ALIVE":
        alive = [k for k, c in ctx["cells"].items() if c["alive"]]
        W(f"**Stage 0 is ALIVE** (cells: {', '.join(alive)}). Per the frozen rule, Stage 1")
        W("(flow-intensity DiD) proceeds under the registered design.")
    else:
        W("**NO VERDICT** — both regime cells fell below the pre-registered minimum-N")
        W("floor. The lane returns to the bench; no family adjudication is made.")
    W("")
    W("This is a pre-registered falsifier outcome, not an exploratory read: the gate,")
    W("floors, calipers, estimand choice, and regime split were all frozen before any")
    W("outcome was computed.")
    W("")
    W("## 5. Stage 1 status")
    W("")
    if outcome == "STAGE0_ALIVE":
        W("TRIGGERED — see the Stage-1 section/report appended by the Stage-1 harness.")
    else:
        W("NOT RUN. The Stage-1 flow-intensity DiD (pre-declared above) runs only on a")
        W("Stage-0 ALIVE outcome. Nothing in the Stage-1 design was touched by outcomes.")
    W("")
    W("---")
    W("")
    W(f"*Report generated by `scripts/d4_cn_supply_absorption_d401b_stage0.py` on")
    W(f"{ctx['run_date']}. Store: `{ctx['store']}` (canonical host; env override).")
    W(f"Prices: `data/china_stocks_raw` (.SH->.SS normalized). Trial-ledger rows for the")
    W(f"full Stage-0 cell grid were logged AT GENERATION (family `{FAMILY}`) and the")
    W(f"ledger file restored per the intraday data/-discard law; delta in the PR body.")
    W(f"Display-tier study output; no production signal; per house law this text makes no")
    W(f"promotion claims.*")
    W("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    freeze_only = "--freeze-only" in sys.argv
    print("=" * 72)
    print(f"D4-01b STAGE 0 — {FAMILY} — deep-discount block reversion falsifier")
    print("=" * 72)
    if freeze_only:
        REPORT_PATH.write_text(render_report({"results_ready": False}), encoding="utf-8")
        print(f"[freeze] wrote prereg-only report: {REPORT_PATH}")
        return

    tape = load_tape()
    closes, amounts = load_price_frames()
    ev = build_stage0_events(tape, closes)

    # ---- trial ledger: log the full cell grid AT GENERATION (before outcomes) ----
    base_cfg = {
        "lane": LANE, "event": f"premium_ratio<={DEEP_RATIO}@2013+",
        "episode_dedup_days": EPISODE_DEDUP_DAYS, "entry": f"t+{ENTRY_LAG}",
        "horizon_d": HORIZON, "match": f"within-date continuous caliper {CALIPER_SD}sd "
        f"(path,ln_vol,ln_size) nearest-{MAX_CONTROLS}",
        "pool_excl": f"any-block [-{POOL_EXCL_BACK},+{POOL_EXCL_FWD}]cd",
        "nw_lag": NW_LAG, "floor": f">={FLOOR_EVENTS}ev,>={FLOOR_DATES}dates",
        "gate": f"mean>0 & |t|>={T_THRESHOLD} & BH q<={BH_ALPHA} (powered cells)",
    }
    grid = []
    for regime in ("pre_gui", "post_gui", "pooled_nondecisive"):
        for estimand in ("ew_decisive" if regime != "pooled_nondecisive" else "ew_nondecisive",
                         "n_weighted_printed"):
            grid.append({**base_cfg, "regime": regime, "estimand": estimand})
    led = TrialLedger(family=FAMILY)
    n_new = led.log_grid(grid, family=FAMILY,
                         note="D4-01b Stage 0 grid logged at generation (pre-outcome)")
    print(f"\n[trial_ledger] logged {n_new} new config rows at generation (family {FAMILY})")

    # ---- outcome computation begins here ----
    event_dates = sorted(ev["date"].unique())
    event_dates = [pd.Timestamp(d) for d in event_dates]
    tickers, PATH, FWD, LV, LS = build_matrices(event_dates, closes, amounts)
    blocked = build_blocked_sets(tape, event_dates)
    daily, mstats = run_matching(ev, event_dates, tickers, PATH, FWD, LV, LS, blocked)

    pre = daily[daily["date"] < REGIME_SPLIT]
    post = daily[daily["date"] >= REGIME_SPLIT]
    cells = {
        "pre_gui (2013..2023-08-26)": cell_estimands(pre, "pre_gui"),
        "post_gui (2023-08-27+)": cell_estimands(post, "post_gui"),
    }
    pooled = cell_estimands(daily, "pooled_NONDECISIVE")
    gate = evaluate_gate(cells)

    ew_nww_disagree = any(
        c["ew"]["t"] is not None and c["nww"]["t"] is not None
        and ((c["ew"]["t"] >= T_THRESHOLD) != (c["nww"]["t"] >= T_THRESHOLD)
             or (c["ew"]["mean"] or 0) * (c["nww"]["mean"] or 0) < 0)
        for c in cells.values()
    )

    usable_rows = int((tape["date"] >= USABLE_FROM).sum())
    pr_u = tape.loc[tape["date"] >= USABLE_FROM, "premium_ratio"].astype(float)
    ctx = {
        "results_ready": True,
        "run_date": pd.Timestamp("2026-07-08").date().isoformat(),
        "store": str(TAPE_STORE),
        "tape_files": len(sorted(TAPE_STORE.glob("mrtj_*.parquet"))),
        "tape_rows": len(tape),
        "tape_min": str(tape["date"].min().date()), "tape_max": str(tape["date"].max().date()),
        "tape_dup": int(tape.duplicated(["date", "ticker"]).sum()),
        "pr_median": float(tape["premium_ratio"].median()),
        "known_rows": len(closes[KNOWN_TICKER]),
        "n_price_tickers": len(closes),
        "usable_rows": usable_rows,
        "variant_counts": {th: int(pr_u.le(th).sum()) for th in VARIANT_THRESHOLDS},
        "n_deep": int(pr_u.le(DEEP_RATIO).sum()),
        "pass_rate": 100.0 * int(pr_u.le(DEEP_RATIO).sum()) / usable_rows,
        "n_episodes": ctx_episodes(ev, tape),
        "n_covered": len(ev),
        "cov_rate": 0.0,   # filled below
        "n_matched": mstats["n_matched_events"],
        "n_match_dates": len(daily),
        "mstats": mstats,
        "cells": cells,
        "pooled": pooled,
        "gate": gate,
        "ew_nww_disagree": ew_nww_disagree,
    }
    ctx["cov_rate"] = 100.0 * ctx["n_covered"] / max(ctx["n_episodes"], 1)

    REPORT_PATH.write_text(render_report(ctx), encoding="utf-8")
    print(f"\n[report] wrote {REPORT_PATH}")
    print(f"[outcome] {gate['outcome']}")


def ctx_episodes(ev: pd.DataFrame, tape: pd.DataFrame) -> int:
    """Episode-event count BEFORE the coverage join (for the report pipeline table).
    Recomputed the same way build_stage0_events did (dedup happens pre-coverage)."""
    usable = tape[tape["date"] >= USABLE_FROM]
    deep = usable[usable["premium_ratio"].astype(float).le(DEEP_RATIO).values]
    deep = deep.sort_values(["ticker", "date"])
    last: dict[str, pd.Timestamp] = {}
    n = 0
    for tk, d in zip(deep["ticker"].tolist(), deep["date"].tolist()):
        lk = last.get(tk)
        if lk is None or (d - lk).days > EPISODE_DEDUP_DAYS:
            n += 1
            last[tk] = d
    return n


if __name__ == "__main__":
    main()
