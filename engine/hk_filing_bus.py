"""HK Filing Bus engine — deterministic company-catalyst tape.

Answers "what corporate event is behind this move?" for HK bellwether names.
DISPLAY-ONLY context layer. No buy/sell signals; no scoring; no LLM origination.

CLASSIFICATION SCHEMA (deterministic keyword rules only)
---------------------------------------------------------
Category       | Source                   | Flags
───────────────┼──────────────────────────┼──────────────────────────────────
buyback        | collector cat "buyback"   | buyback_flag=True; NOT dilutive
placement      | hk_placements events.pq   | dilution_flag=True when is_dilutive
results        | "final_results"+"interim" | both flags False
mandate        | "general_mandate"         | dilution_flag=True (share issuance)
shareholder    | "shareholder"             | both flags False (context only)
other          | fallback                  | both flags False

DILUTION FLAG RULES (deterministic, no LLM)
-------------------------------------------
  dilution_flag=True:
    category in {placement, mandate}
    AND title passes _is_dilutive_title()
  buyback_flag=True:
    category == "buyback"
    AND title passes _is_buyback_title()

HARD CONSTRAINT: a row can NEVER have both dilution_flag AND buyback_flag True.

OUTPUTS
-------
  Per-row tape:  {ticker, date, category, title_en, official_flag,
                  dilution_flag, buyback_flag}
  Per-ticker summary: {ticker, name_en, name_zh, counts_by_category,
                       most_recent, most_recent_category, most_recent_date}
  Snapshot dict returned by run():
    {as_of, freshness, tape (list), bellwethers (list), display_only: True,
     banner (dict|None)}

FORWARD LEDGER
--------------
  data/hk_impulse/filing_ledger.jsonl
  Append-only, atomic temp+rename, idempotent on (ticker, date, category,
  title_hash). Gated by CN_LANE=asia (nightly sole advancer — house law).

FAIL-OPEN
---------
  Every store read is wrapped; missing/stale degrades to empty with banner.
  Never raises; never crashes the nightly render.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from collectors.hk_placements import is_dilutive as _hk_placements_is_dilutive
from lib import config

log = logging.getLogger(__name__)

from engine.ledger_lane import asia_advance_enabled as _ledger_advance_enabled


# ---------------------------------------------------------------------------
# Bellwether universe (large-cap HK names we surface in the tape)
# ---------------------------------------------------------------------------

class _Ticker:
    def __init__(self, ticker: str, name_en: str, name_zh: str) -> None:
        self.ticker   = ticker
        self.name_en  = name_en
        self.name_zh  = name_zh

_BELLWETHERS = [
    _Ticker("0700.HK",  "Tencent",    "腾讯"),
    _Ticker("9988.HK",  "Alibaba",    "阿里巴巴"),
    _Ticker("9618.HK",  "JD.com",     "京东"),
    _Ticker("3690.HK",  "Meituan",    "美团"),
    _Ticker("1810.HK",  "Xiaomi",     "小米"),
    _Ticker("9888.HK",  "Baidu",       "百度"),
    _Ticker("1024.HK",  "Kuaishou",   "快手"),
    _Ticker("0981.HK",  "SMIC",       "中芯国际"),
    _Ticker("0388.HK",  "HKEx",       "港交所"),
    _Ticker("2318.HK",  "Ping An",    "平安保险"),
    _Ticker("0941.HK",  "China Mobile","中国移动"),
    _Ticker("1398.HK",  "ICBC",       "工商银行"),
    _Ticker("3988.HK",  "Bank of China","中国银行"),
    _Ticker("0939.HK",  "CCB",        "建设银行"),
    _Ticker("0857.HK",  "PetroChina", "中国石油"),
    _Ticker("0883.HK",  "CNOOC",      "中国海洋石油"),
    _Ticker("1997.HK",  "Wharf REIC", "九龙仓置业"),
    _Ticker("2020.HK",  "ANTA Sports","安踏体育"),
    _Ticker("0175.HK",  "Geely Auto", "吉利汽车"),
    _Ticker("0002.HK",  "CLP Holdings","中电控股"),
]

_BELLWETHER_SET = {t.ticker for t in _BELLWETHERS}
_TICKER_META: dict[str, _Ticker] = {t.ticker: t for t in _BELLWETHERS}

# Canonical category values in the output tape
VALID_CATEGORIES = frozenset([
    "buyback", "placement", "results", "mandate", "shareholder", "other"
])


# ---------------------------------------------------------------------------
# Deterministic classification helpers
# ---------------------------------------------------------------------------

# ---- Buyback title classifier ----
# On-market share repurchase: must contain substantive repurchase language.
_BUYBACK_STRONG_RE = re.compile(
    r"SHARE\s+BUY[-\s]?BACK|REPURCHASE\s+(OF\s+)?(OWN\s+)?SHARES|"
    r"SHARE\s+REPURCHASE|BUY[-\s]?BACK\s+OF\s+SHARES",
    re.I)
_BUYBACK_WEAK_RE = re.compile(
    r"\bBUY[-\s]?BACK\b|\bREPURCHASE\b", re.I)
# Exclusions: debt/bond buyback, share-consolidation, privatisation
_BUYBACK_EXCL_RE = re.compile(
    r"\bBONDS?\b|\bNOTES?\b|\bDEBT\b|CONVERTIBLE\s+SECURITIES|"
    r"PRIVATISATION|PRIVATIZATION|CONSOLIDAT\b",
    re.I)


def _is_buyback_title(title: str) -> bool:
    """True when the title describes an on-market share repurchase."""
    t = str(title or "")
    if _BUYBACK_EXCL_RE.search(t):
        return False
    return bool(_BUYBACK_STRONG_RE.search(t) or _BUYBACK_WEAK_RE.search(t))


# ---- Dilutive-issuance title classifier ----
# Delegates to collectors.hk_placements.is_dilutive (the canonical implementation)
# to avoid drift.  hk_placements owns the regex vocabulary; any new strong tokens
# (e.g. "SHARE ISSUANCE") are automatically picked up here.

def _is_dilutive_title(title: str) -> bool:
    """True when the title describes a common-equity dilution event.

    Applied on top of category filters (mandate / placement categories only).
    Delegates to collectors.hk_placements.is_dilutive() — do not duplicate
    the regex logic here.
    """
    return _hk_placements_is_dilutive(title)


# ---- Category → canonical label mapping ----

_CAT_MAP: dict[str, str] = {
    # From hk_hkexnews collector
    "buyback":         "buyback",
    "final_results":   "results",
    "interim_results": "results",
    "general_mandate": "mandate",
    "shareholder":     "shareholder",
    # From hk_placements collector (joined at engine time)
    "placing":         "placement",
    "rights_issue":    "placement",
    "open_offer":      "placement",
}


def classify_row(category: str, title: str) -> dict:
    """Classify one event row into canonical flags.

    Returns: {category, dilution_flag, buyback_flag}

    HARD CONSTRAINT enforced: dilution_flag XOR buyback_flag (never both True).
    """
    canon = _CAT_MAP.get(category, "other")

    if canon == "buyback" and _is_buyback_title(title):
        return {"category": "buyback", "dilution_flag": False, "buyback_flag": True}

    if canon == "buyback":
        # Buyback category but title doesn't read as a buyback — classify as other
        return {"category": "other", "dilution_flag": False, "buyback_flag": False}

    if canon in ("placement", "mandate") and _is_dilutive_title(title):
        return {"category": canon, "dilution_flag": True, "buyback_flag": False}

    if canon in ("placement", "mandate"):
        # Over-captured (e.g. convertible bond, meeting notice) — demote to other
        return {"category": "other", "dilution_flag": False, "buyback_flag": False}

    # results, shareholder, other → no flags
    return {"category": canon, "dilution_flag": False, "buyback_flag": False}


# ---------------------------------------------------------------------------
# Store readers
# ---------------------------------------------------------------------------

def _load_filings(data_root: Path | None = None) -> pd.DataFrame:
    """Load hk_filings events store (new categories). Fail-open → empty."""
    root = data_root or Path(config.data_dir())
    p = root / "hk_filings" / "events.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("hk_filing_bus: hk_filings read failed (%s)", e)
        return pd.DataFrame()


def _load_placements(data_root: Path | None = None) -> pd.DataFrame:
    """Load hk_placements events store (existing). Fail-open → empty."""
    root = data_root or Path(config.data_dir())
    p = root / "hk_placements" / "events.parquet"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("hk_filing_bus: hk_placements read failed (%s)", e)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Tape builder
# ---------------------------------------------------------------------------

def _title_hash(title: str) -> str:
    """First 8 hex chars of SHA-256 of the title — idempotency key."""
    return hashlib.sha256(title.encode()).hexdigest()[:8]


def build_tape(filings_df: pd.DataFrame,
               placements_df: pd.DataFrame,
               window_days: int = 90) -> pd.DataFrame:
    """Build the combined, classified, per-row catalyst tape.

    Merges both stores, applies the deterministic classifier, and filters to
    the trailing ``window_days`` window.

    Returns a DataFrame with columns:
      news_id, stock_code, ticker, date, category, title_en,
      official_flag, dilution_flag, buyback_flag, title_hash
    """
    frames: list[pd.DataFrame] = []

    if not filings_df.empty:
        frames.append(filings_df)
    if not placements_df.empty:
        frames.append(placements_df)

    if not frames:
        return pd.DataFrame(columns=[
            "news_id", "stock_code", "ticker", "date", "category",
            "title_en", "official_flag", "dilution_flag", "buyback_flag",
            "title_hash"])

    combined = pd.concat(frames, ignore_index=True)

    # Date filter — trailing window
    today_ts = pd.Timestamp.today().normalize()
    cutoff = today_ts - pd.Timedelta(days=window_days)
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined[combined["date"] >= cutoff].copy()

    if combined.empty:
        return pd.DataFrame(columns=[
            "news_id", "stock_code", "ticker", "date", "category",
            "title_en", "official_flag", "dilution_flag", "buyback_flag",
            "title_hash"])

    # Dedup on (news_id, stock_code)
    combined = (combined
                .drop_duplicates(subset=["news_id", "stock_code"], keep="first")
                .reset_index(drop=True))

    # Apply classifier
    classified = combined["category"].combine(
        combined.get("title", pd.Series([""] * len(combined))),
        lambda cat, title: classify_row(cat, title))
    combined["category"] = classified.map(lambda d: d["category"])
    combined["dilution_flag"] = classified.map(lambda d: d["dilution_flag"])
    combined["buyback_flag"] = classified.map(lambda d: d["buyback_flag"])

    # HARD CONSTRAINT: never both flags True
    both = combined["dilution_flag"] & combined["buyback_flag"]
    if both.any():
        log.error("hk_filing_bus: BUG — %d rows have both dilution_flag AND "
                  "buyback_flag True; zeroing buyback_flag", both.sum())
        combined.loc[both, "buyback_flag"] = False

    # official_flag: announcement from an officially designated t2 category
    # (all rows here are from the official HKEX headline system)
    combined["official_flag"] = True

    # Clean up output columns
    title_col = "title" if "title" in combined.columns else "TITLE"
    combined["title_en"] = combined.get(title_col, pd.Series([""] * len(combined))).fillna("")
    combined["title_hash"] = combined["title_en"].map(_title_hash)

    out_cols = ["news_id", "stock_code", "ticker", "date", "category",
                "title_en", "official_flag", "dilution_flag", "buyback_flag",
                "title_hash"]
    return combined[out_cols].sort_values("date", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Per-ticker summary
# ---------------------------------------------------------------------------

def _ticker_summary(tape: pd.DataFrame, ticker: str) -> dict:
    """Recent-catalyst summary for one ticker."""
    meta = _TICKER_META.get(ticker, None)
    name_en = meta.name_en if meta else ticker
    name_zh = meta.name_zh if meta else ticker

    sub = tape[tape["ticker"] == ticker] if not tape.empty else pd.DataFrame()
    if sub.empty:
        return {
            "ticker": ticker, "name_en": name_en, "name_zh": name_zh,
            "counts": {}, "most_recent": None, "most_recent_category": None,
            "most_recent_date": None, "has_dilution": False,
            "has_buyback": False,
        }

    counts = sub["category"].value_counts().to_dict()
    recent = sub.sort_values("date", ascending=False).iloc[0]

    return {
        "ticker": ticker,
        "name_en": name_en,
        "name_zh": name_zh,
        "counts": counts,
        "most_recent": str(recent.get("title_en", ""))[:120],
        "most_recent_category": str(recent.get("category", "")),
        "most_recent_date": str(pd.Timestamp(recent["date"]).date()),
        "has_dilution": bool(sub["dilution_flag"].any()),
        "has_buyback": bool(sub["buyback_flag"].any()),
    }


# ---------------------------------------------------------------------------
# Freshness gate (mirrors hk_cbbc._freshness_verdict pattern)
# ---------------------------------------------------------------------------

def _freshness(data_root: Path | None = None) -> str:
    """Simple freshness verdict based on the coverage stamp."""
    root = data_root or Path(config.data_dir())
    p = root / "hk_filings" / "coverage.json"
    if not p.exists():
        return "dead"
    try:
        cov = json.loads(p.read_text())
        latest = cov.get("latest", "")
        if not latest:
            return "dead"
        lag = (date.today() - date.fromisoformat(str(latest))).days
        if lag <= 2:
            return "fresh"
        if lag <= 7:
            return "slow"
        return "stale"
    except Exception:  # noqa: BLE001
        return "dead"


# ---------------------------------------------------------------------------
# Forward ledger
# ---------------------------------------------------------------------------

_LEDGER_DIR = "hk_impulse"
_LEDGER_FILE = "filing_ledger.jsonl"


def _ledger_path(data_root: Path | None = None) -> Path:
    root = data_root or Path(config.data_dir())
    return root / _LEDGER_DIR / _LEDGER_FILE


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
    content = "\n".join(json.dumps(r, default=str) for r in rows)
    if content:
        content += "\n"
    fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=".filing_ledger_tmp_")
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


def stamp_ledger(tape: pd.DataFrame, data_root: Path | None = None) -> int:
    """Append one ledger row per new (ticker, date, category, title_hash).

    Idempotent: rows already present (same key) are skipped.
    Gated by CN_LANE=asia (house law: nightly sole advancer).
    Never raises.
    """
    if not _ledger_advance_enabled():
        log.debug("hk_filing_bus.stamp_ledger: skipped (CN_LANE != asia)")
        return 0
    try:
        rows = load_ledger(data_root)
        existing_keys = {
            (r.get("ticker"), r.get("date"), r.get("category"), r.get("title_hash"))
            for r in rows
        }
        appended = 0
        for _, ev in tape.iterrows():
            key = (
                str(ev.get("ticker", "")),
                str(pd.Timestamp(ev["date"]).date()),
                str(ev.get("category", "")),
                str(ev.get("title_hash", "")),
            )
            if key in existing_keys:
                continue
            rows.append({
                "ticker":       key[0],
                "date":         key[1],
                "category":     key[2],
                "title_hash":   key[3],
                "title_en":     str(ev.get("title_en", ""))[:120],
                "dilution_flag":bool(ev.get("dilution_flag", False)),
                "buyback_flag": bool(ev.get("buyback_flag", False)),
                "stamped_at":   datetime.now(timezone.utc).isoformat(),
            })
            existing_keys.add(key)
            appended += 1
        if appended:
            _write_ledger(rows, data_root)
        return appended
    except Exception as e:  # noqa: BLE001
        log.warning("hk_filing_bus.stamp_ledger failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# Main engine entry point
# ---------------------------------------------------------------------------

def run(data_root: Path | None = None, window_days: int = 90) -> dict:
    """Build the filing-bus catalyst snapshot.

    Returns:
      {as_of, freshness, tape (list[dict]), bellwethers (list[dict]),
       display_only (True), banner (dict|None)}

    Stamps the forward ledger when CN_LANE=asia.
    Never raises.
    """
    try:
        filings_df    = _load_filings(data_root)
        placements_df = _load_placements(data_root)

        freshness = _freshness(data_root)

        banner = None
        if freshness in ("stale", "dead") and filings_df.empty:
            banner = {
                "en": f"Filing data {freshness} — catalyst tape unavailable",
                "zh": f"公告数据{'落后' if freshness == 'stale' else '缺失'}，催化剂记录不可用",
            }

        tape_df = build_tape(filings_df, placements_df, window_days=window_days)
        tape_rows = []
        for _, row in tape_df.iterrows():
            tape_rows.append({
                "ticker":        str(row.get("ticker", "") or ""),
                "date":          str(pd.Timestamp(row["date"]).date()),
                "category":      str(row.get("category", "")),
                "title_en":      str(row.get("title_en", ""))[:120],
                "official_flag": bool(row.get("official_flag", True)),
                "dilution_flag": bool(row.get("dilution_flag", False)),
                "buyback_flag":  bool(row.get("buyback_flag", False)),
            })

        bellwethers = [_ticker_summary(tape_df, t.ticker) for t in _BELLWETHERS]

        snap = {
            "as_of": date.today().isoformat(),
            "freshness": freshness,
            "tape": tape_rows,
            "bellwethers": bellwethers,
            "display_only": True,
            "banner": banner,
        }

        # Stamp forward ledger (gated by CN_LANE=asia)
        stamp_ledger(tape_df, data_root)

        return snap

    except Exception as e:  # noqa: BLE001 — never crash the nightly render
        log.error("hk_filing_bus engine failed: %s", e)
        return {
            "as_of": date.today().isoformat(),
            "freshness": "dead",
            "tape": [],
            "bellwethers": [],
            "display_only": True,
            "banner": {
                "en": "Filing bus engine error — catalyst tape unavailable",
                "zh": "公司公告引擎错误，催化剂记录不可用",
            },
        }
