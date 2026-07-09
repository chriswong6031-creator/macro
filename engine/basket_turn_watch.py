"""basket_turn_watch — EOD K-of-N confluence organ per US basket (FTR W4).

Clones the engine/hk_washout_watch.py pattern (six organs, ledger, display-only,
exit-0). Detects whether enough independent legs agree that a basket is showing
turn-watch / ignition conditions.

DOCTRINE
--------
- DISPLAY-ONLY / CONTEXT.  Authority block: tier=display, horizon_role=context,
  may_rank/gate/size/escalate = false.
- DISCLOSURE: sector-level standalone washout→turn triggers printed NULL
  (Oracle P8 P-W1/S-W3; DO_NOT_REBUILD §2 "Washout × turn"). This organ is a
  *different construction* (multi-leg confluence, basket granularity) shipped
  display-tier as an expected-NULL forward meter (FT-R9). Not a revival claim.
- FT-R3: shock_relative_bid is a binary present/absent confluence flag —
  no ranking, no beneficiary / casualty / shelter / front_run / buy / direction
  fields anywhere.
- Forward ledger starts at ship date; no backfilled gradeable claims (FT-R9).
  Backscan = site-artifact descriptive only.
- Nightly writer: the US_LANE gate in stamp_ledger() ensures only the nightly
  lane writes to data/ (house law: nightly is the sole advancer of data/ ledgers).
- Idempotent re-runs: keep-first per (date, basket_id).
- 2-session hysteresis on state downgrade (TI-R3 shape).

SIX LEGS v1 (FROZEN per FT-R9)
--------------------------------
1. impulse_day      ≥1/3 of active members with day return ≥ +3%  (floor: 2 members)
2. rs_z             basket EW 1d return vs SPY, z-scored cross-sectionally ≥ +2
3. breadth_surge    z of today's Δpct50 (Δfraction above 50d MA) vs trailing 60-session
                    Δpct50 distribution ≥ 2, AND ≥2 members crossed today
4. volume_confirm   basket EW dollar-volume ≥ 1.5× its 20d median
5. complex_confirm  ≥2 sibling baskets in the same theme-complex with positive 1d rs z
6. shock_relative_bid BINARY flag — market_drivers primary ∈ {oil_shock, geopolitical}
                    AND SPY down AND this basket's 1d rs z > 0

STATES
------
WATCH    K ≥ 2
IGNITION K ≥ 3 AND rs_z leg is true
+ 2-session hysteresis before state downgrade

FORBIDDEN FIELD NAMES
---------------------
beneficiary, casualty, shelter, front_run, buy, direction
(CI-checked by tests/test_basket_turn_watch.py)
"""
from __future__ import annotations

import json
import logging
import os
import statistics
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (invariant — matches synapse registration)
# ---------------------------------------------------------------------------

AUTHORITY = {
    "tier": "display",
    "horizon_role": "context",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

DISCLOSURE = (
    "Sector-level standalone washout-to-turn triggers printed NULL "
    "(Oracle P8 P-W1/S-W3); this confluence construction accrues as an "
    "expected-null forward meter — display only."
)

# ---------------------------------------------------------------------------
# Leg thresholds (v1 — FROZEN per FT-R9 / PS-R9)
# ---------------------------------------------------------------------------

# Leg 1: impulse_day
IMPULSE_FRACTION = 1 / 3      # at least 1/3 of active members
IMPULSE_MIN_MEMBERS = 2       # floor: at least this many must fire
IMPULSE_THRESHOLD = 0.03      # +3% day return

# Leg 2: rs_z
RS_Z_THRESHOLD = 2.0          # cross-sectional z of 1d EW return vs SPY ≥ +2

# Leg 3: breadth_surge
BREADTH_Z_THRESHOLD = 2.0     # z of Δpct50 vs trailing 60-session distribution
BREADTH_MIN_CROSSINGS = 2     # at least 2 members crossed above 50d MA today
BREADTH_LOOKBACK = 60         # sessions for Δpct50 trailing distribution

# Leg 4: volume_confirm
VOLUME_MULTIPLIER = 1.5       # basket EW dollar-vol ≥ 1.5× 20d median
VOLUME_MEDIAN_DAYS = 20

# Leg 5: complex_confirm
COMPLEX_SIBLING_MINIMUM = 2   # ≥2 sibling baskets in the same complex with positive rs_z

# Leg 6: shock_relative_bid (binary gate)
_SHOCK_PRIMARY_KEYS: frozenset[str] = frozenset({"oil_shock"})
_SHOCK_FAMILIES: frozenset[str] = frozenset({"geopolitical"})

# State thresholds
STATE_WATCH_K = 2
STATE_IGNITION_K = 3

# Hysteresis: sessions before state downgrade
HYSTERESIS_SESSIONS = 2

# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

_LEDGER_DIR = "basket_turn"
_LEDGER_FILE = "ledger.jsonl"


def _ledger_advance_enabled() -> bool:
    """True only when running in the nightly US lane (US_LANE=nightly)."""
    return os.environ.get("US_LANE", "").lower() == "nightly"


def _ledger_path(data_root: Path | None = None) -> Path:
    from lib import config
    root = data_root if data_root is not None else config.data_dir()
    return root / _LEDGER_DIR / _LEDGER_FILE


def load_ledger(data_root: Path | None = None) -> list[dict]:
    """Load all ledger rows. Returns [] if file missing/corrupt."""
    p = _ledger_path(data_root)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _write_ledger(rows: list[dict], data_root: Path | None = None) -> None:
    """Write ledger atomically via temp-file + os.replace (mirror hk_washout pattern)."""
    p = _ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(r, default=str) for r in rows)
    if content:
        content += "\n"
    fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=".basket_turn_ledger_tmp_")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
        os.replace(tmp_path, p)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def stamp_ledger(
    watch_rows: list[dict],
    as_of: str | None = None,
    data_root: Path | None = None,
) -> int:
    """Append rows for baskets in WATCH/IGNITION (plus downgrades).

    Idempotent: keep-first per (date, basket_id). Gated by US_LANE=nightly.
    Returns count of appended rows.
    """
    if not _ledger_advance_enabled():
        log.debug("basket_turn_watch.stamp_ledger: skipped (US_LANE != nightly)")
        return 0
    if not watch_rows:
        return 0
    today_str = as_of or date.today().isoformat()
    try:
        rows = load_ledger(data_root)
        existing = {(r.get("basket_id"), r.get("date")) for r in rows}
        appended = 0
        for w in watch_rows:
            key = (w.get("basket_id"), today_str)
            if key in existing:
                continue
            rows.append({
                "date":         today_str,
                "basket_id":    w.get("basket_id"),
                "state":        w.get("state"),
                "k":            w.get("k"),
                "legs":         w.get("legs", {}),
                "as_of":        today_str,
                # Forward outcome fields — blank at fire time, graded forward
                "fwd_21d_ew_vs_spy": None,
                "graded_at":    None,
            })
            existing.add(key)
            appended += 1
        if appended:
            _write_ledger(rows, data_root)
        return appended
    except Exception as e:  # noqa: BLE001
        log.warning("basket_turn_watch.stamp_ledger failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# Price-store helpers
# ---------------------------------------------------------------------------

def _load_prices(ticker: str, data_root: Path | None = None) -> pd.DataFrame | None:
    """Load price parquet for a single ticker from data/stocks/.

    Returns a DataFrame with columns [close, high, low, volume] indexed by Date,
    or None if unavailable.
    """
    from lib import config
    root = data_root if data_root is not None else config.data_dir()
    p = root / "stocks" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:  # noqa: BLE001
        log.debug("_load_prices(%s): %s", ticker, e)
        return None


def _spy_prices(data_root: Path | None = None) -> pd.Series | None:
    """Return SPY close series."""
    df = _load_prices("SPY", data_root)
    if df is None:
        return None
    return df["close"].astype(float)


# ---------------------------------------------------------------------------
# Membership helpers
# ---------------------------------------------------------------------------

def _active_tickers(basket: dict) -> list[str]:
    """Return currently active (non-removed) member tickers."""
    return [
        m["ticker"]
        for m in (basket.get("members") or [])
        if m.get("removed") is None and m.get("ticker")
    ]


# ---------------------------------------------------------------------------
# AI-capex complex membership (engine/demand_capex.AI_CAPEX_THEMES keys)
# ---------------------------------------------------------------------------

def _ai_capex_basket_ids() -> frozenset[str]:
    """Return basket ids belonging to the AI-capex complex.

    Uses engine.demand_capex.AI_CAPEX_THEMES keys directly (FT-R10: FTR creates
    no new theme vocabulary). The keys ARE the basket ids.
    """
    try:
        from engine.demand_capex import AI_CAPEX_THEMES
        return frozenset(AI_CAPEX_THEMES.keys())
    except Exception as e:  # noqa: BLE001
        log.warning("basket_turn_watch: AI_CAPEX_THEMES import failed: %s", e)
        return frozenset()


def _theme_sibling_map(baskets_meta: dict) -> dict[str, frozenset[str]]:
    """Build a map of basket_id -> set of sibling basket ids sharing the same
    crosswalk theme or ai_capex complex.

    For the ai_capex complex: sibling set = AI_CAPEX_THEMES keys.
    For all other baskets: sibling set = baskets sharing the same crosswalk
    theme-id (config/theme_crosswalk.yml) EXCLUDING the basket itself.
    """
    ai_capex_ids = _ai_capex_basket_ids()

    # Load crosswalk theme membership
    crosswalk_themes: dict[str, str] = {}  # basket_id -> theme_id
    try:
        from lib import config
        cw_path = config.ROOT / "config" / "theme_crosswalk.yml"
        if cw_path.exists():
            import yaml
            with cw_path.open(encoding="utf-8") as fh:
                cw = yaml.safe_load(fh)
            for t in (cw.get("themes") or []):
                tid = t.get("id") or t.get("foresight_id")
                if not tid:
                    continue
                # Theme id may be a basket id directly (crosswalk uses basket ids as theme ids)
                # Also check the 'baskets' sub-list if present
                for bid in (t.get("baskets") or []):
                    crosswalk_themes[bid] = tid
                # When theme id matches a basket id (TIL W0 pattern)
                if tid in baskets_meta:
                    crosswalk_themes.setdefault(tid, tid)
    except Exception as e:  # noqa: BLE001
        log.debug("basket_turn_watch: crosswalk load failed: %s", e)

    # Build sibling sets
    # Group baskets by theme_id
    theme_groups: dict[str, list[str]] = {}
    for bid in baskets_meta:
        if bid in ai_capex_ids:
            theme_groups.setdefault("_ai_capex", []).append(bid)
        elif bid in crosswalk_themes:
            tid = crosswalk_themes[bid]
            theme_groups.setdefault(tid, []).append(bid)

    sibling_map: dict[str, frozenset[str]] = {}
    for bid in baskets_meta:
        if bid in ai_capex_ids:
            siblings = frozenset(ai_capex_ids) - {bid}
        else:
            tid = crosswalk_themes.get(bid)
            if tid and tid in theme_groups:
                siblings = frozenset(theme_groups[tid]) - {bid}
            else:
                siblings = frozenset()
        sibling_map[bid] = siblings

    return sibling_map


# ---------------------------------------------------------------------------
# Per-basket leg computations
# ---------------------------------------------------------------------------

def _leg_impulse_day(
    tickers: list[str],
    closes_map: dict[str, pd.Series],
) -> bool:
    """Leg 1: ≥1/3 of active members with 1d return ≥ +3% (floor: 2 members)."""
    n = len(tickers)
    if n == 0:
        return False
    threshold = max(IMPULSE_FRACTION * n, IMPULSE_MIN_MEMBERS)
    count = 0
    for tk in tickers:
        s = closes_map.get(tk)
        if s is None or len(s) < 2:
            continue
        ret = float(s.iloc[-1]) / float(s.iloc[-2]) - 1.0
        if ret >= IMPULSE_THRESHOLD:
            count += 1
    return count >= threshold


def _basket_ew_1d_return(
    tickers: list[str],
    closes_map: dict[str, pd.Series],
) -> float | None:
    """Equal-weight 1d return for a basket. Returns None if insufficient data."""
    rets = []
    for tk in tickers:
        s = closes_map.get(tk)
        if s is None or len(s) < 2:
            continue
        prev = float(s.iloc[-2])
        if prev == 0:
            continue
        rets.append(float(s.iloc[-1]) / prev - 1.0)
    if not rets:
        return None
    return float(np.mean(rets))


def _leg_rs_z(
    basket_id: str,
    basket_ew_ret: float | None,
    all_basket_ew_rets: dict[str, float],
    spy_ret: float | None,
) -> tuple[bool, float | None]:
    """Leg 2: basket EW 1d return vs SPY, z-scored cross-sectionally ≥ +2.

    Returns (fired, z_value).
    Cross-sectional: excess returns = basket_ret - spy_ret for all US baskets.
    z = (this_basket_excess - mean_excess) / std_excess.
    """
    if basket_ew_ret is None or spy_ret is None:
        return False, None

    this_excess = basket_ew_ret - spy_ret
    all_excesses = []
    for bid, bret in all_basket_ew_rets.items():
        if bret is not None:
            all_excesses.append(bret - spy_ret)

    if len(all_excesses) < 3:
        return False, None

    mu = float(np.mean(all_excesses))
    sigma = float(np.std(all_excesses, ddof=1))
    if sigma < 1e-9:
        return False, None
    z = (this_excess - mu) / sigma
    return z >= RS_Z_THRESHOLD, round(z, 3)


def _leg_breadth_surge(
    tickers: list[str],
    closes_map: dict[str, pd.Series],
) -> bool:
    """Leg 3: z of today's Δpct50 vs trailing 60-session distribution ≥ 2, AND ≥2 crossings.

    pct50_t = fraction of members whose close > their 50d MA on day t.
    Δpct50_t = pct50_t - pct50_{t-1}.
    z = (Δpct50_today - mean(trailing_60)) / std(trailing_60).
    """
    # Build aligned close matrix
    frames = {tk: closes_map[tk] for tk in tickers if closes_map.get(tk) is not None and len(closes_map[tk]) >= 51}
    if len(frames) < 2:
        return False

    # Align on common dates
    combined = pd.DataFrame(frames)
    combined = combined.dropna(how="all")
    if len(combined) < BREADTH_LOOKBACK + 2:
        return False

    # pct50 per day: fraction of members where close > 50d MA
    def _pct50_series(df: pd.DataFrame) -> pd.Series:
        result = []
        idx = []
        for i in range(50, len(df)):
            window = df.iloc[i - 50: i + 1]
            ma50 = window.iloc[:-1].mean()
            today_close = window.iloc[-1]
            above = (today_close > ma50).sum()
            total = today_close.notna().sum()
            result.append(above / total if total > 0 else 0.0)
            idx.append(df.index[i])
        return pd.Series(result, index=idx)

    pct50 = _pct50_series(combined)
    if len(pct50) < BREADTH_LOOKBACK + 2:
        return False

    delta_pct50 = pct50.diff().dropna()
    if len(delta_pct50) < BREADTH_LOOKBACK + 1:
        return False

    today_delta = float(delta_pct50.iloc[-1])
    trailing = delta_pct50.iloc[-(BREADTH_LOOKBACK + 1):-1]
    if len(trailing) < 5:
        return False

    mu = float(trailing.mean())
    sigma = float(trailing.std(ddof=1))
    if sigma < 1e-9:
        return False
    z = (today_delta - mu) / sigma
    if z < BREADTH_Z_THRESHOLD:
        return False

    # Count crossings: members that moved above their 50d MA today
    crossings = 0
    for tk in tickers:
        s = closes_map.get(tk)
        if s is None or len(s) < 52:
            continue
        ma50_yesterday = float(s.iloc[-51:-1].mean())
        ma50_today = float(s.iloc[-50:].mean())
        prev_close = float(s.iloc[-2])
        today_close = float(s.iloc[-1])
        was_below = prev_close <= ma50_yesterday
        is_above = today_close > ma50_today
        if was_below and is_above:
            crossings += 1

    return crossings >= BREADTH_MIN_CROSSINGS


def _leg_volume_confirm(
    tickers: list[str],
    price_data: dict[str, pd.DataFrame],
) -> bool:
    """Leg 4: basket EW dollar-volume ≥ 1.5× its 20d median.

    Dollar-volume = close × volume per ticker. EW basket dollar-vol =
    mean of member dollar-vols. Median over the 20 sessions before today.
    """
    today_dvols = []
    median_dvols = []
    for tk in tickers:
        df = price_data.get(tk)
        if df is None or len(df) < VOLUME_MEDIAN_DAYS + 1:
            continue
        if "volume" not in df.columns:
            continue
        close = df["close"].astype(float)
        vol = df["volume"].astype(float)
        dvol = close * vol
        if dvol.iloc[-1] == 0 or pd.isna(dvol.iloc[-1]):
            continue
        today_dvols.append(float(dvol.iloc[-1]))
        trailing = dvol.iloc[-(VOLUME_MEDIAN_DAYS + 1):-1]
        trailing = trailing[trailing > 0].dropna()
        if len(trailing) < 5:
            continue
        median_dvols.append(float(trailing.median()))

    if not today_dvols or not median_dvols:
        return False

    ew_today = float(np.mean(today_dvols))
    ew_median = float(np.mean(median_dvols))
    if ew_median <= 0:
        return False
    return (ew_today / ew_median) >= VOLUME_MULTIPLIER


def _leg_complex_confirm(
    basket_id: str,
    sibling_ids: frozenset[str],
    all_basket_rs_z: dict[str, float | None],
) -> bool:
    """Leg 5: ≥2 sibling baskets in the same complex with positive 1d rs z."""
    positive_siblings = 0
    for sid in sibling_ids:
        z = all_basket_rs_z.get(sid)
        if z is not None and z > 0:
            positive_siblings += 1
    return positive_siblings >= COMPLEX_SIBLING_MINIMUM


def _leg_shock_relative_bid(
    rs_z: float | None,
    market_drivers: dict | None,
    spy_ret: float | None,
) -> bool:
    """Leg 6: binary flag — shock primary active AND SPY down AND rs_z > 0.

    BINARY presence/absence only (FT-R3). No ranking, no beneficiary fields.
    """
    if market_drivers is None or rs_z is None or spy_ret is None:
        return False
    primary = market_drivers.get("primary", "")
    family = market_drivers.get("family", "")
    if primary not in _SHOCK_PRIMARY_KEYS and family not in _SHOCK_FAMILIES:
        return False
    if spy_ret >= 0:
        return False
    return rs_z > 0


# ---------------------------------------------------------------------------
# Hysteresis helper
# ---------------------------------------------------------------------------

def _prior_state_for(basket_id: str, ledger_rows: list[dict]) -> str | None:
    """Return the most recent state for basket_id from the ledger."""
    for row in reversed(ledger_rows):
        if row.get("basket_id") == basket_id:
            return row.get("state")
    return None


def _days_since_last_state(basket_id: str, ledger_rows: list[dict], today_str: str) -> int:
    """Return sessions since the last ledger row for basket_id (0 if today, -1 if none)."""
    from lib import nyse_calendar
    for row in reversed(ledger_rows):
        if row.get("basket_id") == basket_id:
            try:
                last_date = date.fromisoformat(row["date"])
                today_date = date.fromisoformat(today_str)
                # Count trading sessions between last_date and today_date
                sessions = 0
                d = last_date
                while d < today_date:
                    from datetime import timedelta
                    d += timedelta(days=1)
                    try:
                        if nyse_calendar.is_session(d):
                            sessions += 1
                    except Exception:
                        if d.weekday() < 5:
                            sessions += 1
                return sessions
            except Exception:
                return -1
    return -1


# ---------------------------------------------------------------------------
# Backscan computation
# ---------------------------------------------------------------------------

def _backscan(
    baskets_meta: dict,
    closes_map: dict[str, pd.Series],
    price_data: dict[str, pd.DataFrame],
    spy_closes: pd.Series,
    market_drivers: dict | None,
    n_sessions: int = 250,
) -> dict:
    """Compute would-have-fired statistics over the last n_sessions.

    Returns a descriptive dict embedded in the site artifact.
    FT-R9: descriptive only; forward ledger starts at ship date.
    """
    # We'll compute a simplified backscan: iterate recent sessions,
    # compute legs for each basket, count fires.
    try:
        spy_rets_full = spy_closes.pct_change()
        # Limit to last n_sessions
        if len(spy_closes) < n_sessions + 1:
            n_sessions = len(spy_closes) - 1

        watch_fires: int = 0
        ignition_fires: int = 0
        leg_fires: dict[str, int] = {
            "impulse_day": 0,
            "rs_z": 0,
            "breadth_surge": 0,
            "volume_confirm": 0,
            "complex_confirm": 0,
            "shock_relative_bid": 0,
        }
        total_basket_days: int = 0

        # Build sibling map once
        sibling_map = _theme_sibling_map(baskets_meta)
        ai_capex_ids = _ai_capex_basket_ids()

        # Iterate over the last n_sessions index positions
        all_dates = spy_closes.index
        if len(all_dates) < n_sessions + 1:
            return {"error": "insufficient history", "n_sessions": 0}

        start_idx = len(all_dates) - n_sessions - 1  # -1 to allow d-1 for prev

        for i in range(start_idx + 1, len(all_dates)):
            spy_ret_today: float | None = None
            spy_prev = float(spy_closes.iloc[i - 1])
            spy_today = float(spy_closes.iloc[i])
            if spy_prev != 0:
                spy_ret_today = spy_today / spy_prev - 1.0

            # Compute EW 1d returns per basket using closes up to index i
            all_ew_rets: dict[str, float] = {}
            for bid, basket in baskets_meta.items():
                tickers = _active_tickers(basket)
                rets = []
                for tk in tickers:
                    s = closes_map.get(tk)
                    if s is None or len(s) <= i:
                        continue
                    prev = float(s.iloc[i - 1])
                    if prev == 0:
                        continue
                    rets.append(float(s.iloc[i]) / prev - 1.0)
                if rets:
                    all_ew_rets[bid] = float(np.mean(rets))

            # Per-basket leg checks (simplified)
            all_rs_z: dict[str, float | None] = {}
            for bid, ew_ret in all_ew_rets.items():
                if spy_ret_today is None:
                    all_rs_z[bid] = None
                    continue
                this_excess = ew_ret - spy_ret_today
                excesses = [r - spy_ret_today for r in all_ew_rets.values()]
                if len(excesses) < 3:
                    all_rs_z[bid] = None
                    continue
                mu = float(np.mean(excesses))
                sigma = float(np.std(excesses, ddof=1))
                if sigma < 1e-9:
                    all_rs_z[bid] = None
                    continue
                all_rs_z[bid] = (this_excess - mu) / sigma

            for bid, basket in baskets_meta.items():
                tickers = _active_tickers(basket)
                if not tickers:
                    continue
                total_basket_days += 1

                ew_ret = all_ew_rets.get(bid)
                rs_z_val = all_rs_z.get(bid)

                # Impulse (simplified — using same-day slice)
                impulse = False
                if ew_ret is not None:
                    count_up = 0
                    for tk in tickers:
                        s = closes_map.get(tk)
                        if s is None or len(s) <= i:
                            continue
                        prev = float(s.iloc[i - 1])
                        if prev == 0:
                            continue
                        if float(s.iloc[i]) / prev - 1.0 >= IMPULSE_THRESHOLD:
                            count_up += 1
                    threshold = max(IMPULSE_FRACTION * len(tickers), IMPULSE_MIN_MEMBERS)
                    impulse = count_up >= threshold

                rs_z_fired = rs_z_val is not None and rs_z_val >= RS_Z_THRESHOLD
                shock_fired = _leg_shock_relative_bid(rs_z_val, market_drivers, spy_ret_today)

                k = sum([impulse, rs_z_fired, shock_fired])
                if impulse:
                    leg_fires["impulse_day"] += 1
                if rs_z_fired:
                    leg_fires["rs_z"] += 1
                if shock_fired:
                    leg_fires["shock_relative_bid"] += 1

                if k >= STATE_WATCH_K:
                    watch_fires += 1
                if k >= STATE_IGNITION_K and rs_z_fired:
                    ignition_fires += 1

        fire_rate_pct = round(watch_fires / total_basket_days * 100, 2) if total_basket_days > 0 else 0.0
        leg_rates = {
            name: round(cnt / total_basket_days * 100, 2) if total_basket_days > 0 else 0.0
            for name, cnt in leg_fires.items()
        }
        return {
            "description": (
                "Descriptive only — would-have-fired statistics over last "
                f"~{n_sessions} sessions. FT-R9: forward ledger starts at ship "
                "date; no backfilled gradeable claims."
            ),
            "n_sessions_approx": n_sessions,
            "total_basket_days": total_basket_days,
            "watch_fires": watch_fires,
            "ignition_fires": ignition_fires,
            "watch_fire_rate_pct": fire_rate_pct,
            "per_leg_fire_rates_pct": leg_rates,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("basket_turn_watch._backscan failed: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Market drivers loading
# ---------------------------------------------------------------------------

def _load_market_drivers(data_root: Path | None = None) -> dict | None:
    """Load market_drivers from data/regime/latest.json or site/live/market_drivers.json."""
    from lib import config
    root = data_root if data_root is not None else config.data_dir()

    # Primary: data/regime/latest.json (EOD, canonical)
    p = root / "regime" / "latest.json"
    if p.exists():
        try:
            d = json.loads(p.read_text())
            md = d.get("market_drivers")
            if md:
                return md
        except Exception:
            pass

    # Fallback: site/live/market_drivers.json
    site_dir = config.ROOT / config.load()["storage"]["site_dir"]
    p2 = site_dir / "live" / "market_drivers.json"
    if p2.exists():
        try:
            return json.loads(p2.read_text())
        except Exception:
            pass

    return None


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def compute(
    baskets_meta: dict | None = None,
    data_root: Path | None = None,
    as_of: str | None = None,
    run_backscan: bool = True,
) -> dict:
    """Compute the basket turn-watch organ for all US baskets.

    Parameters
    ----------
    baskets_meta :
        Baskets dict from data/baskets/membership.json["baskets"]. If None,
        loaded automatically.
    data_root :
        Override data root for testing.
    as_of :
        ISO date string (defaults to today).
    run_backscan :
        Whether to include the descriptive backscan block in the site artifact.

    Returns
    -------
    dict — full site artifact shape (baskets, backscan, authority, disclosure,
    as_of). Never raises.
    """
    try:
        return _compute_inner(baskets_meta, data_root, as_of, run_backscan)
    except Exception as e:  # noqa: BLE001
        log.error("basket_turn_watch.compute crashed (%s) — returning empty result", e)
        return {
            "schema": "basket_turn_watch.v1",
            "as_of": as_of or date.today().isoformat(),
            "baskets": [],
            "authority": AUTHORITY,
            "disclosure": DISCLOSURE,
            "error": str(e),
        }


def _compute_inner(
    baskets_meta: dict | None,
    data_root: Path | None,
    as_of: str | None,
    run_backscan: bool,
) -> dict:
    from lib import config

    if as_of is None:
        as_of = date.today().isoformat()

    # Load membership if not provided
    if baskets_meta is None:
        root = data_root if data_root is not None else config.data_dir()
        mp = root / "baskets" / "membership.json"
        if not mp.exists():
            log.warning("basket_turn_watch: membership.json not found")
            return {
                "schema": "basket_turn_watch.v1",
                "as_of": as_of,
                "baskets": [],
                "authority": AUTHORITY,
                "disclosure": DISCLOSURE,
            }
        raw = json.loads(mp.read_text())
        baskets_meta = raw.get("baskets") or {}

    if not baskets_meta:
        return {
            "schema": "basket_turn_watch.v1",
            "as_of": as_of,
            "baskets": [],
            "authority": AUTHORITY,
            "disclosure": DISCLOSURE,
        }

    # Filter to US baskets only (exclude cn_, hk_, ca_ prefixes)
    us_baskets = {
        bid: basket for bid, basket in baskets_meta.items()
        if not any(bid.startswith(p) for p in ("cn_", "hk_", "ca_"))
    }

    # Load price data for all members
    all_tickers: set[str] = {"SPY"}
    for basket in us_baskets.values():
        all_tickers.update(_active_tickers(basket))

    closes_map: dict[str, pd.Series] = {}
    price_data: dict[str, pd.DataFrame] = {}
    for tk in all_tickers:
        df = _load_prices(tk, data_root)
        if df is not None and not df.empty:
            closes_map[tk] = df["close"].astype(float)
            price_data[tk] = df

    spy_closes = closes_map.get("SPY")
    spy_ret: float | None = None
    if spy_closes is not None and len(spy_closes) >= 2:
        prev = float(spy_closes.iloc[-2])
        if prev != 0:
            spy_ret = float(spy_closes.iloc[-1]) / prev - 1.0

    # Load market drivers
    market_drivers = _load_market_drivers(data_root)

    # Build sibling map for complex_confirm
    sibling_map = _theme_sibling_map(us_baskets)

    # Compute EW 1d return for every basket (needed for cross-sectional rs_z)
    all_basket_ew_rets: dict[str, float] = {}
    for bid, basket in us_baskets.items():
        tickers = _active_tickers(basket)
        ret = _basket_ew_1d_return(tickers, closes_map)
        if ret is not None:
            all_basket_ew_rets[bid] = ret

    # Compute rs_z for every basket (needed for complex_confirm)
    all_basket_rs_z: dict[str, float | None] = {}
    for bid in us_baskets:
        _, z = _leg_rs_z(bid, all_basket_ew_rets.get(bid), all_basket_ew_rets, spy_ret)
        all_basket_rs_z[bid] = z

    # Load prior ledger for hysteresis
    prior_ledger = load_ledger(data_root)

    # Per-basket computation
    basket_states: list[dict] = []
    ledger_candidates: list[dict] = []

    for bid, basket in us_baskets.items():
        try:
            tickers = _active_tickers(basket)
            if not tickers:
                continue

            ew_ret = all_basket_ew_rets.get(bid)
            rs_z_val = all_basket_rs_z.get(bid)
            sibling_ids = sibling_map.get(bid, frozenset())

            # --- Compute all 6 legs ---
            l1 = _leg_impulse_day(tickers, closes_map)
            rs_z_fired, rs_z_computed = _leg_rs_z(
                bid, ew_ret, all_basket_ew_rets, spy_ret)
            l2 = rs_z_fired
            l3 = _leg_breadth_surge(tickers, closes_map)
            l4 = _leg_volume_confirm(tickers, price_data)
            l5 = _leg_complex_confirm(bid, sibling_ids, all_basket_rs_z)
            l6 = _leg_shock_relative_bid(rs_z_val, market_drivers, spy_ret)

            legs = {
                "impulse_day": l1,
                "rs_z": l2,
                "breadth_surge": l3,
                "volume_confirm": l4,
                "complex_confirm": l5,
                "shock_relative_bid": l6,
            }

            k = sum(legs.values())

            # --- State assignment with hysteresis ---
            raw_state: str | None = None
            if k >= STATE_IGNITION_K and l2:
                raw_state = "IGNITION"
            elif k >= STATE_WATCH_K:
                raw_state = "WATCH"

            # Hysteresis: if raw_state is None (would downgrade), check if
            # the prior state was WATCH/IGNITION within HYSTERESIS_SESSIONS
            state: str | None = raw_state
            if raw_state is None:
                prior = _prior_state_for(bid, prior_ledger)
                if prior in ("WATCH", "IGNITION"):
                    sessions_since = _days_since_last_state(bid, prior_ledger, as_of)
                    if 0 < sessions_since <= HYSTERESIS_SESSIONS:
                        state = "DOWNGRADE"  # hysteresis hold

            row = {
                "basket_id": bid,
                "state": state,
                "k": k,
                "legs": legs,
                "rs_z_value": rs_z_computed,
                "ew_1d_ret": round(ew_ret, 5) if ew_ret is not None else None,
                "as_of": as_of,
            }
            basket_states.append(row)

            # Ledger candidates: WATCH / IGNITION / DOWNGRADE
            if state in ("WATCH", "IGNITION", "DOWNGRADE"):
                ledger_candidates.append(row)

        except Exception as ex:  # noqa: BLE001 — one bad basket never aborts the rest
            log.debug("basket_turn_watch: basket %s failed: %s", bid, ex)
            continue

    # Stamp forward ledger (US_LANE gate inside stamp_ledger)
    try:
        n = stamp_ledger(ledger_candidates, as_of=as_of, data_root=data_root)
        if n:
            log.info("basket_turn_watch: stamped %d rows to ledger", n)
    except Exception as ex:  # noqa: BLE001
        log.warning("basket_turn_watch: ledger stamp failed: %s", ex)

    # Backscan (descriptive site artifact only)
    backscan: dict = {}
    if run_backscan and spy_closes is not None:
        backscan = _backscan(
            us_baskets, closes_map, price_data, spy_closes, market_drivers)

    # Assemble site artifact
    result: dict = {
        "schema": "basket_turn_watch.v1",
        "as_of": as_of,
        "built": datetime.now(timezone.utc).isoformat(),
        "n_baskets": len(basket_states),
        "baskets": basket_states,
        "authority": AUTHORITY,
        "disclosure": DISCLOSURE,
    }
    if backscan:
        result["backscan"] = backscan

    return result


# ---------------------------------------------------------------------------
# Site artifact writer
# ---------------------------------------------------------------------------

def write_site_artifact(
    result: dict,
    site_root: Path | None = None,
) -> Path:
    """Write site/basketdata/turn_watch.json. Returns the written path."""
    from lib import config
    if site_root is None:
        site_root = config.ROOT / config.load()["storage"]["site_dir"]
    out_dir = site_root / "basketdata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "turn_watch.json"
    out_path.write_text(
        json.dumps(result, separators=(",", ":"), default=str) + "\n",
        encoding="utf-8",
    )
    return out_path
