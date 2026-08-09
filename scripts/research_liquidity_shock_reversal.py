"""Liquidity-shock reversal classifier — PHASE-0 (LSR-P0).

THE CANDIDATE. Separate "this stock is falling because informed investors learned
something bad" from "this stock is falling because someone urgently needed
liquidity". The two charts look identical; the forward paths are supposed to
differ (Savor 2012: shocks WITH information drift, shocks WITHOUT information
reverse). If the separation is real it would give Prophet two things — genuine
mean-reversion candidates, and a veto that stops the momentum engine buying the
last stage of a forced-covering squeeze.

WHAT THIS SCRIPT MEASURES (four questions, one run):

  A. Does the BASE effect exist here at all? Unconditional 1d/5d-formation
     residual reversal across the full tradeable universe, by liquidity tercile,
     with the break-even round-trip cost printed next to the gross edge. If
     short-horizon reversal is not there, no classifier can sort it.
  B. THE HEADLINE CONTRAST. Among +/-3sd high-volume shocks, do no-information
     shocks reverse and information shocks drift? Information proxy = an EDGAR
     8-K filed in [t0-1, t0+1] (earnings item 2.02 and material items separately,
     on acceptance timestamps).
  C. THE CLASSIFIER. Inside the no-information shock population, do the candidate's
     microstructure features (close-location value, intraday recovery, abnormal
     volume/trade-count, average trade size, Amihud price impact, spread proxy,
     flow persistence) rank the forward path?
  D. THE VETO, which has a far lower bar than alpha. Against a transparent
     momentum STAND-IN for the kind of name the board buys, does a fresh shock
     move the forward distribution enough to be worth skipping a trade?

WHAT IT CANNOT MEASURE, AND WHY (state this before reading any result). The
candidate's feature list wants signed order imbalance, quoted spread and a true
price-impact-per-dollar-of-signed-flow. Our massive.com entitlement covers
AGGREGATE products only — the per-trade tape (`trades_v1`) and the NBBO
(`quotes_v1`) both 403 (collectors/massive_flatfiles). So the order-flow half of
the proposal is proxied from daily bars (close-location value, average trade size
from the `transactions` count, Corwin-Schultz high-low spread, Amihud) and is
NOT tested at its intended fidelity. A null here closes the OHLCV-grade
construction; it does not close the tape-grade one.

INFERENCE. Shock events cluster into market-wide selloff days, so every interval
is a circular block bootstrap over TRADING DATES (the same resampling scheme as
engine.validation.block_bootstrap_ci), never over name-days, and every arm
contrast is also computed WITHIN date so the tape cancels exactly.

DATA HONESTY.
  * Prices are data/massive_stock_day (~20.5k names, 2021-07-06..present) —
    UNADJUSTED. A 10:1 split reads as a -90% shock, i.e. exactly the event this
    study triggers on. Split repair reuses the canonical yahoo-verified detector
    scripts.replay_standout_pipeline.split_adjust; every bar it touches is stamped
    and made INELIGIBLE, because its snap band can swallow a genuine one-day crash.
    Measured against the 231 overlapping adjusted names in data/stocks, repair cuts
    >10pp daily disagreements from 36 to 10; the 10 residuals are SPINOFFS (GE, DD,
    T, EXC, MMM, DHR, WDC, BKNG), which massive does not adjust and we do not repair.
  * Dividends are not adjusted either (a ~0.5% ex-date drop is noise against a 3sd
    trigger, but it is a small downward bias in every forward window).
  * The information firewall only sees names in data/edgar — 1,314 tickers. Results
    are reported on that covered subset and the coverage rate is printed.

Run: PYTHONPATH=. python -m scripts.research_liquidity_shock_reversal [--panel-cache DIR]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from lib import config  # noqa: E402
from scripts.replay_standout_pipeline import split_adjust  # noqa: E402

log = logging.getLogger("lsr")

# ── frozen design constants (set before any outcome was inspected) ───────────
Z_TRIGGER = 3.0          # residual-return z that defines a shock
VOL_TRIGGER = 2.0        # x trailing-60d median volume
MIN_PRICE = 5.0
MIN_ADV_PANEL = 2e6      # universe floor
MIN_ADV_EVENT = 5e6      # event-eligibility floor
BASE_WIN = 60            # trailing baseline window
FWD_HORIZONS = (1, 3, 5, 10, 21)
NEWS_WINDOW_DAYS = 1     # +/- calendar days around an 8-K filing date
ERA_CUT = "2024-03-01"   # split-half boundary
FAMILY = "liquidity_shock_reversal_p0"


# ══════════════════════════════════════════════════════════════════════════════
# pure helpers (unit-tested in tests/test_liquidity_shock_reversal.py)
# ══════════════════════════════════════════════════════════════════════════════
def corwin_schultz(high: pd.DataFrame, low: pd.DataFrame) -> pd.DataFrame:
    """Corwin-Schultz (2012) two-day high-low effective-spread estimate, per name-day.

    Returns the PROPORTIONAL spread, negatives clipped to 0 (the estimator goes
    negative for roughly half of name-days by construction).

    NOT A COST ESTIMATE — DO NOT SUBTRACT IT FROM A RETURN. Measured on simulated
    paths with a KNOWN planted spread (tests/test_liquidity_shock_reversal.py), the
    clipped mean is dominated by VOLATILITY, not by the spread: a 5bp true spread
    reads 38bp at 1.5%/day vol and 74bp at 3%/day vol, rising only to 80bp / 110bp
    when the true spread is actually 100bp. On a shock-day population — high
    volatility by selection — the estimator therefore reads a large "spread" that is
    mostly the day's range. It is usable as a RELATIVE cross-sectional ranking at
    comparable volatility, and that is all this study uses it for. The cost gate is
    expressed as a BREAK-EVEN in basis points, never as a subtracted point estimate.
    (Upward bias also documented in Holden & Jacobs 2014.)
    """
    hl = np.log(high / low) ** 2
    beta = hl + hl.shift(1)
    gamma = np.log(np.maximum(high, high.shift(1)) / np.minimum(low, low.shift(1))) ** 2
    den = 3.0 - 2.0 * np.sqrt(2.0)
    alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / den - np.sqrt(gamma / den)
    return (2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))).clip(lower=0.0)


def sector_ex_self_peer(ret: pd.DataFrame, sector: pd.Series, min_peers: int = 4) -> pd.DataFrame:
    """Equal-weighted same-sector EX-SELF peer return, per name-day.

    The residual basis for the whole study. Ex-self matters: including the subject in
    its own benchmark shrinks its residual toward zero exactly on the extreme days the
    trigger fires. Names with no sector label, or with fewer than `min_peers` labelled
    peers priced that day, fall back to the equal-weighted whole-universe mean.
    """
    peer = pd.DataFrame(np.nan, index=ret.index, columns=ret.columns)
    labelled = sector.reindex(ret.columns).dropna()
    for names in labelled.groupby(labelled).groups.values():
        names = list(names)
        sub = ret[names]
        n = sub.notna().sum(axis=1)
        tot = sub.sum(axis=1, min_count=1)
        exself = (tot.values[:, None] - sub.values) / np.maximum(n.values[:, None] - 1, 1)
        peer[names] = np.where(n.values[:, None] >= min_peers, exself, np.nan)
    mkt = ret.mean(axis=1)
    return peer.apply(lambda c: c.fillna(mkt))


def date_block_ci(per_date, block: int = 5, B: int = 4000, seed: int = 7) -> dict:
    """Mean of a per-DATE series with a circular block-bootstrap 95% CI over dates.

    Blocks preserve the day-to-day autocorrelation of a clustered event tape. The unit
    is the trading date, never the name-day: shocks arrive in market-wide bunches, so
    name-day standard errors overstate precision by roughly the average cluster size.
    """
    x = pd.Series(per_date).dropna().to_numpy(dtype=float)
    n = len(x)
    if n < 20:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": n}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    grid = np.arange(block)
    means = np.empty(B)
    for k in range(B):
        idx = (rng.integers(0, n, nb)[:, None] + grid[None, :]).ravel()[:n] % n
        means[k] = x[idx].mean()
    return {"mean": float(x.mean()), "lo": float(np.percentile(means, 2.5)),
            "hi": float(np.percentile(means, 97.5)), "n": n}


def break_even_bps(gross_spread_pct: float, n_legs: int = 2) -> float:
    """Round-trip cost PER LEG (bps) at which a long-short spread return goes to zero.

    A decile long/short pays a round trip on both legs each cycle, so the edge dies at
    gross/n_legs. Reported instead of a subtracted point estimate because our only
    spread measurement (Corwin-Schultz) is a biased-high proxy.
    """
    return float(gross_spread_pct) / n_legs * 100.0


# ══════════════════════════════════════════════════════════════════════════════
# panel
# ══════════════════════════════════════════════════════════════════════════════
def build_panel(cache: Path, massive_dir: Path, *, min_price: float = MIN_PRICE,
                min_adv: float = MIN_ADV_PANEL) -> dict[str, pd.DataFrame]:
    """Split-repaired, liquidity-filtered wide OHLCV panel. Cached — the scan is ~50s.

    `min_price`/`min_adv` are parameters so the illiquid-tail reopener re-measures at a
    lower floor through THIS builder rather than forking the split repair (which is the
    part that is easy to get wrong and expensive to re-verify).
    """
    cols = ("open", "high", "low", "close", "volume", "transactions", "split_day")
    if all((cache / f"panel_{c}.parquet").exists() for c in cols):
        log.info("lsr: panel cache hit at %s", cache)
        return {c: pd.read_parquet(cache / f"panel_{c}.parquet") for c in cols}

    files = sorted(massive_dir.glob("*.parquet"))
    log.info("lsr: scanning %d tickers in %s", len(files), massive_dir)
    keep: dict[str, pd.DataFrame] = {}
    for f in files:
        try:
            df = pd.read_parquet(f)
        except Exception:  # noqa: BLE001 — a torn vendor file must not kill the scan
            continue
        if len(df) < 400 or not {"open", "high", "low", "close", "volume"} <= set(df.columns):
            continue
        df = df[~df.index.duplicated(keep="last")].sort_index()
        px = df["close"].astype(float).dropna()
        vol = df["volume"].astype(float)
        if len(px) < 400 or px.tail(252).median() < min_price or (px * vol).median() < min_adv:
            continue
        factor = (px / split_adjust(px)).reindex(df.index).ffill().bfill()
        keep[f.stem] = pd.DataFrame({
            "open": df["open"].astype(float) / factor,
            "high": df["high"].astype(float) / factor,
            "low": df["low"].astype(float) / factor,
            "close": df["close"].astype(float) / factor,
            "volume": vol * factor,
            "transactions": (df["transactions"].astype(float) if "transactions" in df else np.nan),
            "split_day": (factor.diff().fillna(0.0).abs() > 1e-9),
        })
    log.info("lsr: %d tradeable names", len(keep))
    cache.mkdir(parents=True, exist_ok=True)
    out = {}
    for c in cols:
        fr = pd.DataFrame({t: d[c] for t, d in keep.items()}).sort_index()
        if c == "split_day":
            fr = fr.fillna(False).astype(bool)
        fr.to_parquet(cache / f"panel_{c}.parquet")
        out[c] = fr
    return out


def derive(panel: dict[str, pd.DataFrame], data_dir: Path, *, min_price: float = MIN_PRICE,
           min_adv_event: float = MIN_ADV_EVENT) -> dict:
    """Residual returns, the candidate's feature set, and forward outcomes."""
    close, high, low = panel["close"], panel["high"], panel["low"]
    op, vol, txn = panel["open"], panel["volume"], panel["transactions"]
    splitd = panel["split_day"].reindex_like(close).fillna(False)

    ret = close.pct_change().where(lambda r: r.abs() < 0.90)      # bad-print guard
    sec = pd.read_parquet(data_dir / "breadth/ticker_sectors.parquet").set_index("ticker")["sector"]
    peer = sector_ex_self_peer(ret, sec)
    resid = ret - peer

    sd = resid.rolling(BASE_WIN, min_periods=40).std().shift(1)
    dv = close * vol
    dv_med = dv.rolling(BASE_WIN, min_periods=40).median().shift(1)
    amihud = ret.abs() / dv.replace(0, np.nan)

    f = {
        "resid_z": resid / sd,
        "abn_volume": vol / vol.rolling(BASE_WIN, min_periods=40).median().shift(1),
        "abn_txn": txn / txn.rolling(BASE_WIN, min_periods=40).median().shift(1),
        "avg_trade_size_rel": (vol / txn) / (vol / txn).rolling(BASE_WIN, min_periods=40).median().shift(1),
        "clv": (close - low) / (high - low).replace(0, np.nan),
        "gap": op / close.shift(1) - 1.0,
        "intraday_ret": close / op - 1.0,
        "amihud_rel": amihud / amihud.rolling(BASE_WIN, min_periods=40).median().shift(1),
        "spread_shock": corwin_schultz(high, low),
        "prior5_resid": resid.shift(1).rolling(5, min_periods=3).sum(),
        "run_sign": np.sign(resid).fillna(0.0).rolling(3, min_periods=3).sum().shift(1),
        "dv_med": dv_med,
        "ret": ret, "resid": resid, "close": close,
    }
    f["spread_base"] = f["spread_shock"].rolling(20, min_periods=10).mean().shift(1)

    cum = np.log1p(resid.clip(-0.9, 5.0)).cumsum()
    fwd = {h: cum.shift(-h) - cum for h in FWD_HORIZONS}          # t+1..t+h, no overlap with t
    eligible = (~splitd) & (close >= min_price) & (dv_med >= min_adv_event) & sd.notna()
    return {"f": f, "cum": cum, "fwd": fwd, "eligible": eligible, "resid": resid, "dv_med": dv_med}


def news_flags(ev: pd.DataFrame, data_dir: Path) -> pd.DataFrame:
    """Stamp each event with the EDGAR information firewall.

    A filing on day d covers [d-1, d+1] in CALENDAR days, which also lifts a
    Friday-night filing onto the Monday shock it explains.
    """
    e8k = pd.read_parquet(data_dir / "edgar/earnings_8k_dates.parquet")
    m8k = pd.read_parquet(data_dir / "edgar/material_8k_events.parquet")
    m8k = m8k[m8k["form"] == "8-K"]
    for df in (e8k, m8k):
        df["filing_date"] = pd.to_datetime(df["filing_date"])

    def keys(filings: pd.DataFrame) -> set:
        out = set()
        for t, g in filings.groupby("ticker"):
            for d in pd.to_datetime(g["filing_date"].unique()):
                for off in range(-NEWS_WINDOW_DAYS, NEWS_WINDOW_DAYS + 1):
                    out.add((t, d + pd.Timedelta(days=off)))
        return out

    ke, km = keys(e8k), keys(m8k)
    ev["cov_earn8k"] = ev["ticker"].isin(set(e8k["ticker"].unique()))
    ev["earn8k"] = [(t, d) in ke for t, d in zip(ev["ticker"], ev["date"])]
    ev["mat8k"] = [(t, d) in km for t, d in zip(ev["ticker"], ev["date"])]
    ev["news"] = ev["earn8k"] | ev["mat8k"]
    return ev


def harvest_events(d: dict) -> pd.DataFrame:
    """Every +/-3sd high-volume shock, with its features and forward outcomes."""
    f, fwd, elig = d["f"], d["fwd"], d["eligible"]
    z, av = f["resid_z"], f["abn_volume"]
    frames = []
    for side, mask in (("down", elig & (z <= -Z_TRIGGER) & (av >= VOL_TRIGGER)),
                       ("up", elig & (z >= Z_TRIGGER) & (av >= VOL_TRIGGER))):
        idx = np.argwhere(mask.to_numpy())
        if not len(idx):
            continue
        rec = {"date": mask.index.to_numpy()[idx[:, 0]],
               "ticker": np.asarray(mask.columns)[idx[:, 1]], "side": side}
        for k, fr in f.items():
            rec[k] = fr.to_numpy()[idx[:, 0], idx[:, 1]]
        for h, fr in fwd.items():
            rec[f"fwd{h}"] = fr.to_numpy()[idx[:, 0], idx[:, 1]]
        frames.append(pd.DataFrame(rec))
    ev = pd.concat(frames, ignore_index=True)
    ev["date"] = pd.to_datetime(ev["date"])
    return ev


# ══════════════════════════════════════════════════════════════════════════════
# the four questions
# ══════════════════════════════════════════════════════════════════════════════
def question_a(d: dict) -> list[dict]:
    """Does unconditional short-horizon residual reversal exist, and what does it cost?"""
    cum, elig, dv = d["cum"], d["eligible"], d["dv_med"]
    terc = dv.rank(axis=1, pct=True)
    out = []
    for lb in (1, 5):
        sig = -(cum - cum.shift(lb))                       # positive = the reversal bet
        for hz in (1, 5, 10):
            fwd = cum.shift(-hz) - cum
            for tname, lo, hi in (("illiquid", 0.0, 1 / 3), ("mid", 1 / 3, 2 / 3), ("liquid", 2 / 3, 1.01)):
                m = elig & (terc >= lo) & (terc < hi) & sig.notna() & fwd.notna()
                s, fv = sig.where(m), fwd.where(m)
                ic = date_block_ci(s.corrwith(fv, axis=1, method="spearman"))
                pr = s.rank(axis=1, pct=True)
                sp = (fv.where(pr >= 0.9).mean(axis=1) - fv.where(pr <= 0.1).mean(axis=1)) \
                    .where(m.sum(axis=1) >= 30)
                dec = date_block_ci(sp)
                out.append({"lookback_d": lb, "horizon_d": hz, "tercile": tname,
                            "rank_ic": ic, "decile_spread_pct": {k: (100 * v if k in ("mean", "lo", "hi") else v)
                                                                 for k, v in dec.items()},
                            "break_even_bps_per_leg": break_even_bps(100 * dec["mean"]),
                            "cycles_per_year": round(252 / hz, 1)})
    return out


def _arm(ev: pd.DataFrame, h: int) -> pd.Series:
    return ev.groupby("date")[f"fwd{h}"].mean()


def question_b(ev: pd.DataFrame) -> list[dict]:
    """News vs no-news, per side, per horizon, plus the WITHIN-DATE paired difference."""
    out = []
    for side in ("down", "up"):
        s = ev[ev["side"] == side]
        for h in FWD_HORIZONS:
            for label, sub in (("no_news", s[~s["news"]]), ("news", s[s["news"]])):
                ci = date_block_ci(_arm(sub, h))
                out.append({"side": side, "horizon_d": h, "arm": label, "n_events": len(sub),
                            "mean_pct": 100 * ci["mean"], "lo_pct": 100 * ci["lo"],
                            "hi_pct": 100 * ci["hi"], "n_dates": ci["n"],
                            "hit_rate": float((sub[f"fwd{h}"] > 0).mean())})
            diff = (_arm(s[~s["news"]], h) - _arm(s[s["news"]], h)).dropna()
            ci = date_block_ci(diff)
            out.append({"side": side, "horizon_d": h, "arm": "DIFF_no_news_minus_news",
                        "n_events": len(diff), "mean_pct": 100 * ci["mean"],
                        "lo_pct": 100 * ci["lo"], "hi_pct": 100 * ci["hi"], "n_dates": ci["n"],
                        "excludes_zero": bool(ci["lo"] > 0 or ci["hi"] < 0)})
    return out


CLASSIFIER_FEATURES = ["clv", "intraday_ret", "gap", "abn_volume", "abn_txn",
                       "avg_trade_size_rel", "amihud_rel", "spread_shock",
                       "prior5_resid", "resid_z", "run_sign", "dv_med"]


def question_c(ev: pd.DataFrame) -> list[dict]:
    """Do the candidate's microstructure features rank the forward path inside the
    no-information shock population? Date-clustered rank-IC per feature per horizon."""
    d = ev[(ev["side"] == "down") & ev["cov_earn8k"] & ~ev["news"]]
    out = []
    for h in (3, 5, 10):
        for feat in CLASSIFIER_FEATURES:
            ics = []
            for _, g in d.groupby("date"):
                if g[feat].notna().sum() >= 5 and g[f"fwd{h}"].notna().sum() >= 5:
                    c = g[feat].corr(g[f"fwd{h}"], method="spearman")
                    if np.isfinite(c):
                        ics.append(c)
            ci = date_block_ci(ics)
            out.append({"horizon_d": h, "feature": feat, "rank_ic": ci["mean"],
                        "lo": ci["lo"], "hi": ci["hi"], "n_dates": ci["n"],
                        "excludes_zero": bool(np.isfinite(ci["lo"]) and (ci["lo"] > 0 or ci["hi"] < 0))})
    return out


def question_d(panel: dict, d: dict) -> list[dict]:
    """The veto, against a momentum STAND-IN for the kind of name the board buys.

    The live frames cannot answer this: data/prophet_postmortem holds 808 episodes over
    24 board dates and us_board_ledger/retro_grades 2,282 rows over five weeks — one
    regime, no power against a ~0.3pp effect. So this is the roadmap's "retro stand-in
    first" pattern, and it is labelled a stand-in, not the board.
    """
    close, cum, elig = panel["close"], d["cum"], d["eligible"]
    f = d["f"]
    sma200 = close.rolling(200, min_periods=150).mean()
    hi252 = close.rolling(252, min_periods=200).max()
    mom63 = cum - cum.shift(63)
    base = elig & (close > sma200) & (close >= 0.85 * hi252) & (mom63.rank(axis=1, pct=True) >= 2 / 3)
    up = base & (f["resid_z"] >= Z_TRIGGER) & (f["abn_volume"] >= VOL_TRIGGER)
    dn = base & (f["resid_z"] <= -Z_TRIGGER) & (f["abn_volume"] >= VOL_TRIGGER)

    out = []
    for h in (5, 10, 21):
        fwd = cum.shift(-h) - cum
        b = fwd.where(base).mean(axis=1)
        for name, mask in (("base_standin", base), ("V1_chase_up_shock", up), ("V2_flush_down_shock", dn)):
            ci = date_block_ci(fwd.where(mask).mean(axis=1))
            out.append({"horizon_d": h, "state": name, "n_name_days": int(mask.sum().sum()),
                        "mean_pct": 100 * ci["mean"], "lo_pct": 100 * ci["lo"], "hi_pct": 100 * ci["hi"]})
        for name, mask in (("V1_gap_vs_base", up), ("V2_gap_vs_base", dn)):
            ci = date_block_ci((fwd.where(mask).mean(axis=1) - b).dropna())
            out.append({"horizon_d": h, "state": name, "n_dates": ci["n"],
                        "mean_pct": 100 * ci["mean"], "lo_pct": 100 * ci["lo"], "hi_pct": 100 * ci["hi"],
                        "excludes_zero": bool(ci["lo"] > 0 or ci["hi"] < 0)})
    return out


def firewall_validity(ev: pd.DataFrame) -> dict:
    """Prove the information flag DISCRIMINATES before believing a null built on it.

    A null from a flag that is really noise is worthless. Earnings shocks must look
    obviously different from no-news shocks — bigger overnight gap above all, because
    earnings move overnight while a liquidity shock moves intraday.
    """
    d = ev[(ev["side"] == "down") & ev["cov_earn8k"]]
    med = d.groupby("news")[["ret", "abn_volume", "abn_txn", "gap", "resid_z"]].median()
    return {
        "n_covered_down_shocks": len(d),
        "news_rate": float(d["news"].mean()),
        "median_by_arm": {str(k): {c: float(v) for c, v in row.items()} for k, row in med.iterrows()},
        "gap_ratio_news_over_no_news": float(med.loc[True, "gap"] / med.loc[False, "gap"])
        if False in med.index and True in med.index else None,
    }


# ══════════════════════════════════════════════════════════════════════════════
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel-cache", default=None, help="dir for the cached wide panel")
    ap.add_argument("--massive-dir", default=None, help="override data/massive_stock_day")
    ap.add_argument("--out", default=None, help="report JSON path")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    data_dir = Path(config.data_dir())
    massive = Path(args.massive_dir) if args.massive_dir else data_dir / "massive_stock_day"
    cache = Path(args.panel_cache) if args.panel_cache else data_dir / "research" / "lsr_p0_panel"
    if not massive.exists() or not any(massive.glob("*.parquet")):
        print(f"::warning title=lsr-p0::massive_stock_day absent at {massive} — cannot run", flush=True)
        return 1

    panel = build_panel(cache, massive)
    d = derive(panel, data_dir)
    ev = news_flags(harvest_events(d), data_dir)
    covered = ev[ev["cov_earn8k"]]

    report = {
        "study": "LSR-P0 liquidity-shock reversal classifier, phase-0",
        "family": FAMILY,
        "design": {
            "z_trigger": Z_TRIGGER, "vol_trigger": VOL_TRIGGER,
            "min_price": MIN_PRICE, "min_adv_event_usd": MIN_ADV_EVENT,
            "residual_basis": "equal-weighted same-sector ex-self peer return",
            "news_proxy": "EDGAR 8-K (earnings item 2.02 + material) within +/-1 calendar day",
            "inference": "circular block bootstrap over trading dates, block=5",
            "frozen_before_outcomes": True,
        },
        "coverage": {
            "universe_names": int(panel["close"].shape[1]),
            "panel_span": [str(panel["close"].index.min().date()), str(panel["close"].index.max().date())],
            "events_total": len(ev),
            "events_down": int((ev["side"] == "down").sum()),
            "events_up": int((ev["side"] == "up").sum()),
            "events_8k_covered": len(covered),
            "8k_coverage_rate": float(ev["cov_earn8k"].mean()),
            "covered_names": int(covered["ticker"].nunique()),
            "covered_dates": int(covered["date"].nunique()),
        },
        "firewall_validity": firewall_validity(ev),
        "A_unconditional_reversal": question_a(d),
        "B_news_contrast": question_b(covered),
        "C_microstructure_classifier": question_c(ev),
        "D_veto_standin": question_d(panel, d),
        "cannot_measure": [
            "signed order imbalance — no per-trade tape (massive trades_v1 403)",
            "quoted/effective spread from NBBO — no quotes_v1 entitlement",
            "true intraday recovery path — no equity minute aggregates entitlement",
            "sub-$5 / sub-$5m-ADV tail — excluded by the tradeability floor",
            "information beyond EDGAR 8-K (analyst revisions, newswire) — Savor 2012 used analyst reports",
        ],
    }
    out = Path(args.out) if args.out else data_dir / "research" / "lsr_p0_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    log.info("lsr: wrote %s", out)

    diffs = [r for r in report["B_news_contrast"] if r["arm"] == "DIFF_no_news_minus_news"]
    n_sep = sum(1 for r in diffs if r.get("excludes_zero"))
    n_cls = sum(1 for r in report["C_microstructure_classifier"] if r.get("excludes_zero"))
    n_veto = sum(1 for r in report["D_veto_standin"] if r.get("excludes_zero"))
    log.info("lsr: separation %d/%d contrasts, classifier %d/%d features, veto %d gaps exclude zero",
             n_sep, len(diffs), n_cls, len(report["C_microstructure_classifier"]), n_veto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
