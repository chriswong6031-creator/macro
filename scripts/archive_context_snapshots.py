"""Append-only archiver of context-regime state into data/signal_archive/context_daily.parquet.

Reads regime/latest.json, market_state/latest.json, and the fear-greed parquet, then
appends one row per calendar date (keep-FIRST — same-day re-runs are a no-op) following
the pattern in engine/signal_archive.py.  Every source is absent-safe: a missing file
yields NaN columns, never a crash.  Running this nightly fixes the P-D5-3 class of
'no PIT context history' problems going forward.

Columns written:
  date, quad, liquidity, cycle_tag, transition_state, regime_confidence,
  market_verdict, market_score, vol_regime_verdict,
  fear_greed_composite,   ← CRYPTO fear/greed (data/sentiment_crypto/fear_greed.parquet)
  fg_dial_us, fg_n_legs, fg_as_of,   ← US fear/greed (site/basketdata/fear_greed.json)
  vix_pctile_252, vix_chg5d_pctile, vvix_vix_ratio, vix9d_vix3m, vol_weather_as_of,
  vix_close, vix1d, dspx, vixeq, cor1m, cor3m,
  rsp_spy_ratio,
  ai_breadth_spread_50, ai_pct50, nonai_pct50, breadth_split_as_of

NOTE on fear_greed naming: `fear_greed_composite` is the CRYPTO sentiment series from
data/sentiment_crypto/ (crypto BTC-derived index).  `fg_dial_us` is the separate US
equity Fear/Greed composite from site/basketdata/fear_greed.json.  These are DIFFERENT
series; do not confuse them despite the shared "fear_greed" branding.

Usage: python -m scripts.archive_context_snapshots
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("archive_context_snapshots")


def _ledger_advance_enabled() -> bool:
    """True only when running in the nightly engine lane.

    Gate: COLLECT_LANE=nightly — the same sentinel set by daily.yml's engine-job
    env.  US_LANE is accepted as a legacy alias.
    """
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"

ARCHIVE_FILE = "context_daily.parquet"

# Freshness window: raw price/vol columns are set to None when the store's last
# index date is older than this many calendar days from the row date.
_RAW_FRESHNESS_DAYS = 7


def _load_json_safe(path: Path) -> dict:
    """Return parsed JSON dict or {} if file missing / unreadable."""
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _read_regime(data_dir: Path) -> dict:
    return _load_json_safe(data_dir / "regime" / "latest.json")


def _read_market_state(data_dir: Path) -> dict:
    return _load_json_safe(data_dir / "market_state" / "latest.json")


def _read_fear_greed(data_dir: Path) -> float | None:
    """Return the latest crypto fear-greed composite value or None if absent.

    WARNING: this reads data/sentiment_crypto/fear_greed.parquet which is the
    CRYPTO (BTC-derived) fear/greed series, NOT the US equity fear/greed.
    The US equity dial is in fg_dial_us (from site/basketdata/fear_greed.json).
    Do not confuse the two despite the shared column prefix.
    """
    p = data_dir / "sentiment_crypto" / "fear_greed.parquet"
    try:
        df = pd.read_parquet(p)
        if df.empty or "fear_greed" not in df.columns:
            return None
        return float(df["fear_greed"].iloc[-1])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# New Vol-Suppression / Bifurcation readers (VSB W2)
# ---------------------------------------------------------------------------

def _read_fg_us(root: Path) -> dict:
    """Read US equity Fear/Greed from site/basketdata/fear_greed.json.

    Returns keys: fg_dial_us, fg_n_legs, fg_as_of.
    All None if file absent or malformed.

    NOTE: this is the US equity composite; fear_greed_composite in this same
    row is the CRYPTO series — see module docstring for the naming trap.
    """
    p = root / "site" / "basketdata" / "fear_greed.json"
    out: dict = {"fg_dial_us": None, "fg_n_legs": None, "fg_as_of": None}
    try:
        d = json.loads(p.read_text())
        raw_dial = d.get("dial")
        out["fg_dial_us"] = int(raw_dial) if raw_dial is not None else None
        raw_n = d.get("n_legs_qualifying")
        out["fg_n_legs"] = int(raw_n) if raw_n is not None else None
        out["fg_as_of"] = d.get("as_of")
    except Exception:
        pass
    return out


def _read_vol_weather(root: Path) -> dict:
    """Read vol-weather chips from site/basketdata/vol_weather.json (sibling PR).

    Chips list: keyed by 'key' in ['vix_level', 'vix_velocity', 'vvix_vix', 'term_slope'].
    Returns: vix_pctile_252, vix_chg5d_pctile, vvix_vix_ratio, vix9d_vix3m, vol_weather_as_of.
    All None if file absent or malformed.
    """
    p = root / "site" / "basketdata" / "vol_weather.json"
    out: dict = {
        "vix_pctile_252": None, "vix_chg5d_pctile": None,
        "vvix_vix_ratio": None, "vix9d_vix3m": None, "vol_weather_as_of": None,
    }
    try:
        d = json.loads(p.read_text())
        chips = d.get("chips") or []
        # Index chips by key
        by_key: dict[str, dict] = {}
        for chip in chips:
            k = chip.get("key")
            if k:
                by_key[k] = chip
        if "vix_level" in by_key:
            out["vix_pctile_252"] = by_key["vix_level"].get("pctile")
        if "vix_velocity" in by_key:
            out["vix_chg5d_pctile"] = by_key["vix_velocity"].get("pctile")
        if "vvix_vix" in by_key:
            out["vvix_vix_ratio"] = by_key["vvix_vix"].get("value")
        if "term_slope" in by_key:
            out["vix9d_vix3m"] = by_key["term_slope"].get("value")
        out["vol_weather_as_of"] = d.get("as_of")
    except Exception:
        pass
    return out


def _stale_cutoff(last_idx_date: pd.Timestamp | None, row_date: str,
                  days: int = _RAW_FRESHNESS_DAYS) -> bool:
    """True if last_idx_date is more than `days` calendar days before row_date.

    A frozen feed must record None, not a stale echo — this enforces that.
    """
    if last_idx_date is None:
        return True
    try:
        rd = pd.Timestamp(row_date)
        return (rd - pd.Timestamp(last_idx_date)).days > days
    except Exception:
        return True


def _last_close_cboe(name: str, data_dir: Path, row_date: str) -> float | None:
    """Read last 'close' from data/cboe/<name>.parquet with freshness gate.

    Returns None if file absent, column missing, or last date is stale.
    Uses pd.read_parquet directly because these are small files written by
    collectors/cboe.py (PR #2528) and are NOT in the lib.store namespace.
    """
    p = data_dir / "cboe" / f"{name}.parquet"
    try:
        df = pd.read_parquet(p)
        if df.empty or "close" not in df.columns:
            return None
        c = df["close"].dropna()
        if c.empty:
            return None
        if _stale_cutoff(c.index[-1], row_date):
            log.debug("cboe/%s stale (last=%s row_date=%s) — recording None", name, c.index[-1], row_date)
            return None
        return float(c.iloc[-1])
    except Exception:
        return None


def _read_raw_vol(row_date: str) -> dict:
    """Read raw last-close values for VIX and CBOE vol derivatives.

    vix_close: from store.read('yahoo', '_VIX')['close']
    vix1d, dspx, vixeq, cor1m, cor3m: from data/cboe/<name>.parquet['close']

    Per doctrine (RRX-R10): these are raw levels for PIT archival only, never
    used as absolute thresholds in any signal; relative/percentile constructions
    are the responsibility of the consuming analysis layer.

    All values subject to 7-day freshness cutoff: stale feed -> None.
    """
    out: dict = {
        "vix_close": None, "vix1d": None, "dspx": None,
        "vixeq": None, "cor1m": None, "cor3m": None,
    }
    # vix_close via store API (yahoo group)
    try:
        vix_df = store.read("yahoo", "_VIX")
        if vix_df is not None and "close" in vix_df.columns:
            c = vix_df["close"].dropna()
            if not c.empty and not _stale_cutoff(c.index[-1], row_date):
                out["vix_close"] = float(c.iloc[-1])
    except Exception:
        pass

    data_dir_path = config.data_dir()
    # CBOE derivatives via direct parquet read (not in store namespace)
    for key in ("vix1d", "dspx", "vixeq", "cor1m", "cor3m"):
        out[key] = _last_close_cboe(key, data_dir_path, row_date)

    return out


def _read_rsp_spy_ratio(row_date: str) -> float | None:
    """Compute RSP/SPY last-close ratio (equal-weight vs cap-weight breadth).

    Reads store.read('yahoo', 'RSP') and store.read('yahoo', 'SPY').
    Returns ratio at the last common date, or None if either absent/stale.
    """
    try:
        rsp_df = store.read("yahoo", "RSP")
        spy_df = store.read("yahoo", "SPY")
        if rsp_df is None or spy_df is None:
            return None
        if "close" not in rsp_df.columns or "close" not in spy_df.columns:
            return None
        rsp_c = rsp_df["close"].dropna()
        spy_c = spy_df["close"].dropna()
        if rsp_c.empty or spy_c.empty:
            return None
        # Align on common dates
        common_rsp, common_spy = rsp_c.align(spy_c, join="inner")
        if common_rsp.empty:
            return None
        last_date = common_rsp.index[-1]
        if _stale_cutoff(last_date, row_date):
            log.debug("rsp_spy_ratio stale (last=%s row_date=%s) — recording None", last_date, row_date)
            return None
        return float(common_rsp.iloc[-1] / common_spy.iloc[-1])
    except Exception:
        return None


def _read_breadth_split(root: Path) -> dict:
    """Read AI/non-AI breadth split from site/basketdata/breadth_split.json (sibling PR).

    Returns: ai_breadth_spread_50, ai_pct50, nonai_pct50, breadth_split_as_of.
    All None if file absent or malformed.
    """
    p = root / "site" / "basketdata" / "breadth_split.json"
    out: dict = {
        "ai_breadth_spread_50": None, "ai_pct50": None,
        "nonai_pct50": None, "breadth_split_as_of": None,
    }
    try:
        d = json.loads(p.read_text())
        latest = d.get("latest") or {}
        spread = latest.get("spread_50")
        out["ai_breadth_spread_50"] = float(spread) if spread is not None else None
        ai = latest.get("ai_pct50")
        out["ai_pct50"] = float(ai) if ai is not None else None
        nonai = latest.get("nonai_pct50")
        out["nonai_pct50"] = float(nonai) if nonai is not None else None
        out["breadth_split_as_of"] = d.get("as_of")
    except Exception:
        pass
    return out


def _build_row(regime: dict, ms: dict, fear_greed: float | None,
               fg_us: dict | None = None, vol_weather: dict | None = None,
               raw_vol: dict | None = None, rsp_spy_ratio: float | None = None,
               breadth_split: dict | None = None) -> dict:
    """Flatten the sources into the flat schema row."""
    vol = regime.get("vol_regime") or {}
    date_val = regime.get("date") or regime.get("asof") or datetime.now(timezone.utc).date().isoformat()
    row: dict = {
        "date": str(date_val)[:10],
        "quad": regime.get("quad"),
        "liquidity": regime.get("liquidity_overlay"),
        "cycle_tag": regime.get("cycle_tag"),
        "transition_state": regime.get("transition_state"),
        "regime_confidence": regime.get("confidence"),
        "market_verdict": ms.get("verdict") if ms else None,
        "market_score": ms.get("score") if ms else None,
        "vol_regime_verdict": vol.get("regime") if isinstance(vol, dict) else None,
        # CRYPTO fear/greed (data/sentiment_crypto/) — see naming-trap note in docstring
        "fear_greed_composite": fear_greed,
    }
    # US Fear/Greed from site/basketdata/fear_greed.json
    if fg_us:
        row.update(fg_us)
    else:
        row.update({"fg_dial_us": None, "fg_n_legs": None, "fg_as_of": None})
    # Vol weather from site/basketdata/vol_weather.json (sibling PR artifact)
    if vol_weather:
        row.update(vol_weather)
    else:
        row.update({
            "vix_pctile_252": None, "vix_chg5d_pctile": None,
            "vvix_vix_ratio": None, "vix9d_vix3m": None, "vol_weather_as_of": None,
        })
    # Raw vol closes with freshness gate
    if raw_vol:
        row.update(raw_vol)
    else:
        row.update({
            "vix_close": None, "vix1d": None, "dspx": None,
            "vixeq": None, "cor1m": None, "cor3m": None,
        })
    row["rsp_spy_ratio"] = rsp_spy_ratio
    # AI/non-AI breadth split from site/basketdata/breadth_split.json (sibling PR)
    if breadth_split:
        row.update(breadth_split)
    else:
        row.update({
            "ai_breadth_spread_50": None, "ai_pct50": None,
            "nonai_pct50": None, "breadth_split_as_of": None,
        })
    return row


def _append(archive_path: Path, row: dict) -> bool:
    """Append row to archive, keep-FIRST per date. Returns True if written.

    Gated by COLLECT_LANE=nightly: no-ops outside the nightly lane.
    """
    date = row["date"]
    if not date:
        log.warning("no date resolved — skipping")
        return False
    old = pd.read_parquet(archive_path) if archive_path.exists() else None
    if old is not None and "date" in old.columns and date in set(old["date"].astype(str)):
        log.info("context_daily — already logged for %s (keep-first)", date)
        return False
    if not _ledger_advance_enabled():
        log.debug(
            "archive_context_snapshots._append: write skipped for date=%s "
            "(COLLECT_LANE != nightly)",
            date,
        )
        return False
    logged_at = datetime.now(timezone.utc).isoformat()
    new_row = {"logged_at": logged_at, **row}
    merged = pd.concat([old, pd.DataFrame([new_row])], ignore_index=True) \
        if old is not None else pd.DataFrame([new_row])
    merged.to_parquet(archive_path, index=False)
    log.info("context_daily — logged %s", date)
    return True


def main() -> int:
    data_dir = config.data_dir()
    root = config.ROOT
    archive_dir = data_dir / "signal_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / ARCHIVE_FILE

    regime = _read_regime(data_dir)
    ms = _read_market_state(data_dir)
    fear_greed = _read_fear_greed(data_dir)

    # Resolve the row date early so raw readers can apply freshness cutoffs
    date_val = (regime.get("date") or regime.get("asof")
                or datetime.now(timezone.utc).date().isoformat())
    row_date = str(date_val)[:10]

    fg_us = _read_fg_us(root)
    vol_weather = _read_vol_weather(root)
    raw_vol = _read_raw_vol(row_date)
    rsp_spy = _read_rsp_spy_ratio(row_date)
    breadth_split = _read_breadth_split(root)

    row = _build_row(regime, ms, fear_greed,
                     fg_us=fg_us, vol_weather=vol_weather,
                     raw_vol=raw_vol, rsp_spy_ratio=rsp_spy,
                     breadth_split=breadth_split)
    _append(archive_path, row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
