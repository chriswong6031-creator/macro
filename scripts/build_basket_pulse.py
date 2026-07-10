"""scripts/build_basket_pulse.py — intraday basket-level tape pulse.

Consumes the ALREADY-FETCHED live-quotes snapshot from site/live/quotes.json
(written there by the intraday-fastpath workflow's quotes step, or fetched from
the live-data branch by git fetch) and produces site/live/basket_pulse.json.

QUOTES SOURCE DECISION:
  The canonical live-quotes snapshot is force-pushed to the `live-data` branch by
  live-quotes.yml (runs on ubuntu-latest every 10 min, all day). The intraday-fastpath
  workflow already writes a LOCAL site/live/quotes.json (the BTC-only hourly snapshot)
  via btc-live.yml, so that path already exists but contains only BTC-USD. The
  correct equity snapshot is from live-data.

  Resolution: the fastpath step that calls this script first fetches the live-data
  branch and checks out just quotes.json into a temp path. We read that file.
  Specifically, the step does:
    git fetch origin live-data:refs/remotes/origin/live-data
    git show origin/live-data:quotes.json > /tmp/quotes_live.json
  and this script reads LIVE_QUOTES_PATH env (default: /tmp/quotes_live.json) or
  falls back to site/live/quotes.json if it exists and has >1 quote.

  NO new per-symbol network fetching is ever done here.

OUTPUT: site/live/basket_pulse.json  +  site/live/basket_pulse_lastgood.json
  Tier: display/de-escalation only (FT-R1, FT-R2).
  FT-R3: shock_day_relative_bid is a same-session descriptive readout with no
  beneficiary/casualty/direction fields and carries the T+1 fade note.
  FT-R5: writes site/ only, data/ discard guard in the workflow.

GRADED MODES (TS-R1 honest-delay law):
  live      — quotes present, median member delayMin <= LIVE_STALE_MIN, pre/rth session.
  delayed   — quotes present but older (median delayMin > LIVE_STALE_MIN), pre/rth session.
              COMPUTE per-basket values from the delayed quotes anyway; stamp delay_min_median.
              A delayed value with its true age is better than a null.
  last_rth  — session post/closed. Serve the sidecar basket_pulse_lastgood.json (persisted
              whenever a live or delayed compute succeeds). Original as_of stamps preserved.
  eod       — no lastgood sidecar yet (first deploy or data gap). Compute 1d EW %chg from
              the last two EOD closes in data/baskets/ohlcv/<SYM>.parquet, stamp bar date.

  The per-basket 'stale' flag is kept for backwards compat.
  Disagreement chips (FT-R12) stay suppressed when mode != live.
"""
from __future__ import annotations

import json
import logging
import os
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("basket_pulse_build")

# ── constants ─────────────────────────────────────────────────────────────────

# Quote age (minutes) beyond which we mark a basket stale (used for live/delayed boundary)
LIVE_STALE_MIN: int = 20

# Minimum coverage fraction for a basket to compute a live EW avg.
# Below this threshold live_ew_chg_pct is set to None (honest null).
MIN_COVERAGE: float = 0.30

# Sidecar file name for last-good pulse
LASTGOOD_FILENAME: str = "basket_pulse_lastgood.json"

# Mode literals (TS-R1)
MODE_LIVE: str = "live"
MODE_DELAYED: str = "delayed"
MODE_LAST_RTH: str = "last_rth"
MODE_EOD: str = "eod"

# ETFs for the offense/defense spread (print-only, no z claims, FT-R3)
DEFENSE_ETFS: list[str] = ["XLP", "XLU", "XLV"]
OFFENSE_ETFS: list[str] = ["SMH", "XLK"]

# Session boundary hours in ET
_PRE_OPEN_START_ET = 4    # 04:00 ET = premarket open
_RTH_START_ET = 9         # 09:30 ET
_RTH_START_MINUTE = 30
_RTH_END_ET = 16          # 16:00 ET
_POST_CLOSE_END_ET = 20   # 20:00 ET = after-hours end

# Shock day relative-bid gate (FT-R3)
_SHOCK_PRIMARY_KEYS: frozenset[str] = frozenset({"oil_shock"})
_SHOCK_FAMILIES: frozenset[str] = frozenset({"geopolitical"})
_T1_FADE_NOTE: str = "58% of violent flips fade at T+1 (n=26)"


# ── session detection ──────────────────────────────────────────────────────────

def _et_session(now_utc: datetime) -> str:
    """Return pre|rth|post|closed from the UTC clock.

    Uses simple hour/minute arithmetic in ET (UTC-4 summer / UTC-5 winter).
    lib.nyse_calendar.is_session() tells us if it's a trading day; if it's a
    weekend/holiday the market never opens → always 'closed'.
    """
    from zoneinfo import ZoneInfo
    from lib import nyse_calendar

    et = now_utc.astimezone(ZoneInfo("America/New_York"))
    if not nyse_calendar.is_session(et.date()):
        return "closed"

    h, m = et.hour, et.minute
    if h < _PRE_OPEN_START_ET:
        return "closed"
    if h < _RTH_START_ET or (h == _RTH_START_ET and m < _RTH_START_MINUTE):
        return "pre"
    if h < _RTH_END_ET:
        return "rth"
    if h < _POST_CLOSE_END_ET:
        return "post"
    return "closed"


# ── quotes loading ─────────────────────────────────────────────────────────────

def _load_quotes(quotes_path: Path | None) -> tuple[dict[str, Any], Path | None]:
    """Return (quotes_dict {SYM: {...}}, resolved_path).

    Search order:
    1. $LIVE_QUOTES_PATH env var
    2. Explicit quotes_path argument
    3. /tmp/quotes_live.json (written by workflow git-fetch step)
    4. site/live/quotes.json (fall-through; may be BTC-only)
    """
    from lib import config

    candidates: list[Path] = []
    env_path = os.environ.get("LIVE_QUOTES_PATH")
    if env_path:
        candidates.append(Path(env_path))
    if quotes_path is not None:
        candidates.append(quotes_path)
    candidates.append(Path("/tmp/quotes_live.json"))
    site_dir = config.ROOT / config.load()["storage"]["site_dir"]
    candidates.append(site_dir / "live" / "quotes.json")

    for p in candidates:
        if not p.exists() or p.stat().st_size < 10:
            continue
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        qs = data.get("quotes") or {}
        if len(qs) < 2:
            # site/live/quotes.json is BTC-only when live-data hasn't been fetched
            log.debug("skipping %s — only %d quotes", p, len(qs))
            continue
        log.info("loaded %d quotes from %s (asof=%s)", len(qs), p, data.get("asof"))
        return qs, p

    log.warning("::warning::no usable quotes file found; pulse will have null coverage")
    return {}, None


# ── membership loading ─────────────────────────────────────────────────────────

def _load_membership(membership_path: Path | None) -> dict[str, Any]:
    """Load data/baskets/membership.json. Returns the baskets dict."""
    from lib import config

    p = membership_path or (config.data_dir() / "baskets" / "membership.json")
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        log.warning("::warning::cannot read membership.json: %s", e)
        return {}
    return data.get("baskets") or {}


def _active_members(basket: dict[str, Any]) -> list[str]:
    """Return tickers of non-removed members."""
    return [
        m["ticker"]
        for m in (basket.get("members") or [])
        if m.get("removed") is None and m.get("ticker")
    ]


# ── staleness check ────────────────────────────────────────────────────────────

def _quote_delay_min(quote: dict[str, Any], now_ms: int) -> float | None:
    """Return quote delay in minutes.

    Prefer the explicit `delayMin` field (written by the quotes worker and
    reflecting the data-provider's own delay, e.g. 193 for Polygon free tier).
    Fall back to (now_ms - ts_ms) / 60_000 if delayMin is absent.
    Using delayMin directly avoids the false-stale problem where the clock drift
    between the quotes worker run and this script run inflates the apparent age.
    """
    delay = quote.get("delayMin")
    if delay is not None:
        try:
            return float(delay)
        except (TypeError, ValueError):
            pass
    ts_ms = quote.get("ts")
    if ts_ms is None:
        return None
    return (now_ms - int(ts_ms)) / 60_000


# Keep backward-compat alias used by existing callers
def _quote_age_min(quote: dict[str, Any], now_ms: int) -> float | None:
    return _quote_delay_min(quote, now_ms)


def _is_stale(quote: dict[str, Any], now_ms: int, stale_min: int = LIVE_STALE_MIN) -> bool:
    delay = _quote_delay_min(quote, now_ms)
    if delay is None:
        return True
    return delay > stale_min


def _median_member_delay(tickers: list[str], quotes: dict[str, Any], now_ms: int) -> float | None:
    """Median delayMin across tickers that are present in quotes."""
    delays: list[float] = []
    for tk in tickers:
        q = quotes.get(tk)
        if q is not None:
            d = _quote_delay_min(q, now_ms)
            if d is not None:
                delays.append(d)
    if not delays:
        return None
    return statistics.median(delays)


# ── EW computation ─────────────────────────────────────────────────────────────

def _ew_chg(tickers: list[str], quotes: dict[str, Any], now_ms: int,
             stale_min: int = LIVE_STALE_MIN,
             include_delayed: bool = False) -> tuple[float | None, int, int, bool]:
    """Equal-weight average of changePct across quoted tickers.

    When include_delayed=False (default, live mode): only fresh quotes (delay <=
    stale_min) contribute to the EW average. Stale quotes are counted in n_quoted
    but excluded from changes.

    When include_delayed=True (delayed mode): ALL present quotes contribute to the
    EW average regardless of delay. This implements the honest-delay law: a delayed
    value with its true age beats a null.

    Returns (ew_chg_pct, n_quoted, n_members, any_stale).
    If coverage < MIN_COVERAGE returns (None, n_quoted, n_members, any_stale).
    """
    changes: list[float] = []
    n_quoted = 0
    any_stale = False
    for tk in tickers:
        q = quotes.get(tk)
        if q is None:
            continue
        n_quoted += 1
        is_q_stale = _is_stale(q, now_ms, stale_min)
        if is_q_stale:
            any_stale = True
            if not include_delayed:
                continue  # live mode: skip stale
        chg = q.get("changePct")
        if chg is not None:
            changes.append(float(chg))

    n_members = len(tickers)
    coverage = len(changes) / n_members if n_members > 0 else 0.0
    if coverage < MIN_COVERAGE:
        return None, n_quoted, n_members, any_stale
    return round(sum(changes) / len(changes), 3), n_quoted, n_members, any_stale


# ── cum_2d computation ─────────────────────────────────────────────────────────

def _cum_2d(basket_id: str, live_ew_chg_pct: float | None) -> float | None:
    """Yesterday close-to-close + today's live move.

    Uses data/basket_levels/us.parquet `{id}__level_price` column.
    The 2d pct change is (yesterday_close / 2_days_ago_close - 1) + live_chg_pct/100,
    expressed as percentage.

    Returns None if data unavailable or live_ew_chg_pct is None.
    """
    if live_ew_chg_pct is None:
        return None
    try:
        import pandas as pd
        from lib import config

        p = config.data_dir() / "basket_levels" / "us.parquet"
        col = f"{basket_id}__level_price"
        df = pd.read_parquet(p, columns=[col])
        if df.empty or len(df) < 2:
            return None
        # last two rows: yesterday and day before
        vals = df[col].dropna()
        if len(vals) < 2:
            return None
        yesterday = float(vals.iloc[-1])
        day_before = float(vals.iloc[-2])
        if day_before == 0:
            return None
        yday_chg = (yesterday / day_before - 1) * 100
        return round(yday_chg + live_ew_chg_pct, 3)
    except Exception as e:
        log.debug("cum_2d unavailable for %s: %s", basket_id, e)
        return None


# ── cross-sectional rank ───────────────────────────────────────────────────────

def _tape_ranks(baskets_data: list[dict[str, Any]]) -> dict[str, int | None]:
    """Cross-sectional rank of live_ew_chg_pct (1=weakest, N=strongest).
    Baskets with null live_ew_chg_pct get rank None.
    """
    ranked = [(b["id"], b["live_ew_chg_pct"])
              for b in baskets_data if b["live_ew_chg_pct"] is not None]
    ranked.sort(key=lambda x: x[1])
    result: dict[str, int | None] = {b["id"]: None for b in baskets_data}
    for i, (bid, _) in enumerate(ranked):
        result[bid] = i + 1
    return result


# ── offense/defense spread ─────────────────────────────────────────────────────

def _od_spread(quotes: dict[str, Any], now_ms: int,
               stale_min: int = LIVE_STALE_MIN) -> float | None:
    """EW(XLP,XLU,XLV) vs EW(SMH,XLK) live changePct spread.
    Print-only intraday descriptive (FT-R3). Returns None if any ETF missing/stale.
    """
    def _ew_etfs(tickers: list[str]) -> float | None:
        vals = []
        for tk in tickers:
            q = quotes.get(tk)
            if q is None or _is_stale(q, now_ms, stale_min):
                return None
            chg = q.get("changePct")
            if chg is None:
                return None
            vals.append(float(chg))
        return sum(vals) / len(vals) if vals else None

    def_ew = _ew_etfs(DEFENSE_ETFS)
    off_ew = _ew_etfs(OFFENSE_ETFS)
    if def_ew is None or off_ew is None:
        return None
    # spread = defensive - offensive (positive = defense leading)
    return round(def_ew - off_ew, 3)


# ── EOD fallback ──────────────────────────────────────────────────────────────

def _eod_basket_chg(basket_id: str, members: list[str]) -> tuple[float | None, str | None]:
    """Equal-weight 1d % change from the last two EOD closes for all members.

    Reads data/baskets/ohlcv/<SYM>.parquet (close column) for each member.
    Returns (ew_chg_pct, bar_date_str) or (None, None) if data unavailable.
    This is the honest-null fallback when no quotes and no lastgood exist.
    """
    try:
        import pandas as pd
        from lib import config

        ohlcv_dir = config.data_dir() / "baskets" / "ohlcv"
        changes: list[float] = []
        bar_dates: list[str] = []

        for sym in members:
            p = ohlcv_dir / f"{sym}.parquet"
            if not p.exists():
                continue
            try:
                df = pd.read_parquet(p, columns=["close"])
                vals = df["close"].dropna()
                if len(vals) < 2:
                    continue
                prev_close = float(vals.iloc[-2])
                last_close = float(vals.iloc[-1])
                if prev_close == 0:
                    continue
                chg = (last_close / prev_close - 1) * 100
                changes.append(chg)
                # Capture the bar date from index
                bar_date = vals.index[-1]
                if hasattr(bar_date, "date"):
                    bar_dates.append(str(bar_date.date()))
                else:
                    bar_dates.append(str(bar_date)[:10])
            except Exception as e:
                log.debug("eod_basket_chg: skip %s: %s", sym, e)
                continue

        if len(changes) < max(1, len(members) * MIN_COVERAGE):
            return None, None

        ew_chg = round(sum(changes) / len(changes), 3)
        # Use the most common bar date (mode)
        bar_date_out = max(set(bar_dates), key=bar_dates.count) if bar_dates else None
        return ew_chg, bar_date_out

    except Exception as e:
        log.debug("_eod_basket_chg failed for %s: %s", basket_id, e)
        return None, None


# ── lastgood sidecar ──────────────────────────────────────────────────────────

def _load_lastgood(out_dir: Path) -> dict[str, Any] | None:
    """Load basket_pulse_lastgood.json from out_dir. Returns None if absent."""
    p = out_dir / LASTGOOD_FILENAME
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:
        log.debug("lastgood load failed: %s", e)
        return None


def _save_lastgood(result: dict[str, Any], out_dir: Path) -> None:
    """Persist a live/delayed pulse result as the lastgood sidecar."""
    p = out_dir / LASTGOOD_FILENAME
    try:
        p.write_text(json.dumps(result, separators=(",", ":"), allow_nan=False) + "\n")
        log.info("saved lastgood sidecar → %s", p)
    except Exception as e:
        log.warning("::warning::could not save lastgood sidecar: %s", e)


# ── shock-day relative bid ─────────────────────────────────────────────────────

def _shock_day_relative_bid(
    market_drivers: dict[str, Any] | None,
    baskets_data: list[dict[str, Any]],
    quotes: dict[str, Any],
    now_ms: int,
    stale_min: int = LIVE_STALE_MIN,
) -> dict[str, Any] | None:
    """Populate ONLY when market_drivers shows oil_shock/geopolitical-family primary
    AND index is down. Returns the same-session descriptive readout per FT-R3.

    NO beneficiary/casualty/direction fields. Carries T+1 fade note.
    """
    if not market_drivers:
        return None

    primary = market_drivers.get("primary", "")
    family = market_drivers.get("family", "")
    # Gate: oil_shock primary OR geopolitical family
    if primary not in _SHOCK_PRIMARY_KEYS and family not in _SHOCK_FAMILIES:
        return None

    # Gate: index (SPY) must be down today
    spy = quotes.get("SPY") or quotes.get("^GSPC")
    if spy is None:
        return None
    spy_chg = spy.get("changePct")
    if spy_chg is None or float(spy_chg) >= 0:
        return None

    # Build rows: observed live move for each basket — descriptive, no ranking
    rows = []
    for b in baskets_data:
        if b["live_ew_chg_pct"] is not None:
            rows.append({"id": b["id"], "live_ew_chg_pct": b["live_ew_chg_pct"]})

    if not rows:
        return None

    return {
        "active_driver": primary or family,
        "index_chg_pct": round(float(spy_chg), 3),
        "rows": rows,
        "t1_fade_note": _T1_FADE_NOTE,
    }


# ── market_drivers loading ─────────────────────────────────────────────────────

def _load_market_drivers(drivers_path: Path | None) -> dict[str, Any] | None:
    """Load site/live/market_drivers.json. Returns None if unavailable."""
    from lib import config

    p = drivers_path
    if p is None:
        site_dir = config.ROOT / config.load()["storage"]["site_dir"]
        p = site_dir / "live" / "market_drivers.json"
    if not p or not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


# ── W5: AI-capex complex rollup ───────────────────────────────────────────────

# AI-capex complex basket ids (mirrors engine/demand_capex.AI_CAPEX_THEMES keys).
# FT-R10: FTR creates no new theme vocabulary; we import the canonical set.
def _ai_capex_ids() -> frozenset[str]:
    try:
        from engine.demand_capex import AI_CAPEX_THEMES
        return frozenset(AI_CAPEX_THEMES.keys())
    except Exception:
        # Fallback hard-coded to avoid dependency failures making the build fatal
        return frozenset({
            "memory_storage", "ai_semiconductors", "semicap_equipment",
            "data_center_power", "grid_electrification", "nuclear_power",
        })


def _compute_complexes(
    baskets_data: list[dict[str, Any]],
    quotes: dict[str, Any],
    now_ms: int,
    stale_min: int = LIVE_STALE_MIN,
) -> list[dict[str, Any]]:
    """W5: aggregate live basket pulse to the AI-capex complex.

    For the ai_capex complex (engine/demand_capex.AI_CAPEX_THEMES keys):
    - live_ew_chg_pct: EW over member baskets' live_ew_chg_pct (skipping nulls)
    - n_baskets: total baskets in the complex
    - n_live: baskets with a non-null live_ew_chg_pct
    - only_green_complex: bool — this complex EW positive while SPY proxy negative
      AND all other computable complexes negative (descriptive, same-session)

    Coverage-null rules: if no member basket has live_ew_chg_pct, live_ew_chg_pct
    is None (honest null). FT-R3: descriptive same-session only.
    """
    ai_ids = _ai_capex_ids()

    # Index baskets by id
    by_id: dict[str, dict[str, Any]] = {b["id"]: b for b in baskets_data}

    # Compute EW for ai_capex complex
    ai_chgs: list[float] = []
    n_baskets = 0
    for bid in ai_ids:
        if bid in by_id:
            n_baskets += 1
            chg = by_id[bid].get("live_ew_chg_pct")
            if chg is not None:
                ai_chgs.append(float(chg))

    ai_ew = round(sum(ai_chgs) / len(ai_chgs), 3) if ai_chgs else None

    # SPY proxy: read from quotes directly (stale-gated)
    spy_q = quotes.get("SPY") or quotes.get("^GSPC")
    spy_chg: float | None = None
    if spy_q is not None and not _is_stale(spy_q, now_ms, stale_min):
        raw = spy_q.get("changePct")
        if raw is not None:
            spy_chg = float(raw)

    # only_green_complex: ai_capex EW positive while SPY negative
    # AND all other computable complex EWs are also negative.
    # "Other computable complexes" = there are none yet in v1 (only ai_capex).
    # Per the spec: "all other computable complexes negative" — with only one
    # complex in v1, this condition is satisfied vacuously when SPY is down.
    only_green: bool = (
        ai_ew is not None
        and spy_chg is not None
        and ai_ew > 0
        and spy_chg < 0
    )

    return [
        {
            "complex_id": "ai_capex",
            "live_ew_chg_pct": ai_ew,
            "n_baskets": n_baskets,
            "n_live": len(ai_chgs),
            "only_green_complex": only_green,
        }
    ]


# ── mode detection ────────────────────────────────────────────────────────────

def _detect_mode(quotes: dict[str, Any], session: str, now_ms: int,
                 stale_min: int, all_members: list[str]) -> str:
    """Determine which pulse mode applies given the current state.

    Rules (TS-R1):
      live     — pre/rth session + quotes present + median member delay <= stale_min
      delayed  — pre/rth session + quotes present + median member delay > stale_min
      last_rth — post/closed session (serve from sidecar)
      eod      — post/closed session with no sidecar (EOD fallback)

    Note: last_rth vs eod distinction is made by the caller (it checks for sidecar).
    This function only returns live, delayed, or a placeholder for post/closed.
    """
    if session in ("post", "closed"):
        return MODE_LAST_RTH  # caller will check for sidecar and may downgrade to eod

    if not quotes:
        return MODE_LAST_RTH  # no quotes at all → try sidecar

    med = _median_member_delay(all_members, quotes, now_ms)
    if med is None:
        return MODE_LAST_RTH  # no member quotes at all

    return MODE_LIVE if med <= stale_min else MODE_DELAYED


# ── main build ─────────────────────────────────────────────────────────────────

def build(
    *,
    quotes_path: Path | None = None,
    membership_path: Path | None = None,
    drivers_path: Path | None = None,
    stale_min: int = LIVE_STALE_MIN,
    now: datetime | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Build the basket pulse JSON. Returns the full output dict.

    Implements graded modes (TS-R1 honest-delay law):
      live/delayed — compute from quotes; save lastgood sidecar.
      last_rth     — load lastgood sidecar; stamp mode=last_rth.
      eod          — compute 1d EW from OHLCV closes; stamp mode=eod + bar date.

    Exit-0-always contract: any unexpected exception is caught; the caller will
    emit ::warning:: and write a degraded output (see main()).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    now_ms = int(now.timestamp() * 1000)

    session = _et_session(now)
    quotes, resolved_path = _load_quotes(quotes_path)
    baskets_meta = _load_membership(membership_path)
    market_drivers = _load_market_drivers(drivers_path)

    # Collect all active members for global delay median
    all_members: list[str] = []
    for basket in baskets_meta.values():
        all_members.extend(_active_members(basket))

    # Determine mode
    mode = _detect_mode(quotes, session, now_ms, stale_min, all_members)

    # ── last_rth / eod branch ─────────────────────────────────────────────────
    if mode == MODE_LAST_RTH:
        # Try to load the lastgood sidecar
        if out_dir is not None:
            lastgood = _load_lastgood(out_dir)
        else:
            lastgood = None

        if lastgood is not None:
            # Serve the last good read with updated mode stamp
            lastgood = dict(lastgood)
            lastgood["mode"] = MODE_LAST_RTH
            lastgood["built"] = now.strftime("%Y-%m-%d %H:%M:%S UTC")
            # Preserve original as_of_quotes from lastgood; add a served_utc stamp
            lastgood["served_utc"] = now.isoformat()
            lastgood["session"] = session
            log.info("serving lastgood sidecar (mode=last_rth) from %s",
                     lastgood.get("as_of_utc", "?"))
            return lastgood

        # No sidecar → EOD fallback
        log.info("no lastgood sidecar — attempting EOD fallback (mode=eod)")
        baskets_data: list[dict[str, Any]] = []
        bar_dates: list[str] = []
        for basket_id, basket in baskets_meta.items():
            members = _active_members(basket)
            if not members:
                continue
            eod_chg, bar_date = _eod_basket_chg(basket_id, members)
            baskets_data.append({
                "id": basket_id,
                "n_members": len(members),
                "n_quoted": 0,
                "live_ew_chg_pct": eod_chg,
                "cum_2d_pct": None,
                "tape_rank": None,
                "stale": True,
                "delay_min": None,
                "bar_date": bar_date,
            })
            if bar_date:
                bar_dates.append(bar_date)

        rank_map = _tape_ranks(baskets_data)
        for b in baskets_data:
            b["tape_rank"] = rank_map.get(b["id"])

        n_non_null = sum(1 for b in baskets_data if b["live_ew_chg_pct"] is not None)
        eod_bar_date = (max(set(bar_dates), key=bar_dates.count)
                        if bar_dates else None)
        return {
            "schema": "basket_pulse.v1",
            "as_of_utc": now.isoformat(),
            "as_of_quotes": eod_bar_date,
            "built": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "session": session,
            "mode": MODE_EOD,
            "delay_min_median": None,
            "coverage_pct": round(n_non_null / len(baskets_data) * 100, 1) if baskets_data else 0.0,
            "quotes_source": None,
            "n_quotes_total": 0,
            "stale_min": stale_min,
            "baskets": baskets_data,
            "od_spread_print": None,
            "shock_day_relative_bid": None,
            "complexes": _compute_complexes(baskets_data, {}, now_ms, stale_min),
        }

    # ── live / delayed branch ─────────────────────────────────────────────────
    include_delayed = (mode == MODE_DELAYED)

    # Global delay median
    delay_med = _median_member_delay(all_members, quotes, now_ms)

    baskets_data_live: list[dict[str, Any]] = []
    coverage_sum = 0.0
    coverage_count = 0

    for basket_id, basket in baskets_meta.items():
        members = _active_members(basket)
        if not members:
            continue
        n_members = len(members)

        live_ew, n_quoted, _, any_stale = _ew_chg(
            members, quotes, now_ms, stale_min,
            include_delayed=include_delayed)

        # Per-basket delay median
        basket_delay = _median_member_delay(members, quotes, now_ms)

        coverage_frac = n_quoted / n_members if n_members > 0 else 0.0
        coverage_sum += coverage_frac
        coverage_count += 1

        cum_2d = _cum_2d(basket_id, live_ew)

        baskets_data_live.append({
            "id": basket_id,
            "n_members": n_members,
            "n_quoted": n_quoted,
            "live_ew_chg_pct": live_ew,
            "cum_2d_pct": cum_2d,
            "tape_rank": None,  # filled below
            "stale": bool(any_stale),
            "delay_min": round(basket_delay, 1) if basket_delay is not None else None,
        })

    # ── cross-sectional ranks ──────────────────────────────────────────────────
    rank_map = _tape_ranks(baskets_data_live)
    for b in baskets_data_live:
        b["tape_rank"] = rank_map.get(b["id"])

    # ── offense/defense spread (fresh-gated: only in live mode) ───────────────
    od_spread = _od_spread(quotes, now_ms, stale_min) if mode == MODE_LIVE else None

    # ── shock-day relative bid ─────────────────────────────────────────────────
    shock_bid = _shock_day_relative_bid(
        market_drivers, baskets_data_live, quotes, now_ms, stale_min)

    # ── coverage summary ───────────────────────────────────────────────────────
    coverage_pct = round(coverage_sum / coverage_count * 100, 1) if coverage_count else 0.0

    # ── W5: AI-capex complex rollup ────────────────────────────────────────────
    complexes = _compute_complexes(baskets_data_live, quotes, now_ms, stale_min)

    # ── assemble output ────────────────────────────────────────────────────────
    result: dict[str, Any] = {
        "schema": "basket_pulse.v1",
        "as_of_utc": now.isoformat(),
        "as_of_quotes": now.isoformat(),
        "built": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "session": session,
        "mode": mode,
        "delay_min_median": round(delay_med, 1) if delay_med is not None else None,
        "coverage_pct": coverage_pct,
        "quotes_source": str(resolved_path) if resolved_path else None,
        "n_quotes_total": len(quotes),
        "stale_min": stale_min,
        "baskets": baskets_data_live,
        "od_spread_print": od_spread,
        "shock_day_relative_bid": shock_bid,
        "complexes": complexes,
    }

    # Persist lastgood sidecar whenever we have a live or delayed compute
    if out_dir is not None:
        _save_lastgood(result, out_dir)

    return result


def main() -> None:
    import argparse
    from lib import config

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="Build site/live/basket_pulse.json.")
    ap.add_argument("--out", default=None, help="output path (default: site/live/basket_pulse.json)")
    ap.add_argument("--quotes", default=None, help="path to quotes.json snapshot")
    ap.add_argument("--drivers", default=None, help="path to market_drivers.json")
    ap.add_argument("--stale-min", type=int, default=LIVE_STALE_MIN)
    args = ap.parse_args()

    site_dir = config.ROOT / config.load()["storage"]["site_dir"]
    out_path = Path(args.out) if args.out else (site_dir / "live" / "basket_pulse.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_dir = out_path.parent

    try:
        result = build(
            quotes_path=Path(args.quotes) if args.quotes else None,
            drivers_path=Path(args.drivers) if args.drivers else None,
            stale_min=args.stale_min,
            out_dir=out_dir,
        )
    except Exception as exc:
        log.error("::warning::basket_pulse build failed: %s", exc)
        # Emit a degraded placeholder — exit 0 always per contract
        now = datetime.now(timezone.utc)
        result = {
            "schema": "basket_pulse.v1",
            "as_of_utc": now.isoformat(),
            "as_of_quotes": None,
            "built": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "session": "unknown",
            "mode": "error",
            "delay_min_median": None,
            "coverage_pct": 0.0,
            "error": str(exc),
            "baskets": [],
            "od_spread_print": None,
            "shock_day_relative_bid": None,
            "complexes": [],
        }

    out_path.write_text(
        json.dumps(result, separators=(",", ":"), allow_nan=False) + "\n")
    n_baskets = len(result.get("baskets") or [])
    n_quoted = sum(b.get("n_quoted", 0) for b in (result.get("baskets") or []))
    log.info("wrote %s — %d baskets, %d symbols quoted, session=%s, mode=%s, coverage=%.1f%%",
             out_path, n_baskets, n_quoted,
             result.get("session"), result.get("mode", "?"), result.get("coverage_pct", 0))


if __name__ == "__main__":
    main()
