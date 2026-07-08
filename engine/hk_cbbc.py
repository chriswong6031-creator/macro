"""HK CBBC / Warrant Leverage Map engine — display-tier context organ.

Surfaces HK's most distinctive microstructure: retail-leverage froth and
issuer-hedging "magnet" zones. Dense outstanding CBBC call levels near spot =
forced-sell cascade risk when spot touches the mandatory call price.

DISPLAY-ONLY. No buy/sell signals; no scoring. "Magnet" and "froth" are
descriptive labels — they accrue context, not edges.

Outputs (per bellwether underlying):
  bull_bear_ratio         — outstanding bull CBBC / outstanding bear CBBC
                            (>1 = retail positioning skewed bull; descriptive)
  bull_outstanding        — total bull CBBC outstanding (contracts)
  bear_outstanding        — total bear CBBC outstanding (contracts)
  total_outstanding       — bull + bear total
  leverage_state          — descriptive label (see _LEVERAGE_STATES)
  data_note               — honest caveat string (e.g. "call level not available")

Bellwether universe (matches adr_bridge):
  9988.HK  Alibaba / 阿里巴巴
  0700.HK  Tencent / 腾讯
  3690.HK  Meituan / 美团
  9618.HK  JD.com  / 京东
  1810.HK  Xiaomi  / 小米
  9888.HK  Baidu   / 百度
  1024.HK  Kuaishou / 快手
  0981.HK  SMIC    / 中芯国际
  HSI      Hang Seng Index (index CBBCs)
  HSTECH   Hang Seng Tech Index (index CBBCs)

Freshness: degrades visibly (banner + null fields) when the store is missing
or stale. Never raises; never crashes the nightly render.

Forward ledger: data/hk_impulse/cbbc_ledger.jsonl
  One row per (date, underlying) when CN_LANE=asia.
  Fields: date, underlying, bull_bear_ratio, leverage_state, asof_freshness.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lane guard (same pattern as hk_adr_bridge)
# ---------------------------------------------------------------------------

def _ledger_advance_enabled() -> bool:
    """True only when running in the asia-close nightly lane (CN_LANE=asia)."""
    return os.environ.get("CN_LANE", "").lower() == "asia"


# ---------------------------------------------------------------------------
# Bellwether mapping
# ---------------------------------------------------------------------------

class _Bellwether(NamedTuple):
    underlying_code: str   # as it appears in the CBBC short name (e.g. "HSI")
    hk_ticker: str         # e.g. "9988.HK" or "^HSI"
    name_en: str
    name_zh: str
    is_index: bool         # True for HSI/HSTECH (index CBBCs)


# The underlying_code is what appears after '#' in the CBBC short name
# Verified from live data: 'CT#HSI  RC2709C' → HSI, 'CT#HKEX RC2610A' → HKEX
_BELLWETHERS: list[_Bellwether] = [
    # HK-listed tech bellwethers (by underlying_code in CBBC names, verified)
    _Bellwether("BABA", "9988.HK", "Alibaba",  "阿里巴巴", False),
    _Bellwether("TENCENT", "0700.HK", "Tencent", "腾讯", False),
    _Bellwether("TEN", "0700.HK",  "Tencent",  "腾讯",    False),   # alternate abbrev
    _Bellwether("700",  "0700.HK",  "Tencent",  "腾讯",    False),
    _Bellwether("MEITUAN", "3690.HK", "Meituan", "美团",  False),
    _Bellwether("MEIT", "3690.HK", "Meituan",  "美团",    False),
    _Bellwether("JD",   "9618.HK",  "JD.com",   "京东",    False),
    _Bellwether("JDCOM", "9618.HK", "JD.com",  "京东",    False),
    _Bellwether("XIAOMI", "1810.HK", "Xiaomi",  "小米",   False),
    _Bellwether("XIAO",  "1810.HK", "Xiaomi",  "小米",    False),
    _Bellwether("BAIDU", "9888.HK", "Baidu",   "百度",    False),
    _Bellwether("BIDU",  "9888.HK", "Baidu",   "百度",    False),
    _Bellwether("KWSHOU","1024.HK",  "Kuaishou","快手",    False),
    _Bellwether("KUAI",  "1024.HK",  "Kuaishou","快手",    False),
    _Bellwether("SMIC",  "0981.HK",  "SMIC",    "中芯国际",False),
    # Index CBBCs (large volumes)
    _Bellwether("HSI",   "^HSI",     "HSI",     "恒生指数",True),
    _Bellwether("HSTE",  "^HSTECH",  "HSTECH",  "恒生科技",True),
    _Bellwether("HKEX",  "0388.HK",  "HKEx",    "港交所",  False),
]

# Canonical output ticker → deduplicated list of underlying codes to match
_TICKER_TO_CODES: dict[str, list[str]] = {}
_TICKER_META: dict[str, tuple[str, str, bool]] = {}
for _bw in _BELLWETHERS:
    _TICKER_TO_CODES.setdefault(_bw.hk_ticker, []).append(_bw.underlying_code.upper())
    _TICKER_META[_bw.hk_ticker] = (_bw.name_en, _bw.name_zh, _bw.is_index)

# Ordered list of tickers for output (deterministic display order)
_OUTPUT_TICKERS: list[str] = [
    "^HSI", "^HSTECH",
    "0700.HK", "9988.HK", "9618.HK", "3690.HK",
    "1810.HK", "9888.HK", "1024.HK", "0981.HK",
    "0388.HK",
]

# ---------------------------------------------------------------------------
# Leverage state labels (descriptive only)
# ---------------------------------------------------------------------------

_LEVERAGE_STATES = frozenset([
    "bull_skew_froth",   # bull outstanding >> bear (bull:bear > 3)
    "bull_skew",         # bull outstanding > bear (bull:bear 1.5-3)
    "balanced",          # roughly equal (bull:bear 0.67-1.5)
    "bear_skew",         # bear outstanding > bull (bull:bear 0.33-0.67)
    "bear_skew_froth",   # bear outstanding >> bull (bull:bear < 0.33)
    "no_data",           # store missing / zero outstanding
])

_FROTH_THRESHOLD   = 3.0   # ratio > this → froth label
_SKEW_THRESHOLD    = 1.5   # ratio > this (but <= froth) → skew label


def _leverage_state(bull: int, bear: int) -> str:
    if bull == 0 and bear == 0:
        return "no_data"
    if bear == 0:
        return "bull_skew_froth"
    if bull == 0:
        return "bear_skew_froth"
    ratio = bull / bear
    if ratio > _FROTH_THRESHOLD:
        return "bull_skew_froth"
    if ratio > _SKEW_THRESHOLD:
        return "bull_skew"
    if ratio >= (1.0 / _SKEW_THRESHOLD):
        return "balanced"
    if ratio >= (1.0 / _FROTH_THRESHOLD):
        return "bear_skew"
    return "bear_skew_froth"


# ---------------------------------------------------------------------------
# Engine: per-underlying aggregation
# ---------------------------------------------------------------------------

def _underlying_matches(underlying_code: str, code_list: list[str]) -> bool:
    """True if the underlying_code from the XLSX matches any target code.

    Requires exact-match OR that the XLSX code starts with a target code
    (handles minor suffix variants from different issuers).

    We do NOT allow c.startswith(uc) (the reverse arm) because it causes
    short fragments to match multiple bellwethers — e.g. "B" would match
    both "BABA" (Alibaba 9988.HK) and "BAIDU" (Baidu 9888.HK), summing
    unrelated warrants into the wrong bellwether totals.

    Minimum token length guard: codes shorter than 2 chars are rejected to
    prevent single-letter fragments from sweeping large fractions of the
    universe.
    """
    uc = str(underlying_code or "").upper().strip()
    if len(uc) < 2:
        return False
    return any(uc == c or uc.startswith(c) for c in code_list if c)


def _aggregate_for_ticker(cbbc_df: pd.DataFrame,
                           ticker: str) -> dict:
    """Aggregate CBBC outstanding for one output ticker.

    Returns a dict with bull_outstanding, bear_outstanding, total, ratio,
    leverage_state, data_note.
    """
    codes = _TICKER_TO_CODES.get(ticker, [])
    name_en, name_zh, is_index = _TICKER_META.get(ticker, (ticker, ticker, False))

    if cbbc_df.empty:
        return {
            "ticker": ticker, "name_en": name_en, "name_zh": name_zh,
            "is_index": is_index, "bull_outstanding": None, "bear_outstanding": None,
            "total_outstanding": None, "bull_bear_ratio": None,
            "leverage_state": "no_data",
            "data_note": "store empty",
        }

    # Match by underlying_code (best-effort name extraction from short_name)
    mask = cbbc_df["underlying_code"].apply(
        lambda uc: _underlying_matches(uc, codes))
    sub = cbbc_df[mask]

    if sub.empty:
        return {
            "ticker": ticker, "name_en": name_en, "name_zh": name_zh,
            "is_index": is_index, "bull_outstanding": 0, "bear_outstanding": 0,
            "total_outstanding": 0, "bull_bear_ratio": None,
            "leverage_state": "no_data",
            "data_note": f"no CBBC found for {codes}",
        }

    bull_rows = sub[sub["bull_bear"] == "bull"]
    bear_rows = sub[sub["bull_bear"] == "bear"]
    bull_out = int(bull_rows["outstanding"].sum())
    bear_out = int(bear_rows["outstanding"].sum())
    total    = bull_out + bear_out

    if total == 0:
        ratio = None
    elif bear_out == 0:
        ratio = None  # infinite — displayed as "—" in UI
    else:
        ratio = round(bull_out / bear_out, 2)

    state = _leverage_state(bull_out, bear_out)

    # Honest caveat: call level from SLD PDFs is not sourced in W1
    data_note = (
        "outstanding qty from daily XLSX; "
        "mandatory call price not sourced (requires SLD PDF)"
    )

    return {
        "ticker": ticker,
        "name_en": name_en,
        "name_zh": name_zh,
        "is_index": is_index,
        "bull_outstanding": bull_out,
        "bear_outstanding": bear_out,
        "total_outstanding": total,
        "bull_bear_ratio": ratio,
        "leverage_state": state,
        "n_cbbc_contracts": len(sub),
        "data_note": data_note,
    }


# ---------------------------------------------------------------------------
# Freshness check
# ---------------------------------------------------------------------------

def _freshness_verdict(latest_trade_date: str | None) -> str:
    """Simple freshness verdict for the CBBC store."""
    if not latest_trade_date:
        return "dead"
    try:
        # trade_date may be DDMMYYYY or YYYYMMDD
        if re.match(r"^\d{8}$", latest_trade_date):
            try:
                td = datetime.strptime(latest_trade_date, "%d%m%Y").date()
            except ValueError:
                td = datetime.strptime(latest_trade_date, "%Y%m%d").date()
        else:
            return "dead"
    except Exception:
        return "dead"
    lag = (date.today() - td).days
    if lag <= 2:
        return "fresh"
    if lag <= 4:
        return "slow"
    return "stale"


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

_LEDGER_DIR_REL = "hk_impulse"
_LEDGER_FILE    = "cbbc_ledger.jsonl"
_ORGAN_ID       = "hk_cbbc"


def _ledger_path(data_root: Path | None = None) -> Path:
    if data_root is None:
        data_root = config.data_dir()
    return data_root / _LEDGER_DIR_REL / _LEDGER_FILE


def load_ledger(data_root: Path | None = None) -> list[dict]:
    """Load all ledger rows. Returns [] if file missing/corrupt."""
    p = _ledger_path(data_root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _write_ledger(rows: list[dict], data_root: Path | None = None) -> None:
    """Write ledger atomically via temp-file + os.replace."""
    p = _ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(r) for r in rows) + ("\n" if rows else "")
    fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=".cbbc_ledger_tmp_")
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


def stamp_ledger(snap: dict, data_root: Path | None = None) -> int:
    """Append one ledger row per underlying in this snapshot.

    Gated by CN_LANE=asia (house law: nightly sole advancer).
    Idempotent on (date, underlying). Never raises.
    """
    if not _ledger_advance_enabled():
        log.debug("hk_cbbc.stamp_ledger: skipped (CN_LANE != asia)")
        return 0
    try:
        today_str = str(snap.get("as_of_trade_date", date.today().isoformat()))
        rows = load_ledger(data_root)
        existing = {(r.get("date"), r.get("underlying")) for r in rows}
        appended = 0
        for entry in snap.get("bellwethers", []):
            underlying = entry.get("ticker", "")
            key = (today_str, underlying)
            if key in existing:
                continue
            row = {
                "date": today_str,
                "underlying": underlying,
                "name_en": entry.get("name_en", ""),
                "bull_bear_ratio": entry.get("bull_bear_ratio"),
                "leverage_state": entry.get("leverage_state", "no_data"),
                "bull_outstanding": entry.get("bull_outstanding"),
                "bear_outstanding": entry.get("bear_outstanding"),
                "total_outstanding": entry.get("total_outstanding"),
                "asof_freshness": snap.get("freshness", "unknown"),
            }
            rows.append(row)
            existing.add(key)
            appended += 1
        if appended:
            _write_ledger(rows, data_root)
        return appended
    except Exception as e:  # noqa: BLE001
        log.warning("hk_cbbc.stamp_ledger failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# Main engine entry point
# ---------------------------------------------------------------------------

def run(data_root: Path | None = None) -> dict:
    """Build the CBBC leverage map snapshot.

    Returns a dict with:
      as_of_trade_date, freshness, bellwethers (list), banner (dict|None),
      display_only (always True).

    Stamps the forward ledger when CN_LANE=asia.
    Never raises.
    """
    try:
        from collectors.hk_cbbc import load_latest, store_status
        status = store_status(data_root)
        cbbc_df = load_latest("cbbc", data_root)
        freshness = _freshness_verdict(status.get("latest_trade_date"))

        # Banner when data is stale or missing
        banner = None
        if freshness in ("stale", "dead") or cbbc_df.empty:
            banner = {
                "en": f"CBBC data {freshness} — leverage map unavailable",
                "zh": f"牛熊证数据{('落后' if freshness == 'stale' else '缺失')}，杠杆图不可用",
            }

        bellwethers = []
        for ticker in _OUTPUT_TICKERS:
            entry = _aggregate_for_ticker(cbbc_df, ticker)
            bellwethers.append(entry)

        snap = {
            "as_of_trade_date": status.get("latest_trade_date", ""),
            "freshness": freshness,
            "bellwethers": bellwethers,
            "banner": banner,
            "cbbc_total_contracts": status.get("cbbc_rows", 0),
            "dw_total_contracts": status.get("dw_rows", 0),
            "display_only": True,
        }

        # Stamp forward ledger (gated by CN_LANE=asia)
        stamp_ledger(snap, data_root)

        return snap

    except Exception as e:  # noqa: BLE001 — never crash the nightly render
        log.error("hk_cbbc engine failed: %s", e)
        return {
            "as_of_trade_date": "",
            "freshness": "dead",
            "bellwethers": [],
            "banner": {
                "en": "CBBC engine error — data unavailable",
                "zh": "牛熊证引擎错误，数据不可用",
            },
            "cbbc_total_contracts": 0,
            "dw_total_contracts": 0,
            "display_only": True,
        }
