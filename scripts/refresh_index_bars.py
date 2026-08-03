#!/usr/bin/env python3
"""scripts/refresh_index_bars.py — daily OHLC bars for the index grading lane (R2.4b).

WHY: the levels grading lane grades boards against next-session high/low/close, and
``data/stocks`` (the only US store with high/low) carries no ETF/index bars — so
SPY/QQQ/IWM/DIA/SPX/SPXW had zero graded boards. This script keeps a tiny dedicated
store at ``data/levels/index_bars/{ROOT}.parquet`` in the exact ``data/stocks`` schema
(DatetimeIndex named Date; float64 open/close/high/low/volume) so
``build_levels_track_record --universe index`` can grade the anchor roots.

SOURCE: yfinance, ``auto_adjust=True`` — the ADJUSTED basis, same as ``data/stocks``.
The track-record driver rebases each RAW greeks board onto the adjusted bar basis
(``_rebase_to_adjusted``), so basis consistency is what matters, not rawness. SPX and
SPXW both grade against ^GSPC (the S&P 500 index itself; indices have no dividend/split
adjustments, so adjusted == raw there).

WRITE DISCIPLINE: full-history pull each run (period="max" is a few thousand rows per
symbol — cheap), atomic tmp+replace, and a fetch failure NEVER blanks a prior parquet:
the old file simply stays and tonight's grading uses it. Exit 0 if at least one symbol
refreshed; 1 only when everything failed AND nothing usable exists on disk.

Usage: python -m scripts.refresh_index_bars
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from lib.config import data_dir  # noqa: E402

log = logging.getLogger("refresh_index_bars")

BARS_DIR = Path(data_dir()) / "levels" / "index_bars"
#: store file → Yahoo symbol. SPXW aliases to SPX at LOAD time in the driver, so no file here.
SYMBOLS: dict[str, str] = {
    "SPY": "SPY", "QQQ": "QQQ", "IWM": "IWM", "DIA": "DIA", "SPX": "^GSPC",
}
_REN = {"Open": "open", "Close": "close", "High": "high", "Low": "low", "Volume": "volume"}
_MIN_ROWS = 250  # a "full history" pull with under a year of rows is a bad response


def _fetch(yahoo_sym: str) -> pd.DataFrame | None:
    import yfinance as yf  # noqa: PLC0415 — keep import cost out of --help / tests
    try:
        df = yf.download(yahoo_sym, period="max", auto_adjust=True,
                         progress=False, group_by="column", threads=False)
    except Exception as e:  # noqa: BLE001
        log.warning("%s: yfinance failed — %s", yahoo_sym, e)
        return None
    if df is None or df.empty:
        log.warning("%s: empty yfinance response", yahoo_sym)
        return None
    if isinstance(df.columns, pd.MultiIndex):  # single-symbol pulls can still nest
        df.columns = df.columns.get_level_values(0)
    cols = [c for c in ("Open", "Close", "High", "Low", "Volume") if c in df.columns]
    if "Close" not in cols or "High" not in cols or "Low" not in cols:
        log.warning("%s: response missing OHLC columns (%s)", yahoo_sym, list(df.columns))
        return None
    out = df[cols].rename(columns=_REN).dropna(subset=["close"]).astype("float64")
    out.index = pd.to_datetime(out.index).tz_localize(None)
    out.index.name = "Date"
    if len(out) < _MIN_ROWS:
        log.warning("%s: only %d rows on a period=max pull — refusing to overwrite",
                    yahoo_sym, len(out))
        return None
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    BARS_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for root, ysym in SYMBOLS.items():
        df = _fetch(ysym)
        target = BARS_DIR / f"{root}.parquet"
        if df is None:
            log.info("%s: kept prior store (%s)", root,
                     "present" if target.exists() else "ABSENT — root ungradeable tonight")
            continue
        tmp = target.with_suffix(".tmp.parquet")
        df.to_parquet(tmp)
        tmp.replace(target)
        ok += 1
        log.info("%s: %d bars %s → %s", root, len(df),
                 df.index[-1].strftime("%Y-%m-%d"), target)
    if ok:
        return 0
    # nothing refreshed — still fine if every root has a prior store to grade against
    have = sum(1 for r in SYMBOLS if (BARS_DIR / f"{r}.parquet").exists())
    log.error("no symbol refreshed (%d/%d prior stores on disk)", have, len(SYMBOLS))
    return 0 if have == len(SYMBOLS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
