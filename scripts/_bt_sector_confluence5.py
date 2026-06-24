"""Phase-5 — MTF (daily early-trigger + 3-day confirm). The user's own examples
(XLI 'stoch 100->91 after a 3% drop', XLB 'down 6 straight days') are DAILY
observations a pure-3D engine misses. Test whether a DAILY early-topping rule
(extended + momentum rolling, before the confirmed cross) has predictive power,
and whether daily+3D agreement sharpens the BUY.

Run: python3 -m scripts._bt_sector_confluence5
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.cycles import macd_parts, stoch_rsi
from engine.technicals import rsi
from scripts._bt_sector_confluence import _load, _to_3b, _signals_3b, SECTORS, BENCH, HORIZONS


def _daily_sigs(daily: pd.Series) -> pd.DataFrame:
    m = macd_parts(daily); h = m["hist"]; s = stoch_rsi(daily); r = rsi(daily, 14)
    prior_le0 = (h.shift(1) <= 0) | (h.shift(2) <= 0) | (h.shift(3) <= 0)
    prior_ge0 = (h.shift(1) >= 0) | (h.shift(2) >= 0) | (h.shift(3) >= 0)
    macd_up = (h > 0) & prior_le0
    macd_dn = (h < 0) & prior_ge0
    prior_s_lt20 = (s.shift(1) < 20) | (s.shift(2) < 20) | (s.shift(3) < 20)
    prior_s_gt80 = (s.shift(1) > 80) | (s.shift(2) > 80) | (s.shift(3) > 80)
    stoch_up = (s >= 20) & prior_s_lt20
    stoch_dn = (s <= 80) & prior_s_gt80
    rising = (h > h.shift(1)) & (h.shift(1) > h.shift(2))
    falling = (h < h.shift(1)) & (h.shift(1) < h.shift(2))
    # early topping: stoch turning down from >80 OR rsi turning down from >70
    stoch_roll = (s < s.shift(1)) & ((s.shift(1) > 80) | (s.shift(2) > 80))
    rsi_roll = (r < r.shift(1)) & ((r.shift(1) > 70) | (r.shift(2) > 70))
    return pd.DataFrame({
        "d_rsi": r, "d_stoch": s,
        "d_macd_up": macd_up.fillna(False), "d_macd_dn": macd_dn.fillna(False),
        "d_stoch_up": stoch_up.fillna(False), "d_stoch_dn": stoch_dn.fillna(False),
        "d_setup_up": ((h < 0) & rising).fillna(False),
        "d_setup_dn": ((h > 0) & falling).fillna(False),
        "d_stoch_roll": stoch_roll.fillna(False), "d_rsi_roll": rsi_roll.fillna(False),
    })


def _enrich_mtf(t: str, spy: pd.Series) -> pd.DataFrame:
    daily = _load(t)
    s3 = _to_3b(daily)
    sig3 = _signals_3b(s3["close"])
    dsig = _daily_sigs(daily)
    # 3D state reindexed to daily (ffill), so we can read it on every daily date
    s3_daily = sig3.reindex(daily.index, method="ffill")
    df = dsig.copy()
    for c in ["macd_up", "macd_dn", "stoch_up", "stoch_dn", "setup_up", "setup_dn"]:
        df[f"t3_{c}"] = s3_daily[c].fillna(False).values
    sma200 = daily.rolling(200).mean()
    df["above200"] = (daily > sma200).fillna(False).values
    df["close"] = daily.values
    df["ticker"] = t
    didx = daily.index
    for h in HORIZONS:
        fwd = daily.shift(-h) / daily - 1
        spy_fwd = (spy.reindex(didx).shift(-h) / spy.reindex(didx) - 1)
        df[f"fwd{h}"] = fwd.values
        df[f"exc{h}"] = (fwd - spy_fwd).values
    df.index = didx
    return df


def _stat(sub: pd.DataFrame, col="exc63") -> tuple:
    e = sub[col].dropna() * 100
    if len(e) < 20:
        return (len(e), np.nan, np.nan)
    return (len(e), round(e.mean(), 2), round(100 * (e > 0).mean(), 0))


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    spy = _load(BENCH)
    R = pd.concat([_enrich_mtf(t, spy) for t in SECTORS])
    ext = (R["d_rsi"] > 70) | (R["d_stoch"] > 80)

    print("=" * 95)
    print("EARLY TOPPING on the DAILY (want NEGATIVE exc) — fires before the confirmed 3D cross")
    print("=" * 95)
    for lbl, m in [
        ("daily extended alone", ext),
        ("ext & daily stoch_roll (down from >80)", ext & R["d_stoch_roll"]),
        ("ext & daily rsi_roll (down from >70)", ext & R["d_rsi_roll"]),
        ("ext & (stoch_roll | rsi_roll | setup_dn)", ext & (R["d_stoch_roll"] | R["d_rsi_roll"] | R["d_setup_dn"])),
        ("ext & daily down-cross (macd|stoch dn)", ext & (R["d_macd_dn"] | R["d_stoch_dn"])),
        ("ext & 3D down-cross/setup_dn (confirmed)", ext & (R["t3_macd_dn"] | R["t3_stoch_dn"] | R["t3_setup_dn"])),
        ("ext & daily-roll & 3D rolling too (MTF)", ext & (R["d_stoch_roll"] | R["d_rsi_roll"]) & (R["t3_setup_dn"] | R["t3_macd_dn"] | R["t3_stoch_dn"])),
    ]:
        n, m21, _ = _stat(R[m], "exc21"); n2, m63, h63 = _stat(R[m], "exc63")
        print(f"  {lbl:46s} n={n:6d}  exc21={m21}  exc63={m63}  hit63={h63}")

    print("\n" + "=" * 95)
    print("BUY: daily early-trigger vs 3D-confirmed vs MTF agreement (want POSITIVE exc, above200)")
    print("=" * 95)
    a = R[R["above200"]]
    not_ext = a["d_rsi"] < 65
    for lbl, m in [
        ("daily fresh-up (setup|cross) only", (a["d_setup_up"] | a["d_macd_up"] | a["d_stoch_up"]) & not_ext),
        ("3D fresh-up only", (a["t3_setup_up"] | a["t3_macd_up"] | a["t3_stoch_up"]) & not_ext),
        ("daily fresh-up & 3D fresh-up (MTF agree)", (a["d_setup_up"] | a["d_macd_up"] | a["d_stoch_up"]) & (a["t3_setup_up"] | a["t3_macd_up"] | a["t3_stoch_up"]) & not_ext),
        ("daily fresh-up & 3D not rolling-over", (a["d_setup_up"] | a["d_macd_up"] | a["d_stoch_up"]) & ~(a["t3_setup_dn"] | a["t3_macd_dn"]) & not_ext),
    ]:
        n, m21, _ = _stat(a[m], "exc21"); n2, m63, h63 = _stat(a[m], "exc63")
        print(f"  {lbl:46s} n={n:6d}  exc21={m21}  exc63={m63}  hit63={h63}")

    # re-read XLI/XLB/XLF NOW with the MTF early rule
    print("\n" + "=" * 95)
    print("LIVE re-read with daily early-warning — XLI/XLB should now flag topping")
    print("=" * 95)
    for t in ["XLI", "XLB", "XLF", "XLV", "XLK"]:
        last = R[R["ticker"] == t].iloc[-1]
        e = (last["d_rsi"] > 70) or (last["d_stoch"] > 80)
        early_top = e and (last["d_stoch_roll"] or last["d_rsi_roll"] or last["d_setup_dn"])
        print(f"  {t}: d_rsi={last['d_rsi']:.0f} d_stoch={last['d_stoch']:.0f} ext={e} "
              f"stoch_roll={last['d_stoch_roll']} rsi_roll={last['d_rsi_roll']} setup_dn={last['d_setup_dn']} "
              f"-> EARLY_TOP={early_top}")
