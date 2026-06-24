"""Sanity-check the locked confluence rules against the user's OWN live calls:
  * XLI: 'STOCH RSI 100 last week, 91 this week after a 3% drop' -> should read TOP/AVOID
  * XLB: 'topped ~a week ago at 53, now 51, down 6 straight days' -> TOP/AVOID
  * XLF: 'in uptrend since Apr 1 2026'                            -> healthy / no top
Run: python3 -m scripts._bt_sector_confluence_now
"""
from __future__ import annotations

import pandas as pd

from scripts._bt_sector_confluence import _load, _to_3b, _signals_3b, SECTORS


def read_now(t: str) -> dict:
    daily = _load(t)
    s3 = _to_3b(daily)
    sig = _signals_3b(s3["close"]).iloc[-1]
    sma200 = daily.rolling(200).mean().iloc[-1]
    sma50 = daily.rolling(50).mean().iloc[-1]
    px = daily.iloc[-1]
    ext = (sig["rsi14"] > 70) or (sig["stoch"] > 80)
    buy = (sig["setup_up"] or sig["macd_up"] or sig["stoch_up"]) and px > sma200 and sig["rsi14"] < 65
    avoid = (sig["macd_dn"] or sig["stoch_dn"] or sig["setup_dn"]) and ext
    if avoid and not buy:
        verdict = "AVOID/TOP"
    elif buy and not avoid:
        verdict = "BUY/SETUP"
    else:
        verdict = "neutral"
    return {"t": t, "px": round(px, 2), ">200d": px > sma200, ">50d": px > sma50,
            "rsi3D": sig["rsi14"], "stoch3D": sig["stoch"],
            "macd_up": sig["macd_up"], "macd_dn": sig["macd_dn"],
            "stoch_up": sig["stoch_up"], "stoch_dn": sig["stoch_dn"],
            "setup_up": sig["setup_up"], "setup_dn": sig["setup_dn"],
            "ext": ext, "VERDICT": verdict}


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    rows = [read_now(t) for t in SECTORS]
    df = pd.DataFrame(rows).set_index("t")
    print(df.to_string())
    print("\nUser's cited calls — XLI/XLB should be AVOID/TOP, XLF healthy:")
    for t in ["XLI", "XLB", "XLF"]:
        print(f"  {t}: {df.loc[t, 'VERDICT']}  (rsi3D={df.loc[t,'rsi3D']}, stoch3D={df.loc[t,'stoch3D']}, "
              f"dn-cross={df.loc[t,'macd_dn'] or df.loc[t,'stoch_dn']}, setup_dn={df.loc[t,'setup_dn']})")
