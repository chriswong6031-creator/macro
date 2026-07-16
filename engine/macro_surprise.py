"""Macro Surprise Engine — parse official FRED releases into surprise cards.

LEAF · CONTEXT-ONLY. Imports nothing from the mechanical scoring core
(conditions/regime/run/inputs/equity_alloc) and nothing in the scoring path
imports this module. Every public function returns plain data and NEVER raises
into the build — all network/parse/IO failures degrade gracefully to empty.

PIT CAVEAT: FRED's public API serves the LATEST REVISED values, not the
first-print values that were knowable in real time. The 'prior' value in every
card is the REVISED prior, not the original first print. Consensus comparison
and ALFRED point-in-time vintages are deferred to a later wave. Labels say
"vs revised prior" to be honest about this.

HOW surprise is measured (no consensus feed exists free — we do NOT fake one):
  (a) delta vs revised prior print
  (b) delta vs trailing 3-month and 6-month mean of the transformed series
  (c) z-score of the new print vs trailing 3y and 5y distributions
  (d) fail-open hook: deviation vs real_activity_nowcast if a compatible
      series is exposed there (silently skipped if unavailable)

Surprise size is classified from |z3y|:
  <0.5  → 'inline'   (in-line with recent trend)
  0.5–1.5 → 'notable'  (worth noting)
  >1.5  → 'large'    (significantly outside recent trend)

STUB SUPPRESSION: is_release_stub(title) returns True for bare official
release-title stubs (the release NAME with no data, e.g. "Manufacturing and
Trade Inventories and Sales"). These are suppressed in macro_news.py with
reason 'macro_release_stub' via the W0 reject plumbing.  Real headlines that
carry values ("Payrolls +57k vs +139k prior — labor cooling") are NOT stubs.

Cache: FRED fetches are cached to data/macro/fred_surprise_cache/ with a 12h
TTL, matching the rest of the news-feed cache discipline.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from lib import config

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# RELEASE REGISTRY
# Each entry drives both the FRED fetch and the stub-suppression alias list.
#
# Fields:
#   key             — short machine key
#   display_name    — human-readable name (used in cards)
#   title_aliases   — bare release-name stubs to suppress (case-insensitive,
#                     near-exact match against the raw title)
#   fred_series     — FRED series ID
#   transform       — 'level' | 'mom_diff' | 'mom_pct' | 'yoy_pct'
#   cadence         — 'monthly' | 'weekly' | 'quarterly'
#   macro_channel   — 'inflation' | 'labor' | 'growth' | 'trade'
#   direction_map   — 'higher_hotter' (higher = hotter/worse for inflation/labor
#                     concerns) | 'higher_better' | 'lower_better' | 'neutral'
# --------------------------------------------------------------------------- #
RELEASE_REGISTRY: list[dict] = [
    {
        "key": "cpi",
        "display_name": "CPI (Consumer Price Index)",
        "title_aliases": [
            "consumer price index",
            "consumer price index for all urban consumers",
            "cpi for all urban consumers",
        ],
        "fred_series": "CPIAUCSL",
        "transform": "mom_pct",
        "cadence": "monthly",
        "macro_channel": "inflation",
        "direction_map": "higher_hotter",
    },
    {
        "key": "ppi",
        "display_name": "PPI (Producer Price Index)",
        "title_aliases": [
            "producer price index",
            "producer price index by commodity",
            "producer prices",
        ],
        "fred_series": "PPIFIS",
        "transform": "mom_pct",
        "cadence": "monthly",
        "macro_channel": "inflation",
        "direction_map": "higher_hotter",
    },
    {
        "key": "payrolls",
        "display_name": "Nonfarm Payrolls",
        "title_aliases": [
            "employment situation",
            "the employment situation",
            "nonfarm payrolls",
            "nonfarm payroll",
        ],
        "fred_series": "PAYEMS",
        "transform": "mom_diff",
        "cadence": "monthly",
        "macro_channel": "labor",
        "direction_map": "higher_better",
    },
    {
        "key": "unemployment",
        "display_name": "Unemployment Rate",
        "title_aliases": [
            "unemployment rate",
            "the unemployment rate",
        ],
        "fred_series": "UNRATE",
        "transform": "level",
        "cadence": "monthly",
        "macro_channel": "labor",
        "direction_map": "lower_better",
    },
    {
        "key": "retail_sales",
        "display_name": "Retail Sales",
        "title_aliases": [
            "advance retail sales",
            "retail sales",
            "retail and food services sales",
            "advance monthly sales for retail and food services",
        ],
        "fred_series": "RSAFS",
        "transform": "mom_pct",
        "cadence": "monthly",
        "macro_channel": "growth",
        "direction_map": "higher_better",
    },
    {
        "key": "trade_balance",
        "display_name": "Trade Balance",
        "title_aliases": [
            "u.s. international trade in goods and services",
            "international trade in goods and services",
            "trade balance",
            "u.s. trade in goods and services",
        ],
        "fred_series": "BOPGSTB",
        "transform": "level",
        "cadence": "monthly",
        "macro_channel": "trade",
        "direction_map": "neutral",
    },
    {
        "key": "initial_claims",
        "display_name": "Initial Jobless Claims",
        "title_aliases": [
            "unemployment insurance weekly claims",
            "initial claims",
            "jobless claims",
            "unemployment claims",
        ],
        "fred_series": "ICSA",
        "transform": "level",
        "cadence": "weekly",
        "macro_channel": "labor",
        "direction_map": "lower_better",
    },
    {
        "key": "business_inventories",
        "display_name": "Business Inventories",
        "title_aliases": [
            "manufacturing and trade inventories and sales",
            "business inventories",
            "manufacturing & trade inventories and sales",
            "inventories and sales",
        ],
        "fred_series": "BUSINV",
        "transform": "mom_pct",
        "cadence": "monthly",
        "macro_channel": "growth",
        "direction_map": "neutral",
    },
    {
        "key": "gdp",
        "display_name": "Real GDP (Quarterly, SAAR)",
        "title_aliases": [
            "gross domestic product",
            "gdp",
            "national income and product accounts",
            "national income & product accounts",
            "gross domestic product 3rd estimate",
            "gross domestic product 2nd estimate",
            "gross domestic product advance estimate",
        ],
        "fred_series": "A191RL1Q225SBEA",
        "transform": "level",
        "cadence": "quarterly",
        "macro_channel": "growth",
        "direction_map": "higher_better",
    },
    {
        "key": "pce",
        "display_name": "PCE Price Index",
        "title_aliases": [
            "personal income and outlays",
            "personal consumption expenditures",
            "personal income and spending",
            "pce price index",
        ],
        "fred_series": "PCEPI",
        "transform": "mom_pct",
        "cadence": "monthly",
        "macro_channel": "inflation",
        "direction_map": "higher_hotter",
    },
]

# Build a flat set of alias tokens for fast lookup (normalised lowercase)
_STUB_ALIASES: list[tuple[str, str]] = []  # (normalised_alias, release_key)
for _entry in RELEASE_REGISTRY:
    for _alias in _entry["title_aliases"]:
        _STUB_ALIASES.append((_alias.lower().strip(), _entry["key"]))


def _norm_stub(t: str) -> str:
    """Normalise for stub matching: lowercase, collapse whitespace, strip punct."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())).strip()


# Pre-normalise the aliases
_STUB_NORM: list[tuple[str, str]] = [(_norm_stub(a), k) for a, k in _STUB_ALIASES]

# Tokens whose presence indicates the title carries actual data values (NOT a stub)
# — real headlines mention numbers or direction words.
_VALUE_INDICATORS = re.compile(
    r"\b(?:up|down|rose|fell|fell\s+to|climbed|dropped|slipped|jumped|gained|lost|"
    r"increased|decreased|accelerated|decelerated|beat|missed|exceeded|below|above|"
    r"vs\.|vs\s|better|worse|hotter|cooler|cooling|surged|plunged|shrank|expanded|"
    r"contracted|narrowed|widened|tick(?:ed|s)\s+(?:up|down)|"
    r"\+|-|\d+[\.,]\d+|\d+k|\d+%|percent|pct|basis\s+point|\bbps\b)\b",
    re.I,
)


def is_release_stub(title: str) -> bool:
    """True when `title` is a bare official-release stub (the release NAME alone,
    carrying no data values) that should be suppressed.

    A STUB is near-exact to one of the registry's `title_aliases` after normalisation,
    AND does NOT contain value-indicator tokens (numbers, directional words).

    Positive case:  "Manufacturing and Trade Inventories and Sales"  → True
    Negative case:  "U.S. job creation cools in June with payrolls growth of just 57,000"
                                                                     → False (has values)
    Negative case:  "Powell cites employment situation as key uncertainty"
                                                                     → False (contextual, not stub)
    """
    if not title:
        return False
    normed = _norm_stub(title)
    # Quick value-indicator guard: if the ORIGINAL title clearly carries data, it's news.
    if _VALUE_INDICATORS.search(title):
        return False
    # Near-exact match: the alias must be (almost) fully covered by the title,
    # AND the title must not carry much beyond the alias. Coverage is measured
    # against the ALIAS length — not max(title, alias) — so trailing date tokens
    # ("The Employment Situation - June 2026") don't dilute the ratio; the
    # extra-token cap alone bounds how much the title may add. Partial-phrase
    # matches like "Powell cites employment situation..." still fail on both
    # counts (incomplete alias coverage and/or too many extra tokens).
    normed_tokens = set(normed.split())
    for alias_norm, _key in _STUB_NORM:
        alias_tokens = set(alias_norm.split())
        if not alias_tokens:
            continue
        overlap = len(normed_tokens & alias_tokens)
        alias_coverage = overlap / len(alias_tokens)
        title_extra_tokens = len(normed_tokens - alias_tokens)
        if alias_coverage >= 0.80 and title_extra_tokens <= 3:
            return True
    return False


# --------------------------------------------------------------------------- #
# FRED fetch with caching
# --------------------------------------------------------------------------- #
_CACHE_DIR_NAME = "fred_surprise_cache"
_CACHE_TTL_H = 12.0


def _cache_dir() -> Path:
    d = config.data_dir() / "macro" / _CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(series_id: str) -> Path:
    return _cache_dir() / f"{series_id}.json"


def _cache_fresh(path: Path, ttl_h: float = _CACHE_TTL_H) -> bool:
    if not path.exists():
        return False
    age_h = (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 3600.0
    return age_h < ttl_h


def _cache_read(path: Path) -> list[dict] | None:
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None


def _cache_write(path: Path, records: list[dict]) -> None:
    try:
        path.write_text(json.dumps(records, default=str))
    except Exception as e:  # noqa: BLE001
        log.debug("macro_surprise cache write failed (%s)", e)


def _fetch_fred_series(series_id: str) -> list[dict] | None:
    """Fetch a FRED series via the fredgraph.csv keyless endpoint.
    Returns list of {"date": "YYYY-MM-DD", "value": float} or None on error.
    Reuses collectors.fred.FREDGRAPH_UA (the library UA that passes the WAF).
    Caches to data/macro/fred_surprise_cache/<series_id>.json with 12h TTL.
    Never raises."""
    cache = _cache_path(series_id)
    if _cache_fresh(cache):
        data = _cache_read(cache)
        if data is not None:
            return data
    try:
        import io
        import requests
        from collectors.fred import FREDGRAPH_UA
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        r = requests.get(url, headers={"User-Agent": FREDGRAPH_UA}, timeout=30)
        if r.status_code != 200:
            log.warning("macro_surprise: FRED %s → HTTP %d", series_id, r.status_code)
            return None
        import pandas as pd
        df = pd.read_csv(io.StringIO(r.text))
        if df.shape[1] != 2:
            log.warning("macro_surprise: FRED %s unexpected shape %s", series_id, df.shape)
            return None
        df.columns = ["date", "value"]
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"])
        if df.empty:
            return None
        records = df.to_dict("records")
        _cache_write(cache, records)
        return records
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("macro_surprise: FRED fetch %s failed (%s)", series_id, e)
        return None


# --------------------------------------------------------------------------- #
# Transform helpers
# --------------------------------------------------------------------------- #
def _apply_transform(values: list[float], transform: str) -> list[float]:
    """Apply the registered transform to a raw FRED value series (oldest-first).
    Returns a list the same length (NaN-padded at the start for diff transforms).
    PURE — no pandas required for simple arithmetic."""
    import math
    if transform == "level":
        return list(values)
    if transform == "mom_diff":
        out: list[float] = [float("nan")]
        for i in range(1, len(values)):
            if not math.isnan(values[i]) and not math.isnan(values[i - 1]):
                out.append(values[i] - values[i - 1])
            else:
                out.append(float("nan"))
        return out
    if transform == "mom_pct":
        out = [float("nan")]
        for i in range(1, len(values)):
            prev = values[i - 1]
            if not math.isnan(values[i]) and not math.isnan(prev) and prev != 0:
                out.append(100.0 * (values[i] - prev) / prev)
            else:
                out.append(float("nan"))
        return out
    if transform == "yoy_pct":
        out = [float("nan")] * min(12, len(values))
        for i in range(12, len(values)):
            prev = values[i - 12]
            if not math.isnan(values[i]) and not math.isnan(prev) and prev != 0:
                out.append(100.0 * (values[i] - prev) / prev)
            else:
                out.append(float("nan"))
        return out
    return list(values)


def _finite(lst: list[float]) -> list[float]:
    import math
    return [x for x in lst if not math.isnan(x) and not math.isinf(x)]


def _mean(lst: list[float]) -> float | None:
    f = _finite(lst)
    return sum(f) / len(f) if f else None


def _std(lst: list[float]) -> float | None:
    import math
    f = _finite(lst)
    if len(f) < 2:
        return None
    mu = sum(f) / len(f)
    var = sum((x - mu) ** 2 for x in f) / (len(f) - 1)
    return math.sqrt(var)


# --------------------------------------------------------------------------- #
# Surprise math
# --------------------------------------------------------------------------- #
def _surprise_for_series(records: list[dict], entry: dict,
                         asof: datetime | None = None) -> dict | None:
    """Compute surprise statistics for one FRED series.
    Returns a dict with deltas, z-scores, summary, or None if not enough data.
    PURE beyond the records list (no network calls)."""
    import math
    asof = asof or datetime.now(timezone.utc)

    # Sort oldest-first, keep only dates on or before asof
    asof_date = asof.date().isoformat()
    rows = sorted(
        (r for r in records if r.get("date") and r["date"] <= asof_date),
        key=lambda r: r["date"],
    )
    if len(rows) < 3:
        return None

    raw_values = [float(r["value"]) if r.get("value") is not None else float("nan")
                  for r in rows]
    dates = [r["date"] for r in rows]

    transform = entry.get("transform", "level")
    series_t = _apply_transform(raw_values, transform)

    # Find the most recent finite observation
    latest_idx = None
    for i in range(len(series_t) - 1, -1, -1):
        if not math.isnan(series_t[i]):
            latest_idx = i
            break
    if latest_idx is None or latest_idx < 1:
        return None

    latest_val = series_t[latest_idx]
    latest_date = dates[latest_idx]

    # Prior print (the one before the latest)
    prior_val: float | None = None
    prior_date: str | None = None
    for i in range(latest_idx - 1, -1, -1):
        if not math.isnan(series_t[i]):
            prior_val = series_t[i]
            prior_date = dates[i]
            break

    delta_vs_prior: float | None = (
        round(latest_val - prior_val, 4) if prior_val is not None else None
    )

    # Trailing window statistics (use the series EXCLUDING the latest point)
    hist = [x for x in series_t[:latest_idx] if not math.isnan(x)]

    # 3-month and 6-month mean (approx by obs count: monthly=3/6, weekly=13/26, q=2/4)
    cadence = entry.get("cadence", "monthly")
    obs_3m = {"monthly": 3, "weekly": 13, "quarterly": 2}.get(cadence, 3)
    obs_6m = {"monthly": 6, "weekly": 26, "quarterly": 4}.get(cadence, 6)
    obs_3y = {"monthly": 36, "weekly": 156, "quarterly": 12}.get(cadence, 36)
    obs_5y = {"monthly": 60, "weekly": 260, "quarterly": 20}.get(cadence, 60)

    hist3m = hist[-obs_3m:] if len(hist) >= obs_3m else hist
    hist6m = hist[-obs_6m:] if len(hist) >= obs_6m else hist
    hist3y = hist[-obs_3y:] if len(hist) >= obs_3y else hist
    hist5y = hist[-obs_5y:] if len(hist) >= obs_5y else hist

    mean3m = _mean(hist3m)
    mean6m = _mean(hist6m)
    delta_vs_3m = round(latest_val - mean3m, 4) if mean3m is not None else None
    delta_vs_6m = round(latest_val - mean6m, 4) if mean6m is not None else None

    # Z-scores
    mu3y = _mean(hist3y)
    sd3y = _std(hist3y)
    mu5y = _mean(hist5y)
    sd5y = _std(hist5y)
    z3y = round((latest_val - mu3y) / sd3y, 2) if (mu3y is not None and sd3y and sd3y > 0) else None
    z5y = round((latest_val - mu5y) / sd5y, 2) if (mu5y is not None and sd5y and sd5y > 0) else None

    # Surprise size
    abs_z = abs(z3y) if z3y is not None else None
    if abs_z is None:
        surprise_size = "unknown"
    elif abs_z < 0.5:
        surprise_size = "inline"
    elif abs_z < 1.5:
        surprise_size = "notable"
    else:
        surprise_size = "large"

    # Direction tag (inflation-centric for inflation series)
    direction_map = entry.get("direction_map", "neutral")
    channel = entry.get("macro_channel", "growth")

    direction_tag = _direction_tag(latest_val, prior_val, delta_vs_prior,
                                   direction_map, channel, z3y)

    # Period label: for quarterly use the year-quarter of the raw date
    period = _period_label(latest_date, cadence, raw_values[-1] if raw_values else None)

    # Plain-English one-liner
    summary = _plain_english(
        entry["display_name"], period, latest_val, prior_val, delta_vs_prior,
        delta_vs_3m, z3y, surprise_size, direction_tag, transform, channel,
    )

    return {
        "release": entry["key"],
        "display_name": entry["display_name"],
        "macro_channel": channel,
        "period": period,
        "latest_date": latest_date,
        "actual": round(latest_val, 4),
        "prior": round(prior_val, 4) if prior_val is not None else None,
        "prior_date": prior_date,
        "prior_label": "vs revised prior",
        "transform": transform,
        "deltas": {
            "vs_prior": delta_vs_prior,
            "vs_3m_mean": delta_vs_3m,
            "vs_6m_mean": delta_vs_6m,
        },
        "z3y": z3y,
        "z5y": z5y,
        "surprise_size": surprise_size,
        "direction_tag": direction_tag,
        "summary": summary,
        "n_hist_3y": len(hist3y),
        "n_hist_5y": len(hist5y),
    }


def _period_label(date_str: str, cadence: str, _raw_val: Any = None) -> str:
    """Human-readable period label, e.g. 'May 2026', 'Q1 2026', 'wk of May 3'."""
    try:
        from datetime import date
        d = date.fromisoformat(date_str)
        if cadence == "quarterly":
            q = (d.month - 1) // 3 + 1
            return f"Q{q} {d.year}"
        if cadence == "weekly":
            return d.strftime("wk of %b %-d")
        return d.strftime("%b %Y")
    except Exception:  # noqa: BLE001
        return date_str


def _direction_tag(actual: float, prior: float | None, delta: float | None,
                   direction_map: str, channel: str, z3y: float | None) -> str:
    """Short direction/interpretation tag, e.g. 'inflation hotter', 'labor cooling'."""
    if delta is None:
        return ""
    channel_name = {
        "inflation": "inflation",
        "labor": "labor",
        "growth": "growth",
        "trade": "trade",
    }.get(channel, channel)

    if direction_map == "higher_hotter":
        if delta > 0:
            return f"{channel_name} hotter"
        elif delta < 0:
            return f"{channel_name} cooler"
        return f"{channel_name} unchanged"
    if direction_map == "higher_better":
        if delta > 0:
            return f"{channel_name} stronger"
        elif delta < 0:
            return f"{channel_name} weaker"
        return f"{channel_name} unchanged"
    if direction_map == "lower_better":
        # For unemployment/claims: lower is better
        if delta < 0:
            return f"{channel_name} improving"
        elif delta > 0:
            return f"{channel_name} deteriorating"
        return f"{channel_name} unchanged"
    return ""


def _plain_english(display_name: str, period: str, actual: float,
                   prior: float | None, delta: float | None,
                   delta_3m: float | None, z3y: float | None,
                   surprise_size: str, direction_tag: str,
                   transform: str, channel: str) -> str:
    """One-line plain-English summary. No jargon walls."""
    # Format the actual value
    if transform == "mom_pct" or transform == "yoy_pct":
        actual_fmt = f"{actual:+.1f}%"
        prior_fmt = f"{prior:+.1f}%" if prior is not None else "n/a"
        delta_fmt = f"{delta:+.2f}pp" if delta is not None else ""
    elif transform == "mom_diff":
        # Payrolls is in thousands
        actual_fmt = f"{actual:+,.0f}k" if channel == "labor" else f"{actual:+,.0f}"
        prior_fmt = f"{prior:+,.0f}k" if (prior is not None and channel == "labor") else (f"{prior:+,.0f}" if prior is not None else "n/a")
        delta_fmt = ""
    else:  # level
        if channel == "labor" and display_name.startswith("Unemployment"):
            actual_fmt = f"{actual:.1f}%"
            prior_fmt = f"{prior:.1f}%" if prior is not None else "n/a"
        elif channel == "labor":  # claims — thousands
            actual_fmt = f"{actual:,.0f}"
            prior_fmt = f"{prior:,.0f}" if prior is not None else "n/a"
        elif channel == "growth" and "GDP" in display_name:
            actual_fmt = f"{actual:.1f}%"
            prior_fmt = f"{prior:.1f}%" if prior is not None else "n/a"
        elif channel == "trade":
            actual_fmt = f"${actual:,.1f}bn"
            prior_fmt = f"${prior:,.1f}bn" if prior is not None else "n/a"
        else:
            actual_fmt = f"{actual:,.1f}"
            prior_fmt = f"{prior:,.1f}" if prior is not None else "n/a"
        delta_fmt = ""

    # Trend qualifier
    trend_q = ""
    if z3y is not None:
        if surprise_size == "large":
            trend_q = "well outside the 3y trend"
        elif surprise_size == "notable":
            trend_q = "outside the 3y trend"
        else:
            trend_q = "in line with the 3y trend"

    # Assemble
    parts = [f"{display_name}: {actual_fmt}"]
    if prior is not None:
        parts.append(f"vs {prior_fmt} revised prior")
    if trend_q:
        parts.append(trend_q)
    if direction_tag:
        parts.append(direction_tag)
    return "; ".join(parts) + "."


# --------------------------------------------------------------------------- #
# Lookback window check
# --------------------------------------------------------------------------- #

# Tiered lookback by cadence.
# Monthly series (CPI, PCE, payrolls, etc.) publish 4-6 weeks after their
# reference date, so a 10-day flat window structurally misses them ~25 of 30
# days.  Weekly series (ICSA) are available within a few days; quarterly GDP
# only publishes once per quarter.
#
# Windows are period-start dated (FRED observation date = start of reference
# period, not release date).  Measured reality on 2026-07-16: CPI/PPI/PCE/
# retail latest FRED obs ~76d old; inventories 106d; GDP 196d; claims 12d.
# Old windows (weekly=10, monthly=45, quarterly=95) dropped 8 of 10 series.
# New windows cover one full release cycle plus FRED lag:
#   weekly=14d   (7d release cadence + ~3d FRED lag + 4d buffer)
#   monthly=80d  (≈ June print with ~6-week FRED lag + a few days buffer)
#   quarterly=210d (≈ one quarter + ~6-week initial lag + revision cycle)
_LOOKBACK_BY_CADENCE: dict[str, int] = {
    "weekly":    14,
    "monthly":   80,
    "quarterly": 210,
}
_LOOKBACK_DEFAULT: int = 80


def lookback_days_for(entry: dict) -> int:
    """Return the appropriate lookback window (days) for a registry entry,
    keyed on the 'cadence' field.  PURE."""
    cadence = (entry.get("cadence") or "monthly").lower()
    return _LOOKBACK_BY_CADENCE.get(cadence, _LOOKBACK_DEFAULT)


def _within_lookback(latest_date: str, asof: datetime, lookback_days: int) -> bool:
    """True if the latest data point is within `lookback_days` of asof."""
    try:
        from datetime import date
        d = date.fromisoformat(latest_date)
        delta = (asof.date() - d).days
        return 0 <= delta <= lookback_days
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def _load_prior_cards(prior_artifact_path: "Path | str | None") -> dict[str, dict]:
    """Read the prior macro_releases.json and return a dict keyed by release key.
    Returns {} on any read/parse error — never raises.  Pure display-tier helper."""
    if prior_artifact_path is None:
        return {}
    try:
        from pathlib import Path as _Path
        p = _Path(prior_artifact_path)
        if not p.exists():
            return {}
        raw = json.loads(p.read_text())
        cards = raw.get("cards") or []
        return {c["release"]: c for c in cards if c.get("release")}
    except Exception as e:  # noqa: BLE001
        log.debug("macro_surprise: could not read prior artifact (%s)", e)
        return {}


def build_release_cards(asof: datetime | None = None,
                        lookback_days: int = 10,
                        prior_artifact_path: "Path | str | None" = None) -> dict:
    """Build macro-surprise cards for recent releases.

    The `lookback_days` parameter is now a FLOOR override only (kept for
    backward-compat); per-series windows are determined by cadence via
    ``lookback_days_for(entry)`` (weekly=14d, monthly=80d, quarterly=210d).
    A June CPI print therefore remains visible well into August rather than
    disappearing after 45 days.

    ``prior_artifact_path``: optional path to the previously-written
    macro_releases.json.  When a fresh FRED fetch returns an older observation
    than what was shown in the prior artifact (e.g. a flaky/rate-limited
    response), the prior card is kept verbatim and marked
    ``last_good_fallback=True``.  This prevents a transient fetch regression
    from silently shrinking the board.  Display-tier guard only — never touches
    scores or allocations.

    Returns:
      {
        "schema": "macro_releases.v1",
        "is_context_only": true,
        "asof": "<ISO datetime>",
        "cards": [...],           # only releases whose latest obs is within lookback
        "n_registry": int,        # total entries in registry
        "n_fetched": int,         # series successfully fetched from FRED
        "n_cards": int,           # cards emitted
        "skipped": [...],         # series that failed to fetch (logged, not raised)
      }

    Degrades to empty cards on ANY failure — never raises into the build.
    """
    asof = asof or datetime.now(timezone.utc)
    asof_iso = asof.isoformat()
    result: dict = {
        "schema": "macro_releases.v1",
        "is_context_only": True,
        "asof": asof_iso,
        "cards": [],
        "n_registry": len(RELEASE_REGISTRY),
        "n_fetched": 0,
        "n_cards": 0,
        "skipped": [],
    }

    # Load prior artifact for last-good fallback (display-tier only).
    prior_cards: dict[str, dict] = _load_prior_cards(prior_artifact_path)

    # Kill-criterion check: only run surprise math if ≥6 series verify
    fetched_entries: list[tuple[dict, list[dict]]] = []
    for entry in RELEASE_REGISTRY:
        sid = entry["fred_series"]
        try:
            records = _fetch_fred_series(sid)
        except Exception as e:  # noqa: BLE001 — degrade, never raise
            log.warning("macro_surprise: %s (%s) raised (%s) — skipping",
                        entry["key"], sid, e)
            result["skipped"].append({"key": entry["key"], "series": sid,
                                      "reason": f"exception: {e}"})
            continue
        if records is None or len(records) < 10:
            log.warning("macro_surprise: %s (%s) failed or too few rows — skipping",
                        entry["key"], sid)
            result["skipped"].append({"key": entry["key"], "series": sid,
                                      "reason": "fetch_failed_or_too_few"})
            continue
        fetched_entries.append((entry, records))

    result["n_fetched"] = len(fetched_entries)

    if result["n_fetched"] < 6:
        log.warning(
            "macro_surprise: only %d/%d series fetched — kill criterion triggered, "
            "emitting stub-suppression only, no surprise cards",
            result["n_fetched"], len(RELEASE_REGISTRY),
        )
        result["kill_criterion_triggered"] = True
        # Even under kill-criterion: rescue any prior cards that are still within
        # their lookback window so the board doesn't go blank on a bad FRED run.
        rescued: list[dict] = []
        for key, prior_card in prior_cards.items():
            prior_date = prior_card.get("latest_date", "")
            entry = next((e for e in RELEASE_REGISTRY if e["key"] == key), None)
            if entry is None:
                continue
            series_window = max(lookback_days, lookback_days_for(entry))
            if _within_lookback(prior_date, asof, series_window):
                rescued_card = dict(prior_card)
                rescued_card["last_good_fallback"] = True
                rescued.append(rescued_card)
        if rescued:
            log.warning(
                "macro_surprise: rescued %d prior cards under kill-criterion",
                len(rescued),
            )
            result["cards"] = rescued
            result["n_cards"] = len(rescued)
            result["last_good_rescued"] = len(rescued)
        return result

    # Build cards — use tiered per-series lookback (cadence-keyed)
    cards: list[dict] = []
    for entry, records in fetched_entries:
        key = entry["key"]
        try:
            surprise = _surprise_for_series(records, entry, asof)
            if surprise is None:
                continue
            # Per-series window: weekly=14d, monthly=80d, quarterly=210d.
            # The `lookback_days` param is honoured as a minimum floor so callers
            # can pass a smaller value for testing; in production pass the default.
            series_window = max(lookback_days, lookback_days_for(entry))

            # Last-good fallback: if the freshly-fetched latest_date is OLDER
            # than what the prior artifact showed for this series, a transient
            # FRED regression is silently shrinking the board.  Keep the prior
            # card (marked last_good_fallback=True) instead of dropping the card.
            fresh_date = surprise.get("latest_date", "")
            prior_card = prior_cards.get(key)
            if prior_card:
                prior_date = prior_card.get("latest_date", "")
                if prior_date and fresh_date and fresh_date < prior_date:
                    log.warning(
                        "macro_surprise: %s fresh latest_date %s < prior %s — "
                        "keeping prior card (last_good_fallback)",
                        key, fresh_date, prior_date,
                    )
                    fallback = dict(prior_card)
                    fallback["last_good_fallback"] = True
                    # Still apply lookback filter to the prior date
                    if _within_lookback(prior_date, asof, series_window):
                        fallback["lookback_days"] = series_window
                        cards.append(fallback)
                    continue  # do not emit the stale fresh card

            if not _within_lookback(fresh_date, asof, series_window):
                continue
            # Expose the effective window so the board can display it accurately.
            surprise["lookback_days"] = series_window
            cards.append(surprise)
        except Exception as e:  # noqa: BLE001 — degrade, never raise
            log.warning("macro_surprise: card build failed for %s (%s)", key, e)

    # Completeness rescue: a series whose fetch failed outright (or whose surprise
    # math returned None) never reaches the loop above, so the fresh_date<prior_date
    # branch cannot fire.  Invariant: a card present in the prior artifact and still
    # within its lookback window never vanishes unless replaced by fresher data.
    _have = {c.get("release") for c in cards}
    for key, prior_card in prior_cards.items():
        if key in _have:
            continue
        entry = next((e for e in RELEASE_REGISTRY if e["key"] == key), None)
        if entry is None:
            continue
        series_window = max(lookback_days, lookback_days_for(entry))
        if _within_lookback(prior_card.get("latest_date", ""), asof, series_window):
            log.warning("macro_surprise: %s missing from fresh fetch — keeping prior "
                        "card (last_good_fallback)", key)
            fallback = dict(prior_card)
            fallback["last_good_fallback"] = True
            fallback["lookback_days"] = series_window
            cards.append(fallback)

    result["cards"] = cards
    result["n_cards"] = len(cards)
    # Top-level metadata: effective windows by cadence (display context, not copy)
    result["lookback_by_cadence"] = dict(_LOOKBACK_BY_CADENCE)
    return result
