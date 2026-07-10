"""Risk Radar — market-internal confirmation chips for the recovery panel.

DISPLAY-ONLY · ACCRUING · NEVER RAISES. Provenance: RRX-R2..R7 (research/RISK_RADAR_EXPANSION_MASTERPLAN_BY_FABLE.md).

Every chip degrades to absent (fired=False, fresh=False, detail with 'note') when its data store
is missing or malformed. None of these chips touch _LEG_CALIB, state, gross, or the banner —
they are added as sibling fields on the recovery panel (RRX-R7).

Mature-window gates mirror advanced_breadth.py precedent:
  MATURE_N     = 400  (for adv/dec breadth chips: c1)
  THRUST_N     = 250  (for summation / other chips: c2)

Literature stats quoted in 'detail' dicts are as reported in cited sources, not our own forward
record. The forward record is managed by engine/risk_radar_recovery_audit.py (W0).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window
from lib import config, store

log = logging.getLogger(__name__)

MATURE_N = 400      # minimum n_members for adv/dec chips (c1) — advanced_breadth precedent
THRUST_N = 250      # minimum n_members for summation/other chips (c2+)
_FRESH_BD = 10      # business days within which a chip is "fresh"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _iso(ts) -> str | None:
    """Return ISO date string from a pandas Timestamp or None."""
    try:
        if ts is None or (isinstance(ts, float) and np.isnan(ts)):
            return None
        return str(pd.Timestamp(ts).date())
    except Exception:  # noqa: BLE001
        return None


def _bd_since(ts) -> int | None:
    """Business days between ts and today."""
    if ts is None:
        return None
    try:
        t = pd.Timestamp(ts)
        today = pd.Timestamp(date.today())
        bdays = len(pd.bdate_range(t, today)) - 1
        return max(0, bdays)
    except Exception:  # noqa: BLE001
        return None


def _is_fresh(ts) -> bool:
    """True if ts is within _FRESH_BD business days of today."""
    bd = _bd_since(ts)
    return bd is not None and bd <= _FRESH_BD


def _absent_chip(key: str, label_en: str, label_zh: str, note: str) -> dict:
    return {
        "key": key,
        "label_en": label_en,
        "label_zh": label_zh,
        "fired": False,
        "fresh": False,
        "since": None,
        "detail": {"note": note},
        "accruing": True,
    }


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


# ---------------------------------------------------------------------------
# C1 — breadth thrust confluence (K-of-N, ONE chip, RRX-R3)
# ---------------------------------------------------------------------------

def _c1_thrust_confluence(breadth: pd.DataFrame) -> dict:
    """ONE chip over {ZBT, BAM, ADT5, T70}. Any single underlying breadth burst fires k>=1.
    Mature-window gate: n_members >= MATURE_N for all days counted (RRX-R1).

    lit stats (not our record): ZBT ~14-18 NYSE events 1945+; 6m +17%/12m +23%; S&P fires more often.
    """
    key = "thrust_confluence"
    label_en = "Breadth thrust confluence"
    label_zh = "广度推进共振"

    try:
        b = breadth.copy()
        b.index = pd.to_datetime(b.index)
        b = b.sort_index()

        required = {"adv", "dec", "n_members"}
        if not required.issubset(b.columns):
            return _absent_chip(key, label_en, label_zh, "breadth columns missing")

        # mature-window filter
        b = b[b["n_members"] >= MATURE_N]
        if len(b) < 30:
            return _absent_chip(key, label_en, label_zh, f"n_members < {MATURE_N} throughout")

        total = b["adv"] + b["dec"]
        # avoid division by zero
        total = total.replace(0, np.nan)
        ratio = b["adv"] / total

        adv10 = b["adv"].rolling(10, min_periods=5).sum()
        dec10 = b["dec"].rolling(10, min_periods=5).sum()
        ema_ratio = _ema(ratio, 10)

        today = b.index[-1]
        # lookback windows (calendar not bday, but pandas DateOffset handles weekends)
        w21 = b.index >= (today - pd.offsets.BDay(21))
        w25 = b.index >= (today - pd.offsets.BDay(25))

        components: dict[str, dict] = {}

        # --- ZBT: 10d EMA crossed <=0.40 then >=0.615 within <=10 sessions, scanned last 25 ---
        zbt_fired = False
        zbt_last = None
        ema_w25 = ema_ratio[w25]
        if len(ema_w25) >= 10:
            for i in range(len(ema_w25) - 9):
                window = ema_w25.iloc[i: i + 10]
                if (window <= 0.40).any() and (window >= 0.615).any():
                    # ensure the <=0.40 comes before >=0.615
                    low_idx = (window <= 0.40).values.argmax()
                    high_idx = (window >= 0.615).values.argmax()
                    if low_idx < high_idx:
                        zbt_fired = True
                        zbt_last = _iso(window.index[-1])
        components["zbt"] = {"fired": zbt_fired, "last": zbt_last,
                              "desc": "10d EMA adv-share: <=0.40 then >=0.615 within 10 sessions"}

        # --- BAM (Deemer): 10d sum adv / 10d sum dec >= 1.97, any day in last 21 ---
        bam_fired = False
        bam_last = None
        dec10_safe = dec10.replace(0, np.nan)
        bam_ratio = (adv10 / dec10_safe)[w21]
        if len(bam_ratio) > 0:
            bam_idx = bam_ratio[bam_ratio >= 1.97]
            if not bam_idx.empty:
                bam_fired = True
                bam_last = _iso(bam_idx.index[-1])
        components["bam"] = {"fired": bam_fired, "last": bam_last,
                             "desc": "10d Σadv / 10d Σdec >= 1.97 (Deemer breakaway)"}

        # --- ADT5 (Whaley): 5d mean ratio >= 0.73, any day last 21 ---
        adt5_fired = False
        adt5_last = None
        mean5 = ratio.rolling(5, min_periods=3).mean()[w21]
        if len(mean5) > 0:
            adt5_idx = mean5[mean5 >= 0.73]
            if not adt5_idx.empty:
                adt5_fired = True
                adt5_last = _iso(adt5_idx.index[-1])
        components["adt5"] = {"fired": adt5_fired, "last": adt5_last,
                              "desc": "5d mean adv-share >= 0.73 (Whaley ADT5)"}

        # --- T70: 3 consecutive days ratio >= 0.70, run ending in last 21 ---
        t70_fired = False
        t70_last = None
        ratio_w21 = ratio[w21]
        if len(ratio_w21) >= 3:
            above70 = (ratio_w21 >= 0.70).astype(int)
            # look for 3-consecutive run ending anywhere in the window
            for i in range(len(above70) - 2):
                if above70.iloc[i] and above70.iloc[i + 1] and above70.iloc[i + 2]:
                    t70_fired = True
                    t70_last = _iso(above70.index[i + 2])
        components["t70"] = {"fired": t70_fired, "last": t70_last,
                             "desc": "3 consecutive sessions ratio >= 0.70 (Triple-70)"}

        k = sum(1 for c in components.values() if c["fired"])
        fired = k >= 1

        # "since" = earliest last_date among fired components
        fired_dates = [c["last"] for c in components.values() if c["fired"] and c["last"]]
        since = min(fired_dates) if fired_dates else None
        fresh = _is_fresh(since) if fired else False

        return {
            "key": key,
            "label_en": label_en,
            "label_zh": label_zh,
            "fired": fired,
            "fresh": fresh,
            "since": since,
            "detail": {
                "k": k,
                "components": components,
                "burst_counted_once": True,
                "note": (
                    "Lit stats (not our record): ZBT ~14-18 NYSE events 1945+, 6m +17%/12m +23%; "
                    "S&P proxy fires more often. ONE chip regardless of components lit (RRX-R3)."
                ),
            },
            "accruing": True,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("c1 thrust_confluence failed: %s", e)
        return _absent_chip(key, label_en, label_zh, f"error: {e}")


# ---------------------------------------------------------------------------
# C2 — McClellan Summation low→high swing
# ---------------------------------------------------------------------------

def _c2_msi_swing(breadth: pd.DataFrame) -> dict:
    """RANA-based McClellan Summation Index. Event: min(last 126) < 100 AND now > 1000 AND
    5d slope > 0. Mature-window gate: n_members >= THRUST_N.
    """
    key = "msi_swing"
    label_en = "Summation low→high swing"
    label_zh = "麦克伦求和指数低位跃升"

    try:
        b = breadth.copy()
        b.index = pd.to_datetime(b.index)
        b = b.sort_index()

        if not {"adv", "dec", "n_members"}.issubset(b.columns):
            return _absent_chip(key, label_en, label_zh, "breadth columns missing")

        # mature-window gate
        b_mature = b[b["n_members"] >= THRUST_N]
        if len(b_mature) < 60:
            return _absent_chip(key, label_en, label_zh, f"fewer than 60 mature rows (n_members >= {THRUST_N})")

        # RANA = 1000 * (adv - dec) / (adv + dec) — ratio-adjusted
        total = b_mature["adv"] + b_mature["dec"]
        total = total.replace(0, np.nan)
        rana = 1000.0 * (b_mature["adv"] - b_mature["dec"]) / total

        # oscillator = ema19(RANA) - ema39(RANA)
        osc = _ema(rana, 19) - _ema(rana, 39)

        # summation = cumulative sum of oscillator starting at first mature date
        summ = osc.cumsum()

        now_val = float(summ.iloc[-1]) if not summ.empty else None
        if now_val is None or np.isnan(now_val):
            return _absent_chip(key, label_en, label_zh, "summation is NaN")

        # 5d slope
        if len(summ) >= 6:
            slope_5d = float(summ.iloc[-1] - summ.iloc[-6])
        else:
            slope_5d = None

        # min of last 126 bars
        w126 = summ.iloc[-126:] if len(summ) >= 126 else summ
        recent_min = float(w126.min())

        fired = (recent_min < 100) and (now_val > 1000) and (slope_5d is not None and slope_5d > 0)

        # fresh: did it cross above 1000 within last _FRESH_BD business days?
        since = None
        fresh = False
        if fired:
            # find the crossing date (last time summation crossed above 1000 after being below)
            above1k = summ > 1000
            below_then_above = (~above1k.shift(1, fill_value=False)) & above1k
            crossings = summ[below_then_above]
            if not crossings.empty:
                last_cross = crossings.index[-1]
                since = _iso(last_cross)
                fresh = _is_fresh(last_cross)

        return {
            "key": key,
            "label_en": label_en,
            "label_zh": label_zh,
            "fired": fired,
            "fresh": fresh,
            "since": since,
            "detail": {
                "summation_now": round(now_val, 1) if now_val is not None else None,
                "recent_min_126": round(recent_min, 1),
                "slope_5d": round(slope_5d, 1) if slope_5d is not None else None,
                "note": (
                    "Lit (SentimenTrader): ~29 events since 1962 on NYSE. S&P proxy fires more often. "
                    "Distinct from killed MCO-bounce constructs (RRX-R4)."
                ),
            },
            "accruing": True,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("c2 msi_swing failed: %s", e)
        return _absent_chip(key, label_en, label_zh, f"error: {e}")


# ---------------------------------------------------------------------------
# C3 — %>20dma washout→thrust round-trip
# ---------------------------------------------------------------------------

def _c3_washout_thrust20(root: Path | None) -> dict:
    """Needs data/breadth/_closes_cache.parquet (gitignored, runner-local).
    Degrades gracefully if absent — chip ships with note 'cache-local; accrues on runner'.
    """
    key = "washout_thrust20"
    label_en = "%>20dma washout→thrust"
    label_zh = "20日线上比例洗出→推进"

    try:
        base = config.data_dir() if root is None else (Path(root) / "data")
        cache_path = base / "breadth" / "_closes_cache.parquet"

        if not cache_path.exists():
            return _absent_chip(key, label_en, label_zh,
                                "cache-local; accrues on runner (data/breadth/_closes_cache.parquet absent)")

        df = pd.read_parquet(cache_path)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        if len(df) < 63:
            return _absent_chip(key, label_en, label_zh, "cache too short (<63 rows)")

        # compute pct of tickers above their 20dma
        ma20 = df.rolling(20, min_periods=10).mean()
        above20 = (df > ma20).sum(axis=1)
        n_valid = df.notna().sum(axis=1).replace(0, np.nan)
        pct = above20 / n_valid

        # event: trailing 63d min < 25% then now > 90%
        now_val = float(pct.iloc[-1])
        w63_min = float(pct.iloc[-63:].min())

        fired = (w63_min < 0.25) and (now_val > 0.90)

        since = None
        fresh = False
        if fired:
            # find crossing above 90% after being below 25%
            above90 = pct > 0.90
            below25 = pct < 0.25
            # find episodes: first find where we were below 25%, then crossed 90%
            crossings = []
            last_below25 = None
            for i in range(len(pct)):
                if below25.iloc[i]:
                    last_below25 = i
                elif above90.iloc[i] and last_below25 is not None:
                    crossings.append(pct.index[i])
                    last_below25 = None  # reset until next washout
            if crossings:
                last_cross = crossings[-1]
                since = _iso(last_cross)
                fresh = _is_fresh(last_cross)

        return {
            "key": key,
            "label_en": label_en,
            "label_zh": label_zh,
            "fired": fired,
            "fresh": fresh,
            "since": since,
            "detail": {
                "pct_now": round(now_val, 3),
                "min_63d": round(w63_min, 3),
                "note": (
                    "ONE canonical %>20dma lookback (RRX-R5). ~2 events/yr. "
                    "Single-condition >90% fires ~8x/yr — context descriptor only."
                ),
            },
            "accruing": True,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("c3 washout_thrust20 failed: %s", e)
        return _absent_chip(key, label_en, label_zh, f"error: {e}")


# ---------------------------------------------------------------------------
# C4 — Follow-Through Day
# ---------------------------------------------------------------------------

def _c4_ftd(root: Path | None) -> dict:
    """IBD-style Follow-Through Day from SPY OHLCV.
    Rally attempt: after >=6% drawdown from 63d high, attempt starts on first up-close from low;
    day counter resets if low undercut. FTD = attempt day 4..13, close +>=1.2%, volume > prior session.
    """
    key = "ftd"
    label_en = "Follow-through day"
    label_zh = "放量确认日"

    try:
        spy = store.read("yahoo", "SPY")
        if spy is None or "close" not in spy.columns or "volume" not in spy.columns:
            return _absent_chip(key, label_en, label_zh, "SPY close/volume unavailable")

        spy = spy[["close", "volume"]].dropna().sort_index()
        if len(spy) < 70:
            return _absent_chip(key, label_en, label_zh, "SPY too short")

        close = spy["close"].astype(float)
        volume = spy["volume"].astype(float)

        # rolling 63d high
        hi63 = close.rolling(63, min_periods=30).max()

        ftd_dates = []

        # Simulate rally attempts over the full history
        attempt_start = None
        attempt_low = None
        attempt_day = 0
        in_drawdown = False

        for i in range(1, len(close)):
            px = close.iloc[i]
            prev = close.iloc[i - 1]
            vol = volume.iloc[i]
            prev_vol = volume.iloc[i - 1]
            h63 = hi63.iloc[i]

            dd_from_peak = (px / h63 - 1.0) if (h63 and not np.isnan(h63)) else 0.0

            # drawdown threshold: >=6% from 63d high
            if dd_from_peak <= -0.06:
                if not in_drawdown:
                    in_drawdown = True
                    attempt_start = None
                    attempt_low = None
                    attempt_day = 0
                # track the intraday low in the drawdown phase — use close as proxy
                if attempt_low is None or px < attempt_low:
                    attempt_low = px
            else:
                in_drawdown = False

            # attempt start: first up-close from the drawdown low
            if attempt_low is not None and px > prev and attempt_start is None:
                attempt_start = i
                attempt_day = 1
            elif attempt_start is not None:
                # reset if price undercuts the attempt low
                if px < attempt_low:
                    attempt_start = None
                    attempt_low = px
                    attempt_day = 0
                else:
                    attempt_day += 1

            # FTD check: day 4..13 of attempt, +>=1.2%, volume > prior session
            if attempt_start is not None and 4 <= attempt_day <= 13:
                pct_chg = (px / prev - 1.0)
                if pct_chg >= 0.012 and vol > prev_vol:
                    ftd_dates.append(close.index[i])
                    # after FTD, reset — wait for next drawdown
                    attempt_start = None
                    attempt_low = None
                    attempt_day = 0

        fired = False
        since = None
        fresh = False

        if ftd_dates:
            # check if any FTD within last _FRESH_BD business days
            last_ftd = ftd_dates[-1]
            bd_ago = _bd_since(last_ftd)
            if bd_ago is not None and bd_ago <= 21:   # "fired" = within last 21bd
                fired = True
                since = _iso(last_ftd)
                fresh = bd_ago <= _FRESH_BD

        return {
            "key": key,
            "label_en": label_en,
            "label_zh": label_zh,
            "fired": fired,
            "fresh": fresh,
            "since": since,
            "detail": {
                "last_ftd": _iso(ftd_dates[-1]) if ftd_dates else None,
                "n_ftds_all": len(ftd_dates),
                "note": (
                    "O'Neil FTD: day 4..13 of rally attempt after >=6% drawdown, "
                    "+>=1.2% on higher volume. Lit (QE): ~55% success rate. "
                    "Orthogonal to breadth chips — pure price+volume."
                ),
            },
            "accruing": True,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("c4 ftd failed: %s", e)
        return _absent_chip(key, label_en, label_zh, f"error: {e}")


# ---------------------------------------------------------------------------
# C5 — Retest breadth divergence
# ---------------------------------------------------------------------------

def _c5_retest_divergence(breadth: pd.DataFrame, root: Path | None) -> dict:
    """At a price retest of a prior low: (a) fewer new lows, (b) A/D line higher.
    Two facets, one chip (RRX-R6). SPY close from store.
    """
    key = "retest_divergence"
    label_en = "Retest breadth divergence"
    label_zh = "回踩广度背离"

    try:
        spy = store.read("yahoo", "SPY")
        if spy is None or "close" not in spy.columns:
            return _absent_chip(key, label_en, label_zh, "SPY close unavailable")

        spy_c = spy["close"].dropna().sort_index()
        spy_c.index = pd.to_datetime(spy_c.index)

        b = breadth.copy()
        b.index = pd.to_datetime(b.index)
        b = b.sort_index()

        if not {"nl", "ad_line"}.issubset(b.columns):
            return _absent_chip(key, label_en, label_zh, "nl or ad_line column missing")

        # align on common index
        common = spy_c.index.intersection(b.index)
        if len(common) < 130:
            return _absent_chip(key, label_en, label_zh, "insufficient history after alignment")

        spy_c = spy_c.loc[common]
        nl = b["nl"].loc[common]
        adline = b["ad_line"].loc[common]

        # low2 = min last 15 business days
        low2_val = spy_c.iloc[-15:].min()
        low2_date = spy_c.iloc[-15:].idxmin()

        # low1 = min over [-126, -21]
        w_old = spy_c.iloc[-126:-21]
        if len(w_old) < 10:
            return _absent_chip(key, label_en, label_zh, "insufficient old-window data")
        low1_val = w_old.min()
        low1_date = w_old.idxmin()

        # is it a retest? low2 <= low1 * 1.02 (within 2%) AND max close between lows >= low1 * 1.04
        is_retest = (low2_val <= low1_val * 1.02)
        if is_retest:
            # max close between the two lows
            between_mask = (spy_c.index > low1_date) & (spy_c.index < low2_date)
            between = spy_c[between_mask]
            mid_max = float(between.max()) if len(between) > 0 else low1_val
            is_retest = is_retest and (mid_max >= low1_val * 1.04)

        facet_a = False
        facet_b = False
        facet_detail = {}

        if is_retest:
            # Facet (a): 5d mean nl at low2_date < 0.7 * 5d mean nl at low1_date
            def _mean5nl(idx_target):
                pos = nl.index.searchsorted(idx_target)
                start = max(0, pos - 4)
                return float(nl.iloc[start: pos + 1].mean())

            nl_at_low2 = _mean5nl(low2_date)
            nl_at_low1 = _mean5nl(low1_date)
            if nl_at_low1 > 0:
                facet_a = nl_at_low2 < 0.7 * nl_at_low1
            facet_detail["facet_a"] = {
                "nl_at_low2": round(nl_at_low2, 1),
                "nl_at_low1": round(nl_at_low1, 1),
                "fired": facet_a,
                "desc": "5d mean new-lows at low2 < 70% of 5d mean at low1",
            }

            # Facet (b): A/D line at low2_date > A/D line at low1_date
            def _adline_at(idx_target):
                pos = adline.index.searchsorted(idx_target, side="right") - 1
                return float(adline.iloc[pos]) if 0 <= pos < len(adline) else None

            adl_low2 = _adline_at(low2_date)
            adl_low1 = _adline_at(low1_date)
            if adl_low1 is not None and adl_low2 is not None:
                facet_b = adl_low2 > adl_low1
            facet_detail["facet_b"] = {
                "adline_at_low2": adl_low2,
                "adline_at_low1": adl_low1,
                "fired": facet_b,
                "desc": "A/D line at low2 > A/D line at low1 (higher low)",
            }

        fired = is_retest and (facet_a or facet_b)
        since = _iso(low2_date) if fired else None
        fresh = _is_fresh(low2_date) if fired else False

        # strength: how many facets
        strength = sum([facet_a, facet_b])

        return {
            "key": key,
            "label_en": label_en,
            "label_zh": label_zh,
            "fired": fired,
            "fresh": fresh,
            "since": since,
            "detail": {
                "is_retest": is_retest,
                "low1": {"date": _iso(low1_date), "price": round(float(low1_val), 2)},
                "low2": {"date": _iso(low2_date), "price": round(float(low2_val), 2)},
                "facets": facet_detail,
                "strength": strength,
                "note": (
                    "Retest-conditional (mute in V-bottoms). "
                    "Fires prematurely in grinding bears — grade, don't trust (RRX-R6)."
                ),
            },
            "accruing": True,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("c5 retest_divergence failed: %s", e)
        return _absent_chip(key, label_en, label_zh, f"error: {e}")


# ---------------------------------------------------------------------------
# C6 — VIX term-structure backwardation resolution
# ---------------------------------------------------------------------------

def _c6_vix_term_resolution() -> dict:
    """VIX/VIX3M ratio. Episode: r>1.0 for >=3 consecutive sessions within last 63d.
    Resolution: last 3 sessions all <1.0 after such an episode.
    """
    key = "vix_term_resolution"
    label_en = "VIX backwardation resolved"
    label_zh = "VIX期限倒挂解除"

    try:
        vix = store.read("yahoo", "_VIX")
        vix3m = store.read("yahoo", "_VIX3M")
        if vix is None or vix3m is None:
            return _absent_chip(key, label_en, label_zh, "_VIX or _VIX3M unavailable")

        v = vix["close"].dropna().sort_index()
        v3 = vix3m["close"].dropna().sort_index()
        v.index = pd.to_datetime(v.index)
        v3.index = pd.to_datetime(v3.index)

        common = v.index.intersection(v3.index)
        if len(common) < 70:
            return _absent_chip(key, label_en, label_zh, "insufficient common VIX/VIX3M history")

        v = v.loc[common]
        v3 = v3.loc[common]
        ratio = (v / v3).replace([np.inf, -np.inf], np.nan).dropna()

        if len(ratio) < 70:
            return _absent_chip(key, label_en, label_zh, "ratio series too short")

        today_idx = ratio.index[-1]
        w63_mask = ratio.index >= (today_idx - pd.offsets.BDay(63))
        ratio_63 = ratio[w63_mask]

        # find episode: >=3 consecutive sessions r>1.0 within last 63d
        above1 = (ratio_63 > 1.0).astype(int)
        episode_found = False
        episode_end_pos = None

        for i in range(len(above1) - 2):
            if above1.iloc[i] and above1.iloc[i + 1] and above1.iloc[i + 2]:
                episode_found = True
                # find the end of this run
                j = i + 2
                while j + 1 < len(above1) and above1.iloc[j + 1]:
                    j += 1
                episode_end_pos = j  # last index in ratio_63 that was above 1.0 in this episode

        if not episode_found:
            return {
                "key": key,
                "label_en": label_en,
                "label_zh": label_zh,
                "fired": False,
                "fresh": False,
                "since": None,
                "detail": {
                    "ratio_last": round(float(ratio.iloc[-1]), 3),
                    "episode_found": False,
                    "note": "No backwardation episode (>=3 consecutive r>1.0) in last 63d.",
                },
                "accruing": True,
            }

        # resolution: last 3 sessions all < 1.0 after the episode
        last_3 = ratio.iloc[-3:]
        resolved = bool((last_3 < 1.0).all())

        # check that resolution is after the episode end
        if resolved and episode_end_pos is not None:
            episode_end_date = ratio_63.index[episode_end_pos]
            resolved = resolved and bool(ratio.index[-1] > episode_end_date)

        fired = resolved

        # since = date of first sub-1.0 session after episode
        since = None
        fresh = False
        if fired:
            # find when ratio first fell below 1.0 after the episode
            ep_end_date = ratio_63.index[episode_end_pos]
            after_ep = ratio[ratio.index > ep_end_date]
            below1 = after_ep[after_ep < 1.0]
            if not below1.empty:
                since = _iso(below1.index[0])
                fresh = _is_fresh(ratio.index[-1])  # 3rd sub-1.0 day

        return {
            "key": key,
            "label_en": label_en,
            "label_zh": label_zh,
            "fired": fired,
            "fresh": fresh,
            "since": since,
            "detail": {
                "ratio_last": round(float(ratio.iloc[-1]), 3),
                "episode_found": episode_found,
                "resolved": resolved,
                "note": (
                    "Lit (options.cafe, ~43 episodes): +3.04%/88% at 5d, +4.38%/91% at 21d "
                    "vs +0.26%/60% base. Misses grinding bears (2022). Small-N."
                ),
            },
            "accruing": True,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("c6 vix_term_resolution failed: %s", e)
        return _absent_chip(key, label_en, label_zh, f"error: {e}")


# ---------------------------------------------------------------------------
# C7 — HY-OAS ROC rollover
# ---------------------------------------------------------------------------

def _c7_oas_rollover() -> dict:
    """BAMLH0A0HYM2: 21d ROC percentile. Fired from >= 90th pctile, now rolled down >=0.15
    and <0.75 and < 5 sessions ago.
    """
    key = "oas_rollover"
    label_en = "Credit spread ROC rollover"
    label_zh = "信用利差动量回落"

    try:
        df = store.read("fred", "BAMLH0A0HYM2")
        if df is None or "hy_oas" not in df.columns:
            return _absent_chip(key, label_en, label_zh, "BAMLH0A0HYM2 hy_oas unavailable")

        oas = df["hy_oas"].dropna().sort_index()
        oas.index = pd.to_datetime(oas.index)

        if len(oas) < 530:
            return _absent_chip(key, label_en, label_zh, "hy_oas series too short (<530 rows)")

        roc = oas.diff(21)
        p = pct_rank_window(roc, 504)

        p_now = float(p.iloc[-1])
        if np.isnan(p_now):
            return _absent_chip(key, label_en, label_zh, "pct rank is NaN")

        # max(p over last 63)
        p_63 = p.iloc[-63:]
        p_max = float(p_63.max())

        # p 5 sessions ago
        p_5ago = float(p.iloc[-6]) if len(p) >= 6 else None

        fired = (
            p_max >= 0.90
            and p_now <= p_max - 0.15
            and p_now < 0.75
            and (p_5ago is None or p_now < p_5ago)
        )

        # find the peak date
        peak_date = _iso(p_63.idxmax()) if fired else None

        # since = date when p first fell below the rollover threshold
        since = None
        fresh = False
        if fired:
            # find the date when p_now first rolled below p_max - 0.15 and < 0.75
            rollover_thresh = p_max - 0.15
            rolled = p.iloc[-63:]
            # find the first date after the peak where both conditions met
            peak_pos = p_63.idxmax()
            after_peak = rolled[rolled.index > peak_pos]
            rolled_days = after_peak[(after_peak <= rollover_thresh) & (after_peak < 0.75)]
            if not rolled_days.empty:
                since = _iso(rolled_days.index[0])
                fresh = _is_fresh(rolled_days.index[0])

        return {
            "key": key,
            "label_en": label_en,
            "label_zh": label_zh,
            "fired": fired,
            "fresh": fresh,
            "since": since,
            "detail": {
                "p_now": round(p_now, 3),
                "p_max_63": round(p_max, 3),
                "peak_date": peak_date,
                "p_5ago": round(p_5ago, 3) if p_5ago is not None else None,
                "note": (
                    "Best-positioned chip to earn de-escalation authority (RRX-R7) — "
                    "reuses already-gauntleted series. Failure modes: 2015-16 false peak, "
                    "COVID simultaneity."
                ),
            },
            "accruing": True,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("c7 oas_rollover failed: %s", e)
        return _absent_chip(key, label_en, label_zh, f"error: {e}")


# ---------------------------------------------------------------------------
# C8 — Vol instability VETO (not a confirmation chip)
# ---------------------------------------------------------------------------

def _c8_vol_instability_veto() -> dict:
    """21d rolling std of VIX daily changes. pct_rank_window(504). Veto active if p_now >= 0.80.
    Returns veto dict, not a chip.
    """
    try:
        vix = store.read("yahoo", "_VIX")
        if vix is None or "close" not in vix.columns:
            return {"active": False, "detail": "VIX unavailable — veto inactive"}

        v = vix["close"].dropna().sort_index().astype(float)
        v.index = pd.to_datetime(v.index)

        if len(v) < 530:
            return {"active": False, "detail": "VIX series too short — veto inactive"}

        inst = v.diff().rolling(21, min_periods=10).std()
        p = pct_rank_window(inst, 504)

        p_now = float(p.iloc[-1])
        if np.isnan(p_now):
            return {"active": False, "detail": "pct rank NaN — veto inactive"}

        active = p_now >= 0.80

        return {
            "active": active,
            "p_now": round(p_now, 3),
            "detail": (
                f"VIX 21d realized-vol pctile={p_now:.2f} "
                f"({'vol still erratic — veto active' if active else 'vol stabilizing — veto inactive'})"
            ),
            "label_en": "Vol still unstable",
            "label_zh": "波动仍未稳定",
        }
    except Exception as e:  # noqa: BLE001
        log.debug("c8 vol_instability veto failed: %s", e)
        return {"active": False, "detail": f"error: {e} — veto inactive"}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute(root=None) -> dict:
    """Compute all market-internal confirmation chips + veto.

    Returns:
        {
          asof: ISO date,
          chips: [chip...],           each with key/label_en/label_zh/fired/fresh/since/detail/accruing
          market_confirmed_raw: bool,  (any non-veto chip fresh, ignoring veto)
          market_confirmed: bool,      (market_confirmed_raw AND veto not active)
          n_fresh: int,
          veto: {active, detail, ...},
          note: str,
        }

    Never raises — degrades to all-absent on any failure.
    """
    try:
        today = str(date.today())

        # Load breadth once
        breadth = store.read("breadth", "breadth")
        if breadth is None:
            breadth = pd.DataFrame()

        root_path = None if root is None else Path(root)

        chips = [
            _c1_thrust_confluence(breadth),
            _c2_msi_swing(breadth),
            _c3_washout_thrust20(root_path),
            _c4_ftd(root_path),
            _c5_retest_divergence(breadth, root_path),
            _c6_vix_term_resolution(),
            _c7_oas_rollover(),
        ]

        veto = _c8_vol_instability_veto()
        veto_active = veto.get("active", False)

        n_fresh = sum(1 for c in chips if c.get("fresh"))
        market_confirmed_raw = n_fresh >= 1
        market_confirmed = market_confirmed_raw and not veto_active

        return {
            "asof": today,
            "chips": chips,
            "market_confirmed_raw": market_confirmed_raw,
            "market_confirmed": market_confirmed,
            "n_fresh": n_fresh,
            "veto": veto,
            "note": (
                "Display-only, accruing. Chips forward-graded by engine/risk_radar_recovery_audit.py "
                "on the rebound ruler (RRX-R2). No significance claimed below n>=30 per arm."
            ),
        }
    except Exception as e:  # noqa: BLE001
        log.warning("risk_radar_market_catalysts compute failed: %s", e)
        return {
            "asof": str(date.today()),
            "chips": [],
            "market_confirmed_raw": False,
            "market_confirmed": False,
            "n_fresh": 0,
            "veto": {"active": False, "detail": f"error: {e}"},
            "note": f"compute failed: {e}",
        }
