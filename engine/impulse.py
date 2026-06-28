"""Impulse Tracker — a fast, reactive EARLY-IGNITION screen for the US equity tape.

The product question this answers: *which names are JUST STARTING to accelerate —
where price/volume velocity is turning up NOW and the move has not already run* —
so an entry still exists. It is the opposite of a "biggest movers" list: a name that
already ripped +40% is explicitly demoted (no entry left), and a name whose
acceleration is rolling over is routed to a FADING lane, never a buy.

WHAT IT MEASURES (per name, daily bars, all causal / point-in-time):
  • price velocity     1st derivative — short-EMA slope of log returns.
  • price acceleration 2nd derivative — fast-EMA slope pulling ABOVE the slow-EMA
                       slope, normalised by the name's own return vol (``accel_z``),
                       plus the denoised MACD-histogram impulse (z(hist)×efficiency).
  • volume velocity    relative volume (RVOL vs 20d median) + a short/slow volume
                       ratio — is participation waking up to confirm the ramp?
  • extension gates    20d run-up, distance above the 50/200d MA, percentile within
                       the 252d range — used to EXCLUDE names that already ran.
  • absolute trend     ``slope_z`` t-stat — a hard down-trend gate (no falling knives).

HONESTY GATE (load-bearing — mirrors engine/velocity.py and the house discipline):
short-horizon DIRECTION on this tape is a measured coin-flip (Brier skill ≈ 0) and
momentum's forward edge is REGIME-SWITCHED (IC ≈ +0.03 in calm tape, ≤0 in stress).
So this engine is a *reactive timing / context screen*, NOT a validated standalone
alpha. It is regime-aware (it surfaces the calm/stress state and flags reduced
confidence in stress) and it never claims a P(up). Everything is display/context until
a leg earns its own Phase-0 pass (engine/signal_lab.py). Nothing here feeds a score
elsewhere in the system.

Pure transforms only: the recompute-on-truncated == full-history test must hold
(see tests/test_impulse.py). Missing data stays NaN — never silently 0 (a name with
no volume is "unknown", not "no impulse"). Reuses velocity.impulse / velocity.
efficiency_ratio / indicators.slope_z verbatim (they vectorise column-wise over the
wide panel, byte-identically to the per-Series path).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from engine import indicators, velocity

# canonical state vocabulary (the buy lane is EARLY_IGNITION)
EARLY_IGNITION = "EARLY_IGNITION"   # accelerating + volume confirming + NOT yet extended  → the entry
IGNITING = "IGNITING"               # accelerating, constructive, but lighter confirmation
EXTENDED_RUN = "EXTENDED_RUN"       # accelerating BUT already ran — no entry, wait for a pullback
COILING = "COILING"                 # quiet base, volume just starting to tick — pre-ignition watch
FADING = "FADING"                   # acceleration rolling over / trend down — exit / avoid
NEUTRAL = "NEUTRAL"                 # no clear impulse


@dataclass(frozen=True)
class ImpulseConfig:
    """All windows + gate thresholds in one place (overridable from config.yml).

    Defaults are tuned for *daily* bars and a ~1-5 day "just igniting" horizon. The
    extension gates encode the core product rule: a name only qualifies for the BUY
    lane while the move is still young.
    """
    # --- derivative windows ---
    vel_fast: int = 5          # fast EMA span for the velocity (1st derivative) of log returns
    vel_slow: int = 20         # slow EMA span — accel = fast − slow
    vol_norm_win: int = 20     # window to normalise acceleration by the name's own return vol
    macd_fast: int = 12
    macd_slow: int = 26
    macd_sig: int = 9
    er_n: int = 10             # efficiency-ratio window (move cleanliness)
    z_win: int = 60            # z-window for the MACD-histogram impulse
    trend_slope_w: int = 20    # absolute-trend slope window
    trend_base_w: int = 60     # absolute-trend baseline-vol window
    ma_short: int = 50
    ma_long: int = 200
    high_win: int = 252        # 52w window for the off-high / range-percentile gate
    # --- volume windows (the wide volume cache is shallow ~23 sessions) ---
    rvol_win: int = 20         # RVOL = last volume / median of this window
    vol_vel_fast: int = 3      # short volume window for the velocity ratio
    vol_vel_slow: int = 20     # slow volume window for the velocity ratio
    # --- gates / thresholds ---
    min_history: int = 40            # need at least this many closes to score a name
    min_dollar_vol: float = 3.0e6    # liquidity floor on 20d average dollar volume
    accel_early_z: float = 0.5       # accel_z above this = the acceleration is meaningfully up
    vol_confirm: float = 1.05        # vol-velocity ratio above this = participation waking up
    rvol_confirm: float = 1.30       # OR RVOL above this confirms volume
    runup_extended: float = 0.22     # 20d run-up at/above this = already ran (no entry)
    runup_early_max: float = 0.15    # the BUY lane wants the recent run-up still small
    ext50_extended: float = 0.20     # >20% above the 50dMA = stretched
    ext200_extended: float = 0.40    # >40% above the 200dMA = a sustained runner, demote
    trend_hard_down: float = -1.5    # slope_z below this = active down-trend (falling knife) → no buy
    coil_runup_max: float = 0.04     # COILING base: barely moved on price...
    coil_vol_min: float = 1.15       # ...but volume just starting to perk up
    # NOTE: 52w-range percentile is intentionally NOT an extension gate — a fresh
    # breakout to new highs on a small recent run-up is the EARLY entry we want, not
    # a name to exclude. "Already ran" is measured by recent run-up + MA distance.

    @classmethod
    def from_config(cls, d: dict | None) -> "ImpulseConfig":
        """Build from a (possibly partial) config.yml ``impulse:`` mapping; unknown
        keys are ignored, missing keys keep the default. Values are coerced to each
        field's declared type so a YAML quirk (e.g. ``3.0e6`` parsing as a string)
        can never reach the comparisons and break the build."""
        if not d:
            return cls()
        # `from __future__ import annotations` makes fld.type the string name.
        casters = {"int": int, "float": float}
        out: dict = {}
        for name, fld in cls.__dataclass_fields__.items():
            if name not in d:
                continue
            cast = casters.get(fld.type)
            try:
                out[name] = cast(d[name]) if cast else d[name]
            except (TypeError, ValueError):
                continue  # keep the default for an un-coercible value
        return cls(**out)

    def as_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
#  low-level vectorised transforms (column-wise over the wide panel)
# --------------------------------------------------------------------------- #
def _log_returns(closes: pd.DataFrame) -> pd.DataFrame:
    """Daily log returns; non-positive prices → NaN (never a fake 0)."""
    return np.log(closes.where(closes > 0)).diff()


def accel_z_panel(closes: pd.DataFrame, cfg: ImpulseConfig) -> pd.DataFrame:
    """Acceleration z-panel: the fast-EMA return slope pulling above the slow-EMA
    slope, normalised by the name's own trailing return volatility. Positive &
    rising = the move is accelerating; this is the core "igniting" gauge. Causal."""
    lr = _log_returns(closes)
    vel_fast = lr.ewm(span=cfg.vel_fast, adjust=False, min_periods=cfg.vel_fast).mean()
    vel_slow = lr.ewm(span=cfg.vel_slow, adjust=False, min_periods=cfg.vel_slow).mean()
    sig = lr.rolling(cfg.vol_norm_win, min_periods=max(5, cfg.vol_norm_win // 2)).std(ddof=0)
    return (vel_fast - vel_slow) / sig.replace(0, np.nan)


def velocity_pct_panel(closes: pd.DataFrame, cfg: ImpulseConfig) -> pd.DataFrame:
    """1st-derivative velocity as an interpretable %/day (fast-EMA of daily returns)."""
    lr = _log_returns(closes)
    return lr.ewm(span=cfg.vel_fast, adjust=False, min_periods=cfg.vel_fast).mean()


def igniting_panel(closes: pd.DataFrame, cfg: ImpulseConfig) -> pd.DataFrame:
    """Boolean panel: where acceleration is up (accel_z over the early threshold AND
    the denoised MACD impulse positive). Used for ``days_since_ignition``."""
    az = accel_z_panel(closes, cfg)
    imp = velocity.impulse(closes, fast=cfg.macd_fast, slow=cfg.macd_slow,
                           sig=cfg.macd_sig, er_n=cfg.er_n, z_win=cfg.z_win)
    return (az > cfg.accel_early_z) & (imp > 0)


def days_since_ignition(closes: pd.DataFrame, cfg: ImpulseConfig) -> pd.Series:
    """Per-name count of *consecutive most-recent* sessions the name has been igniting
    (0 = not igniting today). 1 = "broke out today" (freshest); higher = older ramp.
    Vectorised trailing-run-length via reversed cumulative-AND."""
    ig = igniting_panel(closes, cfg).to_numpy()
    if ig.shape[0] == 0:
        return pd.Series(dtype=float, index=closes.columns)
    rev = ig[::-1]
    # NaN→False so a gap breaks the run; cumprod down the reversed axis = leading-True run
    run = np.cumprod(np.where(np.isnan(rev), 0, rev), axis=0).sum(axis=0)
    return pd.Series(run.astype(float), index=closes.columns)


def _winsor_z(s: pd.Series, cap: float = 3.0) -> pd.Series:
    """Cross-sectional z-score, robustly clipped (median/MAD, fallback mean/std)."""
    s = s.astype(float)
    med = s.median()
    mad = (s - med).abs().median()
    if mad and np.isfinite(mad):
        z = 0.6745 * (s - med) / mad
    else:
        sd = s.std(ddof=0)
        z = (s - s.mean()) / sd if sd else s * 0.0
    return z.clip(-cap, cap)


# --------------------------------------------------------------------------- #
#  the cross-section: one row per ticker at `asof`
# --------------------------------------------------------------------------- #
def compute_features(closes: pd.DataFrame, volumes: pd.DataFrame | None = None, *,
                     asof: pd.Timestamp | None = None,
                     cfg: ImpulseConfig = ImpulseConfig()) -> pd.DataFrame:
    """Per-ticker impulse FEATURES at ``asof`` (default: the last available bar).

    Returns a DataFrame indexed by ticker. Only rows with ``>= cfg.min_history``
    closes are kept. Pure / leak-free: only data with index ``<= asof`` is read, so
    recompute-on-truncated == full-history.
    """
    if asof is not None:
        closes = closes.loc[:asof]
        if volumes is not None:
            volumes = volumes.loc[:asof]
    if closes.empty:
        return pd.DataFrame()

    # --- price derivatives (whole-panel, then take the asof row) ---
    az = accel_z_panel(closes, cfg).iloc[-1]
    velp = velocity_pct_panel(closes, cfg).iloc[-1]
    imp = velocity.impulse(closes, fast=cfg.macd_fast, slow=cfg.macd_slow, sig=cfg.macd_sig,
                           er_n=cfg.er_n, z_win=cfg.z_win).iloc[-1]
    eff = velocity.efficiency_ratio(closes, cfg.er_n).iloc[-1]
    trend = indicators.slope_z(closes, cfg.trend_slope_w, cfg.trend_base_w, use_log=True).iloc[-1]
    dsi = days_since_ignition(closes, cfg)

    last = closes.iloc[-1]
    ma_s = closes.rolling(cfg.ma_short, min_periods=cfg.ma_short // 2).mean().iloc[-1]
    ma_l = closes.rolling(cfg.ma_long, min_periods=cfg.ma_long // 2).mean().iloc[-1]
    hi = closes.rolling(cfg.high_win, min_periods=cfg.high_win // 4).max().iloc[-1]
    pctile = indicators.pct_rank_window(closes, cfg.high_win).iloc[-1]

    def _ret(n: int) -> pd.Series:
        if len(closes) <= n:
            return pd.Series(np.nan, index=closes.columns)
        return last / closes.iloc[-1 - n] - 1.0

    feat = pd.DataFrame({
        "price": last,
        "accel_z": az,
        "impulse_macd": imp,
        "vel_pct": velp,
        "eff_ratio": eff,
        "trend_vel": trend,
        "ret_1d": _ret(1),
        "runup_5": _ret(5),
        "runup_20": _ret(20),
        "dist_50": last / ma_s - 1.0,
        "dist_200": last / ma_l - 1.0,
        "off_high": last / hi - 1.0,
        "range_pctile": pctile,
        "days_igniting": dsi,
    })

    # --- volume features (shallow panel; align to the priced names) ---
    if volumes is not None and not volumes.empty:
        vol = volumes.reindex(columns=closes.columns)
        vlast = vol.iloc[-1]
        vmed = vol.rolling(cfg.rvol_win, min_periods=max(3, cfg.rvol_win // 2)).median().iloc[-1]
        vfast = vol.rolling(cfg.vol_vel_fast, min_periods=cfg.vol_vel_fast).mean().iloc[-1]
        vslow = vol.rolling(cfg.vol_vel_slow, min_periods=max(3, cfg.vol_vel_slow // 2)).mean().iloc[-1]
        feat["rvol"] = vlast / vmed.replace(0, np.nan)
        feat["vol_vel"] = vfast / vslow.replace(0, np.nan)
        feat["dollar_vol"] = last * vlast
        # 20d average dollar volume = the liquidity floor
        dvol = (closes * vol).rolling(cfg.vol_vel_slow, min_periods=max(3, cfg.vol_vel_slow // 2)).mean().iloc[-1]
        feat["adv20"] = dvol
    else:
        for c in ("rvol", "vol_vel", "dollar_vol", "adv20"):
            feat[c] = np.nan

    # need enough history to have meaningful derivatives
    enough = closes.notna().sum() >= cfg.min_history
    feat = feat[enough.reindex(feat.index, fill_value=False)]
    # drop names with no usable price impulse at all (all-NaN row of the core legs)
    core = feat[["accel_z", "impulse_macd", "trend_vel"]]
    feat = feat[core.notna().any(axis=1)]
    return feat


def classify(feat: pd.DataFrame, cfg: ImpulseConfig = ImpulseConfig()) -> pd.Series:
    """Vectorised state for each row of ``compute_features`` output.

    Order matters (first match wins): FADING → EXTENDED_RUN → EARLY_IGNITION →
    IGNITING → COILING → NEUTRAL.
    """
    az = feat["accel_z"]
    imp = feat["impulse_macd"]
    trend = feat["trend_vel"]
    runup = feat["runup_20"]
    ext = feat["dist_50"]
    ext_l = feat["dist_200"]
    vv = feat.get("vol_vel")
    rv = feat.get("rvol")

    accel_up = (az > cfg.accel_early_z) & (imp > 0)
    vol_ok = pd.Series(True, index=feat.index)
    if vv is not None:
        confirm = (vv > cfg.vol_confirm)
        if rv is not None:
            confirm = confirm | (rv > cfg.rvol_confirm)
        # absent volume data → don't block (NaN treated as "unknown", allowed)
        vol_ok = confirm | vv.isna()
    extended = (runup >= cfg.runup_extended) | (ext >= cfg.ext50_extended) | (ext_l >= cfg.ext200_extended)
    fresh = runup < cfg.runup_early_max
    downtrend = trend < cfg.trend_hard_down
    fading = ((az < -cfg.accel_early_z) & (imp < 0)) | (downtrend & (imp < 0))

    coiling = pd.Series(False, index=feat.index)
    if vv is not None:
        coiling = (runup.abs() < cfg.coil_runup_max) & (vv > cfg.coil_vol_min) & ~accel_up & ~downtrend

    out = pd.Series(NEUTRAL, index=feat.index)
    out[coiling] = COILING
    igniting = accel_up & ~downtrend
    out[igniting] = IGNITING
    out[igniting & extended] = EXTENDED_RUN
    out[igniting & ~extended & fresh & vol_ok] = EARLY_IGNITION
    out[fading] = FADING
    return out


def score_panel(closes: pd.DataFrame, volumes: pd.DataFrame | None = None, *,
                asof: pd.Timestamp | None = None,
                cfg: ImpulseConfig = ImpulseConfig()) -> pd.DataFrame:
    """Full pipeline → one ranked row per ticker.

    Adds, on top of ``compute_features``:
      • ``raw`` — the transparent early-ignition composite (rewards acceleration +
        volume confirmation + move-cleanliness; SUBTRACTS an extension penalty so a
        name that already ran can never out-rank a fresh one).
      • ``impulse_score`` — 0-100 cross-sectional percentile of ``raw`` (display skin).
      • ``state`` / ``just_starting`` — the lane.
      • ``liquid`` — passes the dollar-volume floor.

    Sorted by ``impulse_score`` descending. No learned weights (forecast-combination
    discipline); the weights are fixed and legible.
    """
    feat = compute_features(closes, volumes, asof=asof, cfg=cfg)
    if feat.empty:
        return feat

    z_acc = _winsor_z(feat["accel_z"])
    z_imp = _winsor_z(feat["impulse_macd"])
    z_vv = _winsor_z(feat["vol_vel"]) if feat["vol_vel"].notna().any() else feat["accel_z"] * 0.0
    z_rv = _winsor_z(feat["rvol"]) if feat["rvol"].notna().any() else feat["accel_z"] * 0.0

    # reward: acceleration (price) + volume waking up, weighted toward the price legs.
    raw = 0.40 * z_acc + 0.30 * z_imp + 0.20 * z_vv.fillna(0.0) + 0.10 * z_rv.fillna(0.0)
    # cleanliness multiplier — a clean directional move counts more than chop.
    raw = raw * (0.5 + 0.5 * feat["eff_ratio"].clip(0, 1).fillna(0.0))
    # extension penalty (subtract-only): the further a name has already run, the more
    # it is demoted — this is what keeps the BUY lane to names still offering an entry.
    ext_pen = (
        (feat["dist_50"] - cfg.ext50_extended).clip(lower=0) * 4.0
        + (feat["runup_20"] - cfg.runup_early_max).clip(lower=0) * 5.0
        + (feat["dist_200"] - cfg.ext200_extended).clip(lower=0) * 2.0
    ).fillna(0.0)
    raw = raw - ext_pen

    feat["raw"] = raw
    feat["impulse_score"] = (raw.rank(pct=True) * 100.0).round(0)
    feat["state"] = classify(feat, cfg)
    feat["just_starting"] = feat["state"] == EARLY_IGNITION
    feat["liquid"] = feat["adv20"].fillna(0.0) >= cfg.min_dollar_vol
    return feat.sort_values("impulse_score", ascending=False)
