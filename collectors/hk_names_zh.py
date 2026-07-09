"""HK Chinese name enricher — fetches ticker→中文名 for the HK universe.

WHY
---
The 165-name HK universe carries English company names from HKEX/yfinance; ZH mode
needs the official Chinese names.  This collector resolves them and persists
``config/hk_names_zh.json`` so the build pipeline can wire name_zh into every
ticker row (standouts / washout_watch / catalyst tape / command-panel scorecards).

SOURCE STRATEGY
---------------
Preferred: ``akshare.stock_hk_spot_em()`` — returns the Eastmoney HK quote table
with 名称 (Chinese name) columns, no API key required.

Fallback: the curated ``config/hk_names_zh.json`` committed alongside this file.
This JSON is a hand-verified map of all 160 current universe tickers.  The
collector MAY re-enrich it from akshare on successful runs, but the committed
file always provides a usable baseline.

FAIL-OPEN
---------
A failed or partial enrichment degrades to whatever is already in the JSON.
The build pipeline uses ``load_names_zh()`` which always returns a dict (possibly
empty), so a missing name → falls back to the English name in the template
(``{{ t(name_en, name_zh or name_en) }}``).

RUN
---
  python -m scripts.collect --only hk_names_zh

Or standalone for testing / backfill:
  python -m collectors.hk_names_zh
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_CONFIG_JSON = Path(__file__).resolve().parent.parent / "config" / "hk_names_zh.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_names_zh() -> dict[str, str]:
    """Return ticker → Chinese name dict.

    Reads ``config/hk_names_zh.json`` (committed + enriched by this collector).
    Always returns a dict; empty when the file is missing / corrupt.

    Usage::

        from collectors.hk_names_zh import load_names_zh
        _NAMES_ZH = load_names_zh()
        name_zh = _NAMES_ZH.get(ticker)   # None if not in map
    """
    try:
        raw = json.loads(_CONFIG_JSON.read_text(encoding="utf-8"))
        return {k: v for k, v in raw.items() if not k.startswith("_")}
    except FileNotFoundError:
        log.warning("hk_names_zh: config/hk_names_zh.json not found — name_zh will be None")
        return {}
    except Exception as e:  # noqa: BLE001
        log.warning("hk_names_zh: failed to load names_zh (%s) — name_zh will be None", e)
        return {}


def _fetch_akshare_names() -> dict[str, str]:
    """Attempt live fetch from akshare.stock_hk_spot_em().

    Returns ticker → Chinese name dict, or {} on any failure.
    """
    try:
        import akshare as ak  # optional dependency
        df = ak.stock_hk_spot_em()
        # Columns include: 代码 (code, e.g. 00700), 名称 (Chinese name)
        if "代码" not in df.columns or "名称" not in df.columns:
            log.warning("hk_names_zh: akshare df missing expected columns: %s", df.columns.tolist())
            return {}
        result: dict[str, str] = {}
        for _, row in df.iterrows():
            code = str(row["代码"]).zfill(5)  # e.g. '00700'
            # Convert to our ticker format: e.g. '00700' → '0700.HK'
            tk = code.lstrip("0").zfill(4) + ".HK"
            name_zh = str(row["名称"]).strip()
            if name_zh:
                result[tk] = name_zh
        log.info("hk_names_zh: akshare returned %d names", len(result))
        return result
    except ImportError:
        log.debug("hk_names_zh: akshare not installed — skip live fetch")
        return {}
    except Exception as e:  # noqa: BLE001
        log.warning("hk_names_zh: akshare fetch failed (%s) — using committed JSON", e)
        return {}


def enrich_and_persist(tickers: list[str] | None = None) -> dict[str, str]:
    """Fetch live names from akshare and merge into config/hk_names_zh.json.

    Called by the collector adapter's ``fetch()``.  Best-effort: the committed
    JSON is always the authoritative fallback; a failed live fetch is not fatal.

    Parameters
    ----------
    tickers:
        Optional list of tickers to restrict the update to (e.g. the current
        universe).  When None, all akshare-returned names are merged.

    Returns the final (merged) ticker → name dict that was persisted.
    """
    existing = load_names_zh()

    live = _fetch_akshare_names()

    if live:
        # Merge: live data wins, but only for tickers in our universe
        if tickers:
            live = {t: v for t, v in live.items() if t in set(tickers)}
        merged = {**existing, **live}
    else:
        # No live data — keep existing
        merged = existing

    if live:
        # Persist enriched map (preserving the _comment key)
        try:
            raw = json.loads(_CONFIG_JSON.read_text(encoding="utf-8")) if _CONFIG_JSON.exists() else {}
        except Exception:  # noqa: BLE001
            raw = {}
        comment = raw.get("_comment", "HK universe Chinese company names.")
        out = {"_comment": comment}
        out.update(merged)
        _CONFIG_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("hk_names_zh: persisted %d names to config/hk_names_zh.json", len(merged))
    else:
        log.info("hk_names_zh: no live update — using %d committed names", len(existing))

    return merged


# ---------------------------------------------------------------------------
# Standalone / test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    names = load_names_zh()
    print(f"Loaded {len(names)} names from config/hk_names_zh.json")
    # Quick spot-check on the 4 Bottom-Watch large-caps mentioned in the brief
    for tk, expected_zh in [
        ("0358.HK", "江西铜业"),
        ("0017.HK", "新世界发展"),
        ("2600.HK", "中国铝业"),
        ("3993.HK", "洛阳钼业"),
    ]:
        got = names.get(tk)
        status = "OK" if got == expected_zh else ("MISSING" if got is None else f"GOT:{got}")
        print(f"  {tk}: {status}")
