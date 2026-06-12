"""Alert rules — config-driven, evaluated on the engine's daily output.

Every rule compares today against yesterday (or a trailing window) using the
already-stored regime history and raw series, so alerts fire on *changes*,
never on levels alone. Fired alerts are appended to
data/alerts/alerts_log.parquet keyed by (date, rule) — re-running the same
day is idempotent and cannot double-send.

Severity is informational only ("info" | "warn" | "act"): it orders the
message, it does not gate anything.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)


@dataclass
class Alert:
    rule: str
    severity: str
    message: str


def _regime_history() -> pd.DataFrame | None:
    p = config.data_dir() / "regime" / "regime_history.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def _last_two(df: pd.DataFrame) -> tuple[pd.Series, pd.Series] | None:
    d = df.dropna(subset=["quad"])
    if len(d) < 2:
        return None
    return d.iloc[-2], d.iloc[-1]


# --- individual rules ----------------------------------------------------------

def transition_state_change(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    pair = _last_two(hist)
    if pair is None:
        return None
    prev, cur = pair
    if cur["transition_state"] != prev["transition_state"]:
        sev = {"STABLE": "info", "WEAKENING": "warn",
               "TRANSITIONING": "act", "NEW_REGIME": "act"}.get(cur["transition_state"], "info")
        return Alert("transition_state_change", sev,
                     f"Transition state {prev['transition_state']} -> {cur['transition_state']} "
                     f"({int(cur['n_flags'])} flags active)")
    return None


def axis_confidence_floor(hist: pd.DataFrame, f: pd.DataFrame) -> list[Alert]:
    floor = config.load()["alerts"]["axis_confidence_floor"]
    pair = _last_two(hist)
    if pair is None:
        return []
    prev, cur = pair
    out = []
    for axis in ("growth", "inflation"):
        col = f"{axis}_confidence"
        if prev[col] >= floor > cur[col]:
            out.append(Alert(f"{axis}_confidence_floor", "warn",
                             f"{axis.capitalize()} axis confidence dropped below {floor:.0%}: "
                             f"{prev[col]:.0%} -> {cur[col]:.0%}"))
    return out


def sector_rs_percentile_cross(hist: pd.DataFrame, f: pd.DataFrame) -> list[Alert]:
    acfg = config.load()["alerts"]
    hi, lo = acfg["sector_rs_percentile_hi"], acfg["sector_rs_percentile_lo"]
    from engine.inputs import yahoo_closes
    closes = yahoo_closes()
    bench = config.load()["engine"]["rs_ranking"]["benchmark"]
    sectors = config.load()["yahoo"]["tickers"]["sectors"]
    out = []
    for t in sectors:
        if t not in closes.columns or bench not in closes.columns:
            continue
        rs = (closes[t] / closes[bench]).dropna()
        if len(rs) < 120:
            continue
        pct = rs.rolling(90, min_periods=60).rank(pct=True) * 100
        if len(pct.dropna()) < 2:
            continue
        y, t_ = pct.dropna().iloc[-2], pct.dropna().iloc[-1]
        if y < hi <= t_:
            out.append(Alert("sector_rs_cross_high", "info",
                             f"{t} RS vs {bench} crossed above {hi}th pctile of 90d (now {t_:.0f})"))
        elif y > lo >= t_:
            out.append(Alert("sector_rs_cross_low", "info",
                             f"{t} RS vs {bench} crossed below {lo}th pctile of 90d (now {t_:.0f})"))
    return out


def holdings_active_changes(hist: pd.DataFrame, f: pd.DataFrame) -> list[Alert]:
    from collectors.holdings import active_changes
    hcfg = config.load()["holdings"]
    thresh = hcfg["active_change_alert_pct"]
    out = []
    for ticker in hcfg["watchlist"]:
        ch = active_changes(ticker)
        if ch is None or ch.empty:
            continue
        big = ch[ch["active_chg_pct"].abs() >= thresh].dropna(subset=["active_chg_pct"])
        for pos, row in big.iterrows():
            verb = "added" if row["active_chg_pct"] > 0 else "cut"
            out.append(Alert("holdings_active_change", "info",
                             f"{ticker}: manager {verb} {pos} by {row['active_chg_pct']:+.0f}% "
                             f"of position ({row['window_start']}..{row['window_end']}, "
                             f"flow-normalized)"))
    return out


def net_liquidity_roc_flip(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    if not config.load()["alerts"]["net_liquidity_roc_sign_flip"]:
        return None
    w = config.load()["engine"]["liquidity"]["roc_window_d"]
    roc = (f["net_liquidity_bn"] - f["net_liquidity_bn"].shift(w)).dropna()
    if len(roc) < 2:
        return None
    y, t = roc.iloc[-2], roc.iloc[-1]
    if np.sign(y) != np.sign(t) and t != 0:
        direction = "positive (expanding)" if t > 0 else "negative (contracting)"
        return Alert("net_liquidity_roc_flip", "warn",
                     f"Net liquidity 4-week RoC flipped {direction}: "
                     f"{y:+.0f}bn -> {t:+.0f}bn")
    return None


def hy_oas_widening(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    zmax = config.load()["alerts"]["hy_oas_1d_widening_z"]
    oas = f["hy_oas"].dropna()
    if len(oas) < 260:
        return None
    chg = oas.diff()
    z = (chg.iloc[-1] - chg.rolling(252).mean().iloc[-1]) / chg.rolling(252).std().iloc[-1]
    if z > zmax:
        return Alert("hy_oas_widening", "act",
                     f"HY OAS 1-day widening {chg.iloc[-1]:+.2f}pp is {z:.1f} sigma "
                     f"(level {oas.iloc[-1]:.2f}%)")
    return None


def gex_flip_cross(hist: pd.DataFrame, f: pd.DataFrame) -> Alert | None:
    if not config.load()["alerts"]["gex_flip_cross"]:
        return None
    g = store.read("cboe", "gex")
    if g is None or len(g) < 2:
        return None
    y, t = g.iloc[-2], g.iloc[-1]
    crossed_flip = (pd.notna(y.get("spot_vs_flip_pct")) and pd.notna(t.get("spot_vs_flip_pct"))
                    and np.sign(y["spot_vs_flip_pct"]) != np.sign(t["spot_vs_flip_pct"]))
    sign_change = (pd.notna(y.get("net_gex_bn")) and pd.notna(t.get("net_gex_bn"))
                   and np.sign(y["net_gex_bn"]) != np.sign(t["net_gex_bn"]))
    if crossed_flip or sign_change:
        what = "spot crossed the gamma flip" if crossed_flip else "net GEX changed sign"
        return Alert("gex_flip_cross", "warn",
                     f"GEX: {what} (net {t['net_gex_bn']:+.0f}bn, "
                     f"spot vs flip {t.get('spot_vs_flip_pct', float('nan')):+.1f}%)")
    return None


# --- runner ---------------------------------------------------------------------

def evaluate(f: pd.DataFrame) -> list[Alert]:
    hist = _regime_history()
    if hist is None:
        log.warning("alerts: no regime history yet")
        return []
    alerts: list[Alert] = []
    rules = [transition_state_change, net_liquidity_roc_flip, hy_oas_widening,
             gex_flip_cross]
    multi = [axis_confidence_floor, sector_rs_percentile_cross, holdings_active_changes]
    for rule in rules:
        try:
            a = rule(hist, f)
            if a:
                alerts.append(a)
        except Exception as e:  # noqa: BLE001 — one rule must not kill the rest
            log.error("alert rule %s failed: %s", rule.__name__, e)
    for rule in multi:
        try:
            alerts.extend(rule(hist, f))
        except Exception as e:  # noqa: BLE001
            log.error("alert rule %s failed: %s", rule.__name__, e)
    order = {"act": 0, "warn": 1, "info": 2}
    return sorted(alerts, key=lambda a: order.get(a.severity, 9))


def log_and_dedup(alerts: list[Alert], asof: pd.Timestamp) -> list[Alert]:
    """Append to the alert log; drop alerts already fired for this date."""
    p = config.data_dir() / "alerts" / "alerts_log.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    old = pd.read_parquet(p) if p.exists() else pd.DataFrame(
        columns=["date", "rule", "severity", "message"])
    seen = set(zip(old["date"].astype(str), old["rule"], old["message"]))
    fresh = [a for a in alerts
             if (str(asof.date()), a.rule, a.message) not in seen]
    if fresh:
        new = pd.DataFrame([{"date": str(asof.date()), "rule": a.rule,
                             "severity": a.severity, "message": a.message}
                            for a in fresh])
        pd.concat([old, new], ignore_index=True).to_parquet(p)
    return fresh


def recent_alerts(days: int = 7) -> pd.DataFrame:
    p = config.data_dir() / "alerts" / "alerts_log.parquet"
    if not p.exists():
        return pd.DataFrame(columns=["date", "rule", "severity", "message"])
    df = pd.read_parquet(p)
    cutoff = (pd.Timestamp.today() - pd.Timedelta(days=days)).date()
    return df[pd.to_datetime(df["date"]).dt.date >= cutoff]
