"""Concept canon — ONE implementation per cross-engine concept (audit #7 #12 #28 #40 #45).

The audit found the same named quantity computed 2-3 divergent ways across engines,
with no source of truth: `net liquidity` computed 3 ways (one dropping TGA, one mixing
trillions with billions), `credit impulse` under one label meaning a 1st-derivative in
one engine and a 2nd-derivative in another, `VIX term` from three cached copies, and a
`sector_macro_beta` table with a physically-impossible XLC=1.0 that predates XLC's 2018
launch.  Divergences that can flip SIGN on the same day at the turning points that matter.

This module is the single canonical home.  Every consumer either imports the function
here or is validated byte-for-byte against its committed golden vector
(``tests/test_canon.py`` + ``tests/golden/canon_vectors.json``).  A concept computed two
ways is a bug the moment the two disagree; canon makes "they must agree" a testable
invariant instead of a coincidence.

DESIGN — two call conventions, one formula
------------------------------------------
Concepts are consumed from two data paths in this repo:
  * the ``store``/DataFrame path (``engine.inputs``) — already-scaled billions columns;
  * the raw-parquet ``idx``-reindex path (``engine.anticipation``) — reads FRED parquet
    and scales inline.
Canon exposes the *pure formula* (operating on already-aligned Series) AND a raw-parquet
loader that produces the correctly-scaled components, so both callers share one truth.

The confluence primitives (``rma``, ``ema``, ``rsi``, ``resample_sessions``) are the
CORRECTED math the cross-repo signal contract is anchored to (audit #7): SMA-seeded
Wilder RMA, recursive ``adjust=False`` EMA, and a session-GROUPED 3D/2D resample that
does not mis-split a bucket across a market gap the way calendar ``resample("3B")`` does.
The Terminal's ``signal_layer/confluence.py`` is ported to these and gated against the
exported golden vectors (``scripts/export_signal_contracts.py``).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ═════════════════════════════════════════════════════════════════════════════
# 1 · NET FED LIQUIDITY  (audit #28, #12)
# ═════════════════════════════════════════════════════════════════════════════
# Canonical 3-term definition, BILLIONS:  WALCL_bn − RRP_bn − TGA_bn
# mirroring engine/inputs.py:310 (the regime-overlay canonical).  The two known
# divergences this retires:
#   * anticipation.py used WALCL/1e6 (TRILLIONS) − RRP (billions) — a mixed-unit
#     subtraction that annihilated the balance-sheet trend, reducing the leg to a
#     pure −RRP-velocity proxy (fixed inline in #808; now MIGRATED here).
#   * forex_dollar.py dropped TGA entirely (a bug) and inverts the sign for a
#     dollar framing (intentional — expressed here via `dollar_liquidity_roc`).


def net_liquidity_bn(
    walcl_bn: pd.Series,
    rrp_bn: pd.Series | None,
    tga_bn: pd.Series | None,
) -> pd.Series:
    """Net Fed liquidity in BILLIONS: ``walcl_bn − rrp_bn − tga_bn``.

    ALL three inputs must already be in billions (the caller's responsibility; use
    :func:`load_net_liquidity_components` for the raw-parquet path which scales for you).
    Missing RRP/TGA contribute 0 — a missing drain must NOT annihilate the balance-sheet
    trend pre-history (the original #28 failure mode was the balance-sheet trend, not the
    drain, going to zero).  The unit contract is asserted loudly: if WALCL looks like
    trillions (max < 100) while RRP looks like billions, we have the #28 mixed-unit bug.
    """
    walcl_bn = _as_series(walcl_bn)
    rrp = _as_series(rrp_bn).reindex(walcl_bn.index).fillna(0.0) if rrp_bn is not None \
        else pd.Series(0.0, index=walcl_bn.index)
    tga = _as_series(tga_bn).reindex(walcl_bn.index).fillna(0.0) if tga_bn is not None \
        else pd.Series(0.0, index=walcl_bn.index)
    _assert_billions_scale(walcl_bn, rrp)
    return walcl_bn - rrp - tga


def dollar_liquidity_roc(net_liq_bn: pd.Series, window_d: int = 63) -> pd.Series:
    """USD-framed net-liquidity rate-of-change (audit #12, forex_dollar's variant).

    The dollar desk reads FALLING net liquidity as USD-SUPPORTIVE — i.e. it uses the
    NEGATIVE of the liquidity change.  That sign flip is an intentional dollar framing,
    NOT a different liquidity series; expressing it as an explicit transform of the ONE
    canonical net-liquidity keeps forex_dollar honest (it previously also *dropped TGA*,
    which was a plain bug — see load_net_liquidity_components, which always includes TGA).

    Returns the negated ``window_d``-day change: > 0 ⇒ liquidity draining ⇒ USD supportive.
    """
    return -net_liquidity_bn_change(net_liq_bn, window_d)


def net_liquidity_bn_change(net_liq_bn: pd.Series, window_d: int = 63) -> pd.Series:
    """The signed ``window_d``-day change of net liquidity (billions).  Rising = easing."""
    return _as_series(net_liq_bn).diff(window_d)


def load_net_liquidity_components(
    idx: pd.Index,
    fred_dir: str | Path = "data/fred",
    tga_path: str | Path = "data/treasury/tga.parquet",
) -> dict[str, pd.Series]:
    """Raw-parquet loader (the ``engine.anticipation`` path) → correctly-SCALED billions.

    Unit contract (the #28 bug):
      * WALCL is FRED MILLIONS → /1000 ⇒ billions.  (The old anticipation code used /1e6
        ⇒ trillions, then subtracted a billions-scale RRP: mixed units.)
      * RRP (RRPONTSYD) is ALREADY billions → no scaling.
      * TGA (Treasury General Account) is millions → /1000 ⇒ billions, and was previously
        DROPPED entirely.
    Missing RRP/TGA history contributes 0 (must not annihilate netliq pre-history).

    Returns ``{"walcl_bn", "rrp_bn", "tga_bn", "netliq_bn"}`` so the mixed-unit invariant
    is directly testable on the components.  Never raises on a missing drain file.
    """
    F = Path(fred_dir)
    R = lambda s: s.reindex(idx).ffill()
    col0 = lambda p: (lambda d: d[d.columns[0]])(pd.read_parquet(p))
    walcl_bn = R(col0(F / "WALCL.parquet")) / 1000.0
    try:
        rrp_bn = R(col0(F / "RRPONTSYD.parquet")).fillna(0.0)
    except Exception:  # noqa: BLE001 — a missing drain must not annihilate the trend
        rrp_bn = pd.Series(0.0, index=idx)
    try:
        tga_bn = (R(col0(Path(tga_path))) / 1000.0).fillna(0.0)
    except Exception:  # noqa: BLE001
        tga_bn = pd.Series(0.0, index=idx)
    return {"walcl_bn": walcl_bn, "rrp_bn": rrp_bn, "tga_bn": tga_bn,
            "netliq_bn": net_liquidity_bn(walcl_bn, rrp_bn, tga_bn)}


def _assert_billions_scale(walcl_bn: pd.Series, rrp_bn: pd.Series) -> None:
    """Catch the #28 mixed-unit subtraction LOUDLY.

    Post-2008 WALCL is ~$4-9 TRILLION = 4,000-9,000 in BILLIONS.  The #28 bug scaled WALCL
    by /1e6 (→ trillions, ~4-9) then subtracted a billions-scale RRP/TGA (tens-to-hundreds):
    the balance-sheet term became numerically smaller than the drain, annihilating the
    trend.  A billions-scale WALCL is in the THOUSANDS; a max < 100 means the caller scaled
    to trillions.  This only fires on a WALCL-shaped series (max > 1) so a caller passing an
    empty/degenerate series never trips it.  A pure-normalisation consumer never NaNs on the
    mismatch, so a scale invariant is the only way to catch it."""
    w = pd.to_numeric(walcl_bn, errors="coerce").dropna()
    r = pd.to_numeric(rrp_bn, errors="coerce").dropna()
    if len(w) < 3:
        return  # too short to judge scale (golden-vector fixtures / tests)
    wmax = w.abs().max()
    rmax = r.abs().max() if len(r) else 0.0
    # WALCL in trillions (< 100) while the drain is billions-scale (tens+) → the #28 bug.
    if 1.0 < wmax < 100.0 and rmax > 1.0:
        raise ValueError(
            f"net_liquidity_bn mixed-unit bug (audit #28): WALCL max {wmax:.1f} looks like "
            f"TRILLIONS while the drain max {rmax:.1f} is billions-scale. A billions-scale "
            "balance sheet is in the THOUSANDS — scale WALCL by /1000 (millions→billions), "
            "not /1e6.")


# ═════════════════════════════════════════════════════════════════════════════
# 2 · CHINA CREDIT IMPULSE  (audit #12 — the LABEL COLLISION)
# ═════════════════════════════════════════════════════════════════════════════
# TSF (Total Social Financing) is a monthly FLOW with heavy January seasonality.
# De-seasonalise via a trailing-12m SUM, then:
#   * LEVEL  = the 6-month % change of that 12m sum          (1st derivative — the impulse)
#   * ACCEL  = the 6-month change of the YoY growth rate      (2nd derivative — acceleration)
# china_radar.py used LEVEL, china_strategies.py used ACCEL, both under the label
# "credit impulse" — a mathematically DIFFERENT series feeding leveraged GTAA books vs a
# radar chip.  These are now two NAMES, not one ambiguous label.


def credit_impulse_level(tsf_total: pd.Series) -> pd.Series:
    """Credit-impulse LEVEL: the 6-month % change of the trailing-12m TSF sum.

    == china_radar._sig_credit_impulse:  ``s.rolling(12).sum().pct_change(6)``.
    A 1st-derivative — how fast credit is flowing vs 6 months ago.  Returned as a raw
    fraction (multiply by 100 for the display %)."""
    s = pd.to_numeric(_as_series(tsf_total), errors="coerce").dropna()
    return s.rolling(12).sum().pct_change(6)


def credit_impulse_accel(tsf_total: pd.Series) -> pd.Series:
    """Credit-impulse ACCELERATION: the 6-month change of the 12m-sum YoY growth rate.

    == china_strategies._credit_derisk core:  ``s.rolling(12).sum().pct_change(12) * 100``
    then ``.diff(6)``.  A 2nd-derivative — is credit GROWTH itself speeding up or slowing?
    Returned in the same units china_strategies uses (YoY in %, then a 6m change)."""
    s = pd.to_numeric(_as_series(tsf_total), errors="coerce").dropna()
    yoy = s.rolling(12).sum().pct_change(12) * 100.0
    return yoy.diff(6)


# ═════════════════════════════════════════════════════════════════════════════
# 3 · VIX TERM STRUCTURE  (audit #12)
# ═════════════════════════════════════════════════════════════════════════════
# ONE basis: the VIX / VIX3M ratio (front-month vol vs 3-month).  < 1 = contango (calm);
# ≥ 1 = backwardation (stress).  vol_regime.ts_slope, conditions.vix_term, and
# vol_shock's _f_vix_term (which reads a cached term_ratio) are all THIS ratio; they now
# share one definition instead of three cached copies that can silently drift apart.


def vix_term(vix: pd.Series, vix3m: pd.Series) -> pd.Series:
    """VIX term-structure ratio ``VIX / VIX3M`` (the ONE basis).  ≥ 1 ⇒ backwardation."""
    vix = _as_series(vix)
    v3 = _as_series(vix3m).reindex(vix.index).astype(float)
    return (vix.astype(float) / v3)


def vix_term_scalar(vix: float | None, vix3m: float | None) -> float | None:
    """Scalar VIX/VIX3M for the latest-value consumers (vol_shock reads a cached ratio)."""
    try:
        if vix is None or vix3m is None or float(vix3m) == 0.0:
            return None
        return float(vix) / float(vix3m)
    except (TypeError, ValueError):
        return None


# ═════════════════════════════════════════════════════════════════════════════
# 4 · SECTOR MACRO BETA  (audit #40) — SHADOW artifact (wired, NOT consumed this wave)
# ═════════════════════════════════════════════════════════════════════════════
# playbook.py's heat penalty reads a hand-pasted config.yml table with a physically-
# impossible XLC=1.0 (predates XLC's 2018 launch).  A measured per-sector rate+inflation
# forward-IC (sector_rate_inflation / the transmission calibration) exists but is kept
# display-only because it's noisy.  Canon emits a SHRUNKEN BLEND (measured ⊕ prior) with
# the impossible entries retired — as a SHADOW artifact.  This wave does NOT flip
# playbook.py's consumption (#40's full fix is a later, separately-validated flip).

# SPDR sectors whose measured macro beta is genuinely UNKNOWABLE from the current
# calibration window (no clean pre-2018 history) → force full shrink to a corrected prior.
_XLC_LAUNCH = "2018-06-2018"  # SPDR XLC first traded 2018-06-19; the 1.0 prior is fiction.


def sector_macro_beta_blend(
    prior_table: dict[str, float],
    measured_ic: dict[str, float] | None,
    *,
    shrink_k: float = 8.0,
    measured_n: dict[str, int] | None = None,
) -> dict[str, dict]:
    """Shrunken measured⊕prior sector-macro-beta table (audit #40) — SHADOW ONLY.

    For each sector the blended beta is::

        w      = n / (n + shrink_k)               # measurement confidence
        beta   = w * measured + (1 - w) * prior

    where ``measured`` is the sign-oriented, prior-scaled forward-IC read and ``n`` its
    effective sample.  A sector with NO measured read (e.g. XLC — no pre-2018 history) is
    forced to full shrink (w=0) toward a CORRECTED prior: the impossible XLC=1.0 is
    neutralised to 0.0 rather than carried forward as a textbook fiction.

    Returns ``{sector: {prior, measured, n, w, blended, retired}}`` so the shadow artifact
    is fully auditable.  Does NOT mutate config.yml or touch the live heat score.
    """
    measured_ic = measured_ic or {}
    measured_n = measured_n or {}
    out: dict[str, dict] = {}
    for key, prior in prior_table.items():
        prior_f = float(prior)
        retired = False
        # Retire the physically-impossible XLC=1.0 textbook prior (predates 2018 launch).
        if str(key).strip().upper() in ("XLC", "COMMUNICATIONS", "COMMUNICATION SERVICES"):
            if abs(prior_f - 1.0) < 1e-9:
                prior_f = 0.0          # no clean history → neutral, not a Financials-grade penalty
                retired = True
        meas = measured_ic.get(key)
        n = int(measured_n.get(key, 0))
        if meas is None or n <= 0:
            w = 0.0
            blended = prior_f
        else:
            w = n / (n + float(shrink_k))
            blended = w * float(meas) + (1.0 - w) * prior_f
        out[key] = {
            "prior": round(prior_f, 4),
            "measured": (None if meas is None else round(float(meas), 4)),
            "n": n,
            "w": round(w, 4),
            "blended": round(blended, 4),
            "retired_impossible_prior": retired,
        }
    return out


# ═════════════════════════════════════════════════════════════════════════════
# 5 · CORRECTED CONFLUENCE PRIMITIVES  (audit #7, #45)
# ═════════════════════════════════════════════════════════════════════════════
# The three fixes the audit names (the Terminal's stale fork still uses the WRONG paths):
#   (a) SMA-seeded Wilder RMA        — Pine ta.rma seeds with an SMA of the first n bars;
#                                      pure ewm(alpha=1/n) has a different warm-up that
#                                      flips near-threshold crosses in the early history.
#   (b) recursive adjust=False EMA   — Pine ta.ema is recursive; ewm(span) with the default
#                                      adjust=True is an expanding-weight average that
#                                      disagrees near threshold crosses.
#   (c) session-GROUPED 3D resample  — bucket by trading-SESSION position (every 3rd bar),
#                                      not the calendar "3B" business-day bin, which mis-
#                                      splits a bucket across a holiday/gap (~80% of NVDA
#                                      signal dates relocated on the calendar-bin path).


def rma(series: pd.Series, n: int) -> pd.Series:
    """Wilder's RMA == Pine ``ta.rma``: SMA-seeded, then recursive ``adjust=False``.

    The seed is the SMA of the first ``n`` finite values; before that the output is NaN.
    This differs from a bare ``ewm(alpha=1/n)`` (which begins accumulating from bar 0 with
    an expanding warm-up) exactly where it matters — the early, near-threshold history the
    audit says flips crosses."""
    s = pd.to_numeric(_as_series(series), errors="coerce").astype(float)
    vals = s.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    alpha = 1.0 / n
    # find the first window of n finite values to seed the SMA
    finite = np.isfinite(vals)
    prev = np.nan
    seeded = False
    for i in range(len(vals)):
        if not seeded:
            # seed once we have n finite values ending at i
            if i >= n - 1 and finite[i - n + 1:i + 1].all():
                prev = float(np.mean(vals[i - n + 1:i + 1]))
                out[i] = prev
                seeded = True
            continue
        v = vals[i]
        if not np.isfinite(v):
            out[i] = prev  # carry (Pine na-handling: RMA holds through a gap)
            continue
        prev = alpha * v + (1.0 - alpha) * prev
        out[i] = prev
    return pd.Series(out, index=s.index)


def ema(series: pd.Series, span: int) -> pd.Series:
    """Recursive EMA == Pine ``ta.ema``: ``ewm(span, adjust=False)`` with an ``n``-bar warm-up.

    ``adjust=False`` is the recursive definition TradingView uses; the pandas default
    (``adjust=True``) is an expanding-weight average that disagrees near threshold crosses.
    ``min_periods=span`` keeps the warm-up NaN so early bars don't emit a half-warmed EMA."""
    s = pd.to_numeric(_as_series(series), errors="coerce").astype(float)
    return s.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI on the SMA-seeded RMA (== Pine ``ta.rsi``).  This is the corrected RSI
    the whole confluence cascade rides on; it differs from ``engine.technicals.rsi``
    (bare ``ewm(alpha=1/n)``) only in the early warm-up — but that is where crosses flip."""
    s = pd.to_numeric(_as_series(close), errors="coerce").astype(float)
    d = s.diff()
    up = rma(d.clip(lower=0), n)
    dn = rma((-d).clip(lower=0), n)
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def resample_sessions(daily: pd.Series, n: int) -> tuple[pd.Series, pd.Series]:
    """Session-GROUPED resample: bucket the SESSIONS present (not calendar days) into groups
    of ``n`` and take the last close of each group.  Returns ``(bucketed, known_dates)``
    where ``known_dates`` is the actual last-session date of each bucket (leak-free: a
    downstream ffill onto the daily grid can only reference a bucket AT/AFTER its close).

    Why not ``resample("3B")``: the calendar business-day bin re-anchors on the calendar, so
    a market holiday or a listing gap shifts which sessions share a bucket — the audit
    measured ~80% of NVDA signal dates relocating vs this session-grouped path."""
    s = pd.to_numeric(_as_series(daily), errors="coerce").dropna()
    if s.empty:
        return s, s
    # group by SESSION ORDINAL, not calendar: sessions 0..n-1 → bucket 0, n..2n-1 → bucket 1
    grp = np.arange(len(s)) // n
    df = pd.DataFrame({"v": s.to_numpy(), "d": s.index}, index=s.index)
    df["g"] = grp
    last = df.groupby("g").last()
    bucketed = pd.Series(last["v"].to_numpy(), index=pd.DatetimeIndex(last["d"]))
    known = pd.Series(pd.DatetimeIndex(last["d"]).to_numpy(),
                      index=pd.DatetimeIndex(last["d"]))
    return bucketed, known


def crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b) & (a.shift(1) <= b.shift(1))


def crossunder(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a < b) & (a.shift(1) >= b.shift(1))


def bars_since(cond: pd.Series) -> pd.Series:
    """Bars since ``cond`` was last True (0 on a True bar; NaN before the first True)."""
    pos = np.arange(len(cond))
    last = pd.Series(np.where(cond.to_numpy(), pos, np.nan), index=cond.index).ffill()
    return pd.Series(pos, index=cond.index) - last


# ── confluence params (single source; the Terminal imports these) ─────────────
RSI_LEN, FAST_LEN, BASE_LEN, SIG_LEN = 14, 14, 60, 5
STOCH_LEN, SMOOTH_K, SMOOTH_D = 14, 3, 3
OB, OS = 80, 20
CONF_W, BUY_RSI_MAX, EXT_RSI, REV_BARS = 8, 65, 70, 3
CONFLUENCE_PARAMS = {
    "rsiLen": RSI_LEN, "macd_fast": FAST_LEN, "macd_slow": BASE_LEN, "macd_signal": SIG_LEN,
    "stoch_len": STOCH_LEN, "smooth_k": SMOOTH_K, "smooth_d": SMOOTH_D,
    "ob": OB, "os": OS, "confW": CONF_W, "buy_rsi_max": BUY_RSI_MAX,
    "ext_rsi": EXT_RSI, "rev_bars": REV_BARS, "resample": "session_grouped_3",
    "ema": "adjust_false", "rma": "sma_seeded",
}


def rsi_macd(close: pd.Series):
    """Pine 'RSI-based MACD': EMA(RSI) − slower EMA(RSI), signal = EMA(macd)."""
    r = rsi(close, RSI_LEN)
    macd = ema(r, FAST_LEN) - ema(r, BASE_LEN)
    return macd, ema(macd, SIG_LEN)


def stoch_rsi_kd(close: pd.Series):
    """Pine StochRSI (high amplitude): stochastic OF the RSI, then %K/%D smooth."""
    r = rsi(close, RSI_LEN)
    lo, hi = r.rolling(STOCH_LEN).min(), r.rolling(STOCH_LEN).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k = rawk.rolling(SMOOTH_K).mean()
    return k, k.rolling(SMOOTH_D).mean()


def confluence_signals(daily_close: pd.Series) -> pd.DataFrame:
    """The CORRECTED confluence signal frame — the golden oracle the cross-repo contract
    is anchored to (audit #7).  Faithful port of the live Pine strategy on the session-
    grouped 3D grid, with SMA-seeded RMA + adjust=False EMA throughout.  Columns match the
    Terminal's ``compute_signals`` (macd/sig/k/d/rsi14 + CB/CS/revBuy/revSell + regime
    gates) so ``golden_gate`` can diff them 1:1.  Never raises; empty frame if too short."""
    s3, _known3 = resample_sessions(daily_close, 3)
    if len(s3) < 90:
        return pd.DataFrame()

    macd, sig = rsi_macd(s3)
    k, d = stoch_rsi_kd(s3)
    r14 = rsi(s3, RSI_LEN)

    stoch_bull = crossover(k, d)
    stoch_bear = crossunder(k, d)
    macd_bull = crossover(macd, sig)
    macd_bear = crossunder(macd, sig)

    # weekly confirm-TF gate (one step up from 3D), leak-free (prior CLOSED week)
    wk, _ = _resample_weekly(daily_close, "W-FRI")
    wmacd, wsig = rsi_macd(wk)
    w_bull = (wmacd >= wsig).shift(1)
    w_bull_on3 = w_bull.reindex(s3.index, method="ffill").fillna(False).astype(bool)

    b1_from_os = d.rolling(CONF_W).min() < OS
    s1_from_ob = d.rolling(CONF_W).max() > OB
    recent_b1 = bars_since(stoch_bull) <= CONF_W
    recent_s1 = bars_since(stoch_bear) <= CONF_W

    confirm_bull = w_bull_on3 | b1_from_os
    confirm_bear = (~w_bull_on3) | s1_from_ob
    buy_regime_ok = r14 < BUY_RSI_MAX
    recent_extended = (k.rolling(CONF_W).max() >= OB) | (r14.rolling(CONF_W).max() >= EXT_RSI)

    cb = macd_bull & recent_b1 & confirm_bull & buy_regime_ok
    cs = macd_bear & recent_s1 & confirm_bear & recent_extended

    rev_exit_sell = macd_bear & (bars_since(cb) <= REV_BARS)
    rev_exit_buy = macd_bull & (bars_since(cs) <= REV_BARS)

    ma200 = daily_close.rolling(200).mean()
    above200 = (s3 > ma200.reindex(s3.index).ffill()).fillna(False)
    mo, _ = _resample_weekly(daily_close, "ME")
    mmacd, msig = rsi_macd(mo)
    mo_bull = (mmacd >= msig).shift(1).reindex(s3.index, method="ffill").fillna(False).astype(bool)
    w2, _ = _resample_weekly(daily_close, "2W-FRI")
    w2macd, w2sig = rsi_macd(w2)
    w2_bull = (w2macd >= w2sig).shift(1).reindex(s3.index, method="ffill").fillna(False).astype(bool)

    return pd.DataFrame({
        "close": s3, "macd": macd, "sig": sig, "k": k, "d": d, "rsi14": r14,
        "CB": cb.fillna(False), "CS": cs.fillna(False),
        "revBuy": rev_exit_buy.fillna(False), "revSell": rev_exit_sell.fillna(False),
        "w_bull": w_bull_on3, "above200": above200, "mo_bull": mo_bull,
        "w2_bull": w2_bull,
    })


def _resample_weekly(daily: pd.Series, rule: str) -> tuple[pd.Series, pd.Series]:
    """Calendar resample for the higher confirm timeframes (weekly/2-weekly/monthly).

    These stay CALENDAR-anchored on purpose: the confirm-TF gate is a coarse trend read
    where the exact bucket boundary is immaterial (unlike the 3D signal grid, where the
    session-grouping fix matters).  Returns (bucketed, index) for a uniform call site."""
    s = pd.to_numeric(_as_series(daily), errors="coerce").dropna()
    b = s.resample(rule).last().dropna()
    return b, pd.Series(b.index, index=b.index)


# ═════════════════════════════════════════════════════════════════════════════
# helpers
# ═════════════════════════════════════════════════════════════════════════════
def _as_series(x) -> pd.Series:
    if isinstance(x, pd.Series):
        return x
    return pd.Series(x)
