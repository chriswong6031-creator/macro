"""Leadership Crack — DISPLAY-ONLY organ (RSR-R2/R4).

Watches the AI-hardware leadership cohort (ai_semiconductors + ai_infra +
memory_storage + semicap_equipment) for three signs of a cracking leadership:

  LEG-1  VELOCITY: 5-day excess return of the cohort vs SPY, z-scored against
         trailing 120-day history. A large negative z-vel means the cohort is
         falling much faster than the index — leadership is selling into the tape.

  LEG-2  CARNAGE: share of names that are >=20% off their 63-day rolling high.
         When many names are deeply broken (not just slightly off), that is
         structural damage, not a rotation.

STATE MACHINE (hysteresis — never a single-day flip):
  INTACT   : z_vel > -1.5 AND med_dd > -0.12
  CRACKING : z_vel <= -1.5 OR (med_dd <= -0.12 AND carnage_share_ema >= 0.40)
  BROKEN   : med_dd <= -0.20 AND carnage_share_ema >= 0.60
             (stays BROKEN until med_dd > -0.12 for 3 consecutive sessions)

dislocation flag fires when CRACKING or BROKEN AND SPY is within -3% of its 63d max.

DISPLAY-ONLY: writes data/leadership_crack/latest.json every run;
appends data/leadership_crack/forward_log.jsonl ONLY on the nightly lane.
Never raises into the build (degrade-never-raise).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

COHORT_KEYS = ["ai_semiconductors", "ai_infra", "memory_storage", "semicap_equipment"]
SCHEMA = "leadership_crack.v1"

# freshness gate: max sessions a member may lag behind the panel's most recent date
_FRESHNESS_LAG_SESSIONS = 3
# drawdown thresholds for carnage buckets
_DD_10 = -0.10
_DD_20 = -0.20
_DD_30 = -0.30
# state machine thresholds
_CRACK_Z_VEL = -1.5
_CRACK_MED_DD = -0.12
_CRACK_CARNAGE = 0.40
_BROKEN_MED_DD = -0.20
_BROKEN_CARNAGE = 0.60
_BROKEN_HEAL_MED_DD = -0.12   # must clear this for 3 sessions to exit BROKEN
_BROKEN_HEAL_SESSIONS = 3
# ffill cap
_FFILL_DAYS = 3
# velocity z-score params
_VEL_DAYS = 5
_VEL_WINDOW = 120
_VEL_MIN_PERIODS = 60
# rolling high window for carnage
_CARNAGE_WINDOW = 63
# EMA span for carnage_share smoothing
_CARNAGE_EMA_SPAN = 3
# SPY proximity for dislocation
_DISLO_SPY_PROX = 0.97   # within 3% of 63d max
_SPY_ROLL_WIN = 63
# worst members to surface
_WORST_N = 6


def _data_dir() -> Path:
    return config.data_dir()


def _membership_path() -> Path:
    return _data_dir() / "baskets" / "membership.json"


def _ohlcv_path(ticker: str) -> Path:
    return _data_dir() / "baskets" / "ohlcv" / f"{ticker}.parquet"


def _spy_path() -> Path:
    return _data_dir() / "yahoo" / "SPY.parquet"


def _out_dir() -> Path:
    d = _data_dir() / "leadership_crack"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _live_members() -> list[str]:
    """Union of live members from the four cohort baskets, in order, de-duped."""
    try:
        raw = json.loads(_membership_path().read_text())
        baskets = raw.get("baskets", raw)
    except Exception as e:  # noqa: BLE001
        log.warning("leadership_crack: membership load failed (%s)", e)
        return []
    seen: set[str] = set()
    out: list[str] = []
    for key in COHORT_KEYS:
        for m in (baskets.get(key) or {}).get("members") or []:
            t = m.get("ticker")
            if t and m.get("removed") is None and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def _load_closes(tickers: list[str]) -> pd.DataFrame:
    """Load close series for each ticker, ffill <=3 days, drop sparse names."""
    cols: dict[str, pd.Series] = {}
    for t in tickers:
        p = _ohlcv_path(t)
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns:
                continue
            s = df["close"].dropna()
            if s.empty:
                continue
            cols[t] = s
        except Exception as e:  # noqa: BLE001
            log.debug("leadership_crack: load failed %s (%s)", t, e)
    if not cols:
        return pd.DataFrame()
    mat = pd.DataFrame(cols).sort_index()
    mat = mat.ffill(limit=_FFILL_DAYS)
    return mat


def _load_spy() -> pd.Series | None:
    """SPY close series from data/yahoo/SPY.parquet."""
    try:
        df = pd.read_parquet(_spy_path())
        col = "close" if "close" in df.columns else "close_price"
        s = df[col].dropna()
        return s.sort_index() if not s.empty else None
    except Exception as e:  # noqa: BLE001
        log.warning("leadership_crack: SPY load failed (%s)", e)
        return None


def _fresh_members(mat: pd.DataFrame) -> pd.DataFrame:
    """Keep only members whose last observation is within _FRESHNESS_LAG_SESSIONS
    of the panel max date.  Returns subset dataframe."""
    if mat.empty:
        return mat
    panel_max = mat.index.max()
    # compute last valid date per column
    last_valid = mat.apply(lambda s: s.dropna().index.max() if s.dropna().shape[0] else pd.NaT)
    # count business days between last_valid and panel_max
    def _lag(d):
        if pd.isna(d):
            return 9999
        return max(0, len(pd.bdate_range(d, panel_max)) - 1)
    keep = [c for c in mat.columns if _lag(last_valid[c]) <= _FRESHNESS_LAG_SESSIONS]
    return mat[keep]


def _velocity_z(r_cohort: pd.Series, r_spy: pd.Series) -> pd.Series:
    """Causal z-scored 5d excess return (shift before stats windows apply).
    Strictly causal: shift(1) before computing mean/std so today's value does
    not enter its own normalisation denominator."""
    ex5 = r_cohort.rolling(_VEL_DAYS, min_periods=_VEL_DAYS).sum() - \
          r_spy.rolling(_VEL_DAYS, min_periods=_VEL_DAYS).sum()
    mu = ex5.shift(1).rolling(_VEL_WINDOW, min_periods=_VEL_MIN_PERIODS).mean()
    sd = ex5.shift(1).rolling(_VEL_WINDOW, min_periods=_VEL_MIN_PERIODS).std()
    return (ex5 - mu) / sd.replace(0, np.nan)


def _compute(mat_fresh: pd.DataFrame, spy: pd.Series | None) -> dict[str, Any]:
    """Core computation.  mat_fresh is already freshness-filtered."""
    n_fresh = mat_fresh.shape[1]

    # Align SPY to same index
    if spy is not None:
        spy_aligned = spy.reindex(mat_fresh.index)
    else:
        spy_aligned = pd.Series(np.nan, index=mat_fresh.index)

    # Member daily returns
    rets = mat_fresh.pct_change(fill_method=None)
    r_cohort = rets.mean(axis=1)

    # SPY daily returns
    spy_ret = spy_aligned.pct_change(fill_method=None)

    # LEG-1: velocity z-score
    z_series = _velocity_z(r_cohort, spy_ret)

    # LEG-2: carnage
    roll_max = mat_fresh.rolling(_CARNAGE_WINDOW, min_periods=_CARNAGE_WINDOW).max()
    dd = (mat_fresh / roll_max) - 1.0  # negative drawdown per member
    med_dd_series = dd.median(axis=1)

    share10 = (dd <= _DD_10).sum(axis=1) / n_fresh
    share20 = (dd <= _DD_20).sum(axis=1) / n_fresh
    share30 = (dd <= _DD_30).sum(axis=1) / n_fresh
    # smooth carnage_share with 3d EMA
    carnage_ema = share20.ewm(span=_CARNAGE_EMA_SPAN, min_periods=1).mean()

    # SPY: proximity to 63d high (for dislocation flag)
    spy_roll_max = spy_aligned.rolling(_SPY_ROLL_WIN, min_periods=1).max()
    spy_prox = spy_aligned / spy_roll_max.replace(0, np.nan)

    # SPY drawdown from its own 252d high (index_dd)
    spy_max252 = spy_aligned.rolling(252, min_periods=63).max()
    spy_dd_series = (spy_aligned / spy_max252.replace(0, np.nan)) - 1.0

    return {
        "z_series": z_series,
        "med_dd_series": med_dd_series,
        "carnage_ema": carnage_ema,
        "share10": share10,
        "share20": share20,
        "share30": share30,
        "spy_prox": spy_prox,
        "spy_dd_series": spy_dd_series,
        "dd": dd,   # per-member drawdowns (latest row)
    }


def _state_machine(z_series: pd.Series,
                   med_dd_series: pd.Series,
                   carnage_ema: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Apply hysteresis state machine row by row.
    Returns (state_series, state_since_series) where:
      state_series:  str per date  ("INTACT"|"CRACKING"|"BROKEN")
      state_since_series: Timestamp (first date this state was entered)
    """
    states: list[str] = []
    sinces: list[pd.Timestamp] = []
    idx = z_series.index

    cur_state = "INTACT"
    cur_since = idx[0] if len(idx) else pd.NaT
    broken_heal_count = 0  # consecutive sessions med_dd > -0.12 while in BROKEN

    for i, date in enumerate(idx):
        z = z_series.iloc[i]
        md = med_dd_series.iloc[i]
        ce = carnage_ema.iloc[i]

        # NaN values: stay in current state but don't transition
        if pd.isna(z) or pd.isna(md) or pd.isna(ce):
            states.append(cur_state)
            sinces.append(cur_since)
            continue

        if cur_state == "BROKEN":
            # Exit BROKEN only when med_dd > heal threshold for 3 consecutive sessions
            if md > _BROKEN_HEAL_MED_DD:
                broken_heal_count += 1
                if broken_heal_count >= _BROKEN_HEAL_SESSIONS:
                    cur_state = "INTACT"
                    cur_since = date
                    broken_heal_count = 0
            else:
                broken_heal_count = 0
            # Can remain BROKEN even while counting heal sessions
        elif cur_state == "CRACKING":
            # Upgrade to BROKEN
            if md <= _BROKEN_MED_DD and ce >= _BROKEN_CARNAGE:
                cur_state = "BROKEN"
                cur_since = date
                broken_heal_count = 0
            # Return to INTACT
            elif z > _CRACK_Z_VEL and md > _CRACK_MED_DD:
                cur_state = "INTACT"
                cur_since = date
        else:  # INTACT
            # Enter BROKEN directly (fast path)
            if md <= _BROKEN_MED_DD and ce >= _BROKEN_CARNAGE:
                cur_state = "BROKEN"
                cur_since = date
                broken_heal_count = 0
            # Enter CRACKING
            elif z <= _CRACK_Z_VEL or (md <= _CRACK_MED_DD and ce >= _CRACK_CARNAGE):
                cur_state = "CRACKING"
                cur_since = date

        states.append(cur_state)
        sinces.append(cur_since)

    return pd.Series(states, index=idx), pd.Series(sinces, index=idx)


def build() -> dict | None:
    """Compute leadership_crack snapshot, write latest.json, conditionally append
    forward_log.jsonl.  Returns the snapshot dict or None on failure."""
    try:
        return _build()
    except Exception as e:  # noqa: BLE001
        log.warning("leadership_crack: build failed (%s)", e, exc_info=True)
        return None


def _build() -> dict | None:
    members = _live_members()
    n_total = len(members)
    if not members:
        log.warning("leadership_crack: no live members found")
        return None

    mat_all = _load_closes(members)
    if mat_all.empty:
        log.warning("leadership_crack: no close data loaded")
        return None

    mat_fresh = _fresh_members(mat_all)
    n_fresh = mat_fresh.shape[1]
    if n_fresh < 3:
        log.warning("leadership_crack: too few fresh members (%d)", n_fresh)
        return None

    spy = _load_spy()

    computed = _compute(mat_fresh, spy)
    z_s = computed["z_series"]
    md_s = computed["med_dd_series"]
    ce_s = computed["carnage_ema"]

    state_s, since_s = _state_machine(z_s, md_s, ce_s)

    # Snapshot on the last row with valid data
    # Use the last date where all series have values
    valid_idx = z_s.dropna().index.intersection(md_s.dropna().index) \
                              .intersection(ce_s.dropna().index)
    if valid_idx.empty:
        log.warning("leadership_crack: no valid rows in computed series")
        return None

    asof = valid_idx[-1]
    state = state_s.loc[asof]
    state_since = since_s.loc[asof]

    z_vel = float(z_s.loc[asof]) if not pd.isna(z_s.loc[asof]) else None
    med_dd = float(md_s.loc[asof]) if not pd.isna(md_s.loc[asof]) else None
    carnage_share_ema = float(ce_s.loc[asof]) if not pd.isna(ce_s.loc[asof]) else None

    share10 = float(computed["share10"].loc[asof]) if asof in computed["share10"].index else None
    share30 = float(computed["share30"].loc[asof]) if asof in computed["share30"].index else None

    # SPY index_dd
    spy_dd_val = None
    if spy is not None:
        spy_dd_s = computed["spy_dd_series"]
        if asof in spy_dd_s.index and not pd.isna(spy_dd_s.loc[asof]):
            spy_dd_val = float(spy_dd_s.loc[asof])

    # dislocation: CRACKING or BROKEN AND SPY within 3% of 63d max
    spy_prox_val = None
    if spy is not None and asof in computed["spy_prox"].index:
        v = computed["spy_prox"].loc[asof]
        if not pd.isna(v):
            spy_prox_val = float(v)
    dislocation = (state in {"CRACKING", "BROKEN"}) and (
        spy_prox_val is not None and spy_prox_val >= _DISLO_SPY_PROX
    )

    # Worst 6 members by dd at asof
    dd_row = computed["dd"].loc[asof].dropna().sort_values()
    worst = [{"ticker": t, "dd": round(float(v), 4)}
             for t, v in dd_row.head(_WORST_N).items()]

    snap: dict[str, Any] = {
        "schema": SCHEMA,
        "asof": str(asof.date()),
        "state": state,
        "z_vel": round(z_vel, 4) if z_vel is not None else None,
        "med_dd": round(med_dd, 4) if med_dd is not None else None,
        "carnage_share_ema": round(carnage_share_ema, 4) if carnage_share_ema is not None else None,
        "share10": round(share10, 4) if share10 is not None else None,
        "share30": round(share30, 4) if share30 is not None else None,
        "n_fresh": n_fresh,
        "n_total": n_total,
        "worst_members": worst,
        "index_dd": round(spy_dd_val, 4) if spy_dd_val is not None else None,
        "dislocation": bool(dislocation),
        "state_since": str(state_since.date()) if pd.notna(state_since) else None,
    }

    # Write latest.json always
    out_dir = _out_dir()
    latest_path = out_dir / "latest.json"
    try:
        latest_path.write_text(json.dumps(snap, default=str), encoding="utf-8")
        log.info("leadership_crack: wrote %s", latest_path)
    except Exception as e:  # noqa: BLE001
        log.warning("leadership_crack: latest.json write failed (%s)", e)

    # Append forward_log.jsonl ONLY when nightly lane is armed (idempotent by asof)
    try:
        from engine.risk_radar_intl_audit import ledger_lane_armed
        if ledger_lane_armed():
            import datetime as _dt
            fwd_path = out_dir / "forward_log.jsonl"
            # Read existing rows; skip append if this asof already recorded
            existing: list[dict] = []
            if fwd_path.exists():
                for line in fwd_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        try:
                            existing.append(json.loads(line))
                        except Exception:  # noqa: BLE001
                            pass
            asof_str = str(snap.get("asof", ""))
            if any(r.get("asof") == asof_str for r in existing):
                log.debug("leadership_crack: asof %s already in forward_log, skipping", asof_str)
            else:
                row = dict(snap)
                row["logged_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
                with open(fwd_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, default=str) + "\n")
                log.info("leadership_crack: appended to %s", fwd_path)
    except Exception as e:  # noqa: BLE001
        log.warning("leadership_crack: forward_log append failed (%s)", e)

    return snap
