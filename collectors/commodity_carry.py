"""Commodity roll-yield (carry / term-structure) collector.

Backwardation (the front contract priced ABOVE deferred months) earns a positive
roll yield as a long position rolls up the curve; contango bleeds. Roll yield is
the dominant driver of long-run commodity total returns (research/
QUANT_FACTOR_EXPANSION.md). Yahoo exposes individual DATED futures contracts
(CLN26.NYM, GCQ26.CMX, ...), so we fetch the nearest several per commodity and
reconstruct a continuous FRONT-vs-SECOND annualized roll yield: at each date the
two nearest not-yet-expired contracts define the slope.

Stored as a daily series per asset under data/commodity_carry/. The fetch is
cached weekly (the curve shape is slow); each row carries roll_yield_ann plus the
front/second contract prices and symbols for transparency.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

_MONTH_CODE = "FGHJKMNQUVXZ"      # Jan..Dec CME month letters


def _cfg() -> dict:
    return config.load()["commodities"]["carry"]


def _enumerate_symbols(root: str, suffix: str, back: int, fwd: int) -> list[tuple[str, int, int]]:
    """(symbol, year, month) for each calendar month in the window. Uses a fixed
    reference month so it is deterministic (Date.now is unavailable in some run
    contexts); the engine drops months whose contract returns no data."""
    # reference = latest stored CL=F date's month, else fall back to the file's notion
    from lib import store
    ref = store.read("yahoo", "CL_F")
    base = ref.index.max() if ref is not None and not ref.empty else pd.Timestamp("2026-06-01")
    y, m = base.year, base.month
    out = []
    for off in range(-back, fwd + 1):
        mm = m + off
        yy = y + (mm - 1) // 12
        mc = (mm - 1) % 12               # 0-based month index
        sym = f"{root}{_MONTH_CODE[mc]}{yy % 100:02d}{suffix}"
        out.append((sym, yy, mc + 1))
    return out


def _fetch_contract(sym: str) -> pd.Series | None:
    import yfinance as yf
    try:
        h = yf.Ticker(sym).history(period="2y", auto_adjust=False)
        if h is None or h.empty or "Close" not in h:
            return None
        s = h["Close"].dropna()
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        return s if len(s) >= 20 else None
    except Exception as e:  # noqa: BLE001 — non-active months simply return nothing
        log.debug("carry contract %s failed: %s", sym, e)
        return None


def _reconstruct(asset_contracts: list[tuple[int, int, pd.Series]], history_d: int) -> pd.DataFrame:
    """Continuous front/second roll yield from the fetched dated contracts. Each
    contract's last data date approximates its expiry; at each date the two
    nearest non-expired contracts give the slope."""
    if len(asset_contracts) < 2:
        return pd.DataFrame()
    # delivery ordinal + (first,last) span per contract
    contracts = []
    for yy, mm, s in asset_contracts:
        contracts.append({"deliv": yy * 12 + mm, "first": s.index.min(),
                          "last": s.index.max(), "s": s,
                          "sym_deliv": (yy, mm)})
    idx = pd.bdate_range(
        max(c["first"] for c in contracts), max(c["last"] for c in contracts))
    idx = idx[-history_d:]
    rows = []
    for t in idx:
        active = sorted([c for c in contracts if c["first"] <= t <= c["last"]],
                        key=lambda c: c["deliv"])
        if len(active) < 2:
            continue
        f, sec = active[0], active[1]
        fv = f["s"].asof(t)
        sv = sec["s"].asof(t)
        if pd.isna(fv) or pd.isna(sv) or sv <= 0:
            continue
        gap = max(1, sec["deliv"] - f["deliv"])     # months between front & second
        roll_ann = (fv / sv - 1.0) * 12.0 / gap
        rows.append({"date": t, "front": fv, "second": sv,
                     "roll_yield_ann": roll_ann, "gap_months": gap})
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()


def fetch_carry(force: bool = False, max_age_days: int = 7) -> dict[str, pd.DataFrame]:
    cfg = _cfg()
    cdir = config.data_dir() / "commodity_carry"
    cdir.mkdir(parents=True, exist_ok=True)
    meta = cdir / "_meta.json"
    if not force and meta.exists():
        try:
            built = datetime.fromisoformat(json.loads(meta.read_text())["built"])
            if (datetime.now(timezone.utc) - built).total_seconds() / 86400.0 < max_age_days:
                log.info("carry cache fresh — skip fetch")
                return {a: pd.read_parquet(cdir / f"{a}.parquet")
                        for a in cfg["contracts"] if (cdir / f"{a}.parquet").exists()}
        except Exception:  # noqa: BLE001
            pass

    out: dict[str, pd.DataFrame] = {}
    for asset, (root, suffix) in cfg["contracts"].items():
        fetched = []
        for sym, yy, mm in _enumerate_symbols(root, suffix, cfg["months_back"], cfg["months_fwd"]):
            s = _fetch_contract(sym)
            if s is not None:
                fetched.append((yy, mm, s))
        df = _reconstruct(fetched, cfg["history_d"])
        if not df.empty:
            df.to_parquet(cdir / f"{asset}.parquet")
            out[asset] = df
            log.info("carry %s: %d rows, latest roll %.1f%%/yr (%d contracts)",
                     asset, len(df), df["roll_yield_ann"].iloc[-1] * 100, len(fetched))
        else:
            log.warning("carry %s: no reconstruction (%d contracts)", asset, len(fetched))
    meta.write_text(json.dumps({"built": datetime.now(timezone.utc).isoformat(),
                                "assets": list(out)}))
    return out
