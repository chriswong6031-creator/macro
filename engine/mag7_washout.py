"""Mag-7 washout re-entry gate — BACKGROUND-ONLY context organ (MWR-W0).

Operator-chartered 2026-07-24 as the lawful re-entry path after the forced-call
kill (DO_NOT_REBUILD §2, POSTMORTEM_20260723_MAG7_FORCED_CALL): a new Mag-7
leadership surface may only be PROPOSED after a graded cohort washout-reset.
Construction + grading rules pinned in research/MAG7_WASHOUT_REENTRY_PREREG.md;
phase-0 census in reports/mag7_washout_scan.md (13 S1-A signals 2015→2026,
10 good / 3 bad, all failures in the sustained-2022-bear regime).

DISPLAY-TIER / NO SURFACE: writes data/mag7_washout/latest.json and appends
trigger events to data/mag7_washout/triggers.jsonl (nightly is the sole
advancer — never seeded or advanced by interactive sessions). No template
consumes this artifact; it exists so the gate accrues a forward track record
before any resurface ruling. Deterministic arithmetic only; never fatal.

Sibling organ: engine/index_momentum.py (IHM) already runs an RSI-MACD hybrid
with washout_turn tags on the SAME equal-weight MAG7 carrier at 1D/2B/3B/W-FRI
("indicator only"). MWR does not replace it — it adds the pieces IHM lacks:
the 2W timeframe (the operator's primary washout tool), per-member breadth,
and the gate state machine + trigger ledger. Construction drift guard: both
build the carrier from the same store and the same engine.technicals.rsi.

Indicators (prereg §1): equal-weight daily-rebalanced basket of the 7 members;
Wilder RSI(14) (engine.technicals.rsi == TradingView); Stoch-RSI 14/14/3/3 on
2W bars (anchor A: W-FRI closes at even index from the 2014 series start —
matches the operator's TradingView 2W phase, K≈53 vs our 55 on 2026-07-24);
"RSI-MACD" = MACD(12,26,9) computed ON the RSI(14) series (TH_RSIMACD+ analog).

States (deterministic ladder, de-escalatory wording):
  idle        — nothing washed out (today's tape, 2026-07-24: K≈55, 0/7 members)
  washed_out  — 2W-A K < 20, or ≥4/7 members individually < 20 on 2W-A
  triggered   — washed_out was true within the last three 2W bars AND a bullish
                cross printed (2W Stoch-RSI K over D from <20, or 3D RSI-MACD
                line over signal while line < 0)
Triggers append once per bar-date to triggers.jsonl (dedup by date+tf).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from engine.technicals import rsi
from lib import config

log = logging.getLogger(__name__)

M7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]
SCHEMA = "mag7_washout.v1"

# prereg §1 thresholds — pinned; changing any requires a prereg amendment
WASHOUT_FLOOR = 20.0     # Stoch-RSI K washout line
MEMBER_BREADTH = 4       # ≥N of 7 members < floor = cohort washout
ARMED_LOOKBACK = 3       # 2W bars a washout stays "armed" for a trigger cross


def _ohlcv_root(root: Path | None) -> Path:
    return (root if root is not None else config.data_dir()) / "baskets" / "ohlcv"


def ew_basket(root: Path | None = None) -> pd.Series:
    """Daily-rebalanced equal-weight close index of the 7 members (house form —
    the EW basket, not MAGS: longer history, no ETF-inception truncation)."""
    closes = {}
    for t in M7:
        p = _ohlcv_root(root) / f"{t}.parquet"
        closes[t] = pd.read_parquet(p)["close"]
    px = pd.DataFrame(closes).dropna()
    rets = px.pct_change().dropna()
    return (1 + rets.mean(axis=1)).cumprod().rename("ew")


def two_week_bars(daily: pd.Series) -> pd.Series:
    """Anchor-A 2W bars: W-FRI closes at even index from series start (pinned —
    TV 2W bars are phase-sensitive; anchor B differs by one week)."""
    weekly = daily.resample("W-FRI").last().dropna()
    return weekly.iloc[::2]


def three_day_bars(daily: pd.Series) -> pd.Series:
    """3-trading-day block closes (TV 3D analog)."""
    return daily.iloc[2::3]


def stoch_rsi(close: pd.Series, n_rsi: int = 14, n_st: int = 14,
              k_s: int = 3, d_s: int = 3) -> tuple[pd.Series, pd.Series]:
    r = rsi(close, n_rsi)
    lo, hi = r.rolling(n_st).min(), r.rolling(n_st).max()
    st = (100 * (r - lo) / (hi - lo).replace(0, pd.NA)).astype(float)
    k = st.rolling(k_s).mean()
    return k, k.rolling(d_s).mean()


def rsi_macd(close: pd.Series, n_rsi: int = 14) -> tuple[pd.Series, pd.Series]:
    r = rsi(close, n_rsi)
    line = r.ewm(span=12, min_periods=12).mean() - r.ewm(span=26, min_periods=26).mean()
    return line, line.ewm(span=9, min_periods=9).mean()


def cross_up(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b) & (a.shift() <= b.shift())


def _env_tags(root: Path | None, when: pd.Timestamp) -> dict:
    """Fire-time environment tags for the conditioner hypothesis (prereg §2c —
    operator 2026-07-24: '2022 is a midterm year and was a rate hike year').
    Recorded AT trigger time so phase-1 grading is hindsight-proof. Fail-open:
    absent DFF store → policy tags omitted, midterm flag always present."""
    out: dict = {"midterm_yr": bool(when.year % 4 == 2)}
    try:
        dff = pd.read_parquet(
            (root if root is not None else config.data_dir()) / "fred" / "DFF.parquet"
        ).iloc[:, 0]
        d_bp = float(dff.asof(when)) - float(dff.asof(when - pd.Timedelta(days=182)))
        out["dffr_6m_bp"] = int(round(d_bp * 100))
        out["policy"] = ("hiking" if d_bp >= 0.25 else
                         "cutting" if d_bp <= -0.25 else "flat")
        # Amendment-2 conditioner (operator override 2026-07-24): the failure
        # class is ACCELERATING tightening — trailing-6m ΔFFR still rising vs
        # 91 calendar days ago. Panel evidence: hike_accel median excess −1.02%
        # vs hike_decel +1.98% / cutting +2.44% across 27,647 signals
        # (reports/mwr_phase1_conditioner_study.md; CI includes 0 — disclosed).
        d_prev = (float(dff.asof(when - pd.Timedelta(days=91)))
                  - float(dff.asof(when - pd.Timedelta(days=91 + 182))))
        accel = d_bp - d_prev
        out["regime"] = ("hike_accel" if (d_bp >= 0.25 and accel > 0) else
                         "hike_decel" if d_bp >= 0.25 else
                         "cutting" if d_bp <= -0.25 else "flat")
    except Exception as e:  # noqa: BLE001 — store-optional
        log.debug("mag7_washout env tags unavailable (%s)", e)
    return out


def _members_washed(root: Path | None) -> tuple[int, dict[str, float]]:
    per = {}
    for t in M7:
        try:
            px = pd.read_parquet(_ohlcv_root(root) / f"{t}.parquet")["close"]
            k, _ = stoch_rsi(two_week_bars(px))
            v = float(k.iloc[-1])
            per[t] = round(v, 1)
        except Exception as e:  # noqa: BLE001 — per-member fail-open
            log.warning("mag7_washout member %s failed (%s)", t, e)
            per[t] = None
    n = sum(1 for v in per.values() if v is not None and v < WASHOUT_FLOOR)
    return n, per


def snapshot(root: Path | None = None, write: bool = True) -> dict | None:
    """Compute the washout-gate state; write latest.json + append new triggers.
    root overrides the data dir (tests) — mirrors mag7_regime's convention."""
    try:
        daily = ew_basket(root)
        bars2w = two_week_bars(daily)
        k2, d2 = stoch_rsi(bars2w)
        line3, sig3 = rsi_macd(three_day_bars(daily))
        line1, sig1 = rsi_macd(daily.resample("W-FRI").last().dropna())

        washed_series = (k2 < WASHOUT_FLOOR).fillna(False)
        n_washed, per_member = _members_washed(root)
        basket_washed = bool(washed_series.iloc[-1]) or n_washed >= MEMBER_BREADTH
        armed = bool(washed_series.iloc[-ARMED_LOOKBACK:].any()) or n_washed >= MEMBER_BREADTH

        s1_cross = (cross_up(k2, d2) & (k2.shift() < WASHOUT_FLOOR)).fillna(False)
        s3_cross = (cross_up(line3, sig3) & (line3 < 0)).fillna(False)
        triggers: list[dict] = []
        env = _env_tags(root, daily.index[-1])
        if bool(s1_cross.iloc[-1]):
            triggers.append({"tf": "2W_stochrsi",
                             "date": str(bars2w.index[-1].date()), **env})
        if armed and bool(s3_cross.iloc[-1]):
            triggers.append({"tf": "3D_rsimacd",
                             "date": str(three_day_bars(daily).index[-1].date()), **env})

        state = "triggered" if triggers else ("washed_out" if basket_washed else "idle")
        out = {
            "schema": SCHEMA,
            "as_of": str(daily.index[-1].date()),
            "state": state,
            "basket": {
                "stoch2w_k": round(float(k2.iloc[-1]), 1),
                "stoch2w_d": round(float(d2.iloc[-1]), 1),
                "rsi_macd_1w": {"line": round(float(line1.iloc[-1]), 2),
                                "sig": round(float(sig1.iloc[-1]), 2)},
                "rsi_macd_3d": {"line": round(float(line3.iloc[-1]), 2),
                                "sig": round(float(sig3.iloc[-1]), 2)},
            },
            "members_washed": n_washed,
            "members": per_member,
            "armed": armed,
            "triggers_today": triggers,
            # Amendment 2 (operator override 2026-07-24): Use-B is CONDITIONAL-LIVE —
            # a trigger is actionable ONLY outside the accelerating-tightening regime.
            # regime unknown (no DFF store) → actionable None: operator checks manually.
            "regime": env.get("regime"),
            "gate_actionable": (
                None if (state != "triggered" or env.get("regime") is None)
                else env.get("regime") != "hike_accel"
            ),
            "veto": ("hike_accel" if (state == "triggered"
                                      and env.get("regime") == "hike_accel") else None),
            "note": "MWR Amendment 2 (2026-07-24): conditional-live behind the "
                    "accelerating-tightening veto; §4 kill-switch binding "
                    "(2 consecutive FAILs or −25% adverse → auto-demote)",
        }
        if write:
            base = (root if root is not None else config.data_dir()) / "mag7_washout"
            base.mkdir(parents=True, exist_ok=True)
            (base / "latest.json").write_text(
                json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
            if triggers:
                ledger = base / "triggers.jsonl"
                seen = set()
                if ledger.exists():
                    for ln in ledger.read_text(encoding="utf-8").splitlines():
                        try:
                            row = json.loads(ln)
                            seen.add((row.get("tf"), row.get("date")))
                        except Exception:  # noqa: BLE001
                            pass
                with ledger.open("a", encoding="utf-8") as f:
                    for tr in triggers:
                        if (tr["tf"], tr["date"]) not in seen:
                            f.write(json.dumps({**tr, "as_of": out["as_of"],
                                                "stoch2w_k": out["basket"]["stoch2w_k"]},
                                               ensure_ascii=False) + "\n")
        return out
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("mag7_washout snapshot failed (%s)", e)
        return None
